import os
from setuptools import setup, find_packages

here =      os.path.abspath(os.path.dirname(__file__))
readme =    open(os.path.join(here, 'README.rst')).read()
changes =   open(os.path.join(here, 'CHANGES.rst')).read()

requires = [
    'docopt',
    'sqlalchemy',
    'batteries==0.3',
]

tests_require = []

deps = [
    'https://github.com/jessedhillon/batteries/tarball/master#egg=batteries-0.3'
]

setup(
    name='roxy',
    version='0.0',
    description='roxy site generator',
    long_description="\n\n".join([readme, changes]),
    classifiers=[
        "Programming Language :: Python",
        "Topic :: Internet :: WWW/HTTP",
    ],
    author='Jesse Dhillon',
    author_email='jesse@dhillon.com',
    url='',
    keywords='web',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=requires,
    tests_require=tests_require,
    dependency_links=deps,
    entry_points={
        'console_scripts': [
            'roxy = roxy.main:main',
        ]
    }
)

