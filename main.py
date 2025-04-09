from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import requests
import sys
# import google.generativeai as genai
from firebase import firebase
import os
from dotenv import load_dotenv
import datetime

# Load environment variables
load_dotenv()

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
FIREBASE_URL = os.environ.get('FIREBASE_URL')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
# genai.configure(api_key = GEMINI_API_KEY)
# model = genai.GenerativeModel('gemini-pro')

GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"

# 接收 LINE Webhook 的入口
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        print("sign:",signature)
        print(body)
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'


# 處理收到的訊息事件
#  """Event - User sent message

#  Args:
#      event (LINE Event Object): Refer to https://developers.line.biz/en/reference/messaging-api/#message-event
#  """
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    msg_type = event.message.type
    reply_token = event.reply_token
    user_chat_path =  f'chat/{user_id}'
    user_message = event.message.text
    fdb = firebase.FirebaseApplication(FIREBASE_URL, None)
    timestamp = datetime.datetime.utcnow().isoformat()

    # user_chat_history:list = fdb.get(user_chat_path, None)
    gemini_reply = get_gemini_reply(user_message)

    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(text=gemini_reply)
    )
    try:
      fdb.put(user_chat_path, timestamp, {"from": "user", "msg": user_message})
      fdb.put(user_chat_path, timestamp + "_bot", {"from": "bot", "msg": gemini_reply})
    except Exception as e:
        print(f"Firebase error: {e}")


# 呼叫 Gemini API 並回傳回應文字
def get_gemini_reply(prompt):
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    try:
        response = requests.post(GEMINI_API_URL, headers=headers, json=data)
        res_json = response.json()
        return res_json.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "無回應")
    except Exception as e:
        print(f"Gemini API error: {e}")
        return "抱歉，我無法理解這個問題。"

# if __name__ == "__main__":
    # app.run()
    #  app.run(host='0.0.0.0', port=10000)
