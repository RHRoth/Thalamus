# Script to produce ABA outlines as vectors MAPPED TO an individual brain slice for figure.
# This output was merged with figure image and formatted in Adobe Illustrator (v29.0.1).
# muniak@ohsu.edu
# 2024.11.13 - output verified for manuscript.

# Custom script path (must contain rothetal_pkg folder).
PKG_PATH = r'<<FILEPATH_TO_SCRIPTS>>'

# Set location of data.
ROOT_DIR = r'<<FILEPATH_TO_DATA>>'

import os
import sys
import pandas as pd
from vedo import Mesh
import matplotlib.pyplot as plt

# Custom modules.
sys.path.insert(0, PKG_PATH)
from rothetal_pkg.napari.aba import get_aba
from rothetal_pkg.napari.aba import load_aba_as_mesh
from rothetal_pkg.napari.vedo import clip_lines
from rothetal_pkg.napari.thal import filter_brain_coords
from rothetal_pkg.napari.affine3d import apply_affine

# CSV path.
CSV_PATH = os.path.join(ROOT_DIR, r'CSVs')

# FIG output path.
FIG_PATH = os.path.join(ROOT_DIR, r'CSVs')

# Options.
BRAIN = 10
CHOSEN_Z = 3920
ATLAS = 'aba'  # Figure only made for ABA.
RES = 10
F_COLUMN = 'intensity'
F_METHOD = 'intensity'
F_THRESHOLD = 0.05
# Scale values reflect the downsampled calibration used in the TrakEM2 projects
# where fiducials were plotted.  I suppose I could've logged this in a CSV
# somewhere... but I didn't so we're gonna hard-code it rather than digging
# into TrakEM2 XMLs... it never changes for this project!
BRAIN_SCALE = np.array((40.0, 3.632005230087531, 3.632005230087531))

# Edit of rothetal_pkg.napari.vedo.show_vedo_slice() just for this figure.
def show_vedo_slice_mod(ax, mesh, layer=None, origin=(0,0,0), normal=(1,0,0), translation=(0,0,0), type='polygon', 
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
    for line in lines:
        line = np.vstack([line, line[0,:]]) * scale
        ax.plot(line[:,2], line[:,1], '-k')
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
    return ax

# Edit of rothetal_pkg.napari.vedo.transform_and_slice_mesh() just for this figure.
def transform_and_slice_mesh_mod(ax, mesh, zs, at=None, translations=None, scale=(1,1,1), clip=None, color='blue', name=None, aba=None):
    if isinstance(mesh, list):
        for m in mesh:
            ax = transform_and_slice_mesh_mod(ax, m, zs, at=at, translations=translations, scale=scale, clip=clip, color=color, name=name, aba=aba)
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
        ax = show_vedo_slice_mod(ax, obj, layer=layer, origin=(z,0,0), normal=(1,0,0), translation=translations[t, :], scale=scale,
                                clip=clip, edge_color=color, edge_width=1, face_color=[0,0,0,0], name=name)
    return ax

aba = get_aba(RES, ATLAS)
aba_mid = np.array(RES) * aba.shape / 2.

at = np.asarray(pd.read_csv(os.path.join(CSV_PATH, 'brain%d_at_%s_%dum.csv' % (BRAIN, ATLAS, RES))))
xy_offsets = pd.read_csv(os.path.join(CSV_PATH, 'brain%d_txy_%s_%dum.csv' % (BRAIN, ATLAS, RES)), index_col='z')
chosen_xyo = np.array([xy_offsets.loc[CHOSEN_Z].to_numpy()])

fig, ax = plt.subplots(figsize=(20,20))
transform_and_slice_mesh_mod(ax, ['TH', 'VM', 'VAL', 'SMT', 'CM', 'PCN', 'MD', 'CL', 'LP', 'LGd', 'RT', 'VPL', 'VPM', 'PO'], [CHOSEN_Z], at=at, translations=chosen_xyo, scale=BRAIN_SCALE, clip=[None, None, aba_mid[2]], color='red', aba=aba)

cc = filter_brain_coords(BRAIN, CSV_PATH, column=F_COLUMN, method=F_METHOD, threshold=F_THRESHOLD)
cc = cc[cc[:,0] == CHOSEN_Z]
ax.plot(cc[:,2], cc[:,1], 'or')

ax.plot([7000, 8000], [5400, 5400], '-g')
ax.axis('equal')
ax.invert_yaxis()
fig.show()

# fig.savefig(os.path.join(FIG_PATH, r'___thalslice.pdf'))
# viewer.screenshot(os.path.join(FIG_PATH, r'___thalslice.png'))