
with Page.router.connect("/pages/{page.slug}.html") as route:
    pages = Page.query.all()
    pages.generate(route)

with Article.router.connect("/index.html") as route:
    popular = Article.query.\
                orderby(Article.popularity.dex()).\
                limit(10)

    site.template.get('home').generate(route, articles=popular)

with Article.query.\
        filter(Article.status == 'published').\
        orderby(Article.publish_time.desc()).\
        limit(10) as articles:
    with Article.router.connect("/index.html"):
        for article in articles:
            article.template.generate(route)

articles = site.articles.filter(status='published').order_by(publish_time='desc')
articles.limit(10).connect("/index.html", 'home').generate()
articles.connect("/slug/{article.slug}.html", 'article').generate()

site # total document query
site.articles # accumulate articles
site.articles.pages # accumulate pages
site.articles.pages.order_by(publish_time='desc') # sort both by desc publish_time

with site.route('/index.html') as route: # target output file
    route.template('home') # generate with 'home' template
    route.generate(articles=articles) # generate, with `articles` context var

# 1. flexibility in building routes (URLs)
# 1. declare which routes/objects render with which templates
# 1. query sets for different templates -- some templates can be only for certain classes of objects, objects with instrinsic properties (like view counts, tags, recency etc)

# this route expects articles, will have an {article} variable available for expansion
site.articles.route("/index.html").query(orderby=Article.date.desc(), limit=10).\
generate('index')

site.articles.route("/{archive.date.year}/{archive.date.month}/index.html").\
generate('archive_index')

site.articles.\
route("/{article.date.year}/{article.date.month}/{article.date.day}/{article.slug}.html").\
generate('article')

# multiple depth content
site.pages.query(level=0).paginate().route("/{page.slug}/page_{pagination.number}.html").generate('{page.parent.slug}_page')
site.pages.query(level=1).route("/{page.parent.slug}/{page.slug}/page_{pagination.number}.html").generate('{page.parent.slug})_page')

# various type of content
site.articles.query(level=0, type='tutorial').route("/tutorials/{article.slug}.html").generate('tutorial')

site.articles.filter(Article.level == 0).filter(Article.type == 'tutorial').route("/tutorials/{article.slug}.html").generate('tutorial')

site.\
articles.\
filter(Article.level == 0).\
filter(Article.type == 'tutorial').\
route("/tutorials/{article.slug}.html").\
template('tutorial')

site.\
pages.\
filter(Page.level == 0).\
paginate().\
route("/{page.slug}/page_{pagination.number}.html").\
template("{page.parent.slug}_page")

with site.route("/index.html"):
    with site.template('index'):
        site.pages.limit(10)
        # will not apply any results to the formatting of the route

with site.route("/blog/{article.date.year}/{article.date.month}/{article.slug}.html"):
    with site.template('article_{article.date.month}'):
        site.articles.order_by(Article.date.desc())

with site.route("/{page.slug}.html", paginate="/{page.slug}/page_{pagination.number}.html"):
    with site.template('page_{page.parent.slug}'):
        site.pages.filter(Page.level == 0).each().paginate(10, orphans=2)
        # will apply {page} formatting parameter with each of these results

class Site(object):
    config = None

    states = None
    routes = None

    def __init__(self, config):
        self.states = []

    def collect(self):
        pass

    def generate(self, route=None):
        pass

    def route(self, spec):
        return Route(self, spec)

    def template(self, spec):
        return Template(self, spec)

    @property
    def pages(self):
        return ObjectSet(self, Page)

    @property
    def articles(self):
        return ObjectSet(self, Article)

    def new_context(self):
        self.contexts.append(Context(self))
        return self.contexts[-1]

    def current_context(self):
        if not self.contexts or self.contexts[-1].complete():
            return self.new_context()

        return self.contexts[-1]

class Context(object):
    count = None

    def __init__(self, site):
        self.routes = []
        self.templates = []
        self.queries = []

    def add_route(self, route):
        self.routes.append(route)

    def add_template(self, template):
        self.templates.append(template)

    def add_query(self, query):
        self.queries.append(query)

    def enter(self):
        self.count = 1

    def exit(self):
        if self.count == 0:
            raise Exception()

        self.count -= 1

    def complete(self):
        return self.count == 0

class Route(object):
    def __init__(self, site, route):
        self.site = site
        self.spec = spec

    def __enter__(self):
        self.state = self.site.current_state()
        self.state.enter()
        self.state.add_route(self)

    def __exit__(self, type, value, tb):
        self.state.exit()

class Template(object):
    def __init__(self, site, template):
        self.site = site
        self.spec = spec

    def __enter__(self):
        self.state = self.site.current_state()
        self.state.enter()
        self.state.add_template(self)

    def __exit__(self, type, value, tb):
        self.state.exit()

    def paginate(self, count=None, pages=None):
        pass

class ObjectSet(object):
    query = None
    site = None

    def __init__(self, site, cls):
        self.state = site.current_state()
        self.query = cls.query
        self.state.add_query(q)

    def paginate(self, count=None, orphan=None):
        pass

    def __getattr__(self, name):
        p = getattr(self.query, name)
        if isinstance(p, collections.Callable):
            def f(*args):
                self.query = p(*args)
                return self.query

            return f

        else:
            raise ValueError
