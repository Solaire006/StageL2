from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import Profile

User = get_user_model()


def _email_taken(email, exclude_pk=None):
    qs = User.objects.filter(email__iexact=email)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


class SignupForm(UserCreationForm):
    first_name = forms.CharField(label='Prénom', max_length=150)
    last_name = forms.CharField(label='Nom', max_length=150)
    email = forms.EmailField(label='Adresse e-mail')

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'first_name', 'last_name', 'email')

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if _email_taken(email):
            raise forms.ValidationError('Un compte utilise déjà cette adresse e-mail.')
        return email


class UserForm(forms.ModelForm):
    email = forms.EmailField(label='Adresse e-mail')

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email')
        labels = {'first_name': 'Prénom', 'last_name': 'Nom'}

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if _email_taken(email, exclude_pk=self.instance.pk):
            raise forms.ValidationError('Un compte utilise déjà cette adresse e-mail.')
        return email


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ('phone', 'skills')
        widgets = {'skills': forms.Textarea(attrs={'rows': 5})}
