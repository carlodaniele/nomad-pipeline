import os
import glob
import shutil
from google import genai
from PIL import Image
import requests

# Configurazione Secrets
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WP_URL = os.getenv("WP_URL")
WP_USER = "carlo" 
WP_PASS = os.getenv("WP_APP_PASSWORD")

client = genai.Client(api_key=GEMINI_API_KEY)

def resize_image(file_path, max_width=1600):
    """Ridimensiona l'immagine per ottimizzare spazio su Kinsta"""
    try:
        with Image.open(file_path) as img:
            if img.width > max_width:
                ratio = max_width / float(img.width)
                new_height = int(float(img.height) * float(ratio))
                img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                # Sovrascrive l'originale con la versione ottimizzata
                img.save(file_path, optimize=True, quality=85)
    except Exception as e:
        print(f"Errore resize: {e}")

def upload_media(file_path):
    """Carica l'immagine su WP e restituisce ID e URL"""
    resize_image(file_path)
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

def generate_post_content(raw_text, image_list=[]):
    """
    Passiamo a Gemini solo il testo. 
    Lui genera Body e Titolo, noi aggiungiamo la parte visiva dopo.
    """
    
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
    raw_output = response.text

    # Inizializziamo il contenitore come stringa vuota (Scenario 0: Nessuna immagine)
    images_content = ""
    num_images = len(image_list)

    if num_images == 1:
        # Scenario 1: Singola immagine
        img = image_list[0]
        images_content = (
            '\n\n\n' +
            '<!-- wp:image ' + str(img["id"]) + ', "sizeSlug": "large", "linkDestination":"none"} -->\n' +
            '<figure class="wp-block-image size-large"><img src="' + img["url"] + '" alt="Nomad Journey" class="wp-image-' + str(img["id"]) + '"/></figure>\n' +
            '<!-- /wp:image -->\n' +
            '\n'
        )
        
    elif num_images > 1:
        # Scenario 2: Più immagini (Galleria)
        ids_str = ",".join([str(img['id']) for img in image_list])
        images_content = '\n\n\n'
        images_content += '<!-- wp:gallery {"linkTo":"none"} -->\n'
        images_content += '<figure class="wp-block-gallery has-nested-images columns-default is-cropped">'
        for img in image_list:
            images_content += (
                '\n\n\n' +
                '<!-- wp:image {"id": ' + str(img["id"]) + ', "sizeSlug": "large", "linkDestination":"none"} -->\n' +
                '<figure class="wp-block-image size-large"><img src="' + img["url"] + '" alt="Nomad Journey" class="wp-image-' + str(img["id"]) + '"/></figure>\n' +
                '<!-- /wp:image -->\n' +
                '\n'
            )
        images_content += '\n<!-- /wp:gallery -->\n'
        images_content += '\n</figure>\n'

    # Se num_images è 0, images_content resta "" e non sporca il post.
    return raw_output + images_content

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

def publish_to_wordpress(title, content, media_id=None):
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

    # 1. Carica TUTTE le Immagini
    image_extensions = ('*.jpg', '*.jpeg', '*.png', '*.webp')
    image_files = []
    for ext in image_extensions:
        image_files.extend(glob.glob(os.path.join(upload_dir, ext)))
    
    uploaded_images = [] # Creiamo la lista per la galleria
    for img_path in image_files:
        print(f"Caricamento immagine: {img_path}")
        m_id, m_url = upload_media(img_path)
        if m_id:
            uploaded_images.append({'id': m_id, 'url': m_url})

    # 2. Cerca Testi
    text_files = glob.glob(os.path.join(upload_dir, "*.txt"))
    if not text_files:
        print("Nessun file di testo trovato.")
    else:
        for file_path in text_files:
            print(f"In lavorazione: {file_path}")
            with open(file_path, "r", encoding="utf-8") as f:
                raw_notes = f.read()
            
            # 1. Genera il contenuto passando la LISTA delle immagini
            raw_output = generate_post_content(raw_notes, uploaded_images)
            title, blog_content = parse_gemini_output(raw_output)

            # 2. Prendi la prima immagine come immagine in evidenza (se esiste)
            feat_id = uploaded_images[0]['id'] if uploaded_images else None
            
            # 3. Pubblica UNA SOLA VOLTA
            status = publish_to_wordpress(title, blog_content, feat_id)
            
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
