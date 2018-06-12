"""Configuration-free Python doc generation via Sphinx."""

import inspect
import subprocess
import sys
import webbrowser
from functools import reduce, wraps
from pathlib import Path

import click
from jinja2 import Environment

import pytoml as toml
from project_metadata import ProjectMetadata
from sphinx.cmd.build import main as sphinx_build
from sphinx_autobuild import main as sphinx_autobuild

__version__ = '0.1.1'

GENERATED_TEXT = "THIS FILE IS AUTOMATICALLY GENERATED BY FLINX. "
"MANUAL CHANGES WILL BE LOST."

# Allow these names as shortcuts for sphinx.ext.*.
sphinx_builtin_extensions = ['autodoc', 'autosectionlabel', 'autosummary', 'coverage',
                             'doctest', 'extlinks', 'githubpages', 'graphviz',
                             'ifconfig', 'imgconverter',
                             'imgmath', 'mathjax', 'jsmith', 'inheritance_diagram',
                             'intersphinx', 'linkcode',  'napoleon', 'todo', 'viewcode']

# Configuration variables that start with image_ imply the imgconverter (not image)
# extension, etc.
config_var_ext_prefixes = {'image': 'imgconverter', 'inheritance': 'inheritance_graph'}

# Use this, if the user doesn't specify extensions.
default_extensions = ['autodoc']

env = Environment()
env.filters['repr'] = repr
poject_relpath = Path('..')
env.filters['project_rel'] = lambda s: str(poject_relpath / s)

TEMPLATE_DIR = Path('templates')
conf_tpl = env.from_string((TEMPLATE_DIR / 'conf.py.tpl').read_text())
index_tpl = env.from_string((TEMPLATE_DIR / 'index.rst.tpl').read_text())


def write_template_files(output_dir, include_generated_warning=True, verbose=True):
    """Generate the ``conf.py`` and ``README.rst`` files."""
    # TODO: refuse to overwrite non-generated files?
    metadata = ProjectMetadata.from_dir('.')
    config = get_sphinx_configuration('.')
    generated_text = GENERATED_TEXT if include_generated_warning else None
    index_text = index_tpl.render(
        readme=metadata['readme'],
        module_name=metadata['module'],
        generated_text=generated_text,
    )
    index_path = output_dir / 'index.rst'
    index_path.write_text(index_text)
    if verbose:
        print('wrote', index_path)

    author = metadata['author']
    copyright_year = '2018'  # TODO:
    config['extensions'] = get_extensions(config)
    conf_text = conf_tpl.render(
        module_path='..',
        project=metadata['module'],
        copyright=f'{copyright_year}, {author}',
        author=author,
        version=metadata['version'],
        source_suffix=['.rst'],
        master_basename='index',
        generated_text=generated_text,
        config=config.items(),
    )
    conf_path = output_dir / 'conf.py'
    conf_path.write_text(conf_text)
    if verbose:
        print('wrote', conf_path)
    return conf_path


def get_extensions(config_vars):
    # expand shortcut names
    extensions = ['sphinx.ext.' + ext
                  if ext in sphinx_builtin_extensions else ext
                  for ext in config_vars.get('extensions', default_extensions)]
    # add extensions implied by configuration value names
    prefixes = {k.split('_', 1)[0] for k in config_vars.keys() if '_' in k}
    detected_exts = (config_var_ext_prefixes.get(prefix, prefix)
                     for prefix in prefixes)
    auto_exts = sorted('sphinx.ext.' + ext
                       for ext in detected_exts
                       if ext in sphinx_builtin_extensions)
    for ext in auto_exts:
        if ext not in extensions:
            extensions.append(ext)
    return extensions


def get_sphinx_configuration(project_dir):
    try:
        project = toml.loads(Path('pyproject.toml').read_text())
        return reduce(lambda a, b: a[b], 'tool.flinx.configuration'.split('.'), project)
    except (FileNotFoundError, KeyError):
        return {}


@click.group()
def main():
    pass


@main.command()
def generate():
    docs_dir = Path('./docs')
    write_template_files(docs_dir, verbose=True)


@main.command()
def eject():
    docs_dir = Path('./docs')
    write_template_files(docs_dir, include_generated_warning=False, verbose=True)


def build_sphinx_args(all=False, format='html', verbose=False, **args):
    docs_dir = Path('./docs')
    build_dir = docs_dir / '_build' / format
    docs_dir.mkdir(exist_ok=True)
    conf_path = write_template_files(docs_dir, verbose=verbose)
    args = [
        '-b', format,
        '-c', str(conf_path.parent),  # config file
        '-j', 'auto',  # processors
        '-q',  # quiet
        str(docs_dir),
        str(build_dir)
    ]
    if all:
        args += ['-a']
    return dict(build_args=args, build_dir=build_dir, docs_dir=docs_dir)


def with_sphinx_build_args(f):
    @click.option('-a', '--all', is_flag=False,
                  help='Rebuild all the docs, regardless of what has changed.')
    @click.option('-o', '--open', is_flag=True,
                  help='Open the HTML index in a browser.')
    @click.option('--format', default='html', type=click.Choice(['html']),
                  help='The output format.')
    @click.option('--verbose', is_flag=True)
    @wraps(f)
    def wrapper(**kwargs):
        # build_args, build_dir, docs_dir = build_sphinx_args(**kwargs)
        build_args = build_sphinx_args(**kwargs)
        kwargs = {k: v for k, v in kwargs.items() if k not in consumed_args}
        for k, v in build_args.items():
            if k in wrapped_args:
                kwargs[k] = v
        return f(**kwargs)

    def position_param_names(f):
        var_parameter_kinds = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        return {p.name for p in inspect.signature(f).parameters.values()
                if p.kind not in var_parameter_kinds}

    wrapped_args = position_param_names(f)
    consumed_args = position_param_names(build_sphinx_args) - wrapped_args
    return wrapper


@main.command()
@with_sphinx_build_args
def build(build_args=None, docs_dir=None, build_dir=None, format=None, open=False):
    """Build the documentation."""
    status = sphinx_build(build_args)
    if status:
        sys.exit(sys.exit)
    if open and format == 'html':
        webbrowser.open(str(build_dir / 'index.html'))


@main.command()
@with_sphinx_build_args
def serve(build_args=None, open=False):
    if open:
        build_args += ['-B']
    process = subprocess.run(['sphinx-autobuild'] + build_args)
    if process.returncode:
        sys.exit(1)


if __name__ == '__main__':
    main()
