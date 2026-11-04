import os
import smtplib
import time

from django.core.mail import send_mail


class ProviderError(Exception):
    """Represent a transient email-provider failure, such as a timeout or 5xx response."""


def send_via_provider(job):
    """Send one email through Django's configured EMAIL_BACKEND."""
    # An optional delay lets the demo simulate a slow provider and worker termination.
    delay = float(os.environ.get("DEMO_SEND_DELAY", "0"))
    if delay:
        time.sleep(delay)
    try:
        send_mail(
            subject=job.subject,
            message=job.body,
            from_email="noreply@example.com",
            recipient_list=[job.recipient],
            fail_silently=False,
        )
    except (OSError, smtplib.SMTPException) as exc:
        raise ProviderError(str(exc)) from exc
