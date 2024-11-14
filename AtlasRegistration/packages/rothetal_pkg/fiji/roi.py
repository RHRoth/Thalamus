# fiji/roi.py
# v.2022.04.07
# m@muniak.com
#
# Functions for ROIs.

# 2024.11.07 - Cleaned up for manuscript deposit.

from array import array
from ij.io import Opener
from ij.gui import ImageRoi
from ij.gui import PolygonRoi
from ij.gui import Roi
from ij.gui import ShapeRoi
from ij.gui import TextRoi
from ij.plugin import RoiEnlarger
from ij.plugin import RoiScaler
from ij.process import ByteProcessor
from java.awt.geom import AffineTransform
from java.awt.geom import Rectangle2D

from .calibration import convert_units
from .utils import is_num
from .utils import logerror
from .utils import logmsg


def roi_bounds_area(roi):
    """ Return area bounded by Roi's bounds.
        NOTE: Not necessarily area of Roi itself if not rectangle.
    """
    rec = roi.getBounds()
    return rec.getWidth() * rec.getHeight()


def get_real_float_bounds(roi):
    """ Returns ACTUAL Float boundaries of an Roi.
        Built-in .FloatWidth() etc. seem to be rounded values...
    """
    fp = roi.getFloatPolygon()
    if len(fp.xpoints) == 0 or len(fp.ypoints) == 0:
        return None
    min_x = min(fp.xpoints)
    max_x = max(fp.xpoints)
    min_y = min(fp.ypoints)
    max_y = max(fp.ypoints)
    return Rectangle2D.Float(min_x, min_y, max_x-min_x, max_y-min_y)


def roi_area(roi, ip=None, cal=None):
    """ Return area of Roi; calibrated if provided.
        If no ImagePlus or ImageProcessor is provided, one is temporarily created.
    """
    if not ip:
        b = roi.getBounds()
        ip = ByteProcessor(b.x+b.width, b.y+b.height)
    try:
        # Allow for ImagePlus.  Only override calibration if not provided.
        if not cal: cal = ip.getCalibration()  #
        ip = ip.getProcessor()
    except:
        pass
    old_roi = ip.getRoi()
    ip.setRoi(roi)
    a = ip.getStats().area
    ip.setRoi(old_roi)
    if cal:
        a = cal.getX(cal.getY(a))
    return a


def get_roi_from_path(path, invert=False):
    """ Extract ROI from an image file (if it exists).
    """
    imp = Opener().openImage(path)
    if imp is None:
        logmsg('Image not found: %s' % path)
        return None
    roi = imp.getRoi()
    if invert:
        roi = invert_roi(imp.getRoi(), imp)
    imp.close()
    imp.flush()
    return roi


def invert_roi(roi, a, b=None):
    """ Programmatic version of "Make Inverse" command.
        XOR only works with ShapeRois, so must convert.
        'a' can either be an ImagePlus/Processor or a 
        width value; if the latter, 'b' must be height.
    """
    #if roi is None:
    if not roi:
        return None
    try:  # Did we get numbers?
        w = int(a)
        h = int(b)
    except TypeError:
        try:  # Is (a) a layerset?  (.getWidth() returns 20px)
            w = a.getLayerWidth()
            h = a.getLayerHeight()
        except AttributeError:  # Must be an ImagePlus/Processor
            w = a.getWidth()
            h = a.getHeight()
    roi1 = ShapeRoi(roi)  # Not sure if bombproof.
    roi2 = ShapeRoi(Roi(0, 0, w, h))
    res = roi1.xor(roi2)
    if roi_bounds_area(res) == 0:
        return None
    else:
        return res


def transform_roi(roi, at, inverse=True):
    """ Transform an roi based on an AffineTransform.
    """
    #if roi is None:
    if not roi:
        return None
    elif at is None:
        return roi
    # This _should_ correctly transform composite Rois... might need to sort getRois() smallest-to-largest?
    if isinstance(roi, ShapeRoi):
        result = None
        for roi2 in [transform_roi(r, at, inverse=inverse) for r in roi.getRois()]:
            if not result:
                result = ShapeRoi(roi2)
            else:
                result.xor(ShapeRoi(roi2))
        return result
    else:
        poly = roi.getFloatPolygon()  # Fix 2021.05.12 to use floats.
        pts = array('d', [p for t in zip(poly.xpoints, poly.ypoints) for p in t])
        if inverse:
            at.inverseTransform(pts, 0, pts, 0, poly.npoints)
        else:
            at.transform(pts, 0, pts, 0, poly.npoints)
        pts = [float(p) for p in pts]  # Fix 2021.05.12 to use floats.
        poly2 = PolygonRoi(pts[::2], pts[1::2], poly.npoints, PolygonRoi.POLYGON)
        return ShapeRoi(poly2)


def smooth_roi(roi, s):
    """ Smooth an roi with an interval of s.
        Not guaranteed to work with complex ShapeRois, but maybe?
    """
    if isinstance(roi, ShapeRoi):
        result = None
        for roi2 in [smooth_roi(r, s) for r in roi.getRois()]:
            try:
                if not result:
                    result = ShapeRoi(roi2)
                    # Quick check to verify this ROI actually contains an area.
                    # Otherwise subsequent XORs will fail.
                    if not result.getShape():
                        result = None
                else:
                    result.xor(ShapeRoi(roi2))
            except:  # Not sure what exact exception(s) occur (seeing Java NullPointerException).
                continue
        return result
    else:
        tmp = PolygonRoi(roi.getInterpolatedPolygon(1, False), PolygonRoi.POLYGON)  # 2021.04.14 Fix to ensure that starting material is 1px spaced polygon.
        return PolygonRoi(tmp.getInterpolatedPolygon(s, True), PolygonRoi.POLYGON)


def on_edge(roi, w, h):
    """ Test if ROI is touching boundary of box.
    """
    b = roi.getBounds()
    return b.x == 0 or b.y == 0 or b.x+b.width == w or b.y+b.height == h


def contains_all(roi1, roi2):
    """ Test if ROI1 entirely contains the points of ROI2.
    """
    fp = roi2.getPolygon()
    return all([roi1.contains(x,y) for x,y in zip(fp.xpoints, fp.ypoints)])


def contains_any(roi1, roi2):
    """ Test if ROI1 contains any points of ROI2.
    """
    fp = roi2.getPolygon()
    return any([roi1.contains(x,y) for x,y in zip(fp.xpoints, fp.ypoints)])


def merge_rois(*args):
    """ Simple merging (or) of ROIs into a single ShapeRoi.
        Input is list of ROIs (separate args).
    """
    try:
        result = []
        for i,roi in enumerate(args):
            if not roi:
                continue
            if not result:
                result = ShapeRoi(roi)
            else:
                result.or(ShapeRoi(roi))
        return result
    except TypeError:
        logerror(TypeError, 'ROI #%d is invalid and could not be merged!' % (i+1))


def intersect_rois(*args):
    """ Simple intersection (and) of ROIs into a single ShapeRoi.
        Input is list of ROIs (separate args).
    """
    try:
        result = []
        for i,roi in enumerate(args):
            if not roi:
                continue
            if not result:
                result = ShapeRoi(roi)
            else:
                result.and(ShapeRoi(roi))
        return result
    except TypeError:
        logerror(TypeError, 'ROI #%d is invalid and could not be merged!' % (i+1))


def xor_rois(*args):  # added 2022.03.15
    """ Simple merging (XOR) of ROIs into a single ShapeRoi.
        Input is list of ROIs (separate args).
        Order matters, I think.
    """
    try:
        result = []
        for i,roi in enumerate(args):
            if not roi:
                continue
            if not result:
                result = ShapeRoi(roi)
            else:
                result.xor(ShapeRoi(roi))
        return result
    except TypeError:
        logerror(TypeError, 'ROI #%d is invalid and could not be XORed!' % (i+1))


def merge_adjacent_rois(rois, th=50, ip=None):
    """ Examine a set of ROIs for shared points, and merge those that share at least TH points.
        Process from smallest to largest.

        Assumption is that ROIs are the result of a Distance Transform Watershed, which means
        they are separated by a 1px margin.  Thus, pairs of ROIs are enlarged by 1px, and the 
        size of the mutual overlap (a close proxy for distance of shared border) is used to
        decide if they should be merged or not.
    """
    rois = sorted(rois, key=lambda x: x.size())  # Note: This is only number of points, which is not necessarily area.
    n = len(rois)
    # Iterate through all combinations of pairs.
    for i in range(n-1):
        # If we are excluding objects touching the edge, don't bother processing.
        if ip and on_edge(rois[i], ip.getWidth(), ip.getHeight()):
            continue
        # Enlarge by 1 px.
        r1 = RoiEnlarger.enlarge(rois[i], 1)
        # Default flags.
        idx = None
        max_a = 0.0
        # Iterating through second of pair.
        for j in range(i+1, n):
            # Ditto about edge.
            if ip and on_edge(rois[j], ip.getWidth(), ip.getHeight()):
                continue
            # Enlarge by 1 px.
            r2 = RoiEnlarger.enlarge(rois[j], 1)
            # Find any overlap and compute size (# of px).
            rx = ShapeRoi(r1).and(ShapeRoi(r2))
            a = roi_area(rx,ip)
            # If overlap sufficiently large, mark for merging.
            if a >= th and a > max_a:
                max_a = a
                idx = j
                # Construct merged ROI.
                new_roi = merge_rois(rx, rois[i], rois[j])
        if idx:
            # Keep merged ROI, remove one of the originals ones.
            rois[idx] = new_roi
            rois[i] = None
    # Return w/o Nones.
    return [roi for roi in rois if roi]


# def scale_roi(roi, x_scale, y_scale=None, centered=False):
#     """ Calls RoiScaler IJ plugin.
#     """
#     if y_scale is None:
#         y_scale = x_scale
#     return RoiScaler.scale(roi, x_scale, y_scale, centered)


def scale_roi(roi, x_scale, y_scale=None, centered=False):
    """ Scales ROI without integer rounding.
        If input is TextRoi or ImageRoi, use RoiScaler plugin.
        Scales stroke width.
    """
    if y_scale is None:
        y_scale = x_scale
    if (isinstance(roi, TextRoi) or isinstance(roi, ImageRoi)):
        return RoiScaler.scale(roi, x_scale, y_scale, centered)
    at = AffineTransform()
    if centered:
        fb = get_real_float_bounds(roi)
        at.translate(fb.x+fb.width/2, fb.y+fb.height/2)
    at.scale(x_scale, y_scale)
    if centered:
        at.translate(-fb.x-fb.width/2, -fb.y-fb.height/2)
    t_roi = transform_roi(roi, at, inverse=False)
    t_roi.setStrokeWidth(roi.getStrokeWidth() * (x_scale+y_scale) / 2)
    return t_roi


def resize_calibrated_roi(source_cal, target_cal, roi):
    """ Resize an Roi based on source/target pixel calibrations.
    """
    # Calculate X scaling.
    x_scale = source_cal.pixelWidth / target_cal.pixelWidth
    x_scale, _ = convert_units(x_scale, source_cal.getUnit(), target_cal.getUnit())
    # Calculate Y scaling (should be same).
    y_scale = source_cal.pixelHeight / target_cal.pixelHeight
    y_scale, _ = convert_units(y_scale, source_cal.getUnit(), target_cal.getUnit())
    # Scale Roi.
    #roi2 = RoiScaler.scale(roi, x_scale, y_scale, False)
    roi2 = scale_roi(roi, x_scale, y_scale)
    return roi2


def xfer_calibrated_roi(source, target, roi=None):
    """ Transfer an Roi from one ImagePlus to another using calibrated coordinates.
    """
    if roi is None:
        roi = source.getRoi()
    if not roi:
        logmsg('No Roi to transfer..!')
        return
    # Get calibrations.
    source_cal = source.getCalibration()
    target_cal = target.getCalibration()
    # Resize Roi.
    roi2 = resize_calibrated_roi(source_cal, target_cal, roi)
    target.setRoi(roi2)
    return roi2
