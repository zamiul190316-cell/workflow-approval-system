"""
middleware.py — Custom middleware for the Workflow Approval System
"""
import logging
from django.utils import timezone
from django.shortcuts import redirect
from django.urls import reverse

logger = logging.getLogger('workflow')


class WorkflowAuditMiddleware:
    """
    Logs every state-changing request (POST) to the Python logger.
    The actual DB audit trail is handled in views.py via log_history().
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (request.method == 'POST' and
                request.user.is_authenticated and
                response.status_code in (200, 302)):
            logger.info(
                'ACTION | user=%s | path=%s | ip=%s | status=%s',
                request.user.username,
                request.path,
                self._get_ip(request),
                response.status_code,
            )
        return response

    @staticmethod
    def _get_ip(request):
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        return xff.split(',')[0] if xff else request.META.get('REMOTE_ADDR', '')


class LeaveCheckMiddleware:
    """
    Auto-updates user.on_leave status based on active LeaveRecord dates.
    Runs once per authenticated request (cheap: single DB query).
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self._skip_paths = {'/login/', '/logout/', '/static/', '/media/'}

    def __call__(self, request):
        if (request.user.is_authenticated and
                not any(request.path.startswith(p) for p in self._skip_paths)):
            self._sync_leave_status(request.user)
        return self.get_response(request)

    @staticmethod
    def _sync_leave_status(user):
        from workflow_app.models import LeaveRecord
        today = timezone.now().date()
        on_leave = LeaveRecord.objects.filter(
            user=user, status='active',
            start_date__lte=today, end_date__gte=today
        ).exists()
        if user.on_leave != on_leave:
            user.on_leave = on_leave
            user.is_available_for_approval = not on_leave
            user.save(update_fields=['on_leave', 'is_available_for_approval'])


class SLAEscalationMiddleware:
    """
    Checks for SLA breaches on every authenticated request and fires
    escalation notifications (at most once per request).
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.method == 'GET':
            self._check_escalations(request.user)
        return self.get_response(request)

    @staticmethod
    def _check_escalations(user):
        from workflow_app.models import ApprovalStep, Notification
        now = timezone.now()
        breached = ApprovalStep.objects.filter(
            approver=user,
            status='pending',
            deadline__lt=now,
        ).select_related('request')[:5]

        for step in breached:
            already_notified = Notification.objects.filter(
                user=user,
                request=step.request,
                notif_type='info',
                title__startswith='⚠️ SLA',
                created_at__date=now.date(),
            ).exists()
            if not already_notified:
                Notification.objects.create(
                    user=user,
                    request=step.request,
                    notif_type='info',
                    title=f'⚠️ SLA Breached: {step.request.reference_number}',
                    message=(
                        f'Your approval for "{step.request.subject}" '
                        f'is overdue. Deadline was {step.deadline.strftime("%d %b %Y %H:%M")}.'
                    ),
                )
