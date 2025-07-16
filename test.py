import requests
import os
import yaml
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config.yaml")

try:
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    api = config.get('api')
    res = requests.get(api)
    print(res.json())

except FileNotFoundError:
    print("Ошибка: config.yaml файл не найден.")
    sys.exit(1)
except Exception as e:
    print(f"Произошла ошибка: {e}")
    sys.exit(1)
