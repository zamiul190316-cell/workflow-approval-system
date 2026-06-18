from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import uuid
import os


# ─── DIVISION ─────────────────────────────────────────────────────────────────

class Division(models.Model):
    name = models.CharField(max_length=150, unique=True)
    head_name = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'workflow_divisions'
        ordering = ['name']


# ─── BRANCH ───────────────────────────────────────────────────────────────────

class Branch(models.Model):
    name = models.CharField(max_length=150, unique=True)
    code = models.CharField(max_length=20, unique=True, blank=True)
    address = models.TextField(blank=True)
    manager = models.ForeignKey(
        'User', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='managed_branches'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'workflow_branches'
        ordering = ['name']
        verbose_name_plural = 'Branches'


# ─── USER MODEL ───────────────────────────────────────────────────────────────

def signature_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    return f'signatures/{instance.employee_id or "user"}{ext}'


class User(AbstractUser):
    ROLE_CHOICES = [
        ('initiator', 'Initiator'),
        ('approver', 'Approver'),
        ('chief_manager', 'Chief Manager'),
        ('sub_manager', 'Sub Manager'),
        ('manager_operations', 'Manager Operations'),
        ('division_head', 'Division Head'),
        ('branch_manager', 'Branch Manager'),
        ('md', 'Managing Director'),
        ('admin', 'Administrator'),
        ('maker', 'Maker'),
        ('checker', 'Checker'),
    ]

    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='initiator')
    employee_id = models.CharField(max_length=20, unique=True, blank=True, null=True)
    designation = models.CharField(max_length=100, blank=True)
    division = models.ForeignKey(
        Division, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='users'
    )
    branch = models.ForeignKey(
        Branch, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='users'
    )
    phone = models.CharField(max_length=20, blank=True)
    signature_image = models.ImageField(
        upload_to=signature_upload_path,
        null=True, blank=True
    )
    is_available_for_approval = models.BooleanField(default=True)
    on_leave = models.BooleanField(default=False)
    delegate_to = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='delegated_from'
    )
    delegate_until = models.DateTimeField(null=True, blank=True)
    delegation_authority = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    department = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.employee_id or 'N/A'})"

    def get_effective_approver(self):
        if (self.delegate_to and self.delegate_until
                and timezone.now() < self.delegate_until):
            return self.delegate_to
        return self

    def is_approver_role(self):
        return self.role in [
            'approver', 'chief_manager', 'sub_manager',
            'manager_operations', 'division_head',
            'branch_manager', 'md', 'maker', 'checker'
        ]

    class Meta:
        db_table = 'workflow_users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'


# ─── LEAVE MANAGEMENT ─────────────────────────────────────────────────────────

class LeaveRecord(models.Model):
    STATUS_CHOICES = [
        ('active', 'On Leave'),
        ('ended', 'Leave Ended'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='leave_records')
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} leave {self.start_date} to {self.end_date}"

    class Meta:
        db_table = 'workflow_leaves'
        ordering = ['-start_date']


# ─── DELEGATION LOG ───────────────────────────────────────────────────────────

class DelegationLog(models.Model):
    original_approver = models.ForeignKey(
        User, on_delete=models.PROTECT,
        related_name='delegation_logs_as_original'
    )
    acting_approver = models.ForeignKey(
        User, on_delete=models.PROTECT,
        related_name='delegation_logs_as_acting'
    )
    delegated_at = models.DateTimeField(auto_now_add=True)
    valid_until = models.DateTimeField()
    authority_description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.original_approver} → {self.acting_approver}"

    class Meta:
        db_table = 'workflow_delegation_logs'
        ordering = ['-delegated_at']


# ─── APPROVAL CATEGORIES ──────────────────────────────────────────────────────

class ApprovalCategory(models.Model):
    CATEGORY_GROUP_CHOICES = [
        ('financial', 'Financial Approvals'),
        ('employee_benefits', 'Employee Benefits'),
        ('operational', 'Operational Approvals'),
        ('administrative', 'Administrative'),
    ]
    group = models.CharField(max_length=30, choices=CATEGORY_GROUP_CHOICES)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    min_approvers = models.PositiveIntegerField(default=2)
    max_approvers = models.PositiveIntegerField(default=50)
    required_division = models.ForeignKey(
        Division, null=True, blank=True,
        on_delete=models.SET_NULL,
        help_text='At least N approvers must be from this division'
    )
    min_required_from_division = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.get_group_display()} → {self.name}"

    class Meta:
        db_table = 'workflow_categories'
        verbose_name_plural = 'Approval Categories'
        ordering = ['group', 'name']


# ─── WORKFLOW TEMPLATE ────────────────────────────────────────────────────────

class WorkflowTemplate(models.Model):
    name = models.CharField(max_length=150)
    category = models.ForeignKey(
        ApprovalCategory, on_delete=models.CASCADE,
        related_name='templates'
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT,
        related_name='created_templates'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'workflow_templates'


class WorkflowTemplateStep(models.Model):
    APPROVER_ROLE_CHOICES = [
        ('maker', 'Maker'), ('checker', 'Checker'),
        ('branch_approval', 'Branch Approval'), ('head_office', 'Head Office'),
        ('cfo', 'CFO'), ('ceo', 'CEO'), ('board', 'Board'),
        ('compliance', 'Compliance Officer'), ('legal', 'Legal Advisor'),
        ('custom', 'Custom Role'),
    ]
    template = models.ForeignKey(WorkflowTemplate, on_delete=models.CASCADE, related_name='steps')
    step_number = models.PositiveIntegerField()
    default_approver = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='template_steps')
    approver_role = models.CharField(max_length=30, choices=APPROVER_ROLE_CHOICES)
    role_label = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = 'workflow_template_steps'
        ordering = ['step_number']
        unique_together = ['template', 'step_number']


# ─── APPROVAL REQUEST ─────────────────────────────────────────────────────────

def attachment_upload_path(instance, filename):
    return f'attachments/{instance.reference_number}/{filename}'


class ApprovalRequest(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('in_progress', 'In Progress'),
        ('approved', 'Fully Approved'),
        ('rejected', 'Rejected'),
        ('returned', 'Returned for Modification'),
        ('payment_pending', 'Payment Pending'),
        ('payment_released', 'Payment Released'),
    ]
    PDF_MODE_CHOICES = [
        ('system', 'System Generated'),
        ('manual', 'Manual Signature Print'),
        ('digital', 'Digital Signature PDF'),
    ]

    reference_number = models.CharField(max_length=20, unique=True, editable=False)
    version = models.PositiveIntegerField(default=1)
    date = models.DateField(auto_now_add=True)
    subject = models.CharField(max_length=255)
    description = models.TextField()
    category = models.ForeignKey(ApprovalCategory, on_delete=models.PROTECT, related_name='requests')
    amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=10, default='BDT')
    initiator = models.ForeignKey(User, on_delete=models.PROTECT, related_name='initiated_requests')
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL, related_name='requests')
    division = models.ForeignKey(Division, null=True, blank=True, on_delete=models.SET_NULL, related_name='requests')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    current_step = models.PositiveIntegerField(default=1)
    total_steps = models.PositiveIntegerField(default=1)
    rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    sla_deadline = models.DateTimeField(null=True, blank=True)
    attachments_note = models.TextField(blank=True)
    attachment_file = models.FileField(upload_to='attachments/', null=True, blank=True)
    PRIORITY_CHOICES = [
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    pdf_mode = models.CharField(max_length=20, choices=PDF_MODE_CHOICES, default='system')
    audit_id = models.UUIDField(default=uuid.uuid4, unique=True)

    def save(self, *args, **kwargs):
        if not self.reference_number:
            self.reference_number = self._generate_ref()
        super().save(*args, **kwargs)

    def _generate_ref(self):
        year = timezone.now().year
        count = ApprovalRequest.objects.filter(created_at__year=year).count() + 1
        return f"REF-{year}-{count:05d}"

    def get_current_approver_step(self):
        return self.steps.filter(step_number=self.current_step, status='pending').first()

    def is_sla_breached(self):
        return bool(self.sla_deadline and timezone.now() > self.sla_deadline)

    def __str__(self):
        return f"{self.reference_number} - {self.subject}"

    class Meta:
        db_table = 'workflow_requests'
        ordering = ['-created_at']


class RequestVersion(models.Model):
    request = models.ForeignKey(ApprovalRequest, on_delete=models.CASCADE, related_name='versions')
    version_number = models.PositiveIntegerField()
    subject = models.CharField(max_length=255)
    description = models.TextField()
    status_snapshot = models.CharField(max_length=20)
    saved_at = models.DateTimeField(auto_now_add=True)
    saved_by = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        db_table = 'workflow_request_versions'
        ordering = ['version_number']


# ─── APPROVAL STEP ────────────────────────────────────────────────────────────

class ApprovalStep(models.Model):
    APPROVER_ROLE_CHOICES = [
        ('maker', 'Maker'), ('checker', 'Checker'),
        ('branch_approval', 'Branch Approval'), ('head_office', 'Head Office'),
        ('cfo', 'CFO'), ('ceo', 'CEO'), ('board', 'Board'),
        ('compliance', 'Compliance Officer'), ('legal', 'Legal Advisor'),
        ('custom', 'Custom Role'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'), ('approved', 'Approved'),
        ('rejected', 'Rejected'), ('returned', 'Returned'),
        ('skipped', 'Skipped'), ('delegated', 'Delegated'),
    ]

    request = models.ForeignKey(ApprovalRequest, on_delete=models.CASCADE, related_name='steps')
    step_number = models.PositiveIntegerField()
    approver = models.ForeignKey(User, on_delete=models.PROTECT, related_name='approval_steps')
    acting_approver = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='acting_approval_steps'
    )
    approver_role = models.CharField(max_length=30, choices=APPROVER_ROLE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    comment = models.TextField(blank=True)
    attachment = models.FileField(upload_to='step_attachments/', null=True, blank=True)
    action_taken_at = models.DateTimeField(null=True, blank=True)
    deadline = models.DateTimeField(null=True, blank=True)
    email_sent = models.BooleanField(default=False)
    token = models.UUIDField(default=uuid.uuid4, unique=True)

    def __str__(self):
        return f"Step {self.step_number} - {self.request.reference_number} - {self.approver}"

    class Meta:
        db_table = 'workflow_steps'
        ordering = ['step_number']
        unique_together = ['request', 'step_number']


# ─── APPROVAL HISTORY (AUDIT TRAIL) ──────────────────────────────────────────

class ApprovalHistory(models.Model):
    ACTION_CHOICES = [
        ('created', 'Request Created'),
        ('submitted', 'Submitted for Approval'),
        ('approved_step', 'Step Approved'),
        ('rejected_step', 'Step Rejected'),
        ('returned_step', 'Returned for Modification'),
        ('fully_approved', 'Fully Approved'),
        ('rejected', 'Request Rejected'),
        ('returned', 'Returned to Initiator'),
        ('resubmitted', 'Resubmitted'),
        ('payment_initiated', 'Payment Initiated'),
        ('payment_released', 'Payment Released'),
        ('email_sent', 'Email Notification Sent'),
        ('delegated', 'Approval Delegated'),
        ('commented', 'Comment Added'),
        ('pdf_generated', 'PDF Generated'),
        ('approver_added', 'Approver Added Dynamically'),
        ('approver_removed', 'Approver Removed'),
    ]

    request = models.ForeignKey(ApprovalRequest, on_delete=models.CASCADE, related_name='history')
    step = models.ForeignKey(ApprovalStep, on_delete=models.SET_NULL, null=True, blank=True, related_name='history_entries')
    actor = models.ForeignKey(User, on_delete=models.PROTECT, related_name='actions')
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    comment = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.request.reference_number} - {self.action} by {self.actor}"

    class Meta:
        db_table = 'workflow_history'
        ordering = ['-timestamp']


# ─── DIGITAL SIGNATURE ────────────────────────────────────────────────────────

class DigitalSignature(models.Model):
    step = models.OneToOneField(ApprovalStep, on_delete=models.CASCADE, related_name='digital_signature')
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    signed_at = models.DateTimeField(auto_now_add=True)
    signature_hash = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = 'workflow_digital_signatures'


# ─── PAYMENT ──────────────────────────────────────────────────────────────────

class Payment(models.Model):
    PAYMENT_TYPE_CHOICES = [('full', 'Full Payment'), ('partial', 'Partial Payment (Installments)')]
    STATUS_CHOICES = [('pending', 'Pending'), ('processing', 'Processing'), ('released', 'Released'), ('failed', 'Failed')]

    request = models.OneToOneField(ApprovalRequest, on_delete=models.CASCADE, related_name='payment')
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=10, default='BDT')
    number_of_installments = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    initiated_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='initiated_payments')
    created_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Payment for {self.request.reference_number}"

    class Meta:
        db_table = 'workflow_payments'


class PaymentInstallment(models.Model):
    STATUS_CHOICES = [('pending', 'Pending'), ('released', 'Released')]
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='installments')
    installment_number = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    released_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Installment {self.installment_number} of {self.payment}"

    class Meta:
        db_table = 'workflow_installments'
        ordering = ['installment_number']


# ─── NOTIFICATION ─────────────────────────────────────────────────────────────

class Notification(models.Model):
    NOTIF_TYPE_CHOICES = [
        ('approval_required', 'Approval Required'), ('approved', 'Approved'),
        ('rejected', 'Rejected'), ('returned', 'Returned for Correction'),
        ('completed', 'Workflow Completed'), ('comment', 'Comment Added'),
        ('payment', 'Payment Update'), ('info', 'Information'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    request = models.ForeignKey(ApprovalRequest, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    notif_type = models.CharField(max_length=30, choices=NOTIF_TYPE_CHOICES, default='info')
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notification for {self.user}: {self.title}"

    class Meta:
        db_table = 'workflow_notifications'
        ordering = ['-created_at']
        # ─── INTERNAL MAIL INBOX ──────────────────────────────────────────────────────

class InboxMessage(models.Model):
    sender     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_messages')
    recipient  = models.ForeignKey(User, on_delete=models.CASCADE, related_name='inbox_messages')
    subject    = models.CharField(max_length=255)
    body       = models.TextField()
    request    = models.ForeignKey(ApprovalRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name='inbox_messages')
    is_read    = models.BooleanField(default=False)
    is_starred = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'To: {self.recipient} | {self.subject}'

    class Meta:
        db_table = 'workflow_inbox'
        ordering = ['-created_at']
        # ─── APPROVAL GROUP ───────────────────────────────────────────────────────────

class ApprovalGroup(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    division = models.ForeignKey(
        Division, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='approval_groups'
    )
    owner = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='owned_groups'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def get_active_members(self):
        return self.members.filter(is_active=True).select_related('user')

    class Meta:
        db_table = 'workflow_approval_groups'
        ordering = ['name']


class ApprovalGroupMember(models.Model):
    group = models.ForeignKey(
        ApprovalGroup, on_delete=models.CASCADE, related_name='members'
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='group_memberships'
    )
    is_active = models.BooleanField(default=True)
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.get_full_name()} in {self.group.name}'

    class Meta:
        db_table = 'workflow_group_members'
        unique_together = ['group', 'user']


class ApprovalStepGroup(models.Model):
    step = models.OneToOneField(
        ApprovalStep, on_delete=models.CASCADE, related_name='group_assignment'
    )
    group = models.ForeignKey(
        ApprovalGroup, on_delete=models.PROTECT, related_name='assigned_steps'
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Step {self.step.pk} to {self.group.name}'

    class Meta:
        db_table = 'workflow_step_groups'


class GroupApprovalLog(models.Model):
    ACTION_CHOICES = [
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('returned', 'Returned to Initiator'),
        ('modification_requested', 'Modification Requested'),
        ('commented', 'Comment Added'),
    ]
    step = models.ForeignKey(
        ApprovalStep, on_delete=models.CASCADE, related_name='group_logs'
    )
    group = models.ForeignKey(
        ApprovalGroup, on_delete=models.PROTECT, related_name='approval_logs'
    )
    actor = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='group_approval_actions'
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    comment = models.TextField(blank=True)
    attachment = models.FileField(
        upload_to='group_step_attachments/', null=True, blank=True
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    acted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.actor} {self.action} on step {self.step.pk}'

    class Meta:
        db_table = 'workflow_group_approval_logs'
        ordering = ['-acted_at']


class UserTaskHistory(models.Model):
    ACTION_CHOICES = [
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('returned', 'Returned to Initiator'),
        ('modification_requested', 'Modification Requested'),
        ('commented', 'Comment Added'),
        ('delegated', 'Delegated'),
    ]
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='task_history'
    )
    request = models.ForeignKey(
        ApprovalRequest, on_delete=models.CASCADE, related_name='task_history'
    )
    step = models.ForeignKey(
        ApprovalStep, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='task_history'
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    comment = models.TextField(blank=True)
    has_attachment = models.BooleanField(default=False)
    via_group = models.ForeignKey(
        ApprovalGroup, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='task_history'
    )
    acted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user} {self.action} on {self.request.reference_number}'

    class Meta:
        db_table = 'workflow_user_task_history'
        ordering = ['-acted_at']
