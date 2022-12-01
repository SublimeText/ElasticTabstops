"""
UPDATE
	Use this command to reprocess the whole file. Shouldn't be necessary except
	in specific cases.

	{ "keys": ["super+j"], "command": "elastic_tabstops_update"},
"""


import sublime
import sublime_plugin
import re
import sys
import time

if sys.version_info[0] < 3:
	from edit import Edit
	from itertools import izip, izip_longest
	zip = izip
	zip_longest = izip_longest
else:
	from ElasticTabstops.edit import Edit
	from itertools import zip_longest

# binary representation of all ST events
NEW               	= 1
CLONE             	= 2
LOAD              	= 4
PRE_SAVE          	= 8
POST_SAVE         	= 16
MODIFIED          	= 32
SELECTION_MODIFIED	= 64
ACTIVATED         	= 128
DEACTIVATED       	= 256

try:
  set_timeout = sublime.set_timeout_async
except AttributeError:
  set_timeout = sublime.set_timeout

def lines_in_buffer(view):
	row, col = view.rowcol(view.size())
	#"row" is the index of the last row; need to add 1 to get number of rows
	return row + 1

def get_selected_rows(view):
	selected_rows = set()
	for s in view.sel():
		begin_row,_ = view.rowcol(s.begin())
		end_row,_ = view.rowcol(s.end())
		# Include one row before and after the selection, to cover cases like
		# hitting enter at the beginning of a line: affect both the newly-split
		# block and the block remaining above.
		list(map(selected_rows.add, range(begin_row-1, end_row+1 + 1)))
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

def adjust_row(view, glued, row, widths):
	row_tabs = tabs_for_row(view, row)
	if len(row_tabs) == 0:
		return glued
	bias = 0
	location = -1

	for w, it in zip(widths,row_tabs):
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
			view.run_command("maybe_mark_undo_groups_for_gluing")
			glued = True
			with Edit(view, "ElasticTabstops") as edit:
				#put the spaces after the tab and then delete the tab, so any insertion
				#points behave as expected
				edit.insert(end_tab_point+1, (' ' * difference) + "\t")
				edit.erase(sublime.Region(end_tab_point, end_tab_point + 1))
			bias += difference
		if difference < 0 and ispaces >= -difference:
			view.run_command("maybe_mark_undo_groups_for_gluing")
			glued = True
			with Edit(view, "ElasticTabstops") as edit:
				edit.erase(sublime.Region(end_tab_point, end_tab_point + difference))
			bias += difference
	return glued

def set_block_cell_widths_to_max(cell_widths):
	starting_new_block = True
	for c, column in enumerate(zip_longest(*cell_widths, fillvalue=-1)):
		#add an extra -1 to the end so that the end of the column automatically
		#finishes a block
		column += (-1,)
		done = False
		for r, width in enumerate(column):
			if starting_new_block:
				block_start_row = r
				starting_new_block = False
				max_width = 0
			if width == -1:
				#block ended
				block_end_row = r
				for j in range(block_start_row, block_end_row):
					cell_widths[j][c] = max_width
				starting_new_block = True
			max_width = max(max_width, width)

def process_rows(view, rows):
	glued = False
	checked_rows = set()
	for row in rows:
		if row in checked_rows:
			continue

		cell_widths_by_row, row_index = find_cell_widths_for_block(view, row)
		set_block_cell_widths_to_max(cell_widths_by_row)
		for widths in cell_widths_by_row:
			checked_rows.add(row_index)
			glued = adjust_row(view, glued, row_index, widths)
			row_index += 1
	if glued:
		view.run_command("glue_marked_undo_groups")

def fix_view(view):
	# When modifying a clone of a view, Sublime Text will only pass in
	# the original view ID, which means we refer to the wrong selections.
	# Fix which view we have.
	active_view = sublime.active_window().active_view()
	if view == None:
		view = active_view
	elif view.id() != active_view.id() and view.buffer_id() == active_view.buffer_id():
		view = active_view
	return view

class ElasticTabstopsListener(sublime_plugin.EventListener):
	def __init__(self):
		self.view_events = {}

	def debounce(self, view, event_id):
		"""Invoke evaluation of changes after some idle time
			view     (View): The view to perform evaluation for
			event_id (int) : The event identifier """
		# based on https://github.com/jisaacks/GitGutter/blob/master/modules/events.py
		key = view.id()
		try:
			self.view_events[key].push(event_id)
		except KeyError:
			if view.buffer_id():
				new_listener = ViewEventListener(view)
				new_listener.push(event_id)
				self.view_events[key] = new_listener
			for vid in [vid for vid, listener in self.view_events.items() # collect garbage
				if listener.view.buffer_id() == 0]:
					del self.view_events[vid]

	# TODO: check if activated/selection asyncs bug and need to revert to the blocking version
	def on_activated_async         (self, view):
		self.debounce(view,ACTIVATED)
	def on_selection_modified_async(self, view):
		self.debounce(view,SELECTION_MODIFIED)
	def on_modified                (self, view):
		# user editing during the line-by-line tabstop fixing operation can bug by deleting/inserting a symbol; use the sync API to block it
		self.debounce(view,          MODIFIED)

class ViewEventListener(object):
	"""Queues and forwards view events to Commands
	A ViewEventListener object queues all events received from a view and starts a single Sublime timer to forward the event to Commands after some idle time. Prevents bloating Sublime API due to dozens of timers running for debouncing events
	"""
	def __init__(self, view):
		"""Initialize ViewEventListener object
		  view (View): The view the object is created for """

		self.view       	= view
		self.settings   	= view.settings()                               	#
		self.busy       	= False                                         	# flag: timer is running
		self.running    	= False                                         	# flag: modification is running
		self.events     	= 0                                             	# a binary combination of above events
		self.latest_time	= 0.0                                           	# latest time of append() call
		_delay          	= self.settings.get('eltab_debounce_delay',1000)	# config: debounce delay
		self.delay      	= max(200,_delay if _delay is not None else 0)  	# debounce delay in milliseconds
		self.selected_rows_by_view = {}

	def push(self, event_id):
		"""Push the event to the queue and start idle timer.
		Add the event identifier to 'events' and update the 'latest_time'. This marks an event to be received rather than counting the number of received events. The idle timer is started only, if no other one is already in flight.
		                	event_id (int): One of the event identifiers"""
		self.latest_time	 = time.time()
		self.events     	|= event_id
		if not self.busy:
			self.start_timer(self.delay)

	def start_timer(self, delay):
		"""Run commands after some idle time
		If no events received during the idle time → run the commands
		Else                                       → restart timer to check later
		Timer is stopped without calling the commands if a view is not visible to save some resources. Evaluation will be triggered by activating the view next time
			delay (int): The delay in milliseconds to wait until probably
				forward the events, if no other event was received in the meanwhile"""
		start_time = self.latest_time

		def worker():
			"""The function called after some idle time."""
			if start_time < self.latest_time:
				self.start_timer(self.delay)
				return
			self.busy = False
			if not self.is_view_visible():
				return
			# bitwise AND comparison to see which events were triggered during the delay
			if ACTIVATED          == ACTIVATED          & self.events:
				self.activated()
			if SELECTION_MODIFIED == SELECTION_MODIFIED & self.events:
				self.selection_modified()
			if MODIFIED           == MODIFIED           & self.events:
				self.modified()
			self.events = 0

		self.busy = True
		if   MODIFIED           == MODIFIED           & self.events:
			sublime.set_timeout(worker, delay) # force sync timeout
		else:
			set_timeout(worker, delay)         #      async timeout (if exists)

	def is_view_visible(self):
		"""Determine if the view is visible
		Only an active view of a group is visible
		Returns: bool: True if the view is visible in any window """
		window = self.view.window()
		if window:
			view_id = self.view.id()
			for group in range(window.num_groups()):
				active_view = window.active_view_in_group(group)
				if active_view and active_view.id() == view_id:
					return True
		return False

	def activated(self):
		view	= self.view
		view	= fix_view(view)
		self.selected_rows_by_view[view.id()] = get_selected_rows(view)

	def selection_modified(self):
		view	= self.view
		view	= fix_view(view)
		self.selected_rows_by_view[view.id()] = get_selected_rows(view)

	def modified(self):
		view      = self.view
		if self.running:
			return

		view = fix_view(view)

		history_item = view.command_history(1)[1]
		if history_item:
			if history_item.get                  ('name') == "ElasticTabstops":
				return
			if history_item.get('commands') and \
				 history_item['commands'][0][1].get('name') == "ElasticTabstops":
				return

		selected_rows = self.selected_rows_by_view.get(view.id(), set())
		selected_rows = selected_rows.union(get_selected_rows(view))

		try:
			self.running = True
			translate = False
			if self.settings.get("translate_tabs_to_spaces"):
				translate = True
				self.settings.set("translate_tabs_to_spaces", False)

			process_rows(view, selected_rows)

		finally:
			self.running = False
			if translate:
				self.settings.set("translate_tabs_to_spaces",True)


class ElasticTabstopsUpdateCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		rows = range(0,lines_in_buffer(self.view))
		process_rows(self.view, rows)


class MoveByCellsCommand(sublime_plugin.TextCommand):
	def run(self, edit, direction, extend):
		new_regions = []
		for s in self.view.sel():
			line = self.view.substr(self.view.line(s.b))
			row, col = self.view.rowcol(s.b)
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
