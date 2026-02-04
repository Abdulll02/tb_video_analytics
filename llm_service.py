import os
from openai import AsyncOpenAI

client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

MODEL_NAME = os.getenv("OPENROUTER_MODEL", "arcee-ai/trinity-large-preview:free")

SYSTEM_PROMPT = """
You are an expert PostgreSQL Data Analyst. 
You are given a database with two tables. 
Your task is to convert a natural language question (in Russian) into a SINGLE executable SQL query that returns exactly ONE numeric value (integer or float).

### Database Schema

1. Table `videos` (General stats per video):
   - `id` (UUID): Video ID
   - `creator_id` (UUID): Creator ID
   - `video_created_at` (TIMESTAMP): When video was published
   - `views_count` (BIGINT): Total views
   - `likes_count` (BIGINT): Total likes
   - `comments_count` (BIGINT): Total comments
   - `reports_count` (BIGINT): Total reports

2. Table `video_snapshots` (Hourly statistics tracking):
   - `video_id` (UUID): FK to videos.id
   - `created_at` (TIMESTAMP): When the snapshot was taken
   - `delta_views_count` (BIGINT): New views since last hour
   - `delta_likes_count` (BIGINT): New likes since last hour
   - `delta_comments_count` (BIGINT): New comments since last hour
   - `views_count` (BIGINT): Value at that specific time
   
### Important Rules for Query Construction:

1. **Date Handling**: 
   - The user will ask in Russian (e.g., "28 ноября 2025"). You MUST convert this to SQL dates.
   - "28 ноября 2025" -> `'2025-11-28 00:00:00'` to `'2025-11-28 23:59:59'`.
   - "С 1 по 5 ноября" -> `BETWEEN '2025-11-01'` AND `'2025-11-05 23:59:59'`.
   - If user asks about "growth" or "increase" (прирост, выросли) on a specific date, you MUST use `SUM(delta_...)` from `video_snapshots`.
   - If user asks about "how many videos" (сколько видео) published/released, use `COUNT(*)` from `videos` filtering by `video_created_at`.
   - If user asks about "how many videos got views" (получали просмотры), count distinct `video_id` from `video_snapshots` where `delta_views_count > 0` and `created_at` is in range.

2. **Output**:
   - Return ONLY the SQL query. 
   - NO Markdown code blocks (```sql).
   - NO explanation.
   - The result of the SQL query must be a single column named `result`.

### Examples:

User: "Сколько видео у креатора '123-uuid' вышло 1 ноября 2025?"
SQL: SELECT COUNT(*) as result FROM videos WHERE creator_id = '123-uuid' AND video_created_at >= '2025-11-01 00:00:00' AND video_created_at <= '2025-11-01 23:59:59';

User: "На сколько просмотров в сумме выросли все видео 28 ноября 2025?"
SQL: SELECT SUM(delta_views_count) as result FROM video_snapshots WHERE created_at >= '2025-11-28 00:00:00' AND created_at <= '2025-11-28 23:59:59';

User: "Сколько видео набрало больше 100 000 просмотров за всё время?"
SQL: SELECT COUNT(*) as result FROM videos WHERE views_count > 100000;
"""

async def generate_sql(user_query: str) -> str:
    try:
        completion = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_query},
            ],
            temperature=0.1, # low temperature for deterministic code
        )
        sql = completion.choices[0].message.content.strip()
        
        # Очистка от маркдауна, если модель его все-таки добавила
        sql = sql.replace("```sql", "").replace("```", "").strip()
        
        # Примитивная защита от деструктивных действий (для теста)
        forbidden = ["DROP", "DELETE", "TRUNCATE", "INSERT", "UPDATE", "ALTER"]
        if any(word in sql.upper() for word in forbidden):
             return None
             
        return sql
    except Exception as e:
        print(f"LLM Error: {e}")
        return None