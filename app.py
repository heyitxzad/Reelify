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
# 1. STREAMLIT APP LAYOUT & DESIGNS (Reelify)
# ----------------------------------------------------------
st.set_page_config(page_title="Reelify", page_icon="🎬", layout="centered")

# Branded Red Header
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
user_prompt = st.text_area("Video Prompt / Vibe (Optional)", placeholder="e.g. Make it feel super energetic, focused on clearing acne for sensitive skin.")

# Step 1: Model Selection
st.subheader("👤 Step 1: Select Your Presenter Model")
col1, col2 = st.columns(2)
with col1:
    model_gender = st.selectbox("Model Gender:", ["Female", "Male"])
with col2:
    model_ethnicity = st.selectbox(
        "Model Region / Ethnicity:",
        ["East Asian", "South Asian / Indian", "Black / African", "Caucasian / Western", "None (Use Uploaded Assets Only)"]
    )

# Step 2: Voice Selection
st.subheader("🎙️ Step 2: Select Your Presenter Voice & Tone")
col3, col4 = st.columns(2)
with col3:
    voice_region = st.selectbox("Voice Accent / Region:", ["United States", "United Kingdom", "Australia", "India"])
with col4:
    voice_tone = st.selectbox("Voice Tone / Style:", ["Confident & Energetic", "Warm & Conversational", "Calm & Professional"])

# Step 3: Product Upload
st.subheader("📸 Step 3: Upload Product Photos (Optional)")
uploaded_files = st.file_uploader(
    "Upload photos of your product. If added, the editor will dynamically blend them with your chosen model photos!",
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
    canvas = Image.new("RGBA", (target_w, target_h), (18, 18, 18, 255))
    
    # Paste centered
    paste_x = (target_w - new_w) // 2
    paste_y = (target_h - new_h) // 2
    canvas.paste(img_resized, (paste_x, paste_y))

    draw = ImageDraw.Draw(canvas, "RGBA")
    font = get_custom_font(55)

    color_map = {"yellow": (255, 223, 0, 255), "white": (255, 255, 255, 255), "cyan": (0, 255, 255, 255)}
    font_color = color_map.get(styling.get("text_color"), (255, 255, 255, 255))
    text_style = styling.get("text_style", "tiktok_stroke")

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
    y_pos = int(target_h * 0.72)

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
        
    return canvas

# Dynamic Database of Free, Premium Vertical Photos of Models
MODEL_DATABASE = {
    "Female_East Asian": [
        "https://images.unsplash.com/photo-1512290923902-8a9f81dc236c?w=800", # Glowing skin apply
        "https://images.unsplash.com/photo-1501196354995-cbb51c65aaea?w=800", # Elegant smile
        "https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?w=800"  # Skincare routine
    ],
    "Female_South Asian / Indian": [
        "https://images.unsplash.com/photo-1617897903246-719242758050?w=800", # Warm skincare dropper
        "https://images.unsplash.com/photo-1601412436009-d964bd02edbc?w=800", # Aesthetic model smile
        "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=800"  # Clean face close up
    ],
    "Female_Black / African": [
        "https://images.unsplash.com/photo-1531123897727-8f129e1688ce?w=800", # Confident glowing skin
        "https://images.unsplash.com/photo-1523824921871-d6f1a15151f1?w=800", # Aesthetic skincare wash
        "https://images.unsplash.com/photo-1509631179647-0177331693ae?w=800"  # Gorgeous smile close up
    ],
    "Female_Caucasian / Western": [
        "https://images.unsplash.com/photo-1556228720-195a672e8a03?w=800", # Elegant bathroom skincare
        "https://images.unsplash.com/photo-1598440947619-2c35fc9aa908?w=800", # Applying moisturizer
        "https://images.unsplash.com/photo-1608248597481-496100c80836?w=800"  # Serum dropper
    ],
    "Male_East Asian": [
        "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800", # Friendly clean smile
        "https://images.unsplash.com/photo-1620916566398-39f1143ab7be?w=800", # Skincare routine male
        "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=800"  # Fresh skin close up
    ],
    "Male_South Asian / Indian": [
        "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=800", # Confident male grooming
        "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=800", # Clean smile close up
        "https://images.unsplash.com/photo-1618015358954-115ef1ed1515?w=800"  # Grooming routine
    ],
    "Male_Black / African": [
        "https://images.unsplash.com/photo-1492562080023-ab3db95bfbce?w=800", # Energetic handsome smile
        "https://images.unsplash.com/photo-1503944583220-79d8926ad5e2?w=800", # Grooming facial shot
        "https://images.unsplash.com/photo-1522075469751-3a6694fb2f61?w=800"  # Clean model look
    ],
    "Male_Caucasian / Western": [
        "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=800", # Luxury grooming aesthetic
        "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=800", # Sharp model jawline
        "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=800"  # Clean smile
    ]
}

def download_model_photos(gender, ethnicity, temp_dir="temp_assets"):
    os.makedirs(temp_dir, exist_ok=True)
    key = f"{gender}_{ethnicity}"
    urls = MODEL_DATABASE.get(key, MODEL_DATABASE["Female_Caucasian / Western"])
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

# Free Edge Neural Voices mapping
VOICE_MAP = {
    "United States_Female_Confident & Energetic": "en-US-EmmaMultilingualNeural",
    "United States_Female_Warm & Conversational": "en-US-AvaNeural",
    "United States_Female_Calm & Professional": "en-US-JennyNeural",
    
    "United States_Male_Confident & Energetic": "en-US-BrianNeural",
    "United States_Male_Warm & Conversational": "en-US-GuyNeural",
    "United States_Male_Calm & Professional": "en-US-AndrewNeural",
    
    "United Kingdom_Female_Confident & Energetic": "en-GB-SoniaNeural",
    "United Kingdom_Male_Confident & Energetic": "en-GB-RyanNeural",
    
    "Australia_Female_Confident & Energetic": "en-AU-NatashaNeural",
    
    "India_Female_Confident & Energetic": "en-IN-NeerjaNeural",
    "India_Male_Confident & Energetic": "en-IN-PrabhatNeural",
}

async def generate_neural_voiceover(text, region, gender, tone, output_path="temp_voiceover.mp3"):
    key = f"{region}_{gender}_{tone}"
    # Fallback to standard US Emma if not found
    voice_actor = VOICE_MAP.get(key, VOICE_MAP.get(f"United States_{gender}_Confident & Energetic", "en-US-EmmaMultilingualNeural"))
    communicate = edge_tts.Communicate(text, voice_actor)
    await communicate.save(output_path)
    return output_path

# ----------------------------------------------------------
# 3. RUN GENERATION ACTION
# ----------------------------------------------------------
if st.button("🚀 Generate Viral Ad Video"):
    if not product_input:
        st.error("Please enter your product name first!")
    elif "None" in model_ethnicity and not uploaded_files:
        st.error("Please upload at least 2 product photos if you are not using a model!")
    else:
        with st.spinner("Reelify is analyzing, generating natural speech, and aligning custom layouts..."):
            try:
                temp_dir = "temp_assets"
                os.makedirs(temp_dir, exist_ok=True)
                
                # 1. Setup model assets
                model_assets = []
                if "None" not in model_ethnicity:
                    st.info(f"Directing {model_ethnicity} {model_gender} Presenter Model...")
                    model_assets = download_model_photos(model_gender, model_ethnicity, temp_dir)
                
                # 2. Setup user uploaded assets
                uploaded_assets = []
                if uploaded_files:
                    st.info("Loading your product photos...")
                    for uploaded_file in uploaded_files:
                        path = os.path.join(temp_dir, f"uploaded_{uploaded_file.name}")
                        with open(path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                        uploaded_assets.append(path)
                    uploaded_assets.sort()

                # Dynamic Blend (Interleave)
                saved_assets = []
                max_len = max(len(model_assets), len(uploaded_assets))
                for i in range(max_len):
                    if i < len(model_assets):
                        saved_assets.append(model_assets[i])
                    if i < len(uploaded_assets):
                        saved_assets.append(uploaded_assets[i])

                if not saved_assets:
                    raise ValueError("No assets found to compile.")

                # 3. Call Gemini for copy based on prompt
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
                    prompt_instructions = (
                        f"Write a conversational, high-converting social media script for '{product_input}'. "
                        f"Tone guidelines: {user_prompt if user_prompt else 'conversational, excited, talking to a friend'}. "
                        "Do not sound robotic. Output raw JSON only."
                    )
                    prompt = f'{prompt_instructions}. Output raw JSON only.'
                    response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    text = response.text.strip()
                    if text.startswith("```json"): text = text[7:]
                    elif text.startswith("```"): text = text[3:]
                    if text.endswith("```"): text = text[:-3]
                    pkg = json.loads(text.strip())

                # 4. Create Neural Voiceover (100% realistic)
                st.info("🎙️ Synthesizing Premium Human-like Neural Voiceover...")
                voice_path = "temp_voiceover.mp3"
                asyncio.run(generate_neural_voiceover(pkg["voiceover_text"], voice_region, model_gender, voice_tone, voice_path))

                # 5. Compile Video Scenes
                st.info("🎬 Rendering dynamic video scenes...")
                voice_clip = AudioFileClip(voice_path)
                total_duration = voice_clip.duration
                scene_duration = total_duration / len(saved_assets)
                
                clips = []
                num_subs = len(pkg["script"])
                sub_display_time = total_duration / num_subs

                for i, asset_path in enumerate(saved_assets):
                    # Subtitle synchronization
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