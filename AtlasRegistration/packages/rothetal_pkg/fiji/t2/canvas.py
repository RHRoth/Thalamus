# fiji/t2/canvas.py
# v.2020.12.03
# m@muniak.com
#
# Common canvas functions for TrakEM2.

# 2024.11.07 - Cleaned up for manuscript deposit.

import time
from ij import IJ
from ini.trakem2.display import Display
from ini.trakem2.display import Patch

from ..multithread import multi_task
from .. import t2
import ..t2.layer


def expand(layerset=None, scale=2):
    """ Expand canvas dimensions.
    """
    if layerset is None:
        layerset = t2.get_layerset()
    layerset.setDimensions(layerset.getLayerWidth() * scale, layerset.getLayerHeight() * scale, layerset.CENTER)
    t2.get_display().repaint()
    t2.get_display().getCanvas().zoomToFit()


def min_bbox(layers, nonzero=False, reset_dim=True):
    """ Get minimum bounding box for subset of layers.
    """
    bbox = None
    if nonzero and reset_dim:
        # Need to reset canvas first as non-zero bounds are based on image of current canvas.
        layers[0].getParent().setMinimumDimensions()
    def min_bbox_task(i,layer):
        if nonzero:
            IJ.showStatus('Finding nonzero bounds...')
            IJ.showProgress(i, len(layers))
            b = t2.layer.get_nonzero_bounds(layer)  # TODO: Only factors in patches for now.
        else:
            b = layer.getMinimalBoundingBox(Patch, True)  # TODO: Only factors in patches for now.
        return b
    # Soooo much faster multithreaded.
    boxes = multi_task(min_bbox_task, args=zip(range(len(layers)),layers))
    for b in boxes:
        if bbox is None:
            bbox = b
        elif b is not None: # takes care of empty layers
            bbox.add(b)
    return bbox


def minimize(layers=None, nonzero=False):
    """ Minimize total canvas size by moving each layer bounding-box to top-left corner.
    """
    layerset = t2.get_layerset()
    if layers is None:
        layers = layerset.getLayers()
    for layer in layers:
        bbox = min_bbox([layer], nonzero, reset_dim=False)
        t2.layer.translate(layer, -bbox.x, -bbox.y)
    reset(layerset, zoomout=True, resize=True, visible_only=True, nonzero=nonzero)


def reset(layerset=None, zoomout=False, resize=False, visible_only=False, nonzero=False):
    """ Reset canvas display nicely.
    """
    if layerset is None:
        layerset = t2.get_layerset()
    if resize and visible_only:
        bbox = min_bbox(layerset.getLayers(), nonzero)
        layerset.setDimensions(bbox.x, bbox.y, bbox.width, bbox.height)
    elif resize:
        layerset.setMinimumDimensions()
    while Display.getFront() is None: # Sometimes goes too fast, misses display?
        time.sleep(1)
    display = t2.get_display()
    display.repaint()
    if zoomout:
        display.getCanvas().zoomToFit()
    display.repairGUI()
    display.update()