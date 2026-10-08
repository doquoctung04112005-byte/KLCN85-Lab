from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from accounts import views as account_views


urlpatterns = [
    path("", RedirectView.as_view(pattern_name="dashboard", permanent=False), name="home"),
    path("admin/", admin.site.urls),
    path("documents/", include("documents.urls")),
    path("users/", account_views.user_list, name="user_list"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="accounts/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path("dashboard/", account_views.dashboard, name="dashboard"),
    path("profile/", account_views.profile, name="profile"),
]
