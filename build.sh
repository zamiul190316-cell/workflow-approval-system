#!/usr/bin/env bash
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

mkdir -p staticfiles
python manage.py collectstatic --no-input
python manage.py migrate

python manage.py shell -c "
from workflow_app.models import User
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'zamiul190316@gmail.com', 'Admin@1234')
    print('Superuser created')
else:
    print('Superuser already exists')
"