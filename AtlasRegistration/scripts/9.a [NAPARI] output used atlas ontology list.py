# Script to output a CSV of all atlas IDs used in 2D planes for cell density figure.
# From this list, a custom Excel sheet was created that enabled me to toggle which regions
# to show and/or merge for final vectorized output (see "9.b [napari] generate 2D + 3D figures.py").
# Excel sheets saved as aba100_regions_to_plot.xlsx and kim100_regions_to_plot.xlsx
# muniak@ohsu.edu
# 2024.11.13 - output verified for manuscript.

# Custom script path (must contain rothetal_pkg folder).
PKG_PATH = r'<<FILEPATH_TO_SCRIPTS>>'

# Set location of data.
ROOT_DIR = r'<<FILEPATH_TO_DATA>>'

import os
import sys
import pandas as pd
import numpy as np

# Custom modules.
sys.path.insert(0, PKG_PATH)
from rothetal_pkg.napari.aba import get_aba
from rothetal_pkg.napari.utils import is_int

# CSV path.
CSV_PATH = os.path.join(ROOT_DIR, 'CSVs')

# Options.
ATLAS = 'kim' # 'aba' or 'kim'
RES = 10
AP_BIN_SIZE = 100

aba = get_aba(RES, ATLAS)
aba_name = aba.atlas_name
viewer = napari.current_viewer()

AP_DOWNSAMPLE = AP_BIN_SIZE / aba.resolution[0] #10
if is_int(AP_DOWNSAMPLE):
    AP_DOWNSAMPLE = int(AP_DOWNSAMPLE)
else:
    raise ValueError('AP_DOWNSAMPLE is not an integer!')
    
aba100 = aba.annotation[::AP_DOWNSAMPLE, :, :]

def add_to_df(df, aba_id, ztxt):
    if aba_id == 0: return
    for v in aba.structures[aba_id]['structure_id_path'][:-1]:
        add_to_df(df, v, ztxt)
    if aba_id not in df.index:
        df.loc[aba_id, 'structure_id_path'] = '/'.join(['%d' % v for v in aba.structures[aba_id]['structure_id_path']])
        df.loc[aba_id, 'name'] = aba.structures[aba_id]['name']
        df.loc[aba_id, 'acronym'] = aba.structures[aba_id]['acronym']
        color = aba.structures[aba_id]['rgb_triplet']
        df.loc[aba_id, 'r'] = color[0]
        df.loc[aba_id, 'g'] = color[1]
        df.loc[aba_id, 'b'] = color[2]
    df.loc[aba_id, ztxt] = 1
    return

z_range = range(60, 85)
df = pd.DataFrame(columns=['id', 'structure_id_path', 'name', 'acronym', 'r', 'g', 'b'] + ['%d' % z for z in z_range]).set_index('id')
for z in z_range:
    aba_ids = np.unique(aba100[z, ...])
    for aba_id in aba_ids:
        add_to_df(df, aba_id, '%d' % z)
df.to_csv(os.path.join(CSV_PATH, '%s%d_used_ontology_list.csv' % (ATLAS, AP_BIN_SIZE)))