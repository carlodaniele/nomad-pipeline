import os
import glob
import shutil
from google import genai
from PIL import Image, ExifTags
import requests
import json

# Configurazione Secrets
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WP_URL = os.getenv("WP_URL")
WP_USER = "carlo"
WP_PASS = os.getenv("WP_APP_PASSWORD")

client = genai.Client(api_key=GEMINI_API_KEY)

def get_decimal_from_dms(dms, ref):
    degrees = dms[0]
    minutes = dms[1] / 60.0
    seconds = dms[2] / 3600.0
    if ref in ['S', 'W']:
        return -float(degrees + minutes + seconds)
    return float(degrees + minutes + seconds)

def process_image_and_metadata(img_path):
    try:
        img = Image.open(img_path)
        exif = img._getexif()
        coords = None

        if exif:
            # Creiamo un dizionario leggibile dei metadati
            metadata = {ExifTags.TAGS.get(tag, tag): value for tag, value in exif.items()}

            # 1. Raddrizzamento fisico basato sull'orientamento
            orientation = metadata.get('Orientation')
            if orientation == 3:
                img = img.rotate(180, expand=True)
            elif orientation == 6:
                img = img.rotate(270, expand=True)
            elif orientation == 8:
                img = img.rotate(90, expand=True)

            # 2. Estrazione coordinate GPS
            gps_info = metadata.get('GPSInfo')
            if gps_info:
                # Il tag 2 è Latitudine, 4 è Longitudine (standard EXIF)
                # Il tag 1 è il riferimento (N/S), 3 è (E/W)
                try:
                    lat = get_decimal_from_dms(gps_info[2], gps_info[1])
                    lon = get_decimal_from_dms(gps_info[4], gps_info[3])
                    coords = {"lat": lat, "lon": lon}
                except Exception as gps_err:
                    print(f"Errore conversione coordinate: {gps_err}")

        # 3. Compressione e salvataggio definitivo (sovrascrive l'originale)
        # Salvando così, l'immagine sarà dritta e "leggera"
        img.save(img_path, "JPEG", quality=85, optimize=True)
        
        return coords

    except Exception as e:
        print(f"Errore nel processing dell'immagine {img_path}: {e}")
        return None

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
    """Carica l'immagine su WP e restituisce ID, URL e COORDINATE"""
    # CHIAMATA CRUCIALE: Raddrizza, comprime e legge il GPS in un colpo solo
    coords = process_image_and_metadata(file_path)
    
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
            # Restituiamo anche le coordinate!
            return data['id'], data['source_url'], coords 
        else:
            print(f"Errore caricamento media: {response.status_code}")
            return None, None, None
    except Exception as e:
        print(f"Errore upload_media: {e}")
        return None, None, None

def upload_audio_to_gemini(file_path):
    """Carica il file audio sui server Google per l'elaborazione"""
    try:
        print(f"Uploading audio to Gemini: {file_path}")
        audio_file = client.files.upload(file=file_path)
        return audio_file
    except Exception as e:
        print(f"Errore caricamento audio: {e}")
        return None

def generate_post_content(raw_text, image_list, locations, lang, audio_files_refs=[]):
    """
    Passiamo a Gemini testo, coordinate e file audio.
    Lui genera Body e Titolo, noi aggiungiamo la parte visiva dopo.
    """

    # Creiamo una stringa con le posizioni se disponibili
    locations_str = ""
    for img in image_list:
        if img.get('coords'):
            locations_str += f"- Image at Lat: {img['coords']['lat']}, Lon: {img['coords']['lon']}\n"
    
    contents = []
    # Aggiungiamo i file audio alla richiesta
    for audio_ref in audio_files_refs:
        contents.append(audio_ref)

    # Uso dei segnaposto per non far sparire i tag nella chat
    # I commenti HTML servono a WordPress per creare i blocchi Gutenberg
    prompt = """
    Transform these notes into a professional blog post.
    Act as a professional Business Content Strategist. 
    Convert the following notes into a blog post a WordPress blog.
    Use the provided coordinates to mention the specific city or area in the post.

    MANDATORY RULES:
    1. LANGUAGE: All content in the JSON fields must be in {lang}.
    2. GEOLOCATION: Use the coordinates {locs} to identify the location. 
       CRITICAL: If {locs} is empty, DO NOT invent a location.
    3. FORMAT: Return ONLY a valid JSON object.

    Structure the 'body' using WordPress Gutenberg blocks (, ).

    WORDPRESS BLOCK RULES (Apply to the 'body' field): 
    1. You must wrap every element exactly like this:
    - Paragraphs: <!-- wp:paragraph --><p>text</p><!-- /wp:paragraph -->
    - Headings: <!-- wp:heading --><h2 class="wp-block-heading">text</h2><!-- /wp:heading -->

    REQUIRED JSON STRUCTURE:
    {{
        "title": "A catchy, professional title",
        "body": "The main content using WordPress Gutenberg blocks (and )",
        "excerpt": "A 20-word SEO-friendly summary",
        "tags": ["tag1", "tag2", "tag3"],
        "focus_kw": "The primary focus keyword for Yoast SEO"
    }}
    
    Notes: {notes}
    """.format(notes=raw_text, locs=locations_str, lang=lang)
    
    contents.append(prompt)
    
    response = client.models.generate_content(
        model="gemini-flash-latest", # <--- CORRETTO
        contents=contents
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

def process_gemini_response(response_text):
    try:
        # Remove any markdown formatting if present
        clean_json = response_text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_json)
        return data
    except Exception as e:
        print(f"Error parsing JSON: {e}")
        return None

def publish_to_wordpress(data, media_id=None, locations=None):
    base_url = WP_URL.strip().rstrip('/')
    endpoint = f"{base_url}/index.php?rest_route=/wp/v2/posts"
    auth = (WP_USER, WP_PASS)
    
    # Extract data from the JSON dictionary provided by Gemini
    title = data.get("title", "New Post from Nomad Pipeline")
    content = data.get("body", "")
    excerpt = data.get("excerpt", "")
    focus_kw = data.get("focus_kw", "")
    
    # Add Google Maps link if locations are available
    if locations and isinstance(locations, str):
        try:
            # Prende la prima coordinata (funziona sia con 1 che con 10 foto)
            first_coord = locations.split(';')[0].strip()
            # Pulizia opzionale se la stringa contiene "lat:"
            clean_coord = first_coord.replace("lat:", "").replace("lon:", "").replace("{", "").replace("}", "").strip()
            
            map_html = f'\n\n<p>📍 <a href="https://www.google.com/maps/search/?api=1&query={clean_coord}">View on Google Maps</a></p>'
            content += map_html
        except:
            pass

    post_data = {
        "title": title,
        "content": content,
        "excerpt": excerpt,
        "status": "draft",
        "meta": {
            "_yoast_wpseo_focuskw": focus_kw,
            "_yoast_wpseo_metadesc": excerpt
        }
    }
    
    if media_id:
        post_data["featured_media"] = media_id
        
    try:
        response = requests.post(endpoint, json=post_data, auth=auth)
        if response.status_code == 201:
            print("Post created successfully as a draft.")
        else:
            print(f"WP Error: {response.status_code} - {response.text}")
        return response.status_code
    except Exception as e:
        print(f"Error connecting to WordPress: {e}")
        return None

if __name__ == "__main__":    
    # Configuration
    upload_dir = "uploads"
    archive_dir = "processed"
    target_language = "Italian"
    
    if not os.path.exists(upload_dir): os.makedirs(upload_dir)
    if not os.path.exists(archive_dir): os.makedirs(archive_dir)

    # --- 1. RACCOLTA FILE ---
    image_files = []
    for ext in ('*.jpg', '*.jpeg', '*.png', '*.webp'):
        image_files.extend(glob.glob(os.path.join(upload_dir, ext)))
    
    audio_files = []
    for ext in ('*.mp3', '*.m4a', '*.wav', '*.ogg', '*.oga'):
        audio_files.extend(glob.glob(os.path.join(upload_dir, ext)))
    
    text_files = glob.glob(os.path.join(upload_dir, "*.txt"))

    # --- 2. UPLOAD IMMAGINI SU WORDPRESS (Per la Galleria) ---
    uploaded_images = []
    locations_list = []
    for img_path in image_files:
        print(f"Uploading image to WP: {img_path}")
        m_id, m_url, m_coords = upload_media(img_path)
        if m_id:
            uploaded_images.append({'id': m_id, 'url': m_url, 'coords': m_coords})
            if m_coords: locations_list.append(f"{m_coords['lat']},{m_coords['lon']}")

    all_coords = "; ".join(locations_list) if locations_list else ""

    # --- 3. UPLOAD AUDIO SU GOOGLE AI (Per Gemini) ---
    audio_refs = []
    for au_path in audio_files:
        ref = upload_audio_to_gemini(au_path)
        if ref:
            audio_refs.append(ref)

    # --- 4. LETTURA NOTE TESTUALI ---
    raw_notes = ""
    for txt_path in text_files:
        with open(txt_path, "r", encoding="utf-8") as f:
            raw_notes += f.read() + "\n"

    # --- 5. GENERAZIONE POST (Solo se abbiamo almeno un testo o un audio) ---
    if not raw_notes and not audio_refs:
        print("Nulla da elaborare (mancano sia testo che audio).")
    else:
        print("Generating content with Gemini...")
        raw_output = generate_post_content(raw_notes, uploaded_images, all_coords, target_language, audio_refs)
        structured_data = process_gemini_response(raw_output)

        if structured_data:
            # 6. COSTRUZIONE GALLERIA (Usa la logica corretta +=)
            gallery_html = ""
            if len(uploaded_images) > 1:
                gallery_html = '\n\n\n<!-- wp:gallery {"linkTo":"none"} -->'
                gallery_html += '\n<figure class="wp-block-gallery has-nested-images columns-default is-cropped">'
                for img in uploaded_images:
                    gallery_html = '\n<!-- wp:image {"lightbox":{"enabled":true}, "id": %s, "sizeSlug": "large", "linkDestination":"none"} -->\n' % str(img["id"])
                    gallery_html += f'<figure class="wp-block-image size-large"><img src="{img["url"]}" alt="Nomad" class="wp-image-{img["id"]}"/></figure>\n'
                    gallery_html += '\n<!-- /wp:image -->\n'
                gallery_html += '\n</figure>'
                gallery_html += '\n<!-- /wp:gallery -->\n'
            elif len(uploaded_images) == 1:
                img = uploaded_images[0]
                gallery_html = '\n\n\n<!-- wp:image {"lightbox":{"enabled":true}, "id": %s, "sizeSlug": "large", "linkDestination":"none"} -->\n' % str(img["id"])
                gallery_html += f'<figure class="wp-block-image size-large"><img src="{img["url"]}" alt="Nomad" class="wp-image-{img["id"]}"/></figure>\n'
                gallery_html += '\n<!-- /wp:image -->\n'
            
            structured_data["body"] = structured_data.get("body", "") + gallery_html

            # 7. PUBBLICAZIONE
            feat_id = uploaded_images[0]['id'] if uploaded_images else None
            status = publish_to_wordpress(structured_data, feat_id, all_coords)
            
            if status in [200, 201]:
                print(f"Success! Post created.")
                # ARCHIVIAZIONE FILE
                for f in image_files + audio_files + text_files:
                    try:
                        shutil.move(f, os.path.join(archive_dir, os.path.basename(f)))
                    except:
                        pass
            else:
                print(f"WP Error: {status}")
        else:
            print("Gemini non ha restituito un JSON valido.")