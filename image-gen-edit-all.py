import argparse
import base64
import json
import os
import sys
import time
from urllib import error, request

from openai import OpenAI

DEFAULT_BASE_URL = "https://aihubmix.com/v1"
DEFAULT_TASK_BASE_URL = "https://api.aihubmix.com/v1"
AIHUBMIX_API_KEY = "sk-4IRRyK6M2O3lPcGDEd1b76710b434b27A35aF09458Fd8330"

ROUTES = {
    "image_generate": {
        "gpt-image-1.5": {"input_mode": "text", "handler": "openai_generate"},
        "gemini-3.1-flash-image-preview": {"input_mode": "text_or_both", "handler": "gemini"},
        "gemini-3-pro-image-preview": {"input_mode": "text_or_both", "handler": "gemini"},
        "gemini-2.5-flash-image": {"input_mode": "text_or_both", "handler": "gemini"},
        "flux-2-flex": {"input_mode": "text_or_both", "handler": "prediction"},
        "flux-2-pro": {"input_mode": "text_or_both", "handler": "prediction"},
    },
    "image_edit": {
        "gpt-image-1.5": {"input_mode": "both", "handler": "openai_edit"},
        "gemini-3.1-flash-image-preview": {"input_mode": "both", "handler": "gemini"},
        "gemini-3-pro-image-preview": {"input_mode": "both", "handler": "gemini"},
        "gemini-2.5-flash-image": {"input_mode": "both", "handler": "gemini"},
        "flux-2-flex": {"input_mode": "both", "handler": "prediction"},
        "flux-2-pro": {"input_mode": "both", "handler": "prediction"},
    },
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


def read_image_as_data_uri(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    encoded = base64.b64encode(raw).decode("utf-8")
    ext = os.path.splitext(path)[1].lower().replace(".", "") or "png"
    mime = "image/" + ("jpeg" if ext in ("jpg", "jpeg") else ext)
    return "data:" + mime + ";base64," + encoded


def decode_openai_image(response):
    data = getattr(response, "data", None)
    if not data or not getattr(data[0], "b64_json", None):
        raise RuntimeError("No b64_json found in image response")
    return base64.b64decode(data[0].b64_json)


def decode_gemini_image(response):
    choices = getattr(response, "choices", None)
    message = getattr(choices[0], "message", None) if choices else None
    parts = getattr(message, "multi_mod_content", None) if message else None
    if not parts:
        raise RuntimeError("No multimodal content in chat response")
    for part in parts:
        if isinstance(part, dict) and part.get("inline_data", {}).get("data"):
            return base64.b64decode(part["inline_data"]["data"])
    raise RuntimeError("No inline image data found in multimodal response")


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


def download_image_from_payload(payload, api_key):
    output = payload.get("output")
    if isinstance(output, list) and output:
        item = output[0]
        if isinstance(item, str):
            if item.startswith("http"):
                code, body = http_get(item, timeout=120)
                if code >= 400:
                    raise RuntimeError("Download image failed")
                return body
            try:
                return base64.b64decode(item)
            except Exception:
                pass
        if isinstance(item, dict):
            url = item.get("url") or item.get("image")
            if url:
                code, body = http_get(url, timeout=120)
                if code >= 400:
                    raise RuntimeError("Download image failed")
                return body
            b64 = item.get("b64_json") or item.get("base64")
            if b64:
                return base64.b64decode(b64)
    for key in ("image", "image_url", "url", "urls"):
        val = payload.get(key)
        if not val and isinstance(output, dict):
            val = output.get(key)
        if isinstance(val, list):
            val = val[0] if val else None
        if isinstance(val, str) and val.startswith("http"):
            code, body = http_get(val, headers={"Authorization": "Bearer " + api_key}, timeout=120)
            if code >= 400:
                code, body = http_get(val, timeout=120)
            if code >= 400:
                raise RuntimeError("Download image failed")
            return body
    raise RuntimeError("Could not extract image bytes from payload")


def handle_openai_generate(args, client):
    response = client.images.generate(model=args.model, prompt=args.text, n=1, size="auto", quality="auto")
    return decode_openai_image(response)


def handle_openai_edit(args, client):
    with open(args.image, "rb") as fh:
        response = client.images.edit(model=args.model, image=fh, prompt=args.text, n=1, size="auto", quality="auto")
    return decode_openai_image(response)


def handle_gemini(args, client):
    user_content = [{"type": "text", "text": args.text}]
    if args.image:
        user_content.append({"type": "image_url", "image_url": {"url": read_image_as_data_uri(args.image)}})
    response = client.chat.completions.create(
        model=args.model,
        messages=[{"role": "system", "content": "aspect_ratio=1:1"}, {"role": "user", "content": user_content}],
        modalities=["text", "image"],
    )
    return decode_gemini_image(response)


def handle_prediction(args, api_key):
    model = "bfl/" + args.model if args.model.startswith("flux-") else args.model
    inp = {"prompt": args.text, "numberOfImages": 1} if "imagen" in model else {"prompt": args.text}
    if args.image:
        inp["input_image"] = args.image if args.image.startswith(("http://", "https://")) else read_image_as_data_uri(args.image)
    payload = {"input": inp} if "imagen" in model else {"input": inp, "width": 1024, "height": 1024}
    url = DEFAULT_BASE_URL.rstrip("/") + "/models/" + model + "/predictions"
    code, body = http_post_json(url, payload, headers={"Authorization": "Bearer " + api_key}, timeout=120)
    if code >= 400:
        raise RuntimeError("Prediction create failed: " + body.decode("utf-8", errors="ignore"))
    created = json.loads(body.decode("utf-8"))
    created = created.get("output", [created])[0]
    task_id = created.get("id") or created.get("task_id") or created.get("taskId")
    if not task_id and isinstance(created.get("urls"), dict):
        task_id = created["urls"].get("get") or created["urls"].get("status")
    if task_id:
        created = poll_task(task_id, api_key)
    return download_image_from_payload(created, api_key)


def find_route(gen_type, model):
    route = ROUTES.get(gen_type, {}).get(model)
    if not route:
        raise RuntimeError("Unsupported gen-type + model combination")
    return route


def validate_inputs(args, mode):
    has_text = bool(args.text and args.text.strip())
    has_image = bool(args.image)
    if mode == "text" and (not has_text or has_image):
        raise RuntimeError("This mode requires --text only")
    if mode == "both" and (not has_text or not has_image):
        raise RuntimeError("This mode requires both --text and --image")
    if mode == "text_or_both" and not has_text:
        raise RuntimeError("This mode requires --text and optionally --image")
    if has_image and not args.image.startswith(("http://", "https://")) and not os.path.exists(args.image):
        raise RuntimeError("Image file does not exist: " + args.image)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gen-type", default="image_generate", choices=["image_generate", "image_edit"])
    parser.add_argument("--model", default="gemini-2.5-flash-image")
    parser.add_argument("--text", default="Fanta sea")
    parser.add_argument("--image", default=None)
    parser.add_argument("--output", default="./imagen-text_image.png")
    return parser.parse_args()


def main():
    try:
        args = parse_args()
        api_key = ensure_api_key()
        route = find_route(args.gen_type, args.model)
        validate_inputs(args, route["input_mode"])
        client = init_client(api_key)
        handlers = {
            "openai_generate": lambda: handle_openai_generate(args, client),
            "openai_edit": lambda: handle_openai_edit(args, client),
            "gemini": lambda: handle_gemini(args, client),
            "prediction": lambda: handle_prediction(args, api_key),
        }
        image_bytes = handlers[route["handler"]]()
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "wb") as fh:
            fh.write(image_bytes)
        print("Saved image to " + args.output)
    except Exception as err:
        print(str(err), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
