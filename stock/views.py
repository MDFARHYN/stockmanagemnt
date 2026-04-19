from collections import defaultdict
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Prefetch, Sum
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from .forms import (
    DailySellEditForm,
    DailySellOrderForm,
    ProductForm,
    get_sale_line_formset,
)
from .models import DailySell, DailySellLine, DailySellPayment, Product

PAGE_SIZE = 20


def _parse_payment_datetime(raw):
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip().replace(' ', 'T')
    dt = parse_datetime(s)
    if dt is None:
        raise ValidationError('জমার সময় বুঝতে পারিনি।')
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _apply_payment_log_edits(sale, post):
    """Checkbox 'enable_payment_edit' থাকলে গ্রাহকের জমার লাইন আপডেট করে।"""
    if post.get('enable_payment_edit') != 'on':
        return False
    entries = list(
        DailySellPayment.objects.filter(sale_id=sale.pk).order_by('paid_at', 'id')
    )
    if not entries:
        raise ValidationError(
            'সম্পাদনার জন্য কোনো জমার রেকর্ড নেই। প্রথমে নতুন পরিশোধ যোগ করুন।'
        )
    line = sale.line_total
    total = Decimal('0')
    updates = []
    for e in entries:
        raw_a = post.get(f'pay_amt_{e.pk}', '').strip().replace(',', '.')
        raw_t = post.get(f'pay_at_{e.pk}', '').strip()
        if raw_a == '':
            raise ValidationError(
                'প্রতিটি জমার টাকার ঘর পূরণ করুন বা সম্পাদনা বন্ধ রাখুন।'
            )
        try:
            amt = Decimal(raw_a).quantize(Decimal('0.01'))
        except Exception:
            raise ValidationError('জমার টাকার সংখ্যা ঠিক করুন।')
        if amt < 0:
            raise ValidationError('জমার টাকা ঋণাত্মক হতে পারে না।')
        paid_at = _parse_payment_datetime(raw_t) if raw_t else e.paid_at
        raw_note = post.get(f'pay_note_{e.pk}', '')
        note_txt = (raw_note or '').strip()[:2000]
        total += amt
        updates.append((e, amt, paid_at, note_txt))
    if total > line:
        raise ValidationError(
            'জমার মোট %(total)s টাকা, মোট বিল %(line)s টাকার বেশি হতে পারে না।'
            % {'total': int(total), 'line': int(line)}
        )
    for e, amt, paid_at, note_txt in updates:
        e.amount = amt
        e.paid_at = paid_at
        e.note = note_txt
        e.save(update_fields=['amount', 'paid_at', 'note'])
    sale.amount_paid = total.quantize(Decimal('0.01'))
    sale.amount_due = (line - sale.amount_paid).quantize(Decimal('0.01'))
    sale.save(update_fields=['amount_paid', 'amount_due'])
    return True


def _apply_validation_errors(form, error):
    if hasattr(error, 'error_dict') and error.error_dict:
        for field, msgs in error.error_dict.items():
            for msg in msgs:
                form.add_error(field if field != '__all__' else None, msg)
    elif getattr(error, 'messages', None):
        for msg in error.messages:
            form.add_error(None, msg)


def _commit_new_sale(order_form, line_formset):
    """
    ট্রানজাকশনে অর্ডার, লাইন ও স্টক আপডেট। সফল হলে DailySell ফেরত;
    পরিশোধ বিলের বেশি হলে False (ফর্মে এরর যোগ করা হয়েছে)।
    """
    rows = line_formset.cleaned_line_rows
    qty_by_pid = defaultdict(int)
    for p, q in rows:
        qty_by_pid[p.pk] += q

    paid = order_form.cleaned_data.get('amount_paid') or Decimal('0')
    paid = paid.quantize(Decimal('0.01'))

    with transaction.atomic():
        locked = {}
        for pid in qty_by_pid:
            locked[pid] = Product.objects.select_for_update().get(pk=pid)

        for pid, need in qty_by_pid.items():
            prod = locked[pid]
            if need > prod.stock_quantity:
                raise ValidationError(
                    f'«{prod.name}»: স্টকে আছে মাত্র {prod.stock_quantity} টি।'
                )

        total_bill = Decimal('0')
        line_specs = []
        for p, q in rows:
            prod = locked[p.pk]
            up = prod.price.quantize(Decimal('0.01'))
            line_specs.append((prod.pk, q, up))
            total_bill += (up * Decimal(q)).quantize(Decimal('0.01'))
        total_bill = total_bill.quantize(Decimal('0.01'))

        if paid > total_bill:
            order_form.add_error(
                'amount_paid',
                ValidationError(
                    'মোট বিল %(total)s টাকা। পরিশোধ এর চেয়ে বেশি হতে পারে না।',
                    params={'total': int(total_bill)},
                ),
            )
            return False, None

        sale = DailySell.objects.create(
            customer_name=order_form.cleaned_data['customer_name'],
            phone=order_form.cleaned_data['phone'],
            address=order_form.cleaned_data.get('address') or '',
            amount_paid=paid,
            amount_due=(total_bill - paid).quantize(Decimal('0.01')),
        )

        for prod_pk, q, up in line_specs:
            DailySellLine.objects.create(
                sale=sale,
                product_id=prod_pk,
                quantity=q,
                unit_price=up,
            )
            Product.objects.filter(pk=prod_pk).update(
                stock_quantity=F('stock_quantity') - q
            )

        if paid > 0:
            DailySellPayment.objects.create(
                sale=sale,
                amount=paid,
                paid_at=sale.sold_at,
            )

        return True, sale


def _products_with_line_value():
    return Product.objects.annotate(
        line_value=ExpressionWrapper(
            F('price') * F('stock_quantity'),
            output_field=DecimalField(max_digits=18, decimal_places=2),
        )
    )


class StockDashboardView(LoginRequiredMixin, View):
    login_url = '/'
    template_name = 'stock/dashboard.html'

    def get(self, request):
        editing = None
        form = ProductForm()
        edit_pk = request.GET.get('edit')
        if edit_pk:
            try:
                pk = int(edit_pk, base=10)
            except (TypeError, ValueError):
                messages.error(request, 'অবৈধ পণ্য নির্বাচন।')
                return redirect('stock:dashboard')
            editing = get_object_or_404(Product, pk=pk)
            form = ProductForm(instance=editing)
        return render(
            request,
            self.template_name,
            self._ctx(request, product_form=form, editing_product=editing),
        )

    def post(self, request):
        if 'add_product' in request.POST:
            pf = ProductForm(request.POST)
            if pf.is_valid():
                pf.save()
                messages.success(request, 'পণ্য যোগ হয়েছে।')
                return redirect('stock:dashboard')
            return render(request, self.template_name, self._ctx(request, product_form=pf))

        if 'update_product' in request.POST:
            try:
                pk = int(request.POST.get('product_id', ''), base=10)
            except (TypeError, ValueError):
                messages.error(request, 'অবৈধ অনুরোধ।')
                return redirect('stock:dashboard')
            product = get_object_or_404(Product, pk=pk)
            pf = ProductForm(request.POST, instance=product)
            if pf.is_valid():
                pf.save()
                messages.success(request, 'পণ্য আপডেট হয়েছে।')
                return redirect('stock:dashboard')
            return render(
                request,
                self.template_name,
                self._ctx(request, product_form=pf, editing_product=product),
            )

        if 'delete_product' in request.POST:
            try:
                pk = int(request.POST.get('product_id', ''), base=10)
            except (TypeError, ValueError):
                messages.error(request, 'অবৈধ অনুরোধ।')
                return redirect('stock:dashboard')
            product = get_object_or_404(Product, pk=pk)
            label = product.name
            try:
                product.delete()
            except ProtectedError:
                messages.error(
                    request,
                    'এই পণ্যের ওপর বিক্রয় রেকর্ড থাকায় মুছে ফেলা যাবে না।',
                )
                return redirect('stock:dashboard')
            messages.success(request, f'«{label}» মুছে ফেলা হয়েছে।')
            return redirect('stock:dashboard')

        return redirect('stock:dashboard')

    def _ctx(self, request, product_form=None, editing_product=None):
        qs = _products_with_line_value()
        grand = qs.aggregate(grand=Sum('line_value'))['grand']
        paginator = Paginator(qs.order_by('name'), PAGE_SIZE)
        products_page = paginator.get_page(request.GET.get('page'))
        return {
            'products_page': products_page,
            'stock_total_value': grand if grand is not None else Decimal('0'),
            'product_form': product_form if product_form is not None else ProductForm(),
            'editing_product': editing_product,
        }


class SalePrintView(LoginRequiredMixin, View):
    """ক্রেতা ও অর্ডার প্রিন্টের জন্য সরল পাতা।"""

    login_url = '/'
    template_name = 'stock/sale_print.html'

    def get(self, request, pk):
        sale = get_object_or_404(
            DailySell.objects.prefetch_related('lines__product'),
            pk=pk,
        )
        return render(request, self.template_name, {'sale': sale})


class DailySellView(LoginRequiredMixin, View):
    login_url = '/'
    template_name = 'stock/daily_sell.html'

    def get(self, request):
        sale_pk = request.GET.get('sale_edit')
        if sale_pk:
            try:
                pk = int(sale_pk, base=10)
            except (TypeError, ValueError):
                messages.error(request, 'অবৈধ বিক্রয় নির্বাচন।')
                return redirect('stock:daily_sell')
            sale = get_object_or_404(
                DailySell.objects.prefetch_related(
                    Prefetch(
                        'payment_entries',
                        queryset=DailySellPayment.objects.order_by('paid_at', 'id'),
                    ),
                    'lines__product',
                ),
                pk=pk,
            )
            form = DailySellEditForm(instance=sale)
            return render(
                request,
                self.template_name,
                self._ctx(request, form, editing_sale=sale),
            )
        return render(
            request,
            self.template_name,
            self._ctx(
                request,
                order_form=DailySellOrderForm(),
                line_formset=get_sale_line_formset(),
            ),
        )

    def post(self, request):
        if 'update_sale' in request.POST:
            try:
                pk = int(request.POST.get('sale_id', ''), base=10)
            except (TypeError, ValueError):
                messages.error(request, 'অবৈধ অনুরোধ।')
                return redirect('stock:daily_sell')
            sale = get_object_or_404(
                DailySell.objects.prefetch_related(
                    Prefetch(
                        'payment_entries',
                        queryset=DailySellPayment.objects.order_by('paid_at', 'id'),
                    ),
                    'lines__product',
                ),
                pk=pk,
            )
            log_edited = False
            try:
                with transaction.atomic():
                    log_edited = _apply_payment_log_edits(sale, request.POST)
            except ValidationError as exc:
                sale.refresh_from_db()
                form = DailySellEditForm(request.POST, instance=sale)
                msg = exc.messages[0] if getattr(exc, 'messages', None) else str(exc)
                form.add_error(None, msg)
                return render(
                    request,
                    self.template_name,
                    self._ctx(request, form, editing_sale=sale),
                )
            sale.refresh_from_db()
            form = DailySellEditForm(request.POST, instance=sale)
            if form.is_valid():
                paid_chunk = form.cleaned_data.get('payment_add') or Decimal('0')
                form.save()
                if log_edited and paid_chunk > 0:
                    messages.success(
                        request,
                        'জমার খাতা ও নতুন পরিশোধ আপডেট হয়েছে।',
                    )
                elif log_edited:
                    messages.success(
                        request,
                        'জমার খাতা আপডেট হয়েছে; মোট পরিশোধ ও বাকি ঠিক করা হয়েছে।',
                    )
                elif paid_chunk > 0:
                    messages.success(
                        request,
                        'পরিশোধের রেকর্ড যোগ হয়েছে; মোট পরিশোধ ও বাকি আপডেট হয়েছে।',
                    )
                else:
                    messages.success(request, 'বিক্রয় তথ্য আপডেট হয়েছে।')
                return self._redirect_after_sale(request)
            return render(
                request,
                self.template_name,
                self._ctx(request, form, editing_sale=sale),
            )

        order_form = DailySellOrderForm(request.POST)
        line_formset = get_sale_line_formset(request.POST)
        if order_form.is_valid() and line_formset.is_valid():
            try:
                ok, _sale = _commit_new_sale(order_form, line_formset)
            except ValidationError as e:
                _apply_validation_errors(order_form, e)
                return render(
                    request,
                    self.template_name,
                    self._ctx(
                        request,
                        order_form=order_form,
                        line_formset=line_formset,
                    ),
                )
            if ok:
                messages.success(
                    request,
                    'বিক্রয় রেকর্ড হয়েছে; স্টক আপডেট হয়েছে।',
                )
                return self._redirect_after_sale(request)
        return render(
            request,
            self.template_name,
            self._ctx(
                request,
                order_form=order_form,
                line_formset=line_formset,
            ),
        )

    def _redirect_after_sale(self, request):
        page = request.POST.get('_sales_page')
        base = reverse('stock:daily_sell')
        if page and page != '1':
            return redirect(f'{base}?page={page}')
        return redirect(base)

    def _ctx(
        self,
        request,
        form=None,
        order_form=None,
        line_formset=None,
        editing_sale=None,
    ):
        meta = {
            str(p.pk): {'stock': p.stock_quantity, 'price': str(p.price)}
            for p in Product.objects.all()
        }
        sales_qs = DailySell.objects.prefetch_related('lines__product').order_by(
            '-sold_at'
        )
        page_arg = request.GET.get('page') or request.POST.get('_sales_page')
        sales_page = Paginator(sales_qs, PAGE_SIZE).get_page(page_arg)
        return {
            'form': form,
            'order_form': order_form,
            'line_formset': line_formset,
            'sale_meta': meta,
            'has_stock': Product.objects.filter(stock_quantity__gt=0).exists(),
            'sales_page': sales_page,
            'editing_sale': editing_sale,
        }
