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

# --- 2. CÁC CÔNG CỤ TRUY VẾT (V13.75) ---

def get_bottom_tracer(db, mapping, n_bottom=180):
    """Lớp 1: Truy vết N dây điểm thấp nhất (Điểm nén)"""
    bottom_wires = sorted(db.items(), key=lambda x: x[1]['score'])[:n_bottom]
    bottom_numbers = set()
    for wire_id, data in bottom_wires:
        num = mapping.get(str(wire_id))
        if num: bottom_numbers.add(num)
    return list(bottom_numbers)

def get_historical_mapping(history):
    """Lớp 2: Truy vết ánh xạ lịch sử (Mapping)"""
    m_dict = {}
    if len(history) < 2: return m_dict
    for i in range(len(history) - 1):
        try:
            prev = history[i+1]['GĐB'].split()[0]
            curr = history[i]['GĐB'].split()[0]
            if prev not in m_dict: m_dict[prev] = {}
            m_dict[prev][curr] = m_dict[prev].get(curr, 0) + 1
        except: continue
    return m_dict

# --- 3. BỘ NÃO HỘI TỤ TRINITY V13.75 ---

def thermal_ai_engines_v75(df_raw, history, db, mapping, n_bottom=180):
    if df_raw is None or df_raw.empty: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    
    df_c = df_raw.copy()
    
    # A. Lấy 3 nguồn dữ liệu
    bottom_list = get_bottom_tracer(db, mapping, n_bottom)
    mapping_dict = get_historical_mapping(history)
    last_gdb = history[0]['GĐB'].split()[0] if history else ""
    history_preds = list(mapping_dict.get(last_gdb, {}).keys())
    # Lấy dàn 79 kỹ thuật (Rank + Nhịp)
    df_tech_79 = df_c.sort_values(['Điểm', 'Rank'], ascending=[False, True]).head(79)
    tech_list = df_tech_79['Số'].tolist()

    # B. Chấm điểm Hội tụ (Trinity Match)
    def check_trinity(num):
        match_count = 0
        tags = []
        if num in tech_list: match_count += 1; tags.append("Tech")
        if num in bottom_list: match_count += 1; tags.append("Bottom")
        if num in history_preds: match_count += 1; tags.append("Hist")
        return match_count, "|".join(tags)

    df_c[['Match', 'Tags']] = df_c['Số'].apply(lambda x: pd.Series(check_trinity(x)))

    # C. Phân tầng ưu tiên để lọc dàn 59
    # Ưu tiên: Match (3->2->1) rồi đến Điểm rồi đến Rank
    df_sorted = df_c.sort_values(['Match', 'Điểm', 'Rank'], ascending=[False, False, True])

    df_ai = df_sorted.head(59)
    df_ket = df_ai.head(39)
    df_safe = df_sorted.head(79)
    df_loai = df_c[~df_c['Số'].isin(df_safe['Số'])].sort_values('Rank', ascending=False).head(21)
    
    return df_ket, df_ai, df_safe, df_loai, bottom_list

# --- 4. GIAO DIỆN STREAMLIT ---
st.set_page_config(layout="wide", page_title="Matrix V13.75 Trinity")
st.markdown("<h1 style='text-align: center; color: #FF4B4B;'>Matrix V13.75 - Trinity Convergence</h1>", unsafe_allow_html=True)

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
        data = json.load(up_json); st.session_state['db'] = data.get('matrix', data); st.session_state['history'] = data.get('history', []); st.session_state['last_full_str'] = data.get('last_full_str', ""); st.rerun()
    
    st.divider()
    st.header("🛡️ CẤU HÌNH Trinity")
    n_bottom = st.slider("Số lượng dây đáy (180 là mốc 90%):", 100, 200, 180)

    st.header("📸 QUÉT KQ (OCR)")
    up_img = st.file_uploader("Chọn ảnh", type=['jpg', 'jpeg', 'png'])
    if up_img and st.button("🚀 CHẠY OCR"):
        reader = load_ocr(); results = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
        if nums: st.session_state['raw_input'] = ", ".join(nums); st.session_state['gdb_val'] = nums[0][-2:]; st.rerun()

    st.session_state['raw_input'] = st.text_area("27 giải loto:", value=st.session_state.get('raw_input', ""), height=80)
    st.session_state['gdb_val'] = st.text_input("GĐB:", value=st.session_state.get('gdb_val', ""), max_chars=2)
    
    if st.button("🔥 PHÂN TÍCH KỲ MỚI"):
        # Hàm quét ma trận cơ bản
        def run_matrix():
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

        df_raw = run_matrix()
        mapping = get_mapping_v11(st.session_state.get('last_full_str', ""))
        dk, da, ds, dl, bottom_list = thermal_ai_engines_v75(df_raw, st.session_state['history'], st.session_state['db'], mapping, n_bottom)
        
        raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
        if len(raw_list) >= 27:
            gv = st.session_state['gdb_val']
            st.session_state['history'].insert(0, {"STT": len(st.session_state['history'])+1, "GĐB": gv, "Kết": "A" if gv in dk["Số"].tolist() else "T", "Ai": "A" if gv in da["Số"].tolist() else "T", "Bottom": "A" if gv in bottom_list else "T"})
            update_matrix_state(st.session_state['db'], [n[-2:] for n in raw_list[:27]], mapping)
            st.session_state['last_full_str'] = "".join(raw_list[:27]); st.rerun()

# --- 5. HIỂN THỊ ---
if 'last_full_str' in st.session_state:
    def run_matrix_display():
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

    df_display = run_matrix_display()
    mapping = get_mapping_v11(st.session_state.get('last_full_str', ""))
    dk, da, ds, dl, bottom_list = thermal_ai_engines_v75(df_display, st.session_state['history'], st.session_state['db'], mapping, n_bottom)
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("KẾT (39)", len(dk)); c2.metric("AI (59)", len(da)); c3.metric("SAFE (79)", len(ds)); c4.metric("BTM (180 Dây)", len(bottom_list))

    st.write(f"🛡️ **Dàn Đáy 180 dây ({len(bottom_list)} số):**"); st.code(", ".join(bottom_list))
    st.write(f"🤖 **Dàn Ai 59 (Trinity Convergence):**"); st.code(", ".join(da.sort_values("Số")["Số"].tolist()))
    st.write(f"🎯 **Dàn Kết 39 (Top Hội Tụ):**"); st.code(", ".join(dk.sort_values("Số")["Số"].tolist()))
    
    st.divider()
    col_a, col_b = st.columns([1, 1.5])
    with col_a: 
        st.subheader("📊 CHI TIẾT HỘI TỤ"); st.dataframe(da[['Số', 'Match', 'Tags', 'Điểm', 'Rank']], use_container_width=True, hide_index=True)
    with col_b: 
        st.subheader("📜 LỊCH SỬ"); st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True)
