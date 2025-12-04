# core/routing.py
from django.urls import re_path

# Correct imports — consumers.py is in the same folder
from core.consumers import AdminDashboardConsumer, TaskConsumer

websocket_urlpatterns = [
    re_path(r'ws/admin/$', AdminDashboardConsumer.as_asgi()),
    re_path(r'ws/client/$', AdminDashboardConsumer.as_asgi()),
    re_path(r'ws/task/(?P<task_id>\d+)/$', TaskConsumer.as_asgi()),
]