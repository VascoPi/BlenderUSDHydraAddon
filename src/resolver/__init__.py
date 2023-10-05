bl_info = {
    "name": "Render Studio Resolver",
    "author": "AMD",
    "version": (1, 0, 0),
    "blender": (3, 5, 0),
    "location": "Info header > Render engine menu",
    "description": "Radeon ProRender delegate for Hydra render engine",
    "tracker_url": "",
    "doc_url": "",
    "community": "",
    "downloads": "",
    "main_web": "",
    "support": 'TESTING',
    "category": "Render"
}

import os
import sys
import platform
from pathlib import Path
import bpy
from pxr import Plug


LIBS_DIR = Path(__file__).parent / "libs"


def preload_resolver():
    root_folder = "blender.shared" if platform.system() == 'Windows' else "lib"
    path = os.pathsep.join([str(Path(bpy.app.binary_path).parent / f"{root_folder}")])
    os.add_dll_directory(path)
    os.add_dll_directory(str(LIBS_DIR / "lib"))
    os.environ['PATH'] += ";" + str(LIBS_DIR / "lib")
    sys.path.append(str(LIBS_DIR / "python"))
    Plug.Registry().RegisterPlugins(str(LIBS_DIR / "plugin"))
    usd_plugin = Plug.Registry().GetPluginWithName('RenderStudioResolver')
    if not usd_plugin.isLoaded:
        usd_plugin.Load()


preload_resolver()


from . import resolver, ui, properties, operators


def register():
    properties.register()
    bpy.types.Object.resolver = bpy.props.PointerProperty(type=properties.RESOLVER_object_properties)
    bpy.types.Collection.resolver = bpy.props.PointerProperty(type=properties.RESOLVER_collection_properties)
    bpy.app.handlers.depsgraph_update_post.append(resolver.on_depsgraph_update_post)
    operators.register()
    ui.register()


def unregister():
    ui.unregister()
    operators.unregister()
    del bpy.types.Collection.resolver
    del bpy.types.Object.resolver
    bpy.app.handlers.depsgraph_update_post.remove(resolver.on_depsgraph_update_post)
    properties.unregister()
