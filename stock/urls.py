from django.urls import path

from . import views

app_name = 'stock'

urlpatterns = [
    path('', views.StockDashboardView.as_view(), name='dashboard'),
    path('daily-sell/', views.DailySellView.as_view(), name='daily_sell'),
    path('sale/<int:pk>/print/', views.SalePrintView.as_view(), name='sale_print'),
]
