from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, Division, Branch, ApprovalCategory, ApprovalRequest,
    ApprovalStep, ApprovalHistory, WorkflowTemplate, WorkflowTemplateStep,
    LeaveRecord, DelegationLog, Payment, PaymentInstallment,
    Notification, DigitalSignature, RequestVersion
)


@admin.register(Division)
class DivisionAdmin(admin.ModelAdmin):
    list_display = ['name', 'head_name', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'head_name']


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'manager', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'code']
    raw_id_fields = ['manager']


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'get_full_name', 'employee_id', 'role', 'division', 'branch', 'on_leave', 'is_active']
    list_filter = ['role', 'division', 'branch', 'on_leave', 'is_active']
    search_fields = ['username', 'first_name', 'last_name', 'employee_id', 'email']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Staff Profile', {
            'fields': ('role', 'employee_id', 'designation', 'phone',
                       'division', 'branch', 'signature_image',
                       'is_available_for_approval', 'on_leave',
                       'delegate_to', 'delegate_until', 'delegation_authority')
        }),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Staff Profile', {'fields': ('role', 'employee_id', 'designation', 'division', 'branch')}),
    )


@admin.register(ApprovalCategory)
class ApprovalCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'group', 'min_approvers', 'max_approvers', 'required_division', 'is_active']
    list_filter = ['group', 'is_active', 'required_division']
    search_fields = ['name']


class ApprovalStepInline(admin.TabularInline):
    model = ApprovalStep
    extra = 0
    readonly_fields = ['token', 'action_taken_at', 'email_sent']


class ApprovalHistoryInline(admin.TabularInline):
    model = ApprovalHistory
    extra = 0
    readonly_fields = ['timestamp', 'actor', 'action', 'comment', 'ip_address']
    can_delete = False


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ['reference_number', 'subject', 'initiator', 'category', 'status',
                    'current_step', 'total_steps', 'created_at']
    list_filter = ['status', 'category', 'branch', 'division', 'pdf_mode']
    search_fields = ['reference_number', 'subject', 'initiator__username', 'initiator__first_name']
    readonly_fields = ['reference_number', 'audit_id', 'created_at', 'updated_at']
    inlines = [ApprovalStepInline, ApprovalHistoryInline]
    date_hierarchy = 'created_at'


@admin.register(ApprovalStep)
class ApprovalStepAdmin(admin.ModelAdmin):
    list_display = ['request', 'step_number', 'approver', 'approver_role', 'status', 'action_taken_at']
    list_filter = ['status', 'approver_role']
    search_fields = ['request__reference_number', 'approver__username']
    readonly_fields = ['token', 'action_taken_at']


@admin.register(ApprovalHistory)
class ApprovalHistoryAdmin(admin.ModelAdmin):
    list_display = ['request', 'actor', 'action', 'timestamp', 'ip_address']
    list_filter = ['action']
    search_fields = ['request__reference_number', 'actor__username']
    readonly_fields = ['timestamp']
    date_hierarchy = 'timestamp'


@admin.register(LeaveRecord)
class LeaveRecordAdmin(admin.ModelAdmin):
    list_display = ['user', 'start_date', 'end_date', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['user__username', 'user__first_name']


@admin.register(DelegationLog)
class DelegationLogAdmin(admin.ModelAdmin):
    list_display = ['original_approver', 'acting_approver', 'delegated_at', 'valid_until', 'is_active']
    list_filter = ['is_active']


@admin.register(WorkflowTemplate)
class WorkflowTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'created_by', 'is_active', 'created_at']
    list_filter = ['is_active', 'category']
    search_fields = ['name']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['request', 'payment_type', 'total_amount', 'currency', 'status', 'created_at']
    list_filter = ['status', 'payment_type']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'notif_type', 'is_read', 'created_at']
    list_filter = ['notif_type', 'is_read']
    search_fields = ['user__username', 'title']


@admin.register(DigitalSignature)
class DigitalSignatureAdmin(admin.ModelAdmin):
    list_display = ['step', 'user', 'signed_at', 'ip_address']
    readonly_fields = ['signature_hash', 'signed_at']
