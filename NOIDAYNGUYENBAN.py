import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
import re
from PIL import Image

# --- 1. THÔNG SỐ HỆ THỐNG ---
TOTAL_POS = 107 
AVG_WIRES = 114.5
WINDOW = 10 

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'])

def get_mapping_v11(full_str):
    if not full_str or len(full_str) < TOTAL_POS:
        return {str(i): f"{i % 100:02d}" for i in range(11449)}
    return {str(i * TOTAL_POS + j): f"{full_str[i]}{full_str[j]}" for i in range(TOTAL_POS) for j in range(TOTAL_POS)}

def calculate_tier(losses, threshold_pct):
    if not losses: return 0
    losses_sorted = sorted(losses, reverse=True)
    idx = int(len(losses_sorted) * (threshold_pct / 100)) - 1
    return losses_sorted[max(0, idx)]

def update_matrix_state(db, results_27, mapping):
    for wire_id, w_data in db.items():
        num = mapping.get(str(wire_id))
        if num in results_27:
            w_data["streak_win"] = w_data.get("streak_win", 0) + 1
            w_data["streak_loss"] = 0
            w_data["score"] = w_data.get("score", 1000.0) - 2.7
            hist = w_data.get("hit_history", [0]*10)
            hist.append(1)
            w_data["hit_history"] = hist[-10:]
        else:
            w_data["streak_loss"] = w_data.get("streak_loss", 0) + 1
            w_data["streak_win"] = 0
            w_data["score"] = w_data.get("score", 1000.0) + 1.0
            hist = w_data.get("hit_history", [0]*10)
            hist.append(0)
            w_data["hit_history"] = hist[-10:]

# --- 2. BỘ NÃO AI (PURE 65%) ---
def thermal_ai_engine(df_raw):
    if df_raw is None or df_raw.empty: return pd.DataFrame()
    def scoring(row):
        s = 0
        if row['An'] in [2, 3]: s += 5
        elif row['An'] == 4: s += 3
        if row['Tang'] in [1, 2, 3]: s += 5
        if 30 <= row['DâySạch'] <= 119: s += 2
        if 9 <= row['Cứng(10k)'] <= 29: s += 5
        return s
    df_c = df_raw.copy()
    df_c['AI_Score'] = df_c.apply(scoring, axis=1)
    core = df_c[df_c['AI_Score'] >= 15].copy()
    rem = df_c[df_c['AI_Score'] < 15].sort_values(['AI_Score', 'Điểm'], ascending=[False, False]).copy()
    final = core.copy()
    for _, r in rem.iterrows():
        if len(final) >= 59: break
        c_avg = final['Cứng(10k)'].mean() if not final.empty else 24.0
        if c_avg > 26: 
            if r['Cứng(10k)'] < c_avg: final = pd.concat([final, pd.DataFrame([r])])
        elif c_avg < 22:
            if r['Cứng(10k)'] > c_avg: final = pd.concat([final, pd.DataFrame([r])])
        else:
            final = pd.concat([final, pd.DataFrame([r])])
    return final

# --- 3. XỬ LÝ MA TRẬN ---
def process_matrix_v13_61():
    db = st.session_state.get('db', {})
    f_str = st.session_state.get('last_full_str', "")
    mapping = get_mapping_v11(f_str)
    stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "clean_wire_count": 0, "clean_window_hits": 0, "all_losses": []} for i in range(100)}
    for wire_id, w_data in db.items():
        num = mapping.get(str(wire_id))
        if num:
            s = stats[num]
            sw, sl = int(w_data.get("streak_win", 0)), int(w_data.get("streak_loss", 0))
            s["all_losses"].append(sl if sw == 0 else 0)
            if sw > s["max_an"]: s["max_an"] = sw
            s["clean_window_hits"] += sum(w_data.get("hit_history", [])[-WINDOW:])
            if sw == 0:
                s["clean_wire_count"] += 1
                s["total_score"] += float(w_data.get("score", 1000.0))
    res = []
    for num, s in stats.items():
        dc = s["clean_wire_count"] if s["clean_wire_count"] > 0 else 1
        hard = round((s["clean_window_hits"] / (WINDOW * AVG_WIRES)) * 100, 2)
        score = round((s["total_score"] / dc) * (1 + hard/100), 2)
        res.append({"Số": num, "Điểm": score, "An": s["max_an"], "Tang": calculate_tier(s["all_losses"], 65), "DâySạch": s["clean_wire_count"], "Cứng(10k)": hard})
    df = pd.DataFrame(res).sort_values("Điểm", ascending=False).reset_index(drop=True)
    df["Rank"] = df.index + 1
    st.session_state['df_raw'] = df
    return df

# --- 4. GIAO DIỆN ---
st.set_page_config(layout="wide", page_title="Matrix V13.61 Final Fix")
st.markdown("<h1 style='text-align: center; color: red;'>Matrix V13.61 - Bug Fixed</h1>", unsafe_allow_html=True)

if 'db' not in st.session_state: st.session_state['db'] = {}
if 'history' not in st.session_state: st.session_state['history'] = []

with st.sidebar:
    st.header("📂 HỆ THỐNG")
    col1, col2 = st.columns(2)
    with col1: 
        if st.button("🚨 RESET"): st.session_state.clear(); st.rerun()
    with col2:
        if st.button("💎 KHỞI TẠO"):
            st.session_state['db'] = {str(i): {"score": 1000.0, "streak_win": 0, "streak_loss": 0, "hit_history": [0]*10} for i in range(11449)}
            st.session_state['last_full_str'] = ""; process_matrix_v13_61(); st.rerun()

    up_json = st.file_uploader("📥 Nạp JSON", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json)
        st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', [])
        st.session_state['last_full_str'] = data.get('last_full_str', ""); process_matrix_v13_61(); st.rerun()

    st.divider()
    ai_on = st.toggle("AI Cân bằng nhiệt", value=True)
    if not ai_on:
        f_rank = st.slider("Rank:", 0, 100, (11, 85))
        f_an = st.slider("An:", 0, 15, (0, 3)); f_tang_min = st.slider("Tầng:", 0, 10, 1); f_hard = st.slider("Cứng%:", 0.0, 100.0, (13.0, 45.0))
        if st.button("✅ ÁP DỤNG BỘ LỌC TAY"): process_matrix_v13_61(); st.rerun()

    st.header("📸 QUÉT KQ (OCR)")
    up_img = st.file_uploader("Chọn ảnh", type=['jpg', 'jpeg', 'png'])
    if up_img and st.button("🚀 CHẠY OCR"):
        reader = load_ocr(); results = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
        if nums: st.session_state['raw_input'] = ", ".join(nums); st.session_state['gdb_val'] = nums[0][-2:]; st.rerun()

    st.session_state['raw_input'] = st.text_area("27 giải loto:", value=st.session_state.get('raw_input', ""), height=80)
    st.session_state['gdb_val'] = st.text_input("GĐB:", value=st.session_state.get('gdb_val', ""), max_chars=2)
    
    if st.button("🔥 PHÂN TÍCH KỲ MỚI"):
        df_before = process_matrix_v13_61()
        df_ai_current = thermal_ai_engine(df_before) if ai_on else df_before.head(55)
        ai_list = df_ai_current["Số"].tolist()
        raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
        if len(raw_list) >= 27:
            gv = st.session_state['gdb_val']
            r_row = df_before[df_before['Số'] == gv].iloc[0] if gv in df_before['Số'].values else None
            g_p = f"{gv} (R{int(r_row['Rank'])}-A{int(r_row['An'])}-D{int(r_row['DâySạch'])}-T{int(r_row['Tang'])}-C{int(r_row['Cứng(10k)'])}%)" if r_row is not None else gv
            
            def get_t_rep(n):
                h_list = [h for h in st.session_state['history'][:n] if "A(" in str(h.get("Ai", ""))]
                return f"{len(h_list)}({','.join([str(h.get('GĐB', ''))[:2] for h in h_list])})" if h_list else "0"

            entry = {"STT": len(st.session_state['history'])+1, "GĐB": g_p, "Ai": f"A({len(ai_list)})" if gv in ai_list else f"T({len(ai_list)})", "AvgC": round(df_ai_current['Cứng(10k)'].mean(), 2) if not df_ai_current.empty else 0, "T5": get_t_rep(5), "T10": get_t_rep(10), "T15": get_t_rep(15), "T20": get_t_rep(20)}
            st.session_state['history'].insert(0, entry)
            
            loto_27 = [n[-2:] for n in raw_list[:27]]; mapping_old = get_mapping_v11(st.session_state.get('last_full_str', ""))
            update_matrix_state(st.session_state['db'], loto_27, mapping_old); st.session_state['last_full_str'] = "".join(raw_list[:27])
            process_matrix_v13_61(); st.rerun()

# --- 5. HIỂN THỊ ---
if st.session_state.get('df_raw') is not None:
    df_raw_cur = st.session_state['df_raw']
    df_d = thermal_ai_engine(df_raw_cur) if ai_on else df_raw_cur.head(55)
    col_m, col_d = st.columns([2, 1])
    with col_m: st.metric("DÀN CHỐT TIẾP THEO", f"{len(df_d)} quân", f"AvgC: {df_d['Cứng(10k)'].mean():.2f}")
    with col_d: st.download_button("💾 LƯU .JSON", data=json.dumps({"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state['last_full_str']}), file_name="matrix_v13_61.json")
    st.code(", ".join(df_d.sort_values("Số")["Số"].tolist()))
    st.divider()
    c1, c2 = st.columns([1, 2.8])
    with c1: st.subheader("🎯 CHI TIẾT"); st.dataframe(df_d, use_container_width=True, hide_index=True)
    with c2: 
        st.subheader("📜 LỊCH SỬ CHUẨN")
        h_df = pd.DataFrame(st.session_state['history'])
        if not h_df.empty:
            # FIX LỖI KEYERROR: Chỉ lọc những cột nào THỰC SỰ tồn tại
            desired_order = ["STT", "GĐB", "Ai", "AvgC"]
            actual_cols = h_df.columns.tolist()
            final_fixed = [c for c in desired_order if c in actual_cols]
            t_cols = sorted([c for c in actual_cols if c.startswith("T") and c[1:].isdigit()], key=lambda x: int(x[1:]))
            other_cols = [c for c in actual_cols if c not in final_fixed and c not in t_cols]
            h_df = h_df[final_fixed + t_cols + other_cols]
        st.dataframe(h_df, use_container_width=True, height=800)
