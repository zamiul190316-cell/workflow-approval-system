"""
services.py — Business logic services for the Workflow Approval System
All heavy lifting that doesn't belong in views goes here.
"""
import hashlib
import logging
from datetime import timedelta

from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.conf import settings
from django.db import transaction

logger = logging.getLogger('workflow')


# ─── Email Service ─────────────────────────────────────────────────────────────

class EmailService:
    """Centralised email delivery for all workflow events."""

    FROM = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@trustbankplc.com')
    SITE = getattr(settings, 'SITE_URL', 'http://localhost:8000')

    @classmethod
    def send_approval_request(cls, step):
        """Notify the next approver that action is required."""
        approver = step.approver.get_effective_approver()
        req = step.request
        subject = f'[Action Required] {req.reference_number}: {req.subject}'
        action_url = f'{cls.SITE}/approvals/token/{step.token}/'
        body = (
            f'Dear {approver.get_full_name() or approver.username},\n\n'
            f'A workflow request requires your approval.\n\n'
            f'Reference  : {req.reference_number}\n'
            f'Subject    : {req.subject}\n'
            f'Category   : {req.category.name}\n'
            f'Submitted  : {req.submitted_at.strftime("%d %b %Y %H:%M") if req.submitted_at else "N/A"}\n'
            f'Your Role  : {step.get_approver_role_display()}\n'
            f'Step       : {step.step_number} of {req.total_steps}\n\n'
            f'Action required at:\n{action_url}\n\n'
            f'Trust Bank PLC — Workflow Approval System'
        )
        cls._send(subject, body, [approver.email])

    @classmethod
    def send_status_update(cls, req, recipient, event):
        """Notify initiator / relevant parties of status changes."""
        messages = {
            'approved': (
                f'✅ Fully Approved: {req.reference_number}',
                f'Your request "{req.subject}" has been fully approved.'
            ),
            'rejected': (
                f'❌ Rejected: {req.reference_number}',
                f'Your request "{req.subject}" was rejected.\nReason: {req.rejection_reason}'
            ),
            'returned': (
                f'↩️ Returned: {req.reference_number}',
                f'Your request "{req.subject}" was returned for modification.\nNotes: {req.rejection_reason}'
            ),
            'payment_released': (
                f'💰 Payment Released: {req.reference_number}',
                f'Payment for request "{req.subject}" has been released.'
            ),
            'escalated': (
                f'⚠️ Escalated: {req.reference_number}',
                f'Request "{req.subject}" has been escalated due to SLA breach.'
            ),
        }
        subj, body = messages.get(event, ('Workflow Update', 'Your request has been updated.'))
        detail_url = f'{cls.SITE}/requests/{req.pk}/'
        body += f'\n\nView details: {detail_url}\n\nTrust Bank PLC — Workflow System'
        cls._send(subj, body, [recipient.email])

    @classmethod
    def send_escalation_alert(cls, step, division_head):
        """Alert division head when an approver's SLA is breached."""
        req = step.request
        subject = f'⚠️ SLA Breach Alert: {req.reference_number}'
        body = (
            f'Dear {division_head.get_full_name()},\n\n'
            f'The following approval is overdue:\n\n'
            f'Reference  : {req.reference_number}\n'
            f'Subject    : {req.subject}\n'
            f'Approver   : {step.approver.get_full_name()}\n'
            f'Deadline   : {step.deadline.strftime("%d %b %Y %H:%M") if step.deadline else "N/A"}\n\n'
            f'Please take immediate action.\n\nTrust Bank PLC — SLA Monitor'
        )
        cls._send(subject, body, [division_head.email])

    @classmethod
    def _send(cls, subject, body, recipients):
        valid = [r for r in recipients if r and '@' in r]
        if not valid:
            return
        try:
            send_mail(subject, body, cls.FROM, valid, fail_silently=True)
        except Exception as exc:
            logger.warning('Email send failed: %s', exc)


# ─── Notification Service ──────────────────────────────────────────────────────

class NotificationService:
    """Creates in-app notifications."""

    @classmethod
    def notify(cls, user, req, notif_type, title, message):
        from workflow_app.models import Notification
        Notification.objects.create(
            user=user, request=req,
            notif_type=notif_type,
            title=title, message=message
        )

    @classmethod
    def notify_approval_required(cls, step):
        approver = step.approver.get_effective_approver()
        cls.notify(
            approver, step.request, 'approval_required',
            f'Action Required: {step.request.reference_number}',
            f'Step {step.step_number}/{step.request.total_steps} — {step.request.subject}'
        )

    @classmethod
    def notify_status(cls, req, recipient, event):
        type_map = {
            'approved': 'approved', 'rejected': 'rejected',
            'returned': 'returned', 'payment_released': 'payment',
        }
        title_map = {
            'approved': f'✅ Approved: {req.reference_number}',
            'rejected': f'❌ Rejected: {req.reference_number}',
            'returned': f'↩️ Returned: {req.reference_number}',
            'payment_released': f'💰 Payment Released: {req.reference_number}',
        }
        msg_map = {
            'approved': f'Your request "{req.subject}" was fully approved.',
            'rejected': f'Your request was rejected. Reason: {req.rejection_reason}',
            'returned': f'Your request was returned. Notes: {req.rejection_reason}',
            'payment_released': f'Payment for "{req.subject}" has been released.',
        }
        cls.notify(
            recipient, req,
            type_map.get(event, 'info'),
            title_map.get(event, 'Workflow Update'),
            msg_map.get(event, '')
        )


# ─── Workflow Engine ────────────────────────────────────────────────────────────

class WorkflowEngine:
    """Core workflow processing — advance, reject, return, escalate."""

    @classmethod
    @transaction.atomic
    def advance(cls, step, actor, comment='', ip=None):
        """Mark step approved and move workflow to next step."""
        from workflow_app.models import ApprovalHistory, DigitalSignature
        step.status = 'approved'
        step.comment = comment
        step.action_taken_at = timezone.now()
        if step.approver != actor:
            step.acting_approver = actor
        step.save()

        # Digital signature hash
        raw = f'{step.pk}{actor.pk}{step.action_taken_at}{comment}'
        DigitalSignature.objects.get_or_create(
            step=step,
            defaults={
                'user': actor,
                'signature_hash': hashlib.sha256(raw.encode()).hexdigest(),
                'ip_address': ip,
            }
        )

        ApprovalHistory.objects.create(
            request=step.request, step=step, actor=actor,
            action='approved_step', comment=comment, ip_address=ip
        )

        req = step.request
        if step.step_number >= req.total_steps:
            cls._complete(req, actor, ip)
        else:
            req.status = 'in_progress'
            req.current_step = step.step_number + 1
            req.save()
            next_step = req.steps.filter(step_number=req.current_step).first()
            if next_step:
                EmailService.send_approval_request(next_step)
                NotificationService.notify_approval_required(next_step)

    @classmethod
    def _complete(cls, req, actor, ip):
        from workflow_app.models import ApprovalHistory
        req.status = 'approved'
        req.completed_at = timezone.now()
        req.save()
        ApprovalHistory.objects.create(
            request=req, actor=actor,
            action='fully_approved', ip_address=ip
        )
        EmailService.send_status_update(req, req.initiator, 'approved')
        NotificationService.notify_status(req, req.initiator, 'approved')

    @classmethod
    @transaction.atomic
    def reject(cls, step, actor, comment, ip=None):
        from workflow_app.models import ApprovalHistory
        step.status = 'rejected'
        step.comment = comment
        step.action_taken_at = timezone.now()
        if step.approver != actor:
            step.acting_approver = actor
        step.save()
        req = step.request
        req.status = 'rejected'
        req.rejection_reason = comment or 'No reason provided.'
        req.save()
        ApprovalHistory.objects.create(
            request=req, step=step, actor=actor,
            action='rejected_step', comment=comment, ip_address=ip
        )
        ApprovalHistory.objects.create(
            request=req, actor=actor, action='rejected', ip_address=ip
        )
        EmailService.send_status_update(req, req.initiator, 'rejected')
        NotificationService.notify_status(req, req.initiator, 'rejected')

    @classmethod
    @transaction.atomic
    def return_to_initiator(cls, step, actor, comment, ip=None):
        from workflow_app.models import ApprovalHistory
        step.status = 'returned'
        step.comment = comment
        step.action_taken_at = timezone.now()
        if step.approver != actor:
            step.acting_approver = actor
        step.save()
        req = step.request
        req.status = 'returned'
        req.rejection_reason = comment or 'Returned for modification.'
        req.save()
        ApprovalHistory.objects.create(
            request=req, step=step, actor=actor,
            action='returned_step', comment=comment, ip_address=ip
        )
        EmailService.send_status_update(req, req.initiator, 'returned')
        NotificationService.notify_status(req, req.initiator, 'returned')

    @classmethod
    @transaction.atomic
    def escalate(cls, step, actor, comment, ip=None):
        """Escalate an overdue step to the division head."""
        from workflow_app.models import ApprovalHistory, User
        ApprovalHistory.objects.create(
            request=step.request, step=step, actor=actor,
            action='commented', comment=f'ESCALATED: {comment}', ip_address=ip
        )
        # Notify division head of the approver
        if step.approver.division:
            heads = User.objects.filter(
                division=step.approver.division,
                role='division_head', is_active=True
            )
            for head in heads:
                EmailService.send_escalation_alert(step, head)
                NotificationService.notify(
                    head, step.request, 'info',
                    f'⚠️ Escalation: {step.request.reference_number}',
                    f'Approval by {step.approver.get_full_name()} is overdue.'
                )


# ─── SLA Service ───────────────────────────────────────────────────────────────

class SLAService:
    """SLA monitoring and automated escalation."""

    @classmethod
    def check_and_escalate_all(cls):
        """
        Called periodically (e.g. cron / management command).
        Finds all breached pending steps and escalates.
        """
        from workflow_app.models import ApprovalStep, User
        now = timezone.now()
        breached = ApprovalStep.objects.filter(
            status='pending',
            deadline__lt=now,
        ).select_related('request', 'approver', 'approver__division')

        escalated = 0
        for step in breached:
            if step.approver.division:
                heads = User.objects.filter(
                    division=step.approver.division,
                    role='division_head', is_active=True
                )
                for head in heads:
                    EmailService.send_escalation_alert(step, head)
                escalated += 1
        return escalated

    @classmethod
    def get_sla_stats(cls):
        from workflow_app.models import ApprovalRequest
        now = timezone.now()
        active = ApprovalRequest.objects.filter(status__in=['pending', 'in_progress'])
        breached = [r for r in active if r.sla_deadline and r.sla_deadline < now]
        on_time = [r for r in active if not (r.sla_deadline and r.sla_deadline < now)]
        return {'breached': breached, 'on_time': on_time, 'total_active': active.count()}


# ─── Digital Signature Service ─────────────────────────────────────────────────

class SignatureService:
    """Generate and verify digital signature hashes."""

    @classmethod
    def generate_hash(cls, step, actor):
        raw = f'{step.pk}:{actor.pk}:{actor.employee_id}:{step.request.reference_number}:{timezone.now().isoformat()}'
        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    def verify(cls, signature_obj):
        """Basic tamper check — returns True if hash format is valid."""
        h = signature_obj.signature_hash
        return isinstance(h, str) and len(h) == 64 and all(c in '0123456789abcdef' for c in h)
