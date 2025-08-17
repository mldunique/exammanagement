from django.urls import path
from . import views

urlpatterns = [
    path('', views.login, name="login"),
    path('home/', views.home, name="home"),
    path('import/', views.import_docx, name="import_docx"),
    path('exam/create/', views.exam_create, name='exam_create'),
    path('exam/<int:exam_id>/', views.exam_preview, name='exam_preview'),
]