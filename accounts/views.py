from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render

from .forms import ProfileForm, SignupForm, UserForm
from .models import Profile


def signup(request):
    if not settings.ALLOW_SIGNUP:
        raise Http404
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)
    form = SignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, 'Compte créé. Bienvenue !')
        return redirect(settings.LOGIN_REDIRECT_URL)
    return render(request, 'accounts/signup.html', {'form': form})


@login_required
def profile(request):
    profile_obj, _ = Profile.objects.get_or_create(user=request.user)
    user_form = UserForm(request.POST or None, instance=request.user)
    profile_form = ProfileForm(request.POST or None, instance=profile_obj)
    if request.method == 'POST' and user_form.is_valid() and profile_form.is_valid():
        user_form.save()
        profile_form.save()
        messages.success(request, 'Profil mis à jour.')
        return redirect('accounts:profile')
    return render(request, 'accounts/profile.html',
                  {'user_form': user_form, 'profile_form': profile_form})
