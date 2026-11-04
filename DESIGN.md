
# Design: Rate-Limited Asynchronous Email Queue

## 1. Problem and scale

During a flash sale, the system receives 2,000 order-confirmation email
requests in less than 10 seconds. The email provider allows 200 emails per
minute. That is an average of about 3.33 emails per second.

At the average rate, about 33 emails can be sent in 10 seconds if sending is
evenly paced. The actual number depends on the rate-limiter algorithm and the
starting quota. Sending all 2,000 emails takes at least 10 minutes of provider
capacity, assuming no retries or outages.

Accepting the burst within 10 seconds means accepting and enqueueing the
requests. It does not mean delivering every email within that time. The API
should enqueue the work and return promptly instead of calling the provider
directly.

## 2. Options considered

### 2.1 Celery + Redis

Advantages

- Celery provides task execution, queue handling, acknowledgement controls,
  and retry support.
- Redis can act as both the broker and shared storage for a global rate
  limiter.
- Celery and Redis have established monitoring and operational tools.

Disadvantages

- Django, Redis, and Celery workers must be operated and monitored.
- Celery's built-in rate limit applies to each worker. It does not enforce one
  shared quota across workers. A separate shared rate limiter is needed.
- Redis durability depends on its persistence and deployment settings.
  Persistence lowers the risk of losing queued work, but cannot prevent data
  loss in every failure.
- Late acknowledgements can cause a task to run again. They do not guarantee
  that an email is delivered exactly once.

### 2.2 Django Q / Django Q2

Advantages

- Django Q2 can use the Django ORM as a broker. In some deployments, this
  reduces the need for separate broker infrastructure.
- It supports task execution and retry settings.
- It offers broker choices for different infrastructure needs.

Disadvantages

- An ORM broker can add database writes and polling alongside application
  queries.
- A shared rate limiter is still needed to enforce the provider's global
  quota.
- Retry behavior and compatibility depend on the package version and broker
  settings.
- Before adopting it, check its maintenance status, supported Django
  versions, and security updates.

### 2.3 Custom queue implementation

Advantages

- It provides full control over job storage, scheduling, retries, and rate
  limiting.
- It can be tailored to a specific workload.

Disadvantages

- Reliable processing requires a way to recover jobs claimed by workers that
  crash.
- Redis `BRPOP` removes a job before processing. If a worker crashes, the job
  can be lost unless a recovery mechanism is added.
- The application must handle retries, exponential backoff, dead letters,
  monitoring, and recovery.
- This increases implementation and maintenance risks.

## 3. Decision

I chose Celery with Redis. Celery runs the tasks and manages acknowledgements.
The task code retries provider failures with exponential backoff, up to five
attempts. Redis serves as both the broker and the shared rate-limiter store.

The application uses a custom atomic sliding-window limiter. This ensures the
provider's limit of 200 emails per minute applies across all workers. Jobs
that reach the provider retry limit are marked `DEAD` in the database.

The design accepts requests quickly and sends emails asynchronously at a
controlled rate. A successful enqueue does not guarantee successful delivery.

## 4. Rate limiter

### 4.1 Why a sliding window?

The requirement is no more than 200 sends in any rolling 60-second period.
A token bucket with a capacity of 200 can allow 200 immediate sends, followed
by more as tokens refill. A fixed-window counter can allow nearly 400 sends
across a minute boundary.

A sliding-window limiter checks reservations from the previous 60 seconds.
It allows a new reservation only when quota is available, directly matching
the rolling-window requirement.

The limiter stores one sorted-set entry per reservation and uses more Redis
operations than a simple counter. With a quota of 200, the active set remains
small.

### 4.2 Atomicity

The limiter uses a Redis Lua script to remove expired entries, count active
reservations, and record an allowed reservation in one atomic operation.
Redis runs the script without interleaving commands from other clients.

The script uses Redis server time, so workers do not depend on their own
system clocks. Each reservation has a unique member. This prevents
reservations made in the same millisecond from overwriting each other.

The key expires when it becomes idle. The sorted-set window logic enforces
the quota.

### 4.3 Redis failure policy: fail closed

The limiter fails closed. If it cannot obtain a reservation, the task does
not send the email. Redis errors trigger a retry instead of bypassing the
limiter.

Redis also serves as the broker. An outage can prevent new jobs from being
enqueued and disrupt workers' access to queued messages. The API should report
an enqueue failure rather than claim that the email was accepted.

Failing closed prevents unmetered sending. However, new jobs cannot be
accepted if a broker outage prevents enqueueing.

## 5. Reliability: retries, dead letters, and worker crashes

### 5.1 Provider retries

When the provider raises `ProviderError`, the task increments
`EmailJob.attempts` and saves the error in `last_error`. It retries with an
exponential delay of `min(2 ** attempts, 300)` seconds. After five failed
attempts, it marks the job `DEAD`.

The application uses the database attempt counter to limit provider retries.
It does not rely on Celery's `autoretry_for` setting.

Redis errors use a separate retry path with a five-second delay. Celery's
retry counter is unlimited for this task, while provider retries are limited
by `MAX_PROVIDER_ATTEMPTS`.

Rate-limit denials do not increase the provider attempt count because the
provider was not called.

### 5.2 Dead-letter handling

After five provider failures, the existing `EmailJob` row becomes the
dead-letter record. Its status is `DEAD`, and the row stores the error. This
avoids a separate dead-letter queue and keeps failed jobs available in the
database.

Requeueing a dead job after fixing the cause is a manual operation.
Automated review and replay tools are not included.

### 5.3 Rate-limit denial

When the limiter denies a reservation, the task schedules another message
with `apply_async(countdown=...)`. It does not block a worker with
`time.sleep()`. The countdown includes the limiter's retry delay and random
jitter to spread out simultaneous retries.

The provider attempt counter does not increase. A task may be rescheduled
several times while it waits for quota.

Duplicate messages are possible if the replacement message is published but
the current task is not acknowledged. The database status check skips jobs
that are no longer pending. It does not make database and broker updates
atomic.

### 5.4 Worker termination and redelivery

The task sets `acks_late=True`, so Celery acknowledges it after execution.
`reject_on_worker_lost=True` asks Celery to requeue it if the worker child
process is lost.

With a Redis broker, an unacknowledged task can be redelivered after the
visibility timeout. This project sets the timeout to 120 seconds. It must be
longer than the maximum task runtime and countdown. Otherwise, a message could
be redelivered while its original execution is still running.

`worker_prefetch_multiplier=1` limits how many messages a worker reserves
before processing them. When a message is redelivered, the task checks the
`EmailJob` status and skips jobs that are no longer pending.

These settings help with recovery but do not prove that every crash scenario
is handled. A worker-termination test should verify redelivery and confirm
that completed jobs are not sent again.

### 5.5 Delivery guarantee

This design provides at-least-once task processing, not exactly-once email
delivery. If the provider accepts an email but the worker stops before saving
`status=SENT`, a redelivered task may send it again. A task that runs longer
than the visibility timeout may also overlap with its redelivery.

If the provider supports idempotency keys, they can reduce duplicate
deliveries. The limiter reserves quota before the provider call, so failed
attempts still use quota. This helps ensure that the provider's limit is not
exceeded.

## 6. Redis failure behaviour

Redis serves as both the Celery broker and the shared rate-limiter store. An
outage can affect queue operations and permission to send.

The task does not bypass the limiter when Redis is unavailable. It retries
after Redis errors, and the API should report enqueue failures. Choose Redis
persistence and recovery settings to meet the deployment's durability needs.
Test those settings under failure conditions.

In production, monitor Redis availability, queue depth, the age of the oldest
job, retry volume, and dead-letter count. Recovery procedures should explain
how to restore Redis, check pending jobs, and safely replay dead-lettered
work.

## 7. Known limitations

- Email delivery is not exactly once. The provider may accept a message
  before the application records success, so a retry could send it again.
- Saving an `EmailJob` and publishing its Celery message are separate
  operations. A transactional outbox could help recover from failures between
  them.
- Redis durability depends on persistence and failover settings. Test queue
  and rate-limit state across restarts and failures.
- Dead-lettered jobs need manual review and requeueing. There are no automated
  replay tools.
- Run and record a worker-crash recovery test before claiming that a
  `SIGKILL` scenario has been verified.
- The ORM benchmark measures local SQLite query counts. It shows fewer
  queries, but does not reproduce the production latency issue or prove a
  specific production response-time improvement.
