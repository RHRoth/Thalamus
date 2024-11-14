# fiji/utils.py
# v.2024.09.18
# m@muniak.com
#
# Various handy functions.

# 2024.09.18 - added extra check to make_directory() to deal with funny business on M1+ Macs.
# 2024.02.26 - Found a rogue 'print' statement in process_str()...
# 2021.05.19 - Added ';' delimited list to process_str().  Fixed is_int() to handle decimals in string.
# 2020.11.17 - Original?

import errno
import math
import os
import re
import shutil
import sys
import time
from array import array
from datetime import datetime
from ij import IJ
from ij import CompositeImage
from ij import ImagePlus
from ij import ImageStack
from ij import Prefs
from java.awt import Color


def process_str(s):
    """ Try to convert a string to a int/float/bool/None if possible.
    """
    if is_num(s):
        if is_int(s):
            return int(s)
        else:
            return float(s)  # Also captures NaNs.
    elif s is None or s.lower() == 'none':
        return None
    elif s.lower() == 'true':
        return True
    elif s.lower() == 'false':
        return False
    elif s.startswith('[') and s.endswith(']'):
        return [process_str(x) for x in s[1:-1].split(';')]
    else:
        return s


def load_pref(name, ns='fiji', default=''):
    """ Import preference from IJ_prefs.txt or use default.
        Set float/none type as appropriate.  Bools will work as ints.
        TODO: Does not deal with number arrays for now, which remain strings.
    """
    p = Prefs.get('.'.join(['muniak', ns, name]), default)
    return process_str(p)


def save_pref(name, ns='fiji', val=''):
    """ Save script preference to IJ_prefs.txt.
    """
    pname = '.'.join(['muniak', ns, name])
    try:
        if val is None:
            val = 'none'
        Prefs.set(pname, val)
        return True
    except:
        logmsg('Could not save preference: %s' % pname)
        return False


def save_attributes_as_prefs(obj, ns, keys=None):
    """ Save each key/value attribute of an object as preferences to IJ_prefs.txt.
        If KEYS are provided, only those attributes will be saved.
    """
    if not keys:
        keys = vars(obj)
    success = True
    for key in keys:
        success &= save_pref(key, ns, getattr(obj, key))
    return success


def replace_attributes_from_prefs(obj, ns):
    """ Attempt to load attribute values of an object from IJ_prefs.txt, and replace if they exist.
    """
    for key in vars(obj):
        setattr(obj, key, load_pref(key, ns, getattr(obj, key)))
    return obj


def attributes_to_string(obj, dated=True):
    """ Convert an attribute object into a key=value string.  If OBJ is a list, individual
        objects are separated by new lines.  If DATED is true, current time is appended
        to the beginning of the final string.
    """
    txt = ''
    if dated:
        txt += datetime.now().strftime('time=%y-%m-%d %H:%M:%S,')
    try:
        txt += '\n'.join([','.join(['%s=%s' % (k,getattr(o, k)) for k in vars(o)]) for o in obj])
        for o in obj: print o.slice_position
    except TypeError:  # OBJ is not a list.
        txt += ','.join(['%s=%s' % (k,getattr(obj, k)) for k in vars(obj)])
    return txt


def make_directory(path):
    """ Safely create a directory, if not existent.
        https://stackoverflow.com/questions/273192/
    """
    try:
        os.makedirs(path)
    except OSError as e:
        # 2024.09.18 -- Added isdir() to sequence because something about new M1+ Macs is
        # triggering an Errno 20049 for existing dirs, but I cannot figure
        # out exactly what it is supposed to mean... but this only happens
        # when the full path already exists (I think).
        if os.path.isdir(path):
            pass
        elif e.errno == errno.EEXIST:
            pass
        elif e.errno == 20000:
            # Jython 2.5.3 POSIX bug -- https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=752357
            pass
        else:
            logerror(e, 'Problem creating directory %s' % path)


def rename_mtime(path):
    """ Rename a path by suffixing with its last mtime.
    """
    if not os.path.exists(path):
        return
    base, ext = os.path.splitext(path)
    mtime = os.path.getmtime(path)
    suffix = time.strftime("%y%m%d.%H%M%S", time.localtime(mtime))
    shutil.move(path, base + '_' + suffix + ext)


def lower_ext(path):
    """ Find any files in PATH with all caps extension, and lower them.
    """
    files = filter(re.compile('^.*\.[A-Z]+$').match, os.listdir(path))
    for f in files:
        name, ext = os.path.splitext(f)
        shutil.move(os.path.join(path, f), os.path.join(path, name + ext.lower()))


def find_files_by_ext(base, ext, splitext=False, d=None):
    """ Find all files with matching extension in recursive search path.
        Return as dict with file:fullpath mapping.
        Enable SPLITEXT to trim extension from dict keys.
        Provide existing dict to RES if you want to append.
    """
    if not d: d = {}
    r = re.compile('^[^\._].*\.'+ext+'$', re.I)  # Excluding ._ thumbnails.
    for root, dirs, files in os.walk(base, topdown=False):
        dirs[:] = filter(re.compile('^[^trakem2\.[0-9]+]').match, dirs)  # Exclude trakem2 directories.
        for f in filter(r.match, files):
            f_path = os.path.join(root, f)
            if splitext:
                f,_ = os.path.splitext(f)
            if f in d.keys() and d[f] != f_path:
                logmsg('"%s" found more than once in search path, only one source kept!' % f)
            d[f] = f_path
    return d


def resize_hyperstack(imp, scale=1.0, keep=False):
    """ More or less doing the same thing as FIJI> Image> Scale... but easier to script.
    """
    logmsg('Resizing %s by %f ...' % (imp.getTitle(), scale))
    stack = imp.getStack()
    w = int(imp.getWidth() * scale)
    h = int(imp.getWidth() * scale)
    cal = imp.getCalibration().copy()
    cal.pixelWidth = cal.pixelWidth / scale
    cal.pixelHeight = cal.pixelHeight / scale
    stack2 = ImageStack(w, h)
    for i in range(stack.getSize()):
        stack2.addSlice(stack.getProcessor(i+1).resize(w, h, True))
    imp2 = ImagePlus(imp.getTitle(), stack2)
    imp2.setDimensions(imp.getNChannels(), imp.getNSlices(), imp.getNFrames())
    imp2 = CompositeImage(imp2, CompositeImage.COMPOSITE)
    imp2.setCalibration(cal)
    if not keep:
        imp.changes = False
        imp.close()
        imp.flush()
    return imp2


def lut_color(lut):
    return Color(*byte2list([lut.getBytes()[b] for b in [255, 511, 767]]))


COLOR_DICT = {Color(255,0,0): 'red',
              Color(0,255,0): 'green',
              Color(0,255,91): 'green',  # KW Macroscope GFP
              Color(0,0,255): 'blue',
              Color(0,0,0): 'black',
              Color(255,255,255): 'white'}
def color_name(color):
    return COLOR_DICT.get(color, None)


def mean(iterable):
    """ Return mean of an iterable.  Does not check type first.
    """
    try:
        return 1.0 * sum(iterable) / len(iterable)
    except ZeroDivisionError:
        return float('nan')


def std(iterable, pop=False):
    """ Return std of an iterable.  Does not check type first.
    """
    if pop:
        n = len(iterable)
    else:
        n = len(iterable) - 1
    if n < 1:
        return 0
    m = mean(iterable)
    return (sum([(item-m)**2 for item in iterable])/n)**0.5


def iqr_filter(iterable, lim=1.5):
    """ Find 1st & 3rd IQRs, and remove outliers.
        Inlier bounds: Q1 - lim*IQR, Q3 + lim*IQR
    """
    n = len(iterable)
    if n == 0:
        return None, None
    if lim is None:
        return min(iterable), max(iterable)
    iterable.sort()
    if n % 2 == 0:
        # Even.
        q1 = iterable[(n+2)/4 - 1]
        q3 = iterable[(3*n+2)/4 - 1]
    else:
        # Odd
        q1 = iterable[(n+3)/4 - 1]
        q3 = iterable[(3*n+2)/4 - 1]
    iqr = q3 - q1
    return filter(lambda x: x >= q1 - iqr*lim and x <= q3 + iqr*lim, iterable)


def centroid(bbox):
    """ Return center coordinate of a bounding box.
    """
    x = bbox.x + bbox.width / 2
    y = bbox.y + bbox.height / 2
    return x, y


def euclid(p1, p2):
    """ Euclidian distance between pair of points.
    """
    try:  # If java.awt.Point objects.
        return ( (p1.x-p2.x)**2 + (p1.y-p2.y)**2 )**0.5
    except AttributeError:  # If tuples.
        return ( (p1[0]-p2[0])**2 + (p1[1]-p2[1])**2 )**0.5


def is_close_enough(a, b, tol=(sys.float_info.epsilon * 1e6)): # was 1e-6
    """ Check if two numbers are nearly exact.
    """
    return (((1-tol) < (a/b)) & ((a/b) < (1+tol)))


def is_int(s):
    """ Check if input is an integer.
    """
    if is_num(s):
        if math.isnan(float(s)):
            return False
        try:
            if float(s) == int(s):
                return True
        except ValueError:  # Triggers if decimal in string.
            pass
    return False


def is_num(s):
    """ Check if input is a number.
    """
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def list2byte(elem):
    """ Convert input to byte array.
    """
    return array('b', [x-256 if x > 127 else x for x in elem])


def byte2list(elem):
    """ Convert input to list array.
    """
    return array('i', [x+256 if x < 0 else x for x in elem])


def logmsg(msg, show=False):
    """ Send alerts everywhere.
    """
    datedmsg = '[%s] %s' % (datetime.now().strftime("%y-%m-%d %H:%M:%S"), msg)
    IJ.log(datedmsg)
    print(datedmsg)
    if show:
        IJ.showMessage(msg)


def logerror(err, msg, show=False):
    """ Send error alerts everywhere.
    """
    logmsg('ERROR: ' + msg, show)
    raise err(msg)
