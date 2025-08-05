# Импортируем всё подряд, потому что вдруг пригодится
import sys
import yaml
import os
import sqlite3
import time
from pathlib import Path
from flask import Flask, render_template
from flask_restful import Api, Resource
import threading
from sqlalchemy import create_engine, text
from datetime import datetime
from contextlib import contextmanager

# ==== Работа с базой ====

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()

def create_table():
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                size INTEGER NOT NULL,
                n_files INTEGER NOT NULL,
                last_updated TEXT NOT NULL
            )
        """)
        conn.commit()

def get_path_size_filenum(path):
    path_obj = Path(path)
    if not path_obj.exists():
        print(f"⚠ Путь не найден: {path}")
        return 0, 0
    size, n_files = 0, 0
    for f in path_obj.rglob("*"):
        if f.is_file():
            size += f.stat().st_size
            n_files += 1
    return size, n_files

# ==== API ресурсы ====

class ALL(Resource):
    def get(self):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT path, size FROM folders")
            all_folders = {p: round(s/1024/1024, 2) for p, s in cursor.fetchall()}
            cursor.execute("SELECT path, n_files FROM folders")
            all_files = {p: nf for p, nf in cursor.fetchall()}

        results, errors = {}, {}
        for name, db_info in db.items():
            try:
                engine = create_engine(db_info["uri"])
                with engine.connect() as conn_db:
                    count = conn_db.execute(text(f"SELECT COUNT(*) FROM {db_info['table']}")).scalar()
                    results[name] = count
            except Exception as e:
                errors[name] = str(e)
        return {"size": all_folders, "n_files": all_files, "db_dashboards_count": results, "errors": errors}

class AllDashboards(Resource):
    def get(self):
        results, errors = {}, {}
        for name, db_info in db.items():
            try:
                engine = create_engine(db_info["uri"])
                with engine.connect() as conn_db:
                    count = conn_db.execute(text(f"SELECT COUNT(*) FROM {db_info['table']}")).scalar()
                    results[name] = count
            except Exception as e:
                errors[name] = str(e)
        return {"db_dashboards_count": results, "errors": errors}

class Dashboard(Resource):
    def get(self, str):
        try:
            if str not in db:
                return {"error": f"Неизвестная база: {str}"}, 404
            db_info = db[str]
            engine = create_engine(db_info["uri"])
            with engine.connect() as conn_db:
                count = conn_db.execute(text(f"SELECT COUNT(*) FROM {db_info['table']}")).scalar()
                return {str: count}
        except Exception as e:
            return {"error": str(e)}, 500

class AllSizes(Resource):
    def get(self):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT path, size FROM folders")
            return {"folders": {p: round(s/1024/1024, 2) for p, s in cursor.fetchall()}}

class SizeByName(Resource):
    def get(self, str):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if str == "total":
                cursor.execute("SELECT SUM(size) FROM folders")
                total = cursor.fetchone()[0] or 0
                return {"total": round(total/1024/1024, 2)}
            else:
                cursor.execute("SELECT size FROM folders WHERE path=?", (str,))
                row = cursor.fetchone()
                return {str: round(row[0]/1024/1024, 2)} if row else ({"error": "Папка не найдена"}, 404)

class AllFilnums(Resource):
    def get(self):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT path, n_files FROM folders")
            return {"files_in_folders": {p: nf for p, nf in cursor.fetchall()}}

class FilenumByName(Resource):
    def get(self, str):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if str == "total":
                cursor.execute("SELECT SUM(n_files) FROM folders")
                total = cursor.fetchone()[0] or 0
                return {"total": total}
            else:
                cursor.execute("SELECT n_files FROM folders WHERE path=?", (str,))
                row = cursor.fetchone()
                return {str: row[0]} if row else ({"error": "Папка не найдена"}, 404)

# ==== Безопасное обновление через временную таблицу ====

def update_db_loop():
    while True:
        try:
            with get_db_connection() as conn:
                cur = conn.cursor()
                #начало транзакции
                conn.execute("BEGIN")

                # Создаем временную таблицу
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS folders_temp (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        path TEXT NOT NULL,
                        size INTEGER NOT NULL,
                        n_files INTEGER NOT NULL,
                        last_updated TEXT NOT NULL
                    )
                """)
                cur.execute("DELETE FROM folders_temp")

                # Заполняем временную таблицу новыми данными
                now = datetime.now().isoformat()
                for name, path in disk_space.items():
                    size, n_files = get_path_size_filenum(path)
                    cur.execute(
                        "INSERT INTO folders_temp (path, size, n_files, last_updated) VALUES (?, ?, ?, ?)",
                        (name, size, n_files, now)
                    )
                    print(f"{name}: {size} байт, файлов: {n_files}, обновлено: {now}")

                # Заменяем старую таблицу новыми данными
                cur.execute("DELETE FROM folders")
                cur.execute("""
                    INSERT INTO folders (path, size, n_files, last_updated)
                    SELECT path, size, n_files, last_updated FROM folders_temp
                """)
                
                conn.commit() # Фиксирует изменения если все прошло успешно
                print("Данные обновлены")

        except Exception as e:
            conn.rollback() # откатывает изменения при любой ошибке, чтобы база вернулась к прежнему состоянию
            print(f"❌ Ошибка обновления: {e} — откат изменений")

        time.sleep(cycle)

# ==== Запуск ====

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.yaml")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        disk_space = config["disk_space"]
        db = config["db"]
        cycle = config.get("cycle", 60)
        db_path = os.path.join(script_dir, config.get("db_path", "data.db"))
        port = config.get("port", 5000)
        host = config.get("host", "127.0.0.1")

        create_table()

        threading.Thread(target=update_db_loop, daemon=True).start()

    except FileNotFoundError:
        print("Ошибка: config.yaml не найден")
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка: {e}")
        sys.exit(1)

    app = Flask(__name__)
    api = Api()
    api.add_resource(AllSizes, "/api/size")
    api.add_resource(SizeByName, "/api/size/<str>")
    api.add_resource(FilenumByName, "/api/filenum/<str>")
    api.add_resource(AllFilnums, "/api/filenum")
    api.add_resource(Dashboard, "/api/count/<str>")
    api.add_resource(AllDashboards, "/api/count")
    api.add_resource(ALL, "/api")

    @app.route("/")
    def index():
        return render_template("index.html")

    api.init_app(app)
    app.run(debug=False, port=port, host=host)
