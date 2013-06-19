# edit.py
# buffer editing for both ST2 and ST3 that "just works"
# from https://raw.github.com/lunixbochs/SublimeXiki/74fa3e6b9b83f18da278e804e5b480e5511d6aef/edit.py

import sublime
import sublime_plugin

try:
    sublime.edit_storage
except AttributeError:
    sublime.edit_storage = {}

class EditStep:
    def __init__(self, cmd, *args):
        self.cmd = cmd
        self.args = args

    def run(self, view, edit):
        if self.cmd == 'callback':
            return self.args[0](view, edit)

        funcs = {
            'insert': view.insert,
            'erase': view.erase,
            'replace': view.replace,
        }
        func = funcs.get(self.cmd)
        if func:
            func(edit, *self.args)


class Edit:
    def __init__(self, view, name=None):
        self.view = view
        self.name = name
        self.steps = []

    def step(self, cmd, *args):
        step = EditStep(cmd, *args)
        self.steps.append(step)

    def insert(self, point, string):
        self.step('insert', point, string)

    def erase(self, region):
        self.step('erase', region)

    def replace(self, region, string):
        self.step('replace', region, string)

    def callback(self, func):
        self.step('callback', func)

    def run(self, view, edit, name):
        for step in self.steps:
            step.run(view, edit)

    def end(self):
        self.__exit__(None, None, None)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        view = self.view
        key = str(hash(tuple(self.steps)))
        sublime.edit_storage[key] = self.run
        view.run_command('apply_edit', {'key': key, 'name': self.name})


class apply_edit(sublime_plugin.TextCommand):
    def run(self, edit, key, name):
        sublime.edit_storage.pop(key)(self.view, edit, name)
