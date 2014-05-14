roxy
====

The first static site generator to matter

Usage
-----

- After installing, copy and modify the example :literal:`site.ini` with your appropriate values:
  - In a section called :literal:`[roxy]`
    - :literal:`timezone` should be the name of an `IANA Database entry <https://en.wikipedia.org/wiki/Tz_database>`_, like :literal:`America/Los_Angeles`
  - In a section labeled :literal:`[site:site-identifier]` where :literal:`site-identifier` can pretty much be anything
    - :literal:`name` the name of your site
    - :literal:`url` the URL for your site (purely for cosmetic purposes)
    - :literal:`url_base` the base URL from which absolute URLs will be generated
    - :literal:`generator` the qualified name of a Python module which will act as the generator for this site, see below
    - :literal:`content_source_path` the location of source documents
    - :literal:`asset_source_path` the location of source assets
    - :literal:`template_path` the location of `Jinja2 <http://jinja.pocoo.org/docs/>`_ templates
    - :literal:`build_path` the location where generated documents will be written

Then run::

    roxy initialize site-identifier

Repeating the same :literal:`site-identifier` from the :literal:`site.ini`

Document Format
---------------

Documents are formatted according to Markdown syntax, with one addition. Until an empty line is encountered, lines are interpreted as metadata, for example::

    title: The Title of the Document
    slug: super-cool-thoughts
    date: 2014-05-12
    tags: this,
          that,
          the other thing
    mood: cheerful
    eating: A sandwich

The metadata is a place to describe the document and attach arbitrary values to your content. These values will be accessible from the :literal:`Content` object, which is primarily how you interact with documents. You can filter documents on these criteria when describing how to generate your site, and also access these metadata from templates used to render these documents.

After the metadata, insert a blank line and then begin the body of your document.

Assets
------

Assets should exist in the directory specified by :literal:`asset_source_path`. Their path, relative to that directory, will be preserved when writing them out to :literal:`build_path` -- `e.g.`, an image at :literal:`images/dogs/happy.jpg` would, when processed, cause the same directory structure to be written beneath :literal:`build_path`.

Generators
----------

Generators are a way to describe how to take in source contents and assets, and write out result documents. I'm lazy, so just look at :literal:`roxy/generators/blog.py` for now. I'll write this up later.
