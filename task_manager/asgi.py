# task_manager/asgi.py
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "task_manager.settings")

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter

from core.routing import websocket_urlpatterns
from core.middleware import JWTAuthMiddleware  # ensure this module exists

# Instantiate once to avoid side effects
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(
        URLRouter(websocket_urlpatterns)
    ),
})
