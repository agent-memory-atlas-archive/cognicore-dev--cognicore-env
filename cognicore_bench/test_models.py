import os, requests, json

env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.startswith('GROQ_API_KEY='):
                os.environ['GROQ_API_KEY'] = line.strip().split('=', 1)[1]

resp = requests.get('https://api.groq.com/openai/v1/models', headers={'Authorization': f"Bearer {os.environ.get('GROQ_API_KEY')}"})
print(json.dumps(resp.json(), indent=2))
