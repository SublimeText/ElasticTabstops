import sublime
import sublime_plugin
import re

def lines_in_buffer(view):
  #todo: maybe this is wrong? do i need size - 1?
  row, col = view.rowcol(view.size())
  #"row" is the index of the last row; need to add 1 to get number of rows
  return row + 1

def spaces_for_view(view):
  regions = view.get_regions("ElasticTabstopsCommand")
  spaces_by_line = [[] for i in range(lines_in_buffer(view))]
  for region in regions:
    row,col = view.rowcol(region.begin())
    spaces_by_line[row].append(col)
  return spaces_by_line

def highlight_cell(view, text_point, delta):
  row, col = view.rowcol(text_point)
  spaces_by_line = spaces_for_view(view)
  
  right_edge = 0
  for i,sp in enumerate(spaces_by_line[row]):
    if sp > col:
      right_edge = sp - delta
      break
  if right_edge == 0:
    #not a cell
    return
  
  left_edge = 0
  if i != 0:
    left_edge = spaces_by_line[row][spaces_by_line[row].index(right_edge + delta) - 1]
  
  regions = []
  
  #backward
  iter_row = row - 1
  while iter_row >= 0:
    if right_edge in spaces_by_line[iter_row]:
      regions.insert(0, sublime.Region(view.text_point(iter_row,left_edge),view.text_point(iter_row,right_edge)))
    else:
      break
    iter_row -= 1
  
  #current row
  regions.append(sublime.Region(view.text_point(row,left_edge),view.text_point(row,right_edge+delta)))
  
  #forward
  iter_row = row + 1
  num_lines_in_buffer = lines_in_buffer(view)
  while iter_row < num_lines_in_buffer:
    if right_edge in spaces_by_line[iter_row]:
      regions.append(sublime.Region(view.text_point(iter_row,left_edge),view.text_point(iter_row,right_edge)))
    else:
      break
    iter_row += 1
  
  view.add_regions("ElasticTabstopsCell", regions, "string", sublime.DRAW_EMPTY)
  return regions

class ElasticTabstopsCommand(sublime_plugin.TextCommand):
  spaces_re = re.compile(r"(?<=  )(?=[^ ])")
  
  def indent_line(self, line_number, starting_col, amount):
    self.view.insert(view.text_point(line_number, starting_col), ' ' * amount)
  
  def indent_block(self, line_numbers, starting_col, amount):
    for line_number in line_numbers:
      indent_line(line_number, starting_col, amount)
  
  def run(self, edit):
    all_spaces = []
    
    all_spaces = self.view.find_all(self.spaces_re.pattern)
    spaces_by_line = spaces_for_view(self.view)
    for space in all_spaces:
      row, col = self.view.rowcol(space.end())
      spaces_by_line[row].append(col)
    # forward
    for i,spaces in enumerate(spaces_by_line):
      next_index = i+1
      if next_index == len(spaces_by_line):
        break
      if 0 == len(spaces_by_line[next_index]):
        continue
      for space in spaces:
        line = self.view.substr(self.view.line(self.view.text_point(next_index,0)))
        if  (space not in spaces_by_line[next_index] and
            space < len(line) and
            ((not space > 2) or line[space-2:space] == "  ")):
          spaces_by_line[next_index].append(space)
    
    # reverse
    for i,spaces in reversed(list(enumerate(spaces_by_line))):
      next_index = i-1
      if next_index == 0:
        break
      if 0 == len(spaces_by_line[next_index]):
        continue
      for space in spaces:
        line = self.view.substr(self.view.line(self.view.text_point(next_index,0)))
        if (space not in spaces_by_line[next_index] and
            space < len(line) and
            ((not space > 2) or line[space-2:space] == "  ")):
          spaces_by_line[next_index].append(space)
    for n,line in enumerate(spaces_by_line):
      line.sort()
      print n,line
    all_spaces = []
    for row,line in enumerate(spaces_by_line):
      for col in line:
        all_spaces.append(sublime.Region( *([self.view.text_point(row,col)]*2) ))
    print all_spaces
    self.view.add_regions("ElasticTabstopsCommand", all_spaces, "comment", sublime.DRAW_EMPTY)
    highlight_cell(self.view, self.view.sel()[0].begin(), 0)


class ElasticTabstopsListener(sublime_plugin.EventListener):
  pending = 0
  text_points_by_view = {}
  
  def on_modified(self, view):
    if self.pending == 1:
      return
    
    text_points = self.text_points_by_view[view.id()]
    deltas = [0 for t in text_points]
    changes = ['' for t in text_points]
    bias = 0
    for i,(t,s) in enumerate(zip(text_points,view.sel())):
      s = s.end()
      delta = s - t - bias
      deltas[i] = delta
      # if delta > 0:
      #   print("Selection {0}: inserted {1} chars".format(i,delta))
      # if delta < 0:
      #   print("Selection {0}: deleted  {1} chars".format(i,-(delta)))
      bias = s - t
    
    print('deltas',deltas)
    
    #check additions first
    for i,(d,s) in enumerate(zip(deltas,view.sel())):
      if d > 0:
        changes[i] = view.substr(sublime.Region(s.end(),s.end()-delta))
    
    self.pending = 1
    view.run_command('undo')
    self.pending = 0
    
    #now that we've undone, we can see what was deleted
    for i,(d,s) in enumerate(zip(deltas,view.sel())):
      if d < 0:
        changes[i] = view.substr(sublime.Region(s.end(),s.end()+delta))
    
    self.pending = 1
    # view.run_command('redo')
    self.pending = 0
    
    print(changes)
    try:
      self.pending = 1
      edit = view.begin_edit()
      for d,c,t in zip(deltas,changes,text_points):
        if delta > 0:
          view.insert(edit, t, c)
        else:
          view.erase(edit, sublime.Region(s.end(),s.end()+delta))
      
      regions = highlight_cell(view, view.sel()[0].begin(), deltas[0])
      if not regions:
        # print("none")
        return
      row, col = view.rowcol(view.sel()[0].begin())
      
      for region in reversed(regions):
        point = region.end() - 1
        r, c = view.rowcol(point)
        if row != r:
          if(deltas[0] > 0):
            view.insert(edit, point, " " * deltas[0])
          else:
            view.erase(edit, sublime.Region(point + deltas[0], point))
    finally:
      view.end_edit(edit)
      self.pending = 0
  
  def on_selection_modified(self, view):
    self.text_points_by_view[view.id()] = [s.end() for s in view.sel()]
