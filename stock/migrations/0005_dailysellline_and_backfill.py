from django.db import migrations, models
import django.db.models.deletion


def backfill_lines(apps, schema_editor):
    DailySell = apps.get_model('stock', 'DailySell')
    DailySellLine = apps.get_model('stock', 'DailySellLine')
    for s in DailySell.objects.iterator():
        DailySellLine.objects.create(
            sale_id=s.pk,
            product_id=s.product_id,
            quantity=s.quantity,
            unit_price=s.unit_price,
        )


def noop_reverse(apps, schema_editor):
    DailySellLine = apps.get_model('stock', 'DailySellLine')
    DailySellLine.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0004_dailysellpayment_note'),
    ]

    operations = [
        migrations.CreateModel(
            name='DailySellLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveIntegerField()),
                ('unit_price', models.DecimalField(decimal_places=2, editable=False, help_text='বিক্রয় মুহূর্তে একক দাম', max_digits=12)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sale_lines', to='stock.product')),
                ('sale', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='stock.dailysell')),
            ],
            options={
                'db_table': 'stock_management_dailysellline',
                'ordering': ['id'],
            },
        ),
        migrations.RunPython(backfill_lines, noop_reverse),
    ]
