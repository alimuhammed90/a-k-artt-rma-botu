
import sqlite3
from datetime import datetime
import os
import cv2

from config import DATABASE


class DatabaseManager:

    def __init__(self, database):
        self.database = database

    def connect(self):
        conn = sqlite3.connect(self.database)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def create_tables(self):
        with self.connect() as conn:

            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    user_name TEXT,
                    bonus_points INTEGER DEFAULT 0
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS prizes (
                    prize_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image TEXT,
                    used INTEGER DEFAULT 0,
                    is_special INTEGER DEFAULT 0,
                    bonus_cost INTEGER DEFAULT 0
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS winners (
                    user_id INTEGER,
                    prize_id INTEGER,
                    win_time TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(user_id),
                    FOREIGN KEY(prize_id) REFERENCES prizes(prize_id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    setting_name TEXT PRIMARY KEY,
                    setting_value INTEGER
                )
            """)

            user_columns = [
                x[1] for x in conn.execute(
                    "PRAGMA table_info(users)"
                ).fetchall()
            ]

            if "bonus_points" not in user_columns:
                conn.execute(
                    "ALTER TABLE users ADD COLUMN bonus_points INTEGER DEFAULT 0"
                )

            prize_columns = [
                x[1] for x in conn.execute(
                    "PRAGMA table_info(prizes)"
                ).fetchall()
            ]

            if "is_special" not in prize_columns:
                conn.execute(
                    "ALTER TABLE prizes ADD COLUMN is_special INTEGER DEFAULT 0"
                )

            if "bonus_cost" not in prize_columns:
                conn.execute(
                    "ALTER TABLE prizes ADD COLUMN bonus_cost INTEGER DEFAULT 0"
                )

            conn.execute("""
                INSERT OR IGNORE INTO settings
                VALUES ('interval_minutes', 1)
            """)

            conn.execute("""
                INSERT OR IGNORE INTO settings
                VALUES ('bonus_per_win', 5)
            """)

    def add_user(self, user_id, user_name):
        with self.connect() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO users (user_id, user_name)
                VALUES (?, ?)
            """, (user_id, user_name))

    def add_prize(self, image, is_special=0, bonus_cost=0):
        with self.connect() as conn:
            cursor = conn.execute("""
                INSERT INTO prizes (image, is_special, bonus_cost)
                VALUES (?, ?, ?)
            """, (image, is_special, bonus_cost))

            return cursor.lastrowid

    def claim_prize(self, user_id, prize_id):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")

            prize = conn.execute("""
                SELECT image, used, is_special
                FROM prizes
                WHERE prize_id = ?
            """, (prize_id,)).fetchone()

            if prize is None or prize[1] == 1 or prize[2] == 1:
                return "not_found"

            existing = conn.execute("""
                SELECT 1 FROM winners
                WHERE user_id = ? AND prize_id = ?
            """, (user_id, prize_id)).fetchone()

            if existing:
                return "owned"

            count = conn.execute("""
                SELECT COUNT(*)
                FROM winners
                WHERE prize_id = ?
            """, (prize_id,)).fetchone()[0]

            if count >= 3:
                return "full"

            win_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            conn.execute("""
                INSERT INTO winners (user_id, prize_id, win_time)
                VALUES (?, ?, ?)
            """, (user_id, prize_id, win_time))

            bonus = conn.execute("""
                SELECT setting_value
                FROM settings
                WHERE setting_name = 'bonus_per_win'
            """).fetchone()[0]

            conn.execute("""
                UPDATE users
                SET bonus_points = bonus_points + ?
                WHERE user_id = ?
            """, (bonus, user_id))

            return "success"

    def redeem_special(self, user_id, prize_id):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")

            prize = conn.execute("""
                SELECT bonus_cost, used, is_special
                FROM prizes
                WHERE prize_id = ?
            """, (prize_id,)).fetchone()

            if prize is None or prize[1] == 1 or prize[2] != 1:
                return "not_found"

            existing = conn.execute("""
                SELECT 1 FROM winners
                WHERE user_id = ? AND prize_id = ?
            """, (user_id, prize_id)).fetchone()

            if existing:
                return "owned"

            user = conn.execute("""
                SELECT bonus_points
                FROM users
                WHERE user_id = ?
            """, (user_id,)).fetchone()

            if user is None or user[0] < prize[0]:
                return "points"

            win_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            conn.execute("""
                UPDATE users
                SET bonus_points = bonus_points - ?
                WHERE user_id = ?
            """, (prize[0], user_id))

            conn.execute("""
                INSERT INTO winners (user_id, prize_id, win_time)
                VALUES (?, ?, ?)
            """, (user_id, prize_id, win_time))

            conn.execute("""
                UPDATE prizes SET used = 1
                WHERE prize_id = ?
            """, (prize_id,))

            return "success"

    def get_bonus_points(self, user_id):
        with self.connect() as conn:
            result = conn.execute("""
                SELECT bonus_points
                FROM users
                WHERE user_id = ?
            """, (user_id,)).fetchone()

            return result[0] if result else 0

    def get_users(self):
        with self.connect() as conn:
            result = conn.execute("""
                SELECT user_id FROM users
            """).fetchall()

            return [x[0] for x in result]

    def get_random_prize(self):
        with self.connect() as conn:
            return conn.execute("""
                SELECT prize_id, image
                FROM prizes
                WHERE used = 0 AND is_special = 0
                ORDER BY RANDOM()
                LIMIT 1
            """).fetchone()

    def get_prize_img(self, prize_id):
        with self.connect() as conn:
            result = conn.execute("""
                SELECT image FROM prizes
                WHERE prize_id = ?
            """, (prize_id,)).fetchone()

            return result[0] if result else None

    def mark_prize_used(self, prize_id):
        with self.connect() as conn:
            conn.execute("""
                UPDATE prizes SET used = 1
                WHERE prize_id = ?
            """, (prize_id,))

    def get_winners_count(self, prize_id):
        with self.connect() as conn:
            return conn.execute("""
                SELECT COUNT(*)
                FROM winners
                WHERE prize_id = ?
            """, (prize_id,)).fetchone()[0]

    def get_winners_img(self, user_id):
        with self.connect() as conn:
            return conn.execute("""
                SELECT prizes.image
                FROM winners
                INNER JOIN prizes
                ON winners.prize_id = prizes.prize_id
                WHERE winners.user_id = ?
            """, (user_id,)).fetchall()

    def get_rating(self):
        with self.connect() as conn:
            return conn.execute("""
                SELECT users.user_name,
                       COUNT(winners.prize_id) AS count_prize
                FROM winners
                INNER JOIN users
                ON users.user_id = winners.user_id
                GROUP BY winners.user_id
                ORDER BY count_prize DESC
                LIMIT 10
            """).fetchall()

    def get_settings(self):
        with self.connect() as conn:
            result = conn.execute("""
                SELECT setting_name, setting_value
                FROM settings
            """).fetchall()

            return {x[0]: x[1] for x in result}

    def update_setting(self, setting_name, value):
        allowed = ["interval_minutes", "bonus_per_win"]

        if setting_name not in allowed:
            return False

        with self.connect() as conn:
            conn.execute("""
                UPDATE settings
                SET setting_value = ?
                WHERE setting_name = ?
            """, (value, setting_name))

        return True


def hide_img(img_name):
    image_path = f"img/{img_name}"
    image = cv2.imread(image_path)

    if image is None:
        print(f"Resim okunamadı: {image_path}")
        return

    blurred_image = cv2.GaussianBlur(image, (15, 15), 0)

    pixelated_image = cv2.resize(
        blurred_image,
        (30, 30),
        interpolation=cv2.INTER_NEAREST
    )

    pixelated_image = cv2.resize(
        pixelated_image,
        (image.shape[1], image.shape[0]),
        interpolation=cv2.INTER_NEAREST
    )

    cv2.imwrite(f"hidden_img/{img_name}", pixelated_image)


if __name__ == "__main__":
    manager = DatabaseManager(DATABASE)
    manager.create_tables()

    for filename in os.listdir("img"):
        if filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            manager.add_prize(filename)
