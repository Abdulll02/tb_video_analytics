import asyncio
import ijson
import os
import logging
from datetime import datetime
from database import get_db_pool

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_PATH = os.getenv("JSON_DATA_PATH", "data/data.json")

"""
Немножко документации о загрузке данных в бд.
При первом запуске скрипт load_data.py будет загружать данные. Так как файл большой (500к+), 
это может занять от 30 секунд до пары минут в зависимости от скорости диска. 
В логах контейнера bot вы можете увидеть "Starting data loading..." и затем "Data loading finished successfully". 
Только после этого бот начнет отвечать.
ijson позволяет читать файл любого размера, не потребляя память. 
executemany отправляет данные пачками по 1000 штук, что значительно быстрее построчной вставки.
"""

def parse_iso_date(date_str):
    """Превращает строку ISO 8601 в объект datetime, понятный для postgres"""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except ValueError:
        return None

async def load_json_to_db():
    if not os.path.exists(DATA_PATH):
        logger.warning(f"File {DATA_PATH} not found. Skipping data loading.")
        return

    pool = await get_db_pool()
    
    # 1. Проверка на наличие данных (исправленная логика без блокировки пула)
    should_skip = False
    existing_count = 0
    try:
        async with pool.acquire() as conn:
            existing_count = await conn.fetchval("SELECT COUNT(*) FROM videos")
            if existing_count > 0:
                should_skip = True
    except Exception as e:
        logger.error(f"Error checking database status: {e}")

    if should_skip:
        logger.info(f"Database already contains {existing_count} videos. Skipping load.")
        await pool.close() # Теперь закрытие пройдет мгновенно
        return

    # 2. Если данных нет, начинаем загрузку
    logger.info("Starting data loading... (This may take a while)")
    
    videos_batch = []
    snapshots_batch = []
    BATCH_SIZE = 1000
    total_videos = 0

    try:
        async with pool.acquire() as conn:
            with open(DATA_PATH, 'rb') as f:
                # Ищем массив внутри ключа "videos"
                videos_iterator = ijson.items(f, 'videos.item')
                
                for video in videos_iterator:
                    total_videos += 1
                    
                    if total_videos % 1000 == 0:
                        logger.info(f"Processing video #{total_videos}...")

                    # Подготовка данных видео
                    v_data = (
                        video['id'],
                        video['creator_id'],
                        parse_iso_date(video['video_created_at']),
                        video['views_count'],
                        video['likes_count'],
                        video['comments_count'],
                        video['reports_count'],
                        parse_iso_date(video.get('created_at')),
                        parse_iso_date(video.get('updated_at'))
                    )
                    videos_batch.append(v_data)

                    # Подготовка данных снапшотов
                    if 'snapshots' in video and video['snapshots']:
                        for snap in video['snapshots']:
                            s_data = (
                                snap['id'],
                                snap['video_id'],
                                snap['views_count'],
                                snap['likes_count'],
                                snap['comments_count'],
                                snap['reports_count'],
                                snap['delta_views_count'],
                                snap['delta_likes_count'],
                                snap['delta_comments_count'],
                                snap['delta_reports_count'],
                                parse_iso_date(snap['created_at']),
                                parse_iso_date(snap.get('updated_at'))
                            )
                            snapshots_batch.append(s_data)

                    # Вставка пачками
                    if len(videos_batch) >= BATCH_SIZE:
                        await insert_batch(conn, videos_batch, snapshots_batch)
                        videos_batch = []
                        snapshots_batch = []

                # Вставка остатков
                if videos_batch or snapshots_batch:
                    await insert_batch(conn, videos_batch, snapshots_batch)
                    
        logger.info(f"Data loading finished. Total videos processed: {total_videos}")

    except Exception as e:
        logger.error(f"Error during JSON processing: {e}")
    finally:
        await pool.close()

async def insert_batch(conn, videos, snapshots):
    try:
        if videos:
            await conn.executemany("""
                INSERT INTO videos (id, creator_id, video_created_at, views_count, likes_count, comments_count, reports_count, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (id) DO NOTHING
            """, videos)
        
        if snapshots:
            await conn.executemany("""
                INSERT INTO video_snapshots (id, video_id, views_count, likes_count, comments_count, reports_count, 
                                           delta_views_count, delta_likes_count, delta_comments_count, delta_reports_count, 
                                           created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (id) DO NOTHING
            """, snapshots)
    except Exception as e:
        logger.error(f"Batch insert failed: {e}")
        raise e

if __name__ == "__main__":
    asyncio.run(load_json_to_db())