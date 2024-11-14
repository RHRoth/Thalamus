# Script to fix base calibration of TrakEM2 environment to be equal to images.
# muniak@ohsu.edu
# 2024.11.06 - froze BASECAL_TABLE, output verified for manuscript.

# Custom script path (must contain rothetal_pkg folder).
PKG_PATH = r'<<FILEPATH_TO_SCRIPTS>>'

# scripts/trakem2/change_base_calibration.py
# v.2020.09.26
# m@muniak.com
#
# Change base calibration of TrakEM2 project based on either calibration of loaded images or presets.

# Imports
import sys
from ij.gui import GenericDialog
from ini.trakem2.display import Display
from ini.trakem2.display import Patch
from java.awt.geom import AffineTransform

sys.path.insert(0, PKG_PATH)
BASECAL_TABLE = {'Unknown': 1.0}
from rothetal_pkg.fiji.calibration import convert_units
from rothetal_pkg.fiji.utils import logmsg
from rothetal_pkg.fiji.t2.canvas import reset

def change_base_calibration():
    # Do we have an open project?
    display = Display.getFront()
    if not display:
        logmsg('No TrakEM2 project detected!', True)
        return
    layerset = display.getLayerSet()
    patches = layerset.getDisplayables(Patch)

    # Get calibrations for all patches... might take awhile!
    cals = [patch.getImagePlus().getCalibration() for patch in patches]

    # Get unique calibration values and sort with lowest mag first.
    unique_cals = sorted(set([(cal.pixelWidth, cal.getUnit()) for cal in cals]), key=lambda x: x[0], reverse=True)
    unique_patches = [None] * len(unique_cals)

    # Find first instance of a patch that matches each unique calibration/mag.
    for i,ucal in enumerate(unique_cals):
        idx = [cal.pixelWidth for cal in cals].index(ucal[0])
        unique_patches[i] = patches[idx]

    # Sanity check: convert all calibration values to microns if they aren't already.
    for i,ucal in enumerate(unique_cals):
        unique_cals[i] = convert_units(ucal[0], ucal[1], 'micron')

    # Create list for dialog.
    cal_list = ['%0.4f um/px  [ %s ]' % (ucal[0], upatch.getTitle()) for ucal, upatch in zip(unique_cals, unique_patches)]
    cal_list += sorted(BASECAL_TABLE.keys())

    # Present user with dialog to select new calibration.
    dlg = GenericDialog('Change base calibration')
    dlg.addChoice('New base calibration:', cal_list, cal_list[0])
    dlg.showDialog()
    if not dlg.wasOKed():
        return

    # Get selected calibration value.
    idx = dlg.getNextChoiceIndex()
    if idx < len(unique_cals):
        new_pw = unique_cals[idx][0]
    else:
        new_pw = BASECAL_TABLE[cal_list[idx]]

    # Get project calibration.
    cal = layerset.getCalibrationCopy()
    # Determine scale factor to new calibration.
    sf = cal.pixelWidth / new_pw
    cal.pixelWidth = new_pw
    cal.pixelHeight = new_pw
    at = AffineTransform()
    at.scale(sf, sf)
    # Scale all objects in project to new calibration.
    for d in set(layerset.getDisplayables() + layerset.getZDisplayables()):
        d.preTransform(at, False)
    # Scale all layer thicknesses to new calibration.
    for layer in layerset.getLayers():
        layer.setZ(layer.getZ() * sf)
        layer.setThickness(layer.getThickness() * sf)
    # Apply new calibration!
    layerset.setCalibration(cal)
    logmsg('Project elements scaled by %0.2f to match new calibration ...' % sf)
    # Reset canvas... TODO: Is there a way to set resize=True but keep same RELATIVE bounding box...?
    reset(layerset, zoomout=True, resize=True)

change_base_calibration()