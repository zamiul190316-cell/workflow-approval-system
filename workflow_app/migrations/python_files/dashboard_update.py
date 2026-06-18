# ════════════════════════════════════════════════════════════════
# INSTRUCTION: Update dashboard views to add Pending Tasks counts
# FILE: workflow_app/views.py
# ════════════════════════════════════════════════════════════════
#
# FIND the dashboard() function
# FIND this block inside the elif user.is_approver_role() section:
#
#   data = {
#       'role': 'approver',
#       'pending_count': pending_steps.count(),
#       ...
#   }
#
# ADD these lines to the ctx dictionary (for ALL dashboard types):
# ════════════════════════════════════════════════════════════════

# Add to the approver dashboard ctx dict:
    from .models import ApprovalGroup, UserTaskHistory
    user_group_ids = ApprovalGroup.objects.filter(
        members__user=user, members__is_active=True, is_active=True
    ).values_list('pk', flat=True)
    group_pending_count = ApprovalStep.objects.filter(
        group_assignment__group_id__in=user_group_ids,
        status='pending'
    ).exclude(approver=user).count()
    total_pending = pending_steps.count() + group_pending_count
    completed_count = UserTaskHistory.objects.filter(user=user).count()

# Then add to ctx:
    ctx['total_pending_tasks'] = total_pending
    ctx['group_pending_count'] = group_pending_count
    ctx['completed_count'] = completed_count

# ════════════════════════════════════════════════════════════════
# UPDATE dashboard_approver.html stats section
# FIND this in dashboard_approver.html:
#   <div class="stats-grid">
#     <div class="stat-card amber">...Pending Actions...
#
# ADD two more stat cards:
# ════════════════════════════════════════════════════════════════
  <div class="stat-card violet"><div class="stat-label">Group Pending</div><div class="stat-value">{{ group_pending_count|default:"0" }}</div><div class="stat-icon">👥</div></div>
  <div class="stat-card blue"><div class="stat-label">Completed Tasks</div><div class="stat-value">{{ completed_count|default:"0" }}</div><div class="stat-icon">✅</div></div>
