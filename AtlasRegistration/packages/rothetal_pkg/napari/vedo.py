# Functions relating to vedo.
#
# v.2024.02.27
# m@muniak.com

# 2024.11.07 - cleaned up for manuscript deposit.

import os
import meshio
import napari
import numpy as np
from vedo import Mesh
from vedo.utils import is_ragged

from .aba import load_aba_as_mesh
from .affine3d import apply_affine


def vedo2napari(mesh, name='', scalar_name='scalars', **kwargs):
    """ Convert vedo mesh to napari volume.
    """
    points = mesh.vertices
    faces = mesh.cells
    if len(faces):
        if is_ragged(faces) or len(faces[0]):
            tri_mesh = mesh.clone().triangulate()
            faces = tri_mesh.cells
    faces = np.asarray(faces, dtype=int)
    if scalar_name in mesh.pointdata.keys():
        mesh_tuple = (points, faces, mesh.pointdata[scalar_name])
    else:
        mesh_tuple = (points, faces)
    if len(mesh_tuple[0]) == 0:
        print('No mesh to send to napari!')
        return
    if not name:
        if mesh.name:
            name = mesh.name
        elif mesh.filename:
            name = os.path.basename(mesh.filename).split('.')[0]
        else:
            name = 'vedo_mesh'
    return napari.current_viewer().add_surface(mesh_tuple, name=name, **kwargs)


def napari2vedo(layer=None):
    """ Convert napari volume to vedo mesh.
    """
    if layer is None:
        layer = viewer.layers.selection.active
    points = layer.data[0].astype(float)
    faces = layer.data[1].astype(int)
    scalars = layer.data[2]
    mesh = Mesh([points, faces])
    if len(scalars) > 0:
        mesh.pointdata['scalars'] = scalars
    if layer.name:
        mesh.name = layer.name
    return mesh


def loadobj2vedo(path, name=''):
    """ Load .obj as a vedo mesh.
    """
    mesh = meshio.read(path)
    if not name:
        name = os.path.basename(path).split('.')
    return Mesh([mesh.points.astype(float), mesh.cells[0].data.astype(int)])


def show_vedo_slice(mesh, layer=None, origin=(0,0,0), normal=(1,0,0), translation=(0,0,0), type='polygon', 
                    clip=[None]*3, clip_r=[True]*3, name='', viewer=None, scale=1., tol=0.0001, **kwargs):
    if len(scale) == 1:
        scale = [scale] * 3
    if viewer is None:
        viewer = napari.current_viewer()
    if not isinstance(mesh, Mesh):
        mesh = napari2vedo(mesh)
    lines = mesh.intersect_with_plane(origin=origin, normal=normal).join_segments(tol=tol)
    if (not lines) or (lines is None):
        # No slice, exit.
        print('No intersecting slice at origin: %s, normal: %s ...' % (origin, normal))
        return layer
    if type=='path':
        lines = [(np.vstack((line.vertices, line.vertices[0, ...])) + translation) * (1. / scale) for line in lines]
    else:
        lines = [np.array(line.vertices + translation) * (1. / scale) for line in lines]
    # This is a lil' messy.
    lines = clip_lines(lines, [(clip[i] + translation[i]) / scale[i] if clip[i] is not None else None for i in range(3)], clip_r)
    if not lines:
        return layer
    if lines and (layer is None):
        if not name:
            if mesh.name:
                name = mesh.name
            elif mesh.filename:
                name = os.path.basename(mesh.filename).split('.')[0]
        layer = viewer.add_shapes(lines, shape_type=[type]*len(lines), name=name, **kwargs)
        layer.scale *= scale
    else:
        layer.add(lines, shape_type=[type]*len(lines), **kwargs)
    return layer


def clip_lines(lines, clip=[None]*3, clip_r=[True]*3):
    for i in range(3):
        if clip[i] is not None:
            for j in range(len(lines))[::-1]:
                tf = lines[j][:, i] > clip[i]
                if not clip_r:
                    tf = ~tf
                if np.sum(tf) > 1:
                    lines[j] = lines[j][tf, :]
                else:
                    lines.pop(j)
    return lines


def transform_and_slice_mesh(mesh, zs, at=None, translations=None, scale=(1,1,1), clip=None, color='blue', name=None, aba=None):
    if isinstance(mesh, list):
        for m in mesh:
            transform_and_slice_mesh(m, zs, at=at, translations=translations, scale=scale, clip=clip, color=color, name=name, aba=aba)
        return
    try:  # Try MESH as a string, for which we mean an ABA object... convenience!
        obj = load_aba_as_mesh(mesh, aba=aba)
        name = mesh
    except:
        obj = mesh
    if at is None:
        at = np.eye(4)
    if translations is None:
        translations = np.zeros((len(zs), 3))
    if clip is None:
        clip = [None] * 3
    obj = apply_affine(obj, at)
    layer = None
    for t, z in enumerate(zs):
        layer = show_vedo_slice(obj, layer=layer, origin=(z,0,0), normal=(1,0,0), translation=translations[t, :], scale=scale,
                                clip=clip, edge_color=color, edge_width=5, face_color=[0,0,0,0], name=name)
    return layer


def rects2mesh(bounds, scale=np.ones(3)):
    """ Input is a list of 3D coordinates, (z, ymin, ymax, xmin, xmax).
    
        Add a half-z-step boundary to each cap.
    """
    n = bounds.shape[0] + 2
    coords = np.vstack([ bounds[0, :] + np.array([-0.5, 0, 0, 0, 0]),
                         bounds,
                         bounds[-1, :] + np.array([0.5, 0, 0, 0, 0]) ])
    # 4 corners of rect
    verts = np.array([ c for i in range(n) for c in [ 
                        coords[i, [0, 1, 3]], # a
                        coords[i, [0, 2, 3]], # b
                        coords[i, [0, 2, 4]], # c
                        coords[i, [0, 1, 4]], # d
                      ]])
    verts *= scale
    
    cube = np.array([  [0, 1, 5, 4],
                       [3, 0, 4, 7],
                       [2, 3, 7, 6],
                       [2, 1, 5, 6], ])
    faces = np.tile(cube, (n-1, 1, 1))
    faces += np.arange(n-1).reshape(n-1, 1, 1) * 4
    faces = np.vstack((np.vstack(faces), [0, 1, 2, 3], [n*4 - 4, n*4 - 3, n*4 - 2, n*4 - 1]))
    return Mesh([verts, faces])