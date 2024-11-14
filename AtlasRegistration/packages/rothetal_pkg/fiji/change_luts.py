# fiji/change_luts.py
# v.2020.08.18
# m@muniak.com
#
# Change LUTs for one or more images.

# 2024.11.07 - Cleaned up for manuscript deposit.

from ij import IJ
from ij import WindowManager
from ij.gui import DialogListener
from ij.gui import NonBlockingGenericDialog
from ij.process import LUT
from java.awt import Button
#from java.awt import Checkbox
#from java.awt import Color
from java.awt import GridBagConstraints
from java.awt import GridBagLayout
from java.awt import Insets
from java.awt import Panel

from .utils import list2byte

# Based on ImageJ's 16_colors LUT (NCSA-PalEdit)
reds    = [   0,   1,   1,   0,   1,   1,   1, 190, 255, 255, 255, 250, 245, 245, 222, 255]
greens  = [   0,   1,   1, 110, 171, 224, 254, 255, 255, 224, 141,  94,   0,   0, 180, 255]
blues   = [   0, 171, 224, 255, 254, 254,   1,   0,   0,   0,   0,   0,   0, 135, 222, 255]


def scale_using_replication(r, g, b, size):
    old_size = len(r)
    r2 = [0]*size
    g2 = [0]*size
    b2 = [0]*size
    for i in range(size):
        idx = int(i*(float(old_size)/size))
        r2[i] = r[idx]
        g2[i] = g[idx]
        b2[i] = b[idx]
    return r2, g2, b2

def scale_using_interpolation(r, g, b, size):
    old_size = len(r)
    r2 = [0]*size
    g2 = [0]*size
    b2 = [0]*size
    scale = (float(old_size)-1)/(size-1)
    for i in range(size):
        idx1 = int(i*scale)
        idx2 = idx1+1
        if idx2 == old_size: idx2 = old_size-1
        f = i*scale - idx1
        r2[i] = int((1.0-f)*r[idx1] + f*r[idx2]
)
        g2[i] = int((1.0-f)*g[idx1] + f*g[idx2]
)
        b2[i] = int((1.0-f)*b[idx1] + f*b[idx2]
)
    return r2, g2, b2

def cutoff_lut(r, g, b, p):
    if len(r) != 256:
        print 'LUT size less than 256, no good!'
        raise IndexError
    if p < 0 or p > 1:
        print 'p-val must be between 0 and 1!'
        raise ValueError
    idx = int(p*255)
    for i in range(idx):
        r[i] = 0
        g[i] = 0
        b[i] = 0
    return r, g, b

def set_zero_val(r, g, b, v):
    if v is None: return r, g, b
    if len(r) != 256:
        print 'LUT size less than 256, no good!'
        raise IndexError
    if v < 0 or v > 255:
        print 'v must be between 0 and 255!'
        raise ValueError
    r[0] = v
    g[0] = v
    b[0] = v
    return r, g, b

def create_mod_lut(size=16, interp=False, cutoff=0.0, zerov=None):
    r = reds
    g = greens
    b = blues
    if size < len(reds):
        r, g, b = scale_using_replication(r, g, b, size)
    if interp:
        r, g, b = scale_using_interpolation(r, g, b, 256)
    else:
        r, g, b = scale_using_replication(r, g, b, 256)
    r, g, b = cutoff_lut(r, g, b, cutoff)
    r, g, b = set_zero_val(r, g, b, zerov)
    return LUT(list2byte(r), list2byte(g), list2byte(b))

def change_luts(size=4, interp=True, cutoff=0.15, zerov=64, allimages=False):
    lut = create_mod_lut(size, interp, cutoff, zerov)
    if allimages:
        imps = [WindowManager.getImage(title) for title in WindowManager.getImageTitles()]
    else:
        imps = [IJ.getImage()]
    for imp in imps:
        imp.setLut(lut)
        imp.updateAndDraw()
    
def launch_gui():
    class dl (DialogListener):
        """ Event handler for GUI buttons.
        """
        def dialogItemChanged(self, gd, e):
            if not e: return
            es = e.getSource()
            try:
                if es == bt_doit:
                    process_button(gd)
                elif es == bt_sync:
                    IJ.run('Synchronize Windows')
            except:
                print 'button problem ...'
            return True
    
    def process_button(dlg):
        numbers = dlg.getNumericFields()
        checkboxes = dlg.getCheckboxes()
        size = int(numbers[0].getText())
        interp = checkboxes[0].getState()
        cutoff = float(numbers[1].getText())
        zerov = int(numbers[2].getText())
        allimages = checkboxes[1].getState()
        change_luts(size, interp, cutoff, zerov, allimages)
        return True
    
    dlg = NonBlockingGenericDialog('Change LUTs')
    dlg.addNumericField('Size', 4, 0)
    dlg.addCheckbox('Interpolate', True)
    dlg.addNumericField('Cutoff %', 0.15, 2)
    dlg.addNumericField('Zero Val', 64, 0)
    dlg.addCheckbox('All Images', False)
    c = GridBagConstraints()
    panel = Panel(GridBagLayout())
    c.insets = Insets(5, 3, 3, 3)
    c.gridx = 0
    c.gridy = 0
    bt_doit = Button('Change LUT(s)!')
    bt_doit.addActionListener(dlg)
    panel.add(bt_doit, c)
    c.insets = Insets(25, 3, 3, 3)
    c.gridy = 1
    bt_sync = Button('Open WinSync')
    bt_sync.addActionListener(dlg)
    panel.add(bt_sync, c)
    dlg.addPanel(panel)
    dlg.addDialogListener(dl())
    dlg.hideCancelButton()
    dlg.setOKLabel('Quit')
    process_button(dlg)
    dlg.showDialog()
    return

if __name__ in ['__main__', '__builtin__']:
    launch_gui()