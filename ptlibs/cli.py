import argparse
from ptlibs._version import __version__

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--version', action='version', version=f'%(prog)s {__version__}')
    args = parser.parse_args()
    if not bool(vars(args)):
        print(f'ptlibs {__version__}')

if __name__ == "__main__":
    main()