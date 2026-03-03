## google python

``` python
import os
import time
from google import genai
from google.genai import types
from PIL import Image
from io import BytesIO

client = genai.Client(
    api_key="<AIHUBMIX_API_KEY>", # 🔑 换成你在 AiHubMix 生成的密钥
    http_options={"base_url": "https://aihubmix.com/gemini"},
)

# 目前只支持英文 prompt，绘制大量文本的表现较差
response = client.models.generate_images(
    model='imagen-4.0',
    prompt='A minimalist logo for a LLM router market company on a solid white background. trident in a circle as the main symbol, with ONLY text \'InferEra\' below.',
    config=types.GenerateImagesConfig(
        number_of_images=1,
        aspect_ratio="1:1", # supports "1:1", "9:16", "16:9", "3:4", or "4:3".
    )
)

script_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(script_dir, "output")

os.makedirs(output_dir, exist_ok=True)

# 生成时间戳作为文件名前缀，避免文件名冲突
timestamp = int(time.time())

# 保存并显示生成的图片
if response and hasattr(response, 'generated_images') and response.generated_images:
    for i, generated_image in enumerate(response.generated_images):
        try:
            image = Image.open(BytesIO(generated_image.image.image_bytes))
            image.show()
            
            file_name = f"imagen3_{timestamp}_{i+1}.png"
            file_path = os.path.join(output_dir, file_name)
            image.save(file_path)
            
            print(f"图片已保存至：{file_path}")
        except Exception as e:
            print(f"处理图片 {i+1} 时出错：{e}")
else:
    print("错误：未收到有效的图片响应")
    print(f"响应类型：{type(response)}")
    if response:
        print(f"响应属性：{dir(response)}")
        if hasattr(response, 'generated_images'):
            print(f"generated_images 值：{response.generated_images}")
    else:
        print("响应为空，请检查 API 密钥和网络连接")
```

## requests

``` python
import requests
import json

url = f"https://aihubmix.com/v1/models/imagen-4.0/predictions"

headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer <AIHUBMIX_API_KEY>' # 换成你在 AiHubMix 生成的密钥
}

data = {
  "input": {
    "prompt": "A deer drinking in the lake, Sakura petals falling, green and clean water, japanese temple, dappled sunlight, cinematic lighting, expansive view, peace",
    "numberOfImages": 1
  }
}

response = requests.post(url, headers=headers, data=json.dumps(data))

print(response.json())
```

