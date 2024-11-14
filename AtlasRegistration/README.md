# Analysis pipeline for mapping thalamic cells to standardized atlases
2024-Nov-14 - <muniak@ohsu.edu>

***

## Introduction
The following Python scripts were used to go from raw confocal images of
brain slices to mapped cells in standardized atlases (as shown in
Figures 2 and S2). All scripts were executed in either FIJI (via the
Script Editor), or napari. Manual annotation/manipulation of data
occurred at a few stages—documented below—and the subsequent results are
also provided in this repository.

***

## Software Environments

### *FIJI*
<https://fiji.sc>  
Any current version (~2023 onwards) should work fine.
- Additional plugins to install:
    - *ImageScience*
    - *IJPB-plugins*

### *napari*
<https://napari.org>  
Installed via Anaconda package manager. The environment was created
using the following sequence:
> conda create -y -n napari -c conda-forge python=3.10  
> conda activate napari  
> conda install -c conda-forge napari pyqt numpy=1.26.4  
> conda update napari  
> conda install -c conda-forge brainreg  
> conda install -c conda-forge vedo  
> conda install -c conda-forge brainglobe-atlasapi  
> conda install -c conda-forge shapely  
> conda install -c conda-forge transforms3d  
> conda install opencv
> conda install -c conda-forge napari-aicsimageio #==0.7.2  \#\#\# <-- This last one is excecuted within the napari shell.  

***

## Data

Manual annotation/interpretation of the data occurs at a few stages, and
the results are preserved in the data folder. All other components of
the analysis pipeline can be generated from the scripts.

1.  Serial-section alignment of downsampled sections in the TrakEM2
    environment. The affine transform applied to each image is saved
    within the TrakEM2 XML project file.

2.  ROI cropping of image stack for cell counting. Used ROI bounds are
    saved in an Excel table.

3.  Manual cell counts are saved as their original FIJI Cell Counter
    plugin XML files.

4.  Annotation of fiducials for thalamus alignment. Fiducials were
    annotated as either AreaLists or Balls in the TrakEM2 environment,
    and their coordinates are also saved within the TrakEM2 XML project
    file.

5.  A list of atlas regions to show/hide/merge when creating the final
    figures are documented in Excel tables.

***

## Scripts

In addition to the following sequence of Python scripts, custom Python
modules were used. As these are not fully developed packages, they are
provided as standalone folders which are added to the system path at
runtime in the scripts. Each script has configuration variables at the
beginning for pointing to the locations of the package folders and data.

**1.a \[FIJI\] extract stats.py**

> Extract image statistics to facilitate level-balancing of confocal
images prior to downsampling and importing into TrakEM2 projects.

**1.b \[FIJI\] level and downsample.py**

> Use image statistics CSV to create level-balanced versions of confocal
images and downsample.

**2.a \[FIJI\] trakem2 import.py**

> Load downsampled stacks into TrakEM2 project for alignment, annotations,
etc.

**2.b \[TRAKEM2\] fix calibration.py**

> Quick fix to ensure TrakEM2 project calibration matches that of images
(prevents over/under-sampling of image pixels).

**2.c \[TRAKEM2\] add annotation objs.py**

> Add annotation elements to TrakEM2 project.

**2.d \[TRAKEM2\] arealist annotation helper.py**

> Helper script to modify AreaLists while annotating TrakEM2 project.

**3.a \[TRAKEM2\] export transformed hyperstack.py**

> Export full-resolution and original bit-depth hyperstack of confocal
images, but images are aligned according to transformations from TrakEM2
project.

**3.b \[TRAKEM2\] export fiducial coordinates.py**

> Export fiducial coordinates to CSV.

**4.a \[TRAKEM2\] cell counts to aligned coordinates \_ brains
2-7.py**

> Transform Cell Counter coordinates from sub-stack coordinates to brain
coordinates space, as dictated by TrakEM2 project alignment. For Brains
2-7 where counting occurred post-alignment.

**4.b \[FIJI\] extract image dims.py**

> Extract dimensions of confocal images to help correct cell count
locations in script 4.c.

**4.c \[TRAKEM2\] cell counts to aligned coordinates \_ brains
8-11.py**

> Transform Cell Counter coordinates from sub-stack coordinates to brain
coordinates space, as dictated by TrakEM2 project alignment. For Brains
8-11 where counting occurred pre-alignment.

**5.a \[FIJI\] get pixel intensity for each cell.py**

> Get approximate labeling intensity of each counted cell to facilitate
filtering of dataset by relative intensity.

**5.b \[PYTHON\] add norm column.py**

> Add normalized intensity values to each CSV column.

**6.a \[NAPARI\] extract aba fiducials.py**

> Automatically extract alignment fiducials from ABA atlas, in CCFv3
space.

**6.b \[NAPARI\] extract pax-kim fiducials.py**

> Automatically extract alignment fiducials from Paxinos/Kim atlas (some
regions have different IDs), in CCFv3 space.

**7. \[NAPARI\] align brain using fiducials.py**

> Align experimental brain to atlas coordinates using fiducials.

**8.a \[NAPARI\] assign cells to atlas structures.py**

> Map counted cells to atlas structures using alignments.

**8.b \[NAPARI\] average cell assignments.py**

> Perform stats on cell assignments.

**9.a \[NAPARI\] output used atlas ontology list.py**

> Generate list of all possible atlas structures that could be shown in
specific 2D plates.

**9.b \[NAPARI\] generate 2D + 3D figures.py**

> Generate raw elements for 2D and 3D figures that show mapped cells in
atlas space.

**9.c \[NAPARI\] generate ABA outlines on slice.py**

> Generate outlines of ABA mapped to a brain slice for figure.

***

Questions? <muniak@ohsu.edu>