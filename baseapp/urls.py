from django.urls import path
from . import views
path('admin/home/', views.admin_home, name="admin_home"),

urlpatterns = [
    # Authentication
    path('', views.login_view, name="home"),
    path('logout/', views.logout_view, name="logout"),
    
    # ADMIN URLs (Yêu cầu 1, 3) - Chỉ admin/staff
    path('admin/home/', views.admin_home, name="admin_home"),
    path('admin/import/', views.import_docx, name="import_docx"),
    path('admin/exam/create/', views.exam_create, name='exam_create'),
    path('admin/exam/<int:exam_id>/', views.exam_preview, name='exam_preview'),
    path('admin/exam/manage/', views.exam_manage, name='exam_manage'),
    
    # STUDENT URLs (Yêu cầu 5) - Cho học sinh
    path('student/home/', views.student_home, name="student_home"),
    path('student/exam/<int:exam_id>/start/', views.exam_start, name='exam_start'),
    path('student/attempt/<int:attempt_id>/', views.exam_take, name='exam_take'),
    path('student/result/<int:attempt_id>/', views.exam_result, name='exam_result'),
    path('student/my-results/', views.my_results, name='my_results'),
]