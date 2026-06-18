from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, Http404, HttpResponse
from django.utils import timezone
from django.db import transaction
from django.core.mail import send_mail
from django.conf import settings
from django.views.decorators.http import require_POST
from django.db.models import Q, Count
from .models import (
    User, ApprovalRequest, ApprovalStep, ApprovalHistory,
    ApprovalCategory, Payment, PaymentInstallment, Notification,
    Division, Branch, WorkflowTemplate, WorkflowTemplateStep,
    LeaveRecord, DelegationLog, RequestVersion, DigitalSignature
)
import json
import hashlib
from datetime import timedelta

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')


def log_history(request_obj, actor, action, comment='', step=None, ip=None, metadata=None):
    ApprovalHistory.objects.create(
        request=request_obj, actor=actor, action=action,
        comment=comment, step=step, ip_address=ip, metadata=metadata or {}
    )


def send_approval_notification(step):
    approver = step.approver.get_effective_approver()
    req = step.request
    token_url = f"{settings.SITE_URL}/approvals/token/{step.token}/"
    subject = f"[Action Required] Approval Request: {req.reference_number}"
    body = f"""Dear {approver.get_full_name() or approver.username},

You have a pending approval request requiring your action.

Reference Number : {req.reference_number}
Subject          : {req.subject}
Category         : {req.category.name}
Submitted By     : {req.initiator.get_full_name() or req.initiator.username}
Step             : {step.step_number} of {req.total_steps}
Your Role        : {step.get_approver_role_display()}

Description:
{req.description}

Please click the link below to review and take action:
{token_url}

This is an automated notification from Trust Bank PLC Workflow Approval System.
"""
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [approver.email], fail_silently=True)
        step.email_sent = True
        step.save(update_fields=['email_sent'])
    except Exception:
        pass

    Notification.objects.create(
        user=approver, request=req, notif_type='approval_required',
        title=f"Approval Required: {req.reference_number}",
        message=f"Step {step.step_number} of {req.total_steps}: {req.subject}"
    )


def send_status_notification(req, recipient, action):
    subject_map = {
        'approved': f"✅ Request Approved: {req.reference_number}",
        'rejected': f"❌ Request Rejected: {req.reference_number}",
        'returned': f"↩️ Request Returned: {req.reference_number}",
        'payment_released': f"💰 Payment Released: {req.reference_number}",
    }
    body_map = {
        'approved': f"Your request '{req.subject}' (Ref: {req.reference_number}) has been fully approved.",
        'rejected': f"Your request '{req.subject}' (Ref: {req.reference_number}) was rejected. Reason: {req.rejection_reason}",
        'returned': f"Your request '{req.subject}' (Ref: {req.reference_number}) was returned for modification.",
        'payment_released': f"Payment for request '{req.subject}' (Ref: {req.reference_number}) has been released.",
    }
    notif_type_map = {
        'approved': 'approved', 'rejected': 'rejected',
        'returned': 'returned', 'payment_released': 'payment',
    }
    try:
        send_mail(
            subject_map.get(action, 'Workflow Update'),
            body_map.get(action, ''),
            settings.DEFAULT_FROM_EMAIL, [recipient.email], fail_silently=True
        )
    except Exception:
        pass
    Notification.objects.create(
        user=recipient, request=req,
        notif_type=notif_type_map.get(action, 'info'),
        title=subject_map.get(action, 'Workflow Update'),
        message=body_map.get(action, '')
    )


def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.role != 'admin':
            messages.error(request, 'Admin access required.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


# ─── AUTH VIEWS ───────────────────────────────────────────────────────────────

def home_redirect(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        user = authenticate(request, username=request.POST.get('username'), password=request.POST.get('password'))
        if user:
            login(request, user)
            return redirect('dashboard')
        messages.error(request, 'Invalid username or password.')
    return render(request, 'workflow_app/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


def register_view(request):
    if request.method == 'POST':
        data = request.POST
        if User.objects.filter(username=data.get('username')).exists():
            messages.error(request, 'Username already taken.')
            return render(request, 'workflow_app/register.html', {'divisions': Division.objects.filter(is_active=True), 'branches': Branch.objects.filter(is_active=True)})
        user = User.objects.create_user(
            username=data.get('username'), email=data.get('email'),
            password=data.get('password'), first_name=data.get('first_name', ''),
            last_name=data.get('last_name', ''), role=data.get('role', 'initiator'),
            employee_id=data.get('employee_id', '') or None,
            designation=data.get('designation', ''), phone=data.get('phone', ''),
        )
        if data.get('division'):
            user.division_id = data.get('division')
        if data.get('branch'):
            user.branch_id = data.get('branch')
        user.save()
        messages.success(request, 'Account created! You can now log in.')
        return redirect('login')
    return render(request, 'workflow_app/register.html', {
        'divisions': Division.objects.filter(is_active=True),
        'branches': Branch.objects.filter(is_active=True),
    })


# ─── DASHBOARD ────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    user = request.user
    ctx = {'user': user}

    if user.role == 'admin':
        ctx['total_requests'] = ApprovalRequest.objects.count()
        ctx['pending_requests'] = ApprovalRequest.objects.filter(status__in=['pending', 'in_progress']).count()
        ctx['approved_requests'] = ApprovalRequest.objects.filter(status='approved').count()
        ctx['rejected_requests'] = ApprovalRequest.objects.filter(status='rejected').count()
        ctx['total_users'] = User.objects.count()
        ctx['total_divisions'] = Division.objects.count()
        ctx['total_branches'] = Branch.objects.count()
        ctx['recent_requests'] = ApprovalRequest.objects.select_related('initiator', 'category').order_by('-created_at')[:10]
        ctx['sla_breached'] = [r for r in ApprovalRequest.objects.filter(
            status__in=['pending', 'in_progress'], sla_deadline__isnull=False
        ) if r.is_sla_breached()]
        return render(request, 'workflow_app/dashboard_admin.html', ctx)

    elif user.is_approver_role():
        pending_steps = ApprovalStep.objects.filter(
            approver=user, status='pending'
        ).select_related('request', 'request__initiator', 'request__category').order_by('deadline')
        ctx['pending_steps'] = pending_steps
        ctx['pending_count'] = pending_steps.count()
        ctx['approved_count'] = ApprovalStep.objects.filter(approver=user, status='approved').count()
        ctx['rejected_count'] = ApprovalStep.objects.filter(approver=user, status='rejected').count()
        ctx['recent_history'] = ApprovalStep.objects.filter(
            approver=user, status__in=['approved', 'rejected', 'returned']
        ).select_related('request').order_by('-action_taken_at')[:5]
        ctx['delegated_steps'] = ApprovalStep.objects.filter(
            approver__delegate_to=user, status='pending'
        ).select_related('request').order_by('deadline')[:5]
        return render(request, 'workflow_app/dashboard_approver.html', ctx)

    else:
        my_requests = ApprovalRequest.objects.filter(initiator=user)
        ctx['my_requests'] = my_requests.order_by('-created_at')[:10]
        ctx['pending_count'] = my_requests.filter(status__in=['pending', 'in_progress']).count()
        ctx['approved_count'] = my_requests.filter(status='approved').count()
        ctx['rejected_count'] = my_requests.filter(status='rejected').count()
        ctx['draft_count'] = my_requests.filter(status='draft').count()
        ctx['categories'] = ApprovalCategory.objects.filter(is_active=True)
        return render(request, 'workflow_app/dashboard_initiator.html', ctx)


# ─── REQUEST MANAGEMENT ───────────────────────────────────────────────────────

@login_required
def create_request(request):
    categories = ApprovalCategory.objects.filter(is_active=True)
    approvers = User.objects.filter(is_active=True).filter(
        Q(role__in=['approver','chief_manager','sub_manager','manager_operations',
                    'division_head','branch_manager','md','maker','checker'])
    ).order_by('first_name', 'last_name')
    templates = WorkflowTemplate.objects.filter(is_active=True).select_related('category')
    divisions = Division.objects.filter(is_active=True)
    branches = Branch.objects.filter(is_active=True)

    if request.method == 'POST':
        data = request.POST
        category_id = data.get('category')
        subject = data.get('subject', '').strip()
        description = data.get('description', '').strip()
        amount = data.get('amount') or None
        approver_ids = data.getlist('approvers')
        approver_roles = data.getlist('approver_roles')

        errors = []
        if not subject: errors.append('Subject is required.')
        if not description: errors.append('Description is required.')
        if not category_id: errors.append('Category is required.')
        if len(approver_ids) < 2: errors.append('Minimum 2 approvers required.')
        if len(approver_ids) > 50: errors.append('Maximum 50 approvers allowed.')

        # Conditional rule check
        if category_id:
            try:
                cat = ApprovalCategory.objects.get(pk=category_id)
                if cat.required_division and cat.min_required_from_division > 0:
                    division_approver_count = User.objects.filter(
                        pk__in=approver_ids, division=cat.required_division
                    ).count()
                    if division_approver_count < cat.min_required_from_division:
                        errors.append(
                            f"At least {cat.min_required_from_division} approver(s) must be from the "
                            f"'{cat.required_division.name}' division for this category."
                        )
            except ApprovalCategory.DoesNotExist:
                pass

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'workflow_app/create_request.html', {
                'categories': categories, 'approvers': approvers,
                'templates': templates, 'divisions': divisions, 'branches': branches,
                'post_data': data
            })

        with transaction.atomic():
            cat = get_object_or_404(ApprovalCategory, pk=category_id)
            req = ApprovalRequest.objects.create(
                subject=subject, description=description, category=cat,
                initiator=request.user, amount=amount, status='draft',
                total_steps=len(approver_ids),
                attachments_note=data.get('attachments_note', ''),
                sla_deadline=timezone.now() + timedelta(days=3),
                pdf_mode=data.get('pdf_mode', 'system'),
            )
            if data.get('branch'):
                req.branch_id = data.get('branch')
            if data.get('division'):
                req.division_id = data.get('division')
            req.save()

            for idx, (approver_id, role) in enumerate(zip(approver_ids, approver_roles), start=1):
                approver = get_object_or_404(User, pk=approver_id)
                ApprovalStep.objects.create(
                    request=req, step_number=idx, approver=approver,
                    approver_role=role or 'checker',
                    deadline=timezone.now() + timedelta(days=2 * idx)
                )
            if request.FILES.get('attachment_file'):
                req.attachment_file = request.FILES['attachment_file']
                req.save()
            log_history(req, request.user, 'created', ip=get_client_ip(request))

        messages.success(request, f'Request {req.reference_number} created as draft.')
        return redirect('request_detail', pk=req.pk)

    return render(request, 'workflow_app/create_request.html', {
        'categories': categories, 'approvers': approvers,
        'role_choices': ApprovalStep.APPROVER_ROLE_CHOICES,
        'templates': templates, 'divisions': divisions, 'branches': branches,
    })


@login_required
def edit_request(request, pk):
    req = get_object_or_404(ApprovalRequest, pk=pk, initiator=request.user)
    if req.status not in ['draft', 'rejected', 'returned']:
        messages.error(request, 'Only draft, rejected, or returned requests can be edited.')
        return redirect('request_detail', pk=pk)

    categories = ApprovalCategory.objects.filter(is_active=True)
    approvers = User.objects.filter(is_active=True).filter(
        Q(role__in=['approver','chief_manager','sub_manager','manager_operations',
                    'division_head','branch_manager','md','maker','checker'])
    )
    divisions = Division.objects.filter(is_active=True)
    branches = Branch.objects.filter(is_active=True)

    if request.method == 'POST':
        data = request.POST
        approver_ids = data.getlist('approvers')
        approver_roles = data.getlist('approver_roles')

        if len(approver_ids) < 2 or len(approver_ids) > 50:
            messages.error(request, 'Approvers must be between 2 and 50.')
            return redirect('edit_request', pk=pk)

        with transaction.atomic():
            # Save version snapshot
            RequestVersion.objects.create(
                request=req, version_number=req.version,
                subject=req.subject, description=req.description,
                status_snapshot=req.status, saved_by=request.user
            )
            req.version += 1
            req.subject = data.get('subject', req.subject)
            req.description = data.get('description', req.description)
            req.category = get_object_or_404(ApprovalCategory, pk=data.get('category', req.category.pk))
            req.amount = data.get('amount') or None
            req.status = 'draft'
            req.current_step = 1
            req.total_steps = len(approver_ids)
            req.rejection_reason = ''
            req.pdf_mode = data.get('pdf_mode', req.pdf_mode)
            if data.get('branch'):
                req.branch_id = data.get('branch')
            if data.get('division'):
                req.division_id = data.get('division')
            req.save()

            req.steps.all().delete()
            for idx, (approver_id, role) in enumerate(zip(approver_ids, approver_roles), start=1):
                approver = get_object_or_404(User, pk=approver_id)
                ApprovalStep.objects.create(
                    request=req, step_number=idx, approver=approver,
                    approver_role=role or 'checker',
                    deadline=timezone.now() + timedelta(days=2 * idx)
                )
            if request.FILES.get('attachment_file'):
                req.attachment_file = request.FILES['attachment_file']
                req.save()
            log_history(req, request.user, 'resubmitted',
                        comment='Request edited.', ip=get_client_ip(request),
                        metadata={'version': req.version})
        messages.success(request, 'Request updated.')
        return redirect('request_detail', pk=pk)

    return render(request, 'workflow_app/create_request.html', {
        'categories': categories, 'approvers': approvers,
        'role_choices': ApprovalStep.APPROVER_ROLE_CHOICES,
        'edit_mode': True, 'req': req,
        'current_steps': req.steps.order_by('step_number'),
        'divisions': divisions, 'branches': branches,
    })


@login_required
def submit_request(request, pk):
    req = get_object_or_404(ApprovalRequest, pk=pk, initiator=request.user)
    if req.status not in ['draft', 'rejected', 'returned']:
        messages.error(request, 'Request cannot be submitted at this stage.')
        return redirect('request_detail', pk=pk)
    if req.steps.count() < 2:
        messages.error(request, 'At least 2 approvers required before submitting.')
        return redirect('request_detail', pk=pk)

    with transaction.atomic():
        req.status = 'pending'
        req.current_step = 1
        req.submitted_at = timezone.now()
        req.save()
        first_step = req.steps.filter(step_number=1).first()
        if first_step:
            send_approval_notification(first_step)
        log_history(req, request.user, 'submitted', comment='Submitted for approval.', ip=get_client_ip(request))

    messages.success(request, f'Request {req.reference_number} submitted for approval.')
    return redirect('request_detail', pk=req.pk)


@login_required
def my_requests(request):
    status_filter = request.GET.get('status', '')
    qs = ApprovalRequest.objects.filter(initiator=request.user).select_related('category', 'branch', 'division').order_by('-created_at')
    if status_filter:
        qs = qs.filter(status=status_filter)
    if request.user.role == 'admin':
        qs = ApprovalRequest.objects.select_related('category', 'initiator').order_by('-created_at')
        if status_filter:
            qs = qs.filter(status=status_filter)
    return render(request, 'workflow_app/my_requests.html', {
        'requests': qs, 'status_filter': status_filter,
        'status_choices': ApprovalRequest.STATUS_CHOICES,
    })


@login_required
def request_detail(request, pk):
    if request.user.role == 'admin':
        req = get_object_or_404(ApprovalRequest, pk=pk)
    else:
        req = get_object_or_404(ApprovalRequest, pk=pk)
        is_approver = req.steps.filter(approver=request.user).exists()
        if req.initiator != request.user and not is_approver:
            raise Http404

    steps = req.steps.select_related('approver', 'acting_approver').order_by('step_number')
    history = req.history.select_related('actor', 'step').order_by('timestamp')
    payment = Payment.objects.filter(request=req).first()
    versions = req.versions.order_by('version_number')

    return render(request, 'workflow_app/request_detail.html', {
        'req': req, 'steps': steps, 'history': history,
        'payment': payment, 'versions': versions,
        'can_submit': req.initiator == request.user and req.status in ['draft', 'rejected', 'returned'],
        'can_edit': req.initiator == request.user and req.status in ['draft', 'rejected', 'returned'],
        'can_setup_payment': (
            req.status == 'approved' and not payment and
            (request.user.role == 'admin' or req.initiator == request.user)
        ),
        'can_download_pdf': req.status in ['approved', 'payment_pending', 'payment_released'],
        'can_add_approver': (
            request.user.role == 'admin' and
            req.status in ['pending', 'in_progress']
        ),
    })


# ─── DYNAMIC APPROVER MANAGEMENT ─────────────────────────────────────────────

@login_required
@admin_required
def add_approver_dynamic(request, pk):
    """Admin can dynamically add approver mid-workflow."""
    req = get_object_or_404(ApprovalRequest, pk=pk)
    if req.status not in ['pending', 'in_progress']:
        messages.error(request, 'Can only add approvers to active requests.')
        return redirect('request_detail', pk=pk)

    if request.method == 'POST':
        approver_id = request.POST.get('approver_id')
        role = request.POST.get('approver_role', 'custom')
        insert_after = int(request.POST.get('insert_after', req.total_steps))

        with transaction.atomic():
            # Shift existing steps after insertion point
            steps_to_shift = req.steps.filter(step_number__gt=insert_after).order_by('-step_number')
            for s in steps_to_shift:
                s.step_number += 1
                s.save()

            new_step_number = insert_after + 1
            approver = get_object_or_404(User, pk=approver_id)
            ApprovalStep.objects.create(
                request=req, step_number=new_step_number,
                approver=approver, approver_role=role,
                deadline=timezone.now() + timedelta(days=2)
            )
            req.total_steps += 1
            req.save()
            log_history(req, request.user, 'approver_added',
                        comment=f'Added {approver.get_full_name()} at step {new_step_number}',
                        ip=get_client_ip(request))

        messages.success(request, f'Approver {approver.get_full_name()} added at step {new_step_number}.')
    return redirect('request_detail', pk=pk)


@login_required
@admin_required
def remove_approver_dynamic(request, pk, step_id):
    """Admin can remove a pending approver step mid-workflow."""
    req = get_object_or_404(ApprovalRequest, pk=pk)
    step = get_object_or_404(ApprovalStep, pk=step_id, request=req, status='pending')

    if req.total_steps <= 2:
        messages.error(request, 'Cannot remove: minimum 2 approvers required.')
        return redirect('request_detail', pk=pk)

    with transaction.atomic():
        removed_step_number = step.step_number
        step_approver = step.approver.get_full_name()
        step.delete()
        # Re-number remaining steps
        for s in req.steps.filter(step_number__gt=removed_step_number).order_by('step_number'):
            s.step_number -= 1
            s.save()
        req.total_steps -= 1
        req.save()
        log_history(req, request.user, 'approver_removed',
                    comment=f'Removed {step_approver} from step {removed_step_number}',
                    ip=get_client_ip(request))

    messages.success(request, 'Approver removed.')
    return redirect('request_detail', pk=pk)


# ─── APPROVAL ACTIONS ─────────────────────────────────────────────────────────

@login_required
def pending_approvals(request):
    steps = ApprovalStep.objects.filter(
        approver=request.user, status='pending'
    ).select_related('request', 'request__initiator', 'request__category').order_by('deadline')
    # Also show delegated steps
    delegated = ApprovalStep.objects.filter(
        approver__delegate_to=request.user,
        approver__delegate_until__gt=timezone.now(),
        status='pending'
    ).select_related('request', 'request__initiator', 'request__category', 'approver').order_by('deadline')
    return render(request, 'workflow_app/pending_approvals.html', {
        'steps': steps, 'delegated_steps': delegated
    })


@login_required
def approval_history(request):
    steps = ApprovalStep.objects.filter(
        approver=request.user, status__in=['approved', 'rejected', 'returned']
    ).select_related('request', 'request__initiator', 'request__category').order_by('-action_taken_at')
    return render(request, 'workflow_app/approval_history.html', {'steps': steps})


@login_required
def approval_action(request, step_id):
    step = get_object_or_404(ApprovalStep, pk=step_id, status='pending')
    # Allow if direct approver or acting delegate
    if step.approver != request.user:
        effective = step.approver.get_effective_approver()
        if effective != request.user and request.user.role != 'admin':
            messages.error(request, 'You are not authorized for this approval step.')
            return redirect('dashboard')
    return _process_approval_action(request, step)


def approval_by_token(request, token):
    step = get_object_or_404(ApprovalStep, token=token, status='pending')
    if not request.user.is_authenticated:
        return redirect(f'/login/?next=/approvals/token/{token}/')
    if step.approver != request.user:
        effective = step.approver.get_effective_approver()
        if effective != request.user and request.user.role != 'admin':
            messages.error(request, 'You are not authorized for this approval step.')
            return redirect('dashboard')
    return _process_approval_action(request, step)


def _process_approval_action(request, step):
    req = step.request
    if request.method == 'POST':
        action = request.POST.get('action')
        comment = request.POST.get('comment', '').strip()
        ip = get_client_ip(request)

        with transaction.atomic():
            step.comment = comment
            step.action_taken_at = timezone.now()
            # Track acting approver if delegated
            if step.approver != request.user:
                step.acting_approver = request.user
                step.status = 'delegated'

            if action == 'approve':
                step.status = 'approved'
                step.save()
                # Create digital signature hash
                sig_data = f"{step.pk}{request.user.pk}{step.action_taken_at}{comment}"
                DigitalSignature.objects.create(
                    step=step, user=request.user,
                    signature_hash=hashlib.sha256(sig_data.encode()).hexdigest(),
                    ip_address=ip
                )
                log_history(req, request.user, 'approved_step', comment=comment, step=step, ip=ip)

                if step.step_number >= req.total_steps:
                    req.status = 'approved'
                    req.completed_at = timezone.now()
                    req.save()
                    log_history(req, request.user, 'fully_approved', ip=ip)
                    send_status_notification(req, req.initiator, 'approved')
                    messages.success(request, '✅ Request fully approved!')
                else:
                    req.status = 'in_progress'
                    req.current_step = step.step_number + 1
                    req.save()
                    next_step = req.steps.filter(step_number=req.current_step).first()
                    if next_step:
                        send_approval_notification(next_step)
                    messages.success(request, f'Step {step.step_number} approved. Moved to step {req.current_step}.')

            elif action == 'reject':
                step.status = 'rejected'
                step.save()
                req.status = 'rejected'
                req.rejection_reason = comment or 'No reason provided.'
                req.save()
                log_history(req, request.user, 'rejected_step', comment=comment, step=step, ip=ip)
                log_history(req, request.user, 'rejected', ip=ip)
                send_status_notification(req, req.initiator, 'rejected')
                messages.warning(request, '❌ Request rejected and returned to initiator.')

            elif action == 'return':
                step.status = 'returned'
                step.save()
                req.status = 'returned'
                req.rejection_reason = comment or 'Returned for modification.'
                req.save()
                log_history(req, request.user, 'returned_step', comment=comment, step=step, ip=ip)
                log_history(req, request.user, 'returned', ip=ip)
                send_status_notification(req, req.initiator, 'returned')
                messages.info(request, '↩️ Request returned to initiator for modification.')

            elif action == 'comment':
                log_history(req, request.user, 'commented', comment=comment, step=step, ip=ip)
                Notification.objects.create(
                    user=req.initiator, request=req, notif_type='comment',
                    title=f"Comment on {req.reference_number}",
                    message=f"Comment from {request.user.get_full_name()}: {comment}"
                )
                if request.FILES.get('attachment'):
                    step.attachment = request.FILES['attachment']
                    step.save()
                messages.info(request, 'Comment added.')

        return redirect('request_detail', pk=req.pk)

    return render(request, 'workflow_app/approval_action.html', {
        'step': step, 'req': req,
        'steps': req.steps.select_related('approver').order_by('step_number'),
        'history': req.history.select_related('actor').order_by('timestamp'),
    })


# ─── DELEGATE ─────────────────────────────────────────────────────────────────

@login_required
def delegate_approval(request):
    if not request.user.is_approver_role():
        messages.error(request, 'Only approvers can delegate.')
        return redirect('dashboard')

    approvers = User.objects.filter(is_active=True).filter(
        Q(role__in=['approver','chief_manager','sub_manager','manager_operations',
                    'division_head','branch_manager','md'])
    ).exclude(pk=request.user.pk)
    delegation_logs = DelegationLog.objects.filter(
        original_approver=request.user
    ).select_related('acting_approver').order_by('-delegated_at')[:10]

    if request.method == 'POST':
        delegate_to_id = request.POST.get('delegate_to')
        until = request.POST.get('delegate_until')
        authority = request.POST.get('delegation_authority', '')
        if delegate_to_id and until:
            delegate_user = get_object_or_404(User, pk=delegate_to_id)
            request.user.delegate_to = delegate_user
            request.user.delegate_until = until
            request.user.delegation_authority = authority
            request.user.save()
            DelegationLog.objects.create(
                original_approver=request.user,
                acting_approver=delegate_user,
                valid_until=until,
                authority_description=authority,
                is_active=True
            )
            log_history_for_delegate(request.user, delegate_user)
            messages.success(request, f'Delegation set to {delegate_user.get_full_name()} successfully.')
            return redirect('dashboard')

    return render(request, 'workflow_app/delegate.html', {
        'approvers': approvers,
        'delegation_logs': delegation_logs,
        'current_delegate': request.user.delegate_to,
        'delegate_until': request.user.delegate_until,
    })


def log_history_for_delegate(original, acting):
    """Log delegation in all pending steps."""
    pending_steps = ApprovalStep.objects.filter(approver=original, status='pending')
    for step in pending_steps:
        Notification.objects.create(
            user=acting, request=step.request, notif_type='approval_required',
            title=f"Delegated: {step.request.reference_number}",
            message=f"Delegated approval from {original.get_full_name()} — Step {step.step_number}"
        )


@login_required
def revoke_delegation(request):
    if request.method == 'POST':
        request.user.delegate_to = None
        request.user.delegate_until = None
        request.user.delegation_authority = ''
        request.user.save()
        DelegationLog.objects.filter(original_approver=request.user, is_active=True).update(is_active=False)
        messages.success(request, 'Delegation revoked.')
    return redirect('delegate_approval')


# ─── LEAVE MANAGEMENT ─────────────────────────────────────────────────────────

@login_required
@admin_required
def manage_leaves(request):
    leaves = LeaveRecord.objects.select_related('user').order_by('-start_date')
    users = User.objects.filter(is_active=True).order_by('first_name')
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        start = request.POST.get('start_date')
        end = request.POST.get('end_date')
        reason = request.POST.get('reason', '')
        u = get_object_or_404(User, pk=user_id)
        LeaveRecord.objects.create(user=u, start_date=start, end_date=end, reason=reason)
        u.on_leave = True
        u.is_available_for_approval = False
        u.save()
        messages.success(request, f'Leave recorded for {u.get_full_name()}.')
        return redirect('manage_leaves')
    return render(request, 'workflow_app/manage_leaves.html', {'leaves': leaves, 'users': users})


@login_required
@admin_required
def end_leave(request, leave_id):
    leave = get_object_or_404(LeaveRecord, pk=leave_id)
    leave.status = 'ended'
    leave.save()
    leave.user.on_leave = False
    leave.user.is_available_for_approval = True
    leave.user.save()
    messages.success(request, f'Leave ended for {leave.user.get_full_name()}.')
    return redirect('manage_leaves')


# ─── DIVISION MANAGEMENT ─────────────────────────────────────────────────────

@login_required
@admin_required
def manage_divisions(request):
    divisions = Division.objects.annotate(user_count=Count('users')).order_by('name')
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        head_name = request.POST.get('head_name', '').strip()
        description = request.POST.get('description', '')
        if name:
            Division.objects.create(name=name, head_name=head_name, description=description)
            messages.success(request, f'Division "{name}" created.')
            return redirect('manage_divisions')
        messages.error(request, 'Division name is required.')
    return render(request, 'workflow_app/manage_divisions.html', {'divisions': divisions})


@login_required
@admin_required
def edit_division(request, pk):
    div = get_object_or_404(Division, pk=pk)
    if request.method == 'POST':
        div.name = request.POST.get('name', div.name)
        div.head_name = request.POST.get('head_name', div.head_name)
        div.description = request.POST.get('description', div.description)
        div.is_active = request.POST.get('is_active') == 'on'
        div.save()
        messages.success(request, 'Division updated.')
        return redirect('manage_divisions')
    return render(request, 'workflow_app/edit_division.html', {'div': div})


# ─── BRANCH MANAGEMENT ────────────────────────────────────────────────────────

@login_required
@admin_required
def manage_branches(request):
    branches = Branch.objects.select_related('manager').annotate(user_count=Count('users')).order_by('name')
    managers = User.objects.filter(is_active=True, role__in=['branch_manager', 'admin'])
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip()
        address = request.POST.get('address', '')
        manager_id = request.POST.get('manager_id')
        if name:
            b = Branch.objects.create(name=name, code=code, address=address)
            if manager_id:
                b.manager_id = manager_id
                b.save()
            messages.success(request, f'Branch "{name}" created.')
            return redirect('manage_branches')
        messages.error(request, 'Branch name is required.')
    return render(request, 'workflow_app/manage_branches.html', {
        'branches': branches, 'managers': managers
    })


@login_required
@admin_required
def edit_branch(request, pk):
    branch = get_object_or_404(Branch, pk=pk)
    managers = User.objects.filter(is_active=True, role__in=['branch_manager', 'admin'])
    employees = User.objects.filter(branch=branch).order_by('first_name')
    all_users = User.objects.filter(is_active=True).order_by('first_name')
    if request.method == 'POST':
        branch.name = request.POST.get('name', branch.name)
        branch.code = request.POST.get('code', branch.code)
        branch.address = request.POST.get('address', branch.address)
        branch.is_active = request.POST.get('is_active') == 'on'
        manager_id = request.POST.get('manager_id')
        if manager_id:
            branch.manager_id = manager_id
        branch.save()
        # Assign employees
        employee_ids = request.POST.getlist('employee_ids')
        if employee_ids:
            User.objects.filter(pk__in=employee_ids).update(branch=branch)
        messages.success(request, 'Branch updated.')
        return redirect('manage_branches')
    return render(request, 'workflow_app/edit_branch.html', {
        'branch': branch, 'managers': managers,
        'employees': employees, 'all_users': all_users,
    })


# ─── WORKFLOW TEMPLATES ───────────────────────────────────────────────────────

@login_required
@admin_required
def manage_templates(request):
    templates = WorkflowTemplate.objects.select_related('category', 'created_by').prefetch_related('steps').order_by('name')
    categories = ApprovalCategory.objects.filter(is_active=True)
    return render(request, 'workflow_app/manage_templates.html', {
        'templates': templates, 'categories': categories
    })


@login_required
@admin_required
def create_template(request):
    categories = ApprovalCategory.objects.filter(is_active=True)
    approvers = User.objects.filter(is_active=True).filter(
        Q(role__in=['approver','chief_manager','sub_manager','manager_operations',
                    'division_head','branch_manager','md','maker','checker'])
    )
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        category_id = request.POST.get('category')
        description = request.POST.get('description', '')
        approver_ids = request.POST.getlist('approvers')
        roles = request.POST.getlist('approver_roles')
        if not name or not category_id or len(approver_ids) < 2:
            messages.error(request, 'Name, category, and at least 2 approvers are required.')
        else:
            with transaction.atomic():
                tmpl = WorkflowTemplate.objects.create(
                    name=name, category_id=category_id,
                    description=description, created_by=request.user
                )
                for idx, (aid, role) in enumerate(zip(approver_ids, roles), start=1):
                    WorkflowTemplateStep.objects.create(
                        template=tmpl, step_number=idx,
                        default_approver_id=aid, approver_role=role or 'checker'
                    )
            messages.success(request, f'Template "{name}" created.')
            return redirect('manage_templates')
    return render(request, 'workflow_app/create_template.html', {
        'categories': categories, 'approvers': approvers,
        'role_choices': WorkflowTemplateStep.APPROVER_ROLE_CHOICES,
    })


@login_required
def api_template_steps(request, template_id):
    tmpl = get_object_or_404(WorkflowTemplate, pk=template_id)
    steps = [
        {
            'approver_id': s.default_approver.pk if s.default_approver else '',
            'approver_name': s.default_approver.get_full_name() if s.default_approver else '',
            'approver_employee_id': s.default_approver.employee_id if s.default_approver else '',
            'approver_designation': s.default_approver.designation if s.default_approver else '',
            'role': s.approver_role,
            'role_display': s.get_approver_role_display(),
        }
        for s in tmpl.steps.order_by('step_number')
    ]
    return JsonResponse({'steps': steps})


# ─── PDF GENERATION ───────────────────────────────────────────────────────────

@login_required
def generate_pdf(request, pk):
    req = get_object_or_404(ApprovalRequest, pk=pk)
    if req.status not in ['approved', 'payment_pending', 'payment_released']:
        messages.error(request, 'PDF only available for approved requests.')
        return redirect('request_detail', pk=pk)

    # Check access
    is_approver_in_chain = req.steps.filter(approver=request.user).exists()
    if req.initiator != request.user and not is_approver_in_chain and request.user.role != 'admin':
        raise Http404

    pdf_mode = request.GET.get('mode', req.pdf_mode)
    log_history(req, request.user, 'pdf_generated',
                comment=f'PDF generated (mode: {pdf_mode})', ip=get_client_ip(request))

    steps = req.steps.select_related('approver').order_by('step_number')
    history = req.history.select_related('actor').order_by('timestamp')

    return render(request, 'workflow_app/pdf_document.html', {
        'req': req, 'steps': steps, 'history': history,
        'pdf_mode': pdf_mode, 'generated_at': timezone.now(),
    })


# ─── PAYMENT ──────────────────────────────────────────────────────────────────

@login_required
def payment_setup(request, request_id):
    req = get_object_or_404(ApprovalRequest, pk=request_id, status='approved')
    if Payment.objects.filter(request=req).exists():
        messages.info(request, 'Payment already configured.')
        return redirect('request_detail', pk=request_id)

    if request.method == 'POST':
        payment_type = request.POST.get('payment_type')
        total_amount = request.POST.get('total_amount')
        num_installments = int(request.POST.get('number_of_installments', 1))
        notes = request.POST.get('notes', '')
        with transaction.atomic():
            payment = Payment.objects.create(
                request=req, payment_type=payment_type, total_amount=total_amount,
                number_of_installments=num_installments if payment_type == 'partial' else 1,
                initiated_by=request.user, notes=notes,
                payment_reference=f"PAY-{req.reference_number}"
            )
            if payment_type == 'partial':
                for i in range(1, num_installments + 1):
                    PaymentInstallment.objects.create(
                        payment=payment, installment_number=i,
                        amount=request.POST.get(f'installment_amount_{i}', 0),
                        due_date=request.POST.get(f'installment_due_{i}') or None
                    )
            req.status = 'payment_pending'
            req.save()
            log_history(req, request.user, 'payment_initiated',
                        comment=f'{payment_type} payment configured.', ip=get_client_ip(request))
        messages.success(request, 'Payment configured successfully.')
        return redirect('request_detail', pk=request_id)
    return render(request, 'workflow_app/payment_setup.html', {'req': req})


@login_required
def payment_release(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    req = payment.request
    if request.method == 'POST':
        with transaction.atomic():
            if payment.payment_type == 'full':
                payment.status = 'released'
                payment.released_at = timezone.now()
                payment.save()
                req.status = 'payment_released'
                req.save()
                log_history(req, request.user, 'payment_released', ip=get_client_ip(request))
                send_status_notification(req, req.initiator, 'payment_released')
                messages.success(request, 'Full payment released.')
            else:
                messages.info(request, 'Release individual installments.')
    return redirect('request_detail', pk=req.pk)


@login_required
def release_installment(request, payment_id, inst_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    installment = get_object_or_404(PaymentInstallment, pk=inst_id, payment=payment)
    if request.method == 'POST':
        installment.status = 'released'
        installment.released_at = timezone.now()
        installment.save()
        if not payment.installments.filter(status='pending').exists():
            payment.status = 'released'
            payment.released_at = timezone.now()
            payment.save()
            payment.request.status = 'payment_released'
            payment.request.save()
            log_history(payment.request, request.user, 'payment_released', ip=get_client_ip(request))
        messages.success(request, f'Installment {installment.installment_number} released.')
    return redirect('request_detail', pk=payment.request.pk)


# ─── ADMIN VIEWS ──────────────────────────────────────────────────────────────

@login_required
@admin_required
def admin_dashboard(request):
    ctx = {
        'total_users': User.objects.count(),
        'total_requests': ApprovalRequest.objects.count(),
        'pending': ApprovalRequest.objects.filter(status__in=['pending', 'in_progress']).count(),
        'approved': ApprovalRequest.objects.filter(status='approved').count(),
        'rejected': ApprovalRequest.objects.filter(status='rejected').count(),
        'payment_released': ApprovalRequest.objects.filter(status='payment_released').count(),
        'total_divisions': Division.objects.count(),
        'total_branches': Branch.objects.count(),
        'recent_requests': ApprovalRequest.objects.select_related('initiator', 'category').order_by('-created_at')[:15],
        'categories': ApprovalCategory.objects.all(),
        'divisions': Division.objects.all(),
        'sla_breached': [r for r in ApprovalRequest.objects.filter(
            status__in=['pending', 'in_progress'], sla_deadline__isnull=False
        ) if r.is_sla_breached()],
    }
    return render(request, 'workflow_app/admin_dashboard.html', ctx)


@login_required
@admin_required
def manage_users(request):
    q = request.GET.get('q', '')
    role_filter = request.GET.get('role', '')
    division_filter = request.GET.get('division', '')
    users = User.objects.select_related('division', 'branch').order_by('role', 'first_name')
    if q:
        users = users.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(username__icontains=q) | Q(employee_id__icontains=q))
    if role_filter:
        users = users.filter(role=role_filter)
    if division_filter:
        users = users.filter(division_id=division_filter)
    return render(request, 'workflow_app/manage_users.html', {
        'users': users, 'q': q, 'role_filter': role_filter,
        'role_choices': User.ROLE_CHOICES,
        'divisions': Division.objects.filter(is_active=True),
    })


@login_required
@admin_required
def edit_user(request, pk):
    user_obj = get_object_or_404(User, pk=pk)
    divisions = Division.objects.filter(is_active=True)
    branches = Branch.objects.filter(is_active=True)
    if request.method == 'POST':
        user_obj.role = request.POST.get('role', user_obj.role)
        user_obj.designation = request.POST.get('designation', user_obj.designation)
        user_obj.employee_id = request.POST.get('employee_id', user_obj.employee_id) or None
        user_obj.phone = request.POST.get('phone', user_obj.phone)
        user_obj.is_available_for_approval = request.POST.get('is_available_for_approval') == 'on'
        user_obj.is_active = request.POST.get('is_active') == 'on'
        div_id = request.POST.get('division')
        if div_id:
            user_obj.division_id = div_id
        else:
            user_obj.division = None
        branch_id = request.POST.get('branch')
        if branch_id:
            user_obj.branch_id = branch_id
        else:
            user_obj.branch = None
        if request.FILES.get('signature_image'):
            user_obj.signature_image = request.FILES['signature_image']
        user_obj.save()
        messages.success(request, 'User updated.')
        return redirect('manage_users')
    return render(request, 'workflow_app/edit_user.html', {
        'user_obj': user_obj, 'role_choices': User.ROLE_CHOICES,
        'divisions': divisions, 'branches': branches,
    })


@login_required
@admin_required
def audit_trail(request):
    action_filter = request.GET.get('action', '')
    logs = ApprovalHistory.objects.select_related('request', 'actor', 'step').order_by('-timestamp')
    if action_filter:
        logs = logs.filter(action=action_filter)
    return render(request, 'workflow_app/audit_trail.html', {
        'logs': logs[:300], 'action_filter': action_filter,
        'action_choices': ApprovalHistory.ACTION_CHOICES,
    })


@login_required
@admin_required
def sla_monitor(request):
    active_requests = ApprovalRequest.objects.filter(
        status__in=['pending', 'in_progress']
    ).select_related('initiator', 'category', 'branch', 'division')
    breached = [r for r in active_requests if r.is_sla_breached()]
    on_time = [r for r in active_requests if not r.is_sla_breached()]
    return render(request, 'workflow_app/sla_monitor.html', {
        'breached': breached, 'on_time': on_time,
    })


# ─── PROFILE ──────────────────────────────────────────────────────────────────

@login_required
def my_profile(request):
    if request.method == 'POST':
        u = request.user
        u.first_name = request.POST.get('first_name', u.first_name)
        u.last_name = request.POST.get('last_name', u.last_name)
        u.email = request.POST.get('email', u.email)
        u.phone = request.POST.get('phone', u.phone)
        u.designation = request.POST.get('designation', u.designation)
        if request.FILES.get('signature_image'):
            u.signature_image = request.FILES['signature_image']
        pw = request.POST.get('new_password')
        if pw:
            u.set_password(pw)
        u.save()
        messages.success(request, 'Profile updated.')
        return redirect('my_profile')
    return render(request, 'workflow_app/my_profile.html', {'user_obj': request.user})


# ─── API / AJAX ───────────────────────────────────────────────────────────────

@login_required
def api_users(request):
    q = request.GET.get('q', '')
    division_id = request.GET.get('division', '')
    users = User.objects.filter(is_active=True).filter(
        Q(role__in=['approver','chief_manager','sub_manager','manager_operations',
                    'division_head','branch_manager','md','maker','checker'])
    )
    if q:
        users = users.filter(
            Q(username__icontains=q) | Q(first_name__icontains=q) |
            Q(last_name__icontains=q) | Q(employee_id__icontains=q)
        )
    if division_id:
        users = users.filter(division_id=division_id)
    data = [{
        'id': u.pk, 'name': u.get_full_name() or u.username,
        'employee_id': u.employee_id or 'N/A', 'designation': u.designation,
        'division': u.division.name if u.division else '',
        'branch': u.branch.name if u.branch else '',
        'role': u.get_role_display(),
        'available': u.is_available_for_approval and not u.on_leave,
    } for u in users.distinct()[:30]]
    return JsonResponse({'users': data})


@login_required
@require_POST
def mark_notifications_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'status': 'ok'})


@login_required
def request_status_api(request, pk):
    req = get_object_or_404(ApprovalRequest, pk=pk)
    return JsonResponse({
        'status': req.status, 'status_display': req.get_status_display(),
        'current_step': req.current_step, 'total_steps': req.total_steps,
    })


# ─── AI DOCUMENT VALIDATION ───────────────────────────────────────────────────

@login_required
def ai_validate_document(request):
    """AJAX endpoint: validate an uploaded document against a category."""
    if request.method == 'POST':
        uploaded_file = request.FILES.get('document')
        category = request.POST.get('category', '')
        subject = request.POST.get('subject', '')
        if not uploaded_file:
            return JsonResponse({'error': 'No file uploaded.'}, status=400)
        try:
            from .ai_validator import quick_validate
            result = quick_validate(uploaded_file, category, subject)
            return JsonResponse(result)
        except Exception as exc:
            return JsonResponse({'error': str(exc), 'valid': True, 'confidence': 50,
                                 'message': 'Validation skipped (error).', 'matched_keywords': []})
    return JsonResponse({'error': 'POST required.'}, status=405)


# ─── NOTIFICATIONS ────────────────────────────────────────────────────────────

@login_required
def notifications_list(request):
    notifs = request.user.notifications.all().order_by('-created_at')[:50]
    notifs.filter(is_read=False).update(is_read=True)
    return render(request, 'workflow_app/notifications.html', {'notifs': notifs})
# ─── INTERNAL INBOX ───────────────────────────────────────────────────────────

@login_required
def inbox(request):
    from .models import InboxMessage
    folder = request.GET.get('folder', 'inbox')
    if folder == 'sent':
        messages_qs = InboxMessage.objects.filter(
            sender=request.user
        ).select_related('recipient', 'request').order_by('-created_at')
    elif folder == 'starred':
        messages_qs = InboxMessage.objects.filter(
            recipient=request.user, is_starred=True
        ).select_related('sender', 'request').order_by('-created_at')
    else:
        messages_qs = InboxMessage.objects.filter(
            recipient=request.user
        ).select_related('sender', 'request').order_by('-created_at')

    unread_count = InboxMessage.objects.filter(
        recipient=request.user, is_read=False
    ).count()

    return render(request, 'workflow_app/inbox.html', {
        'messages_qs': messages_qs,
        'folder': folder,
        'unread_count': unread_count,
    })


@login_required
def inbox_message_detail(request, pk):
    from .models import InboxMessage
    msg = get_object_or_404(InboxMessage, pk=pk)
    if msg.recipient != request.user and msg.sender != request.user:
        raise Http404
    if msg.recipient == request.user and not msg.is_read:
        msg.is_read = True
        msg.save(update_fields=['is_read'])
    return render(request, 'workflow_app/inbox_detail.html', {'msg': msg})


@login_required
def inbox_compose(request):
    from .models import InboxMessage
    users = User.objects.filter(is_active=True).exclude(pk=request.user.pk).order_by('first_name')
    if request.method == 'POST':
        recipient_id = request.POST.get('recipient')
        subject = request.POST.get('subject', '').strip()
        body = request.POST.get('body', '').strip()
        if recipient_id and subject and body:
            recipient = get_object_or_404(User, pk=recipient_id)
            InboxMessage.objects.create(
                sender=request.user,
                recipient=recipient,
                subject=subject,
                body=body,
            )
            messages.success(request, f'Message sent to {recipient.get_full_name() or recipient.username}.')
            return redirect('inbox')
        messages.error(request, 'Recipient, subject and body are all required.')
    return render(request, 'workflow_app/inbox_compose.html', {'users': users})


@login_required
def inbox_star(request, pk):
    from .models import InboxMessage
    msg = get_object_or_404(InboxMessage, pk=pk, recipient=request.user)
    msg.is_starred = not msg.is_starred
    msg.save(update_fields=['is_starred'])
    return redirect(request.META.get('HTTP_REFERER', '/inbox/'))


@login_required
def inbox_delete(request, pk):
    from .models import InboxMessage
    msg = get_object_or_404(InboxMessage, pk=pk, recipient=request.user)
    msg.delete()
    messages.success(request, 'Message deleted.')
    return redirect('inbox')


@login_required
def inbox_mark_read(request):
    from .models import InboxMessage
    InboxMessage.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return redirect('inbox')


@login_required
def notifications_list(request):
    from .models import Notification
    notifs = Notification.objects.filter(
        user=request.user
    ).order_by('-created_at')[:50]
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return render(request, 'workflow_app/notifications.html', {'notifs': list(notifs)})
