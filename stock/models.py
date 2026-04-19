from decimal import Decimal



from django.db import models, transaction

from django.db.models import F

from django.utils import timezone





class Product(models.Model):

    name = models.CharField(max_length=255)

    quality = models.CharField(max_length=255, help_text='যেমন গ্রেড / মান')

    price = models.DecimalField(

        max_digits=12,

        decimal_places=2,

        help_text='প্রতি এককের দাম (টাকা)। বিক্রয় মোট = একক দাম × পরিমাণ।',

    )

    stock_quantity = models.PositiveIntegerField(default=0)



    class Meta:

        db_table = 'stock_management_product'

        ordering = ['name']



    def __str__(self):

        return self.name





class DailySell(models.Model):

    """এক বিক্রয় অর্ডার — এক ক্রেতা, একাধিক পণ্য লাইন।"""



    customer_name = models.CharField(max_length=255)

    phone = models.CharField(max_length=32)

    address = models.TextField(blank=True)

    amount_paid = models.DecimalField(

        max_digits=12,

        decimal_places=2,

        default=0,

        help_text='ক্রেতা যে টাকা দিয়েছে',

    )

    amount_due = models.DecimalField(

        max_digits=12,

        decimal_places=2,

        default=0,

        help_text='বাকি (মোট − পরিশোধ)',

    )

    sold_at = models.DateTimeField(auto_now_add=True)



    class Meta:

        db_table = 'stock_management_dailysell'

        ordering = ['-sold_at']



    def __str__(self):

        return f'{self.customer_name} — {self.sold_at:%Y-%m-%d}'



    def delete(self, *args, **kwargs):

        with transaction.atomic():

            for line in self.lines.select_related('product'):

                Product.objects.filter(pk=line.product_id).update(

                    stock_quantity=F('stock_quantity') + line.quantity

                )

            super().delete(*args, **kwargs)



    @property

    def line_total(self) -> Decimal:

        """সব লাইনের মোট বিল।"""

        total = Decimal('0')

        for ln in self.lines.all():

            total += (ln.unit_price * ln.quantity).quantize(Decimal('0.01'))

        return total.quantize(Decimal('0.01'))



    @property

    def total_line_units(self) -> int:

        return sum(ln.quantity for ln in self.lines.all())





class DailySellLine(models.Model):

    """একটি বিক্রয় অর্ডারের এক লাইন (পণ্য × পরিমাণ)।"""



    sale = models.ForeignKey(

        DailySell,

        on_delete=models.CASCADE,

        related_name='lines',

    )

    product = models.ForeignKey(

        Product,

        on_delete=models.PROTECT,

        related_name='sale_lines',

    )

    quantity = models.PositiveIntegerField()

    unit_price = models.DecimalField(

        max_digits=12,

        decimal_places=2,

        editable=False,

        help_text='বিক্রয় মুহূর্তে একক দাম',

    )



    class Meta:

        db_table = 'stock_management_dailysellline'

        ordering = ['id']



    def __str__(self):

        return f'{self.product.name} × {self.quantity}'



    @property

    def line_total(self) -> Decimal:

        return (self.unit_price * self.quantity).quantize(Decimal('0.01'))





class DailySellPayment(models.Model):

    """একটি বিক্রয়ে একাধিকবার পরিশোধের রেকর্ড (তারিখ ও টাকা)।"""



    sale = models.ForeignKey(

        DailySell,

        on_delete=models.CASCADE,

        related_name='payment_entries',

    )

    amount = models.DecimalField(max_digits=12, decimal_places=2)

    paid_at = models.DateTimeField(default=timezone.now)

    note = models.TextField(

        blank=True,

        default='',

        help_text='বাকি পরিশোধের সাথে মন্তব্য (ঐচ্ছিক)',

    )



    class Meta:

        db_table = 'stock_management_dailysellpayment'

        ordering = ['-paid_at', '-id']



    def __str__(self):

        return f'{self.sale_id} · {self.amount} @ {self.paid_at}'


