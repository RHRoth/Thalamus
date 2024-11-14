# fiji/segmentation.py
# v.2022.03.15  # Still a work in progress...  CHECK FOR VESTIGIAL IMPORTS
# m@muniak.com
#
# Functions for segmenting & masking images.

# 2024.11.07 - Cleaned up for manuscript deposit.

import math
from ij import IJ
from ij import ImagePlus
from ij.gui import GenericDialog
from ij.gui import NonBlockingGenericDialog
from ij.gui import Overlay
from ij.gui import PolygonRoi
from ij.gui import Roi
from ij.gui import ShapeRoi
from ij.plugin import RoiEnlarger
from ij.plugin.filter import Binary
from ij.plugin.filter import RankFilters
from ij.plugin.filter import ThresholdToSelection
from ij.process import AutoThresholder
from ij.process import Blitter
from ij.process import ColorProcessor
from java.awt import Color
from java.awt import Point

from .roi import contains_all
from .roi import invert_roi
from .roi import merge_adjacent_rois
from .roi import merge_rois
from .roi import on_edge
from .roi import resize_calibrated_roi
from .roi import roi_area
from .roi import roi_bounds_area
from .roi import smooth_roi
from .roi import xor_rois
from .utils import attributes_to_string
from .utils import is_num
from .utils import logerror
from .utils import logmsg
from .utils import process_str
from .utils import replace_attributes_from_prefs
from .utils import save_attributes_as_prefs

# Attempt to load INRA modules -- not loaded in FIJI by default, must be selected in updater!
try:
    from inra.ijpb.binary import BinaryImages
    from inra.ijpb.binary import ChamferWeights
    from inra.ijpb.morphology import Strel
    from inra.ijpb.watershed import ExtendedMinimaWatershed
except ImportError as e:
    logerror(ImportError, 'INRA libraries must be loaded--select "IJPB-plugins" in update sites!', True)
    raise


# List of parameter options that we will save in IJ Prefs.
PREFS_LIST = ['background_color', 'null_detect', 'threshold_method', 'clip_percent', 'mask_edge_buffer', 
              'smooth', 'remove_edge', 'add_center', 'review', 'custom_params', 'final_action']


# Auto Thresholder methods.  Hardcoded because slight difference between the way Auto_Threshold.java plugin works
# compared to AutoThresholder.java... the latter's .getMethods() returns 'MinError' while the former uses 'MinError(I)'.
AT_METHODS = ['Default', 'Huang', 'Huang2', 'Intermodes', 'IsoData',  'Li', 'MaxEntropy', 'Mean', 'MinError(I)', 
              'Minimum', 'Moments', 'Otsu', 'Percentile', 'RenyiEntropy', 'Shanbhag' , 'Triangle', 'Yen']


def init_mask_params(**kwargs):
    """ Return default parameters array for mask_image function.
        Further customize options with named inputs.
    """
    params = lambda:0
    params.debug = None                  # Debug options.
    params.downsample_calibration = 0.1  # Image res (px/um) for finding max.
    params.downsample_aliasing = False   # Apply aliasing while downsampling image? -- added 2022.03.15
    params.background_color = 'white' #'black'    # 'black'/'white'
    params.null_detect = 'both' #None            # Blocks of null space to remove: 'white','black','both'
    params.null_border = True            # Restrict null space to regions touching border.
    params.pad_percent = 0.1             # Percentage of (max-min) range to pad null_border detection to catch aliased edges.
    params.alias_edge = 2                # Expansion of black/white null_border detection (in px) to catch aliased edges.
    params.clip_percent = 0.1 #0.05           # Range (of 255) to clip min/max values.  0.1 works well for slide scans within uneven background.
    params.variance = None               # Calibrated units if not None.
    params.median_radius = 1             # px.
    params.saturated = 0.30              # %  -- added 2022.03.15
    params.rolling_ball = None           # If value given, will do rolling ball "background subtraction" with this size (px) ball.
    params.threshold_method = 'Minimum' # Any Auto Threshold method.
    params.fill_holes = True             # Fill holes in thresholded binary image.
    params.watershed_weight = 5          # Empirically determined.
    params.roi_merge_threshold = 5 # 35      # Pixel cutoff for merging adjacent ROIs.
    params.minimum_obj_size = 0.2        # Percentage of largest object size.
    params.remove_edge = True            # Remove objects touching image edge.
    params.add_center = False            # Add central coordinate to coords (implies coords will be used).
    params.mask_edge_buffer = 25         # Calibrated units.
    params.smooth = 10 #0                   # Calibrated units.
    params.review = True #False                # Review mask objects before committing.
    params.separate = False              # Return individual ROIs as list rather than merged into single ROI.
    params.invert = False                # Invert mask before returning.
    params.custom_params = ''            # Placeholder string for retaining GUI prefs.
    params.final_action = 'Add as ROI'   # Placeholder string for retaining GUI prefs.
    params.flatten = True                # Return ROI instead of list (if only one).
    params.roi_color = 'red'             # Color of displayed ROI outlines.  Must be a java.awt.Color keyword.
    params.roi_stroke = 3                # Width of displayed ROI outlines.
    params.overlay_alpha = 50            # Transparency of displayed overlays.
    return mod_mask_params(params, **kwargs)


def mod_mask_params(params, **kwargs):
    """ Override defaults of mask params.
        TODO: Might generalize this to any kind of pref in future...
    """
    # Override defaults. 
    for kw in kwargs:
        if not hasattr(params, kw):
            logerror(AttributeError, '[ %s ] is not a valid mask_params attribute!' % kw)
        setattr(params, kw, process_str(kwargs[kw]))
    return params


def request_mask_params_gui(show_final_action=True, **kwargs):
    """ GUI to get mask parameters from user.
    """

    # Get mask parameters.
    params =  mod_mask_params(replace_attributes_from_prefs(init_mask_params(), 'segmentation'), **kwargs)
    test_thresholds = False

    # Show dialog w/ options.
    dlg = GenericDialog('Image Masker')
    dlg.addChoice('Background:', ['black', 'white'], params.background_color)
    dlg.addChoice('Null space:', ['none', 'both', 'white', 'black'], params.null_detect)
    #dlg.setInsets(0, 120, 0)
    #dlg.addCheckbox('Border only?', params.null_border)
    #dlg.setInsets(10, 0, 0)
    #dlg.addChoice('Threshold Method:', AutoThresholder.getMethods(), params.threshold_method)
    dlg.addChoice('Threshold Method:', AT_METHODS, params.threshold_method)
    #dlg.setInsets(20, 0, 0)
    dlg.addNumericField('Clip:', params.clip_percent * 100, 0, 3, '%')
    dlg.addNumericField('Pad:', params.mask_edge_buffer, 0, 3, 'um (px if not calibrated)')
    dlg.addNumericField('Smooth:', params.smooth, 0, 3, 'um (px if not calibrated)')
    #dlg.setInsets(20, 20, 0)
    dlg.addCheckbox('Remove edge objects?', params.remove_edge)
    dlg.addCheckbox('Prioritize center?', params.add_center)
    dlg.addCheckbox('Review objects?', params.review)
    dlg.setInsets(10, 0, 0)
    dlg.addStringField('Custom Params:', params.custom_params, 20)
    if show_final_action:
        dlg.setInsets(20, 0, 0)
        dlg.addChoice('With result ...', ['Mask Object(s) [black]', 'Mask Object(s) [white]', 'Add as ROI', 'Add as Overlay', 'List Individual ROIs'], params.final_action)
    dlg.enableYesNoCancel('Mask Image', 'Test Threshold Methods')
    # Make buttons easier to distinguish (sometimes switch places on different platforms).
    buttons = dlg.getButtons()
    buttons[0].setBackground(Color(200, 255, 200))  # Yes
    buttons[1].setBackground(Color(255, 200, 200))  # Cancel
    buttons[2].setBackground(Color(200, 200, 255))  # No
    dlg.showDialog()
    if dlg.wasCanceled():
        return None
    elif not dlg.wasOKed():
        test_thresholds = True

    # Grab settings.
    params.background_color = dlg.getNextChoice()
    params.null_detect = process_str(dlg.getNextChoice())  # Converts 'none' to None.
    #params.null_border = dlg.getNextBoolean()
    params.threshold_method = dlg.getNextChoice()
    params.clip_percent = dlg.getNextNumber() / 100.
    params.mask_edge_buffer = dlg.getNextNumber()
    params.smooth = dlg.getNextNumber()
    params.remove_edge = dlg.getNextBoolean()
    params.add_center = dlg.getNextBoolean()
    params.review = dlg.getNextBoolean()
    params.custom_params = dlg.getNextString()
    if show_final_action:
        params.final_action = dlg.getNextChoice()
        params.separate = params.final_action.endswith('ROIs')
    
    # Parse custom parameters, if any.
    # Note: Overrides other settings.
    # TODO: Generalize this!
    try:
        custom_params = {k:v for item in params.custom_params.split(',') if any(item) for k,v in [item.strip().split('=')]}
        ## Convert any numeric strings to floats, 'True'/'False' to bools.
        #for key in custom_params:
        #    val = custom_params[key]
        #    if is_num(val):
        #        custom_params[key] = float(val)
        #    elif val.lower() == 'true':
        #        custom_params[key] = True
        #    elif val.lower() == 'false':
        #        custom_params[key] = False
        #    elif val.lower() == 'none':
        #        custom_params[key] = None
        params = mod_mask_params(params, **custom_params)
    except ValueError:
        # Secret trick to reset parameters to sourcecode defaults.
        if params.custom_params.lower().startswith('reset'):
            logmsg('Segmentation preferences have been reset to defaults!')
            params = init_mask_params()
        else:
            logerror(ValueError, 'Invalid mask parameter key/value pair!', True)

    # Save params in IJ prefs.
    save_attributes_as_prefs(params, 'segmentation', PREFS_LIST)

    # Override threshold method if we are testing thresholds.
    if test_thresholds:
        params.threshold_method = '[Try all]'
    
    return params


def mask_image(source=None, cal=None, nullzone=None, coords=None, params=None, **kwargs):
    """ Isolate center object in image using auto-thresholding, opening, and watershed operations.
        If coordinates are provided, keep all elements that enclose at least one coordinate, otherwise keep center object.
        Note: Requires MorphoLibJ to be installed!!
        
        Returns a list of ROIs and final PARAMS for each slice.
    """
    # Tweak mask parameters if additional arguments provided.
    if not params:
        params = init_mask_params(**kwargs)
    else:
        params = mod_mask_params(params, **kwargs)
    
    final_rois = []
    final_used_params = []

    # Were we given an ImagePlus?
    # Need to check for Composite, Hyperstack, etc.
    try:
        if not cal:
            cal = source.getCalibration()
        orig_comp_mode = source.getCompositeMode()
        orig_position = (source.getC(), source.getZ(), source.getT())  # Save settings in case open image.
        
        # TODO: Maybe find a way to multithread this after parameters are set?
        # Loop through slices/frames if we have a stack.
        prog_100 = source.getNSlices() * source.getNFrames()
        for z in range(source.getNSlices()):
            for t in range(source.getNFrames()):
                IJ.showProgress((z+1)*(t+1), prog_100)
                source.setPositionWithoutUpdate(1, z+1, t+1)
                if source.isComposite():
                    source.setMode(source.COMPOSITE)  # Save settings in case open image.
                    tmp = ColorProcessor(source.getImage())
                else:
                    tmp = source.getProcessor()
                # Call function with specific processor/calibration.
                rois, used_params = mask_processor(source=tmp, cal=cal, nullzone=nullzone, coords=coords, params=params)
                if rois is None:
                    return rois, used_params  # User canceled.
                # Add slice position to stored metadata (params may differ between slices).
                used_params += ',slice_position=%d_%d_%d' % (1, z+1, t+1)
                # Store stack positions.
                for roi in rois:
                    roi.setPosition(source)
                final_rois += rois
                final_used_params.append(used_params)
        
        # Restore settings in case open image.
        source.setPosition(*orig_position)
        if orig_comp_mode > 0:
            source.setMode(orig_comp_mode)

    # Or maybe we were given an ImageProcessor?  (Would fail at .getCalibration())
    except AttributeError:
        final_rois, used_params = mask_processor(source=source, cal=cal, nullzone=nullzone, coords=coords, params=params)
        final_used_params.append(used_params)
        if final_rois is None:
            return final_rois, used_params  # User canceled.
    
    # Flatten if requested.
    if params.flatten:
        if len(final_rois) == 1:
            return final_rois[0], final_used_params[0]
        # Or no ROIs detected.
        elif not final_rois:
            return None, final_used_params[0]
        # Or, couldn't flatten.
        logmsg('Multiple ROIs in mask, cannot flatten!')
    return final_rois, final_used_params


def mask_processor(source=None, cal=None, nullzone=None, coords=None, params=None, **kwargs):
    """ Isolate center object in processor using auto-thresholding, opening, and watershed operations.
        If coordinates are provided, keep all elements that enclose at least one coordinate, otherwise keep center object.
        Note: Requires MorphoLibJ to be installed!!
        
        Return a list of ROIs and final PARAMS.
    """
    # Tweak mask parameters if additional arguments provided.
    if not params:
        params = init_mask_params(**kwargs)
    else:
        params = mod_mask_params(params, **kwargs)
    #final_roi = []
    
    # For debugging.
    if not source:
        source = IJ.getImage().getProcessor()
        nullzone = IJ.getImage().getRoi()
        cal = IJ.getImage().getCalibration()

    # Double check that calibration is real (i.e., not 1pxx1px).
    if cal and not cal.scaled():
        cal = None
    
    # Set up potentially downsampled ImagePlus.
    ip = source.convertToByteProcessor(True)  # Convert to 8bit, allow scaling to deal with 16bit, etc.
    ip.setRoi(None)  # Just in case.
    sf = 1.0
    if cal:
        sf = min([params.downsample_calibration * cal.pixelWidth, sf])  # Don't upscale.
    w = int(round(ip.getWidth() * sf))
    sfx = 1.0 * w / ip.getWidth()  # Correct for rounding.
    h = int(round(ip.getHeight() * sf))
    sfy = 1.0 * h / ip.getHeight()  # Correct for rounding.
    ip = ip.resize(w, h, params.downsample_aliasing)  # Disabled averaging by default, was producing occasional edge artifacts. -- FIXED 21.07.20 -- Made parameter 22.03.10
    if params.review:
        dup_ip = ip.duplicate()  # Will need it later.
        if coords:
            dup_coords = [p for p in coords]
        else:
            dup_coords = coords
        try:
            dup_nullzone = ShapeRoi(nullzone)
        except:
            dup_nullzone = nullzone
    imp = ImagePlus('tmp', ip)
    cal2 = imp.getCalibration()
    if cal:
        cal2.pixelWidth = cal.pixelWidth / sfx
        cal2.pixelHeight = cal.pixelHeight / sfy
        cal2.setUnit(cal.getUnit())
        imp.setCalibration(cal2)
    
    # Downsample input coords if necessary.
    if coords and sf < 1.0:
        coords = [Point(int(round(p.x * sfx)), int(round(p.y * sfy))) for p in coords]
    elif coords is None:
        coords = []
    
    # Downsample input nullzone if necessary.
    if isinstance(nullzone, Roi) and sf < 1.0:
        nullzone = resize_calibrated_roi(cal, cal2, nullzone)
    
    if params.debug == 'downsample':
        imp.show()
        raise
    
    # If background is white, invert image.
    null_detect = params.null_detect  # Copy to allow modification below. -- fixed 2021.05.24
    if params.background_color.lower() == 'white':
        ip.invert()
        imp.updateImage()
        # Also need to update null color if not none/both -- fixed 2021.03.08.
        if params.null_detect == 'white':
            null_detect = 'black'
        elif params.null_detect == 'black':
            null_detect = 'white'
    
    # UPDATE 21.07.08
    # Discovered that if "black" is not set in binary options, Fill Holes,
    # and possibly other operations, will fail spectacularly here...
    IJ.run("Options...", "black do=Nothing")
    
    # Remove white/black borders, if requested.
    if null_detect:
        if params.null_border:
            roi = isolate_null_border(imp, background=null_detect, return_null=True, alias_edge=params.alias_edge, pad_percent=params.pad_percent)
        else:
            roi = isolate_null(imp, background=null_detect, return_null=True, alias_edge=params.alias_edge, pad_percent=params.pad_percent)
        if params.debug == 'null':
            imp.setRoi(roi)
            imp.show()
            raise
        if roi:
            ip.setValue(0)
            ip.fill(roi)
            imp.updateImage()
            nullzone = invert_roi(roi, imp)
    
    # Option to filter out potential "null" space from TrakEM2 (black) from next steps.
    # If not provided, invoke with False / [] / ''.
    if not nullzone and nullzone is not None:
        ip.setThreshold(0, 0, False)
        nullzone = ThresholdToSelection().convert(ip)
        nullzone = invert_roi(nullzone, w, h)
    if params.debug == 'nullzone':
        imp.show()
        imp.setRoi(nullzone)
        raise
        
    # Median filter.  -- previously was before Autho Threshold step.
    IJ.run(imp, 'Median...', 'radius=%d' % params.median_radius)
    if params.debug == 'median':
        imp.show()
        raise
    
    # Normalize contrast.
    imp.setRoi(nullzone)
    IJ.run(imp, 'Enhance Contrast...', 'saturated=%0.4f normalize' % params.saturated)  # 2022.03.15 -- Change from 0.3 to 0.30 due to ContrastEnhancer.java bug that I found!  (fixed in IJ 1.53q8)
    imp.setRoi(None)
    if params.debug == 'contrast':
        imp.show()
        raise

    # Clip min/max values to filter histogram.
    cp = params.clip_percent
    if is_num(cp):
        cp = [cp, cp]
    cp = [int(round(item * 255)) for item in cp]
    ip.min(cp[0])
    ip.max(255 - cp[1])
    imp.updateImage()
    if params.debug == 'clip':
        imp.show()
        raise
    
    # Use optional variance filter to deal with variable background.
    if params.variance:
        vmp = imp.duplicate()
        IJ.run(vmp, 'Variance...', 'radius=%d' % cal2.getRawX(params.variance))
        IJ.run(vmp, 'Auto Threshold', 'method=%s white' % params.threshold_method)
        #IJ.run(vmp, 'Options...', 'iterations=%d count=1 black pad do=Erode' % math.floor(cal2.getRawX(params.variance) / 2))
        vp = vmp.getProcessor().convertToFloatProcessor()
        vp.multiply(1.0 / 255)
        imp.getProcessor().copyBits(vp, 0, 0, Blitter.MULTIPLY)
    if params.debug == 'variance':
        imp.show()
        raise
    
    # Rolling ball background subtraction.
    if params.rolling_ball:
        IJ.run(imp, 'Subtract Background...', 'rolling=%f' % params.rolling_ball)
    if params.debug == 'rolling':
        imp.show()
        raise
    
    if params.debug == 'pre_threshold':
        imp.show()
        raise

    # Auto threshold.
    #imp.setRoi(nullzone)  # TODO ?
    IJ.run(imp, 'Auto Threshold', 'method=%s white' % params.threshold_method)
    imp.setRoi(None)
    
    # Check if we are testing threshold methods.  If so, return result and quit.
    if params.threshold_method == '[Try all]':
        return None, None #attributes_to_string(params)
    
    if params.debug == 'post_threshold':
        imp.show()
        raise

    # Fill holes.
    if params.fill_holes:
        IJ.run(imp, 'Fill Holes', '')

    # Run distance transform watershed to separate loosely connected objects.
    dist = BinaryImages.distanceMap(ip, ChamferWeights.CHESSKNIGHT.getShortWeights(), True)  # CHESSBOARD
    dist.invert()
    ip = ExtendedMinimaWatershed.extendedMinimaWatershed(dist, ip, params.watershed_weight, 4, 16, False)

    if params.debug == 'watershed':
        ImagePlus('watershed', ip).show()
        raise

    # Extract ROIs
    rois = []
    for i in range(1, int(ip.getMax())+1):
        ip.setThreshold(i, i, False)
        tmp_roi = ThresholdToSelection().convert(ip)
        if tmp_roi:
            rois.append(tmp_roi)

    if params.debug == 'watershed_thresholded':
        imp.setRoi(xor_rois(*rois))
        imp.show()
        raise
    #review_rois(dup_ip, source, cal, rois, [True]*len(rois), params)  # Debugging.
    
    # Merge ROIs that share an extended border (false split from watershed algo).
    if params.remove_edge:
        rois = merge_adjacent_rois(rois, th=params.roi_merge_threshold, ip=ip)
    else:
        rois = merge_adjacent_rois(rois, th=params.roi_merge_threshold)
    nr = len(rois)
    
    if params.debug == 'roi_merge':
        imp.setRoi(xor_rois(*rois))
        imp.show()
        raise
    
    # Filter ROIs based on size and/or touching edges (if more than one ROI).
    flags = [True] * nr
    if nr > 1:
        if params.minimum_obj_size > 0:
            areas = [roi_area(roi, ip) for roi in rois]
            area_cutoff = max(areas) * params.minimum_obj_size  # Percentage.
            for i,area in enumerate(areas):
                if area < area_cutoff:
                    flags[i] = False
        if params.remove_edge:
            for i,roi in enumerate(rois):
                if on_edge(roi, w, h):
                    flags[i] = False

    # Add center coordinate, if requested.
    if params.add_center:
        coords.append(Point(w/2, h/2))

    # Filter ROIs by overlap with provided coordinates, if any.
    if coords:
        for i,roi in enumerate(rois):
            flags[i] = any([roi.contains(p.x, p.y) for p in coords])

    # Manual review/override of ROIs if selected.
    if params.review:
        rois, flags = review_rois(dup_ip, source, cal, rois, flags, params, dup_nullzone, dup_coords)
        # While not the cleanest syntax, this next bit is a way to abort the current
        # function for one of two reasons: user aborted during review (returned None), or
        # user tried another threshold method, in which case another iteration of this
        # function was invoked and we need to return its result... either way, that result
        # was returned to the "flags" variable.
        if rois is None:
            return flags
    
    # Keep only flagged ROIs.
    rois = [roi for roi, flag in zip(rois, flags) if flag]
    
    if params.debug == 'pre_resize':
        imp.setRoi(xor_rois(*rois))
        imp.show()
        raise
    
    # Resize ROIs pt 1
    if params.mask_edge_buffer > 0:
        for i,roi in enumerate(rois):
            roi = RoiEnlarger.enlarge(roi, cal2.getRawX(params.mask_edge_buffer) * 2.0)
            roi = RoiEnlarger.enlarge(roi, -cal2.getRawX(params.mask_edge_buffer))
            rois[i] = roi
    
    if params.debug == 'pre_upsample':
        o = Overlay()
        for roi in rois:
            o.add(roi)
        imp.setOverlay(o)
        imp.show()
        raise
    
    # Resize ROIs pt 2
    for i,roi in enumerate(rois):
        if cal:
            roi = resize_calibrated_roi(cal2, cal, roi)
        if params.smooth > 0:
            if cal:
                roi = smooth_roi(roi, cal.getRawX(params.smooth))
            else:
                roi = smooth_roi(roi, params.smooth)
        rois[i] = roi
    
    # Merge ROIs if required (but keep as a list).
    if rois and not params.separate:
        rois = [merge_rois(*rois)]
    
    # Return, inverted if required.
    if params.invert:
        return [invert_roi(roi, source) for roi in rois], attributes_to_string(params)
    else:
        return rois, attributes_to_string(params)


def isolate_null(imp, background='both', th_min=0, th_max=255, return_null=True, alias_edge=2, pad_percent=0):
    """ Isolate null black and/or white regions.
        These are often non-imaged regions from a non-rectangular slide scan.
        
        TH_MIN/TH_MAX: Custom designation of 'pure' black/white based on bit depth.
        RETURN_NULL: If True, returns Roi of blank area.  If false, Roi is of image data.
    """
    roi = None
    # Get processor.
    ip = imp.getProcessor()
    # Compute amount of value padding.
    pad = (th_max - th_min) * pad_percent
    # Grab black and/or white background.
    if background.lower() == 'black' or background.lower() == 'both':
        ip.setThreshold(th_min, th_min+pad, False)
        roi = ThresholdToSelection.run(imp)
    if background.lower() == 'white' or background.lower() == 'both':
        ip.setThreshold(th_max-pad, th_max, False)
        if background.lower() == 'white':
            roi = ThresholdToSelection.run(imp)
        else:
            roi = merge_rois(roi, ThresholdToSelection.run(imp))
    ip.resetThreshold()
    # Try to catch aliased edges.
    if roi and alias_edge:  # Fixed to catch empty ROIs -- 21.05.24
        roi = ShapeRoi(RoiEnlarger.enlarge(roi, alias_edge))  # Fixed 22.03.10 -- Force to ShapeRoi or else "and" in next step will fail.
        roi = roi.and(ShapeRoi(Roi(0, 0, imp.getWidth(), imp.getHeight())))  # Added step to limit ROI to bounds of image -- 21.07.20
    if return_null:
        return roi
    else:
        return invert_roi(roi, imp)


def isolate_null_border(imp, background='both', th_min=0, th_max=255, return_null=True, alias_edge=2, pad_percent=0):
    """ Isolate null black and/or white regions that touch the edge of the image.
        These are often non-imaged regions from a non-rectangular slide scan.
        
        TH_MIN/TH_MAX: Custom designation of 'pure' black/white based on bit depth.
        RETURN_NULL: If True, returns Roi of blank area.  If false, Roi is of image data.
    """
    roi = isolate_null(imp, background=background, th_min=th_min, th_max=th_max, return_null=True, alias_edge=alias_edge, pad_percent=pad_percent)
    if not roi:  # Fixed to catch empty ROIs -- 21.05.24
        return roi
    bounds = roi.getBounds()  # Get surrounding box.  Should generally be same
                              # as 'Auto Crop' result for this slice with black.
    # Initialize final ROI, from which we will whittle away edges.
    # Must be a ShapeRoi so that we can use XOR operations.
    final_roi = ShapeRoi(Roi(0, 0, imp.getWidth(), imp.getHeight()))
    # Now, we want to find everything that is 'empty' within this boundary, and 
    # exclude any patches that touch the boundary.  Generally, this will 
    # preserve any "oversaturated" pixels within the source image.. however, 
    # saturated regions along edges will thereby become excluded.  Can't think of 
    # a way to identify such regions without a lot of pain and suffering...
    if roi and isinstance(roi, ShapeRoi):
        rois = sorted(roi.getRois(), key=lambda x: -roi_bounds_area(x))  # Sort ROIs by size, biggest first.
        # Important but confusing test!  Need to find out if largest ROI contains 
        # second-largest ROI.  If yes, then that means we have a complete white 
        # border around image, and this must be treated as a special case.
        # Test if second-largest ROI is within largest ROI.
        if len(rois) > 1 and contains_all(rois[0], rois[1]):  # Fixed 22.03.10 -- Only test if there are >1 rois!
            # Create ROI of _just_ the border region (within parens), and exclude from final ROI.
            final_roi = xor_rois(final_roi, rois[0], merge_rois(*rois[1:])) #.xor(ShapeRoi(rois[0]).xor(merge_rois(*rois[1:])))
            del rois[0:1]
        for r in rois:  # Test each ROI to see if it touches border of bounds.
            b = r.getBounds()  # Get bounds of ROI.
            if (b.x == bounds.x  # Test left edge.
             or b.y == bounds.y  # Test top edge.
             or b.x+b.width == bounds.x+bounds.width  # Test right edge.
             or b.y+b.height == bounds.y+bounds.height):  # Test bottom edge.
                final_roi.xor(ShapeRoi(r))  # Exclude from final ROI.
    elif roi:  # Might still be a single box on edge, so let's test it.
                  # Pardon the redundancy..
        b = roi.getBounds()  # Get bounds of ROI.
        if (b.x == bounds.x  # Test left edge.
         or b.y == bounds.y  # Test top edge.
         or b.x+b.width == bounds.x+bounds.width  # Test right edge.
         or b.y+b.height == bounds.y+bounds.height):  # Test bottom edge.
            final_roi.xor(ShapeRoi(roi))  # Exclude from final ROI.
    if return_null:
        return invert_roi(final_roi, imp)
    else:
        return final_roi


def review_rois(ip, source, cal, rois, flags, params, nullzone=None, coords=None):
    """ Quick GUI to approve/override automatically segmented ROIs.
    """
    imp = ImagePlus('Review ROIs', ip)
    o = Overlay()
    null = ShapeRoi(Roi(0, 0, imp.getWidth(), imp.getHeight()))
    o.add(null)  # Will replace at end, but need at bottom of stacking.
    # Iterate through ROIs, color according to flag.
    for roi, flag in zip(rois, flags):
        if flag:
            c = Color.RED
        else:
            c = Color.CYAN
        tmp = ShapeRoi(roi)
        null = null.not(tmp)
        tmp.setStrokeColor(c)
        tmp.setStrokeWidth(3)
        o.add(tmp)
        c = Color(c.getRed(), c.getGreen(), c.getBlue(), 63)  # No way to modify existing Color?
        roi.setFillColor(c)  # To have both stroked and filled Overlays, need to add as two separate ROIs.
        o.add(roi)
    # Replace 'bottom' overlay.
    null.setFillColor(Color(0, 0, 0, 191))
    o.set(null, 0)
    imp.setOverlay(o)
    imp.show()
    # Save preference to restore at end.
    orig_tool = IJ.getToolName()
    IJ.setTool('multi-point')
    # Build dialog.
    dlg = NonBlockingGenericDialog('Review ROIs')
    dlg.addMessage('%d of %d detected objects have been selected.' % (sum(flags), len(rois)))
    dlg.addMessage('RED objects will be kept, CYAN objects will be masked.')
    dlg.addMessage('To OVERRIDE, place a marker over each object to keep.')
    dlg.addMessage('Or, DRAW your own custom ROI outline.')
    dlg.setInsets(20, 20, 0)
    #dlg.addChoice('Threshold Method:', AutoThresholder.getMethods(), params.threshold_method)
    dlg.addChoice('Threshold Method:', AT_METHODS, params.threshold_method)
    dlg.enableYesNoCancel('Use Selected ROIs', 'Retry Threshold')
    # Make buttons easier to distinguish (sometimes switch places on different platforms).
    buttons = dlg.getButtons()
    buttons[0].setBackground(Color(200, 255, 200))  # Yes
    buttons[1].setBackground(Color(255, 200, 200))  # Cancel
    buttons[2].setBackground(Color(200, 200, 255))  # No
    dlg.setAlwaysOnTop(True)
    # Position dialog just to right of ImagePlus (overlapping as needed to fit on screen).
    dlg.pack()
    imp_loc = imp.getWindow().getLocation()
    imp_w = imp.getWindow().getSize().width
    screen_w = IJ.getScreenSize().width
    dlg_w = dlg.getSize().width
    dlg_x = min(imp_loc.x + imp_w, screen_w - dlg_w)
    dlg.setLocation(dlg_x, imp_loc.y)
    # Show Dialog.
    dlg.showDialog()
    IJ.setTool(orig_tool)  # Restore tool pref.
    r = imp.getRoi()
    imp.close()
    imp.flush()
    # Return rois and flags, edited if needed.
    if dlg.wasOKed():
        if r and r.getType() == r.POINT:
            for i,roi in enumerate(rois):
                # Note, .containsPoint() weirdly fails sometimes... but .contains() is OK??
                flags[i] = any([roi.contains(p.x, p.y) for p in r.getContainedPoints()])
        elif r and r.isArea():
            # TODO: Could try to split ShapeROIs, but dealing with nested ROIs is a pain, so just return the whole thing.
            rois = [r]
            flags = [True]
        elif r:
            logmsg('User ROI is not a point or closed area--ignored!')
        return rois, flags
    # User Canceled
    elif dlg.wasCanceled():
        return None, (None, None)  # Eh.
    # Redo the masking procedure with same parameters but different thresholder.
    else:
        return None, mask_processor(source, cal=cal, nullzone=nullzone, coords=coords, params=params, threshold_method=dlg.getNextChoice())
    

""" Old masking function, saved for posterity.
"""
default_th = 'Triangle'  # 'MinError(I)' 'Triangle'
default_median_filter = 2.0
default_morpho_radius = 5  # Totally empirically determined...
default_watershed_weight = 60  # Totally empirically determined...
default_rind = 5
default_interp_int = 10
default_smooth = True
def mask_center(ip=None, th=default_th, bg_color='black', nullzone=None, mf=default_median_filter, mr=default_morpho_radius, ww=default_watershed_weight, rind=default_rind, interp_int=default_interp_int, smooth=default_smooth, coords=None):
    """ Isolate center object in image using auto-thresholding, opening, and watershed operations.
        If coordinates are provided, keep all elements that enclose at least one coordinate, otherwise keep center object.
        Note: Requires MorphoLibJ to be installed!!
        Return as ROI.
    """
    if not ip:  # For debugging.
        ip = IJ.getImage().getProcessor().duplicate()
        nullzone = IJ.getImage().getRoi()
    # If background is white, invert image.
    if bg_color.lower() == 'white':
        ip.invert()
    roi = None
    w = ip.getWidth()
    h = ip.getHeight()
    # Filter out potential "null" space from TrakEM2 (black) from thresholder.
    # If not provided, invoke with False / [] / ''.
    if not nullzone and nullzone is not None:
        ip.setThreshold(0, 0, False)
        nullzone = ThresholdToSelection().convert(ip)
        nullzone = invert_roi(nullzone, w, h)
    ip.setRoi(nullzone)
    # Run auto-thresholder.
    ip.setAutoThreshold(AutoThresholder.Method.valueOf(th), True)
    ip.threshold(int(ip.getMinThreshold()-1))
    # Do a median filter to get rid of speckle noise.
    RankFilters().rank(ip, mf, RankFilters.MEDIAN)
    # Perform opening using MorphoLibJ
    strel = Strel.Shape.DISK.fromRadius(mr)
    ip = strel.opening(ip)
    # Fill Holes
    bin = Binary()
    bin.setup('fill', None)
    bin.run(ip)
    # Run distance transform watershed to separate loosely connected objects.
    dist = BinaryImages.distanceMap(ip, ChamferWeights.CHESSBOARD.getShortWeights(), True)
    dist.invert()
    ip = ExtendedMinimaWatershed.extendedMinimaWatershed(dist, ip, ww, 4, 16, False)
    # Extract ROIs
    rois = []
    for i in range(1, int(ip.getMax())+1):
        ip.setThreshold(i, i, False)
        tmp_roi = ThresholdToSelection().convert(ip)
        if tmp_roi:
            rois.append(tmp_roi)
    if rois:
        r_tmp = None
        if coords:
            areas = [0] * len(rois)  # Dummy var.
        else:
            # Center coordinate.
            coords = [(w / 2.0, h / 2.0)]
            areas = [roi_bounds_area(r) for r in rois]
        mean_area = sum(areas) / len(areas)
        for r, a in zip(rois, areas):
            # Warning, coonvoluted logic ahead!
            # Keep roi if it is the only one,
            # OR if it contains a coordinate point,
            # OR it is sufficiently large AND does not touch edge.
            # NOTE: DIV by 8 is arbitrary!
            b = r.getBounds()
            if (len(rois) == 1 or
                any([r.containsPoint(cx,cy) for cx,cy in coords]) or
                (a >= mean_area/8 and b.x > 0 and b.y > 0 and (b.x+b.width) < w and (b.y+b.height) < h)):
                if r_tmp is None:
                    r_tmp = ShapeRoi(r)  # Start roi.
                else:
                    r_tmp = r_tmp.xor(ShapeRoi(r))  # Add to roi.
        if r_tmp:
            # Simplify roi.
            r2 = RoiEnlarger.enlarge(r_tmp, rind)
            # If enlargement results in a composite roi, need to smooth each element individually.
            # A little messy, might be possible to simplify?
            if r2.getType() == r2.COMPOSITE:
                for r3 in r2.getRois():
                    poly = r3.getInterpolatedPolygon(-1*interp_int, smooth)
                    if poly.npoints < 3:  # Interpolated out of existence!
                        continue
                    if roi is None:
                        roi = ShapeRoi(PolygonRoi(poly, Roi.POLYGON))
                    else:
                        roi = roi.xor(ShapeRoi(PolygonRoi(poly, Roi.POLYGON)))
            else:
                poly = r2.getInterpolatedPolygon(-1*interp_int, smooth)
                roi = PolygonRoi(poly, Roi.POLYGON)
            roi = invert_roi(roi, w, h)
    return roi