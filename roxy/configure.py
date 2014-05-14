import os
import logging
import logging.config
import importlib
from ConfigParser import SafeConfigParser, NoSectionError

from dateutil.tz import tzutc, gettz
import sqlalchemy
from jinja2 import FileSystemLoader, Environment

import roxy.model as model
import roxy.util as util

logger = None
config = None


def _configure_list(config, *keys):
    for k in keys:
        config[k] = map(lambda s: s.strip(), config[k].split('\n'))

    return config



def configure(arguments):
    global config
    global logger

    site_name = arguments['<site>']
    here = os.getcwd()
    config_file = arguments['--config']

    # logging
    logging.config.fileConfig(config_file)
    logger = logging.getLogger('roxy')

    # config parser
    parser = SafeConfigParser(dict(here=here))
    with open(config_file, 'rb') as fp:
        parser.readfp(fp)

    # sqlalchemy
    content_store = '{}.content'.format(site_name)
    dsn = 'sqlite:///{}/{}'.format(here, content_store)
    engine = sqlalchemy.create_engine(dsn, encoding='utf8')
    model.initialize(engine, create=arguments['initialize'])
    logger.info("using content store {}".format(content_store))
    logger.debug("dsn {}".format(dsn))

    # globals
    try:
        roxy = dict(parser.items('roxy'))

    except NoSectionError:
        roxy = {}

    # post-process ini values
    site = "site:{}".format(site_name)
    site = dict(parser.items(site))
    site.pop('here')

    roxy.update(site)
    roxy['site'] = site_name

    # document_formats
    _configure_list(roxy, 'document_formats')
    roxy['document_formats'] = map(lambda s: s.lower(), roxy['document_formats'])

    # timezone
    if 'timezone' in roxy:
        roxy['timezone'] = gettz(roxy['timezone'])
    else:
        roxy['timezone'] = tzutc()

    # renderer
    jinja2 = dict(parser.items('jinja2'))
    _configure_list(jinja2, 'filters')
    loader = FileSystemLoader(roxy['template_path'])
    env = Environment(loader=loader)

    for m in jinja2['filters']:
        m = importlib.import_module(m)
        for name in dir(m):
            if name.endswith('_filter'):
                fname = name.split('_filter', 1)[0]
                logger.debug('installing {} filter', fname)
                env.filters[fname] = getattr(m, name)

    roxy['renderer'] = env

    config = roxy
    return roxy


def current_config():
    return config
