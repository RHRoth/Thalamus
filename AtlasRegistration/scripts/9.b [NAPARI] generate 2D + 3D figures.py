# Generate 2D / 3D figures from napari.
# muniak@ohsu.edu
# 2024.11.13 - output verified for manuscript.

# ** NOTES **
#
# 1) This script requires the manually curated Excel sheet [aba/kim]100_regions_to_plot.xlsx
#
# 2) 2D grid panels outputs were assembled in Adobe Illustrator (v29.0.1) to build the final figure. 
# 
# 3) The vectorized output of atlas annotation boundaries were smoothed in Adobe 
#    Illustrator (v29.0.1) to reduce the pixelated appearance of the curves.
#    All structure paths were selected and the smooth tool was applied with a setting of 5%.

# Custom script path (must contain rothetal_pkg folder).
PKG_PATH = r'<<FILEPATH_TO_SCRIPTS>>'

# Set location of data.
ROOT_DIR = r'<<FILEPATH_TO_DATA>>'

import os
import sys
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import cv2

# Custom modules.
sys.path.insert(0, PKG_PATH)
from rothetal_pkg.napari.aba import get_aba
from rothetal_pkg.napari.aba import load_aba_3d
from rothetal_pkg.napari.thal import get_brain_coords
from rothetal_pkg.napari.thal import get_brain_color
from rothetal_pkg.napari.utils import is_int

# CSV path.
CSV_PATH = os.path.join(ROOT_DIR, r'CSVs')

# XLSX path (for _regions_to_plot.xlsx).
XLSX_PATH = os.path.join(ROOT_DIR, r'CSVs')

# FIG output path.
FIG_PATH = os.path.join(ROOT_DIR, r'CSVs')

# Options.
BRAINS = [2, 3, 4, 6, 7, 8, 9, 10, 11]
ATLAS = 'kim'
RES = 10
AP_BIN_SIZE = 100  # Interval for 2D plates.  Also determines 2D bin sizes per plate.
BIN_SIZE = AP_BIN_SIZE
F_COLUMN = 'intensity'
F_METHOD = 'intensity'
F_THRESHOLD = 0.05
COLORMAP = 'Greens'

aba = get_aba(RES, ATLAS)
aba_name = aba.atlas_name

AP_DOWNSAMPLE = AP_BIN_SIZE / aba.resolution[0]
if is_int(AP_DOWNSAMPLE):
    AP_DOWNSAMPLE = int(AP_DOWNSAMPLE)
else:
    raise ValueError('AP_DOWNSAMPLE is not an integer!')
aba100 = aba.annotation[::AP_DOWNSAMPLE, :, :]

# Extract vectorized outlines from a slice of atlas annotation volume.
def plot_vectorized_aba(ax, df, aba_id_selection, z, rdp_eps=0):
    for aba_id in aba_id_selection:
        if aba_id == 0: continue  # empty space
        layer = aba100[z, ...]
        tf = np.zeros(layer.shape, dtype='uint8')
        idx = df['structure_id_path'].str.contains('/%d/' % aba_id)
        for id in df.index[idx]:
            tf[layer == id] = 1
        contours, hierarchy = cv2.findContours(tf, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        fc = df.loc[aba_id]['fill?']
        if ',' in str(fc):  # dumb, don't care.
            fc = np.fromstring(df.loc[aba_id, 'fill?'], sep=',')
            ec = 'none'
        else:
            fc = 'none'
            ec = [0, 0, 0, 1]
        for contour in contours:
            points = contour.squeeze()
            if points.ndim == 1: continue  # Just a single point!
            points = np.vstack((points, points[0, :]))
            if rdp_eps > 0:
                points = rdp(points, rdp_eps)
            ax.fill(points[:, 0], points[:, 1], edgecolor=ec, facecolor=fc, linestyle='-', linewidth=0.5)
    return ax

def add_box(ax, yx, bin, color, **kwargs):
    corners = np.array([yx + np.array([0, 0]),
                        yx + np.array([bin, 0]),
                        yx + np.array([bin, bin]),
                        yx + np.array([0, bin])])
    # note order of dims!                 
    ax.fill(corners[:, 1], corners[:, 0], facecolor=color, **kwargs)
    return ax

# Display vectorized atlas outlines and normalized cell count bins on a 2D plane.
# Creates a pyplot fig which can be saved as a PDF.
def make_plot_for_z(z, add_grid=True, all_lines=False, show=True):
    df = pd.read_excel(os.path.join(FIG_PATH, '%s100_regions_to_plot.xlsx' % ATLAS)).set_index('id')
    df['structure_id_path'] = df['structure_id_path'].astype(str)
    for idx in df.index:  # This is dumb, but avoids false matches because I'm doing this using strings.
        df.loc[idx, 'structure_id_path'] = '/' + df.loc[idx, 'structure_id_path'] + '/'
        tf = df.loc[:, z] == 1
    if not all_lines:
        tf = (df.loc[:, 'use?'] == 1) & tf
    fig, ax = plt.subplots(figsize=(20,20))
    ax = plot_vectorized_aba(ax, df, df.index[tf], z)
    if add_grid:
        xys = np.array(np.nonzero(aba100_bin_mean[z, ...])).T
        for xy in xys:
            ax = add_box(ax, xy * bin, bin=bin, color=cmap(aba100_bin_mean_v[z, xy[0], xy[1]].astype(float)), edgecolor='none')
    ax.axis('equal')
    ax.set_xlim([0, aba100.shape[2]])
    ax.set_ylim([0, aba100.shape[1]])
    ax.invert_yaxis()
    ax.axis('off')
    if show:
        fig.show()
    return fig


viewer = napari.current_viewer()
#viewer.add_image(aba100 % 255, scale=[AP_BIN_SIZE, RES, RES])
cmap = plt.get_cmap(COLORMAP)

bin = BIN_SIZE / RES
mid = int(aba100.shape[-1] / 2)
bin_offset = np.remainder(aba100.shape[-1] / 2, bin) + (bin / 2)
bin_offset = np.array([0, bin_offset, bin_offset])

RES_ALL = np.array([AP_DOWNSAMPLE, 1, 1]) * aba.resolution[0]

# Allocate filtered cell counts into bins.
aba_cc = {}
aba100_cc = {}
aba_nv = {}
aba100_bin = np.zeros(np.ceil(np.array((len(BRAINS), *aba100.shape)) / [1, 1, bin, bin]).astype(int))

for bi, b in enumerate(BRAINS):
    aba_cc[b] = get_brain_coords(b, CSV_PATH, RES, ATLAS, filter_column=F_COLUMN, filter_method=F_METHOD, filter_threshold=F_THRESHOLD)
    aba100_cc[b] = aba_cc[b] / (np.array([AP_DOWNSAMPLE, 1, 1]) * aba.resolution[0])
    aba_nv[b] = len(aba_cc[b])
    tmp_bin = np.round((aba100_cc[b] - bin_offset) / [1, bin, bin]).astype(int)  # Only binning on x/y.  Use offset to make binning match pixel display e.g., 5700<=x<5800.
    for row in tmp_bin:
        aba100_bin[bi, row[0], row[1], row[2]] += 1
    aba100_bin[bi, ...] /= aba_nv[b]

aba100_bin_mean = np.mean(aba100_bin, axis=0)
bmax = np.nanmax(aba100_bin_mean)
#bmax = np.floor(bmax * 1e3) / 1e3  # round down to tenth of percent
bmax = .006  # Fix upper limit of color scale to 0.6% for final figures.
aba100_bin_mean_v = aba100_bin_mean / bmax

# Show bins in napari.
hmean = viewer.add_image(aba100_bin_mean, scale=np.array([AP_DOWNSAMPLE, bin, bin]) * RES, translate=(bin_offset * RES), colormap=COLORMAP, name='brain bin%d avg' % (bin * RES), visible=True, contrast_limits=[0, bmax])

# Iterate through 100um plates and output PDFs.
z_range = range(60, 85)
for z in z_range:
    fig = make_plot_for_z(z, add_grid=1, all_lines=0, show=0)
    fig.savefig(os.path.join(FIG_PATH, '__%s_output_%d.pdf' % (ATLAS, z)))

# Create PDF of scale colorbar.
fig.colorbar(matplotlib.cm.ScalarMappable(norm=None, cmap=cmap), ax=fig.get_axes()[0])
fig.savefig(os.path.join(FIG_PATH, '__%s_output_colorbar.pdf' % ATLAS))

# Visualize key brain regions in 3D.
load_aba_3d('TH', aba=aba, colormap='gray', blending='translucent_no_depth', shading='smooth', opacity=0.05)
load_aba_3d('VM', aba=aba, colormap='gray', blending='translucent_no_depth', shading='smooth', opacity=0.10)
if ATLAS == 'aba':
    load_aba_3d('VAL', aba=aba, colormap='gray', blending='translucent_no_depth', shading='smooth', opacity=0.10)
elif ATLAS == 'kim':
    load_aba_3d('VA', aba=aba, colormap='gray', blending='translucent_no_depth', shading='smooth', opacity=0.10)
    load_aba_3d('VL', aba=aba, colormap='gray', blending='translucent_no_depth', shading='smooth', opacity=0.10)
load_aba_3d('root', aba=aba, colormap='gray', blending='translucent_no_depth', shading='smooth', opacity=0.05, visible=False)

# Create 3D dot equivalents of 2D bins.
zyx = np.array(np.nonzero(aba100_bin_mean)).T
c = aba100_bin_mean_v[np.nonzero(aba100_bin_mean)]
colors = cmap(c)
colors[:, -1] = c
colors[colors > 1] = 1
msize = c * 10
viewer.add_points((zyx * [1, bin, bin]) + bin_offset, size=msize, scale=[100, 10, 10], face_color=colors, border_color='none', border_width=0, blending='minimum', name='binned points')

# Create 3D dot scale.
scale_points = np.array([[69, 50, 77], [69, 51, 77], [69, 52, 77], [69, 53, 77], [69, 54, 77], [69, 55, 77]])
scale_levs = np.array([0.06, 0.05, 0.04, 0.03, 0.02, 0.01]) / 0.06
scale_colors = cmap(scale_levs)
scale_colors[:, -1] = scale_levs
viewer.add_points((scale_points * [1, bin, bin]) + bin_offset, size=scale_levs * 10, scale=[100, 10, 10], face_color=scale_colors, border_color='none', border_width=0, blending='minimum', name='scale points')

# Show filtered cells as dots.
dot_size = 3
for b in BRAINS:
    color = get_brain_color(b, CSV_PATH)
    color = 'black'  # If we don't want individual colors.
    h = viewer.add_points(aba100_cc[b], size=dot_size, face_color=color, border_color='white', border_width=0.001, name='brain%d dots' % b, scale=np.array([AP_DOWNSAMPLE, 1, 1]) * RES, visible=True, blending='translucent')


"""
napari camera settings used for 3D screenshots.
Note that output also depends on viewer window size.

# aba zoom
{'center': (6793.920219570407, 4017.505832416806, 6718.96297075135),
 'zoom': 0.2640128233521941,
 'angles': (-4.097651435286288, 26.090123427769704, 84.563517545347),
 'perspective': 0.0})

# aba zoom alt
{'center': (6553.524393002436, 4033.5385685890524, 6233.3500777937525),
 'zoom': 0.2321372827229829,
 'angles': (-4.097651435286289, 26.09012342776971, 84.56351754534701),
 'perspective': 0.0})

# pax zoom
{'center': (6793.920219570407, 4017.505832416806, 6718.96297075135),
 'zoom': 0.24039321980636771,
 'angles': (-4.097651435286289, 26.09012342776971, 84.56351754534701),
 'perspective': 0.0})

# whole brain
{'center': (6571.25, 3847.1868298471913, 5697.5),
 'zoom': 0.10496104523580606,
 'angles': (0.0, 0.0, 89.99999999999999),
 'perspective': 0.0})
"""