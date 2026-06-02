import streamlit as st
import os
import json
import urllib.request
import numpy as np
import traceback
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS
from google import genai
from moviepy import ImageClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip

# ----------------------------------------------------------
# 1. STREAMLIT APP LAYOUT & DESIGNS (Branded)
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
            Upload product photos, enter your keyword, and let the AI build a styled, voiced-over video automatically!
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

# Sidebar for credentials and configurations
st.sidebar.header("🔑 App Settings")
gemini_key = st.sidebar.text_input("Enter GEMINI_API_KEY", type="password", help="Get a free key from Google AI Studio.")

# Main Inputs
product_input = st.text_input("Affiliate Product / Keyword", placeholder="e.g. Good Molecules Azelaic Acid Cleanser")
uploaded_files = st.file_uploader("Upload Product Photos or Videos", accept_multiple_files=True, type=['png', 'jpg', 'jpeg', 'mp4', 'mov'])

# ----------------------------------------------------------
# 2. BACKEND PIPELINE LOGIC
# ----------------------------------------------------------
def draw_smart_text(image_path, text, styling):
    img = Image.open(image_path)
    target_w, target_h = 720, 1280
    img_ratio = img.width / img.height
    target_ratio = target_w / target_h
    
    if img_ratio > target_ratio:
        scale = target_h / img.height
        new_w = int(img.width * scale)
        img_final = img.resize((new_w, target_h), Image.Resampling.LANCZOS).crop(((new_w - target_w) // 2, 0, (new_w - target_w) // 2 + target_w, target_h))
    else:
        scale = target_w / img.width
        new_h = int(img.height * scale)
        img_final = img.resize((target_w, new_h), Image.Resampling.LANCZOS).crop((0, (new_h - target_h) // 2, target_w, (new_h - target_h) // 2 + target_h))

    draw = ImageDraw.Draw(img_final, "RGBA")
    font = ImageFont.load_default()

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
    y_pos = int(target_h * 0.70)

    if text_style == "tiktok_stroke":
        draw.multiline_text((center_x, y_pos), wrapped_text, font=font, fill=font_color, stroke_width=5, stroke_fill=(0, 0, 0, 255), anchor="ma", align="center")
    elif text_style == "neon_glow":
        for offset in range(3, 0, -1):
            draw.multiline_text((center_x + offset, y_pos + offset), wrapped_text, font=font, fill=(0, 0, 0, 100), anchor="ma", align="center")
        draw.multiline_text((center_x, y_pos), wrapped_text, font=font, fill=font_color, anchor="ma", align="center")
    else: # classic_banner
        padding = 20
        draw.rectangle([(0, y_pos - 10), (target_w, y_pos + text_h + padding*2)], fill=(0, 0, 0, 160))
        draw.multiline_text((center_x, y_pos + padding - 10), wrapped_text, font=font, fill=font_color, anchor="ma", align="center")
        
    return img_final

# ----------------------------------------------------------
# 3. RUN GENERATION ACTION
# ----------------------------------------------------------
if st.button("🚀 Generate Viral Short-Form Video"):
    if not product_input:
        st.error("Please enter a product name first!")
    elif not uploaded_files:
        st.error("Please upload at least 2 product photos!")
    else:
        with st.spinner("AI is analyzing product, generating script, voiceover, and rendering video..."):
            try:
                temp_dir = "temp_assets"
                os.makedirs(temp_dir, exist_ok=True)
                for file in os.listdir(temp_dir):
                    os.remove(os.path.join(temp_dir, file))
                
                saved_assets = []
                for uploaded_file in uploaded_files:
                    path = os.path.join(temp_dir, uploaded_file.name)
                    with open(path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    saved_assets.append(path)
                saved_assets.sort()

                if not gemini_key:
                    pkg = {
                        "script": ["Looking for a game-changer?", f"This {product_input} upgrades your routine instantly.", "Get yours today! Link in bio!"],
                        "voiceover_text": f"If you are looking for the absolute best {product_input}, you need to stop scrolling. Grab yours now at the link in bio.",
                        "captions": f"Upgrade your lifestyle with {product_input}! Link in bio.",
                        "hashtags": "#musthave #viralproduct #affiliate",
                        "styling": {"text_color": "yellow", "text_style": "tiktok_stroke", "music_genre": "lofi", "transition_effect": "none"}
                    }
                else:
                    client = genai.Client(api_key=gemini_key)
                    prompt = f'Create a viral vertical video marketing package for: "{product_input}". Output raw JSON only.'
                    response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    text = response.text.strip()
                    if text.startswith("```json"): text = text[7:]
                    elif text.startswith("```"): text = text[3:]
                    if text.endswith("```"): text = text[:-3]
                    pkg = json.loads(text.strip())

                voice_path = "temp_voiceover.mp3"
                tts = gTTS(text=pkg["voiceover_text"], lang='en', slow=False)
                tts.save(voice_path)

                voice_clip = AudioFileClip(voice_path)
                total_duration = voice_clip.duration
                scene_duration = total_duration / len(saved_assets)
                
                clips = []
                num_subs = len(pkg["script"])
                sub_display_time = total_duration / num_subs

                for i, asset_path in enumerate(saved_assets):
                    current_time = i * scene_duration
                    sub_idx = min(int(current_time / sub_display_time), num_subs - 1)
                    sub_text = pkg["script"][sub_idx]
                    
                    processed_img = draw_smart_text(asset_path, sub_text, pkg["styling"])
                    clip = ImageClip(np.array(processed_img)).with_duration(scene_duration)
                    clips.append(clip)

                final_clip = concatenate_videoclips(clips, method="compose")
                
                audio_tracks = [voice_clip.with_volume_scaled(1.0)]
                final_clip = final_clip.with_audio(CompositeAudioClip(audio_tracks))

                output_path = "output_viral_video.mp4"
                final_clip.write_videofile(output_path, fps=24, codec="libx264", audio=True)
                
                for c in clips: c.close()
                voice_clip.close()
                final_clip.close()

                st.success("🎉 Video Successfully Compiled!")
                st.video(output_path)
                
                with open(output_path, "rb") as file:
                    st.download_button(
                        label="💾 Download Video File",
                        data=file,
                        file_name="viral_ad.mp4",
                        mime="video/mp4"
                    )
                
                st.subheader("📝 Proposed Social Caption & Hashtags")
                st.code(f"{pkg['captions']}\n\n{pkg['hashtags']}")

            except Exception as e:
                st.error("Something went wrong during assembly.")
                st.text(traceback.format_exc())