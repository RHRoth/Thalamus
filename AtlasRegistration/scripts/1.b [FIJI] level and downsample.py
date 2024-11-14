# Get stats from each channel of confocal images
# muniak@ohsu.edu
# 2023.?? - Original.
# 2024.11.06 - Cleaned up, output verified.

# Custom script path (must contain rothetal_pkg folder).
PKG_PATH = r'<<FILEPATH_TO_SCRIPTS>>'

# Set location of data.
ROOT_DIR = r'<<FILEPATH_TO_DATA>>'

import os
import re
import csv
import math
import sys
from ij import IJ
from ij.process import LUT
from java.awt import Color
from ij.process import StackConverter

sys.path.insert(0, PKG_PATH)
from rothetal_pkg.fiji.multithread import multi_task
from rothetal_pkg.fiji.utils import make_directory
from rothetal_pkg.fiji.utils import process_str

# Stats CSV.
CSV_PATH = os.path.join(ROOT_DIR, r'__stats.csv')

# Folders with confocal images, lowres C2 setting, and lowres scaling.
source_folders = [
(r'Brain2\10x',   9000, 0.125, 'x8'),
(r'Brain3\10x',  16383, 0.125, 'x8'),
(r'Brain4\10x',  26000, 0.125, 'x8'),
(r'Brain6\10x',  16383, 0.25,  'x4'),
(r'Brain7\10x',  16383, 0.25,  'x4'),
(r'Brain8\10x',   5000, 0.25,  'x4'),
(r'Brain9\10x',  20000, 0.25,  'x4'),
(r'Brain10\10x',  8000, 0.25,  'x4'),
(r'Brain11\10x', 14000, 0.25,  'x4'),
]

# Settings
nch = 2
hist_cat = 'hist_.05'  # Histogram saturation value for level balancing (ala ImageJ's 'Process > Enhance Contrast...')
max_val = 65535
lut_colors = ('red', 'cyan')
max_val_ch1 = 16383  # does not change per brain

# Set up stats lookup table.
c = csv.reader(open(CSV_PATH, 'r'), delimiter=',', )
header = c.next()
stats = dict()
for row in c:
    stats[row[0]] = {k:process_str(v) for k,v in zip(header[1:], row[1:])}
uids = set([stats[k]['id'] for k in stats])
levels = {id:{} for id in uids}
for id in uids:
    for ch in range(nch):
        levels[id][ch] = {'adj_min':float('inf'),
                          'adj_max':float('-inf'),
                          'sf':1.0,
                          }
for k in stats:
    id = stats[k]['id']
    for ch in range(nch):
        levels[id][ch]['adj_min'] = min(levels[id][ch]['adj_min'], 1. - (stats[k]['C%d_mean' % (ch+1)] / stats[k]['C%d_roi_mean' % (ch+1)]))
        levels[id][ch]['adj_max'] = max(levels[id][ch]['adj_max'], (stats[k]['C%d_%s_hi' % (ch+1, hist_cat)] - stats[k]['C%d_mean' % (ch+1)]) / stats[k]['C%d_roi_mean' % (ch+1)])
for id in uids:
    for ch in range(nch):
        levels[id][ch]['sf'] = max_val / (levels[id][ch]['adj_max'] - levels[id][ch]['adj_min'])

# Level balance function.
def level_and_scale_image(source_folder=None, f=None, max_val_ch2=None, scale_factor=None, scale_factor_txt=None):
    if not f: return
    
    # Used to adjust LUT of low-mag RGB output.
    max_vals = (max_val_ch1, max_val_ch2)
    
    id = stats[f]['id']
    
    # Open image.
    source_path = os.path.join(source_folder, f)
    imp = IJ.openImage(source_path)
    cal = imp.getCalibration()
    stack = imp.getStack()
    nc = imp.getNChannels()
    
    # Adjust range.
    for c in range(nc):
        sidx = imp.getStackIndex(c+1, 1, 1)
        fp = stack.getProcessor(sidx).convertToFloat()
        fp.multiply(1. / stats[f]['C%d_roi_mean' % (c+1)])
        fp.subtract(stats[f]['C%d_mean' % (c+1)] / stats[f]['C%d_roi_mean' % (c+1)])
        fp.subtract(levels[id][c]['adj_min'])
        fp.multiply(levels[id][c]['sf'])
        if max_val == 65535:
            stack.setProcessor(fp.convertToShort(False), sidx)
        elif max_val == 255:
            stack.setProcessor(fp.convertToByte(False), sidx)
        else:
            raise
        
        stack.getProcessor(sidx).setMinAndMax(0, max_val)  # Not sure this is needed but playing it safe.
    
    """ This next line is SUPER DUMB, but if I don't do this, it seems like some memory error causes the operations
        in the following loop to revert Channel #0 (but not #1??!?) to its original status before the math operations
        above... SUPER WEIRD, need to post on the ImageJ forum about it...
    """
    imp = imp.duplicate()  # <-- THIS IS SUPER DUMB
    stack = imp.getStack()
    for c in range(stack.getSize()):
        imp.setC(c+1)
        stack.getProcessor(c+1).setMinAndMax(0, max_val)  # Not sure this is needed but playing it safe.
        imp.setDisplayRange(0, max_val)
    imp.setDisplayMode(IJ.COMPOSITE)
        
    imp.setLuts([LUT.createLutFromColor(getattr(Color, lc)) for lc in lut_colors])
    imp.setDisplayMode(IJ.COMPOSITE)
    out_folder = source_folder + '__relevel'
    make_directory(out_folder)
    IJ.save(imp, os.path.join(out_folder, f.replace('RRJD-', 'RRJD').replace('.ome', '').replace('.tiff', '.tif').replace('.tif', '__relevel.tif')))
    
    # Resize.
    sw = int(imp.getWidth() * scale_factor)
    sh = int(imp.getHeight() * scale_factor)
    imp = imp.resize(sw, sh, 'bilinear')
    cal.pixelWidth /= scale_factor
    cal.pixelHeight /= scale_factor
    imp.setCalibration(cal)
    
    stack = imp.getStack()
    for c in range(stack.getSize()):
        imp.setC(c+1)
        stack.getProcessor(c+1).setMinAndMax(0, max_vals[c])  # Not sure this is needed but playing it safe.
        imp.setDisplayRange(0, max_vals[c])
    imp.setDisplayMode(IJ.COMPOSITE)
    StackConverter(imp).convertToRGB()
    # Save image.
    out_folder = source_folder.replace('__relevel', '') + '__RGB__%s' % scale_factor_txt
    make_directory(out_folder)
    IJ.save(imp, os.path.join(out_folder, f.replace('RRJD-', 'RRJD').replace('.ome', '').replace('.tiff', '.tif').replace('.tif', '__RGB__%s.tif' % scale_factor_txt)))

# Multithread.
re_tif = re.compile('[^.](.+)?\.tiff?', re.I).match
for source_folder, max_val_ch2, scale_factor, scale_factor_txt in source_folders:
    file_pairs = [(os.path.join(ROOT_DIR, source_folder), f, max_val_ch2, scale_factor, scale_factor_txt) for f in filter(re_tif, os.listdir(os.path.join(ROOT_DIR, source_folder)))]
    multi_task(level_and_scale_image, file_pairs)