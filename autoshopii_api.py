
from flask import Flask, request, jsonify
import sys
import os

# Ensure working directory and system path
sys.path.insert(0, os.path.dirname("/mnt/data/autoshopii.py"))

app = Flask(__name__)

@app.route('/check', methods=['GET'])
def check():
    cc = request.args.get('cc')
    proxy = request.args.get('proxy')  # Optional proxy
    site = request.args.get('site')

    if not cc or len(cc.split('|')) != 4:
        return jsonify({'error': 'Missing or invalid cc format. Expected format: cc|mm|yy|cvv'}), 400

    os.environ['CARD_INPUT'] = cc
    os.environ['SITE_INPUT'] = site or ''
    os.environ['PROXY_INPUT'] = proxy or ''

    try:
        import autoshopii
        result = autoshopii.run_main_logic()  # Replace with the main callable in your script
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
