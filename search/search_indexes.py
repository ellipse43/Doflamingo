# -*- coding:utf-8 -*-

from __future__ import unicode_literals

import traceback
from haystack import indexes

from oscar.core.loading import get_model, get_class

from django.conf import settings

# Load default strategy (without a user/request)
is_solr_supported = get_class('search.features', 'is_solr_supported')
Selector = get_class('partner.strategy', 'Selector')
strategy = Selector().strategy()


# fix
ProductAttributeValue = get_model('catalogue', 'ProductAttributeValue')
AttributeOptionGroup = get_model('catalogue', 'AttributeOptionGroup')


class ProductIndex(indexes.SearchIndex, indexes.Indexable):
    # Search text
    text = indexes.EdgeNgramField(
        document=True, use_template=True,
        template_name='oscar/search/indexes/product/item_text.txt')

    upc = indexes.CharField(model_attr="upc", null=True)
    title = indexes.EdgeNgramField(model_attr='title', null=True)

    # Fields for faceting
    product_class = indexes.CharField(null=True, faceted=True)
    category = indexes.MultiValueField(null=True, faceted=True)
    price = indexes.DecimalField(null=True, faceted=True)
    num_in_stock = indexes.IntegerField(null=True, faceted=True)
    rating = indexes.IntegerField(null=True, faceted=True)

    # Spelling suggestions
    suggestions = indexes.FacetCharField()

    date_created = indexes.DateTimeField(model_attr='date_created')
    date_updated = indexes.DateTimeField(model_attr='date_updated')

    # fix -> Extra
    price_range = indexes.CharField(null=True, faceted=True)

    _vars = vars()
    for option in AttributeOptionGroup.objects.all():
        _vars[option.name] = indexes.CharField(null=True, faceted=True)
    del _vars

    def get_model(self):
        return get_model('catalogue', 'Product')

    def index_queryset(self, using=None):
        # Only index browsable products (not each individual child product)
        return self.get_model().browsable.order_by('-date_updated')

    def read_queryset(self, using=None):
        return self.get_model().browsable.base_queryset()

    def prepare_product_class(self, obj):
        return obj.get_product_class().name

    def prepare_category(self, obj):
        categories = obj.categories.all()
        if len(categories) > 0:
            return [category.full_name for category in categories]

    def prepare_rating(self, obj):
        if obj.rating is not None:
            return int(obj.rating)

    # Pricing and stock is tricky as it can vary per customer.  However, the
    # most common case is for customers to see the same prices and stock levels
    # and so we implement that case here.

    def prepare_price(self, obj):
        result = None
        if obj.is_parent:
            result = strategy.fetch_for_parent(obj)
        elif obj.has_stockrecords:
            result = strategy.fetch_for_product(obj)

        if result:
            if result.price.is_tax_known:
                return result.price.incl_tax
            return result.price.excl_tax

    def prepare_num_in_stock(self, obj):
        if obj.is_parent:
            # Don't return a stock level for parent products
            return None
        elif obj.has_stockrecords:
            result = strategy.fetch_for_product(obj)
            return result.stockrecord.net_stock_level

    # fix
    # def prepare_brand(self, obj):
    #     try:
    #         attr = obj.attributes.get(code='brand')
    #         return ProductAttributeValue.objects.get(attribute=attr, product=obj).value.option
    #     except:
    # traceback.print_exc()
    #         return None

    def prepare_price_range(self, obj):
        result = None
        if obj.is_parent:
            result = strategy.fetch_for_parent(obj)
        elif obj.has_stockrecords:
            result = strategy.fetch_for_product(obj)

        price = None
        if result:
            if result.price.is_tax_known:
                price = float(result.price.incl_tax)
            price = float(result.price.excl_tax)

        if price is not None:
            breakpoints = [0, 20, 40, 60]
            breakpoints = sorted(breakpoints)
            if 0 not in breakpoints:
                breakpoints = [0] + breakpoints

            for index, upper in enumerate(breakpoints[1:]):
                lower = breakpoints[index]
                if lower <= price <= upper:
                    return '%s-%s' % (lower, upper)
            return '%s+' % upper

    def prepare(self, obj):
        prepared_data = super(ProductIndex, self).prepare(obj)

        # We use Haystack's dynamic fields to ensure that the title field used
        # for sorting is of type "string'.
        if is_solr_supported():
            prepared_data['title_s'] = prepared_data['title']

        # Use title to for spelling suggestions
        prepared_data['suggestions'] = prepared_data['text']

        # fix -> Product Options -> error with sqs display

        for attr in obj.attributes.all():
            if attr.is_option:
                try:
                    prepared_data[attr.code] = str(
                        ProductAttributeValue.objects.get(attribute=attr, product=obj).value.option)
                except:
                    traceback.print_exc()

        return prepared_data

    def get_updated_field(self):
        """
        Used to specify the field used to determine if an object has been
        updated

        Can be used to filter the query set when updating the index
        """
        return 'date_updated'
