# 📊 License Counter

License Counter — это веб-приложение на Flask, предназначенное для мониторинга объема данных и количества файлов в заданных директориях, а также отображения количества записей в таблицах внешних баз данных.

## 🚀 Возможности

- Подсчет объема данных (в мегабайтах) в указанных папках
- Подсчет количества файлов в этих папках
- Получение количества записей в таблицах внешних баз данных
- Веб-интерфейс для отображения информации
- API с несколькими endpoint'ами
- Фоновое обновление данных каждые `N` секунд


```

## ⚙️ Установка

### 1. Клонирование репозитория

```bash
git clone https://github.com/pydevil1812/License_counter.git
cd License_counter
```

### 2. Установка зависимостей

#### Через Docker (рекомендуется)

```bash
docker build -t license_counter .

```

#### Локально (если без Docker)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 📄 Пример .env файла

```env
PORT=3000
HOST=0.0.0.0
DB_PATH=folders.db
CYCLE=15
DISK_SPACE={"path1":"/License_counter/test","path2":"/License_counter/end"}
DB={"name1":{"uri":"sqlite:///folders.db","table":"folders"}}
```

## ▶️ Запуск

### Через Docker

```bash
docker run -p 3000:3000 --name license_counter license_counter
```

### Локально

```bash
python license_counter.py
```

После запуска, приложение будет доступно по адресу:  
📍 `http://localhost:3000`

## 🖥 Интерфейс

На главной странице отображается:

- Размер каждой директории и общий размер
- Количество файлов в каждой директории и общее количество
- Количество записей в указанных базах данных

## 🔌 API Endpoints

| Endpoint | Описание |
|---------|----------|
| `/api` | Возвращает размеры, количество файлов и количество записей в БД |
| `/api/size` | Размер всех папок |
| `/api/size/<name>` | Размер конкретной папки или `total` |
| `/api/filenum` | Количество файлов во всех папках |
| `/api/filenum/<name>` | Количество файлов в конкретной папке или `total` |
| `/api/count` | Количество записей в каждой базе |
| `/api/count/<name>` | Количество записей в конкретной базе |

## 🔄 Обновление данных

Скрипт запускает фоновый поток, который:

- Каждые `CYCLE` секунд (из `.env`) пересчитывает размер и количество файлов в директориях
- Обновляет таблицу `folders` в SQLite базе

## 🛠 Технологии

- Python 3.12
- Flask + Flask-RESTful
- SQLite
- SQLAlchemy
- Docker + Docker Compose
- HTML / CSS / JavaScript (Vanilla)

## 📦 Зависимости

Список библиотек в `requirements.txt`:

```
PyYAML==6.0.2
pathlib==1.0.1
Flask==3.1.1
Flask-RESTful==0.3.10
SQLAlchemy==2.0.41
python-dotenv==1.1.1
```