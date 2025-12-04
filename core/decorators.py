from django.shortcuts import redirect
from django.core.exceptions import PermissionDenied

def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')

        # check if profile exists and role is admin
        if hasattr(request.user, 'userprofile') and request.user.userprofile.role == 'admin':
            return view_func(request, *args, **kwargs)

        raise PermissionDenied  # or redirect('client_dashboard')
    return wrapper


def client_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')

        if hasattr(request.user, 'userprofile') and request.user.userprofile.role == 'client':
            return view_func(request, *args, **kwargs)

        raise PermissionDenied  # or redirect('admin_dashboard')
    return wrapper
