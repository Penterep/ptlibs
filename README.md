[![penterepTools](https://www.penterep.com/external/penterepToolsLogo.png)](https://www.penterep.com/)


# PTLIBS
> Support library for penterepTools

## Installation
```
pip install ptlibs
```

## Version History
```
- 1.0.0
    - Cookie redirect fix
- 0.1.3
    - ptpathtypedetector - get_type() method tweaks
    - arraylock - new ThreadSafeArray class
    - added windows support (for tools that do not use functions that depend on fcntl, termios libraries)
- 0.1.2
    - Unification with type hints changes
- 0.1.1
    - Cached requests are now saved into /tmp/pentereptools/
    - Updated load_url_from_web_or_temp function
    - Requests are now being saved along with parsed request and response objects as a string
    - Other small changes to make ptscripts work properly
- 0.0.7 - 0.1.0
    - Unification with ptthreads
    - Added type hints
    - ptmisclib split into multiple classes
    - Implemented parsing of url to nodes
- 0.0.5 - 0.0.6
    - Implemented new printing method
    - New 'WARNING' definition added to ptdefs
- 0.0.4
    - removed 3rd party ipaddress module dependency
- 0.0.3
    - Replaced some characters in ptdefs
    - Added new methods to ptmisclib
- 0.0.1 - 0.0.2
    - Alpha releases
```

## License

Copyright (c) 2023 Penterep Security s.r.o.

ptlibs is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

ptlibs is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with ptlibs.  If not, see <https://www.gnu.org/licenses/>.