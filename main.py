import hashlib
import os
import random
import string
from datetime import time, datetime, timezone, timedelta
import hashlib
import pandas as pd
import requests
import yfinance as yf
import psycopg2
import pytz
from dateutil.relativedelta import relativedelta
from flask import Flask, render_template, url_for, request, session, make_response, jsonify, json

app = Flask(__name__)
app.secret_key = b'_5#y2L"F4Q8z\n\xec]/'

try:
    conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
except:
    print("I am unable to connect to the database")

def popular_chatrooms():
    cur = conn.cursor()
    cur.execute(
        """SELECT name, item_id, COUNT(item_id) AS count FROM talk GROUP BY item_id, name ORDER BY count DESC LIMIT 5""")
    chatrooms = cur.fetchall()
    cur.close()
    return chatrooms

def main_news():
    cur = conn.cursor()
    cur.execute("""SELECT * FROM news ORDER BY system_date DESC LIMIT 7""")
    news = cur.fetchall()
    cur.close()
    return news

def get_stocklist():
    cur = conn.cursor()
    cur.execute("""SELECT * FROM analysis""")
    items = cur.fetchall()
    cur.close()
    return items

def stock_preferences():
    cur = conn.cursor()
    items = get_stocklist()
    favorable = []
    item_list = []
    for item in items:
        if session.get("username"):
            cur.execute("""SELECT * FROM preferences WHERE username = %s AND symbol = %s LIMIT 1""",
                        (session.get("username"), item[3]))
            exists = cur.fetchall()
            if len(exists) == 1:
                item_list.append(item)
            else:
                favorable.append(item)

    if not favorable:
        favorable.append(tuple(['AMZN', 'AMZN', 'AMZN', 'AMZN']))  # should insert name and id too
        item_list.append(tuple(['TSLA', 'TSLA', 'TSLA', 'TSLA']))

    cur.close()
    return favorable, item_list

def login_status():
    if not session.get("username"):
        profile_card = "no_user"
    else:
        profile_card = "logged_in"
    return profile_card

def user_details():
    cur = conn.cursor()
    if session.get("username"):
        cur.execute("""SELECT * FROM users WHERE username = %s LIMIT 1""", (session.get("username"),))
        user_info = cur.fetchall()

        for user in user_info:
            if user[3] >= 50 + (100 * user[2]):
                cur.execute("UPDATE users SET level = level + 1 AND points = 0 AND total = total + points WHERE username = %s ",
                            (session.get("username")))
                conn.commit()
                user_info = cur.fetchall()
    else:
        user_info = None

    cur.close()
    return user_info

def banks():
    cur = conn.cursor()
    cur.execute("SELECT * FROM bank_list ORDER BY priority ASC")
    bank_list = cur.fetchall()
    cur.close()
    return bank_list

def top_list():
    favorable, item_list = stock_preferences()
    favorable_up = []
    favorable_down = []
    for fav in favorable:
        yticker = yf.Ticker(fav[3])
        df = yticker.history(period="2d")

        rate = ((df['Close'][1] - df['Close'][0]) / df['Close'][0]) * 100
        if df['Close'][1] < df['Close'][0]:
            add = (round(rate, 2),) + fav
            favorable_down.append(add)

        if df['Close'][1] > df['Close'][0]:
            add = (round(rate, 2),) + fav
            favorable_up.append(add)

        favorable_up.sort(reverse=True)
        favorable_down.sort(reverse=True)

        if not favorable_up:
            print("nothing")
        else:
            favorable_up = favorable_up[:5]

        if not favorable_down:
            print('nothing')
        else:
            favorable_down = favorable_down[:5]

    return favorable_up, favorable_down

def stock_chart():
    favorable, item_list = stock_preferences()
    frame = pd.DataFrame()
    for fav in favorable:
        data = yf.download(tickers=fav[3], period="365d", interval="1d", auto_adjust=True)
        frame[fav[3]] = round(data['Close'], 2)

    frame['mean'] = frame.mean(axis=1)

    mean_list = frame['mean'].tolist()

    frame['Date'] = pd.to_datetime(data.index)
    frame['time'] = frame['Date'].dt.strftime('%m/%d/%Y')

    time_list = frame['time'].tolist()

    # 전일대비
    compare = ((frame['mean'][-1] - frame['mean'][-2]) / frame['mean'][-2]) * 100
    compare = round(compare, 2)
    if frame['mean'][-1] > frame['mean'][-2]:
        compare_rate = 'increase'
    elif frame['mean'][-1] < frame['mean'][-2]:
        compare_rate = 'decrease'
    elif frame['mean'][-1] == frame['mean'][-2]:
        compare_rate = 'equal'

    return mean_list, time_list, compare, compare_rate

def today_date():
    format = "%Y-%m-%d"
    d = datetime.now(tz=pytz.timezone('Asia/Seoul'))
    today = d.strftime(format)
    return today

def yesterday_date():
    format = "%Y-%m-%d"
    d = datetime.now(tz=pytz.timezone('Asia/Seoul'))
    d -= timedelta(days=1)
    d = d.astimezone(pytz.utc)
    d = d.replace(tzinfo=None)
    yesterday = d.strftime(format)
    return yesterday

def SBA_chart():
    cur = conn.cursor()
    today = today_date()

    cur.execute("SELECT misc FROM dc_fin WHERE datetime = %s AND item_id = %s ORDER BY datetime ASC LIMIT 1",
                (today, "SBA"))
    open = cur.fetchall()

    yesterday = yesterday_date()

    cur.execute("SELECT misc FROM dc_fin WHERE datetime = %s AND item_id = %s ORDER BY datetime DESC LIMIT 1",
                (yesterday, "SBA"))
    close = cur.fetchall()

    if open > close:
        open_close = "increase"
    if open < close:
        open_close = "decrease"
    if open == close:
        open_close = "equal"

    cur.execute("SELECT misc, datetime FROM dc_fin WHERE item_id = %s ORDER BY datetime ASC", ("SBA",))
    SBA1 = cur.fetchall()
    SBA_rates = []
    SBA_dates = []
    for x in SBA1:
        SBA_rates.append(x[0])
        SBA_dates.append(x[1])

    open = SBA_rates[-1]

    SBA_trades = []
    cur.execute("SELECT misc2 FROM dc_fin WHERE item_id = %s ORDER BY datetime ASC", ('SBA',))
    SBA_trades1 = cur.fetchall()
    for x in SBA_trades1:
        y = x[0] * 10
        SBA_trades.append(y)

    cur.close()

    return open, open_close, SBA_rates, SBA_dates, SBA_trades

def SBB_chart():
    cur = conn.cursor()
    today = today_date()

    # SBB : 오늘의 만기일 불러오기
    cur.execute("SELECT misc FROM dc_fin WHERE datetime = %s AND item_id = %s ORDER BY datetime ASC LIMIT 1",
                (today, "SBB"))
    misc_today = cur.fetchall()

    yesterday = yesterday_date()

    cur.execute("SELECT misc FROM dc_fin WHERE datetime = %s AND item_id = %s ORDER BY datetime DESC LIMIT 1",
                (yesterday, "SBB"))
    misc_yesterday = cur.fetchall()

    if misc_today > misc_yesterday:
        misc_trend = "increase"
    if misc_today < misc_yesterday:
        misc_trend = "decrease"
    if misc_today == misc_yesterday:
        misc_trend = "equal"

    # SBB 기간
    cur.execute("SELECT misc, datetime, misc2 FROM dc_fin WHERE item_id = %s ORDER BY datetime ASC", ("SBB",))
    SBB1 = cur.fetchall()
    period = []
    misc_dates = []
    period_z = []
    for misc in SBB1:
        period.append(misc[0])
        misc_dates.append(misc[1])
        period_z.append(misc[2])

    # getting call_date and end_date for SBB
    format = "%Y-%m-%d"
    d = datetime.now(tz=pytz.timezone('Asia/Tokyo'))
    d = d + relativedelta(months=3)  # change this to misc_today (오늘의 만기일)
    end_date = d.strftime(format)
    end_date.replace("-", "월 ")
    end_date = end_date + "일"

    d = d + relativedelta(months=1)
    call_date = d.strftime(format)
    call_date.replace("-", "월 ")
    call_date = call_date + "일"

    cur.close()

    return misc_today, misc_trend, period_z, misc_dates, end_date, call_date, period

def BB_spot():
    cur = conn.cursor()
    cur.execute("""SELECT open FROM dc_fin WHERE item_id = %s ORDER BY datetime ASC LIMIT 1""", ("BB",))
    BB1 = cur.fetchone()
    spot = []
    for x in BB1:
        spot.append(x)
    spot = spot[-1]
    cur.close()
    return spot

def BB_chart():
    cur = conn.cursor()
    cur.execute("""SELECT open, datetime FROM dc_fin WHERE item_id = %s ORDER BY datetime ASC LIMIT 360""", ("BB",))
    BB1 = cur.fetchall()
    BB_values = []
    BB_dates = []
    for values in BB1:
        BB_values.append(values[0])
        BB_dates.append(values[1])

    spot = BB_values[-1]

    today = today_date()
    yesterday = yesterday_date()

    cur.execute(
        """SELECT open FROM dc_fin WHERE item_id = %s AND datetime >= %s AND datetime < %s ORDER BY datetime DESC LIMIT 1""",
        ("BB", yesterday, today))
    yesterday_spot = cur.fetchone()
    ys = int(yesterday_spot[0])

    spot_rate = round(((spot - ys) / ys) * 100, 2)

    if spot > ys:
        spot_trend = "increase"
    if spot < ys:
        spot_trend = "decrease"
    if spot == ys:
        spot_trend = "equal"

    cur.close()

    return spot_trend, spot_rate, BB_values, BB_dates, ys

def seconds_till_one_minute(): # not using
    format = "%S"
    a_datetime = datetime.now(pytz.timezone("Asia/Seoul"))
    seconds = a_datetime.strftime(format)

    interval = 60 - int(seconds)
    return interval

def BB_prices(spot):
    cur = conn.cursor()
    today = today_date()

    low1 = spot - 5
    low2 = spot - 10
    high1 = spot + 5
    high2 = spot + 10

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (spot, today, "uncleared", "BB", "offer"))
    spot_quantity = cur.fetchone()
    spot_quantity = int(spot_quantity[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (low1, today, "uncleared", "BB", "offer"))
    low1_quantity = cur.fetchone()
    low1_quantity = int(low1_quantity[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (low2, today, "uncleared", "BB", "offer"))
    low2_quantity = cur.fetchone()
    low2_quantity = int(low2_quantity[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (high1, today, "uncleared", "BB", "offer"))
    high1_quantity = cur.fetchone()
    high1_quantity = int(high1_quantity[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (high2, today, "uncleared", "BB", "offer"))
    high2_quantity = cur.fetchone()
    high2_quantity = int(high2_quantity[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (spot, today, "uncleared", "BB", "bid"))
    spot_quantity_buy = cur.fetchone()
    spot_quantity_buy = int(spot_quantity_buy[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (low1, today, "uncleared", "BB", "bid"))
    low1_quantity_buy = cur.fetchone()
    low1_quantity_buy = int(low1_quantity_buy[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (low2, today, "uncleared", "BB", "bid"))
    low2_quantity_buy = cur.fetchone()
    low2_quantity_buy = int(low2_quantity_buy[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (high1, today, "uncleared", "BB", "bid"))
    high1_quantity_buy = cur.fetchone()
    high1_quantity_buy = int(high1_quantity_buy[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (high2, today, "uncleared", "BB", "bid"))
    high2_quantity_buy = cur.fetchone()
    high2_quantity_buy = int(high2_quantity_buy[0])

    cur.close()
    return spot_quantity, spot_quantity_buy, low1, low2, high1, high2, low1_quantity, low1_quantity_buy, low2_quantity, low2_quantity_buy, high1_quantity, high1_quantity_buy, high2_quantity, high2_quantity_buy

def my_value():
    spot = BB_spot()
    user_info = user_details()

    for x in user_info:
        token_total = x[7]
        buy_price = x[6]

        if buy_price > 0:
            current_value = token_total * spot
            orig_value = token_total * buy_price
            profit1 = ((current_value - orig_value) / orig_value) * 100
            profit = round(profit1, 2)

            if orig_value > current_value:
                profit_rate = "decrease"
            if orig_value < current_value:
                profit_rate = "increase"
            if orig_value == current_value:
                profit_rate = "equal"
        else:
            profit = 0
            profit_rate = 0
            current_value = 0
            orig_value = 0

    return profit, profit_rate, current_value, orig_value

def pending_orders():
    cur = conn.cursor()
    today = today_date()
    cur.execute("SELECT COUNT(*) FROM transactions WHERE username = %s AND datetime >= %s AND item_id = %s AND status = %s",
        (session.get("username"), today, "BB", "pending"))
    pending_total = cur.fetchone()
    pending_total = int("".join(map(str, pending_total)))
    cur.close()
    return pending_total

def now_date():
    time_format = "%Y-%m-%d %H:%M"
    d = datetime.now(tz=pytz.timezone('Asia/Tokyo'))
    d = d - timedelta(minutes=1)
    now = d.strftime(time_format)
    return now

@app.route("/")
def index():
    cur = conn.cursor()

    chatrooms = popular_chatrooms()
    news = main_news()

    favorable, item_list = stock_preferences()
    profile_card = login_status()

    if not session.get("username"):
        ticket_total = 0
        token_total = 0
        buy_price = 0
        user_info = None
    else:
        user_info = user_details()
        for x in user_details():
            ticket_total = x[8]
            token_total = x[7]
            buy_price = x[6]

    bank_list = banks()

    favorable_up, favorable_down = top_list()
    mean_list, time_list, compare, compare_rate = stock_chart()

    open, open_close, SBA_rates, SBA_dates, SBA_trades = SBA_chart()
    misc_today, misc_trend, period_z, misc_dates, end_date, call_date, period = SBB_chart()

    spot_trend, spot_rate, BB_values, BB_dates, ys = BB_chart()
    spot = BB_spot()
    spot_quantity, spot_quantity_buy, low1, low2, high1, high2, low1_quantity, low1_quantity_buy, low2_quantity, low2_quantity_buy, high1_quantity, high1_quantity_buy, high2_quantity, high2_quantity_buy = BB_prices(spot)

    # getting the current value
    if not session.get("username"):
        current_value = 0
        orig_value = 0
        profit = 0
        profit_rate = "equal"
    else:
        profit, profit_rate, current_value, orig_value = my_value()

    # counting pending transactions if session exists
    if not session.get("username"):
        pending_total = 0
    else:
        pending_total = pending_orders()

    cur.close()

    return render_template("index.html", compare = compare, compare_rate = compare_rate, period_z = period_z, SBA_trades = SBA_trades, bank_list = bank_list, ticket_total = ticket_total, pending_total = pending_total, profit = profit, profit_rate = profit_rate, token_total = token_total, buy_price = buy_price, spot_quantity = spot_quantity, spot_quantity_buy = spot_quantity_buy, spot = spot, low1 = low1, low2 = low2, high1 = high1, high2 = high2, low1_quantity = low1_quantity, low1_quantity_buy = low1_quantity_buy, low2_quantity = low2_quantity, low2_quantity_buy = low2_quantity_buy, high1_quantity = high1_quantity, high1_quantity_buy = high1_quantity_buy, high2_quantity = high2_quantity, high2_quantity_buy = high2_quantity_buy, end_date = end_date, call_date = call_date, ys = ys, spot_trend = spot_trend, spot_rate = spot_rate, BB_values = BB_values, BB_dates = BB_dates, SBA_rates = SBA_rates, SBA_dates = SBA_dates, period = period, misc_dates = misc_dates, misc_today = misc_today, misc_trend = misc_trend, open = open, open_close = open_close, mean_list = mean_list, time_list = time_list, favorable_up = favorable_up, favorable_down = favorable_down, profile_card = profile_card, chatrooms = chatrooms, news = news, item_list = item_list, favorable = favorable, user_info = user_info)

@app.route('/BB_table', methods=["POST"])
def BB_table():
    cur = conn.cursor()

    now = now_date()
    today = today_date()

    cur.execute("SELECT price FROM transactions WHERE item_id = %s AND datetime >= %s ORDER BY datetime DESC LIMIT 1", ("BB", now))
    spot = cur.fetchone()
    if cur.rowcount < 1:
        cur.execute("SELECT open FROM dc_fin WHERE item_id = %s AND datetime > %s ORDER BY datetime DESC LIMIT 1", ("BB", today))
        spot = cur.fetchone()

    spot = spot[0]

    spot_quantity, spot_quantity_buy, low1, low2, high1, high2, low1_quantity, low1_quantity_buy, low2_quantity, low2_quantity_buy, high1_quantity, high1_quantity_buy, high2_quantity, high2_quantity_buy = BB_prices(spot)

    cur.close()

    return render_template("BB_table.html", spot_quantity = spot_quantity, spot_quantity_buy = spot_quantity_buy, spot = spot, low1 = low1, low2 = low2, high1 = high1, high2 = high2, low1_quantity = low1_quantity, low1_quantity_buy = low1_quantity_buy, low2_quantity = low2_quantity, low2_quantity_buy = low2_quantity_buy, high1_quantity = high1_quantity, high1_quantity_buy = high1_quantity_buy, high2_quantity = high2_quantity, high2_quantity_buy = high2_quantity_buy)

@app.route("/BB_profit", methods=['GET', 'POST'])
def BB_profit():
    cur = conn.cursor()

    # getting the current value
    if not session.get("username"):
        current_value = 0
        orig_value = 0
        profit = 0
        profit_rate = "equal"
    else:
        profit, profit_rate, current_value, orig_value = my_value()

    # counting pending transactions if session exists
    if not session.get("username"):
        pending_total = 0
    else:
        pending_total = pending_orders()

    if not session.get("username"):
        ticket_total = 0
        token_total = 0
        buy_price = 0
        user_info = None
    else:
        user_info = user_details()
        for x in user_details():
            ticket_total = x[8]
            token_total = x[7]
            buy_price = x[6]

    # getting the current value
    if not session.get("username"):
        current_value = 0
        orig_value = 0
        profit = 0
        profit_rate = "equal"
    else:
        profit, profit_rate, current_value, orig_value = my_value()

    return render_template("coin.html", profit=profit, pending_total = pending_total, profit_rate=profit_rate, ticket_total = ticket_total, token_total=token_total, buy_price=buy_price)

@app.route("/sell_BB", methods=['GET', 'POST'])
def sell_BB():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    spot = int(request.form.get("price"))
    token_total = int(request.form.get("token_total"))

    if session.get("username"):
        time_format = "%Y-%m-%d %H:%M"
        d = datetime.datetime.now(tz=pytz.timezone('Asia/Tokyo'))
        d = d - timedelta(minutes=1)
        now = d.strftime(time_format)

        day_format = "%Y-%m-%d"
        today = d.strftime(day_format)

        check_time_format = "%H:%M"
        check_time = d.strftime(check_time_format)
        check_day = d.weekday()

        if check_time >= '09:00' and check_time <= '15:00' and check_day < 6:

            cur.execute("SELECT COUNT(*) FROM transactions WHERE username = %s AND datetime > %s AND position = %s AND status != %s AND item_id = %s", (session.get("username"), today, "offer", "cleared", "BB"))
            daily_transac = cur.fetchone()

            if daily_transac < token_total:

                cur.execute("SELECT * FROM transactions WHERE status = %s AND username != %s AND item_id = %s AND price = %s AND action = %s ORDER BY id ASC LIMIT 1", ('pending', '', 'BB', spot, 'bid'))
                if cur.rowcount == 1:
                    buyer = cur.fetchall()
                    for x in buyer:
                        cur.execute("UPDATE transactions SET datetime = %s, status = %s WHERE id = %s", (now, 'cleared', x[0])) # row id
                        cur.execute("UPDATE users SET token_count = token_count + 1, ticket_count = ticket_count - %s WHERE username = %s", (spot, x[1])) # username

                    cur.execute("INSERT INTO transactions (datetime, price, action, username, status, item_id) VALUES (%s, %s, %s, %s, %s, %s)",
                        (now, spot, "offer", session.get("username"), "cleared", "BB"))

                    cur.execute("UPDATE users SET token_total = token_total - 1, ticket_count = ticket_count + %s WHERE username = %s", (spot, session.get("username")))

                    conn.commit()

                else:
                    cur.execute("INSERT INTO transactions (datetime, price, action, username, status, item_id) VALUES (%s, %s, %s, %s, %s, %s)", (now, spot, "offer", session.get("username"), "uncleared", "BB"))
                    conn.commit()

                msg = "" # to count success

        else:
            msg = "failed_time"

    else:
        msg = "failed_login"

    cur.execute("""SELECT * FROM talk ORDER BY system_date DESC LIMIT 3""")
    chats = cur.fetchall()

    cur.execute("""SELECT name, item_id, COUNT(item_id) AS count FROM talk GROUP BY name ORDER BY count DESC LIMIT 5""")
    chatrooms = cur.fetchall()

    cur.execute("""SELECT * FROM news ORDER BY system_date DESC LIMIT 7""")
    news = cur.fetchall()

    cur.execute("""SELECT * FROM analysis""")
    items = cur.fetchall()
    favorable = []
    item_list = []
    for item in items:
        if not session.get("username"):
            if item[3] == "AMZN":
                favorable.append(item)
            else:
                item_list.append(item)
        else:
            cur.execute("""SELECT * FROM preferences WHERE username = %s AND symbol = %s LIMIT 1""",
                        (session.get("username"), item[3]))
            exists = cur.fetchall()
            if len(exists) == 1:
                item_list.append(item)
            else:
                favorable.append(item)

    if not favorable:
        favorable.append(tuple(['AMZN', 'AMZN', 'AMZN']))  # should insert name and id too

    if not session.get("username"):
        profile_card = "no_user"
        user_info = None
        token_total = 0
        buy_price = 0
        ticket_total = 0
    else:
        profile_card = "logged_in"
        cur.execute("""SELECT * FROM users WHERE username = %s LIMIT 1""", (session.get("username"),))
        user_info = cur.fetchall()

        for user in user_info:
            token_total = user[6]  # quantity of token
            buy_price = user[7]  # price of token
            ticket_total = user[8]  # quantity of tickets

            if user[5] >= 50 + (100 * user[4]):
                cur.execute("UPDATE users SET level = level + 1 AND points = 0 WHERE username = %s ",
                            (session.get("username")))
                conn.commit()
                user_info = cur.fetchall()

    # getting bank info

    cur.execute("SELECT * FROM bank_list ORDER BY priority ASC")
    bank_list = cur.fetchall()

    # making the top list

    favorable_up = []
    favorable_down = []
    for fav in favorable:
        yticker = yf.Ticker(fav[3])
        df = yticker.history(period="2d")

        rate = ((df['Close'][1] - df['Close'][0]) / df['Close'][0]) * 100
        if df['Close'][1] < df['Close'][0]:
            add = (round(rate, 2),) + fav
            favorable_down.append(add)

        if df['Close'][1] > df['Close'][0]:
            add = (round(rate, 2),) + fav
            favorable_up.append(add)

        favorable_up.sort(reverse=True)
        favorable_down.sort(reverse=True)

        if not favorable_up:
            print("nothing")
        else:
            favorable_up = favorable_up[:5]

        if not favorable_down:
            print('nothing')
        else:
            favorable_down = favorable_down[:5]

    # 종가 불러오기
    frame = pd.DataFrame()
    for fav in favorable:
        data = yf.download(tickers=fav[3], period="365d", interval="1d", auto_adjust=True)
        frame[fav[3]] = round(data['Close'], 2)

    frame['mean'] = frame.mean(axis=1)

    mean_list = frame['mean'].tolist()

    frame['Date'] = pd.to_datetime(data.index)
    frame['time'] = frame['Date'].dt.strftime('%m/%d/%Y')

    time_list = frame['time'].tolist()

    print(time_list)

    time_list = ','.join("'{0}'".format(x) for x in time_list)

    print(time_list)

    # SBA : 오늘의 환율 불러오기

    format = "%Y-%m-%d"
    d = datetime.now(tz=pytz.timezone('Asia/Seoul'))
    today = d.strftime(format)

    cur.execute("SELECT misc FROM dc_fin WHERE datetime = %s AND item_id = %s ORDER BY datetime ASC LIMIT 1",
                (today, "SBA"))
    open = cur.fetchone()

    d -= timedelta(days=1)
    d = d.astimezone(pytz.utc)
    d = d.replace(tzinfo=None)
    yesterday = d.strftime(format)

    cur.execute("SELECT misc FROM dc_fin WHERE datetime = %s AND item_id = %s ORDER BY datetime DESC LIMIT 1",
                (yesterday, "SBA"))
    close = cur.fetchall()

    if open > close:
        open_close = "increase"
    if open < close:
        open_close = "decrease"
    if open == close:
        open_close = "equal"

    # SBB : 오늘의 만기일 불러오기

    cur.execute("SELECT misc FROM dc_fin WHERE datetime = %s AND item_id = %s ORDER BY datetime ASC LIMIT 1",
                (today, "SBB"))
    misc_today = cur.fetchone()

    cur.execute("SELECT misc FROM dc_fin WHERE datetime = %s AND item_id = %s ORDER BY datetime DESC LIMIT 1",
                (yesterday, "SBB"))
    misc_yesterday = cur.fetchone()

    if misc_today > misc_yesterday:
        misc_trend = "increase"
    if misc_today < misc_yesterday:
        misc_trend = "decrease"
    if misc_today == misc_yesterday:
        misc_trend = "equal"

    # SBB 기간
    cur.execute("SELECT misc, datetime, misc2 FROM dc_fin WHERE item_id = %s ORDER BY datetime ASC", ("SBB",))
    SBB1 = cur.fetchall()
    period = []
    misc_dates = []
    period_z = []
    for misc in SBB1:
        period.append(misc[0])
        misc_dates.append(misc[1])
        period_z.append(misc[2])

    # SBA open
    cur.execute("SELECT misc, datetime FROM dc_fin WHERE item_id = %s ORDER BY datetime ASC", ("SBA",))
    SBA1 = cur.fetchall()
    SBA_rates = []
    SBA_dates = []
    for x in SBA1:
        SBA_rates.append(x[0])
        SBA_dates.append(x[1])

    # getting BB data
    cur.execute("""SELECT open, datetime FROM dc_fin WHERE item_id = %s ORDER BY datetime ASC LIMIT 360""", ("BB",))
    BB1 = cur.fetchall()
    BB_values = []
    BB_dates = []
    for values in BB1:
        BB_values.append(values[0])
        BB_dates.append(values[1])

    spot = BB_values[-1]

    cur.execute("""SELECT open FROM dc_fin WHERE item_id = %s AND datetime = %s ORDER BY datetime DESC LIMIT 1""",
                ("BB", yesterday))
    yesterday_spot = cur.fetchone()
    ys = int(yesterday_spot[0])

    spot_rate = round(((spot - ys) / ys) * 100, 2)

    if spot > ys:
        spot_trend = "increase"
    if spot < ys:
        spot_trend = "decrease"
    if spot == ys:
        spot_trend = "equal"

    # running functions timely

    format = "%S"
    a_datetime = datetime.now(pytz.timezone("Asia/Seoul"))
    seconds = a_datetime.strftime(format)

    interval = 60 - int(seconds)

    # getting price table for BB

    low1 = spot - 5
    low2 = spot - 10
    high1 = spot + 5
    high2 = spot + 10

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (spot, today, "uncleared", "BB", "offer"))
    spot_quantity = cur.fetchone()
    spot_quantity = int(spot_quantity[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (low1, today, "uncleared", "BB", "offer"))
    low1_quantity = cur.fetchone()
    low1_quantity = int(low1_quantity[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (low2, today, "uncleared", "BB", "offer"))
    low2_quantity = cur.fetchone()
    low2_quantity = int(low2_quantity[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (high1, today, "uncleared", "BB", "offer"))
    high1_quantity = cur.fetchone()
    high1_quantity = int(high1_quantity[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (high2, today, "uncleared", "BB", "offer"))
    high2_quantity = cur.fetchone()
    high2_quantity = int(high2_quantity[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (spot, today, "uncleared", "BB", "bid"))
    spot_quantity_buy = cur.fetchone()
    spot_quantity_buy = int(spot_quantity_buy[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (low1, today, "uncleared", "BB", "bid"))
    low1_quantity_buy = cur.fetchone()
    low1_quantity_buy = int(low1_quantity_buy[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (low2, today, "uncleared", "BB", "bid"))
    low2_quantity_buy = cur.fetchone()
    low2_quantity_buy = int(low2_quantity_buy[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (high1, today, "uncleared", "BB", "bid"))
    high1_quantity_buy = cur.fetchone()
    high1_quantity_buy = int(high1_quantity_buy[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (high2, today, "uncleared", "BB", "bid"))
    high2_quantity_buy = cur.fetchone()
    high2_quantity_buy = int(high2_quantity_buy[0])

    # getting call_date and end_date for SBB

    d = datetime.now(tz=pytz.timezone('Asia/Tokyo'))
    d = d + relativedelta(months=3)  # change this to misc_today (오늘의 만기일)
    end_date = d.strftime(format)
    end_date.replace("-", "월 ")
    end_date = end_date + "일"

    d = d + relativedelta(months=1)
    call_date = d.strftime(format)
    call_date.replace("-", "월 ")
    call_date = call_date + "일"

    # getting the current value

    if not session.get("username"):
        current_value = 0
        orig_value = 0
        profit = 0
        profit_rate = "equal"
    else:
        current_value = token_total * spot
        orig_value = token_total * buy_price
        profit1 = ((current_value - orig_value) / orig_value) * 100
        profit = round(profit1, 2)

        if orig_value > current_value:
            profit_rate = "decrease"
        if orig_value < current_value:
            profit_rate = "increase"
        if orig_value == current_value:
            profit_rate = "equal"

    # counting pending transactions if session exists

    if not session.get("username"):
        pending_total = 0
    else:
        cur.execute(
            "SELECT COUNT(*) FROM transactions WHERE username = %s AND datetime >= %s AND item_id = %s AND status = %s",
            (session.get("username"), today, "BB", "pending"))
        pending_total = cur.fetchone()

    cur.close()

    return render_template("index.html", period_z = period_z, bank_list = bank_list, ticket_total = ticket_total, pending_total = pending_total, profit = profit, profit_rate = profit_rate, token_total = token_total, buy_price = buy_price, spot_quantity = spot_quantity, spot_quantity_buy = spot_quantity_buy, spot = spot, low1 = low1, low2 = low2, high1 = high1, high2 = high2, low1_quantity = low1_quantity, low1_quantity_buy = low1_quantity_buy, low2_quantity = low2_quantity, low2_quantity_buy = low2_quantity_buy, high1_quantity = high1_quantity, high1_quantity_buy = high1_quantity_buy, high2_quantity = high2_quantity, high2_quantity_buy = high2_quantity_buy, end_date = end_date, call_date = call_date, yesterday_spot = yesterday_spot, interval = interval, spot_trend = spot_trend, spot_rate = spot_rate, BB_values = BB_values, BB_dates = BB_dates, SBA_rates = SBA_rates, SBA_dates = SBA_dates, period = period, misc_dates = misc_dates, misc_today = misc_today, misc_trend = misc_trend, open = open, open_close = open_close, mean_list = mean_list, time_list = time_list, favorable_up = favorable_up, favorable_down = favorable_down, profile_card = profile_card, chats = chats, chatrooms = chatrooms, news = news, item_list = item_list, favorable = favorable, user_info = user_info, msg = msg)

@app.route("/buy_BB", methods=['GET', 'POST'])
def buy_BB():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    spot = int(request.form.get("price"))
    ticket_total = int(request.form.get("ticket_total"))

    if session.get("username"):
        time_format = "%Y-%m-%d %H:%M"
        d = datetime.datetime.now(tz=pytz.timezone('Asia/Tokyo'))
        d = d - timedelta(minutes=1)
        now = d.strftime(time_format)

        day_format = "%Y-%m-%d"
        today = d.strftime(day_format)

        check_time_format = "%H:%M"
        check_time = d.strftime(check_time_format)
        check_day = d.weekday()

        if check_time >= '09:00' and check_time <= '15:00' and check_day < 6:

            cur.execute("SELECT SUM(price) FROM transactions WHERE username = %s AND datetime > %s AND position = %s AND status != %s AND item_id = %s", (session.get("username"), today, "bid", "cleared", "BB"))
            daily_transac = cur.fetchall()

            for price in daily_transac:
                if price + spot <= ticket_total:

                    cur.execute("SELECT * FROM transactions WHERE status = %s AND username != %s AND item_id = %s AND price = %s AND action = %s ORDER BY id ASC LIMIT 1", ('pending', '', 'BB', spot, 'offer'))
                    if cur.rowcount == 1:
                        seller = cur.fetchall()
                        for x in seller:
                            cur.execute("UPDATE transactions SET datetime = %s, status = %s WHERE id = %s", (now, 'cleared', x[0])) # row id
                            cur.execute("UPDATE users SET token_count = token_count - 1, ticket_count = ticket_count + %s WHERE username = %s", (spot, x[1])) # username

                        cur.execute("INSERT INTO transactions (datetime, price, action, username, status, item_id) VALUES (%s, %s, %s, %s, %s, %s)",
                        (now, spot, "bid", session.get("username"), "cleared", "BB"))

                        cur.execute("UPDATE users SET token_total = token_total + 1, ticket_count = ticket_count - %s WHERE username = %s", (spot, session.get("username")))

                        conn.commit()

                    else:
                        cur.execute("INSERT INTO transactions (datetime, price, action, username, status, item_id) VALUES (%s, %s, %s, %s, %s, %s)", (now, spot, "bid", session.get("username"), "uncleared", "BB"))
                        conn.commit()

                    msg = ""

        else:
            msg = "failed_time"

    else:
        msg = "failed_login"

    cur.execute("""SELECT * FROM talk ORDER BY system_date DESC LIMIT 3""")
    chats = cur.fetchall()

    cur.execute("""SELECT name, item_id, COUNT(item_id) AS count FROM talk GROUP BY name ORDER BY count DESC LIMIT 5""")
    chatrooms = cur.fetchall()

    cur.execute("""SELECT * FROM news ORDER BY system_date DESC LIMIT 7""")
    news = cur.fetchall()

    cur.execute("""SELECT * FROM analysis""")
    items = cur.fetchall()
    favorable = []
    item_list = []
    for item in items:
        if not session.get("username"):
            if item[3] == "AMZN":
                favorable.append(item)
            else:
                item_list.append(item)
        else:
            cur.execute("""SELECT * FROM preferences WHERE username = %s AND symbol = %s LIMIT 1""",
                        (session.get("username"), item[3]))
            exists = cur.fetchall()
            if len(exists) == 1:
                item_list.append(item)
            else:
                favorable.append(item)

    if not favorable:
        favorable.append(tuple(['AMZN', 'AMZN', 'AMZN']))  # should insert name and id too

    if not session.get("username"):
        profile_card = "no_user"
        user_info = None
        token_total = 0
        buy_price = 0
        ticket_total = 0
    else:
        profile_card = "logged_in"
        cur.execute("""SELECT * FROM users WHERE username = %s LIMIT 1""", (session.get("username"),))
        user_info = cur.fetchall()

        for user in user_info:
            token_total = user[6]  # quantity of token
            buy_price = user[7]  # price of token
            ticket_total = user[8]  # quantity of tickets

            if user[5] >= 50 + (100 * user[4]):
                cur.execute("UPDATE users SET level = level + 1 AND points = 0 WHERE username = %s ",
                            (session.get("username")))
                conn.commit()
                user_info = cur.fetchall()

    # getting bank info

    cur.execute("SELECT * FROM bank_list ORDER BY priority ASC")
    bank_list = cur.fetchall()

    # making the top list

    favorable_up = []
    favorable_down = []
    for fav in favorable:
        yticker = yf.Ticker(fav[3])
        df = yticker.history(period="2d")

        rate = round(((df['Close'][1] - df['Close'][0]) / df['Close'][0]) * 100)
        if df['Close'][1] < df['Close'][0]:
            add = (round(rate, 2),) + fav
            favorable_down.append(add)

        if df['Close'][1] > df['Close'][0]:
            add = (round(rate, 2),) + fav
            favorable_up.append(add)

        favorable_up.sort(reverse=True)
        favorable_down.sort(reverse=True)

        if not favorable_up:
            print("nothing")
        else:
            favorable_up = favorable_up[:5]

        if not favorable_down:
            print('nothing')
        else:
            favorable_down = favorable_down[:5]

    # 종가 불러오기
    frame = pd.DataFrame()
    for fav in favorable:
        data = yf.download(tickers=fav[3], period="365d", interval="1d", auto_adjust=True)
        frame[fav[3]] = round(data['Close'], 2)

    frame['mean'] = frame.mean(axis=1)

    mean_list = frame['mean'].tolist()

    frame['Date'] = pd.to_datetime(data.index)
    frame['time'] = frame['Date'].dt.strftime('%m/%d/%Y')

    time_list = frame['time'].tolist()

    print(time_list)

    time_list = ','.join("'{0}'".format(x) for x in time_list)

    print(time_list)

    # SBA : 오늘의 환율 불러오기

    format = "%Y-%m-%d"
    d = datetime.now(tz=pytz.timezone('Asia/Seoul'))
    today = d.strftime(format)

    cur.execute("SELECT misc FROM dc_fin WHERE datetime = %s AND item_id = %s ORDER BY datetime ASC LIMIT 1",
                (today, "SBA"))
    open = cur.fetchall()

    d -= timedelta(days=1)
    d = d.astimezone(pytz.utc)
    d = d.replace(tzinfo=None)
    yesterday = d.strftime(format)

    cur.execute("SELECT misc FROM dc_fin WHERE datetime = %s AND item_id = %s ORDER BY datetime DESC LIMIT 1",
                (yesterday, "SBA"))
    close = cur.fetchall()

    if open > close:
        open_close = "increase"
    if open < close:
        open_close = "decrease"
    if open == close:
        open_close = "equal"

    # SBB : 오늘의 만기일 불러오기

    cur.execute("SELECT misc FROM dc_fin WHERE datetime = %s AND item_id = %s ORDER BY datetime ASC LIMIT 1",
                (today, "SBB"))
    misc_today = cur.fetchall()

    cur.execute("SELECT misc FROM dc_fin WHERE datetime = %s AND item_id = %s ORDER BY datetime DESC LIMIT 1",
                (yesterday, "SBB"))
    misc_yesterday = cur.fetchall()

    if misc_today > misc_yesterday:
        misc_trend = "increase"
    if misc_today < misc_yesterday:
        misc_trend = "decrease"
    if misc_today == misc_yesterday:
        misc_trend = "equal"

    # line chart는 hover 살려두고 list를 "str"으로 표시하면 됨

    # SBB 기간
    cur.execute("SELECT misc, datetime FROM dc_fin WHERE item_id = %s ORDER BY datetime ASC", ("SBB",))
    SBB1 = cur.fetchall()
    period = []
    misc_dates = []
    for misc in SBB1:
        period.append(misc[0])
        misc_dates.append(misc[1])

    # SBA open
    cur.execute("SELECT misc, datetime FROM dc_fin WHERE item_id = %s ORDER BY datetime ASC", ("SBA",))
    SBA1 = cur.fetchall()
    SBA_rates = []
    SBA_dates = []
    for misc in SBA1:
        SBA_rates.append(misc[0])
        SBA_dates.append(misc[1])

    # getting BB data
    cur.execute("""SELECT open, datetime FROM dc_fin WHERE item_id = %s ORDER BY datetime ASC LIMIT 360""", ("BB",))
    BB1 = cur.fetchall()
    BB_values = []
    BB_dates = []
    for values in BB1:
        BB_values.append(values[0])
        BB_dates.append(values[1])

    spot = BB_values[-1]

    cur.execute("""SELECT open FROM dc_fin WHERE item_id = %s AND datetime = %s ORDER BY datetime DESC LIMIT 1""",
                ("BB", yesterday))
    yesterday_spot = cur.fetchone()
    ys = int(yesterday_spot[0])

    spot_rate = round(((spot - ys) / ys) * 100, 2)

    if spot > ys:
        spot_trend = "increase"
    if spot < ys:
        spot_trend = "decrease"
    if spot == ys:
        spot_trend = "equal"

    # running functions timely

    format = "%S"
    a_datetime = datetime.now(pytz.timezone("Asia/Seoul"))
    seconds = a_datetime.strftime(format)

    interval = 60 - int(seconds)

    # getting price table for BB

    low1 = spot - 5
    low2 = spot - 10
    high1 = spot + 5
    high2 = spot + 10

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (spot, today, "uncleared", "BB", "offer"))
    spot_quantity = cur.fetchone()
    spot_quantity = int(spot_quantity[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (low1, today, "uncleared", "BB", "offer"))
    low1_quantity = cur.fetchone()
    low1_quantity = int(low1_quantity[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (low2, today, "uncleared", "BB", "offer"))
    low2_quantity = cur.fetchone()
    low2_quantity = int(low2_quantity[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (high1, today, "uncleared", "BB", "offer"))
    high1_quantity = cur.fetchone()
    high1_quantity = int(high1_quantity[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (high2, today, "uncleared", "BB", "offer"))
    high2_quantity = cur.fetchone()
    high2_quantity = int(high2_quantity[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (spot, today, "uncleared", "BB", "bid"))
    spot_quantity_buy = cur.fetchone()
    spot_quantity_buy = int(spot_quantity_buy[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (low1, today, "uncleared", "BB", "bid"))
    low1_quantity_buy = cur.fetchone()
    low1_quantity_buy = int(low1_quantity_buy[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (low2, today, "uncleared", "BB", "bid"))
    low2_quantity_buy = cur.fetchone()
    low2_quantity_buy = int(low2_quantity_buy[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (high1, today, "uncleared", "BB", "bid"))
    high1_quantity_buy = cur.fetchone()
    high1_quantity_buy = int(high1_quantity_buy[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (high2, today, "uncleared", "BB", "bid"))
    high2_quantity_buy = cur.fetchone()
    high2_quantity_buy = int(high2_quantity_buy[0])

    # getting call_date and end_date for SBB

    d = datetime.now(tz=pytz.timezone('Asia/Tokyo'))
    d = d + relativedelta(months=3)  # change this to misc_today (오늘의 만기일)
    end_date = d.strftime(format)
    end_date.replace("-", "월 ")
    end_date = end_date + "일"

    d = d + relativedelta(months=1)
    call_date = d.strftime(format)
    call_date.replace("-", "월 ")
    call_date = call_date + "일"

    # getting the current value

    if not session.get("username"):
        current_value = 0
        orig_value = 0
        profit = 0
        profit_rate = "equal"
    else:
        current_value = token_total * spot
        orig_value = token_total * buy_price
        profit1 = ((current_value - orig_value) / orig_value) * 100
        profit = round(profit1, 2)

        if orig_value > current_value:
            profit_rate = "decrease"
        if orig_value < current_value:
            profit_rate = "increase"
        if orig_value == current_value:
            profit_rate = "equal"

    # counting pending transactions if session exists

    if not session.get("username"):
        pending_total = 0
    else:
        cur.execute(
            "SELECT COUNT(*) FROM transactions WHERE username = %s AND datetime >= %s AND item_id = %s AND status = %s",
            (session.get("username"), today, "BB", "pending"))
        pending_total = cur.fetchone()

    cur.close()

    return render_template("index.html", msg = msg, bank_list=bank_list, ticket_total=ticket_total, pending_total=pending_total,
                           profit=profit, profit_rate=profit_rate, token_total=token_total, buy_price=buy_price,
                           spot_quantity=spot_quantity, spot_quantity_buy=spot_quantity_buy, spot=spot, low1=low1,
                           low2=low2, high1=high1, high2=high2, low1_quantity=low1_quantity,
                           low1_quantity_buy=low1_quantity_buy, low2_quantity=low2_quantity,
                           low2_quantity_buy=low2_quantity_buy, high1_quantity=high1_quantity,
                           high1_quantity_buy=high1_quantity_buy, high2_quantity=high2_quantity,
                           high2_quantity_buy=high2_quantity_buy, end_date=end_date, call_date=call_date,
                           yesterday_spot=yesterday_spot, interval=interval, spot_trend=spot_trend, spot_rate=spot_rate,
                           BB_values=BB_values, BB_dates=BB_dates, SBA_rates=SBA_rates, SBA_dates=SBA_dates,
                           period=period, misc_dates=misc_dates, misc_today=misc_today, misc_trend=misc_trend,
                           open=open, open_close=open_close, mean_list=mean_list, time_list=time_list,
                           favorable_up=favorable_up, favorable_down=favorable_down, profile_card=profile_card,
                           chats=chats, chatrooms=chatrooms, news=news, item_list=item_list, favorable=favorable,
                           user_info=user_info)

@app.route("/buy_SBA", methods=['GET', 'POST'])
def buy_SBA():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    quantity = str(request.form.get("quantity"))
    misc = str(request.form.get("misc"))
    spot = str(request.form.get("price"))
    ticket_total = str(request.form.get("ticket_total"))

    if session.get("username"):
        time_format = "%Y-%m-%d %H:%M"
        d = datetime.datetime.now(tz=pytz.timezone('Asia/Tokyo'))
        d = d - timedelta(minutes=1)
        now = d.strftime(time_format)

        day_format = "%Y-%m-%d"
        today = d.strftime(day_format)

        check_time_format = "%H:%M"
        check_time = d.strftime(check_time_format)
        check_day = d.weekday()

        if check_time >= '09:00' and check_time <= '15:00' and check_day < 6:

            cur.execute("SELECT * FROM transactions WHERE username = %s AND status = %s AND item_id = %s LIMIT 1", (session.get("username"), "pending", "SBA"))
            if cur.rowcount == 1:
                msg = "exists_A"
            else:
                cur.execute("SELECT SUM(price) FROM transactions WHERE username = %s AND datetime > %s AND position = %s AND status != %s AND item_id = %s",
                (session.get("username"), today, "bid", "cleared", "BB"))
                daily_transac = cur.fetchall()

                for price in daily_transac:
                    if price + spot <= ticket_total:

                        cur.execute("INSERT INTO transactions (status, item_id, username, datetime, price, misc, misc2) VALUES (%s, %s, %s, %s, %s, %s, %s)", ('pending', 'SBA', session.get("username"), now, spot, misc, quantity))
                        cur.execute("UPDATE users SET ticket_total = ticket_total - %s AND token_total = token_total + 20 WHERE username = %s", (spot, session.get("username")))

                        conn.commit()

                    else:
                        msg = "notenough"

                msg = ""

        cur.execute("""SELECT * FROM users WHERE username = %s LIMIT 1""", (session.get("username"),))
        user_info = cur.fetchall()

        for user in user_info:
            token_total = user[6]  # quantity of token
            buy_price = user[7]  # price of token
            ticket_total = user[8]  # quantity of tickets

            cur.execute(
                "SELECT COUNT(*) FROM transactions WHERE username = %s AND datetime >= %s AND item_id = %s AND status = %s",
                (session.get("username"), today, "BB", "pending"))
            pending_total = cur.fetchone()

            cur.execute(
                "SELECT price FROM transactions WHERE item_id = %s AND datetime >= %s ORDER BY datetime DESC LIMIT 1",
                ("BB", now))
            spot = cur.fetchall
            if spot.rowcount < 1:
                cur.execute(
                    "SELECT open FROM dc_fin WHERE item_id = %s AND datetime > %s ORDER BY datetime DESC LIMIT 1",
                    ("BB", today))
                spot = cur.fetchall()

            current_value = token_total * spot
            orig_value = token_total * buy_price
            profit1 = ((current_value - orig_value) / orig_value) * 100
            profit = round(profit1, 2)

            if orig_value > current_value:
                profit_rate = "decrease"
            if orig_value < current_value:
                profit_rate = "increase"
            if orig_value == current_value:
                profit_rate = "equal"

        else:
            msg = "failed"

    cur.close()

    return render_template("coin.html", msg=msg, token_total=token_total, ticket_total=ticket_total,
                           buy_price=buy_price, pending_total=pending_total, profit=profit, profit_rate=profit_rate)

@app.route("/buy_SBB", methods=['GET', 'POST'])
def buy_SBB():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    jsonStr = request.get_json()

    spot = jsonStr['spot']
    ticket_total = jsonStr['ticket_total']
    call_date = jsonStr['call_date']
    end_date = jsonStr['end_date']

    # token_total is always +100

    if session.get("username"):
        time_format = "%Y-%m-%d %H:%M"
        d = datetime.datetime.now(tz=pytz.timezone('Asia/Tokyo'))
        d = d - timedelta(minutes=1)
        now = d.strftime(time_format)

        day_format = "%Y-%m-%d"
        today = d.strftime(day_format)

        check_time_format = "%H:%M"
        check_time = d.strftime(check_time_format)
        check_day = d.weekday()

        if check_time >= '09:00' and check_time <= '15:00' and check_day < 6:

            cur.execute("SELECT * FROM transactions WHERE username = %s AND status = %s AND item_id = %s LIMIT 1", (session.get("username"), "pending", "SBB"))
            if cur.rowcount == 1:
                msg = "exists_B"
            else:
                cur.execute("SELECT SUM(price) FROM transactions WHERE username = %s AND datetime > %s AND position = %s AND status != %s AND item_id = %s",
                (session.get("username"), today, "bid", "cleared", "BB"))
                daily_transac = cur.fetchall()

                for price in daily_transac:
                    if price + spot <= ticket_total:

                        cur.execute("INSERT INTO transactions (status, item_id, username, datetime, price, misc, misc2) VALUES (%s, %s, %s, %s, %s, %s, %s)", ('pending', 'SBB', session.get("username"), now, spot, end_date, call_date))
                        cur.execute("UPDATE users SET ticket_total = ticket_total - %s AND token_total = token_total + 100 WHERE username = %s", (spot, session.get("username")))

                        conn.commit()

                    else:
                        msg = "notenough"

                msg = ""

        cur.execute("""SELECT * FROM users WHERE username = %s LIMIT 1""", (session.get("username"),))
        user_info = cur.fetchall()

        for user in user_info:
            token_total = user[6]  # quantity of token
            buy_price = user[7]  # price of token
            ticket_total = user[8]  # quantity of tickets

            cur.execute(
                "SELECT COUNT(*) FROM transactions WHERE username = %s AND datetime >= %s AND item_id = %s AND status = %s",
                (session.get("username"), today, "BB", "pending"))
            pending_total = cur.fetchone()

            cur.execute(
                "SELECT price FROM transactions WHERE item_id = %s AND datetime >= %s ORDER BY datetime DESC LIMIT 1",
                ("BB", now))
            spot = cur.fetchall
            if spot.rowcount < 1:
                cur.execute(
                    "SELECT open FROM dc_fin WHERE item_id = %s AND datetime > %s ORDER BY datetime DESC LIMIT 1",
                    ("BB", today))
                spot = cur.fetchall()

            current_value = token_total * spot
            orig_value = token_total * buy_price
            profit1 = ((current_value - orig_value) / orig_value) * 100
            profit = round(profit1, 2)

            if orig_value > current_value:
                profit_rate = "decrease"
            if orig_value < current_value:
                profit_rate = "increase"
            if orig_value == current_value:
                profit_rate = "equal"

        else:
            msg = "failed"

    cur.close()

    return render_template("coin.html", msg=msg, token_total=token_total, ticket_total=ticket_total,
                           buy_price=buy_price, pending_total=pending_total, profit=profit, profit_rate=profit_rate)

@app.route('/bb_minute', methods=["POST"])
def bb_minute():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    cur.execute("""SELECT open, datetime FROM dc_fin WHERE item_id = %s ORDER BY datetime ASC LIMIT 360""", ("BB",))
    BB1 = cur.fetchall()
    BB_values = []
    BB_dates = []
    for values in BB1:
        BB_values.append(values[0])
        BB_dates.append(values[1])

    spot = BB_values[-1]

    yesterday_spot = request.args.get('yesterday_spot')

    spot_rate = ((spot - yesterday_spot) / yesterday_spot) * 100

    if spot > yesterday_spot:
        spot_trend = "increase"
    if spot < yesterday_spot:
        spot_trend = "decrease"
    if spot == yesterday_spot:
        spot_trend = "equal"

    cur.close()

    return render_template("BB_chart.html", BB_values = BB_values, BB_dates = BB_dates, yesterday_spot = yesterday_spot, spot_rate = spot_rate, spot_trend = spot_trend)

@app.route('/bb_day', methods=["POST"])
def bb_day():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    search_term = '09:00'
    perday = '%{}%'.format(search_term)

    cur.execute("""SELECT open, datetime FROM dc_fin WHERE item_id = %s AND datetime LIKE %s ORDER BY datetime ASC LIMIT 365""", ("BB", perday))
    BB1 = cur.fetchall()
    BB_values = []
    BB_dates = []
    for values in BB1:
        BB_values.append(values[0])
        BB_dates.append(values[1])

    spot = BB_values[-1]

    yesterday_spot = request.args.get('yesterday_spot')

    spot_rate = ((spot - yesterday_spot) / yesterday_spot) * 100

    if spot > yesterday_spot:
        spot_trend = "increase"
    if spot < yesterday_spot:
        spot_trend = "decrease"
    if spot == yesterday_spot:
        spot_trend = "equal"

    cur.close()

    return render_template("BB_chart.html", BB_values = BB_values, BB_dates = BB_dates, yesterday_spot = yesterday_spot, spot_rate = spot_rate, spot_trend = spot_trend)

@app.route('/day_list', methods=["POST"])
def day_list():
    global token_total, buy_price, ticket_total
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    cur.execute("""SELECT * FROM talk ORDER BY system_date DESC LIMIT 3""")
    chats = cur.fetchall()

    cur.execute("""SELECT name, item_id, COUNT(item_id) AS count FROM talk GROUP BY name ORDER BY count DESC LIMIT 5""")
    chatrooms = cur.fetchall()

    cur.execute("""SELECT * FROM news ORDER BY system_date DESC LIMIT 7""")
    news = cur.fetchall()

    cur.execute("""SELECT * FROM analysis""")
    items = cur.fetchall()

    if not session.get("username"):
        profile_card = "no_user"
        user_info = None
        token_total = 0
        buy_price = 0
        ticket_total = 0
    else:
        profile_card = "logged_in"
        cur.execute("""SELECT * FROM users WHERE username = %s LIMIT 1""", (session.get("username"),))
        user_info = cur.fetchall()

        for user in user_info:
            token_total = user[6]  # quantity of token
            buy_price = user[7]  # price of token
            ticket_total = user[8]  # quantity of tickets

            if user[5] >= 50 + (100 * user[4]):
                cur.execute("UPDATE users SET level = level + 1 AND points = 0 WHERE username = %s ",
                            (session.get("username")))
                conn.commit()
                user_info = cur.fetchall()

    # getting bank info

    cur.execute("SELECT * FROM bank_list ORDER BY priority ASC")
    bank_list = cur.fetchall()

    # making the top list

    favorable = request.form.get('fav_list')
    favorable = favorable.split(',')
    favorable = tuple(favorable,)

    item_list = []
    if not session.get("username"):
        item_list = favorable
    else:
        cur.execute("""SELECT * FROM preferences WHERE username = %s AND symbol = %s LIMIT 1""",
                    (session.get("username"), item[3]))
        exists = cur.fetchall()
        if len(exists) == 1:
            item_list.append(item)
        else:
            favorable.append(item)

    favorable_up = []
    favorable_down = []
    for fav in favorable:
        yticker = yf.Ticker(fav)
        df = yticker.history(period="2d")

        rate = ((df['Close'][1] - df['Close'][0]) / df['Close'][0]) * 100

        if df['Close'][1] < df['Close'][0]:
            add = (round(rate, 2), fav)
            favorable_down.append(add)

        if df['Close'][1] > df['Close'][0]:
            add = (round(rate, 2), fav)
            favorable_up.append(add)

        favorable_up.sort(reverse=True)
        favorable_down.sort(reverse=True)

        if not favorable_up:
            print("nothing")
        else:
            favorable_up = favorable_up[:5]

        if not favorable_down:
            print('nothing')
        else:
            favorable_down = favorable_down[:5]

    fav_list = []
    cur.execute("SELECT * FROM analysis")
    res = cur.fetchall()
    for a,b in zip(res,favorable):
        if a[3] == b:
            fav_list.append(a)

    favorable = fav_list
    if not session.get("username"):
        item_list = favorable # must be everything else

    # 종가 불러오기
    frame = pd.DataFrame()
    for fav in favorable:
        data = yf.download(tickers=fav[3], period="365d", interval="1d", auto_adjust=True)
        frame[fav[3]] = round(data['Close'], 2)

    frame['mean'] = frame.mean(axis=1)

    mean_list = frame['mean'].tolist()

    frame['Date'] = pd.to_datetime(data.index)
    frame['time'] = frame['Date'].dt.strftime('%m/%d/%Y')

    time_list = frame['time'].tolist()

    # 전일대비
    compare = ((frame['mean'][-1] - frame['mean'][-2]) / frame['mean'][-2]) * 100

    compare = round(compare, 2)
    if frame['mean'][-1] > frame['mean'][-2]:
        compare_rate = 'decrease'
    elif frame['mean'][-1] < frame['mean'][-2]:
        compare_rate = 'increase'
    elif frame['mean'][-1] == frame['mean'][-2]:
        compare_rate = 'equal'

    # SBA : 오늘의 환율 불러오기

    format = "%Y-%m-%d"
    d = datetime.now(tz=pytz.timezone('Asia/Seoul'))
    today = d.strftime(format)

    cur.execute("SELECT misc FROM dc_fin WHERE datetime = %s AND item_id = %s ORDER BY datetime ASC LIMIT 1",
                (today, "SBA"))
    open = cur.fetchall()

    d -= timedelta(days=1)
    d = d.astimezone(pytz.utc)
    d = d.replace(tzinfo=None)
    yesterday = d.strftime(format)

    cur.execute("SELECT misc FROM dc_fin WHERE datetime = %s AND item_id = %s ORDER BY datetime DESC LIMIT 1",
                (yesterday, "SBA"))
    close = cur.fetchall()

    if open > close:
        open_close = "increase"
    if open < close:
        open_close = "decrease"
    if open == close:
        open_close = "equal"

    # SBB : 오늘의 만기일 불러오기

    cur.execute("SELECT misc FROM dc_fin WHERE datetime = %s AND item_id = %s ORDER BY datetime ASC LIMIT 1",
                (today, "SBB"))
    misc_today = cur.fetchall()

    cur.execute("SELECT misc FROM dc_fin WHERE datetime = %s AND item_id = %s ORDER BY datetime DESC LIMIT 1",
                (yesterday, "SBB"))
    misc_yesterday = cur.fetchall()

    if misc_today > misc_yesterday:
        misc_trend = "increase"
    if misc_today < misc_yesterday:
        misc_trend = "decrease"
    if misc_today == misc_yesterday:
        misc_trend = "equal"

    # line chart는 hover 살려두고 list를 "str"으로 표시하면 됨

    # SBB 기간
    cur.execute("SELECT misc, datetime, misc2 FROM dc_fin WHERE item_id = %s ORDER BY datetime ASC", ("SBB",))
    SBB1 = cur.fetchall()
    period = []
    misc_dates = []
    period_z = []
    for misc in SBB1:
        period.append(misc[0])
        misc_dates.append(misc[1])
        period_z.append(misc[2])

    # SBA open
    cur.execute("SELECT misc, datetime FROM dc_fin WHERE item_id = %s ORDER BY datetime ASC", ("SBA",))
    SBA1 = cur.fetchall()
    SBA_rates = []
    SBA_dates = []
    for x in SBA1:
        SBA_rates.append(x[0])
        SBA_dates.append(x[1])

    open = SBA_rates[-1]

    SBA_trades = []
    cur.execute("SELECT misc2 FROM dc_fin WHERE item_id = %s ORDER BY datetime ASC", ('SBA',))
    SBA_trades1 = cur.fetchall()
    for x in SBA_trades1:
        y = x[0] * 10
        SBA_trades.append(y)

    # getting BB data
    cur.execute("""SELECT open, datetime FROM dc_fin WHERE item_id = %s ORDER BY datetime ASC LIMIT 360""", ("BB",))
    BB1 = cur.fetchall()
    BB_values = []
    BB_dates = []
    for values in BB1:
        BB_values.append(values[0])
        BB_dates.append(values[1])

    spot = BB_values[-1]

    cur.execute(
        """SELECT open FROM dc_fin WHERE item_id = %s AND datetime >= %s AND datetime < %s ORDER BY datetime DESC LIMIT 1""",
        ("BB", yesterday, today))
    yesterday_spot = cur.fetchone()
    ys = int(yesterday_spot[0])

    spot_rate = round(((spot - ys) / ys) * 100, 2)

    if spot > ys:
        spot_trend = "increase"
    if spot < ys:
        spot_trend = "decrease"
    if spot == ys:
        spot_trend = "equal"

    # running functions timely

    format = "%S"
    a_datetime = datetime.now(pytz.timezone("Asia/Seoul"))
    seconds = a_datetime.strftime(format)

    interval = 60 - int(seconds)  # not using

    # getting price table for BB

    low1 = spot - 5
    low2 = spot - 10
    high1 = spot + 5
    high2 = spot + 10

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (spot, today, "uncleared", "BB", "offer"))
    spot_quantity = cur.fetchone()
    spot_quantity = int(spot_quantity[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (low1, today, "uncleared", "BB", "offer"))
    low1_quantity = cur.fetchone()
    low1_quantity = int(low1_quantity[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (low2, today, "uncleared", "BB", "offer"))
    low2_quantity = cur.fetchone()
    low2_quantity = int(low2_quantity[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (high1, today, "uncleared", "BB", "offer"))
    high1_quantity = cur.fetchone()
    high1_quantity = int(high1_quantity[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (high2, today, "uncleared", "BB", "offer"))
    high2_quantity = cur.fetchone()
    high2_quantity = int(high2_quantity[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (spot, today, "uncleared", "BB", "bid"))
    spot_quantity_buy = cur.fetchone()
    spot_quantity_buy = int(spot_quantity_buy[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (low1, today, "uncleared", "BB", "bid"))
    low1_quantity_buy = cur.fetchone()
    low1_quantity_buy = int(low1_quantity_buy[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (low2, today, "uncleared", "BB", "bid"))
    low2_quantity_buy = cur.fetchone()
    low2_quantity_buy = int(low2_quantity_buy[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (high1, today, "uncleared", "BB", "bid"))
    high1_quantity_buy = cur.fetchone()
    high1_quantity_buy = int(high1_quantity_buy[0])

    cur.execute(
        "SELECT COUNT(*) AS count FROM transactions WHERE price = %s AND datetime >= %s AND status = %s AND item_id = %s AND action = %s",
        (high2, today, "uncleared", "BB", "bid"))
    high2_quantity_buy = cur.fetchone()
    high2_quantity_buy = int(high2_quantity_buy[0])

    # getting call_date and end_date for SBB

    d = datetime.now(tz=pytz.timezone('Asia/Tokyo'))
    d = d + relativedelta(months=3)  # change this to misc_today (오늘의 만기일)
    end_date = d.strftime(format)
    end_date.replace("-", "월 ")
    end_date = end_date + "일"

    d = d + relativedelta(months=1)
    call_date = d.strftime(format)
    call_date.replace("-", "월 ")
    call_date = call_date + "일"

    # getting the current value

    if not session.get("username"):
        current_value = 0
        orig_value = 0
        profit = 0
        profit_rate = "equal"
    else:
        current_value = token_total * spot
        orig_value = token_total * buy_price
        profit1 = ((current_value - orig_value) / orig_value) * 100
        profit = round(profit1, 2)

        if orig_value > current_value:
            profit_rate = "decrease"
        if orig_value < current_value:
            profit_rate = "increase"
        if orig_value == current_value:
            profit_rate = "equal"

    # counting pending transactions if session exists

    if not session.get("username"):
        pending_total = 0
    else:
        cur.execute(
            "SELECT COUNT(*) FROM transactions WHERE username = %s AND datetime >= %s AND item_id = %s AND status = %s",
            (session.get("username"), today, "BB", "pending"))
        pending_total = cur.fetchone()

    cur.close()

    return render_template("index.html", compare=compare, compare_rate=compare_rate, period_z=period_z,
                           SBA_trades=SBA_trades, bank_list=bank_list, ticket_total=ticket_total,
                           pending_total=pending_total, profit=profit, profit_rate=profit_rate, token_total=token_total,
                           buy_price=buy_price, spot_quantity=spot_quantity, spot_quantity_buy=spot_quantity_buy,
                           spot=spot, low1=low1, low2=low2, high1=high1, high2=high2, low1_quantity=low1_quantity,
                           low1_quantity_buy=low1_quantity_buy, low2_quantity=low2_quantity,
                           low2_quantity_buy=low2_quantity_buy, high1_quantity=high1_quantity,
                           high1_quantity_buy=high1_quantity_buy, high2_quantity=high2_quantity,
                           high2_quantity_buy=high2_quantity_buy, end_date=end_date, call_date=call_date,
                           yesterday_spot=yesterday_spot, spot_trend=spot_trend, spot_rate=spot_rate,
                           BB_values=BB_values, BB_dates=BB_dates, SBA_rates=SBA_rates, SBA_dates=SBA_dates,
                           period=period, misc_dates=misc_dates, misc_today=misc_today, misc_trend=misc_trend,
                           open=open, open_close=open_close, mean_list=mean_list, time_list=time_list,
                           favorable_up=favorable_up, favorable_down=favorable_down, profile_card=profile_card,
                           chats=chats, chatrooms=chatrooms, news=news, item_list=item_list, favorable=favorable,
                           user_info=user_info, anchor = 'Chart')

@app.route('/fave_list', methods=["POST"])
def fave_list():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    favorable = request.get_json()

    # making the top list - before update

    favorable_up = []
    favorable_down = []
    for fav in favorable:
        yticker = yf.Ticker(fav[3])
        df = yticker.history(period="2d")

        rate = ((df['Close'][1] - df['Close'][0]) / df['Close'][0]) * 100
        if df['Close'][1] < df['Close'][0]:
            add = (round(rate, 2),) + fav
            favorable_down.append(add)

        if df['Close'][1] > df['Close'][0]:
            add = (round(rate, 2),) + fav
            favorable_up.append(add)

    favorable_up.sort(reverse=True)
    favorable_down.sort(reverse=True)

    if not favorable_up:
        print("nothing")
    else:
        favorable_up = favorable_up[:5]

    if not favorable_down:
        print('nothing')
    else:
        favorable_down = favorable_down[:5]

    return render_template('fave_list.html', favorable_up = favorable_up, favorable_down = favorable_down)

@app.route('/add_favorites', methods=["POST"])
def add_favorites():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    symbol = request.args.get('symbol')

    cur.execute("INSERT INTO preferences (username, symbol) VALUES (%s, %s)", (session.get("username"), symbol))

    conn.commit()

    return True

@app.route('/remove_favorites', methods=["POST"])
def remove_favorites():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    symbol = request.args.get('symbol')

    cur.execute("DELETE FROM preferences WHERE username = %s AND symbol = %s", (session.get("username"), symbol))

    conn.commit()

    return True

@app.route('/register_form', methods=["POST"])
def register_form():
    cur = conn.cursor()

    username = str(request.form.get("username"))
    password = str(request.form.get("password"))

    hashed = hashlib.sha256(password.encode('utf-8')).hexdigest()

    login_error = None

    if len(username) == 0:
        profile_card = "register_form"
        user_info = None
    else:
        cur.execute("SELECT * FROM users WHERE username = %s AND password = %s LIMIT 1", (username, hashed))
        user_info = cur.fetchall()

        if len(user_info) == 1:
            profile_card = "logged_in"

            session["username"] = username

            for user in user_info:
                session["nickname"] = user[1]
        else:
            profile_card = "no_user"
            login_error = "wrong_credentials"

    chatrooms = popular_chatrooms()
    news = main_news()

    favorable, item_list = stock_preferences()
    profile_card = login_status()

    if not session.get("username"):
        ticket_total = 0
        token_total = 0
        buy_price = 0
        user_info = None
    else:
        user_info = user_details()
        for x in user_details():
            ticket_total = x[8]
            token_total = x[7]
            buy_price = x[6]

    bank_list = banks()

    favorable_up, favorable_down = top_list()
    mean_list, time_list, compare, compare_rate = stock_chart()

    open, open_close, SBA_rates, SBA_dates, SBA_trades = SBA_chart()
    misc_today, misc_trend, period_z, misc_dates, end_date, call_date, period = SBB_chart()

    spot_trend, spot_rate, BB_values, BB_dates, ys = BB_chart()
    spot = BB_spot()
    spot_quantity, spot_quantity_buy, low1, low2, high1, high2, low1_quantity, low1_quantity_buy, low2_quantity, low2_quantity_buy, high1_quantity, high1_quantity_buy, high2_quantity, high2_quantity_buy = BB_prices(
        spot)

    # getting the current value
    if not session.get("username"):
        current_value = 0
        orig_value = 0
        profit = 0
        profit_rate = "equal"
    else:
        profit, profit_rate, current_value, orig_value = my_value()

    # counting pending transactions if session exists
    if not session.get("username"):
        pending_total = 0
    else:
        pending_total = pending_orders()

    cur.close()

    return render_template("index.html", compare=compare, compare_rate=compare_rate, period_z=period_z,
                           SBA_trades=SBA_trades, bank_list=bank_list, ticket_total=ticket_total,
                           pending_total=pending_total, profit=profit, profit_rate=profit_rate, token_total=token_total,
                           buy_price=buy_price, spot_quantity=spot_quantity, spot_quantity_buy=spot_quantity_buy,
                           spot=spot, low1=low1, low2=low2, high1=high1, high2=high2, low1_quantity=low1_quantity,
                           low1_quantity_buy=low1_quantity_buy, low2_quantity=low2_quantity,
                           low2_quantity_buy=low2_quantity_buy, high1_quantity=high1_quantity,
                           high1_quantity_buy=high1_quantity_buy, high2_quantity=high2_quantity,
                           high2_quantity_buy=high2_quantity_buy, end_date=end_date, call_date=call_date, ys=ys,
                           spot_trend=spot_trend, spot_rate=spot_rate, BB_values=BB_values, BB_dates=BB_dates,
                           SBA_rates=SBA_rates, SBA_dates=SBA_dates, period=period, misc_dates=misc_dates,
                           misc_today=misc_today, misc_trend=misc_trend, open=open, open_close=open_close,
                           mean_list=mean_list, time_list=time_list, favorable_up=favorable_up,
                           favorable_down=favorable_down, profile_card=profile_card, chatrooms=chatrooms, news=news,
                           item_list=item_list, favorable=favorable, user_info=user_info, login_error = login_error)

@app.route("/register", methods=["POST"])
def register():
    cur = conn.cursor()

    username = str(request.form.get("username"))
    nickname = str(request.form.get("nickname"))
    password = str(request.form.get("password"))

    hashed = hashlib.sha256(password.encode('utf-8')).hexdigest()

    if len(username) == 0:
        profile_card = "login_form"
        login_error = None
    else:
        cur.execute("""SELECT * FROM users WHERE username = %s AND nickname = %s""", (username, nickname))
        user_exists = cur.fetchall()

        if len(user_exists) > 0:
            login_error = "existing_user"
            profile_card = "no_user"
            user_info = None
        else:
            cur.execute("""INSERT INTO users (username, nickname, password) VALUES (%s, %s, %s);""",
                    (username, nickname, hashed))

            conn.commit()

            profile_card = "logged_in"

            cur.execute("SELECT * FROM users WHERE username = %s", (username,))
            user_info = cur.fetchone()

            session["username"] = username
            session["nickname"] = nickname

    chatrooms = popular_chatrooms()
    news = main_news()

    favorable, item_list = stock_preferences()
    profile_card = login_status()

    if not session.get("username"):
        ticket_total = 0
        token_total = 0
        buy_price = 0
        user_info = None
    else:
        user_info = user_details()
        for x in user_details():
            ticket_total = x[8]
            token_total = x[7]
            buy_price = x[6]

    bank_list = banks()

    favorable_up, favorable_down = top_list()
    mean_list, time_list, compare, compare_rate = stock_chart()

    open, open_close, SBA_rates, SBA_dates, SBA_trades = SBA_chart()
    misc_today, misc_trend, period_z, misc_dates, end_date, call_date, period = SBB_chart()

    spot_trend, spot_rate, BB_values, BB_dates, ys = BB_chart()
    spot = BB_spot()
    spot_quantity, spot_quantity_buy, low1, low2, high1, high2, low1_quantity, low1_quantity_buy, low2_quantity, low2_quantity_buy, high1_quantity, high1_quantity_buy, high2_quantity, high2_quantity_buy = BB_prices(
        spot)

    # getting the current value
    if not session.get("username"):
        current_value = 0
        orig_value = 0
        profit = 0
        profit_rate = "equal"
    else:
        profit, profit_rate, current_value, orig_value = my_value()

    # counting pending transactions if session exists
    if not session.get("username"):
        pending_total = 0
    else:
        pending_total = pending_orders()

    cur.close()

    return render_template("index.html", compare=compare, compare_rate=compare_rate, period_z=period_z,
                           SBA_trades=SBA_trades, bank_list=bank_list, ticket_total=ticket_total,
                           pending_total=pending_total, profit=profit, profit_rate=profit_rate, token_total=token_total,
                           buy_price=buy_price, spot_quantity=spot_quantity, spot_quantity_buy=spot_quantity_buy,
                           spot=spot, low1=low1, low2=low2, high1=high1, high2=high2, low1_quantity=low1_quantity,
                           low1_quantity_buy=low1_quantity_buy, low2_quantity=low2_quantity,
                           low2_quantity_buy=low2_quantity_buy, high1_quantity=high1_quantity,
                           high1_quantity_buy=high1_quantity_buy, high2_quantity=high2_quantity,
                           high2_quantity_buy=high2_quantity_buy, end_date=end_date, call_date=call_date, ys=ys,
                           spot_trend=spot_trend, spot_rate=spot_rate, BB_values=BB_values, BB_dates=BB_dates,
                           SBA_rates=SBA_rates, SBA_dates=SBA_dates, period=period, misc_dates=misc_dates,
                           misc_today=misc_today, misc_trend=misc_trend, open=open, open_close=open_close,
                           mean_list=mean_list, time_list=time_list, favorable_up=favorable_up,
                           favorable_down=favorable_down, profile_card=profile_card, chatrooms=chatrooms, news=news,
                           item_list=item_list, favorable=favorable, user_info=user_info, login_error=login_error)

@app.route("/personal_edit", methods=["POST"])
def personal_edit():
    try:
        conn = psycopg2.connect(dbname='dc', user='postgres', password='snowai**', host='172.30.1.96', port='5432')
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    nickname = str(request.form.get("nickname"))
    bank1 = str(request.form.get("bank"))
    address = str(request.form.get("address"))

    if bank1 == "은행/코인":
        bank = ""
    else:
        bank = bank1

    cur.execute("""UPDATE users SET nickname = %s, bank_info = %s, bank_misc = %s, WHERE username = %s""", (nickname, bank, address, session.get("username")))
    conn.commit()

    profile_card = "logged_in"
    session['nickname'] = nickname

    cur.execute("""SELECT * FROM users WHERE username = %s LIMIT 1""", (session.get("username"),))
    user_info = cur.fetchall()

    return render_template("index.html", profile_card=profile_card, user_info=user_info)

@app.route("/logout", methods=["POST"])
def logout():
    session["username"] = None
    session["nickname"] = None

    chatrooms = popular_chatrooms()
    news = main_news()

    favorable, item_list = stock_preferences()
    profile_card = login_status()

    if not session.get("username"):
        ticket_total = 0
        token_total = 0
        buy_price = 0
        user_info = None
    else:
        user_info = user_details()
        for x in user_details():
            ticket_total = x[8]
            token_total = x[7]
            buy_price = x[6]

    bank_list = banks()

    favorable_up, favorable_down = top_list()
    mean_list, time_list, compare, compare_rate = stock_chart()

    open, open_close, SBA_rates, SBA_dates, SBA_trades = SBA_chart()
    misc_today, misc_trend, period_z, misc_dates, end_date, call_date, period = SBB_chart()

    spot_trend, spot_rate, BB_values, BB_dates, ys = BB_chart()
    spot = BB_spot()
    spot_quantity, spot_quantity_buy, low1, low2, high1, high2, low1_quantity, low1_quantity_buy, low2_quantity, low2_quantity_buy, high1_quantity, high1_quantity_buy, high2_quantity, high2_quantity_buy = BB_prices(
        spot)

    # getting the current value
    if not session.get("username"):
        current_value = 0
        orig_value = 0
        profit = 0
        profit_rate = "equal"
    else:
        profit, profit_rate, current_value, orig_value = my_value()

    # counting pending transactions if session exists
    if not session.get("username"):
        pending_total = 0
    else:
        pending_total = pending_orders()

    return render_template("index.html", compare=compare, compare_rate=compare_rate, period_z=period_z,
                           SBA_trades=SBA_trades, bank_list=bank_list, ticket_total=ticket_total,
                           pending_total=pending_total, profit=profit, profit_rate=profit_rate, token_total=token_total,
                           buy_price=buy_price, spot_quantity=spot_quantity, spot_quantity_buy=spot_quantity_buy,
                           spot=spot, low1=low1, low2=low2, high1=high1, high2=high2, low1_quantity=low1_quantity,
                           low1_quantity_buy=low1_quantity_buy, low2_quantity=low2_quantity,
                           low2_quantity_buy=low2_quantity_buy, high1_quantity=high1_quantity,
                           high1_quantity_buy=high1_quantity_buy, high2_quantity=high2_quantity,
                           high2_quantity_buy=high2_quantity_buy, end_date=end_date, call_date=call_date, ys=ys,
                           spot_trend=spot_trend, spot_rate=spot_rate, BB_values=BB_values, BB_dates=BB_dates,
                           SBA_rates=SBA_rates, SBA_dates=SBA_dates, period=period, misc_dates=misc_dates,
                           misc_today=misc_today, misc_trend=misc_trend, open=open, open_close=open_close,
                           mean_list=mean_list, time_list=time_list, favorable_up=favorable_up,
                           favorable_down=favorable_down, profile_card=profile_card, chatrooms=chatrooms, news=news,
                           item_list=item_list, favorable=favorable, user_info=user_info)

@app.route("/item")
def item():
    item_id = request.args.get('id', default='ns-abc-aaa', type=str)

    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    cur.execute("""SELECT * FROM news WHERE item_id = %s ORDER BY system_date DESC LIMIT 50""", (item_id,))
    news = cur.fetchall()

    cur.execute("""SELECT * FROM analysis WHERE item_id = %s""", (item_id,))
    item_info = cur.fetchall()

    if not session.get("username"):
        profile_card = "no_user"
        user_info = None
    else:
        profile_card = "logged_in"
        cur.execute("""SELECT * FROM users WHERE username = %s LIMIT 1""", (session.get("username"),))
        user_info = cur.fetchall()

        for user in user_info:
            if user[5] >= 50 + (100 * user[4]):
                cur.execute("UPDATE users SET level = level + 1 AND points = 0 AND total = total + points WHERE username = %s ",
                            (session.get("username")))
                conn.commit()
                user_info = cur.fetchall()

    cur.execute("SELECT system_date, close FROM yfin WHERE item_id = %s ORDER BY system_date ASC LIMIT 7", (item_id,))
    graph_data = cur.fetchall()
    labels = []
    data = []
    for point in graph_data:
        labels.append(point[0])
        data.append(point[1])

    tickers = ['ABEV3.SA']
    for ticker in tickers:
        ticker_yahoo = yf.Ticker(ticker)
        data1 = ticker_yahoo.history()
        last_quote = data1['Close'].iloc[-1]
        tick_price = round(last_quote, 2)

    rate = ((tick_price - data[-1]) / data[-1]) * 100
    if tick_price < data[-1]:
        sign = "decrease"
    if tick_price > data[-1]:
        sign = "increase"
    if tick_price == data[-1]:
        sign = "equal"

    cur.close()

    start_date = None
    end_date = None

    return render_template("item.html", rate = rate, sign = sign, tick_price = tick_price, profile_card = profile_card, user_info = user_info, news = news, item_info = item_info, labels = labels, data = data)

@app.route("/item_personal_edit", methods=["POST"])
def item_personal_edit():
    try:
        conn = psycopg2.connect(dbname='dc', user='postgres', password='snowai**', host='172.30.1.96', port='5432')
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    nickname = str(request.form.get("nickname"))

    cur.execute("""UPDATE users SET nickname = %s WHERE username = %s""", (nickname, session.get("username")))
    conn.commit()

    profile_card = "logged_in"

    cur.execute("""SELECT * FROM users WHERE username = %s LIMIT 1""", (session.get("username"),))
    user_info = cur.fetchall()

    return render_template("item.html", profile_card=profile_card, user_info=user_info)

@app.route("/discussion")
def discussion():
    item_id = request.args.get('id', default='ns-abc-aaa', type=str)

    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    cur.execute("""SELECT * FROM news WHERE item_id = %s ORDER BY system_date DESC LIMIT 100""", (item_id,))
    news = cur.fetchall()

    cur.execute("""SELECT * FROM analysis WHERE item_id = %s""", (item_id,))
    item_info = cur.fetchall()

    cur.close()

    return render_template("discussion.html", news = news, item_info = item_info)

@app.route("/add_chat", methods=['GET', 'POST'])
def add_chat():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    dt = datetime.now()
    ts = datetime.timestamp(dt)

    res = ''.join(random.choices(string.ascii_uppercase +
                                 string.digits, k=7))
    id = str(ts)+res

    timeZ_Kl = pytz.timezone('Asia/Seoul')
    currentTime = datetime.now(timeZ_Kl)

    jsonStr = request.get_json()

    text = jsonStr['text']
    item_id = jsonStr['item_id']
    name = jsonStr['name']

    if not session.get("username"):
        cur.execute("""INSERT INTO talk (nickname, text, item_id, system_date, name, id) VALUES (%s, %s, %s, %s, %s, %s)""",
            ("게스트", text, item_id, currentTime, name, id))
    else:
          cur.execute("""INSERT INTO talk (username, nickname, text, item_id, system_date, name, id) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                 (session.get("username"), session.get("nickname"), text, item_id, currentTime, name, id))

    conn.commit()

    if session.get("username"):
        cur.execute("UPDATE users SET points = points + 5 WHERE username = %s", (session.get("username")))

    conn.commit()

    cur.close()

    return json.dumps({'success':True}), 200, {'ContentType':'application/json'}

@app.route("/reload_chat", methods=['GET', 'POST'])
def reload_chat():
    cur = conn.cursor()

    params = request.get_data()
    item_id = params.decode('utf-8')

    cur.execute("""SELECT * FROM talk WHERE item_id = %s ORDER BY system_date DESC LIMIT 100""", (item_id,))

    chatlist = []
    for row in cur.fetchall():
        chatlist.append("{}, {}, {}".format(row[1], row[2], row[7]))

    list = []
    for chat in chatlist:
        list = [chat.split(',')]

    cur.close()

    return render_template('chat.html', list = list, chatlist = chatlist)

@app.route("/add_news", methods=['GET', 'POST'])
def add_news():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    dt = datetime.now()
    ts = datetime.timestamp(dt)

    res = ''.join(random.choices(string.ascii_uppercase +
                                 string.digits, k=7))
    id = str(ts)+res

    timeZ_Kl = pytz.timezone('Asia/Seoul')
    currentTime = datetime.now(timeZ_Kl)

    jsonStr = request.get_json()

    text = jsonStr['text']
    item_id = jsonStr['item_id']
    name = jsonStr['name']
    link = jsonStr['link']

    if not session.get("username"):
        cur.execute("""INSERT INTO news (nickname, title, link, item_id, system_date, sub_category, id) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            ("게스트", text, link, item_id, currentTime, name, id))
    else:
          cur.execute("""INSERT INTO news (username, nickname, title, link, item_id, system_date, sub_category, id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                 (session.get("username"), session.get("nickname"), text, link, item_id, currentTime, name, id))

    conn.commit()

    if session.get("username"):
       cur.execute("UPDATE users SET points = points + 10 WHERE username = %s", (session.get("username")))

    conn.commit()

    cur.close()

    return json.dumps({'success':True}), 200, {'ContentType':'application/json'}

@app.route("/reload_news", methods=['GET', 'POST'])
def reload_news():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    item_id = request.args.get('item_id')

    cur.execute("""SELECT * FROM news WHERE item_id = %s ORDER BY system_date DESC LIMIT 100""", (item_id,))

    chatlist = []
    for row in cur.fetchall():
        chatlist.append("{}, {}, {}, {}".format(row[1], row[2], row[3], row[5]))

    for chat in chatlist:
        list = [chat.split(',')]

    cur.close()

    return render_template('news.html', list = list, chatlist = chatlist)

@app.route('/pending', methods=["POST"])
def pending():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    if not session.get("username"):
        data = "no_user"
    else:
        cur.execute("SELECT * FROM transactions WHERE status != %s AND username = %s ORDER BY datetime DESC", ("cleared", session.get("username")))
        data = cur.fetchall()

    cur.close()

    return render_template("pending.html", data = data)

@app.route('/history', methods=["POST"])
def history():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    # cleared transactions

    cur.execute("""SELECT * FROM transactions WHERE username = %s AND status = %s GROUP BY datetime ORDER BY id DESC""", (session.get("username"), "cleared"))
    cleared_data = cur.fetchall()

    # pending transactions

    cur.execute("""SELECT * FROM transactions WHERE username = %s AND status != %s GROUP BY datetime ORDER BY id DESC""", (session.get("username"), "cleared"))
    pending_data = cur.fetchall()

    # is holding SBA

    cur.execute("SELECT * FROM transactions WHERE username = %s AND status != %s AND item_id = %s", (session.get("username"), "cleared", "SBA"))
    result = cur.fetchall()
    if result.rowcount == 1:

        for x in result:
            date = x[0] # datetime
            filter = date.split(" ")
            integer = filter[0].split("-")

            months = int(x[9]) # misc

            misc_months = datetime.date(int(integer[0]), int(integer[1]), int(integer[2])) + relativedelta(months=+months)

            format = "%Y-%m-%d"
            a_datetime = datetime.datetime.now(pytz.timezone("Asia/Seoul"))
            today = a_datetime.strftime(format)

            if misc_months <= today:
                cur.execute("UPDATE transactions SET status = %s, datetime = %s WHERE username = %s AND item_id = %s", ("cleared", misc_months, session.get("username"), "SBA"))
                conn.commit()

                SBA_info = "none"
            else:
                SBA_info = result


            # if fixed to 3 months

            first_month = datetime.date(int(integer[0]), int(integer[1]), int(integer[2])) + relativedelta(months=+1)
            second_month = datetime.date(int(integer[0]), int(integer[1]), int(integer[2])) + relativedelta(months=+2)

            if today > first_month and today < second_month:
                cur.execute("SELECT COUNT(*) FROM transactions WHERE datetime >= %s AND username = %s AND item_id = %s AND status = %s", (x[0], session.get("username"), "SBA", "cleared"))
                counted = cur.fetchall()
                if counted == 0:
                    # clear
                    cur.execute("UPDATE transactions SET datetime = %s, status = %s WHERE username = %s AND item_id = %s AND status = %s", (today, "cleared", session.get("username"), "SBA", "pending"))
                    conn.commit()
                    next_payment = "none"
                    end_date = "none"
                elif counted == 1:
                    next_payment = second_month
                    end_date = "none"
                elif counted == 2:
                    next_payment = "none"
                    end_date = misc_months
            elif today <= first_month:
                cur.execute("SELECT COUNT(*) FROM transactions WHERE datetime >= %s AND username = %s AND item_id = %s AND status = %s",
                    (x[0], session.get("username"), "SBA", "cleared"))
                counted = cur.fetchall()
                if counted == 0:
                    next_payment = first_month
                    end_date = "none"
                elif counted == 1:
                    next_payment = second_month
                    end_date = "none"
                elif counted == 2:
                    end_date = misc_months
                    next_payment = "none"
            elif today > second_month:
                cur.execute("SELECT COUNT(*) FROM transactions WHERE datetime >= %s AND username = %s AND item_id = %s AND status = %s",
                    (x[0], session.get("username"), "SBA", "cleared"))
                counted = cur.fetchall()
                if counted == 1:
                    # clear
                    cur.execute(
                        "UPDATE transactions SET datetime = %s, status = %s WHERE username = %s AND item_id = %s AND status = %s",
                        (today, "cleared", session.get("username"), "SBA", "pending"))
                    conn.commit()
                elif counted == 2:
                    end_date = misc_months
                    next_payment = "none"

    else:
        SBA_info = "none"

    # is holding SBB

    cur.execute("SELECT * FROM transactions WHERE username = %s AND status != %s AND item_id = %s", (session.get('username'), "cleared", "SBB"))
    res = cur.fetchall()
    if res.rowcount == 1:
        SBB_info = res

        format = "%Y-%m-%d %H:%M"
        a_datetime = datetime.datetime.now(pytz.timezone("Asia/Seoul"))
        today = a_datetime.strftime(format)

        for x in res:
            if x[0] == today: # i think misc
                isDue = "true"
            else:
                if x[1] >= today: # i think misc2
                    isDue = "callable"
                else:
                    isDue = "premature"
    else:
        SBB_info = "none"
        isDue = "none"

    # retrieving crypto info

    cur.execute("SELECT * FROM bank_info WHERE type = %s ORDER BY priority ASC", ('coin',))
    crypto = cur.fetchall()

    cryptos = []
    for x in crypto:
        url = ("https://api.upbit.com/v1/candles/days?market=%s&count=%d" % (x[0], 1)) # coin symbol
        raw_resp = requests.get(url)
        response = raw_resp.json()
        cryptos.append((x[1], x[2], response[0]['trade_price'])) # name, address, trade_price

    memo = hash(session.get("username"))
    memo = abs(memo)

    # ticket_total

    cur.execute("""SELECT * FROM users WHERE username = %s LIMIT 1""", (session.get("username"),))
    user_info = cur.fetchall()

    cur.close()

    return render_template("history.html", user_info = user_info, isDue = isDue, memo = memo, cryptos = cryptos, SBA_info = SBA_info, SBB_info = SBB_info, cleared_data = cleared_data, pending_data = pending_data, next_payment = next_payment, end_date = end_date)

@app.route('/refresh_upbit', methods=["POST"])
def refresh_upbit():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    # retrieving crypto info

    cur.execute("SELECT * FROM upbit_fin ORDER BY priority ASC")
    crypto = cur.fetchall()

    cryptos = []
    for x in crypto:
        url = ("https://api.upbit.com/v1/candles/days?market=%s&count=%d" % (x[0], 1))  # coin symbol
        raw_resp = requests.get(url)
        response = raw_resp.json()
        cryptos.append((x[1], x[2], response[0]['trade_price']))  # name, address, trade_price

    memo = hash(session.get("username"))
    memo = abs(memo)

    cur.close()

    return render_template("crypto.html", cryptos = cryptos, memo = memo)

@app.route('/charge', methods=["POST"])
def charge():
    try:
        conn = psycopg2.connect(dbname='dc', user='postgres', password='snowai**', host='172.30.1.96', port='5432')
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    value = str(request.form.get("value"))
    memo = str(request.form.get("memo"))
    coin = str(request.form.get("coin_name"))

    format = "%Y-%m-%d %H:%M:%S"
    d = datetime.datetime.now(tz=pytz.timezone('Asia/Seoul'))
    now = d.strftime(format)

    cur.execute("INSERT INTO transactions(datetime, price, username, status, item_id, misc, misc2, action) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (now, value, session.get("username"), 'pending', 'ticket', memo, coin, 'insert'))
    conn.commit()

    # pending transactions

    cur.execute("""SELECT * FROM transactions WHERE username = %s AND status != %s ORDER BY datetime DESC""",
                (session.get("username"), "cleared"))
    pending_data = cur.fetchall()

    cur.close()

    return render_template("history.html", pending_data = pending_data)

@app.route('/extract', methods=["POST"])
def extract():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    change_amt = request.args.get('change_amt')

    format = "%Y-%m-%d %H:%M"
    a_datetime = datetime.datetime.now(pytz.timezone("Asia/Seoul"))
    today = a_datetime.strftime(format)

    cur.execute("INSERT INTO transactions (username, price, item_id, action, status, datetime) VALUES (%s, %s, %s, %s, %s, %s)", (session.get('username'), change_amt, 'ticket', 'extract', today))
    conn.commit()

    cur.close()

    return render_template("history.html")

@app.route('/cancel_SBA', methods=["POST"])
def cancel_SBA():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    cur.execute("""UPDATE transactions SET status = %s WHERE username = %s AND item_id = %s""", ("cleared", session.get('username'), "SBA"))
    conn.commit()

    cur.close()

    return render_template("history.html")

@app.route('/cancel_SBB', methods=["POST"])
def cancel_SBB():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    cur.execute("""UPDATE transactions SET status = %s WHERE username = %s AND item_id = %s""",
                ("cleared", session.get('username'), "SBB"))
    conn.commit()

    cur.close()

    return render_template("history.html")

@app.route('/cancel_BB', methods=["POST"])
def cancel_BB():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        print("I am unable to connect to the database")

    cur = conn.cursor()

    data = request.args.get('data')

    cur.execute("DELETE FROM transactions WHERE id = %s", (data,))
    conn.commit()

    # pending transactions

    cur.execute("""SELECT * FROM transactions WHERE username = %s AND status != %s ORDER BY datetime DESC""",
                (session.get("username"), "cleared"))
    pending_data = cur.fetchall()

    cur.close()

    return render_template("history.html", pending_data = pending_data)

@app.route('/pay_SBA', methods=["POST"])
def pay_SBA():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        action = "I am unable to connect to the database" # better to log

    cur = conn.cursor()

    jsonStr = request.get_json()

    SBA_pay = jsonStr['SBA_pay']
    SBA_get = jsonStr['SBA_get']

    format = "%Y-%m-%d %H:%M"
    a_datetime = datetime.datetime.now(pytz.timezone("Asia/Seoul"))
    today = a_datetime.strftime(format)

    cur.execute("""SELECT * FROM users WHERE username = %s LIMIT 1""", (session.get("username"),))
    user_info = cur.fetchall()

    for user in user_info:
        ticket_total = user[8]  # quantity of tickets

        if ticket_total + SBA_pay >= SBA_pay:
            cur.execute("INSERT INTO transactions (item_id, status, datetime, username, price) VALUES (%s, %s, %s, %s, %s)", ("SBA", "cleared", today, session.get("username"), SBA_pay))
            cur.execute("UPDATE users SET token_total = token_total = %s WHERE username = %s", (SBA_get, session.get("username")))
            cur.execute("UPDATE users SET ticket_total = ticket_total - %s WHERE username = %s", (SBA_pay, session.get("username")))

            conn.commit()

            action = ""
        else:
            action = "failed_SBA"

    cur.close()

    return render_template("history.html", action=action)

@app.route('/pay_SBB', methods=["POST"])
def pay_SBB():
    try:
        conn = psycopg2.connect("dbname='postgres' user='postgres' host='localhost' password='1225'")
    except:
        action = "I am unable to connect to the database" # better to log

    cur = conn.cursor()

    jsonStr = request.get_json()

    SBB_pay = jsonStr['SBB_pay']
    SBB_get = jsonStr['SBB_get']

    format = "%Y-%m-%d %H:%M"
    a_datetime = datetime.datetime.now(pytz.timezone("Asia/Seoul"))
    today = a_datetime.strftime(format)

    cur.execute("""SELECT * FROM users WHERE username = %s LIMIT 1""", (session.get("username"),))
    user_info = cur.fetchall()

    for user in user_info:
        token_total = user[6]  # quantity of token

    if token_total + SBB_pay >= SBB_pay:
        cur.execute("UPDATE transactions SET status = %s, datetime = %s WHERE item_id = %s, username = %s", ("cleared", today, "SBB", session.get("username")))
        cur.execute("UPDATE users SET token_total = token_total - %s WHERE username = %s", (SBB_pay, session.get("username")))
        cur.execute("UPDATE users SET ticket_total = ticket_total + %s WHERE username = %s", (SBB_get, session.get("username")))

        action = ""
    else:
        action = "failed_BB"

    conn.commit()

    cur.close()

    return render_template("history.html", action=action)

if __name__ == '__main__':
    app.run(debug=True, host=os.getenv("OPENSHIFT__IP"), port=os.getenv("OPENSHIFT__PORT"))
