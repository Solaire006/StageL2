from django.urls import path

from . import views

app_name = "scraper"

urlpatterns = [
    path("", views.job_list, name="job_list"),
    path("jobs/<int:pk>/", views.job_detail, name="job_detail"),
    path("export/", views.export_excel, name="export"),
    path("scrape/", views.start_scrape, name="start_scrape"),
    path("scrape/status/", views.scrape_status, name="scrape_status"),
]
