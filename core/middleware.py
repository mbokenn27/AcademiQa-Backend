from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware


@database_sync_to_async
def get_user_from_token(token):
    try:
        # Import here (AFTER apps are ready)
        from rest_framework_simplejwt.authentication import JWTAuthentication
        validated = JWTAuthentication().get_validated_token(token)
        return JWTAuthentication().get_user(validated)
    except Exception:
        # Import here too
        from django.contrib.auth.models import AnonymousUser
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode()
        params = parse_qs(query_string)

        token = params.get("token", [None])[0]

        if token:
            scope["user"] = await get_user_from_token(token)
        else:
            from django.contrib.auth.models import AnonymousUser
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)
