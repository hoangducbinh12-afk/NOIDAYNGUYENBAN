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

# --- 2. BỘ NÃO AI: LINK ĐỘNG 50-59 & ĐỐI SOÁT CHUẨN ---
def get_ai_final_set(df_raw, history):
    if df_raw is None or df_raw.empty: return []
    
    # A. Phân tích vùng nổ từ lịch sử
    r_h, c_h = [], []
    for h in history:
        m = re.search(r"R(\d+).*?C(\d+)", h.get('GĐB', ''))
        if m: r_h.append(int(m.group(1))); c_h.append(int(m.group(2)))
    
    c_l, c_h_val = (np.percentile(c_h, 15), np.percentile(c_h, 85)) if c_h else (8.0, 35.0)
    r_l, r_h_val = (np.percentile(r_h, 15), np.percentile(r_h, 85)) if r_h else (10, 85)
    
    # B. Xây Lõi (Core)
    core_df = df_raw[
        (df_raw["An"] <= 3) & 
        (df_raw["Tang"].isin([1, 2, 3])) & 
        (df_raw["Cứng(10k)"] >= c_l) & (df_raw["Cứng(10k)"] <= c_h_val) & 
        (df_raw["Rank"] >= r_l) & (df_raw["Rank"] <= r_h_val)
    ].copy()
    
    # C. Điều chỉnh động 50-59
    current_count = len(core_df)
    if 50 <= current_count <= 59:
        return core_df["Số"].tolist()
    elif current_count < 50:
        # Đắp thêm vỏ cho đủ 50
        rem_df = df_raw[~df_raw["Số"].isin(core_df["Số"])].copy()
        rem_df['BP'] = rem_df.apply(lambda x: (1 if x['An'] >= 4 else 0) + (1 if x['Tang'] == 0 else 0), axis=1)
        filling = rem_df.sort_values(['BP', 'Điểm'], ascending=[True, False]).head(50 - current_count)
        return pd.concat([core_df, filling])["Số"].tolist()
    else:
        # Cắt tỉa bớt cho còn 59
        return core_df.sort_values("Điểm", ascending=False).head(59)["Số"].tolist()

# --- 3. XỬ LÝ MA TRẬN ---
def process_matrix_v13_28():
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

# --- 4. GIAO DIỆN PHỤC HỒI CHUẨN ---
st.set_page_config(layout="wide", page_title="Matrix V13.28 Dynamic AI")
st.markdown("<h1 style='text-align: center; color: yellow; background: black;'>Matrix V13.28 - Dynamic Core 50-59</h1>", unsafe_allow_html=True)

if 'db' not in st.session_state: st.session_state['db'] = {}
if 'history' not in st.session_state: st.session_state['history'] = []

with st.sidebar:
    st.header("📂 HỆ THỐNG")
    if st.button("🚨 RESET"): st.session_state.clear(); st.rerun()
    up_json = st.file_uploader("📥 Nạp JSON", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json); st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', []); st.session_state['last_full_str'] = data.get('last_full_str', "0"*107)
        process_matrix_v13_28(); st.rerun()

    st.divider()
    st.header("🧠 CHIẾN THUẬT AI")
    ai_on = st.toggle("Kích hoạt Dynamic Core (50-59)", value=True)
    
    st.header("📸 QUÉT KQ (OCR)")
    up_img = st.file_uploader("Chọn ảnh", type=['jpg', 'jpeg', 'png'])
    if up_img and st.button("🚀 CHẠY OCR"):
        reader = load_ocr(); results = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
        if nums: st.session_state['raw_input'] = ", ".join(nums); st.session_state['gdb_val'] = nums[0][-2:]; st.rerun()

    st.session_state['raw_input'] = st.text_area("27 giải:", value=st.session_state.get('raw_input', ""), height=80)
    st.session_state['gdb_val'] = st.text_input("GĐB (2 số):", value=st.session_state.get('gdb_val', ""), max_chars=2)
    
    if st.button("🔥 PHÂN TÍCH KỲ MỚI"):
        df_now = process_matrix_v13_28()
        if df_now is not None:
            raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
            if len(raw_list) >= 27:
                loto_list = [n[-2:] for n in raw_list[:27]]; gdb_val = st.session_state['gdb_val']
                
                # CHỐT DÀN ĐỂ ĐỐI SOÁT LỊCH SỬ (Chuẩn 100%)
                if ai_on:
                    ai_set = get_ai_final_set(df_now, st.session_state['history'])
                else:
                    ai_set = df_now.head(55)["Số"].tolist()
                
                ai_status = f"A({len(ai_set)})" if gdb_val in ai_set else f"T({len(ai_set)})"
                total_c = sum([df_now[df_now['Số'] == n]['Cứng(10k)'].values[0] for n in loto_list if n in df_now['Số'].values])
                
                gdb_info = gdb_val
                if gdb_val in df_now['Số'].values:
                    r = df_now[df_now['Số'] == gdb_val].iloc[0]
                    gdb_info = f"{gdb_val} (R{int(r['Rank'])}-A{int(r['An'])}-D{int(r['DâySạch'])}-T{int(r['Tang'])}-C{int(r['Cứng(10k)'])}%)"
                
                st.session_state['history'].insert(0, {"STT": len(st.session_state['history'])+1, "GĐB": gdb_info, "Ai": ai_status, "Nhiệt(AvgC)": round(total_c/27, 2)})
                st.session_state['last_full_str'] = "".join(raw_list[:27]); process_matrix_v13_28(); st.rerun()

# --- 5. HIỂN THỊ KẾT QUẢ ---
if st.session_state.get('df_raw') is not None:
    df_f = st.session_state['df_raw']
    if ai_on:
        ai_list = get_ai_final_set(df_f, st.session_state['history'])
        df_final = df_f[df_f["Số"].isin(ai_list)].copy()
    else:
        df_final = df_f.head(55)

    col_m, col_d = st.columns([2, 1])
    with col_m: st.metric("DÀN DYNAMIC AI (50-59)", f"{len(df_final)} quân")
    with col_d: st.download_button("💾 LƯU .JSON", data=json.dumps({"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state['last_full_str']}), file_name="matrix_v13_28.json")
    
    st.code(", ".join(df_final.sort_values("Số")["Số"].tolist()))
    
    st.divider()
    c1, c2 = st.columns([1, 2.5])
    with c1: st.subheader("🎯 CHI TIẾT SỐ"); st.dataframe(df_final, use_container_width=True, hide_index=True)
    with c2: st.subheader("📜 LỊCH SỬ CHUẨN"); st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True, height=800)
