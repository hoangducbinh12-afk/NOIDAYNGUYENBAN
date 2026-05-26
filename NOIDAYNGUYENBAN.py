import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
import re
from PIL import Image

# --- 1. LÕI HỆ THỐNG ---
TOTAL_POS = 107 
AVG_WIRES = 114.5
WINDOW = 10 

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'])

def get_mapping_v11(full_str):
    if not full_str or len(full_str) < TOTAL_POS: return None
    return {str(i * TOTAL_POS + j): f"{full_str[i]}{full_str[j]}" for i in range(TOTAL_POS) for j in range(TOTAL_POS)}

def calculate_tier(losses, threshold_pct):
    if not losses: return 0
    losses_sorted = sorted(losses, reverse=True)
    idx = int(len(losses_sorted) * (threshold_pct / 100)) - 1
    return losses_sorted[max(0, idx)]

# --- 2. BỘ NÃO AI: XÂY LÕI & ĐẮP VỎ ---
def ai_core_filling_engine(history, df_raw):
    if df_raw is None or df_raw.empty:
        return df_raw, "⚠️ Chờ dữ liệu..."

    # A. PHÂN TÍCH VÙNG NỔ LỊCH SỬ (R & C)
    r_h, c_h = [], []
    for h in history:
        m = re.search(r"R(\d+).*?C(\d+)", h.get('GĐB', ''))
        if m:
            r_h.append(int(m.group(1))); c_h.append(int(m.group(2)))
    
    # Xác định vùng nổ dày nhất (Percentile 15-85)
    c_low, c_high = (np.percentile(c_h, 15), np.percentile(c_h, 85)) if c_h else (9.0, 35.0)
    r_low, r_high = (np.percentile(r_h, 15), np.percentile(r_h, 85)) if r_h else (10, 80)

    # B. XÁC ĐỊNH NHÂN DÀN (CORE)
    # Thỏa mãn đồng thời cả 4 điều kiện
    core_df = df_raw[
        (df_raw["An"] <= 3) & 
        (df_raw["Tang"].isin([1, 2, 3])) & 
        (df_raw["Cứng(10k)"] >= c_low) & (df_raw["Cứng(10k)"] <= c_high) & 
        (df_raw["Rank"] >= r_low) & (df_raw["Rank"] <= r_high)
    ].copy()
    core_df['Source'] = 'CORE'

    # C. LẤP ĐẦY (FILLING)
    # Lấy các số không nằm trong lõi
    remaining_df = df_raw[~df_raw["Số"].isin(core_df["Số"])].copy()
    
    # Tính Điểm Đen để nhặt thằng ít xấu nhất
    def scoring(row):
        penalty = 0
        if row['An'] >= 4: penalty += 1
        if row['Tang'] == 0: penalty += 1
        if row['Cứng(10k)'] < c_low or row['Cứng(10k)'] > c_high: penalty += 1
        if row['Rank'] < r_low or row['Rank'] > r_high: penalty += 1
        return penalty

    remaining_df['BlackPoint'] = remaining_df.apply(scoring, axis=1)
    remaining_df['Source'] = 'FILLING'
    
    # Sắp xếp thằng ít Điểm Đen nhất lên đầu
    remaining_df = remaining_df.sort_values(['BlackPoint', 'Điểm'], ascending=[True, False])
    
    # Kết hợp
    needed = 55 - len(core_df)
    if needed > 0:
        filling_df = remaining_df.head(needed)
        final_df = pd.concat([core_df, filling_df])
    else:
        # Nếu lõi đã > 55 quân, ta giữ nguyên lõi (tối đa 59)
        final_df = core_df.head(59)

    msg = f"💎 AI Core: Giữ {len(core_df)} quân Lõi. Đã đắp thêm {max(0, needed)} quân Vỏ. Tổng: {len(final_df)} quân."
    return final_df.sort_values("Điểm", ascending=False), msg

# --- 3. XỬ LÝ MA TRẬN ---
def process_matrix_v13_26():
    full_str = st.session_state.get('last_full_str', "0"*107)
    db = st.session_state.get('db', {})
    if not db: return None
    current_map = get_mapping_v11(full_str)
    stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "max_gan": 0, "clean_wire_count": 0, "clean_window_hits": 0, "all_losses": []} for i in range(100)}
    for wire_id, num in current_map.items():
        wire = db.get(str(wire_id), {"score": 1000.0, "streak_win": 0, "streak_loss": 0, "hit_history": [0]*10})
        s = stats[num]
        s_win = wire.get("streak_win", 0)
        s["all_losses"].append(wire.get("streak_loss", 0) if s_win == 0 else 0)
        if s_win > s["max_an"]: s["max_an"] = s_win
        s["clean_window_hits"] += sum(wire.get("hit_history", [])[-WINDOW:])
        if s_win == 0:
            s["clean_wire_count"] += 1
            s["total_score"] += wire.get("score", 1000.0) 

    data_list = []
    denominator = WINDOW * AVG_WIRES 
    for num, s in stats.items():
        c_count = s["clean_wire_count"] if s["clean_wire_count"] > 0 else 1
        tang_val = calculate_tier(s["all_losses"], 65)
        avg_score_db = s["total_score"] / c_count
        do_cung_10 = s["clean_window_hits"] / denominator
        final_score = (avg_score_db + (avg_score_db * do_cung_10)) * {3:1.15, 2:1.1, 4:1.1, 1:1.05}.get(s["max_an"], 1.0)
        data_list.append({"Số": num, "Điểm": round(final_score, 2), "An": s["max_an"], "Gan": s["max_gan"], "Tang": tang_val, "DâySạch": s["clean_wire_count"], "Cứng(10k)": round(do_cung_10 * 100, 2)})
    
    df = pd.DataFrame(data_list).sort_values("Điểm", ascending=False).reset_index(drop=True)
    df["Rank"] = df.index + 1
    st.session_state['df_raw'] = df
    return df

# --- 4. GIAO DIỆN PHẲNG ---
st.set_page_config(layout="wide", page_title="Matrix V13.26 Core Engine")
st.markdown("<h1 style='text-align: center; color: red;'>Matrix V13.26 - Core & Filling AI</h1>", unsafe_allow_html=True)

if 'history' not in st.session_state: st.session_state['history'] = []

with st.sidebar:
    st.header("📂 HỆ THỐNG")
    if st.button("🚨 RESET"): st.session_state.clear(); st.rerun()
    up_json = st.file_uploader("📥 Nạp JSON", type=['json'])
    if up_json and st.button("NẠP DATA"):
        data = json.load(up_json); st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', []); st.session_state['last_full_str'] = data.get('last_full_str', "0"*107)
        process_matrix_v13_26(); st.rerun()

    st.divider()
    st.header("🧠 CHIẾN THUẬT AI")
    ai_on = st.toggle("Kích hoạt Core & Filling Engine", value=True)
    
    st.header("📸 QUÉT KQ")
    up_img = st.file_uploader("Chọn ảnh", type=['jpg', 'jpeg', 'png'])
    if up_img and st.button("🚀 OCR"):
        reader = load_ocr(); results = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
        if nums: st.session_state['raw_input'] = ", ".join(nums); st.session_state['gdb_val'] = nums[0][-2:]; st.rerun()

    st.session_state['raw_input'] = st.text_area("27 giải:", value=st.session_state.get('raw_input', ""), height=80)
    st.session_state['gdb_val'] = st.text_input("GĐB:", value=st.session_state.get('gdb_val', ""), max_chars=2)

# --- 5. HIỂN THỊ KẾT QUẢ ---
if st.session_state.get('df_raw') is not None:
    df_raw = st.session_state['df_raw']
    if ai_on:
        df_final, msg = ai_core_filling_engine(st.session_state['history'], df_raw)
        st.success(msg)
    else:
        df_final = df_raw.head(55)

    col_m, col_d = st.columns([2, 1])
    with col_m: st.metric("DÀN CHỐT (50-59)", f"{len(df_final)} quân")
    with col_d: st.download_button("💾 LƯU .JSON", data=json.dumps({"matrix": st.session_state.get('db'), "history": st.session_state['history'], "last_full_str": st.session_state.get('last_full_str')}), file_name="matrix_v13_26.json")
    
    st.code(", ".join(df_final.sort_values("Số")["Số"].tolist()))
    
    st.divider()
    c1, c2 = st.columns([1, 2.8])
    with c1: st.subheader("🎯 CHI TIẾT"); st.dataframe(df_final[["Số", "Điểm", "An", "Tang", "Cứng(10k)", "Rank", "Source"]], use_container_width=True, hide_index=True)
    with c2: st.subheader("📜 LỊCH SỬ"); st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True)
