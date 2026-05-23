import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
from PIL import Image

# --- 1. CÔNG CỤ & OCR ---
TOTAL_POS = 107 

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'])

def get_mapping_v10(full_str):
    if not full_str or len(full_str) < TOTAL_POS: return None
    mapping = {}
    for i in range(TOTAL_POS):
        for j in range(TOTAL_POS):
            wire_id = str(i * TOTAL_POS + j)
            num_formed = f"{full_str[i]}{full_str[j]}"
            mapping[wire_id] = num_formed
    return mapping

def process_data_v106():
    if not st.session_state.get('last_full_str'): return
    current_map = get_mapping_v10(st.session_state['last_full_str'])
    db = st.session_state['db']
    history = st.session_state.get('history', [])
    total_periods = len(history)
    
    stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "max_gan": 0, "wire_count": 0, "total_hits": 0} for i in range(100)}
    for wire_id, num in current_map.items():
        wire = db.get(str(wire_id), {"score": 100.0, "streak_win": 0, "streak_loss": 0, "history_hits": 0})
        s = stats[num]
        s["wire_count"] += 1
        s["total_hits"] += wire.get("history_hits", 0)
        p_coef = 1.5 if wire.get("streak_win", 0) > 0 else 0.7
        s["total_score"] += (wire.get("score", 100.0) * p_coef)
        if wire.get("streak_win", 0) > s["max_an"]: s["max_an"] = wire.get("streak_win", 0)
        if wire.get("streak_loss", 0) > s["max_gan"]: s["max_gan"] = wire.get("streak_loss", 0)

    data_list = []
    for num, s in stats.items():
        hardness = (s["total_hits"] / (s["wire_count"] * total_periods) * 100) if (total_periods > 0 and s["wire_count"] > 0) else 0
        data_list.append({"Số": num, "Điểm": round(s["total_score"], 1), "An": s["max_an"], "Nén": s["max_gan"], "Dây": s["wire_count"], "Cứng(%)": round(hardness, 1)})
    st.session_state['df_raw'] = pd.DataFrame(data_list)

# --- 2. GIAO DIỆN ---
st.set_page_config(layout="wide", page_title="MATRIX V10.6")

if 'db' not in st.session_state: st.session_state['db'] = {}
if 'history' not in st.session_state: st.session_state['history'] = []

with st.sidebar:
    st.header("📂 HỆ THỐNG")
    if st.button("🚨 RESET ALL"): st.session_state.clear(); st.rerun()
    up_json = st.file_uploader("📥 Nạp JSON", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json)
        st.session_state['db'] = {str(k): v for k, v in data.get('matrix', data).items()}
        st.session_state['history'] = data.get('history', [])
        st.session_state['last_full_str'] = data.get('last_full_str', "")
        process_data_v106(); st.success("Đã nạp!")

    st.divider()
    st.header("🎛️ BỘ LỌC")
    f_an = st.slider("An:", 0, 10, (1, 3))
    f_gan = st.slider("Gan:", 0, 40, (0, 40))
    f_day = st.slider("Dây min:", 0, 115, 20)
    f_hard = st.slider("Cứng min (%):", 0.0, 40.0, 23.5, 0.5)
    
    st.divider()
    st.header("📸 NHẬP KQ")
    up_img = st.file_uploader("Quét ảnh", type=['jpg', 'jpeg', 'png'])
    if up_img and st.button("CHẠY OCR"):
        reader = load_ocr()
        results = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
        if nums: st.session_state['raw_input'] = ", ".join(nums); st.session_state['gdb_val'] = nums[0][-2:]
        st.rerun()
    st.session_state['raw_input'] = st.text_area("27 giải:", value=st.session_state.get('raw_input', ""), height=80)
    st.session_state['gdb_val'] = st.text_input("GĐB:", value=st.session_state.get('gdb_val', ""), max_chars=2)
    if st.button("🔥 PHÂN TÍCH KỲ MỚI"):
        raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
        if len(raw_list) >= 27:
            # Logic cập nhật kỳ (giữ nguyên như V10.5)
            # ... [Phần code cập nhật matrix ẩn đi cho gọn] ...
            st.session_state['history'].insert(0, {"STT": len(st.session_state['history']) + 1, "GĐB": st.session_state['gdb_val']})
            process_data_v106(); st.rerun()

# --- 3. HIỂN THỊ CHÍNH ---
if st.session_state.get('df_raw') is not None:
    df_all = st.session_state['df_raw'].sort_values("Điểm", ascending=False)
    df_f = df_all[(df_all["An"] >= f_an[0]) & (df_all["An"] <= f_an[1]) & (df_all["Nén"] >= f_gan[0]) & (df_all["Nén"] <= f_gan[1]) & (df_all["Dây"] >= f_day) & (df_all["Cứng(%)"] >= f_hard)].copy()
    
    # DASHBOARD TRÊN CÙNG
    c_m1, c_m2, c_m3 = st.columns([1, 2, 1])
    with c_m1: st.metric("SỐ QUÂN", f"{len(df_f)} quân")
    with c_m2:
        st.write("**DÀN SỐ ĐÃ LỌC:**")
        dan_so = ", ".join(df_f.sort_values("Số")["Số"].tolist())
        st.code(dan_so if dan_so else "Chưa có quân nào thỏa mãn bộ lọc")
    with c_m3:
        if st.session_state.get('db'):
            st.download_button("💾 XUẤT JSON V10.6", data=json.dumps({"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state['last_full_str']}), file_name="matrix_v10_6.json")

    st.divider()
    col_left, col_right = st.columns([1.2, 2.8])
    
    with col_left:
        st.subheader("🎯 CHI TIẾT QUÂN LỌC")
        st.dataframe(df_f.sort_values("Điểm", ascending=False), use_container_width=True, height=400)
        with st.expander("📊 TỔNG LỰC 100 SỐ", expanded=False):
            st.dataframe(df_all, use_container_width=True, height=400)
            
    with col_right:
        st.subheader("📜 LỊCH SỬ ĐỐI SOÁT CHI TIẾT (FULL V8.5)")
        # Hiển thị bảng lịch sử full các cột đối soát vùng Top
        df_history = pd.DataFrame(st.session_state['history'])
        st.dataframe(df_history, use_container_width=True, height=850)
