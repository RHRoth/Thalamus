# -*- coding: utf-8 -*-
# fiji/t2/injection.py
# v.2020.10.08
# m@muniak.com
#
# Functions for dealing with injection-specific TrakEM2 projects.

# 2024.11.07 - Cleaned up for manuscript deposit.

import math
from ij import IJ
from ij import WindowManager
from ij.gui import GenericDialog
from ij.gui import Line
from ij.gui import OvalRoi
from ij.gui import Roi
from ij.gui import TextRoi
from ij.process import LUT
from java.awt import Font
from java.awt import Color

from .. import color_chooser
from ..utils import logerror
from ..utils import logmsg
from .. import t2
import ..t2.objs


bicubic_offset = 0.25  # % of layer thickness.  Should be 0.5, but there appears to be a bug in bicubic interpolation...


def add_markers(N=2, colors=[], comments=[]):
    injs = t2.objs.find_type_in_project('polyline', parent_name='injs')
    injs.sort(key=lambda x: x.getTitle())
    if not colors:  # If no overriding input provided.
        colors = [inj.getColor() for inj in injs]
        if colors:
            comments = [inj.getTitle().replace('inj_%d_' % (i+1), '') for i,inj in enumerate(injs)]
    if not comments:
        comments = [''] * N

    cc = color_chooser.run(colors, desc='Inj.', n=N, adjustable=True, comments=comments)
    if cc is None:
        return
    colors, comments = cc
    
    if len(colors) < len(injs):
        del_injs = injs[len(colors):]
        dlg = GenericDialog('Removing Injs.')
        dlg.addMessage('Remove the following injection polylines?')
        for inj in del_injs:
            dlg.addMessage('-- ' + inj.getTitle().replace('_',' '))
        dlg.enableYesNoCancel()
        dlg.hideCancelButton()
        dlg.showDialog()
        if dlg.wasOKed():
            t2.get_project().removeAll(set(del_injs))
    
    for i,(c,cmt) in enumerate(zip(colors,comments)):
        try:
            injs[i].setColor(c)  # Adjust color of existing polyline.
        except IndexError:  # Need to add polyline.
            injs.append(t2.objs.add_to_node(node='injs', objtype='polyline', objcolor=c))
        injs[i].setTitle('inj_%d_%s' % (i+1, cmt))
        t2.get_project().getProjectTree().updateUILater()
        t2.get_display().update()


def draw_crosshairs(imp, diam, tick, n=2):
    # Assumption that injection is centered in square at bottom of image.
    # n = number of viewing angles.

    cal = imp.getCalibration()
    ip = imp.getProcessor()
    ip.setLineWidth(1)
    ip.setColor(Color.WHITE)

    w = imp.getWidth()/2.0
    h = imp.getHeight()
    d = cal.getRawX(diam)  # Circle diam in px.
    t = cal.getRawX(tick)  # Tick length in px.

    for i in range(n):
        xc = w/2.0   # Horizontal center.
        yc = h-xc    # Vertical center.  Assumption that injection is at bottom.
        xc += w*i    # Horizontal offset for each panel.
        xe = xc-d/2  # Horizontal left edge.
        ye = yc-d/2  # Vertical top edge.
        roi = OvalRoi(xe, ye, d, d)
        ip.draw(roi)
        lines = [(xe-t/2,   ye+d/2,   xe+t/2,   ye+d/2),    # Left tick.
                 (xe-t/2+d, ye+d/2,   xe+t/2+d, ye+d/2),    # Right tick.
                 (xe+d/2,   ye-t/2,   xe+d/2,   ye+t/2),    # Top tick.
                 (xe+d/2,   ye-t/2+d, xe+d/2,   ye+t/2+d)]  # Bottom tick.
        for l in lines:
            roi = Line(l[0], l[1], l[2], l[3])
            roi.setStrokeWidth(1)
            ip.draw(roi)

    imp.updateAndDraw()
    return imp


def process_poly(poly, layerset, cal, w, h):
    # Get VectorString3D
    v3d = poly.asVectorString3D()

    # Get coordinates.
    x1,x2 = [cal.getX(v) for v in v3d.getPoints(0)]  # µm
    y1,y2 = [cal.getY(v) for v in v3d.getPoints(1)]  # µm
    z1,z2 = [cal.getX(v) for v in v3d.getPoints(2)]  # µm... note getX() (or Y)!
    
    # Get tilt.
    try:
        th = math.atan((y2-y1) / (z2-z1))
        th = math.copysign((math.pi / 2) - abs(th), th)
    except ZeroDivisionError:
        th = 0
    dz = math.sin(th)
    dy = math.cos(th)

    # Determine center coords.
    a = w/2      # µm
    b = w/2 - h  # µm
    corners_z = [z1+r for r in [a*(dz-dy), a*(dz+dy), (b*dz)-(a*dy), (b*dz)+(a*dy)]]
    corners_y = [y1+r for r in [a*(dy+dz), a*(dy-dz), (b*dy)+(a*dz), (b*dy)-(a*dz)]]
    y_span = max(corners_y) - max([0, min(corners_y)])
    yc = y_span - a*(abs(dy) + abs(dz))
    xc = a
    
    z_start = max([cal.getX(layerset.getLayers()[0].getZ()),
                  cal.getZ(math.floor(cal.getRawZ(min(corners_z))))])  # First possible layer, in µm.
    # If corresponding layer does not exist, back up section-by-section until it does.
    while layerset.getLayer(cal.getRawX(z_start)) is None:
        z_start -= cal.getZ(1)
    z_end = min([cal.getX(layerset.getLayers()[-1].getZ()),
                 cal.getZ(math.ceil(cal.getRawZ(max(corners_z))))])  # Last possible layer, in µm.
    # If corresponding layer does not exist, move up section-by-section until it does.
    while layerset.getLayer(cal.getRawX(z_end)) is None:
        z_end += cal.getZ(1)
    zc = z1 - z_start + cal.getZ(bicubic_offset)

    # Get existing layers (as index) that correspond to z-vals.
    try:
        first_layer = layerset.getLayerIndex(layerset.getLayer(cal.getRawX(z_start)).getId())
        last_layer = layerset.getLayerIndex(layerset.getLayer(cal.getRawX(z_end)).getId())
    except TypeError:
        logerror(TypeError, 'Something went wrong with finding layer index by z-val...', True)

    # Compute xy export roi.
    px = int(cal.getRawX(x1 - a))
    py = int(cal.getRawY(max([0, min(corners_y)])))
    roi_rect = Roi(px, py, cal.getRawX(w), cal.getRawY(int(y_span)))

    # Compute yz export roi.
    roi_line = Line(cal.getRawX(zc + dz*a), cal.getRawY(yc + dy*a), 
                    cal.getRawX(zc + dz*b), cal.getRawY(yc + dy*b))
    roi_line.setStrokeWidth(cal.getRawX(w))

    # Return
    return first_layer, last_layer, roi_rect, roi_line


def export(w=1250., h=6000., do_crosshairs=True, do_label=True, do_fire=True, do_8bit=True, do_close=True, do_closestacks=True, channels=[], titles=[], crosshair_diam=0.8, crosshair_tick=0.1):
    project = t2.get_project()
    layerset = t2.get_layerset()
    cal = t2.get_calibration()
    polys = sorted(t2.objs.find_type_in_project('polyline', parent_name='injs'))
    
    if not polys:
        logerror(IndexError, 'No injection Polylines found in project!', True)
    # Make sure each line is only 2 points.
    # TODO: Allow more than 2 and use best-fit line?
    for poly in polys:
        if poly.length() < 2:
            logerror(ValueError, 'Polyline [ %s ] has less than 2 points!' % poly.getTitle(), True)
        elif poly.length() > 2:
            logerror(ValueError, 'Polyline [ %s ] has more than 2 points!' % poly.getTitle(), True)
    
    # Ask which channel to use for each injection (if not provided).
    if not channels:
        dlg = GenericDialog('Select channels')
        dlg.addMessage('Please select raw channel to use for each injection:')
        for i,poly in enumerate(polys):
            dlg.addChoice(poly.getTitle(), ['Ch. %d' % (c+1) for c in range(max([3, len(polys)]))], 'Ch. %d' % (i+1))
            dlg.addToSameRow()
            dlg.addPanel(color_chooser.create_swatch(poly.getColor()))
        dlg.showDialog()
        if not dlg.wasOKed():
            return None
        channels = [choice.getSelectedIndex() for choice in dlg.getChoices()]
    
    # Process polylines and get relevant extraction coordinates.
    coords = [process_poly(poly, layerset, cal, w, h) for poly in polys]

    # Get smallest layer range we need to export.
    first_layer = min([coord[0] for coord in coords])
    last_layer = max([coord[1] for coord in coords])
    
    # Get raw files.
    prev_ids = WindowManager.getIDList()
    IJ.run('create raw hyperstack', 'ext=czi do_split=True first_index=%d last_index=%d insert_missing=True' % (first_layer, last_layer))
    new_ids = set(WindowManager.getIDList()).difference(set(prev_ids))
    imps = [WindowManager.getImage(id) for id in new_ids]
    imps.sort(key=lambda x: x.getTitle())

    # Process each polyline/injection.
    results = []
    for i in range(len(polys)):
        # Get title.
        try:
            title = titles[i]
        except IndexError:
            title = polys[i].getTitle().replace('inj_%d_' % (i+1), '')
        if not title:
            title = '%s inj.%d' % (project.getTitle(), i+1)

        # Get color.
        color = polys[i].getColor()
        lut = LUT.createLutFromColor(color)
        
        # Get coordinate info.
        range1, range2, roi_rect, roi_line = coords[i]
        
        # Get relevant raw image.
        imp = imps[channels[i]]
        
        # Extract relevant xy stack.
        imp.setRoi(roi_rect)
        IJ.run(imp, 'Duplicate...', 'duplicate range=%d-%d' % (range1 - first_layer + 1, range2 - first_layer + 1))
        stack_xy = IJ.getImage()
        stack_xy.setTitle('%s XY stack' % title)
        
        # Compute yz stack.
        IJ.run(stack_xy, 'Reslice [/]...', 'output=%d start=Left rotate' % cal.pixelWidth)
        stack_yz = IJ.getImage()
        
        # Straighten yz stack.
        stack_yz.setRoi(roi_line)
        IJ.run(stack_yz, 'Straighten...', 'title=temp line=%d process' % int(cal.getRawX(w)))
        stack_yz_straight = IJ.getImage()
        IJ.run(stack_yz_straight, 'Rotate 90 Degrees Left', None)
        
        # Compute tilted xy stack.
        IJ.run(stack_yz_straight, 'Reslice [/]...', 'output=%d start=Left rotate' % cal.pixelWidth)
        stack_xy_straight = IJ.getImage()
        stack_xy_straight.setTitle('%s XY tilted stack' % title)
        if do_close:
            stack_yz.close()
            if do_closestacks:
                stack_xy.close()

        # Compute max projections.
        IJ.run(stack_xy_straight, 'Z Project...', 'projection=[Max Intensity]')
        max_xy = IJ.getImage()
        IJ.run(stack_yz_straight, 'Z Project...', 'projection=[Max Intensity]')
        max_yz = IJ.getImage()
        if do_close:
            stack_yz_straight.close()
            if do_closestacks:
                stack_xy_straight.close()

        # Make sure max proj images have same vertical dimensions (they should...).
        wxy = max_xy.getWidth()
        wyz = max_yz.getWidth()
        hxy = max_xy.getHeight()
        hyz = max_yz.getHeight()
        if abs(hxy-hyz) > 2:
            logerror(ValueError, 'Height mismatch!' % pl.getTitle(), True)

        # Combine max projs into single image.
        IJ.run(max_xy, 'Canvas Size...', 'width=%d height=%d position=Top-Left zero' % (wxy+wyz+1, hxy))
        mip = max_xy.getProcessor()
        mip.insert(max_yz.getProcessor(), wxy+1, 0)
        if do_close:
            max_yz.close()
        
        # Manually set calibration if it does not carry over
        # (sometimes the z-cal is fractionally different than xy-cal during operations).
        cal2 = max_xy.getCalibration()
        if cal2.pixelWidth == 1.0:
            cal2.pixelWidth = cal.pixelWidth
            cal2.pixelHeight = cal.pixelHeight

        # Set display range and LUT.
        ip_max = imp.getDisplayRangeMax()
        mip.setMinAndMax(imp.getDisplayRangeMin(), ip_max)
        if do_fire:
            IJ.run(max_xy, 'Fire', None)
        else:
            max_xy.setLut(lut)

        # Convert to 8-bit if requested.
        if do_8bit:
            mip = mip.convertToByteProcessor(True)
        # Otherwise match raw file.
        else:
            bit = imp.getBitDepth()
            if bit == 32:
                pass  # Already a float.
            elif bit == 16:
                mip = mip.convertToShortProcessor(False)
            elif bit == 8:
                mip = mip.converToByteProcessor(False)

        # Add labels.
        if do_label:
            mip.setColor(Color.WHITE)
            mip.setAntialiasedText(True)
            ft = Font('SansSerif', Font.BOLD, 14)
            TextRoi(5, 5, title, ft).drawPixels(mip)
            TextRoi(5+wxy+1, 5, title, ft).drawPixels(mip)
            TextRoi(5, 25, 'XY', ft).drawPixels(mip)
            TextRoi(5+wxy+1, 25, 'YZ', ft).drawPixels(mip)

        # Finalize.
        max_xy.setProcessor(mip)
        max_xy.setTitle(title)
        max_xy.updateAndDraw()
        results.append(max_xy)

        # Draw crosshairs.
        if do_crosshairs:
            draw_crosshairs(max_xy, w * crosshair_diam, w * crosshair_diam * crosshair_tick, 2)

    # Close raw images.
    for imp in imps:
        imp.close()
        imp.flush()

    return results