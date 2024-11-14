# Customized version of a private import script tailored to this project.
# muniak@ohsu.edu
# 2024.11.06 - Removed unused masking option (for this project), froze BASECAL_TABLE, output verified for manuscript.

# Custom script path (must contain rothetal_pkg folder).
PKG_PATH = r'<<FILEPATH_TO_SCRIPTS>>'

# scripts/trakem2/_import_images.py ** MODIFIED FOR RR_JD IMPORTS
# v.2021.05.17
# m@muniak.com
#
# Loads TIFs into appropriate layers based on filenames.
# Attempts to montage images in layers and possibly align layers.
#
# This is an update to the original "[TrakEM2] Load LMs.txt"
#
# 2020.10.05 -- added hidden z_map option (mapping of filenames to section #s)
# 2021.04.25 -- Need to switch to new mask_patch() method eventually...

# Imports
import math
import os
import re
import sys
import time
from ij import IJ
from ij.io import DirectoryChooser
from ij.gui import GenericDialog
from ij.gui import NonBlockingGenericDialog
from ini.trakem2 import Project
from ini.trakem2.display import Display
from ini.trakem2.display import Patch
from ini.trakem2.persistence import FSLoader
from ini.trakem2.utils import Bureaucrat
from ini.trakem2.utils import Utils
from java.awt.event import ItemListener
from java.awt.event import MouseWheelListener
from java.lang import Runtime
from java.lang import System
from mpicbg.trakem2.align import RegularizedAffineLayerAlignment

sys.path.insert(0, PKG_PATH)
BASECAL_TABLE = {'Unknown': 1.0}
from rothetal_pkg.fiji.calibration import get_embedded_cal
from rothetal_pkg.fiji.utils import logmsg
from rothetal_pkg.fiji import t2
import rothetal_pkg.fiji.t2.canvas
import rothetal_pkg.fiji.t2.displayable
import rothetal_pkg.fiji.t2.layer
import rothetal_pkg.fiji.t2.patch


# Establish some 'global' defaults.
opts = lambda:0  # Black magic.
opts.cal_xy = 1.0  # Only temporary, adjusted after init dialog.
opts.cal_z = 40.0 #100.0  # Usual section thickness (in m).
opts.cal_unit = u'm'  # 'um' also interpreted as same thing.
opts.ifilter_montage = 'None'
opts.ifilter = 'None'
opts.ifilter_all = False
opts.ifilter_defminmax = False
opts.basecal = 'Unknown'
opts.silent_mode = True
opts.mask_central = False
opts.silent_do_rigid = False
opts.silent_do_affine = False
opts.silent_do_save = False #True
opts.silent_close_proj = False #True
opts.option_do_manual = False
opts.append_lock_montage = False
opts.append_lock_layers = False
opts.lowmag_model_index = 0
opts.n_mipmap_threads = Runtime.getRuntime().availableProcessors()  # Max out cores.
opts.relative_scale_tolerance = 0.05  # Allow 5% difference?

# Regular expression patterns.
re_tif = re.compile('([^.][a-z0-9]+)?[_ ]?([0-9]+)(.+)?\.tiff?', re.I).match
re_folder_filter = re.compile("^(?!trakem2\.|_exclude).*$", re.I).match
re_offset = re.compile("_offset ([0-9]+) to ([0-9]+)_", re.I).findall
re_section_num = re.compile("^sec#[0-9.]+", re.I)
    
# Get default montage parameters.
param_montage = t2.init_param_montage('Similarity', False, 64, 1024)
param_layer = t2.init_param_layer('Rigid', False, 16, 256)
param_layer.ppm.sift.fdSize = 8


def manual_position_dlg(layerlist):
    """ Build interactive dialog for manually positioning patches in layerlist
        prior to montaging.
    """
    
    layerset = layerlist[0].getParent()
    # Use object for 'global' options.
    dlg_opts = lambda:0  # Black magic.
    dlg_opts.idx = 0
    dlg_opts.montagelist = t2.displayable.sort_by_z(layerlist)
    dlg_opts.chooserlist = t2.displayable.sort_by_z(layerset.getLayers())
    
    # Set current layer.
    if Display.getFront().getLayer() not in dlg_opts.montagelist:
        Display.getFront().setLayer(dlg_opts.montagelist[0])
    layerset.setMinimumDimensions()
    t2.canvas.expand(layerset)

    def set_button_labels():
        try:  # Set button labels to reflect currently displayed layer.
            dlg_opts.idx = dlg_opts.montagelist.index(Display.getFront().getLayer())
        except ValueError:  # Or not if it isn't  in the list.
            pass
        if dlg_opts.idx > 0:
            button_prev.setEnabled(True)
            button_prev.setLabel('%s (z=%0.1f)' % 
                (dlg_opts.montagelist[dlg_opts.idx-1].getTitle(), 
                 dlg_opts.montagelist[dlg_opts.idx-1].getZ()))
        else:
            button_prev.setEnabled(False)
            button_prev.setLabel('--')
        if dlg_opts.idx < len(dlg_opts.montagelist) - 1:
            button_next.setEnabled(True)
            button_next.setLabel('%s (z=%0.1f)' % 
                (dlg_opts.montagelist[dlg_opts.idx+1].getTitle(), 
                 dlg_opts.montagelist[dlg_opts.idx+1].getZ()))
        else:
            button_next.setEnabled(False)
            button_next.setLabel('--')

    class mouse_wheel_listener (MouseWheelListener):
        def mouseWheelMoved(self, e):
            l_max = len(dlg_opts.montagelist) - 1
            dlg_opts.idx += e.getWheelRotation()
            if dlg_opts.idx < 0:
                dlg_opts.idx = 0
            elif dlg_opts.idx > l_max:
                dlg_opts.idx = l_max
            Display.getFront().setLayer(dlg_opts.montagelist[dlg_opts.idx])
            set_button_labels()

    class button_listeners (ItemListener):
        def itemStateChanged(self, e):
            if not e: return
            es = e.getSource()
            if es == button_top:
                dlg.setAlwaysOnTop(es.getState())
                return
            elif es == choice_layer_chooser:
                idx = choice_layer_chooser.getSelectedIndex()
                if idx > 0:
                    patches = Display.getFront().getSelected(Patch)
                    if patches:
                        cur_layer = Display.getFront().getLayer()
                        if idx > 0:
                            new_layer = dlg_opts.chooserlist[idx-1]
                            if t2.patch.move_to_layer(patches, cur_layer, new_layer):
                                # Returns True if cur_layer was removed.
                                dlg_opts.montagelist.remove(cur_layer)
                                dlg_opts.montagelist = t2.displayable.sort_by_z(dlg_opts.montagelist)
                                dlg_opts.chooserlist = t2.displayable.sort_by_z(layerset.getLayers())
                                build_layer_chooser()
                                set_button_labels()
                    else:
                        IJ.showMessage('No patches selected!')
                choice_layer_chooser.select(0)
                return
            # Buttons that are only active when checked.
            if not es.getState(): return
            if es == button_prev:
                if dlg_opts.idx > 0:
                    dlg_opts.idx += -1
                    Display.getFront().setLayer(dlg_opts.montagelist[dlg_opts.idx])
                    set_button_labels()
            elif es == button_next:
                if dlg_opts.idx < len(dlg_opts.montagelist) - 1:
                    dlg_opts.idx += 1
                    Display.getFront().setLayer(dlg_opts.montagelist[dlg_opts.idx])
                    set_button_labels()
            elif es == button_enlarge:
                t2.canvas.expand()
            elif es == button_reset_canvas:
                t2.canvas.reset(zoomout=True, resize=True)
            elif es == button_hide_all:
                for patch in dlg_opts.montagelist[dlg_opts.idx].getDisplayables(Patch):
                    patch.setVisible(False, True)
                Display.getFront().repairGUI()
            elif es == button_show_all:
                for patch in dlg_opts.montagelist[dlg_opts.idx].getDisplayables(Patch):
                    patch.setVisible(True, True)
                Display.getFront().repairGUI()
            elif es == button_hide_sel:
                selectedPatches = Display.getFront().getSelected(Patch)
                for patch in selectedPatches:
                    patch.setVisible(False, True)
                Display.getFront().repairGUI()
                for patch in selectedPatches:
                    Display.getFront().getSelection().add(patch)
            elif es == button_show_sel:
                selectedPatches = Display.getFront().getSelected(Patch)
                for patch in selectedPatches:
                    patch.setVisible(True, True)
                Display.getFront().repairGUI()
                for patch in selectedPatches:
                    Display.getFront().getSelection().add(patch)
            elif es == button_select_roi:
                sel = Display.getFront().getSelection()
                roi = Display.getFront().getRoi()
                sel.clear()
                sel.selectAll(roi, True)
            elif es == button_select_match:
                sel = Display.getFront().getSelection()
                sel.clear()
                patches = Display.getFront().getLayer().getDisplayables(Patch)
                reTmp = re.compile('.*' + string_select_match.text + '.*').match
                for patch in patches:
                    if reTmp(patch.getTitle()):
                        sel.add(patch)
            es.setState(False)

    def build_layer_chooser():
        choice_layer_chooser.removeAll()
        choice_layer_chooser.add('             - select - ')
        for layer in dlg_opts.chooserlist:
            choice_layer_chooser.add('%s (z=%0.1f)' % (layer.getTitle(), layer.getZ()*layerset.getCalibrationCopy().pixelWidth))
        choice_layer_chooser.select(0)
    
    # Build dialog.
    dlg = NonBlockingGenericDialog('Manual Alignment')
    dlg.addMessage('Manually position patches in rough alignment')
    dlg.setInsets(0, 20, 0)
    dlg.addMessage('for each layer, then click MONTAGE.')
    dlg.setInsets(5, 20, 0)
    dlg.addMessage('Only overlapping patches will be compared.')
    dlg.setInsets(0, 30, 0)
    dlg.addCheckboxGroup(4, 2, ['Show Selected', 'Hide Selected', 'Show All', 
                                'Hide All', 'Enlarge Canvas', 'Reset Canvas', 
                                'Select Under ROI', 'Always on Top'], 
                               [False, False, False, False, False, False, False, True], 
                               ['', ''])
    button_show_sel = dlg.getCheckboxes().get(0)
    button_show_sel.addItemListener(button_listeners())
    button_hide_sel = dlg.getCheckboxes().get(1)
    button_hide_sel.addItemListener(button_listeners())
    button_show_all = dlg.getCheckboxes().get(2)
    button_show_all.addItemListener(button_listeners())
    button_hide_all = dlg.getCheckboxes().get(3)
    button_hide_all.addItemListener(button_listeners())
    button_enlarge = dlg.getCheckboxes().get(4)
    button_enlarge.addItemListener(button_listeners())
    button_reset_canvas = dlg.getCheckboxes().get(5)
    button_reset_canvas.addItemListener(button_listeners())
    button_select_roi = dlg.getCheckboxes().get(6)
    button_select_roi.addItemListener(button_listeners())
    button_top = dlg.getCheckboxes().get(7)
    button_top.addItemListener(button_listeners())
    dlg.setInsets(15, 20, 0)
    dlg.addMessage('Select patches with matching RegEx:')
    dlg.setInsets(0, 30, 0)
    dlg.addStringField('', '', 15)
    dlg.setInsets(0, 40, 0)
    dlg.addCheckbox('Select Patches', False)
    string_select_match = dlg.getStringFields().get(0)
    button_select_match = dlg.getCheckboxes().get(8)
    button_select_match.addItemListener(button_listeners())
    dlg.addMessage('- - - - - - - - - - - - - - - - - - - - - - - -')
    dlg.setInsets(5, 20, 0)
    dlg.addMessage('Cycle through layers with new images:')
    dlg.setInsets(5, 30, 0)
    dlg.addCheckboxGroup(1, 2, ['<<', '>>'], [False, False], ['%-28s' % 'Previous', 
                                                              '%-28s' % 'Next'])
    button_prev = dlg.getCheckboxes().get(9)
    button_prev.addItemListener(button_listeners())
    button_next = dlg.getCheckboxes().get(10)
    button_next.addItemListener(button_listeners())
    dlg.addMessage('- - - - - - - - - - - - - - - - - - - - - - - -')
    dlg.setInsets(5, 20, 0)
    dlg.addMessage('Move selected patches to layer...')
    dlg.setInsets(5, 30, 0)
    dlg.addChoice(' ', [' - select - '], ' - select - ')
    choice_layer_chooser = dlg.getChoices().get(0)
    choice_layer_chooser.addItemListener(button_listeners())
    dlg.enableYesNoCancel('Montage Images', 'Save & Resume Later')
    dlg.setAlwaysOnTop(True)
    dlg.addMouseWheelListener(mouse_wheel_listener())
    set_button_labels()
    build_layer_chooser()
    dlg.showDialog()
    
    if dlg.wasOKed():
        return t2.displayable.sort_by_z(dlg_opts.montagelist), False
    elif dlg.wasCanceled():
        return None, None
    else:
        return t2.displayable.sort_by_z(dlg_opts.montagelist), True


def montage_task(layerlist, tilesinplace=False, fu_dict={}, lowmag=None, exclude_layers=[]):
    """ Routine for montaging patches in layerlist.
    """
    
    if not layerlist:
        return  # Nothing to montage.
    project = layerlist[0].getProject()
    cal = layerlist[0].getParent().getCalibrationCopy()
    filter_ = t2.IFILTERS[opts.ifilter_montage]
    if opts.ifilter_defminmax:
        if filter_ is None:
            filter_ = t2.IFILTERS['Default Min/Max']
        else:
            filter_ = t2.IFILTERS['Default Min/Max'] + filter_
    # Create list of lowmag layers to work on.
    lowmag_layerlist = list(set(layerlist).difference(exclude_layers))
    # List of patches that will be locked/unlocked.
    lowmag_unlocked_patches = []
    # List of currently visible patches that will be temporarily hidden.
    visible_patches = [patch for layer in layerlist 
                             for patch in layer.getDisplayables(Patch)
                             if patch.isVisible()]
    if lowmag and lowmag_layerlist:
        # Save default values for montage parameters.
        pm_ex_prev = param_montage.expectedModelIndex
        pm_de_prev = param_montage.desiredModelIndex
        # Switch params to translate.
        param_montage.expectedModelIndex = opts.lowmag_model_index
        param_montage.desiredModelIndex = opts.lowmag_model_index
        t2.patch.toggle_visibility(visible_patches, False)  # Hide all patches.
        
        # Remove any layers that do not have lowmag items.
        lowmag_layerlist[:] = [layer for layer in lowmag_layerlist
                               if any([get_embedded_cal(patch, cal.getUnit()) == lowmag
                                       for patch in layer.getDisplayables(Patch)])]
        
        # Apply filters to patches layerwise.
        for layer in lowmag_layerlist:
            if layer not in fu_dict:
                fu_dict[layer] = {}  # Necessary?
            if lowmag not in fu_dict[layer]:
                fu_dict[layer][lowmag] = []  # Necessary?
            patches = [patch for patch in layer.getDisplayables(Patch)
                             if get_embedded_cal(patch, cal.getUnit()) == lowmag]
            #if len(patches) < 2:
            #    lowmag_layerlist.remove(layer)  # Not enough lowmags to montage.
            #    continue  # Skip to next layer.
            lowmag_unlocked_patches += [patch for patch in patches if not patch.isLocked()]
            t2.patch.toggle_visibility(patches, True)  # Show only lowmag patches.
            fu_dict[layer][lowmag] += t2.patch.set_filters(patches, filter_)
        
        # Montage lowmags layer-wise, allows for concurrent mipmap threads to run in background.
        n = len(lowmag_layerlist)
        for i,layer in enumerate(sorted(lowmag_layerlist, key=lambda x: x.getZ())):
            if not t2.are_all_done(fu_dict[layer][lowmag]):
                logmsg('Waiting for lowmag MipMaps in layer %s to update...' % layer.getTitle().encode('utf-8'), False)
                Utils.waitIfAlive(fu_dict[layer][lowmag], False)  # Wait until mipmaps are done.
            logmsg('Montaging lowmags in layer %s using %s [%d/%d] ...' % (layer.getTitle().encode('utf-8'), t2.MODEL_STRINGS[param_montage.desiredModelIndex], i+1, n), False)
            if len(layer.getDisplayables(Patch)) > 1:  # Don't montage if only one item..
                b = Bureaucrat.createAndStart(t2.MontageLayerWorker('mw', params=param_montage, layer=layer, tilesAreInPlaceIn=tilesinplace), project)
                b.join()  # Wait for thread to finish.
        
        t2.patch.toggle_lock(lowmag_unlocked_patches, True, False)  # Lock any unlocked lowmag patches.
        # Restore params.
        param_montage.expectedModelIndex = pm_ex_prev
        param_montage.desiredModelIndex = pm_de_prev
        t2.patch.toggle_visibility(visible_patches, True)
    
    # Now do normal montaging on all layers in list.
    # Apply filters to patches layer-wise.
    for layer in layerlist:
        if layer not in fu_dict:
            fu_dict[layer] = {}  # Necessary?
        # Not necessary to add to correct 'calibration' key at this point, so just use dummy key.
        fu_dict[layer]['x'] = t2.patch.set_filters(layer.getDisplayables(Patch), filter_)
    
    # Montage layer-wise, allows for concurrent mipmap threads to run in background.
    n = len(layerlist)
    for i,layer in enumerate(sorted(layerlist, key=lambda x: x.getZ())):
        futures = [item for sublist in fu_dict[layer].values() for item in sublist]
        if not t2.are_all_done(futures):
            logmsg('Waiting for MipMaps to in layer %s to update...' % layer.getTitle().encode('utf-8'), False)
            Utils.waitIfAlive(futures, False)
        if len(layer.getDisplayables(Patch)) > 1 and not t2.patch.are_all_locked([layer])[0]:
            logmsg('Montaging images in layer %s using %s [%d/%d] ...' % (layer.getTitle().encode('utf-8'), t2.MODEL_STRINGS[param_montage.desiredModelIndex], i+1, n), False)
            b = Bureaucrat.createAndStart(t2.MontageLayerWorker('mw', params=param_montage, layer=layer, tilesAreInPlaceIn=tilesinplace), project)
            b.join()  # Wait for thread to finish.
        else:
            logmsg('No futher images to montage in layer %s...' % layer.getTitle().encode('utf-8'), False)
            
    # Unlock any lowmag items we locked above (excluding those locked by user).
    t2.patch.toggle_lock(lowmag_unlocked_patches, False)
    return  ## end montage_task()
            

def montage_patches(layerset, layerlist, folder, projname, fu_dict={}, existing_layers=[]):
    """ Set up patches and layers for montaging.  Can be automatic or manual.
    """
    
    if not layerlist:
        return layerlist  # If empty, nothing to montage, but don't want to 
                          # return None as that triggers an exit.
    
    project = layerset.getProject()
    cal = layerset.getCalibrationCopy()
    tilesinplace = False
    
    # Manual positioning or automatic montaging?
    if opts.option_do_manual:
        layerlist, save_and_quit = manual_position_dlg(layerlist)  # Manual dialog will return layerlist, including any additions.
        if layerlist is None:  # Exit now.
            return None
        elif save_and_quit:  # Save for resuming later.
            # Wait for mipmaps to finish for validation.
            futures = [item for layerlist_ in fu_dict.values() for sublist in layerlist_.values() for item in sublist]
            if not t2.are_all_done(futures):
                IJ.showMessage('Waiting for MipMaps to finish before saving...')
                Utils.waitIfAlive(futures, False)
            if not project.getLoader().getProjectXMLPath(): # not saved yet, need to save
                project.saveAs(os.path.join(folder, projname + '.xml'), False)
            else:
                project.save()
            
            # Save options for restoring later.
            r_opts = [opts.ifilter_all, opts.ifilter_defminmax, opts.silent_mode, opts.mask_central, opts.silent_do_rigid, 
                      opts.silent_do_affine, opts.silent_do_save, opts.option_do_manual, 
                      opts.append_lock_montage, opts.append_lock_layers, opts.silent_close_proj, 
                      str(opts.lowmag_model_index)]
            r_path = os.path.join(project.getLoader().getUNUIdFolder(), 'resumeproject.new')
            r_file = open(r_path, 'w')
            r_file.write(','.join([str(item.getId()) for item in layerlist]) + '\n')  # Layer IDs to be montaged on resume.
            r_file.write(opts.basecal + '\n')  # Selected base calibration.
            r_file.write(opts.ifilter + '\n')  # Selected image filter.
            r_file.write(','.join([str(int(item)) for item in r_opts]) + '\n')  # Bool of options.
            r_file.write(str(Display.getFront().getLayer().getId()) + '\n')  # Current layer.
            r_file.close()
            
            # Check if project should be closed.
            dlg = GenericDialog('Close?')
            dlg.addMessage('Close project now?')
            dlg.showDialog()
            if dlg.wasOKed():
                project.getLoader().setChanged(False)
                project.destroy()
            logmsg('Project saved to be resumed later (use same script).', not opts.silent_mode)
            return None
        else:  # Done with manual positioning, continue with montaging.
            tilesinplace = True
            
    # Get lowest magnification (highest cal) in project.  Images at this mag
    # will first be montaged using a Translation model.
    lowmag = max([get_embedded_cal(patch, cal.getUnit()) for patch in layerset.getDisplayables(Patch)])
    if opts.append_lock_montage:
        # When appending, locked patches don't play well with the translation 
        # transform.  Ergo, only attempt lowmag montage on newly created layers.
        montage_task(layerlist, tilesinplace, fu_dict, lowmag, existing_layers)
    else:
        montage_task(layerlist, tilesinplace, fu_dict, lowmag)
    
    # Check if any newly added (unlocked) patches drastically differ in their relative scale
    # from existing (locked) patches.  Because of the locked pages, the layer will not be normalized.
    # If mis-scaled patches exist, appropriately scale them each independently, centered on (0,0).
    # This should keep newly montaged patches aligned.  Should also catch when different patches
    # have different incorrect scales as well.  Not a perfect fix, but should help...
    if opts.append_lock_montage:
        for layer in layerlist:
            scale_list = []
            visible_patches = [patch for patch in layer.getDisplayables(Patch) if patch.isVisible()]
            locked_patches = [patch for patch in visible_patches if patch.isLocked()]
            if not locked_patches:  # No locked patches in this layer, irrelevant.
                continue
            unlocked_patches = [patch for patch in visible_patches if not patch.isLocked()]
            locked_scale = [t2.displayable.get_relative_scale(patch) for patch in locked_patches]
            locked_scale = sum(locked_scale) / len(locked_scale)
            for patch in unlocked_patches:
                diff = t2.displayable.get_relative_scale(patch) / locked_scale
                if abs(1.0 - diff) > opts.relative_scale_tolerance:  # Only adjust if difference is greater than set amount (default: 5%).
                    scale_list.append([patch.getTitle(), 1.0/diff])
                    t2.patch.scale([patch], 1.0/diff, xo=0.0, yo=0.0, vd=False, linked=False)
            if scale_list:
                logmsg('The following patches in layer %s (z=%0.1f) were resized to match existing relative scaling:' % (layer.getTitle().encode('utf-8'), layer.getZ()*cal.pixelWidth))
                for pt,sc in scale_list:
                    logmsg('%s was scaled by %0.4f.' % (pt,sc))

    t2.canvas.reset(layerset, zoomout=True, resize=True)
    return layerlist  # In case new layers were created.


def load_patches(layerset, filelist, z_map=None):
    """ Load patches into layers.  Returns layerlist & dict of futures.
    """
    
    logmsg('Loading new patches...', False)
    project = layerset.getProject()
    cal = layerset.getCalibrationCopy()
    filter_ = t2.IFILTERS[opts.ifilter_montage]
    if opts.ifilter_defminmax:
        if filter_ is None:
            filter_ = t2.IFILTERS['Default Min/Max']
        else:
            filter_ = t2.IFILTERS['Default Min/Max'] + filter_
    section_thickness = cal.pixelDepth / cal.pixelWidth
    mask_params = None
    fu_dict = {}  # Convoluted futures list broken down by mag and layer.
                  # Theoretically speeds things up down the line..?
    layerlist = set()  # List of layers that have been added.
    # Load patches into respective layers based on section num.
    # Wrap in a "try" in case user cancels during interactive masking.
    try:
        for root, filenames, offset in filelist:
            for filename in filenames:
                try:
                    z = z_map[filename].pop(0)
                    if z_map[filename]:  # Remaining entires because file used for multiple sections (usually a badly segmented slidescan).
                        filenames.append(filename)  # Add filename to iterator to do again.
                except TypeError:  # No dict provided, using filename.
                    z = int(re_tif(filename).group(2)) + offset  # Z as integer.
                except KeyError:  # Dict provided, but entry is missing.
                    logmsg('[ %s ] not found in z_map.csv, relying on filename!' % filename)
                    z = int(re_tif(filename).group(2)) + offset  # Z as integer.
                z_str = 'sec#%02.0d' % z  # Layer name based on z w/ offset accounted for.. 
                                          # this remains even after reshuffling.
                z = float(z) * section_thickness  # Calibrated layer z in pixels.
                layer = layerset.getLayer(z, section_thickness, True)  # Will create new layer if it doesn't exist.
                project.findLayerThing(layer).setTitle(z_str)
                filepath = os.path.join(root, filename)
                patch = Patch.createPatch(project, filepath)
                layer.add(patch)
                patch.maskBorder(0, 0, 0, 0)  # Otherwise transparency doesn't work???
                ecal = get_embedded_cal(patch, cal.getUnit(), True)
                rescale = ecal / cal.pixelWidth  # Relative scaling of patch.
                patch.scale(rescale, rescale, 0.0, 0.0)
                if layer not in fu_dict:
                    fu_dict[layer] = {}
                if ecal not in fu_dict[layer]:
                    fu_dict[layer][ecal] = []
                fu_dict[layer][ecal] += t2.patch.set_filters([patch], filter_)  # Apply montage filter now.
                # Mask central object in patch.
                # Wrapped in try because we need to recreate buckets even if canceled.
                try:
                    if opts.mask_central: ####
                        logmsg('Masking option not enabled for this version of script, sorry!', show=True)
                finally:
                    layer.recreateBuckets()
                    #IJ.showMessage(layer.getTitle())
                layerlist.add(layer)  # Add layer to list of layers to process.
    
        layerlist = list(layerlist)  # Returns list w/o dupes.
        t2.patch.sort_by_mag(layerlist)

    except KeyboardInterrupt:
        t2.canvas.reset(layerset)
        layerlist = None  # Results in canceling out after return.

    finally:
        layerset.recreateBuckets(True)
        project.getLayerTree().updateList(layerset)
        Display.updateLayerScroller(layerset)
    return layerlist, fu_dict


def start_project(folder, project, projname, filelist, layerlist=[], z_map=None):
    """ Main script to initialize project and import/montage images.
    """

    # Initalize project.
    new_project = True if not project else False
    existing_layers = []
    
    if not project:
        # Start new project.
        project = Project.newFSProject("blank", None, folder)
        layerset = project.getRootLayerSet()
        
        # Default calibration.
        cal = layerset.getCalibrationCopy()
        cal.pixelWidth = opts.cal_xy
        cal.pixelHeight = opts.cal_xy
        cal.pixelDepth = opts.cal_z
        cal.setUnit(opts.cal_unit)
        layerset.setCalibration(cal)
        section_thickness = cal.pixelDepth / cal.pixelWidth
        
        # Initialize first layer to correct Z.
        layer = layerset.getLayer(0.0)
        try:  # If z_map provided.
            z = int(z_map[filelist[0][1][0]]) + filelist[0][2]
        except (TypeError, KeyError):  # If no z_map, or filename not in list.
            z = int(re_tif(filelist[0][1][0]).group(2)) + filelist[0][2]
        layer.setZ(z * section_thickness)
        layer.setThickness(section_thickness)
        
    else:
        # Use existing project.
        layerset = project.getRootLayerSet()
        for layer in layerset.getLayers():
            for patch in layer.getDisplayables(Patch):
        #        patch.unlink()
                if opts.append_lock_montage:
                    patch.setLocked(True)
        cal = layerset.getCalibrationCopy()
        section_thickness = cal.pixelDepth / cal.pixelWidth
        existing_layers = layerset.getLayers()
    
    # Maximize number of threads for mipmaps.
    FSLoader.restartMipMapThreads(opts.n_mipmap_threads)
    
    # Get list of pre-existing filters to restore.
    filterlist = dict([(patch, patch.getFilters())
                       for patch in layerset.getDisplayables(Patch)])
    
    # If we have a filelist, load patches, get list of layers w/ new patches...
    # else we are resuming a project, and we were given list of layers to resume.
    if filelist:
        new_layerlist, fu_dict = load_patches(layerset, filelist, z_map)
        if new_layerlist is None:
            return  # Allows for cancelling out/stopping at this stage.
        layerlist = list(set(layerlist + new_layerlist))  # Get rid of potential duplicates.
    else:
        fu_dict = {}
        pass
    
    # Unlink and apply locks as needed.  [NEW, MOVED]
    for layer in layerlist:
        for patch in layer.getDisplayables(Patch):
            patch.unlink()
    
    # Montage patches within each layer.
    layerlist = montage_patches(layerset, layerlist, folder, projname, fu_dict, existing_layers)
    if layerlist is None:
        return  # Allows for cancelling out/stopping at this stage.
    
    # Rescale layers after montaging to get calibration correct.
    t2.layer.normalize(layerset, layerlist)

    # Check if pre-existing patches should still be locked.
    if opts.append_lock_montage and not opts.append_lock_layers:
        t2.patch.toggle_lock(layerset.getLayers(), False)
            
    # Perform layer-wise alignments.
    if any([opts.silent_do_rigid, opts.silent_do_affine]) and len(layerset.getLayers()) > 1:
        ## TODO: Can SIFT parameters be optimized based on overall canvas size??
        
        # Set everything to the montage filter.. assume better results?
        filter_ = t2.IFILTERS[opts.ifilter_montage]
        if opts.ifilter_defminmax:
            if filter_ is None:
                filter_ = t2.IFILTERS['Default Min/Max']
            else:
                filter_ = t2.IFILTERS['Default Min/Max'] + filter_
        futures = t2.patch.set_filters(layerset.getDisplayables(Patch), filter_)
        if futures:
            logmsg('Waiting for MipMaps to update...', False)
            Utils.waitIfAlive(futures, False)
        
        # In case montaging or other operations have left lots of random blank space,
        # move contents of each layer to top-left corner and reset canvas to ensure
        # that the largest canvas size corresponds to the layer with the largest
        # content.. trying to optimize the layer alignment SIFT step...
        t2.canvas.minimize(nonzero=True)
        
        # Align images across layers using RIGID transform.
        if opts.silent_do_rigid:
            try:
                logmsg('Attempting rigid alignment...', False)
                RegularizedAffineLayerAlignment().exec(param_layer,layerset.getLayers(),set(),set(),layerset.getMinimalBoundingBox(Patch),False,False,None)
                t2.canvas.reset(layerset, zoomout=True, resize=True)
            except:
                logmsg('Rigid alignment not possible!', not opts.silent_mode)

        # Align images across layers using AFFINE transform.
        if opts.silent_do_affine:
            layerset.addTransformStep()
            param_layer.desiredModelIndex = 3
            param_layer.expectedModelIndex = 3
            try:
                logmsg('Attempting affine alignment...', False)
                RegularizedAffineLayerAlignment().exec(param_layer,layerset.getLayers(),set(),set(),layerset.getMinimalBoundingBox(Patch),False,False,None)
                t2.canvas.reset(layerset, zoomout=True, resize=True)
            except:
                logmsg('Affine alignment not possible!', not opts.silent_mode)

    # Check again if pre-existing patches should still be locked.
    if opts.append_lock_montage and opts.append_lock_layers:
        t2.patch.toggle_lock(layerset.getLayers(), False)
    
    # Restore filters and/or apply selected filter.
    futures = []
    filter_ = t2.IFILTERS[opts.ifilter]
    if opts.ifilter_defminmax:
        if filter_ is None:
            filter_ = t2.IFILTERS['Default Min/Max']
        else:
            filter_ = t2.IFILTERS['Default Min/Max'] + filter_
    logmsg('Applying selected filter [%s] to images...' % opts.ifilter, False)
    #for layer in layerset.getLayers():
    for layer in layerlist:  ## CHANGED FROM LAYERLIST TO LAYERSET.GETLAYERS
        for patch in layer.getDisplayables():
            if opts.ifilter_all:
                futures += t2.patch.set_filters([patch], filter_)
            else:
                # Uses default if key(patch) not present.
                filter_old = filterlist.get(patch, filter_)
                futures += t2.patch.set_filters([patch], filter_old)
        layer.recreateBuckets()  # Not sure if needed?
    
    # Link all items in each layer, but only if overlapping.
    for layer in layerlist:
        logmsg('Crosslinking overlapping patches in layer %s... may take awhile.' % layer.getTitle().encode('utf-8'), False)
        t2.displayable.crosslink(layer.getDisplayables(Patch), True)
    
    t2.canvas.reset(zoomout=True, resize=True, visible_only=True, nonzero=opts.mask_central)
    project.getLayerTree().updateList(layerset)  # Updates layer listings.

    # Wait for mipmaps to finish for validation.
    if futures:
        logmsg('Waiting for MipMaps to update...', False)
        Utils.waitIfAlive(futures, False)

    # Do a final sanity check and alert user if any patches are incorrectly scaled relative to project calibration.
    # But only checking layers that were currently processed...
    scale_check = []
    for layer in layerlist:
        for patch in layer.getDisplayables(Patch):
            ps = t2.displayable.get_relative_scale(patch)
            if abs(ps-1.0) > opts.relative_scale_tolerance:
                scale_check.append('[%0.3f]: %s in layer %s (z=%0.1f)' % (ps, patch.getTitle(), layer.getTitle().encode('utf-8'), layer.getZ()*layerset.getCalibrationCopy().pixelWidth))
    if scale_check:
        logmsg('The following patches appear to be incorrectly scaled relative to project:\n' +
                     '\n'.join(scale_check), True)
    
    # Save project and finish.
    if opts.silent_do_save:
        if new_project:
            project.saveAs(os.path.join(folder, projname + '.xml'), False)
        else:
            project.save()
        logmsg('Done with alignment!', not opts.silent_mode)
    if opts.silent_close_proj:
        project.getLoader().setChanged(False)
        project.destroy()
        #### COLLECT GARBAGE
        #for _ in range(3):
        #    System.gc()
        #    time.sleep(5)
    else:
        logmsg('Done with alignment! Don\'t forget to save!', not opts.silent_mode)
    return  ## end start_project()


def build_file_list(folder, project, projname, layerlist=[]):
    """ Get list of images to import into project.
    """
    
    # Check for z_map.csv file (hidden patch-2-layer mapping feature that ignores filenames).
    z_map = None
    try:
        with open(os.path.join(folder, 'z_map.csv'), 'r') as f:
            z_map = {fname:[int(zval) for zval in zvals.split('|')]
                     for line in f.read().splitlines() 
                     for (fname,zvals) in [line.split(',')]
                     }
    except:  # folder is None or file not found.
        pass
    
    filelist = []
    if project:
        existingfiles = set([patch.getFilePath() for layer in project.getRootLayerSet().getLayers() for patch in layer.getDisplayables(Patch)])
    
    try:
        logmsg('Searching for TIF images...', False)
        for root, dirs, files in os.walk(folder):
            logmsg('Scanning: %s' % root, False)
            dirs[:] = filter(re_folder_filter, dirs)
            offset = 0
            offset_match = re_offset(root)
            for offset_item in offset_match:
                offset += int(offset_item[1]) - int(offset_item[0])
            filenames = filter(re_tif, files)
            
            # Do not reload existing/duplicate files if we are appending to a project.
            # Does not work if existing files have been moved to a different location 
            # and the xml wasn't updated..
            if project:
                newfiles = set([os.path.join(root,filename).replace('\\','/') for filename in filenames]).difference(existingfiles)
                filenames = [os.path.basename(newfile) for newfile in newfiles] 
            if len(filenames) > 0:
                filelist.append([root, filenames, offset])
    except TypeError:
        pass  # Assumption that folder == 'None'
    except StopIteration:
        pass
    
    if len(filelist) == 0:
        if not project:
            logmsg('No TIF images found in "' + folder + '" or any subfolders!  Stopping ...', not opts.silent_mode)
            return
        elif folder:
            logmsg('No additional TIF images found in "' + folder + '" or any subfolders ...', not opts.silent_mode)
    start_project(folder, project, projname, filelist, layerlist, z_map)
    return  ## end build_file_list()


def resume_project(project):
    """ Restore saved options, and resume.
    """
    
    layerset = project.getRootLayerSet()
    r_path = os.path.join(project.getLoader().getUNUIdFolder(),'resumeproject.new')
    r_file = open(r_path, 'r')
    layerlist = [layerset.getLayer(long(item)) for item in r_file.readline().strip().split(',')]
    opts.basecal = r_file.readline().rstrip()  # rstrip() only to preserve prefix-spaces.
    opts.cal_xy = BASECAL_TABLE[opts.basecal]
    opts.ifilter = r_file.readline().strip()
    r_opts = [bool(int(item)) for item in r_file.readline().strip().split(',')]
    display_id = long(r_file.readline().strip())
    r_file.close()
    
    # Restore options.
    opts.ifilter_all           = r_opts[0]
    opts.ifilter_defminmax     = r_opts[1]
    opts.silent_mode           = r_opts[2]
    opts.mask_central          = r_opts[3]
    opts.silent_do_rigid       = r_opts[4]
    opts.silent_do_affine      = r_opts[5]
    opts.silent_do_save        = r_opts[6]
    opts.option_do_manual      = r_opts[7]
    opts.append_lock_montage   = r_opts[8]
    opts.append_lock_layers    = r_opts[9]
    opts.silent_close_proj     = r_opts[10]
    opts.lowmag_model_index      = int(r_opts[11])
    
    folder, projname = os.path.split(project.getLoader().getProjectXMLPath())
    projname = os.path.splitext(projname)[0]
    try:
        os.rename(r_path, os.path.splitext(r_path)[0] + '.old')  # Save old copy just in case (overwrites any prev .old)
    except OSError:  # Stupid windows
        os.remove(os.path.splitext(r_path)[0] + '.old')
        os.rename(r_path, os.path.splitext(r_path)[0] + '.old')
    Display.getFront().setLayer(layerset.getLayer(display_id))
    start_project(folder, project, projname, None, layerlist)
    return  ## end resume_project()


def redo_section_thickness():
    """ Helper to make sure we get a numeric value.
    """
    
    dlg = GenericDialog('Section thickness')
    dlg.addMessage('Value must be numeric!')
    dlg.setInsets(15, 20, 0)
    dlg.addNumericField('Section thickness:', opts.cal_z, 0, 3, opts.cal_unit)
    dlg.showDialog()
    if not dlg.wasOKed():
        return None
    else:
        return dlg.getNextNumber()


def choose_dir():
    """ Dialog to choose directory w/ images and configure options before starting project.
    """
    
    project = None
    folder = None
    layerlist = []
    choose_dir = True
    
    # See if there is an open project that can be resumed.
    if Display.getFront() and os.path.isfile(os.path.join(Display.getFront().getProject().getLoader().getUNUIdFolder(),'resumeproject.new')):
        dlg = GenericDialog('Resume?')
        dlg.addMessage('Resume montaging of open project: ' + Display.getFront().getProject().toString() + '?')
        dlg.enableYesNoCancel('Resume', 'Nope')
        dlg.hideCancelButton()
        dlg.showDialog()
        if dlg.wasOKed():
            resume_project(Display.getFront().getProject())
            return

    # Check if we are working to an open project.
    if Display.getFront():
        tmp_layers = Display.getFront().getLayerSet().getLayers()
        dlg = GenericDialog('Existing Project?')
        dlg.addMessage('A project is already open: %s' % Display.getFront().getProject().getTitle())
        dlg.setInsets(15, 20, 0)
        dlg.addCheckbox('Re-montage existing layers?', False)
        dlg.setInsets(0, 10, 0)
        dlg.addChoice('First layer:', [l.getTitle() for l in tmp_layers], tmp_layers[0].getTitle())
        dlg.setInsets(0, 10, 0)
        dlg.addChoice('Last layer:', [l.getTitle() for l in tmp_layers], tmp_layers[-1].getTitle())
        dlg.setInsets(15, 20, 0)
        dlg.addCheckbox('Add additional images?', True)
        dlg.setInsets(0, 50, 0)
        dlg.addMessage('You will be prompted to choose a directory.')
        dlg.setInsets(15, 20, 0)
        dlg.addCheckbox('Lock existing sections for montage?', opts.append_lock_montage)
        dlg.setInsets(5, 20, 0)
        dlg.addCheckbox('Also lock for layer alignment?', opts.append_lock_layers)
        dlg.addMessage('Note: If a new project is started, all images will be used.')
        dlg.enableYesNoCancel('Use Existing Project','Start New Project')
        #dlg.hideCancelButton()
        dlg.showDialog()
        if dlg.wasOKed():  # Yes, we want to work with project.
            project = Display.getFront().getProject()
            layerset = project.getRootLayerSet()
            if dlg.getNextBoolean():
                layerlist = tmp_layers[dlg.getNextChoiceIndex():dlg.getNextChoiceIndex()+1]
            choose_dir = dlg.getNextBoolean()
            opts.append_lock_montage = dlg.getNextBoolean()
            opts.append_lock_layers = dlg.getNextBoolean()
            cal = layerset.getCalibrationCopy()
            opts.cal_z = cal.pixelDepth
            opts.cal_unit = cal.unit
            # Unable to store cal-table key in layerset properties, because
            # layerset.setProperties() doesn't seem to save w/ XML...
            cal_desc = [k for k,v in BASECAL_TABLE.items() if v == cal.pixelWidth]
            if cal_desc:
                opts.basecal = cal_desc[0]
            else:
                # Not sure what to do with this yet...
                logmsg('Unknown project calibration!?', False)
        elif dlg.wasCanceled():
            return
    
    # Choose directory.
    if choose_dir:
        folder = DirectoryChooser('Choose directory with TIFs ...').getDirectory()
        if not folder:
            logmsg('No directory chosen!', False)
            return

    class toggle_affine_listener (ItemListener):
        def itemStateChanged(self, e):
            cb_affine.setEnabled(cb_rigid.getState())

    # Check options.
    dlg = GenericDialog('Options')
    if project and project.getLoader().getProjectXMLPath():
        dlg.addStringField('Project Name:', os.path.splitext(os.path.basename(project.getLoader().getProjectXMLPath()))[0], 25)
        dlg.getStringFields()[0].setEnabled(False)
    else:
        dlg.addStringField('Project Name:', os.path.basename(os.path.abspath(folder)) + ' TrakEM2 Project', 25)
    dlg.setInsets(10, 20, 0)
    dlg.addNumericField('Section thickness:', opts.cal_z, 0, 3, opts.cal_unit)
    dlg.setInsets(10, 20, 0)
    dlg.addChoice('Base calibration:', sorted(BASECAL_TABLE.keys()), opts.basecal)
    if project:
        dlg.getNumericFields()[0].setEnabled(False)
        dlg.getChoices()[0].setEnabled(False)
    dlg.setInsets(10, 20, 0)
    dlg.addChoice('Montaging filter:', sorted(t2.IFILTERS.keys()), opts.ifilter_montage)
    dlg.setInsets(10, 20, 0)
    dlg.addChoice('Final image filter:', sorted(t2.IFILTERS.keys()), opts.ifilter)
    dlg.setInsets(0, 130, 0)
    dlg.addCheckbox('Force default min/max values before filtering?', opts.ifilter_defminmax)
    dlg.setInsets(0, 130, 0)
    dlg.addCheckbox('Apply final filter to existing images?', opts.ifilter_all)
    modeltmp = ['Translation', 'Rigid', 'Similarity']
    dlg.setInsets(10, 20, 0)
    dlg.addChoice('Model for lowmag patches:', modeltmp, modeltmp[opts.lowmag_model_index])
    dlg.setInsets(15, 20, 0)
    dlg.addCheckbox('Run in silent mode (alerts are suppresed)', opts.silent_mode)
    dlg.setInsets(5, 20, 0)
    dlg.addCheckbox('Manually position patches prior to montaging (*)', opts.option_do_manual)
    dlg.setInsets(0, 50, 0)
    dlg.addMessage('(only compare patches that overlap)')
    dlg.setInsets(5, 20, 0)
    dlg.addCheckbox('Isolate/mask central object in each new patch', opts.mask_central)
    dlg.getCheckboxes()[-1].setEnabled(False)
    dlg.setInsets(5, 20, 0)
    dlg.addCheckbox('Attempt rigid layer alignment', opts.silent_do_rigid)
    dlg.setInsets(5, 40, 0)
    cb_rigid = dlg.getCheckboxes()[-1]
    cb_rigid.addItemListener(toggle_affine_listener())
    dlg.addCheckbox('Attempt affine layer alignment', opts.silent_do_affine)
    cb_affine = dlg.getCheckboxes()[-1]
    cb_affine.setEnabled(False)
    dlg.setInsets(5, 20, 0)
    dlg.addCheckbox('Save project(s) when finished', opts.silent_do_save)
    dlg.setInsets(5, 20, 0)
    dlg.addCheckbox('Close project(s) when finished', opts.silent_close_proj)
    dlg.setInsets(10, 20, 0)
    dlg.addMessage('(*) not recommended with multiple projects')
    dlg.showDialog()
    if dlg.wasOKed():  # Store options in global config object.
        # Insist in numeric value for Z.
        opts.cal_z = dlg.getNextNumber()
        while math.isnan(opts.cal_z):
            opts.cal_z = redo_section_thickness()
            if opts.cal_z is None:
                return  # User cancelled.
        projname = dlg.getNextString()
        opts.basecal = dlg.getNextChoice()
        opts.cal_xy = BASECAL_TABLE[opts.basecal]
        opts.ifilter_montage = dlg.getNextChoice()
        opts.ifilter = dlg.getNextChoice()
        opts.ifilter_defminmax = dlg.getNextBoolean()
        opts.ifilter_all = dlg.getNextBoolean()
        opts.lowmag_model_index = dlg.getNextChoiceIndex()
        opts.silent_mode = dlg.getNextBoolean()
        opts.option_do_manual = dlg.getNextBoolean()
        opts.mask_central = dlg.getNextBoolean()
        opts.silent_do_rigid = dlg.getNextBoolean()
        opts.silent_do_affine = dlg.getNextBoolean()
        opts.silent_do_save = dlg.getNextBoolean()
        opts.silent_close_proj = dlg.getNextBoolean()
        if not opts.silent_do_rigid:
            opts.silent_do_affine = False
    else:
        return
    
    # Check if there are multiple project folders,
    # but don't do this if appending, won't make sense!
    if project is None:
        root, dirs, files = os.walk(folder).next()
        dirs[:] = filter(re_folder_filter, dirs)
        if len(dirs) > 0:
            dlg = GenericDialog('Multiple projects?')
            dlg.addMessage('Multiple folders found in root directory.')
            dlg.setInsets(10, 20, 0)
            dlg.addMessage('Consider each folder as a separate project?')
            dlg.setInsets(0, 20, 0)
            dlg.addMessage('If YES, any images in root folder will be ignored.')
            dlg.enableYesNoCancel()
            dlg.showDialog()
            if dlg.wasOKed():
                dlg = GenericDialog('Project Names')
                dlg.addMessage('Specify project names, or click OK to use defaults (recommended).')
                for d in dirs:
                    dlg.setInsets(15, 0, 0)
                    dlg.addMessage('Project Folder: ' + d)
                    dlg.addStringField('Project Name:', d + ' TrakEM2 Project', 25)
                dlg.showDialog()
                if dlg.wasOKed():
                    for d in dirs:
                        projname = dlg.getNextString()
                        build_file_list(os.path.join(root, d), project, projname, layerlist)
                    logmsg('Done with all projects!', not opts.silent_mode)
                elif dlg.wasCanceled():
                    logmsg('User cancelled.', False)
            elif dlg.wasCanceled():
                logmsg('User cancelled.', False)
            else:
                build_file_list(root, project, projname, layerlist)
        else:
            build_file_list(root, project, projname, layerlist)
    else:
        build_file_list(folder, project, projname, layerlist)
    return  ## end choose_dir()


# Start the script!!!
choose_dir()
logmsg('Finished.  See log for details.', False)