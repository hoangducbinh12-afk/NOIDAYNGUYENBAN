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

def get_mapping_v11(full_str):
    if not full_str or len(full_str) < TOTAL_POS: return None
    return {str(i * TOTAL_POS + j): f"{full_str[i]}{full_str[j]}" for i in range(TOTAL_POS) for j in range(TOTAL_POS)}

def process_data_v11():
    if not st.session_state.get('last_full_str') or not st.session_state.get('db'): return
    current_map = get_mapping_v11(st.session_state['last_full_str'])
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

    data_list = []
    for num, s in stats.items():
        hardness = (s["total_hits"] / (s["wire_count"] * total_periods) * 100) if (total_periods > 0 and s["wire_count"] > 0) else 0
        data_list.append({"Số": num, "Điểm": round(s["total_score"], 1), "An": s["max_an"], "Nén": s["max_gan"], "Dây": s["wire_count"], "Cứng(%)": round(hardness, 1)})
    st.session_state['df_raw'] = pd.DataFrame(data_list).sort_values("Điểm", ascending=False).reset_index(drop=True)

def audit_history(loto_list, gdb):
    if 'df_raw' not in st.session_state: return {"STT": len(st.session_state['history'])+1, "GĐB": gdb}
    df = st.session_state['df_raw']
    res = {"STT": len(st.session_state['history'])+1, "GĐB": gdb}
    thresholds = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 95, 100]
    prev_t = 0
    for t in thresholds:
        label = f"T{t}" if t < 100 else "Cao"
        subset = df.iloc[prev_t:t]
        found = [n for n in loto_list if n in subset['Số'].values]
        res[label] = f"{len(found)}({','.join(set(found))})" if len(found) > 0 else "0"
        prev_t = t
    return res

# --- 2. GIAO DIỆN ---
st.set_page_config(layout="wide", page_title="Matrix Final")

# Tiêu đề chữ Đỏ
st.markdown("<h1 style='text-align: center; color: red;'>Matrix Final</h1>", unsafe_allow_html=True)

if 'db' not in st.session_state: st.session_state['db'] = {}
if 'history' not in st.session_state: st.session_state['history'] = []

with st.sidebar:
    st.header("📂 HỆ THỐNG")
    if st.button("🚨 RESET ALL"): st.session_state.clear(); st.rerun()
    if st.button("💎 KHỞI TẠO TRỐNG"):
        st.session_state['db'] = {str(i): {"score": 100.0, "streak_win": 0, "streak_loss": 0, "history_hits": 0} for i in range(11449)}
        st.session_state['history'] = []; st.session_state['last_full_str'] = "0" * 107; st.success("Đã tạo trống!")

    up_json = st.file_uploader("📥 Nạp JSON", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json)
        st.session_state['db'] = {str(k): v for k, v in data.get('matrix', data).items()}
        st.session_state['history'] = data.get('history', [])
        st.session_state['last_full_str'] = data.get('last_full_str', "")
        process_data_v11(); st.rerun()

    st.divider()
    st.header("🎛️ BỘ LỌC BIÊN ĐỘ")
    f_an = st.slider("Khoảng Ăn (An):", 0, 20, (0, 3)) # Nới lên 20
    f_gan = st.slider("Khoảng Nén (Gan):", 0, 100, (0, 100)) # Nới lên 100
    f_day = st.slider("Dây tối thiểu:", 0, 115, 20)
    f_hard = st.slider("Độ cứng min (%):", 0.0, 40.0, 23.5, 0.5)
    
    st.divider()
    st.header("📸 QUÉT KQ")
    up_img = st.file_uploader("Chọn ảnh", type=['jpg', 'jpeg', 'png'])
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
            full_str_new = "".join(raw_list[:27]); loto_list = [n[-2:] for n in raw_list[:27]]; gdb_val = st.session_state['gdb_val']
            history_entry = audit_history(loto_list, gdb_val)
            st.session_state['history'].insert(0, history_entry)
            curr_map = get_mapping_v11(st.session_state['last_full_str'])
            new_db = st.session_state['db'].copy()
            for i in range(11449):
                wid = str(i); wire = new_db[wid]
                num_f = curr_map.get(wid)
                if num_f in loto_list:
                    wire["streak_loss"] = 0; wire["streak_win"] += 1; wire["history_hits"] += 1
                    if num_f == gdb_val: wire["score"] += 2.0
                    wire["score"] += 1.5 if wire["streak_win"] < 4 else -0.5
                else:
                    wire["streak_win"] = 0; wire["streak_loss"] += 1
                    if wire["streak_loss"] >= 5: wire["score"] += 0.1
            st.session_state['db'] = new_db; st.session_state['last_full_str'] = full_str_new
            process_data_v11(); st.rerun()

# --- 3. HIỂN THỊ ---
if st.session_state.get('df_raw') is not None:
    df_all = st.session_state['df_raw']
    df_f = df_all[(df_all["An"] >= f_an[0]) & (df_all["An"] <= f_an[1]) & (df_all["Nén"] >= f_gan[0]) & (df_all["Nén"] <= f_gan[1]) & (df_all["Dây"] >= f_day) & (df_all["Cứng(%)"] >= f_hard)].copy()
    
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1: st.metric("QUÂN LỌC", f"{len(df_f)} quân")
    with c2: st.code(", ".join(df_f.sort_values("Số")["Số"].tolist()) if not df_f.empty else "Dàn trống")
    with c3: st.download_button("💾 XUẤT JSON", data=json.dumps({"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state['last_full_str']}), file_name="matrix_final.json")

    col_l, col_r = st.columns([1, 2.5])
    with col_l:
        st.subheader("🎯 CHI TIẾT LỌC")
        st.dataframe(df_f, use_container_width=True, height=400)
        with st.expander("📊 100 SỐ FULL"): st.dataframe(df_all, use_container_width=True)
    with col_r:
        st.subheader("📜 LỊCH SỬ ĐỐI SOÁT FULL")
        st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True, height=800)
