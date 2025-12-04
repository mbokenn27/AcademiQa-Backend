from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from django.http import JsonResponse, HttpResponseRedirect
from django.conf import settings
from django.conf.urls.static import static

def healthz(_request):
    return JsonResponse({"ok": True})

def favicon(_request):
    return HttpResponseRedirect("/static/favicon.ico")

urlpatterns = [
    # Health (both variants to avoid redirects)
    path("healthz", healthz),
    path("healthz/", healthz),

    # Favicon (served by WhiteNoise after collectstatic)
    path("favicon.ico", favicon),

    # App routes
    path("", include("core.urls")),      # core handles / and /api/... as you designed
    path("admin/", admin.site.urls),
    #path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
