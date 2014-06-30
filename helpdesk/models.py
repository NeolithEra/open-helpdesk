# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models
try:
    from django.db.transaction import atomic
except ImportError:  # pragma: no cover
    from django.db.transaction import commit_on_success as atomic

from django.contrib.admin.templatetags.admin_urls import admin_urlname
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.template.defaultfilters import truncatewords
from django.utils.encoding import python_2_unicode_compatible
from django.utils.html import strip_tags
from django.utils.translation import ugettext_lazy as _

from mezzanine.conf import settings
from mezzanine.core.models import RichText, SiteRelated, TimeStamped
from mezzanine.utils.models import (upload_to, get_user_model_name,
                                    get_user_model)

from model_utils.models import StatusModel
from model_utils import Choices

from .core import (TICKET_STATUSES, TicketIsNotNewError, TicketIsNotOpenError,
                   TicketStatusError, TicketIsClosedError)
from .managers import HeldeskableManager


User = get_user_model()
user_model_name = get_user_model_name()


PRIORITY_URGENT = 8
PRIORITY_HIGH = 4
PRIORITY_NORMAL = 2
PRIORITY_LOW = 1

PRIORITIES = (
    (PRIORITY_URGENT, _('Urgent')),
    (PRIORITY_HIGH, _('High')),
    (PRIORITY_NORMAL, _('Normal')),
    (PRIORITY_LOW, _('Low')),
)


class HelpdeskUser(User):
    class Meta:
        proxy = True

    @property
    def group_names(self):
        return self.groups.values_list('name', flat=True)

    def is_requester(self):
        """Test if user belong to settings.HELPDESK_REQUESTERS group."""
        if settings.HELPDESK_REQUESTERS in self.group_names:
            return True
        return False

    def is_operator(self):
        """Test if user belong to settings.HELPDESK_OPERATORS group."""
        if settings.HELPDESK_OPERATORS in self.group_names:
            return True
        return False

    def is_admin(self):
        """Test if user belong to settings.HELPDESK_ADMINS group."""
        if settings.HELPDESK_ADMINS in self.group_names:
            return True
        return False

    def get_messages_by_ticket(self, ticket_id):
        """
        Returns all Messages object filterd by 'ticket_id' parameter and
        by sender or recipient is self user. Queryset is ordered by createion
        date.

        :param ticket_id: ticket id
        :return: recordset of Message objects
        """
        messages = Message.objects.select_related(
            'sender', 'recipient').filter(ticket_id=ticket_id).filter(
                Q(sender__id=self.id) |
                Q(recipient__id=self.id)).order_by('created')
        return messages


@python_2_unicode_compatible
class Category(TimeStamped):
    title = models.CharField(_('Title'), max_length=500, unique=True)

    class Meta:
        verbose_name = _('Category')
        verbose_name_plural = _('Categories')
        ordering = ('title',)

    def __str__(self):
        return self.title

    @property
    def tipology_pks(self):
        return [str(pk) for pk in self.tipologies.values_list('pk', flat=True)]

    def admin_tipologies(self):
        return '<br>'.join(
            ['<a href="{}?id={}" class="view_tipology">{}</a>'.format(
                reverse(admin_urlname(t._meta, 'changelist')), t.pk, t.title)
             for t in self.tipologies.all()])
    admin_tipologies.allow_tags = True
    admin_tipologies.short_description = _('Tipologies')


@python_2_unicode_compatible
class Tipology(TimeStamped):
    """
    Model for tipologies of tickets. Field sites is a 'ManyToManyField'
    because one tipology can be visible on more sites.
    """
    title = models.CharField(_('Title'), max_length=500)
    category = models.ForeignKey('Category',
                                 verbose_name=_('Categories'),
                                 related_name='tipologies')
    sites = models.ManyToManyField('sites.Site', blank=True,
                                   verbose_name=_('Enable on Sites'),
                                   related_name='tipologies')
    priority = models.IntegerField(_('Priority'), choices=PRIORITIES,
                                   default=PRIORITY_LOW)

    class Meta:
        verbose_name = _('Tipology')
        verbose_name_plural = _('Tipologies')
        ordering = ('category__title', 'title',)
        unique_together = ('title', 'category',)

    def __str__(self):
        return '[{self.category.title}] {self.title}'.format(self=self)

    def admin_category(self):
        return (
            '<a href="{url}?id={category.pk}" class="view_category">'
            '{category.title}</a>'.format(
                url=reverse('admin:helpdesk_category_changelist'),
                category=self.category))
    admin_category.allow_tags = True
    admin_category.admin_order_field = 'category'
    admin_category.short_description = _('Enable on Sites')

    def admin_sites(self):
        return '<br>'.join(
            ['<a href="{url}?id={site.pk}" class="view_site">{site.domain}'
             '</a>'.format(url=reverse(admin_urlname(s._meta, 'changelist')),
                           site=s)
             for s in self.sites.all()])
    admin_sites.allow_tags = True
    admin_sites.short_description = _('Enable on Sites')


class Attachment(TimeStamped):
    f = models.FileField(verbose_name=_('File'),
                         upload_to=upload_to('helpdesk.Issue.attachments',
                                             'helpdesk/attachments'), )
    description = models.CharField(_('Description'), max_length=500)
    ticket = models.ForeignKey('Ticket', blank=True, null=True  )

    class Meta:
        verbose_name = _('Attachment')
        verbose_name_plural = _('Attachments')
        ordering = ('-created',)


@python_2_unicode_compatible
class Ticket(SiteRelated, TimeStamped, RichText, StatusModel):
    STATUS = Choices(*TICKET_STATUSES)
    tipologies = models.ManyToManyField('Tipology',
                                        verbose_name=_('Tipologies'))
    priority = models.IntegerField(_('Priority'), choices=PRIORITIES,
                                   default=PRIORITY_LOW)
    requester = models.ForeignKey(user_model_name, verbose_name=_('Requester'),
                                  related_name='requested_tickets')
    assignee = models.ForeignKey(user_model_name, verbose_name=_('Assignee'),
                                 related_name="assigned_tickets",
                                 blank=True, null=True)
    related_tickets = models.ManyToManyField(
        'self', verbose_name=_('Related tickets'), blank=True)

    objects = HeldeskableManager()

    class Meta:
        get_latest_by = 'created'
        ordering = ('-created',)
        verbose_name = _('Ticket')
        verbose_name_plural = _('Tickets')

    def __str__(self):
        return str(self.pk)

    def get_clean_content(self, words=10):
        """
        Return self.content with html tags stripped and truncate after a
        "words" number of words with use of django template filter
        'truncatewords'.

        :param words: Number of words to truncate after
        """
        return truncatewords(strip_tags(self.content), words)

    def admin_content(self):
        return self.get_clean_content(words=12)
    admin_content.short_description = _('Content')

    def admin_readonly_content(self):
        return '<div style="width: 85%; float:right;">{}</div>'.format(
            self.content)
    admin_readonly_content.short_description = 'Content'
    admin_readonly_content.allow_tags = True

    @atomic
    def change_state(self, before, after, user):
        """Change status of ticket an record changelog for this.

        :param before: Ticket.STATUS, status that will be
        :param after: Ticket.STATUS, status before changing
        :param user: django.contrib.auth.get_user_model
        :return: boolean
        """
        self.status = after
        self.save()
        self.status_changelogs.create(before=before,
                                      after=after,
                                      changer=user)
        return True

    @atomic
    def opening(self, assignee):
        """Logic 'open' ticket operation.

        Opening the ticket. Set status to open, assignee user and create an
        StatusChangesLog.

        :param assignee: user to set 'assignee' field
        :type assignee: django.contrib.auth.get_user_model
        """
        if self.status != Ticket.STATUS.new:
            raise TicketIsNotNewError()
        self.change_state(Ticket.STATUS.new, Ticket.STATUS.open, assignee)
        self.assignee = assignee
        self.save()

    @atomic
    def put_on_pending(self, user):
        """Logic 'put_on_pending' ticket operation.

        Set status to pending and create an StatusChangesLog object.

        :param user: user to set into status_changelogs related object
        :type user: django.contrib.auth.get_user_model
        """
        if self.status != Ticket.STATUS.open:
            raise TicketIsNotOpenError()
        self.change_state(Ticket.STATUS.open, Ticket.STATUS.pending, user)

    @atomic
    def closing(self, user):
        """Logic 'closing' ticket operation.

        Closing the ticket. Set status to closed and create an
        StatusChangesLog object.

        :param user: user to set 'user' field
        :type user: django.contrib.auth.get_user_model
        """
        if self.status == Ticket.STATUS.closed:
            raise TicketIsClosedError()
        if self.status == Ticket.STATUS.new:
            raise TicketStatusError("The ticket is still open")
        self.change_state(self.status, Ticket.STATUS.closed, user)


@python_2_unicode_compatible
class Message(TimeStamped):
    content = models.TextField(_('Content'))
    sender = models.ForeignKey(user_model_name, verbose_name=_('Sender'),
                               related_name='sender_of_messages')
    recipient = models.ForeignKey(user_model_name, verbose_name=_('Recipient'),
                                  blank=True, null=True,
                                  related_name='recipent_of_messages')
    ticket = models.ForeignKey('Ticket', related_name='messages',
                               blank=True, null=True, verbose_name=_('Ticket'))

    class Meta:
        get_latest_by = 'created'
        ordering = ('-created',)
        verbose_name = _('Message')
        verbose_name_plural = _('Messages')

    def __str__(self):
        return self.content


@python_2_unicode_compatible
class Report(Message):
    action_on_ticket = models.IntegerField(blank=True, null=True)
    visible_from_requester = models.BooleanField(default=True)

    class Meta:
        get_latest_by = 'created'
        ordering = ('-created',)
        verbose_name = _('Report')
        verbose_name_plural = _('Reports')

    def __str__(self):
        return self.content


@python_2_unicode_compatible
class Activity(TimeStamped, RichText):
    maker = models.ForeignKey(user_model_name, verbose_name=_('Maker'),
                              related_name='maker_of_activities')
    co_maker = models.ManyToManyField(user_model_name,
                                      verbose_name=_('Co Makers'),
                                      blank=True, null=True,
                                      related_name='co_maker_of_activities')
    ticket = models.ForeignKey('Ticket', related_name='activities',
                               blank=True, null=True)
    report = models.OneToOneField('Report', blank=True, null=True)
    scheduled_at = models.DateTimeField(blank=True, null=True,
                                        verbose_name=_('Scheduled at'))

    class Meta:
        get_latest_by = 'created'
        ordering = ('-created',)
        verbose_name = _('Activity')
        verbose_name_plural = _('Activities')

    def __str__(self):
        return self.content


@python_2_unicode_compatible
class StatusChangesLog(TimeStamped):
    """
    StatusChangesLog model for record the changes of status of Tickets objects.
    """
    ticket = models.ForeignKey('Ticket', related_name='status_changelogs')
    before = models.CharField(max_length=100)
    after = models.CharField(max_length=100)
    changer = models.ForeignKey(user_model_name, verbose_name=_('Changer'))

    class Meta:
        get_latest_by = 'created'
        ordering = ('ticket', 'created')
        verbose_name = _('Status Changelog')
        verbose_name_plural = _('Status Changelogs')

    def __str__(self):
        return ('{self.ticket_id} {created}: {self.before} ==> '
                '{self.after}'.format(self=self,
                                      created=self.created.strftime(
                                          '%Y-%m-%d %H:%M:%S')))
