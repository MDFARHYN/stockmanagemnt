# Generated manually for DailySellPayment

from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def backfill_payments(apps, schema_editor):
    DailySell = apps.get_model('stock', 'DailySell')
    DailySellPayment = apps.get_model('stock', 'DailySellPayment')
    for s in DailySell.objects.iterator():
        ap = getattr(s, 'amount_paid', None) or Decimal('0')
        if ap > 0:
            DailySellPayment.objects.create(
                sale_id=s.pk,
                amount=ap,
                paid_at=s.sold_at,
            )


def noop_reverse(apps, schema_editor):
    DailySellPayment = apps.get_model('stock', 'DailySellPayment')
    DailySellPayment.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0002_dailysell_payment_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='DailySellPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('paid_at', models.DateTimeField(default=django.utils.timezone.now)),
                (
                    'sale',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='payment_entries',
                        to='stock.dailysell',
                    ),
                ),
            ],
            options={
                'db_table': 'stock_management_dailysellpayment',
                'ordering': ['-paid_at', '-id'],
            },
        ),
        migrations.RunPython(backfill_payments, noop_reverse),
    ]
