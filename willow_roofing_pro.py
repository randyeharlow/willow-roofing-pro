import streamlit as st
import requests
import math
from geopy.geocoders import Nominatim
from fpdf import FPDF
import datetime
import pandas as pd
import plotly.graph_objects as go
import cv2
import numpy as np
from PIL import Image
import tempfile
import os

# Initialize session state for totals and flags
if 'total_sqft' not in st.session_state:
    st.session_state.total_sqft = 0
    st.session_state.total_perimeter = 0
    st.session_state.total_hip_ridge = 0
    st.session_state.total_valley = 0
    st.session_state.report_generated = False
    st.session_state.jobs = []

st.set_page_config(page_title="Willow Roofing Pro", layout="wide")
st.title("🌟 Willow Roofing Pro — Instant Roof Measurements")
st.markdown("Better, faster, and cheaper than EagleView or Hover. Unlimited reports.")

# Branding
col1, col2 = st.columns([1, 4])
with col1:
    logo_file = st.file_uploader("Upload Logo (optional)", type=["png", "jpg"])
    if logo_file:
        with open("logo.png", "wb") as f:
            f.write(logo_file.getbuffer())
        st.image("logo.png", width=120)
with col2:
    company_name = st.text_input("Company Name", value="Willow Roofing")

api_key = st.text_input("Google API Key (Solar + Static Maps enabled)", type="password")

# Job Management
st.sidebar.header("Job Addresses")
address = st.text_input("Add Property Address", placeholder="123 Main St, Greenbrier, TN 37073")
if st.button("➕ Add to Job"):
    if address.strip():
        st.session_state.jobs.append(address.strip())
        st.success(f"Added: {address}")

for i, addr in enumerate(st.session_state.jobs):
    col1, col2 = st.sidebar.columns([4, 1])
    col1.write(f"{i+1}. {addr}")
    if col2.button("🗑️", key=f"del_{i}"):
        del st.session_state.jobs[i]
        st.rerun()

if st.button("🚀 Generate Full Report") and api_key and st.session_state.jobs:
    st.session_state.report_generated = False
    st.session_state.total_sqft = 0
    st.session_state.total_perimeter = 0
    st.session_state.total_hip_ridge = 0
    st.session_state.total_valley = 0

    all_data = []
    progress = st.progress(0)

    for idx, addr in enumerate(st.session_state.jobs):
        with st.spinner(f"Processing {addr}..."):
            try:
                geolocator = Nominatim(user_agent="willow_roofing_app")
                loc = geolocator.geocode(addr, timeout=10)
                if not loc:
                    st.warning(f"Could not geocode: {addr}")
                    continue
                lat, lng = loc.latitude, loc.longitude

                # Google Solar API call
                url = f"https://solar.googleapis.com/v1/buildingInsights:findClosest?location.latitude={lat}&location.longitude={lng}&requiredQuality=HIGH&key={api_key}"
                resp = requests.get(url)
                if resp.status_code != 200:
                    st.error(f"API error for {addr}: {resp.status_code}")
                    continue
                data = resp.json()

                solar = data.get("solarPotential", {})
                whole = solar.get("wholeRoofStats", {})
                area_sqft = round(whole.get("areaMeters2", 0) * 10.7639)

                segments = solar.get("roofSegmentStats", [])
                perimeter_ft = 0
                hip_ridge_ft = 0
                valley_ft = 0

                for seg in segments:
                    bb = seg.get("boundingBox", {})
                    sw, ne = bb.get("sw", {}), bb.get("ne", {})
                    if sw and ne:
                        lat_diff = abs(ne["latitude"] - sw["latitude"]) * 111320
                        lng_diff = abs(ne["longitude"] - sw["longitude"]) * 111320 * math.cos(math.radians(lat))
                        perimeter_ft += 2 * (lat_diff + lng_diff) * 3.28084  # rough meters to feet

                    pitch_rad = math.radians(seg.get("pitchDegrees", 30))
                    sloped = 1 / math.cos(pitch_rad) if abs(pitch_rad) < math.pi/2 else 1
                    seg_area = seg.get("stats", {}).get("areaMeters2", 0) * 10.7639
                    hip_ridge_ft += seg_area * 0.18 * sloped
                    valley_ft += seg_area * 0.09 * sloped

                all_data.append({
                    "Address": addr,
                    "Sq Ft": area_sqft,
                    "Planes": len(segments),
                    "Perimeter ft": round(perimeter_ft),
                    "Hips/Ridges ft": round(hip_ridge_ft),
                    "Valleys ft": round(valley_ft)
                })

                st.session_state.total_sqft += area_sqft
                st.session_state.total_perimeter += perimeter_ft
                st.session_state.total_hip_ridge += hip_ridge_ft
                st.session_state.total_valley += valley_ft

                # Satellite preview
                static_url = f"https://maps.googleapis.com/maps/api/staticmap?center={lat},{lng}&zoom=20&size=600x300&maptype=satellite&key={api_key}"
                st.image(static_url, caption=addr)

            except Exception as e:
                st.error(f"Error with {addr}: {str(e)}")

        progress.progress((idx + 1) / len(st.session_state.jobs))

    if all_data:
        st.session_state.report_generated = True
        st.success("Report complete!")

        # Dashboard
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Area", f"{st.session_state.total_sqft:,.0f} sq ft")
        col2.metric("Perimeter", f"{round(st.session_state.total_perimeter):,} ft")
        col3.metric("Hips + Ridges", f"{round(st.session_state.total_hip_ridge):,} ft")
        col4.metric("Valleys", f"{round(st.session_state.total_valley):,} ft")

        st.dataframe(pd.DataFrame(all_data), use_container_width=True)

        # Pricing
        st.subheader("Pricing & Profit")
        shingle_cost = st.number_input("Shingles $/square", value=45.0, step=1.0)
        labor_sqft = st.number_input("Labor $/sq ft", value=3.75, step=0.25)
        margin_pct = st.slider("Profit + Overhead Margin %", 30, 150, 85)

        cost_materials = (st.session_state.total_sqft / 100) * shingle_cost
        cost_labor = st.session_state.total_sqft * labor_sqft
        total_cost = cost_materials + cost_labor
        sell_price = total_cost * (1 + margin_pct / 100)

        col1, col2 = st.columns(2)
        col1.metric("Total Cost", f"${total_cost:,.0f}")
        col2.metric("Sell Price", f"${sell_price:,.0f}")
        profit = sell_price - total_cost
        st.metric("Profit", f"${profit:,.0f}", delta=f"{round(profit / total_cost * 100) if total_cost > 0 else 0}%")

        # PDF export (simple version)
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"{company_name} Roof Report - {datetime.date.today()}", ln=1, align="C")
        pdf.cell(200, 10, txt=f"Total Area: {st.session_state.total_sqft:,.0f} sq ft", ln=1)
        pdf.output("report.pdf")
        with open("report.pdf", "rb") as f:
            st.download_button("Download PDF Report", f, "willow_report.pdf")

st.info("Enter your Google API key and addresses above, then generate the report.")
st.caption("Willow Roofing — Greenbrier, TN | Powered by Grok")
