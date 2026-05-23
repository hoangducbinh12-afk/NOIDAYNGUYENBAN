import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
from PIL import Image

# --- 1. KHỞI TẠO & OCR ---
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

# --- 2. HÀM XỬ LÝ DỮ LIỆU ---
def refresh_all_logic():
    if not st.session_state.get('last_full_str'): return
    
    current_map = get_mapping_v10(st.session_state['last_full_str'])
    db = st.session_state['db']
    total_periods = len(st.session_state['history'])
    
    stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "max_gan": 0, "wire_count": 0, "total_hits": 0} for i in range(100)}

    for wire_id, num in current_map.items():
        wire = db.get(wire_id, {"score": 100.0, "streak_win": 0, "streak_loss": 0, "history_hits": 0})
        s = stats[num]
        s["wire_count"] += 1
        s["total_hits"] += wire.get("history_hits", 0)
        p_coef = 1.5 if wire.get("streak_win", 0) > 0 else 0.7
        s["total_score"] += (wire.get("score", 100.0) * p_coef)
        if wire.get("streak_win", 0) > s["max_an"]: s["max_an"] = wire.get("streak_win", 0)
        if wire.get("streak_loss", 0) > s["max_gan"]: s["max_gan"] = wire.get("streak_loss", 0)

    data_list = []
    for num, s in stats.items():
        hardness = (s["total_hits"] / (s["wire_count"] * total_periods) * 100) if total_periods > 0 else 0
        data_list.append({
            "Số": num, "Điểm": round(s["total_score"], 1), "An": s["max_an"], 
            "Nén": s["max_gan"], "Dây": s["wire_count"], "Cứng(%)": round(hardness, 1)
        })
    
    df_all = pd.DataFrame(data_list)
    st.session_state['df_all'] = df_all.sort_values("Điểm", ascending=False)

    # --- LỌC CHIẾN THUẬT V10 ---
    df_f = df_all[(df_all["Cứng(%)"] >= 23.5) & (df_all["An"].isin([1, 2, 3]))].copy()
    if len(df_f) > 9:
        df_f = df_f.sort_values("Điểm", ascending=False)
        idx_top = df_f.sort_values("Nén", ascending=False).head(5).index
        df_f = df_f.drop(index=idx_top)
        if len(df_f) > 4:
            idx_bot = df_f.sort_values("Nén", ascending=False).tail(4).index
            df_f = df_f.drop(index=idx_bot)
    st.session_state['df_strategy'] = df_f.sort_values("Điểm", ascending=False)

# --- 3. GIAO DIỆN ---
st.set_page_config(layout="wide")
st.title("🌐 MATRIX V10.2 - FULL OPTION & CHIẾN THUẬT")

if 'db' not in st.session_state: st.session_state['db'] = {}
if 'history' not in st.session_state: st.session_state['history'] = []

with st.sidebar:
    st.header("📂 HỆ THỐNG")
    if st.button("🚨 RESET ALL"):
        st.session_state.clear()
        st.rerun()

    up_json = st.file_uploader("📥 Nạp JSON", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json)
        st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', [])
        st.session_state['last_full_str'] = data.get('last_full_str', "")
        refresh_all_logic()
        st.success("Đã đồng bộ dữ liệu!")

    st.divider()
    st.header("📸 QUÉT KQ")
    up_img = st.file_uploader("Chọn ảnh kết quả", type=['jpg', 'jpeg', 'png'])
    if up_img and st.button("CHẠY OCR"):
        reader = load_ocr()
        results = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
        if nums:
            st.session_state['raw_input'] = ", ".join(nums)
            st.session_state['gdb_val'] = nums[0][-2:]
        st.rerun()

    st.session_state['raw_input'] = st.text_area("Dữ liệu 27 giải:", value=st.session_state.get('raw_input', ""), height=100)
    st.session_state['gdb_val'] = st.text_input("GĐB:", value=st.session_state.get('gdb_val', ""), max_chars=2)

    if st.button("🔥 PHÂN TÍCH KỲ MỚI"):
        raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
        if len(raw_list) >= 27:
            full_str_new = "".join(raw_list[:27])
            loto_list = [n[-2:] for n in raw_list[:27]]
            
            # Cập nhật điểm và nén cho từng dây dựa trên mapping cũ
            if st.session_state.get('last_full_str'):
                current_map = get_mapping_v10(st.session_state['last_full_str'])
                new_db = json.loads(json.dumps(st.session_state['db']))
                for wire_id, num_formed in current_map.items():
                    wire = new_db[wire_id]
                    if num_formed in loto_list:
                        wire["streak_loss"] = 0
                        wire["streak_win"] += 1
                        wire["history_hits"] += 1
                        # Thưởng phạt V9.8 logic
                        if num_formed == st.session_state['gdb_val']: wire["score"] += 2.0
                        wire["score"] += 1.5 if wire["streak_win"] < 4 else -0.5
                    else:
                        wire["streak_win"] = 0
                        wire["streak_loss"] += 1
                        if wire["streak_loss"] >= 5: wire["score"] += 0.1
                st.session_state['db'] = new_db
            
            st.session_state['last_full_str'] = full_str_new
            refresh_all_logic()
            st.rerun()

# --- 4. HIỂN THỊ CHÍNH ---
if st.session_state.get('df_all') is not None:
    c1, c2 = st.columns([1, 1])
    with c1:
        st.subheader("📊 TỔNG LỰC (CỘT DÂY)")
        st.dataframe(st.session_state['df_all'], use_container_width=True, height=600)
    with c2:
        st.subheader("🎯 BỘ LỌC CHIẾN THUẬT")
        df_s = st.session_state.get('df_strategy')
        if df_s is not None and not df_s.empty:
            st.dataframe(df_s, use_container_width=True)
        else:
            st.warning("⚠️ Không có quân nào thỏa mãn bộ lọc gắt này.")
        
        st.divider()
        st.subheader("📜 LỊCH SỬ")
        st.dataframe(pd.DataFrame(st.session_state['history']).head(10), use_container_width=True)
        
        if not st.session_state['df_all'].empty:
            st.download_button("💾 XUẤT JSON V10.2", data=json.dumps({"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state['last_full_str']}), file_name="matrix_v10_2.json")
