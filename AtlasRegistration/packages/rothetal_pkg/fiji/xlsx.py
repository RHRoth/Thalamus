# fiji/xlsx.py
# v.2020.11.09
# m@muniak.com
#
# Functions for reading info from Excel .xlsx files.
#
# Requires that poi.jar is loaded in ImageJ... easiest way
# is to enable "ResultsToExcel" from the list of update sites. 

# 2024.11.07 - Cleaned up for manuscript deposit.

import os
from ij.gui import GenericDialog
from ij.io import OpenDialog
from java.io import File

from .utils import logerror

# Attempt to load POI modules -- not loaded in FIJI by default, must be selected in updater!
try:
    from org.apache.poi.openxml4j.opc import OPCPackage
    from org.apache.poi.xssf.eventusermodel import XSSFReader
    from org.apache.poi.xssf.usermodel import XSSFWorkbook
    from org.apache.poi.ss.usermodel import CellType
    from org.apache.poi.ss.usermodel import DateUtil
except ImportError as e:
    logerror(ImportError, 'POI libraries must be loaded--select "ResultsToExcel" in update sites!', True)
    raise


def rows_as_dict(xlspath=None, sheet_str=None, header_row=3, add_sequence=False):
    # Select file if not provided or path is bad.
    if not xlspath or not os.path.isfile(xlspath):
        xlspath = OpenDialog('Select XLSX File').getPath()
        if not xlspath:
            return None
    
    # Read in workbook.
    pkg = OPCPackage.open(File(xlspath))
    workbook = XSSFWorkbook(pkg)
    pkg.revert()  # Close w/o saving.

    # If no sheet specified and multiple exist, ask user.
    if not sheet_str:
        if workbook.getNumberOfSheets() > 1:
            dlg = GenericDialog('Load XLSX Sheet')
            dlg.addChoice('Select Sheet:', [workbook.getSheetName(i) for i in range(workbook.getNumberOfSheets())], None)
            dlg.showDialog()
            if not dlg.wasOKed():
                return None
            sheet_str = dlg.getNextChoice()
        else:
            sheet_str = workbook.getSheetName(0)

    # Get sheet.
    s = workbook.getSheet(sheet_str)
    if not s:
        logerror(ValueError, 'Sheet name [ %s ] not found in %s ..!' % (sheet_str, xlspath))
    desc = [fetch_cell_contents(c) for c in s.getRow(header_row).cellIterator()]

    # 
    rows = []
    for seq,i in enumerate(range((header_row+1),(s.getLastRowNum()+1))):
        tmp = {}
        row = s.getRow(i)
        if row is None: # or row.getCell(0, row.MissingCellPolicy.RETURN_BLANK_AS_NULL) is None:
            continue
        for j,d in enumerate(desc):
            tmp[d] = fetch_cell_contents(row.getCell(j, row.MissingCellPolicy.RETURN_BLANK_AS_NULL))
        if not any(tmp.values()):  # Blank row in middle of sheet.
            continue
        if tmp:
            if add_sequence:
                tmp['sequence'] = seq
            rows.append(tmp)
#
#    # Find last row #
#    last_row = header_row + 1
#    while True:
#        c = s.getRow(last_row).getCell(0)
#        if not c or c.getCellType() == CellType.BLANK.getCode():
#            break
#        last_row += 1
#
#    # Iterate over rows
#    rows = []
#    for seq,i in enumerate(range((header_row+1),last_row)):
#        tmp = {}
#        # Generally, every field is returned as a string except for dates.
#        for d,c in zip(desc, s.getRow(i).cellIterator()):
#            if c.getCellType() == CellType.STRING.getCode():
#                tmp[d] = c.getStringCellValue()
#            elif c.getCellType() == CellType.NUMERIC.getCode() and DateUtil.isCellDateFormatted(c):
#                tmp[d] = c.getDateCellValue()
#            else:
#                tmp[d] = c.getRawValue()
#            if d == 'date':
#                print c.getCellType(), DateUtil.isCellDateFormatted(c), i, c, tmp['id'], tmp[d]
#        if add_sequence:
#            tmp['sequence'] = seq
#        rows.append(tmp)

    return rows, desc


def fetch_cell_contents(c):
    """ Get XLSX cell contents depending on cell type.
    """
    if c is None:
        return None
    elif c.getCellType() == CellType.STRING.getCode():
        return c.getStringCellValue()
    elif c.getCellType() == CellType.NUMERIC.getCode() and DateUtil.isCellDateFormatted(c):
        return c.getDateCellValue()
    else:
        return c.getRawValue()


def get_column(rows, name):
    return [r[name] for r in rows]


def find_by_desc(rows, value, desc='id', exact=False):
    if value is None:
        return [r for r in rows if not r[desc]]
    elif desc.lower().startswith('date'):  # TODO -- I forget if this is supposed to deal w/ DateTime objects?
        return [r for r in rows if value.equals(r[desc])]
    elif exact:
        return [r for r in rows if r[desc] and str(value) == r[desc]]
    else:
        return [r for r in rows if r[desc] and str(value) in r[desc]]


def sort_rows(rows, keys, reverse=False):
    # NOTE: keys are provided in heirarchical order (but will be applied in reverse order).
    if not isinstance(keys, list):
        keys = [keys]
    keys.reverse()
    for key in keys:
        rows.sort(key=lambda x: try_int(x[key]), reverse=reverse)
    return rows


def try_int(x):
    try:
        return int(x)
    except ValueError:
        return x