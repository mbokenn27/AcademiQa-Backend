# core/views.py
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes  # ADD THIS IMPORT
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone
from .email_service import send_new_task_notification
from rest_framework.views import APIView
from .models import TaskCategory, Task, ChatMessage, Notification, UserProfile, TaskFile, Revision, BudgetProposal
from .serializers import (
    UserSerializer, TaskSerializer, ChatMessageSerializer,
    NotificationSerializer, TaskCategorySerializer,
    UserRegistrationSerializer, CustomTokenObtainPairSerializer,
    TaskFileSerializer, RevisionSerializer, BudgetProposalSerializer
)
from .tasks import notify_task_status_update, create_notification

class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            hasattr(request.user, "profile") and
            request.user.profile.role == "admin"
        )

class AuthenticatedAPIView(generics.GenericAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

class BroadcastMixin:
    def _broadcast_task_update(self, request, task):
        channel_layer = get_channel_layer()
        if channel_layer:
            task_data = TaskSerializer(task, context={'request': request}).data
            # Broadcast to task-specific room
            async_to_sync(channel_layer.group_send)(
                f"task_{task.id}",
                {"type": "task_updated", "task": task_data}
            )
            # Broadcast to admin dashboard
            async_to_sync(channel_layer.group_send)(
                "admin_dashboard",
                {"type": "task_updated", "task": task_data}
            )

# Auth Views
class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

class RegisterView(generics.CreateAPIView):
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]

class CurrentUserView(AuthenticatedAPIView):
    def get(self, request):
        profile = request.user.profile if hasattr(request.user, 'profile') else None
        return Response({
            "id": request.user.id,
            "username": request.user.username,
            "email": request.user.email,
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "role": profile.role if profile else "client",
            "phone": profile.phone if profile else None,
            "education_level": profile.education_level if profile else None,
            "avatar": profile.avatar if profile else None,
            "expertise": profile.expertise if profile else None,
            "rating": float(profile.rating) if profile and profile.rating else None,
            "completed_tasks": profile.completed_tasks if profile else 0,
            "earnings": float(profile.earnings) if profile and profile.earnings else 0,
            "is_verified": profile.is_verified if profile else False,
        })

# Task Categories
class TaskCategoryListCreate(AuthenticatedAPIView, generics.ListCreateAPIView):
    queryset = TaskCategory.objects.all()
    serializer_class = TaskCategorySerializer
    permission_classes = [IsAuthenticated, IsAdmin]

class TaskCategoryDetail(AuthenticatedAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = TaskCategory.objects.all()
    serializer_class = TaskCategorySerializer
    permission_classes = [IsAuthenticated, IsAdmin]

# Tasks - Unified Client & Admin
class TaskListCreate(AuthenticatedAPIView, generics.ListCreateAPIView, BroadcastMixin):
    serializer_class = TaskSerializer
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_queryset(self):
        profile = getattr(self.request.user, "profile", None)
        role = getattr(profile, "role", "client") if profile else "client"
        
        if role == "admin":
            return Task.objects.all().select_related(
                'client', 'assigned_admin', 'category', 'timezone'
            ).prefetch_related('files', 'revisions', 'messages').order_by('-created_at')
        
        return Task.objects.filter(client=self.request.user).select_related(
            'client', 'assigned_admin', 'category', 'timezone'
        ).prefetch_related('files', 'revisions', 'messages').order_by('-created_at')

    def perform_create(self, serializer):
        task = serializer.save(client=self.request.user)

        #send notification to admins
        send_new_task_notification(task)
        
        # Broadcast to admin dashboard
        channel_layer = get_channel_layer()
        if channel_layer:
            task_data = TaskSerializer(task, context={'request': self.request}).data
            async_to_sync(channel_layer.group_send)(
                "admin_dashboard",
                {"type": "task_created", "task": task_data}
            )

class TaskDetail(AuthenticatedAPIView, generics.RetrieveUpdateDestroyAPIView, BroadcastMixin):
    serializer_class = TaskSerializer

    def get_queryset(self):
        profile = getattr(self.request.user, "profile", None)
        role = getattr(profile, "role", "client") if profile else "client"
        if role == "admin":
            return Task.objects.all().select_related(
                'client', 'assigned_admin', 'category', 'timezone'
            ).prefetch_related('files', 'revisions', 'messages')
        return Task.objects.filter(client=self.request.user).select_related(
            'client', 'assigned_admin', 'category', 'timezone'
        ).prefetch_related('files', 'revisions', 'messages')

    def perform_update(self, serializer):
        task = serializer.save()
        self._broadcast_task_update(self.request, task)

# ============================================================================
# CLIENT BUDGET NEGOTIATION ENDPOINTS - ADD THESE
# ============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def client_accept_budget(request, pk):
    """
    Client accepts the admin's counter budget offer
    """
    try:
        task = get_object_or_404(Task, pk=pk, client=request.user)
        
        if not task.admin_counter_budget:
            return Response({'error': 'No counter budget available to accept'}, status=400)
        
        if task.status not in ['submitted', 'budget_negotiation']:
            return Response({'error': 'Cannot accept budget in current task status'}, status=400)
        
        # Accept the admin's counter offer
        task.budget = task.admin_counter_budget
        task.negotiation_status = 'accepted'
        task.status = 'in_progress'
        task.save()
        
        # BROADCAST TO ADMIN DASHBOARD — THIS WAS MISSING!
        channel_layer = get_channel_layer()
        if channel_layer:
            task_data = TaskSerializer(task, context={'request': request}).data
            async_to_sync(channel_layer.group_send)(
                "admin_dashboard",
                {"type": "task_updated", "task": task_data}
            )

        # Notify admin
        if task.assigned_admin:
            create_notification.delay(
                task.assigned_admin.id,
                "Budget Accepted",
                f"Client accepted your budget proposal of ${task.budget} for task '{task.title}'",
                task.id,
                'budget_accepted'
            )
        
        return Response({
            'status': 'success',
            'message': 'Budget accepted successfully',
            'task': {
                'id': task.id,
                'budget': task.budget,
                'negotiation_status': task.negotiation_status,
                'status': task.status
            }
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def client_counter_budget(request, pk):
    """
    Client sends a counter budget offer
    """
    try:
        task = get_object_or_404(Task, pk=pk, client=request.user)
        amount = request.data.get('amount')
        
        if not amount:
            return Response({'error': 'Amount is required'}, status=400)
        
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return Response({'error': 'Invalid amount format'}, status=400)
        
        if amount <= 0:
            return Response({'error': 'Amount must be greater than 0'}, status=400)
        
        if task.status not in ['submitted', 'budget_negotiation']:
            return Response({'error': 'Cannot counter budget in current task status'}, status=400)
        
        # Update with client's counter offer
        task.proposed_budget = amount
        task.negotiation_status = 'pending_admin_response'
        task.status = 'budget_negotiation'
        task.negotiation_reason = request.data.get('reason', '')
        task.save()

        # THIS IS THE MAGIC — now properly closed and consistent
        channel_layer = get_channel_layer()
        if channel_layer:
            task_data = TaskSerializer(task, context={'request': request}).data
            async_to_sync(channel_layer.group_send)(
                "admin_dashboard",
                {"type": "task_updated", "task": task_data}
            )

        # Notify admin
        if task.assigned_admin:
            create_notification.delay(
                task.assigned_admin.id,
                "Budget Counter-Offer Received",
                f"Client countered with ${amount} for task '{task.title}'",
                task.id,
                'budget_countered'
            )
        
        return Response({
            'status': 'success',
            'message': 'Counter offer sent successfully',
            'task': {
                'id': task.id,
                'proposed_budget': task.proposed_budget,
                'negotiation_status': task.negotiation_status,
                'status': task.status
            }
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def client_reject_budget(request, pk):
    """
    Client rejects the budget negotiation
    """
    try:
        task = get_object_or_404(Task, pk=pk, client=request.user)
        
        if task.status not in ['submitted', 'budget_negotiation']:
            return Response({'error': 'Cannot reject budget in current task status'}, status=400)
        
        # Reject the budget negotiation
        task.negotiation_status = 'rejected'
        task.status = 'budget_rejected'
        task.save()
        
        # Notify admin
        if task.assigned_admin:
            create_notification.delay(
                task.assigned_admin.id,
                "Budget Rejected",
                f"Client rejected the budget negotiation for task '{task.title}'",
                task.id,
                'budget_rejected'
            )
        
        return Response({
            'status': 'success',
            'message': 'Budget negotiation rejected',
            'task': {
                'id': task.id,
                'negotiation_status': task.negotiation_status,
                'status': task.status
            }
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=500)

def can_withdraw_task(task):
    """Check if task can be withdrawn based on your business rules"""
    withdrawable_statuses = ['submitted', 'budget_negotiation']
    if task.status in withdrawable_statuses:
        return True
    if task.status == 'in_progress' and task.withdrawal_deadline:
        return timezone.now() < task.withdrawal_deadline
    return False

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def client_withdraw_task(request, pk):
    """
    Client withdraws a task
    """
    try:
        task = get_object_or_404(Task, pk=pk, client=request.user)
        reason = request.data.get('reason', '')
        
        # Check if task can be withdrawn
        if not can_withdraw_task(task):
            return Response({'error': 'This task cannot be withdrawn'}, status=400)
        
        # Withdraw the task
        task.status = 'withdrawn'
        task.withdrawal_reason = reason
        task.save()
        
        # Notify admin
        if task.assigned_admin:
            create_notification.delay(
                task.assigned_admin.id,
                "Task Withdrawn",
                f"Client withdrew task '{task.title}'. Reason: {reason}",
                task.id,
                'task_withdrawn'
            )
        
        return Response({
            'status': 'success',
            'message': 'Task withdrawn successfully',
            'task': {
                'id': task.id,
                'status': task.status,
                'withdrawal_reason': task.withdrawal_reason
            }
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=500)

# Add these functions with the other client actions (around line 250)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def client_approve_task(request, pk):
    """Client approves and completes the task"""
    try:
        task = get_object_or_404(Task, pk=pk, client=request.user)
        
        if task.status != "awaiting_review":
            return Response({"error": "Can only approve tasks that are awaiting review"}, status=400)
        
        # Approve the task
        task.status = "completed"
        task.completed_at = timezone.now()
        task.save()
        
        # Update admin stats
        if task.assigned_admin and task.budget:
            admin_profile = task.assigned_admin.profile
            admin_profile.completed_tasks += 1
            admin_profile.earnings += task.budget
            admin_profile.save()
        
        # Notify admin
        if task.assigned_admin:
            create_notification.delay(
                task.assigned_admin.id,
                "Task Approved",
                f"Client approved and completed task '{task.title}'",
                task.id,
                'task_approved'
            )
        
        # Broadcast update
        channel_layer = get_channel_layer()
        if channel_layer:
            task_data = TaskSerializer(task, context={'request': request}).data
            async_to_sync(channel_layer.group_send)(
                f"task_{task.id}",
                {"type": "task_updated", "task": task_data}
            )
            async_to_sync(channel_layer.group_send)(
                "admin_dashboard",
                {"type": "task_updated", "task": task_data}
            )
        
        return Response({
            'status': 'success',
            'message': 'Task approved successfully',
            'task': {
                'id': task.id,
                'status': task.status,
                'completed_at': task.completed_at
            }
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def client_request_revision(request, pk):
    """Client requests revision for the task"""
    try:
        task = get_object_or_404(Task, pk=pk, client=request.user)
        feedback = request.data.get("feedback", "").strip()
        
        if not feedback:
            return Response({"error": "Feedback is required"}, status=400)
        
        if task.status != "awaiting_review":
            return Response({"error": "Can only request revision for tasks awaiting review"}, status=400)
        
        # Request revision
        task.status = "revision_requested"
        task.save()
        
        # Create revision record
        revision = Revision.objects.create(
            task=task,
            feedback=feedback,
            requested_by=request.user
        )
        
        # Notify admin
        if task.assigned_admin:
            create_notification.delay(
                task.assigned_admin.id,
                "Revision Requested",
                f"Client requested revision for task '{task.title}'. Feedback: {feedback}",
                task.id,
                'revision_requested'
            )
        
        # Broadcast update
        channel_layer = get_channel_layer()
        if channel_layer:
            task_data = TaskSerializer(task, context={'request': request}).data
            async_to_sync(channel_layer.group_send)(
                f"task_{task.id}",
                {"type": "task_updated", "task": task_data}
            )
            async_to_sync(channel_layer.group_send)(
                "admin_dashboard",
                {"type": "task_updated", "task": task_data}
            )
        
        return Response({
            'status': 'success',
            'message': 'Revision requested successfully',
            'task': {
                'id': task.id,
                'status': task.status
            },
            'revision': RevisionSerializer(revision).data
        })
        
    except Exception as e:
        return Response({'error': str(e)}, status=500)

# ============================================================================
# ADMIN TASK ACTIONS (EXISTING CODE CONTINUES BELOW)
# ============================================================================

@method_decorator(csrf_exempt, name='dispatch')
class AdminAcceptTask(AuthenticatedAPIView, BroadcastMixin):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk)
        
        if task.status not in ['submitted', 'rejected']:
            return Response(
                {"error": f"Cannot accept task in '{task.status}' status."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        task.status = "in_progress"
        task.assigned_admin = request.user
        task.accepted_at = timezone.now()
        task.progress = 5
        task.save()

        # Notify student
        notify_task_status_update.delay(
            task.id, 
            f"Your task '{task.title}' has been accepted by {request.user.get_full_name() or request.user.username} and work has begun."
        )

        self._broadcast_task_update(request, task)
        serializer = TaskSerializer(task, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

@method_decorator(csrf_exempt, name='dispatch')
class AdminProposeBudget(AuthenticatedAPIView, BroadcastMixin):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk)
        amount = request.data.get('amount')
        reason = request.data.get('reason', '')
        
        if not amount:
            return Response({"error": "Amount is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Create budget proposal
        proposal = BudgetProposal.objects.create(
            task=task,
            amount=amount,
            description=reason,
            proposed_by=request.user
        )

        # Update task negotiation status
        task.admin_counter_budget = amount
        task.negotiation_status = 'pending_student_response'
        task.negotiation_reason = reason
        task.status = 'budget_negotiation'
        task.assigned_admin = request.user  # Temporarily assign during negotiation
        task.save()

        # Notify student
        create_notification.delay(
            task.client.id,
            "Budget Counter-Offer Received",
            f"Expert has proposed a counter-offer of ${amount} for your task '{task.title}'",
            task.id,
            'budget_proposed'
        )

        self._broadcast_task_update(request, task)
        return Response({
            "detail": "Budget proposal sent successfully",
            "task": TaskSerializer(task, context={'request': request}).data,
            "proposal": BudgetProposalSerializer(proposal).data
        })

# core/views.py

@method_decorator(csrf_exempt, name='dispatch')
class AdminAcceptBudget(AuthenticatedAPIView, BroadcastMixin):
    """
    Admin accepts the student's budget (original or counter) and starts work
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk)

        # Only allow from submitted / negotiation states
        if task.status not in ['submitted', 'budget_negotiation']:
            return Response(
                {"error": "Cannot accept budget in current task status."},
                status=400
            )

        # Decide which amount we're actually accepting.
        # Priority: student's latest offer (proposed_budget).
        accepted_amount = None
        # Decide which amount we're actually accepting.
        # 500 → 900 → 700 case:
        # - after student counters with 700: proposed_budget = 700, negotiation_status = 'pending_admin_response'
        # - we MUST use proposed_budget (700), not admin_counter_budget (900)
        accepted_amount = None

        if task.negotiation_status == 'pending_admin_response' and task.proposed_budget:
            # Student has just countered (e.g. 700) → admin now accepts that
            accepted_amount = task.proposed_budget
        elif task.admin_counter_budget:
            # Student is accepting admin's counter (e.g. 900) or admin is accepting an earlier admin offer
            accepted_amount = task.admin_counter_budget
        elif task.proposed_budget:
            # No negotiation yet: admin accepting student's original proposed budget (e.g. 500)
            accepted_amount = task.proposed_budget

        if not accepted_amount:
            return Response(
                {"error": "No budget available to accept."},
                status=400
            )


        # Persist acceptance
        task.budget = accepted_amount
        task.negotiation_status = 'accepted'
        task.status = 'in_progress'
        task.assigned_admin = request.user
        task.accepted_at = timezone.now()
        task.progress = 5
        task.save()

        # Notify client via email/notification
        notify_task_status_update.delay(
            task.id,
            f"Expert has accepted your budget of ${accepted_amount} and started working on your task."
        )

        # Broadcast to WebSocket listeners (admin dashboard + task room)
        self._broadcast_task_update(request, task)

        serializer = TaskSerializer(task, context={'request': request})
        return Response(serializer.data)


@method_decorator(csrf_exempt, name='dispatch')
class AdminUpdateProgress(AuthenticatedAPIView, BroadcastMixin):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk)
        
        if task.assigned_admin != request.user:
            return Response({"error": "You are not assigned to this task"}, status=status.HTTP_403_FORBIDDEN)

        progress = request.data.get('progress')
        message = request.data.get('message', '')
        
        if progress is not None:
            task.progress = max(0, min(100, int(progress)))
            task.save()

        if message:
            # Create progress update message
            ChatMessage.objects.create(
                task=task,
                sender=request.user,
                message=f"Progress Update: {message} (Progress: {task.progress}%)"
            )

        self._broadcast_task_update(request, task)
        serializer = TaskSerializer(task, context={'request': request})
        return Response(serializer.data)

@method_decorator(csrf_exempt, name='dispatch')
class AdminSubmitForReview(AuthenticatedAPIView, BroadcastMixin):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk)
        
        if task.assigned_admin != request.user:
            return Response({"error": "You are not assigned to this task"}, status=status.HTTP_403_FORBIDDEN)

        task.status = 'awaiting_review'
        task.progress = 100
        task.save()

        # Notify student
        notify_task_status_update.delay(
            task.id,
            f"Your task '{task.title}' is ready for review. Please check the submitted work."
        )

        self._broadcast_task_update(request, task)
        serializer = TaskSerializer(task, context={'request': request})
        return Response(serializer.data)

@method_decorator(csrf_exempt, name='dispatch')
class AdminMarkComplete(AuthenticatedAPIView, BroadcastMixin):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk)
        
        if task.assigned_admin != request.user:
            return Response({"error": "You are not assigned to this task"}, status=status.HTTP_403_FORBIDDEN)

        task.status = 'completed'
        task.progress = 100
        task.completed_at = timezone.now()
        task.save()

        # Update admin stats
        admin_profile = request.user.profile
        admin_profile.completed_tasks += 1
        if task.budget:
            admin_profile.earnings += task.budget
        admin_profile.save()

        # Notify student
        notify_task_status_update.delay(
            task.id,
            f"Your task '{task.title}' has been completed successfully."
        )

        self._broadcast_task_update(request, task)
        serializer = TaskSerializer(task, context={'request': request})
        return Response(serializer.data)

@method_decorator(csrf_exempt, name='dispatch')
class AdminRejectTask(AuthenticatedAPIView, BroadcastMixin):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk)
        reason = request.data.get("reason", "").strip()
        
        if not reason:
            return Response({"error": "Reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        task.status = "rejected"
        task.reject_reason = reason
        task.rejected_at = timezone.now()
        task.assigned_admin = None  # Unassign admin
        task.save()

        # Notify student
        notify_task_status_update.delay(
            task.id,
            f"Your task '{task.title}' has been rejected. Reason: {reason}"
        )

        self._broadcast_task_update(request, task)
        serializer = TaskSerializer(task, context={'request': request})
        return Response(serializer.data)

# File Upload
@method_decorator(csrf_exempt, name='dispatch')
class AdminUploadSolution(AuthenticatedAPIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        # 1. Get task
        task = get_object_or_404(Task, pk=pk)

        # 2. Get file
        file = request.FILES.get("solution") or request.FILES.get("file")
        if not file:
            return Response({"error": "No file provided"}, status=400)

        # 3. Save file
        TaskFile.objects.create(
            task=task,
            file=file,
            name=file.name,
            file_type=self.get_file_type(file.name),
            size=f"{file.size / 1024 / 1024:.2f} MB",
            uploaded_by=request.user
        )

        # 4. FORCE STATUS CHANGE
        if task.status in ['in_progress', 'revision_requested']:
            task.status = 'awaiting_review'
            task.progress = 100
            task.save(update_fields=['status', 'progress'])

        # 5. RE-READ TASK FROM DATABASE — this is the nuclear option
        from django.db import connection
        task = Task.objects.select_related('client', 'assigned_admin', 'category', 'timezone')\
                          .prefetch_related('files', 'revisions', 'messages')\
                          .get(pk=task.pk)

        # 6. Serialize FRESH data
        task_data = TaskSerializer(task, context={'request': request}).data

        # 7. Broadcast to BOTH places — manually, no mixin
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"task_{task.id}",
                {"type": "task_updated", "task": task_data}
            )
            async_to_sync(channel_layer.group_send)(
                "admin_dashboard",
                {"type": "task_updated", "task": task_data}
            )

        # 8. Return fresh data
        return Response({
            "detail": "Solution uploaded — awaiting student approval",
            "task": task_data
        }, status=200)

    def get_file_type(self, filename):
        ext = filename.split('.')[-1].lower()
        return {
            'pdf': 'pdf', 'doc': 'word', 'docx': 'word',
            'xls': 'excel', 'xlsx': 'excel',
            'jpg': 'image', 'jpeg': 'image', 'png': 'image', 'gif': 'image',
        }.get(ext, 'other')

# Chat
class ChatMessageListCreate(AuthenticatedAPIView, generics.ListCreateAPIView):
    serializer_class = ChatMessageSerializer

    def get_queryset(self):
        return ChatMessage.objects.filter(task_id=self.kwargs['task_id']).select_related('sender')

    def perform_create(self, serializer):
        task = get_object_or_404(Task, pk=self.kwargs['task_id'])
        message = serializer.save(task=task, sender=self.request.user)

        # Broadcast message via WebSocket
        channel_layer = get_channel_layer()
        if channel_layer:
            msg_data = ChatMessageSerializer(message, context={'request': self.request}).data
            async_to_sync(channel_layer.group_send)(
                f"task_{task.id}",
                {"type": "chat_message", "message": msg_data}
            )

# Notifications
class NotificationList(AuthenticatedAPIView, generics.ListAPIView):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).select_related('task').order_by('-created_at')

class MarkNotificationRead(AuthenticatedAPIView):
    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, user=request.user)
        notification.is_read = True
        notification.save()
        return Response({"detail": "Notification marked as read"})

# Admin Stats
class AdminStatsView(AuthenticatedAPIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        from django.db.models import Count, Sum, Q
        from django.utils import timezone
        from datetime import timedelta

        # Task statistics
        total_tasks = Task.objects.count()
        new_requests = Task.objects.filter(status='submitted').count()
        active_tasks = Task.objects.filter(status='in_progress').count()
        under_review = Task.objects.filter(status='awaiting_review').count()
        completed_tasks = Task.objects.filter(status='completed').count()

        # Recent tasks (last 7 days)
        week_ago = timezone.now() - timedelta(days=7)
        recent_tasks = Task.objects.filter(created_at__gte=week_ago).count()

        # Admin performance
        admin_tasks = Task.objects.filter(assigned_admin=request.user)
        admin_completed = admin_tasks.filter(status='completed').count()
        admin_earnings = admin_tasks.filter(status='completed').aggregate(
            total_earnings=Sum('budget')
        )['total_earnings'] or 0

        return Response({
            "task_stats": {
                "total": total_tasks,
                "new_requests": new_requests,
                "active": active_tasks,
                "under_review": under_review,
                "completed": completed_tasks,
                "recent": recent_tasks,
            },
            "admin_stats": {
                "assigned_tasks": admin_tasks.count(),
                "completed_tasks": admin_completed,
                "total_earnings": float(admin_earnings),
                "rating": float(request.user.profile.rating) if request.user.profile.rating else 5.0,
            }
        })
