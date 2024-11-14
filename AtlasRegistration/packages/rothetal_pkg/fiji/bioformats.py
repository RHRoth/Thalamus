# fiji/bioformats.py
# v.2024.01.05
# m@muniak.com
#
# Functions related to BioFormats plugin (processing CZIs, etc.).

# 2024.11.07 - Cleaned up for manuscript deposit.
# 2021.07.21 - Fixed 0 vs. 1 scene indexing w/ newer Bio-Formats update (text display is 1-based, actual files are 0-based).
# 2021.05.17 - Add calibration to get_czi_series_info.
# 2021.08.13 - Fix save_lzw to ACTUALLY save LZW compression by default, doh!
# 2022.02.17 - Fix 'hex' assignment when not found.
# 2022.03.24 - Fix CenterPosition/CenterSize metadata extraction for single series CZIs.
# 2022.04.07 - Account for crop bounds that may extend beyond image dimensions.
# 2023.12.28 - Updated open_slide_scene() to also work for single (non-slide) pyramidal images.
#              Also added new button to load a new CZI (rather than closing and using menu again).
# 2024.01.05 - Split out slide preview extraction to extract_slide_preview() so it could be used independently of GUI.
#              Also forced RGB LUT onto slide preview (it seemed to carry-over prior Bioformats LUTs by default?).

import errno
import os
import re
from ij import IJ
from ij import ImagePlus
from ij.gui import DialogListener
from ij.gui import GenericDialog
from ij.gui import NonBlockingGenericDialog
from ij.gui import Roi
from ij.gui import TextRoi
from ij.io import OpenDialog
from ij.plugin import CanvasResizer
from ij.plugin import RGBStackMerge
from ij.plugin import StackCombiner
from ij.process import LUT
from ij.process import StackConverter
from java.awt import Button
from java.awt import Color
from java.awt import Font
from java.awt import Panel
from java.awt import Rectangle
from java.awt.image import IndexColorModel
from loci.common import DebugTools
from loci.common import Region
from loci.formats import ImageReader
from loci.formats import MetadataTools
from loci.plugins import BF
from loci.plugins.in import ImporterOptions

from . import color_chooser
from .roi import intersect_rois
from .roi import xfer_calibrated_roi
from .utils import byte2list
from .utils import is_int
from .utils import logerror
from .utils import logmsg


def save_lzw(imp, path, compression='LZW', export_roi=False):
    """ Use Bio-Formats Exporter to save a LZW compressed TIF.
        Can also optionally embed existing overlays.
    """
    # BF exporter doesn't overwrite, but appends?
    # Stupid (?) workaround is to remove file first.
    if export_roi:
        export_txt = 'export'  # "export" == embed overlays.
    else:
        export_txt = ''
    try:
        os.remove(path)
    except OSError as e:
        if e.errno == errno.ENOENT:
            pass
        else:
            logerror(e, 'Problem saving as LZW: %s' % path)
    IJ.run(imp, 'Bio-Formats Exporter', 'save=[%s] %s compression=%s' % (path, export_txt, compression))
    return True


def load_lzw(path, import_roi=False):
    """ Import LZW TIF created with Bio-Formats exporter.
        Must use this method in order to load proper calibration!
        
        Note: Calibration unit seems to be forced to 'micron'??  A bug?
    """
    opts = ImporterOptions()
    opts.setId(path)
    opts.setStackFormat(opts.VIEW_HYPERSTACK)
    opts.setGroupFiles(False)
    opts.setAutoscale(False)
    opts.setCrop(False)
    opts.setColorMode(opts.COLOR_MODE_GRAYSCALE)
    #opts.setOpenAllSeries(False)
    #opts.clearSeries()
    #opts.setSeriesOn(series, True)
    opts.setShowROIs(import_roi)
    opts.setROIsMode(opts.ROIS_MODE_OVERLAY )
    return BF.openImagePlus(opts)[0]  # Provided as array, but should only have one element.


def open_czi(path, series=0, split_channels=False, pyramid=False, res_level=1, crop=None):
    """ Import a multi-channel Zeiss CZI image with each channel preserving the original color.
    
        Currently defaults to first series if not specified, and only opens one series at a time.
    
        If CZI is specified to be a pyramid, then we are using "series" to specify a "scene"
        as defined by Zeiss ZEN software (typically individual sections on a slide).  The issue
        is that each resolution level of a pyramidal image is "flattened" and is called 
        a different "series" by BioFormats.  So we need to first examine the CZI and work out
        how many series/resolutions exist for each scene.
    """
    # Lower logging level because we keep getting warnings about unknown "IlluminationType" or "DetectorType" values.
    DebugTools.setRootLevel('error')
	# Initalize metadata reader.
    reader = ImageReader()
    reader.setFlattenedResolutions(True)
    ome_meta = MetadataTools.createOMEXMLMetadata()
    reader.setMetadataStore(ome_meta)
    reader.setId(path)
    s_count = reader.getSeriesCount()
    # Set up ImagePlus title.
    _, title = os.path.split(path)
    ### Changed this sequence 2022.04.07 ####
    if not pyramid and res_level != 1:
        logerror(ValueError, 'Cannot specify res_level > 1 if pyramid is False!')
    si = get_czi_series_info(path)
    # Extra scrutiny if using a pyramid.
    if pyramid:
        try:
            mag_idx = si.res[series].index(res_level)  # Find index of res level for scene.
        except ValueError:
            logerror(ValueError, 'Res level [%d] not found for series [%d] in %s..!' % (res_level, series, path))
        w, h = si.dim[series][mag_idx]
        title += ' %s x%d' % (si.name[series], res_level)
        series = si.idx[series] + mag_idx  # Actual location of scene/resolution combo.
    else:
        w, h = [item for sublist in si.dim for item in sublist][series]  # 2022.05.02 -- Wonky fix to flatten list when not using pyramid-series notation.
        if s_count > 1:
            title += ' Scene #%d' % series
    # # Extra scrutiny if using a pyramid.
    # if pyramid:
    #     si = get_czi_series_info(path)
    #     title += ' %s x%d' % (si.name[series], res_level)
    #     try:
    #         mag_idx = si.res[series].index(res_level)  # Find index of res level for scene.
    #     except ValueError:
    #         logerror(ValueError, 'Res level [%d] not found for series [%d] in %s..!' % (res_level, series, path))
    #     series = si.idx[series] + mag_idx  # Actual location of scene/resolution combo.
    # elif res_level != 1:
    #     logerror(ValueError, 'Cannot specify res_level > 1 if pyramid is False!')
    # elif s_count > 1:
    #     title += ' Scene #%d' % series
    ### End change 2022.04.07 ####
    if series > s_count-1:
        logerror(ValueError, 'Series [%d] not found, only %d available..!' % (series, s_count))
    c_count = reader.getSizeC()
    i_count = reader.getMetadataValue('Information|Image|SizeI #1')  # For dual illumination.
    if i_count: i_count = int(i_count)  # Can't run int() on None type.
    # Color value could be in different locations depending on source scope.
    # Not sure of best way to best identify scope yet...  ## TODO
    acq_mode = reader.getMetadataValue('Information|Image|Channel|AcquisitionMode #1')
    if reader.isRGB():
        # The three channels are part of a color RGB image, not separate wavelengths.
        colors = {0:Color(255, 0, 0, 255), 1:Color(0, 255, 0, 255), 2:Color(0, 0, 255, 255)}
    else:
        # Get color for each channel from metadata.
        colors = dict()
        for i in range(c_count):
            if i_count > 1:
                i2 = i % i_count
            else:
                i2 = i
            if acq_mode == 'SPIM':  # For Lightsheet.
                hex = reader.getMetadataValue('Experiment|AcquisitionBlock|MultiTrackSetup|TrackSetup|Detector|Color #%d' % (i2+1))
            elif acq_mode == 'WideField':  # For Macroscope.
                hex = reader.getMetadataValue('Information|Image|Channel|Color #%d' % (i2+1))
            else:
                hex = '#FFFFFFFF' ## TODO (this will probably cause an error for now...)
            hex = int(hex.replace('#',''), 16)  # Convert from hex string to int.
            a = (hex & 0xFF000000) >> 24  # Extract alpha value.
            r = (hex & 0XFF0000) >> 16    # Extract red value.
            g = (hex & 0XFF00) >> 8       # Extract green value.
            b = (hex & 0XFF)              # Extract blue value.
            colors[i] = Color(r, g, b, a)
    reader.close()
    # Built LUT list for colors (used for certain programs).
    luts = [LUT.createLutFromColor(colors[i]) for i in range(c_count)]
    # Import image with color settings.
    opts = ImporterOptions()
    opts.setId(path)
    opts.setGroupFiles(False)
    opts.setStackFormat(opts.VIEW_HYPERSTACK)
    opts.setAutoscale(False)
    opts.setCrop(False)
    opts.setSplitChannels(True)
    opts.clearSeries()
    opts.setSeriesOn(series, True)
    opts.setColorMode(opts.COLOR_MODE_CUSTOM)
    for i in range(c_count):
        opts.setCustomColor(series, i, colors[i])
    # Set crop boundary, if roi given.
    offset_flag = False
    if crop:
        # Fix 2022.04.07 -- If crop bounds extend beyond image, output does not match expectations (or fails).
        #                   Solution is to adjust crop bounds, and afterwards insert null space in image.
        cw = crop.width
        ch = crop.height
        xoff = abs(min(0, crop.x))
        yoff = abs(min(0, crop.y))
        xoff2 = max(0, (crop.x + crop.width) - w)
        yoff2 = max(0, (crop.y + crop.height) - h)
        if (xoff + yoff + xoff2 + yoff2) > 0:
            roi1 = Roi(crop.x, crop.y, crop.width, crop.height)
            roi2 = Roi(0, 0, w, h)
            crop = intersect_rois(roi1, roi2).getBounds()
            offset_flag = True
        opts.setCrop(True)
        opts.setCropRegion(series, Region(crop.x, crop.y, crop.width, crop.height))
    # Extract the image.
    imp = BF.openImagePlus(opts)
    # If there was a crop offset (see above), expand the canvas accordingly.
    if offset_flag:
        for im in imp:  # BF returns a list.
            stack = im.getStack()
            if stack and stack.getSize() > 1:
                im.setStack(None, CanvasResizer().expandStack(stack, cw, ch, xoff, yoff))
            else:
                im.setProcessor(None, CanvasResizer().expandImage(im.getProcessor(), cw, ch, xoff, yoff))
    # Work around for memory issue... if splitChannels is not invoked, it is impossible
    # to clear the imp from memory via garbage collection due to a BioFormats bug!
    # See: https://forum.image.sc/t/memory-not-clearing-over-time/2137/35
    if not split_channels:
        cal = imp[0].getCalibration()
        if len(imp) > 1:
            # This function returns NULL if imp is a list of len==1!  Dumb.
            imp = RGBStackMerge.mergeChannels(imp, False)
        else:
            imp = imp[0]
        cal.pixelWidth *= res_level
        cal.pixelHeight *= res_level
        imp.setCalibration(cal)
        imp.setTitle(title)
        imp.setProperty('czi', path)
    # BioFormats only uses calibration from highest-res image, so must adjust accordingly.
    else:
        for i,im in enumerate(imp):
            cal = im.getCalibration()
            cal.pixelWidth *= res_level
            cal.pixelHeight *= res_level
            im.setCalibration(cal)
            im.setTitle('%s - C=%d' % (title, i))
            im.setProperty('czi', path)
    # Restore logging to default level.
    DebugTools.setRootLevel('warn')
    return imp, luts


def get_czi_series_info(path):
    """ Examine a CZI for the presence of multiple series' and/or resolutions (pyramid).
    """
    logmsg('Examining %s ...' % path)
    reader = ImageReader()
    ome_meta = MetadataTools.createOMEXMLMetadata()
    reader.setMetadataStore(ome_meta)
    reader.setFlattenedResolutions(False)
    reader.setId(path)

    series_info = lambda:0  # Container for info.
    series_info.path    = path # File path.
    series_info.count   = []   # How many resolutions?
    series_info.idx     = []   # First index in flattened series?
    series_info.res     = []   # Resolution scale factors?
    series_info.name    = []   # Image/series name?
    series_info.box     = []   # Position on slide?
    series_info.dim     = []   # Image dimensions?
    series_info.calx    = []   # Physical X calibration (of orig resolution)?
    series_info.caly    = []   # Physical Y calibration (of orig resolution)?
    #series_info.zcal    = []   # Physical Z calibration?  ## NOTE: Note dealing w/ 3rd dim for now.
    series_info.calunit = []   #  Physical calibration unit?
    #series_info.nc      = []   # Number of color channels?
    #series_info.bits    = []   # Number of _valid_ bits per pixel?
    #series_info.rgb     = []   # Boolean is RGB?
    
    # Length of 0-padding for string formatting below.  Metadata # padding changes based on total series count.
    # Seems janky, but it works...
    pad = str(len(str(reader.getSeriesCount()-2)))  # Do not count label/macro series.
    
    # Iterate over each scene/series.
    for i in range(reader.getSeriesCount()):
        reader.setSeries(i)
        series_info.idx.append(sum(series_info.count))  # First index is sum of total prior scenes/resolutions.
        series_info.count.append(reader.getResolutionCount())  # Number of resolutions for this scene.
        series_info.name.append(ome_meta.getImageName(i))  # Name of each scene (either "Scene #X" or "label/macro image")
        series_info.calx.append(ome_meta.getPixelsPhysicalSizeX(i).value())
        series_info.caly.append(ome_meta.getPixelsPhysicalSizeY(i).value())
        #series_info.caly.append(ome_meta.getPixelsPhysicalSizeZ(i).value())
        series_info.calunit.append(ome_meta.getPixelsPhysicalSizeX(i).unit().getSymbol())
        #series_info.nc.append(reader.getSizeC())
        #series_info.bits.append(reader.getBitsPerPixel())
        #series_info.rgb.append(reader.isRGB())
        # Work out the different resolution scales (should be factors of 2?).
        x = []
        xy = []
        for j in range(reader.getResolutionCount()):
            reader.setResolution(j)
            x.append(reader.getSizeX())
            xy.append((reader.getSizeX(), reader.getSizeY()))
        series_info.res.append([x[0]/item for item in x])
        series_info.dim.append(xy)
        # Work out the bounding box for this scene, in um, relative to bottom-right corner of "macro image"... this relationship is inferred.
        # But don't do this for label/macro images...
        if series_info.name[i].startswith('label') or series_info.name[i].startswith('macro'):
            series_info.box.append(None)
            continue
        cpos = reader.getMetadataValue(('Information|Image|S|Scene|CenterPosition #%0' + pad + 'd') % (i+1))
        csize = reader.getMetadataValue(('Information|Image|S|Scene|ContourSize #%0' + pad + 'd') % (i+1))
        if not cpos and not csize:  # FIXED 2022.03.24 -- Have noticed that Series # is not always used if there is only one series in CZI...
            cpos = reader.getMetadataValue(('Information|Image|S|Scene|CenterPosition'))
            csize = reader.getMetadataValue(('Information|Image|S|Scene|ContourSize'))
        if not cpos and not csize:
            series_info.box.append(None)
            continue
        cpos = [float(item) for item in cpos.split(',')]  # Uses 1-indexing.
        csize = [float(item) for item in csize.split(',')]  # Uses 1-indexing.
        box = (cpos[0]-(csize[0]/2), cpos[1]-(csize[1]/2), csize[0], csize[1])
        series_info.box.append(box)
    
    reader.close()
    # If there was only one series, it might not have a name.  Fudge it.
    if series_info.name[0] == '':
        series_info.name[0] = 'Scene #0'
    return series_info


def get_czi_series_by_name(path, name, si=None, r=0, split_channels=False, as_rgb=False, colors=False):
    """ Get a specific series from a CZI file if a matching name is found.
    """
    if si:
        path = si.path
    else:
        si = get_czi_series_info(path)
    try:
        idx = [n.lower() for n in si.name].index(name.lower())
    except ValueError:
        logmsg('Series "%s" not found!' % name)
        return None
    flat_idx = si.idx[idx] + r  # Start of series + Resolution level (0 == highest res).
    logmsg('Retrieving series "%s" at resolution [%d] ...' % (name, r))
    if as_rgb:
        return czi_to_rgb(path, series=flat_idx, colors=colors)
    else:
        return open_czi(path, series=flat_idx, split_channels=split_channels)


def czi_to_rgb(path, colors=False, levels=False, flatten=True, series=0, pyramid=False, res_level=1):
    """ Convert a multi-channel Zeiss CZI image to an RGB TIF, mixing according to color values.
    
        COLORS: RGB values can be specified as a list of tuple triplets corresponding to each channel/slice.
                RGB values can also be specified as a list of java.awt.Color(s).
                If True, user is prompted to provide colors.
                If False, default colors are used.
    
        LEVELS: Min/max values can be specified as a list of tuple pairs corresponding to each channel/slice.
                If True, user is prompted to provide levels.
                If False, no level adjustments are made.
    """
    # Import CZI image from path.
    imp, luts = open_czi(path, series=series, split_channels=False,  pyramid=pyramid, res_level=res_level)
    # User will specify custom colors.
    if colors is True:
        colors = color_chooser.run([Color(*byte2list([lut.getBytes()[b] for b in [255, 511, 767]])) for lut in luts])
    # Custom colors were specified as arrays.
    elif colors:
        if not all([isinstance(color, Color) for color in colors]):
            # Must be numeric triplets, build Colors from values.
            colors = [Color(color[0], color[1], color[2]) for color in colors]
    # Assign new colors to each channel of composite image.
    if colors:
        for i,color in enumerate(colors):
            lut = LUT.createLutFromColor(color)
            lb = lut.getBytes()
            cm = IndexColorModel(8, 256, lb[0:256], lb[256:512], lb[512:768])
            imp.setC(i+1)
            imp.setChannelColorModel(cm)
        imp.updateAndDraw()
    # Determine if we need to ask for min/max levels.
    if levels is True:
        levels = [(0,0)] * len(luts)
        dlg = GenericDialog('CZI Min/Max Levels')
        dlg.addMessage('Specify custom min/max levels, set both as 0 for default.')
        for i,lut in enumerate(luts):
            if colors:
                color_ = colors[i]
            else:
                color_ = Color(*byte2list([lut.getBytes()[b] for b in [255, 511, 767]]))
            dlg.setInsets(0, 20, 0)
            dlg.addPanel(color_chooser.create_swatch(color_))
            dlg.addToSameRow()
            dlg.addNumericField('Min:', 0, 0)
            dlg.addToSameRow()
            dlg.addNumericField('Max:', 0, 0)
            dlg.addToSameRow()
            dlg.addCheckbox('enabled', True)
        dlg.showDialog()
        if not dlg.wasOKed():
            return [None]*3
        for i in range(len(luts)):
            levels[i] = (dlg.getNextNumber(), dlg.getNextNumber())  # Must consume numbers even if not used.
            if not dlg.getNextBoolean():
                levels[i] = [65536, 65536]  # Set beyond maximum 16-bit value, forces to black.
    # Apply levels if specified.
    if levels:
        for i,level in enumerate(levels):
            if level[0] == 0 and level[1] == 0: continue  # Skip, using default.
            imp.setPositionWithoutUpdate(i+1, 1, 1)
            imp.setDisplayRange(level[0], level[1])
    # Convert to 8-bit RGB.
    if imp.isComposite():
        imp.setMode(IJ.COMPOSITE)  # Should already be a composite image.
    if flatten and imp.getStackSize() > 1:
        StackConverter(imp).convertToRGB()  # Converts in place.
    else:
        imp.setProcessor(imp.getProcessor().convertToByte(True))
    # Return ImagePlus, color, & level settings for repeated use.
    return imp, colors, levels


def extract_slide_preview(path, px_cal=35.554827, x_offset=50, si=None, name=None, show_boxes=True, rotate_label=False):
    """ Extract slide preview (or preview of single image) from CZI file at correct calibration!
    
        PX_CAL (um/px): Approximation of slide-preview calibration obtained from ZEN software.
        
        X_OFFSET (px): Fudge factor to place boxes at correct position on slide.  Positional values in the
                       CZI metadata appear to be relative to the _actual_ upper-right corner, but the preview
                       image does not fully capture the whole slide.  Based on a subset of samples, this offset
                       appears to put the boxes roughly in the right position.
                       
        SI: CZI series info, if pre-calculated.
        
        NAME: CZI name, if pre-calculated.
        
        SHOW_BOXES: Show series ROI locations on preview.
        
        ROTATE_LABEL: False for no rotation, 'Right' or 'Left' to rotate 90 degrees.
    """
    if si:
        path = si.path
    else:
        si = get_czi_series_info(path)
    if name is None:
        name,_ = os.path.splitext(os.path.split(path)[1])
    
    if 'label image' in si.name:
        # Specifically extract 'label image' and 'macro image' series' from CZI.
        # Getting some weird results with preview LUTs, need to force as RGB.
        rgb = [Color.red, Color.green, Color.blue]
        label, _, _ = get_czi_series_by_name(None, 'label image', si=si, as_rgb=True, colors=rgb)  # Only want ImagePlus.
        macro, _, _ = get_czi_series_by_name(None, 'macro image', si=si, as_rgb=True, colors=rgb)  # Only want ImagePlus.
        
        # Rotate label.
        if rotate_label:
            IJ.run(label, 'Rotate 90 Degrees %s' % rotate_label, '')
        
        # Center the label vertically for aesthetics.
        h_diff = (label.getHeight() - macro.getHeight()) / 2
        if h_diff < 0: h_diff = 0
        h = max([label.getHeight(), macro.getHeight()])
        IJ.run(label, 'Canvas Size...', 'width=%d height=%d position=Center zero' % (label.getWidth(), h))
        IJ.run(macro, 'Canvas Size...', 'width=%d height=%d position=Center zero' % (macro.getWidth(), h))
        
        # Combine label and macro images.
        stack = StackCombiner().combineHorizontally(label.getStack(), macro.getStack())
        slide = ImagePlus(name, stack)
    else:
        logmsg('[ %s ] is not a slide scan, but is pyramidal...' % os.path.basename(czi_path))
        # No "preview" exists per se, so use res level with max dim closest to 1500px (arbitrary number...).
        preview_df = [abs(max(item) - 1500) for item in si.dim[0]]
        preview_res_idx = sorted(range(len(preview_df)), key=preview_df.__getitem__)[0]
        slide, _ = open_czi(czi_path, series=0, split_channels=False, pyramid=True, res_level=si.res[0][preview_res_idx])
        h_diff = 0
        
    # Add calibration.
    cal = slide.getCalibration()
    cal.pixelWidth = px_cal
    cal.pixelHeight = px_cal
    cal.setUnit('um')
    
    # Add boxes.
    if show_boxes:
        ip = slide.getProcessor()
        ip.setColor(Color.RED)
        w = slide.getWidth()  # Already have h from above.
        ft = Font(Font.SANS_SERIF, Font.BOLD, 48)
        for i in range(len(si.box)):
            if si.box[i] is None: continue
            b = [item/px_cal for item in si.box[i]]
            roi = Roi(w+b[0]+x_offset, b[1]+h_diff, b[2], b[3])
            roi.setStrokeWidth(3)
            ip.draw(roi)
            txt = TextRoi(w+b[0]+x_offset+(b[2]/2), b[1]+h_diff+(b[3]/2), str(i+1), ft)  # Text scene numbers are now 1-indexed in bioformats -- FIXED 21.07.21
            txt.setJustification(TextRoi.CENTER)
            th = txt.getFloatHeight()
            txt.setLocation(txt.getXBase(), txt.getYBase() - txt.getFloatHeight()/2)
            ip.draw(txt)
    
    return slide
    

def open_slide_scene(px_cal=35.554827, x_offset=50, rotate_label=False):
    """ Interactive dialog to choose a specific scene/resolution from CZI file at correct calibration!
    
        PX_CAL (um/px): Approximation of slide-preview calibration obtained from ZEN software.
        
        X_OFFSET (px): Fudge factor to place boxes at correct position on slide.  Positional values in the
                       CZI metadata appear to be relative to the _actual_ upper-right corner, but the preview
                       image does not fully capture the whole slide.  Based on a subset of samples, this offset
                       appears to put the boxes roughly in the right position.
        
        ROTATE_LABEL: False for no rotation, 'Right' or 'Left' to rotate 90 degrees.
    """

    # Select CZI file.
    czi_path = OpenDialog('Select CZI file').getPath()
    if not czi_path:
        return
    elif not czi_path.endswith('.czi'):
        logmsg('This script only works with CZI files!', True)
        return

    # Get series info.
    si = get_czi_series_info(czi_path)
    name,_ = os.path.splitext(os.path.split(czi_path)[1])
    
    # Is this a slide scan?  If not, check if pyramid or regular image.
    if 'label image' not in si.name:
        if len(si.count) > 1:
            logerror(ValueError, 'No \"label image\" but multiple series\'... not sure what to do with this!', True)
        elif si.count[0] == 1:
            logmsg('[ %s ] is not a slide scan, just opening file instead...' % os.path.basename(czi_path))
            imp, lut = open_czi(czi_path)
            imp.show()
            return
    
    # Get slide preview.
    slide = extract_slide_preview(None, px_cal=px_cal, x_offset=x_offset, si=si, name=name, show_boxes=True, rotate_label=rotate_label)
    
    # Resize for display in dialog.
    ss = IJ.getScreenSize()
    sf = min([(ss.width*0.5) / slide.getWidth(), (ss.height*0.75) / slide.getHeight()])
    slide = slide.resize(int(sf*slide.getWidth()), int(sf*slide.getHeight()), 'bicubic')
    
    class dl (DialogListener):
        def dialogItemChanged(self, gc, e):
            if not e:
                return
            es = e.getSource()
            if es == series_choice:
                populate_res_choice()
            elif es == res_choice:
                populate_res_text()
            elif es == open_btn:
                open_scene()
            elif es == ontop:
                dlg.setAlwaysOnTop(ontop.getState())
            return True
    
    def populate_res_choice():
        s_idx = series_choice.getSelectedIndex()
        r_idx = res_choice.getSelectedIndex()
        res_choice.removeAll()
        for s in si.res[s_idx]:
            res_choice.add('%dx' % s)
        r_idx = min([r_idx, res_choice.getItemCount()-1])
        res_choice.select(r_idx)
        populate_res_text()
        return
    
    def populate_res_text():
        s_idx = series_choice.getSelectedIndex()
        r_idx = res_choice.getSelectedIndex()
        x,y = si.dim[s_idx][r_idx]
        res_text.setText('%d x %d px' % (x, y))
        return
    
    def open_scene():
        series = series_choice.getSelectedIndex()
        res_level = si.res[series][res_choice.getSelectedIndex()]
        imp, luts = open_czi(czi_path, series=series, split_channels=False, pyramid=True, res_level=res_level)
        imp.show()
        return
        
    
    dlg = NonBlockingGenericDialog('CZI Opener')
    dlg.addImage(slide)
    dlg.setInsets(20, 0, 0)
    dlg.addChoice('Scene to open:', si.name, si.name[0])
    dlg.addChoice('Downsampling:', ['1x','2x','4x'], '4x')  # Dummy data.
    dlg.addMessage('')
    open_btn = Button('Open Scene')
    open_btn.setBackground(Color(200, 255, 200))
    open_btn.addActionListener(dlg)
    pnl = Panel()
    pnl.add(open_btn)
    dlg.addPanel(pnl)
    dlg.setInsets(0, 0, 0)
    dlg.addCheckbox('Keep window on top?', False)
    series_choice, res_choice = dlg.getChoices()
    res_text = dlg.getMessage()
    [ontop] = dlg.getCheckboxes()
    dlg.addDialogListener(dl())
    populate_res_choice()
    dlg.setOKLabel('Close CZI Opener')
    dlg.setCancelLabel('Load new CZI...')
    #dlg.hideCancelButton()
    ok_btn = dlg.getButtons()[0]
    ok_btn.setBackground(Color(255, 200, 200))
    dlg.showDialog()
    if dlg.wasCanceled():
        open_slide_scene()
    return


def extract_czi_subregion_gui():
    """ Interactive dialog to extract a full-resolution subregion of a CZI slide scan
        based on an ROI.  Requires the full CZI path, series/scene #, and relative
        downsampling scale of the lower-resolution image.
    """

    class dl (DialogListener):
        def dialogItemChanged(self, gc, e):
            if not e:
                return
            es = e.getSource()
            if es == btn_detect:
                detect_from_image()
            elif es == btn_extract:
                extract_from_image()
                return True
            elif es == chk_top:
                dlg.setAlwaysOnTop(chk_top.getState())
                return True
            validate_fields()
            return True
    
    
    def validate_fields():
        # Only allow extraction if field values are valid.
        flag = (objs.path.getText().lower().endswith('.czi') and
                os.path.isfile(objs.path.getText()) and
                is_int(objs.scene.getText()) and
                is_int(objs.res_level.getText())
                )
        btn_extract.setEnabled(flag)
        if flag:
            btn_extract.setBackground(Color(50, 255, 50))
        else:
            btn_extract.setBackground(None)
        return True
        
    
    def detect_from_image():
        # Detect required values from open image.
        # CZI path should be embedded in image (if opened w/ my CZI Slide Opener).
        try:
            objs.imp = IJ.getImage()
        except:
            return
        path = objs.imp.getProperty('czi')
        if not path:
            path = ''
        objs.path.setText(path)
        title = objs.imp.getTitle()
        objs.title.setText(title)
        regex = re.compile('(.*) Scene #([0-9]+) x([0-9]+)$', re.I).match(title)
        if regex:
            #objs.name = regex.group(1)
            objs.scene.setText(regex.group(2))
            objs.res_level.setText(regex.group(3))
        else:
            #objs.name = ''
            objs.scene.setText('0')
            objs.res_level.setText('1')
        return
    
    
    def extract_from_image():
        """ Extract ROI subregion from CZI at full resolution.
        """
        try:
            # Validate ROI.
            roi = objs.imp.getRoi()
            if roi is None:
                flag = IJ.showMessageWithCancel('Question', 'No ROI detected, extract whole image??')
                if flag:
                    roi = Roi(0, 0, objs.imp.getWidth(), objs.imp.getHeight())
                else:
                    return
            elif not roi.isArea():
                IJ.showMessage('ROI must be an area selection!')
                return
            # TODO: Error checking for too large of a selection.
            # Get details from dialog.
            path = objs.path.getText()
            scene = int(objs.scene.getText()) - 1  # Display indexing is now 1-based, actual indexing is 0-based... -- FIXED 21.07.21
            res_level = int(objs.res_level.getText())
            bounds = roi.getBounds()
            # Scale crop box based on downsampling level.
            rect = Rectangle(bounds.x*res_level, bounds.y*res_level, bounds.width*res_level, bounds.height*res_level)
            # Get full-res, cropped ImagePlus.
            imp2,_ = open_czi(path, series=scene, split_channels=False, pyramid=True, res_level=1, crop=rect)
            # Transfer ROI and/or clear outside ROI if non-rectangular.
            if (roi.getType() or roi.getCornerDiameter()) and (chk_xfer.getState() or chk_clear.getState()):
                xfer_calibrated_roi(objs.imp, imp2, roi)
                imp2.getRoi().setLocation(0,0)
                if chk_clear.getState():
                    IJ.run(imp2, 'Clear Outside', '')
                if not chk_xfer.getState():
                    imp2.setRoi(None)
            # Show the result!
            imp2.show()
        except:
            logmsg('Could not extract from CZI, are the parameters correct?', True)
        return

    # "Global" objects.
    objs = lambda:0

    # Build dialog.
    dlg = NonBlockingGenericDialog('CZI ROI Extractor')
    dlg.addMessage('')
    dlg.setInsets(20, 0, 0)
    dlg.addStringField('CZI Path:', '', 30)
    dlg.addNumericField('Scene #:', 0, 0, 2, '')
    dlg.addNumericField('Downsampled:', 1, 0, 2, 'x')
    objs.title = dlg.getMessage()
    [objs.path] = dlg.getStringFields()
    [objs.scene, objs.res_level] = dlg.getNumericFields()
    dlg.setInsets(0, 0, 0)
    dlg.addCheckbox('Transfer ROI (non-rectangle only)?', False)
    dlg.setInsets(0, 0, 0)
    dlg.addCheckbox('Clear outside ROI w/ background?', False)
    btn_detect = Button('Redetect from image')
    btn_detect.addActionListener(dlg)
    pnl = Panel()
    pnl.add(btn_detect)
    btn_extract = Button('Extract ROI')
    btn_extract.setEnabled(False)
    btn_extract.addActionListener(dlg)
    pnl.add(btn_extract)
    dlg.addPanel(pnl)
    dlg.setInsets(0, 0, 0)
    dlg.addCheckbox('Keep window on top?', False)
    [chk_xfer, chk_clear, chk_top] = dlg.getCheckboxes()
    dlg.addDialogListener(dl())
    detect_from_image()
    validate_fields()
    dlg.setOKLabel('Close Extractor')
    dlg.hideCancelButton()
    dlg.showDialog()
    return