import sys
import yaml
import os
import sqlite3
import time
from pathlib import Path

script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config.yaml")
db_path = os.path.join(script_dir, "foldersizes.db")


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


try:
    create_table()
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    disk_space = config['disk_space']
    cycle = config.get('cycle')

    while True:
        clear_table()
        for name, path in disk_space.items():
            size = get_folder_size(path)
            insert_folder_size(path, size)
            print(f"{path}: {size} байт записано в БД")
        time.sleep(cycle)
        print("перезаписалось")

except FileNotFoundError:
    print("Ошибка: config.yaml файл не найден.")
    sys.exit(1)
except Exception as e:
    print(f"Произошла ошибка: {e}")
    sys.exit(1)
