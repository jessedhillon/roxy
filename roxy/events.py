import logging

logger = logging.getLogger('roxy')


class Event(object):
    def __init__(self, name):
        self.name = name
        self.subscribers = []

    def subscribe(self, subscriber):
        self.subscribers.append(subscriber)
        return subscriber

    def fire(self, *args, **kwargs):
        if self.subscribers:
            logger.debug('firing {!r}'.format(self))

        for s in self.subscribers:
            result = s(*args, **kwargs)
            if result is False:
                break

    def __unicode__(self):
        s = ['.'.join([f.__module__, f.__name__]) for f in self.subscribers]
        return "<Event: {}, subscribers=[{}]>".format(self.name, ', '.join(s))

    __repr__ = __unicode__
    __str__ = __unicode__

BeforeIngest = Event('BeforeIngest')
BeforeGenerate = Event('BeforeGenerate')
BeforeRoute = Event('BeforeRoute')
BeforeRender = Event('BeforeRender')
BeforeWrite = Event('BeforeWrite')

Render = Event('Render')

AfterIngest = Event('AfterIngest')
AfterGenerate = Event('AfterGenerate')
AfterRoute = Event('AfterRoute')
AfterRender = Event('AfterRender')
AfterWrite = Event('AfterWrite')
