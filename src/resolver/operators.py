import bpy


class RESOLVER_OP_start_live_mode(bpy.types.Operator):
    bl_idname = 'resolver.start_live_mode'
    bl_label = "Start Live Mode"
    bl_description = ""

    def execute(self, context):
        resolver = context.collection.resolver
        resolver.start_live_mode()
        return {'FINISHED'}


class RESOLVER_OP_stop_live_mode(bpy.types.Operator):
    bl_idname = 'resolver.stop_live_mode'
    bl_label = "Stop Live Mode"
    bl_description = ""

    def execute(self, context):
        resolver = context.collection.resolver
        resolver.stop_live_mode()
        return {'FINISHED'}


class RESOLVER_OP_process_live_update(bpy.types.Operator):
    bl_idname = 'resolver.process_live_mode'
    bl_label = "Process Live Mode"
    bl_description = ""

    def execute(self, context):
        resolver = context.collection.resolver
        resolver.process_live_updates()
        return {'FINISHED'}


class RESOLVER_OP_add_prim(bpy.types.Operator):
    bl_idname = 'resolver.add_prim'
    bl_label = "Add Prim"
    bl_description = ""

    def execute(self, context):
        resolver = context.collection.resolver
        resolver.add_prim()
        return {'FINISHED'}


class RESOLVER_OP_open_stage_uri(bpy.types.Operator):
    bl_idname = 'resolver.open_stage_uri'
    bl_label = "Open Stage Uri"
    bl_description = ""

    def execute(self, context):
        resolver = context.collection.resolver
        resolver.open_stage()
        return {'FINISHED'}


class RESOLVER_OP_import_stage(bpy.types.Operator):
    bl_idname = 'resolver.import_stage'
    bl_label = "Import Stage"
    bl_description = ""

    def execute(self, context):
        resolver = context.collection.resolver
        resolver.import_stage()
        return {'FINISHED'}


class RESOLVER_OP_export_stage_to_string(bpy.types.Operator):
    bl_idname = 'resolver.export_stage'
    bl_label = "Export Stage to Console"
    bl_description = ""

    def execute(self, context):
        resolver = context.collection.resolver
        print(resolver.get_stage().ExportToString())
        return {'FINISHED'}


register_classes, unregister_classes = bpy.utils.register_classes_factory([
    RESOLVER_OP_start_live_mode,
    RESOLVER_OP_stop_live_mode,
    RESOLVER_OP_process_live_update,
    RESOLVER_OP_open_stage_uri,
    RESOLVER_OP_import_stage,
    RESOLVER_OP_export_stage_to_string,
    RESOLVER_OP_add_prim,
    ])

def register():
    register_classes()


def unregister():
    unregister_classes()
