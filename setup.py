from setuptools import setup

exec(open('ytinfo/version.py').read())

setup(
    name='ytinfo',
    version=__version__,
    description='Metadata extraction library for YouTube',
    author='xiema',
    author_email='maxprincipe@yahoo.com',
    url='http://www.github.com/xiema',
    license='Unlicense',
    packages=['ytinfo'],
    install_requires=['requests',],

    classifiers=[
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ]
)
