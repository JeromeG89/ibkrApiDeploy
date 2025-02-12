from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
import threading
import time
import yfinance as yf

class IBKRClient(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.nextOrderId = None
        self.account_key = None
        self.portfolio = {}
        self.total_value = None  # Initialize total account value
        self.liquidity = None  # Initialize liquidity
        self.cash_balance = {} # Initialize Cash

        

    
    def managedAccounts(self, accountsList):
        """Callback for managed accounts."""
        # print(f"Managed accounts: {accountsList}")
        self.account_key = accountsList.split(",")[0]

    def nextValidId(self, orderId: int):
        """Callback when the next valid order ID is received."""
        # print(f"Next valid order ID: {orderId}")
        self.nextOrderId = orderId
        # print(f'Next Valid Order ID: {self.nextOrderId}')
        self.reqManagedAccts()  # Request managed accounts
        
    def updatePortfolio(self, contract, position, marketPrice, marketValue, averageCost, unrealizedPNL, realizedPNL, accountName):
        """Callback for portfolio updates."""
        # print(f"Portfolio Update - Symbol: {contract.symbol}, Position: {position}, Market Value: {marketValue}")
        if position != 0:
            self.portfolio[contract.symbol] = {
                "position": position,
                "marketPrice": marketPrice,
                "marketValue": marketValue,
                "averageCost": averageCost,
                "unrealizedPNL": unrealizedPNL,
                "realizedPNL": realizedPNL,
            }
            

    def accountSummary(self, reqId, account, tag, value, currency):
        """Callback for account summary updates."""
        # print(f"Account Summary - ReqId: {reqId}, Account: {account}, Tag: {tag}, Value: {value}, Currency: {currency}")
        if tag == "NetLiquidation":
            # print(f"Total Account Value (Net Liquidation): {value} {currency}")
            self.total_value = float(value)
        elif tag == "AvailableFunds":
            # print(f"Available Liquidity: {value} {currency}")
            self.liquidity = float(value)
    
    
    def updateAccountValue(self, key, val, currency, accountName):

        if key == 'CashBalance':
            self.cash_balance[currency] = float(val)
            # print(f'Cash Balance: {self.cash_balance} {currency}')
            
    def error(self, reqId, errorCode, errorString):
        """Callback for error messages."""
        print(f"Error {errorCode}: {errorString}")

    def connectionClosed(self):
        """Callback when the connection to IBKR is closed."""
        print("Connection to IBKR closed.")





def fetch_account_summary(client):
    """Request account summary and wait for the response."""
    # print("Requesting account summary...")
    client.total_value = None  # Reset before fetching
    client.liquidity = None

    client.reqAccountSummary(1, "All", "NetLiquidation,AvailableFunds,CashBalance")
    # print("reqAccountSummary sent for NetLiquidation, AvailableFunds and CashBalance")

    # Wait for the values to update
    for _ in range(10):
        if client.total_value is not None and client.liquidity is not None:
            print(f"Fetched Total Value: {client.total_value}, Liquidity: {client.liquidity}")
            return client.total_value, client.liquidity
        time.sleep(1)

    print(f"Failed to fetch account summary within the timeout period., {client.total_value}, {client.liquidity}, {client.cash_balance}")
    return None, None, None


def fetch_portfolio(client):
    """Request portfolio updates and wait for the response."""
    if client.account_key:
        print(f"Requesting account updates for account: {client.account_key}")
        client.reqAccountUpdates(True, client.account_key)
        time.sleep(2)  # Wait for portfolio updates
        client.reqAccountUpdates(False, client.account_key)
        return client.portfolio, client.cash_balance
    
    else:
        print("Account key not available. Unable to fetch portfolio.")
        return {}, None



def portfolio_distribution(client):
    full_value, liquidity = fetch_account_summary(client)

    portfolio, cash = fetch_portfolio(client)

    usd_total_value = sum(val['marketValue'] for val in portfolio.values()) + cash['USD']

    distribution = {key:val['marketValue'] / usd_total_value for key, val in portfolio.items()} 
    distribution['Cash'] = cash['USD'] / usd_total_value
    return distribution, usd_total_value


def request_stock_prices(tickers):
    return {tick : yf.Ticker(tick).info['currentPrice'] for tick in tickers}


def get_difference(client, weights, tickers):
    cur_portfolio, total_value = portfolio_distribution(client)
    desired_portfolio = {tickers[i]: weights[i] for i in range(len(tickers))}

    stock_prices = request_stock_prices(tickers)
    to_change = {tick: (desired_portfolio[tick] - cur_portfolio.get(tick, 0)) * total_value // stock_prices[tick] for tick in desired_portfolio}
    return to_change


def create_stock_contract(symbol, exchange="SMART", currency="USD"):
    """Create a Stock Contract."""
    contract = Contract()
    contract.symbol = symbol
    contract.secType = "STK"
    contract.exchange = exchange
    contract.currency = currency
    return contract

def create_market_order(action, quantity): #### Jerome's Note, possible to change to LMT order and based off current prices from yfinance
    """Create a Market Order."""
    order = Order()
    order.action = action  # "BUY" or "SELL"
    order.orderType = "MKT"  # Market Order
    order.totalQuantity = abs(quantity)  # Use absolute value for quantity
    order.tif = "DAY"  # Time-in-force: Valid for the day
    order.eTradeOnly = False
    order.firmQuoteOnly = False
    return order

def place_orders(client, stock_data):
    """Place buy and sell orders based on the stock data."""
    for symbol, value in stock_data.items():
        if value == 0:  # Skip if no action is required
            continue

        action = "BUY" if value > 0 else "SELL"
        quantity = abs(int(value))  # Ensure quantity is positive

        print(f"Placing {action} order for {quantity} shares of {symbol}...")

        # Create contract and order
        contract = create_stock_contract(symbol)
        order = create_market_order(action, quantity)

        # Place the order
        client.placeOrder(client.nextOrderId, contract, order)
        client.nextOrderId += 1  # Increment order ID

        time.sleep(1)  # Small delay between orders to avoid API overload
        
        
def buy(weights, tickers):
    client = IBKRClient()
    client.connect("127.0.0.1", 4001, clientId=1)  # Use the correct port and unique clientId

    api_thread = threading.Thread(target=client.run, daemon=True)
    api_thread.start()

    try:
        time.sleep(2) #Let connection stablise

        orders = get_difference(client, weights, tickers)
        print(orders)
        place_orders(client, orders)


    finally:
        client.disconnect()
        api_thread.join()

if __name__ == "__main__":
    buy(weights = [1.12924305e-01 ,3.69146895e-14 ,6.26083476e-14 ,6.79025480e-14,0.00000000e+00 ,0.00000000e+00 ,1.58486544e-01 ,3.55500901e-02,3.81148954e-14 ,0.00000000e+00 ,0.00000000e+00 ,3.99374318e-14,0.00000000e+00 ,0.00000000e+00 ,0.00000000e+00 ,1.00844844e-14,0.00000000e+00 ,0.00000000e+00 ,8.33154523e-02 ,0.00000000e+00,5.18840758e-15 ,2.07607845e-01 ,0.00000000e+00 ,6.84419764e-14,3.87840490e-14 ,1.30361348e-14 ,3.50368669e-14 ,0.00000000e+00,0.00000000e+00 ,1.71525960e-01 ,6.99914883e-14 ,2.26404807e-14,1.03922055e-14 ,1.63324539e-14 ,8.10892743e-14 ,0.00000000e+00,0.00000000e+00 ,3.64595253e-14 ,0.00000000e+00 ,1.61263467e-01,8.72187004e-14 ,7.38494204e-14 ,2.48209276e-14 ,6.93263371e-02,0.00000000e+00 ,0.00000000e+00 ,0.00000000e+00 ,4.63990418e-15,0.00000000e+00 ,0.00000000e+00], 
        tickers = ['AAPL', 'ABBV', 'ACN', 'ADBE', 'AMD', 'AMT', 'AMZN', 'AVGO', 'BAC', 'BLK', 'BRK-B', 'COST', 'CSCO', 'CVX', 'GOOGL', 'HD', 'INTC', 'JNJ', 'JPM', 'KO', 'LIN', 'LLY', 'LOW', 'MA', 'META', 'MRK', 'MS', 'MSFT', 'NEE', 'NFLX', 'NKE', 'NVDA', 'ORCL', 'PEP', 'PFE', 'PG', 'PM', 'QCOM', 'RTX', 'SCHW', 'SPGI', 'T', 'TMO', 'TSLA', 'TXN', 'UNH', 'UPS', 'V', 'WMT', 'XOM']
)




