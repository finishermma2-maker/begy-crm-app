---
description: Как запустить и проверить проект Alsor_Bot
---

// turbo-all

## Проверка и запуск проекта

1. Проверить установленные зависимости:
```
pip list --format=columns | findstr /i "aiogram fastapi uvicorn sqlalchemy pydantic aiohttp"
```

2. Установить/обновить зависимости если нужно:
```
pip install -r requirements.txt
```

3. Проверить синтаксис Python файлов:
```
python -c "import py_compile; py_compile.compile('main.py', doraise=True); py_compile.compile('database.py', doraise=True); print('OK: синтаксис корректен')"
```

4. Запустить сервер:
```
python main.py
```

5. Проверить что сервер отвечает (в отдельном терминале):
```
curl http://localhost:8000/
```
