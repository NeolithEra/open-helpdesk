# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import

import pytest


@pytest.fixture
def rf_with_helpdeskuser(request, rf):
    rf.user = None
    if getattr(request, 'cls', None):
        class HelpdeskUser(object):
            def is_requester(self):
                return getattr(request.cls, 'is_requester', False)

            def is_operator(self):
                return getattr(request.cls, 'is_operator', False)

            def is_admin(self):
                return getattr(request.cls, 'is_admin', False)
        rf.user = HelpdeskUser()
    return rf


def get_tipologies(n_tipologies):
    from django.contrib.sites.models import Site
    from .factories import CategoryFactory, TipologyFactory
    from .settings_base import SITE_ID
    category = CategoryFactory()
    site = Site.objects.get(pk=SITE_ID)
    tipologies = [
        TipologyFactory(sites=(site,), category=category).pk
        for i in range(0, n_tipologies)]
    return tipologies


@pytest.fixture
def tipologies():
    return get_tipologies(2)


@pytest.fixture(scope='class')
def tipologies_cls(request):
    setattr(request.cls, 'tipologies', get_tipologies(5))


@pytest.fixture(scope='module')
def ticket_content(scope='module'):
    return ("foo " * 20).rstrip()