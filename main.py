# Import necessary libraries and modules
import os
import sys
import logging
from flask import Flask, request, jsonify
import threading
import csv
import datetime as dt
import datetime
import time
import pyotp
from api_helper import ShoonyaApiPy
import requests

# Initialize the Flask application
app = Flask(__name__)

# Global variables and data structures
client = ShoonyaApiPy()  # API client instance
traded_stocks = {}  # Dictionary to keep track of traded stocks
feedJson = {}  # Store feed updates
orderJson = {}  # Store order updates
risk_per_trade = 50  # Risk limit for each trade
feed_opened = False
socket_opened = False

# Replace with your bot token and channel ID
TELEGRAM_TOKEN = '6888570471:AAHrA5D6hF0ly_4k2r0BxcO7Td2w6d_qFGo'
TELEGRAM_CHANNEL_ID = '@ge11'

# Utility Functions
def custom_round(number):
    """
    Custom rounding function to round a number to 2 decimal places.
    It rounds up if the third decimal is 5 or more, and rounds down otherwise.

    :param number: The number to be rounded
    :return: Rounded number with 2 decimal places
    """
    return round(number, 2)

def calculate_quantity(entry_price, stop_loss_price):
    """
    Calculate the quantity to buy based on the risk per trade and price difference.

    :param entry_price: The entry price for the trade
    :param stop_loss_price: The stop loss price for the trade
    :return: Quantity of stocks to buy
    """
    return int(risk_per_trade / (entry_price - stop_loss_price))

def round_to_tick_size(price, tick_size=0.05):
    """
    Round the price to the nearest tick size.

    :param price: The price to be rounded
    :param tick_size: The tick size for rounding
    :return: Price rounded to the nearest tick size
    """
    return round(price / tick_size) * tick_size

def send_telegram_message(message):
    """
    Sends a message to a specified Telegram channel.

    :param message: The message to be sent
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHANNEL_ID, "text": message}
    response = requests.post(url, data)
    if not response.ok:
        logging.error(f"Failed to send Telegram message: {response.text}")


# Core Logic Functions
        
# Callback function for opening the WebSocket connection
def open_callback():
    """
    Callback function that is called when the WebSocket connection is opened.
    """
    print("WebSocket Connection Opened")
    global feed_opened
    feed_opened = True
    global socket_opened
    socket_opened = True        

# Function to handle order updates
def event_handler_order_update(imessage):
    """
    Handles updates for orders.

    :param imessage: The message received about an order update
    """
    if 'norenordno' in imessage and 'status' in imessage:
        order_id = imessage['norenordno']
        status = imessage['status']
        orderJson[order_id] = {'status': status}
        print(f"Order Update Received: Order ID: {order_id}, Status: {status}")

# Function to handle quote updates
def event_handler_quote_update(message):
    """
    Handles updates for stock quotes.

    :param message: The message received about a quote update
    """
    if 'lp' in message and "tk" in message:
        feedJson[message['tk']] = {'ltp': float(message['lp'])}
        #print(f"Quote Update Received for Token {message['tk']}: Last Traded Price: {message['lp']}")

# Function to manage WebSocket connection
def manage_websocket():
   
  #Raj Login
    totptoken = "5K7NP64475SK6BY756T5G754U6VAT667"
    user_id = "FA197319"
    password = "9b@Iloves@9" 
    twoFA=pyotp.TOTP(totptoken).now()
    vendor_code = "FA197319_U"
    api_secret = "da0c8f007da51e5a11ee7863f8b62d93"
    imei = "abc1234"

    #Raj is cool
    # Perform login
    ret = client.login(userid=user_id, password=password, twoFA=twoFA,
                       vendor_code=vendor_code, api_secret=api_secret, imei=imei)
    
    print(ret)

    if ret:
        client.start_websocket(order_update_callback=event_handler_order_update,
                            subscribe_callback=event_handler_quote_update,
                            socket_open_callback=open_callback)

# Function to find symbol details in a CSV file
def find_symbol_details(file_path, search_symbol):
    """
    Finds symbol details from a CSV file.

    :param file_path: Path to the CSV file
    :param search_symbol: Symbol to search for
    :return: A dictionary of symbol details if found, None otherwise
    """
    with open(file_path, 'r') as file:
        csv_reader = csv.DictReader(file, delimiter=',')
        for row in csv_reader:
            if row['Symbol'].strip() == search_symbol:
                return {
                    'TradingSymbol': row['TradingSymbol'].strip(),
                    'TickSize': float(row['TickSize'].strip()),
                    'Token': row['Token'].strip()
                }
    return None

# Function to parse trigger time
def parse_trigger_time(trigger_time_str):
    """
    Parses a trigger time string to a datetime object.

    :param trigger_time_str: Trigger time string in the format 'HH:MM %p'
    :return: datetime object representing the trigger time
    """
    return dt.datetime.strptime(trigger_time_str, "%I:%M %p").time()

def get_todays_opening_price(api, token):
    """
    Retrieves today's opening price for a given stock token.

    :param api: API client instance for fetching candle data.
    :param token: Stock token to fetch data for.
    :return: Today's opening price or None if not available.
    """
    # Set the date range to the current trading day
    current_date = dt.datetime.now().date()
    start_time = current_date.replace(hour=9, minute=15, second=0, microsecond=0)

    # Fetch the first candle data of the day
    end_time = start_time + dt.timedelta(minutes=5)  # Adding 5 minutes to get the first candle

    response = api.get_time_price_series(exchange='NSE', token=token, 
                                         starttime=int(start_time.timestamp()), 
                                         endtime=int(end_time.timestamp()), interval='5')

    if response and response[0]['stat'] == 'Ok':
        # Get the opening price from the first candle
        opening_price = response[0]['open'] if 'open' in response[0] else None
        return float(opening_price) if opening_price is not None else None
    else:
        return None


# Utility Function to Fetch Candle Data

def get_candle_data_at_trigger_time(api, token, trigger_time_str):
    """
    Fetches candle data for a stock at a specified trigger time.

    :param api: API client instance for fetching candle data.
    :param token: Token of the stock to fetch data for.
    :param trigger_time_str: Trigger time as a string.
    :return: High and low prices of the candle at the trigger time.
    """
    # Get the current date
    current_date = dt.datetime.now().date()
    #current_date = dt.datetime.now().date() - dt.timedelta(days=1)

    # Convert the trigger time string to a datetime object
    trigger_time = dt.datetime.strptime(f"{current_date} {trigger_time_str}", "%Y-%m-%d %I:%M %p")

    # Align start time to the beginning of the 5-minute interval and subtract additional 5 minutes
    start_time = trigger_time - dt.timedelta(minutes=trigger_time.minute % 5 + 5, seconds=trigger_time.second)

    # End time is 5 minutes after start time
    end_time = start_time + dt.timedelta(minutes=5)

    # Fetch candle data from the API
    response = client.get_time_price_series(exchange='NSE', token=token, 
                                         starttime=int(start_time.timestamp()), 
                                         endtime=int(end_time.timestamp()), interval='5')

    # Process and return the candle data
    if response and response[0]['stat'] == 'Ok':
        last_candle = response[-1]
        return float(last_candle['inth']), float(last_candle['intl'])
    else:
        return None, None


# Trade Management Functions
    
# Function to monitor trades
def monitor_trades():
    """
    Continuously monitors and manages each trade based on current price.
    """
    print("Monitoring Trades")
    while True:
        for stock_symbol, trade_info in list(traded_stocks.items()):
            # Get the current price from the feed data
            stock_token = trade_info.get('token')
            current_price = feedJson.get(str(stock_token), {}).get('ltp')

            if current_price:
                # Manage the trade based on the current price
                manage_trade(client, stock_symbol, trade_info, current_price)

            # Sleep to prevent excessive resource use (modify as needed)
            time.sleep(1)


def manage_trade(api, stock_symbol, trade_info, current_price):
    entry_price = trade_info['entry_price']
    targets = trade_info['targets']
    stop_loss = trade_info['stop_loss']
    quantity = trade_info['quantity']
    buy_order_id = trade_info.get('buy_order_id')
    stop_loss_order_id = trade_info.get('stop_loss_order_id')
    '''
    if buy_order_id:
        buy_order_status = orderJson.get(buy_order_id, {}).get('status')
        if buy_order_status == 'REJECTED':
            print(f"Buy order for {stock_symbol} rejected. Exiting trade management.")
            return  # Exit the function if buy order is rejected
    '''
    if buy_order_id:
        buy_order_status = orderJson.get(buy_order_id, {}).get('status')
        if buy_order_status == 'REJECTED':
            print(f"Buy order for {stock_symbol} rejected. Removing from traded stocks.")
            if stock_symbol in traded_stocks:
                del traded_stocks[stock_symbol]  # Remove the rejected buy order from the dictionary
            return  # Exit the function if buy order is rejected
   


    # Check for order execution and place stop-loss order
    if buy_order_id and 'COMPLETE' == orderJson.get(buy_order_id, {}).get('status') and not stop_loss_order_id:
        stop_loss_order_id = place_stop_loss_order(api, trade_info)
        trade_info['stop_loss_order_id'] = stop_loss_order_id


   

    # Process targets
    for i, target in enumerate(targets):
        if current_price >= target and not trade_info['target_status'][i]:
            print(f"Target {i+1} hit for {stock_symbol}. Current price: {current_price}, Target: {target}")
            
            # For the first two targets, sell half the stocks each
            if i < 2:
                sell_quantity = quantity // 2
                remaining_quantity = quantity - sell_quantity
                place_sell_order(api, stock_symbol, sell_quantity)
                new_sl_price = entry_price if i == 0 else targets[0]
                
                modify_stop_loss_order(api, stock_symbol, new_sl_price, remaining_quantity, stop_loss_order_id, trade_info['tick_size'])

                trade_info['quantity'] = remaining_quantity

            # For subsequent targets, only update the SL
            else:
                new_sl_price = targets[i - 1]
                modify_stop_loss_order(api, stock_symbol, new_sl_price, trade_info['quantity'], stop_loss_order_id,trade_info['tick_size'])

            # Update the trade_info
            trade_info['target_status'][i] = True

    # Check if it's time to close the position (e.g., at 3:15 PM)
    '''        
    current_time = dt.datetime.now().time()
    if current_time >= dt.time(15, 15) and trade_info['quantity'] > 0:
        # Close any remaining position
        place_sell_order(api, stock_symbol, trade_info['quantity'])
        print(f"Closed remaining position of {stock_symbol} ")
    '''


# Function to place a stop loss order
def place_stop_loss_order(api, trade_info):
    """
    Place a stop-loss order for a given stock.

    :param api: ShoonyaApiPy client instance
    :param trade_info: Dictionary containing trade details like entry price, stop loss, quantity, etc.
    :return: Order ID of the placed stop-loss order
    """
    print("Placing SL order for", trade_info['stock_symbol'], "at SL price", trade_info['stop_loss'], "quantity:", trade_info['quantity'])
    try:
        stock_symbol = trade_info['stock_symbol']
        stop_loss_price = trade_info['stop_loss']
        quantity = trade_info['quantity']

        stop_loss_order_result = client.place_order(
            buy_or_sell='S',  # S for Sell
            product_type='I',  # Assuming 'I' for Intraday; change as needed
            exchange='NSE',  # Assuming NSE; change if necessary
            tradingsymbol=stock_symbol,
            quantity=quantity,
            discloseqty=0,
            price_type='SL-LMT',  # Stop-loss market order
            price=custom_round(round_to_tick_size(stop_loss_price * .99, trade_info["tick_size"])),  # Price is 0 for market orders
            trigger_price=stop_loss_price,  # Stop loss trigger price
            retention='DAY',  # Assuming DAY; change as needed
            remarks='Stop-loss Order'
        )

        print(f"Stop-loss order placed for {stock_symbol}: {stop_loss_order_result}")

        stop_loss_order_no = stop_loss_order_result.get('norenordno')
        print("Traded Stocks Info", traded_stocks)
        print("Stop Loss Order Id is", stop_loss_order_no)
        trade_info["stop_loss_order_id"]=stop_loss_order_no
        return stop_loss_order_no
    except Exception as e:
        print(f"Error placing stop-loss order for {stock_symbol}: {e}")
        return None

# Function to modify a stop loss order
def modify_stop_loss_order(api, stock_symbol, new_stop_loss, new_stop_loss_quantity, existing_order_id,tick_size):
    """
    Modifies the stop-loss order for a given stock.

    :param api: API client for placing/modifying orders
    :param stock_symbol: Symbol of the stock
    :param new_stop_loss: New stop-loss price
    :param new_stop_loss_quantity: Quantity for the new stop-loss order
    :param existing_order_id: The order ID of the existing stop-loss order
    """
    
    print("Modifying SL for Order Id", existing_order_id, "for", stock_symbol)    
    try:
        response = api.modify_order(
            orderno=existing_order_id,  # Adjusted parameter name
            exchange='NSE',
            tradingsymbol=stock_symbol,
            newquantity=new_stop_loss_quantity,
            newprice_type='SL-LMT',  # Assuming a market order for the stop-loss
            newprice= custom_round(round_to_tick_size(new_stop_loss * .99, tick_size)),  # Price is zero for a market order
            newtrigger_price=new_stop_loss  # New trigger price for the stop-loss
        )
        print("Modify Order Response is",response)
        print(f"Modified stop-loss order for {stock_symbol}. New SL: {new_stop_loss}, Quantity: {new_stop_loss_quantity}")
        return response
    except Exception as e:
        print(f"Error modifying stop-loss order for {stock_symbol}: {e}")
        return None
    

# Function to place a sell order
def place_sell_order(api, stock_symbol, quantity):
    """
    Places a sell order for a given stock.

    :param api: API client for placing orders
    :param stock_symbol: Symbol of the stock
    :param quantity: Quantity of shares to sell
    :param price: Selling price
    """
    print("Placing a sell order")
    try:
        response = client.place_order(
            buy_or_sell='S',  # S for sell
            product_type='I',  # Assuming Intraday trading
            exchange='NSE',  # Assuming NSE exchange
            tradingsymbol=stock_symbol,
            quantity=quantity,
            discloseqty=0,  # Assuming full quantity disclosure
            price_type='MKT',  # Assuming a market order
            price=0,  # Selling price
            trigger_price=0,  # No trigger price for limit order
            retention='DAY',  # Assuming order valid for the day
            remarks='Sell Order'
        )

        print(f"Placed market price sell order for {stock_symbol}. Quantity: {quantity}")
        return response
    except Exception as e:
        print(f"Error placing sell order for {stock_symbol}: {e}")




def buy_stock(stock_symbol, quantity, candle_high, candle_low, tick_size, stock_token, trigger_time):
    """
    Places a buy order for a stock based on the provided parameters.

    :param stock_symbol: Symbol of the stock to buy.
    :param quantity: Quantity of stocks to buy.
    :param candle_high: The high price of the current candle.
    :param candle_low: The low price of the current candle.
    :param tick_size: The minimum price movement of the stock.
    :param stock_token: Unique identifier for the stock.
    :param trigger_time: Time at which the trigger is activated.
    :return: None
    """
    try:
        # Calculate entry and stop-loss prices
        entryabove_price = custom_round(round_to_tick_size(candle_high * 1.001, tick_size))
        stop_loss_price = custom_round(round_to_tick_size((candle_high - ((candle_high - candle_low) * 0.5)) * 0.999, tick_size))
        entrypricelimit = custom_round(round_to_tick_size(entryabove_price * 1.004, tick_size))
        RPTQuantity = calculate_quantity(entryabove_price, stop_loss_price)

        # Risk amount per stock
        risk_per_stock = entryabove_price - stop_loss_price
        risk_per_stock = custom_round(round_to_tick_size(risk_per_stock*.75))

        print("Risk Per Stock",risk_per_stock)

        # Calculate target prices with progressive RR
        targets = []
        for i in range(10):
            rr_ratio = i + 1  # Risk-reward ratio (1:1, 1:2, 1:3, ...)
            target_price = custom_round(entryabove_price + (risk_per_stock * rr_ratio))
            targets.append(target_price)
        # Calculate target prices
        #targets = [custom_round(round_to_tick_size(entryabove_price + ((candle_high - candle_low) * (0.45 * i)), tick_size)) for i in range(15)]

        # Place the initial buy order using the client's API
       
        buy_order_result = client.place_order(
            buy_or_sell='B',
            product_type='I',  # Intraday trading
            exchange='NSE',
            tradingsymbol=stock_symbol,
            quantity=RPTQuantity,
            discloseqty=0,
            price_type='SL-LMT',  # Stop-Limit Market Order
            price=entrypricelimit,
            trigger_price=entryabove_price,
            retention='DAY',
            remarks='MIS Order'
        )


        # Handle the response from the order
        buy_order_id = buy_order_result.get('norenordno', None)
        print(f"MIS order placed for {stock_symbol}: {buy_order_result}")

        # Store the trade information in the dictionary
        traded_stocks[stock_symbol] = {
            'stock_symbol': stock_symbol,
            'entry_price': entryabove_price,
            'quantity': RPTQuantity,
            'targets': targets,
            'stop_loss': stop_loss_price,
            'target_status': [False] * 10,
            'token': stock_token,
            'buy_order_id': buy_order_id,
            'stop_loss_order_id': None,
            'tick_size': tick_size
        }

        print("Traded Stocks Info", traded_stocks)

        # Subscribe to the stock token for updates
        subscribetoken = "NSE|" + str(stock_token)
        print("Subscribing to token:", subscribetoken)
        response = client.subscribe(subscribetoken, feed_type='d')
        print("Subscription response:", response)

        # Log trade details to a file
        with open("trade_log.txt", "a") as file:
            file.write(f"{datetime.datetime.now()} - Trade for {stock_symbol}\n")
            file.write(f"Signal Time: {trigger_time}\n")
            file.write(f"Entry Level: {entryabove_price}\n")
            file.write(f"Stop Loss: {stop_loss_price}\n")
            for i, target in enumerate(targets):
                file.write(f"Target {i+1}: {target}\n")
            file.write(f"Quantity: {quantity}\n")
            file.write(f"Buy Order ID: {buy_order_id}\n")
            file.write("--------------------------------------------------\n")

    except Exception as e:
        print(f"Exception in buy_stock: {e}")



# Flask Routes and Application Logic

@app.route('/')
def index():
    """
    Index route for the Flask application.
    :return: Welcome message
    """
    return 'Welcome to Auto Trader using Shoonya API!'

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    file_path = 'NSE_EQ_symbols.txt'
    try:
        # Splitting stocks and trigger prices from the incoming JSON data
        stock_symbols = data['stocks'].split(',')
        trigger_prices = [float(price) for price in data['trigger_prices'].split(',')]
        trigger_time = data['triggered_at']

        for stock_symbol, trigger_price in zip(stock_symbols, trigger_prices):
            symbol_details = find_symbol_details(file_path, stock_symbol)
            if symbol_details:
                shoonya_symbol = symbol_details['TradingSymbol']
                if shoonya_symbol in traded_stocks:
                    print(f"Already traded {shoonya_symbol} today. Ignoring signal.")
                    continue

                tick_size = symbol_details['TickSize']
                token = symbol_details['Token']
                high, low = get_candle_data_at_trigger_time(client, token, trigger_time)
                
                if high is not None and low is not None:
                    traded_stocks[shoonya_symbol] = {'processed': True}
                    buy_stock(shoonya_symbol, 1, high, low, tick_size, token, trigger_time)
                else:
                    print(f"Could not fetch candle data for {shoonya_symbol}")
            else:
                print(f"Symbol details not found for {stock_symbol}")

    except KeyError as e:
        print(f"Missing data in the webhook: {e}")
        return f"Missing data: {e}", 400
    except Exception as e:
        print(f"Error processing the webhook: {e}")
        return f"Error: {e}", 500
    return 'Data Received and Processed', 200


# Start WebSocket Management and Trade Monitoring in separate threads
if __name__ == '__main__':
    threading.Thread(target=monitor_trades).start()
    threading.Thread(target=manage_websocket).start()
    app.debug = True
    app.run(host='0.0.0.0')

    #Good Luck

