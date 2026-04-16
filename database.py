# -*- coding: utf-8 -*-
import sqlite3
import os

DB_PATH = "exam_data.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # 問題管理テーブル
    cur.execute('''
        CREATE TABLE IF NOT EXISTS problems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,          -- 例: Q4-1, Q2, Q4-2
            field TEXT,             -- 例: doro, josuido (Q4-2の場合など)
            year TEXT,              -- 例: R01, h25
            question_num INTEGER,   -- 問題番号: 1, 2...
            image_path TEXT,        -- クロップした画像のパス
            correct_answer TEXT     -- 正答（例: "3", "a" など）
        )
    ''')
    # AI解説キャッシュテーブル
    cur.execute('''
        CREATE TABLE IF NOT EXISTS explanations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            problem_id INTEGER,
            explanation_text TEXT,
            FOREIGN KEY(problem_id) REFERENCES problems(id)
        )
    ''')
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("SQLiteデータベースの初期化が完了しました。")
