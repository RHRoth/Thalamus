# Custom functions specific to thalamus mapping.
#
# v.2024.08.14
# m@muniak.com

# 2024.11.07 -- cleaned up for manuscript deposit
# 2024.08.14 -- added 'atlas' key to get_brain_coords to allow for Kim alignment.
# 2024.10.16 -- added method to filter coordinates based on intensity values in _cellcoords.csv

import os
import napari
import numpy as np
import pandas as pd
from shapely import LinearRing
from shapely import LineString

from .affine3d import apply_affine

def axis_length_spanning_volume_percent_areas(mesh, steps, axis=0, lo=0.01, hi=0.99, tol=0.0001):
    # Terrible name, sorry.
    spacing = steps[1] - steps[0]
    dims = [i for i in range(3) if i != axis]
    areas = [abs(poly_area(a.vertices)) for step in steps for a in mesh.intersect_with_plane(origin=(step, 0, 0), normal=(1, 0, 0)).join_segments(tol=tol) if a]
    vols = np.array(areas) * spacing
    cs = np.cumsum(vols) / np.sum(vols)
    tf = np.flatnonzero(np.bitwise_and(cs >= lo, cs <= hi))
    idx_lo = np.amin(tf)
    if idx_lo > 0:
        idx_lo -= (cs[idx_lo] - lo) / (cs[idx_lo] - cs[idx_lo - 1])
    idx_hi = np.amax(tf)
    if idx_hi < (len(cs) - 1):
        idx_hi += (hi - cs[idx_hi]) / (cs[idx_hi + 1] - cs[idx_hi])
    return (idx_hi - idx_lo) * spacing
    

def axis_length_spanning_volume_percent_binarized(mesh, axis=0, lo=0.01, hi=0.99, spacing=40, slices=[slice(None)]*3):
    # Terrible name, sorry.
    binz = mesh.binarize(spacing=[spacing]*3).tonumpy()
    s = np.sum(binz[slices[0], slices[1], slices[2]], axis=tuple(i for i in range(binz.ndim) if i != axis))
    cs = np.cumsum(s) / np.sum(s)
    tf = np.flatnonzero(np.bitwise_and(cs >= lo, cs <= hi))
    idx_lo = np.amin(tf)
    if idx_lo > 0:
        idx_lo -= (cs[idx_lo] - lo) / (cs[idx_lo] - cs[idx_lo - 1])
    idx_hi = np.amax(tf)
    if idx_hi < (len(s) - 1):
        idx_hi += (hi - cs[idx_hi]) / (cs[idx_hi + 1] - cs[idx_hi])
    return idx_hi - idx_lo


def get_slice_offsets_center_of_mass(ref, obj, zs, at=None):
    xy_offsets = np.zeros((len(zs), 3))
    if at is None:
        at = np.eye(4)
    obj = apply_affine(obj, at)
    for i, z in enumerate(zs):
        slice_ref = ref.intersect_with_plane(origin=(z, 0, 0), normal=(1, 0, 0)).join_segments(tol=0.0001)
        if len(slice_ref) == 0:
            continue
        elif len(slice_ref) > 1:
            print('More than one line!  Using longest one...')
            slice_ref = sorted(slice_ref, key=lambda x: x.length(), reverse=True)
        slice_obj = obj.intersect_with_plane(origin=(z, 0, 0), normal=(1, 0, 0)).join_segments(tol=0.0001)
        if len(slice_obj) == 0:
            continue
        elif len(slice_obj) > 1:
            print('More than one line!  Using longest one...')
            slice_obj = sorted(slice_obj, key=lambda x: x.length(), reverse=True)
        xy_offsets[i, 1:] = poly_com(slice_ref[0].vertices, x_col=1, y_col=2) - poly_com(slice_obj[0].vertices, x_col=1, y_col=2)
    return xy_offsets


def get_slice_offsets_upper_left(ref, obj, zs, at=None):
    """ THIS ONE ALIGNS UPPER-MEDIAL CORNER """
    xy_offsets = np.zeros((len(zs), 3))
    if at is None:
        at = np.eye(4)
    obj = apply_affine(obj, at)
    for i, z in enumerate(zs):
        slice_ref = ref.intersect_with_plane(origin=(z, 0, 0), normal=(1, 0, 0)).join_segments(tol=0.0001)
        if len(slice_ref) == 0:
            continue
        elif len(slice_ref) > 1:
            print('More than one line!  Using longest one...')
            slice_ref = sorted(slice_ref, key=lambda x: x.length(), reverse=True)
        slice_obj = obj.intersect_with_plane(origin=(z, 0, 0), normal=(1, 0, 0)).join_segments(tol=0.0001)
        if len(slice_obj) == 0:
            continue
        elif len(slice_obj) > 1:
            print('More than one line!  Using longest one...')
            slice_obj = sorted(slice_obj, key=lambda x: x.length(), reverse=True)
        xy_offsets[i, 1:] = np.array(slice_ref[0].bounds()[2::2]) - np.array(slice_obj[0].bounds()[2::2])
    return xy_offsets


def poly_area(p, x_col=1, y_col=2):
        """ Area of NON-INTERSECTING polygon.
        
            Point array P could have other dimensions, so must specify 
            which ones to use for calculation.
        """
        p = np.array(p)
        n = p.shape[0]
        x = np.hstack((p[:, x_col], p[0, x_col]))
        y = np.hstack((p[:, y_col], p[0, y_col]))
        return 0.5 * np.sum((x[:n] * y[1:]) - (x[1:] * y[:n]))


def poly_com(p, x_col=1, y_col=2):
    """ Center of mass of NON-INTERSECTING polygon.
    
        Point array P could have other dimensions, so must specify 
        which ones to use for calculation.
    """
    p = np.array(p)
    n = p.shape[0]
    x = np.hstack((p[:, x_col], p[0, x_col]))
    y = np.hstack((p[:, y_col], p[0, y_col]))
    A = 0.5 * np.sum((x[:n] * y[1:]) - (x[1:] * y[:n]))
    Mx = np.sum((x[:n] + x[1:]) * ((x[:n] * y[1:]) - (x[1:] * y[:n]))) / 6.
    My = np.sum((y[:n] + y[1:]) * ((x[:n] * y[1:]) - (x[1:] * y[:n]))) / 6.
    return np.array((Mx / A, My / A))


def sample_xy_span_at_z(mesh, z, steps=np.arange(0.05, 1.0, 0.1), tol=0.0001, return_mean=False):
    # Default is 0.05, 0.15 ... 0.95.
    n = len(steps)
    s = mesh.intersect_with_plane(origin=(z,0,0), normal=(1,0,0)).join_segments(tol=tol)
    if len(s) == 0:
        return None, None
    elif len(s) > 1:
        print('More than one line!  Using longest one...')
        s = sorted(s, key=lambda x: x.length(), reverse=True)
    s = s[0]
    bounds_0 = s.bounds()[2:4]
    bounds_1 = s.bounds()[4:6]
    lim_0 = np.diff(bounds_0)
    lim_1 = np.diff(bounds_1)
    lr = LinearRing(s.vertices[:, 1:])
    dim_0_lengths = np.zeros(n)
    dim_1_lengths = np.zeros(n)
    for i in range(n):
        # dim 0
        d = bounds_0[0] + (lim_0 * steps[i])
        p = LineString(((d, bounds_1[0]), (d, bounds_1[1]))).intersection(lr)
        dim_0_lengths[i] = abs(p.geoms[1].y - p.geoms[0].y)
        # dim 1
        d = bounds_1[0] + (lim_1 * steps[i])
        p = LineString(((bounds_0[0], d), (bounds_0[1], d))).intersection(lr)
        dim_1_lengths[i] = abs(p.geoms[1].x - p.geoms[0].x)
    if return_mean:
        return np.mean(dim_0_lengths), np.mean(dim_1_lengths)
    else:
        return dim_0_lengths, dim_1_lengths


def span_vol(mesh, steps, axis=0, tol=0.0001):
    # Terrible name, sorry.
    spacing = steps[1] - steps[0]
    dims = [i for i in range(3) if i != axis]
    areas = [abs(poly_area(a.vertices)) for step in steps for a in mesh.intersect_with_plane(origin=(step, 0, 0), normal=(1, 0, 0)).join_segments(tol=tol) if a]
    return np.sum(np.array(areas) * spacing)


def get_brain_coords(b, path, res, atlas='', filter_column=None, filter_method=None, filter_threshold=0.02):  # '' == aba default
    cc = filter_brain_coords(b, path, filter_column, filter_method, filter_threshold)
    at = np.asarray(pd.read_csv(os.path.join(path, 'brain%d_at_%s_%dum.csv' % (b, atlas, res))))
    txy = pd.read_csv(os.path.join(path, 'brain%d_txy_%s_%dum.csv' % (b, atlas, res)), index_col='z')
    return apply_affine(cc - np.asarray(txy.loc[cc[:,0]]), np.linalg.inv(at))


def filter_brain_coords(b, path, column=None, method='rank', threshold=0.02):
	cc = pd.read_csv(os.path.join(path, 'brain%d_cellcoords.csv' % b))
	if column is None:
		idx = cc.index
	else:
		if method == 'rank':
			cutoff = np.floor(threshold * len(cc)).astype(int)
		elif method == 'intensity':
			vmin = np.amin(cc[column])
			vmax = np.amax(cc[column])
			cutoff = np.sum(cc[column] <= (vmin + (threshold * (vmax - vmin)))).astype(int)
		idx = cc.sort_values(column).index[cutoff:]
	return np.asarray(cc.loc[idx, ['AP', 'DV', 'LM']])


def get_brain_color(b, path, norm=True):
    c = pd.read_csv(os.path.join(path, 'colors.csv'), index_col='id').loc[b, :]
    if norm:
        c /= 255
    return np.array(c)


def view_brain_coords(b, path, res, size=50., atlas='', filter_column=None, filter_method=None, filter_threshold=0.02, **kwargs):
    coords = get_brain_coords(b, path, res, atlas=atlas, filter_column=filter_column, filter_method=filter_method, filter_threshold=filter_threshold)
    color = get_brain_color(b, path)
    h = napari.current_viewer().add_points(coords, size=size, face_color=color, name='brain%d' % b, **kwargs)
    return h


def view_binned_brain_coords(b, path, res, bin=250, bin_vmax=0.1, atlas='', filter_column=None, filter_method=None, filter_threshold=0.02, **kwargs):
    coords, counts = np.unique(np.round(get_brain_coords(b, path, res, atlas=atlas, filter_column=filter_column, filter_method=filter_method, filter_threshold=filter_threshold) / bin).astype(int), axis=0, return_counts=True)
    coords *= bin
    counts = counts / np.sum(counts) / bin_vmax * bin
    color = get_brain_color(b, path)
    h = napari.current_viewer().add_points(coords, size=counts, face_color=color, name='brain%d dens' % b, **kwargs)
    return h


def view_binned_brain_coords_all(brain_nums, path, res, bin=250, bin_vmax=0.1, face_color='w', atlas='', filter_column=None, filter_method=None, filter_threshold=0.02, **kwargs):
    c_dict = {}
    for b in brain_nums:
        coords, counts = np.unique(np.round(get_brain_coords(b, path, res, atlas=atlas, filter_column=filter_column, filter_method=filter_method, filter_threshold=filter_threshold) / bin).astype(int), axis=0, return_counts=True)
        counts = counts / np.sum(counts)
        for coord, count in zip(tuple(map(tuple, coords)), counts):
            c_dict[coord] = c_dict.get(coord, 0) + count
    coords = c_dict.keys()
    counts = np.array([c_dict[coord] for coord in coords]) / len(brain_nums) / bin_vmax * bin
    coords = np.array(list(coords)) * bin
    h = napari.current_viewer().add_points(coords, size=counts, name='average dens', face_color=face_color, **kwargs)
    return h


def show_scale_dots(scales, bin=250, bin_vmax=0.1, face_color='k', **kwargs):
    viewer = napari.current_viewer()
    scales = np.array(scales)  # Just in case.
    n = len(scales)
    s = n // 2
    ticks = np.arange(-s, -s + n, 1)[np.newaxis, ...]
    coords = np.array(viewer.camera.center) + viewer.camera.up_direction * (ticks * bin).T
    scales = scales / bin_vmax * bin
    h = viewer.add_points(coords, size=scales, face_color=face_color, name='scale', **kwargs)
    return h


def query_brain_coords(b, path, aba, res, atlas='', filter_column=None, filter_method=None, filter_threshold=None):
    cc = get_brain_coords(b, path, res, atlas=atlas, filter_column=filter_column, filter_method=filter_method, filter_threshold=filter_threshold)
    cc = np.round(cc / aba.resolution[0]).astype(int)
    vals = aba.annotation[cc[:,0], cc[:,1], cc[:,2]]
    ids, counts = np.unique(vals, return_counts=True)
    return ids, counts


def get_camera():
    camera = dict()
    for item in ['center', 'zoom', 'angles', 'perspective']:
        camera[item] = getattr(napari.current_viewer().camera, item)
    return camera
    

def set_camera(camera):
    for item in ['center', 'zoom', 'angles', 'perspective']:
        setattr(napari.current_viewer().camera, item, camera[item])