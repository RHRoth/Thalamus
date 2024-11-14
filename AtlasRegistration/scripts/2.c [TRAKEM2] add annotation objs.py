# Add annotation objects to TrakEM2 project.
# muniak@ohsu.edu
# 2024.11.06 - output verified for manuscript.

""" Note that fiducials are hard-coded in later script to be clicked in the following order:
    1) corpus callosum - anterior edge @ midline
    2) anterior commissure - posterior edge @ midline
    3) dentate gyrus - anterior emergence @ midline
    4) corpus callosum - posterior edge @ midline
    5) subcommissural organ - just posterior to end of habenula @ midline
    6) left skew-fiducial A (e.g., posterior edge of lateral geniculate nucleus)
    7) right skew-fiducial A
    8) left skew-fiducial B (e.g., posterior-most limit of arch of the stria terminalis)
    9) right skew-fiducial B
"""

# Custom script path (must contain rothetal_pkg folder).
PKG_PATH = r'<<FILEPATH_TO_SCRIPTS>>'

import sys

sys.path.insert(0, PKG_PATH)
from rothetal_pkg.fiji.t2.objs import add_to_node

root = add_to_node(None, 'base', 'thal')
add_to_node(root, 'area_list', 'rect')
add_to_node(root, 'ball', 'fiducials')
