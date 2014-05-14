import os

from PIL import Image, ImageOps

import roxy.util as util
from roxy.model import Asset


def process(config, metadata, path, asset=None):
    relative_path = os.path.relpath(path, config['asset_source_path'])
    if asset is None:
        asset = Asset(path=relative_path)

    # determine requested previews
    conf = util.prefixed_keys(config, 'asset_')
    conf.update(util.prefixed_keys(config, 'image_'))
    conf.update(metadata)
    preview_specs = _parse_preview_specs(conf)
    fmt = conf['image_preview_format']

    # write the image to the output path
    image = Image.open(path)
    fname = os.path.splitext(relative_path)[0]

    if fmt == 'JPEG':
        ext = 'jpeg'
    elif fmt == 'PNG':
        ext = 'png'

    path = os.path.join(conf['asset_build_path'], '{}.{}'.format(fname, ext))
    dirname = os.path.dirname(path)
    if not os.path.exists(dirname):
        os.makedirs(dirname)

    copy = image.copy()
    copy.save(path, format=fmt)
    asset.width, asset.height = image.size

    for name, spec in preview_specs.items():
        path = os.path.join(conf['asset_build_path'],
                            '{}-{}.{}'.format(fname, name, ext))
        preview = ImageOps.fit(image,
                               (spec[0], spec[1]),
                               centering=(spec[2], spec[3]),
                               method=Image.ANTIALIAS)
        preview.save(path, format=fmt)
        relative_path = os.path.relpath(path, conf['asset_build_path'])
        setattr(asset, name, relative_path)

    for k, v in metadata.items():
        if not k.startswith('image_') or k.startswith('asset_'):
            setattr(asset, k, v)

    return asset


def _parse_preview_specs(config):
    preview_spec = config['image_previews']
    specs = {}
    for spec in preview_spec:
        name, spec = spec.split(':', 1)
        spec = spec.split()
        default_center = [0.50, 0.50]

        if len(spec) == 1:
            width, height = [int(spec)] * 2
            x, y = default_center

        elif len(spec) == 2:
            width, height = map(int, spec)
            x, y = default_center

        elif len(spec) == 4:
            width, height = map(int, spec[:2])
            x, y = map(float, spec[2:])

        specs[name] = (width, height, x, y)

    return specs
