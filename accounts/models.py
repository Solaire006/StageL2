from django.conf import settings
from django.db import models


class Profile(models.Model):
    """Extra data about a user. Created automatically with the user."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField('téléphone', max_length=30, blank=True)
    skills = models.TextField(
        'compétences', blank=True,
        help_text='Une compétence par ligne (sert plus tard à adapter vos candidatures).')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Profil de {self.user}'

    @property
    def skills_list(self):
        return [s.strip() for s in self.skills.splitlines() if s.strip()]
