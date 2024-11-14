# fiji/t2/patch.py
# v.2022.02.09  # IN PROGRESS -- see mask fixes
# m@muniak.com
#
# Common patch functions for TrakEM2.

# 2024.11.07 - Cleaned up for manuscript deposit.
# 2022.02.09 -- Fix sort_by_mag() to set new keyword t2flag=True in call to get_embedded_cal()

import os
import re
import time
from ij import IJ
#from ij import ImagePlus
#from ij import WindowManager
from ij.gui import DialogListener
from ij.gui import GenericDialog
from ij.gui import PolygonRoi
from ij.gui import Roi
from ij.gui import ShapeRoi
from ij.plugin import RoiEnlarger
from ij.plugin.filter import Binary
from ij.plugin.filter import RankFilters
from ij.plugin.filter import ThresholdToSelection
from ij.process import AutoThresholder
from ij.process import Blitter
from ij.process import ByteProcessor
from ini.trakem2.display import Display
from ini.trakem2.display import Layer
from ini.trakem2.display import Patch
from java.awt import Button
from java.awt import Checkbox
from java.awt import GridBagConstraints
from java.awt import GridBagLayout
from java.awt import Insets
from java.awt import Label
from java.awt import Panel
from java.awt import Scrollbar
from java.awt.event import ActionEvent
from java.awt.event import AdjustmentListener
from java.awt.geom import AffineTransform
from mpicbg.trakem2.align import AlignTask
from mpicbg.trakem2.transform import ExportBestFlatImage

from ..calibration import get_embedded_cal
from ..roi import invert_roi
from ..roi import roi_bounds_area
from ..roi import transform_roi
from ..segmentation import request_mask_params_gui
from ..segmentation import mask_image
from ..segmentation import mask_center ## OLD DEPRECIATED TEMPORARY
from ..utils import logerror
from ..utils import logmsg
from .. import t2
import rothetal_pkg.fiji.t2.layer


# Attempt to load INRA modules -- not loaded in FIJI by default, must be selected in updater!
try:
    from inra.ijpb.binary import BinaryImages
    from inra.ijpb.binary import ChamferWeights
    from inra.ijpb.morphology import Strel
    from inra.ijpb.watershed import ExtendedMinimaWatershed
except ImportError as e:
    logerror(ImportError, 'INRA libraries must be loaded--select "IJPB-plugins" in update sites!', True)
    raise

default_th = 'Triangle'  # 'MinError(I)' 'Triangle'
default_median_filter = 2.0
default_morpho_radius = 5  # Totally empirically determined...
default_watershed_weight = 60  # Totally empirically determined...
default_rind = 5
default_interp_int = 10
default_smooth = True


def has_effective_alpha_mask(p):
    """ Test if a patch has an 'effective' alpha mask, meaning that even if an alpha
        mask is present, it must have at least one pixel with a value less than 255!
    """
    if not p.hasAlphaMask():
        return False
    return p.getAlphaMask().getStats().min < 255


def add_mask(roi, patches=[], futures=None, clear=False, reveal=False, inside=True, replace=False, global_coords=False, display=None, regex=None):
    """ Add mask to patches.  This method directly creates a new ByteProcessor and sets it as the current
        alpha mask, rather than using .addAlphaMask() which can be _very_ slow for complicated ROIs!
        
        PATCHES: If not specified, all visible patches in current layer will be used.
        FUTURES: List of MipMap tasks to finish.
        CLEAR: Just remove existing masks.
        REVEAL: If True, remove selected area from mask.
        INSIDE: If False, seleced area is inverse of ROI.
        REPLACE: Replace existing mask with new mask instead of additive.
        GLOBAL_COORDS: ROI is relative to PATCHES in project canvas, instead of original image(s).
        DISPLAY: Assign function to DISPLAY (not necessarily front display).
        REGEX: Optional filter for patch names.
        
        Returns FUTURES.
    """
    if not futures:
        futures = []
    if not display:
        display = t2.get_display()
    if not patches:
        patches = t2.get_patches(visible=True)
        if regex:
            patches = filter(lambda x: regex(x.getTitle()), patches)
    for p in patches:
        logmsg('Adding mask to patch %s in layer %s ...' % (p.getTitle(), p.getLayer().getTitle()))
        if clear or (replace and roi):
            p.setAlphaMask(None)
            if clear:
                futures.append(p.updateMipMaps())
                continue
        if not roi:
            continue
        if global_coords:
            r = transform_roi(roi, p.getAffineTransformCopy())
        else:
            r = roi
        w = p.getOWidth()
        h = p.getOHeight()
        ip = ByteProcessor(w, h)
        ip.setValue(255)
        ip.fill(r)
        if inside ^ reveal:
            ip.invert()
        mask = p.getAlphaMask()
        if mask:
            if reveal:
                ip.copyBits(mask, 0, 0, Blitter.OR)
            else:
                ip.copyBits(mask, 0, 0, Blitter.AND)
        p.setAlphaMask(ip)
        futures.append(p.updateMipMaps())
    display.repaint()
    display.repairGUI()
    display.update()
    return futures


def mask_patch(patch=None, params=None, bbox=None, stop_if_none=True, mask_warning=True):
    """ Use image segementation to mask a patch.
        
        PATCH: can be a single patch or a list of patches.
        BBOX: can be an Roi to restrict segmentation to only this region.
    """
    futures = []
    
    # Warn if no patches selected.
    if not patch and IJ.showMessageWithCancel('Alert', 'No patches selected, do you want to mask each visible patch in current layer?'):
        patch = t2.get_patches(visible=True)

    # Check if patch currently has an Alpha Mask.
    try:
        # patch is a list.
        mask_warning &= any([has_effective_alpha_mask(p) for p in patch])
    except TypeError:
        # patch is not a list.
        mask_warning &= has_effective_alpha_mask(patch)
    if mask_warning and not IJ.showMessageWithCancel('Alert', 'One or more patches already has a mask applied, if you continue they will be overwritten!'):
        return None

    # Get mask parameters via GUI.
    if not params:
        params = request_mask_params_gui(show_final_action=False, add_center=True, flatten=True)
        if not params:
            return None ## TODO THIS CURRENTLY PRODUCES AN ERROR (WORKS BUT NOT THE WAY I WANT)
            ## TODO NEED A WAY TO HAVE PERSISTENT PARAMS OR ALLOW FOR CHANGE
    
    # Loop through patches if a list.
    try:
        for p in patch:
            futures += mask_patch(patch=p, params=params, bbox=bbox, stop_if_none=stop_if_none, mask_warning=False)
            if futures[-1] is None:
                return futures[:-1]
            #try:
            #    futures += mask_patch(patch=p, params=params, bbox=bbox, stop_if_none=stop_if_none, mask_warning=False)
            #except TypeError:  # mask_patch() returns None to quit.
            #    return futures
        return futures
    except TypeError:  # Just a patch.
        pass

    logmsg('Calculating mask for patch %s in layer %s...' % (patch.getTitle(), patch.getLayer().getTitle()))
    
    # If bbox is provided, transform so it is patch-centric.
    bbox = transform_roi(bbox, patch.getAffineTransformCopy())
    
    # Get image and find mask.
    roi, used_params = mask_image(patch.getImageProcessor().convertToByte(False), 
                                  cal=patch.getImagePlus().getCalibration(), 
                                  nullzone=bbox, params=params)

    # If we are testing thresholds, an image already popped up.  Exit now.
    if params.threshold_method == '[Try all]':
        return futures
    
    # Use ROI to add mask, or quit.
    if roi:
        futures += add_mask(roi, patches=[patch], futures=futures, inside=False, replace=True)
        patch.setProperty('mask_params', used_params)
    else:
        logmsg('Failed to find a mask for %s ...' % patch.getTitle())
        if stop_if_none:
            logmsg('User cancelled.')
            return None
            #logerror(KeyboardInterrupt, 'Cancelling further operations ...')
    return futures


def mask_layer(patches=[], params=None, bbox=None, regex=None, stop_if_none=True):
    """ Use image segmentation to mask a layer.
        
        PATCHES: can preselect patches to consider.
        BBOX: can be an Roi to restrict segmentation to only this region.
        REGEX: Optional filter for patch names.
    """
    # Get patches.
    if not patches:
        patches = t2.get_patches(visible=True)
        if regex:
            patches = filter(lambda x: regex(x.getTitle()), patches)

    # Get mask parameters via GUI.
    if not params:
        params = request_mask_params_gui(show_final_action=False, add_center=True, flatten=True)
        if not params:
            return futures
    
    logmsg('Calculating mask for layer %s ...' % patches[0].getLayer().getTitle())

    # Get roi of actual area containing patches (exclude null space, existing masks).
    nullzone = None
    for patch in patches:
        if not nullzone:
            nullzone = ShapeRoi(patch.getArea())
        else:
            nullzone.or(ShapeRoi(patch.getArea()))
    if bbox:
        nullzone.and(ShapeRoi(bbox))
    
    ###return nullzone
    
    # Get image of layer and find mask.
    roi, used_params = mask_image(ExportBestFlatImage(patches, t2.get_layerset().get2DBounds(), 0, 1).makeFlatGrayImage(),
                                  cal=t2.get_layerset().getCalibrationCopy(), 
                                  nullzone=nullzone, params=params)
    
    # Use ROI to add mask to each patch, or quit.
    if roi:
        futures = add_mask(roi, patches, inside=False, replace=False, global_coords=True)
        for patch in patches:
            patch.setProperty('layer_mask_params', used_params)
    else:
        logmsg('Failed to find a layer mask for %s ...' % ', '.join([p.getTitle() for p in patches]))
        if stop_if_none:
            logmsg('User cancelled.')
            return None
            #logerror(KeyboardInterrupt, 'Cancelling further operations ...')
    return futures


def add_mask_OLD(roi, patches=[], val=0, replace=False, without_at=False, display=None, regex=None):
    """ Add mask to patches.
        If patches not specified, all patches in current layer will be used.
        
        REGEX: Optional filter for patch names.
    """
    if not display:
        display = Display.getFront()
    if not patches:
        patches = display.getLayer().getDisplayables(Patch)
        if regex:
            patches = filter(lambda x: regex(x.getTitle()), patches)
    for p in patches:
        at = p.getAffineTransformCopy()
        # Reset Patch position to default so that mask is aligned properly.
        if without_at and at.getType() != AffineTransform.TYPE_IDENTITY:
            at_flag = True
            p.setAffineTransform(AffineTransform())
        # If replacing, clear all existing masks first.
        if replace:
            p.setAlphaMask(None)
        logmsg('Adding mask to patch %s in layer %s ...' % (patches[0].getTitle(), patches[0].getLayer().getTitle()))  # Phrasing not correct if not all patches selected... TODO
        p.addAlphaMask(roi, val)
        p.setAffineTransform(at)
        try:
            p.updateMipMaps().get()
        except:
            logmsg('Dunno... see Patch.java...')
    display.repaint()
    display.repairGUI()
    display.update()
    logmsg('Mask applied to patches in layer: %s' % patches[0].getLayer().getTitle())  # Phrasing not correct if not all patches selected... TODO
    return


def mask_center_of_patch(patch=None, th=default_th, background='white', bbox=None, stop_if_none=False):
    ## TODO OLD SCRIPT!!
    # TODO: Get rid of default_th and background_color!
    """ Add mask to a patch by 'finding' the center object based on auto-thresholding.
    """
    futures = []
    if patch is None:
        if IJ.showMessageWithCancel('Alert', 'No patches selected, do you want to mask each patch in current layer?'):
            for patch in Display.getFront().getLayer().getDisplayables(Patch):
                ####
                futures += mask_center_of_patch(patch, th, background, bbox, stop_if_none)
        return futures
    logmsg('Calculating mask for patch %s in layer %s...' % (patch.getTitle(), patch.getLayer().getTitle()))
    # If bbox is provided, transform so it is patch-centric.
    bbox = transform_roi(bbox, patch.getAffineTransformCopy(), inverse=True)
    # Get image and find mask.
    roi = mask_center(patch.getImageProcessor().convertToByte(False), th, background, nullzone=bbox)
    #roi, used_params = mask_image(patch.getImageProcessor().convertToByte(False), 
    #                              cal=patch.getImagePlus().getCalibration(), nullzone=bbox, add_center=True)
    
    if roi:
        # Much faster to directly set AlphaMask using ByteProcessor when possible!
        w = patch.getOWidth()
        h = patch.getOHeight()
        ip = ByteProcessor(w, h)
        ip.setValue(255)
        ip.fill(roi)
        #ip.threshold(0)
        #ip.setValue(0)
        #ip.fill(roi)
        patch.setAlphaMask(ip)
        futures.append(patch.updateMipMaps())
        #patch.setProperty('mask_params', used_params)
    else:
        logmsg('Failed to find a centered ROI for %s ...' % patch.getTitle())
        if stop_if_none:
            logerror(KeyboardInterrupt, 'Cancelling further imports ...')
    return futures


def mask_center_of_layer(patches=[], th=default_th, background='white', display=None, regex=None, bbox=None):
    ## TODO OLD SCRIPT!!
    # TODO: Get rid of default_th and background_color!
    """ Add mask to each patch by 'finding' the center object based on auto-thresholding.
        
        REGEX: Optional filter for patch names.
    """
    if not display:
        display = t2.get_display()
    if not patches:
        patches = t2.get_patches()
        if regex:
            patches = filter(lambda x: regex(x.getTitle()), patches)
    layerset = t2.get_layerset()
    bounds = layerset.get2DBounds()
    logmsg('Calculating mask for layer %s ...' % patches[0].getLayer().getTitle())
    # Get roi of actual area containing patches (exclude null space).
    nullzone = None
    for patch in patches:
        if not nullzone:
            nullzone = ShapeRoi(patch.getArea())
        else:
            nullzone.or(ShapeRoi(patch.getArea()))
    if bbox:
        nullzone.and(ShapeRoi(bbox))
    # Get image of layer and find mask.
    roi = mask_center(ExportBestFlatImage(patches, bounds, 0, 1).makeFlatGrayImage(), th, background, nullzone)
    #roi, used_params = mask_image(ExportBestFlatImage(patches, bounds, 0, 1).makeFlatGrayImage(),
    #                              invert=True, nullzone=nullzone, threshold_method=th, 
    #                              background_color=background, add_center=True)
    if roi is None:
        logmsg('Failed to find a centered ROI for %s ...' % ', '.join([p.getTitle() for p in patches]))
    else:
        add_mask(roi, patches)
    return


def move_to_layer(patches, cur_layer, new_layer=None):
    """Move patch from cur_layer to new_layer.  Creates new_layer if necessary.
    """
    # # TODO -> ADD OPTION FOR NEW LAYER?
    project = t2.get_project()
    layerset = t2.get_layerset()

    if new_layer:
        dlg = GenericDialog('Confirm')
        dlg.addMessage('Confirm move?')
        dlg.setAlwaysOnTop(True)
        dlg.toFront()
        dlg.showDialog()
        if not dlg.wasOKed():
            return
    
    layerset.move(set(patches), cur_layer, new_layer)
    removed = False
    if cur_layer.isEmpty():
        dlg = GenericDialog('Empty Layer')
        dlg.addMessage('Layer %s is now empty, remove it from project?' % cur_layer.getTitle())
        dlg.enableYesNoCancel()
        dlg.hideCancelButton()
        dlg.showDialog()
        if dlg.wasOKed():
            Display.getFront().setLayer(new_layer)
            t2.layer.remove(project, cur_layer)
            removed = True
    sort_by_mag([new_layer])
    Display.getFront().repairGUI()
    return removed


def set_filters(patches, filter_=None):
    """ Apply filter(s) to set of patches, if not already applied.  Returns futures.
    """
    futures = []
    for patch in patches:
        if patch.getFilters() != filter_:
            patch.setFilters(filter_)
            patch.getProject().getLoader().decacheImagePlus(patch.getId())
            futures.append(patch.updateMipMaps())
    return futures


def sort_by_mag(layers):
    """ Re-sort all patches in each layer according to magnification, then name.
    """
    for layer in layers:
        patches = sorted(layer.getDisplayables(Patch), key=lambda item: item.getTitle(), reverse=True) # secondary sort by name
        patches = sorted(patches, key=lambda x: get_embedded_cal(x, t2flag=True), reverse=True) # primary sort by mag in place
        for patch in patches:
            layer.moveTop(patch)
    return


def split_by_line(display=None):
    """ Programmatic access to 'Split images' right-click action.
    """
    if not display:
        display = t2.get_display()
    patches = display.getSelected(Patch)
    if not patches:
        if IJ.showMessageWithCancel('Split by ROI',
                                    'Warning: No images selected, all images in layer will be split if you continue...'):
            patches = display.getLayer().getDisplayables(Patch)
        else:
            return None
    roi = display.getRoi()
    if roi is None:
        IJ.showMessage('No ROI to split with!')
        return
    if not roi.getType() in [Roi.LINE, Roi.POLYLINE, Roi.FREELINE]:
        IJ.showMessage('Incorrect ROI type to split with!')
        return
    linkflag = False
    for patch in patches:
        if patch.getLinked():
            linkflag = True
        patch.unlink()
    roi2 = PolygonRoi(roi.getFloatPolygon(), Roi.POLYLINE)
    IJ.getImage().setRoi(roi2)
    if linkflag:
        logmsg('Warning: Patches had to be unlinked before splitting!', True)
    ae = ActionEvent(display, ActionEvent.ACTION_FIRST, 'Split images under polyline ROI')
    display.actionPerformed(ae)
    return patches  # For later comparison.


def get_paths(patches=None, splitext=False):
    """ Get full path to each patch and provide as mapped dict.
        Enable SPLITEXT to strip extension from dict keys.
    """
    if patches is None:
        patches = t2.get_all_patches()
    res = {}
    for patch in patches:
        path = patch.getImageFilePath()
        key = os.path.basename(path)
        if splitext:
            key,_ = os.path.splitext(key)
        res[key] = path
    return res


### BEGIN TOGGLE FXNS ###

def are_all_locked(elems):
    """ Test if all/any patches are locked.
    """
    # Assumes all elements are of same class.
    if elems and elems[0].getClass() == Layer:
        patches = [patch for layer in elems for patch in layer.getDisplayables(Patch)]
    else:
        patches = elems
    locked = [patch.isLocked() for patch in patches]
    return all(locked), any(locked)


def are_all_visible(elems):
    """ Test if all/any patches are visible.
    """
    # Assumes all elements are of same class.
    if elems and elems[0].getClass() == Layer:
        patches = [patch for layer in elems for patch in layer.getDisplayables(Patch)]
    else:
        patches = elems
    visible = [patch.isVisible() for patch in patches]
    return all(visible), any(visible)


def toggle_lock(elems, lock=False, dohidden=True):
    """ Lock/unlock all patches in list/layers.
    """
    # Assumes all elements are of same class.
    if elems and elems[0].getClass() == Layer:
        patches = [patch for layer in elems for patch in layer.getDisplayables(Patch)]
    else:
        patches = elems
    for patch in patches:
        if dohidden or patch.isVisible():  # If dohidden == False, will only operate on visible patches.
            patch.setLocked(lock)


def toggle_visibility(elems, visible=True):
    """ Hide/unhide all patches in list/layers.
    """
    # Assumes all elements are of same class.
    if elems and elems[0].getClass() == Layer:
        for layer in elems:
            layer.setVisible('patch', visible, True)
    else:
        for patch in elems:
            patch.setVisible(visible, True)

### END TOGGLE FXNS ###

### BEGIN TRANSFORMATION FXNS ###

def transform(patches, at, vd=True, linked=False):
    """ Apply transform to patches.  Also affects overlapping vector data by default.
    
        Use subroutine from TrakEM2's AlignTask to apply transform to all
        patches and associated vector data.  No need to work out links.  If vd is False, 
        only apply transformations to patches as preTransforms, and possibly links.
    
        Note: Only vector data that directly overlaps with patches will be transformed!
    """
    if isinstance(patches, Patch):
        patches = [patches]
    if vd:
        AlignTask.transformPatchesAndVectorData(patches, at)
    else:
        for patch in patches:
            patch.preTransform(at, linked)


def scale(patches, sx, sy=None, xo=0.0, yo=0.0, vd=True, linked=False):
    """ Scale patches.  Also affects overlapping vector data by default.
    """
    if sy is None:
        sy = sx
    at = AffineTransform()
    at.translate(xo, yo)
    at.scale(sx, sy)
    at.translate(-xo, -yo)
    transform(patches, at, vd, linked)


def translate(patches, tx, ty, vd=True, linked=False):
    """ Translate patches.  Also affects overlapping vector data by default.
    """
    at = AffineTransform()
    at.translate(tx, ty)
    transform(patches, at, vd, linked)

### END TRANSFORMATION FXNS ###


def interactive_minmax(display=None, layers=None, desc='all layers'):
    """ Pop-up dialog to manually adjust min-max of selected patches.
        If no patches are selected, all patches in layer are used.
    """
    ex = re.compile('^(?!_bg.*$).*').match

    if display is None:
        display = Display.getFront()
    if layers is None:
        layers = display.getLayerSet().getLayers()
    layer = display.getLayer()
    patches = display.getSelected(Patch)
    if not patches:
        patches = filter(lambda x: ex(x.getTitle()), layer.getDisplayables(Patch))

    bd = 2**max([p.getImageProcessor().getBitDepth() for p in patches])
    omin = int(min([p.getMin() for p in patches]))
    omax = int(max([p.getMax() for p in patches]))
    
    class dl (DialogListener):
        def dialogItemChanged(self, gd, e):
            if not e: return
            if e.getSource() == bt_apply:
                vmin = sc_min.getValue()
                vmax = sc_max.getValue()
                for layer in layers:
                    for p in filter(lambda x: ex(x.getTitle()), layer.getDisplayables(Patch)):
                        logmsg('Updating minmax for %s (%d, %d)' % (p.getTitle(), vmin, vmax))
                        p.setMinAndMax(vmin, vmax)
                        p.updateMipMaps()
                        time.sleep(1)
                dlg.dispose()
    
    class adjl (AdjustmentListener):
        def adjustmentValueChanged(self, e):
            if not e: return
            vmin = sc_min.getValue()
            vmax = sc_max.getValue()
            es = e.getSource()
            if es == sc_min and vmin > vmax:
                sc_max.setValue(vmin)
                vmax = sc_max.getValue()
            elif es == sc_max and vmax < vmin:
                sc_min.setValue(vmax)
                vmin = sc_min.getValue()
            txt_min.setText('%0.0d' % vmin)
            txt_max.setText('%0.0d' % vmax)
            if cb_live.getState():
                for p in patches:
                    p.setMinAndMax(vmin, vmax)
                    p.updateMipMaps()

    dlg = GenericDialog('MinMax')
    gbc = GridBagConstraints()
    gbc.fill = GridBagConstraints.HORIZONTAL
    gbc.anchor = GridBagConstraints.PAGE_START
    gbc.insets = Insets(3, 3, 3, 3)
    panel = Panel(GridBagLayout())
    gbc.gridx = 0
    gbc.gridy = 0
    panel.add(Label('min:', Label.RIGHT), gbc)
    gbc.gridx = 1
    gbc.gridy = 0
    sc_min = Scrollbar(Scrollbar.HORIZONTAL, omin, 1, 0, bd)
    sc_min.addAdjustmentListener(adjl())
    panel.add(sc_min, gbc)
    gbc.gridx = 2
    gbc.gridy = 0
    txt_min = Label('%0.0d' % omin, Label.LEFT)
    panel.add(txt_min, gbc)
    gbc.gridx = 0
    gbc.gridy = 1
    panel.add(Label('max:', Label.RIGHT), gbc)
    gbc.gridx = 1
    gbc.gridy = 1
    sc_max = Scrollbar(Scrollbar.HORIZONTAL, omax, 1, 0, bd)
    sc_max.addAdjustmentListener(adjl())
    panel.add(sc_max, gbc)
    gbc.gridx = 2
    gbc.gridy = 1
    txt_max = Label('%0.0d' % omax, Label.LEFT)
    panel.add(txt_max, gbc)
    gbc.gridx = 0
    gbc.gridy = 2
    gbc.gridwidth = 3
    cb_live = Checkbox('Live', True)
    panel.add(cb_live, gbc)
    gbc.gridx = 0
    gbc.gridy = 3
    gbc.gridwidth = 2
    bt_apply = Button('Apply to %s' % desc)
    bt_apply.addActionListener(dlg)
    panel.add(bt_apply, gbc)
    dlg.addDialogListener(dl())
    dlg.addPanel(panel)
    dlg.showDialog()
    if not dlg.wasOKed():
        for p in patches:
            p.setMinAndMax(omin, omax)
            p.updateMipMaps()
    return