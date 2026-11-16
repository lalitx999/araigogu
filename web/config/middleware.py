class CSPMiddleware:
    """Hard guarantee for 'no CDN': the browser refuses any host but ours.
    Inline script/style are allowed because the original design relies on onclick="", <script> blocks and style=""."""

    POLICY = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "font-src 'self'; connect-src 'self'; manifest-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'none'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/admin/"):  # Django admin ships inline bits
            response.headers.setdefault("Content-Security-Policy", self.POLICY)
        return response
