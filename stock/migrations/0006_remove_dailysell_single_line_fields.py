from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0005_dailysellline_and_backfill'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='dailysell',
            name='product',
        ),
        migrations.RemoveField(
            model_name='dailysell',
            name='quantity',
        ),
        migrations.RemoveField(
            model_name='dailysell',
            name='unit_price',
        ),
    ]
