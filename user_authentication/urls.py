from django.urls import path, reverse_lazy
from django.contrib.auth.views import LogoutView
from django.views.generic import RedirectView

from . import views

app_name = 'user_authentication'

urlpatterns = [
    path('', views.StoreLoginView.as_view(), name='login'),
    path(
        'login/',
        RedirectView.as_view(pattern_name='user_authentication:login'),
        name='login_legacy',
    ),
    path(
        'logout/',
        LogoutView.as_view(next_page=reverse_lazy('user_authentication:login')),
        name='logout',
    ),
    path('my-account/', views.MyAccountView.as_view(), name='my_account'),
]
