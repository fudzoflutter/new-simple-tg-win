"""
Launcher: ``python run.py``

Kept as a separate one-liner file so deployment commands stay trivial
(systemd, Docker, `pm2 start run.py`, ...).
"""

from app.main import main

if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
