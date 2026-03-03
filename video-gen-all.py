import argparse
import json
import os
import sys
import time
from urllib import error, request

from openai import OpenAI

DEFAULT_BASE_URL = "https://aihubmix.com/v1"
DEFAULT_TASK_BASE_URL = "https://api.aihubmix.com/v1"
AIHUBMIX_API_KEY = "sk-4IRRyK6M2O3lPcGDEd1b76710b434b27A35aF09458Fd8330"
SUPPORTED_MODELS = {
    "sora-2": "sora",
    "sora-2-pro": "sora",
    "veo-3.1-fast-generate-preview": "prediction",
    "veo-3.1-generate-preview": "prediction",
}


def http_get(url, headers=None, timeout=120):
    req = request.Request(url, headers=headers or {}, method="GET")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read()
    except error.HTTPError as e:
        return e.code, e.read()


def http_post_json(url, payload, headers=None, timeout=120):
    all_headers = {"Content-Type": "application/json"}
    if headers:
        all_headers.update(headers)
    req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=all_headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read()
    except error.HTTPError as e:
        return e.code, e.read()


def ensure_api_key():
    if not AIHUBMIX_API_KEY:
        raise RuntimeError("AIHUBMIX_API_KEY is required")
    return AIHUBMIX_API_KEY


def init_client(api_key):
    return OpenAI(api_key=api_key, base_url=DEFAULT_BASE_URL)


def download_bytes(url, api_key):
    code, body = http_get(url, headers={"Authorization": "Bearer " + api_key}, timeout=240)
    if code >= 400:
        code, body = http_get(url, timeout=240)
    if code >= 400:
        raise RuntimeError("Download failed: " + url)
    return body


def poll_task(task_id, api_key):
    headers = {"Authorization": "Bearer " + api_key}
    urls = [
        str(task_id) if str(task_id).startswith(("http://", "https://")) else DEFAULT_TASK_BASE_URL.rstrip("/") + "/tasks/" + str(task_id),
        DEFAULT_BASE_URL.rstrip("/") + "/tasks/" + str(task_id),
    ]
    while True:
        payload = None
        for url in urls:
            code, body = http_get(url, headers=headers, timeout=120)
            if code < 400:
                payload = json.loads(body.decode("utf-8"))
                break
        if payload is None:
            raise RuntimeError("Task poll failed")
        status = payload.get("status") or payload.get("state") or payload.get("task_status")
        if status in ("completed", "succeeded", "success", "done", "Ready"):
            return payload
        if status in ("failed", "error", "canceled", "cancelled"):
            raise RuntimeError("Task failed: " + json.dumps(payload, ensure_ascii=False))
        time.sleep(3)


def extract_video_url(payload):
    output = payload.get("output")
    if isinstance(output, str) and output.startswith("http"):
        return output
    if isinstance(output, list):
        for item in output:
            if isinstance(item, str) and item.startswith("http"):
                return item
            if isinstance(item, dict):
                url = item.get("url") or item.get("video") or item.get("video_url")
                if isinstance(url, str) and url.startswith("http"):
                    return url
    if isinstance(output, dict):
        for key in ("url", "video", "video_url"):
            val = output.get(key)
            if isinstance(val, str) and val.startswith("http"):
                return val
    for key in ("video", "video_url", "url"):
        val = payload.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return val
    return None


def generate_with_sora(args, client):
    video = client.videos.create(model=args.model, prompt=args.text)
    while True:
        video = client.videos.retrieve(video.id)
        status = getattr(video, "status", "")
        if status in ("completed", "succeeded", "success"):
            break
        if status in ("failed", "error", "canceled", "cancelled"):
            raise RuntimeError("Video generation failed")
        time.sleep(5)
    content = client.videos.download_content(video.id)
    if hasattr(content, "read"):
        return content.read()
    if hasattr(content, "content"):
        return content.content
    if hasattr(content, "write_to_file"):
        temp = ".tmp_video_download.bin"
        content.write_to_file(temp)
        with open(temp, "rb") as fh:
            data = fh.read()
        os.remove(temp)
        return data
    raise RuntimeError("Unsupported video content type returned by SDK")


def generate_with_prediction(args, api_key):
    url = DEFAULT_BASE_URL.rstrip("/") + "/models/" + args.model + "/predictions"
    payload = {"input": {"prompt": args.text}}
    code, body = http_post_json(url, payload, headers={"Authorization": "Bearer " + api_key}, timeout=120)
    if code >= 400:
        raise RuntimeError("Prediction create failed: " + body.decode("utf-8", errors="ignore"))
    created = json.loads(body.decode("utf-8"))
    created = created.get("output", [created])[0]
    task_id = created.get("id") or created.get("task_id") or created.get("taskId")
    if not task_id and isinstance(created.get("urls"), dict):
        task_id = created["urls"].get("get") or created["urls"].get("status")
    result = poll_task(task_id, api_key) if task_id else created
    video_url = extract_video_url(result)
    if not video_url:
        raise RuntimeError("Could not extract video url from payload")
    return download_bytes(video_url, api_key)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="sora-2", choices=list(SUPPORTED_MODELS.keys()))
    parser.add_argument("--text", default="A cool cat wearing sunglasses rides a motorcycle on a wet neon-lit city street at night")
    parser.add_argument("--output", default="./generated_video.mp4")
    return parser.parse_args()


def main():
    try:
        args = parse_args()
        api_key = ensure_api_key()
        mode = SUPPORTED_MODELS[args.model]
        client = init_client(api_key)
        if mode == "sora":
            video_bytes = generate_with_sora(args, client)
        else:
            video_bytes = generate_with_prediction(args, api_key)
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "wb") as fh:
            fh.write(video_bytes)
        print("Saved video to " + args.output)
    except Exception as err:
        print(str(err), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
