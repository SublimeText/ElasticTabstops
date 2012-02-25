"""
UPDATE
	Use this command to reprocess the whole file. Shouldn't be necessary except
	in specific cases.
	
	{ "keys": ["super+j"], "command": "elastic_tabstops_update"},
"""


import sublime
import sublime_plugin
import re
from itertools import izip, izip_longest

def lines_in_buffer(view):
	row, col = view.rowcol(view.size())
	#"row" is the index of the last row; need to add 1 to get number of rows
	return row + 1

def get_selected_rows(view):
	selected_rows = set()
	for s in view.sel():
		begin_row,_ = view.rowcol(s.begin())
		end_row,_ = view.rowcol(s.end())
		map(selected_rows.add, range(begin_row, end_row+1))
	return selected_rows

def tabs_for_row(view, row):
	row_tabs = []
	for tab in re.finditer("\t", view.substr(view.line(view.text_point(row,0)))):
		row_tabs.append(tab.start())
	return row_tabs

def selection_columns_for_row(view, row):
	selections = []
	for s in view.sel():
		if s.empty():
			r, c =view.rowcol(s.a)
			if r == row:
				selections.append(c)
	return selections

def rightmost_selection_in_cell(selection_columns, cell_right_edge):
	rightmost = 0
	if len(selection_columns):
		rightmost = max([s if s <= cell_right_edge else 0 for s in selection_columns])
	return rightmost

def cell_widths_for_row(view, row):
	selection_columns = selection_columns_for_row(view, row)
	tabs = [-1] + tabs_for_row(view, row)
	widths = [0] * (len(tabs) - 1)
	line = view.substr(view.line(view.text_point(row,0)))
	for i in range(0,len(tabs)-1):
		left_edge = tabs[i]+1
		right_edge = tabs[i+1]
		rightmost_selection = rightmost_selection_in_cell(selection_columns, right_edge)
		cell = line[left_edge:right_edge]
		widths[i] = max(len(cell.rstrip()), rightmost_selection - left_edge)
	return widths

def find_cell_widths_for_block(view, row):
	cell_widths = []
	
	#starting row and backward
	row_iter = row
	while row_iter >= 0:
		widths = cell_widths_for_row(view, row_iter)
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
		widths = cell_widths_for_row(view, row_iter)
		if len(widths) == 0:
			break
		cell_widths.append(widths)
	
	return cell_widths, first_row

def adjust_row(view, edit, row, widths):
	changed = False
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
		
		changed = True
		
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
	return changed

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
	changed = False
	checked_rows = set()
	for row in rows:
		if row in checked_rows:
			continue
		
		cell_widths_by_row, row_index = find_cell_widths_for_block(view, row)
		set_block_cell_widths_to_max(cell_widths_by_row)
		for widths in cell_widths_by_row:
			checked_rows.add(row_index)
			changed |= adjust_row(view, edit, row_index, widths)
			row_index += 1
	return changed

class ElasticTabstopsListener(sublime_plugin.EventListener):
	pending = 0
	selected_rows_by_view = {}
	
	def set_pending(self, bool):
		self.pending = bool
	
	def on_modified(self, view):
		if self.pending:
			return
		
		changed = False
		selected_rows = self.selected_rows_by_view.get(view.id(), get_selected_rows(view))
		try:
			self.pending = 1
			
			translate = False
			if view.settings().get("translate_tabs_to_spaces"):
				translate = True
				view.settings().set("translate_tabs_to_spaces", False)
			
			edit = view.begin_edit()
			changed = process_rows(view, edit, selected_rows)
			
		finally:
			if translate:
				view.settings().set("translate_tabs_to_spaces",True)
			view.end_edit(edit)
			if changed:
				view.run_command("glue_marked_undo_groups")
			else:
				# We don't want to hold on to our mark in between calls,
				# otherwise undo will only undo between times that you've
				# affected the indentation
				view.run_command("unmark_undo_groups_for_gluing")
			view.run_command("maybe_mark_undo_groups_for_gluing")  #for the next time around
			self.pending = 0
	
	def on_selection_modified(self, view):
		self.selected_rows_by_view[view.id()] = get_selected_rows(view)
	def on_activated(self, view):
		self.selected_rows_by_view[view.id()] = get_selected_rows(view)

class ElasticTabstopsUpdateCommand(sublime_plugin.TextCommand):
	def run(self,edit):
		rows = range(0,lines_in_buffer(self.view))
		process_rows(self.view, edit, rows)


def set_pending(pending):
	for obj in sublime_plugin.all_callbacks['on_modified']:
		try:
			obj.set_pending(pending)
		except:
			pass

def asynchronous_pending_command(view, command_string):
	set_pending(True)
	view.run_command(command_string)
	set_pending(False)

class PendingCommandCommand(sublime_plugin.TextCommand):
	def run(self,edit,command):
		sublime.set_timeout(lambda : asynchronous_pending_command(self.view, command), 1)

class MoveByCellsCommand(sublime_plugin.TextCommand):
	def run(self, edit, direction, extend):
		new_regions = []
		for s in self.view.sel():
			line = self.view.substr(self.view.line(s.b))
			row, col = self.view.rowcol(s.b)
			print(line)
			if direction == "right":
				next_tab_col = line[col+1:].find('\t')
				if next_tab_col == -1:
					next_tab_col = len(line)
				else:
					next_tab_col += col + 1
			elif direction == "left":
				next_tab_col = line[:max(col-1, 0)].rfind('\t')
				if next_tab_col == -1:
					next_tab_col = 0
				else:
					next_tab_col += 1
			else:
				raise Exception("invalid direction")
				next_tab_col = s.b
			
			b = self.view.text_point(row, next_tab_col)
			
			if extend:
				new_regions.append(sublime.Region(s.a, b))
			else:
				new_regions.append(sublime.Region(b, b))
		sel = self.view.sel()
		sel.clear()
		for r in new_regions:
			sel.add(r)
