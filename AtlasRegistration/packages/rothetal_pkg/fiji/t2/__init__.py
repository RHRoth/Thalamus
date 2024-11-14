# fiji/t2/__init__.py
# v.2021.09.20
# m@muniak.com
#
# Common functions for TrakEM2.

# 2024.11.07 - Cleaned up for manuscript deposit.

from array import array
from ini.trakem2.display import Display
from ini.trakem2.display import Patch
from ini.trakem2.imaging.filters import CLAHE
from ini.trakem2.imaging.filters import DefaultMinAndMax
from ini.trakem2.imaging.filters import EqualizeHistogram
from ini.trakem2.imaging.filters import IFilter
from ini.trakem2.imaging.filters import NormalizeLocalContrast
from ini.trakem2.imaging.filters import SubtractBackground
from ini.trakem2.imaging.filters import EnhanceContrast
from ini.trakem2.utils import IJError
from ini.trakem2.utils import Utils
from ini.trakem2.utils import Worker
from java.lang import Runtime
from mpicbg.trakem2.align import Align
from mpicbg.trakem2.align import AlignTask
from mpicbg.trakem2.align import RegularizedAffineLayerAlignment

from ..utils import is_int
from ..utils import logmsg


# Image filter presets.
IFILTERS = {
            'Default Min/Max'               : array(IFilter, [DefaultMinAndMax()]),
            'Subtract Background'           : array(IFilter, [SubtractBackground(50)]),
            'Subtract Background + CLAHE'   : array(IFilter, [SubtractBackground(50), CLAHE(True, 100, 255, 6.0)]),
            'None'                          : None, 
            'Equalize Histogram'            : array(IFilter, [EqualizeHistogram()]), 
            'CLAHE (100, 6.0)'              : array(IFilter, [CLAHE(True, 100, 255, 6.0)]), 
            'CLAHE (400, 3.0)'              : array(IFilter, [CLAHE(True, 400, 255, 3.0)]),
            'Normalize Local Contrast'      : array(IFilter, [NormalizeLocalContrast(500, 500, 3.0, True, True)]),
            'CLAHE + NLC for 2xF'           : array(IFilter, [CLAHE(True, 100, 255, 6.0), NormalizeLocalContrast(500, 500, 3.0, True, True)]),
            'Enhance Contrast'              : array(IFilter, [EnhanceContrast()]),
            }

MODEL_STRINGS = ('Translation', 'Rigid', 'Similarity', 'Affine')


def get_display():
    """ Get front display, if any.
    """
    display = Display.getFront()
    if not display:
        logmsg('Ack!  This script requires an open project!', True)
        return False
    return display
    

def get_project():
    """ Get project in front display, if any.
    """
    return get_display().getProject()


def get_layerset():
    """ Get layerset in front display, if any.
    """
    return get_project().getRootLayerSet()


def get_layer():
    """ Get layer in front display, if any.
    """
    return get_display().getLayer()


def get_selected(type=None):
    """ Return whatever is selected in front display.
    """
    return get_display().getSelected(type)


def get_calibration():
    """ Return layerset calibration in front display, if any.
    """
    return get_layerset().getCalibrationCopy()


def get_patches(layer=None, visible=False):
    """ Return patches for specified layer.
        If VISIBLE is True, only return visible patches.
    """
    if not layer:
        layer = get_layer()
    if visible:
        return [p for p in layer.getDisplayables(Patch) if p.isVisible()]
    else:
        return layer.getDisplayables(Patch)


def get_all_patches(layerset=None, visible=False):
    """ Return all patches in layerset.
        If VISIBLE is True, only return visible patches.
    """
    if not layerset:
        layerset = get_layerset()
    if visible:
        return [p for p in layerset.getDisplayables(Patch) if p.isVisible()]
    else:
        return layerset.getDisplayables(Patch)


def update_all():
    get_project().getProjectTree().updateUILater()
    get_project().getProjectTree().rebuild()
    get_project().getLayerTree().updateUILater()
    get_display().update()
    return


def add_layer(z, layer_name='', auto_name=False):
    """ Add a layer to the project if none found at Z.
    """
    proj = get_project()
    ls = get_layerset()
    cal = get_calibration()
    z_px = cal.getRawX(z)
    z_thickness = cal.getRawX(cal.pixelDepth)
    l = ls.getLayer(z_px)
    if l:
        logmsg('Layer (%d) already exists: %s %s' % (z, l.getTitle(), l.toString()))
    else:
        l = ls.getLayer(z_px, z_thickness, True)
        if auto_name:
            proj.findLayerThing(l).setTitle('sec#%02d' % (cal.getRawZ(z)))
        elif layer_name:
            proj.findLayerThing(l).setTitle(layer_name)
    return l


def are_all_done(futures):
    """ Check if all futures in list are completed.
    """
    return all([f.isDone() for f in futures])


def wait(futures, msg):
    """ Wait for tasks to finish.
    """
    logmsg(msg)
    Utils.waitIfAlive(futures, False)


def init_param_layer(model='Similarity', em=False, min=None, max=None):
    """ Return default layer alignment parameters.
        
        MODEL can be a string or index.
        EM triggers default electron microscope settings.
        MIN/MAX must be numbers.
        
        try/except used to support older FIJI versions (extra parameter was added).
    """
    if not is_int(model):
        model = MODEL_STRINGS.index(model)
    if min is None:
        if em: min = 64
        else:  min = 16
    if max is None:
        if em: max = 1024
        else:  max = 512
    cpus = Runtime.getRuntime().availableProcessors()
    try:
        param_layer = RegularizedAffineLayerAlignment.Param(
            8,      # SIFTfdBins
            4,      # SIFTfdSize
            1.6,    # SIFTinitialSigma
            max,    # SIFTmaxOctaveSize
            min,    # SIFTminOctaveSize
            13,     # SIFTsteps
            True,   # clearCache
            cpus,   # maxNumThreadsSift
            0.92,   # rod
            model,  # desiredModelIndex
            model,  # expectedModelIndex
            5.0,    # identityTolerance
            0.1,    # lambda
            200.0,  # maxEpsilon
            1000,   # maxIterationsOptimize
            3,      # maxNumFailures
            3,      # maxNumNeighbors
            cpus,   # maxNumThreads
            200,    # maxPlateauwidthOptimize 
            0.05,   # minInlierRatio
            7,      # minNumInliers
            True,   # multipleHypotheses
            False,  # widestSetOnly  # NEW
            True,   # regularize
            1,      # regularizerIndex
            False,  # rejectIdentity
            False,  # visualize
            )
    except TypeError:  # For older FIJI installations.
        param_layer = RegularizedAffineLayerAlignment.Param(
            8,      # SIFTfdBins
            4,      # SIFTfdSize
            1.6,    # SIFTinitialSigma
            max,    # SIFTmaxOctaveSize
            min,    # SIFTminOctaveSize
            13,     # SIFTsteps
            True,   # clearCache
            cpus,   # maxNumThreadsSift
            0.92,   # rod
            model,  # desiredModelIndex
            model,  # expectedModelIndex
            5.0,    # identityTolerance
            0.1,    # lambda
            200.0,  # maxEpsilon
            1000,   # maxIterationsOptimize
            3,      # maxNumFailures
            3,      # maxNumNeighbors
            cpus,   # maxNumThreads
            200,    # maxPlateauwidthOptimize 
            0.05,   # minInlierRatio
            7,      # minNumInliers
            True,   # multipleHypotheses
            True,   # regularize
            1,      # regularizerIndex
            False,  # rejectIdentity
            False,  # visualize
            )
    if em:
        param_layer.ppm.sift.fdSize     = 8
        param_layer.ppm.sift_steps      = 3
        param_layer.minNumInliers   = 12
    return param_layer


def init_param_montage(model='Similarity', em=False, min=None, max=None):
    """ Return default montaging parameters.
        
        MODEL can be a string or index.
        EM triggers default electron microscope settings.
        MIN/MAX must be numbers.
    """
    if not is_int(model):
        model = MODEL_STRINGS.index(model)
    if min is None: min = 64
    if max is None: max = 1024
    param_montage = Align.ParamOptimize()  # which extends Align.Param
    param_montage.sift.initialSigma = 1.60
    param_montage.sift.steps = 3
    param_montage.sift.minOctaveSize = min
    param_montage.sift.maxOctaveSize = max
    if em: param_montage.sift.fdSize = 8
    else:  param_montage.sift.fdSize = 4
    param_montage.sift.fdBins = 8
    if em: param_montage.rod = 0.92
    else:  param_montage.rod = 0.8
    param_montage.maxEpsilon = 20.00
    param_montage.minInlierRatio = 0.20
    param_montage.minNumInliers = 7
    param_montage.expectedModelIndex = model
    param_montage.rejectIdentity = False
    param_montage.desiredModelIndex = model
    param_montage.correspondenceWeight = 1.00
    param_montage.regularize = False
    param_montage.filterOutliers = False
    return param_montage


class MontageLayerWorker(Worker.Task):
    """ Subclass of Worker.Task for sending montage tasks to Bureaucrat.
    
        Manually calling AlignTask.montageLayers does not invoke the Bureaucrat, which
        disables most Display functions until the task is complete.  Thus, had to manually
        send tasks the Bureaucrat instead by defining a Worker.Task subclass.  Note that
        it is not possible to define the (Java) abstract method exec() because it's a
        reserved word in Python.. so defined the method exec() and redfined run() using
        the same code as the Java source, but calling exec_() instead.
    """
    
    # Initilize subclass.
    def __init__(self, title, interrupt_on_quit=True, **kwargs):
        Worker.Task.__init__(self, title, interrupt_on_quit)
        self.params = None
        self.layer = None
        self.tilesAreInPlaceIn = False
        self.largestGraphOnlyIn = False
        self.hideDisconnectedTilesIn = False
        self.deleteDisconnectedTilesIn = False
        for key, value in kwargs.items():
            setattr(self, key, value)
        if self.params is None:
            raise ValueError('No parameters provided!')
        if self.layer is None:
            raise ValueError('No layer provided!')
        self.setTaskName('Montaging layer %s...' % self.layer.getTitle().encode('utf-8'))
     
    # Redefine run() to call exec_().
    def run(self):
        try:
            self.startedWorking()
            self.exec_()
        except:
            e = sys.exc_info()[0]
            IJError.print(e)
        finally:
            self.finishedWorking()
    
    # The main function.
    def exec_(self):
        AlignTask.montageLayers(self.params, [self.layer], self.tilesAreInPlaceIn,
                                self.largestGraphOnlyIn, self.hideDisconnectedTilesIn,
                                self.deleteDisconnectedTilesIn)