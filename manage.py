#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
#1. manage.py
"""

相當於 Django 的「總控台」腳本。

你用它做各種事：

python manage.py runserver：啟動開發伺服器

python manage.py migrate：套用資料庫變更

python manage.py createsuperuser：建立後台帳號

想像成：專案的指令入口
"""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
