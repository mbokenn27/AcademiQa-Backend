# core/email_service.py

from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
import os
import socket

SMTP_DEBUG = os.getenv("SMTP_DEBUG", "0") == "1"

RECIPIENTS_NEW_TASK = [
    "mbokenn95@gmail.com",
    # "odugucalvince@gmail.com",
    # "Briansimiyu13@gmail.com",
]


def _open_smtp_connection():
    """
    Open a Django email connection and (optionally) enable low-level SMTP debug.
    Returns (connection, debug_enabled).
    """
    conn = get_connection(
        backend=getattr(settings, "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"),
        host=getattr(settings, "EMAIL_HOST", "smtp.gmail.com"),
        port=int(getattr(settings, "EMAIL_PORT", 587)),
        username=getattr(settings, "EMAIL_HOST_USER", None),
        password=getattr(settings, "EMAIL_HOST_PASSWORD", None),
        use_tls=getattr(settings, "EMAIL_USE_TLS", True),
        timeout=int(getattr(settings, "EMAIL_TIMEOUT", 10)),
    )
    # Actually open the connection so we can set debug level if needed
    conn.open()
    if SMTP_DEBUG and hasattr(conn, "connection") and conn.connection:
        try:
            conn.connection.set_debuglevel(1)  # prints raw SMTP exchange to stdout
        except Exception:
            pass
    return conn


def _safe_from_email():
    """
    Gmail requires the From to be your Gmail account (or a verified alias).
    We default to EMAIL_HOST_USER if DEFAULT_FROM_EMAIL is not explicitly set.
    """
    return getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "EMAIL_HOST_USER", None)


def _mail_guard_preamble(purpose=""):
    # Quick visibility in logs
    print(f"[email] purpose={purpose} DISABLE_EMAILS={getattr(settings, 'DISABLE_EMAILS', False)} "
          f"FROM={_safe_from_email()} HOST_USER={getattr(settings, 'EMAIL_HOST_USER', None)} "
          f"HOST={getattr(settings, 'EMAIL_HOST', None)} PORT={getattr(settings, 'EMAIL_PORT', None)} "
          f"TLS={getattr(settings, 'EMAIL_USE_TLS', None)} TIMEOUT={getattr(settings, 'EMAIL_TIMEOUT', None)}")


def send_new_task_notification(task):
    """
    Send email notification to the fixed list when a new task is created.
    """
    _mail_guard_preamble("new_task")

    if getattr(settings, "DISABLE_EMAILS", False):
        print("[email] skipped: DISABLE_EMAILS=1")
        return

    recipients = [e for e in RECIPIENTS_NEW_TASK if e]
    if not recipients:
        print("[email] skipped: no recipients configured")
        return

    subject = f"NEW TASK • {task.title} • {task.task_id or f'TSK{task.id:04d}'}"

    context = {
        "task_title": task.title,
        "task_subject": getattr(task, "subject", "") or "Not specified",
        "education_level": getattr(task, "education_level", "") or "Not specified",
        "deadline": task.deadline.strftime("%B %d, %Y at %I:%M %p") if getattr(task, "deadline", None) else "Not set",
        "proposed_budget": f"${getattr(task, 'proposed_budget', 0)}",
        "student_name": task.client.get_full_name() or task.client.username,
        "student_email": task.client.email,
        "task_id": task.task_id or f"TSK{task.id:04d}",
        "task_url": f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')}/admin/dashboard",
    }

    html_message = render_to_string("emails/new_task_notification.html", context)
    plain_message = strip_tags(html_message)

    from_email = _safe_from_email()
    if not from_email:
        print("[email] aborted: DEFAULT_FROM_EMAIL/EMAIL_HOST_USER not configured")
        return

    email = EmailMultiAlternatives(
        subject=subject,
        body=plain_message,
        from_email=from_email,
        to=recipients,
        reply_to=[from_email],
        headers={"X-AcademiQa": "new-task"},
    )
    email.attach_alternative(html_message, "text/html")

    try:
        conn = _open_smtp_connection()
        sent = email.send(fail_silently=False)  # raise on error
        conn.close()
        print(f"[email] new_task sent={sent} to={recipients}")
    except socket.gaierror as e:
        print(f"[email] DNS/Network error: {e} (cannot resolve or reach SMTP host)")
    except Exception as e:
        print(f"[email] FAILED to send new task email: {e}")


def send_task_status_update(task, student, update_message):
    _mail_guard_preamble("status_update")
    if getattr(settings, "DISABLE_EMAILS", False):
        print("[email] skipped: DISABLE_EMAILS=1")
        return

    subject = f"Task Update: {task.title}"
    context = {
        "student_name": student.get_full_name() or student.username,
        "task_title": task.title,
        "task_status": task.get_status_display() if hasattr(task, "get_status_display") else getattr(task, "status", ""),
        "update_message": update_message,
        "admin_name": task.assigned_admin.get_full_name() if getattr(task, "assigned_admin", None) else None,
        "task_url": f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')}/client/dashboard/tasks/{task.id}",
    }

    html_message = render_to_string("emails/task_status_update.html", context)
    plain_message = strip_tags(html_message)
    from_email = _safe_from_email()
    email = EmailMultiAlternatives(
        subject=subject,
        body=plain_message,
        from_email=from_email,
        to=[student.email],
        reply_to=[from_email],
        headers={"X-AcademiQa": "status-update"},
    )
    email.attach_alternative(html_message, "text/html")
    try:
        conn = _open_smtp_connection()
        sent = email.send(fail_silently=False)
        conn.close()
        print(f"[email] status_update sent={sent} to={[student.email]}")
    except Exception as e:
        print(f"[email] FAILED status update email: {e}")


def send_new_message_notification(task, message, recipient):
    _mail_guard_preamble("chat_notify")
    if getattr(settings, "DISABLE_EMAILS", False):
        print("[email] skipped: DISABLE_EMAILS=1")
        return

    subject = f"New Message - Task: {task.title}"
    preview = (message.message[:100] + "...") if getattr(message, "message", "") and len(message.message) > 100 else getattr(message, "message", "")

    context = {
        "task_title": task.title,
        "sender_name": message.sender.get_full_name() or message.sender.username,
        "message_preview": preview,
        "task_url": f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')}/client/dashboard/tasks/{task.id}",
    }

    html_message = render_to_string("emails/new_message_notification.html", context)
    plain_message = strip_tags(html_message)
    from_email = _safe_from_email()
    email = EmailMultiAlternatives(
        subject=subject,
        body=plain_message,
        from_email=from_email,
        to=[recipient.email],
        reply_to=[from_email],
        headers={"X-AcademiQa": "chat-notify"},
    )
    email.attach_alternative(html_message, "text/html")
    try:
        conn = _open_smtp_connection()
        sent = email.send(fail_silently=False)
        conn.close()
        print(f"[email] chat_notify sent={sent} to={[recipient.email]}")
    except Exception as e:
        print(f"[email] FAILED chat notification email: {e}")
