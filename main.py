import os
import time
import requests
import yt_dlp

# ================= CONFIGURATION =================
YOUTUBE_SHORTS_URL = "https://www.youtube.com/@YOUR_CHANNEL_HANDLE/shorts"  # Replace handle
HISTORY_FILE = "uploaded_ids.txt"

# Meta Graph API Credentials (retrieved from GitHub Secrets)
IG_USER_ID = os.environ.get("IG_USER_ID")
ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN")
GRAPH_API_VERSION = "v21.0"
# =================================================

def get_posted_ids():
    if not os.path.exists(HISTORY_FILE):
        return set()
    with open(HISTORY_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())

def mark_id_as_posted(video_id):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{video_id}\n")

def get_latest_short():
    ydl_opts = {
        'extract_flat': True,
        'quiet': True,
        'playlist_items': '1',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(YOUTUBE_SHORTS_URL, download=False)
        if 'entries' in info and len(info['entries']) > 0:
            latest = info['entries'][0]
            return latest.get('id'), latest.get('title'), latest.get('url')
    return None, None, None

def download_video(video_url, output_path="temp_reel.mp4"):
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'quiet': True,
        'overwrites': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])
    return output_path

def upload_and_publish_reel(video_path, caption):
    file_size = os.path.getsize(video_path)

    # 1. Create a Resumable Reel Container
    init_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{IG_USER_ID}/media"
    init_payload = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": caption,
        "access_token": ACCESS_TOKEN
    }
    init_res = requests.post(init_url, data=init_payload).json()
    
    if "id" not in init_res:
        raise Exception(f"Failed to create Reel container: {init_res}")
    
    container_id = init_res["id"]
    upload_uri = init_res.get("uri", f"https://rupload.facebook.com/ig-api-upload/{GRAPH_API_VERSION}/{container_id}")
    print(f"Container created (ID: {container_id}). Uploading video binary...")

    # 2. Upload video bytes to rupload.facebook.com
    headers = {
        "Authorization": f"OAuth {ACCESS_TOKEN}",
        "offset": "0",
        "file_size": str(file_size),
        "Content-Type": "application/octet-stream"
    }
    with open(video_path, "rb") as f:
        video_bytes = f.read()

    upload_res = requests.post(upload_uri, headers=headers, data=video_bytes)
    if upload_res.status_code != 200:
        raise Exception(f"Failed to upload video bytes: {upload_res.text}")

    # 3. Wait for Meta to process the video
    print("Video binary sent. Waiting for Instagram processing...")
    status_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{container_id}"
    params = {"fields": "status_code", "access_token": ACCESS_TOKEN}

    for _ in range(20):  # Poll every 5 seconds for up to ~100s
        time.sleep(5)
        status_res = requests.get(status_url, params=params).json()
        status = status_res.get("status_code")
        print(f"Current container status: {status}")

        if status == "FINISHED":
            break
        elif status == "ERROR":
            raise Exception(f"Instagram failed to process video: {status_res}")
    else:
        raise TimeoutError("Timed out waiting for Instagram to process the video.")

    # 4. Publish the Reel
    publish_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{IG_USER_ID}/media_publish"
    publish_payload = {
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN
    }
    pub_res = requests.post(publish_url, data=publish_payload).json()

    if "id" not in pub_res:
        raise Exception(f"Failed to publish Reel: {pub_res}")

    print(f"🎉 Successfully published to Instagram! Post ID: {pub_res['id']}")

def main():
    posted_ids = get_posted_ids()
    video_id, title, url = get_latest_short()

    if not video_id:
        print("Could not retrieve channel info.")
        return

    if video_id in posted_ids:
        print("No new shorts found.")
        return

    print(f"New Short found: {title} (ID: {video_id})")
    video_path = download_video(url)

    try:
        upload_and_publish_reel(video_path, caption=title)
        mark_id_as_posted(video_id)
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)

if __name__ == "__main__":
    main()
