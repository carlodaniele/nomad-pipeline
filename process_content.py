import os
from google import genai
import requests

# Configurazione Secrets
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WP_URL = os.getenv("WP_URL")
WP_USER = "carlo" # Inserisci qui il tuo username WP
WP_PASS = os.getenv("WP_APP_PASSWORD")

# Inizializzazione Client Gemini (Nuova sintassi 2026)
client = genai.Client(api_key=GEMINI_API_KEY)

def generate_post_content(raw_text):
    # Usiamo il modello aggiornato
    prompt = f"Transform this raw travel notes into a professional, engaging English blog post for a tech-nomad audience. Include a title: {raw_text}"
    response = client.models.generate_content(
        model="gemini-2.0-flash", # Aggiornato al modello corrente
        contents=prompt
    )
    return response.text

def publish_to_wordpress(title, content):
    endpoint = f"{WP_URL}/wp/v2/posts"
    auth = (WP_USER, WP_PASS)
    post_data = {
        "title": title,
        "content": content,
        "status": "draft"
    }
    response = requests.post(endpoint, json=post_data, auth=auth)
    return response.status_code

if __name__ == "__main__":
    test_text = "Today at Verucchio, working on my new office. Feeling free."
    blog_content = generate_post_content(test_text)
    print("Content Generated!")
    
    status = publish_to_wordpress("Nomad Diary #1", blog_content)
    if status == 201:
        print("Success! Draft created in WordPress.")
    else:
        print(f"Error: {status}")
