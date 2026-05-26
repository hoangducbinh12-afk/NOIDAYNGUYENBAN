import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
from PIL import Image

# --- 1. LÕI XỬ LÝ ---
TOTAL_POS = 107 
AVG_WIRES = 114.5
WINDOW = 10 

def get_mapping_v11(full_str):
    if not full_str or len(full_str) < TOTAL_POS: return None
    return {str(i * TOTAL_POS + j): f"{full_str[i]}{full_str[j]}" for i in range(TOTAL_POS) for j in range(TOTAL_POS)}

def calculate_tier(losses, threshold_pct):
    if not losses: return 0
    losses_sorted = sorted(losses, reverse=True)
    idx = int(len(losses_sorted) * (threshold_pct / 100)) - 1
    return losses_sorted[max(0, idx)]

def process_data_v13_13():
    if not st.session_state.get('last_full_str') or not st.session_state.get('db'): return
    current_map = get_mapping_v11(st.session_state['last_full_str'])
    db = st.session_state['db']
    threshold_pct = st.session_state.get('f_strict_val', 71)
    
    stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "max_gan": 0, "clean_wire_count": 0, "clean_window_hits": 0, "all_losses": []} for i in range(100)}
    
    for wire_id, num in current_map.items():
        wire = db.get(str(wire_id), {"score": 1000.0, "streak_win": 0, "streak_loss": 0, "hit_history": []})
        s = stats[num]
        s_win, s_loss = wire.get("streak_win", 0), wire.get("streak_loss", 0)
        s["all_losses"].append(s_loss if s_win == 0 else 0)
        if s_win > s["max_an"]: s["max_an"] = s_win
        if s_loss > s["max_gan"]: s["max_gan"] = s_loss
        s["clean_window_hits"] += sum(wire.get("hit_history", [])[-WINDOW:])
        if s_win == 0:
            s["clean_wire_count"] += 1
            s["total_score"] += wire.get("score", 1000.0) 

    data_list = []
    denominator = WINDOW * AVG_WIRES 
    for num, s in stats.items():
        if s["clean_wire_count"] == 0: continue 
        tang_val = calculate_tier(s["all_losses"], threshold_pct)
        avg_score_db = s["total_score"] / s["clean_wire_count"]
        do_cung_10 = s["clean_window_hits"] / denominator if denominator > 0 else 0
        final_score = avg_score_db + (avg_score_db * do_cung_10)
        m_an = s["max_an"]
        multiplier = {3: 1.15, 2: 1.10, 4: 1.10, 1: 1.05}.get(m_an, 1.0)
        final_score *= multiplier
        data_list.append({"Số": num, "Điểm": round(final_score, 2), "An": s["max_an"], "Gan": s["max_gan"], "Tang": tang_val, "DâySạch": s["clean_wire_count"], "Cứng(10k)": round(do_cung_10 * 100, 2)})
    
    df_raw = pd.DataFrame(data_list).sort_values("Điểm", ascending=False).reset_index(drop=True)
    df_raw["Rank"] = df_raw.index + 1
    st.session_state['df_raw'] = df_raw

# --- GIAO DIỆN & LOGIC LỌC ---
st.set_page_config(layout="wide", page_title="Matrix V13.13 Smart AvgC")
st.markdown("<h1 style='text-align: center; color: red;'>Matrix Final V13.13</h1>", unsafe_allow_html=True)

if 'history' not in st.session_state: st.session_state['history'] = []

with st.sidebar:
    st.header("🎛️ BỘ LỌC THÔNG MINH")
    
    # CHẾ ĐỘ AUTO AvgC
    use_smart_avgc = st.checkbox("Bật Auto Smart AvgC", value=False)
    
    if use_smart_avgc and len(st.session_state['history']) > 0:
        # Lấy AvgC của 5 kỳ gần nhất làm mốc
        recent_avgc = [h.get('Nhiệt(AvgC)', 20) for h in st.session_state['history'][:5]]
        market_pulse = sum(recent_avgc) / len(recent_avgc)
        st.info(f"Nhiệt kế thị trường: {market_pulse:.2f}")
        f_hard_range = (market_pulse - 5.0, market_pulse + 10.0) # Khoảng tự động
    else:
        f_hard_range = st.slider("Khoảng Cứng(10k) %:", 0.0, 100.0, (13.0, 40.0))

    f_rank = st.slider("Hạng (Rank):", 0, 100, (11, 85))
    f_an = st.slider("An thông (Ngày):", 0, 15, (0, 3))
    f_tang_min = st.slider("Tầng tối thiểu (T):", 0, 10, 1)

# --- HIỂN THỊ DÀN ---
if st.session_state.get('df_raw') is not None:
    df_f = st.session_state['df_raw']
    df_f = df_f[
        (df_f["Rank"] >= f_rank[0]) & (df_f["Rank"] <= f_rank[1]) & 
        (df_f["An"] >= f_an[0]) & (df_f["An"] <= f_an[1]) & 
        (df_f["Tang"] >= f_tang_min) & 
        (df_f["Cứng(10k)"] >= f_hard_range[0]) & (df_f["Cứng(10k)"] <= f_hard_range[1])
    ].copy()
    
    st.metric("DÀN AvgC THÔNG MINH", f"{len(df_f)} quân")
    st.code(", ".join(df_f.sort_values("Số")["Số"].tolist()))
