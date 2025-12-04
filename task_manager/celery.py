# task_manager/celery.py
import os
from celery import Celery

# Set the default Django settings module for the 'celery' program
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'task_manager.settings')

# Create Celery app
app = Celery('task_manager')

# Load task modules from all registered Django apps
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all apps (e.g., core/tasks.py)
app.autodiscover_tasks(['core'])

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')