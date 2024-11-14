# Helper for arealist annotations in TrakEM2 project.
# muniak@ohsu.edu
# 2024.11.06 - output verified for manuscript.

# 2024.02.14

""" Quick TrakEM2 helper for modifying ROI annotations.
    Creates ROI that is same size as existing Arealist in that section.
    Also deletes existing Arealist (unless commented out).
"""

# Custom script path (must contain rothetal_pkg folder).
PKG_PATH = r'<<FILEPATH_TO_SCRIPTS>>'

import sys
from ij import IJ
from ij.gui import Roi
from ij.gui import ShapeRoi

sys.path.insert(0, PKG_PATH)
from rothetal_pkg.fiji import t2
from rothetal_pkg.fiji.t2.objs import find_in_project

layerset = t2.get_layerset()
canvas_roi = ShapeRoi(Roi(0, 0, layerset.getLayerWidth(), layerset.getLayerHeight()))

a = find_in_project('rect', obj_type='arealist', select=False)
layer = t2.get_layer()

roi = Roi(a.getBounds(None, layer))
a.subtract(layer.getId(), canvas_roi)
IJ.getImage().setRoi(roi)
