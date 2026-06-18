# ══════════════════════════════════════════════════════════════════
# PASTE THIS AT THE VERY BOTTOM OF:
# workflow_app/models.py
# DO NOT DELETE OR CHANGE ANYTHING ABOVE THIS
# ══════════════════════════════════════════════════════════════════


class ApprovalGroup(models.Model):
    """Approval committee group — any member can act on group steps."""
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
    """Links an ApprovalStep to an ApprovalGroup (group approval mode)."""
    step = models.OneToOneField(
        ApprovalStep, on_delete=models.CASCADE, related_name='group_assignment'
    )
    group = models.ForeignKey(
        ApprovalGroup, on_delete=models.PROTECT, related_name='assigned_steps'
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Step {self.step.pk} → {self.group.name}'

    class Meta:
        db_table = 'workflow_step_groups'


class GroupApprovalLog(models.Model):
    """Records which group member took action on a group step."""
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
    """Every approval action per user — powers My Completed Tasks."""
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
        return f'{self.user} {self.action} — {self.request.reference_number}'

    class Meta:
        db_table = 'workflow_user_task_history'
        ordering = ['-acted_at']
