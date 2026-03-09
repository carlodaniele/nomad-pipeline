import os
import google.generativeai as genai
import requests

# 1. Configurazione API (Secrets di GitHub)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WP_URL = os.getenv("WP_URL")
WP_USER = "carlo" # Sostituisci con il tuo username WP
WP_PASS = os.getenv("WP_APP_PASSWORD")

genai.configure(api_key=GEMINI_API_KEY)

def generate_post_content(raw_text):
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"Transform this raw travel notes into a professional, engaging English blog post for a tech-nomad audience. Include a title: {raw_text}"
    response = model.generate_content(prompt)
    return response.text

def publish_to_wordpress(title, content):
    endpoint = f"{WP_URL}/wp/v2/posts"
    # Basic Auth in Base64 per le REST API
    auth = (WP_USER, WP_PASS)
    
    post_data = {
        "title": title,
        "content": content,
        "status": "draft" # Lo pubblichiamo come bozza per sicurezza
    }
    
    response = requests.post(endpoint, json=post_data, auth=auth)
    return response.status_code

# Logica di esecuzione semplificata per il test
if __name__ == "__main__":
    # Per ora simuliamo un input. Poi lo renderemo automatico per i file in /uploads
    test_text = "Today at Verucchio, working on my new office. Feeling free."
    blog_content = generate_post_content(test_text)
    print("Content Generated!")
    
    status = publish_to_wordpress("Nomad Diary #1", blog_content)
    if status == 201:
        print("Success! Draft created in WordPress.")
    else:
        print(f"Error: {status}")
