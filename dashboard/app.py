import functools
import logging

from flask import Flask, Response, render_template, request

from config.settings import DASHBOARD_PASSWORD, DASHBOARD_PORT, DASHBOARD_USERNAME, GOOGLE_SHEET_ID
from services.sheets_service import get_all_rows

logger = logging.getLogger(__name__)

app = Flask(__name__)


def check_auth(username: str, password: str) -> bool:
    return username == DASHBOARD_USERNAME and password == DASHBOARD_PASSWORD


def requires_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return Response(
                "Authentication required",
                401,
                {"WWW-Authenticate": 'Basic realm="Book Automation Dashboard"'},
            )
        return f(*args, **kwargs)
    return decorated


@app.route("/")
@requires_auth
def index():
    try:
        orders = get_all_rows(GOOGLE_SHEET_ID)
    except Exception:
        logger.exception("Failed to fetch orders from Google Sheets")
        orders = []
    return render_template("index.html", orders=orders)


def start_dashboard():
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False)
