# Create image stack based on TrakEM2 transformations, but using source 16-bit confocal images.
# muniak@ohsu.edu
# 2024.11.06 - output verified for manuscript.

# Custom script path (must contain rothetal_pkg folder).
PKG_PATH = r'<<FILEPATH_TO_SCRIPTS>>'

# CUSTOMIZED HACK OF create_raw_hyperstack2.py TO SPECIFICIALLY USE RRJD FILES!
# scripts/trakem2/create_raw_hyperstack2.py
# v.2021.06.02
# m@muniak.com
#
# Script to create a stack/hyperstack in FIJI of the raw source material for a TrakEM2 project
# (e.g., 16-bit TIFs or CZIs) cropped and transformed based on TrakEM2 adjustments to corresponding patches.
#
# Because script parameters cannot be set programatically, the layer range cannot be customized to each project.
# Therefore: 0 == first layer, and -1 == last layer in project range.  Leave these values to export entire layerset.

# <2024.11.06> - SCRIPT PARAMETERS NOT USED IN THIS VERSION, SO THEY HAVE AN EXTRA COMMENT '#' TO DISABLE...
##@ String (label="Raw extension:", value="czi") ext
##@ Boolean (label="Split channels into separate images?", description="Split", value=False, persist=true) do_split
##@ Integer (label="First layer:", value=0, persist=true) first_index
##@ Integer (label="Last layer:", value=-1, persist=true) last_index
##@ Boolean (label="Insert missing layers?", description="Insert missing layers", value=False, persist=true) insert_missing
##@ Boolean (label="Clear outside ROI?", description="Clear outside ROI", value=False, persist=true) clear_outside
##@ Boolean (label="Display ROI?", description="Display ROI", value=True, persist=true) display_roi
##@ Boolean (label="Include alpha mask?", description="Alpha Mask", value=True, persist=true) incl_alpha_mask
##@ String (choices={"Original", "RGB", "RGB > Gray8"}, style="listBox", value="Output Type", value="Original", persist=true) output_type
##@ String (label="CZI suffix pattern:", value="", persist=true) czi_suffix
##@ Integer (label="Series offset:", value=1, persist=true) series_offset
##@ Integer (label="Output level:", value=8, persist=true) output_res_level
##@ Integer (label="Background value:", value=255, persist=true) background_val

n_threads = 16  # For multithreading layer extraction.

#ii = 8 # FOR HI-RES CASES 2-4 -- limited memory issue

if True:  # For debugging.
    ext = 'tiff?'#'czi'#
    do_split = False
    first_index = 0 #12 #
    last_index = -1 #-1 #12 #
    #first_index = (ii*n_threads) # FOR HI-RES CASES 2-4
    #last_index = ((ii+2)*n_threads)-1 # FOR HI-RES CASES 2-4
    insert_missing = False
    clear_outside = False
    display_roi = True
    incl_alpha_mask = True
    output_type = 'Original' #'RGB' #
    czi_suffix = '__RGB__x' #'__s__x' #
    series_offset = 1
    output_res_level = 1
    background_val = 0

FNAME_FIX = '.ome'  # <-- may be necessary for some folders with original confocal images
#FNAME_FIX = '__relevel'  # <-- for releveled image folders

force_rgb = output_type.startswith('RGB')
force_rgb_8bit = output_type.endswith('Gray8')
if force_rgb_8bit:
    force_rgb = True

import os
import re
import sys
from ij import IJ
from ij import CompositeImage
from ij import ImagePlus
from ij import ImageStack
from ij.io import DirectoryChooser
from ij.gui import GenericDialog
from ij.gui import Roi
from ij.gui import ShapeRoi
from ij.plugin import ChannelSplitter
from ij.plugin.filter import ThresholdToSelection
from ij.process import Blitter
from ij.process import ByteProcessor
from ij.process import ColorProcessor
from ij.process import FloatProcessor
from ij.process import ShortProcessor
from ij.process import StackConverter
from ini.trakem2.display import Patch
from java.awt import Rectangle
from java.awt.geom import AffineTransform

sys.path.insert(0, PKG_PATH)
from rothetal_pkg.fiji import t2
from rothetal_pkg.fiji.bioformats import open_czi
from rothetal_pkg.fiji.calibration import scale_calibration
from rothetal_pkg.fiji.multithread import multi_task
from rothetal_pkg.fiji.roi import get_real_float_bounds
from rothetal_pkg.fiji.roi import scale_roi
from rothetal_pkg.fiji.roi import transform_roi
from rothetal_pkg.fiji.utils import find_files_by_ext
from rothetal_pkg.fiji.utils import logerror
from rothetal_pkg.fiji.utils import logmsg

# Attempt to load imagescience modules -- not loaded in FIJI by default, must be selected in updater!
try:
    from imagescience.image import Axes
    from imagescience.image import Image
    from imagescience.transform import Affine
    from imagescience.transform import Transform
except ImportError as e:
    logerror(ImportError, '"ImageScience" library must be loaded to use this script!', True)

def create_raw_hyperstack3(ext, do_split, first_index, last_index):
    # Do we have an open project?
    display = t2.get_display()
    if not display:
        return

    # Get project details.
    project = display.getProject()
    layerset = display.getLayerSet()
    cal = layerset.getCalibrationCopy()
    loader = project.getLoader()
    project_path = loader.getParentFolder()
    
    # Check project calibration.
    if cal.pixelWidth != cal.pixelHeight:
        logmsg('Check calibration aspect ratio!', True)
        return
    
    # Get layers to process.
    layers = layerset.getLayers()
    if last_index == -1: last_index = len(layers)
    else: last_index += 1
    layers = layers[first_index:last_index]

    # Check if we need to temporarily insert missing layers.
    tmp_layers = []
    if insert_missing:
        z1 = int(cal.getRawZ(cal.getX(layers[0].getZ())))
        z2 = int(cal.getRawZ(cal.getX(layers[-1].getZ())))
        for i in range(z1,z2+1):
            if not layerset.getLayer(cal.getRawX(cal.getZ(i))):
                tmp_layers.append(t2.add_layer(cal.getZ(i)))  # Add by section m value.
        layers = sorted(layers+tmp_layers, key=lambda l: l.getZ())
    
    # Construct raw.ext dict by recursively searching project path.
    raw_files = find_files_by_ext(project_path, ext, splitext=True)
    
    # Regex for matching multiple series' from CZI slide scans.
    if czi_suffix:
        do_series = 's' in czi_suffix
        regex = re.compile('(.*)' + czi_suffix.replace('s','([0-9]+)').replace('x','x([0-9]+)')).match
        series_map = {}
        input_res_level = None

    # Go through all patches in selected range and map to raw files.
    patches = [patch for layer in layers for patch in layer.getDisplayables(Patch)]
    patches_map = {}
    for patch in patches:
        key,_ = os.path.splitext(os.path.basename(patch.getImageFilePath()))
        if czi_suffix:
            rmatch = regex(key)
            key = rmatch.group(1)
            if do_series:
                series_map[patch] = int(rmatch.group(2)) - int(series_offset)
                res_group = 3
            else:
                series_map[patch] = 0
                res_group = 2
            if not input_res_level:
                input_res_level = int(rmatch.group(res_group))
            elif input_res_level != int(rmatch.group(res_group)):
                logmsg('WARNING! %s has a different res level (x%d) than other project files (x%d) ...' % (int(rmatch.group(3)), input_res_level))
        while patch not in patches_map:
            try: patches_map[patch] = raw_files[key + FNAME_FIX]
            except KeyError:
                dlg = GenericDialog('Missing file...')
                dlg.addMessage('Raw file for [ %s ] not found in search path, add another location?' % patch.getTitle())
                dlg.enableYesNoCancel()
                dlg.showDialog()
                if dlg.wasOKed():
                    DirectoryChooser.setDefaultDirectory(project_path)
                    extra_path = DirectoryChooser('Choose folder with raw image files.').getDirectory()
                    if extra_path:
                        raw_files = find_files_by_ext(extra_path, ext, splitext=True, d=raw_files)
                elif dlg.wasCanceled():
                    return
                else:
                    patches_map[patch] = None
    
    # Check file(s) type, if composite, and number of color channels (based on first file in list).
    # Note: MAJOR assumption that all files are the same in this regard (i.e., no mixing of file types/channel numbers).
    is_czi = True if ext == 'czi' else False
    is_rgb = False
    test_raw = next(item for item in patches_map.values() if item is not None)
    if is_czi:  # Special opener for CZIs.
        is_composite = True
        tmp, luts = open_czi(test_raw, crop=Rectangle(0, 0, 1, 1))
        n_colors = len(luts)
    else:  # Assumed normal file types (TIF, PNG, JPG, etc.)
        tmp = IJ.openImage(test_raw)
        if tmp.isComposite():
            is_composite = True
            luts = tmp.getLuts()
            n_colors = len(luts)
        else:
            is_composite = False
            n_colors = 1
    orig_cal = tmp.getCalibration()  # This should return calibration of the original resolution image, not downsampled.
    max_range = tmp.getDisplayRangeMax()  # For resetting display range below--should catch 12bit images?
    tmp.close()
    tmp.flush()
    
    # If we are dealing with non-composite files, actually need to check them all and see if ANY are RGB.
    if not is_composite:
        for raw_path in patches_map.values():
            tmp = IJ.openImage(raw_path)
            is_rgb = tmp.getType() == ImagePlus.COLOR_RGB
            tmp.close()
            tmp.flush()
            if is_rgb: break
    
    # Grab ROI we want to export.
    target_roi_orig = display.getRoi()
    if target_roi_orig:
        target_roi = ShapeRoi(target_roi_orig).and(ShapeRoi(layerset.get2DBounds()))  # Just in case ROI went beyond layerset bounds.
    else:
        target_roi = ShapeRoi(layerset.get2DBounds())
    target_bounds = get_real_float_bounds(target_roi)
    target_bounds_int = target_roi.getBounds()

    # Determine output scale factor (res level of files in TrakEM2 project vs. desired output res level).
    sf = 1.0
    if czi_suffix:
        sf = float(input_res_level) / float(output_res_level)
        logmsg('Using scaling factor of %0.1f to map CZIs from x%d -> x%d ...' % (sf, input_res_level, output_res_level))
    target_roi_on_final = scale_roi(transform_roi(target_roi, AffineTransform.getTranslateInstance(target_bounds.x, target_bounds.y)), sf)
    
    # Initialize final image stack.
    w = int(target_bounds_int.width * float(input_res_level) / float(output_res_level))
    h = int(target_bounds_int.height * float(input_res_level) / float(output_res_level))
    if force_rgb:
        n_colors = 1  # We will convert images to RGB immediately after extracting to save memory.
        if not force_rgb_8bit:
            is_rgb = True
    final_stack = ImageStack(w, h, len(layers)*n_colors)

    def extract_layer(s, layer):
        """ Sub-method to allow for multithreading.
        """
        # Iterate through layers.
        ip = [None] * n_colors
        # Iterate over patches and transform.
        for patch in layer.getDisplayables(Patch):  # Should be in sorted order from "bottom" to "top".
            if not patch.isVisible(): continue  # Skip hidden images.
            if patches_map[patch] is None: continue  # Skip this image.
            patch_image = patch.createTransformedImage()
            # Affine transform applied to corresponding patch.
            at = patch.getAffineTransformCopy()
            # Map ROI and its bounds from TrakEM2 workspace to source image.
            roi_on_source = scale_roi(transform_roi(target_roi, at), sf).and(scale_roi(Roi(patch_image.box), sf))
            roib_on_source = scale_roi(transform_roi(ShapeRoi(target_bounds), at), sf).and(scale_roi(Roi(patch_image.box), sf))
            bounds_on_source = get_real_float_bounds(roib_on_source)
            # If empty boundary, we have nothing to extract from this page.
            if not bounds_on_source:
                continue
            # Get x/y offset for placement of extracted content.
            bounds_on_display = get_real_float_bounds(transform_roi(scale_roi(roib_on_source, 1.0/sf), at, inverse=False))
            offset_x = bounds_on_display.x - target_bounds.x
            offset_y = bounds_on_display.y - target_bounds.y
            # Make sure crop box doesn't extend beyond bounds of source image.
            bounds_on_source_int = bounds_on_source.getBounds()
            bx = bounds_on_source_int.x
            by = bounds_on_source_int.y
            bw = min(bounds_on_source_int.width, int(patch_image.box.width * sf) - bx)
            bh = min(bounds_on_source_int.height, int(patch_image.box.height * sf) - by)
            # Shift ROI to origin.
            roi_at_origin = transform_roi(roi_on_source, AffineTransform.getTranslateInstance(bx, by))
            roib_at_origin = transform_roi(roib_on_source, AffineTransform.getTranslateInstance(bx, by))
            # Create copy of AffineTransform that is centered on ROI itself.
            at2 = AffineTransform.getTranslateInstance(bw/2.0, bh/2.0)
            at2.concatenate(AffineTransform(at.getScaleX(), at.getShearY(), at.getShearX(), at.getScaleY(), 0, 0).createInverse())
            at2.translate(-bw/2.0, -bh/2.0)
            # Determine offset caused by expansion of canvas due to image rotation.
            bounds_after_transform = get_real_float_bounds(transform_roi(Roi(0, 0, bw, bh), at2))
            # Determine position of ROI and its bounds on extracted image after transform.
            roi_on_extract = transform_roi(roi_at_origin, at2)
            roib_on_extract = transform_roi(roib_at_origin, at2)
            roi_on_extract = transform_roi(roi_on_extract, AffineTransform.getTranslateInstance(bounds_after_transform.x, bounds_after_transform.y))
            roib_on_extract = transform_roi(roib_on_extract, AffineTransform.getTranslateInstance(bounds_after_transform.x, bounds_after_transform.y))
            # Create transform in format suitable for image.
            t = Transform(at.getScaleX(), at.getShearX(), 0, 0,
                          at.getShearY(), at.getScaleY(), 0, 0,
                                       0,              0, 1, 0)
   
            logmsg('Extracting image for %s ...' % patch.getTitle())
            if is_czi:  # Special opener for CZIs.
                if czi_suffix:
                    imp, _ = open_czi(patches_map[patch], crop=Rectangle(bx, by, bw, bh), series=series_map[patch], pyramid=True, res_level=output_res_level)
                else:
                    imp, _ = open_czi(patches_map[patch], crop=Rectangle(bx, by, bw, bh))
            else:
                tmp = IJ.openImage(patches_map[patch])
                tmp.setRoi(Roi(bx, by, bw, bh))
                imp = tmp.crop('stack')
            # Convert to RGB/Gray8 if requested before further manipulations.
            if force_rgb:
                if is_composite:
                    imp = CompositeImage(imp, CompositeImage.COLOR)
                    for c in reversed(range(len(luts))):
                        imp.setChannelLut(luts[c], c+1)
                        imp.setC(c+1)
                        imp.setDisplayRange(0, max_range)
                    imp.setMode(CompositeImage.COMPOSITE)
                    StackConverter(imp).convertToRGB()
                    if force_rgb_8bit:
                        imp.setProcessor(imp.getProcessor().convertToByteProcessor(False))
            mask = patch_image.mask
            if incl_alpha_mask and mask:
                mask.setThreshold(0, 0, False)
                mask_roi = ThresholdToSelection().convert(mask)
                if mask_roi:
                    logmsg('Applying alpha mask to %s ...' % patch.getTitle())
                    mask_roi = scale_roi(mask_roi, sf)
                    mask_roi = transform_roi(mask_roi, AffineTransform.getTranslateInstance(bx, by)).and(ShapeRoi(Rectangle(imp.getWidth(), imp.getHeight())))
                    for ch in range(imp.getNChannels()):
                        imp.setC(ch+1)
                        tip = imp.getProcessor()
                        tip.setValue(0)
                        tip.fill(mask_roi)
            # Apply transform using imagescience module, export ImagePlus, and get ImageStack.
            logmsg('Applying transform to %s ... ' % patch.getTitle())
            tmp = Affine().run(Image.wrap(imp), t, Affine.CUBIC, True, False, False).imageplus().getStack()
            # Adjust roi_on_extract to clip to bounds of image (subpixel rounding errors can cause crop to fail).
            roi_on_extract = ShapeRoi(roi_on_extract).and(ShapeRoi(Roi(0, 0, tmp.getWidth(), tmp.getHeight())))
            roib_on_extract = ShapeRoi(roib_on_extract).and(ShapeRoi(Roi(0, 0, tmp.getWidth(), tmp.getHeight())))
            # Get bounds on extracted image to facilitate final crop.
            bounds_on_extract = get_real_float_bounds(roib_on_extract)
            bounds_on_extract_int = bounds_on_extract.getBounds()
            bex = bounds_on_extract_int.x
            bey = bounds_on_extract_int.y
            bew = min(bounds_on_extract_int.width, tmp.getWidth() - bex)
            beh = min(bounds_on_extract_int.height, tmp.getHeight() - bey)
            # Determine position of ROI after final crop.
            roi_on_final = transform_roi(roi_on_extract, AffineTransform.getTranslateInstance(bex, bey))
            # Crop stack.
            logmsg('Cropping %s ... ' % patch.getTitle())
            stack = tmp.crop(bex, bey, 0, bew, beh, tmp.size())
            # Sanity check if stack size matches expected number of colors.
            if stack.getSize() != n_colors:
                logerror(ValueError, 'Mismatch between image stack size and n_colors...', True)
            # Iterate through stack slices/colors.
            logmsg('Moving %s to final stack ... ' % patch.getTitle())
            for c in range(n_colors):
                # Get processor.
                tmp = stack.getProcessor(c+1)
                if ip[c] is None:
                    # Create blank processor slice for final stack if not already done.
                    if is_rgb:  # Force to RGB-type for non-composite images.
                        ip[c] = ColorProcessor(w, h)
                        bval = (background_val<<16) + (background_val<<8) + (background_val)
                    else:  # Same type.
                        ip[c] = tmp.createProcessor(w, h)
                        bval = background_val
                    ip[c].setValue(bval)
                    ip[c].fill()
                # Clear outside of extract ROI.
                if clear_outside:
                    tmp.setValue(0)
                    tmp.fillOutside(roi_on_final)
                # Insert transformed/cropped image into processor.
                # TODO: Not totally certain about int/round combo...
                ip[c].copyBits(tmp, int(round(max(offset_x * sf, 0))), int(round(max(offset_y * sf, 0))), Blitter.COPY_ZERO_TRANSPARENT)
                ip[c].resetMinAndMax()  # Not sure if needed.
        # If layer was empty, need blank ips.
        for c in range(n_colors):
            if ip[c] is None:
                if is_rgb:
                    ip[c] = ColorProcessor(w, h)
                elif not force_rgb_8bit and max_range > 65535:
                # TODO: Not really the best way to detect a Float...
                    ip[c] = FloatProcessor(w, h)
                elif not force_rgb_8bit and max_range > 255:
                    ip[c] = ShortProcessor(w, h)
                else:
                    ip[c] = ByteProcessor(w, h)
        # Add processors as slices to final stack.
        for c in range(n_colors):
            final_stack.setProcessor(ip[c], (s*n_colors)+1+c)  # 1-indexing for ImageStack.

    # Multi-task layer extraction.
    multi_task(extract_layer, [(s, layer) for s, layer in enumerate(layers)], n_threads=n_threads)

    # Remove any temporary empty layers.
    for layer in tmp_layers:
        project.getLayerTree().remove(layer, False)
    
    # Create ImagePlus of final stack.
    final_imp = ImagePlus(os.path.splitext(project.getTitle())[0], final_stack)
    # Tell FIJI what our dimensions are for hyperstack.
    final_imp.setDimensions(n_colors, len(layers), 1)
    
    # Special handling for composite images to display correctly.
    if is_composite and not force_rgb:
        final_imp = CompositeImage(final_imp, CompositeImage.COLOR)
        # Custom color assignment.
        for c in reversed(range(n_colors)):
            final_imp.setChannelLut(luts[c], c+1)
            final_imp.setC(c+1)
            final_imp.setDisplayRange(0, max_range)
    else:
        final_imp.setDisplayRange(0, max_range)
    
    # Transfer over calibration from TrakEM2 workspace.
    final_imp.setCalibration(scale_calibration(cal, sf))
    
    # Restore ROI in TrakEM2 workspace in case it was removed.
    display.getCanvas().getFakeImagePlus().setRoi(target_roi_orig)
    
    if do_split:
        imps = ChannelSplitter.split(final_imp)
        for i,imp in enumerate(imps):
            imp.setTitle(imp.getTitle() + '__%d' % i)
            if display_roi:
                imp.setRoi(target_roi_on_final)
            imp.show()
        return imps
    else:
        final_imp.show()
        if display_roi:
            final_imp.setRoi(target_roi_on_final)
        return final_imp

imps = create_raw_hyperstack3(ext, do_split, first_index, last_index)
