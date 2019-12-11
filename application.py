import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Get all the stocks the user owns, grouping them by symbol and summing quantities
    rows = db.execute("SELECT symbol,SUM(quantity) FROM transactions GROUP BY symbol HAVING user_id = :current_id and SUM(quantity)>0",
                      current_id=session["user_id"])
    # add the current price to the dict and get total value of portfolio
    portfolio_value = 0
    for stock in rows:
        portfolio_value += lookup(stock["symbol"])["price"] * stock["SUM(quantity)"]
        stock["current_price"] = usd(lookup(stock["symbol"])["price"])
        stock["current_value"] = usd((lookup(stock["symbol"])["price"]) * stock["SUM(quantity)"])

    # get the disposable cash of the user
    cash = db.execute("SELECT cash FROM users WHERE id = :current_id",
                      current_id=session["user_id"])[0]["cash"]

    return render_template("index.html", stocks=rows, total_value=usd(cash + portfolio_value), cash=usd(cash))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # We capitalize the symbol in case it's lower case
        symbol = request.form.get("symbol").upper()
        data = (lookup(symbol))
        # Check if the symbol exists
        if data:
            try:
                shares = int(request.form.get("shares"))
            except ValueError:
                return apology("the number of shares must be an integer", 400)

            # Check if shares is a positive int
            if shares < 0:
                return apology("the number of shares must be positive", 400)
            else:
                # Retrieve how much cash the user has
                cash = db.execute("SELECT cash FROM users WHERE id = :id",
                                  id=session["user_id"])
                cash = cash[0]["cash"]
                # Compare his cash with shares * price to see if he can buy
                cost = shares * data["price"]
                if cash >= cost:
                    result = db.execute("INSERT INTO transactions (user_id, symbol, quantity, price) VALUES(:user_id, :symbol, :quantity, :price)",
                                        user_id=session["user_id"],
                                        symbol=data["symbol"],
                                        quantity=shares,
                                        price=data["price"])

                    # Update the cash left in user's account in the user table
                    cash_update = db.execute("UPDATE users SET cash = :new_amount WHERE id = :current_id",
                                             new_amount=cash - cost,
                                             current_id=session["user_id"])

                    # Redirect user to home page
                    return redirect("/")

                # Case where user doesn't have enough cash
                else:
                    return apology("you don't have enough cash", 400)

        else:
            return apology("this stock doesn't exist", 400)

    # User reaches through GET
    else:
        return render_template("buy.html")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    username = request.args.get("username")
    if username:
        users = [user["username"] for user in db.execute("SELECT username FROM users")]
        if username in users:
            return jsonify(False)
        else:
            return jsonify(True)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Select all transactions for the user
    rows = db.execute("SELECT symbol, quantity, price, time FROM transactions WHERE user_id = :current_id ORDER BY time DESC",
                      current_id=session["user_id"])
    # [{'symbol': 'AAPL', 'quantity': 6, 'price': 259.4, 'time': '2019-12-04 00:31:23'},
    return render_template("history.html", transactions=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

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
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        data = (lookup(symbol))
        if data:
            name = data["name"]
            price = usd(data["price"])
            return render_template("quoted.html", name=name, price=price)
        else:
            return apology("this stock doesn't exist", 400)

    # User reaches through GET
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure password confirmation was submitted
        elif not request.form.get("confirmation"):
            return apology("must provide a password confirmation", 400)

        # Ensure password and confirmation match
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("your password and confirmation don't match", 400)

        # Get a hash of the password provided
        hashed_password = generate_password_hash(request.form.get("password"))

        # Check if the unique username already exists
        result = db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)",
                            username=request.form.get("username"),
                            hash=hashed_password)
        if not result:
            return apology("this user already exists", 400)

        # Remember which user has registered and keep him logged in
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))
        session["user_id"] = rows[0]["id"]

        # if user is unique then he is rightly registered and we redirect to index
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure fields were submitted
        if not request.form.get("symbol"):
            return apology("please choose a symbol", 400)
        if not request.form.get("shares"):
            return apology("please choose a quantity", 400)
        symbol = request.form.get("symbol").upper()
        data = (lookup(symbol))
        shares = int(request.form.get("shares"))
        # Get the number of shares of symbol the user owns
        shares_owned = db.execute("SELECT SUM(quantity) FROM transactions GROUP BY symbol HAVING user_id = :current_id and symbol = :current_symbol",
                                  current_id=session["user_id"],
                                  current_symbol=symbol)[0]["SUM(quantity)"]
        if shares < 0:
            return apology("please enter a valid amount of shares", 400)
        if shares > shares_owned:
            return apology("you don't have enough shares to sell", 400)
        else:
            # Update the user's cash
            value = shares * data["price"]

            result = db.execute("UPDATE users SET cash=cash+:value WHERE id= :current_id",
                                value=value,
                                current_id=session["user_id"])

            # Update the transactions table
            result = db.execute("INSERT INTO transactions (user_id, symbol, quantity, price) VALUES(:user_id, :symbol, :quantity, :price)",
                                user_id=session["user_id"],
                                symbol=data["symbol"],
                                quantity=-shares,
                                price=data["price"])

            # Redirect to the index
            return redirect("/")

    # User reaches via get
    else:
        # Get a list of the stocks he owns
        stocks = db.execute("SELECT DISTINCT symbol FROM transactions WHERE user_id = :current_id",
                            current_id=session["user_id"])
        stock_symbols = []
        for stock in stocks:
            stock_symbols.append(stock["symbol"])
        return render_template("sell.html", symbols=stock_symbols)


@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    """Deposit cash"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Case where no amount was given
        if not request.form.get("deposit"):
            return apology("please enter an amount", 400)

        # Amount to deposit
        deposit = int(request.form.get("deposit"))

        # Update the cash in user's account in the user table
        cash_update = db.execute("UPDATE users SET cash = cash + :deposit WHERE id = :current_id",
                                 deposit=deposit,
                                 current_id=session["user_id"])

        # Update the transactions table
        result = db.execute("INSERT INTO transactions (user_id, symbol, quantity, price) VALUES(:user_id, :symbol, :quantity, :price)",
                            user_id=session["user_id"],
                            symbol="CASH",
                            quantity=0,
                            price=deposit)

        # Redirect user to home page
        return redirect("/")

    # User reaches through GET
    else:
        return render_template("deposit.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
