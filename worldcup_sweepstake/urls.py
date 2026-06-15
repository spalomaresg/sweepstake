from django.contrib import admin
from django.urls import path, include
from bets import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    path('my-predictions/', views.my_predictions, name='my_predictions'),
    path('standings/', views.group_standings, name='group_standings'),
    path('predict/save/<int:match_id>/', views.save_prediction_ajax, name='save_prediction_ajax'),
]
