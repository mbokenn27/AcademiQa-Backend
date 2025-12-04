# core/email_service.py

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings


def send_new_task_notification(task):
    """Send email notification to ALL admins + extra Gmail addresses when a new task is created"""
    from .models import UserProfile
    
    # 1. Get all active admin users from database
    admin_profiles = UserProfile.objects.filter(role='admin', user__is_active=True)
    admin_emails = [profile.user.email for profile in admin_profiles if profile.user.email]

    # 2. Your personal/extra Gmail addresses (edit anytime)
    EXTRA_ADMIN_EMAILS = [
        #"mbokenn27@gmail.com",
        "mbokenn95@gmail.com",
        #"odugucalvince@gmail.com",
        #"Briansimiyu13@gmail.com",
    ]

    # Combine and remove duplicates
    recipient_emails = list(set(admin_emails + EXTRA_ADMIN_EMAILS))

    if not recipient_emails:
        return  # Nothing to send

    subject = f"NEW TASK • {task.title} • {task.task_id or f'TSK{task.id:04d}'}"

    context = {
        'task_title': task.title,
        'task_subject': task.subject or "Not specified",                    # ← FIXED
        'education_level': task.education_level or "Not specified",
        'deadline': task.deadline.strftime('%B %d, %Y at %I:%M %p') if task.deadline else "Not set",
        'proposed_budget': f"${task.proposed_budget}",
        'student_name': task.client.get_full_name() or task.client.username,
        'student_email': task.client.email,
        'task_id': task.task_id or f"TSK{task.id:04d}",
        'task_url': f"{settings.FRONTEND_URL}/admin/dashboard",             # ← THIS LINE IS HERE
    }
    
    html_message = render_to_string('emails/new_task_notification.html', context)
    plain_message = strip_tags(html_message)

    email = EmailMultiAlternatives(
        subject=subject,
        body=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipient_emails,
    )
    email.attach_alternative(html_message, "text/html")
    
    try:
        email.send()
        print(f"New task email sent successfully to: {recipient_emails}")
    except Exception as e:
        print(f"Failed to send new task email: {e}")

# === ADD THESE 3 FUNCTIONS TO core/email_service.py ===

def send_task_status_update(task, student, update_message):
    """Send email to student when task status is updated"""
    subject = f"Task Update: {task.title}"
    
    context = {
        'student_name': student.get_full_name() or student.username,
        'task_title': task.title,
        'task_status': task.get_status_display(),
        'update_message': update_message,
        'admin_name': task.assigned_admin.get_full_name() if task.assigned_admin else None,
        'task_url': f"{settings.FRONTEND_URL}/client/dashboard/tasks/{task.id}"
    }
    
    html_message = render_to_string('emails/task_status_update.html', context)
    plain_message = strip_tags(html_message)
    
    email = EmailMultiAlternatives(
        subject=subject,
        body=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[student.email]
    )
    email.attach_alternative(html_message, "text/html")
    email.send()


def send_new_message_notification(task, message, recipient):
    """Send email notification for new chat messages"""
    subject = f"New Message - Task: {task.title}"
    
    context = {
        'task_title': task.title,
        'sender_name': message.sender.get_full_name() or message.sender.username,
        'message_preview': message.message[:100] + '...' if len(message.message) > 100 else message.message,
        'task_url': f"{settings.FRONTEND_URL}/client/dashboard/tasks/{task.id}"
    }
    
    html_message = render_to_string('emails/new_message_notification.html', context)
    plain_message = strip_tags(html_message)
    
    email = EmailMultiAlternatives(
        subject=subject,
        body=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient.email]
    )
    email.attach_alternative(html_message, "text/html")
    email.send()