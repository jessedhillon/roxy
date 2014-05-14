# vim: set fileencoding=utf8 :
import os
import logging
import tempfile

from PIL import ImageOps, Image

from roxy.events import BeforeRoute, AfterWrite, BeforeRender
from roxy.model import Model, get_session
import roxy.util as util
import roxy.configure as configure


def model_dict(model, defaults):
    if defaults:
        values = defaults
    else:
        values = {}

    values.update(model.as_dict())
    return values


def render(path_fmt, defaults=None):
    """renders `Content` models"""
    logger = logging.getLogger('roxy')
    def render(fn):
        logger.debug('render {}'.format(path_fmt))
        def queued_render(*args, **kwargs):
            templates = fn(*args, **kwargs)
            render = []
            for t in templates:
                template, fallback, context = t
                if isinstance(context, Model):
                    values = model_dict(context, defaults)
                else:
                    values = context
                path = path_fmt.format(**values)
                logger.debug('rendering {} using {}'.format(path, template))
                render.append((path, template, fallback, context))

            return render
        enqueue_render(queued_render)
        return queued_render
    return render


def using(template_fmt, fallback_fmt=None, defaults=None):
    logger = logging.getLogger('roxy')
    def using(fn):
        logger.debug('using {}, {}'.format(template_fmt, fallback_fmt))
        def template(*args, **kwargs):
            logger.debug('templating {}'.format(fn.__name__))
            context = fn(*args, **kwargs)
            templates = []

            if not isinstance(context, list):
                context = [context]

            for c in context:
                if not isinstance(c, dict):
                    values = model_dict(c, defaults)
                else:
                    values = c

                if fallback_fmt:
                    templates.append((template_fmt.format(**values), fallback_fmt.format(**values), c))
                templates.append((template_fmt.format(**values), None, c))

            return templates
        return template
    return using


_render_queue = []
def enqueue_render(f):
    _render_queue.append(f)


def copy(template_fmt, fallback_fmt=None, defaults=None):
    def copy(fn):
        def queued_copy(*args, **kwargs):
            config = configure.current_config()
            jobs = fn(*args, **kwargs)
            to_copy = []
            for j in jobs:
                if len(j) == 2:
                    source, context = j
                    setter = None
                if len(j) == 3:
                    source, context, setter = j
                path = template_fmt.format(**context)
                to_copy.append((source, path))
                if setter:
                    setter(path)

            return to_copy

        enqueue_copy_job(queued_copy)
        return queued_copy
    return copy


def image_fit(fmt, **sizes):
    def fit(fn):
        def fit(*args, **kwargs):
            config = configure.current_config()
            assets = fn(*args, **kwargs)
            contexts = []
            for asset in assets:
                for size, params in sizes.items():
                    path = os.path.join(config['asset_source_path'], asset.path)
                    image = Image.open(path)

                    bounds = [min(image.size[i], params[i]) for i in range(2)]
                    preview = ImageOps.fit(image, bounds, method=Image.ANTIALIAS)
                    values = {
                        'filename': asset.filename,
                        'size': size,
                        'extension': fmt.lower()
                    }

                    _, path = tempfile.mkstemp(suffix='.'+fmt.lower())

                    def setter(path, size=size):
                        setattr(asset, size, path)
                        session = get_session()
                        session.add(asset)

                    with open(path, 'rb') as f:
                        preview.save(path, format=fmt)
                        contexts.append((path, values, setter))

            return contexts
        return fit
    return fit


_copy_queue = []
def enqueue_copy_job(f):
    _copy_queue.append(f)


@BeforeRoute.subscribe
def get_routes(site, config, route_mappings):
    renders = []
    for r in _render_queue:
        renders.extend(r(site))

    route_mappings.update({
        path: context for path, _, _, context in renders 
        if isinstance(context, Model)
    })


@BeforeRender.subscribe
def process_copy_jobs(site, config, write_list):
    logger = logging.getLogger('roxy')
    config = configure.current_config()
    for j in _copy_queue:
        for src, dest in j(site):
            logger.info("copying {} ▶ {}".format(src, dest))
            util.copy(src, (config['build_path'], dest))


@BeforeRender.subscribe
def get_render_jobs(site, config, render_list):
    renders = []
    for r in _render_queue:
        renders.extend(r(site))

    render_list.extend(renders)


@AfterWrite.subscribe
def commit_session(*args, **kwargs):
    get_session().commit()
