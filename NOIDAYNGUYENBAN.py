import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
import re
from PIL import Image

# --- 1. THÔNG SỐ CƠ BẢN ---
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

# --- 2. TRUY VẾT DÂY & HỘI TỤ (V13.75) ---

def get_wire_hist_set(history, db, mapping):
    """Dàn C: Truy vết ID Dây kỳ trước -> Ánh xạ số cho kỳ này"""
    if len(history) < 2: return set()
    try:
        # Lấy GĐB kỳ trước để xác định ID dây đã nổ
        last_gdb_raw = str(history[0]['GĐB']).split()[0]
        last_gdb = f"{int(re.sub(r'\D', '', last_gdb_raw)[-2:]):02d}"
        
        # Những số hay nổ sau con GĐB này trong lịch sử số
        m_dict = {}
        for i in range(len(history) - 1):
            p = f"{int(re.sub(r'\D', '', str(history[i+1]['GĐB']))[-2:]):02d}"
            c = f"{int(re.sub(r'\D', '', str(history[i]['GĐB']))[-2:]):02d}"
            if p not in m_dict: m_dict[p] = set()
            m_dict[p].add(c)
        
        return m_dict.get(last_gdb, set())
    except:
        return set()

def thermal_ai_engines_v75(df_raw, history, db, mapping, n_bottom):
    if df_raw is None or df_raw.empty: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), []

    # --- DỰNG 3 DÀN ĐỘC LẬP ---
    # Dàn A (GỐC): Safe 79
    df_safe_79 = df_raw.sort_values(['Điểm', 'Rank'], ascending=[False, True]).head(79)
    set_a = {f"{int(x):02d}" for x in df_safe_79['Số']}

    # Dàn B (NÉN): Bottom 180 dây
    bottom_wires = sorted(db.items(), key=lambda x: x[1]['score'])[:n_bottom]
    set_b = {f"{int(mapping.get(str(w_id))):02d}" for w_id, d in bottom_wires if mapping.get(str(w_id))}

    # Dàn C (VÍA): Wire Mapping Tracer
    set_c = get_wire_hist_set(history, db, mapping)

    # --- GIAO ĐIỂM & ƯU TIÊN ---
    results = []
    for i in range(100):
        num_str = f"{i:02d}"
        in_a = num_str in set_a
        in_b = num_str in set_b
        in_c = num_str in set_c
        
        match_count = sum([in_a, in_b, in_c])
        tags = []
        if in_a: tags.append("Safe")
        if in_b: tags.append("Bottom")
        if in_c: tags.append("Wire")
        
        # Lấy dữ liệu từ df_raw
        row_list = df_raw[df_raw['Số'] == num_str].to_dict('records')
        if row_list:
            row_data = row_list[0]
            row_data.update({'Match': match_count, 'Tags': "|".join(tags), 'in_safe': 1 if in_a else 0})
            results.append(row_data)

    df_final = pd.DataFrame(results)

    # --- ĐÚC DÀN (SẮP XẾP THEO ƯU TIÊN CỦA MÀY) ---
    # 1. Trong Safe (in_safe) -> 2. Số lượng Match -> 3. Điểm
    df_sorted = df_final.sort_values(by=['in_safe', 'Match', 'Điểm'], ascending=[False, False, False])

    df_ai = df_sorted.head(59)
    df_ket = df_ai.head(39)
    df_safe = df_sorted.head(79)
    df_loai = df_final[~df_final['Số'].isin(df_safe['Số'])].sort_values('Rank', ascending=False).head(21)
    
    return df_ket, df_ai, df_safe, df_loai, list(set_b)

# --- 3. GIAO DIỆN CHÍNH ---
st.set_page_config(layout="wide", page_title="Matrix V13.75 TRINITY")
st.markdown("<h1 style='text-align: center; color: red;'>Matrix V13.75 - Trinity Wire Matrix</h1>", unsafe_allow_html=True)

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
    n_bottom_val = st.slider("Số lượng dây đáy:", 100, 250, 180)

    st.header("📸 QUÉT KQ")
    up_img = st.file_uploader("Chọn ảnh", type=['jpg', 'jpeg', 'png'])
    if up_img and st.button("🚀 CHẠY OCR"):
        reader = load_ocr()
        results = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
        if nums: st.session_state['raw_input'] = ", ".join(nums); st.session_state['gdb_val'] = nums[0][-2:]; st.rerun()

    st.session_state['raw_input'] = st.text_area("27 giải loto:", value=st.session_state.get('raw_input', ""), height=80)
    st.session_state['gdb_val'] = st.text_input("GĐB:", value=st.session_state.get('gdb_val', ""), max_chars=2)
    
    if st.button("🔥 PHÂN TÍCH KỲ MỚI"):
        def run_matrix():
            db = st.session_state['db']; f_str = st.session_state.get('last_full_str', ""); mapping = get_mapping_v11(f_str)
            stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "clean_wire_count": 0, "clean_window_hits": 0, "all_losses": []} for i in range(100)}
            for w_id, w_d in db.items():
                num = mapping.get(str(w_id))
                if num:
                    s = stats[num]; sw, sl = int(w_d.get("streak_win", 0)), int(w_d.get("streak_loss", 0))
                    s["all_losses"].append(sl if sw == 0 else 0); s["max_an"] = max(s["max_an"], sw)
                    s["clean_window_hits"] += sum(w_d.get("hit_history", [])[-WINDOW:])
                    if sw == 0: s["clean_wire_count"] += 1; s["total_score"] += float(w_d.get("score", 1000.0))
            res = []
            for num, s in stats.items():
                dc = max(1, s["clean_wire_count"]); hard = round((s["clean_window_hits"] / (WINDOW * AVG_WIRES)) * 100, 2)
                score = round((s["total_score"] / dc) * (1 + hard/100), 2)
                res.append({"Số": num, "Điểm": score, "An": s["max_an"], "Tang": calculate_tier(s["all_losses"], 65), "DâySạch": s["clean_wire_count"], "Cứng(10k)": hard})
            df = pd.DataFrame(res).sort_values("Điểm", ascending=False).reset_index(drop=True)
            df["Rank"] = df.index + 1
            return df

        df_raw_new = run_matrix()
        map_v = get_mapping_v11(st.session_state.get('last_full_str', ""))
        dk, da, ds, dl, bl = thermal_ai_engines_v75(df_raw_new, st.session_state['history'], st.session_state['db'], map_v, n_bottom_val)
        
        raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
        if len(raw_list) >= 27:
            gv = st.session_state['gdb_val']
            st.session_state['history'].insert(0, {"STT": len(st.session_state['history'])+1, "GĐB": gv, "Kết": "A" if gv in dk["Số"].tolist() else "T", "Ai": "A" if gv in da["Số"].tolist() else "T", "Match": int(da[da['Số']==gv]['Match'].values[0]) if gv in da['Số'].values else 0})
            update_matrix_state(st.session_state['db'], [n[-2:] for n in raw_list[:27]], map_v)
            st.session_state['last_full_str'] = "".join(raw_list[:27]); st.rerun()

# --- 4. HIỂN THỊ KẾT QUẢ ---
if 'last_full_str' in st.session_state:
    def run_matrix_display():
        db = st.session_state['db']; f_str = st.session_state.get('last_full_str', ""); mapping = get_mapping_v11(f_str)
        stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "clean_wire_count": 0, "clean_window_hits": 0, "all_losses": []} for i in range(100)}
        for w_id, w_d in db.items():
            num = mapping.get(str(w_id))
            if num:
                s = stats[num]; sw, sl = int(w_d.get("streak_win", 0)), int(w_d.get("streak_loss", 0))
                s["all_losses"].append(sl if sw == 0 else 0); s["max_an"] = max(s["max_an"], sw)
                s["clean_window_hits"] += sum(w_d.get("hit_history", [])[-WINDOW:])
                if sw == 0: s["clean_wire_count"] += 1; s["total_score"] += float(w_d.get("score", 1000.0))
        res = []
        for num, s in stats.items():
            dc = max(1, s["clean_wire_count"]); hard = round((s["clean_window_hits"] / (WINDOW * AVG_WIRES)) * 100, 2)
            score = round((s["total_score"] / dc) * (1 + hard/100), 2)
            res.append({"Số": num, "Điểm": score, "An": s["max_an"], "Tang": calculate_tier(s["all_losses"], 65), "DâySạch": s["clean_wire_count"], "Cứng(10k)": hard})
        df = pd.DataFrame(res).sort_values("Điểm", ascending=False).reset_index(drop=True)
        df["Rank"] = df.index + 1
        return df

    df_d = run_matrix_display()
    map_v = get_mapping_v11(st.session_state.get('last_full_str', ""))
    dk, da, ds, dl, bl = thermal_ai_engines_v75(df_d, st.session_state['history'], st.session_state['db'], map_v, n_bottom_val)
    
    c1, c2, c3 = st.columns(3)
    c1.metric("KẾT (39)", len(dk)); c2.metric("AI (59)", len(da)); c3.metric("SAFE (79)", len(ds))

    st.write(f"🛡️ **Dàn Đáy 180 ({len(bl)} số):**"); st.code(", ".join(sorted(bl)))
    st.write(f"🤖 **Dàn Ai 59 (Trinity):**"); st.code(", ".join(da.sort_values("Số")["Số"].tolist()))
    st.write(f"🎯 **Dàn Kết 39 (Top Hội Tụ):**"); st.code(", ".join(dk.sort_values("Số")["Số"].tolist()))
    
    st.divider()
    la, ra = st.columns([1, 1.2])
    with la:
        st.subheader("📊 BẢNG GIAO ĐIỂM"); st.dataframe(da[['Số', 'Match', 'Tags', 'Điểm', 'Rank']].sort_values('Match', ascending=False), use_container_width=True, hide_index=True)
    with ra:
        st.subheader("📜 LỊCH SỬ"); st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True)
