# ══════════════════════════════════════════════════════════════════
# PASTE THIS AT THE VERY BOTTOM OF:
# workflow_app/views.py
# DO NOT DELETE OR CHANGE ANYTHING ABOVE THIS
# ══════════════════════════════════════════════════════════════════


# ─── APPROVAL GROUPS ──────────────────────────────────────────────────────────

@login_required
@admin_required
def manage_groups(request):
    from .models import ApprovalGroup
    q = request.GET.get('q', '')
    division_filter = request.GET.get('division', '')
    groups = ApprovalGroup.objects.select_related('owner', 'division').order_by('name')
    if q:
        groups = groups.filter(name__icontains=q)
    if division_filter:
        groups = groups.filter(division_id=division_filter)
    return render(request, 'workflow_app/manage_groups.html', {
        'groups': groups,
        'divisions': Division.objects.filter(is_active=True),
        'q': q, 'division_filter': division_filter,
    })


@login_required
@admin_required
def create_group(request):
    from .models import ApprovalGroup, ApprovalGroupMember
    divisions = Division.objects.filter(is_active=True)
    users = User.objects.filter(is_active=True).order_by('first_name', 'last_name')
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '')
        division_id = request.POST.get('division')
        member_ids = request.POST.getlist('members')
        if not name:
            messages.error(request, 'Group name is required.')
        elif len(member_ids) < 1:
            messages.error(request, 'At least 1 member is required.')
        else:
            with transaction.atomic():
                group = ApprovalGroup.objects.create(
                    name=name, description=description, owner=request.user,
                    division_id=division_id if division_id else None,
                )
                for uid in member_ids:
                    try:
                        ApprovalGroupMember.objects.create(group=group, user_id=uid)
                    except Exception:
                        pass
            messages.success(request, f'Group "{name}" created with {len(member_ids)} members.')
            return redirect('manage_groups')
    return render(request, 'workflow_app/create_group.html', {
        'divisions': divisions, 'users': users
    })


@login_required
@admin_required
def edit_group(request, pk):
    from .models import ApprovalGroup, ApprovalGroupMember
    group = get_object_or_404(ApprovalGroup, pk=pk)
    divisions = Division.objects.filter(is_active=True)
    all_users = User.objects.filter(is_active=True).order_by('first_name', 'last_name')
    current_member_ids = list(group.members.filter(is_active=True).values_list('user_id', flat=True))
    if request.method == 'POST':
        group.name = request.POST.get('name', group.name).strip()
        group.description = request.POST.get('description', group.description)
        div_id = request.POST.get('division')
        group.division_id = div_id if div_id else None
        group.is_active = request.POST.get('is_active') == 'on'
        group.save()
        member_ids = request.POST.getlist('members')
        with transaction.atomic():
            group.members.all().update(is_active=False)
            for uid in member_ids:
                obj, _ = ApprovalGroupMember.objects.get_or_create(group=group, user_id=uid)
                obj.is_active = True
                obj.save()
        messages.success(request, f'Group "{group.name}" updated.')
        return redirect('manage_groups')
    return render(request, 'workflow_app/edit_group.html', {
        'group': group, 'divisions': divisions,
        'all_users': all_users, 'current_member_ids': current_member_ids,
    })


@login_required
@admin_required
def delete_group(request, pk):
    from .models import ApprovalGroup
    group = get_object_or_404(ApprovalGroup, pk=pk)
    if request.method == 'POST':
        group.is_active = False
        group.save()
        messages.success(request, f'Group "{group.name}" deactivated.')
    return redirect('manage_groups')


@login_required
@admin_required
def group_detail(request, pk):
    from .models import ApprovalGroup
    group = get_object_or_404(ApprovalGroup, pk=pk)
    members = group.members.filter(is_active=True).select_related(
        'user', 'user__division', 'user__branch'
    )
    return render(request, 'workflow_app/group_detail.html', {
        'group': group, 'members': members,
    })


@login_required
def api_groups_list(request):
    from .models import ApprovalGroup
    groups = ApprovalGroup.objects.filter(is_active=True).order_by('name')
    data = [{
        'id': g.pk, 'name': g.name, 'description': g.description,
        'member_count': g.members.filter(is_active=True).count(),
        'members': [
            {'id': m.user.pk,
             'name': m.user.get_full_name() or m.user.username,
             'employee_id': m.user.employee_id or 'N/A',
             'designation': m.user.designation}
            for m in g.members.filter(is_active=True).select_related('user')
        ],
    } for g in groups]
    return JsonResponse({'groups': data})


# ─── GROUP APPROVAL ACTION ────────────────────────────────────────────────────

@login_required
def group_approval_action(request, step_id):
    from .models import ApprovalStepGroup, GroupApprovalLog, UserTaskHistory
    step = get_object_or_404(ApprovalStep, pk=step_id, status='pending')
    try:
        step_group = step.group_assignment
        group = step_group.group
    except Exception:
        messages.error(request, 'This is not a group approval step.')
        return redirect('request_detail', pk=step.request.pk)

    is_member = group.members.filter(user=request.user, is_active=True).exists()
    if not is_member and request.user.role != 'admin':
        messages.error(request, f'You are not a member of "{group.name}".')
        return redirect('dashboard')

    req = step.request

    if request.method == 'POST':
        action = request.POST.get('action')
        comment = request.POST.get('comment', '').strip()
        ip = get_client_ip(request)

        if action in ['rejected', 'returned', 'modification_requested'] and not comment:
            messages.error(request, 'Comment is required for this action.')
            return render(request, 'workflow_app/group_approval_action.html', {
                'step': step, 'group': group, 'req': req,
                'members': group.get_active_members(),
                'history': req.history.select_related('actor').order_by('timestamp'),
            })

        with transaction.atomic():
            attachment = None
            if request.FILES.get('attachment'):
                step.attachment = request.FILES['attachment']
                step.save(update_fields=['attachment'])
                attachment = step.attachment

            GroupApprovalLog.objects.create(
                step=step, group=group, actor=request.user,
                action=action, comment=comment,
                attachment=attachment, ip_address=ip,
            )

            UserTaskHistory.objects.create(
                user=request.user, request=req, step=step,
                action=action, comment=comment,
                has_attachment=bool(attachment),
                via_group=group,
            )

            if action == 'approved':
                WorkflowEngine.advance(step, request.user, comment, ip)
                messages.success(request, f'✅ Step approved on behalf of "{group.name}".')
            elif action == 'rejected':
                WorkflowEngine.reject(step, request.user, comment, ip)
                messages.warning(request, '❌ Request rejected.')
            elif action in ('returned', 'modification_requested'):
                WorkflowEngine.return_to_initiator(step, request.user, comment, ip)
                msg = '↩️ Returned to initiator.' if action == 'returned' else '📝 Modification requested.'
                messages.info(request, msg)
            elif action == 'commented':
                log_history(req, request.user, 'commented', comment=comment, step=step, ip=ip)
                messages.info(request, 'Comment added.')

        return redirect('request_detail', pk=req.pk)

    return render(request, 'workflow_app/group_approval_action.html', {
        'step': step, 'group': group, 'req': req,
        'members': group.get_active_members(),
        'history': req.history.select_related('actor').order_by('timestamp'),
    })


# ─── PENDING TASKS ────────────────────────────────────────────────────────────

@login_required
def pending_tasks(request):
    from .models import ApprovalGroup
    q              = request.GET.get('q', '')
    division_filter= request.GET.get('division', '')
    requester_filter=request.GET.get('requester', '')
    date_from      = request.GET.get('date_from', '')
    date_to        = request.GET.get('date_to', '')

    individual_steps = ApprovalStep.objects.filter(
        approver=request.user, status='pending'
    ).select_related('request', 'request__initiator',
                     'request__category', 'request__division', 'request__branch'
    ).order_by('deadline')

    user_group_ids = ApprovalGroup.objects.filter(
        members__user=request.user, members__is_active=True, is_active=True
    ).values_list('pk', flat=True)

    group_steps = ApprovalStep.objects.filter(
        group_assignment__group_id__in=user_group_ids, status='pending',
    ).exclude(approver=request.user).select_related(
        'request', 'request__initiator', 'request__category',
        'request__division', 'group_assignment__group'
    ).order_by('deadline')

    delegated_steps = ApprovalStep.objects.filter(
        approver__delegate_to=request.user,
        approver__delegate_until__gt=timezone.now(),
        status='pending',
    ).select_related('request', 'request__initiator', 'approver').order_by('deadline')

    if q:
        individual_steps = individual_steps.filter(Q(request__reference_number__icontains=q)|Q(request__subject__icontains=q))
        group_steps      = group_steps.filter(Q(request__reference_number__icontains=q)|Q(request__subject__icontains=q))
    if division_filter:
        individual_steps = individual_steps.filter(request__division_id=division_filter)
        group_steps      = group_steps.filter(request__division_id=division_filter)
    if requester_filter:
        f = Q(request__initiator__first_name__icontains=requester_filter)|Q(request__initiator__last_name__icontains=requester_filter)
        individual_steps = individual_steps.filter(f)
        group_steps      = group_steps.filter(f)
    if date_from:
        individual_steps = individual_steps.filter(request__submitted_at__date__gte=date_from)
        group_steps      = group_steps.filter(request__submitted_at__date__gte=date_from)
    if date_to:
        individual_steps = individual_steps.filter(request__submitted_at__date__lte=date_to)
        group_steps      = group_steps.filter(request__submitted_at__date__lte=date_to)

    total_count = individual_steps.count() + group_steps.count() + delegated_steps.count()

    return render(request, 'workflow_app/pending_tasks.html', {
        'individual_steps': individual_steps,
        'group_steps':      group_steps,
        'delegated_steps':  delegated_steps,
        'total_count':      total_count,
        'divisions':        Division.objects.filter(is_active=True),
        'q': q, 'division_filter': division_filter,
        'date_from': date_from, 'date_to': date_to,
        'requester_filter': requester_filter,
        'now': timezone.now(),
    })


# ─── MY COMPLETED TASKS ───────────────────────────────────────────────────────

@login_required
def my_completed_tasks(request):
    from .models import UserTaskHistory
    history = UserTaskHistory.objects.filter(user=request.user).select_related(
        'request', 'request__initiator', 'request__category',
        'request__division', 'step', 'via_group'
    ).order_by('-acted_at')

    action_filter   = request.GET.get('action', '')
    division_filter = request.GET.get('division', '')
    requester_filter= request.GET.get('requester', '')
    date_from       = request.GET.get('date_from', '')
    date_to         = request.GET.get('date_to', '')
    has_attachment  = request.GET.get('has_attachment', '')
    q               = request.GET.get('q', '')

    if action_filter:
        history = history.filter(action=action_filter)
    if division_filter:
        history = history.filter(request__division_id=division_filter)
    if requester_filter:
        history = history.filter(
            Q(request__initiator__first_name__icontains=requester_filter) |
            Q(request__initiator__last_name__icontains=requester_filter)
        )
    if date_from:
        history = history.filter(acted_at__date__gte=date_from)
    if date_to:
        history = history.filter(acted_at__date__lte=date_to)
    if has_attachment == '1':
        history = history.filter(has_attachment=True)
    if q:
        history = history.filter(
            Q(request__reference_number__icontains=q) |
            Q(request__subject__icontains=q)
        )

    return render(request, 'workflow_app/my_completed_tasks.html', {
        'history':          history[:200],
        'total_count':      history.count(),
        'action_filter':    action_filter,
        'division_filter':  division_filter,
        'requester_filter': requester_filter,
        'date_from':  date_from,
        'date_to':    date_to,
        'has_attachment':   has_attachment,
        'q':          q,
        'divisions':  Division.objects.filter(is_active=True),
        'action_choices': UserTaskHistory.ACTION_CHOICES,
    })


# ─── PENDING COUNT API ────────────────────────────────────────────────────────

@login_required
def pending_tasks_count_api(request):
    from .models import ApprovalGroup
    individual = ApprovalStep.objects.filter(approver=request.user, status='pending').count()
    user_group_ids = ApprovalGroup.objects.filter(
        members__user=request.user, members__is_active=True, is_active=True
    ).values_list('pk', flat=True)
    group = ApprovalStep.objects.filter(
        group_assignment__group_id__in=user_group_ids, status='pending'
    ).exclude(approver=request.user).count()
    return JsonResponse({'total': individual + group, 'individual': individual, 'group': group})
