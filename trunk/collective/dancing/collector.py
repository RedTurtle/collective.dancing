from zope import component
from zope import interface
from zope import schema
import zope.interface.interface
import zope.schema.vocabulary
import zope.schema.interfaces
import zope.app.container.interfaces
import zope.i18nmessageid
import DateTime
import OFS.Folder

import z3c.form.field
import Products.CMFCore.utils
import Products.CMFPlone.interfaces
import Products.CMFPlone.utils
from Products.ATContentTypes.content.topic import ATTopic
import collective.singing.interfaces

from collective.dancing import utils
from collective.dancing import MessageFactory as _

def collector_vocabulary(context):
    root = component.getUtility(Products.CMFPlone.interfaces.IPloneSiteRoot)
    collectors = root['portal_newsletters']['collectors'].objectValues()
    terms = []
    for collector in collectors:
        terms.append(
            zope.schema.vocabulary.SimpleTerm(
                value=collector,
                token='/'.join(collector.getPhysicalPath()),
                title=collector.title))
    return zope.schema.vocabulary.SimpleVocabulary(terms)
interface.alsoProvides(collector_vocabulary,
                       zope.schema.interfaces.IVocabularyFactory)

class CollectorContainer(OFS.Folder.Folder):
    Title = u"Collectors"

@component.adapter(CollectorContainer,
                   zope.app.container.interfaces.IObjectAddedEvent)
def container_added(container, event):
    name = 'default-latest-news'
    container[name] = Collector(
        name, u"Latest news")
    topic = container[name].objectValues()[0]
    type_crit = topic.addCriterion('Type', 'ATPortalTypeCriterion')
    type_crit.setValue('News Item')
    sort_crit = topic.addCriterion('created', 'ATSortCriterion')
    state_crit = topic.addCriterion('review_state',
                                    'ATSimpleStringCriterion')
    state_crit.setValue('published')
    topic.setSortCriterion('created', True)
    topic.setLayout('folder_summary_view')

class ICollectorSchema(interface.Interface):
    pass

@component.adapter(collective.singing.interfaces.ISubscription)
@interface.implementer(ICollectorSchema)
def collectordata_from_subscription(subscription):
    composer_data = collective.singing.interfaces.ICollectorData(subscription)
    return utils.AttributeToDictProxy(composer_data)

class TextCollector(object):
    interface.implements(collective.singing.interfaces.ICollector)
    title = 'Rich text'
    value = u''

    def __init__(self, id, title):
        self.id = id
        self.title = title

    def get_items(self, cue=None, subscription=None):
        return [self.value], None
    
class ReferenceCollector(object):
    interface.implements(collective.singing.interfaces.ICollector)
    title = 'Reference'
    refered = None

    def __init__(self, id, title):
        self.id = id
        self.title = title

    def get_items(self, cue=None, subscription=None):
        if self.refered:
            return [self.refered], None
        else:
            return [], None

class Collector(OFS.Folder.Folder):
    interface.implements(collective.singing.interfaces.ICollector)
    title = 'Collector block'

    def __init__(self, id, title):
        self.id = id
        self.title = title
        self.optional = False
        super(Collector, self).__init__()

    @property
    def Title(self):
        return self.title

    def get_items(self, cue=None, subscription=None):
        now = DateTime.DateTime()

        # Don't return items if we're optional and not selected:
        if self.optional:
            if subscription is not None:
                sdata = collective.singing.interfaces.ICollectorData(
                    subscription)
                name = 'selected_collectors'
                if name in sdata and sdata[name] and self not in sdata[name]:
                    return [], now

        items = []
        for child in self.objectValues():
            if isinstance(child, ATTopic):
                items.extend(self.get_items_for_topic(child, cue))
            else:
                items.extend(child.get_items(cue, subscription)[0])

        return items, now

    @staticmethod
    def get_items_for_topic(topic, cue):
        query_args = {}
        if cue is not None and topic.hasSortCriterion():
            sort_criterion = topic.getSortCriterion()
            query_args[str(sort_criterion.field)] = dict(
                query=cue, range='min')
        return topic.queryCatalog(full_objects=True, **query_args)
        
    def get_optional_collectors(self):
        optional_collectors = []
        if self.optional:
            optional_collectors.append(self)
        for child in self.objectValues():
            if collective.singing.interfaces.ICollector.providedBy(child):
                m = getattr(child, 'get_optional_collectors', None)
                if m is not None:
                    optional_collectors.extend(m())
                elif child.optional:
                    optional_collectors.append(child)
                
        return optional_collectors

    def get_next_id(self):
        if self._objects:
            return str(max([int(info['id']) for info in self._objects]) + 1)
        else:
            return '0'

    @property
    def schema(self):
        fields = []

        optional_collectors = self.get_optional_collectors()
        if optional_collectors:
            vocabulary = zope.schema.vocabulary.SimpleVocabulary(
                [zope.schema.vocabulary.SimpleTerm(
                    value=collector,
                    token='/'.join(collector.getPhysicalPath()),
                    title=collector.title)
                 for collector in optional_collectors])

            name = 'selected_collectors'
            fields.append(
                (name,
                 zope.schema.Set(
                     __name__=name,
                     title=_(u"Sections"),
                     value_type=zope.schema.Choice(vocabulary=vocabulary))
                 ))

        return zope.interface.interface.InterfaceClass(
            'Schema', bases=(ICollectorSchema,),
            attrs=dict(fields))

    def add_topic(self):
        name = self.get_next_id()
        Products.CMFPlone.utils._createObjectByType(
            'Topic', self, id=name, title='Collection for %s' % self.title)
        self[name].unmarkCreationFlag()

        workflow = Products.CMFCore.utils.getToolByName(self, 'portal_workflow')
        workflow.doActionFor(self[name], 'publish')
        return self[name]

@component.adapter(Collector, zope.app.container.interfaces.IObjectAddedEvent)
def sfc_added(sfc, event):
    sfc.add_topic()

collectors = (Collector,) # TextCollector, ReferenceCollector)
