import sys
import os
import signal

from ptlibs.ptprinthelper import ptprint, out_if

def signal_handler(sig, frame):
    sys.stdout.write("\033[?25h")  # Show cursor (if hidden by any reason)
    ptprint(f"\r", clear_to_eol=True)
    SCRIPT_NAME = os.path.basename(sys.argv[0]).split(".py")[0]
    ptprint( out_if(f"{ptdefs.colors['ERROR']}Terminating {SCRIPT_NAME}.{ptdefs.colors['TEXT']}", "ERROR"), clear_to_eol=True)
    os._exit(1)

# Register the signal handler for SIGINT
signal.signal(signal.SIGINT, signal_handler)