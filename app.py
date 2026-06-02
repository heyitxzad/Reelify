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
from moviepy import ImageClip, VideoFileClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip

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

# Smart Presenter/Model Selection
st.subheader("👤 Choose Your Video Model & Style")
model_choice = st.selectbox(
    "Select the AI Presenter & Scene Background style for this video:",
    [
        "Skincare / Beauty Model (Female - Elegant Bathroom Background)",
        "Skincare / Grooming Model (Male - Clean Modern Background)",
        "Self-Improvement / Tech Vibe (Dynamic Abstract Background)",
        "My Own Uploaded Photos/Videos"
    ]
)

uploaded_files = []
if "My Own Uploaded Photos/Videos" in model_choice:
    uploaded_files = st.file_uploader("Upload your own photos or videos", accept_multiple_files=True, type=['png', 'jpg', 'jpeg', 'mp4', 'mov'])

# ----------------------------------------------------------
# 2. ADVANCED BACKEND PIPELINE
# ----------------------------------------------------------
# Downloads a high-quality bold font to prevent tiny unreadable text
def get_custom_font(font_size=55):
    font_path = "RobotoCondensed-Bold.ttf"
    if not os.path.exists(font_path):
        try:
            url = "https://github.com/google/fonts/raw/main/apache/robotocondensed/RobotoCondensed-Bold.ttf"
            urllib.request.urlretrieve(url, font_path)
        except Exception:
            return ImageFont.load_default()
    return ImageFont.truetype(font_path, font_size)

# Draw gorgeous TikTok style outlined subtitles
def draw_smart_text(image_path, text, styling):
    img = Image.open(image_path)
    target_w, target_h = 720, 1280
    img_ratio = img.width / img.height
    target_ratio = target_w / target_h
    
    # 1. Resize/Crop image to vertical 9:16
    if img_ratio > target_ratio:
        scale = target_h / img.height
        new_w = int(img.width * scale)
        img_final = img.resize((new_w, target_h), Image.Resampling.LANCZOS).crop(((new_w - target_w) // 2, 0, (new_w - target_w) // 2 + target_w, target_h))
    else:
        scale = target_w / img.width
        new_h = int(img.height * scale)
        img_final = img.resize((target_w, new_h), Image.Resampling.LANCZOS).crop((0, (new_h - target_h) // 2, target_w, (new_h - target_h) // 2 + target_h))

    draw = ImageDraw.Draw(img_final, "RGBA")
    font = get_custom_font(48) # Clean, bold advertising font size

    color_map = {"yellow": (255, 223, 0, 255), "white": (255, 255, 255, 255), "cyan": (0, 255, 255, 255)}
    font_color = color_map.get(styling.get("text_color"), (255, 255, 255, 255))
    text_style = styling.get("text_style", "tiktok_stroke")

    # Wrap subtitles
    words = text.split()
    lines, current_line = [], []
    for word in words:
        test_line = " ".join(current_line + [word])
        w = draw.textbbox((0, 0), test_line, font=font)[2]
        if w < (target_w - 120):
            current_line.append(word)
        else:
            lines.append(" ".join(current_line))
            current_line = [word]
    if current_line:
        lines.append(" ".join(current_line))
    
    wrapped_text = "\n".join(lines)
    text_h = draw.multiline_textbbox((0, 0), wrapped_text, font=font, align="center")[3]
    
    center_x = target_w // 2
    y_pos = int(target_h * 0.70) # Perfectly placed in bottom third

    if text_style == "tiktok_stroke":
        # Viral style: Bright text with bold black stroke
        draw.multiline_text((center_x, y_pos), wrapped_text, font=font, fill=font_color, stroke_width=6, stroke_fill=(0, 0, 0, 255), anchor="ma", align="center")
    elif text_style == "neon_glow":
        for offset in range(4, 0, -1):
            draw.multiline_text((center_x + offset, y_pos + offset), wrapped_text, font=font, fill=(0, 0, 0, 120), anchor="ma", align="center")
        draw.multiline_text((center_x, y_pos), wrapped_text, font=font, fill=font_color, anchor="ma", align="center")
    else: # classic_banner
        padding = 24
        draw.rectangle([(0, y_pos - 10), (target_w, y_pos + text_h + padding*2)], fill=(0, 0, 0, 160))
        draw.multiline_text((center_x, y_pos + padding - 10), wrapped_text, font=font, fill=font_color, anchor="ma", align="center")
        
    return img_final

# 3. Downloads premium royalty-free visual loops based on chosen model
MODEL_FOOTAGE_URLS = {
    "beauty_female": [
        "https://videos.pexels.com/video-files/3762413/3762413-uhd_1440_2732_25fps.mp4", # Washing face close up
        "https://videos.pexels.com/video-files/4041132/4041132-uhd_1440_2732_25fps.mp4", # Applying serum
        "https://videos.pexels.com/video-files/6001550/6001550-uhd_1440_2732_25fps.mp4"  # Healthy glowing smile
    ],
    "beauty_male": [
        "https://videos.pexels.com/video-files/8091890/8091890-uhd_1440_2732_25fps.mp4", # Male washing face
        "https://videos.pexels.com/video-files/8091901/8091901-uhd_1440_2732_25fps.mp4", # Inspecting skin in mirror
        "https://videos.pexels.com/video-files/8091910/8091910-uhd_1440_2732_25fps.mp4"  # Fresh clean look close up
    ],
    "tech_abstract": [
        "https://videos.pexels.com/video-files/3129957/3129957-uhd_1440_2732_25fps.mp4", # Abstract tech lines
        "https://videos.pexels.com/video-files/3141208/3141208-uhd_1440_2732_25fps.mp4", # Digital glowing matrix
        "https://videos.pexels.com/video-files/3209211/3209211-uhd_1440_2732_25fps.mp4"  # Dynamic liquid shapes
    ]
}

def download_model_assets(style_key, temp_dir="temp_assets"):
    os.makedirs(temp_dir, exist_ok=True)
    urls = MODEL_FOOTAGE_URLS.get(style_key, MODEL_FOOTAGE_URLS["beauty_female"])
    downloaded_paths = []
    
    for i, url in enumerate(urls):
        filename = f"model_clip_{i}.mp4"
        dest_path = os.path.join(temp_dir, filename)
        if not os.path.exists(dest_path):
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req) as response, open(dest_path, 'wb') as out_file:
                    out_file.write(response.read())
                downloaded_paths.append(dest_path)
            except Exception as e:
                print(f"Error downloading asset {i}: {e}")
        else:
            downloaded_paths.append(dest_path)
    return downloaded_paths

# Microsoft Neural Voice generator (Completely realistic)
async def generate_neural_voiceover(text, voice_gender, output_path="temp_voiceover.mp3"):
    # Select voice actor based on gender choice
    voice_actor = "en-US-EmmaMultilingualNeural" if voice_gender == "female" else "en-US-BrianNeural"
    communicate = edge_tts.Communicate(text, voice_actor)
    await communicate.save(output_path)
    return output_path

# ----------------------------------------------------------
# 3. RUN GENERATION ACTION
# ----------------------------------------------------------
if st.button("🚀 Generate High-Conversion Model Video"):
    if not product_input:
        st.error("Please enter your product name first!")
    elif "My Own" in model_choice and not uploaded_files:
        st.error("Please upload at least 2 product files!")
    else:
        with st.spinner("AI is directing your visual layout, synthesizing neural voice, and rendering video..."):
            try:
                # 1. Prepare assets
                temp_dir = "temp_assets"
                os.makedirs(temp_dir, exist_ok=True)
                
                # Setup correct style assets
                if "Female" in model_choice:
                    st.info("Directing Elegant Female Model...")
                    saved_assets = download_model_assets("beauty_female", temp_dir)
                    voice_gender = "female"
                elif "Male" in model_choice:
                    st.info("Directing Clean Grooming Male Model...")
                    saved_assets = download_model_assets("beauty_male", temp_dir)
                    voice_gender = "male"
                elif "Abstract" in model_choice:
                    st.info("Directing Abstract Tech Layout...")
                    saved_assets = download_model_assets("tech_abstract", temp_dir)
                    voice_gender = "male"
                else:
                    st.info("Using your uploaded custom assets...")
                    voice_gender = "female"
                    # Clean previous uploads
                    for file in os.listdir(temp_dir):
                        if "model_clip" not in file:
                            os.remove(os.path.join(temp_dir, file))
                    
                    saved_assets = []
                    for uploaded_file in uploaded_files:
                        path = os.path.join(temp_dir, uploaded_file.name)
                        with open(path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                        saved_assets.append(path)
                    saved_assets.sort()

                # 2. Call Gemini for dynamic copy
                if not gemini_key:
                    pkg = {
                        "script": [
                            "Sensitive, red, or irritated skin?",
                            "This calming formula deeply cleanses without stripping.",
                            "Get clear, glowing skin today! Link in bio."
                        ],
                        "voiceover_text": f"If you struggle with sensitive, red, or oily skin, you need to stop stripping your barrier. Try this soothing azelaic acid cleanser from Good Molecules. It clears irritation instantly. Link in bio!",
                        "captions": f"Heal your skin barrier with Good Molecules. Link in bio.",
                        "hashtags": "#skincare #beauty #glowingskin",
                        "styling": {"text_color": "yellow", "text_style": "tiktok_stroke"}
                    }
                else:
                    client = genai.Client(api_key=gemini_key)
                    prompt = f'Create a viral, high-energy vertical video marketing ad script for "{product_input}". Structure it as a conversational story. Output raw JSON only.'
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
                    current_time = i * scene_duration
                    sub_idx = min(int(current_time / sub_display_time), num_subs - 1)
                    sub_text = pkg["script"][sub_idx]
                    
                    # If asset is a video, open, crop, apply subtitle, and save frame-by-frame
                    if asset_path.lower().endswith(('.mp4', '.mov')):
                        video_clip = VideoFileClip(asset_path).subclip(0, scene_duration)
                        # Extract first frame as a base, apply text, turn into clip
                        frame_img = Image.fromarray(video_clip.get_frame(1.0))
                        # Save frame image temporarily to render
                        temp_frame_path = "temp_frame.jpg"
                        frame_img.save(temp_frame_path)
                        processed_img = draw_smart_text(temp_frame_path, sub_text, pkg["styling"])
                        clip = ImageClip(np.array(processed_img)).with_duration(scene_duration)
                        video_clip.close()
                    else:
                        processed_img = draw_smart_text(asset_path, sub_text, pkg["styling"])
                        clip = ImageClip(np.array(processed_img)).with_duration(scene_duration)
                    
                    clips.append(clip)

                # Concatenate
                final_clip = concatenate_videoclips(clips, method="compose")
                
                # Add audio track
                audio_tracks = [voice_clip.with_volume_scaled(1.0)]
                final_clip = final_clip.with_audio(CompositeAudioClip(audio_tracks))

                output_path = "output_viral_video.mp4"
                final_clip.write_videofile(output_path, fps=24, codec="libx264", audio=True)
                
                # Close files
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