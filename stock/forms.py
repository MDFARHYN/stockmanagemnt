from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseFormSet, formset_factory
from django.utils import timezone

from .models import DailySell, DailySellPayment, Product

_sm_input = {'class': 'sm-input'}
_sm_select = {'class': 'sm-select sm-input'}
_sale_lg = {'class': 'sm-input sale-entry-input-lg'}
_sale_textarea_lg = {'rows': 3, 'class': 'sm-input sm-textarea sale-entry-input-lg'}


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'quality', 'price', 'stock_quantity']
        labels = {
            'name': 'পণ্যের নাম',
            'quality': 'মান / গ্রেড',
            'price': 'একক দাম (টাকা)',
            'stock_quantity': 'স্টক পরিমাণ',
        }
        help_texts = {
            'price': 'প্রতি এককের দাম। বিক্রয়ে মোট টাকা = একক দাম × বিক্রয় সংখ্যা।',
            'stock_quantity': 'মোট কত একক মজুদ আছে।',
        }
        widgets = {
            'name': forms.TextInput(attrs=_sm_input),
            'quality': forms.TextInput(attrs=_sm_input),
            'price': forms.NumberInput(
                attrs={**_sm_input, 'step': '1', 'min': '0', 'inputmode': 'numeric'}
            ),
            'stock_quantity': forms.NumberInput(attrs={**_sm_input, 'min': '0'}),
        }


class SaleLineForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        required=False,
        empty_label='পণ্য নির্বাচন করুন',
        label='পণ্য',
        widget=forms.Select(attrs={**_sm_select, 'class': 'sm-select sm-input sale-entry-input-lg sale-line-product'}),
    )
    quantity = forms.IntegerField(
        min_value=1,
        required=False,
        label='পরিমাণ',
        widget=forms.NumberInput(
            attrs={
                **_sm_input,
                'min': '1',
                'step': '1',
                'inputmode': 'numeric',
                'class': 'sm-input sale-entry-input-lg sale-line-qty',
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Product.objects.filter(stock_quantity__gt=0).order_by('name')
        self.fields['product'].queryset = qs
        self.fields['product'].label_from_instance = (
            lambda obj: f'{obj.name} — স্টক {obj.stock_quantity} টি'
        )

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        p = cleaned.get('product')
        q = cleaned.get('quantity')
        if not p and q is None:
            cleaned['_skip'] = True
            return cleaned
        if p and q is not None:
            cleaned['_skip'] = False
            return cleaned
        raise ValidationError('পণ্য ও পরিমাণ উভয়ই দিন।')


class BaseSaleLineFormSet(BaseFormSet):
    def clean(self):
        super().clean()
        rows = []
        for form in self.forms:
            if not hasattr(form, 'cleaned_data'):
                continue
            cd = form.cleaned_data
            if cd.get('_skip'):
                continue
            rows.append((cd['product'], cd['quantity']))
        if not rows:
            raise ValidationError('কমপক্ষে একটি পণ্য লাইন যোগ করুন।')
        self.cleaned_line_rows = rows


def get_sale_line_formset(data=None, prefix='lines'):
    """নতুন বিক্রয়ের পণ্য লাইন ফর্মসেট।"""
    FS = formset_factory(
        SaleLineForm,
        formset=BaseSaleLineFormSet,
        extra=1,
        max_num=80,
        can_delete=False,
    )
    if data is not None:
        return FS(data, prefix=prefix)
    return FS(prefix=prefix)


class DailySellOrderForm(forms.Form):
    customer_name = forms.CharField(
        label='ক্রেতার নাম',
        widget=forms.TextInput(attrs=_sale_lg),
    )
    phone = forms.CharField(
        label='ফোন',
        widget=forms.TextInput(attrs=_sale_lg),
    )
    address = forms.CharField(
        label='ঠিকানা',
        required=False,
        widget=forms.Textarea(attrs=_sale_textarea_lg),
    )
    amount_paid = forms.DecimalField(
        label='পরিশোধ (টাকা)',
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0'),
        required=False,
        initial=Decimal('0'),
        help_text='ক্রেতা এখন কত টাকা দিয়েছে। মোট বিলের বেশি হতে পারবে না। খালি বা ০ মানে পুরো টাকাই বাকি।',
        widget=forms.NumberInput(
            attrs={
                **_sm_input,
                'step': '1',
                'min': '0',
                'inputmode': 'numeric',
                'id': 'id_amount_paid',
                'class': 'sm-input sale-entry-input-lg',
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _form_id = 'daily-sell-form'
        for _name in ('customer_name', 'phone', 'address'):
            self.fields[_name].widget.attrs['form'] = _form_id

    def clean_amount_paid(self):
        data = self.cleaned_data.get('amount_paid')
        if data is None:
            return Decimal('0')
        return data


class DailySellEditForm(forms.ModelForm):
    """ক্রেতা সম্পাদনা + বাকির ওপর নতুন পরিশোধ জমা (তারিখসহ)।"""

    payment_add = forms.DecimalField(
        label='এই বার জমার টাকা',
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0'),
        required=False,
        initial=Decimal('0'),
        help_text='বাকি থেকে কত টাকা পেলেন—লিখে আপডেট করুন। খালি বা ০ মানে শুধু ক্রেতার তথ্য বদলাবে।',
        widget=forms.NumberInput(
            attrs={
                'class': 'sm-input sale-entry-input-lg',
                'step': '1',
                'min': '0',
                'inputmode': 'numeric',
                'id': 'id_edit_payment_add',
            }
        ),
    )
    payment_at = forms.DateTimeField(
        label='পরিশোধের সময়',
        required=False,
        widget=forms.DateTimeInput(
            attrs={
                'type': 'datetime-local',
                'class': 'sm-input sale-entry-input-lg',
                'id': 'id_edit_payment_at',
            },
            format='%Y-%m-%dT%H:%M',
        ),
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S'],
        help_text='কখন টাকা পেলেন—খালি থাকলে এখনকার সময় ধরা হবে।',
    )
    payment_note = forms.CharField(
        label='মন্তব্য (ঐচ্ছিক)',
        required=False,
        max_length=2000,
        widget=forms.Textarea(
            attrs={
                'rows': 2,
                'class': 'sm-input sm-textarea sale-entry-input-lg',
                'id': 'id_edit_payment_note',
                'placeholder': 'যেমন: নগদ / মোবাইল ব্যাংক / পরের সপ্তাহে বাকি',
            }
        ),
        help_text='এই জমার সাথে সংক্ষিপ্ত নোট রাখতে পারেন।',
    )

    class Meta:
        model = DailySell
        fields = ['customer_name', 'phone', 'address']
        labels = {
            'customer_name': 'ক্রেতার নাম',
            'phone': 'ফোন',
            'address': 'ঠিকানা',
        }
        widgets = {
            'customer_name': forms.TextInput(attrs=_sale_lg),
            'phone': forms.TextInput(attrs=_sale_lg),
            'address': forms.Textarea(attrs=_sale_textarea_lg),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        now = timezone.localtime(timezone.now())
        self.fields['payment_at'].initial = now.strftime('%Y-%m-%dT%H:%M')
        if self.instance.pk:
            due = self.instance.amount_due
            self.fields['payment_add'].widget.attrs['max'] = str(
                due.quantize(Decimal('0.01'))
            )
            if due <= Decimal('0'):
                self.fields['payment_add'].help_text = (
                    'বাকি নেই। নতুন জমা লাগবে না — শুধু উপরের তথ্য আপডেট করুন।'
                )

    def clean(self):
        cleaned = super().clean()
        add = cleaned.get('payment_add')
        if add is None:
            add = Decimal('0')
            cleaned['payment_add'] = add
        due = self.instance.amount_due
        if add > due:
            self.add_error(
                'payment_add',
                ValidationError(
                    'বাকি আছে %(due)s টাকা। এর বেশি জমা দেওয়া যাবে না।',
                    params={'due': int(due)},
                ),
            )
        elif add > 0:
            when = cleaned.get('payment_at')
            if when is None:
                cleaned['payment_at'] = timezone.now()
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        add = self.cleaned_data.get('payment_add') or Decimal('0')
        when = self.cleaned_data.get('payment_at')
        if add > 0:
            note_txt = (self.cleaned_data.get('payment_note') or '').strip()
            DailySellPayment.objects.create(
                sale=instance,
                amount=add,
                paid_at=when or timezone.now(),
                note=note_txt,
            )
            instance.amount_paid = (instance.amount_paid + add).quantize(Decimal('0.01'))
            instance.amount_due = (instance.line_total - instance.amount_paid).quantize(
                Decimal('0.01')
            )
        if commit:
            instance.save()
        return instance
