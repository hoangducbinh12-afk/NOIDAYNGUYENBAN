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

def process_data_v12_7():
    if not st.session_state.get('last_full_str') or not st.session_state.get('db'): return
    current_map = get_mapping_v11(st.session_state['last_full_str'])
    db = st.session_state['db']
    
    # Khởi tạo stats để đo Min Gan (Sàn nén)
    stats = {f"{i:02d}": {"total_score": 0.0, "min_loss": 999, "wire_count": 0, "window_hits": 0} for i in range(100)}
    
    for wire_id, num in current_map.items():
        wire = db.get(str(wire_id), {"score": 1000.0, "streak_win": 0, "streak_loss": 0, "hit_history": []})
        
        # LOẠI TRỪ DÂY VỪA NỔ (Chỉ lấy dây sạch để tính điểm ánh xạ)
        if wire.get("streak_win", 0) > 0:
            continue 
            
        s = stats[num]
        s["wire_count"] += 1
        s["window_hits"] += sum(wire.get("hit_history", [])[-WINDOW:])
        s["total_score"] += wire.get("score", 1000.0) 
        
        curr_loss = wire.get("streak_loss", 0)
        if curr_loss < s["min_loss"]:
            s["min_loss"] = curr_loss

    data_list = []
    denominator = WINDOW * AVG_WIRES 
    for num, s in stats.items():
        if s["wire_count"] == 0: continue 
        
        do_cung_10 = s["window_hits"] / denominator if denominator > 0 else 0
        avg_score_db = s["total_score"] / s["wire_count"]
        final_score = avg_score_db + (avg_score_db * do_cung_10)
        
        data_list.append({
            "Số": num, 
            "Điểm": round(final_score, 2), 
            "MinGan": s["min_loss"] if s["min_loss"] != 999 else 0,
            "DâySạch": s["wire_count"], 
            "Cứng(10k)": round(do_cung_10 * 100, 2)
        })
    # Sắp xếp để tính Rank
    df_raw = pd.DataFrame(data_list).sort_values("Điểm", ascending=False).reset_index(drop=True)
    df_raw["Rank"] = df_raw.index + 1
    st.session_state['df_raw'] = df_raw

def audit_history(loto_list, gdb):
    if 'df_raw' not in st.session_state: return None
    df = st.session_state['df_raw']
    
    gdb_info = gdb
    if gdb in df['Số'].values:
        row = df[df['Số'] == gdb]
        rank = row['Rank'].values[0]
        m_gan = row['MinGan'].values[0]
        gdb_info = f"{gdb} (R{rank}-mG{m_gan})"
    
    res = {"STT": len(st.session_state['history'])+1, "GĐB": gdb_info}
    thresholds = [5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100]
    prev_t = 0
    for t in thresholds:
        label = f"T{t}"; subset = df.iloc[prev_t:t]
        found = [n for n in loto_list if n in subset['Số'].values]
        res[label] = f"{len(found)}({','.join(set(found))})" if len(found) > 0 else "0"
        prev_t = t
    return res

# --- GIAO DIỆN CHÍNH ---
st.set_page_config(layout="wide", page_title="Matrix Final V12.7 Full")
st.markdown("<h1 style='text-align: center; color: red;'>Matrix Final V12.7</h1>", unsafe_allow_html=True)

if 'db' not in st.session_state: st.session_state['db'] = {}
if 'history' not in st.session_state: st.session_state['history'] = []

with st.sidebar:
    st.header("📂 HỆ THỐNG")
    col_r1, col_r2 = st.columns(2)
    with col_r1: 
        if st.button("🚨 RESET ALL"): st.session_state.clear(); st.rerun()
    with col_r2:
        if st.button("💎 KHỞI TẠO"):
            st.session_state['db'] = {str(i): {"score": 1000.0, "streak_win": 0, "streak_loss": 0, "hit_history": []} for i in range(11449)}
            st.session_state['history'] = []; st.session_state['last_full_str'] = "0" * 107; st.success("OK!")

    up_json = st.file_uploader("📥 Nạp dữ liệu JSON", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json)
        st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', [])
        st.session_state['last_full_str'] = data.get('last_full_str', "")
        process_data_v12_7(); st.rerun()

    st.divider()
    st.header("🎛️ BỘ LỌC CHIẾN THUẬT")
    f_rank = st.slider("Hạng (Rank):", 1, 100, (1, 15))
    f_min_gan = st.slider("Min Gan (Sàn trượt):", 0, 50, (1, 15))
    f_day = st.slider("Dây Sạch tối thiểu:", 0, 115, 20)
    f_hard = st.slider("Độ cứng phong độ %:", 0.0, 100.0, 10.0, 1.0)
    
    st.divider()
    st.header("📸 NHẬP KẾT QUẢ")
    # NÚT LOAD ẢNH ĐÃ QUAY TRỞ LẠI
    up_img = st.file_uploader("Quét ảnh kết quả", type=['jpg', 'jpeg', 'png'])
    if up_img and st.button("🚀 CHẠY OCR"):
        with st.spinner("Đang đọc ảnh..."):
            reader = load_ocr()
            results = reader.readtext(np.array(Image.open(up_img)), detail=0)
            nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
            if nums:
                st.session_state['raw_input'] = ", ".join(nums)
                st.session_state['gdb_val'] = nums[0][-2:]
                st.success("Đã nhận diện xong!")
                st.rerun()

    st.session_state['raw_input'] = st.text_area("27 giải loto:", value=st.session_state.get('raw_input', ""), height=80)
    st.session_state['gdb_val'] = st.text_input("GĐB (2 số cuối):", value=st.session_state.get('gdb_val', ""), max_chars=2)
    
    if st.button("🔥 PHÂN TÍCH KỲ MỚI"):
        if not st.session_state.get('db'): st.error("Chưa có dữ liệu!")
        else:
            raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
            if len(raw_list) >= 27:
                loto_list = [n[-2:] for n in raw_list[:27]]; gdb_val = st.session_state['gdb_val']
                # Ghi lịch sử trước khi cập nhật dây
                new_entry = audit_history(loto_list, gdb_val)
                if new_entry:
                    if not st.session_state['history'] or new_entry['GĐB'] != st.session_state['history'][0]['GĐB']:
                        st.session_state['history'].insert(0, new_entry)
                
                curr_map = get_mapping_v11(st.session_state['last_full_str'])
                new_db = st.session_state['db'].copy()
                # CẬP NHẬT 11.449 DÂY (Hệ số giữ nguyên như mày yêu cầu)
                for i in range(11449):
                    wid = str(i); wire = new_db[wid]
                    num_f = curr_map.get(wid)
                    if "hit_history" not in wire: wire["hit_history"] = []
                    
                    if num_f in loto_list:
                        n_hits = loto_list.count(num_f)
                        s_win = wire.get("streak_win", 0) + 1
                        if s_win == 1: wire["score"] += (4.0 * n_hits)
                        elif s_win == 2: wire["score"] += (3.0 * n_hits)
                        elif s_win == 3: wire["score"] += (2.0 * n_hits)
                        elif s_win == 4: wire["score"] += (1.0 * n_hits)
                        elif 5 <= s_win <= 10: wire["score"] += (0.5 * n_hits)
                        wire["streak_loss"] = 0; wire["streak_win"] = s_win; wire["hit_history"].append(1)
                    else:
                        s_loss = wire.get("streak_loss", 0) + 1
                        if 1 <= s_loss <= 4: wire["score"] -= 1.5
                        elif 5 <= s_loss <= 10: wire["score"] -= 0.5
                        wire["streak_win"] = 0; wire["streak_loss"] = s_loss; wire["hit_history"].append(0)
                    wire["hit_history"] = wire["hit_history"][-WINDOW:]
                
                st.session_state['db'] = new_db
                st.session_state['last_full_str'] = "".join(raw_list[:27])
                process_data_v12_7(); st.rerun()

# --- 3. HIỂN THỊ KẾT QUẢ ---
if st.session_state.get('df_raw') is not None:
    df_all = st.session_state['df_raw']
    # Áp dụng bộ lọc 4 biến
    df_f = df_all[
        (df_all["Rank"] >= f_rank[0]) & (df_all["Rank"] <= f_rank[1]) &
        (df_all["MinGan"] >= f_min_gan[0]) & (df_all["MinGan"] <= f_min_gan[1]) &
        (df_all["DâySạch"] >= f_day) &
        (df_all["Cứng(10k)"] >= f_hard)
    ].copy()
    
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1: st.metric("SỐ QUÂN LỌC", f"{len(df_f)} quân")
    with c2: st.code(", ".join(df_f.sort_values("Số")["Số"].tolist()) if not df_f.empty else "Dàn trống")
    with c3: st.download_button("💾 XUẤT JSON V12.7", data=json.dumps({"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state['last_full_str']}), file_name="matrix_v12_7.json")
    
    st.divider()
    col_l, col_r = st.columns([1.2, 2.5])
    with col_l:
        st.subheader("🎯 CHI TIẾT BẢNG LỌC")
        st.dataframe(df_f, use_container_width=True, height=500, hide_index=True)
        with st.expander("📊 XEM BẢNG FULL (100 SỐ)"):
            st.dataframe(df_all, use_container_width=True)
    with col_r:
        st.subheader("📜 TRUY VẾT LỊCH SỬ (Rank-MinGan)")
        st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True, height=800)
