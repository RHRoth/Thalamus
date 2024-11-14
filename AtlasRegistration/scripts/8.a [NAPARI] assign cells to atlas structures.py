# Get cell coordinates (transformed to atlas space) and query atlas annotations.
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
from rothetal_pkg.napari.thal import get_brain_coords

# CSV path.
CSV_PATH = os.path.join(ROOT_DIR, 'CSVs')

# Options.
BRAINS = [2, 3, 4, 6, 7, 8, 9, 10, 11]
DO_MERGE = True
WRITE_RESULTS = True
RES = 10
ATLAS = 'aba'  # 'aba' or 'kim'

# Mapping of subregion annotation IDs to merge with higher
# level structures in ontology hierarchy (for simplicity).
MERGE_MAP = {
    'aba': {
        1096:  127, #   AMd -> AM
        1104:  127, #   AMv -> AM
         414:  406, #  SPFm -> SPF
         422:  406, #  SPFp -> SPF
         725:  718, # VPLpc -> VPL
         741:  733, # VPMpc -> VPM
         804:  797, #    FF -> ZI
    },
    'kim': {
        2075:  946, #   PHD -> PH
        2364:  946, #  PHnd -> PH 
        2046: 2282, #  LDDM -> LD
         155: 2282, #  LDVL -> LD
         617:  362, #   MDC -> MD
         626:  362, #   MDL -> MD
         636:  362, #   MDM -> MD
        2089:  149, #    PV -> PVT
        2090:  149, #   PVP -> PVT
        2073:  178, # PrGPC -> PrG
        2105:  194, #   Gem -> LH
        2110:  797, #     F -> ZI
        2125:  797, #   ZIC -> ZI
        2053:  797, #   ZID -> ZI
        2043:  797, #   ZIR -> ZI
        2054:  797, #   ZIV -> ZI
        2059:  186, #  LHbL -> LHb
        2058:  186, #  LHbM -> LHb
        2064:  907, #   OPC -> PC
        2377:  366, #  SubD -> Sub
        2378:  366, #  SubV -> Sub
        2039: 2038, #  PaXi -> Xi
        2362:  733, #  VPMd -> VPM
        2363:  733, #  VPMv -> VPM
        2099:  215, #  APTD -> APT
        2114: 2414, # p1PAG -> PAG
         422:  406, # SPFPC -> SPF
        2093: 2092, #   RRe -> Re
        2037: 2092, #   VRe -> Re
           0:  997, #  NULL -> root
    },
}

aba = get_aba(RES, ATLAS)
aba_name = aba.atlas_name

for b in BRAINS:
    df = pd.read_csv(os.path.join(CSV_PATH, 'brain%d_cellcoords.csv' % b))
    cc = get_brain_coords(b, CSV_PATH, RES, ATLAS)  # No filter.
    # Edit of 'query_brain_coords()' here, without counting.
    cc = np.round(cc / aba.resolution[0]).astype(int)
    vals = aba.annotation[cc[:, 0], cc[:, 1], cc[:, 2]]
    if DO_MERGE:
        for k, v in MERGE_MAP[ATLAS].items():
            vals[vals == k] = v
    df.loc[:, 'id_%s_%dum' % (ATLAS, RES)] = vals
    if WRITE_RESULTS:
        df.to_csv(os.path.join(CSV_PATH, 'brain%d_cellcoords.csv' % b), index=False)
    print('Mapped Brain%d to %s_%dum%s.' % (b, ATLAS, RES, ', using merges' * DO_MERGE))
