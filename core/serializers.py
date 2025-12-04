from rest_framework import serializers
from django.contrib.auth.models import User
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.utils import timezone
import pytz

from .models import (
    UserProfile, TaskCategory, Task, ChatMessage,
    Notification, Timezone, TaskFile, Revision, BudgetProposal
)

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['role'] = getattr(user, 'profile.role', 'client') if hasattr(user, 'profile') else 'client'
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        
        # Keep basic fields
        data['username'] = self.user.username
        data['role'] = getattr(self.user.profile, 'role', 'client')

        #Add full user object so frontend receives the user details immediately
        data['user'] = UserSerializer(self.user).data

        return data


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'first_name', 'last_name']

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
        )
        UserProfile.objects.get_or_create(user=user, defaults={'role': 'client'})
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = UserProfile
        fields = ['role', 'phone', 'education_level', 'is_suspended', 'avatar', 
                 'expertise', 'rating', 'completed_tasks', 'earnings', 'is_verified', 'full_name']
    
    def get_full_name(self, obj):
        return obj.user.get_full_name()


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'profile', 'full_name']
    
    def get_full_name(self, obj):
        return obj.get_full_name()


class TaskCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskCategory
        fields = ['id', 'name', 'description']


class TimezoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Timezone
        fields = ['zone', 'city', 'country', 'flag', 'offset']


class TaskFileSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source='uploaded_by.get_full_name', read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = TaskFile
        fields = ['id', 'name', 'file_type', 'size', 'uploaded_by', 'uploaded_by_name', 
                 'uploaded_at', 'description', 'file_url']

    def get_file_url(self, obj):
        if obj.file and hasattr(obj.file, 'url'):
            request = self.context.get('request')
            return request.build_absolute_uri(obj.file.url) if request else obj.file.url
        return None


class RevisionSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.CharField(source='requested_by.get_full_name', read_only=True)

    class Meta:
        model = Revision
        fields = ['id', 'requested_by', 'requested_by_name', 'requested_at', 'feedback', 
                 'status', 'completed_at', 'admin_notes']


class BudgetProposalSerializer(serializers.ModelSerializer):
    proposed_by_name = serializers.CharField(source='proposed_by.get_full_name', read_only=True)

    class Meta:
        model = BudgetProposal
        fields = ['id', 'task', 'amount', 'description', 'proposed_by', 'proposed_by_name', 
                 'created_at', 'is_approved']
        read_only_fields = ['id', 'created_at']


# serializers.py
from rest_framework import serializers
from .models import ChatMessage

class ChatMessageSerializer(serializers.ModelSerializer):
    sender_role = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()   # ← NOT a model field
    file_name = serializers.CharField(read_only=True)  # ← We set this manually in consumer

    sender = serializers.ReadOnlyField(source='sender.username')

    class Meta:
        model = ChatMessage
        fields = [
            'id', 'message', 'file', 'file_name', 'file_url',
            'is_read', 'created_at', 'sender', 'sender_role'
        ]
        read_only_fields = ['sender', 'sender_role', 'file_url', 'created_at', 'is_read', 'file_name']

    def get_sender_role(self, obj):
        return getattr(obj.sender.profile, 'role', 'client') if hasattr(obj.sender, 'profile') else 'client'

    def get_file_url(self, obj):
        if obj.file and hasattr(obj.file, 'url'):
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class TaskSerializer(serializers.ModelSerializer):
    client = UserSerializer(read_only=True)
    assigned_admin = UserSerializer(read_only=True, allow_null=True)
    category = TaskCategorySerializer(read_only=True)
    timezone_obj = TimezoneSerializer(source='timezone', read_only=True)
    files = TaskFileSerializer(many=True, read_only=True)
    revisions = RevisionSerializer(many=True, read_only=True)
    chat = ChatMessageSerializer(source='messages', many=True, read_only=True)

    category_id = serializers.PrimaryKeyRelatedField(
        queryset=TaskCategory.objects.all(), source='category', write_only=True, required=False, allow_null=True
    )
    assigned_admin_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(profile__role='admin'), source='assigned_admin',
        write_only=True, required=False, allow_null=True
    )
    timezone_str = serializers.CharField(write_only=True, required=False, allow_blank=True)

    file_url = serializers.SerializerMethodField()
    response_file_url = serializers.SerializerMethodField()
    revision_file_url = serializers.SerializerMethodField()

    unread_messages = serializers.SerializerMethodField()
    days_until_deadline = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            'id', 'task_id', 'client', 'category', 'category_id',
            'title', 'description', 'subject', 'education_level',
            'deadline', 'timezone_obj', 'timezone_str',
            'status', 'assigned_admin', 'assigned_admin_id',
            'priority', 'progress', 'budget', 'proposed_budget',
            'admin_counter_budget', 'negotiation_status', 'negotiation_reason',
            'estimated_hours', 'actual_hours',
            'file', 'file_url', 'response_file', 'response_file_url',
            'revision_note', 'revision_file', 'revision_file_url',
            'cancel_reason', 'reject_reason',
            'files', 'revisions', 'chat', 'unread_messages',
            'withdrawal_deadline', 'withdrawal_fee', 'can_withdraw_free',
            'accepted_at', 'completed_at', 'days_until_deadline', 'is_overdue',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['client', 'task_id', 'files', 'revisions', 'chat', 'unread_messages']

    def get_file_url(self, obj):
        if obj.file and hasattr(obj.file, 'url'):
            request = self.context.get('request')
            return request.build_absolute_uri(obj.file.url) if request else obj.file.url
        return None

    def get_response_file_url(self, obj):
        if obj.response_file and hasattr(obj.file, 'url'):
            request = self.context.get('request')
            return request.build_absolute_uri(obj.response_file.url) if request else obj.response_file.url
        return None

    def get_revision_file_url(self, obj):
        if obj.revision_file and hasattr(obj.revision_file, 'url'):
            request = self.context.get('request')
            return request.build_absolute_uri(obj.revision_file.url) if request else obj.revision_file.url
        return None

    def get_unread_messages(self, obj):
        request = self.context.get('request')
        if not request or not request.user:
            return 0
        user_role = getattr(request.user.profile, 'role', 'client') if hasattr(request.user, 'profile') else 'client'
        if user_role == 'client':
            return obj.messages.filter(is_read=False, sender__profile__role='admin').count()
        else:
            return obj.messages.filter(is_read=False, sender=obj.client).count()

    def get_days_until_deadline(self, obj):
        if obj.deadline:
            delta = obj.deadline - timezone.now()
            return max(0, delta.days)
        return None

    def get_is_overdue(self, obj):
        if obj.deadline and obj.status not in ['completed', 'cancelled', 'rejected']:
            return timezone.now() > obj.deadline
        return False

    def create(self, validated_data):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("User must be authenticated.")

        # Remove files from validated_data — we'll handle them separately
        uploaded_files = request.FILES.getlist('file')  # ← GET ALL FILES

        # Handle timezone
        timezone_str = validated_data.pop('timezone_str', None)
        if timezone_str:
            tz, _ = Timezone.objects.get_or_create(
                zone=timezone_str,
                defaults={
                    'city': timezone_str.split('/')[-1].replace('_', ' '),
                    'country': 'Auto',
                    'offset': 'GMT',
                    'flag': 'UN'
                }
            )
            validated_data['timezone'] = tz

        validated_data['client'] = request.user
        task = super().create(validated_data)

        # SAVE ALL UPLOADED FILES TO TaskFile MODEL
        for file in uploaded_files:
            TaskFile.objects.create(
                task=task,
                file=file,
                name=file.name,
                file_type=file.name.split('.')[-1].lower() if '.' in file.name else 'file',
                size=f"{file.size / 1024 / 1024:.1f} MB" if file.size else "Unknown",
                uploaded_by=request.user
            )

        return task

    def validate_deadline(self, value):
        if value < timezone.now():
            raise serializers.ValidationError("Deadline cannot be in the past.")
        return value


class NotificationSerializer(serializers.ModelSerializer):
    task = TaskSerializer(read_only=True)

    class Meta:
        model = Notification
        fields = ['id', 'title', 'message', 'is_read', 'created_at', 'task']
