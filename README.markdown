Notes
-----
This plugin only works if you are indenting with tabs. Limitations in Sublime Text's API make it virtually impossible to use elastic tabstops with spaces.

Because Sublime Text does not allow variable-width tabs, this plugin works by inserting extra spaces before tab characters. This has two side-effects:

1. The file will have extra spaces in it, obviously.
1. The file will show up correctly in editors that don't support elastic tabstops. Bonus!

Keyboard shortcuts
------------------
ElasticTabstops includes keyboard shortcuts for navigating to the next and previous tab. This can be extremely useful if, for example, one has multiple selections on different rows.

By default, these shortcuts are `ctrl+alt+left` and `ctrl+alt+right`, and holding `shift` will extend the selection as expected.

Install
-------

This plugin is available through Package Control, which is available here:

    http://wbond.net/sublime_packages/package_control

Manual Install
--------------

Go to your Packages subdirectory under ST2's data directory:

* Windows: %APPDATA%\Sublime Text 2
* OS X: ~/Library/Application Support/Sublime Text 2
* Linux: ~/.config/sublime-text-2
* Portable Installation: Sublime Text 2/Data

Then clone this repository:

    git clone git://github.com/SublimeText/ElasticTabstops.git

That's it!

