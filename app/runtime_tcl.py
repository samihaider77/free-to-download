"""Initialize Tcl's working-directory cache before frozen tkinter startup.

Some restricted Windows sessions mis-normalize an ancestor of the executable
path during tkinter initialization. Initializing the cwd cache first, together
with relative Tcl resource paths in main.py, keeps resource lookup functional.
"""
import ctypes
import os
import sys
from pathlib import Path

dll = Path(getattr(sys, "_MEIPASS", "")) / "tcl86t.dll"
if os.name == "nt" and dll.is_file():
    # Best effort only: a normal Windows session never needs this, so failure must not stop startup.
    try:
        library = ctypes.CDLL(str(dll))
        library.Tcl_CreateInterp.restype = ctypes.c_void_p
        library.Tcl_Eval.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        library.Tcl_DeleteInterp.argtypes = [ctypes.c_void_p]
        interpreter = library.Tcl_CreateInterp()
        try:
            library.Tcl_Eval(interpreter, b"pwd")
        finally:
            library.Tcl_DeleteInterp(interpreter)
    except OSError:
        pass
