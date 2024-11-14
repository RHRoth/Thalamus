# Transform cell counts to brain coordinate space - Brains 2-7.
# muniak@ohsu.edu
# 2024.11.06 - output verified for manuscript.

# Custom script path (must contain rothetal_pkg folder).
PKG_PATH = r'<<FILEPATH_TO_SCRIPTS>>'

# Set location of data.
ROOT_DIR = r'<<FILEPATH_TO_DATA>>'

# 2024.02.28
""" FOR BRAINS 2-7 ONLY!! --> Cell counts were performed on pre-aligned images.
    Reconstructed script (original calc'd  via Excel, lol) to adjust Cell Count coordinates
    to "real-world" TrakEM2 project coordinate space.  Simply take the coordinates from
    the Cell Count ResultsTable in FIJI, adjust for relative downsampling, and add in the 
    offset of the ROI used to extract the cell count stack.  Easy peasy.
    
    This is basically a retrofit/simplified edit of the script for Brains 8-11...
    
    *** NOTE REQUIRES COPYING IN BRAIN-SPECIFIC VALUES FROM TABLES BELOW... ***
"""
### Copy over slice,x,y cols from Cell Counter ResultsTable ("Measure...") as one long array (z1, x1, y1, z2, x2, y2, etc..)
xlsvals = [z1, x1, y1, z2, x2, y2, ...]

### Copy over offset vals from "roi_bounds_for_cell_count_stacks.xlsx"
zoff = 0
xoff = 0
yoff = 0


import os
import sys

sys.path.insert(0, PKG_PATH)
from rothetal_pkg.fiji import t2

# CSV path.
CSV_PATH = os.path.join(ROOT_DIR, r'CSVs')

csv_base = t2.get_project().getTitle().replace('RRJD', 'brain').replace('.xml', '')

SECTION_THICKNESS = 40
""" This is ratio between TrakEM2 project and Cell Count stack, which will always be 4.
    This is because Cell Count stacks for higher-res Brains 2-4 were at x2, the rest at x1,
    and accordingly TrakEM2 projects were at x8 and x4.
"""
DOWNSAMPLING = 4.

print t2.get_project()  # Double check correct project is open.
cal = t2.get_calibration()

zs = [z + zoff for z in xlsvals[0::3]]  # leave zs as cell count numbers until later
xs = [x/DOWNSAMPLING + xoff for x, z in zip(xlsvals[1::3], zs)]  # factor in downsampling of t2 project
ys = [y/DOWNSAMPLING + yoff for y, z in zip(xlsvals[2::3], zs)]  # factor in downsampling of t2 project

zdict = {z:[] for z in set(zs)}
for z, x, y in zip(zs, xs, ys):
    zdict[z] += [x, y]

c_out = 'AP,DV,LM\n'

for z in sorted(zdict.keys()):
    for x, y in zip(zdict[z][0::2], zdict[z][1::2]):
        c_out += '\n'.join(['%d,%0.6f,%0.6f' % ((z-1)*SECTION_THICKNESS, cal.getX(y), cal.getX(x))])  # NOTE FLIPPED X/Y, AND 1- to 0- Z-index!!
        c_out += '\n'

c_path = os.path.join(CSV_PATH, csv_base + '_cellcoords.csv')
c_file = open(c_path, 'w')
c_file.write(c_out)
c_file.close()
print('cell coords saved to %s' % c_path)