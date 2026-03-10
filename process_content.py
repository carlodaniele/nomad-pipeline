import os
import glob
import shutil
from google import genai
import requests

# Configurazione Secrets
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WP_URL = os.getenv("WP_URL")
WP_USER = "carlo" 
WP_PASS = os.getenv("WP_APP_PASSWORD")

client = genai.Client(api_key=GEMINI_API_KEY)

def generate_post_content(raw_text):
    # Uso dei segnaposto per non far sparire i tag nella chat
    # I commenti HTML servono a WordPress per creare i blocchi Gutenberg
    prompt = f"""
    Transform these notes into a professional blog post for tech nomads.
    STRUCTURE:
    1. Start with [TITLE] then a creative title.
    2. Then use [BODY] for the content.
    3. The body MUST use WordPress Gutenberg block markers.
    
    IMPORTANT: You must wrap every element exactly like this:
    - Paragraphs: <!-- wp:paragraph --><p>text</p><!-- /wp:paragraph -->
    - Headings: <!-- wp:heading --><h2 class="wp-block-heading">text</h2><!-- /wp:heading -->
    Notes: {raw_text}
    """
    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents=prompt
    )
    return response.text

def parse_gemini_output(output):
    title = "Nomad Journey"
    body = output
    if "[TITLE]" in output and "[BODY]" in output:
        try:
            parts = output.split("[BODY]")
            title = parts[0].replace("[TITLE]", "").strip()
            body = parts[1].strip()
        except:
            pass
    return title, body

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
    # Assicuriamoci che entrambe le cartelle esistano
    upload_dir = "uploads"
    archive_dir = "processed"
    
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
        # Creiamo un file temporaneo per assicurarci che Git la veda
        with open(os.path.join(upload_dir, ".gitkeep"), "w") as f:
            f.write("")

    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)

    files = glob.glob("uploads/*.txt")
    if not files:
        print("Nessun file trovato.")
    else:
        for file_path in files:
            print(f"In lavorazione: {file_path}")
            with open(file_path, "r", encoding="utf-8") as f:
                raw_notes = f.read()
            
            raw_output = generate_post_content(raw_notes)
            title, blog_content = parse_gemini_output(raw_output)
            
            status = publish_to_wordpress(title, blog_content)
            if status in [200, 201]:
                print(f"Successo! Titolo: {title}")
                shutil.move(file_path, os.path.join(archive_dir, os.path.basename(file_path)))
            else:
                print(f"Errore WP: {status}")
