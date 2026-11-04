from .models import EmailJob
from .tasks import send_email_task


def enqueue_email(idempotency_key, recipient, subject, body):
    """Create an email job and enqueue it; return ``(job, created)``.

    If enqueueing fails, for example because Redis is unavailable, delete the
    newly created row and propagate the error. This allows the API to return
    a 503 response instead of reporting that the email was accepted.
    """
    job, created = EmailJob.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={"recipient": recipient, "subject": subject, "body": body},
    )
    if created:
        try:
            send_email_task.delay(job.id)
        except Exception:
            job.delete()
            raise
    return job, created
