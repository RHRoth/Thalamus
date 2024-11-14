# -*- coding: utf-8 -*-
# fiji/stitching.py
# v.2020.09.26
# m@muniak.com
#
# Functions related to stitching (BigStitcher, etc.).

# 2024.11.07 - Cleaned up for manuscript deposit.


import glob
import itertools
import math
import os
from datetime import datetime
from ij import IJ
from ij import CompositeImage
from ij import ImagePlus
from ij import ImageStack
from ij.gui import Roi
from ij.plugin import ChannelSplitter
from ij.plugin.filter import ThresholdToSelection
from ij.process import ByteProcessor
from ij.process import StackStatistics
from mpicbg.stitching import PairWiseStitchingImgLib
from mpicbg.stitching import StitchingParameters

from .bioformats import open_czi
from .multithread import multi_task
from .utils import logmsg
from .utils import iqr_filter
from .utils import logmsg
from .utils import make_directory
from .utils import mean
from .utils import rename_mtime
from .utils import resize_hyperstack
from .utils import std


def resize_czi(path, scale=1.0, savedir=None):
    """ Resize CZI to convenient size for analysis, and optionally save as TIF hyperstack.
    """
    logmsg('Loading %s ...' % path)
    czi, _ = open_czi(path)
    logmsg('Loaded %s ...' % path)
    root, fname = os.path.split(path)
    fname = fname.replace('.czi', '.tif')
    tif = resize_hyperstack(czi, scale, keep=False)
    if savedir:
        IJ.saveAs(tif, 'Tiff', os.path.join(savedir, fname))
    return tif


def resize_tif(path, scale=1.0, savedir=None):
    """ Resize TIF to convenient size for analysis, and optionally save as TIF hyperstack.
    """
    logmsg('Loading %s ...' % path)
    tif_orig = IJ.openImage(path)
    logmsg('Loaded %s ...' % path)
    root, fname = os.path.split(path)
    tif = resize_hyperstack(tif_orig, scale, keep=False)
    if savedir:
        IJ.saveAs(tif, 'Tiff', os.path.join(savedir, fname))
    return tif


def get_stack_stats(path_or_imp):
    """ Open TIF stack and return StackStatistics for each channel.
    """
    try:
        logmsg('Loading %s ...' % path_or_imp)
        path_or_imp = IJ.openImage(path_or_imp)
    except TypeError:
        pass  # Object is already ImagePlus.
    return [StackStatistics(imp) for imp in ChannelSplitter.split(path_or_imp)]


def find_ranged_roi(imp, minval=0, maxval=None, erode_steps=5):
    """ Analyze image stack and find a rectangular ROI that does not contain
        pixel values within specified range at any position in z-stack.
        
        Used for limiting area of analysis for pairwise stitching (nearby 
        injection sites from different channels can create false matches).
    """
    w = imp.getWidth()
    h = imp.getHeight()
    xmin = w; xmax = 0
    ymin = h; ymax = 0
    stack = imp.getStack()
    if maxval is None:
        maxval = stack.getProcessor(1).maxValue()
    for s in range(stack.getSize()):
        s += 1  # Stack indexing starts at 1.
        imp.setPosition(s)
        ip = stack.getProcessor(s)
        ip.setThreshold(minval, maxval, False)
        roi = ThresholdToSelection().convert(ip)
        if not roi:
            continue
        # DUMB WORKAROUND because RoiEnlarger can't make small objects disappear!?
        tp = ByteProcessor(w, h)
        tp.setValue(255)
        tp.fill(roi)
        for _ in range(erode_steps):
            tp.dilate()  # For some reason dilate increases black, not erode..?
        tp.setThreshold(1, 255, False)
        roi = ThresholdToSelection().convert(tp)
        # END WORKAROUND
        if not roi:
            continue
        bounds = roi.getBounds()
        xmin = min([xmin, bounds.x])
        xmax = max([xmax, bounds.x+bounds.width])
        ymin = min([ymin, bounds.y])
        ymax = max([ymax, bounds.y+bounds.height])
    areas = [xmin*h, (w-xmax)*h, ymin*w, (h-ymax)*w]
    if max(areas) == areas[0]:
        roi = Roi(0, 0, xmin, h)
    elif max(areas) == areas[1]:
        roi = Roi(xmax, 0, w-xmax, h)
    elif max(areas) == areas[2]:
        roi = Roi(0, 0, w, ymin)
    elif max(areas) == areas[3]:
        roi = Roi(0, ymax, w, h-ymax)
    imp.setRoi(roi)
    return


class Cuboid:
    def __init__(self, xmin, xmax, ymin, ymax, zmin, zmax):
        self.xmin = xmin
        self.xmax = xmax
        self.ymin = ymin
        self.ymax = ymax
        self.zmin = zmin
        self.zmax = zmax
    def __repr__(self):
        return '<Cuboid x:%d-%d, y:%d-%d, z:%d-%d>' % (self.xmin, self.xmax, self.ymin, self.ymax, self.zmin, self.zmax)


def find_ranged_roi3d(imp, minval=0, maxval=None, erode_steps=5):
    """ Analyze image stack and find a cuboid ROI that fully contains
        pixel values within specified range at any position in z-stack.
        
        Used for limiting area of analysis for pairwise stitching (nearby 
        injection sites from different channels can create false matches).
    """
    w = imp.getWidth()
    h = imp.getHeight()
    xmin = w; xmax = 0
    ymin = h; ymax = 0
    stack = imp.getStack()
    d = stack.getSize()
    zmin = d; zmax = 0
    if maxval is None:
        maxval = stack.getProcessor(1).maxValue()
    for s in range(d):
        #s += 1  # Stack indexing starts at 1.
        imp.setPosition(s+1)
        ip = stack.getProcessor(s+1)
        ip.setThreshold(minval, maxval, False)
        roi = ThresholdToSelection().convert(ip)
        if not roi:
            continue
        # DUMB WORKAROUND because RoiEnlarger can't make small objects disappear!?
        tp = ByteProcessor(w, h)
        tp.setValue(255)
        tp.fill(roi)
        for _ in range(erode_steps):
            tp.dilate()  # For some reason dilate increases black, not erode..?
        tp.setThreshold(1, 255, False)
        roi = ThresholdToSelection().convert(tp)
        # END WORKAROUND
        if not roi:
            continue
        bounds = roi.getBounds()
        xmin = min([xmin, bounds.x])
        xmax = max([xmax, bounds.x+bounds.width])
        ymin = min([ymin, bounds.y])
        ymax = max([ymax, bounds.y+bounds.height])
        zmin = min([zmin, s])
        zmax = max([zmax, s])
    
    # Cuboids are defined by [xmin, xmax, ymin, ymax, zmin, zmax].
    # 6 cuboids per imp bordering each face of the ROI.
    cuboids = [Cuboid(0, xmin, 0, h, 0, d), 
               Cuboid(xmax, w, 0, h, 0, d), 
               Cuboid(0, w, 0, ymin, 0, d), 
               Cuboid(0, w, ymax, h, 0, d), 
               Cuboid(0, w, 0, h, 0, zmin), 
               Cuboid(0, w, 0, h, zmax, d)]
    return cuboids


def find_max_cuboid_overlap(a, b):
    """ Assess two sets of cuboids and return the pair (one from set a
        and one from set b) that has the maximum overlap.
    """
    if a is None or b is None:
        return None, None
    pairs = [(i, j) for i in range(len(a)) for j in range(len(b))]
    vols = []
    for i, j in pairs:
        vols.append((min(a[i].xmax, b[j].xmax) - max(a[i].xmin, b[j].xmin)) * 
                    (min(a[i].ymax, b[j].ymax) - max(a[i].ymin, b[j].ymin)) * 
                    (min(a[i].zmax, b[j].zmax) - max(a[i].zmin, b[j].zmin)))
    if max(vols) < 0:
        return None, None
    else:
        idxa, idxb = pairs[vols.index(max(vols))]
        return a[idxa], b[idxb]


def prep_imp_for_pairwise(imp, cuboid):
    """ Prepare an ImagePlus for pairwise comparison by applying an ROI defined
        by the supplied cuboid.  If cuboid extends across the entire z-depth, 
        simply add an ROI that corresponds to xy-limits of cuboid.  If cuboid
        is limited in z-dimension (and therefore spans entire xy-plane of imp) 
        then return a new partial stack equivalent to cuboid location.
    """
    # Using whole stack, just need to designate an ROI.
    if cuboid.zmin == 0 and cuboid.zmax == imp.getStackSize():
        roi = Roi(cuboid.xmin,
                  cuboid.ymin, 
                  cuboid.xmax - cuboid.xmin,
                  cuboid.ymax - cuboid.ymin)
        imp.setRoi(roi)
        return imp
    # Using partial stack.
    stack = imp.getStack()
    stack_out = ImageStack(imp.getWidth(), imp.getHeight(), cuboid.zmax-cuboid.zmin)
    for z in range(cuboid.zmin, cuboid.zmax):
        stack_out.setProcessor(stack.getProcessor(z+1), (z-cuboid.zmin)+1)
    return ImagePlus(imp.getTitle(), stack_out)


class Offset:
    def __init__(self, pairwise_result, zoffset=0):
        self.pairwise_result = pairwise_result
        self.zoffset = zoffset
    def getX(self):
        return self.pairwise_result.getOffset(0)
    def getY(self):
        return self.pairwise_result.getOffset(1)
    def getZ(self):
        return self.pairwise_result.getOffset(2) - self.zoffset
    def getOffset(self):
        return (self.getX(), self.getY(), self.getZ())
    def getCrossCorrelation(self):
        return self.pairwise_result.getCrossCorrelation()
    def getPhaseCorrelation(self):
        return self.pairwise_result.getPhaseCorrelation()
    def __repr__(self):
        return '<Offset x: %0.6f, y: %0.6f, z: %0.6f>' % (self.getX(), self.getY(), self.getZ())


def pairwise_xy(tif, minval=None, maxval=None, erode_steps=5):
    """ Use pairwise stitching to calculate offsets in z-axis between different
        channels in TIF stack.  If 'minval' is specified, then we will 
        first attempt to find an ROI that excludes a specified pixel range.
        
        ** Old version that only looks for ROI in xy-plane. **
    """
    imps = ChannelSplitter.split(IJ.openImage(tif))
    if minval:
        for ch, imp in enumerate(imps):
            logmsg('Finding ROI for channel %d of %s ...' % (ch, os.path.basename(tif)))
            find_ranged_roi(imp, minval, maxval, erode_steps)
    results = {}
    # Compare every possible pair of channels in TIF.
    for (ch1, imp1), (ch2, imp2) in itertools.combinations(enumerate(imps), 2):
        logmsg('Comparing channels %d & %d of %s ...' % (ch1, ch2, os.path.basename(tif)))
        results[(ch1, ch2)] = Offset(PairWiseStitchingImgLib.stitchPairwise(imp1, imp2, imp1.getRoi(), imp2.getRoi(), 1, 1, init_params()))
    return results


def pairwise(tif, minval=None, maxval=None, erode_steps=5):
    """ Use pairwise stitching to calculate offsets in z-axis between different
        channels in TIF stack.  If 'minval' is specified, then we will 
        first attempt to find an ROI that excludes a specified pixel range.
        
        Returns pair of PairWiseStichingResult and additonal z-offset.
    """
    imps = ChannelSplitter.split(IJ.openImage(tif))
    if minval:
        cuboid_sets = []
        for ch, imp in enumerate(imps):
            logmsg('Finding ROI for channel %d of %s ...' % (ch, os.path.basename(tif)))
            cuboid_sets.append(find_ranged_roi3d(imp, minval, maxval, erode_steps))
    else:
        cuboid_sets = [None] * len(imps)
    results = {}
    # Compare every possible pair of channels in TIF.
    for (ch1, (imp1, cub_set1)), (ch2, (imp2, cub_set2)) in itertools.combinations(enumerate(zip(imps, cuboid_sets)), 2):
        logmsg('Comparing channels %d & %d of %s ...' % (ch1, ch2, os.path.basename(tif)))
        cub1, cub2 = find_max_cuboid_overlap(cub_set1, cub_set2)
        if cub1:
            imp1 = prep_imp_for_pairwise(imp1, cub1)
            imp2 = prep_imp_for_pairwise(imp2, cub2)
            results[(ch1, ch2)] = Offset(PairWiseStitchingImgLib.stitchPairwise(imp1, imp2, imp1.getRoi(), imp2.getRoi(), 1, 1, init_params()), cub2.zmin - cub1.zmin) 
        else:
            results[(ch1, ch2)] = Offset(PairWiseStitchingImgLib.stitchPairwise(imp1, imp2, imp1.getRoi(), imp2.getRoi(), 1, 1, init_params())) 
    return results


def resize_set(path, scale=0.25, savedir=None, ext='czi'):
    """ Batch resize CZIs or TIFs to reduced-size TIFs for pairwise analysis.
    
        Returns path containing resized TIFs.
        
        TODO:  Existing folder renaming retention could be improved (name folders based on scale?)
    """
    if not savedir:
        savedir = os.path.join(path, '_resized')
    try:
        scaletxt = open(os.path.join(savedir, 'scale.txt'), 'r')
        old_scale = float(scaletxt.read().strip())
        scaletxt.close()
    except IOError:
        old_scale = None
    if old_scale != scale:
        rename_mtime(savedir)  # If existing folder with different scale, rename it.
    make_directory(savedir)
    files = glob.glob(os.path.join(path, '*.%s' % ext))
    # Check if scaled files already exist (assumptions are made...).
    if old_scale == scale:
        files = [file for file in files if not os.path.isfile(os.path.join(savedir, os.path.basename(file).replace('.czi', '.tif')))]
    if not files:
        logmsg('Resized files already exist!')
        return savedir
    n_threads = int(math.floor(IJ.maxMemory() / (os.stat(files[0]).st_size * (1 + scale**2))))  # Limit # of processors based on CZI and resized TIF size (which can be huge).
    if ext == 'czi':
        multi_task(resize_czi, [{'path':file, 'scale':scale, 'savedir':savedir} for file in files], n_threads=n_threads)
    elif ext == 'tif':
        multi_task(resize_tif, [{'path':file, 'scale':scale, 'savedir':savedir} for file in files], n_threads=n_threads)
    scaletxt = open(os.path.join(savedir, 'scale.txt'), 'w')
    scaletxt.write('%f' % scale)
    scaletxt.close()
    IJ.run('Collect Garbage')
    logmsg('Done resizing %ss!' % ext.upper())
    return savedir


def calc_z_offsets(path, stats_method='default', minval=0):
    """ Get z-offsets between channels for set of CZI/TIF stacks.
        MORE DETAILS NEEDED
    """
    files = glob.glob(os.path.join(path, '*.tif'))
    # Default method for getting minval (for ROI calc):
    # minval = mean of means + the mean of stdDevs for all channel stacks for all TIFs.
    if stats_method == 'default':
        logmsg('Gathering all stats for TIFs in %s ...' % path)
        stats = multi_task(get_stack_stats, files)
        means, stds = zip(*[(stat.mean, stat.stdDev) for tup in stats for stat in tup])
        minval = sum(means)/len(means) + sum(stds)/len(stds)
    offsets = multi_task(pairwise, kwargs=[{'tif':file, 'minval':minval} for file in files], n_threads=4)
    return offsets


class OffsetSet:
    def __init__(self, offsets, scale_xy=1, scale_z=1, iqr_range=1.5):
        self.offsets = offsets
        self.channels = sorted(set([n for k in offsets[0].keys() for n in k]))
        self.pairs = [p for p in itertools.combinations(range(self.nChannels()), 2)]
        self.scale_xy = scale_xy
        self.scale_z = scale_z
        self.iqr_range = iqr_range
        self.use_scale = True
    def nSets(self):
        return len(self.offsets)
    def nChannels(self):
        return len(self.channels)
    def setUseScale(self, tf):
        self.use_scale = tf
    def setIQR(self, iqr_range):
        self.iqr_range = iqr_range
    def getScaleXY(self):
        if self.use_scale: return self.scale_xy
        else: return 1.0
    def getScaleZ(self):
        if self.use_scale: return self.scale_z
        else: return 1.0
    def getX(self, pair):
        return [o[pair].getX()/self.getScaleXY() for o in self.offsets]
    def getY(self, pair):
        return [o[pair].getY()/self.getScaleXY() for o in self.offsets]
    def getZ(self, pair):
        return [o[pair].getZ()/self.getScaleZ() for o in self.offsets]
    def meanX(self, pair):
        return mean(iqr_filter(self.getX(pair), self.iqr_range))
    def meanY(self, pair):
        return mean(iqr_filter(self.getY(pair), self.iqr_range))
    def meanZ(self, pair):
        return mean(iqr_filter(self.getZ(pair), self.iqr_range))
    def stdX(self, pair):
        return std(iqr_filter(self.getX(pair), self.iqr_range))
    def stdY(self, pair):
        return std(iqr_filter(self.getY(pair), self.iqr_range))
    def stdZ(self, pair):
        return std(iqr_filter(self.getZ(pair), self.iqr_range))
    def printSummary(self):
        txt = u'\nOFFSET SUMMARY:\n'
        txt += u'CH:\tX\t\tY\t\tZ\n'
        for p in self.pairs:
            txt += u'%d,%d:\t% 0.2f ± % 0.2f\t% 0.2f ± % 0.2f\t% 0.2f ± % 0.2f\n' % (
                p[0], p[1], 
                self.meanX(p), self.stdX(p),
                self.meanY(p), self.stdY(p),
                self.meanZ(p), self.stdZ(p),
                )
        txt += u'\n    time: %s\n' % datetime.now().strftime("%y-%m-%d %H:%M:%S")
        txt += u'xy-scale: %0.6f\n z-scale: %0.6f\n' % (self.scale_xy, self.scale_z)
        txt += u'\n# filtered items:\n'
        for p in self.pairs:
            txt += u'%d,%d: %d, %d, %d\n' % (p[0], p[1],
                len(self.getX(p))-len(iqr_filter(self.getX(p), self.iqr_range)),
                len(self.getY(p))-len(iqr_filter(self.getY(p), self.iqr_range)),
                len(self.getZ(p))-len(iqr_filter(self.getZ(p), self.iqr_range)))
        txt += u'\n'
        txt += u'avg without filtering:\n'
        old_iqr = self.iqr_range
        self.setIQR(None)
        for p in self.pairs:
            txt += u'%d,%d:\t% 0.2f ± % 0.2f\t% 0.2f ± % 0.2f\t% 0.2f ± % 0.2f\n' % (
                p[0], p[1], 
                self.meanX(p), self.stdX(p),
                self.meanY(p), self.stdY(p),
                self.meanZ(p), self.stdZ(p),
                )
        self.setIQR(old_iqr)
        txt += u'\n'
        for p in self.pairs:
            txt += u'%d,%d ----\n' % (p[0], p[1])
            for x,y,z in zip(self.getX(p), self.getY(p), self.getZ(p)):
                txt += u'% 0.6f\t% 0.6f\t% 0.6f\n' % (x, y, z)
            txt += u'\n'
        logmsg(txt)
    def summary(self):
        txt = u''
        for p in self.pairs:
            txt += u'%d,%d:\t% f\t% f\t% f\n' % (p[0], p[1], 
                self.meanX(p), self.meanY(p), self.meanZ(p))
        txt += u'\n    time: %s\n' % datetime.now().strftime("%y-%m-%d %H:%M:%S")
        txt += u'xy-scale: %0.6f\n z-scale: %0.6f\n' % (self.scale_xy, self.scale_z)
        txt += u'\n# filtered items:\n'
        for p in self.pairs:
            txt += u'%d,%d: %d, %d, %d\n' % (p[0], p[1],
                len(self.getX(p))-len(iqr_filter(self.getX(p), self.iqr_range)),
                len(self.getY(p))-len(iqr_filter(self.getY(p), self.iqr_range)),
                len(self.getZ(p))-len(iqr_filter(self.getZ(p), self.iqr_range)))
        txt += u'\n'
        txt += u'avg without filtering:\n'
        old_iqr = self.iqr_range
        self.setIQR(None)
        for p in self.pairs:
            txt += u'%d,%d:\t% f\t% f\t% f\n' % (p[0], p[1], 
                self.meanX(p), self.meanY(p), self.meanZ(p))
        self.setIQR(old_iqr)
        txt += u'\n'
        for p in self.pairs:
            txt += u'%d,%d\n' % (p[0], p[1])
            for x,y,z in zip(self.getX(p), self.getY(p), self.getZ(p)):
                txt += u'% f\t% f\t% f\n' % (x, y, z)
            txt += u'\n'
        return txt
    

def init_params(npeaks=5):
    params = StitchingParameters()
    params.dimensionality = 3
    params.fusionMethod = 0
    params.checkPeaks = npeaks
    params.ignoreZeroValuesFusion = False
    params.displayFusion = False
    params.computeOverlap = True
    params.subpixelAccuracy = True
    params.xOffset = 0
    params.yOffset = 0
    params.zOffset = 0
    params.cpuMemChoice = 0
    params.relativeThreshold = 2.5
    params.absoluteThreshold = 3.5
    return params