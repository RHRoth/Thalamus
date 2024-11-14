# fiji/t2/layerset.py
# v.2020.09.26
# m@muniak.com
#
# Common layerset functions for TrakEM2.

# 2024.11.07 - Cleaned up for manuscript deposit.

from java.awt.geom import AffineTransform

from .. import t2
import ..t2.canvas
import ..t2.layer


def scale(layerset, sx, sy=None, xo=0.0, yo=0.0, linked=False):
    """ Scale all elements in all layers of layerset.
    """
    if sy is None:
        sy = sx
    for d in layerset.getDisplayables():  # Assume this always gives full list.
        d.scale(sx, sy, xo, yo, linked)
        # Note: Font sizes of labels are also affected... no easy fix.
    for zd in layerset.getZDisplayables():  # Also assume this gives full list.
        zd.scale(sx, sy, xo, yo, linked)


def rotate(layerset, rot):
    """ Rotate entire layerset.
    
        ROT is in radians.
    """
    for layer in layerset.getLayers():
        t2.layer.rotate(layer, rot)
    t2.canvas.reset(layerset, resize=True)


def flip_x(layerset):
    """ Flip entire project horizontally.
    """
    w = layerset.getLayerWidth()
    at = AffineTransform()
    at.translate(w, 0)
    at.scale(-1, 1)
    for layer in layerset.getLayers():
        t2.layer.transform(layer, at)
    t2.canvas.reset(layerset)


def flip_y(layerset):
    """ Flip entire project vertically.
    """
    h = layerset.getLayerHeight()
    at = AffineTransform()
    at.translate(0, h)
    at.scale(1, -1)
    for layer in layerset.getLayers():
        t2.layer.transform(layer, at)
    t2.canvas.reset(layerset)