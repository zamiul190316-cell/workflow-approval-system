"""
Management command: python manage.py seed_data
Seeds all initial Trust Bank PLC data:
- 14 Divisions with heads
- 13 Branches
- Admin user + sample users per role
- All approval categories
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from workflow_app.models import Division, Branch, User, ApprovalCategory


DIVISIONS = [
    ("Retail Banking Division",              "Rahim Ahmed"),
    ("Corporate Banking Division",           "Karim Uddin"),
    ("SME Banking Division",                 "Abdul Sattar"),
    ("Islamic Banking Division",             "Jabbar Hossain"),
    ("International Banking Division",       "Kamal Chowdhury"),
    ("Treasury Division",                    "Nur Alam"),
    ("Credit & Risk Management Division",    "Habibur Rahman"),
    ("Human Resources (HR) Division",        "Selim Reza"),
    ("Information Technology (IT) Division", "Faruk Hasan"),
    ("Finance & Accounts Division",          "Anwarul Islam"),
    ("Branch Control & Inspection Division", "Shahidul Karim"),
    ("Operations Division",                  "Mizanur Rahman"),
    ("Card Division",                        "Rafiq Ahmed"),
    ("Customer Service Division",            "Babul Mia"),
]

BRANCHES = [
    ("Head Office",                         "HO001"),
    ("Principal Branch",                    "PR001"),
    ("SKB Branch",                          "SKB01"),
    ("Bogura Cantt. Branch",                "BGA01"),
    ("Cumilla Cantt. Branch",               "CUM01"),
    ("Chattogram Cantt. Branch",            "CTG01"),
    ("Rangpur Cantt. Branch",               "RNG01"),
    ("Jashore Cantt. Branch",               "JSR01"),
    ("Mymensingh Cantt. Branch",            "MYM01"),
    ("Savar Cantt. Branch",                 "SVR01"),
    ("Jalalabad Cantt. Branch",             "JLB01"),
    ("Agrabad Branch",                      "AGR01"),
    ("Shaheed Salahuddin Cantonment Branch","SSL01"),
]

CATEGORIES = [
    # (group, name, min_approvers, max_approvers, required_division_name, min_from_div)
    ("financial",         "Loan Approval",                   3, 50, None, 0),
    ("financial",         "Credit Limit Increase",           3, 50, "Credit & Risk Management Division", 1),
    ("financial",         "Fund Transfer",                   2, 50, None, 0),
    ("financial",         "Investment Approval",             3, 50, None, 0),
    ("employee_benefits", "Medical Claim",                   2, 50, None, 0),
    ("employee_benefits", "Travel Allowance",                2, 50, None, 0),
    ("employee_benefits", "Training Request",                2, 50, None, 0),
    ("employee_benefits", "Leave Application",               2, 50, "Human Resources (HR) Division", 1),
    ("operational",       "Account Opening",                 2, 50, None, 0),
    ("operational",       "Fixed Deposit Closure",           2, 50, None, 0),
    ("operational",       "Statement Generation",            2, 50, None, 0),
    ("operational",       "Bulk Cheque Book Request",        2, 50, None, 0),
    ("administrative",    "Procurement Request",             2, 50, None, 0),
    ("administrative",    "IT Procurement - Server/Laptop",  3, 50, "Information Technology (IT) Division", 2),
    ("administrative",    "Vendor Payment",                  3, 50, "Finance & Accounts Division", 1),
    ("administrative",    "Recruitment",                     3, 50, "Human Resources (HR) Division", 1),
    ("administrative",    "Asset Purchase",                  3, 50, None, 0),
]


class Command(BaseCommand):
    help = 'Seed initial Trust Bank PLC data (divisions, branches, users, categories)'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Clear existing data before seeding')

    @transaction.atomic
    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing data...')
            User.objects.filter(is_superuser=False).delete()
            Division.objects.all().delete()
            Branch.objects.all().delete()
            ApprovalCategory.objects.all().delete()

        # 1. Divisions
        self.stdout.write('Creating divisions...')
        division_map = {}
        for name, head in DIVISIONS:
            div, created = Division.objects.get_or_create(
                name=name, defaults={'head_name': head, 'is_active': True}
            )
            if not created:
                div.head_name = head
                div.save()
            division_map[name] = div
            self.stdout.write(f'  {"Created" if created else "Updated"}: {name}')

        # 2. Branches
        self.stdout.write('Creating branches...')
        branch_map = {}
        for name, code in BRANCHES:
            branch, created = Branch.objects.get_or_create(
                name=name, defaults={'code': code, 'is_active': True}
            )
            branch_map[name] = branch
            self.stdout.write(f'  {"Created" if created else "Exists"}: {name}')

        # 3. Categories
        self.stdout.write('Creating approval categories...')
        for group, name, min_ap, max_ap, req_div_name, min_from_div in CATEGORIES:
            req_div = division_map.get(req_div_name) if req_div_name else None
            cat, created = ApprovalCategory.objects.get_or_create(
                name=name, defaults={
                    'group': group, 'min_approvers': min_ap, 'max_approvers': max_ap,
                    'required_division': req_div,
                    'min_required_from_division': min_from_div,
                    'is_active': True,
                }
            )
            self.stdout.write(f'  {"Created" if created else "Exists"}: {name}')

        # 4. Users
        self.stdout.write('Creating users...')
        head_office = branch_map.get("Head Office")
        it_div = division_map.get("Information Technology (IT) Division")
        hr_div = division_map.get("Human Resources (HR) Division")
        finance_div = division_map.get("Finance & Accounts Division")

        users_to_create = [
            # (username, password, first, last, role, emp_id, designation, division, branch)
            ("admin", "admin123", "System", "Admin", "admin", "TBL-ADM-001", "System Administrator", None, head_office),
            ("md_rahman", "pass123", "Managing", "Director", "md", "TBL-MD-001", "Managing Director", None, head_office),
            ("it_head", "pass123", "Faruk", "Hasan", "division_head", "TBL-IT-001", "Head of IT Division", it_div, head_office),
            ("it_officer1", "pass123", "Sohel", "Rana", "approver", "TBL-IT-002", "Senior IT Officer", it_div, head_office),
            ("it_officer2", "pass123", "Riyad", "Islam", "maker", "TBL-IT-003", "IT Officer", it_div, head_office),
            ("hr_head", "pass123", "Selim", "Reza", "division_head", "TBL-HR-001", "Head of HR Division", hr_div, head_office),
            ("finance_head", "pass123", "Anwarul", "Islam", "division_head", "TBL-FIN-001", "Head of Finance", finance_div, head_office),
            ("checker1", "pass123", "Abir", "Hossain", "checker", "TBL-CHK-001", "Senior Checker", None, head_office),
            ("initiator1", "pass123", "Tahmina", "Begum", "initiator", "TBL-STF-001", "Senior Officer", None, head_office),
            ("initiator2", "pass123", "Zahir", "Uddin", "initiator", "TBL-STF-002", "Officer", None, head_office),
        ]

        for username, password, first, last, role, emp_id, des, div, branch in users_to_create:
            if not User.objects.filter(username=username).exists():
                u = User.objects.create_user(
                    username=username, password=password,
                    first_name=first, last_name=last,
                    role=role, employee_id=emp_id, designation=des,
                    division=div, branch=branch,
                    email=f'{username}@trustbankplc.com',
                    is_staff=(role == 'admin'), is_superuser=(role == 'admin'),
                )
                self.stdout.write(self.style.SUCCESS(f'  Created user: {username} / {password}'))
            else:
                self.stdout.write(f'  User exists: {username}')

        self.stdout.write(self.style.SUCCESS('\n✅ Seed data complete!'))
        self.stdout.write('\nDefault login credentials:')
        self.stdout.write('  Admin:    admin / admin123')
        self.stdout.write('  MD:       md_rahman / pass123')
        self.stdout.write('  IT Head:  it_head / pass123')
        self.stdout.write('  Initiator: initiator1 / pass123')
