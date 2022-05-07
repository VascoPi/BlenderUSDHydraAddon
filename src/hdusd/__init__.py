#**********************************************************************
# Copyright 2020 Advanced Micro Devices, Inc
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#********************************************************************

bl_info = {
    "name": "USD Hydra",
    "author": "AMD",
    "version": (1, 0, 92),
    "blender": (2, 93, 0),
    "location": "Info header, render engine menu",
    "description": "USD Hydra rendering plugin for Blender",
    "warning": "",
    "tracker_url": "https://github.com/GPUOpen-LibrariesAndSDKs/BlenderUSDHydraAddon/issues",
    "doc_url": "https://radeon-pro.github.io/RadeonProRenderDocs/en/usd_hydra/about.html",
    "category": "Render"
}
version_build = ""


import tempfile
from pathlib import Path

from . import config
from .utils import logging, temp_dir

import bpy
from bpy.types import Operator, AddonPreferences
from bpy.props import StringProperty, IntProperty, BoolProperty, EnumProperty


class UsdAddonPreferences(AddonPreferences):
    bl_idname = __name__

    def update_temp_dir(self, context):
        if tempfile.gettempdir() == str(Path(self.tmp_dir)):
            log.info(f"Current temp directory is {self.tmp_dir}")
            return

        if not Path(self.tmp_dir).exists():
            return

        tempfile.tempdir = Path(self.tmp_dir)
        log.info(f"Current temp directory is changed to {self.tmp_dir}{id(self.tmp_dir)}")

    def update_dev_tools(self, context):
        config.show_dev_settings = self.dev_tools
        log.info(f"Developer settings is {'enabled' if self.dev_tools else 'disabled'}")

    def update_debug_log(self, context):
        config.logging_level = 'DEBUG' if self.debug_log else 'INFO'
        log.info(f"Log level 'DEBUG' is {'enabled' if self.debug_log else 'disabled'}")

    tmp_dir: StringProperty(
        name="Temp Directory",
        description="Set temp directory",
        maxlen=1024,
        subtype='DIR_PATH',
        default=str(temp_dir()),
        update=update_temp_dir,
    )
    dev_tools: BoolProperty(
        name="Developer Tools",
        description="Enable developer tools",
        default=config.show_dev_settings,
        update=update_dev_tools,
    )
    debug_log: BoolProperty(
        name="Debug",
        description="Enable debug console output",
        default= config.logging_level != 'INFO',
        update=update_debug_log,
    )
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "tmp_dir", icon='NONE' if Path(self.tmp_dir).exists() else 'ERROR')
        layout.prop(self, "dev_tools")
        layout.prop(self, "debug_log")


log = logging.Log('init')
log.info(f"Loading USD Hydra addon version={bl_info['version']}, build={version_build}")

from . import engine, properties, ui, usd_nodes, mx_nodes, bl_nodes


def register():
    """ Register all addon classes in Blender """
    log("register")

    bpy.utils.register_class(UsdAddonPreferences)
    engine.register()
    bl_nodes.register()
    mx_nodes.register()
    usd_nodes.register()
    properties.register()
    ui.register()


def unregister():
    """ Unregister all addon classes from Blender """
    log("unregister")

    mx_nodes.unregister()
    usd_nodes.unregister()
    bl_nodes.unregister()
    ui.unregister()
    properties.unregister()
    engine.unregister()
    bpy.utils.unregister_class(UsdAddonPreferences)
