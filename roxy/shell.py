import os
import sys
import logging
import logging.config
from ConfigParser import SafeConfigParser
from datetime import datetime

import sqlalchemy
from docopt import docopt

import roxy.util as util
import roxy.model as model
from roxy.model import Site, Content, Tag, Property


logger = None


def configure(arguments):
    global logger

    site_name = arguments['<site>']
    here = os.getcwd()

    # config parser
    parser = SafeConfigParser(dict(here=here))
    config_file = arguments['--config']
    with open(config_file, 'rb') as fp:
        parser.readfp(fp)

    # logging
    logging.config.fileConfig(config_file)
    logger = logging.getLogger('roxy')

    # sqlalchemy
    content_store = '{}.content'.format(site_name)
    dsn = 'sqlite:///{}/{}'.format(here, content_store)
    engine = sqlalchemy.create_engine(dsn, encoding='utf8')
    model.initialize(engine, create=arguments['initialize'])
    logger.info("using content store {}".format(content_store))
    logger.debug("dsn {}".format(dsn))

    # post-process ini values
    section = "site:{}".format(site_name)
    section = dict(parser.items(section))
    section.pop('here')

    _configure_list(section, 'document_formats')
    section['document_formats'] = map(lambda s: s.lower(), section['document_formats'])

    return section


def main(argv=sys.argv):
    arguments = docopt(__doc__)
    config = configure(arguments)


