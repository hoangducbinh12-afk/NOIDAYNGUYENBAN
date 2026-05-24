import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
from PIL import Image

# --- 1. CẤU HÌNH HỆ THỐNG ---
TOTAL_POS = 107 
AVG_WIRES = 114.5
WINDOW = 10 

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'])

def get_mapping_v11(full_str):
    if not full_str or len(full_str) < TOTAL_POS: return None
    return {str(i * TOTAL_POS + j): f"{full_str[i]}{full_str[j]}" for i in range(TOTAL_POS) for j in range(TOTAL_POS)}

def process_data_v11_8():
    if not st.session_state.get('last_full_str') or not st.session_state.get('db'): return
    current_map = get_mapping_v11(st.session_state['last_full_str'])
    db = st.session_state['db']
    
    stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "max_gan": 0, "wire_count": 0, "window_hits": 0} for i in range(100)}
    for wire_id, num in current_map.items():
        wire = db.get(str(wire_id), {"score": 1000.0, "streak_win": 0, "streak_loss": 0, "hit_history": []})
        s = stats[num]
        s["wire_count"] += 1
        s["window_hits"] += sum(wire.get("hit_history", [])[-WINDOW:])
        s["total_score"] += wire.get("score", 1000.0) 
        if wire.get("streak_win", 0) > s["max_an"]: s["max_an"] = wire.get("streak_win", 0)
        if wire.get("streak_loss", 0) > s["max_gan"]: s["max_gan"] = wire.get("streak_loss", 0)

    data_list = []
    denominator = WINDOW * AVG_WIRES 
    for num, s in stats.items():
        do_cung_10 = s["window_hits"] / denominator if denominator > 0 else 0
        avg_score_db = s["total_score"] / s["wire_count"] if s["wire_count"] > 0 else 1000.0
        final_score = avg_score_db + (avg_score_db * do_cung_10)
        
        data_list.append({
            "Số": num, "Điểm": round(final_score, 2), "An": s["max_an"], 
            "Nén": s["max_gan"], "Dây": s["wire_count"], "Cứng(10k)": round(do_cung_10 * 100, 2)
        })
    # Lưu bảng gốc để audit rank
    st.session_state['df_raw'] = pd.DataFrame(data_list).sort_values("Điểm", ascending=False).reset_index(drop=True)

def audit_history(loto_list, gdb):
    if 'df_raw' not in st.session_state: return {"STT": len(st.session_state['history'])+1, "GĐB": gdb}
    df = st.session_state['df_raw']
    
    # TÍNH TOÁN RANK VÀ AN CHO GĐB
    gdb_info = gdb
    if gdb in df['Số'].values:
        row = df[df['Số'] == gdb]
        rank = row.index[0] + 1 # Lấy hạng (index + 1)
        max_an = row['An'].values[0]
        gdb_info = f"{gdb} (R{rank}-A{max_an})"
    
    res = {"STT": len(st.session_state['history'])+1, "GĐB": gdb_info}
    
    thresholds = [5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 70, 80, 90, 100]
    prev_t = 0
    for t in thresholds:
        label = f"T{t}"; subset = df.iloc[prev_t:t]
        found = [n for n in loto_list if n in subset['Số'].values]
        res[label] = f"{len(found)}({','.join(set(found))})" if len(found) > 0 else "0"
        prev_t = t
    return res

# --- GIAO DIỆN CHÍNH ---
st.set_page_config(layout="wide", page_title="Matrix Final V11.8")
st.markdown("<h1 style='text-align: center; color: red;'>Matrix Final V11.8</h1>", unsafe_allow_html=True)

if 'db' not in st.session_state: st.session_state['db'] = {}
if 'history' not in st.session_state: st.session_state['history'] = []

with st.sidebar:
    st.header("📂 HỆ THỐNG")
    if st.button("🚨 RESET ALL"): st.session_state.clear(); st.rerun()
    if st.button("💎 KHỞI TẠO 1000đ"):
        st.session_state['db'] = {str(i): {"score": 1000.0, "streak_win": 0, "streak_loss": 0, "hit_history": []} for i in range(11449)}
        st.session_state['history'] = []; st.session_state['last_full_str'] = "0" * 107; st.success("Đã khởi tạo!")

    up_json = st.file_uploader("📥 Nạp JSON", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json)
        st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', [])
        st.session_state['last_full_str'] = data.get('last_full_str', "")
        process_data_v11_8(); st.rerun()

    st.divider()
    st.header("🎛️ BỘ LỌC")
    f_an = st.slider("An:", 0, 20, (0, 3)); f_gan = st.slider("Gan:", 0, 100, (0, 100))
    f_day = st.slider("Dây min:", 0, 115, 20); f_hard = st.slider("Cứng (10k) %:", 0.0, 100.0, 15.0, 1.0)
    
    st.divider()
    st.header("📸 NHẬP KQ")
    up_img = st.file_uploader("Quét ảnh", type=['jpg', 'jpeg', 'png'])
    if up_img and st.button("CHẠY OCR"):
        reader = load_ocr(); results = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
        if nums: st.session_state['raw_input'] = ", ".join(nums); st.session_state['gdb_val'] = nums[0][-2:]
        st.rerun()
    st.session_state['raw_input'] = st.text_area("27 giải:", value=st.session_state.get('raw_input', ""), height=80)
    st.session_state['gdb_val'] = st.text_input("GĐB:", value=st.session_state.get('gdb_val', ""), max_chars=2)
    
    if st.button("🔥 PHÂN TÍCH KỲ MỚI"):
        if not st.session_state.get('db'): st.error("Nạp dữ liệu trước!")
        else:
            raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
            if len(raw_list) >= 27:
                loto_list = [n[-2:] for n in raw_list[:27]]; gdb_val = st.session_state['gdb_val']
                # PHẢI CHẠY AUDIT TRƯỚC KHI UPDATE DB MỚI
                st.session_state['history'].insert(0, audit_history(loto_list, gdb_val))
                
                curr_map = get_mapping_v11(st.session_state['last_full_str'])
                new_db = st.session_state['db'].copy()
                for i in range(11449):
                    wid = str(i); wire = new_db[wid]
                    num_f = curr_map.get(wid)
                    if num_f in loto_list:
                        n_hits = loto_list.count(num_f)
                        wire["score"] += (4.0 * n_hits) 
                        wire["streak_loss"] = 0; wire["streak_win"] += 1; wire["hit_history"].append(1)
                    else:
                        wire["score"] -= 1.0 
                        wire["streak_win"] = 0; wire["streak_loss"] += 1; wire["hit_history"].append(0)
                    wire["hit_history"] = wire["hit_history"][-WINDOW:]
                
                st.session_state['db'] = new_db; st.session_state['last_full_str'] = "".join(raw_list[:27])
                process_data_v11_8(); st.rerun()

# --- 3. HIỂN THỊ ---
if st.session_state.get('df_raw') is not None:
    df_all = st.session_state['df_raw']
    df_f = df_all[(df_all["An"] >= f_an[0]) & (df_all["An"] <= f_an[1]) & (df_all["Nén"] >= f_gan[0]) & (df_all["Nén"] <= f_gan[1]) & (df_all["Dây"] >= f_day) & (df_all["Cứng(10k)"] >= f_hard)].copy()
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1: st.metric("SỐ QUÂN LỌC", f"{len(df_f)} quân")
    with c2: st.code(", ".join(df_f.sort_values("Số")["Số"].tolist()) if not df_f.empty else "Trống")
    with c3: st.download_button("💾 XUẤT JSON V11.8", data=json.dumps({"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state['last_full_str']}), file_name="matrix_final_v11_8.json")
    st.divider()
    col_l, col_r = st.columns(
