import streamlit as st
import requests
import pandas as pd
from streamlit_gsheets import GSheetsConnection

# Expand layout to fit a grid
st.set_page_config(layout="wide", page_title="My Vinyl Collection")
st.title("💿 Vinyl Database Scanner")

# 1. Connect to Google Sheets (ttl=0 forces fresh data)
conn = st.connection("gsheets", type=GSheetsConnection)
existing_data = conn.read(worksheet="Sheet1", ttl=0)

# Clean data: Ensure missing columns exist and drop completely empty rows
if "Cover_URL" not in existing_data.columns:
    existing_data["Cover_URL"] = ""
if "Rating" not in existing_data.columns:
    existing_data["Rating"] = "Unrated"
    
existing_data = existing_data.dropna(subset=["Barcode"]).reset_index(drop=True)

DISCOGS_TOKEN = st.secrets["DISCOGS_TOKEN"]
USER_AGENT = "MyVinylScannerApp/1.0"

# Initialize session states
if "show_manual" not in st.session_state:
    st.session_state["show_manual"] = False
if "failed_barcode" not in st.session_state:
    st.session_state["failed_barcode"] = ""
if "edit_row" not in st.session_state:
    st.session_state["edit_row"] = None # Tracks which record is being edited

# Split screen into Left (Scanner & Manual Entry) and Right (Gallery)
col_left, col_right = st.columns([1, 2])

with col_left:
    st.subheader("Scan New Record")
    
    # 2. Scanner Interface
    with st.form("scanner_form", clear_on_submit=True):
        barcode = st.text_input("Scan Barcode Here:")
        submitted = st.form_submit_button("Search & Save")

    # 3. Lookup and Save Logic
    if submitted and barcode:
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
                        "Barcode": barcode,
                        "Artist": artist,
                        "Album": album,
                        "Year": year,
                        "Genre": genre,
                        "Cover_URL": cover_url,
                        "Rating": "Unrated"
                    }])
                    
                    existing_data = pd.concat([existing_data, new_row], ignore_index=True)
                    conn.update(worksheet="Sheet1", data=existing_data)
                    
                    st.session_state["show_manual"] = False
                    st.session_state["failed_barcode"] = ""
                    st.session_state["edit_row"] = None # Close any open edits
                    
                    st.success(f"Successfully saved: **{artist} - {album}**")
                else:
                    st.session_state["failed_barcode"] = barcode
                    st.session_state["show_manual"] = True
                    st.error("Barcode not found in Discogs. Fill out the manual form below:")
            else:
                st.error(f"API Error: {response.status_code}")

    st.write("---")

    # 4. Manual Entry Form (Expander)
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
                        "Artist": m_artist,
                        "Album": m_album,
                        "Year": m_year if m_year else "Unknown",
                        "Genre": m_genre if m_genre else "Unknown",
                        "Cover_URL": m_cover,
                        "Rating": m_rating
                    }])
                    
                    existing_data = pd.concat([existing_data, manual_row], ignore_index=True)
                    conn.update(worksheet="Sheet1", data=existing_data)
                    
                    st.session_state["show_manual"] = False
                    st.session_state["failed_barcode"] = ""
                    st.session_state["edit_row"] = None
                    
                    st.success(f"Manually saved: **{m_artist} - {m_album}**")
                    st.rerun()
                else:
                    st.error("Artist and Album Title are required.")

with col_right:
    st.subheader(f"My Collection ({len(existing_data)} Records)")
    
    # 5. Display the collection as a visual grid
    if not existing_data.empty:
        grid_cols = st.columns(4)
        
        for index, row in existing_data.iterrows():
            with grid_cols[index % 4]:
                
                # Check if this specific record is in "Edit Mode"
                if st.session_state["edit_row"] == index:
                    # EDIT MODE UI
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
                            existing_data.at[index, "Artist"] = edit_artist
                            existing_data.at[index, "Album"] = edit_album
                            existing_data.at[index, "Rating"] = edit_rating
                            conn.update(worksheet="Sheet1", data=existing_data)
                            st.session_state["edit_row"] = None
                            st.rerun()
                    with col_cancel:
                        if st.button("❌ Cancel", key=f"cancel_{index}"):
                            st.session_state["edit_row"] = None
                            st.rerun()
                            
                else:
                    # VIEW MODE UI (Default)
                    if pd.notna(row.get("Cover_URL")) and str(row["Cover_URL"]).startswith("http"):
                        st.image(row["Cover_URL"], use_container_width=True)
                    else:
                        st.write("💿 No Cover Art")
                    
                    st.markdown(f"**{row['Album']}**")
                    st.caption(f"{row['Artist']}")
                    
                    # Display rating as plain text instead of a dropdown
                    display_rating = row.get("Rating", "Unrated")
                    if display_rating != "Unrated":
                        st.write(display_rating)
                    
                    # Edit & Delete Buttons
                    if st.button("✏️ Edit Record", key=f"edit_{index}"):
                        st.session_state["edit_row"] = index
                        st.rerun()
                        
                    if st.button("🗑️ Delete", key=f"delete_{index}"):
                        existing_data = existing_data.drop(index)
                        conn.update(worksheet="Sheet1", data=existing_data)
                        st.session_state["edit_row"] = None # Reset edit state to prevent UI glitches
                        st.rerun()