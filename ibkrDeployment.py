from flask import Flask, request, jsonify
from ibkr_integration import IBKRClient, get_difference, place_orders  # Import from your script

app = Flask(__name__)

@app.route('/buy', methods=['POST'])
def buy():
    data = request.json
    weights = data['weights']
    tickers = data['tickers']

    client = IBKRClient()
    client.connect("127.0.0.1", 4001, clientId=1)

    api_thread = threading.Thread(target=client.run, daemon=True)
    api_thread.start()

    try:
        time.sleep(2)  # Let connection stabilize
        orders = get_difference(client, weights, tickers)
        place_orders(client, orders)
        return jsonify({"status": "success", "orders": orders}), 200
    finally:
        client.disconnect()
        api_thread.join()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
