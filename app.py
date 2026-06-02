import streamlit as st
import os
import json
import urllib.request
import numpy as np
import traceback
import asyncio
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from google import genai
from moviepy import ImageClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip

# ----------------------------------------------------------
# 1. STREAMLIT APP LAYOUT & DESIGNS (Reelify Branded)
# ----------------------------------------------------------
st.set_page_config(page_title="Reelify", page_icon="🎬", layout="centered")

# Branded Red Header with stylized 'R'
st.markdown(
    """
    <div style="text-align: center; margin-top: -30px; margin-bottom: 20px;">
        <div style="font-size: 55px; font-weight: 800; color: #E53935; font-family: 'Helvetica Neue', Arial, sans-serif; letter-spacing: -1px;">
            <span style="font-family: 'Georgia', 'Times New Roman', serif; font-size: 72px; font-style: italic; color: #B71C1C; font-weight: 900; margin-right: -6px;">R</span>eelify
        </div>
        <p style="font-size: 15px; color: #666666; margin-top: 5px;">
            The Ultimate Smart Video Editor for Viral Affiliate Ads
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

# Sidebar settings
st.sidebar.header("🔑 App Settings")
gemini_key = st.sidebar.text_input("Enter GEMINI_API_KEY", type="password", help="Get a free key from Google AI Studio.")

# Main Inputs
product_input = st.text_input("Product Name / Affiliate Keyword", placeholder="e.g. Good Molecules Azelaic Acid Cleanser")

# Separate Inputs: Presenter Model AND User Uploads
st.subheader("👤 Step 1: Choose Your Presenter Model")
model_choice = st.selectbox(
    "Select an AI model to present your product:",
    [
        "Skincare / Beauty Model (Female)",
        "Skincare / Grooming Model (Male)",
        "None (Use Uploaded Assets Only)"
    ]
)

st.subheader("📸 Step 2: Upload Your Product Photos (Optional)")
uploaded_files = st.file_uploader(
    "Upload photos of your product. If added, the editor will dynamically blend them with the model photos!",
    accept_multiple_files=True,
    type=['png', 'jpg', 'jpeg']
)

# ----------------------------------------------------------
# 2. ADVANCED BACKEND PIPELINE
# ----------------------------------------------------------
# Downloads a high-impact advertising font
def get_custom_font(font_size=55):
    font_path = "Anton-Regular.ttf"
    if not os.path.exists(font_path):
        try:
            url = "https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf"
            urllib.request.urlretrieve(url, font_path)
        except Exception:
            return ImageFont.load_default()
    return ImageFont.truetype(font_path, font_size)

# Draw gorgeous TikTok style outlined subtitles (Fit-to-Screen)
def draw_smart_text(image_path, text, styling):
    img = Image.open(image_path)
    target_w, target_h = 720, 1280
    img_ratio = img.width / img.height
    target_ratio = target_w / target_h
    
    # "Fit-to-Screen" Letterboxing (No Zoom, No Crop)
    if img_ratio > target_ratio:
        new_w = target_w
        new_h = int(target_w / img_ratio)
    else:
        new_h = target_h
        new_w = int(target_h * img_ratio)
        
    img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    # Create dark-grey solid background canvas
    canvas = Image.new("RGBA", (target_w, target_h), (18, 18, 18, 255))
    
    # Paste resized image centered
    paste_x = (target_w - new_w) // 2
    paste_y = (target_h - new_h) // 2
    canvas.paste(img_resized, (paste_x, paste_y))

    draw = ImageDraw.Draw(canvas, "RGBA")
    font = get_custom_font(55) # Large, bold advertising font

    color_map = {"yellow": (255, 223, 0, 255), "white": (255, 255, 255, 255), "cyan": (0, 255, 255, 255)}
    font_color = color_map.get(styling.get("text_color"), (255, 255, 255, 255))
    text_style = styling.get("text_style", "tiktok_stroke")

    # Wrap subtitles
    words = text.split()
    lines, current_line = [], []
    for word in words:
        test_line = " ".join(current_line + [word])
        w = draw.textbbox((0, 0), test_line, font=font)[2]
        if w < (target_w - 100):
            current_line.append(word)
        else:
            lines.append(" ".join(current_line))
            current_line = [word]
    if current_line:
        lines.append(" ".join(current_line))
    
    wrapped_text = "\n".join(lines)
    text_h = draw.multiline_textbbox((0, 0), wrapped_text, font=font, align="center")[3]
    
    center_x = target_w // 2
    y_pos = int(target_h * 0.72) # Positioned lower to avoid covering the product

    if text_style == "tiktok_stroke":
        draw.multiline_text((center_x, y_pos), wrapped_text, font=font, fill=font_color, stroke_width=6, stroke_fill=(0, 0, 0, 255), anchor="ma", align="center")
    elif text_style == "neon_glow":
        for offset in range(4, 0, -1):
            draw.multiline_text((center_x + offset, y_pos + offset), wrapped_text, font=font, fill=(0, 0, 0, 120), anchor="ma", align="center")
        draw.multiline_text((center_x, y_pos), wrapped_text, font=font, fill=font_color, anchor="ma", align="center")
    else: # classic_banner
        padding = 20
        draw.rectangle([(0, y_pos - 10), (target_w, y_pos + text_h + padding*2)], fill=(0, 0, 0, 160))
        draw.multiline_text((center_x, y_pos + padding - 10), wrapped_text, font=font, fill=font_color, anchor="ma", align="center")
        
    return canvas # FIXED HERE!

# Stable High-Res Aesthetic Stock Images of Models
MODEL_PHOTOS_URLS = {
    "beauty_female": [
        "https://images.unsplash.com/photo-1556228720-195a672e8a03?w=800", # Beauty setup
        "https://images.unsplash.com/photo-1598440947619-2c35fc9aa908?w=800", # Skincare application
        "https://images.unsplash.com/photo-1608248597481-496100c80836?w=800"  # Skincare texture / dropper
    ],
    "beauty_male": [
        "https://images.unsplash.com/photo-1620916566398-39f1143ab7be?w=800", # Male grooming product
        "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=800", # Clean skincare close up
        "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=800"  # Clean smile close up
    ]
}

def download_model_photos(style_key, temp_dir="temp_assets"):
    os.makedirs(temp_dir, exist_ok=True)
    urls = MODEL_PHOTOS_URLS.get(style_key, MODEL_PHOTOS_URLS["beauty_female"])
    downloaded_paths = []
    
    for i, url in enumerate(urls):
        filename = f"model_photo_{i}.jpg"
        dest_path = os.path.join(temp_dir, filename)
        if not os.path.exists(dest_path):
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req) as response, open(dest_path, 'wb') as out_file:
                    out_file.write(response.read())
                downloaded_paths.append(dest_path)
            except Exception as e:
                print(f"Error downloading photo {i}: {e}")
        else:
            downloaded_paths.append(dest_path)
    return downloaded_paths

async def generate_neural_voiceover(text, voice_gender, output_path="temp_voiceover.mp3"):
    voice_actor = "en-US-EmmaMultilingualNeural" if voice_gender == "female" else "en-US-BrianNeural"
    communicate = edge_tts.Communicate(text, voice_actor)
    await communicate.save(output_path)
    return output_path

# ----------------------------------------------------------
# 3. RUN GENERATION ACTION
# ----------------------------------------------------------
if st.button("🚀 Generate High-Conversion Video"):
    if not product_input:
        st.error("Please enter your product name first!")
    elif "None" in model_choice and not uploaded_files:
        st.error("Please upload at least 2 product photos if you are not using a model!")
    else:
        with st.spinner("AI is directing layout, synthesizing neural voice, and rendering video..."):
            try:
                temp_dir = "temp_assets"
                os.makedirs(temp_dir, exist_ok=True)
                
                # Setup model assets
                model_assets = []
                voice_gender = "female"
                
                if "Female" in model_choice:
                    st.info("Directing Elegant Female Model...")
                    model_assets = download_model_photos("beauty_female", temp_dir)
                    voice_gender = "female"
                elif "Male" in model_choice:
                    st.info("Directing Clean Grooming Male Model...")
                    model_assets = download_model_photos("beauty_male", temp_dir)
                    voice_gender = "male"
                
                # Setup user uploaded assets
                uploaded_assets = []
                if uploaded_files:
                    st.info("Loading your product photos...")
                    for uploaded_file in uploaded_files:
                        path = os.path.join(temp_dir, f"uploaded_{uploaded_file.name}")
                        with open(path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                        uploaded_assets.append(path)
                    uploaded_assets.sort()

                # Dynamic Blend (Interleave): Alternates between model photo and product photo
                saved_assets = []
                max_len = max(len(model_assets), len(uploaded_assets))
                for i in range(max_len):
                    if i < len(model_assets):
                        saved_assets.append(model_assets[i])
                    if i < len(uploaded_assets):
                        saved_assets.append(uploaded_assets[i])

                if not saved_assets:
                    raise ValueError("No assets found to compile.")

                # 2. Call Gemini for copy
                if not gemini_key:
                    pkg = {
                        "script": [
                            "Sensitive, red, or irritated skin?",
                            "This calming formula gently cleanses skin without stripping.",
                            "Get smooth, glowing skin today. Link in bio!"
                        ],
                        "voiceover_text": f"If you struggle with sensitive, red, or oily skin, you need to stop stripping your barrier. Try this soothing azelaic acid cleanser from Good Molecules. It clears redness gently. Grab yours at the link in my bio!",
                        "captions": f"Heal your skin barrier with Good Molecules. Link in bio.",
                        "hashtags": "#goodmolecules #skincaremusthaves #sensitiveskin",
                        "styling": {"text_color": "yellow", "text_style": "tiktok_stroke"}
                    }
                else:
                    client = genai.Client(api_key=gemini_key)
                    prompt = f'Create a viral vertical ad script for "{product_input}". Output raw JSON only.'
                    response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    text = response.text.strip()
                    if text.startswith("```json"): text = text[7:]
                    elif text.startswith("```"): text = text[3:]
                    if text.endswith("```"): text = text[:-3]
                    pkg = json.loads(text.strip())

                # 3. Create Neural Voiceover
                st.info("🎙️ Synthesizing Premium Human-like Neural Voiceover...")
                voice_path = "temp_voiceover.mp3"
                asyncio.run(generate_neural_voiceover(pkg["voiceover_text"], voice_gender, voice_path))

                # 4. Compile Video Scenes
                st.info("🎬 Rendering dynamic video scenes...")
                voice_clip = AudioFileClip(voice_path)
                total_duration = voice_clip.duration
                scene_duration = total_duration / len(saved_assets)
                
                clips = []
                num_subs = len(pkg["script"])
                sub_display_time = total_duration / num_subs

                for i, asset_path in enumerate(saved_assets):
                    # Align subtitle segments with the timeline
                    current_time = i * scene_duration
                    sub_idx = min(int(current_time / sub_display_time), num_subs - 1)
                    sub_text = pkg["script"][sub_idx]
                    
                    processed_img = draw_smart_text(asset_path, sub_text, pkg["styling"])
                    clip = ImageClip(np.array(processed_img)).with_duration(scene_duration)
                    clips.append(clip)

                # Concatenate
                final_clip = concatenate_videoclips(clips, method="compose")
                
                audio_tracks = [voice_clip.with_volume_scaled(1.0)]
                final_clip = final_clip.with_audio(CompositeAudioClip(audio_tracks))

                output_path = "output_viral_video.mp4"
                final_clip.write_videofile(output_path, fps=24, codec="libx264", audio=True)
                
                for c in clips: c.close()
                voice_clip.close()
                final_clip.close()

                # ----------------------------------------------------------
                # 4. DISPLAY THE OUTPUTS IN APP
                # ----------------------------------------------------------
                st.success("🎉 Reelify Video Successfully Compiled!")
                st.video(output_path)
                
                with open(output_path, "rb") as file:
                    st.download_button(
                        label="💾 Download Video File",
                        data=file,
                        file_name="reelify_ad.mp4",
                        mime="video/mp4"
                    )
                
                st.subheader("📝 Proposed Caption & Hashtags")
                st.code(f"{pkg['captions']}\n\n{pkg['hashtags']}")

            except Exception as e:
                st.error("Something went wrong during assembly.")
                st.text(traceback.format_exc())