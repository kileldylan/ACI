from django.urls import path

from ACI_backend.api.auth import (
    csrf_token,
    current_user,
    login_view,
    logout_view,
    register,
)


urlpatterns = [
    path("csrf/", csrf_token, name="auth-csrf"),
    path("register/", register, name="auth-register"),
    path("login/", login_view, name="auth-login"),
    path("logout/", logout_view, name="auth-logout"),
    path("me/", current_user, name="auth-me"),
]