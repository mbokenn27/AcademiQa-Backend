# core/models.py - FIXED VERSION
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

class UserProfile(models.Model):
    ROLE_CHOICES = (
        ('client', 'Client'),
        ('admin', 'Admin'),
    )
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='client')
    phone = models.CharField(max_length=20, blank=True, null=True)
    education_level = models.CharField(max_length=100, blank=True, null=True)
    is_suspended = models.BooleanField(default=False)
    avatar = models.URLField(blank=True, null=True)
    expertise = models.TextField(blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True,
                                validators=[MinValueValidator(0), MaxValueValidator(5)])
    completed_tasks = models.IntegerField(default=0)
    earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    @property
    def is_admin(self):
        return self.role == 'admin'

@receiver(post_save, sender='auth.User')
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)

@receiver(post_save, sender='auth.User')
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()

class Timezone(models.Model):
    zone = models.CharField(max_length=100, unique=True, db_index=True)
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    flag = models.CharField(max_length=10, default="UN")
    offset = models.CharField(max_length=10)

    class Meta:
        ordering = ['city']

    def __str__(self):
        return f"{self.city}, {self.country} ({self.offset})"

class TaskCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = "Task Categories"

    def __str__(self):
        return self.name

class Task(models.Model):
    STATUS_CHOICES = (
        ('submitted', 'Submitted'),
        ('budget_negotiation', 'Budget Negotiation'),
        ('in_progress', 'In Progress'),
        ('awaiting_review', 'Awaiting Review'),
        ('revision_requested', 'Revision Requested'),
        ('completed', 'Completed'),
        ('withdrawn', 'Withdrawn'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    )

    NEGOTIATION_STATUS_CHOICES = (
        ('none', 'None'),
        ('pending_admin_review', 'Pending Admin Review'),
        ('pending_student_response', 'Pending Student Response'),
        ('pending_admin_response', 'Pending Admin Response'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    )

    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    )

    # Core fields
    task_id = models.CharField(max_length=20, unique=True, blank=True, null=True, editable=False, db_index=True)
    client = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='tasks')
    category = models.ForeignKey(TaskCategory, on_delete=models.SET_NULL, null=True, blank=True)
    timezone = models.ForeignKey(Timezone, on_delete=models.SET_NULL, null=True, blank=True)
    timezone_str = models.CharField(max_length=100, blank=True, null=True)
    assigned_admin = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tasks')

    subject = models.CharField(max_length=100)
    title = models.CharField(max_length=200)
    description = models.TextField()
    education_level = models.CharField(max_length=50, blank=True)
    deadline = models.DateTimeField()

    # Status & Progress
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submitted', db_index=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    progress = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])

    # Budget & Negotiation
    budget = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    proposed_budget = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    admin_counter_budget = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    negotiation_status = models.CharField(
        max_length=30,
        choices=NEGOTIATION_STATUS_CHOICES,
        default='none'
    )
    negotiation_reason = models.TextField(blank=True)

    # Know who won the negotiation
    accepted_budget_source = models.CharField(
        max_length=10,
        choices=(('client', 'Client'), ('admin', 'Admin')),
        blank=True,
        null=True
    )

    # Time tracking
    estimated_hours = models.IntegerField(default=0)
    actual_hours = models.IntegerField(null=True, blank=True)

    # Files
    file = models.FileField(upload_to='client_uploads/%Y/%m/%d/', blank=True, null=True)
    response_file = models.FileField(upload_to='admin_responses/%Y/%m/%d/', blank=True, null=True)
    revision_file = models.FileField(upload_to='revisions/%Y/%m/%d/', blank=True, null=True)

    # Revision / Rejection
    revision_note = models.TextField(blank=True, null=True)
    cancel_reason = models.TextField(blank=True, null=True)
    reject_reason = models.TextField(blank=True, null=True)
    withdrawal_reason = models.TextField(blank=True, null=True)  # ADDED THIS FIELD

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)

    # Withdrawal
    withdrawal_deadline = models.DateTimeField(null=True, blank=True)
    withdrawal_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    can_withdraw_free = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.task_id or 'DRAFT'}: {self.title}"

    def save(self, *args, **kwargs):
        is_new = not self.pk

        if is_new:
            # First save to get an ID
            super().save(*args, **kwargs)
            self.task_id = f"TSK{self.id:04d}"
            self.withdrawal_deadline = timezone.now() + timezone.timedelta(hours=48)
            super().save(update_fields=['task_id', 'withdrawal_deadline'])
            return

        # Handle timezone string → object
        if self.timezone_str and not self.timezone:
            tz, _ = Timezone.objects.get_or_create(
                zone=self.timezone_str,
                defaults={
                    'city': self.timezone_str.split('/')[-1].replace('_', ' '),
                    'country': 'Auto',
                    'offset': 'GMT',
                }
            )
            self.timezone = tz

        # Auto-set timestamps
        if self.status == 'completed' and not self.completed_at:
            self.completed_at = timezone.now()
        if self.status == 'in_progress' and not self.accepted_at and self.assigned_admin:
            self.accepted_at = timezone.now()
        if self.status == 'rejected' and not self.rejected_at:
            self.rejected_at = timezone.now()

        # CRITICAL: Ensure budget is set when negotiation ends
        if self.negotiation_status == 'accepted' and self.budget is None:
            if self.accepted_budget_source == 'client' and self.proposed_budget:
                self.budget = self.proposed_budget
            elif self.accepted_budget_source == 'admin' and self.admin_counter_budget:
                self.budget = self.admin_counter_budget
            elif self.proposed_budget:
                self.budget = self.proposed_budget
            else:
                self.budget = self.admin_counter_budget or 0

        super().save(*args, **kwargs)

    def unread_messages_count(self, user):
        if user == self.client:
            return self.messages.filter(is_read=False, sender__profile__role='admin').count()
        else:
            return self.messages.filter(is_read=False, sender=self.client).count()

class TaskFile(models.Model):
    FILE_TYPE_CHOICES = (
        ('pdf', 'PDF'), ('word', 'Word Document'), ('excel', 'Excel'),
        ('powerpoint', 'PowerPoint'), ('image', 'Image'), ('python', 'Python File'),
        ('csv', 'CSV'), ('other', 'Other'),
    )
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to='task_files/%Y/%m/%d/')
    name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=20, choices=FILE_TYPE_CHOICES)
    size = models.CharField(max_length=20)
    uploaded_by = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['-uploaded_at']

class Revision(models.Model):
    STATUS_CHOICES = (
        ('requested', 'Requested'), ('in_progress', 'In Progress'),
        ('completed', 'Completed'), ('cancelled', 'Cancelled'),
    )
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='revisions')
    requested_by = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='requested_revisions')
    requested_at = models.DateTimeField(auto_now_add=True)
    feedback = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='requested')
    completed_at = models.DateTimeField(null=True, blank=True)
    admin_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-requested_at']

class ChatMessage(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='sent_messages')
    message = models.TextField(blank=True)
    file = models.FileField(upload_to='chat_files/%Y/%m/%d/', blank=True, null=True)
    file_name = models.CharField(max_length=255, blank=True, null=True)  # ADDED THIS FIELD
    file_url = models.URLField(blank=True, null=True)  # ADDED THIS FIELD
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['created_at']

    @property
    def sender_role(self):
        return 'Admin' if hasattr(self.sender, 'profile') and self.sender.profile.role == 'admin' else 'Client'

    @property
    def time_str(self):
        return self.created_at.strftime("%H:%M")

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save()

class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('task_created', 'New Task Created'), ('task_accepted', 'Task Accepted'),
        ('task_completed', 'Task Completed'), ('message_received', 'New Message'),
        ('budget_proposed', 'Budget Proposed'), ('revision_requested', 'Revision Requested'),
        ('deadline_approaching', 'Deadline Approaching'), ('system', 'System Notification'),
        ('budget_accepted', 'Budget Accepted'), ('budget_countered', 'Budget Countered'),
        ('budget_rejected', 'Budget Rejected'), ('task_withdrawn', 'Task Withdrawn'),
    )
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES, default='system')
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications')
    action_url = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['-created_at']

class BudgetProposal(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='budget_proposals')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    proposed_by = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_approved = models.BooleanField(default=False)
    is_rejected = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Budget Proposal for {self.task.title} - ${self.amount}"