import streamlit as st
import os
import json
import urllib.request
import numpy as np
import traceback
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS
from google import genai
from moviepy.editor import ImageClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip

# ----------------------------------------------------------
# 1. STREAMLIT APP LAYOUT & DESIGNS
# ----------------------------------------------------------
st.set_page_config(page_title="AI Viral Video Generator", page_icon="🎬", layout="centered")

st.title("🎬 Smart AI Viral Video Editor")
st.write("Upload product photos, enter your keyword, and let the AI build a styled, voiced-over video automatically!")

# Sidebar for credentials and configurations
st.sidebar.header("🔑 App Settings")
gemini_key = st.sidebar.text_input("Enter GEMINI_API_KEY", type="password", help="Get a free key from Google AI Studio.")

# Main Inputs
product_input = st.text_input("Affiliate Product / Keyword", placeholder="e.g. Good Molecules Azelaic Acid Cleanser")
uploaded_files = st.file_uploader("Upload Product Photos or Videos", accept_multiple_files=True, type=['png', 'jpg', 'jpeg', 'mp4', 'mov'])

# ----------------------------------------------------------
# 2. BACKEND PIPELINE LOGIC
# ----------------------------------------------------------
# Define helper rendering functions
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
    font = ImageFont.load_default() # Fallback safe font for web servers

    color_map = {"yellow": (255, 223, 0, 255), "white": (255, 255, 255, 255), "cyan": (0, 255, 255, 255)}
    font_color = color_map.get(styling.get("text_color"), (255, 255, 255, 255))
    text_style = styling.get("text_style", "tiktok_stroke")

    # Text wrapping
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
                # 1. Clean and save uploaded files to a temporary directory
                temp_dir = "temp_assets"
                os.makedirs(temp_dir, exist_ok=True)
                # Remove any existing files in temporary folder
                for file in os.listdir(temp_dir):
                    os.remove(os.path.join(temp_dir, file))
                
                saved_assets = []
                for uploaded_file in uploaded_files:
                    path = os.path.join(temp_dir, uploaded_file.name)
                    with open(path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    saved_assets.append(path)
                saved_assets.sort()

                # 2. Call Gemini for Script & styling package
                # Fallback template if key is missing
                if not gemini_key:
                    pkg = {
                        "script": ["Looking for a game-changer?", f"This {product_input} upgrades your routine instantly.", "Get yours today! Link in bio!"],
                        "voiceover_text": f"If you are looking for the absolute best {product_input}, you need to stop scrolling. Grab yours now at the link in bio.",
                        "captions": f"Upgrade your lifestyle with {product_input}! Link in bio.",
                        "hashtags": "#musthave #viralproduct #affiliate",
                        "styling": {"text_color": "yellow", "text_style": "tiktok_stroke", "music_genre": "lofi", "transition_effect": "crossfade"}
                    }
                else:
                    client = genai.Client(api_key=gemini_key)
                    prompt = f'Create a viral vertical video marketing package for: "{product_input}". Output raw JSON only.'
                    response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    text = response.text.strip()
                    # Strip formatting codeblocks
                    if text.startswith("```json"): text = text[7:]
                    elif text.startswith("```"): text = text[3:]
                    if text.endswith("```"): text = text[:-3]
                    pkg = json.loads(text.strip())

                # 3. Create Voiceover
                voice_path = "temp_voiceover.mp3"
                tts = gTTS(text=pkg["voiceover_text"], lang='en', slow=False)
                tts.save(voice_path)

                # 4. Compile Video Scenes
                total_duration = AudioFileClip(voice_path).duration
                scene_duration = total_duration / len(saved_assets)
                
                clips = []
                num_subs = len(pkg["script"])
                sub_display_time = total_duration / num_subs

                for i, asset_path in enumerate(saved_assets):
                    current_time = i * scene_duration
                    sub_idx = min(int(current_time / sub_display_time), num_subs - 1)
                    sub_text = pkg["script"][sub_idx]
                    
                    processed_img = draw_smart_text(asset_path, sub_text, pkg["styling"])
                    clip = ImageClip(np.array(processed_img)).set_duration(scene_duration)
                    if pkg["styling"].get("transition_effect") == "crossfade":
                        clip = clip.crossfadein(0.2).crossfadeout(0.2)
                    clips.append(clip)

                final_clip = concatenate_videoclips(clips, method="compose", padding=-0.2)
                
                # Add audio track
                audio_tracks = [AudioFileClip(voice_path).volumex(1.0)]
                final_clip = final_clip.set_audio(CompositeAudioClip(audio_tracks))

                output_path = "output_viral_video.mp4"
                final_clip.write_videofile(output_path, fps=24, codec="libx264", audio=True)
                
                # Close files to free memory
                for c in clips: c.close()
                final_clip.close()

                # ----------------------------------------------------------
                # 4. DISPLAY THE OUTPUTS IN APP
                # ----------------------------------------------------------
                st.success("🎉 Video Successfully Compiled!")
                
                # Display Video Player
                st.video(output_path)
                
                # Download Button for the MP4 file
                with open(output_path, "rb") as file:
                    st.download_button(
                        label="💾 Download Video File",
                        data=file,
                        file_name="viral_ad.mp4",
                        mime="video/mp4"
                    )
                
                # Display Social Captions
                st.subheader("📝 Proposed Social Caption & Hashtags")
                st.code(f"{pkg['captions']}\n\n{pkg['hashtags']}")

            except Exception as e:
                st.error("Something went wrong during assembly.")
                st.text(traceback.format_exc())
