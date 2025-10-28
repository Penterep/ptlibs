import argparse as _argparse
import sys
from ptlibs.ptjsonlib import PtJsonLib
from argparse import *

class ArgumentParser(_argparse.ArgumentParser):
    def error(self, message):
        if "-j" in sys.argv or "--json" in sys.argv:
            json_mode = True
        else:
            json_mode = False
        jsonlib = PtJsonLib()
        jsonlib.end_error(message, json_mode)

