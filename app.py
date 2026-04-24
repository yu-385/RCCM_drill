# -*- coding: utf-8 -*-
import streamlit as st
import sqlite3
import os
import zipfile

DB_PATH = "exam_data.db"

import glob

# Streamlit Cloud上で画像フォルダが存在しない場合は、ZIPファイル群から自動解凍する
if not os.path.exists("images"):
    zip_files = sorted(glob.glob("images*.zip"))
    if zip_files:
        for zf in zip_files:
            with zipfile.ZipFile(zf, 'r') as zip_ref:
                # 現在のディレクトリに解凍（内部にimagesフォルダが含まれる前提）
                zip_ref.extractall()

st.set_page_config(page_title="過去問統合ドリルアプリ", layout="centered", page_icon="📚")

def get_questions(category, field=None, mode="random", target_year=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    if mode == "random":
        limit = 30 if category == "Q4-2" else 20
        
        # まず対象科目（分野）のすべての問題をごっそり取得する
        if field:
            cur.execute("SELECT id, year, question_num, image_path, correct_answer FROM problems WHERE category=? AND field=?", (category, field))
        else:
            cur.execute("SELECT id, year, question_num, image_path, correct_answer FROM problems WHERE category=? AND field IS NULL", (category,))
        all_rows = cur.fetchall()
        
        # 問題番号ごとにグループ化して分類する
        from collections import defaultdict
        import random
        
        grouped = defaultdict(list)
        for row in all_rows:
            # row[2] が question_num
            grouped[row[2]].append(row)
            
        selected_rows = []
        # 各問題番号グループから「ランダムな年度の過去問１つ」をくじ引きで決める（類似問題回避）
        for q_num, items in grouped.items():
            selected_rows.append(random.choice(items))
            
        # シャッフルした上で上限数で切り取る
        random.shuffle(selected_rows)
        rows = selected_rows[:limit]
        
    else:
        # yearlyモード
        if field:
            cur.execute("SELECT id, year, question_num, image_path, correct_answer FROM problems WHERE category=? AND field=? AND year=? ORDER BY CAST(question_num AS INTEGER)", (category, field, target_year))
        else:
            cur.execute("SELECT id, year, question_num, image_path, correct_answer FROM problems WHERE category=? AND field IS NULL AND year=? ORDER BY CAST(question_num AS INTEGER)", (category, target_year))
        
        rows = cur.fetchall()

    conn.close()
    return rows

def get_cached_explanation(problem_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT explanation_text FROM explanations WHERE problem_id=?", (problem_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def save_explanation(problem_id, text):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("INSERT INTO explanations (problem_id, explanation_text) VALUES (?, ?)", (problem_id, text))
        conn.commit()
        conn.close()
    except Exception as e:
        # クラウド上でDBが読み取り専用になっており書き込めない場合はキャッシュを諦める（クラッシュ回避）
        print(f"Skipping cache save due to DB error: {e}")
        pass

def generate_ai_explanation(year, q_num, correct_ans, image_path, api_key):
    if not api_key:
        return f"### {year}年 問{q_num} の解説\n\n正解は **{correct_ans}** です。\n\n※Gemini APIキーが設定されていないため、解説の自動生成はスキップされました。サイドバーからAPIキーを設定してください。"
    
    try:
        from google import genai
        import PIL.Image
        
        # 新しいSDKインターフェースを使用
        client = genai.Client(api_key=api_key)
        
        img = PIL.Image.open(image_path)
        
        if correct_ans:
            prompt = (
                f"あなたは土木技術・RCCM資格試験の専門インストラクターです。\n"
                f"添付された画像は、{year}年度の実際の試験問題（問{q_num}）です。\n"
                f"公式の正解選択肢は「{correct_ans}」です。\n\n"
                f"【必ず以下の構成で出力してください】\n"
                f"1. 問題のテーマと要点\n"
                f"2. なぜ「{correct_ans}」が正解となるのかの詳しい解説\n"
                f"3. 他の選択肢がなぜ誤り（または不適切）なのかの解説\n\n"
                f"※絶対に空の回答を出力せず、分かりやすい解説を提示してください。"
            )
        else:
            prompt = (
                f"あなたは土木技術・RCCM資格試験の専門インストラクターです。\n"
                f"添付された画像は、{year}年度の実際の試験問題（問{q_num}）です。\n"
                f"この問題は公式の正解が発表されていない（解なし、あるいは不適切問題）可能性があります。\n\n"
                f"【必ず以下の構成で出力してください】\n"
                f"1. 問題のテーマと要点\n"
                f"2. 画像の問題文と選択肢を読み解き、もし強いて正解を選ぶとしたらどれになるか、またはなぜ「解なし（不適切問題）」となったと考えられるかの専門的な考察\n"
                f"3. 各選択肢の技術的な解説\n\n"
                f"※絶対に空の回答を出力せず、分かりやすい解説を提示してください。"
            )
        
        try:
            # 元々動いていた 2.5-flash にモデルを戻す（プロンプト強化版）
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[img, prompt]
            )
        except Exception as api_err:
            raise api_err
                
        # 安全フィルター等でブロックされた、あるいは空の応答が返ってきた場合のフェイルセーフ
        if not response or not response.text:
            reason = "Unknown"
            if hasattr(response, "candidates") and response.candidates:
                reason = getattr(response.candidates[0], "finish_reason", "Unknown")
            raise Exception(f"AIからの返答が空でした（安全フィルター等によるブロックの可能性があります）\nFinish Reason: {reason}")
                
        correct_ans_disp = correct_ans if correct_ans else "不明（または解なし）"
        return f"### {year}年 問{q_num} の解説（AI自動生成）\n\n正解は **{correct_ans_disp}** です。\n\n#### 解説\n{response.text}"
    except Exception as e:
        return f"### {year}年 問{q_num} の解説\n\n正解は **{correct_ans}** です。\n\n🚨 AI解説の生成中にエラーが発生しました:\n```\n{e}\n```"

def get_available_categories():
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT category FROM problems")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]

def get_available_fields(category):
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT field FROM problems WHERE category=? AND field IS NOT NULL", (category,))
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]

def get_available_years(category, field=None):
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if field:
        cur.execute("SELECT DISTINCT year FROM problems WHERE category=? AND field=?", (category, field))
    else:
        cur.execute("SELECT DISTINCT year FROM problems WHERE category=? AND field IS NULL", (category,))
    rows = cur.fetchall()
    conn.close()
    return sorted([r[0] for r in rows if r[0]])

def main():
    st.title("📚 過去問統合ドリルAI")
    
    avail_cats = get_available_categories()
    
    with st.sidebar:
        st.header("🎯 出題設定")
        if not avail_cats:
            st.warning("登録されている科目データがありません。先にPDFを処理してください。")
            category_options = ["Q4-1"]
        else:
            category_options = avail_cats
        
        selected_cat = st.selectbox(
            "科目を選択してください",
            options=category_options,
            format_func=lambda x: {
                "Q4-1": "RCCM問題4-1 (共通基礎技術)",
                "Q2": "RCCM問題2 (業務関連法制度等)",
                "Q4-2": "RCCM問題4-2 (専門)"
            }.get(x, x)
        )
        
        selected_field = None
        if selected_cat == "Q4-2":
            avail_fields = get_available_fields(selected_cat)
            if avail_fields:
                selected_field = st.selectbox(
                    "専門分野を選択してください",
                    options=avail_fields,
                    format_func=lambda x: {
                        "doro": "道路",
                        "josuido": "上水道",
                        "gesuido": "下水道",
                        "kasen": "河川",
                        "nogyo": "農業土木",
                        "nogyo_doboku": "農業土木"
                    }.get(x, x)
                )
            else:
                st.info("登録されている専門分野データがありません。")
                
        st.markdown("---")
        st.header("🎮 出題モード")
        selected_mode = st.radio(
            "モードを選択してください",
            options=["random", "yearly"],
            format_func=lambda x: "🎲 ランダム20問" if x == "random" else "📅 年度別通しプレイ"
        )
        
        selected_year = None
        if selected_mode == "yearly":
            avail_years = get_available_years(selected_cat, selected_field)
            if avail_years:
                selected_year = st.selectbox(
                    "挑戦する年度を選択してください",
                    options=avail_years
                )
            else:
                st.info("該当する年度データが見つかりません。")
                
        st.markdown("---")
        st.header("⚙️ API設定")
        api_key = st.text_input("Gemini API Key", type="password", help="AIによる動的解説を使用するにはAPIキーを入力してください。")
        st.caption("※ 一度生成した解説はデータベースにキャッシュされ、次回以降高速に表示されます。")
        
    # カテゴリや分野、出題モードが変更されたらセッションをリセット
    if ("current_category" not in st.session_state or 
        st.session_state.current_category != selected_cat or
        st.session_state.get("current_field") != selected_field or
        st.session_state.get("current_mode") != selected_mode or
        st.session_state.get("current_year") != selected_year):
        st.session_state.current_category = selected_cat
        st.session_state.current_field = selected_field
        st.session_state.current_mode = selected_mode
        st.session_state.current_year = selected_year
        st.session_state.questions = get_questions(selected_cat, selected_field, selected_mode, selected_year)
        st.session_state.current_idx = 0
        st.session_state.score = 0
        st.session_state.answered = False
        st.session_state.selected_ans = None
        
    if "questions" not in st.session_state:
        st.session_state.questions = get_questions(selected_cat, selected_field, selected_mode, selected_year)
        st.session_state.current_idx = 0
        st.session_state.score = 0
        st.session_state.answered = False
        st.session_state.selected_ans = None

    if not st.session_state.questions:
        st.warning(f"現在選択されている条件（{selected_cat} / {selected_field}）の問題データが見つかりません。")
        return

    q_idx = st.session_state.current_idx
    q_total = len(st.session_state.questions)
    
    if q_idx >= q_total:
        st.success(f"🎉 終了！あなたのスコア: {st.session_state.score} / {q_total}")
        if st.button("もう一度チャレンジする"):
            st.session_state.current_idx = 0
            st.session_state.score = 0
            st.session_state.answered = False
            st.session_state.selected_ans = None
            st.rerun()
        return

    # 現在の問題を取得
    prob_id, year, q_num, img_path, correct_ans = st.session_state.questions[q_idx]

    # Windows(ローカル)とLinux(クラウド)のパス区切り文字の違いを吸収するため、\ を / に統一する
    img_path = img_path.replace('\\', '/')

    st.progress((q_idx) / q_total)
    st.write(f"**第 {q_idx + 1} 問** ({year}年度 問題 {q_num})")
    
    if os.path.exists(img_path):
        st.image(img_path, use_container_width=True)
    else:
        st.error(f"画像が見つかりません: {img_path}")

    # ボタンUI
    st.write("#### 回答を選択してください")
    cols = st.columns(4)
    options = ['a', 'b', 'c', 'd']
    
    for i, opt in enumerate(options):
        if st.session_state.answered:
            cols[i].button(opt, disabled=True, key=f"btn_{opt}_{q_idx}")
        else:
            if cols[i].button(opt, key=f"btn_{opt}_{q_idx}"):
                st.session_state.selected_ans = opt
                st.session_state.answered = True
                if opt == correct_ans:
                    st.session_state.score += 1
                st.rerun()

    if st.session_state.answered:
        correct_ans_disp = correct_ans if correct_ans else "不明（AI解説を参照）"
        is_correct = (st.session_state.selected_ans == correct_ans)
        
        if not correct_ans:
            st.warning("⚠️ この問題の公式解答データがシステムに登録されていません。AIの解説から正解を確認してください！")
        elif is_correct:
            st.success("✅ 正解！")
        else:
            st.error(f"❌ 不正解... 正解は **{correct_ans_disp}** です。")
            
        with st.spinner("解説を表示しています..."):
            explanation = get_cached_explanation(prob_id)
            if not explanation:
                st.info("💡 AIに解説を生成させています... 少しお待ちください。")
                explanation = generate_ai_explanation(year, q_num, correct_ans, img_path, api_key)
                if "エラーが発生しました" not in explanation and "設定されていないため" not in explanation:
                    save_explanation(prob_id, explanation)
                    st.info("💡 新しくAIが解説を生成し、データベースにキャッシュしました。")
            else:
                st.info("⚡ キャッシュから解説を高速表示しました。")
                
            st.markdown(explanation)
        
        if st.button("次の問題へ"):
            st.session_state.current_idx += 1
            st.session_state.answered = False
            st.session_state.selected_ans = None
            st.rerun()

if __name__ == "__main__":
    main()
