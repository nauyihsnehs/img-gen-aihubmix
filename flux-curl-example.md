## text to image
``` python
# 文生图
curl https://aihubmix.com/v1/models/bfl/flux-2-flex/predictions \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer sk-***" \
    -d '{
  "input": {
    "prompt": "Cinematic shot of a futuristic city at sunset, 85mm lens",
    "width": 1920,
    "height": 1080,
    "safety_tolerance": 2
  }
}'

# 获取结果
curl https://api.aihubmix.com/v1/tasks/api.us1.bfl.*** \
    -H "Authorization: Bearer sk-***" \
    -X GET
```

## image edit

``` python
# 图生图
curl https://aihubmix.com/v1/models/bfl/flux-2-flex/predictions \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer sk-***" \
    -d '{
  "input": {
    "prompt": "<What you want to edit on the image>",
    "input_image": "https://example.com/your-image.jpg"
  }
}'

# 获取结果
curl https://api.aihubmix.com/v1/tasks/api.us1.bfl.*** \
    -H "Authorization: Bearer sk-***" \
    -X GET
```

## flux-1.1

``` python
curl 'https://aihubmix.com/v1/images/generations' \\
-H 'accept: */*' \\
-H 'accept-language: zh-CN' \\
-H 'authorization: Bearer <AIHUBMIX_API_KEY>' \\
-H 'content-type: application/json' \\
--data-raw '{"prompt":"a cat in the garden, cute cartoon","model":"FLUX-1.1-pro","safety_tolerance":6}' \\
| jq -r '.data[0].b64_json' \\
| base64 -D > "$HOME/Desktop/image_extract.png"
```