## image generate

``` python
import base64
from openai import OpenAI

client = OpenAI(
    api_key="<AIHUBMIX_API_KEY>",  # 换成你在 AiHubMix 生成的密钥
    base_url="https://aihubmix.com/v1"
)

response = client.images.generate(
    model="gpt-image-1.5",
    prompt="A vase of flowers on a table, with intense contrasting colors and thick, expressive brushstrokes. Render the image so it looks painted in Fauvist style.",
    n=1, # 生成图片数量，支持1-10
    size="auto", # 图像尺寸，支持参数：1024x1024, 1024x1536, 1536x1024，auto(默认值)
    quality="auto", # 图像质量，支持参数：high, medium, low，auto(默认值）
)

image_bytes = base64.b64decode(response.data[0].b64_json)
with open("output.png", "wb") as f:
    f.write(image_bytes)
```

## image edit

``` python
import base64
from openai import OpenAI

client = OpenAI(
    api_key="<AIHUBMIX_API_KEY>",  # 换成你在 AiHubMix 生成的密钥
    base_url="https://aihubmix.com/v1"
)

prompt = """
Generate a photorealistic image of a gift basket on a white background 
labeled 'Relax & Unwind' with a ribbon and handwriting-like font, 
containing all the items in the reference pictures.
"""

# 确保你的当前目录下有这些图片文件
result = client.images.edit(
    model="gpt-image-1.5",
    image=open("body-lotion.png", "rb"),
    mask=open("mask.png", "rb"),
    prompt=prompt,
    n=1, # 生成图片数量，支持1-10
    size="auto", # 图像尺寸，支持参数：1024x1024, 1024x1536, 1536x1024，auto(默认值)
    quality="auto", # 图像质量，支持参数：high, medium, low，auto(默认值）
)

image_base64 = result.data[0].b64_json
image_bytes = base64.b64decode(image_base64)

# 将图片保存到文件
with open("gift-basket.png", "wb") as f:
    f.write(image_bytes)
```

## python response

``` python
import base64
from openai import OpenAI

client = OpenAI(
    api_key="<AIHUBMIX_API_KEY>",  # 换成你在 AiHubMix 生成的密钥
    base_url="https://aihubmix.com/v1"
)

# 通过 gpt-4.1 使用 chat completions 接口调用图片生成
response = client.chat.completions.create(
    model="gpt-4.1",
    messages=[
        {
            "role": "user",
            "content": "请使用 gpt-image-1.5 生成图片：A cute baby sea otter"
        }
    ],
    tools=[
        {
            "type": "function",
            "function": {
                "name": "generate_image",
                "description": "使用 gpt-image-1.5 生成图片",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "图片生成的提示词"
                        },
                        "size": {
                            "type": "string",
                            "description": "图片尺寸",
                            "enum": ["1024x1024", "512x512", "256x256"]
                        }
                    },
                    "required": ["prompt"]
                }
            }
        }
    ],
    tool_choice="auto"
)

if response.choices[0].message.tool_calls:
    tool_call = response.choices[0].message.tool_calls[0]
    import json
    args = json.loads(tool_call.function.arguments)
    
    image_response = client.images.generate(
        model="gpt-image-1.5",
        prompt=args.get("prompt", "A cute baby sea otter"),
        n=1,
        size=args.get("size", "1024x1024")
    )
    
    image_bytes = base64.b64decode(image_response.data[0].b64_json)
    with open("output.png", "wb") as f:
        f.write(image_bytes)
    
    print("图片生成成功！")
else:
    print("未能调用图片生成工具")
```