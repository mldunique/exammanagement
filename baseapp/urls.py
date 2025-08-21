# from django.urls import path
# from . import views

# urlpatterns = [
#     path('', views.login, name="login"),
#     path('home/', views.home, name="home"),
#     path('import/', views.import_docx, name="import_docx"),
#     path('exam/create/', views.exam_create, name='exam_create'),
#     path('exam/<int:exam_id>/', views.exam_preview, name='exam_preview'),
# ]

from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('', views.login_view, name="login"),
    path('logout/', views.logout_view, name="logout"),
    
    # Admin URLs
    path('admin/home/', views.admin_home, name="admin_home"),
    path('admin/import/', views.import_docx, name="import_docx"),
    path('admin/exam/create/', views.exam_create, name='exam_create'),
    path('admin/exam/<int:exam_id>/', views.exam_preview, name='exam_preview'),
    path('admin/exam/<int:exam_id>/schedule/', views.exam_schedule, name='exam_schedule'),
    path('admin/exam/<int:exam_id>/delete/', views.exam_delete, name='exam_delete'),
    
    # Student URLs
    path('student/home/', views.student_home, name="student_home"),
    path('student/exam/<int:exam_id>/start/', views.exam_start, name='exam_start'),
    path('student/exam/session/<int:session_id>/', views.exam_taking, name='exam_taking'),
    path('student/exam/session/<int:session_id>/submit/', views.exam_submit, name='exam_submit'),
    path('student/exam/session/<int:session_id>/result/', views.exam_result, name='exam_result'),
    
    # AJAX
    path('ajax/save-answer/', views.save_answer, name='save_answer'),
]