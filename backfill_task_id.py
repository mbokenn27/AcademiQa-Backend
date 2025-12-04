# backfill_task_id.py
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'task_manager.settings')
django.setup()

from core.models import Task

def backfill():
    # Find tasks with no task_id
    tasks = Task.objects.filter(task_id__isnull=True) | Task.objects.filter(task_id='')
    total = tasks.count()
    print(f"Found {total} tasks without task_id")

    for i, task in enumerate(tasks, 1):
        task.task_id = f"TSK{task.id:04d}"
        task.save(update_fields=['task_id'])
        print(f"[{i}/{total}] Task {task.id} → {task.task_id}")

    print("Backfill complete! All tasks now have TSK IDs.")

if __name__ == "__main__":
    backfill()