import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
import re
from PIL import Image

# --- 1. LÕI HỆ THỐNG & OCR ---
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

# --- 2. BỘ NÃO THERMAL BALANCE AI ---
def get_thermal_ai_set(df_raw, history):
    if df_raw is None or df_raw.empty: return []

    # A. Chấm điểm theo bảng điểm của mày
    def scoring(row):
        s = 0
        if row['An'] in [2, 3]: s += 5
        elif row['An'] == 4: s += 3
        elif row['An'] in [0, 1]: s += 2
        if row['Tang'] == 1: s += 5
        elif row['Tang'] > 1: s += 4
        if 30 <= row['DâySạch'] <= 119: s += 2
        elif row['DâySạch'] >= 120: s += 1
        if 9 <= row['Cứng(10k)'] <= 29: s += 5
        elif row['Cứng(10k)'] >= 30: s += 4
        return s

    df_raw['AI_Score'] = df_raw.apply(scoring, axis=1)
    
    # B. Xác định Nhân Core (17 điểm)
    core_df = df_raw[df_raw['AI_Score'] == 17].copy()
    remaining_df = df_raw[df_raw['AI_Score'] < 17].sort_values(['AI_Score', 'Điểm'], ascending=[False, False]).copy()
    
    # C. Cân bằng nhiệt linh động (20-28)
    # Tính nhiệt của Nhân
    avg_c_core = core_df['Cứng(10k)'].mean() if not core_df.empty else 24.0
    
    final_list = core_df.copy()
    
    # Nhặt quân dự bị dựa trên xu hướng bù trừ nhiệt
    for _, row in remaining_df.iterrows():
        if len(final_list) >= 59: break
        
        current_avg = final_list['Cứng(10k)'].mean()
        # Nếu nhiệt đang cao (>25), ưu tiên nhặt thằng nguội (<24) và ngược lại
        if current_avg > 25:
            if row['Cứng(10k)'] < current_avg:
                final_list = pd.concat([final_list, pd.DataFrame([row])])
        elif current_avg < 23:
            if row['Cứng(10k)'] > current_avg:
                final_list = pd.concat([final_list, pd.DataFrame([row])])
        else:
            # Nhiệt đang đẹp thì cứ điểm cao là hốt
            final_list = pd.concat([final_list, pd.DataFrame([row])])
            
    # Ép dàn về ngưỡng 50-59 (Ưu tiên cắt tỉa để AvgC nằm trong 20-28)
    while len(final_list) > 59 or (len(final_list) > 50 and (final_list['Cứng(10k)'].mean() < 20 or final_list['Cứng(10k)'].mean() > 28)):
        # Loại thằng có điểm thấp nhất mà giúp AvgC về dải mong muốn
        final_list = final_list.sort_values('AI_Score', ascending=True)
        final_list = final_list.iloc[1:]
        
    return final_list

# --- 3. XỬ LÝ MA TRẬN ---
def process_matrix_v13_31():
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
        do_cung_10 = s["clean_window_hits"] / (WINDOW * AVG_WIRES)
        final_score = (s["total_score"] / c_count) * (1 + do_cung_10)
        data_list.append({"Số": num, "Điểm": round(final_score, 2), "An": s["max_an"], "Tang": calculate_tier(s["all_losses"], 65), "DâySạch": c_count, "Cứng(10k)": round(do_cung_10 * 100, 2)})
    
    df = pd.DataFrame(data_list).sort_values("Điểm", ascending=False).reset_index(drop=True)
    df["Rank"] = df.index + 1
    st.session_state['df_raw'] = df
    return df

# --- 4. GIAO DIỆN PHỤC HỒI CHUẨN V13.21 ---
st.set_page_config(layout="wide", page_title="Matrix V13.31 Thermal AI")
st.markdown("<h1 style='text-align: center; color: red;'>Matrix V13.31 - Thermal Balance AI</h1>", unsafe_allow_html=True)

if 'history' not in st.session_state: st.session_state['history'] = []

with st.sidebar:
    st.header("📂 HỆ THỐNG")
    if st.button("🚨 RESET"): st.session_state.clear(); st.rerun()
    up_json = st.file_uploader("📥 Nạp JSON", type=['json'])
    if up_json and st.button("NẠP DATA"):
        data = json.load(up_json); st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', []); st.session_state['last_full_str'] = data.get('last_full_str', "0"*107)
        process_matrix_v13_31(); st.rerun()

    st.divider()
    st.header("🧠 CHIẾN THUẬT AI")
    ai_on = st.toggle("Kích hoạt Thermal Balance AI", value=True)
    
    st.header("📸 QUÉT KQ (OCR)")
    up_img = st.file_uploader("Chọn ảnh", type=['jpg', 'jpeg', 'png'])
    if up_img and st.button("🚀 OCR"):
        reader = load_ocr(); results = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
        if nums: st.session_state['raw_input'] = ", ".join(nums); st.session_state['gdb_val'] = nums[0][-2:]; st.rerun()

    st.session_state['raw_input'] = st.text_area("27 giải:", value=st.session_state.get('raw_input', ""), height=80)
    st.session_state['gdb_val'] = st.text_input("GĐB:", value=st.session_state.get('gdb_val', ""), max_chars=2)
    
    if st.button("🔥 PHÂN TÍCH KỲ MỚI"):
        df_now = process_matrix_v13_31()
        if df_now is not None:
            raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
            if len(raw_list) >= 27:
                loto_list = [n[-2:] for n in raw_list[:27]]; gdb_val = st.session_state['gdb_val']
                # Chốt dàn đối soát
                df_final = get_thermal_ai_set(df_now, st.session_state['history']) if ai_on else df_now.head(55)
                ai_set = df_final["Số"].tolist()
                ai_status = f"A({len(ai_set)})" if gdb_val in ai_set else f"T({len(ai_set)})"
                avg_c_val = df_final['Cứng(10k)'].mean()
                st.session_state['history'].insert(0, {"STT": len(st.session_state['history'])+1, "GĐB": gdb_val, "Ai": ai_status, "AvgC": round(avg_c_val, 2)})
                st.session_state['last_full_str'] = "".join(raw_list[:27]); process_matrix_v13_31(); st.rerun()

# --- 5. HIỂN THỊ KẾT QUẢ ---
if st.session_state.get('df_raw') is not None:
    df_f = st.session_state['df_raw']
    df_final = get_thermal_ai_set(df_f, st.session_state['history']) if ai_on else df_f.head(55)

    col_m, col_d = st.columns([2, 1])
    with col_m: st.metric("DÀN AI CHỐT", f"{len(df_final)} quân", f"AvgC: {df_final['Cứng(10k)'].mean():.2f}")
    with col_d: st.download_button("💾 LƯU .JSON", data=json.dumps({"matrix": st.session_state.get('db'), "history": st.session_state['history'], "last_full_str": st.session_state.get('last_full_str')}), file_name="matrix_v13_31.json")
    
    st.code(", ".join(df_final.sort_values("Số")["Số"].tolist()))
    
    st.divider()
    c1, c2 = st.columns([1, 2.5])
    with c1: st.subheader("🎯 CHI TIẾT"); st.dataframe(df_final, hide_index=True)
    with c2: st.subheader("📜 LỊCH SỬ CHUẨN"); st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True)
