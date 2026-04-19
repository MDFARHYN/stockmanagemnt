from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0003_dailysellpayment_and_backfill'),
    ]

    operations = [
        migrations.AddField(
            model_name='dailysellpayment',
            name='note',
            field=models.TextField(
                blank=True,
                default='',
                help_text='বাকি পরিশোধের সাথে মন্তব্য (ঐচ্ছিক)',
            ),
        ),
    ]
