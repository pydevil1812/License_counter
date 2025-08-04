# Импортируем всё подряд
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
from datetime import datetime
from contextlib import contextmanager
import subprocess, tempfile, textwrap, webbrowser

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
        conn.execute("DROP TABLE IF EXISTS folders")  # пересоздаём таблицу каждый раз
        conn.execute("""
            CREATE TABLE folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                size INTEGER NOT NULL,
                n_files INTEGER NOT NULL,
                last_updated TEXT NOT NULL
            )
        """)
        conn.commit()

def clear_table():
    with get_db_connection() as conn:
        conn.execute("DELETE FROM folders")
        conn.commit()

def insert_folder_size(path, size, n_files):
    now = datetime.now().isoformat()
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO folders (path, size, n_files, last_updated) VALUES (?, ?, ?, ?)",
            (path, size, n_files, now),
        )
        conn.commit()

def get_path_size_filenum(path):
    path_obj = Path(path)
    if not path_obj.exists():
        print(f"⚠ Путь не найден: {path}")
        return 0, 0
    size = 0
    n_files = 0
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
            all_folders = {path: size for path, size in cursor.fetchall()}
            cursor.execute("SELECT path, n_files FROM folders")
            all_folderz = {path: n_files for path, n_files in cursor.fetchall()}
        results = {}
        errors = {}
        for name, db_info in db.items():
            db_uri = db_info["uri"]
            db_table = db_info["table"]
            try:
                engine = create_engine(db_uri)
                with engine.connect() as conn_db:
                    result = conn_db.execute(text(f"SELECT COUNT(*) FROM {db_table}"))
                    row = result.fetchone()
                    count = row[0] if row else 0
                    results[name] = count
            except Exception as e:
                errors[name] = str(e)
        return {"size": all_folders, "n_files": all_folderz, "db_dashboards_count": results}

class AllDashboards(Resource):
    def get(self):
        results = {}
        errors = {}
        for name, db_info in db.items():
            db_uri = db_info["uri"]
            db_table = db_info["table"]
            try:
                engine = create_engine(db_uri)
                with engine.connect() as conn_db:
                    result = conn_db.execute(text(f"SELECT COUNT(*) FROM {db_table}"))
                    row = result.fetchone()
                    count = row[0] if row else 0
                    results[name] = count
            except Exception as e:
                errors[name] = str(e)
        resp = {"db_dashboards_count": results}
        if errors:
            resp["errors"] = errors
        return resp

class Dashboard(Resource):
    def get(self, str):
        try:
            if str not in db:
                return {"error": f"Неизвестное имя базы: {str}"}, 404
            db_info = db[str]
            engine = create_engine(db_info["uri"])
            with engine.connect() as conn_db:
                result = conn_db.execute(text(f"SELECT COUNT(*) FROM {db_info['table']}"))
                row = result.fetchone()
                count = row[0] if row else 0
                return {str: count}
        except Exception as e:
            return {"error": f"Ошибка при запросе: {e}"}, 500

class AllSizes(Resource):
    def get(self):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT path, size FROM folders")
            return {"folders": {p: s for p, s in cursor.fetchall()}}

class SizeByName(Resource):
    def get(self, str):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if str == "total":
                cursor.execute("SELECT size FROM folders")
                return {"total": sum(row[0] for row in cursor.fetchall())}
            else:
                cursor.execute("SELECT size FROM folders WHERE path=?", (str,))
                row = cursor.fetchone()
                return {str: row[0]} if row else ({"error": "Папка не найдена"}, 404)

class AllFilnums(Resource):
    def get(self):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT path, n_files FROM folders")
            return {"files_in_folders": {p: f for p, f in cursor.fetchall()}}

class FilenumByName(Resource):
    def get(self, str):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if str == "total":
                cursor.execute("SELECT n_files FROM folders")
                return {"total": sum(row[0] for row in cursor.fetchall())}
            else:
                cursor.execute("SELECT n_files FROM folders WHERE path=?", (str,))
                row = cursor.fetchone()
                return {str: row[0]} if row else ({"error": "Папка не найдена"}, 404)

# ==== Цикл обновления базы ====

def update_db_loop():
    while True:
        clear_table()
        for name, path in disk_space.items():
            size, n_files = get_path_size_filenum(path)
            insert_folder_size(name, size, n_files)
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT last_updated FROM folders WHERE path=?", (name,))
                last_updated = cur.fetchone()[0]
            print(f"{name}: {size} байт, файлов: {n_files}, обновлено: {last_updated}")
        time.sleep(cycle)
        print("перезаписалось")

# ==== Запуск приложения ====

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.yaml")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        disk_space = config["disk_space"]
        db = config["db"]
        cycle = config.get("cycle")
        db_path = os.path.join(script_dir, config.get("db_path"))
        port = config.get("port")
        host = config.get("host")

        create_table()  # пересоздаём таблицу

        threading.Thread(target=update_db_loop, daemon=True).start()

    except FileNotFoundError:
        print("Ошибка: config.yaml не найден.")
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
    api.init_app(app)

    def run_streamlit():
        frontend_code = textwrap.dedent(f"""
        import streamlit as st
        import pandas as pd
        import requests
        from streamlit_autorefresh import st_autorefresh

        API_BASE = "http://{host}:{port}/api"
        st_autorefresh(interval=5000, key="refresh")

        st.set_page_config(page_title="📊 Мониторинг API", layout="wide")
        st.title("📊 Мониторинг API")

        tabs = st.tabs(["Общий обзор", "Размеры папок", "Файлы", "Dashboards"])

        def bytes_to_mb(b): return round(b / (1024*1024), 2)

        with tabs[0]:
            try:
                data = requests.get(API_BASE).json()
                size_df = pd.DataFrame([(k, bytes_to_mb(v)) for k,v in data["size"].items()], columns=["Папка","Размер (МБ)"])
                files_df = pd.DataFrame(data["n_files"].items(), columns=["Папка","Файлы"])
                dash_df = pd.DataFrame(data["db_dashboards_count"].items(), columns=["База","Dashboards"])
                st.subheader("Размеры папок (МБ)")
                st.dataframe(size_df)
                st.subheader("Файлы")
                st.dataframe(files_df)
                st.subheader("Dashboards")
                st.dataframe(dash_df)
            except Exception as e:
                st.error(e)

        with tabs[1]:
            try:
                data = requests.get(f"{{API_BASE}}/size").json()
                df = pd.DataFrame([(k, bytes_to_mb(v)) for k,v in data["folders"].items()], columns=["Папка","Размер (МБ)"])
                st.dataframe(df)
            except Exception as e:
                st.error(e)

        with tabs[2]:
            try:
                data = requests.get(f"{{API_BASE}}/filenum").json()
                df = pd.DataFrame(data["files_in_folders"].items(), columns=["Папка","Файлы"])
                st.dataframe(df)
            except Exception as e:
                st.error(e)

        with tabs[3]:
            try:
                data = requests.get(f"{{API_BASE}}/count").json()
                df = pd.DataFrame(data["db_dashboards_count"].items(), columns=["База","Dashboards"])
                st.dataframe(df)
            except Exception as e:
                st.error(e)
        """)
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tmp:
            tmp.write(frontend_code)
            tmp_path = tmp.name
        subprocess.Popen(["streamlit", "run", tmp_path])
        time.sleep(3)
        webbrowser.open("http://localhost:8501")

    threading.Thread(target=run_streamlit, daemon=True).start()
    app.run(debug=False, port=port, host=host)
