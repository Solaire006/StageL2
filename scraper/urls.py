from django.urls import path

from . import views

app_name = "scraper"

urlpatterns = [
    path("", views.job_list, name="job_list"),
    path("jobs/<int:pk>/", views.job_detail, name="job_detail"),
]
