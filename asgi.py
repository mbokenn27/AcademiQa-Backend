import os
from django.core.asgi import get_asgi_application

from channels.routing import ProtocolTypeRouter, URLRouter
from core.routing import websocket_urlpatterns
from core.middleware import JWTAuthMiddleware  

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'task_manager.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": JWTAuthMiddleware(              
        URLRouter(websocket_urlpatterns)
    ),
})