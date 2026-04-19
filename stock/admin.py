from django.contrib import admin

from .models import DailySell, DailySellLine, Product


class DailySellLineInline(admin.TabularInline):
    model = DailySellLine
    extra = 0
    readonly_fields = ('unit_price',)
    fields = ('product', 'quantity', 'unit_price')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'quality', 'price', 'stock_quantity')
    search_fields = ('name', 'quality')


@admin.register(DailySell)
class DailySellAdmin(admin.ModelAdmin):
    inlines = [DailySellLineInline]
    list_display = (
        'sold_at',
        'customer_name',
        'phone',
        'lines_summary',
        'line_total_display',
        'amount_paid',
        'amount_due',
    )
    list_filter = ('sold_at',)
    search_fields = ('customer_name', 'phone', 'lines__product__name')
    readonly_fields = ('sold_at', 'line_total_display')
    ordering = ('-sold_at',)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('lines__product')

    @admin.display(description='লাইনসমূহ')
    def lines_summary(self, obj):
        parts = [
            f'{ln.product.name}×{ln.quantity}' for ln in obj.lines.all()[:5]
        ]
        if not parts:
            return '—'
        more = obj.lines.count() - len(parts)
        if more > 0:
            parts.append(f'… +{more}')
        return ', '.join(parts)

    @admin.display(description='মোট')
    def line_total_display(self, obj):
        return obj.line_total


@admin.register(DailySellLine)
class DailySellLineAdmin(admin.ModelAdmin):
    list_display = ('sale', 'product', 'quantity', 'unit_price')
    list_select_related = ('sale', 'product')
    autocomplete_fields = ('sale', 'product')
