# Get stats from each channel of confocal images
# muniak@ohsu.edu
# 2023.03.20 - Original.
# 2024.11.06 - Cleaned up, output verified.

# Custom script path (must contain rothetal_pkg folder).
PKG_PATH = r'<<FILEPATH_TO_SCRIPTS>>'

# Set location of data.
ROOT_DIR = r'<<FILEPATH_TO_DATA>>'

import os
import re
import sys
from ij import IJ

sys.path.insert(0, PKG_PATH)
from rothetal_pkg.fiji.multithread import multi_task
from rothetal_pkg.fiji.utils import logmsg

# Output CSV.
CSV_PATH = os.path.join(ROOT_DIR, r'__stats.csv')

# Folders with confocal images.
source_folders = [
(r'Brain2\10x',  'RRJD2_F'),
(r'Brain3\10x',  'RRJD3_F'),
(r'Brain4\10x',  'RRJD4_F'),
(r'Brain6\10x',  'RRJD6_F'),
(r'Brain7\10x',  'RRJD7_F'),
(r'Brain8\10x',  'RRJD8_F'),
(r'Brain9\10x',  'RRJD9_F'),
(r'Brain10\10x', 'RRJD10_F'),
(r'Brain11\10x', 'RRJD11_F'),
]

# Saturation values for querying histogram (ala ImageJ's 'Process > Enhance Contrast...')
saturated1 = .05  # %
saturated2 = .005  # %

# Upper-left corner ROI for sampling slide background levels.
roi_dims = (0, 0, 500, 500)  # px

# Main routine.
def get_minmax_stats(f=None, rrjd_id=''):
    if not f: return
    # Open image.
    source_path = os.path.join(source_folder, f)
    imp = IJ.openImage(source_path)
    stack = imp.getStack()
    w = imp.getWidth()
    h = imp.getHeight()
    cal = imp.getCalibration()
    pw = cal.pixelWidth
    mv = stack.getProcessor(1).maxValue()
    row = ['\"%s\"' % imp.getTitle(), rrjd_id, '%d' % w, '%d' % h, '%0.6f' % pw, '%d' % mv]
    nc = imp.getNChannels()
    for c in range(nc):
        sidx = imp.getStackIndex(c+1, 1, 1)
        ip = stack.getProcessor(sidx)
        
        ip.setRoi(*roi_dims)
        stats_corner = ip.getStats()
        
        ip.setRoi(None)
        stats = ip.getStats()
        
        if stats.histogram16 is not None:
            histogram = stats.histogram16
        else:
            histogram = stats.histogram()
        hsize = len(histogram)

        # THRESHOLD 1        
        threshold1 = int(stats.pixelCount * max([0.0, saturated1]) / 200.0)
        
        count = 0
        for hmin1 in range(hsize):
            count += histogram[hmin1]
            if count > threshold1:
                break
        
        count = 0
        for hmax1 in range(hsize)[::-1]:
            count += histogram[hmax1]
            if count > threshold1:
                break

        # THRESHOLD 2
        threshold2 = int(stats.pixelCount * max([0.0, saturated2]) / 200.0)
        
        count = 0
        for hmin2 in range(hsize):
            count += histogram[hmin2]
            if count > threshold2:
                break
        
        count = 0
        for hmax2 in range(hsize)[::-1]:
            count += histogram[hmax2]
            if count > threshold2:
                break        
        
        # Whole image stats.
        row += ['%0.2f' % stats.mean, '%0.2f' % stats.min, '%0.2f' % stats.max]
        # Upper-left corner ROI background stats.
        row += ['%0.2f' % stats_corner.mean, '%0.2f' % stats_corner.min, '%0.2f' % stats_corner.max]
        # Histogram bin % stats.
        row += ['%d' % hmin1, '%d' % hmax1, '%d' % hmin2, '%d' % hmax2]

    imp.close()
    return row

# Loop through image folders and multithreading image analysis.
re_tif = re.compile('[^.](.+)?\.tiff?', re.I).match
rows = []
for source_folder, rrjd_id in source_folders:
    files = [(os.path.join(ROOT_DIR, source_folder, f), rrjd_id) for f in filter(re_tif, os.listdir(os.path.join(ROOT_DIR, source_folder)))]
    rows += multi_task(get_minmax_stats, files)

# Silly way to recapitulate column names.
nc = (max([len(row) for row in rows]) - 6) // 10
label_row = ['fname', 'id', 'width_px', 'height_px', 'cal', 'max_val']
label_tmp = ['mean', 'min', 'max', 'roi_mean', 'roi_min', 'roi_max']
label_tmp += ['hist_%s_%s' % (str(saturated1).replace('0.','.'), x) for x in ['lo', 'hi']]
label_tmp += ['hist_%s_%s' % (str(saturated2).replace('0.','.'), x) for x in ['lo', 'hi']]
for c in range(nc):
    for m in label_tmp:
        label_row += ['C%d_%s' % (c+1, m)]

# Build output and write. No pandas in FIJI :(
out = ','.join(label_row) + '\n'
for row in rows:
    out += ','.join(row) + '\n'
f = open(CSV_PATH, 'w')
f.write(out)
f.close()
logmsg('Done grabbing stats.')

