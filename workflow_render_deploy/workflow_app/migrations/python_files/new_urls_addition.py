# ══════════════════════════════════════════════════════════════════
# ADD THESE LINES TO: workflow_app/urls.py
# Find the closing ] bracket at the end of urlpatterns
# Paste ALL these lines just before that ]
# ══════════════════════════════════════════════════════════════════

    # ── Approval Groups ──────────────────────────────────────────
    path('admin-panel/groups/', views.manage_groups, name='manage_groups'),
    path('admin-panel/groups/create/', views.create_group, name='create_group'),
    path('admin-panel/groups/<int:pk>/', views.group_detail, name='group_detail'),
    path('admin-panel/groups/<int:pk>/edit/', views.edit_group, name='edit_group'),
    path('admin-panel/groups/<int:pk>/delete/', views.delete_group, name='delete_group'),

    # ── Group Approval Action ─────────────────────────────────────
    path('approvals/group/<int:step_id>/action/', views.group_approval_action, name='group_approval_action'),

    # ── Pending Tasks ────────────────────────────────────────────
    path('pending-tasks/', views.pending_tasks, name='pending_tasks'),

    # ── My Completed Tasks ────────────────────────────────────────
    path('completed-tasks/', views.my_completed_tasks, name='my_completed_tasks'),

    # ── API ───────────────────────────────────────────────────────
    path('api/groups/', views.api_groups_list, name='api_groups_list'),
    path('api/pending-tasks/count/', views.pending_tasks_count_api, name='pending_tasks_count_api'),
