from celery import Celery

from app.core.config import get_settings

celery_app = Celery("ai-native", broker=get_settings().redis_url, include=["app.worker.tasks"])
celery_app.conf.broker_connection_retry_on_startup = True
