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
            hist.append(1); w_data["hit_history"] = hist[-10:]
        else:
            w_data["streak_loss"] = w_data.get("streak_loss", 0) + 1
            w_data["streak_win"] = 0
            w_data["score"] = w_data.get("score", 1000.0) + 1.0
            hist = w_data.get("hit_history", [0]*10)
            hist.append(0); w_data["hit_history"] = hist[-10:]

# --- 2. CÔNG CỤ TRUY VẾT & HỘI TỤ ---

def get_bottom_tracer(db, mapping, n_bottom):
    bottom_wires = sorted(db.items(), key=lambda x: x[1]['score'])[:n_bottom]
    bottom_numbers = set()
    for wire_id, data in bottom_wires:
        num = mapping.get(str(wire_id))
        if num: bottom_numbers.add(f"{int(num):02d}")
    return list(bottom_numbers)

def get_historical_mapping(history):
    m_dict = {}
    if len(history) < 2: return m_dict
    for i in range(len(history) - 1):
        try:
            prev_raw = str(history[i+1]['GĐB']).split()[0]
            curr_raw = str(history[i]['GĐB']).split()[0]
            prev = f"{int(re.sub(r'\D', '', prev_raw)[-2:]):02d}"
            curr = f"{int(re.sub(r'\D', '', curr_raw)[-2:]):02d}"
            if prev not in m_dict: m_dict[prev] = {}
            m_dict[prev][curr] = m_dict[prev].get(curr, 0) + 1
        except: continue
    return m_dict

def thermal_ai_engines_v75(df_raw, history, db, mapping, n_bottom):
    if df_raw is None or df_raw.empty: 
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), []
    
    df_c = df_raw.copy()

    # A. CHUẨN HÓA CÁC TẬP HỢP (SETS)
    bottom_set = set(get_bottom_tracer(db, mapping, n_bottom))
    
    mapping_dict = get_historical_mapping(history)
    last_gdb_raw = str(history[0]['GĐB']).split()[0] if history and 'GĐB' in history[0] else ""
    last_gdb_clean = f"{int(re.sub(r'\D', '', last_gdb_raw)[-2:]):02d}" if re.sub(r'\D', '', last_gdb_raw) else ""
    hist_set = {f"{int(x):02d}" for x in mapping_dict.get(last_gdb_clean, {}).keys()}
    
    tech_set = {f"{int(x):02d}" for x in df_raw.sort_values(['Điểm', 'Rank'], ascending=[False, True]).head(79)['Số']}

    # B. CHẤM ĐIỂM TRINITY (HỘI TỤ)
    def check_trinity(num):
        s = f"{int(num):02d}"
        tags = []
        if s in tech_set: tags.append("Tech")
        if s in bottom_set: tags.append("Bottom")
        if s in hist_set: tags.append("Hist")
        return len(tags), "|".join(tags)

    trinity_res = df_c['Số'].apply(check_trinity)
    df_c['Match'] = [x[0] for x in trinity_res]
    df_c['Tags'] = [x[1] for x in trinity_res]

    # C. PHÂN TẦNG ƯU TIÊN
    df_sorted = df_c.sort_values(by=['Match', 'Điểm', 'Rank'], ascending=[False, False, True])
    df_ai = df_sorted.head(59)
    df_ket = df_ai.head(39)
    df_safe = df_sorted.head(79)
    df_loai = df_c[~df_c['Số'].isin(df_safe['Số'])].sort_values('Rank', ascending=False).head(21)
    
    return df_ket, df_ai, df_safe, df_loai, list(bottom_set)

# --- 3. GIAO DIỆN & LUỒNG XỬ LÝ ---
st.set_page_config(layout="wide", page_title="Matrix V13.75 FIX")
st.markdown("<h1 style='text-align: center; color: #FF4B4B;'>Matrix V13.75 - Trinity Alignment</h1>", unsafe_allow_html=True)

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
            st.session_state['last_full_str'] = ""; st.rerun()
    
    up_json = st.file_uploader("📥 Nạp JSON", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json)
        st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', [])
        st.session_state['last_full_str'] = data.get('last_full_str', "")
        st.rerun()
    
    st.divider()
    n_bottom = st.slider("Độ nhạy dây đáy (Bottom):", 100, 250, 180)

    st.header("📸 QUÉT KQ (OCR)")
    up_img = st.file_uploader("Chọn ảnh", type=['jpg', 'jpeg', 'png'])
    if up_img and st.button("🚀 CHẠY OCR"):
        reader = load_ocr()
        results = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
        if nums: st.session_state['raw_input'] = ", ".join(nums); st.session_state['gdb_val'] = nums[0][-2:]; st.rerun()

    st.session_state['raw_input'] = st.text_area("27 giải loto:", value=st.session_state.get('raw_input', ""), height=80)
    st.session_state['gdb_val'] = st.text_input("GĐB:", value=st.session_state.get('gdb_val', ""), max_chars=2)
    
    if st.button("🔥 PHÂN TÍCH KỲ MỚI"):
        def get_raw_matrix():
            db = st.session_state['db']; f_str = st.session_state.get('last_full_str', ""); mapping = get_mapping_v11(f_str)
            stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "clean_wire_count": 0, "clean_window_hits": 0, "all_losses": []} for i in range(100)}
            for w_id, w_d in db.items():
                num = mapping.get(str(w_id))
                if num:
                    s = stats[num]; sw, sl = int(w_d.get("streak_win", 0)), int(w_d.get("streak_loss", 0))
                    s["all_losses"].append(sl if sw == 0 else 0)
                    if sw > s["max_an"]: s["max_an"] = sw
                    s["clean_window_hits"] += sum(w_d.get("hit_history", [])[-WINDOW:])
                    if sw == 0: s["clean_wire_count"] += 1; s["total_score"] += float(w_d.get("score", 1000.0))
            res = []
            for num, s in stats.items():
                dc = s["clean_wire_count"] if s["clean_wire_count"] > 0 else 1
                hard = round((s["clean_window_hits"] / (WINDOW * AVG_WIRES)) * 100, 2)
                score = round((s["total_score"] / dc) * (1 + hard/100), 2)
                res.append({"Số": num, "Điểm": score, "An": s["max_an"], "Tang": calculate_tier(s["all_losses"], 65), "DâySạch": s["clean_wire_count"], "Cứng(10k)": hard})
            df = pd.DataFrame(res).sort_values("Điểm", ascending=False).reset_index(drop=True)
            df["Rank"] = df.index + 1
            return df

        df_r = get_raw_matrix()
        map_v = get_mapping_v11(st.session_state.get('last_full_str', ""))
        dk, da, ds, dl, b_l = thermal_ai_engines_v75(df_r, st.session_state['history'], st.session_state['db'], map_v, n_bottom)
        
        raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
        if len(raw_list) >= 27:
            gv = st.session_state['gdb_val']
            st.session_state['history'].insert(0, {"STT": len(st.session_state['history'])+1, "GĐB": gv, "Kết": "A" if gv in dk["Số"].tolist() else "T", "Ai": "A" if gv in da["Số"].tolist() else "T", "Match_Max": int(da['Match'].max()) if not da.empty else 0})
            update_matrix_state(st.session_state['db'], [n[-2:] for n in raw_list[:27]], map_v)
            st.session_state['last_full_str'] = "".join(raw_list[:27]); st.rerun()

# --- 4. HIỂN THỊ ---
if 'last_full_str' in st.session_state:
    def get_raw_matrix_display():
        db = st.session_state['db']; f_str = st.session_state.get('last_full_str', ""); mapping = get_mapping_v11(f_str)
        stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "clean_wire_count": 0, "clean_window_hits": 0, "all_losses": []} for i in range(100)}
        for w_id, w_d in db.items():
            num = mapping.get(str(w_id))
            if num:
                s = stats[num]; sw, sl = int(w_d.get("streak_win", 0)), int(w_d.get("streak_loss", 0))
                s["all_losses"].append(sl if sw == 0 else 0)
                if sw > s["max_an"]: s["max_an"] = sw
                s["clean_window_hits"] += sum(w_d.get("hit_history", [])[-WINDOW:])
                if sw == 0: s["clean_wire_count"] += 1; s["total_score"] += float(w_d.get("score", 1000.0))
        res = []
        for num, s in stats.items():
            dc = s["clean_wire_count"] if s["clean_wire_count"] > 0 else 1
            hard = round((s["clean_window_hits"] / (WINDOW * AVG_WIRES)) * 100, 2)
            score = round((s["total_score"] / dc) * (1 + hard/100), 2)
            res.append({"Số": num, "Điểm": score, "An": s["max_an"], "Tang": calculate_tier(s["all_losses"], 65), "DâySạch": s["clean_wire_count"], "Cứng(10k)": hard})
        df = pd.DataFrame(res).sort_values("Điểm", ascending=False).reset_index(drop=True)
        df["Rank"] = df.index + 1
        return df

    df_d = get_raw_matrix_display()
    map_v = get_mapping_v11(st.session_state.get('last_full_str', ""))
    dk, da, ds, dl, b_l = thermal_ai_engines_v75(df_d, st.session_state['history'], st.session_state['db'], map_v, n_bottom)
    
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("KẾT (39)", len(dk)); col_m2.metric("AI (59)", len(da)); col_m3.metric("SAFE (79)", len(ds))

    st.write(f"🛡️ **Dàn Đáy ({len(b_l)} số):**"); st.code(", ".join(sorted(b_l)))
    st.write(f"🤖 **Dàn Ai 59 (Trinity Convergence):**"); st.code(", ".join(da.sort_values("Số")["Số"].tolist()))
    
    st.divider()
    c_left, c_right = st.columns([1, 1.2])
    with c_left:
        st.subheader("📊 BẢNG HỘI TỤ"); st.dataframe(da[['Số', 'Match', 'Tags', 'Điểm', 'Rank']], use_container_width=True, hide_index=True)
    with c_right:
        st.subheader("📜 LỊCH SỬ"); st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True, hide_index=True)
    
    st.download_button("💾 XUẤT JSON", data=json.dumps({"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state['last_full_str']}), file_name="matrix_v13_75.json")
