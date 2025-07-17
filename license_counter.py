# Импортируем всё подряд, потому что иначе не работает
import sys
import yaml
import os
import sqlite3
import time
from pathlib import Path
from flask import Flask
from flask_restful import Api, Resource
import threading
from sqlalchemy import create_engine, text


# класс, который возвращает всё сразу (моно пользоваться только программистам уровня senior, остальные не настолько ленивые)
class ALL(Resource):
    def get(self):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT path, size FROM folders")
            rows = cursor.fetchall()
            all_folders = {path: size for path, size in rows}
            cursor.execute("SELECT path, filenum FROM folders")
            rowz = cursor.fetchall()
            all_folderz = {path: filenum for path, filenum in rowz}
            results = {}
            errors = {}
            for name, db_info in db.items():
                db_uri = db_info["uri"]
                db_table = db_info["table"]
                try:
                    engine = create_engine(db_uri)
                    with engine.connect() as conn:
                        result = conn.execute(text(f"SELECT COUNT(*) FROM {db_table}"))
                        row = result.fetchone()
                        count = row[0] if row else 0
                        results[name] = count
                except Exception as e:
                    errors[name] = str(e)
            return {"size": all_folders, "filenum": all_folderz, "db_dashboards_count": results}


# возвращает статистику по всем базам, если вдруг надо
class AllDashboards(Resource):
    def get(self):
        results = {}
        errors = {}
        for name, db_info in db.items():
            db_uri = db_info["uri"]
            db_table = db_info["table"]
            try:
                engine = create_engine(db_uri)
                with engine.connect() as conn:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {db_table}"))
                    row = result.fetchone()
                    count = row[0] if row else 0
                    results[name] = count
            except Exception as e:
                errors[name] = str(e)
        response = {"db_dashboards_count": results}
        if errors:
            response["errors"] = errors
        return response


# Возвращает статистику по одной базе, если вдруг очень надо
class Dashboard(Resource):
    def get(self, str):
        try:
            if str not in db:
                return {"error": f"Неизвестное имя базы: {str}"}, 404

            db_info = db[str]
            db_uri = db_info["uri"]
            db_table = db_info["table"]

            engine = create_engine(db_uri)

            with engine.connect() as conn:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {db_table}"))
                row = result.fetchone()
                count = row[0] if row else 0
                return {str: count}

        except Exception as e:
            return {"error": f"Ошибка при запросе: {e}"}, 500


# Возвращает размеры всех папок, потому что почему бы и нет
class AllSizes(Resource):
    def get(self):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT path, size FROM folders")
            rows = cursor.fetchall()
            all_folders = {path: size for path, size in rows}
            return {"folders": all_folders}


# Возвращает размер по имени папки или total, если лень указывать имя
class SizeByName(Resource):
    def get(self, str):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if str == "total":
                cursor.execute("SELECT size FROM folders")
                sizes = [row[0] for row in cursor.fetchall()]
                return {"total": sum(sizes)}
            else:
                cursor.execute("SELECT size FROM folders WHERE path = ?", (str,))
                row = cursor.fetchone()
                if row:
                    return {str: row[0]}
                return {"error": "Папка не найдена"}, 404


# Возвращает количество файлов во всех папках, потому что надо
class AllFilnums(Resource):
    def get(self):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT path, filenum FROM folders")
            rows = cursor.fetchall()
            all_folders = {path: filenum for path, filenum in rows}
            return {"files_in_folders": all_folders}


# Возвращает количество файлов по имени папки или total, если лень
class FilenumByName(Resource):
    def get(self, str):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if str == "total":
                cursor.execute("SELECT filenum FROM folders")
                filenums = [row[0] for row in cursor.fetchall()]
                return {"total": sum(filenums)}
            else:
                cursor.execute("SELECT filenum FROM folders WHERE path = ?", (str,))
                row = cursor.fetchone()
                if row:
                    return {str: row[0]}
                return {"error": "Папка не найдена"}, 404


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.yaml")

    # возвращает соединение с базой, ничего особенного
    def get_db_connection():
        return sqlite3.connect(db_path)

    # Создаёт таблицу, если вдруг её нет
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

    # Чистит таблицу, потому что проще перезаписать всё заново
    def clear_table():
        with get_db_connection() as conn:
            conn.execute("DELETE FROM folders")
            conn.commit()

    # Вставляет размер и количество файлов в базу, потому что надо
    def insert_folder_size(path, size, filenum):
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO folders (path, size, filenum) VALUES (?, ?, ?)",
                (path, size, filenum),
            )
            conn.commit()

    # Считает размер и количество файлов в папке, потому что никто другой не будет
    def get_path_size_filenum(path):
        path_obj = Path(path)
        if not path_obj.exists():
            print(f"⚠ Путь не найден: {path}")
            return 0
        size = 0
        filenum = 0
        for f in path_obj.rglob("*"):
            if f.is_file():
                size += f.stat().st_size
                filenum += 1
        return size, filenum

    # Тут раньше была функция для подсчёта файлов, но она не нужна
    """def filenum_in_folder(path):
        file_count = 0
        for root, dirs, files in os.walk(path):
            for file in files:
                full_path = os.path.join(root, file)
                if os.path.isfile(full_path):
                    file_count += 1
        return file_count"""

    # Бесконечно обновляет базу, потому что Flask не умеет по-другому
    def update_db_loop():
        while True:
            clear_table()
            for name, path in disk_space.items():
                size, filenum = get_path_size_filenum(path)
                # filenum = filenum_in_folder(path)
                insert_folder_size(name, size, filenum)
                print(f"{name}: {size} байт записано в БД и столько файлов: {filenum}")
            time.sleep(cycle)
            print("перезаписалось")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        disk_space = config["disk_space"]
        db = config["db"]
        cycle = config.get("cycle")
        dbpath = config.get("db_path")
        port = config.get("port")
        host = config.get("host")
        db_path = os.path.join(script_dir, dbpath)
        create_table()

        # Поток для обновления базы, потому что Flask иначе ругается
        db_thread = threading.Thread(
            target=update_db_loop, daemon=True
        )
        db_thread.start()

    except FileNotFoundError:
        print("Ошибка: config.yaml файл не найден.")
        sys.exit(1)
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        sys.exit(1)

    # запускается Flask, потому что надо же как-то отдавать API
    app = Flask(__name__)
    api = Api()
    api.add_resource(AllSizes, "/api/size")
    api.add_resource(SizeByName, "/api/size/<str>")
    api.add_resource(FilenumByName, "/api/filenum/<str>")
    api.add_resource(AllFilnums, "/api/filenum")
    api.add_resource(Dashboard, "/api/count/<str>")
    api.add_resource(AllDashboards, "/api/count")
    api.add_resource(ALL, '/api')
    api.init_app(app)
    app.run(debug=False, port=port, host=host)