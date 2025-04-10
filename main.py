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
MODEL = os.environ.get("MODEL")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
client = genai.Client(api_key=GEMINI_API_KEY)
fdb = firebase.FirebaseApplication(FIREBASE_URL, None)


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
    if not isinstance(event.message, TextMessage):
        return
    
    user_id = event.source.user_id
    reply_token = event.reply_token
    mention = getattr(event.message, 'mention', None)

    # reply only when mentioned
    if mention and mention.mentionees:
        mentionees = event.message.mention.mentionees
        bot_id = line_bot_api.get_bot_info().user_id
        # print("bot_id:",bot_id)
        is_bot_mentioned = any(m.user_id == bot_id for m in mentionees)
        # print("is_bot_mentioned:",is_bot_mentioned)

        if not is_bot_mentioned:
            return 
        
        user_chat_path =  f'chat/{user_id}'
        today = datetime.datetime.utcnow().strftime("%Y%m%d")
        get_user_today_msg = fdb.get(user_chat_path, today)
        # print('get_user_today_msg: ', get_user_today_msg)

        # clear history message
        delete_previous_history(user_chat_path, user_id)

        user_message = event.message.text
        if not get_user_today_msg:
            messages = []
        else:
            messages = get_user_today_msg
            

        if user_message == 'clear':
            reply_msg = f"userId:{user_id} 今日對話紀錄清空"
            try:
                fdb.delete(user_chat_path, today)
                print(f"✅ 已刪除 {user_id} 的今日聊天紀錄")
            except Exception as e:
                print(f"刪除失敗：{e}")
                

        else:
            messages.append({'role':'user','parts': [{'text':user_message}]})
            reply_msg = get_gemini_reply(messages)
            messages.append({'role':'model','parts': [{'text':reply_msg}]})
            try:
                fdb.put(user_chat_path, today, messages)
            except Exception as e:
                print(f"Firebase error: {e}")
            
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=reply_msg)
        )

def delete_previous_history(user_chat_path, user_id):
    yesterday = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).date()
    msg_record = fdb.get('/chat', user_id)
    if not msg_record:
        return 
    
    history_dates = list(msg_record.keys())
    for date_str in history_dates:
        date = datetime.datetime.strptime(date_str,"%Y%m%d").date()
        if date < yesterday:
            fdb.delete(user_chat_path, date_str)
            print(f"delete_previous_history: ✅ 已刪除 {date_str} 的聊天紀錄")



def get_gemini_reply(messages):
  # prompt_format = f"user question: {prompt}, pls answers it in simple way. not more than 150 words each time. because we are using Line(one of the chat application)."
  try:
    response = client.models.generate_content(
        model=MODEL,
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
