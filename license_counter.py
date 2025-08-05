# Импортируем всё подряд, потому что вдруг пригодится (даже если не пригодится)
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
from flask import render_template

# ==== Работа с базой ====

@contextmanager
def get_db_connection():
    # Берём соединение с базой, потом аккуратно его закрываем, чтоб база не ругалась
    conn = sqlite3.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()  # Всё, свободен!

def create_table():
    # Создаём новую таблицу folders, если была — сносим нафиг и создаём заново
    with get_db_connection() as conn:
        conn.execute("DROP TABLE IF EXISTS folders")  # Халява, можно создавать с нуля
        conn.execute("""
            CREATE TABLE folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                size INTEGER NOT NULL,
                n_files INTEGER NOT NULL,
                last_updated TEXT NOT NULL
            )
        """)
        conn.commit()  # Не забываем сохранять изменения — база любит порядок

def clear_table():
    # Просто очищаем таблицу, чтобы не было старья
    with get_db_connection() as conn:
        conn.execute("DELETE FROM folders")
        conn.commit()

def insert_folder_size(path, size, n_files):
    # Кидаем данные в базу, не забывая засечь время, когда это произошло
    now = datetime.now().isoformat()
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO folders (path, size, n_files, last_updated) VALUES (?, ?, ?, ?)",
            (path, size, n_files, now),
        )
        conn.commit()

def get_path_size_filenum(path):
    # Считаем размер папки и количество файлов, обходя её рекурсивно
    path_obj = Path(path)
    if not path_obj.exists():
        print(f"⚠ Путь не найден: {path}")  # Если папки нет — предупреждаем
        return 0, 0
    size = 0
    n_files = 0
    for f in path_obj.rglob("*"):
        if f.is_file():
            size += f.stat().st_size  # Размер каждого файла суммируем
            n_files += 1  # И считаем их кол-во
    return size, n_files

# ==== API ресурсы (фичи для нашего сервера) ====

class ALL(Resource):
    def get(self):
        # Забираем всё из базы: размеры, кол-во файлов и данные из других баз
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT path, size FROM folders")
            all_folders = {path: size for path, size in cursor.fetchall()}
            cursor.execute("SELECT path, n_files FROM folders")
            all_folderz = {path: n_files for path, n_files in cursor.fetchall()}
        results = {}
        errors = {}
        # Тут лезем в каждую внешнюю базу и считаем кол-во записей в таблицах
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
                errors[name] = str(e)  # Если что-то сломалось — записываем ошибку
        return {"size": all_folders, "n_files": all_folderz, "db_dashboards_count": results}

class AllDashboards(Resource):
    def get(self):
        # Возвращаем просто кол-во дашбордов из всех баз
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
            resp["errors"] = errors  # Говорим, если где-то было фиаско
        return resp

class Dashboard(Resource):
    def get(self, str):
        # Вернём кол-во дашбордов по конкретному имени базы, если есть
        try:
            if str not in db:
                return {"error": f"Неизвестное имя базы: {str}"}, 404  # Ошибка 404, если базы нет
            db_info = db[str]
            engine = create_engine(db_info["uri"])
            with engine.connect() as conn_db:
                result = conn_db.execute(text(f"SELECT COUNT(*) FROM {db_info['table']}"))
                row = result.fetchone()
                count = row[0] if row else 0
                return {str: count}
        except Exception as e:
            return {"error": f"Ошибка при запросе: {e}"}, 500  # Если упали с ошибкой — 500

class AllSizes(Resource):
    def get(self):
        # Вернём все размеры папок одним махом
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT path, size FROM folders")
            return {"folders": {p: s for p, s in cursor.fetchall()}}

class SizeByName(Resource):
    def get(self, str):
        # Размер конкретной папки или общий размер всех
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if str == "total":
                cursor.execute("SELECT size FROM folders")
                return {"total": sum(row[0] for row in cursor.fetchall())}  # Суммируем всех папок
            else:
                cursor.execute("SELECT size FROM folders WHERE path=?", (str,))
                row = cursor.fetchone()
                return {str: row[0]} if row else ({"error": "Папка не найдена"}, 404)

class AllFilnums(Resource):
    def get(self):
        # Кол-во файлов во всех папках
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT path, n_files FROM folders")
            return {"files_in_folders": {p: f for p, f in cursor.fetchall()}}

class FilenumByName(Resource):
    def get(self, str):
        # Кол-во файлов в конкретной папке или общее
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if str == "total":
                cursor.execute("SELECT n_files FROM folders")
                return {"total": sum(row[0] for row in cursor.fetchall())}
            else:
                cursor.execute("SELECT n_files FROM folders WHERE path=?", (str,))
                row = cursor.fetchone()
                return {str: row[0]} if row else ({"error": "Папка не найдена"}, 404)

# ==== Цикл обновления базы (вечно работающий бодрячок) ====

def update_db_loop():
    while True:
        clear_table()  # Перед началом чистим старое, чтобы не путаться
        for name, path in disk_space.items():
            size, n_files = get_path_size_filenum(path)
            insert_folder_size(name, size, n_files)
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT last_updated FROM folders WHERE path=?", (name,))
                last_updated = cur.fetchone()[0]
            print(f"{name}: {size} байт, файлов: {n_files}, обновлено: {last_updated}")
        time.sleep(cycle)  # Засыпаем на нужное время и снова в бой!
        print("перезаписалось — всё по новой!")

# ==== Запуск всего этого веселья ====

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))  # Где лежит этот файл?
    config_path = os.path.join(script_dir, "config.yaml")  # Конфиг рядом лежит

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)  # Читаем конфиг, чтобы знать что и куда

        disk_space = config["disk_space"]  # Папки для замеров
        db = config["db"]  # Данные по базам (урлы, таблицы)
        cycle = config.get("cycle")  # Интервал обновления
        db_path = os.path.join(script_dir, config.get("db_path"))  # Путь к базе SQLite
        port = config.get("port")  # Порт для сервера
        host = config.get("host")  # Хост (обычно localhost)

        create_table()  # Строим новую табличку в базе

        threading.Thread(target=update_db_loop, daemon=True).start()  # Запускаем вечный цикл обновления в отдельном потоке

    except FileNotFoundError:
        print("Ошибка: config.yaml не найден. Где он, а?")  # Если конфиг потерялся — говорим об этом
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка: {e}")  # Все остальные ошибки сюда
        sys.exit(1)

    app = Flask(__name__)
    api = Api()
    # Навешиваем эндпоинты — чтобы фронтенд и другие могли дергать
    api.add_resource(AllSizes, "/api/size")
    api.add_resource(SizeByName, "/api/size/<str>")
    api.add_resource(FilenumByName, "/api/filenum/<str>")
    api.add_resource(AllFilnums, "/api/filenum")
    api.add_resource(Dashboard, "/api/count/<str>")
    api.add_resource(AllDashboards, "/api/count")
    api.add_resource(ALL, "/api")

    @app.route("/")
    def index():
        # Главная страница — где наша красотища отображается
        return render_template("index.html")

    api.init_app(app)
    app.run(debug=False, port=port, host=host)  # Запускаем сервак, пусть пашет
