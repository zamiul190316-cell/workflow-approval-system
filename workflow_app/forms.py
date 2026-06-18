"""
forms.py — All Django forms for the Workflow Approval System
"""
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from .models import (
    User, ApprovalRequest, ApprovalStep, ApprovalCategory,
    Division, Branch, WorkflowTemplate, WorkflowTemplateStep,
    LeaveRecord, DelegationLog, Payment, PaymentInstallment
)


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username or Employee ID'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'})
    )


class UserRegistrationForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}),
        min_length=6
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm Password'})
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'employee_id',
                  'designation', 'phone', 'role', 'division', 'branch']
        widgets = {
            'username':    forms.TextInput(attrs={'class': 'form-control'}),
            'first_name':  forms.TextInput(attrs={'class': 'form-control'}),
            'last_name':   forms.TextInput(attrs={'class': 'form-control'}),
            'email':       forms.EmailInput(attrs={'class': 'form-control'}),
            'employee_id': forms.TextInput(attrs={'class': 'form-control'}),
            'designation': forms.TextInput(attrs={'class': 'form-control'}),
            'phone':       forms.TextInput(attrs={'class': 'form-control'}),
            'role':        forms.Select(attrs={'class': 'form-control'}),
            'division':    forms.Select(attrs={'class': 'form-control'}),
            'branch':      forms.Select(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password') != cleaned.get('confirm_password'):
            raise forms.ValidationError('Passwords do not match.')
        return cleaned


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'employee_id', 'designation',
                  'phone', 'role', 'division', 'branch', 'is_active',
                  'is_available_for_approval', 'signature_image']
        widgets = {
            'first_name':               forms.TextInput(attrs={'class': 'form-control'}),
            'last_name':                forms.TextInput(attrs={'class': 'form-control'}),
            'email':                    forms.EmailInput(attrs={'class': 'form-control'}),
            'employee_id':              forms.TextInput(attrs={'class': 'form-control'}),
            'designation':              forms.TextInput(attrs={'class': 'form-control'}),
            'phone':                    forms.TextInput(attrs={'class': 'form-control'}),
            'role':                     forms.Select(attrs={'class': 'form-control'}),
            'division':                 forms.Select(attrs={'class': 'form-control'}),
            'branch':                   forms.Select(attrs={'class': 'form-control'}),
            'is_active':                forms.CheckboxInput(),
            'is_available_for_approval':forms.CheckboxInput(),
            'signature_image':          forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }


class ApprovalRequestForm(forms.ModelForm):
    class Meta:
        model = ApprovalRequest
        fields = ['subject', 'description', 'category', 'amount', 'currency',
                  'branch', 'division', 'attachments_note', 'attachment_file', 'pdf_mode', 'priority']
        widgets = {
            'subject':         forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Brief subject'}),
            'description':     forms.Textarea(attrs={'class': 'form-control', 'rows': 6}),
            'category':        forms.Select(attrs={'class': 'form-control'}),
            'amount':          forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'currency':        forms.Select(attrs={'class': 'form-control'}),
            'branch':          forms.Select(attrs={'class': 'form-control'}),
            'division':        forms.Select(attrs={'class': 'form-control'}),
            'attachments_note':forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'attachment_file': forms.FileInput(attrs={'class': 'form-control'}),
            'pdf_mode':        forms.Select(attrs={'class': 'form-control'}),
            'priority':        forms.Select(attrs={'class': 'form-control'}),
        }


class ApprovalActionForm(forms.Form):
    ACTION_CHOICES = [
        ('approve',  'Approve'),
        ('reject',   'Reject'),
        ('return',   'Return for Modification'),
        ('comment',  'Add Comment Only'),
        ('escalate', 'Escalate'),
    ]
    action = forms.ChoiceField(choices=ACTION_CHOICES)
    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Add comment...'})
    )
    attachment = forms.FileField(required=False, widget=forms.FileInput(attrs={'class': 'form-control'}))


class DivisionForm(forms.ModelForm):
    class Meta:
        model = Division
        fields = ['name', 'head_name', 'description', 'is_active']
        widgets = {
            'name':        forms.TextInput(attrs={'class': 'form-control'}),
            'head_name':   forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active':   forms.CheckboxInput(),
        }


class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = ['name', 'code', 'address', 'manager', 'is_active']
        widgets = {
            'name':    forms.TextInput(attrs={'class': 'form-control'}),
            'code':    forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'manager': forms.Select(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(),
        }


class LeaveRecordForm(forms.ModelForm):
    class Meta:
        model = LeaveRecord
        fields = ['user', 'start_date', 'end_date', 'reason']
        widgets = {
            'user':       forms.Select(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date':   forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reason':     forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class DelegationForm(forms.Form):
    delegate_to = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    delegate_until = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'})
    )
    delegation_authority = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3,
                                     'placeholder': 'Describe the scope of delegated authority...'})
    )


class WorkflowTemplateForm(forms.ModelForm):
    class Meta:
        model = WorkflowTemplate
        fields = ['name', 'category', 'description', 'is_active']
        widgets = {
            'name':        forms.TextInput(attrs={'class': 'form-control'}),
            'category':    forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active':   forms.CheckboxInput(),
        }


class PaymentSetupForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['payment_type', 'total_amount', 'currency', 'number_of_installments', 'notes']
        widgets = {
            'payment_type':           forms.Select(attrs={'class': 'form-control'}),
            'total_amount':           forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'currency':               forms.Select(attrs={'class': 'form-control'}),
            'number_of_installments': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 60}),
            'notes':                  forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class AIValidationForm(forms.Form):
    document = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png,.doc,.docx'})
    )
    expected_category = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Medical Claim, IT Procurement'})
    )
    subject = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Request subject...'})
    )
