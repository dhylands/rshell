import os
from setuptools import setup

here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name = 'rshell',
    version = '0.0.1',
    author = 'Dave Hylands',
    author_email = 'dhylands@gmail.com',
    description = ('A remote shell for working with MicroPython boards.'),
    license = 'MIT',
    keywords = 'micropython shell',
    url = 'https://github.com/dhylands/rshell',
    download_url = 'https://github.com/dhylands/rshell/tarball/v0.0.1',
    packages=['rshell', 'tests'],
    long_description=long_description,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Embedded Systems',
        'Topic :: System :: Shells',
        'Topic :: Terminals :: Serial',
        'Topic :: Utilities',
    ],
    install_requires=[
        'pyserial',
        'pyudev >= 0.16',
    ],
    entry_points = {
        'console_scripts': ['rshell=rshell.command_line:main'],
    },
)
