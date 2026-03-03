## python

``` python
import sys
import time
from openai import OpenAI

API_KEY = "<AIHUBMIX_API_KEY>"
BASE_URL = "https://aihubmix.com/v1"
MODEL = "sora-2"
PROMPT = (
    "A cool cat wearing sunglasses rides a motorcycle on a wet, "
    "neon-lit city street at night, with reflections on the pavement."
)


def init_client():
    try:
        return OpenAI(api_key=API_KEY, base_url=BASE_URL)
    except Exception as e:
        sys.exit(f"Init client error: {e}")


def create_video(client):
    try:
        print("Creating video task...")
        return client.videos.create(model=MODEL, prompt=PROMPT)
    except Exception as e:
        sys.exit(f"Create video error: {e}")


def wait_for_video(client, video):
    bar_len = 30
    while video.status in ("in_progress", "queued"):
        try:
            video = client.videos.retrieve(video.id)
        except Exception as e:
            print(f"\nRetrieve status error: {e}")
            time.sleep(5)
            continue

        progress = getattr(video, "progress", 0) or 0
        filled = int(progress / 100 * bar_len)
        bar = "█" * filled + "-" * (bar_len - filled)
        sys.stdout.write(f"\r{video.status.capitalize():10} [{bar}] {progress:5.1f}%")
        sys.stdout.flush()
        time.sleep(5)

    print()  # newline
    return video


def download_video(client, video):
    if video.status == "completed":
        try:
            content = client.videos.download_content(video.id)
            content.write_to_file("generated_video.mp4")
            print("Video saved as generated_video.mp4")
        except Exception as e:
            print(f"Download error: {e}")
    elif video.status == "failed":
        msg = getattr(getattr(video, "error", None), "message", "Unknown error")
        sys.exit(f"Video failed: {msg}")
    else:
        print(f"Unexpected status: {video.status}")


def main():
    client = init_client()
    video = create_video(client)
    video = wait_for_video(client, video)
    download_video(client, video)


if __name__ == "__main__":
    main()
```