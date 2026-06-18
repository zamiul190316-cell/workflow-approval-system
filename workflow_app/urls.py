from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('', views.home_redirect, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),

    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),

    # Profile
    path('profile/', views.my_profile, name='my_profile'),

    # Requests
    path('requests/create/', views.create_request, name='create_request'),
    path('requests/', views.my_requests, name='my_requests'),
    path('requests/<int:pk>/', views.request_detail, name='request_detail'),
    path('requests/<int:pk>/edit/', views.edit_request, name='edit_request'),
    path('requests/<int:pk>/submit/', views.submit_request, name='submit_request'),
    path('requests/<int:pk>/pdf/', views.generate_pdf, name='generate_pdf'),
    path('requests/<int:pk>/add-approver/', views.add_approver_dynamic, name='add_approver_dynamic'),
    path('requests/<int:pk>/remove-approver/<int:step_id>/', views.remove_approver_dynamic, name='remove_approver_dynamic'),

    # Approvals
    path('approvals/', views.pending_approvals, name='pending_approvals'),
    path('approvals/history/', views.approval_history, name='approval_history'),
    path('approvals/<int:step_id>/action/', views.approval_action, name='approval_action'),
    path('approvals/token/<uuid:token>/', views.approval_by_token, name='approval_by_token'),
    path('approvals/delegate/', views.delegate_approval, name='delegate_approval'),
    path('approvals/delegate/revoke/', views.revoke_delegation, name='revoke_delegation'),

    # Payment
    path('payment/<int:request_id>/setup/', views.payment_setup, name='payment_setup'),
    path('payment/<int:payment_id>/release/', views.payment_release, name='payment_release'),
    path('payment/<int:payment_id>/installment/<int:inst_id>/release/', views.release_installment, name='release_installment'),

    # Admin Panel
    path('admin-panel/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-panel/users/', views.manage_users, name='manage_users'),
    path('admin-panel/users/<int:pk>/edit/', views.edit_user, name='edit_user'),
    path('admin-panel/audit/', views.audit_trail, name='audit_trail'),
    path('admin-panel/sla/', views.sla_monitor, name='sla_monitor'),
    path('admin-panel/divisions/', views.manage_divisions, name='manage_divisions'),
    path('admin-panel/divisions/<int:pk>/edit/', views.edit_division, name='edit_division'),
    path('admin-panel/branches/', views.manage_branches, name='manage_branches'),
    path('admin-panel/branches/<int:pk>/edit/', views.edit_branch, name='edit_branch'),
    path('admin-panel/templates/', views.manage_templates, name='manage_templates'),
    path('admin-panel/templates/create/', views.create_template, name='create_template'),
    path('admin-panel/leaves/', views.manage_leaves, name='manage_leaves'),
    path('admin-panel/leaves/<int:leave_id>/end/', views.end_leave, name='end_leave'),

    # API / AJAX
    path('api/users/', views.api_users, name='api_users'),
    path('api/template/<int:template_id>/steps/', views.api_template_steps, name='api_template_steps'),
    path('api/notifications/mark-read/', views.mark_notifications_read, name='mark_notifications_read'),
    path('api/request/<int:pk>/status/', views.request_status_api, name='request_status_api'),
    path('api/ai-validate/', views.ai_validate_document, name='ai_validate_document'),
    path('notifications/', views.notifications_list, name='notifications_list'),
    path('inbox/', views.inbox, name='inbox'),
    path('inbox/compose/', views.inbox_compose, name='inbox_compose'),
    path('inbox/mark-all-read/', views.inbox_mark_read, name='inbox_mark_read'),
    path('inbox/<int:pk>/', views.inbox_message_detail, name='inbox_detail'),
    path('inbox/<int:pk>/star/', views.inbox_star, name='inbox_star'),
    path('inbox/<int:pk>/delete/', views.inbox_delete, name='inbox_delete'),
]
