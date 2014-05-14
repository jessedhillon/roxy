from datetime import datetime, timedelta

from roxy.events import Render
from roxy.generators import render, copy, using, image_fit


@render('/page/{slug}.html')
@using('page.jinja2')
def pages(site):
    return site.content.filter(type='page').all()


@render('/posts/{publish_time:%Y/%m/%d}/{slug}.html')
@using('post-{category}.jinja2', 'post.jinja2', defaults={'category': 'default'})
def new_posts(site):
    threshold = datetime.now() - timedelta(days=30)
    return site.content.filter(type='post', publish_time={'after': threshold}).all()


@render('/archive/{publish_time:%Y/%m/%d}/{slug}.html')
@using('post-archive.jinja2')
def archived_posts(site):
    threshold = datetime.now() - timedelta(days=30)
    return site.content.filter(type='post', publish_time={'on_before': threshold}).all()


@render('/index.html')
@using('home.jinja2')
def home(site):
    return {
            'pages': site.content.filter(type='page').limit(5).all(),
            'posts': site.content.filter(type='post').order_by(desc=['likes']).limit(10).all(),
            'awesome': site.content.filter(tags=['awesome', 'dude']).order_by(desc=['likes']).limit(10).all()
    }


@render('/tag/{name}.html')
@using('tag-index.jinja2')
def tag_index(site):
    return site.tags.all()


@Render.subscribe
def before_render(site, path, template, fallback, context):
    context['footer'] = u"&copy; Foobar {:%Y}".format(datetime.now())


@copy('/images/{filename[0]}-{size}.{extension}')
@image_fit('JPEG', full=(2000, 2000), thumb=(64, 64), tile=(128, 128))
def thumbnails(site):
    return site.assets.filter(type='image').all()
