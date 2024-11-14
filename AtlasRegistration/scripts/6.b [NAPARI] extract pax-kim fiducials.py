# Load and extract coordinates of defined fiducials and thalamus alignment box from ABA.
# muniak@ohsu.edu
# 2024.11.07 - output verified for manuscript.

# Custom script path (must contain rothetal_pkg folder).
PKG_PATH = r'<<FILEPATH_TO_SCRIPTS>>'

# Set location of data.
ROOT_DIR = r'<<FILEPATH_TO_DATA>>'

import os
import sys
import numpy as np
import pandas as pd
from scipy.ndimage import center_of_mass

# Custom modules.
sys.path.insert(0, PKG_PATH)
from rothetal_pkg.napari.aba import get_aba
from rothetal_pkg.napari.aba import get_aba_mask
from rothetal_pkg.napari.utils import is_int

# CSV path.
CSV_PATH = os.path.join(ROOT_DIR, 'CSVs')

# Options.
SHOW_RESULTS = True
WRITE_RESULTS = True
RES = 10
AP_RESAMPLE = 100
AP_RELATIVE_RESAMPLE = AP_RESAMPLE / RES
if is_int(AP_RELATIVE_RESAMPLE):
	AP_RELATIVE_RESAMPLE = int(AP_RELATIVE_RESAMPLE)
else:
	raise ValueError('AP_RELATIVE_RESAMPLE is not an integer!')

kim = get_aba(RES, 'kim')  ### Using Kim atlas!
kim_name = kim.atlas_name

""" When we get masks from the Kim/Pax atlas, we will "resample" the A/P axis to
    100 um steps, because that's what the original atlas is (100 x 10 x 10 um).
    BrainGlobe's instance of the atlas simply repeats each coronal slice along the
    A/P axis to match the voxel resolution.  But the only way to get the full 10-um
    resolution on the L/M and D/V axes is to first obtain the 10-um^3 dataset (kim_mouse_10um).
"""

viewer = napari.current_viewer()
ref = viewer.add_image(kim.reference, colormap='gray', scale=[RES]*3, name=kim_name)
ann = viewer.add_image(kim.annotation, colormap='gray', scale=[RES]*3, name=kim_name + '_ann', opacity=0)


"""
TH   - thalamus
SubB - subbrachial nucleus

aca  - anterior commissure, temporal limb
PrG  - lateral geniculate, ventral part

EPI  - epithalamus (mostly habenula)
MB   - midbrain
SCs  - superior colliculus, sensory related

ic   - internal capsule
cp   - cerebral peduncle
2n   - optic nerve
3V   - 3rd ventricle

DG   - dentate gyrus
cc   - corpus callosum

MG   - medial geniculate complex

SCO  - subcommissural organ

"""


""" ABA axes are (when coronal):
    0: A-P (z)
    1: D-V (y)
    2: L-M (x)
"""


""" Flag to only consider data in hemi of ABA. """
hemi_flag = 'left'


##########################################################################################
""" This section obtains defined bounds of reference rectangles for brain alignment.
"""
##########################################################################################

""" One section posterior to any 'act' within 0.25mm of midline,
    or anterior-most section of 'TH' if somehow a gap be. 
    Also posterior-most section of 'TH'. """
mid_distance = 250  # In um.
# Get 'act' mask.
mask = get_aba_mask('aca', aba=kim, hemi=hemi_flag, ap_resample=AP_RESAMPLE)  # Changed to Kim nomenclature.
# Get indices within midline.
mid_val = mask.shape[2] / 2
mid_range = np.arange(np.floor(mid_val - (mid_distance / RES)), 
                       np.ceil(mid_val + (mid_distance / RES)), dtype=int)
# Collapse to A-P axis only.
mask = np.sum(mask[:,:,mid_range], axis=(2, 1))
# Z-index of last section with 'act' + 1.
idx = np.amax(np.flatnonzero(mask)) + 1
# Get 'TH' mask.
#mask = get_aba_mask('TH', aba=kim, hemi=hemi_flag)
mask = np.logical_xor(get_aba_mask('TH', aba=kim, hemi=hemi_flag, ap_resample=AP_RESAMPLE).astype(bool),
                      get_aba_mask('SubB', aba=kim, hemi=hemi_flag, ap_resample=AP_RESAMPLE).astype(bool))
### Fix for badly coded pixels (as '617'/MDC in plate 119 of Kim dataset) in middle of brainstem!
mask[int(12500 / RES / AP_RELATIVE_RESAMPLE):, :, :] = False
th_mask = mask.copy()  # To save for repeat uses later on.
# Collapse to A-P axis only.
mask = np.sum(th_mask, axis=(2,1))
# Z-index of first section with 'TH' _OR_ first past 'act'.
idx_a = np.amax([idx, np.amin(np.flatnonzero(mask))])
# Z-index of last section with 'TH' + another 100 um buffer (+ 1).
idx_p = np.amax(np.flatnonzero(mask)) + int(100 // RES // AP_RELATIVE_RESAMPLE) + 1



""" Dorsal and ventral bounds of ((TH + MB) - EPI) in each section within A-P range. """
mask = np.logical_xor(np.logical_or(th_mask,
                                    get_aba_mask('MB', aba=kim, hemi=hemi_flag, ap_resample=AP_RESAMPLE).astype(bool)),
                      get_aba_mask('EPI', aba=kim, hemi=hemi_flag, ap_resample=AP_RESAMPLE).astype(bool))
mask[:idx_a, :, :] = False
mask[idx_p:, :, :] = False
mask_tmp = np.sum(mask, axis=2)
idx_th_d = np.array([np.amin(np.flatnonzero(mask_tmp[i, :])) if np.any(mask_tmp[i, :]) else np.nan for i in range(mask_tmp.shape[0])])
idx_th_v = np.array([np.amax(np.flatnonzero(mask_tmp[i, :])) if np.any(mask_tmp[i, :]) else np.nan for i in range(mask_tmp.shape[0])])


""" Lateral and medial bounds of (TH - EPI) in each section within A-P range. """
mask_tmp = np.sum(mask, axis=1)
if hemi_flag.lower().startswith('l'):
    idx_l = np.array([np.amax(np.flatnonzero(mask_tmp[i, :])) if np.any(mask_tmp[i, :]) else np.nan for i in range(mask_tmp.shape[0])])
elif hemi_flag.lower().startswith('r'):
    idx_l = np.array([np.amin(np.flatnonzero(mask_tmp[i, :])) if np.any(mask_tmp[i, :]) else np.nan for i in range(mask_tmp.shape[0])])
idx_m = mid_val  # From above.


""" Ventral bound of mid-region of (SCs) in each section within A-P range. """
mask = get_aba_mask('SCs', aba=kim, hemi=hemi_flag, ap_resample=AP_RESAMPLE).astype(bool)
mask[:idx_a, :, :] = False
mask[idx_p:, :, :] = False
mask = np.sum(mask[:, :, mid_range], axis=2)
idx_sc_v = np.array([np.amax(np.flatnonzero(mask[i, :])) if np.any(mask[i, :]) else np.nan for i in range(mask.shape[0])])


""" Dorsal bound of ((TH + MB) - EPI) except if (SCs) present, then its ventral bound. """
idx_d = np.nanmax(np.vstack((idx_th_d, idx_sc_v)), axis=0)


""" Dorsal and ventral bounds of (int + cpd) in each section within A-P range. """
mask = np.logical_or(get_aba_mask('ic', aba=kim, hemi=hemi_flag, ap_resample=AP_RESAMPLE).astype(bool),  # Changed to Kim nomenclature.
                     get_aba_mask('cp', aba=kim, hemi=hemi_flag, ap_resample=AP_RESAMPLE).astype(bool))  # Changed to Kim nomenclature.
mask[:idx_a, :, :] = False
mask[idx_p:, :, :] = False
mask = np.sum(mask, axis=2)
idx_ic_d = np.array([np.amin(np.flatnonzero(mask[i, :])) if np.any(mask[i, :]) else np.nan for i in range(mask.shape[0])])
idx_ic_v = np.array([np.amax(np.flatnonzero(mask[i, :])) if np.any(mask[i, :]) else np.nan for i in range(mask.shape[0])])


""" Dorsal bound of (IIn) in each section within A-P range. """
mask = get_aba_mask('2n', aba=kim, hemi=hemi_flag, ap_resample=AP_RESAMPLE).astype(bool)  # Changed to Kim nomenclature.
mask[:idx_a, :, :] = False
mask[idx_p:, :, :] = False
mask = np.sum(mask, axis=2)
idx_iin_d = np.array([np.amin(np.flatnonzero(mask[i, :])) if np.any(mask[i, :]) else np.nan for i in range(mask.shape[0])])


""" Switch-over point where (IIn) is more dorsal than ventral edge of (int + cpd). """
xover_v = np.argmax((idx_ic_v - idx_iin_d) >= 0)


""" Dorsal-most bound of blob of (V3) closest to ventral-most bound of (TH) in each section within A-P range. """
mask = get_aba_mask('3V', aba=kim, hemi=hemi_flag, ap_resample=AP_RESAMPLE).astype(bool)  # Changed to Kim nomenclature.
mask = np.sum(mask, axis=2)
mask = [np.flatnonzero(mask[i, :]) if np.any(mask[i, :]) else np.zeros(1) for i in range(mask.shape[0])]
# Index of dorsal-most bound of each V3 blob.
mask = [m[np.flatnonzero(np.hstack(([1], np.diff(m) - 1)))] for m in mask]
# Differences from TH ventral-most bound.
mask = np.array([m[np.argmin(np.abs(m - th_v))] for m, th_v in zip(mask, idx_th_v)])
mask[:idx_a] = np.nan
mask[idx_p:] = np.nan
# Fix for sections without V3 annotations within A-P range.. use value from next-posterior section.
for i in range(len(mask))[::-1]:
    if np.isnan(mask[i]):
        continue
    elif mask[i] < idx_d[i]:
        mask[i] = mask[i+1]
idx_v3_d = np.array(mask)


""" Switch-over point where (IIn) is more dorsal than ventral edge of (int + cpd).
    Before this index, use idx_v3_d.
    From this index onwards, use idx_ic_v.
    Add +1 to facilitate array syntax.
    Also used to compute a fiducial.
"""
idx_v = np.hstack((idx_v3_d[:xover_v], idx_ic_v[xover_v:])) + 1
# Fix for very last couple sections where (int + cpd) disappears.  Just duplicate the posterior-most value.
for i in range(idx_a, idx_p):
    if np.isnan(idx_v[i]):
        idx_v[i] = idx_v[i-1]


""" Switch-over point where (IIn) is more dorsal than dorsal edge of (int + cpd).
    Used to compute a fiducial.
"""
xover_d = np.argmax((idx_ic_d - idx_iin_d) >= 0)


##########################################################################################
""" This section obtains reference fiducial coordinates from ABA for rotation correction.
    See Hunnicutt et al. (2014), Supplemental Figure 5.
    
    After finding the coronal plane that matches the criteria, the average D-V
    location proximal to the midline ('mid_range', computed above) is used.
"""
##########################################################################################


""" Anterior-most appearance of Dentate Gyrus ('DG'). """
f_dg = np.zeros(3)
mask = get_aba_mask('DG', aba=kim, ap_resample=AP_RESAMPLE).astype(bool)
f_dg[0] = np.amin(np.flatnonzero(np.sum(mask, axis=(2, 1))))
f_dg[1] = np.mean(np.flatnonzero(np.sum(mask[f_dg[0].astype(int), :, :][:, mid_range], axis=1)))
f_dg[2] = mid_val


""" Posterior-most section of anterior commissure 'act' within 0.5mm of midline. """
f_act = np.zeros(3)
mask = get_aba_mask('aca', aba=kim, ap_resample=AP_RESAMPLE)  # Changed to Kim nomenclature.
f_act[0] = np.amax(np.flatnonzero(np.sum(mask[:, :, mid_range], axis=(2, 1))))
f_act[1] = np.mean(np.flatnonzero(np.sum(mask[f_act[0].astype(int), :, :][:, mid_range], axis=1)))  # Double-indexing to stop dimensions shifting order.
f_act[2] = mid_val


""" Anterior-most and posterior-most positions of corpus callosum ('cc') that cross the midline. """
f_cca = np.zeros(3)
f_ccp = np.zeros(3)
mask = get_aba_mask('cc', aba=kim, ap_resample=AP_RESAMPLE).astype(bool)
# 'cc' is wide enough that it spans the entirety of 'mid_range' on the L-M axis,
# so any sections that do not span the midline will have zeros in them and report False below.
tmp = np.all(np.sum(mask, axis=1)[:, mid_range], axis=1)
f_cca[0] = np.amin(np.flatnonzero(tmp))
f_ccp[0] = np.amax(np.flatnonzero(tmp))
f_cca[1] = np.mean(np.flatnonzero(np.sum(mask[f_cca[0].astype(int), :, :][:, mid_range], axis=1)))
f_ccp[1] = np.mean(np.flatnonzero(np.sum(mask[f_ccp[0].astype(int), :, :][:, mid_range], axis=1)))
f_cca[2] = mid_val
f_ccp[2] = mid_val


""" Center of posterior-most LGv. """
# Get 'LGv' mask.
mask = get_aba_mask('PrG', aba=kim, hemi=hemi_flag, ap_resample=AP_RESAMPLE)  # Changed to Kim nomenclature.
# Z-index of posterior-most section.
idx = np.amax(np.flatnonzero(np.sum(mask, axis=(2, 1))))
# Fiducial is center-of-mass of this section.
f_lgv = np.hstack((idx, center_of_mass(mask[idx].astype(bool))))


""" Center of posterior-most MG. <<< MIGHT NEED TO CHECK ABOUT THAT SINGLE PIXEL IN LAST SECTION """
# Get 'MG' mask.
mask = get_aba_mask('MG', aba=kim, hemi=hemi_flag, ap_resample=AP_RESAMPLE)
# Z-index of posterior-most section.
idx = np.amax(np.flatnonzero(np.sum(mask, axis=(2, 1))))
# Fiducial is center-of-mass of this section.
f_mg = np.hstack((idx, center_of_mass(mask[idx].astype(bool))))


""" Dorsal bound of (IIn) as it crosses ventral and dorsal bounds of (int + cpd). """
# Get 'IIn' mask.
mask = get_aba_mask('2n', aba=kim, hemi=hemi_flag, ap_resample=AP_RESAMPLE).astype(bool)
mask[:idx_a, :, :] = False
mask[idx_p:, :, :] = False
# Dorsal-edge of 'IIn' as it crosses ventral (int + cpd), from above.
tmp_v = np.amin(np.flatnonzero(np.sum(mask[xover_v, :, :], axis=1)))
# Average L-M coordinate to complete fiducial.
f_iinv = np.array([xover_v, tmp_v, np.mean(np.flatnonzero(mask[xover_v, tmp_v, :]))])
# Dorsal-edge of 'IIn' as it crosses dorsal (int + cpd), from above.
tmp_d = np.amin(np.flatnonzero(np.sum(mask[xover_d, :, :], axis=1)))
# Average L-M coordinate to complete fiducial.
f_iind = np.array([xover_d, tmp_d, np.mean(np.flatnonzero(mask[xover_d, tmp_d, :]))])


""" Midpoint of (SCO) in section just posterior to end of (EPI). """
f_sco = np.zeros(3)
# Posterior-edge of 'EPI' + 1.
mask = get_aba_mask('EPI', aba=kim, hemi=hemi_flag, ap_resample=AP_RESAMPLE).astype(bool)
f_sco[0] = np.amax(np.flatnonzero(np.sum(mask, axis=(2, 1)))) + 1
mask = get_aba_mask('SCO', aba=kim, hemi=hemi_flag, ap_resample=AP_RESAMPLE).astype(bool)
f_sco[1] = np.mean(np.flatnonzero(np.sum(mask[f_sco[0].astype(int), :, :][:, mid_range], axis=1)))
f_sco[2] = mid_val


##########################################################################################
""" Correct for relative resampling along A-P of Kim atlas (due to 100um step size).
"""
##########################################################################################

#idx_a *= AP_RELATIVE_RESAMPLE
#idx_p *= AP_RELATIVE_RESAMPLE
f_dg[0] *= AP_RELATIVE_RESAMPLE
f_act[0] *= AP_RELATIVE_RESAMPLE
f_cca[0] *= AP_RELATIVE_RESAMPLE
f_ccp[0] *= AP_RELATIVE_RESAMPLE
f_lgv[0] *= AP_RELATIVE_RESAMPLE
f_mg[0] *= AP_RELATIVE_RESAMPLE
f_iinv[0] *= AP_RELATIVE_RESAMPLE
f_iind[0] *= AP_RELATIVE_RESAMPLE
f_sco[0] *= AP_RELATIVE_RESAMPLE



##########################################################################################
""" Output and visualize results.
"""
##########################################################################################

""" Create and add rectangle shapes to napari matching above bounds. """
r_verts = np.stack((idx_d, idx_v, idx_l, np.tile(idx_m, idx_l.shape)), axis=1)
r_corners = r_verts[idx_a:idx_p, [[0, 2], [0, 3], [1, 3], [1, 2]]]
idx_ap = np.tile(np.arange(idx_a, idx_p).reshape((r_corners.shape[0], 1, 1)), (1, 4, 1)) * AP_RELATIVE_RESAMPLE  ## CORRECTION
r_shapes = np.concatenate((idx_ap, r_corners), axis=2)
if SHOW_RESULTS:
    r_layer = viewer.add_shapes(r_shapes, shape_type='polygon', name='kim_rects')
    r_layer.scale *= RES
    
    
""" Create and add fiducial shapes to napari. """
if SHOW_RESULTS:
    tris = viewer.add_shapes(np.array([np.vstack((f_act, f_cca, f_ccp)), np.vstack((f_act, f_cca, f_dg))]), 
                             shape_type='polygon', face_color=[0,0,0,0], edge_color=['cyan', 'red'], edge_width=1, name='kim_fiducials')
    tris.scale *= RES
    trisp = viewer.add_points(np.vstack((f_cca, f_act, f_dg, f_ccp, f_sco)), size=0.4, face_color='yellow', name='kim_fiducials2')
    trisp.scale *= RES


""" Fiducials dataframe. """
kim_fids = pd.DataFrame(columns=['id', 'ap', 'dv', 'lm'])
kim_fids['id'] = ['cca', 'act', 'dg', 'ccp', 'sco']
kim_fids.loc[:, ['ap', 'dv', 'lm']] = np.vstack((f_cca, f_act, f_dg, f_ccp, f_sco))
if WRITE_RESULTS:
    kim_fids.round(1).to_csv(os.path.join(CSV_PATH, 'kim_%dum_fiducials.csv' % RES), index=False)


""" Rectangles dataframe. """
kim_rects = pd.DataFrame(np.hstack((np.arange(idx_a, idx_p)[:, np.newaxis], np.stack((idx_d, idx_v, np.tile(idx_m, idx_l.shape), idx_l), axis=1)[idx_a:idx_p])), 
                         columns=['ap', 'd', 'v', 'm', 'l'])
kim_rects['ap'] *= AP_RELATIVE_RESAMPLE  ## CORRECTION
if WRITE_RESULTS:
    kim_rects.round(0).to_csv(os.path.join(CSV_PATH, 'kim_%dum_rectangles.csv' % RES), index=False)

