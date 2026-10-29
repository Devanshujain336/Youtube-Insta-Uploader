import os
import time
import subprocess
import requests
import yt_dlp

# ==========================================
# 1. CONFIGURATION
# ==========================================
YOUTUBE_CHANNEL_URL = os.environ.get("YOUTUBE_CHANNEL_URL", "https://www.youtube.com/@MathonGoCoupons/shorts")
IG_USER_ID = "".join(os.environ.get("IG_USER_ID", "").replace("IG_USER_ID:", "").split())
IG_ACCESS_TOKEN = "".join(os.environ.get("IG_ACCESS_TOKEN", "").replace("IG_ACCESS_TOKEN:", "").split())

HISTORY_FILE = "posted_videos.txt"

# ==========================================
# 2. CHECK FOR NEW YOUTUBE VIDEO & DOWNLOAD
# ==========================================
def get_posted_history():
    if not os.path.exists(HISTORY_FILE):
        return set()
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_to_history(video_id):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{video_id}\n")

def get_oembed_title(video_url):
    """Fetches video title via YouTube oEmbed API (never blocked by bot checks)"""
    try:
        r = requests.get(f"https://www.youtube.com/oembed?url={video_url}&format=json", timeout=10).json()
        return r.get("title", "")
    except Exception:
        return ""

def download_with_multi_bypass(video_url, output_mp4):
    """Rotates across PO-Token clients + pytubefix to bypass datacenter bot checks"""
    client_strategies = [
        None,  # Uses default web/tv client with bgutil PO Token plugin on port 4416
        ["tv_downgraded", "web_embedded", "mweb"],
        ["mweb", "tv_downgraded"],
        ["android_vr", "tv_downgraded"],
        ["web_creator", "web_embedded"]
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
        if clients:
            dl_opts["extractor_args"] = {"youtube": {"player_client": clients}}

        try:
            print(f"   🔓 Download Attempt {idx+1} (Clients: {clients or 'PO-Token Default'})...")
            with yt_dlp.YoutubeDL(dl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                if os.path.exists(output_mp4) and os.path.getsize(output_mp4) > 10000:
                    return info.get("title", ""), info.get("description", "")
        except Exception as e:
            print(f"   ⚠️ Strategy {idx+1} blocked: {e}")

    # Fallback to pytubefix if all yt-dlp clients fail
    print("   🔄 Trying pytubefix fallback...")
    from pytubefix import YouTube
    for pt_client in ["WEB", "MWEB", "ANDROID_VR", "TV"]:
        try:
            yt = YouTube(video_url, client=pt_client)
            stream = yt.streams.filter(progressive=True, file_extension="mp4").order_by("resolution").desc().first()
            if not stream:
                stream = yt.streams.filter(file_extension="mp4").first()
            if stream:
                stream.download(filename=output_mp4)
                if os.path.exists(output_mp4) and os.path.getsize(output_mp4) > 10000:
                    return yt.title or "", yt.description or ""
        except Exception as e:
            print(f"   ⚠️ pytubefix ({pt_client}) failed: {e}")

    raise RuntimeError("❌ All YouTube download bypass strategies failed.")

def fetch_latest_youtube_video():
    print(f"🔍 Checking YouTube channel for new uploads: {YOUTUBE_CHANNEL_URL}")
    posted_ids = get_posted_history()

    flat_opts = {"extract_flat": True, "playlistend": 3, "quiet": True}
    with yt_dlp.YoutubeDL(flat_opts) as ydl:
        info = ydl.extract_info(YOUTUBE_CHANNEL_URL, download=False)
        entries = info.get("entries", [])

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

    output_mp4 = "latest_yt_short.mp4"
    dl_title, dl_desc = download_with_multi_bypass(video_url, output_mp4)

    final_title = dl_title or playlist_title or get_oembed_title(video_url) or "New Short #shorts"
    final_desc = dl_desc or final_title

    print(f"✅ Downloaded Successfully: '{final_title}'")
    return {
        "id": video_id,
        "video_path": output_mp4,
        "title": final_title,
        "description": final_desc
    }

# ==========================================
# 3. STAGE VIDEO & UPLOAD TO INSTAGRAM REELS
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
