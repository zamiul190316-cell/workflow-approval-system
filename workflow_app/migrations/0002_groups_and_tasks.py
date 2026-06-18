# New migration for Approval Groups, Group Members, Group Logs, Task History
# Place this file at:
# workflow_app/migrations/0002_groups_and_tasks.py

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('workflow_app', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ApprovalGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=150, unique=True)),
                ('description', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('division', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approval_groups', to='workflow_app.division')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='owned_groups', to='workflow_app.user')),
            ],
            options={'db_table': 'workflow_approval_groups', 'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='ApprovalGroupMember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('is_active', models.BooleanField(default=True)),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='members', to='workflow_app.approvalgroup')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='group_memberships', to='workflow_app.user')),
            ],
            options={'db_table': 'workflow_group_members', 'unique_together': {('group', 'user')}},
        ),
        migrations.CreateModel(
            name='ApprovalStepGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('assigned_at', models.DateTimeField(auto_now_add=True)),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='assigned_steps', to='workflow_app.approvalgroup')),
                ('step', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='group_assignment', to='workflow_app.approvalstep')),
            ],
            options={'db_table': 'workflow_step_groups'},
        ),
        migrations.CreateModel(
            name='GroupApprovalLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('action', models.CharField(choices=[('approved','Approved'),('rejected','Rejected'),('returned','Returned to Initiator'),('modification_requested','Modification Requested'),('commented','Comment Added')], max_length=30)),
                ('comment', models.TextField(blank=True)),
                ('attachment', models.FileField(blank=True, null=True, upload_to='group_step_attachments/')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('acted_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='group_approval_actions', to='workflow_app.user')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='approval_logs', to='workflow_app.approvalgroup')),
                ('step', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='group_logs', to='workflow_app.approvalstep')),
            ],
            options={'db_table': 'workflow_group_approval_logs', 'ordering': ['-acted_at']},
        ),
        migrations.CreateModel(
            name='UserTaskHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('action', models.CharField(choices=[('approved','Approved'),('rejected','Rejected'),('returned','Returned to Initiator'),('modification_requested','Modification Requested'),('commented','Comment Added'),('delegated','Delegated')], max_length=30)),
                ('comment', models.TextField(blank=True)),
                ('has_attachment', models.BooleanField(default=False)),
                ('acted_at', models.DateTimeField(auto_now_add=True)),
                ('request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='task_history', to='workflow_app.approvalrequest')),
                ('step', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='task_history', to='workflow_app.approvalstep')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='task_history', to='workflow_app.user')),
                ('via_group', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='task_history', to='workflow_app.approvalgroup')),
            ],
            options={'db_table': 'workflow_user_task_history', 'ordering': ['-acted_at']},
        ),
    ]
