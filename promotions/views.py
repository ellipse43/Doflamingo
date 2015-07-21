# -*- coding: utf-8 -*-

from django.views.generic import TemplateView, RedirectView
from django.core.urlresolvers import reverse


class HomeView(TemplateView):

    """
    This is the home page and will typically live at /
    """
    template_name = 'promotions/ihome.html'
