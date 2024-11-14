# Quick script to add normalized intensity column to cell count CSVs.
# muniak@ohsu.edu
# 2024.11.06 - output verified for manuscript.

# CSV path.
CSV_PATH = r'<<FILEPATH_TO_CSV_FOLDER>>'

import os
import pandas as pd

brains = [6]  # <- Brain ID(s) (as a list).
col = 'intensity'

for b in brains:
    df = pd.read_csv(os.path.join(CSV_PATH, 'brain%d_cellcoords.csv' % b))
    colnorm = col + '_norm'
    df.loc[:, colnorm] = df.loc[:, col].astype(float)
    df.loc[:, colnorm] -= df.loc[:, colnorm].min()
    df.loc[:, colnorm] /= df.loc[:, colnorm].max()
    df.to_csv(os.path.join(CSV_PATH, 'brain%d_cellcoords.csv' % b), index=False)