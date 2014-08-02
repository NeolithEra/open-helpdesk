# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import

import pytest
from django.contrib.admin.templatetags.admin_urls import admin_urlname
from django.core.urlresolvers import reverse

from openhelpdesk.models import Ticket, PRIORITY_NORMAL


pytestmark = pytest.mark.django_db


@pytest.fixture
def add_form_data(tipologies, ticket_content):
    class FormData(object):
        def __init__(self):
            self.content = ticket_content
            self.priority = PRIORITY_NORMAL
            self.tipologies = [t.pk for t in tipologies[0:2]]
    return FormData()

@pytest.fixture(scope='class')
def add_url(request):
    setattr(request.cls, 'url', reverse(admin_urlname(Ticket._meta, 'add')))


@pytest.mark.usefixtures('add_url')
class TestAddingTicketByRequester(object):
    def test_requester_field_is_setted_with_current_logged_user(
            self, app, requester, add_form_data):
        response = app.get(self.url, user=requester)
        form = response.forms['ticket_form']
        form['content'] = add_form_data.content
        form['priority'] = add_form_data.priority
        form['tipologies'] = add_form_data.tipologies
        form.submit('_save')
        ticket = Ticket.objects.latest()
        assert ticket.requester.pk == requester.pk
        assert ticket.priority == PRIORITY_NORMAL
        assert ticket.content in ticket.content
        assert (set(ticket.tipologies.values_list('pk', flat=True))
                == set(add_form_data.tipologies))

    def test_statuschangelog_obj_is_created(
            self, app, requester, add_form_data):
        response = app.get(reverse(admin_urlname(Ticket._meta, 'add')),
                           user=requester)
        form = response.forms['ticket_form']
        form['content'] = add_form_data.content
        form['priority'] = add_form_data.priority
        form['tipologies'] = add_form_data.tipologies
        form.submit('_continue')
        assert Ticket.objects.count() == 1
        ticket = Ticket.objects.latest()
        assert ticket.status_changelogs.count() == 1
        statuschangelog = ticket.status_changelogs.all()[0]
        assert statuschangelog.before == ''
        assert statuschangelog.after == Ticket.STATUS.new
        assert statuschangelog.changer.pk == requester.pk


class TestChangingTicketByRequester(object):
    def test_set_sender_field_on_change_ticket_inserting_message_obj(
            self, app, opened_ticket):
        """
        Test for testing custom "save_formset" method of TicketAdmin. From
        ticket change view is added a new message object and "save_formset"
        set sender field of message object to request.user
        """
        assert len(opened_ticket.messages.all()) == 0
        response = app.get(
            reverse('admin:openhelpdesk_ticket_change', args=(opened_ticket.pk,)),
            user=opened_ticket.requester)
        form = response.forms['ticket_form']
        form['messages-0-content'] = 'foo'
        form.submit('_save')
        message = opened_ticket.messages.latest()
        assert message.sender_id == opened_ticket.requester_id