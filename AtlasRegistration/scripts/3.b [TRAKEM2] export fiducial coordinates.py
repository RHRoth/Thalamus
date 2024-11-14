# Export fiducial coordinates.
# muniak@ohsu.edu
# 2024.11.06 - output verified for manuscript.
# 2024.02.14 - original

""" Extract alignment coordinates (fiducials, rectangles) from TrakEM2 annotations
    and format for use in napari scripts.
    
    Fiducials are tuples of (AP, DV, LM).
    
    Rectangles are tuples of (AP, D, V, M, L)
"""

# Custom script path (must contain rothetal_pkg folder).
PKG_PATH = r'<<FILEPATH_TO_SCRIPTS>>'

# Set location of data.
ROOT_DIR = r'<<FILEPATH_TO_DATA>>'

import os
import sys

sys.path.insert(0, PKG_PATH)
from rothetal_pkg.fiji import t2
from rothetal_pkg.fiji.t2.objs import find_in_project

# CSV path.
CSV_PATH = os.path.join(ROOT_DIR, r'CSVs')

cal = t2.get_calibration()
rect = find_in_project('rect', obj_type='area_list', select=False)
fids = find_in_project('fiducials', obj_type='ball', select=False)

csv_base = t2.get_project().getTitle().replace('RRJD', 'brain').replace('.xml', '')

fid_names = ['cca', 'act', 'dg', 'ccp', 'sco', 'lgn_l', 'lgn_r', 'str_l', 'str_r']

### FIDUCIAL POINTS
f_points = [[ round(b[2] / cal.pixelDepth) - 1,  # !! My TrakEM2 projects start with index 1, not zero...
              round(cal.getRawX(b[1])), 
              round(cal.getRawX(b[0])), ]
            for b in fids.getWorldBalls()]
f_out = 'id,ap,dv,lm\n'
for name, (ap, dv, lm) in zip(fid_names, f_points):
    f_out += '%s,%d,%d,%d\n' % (name, ap, dv, lm)
f_path = os.path.join(CSV_PATH, csv_base + '_fiducials.csv')
f_file = open(f_path, 'w')
f_file.write(f_out)
f_file.close()
print('Saved fiducials to %s!' % f_path)

### RECTANGLE POINTS
r_points = [vert
             for layer in rect.getLayerRange()
             for z, bounds in [[round(cal.getX(layer.getZ()) / cal.pixelDepth) - 1, rect.getBounds(None, layer)]]
                 if (bounds.width + bounds.height) > 0
             for vert in [ (z, bounds.y, bounds.y + bounds.height, bounds.x, bounds.x + bounds.width) ] ]

r_out = 'ap,d,v,m,l\n'
for (ap, d, v, m, l) in r_points:
    r_out += '%d,%d,%d,%d,%d\n' % (ap, d, v, m, l)
r_path = os.path.join(CSV_PATH, csv_base + '_rectangles.csv')
r_file = open(r_path, 'w')
r_file.write(r_out)
r_file.close()
print('Saved rectangles to %s!' % r_path)