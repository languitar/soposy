from setuptools import setup, find_packages

setup(
    name='soposy',
    version='0.1-dev',
    author='Johannes Wienke',
    author_email='languitar@semipol.de',
    url='https://github.com/languitar/soposy',
    description='A sync daemon for social media profile entries',
    license='LGPLv3+',
    keywords=['social media'],
    classifiers=[
        'Programming Language :: Python :: 3',
        'Topic :: Utilities',
        'License :: OSI Approved :: '
        'GNU Lesser General Public License v3 or later (LGPLv3+)'
    ],

    install_requires=['iso8601', 'requests', 'requests-oauthlib', 'tweepy',
                      'pyxdg', 'pytz'],

    packages=find_packages(),

    entry_points={
        'console_scripts': [
            'soposy = soposy:main',
        ]
    },
)
