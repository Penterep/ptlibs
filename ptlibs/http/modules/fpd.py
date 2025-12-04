def find_fpd(response, error_patterns=None):
    r"""
    Scan the full redirect chain of a response for Full Path Disclosure (FPD) errors.

    The function iterates over each response in the redirect history (including the final response)
    and applies all regex patterns in `error_patterns` to the response text. It attempts to
    extract server file paths (Unix or Windows) that appear in error messages.

    Parameters:
        response : requests.Response-like object
            The HTTP response object, which may include a `.history` of redirects.
        
        error_patterns : list of str, optional
            A list of regular expression strings to match error messages indicating FPD.
            If not provided, a default set of common PHP error patterns will be used.

    Returns:
        list of dict
            Each dict maps a URL to a list of extracted FPD paths found in that response.
            Example:
            [
                {"https://www.example.com": ["/var/www/html/index.php", "/var/www/html/test.php"]},
                {"https://redirect.example.com": ["C:\\xampp\\htdocs\\file.php"]}
            ]

    Notes:
        - The path extractor regex inside each pattern is expected to catch:
            * Unix absolute paths: /var/www/html/file.php
            * Windows absolute paths: C:\xampp\htdocs\file.php
        - Only unique paths per URL are returned (duplicates are removed).
        - The function does not return a global list of all FPD paths; each URL is mapped individually.
    """
    if error_patterns is None or not isinstance(error_patterns, list):
        error_patterns = [
            r"(?:<b>)Warning(?:</b>)?: .* on line.*",
            r"(?:<b>)Fatal error(?:</b>)?: .* on line.*",
            r"(?:<b>)Error<(?:</b>)?: .* on line.*",
            r"(?:<b>)Notice(?:</b>)?: .* on line.*",
            r"(?:<b>)Uncaught Exception(?:</b>))?: [.\s]* on line.*",
            r"Fatal error:\s.*?in\s+\/[\w\/\.-]+:\d+",
            r"Uncaught .*? in\s+\/[\w\/\.-]+:\d+",
        ]

    results = []
    chain = list(response.history) + [response]
    
    path_extractor = r"([a-zA-Z]:\\(?:[^\\\s]+\\)*[^\s]+|/(?:[\w.-]+/)*[\w.-]+)"

    for resp in chain:
        url = resp.url
        text = getattr(resp, "text", "") or ""
        found = set()

        # iterate over all patterns
        for pattern in error_patterns:
            for match in re.finditer(pattern, text):
                raw = match.group(0)
                clean = re.sub(r'<[^>]+>', '', raw)

                # try to extract actual "in /path/file.php"
                pm = re.search(path_extractor, clean)
                if pm:
                    fp = pm.group(1)
                else:
                    fp = clean.strip()

                found.add(fp)

        if found:
            results.append({url: sorted(found)})
    return results