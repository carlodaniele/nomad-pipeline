import os
import glob
from google import genai
import requests
import shutil

# Configurazione Secrets
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WP_URL = os.getenv("WP_URL")
WP_USER = "carlo" 
WP_PASS = os.getenv("WP_APP_PASSWORD")

client = genai.Client(api_key=GEMINI_API_KEY)

def generate_post_content(raw_text):
    prompt = f"Transform these raw travel notes into a professional, engaging English blog post for a tech-nomad audience. Separate the Title and the Body. Notes: {raw_text}"
    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents=prompt
    )
    return response.text

def publish_to_wordpress(title, content):
    base_url = WP_URL.strip().rstrip('/')
    endpoint = f"{base_url}/index.php?rest_route=/wp/v2/posts"
    
    auth = (WP_USER, WP_PASS)
    post_data = {
        "title": title,
        "content": content,
        "status": "draft"
    }
    
    try:
        response = requests.post(endpoint, json=post_data, auth=auth)
        return response.status_code
    except Exception as e:
        print(f"Errore: {e}")
        return None

if __name__ == "__main__":
    # Assicuriamoci che la cartella archivio esista
    archive_dir = "processed"
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)

    # 1. Cerca file .txt nella cartella uploads
    files = glob.glob("uploads/*.txt")
    
    if not files:
        print("Nessun nuovo file da processare nella cartella uploads/")
    else:
        for file_path in files:
            print(f"Processando: {file_path}")
            
            with open(file_path, "r", encoding="utf-8") as f:
                raw_notes = f.read()
            
            # 2. Genera contenuto con Gemini
            blog_content = generate_post_content(raw_notes)
            print("Content Generated!")
            
            # 3. Pubblica
            filename = os.path.basename(file_path)
            title_clean = filename.replace(".txt", "").replace("-", " ").title()
            status = publish_to_wordpress(f"Nomad Post: {title_clean}", blog_content)
            
            if status in [200, 201]:
                print(f"Successo per {file_path}!")
                # 4. Sposta il file nella cartella processed
                shutil.move(file_path, os.path.join(archive_dir, filename))
                print(f"File archiviato in {archive_dir}/")
            else:
                print(f"Errore nella pubblicazione di {file_path}: {status}")
