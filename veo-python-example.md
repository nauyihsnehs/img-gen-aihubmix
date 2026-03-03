## python

``` python
import openai

client = openai.OpenAI(
  api_key="<AIHUBMIX_API_KEY>",  # Replace with your AIHubMix generated key
  base_url="https://aihubmix.com/v1"
)

response = client.chat.completions.create(
  model="veo-2.0-generate-001",
  messages=[
      {"role": "user", "content": "Hello, how are you?"}
  ]
)

print(response.choices[0].message.content)
```