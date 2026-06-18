# ══════════════════════════════════════════════════════════════════
# ADD THIS INSIDE _process_approval_action() in views.py
# FILE: workflow_app/views.py
#
# FIND the with transaction.atomic(): block inside _process_approval_action
# FIND the very last line inside that block:
#     (it ends before "return redirect('request_detail', pk=req.pk)")
#
# ADD these lines BEFORE the return redirect line:
# ══════════════════════════════════════════════════════════════════

            # Record in UserTaskHistory (powers My Completed Tasks)
            try:
                from .models import UserTaskHistory
                action_map = {
                    'approve': 'approved',
                    'reject': 'rejected',
                    'return': 'returned',
                }
                task_action = action_map.get(action)
                if task_action:
                    UserTaskHistory.objects.create(
                        user=request.user,
                        request=req,
                        step=step,
                        action=task_action,
                        comment=comment,
                        has_attachment=bool(request.FILES.get('attachment')),
                    )
            except Exception:
                pass

# ══════════════════════════════════════════════════════════════════
# ALSO UPDATE send_approval_notification() in views.py
# FIND: def send_approval_notification(step):
# ADD this block right before the final try: block that sends email
# This makes group steps notify ALL group members
# ══════════════════════════════════════════════════════════════════

    # Check if this is a group step — notify all members
    try:
        from .models import ApprovalStepGroup
        step_group = step.group_assignment
        group = step_group.group
        group_members = [m.user for m in group.members.filter(is_active=True).select_related('user')]
        action_url = f"{settings.SITE_URL}/login/?next=/approvals/group/{step.pk}/action/"
        for member in group_members:
            try:
                Notification.objects.create(
                    user=member, request=req, notif_type='approval_required',
                    title=f'[Group] Action Required: {req.reference_number}',
                    message=f'Group: {group.name} — Step {step.step_number}/{req.total_steps}: {req.subject}'
                )
                from .models import InboxMessage
                InboxMessage.objects.create(
                    sender=None, recipient=member,
                    subject=f'[Group Action Required] {req.reference_number}: {req.subject}',
                    body=f'Group: {group.name}\nStep {step.step_number} of {req.total_steps}\n\n{req.subject}\n\nLogin: {action_url}',
                    request=req,
                )
            except Exception:
                pass
        return  # Skip individual notification for group steps
    except Exception:
        pass  # Not a group step — continue with individual notification below
