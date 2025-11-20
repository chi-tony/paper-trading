from flask import Flask, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
from pytz import timezone
from sqlalchemy import create_engine, select, func, insert, update, and_, TypeDecorator, String
from sqlalchemy import Table, Column, MetaData, Integer
import yfinance as yf
from decimal import Decimal, ROUND_HALF_UP

from helpers import apology, login_required, usd, autocomplete

# Custom type to store Decimals as Strings in SQLite
class SqliteDecimal(TypeDecorator):
    """Store Decimal objects as strings in SQLite for precision"""
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Convert Decimal to string when storing"""
        if value is not None:
            return str(value)
        return value

    def process_result_value(self, value, dialect):
        """Convert string back to Decimal when fetching"""
        if value is not None:
            return Decimal(value)
        return value

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
            history = Table('history', meta, Column("shares", Integer), autoload=True, autoload_with=engine, extend_existing=True)
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

        # Fetch all tickers at once
        symbols = [h["symbol"] for h in holdings]
        if symbols:
            tickers = yf.Tickers(' '.join(symbols))
            prices = {symbol: tickers.tickers[symbol].info.get("currentPrice") for symbol in symbols}
        else:
            prices = {}
            
        total = cash
        unrealized = Decimal('0')
        totals = {}

        # Get all gains/stats for each holding
        for holding in holdings:
            symbol = holding["symbol"]
            
            price = prices.get(symbol)
            if not price:
                return apology(f"ERROR: YFINANCE UPDATE {symbol}")

            holding["price"] = price
            shares = holding["shares"]
            
            holding_val = Decimal(str(shares * price)).quantize(Decimal('0.01'))
            holding["total"] = float(holding_val)
            
            cost_basis = Decimal(str(holding["total_cost"]))

            # Calculate stats
            holding["average_cost"] = float(cost_basis / shares)
            total_gain = holding_val - cost_basis
            holding["total_gain"] = float(total_gain)
            holding["total_change"] = float(total_gain / cost_basis * 100)
            
            unrealized += total_gain
            total += holding_val
            totals[symbol] = float(holding_val)

        gains = unrealized + realized
        holds = total - cash
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

        symbol = request.form.get("symbol").upper()
        shares = int(request.form.get("shares"))

        ticker = yf.Ticker(symbol).info
        name = ticker.get("longName")
        price = ticker.get("currentPrice")
        if not price:
            return apology(f"ERROR: YFINANCE UPDATE {symbol}")

        # Calculate total price of purchase
        total_buy = Decimal(str(shares * price)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # Get current user's cash reserve
        with engine.connect() as conn:
            users = Table('users', meta, autoload=True, autoload_with=engine)
            stmt = select(users.c.cash).where(users.c.id == session["user_id"])
            cash = Decimal(str(conn.execute(stmt).scalar()))

            # Ensure user has sufficient cash to purchase
            if total_buy > cash:
                return apology("INSUFFICIENT CASH")
            
            tz = timezone('EST')
            timestamp = datetime.now(tz).replace(microsecond=0)
            
            # Use transaction for atomic operations
            trans = conn.begin()
            try:
                # Update user's cash amount in database
                stmt = update(users).values(cash = cash - total_buy).where(users.c.id == session["user_id"])
                conn.execute(stmt)

                # Insert transaction into history table
                history = Table('history', meta, Column("shares", Integer), autoload=True, autoload_with=engine, extend_existing=True)
                stmt = insert(history).values(
                    user_id = session['user_id'], 
                    symbol = symbol,
                    name = name, 
                    shares = shares, 
                    price = price,
                    total_cost = total_buy, 
                    time = timestamp
                )
                conn.execute(stmt)
                trans.commit()
            except:
                trans.rollback()
                return apology("TRANSACTION FAILED")

            # Redirect user to home page
            return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        # Define symbol selected on index
        index_buy = request.args.get("symbol", default="", type=str)

        # Get current user's cash reserve
        with engine.connect() as conn:
            users = Table('users', meta, autoload=True, autoload_with=engine)
            stmt = select(users.c.cash).where(users.c.id == session["user_id"])
            cash = Decimal(str(conn.execute(stmt).scalar()))

        # Render buy page
        return render_template("buy.html", index_buy=index_buy, cash=cash)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # User reached route via GET (as by clicking a link or via redirect)
    if request.method == "GET":

        # Extract history for user
        with engine.connect() as conn:
            history = Table('history', meta, Column("shares", Integer), autoload=True, autoload_with=engine, extend_existing=True)
            stmt = select(history.c.symbol, history.c.name, history.c.shares, history.c.price,
                history.c.total_cost, history.c.time).where(history.c.user_id == session["user_id"]).\
                order_by(history.c.time.desc())
            transactions = conn.execute(stmt).fetchall()

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
        with engine.connect() as conn:
            users = Table('users', meta, autoload=True, autoload_with=engine)
            stmt = select([users]).where(users.c.username == request.form.get("username"))
            rows = conn.execute(stmt).fetchall()

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
        with engine.connect() as conn:
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
                trans = conn.begin()
                try:
                    stmt = insert(users).values(id = user_id, username = username, hash = hash)
                    conn.execute(stmt)
                    trans.commit()
                except:
                    trans.rollback()
                    return apology("REGISTRATION FAILED")

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

        symbol = request.form.get("symbol").upper()
        shares = int(request.form.get("shares"))

        ticker = yf.Ticker(symbol).info
        name = ticker.get("longName")
        price = ticker.get("currentPrice")
        if not price:
            return apology(f"ERROR: YFINANCE UPDATE {symbol}")

        # Ensure valid number of shares provided
        with engine.connect() as conn:
            history = Table('history', meta, Column("shares", Integer), autoload=True, autoload_with=engine, extend_existing=True)
            users = Table('users', meta, autoload=True, autoload_with=engine)

            # Get current number of shares owned
            stmt = select(
                func.sum(history.c.shares).label("total_shares"),
                func.sum(history.c.total_cost).label("total_cost")
            ).where(and_(
                history.c.symbol == symbol,
                history.c.user_id == session["user_id"]
            ))
            position = conn.execute(stmt).fetchone()

            # Ensure user has enough shares
            current_shares = position["total_shares"]
            total_cost = Decimal(str(position["total_cost"]))
            
            if shares > current_shares:
                return apology("INSUFFICIENT SHARES OWNED")
            
            # Determine proportional cost basis
            avg_cost_per_share = total_cost / current_shares
            sale_cost_basis = avg_cost_per_share * shares
            sale_price = Decimal(str(shares * price))
            realized_gain = sale_price - sale_cost_basis

            # Get timestamp
            tz = timezone('EST')
            timestamp = datetime.now(tz).replace(microsecond=0)
            
            trans = conn.begin()
            try:
              # Insert negative transaction with proportional cost basis
                stmt = insert(history).values(
                    user_id = session["user_id"], 
                    symbol = symbol, 
                    name = name,
                    shares = -shares, 
                    price = price, 
                    total_cost = -sale_cost_basis,
                    time = timestamp
                )
                conn.execute(stmt)
                
                # Get current cash and realized gains
                stmt = select(users.c.cash, users.c.realized).where(users.c.id == session["user_id"])
                user_data = conn.execute(stmt).fetchone()
                
                cash = Decimal(str(user_data["cash"]))
                current_realized = Decimal(str(user_data["realized"]))
                
                # Update cash and realized gains
                stmt = update(users).values(
                    cash=cash + sale_price,
                    realized=current_realized + realized_gain
                ).where(users.c.id == session["user_id"])
                conn.execute(stmt)
                
                trans.commit()
                
            except Exception as e:
                trans.rollback()
                return apology(f"TRANSACTION FAILED: {str(e)}")

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        # Display current holdings as dropdown list
        with engine.connect() as conn:
            history = Table('history', meta, Column("shares", Integer), autoload=True, autoload_with=engine, extend_existing=True)
            users = Table('users', meta, autoload=True, autoload_with=engine)
            
            stmt = select(
                history.c.symbol,
                func.sum(history.c.shares).label("shares")
            ).where(
                history.c.user_id == session["user_id"]
            ).group_by(
                history.c.symbol
            ).having(
                func.sum(history.c.shares) > 0
            ).order_by(
                history.c.symbol.asc()
            )
            holding_symbols = conn.execute(stmt).fetchall()

            # Define symbol selected on index
            index_sell = request.args.get("symbol", default="", type=str)

            # Get current user's cash reserve
            stmt = select(users.c.cash).where(users.c.id == session["user_id"])
            cash = Decimal(str(conn.execute(stmt).scalar()))

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
        deposit = Decimal(str(request.form.get("deposit")))

        # Get current user's cash reserve
        with engine.connect() as conn:
            users = Table('users', meta, autoload=True, autoload_with=engine)
            stmt = select(users.c.cash).where(users.c.id == session["user_id"])
            cash = Decimal(str(conn.execute(stmt).scalar()))
            
            tz = timezone('EST')
            timestamp = datetime.now(tz).replace(microsecond=0)
            
            trans = conn.begin()
            try:
                # Add to user's cash amount
                stmt = update(users).values(cash = cash + deposit).where(users.c.id == session["user_id"])
                conn.execute(stmt)
                
                # Update history table
                history = Table('history', meta, Column("shares", Integer), autoload=True, autoload_with=engine, extend_existing=True)
                stmt = insert(history).values(
                    user_id = session['user_id'],
                    symbol = 'DEPOSIT',
                    name = 'Deposit',
                    shares = 0,
                    price = 0,
                    total_cost = deposit,
                    time = timestamp
                )
                conn.execute(stmt)
                trans.commit()
                
            except:
                trans.rollback()
                return apology("TRANSACTION FAILED")

        # Redirect to homepage
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # Get current user's cash reserve
        with engine.connect() as conn:
            users = Table('users', meta, autoload=True, autoload_with=engine)
            stmt = select(users.c.cash).where(users.c.id == session["user_id"])
            cash = Decimal(str(conn.execute(stmt).scalar()))
        
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
        withdrawal = Decimal(str(request.form.get("withdraw")))

        # Get current user's cash reserve
        with engine.connect() as conn:
            users = Table('users', meta, autoload=True, autoload_with=engine)
            stmt = select(users.c.cash).where(users.c.id == session["user_id"])
            cash = Decimal(str(conn.execute(stmt).scalar()))

            # Ensure user has sufficient cash to withdraw
            if withdrawal > cash:
                return apology("INSUFFICIENT CASH")

            tz = timezone('EST')
            timestamp = datetime.now(tz).replace(microsecond=0)
            
            trans = conn.begin()
            try:
                # Subtract from user's cash amount
                stmt = update(users).values(cash = cash - withdrawal).where(users.c.id == session["user_id"])
                conn.execute(stmt)
                
                # Update history table
                history = Table('history', meta, Column("shares", Integer), autoload=True, autoload_with=engine, extend_existing=True)
                stmt = insert(history).values(
                    user_id = session['user_id'],
                    symbol = 'WITHDRAW',
                    name = 'Cash Withdrawal',
                    shares = 0,
                    price = 0,
                    total_cost = -withdrawal,
                    time = timestamp
                )
                conn.execute(stmt)
                trans.commit()
            except:
                trans.rollback()
                return apology("TRANSACTION FAILED")

        # Redirect to homepage
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:

        # Get current user's cash reserve
        with engine.connect() as conn:
            users = Table('users', meta, autoload=True, autoload_with=engine)
            stmt = select(users.c.cash).where(users.c.id == session["user_id"])
            cash = Decimal(str(conn.execute(stmt).scalar()))

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
        with engine.connect() as conn:
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
            trans = conn.begin()
            try:
                stmt = update(users).values(hash = new_hash).where(users.c.id == session["user_id"])
                conn.execute(stmt)
                trans.commit()
            except:
                trans.rollback()
                return apology("PASSWORD UPDATE FAILED")

        # Redirect to homepage
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("account.html")
