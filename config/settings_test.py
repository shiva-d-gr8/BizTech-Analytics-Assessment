from .settings import *  # noqa: F401,F403

# Use a separate Redis database so tests do not affect development data.
REDIS_URL = "redis://localhost:6379/1"
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL

# Use a shorter window so 500 test jobs finish quickly.
EMAIL_RATE_LIMIT = 100
EMAIL_RATE_WINDOW_SECONDS = 2

# Use a file-based test database shared by the worker and test threads.
DATABASES["default"]["TEST"] = {"NAME": str(BASE_DIR / "test_db.sqlite3")}  # noqa: F405
DATABASES["default"]["OPTIONS"] = {"timeout": 20}  # noqa: F405
