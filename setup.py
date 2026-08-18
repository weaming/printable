from pathlib import Path

from setuptools import find_packages, setup

here = Path(__file__).parent


long_description = (here / 'README.md').read_text(encoding='utf-8')

install_requires = [
    line
    for line in (here / 'requirements.txt').read_text(encoding='utf-8').splitlines()
    if line.strip() and not line.strip().startswith('#')
]

name = 'printable'
gh_repo = f'https://github.com/weaming/{name}'

setup(
    name=name,  # Required
    version='0.4.3',  # Required
    # This is a one-line description or tagline of what your project does.
    description='CLI and functions help for printing tabular data',  # Required
    long_description=long_description,  # Optional
    long_description_content_type='text/markdown',  # Optional
    install_requires=install_requires,
    # You can use `find_packages()` or the `py_modules` argument which expect a
    # single python file
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),  # Required
    package_data={
        'printable.native': ['lib/*/libcolumn.dylib', 'lib/*/libcolumn.so'],
    },
    include_package_data=True,
    entry_points={'console_scripts': ['printable=printable:main']},  # Optional
    url=gh_repo,  # Optional
    author='weaming',  # Optional
    author_email='garden.yuen@gmail.com',  # Optional
    keywords='math',  # Optional
    project_urls={'Bug Reports': gh_repo, 'Source': gh_repo},  # Optional
)
