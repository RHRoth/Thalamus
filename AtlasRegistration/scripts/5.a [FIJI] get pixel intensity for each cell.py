# Get pixel intensity for each counted cell.
# muniak@ohsu.edu
# 2024.11.06 - output verified for manuscript.

# 2024.10.08
# Queries mean/max pixel intensity in circle around each plotted cell.

""" Before running this script must first load Cell Counter project for
    Brain X (i.e., counting subset TIF stack and associated XML).  Then
    within Cell Counter window click 'Measure...' to open a ResultsTable.
"""

# CSV path.
CSV_PATH = r'<<FILEPATH_TO_CSV_FOLDER>>'

# Brain ID.
BRAIN_NUM = 6  # <-- for loading correct _cellcoords.csv to insert intensity values.

import os
from copy import copy
from ij import IJ
from ij.gui import OvalRoi
from ij.measure import ResultsTable

PX_OFF = 0.5  # Offset to make sure we're measuring center of pixel.
# In microns.
DIAMETERS = [25]  # ROI diameters to test.
TH_PCT = 0.2  # % of most-intense pixels within ROI to measure.

imp = IJ.getImage()
stack = imp.getStack()
cal = imp.getCalibration()

def get_vals(i, s, x, y, d, p=TH_PCT):
    col_mean = 'D%d_mean' % d
    col_med = 'D%d_median' % d
    col_max = 'D%d_max' % d
    col_perc = 'D%d-P%0.2f_mean' % (d, p)
    ip = stack.getProcessor(int(s))
    d_px = cal.getRawX(d)
    r_px = d_px / 2.0
    roi = OvalRoi(x - r_px + PX_OFF, y - r_px + PX_OFF, d_px, d_px)
    ip.setRoi(roi)
    stats = ip.getStatistics()
    rt.setValue(col_mean, i, stats.mean)
    rt.setValue(col_med, i, stats.median)
    rt.setValue(col_max, i, stats.max)
    
    hist = ip.getHistogram()
    thresh = sum(hist) * p
    cum_cnt = 0
    cum_val = 0
    # March backwards through histogram, adding up values
    # until count threshold is reached.
    for idx, val in enumerate(hist[::-1]):
        if val > 0:
            cum_cnt += val
            cum_val += (val * (ip.maxValue() - idx))
            if cum_cnt > thresh:
                break
    rt.setValue(col_perc, i, cum_val / cum_cnt)
    return

rt = ResultsTable.getActiveTable().clone()

# This could be multi-threaded by slice, but not worth effort.
for i, (s, x, y) in enumerate(zip( rt.getColumn('Slice'), 
                                   rt.getColumn('X'),
                                   rt.getColumn('Y'), )):
    IJ.showProgress(i, rt.getCounter())
    for d in DIAMETERS:
        get_vals(i, s, x, y, d)

# Note hard-coded to final value used.
intensities = rt.getColumn('D%d-P%0.2f_mean' % (25, .2))
rt_out = ResultsTable.open(os.path.join(CSV_PATH, 'brain%d_cellcoords.csv' % BRAIN_NUM))
rt_out.setPrecision(6)
rt_out.setValues('intensity', intensities)
rt_out.setDecimalPlaces(rt_out.getColumnIndex('intensity'), 3)
rt_out.save(os.path.join(CSV_PATH, 'brain%d_cellcoords.csv' % BRAIN_NUM))
rt_out.show('brain%d results' % BRAIN_NUM)