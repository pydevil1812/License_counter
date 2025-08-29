# =======================
# License Counter Server
# =======================
# Назначение: мониторинг размера и количества файлов в директориях,
# а также количества записей в внешних БД. Отдает данные через REST API.
# =======================

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
import json
from dotenv import load_dotenv

# === Загрузка переменных окружения из .env ===
load_dotenv()


# ===================
# Работа с SQLite БД
# ===================


@contextmanager
def get_db_connection():
    """Контекстный менеджер для подключения к SQLite БД"""
    conn = sqlite3.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def create_table():
    """Создает таблицу folders, если она не существует"""
    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                size INTEGER NOT NULL,
                n_files INTEGER NOT NULL,
                last_updated TEXT NOT NULL
            )
        """
        )
        conn.commit()


def get_path_size_filenum(path):
    """
    Рекурсивно подсчитывает размер (в байтах) и количество файлов по указанному пути.
    Возвращает (размер, количество файлов)
    """
    path_obj = Path(path)
    if not path_obj.exists():
        print(f"⚠ Путь не найден: {path}")
        return 0, 0
    size, n_files = 0, 0
    for f in path_obj.rglob("*"):
        if f.is_file():
            ext = f.suffix.lower().lstrip(".")
            if ext in file_extensions:
                size += f.stat().st_size
                n_files += 1
    return size, n_files


# ====================
# API ресурсы (REST)
# ====================


class ALL(Resource):
    """Возвращает размеры папок, количество файлов и записи из баз данных + лимиты и статус"""

    def get(self):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT path, size FROM folders")
            all_folders = {p: round(s / 1024 / 1024, 2) for p, s in cursor.fetchall()}
            cursor.execute("SELECT path, n_files FROM folders")
            all_files = {p: nf for p, nf in cursor.fetchall()}

        # --- размеры ---
        total_size = sum(all_folders.values())
        limit_mb = limit_size * 1024  # лимит в МБ
        status_size = None
        if total_size > limit_mb:
            status_size = "Exceeding the limit"
        elif total_size > limit_mb * edge_percent and total_size <= limit_mb:
            status_size = "On edge"
        else:
            status_size = "All right"

        # --- файлы ---
        total_files = sum(all_files.values())
        status_files = None
        if total_files > limit_files:
            status_files = "Exceeding the limit"
        elif (
            total_files > limit_files * edge_percent
            and total_files <= limit_files
        ):
            status_files = "On edge"
        else:
            status_files = "All right"

        # --- дашборды ---
        for name, db_info in db.items():
            errors = 0
            try:
                engine = create_engine(db_info["uri"])
                with engine.connect() as conn_db:
                    count = conn_db.execute(
                        text(f"SELECT COUNT(*) FROM {db_info['table']}")
                    ).scalar()
            except Exception as e:
                errors = {}
                errors[name] = str(e)
                status_dashboards = None
            if count > limit_dashboards:
                status_dashboards = "Exceeding the limit"
            elif count > limit_dashboards * edge_percent and count <= limit_dashboards:
                status_dashboards = "On edge"
            else:
                status_dashboards = "All right"

        return {
            "size": {
                "folders": all_folders,
                "total": total_size,
                "limit": limit_mb,
                "status": status_size,
            },
            "n_files": {
                "folders": all_files,
                "total": total_files,
                "limit": limit_files,
                "status": status_files,
            },
            "db_dashboards_count": {
                "databases": count,
                "limit": limit_dashboards,
                "status": status_dashboards,
                "errors": errors,
            },
            "errors": errors,
        }


class AllSizes(Resource):
    """Возвращает размеры всех отслеживаемых папок (в МБ) + лимит и статус"""

    def get(self):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT path, size FROM folders")
            data = {p: round(s / 1024 / 1024, 2) for p, s in cursor.fetchall()}

        total = sum(data.values())
        limit_mb = limit_size * 1024  # лимит хранится в ГБ → переводим в МБ
        status = None
        if total > limit_mb:
            status = "Exceeding the limit"
        elif total > limit_mb * edge_percent and total <= limit_mb:
            status = "On edge"
        else:
            status = "All right"

        return {"folders": data, "total": total, "limit": limit_mb, "status": status}


class AllFilnums(Resource):
    """Возвращает количество файлов во всех папках + лимит и статус"""

    def get(self):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT path, n_files FROM folders")
            data = {p: nf for p, nf in cursor.fetchall()}

        total = sum(data.values())
        status = None
        if total > limit_files:
            status = "Exceeding the limit"
        elif total > limit_files * edge_percent and total <= limit_files:
            status = "On edge"
        else:
            status = "All right"

        return {
            "files_in_folders": data,
            "total": total,
            "limit": limit_files,
            "status": status,
        }


class AllDashboards(Resource):
    """Возвращает количество записей в таблице базы + лимит и статус"""

    def get(self):
        name, db_info = next(iter(db.items()))  # берём единственную базу
        try:
            engine = create_engine(db_info["uri"])
            with engine.connect() as conn_db:
                count = conn_db.execute(
                    text(f"SELECT COUNT(*) FROM {db_info['table']}")
                ).scalar()
        except Exception as e:
            return {"error": str(e)}, 500

        status = None
        if count > limit_dashboards:
            status = "Exceeding the limit"
        elif count > limit_dashboards * edge_percent and count <= limit_dashboards:
            status = "On edge"
        else:
            status = "All right"

        return {
            "database": name,
            "count": count,
            "limit": limit_dashboards,
            "status": status,
        }


class Dashboard(Resource):
    """Возвращает количество записей в таблице указанной базы"""

    def get(self, str):
        try:
            if str not in db:
                return {"error": f"Неизвестная база: {str}"}, 404
            db_info = db[str]
            engine = create_engine(db_info["uri"])
            with engine.connect() as conn_db:
                count = conn_db.execute(
                    text(f"SELECT COUNT(*) FROM {db_info['table']}")
                ).scalar()
                return {str: count}
        except Exception as e:
            return {"error": str(e)}, 500


class SizeByName(Resource):
    """Возвращает размер конкретной папки или общий объем ('total')"""

    def get(self, str):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if str == "total":
                cursor.execute("SELECT SUM(size) FROM folders")
                total = cursor.fetchone()[0] or 0
                return {"total": round(total / 1024 / 1024, 2)}
            else:
                cursor.execute("SELECT size FROM folders WHERE path=?", (str,))
                row = cursor.fetchone()
                return (
                    {str: round(row[0] / 1024 / 1024, 2)}
                    if row
                    else ({"error": "Папка не найдена"}, 404)
                )


class FilenumByName(Resource):
    """Возвращает количество файлов в конкретной папке или общее ('total')"""

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


# ==========================================
# Фоновое обновление БД через временную таблицу
# ==========================================


def update_db_loop():
    """
    Периодически обновляет данные в таблице folders.
    Используется временная таблица folders_temp для безопасного обновления.
    """
    while True:
        start_time = time.time()
        try:
            with get_db_connection() as conn:
                cur = conn.cursor()
                conn.execute("BEGIN")
                cur.execute("DELETE FROM folders")

                now = datetime.now().isoformat()
                for name, path in disk_space.items():
                    size, n_files = get_path_size_filenum(path)
                    cur.execute(
                        "INSERT INTO folders (path, size, n_files, last_updated) VALUES (?, ?, ?, ?)",
                        (name, size, n_files, now),
                    )
                    print(f"{name}: {size} bytes, files: {n_files}, updated: {now}")
                conn.commit()
                print("Data updated successfully")

        except Exception as e:
            conn.rollback()
            print(f"❌ Update error: {e} — rolling back", file=sys.stderr)

        elapsed = time.time() - start_time
        remaining_sleep = cycle - elapsed

        if remaining_sleep > 0:
            print(
                f"⏳ Sleeping for {round(remaining_sleep, 2)} seconds, processing took {round(elapsed, 2)} seconds"
            )
            time.sleep(remaining_sleep)
        else:
            print(
                f"⚠ No sleep, processing took {round(elapsed, 2)} seconds which is >= cycle ({cycle}s)"
            )


# ===========================
# Точка входа — запуск сервера
# ===========================

if __name__ == "__main__":
    # Определяем директорию скрипта
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Загружаем конфигурацию из переменных окружения
    try:
        port = int(os.getenv("PORT", "3000"))
        host = os.getenv("HOST", "0.0.0.0")
        db_path = os.getenv("DB_PATH", os.path.join(script_dir, "folders.db"))
        cycle = int(os.getenv("CYCLE", "60"))
        file_extensions = os.getenv("FILE_EXTENSIONS", "").split(",")
        disk_space_raw = os.getenv("DISK_SPACE", "")
        disk_space = json.loads(disk_space_raw)
        db_raw = os.getenv("DB", "")
        db = json.loads(db_raw)
        limits = os.path.join(script_dir, "license_count.yaml")
        try:
            with open(limits, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                limit_size = config["limit_size"]  # в ГБ
                limit_files = config["limit_files"]
                limit_dashboards = config["limit_dashboards"]
                edge_percent = int(config["edge_percent"])/100
        except Exception:
            print("Лимиты лицензии не найдены", file=sys.stderr)

        # Создание таблицы и запуск фонового обновления
        create_table()
        threading.Thread(target=update_db_loop, daemon=True).start()

    except Exception as e:
        print(f"Config loading error: {e}", file=sys.stderr)

    # Инициализация Flask и REST API
    app = Flask(__name__)
    api = Api()

    # Регистрация маршрутов
    api.add_resource(AllSizes, "/api/size")
    api.add_resource(SizeByName, "/api/size/<str>")
    api.add_resource(FilenumByName, "/api/filenum/<str>")
    api.add_resource(AllFilnums, "/api/filenum")
    api.add_resource(Dashboard, "/api/count/<str>")
    api.add_resource(AllDashboards, "/api/count")
    api.add_resource(ALL, "/api")

    # Главная страница
    @app.route("/")
    def index():
        return render_template("index.html")

    # Запуск сервера
    api.init_app(app)
    app.run(debug=False, port=port, host=host)
