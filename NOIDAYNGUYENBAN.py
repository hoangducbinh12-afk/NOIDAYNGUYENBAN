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

# --- 2. BỘ NÃO AI TỐI ƯU AN TOÀN 65% (DÀN 50-59) ---
def ai_safety_65_engine(history, df_raw):
    # Cấu hình "Pháo đài" theo yêu cầu mới
    f_purity = 65
    f_an = (0, 4)
    f_hard_min = 8.0
    
    if df_raw is None or df_raw.empty:
        return (0, 99), 1, (0, 250), (8.0, 50.0), "⚠️ Chờ tính toán dữ liệu..."

    # Lọc sơ bộ theo An và Cứng trước
    temp_df = df_raw[
        (df_raw["An"] >= f_an[0]) & (df_raw["An"] <= f_an[1]) & 
        (df_raw["Cứng(10k)"] >= f_hard_min) & (df_raw["Tang"] >= 1)
    ]
    
    # AI tự động điều chỉnh Rank để ép dàn về 50-59 số
    f_r_max = 99
    for r in range(99, 30, -1):
        count = len(temp_df[temp_df["Rank"] <= r])
        if count <= 59:
            f_r_max = r
            if count >= 50: break
            
    f_r = (0, f_r_max)
    
    # Phỏng đoán dải Dây (D) từ lịch sử
    d_h = [int(re.search(r"D(\d+)", h.get('GĐB', '')).group(1)) for h in history if re.search(r"D(\d+)", h.get('GĐB', ''))]
    f_d = (int(np.percentile(d_h, 5)) if d_h else 0, 250)

    msg = f"🛡️ AI 65% Mode: Dàn {len(temp_df[temp_df['Rank'] <= f_r_max])} quân. Vùng an toàn R(0-{f_r_max}) đã được xác lập."
    return f_r, 1, f_d, (f_hard_min, 55.0), msg

# --- 3. XỬ LÝ MA TRẬN ---
def process_matrix_v13_24():
    full_str = st.session_state.get('last_full_str', "0"*107)
    db = st.session_state.get('db', {})
    if not db: return None
    
    # CHỐT ĐỘ TINH KHIẾT 65%
    st.session_state['f_strict_val'] = 65
    threshold_pct = 65
    
    current_map = get_mapping_v11(full_str)
    stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "max_gan": 0, "clean_wire_count": 0, "clean_window_hits": 0, "all_losses": []} for i in range(100)}
    
    for wire_id, num in current_map.items():
        wire = db.get(str(wire_id), {"score": 1000.0, "streak_win": 0, "streak_loss": 0, "hit_history": [0]*10})
        s = stats[num]
        s_win, s_loss = wire.get("streak_win", 0), wire.get("streak_loss", 0)
        s["all_losses"].append(s_loss if s_win == 0 else 0)
        if s_win > s["max_an"]: s["max_an"] = s_win
        s["clean_window_hits"] += sum(wire.get("hit_history", [])[-WINDOW:])
        if s_win == 0:
            s["clean_wire_count"] += 1
            s["total_score"] += wire.get("score", 1000.0) 

    data_list = []
    denominator = WINDOW * AVG_WIRES 
    for num, s in stats.items():
        c_count = s["clean_wire_count"] if s["clean_wire_count"] > 0 else 1
        tang_val = calculate_tier(s["all_losses"], threshold_pct)
        avg_score_db = s["total_score"] / c_count
        do_cung_10 = s["clean_window_hits"] / denominator if denominator > 0 else 0
        multiplier = {3: 1.15, 2: 1.10, 4: 1.10, 1: 1.05}.get(s["max_an"], 1.0)
        final_score = (avg_score_db + (avg_score_db * do_cung_10)) * multiplier
        data_list.append({"Số": num, "Điểm": round(final_score, 2), "An": s["max_an"], "Gan": s["max_gan"], "Tang": tang_val, "DâySạch": s["clean_wire_count"], "Cứng(10k)": round(do_cung_10 * 100, 2)})
    
    df = pd.DataFrame(data_list).sort_values("Điểm", ascending=False).reset_index(drop=True)
    df["Rank"] = df.index + 1
    st.session_state['df_raw'] = df
    return df

# --- 4. GIAO DIỆN ---
st.set_page_config(layout="wide", page_title="Matrix V13.24 Safety 65%")
st.markdown("<h1 style='text-align: center; color: red;'>Matrix V13.24 - Safety Fortress 65% (50-59)</h1>", unsafe_allow_html=True)

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
            process_matrix_v13_24(); st.rerun()

    up_json = st.file_uploader("📥 Nạp JSON", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json)
        st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', [])
        st.session_state['last_full_str'] = data.get('last_full_str', "0"*107)
        process_matrix_v13_24(); st.rerun()

    st.divider()
    st.header("🧠 SIÊU AI 65% (AUTO)")
    ai_on = st.toggle("Kích hoạt AI Tối ưu an toàn", value=True)
    
    if ai_on and 'df_raw' in st.session_state:
        f_rank, f_tang_min, f_day, f_hard, msg = ai_safety_65_engine(st.session_state['history'], st.session_state['df_raw'])
        f_an = (0, 4)
        st.success(msg)
    else:
        st.header("🎛️ BỘ LỌC TAY")
        f_rank = st.slider("Hạng (Rank):", 0, 100, (0, 99))
        f_an = st.slider("An thông:", 0, 15, (0, 4))
        f_tang_min = st.slider("Tầng tối thiểu:", 0, 10, 1)
        f_day = st.slider("Dây Sạch (D):", 0, 250, (0, 250))
        f_hard = st.slider("Khoảng Cứng %:", 0.0, 100.0, (8.0, 50.0))

    st.divider()
    st.header("📸 QUÉT KQ (OCR)")
    up_img = st.file_uploader("Chọn ảnh kết quả", type=['jpg', 'jpeg', 'png'])
    if up_img and st.button("🚀 CHẠY OCR"):
        reader = load_ocr(); results = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
        if nums:
            st.session_state['raw_input'] = ", ".join(nums)
            st.session_state['gdb_val'] = nums[0][-2:]; st.rerun()

    st.session_state['raw_input'] = st.text_area("27 giải loto:", value=st.session_state.get('raw_input', ""), height=80)
    st.session_state['gdb_val'] = st.text_input("GĐB (2 số):", value=st.session_state.get('gdb_val', ""), max_chars=2)
    
    if st.button("🔥 PHÂN TÍCH KỲ MỚI"):
        df_now = process_matrix_v13_24()
        if df_now is not None:
            raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
            if len(raw_list) >= 27:
                loto_list = [n[-2:] for n in raw_list[:27]]; gdb_val = st.session_state['gdb_val']
                # Kiểm chứng AI
                df_ai = df_now[
                    (df_now["Rank"] >= f_rank[0]) & (df_now["Rank"] <= f_rank[1]) & 
                    (df_now["An"] >= f_an[0]) & (df_now["An"] <= f_an[1]) & 
                    (df_now["Tang"] >= f_tang_min) & (df_now["DâySạch"] >= f_day[0]) & (df_now["DâySạch"] <= f_day[1]) &
                    (df_now["Cứng(10k)"] >= f_hard[0]) & (df_now["Cứng(10k)"] <= f_hard[1])
                ]
                ai_set = df_ai["Số"].tolist()
                ai_status = f"A({len(ai_set)})" if gdb_val in ai_set else f"T({len(ai_set)})"
                
                total_c = sum([df_now[df_now['Số'] == n]['Cứng(10k)'].values[0] for n in loto_list if n in df_now['Số'].values])
                gdb_info = gdb_val
                if gdb_val in df_now['Số'].values:
                    r = df_now[df_now['Số'] == gdb_val].iloc[0]
                    gdb_info = f"{gdb_val} (R{int(r['Rank'])}-A{int(r['An'])}-D{int(r['DâySạch'])}-T{int(r['Tang'])}-C{int(r['Cứng(10k)'])}%)"
                
                st.session_state['history'].insert(0, {"STT": len(st.session_state['history'])+1, "GĐB": gdb_info, "Ai": ai_status, "Nhiệt(AvgC)": round(total_c/27, 2)})
                st.session_state['last_full_str'] = "".join(raw_list[:27])
                process_matrix_v13_24(); st.rerun()

# --- 5. HIỂN THỊ KẾT QUẢ ---
if st.session_state.get('df_raw') is not None:
    df_f = st.session_state['df_raw']
    df_final = df_f[
        (df_f["Rank"] >= f_rank[0]) & (df_f["Rank"] <= f_rank[1]) & 
        (df_f["An"] >= f_an[0]) & (df_f["An"] <= f_an[1]) & 
        (df_f["Tang"] >= f_tang_min) & (df_f["DâySạch"] >= f_day[0]) & (df_f["DâySạch"] <= f_day[1]) &
        (df_f["Cứng(10k)"] >= f_hard[0]) & (df_f["Cứng(10k)"] <= f_hard[1])
    ].copy()
    
    col_m, col_d = st.columns([2, 1])
    with col_m: st.metric("DÀN 65% SIÊU AN TOÀN", f"{len(df_final)} quân")
    with col_d: st.download_button("💾 LƯU .JSON", data=json.dumps({"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state['last_full_str']}), file_name="matrix_v13_24.json")
    
    st.code(", ".join(df_final.sort_values("Số")["Số"].tolist()) if not df_final.empty else "Dàn trống")
    
    st.divider()
    c1, c2 = st.columns([1, 2.8])
    with c1: st.subheader("🎯 CHI TIẾT"); st.dataframe(df_final, use_container_width=True, height=500, hide_index=True)
    with c2: st.subheader("📜 LỊCH SỬ"); st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True, height=800)
