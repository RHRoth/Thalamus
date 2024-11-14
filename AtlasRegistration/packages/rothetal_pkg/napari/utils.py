# Handy utilities.
#
# v.2024.02.26
# m@muniak.com

import os
import re
import shutil
import numpy as np
from math import isnan

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

def is_int(s):
    """ Check if input is an integer.
    """
    if is_num(s):
        if isnan(float(s)):
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

def regex_renamer(path=None, regex=None, rep=None, go=False):
    """ Rename files in PATH using REGEX and REP.
        REGEX is form of re.compile('...').match.
        REP is a 2-element array [STR, GROUPS]:
            STR is a formatting string, e.g., 'thing%d%s'.
            GROUPS is in array of ints indicating which regex groups to use in STR.
    """
    if (regex is None) or (rep is None):
        print('No REGEX or REP supplied!')
        return
    for f in os.listdir(path):
        x = regex(f)
        if x:
            f2 = rep[0] % tuple(process_str(x.group(i)) for i in rep[1])
            print('%s -> %s' % (f, f2))
            if go:
                shutil.move(os.path.join(path, f), os.path.join(path, f2))
        else:
            print('invalid file: %s' % f)
    if not go:
        print('NOTE: No files were renamed, set GO to True to rename.')
    return


def solve_angle(pc, pb, pa, scale=np.array([1, 1])):
    """ Law of cosines where pc is vertex of angle to be solved, and pb, pa are the other vertices of triangle.
        SCALE is used if coordinates are from a non-isotropic coordinate system.
        Note: Only first two dims are used!
    """
    a = np.linalg.norm( (pc[:2] * scale[:2]) - (pb[:2] * scale[:2]) )
    b = np.linalg.norm( (pc[:2] * scale[:2]) - (pa[:2] * scale[:2]) )
    c = np.linalg.norm( (pa[:2] * scale[:2]) - (pb[:2] * scale[:2]) )
    return np.arccos( (a**2 + b**2 - c**2) / (2 * a * b) )