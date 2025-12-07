# core/email_service.py
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
import threading


def _send_async(email: EmailMultiAlternatives):
    """
    Fire-and-forget sender so API requests don't block on SMTP.
    """
    try:
        email.send(fail_silently=True)
    except Exception as e:
        # Don't crash request threads due to SMTP errors
        print(f"[email] send failed: {e}")


def send_new_task_notification(task):
    """
    Send email notification when a new task is created.

    Per your request: send FROM ad.academiqa@gmail.com TO the explicit list below.
    (You can add/remove recipients in EXTRA_ADMIN_EMAILS.)
    """
    if getattr(settings, "DISABLE_EMAILS", False):
        print("[email] skipped: DISABLE_EMAILS=1")
        return

    # Explicit recipients (you can uncomment / add more as needed)
    EXTRA_ADMIN_EMAILS = [
        "mbokenn95@gmail.com",
        # "odugucalvince@gmail.com",
        # "Briansimiyu13@gmail.com",
    ]

    # If you want to include *all* admin users as well, flip this to True.
    INCLUDE_DB_ADMINS = False

    recipients = set(EXTRA_ADMIN_EMAILS)

    if INCLUDE_DB_ADMINS:
        try:
            from .models import UserProfile
            admin_profiles = UserProfile.objects.filter(role='admin', user__is_active=True)
            for p in admin_profiles:
                if p.user.email:
                    recipients.add(p.user.email)
        except Exception as e:
            print(f"[email] failed to collect admin emails: {e}")

    recipients = [r for r in recipients if r]  # drop empties
    if not recipients:
        print("[email] no recipients; skipping")
        return

    task_code = task.task_id or f"TSK{task.id:04d}"
    subject = f"NEW TASK • {task.title} • {task_code}"

    context = {
        'task_title': task.title,
        'task_subject': getattr(task, 'subject', None) or "Not specified",
        'education_level': getattr(task, 'education_level', None) or "Not specified",
        'deadline': task.deadline.strftime('%B %d, %Y at %I:%M %p') if getattr(task, 'deadline', None) else "Not set",
        'proposed_budget': f"${getattr(task, 'proposed_budget', '')}",
        'student_name': task.client.get_full_name() or task.client.username,
        'student_email': task.client.email,
        'task_id': task_code,
        'task_url': f"{settings.FRONTEND_URL}/admin/dashboard",
    }

    html_message = render_to_string('emails/new_task_notification.html', context)
    plain_message = strip_tags(html_message)

    email = EmailMultiAlternatives(
        subject=subject,
        body=plain_message,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", settings.EMAIL_HOST_USER),
        to=recipients,
    )
    email.attach_alternative(html_message, "text/html")

    # Send in background (non-blocking)
    threading.Thread(target=_send_async, args=(email,), daemon=True).start()
    print(f"[email] queued new task email to: {recipients}")


def send_task_status_update(task, student, update_message):
    """
    Email student when task status is updated.
    """
    if getattr(settings, "DISABLE_EMAILS", False):
        print("[email] skipped: DISABLE_EMAILS=1")
        return

    subject = f"Task Update: {task.title}"

    context = {
        'student_name': student.get_full_name() or student.username,
        'task_title': task.title,
        'task_status': task.get_status_display(),
        'update_message': update_message,
        'admin_name': task.assigned_admin.get_full_name() if getattr(task, 'assigned_admin', None) else None,
        'task_url': f"{settings.FRONTEND_URL}/client/dashboard/tasks/{task.id}"
    }

    html_message = render_to_string('emails/task_status_update.html', context)
    plain_message = strip_tags(html_message)

    email = EmailMultiAlternatives(
        subject=subject,
        body=plain_message,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", settings.EMAIL_HOST_USER),
        to=[student.email],
    )
    email.attach_alternative(html_message, "text/html")
    threading.Thread(target=_send_async, args=(email,), daemon=True).start()
    print(f"[email] queued task status update to: {student.email}")


def send_new_message_notification(task, message, recipient):
    """
    Email notification for new chat messages.
    """
    if getattr(settings, "DISABLE_EMAILS", False):
        print("[email] skipped: DISABLE_EMAILS=1")
        return

    subject = f"New Message - Task: {task.title}"

    preview = (message.message[:100] + '...') if len(message.message or "") > 100 else (message.message or "")
    sender_name = (
        getattr(message, "sender", None) and (getattr(message.sender, "get_full_name", lambda: "")() or getattr(message.sender, "username", None))
    ) or "User"

    context = {
        'task_title': task.title,
        'sender_name': sender_name,
        'message_preview': preview,
        'task_url': f"{settings.FRONTEND_URL}/client/dashboard/tasks/{task.id}",
    }

    html_message = render_to_string('emails/new_message_notification.html', context)
    plain_message = strip_tags(html_message)

    email = EmailMultiAlternatives(
        subject=subject,
        body=plain_message,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", settings.EMAIL_HOST_USER),
        to=[recipient.email],
    )
    email.attach_alternative(html_message, "text/html")
    threading.Thread(target=_send_async, args=(email,), daemon=True).start()
    print(f"[email] queued new message notification to: {recipient.email}")
