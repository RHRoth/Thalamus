# v.2024.02.26
# m@muniak.com

import numpy as np


# Convenience functions from: https://stackoverflow.com/questions/20546182/how-to-perform-coordinates-affine-transformation-using-python-part-2
pad = lambda x: np.hstack([x, np.ones((x.shape[0], 1))])
unpad = lambda x: x[:,:-1]


class affine3d:
    """ Quick AFFINE3D class modeled after Java7 java.awt.geom.AffineTransform.
        If something like this already exists in numpy, etc., I couldn't find it...
    """
    PRE_ = True

    def __init__(self, m=None):
        if m:
            self.m = m
        else:
            self.m = np.identity(4)

    
    def __repr__(self):
        return 'affine3d() matrix 4x4:\n' + np.array2string(self.m)

    
    def __str__(self):
        return self.__repr__()

    
    def reset(self):
        self.m = np.identity(4)

    
    def concatenate(self, t, pre=PRE_, center=None):
        center = np.array(center)  # Just in case.
        try:
            self.translate(*-center, pre=pre)
        except TypeError:
            pass
        if pre:
            self.m = t @ self.m
        else:
            self.m = self.m @ t
        try:
            self.translate(*center, pre=pre)
        except TypeError:
            pass

    
    def trig(self, th):
        quads = np.array([[ 1,  0],
                          [ 0,  1],
                          [-1,  0],
                          [ 0, -1]])
        div, mod = np.divmod(th, np.pi/2.)
        div = np.mod(div, 4).astype(int)
        # Threshold from Java7 java.awt.geom.AffineTransform documentation.
        if np.abs(mod) < 0.0000000211:
            return quads[div, :]
        else:
            return np.cos(th), np.sin(th)

    
    def translate(self, tx=0., ty=0., tz=0., pre=PRE_):
        t = np.array([[ 1., 0., 0.,  tx],
                      [ 0., 1., 0.,  ty],
                      [ 0., 0., 1.,  tz],
                      [ 0., 0., 0.,  1.]])
        self.concatenate(t, pre=pre, center=None)

    
    def scale(self, sx=1., sy=1., sz=1., pre=PRE_, center=None):
        t = np.array([[ sx, 0., 0.,  0.],
                      [ 0., sy, 0.,  0.],
                      [ 0., 0., sz,  0.],
                      [ 0., 0., 0.,  1.]])
        self.concatenate(t, pre=pre, center=center)

    
    def rotx(self, th=0., pre=PRE_, center=None):
        c, s = self.trig(th)
        t = np.array([[ 1., 0., 0.,  0.],
                      [ 0.,  c, -s,  0.],
                      [ 0.,  s,  c,  0.],
                      [ 0., 0., 0.,  1.]])
        self.concatenate(t, pre=pre, center=center)

    
    def roty(self, th=0., pre=PRE_, center=None):
        c, s = self.trig(th)
        t = np.array([[  c, 0.,  s,  0.],
                      [ 0., 1., 0.,  0.],
                      [ -s, 0.,  c,  0.],
                      [ 0., 0., 0.,  1.]])
        self.concatenate(t, pre=pre, center=center)

    
    def rotz(self, th=0., pre=PRE_, center=None):
        c, s = self.trig(th)
        t = np.array([[  c, -s, 0.,  0.],
                      [  s,  c, 0.,  0.],
                      [ 0., 0., 1.,  0.],
                      [ 0., 0., 0.,  1.]])
        self.concatenate(t, pre=pre, center=center)

    
    def shearx(self, hy=0., hz=0., pre=PRE_, center=None):
        t = np.array([[ 1., 0., 0.,  0.],
                      [ hy, 1., 0.,  0.],
                      [ hz, 0., 1.,  0.],
                      [ 0., 0., 0.,  1.]])
        self.concatenate(t, pre=pre, center=center)

    
    def sheary(self, hx=0., hz=0., pre=PRE_, center=None):
        t = np.array([[ 1., hx, 0.,  0.],
                      [ 0., 1., 0.,  0.],
                      [ 0., hz, 1.,  0.],
                      [ 0., 0., 0.,  1.]])
        self.concatenate(t, pre=pre, center=center)

    
    def shearz(self, hx=0., hy=0., pre=PRE_, center=None):
        t = np.array([[ 1., 0., hx,  0.],
                      [ 0., 1., hy,  0.],
                      [ 0., 0., 1.,  0.],
                      [ 0., 0., 0.,  1.]])
        self.concatenate(t, pre=pre, center=center)

    
    def inverse(self):
        return np.linalg.inv(self.m)

    
    def invert(self):
        self.m = self.inverse()

    
    def transform(self, points):
        """ Input POINTS is Nx3, because I prefer it that way.
        """
        t = np.ones((4, points.shape[0]))
        t[:3, :] = points.T
        res = self.m @ t
        return res[:3, :].T


def apply_affine(obj, at):
    try:
        obj.vertices = unpad(pad(obj.vertices) @ at.T)
    except AttributeError:
        obj = unpad(pad(obj) @ at.T)
    return obj