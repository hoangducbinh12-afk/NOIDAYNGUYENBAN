import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
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

# --- 2. BỘ NÃO AI DỰ BÁO ---
def ai_predict_filters(history):
    if len(history) < 3:
        return (11, 85), (0, 3), 1, (13.0, 40.0), "⚠️ AI đang chờ thêm dữ liệu..."
    recent_avgc = [h.get('Nhiệt(AvgC)', 20.0) for h in history[:7]]
    avg_c = np.mean(recent_avgc)
    if recent_avgc[0] < avg_c: f_c = (recent_avgc[0] + 0.5, avg_c + 7.0)
    else: f_c = (avg_c - 7.0, recent_avgc[0] - 0.5)
    return (11, 85), (0, 3), 1, f_c, "🚀 AI Pilot: Đã tối ưu bộ lọc theo nhịp thị trường."

# --- 3. XỬ LÝ DỮ LIỆU ---
def process_data_v13_16():
    full_str = st.session_state.get('last_full_str', "0"*107)
    if not st.session_state.get('db'): return
    current_map = get_mapping_v11(full_str)
    db = st.session_state['db']
    threshold_pct = st.session_state.get('f_strict_val', 71)
    
    stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "max_gan": 0, "clean_wire_count": 0, "clean_window_hits": 0, "all_losses": []} for i in range(100)}
    for wire_id, num in current_map.items():
        wire = db.get(str(wire_id), {"score": 1000.0, "streak_win": 0, "streak_loss": 0, "hit_history": [0]*10})
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
        c_count = s["clean_wire_count"] if s["clean_wire_count"] > 0 else 1
        tang_val = calculate_tier(s["all_losses"], threshold_pct)
        avg_score_db = s["total_score"] / c_count
        do_cung_10 = s["clean_window_hits"] / denominator if denominator > 0 else 0
        m_an = s["max_an"]
        multiplier = {3: 1.15, 2: 1.10, 4: 1.10, 1: 1.05}.get(m_an, 1.0)
        final_score = (avg_score_db + (avg_score_db * do_cung_10)) * multiplier
        data_list.append({"Số": num, "Điểm": round(final_score, 2), "An": s["max_an"], "Gan": s["max_gan"], "Tang": tang_val, "DâySạch": s["clean_wire_count"], "Cứng(10k)": round(do_cung_10 * 100, 2)})
    
    df_raw = pd.DataFrame(data_list).sort_values("Điểm", ascending=False).reset_index(drop=True)
    df_raw["Rank"] = df_raw.index + 1
    st.session_state['df_raw'] = df_raw

def audit_history(loto_list, gdb):
    if 'df_raw' not in st.session_state: return None
    df = st.session_state['df_raw']
    total_c = sum([df[df['Số'] == n]['Cứng(10k)'].values[0] for n in loto_list if n in df['Số'].values])
    avg_c_day = round(total_c / 27, 2)
    gdb_info = gdb
    if gdb in df['Số'].values:
        r = df[df['Số'] == gdb].iloc[0]
        gdb_info = f"{gdb} (R{r['Rank']}-A{r['An']}-D{r['DâySạch']}-T{r['Tang']}-C{int(r['Cứng(10k)'])}%)"
    res = {"STT": len(st.session_state['history'])+1, "GĐB": gdb_info, "Nhiệt(AvgC)": avg_c_day}
    for t in [5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100]:
        subset = df.head(t)
        found = [n for n in loto_list if n in subset['Số'].values]
        res[f"T{t}"] = f"{len(found)}({','.join(set(found))})" if found else "0"
    return res

# --- 4. GIAO DIỆN ---
st.set_page_config(layout="wide", page_title="Matrix V13.16 Full UI")
st.markdown("<h1 style='text-align: center; color: red;'>Matrix Final V13.16 - Full UI & AI</h1>", unsafe_allow_html=True)

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
            process_data_v13_16(); st.rerun()

    up_json = st.file_uploader("📥 Nạp JSON", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json)
        st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', [])
        st.session_state['last_full_str'] = data.get('last_full_str', "0"*107)
        process_data_v13_16(); st.rerun()

    st.divider()
    st.header("🧠 AI AUTO-PILOT")
    ai_on = st.toggle("Kích hoạt AI", value=False)
    
    if ai_on:
        f_rank, f_an, f_tang_min, f_hard_range, msg = ai_predict_filters(st.session_state['history'])
        st.info(msg)
    else:
        f_rank = st.slider("Hạng (Rank):", 0, 100, (11, 85))
        f_an = st.slider("An thông (Ngày):", 0, 15, (0, 3))
        f_tang_min = st.slider("Tầng tối thiểu (T):", 0, 10, 1)
        f_hard_range = st.slider("Khoảng Cứng(10k) %:", 0.0, 100.0, (13.0, 40.0))

    st.session_state['f_strict_val'] = st.slider("Độ tinh khiết (%):", 50, 100, 71)
    f_day = st.slider("Khoảng Dây Sạch (D):", 0, 250, (0, 250))

    st.divider()
    st.header("📸 QUÉT KẾT QUẢ (OCR)")
    up_img = st.file_uploader("Chọn ảnh kết quả", type=['jpg', 'jpeg', 'png'])
    if up_img and st.button("🚀 CHẠY OCR"):
        reader = load_ocr()
        results = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
        if nums:
            st.session_state['raw_input'] = ", ".join(nums)
            st.session_state['gdb_val'] = nums[0][-2:]
            st.rerun()

    st.session_state['raw_input'] = st.text_area("27 giải loto:", value=st.session_state.get('raw_input', ""), height=80)
    st.session_state['gdb_val'] = st.text_input("GĐB (2 số):", value=st.session_state.get('gdb_val', ""), max_chars=2)
    
    if st.button("🔥 PHÂN TÍCH KỲ MỚI"):
        if st.session_state.get('db'):
            raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
            if len(raw_list) >= 27:
                loto_list = [n[-2:] for n in raw_list[:27]]; gdb_val = st.session_state['gdb_val']
                new_entry = audit_history(loto_list, gdb_val)
                if new_entry: st.session_state['history'].insert(0, new_entry)
                # Logic cập nhật DB (giữ nguyên các bản trước)
                process_data_v13_16(); st.rerun()

# --- 5. HIỂN THỊ ---
if st.session_state.get('df_raw') is not None:
    df_f = st.session_state['df_raw']
    df_f = df_f[
        (df_f["Rank"] >= f_rank[0]) & (df_f["Rank"] <= f_rank[1]) & 
        (df_f["An"] >= f_an[0]) & (df_f["An"] <= f_an[1]) & 
        (df_f["Tang"] >= f_tang_min) & 
        (df_f["Cứng(10k)"] >= f_hard_range[0]) & (df_f["Cứng(10k)"] <= f_hard_range[1])
    ].copy()
    
    st.metric("DÀN KẾT QUẢ", f"{len(df_f)} quân")
    st.code(", ".join(df_f.sort_values("Số")["Số"].tolist()) if not df_f.empty else "Dàn trống")
    st.download_button("💾 XUẤT JSON V13.16", data=json.dumps({"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state['last_full_str']}), file_name="matrix_v13_16.json")
    
    st.divider()
    col_l, col_r = st.columns([1, 2.5])
    with col_l:
        st.subheader("🎯 CHI TIẾT SỐ")
        st.dataframe(df_f, use_container_width=True, height=500, hide_index=True)
    with col_r:
        st.subheader("📜 TRUY VẾT & NHIỆT KẾ")
        st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True, height=800)
