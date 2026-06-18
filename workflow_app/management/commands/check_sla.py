"""
Management command: python manage.py check_sla
Run periodically via cron to escalate SLA-breached approvals.

Suggested cron entry (every hour):
0 * * * * /path/to/venv/bin/python /path/to/workflow_system/manage.py check_sla
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Check SLA deadlines and send escalation notifications'

    def handle(self, *args, **options):
        from workflow_app.services import SLAService
        count = SLAService.check_and_escalate_all()
        self.stdout.write(self.style.SUCCESS(f'✅ SLA check complete. Escalated {count} approval(s).'))
