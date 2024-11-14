# fiji/t2/displayable.py
# v.2022.04.01
# m@muniak.com
#
# Common displayable functions for TrakEM2.

# 2024.11.07 - Cleaned up for manuscript deposit.
# 2022.04.01 -- added get_flipped(); added copysign() to get_scale() to indicate if element is flipped along dim (but commented it back out)

import math
from ij import IJ

from ..calibration import get_embedded_cal


def centroid(elems):
    """ Get center coordinate for a list of Displayables.
    """
    xmin = float('inf')
    xmax = float('-inf')
    ymin = float('inf')
    ymax = float('-inf')
    for elem in elems:
        box = elem.getBoundingBox()
        xmin = min(xmin, box.x)
        xmax = max(xmax, box.x+box.width)
        ymin = min(ymin, box.y)
        ymax = max(ymax, box.y+box.height)
    xc = (xmin + xmax) / 2.0
    yc = (ymin + ymax) / 2.0
    return xc, yc


def crosslink(patches, overlapping_only=False):
    """ Crosslink all patches.
    """
    for i in range(len(patches)):
        for j in range(i+1, len(patches)):
            if overlapping_only and not patches[i].intersects(patches[j]):
                pass
            else:
                patches[i].link(patches[j])


def get_relative_scale(elem):
    """ Get relative scaling of object within the project coordinate space.
    """
    cal = elem.getLayerSet().getCalibrationCopy()
    pw = cal.pixelWidth
    u = cal.getUnit()
    return pw / ((2 * get_embedded_cal(elem, u)) / (get_scale(elem,0) + get_scale(elem,1)))


def get_scale(elem, dim=0):
    """ Get scale component of object's affine transform, in x- or y-dimension.
    """
    # FIX 2022.04.01 -- Added copysign() to indicate if item was flipped or not along axis!
    at = elem.getAffineTransformCopy()
    if dim == 0:
        return (at.getScaleX()**2 + at.getShearX()**2) ** 0.5
        #return math.copysign((at.getScaleX()**2 + at.getShearX()**2) ** 0.5, at.getScaleX())
    elif dim == 1:
        return (at.getScaleY()**2 + at.getShearY()**2) ** 0.5
        #return math.copysign((at.getScaleY()**2 + at.getShearY()**2) ** 0.5, at.getScaleY())


def get_flipped(elem):
    """ Return -1 if elem has been flipped (X or Y), otherwise +1.
    """
    at = elem.getAffineTransformCopy()
    return math.copysign(1, at.getScaleX() * at.getScaleY())


def get_rotation(elem):
    """ Get rotation component of object's affine transform.
    """
    at = elem.getAffineTransformCopy()
    return math.atan2(at.getShearY(), at.getScaleY())


def get_translation(elem):
    """ Get translation components of object's affine transform.
    """
    at = elem.getAffineTransformCopy()
    return (at.getTranslateX(), at.getTranslateY())


def remove_linked(elems):
    """ Return list of elems that only includes one element from each linked subset.
    """
    for elem in elems[1::]:
        if elems[0].isLinked(elem):
            elems.remove(elem)
    return elems


def scale(elems, s, absolute=False, center=True, linked=True):
    """ Scale displayables by value.  Can be relative or absolute.
    """
    if math.isnan(s):
        IJ.showMessage('Scale value must be numeric!')
        return False
    if center: xc, yc = centroid(elems)
    else:      xc, yc = 0, 0
    #if absolute: linked = False  # Override.  ## TODO: Might be a problem?
    if linked:
        elems = remove_linked(elems)
    for elem in elems:
        s_ = s
        if absolute:
            s_ = s_ / get_scale(elem)
        elem.scale(s_, s_, xc, yc, linked)
    return True


def sort_by_z(objs):
    """ Sort objects by Z, then title.
    """
    objs = sorted(objs, key=lambda item: item.getTitle())  # Secondary sort.
    objs = sorted(objs, key=lambda item: item.getZ())  # Primary sort.
    return objs


def unlink(elems):
    """ Unlink all elements.
    """
    for elem in elems:
        elem.unlink()