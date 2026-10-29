import os
import time
import xml.etree.ElementTree as ET
import requests
import yt_dlp

# ==========================================
# 1. CONFIGURATION
# ==========================================
YOUTUBE_CHANNEL_URL = os.environ.get("YOUTUBE_CHANNEL_URL", "https://www.youtube.com/@MathonGoCoupons/shorts")
YT_COOKIES = os.environ.get("YT_COOKIES", "").strip()
IG_USER_ID = "".join(os.environ.get("IG_USER_ID", "").replace("IG_USER_ID:", "").split())
IG_ACCESS_TOKEN = "".join(os.environ.get("IG_ACCESS_TOKEN", "").replace("IG_ACCESS_TOKEN:", "").split())

HISTORY_FILE = "posted_videos.txt"
COOKIES_FILE = "cookies.txt"

if YT_COOKIES:
    with open(COOKIES_FILE, "w", encoding="utf-8") as f:
        f.write(YT_COOKIES + "\n")
    print("🍪 Loaded YT_COOKIES for authenticated YouTube download!")

# ==========================================
# 2. FETCH EXACT TITLE & DESCRIPTION VIA OFFICIAL YOUTUBE XML FEED
# ==========================================
def get_posted_history():
    if not os.path.exists(HISTORY_FILE):
        return set()
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_to_history(video_id):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{video_id}\n")

def fetch_metadata_from_xml_feed(channel_id, video_id):
    """Fetches exact Title & Full Description from YouTube's official XML feed (Never blocked!)"""
    if not channel_id:
        return "", ""
    try:
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            root = ET.fromstring(r.text)
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "yt": "http://www.youtube.com/xml/schemas/2015",
                "media": "http://search.yahoo.com/mrss/"
            }
            for entry in root.findall("atom:entry", ns):
                vid_elem = entry.find("yt:videoId", ns)
                if vid_elem is not None and vid_elem.text == video_id:
                    title_elem = entry.find("atom:title", ns)
                    desc_elem = entry.find("media:group/media:description", ns)
                    return (
                        title_elem.text if title_elem is not None else "",
                        desc_elem.text if desc_elem is not None else ""
                    )
    except Exception as e:
        print(f"   ⚠️ XML Feed lookup note: {e}")
    return "", ""

# ==========================================
# 3. MULTI-LAYER VIDEO DOWNLOADER (DENO + COOKIES + PROXY MIRRORS)
# ==========================================
def download_via_proxy_mirrors(video_id, output_mp4):
    """Fallback: Downloads MP4 via external Invidious/Piped proxy servers outside GitHub Actions IP"""
    print("   🌐 Trying External Proxy Mirrors (Invidious / Piped APIs)...")
    
    # 1. Try Piped API Mirrors
    piped_hosts = [
        "https://pipedapi.kavin.rocks",
        "https://pipedapi.tokhmi.xyz",
        "https://pipedapi.drgns.space"
    ]
    for host in piped_hosts:
        try:
            r = requests.get(f"{host}/streams/{video_id}", timeout=20).json()
            streams = [s for s in r.get("videoStreams", []) if not s.get("videoOnly", True) and s.get("format") == "MPEG_4"]
            if streams:
                dl_url = streams[0]["url"]
                vid_bytes = requests.get(dl_url, timeout=45).content
                if len(vid_bytes) > 20000:
                    with open(output_mp4, "wb") as f:
                        f.write(vid_bytes)
                    return r.get("title", ""), r.get("description", "")
        except Exception as e:
            print(f"   ⚠️ Piped mirror ({host}) skipped: {e}")

    # 2. Try Invidious API Mirrors
    inv_hosts = [
        "https://inv.nadeko.net",
        "https://invidious.nerdvpn.de",
        "https://yt.chocolatemoo53.com"
    ]
    for host in inv_hosts:
        try:
            r = requests.get(f"{host}/api/v1/videos/{video_id}", timeout=20).json()
            fmt_streams = r.get("formatStreams", [])
            if fmt_streams:
                dl_url = fmt_streams[-1]["url"]
                if dl_url.startswith("/"):
                    dl_url = host + dl_url
                vid_bytes = requests.get(dl_url, timeout=45).content
                if len(vid_bytes) > 20000:
                    with open(output_mp4, "wb") as f:
                        f.write(vid_bytes)
                    return r.get("title", ""), r.get("description", "")
        except Exception as e:
            print(f"   ⚠️ Invidious mirror ({host}) skipped: {e}")

    return None, None

def download_with_multi_bypass(video_url, video_id, output_mp4):
    client_strategies = [
        None,  # Uses Deno + PO-Token + Cookies (if provided)
        ["tv", "web_safari"],
        ["mweb", "web_embedded"],
        ["web_creator"]
    ]

    for idx, clients in enumerate(client_strategies):
        if os.path.exists(output_mp4):
            os.remove(output_mp4)

        dl_opts = {
            "format": "bestvideo[ext=mp4][height<=1920]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "outtmpl": output_mp4,
            "quiet": False,
            "nocheckcertificate": True,
        }
        if os.path.exists(COOKIES_FILE):
            dl_opts["cookiefile"] = COOKIES_FILE
        if clients:
            dl_opts["extractor_args"] = {"youtube": {"player_client": clients}}

        try:
            print(f"   🔓 Download Attempt {idx+1} (Clients: {clients or 'Deno + Cookies/POT'})...")
            with yt_dlp.YoutubeDL(dl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                if os.path.exists(output_mp4) and os.path.getsize(output_mp4) > 10000:
                    return info.get("title", ""), info.get("description", "")
        except Exception as e:
            print(f"   ⚠️ Strategy {idx+1} blocked: {e}")

    # Try external proxy mirrors if GitHub IP is blocked
    p_title, p_desc = download_via_proxy_mirrors(video_id, output_mp4)
    if os.path.exists(output_mp4) and os.path.getsize(output_mp4) > 10000:
        return p_title or "", p_desc or ""

    raise RuntimeError("❌ Download blocked by YouTube IP check. Please add YT_COOKIES to GitHub Secrets (takes 30 seconds)!")

def fetch_latest_youtube_video():
    print(f"🔍 Checking YouTube channel for new uploads: {YOUTUBE_CHANNEL_URL}")
    posted_ids = get_posted_history()

    flat_opts = {"extract_flat": True, "playlistend": 3, "quiet": True}
    if os.path.exists(COOKIES_FILE):
        flat_opts["cookiefile"] = COOKIES_FILE

    with yt_dlp.YoutubeDL(flat_opts) as ydl:
        info = ydl.extract_info(YOUTUBE_CHANNEL_URL, download=False)
        entries = info.get("entries", [])
        channel_id = info.get("channel_id", "")

    if not entries:
        print("ℹ️ No videos found on this channel tab.")
        return None

    latest_entry = entries[0]
    video_id = latest_entry.get("id")
    playlist_title = latest_entry.get("title", "")

    if video_id in posted_ids:
        print(f"✅ Latest video ({video_id}) is already posted on Instagram. Nothing new to upload!")
        return None

    video_url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"🆕 NEW YOUTUBE VIDEO DETECTED! ID: {video_id}")

    # Fetch guaranteed Title & Full Description from official XML feed
    xml_title, xml_desc = fetch_metadata_from_xml_feed(channel_id, video_id)

    output_mp4 = "latest_yt_short.mp4"
    dl_title, dl_desc = download_with_multi_bypass(video_url, video_id, output_mp4)

    final_title = dl_title or xml_title or playlist_title or "New Short #shorts"
    final_desc = dl_desc or xml_desc or final_title

    print(f"✅ Downloaded Successfully: '{final_title}'")
    return {
        "id": video_id,
        "video_path": output_mp4,
        "title": final_title,
        "description": final_desc
    }

# ==========================================
# 4. STAGE VIDEO & UPLOAD TO INSTAGRAM REELS
# ==========================================
def get_temp_public_video_url(video_path):
    try:
        with open(video_path, "rb") as f:
            r = requests.post("https://tmpfiles.org/api/v1/upload", files={"file": f}, timeout=60).json()
        url = r.get("data", {}).get("url", "")
        if url:
            return url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
    except Exception as e:
        print(f"   ⚠️ tmpfiles fallback ({e})...")

    try:
        with open(video_path, "rb") as f:
            r = requests.post(
                "https://litterbox.catbox.moe/resources/internals/api.php",
                data={"reqtype": "fileupload", "time": "1h"},
                files={"fileToUpload": f},
                timeout=60
            )
        if r.status_code == 200 and r.text.startswith("http"):
            return r.text.strip()
    except Exception as e:
        print(f"   ⚠️ litterbox fallback ({e})...")

    with open(video_path, "rb") as f:
        r = requests.post("https://uguu.se/upload", files={"files[]": f}, timeout=60).json()
    return r["files"][0]["url"]

def resolve_ig_account():
    if IG_ACCESS_TOKEN.startswith("IG"):
        return "https://graph.instagram.com/v21.0", IG_USER_ID, IG_ACCESS_TOKEN

    base_url = "https://graph.facebook.com/v21.0"
    try:
        r = requests.get(
            f"{base_url}/me/accounts",
            params={"fields": "id,name,access_token,instagram_business_account{id,username}", "access_token": IG_ACCESS_TOKEN},
            timeout=20
        ).json()
        for page in r.get("data", []):
            ig_acc = page.get("instagram_business_account")
            if ig_acc and ig_acc.get("id"):
                print(f"   ✅ Connected to Instagram @{ig_acc.get('username')} (ID: {ig_acc['id']})")
                return base_url, ig_acc["id"], page.get("access_token", IG_ACCESS_TOKEN)
    except Exception:
        pass
    return base_url, IG_USER_ID, IG_ACCESS_TOKEN

def post_to_instagram_reels(video_data):
    print("📸 Uploading to Instagram Reels with same Title & Description...")
    if not IG_USER_ID or not IG_ACCESS_TOKEN:
        raise ValueError("❌ IG_USER_ID or IG_ACCESS_TOKEN is missing!")

    base_url, target_ig_id, active_token = resolve_ig_account()

    print("   🌐 Generating temporary public link for Meta Graph API...")
    public_video_url = get_temp_public_video_url(video_data["video_path"])
    print(f"   ✅ Temporary URL ready: {public_video_url}")

    full_caption = f"{video_data['title']}\n\n{video_data['description']}"[:2180]

    create_url = f"{base_url}/{target_ig_id}/media"
    payload = {
        "media_type": "REELS",
        "video_url": public_video_url,
        "caption": full_caption,
        "share_to_feed": "true",
        "access_token": active_token
    }
    res = requests.post(create_url, data=payload, timeout=30).json()
    if "id" not in res:
        raise RuntimeError(f"❌ Instagram Container Error: {res}")

    creation_id = res["id"]
    print(f"   ⏳ Container created (ID: {creation_id}). Waiting for Instagram processing...")

    status_url = f"{base_url}/{creation_id}"
    for attempt in range(1, 15):
        time.sleep(10)
        stat_res = requests.get(
            status_url,
            params={"fields": "status_code,status", "access_token": active_token},
            timeout=20
        ).json()
        code = stat_res.get("status_code", "")
        print(f"   🔄 Processing status ({attempt}/14): {code}")
        if code == "FINISHED":
            break
        elif code == "ERROR":
            raise RuntimeError(f"❌ Instagram Processing Failed: {stat_res}")

    pub_url = f"{base_url}/{target_ig_id}/media_publish"
    pub_res = requests.post(
        pub_url,
        data={"creation_id": creation_id, "access_token": active_token},
        timeout=30
    ).json()

    if "id" in pub_res:
        print(f"🎉 SUCCESS! YouTube Video reposted to Instagram Reels! IG Media ID: {pub_res['id']}")
        return True
    else:
        raise RuntimeError(f"❌ Instagram Publish Failed: {pub_res}")

if __name__ == "__main__":
    video_data = fetch_latest_youtube_video()
    if video_data:
        success = post_to_instagram_reels(video_data)
        if success:
            save_to_history(video_data["id"])
            print(f"📝 Saved {video_data['id']} to {HISTORY_FILE} so it won't be reposted again.")
