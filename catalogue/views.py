# -*- coding: utf-8 -*-

import warnings
from django.contrib import messages
from django.core.paginator import InvalidPage
from django.utils.http import urlquote
from django.http import HttpResponsePermanentRedirect, Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import DetailView, TemplateView
from django.utils.translation import ugettext_lazy as _

from oscar.core.loading import get_class, get_model
from oscar.apps.catalogue.signals import product_viewed

Product = get_model('catalogue', 'product')
ProductReview = get_model('reviews', 'ProductReview')
Category = get_model('catalogue', 'category')
ProductAlert = get_model('customer', 'ProductAlert')
ProductAlertForm = get_class('customer.forms', 'ProductAlertForm')
get_product_search_handler_class = get_class(
    'catalogue.search_handlers', 'get_product_search_handler_class')


class ProductCategoryView(TemplateView):

    """
    Browse products in a given category
    """
    context_object_name = "products"
    template_name = 'catalogue/icategory.html'
    enforce_paths = True

    def get(self, request, *args, **kwargs):
        # Fetch the category; return 404 or redirect as needed
        self.category = self.get_category()
        potential_redirect = self.redirect_if_necessary(
            request.path, self.category)
        if potential_redirect is not None:
            return potential_redirect

        try:
            self.search_handler = self.get_search_handler(
                request.GET, request.get_full_path(), self.get_categories())
        except InvalidPage:
            messages.error(request, _('The given page number was invalid.'))
            return redirect(self.category.get_absolute_url())

        return super(ProductCategoryView, self).get(request, *args, **kwargs)

    def get_category(self):
        if 'pk' in self.kwargs:
            # Usual way to reach a category page. We just look at the primary
            # key, which is easy on the database. If the slug changed, get()
            # will redirect appropriately.
            # WARNING: Category.get_absolute_url needs to look up it's parents
            # to compute the URL. As this is slightly expensive, Oscar's
            # default implementation caches the method. That's pretty safe
            # as ProductCategoryView does the lookup by primary key, which
            # will work even if the cache is stale. But if you override this
            # logic, consider if that still holds true.
            return get_object_or_404(Category, pk=self.kwargs['pk'])
        elif 'category_slug' in self.kwargs:
            # DEPRECATED. TODO: Remove in Oscar 1.2.
            # For SEO and legacy reasons, we allow chopping off the primary
            # key from the URL. In that case, we have the target category slug
            # and it's ancestors' slugs concatenated together.
            # To save on queries, we pick the last slug, look up all matching
            # categories and only then compare.
            # Note that currently we enforce uniqueness of slugs, but as that
            # might feasibly change soon, it makes sense to be forgiving here.
            concatenated_slugs = self.kwargs['category_slug']
            slugs = concatenated_slugs.split(Category._slug_separator)
            try:
                last_slug = slugs[-1]
            except IndexError:
                raise Http404
            else:
                for category in Category.objects.filter(slug=last_slug):
                    if category.full_slug == concatenated_slugs:
                        message = (
                            "Accessing categories without a primary key"
                            " is deprecated will be removed in Oscar 1.2.")
                        warnings.warn(message, DeprecationWarning)

                        return category

        raise Http404

    def redirect_if_necessary(self, current_path, category):
        if self.enforce_paths:
            # Categories are fetched by primary key to allow slug changes.
            # If the slug has changed, issue a redirect.
            expected_path = category.get_absolute_url()
            if expected_path != urlquote(current_path):
                return HttpResponsePermanentRedirect(expected_path)

    def get_search_handler(self, *args, **kwargs):
        return get_product_search_handler_class()(*args, **kwargs)

    def get_categories(self):
        """
        Return a list of the current category and its ancestors
        """
        return self.category.get_descendants_and_self()

    def get_context_data(self, **kwargs):
        context = super(ProductCategoryView, self).get_context_data(**kwargs)
        context['category'] = self.category
        search_context = self.search_handler.get_search_context_data(
            self.context_object_name)
        context.update(search_context)
        return context
