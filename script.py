import sys
import yaml
import os
import sqlite3
import time
from pathlib import Path
from flask import Flask, jsonify
from flask_restful import Api, Resource
import threading


class AllSizes(Resource):
    def get(self):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT path, size FROM folders")
            rows = cursor.fetchall()
            all_folders = {path: size for path, size in rows}
            return jsonify({"folders": all_folders})


class SizeByName(Resource):
    def get(self, str):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if str == "total":
                cursor.execute("SELECT size FROM folders")
                sizes = [row[0] for row in cursor.fetchall()]
                return jsonify({"total": sum(sizes)})
            else:
                cursor.execute("SELECT size FROM folders WHERE path = ?", (str,))
                row = cursor.fetchone()
                if row:
                    return jsonify({str: row[0]})
                return jsonify({"error": "Папка не найдена"}), 404


class FilenumByName(Resource):
    def get(self, str):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if str == "total":
                cursor.execute("SELECT filenum FROM folders")
                Filenums = [row[0] for row in cursor.fetchall()]
                return jsonify({"total": sum(Filenums)})
            else:
                cursor.execute("SELECT filenum FROM folders WHERE path = ?", (str,))
                row = cursor.fetchone()
                if row:
                    return jsonify({str: row[0]})
                return jsonify({"error": "Папка не найдена"}), 404


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.yaml")

    def get_db_connection():
        return sqlite3.connect(db_path)

    def create_table():
        with get_db_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS folders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    filenum INTEGER NOT NULL
                )
            """
            )
            conn.commit()

    def clear_table():
        with get_db_connection() as conn:
            conn.execute("DELETE FROM folders")
            conn.commit()

    def insert_folder_size(path, size, filenum):
        with get_db_connection() as conn:
            conn.execute("INSERT INTO folders (path, size, filenum) VALUES (?, ?, ?)", (path, size, filenum))
            conn.commit()

    def get_path_size(path):
        path_obj = Path(path)
        if not path_obj.exists():
            print(f"⚠ Путь не найден: {path}")
            return 0
        return sum(f.stat().st_size for f in path_obj.rglob("*") if f.is_file())

    def filenum_in_folder(path):
        file_count = 0
        for root, dirs, files in os.walk(path):
            for file in files:
                full_path = os.path.join(root, file)
                if os.path.isfile(full_path):
                    file_count += 1
        return file_count

    def update_db_loop():
        while True:
            clear_table()
            for name, path in disk_space.items():
                size = get_path_size(path)
                filenum = filenum_in_folder(path)
                insert_folder_size(name, size, filenum)
                print(f"{name}: {size} байт записано в БД и столько файлов: {filenum}")
            time.sleep(cycle)
            print("перезаписалось")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        disk_space = config["disk_space"]
        cycle = config.get("cycle")
        dbpath = config.get("db_path")
        port = config.get("port")
        host = config.get("host")
        db_path = os.path.join(script_dir, dbpath)
        create_table()

        db_thread = threading.Thread(
            target=update_db_loop, daemon=True
        )  # создает поток для перезаписи данных в бд (flsk потребовал😡)
        db_thread.start()  # запускает поток

    except FileNotFoundError:
        print("Ошибка: config.yaml файл не найден.")
        sys.exit(1)
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        sys.exit(1)
    app = Flask(__name__)
    api = Api()
    api.add_resource(AllSizes, "/api/size")
    api.add_resource(SizeByName, "/api/size/<str>")
    api.add_resource(FilenumByName, "/api/filenum/<str>")
    #api.add_resource(AllFilenums, "/api/filenum")
    api.init_app(app)
    app.run(debug=False, port=port, host=host)  # TODO: в конце поменять на False
