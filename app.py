import streamlit as st
import requests
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import base64

st.set_page_config(layout="wide", page_title="My Vinyl Collection & Wishlist", page_icon="vinyl.png")

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

# --- CENTRALIZED SYNC FUNCTION ---
def sync_database(target="collection"):
    if target == "collection":
        st.session_state["vinyl_db"] = st.session_state["vinyl_db"].sort_values(by=["Artist", "Album"]).reset_index(drop=True)
        conn.update(worksheet="Sheet1", data=st.session_state["vinyl_db"])
    elif target == "wishlist":
        st.session_state["wishlist_db"] = st.session_state["wishlist_db"].sort_values(by=["Artist", "Album"]).reset_index(drop=True)
        conn.update(worksheet="Wishlist", data=st.session_state["wishlist_db"])

# --- LOAD DATASETS ONCE ---
if "vinyl_db" not in st.session_state:
    df_coll = conn.read(worksheet="Sheet1", ttl=0)
    if "Cover_URL" not in df_coll.columns: df_coll["Cover_URL"] = ""
    if "Rating" not in df_coll.columns: df_coll["Rating"] = "Unrated"
    df_coll = df_coll.dropna(subset=["Artist"])
    df_coll["Barcode"] = df_coll["Barcode"].fillna("No Barcode")
    st.session_state["vinyl_db"] = df_coll.sort_values(by=["Artist", "Album"]).reset_index(drop=True)

if "wishlist_db" not in st.session_state:
    try:
        df_wish = conn.read(worksheet="Wishlist", ttl=0)
    except Exception:
        df_wish = pd.DataFrame(columns=["Barcode", "Artist", "Album", "Year", "Genre", "Cover_URL", "Rating"])
        
    if "Cover_URL" not in df_wish.columns: df_wish["Cover_URL"] = ""
    if "Rating" not in df_wish.columns: df_wish["Rating"] = "Unrated"
    df_wish = df_wish.dropna(subset=["Artist"])
    df_wish["Barcode"] = df_wish["Barcode"].fillna("No Barcode")
    st.session_state["wishlist_db"] = df_wish.sort_values(by=["Artist", "Album"]).reset_index(drop=True)

DISCOGS_TOKEN = st.secrets["DISCOGS_TOKEN"]
USER_AGENT = "MyVinylScannerApp/1.0"

# Initialize state keys
for key, default in [
    ("show_manual_coll", False), ("show_manual_wish", False),
    ("failed_barcode_coll", ""), ("failed_barcode_wish", ""),
    ("edit_row_coll", None), ("edit_row_wish", None)
]:
    if key not in st.session_state:
        st.session_state[key] = default

# --- TOP-LEVEL NAVIGATION TABS ---
tab_collection_page, tab_wishlist_page = st.tabs(["📀 My Collection", "🎁 Wishlist"])

# ==============================================================================
# TAB 1: MY COLLECTION PAGE
# ==============================================================================
with tab_collection_page:
    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("Add to Collection")
        tab_scan, tab_text = st.tabs(["📷 Scan Barcode", "🔍 Search by Name"])

        # Barcode Search
        with tab_scan:
            with st.form("coll_scanner_form", clear_on_submit=True):
                barcode = st.text_input("Scan Barcode Here:", key="coll_barcode_input")
                submitted = st.form_submit_button("Search & Save")

            if submitted and barcode:
                with st.spinner(f"Querying Discogs for {barcode}..."):
                    url = f"https://api.discogs.com/database/search?barcode={barcode}&token={DISCOGS_TOKEN}"
                    response = requests.get(url, headers={"User-Agent": USER_AGENT})
                    if response.status_code == 200 and response.json().get("results"):
                        match = response.json()["results"][0]
                        title_split = match.get("title", "Unknown - Unknown").split(" - ", 1)
                        artist = title_split[0]
                        album = title_split[1] if len(title_split) > 1 else match.get("title")
                        
                        new_row = pd.DataFrame([{
                            "Barcode": barcode, "Artist": artist, "Album": album,
                            "Year": match.get("year", "Unknown"), "Genre": ", ".join(match.get("genre", [])),
                            "Cover_URL": match.get("cover_image", ""), "Rating": "Unrated"
                        }])
                        
                        st.session_state["vinyl_db"] = pd.concat([st.session_state["vinyl_db"], new_row], ignore_index=True)
                        sync_database("collection")
                        st.session_state["show_manual_coll"] = False
                        st.session_state["failed_barcode_coll"] = ""
                        st.success(f"Added to Collection: **{artist} - {album}**")
                    else:
                        st.session_state["failed_barcode_coll"] = barcode
                        st.session_state["show_manual_coll"] = True
                        st.error("Barcode not found. Use manual form below:")

        # Text Search
        with tab_text:
            with st.form("coll_text_form", clear_on_submit=True):
                s_artist = st.text_input("Artist Name:", key="coll_search_artist")
                s_title = st.text_input("Album Title:", key="coll_search_title")
                submitted_text = st.form_submit_button("Search & Save")

            if submitted_text and (s_artist or s_title):
                with st.spinner("Searching Discogs..."):
                    params = {"artist": s_artist, "title": s_title, "format": "vinyl", "token": DISCOGS_TOKEN}
                    response = requests.get("https://api.discogs.com/database/search", headers={"User-Agent": USER_AGENT}, params=params)
                    if response.status_code == 200 and response.json().get("results"):
                        match = response.json()["results"][0]
                        title_split = match.get("title", "Unknown - Unknown").split(" - ", 1)
                        artist = title_split[0]
                        album = title_split[1] if len(title_split) > 1 else match.get("title")
                        
                        new_row = pd.DataFrame([{
                            "Barcode": "No Barcode", "Artist": artist, "Album": album,
                            "Year": match.get("year", "Unknown"), "Genre": ", ".join(match.get("genre", [])),
                            "Cover_URL": match.get("cover_image", ""), "Rating": "Unrated"
                        }])
                        
                        st.session_state["vinyl_db"] = pd.concat([st.session_state["vinyl_db"], new_row], ignore_index=True)
                        sync_database("collection")
                        st.session_state["show_manual_coll"] = False
                        st.success(f"Added to Collection: **{artist} - {album}**")
                    else:
                        st.session_state["show_manual_coll"] = True
                        st.error("No vinyl found. Use manual form below:")

        st.write("---")

        # Manual Entry
        with st.expander("✏ Add Record Manually", expanded=st.session_state["show_manual_coll"]):
            with st.form("coll_manual_form", clear_on_submit=True):
                m_barcode = st.text_input("Barcode (Optional):", value=st.session_state["failed_barcode_coll"], key="coll_m_bar")
                m_artist = st.text_input("Artist Name *", key="coll_m_art")
                m_album = st.text_input("Album Title *", key="coll_m_alb")
                m_year = st.text_input("Year:", key="coll_m_yr")
                m_genre = st.text_input("Genre:", key="coll_m_gnr")
                m_cover = st.text_input("Album Cover Photo URL:", key="coll_m_cvr")
                m_rating = st.selectbox("Rating:", options=["Unrated", "⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"], key="coll_m_rtg")
                
                if st.form_submit_button("Save Manual Record"):
                    if m_artist and m_album:
                        manual_row = pd.DataFrame([{
                            "Barcode": m_barcode if m_barcode else "No Barcode",
                            "Artist": m_artist, "Album": m_album,
                            "Year": m_year if m_year else "Unknown",
                            "Genre": m_genre if m_genre else "Unknown",
                            "Cover_URL": m_cover, "Rating": m_rating
                        }])
                        st.session_state["vinyl_db"] = pd.concat([st.session_state["vinyl_db"], manual_row], ignore_index=True)
                        sync_database("collection")
                        st.session_state["show_manual_coll"] = False
                        st.session_state["failed_barcode_coll"] = ""
                        st.success(f"Manually saved: **{m_artist} - {m_album}**")
                    else:
                        st.error("Artist and Album Title are required.")

    with col_right:
        st.subheader(f"Collection ({len(st.session_state['vinyl_db'])} Records)")
        
        # --- LOCAL COLLECTION SEARCH BAR ---
        filter_coll = st.text_input("🔎 Search Collection by Artist or Title:", key="filter_coll_input")
        
        display_coll_df = st.session_state["vinyl_db"]
        if filter_coll.strip():
            query = filter_coll.strip().lower()
            display_coll_df = display_coll_df[
                display_coll_df["Artist"].astype(str).str.lower().str.contains(query) |
                display_coll_df["Album"].astype(str).str.lower().str.contains(query)
            ]

        if not display_coll_df.empty:
            grid_cols = st.columns(4)
            for idx, (index, row) in enumerate(display_coll_df.iterrows()):
                with grid_cols[idx % 4]:
                    if st.session_state["edit_row_coll"] == index:
                        st.markdown("**Editing Record...**")
                        e_artist = st.text_input("Artist", value=row["Artist"], key=f"e_art_coll_{index}")
                        e_album = st.text_input("Album", value=row["Album"], key=f"e_alb_coll_{index}")
                        r_opts = ["Unrated", "⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]
                        curr_r = row.get("Rating", "Unrated") if pd.notna(row.get("Rating")) and row.get("Rating") in r_opts else "Unrated"
                        e_rating = st.selectbox("Rating", options=r_opts, index=r_opts.index(curr_r), key=f"e_rat_coll_{index}")
                        
                        col_save, col_cancel = st.columns(2)
                        with col_save:
                            if st.button("💾 Save", key=f"save_coll_{index}"):
                                st.session_state["vinyl_db"].at[index, "Artist"] = e_artist
                                st.session_state["vinyl_db"].at[index, "Album"] = e_album
                                st.session_state["vinyl_db"].at[index, "Rating"] = e_rating
                                sync_database("collection")
                                st.session_state["edit_row_coll"] = None
                                st.rerun()
                        with col_cancel:
                            if st.button("❌ Cancel", key=f"cancel_coll_{index}"):
                                st.session_state["edit_row_coll"] = None
                                st.rerun()
                    else:
                        if pd.notna(row.get("Cover_URL")) and str(row["Cover_URL"]).startswith("http"):
                            st.image(row["Cover_URL"], use_container_width=True)
                        else:
                            st.write("💿 No Cover Art")
                        
                        st.markdown(f"**{row['Album']}**")
                        st.caption(f"{row['Artist']}")
                        if row.get("Rating", "Unrated") != "Unrated":
                            st.write(row["Rating"])
                        
                        if st.button("✏️ Edit", key=f"edit_coll_{index}"):
                            st.session_state["edit_row_coll"] = index
                            st.rerun()
                        if st.button("🗑 Delete", key=f"del_coll_{index}"):
                            st.session_state["vinyl_db"] = st.session_state["vinyl_db"].drop(index).reset_index(drop=True)
                            sync_database("collection")
                            st.session_state["edit_row_coll"] = None
                            st.rerun()
        else:
            st.info("No matching records found in collection.")

# ==============================================================================
# TAB 2: WISHLIST PAGE
# ==============================================================================
with tab_wishlist_page:
    col_left_w, col_right_w = st.columns([1, 2])

    with col_left_w:
        st.subheader("Add to Wishlist")
        tab_scan_w, tab_text_w = st.tabs(["📷 Scan Barcode", "🔍 Search by Name"])

        # Wishlist Barcode Search
        with tab_scan_w:
            with st.form("wish_scanner_form", clear_on_submit=True):
                w_barcode = st.text_input("Scan Barcode Here:", key="wish_barcode_input")
                submitted_w = st.form_submit_button("Search & Save to Wishlist")

            if submitted_w and w_barcode:
                with st.spinner(f"Querying Discogs for {w_barcode}..."):
                    url = f"https://api.discogs.com/database/search?barcode={w_barcode}&token={DISCOGS_TOKEN}"
                    response = requests.get(url, headers={"User-Agent": USER_AGENT})
                    if response.status_code == 200 and response.json().get("results"):
                        match = response.json()["results"][0]
                        title_split = match.get("title", "Unknown - Unknown").split(" - ", 1)
                        artist = title_split[0]
                        album = title_split[1] if len(title_split) > 1 else match.get("title")
                        
                        new_row = pd.DataFrame([{
                            "Barcode": w_barcode, "Artist": artist, "Album": album,
                            "Year": match.get("year", "Unknown"), "Genre": ", ".join(match.get("genre", [])),
                            "Cover_URL": match.get("cover_image", ""), "Rating": "Unrated"
                        }])
                        
                        st.session_state["wishlist_db"] = pd.concat([st.session_state["wishlist_db"], new_row], ignore_index=True)
                        sync_database("wishlist")
                        st.session_state["show_manual_wish"] = False
                        st.session_state["failed_barcode_wish"] = ""
                        st.success(f"Added to Wishlist: **{artist} - {album}**")
                    else:
                        st.session_state["failed_barcode_wish"] = w_barcode
                        st.session_state["show_manual_wish"] = True
                        st.error("Barcode not found. Use manual form below:")

        # Wishlist Text Search
        with tab_text_w:
            with st.form("wish_text_form", clear_on_submit=True):
                ws_artist = st.text_input("Artist Name:", key="wish_search_artist")
                ws_title = st.text_input("Album Title:", key="wish_search_title")
                submitted_text_w = st.form_submit_button("Search & Save to Wishlist")

            if submitted_text_w and (ws_artist or ws_title):
                with st.spinner("Searching Discogs..."):
                    params = {"artist": ws_artist, "title": ws_title, "format": "vinyl", "token": DISCOGS_TOKEN}
                    response = requests.get("https://api.discogs.com/database/search", headers={"User-Agent": USER_AGENT}, params=params)
                    if response.status_code == 200 and response.json().get("results"):
                        match = response.json()["results"][0]
                        title_split = match.get("title", "Unknown - Unknown").split(" - ", 1)
                        artist = title_split[0]
                        album = title_split[1] if len(title_split) > 1 else match.get("title")
                        
                        new_row = pd.DataFrame([{
                            "Barcode": "No Barcode", "Artist": artist, "Album": album,
                            "Year": match.get("year", "Unknown"), "Genre": ", ".join(match.get("genre", [])),
                            "Cover_URL": match.get("cover_image", ""), "Rating": "Unrated"
                        }])
                        
                        st.session_state["wishlist_db"] = pd.concat([st.session_state["wishlist_db"], new_row], ignore_index=True)
                        sync_database("wishlist")
                        st.session_state["show_manual_wish"] = False
                        st.success(f"Added to Wishlist: **{artist} - {album}**")
                    else:
                        st.session_state["show_manual_wish"] = True
                        st.error("No vinyl found. Use manual form below:")

        st.write("---")

        # Wishlist Manual Entry
        with st.expander("✏ Add Record Manually", expanded=st.session_state["show_manual_wish"]):
            with st.form("wish_manual_form", clear_on_submit=True):
                wm_barcode = st.text_input("Barcode (Optional):", value=st.session_state["failed_barcode_wish"], key="wish_m_bar")
                wm_artist = st.text_input("Artist Name *", key="wish_m_art")
                wm_album = st.text_input("Album Title *", key="wish_m_alb")
                wm_year = st.text_input("Year:", key="wish_m_yr")
                wm_genre = st.text_input("Genre:", key="wish_m_gnr")
                wm_cover = st.text_input("Album Cover Photo URL:", key="wish_m_cvr")
                wm_rating = st.selectbox("Rating:", options=["Unrated", "⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"], key="wish_m_rtg")
                
                if st.form_submit_button("Save Manual Wishlist Record"):
                    if wm_artist and wm_album:
                        manual_row = pd.DataFrame([{
                            "Barcode": wm_barcode if wm_barcode else "No Barcode",
                            "Artist": wm_artist, "Album": wm_album,
                            "Year": wm_year if wm_year else "Unknown",
                            "Genre": wm_genre if wm_genre else "Unknown",
                            "Cover_URL": wm_cover, "Rating": wm_rating
                        }])
                        st.session_state["wishlist_db"] = pd.concat([st.session_state["wishlist_db"], manual_row], ignore_index=True)
                        sync_database("wishlist")
                        st.session_state["show_manual_wish"] = False
                        st.session_state["failed_barcode_wish"] = ""
                        st.success(f"Manually saved to Wishlist: **{wm_artist} - {wm_album}**")
                    else:
                        st.error("Artist and Album Title are required.")

    with col_right_w:
        st.subheader(f"Wishlist ({len(st.session_state['wishlist_db'])} Records)")
        
        # --- LOCAL WISHLIST SEARCH BAR ---
        filter_wish = st.text_input("🔎 Search Wishlist by Artist or Title:", key="filter_wish_input")
        
        display_wish_df = st.session_state["wishlist_db"]
        if filter_wish.strip():
            query_w = filter_wish.strip().lower()
            display_wish_df = display_wish_df[
                display_wish_df["Artist"].astype(str).str.lower().str.contains(query_w) |
                display_wish_df["Album"].astype(str).str.lower().str.contains(query_w)
            ]

        if not display_wish_df.empty:
            grid_cols_w = st.columns(4)
            for idx, (index, row) in enumerate(display_wish_df.iterrows()):
                with grid_cols_w[idx % 4]:
                    if st.session_state["edit_row_wish"] == index:
                        st.markdown("**Editing Wishlist Item...**")
                        we_artist = st.text_input("Artist", value=row["Artist"], key=f"we_art_wish_{index}")
                        we_album = st.text_input("Album", value=row["Album"], key=f"we_alb_wish_{index}")
                        r_opts = ["Unrated", "⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]
                        curr_r = row.get("Rating", "Unrated") if pd.notna(row.get("Rating")) and row.get("Rating") in r_opts else "Unrated"
                        we_rating = st.selectbox("Rating", options=r_opts, index=r_opts.index(curr_r), key=f"we_rat_wish_{index}")
                        
                        col_save, col_cancel = st.columns(2)
                        with col_save:
                            if st.button("💾 Save", key=f"save_wish_{index}"):
                                st.session_state["wishlist_db"].at[index, "Artist"] = we_artist
                                st.session_state["wishlist_db"].at[index, "Album"] = we_album
                                st.session_state["wishlist_db"].at[index, "Rating"] = we_rating
                                sync_database("wishlist")
                                st.session_state["edit_row_wish"] = None
                                st.rerun()
                        with col_cancel:
                            if st.button("❌ Cancel", key=f"cancel_wish_{index}"):
                                st.session_state["edit_row_wish"] = None
                                st.rerun()
                    else:
                        if pd.notna(row.get("Cover_URL")) and str(row["Cover_URL"]).startswith("http"):
                            st.image(row["Cover_URL"], use_container_width=True)
                        else:
                            st.write("💿 No Cover Art")
                        
                        st.markdown(f"**{row['Album']}**")
                        st.caption(f"{row['Artist']}")
                        
                        # Move to Collection Button
                        if st.button("📦 Move to Collection", key=f"move_wish_{index}"):
                            moved_row = row.to_frame().T
                            # 1. Add to collection
                            st.session_state["vinyl_db"] = pd.concat([st.session_state["vinyl_db"], moved_row], ignore_index=True)
                            sync_database("collection")
                            # 2. Remove from wishlist
                            st.session_state["wishlist_db"] = st.session_state["wishlist_db"].drop(index).reset_index(drop=True)
                            sync_database("wishlist")
                            st.rerun()

                        if st.button("✏️ Edit", key=f"edit_wish_{index}"):
                            st.session_state["edit_row_wish"] = index
                            st.rerun()
                        if st.button("🗑 Delete", key=f"del_wish_{index}"):
                            st.session_state["wishlist_db"] = st.session_state["wishlist_db"].drop(index).reset_index(drop=True)
                            sync_database("wishlist")
                            st.session_state["edit_row_wish"] = None
                            st.rerun()
        else:
            st.info("No matching records found in wishlist.")