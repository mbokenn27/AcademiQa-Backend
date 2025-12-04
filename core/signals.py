# # core/signals.py
# from django.db.models.signals import post_save, post_delete
# from django.dispatch import receiver
# from channels.layers import get_channel_layer
# from asgiref.sync import async_to_sync
# from .models import Task, ChatMessage
# from .tasks import notify_new_task, notify_task_status_update, notify_new_message

# @receiver(post_save, sender=Task)
# def task_changed(sender, instance, created, **kwargs):
#     channel_layer = get_channel_layer()
#     if channel_layer:
#         task_data = {
#             "id": instance.id,
#             "status": instance.status,
#             "negotiation_status": instance.negotiation_status,
#             "admin_counter_budget": str(instance.admin_counter_budget) if instance.admin_counter_budget else None,
#             "budget": str(instance.budget) if instance.budget else None,
#             "proposed_budget": str(instance.proposed_budget),
#         }

#         async_to_sync(channel_layer.group_send)(
#             "admin_dashboard",
#             {"type": "task_updated", "task": task_data}
#         )
#         async_to_sync(channel_layer.group_send)(
#             f"client_{instance.client.id}",
#             {"type": "task_updated", "task": task_data}
#         )

#         if created:
#             async_to_sync(channel_layer.group_send)(
#                 "admin_dashboard",
#                 {"type": "task_created", "task": task_data}
#             )

# @receiver(post_save, sender=ChatMessage)
# def message_sent(sender, instance, created, **kwargs):
#     if created:
#         notify_new_message.delay(instance.task.id, instance.id)