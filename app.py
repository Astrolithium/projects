import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

#initialize 2 tables to keep track of history and portfolio
db.execute("CREATE TABLE IF NOT EXISTS purchases (id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, userid INTEGER NOT NULL, ticker TEXT NOT NULL, price NUMERIC NOT NULL, sharenum INTEGER NOT NULL, purchasetime TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)")
db.execute("CREATE TABLE IF NOT EXISTS thistory (id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, userid INTEGER NOT NULL, ttype ENUM('buy', 'sell'), ticker TEXT NOT NULL, price NUMERIC NOT NULL, sharenum INTEGER NOT NULL, ttime TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)")

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
    if not db.execute("SELECT * from sqlite_master where type='table' and name='purchases'"):
        cashbalance = db.execute("SELECT cash FROM users where id=?", session["user_id"])
        cashbalance[0]["cash"] = usd(cashbalance[0]['cash'])
        return render_template("index.html", cashbalance = cashbalance[0]['cash'])
    else:
        userdata = db.execute("SELECT * from purchases where userid=? GROUP BY ticker", session["user_id"])
        totalvalue = float(0)
        for row in userdata:
            quotation = (lookup(row["ticker"]))["price"]
            row["currentprice"] = usd(quotation)
            row["totalvalue"] = quotation * (row["sharenum"])
            totalvalue += row["totalvalue"]
            row["totalvalue"] = usd(row["totalvalue"])
        cashbalance = db.execute("SELECT cash FROM users where id=?", session["user_id"])
        totalvalue = usd(totalvalue + cashbalance[0]["cash"])
        cashbalance[0]["cash"] = usd(cashbalance[0]["cash"])
        return render_template("index.html", userdata = userdata, cashbalance = cashbalance[0]["cash"], totalvalue = totalvalue)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "GET":
        return render_template("buy.html")
    else:
        if not request.form.get("symbol"):
            return apology("Please provide a stock ticker!", 403)
        elif not request.form.get("shares"):
            return apology("Please provide number of shares!", 403)
        
        if not lookup(request.form.get("symbol")):
            return apology("Stock ticker does not exist!", 403)
        elif int(request.form.get("shares")) < 1:
            return apology("Please provide an appropriate number of shares!", 403)
        
        buyingpower = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        ticker = lookup(request.form.get("symbol"))
        cost = ticker["price"] * int(request.form.get("shares"))
        if cost > buyingpower[0]["cash"]:
            return apology("You cannot afford that many shares!", 403)
        
        db.execute("INSERT INTO purchases(userid, ticker, price, sharenum) VALUES(?, ?, ?, ?)", session["user_id"], ticker["symbol"], ticker["price"], int(request.form.get("shares")))
        db.execute("INSERT INTO thistory(userid, ttype, ticker, price, sharenum) VALUES(?, 'buy', ?, ?, ?)", session["user_id"], ticker["symbol"], ticker["price"], int(request.form.get("shares")))
        remainder = buyingpower[0]["cash"] - cost
        db.execute("UPDATE users SET cash = ? WHERE id = ?", remainder, session["user_id"])

        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    transachistory = db.execute("SELECT * FROM thistory where id = ? ORDER BY ttime ASC", session["user_id"])
    return render_template("history.html", trans = transachistory)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

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
    if request.method == "GET":
        return render_template("quote.html")
    else:
        if not request.form.get("symbol"):
            return redirect("/quote")
        ticker = request.form.get("symbol")
        return render_template("quoted.html", ticker=ticker, stockprice=lookup(ticker))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        if not request.form.get("username"):
            return apology("Please provide a username!", 403)
        username = request.form.get("username")

        if not (request.form.get("password") or request.form.get("confirmation")):
            return apology("Please provide a password!", 403)
        password = request.form.get("password")
        password2 = request.form.get("confirmation")

        if password != password2:
            return apology("Passwords must match!", 403)
        
        phash = generate_password_hash(password)

        db.execute("INSERT INTO users (username, hash) VALUES(?,?)", username, phash)

        return redirect("/")
    else:
        return render_template("register.html")

    


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "GET":
        stockticker = db.execute("SELECT ticker from purchases where userid=?", session["user_id"])
        return render_template("sell.html", stockticker = stockticker)
    
    else:
        if not request.form.get("symbol"):
            return apology("Please provide a stock!", 403)
        elif not request.form.get("shares"):
            return apology("Please provide correct number of shares!", 403)
        
        ticker = request.form.get("symbol")
        if not lookup(ticker):
            return apology("Invalid stock ticker!", 403)
        elif not db.execute("SELECT ticker FROM purchases where ticker=?", ticker):
            return apology("You do not own that stock!", 403)
        
        ticker = lookup(ticker)
        sharenum = int(request.form.get("shares"))
        if sharenum < 1:
            return apology("Please provide at least 1 share!")
        
        ownedshares = db.execute("SELECT sharenum FROM purchases where ticker=? and userid=?", ticker["symbol"], session["user_id"])
        if sharenum > ownedshares[0]["sharenum"]:
            return apology("You can not sell more shares than you own!", 403)
        elif sharenum == ownedshares[0]["sharenum"]:
            cashdelta = ticker["price"] * sharenum
            db.execute("INSERT INTO thistory(userid, ttype, ticker, price, sharenum) VALUES(?, 'sell', ?, ?, ?)", session["user_id"], ticker["symbol"], ticker["price"], sharenum)
            db.execute("DELETE FROM purchases WHERE ticker=? and userid=?", ticker, session["user_id"])
            cash = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])
            newcash = cashdelta + cash[0]["cash"]
            db.execute("UPDATE users SET cash = ? WHERE id = ?", newcash, session["user_id"])
        else:
            cashdelta = ticker["price"] * sharenum
            origsharenum = db.execute("SELECT sharenum FROM purchases where ticker=? and userid=?", ticker["symbol"], session["user_id"])
            newsharenum = origsharenum[0]["sharenum"] - sharenum
            db.execute("UPDATE purchases SET sharenum = ? WHERE id = ? AND ticker = ?", newsharenum, session["user_id"], ticker["symbol"])
            db.execute("INSERT INTO thistory(userid, ttype, ticker, price, sharenum) VALUES(?, 'sell', ?, ?, ?)", session["user_id"], ticker["symbol"], ticker["price"], sharenum)
            cash = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])
            newcash = cashdelta + cash[0]["cash"]
            db.execute("UPDATE users SET cash = ? WHERE id = ?", newcash, session["user_id"])

        return redirect("/")
