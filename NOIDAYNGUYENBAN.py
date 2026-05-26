import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
import re
from PIL import Image

# --- 1. HỆ THỐNG LÕI & OCR ---
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

# --- 2. BỘ NÃO AI: THERMAL BALANCE (CORE MỚI) ---
def get_thermal_ai_set(df_raw):
    if df_raw is None or df_raw.empty: return []
    
    def scoring(row):
        s = 0
        # Vùng A: 2,3 (5đ), 4 (3đ), 0,1 (2đ)
        if row['An'] in [2, 3]: s += 5
        elif row['An'] == 4: s += 3
        elif row['An'] in [0, 1]: s += 2
        
        # Vùng T: 1,2,3 (5đ), >3 (4đ) - Theo yêu cầu mới của mày
        if row['Tang'] in [1, 2, 3]: s += 5
        elif row['Tang'] > 3: s += 4
        
        # Vùng D: 30-119 (2đ), >=120 (1đ)
        if 30 <= row['DâySạch'] <= 119: s += 2
        elif row['DâySạch'] >= 120: s += 1
        
        # Vùng C: 9-29 (5đ), >=30 (4đ)
        if 9 <= row['Cứng(10k)'] <= 29: s += 5
        elif row['Cứng(10k)'] >= 30: s += 4
        return s
    
    df_copy = df_raw.copy()
    df_copy['AI_Score'] = df_copy.apply(scoring, axis=1)
    
    # Nhân Core 17 điểm (A:2,3 & T:1,2,3 & D:30-119 & C:9-29)
    core_df = df_copy[df_copy['AI_Score'] == 17].copy()
    rem_df = df_copy[df_copy['AI_Score'] < 17].sort_values(['AI_Score', 'Điểm'], ascending=[False, False]).copy()
    
    final_df = core_df.copy()
    
    # Nhặt quân dự bị và cân bằng nhiệt 20-28
    for _, row in rem_df.iterrows():
        if len(final_df) >= 59: break
        curr_avg = final_df['Cứng(10k)'].mean() if not final_df.empty else 24.0
        
        if curr_avg > 25.5: # Ưu tiên làm nguội
            if row['Cứng(10k)'] < curr_avg: final_df = pd.concat([final_df, pd.DataFrame([row])])
        elif curr_avg < 22.5: # Ưu tiên làm nóng
            if row['Cứng(10k)'] > curr_avg: final_df = pd.concat([final_df, pd.DataFrame([row])])
        else: # Nhiệt ổn định
            final_df = pd.concat([final_df, pd.DataFrame([row])])
            
    # Ép dàn 50-59 và AvgC 20-28
    while len(final_df) > 59 or (len(final_df) > 50 and (final_df['Cứng(10k)'].mean() < 20 or final_df['Cứng(10k)'].mean() > 28)):
        final_df = final_df.sort_values(['AI_Score', 'Điểm'], ascending=[True, True]).iloc[1:]
        
    return final_df

# --- 3. XỬ LÝ MA TRẬN ---
def process_matrix_v13_35():
    full_str = st.session_state.get('last_full_str', "0"*107)
    db = st.session_state.get('db', {})
    if not db: return None
    current_map = get_mapping_v11(full_str)
    stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "clean_window_hits": 0, "all_losses": []} for i in range(100)}
    for wire_id, num in current_map.items():
        wire = db.get(str(wire_id), {"score": 1000.0, "streak_win": 0, "streak_loss": 0, "hit_history": [0]*10})
        s = stats[num]
        s_win = wire.get("streak_win", 0)
        s["all_losses"].append(wire.get("streak_loss", 0) if s_win == 0 else 0)
        if s_win > s["max_an"]: s["max_an"] = s_win
        s["clean_window_hits"] += sum(wire.get("hit_history", [])[-WINDOW:])
        if s_win == 0:
            stats[num]["clean_wire_count"] = stats[num].get("clean_wire_count", 0) + 1
            stats[num]["total_score"] += wire.get("score", 1000.0) 
            
    data_list = []
    for num, s in stats.items():
        c_count = s.get("clean_wire_count", 1)
        do_cung_10 = round((s["clean_window_hits"] / (WINDOW * AVG_WIRES)) * 100, 2)
        final_score = round((s["total_score"] / c_count) * (1 + do_cung_10/100), 2)
        data_list.append({"Số": num, "Điểm": final_score, "An": s["max_an"], "Tang": calculate_tier(s["all_losses"], 65), "DâySạch": c_count, "Cứng(10k)": do_cung_10})
    
    df = pd.DataFrame(data_list).sort_values("Điểm", ascending=False).reset_index(drop=True)
    df["Rank"] = df.index + 1
    st.session_state['df_raw'] = df
    return df

# --- 4. GIAO DIỆN PHỤC HỒI CHUẨN V13.21 ---
st.set_page_config(layout="wide", page_title="Matrix V13.35 Core Refined")
st.markdown("<h1 style='text-align: center; color: red;'>Matrix V13.35 - Thermal Core 1,2,3</h1>", unsafe_allow_html=True)

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
            st.session_state['history'] = []; st.session_state['last_full_str'] = "0" * 107
            process_matrix_v13_35(); st.rerun()

    up_json = st.file_uploader("📥 Nạp JSON", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json); st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', []); st.session_state['last_full_str'] = data.get('last_full_str', "0"*107)
        process_matrix_v13_35(); st.rerun()

    st.divider()
    st.header("🧠 CHIẾN THUẬT AI")
    ai_on = st.toggle("Kích hoạt AI Cân bằng nhiệt", value=True)
    
    if not ai_on:
        st.subheader("🕹️ ĐIỀU CHỈNH TAY")
        f_rank = st.slider("Hạng (Rank):", 0, 100, (0, 99))
        f_an = st.slider("An thông:", 0, 15, (0, 4))
        f_tang_min = st.slider("Tầng tối thiểu:", 0, 10, 1)
        f_hard = st.slider("Khoảng Cứng %:", 0.0, 100.0, (8.0, 55.0))
    
    st.header("📸 QUÉT KQ (OCR)")
    up_img = st.file_uploader("Chọn ảnh", type=['jpg', 'jpeg', 'png'])
    if up_img and st.button("🚀 OCR"):
        reader = load_ocr(); results = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
        if nums: st.session_state['raw_input'] = ", ".join(nums); st.session_state['gdb_val'] = nums[0][-2:]; st.rerun()

    st.session_state['raw_input'] = st.text_area("27 giải loto:", value=st.session_state.get('raw_input', ""), height=80)
    st.session_state['gdb_val'] = st.text_input("GĐB (2 số):", value=st.session_state.get('gdb_val', ""), max_chars=2)
    
    if st.button("🔥 PHÂN TÍCH KỲ MỚI"):
        df_now = process_matrix_v13_35()
        if df_now is not None:
            raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
            if len(raw_list) >= 27:
                gdb_val = st.session_state['gdb_val']
                gdb_row = df_now[df_now['Số'] == gdb_val]
                gdb_display = f"{gdb_val} (R{int(gdb_row.iloc[0]['Rank'])}-A{int(gdb_row.iloc[0]['An'])}-D{int(gdb_row.iloc[0]['DâySạch'])}-T{int(gdb_row.iloc[0]['Tang'])}-C{int(gdb_row.iloc[0]['Cứng(10k)'])}%)" if not gdb_row.empty else gdb_val
                df_final = get_thermal_ai_set(df_now) if ai_on else df_now[(df_now["Rank"] >= f_rank[0]) & (df_now["Rank"] <= f_rank[1]) & (df_now["An"] >= f_an[0]) & (df_now["An"] <= f_an[1]) & (df_now["Tang"] >= f_tang_min) & (df_now["Cứng(10k)"] >= f_hard[0]) & (df_now["Cứng(10k)"] <= f_hard[1])]
                st.session_state['history'].insert(0, {"STT": len(st.session_state['history'])+1, "GĐB": gdb_display, "Ai": f"A({len(df_final)})" if gdb_val in df_final["Số"].tolist() else f"T({len(df_final)})", "AvgC": round(df_final['Cứng(10k)'].mean(), 2)})
                st.session_state['last_full_str'] = "".join(raw_list[:27]); process_matrix_v13_35(); st.rerun()

# --- 5. HIỂN THỊ KẾT QUẢ ---
if st.session_state.get('df_raw') is not None:
    df_f = st.session_state['df_raw']
    df_display = get_thermal_ai_set(df_f) if ai_on else df_f[(df_f["Rank"] >= f_rank[0]) & (df_f["Rank"] <= f_rank[1]) & (df_f["An"] >= f_an[0]) & (df_f["An"] <= f_an[1]) & (df_f["Tang"] >= f_tang_min) & (df_f["Cứng(10k)"] >= f_hard[0]) & (df_f["Cứng(10k)"] <= f_hard[1])]

    col_m, col_d = st.columns([2, 1])
    with col_m: st.metric("DÀN CHỐT", f"{len(df_display)} quân", f"AvgC: {df_display['Cứng(10k)'].mean():.2f}")
    with col_d: st.download_button("💾 LƯU .JSON", data=json.dumps({"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state['last_full_str']}), file_name="matrix_v13_35.json")
    
    st.code(", ".join(df_display.sort_values("Số")["Số"].tolist()))
    
    st.divider()
    c1, c2 = st.columns([1, 2.8])
    with c1: st.subheader("🎯 CHI TIẾT"); st.dataframe(df_display, use_container_width=True, hide_index=True)
    with c2: st.subheader("📜 LỊCH SỬ V13.21"); st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True, height=800)
