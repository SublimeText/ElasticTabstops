"""
UNDO
  In order for undo/redo and soft undo/soft redo to work, you'll need to
  redefine your commands. Put these in your keymap file, and if you're on
  Windows change "super" to "ctrl" in each one.
  
  { "keys": ["super+z"], "command": "undo_skip_on_modified"},
  { "keys": ["super+shift+z"], "command": "redo_skip_on_modified"},
  { "keys": ["super+u"], "command": "soft_undo_skip_on_modified" },
  { "keys": ["super+shift+u"], "command": "soft_redo_skip_on_modified" }
"""


import sublime
import sublime_plugin
import re
from itertools import izip, izip_longest

def lines_in_buffer(view):
  row, col = view.rowcol(view.size())
  #"row" is the index of the last row; need to add 1 to get number of rows
  return row + 1

def get_selected_rows( view):
  selected_rows = set()
  for s in view.sel():
    begin_row,_ = view.rowcol(s.begin())
    end_row,_ = view.rowcol(s.end())
    map(selected_rows.add, range(begin_row, end_row+1))
  return selected_rows

def tabs_for_row( view, row):
  row_tabs = []
  for tab in re.finditer("\t", view.substr(view.line(view.text_point(row,0)))):
    row_tabs.append(tab.start())
  return row_tabs

def cell_widths_for_row(view, row, allow_extra_space):
  tabs = [-1] + tabs_for_row(view, row)
  widths = [0] * (len(tabs) - 1)
  line = view.substr(view.line(view.text_point(row,0)))
  for i in range(0,len(tabs)-1):
    cell = line[tabs[i]+1:tabs[i+1]]
    cell_rstrip_len = len(cell.rstrip())
    if len(cell) == cell_rstrip_len or not allow_extra_space:
      widths[i] = cell_rstrip_len
    else:
      widths[i] = cell_rstrip_len+1
  return widths

def find_cell_widths_for_block(view, row, modified_rows):
  cell_widths = []
  
  #starting row and backward
  rightmost_cell = len(cell_widths) - 1
  row_iter = row
  while row_iter >= 0:
    widths = cell_widths_for_row(view, row_iter, row_iter in modified_rows)
    if len(widths) == 0:
      break
    cell_widths.insert(0, widths)
    row_iter -= 1
  first_row = row_iter + 1
  
  #forward (not including starting row)
  row_iter = row
  num_rows = lines_in_buffer(view)
  while row_iter < num_rows - 1:
    row_iter += 1
    widths = cell_widths_for_row(view, row_iter, row_iter in modified_rows)
    if len(widths) == 0:
      break
    cell_widths.append(widths)
  
  return cell_widths, first_row

def adjust_row(view, edit, row, widths):
  row_tabs = tabs_for_row(view, row)
  if len(row_tabs) == 0:
    return 0
  bias = 0
  location = -1
  for w, it in izip(widths,row_tabs):
    location += 1 + w
    it += bias
    difference = location - it
    if difference == 0:
      continue
    
    end_tab_point = view.text_point(row, it)
    partial_line = view.substr(view.line(end_tab_point))[0:it]
    stripped_partial_line = partial_line.rstrip()
    ispaces = len(partial_line) - len(stripped_partial_line)
    if difference > 0:
      #put the spaces after the tab and then delete the tab, so any insertion
      #points behave as expected
      view.insert(edit, end_tab_point+1, (' ' * difference) + "\t")
      view.erase(edit, sublime.Region(end_tab_point, end_tab_point + 1))
      bias += difference
    if difference < 0 and ispaces >= -difference:
      view.erase(edit, sublime.Region(end_tab_point, end_tab_point + difference))
      bias += difference

def set_block_cell_widths_to_max(cell_widths):
  starting_new_block = True
  for c, column in enumerate(izip_longest(*cell_widths, fillvalue=None)):
    #add an extra None to the end so that the end of the column automatically
    #finishes a block
    column += (None,)
    done = False
    for r, width in enumerate(column):
      if starting_new_block:
        block_start_row = r
        starting_new_block = False
        max_width = 0
      if width == None:
        #block ended
        block_end_row = r
        for j in range(block_start_row, block_end_row):
          cell_widths[j][c] = max_width
        starting_new_block = True
      max_width = max(max_width, width)

def process_rows(view, edit, rows):
  checked_rows = set()
  for row in rows:
    if row in checked_rows:
      continue
    
    cell_widths_by_row, row_index = find_cell_widths_for_block(view, row, rows)
    set_block_cell_widths_to_max(cell_widths_by_row)
    for widths in cell_widths_by_row:
      checked_rows.add(row_index)
      adjust_row(view, edit, row_index, widths)
      row_index += 1

class ElasticTabstopsListener(sublime_plugin.EventListener):
  pending = 0
  selected_rows_by_view = {}
  
  def set_pending(self, bool):
    self.pending = bool
  
  def on_modified(self, view):
    if self.pending:
      return
    
    selected_rows = (self.selected_rows_by_view[view.id()] |
                     get_selected_rows(view))
    try:
      self.pending = 1
      
      translate = False
      if view.settings().get("translate_tabs_to_spaces"):
        translate = True
        view.settings().set("translate_tabs_to_spaces", False)
      
      edit = view.begin_edit()
      process_rows(view, edit, selected_rows)
      
    finally:
      if translate:
        view.settings().set("translate_tabs_to_spaces",True)
      view.end_edit(edit)
      self.pending = 0
  
  def on_selection_modified(self, view):
    self.selected_rows_by_view[view.id()] = get_selected_rows(view)
  def on_activated(self, view):
    self.selected_rows_by_view[view.id()] = get_selected_rows(view)

class ElasticTabstopsUpdateCommand(sublime_plugin.TextCommand):
  def run(self,edit):
    rows = range(0,lines_in_buffer(self.view))
    process_rows(self.view, edit, rows)



class UndoSkipOnModifiedCommand(sublime_plugin.TextCommand):
  def run(self,edit):
    for obj in sublime_plugin.all_callbacks['on_modified']:
      try:
        obj.set_pending(True)
      except:
        pass
    self.view.run_command("undo")
    for obj in sublime_plugin.all_callbacks['on_modified']:
      try:
        obj.set_pending(False)
      except:
        pass

class RedoSkipOnModifiedCommand(sublime_plugin.TextCommand):
  def run(self,edit):
    for obj in sublime_plugin.all_callbacks['on_modified']:
      try:
        obj.set_pending(True)
      except:
        pass
    self.view.run_command("redo")
    for obj in sublime_plugin.all_callbacks['on_modified']:
      try:
        obj.set_pending(False)
      except:
        pass

class SoftUndoSkipOnModifiedCommand(sublime_plugin.TextCommand):
  def run(self,edit):
    for obj in sublime_plugin.all_callbacks['on_modified']:
      try:
        obj.set_pending(True)
      except:
        pass
    self.view.run_command("soft_undo")
    for obj in sublime_plugin.all_callbacks['on_modified']:
      try:
        obj.set_pending(False)
      except:
        pass

class SoftRedoSkipOnModifiedCommand(sublime_plugin.TextCommand):
  def run(self,edit):
    for obj in sublime_plugin.all_callbacks['on_modified']:
      try:
        obj.set_pending(True)
      except:
        pass
    self.view.run_command("soft_redo")
    for obj in sublime_plugin.all_callbacks['on_modified']:
      try:
        obj.set_pending(False)
      except:
        pass
