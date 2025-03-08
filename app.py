from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Gather
import logging
import traceback
import ollama
import pandas as pd

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# In-memory session store (per CallSid for tracking conversation memory)
session_data = {}

# Loading knowledge base 
def load_books():
    try:
        df = pd.read_csv('books.csv')
        logger.debug(f"Successfully loaded {len(df)} books")
        return df
    except Exception as e:
        logger.error(f"Error loading books: {str(e)}")
        logger.error(traceback.format_exc())
        return pd.DataFrame()

# Query LLaMA with Ollama
def query_llama(user_query, books, session_memory):
    book_list = "\n".join([
    f"{row['book_name']} by {row['author']} ({row['genre']}) - ${row['price']}, "
    f"{row['quantity_available']} in stock, Rating: {row['rating']}/5, Format: {row['format']}, "
    f"Language: {row['language']}, Pages: {row['pages']}, Discount: {row['discount']}%, "
    f"{'Bestseller' if row['bestseller'] == 'Yes' else 'Regular'}"
    for _, row in books.iterrows()
])

    memory_context = "\n".join(session_memory) if session_memory else "This is the start of the conversation."

    prompt = f"""
    You are a friendly AI bookstore assistant. Your job is to provide quick and helpful answers about book availability, pricing, and stock.

    Conversation history so far:
    {memory_context}

    Here is the current book inventory:
    {book_list}

    The user asked: "{user_query}"

    Respond in a natural, conversational manner. Keep your answer concise, engaging, and helpful. Avoid repeating the user's question—just provide the relevant information clearly and warmly.
    """

    try:
        response = ollama.chat(model="llama3.1", messages=[{"role": "user", "content": prompt}])
        return response['message']['content']
    except Exception as e:
        logger.error(f"Error querying LLaMA 3.1: {str(e)}")
        return "I'm sorry, but I couldn't retrieve that information right now."

@app.route("/", methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        return start_conversation()
    return "Book Store Voice Assistant is running!"

@app.route("/voice", methods=['POST'])
def voice():
    return start_conversation()

def start_conversation():
    try:
        call_sid = request.values.get('CallSid', 'unknown')
        session_data[call_sid] = []  

        logger.debug(f"Starting conversation for CallSid: {call_sid}")

        resp = VoiceResponse()
        gather = Gather(
            input='speech',
            action='/handle-input',
            method='POST',
            speechTimeout='auto',
            enhanced=True,
            bargeIn=True
        )
        gather.say("Hello! I'm your bookstore assistant. How can I help you today?")
        resp.append(gather)

        return str(resp)

    except Exception as e:
        logger.error(f"Error starting conversation: {str(e)}")
        logger.error(traceback.format_exc())
        return error_response()

@app.route("/handle-input", methods=['POST'])
def handle_input():
    try:
        call_sid = request.values.get('CallSid', 'unknown')
        user_input = request.values.get('SpeechResult', '').strip().lower()

        logger.debug(f"Handling input for CallSid: {call_sid}")
        logger.debug(f"User said: {user_input}")

        books = load_books()
        session_memory = session_data.get(call_sid, [])

        resp = VoiceResponse()

        # Farewell detection: Check if the user is ending the conversation
        farewell_phrases = ["thank you", "thanks", "that's all", "goodbye", "bye", "no more questions"]
        if any(phrase in user_input for phrase in farewell_phrases):
            resp.say("You're very welcome! Have a great day.")
            return str(resp)  

        # Query LLaMA with memory
        response_text = query_llama(user_input, books, session_memory)

        # Update memory
        session_memory.append(f"User: {user_input}")
        session_memory.append(f"Assistant: {response_text}")

        # Respond to user
        gather = Gather(
            input='speech',
            action='/handle-input',
            method='POST',
            speechTimeout='auto',
            enhanced=True,
            bargeIn=True
        )
        gather.say(response_text)

        # Remove unnecessary follow-up prompt
        resp.append(gather)

        return str(resp)

    except Exception as e:
        logger.error(f"Error in handle-input: {str(e)}")
        logger.error(traceback.format_exc())
        return error_response()

def error_response():
    resp = VoiceResponse()
    resp.say("We're sorry, but there was an error. Please try again later.")
    return str(resp)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
