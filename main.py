from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from google import genai
from google.genai import types
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


GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
client = genai.Client(api_key=GEMINI_API_KEY)
chat = client.chats.create(model="gemini-2.0-flash")


@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)

    print("== LINE Webhook Hit ==")
    # print("Signature:", signature)
    # print("Body:", body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("❌ Invalid Signature - maybe your LINE_CHANNEL_SECRET is wrong")
        abort(400)
    except Exception as e:
        print("❌ Unknown Error:", e)
        abort(403)

    return 'OK'



#  """Event - User sent message

#  Args:
#      event (LINE Event Object): Refer to https://developers.line.biz/en/reference/messaging-api/#message-event
#  """
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    reply_token = event.reply_token
    user_chat_path =  f'chat/{user_id}'
    user_message = event.message.text
    fdb = firebase.FirebaseApplication(FIREBASE_URL, None)
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    get_user_history_msg = fdb.get('/chat', user_id)
    print('get_user_history_msg: ',get_user_history_msg)

    #TODO: 超過24hrs的使用者紀錄刪除
    
    if isinstance(event.message, TextMessage):
        user_message = event.message.text
        if not get_user_history_msg:
            messages = []
        else:
            messages = get_user_history_msg


        if user_message == 'clear':
            reply_msg = f"userId:{user_id} 對話紀錄清空"
            try:
              fdb.delete('/chat', user_id)
              print(f"✅ 已刪除 {user_id} 的所有聊天紀錄")
            except Exception as e:
              print(f"刪除失敗：{e}")
                

        else:
            messages.append({'role':'user','parts': [{'text':user_message}]})
            reply_msg = get_gemini_reply(messages)
            messages.append({'role':'model','parts': [{'text':reply_msg}]})
            try:
              fdb.put('/chat', user_id, messages)
              # fdb.put(user_chat_path, timestamp, messages)
            except Exception as e:
                print(f"Firebase error: {e}")
            
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=reply_msg)
        )



# 呼叫 Gemini API 並回傳回應文字
def get_gemini_reply(messages):
  # prompt_format = f"user question: {prompt}, pls answers it in simple way. not more than 150 words each time. because we are using Line(one of the chat application)."
  try:
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(
            system_instruction="""
            You are a RPA assistant. We have a learning group will ask or discuss relevant topics. 
            Making each answer less than 150 words, let everyone understand easier.
            You may need to base on history record to answer.
            """
            ),
        contents=messages
    )

    print(response.text)
    return response.text
  except Exception as e:
      print(f"Gemini API error: {e}")
      return "抱歉，我無法理解這個問題。"


# if __name__ == "__main__":
    # app.run()
    #  app.run(host='0.0.0.0', port=10000)
