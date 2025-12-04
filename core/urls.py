# core/urls.py
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # AUTH
    path('api/register/', views.RegisterView.as_view(), name='register'),
    path('api/token/', views.CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/user/', views.CurrentUserView.as_view(), name='current-user'),

    # CATEGORIES (Admin)
    path('api/admin/categories/', views.TaskCategoryListCreate.as_view(), name='category-list'),
    path('api/admin/categories/<int:pk>/', views.TaskCategoryDetail.as_view(), name='category-detail'),

    # TASKS (Client + Admin)
    path('api/tasks/', views.TaskListCreate.as_view(), name='task-list'),
    path('api/tasks/<int:pk>/', views.TaskDetail.as_view(), name='task-detail'),
    
    # CLIENT TASK ACTIONS
    path('api/tasks/<int:pk>/accept-budget/', views.client_accept_budget, name='client-accept-budget'),
    path('api/tasks/<int:pk>/counter-budget/', views.client_counter_budget, name='client-counter-budget'),
    path('api/tasks/<int:pk>/reject-budget/', views.client_reject_budget, name='client-reject-budget'),
    path('api/tasks/<int:pk>/withdraw/', views.client_withdraw_task, name='client-withdraw-task'),
    path('api/tasks/<int:pk>/approve/', views.client_approve_task, name='task-approve'),
    path('api/tasks/<int:pk>/request-revision/', views.client_request_revision, name='task-request-revision'),

    # ADMIN TASK ACTIONS
    path('api/admin/tasks/<int:pk>/accept/', views.AdminAcceptTask.as_view(), name='admin-accept-task'),
    path('api/admin/tasks/<int:pk>/propose-budget/', views.AdminProposeBudget.as_view(), name='admin-propose-budget'),
    path('api/admin/tasks/<int:pk>/accept-budget/', views.AdminAcceptBudget.as_view(), name='admin-accept-budget'),
    path('api/admin/tasks/<int:pk>/update-progress/', views.AdminUpdateProgress.as_view(), name='admin-update-progress'),
    path('api/admin/tasks/<int:pk>/submit-review/', views.AdminSubmitForReview.as_view(), name='admin-submit-review'),
    path('api/admin/tasks/<int:pk>/mark-complete/', views.AdminMarkComplete.as_view(), name='admin-mark-complete'),
    path('api/admin/tasks/<int:pk>/reject/', views.AdminRejectTask.as_view(), name='admin-reject-task'),
    path('api/admin/tasks/<int:pk>/upload-solution/', views.AdminUploadSolution.as_view(), name='admin-upload-solution'),

    # ADMIN STATS
    path('api/admin/stats/', views.AdminStatsView.as_view(), name='admin-stats'),

    # CHAT
    path('api/tasks/<int:task_id>/chat/', views.ChatMessageListCreate.as_view(), name='chat-messages'),

    # NOTIFICATIONS
    path('api/notifications/', views.NotificationList.as_view(), name='notification-list'),
    path('api/notifications/<int:pk>/read/', views.MarkNotificationRead.as_view(), name='mark-notification-read'),
]