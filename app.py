import streamlit as st
import os
import json
import urllib.request
import numpy as np
import traceback
import asyncio
import time
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel
from google import genai
from google.genai import types
from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip, ImageClip
from gradio_client import Client
from rembg import remove

# ----------------------------------------------------------
# 1. PYDANTIC GUARDRAILS
# ----------------------------------------------------------
class AdPackage(BaseModel):
    subtitle_1: str
    subtitle_2: str
    subtitle_3: str
    voiceover_text: str
    ai_video_prompt: str
    captions: str
    hashtags: str

# ----------------------------------------------------------
# 2. STREAMLIT APP LAYOUT
# ----------------------------------------------------------
st.set_page_config(page_title="Reelify Pro", page_icon="🎬", layout="centered")

st.markdown(
    """
    <div style="text-align: center; margin-top: -30px; margin-bottom: 20px;">
        <div style="font-size: 55px; font-weight: 800; color: #E53935; font-family: 'Helvetica Neue', Arial, sans-serif; letter-spacing: -1px;">
            <span style="font-family: 'Georgia', serif; font-size: 72px; font-style: italic; color: #B71C1C; font-weight: 900; margin-right: -6px;">R</span>eelify <span style="font-size: 24px; color: #FFB300;">PRO</span>
        </div>
        <p style="font-size: 15px; color: #666666;">Studio-Grade Affiliate Ad Generator</p>
    </div>
    """,
    unsafe_allow_html=True
)

st.sidebar.header("🔑 App Settings")
gemini_key = st.sidebar.text_input("Enter GEMINI_API_KEY", type="password")

st.subheader("📦 Step 1: Product & Vision")
product_input = st.text_input("Product Name", placeholder="e.g. Good Molecules Azelaic Acid Cleanser")
user_prompt = st.text_area("Describe the Video/Model", placeholder="e.g. A gorgeous female model in a luxury bathroom, cinematic lighting, 4k.")

st.subheader("📸 Step 2: Upload Product Image (For Auto-Cutout)")
uploaded_file = st.file_uploader("Upload an image with a white/solid background. The AI will magically remove the background!", type=['png', 'jpg', 'jpeg'])

st.subheader("🎙️ Step 3: Voice Style")
voice_region = st.selectbox("Voice Accent:", ["United States", "United Kingdom", "India", "Australia"])
voice_gender = st.selectbox("Voice Gender:", ["Female", "Male"])

# ----------------------------------------------------------
# 3. BACKEND PIPELINE UTILITIES
# ----------------------------------------------------------
def get_custom_font(font_size=60):
    font_path = "Anton-Regular.ttf"
    if not os.path.exists(font_path):
        try:
            url = "https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf"
            urllib.request.urlretrieve(url, font_path)
        except Exception:
            return ImageFont.load_default()
    return ImageFont.truetype(font_path, font_size)

def add_overlays_to_frame(frame, text, sticker_img=None):
    img = Image.fromarray(frame).convert("RGBA")
    target_w, target_h = img.size
    
    if sticker_img:
        sticker_w = int(target_w * 0.45)
        sticker_h = int(sticker_img.height * (sticker_w / sticker_img.width))
        sticker_resized = sticker_img.resize((sticker_w, sticker_h), Image.Resampling.LANCZOS)
        
        paste_x = (target_w - sticker_w) // 2
        paste_y = int(target_h * 0.25)
        img.paste(sticker_resized, (paste_x, paste_y), sticker_resized)

    draw = ImageDraw.Draw(img, "RGBA")
    font = get_custom_font(65)
    font_color = (255, 223, 0, 255) 

    words = text.split()
    lines, current_line = [], []
    for word in words:
        test_line = " ".join(current_line + [word])
        w = draw.textbbox((0, 0), test_line, font=font)[2]
        if w < (target_w - 60):
            current_line.append(word)
        else:
            lines.append(" ".join(current_line))
            current_line = [word]
    if current_line: lines.append(" ".join(current_line))
    
    wrapped_text = "\n".join(lines)
    center_x = target_w // 2
    y_pos = int(target_h * 0.70)

    draw.multiline_text((center_x, y_pos), wrapped_text, font=font, fill=font_color, stroke_width=8, stroke_fill=(0, 0, 0, 255), anchor="ma", align="center")
    return np.array(img.convert("RGB"))

async def generate_neural_voiceover(text, region, gender, output_path="temp_voiceover.mp3"):
    voice_map = {
        "United States_Female": "en-US-EmmaMultilingualNeural",
        "United States_Male": "en-US-BrianNeural",
        "United Kingdom_Female": "en-GB-SoniaNeural",
        "United Kingdom_Male": "en-GB-RyanNeural",
        "India_Female": "en-IN-NeerjaNeural",
        "India_Male": "en-IN-PrabhatNeural",
        "Australia_Female": "en-AU-NatashaNeural",
    }
    voice_actor = voice_map.get(f"{region}_{gender}", "en-US-EmmaMultilingualNeural")
    communicate = edge_tts.Communicate(text, voice_actor)
    await communicate.save(output_path)
    return output_path

def generate_huggingface_video(ai_video_prompt):
    try:
        st.info("📡 Connecting to Hugging Face Open-Source Video Servers... (This takes a few minutes)")
        client = Client("ByteDance/AnimateDiff-Lightning")
        result = client.predict(
            ai_video_prompt, "bad quality, cartoon, blurry, deformed", 1, 512, 768, api_name="/generate_image"
        )
        return result
    except Exception as e:
        st.warning("HF Server busy. Generating beautiful aesthetic fallback background instead.")
        return None

# ----------------------------------------------------------
# 4. EXECUTION ACTION
# ----------------------------------------------------------
if st.button("🚀 Generate Pro Ad Video"):
    if not product_input or not gemini_key:
        st.error("Please enter a valid GEMINI_API_KEY and Product Name!")
    else:
        with st.spinner("AI Brain is orchestrating the ad..."):
            try:
                temp_dir = "temp_assets"
                os.makedirs(temp_dir, exist_ok=True)
                
                sticker_img = None
                if uploaded_file:
                    st.info("✨ AI is removing the background from your product photo...")
                    input_path = os.path.join(temp_dir, uploaded_file.name)
                    with open(input_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    raw_img = Image.open(input_path)
                    sticker_img = remove(raw_img)

                st.info("🧠 AI is writing script and video generation blueprint...")
                client = genai.Client(api_key=gemini_key)
                prompt = f"Create a viral commercial ad package for '{product_input}'. User vibe: '{user_prompt}'. Max 30 words for voiceover. For the ai_video_prompt, describe a 4k vertical shot of a model."
                
                max_retries = 3
                pkg = None
                for attempt in range(max_retries):
                    try:
                        response = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json",
                                response_schema=AdPackage,
                            ),
                        )
                        pkg = json.loads(response.text)
                        break
                    except Exception as e:
                        if "503" in str(e) or "UNAVAILABLE" in str(e):
                            if attempt < max_retries - 1:
                                st.warning(f"Google servers busy. Retrying... (Attempt {attempt+1}/{max_retries})")
                                time.sleep(5)
                            else:
                                st.error("Google Gemini is overloaded. Please try again in 1 minute!")
                                st.stop()
                        else:
                            raise e

                subtitles = [pkg["subtitle_1"], pkg["subtitle_2"], pkg["subtitle_3"]]

                st.info("🎙️ Generating Neural Voiceover...")
                voice_path = "temp_voiceover.mp3"
                asyncio.run(generate_neural_voiceover(pkg["voiceover_text"], voice_region, voice_gender, voice_path))
                voice_clip = AudioFileClip(voice_path)
                target_duration = voice_clip.duration

                raw_video_path = generate_huggingface_video(pkg["ai_video_prompt"])
                
                if raw_video_path and os.path.exists(raw_video_path):
                    base_video = VideoFileClip(raw_video_path)
                    if base_video.duration < target_duration:
                        loops = int(np.ceil(target_duration / base_video.duration))
                        base_video = concatenate_videoclips([base_video] * loops).subclip(0, target_duration)
                    else:
                        base_video = base_video.subclip(0, target_duration)
                else:
                    # FIX: Solid aesthetic dark background that is 100% compatible with MoviePy v2
                    fallback_frame = np.zeros((1280, 720, 3), dtype=np.uint8)
                    fallback_frame[:, :] = [20, 20, 30] # Sleek dark navy
                    base_video = ImageClip(fallback_frame).with_duration(target_duration)

                st.info("🎬 Compositing Video, Product Sticker, and Subtitles...")
                scene_duration = target_duration / len(subtitles)
                clips = []
                
                for i in range(len(subtitles)):
                    sub_text = subtitles[i]
                    start_t = i * scene_duration
                    end_t = (i + 1) * scene_duration if i < len(subtitles) - 1 else target_duration
                    
                    subclipped = base_video.subclipped(start_t, end_t)
                    textured_clip = subclipped.fl(lambda get_frame, t, text=sub_text: add_overlays_to_frame(get_frame(t), text, sticker_img))
                    clips.append(textured_clip)

                final_clip = concatenate_videoclips(clips)
                final_clip = final_clip.with_audio(voice_clip)

                output_path = "output_live_model_ad.mp4"
                final_clip.write_videofile(output_path, fps=24, codec="libx264", audio=True)

                for c in clips: c.close()
                voice_clip.close()
                final_clip.close()
                base_video.close()

                st.success("🎉 Final Ad Completed!")
                st.video(output_path)
                with open(output_path, "rb") as file:
                    st.download_button("💾 Download Masterpiece", data=file, file_name="reelify_pro_ad.mp4", mime="video/mp4")
                
                st.code(f"{pkg['captions']}\n\n{pkg['hashtags']}")

            except Exception as e:
                st.error("Assembly Error.")
                st.text(traceback.format_exc())