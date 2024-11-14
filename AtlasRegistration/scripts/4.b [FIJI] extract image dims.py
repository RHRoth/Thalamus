# Extract raw image dims for particular sample.
# muniak@ohsu.edu
# 2024.11.06 - output verified for manuscript.

# Custom script path (must contain rothetal_pkg folder).
PKG_PATH = r'<<FILEPATH_TO_SCRIPTS>>'

# Set location of data.
ROOT_DIR = r'<<FILEPATH_TO_DATA>>'

import os
import sys

sys.path.insert(0, PKG_PATH)
from rothetal_pkg.fiji.bioformats import get_czi_series_info

brain = 8
start = 100
stop = 118

mx = 0
my = 0

out = ''

for i in range(start, stop+1):
    fname = 'RRJD%d_%d_10x.ome.tiff' % (brain, i)
    si = get_czi_series_info(os.path.join(ROOT_DIR, r"Brain%d\10x" % brain, fname))
    x, y = si.dim[0][0]
    mx = max(mx, x)
    my = max(my, y)
    out += '%d\t%d\t%d\n' % (i, x, y)

out += '\n\t%d\t%d\n' % (mx, my)

print(out)