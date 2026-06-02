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
        img.paste(sticker_resized, (paste_