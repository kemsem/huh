import json
import logging
import os
import re

import requests
from flask import Flask, Response, request
from kik import Configuration, KikApi
from kik.messages import (LinkMessage, SuggestedResponseKeyboard, TextMessage,
                          TextResponse, messages_from_json)
from yahoo_finance import Share

BOT_USERNAME = os.environ.get('BOT_USERNAME', '')
BOT_API_KEY = os.environ.get('BOT_API_KEY', '')
BOT_WEBHOOK = os.environ.get('BOT_WEBHOOK', '')

kik = KikApi(BOT_USERNAME, BOT_API_KEY)
kik.set_configuration(Configuration(webhook=BOT_WEBHOOK))

app = Flask(__name__)

DEBUG = True


def lookup(ticker):
    """Look up ticker information.

    Return
    {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "exch": "NAS",
        "type": "S",
        "exchDisp": "NASDAQ",
        "typeDisp": "Equity"
    } or None.
    """
    url = (
        'http://d.yimg.com/aq/autoc?query={}&region=US&lang=en-US'
        '&callback=YAHOO.util.ScriptNodeDataSource.callbacks'
    ).format(ticker)
    res = requests.get(url)
    lookups = res.text.replace('YAHOO.util.ScriptNodeDataSource.callbacks(', '').replace(');', '')
    try:
        return json.loads(lookups)['ResultSet']['Result']
    except:
        return None


def send_text(user, chat_id, body, keyboards=[]):
    """Send text."""
    message = TextMessage(to=user, chat_id=chat_id, body=body)
    if keyboards:
        message.keyboards.append(
            SuggestedResponseKeyboard(
                to=user,
                hidden=True,
                responses=[TextResponse(keyboard) for keyboard in keyboards],
            )
        )
    kik.send_messages([message])


def send_link(user, chat_id, url=None, title=None, text=None, pic_url=None):
    """Send link."""
    kik.send_messages([LinkMessage(
        to=user,
        chat_id=chat_id,
        url=url,
        title=title,
        pic_url=pic_url,
    )])


@app.route('/', methods=['GET'])
def hello():
    """Hello world."""
    return 'Hello world'


@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook."""
    if not kik.verify_signature(request.headers.get('X-Kik-Signature'), request.get_data()):
        return Response(status=403)

    messages = messages_from_json(request.json['messages'])

    for message in messages:
        if isinstance(message, TextMessage):
            logging.info(message)

            if '$' in message.body:
                send_text(message.from_user, message.chat_id, 'Looking up...')
                for symbol in re.findall(r'\$\w(?:\w)*(?:\.\w+)?', message.body):
                    ticker = symbol[1:]
                    yahoo = Share(ticker)
                    if yahoo.get_price():
                        text = 'Price of ${} is {}'.format(ticker, yahoo.get_price())
                        send_text(message.from_user, message.chat_id, text)
                        send_link(
                            message.from_user,
                            message.chat_id,
                            url='http://finance.yahoo.com/q?s={}'.format(ticker),
                            title='Yahoo finace: ${}'.format(ticker),
                            pic_url='http://chart.finance.yahoo.com/z?s={}'.format(ticker),
                        )
                    else:
                        text = 'We couldn\'t find a ticker with ${}.'.format(ticker)
                        send_text(message.from_user, message.chat_id, text)

                        keyboards = ['$' + t['symbol'] for t in lookup(ticker)][:4]
                        if keyboards:
                            text = 'Are you looking for...'
                            send_text(message.from_user, message.chat_id, text, keyboards)
                        else:
                            text = 'What are you looking for?'
                            send_text(message.from_user, message.chat_id, text)

            elif 'lookup' in message.body.lower():
                lookup_text = re.findall(r'lookup (\w+)', message.body.lower())
                if lookup_text:
                    text = 'Are you looking for...'
                    keyboards = ['$' + t['symbol'] for t in lookup(lookup_text[0])][:8]
                    send_text(message.from_user, message.chat_id, text, keyboards)
                else:
                    text = 'What are you looking for?'
                    send_text(message.from_user, message.chat_id, text)
            else:
                text = 'Hi {}! For live stock quotes type "$" followed by a ticker symbol.'.format(message.from_user)
                text = 'Hi! For live stock quotes type "$" followed by a ticker symbol or "lookup" followed by a company name.'  # noqa
                send_text(message.from_user, message.chat_id, text)
                text = 'For example, if you want to look up Apple, type "$AAPL" or "lookup Apple".'
                send_text(message.from_user, message.chat_id, text)
                text = 'Try it now:'
                send_text(message.from_user, message.chat_id, text, ["Lookup Apple"])

    return Response(status=200)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=DEBUG)
