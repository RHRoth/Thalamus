# fiji/t2/objs.py
# v.2020.09.29
# m@muniak.com
#
# Common object functions for TrakEM2.

# 2024.11.07 - Cleaned up for manuscript deposit.

from ini.trakem2.display import AreaList
from ini.trakem2.display import Ball
from ini.trakem2.display import Display
from ini.trakem2.display import Patch
from ini.trakem2.display import Polyline
from ini.trakem2.utils import ProjectToolbar
from java.awt import Color

from ..utils import logmsg
from .. import t2
import ..t2.canvas


def add_to_node(node, objtype, title='', objcolor=None, keep_multi=False):
    """ Add object to node in TrakEM2 project tree.
    """
    if node is None:
        # Need to set up root "folder" node first.
        project = Display.getFront().getProject()
        node = add_to_node(project.getRootProjectThing(), project.getRootTemplateThing().getType(), title)
        # Just want to return the root "folder" object.
        if objtype == 'base':
            return node
    elif isinstance(node, str):
        # If node is a string, we want the root folder to have this name (may already exist).
        node = add_to_node(None, 'base', node)
    project = node.getProject()
    project_tree = project.getProjectTree()
    if not title:
        title = objtype
    if node.hasChildren():
        objs = [obj for obj in node.getChildren() if obj.getType() == objtype]
        if not keep_multi:  # Skip only if same type and _similar_ title.
            objs = [obj for obj in objs if title in obj.getTitle()]  # Not bothering w/ regexp.
        if objs:
            if len(objs) > 1:
                logmsg('Weird, more than one Project Object of type "%s" called "%s" ...' % (objtype,title))
            return(objs[0])
    obj = node.createChild(objtype)
    if obj is None:  # Object does not exist in template, need to add.
        template = project.getRootTemplateThing()
        template_tree = project.getTemplateTree()
        template_tree.addNewChildType(template, objtype)
        obj = node.createChild(objtype)
    obj.setTitle(title)
    if objcolor:
        obj.getObject().setColor(objcolor)
    project_tree.updateList(node)
    project_tree.selectNode(obj, project_tree)
    return obj


def find_in_project(obj_name, project=None, obj_type=None, parent_name=None, select=True):
    """ Find named object in project.
    """
    if project is None:
        project = t2.get_project()
    root = project.getRootProjectThing()
    if parent_name:
        try:
            ## TODO: Potential danger of more than one match, but ignoring for this script.
            root = next(iter(root.findChildren(parent_name, None, False)))
        except StopIteration:
            return []
    things = root.findChildren(obj_name, None, False)
    if obj_type:  # Might be pointless?
        if obj_type == 'arealist': obj_type = 'area_list'  # TrakEM2 wants underscore.
        things = set(things).intersection(root.findChildrenOfTypeR(obj_type))
    # Only returns first item.
    if len(things) > 1:
        logmsg('More than one object named %s found, only returning first instance ...' % obj_name)
    try:
        obj = next(iter(things))
    except StopIteration:
        return None
    # Catch if object is a "folder", which cannot be selected and .getObject() would just be a string.
    if obj.getType() == 'anything':
        select = False
    else:
        obj = obj.getObject()
    # Select this object.
    if select:
        select_obj(obj)
    return obj


def find_type_in_project(obj_type, project=None, parent_name=None, select=False):
    """ Find all object of type in project.
    """
    if project is None:
        project = t2.get_project()
    root = project.getRootProjectThing()
    if parent_name:
        try:
            ## TODO: Potential danger of more than one match, but ignoring for this script.
            root = next(iter(root.findChildren(parent_name, None, False)))
        except StopIteration:
            return []
    things = root.findChildrenOfTypeR(obj_type)
    objs = [thing.getObject() for thing in things]
    if select and objs:
        select_obj(objs[0])
    return objs


def select_obj(obj):
    """ Select object.
    """
    display = t2.get_display()
    obj.setVisible(True)
    selection = display.getSelection()
    selection.clear()
    selection.add(obj)
    if isinstance(obj, AreaList):
        ProjectToolbar.setTool(ProjectToolbar.BRUSH)
    elif isinstance(obj, Ball):
        ProjectToolbar.setTool(ProjectToolbar.PEN)
    elif isinstance(obj, Patch):
        ProjectToolbar.setTool(ProjectToolbar.SELECT)
    elif isinstance(obj, Polyline):
        ProjectToolbar.setTool(ProjectToolbar.PEN)
    t2.canvas.reset()
    return