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
        model="gemini-flash-latest", # Aggiornato al modello corrente
        contents=prompt
    )
    return response.text

def publish_to_wordpress(title, content):
    # Pulisce l'URL da spazi o slash finali e assicura il percorso corretto
    base_url = WP_URL.strip().rstrip('/')
    endpoint = f"{base_url}/index.php?rest_route=/wp/v2/posts"
    
    # Questo formato (index.php?rest_route=) funziona ANCHE se i permalink 
    # sono impostati su "Semplice", è la versione più compatibile in assoluto.
    
    print(f"Tentativo di pubblicazione su: {endpoint}")
    
    auth = (WP_USER, WP_PASS)
    post_data = {
        "title": title,
        "content": content,
        "status": "draft"
    }

if __name__ == "__main__":
    test_text = "Today at Verucchio, working on my new office. Feeling free."
    blog_content = generate_post_content(test_text)
    print("Content Generated!")
    
    status = publish_to_wordpress("Nomad Diary #1", blog_content)
    if status in [200, 201]:
        print(f"Success! Status code: {status}. Check your WordPress drafts.")
    else:
        print(f"Something went wrong. Status code: {status}")
