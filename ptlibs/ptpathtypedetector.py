import os

class PtPathTypeDetector:
    DOCUMENT_EXTENSIONS = [
        # Text files
        '.txt',
        # Microsoft Word documents
        '.doc', '.docx',
        # OpenOffice/LibreOffice documents
        '.odt',
        # PDF documents
        '.pdf',
        # Rich Text Format documents
        '.rtf',
        # WordPerfect documents
        '.wpd',
        # Microsoft Works documents
        '.wps',
        # Apple Pages documents
        '.pages',
        # eBooks
        '.epub',
        # Spreadsheets
        '.xls', '.xlsx', '.ods', '.csv',
        # Presentations
        '.ppt', '.pptx', '.odp', '.key',
        # Markdown documents
        '.md',
        # LaTeX documents
        '.tex',
        # LyX documents
        '.lyx',
        # AbiWord documents
        '.abw', '.zabw', '.awt', '.zawt', '.bzabw',
        # DjVu documents
        '.djvu',
        # XPS documents
        '.xps',
        # OXPS documents
        '.oxps',
        # Flat ODT documents
        '.fodt',
        # Unified Office Format Text documents
        '.uot',
    ]


    IMAGE_EXTENSIONS = [
        # Raster images
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.ico',
        '.psd', '.xcf', '.webp', '.hdr', '.pic', '.pct', '.exr',
        '.pcx', '.tga', '.dds', '.sgi', '.cgm', '.dxf', '.wmf',
        '.emf', '.pbm', '.pgm', '.ppm', '.xbm', '.xpm', '.ras',
        '.iff', '.lbm', '.pcd', '.pcds', '.mng', '.tga', '.wpg',
        '.msp', '.pdd', '.dib', '.dcx', '.cut', '.pdn', '.pnm',
        '.pntg', '.psp', '.sgi', '.sxd', '.sxw', '.sxc', '.sxi',
        '.sxd', '.sxm', '.sxg', '.sxv', '.sxw', '.sxg',
        # Vector images
        '.svg', '.ai', '.eps', '.cdr', '.cdt', '.cpt', '.cws',
        '.xar', '.mmp', '.odg', '.otg', '.stc', '.sxd', '.sda',
        '.sdd', '.sdp', '.sds', '.sdw', '.sxm', '.vsd', '.vsdx',
        '.vsdm', '.vsd', '.vst', '.vss', '.vssx', '.vssm', '.vstx',
        '.vstm', '.vsw', '.vsx', '.vtx', '.vsx', '.vsdm', '.vsdm',
        # 3D images
        '.3ds', '.dae', '.obj', '.stl', '.skp', '.skb', '.skc',
        '.skm', '.skx', '.skd', '.skf', '.skv', '.skt',
        # Other image formats
        '.apng', '.bpg', '.dcm', '.ecw', '.exr', '.fits', '.flif',
        '.jp2', '.jpegxr', '.kra', '.mng', '.pgf', '.qtvr', '.raw',
        '.sgi', '.tga', '.tiff', '.ufo', '.wdp',
    ]


    CONFIG_EXTENSIONS = [
        # Configuration files
        '.cfg', '.ini', '.conf', '.properties', '.props', '.rc', '.cf', '.cnf', '.reg', '.settings',
        # Information files
        '.inf', '.info', '.stat', '.dat', '.reg', '.prefs', '.pref'
    ]

    HTML_EXTENSIONS = [
        '.htm', '.html', ".shtml", ".xhtml", '.php', '.asp', '.aspx', '.jsp'
    ]

    BINARY_EXTENSIONS = [
        '.exe', '.com'
    ]

    ARCHIVE_EXTENSIONS = [
        '.rar', '.zip', '.tar', '.tgz', '.gz', '.7z', '.arj'
    ]

    JSON_EXTENSIONS = [
        '.json', '.jsn', '.jason', '.geojson'
    ]

    XML_EXTENSIONS = [
        '.xml', '.xsd', '.xsl', '.xslt', '.dtd', '.ent', '.xul'
    ]

    DB_EXTENSIONS = [
        '.db', '.sql'
    ]

    BACKUP_EXTENSIONS = [
        # Backup files
        '.bak', '.backup', '.bk', '.bkp', '.swp', '.sav', '.old', '.tmp', '.temp', '.copy',
        '.snap', '.versions', '.recycle', '.recycler', '.recycled', '.trash', '.deleted',
    ]

    JAVASCRIPT_EXTENSIONS = [".js"]
    CSS_EXTENSIONS = [".css"]
    RSS_EXTENSIONS = [".rss"]

    def get_type(self, path) -> str:
        """Determine the path type based on the extension name.

        Args:
            path (str): path to be determined

        Returns:
            A string representing the file type.
        """

        self.path = path
        self.resource_name, self.extension = os.path.splitext(path)

        if self.is_directory():
            return "webSourceTypeDirectory"
        elif self.is_html():
            return "webSourceTypeHtml"
        elif self.is_robots_file():
            return "webSourceTypeRobotsTxt"
        elif self.is_sitemap_file():
            return "webSourceTypeSitemap"
        elif self.is_security_file():
            return "webSourceTypeSecurityTxt"
        elif self.is_document():
            return 'webSourceTypeDocument'
        elif self.is_image():
            return 'webSourceTypeImage'
        elif self.is_config():
            return 'webSourceTypeConfiguration'
        elif self.is_backup():
            return 'webSourceTypeBackup'
        elif self.is_json():
            return 'webSourceTypeJson'
        elif self.is_xml():
            return 'webSourceTypeXml'
        elif self.is_db():
            return 'webSourceTypeDatabase'
        elif self.is_javascript():
            return 'webSourceTypeJavaScript'
        elif self.is_css():
            return 'webSourceTypeCss'
        elif self.is_rss():
            return 'webSourceTypeRss'
        elif self.is_binary():
            return 'webSourceTypeBinary'
        elif self.is_archive():
            return 'webSourceTypeArchive'
        elif self.is_crossdomain_file():
            return 'webSourceTypeCrossDomainXml'
        else:
            return "webSourceTypeOther"


    def is_directory(self):
        """Determine if the path is a directory."""
        return self.extension == ""

    def is_html(self):
        """Determine if the path is a HTML document."""
        return self.extension in self.HTML_EXTENSIONS

    def is_document(self):
        """Determine if the path is a document."""
        return self.extension in self.DOCUMENT_EXTENSIONS

    def is_binary(self):
        """Determine if the path is a binary file."""
        return self.extension in self.BINARY_EXTENSIONS

    def is_archive(self):
        """Determine if the path is a archive."""
        return self.extension in self.ARCHIVE_EXTENSIONS

    def is_image(self):
        """Determine if the path is an image."""
        return self.extension in self.IMAGE_EXTENSIONS


    def is_config(self):
        """Determine if the path is a configuration file."""
        return self.extension in self.CONFIG_EXTENSIONS


    def is_backup(self):
        """Determine if the path is a backup file."""
        return self.extension in self.BACKUP_EXTENSIONS


    def is_json(self):
        """Determine if the path is a JSON file."""
        return self.extension in self.JSON_EXTENSIONS


    def is_xml(self):
        """Determine if the path is an XML file."""
        return self.extension in self.XML_EXTENSIONS

    def is_db(self):
        """Determine if the path is an DB file."""
        return self.extension in self.DB_EXTENSIONS


    def is_css(self):
        """Determine if the path is a css file."""
        return self.extension in self.CSS_EXTENSIONS

    def is_rss(self):
        """Determine if the path is a rss file."""
        return self.extension in self.RSS_EXTENSIONS


    def is_javascript(self):
        """Determine if the path is a javascript file."""
        return self.extension in self.JAVASCRIPT_EXTENSIONS


    def is_robots_file(self):
        """Determine if the path is a robots.txt file."""
        return self.path == "robots.txt"

    def is_crossdomain_file(self):
        """Determine if the path is a crossdomain.xml file."""
        return self.path == "crossdomain.xml"

    def is_sitemap_file(self):
        """Determine if the path is a sitemap.xml file."""
        return self.path == "sitemap.xml"

    def is_security_file(self):
        """Determine if the path is a security.txt file."""
        return self.path == "security.txt"
