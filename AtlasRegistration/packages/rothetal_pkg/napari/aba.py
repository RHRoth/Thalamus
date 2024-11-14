# Functions relating to Allen Brain Atlas.
#
# v.2024.10.27
# m@muniak.com

# 2024.11.07 -- cleaned up for manuscript deposit
# 2024.10.27 -- fixed passing on of 'aba' variable in load_aba_3d() to load_aba_as_mesh()
# 2024.10.18 -- added option to use 'aba' instead of 'allen' for convenience
# 2024.08.15 -- fixed brainglobe import
# 2024.08.02 -- added ap_resample for get_aba_mask, which can correct Kim atlases to original 100um spacing w/o repeats
# 2024.07.31 -- added functionality for other brainglobe atlases, not just aba
# 2024.02.27 -- original

import numpy as np
try:
    from bg_atlasapi import BrainGlobeAtlas
except ModuleNotFoundError:
    from brainglobe_atlasapi import BrainGlobeAtlas

from .utils import is_int

RES = 25

def get_aba(res=RES, name='allen'):
    if name == 'aba': name = 'allen'
    return BrainGlobeAtlas('%s_mouse_%sum' % (name, res))


def get_aba_mask(structure, aba=None, res=RES, nanzero=False, hemi=False, ap_resample=False):
    if aba is None:
        aba = get_aba(res)
    else:
        res = aba.resolution[0]
    id = aba.structures[structure]['id']
    mask = aba.get_structure_mask(id)
    if ap_resample:
        mask = mask[::int(ap_resample / res), :, :]
    if hemi:
        mid = mask.shape[2] // 2
        if hemi.lower().startswith('l'):
            mask[:,:,:mid] = 0
        elif hemi.lower().startswith('r'):
            mask[:,:,mid:] = 0
        else:
            raise ValueError('Incorrect value for HEMI!  Must be <False, \'left\', or \'right\'>...')
    if nanzero:
        mask = mask.astype('float')
        mask[mask==0] = np.nan
    return mask


def add_mask_to_viewer(structure, viewer=None, show=True, aba=None, hemi=False, res=RES, **kwargs):
    if viewer is None:
        viewer = napari.current_viewer()
    if 'color' in kwargs:  # Convenience.
        kwargs['colormap'] = kwargs['color']
        _ = kwargs.pop('color')
    mask = get_aba_mask(structure, aba=aba, nanzero=True, hemi=hemi)
    if 'name' not in kwargs:
        kwargs['name'] = structure
    if show:
        h = viewer.add_image(mask, scale=[res]*3, **kwargs)
    return mask


def load_aba_as_mesh(name, aba=None, res=RES):
    from .vedo import loadobj2vedo  # A 'lil hacky to throw it down here, but avoids circular import.
    if not (isinstance(name, str) or is_int(name)):
        raise ValueError('Invalid value for "name"!')
    if aba is None:
        aba = get_aba(res)
    return loadobj2vedo(aba.structures[name]['mesh_filename'])



def load_aba_3d(name, aba=None, **kwargs):
    from .vedo import vedo2napari  # A 'lil hacky to throw it down here, but avoids circular import.
    if not (isinstance(name, str) or is_int(name)):
        raise ValueError('Invalid value for "name"!')
    if aba is None:
        aba = get_aba(res)
    return vedo2napari(load_aba_as_mesh(name, aba=aba), name=name, **kwargs)