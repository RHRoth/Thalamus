# fiji/color_chooser.py
# v.2020.10.22
# m@muniak.com
#
# Pop-up interface for selecting multiple colors.

from ij.gui import DialogListener
from ij.gui import GenericDialog
from java.awt import Button
from java.awt import Color
from java.awt import Dimension
from java.awt import Panel
from javax.swing import JColorChooser


AWT_COLORS = ['red', 'green', 'blue', 'magenta', 'cyan', 'yellow', 'orange', 'pink', 'white', 'black']


def create_swatch(color, dim=(20,20)):
    swatch_size = Dimension(*dim)
    swatch = Panel()
    swatch.setPreferredSize(swatch_size)
    swatch.setMinimumSize(swatch_size)
    swatch.setMaximumSize(swatch_size)
    swatch.setBackground(color)
    return swatch


def run(items=None, desc='Channel', c=Color.WHITE, n=3, n_max=10, adjustable=False, comments=[]):
    """ Creates color-chooser dialog for multiple RGB objects.
    
        ITEMS     : Ordered list of any existing Colors.
        DESC      : Object description for dialog.
        C         : Default Color for new objects.
        N         : Number of objects to start empty dialog with (only used if ITEMS is None).
        N_MAX     : Maximum limit of how many color objects to use.
        ADJUSTABLE: If True, user can change how many objects to color (+/-).
        COMMENTS  : If provided, additional field to return a comment for each object color.
    """
        
    def build_dlg(items):
          
        class dl (DialogListener):
            def dialogItemChanged(self, gc, e):
                if not e:
                    return
                es = e.getSource()
                if es == n_chooser:
                    n = es.getSelectedIndex()
                    if n == len(items):
                        return True  # Do nothing.
                    elif n < len(items):
                        items[:] = items[:n]
                        dlg.dispose()
                        return True
                    else:
                        items.extend([c] * (n-len(items)))
                        dlg.dispose()
                        return True
                elif comment_fields and es in comment_fields:
                    return True
                elif es in presets:
                    i = presets.index(es)
                    if es.getSelectedIndex() > 0:
                        set_text_color(i, getattr(Color, es.getSelectedItem()))
                elif es in buttons:
                    i = buttons.index(es)
                    color = JColorChooser.showDialog(None, '%s %d' % (desc, i+1), es.getBackground())
                    if color:
                        set_text_color(i, color)
                for i,button in enumerate(buttons):
                    color = Color(int(rgbs[i*3+0].getText()), 
                                  int(rgbs[i*3+1].getText()), 
                                  int(rgbs[i*3+2].getText()))
                    items[i] = color
                    button.setBackground(color)
                for preset in presets:
                    preset.select(0)
                return True
        
        def set_text_color(i, color):
            rgbs[i*3+0].setText(str(color.getRed()))
            rgbs[i*3+1].setText(str(color.getGreen()))
            rgbs[i*3+2].setText(str(color.getBlue()))
            return
    
        n_chooser = None
        buttons = []
        presets = []
        dlg = GenericDialog('%s Details' % desc)
        if adjustable:
            dlg.addChoice('#', [str(i) for i in range(n_max+1)], str(len(items)))
            n_chooser = dlg.getChoices()[-1]
        for i,color in enumerate(items):
            dlg.setInsets(0, 20, 0)
            p = Panel()
            button = Button('%s %d' % (desc, i+1))
            button.setBackground(color)
            button.addActionListener(dlg)
            buttons.append(button)
            p.add(button)
            dlg.addPanel(p)
            dlg.addToSameRow()
            dlg.addNumericField('R:', color.getRed(), 0)
            dlg.addToSameRow()
            dlg.addNumericField('G:', color.getGreen(), 0)
            dlg.addToSameRow()
            dlg.addNumericField('B:', color.getBlue(), 0)
            dlg.addToSameRow()
            dlg.addChoice('', ['- presets -'] + AWT_COLORS, '- presets -')
            presets.append(dlg.getChoices()[-1])
            if comments:
                try:
                    cmt = comments[i]
                except IndexError:
                    cmt = ''
                dlg.addToSameRow()
                dlg.addStringField('', cmt, 10)
        rgbs = dlg.getNumericFields()
        comment_fields = dlg.getStringFields()
        dlg.addDialogListener(dl())
        dlg.setOKLabel('Make Changes')
        dlg.showDialog()
        if dlg.wasCanceled():
            return None
        elif not dlg.wasOKed():
            return build_dlg(items)  # Restart dialog with new n.
        elif comments:
            return items, [cmt.getText() for cmt in comment_fields]
        else:
            return items
    
    if not items:
        items = [c] * n
    return build_dlg(items)