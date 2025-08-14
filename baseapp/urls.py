from django.contrib import admin
from . import views
from django.urls import path

urlpatterns = [
    path('', views.login, name = "login"),
    path('home/', views.home, name = "home"),
]