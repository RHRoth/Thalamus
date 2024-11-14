# fiji/calibration.py
# v.2021.05.24
# m@muniak.com
#
# Presets and functions for image calibration.

# 2024.11.07 - Cleaned up for manuscript deposit.

import os
import re
from ij.gui import DialogListener
from ij.gui import GenericDialog
from ij.io import OpenDialog
from ij.measure import Calibration
from java.awt import Checkbox
from java.awt import Choice
from java.awt import GridBagConstraints
from java.awt import GridBagLayout
from java.awt import Insets
from java.awt import Label
from java.awt import Panel
from java.awt import TextField

from .utils import is_num
from .utils import load_pref
from .utils import logmsg
from .utils import save_pref


### BEGIN CUSTOM CALIBRATION TABLES ###
CAL_TABLES = dict()
### END CUSTOM CALIBRATION TABLES ###

BASECAL_TABLE = {
    # preset name                # microns/pixels
    'Unknown'                    : 1.0,
    }

UNIT_DICT = {'m': 1e-3, 'cm': 1e-1, 'mm': 1e0, 'micron': 1e3, 'microns': 1e3, 'um': 1e3, u'\xb5m': 1e3, 'nm': 1e6}

default = lambda:0
default.flag    = False
default.xy      = 1
default.unit    = 'pixel'


def get_groups(reset=False):
    """ Dialog to allow user to specify which calibration groups should be used on machine.
    """
    groups = load_pref('groups', 'calibration')
    if not groups:
        reset = True  # No existing preference, trigger GUI.
    groups = groups.split(',')
    custom_path = load_pref('custom_path', 'calibration')
    if reset:
        all_groups = sorted(CAL_TABLES.keys())
        sel_groups = [item in groups for item in all_groups]
        dlg = GenericDialog('Calibration Groups')
        dlg.addMessage('Please specify calibration groups to use.')
        # Populate dialog with available groups and current status.
        for group, tf in zip(all_groups, sel_groups):
            dlg.addCheckbox(CAL_TABLES[group][0], tf)
        # Last checkbox for custom file use.
        if custom_path:
            dlg.addCheckbox('[ %s ]' % os.path.basename(custom_path), True)
        else:
            dlg.addCheckbox('<-- select to load custom file ', False)
        dlg.showDialog()
        if dlg.wasOKed():
            # Get users selections.
            for i,_ in enumerate(sel_groups):
                sel_groups[i] = dlg.getNextBoolean()
            groups = [group for group,tf in zip(all_groups, sel_groups) if tf]
            # Check custom file option.
            if not dlg.getNextBoolean():
                custom_path = None
            elif not custom_path:
                custom_path = OpenDialog('Select custom calibration file.').getPath()
            # Save new preference.
            save_pref('groups', 'calibration', ','.join(groups))
            save_pref('custom_path', 'calibration', custom_path)
    return groups, custom_path


def set_groups():
    """ Shortcut to directly update calibration group preferences.
    """
    init_calibration(True)
    

def init_calibration(reset=False):
    """ Initialize calibration table based on preferences.
    """
    # Update calibration table based on IJ_prefs.txt.
    groups, custom_path = get_groups(reset)
    for group in groups:
        BASECAL_TABLE.update(CAL_TABLES[group][1])
    if not custom_path:
        return
    try:
        temp_table = dict()
        with open(custom_path, 'rU') as cf:
            for line in cf:
                pair = line.strip().split('\t')
                temp_table[pair[0]] = float(pair[1])
        BASECAL_TABLE.update(temp_table)
    except IOError:
        logmsg('Invalid path for custom calibrations: %s ... not loaded!' % custom_path, True)
        save_pref('custom_path', 'calibration', None)
    except IndexError:
        logmsg('Something is wrong with custom calibration file %s.\n' % custom_path +
                     'Each line must have pair, with value as (um/px): NAME [tab] VALUE', True)
        save_pref('custom_path', 'calibration', None)


def convert_units(c, unit_in, unit_out):
    """ Convert value using unit dictionary.
    """
    if unit_in not in UNIT_DICT.keys():
        raise KeyError('Warning, invalid input unit: %s!' % unit_in)
    elif unit_out not in UNIT_DICT.keys():
        raise KeyError('Warning, invalid output unit: %s!' % unit_out)
    else:
        c = float(c) * UNIT_DICT[unit_out] / UNIT_DICT[unit_in]
        return c, unit_out


def scale_calibration(cal, sf=1.0):
    """ Adjust calibration by scale factor.
        Intended for switching between resolutions of a pyramidal image.
    """
    cal2 = cal.copy()
    cal2.pixelWidth /= sf
    cal2.pixelHeight /= sf
    return cal2


def get_cal_description(c):
    """ Reverse lookup of BASECAL_TABLE to pull out calibration description
        based on calibration value.
    """
    desc = 'Unknown'
    for k, v in BASECAL_TABLE.items():
        if v == c:
            desc = k.strip()
    return desc


def get_embedded_cal(elem, unit_out='nm', t2flag=False, as_cal=False):
    """ Get calibration embedded in ImagePlus and converts to specified unit_out.
        
        Note: Embedded cal is # pixels per unit, but final output is # units per pixel.
    """
    c = elem.getProperty('cal')
    u = elem.getProperty('unit')
    
    # If no calibration (or unit) stored with element, need to extract from ImagePlus (slow).
    if not c or not u:
        if t2flag:
            info = elem.getImagePlus().getProperty('Info')
        else:
            info = elem.getProperty('Info')
        # EM image, get calibration from info tag (embedded cal is for print inches).
        if info and info[0:35] == 'ImageDescription: AMT Camera System':
            x = re.findall("[XY]?pixCal=([0-9.]+)", info, re.I)
            u = re.findall("Unit=(.m)", info, re.I)
            if not x:
                raise ValueError('x,y pixel calibrations for "%s" not found!' % elem.getTitle())
            elif len(x) < 2:
                raise ValueError('Only one x or y pixel calibration for "%s" found!' % elem.getTitle())
            elif len(set(x)) > 1:
                raise ValueError('x,y pixel calibrations for "%s" are not equal!  Strange...' % elem.getTitle())
            c = 1.0 / float(x[0])  # Flip from #pix/unit to #unit/pix
            u = u[0]
        # Non-EM image, so assume embedded calibration is correct.
        else:
            if t2flag:
                cal = elem.getImagePlus().getCalibration()
            else:
                cal = elem.getCalibration()
            c = cal.pixelWidth
            u = cal.getUnit()
        
        # Check for 'print' calibrations (sometimes produced by Neurolucida, etc.)
        if u == 'inch' and c in [1.0/300, 1.0/96, 1.0/72]:
            c = 1.0  # Reset.
            u = 'pixel'
        
        # Check if we've obtained a real calibration.  If not, ask for one.
        if u == 'pixel':
            if default.flag:
                c = default.xy
                u = default.unit
            else:
                c = 1.0 / float(c)
                c, u, default.flag = get_user_calibration(elem.getTitle(), c, u, t2flag=t2flag)
                if default.flag:
                    default.xy = c
                    default.unit = u
        
        # Convert as needed.
        if u == 'pixel':
            logmsg('Warning, image appears to be uncalibrated (unit == "pixels")!', False)
        else:
            c, u = convert_units(c, u, unit_out)
            c = round(c, 10)  # Round to bypass str(float) problems.
        elem.setProperty('cal', str(c))  # Store property w/ patch for fast access.
        elem.setProperty('unit', u)
        if as_cal:
            cal = Calibration()
            cal.pixelWidth = c
            cal.pixelHeight = c
            cal.setUnit(u)
            return cal
        else:
            return c
    
    # Different unit desired for output, convert.
    elif u != unit_out:
        c, u = convert_units(c, u, unit_out)
        c = round(c, 10)  # Round to bypass str(float) problems.
        if as_cal:
            cal = Calibration()
            cal.pixelWidth = c
            cal.pixelHeight = c
            cal.setUnit(u)
            return cal
        else:
            return c
    
    # Calibration property was already stored with patch, fast access.
    else:
        return float(c)


def get_user_calibration(title, c='1.0', u='pixel', d=True, t2flag=False):
    """ Ask user for calibration for uncalibrated images.
    """
    class dl (DialogListener):
        def dialogItemChanged(self, gd, e):
            if not e: return
            es = e.getSource()
            if es == presets:
                s = presets.getSelectedItem()
                if s in BASECAL_TABLE:
                    txt_px.setText('%0.4f' % (1.0 / BASECAL_TABLE[s]))
                    txt_unit.select(u'\xb5m')  # == micron
                else:
                    txt_px.setText('1.0')
                    txt_unit.select('pixel')
                    presets.select(0)
            elif es == txt_unit or (es == txt_px and txt_px.isFocusOwner()):
                # Reset presets selection due to user change.
                presets.select(0)
            return True
    
    dlg = GenericDialog('Warning: Uncalibrated Image!')
    gbc = GridBagConstraints()
    gbc.fill = GridBagConstraints.HORIZONTAL
    gbc.anchor = GridBagConstraints.PAGE_START
    gbc.insets = Insets(3, 3, 3, 3)
    panel = Panel(GridBagLayout())
    
    gbc.gridy = 0
    gbc.gridx = 0
    gbc.gridwidth = 3
    panel.add(Label('[ %s ] is not calibrated!' % title), gbc)
    
    gbc.gridy += 1
    gbc.insets = Insets(20, 3, 3, 3)
    panel.add(Label('Please provide new calibration:'), gbc)
    gbc.gridy += 1
    gbc.insets = Insets(3, 3, 3, 3)
    gbc.gridwidth = 1
    txt_px = TextField(str(c), 10)
    txt_px.addTextListener(dlg)
    panel.add(txt_px, gbc)
    gbc.gridx += 1
    panel.add(Label('pixels per', Label.CENTER), gbc)
    gbc.gridx += 1
    #txt_unit = TextField(u, 5)
    txt_unit = Choice()
    for item in ['pixel', 'm', 'cm', 'mm', u'\xb5m', 'nm']:
        txt_unit.add(item)
    txt_unit.select(u)
    txt_unit.addKeyListener(dlg)
    txt_unit.addItemListener(dlg)
    panel.add(txt_unit, gbc)
    
    gbc.gridy += 1
    gbc.gridx = 0
    gbc.gridwidth = 3
    gbc.insets = Insets(10, 3, 3, 3)
    presets = Choice()
    presets.addKeyListener(dlg)
    presets.addItemListener(dlg)
    presets.add('- optional presets -')
    for item in sorted(BASECAL_TABLE.keys()):
        presets.add(item)
    panel.add(presets, gbc)
    
    gbc.gridy += 1
    gbc.gridwidth = 1
    gbc.insets = Insets(20, 3, 3, 3)
    gbc.gridwidth = 3
    if t2flag:
        cb_default = Checkbox('Apply to all uncalibrated images?', d)
    else:
        cb_default = Checkbox('Apply to source image?', d)
    panel.add(cb_default, gbc)
    
    dlg.addPanel(panel)
    dlg.addDialogListener(dl())
    #dlg.hideCancelButton()
    dlg.showDialog()
    if not dlg.wasOKed():
        return (0,0,0)  # Cancelling out.
    
    c = txt_px.getText()
    u = txt_unit.getSelectedItem()
    d = cb_default.getState()
    
    if not is_num(c) or float(c) <= 0:
        logmsg('Calibration must be a positive number, please try again!', True)
        c, u, d = get_user_calibration(title, c, u, d)
    elif u not in UNIT_DICT:
        logmsg('Unit must not be pixels, please try again!', True)
        c, u, d = get_user_calibration(title, c, u, d)
    
    # Invert to format used by IJ.
    c = 1.0 / float(c)
    # If we chose a preset option, override with _actual_ value, not the text value.
    c = BASECAL_TABLE.get(presets.getSelectedItem(), c)
    
    return c, u, d


# Initialize BASECAL_TABLE upon load.
init_calibration()