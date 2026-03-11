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

def upload_media(file_path):
    """Carica l'immagine su WP e restituisce ID e URL"""
    endpoint = f"{WP_URL}/index.php?rest_route=/wp/v2/media"
    auth = (WP_USER, WP_PASS)
    filename = os.path.basename(file_path)
    
    content_type = 'image/jpeg'
    if filename.lower().endswith('.png'):
        content_type = 'image/png'

    headers = {
        'Content-Disposition': f'attachment; filename={filename}',
        'Content-Type': content_type,
    }
    
    try:
        with open(file_path, 'rb') as img:
            response = requests.post(endpoint, data=img, headers=headers, auth=auth)
        if response.status_code in [200, 201]:
            data = response.json()
            return data['id'], data['source_url']
        else:
            print(f"Errore caricamento media: {response.status_code}")
            return None, None
    except Exception as e:
        print(f"Errore upload_media: {e}")
        return None, None

def generate_post_content(raw_text, has_image=False):
    img_instruction = ""
    if has_image:
        img_instruction = """
        4. Since an image is available, include it ONCE at the beginning of the body using this exact syntax:
        <!-- wp:image {"id":[IMAGE_ID],"sizeSlug":"large","linkDestination":"none"} --><figure class="wp-block-image size-large"><img src="[IMAGE_URL]" alt="Nomad Journey Image" class="wp-image-[IMAGE_ID] /></figure><!-- /wp:image -->
        """
    # Uso dei segnaposto per non far sparire i tag nella chat
    # I commenti HTML servono a WordPress per creare i blocchi Gutenberg
    prompt = f"""
    Transform these notes into a professional blog post for tech nomads.
    STRUCTURE:
    1. Start with [TITLE] then a creative title.
    2. Then use [BODY] for the content.
    3. The body MUST use WordPress Gutenberg block markers.
    {img_instruction}
    
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
    if media_id:
        post_data["featured_media"] = media_id
        
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

    # 1. Cerca Immagini
    image_extensions = ('*.jpg', '*.jpeg', '*.png', '*.webp')
    image_files = []
    for ext in image_extensions:
        image_files.extend(glob.glob(os.path.join(upload_dir, ext)))
    
    media_id = None
    image_url = ""
    if image_files:
        print(f"Trovata immagine: {image_files[0]}")
        media_id, image_url = upload_media(image_files[0])

    # 2. Cerca Testi
    text_files = glob.glob(os.path.join(upload_dir, "*.txt"))
    if not text_files:
        print("Nessun file di testo trovato.")
    else:
        for file_path in text_files:
            print(f"In lavorazione: {file_path}")
            with open(file_path, "r", encoding="utf-8") as f:
                raw_notes = f.read()
            
            # Generazione contenuto (passiamo l'info se c'è un'immagine)
            raw_output = generate_post_content(raw_notes, has_image=bool(media_id))
            title, blog_content = parse_gemini_output(raw_output)
            
            # Sostituzione URL immagine nel corpo se necessario
            if image_url and media_id:
            blog_content = blog_content.replace("[IMAGE_URL]", image_url)
            blog_content = blog_content.replace("[IMAGE_ID]", str(media_id)) # <--- RIGA NUOVA
        
        # E QUI PASSIAMO IL MEDIA_ID AL MOMENTO DEL POST
        status = publish_to_wordpress(title, blog_content, media_id)
            
            if status in [200, 201]:
                print(f"Successo! Post creato: {title}")
                # Sposta i file processati
                shutil.move(file_path, os.path.join(archive_dir, os.path.basename(file_path)))
                for img in image_files:
                    try:
                        shutil.move(img, os.path.join(archive_dir, os.path.basename(img)))
                    except:
                        pass
            else:
                print(f"Errore WP: {status}")
