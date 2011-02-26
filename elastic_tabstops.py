import sublime
import sublime_plugin
import re
from itertools import izip, izip_longest

def lines_in_buffer(view):
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
  selected_rows_by_view = {}
  
  def get_selected_rows(self, view):
    selected_rows = set()
    for s in view.sel():
      begin_row,_ = view.rowcol(s.begin())
      end_row,_ = view.rowcol(s.end())
      for l in range(begin_row, end_row+1):
        selected_rows.add(l)
    return selected_rows
  
  def tabs_for_row(self, view, row):
    row_tabs = []
    for tab in re.finditer("\t", view.substr(view.line(view.text_point(row,0)))):
      row_tabs.append(tab.start())
    return row_tabs
  
  def find_max_cell_widths(self, view, row):
    cell_widths = [0] * len(self.tabs_for_row(view, row))
    
    #starting row and backward
    rightmost_cell = len(cell_widths) - 1
    row_iter = row
    while row_iter >= 0:
      line = view.substr(view.line(view.text_point(row_iter,0)))
      tabs = [-1] + self.tabs_for_row(view, row_iter)
      if len(tabs) == 1:
        break
      for i in range(0,len(tabs)-1):
        if i > rightmost_cell:
          break
        cell = line[tabs[i]+1:tabs[i+1]]
        if len(cell) == len(cell.rstrip()):
          cell_widths[i] = max(cell_widths[i],len(cell))
        else:
          cell_widths[i] = max(cell_widths[i],len(cell.rstrip())+1)
      row_iter -= 1
    
    #forward (not including starting row)
    rightmost_cell = len(cell_widths) - 1
    row_iter = row
    num_rows = lines_in_buffer(view)
    while row_iter < num_rows - 1:
      row_iter += 1
      line = view.substr(view.line(view.text_point(row_iter,0)))
      tabs = [-1] + self.tabs_for_row(view, row_iter)
      if len(tabs) == 1:
        break
      for i in range(0,len(tabs)-1):
        if i > rightmost_cell:
          break
        cell = line[tabs[i]+1:tabs[i+1]]
        if len(cell) == len(cell.rstrip()):
          cell_widths[i] = max(cell_widths[i],len(cell))
        else:
          cell_widths[i] = max(cell_widths[i],len(cell.rstrip())+1)
    
    return cell_widths
  
  def adjust_row(self, view, edit, row, start_row_tabs):
    row_tabs = self.tabs_for_row(view, row)
    if len(row_tabs) == 0:
      return 0
    bias = 0
    i = 0
    for st, it in izip(start_row_tabs,row_tabs):
      i += 1
      it += bias
      difference = st - it
      if difference == 0:
        continue
      
      end_tab_point = view.text_point(row, it)
      partial_line = view.substr(view.line(end_tab_point))[0:it]
      stripped_partial_line = partial_line.rstrip()
      ispaces = len(partial_line) - len(stripped_partial_line)
      print(st,it,end_tab_point,ispaces,difference)
      if difference > 0:
        view.insert(edit, end_tab_point+1, (' ' * difference) + "\t")
        view.erase(edit, sublime.Region(end_tab_point, end_tab_point + 1))
        bias += difference
      if difference < 0 and ispaces >= -difference:
        view.erase(edit, sublime.Region(end_tab_point, end_tab_point + difference))
        bias += difference
    return i
  
  def on_modified(self, view):
    if self.pending == 1:
      return
    
    selected_rows =  (self.selected_rows_by_view[view.id()] |
                      self.get_selected_rows(view))
    try:
      self.pending = 1
      edit = view.begin_edit()
      checked_rows = []
      for row in selected_rows:
        start_row_tabs = self.tabs_for_row(view, row)
        max_cell_widths = self.find_max_cell_widths(view, row)
        print("cw",max_cell_widths)
        tab_locations = [0] * len(max_cell_widths)
        for i,w in enumerate(max_cell_widths):
          if i == 0:
            tab_locations[i] = w
          else:
            tab_locations[i] = tab_locations[i - 1] + w + 1
        self.adjust_row(view, edit, row, tab_locations)
        
        start_row_tabs = self.tabs_for_row(view, row)
        row_iter = row
        while row_iter > 0:
          row_iter -= 1
          num_tabs = self.adjust_row(view, edit, row_iter, start_row_tabs)
          if num_tabs == 0:
            break
          print('r',row_iter)
          start_row_tabs = start_row_tabs[0:num_tabs]
        
        start_row_tabs = self.tabs_for_row(view, row)
        row_iter = row
        num_rows = lines_in_buffer(view)
        while row_iter < num_rows - 1:
          row_iter += 1
          num_tabs = self.adjust_row(view, edit, row_iter, start_row_tabs)
          if num_tabs == 0:
            break
          print('r',row_iter)
          start_row_tabs = start_row_tabs[0:num_tabs]
    finally:
      view.end_edit(edit)
      self.pending = 0
  
  def on_selection_modified(self, view):
    self.selected_rows_by_view[view.id()] = self.get_selected_rows(view)
