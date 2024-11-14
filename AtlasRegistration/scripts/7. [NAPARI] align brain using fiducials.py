# Align experimental thalami to ABA or PAX/KIM atlases using fiducials.
# muniak@ohsu.edu
# 2024.11.11 - output verified for manuscript.

# Custom script path (must contain rothetal_pkg folder).
PKG_PATH = r'<<FILEPATH_TO_SCRIPTS>>'

# Set location of data.
ROOT_DIR = r'<<FILEPATH_TO_DATA>>'

# Set location of downsampled image stacks.
IMG_PATH = r'<<FILEPATH_TO_DATA>>'

import os
import sys
import numpy as np
import pandas as pd
from aicsimageio import AICSImage
from transforms3d._gohlketransforms import affine_matrix_from_points

# Custom modules.
sys.path.insert(0, PKG_PATH)
from rothetal_pkg.napari.aba import get_aba
from rothetal_pkg.napari.affine3d import affine3d
from rothetal_pkg.napari.affine3d import apply_affine
from rothetal_pkg.napari.vedo import vedo2napari
from rothetal_pkg.napari.vedo import rects2mesh
from rothetal_pkg.napari.vedo import transform_and_slice_mesh
from rothetal_pkg.napari.thal import axis_length_spanning_volume_percent_areas
from rothetal_pkg.napari.thal import get_slice_offsets_upper_left
from rothetal_pkg.napari.thal import sample_xy_span_at_z

# CSV path.
CSV_PATH = os.path.join(ROOT_DIR, 'CSVs')

# Options.
BRAIN_NUM = 6  # 2, 3, 4, 6, 7, 8, 9, 10, 11
SHOW_RESULTS = True  # <- not recommended for 'kim' because of the 100um Z-sampling.  looks odd when sliced onto brain sections.
SHOW_BRAIN = True
WRITE_RESULTS = True
ATLAS = 'aba'  # 'aba' or 'kim'
RES = 10
# Scale values reflect the downsampled calibration used in the TrakEM2 projects
# where fiducials were plotted.  I suppose I could've logged this in a CSV
# somewhere... but I didn't so we're gonna hard-code it rather than digging
# into TrakEM2 XMLs... it never changes for this project!
BRAIN_SCALE = np.array((40.0, 3.632005230087531, 3.632005230087531))

# Note 'aba' var can refer to either ABA or PAX/KIM, depending on 'ATLAS'.
aba = get_aba(RES, ATLAS)
aba_name = aba.atlas_name
viewer = napari.current_viewer()

# Get aba fiducials and rectangles.
df_aba_fids = pd.read_csv(os.path.join(CSV_PATH, '%s_%dum_fiducials.csv' % (ATLAS, RES)), index_col='id')
aba_fids = np.array(df_aba_fids.loc[['cca', 'act', 'dg', 'ccp', 'sco'], ['ap', 'dv', 'lm']])

df_aba_rects = pd.read_csv(os.path.join(CSV_PATH, '%s_%dum_rectangles.csv' % (ATLAS, RES)))
aba_rects = np.array(df_aba_rects)

aba_scale = np.array(RES)

# Load experimental brain data.
brain_name = 'brain%d' % BRAIN_NUM
df_brain_fids = pd.read_csv(os.path.join(CSV_PATH, '%s_fiducials.csv' % brain_name), index_col='id')
brain_fids = np.array(df_brain_fids.loc[['cca', 'act', 'dg', 'ccp', 'sco'], ['ap', 'dv', 'lm']])
f_lgn_l = df_brain_fids.loc['lgn_l', ['ap', 'dv', 'lm']]
f_lgn_r = df_brain_fids.loc['lgn_r', ['ap', 'dv', 'lm']]
f_str_l = df_brain_fids.loc['str_l', ['ap', 'dv', 'lm']]
f_str_r = df_brain_fids.loc['str_r', ['ap', 'dv', 'lm']]

df_brain_rects = pd.read_csv(os.path.join(CSV_PATH, '%s_rectangles.csv' % brain_name))
brain_rects = np.array(df_brain_rects)

if SHOW_BRAIN:
    if BRAIN_NUM < 5:
        img = AICSImage(os.path.join(IMG_PATH, '%s__c2__x8.ome.tiff' % brain_name))
    else:
        img = AICSImage(os.path.join(IMG_PATH, '%s__c2__x4.ome.tiff' % brain_name))
    #### Temporary fix, using old AICSImage library -- assuming that's the reason for Z not reading correctly? ###
    scale_tmp = img.physical_pixel_sizes
    if (scale_tmp.Z is None) or (scale_tmp.Z == 0):
        scale_tmp = (40, scale_tmp.Y, scale_tmp.X)
    brain = viewer.add_image(img.get_image_data('ZYX', T=0, C=0), name=brain_name, scale=scale_tmp)
    # brain = viewer.add_image(img.get_image_data('ZYX', T=0, C=0), name=brain_name, scale=img.physical_pixel_sizes)

# Visualize landmarks.
tris = viewer.add_shapes(np.array([brain_fids[[0, 1, 3], :],
                                   brain_fids[[0, 1, 2], :],]),
                         shape_type='polygon', face_color=[0,0,0,0], edge_color=['cyan', 'red'], edge_width=1, name='brain tris')
tris.scale = BRAIN_SCALE
tris.visible = False

brain_v = rects2mesh(brain_rects, BRAIN_SCALE)
h_brain = vedo2napari(brain_v, name='brain mesh', colormap='yellow', opacity=0.6)

brain_fids_tx = brain_fids * BRAIN_SCALE
h = viewer.add_points(brain_fids_tx, size=200, face_color='yellow', name='brain fids')


####################
# Alignment steps. #
####################

# Establish ABA midline values.
aba_mid = aba_scale * aba.shape / 2.

# Affine transform dictionary.
ats = dict()
ats['origin'] = np.eye(4)

### Alignment #1 -- match fiducial points of CCA, ACT, DG, CCP.
# Start with identity 3D affine.
at_triangles = np.eye(4)
# Get and insert 2D rotation/scale for A-P and D-V axes only...
fids_to_use = [0, 1, 2, 3]
tmp = affine_matrix_from_points((aba_fids[fids_to_use, :] * aba_scale)[:, :2].T, (brain_fids[fids_to_use, :] * BRAIN_SCALE)[:, :2].T)
# Insert the "2D" transform into a 3D affine, without affecting L-M axis.
at_triangles[:2, [0, 1, 3]] = tmp[:2, :]
# Save AT to dictionary.
ats['triangles'] = at_triangles


### Alignment #2 -- compensate for cutting shear.
# Get shear value: difference in A-P over L-M for two fiducials... posterior end of LGN and split of stria terminalis.
tmp = np.vstack((f_lgn_r - f_lgn_l, f_str_r - f_str_l)) * BRAIN_SCALE
shear_val = np.mean(tmp[:, 0] / tmp[:, 2])
# Build shear affine.
at_shear = affine3d()
at_shear.shearz(hx=shear_val, center=aba_mid, pre=True)
# Concat and save AT to dictionary.
ats['shear'] = at_shear.m @ ats['triangles']

# Show alignment progress, if enabled.
aba_fids_tx = apply_affine(aba_fids * aba_scale, ats['shear'])
if SHOW_RESULTS:
    viewer.add_points(aba_fids_tx, size=200, face_color='blue')
aba_v = rects2mesh(aba_rects, aba_scale)
aba_v = apply_affine(aba_v, ats['shear'])
if SHOW_RESULTS:
    h_trishear = vedo2napari(aba_v, colormap='blue', name='tri + shear', opacity=0.6)
    h_trishear.blending = 'additive'
    h_trishear.visible = False


### Alignment #3 -- scale A-P (Z) axis to match 99% of box volume from habenula fiducial (SCO) to anterior pole.
SPACING = BRAIN_SCALE[0]  # <- Cutting thickness.
LO = 0.01  # <- This establishes 99%.
HI = 1.0  # <- This == SCO location.
# Get Z-vals to sample based on current position of box/SCO.
brain_zs = np.arange(brain_fids_tx[4, 0], brain_v.bounds()[0] - SPACING, -SPACING)[::-1]
aba_zs = np.arange(aba_fids_tx[4, 0], aba_v.bounds()[0] - SPACING, -SPACING)[::-1]
# Calculate ratio of axis length that spans 99% volume using custom function.
z_scale = axis_length_spanning_volume_percent_areas(brain_v, brain_zs, lo=LO, hi=HI) / axis_length_spanning_volume_percent_areas(aba_v, aba_zs, lo=LO, hi=HI)
# Build Z scale affine.
at_zscale = affine3d()
at_zscale.scale(sx=z_scale, center=aba_fids_tx[4, :], pre=True)
# Concat and save AT to dictionary.
ats['zscale'] = at_zscale.m @ ats['shear']


### Alignment #4 -- match SCO coordinate so boxes are roughly in same space.
fids_to_use_for_translation = [4]  # Originally considered using multiple fiducials, hence "mean" below.
# Temporary version of tranformed fiducials up to this point so we can determine necessary translation, but only on AP and DV axes, leave midline where it is.
aba_fids_tx = apply_affine(aba_fids * aba_scale, ats['zscale'])
xyz_trans = np.mean(brain_fids_tx[fids_to_use_for_translation, :2] - aba_fids_tx[fids_to_use_for_translation, :2], axis=0)
# Build translation affine.
at_scotrans = affine3d()
at_scotrans.translate(*xyz_trans, tz=0, pre=True)  # < Note only using first two dims.
# Concat and save AT to dictionary.
ats['scotrans'] = at_scotrans.m @ ats['zscale']

# Show alignment progress, if enabled.
aba_fids_tx = apply_affine(aba_fids * aba_scale, ats['scotrans'])
if SHOW_RESULTS:
    viewer.add_points(aba_fids_tx, size=200, face_color='red')
aba_v = rects2mesh(aba_rects, aba_scale)
aba_v = apply_affine(aba_v, ats['scotrans'])
if SHOW_RESULTS:
    h_zscale = vedo2napari(aba_v, colormap='red', name='zscale', opacity=0.6)
    h_zscale.blending = 'additive'
    h_zscale.visible = False


### Alignment #5 -- scale D-V (Y) and L-M (X) axes to average width and height of rectangle/polygon at each slice of brain within 2-mm span of SCO.
### THIS ASSUMES WE ARE ALIGNED TO HABENULA/SCO FIDUCIAL!!
sample_span = 1000  # <- um in each direction from SCO.
# Gather Z-vals to sample box at.  Will be same A-P vals for both brain and ABA _because_ of SCO alignment and A-P scaling.
sample_zs = [z for z in np.arange(brain_fids_tx[4, 0] - sample_span, brain_fids_tx[4, 0] + sample_span + 1, SPACING)
             if ((z > np.amax((brain_v.bounds()[0], aba_v.bounds()[0]))) and (z < np.amin((brain_v.bounds()[1], aba_v.bounds()[1]))))]
# Sample width/height at quarter, half, and three-quarters of bounds of sliced rectangle/polygon in each dimension.
samp_steps = [0.25, 0.50, 0.75] #np.arange(0.05, 1, 0.1)
# Get samples, already averaged per slice.  Note my x/y designations flip-flop a bit between functions...
brain_samples = np.array([sample_xy_span_at_z(brain_v, z, steps=samp_steps, return_mean=True) for z in sample_zs])
aba_samples = np.array([sample_xy_span_at_z(aba_v, z, steps=samp_steps, return_mean=True) for z in sample_zs])
# Calculate scale ratio.
x_scale, y_scale = np.mean(brain_samples / aba_samples, axis=0)
# Build XY scale affine.
at_xyscale = affine3d()
at_xyscale.scale(sy=y_scale, sz=x_scale, center=aba_fids_tx[4, :], pre=True)  # <--- confusing about orientation, be careful.  x/y/z is 1st/2nd/3rd dim for affine matrix.
# Concat and save AT to dictionary.
ats['xyscale'] = at_xyscale.m @ ats['scotrans']

# Show alignment progress, if enabled.
aba_fids_tx = apply_affine(aba_fids * aba_scale, ats['xyscale'])
if SHOW_RESULTS:
    viewer.add_points(aba_fids_tx, size=200, face_color='magenta')
aba_v = rects2mesh(aba_rects, aba_scale)
aba_v = apply_affine(aba_v, ats['xyscale'])
if SHOW_RESULTS:
    h_xyscale = vedo2napari(aba_v, colormap='magenta', name='xyscale', opacity=0.6)
    h_xyscale.blending = 'additive'


### Alignment #6 -- work out slice-specific D-V (Y) and L-M (X) translations to compensate for drift in serial sections.
# Get all Z-vals in brain sample.
zs = np.unique(brain_rects[:,0] * BRAIN_SCALE[0])
# Offsets based on upper-left corner of each slice polygon/rectangle.
xy_offsets = get_slice_offsets_upper_left(brain_v.copy(), rects2mesh(aba_rects, aba_scale), zs, ats['xyscale'])


### Export results.
if WRITE_RESULTS:
    # Save final affine transform 'xyscale' that is applied globally to all coordinate data for brain (alignments 1-5).
    pd.DataFrame(ats['xyscale'], columns=['a0','a1','a2','a3']).to_csv(os.path.join(CSV_PATH, '%s_at_%s_%dum.csv' % (brain_name, ATLAS, RES)), index=False)
    # Save specific translations for each slice as separate file (alignment 6).
    pd.DataFrame(np.hstack((zs[:, np.newaxis], xy_offsets)), columns=['z','tz','ty','tx']).to_csv(os.path.join(CSV_PATH, '%s_txy_%s_%dum.csv' % (brain_name, ATLAS, RES)), index=False)


### Visualize results.
if SHOW_RESULTS:
    # Create slices of brain box at Zs of brain slices.
    transform_and_slice_mesh(brain_v.copy(), zs, scale=BRAIN_SCALE, color='yellow', name='brain box')

    # Create slices of transformed ABA box at Zs of brain slices.
    transform_and_slice_mesh(aba_v.copy(), zs, translations=xy_offsets, scale=BRAIN_SCALE, color='red', name='aba box adjusted')

    # Create slices of transformed ABA TH boundaries at Zs of brain slices.
    transform_and_slice_mesh(['TH'], zs, at=ats['xyscale'], translations=xy_offsets, scale=BRAIN_SCALE, clip=[None, None, aba_mid[2]], color='magenta', aba=aba)

    # Create slices of transformed ABA VM/VAL boundaries at Zs of brain slices.  Repeat this for any other named area!
    transform_and_slice_mesh(['VM', 'VAL'], zs, at=ats['xyscale'], translations=xy_offsets, scale=BRAIN_SCALE, clip=[None, None, aba_mid[2]], color='red', aba=aba)
