# Perform stats on cell atlas assignments.
# muniak@ohsu.edu
# 2024.11.13 - output verified for manuscript.

# Custom script path (must contain rothetal_pkg folder).
PKG_PATH = r'<<FILEPATH_TO_SCRIPTS>>'

# Set location of data.
ROOT_DIR = r'<<FILEPATH_TO_DATA>>'

import os
import sys
import numpy as np
import pandas as pd

# Custom modules.
sys.path.insert(0, PKG_PATH)
from rothetal_pkg.napari.aba import get_aba

# CSV path.
CSV_PATH = os.path.join(ROOT_DIR, 'CSVs')

# Options.
BRAINS = [2, 3, 4, 6, 7, 8, 9, 10, 11]
DO_MERGE = True
WRITE_RESULTS = True
FILTER_THRESHOLD = 0.05
RES = 10
ATLAS = 'aba'  # 'aba' or 'kim'

aba = get_aba(RES, ATLAS)
aba_name = aba.atlas_name

df = pd.DataFrame(columns=['acronym', 'name', 'structure_id_path'] + ['brain%d' % b for b in BRAINS])

for b in BRAINS:
    df_brain = pd.read_csv(os.path.join(CSV_PATH, 'brain%d_cellcoords.csv' % b))
    idx = df_brain['intensity_norm'] >= FILTER_THRESHOLD
    ids, counts = np.unique(df_brain.loc[idx, 'id_%s_%dum' % (ATLAS, RES)], return_counts=True)
    df['brain%d' % b] = df['brain%d' % b].astype(float)  # To avoid .fillna downcasting warning.
    for id, count in zip(ids, counts):
        if id not in df.index:
            df.loc[id, 'acronym'] = aba.structures[id]['acronym']
            df.loc[id, 'name'] = aba.structures[id]['name']
            df.loc[id, 'structure_id_path'] = '/'.join([aba.structures[v]['acronym'] for v in aba.structures[id]['structure_id_path']])
        df.loc[id, 'brain%d' % b] = count

df.fillna(0, inplace=True)  # Convert nans to 0.

#Build dataframe of _normalized_ cell counts (per brain) assigned to ABA areas.
df_norm = df.copy()
for b in BRAINS:
    col = 'brain%d' % b
    df_norm[col] /= df_norm[col].sum()

# Add summary columns to dataframes.
df.loc[:, 'count'] = np.sum(df.loc[:, ['brain%d' % b for b in BRAINS]], axis=1)
df.loc[:, 'avg'] = np.mean(df.loc[:, ['brain%d' % b for b in BRAINS]], axis=1)
df.loc[:, 'std'] = np.std(df.loc[:, ['brain%d' % b for b in BRAINS]], axis=1)
df_norm.loc[:, 'avg'] = np.mean(df_norm.loc[:, ['brain%d' % b for b in BRAINS]], axis=1)
df_norm.loc[:, 'std'] = np.std(df_norm.loc[:, ['brain%d' % b for b in BRAINS]], axis=1)

# Output results.
if WRITE_RESULTS:
    df.to_csv(os.path.join(CSV_PATH, '_raw_counts__%s_%dum__%d%%.csv' % (ATLAS, RES, FILTER_THRESHOLD * 100)))
    df_norm.to_csv(os.path.join(CSV_PATH, '_norm_counts__%s_%dum__%d%%.csv' % (ATLAS, RES, FILTER_THRESHOLD * 100)))
