import bpy
from pxr import UsdGeom, Gf
from . import logging


log = logging.Log("updates")


def get_transform_local(obj: bpy.types.Object):
    return obj.matrix_local.transposed()


def on_depsgraph_update_post(scene, depsgraph):
    log.debug(bpy.context.collection, bpy.context.object)
    resolver = bpy.context.collection.resolver
    log.debug("IS UPDATE: ", resolver.is_depsgraph_update)
    if not resolver.is_depsgraph_update:
        return
    for update in depsgraph.updates:
        if isinstance(update.id, bpy.types.Object):
            obj = update.id
            stage = bpy.context.collection.resolver.get_stage()
            # edit_layer = Sdf.Layer.CreateAnonymous()
            # root_layer = stage.GetRootLayer()
            # root_layer.subLayerPaths.append(edit_layer.identifier)
            prim = stage.GetPrimAtPath(obj.resolver.sdf_path)
            xform = UsdGeom.XformCommonAPI(prim)
            log.debug(update.id)
            # xform = UsdGeom.Xform.Define(stage, obj.resolver.sdf_path)
            if update.is_updated_transform:
                log.debug("SetTranslate: ", tuple(obj.location))
                xform.SetTranslate(Gf.Vec3d(tuple(obj.location)))
                log.debug("SetRotate: ", tuple(obj.rotation_euler))
                xform.SetRotate(Gf.Vec3f(tuple(obj.rotation_euler)))
                log.debug("SetScale: ", tuple(obj.scale))
                xform.SetScale(Gf.Vec3f(tuple(obj.scale)))
                # prim.GetAttribute('xformOp:transform').Set(Gf.Matrix4d(get_transform_local(obj)))
                # xform.MakeMatrixXform().Set(Gf.Matrix4d(get_transform_local(obj)))

            if prim:
                log.debug("Prim: ", prim)

            log.debug(
                update, update.id, update.is_updated_geometry, update.is_updated_shading, update.is_updated_transform
            )
