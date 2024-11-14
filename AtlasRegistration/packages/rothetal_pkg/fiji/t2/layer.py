# fiji/t2/layer.py
# v.2020.09.26
# m@muniak.com
#
# Common layer functions for TrakEM2.

# 2024.11.07 - Cleaned up for manuscript deposit.

from ij.gui import DialogListener
from ij.gui import NonBlockingGenericDialog
from ij.gui import Roi
from ij.plugin.filter import ThresholdToSelection
from ini.trakem2.display import AffineTransformMode
from ini.trakem2.display import Display
from ini.trakem2.display import Patch
from ini.trakem2.display import VectorDataTransform
from ini.trakem2.utils import M
from java.awt import Button
from java.awt import Checkbox
from java.awt import Color
from java.awt import GridBagConstraints
from java.awt import GridBagLayout
from java.awt import Insets
from java.awt import Label
from java.awt import Panel
from java.awt.geom import AffineTransform
from java.lang import Math
from mpicbg.models import AffineModel2D
from mpicbg.trakem2.transform import ExportBestFlatImage

from ..calibration import get_embedded_cal
from ..utils import centroid
from ..utils import logmsg
from .. import t2
import ..t2.canvas
import ..t2.displayable


def get_nonzero_bounds(layer):
    """ Find bounds for non-zero content in layer.
    """
    layerset = layer.getParent()
    bounds = layerset.get2DBounds()
    patches = layer.getDisplayables(Patch)
    if not patches:
        return None
    ip = ExportBestFlatImage(patches, bounds, 0, 1).makeFlatGrayImage()
    ip.setThreshold(1, 255, False)  # Everything non-zero.
    roi = ThresholdToSelection().convert(ip)
    bounds = roi.getBounds()
    return bounds

 
def transform(layer, at, linked=False):
    """ Apply transform to all elements, but only in single layer.
    
        Special consideration required for ZDisplayables as a simple transform operation would
        effect content in all layers.  Need to employ VectorDataTransform (requires imports).
    """
    layerset = layer.getParent()
    # Transform Displayables in layer.
    for d in layer.getDisplayables():  # Assume this always gives full list.
        d.preTransform(at, linked)
    # Build Coordinate Transform for VDTs
    ct = AffineModel2D()  # CoordinateTransform, imported from mpicbg.models.
    ct.set(at)
    # Transform ZDisplayables in layer.
    zdata = layerset.getZDisplayables()  # Assume full list.
    for zd in zdata:
        apply_vdt(layer, zd, ct)


def apply_vdt(layer, v, ct):
    """ Create and apply a VDT to vector data in a specific layer.
    """
    # Have found that if some Vector Data points are at the boundary of the roi, it
    # will not be affected by the VDT.  Workaround is to increase the roi bounds by
    # 1 unit in each direction... seems to do the trick?
    bounds = v.getBoundingBox()
    # Need to provide VDT with an 'Area' ROI.  Use ImageJ 'Roi' to avoid imports.
    roi = M.getArea(Roi(bounds.x-1, bounds.y-1, bounds.width+2, bounds.height+2))
    vdt = VectorDataTransform(layer)
    vdt.add(roi, ct)
    v.apply(vdt)


def get_displayables(layer):
    """ Get a list of displayables AND z-displayables that are present in layer.
    """
    if layer.isEmpty(): return None
    items = layer.getDisplayables()  # Easy.
    for zd in layer.getParent().getZDisplayables():
        if zd.paintsAt(layer):
            items.append(zd)
    return items


def normalize(layerset, layers=None, match_cal=False):
    """ Normalize scaling of each layer according to calibration.
        
        Note: Layers with locked patches are left untouched!
    """
    cal = layerset.getCalibrationCopy()
    pw = cal.pixelWidth
    if layers is None:
        layers = layerset.getLayers()
    rescale_fail = []
    
    for layer in layers:
        patches = layer.getDisplayables(Patch)
        if any([patch.isLocked() for patch in patches]):
            # Skip layer normalization if locked patches are found.
            rescale_fail.append('%s (z=%0.1f)' % (layer.getTitle(), layer.getZ()))
            logmsg('Locked patches in %s (z=%0.1f), will not be normalized!' % (layer.getTitle().encode('utf-8'), layer.getZ()), False)
            continue
        if match_cal:
            scale_list = [t2.displayable.get_relative_scale(patch) for patch in patches if get_embedded_cal(patch) == pw]
            if not scale_list:
                logmsg('No patches in %s (z=%0.1f) matched project calibration, so normalizing using all patches ...' % (layer.getTitled().encode('utf-8'), layer.getZ()), False)
                scale_list = [t2.displayable.get_relative_scale(patch) for patch in patches]
        else:
            scale_list = [t2.displayable.get_relative_scale(patch) for patch in patches]
        rescale = 1.0 / (float(sum(scale_list)) / len(scale_list))
        scale(layer, rescale)
        straighten_using_patches(layer)
        bbox = layer.getMinimalBoundingBox(Patch, True)
        translate(layer, -bbox.x, -bbox.y)
        layer.recreateBuckets()  # Redundant?
        logmsg('Layer %s (z=%0.1f) was scaled by %0.4f and moved to the origin.' % (layer.getTitle().encode('utf-8'), layer.getZ(), rescale), False)
    
    if rescale_fail:
        logmsg('The following layers were not normalized because they contained locked patches:\n' +
                     '\n'.join(rescale_fail))


def remove(project, layer):
    """ Removes layer from project cleanly.
    """
    project.getLayerTree().remove(layer, False)
    project.getLayerTree().updateList(project.getRootLayerSet())


def rotate(layer, rot, linked=False, center=False):
    """ Rotate all elements, but only in single layer.
    
        ROT is in radians.
    """
    at = AffineTransform()
    if center:
        x,y = centroid(t2.canvas.min_bbox([layer]))
        at.translate(x, y)
    at.rotate(rot)
    if center:
        at.translate(-x, -y)
    transform(layer, at, linked)


def scale(layer, sx, sy=None, xo=0.0, yo=0.0, linked=False):
    """ Scale all elements, but only in single layer.
    """
    if sy is None:
        sy = sx
    at = AffineTransform()
    at.translate(xo, yo)
    at.scale(sx, sy)
    at.translate(-xo, -yo)
    transform(layer, at, linked)


def straighten_using_patches(layer, linked=False, center=False):
    """ Straighten elements according to patches, but only in single layer.
    """
    rots = [t2.displayable.get_rotation(p) for p in layer.getDisplayables(Patch)]
    rot = float(sum(rots)) / len(rots)
    rotate(layer, -rot, linked, center)


def straighten_using_points(layer, p1, p2, horz=True, linked=False, center=False):
    """ Straighten elements in layer according to pair of points.
    
        P1/P2: (x,y) tuples
    """
    if horz:  # Want left-most x-coord first.
        if p1[0] > p2[0]: p2,p1 = p1,p2
    else:  # Want top-most y-coord first.
        if p1[1] > p2[1]: p2,p1 = p1,p2
    rot = Math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    if not horz:
        rot = -(Math.PI/2 - rot)
    rotate(layer, -rot, linked, center)
    logmsg('Layer %s was straightened by %0.2f degrees.' % (layer.getTitle(), Math.toDegrees(rot)))


def translate(layer, tx, ty, linked=False):
    """ Translate all elements, but only in single layer.
    """
    at = AffineTransform()
    at.translate(tx, ty)
    transform(layer, at, linked)


def mod_transformer_gui():
    """ Special dialog to allow the transformation of all types of data in a single
        layer--meaning only layer-specific content in zDisplayables is transformed,
        not the whole object!
    """
    at = lambda:0

    def reset_buttons():
        display.repaint()
        at.layer = None
        at.item = None
        at.old = None
        at.new = None
        label_layer.setText('Layer: --')
        button_transform.setLabel('Init. Transformer')
        button_transform.setBackground(color_off)
        button_propfirst.setEnabled(False)
        button_propfirst.setBackground(color_off)
        button_proplast.setEnabled(False)
        button_proplast.setBackground(color_off)
        button_cancel.setEnabled(False)

    class dl (DialogListener):
        def dialogItemChanged(self, gd, e):
            if not e: return
            layer = display.getLayer()
            es = e.getSource()
            if es == checkbox_top:
                dlg.setAlwaysOnTop(es.getState())
                return True
            if at.old:
                if at.layer != layer:
                    dlg.setAlwaysOnTop(False)
                    logmsg('Active layer was changed, cannot perform transform!', True)
                    dlg.setAlwaysOnTop(checkbox_top.getState())
                    canvas.cancelTransform()
                    reset_buttons()
                    return True
                elif not isinstance(display.getMode(), AffineTransformMode):
                    dlg.setAlwaysOnTop(False)
                    logmsg('Transform mode no longer active, cannot perform transform!', True)
                    dlg.setAlwaysOnTop(checkbox_top.getState())
                    reset_buttons()
                    return True
                at.new = at.item.getAffineTransformCopy()
                at.new.concatenate(at.old.createInverse())
            if es == button_transform:
                if at.old is None:
                    items = get_displayables(layer)
                    if not items:
                        dlg.setAlwaysOnTop(False)
                        logmsg('Nothing to transform in this layer!', True)
                        dlg.setAlwaysOnTop(checkbox_top.getState())
                        return True
                    at.item = items[0]
                    at.layer = layer
                    label_layer.setText('Layer: %s' % layer.getTitle())
                    at.old = at.item.getAffineTransformCopy()
                    button_transform.setLabel('Transform Layer!')
                    button_transform.setBackground(color_on)
                    button_propfirst.setEnabled(True)
                    button_propfirst.setBackground(color_on)
                    button_proplast.setEnabled(True)
                    button_proplast.setBackground(color_on)
                    button_cancel.setEnabled(True)
                    display.getSelection().selectAll()
                    display.setMode(AffineTransformMode(display))
                else:
                    canvas.cancelTransform()
                    transform(layer, at.new)
                    if checkbox_reset.getState():
                        t2.canvas.reset(None, True, True, True)
                    else:
                        t2.canvas.reset()
                    reset_buttons()
            elif es in [button_propfirst, button_proplast]:
                layers = layerset.getLayers()
                if es == button_propfirst:
                    layers = layers[:layers.index(layer)+1]
                elif es == button_proplast:
                    layers = layers[layers.index(layer):]
                canvas.cancelTransform()
                for layer_ in layers:
                    transform(layer_, at.new)
                if checkbox_reset.getState():
                    t2.canvas.reset(None, True, True, True)
                else:
                    t2.canvas.reset()
                reset_buttons()
            elif es == button_cancel:
                canvas.cancelTransform()
                reset_buttons()
            
            return True

    display = Display.getFront()
    canvas = display.getCanvas()
    layerset = display.getLayerSet()

    dlg = NonBlockingGenericDialog('Mod Transformer')
    gbc = GridBagConstraints()
    gbc.fill = GridBagConstraints.HORIZONTAL
    gbc.anchor = GridBagConstraints.CENTER
    gbc.insets = Insets(3, 3, 3, 3)
    panel = Panel(GridBagLayout())

    gbc.gridx = 0
    gbc.gridy = 0
    gbc.gridwidth = 2
    label_layer = Label('Layer: --', Label.LEFT)
    panel.add(label_layer, gbc)

    gbc.gridy += 1
    button_transform = Button('Init. Transformer')
    button_transform.addActionListener(dlg)
    panel.add(button_transform, gbc)
    color_off = button_transform.getBackground()
    color_on = Color.GREEN

    gbc.gridy += 1
    gbc.insets = Insets(15, 3, 3, 3)
    panel.add(Label('Propagate transform:', Label.LEFT), gbc)

    gbc.gridy += 1
    gbc.insets = Insets(3, 3, 3, 3)
    gbc.gridwidth = 1
    button_propfirst = Button('to First')
    button_propfirst.addActionListener(dlg)
    panel.add(button_propfirst, gbc)

    gbc.gridx += 1
    button_proplast = Button('to Last')
    button_proplast.addActionListener(dlg)
    panel.add(button_proplast, gbc)

    gbc.gridy += 1
    gbc.gridx = 0
    gbc.gridwidth = 2
    gbc.insets = Insets(15, 3, 3, 3)
    button_cancel = Button('Cancel Transform')
    button_cancel.addActionListener(dlg)
    panel.add(button_cancel, gbc)
    
    gbc.gridy += 1
    checkbox_reset = Checkbox('Reset canvas?', False)
    checkbox_reset.addItemListener(dlg)
    panel.add(checkbox_reset, gbc)

    gbc.gridy += 1
    checkbox_top = Checkbox('Always on top?', True)
    checkbox_top.addItemListener(dlg)
    panel.add(checkbox_top, gbc)

    dlg.addPanel(panel)
    dlg.addDialogListener(dl())
    dlg.hideCancelButton()
    dlg.setOKLabel('Close')
    dlg.setAlwaysOnTop(True)
    reset_buttons()
    dlg.showDialog()
    # end