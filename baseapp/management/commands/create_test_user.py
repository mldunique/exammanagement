# management/commands/create_test_users.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from baseapp.models import UserProfile

#python manage.py create_test_user 

class Command(BaseCommand):
    help = 'Tạo 2 user test: admin và student'

    def handle(self, *args, **options):
        # Tạo admin user
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@test.com',
                'first_name': 'Admin',
                'last_name': 'User',
                'is_staff': True,
            }
        )
        if created:
            admin_user.set_password('admin123')
            admin_user.save()
            self.stdout.write('Tạo admin user thành công')
        else:
            self.stdout.write('Admin user đã tồn tại')
        
        # Tạo profile cho admin
        admin_profile, created = UserProfile.objects.get_or_create(
            user=admin_user,
            defaults={'role': 'admin'}
        )
        if created:
            self.stdout.write('Tạo admin profile thành công')

        # Tạo student user
        student_user, created = User.objects.get_or_create(
            username='student',
            defaults={
                'email': 'student@test.com',
                'first_name': 'Student',
                'last_name': 'User',
            }
        )
        if created:
            student_user.set_password('student123')
            student_user.save()
            self.stdout.write('Tạo student user thành công')
        else:
            self.stdout.write('Student user đã tồn tại')
        
        # Tạo profile cho student
        student_profile, created = UserProfile.objects.get_or_create(
            user=student_user,
            defaults={'role': 'student', 'student_id': 'SV001'}
        )
        if created:
            self.stdout.write('Tạo student profile thành công')

        self.stdout.write(
            self.style.SUCCESS(
                '\n=== THÔNG TIN ĐĂNG NHẬP ===\n'
                'Admin: username=admin, password=admin123\n'
                'Student: username=student, password=student123\n'
            )
        )