# core/tasks.py
from celery import shared_task
from django.contrib.auth.models import User
from .models import Notification, Task
from .email_service import send_new_task_notification, send_task_status_update, send_new_message_notification

@shared_task
def create_notification(user_id, title, message, task_id=None, notification_type='system'):
    """Create a notification in the database"""
    user = User.objects.get(id=user_id)
    task = Task.objects.get(id=task_id) if task_id else None
    
    Notification.objects.create(
        user=user,
        notification_type=notification_type,
        title=title,
        message=message,
        task=task
    )

@shared_task
def notify_new_task(task_id):
    """Send email notifications for new task"""
    try:
        task = Task.objects.get(id=task_id)
        send_new_task_notification(task)
        
        # Also create in-app notifications for admins
        from .models import UserProfile
        admins = UserProfile.objects.filter(role='admin', user__is_active=True)
        for admin in admins:
            create_notification.delay(
                admin.user.id,
                "New Task Submitted",
                f"New task '{task.title}' has been submitted and requires review.",
                task.id,
                'task_created'
            )
    except Task.DoesNotExist:
        pass

@shared_task
def notify_task_status_update(task_id, update_message):
    """Send email notification for task status update"""
    try:
        task = Task.objects.get(id=task_id)
        send_task_status_update(task, task.client, update_message)
    except Task.DoesNotExist:
        pass

@shared_task
def notify_new_message(task_id, message_id):
    """Send email notification for new chat message"""
    from .models import ChatMessage
    try:
        message = ChatMessage.objects.get(id=message_id)
        task = Task.objects.get(id=task_id)
        
        # Determine recipient (opposite of sender)
        if message.sender == task.client:
            recipient = task.assigned_admin
        else:
            recipient = task.client
            
        if recipient:
            send_new_message_notification(task, message, recipient)
    except (ChatMessage.DoesNotExist, Task.DoesNotExist):
        pass

@shared_task
def check_deadlines():
    """Check for approaching deadlines and send notifications"""
    from django.utils import timezone
    from datetime import timedelta
    
    # Tasks with deadlines in the next 24 hours
    approaching_deadline = timezone.now() + timedelta(hours=24)
    tasks = Task.objects.filter(
        deadline__lte=approaching_deadline,
        deadline__gt=timezone.now(),
        status__in=['in_progress', 'submitted']
    )
    
    for task in tasks:
        create_notification.delay(
            task.assigned_admin.id if task.assigned_admin else task.client.id,
            "Deadline Approaching",
            f"Task '{task.title}' is due in less than 24 hours.",
            task.id,
            'deadline_approaching'
        )