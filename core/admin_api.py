# task_manager/core/admin_api.py

from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import Task, UserProfile, BudgetProposal
from .serializers import TaskSerializer, UserSerializer, BudgetProposalSerializer
from .views import IsAdmin  # Reuse your existing IsAdmin permission


# --------------------------------------------------------------------------- #
# ADMIN TASK MANAGEMENT (SAFE – DOES NOT TOUCH EXISTING ENDPOINTS)
# --------------------------------------------------------------------------- #
class AdminTaskViewSet(viewsets.ViewSet):
    """
    Completely isolated admin task endpoints.
    Uses IsAdmin + IsAuthenticated.
    Does not interfere with existing logic.
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    # GET /api/admin/tasks/
    def list(self, request):
        tasks = Task.objects.all().order_by('-created_at')
        return Response(TaskSerializer(tasks, many=True, context={'request': request}).data)

    # GET /api/admin/tasks/<id>/
    def retrieve(self, request, pk=None):
        task = get_object_or_404(Task, pk=pk)
        return Response(TaskSerializer(task, context={'request': request}).data)

    # POST /api/admin/tasks/<id>/accept_new/
    @action(detail=True, methods=['post'])
    def accept_new(self, request, pk=None):
        task = get_object_or_404(Task, pk=pk)
        task.status = "In Progress"  # NO CHANGE to your existing statuses
        task.assigned_admin = request.user
        task.save()
        return Response({"detail": "Task accepted", "task": TaskSerializer(task, context={'request': request}).data})

    # POST /api/admin/tasks/<id>/reject_new/
    @action(detail=True, methods=['post'])
    def reject_new(self, request, pk=None):
        task = get_object_or_404(Task, pk=pk)
        reason = request.data.get("reason", "")
        task.status = "Rejected"   # No change to your system
        task.reject_reason = reason
        task.save()
        return Response({"detail": "Task rejected", "task": TaskSerializer(task, context={'request': request}).data})

    # POST /api/admin/tasks/<id>/mark_complete_new/
    @action(detail=True, methods=['post'])
    def mark_complete_new(self, request, pk=None):
        task = get_object_or_404(Task, pk=pk)
        task.status = "Completed"
        task.save()
        return Response({"detail": "Task marked as completed", "task": TaskSerializer(task, context={'request': request}).data})

    # POST /api/admin/tasks/<id>/propose_budget_new/
    @action(detail=True, methods=['post'])
    def propose_budget_new(self, request, pk=None):
        task = get_object_or_404(Task, pk=pk)
        data = {
            "task": task.id,
            "amount": request.data.get("amount"),
            "message": request.data.get("message", "")
        }
        serializer = BudgetProposalSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        proposal = serializer.save(proposer=request.user)
        return Response({
            "detail": "Budget proposal sent",
            "proposal": BudgetProposalSerializer(proposal).data
        }, status=status.HTTP_201_CREATED)
        

# --------------------------------------------------------------------------- #
# ADMIN USER MANAGEMENT (SAFE – DOES NOT TOUCH EXISTING LOGIC)
# --------------------------------------------------------------------------- #
class AdminUserViewSet(viewsets.ViewSet):
    """
    Safe and isolated admin user endpoints.
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    # GET /api/admin/users/
    def list(self, request):
        users = UserProfile.objects.filter(role="client")
        return Response([
            {
                "id": u.user.id,
                "username": u.user.username,
                "email": u.user.email,
                "role": u.role,
                "is_active": u.user.is_active,
            }
            for u in users
        ])

    # GET /api/admin/users/<id>/
    def retrieve(self, request, pk=None):
        profile = get_object_or_404(UserProfile, user__pk=pk)
        user = profile.user

        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": profile.role,
            "is_active": user.is_active,
            "tasks": TaskSerializer(user.tasks.all(), many=True, context={'request': request}).data,
        })

    # POST /api/admin/users/<id>/activate_new/
    @action(detail=True, methods=['post'])
    def activate_new(self, request, pk=None):
        profile = get_object_or_404(UserProfile, user__pk=pk)
        user = profile.user
        user.is_active = True
        user.save()
        return Response({"detail": "User activated"})

    # POST /api/admin/users/<id>/deactivate_new/
    @action(detail=True, methods=['post'])
    def deactivate_new(self, request, pk=None):
        profile = get_object_or_404(UserProfile, user__pk=pk)
        user = profile.user
        user.is_active = False
        user.save()
        return Response({"detail": "User deactivated"})

    # DELETE /api/admin/users/<id>/delete_new/
    @action(detail=True, methods=['delete'])
    def delete_new(self, request, pk=None):
        profile = get_object_or_404(UserProfile, user__pk=pk)
        user = profile.user
        user.delete()
        return Response({"detail": "User deleted"})
