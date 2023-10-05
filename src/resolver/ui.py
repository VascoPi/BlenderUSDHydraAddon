import bpy


class RESOLVER_PT_object(bpy.types.Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'object'
    bl_label = "RenderStudio Connector"

    @classmethod
    def poll(cls, context):
        return context.object

    def draw(self, context):
        resolver = context.object.resolver
        layout = self.layout
        layout.prop(resolver, 'sdf_path')


class RESOLVER_PT_collection(bpy.types.Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'collection'
    bl_label = "RenderStudio Connector"

    @classmethod
    def poll(cls, context):
        return True
        # return next(iter(obj for obj in context.collection.objects if obj.resolver.sdf_path), False) or not len(context.collection.objects)
        # return context.object and context.object.type == "EMPTY"

    def draw(self, context):
        resolver = context.collection.resolver
        layout = self.layout
        layout.prop(resolver, 'usd_path')
        layout.prop(resolver, 'liveUrl')
        layout.prop(resolver, 'storageUrl')
        layout.prop(resolver, 'channelId')
        layout.prop(resolver, 'userId')
        layout.operator("resolver.import_stage")
        layout.operator("resolver.open_stage_uri")
        layout.operator("resolver.start_live_mode")
        layout.operator("resolver.stop_live_mode")
        layout.operator("resolver.process_live_mode")
        layout.separator()
        layout.prop(resolver, 'prim_name')
        layout.operator("resolver.add_prim")
        layout.operator("resolver.export_stage")


register_classes, unregister_classes = bpy.utils.register_classes_factory([
    RESOLVER_PT_collection,
    RESOLVER_PT_object,
    ])

def register():
    register_classes()


def unregister():
    unregister_classes()
