"""This module contains functions used for parsing http responses."""

class HttpResponseParser():
    def get_urls_from_response(self, http_response: str, response_url: str, scope: list = None):

        soup = BeautifulSoup(http_response, 'html.parser')
        urls = set()

        # List of attributes that can contain URLs
        url_attributes = [
            "href", "src", "cite", "action", "data", "formaction", "poster",
            "longdesc", "profile", "manifest", "archive", "codebase", "background",
            "icon", "usemap"
        ]

        # List of attributes that can contain URLs
        url_attributes = [
            "href", "src", "action", "cite", "data", "formaction", "poster",
            "longdesc", "profile", "manifest", "archive", "codebase", "background",
            "icon", "usemap", "data-src", "data-href", "data-link", "dynsrc", "lowsrc",
            "xlink:href", "xml:base", "ping", "srcset", "data-srcset", "onerror", ]#"style"
        #]

        # Iterate through all tags and their attributes
        for tag in soup.find_all(True):
            for attr in url_attributes:
                if attr in tag.attrs:
                    urls.add(tag[attr])

         # Extract URLs from inlined JavaScript and CSS
        scripts = soup.find_all('script')
        styles = soup.find_all('style')

        for script in scripts:
            urls.update(re.findall(r'(["\'])((?:https?|ftp):\/\/[^"\']+)', http_response))

        for style in styles:
            urls.update(re.findall(r'url\((.*?)\)', style.string))

        # Extract URLs from meta tags and other places
        meta_tags = soup.find_all('meta')
        for meta in meta_tags:
            if 'content' in meta.attrs:
                urls.update(re.findall(r'(https?://[^\s]+)', meta['content']))

        # Extract URLs from comments
        comments = soup.find_all(text=lambda text: isinstance(text, Comment))
        for comment in comments:
            urls.update(re.findall(r'(https?://[^\s]+)', comment))

        # Print all extracted URLs
        print("-- Found and extracted those URLs from response: -- \n")

        processed_urls = []

        for url in urls:
            if isinstance(url, tuple):
                # Concatenate elements of the tuple into a single string
                new_url = ''.join(i for i in url if len(i) > 1)
                processed_urls.append(new_url)
            elif isinstance(url, str) and len(url) > 1:
                # Add the string to the list if its length is greater than 1
                processed_urls.append(url)
        
        for url in sorted(set(processed_urls)):
            print(url)

        """
        urls = sorted(urls)
        for url in urls:
            if type(url) == tuple:
                new_url = ''
                for i in url:
                    if len(i) == 1:
                        continue
                    else:
                        new_url += i 
                url = new_url
            if type(url) == str and len(url) == 1:
                continue
            print(url)

            if scope:
                if url not in scope:
                    continue
            #if url.startswith("/"):
            #    print(response_url + url)
            #else:
        """
