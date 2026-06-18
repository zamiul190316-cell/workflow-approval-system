# ════════════════════════════════════════════════════════════════
# INSTRUCTION: Update the _process_approval_action function in views.py
# FILE: workflow_app/views.py
# ════════════════════════════════════════════════════════════════
#
# FIND this function:
#   def _process_approval_action(request, step):
#
# FIND inside it, after "if action == 'approve':" block,
# after "elif action == 'comment':" block,
# the line:  return redirect('request_detail', pk=req.pk)
#
# REPLACE the entire return redirect line at the bottom of the
# with/transaction.atomic() block with this code:
# ════════════════════════════════════════════════════════════════

            # ── Record in UserTaskHistory for My Completed Tasks ──────────
            try:
                from .models import UserTaskHistory
                action_map = {
                    'approve': 'approved',
                    'reject': 'rejected',
                    'return': 'returned',
                    'comment': 'commented',
                }
                task_action = action_map.get(action, action)
                if task_action not in ['commented']:  # only record real decisions
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
            # ── END UserTaskHistory ───────────────────────────────────────

        return redirect('request_detail', pk=req.pk)

# ════════════════════════════════════════════════════════════════
# ALSO: Add group support to create_request view
# In views.py find create_request function
# FIND this line inside the with transaction.atomic(): block:
#   for idx, (approver_id, role) in enumerate(zip(approver_ids, approver_roles), start=1):
#       approver = get_object_or_404(User, pk=approver_id)
#       ApprovalStep.objects.create(...)
#
# REPLACE the entire for loop with this:
# ════════════════════════════════════════════════════════════════

            step_type_list = data.getlist('step_types')  # 'individual' or 'group'
            group_id_list = data.getlist('group_ids')

            for idx, (approver_id, role) in enumerate(zip(approver_ids, approver_roles), start=1):
                step_type = step_type_list[idx-1] if idx-1 < len(step_type_list) else 'individual'
                group_id = group_id_list[idx-1] if idx-1 < len(group_id_list) else ''

                if step_type == 'group' and group_id:
                    # Group approval step — use group owner or first member as nominal approver
                    from .models import ApprovalGroup, ApprovalStepGroup
                    try:
                        grp = ApprovalGroup.objects.get(pk=group_id, is_active=True)
                        first_member = grp.members.filter(is_active=True).first()
                        nominal_approver = first_member.user if first_member else request.user
                        new_step = ApprovalStep.objects.create(
                            request=req, step_number=idx,
                            approver=nominal_approver,
                            approver_role=role or 'checker',
                            deadline=timezone.now() + timedelta(days=2 * idx)
                        )
                        ApprovalStepGroup.objects.create(step=new_step, group=grp)
                    except ApprovalGroup.DoesNotExist:
                        approver = get_object_or_404(User, pk=approver_id)
                        ApprovalStep.objects.create(
                            request=req, step_number=idx, approver=approver,
                            approver_role=role or 'checker',
                            deadline=timezone.now() + timedelta(days=2 * idx)
                        )
                else:
                    approver = get_object_or_404(User, pk=approver_id)
                    ApprovalStep.objects.create(
                        request=req, step_number=idx, approver=approver,
                        approver_role=role or 'checker',
                        deadline=timezone.now() + timedelta(days=2 * idx)
                    )

# ════════════════════════════════════════════════════════════════
# ALSO: Update send_approval_notification to notify group members
# FIND this function in views.py and REPLACE with this version:
# ════════════════════════════════════════════════════════════════

def send_approval_notification(step):
    """Send email + notification. If group step, notify ALL members."""
    from .models import ApprovalStepGroup

    # Check if this is a group step
    try:
        step_group = step.group_assignment
        group = step_group.group
        recipients = [m.user for m in group.members.filter(is_active=True).select_related('user')]
        is_group = True
    except Exception:
        recipients = [step.approver.get_effective_approver()]
        is_group = False

    req = step.request
    token_url = f"{settings.SITE_URL}/approvals/token/{step.token}/"
    login_then_approve = f"{settings.SITE_URL}/login/?next=/approvals/token/{step.token}/"

    if is_group:
        action_url = f"{settings.SITE_URL}/approvals/group/{step.pk}/action/"
        login_then_action = f"{settings.SITE_URL}/login/?next=/approvals/group/{step.pk}/action/"
    else:
        action_url = token_url
        login_then_action = login_then_approve

    for approver in recipients:
        subject = f"[Action Required] {req.reference_number}: {req.subject}"
        if is_group:
            subject = f"[Group Action Required] {req.reference_number}: {req.subject}"

        body = f"""Dear {approver.get_full_name() or approver.username},

{"A group approval request" if is_group else "A workflow request"} requires your action.
{"Group: " + group.name if is_group else ""}

Reference  : {req.reference_number}
Subject    : {req.subject}
Category   : {req.category.name}
Submitted  : {req.submitted_at.strftime('%d %b %Y %H:%M') if req.submitted_at else 'N/A'}
Step       : {step.step_number} of {req.total_steps}

{"Any member of " + group.name + " can take action." if is_group else ""}

Click to login and take action:
{login_then_action}

Trust Bank PLC — Workflow Approval System
"""

        try:
            from django.core.mail import EmailMultiAlternatives
            email_msg = EmailMultiAlternatives(
                subject=subject, body=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[approver.email],
            )
            email_msg.send(fail_silently=True)
            step.email_sent = True
            step.save(update_fields=['email_sent'])
        except Exception as e:
            import logging
            logging.getLogger('workflow').error(f'Email failed: {e}')

        # In-app notification
        try:
            from .models import Notification
            Notification.objects.create(
                user=approver, request=req,
                notif_type='approval_required',
                title=f"{'[Group] ' if is_group else ''}Action Required: {req.reference_number}",
                message=f"{'Group: ' + group.name + ' — ' if is_group else ''}Step {step.step_number}/{req.total_steps}: {req.subject}"
            )
        except Exception:
            pass

        # Internal inbox message
        try:
            from .models import InboxMessage
            InboxMessage.objects.create(
                sender=None, recipient=approver,
                subject=subject,
                body=f"Step {step.step_number} of {req.total_steps}\n\n{req.subject}\n\nLogin to take action: {login_then_action}",
                request=req,
            )
        except Exception:
            pass
