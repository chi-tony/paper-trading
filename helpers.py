from flask import redirect, render_template, session
from functools import wraps
import finnhub

def apology(message, code=400):
    """Render message as an apology to user."""

    def escape(s):
        """
        Escape special characters.

        https://github.com/jacebrowning/memegen#special-characters
        """
        for old, new in [
            ("-", "--"),
            (" ", "-"),
            ("_", "__"),
            ("?", "~q"),
            ("%", "~p"),
            ("#", "~h"),
            ("/", "~s"),
            ('"', "''"),
        ]:
            s = s.replace(old, new)
        return s

    return render_template("apology.html", top=code, bottom=escape(message)), code


def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/1.1.x/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function


def usd(value):
    """Format value as USD."""
    return f"${value:,.2f}"


def autocomplete():
    """Look up complete list of stock symbols."""

    # Use API key for Finnhub
    finnhub_client = finnhub.Client(api_key="ce2mje2ad3i1c7jetfr0ce2mje2ad3i1c7jetfrg")

    # Initiate list of symbols and empty dictionary of names
    stock_symbols = []

    # Get stock data from US exchanges and append symbols to symbol list
    for stock in finnhub_client.stock_symbols("US"):
        stock_symbols.append(stock["symbol"])

    # Sort stock names alphabetically by description
    stock_symbols = sorted(stock_symbols)

    return stock_symbols
