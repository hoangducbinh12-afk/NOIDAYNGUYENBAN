import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
from PIL import Image

# --- 1. KHỞI TẠO ---
TOTAL_POS = 107 

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'])

def get_mapping_v10(full_str):
    if not full_str or len(full_str) < TOTAL_POS: return None
    mapping = {str(i * TOTAL_POS + j): f"{full_str[i]}{full_str[j]}" for i in range(TOTAL_POS) for j in range(TOTAL_POS)}
    return mapping

def process_data_v108():
    if not st.session_state.get('last_full_str') or not st.session_state.get('db'): return
    current_map = get_mapping_v10(st.session_state['last_full_str'])
    db = st.session_state['db']
    history = st.session_state.get('history', [])
    total_periods = len(history)
    stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "max_gan": 0, "wire_count": 0, "total_hits": 0} for i in range(100)}
    for wire_id, num in current_map.items():
        wire = db.get(str(wire_id), {"score": 100.0, "streak_win": 0, "streak_loss": 0, "history_hits": 0})
        s = stats[num]; s["wire_count"] += 1; s["total_hits"] += wire.get("history_hits", 0)
        p_coef = 1.5 if wire.get("streak_win", 0) > 0 else 0.7
        s["total_score"] += (wire.get("score", 100.0) * p_coef)
        if wire.get("streak_win", 0) > s["max_an"]: s["max_an"] = wire.get("streak_win", 0)
        if wire.get("streak_loss", 0) > s["max_gan"]: s["max_gan"] = wire.get("streak_loss", 0)
    data_list = [{"Số": n, "Điểm": round(v["total_score"], 1), "An": v["max_an"], "Nén": v["max_gan"], "Dây": v["wire_count"], "Cứng(%)": round((v["total_hits"]/(v["wire_count"]*total_periods)*100),1) if total_periods>0 else 0} for n,v in stats.items()]
    st.session_state['df_raw'] = pd.DataFrame(data_list)

# --- 2. GIAO DIỆN ---
st.set_page_config(layout="wide", page_title="MATRIX V10.8")

if 'db' not in st.session_state: st.session_state['db'] = {}
if 'history' not in st.session_state: st.session_state['history'] = []

with st.sidebar:
    st.header("📂 KHỞI TẠO HỆ THỐNG")
    if st.button("🚨 RESET / LÀM MỚI TỪ ĐẦU"):
        st.session_state.clear()
        st.rerun()
    
    # Nút mới dành riêng cho mày
    if st.button("💎 KHỞI TẠO MA TRẬN TRỐNG"):
        st.session_state['db'] = {str(i): {"score": 100.0, "streak_win": 0, "streak_loss": 0, "history_hits": 0} for i in range(11449)}
        st.session_state['history'] = []
        st.session_state['last_full_str'] = "0" * 107 # Tạo chuỗi giả để giữ cấu trúc
        st.success("Đã tạo ma trận 11.449 dây trống! Giờ hãy quét kỳ 1.")

    up_json = st.file_uploader("📥 Hoặc nạp JSON cũ", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json)
        st.session_state['db'] = {str(k): v for k, v in data.get('matrix', data).items()}
        st.session_state['history'] = data.get('history', [])
        st.session_state['last_full_str'] = data.get('last_full_str', "")
        process_data_v108(); st.rerun()

    st.divider()
    st.header("🎛️ BỘ LỌC")
    f_an = st.slider("An:", 0, 10, (0, 3)) # Cho phép An từ 0
    f_gan = st.slider("Gan:", 0, 50, (0, 50))
    f_day = st.slider("Dây tối thiểu:", 0, 115, 0) # Mặc định 0 để thấy hết
    f_hard = st.slider("Cứng min (%):", 0.0, 40.0, 0.0, 0.5)

    st.divider()
    st.header("📸 QUÉT KẾT QUẢ")
    up_img = st.file_uploader("Chọn ảnh", type=['jpg', 'jpeg', 'png'])
    if up_img and st.button("CHẠY OCR"):
        reader = load_ocr()
        results = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
        if nums: st.session_state['raw_input'] = ", ".join(nums); st.session_state['gdb_val'] = nums[0][-2:]
        st.rerun()
    
    st.session_state['raw_input'] = st.text_area("Dữ liệu 27 giải:", value=st.session_state.get('raw_input', ""), height=80)
    st.session_state['gdb_val'] = st.text_input("GĐB:", value=st.session_state.get('gdb_val', ""), max_chars=2)
    
    if st.button("🔥 PHÂN TÍCH KỲ TIẾP THEO"):
        if not st.session_state.get('db'):
            st.error("Bấm 'KHỞI TẠO MA TRẬN TRỐNG' trước đã mày!")
        else:
            raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
            if len(raw_list) >= 27:
                full_str_new = "".join(raw_list[:27])
                loto_list = [n[-2:] for n in raw_list[:27]]
                # Logic ánh xạ và cập nhật matrix (V8.5 huyền thoại)
                curr_map = get_mapping_v10(st.session_state['last_full_str'])
                new_db = st.session_state['db'].copy()
                for i in range(11449):
                    wid = str(i); wire = new_db[wid]
                    num_f = curr_map.get(wid)
                    if num_f in loto_list:
                        wire["streak_loss"] = 0; wire["streak_win"] += 1; wire["history_hits"] += 1
                        if num_f == st.session_state['gdb_val']: wire["score"] += 2.0
                        wire["score"] += 1.5 if wire["streak_win"] < 4 else -0.5
                    else:
                        wire["streak_win"] = 0; wire["streak_loss"] += 1
                        if wire["streak_loss"] >= 5: wire["score"] += 0.1
                st.session_state['db'] = new_db
                st.session_state['history'].insert(0, {"STT": len(st.session_state['history'])+1, "GĐB": st.session_state['gdb_val']})
                st.session_state['last_full_str'] = full_str_new
                process_data_v108(); st.rerun()

# --- 3. HIỂN THỊ ---
if st.session_state.get('df_raw') is not None:
    df_all = st.session_state['df_raw'].sort_values("Điểm", ascending=False)
    df_f = df_all[(df_all["An"] >= f_an[0]) & (df_all["An"] <= f_an[1]) & (df_all["Nén"] >= f_gan[0]) & (df_all["Nén"] <= f_gan[1]) & (df_all["Dây"] >= f_day) & (df_all["Cứng(%)"] >= f_hard)].copy()
    
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1: st.metric("QUÂN LỌC", f"{len(df_f)} quân")
    with c2: st.code(", ".join(df_f.sort_values("Số")["Số"].tolist()) if not df_f.empty else "Dàn trống")
    with c3: st.download_button("💾 LƯU FILE .JSON", data=json.dumps({"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state['last_full_str']}), file_name="matrix_genesis.json")

    col_l, col_r = st.columns([1, 2.5])
    with col_l:
        st.subheader("🎯 CHI TIẾT LỌC")
        st.dataframe(df_f, use_container_width=True, height=400)
        with st.expander("📊 100 SỐ FULL"): st.dataframe(df_all, use_container_width=True)
    with col_r:
        st.subheader("📜 LỊCH SỬ ĐỐI SOÁT")
        st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True, height=800)
else:
    st.info("💡 Mày muốn chơi từ đầu? Bấm 'KHỞI TẠO MA TRẬN TRỐNG' ở bên trái, sau đó quét kỳ 1 nhé!")
