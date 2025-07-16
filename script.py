import sys
import yaml
import os
import sqlite3
import time
from pathlib import Path
from flask import Flask
from flask_restful import Api, Resource
import threading


script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config.yaml")


def get_db_connection():
    return sqlite3.connect(db_path)


def create_table():
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS folder_sizes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                size INTEGER NOT NULL
            )
        """)
        conn.commit()


def clear_table():
    with get_db_connection() as conn:
        conn.execute("DELETE FROM folder_sizes")
        conn.commit()


def insert_folder_size(path, size):
    with get_db_connection() as conn:
        conn.execute("INSERT INTO folder_sizes (path, size) VALUES (?, ?)", (path, size))
        conn.commit()


def get_folder_size(path):
    return sum(f.stat().st_size for f in Path(path).rglob('*') if f.is_file())


def update_db_loop():
    while True:
        clear_table()
        for name, path in disk_space.items():
            size = get_folder_size(path)
            insert_folder_size(path, size)
            print(f"{path}: {size} байт записано в БД")
        time.sleep(cycle)
        print("перезаписалось")


try:
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    disk_space = config['disk_space']
    cycle = config.get('cycle')
    db_path = config.get('db_path')
    create_table()

    db_thread = threading.Thread(target=update_db_loop, daemon=True) # создает пото для перезаписи данных в бд (flsk потребовал😡)
    db_thread.start()  # запускает поток

except FileNotFoundError:
    print("Ошибка: config.yaml файл не найден.")
    sys.exit(1)
except Exception as e:
    print(f"Произошла ошибка: {e}")
    sys.exit(1)


app = Flask(__name__)
api = Api()


class Main(Resource):
    def get(self):
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT path, size FROM folder_sizes")
            return cursor.fetchall()


api.add_resource(Main, "/api/main")
api.init_app(app)


if __name__ == "__main__":
    app.run(debug=True, port=3000, host='127.0.0.1')  # в конце поменять на False
