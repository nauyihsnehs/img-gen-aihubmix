import argparse
import base64
import json
import os
import sys
import time
from urllib import request, error

from openai import OpenAI

DEFAULT_BASE_URL = "https://aihubmix.com/v1"
DEFAULT_TASK_BASE_URL = "https://api.aihubmix.com/v1"
AIHUBMIX_API_KEY = "sk-4IRRyK6M2O3lPcGDEd1b76710b434b27A35aF09458Fd8330"


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
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers=all_headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read()
    except error.HTTPError as e:
        return e.code, e.read()


def extract_image_bytes_from_openai_images_response(response):
    data = getattr(response, "data", None)
    if not data:
        raise RuntimeError("No image data found in response")
    first = data[0]
    encoded = getattr(first, "b64_json", None)
    if not encoded:
        raise RuntimeError("No b64_json found in image response")
    return base64.b64decode(encoded)


def extract_image_bytes_from_multimodal_chat(response):
    choices = getattr(response, "choices", None)
    if not choices:
        raise RuntimeError("No choices in chat response")
    message = getattr(choices[0], "message", None)
    if not message:
        raise RuntimeError("No message in chat response")
    parts = getattr(message, "multi_mod_content", None)
    if not parts:
        raise RuntimeError("No multimodal content in chat response")
    for part in parts:
        inline_data = part.get("inline_data") if isinstance(part, dict) else None
        if inline_data and inline_data.get("data"):
            return base64.b64decode(inline_data["data"])
    raise RuntimeError("No inline image data found in multimodal response")


def poll_prediction_task(task_id, api_key, base_url):
    headers = {"Authorization": "Bearer " + api_key}
    poll_urls = []
    if str(task_id).startswith("http://") or str(task_id).startswith("https://"):
        poll_urls.append(str(task_id))
    else:
        poll_urls.append(DEFAULT_TASK_BASE_URL.rstrip("/") + "/tasks/" + str(task_id))
        poll_urls.append(base_url.rstrip("/") + "/tasks/" + str(task_id))
    last_err = None
    while True:
        response = None
        for url in poll_urls:
            try:
                status_code, body = http_get(url, headers=headers, timeout=120)
                response = {"status_code": status_code, "body": body}
                if status_code < 400:
                    break
            except Exception as err:
                last_err = err
        if response is None:
            raise RuntimeError("Could not poll task status: " + str(last_err))
        if response["status_code"] >= 400:
            raise RuntimeError("Task poll failed: " + response["body"].decode("utf-8", errors="ignore"))
        payload = json.loads(response["body"].decode("utf-8"))
        status = payload.get("status") or payload.get("state") or payload.get("task_status")
        if status in ("completed", "succeeded", "success", "done", "Ready"):
            return payload
        if status in ("failed", "error", "canceled", "cancelled"):
            raise RuntimeError("Task failed: " + json.dumps(payload, ensure_ascii=False))
        time.sleep(3)


def download_video_content(client, video_id):
    content = client.videos.download_content(video_id)
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


def ensure_api_key():
    api_key = AIHUBMIX_API_KEY
    if not api_key:
        raise RuntimeError("AIHUBMIX_API_KEY is required")
    return api_key


def init_client(api_key, base_url):
    return OpenAI(api_key=api_key, base_url=base_url)


def read_image_as_data_uri(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    encoded = base64.b64encode(raw).decode("utf-8")
    ext = os.path.splitext(path)[1].lower().replace(".", "") or "png"
    mime = "image/" + ("jpeg" if ext in ("jpg", "jpeg") else ext)
    return "data:" + mime + ";base64," + encoded


def fetch_image_bytes_from_any_payload(payload, api_key):
    output = payload.get("output")
    if isinstance(output, list) and output:
        item = output[0]
        if isinstance(item, str) and item.startswith("http"):
            status_code, body = http_get(item, timeout=120)
            if status_code >= 400:
                raise RuntimeError("Download image failed")
            return body
        if isinstance(item, str):
            try:
                return base64.b64decode(item)
            except Exception:
                pass
        if isinstance(item, dict):
            url = item.get("url") or item.get("image")
            if url:
                status_code, body = http_get(url, timeout=120)
                if status_code >= 400:
                    raise RuntimeError("Download image failed")
                return body
            b64 = item.get("b64_json") or item.get("base64")
            if b64:
                return base64.b64decode(b64)
    for key in ("image", "image_url", "url", "urls"):
        val = payload.get(key) or output.get(key)
        val = val[0] if isinstance(val, list) else val
        if isinstance(val, str) and val.startswith("http"):
            headers = {"Authorization": "Bearer " + api_key}
            status_code, body = http_get(val, headers=headers, timeout=120)
            if status_code >= 400:
                status_code, body = http_get(val, timeout=120)
            if status_code >= 400:
                raise RuntimeError("Download image failed")
            return body
    raise RuntimeError("Could not extract image bytes from prediction payload")


def handle_openai_image_generate(args, client):
    response = client.images.generate(
        model=args.model,
        prompt=args.text,
        n=1,
        size="auto",
        quality="auto",
    )
    image_bytes = extract_image_bytes_from_openai_images_response(response)
    return {"kind": "image", "bytes": image_bytes}


def handle_openai_image_edit(args, client):
    with open(args.image, "rb") as image_fh:
        response = client.images.edit(
            model=args.model,
            image=image_fh,
            prompt=args.text,
            n=1,
            size="auto",
            quality="auto",
        )
    image_bytes = extract_image_bytes_from_openai_images_response(response)
    return {"kind": "image", "bytes": image_bytes}


def handle_gemini_chat_image(args, client):
    user_content = [{"type": "text", "text": args.text}]
    if args.image:
        user_content.append({"type": "image_url", "image_url": {"url": read_image_as_data_uri(args.image)}})
    messages = [
        {"role": "system", "content": "aspect_ratio=1:1"},
        {"role": "user", "content": user_content},
    ]
    response = client.chat.completions.create(
        model=args.model,
        messages=messages,
        modalities=["text", "image"],
    )
    image_bytes = extract_image_bytes_from_multimodal_chat(response)
    return {"kind": "image", "bytes": image_bytes}


def handle_prediction_flow(args, api_key, base_url):
    url = base_url.rstrip("/") + "/models/" + args.model + "/predictions"
    inp = {"prompt": args.text, "numberOfImages": 1} if "imagen" in args.model else {"prompt": args.text}
    if args.image:
        if args.image.startswith("http://") or args.image.startswith("https://"):
            inp["input_image"] = args.image
        else:
            inp["input_image"] = read_image_as_data_uri(args.image)
    payload = {"input": inp} if "imagen" in args.model else {"input": inp, "width": 1024, "height": 1024}
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
    }
    status_code, body = http_post_json(url, payload, headers=headers, timeout=120)
    if status_code >= 400:
        raise RuntimeError("Prediction create failed: " + body.decode("utf-8", errors="ignore"))
    create_data = json.loads(body.decode("utf-8"))
    create_data = create_data.get("output")[0] or create_data
    task_id = create_data.get("id") or create_data.get("task_id") or create_data.get("taskId")
    if not task_id:
        urls = create_data.get("urls") or create_data.get("polling_url")
        if isinstance(urls, dict):
            task_id = urls.get("get") or urls.get("status")
    if not task_id:
        if create_data.get("status") in ("completed", "succeeded", "success"):
            image_bytes = fetch_image_bytes_from_any_payload(create_data, api_key)
            return {"kind": "image", "bytes": image_bytes}
        raise RuntimeError("Prediction task id not found in response")
    result = poll_prediction_task(task_id, api_key, base_url)
    image_bytes = fetch_image_bytes_from_any_payload(result, api_key)
    return {"kind": "image", "bytes": image_bytes}


def handle_video_sora(args, client):
    video = client.videos.create(model=args.model, prompt=args.text)
    while True:
        video = client.videos.retrieve(video.id)
        status = getattr(video, "status", "")
        if status in ("completed", "succeeded", "success"):
            break
        if status in ("failed", "error", "canceled", "cancelled"):
            raise RuntimeError("Video generation failed")
        time.sleep(5)
    video_bytes = download_video_content(client, video.id)
    return {"kind": "video", "bytes": video_bytes}


def get_routes():
    return [
        {
            "gen_type": "image_generate",
            "models": {"gpt-image-1.5"},
            "input_mode": "text",
            "handler": "openai_image_generate",
        },
        {
            "gen_type": "image_edit",
            "models": {"gpt-image-1.5"},
            "input_mode": "both",
            "handler": "openai_image_edit",
        },
        {
            "gen_type": "image_generate",
            "models": {"gemini-3.1-flash-image-preview", "gemini-3-pro-image-preview", "gemini-2.5-flash-image"},
            "input_mode": "text_or_both",
            "handler": "gemini_chat_image",
        },
        {
            "gen_type": "image_edit",
            "models": {"gemini-3.1-flash-image-preview", "gemini-3-pro-image-preview", "gemini-2.5-flash-image"},
            "input_mode": "both",
            "handler": "gemini_chat_image",
        },
        {
            "gen_type": "image_generate",
            "models": {
                "flux-2-flex",
                "flux-2-pro",
            },
            "input_mode": "text_or_both",
            "handler": "prediction",
        },
        {
            "gen_type": "image_edit",
            "models": {"flux-2-flex", "flux-2-pro"},
            "input_mode": "both",
            "handler": "prediction",
        },
    ]


def find_route(gen_type, model):
    for route in get_routes():
        if route["gen_type"] == gen_type and model in route["models"]:
            return route
    raise RuntimeError("Unsupported gen-type + model combination")


def validate_inputs(args, route):
    mode = route["input_mode"]
    has_text = bool(args.text and args.text.strip())
    has_image = bool(args.image)
    if mode == "text" and (not has_text or has_image):
        raise RuntimeError("This mode requires --text only")
    if mode == "both" and (not has_text or not has_image):
        raise RuntimeError("This mode requires both --text and --image")
    if mode == "text_or_both" and not has_text:
        raise RuntimeError("This mode requires --text and optionally --image")
    if has_image and not os.path.exists(args.image) and not args.image.startswith("http"):
        raise RuntimeError("Image file does not exist: " + args.image)


def save_output(result, output_path):
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as fh:
        fh.write(result["bytes"])


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gen-type", default='image_generate', choices=["image_generate", "image_edit"])
    parser.add_argument("--model", default="gemini-2.5-flash-image", type=str)
    parser.add_argument("--text", default="Fanta sea")
    parser.add_argument("--image", default=None)
    parser.add_argument("--output", default='./imagen-text_image.png')
    return parser.parse_args()


def main():
    try:
        args = parse_args()
        api_key = ensure_api_key()
        base_url = DEFAULT_BASE_URL
        route = find_route(args.gen_type, args.model)
        validate_inputs(args, route)
        client = init_client(api_key, base_url)

        if route["handler"] == "openai_image_generate":
            result = handle_openai_image_generate(args, client)
        elif route["handler"] == "openai_image_edit":
            result = handle_openai_image_edit(args, client)
        elif route["handler"] == "gemini_chat_image":
            result = handle_gemini_chat_image(args, client)
        elif route["handler"] == "prediction":
            if 'flux' in args.model:
                args.model = 'bfl/' + args.model
            result = handle_prediction_flow(args, api_key, base_url)
        else:
            raise RuntimeError("No handler for route")

        save_output(result, args.output)
        print("Saved " + result["kind"] + " to " + args.output)
    except Exception as err:
        print(str(err), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
