from django.db import models

# Create your models here.
class Company(models.Model):
    name = models.CharField(max_length=225)
    website = models.URLField(blank=True)
    description =  models.TextField(blank=True)
    location = models.CharField(max_length=225, blank=True)

    class Meta:
        verbose_name_plural = "Companies"
        unique_together = [('name', 'website')]

    def __str__(self):
        return self.name

class Job(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="jobs")
    title = models.CharField(max_length=225)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=225, blank=True)
    source_url = models.URLField(unique=True)
    scraped_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-scraped_at']

    def __str__(self):
        return f"{self.title} @ {self.company.name}"