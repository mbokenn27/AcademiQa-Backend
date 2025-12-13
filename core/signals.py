# file: core/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import Task, ChatMessage
from .email_service import send_new_task_notification  # why: actually send email on creation

@receiver(post_save, sender=Task)
def task_changed(sender, instance: Task, created: bool, **kwargs):
    # Broadcast to admin/clients for live updates
    channel_layer = get_channel_layer()
    if channel_layer:
        task_data = {
            "id": instance.id,
            "status": instance.status,
            "negotiation_status": instance.negotiation_status,
            "admin_counter_budget": str(instance.admin_counter_budget) if instance.admin_counter_budget else None,
            "budget": str(instance.budget) if instance.budget is not None else None,
            "proposed_budget": str(instance.proposed_budget),
            "title": instance.title,
        }
        async_to_sync(channel_layer.group_send)("admin_dashboard", {"type": "task_updated", "task": task_data})
        async_to_sync(channel_layer.group_send)(f"client_{instance.client.id}", {"type": "task_updated", "task": task_data})

    if created:
        # Send the email immediately on new task creation
        try:
            send_new_task_notification(instance)  # why: previously never invoked anywhere
        except Exception as exc:
            # keep silent failure from crashing request; logs are in email_service
            print(f"[signals] failed to send new task email: {exc}")
        # Also broadcast a 'created' event for dashboards
        if get_channel_layer():
            async_to_sync(channel_layer.group_send)("admin_dashboard", {"type": "task_created", "task": {"id": instance.id, "title": instance.title}})

@receiver(post_save, sender=ChatMessage)
def message_sent(sender, instance: ChatMessage, created: bool, **kwargs):
    if not created:
        return
    # (Optional) enqueue chat email notifications here if you want
    # from .email_service import send_new_message_notification
    # recipient = instance.task.assigned_admin or instance.task.client
    # send_new_message_notification(instance.task, instance, recipient)
