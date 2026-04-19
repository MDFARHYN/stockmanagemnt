from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.views import LoginView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from .forms import AccountPasswordChangeForm


class StoreLoginView(LoginView):
    template_name = 'user_authentication/login.html'
    redirect_authenticated_user = True


class MyAccountView(LoginRequiredMixin, View):
    template_name = 'user_authentication/my_account.html'

    def get(self, request):
        return render(
            request,
            self.template_name,
            {'password_form': AccountPasswordChangeForm(user=request.user)},
        )

    def post(self, request):
        if request.POST.get('change_password'):
            form = AccountPasswordChangeForm(user=request.user, data=request.POST)
            if form.is_valid():
                form.save()
                update_session_auth_hash(request, form.user)
                messages.success(
                    request,
                    'পাসওয়ার্ড সফলভাবে পরিবর্তন হয়েছে।',
                )
                return redirect(reverse('user_authentication:my_account'))
            return render(
                request,
                self.template_name,
                {'password_form': form},
            )
        return redirect(reverse('user_authentication:my_account'))
