from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Set, Tuple

import vbuild

from . import __version__
from .helpers import KWONLY_SLOTS, hash_file_path

if TYPE_CHECKING:
    from .element import Element


@dataclass(**KWONLY_SLOTS)
class Component:
    key: str
    name: str
    path: Path

    @property
    def tag(self) -> str:
        return f'nicegui-{self.name}'


@dataclass(**KWONLY_SLOTS)
class VueComponent(Component):
    html: str
    script: str
    style: str


@dataclass(**KWONLY_SLOTS)
class JsComponent(Component):
    pass


@dataclass(**KWONLY_SLOTS)
class Library:
    key: str
    name: str
    path: Path
    expose: bool


vue_components: Dict[str, VueComponent] = {}
js_components: Dict[str, JsComponent] = {}
libraries: Dict[str, Library] = {}


def register_vue_component(path: Path) -> Component:
    """Register a .vue or .js Vue component.

    Single-file components (.vue) are built right away
    to delegate this "long" process to the bootstrap phase
    and to avoid building the component on every single request.
    """
    key = compute_key(path)
    name = get_name(path)
    if path.suffix == '.vue':
        if key in vue_components and vue_components[key].path == path:
            return vue_components[key]
        assert key not in vue_components, f'Duplicate VUE component {key}'
        v = vbuild.VBuild(name, path.read_text())
        vue_components[key] = VueComponent(key=key, name=name, path=path, html=v.html, script=v.script, style=v.style)
        return vue_components[key]
    if path.suffix == '.js':
        if key in js_components and js_components[key].path == path:
            return js_components[key]
        assert key not in js_components, f'Duplicate JS component {key}'
        js_components[key] = JsComponent(key=key, name=name, path=path)
        return js_components[key]
    raise ValueError(f'Unsupported component type "{path.suffix}"')


def register_library(path: Path, *, expose: bool = False) -> Library:
    """Register a *.js library."""
    key = compute_key(path)
    name = get_name(path)
    if path.suffix in {'.js', '.mjs'}:
        if key in libraries and libraries[key].path == path:
            return libraries[key]
        assert key not in libraries, f'Duplicate js library {key}'
        libraries[key] = Library(key=key, name=name, path=path, expose=expose)
        return libraries[key]
    raise ValueError(f'Unsupported library type "{path.suffix}"')


def compute_key(path: Path) -> str:
    """Compute a key for a given path using a hash function.

    If the path is relative to the NiceGUI base directory, the key is computed from the relative path.
    """
    nicegui_base = Path(__file__).parent
    try:
        path = path.relative_to(nicegui_base)
    except ValueError:
        pass
    return f'{hash_file_path(path.parent)}/{path.name}'


def get_name(path: Path) -> str:
    return path.name.split('.', 1)[0]


def generate_resources(prefix: str, elements: List[Element]) -> Tuple[List[str],
                                                                      List[str],
                                                                      List[str],
                                                                      Dict[str, str],
                                                                      List[str]]:
    done_libraries: Set[str] = set()
    done_components: Set[str] = set()
    vue_scripts: List[str] = []
    vue_html: List[str] = []
    vue_styles: List[str] = []
    js_imports: List[str] = []
    imports: Dict[str, str] = {}

    # build the importmap structure for exposed libraries
    for key, library in libraries.items():
        if key not in done_libraries and library.expose:
            imports[library.name] = f'{prefix}/_nicegui/{__version__}/libraries/{key}'
            done_libraries.add(key)

    # build the none-optimized component (i.e. the Vue component)
    for key, component in vue_components.items():
        if key not in done_components:
            vue_html.append(component.html)
            vue_scripts.append(component.script.replace(f"Vue.component('{component.name}',",
                                                        f"app.component('{component.tag}',", 1))
            vue_styles.append(component.style)
            done_components.add(key)

    # build the resources associated with the elements
    for element in elements:
        for library in element.libraries:
            if library.key not in done_libraries:
                if not library.expose:
                    url = f'{prefix}/_nicegui/{__version__}/libraries/{library.key}'
                    js_imports.append(f'import "{url}";')
                done_libraries.add(library.key)
        if element.component:
            component = element.component
            if component.key not in done_components and component.path.suffix.lower() == '.js':
                url = f'{prefix}/_nicegui/{__version__}/components/{component.key}'
                js_imports.append(f'import {{ default as {component.name} }} from "{url}";')
                js_imports.append(f'app.component("{component.tag}", {component.name});')
                done_components.add(component.key)
    return vue_html, vue_styles, vue_scripts, imports, js_imports
