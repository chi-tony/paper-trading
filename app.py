from flask import Flask, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
from pytz import timezone
from sqlalchemy import create_engine, select, func, insert, update, and_
from sqlalchemy import Table, Column, MetaData, Integer
import yfinance as yf
from decimal import Decimal, ROUND_HALF_UP

from helpers import apology, login_required, usd, autocomplete

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = 'sqlite:///project.db'
engine = create_engine(db, pool_pre_ping=True)
meta = MetaData()

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Display stock portfolio"""

    # User reached route via GET (as by clicking a link or via redirect)
    if request.method == "GET":
        user_id = session["user_id"]

        # Get list of user stock symbols and share counts
        with engine.connect() as conn:
            history = Table('history', meta, Column("shares", Integer), autoload=True, autoload_with=engine)
            users = Table('users', meta, autoload=True, autoload_with=engine)
            
            # Get cash reserve for user
            stmt = select(
                users.c.cash,
                users.c.realized
            ).where(users.c.id == user_id)
            user_data = conn.execute(stmt).fetchone()
            
            cash = Decimal(str(user_data["cash"]))
            realized = Decimal(str(user_data["realized"]))
            
            stmt = select(
                history.c.symbol,
                history.c.name,
                func.sum(history.c.shares).label("shares"),
                func.sum(history.c.total_cost).label("total_cost")
            ).where(
                history.c.user_id == user_id
            ).group_by(
                history.c.symbol
            ).having(
                func.sum(history.c.shares) > 0
            ).order_by(
                history.c.symbol.asc()
            )
            
            holdings = [dict(row._mapping) for row in conn.execute(stmt)]

        # Calculate total portfolio value for user, starting with cash
        total = Decimal(str(cash))

        # Initialize unrealized gains
        unrealized = Decimal('0')

        # Initialize realized gains
        stmt = select(users.c.realized).where(users.c.id == user_id)
        realized = Decimal(str(conn.execute(stmt).fetchall()[0]["realized"]))
        conn.close()
        engine.dispose()

        # Initialize dictionary with symbols as keys and totals as values
        totals = {}

        # Loop through holding in list of dictionaries
        for holding in holdings:

            # Try to get price
            try:
                holding["price"] = yf.Ticker(holding["symbol"]).info["currentPrice"]

            # Show error page if error
            except:
                return apology("ERROR: YFINANCE UPDATE")

            # Calculate total price
            holding["total"] = Decimal(str(holding["shares"] * float(holding["price"]))).quantize(Decimal('0.01'))

            # Append symbol to symbols list
            totals[holding["symbol"]] = float(holding["total"])

            # Calculate average cost basis
            holding["average_cost"] = Decimal(str(holding["total_cost"])) / holding["shares"]

            # Calculate total gain
            holding["total_gain"] = Decimal(str(holding["total"])) - Decimal(str(holding["total_cost"]))

            # Add holding gains to unrealized gains
            unrealized += holding["total_gain"]

            # Calculate total change
            holding["total_change"] = float(holding["total_gain"]) / float(holding["total_cost"]) * 100

            # Add total price to portfolio total value
            total += Decimal(str(holding["total"]))

        # Calculate total gains
        gains = unrealized + realized

        # Calculate total portfolio holdings
        holds = total - cash

        # Add cash value to totals dictionary
        totals["Cash"] = float(cash)

        # Display portfolio for user
        return render_template("index.html", holdings=holdings, cash=float(cash), total=float(total), 
            unrealized=float(unrealized), realized=float(realized), gains=float(gains), 
            holds=float(holds), totals=totals)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User is sending data to site
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("MUST PROVIDE SYMBOL")

        # Define list of available symbols
        stock_options = autocomplete()

        # Ensure valid symbol was submitted
        if request.form.get("symbol").upper() not in stock_options:
            return apology("SYMBOL NOT VALID")

        # Ensure number of shares was submitted
        if not request.form.get("shares"):
            return apology("MUST PROVIDE SHARES")

        # Try converting share input to an integer
        try:
            int(request.form.get("shares"))
        except:
            return apology("INVALID NUMBER OF SHARES")

        # Ensure valid number of shares
        if int(request.form.get("shares")) <= 0:
            return apology("INVALID NUMBER OF SHARES")

        # Assign symbol as variable
        symbol = request.form.get("symbol").upper()

        # Calculate total cost of stock purchase
        shares = int(request.form.get("shares"))

        # Get Yahoo Finance ticker info for symbol
        ticker = yf.Ticker(symbol).info

        # Define stock name and price variables
        name = yf.Ticker(symbol).info["longName"]

        # Try to get price
        try:
            price = ticker["currentPrice"]

        # Show error page if error
        except:
            return apology("ERROR: YFINANCE UPDATE")

        # Calculate total price of purchase
        total_buy = Decimal(str(shares * price)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # Get current user's cash reserve
        conn = engine.connect()
        users = Table('users', meta, autoload=True, autoload_with=engine)
        stmt = select(users.c.cash).where(users.c.id == session["user_id"])
        cash = Decimal(str(conn.execute(stmt).fetchall()[0]["cash"]))

        # Ensure user has sufficient cash to purchase
        if total_buy > cash:
            return apology("INSUFFICIENT CASH")

        # If valid inputs
        else:

            # Get timestamp
            tz = timezone('EST')
            timestamp = datetime.now(tz).replace(microsecond=0)
            timestamp.strftime('%y-%m-%d %H:%M:%S')

            # Update user's cash amount in database
            stmt = update(users).values(cash = cash - total_buy).where(users.c.id == session["user_id"])
            conn.execute(stmt)

            # Insert transaction into history table
            history = Table('history', meta, Column("shares", Integer), autoload=True, autoload_with=engine)
            stmt = insert(history).values(user_id = session['user_id'], symbol = symbol,
               name = name, shares = shares, price = price,
               total_cost = total_buy, time = timestamp)
            conn.execute(stmt)
            conn.close()
            engine.dispose()

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        # Define symbol selected on index
        index_buy = request.args.get("symbol", default = "", type = str)

        # Get current user's cash reserve
        conn = engine.connect()
        users = Table('users', meta, autoload=True, autoload_with=engine)
        stmt = select(users.c.cash).where(users.c.id == session["user_id"])
        cash = Decimal(str(conn.execute(stmt).fetchall()[0]["cash"]))
        conn.close()
        engine.dispose()

        # Render buy page
        return render_template("buy.html", index_buy=index_buy, cash=cash)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # User reached route via GET (as by clicking a link or via redirect)
    if request.method == "GET":

        # Extract history for user
        conn = engine.connect()
        history = Table('history', meta, Column("shares", Integer), autoload=True, autoload_with=engine)
        stmt = select(history.c.symbol, history.c.name, history.c.shares, history.c.price,
            history.c.total_cost, history.c.time).where(history.c.user_id == session["user_id"]).\
            order_by(history.c.time.desc())
        transactions = conn.execute(stmt).fetchall()
        conn.close()
        engine.dispose()

        # Display history log for user
        return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("MUST PROVIDE USERNAME", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("MUST PROVIDE PASSWORD", 403)

        # Query database for username
        conn = engine.connect()
        users = Table('users', meta, autoload=True, autoload_with=engine)
        stmt = select([users]).where(users.c.username == request.form.get("username"))
        rows = conn.execute(stmt).fetchall()
        conn.close()
        engine.dispose()

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("INVALID USERNAME AND/OR PASSWORD", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User is sending data to site
    if request.method == "POST":

        # Ensure quote was submitted
        if not request.form.get("symbol"):
            return apology("MUST PROVIDE SYMBOL")

        # Define list of available symbols
        stock_options = autocomplete()

        # Ensure valid quote was submitted
        if request.form.get("symbol").upper() not in stock_options:
            return apology("SYMBOL NOT VALID")

        # Define user input stock symbol
        symbol = request.form.get("symbol").upper()

        # Get Yahoo Finance ticker info for symbol
        ticker = yf.Ticker(symbol).info

        # Define name of inputted symbol
        name = yf.Ticker(symbol).info["longName"]

        # Try to get price
        try:
            price = ticker["currentPrice"]

        # Show error page if error
        except:
            return apology("ERROR: YFINANCE UPDATE")

        # Show quote of symbol price
        return render_template("quoted.html", name=name, price=price, symbol=symbol)

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # Define list of available symbols
        stock_options = autocomplete()

        return render_template("quote.html", stock_options=stock_options)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user id
    session.clear()

    # User is sending data to site
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("MUST PROVIDE USERNAME")

        # Query database for username
        conn = engine.connect()
        users = Table('users', meta, autoload=True, autoload_with=engine)
        stmt = select([users]).where(users.c.username == request.form.get("username"))
        rows = conn.execute(stmt).fetchall()

        # Check if username already exists
        if len(rows) == 1:
            return apology("USERNAME ALREADY EXISTS")

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("MUST PROVIDE PASSWORD")

        # Ensure password has at least 6 letters
        elif len(request.form.get("password")) < 6:
            return apology("PASSWORD MUST BE AT LEAST 6 CHARACTERS")

        # Ensure password has at least 1 number
        elif not any(character.isdigit() for character in request.form.get("password")):
            return apology("PASSWORD MUST HAVE AT LEAST 1 NUMBER")

        # Ensure password has at least 1 special character
        special_characters = "~`!@#$%^&*()_-+=[]:;,.?"

        if not any(character in special_characters for character in request.form.get("password")):
            return apology("PASSWORD MUST HAVE AT LEAST 1 SYMBOL")

        # Ensure password confirmation was submitted
        elif not request.form.get("confirmation"):
            return apology("MUST CONFIRM PASSWORD")

        # Ensure password matches confirmation
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("PASSWORDS DO NOT MATCH")

        # User info is valid
        else:
            # Get username and hash password
            username = request.form.get("username")
            hash = generate_password_hash(request.form.get("password"))

            # Increment user ID by 1; if no users available, set user_id to 1
            try:
                stmt = select(func.max(users.c.id).label("max_id"))
                user_id = conn.execute(stmt).fetchone()["max_id"] + 1
            except:
                user_id = 1

            # Insert username and password hash to users table
            stmt = insert(users).values(id = user_id, username = username, hash = hash)
            conn.execute(stmt)
            conn.close()
            engine.dispose()

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # User is sending data to site
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("MUST PROVIDE SYMBOL")

        # Define list of available symbols
        stock_options = autocomplete()

        # Ensure valid symbol was submitted
        if request.form.get("symbol") not in stock_options:
            return apology("SYMBOL NOT VALID")

        # Ensure number of shares was submitted
        elif not request.form.get("shares"):
            return apology("MUST PROVIDE SHARES")

        # Try converting share input to an integer
        try:
            int(request.form.get("shares"))
        except:
            return apology("INVALID NUMBER OF SHARES")

        # Ensure valid number of shares
        if int(request.form.get("shares")) <= 0:
            return apology("INVALID NUMBER OF SHARES")

        # Assign symbol as variable
        symbol = request.form.get("symbol").upper()

        # Calculate total cost of stock purchase
        shares = int(request.form.get("shares"))

        # Get Yahoo Finance ticker info for symbol
        ticker = yf.Ticker(symbol).info

        # Define stock name and price variables
        name = yf.Ticker(symbol).info["longName"]

        # Try to get price
        try:
            price = ticker["currentPrice"]

        # Show error page if error
        except:
            return apology("ERROR: YFINANCE UPDATE")

        # Get Yahoo Finance ticker info for symbol
        ticker = yf.Ticker(symbol).info

        # Define stock name and price variables
        name = yf.Ticker(symbol).info["longName"]
        price = ticker["currentPrice"]

        # Ensure valid number of shares provided
        conn = engine.connect()
        history = Table('history', meta, Column("shares", Integer), autoload=True, autoload_with=engine)

        if shares < 0:
            return apology("SHARES NOT VALID")

        # Get current number of shares owned
        stmt = select(func.sum(history.c.shares).label("shares")).where(and_(history.c.symbol == symbol,
            history.c.user_id == session["user_id"]))
        current_shares = int(conn.execute(stmt).fetchall()[0]["shares"])

        # Ensure user has enough shares
        if current_shares < shares:
            return apology("INSUFFICIENT SHARES OWNED")

        # Get timestamp
        tz = timezone('EST')
        timestamp = datetime.now(tz).replace(microsecond=0)
        timestamp.strftime('%y-%m-%d %H:%M:%S')

        # Calculate total price of sale
        sale_price = shares * price

        # Get total cost of stock
        stmt = select(func.sum(history.c.total_cost).label("total_cost")).where(and_(history.c.symbol == symbol,
            history.c.user_id == session["user_id"]))
        total_cost = float(conn.execute(stmt).fetchall()[0]["total_cost"])

        # Insert transaction into history table
        users = Table('users', meta, autoload=True, autoload_with=engine)
        stmt = insert(history).values(user_id = session["user_id"], symbol = symbol, name = name, shares = -shares,
            price = price, total_cost = -sale_price, time = timestamp)
        conn.execute(stmt)

        # Get current user's cash reserve and realized gains
        stmt = select(users.c.cash, users.c.realized).where(users.c.id == session["user_id"])
        user_info = conn.execute(stmt).fetchall()

        cash = float(user_info[0]["cash"])

        current_realized = float(user_info[0]["realized"])

        # Get cost spent on shares
        sale_cost = (total_cost / current_shares) * shares

        # Update user's cash reserve
        stmt = update(users).values(cash = cash + sale_price, realized = current_realized + sale_price - sale_cost).\
            where(users.c.id == session["user_id"])
        conn.execute(stmt)
        conn.close()
        engine.dispose()

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        # Display current holdings as dropdown list
        conn = engine.connect()
        history = Table('history', meta, Column("shares", Integer), autoload=True, autoload_with=engine)
        stmt = select(
            history.c.symbol,
            func.sum(history.c.shares).label("shares")).\
            where(history.c.user_id == session["user_id"]).\
            group_by(history.c.symbol).\
            having(func.sum(history.c.shares) > 0).\
            order_by(history.c.symbol.asc())
        holding_symbols = conn.execute(stmt)

        # Define symbol selected on index
        index_sell = request.args.get("symbol", default = "", type = str)

        # Get current user's cash reserve
        conn = engine.connect()
        users = Table('users', meta, autoload=True, autoload_with=engine)
        stmt = select(users.c.cash).where(users.c.id == session["user_id"])
        cash = Decimal(str(conn.execute(stmt).fetchall()[0]["cash"]))
        conn.close()
        engine.dispose()

        # Render sell page
        return render_template("sell.html", holding_symbols=holding_symbols,
            index_sell=index_sell, cash=cash)


@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    """Deposit cash."""

    # User is sending data to site
    if request.method == "POST":

        # Ensure deposit amount was submitted
        if not request.form.get("deposit"):
            return apology("MUST PROVIDE DEPOSIT")

        # Define user input deposit
        deposit = float(request.form.get("deposit"))

        # Get current user's cash reserve
        conn = engine.connect()
        users = Table('users', meta, autoload=True, autoload_with=engine)
        stmt = select(users.c.cash).where(users.c.id == session["user_id"])
        cash = Decimal(str(conn.execute(stmt).fetchall()[0]["cash"]))

        # Add to user's cash amount
        stmt = update(users).values(cash = cash + deposit).\
            where(users.c.id == session["user_id"])
        conn.execute(stmt)
        conn.close()
        engine.dispose()

        # Redirect to homepage
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # Get current user's cash reserve
        conn = engine.connect()
        users = Table('users', meta, autoload=True, autoload_with=engine)
        stmt = select(users.c.cash).where(users.c.id == session["user_id"])
        cash = Decimal(str(conn.execute(stmt).fetchall()[0]["cash"]))
        
        return render_template("deposit.html", cash=cash)


@app.route("/withdraw", methods=["GET", "POST"])
@login_required
def withdraw():
    """Withdraw cash."""

    # User is sending data to site
    if request.method == "POST":

        # Ensure withdrawal amount was submitted
        if not request.form.get("withdraw"):
            return apology("MUST PROVIDE WITHDRAWAL")

        # Define user input deposit
        withdrawal = float(request.form.get("withdraw"))

        # Get current user's cash reserve
        conn = engine.connect()
        users = Table('users', meta, autoload=True, autoload_with=engine)
        stmt = select(users.c.cash).where(users.c.id == session["user_id"])
        cash = Decimal(str(conn.execute(stmt).fetchall()[0]["cash"]))

        # Ensure user has sufficient cash to withdraw
        if withdrawal > cash:
            return apology("INSUFFICIENT CASH")

        # Subtract from user's cash amount
        stmt = update(users).values(cash = cash - withdrawal).\
            where(users.c.id == session["user_id"])
        conn.execute(stmt)
        conn.close()
        engine.dispose()

        # Redirect to homepage
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # Get current user's cash reserve
        conn = engine.connect()
        users = Table('users', meta, autoload=True, autoload_with=engine)
        stmt = select(users.c.cash).where(users.c.id == session["user_id"])
        cash = Decimal(str(conn.execute(stmt).fetchall()[0]["cash"]))

        return render_template("withdraw.html", cash=cash)


# @app.route("/about", methods=["GET"])
# @login_required
# def about():
#     """Describe web application to user."""

#     # User reached route via GET (as by clicking a link or via redirect)
#     return render_template("about.html")


@app.route("/account", methods=["GET", "POST"])
@login_required
def change_password():
    """Change user password."""

    # User is sending data to site
    if request.method == "POST":

        # Ensure current password was submitted
        if not request.form.get("current_password"):
            return apology("MUST PROVIDE CURRENT PASSWORD")

        # Ensure current password is correct by comparing hashed password with new password
        conn = engine.connect()
        users = Table('users', meta, autoload=True, autoload_with=engine)
        stmt = select(users.c.hash).where(users.c.id == session["user_id"])
        current_hash = conn.execute(stmt).fetchall()[0]["hash"]

        if not check_password_hash(current_hash, request.form.get("current_password")):
            return apology("CURRENT PASSWORD IS NOT CORRECT")

        # Ensure new password was submitted
        elif not request.form.get("new_password"):
            return apology("MUST PROVIDE NEW PASSWORD")

        # Ensure password has at least 6 letters
        elif len(request.form.get("new_password")) < 6:
            return apology("PASSWORD MUST BE AT LEAST 6 CHARACTERS")

        # Ensure password has at least 1 number
        elif not any(character.isdigit() for character in request.form.get("new_password")):
            return apology("PASSWORD MUST HAVE AT LEAST 1 NUMBER")

        # Ensure password has at least 1 special character
        special_characters = "~`!@#$%^&*()_-+=[]:;,.?"

        if not any(character in special_characters for character in request.form.get("new_password")):
            return apology("PASSWORD MUST HAVE AT LEAST 1 SYMBOL")

        # Ensure password confirmation was submitted
        elif not request.form.get("confirmation"):
            return apology("MUST CONFIRM PASSWORD")

        # Ensure password matches confirmation
        elif request.form.get("new_password") != request.form.get("confirmation"):
            return apology("PASSWORDS DO NOT MATCH")

        # Take user's new password and generate new hash
        new_hash = generate_password_hash(request.form.get("new_password"))

        # Update user's password hash in database
        conn = engine.connect()
        users = Table('users', meta, autoload=True, autoload_with=engine)
        stmt = update(users).values(hash = new_hash).where(users.c.id == session["user_id"])
        conn.execute(stmt)

        # Redirect to homepage
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("account.html")
