import os
import shutil
import logging
from zlib import crc32


def pluck(d, keys):
    return {k: d[k] for k in keys if k in d}


def prefixed_keys(d, prefix):
    return {k: d[k] for k in d.keys() if k.startswith(prefix)}


def checksum(f):
    pos = f.tell()
    f.seek(0)
    block_size = 2 ** 14
    data = f.read(block_size)
    cs = crc32(data)

    data = f.read(block_size)
    while data:
        cs = crc32(data, cs)
        data = f.read(block_size)

    f.seek(pos)
    return cs


def _make_path(p):
    if isinstance(p, (tuple, list)):
        parts = list(p[:1])
        for el in p[1:]:
            if el.startswith('/'):
                parts.append(el[1:])
            else:
                parts.append(el)
        p = os.path.join(*parts)

    dirname = os.path.dirname(p)
    if not os.path.exists(dirname):
        os.makedirs(dirname)

    return p


def write(path, content):
    logger = logging.getLogger('roxy')
    path = _make_path(path)
    dirname = os.path.dirname(path)
    if not os.path.exists(dirname):
        os.makedirs(dirname)

    with open(path, 'wb') as f:
        logger.debug('writing to {}'.format(f.name))
        f.write(content)


def copy(src, dest):
    logger = logging.getLogger('roxy')
    src, dest = map(_make_path, (src, dest))
    shutil.copy(src, dest)
    logger.debug('copying {} to {}'.format(src, dest))


def url_join(*parts):
    base = parts[0]
    if base.endswith('/'):
        base = base[:-1]

    parts = [p[1:] if p.startswith('/') else p for p in parts[1:]]
    url = [base]
    url.extend(parts)
    return '/'.join(url)
