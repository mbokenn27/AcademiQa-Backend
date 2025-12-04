import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'task_manager.settings')
import django
django.setup()
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Task, ChatMessage

class TaskConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.task_id = self.scope['url_route']['kwargs']['task_id']
        self.room_group_name = f"task_{self.task_id}"

        if self.scope["user"].is_anonymous:
            await self.close()
            return

        has_access = await self.verify_task_access(self.task_id, self.scope["user"])
        if not has_access:
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'chat_message':
                content = data.get('message', '').strip()
                file_data = data.get('file')  # { url: "...", name: "file.pdf" }

                # Save message + file info
                message_obj = await self.create_chat_message(
                    task_id=self.task_id,
                    user=self.scope["user"],
                    content=content,
                    file_url=file_data.get('url') if file_data else None,
                    file_name=file_data.get('name') if file_data else None
                )

                # BROADCAST TO EVERYONE — THIS IS THE KEY
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'message': {
                            'id': message_obj.id,
                            'sender': self.scope["user"].username,
                            'sender_role': self.scope["user"].profile.role if hasattr(self.scope["user"], 'profile') else 'client',
                            'message': content,
                            'file_url': file_data.get('url') if file_data else None,
                            'file_name': file_data.get('name') if file_data else None,
                            'created_at': message_obj.created_at.isoformat(),
                            'is_read': False
                        }
                    }
                )

            elif message_type == 'typing':
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'user_typing',
                        'user_id': self.scope["user"].id,
                        'username': self.scope["user"].username,
                        'is_typing': data['is_typing']
                    }
                )

        except Exception as e:
            print("WebSocket receive error:", e)

    # ──────────────────────────────────────────────────────────────
    # Event handlers
    # ──────────────────────────────────────────────────────────────
    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message']
        }))

    async def user_typing(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_typing',
            'user_id': event['user_id'],
            'username': event['username'],
            'is_typing': event['is_typing']
        }))

    async def task_updated(self, event):
        await self.send(text_data=json.dumps({
            'type': 'task_updated',
            'task': event['task']
        }))

    # ──────────────────────────────────────────────────────────────
    # Database helpers
    # ──────────────────────────────────────────────────────────────
    @database_sync_to_async
    def verify_task_access(self, task_id, user):
        try:
            task = Task.objects.get(id=task_id)
            return (user == task.client or 
                    user == task.assigned_admin or 
                    (hasattr(user, 'profile') and user.profile.role == 'admin'))
        except Task.DoesNotExist:
            return False

    @database_sync_to_async
    def create_chat_message(self, task_id, user, content, file_url=None, file_name=None):
        task = Task.objects.get(id=task_id)
        return ChatMessage.objects.create(
            task=task,
            sender=user,
            message=content or "",
            file_name=file_name or "",
            file_url=file_url or ""
        )

class AdminDashboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        
        if user.is_anonymous:
            await self.close()
            return

        # Admins → join "admin_dashboard" group
        if await self.is_admin(user):
            await self.channel_layer.group_add("admin_dashboard", self.channel_name)
        
        # Clients → join their own group so they can receive task updates
        else:
            await self.channel_layer.group_add(f"client_{user.id}", self.channel_name)
        
        await self.accept()

    async def disconnect(self, close_code):
        user = self.scope["user"]
        if not user.is_anonymous:
            if await self.is_admin(user):
                await self.channel_layer.group_discard("admin_dashboard", self.channel_name)
            else:
                await self.channel_layer.group_discard(f"client_{user.id}", self.channel_name)

    # Keep your existing event handlers
    async def task_updated(self, event):
        await self.send(text_data=json.dumps({
            'type': 'task_updated',
            'task': event['task']
        }))

    async def task_created(self, event):
        await self.send(text_data=json.dumps({
            'type': 'task_created',
            'task': event['task']
        }))

    @database_sync_to_async
    def is_admin(self, user):
        return hasattr(user, 'profile') and user.profile.role == 'admin'