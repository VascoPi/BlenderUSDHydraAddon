# **********************************************************************
# Copyright 2023 Advanced Micro Devices, Inc
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
# ********************************************************************
import uuid
from pathlib import Path

import bpy


try:
    from . import configdev
except ImportError:
    configdev = None


class RPR_HYDRA_ADDON_PT_preferences(bpy.types.AddonPreferences):
    bl_idname = "hydrarpr"

    storage_dir: bpy.props.StringProperty(
        name="Storage Dir",
        description="Set directory which would be synchronized for all connected users",
        subtype='DIR_PATH',
        default=getattr(
            configdev, "storage_dir", str(Path.home() / "AppData/Roaming/AMDRenderStudio/Storage/.storage/workspace")
        ),
    )
    server_url: bpy.props.StringProperty(
        name="Server Address",
        description="Set address of remote live server",
        default=getattr(configdev, "server_url", ""),
    )
    storage_url: bpy.props.StringProperty(
        name="Storage Address",
        description="Set address of remote assets storage",
        default=getattr(configdev, "storage_url", ""),
    )
    user_id: bpy.props.StringProperty(
        name="User ID",
        description="Set unique user identifier",
        default=getattr(configdev, "user_id", f"BlenderUser_{uuid.uuid4()}"),
    )
    channel_id: bpy.props.StringProperty(
        name="Channel ID",
        description="Set channel identifier",
        default=getattr(configdev, "channel_id", "Blender"),
    )

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="RenderStudio Settings")
        col = box.column(align=True)
        col.prop(self, "storage_dir", icon='NONE')
        col.prop(self, "server_url", icon='NONE')
        col.prop(self, "storage_url", icon='NONE')
        col.prop(self, "user_id", icon='NONE')
        col.prop(self, "channel_id", icon='NONE')


def preferences():
    return bpy.context.preferences.addons["hydrarpr"].preferences


register, unregister = bpy.utils.register_classes_factory((RPR_HYDRA_ADDON_PT_preferences,))
