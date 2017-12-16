import builtins
import ctypes
import inspect
import logging
import os
import pydoc
import readline
import rlcompleter
import sys
import textwrap
import threading
import time
import traceback

import __main__

try:
    import tkinter as tk
except:
    import Tkinter as tk


LOGGER = logging.getLogger(__name__) # logging is hard because our prints may get eaten

def title(s):
    '''
        Sets the title. Used for testing.
    '''
    if os.name == 'nt':
        ctypes.windll.kernel32.SetConsoleTitleA(ctypes.c_char_p(str(s).encode()))

def getFromNamespaceByName(namespace, name):
    if name in namespace:
        return namespace[name]
    else:
        # get the right side of the equals sign
        if '=' in name:
            name = name.split('=')[-1].strip()
            return getFromNamespaceByName(namespace, name)
        if name.count('.') >= 1:
            moduleName, rest = name.split('.', 1)
            if moduleName in namespace:
                module = namespace[moduleName]
                try:
                    return eval(name, namespace)
                except Exception as ex:
                    LOGGER.debug("Unable to find %s in namespace. Full exception: \n%s" % (name, traceback.format_exc()))
                    title('could not eval?') # TODO... we can probably fix some of these things.
                    return None

        return None # no idea whats going on.

def getDocToPrint(func):
    """
    funcArgsString = getFunctionArgsString(func)
    if funcArgsString:
        if hasattr(func, '__name__'):
            name = func.__name__
        elif hasattr(func, '__class__'):
            name = func.__class__.__name__
        else:
            name = '?'
        retStr = name + getFunctionArgsString(func)
    else:
        return None

    doc = pydoc.plain(pydoc.render_doc(func))
    if doc:
        retStr += os.linesep + "  " + doc.replace("\n", "\n  ").rstrip("\n")
    return retStr
    """
    doc = ''
    if inspect.isclass(func):
        doc += pydoc.plain(pydoc.render_doc(func.__init__))
    doc += pydoc.plain(pydoc.render_doc(func))
    return doc

def getPossibleImportsFromPath(path):
    possibleImports = set()
    if os.path.isdir(path):
        for file in os.listdir(path):
            fullPathToFile = os.path.join(path, file)
            if os.path.isfile(fullPathToFile):
                ext = file.split('.')[-1].upper()
                if ext in ['PY', 'PYC', 'PYD']:
                    possibleImports.add(file.split('.')[0])
            elif os.path.isdir(fullPathToFile):
                # check if this directory is a module
                initFile = os.path.join(fullPathToFile, '__init__.py')
                if os.path.isfile(initFile):
                    possibleImports.add(file)

    return possibleImports

def getAllPossibleImports(removePrivate=False, currentModuleOrFolder=None):
    possibleImports = set()
    for directory in sys.path:

        # if they have sys. then we should show sys.path (example)
        if currentModuleOrFolder is not None:
            directory = os.path.join(directory, currentModuleOrFolder)
            if not os.path.isdir(directory):
                continue
        possibleImports.update(getPossibleImportsFromPath(directory))


    if currentModuleOrFolder is None:
        retList = sorted(list(possibleImports) + list(sys.builtin_module_names))
    else:
        retList = sorted(list(possibleImports))
        for idx, itm in enumerate(retList):
            # add the <ctypes.> to the start
            retList[idx] = currentModuleOrFolder.replace(os.path.sep, '.') + itm

    if removePrivate:
        return [i for i in retList if not i.startswith('_')]

    return retList

def getCurrentImportMatches(module):
    if '.' in module:
        # remove everything after the last dot
        module = module[:module.find('.') + 1]
        module = module.replace('.', os.path.sep)
        return getAllPossibleImports(currentModuleOrFolder=module)

    return getAllPossibleImports()

def isImportLine(lineText):
    return lineText.startswith('import ') or lineText.startswith('from ')

def getImportModulePathFromLine(lineText):
    if lineText.startswith('import '):
        return lineText.lstrip('import').strip()
    elif lineText.startswith('from '):
        lineTextSplit = lineText.split()
        if len(lineText.split()) > 1:
            return lineText.split()[1]
        return '' # nothing after from yet

    raise ValueError("invalid lineText given to function")

def getConsoleSize():
    if os.name == 'nt':
        user32 = ctypes.windll.LoadLibrary('user32')
        w = user32.GetForegroundWindow()
        coords = (ctypes.c_long * 4)()
        if user32.GetWindowRect(ctypes.c_long(w), ctypes.byref(coords)):
            return (coords[2] - coords[0]), (coords[3] - coords[1])

    # lol not windows
    return 300, 200

class CCompleter(rlcompleter.Completer):

    def __init__(self, *args, **kwargs):
        rlcompleter.Completer.__init__(self, *args, **kwargs)
        self._helpText = None # will be created if needed. Only create once.

    def showHelpText(self, text):
        # create if needed
        if self._helpText is None:
            self._helpText = HelpText()

        self._helpText.show(text)

    def complete(self, text, state):
        if self.use_main_ns:
            self.namespace = dict(builtins.__dict__)
            self.namespace.update(__main__.__dict__)

        if len(text) == 0 or isImportLine(readline.get_line_buffer()):
            text = str(readline.get_line_buffer())
        title((text, state,))
        if text.endswith('(') and state == 0:
            funcName = text.rstrip('(')
            func = getFromNamespaceByName(self.namespace, funcName)
            if func:
                doc = getDocToPrint(func)
                if doc:
                    self.showHelpText(doc)
        elif isImportLine(text):
            if state == 0:
                modulePath = getImportModulePathFromLine(text)
                self.possibleImports = getCurrentImportMatches(modulePath)
                if modulePath:
                    self.possibleImports = [i for i in self.possibleImports if i.startswith(modulePath)]
            try:
                return self.possibleImports[state]
            except IndexError:
                # None should be returned when we run out of options.
                return None
        else:
            title('rl')
            return rlcompleter.Completer.complete(self, text, state)

readline.parse_and_bind('tab: complete')
c = CCompleter()
readline.set_completer(c.complete)

class HelpText():
    tk = None
    def __init__(self, *args, **kwargs):
        # HelpText.tk is a static (single) variable for all instances
        if HelpText.tk is None:
            HelpText.tk = tk.Tk()

        self._shouldShow = True
        self.text = tk.Text(self)
        self.text.pack(fill=tk.BOTH, expand=1)
        self.overrideredirect(1) # remove title bar
        self.wm_attributes('-alpha', .9)
        self.bindEverythingToHide()

    def __getattr__(self, name):
        '''
        i should fix this one day
        '''
        if HelpText.tk is not None:
            return getattr(HelpText.tk, name)

        raise ValueError("HelpText.tk is None. That should not happen.")

    def bindEverythingToHide(self):
        self.bind_all("<FocusOut>", self.hide)
        self.bind_all("<Key>", self.hide)
        self.bind_all("<Return>", self.hide)
        self.bind_all("<Tab>", self.hide)

    def getMouseLocation(self):
        x = self.winfo_pointerx() - self.winfo_rootx()
        y = self.winfo_pointery() - self.winfo_rooty()
        return x, y

    def getConsoleLocation(self):
        if os.name == 'nt':
            user32 = ctypes.windll.LoadLibrary('user32')
            w = user32.GetForegroundWindow()
            coords = (ctypes.c_long * 4)()
            if user32.GetWindowRect(ctypes.c_long(w), ctypes.byref(coords)):
                return coords[0], coords[1]

        return self.getMouseLocation()

    def correctConsoleSizeAndLocation(self):
        x, y = self.getConsoleLocation()
        maxWidth, maxHeight = getConsoleSize()
        self.geometry("%dx%d+%d+%d" % (maxWidth - 10, maxHeight - 10, x + 5, y))
        self.update_idletasks()
        self.update()

    def show(self, text):
        # add leading newline and header and indent lines past the first one
        text = os.linesep + 'CCompleter Help Text:' + os.linesep + '  ' + text.replace('\n', '\n  ').rstrip(' ')

        # replace text
        self.text.delete('1.0', tk.END)
        self.text.insert(tk.END, text)

        self.correctConsoleSizeAndLocation()
        self.deiconify()
        self.focus_force()

        # this is basically mainloop()
        while self._shouldShow:
            self.update()
            self.update_idletasks()
            time.sleep(.0001) # make sure self._shouldShow() can get updated.

    def hide(self, event=None):
        self.withdraw()
        self._shouldShow = False
