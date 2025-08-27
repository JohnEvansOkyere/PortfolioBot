from main import app
from starlette.middleware.wsgi import WSGIMiddleware

application = WSGIMiddleware(app)