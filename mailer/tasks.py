import math
import random

from celery import shared_task
from redis.exceptions import RedisError

from .models import EmailJob
from .provider import ProviderError, send_via_provider
from .ratelimit import get_email_rate_limiter

MAX_PROVIDER_ATTEMPTS = 5
MAX_BACKOFF_SECONDS = 300
REDIS_RETRY_SECONDS = 5


@shared_task(
    bind=True,
    acks_late=True,  # Acknowledge the task after it finishes.
    reject_on_worker_lost=True,  # Requeue the task if its worker process is lost.
    max_retries=None,  # Redis retries are unlimited; provider retries use the job's attempt count.
)
def send_email_task(self, job_id):
    try:
        job = EmailJob.objects.get(pk=job_id)
    except EmailJob.DoesNotExist:
        return "missing"

    # Skip completed jobs. This does not prevent concurrent duplicate executions.
    if job.status != EmailJob.Status.PENDING:
        return f"skipped:{job.status}"

    # Request a shared rate-limit reservation. Fail closed if Redis is unavailable.
    try:
        allowed, retry_after_ms, _reserved_at_ms = get_email_rate_limiter().acquire()
    except RedisError as exc:
        raise self.retry(exc=exc, countdown=REDIS_RETRY_SECONDS)

    if not allowed:
        # Reschedule without incrementing job.attempts or blocking a worker.
        # Jitter spreads out jobs that were denied together.
        countdown = math.ceil(retry_after_ms / 1000) + random.randint(0, 5)
        send_email_task.apply_async(args=[job_id], countdown=countdown)
        return "rate_limited"

    # Provider failures use the job's own attempt counter.
    try:
        send_via_provider(job)
    except ProviderError as exc:
        job.attempts += 1
        job.last_error = str(exc)
        if job.attempts >= MAX_PROVIDER_ATTEMPTS:
            job.status = EmailJob.Status.DEAD  # Mark the job as dead-lettered.
            job.save(update_fields=["attempts", "last_error", "status", "updated_at"])
            return "dead"
        job.save(update_fields=["attempts", "last_error", "updated_at"])
        countdown = min(2 ** job.attempts, MAX_BACKOFF_SECONDS)  # Apply exponential backoff.
        raise self.retry(exc=exc, countdown=countdown)

    job.status = EmailJob.Status.SENT
    job.save(update_fields=["status", "updated_at"])
    return "sent"
