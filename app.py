import streamlit as st
import requests
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import base64

# Expand layout to fit a grid
st.set_page_config(layout="wide", page_title="My Vinyl Collection", page_icon="vinyl.png")

# --- START OF MOBILE ICON HACK ---
try:
    with open("vinyl.png", "rb") as f:
        encoded = base64.b64encode(f.read()).decode()
    
    st.markdown(
        f"""
        <img src="dummy" onerror="
            var old = document.querySelector('link[rel=apple-touch-icon]');
            if (old) old.remove();
            var link = document.createElement('link');
            link.rel = 'apple-touch-icon';
            link.href = 'data:image/png;base64,{encoded}';
            document.head.appendChild(link);
        " style="display:none;">
        """,
        unsafe_allow_html=True,
    )
except Exception:
    pass
# --- END OF MOBILE ICON HACK ---

# 1. Connect to Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- STATE MANAGEMENT FIX ---
# Load from Google Sheets ONLY once when the app opens, then use local memory
if "vinyl_db" not in st.session_state:
    df = conn.read(worksheet="Sheet1", ttl=0)
    
    if "Cover_URL" not in df.columns:
        df["Cover_URL"] = ""
    if "Rating" not in df.columns:
        df["Rating"] = "Unrated"
        
    st.session_state["vinyl_db"] = df.dropna(subset=["Barcode"]).reset_index(drop=True)

DISCOGS_TOKEN = st.secrets["DISCOGS_TOKEN"]
USER_AGENT = "MyVinylScannerApp/1.0"

# Initialize other session states
if "show_manual" not in st.session_state:
    st.session_state["show_manual"] = False
if "failed_barcode" not in st.session_state:
    st.session_state["failed_barcode"] = ""
if "edit_row" not in st.session_state:
    st.session_state["edit_row"] = None

# Split screen into Left (Forms) and Right (Gallery)
col_left, col_right = st.columns([1, 2])

with col_left:
    st.subheader("Add New Record")
    
    tab_scan, tab_text = st.tabs(["📷 Scan Barcode", "🔍 Search by Name"])
    
    # --- TAB 1: BARCODE SCANNER ---
    with tab_scan:
        with st.form("scanner_form", clear_on_submit=True):
            barcode = st.text_input("Scan Barcode Here:")
            submitted_barcode = st.form_submit_button("Search & Save")

        if submitted_barcode and barcode:
            with st.spinner(f"Querying Discogs for {barcode}..."):
                url = f"https://api.discogs.com/database/search?barcode={barcode}&token={DISCOGS_TOKEN}"
                response = requests.get(url, headers={"User-Agent": USER_AGENT})
                
                if response.status_code == 200:
                    results = response.json().get("results", [])
                    if results:
                        match = results[0]
                        title_split = match.get("title", "Unknown - Unknown").split(" - ", 1)
                        artist = title_split[0]
                        album = title_split[1] if len(title_split) > 1 else match.get("title")
                        year = match.get("year", "Unknown")
                        genre = ", ".join(match.get("genre", []))
                        cover_url = match.get("cover_image", "") 
                        
                        new_row = pd.DataFrame([{
                            "Barcode": barcode, "Artist": artist, "Album": album,
                            "Year": year, "Genre": genre, "Cover_URL": cover_url, "Rating": "Unrated"
                        }])
                        
                        # Update local memory FIRST, then backup to Google
                        st.session_state["vinyl_db"] = pd.concat([st.session_state["vinyl_db"], new_row], ignore_index=True)
                        conn.update(worksheet="Sheet1", data=st.session_state["vinyl_db"])
                        
                        st.session_state["show_manual"] = False
                        st.session_state["failed_barcode"] = ""
                        st.session_state["edit_row"] = None
                        st.success(f"Successfully saved: **{artist} - {album}**")
                    else:
                        st.session_state["failed_barcode"] = barcode
                        st.session_state["show_manual"] = True
                        st.error("Barcode not found. Fill out the manual form below:")
                else:
                    st.error(f"API Error: {response.status_code}")

    # --- TAB 2: TEXT SEARCH ---
    with tab_text:
        with st.form("text_search_form", clear_on_submit=True):
            search_artist = st.text_input("Artist Name (e.g., Fleetwood Mac):")
            search_title = st.text_input("Album Title (e.g., Rumours):")
            submitted_text = st.form_submit_button("Search & Save")
            
        if submitted_text and (search_artist or search_title):
            with st.spinner(f"Querying Discogs for '{search_title}' by '{search_artist}'..."):
                params = {"artist": search_artist, "title": search_title, "format": "vinyl", "token": DISCOGS_TOKEN}
                response = requests.get("https://api.discogs.com/database/search", headers={"User-Agent": USER_AGENT}, params=params)
                
                if response.status_code == 200:
                    results = response.json().get("results", [])
                    if results:
                        match = results[0]
                        title_split = match.get("title", "Unknown - Unknown").split(" - ", 1)
                        artist = title_split[0]
                        album = title_split[1] if len(title_split) > 1 else match.get("title")
                        year = match.get("year", "Unknown")
                        genre = ", ".join(match.get("genre", []))
                        cover_url = match.get("cover_image", "") 
                        
                        new_row = pd.DataFrame([{
                            "Barcode": "N/A", "Artist": artist, "Album": album,
                            "Year": year, "Genre": genre, "Cover_URL": cover_url, "Rating": "Unrated"
                        }])
                        
                        # Update local memory FIRST, then backup to Google
                        st.session_state["vinyl_db"] = pd.concat([st.session_state["vinyl_db"], new_row], ignore_index=True)
                        conn.update(worksheet="Sheet1", data=st.session_state["vinyl_db"])
                        
                        st.session_state["show_manual"] = False
                        st.session_state["edit_row"] = None
                        st.success(f"Successfully saved: **{artist} - {album}**")
                    else:
                        st.session_state["show_manual"] = True
                        st.error("No vinyl records found matching that search. Fill out the manual form below:")
                else:
                    st.error(f"API Error: {response.status_code}")

    st.write("---")

    # --- MANUAL ENTRY FALLBACK ---
    with st.expander("✏ Add Record Manually", expanded=st.session_state["show_manual"]):
        with st.form("manual_entry_form", clear_on_submit=True):
            m_barcode = st.text_input("Barcode (Optional):", value=st.session_state["failed_barcode"])
            m_artist = st.text_input("Artist Name *")
            m_album = st.text_input("Album Title *")
            m_year = st.text_input("Year:")
            m_genre = st.text_input("Genre:")
            m_cover = st.text_input("Album Cover Photo URL:")
            m_rating = st.selectbox("Rating:", options=["Unrated", "⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"])
            
            if st.form_submit_button("Save Manual Record"):
                if m_artist and m_album:
                    manual_row = pd.DataFrame([{
                        "Barcode": m_barcode if m_barcode else "N/A",
                        "Artist": m_artist, "Album": m_album,
                        "Year": m_year if m_year else "Unknown",
                        "Genre": m_genre if m_genre else "Unknown",
                        "Cover_URL": m_cover, "Rating": m_rating
                    }])
                    
                    # Update local memory FIRST, then backup to Google
                    st.session_state["vinyl_db"] = pd.concat([st.session_state["vinyl_db"], manual_row], ignore_index=True)
                    conn.update(worksheet="Sheet1", data=st.session_state["vinyl_db"])
                    
                    st.session_state["show_manual"] = False
                    st.session_state["failed_barcode"] = ""
                    st.session_state["edit_row"] = None
                    
                    st.success(f"Manually saved: **{m_artist} - {m_album}**")
                else:
                    st.error("Artist and Album Title are required.")

with col_right:
    st.subheader(f"My Collection ({len(st.session_state['vinyl_db'])} Records)")
    
    # --- VISUAL GALLERY ---
    if not st.session_state["vinyl_db"].empty:
        grid_cols = st.columns(4)
        
        for index, row in st.session_state["vinyl_db"].iterrows():
            with grid_cols[index % 4]:
                
                # Check if this specific record is in "Edit Mode"
                if st.session_state["edit_row"] == index:
                    st.markdown("**Editing Record...**")
                    edit_artist = st.text_input("Artist", value=row["Artist"], key=f"edit_art_{index}")
                    edit_album = st.text_input("Album", value=row["Album"], key=f"edit_alb_{index}")
                    
                    rating_options = ["Unrated", "⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]
                    current_rating = row.get("Rating", "Unrated")
                    if pd.isna(current_rating) or current_rating not in rating_options:
                        current_rating = "Unrated"
                        
                    edit_rating = st.selectbox("Rating", options=rating_options, index=rating_options.index(current_rating), key=f"edit_rat_{index}")
                    
                    col_save, col_cancel = st.columns(2)
                    with col_save:
                        if st.button("💾 Save", key=f"save_{index}"):
                            st.session_state["vinyl_db"].at[index, "Artist"] = edit_artist
                            st.session_state["vinyl_db"].at[index, "Album"] = edit_album
                            st.session_state["vinyl_db"].at[index, "Rating"] = edit_rating
                            conn.update(worksheet="Sheet1", data=st.session_state["vinyl_db"])
                            st.session_state["edit_row"] = None
                            st.rerun()
                    with col_cancel:
                        if st.button("❌ Cancel", key=f"cancel_{index}"):
                            st.session_state["edit_row"] = None
                            st.rerun()
                            
                else:
                    # View Mode UI
                    if pd.notna(row.get("Cover_URL")) and str(row["Cover_URL"]).startswith("http"):
                        st.image(row["Cover_URL"], use_container_width=True)
                    else:
                        st.write("💿 No Cover Art")
                    
                    st.markdown(f"**{row['Album']}**")
                    st.caption(f"{row['Artist']}")
                    
                    display_rating = row.get("Rating", "Unrated")
                    if display_rating != "Unrated":
                        st.write(display_rating)
                    
                    if st.button("✏️ Edit Record", key=f"edit_{index}"):
                        st.session_state["edit_row"] = index
                        st.rerun()
                        
                    if st.button("🗑️️ Delete", key=f"delete_{index}"):
                        # Drop row and reset index so grid placement remains stable
                        st.session_state["vinyl_db"] = st.session_state["vinyl_db"].drop(index).reset_index(drop=True)
                        conn.update(worksheet="Sheet1", data=st.session_state["vinyl_db"])
                        st.session_state["edit_row"] = None
                        st.rerun()