"""
Generate the site

Usage:
    roxy [--config=INI] generate <site> [--file=FILE]
    roxy [--config=INI] initialize <site> [--file=FILE]
    roxy [--config=INI] shell <site> [--file=FILE]
    roxy (-h | --help)

Options:
    -h, --help              Show this text
    -c INI, --config=INI    Config path [default: site.ini]
    -f FILE, --file=FILE    Content store, defaults to <site>.content
"""
import os
import sys
import logging
import mimetypes
import importlib
import code
from datetime import datetime
from dateutil.tz import tzutc

from docopt import docopt
from jinja2 import TemplateNotFound
from markdown import Markdown
from BeautifulSoup import BeautifulSoup

import roxy.model as model
import roxy.configure as configure
import roxy.util as util
import roxy.generators
from roxy.model import Model, Site, Content, Asset, Tag, Property
from roxy.events import BeforeRender, BeforeIngest, BeforeRoute, BeforeRender,\
    BeforeGenerate, BeforeWrite, AfterIngest, AfterGenerate, AfterRender,\
    AfterRoute, AfterWrite, Render


logger = None


def main(argv=sys.argv):
    global logger

    arguments = docopt(__doc__)
    config = configure.configure(arguments)
    logger = logging.getLogger('roxy')


    try:
        if arguments['generate']:
            generate(arguments, config)

        if arguments['shell']:
            l = {
                'session': model.get_session(),
                'site': Site.get(slug=config['site']),
                'Site': Site,
                'Content': Content,
                'Asset': Asset,
                'Tag': Tag,
                'Property': Property
            }
            code.interact(local=l)

    except Exception as e:
        import traceback
        import sys
        import pdb

        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[2])


def generate(arguments, config):
    session = model.get_session()

    # find site or create if doesn't exist
    site = Site.get(slug=config['site'])
    if not site:
        site = Site(slug=config['site'], name=config['name'], url=config['url'])
        session.add(site)

    # for all content encountered
    BeforeIngest.fire(site, config)

    content = ingest_content(site, config)
    assets = ingest_assets(site, config)

    AfterIngest.fire(site, config, content=content, assets=assets)

    session.add_all(content)
    session.add_all(assets)
    session.commit()


    # import module which generates site
    BeforeGenerate.fire(site, config)
    generator = importlib.import_module(config['generator'])
    AfterGenerate.fire(site, config, generator)

    # iterate over routes
    route_mappings = {}

    BeforeRoute.fire(site, config, route_mappings)
    # route_mappings.update({path: context for path, _, _, context in write_list if isinstance(context, Model)})
    route_mappings.update({a.path: a for a in assets})

    config['renderer'].filters['route'] = make_router(config, route_mappings)
    config['renderer'].filters['fetch'] = make_fetcher(config, route_mappings)
    config['renderer'].filters['render'] = make_renderer(config)
    AfterRoute.fire(site, config, route_mappings)

    # render the documents
    write_list = []
    render_list = []
    BeforeRender.fire(site, config, render_list)

    for path, template, fallback, context in render_list:
        values = {}

        if isinstance(context, Model):
            params = dict(site=site)
            params.update(values)
            keyname = context.__class__.__name__.lower()
            params[keyname] = context
            context = make_context(config, **params)
        else:
            values.update(context)
            context = make_context(config, site=site, **values)

        Render.fire(site, path, template, fallback, context)

        logger.info("rendering {} via {}".format(path, template))
        s = render(config['renderer'], template, fallback, context)
        AfterRender.fire(site, values, path, template, fallback, content, s)
        write_list.append((path, s))

    # process the write list
    BeforeWrite.fire(site, config, write_list)

    for path, s in write_list:
        if path.startswith('/'):
            path = path[1:]
        path = os.path.join(config['build_path'], path)
        logger.info("writing {}".format(path))
        util.write(path, s)

    AfterWrite.fire(site, config, write_list)


def make_context(config, **kwargs):
    values = {}
    values.update(kwargs)
    values['now'] = datetime.utcnow().replace(tzinfo=tzutc()).astimezone(config['timezone'])
    return values


def make_fetcher(config, mappings):
    objects_by_key = {}
    objects_by_slug = {}

    for context in mappings.values():
        if hasattr(context, 'key'):
            objects_by_key[context.key] = context

        if hasattr(context, 'slug'):
            objects_by_slug[context.slug] = context

    def fetcher(key, cls_=None):
        if cls_ is None:
            if key in objects_by_key:
                return objects_by_key[key]

            if key in objects_by_slug:
                return objects_by_slug[key]
        else:
            classes = {
                'content': Content,
                'asset': Asset,
                'tag': Tag
            }
            if cls_.lower() in classes:
                cls = classes[cls_]
                by_key = cls.get(key)
                by_slug = cls.get(slug=key)
                if by_key is not None or by_slug is not None:
                    return by_key or by_slug

        raise KeyError(key)

    return fetcher


def make_router(config, mappings):
    routes_by_key = {}
    routes_by_slug = {}
    for path, context in mappings.items():
        if hasattr(context, 'key'):
            routes_by_key[context.key] = path

        if hasattr(context, 'slug'):
            routes_by_slug[context.slug] = path

    def router(target, absolute=False):
        p = None
        if isinstance(target, Model):
            p = routes_by_key[target.key]

        if hasattr(target, 'key') and target.key in routes_by_key:
            p = routes_by_key[target.key]
        elif hasattr(target, 'slug') and target.slug in routes_by_slug:
            p = routes_by_slug[target.slug]

        if target in routes_by_key:
            p = routes_by_key[target]
        elif target in routes_by_slug:
            p = routes_by_slug[target]

        if p:
            if absolute:
                base = config['url_base']
                return util.url_join(base, p)
            else:
                return p

        raise KeyError(target)

    return router


_md_renderer = None
def make_renderer(config):
    global _md_renderer
    if not _md_renderer:
        _md_renderer = Markdown()
    route = config['renderer'].filters['route']
    fetch = config['renderer'].filters['fetch']

    def render_filter(s):
        md = _md_renderer.convert(s)
        soup = BeautifulSoup(md)

        def is_ref(attr):
            return attr is not None and ':' in attr

        def dereference(attr):
            id, ref = attr.split(':', 1)
            if '.' in ref:
                ref, field = ref.split('.', 1)
                obj = fetch(id, cls_=ref)
                return getattr(obj, field)
            else:
                return route(id)

        def replace_attrs(el, attr, callback):
            for e in soup.findAll(el, attrs={attr: is_ref}):
                a = e.get(attr)
                value = dereference(a)
                callback(e, attr, value)

        replace_attrs('a', 'href', _set_attr)
        replace_attrs('a', 'title', _set_attr)
        replace_attrs('img', 'src', _set_absolute_url)
        replace_attrs('img', 'alt', _set_attr)

        return unicode(soup)

    def _set_absolute_url(el, key, path):
        url = util.url_join(config['url_base'], path)
        _set_attr(el, key, url)

    def _set_attr(el, key, value):
        for i, (k, v) in enumerate(el.attrs):
            if k.lower() == key.lower():
                el.attrs[i] = (k, value)

    return render_filter


def render(renderer, template, fallback, context):
    try:
        template = renderer.get_template(template)
    except TemplateNotFound:
        if fallback:
            template = renderer.get_template(fallback)
        else:
            raise

    return template.render(context)


def ingest_assets(site, config):
    # for each file encountered in asset directory
    asset_files = discover_assets(config['asset_source_path'])
    assets = []

    processors = []
    for path in asset_files:
        relative_path = os.path.relpath(path, config['asset_source_path'])
        m = mimetypes.guess_type(path)
        if m:
            mimetype = m[0].split('/')[0]
        else:
            raise NotImplementedError(m)

        # search for metadata
        mdpath = '{}.metadata'.format(*os.path.splitext(path))
        if os.path.exists(mdpath):
            with open(mdpath, 'rb') as md:
                document = md.read()
                header, body = _parse_content_header(document)
                metadata = _parse_metadata(header, config)
        else:
            metadata = {}

        # compute the file's checksum
        with open(path,'rb') as f:
            checksum = util.checksum(f)

        a = Asset.get(site=site, path=relative_path)

        if a is None:
            a = Asset(site=site, path=relative_path)

        for k, v in metadata.items():
            setattr(a, k, v)

        a.checksum = checksum
        a.site = site
        if body:
            a.body = body
        assets.append(a)

    return assets


def discover_assets(path):
    asset_files = []
    logger.info("crawling {}".format(path))
    for root, dirs, files in os.walk(path):
        for f in files:
            extension = os.path.splitext(f)[-1][1:].lower()
            if extension != 'metadata':
                path = os.path.join(root, f)
                asset_files.append(path)
                logger.debug("collected {}".format(path))

    return asset_files


def ingest_content(site, config):
    # compute allowed extensions
    extensions = []
    for f in config['document_formats']:
        if f == 'markdown':
            extensions.extend(['md', 'markdown'])

    content_files = discover_content(config['content_source_path'], extensions)
    content = []
    for f in content_files:
        relative_path = os.path.relpath(f, config['content_source_path'])
        with open(f, 'rb') as f:
            document = f.read()
            metadata, body = parse_document(document, config)
            c = Content.get(site=site, path=relative_path)

            if c is None:
                c = Content(site=site, path=relative_path)

            for k, v in metadata.items():
                setattr(c, k, v)

            c.body = body
            content.append(c)

    return content


def discover_content(path, extensions):
    content_files = []
    logger.info("crawling {}".format(path))
    for root, dirs, files in os.walk(path):
        for f in files:
            extension = os.path.splitext(f)[-1][1:].lower()
            if extension in extensions:
                path = os.path.join(root, f)
                content_files.append(path)
                logger.debug("collected {}".format(path))
            else:
                logger.debug("ignoring {}".format(path))

        for d in dirs:
            path = os.path.join(root, d)
            content_files.extend(discover_content(path, extensions))

    return content_files


def _parse_content_header(document):
    metadata = []

    lines = (line.strip() for line in document.split('\n'))
    for line in lines:
        line = line.strip()
        # first blank line indicates end of metadata
        if len(line.strip()) == 0:
            break
        metadata.append(line)

    body = '\n'.join(list(lines))
    metadata = '\n'.join(metadata)
    return metadata.decode('utf8'), body.decode('utf8')


def _parse_metadata(document, config):
    # The keywords are case-insensitive and may consist of letters, numbers, 
    # underscores and dashes and must end with a colon. The values consist of
    # anything following the colon on the line and may even be blank.
    #
    # If a line is indented by 4 or more spaces, that line is assumed to be an
    # additional line of the value for the previous keyword. A keyword may have
    # as many lines as desired.
    session = model.get_session()

    meta = {}
    current_key = None
    metadata, _ = _parse_content_header(document)
    for line in metadata.split('\n'):
        line = line.strip()
        # first blank line indicates end of metadata
        if len(line.strip()) == 0:
            break

        # two cases
        # 1) line has a colon in it, split key from value
        # 2) line doesn't, which indicates it continues previous k/v pair
        parts = line.split(':', 1)
        if len(parts) > 1:
            current_key = parts[0].strip().lower()
            # if value is empty string, assume beginning of a list
            value = parts[1].strip()
            if len(value) == 0:
                meta[current_key] = []
            else:
                meta[current_key] = value

        if len(parts) == 1:
            if not isinstance(meta[current_key], list):
                meta[current_key] = [meta[current_key]]
            value = parts[0].strip()
            meta[current_key].append(value)

    for k, v in meta.items():
        if k.endswith('_time') or k == 'time':
            v = dateutil.parse.parse(v)

            try:
                v = v.astimezone(tzinfo=config['timezone'])
            except ValueError:
                v = v.replace(tzinfo=config['timezone'])

            meta[k] = v

        elif k.endswith('_date') or k == 'date':
            v = datetime.strptime(v, '%Y-%m-%d').replace(tzinfo=config['timezone'])
            meta[k] = v

        elif k == 'tags':
            if not isinstance(v, list):
                v = map(lambda s: s.strip(), v.split(u','))

            tags = []
            for t in v:
                tag = Tag.get(slug=t)
                if not tag:
                    tag = Tag(name=t)
                    session.add(tag)
                tags.append(tag)

            meta[k] = tags

    if 'time' in meta:
        meta[u'publish_time'] = meta['time']
        del meta['time']

    elif 'date' in meta:
        meta[u'publish_time'] = meta['date']
        del meta['date']

    return meta


def parse_document(document, config):
    header, body = _parse_content_header(document)
    return _parse_metadata(header, config), body


if __name__ == '__main__':
    main()
