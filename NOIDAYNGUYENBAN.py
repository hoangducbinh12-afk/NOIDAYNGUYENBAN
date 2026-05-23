import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
from PIL import Image

# --- 1. KHỞI TẠO HỆ THỐNG MAPPING ĐỘNG ---
TOTAL_POS = 107 # Tổng các vị trí số trong 27 giải (GĐB: 5, G1: 5...)
# Để tạo ra 11.449 dây, ta dùng 107 vị trí kết hợp chéo (107 * 107 = 11.449)

if 'db' not in st.session_state:
    # Lưu trữ theo ID DÂY (Cố định)
    st.session_state['db'] = {str(i): {"score": 100.0, "streak_win": 0, "streak_loss": 0, "history_hits": 0} for i in range(TOTAL_POS * TOTAL_POS)}
if 'history' not in st.session_state: st.session_state['history'] = []
if 'last_full_result' not in st.session_state: st.session_state['last_full_result'] = None

# --- HÀM LẤY GIÁ TRỊ TẠI VỊ TRÍ (0-106) ---
def get_val_at_pos(full_result_str, pos_id):
    # full_result_str là chuỗi dính liền của 27 giải (ví dụ: 1234567890...)
    if not full_result_str or pos_id >= len(full_result_str): return 0
    return int(full_result_str[pos_id])

# --- HÀM TÍNH TOÀN BỘ MAPPING CỦA KỲ HIỆN TẠI ---
def get_current_mapping(full_result_str):
    mapping = {} # {wire_id: num_formed}
    for i in range(TOTAL_POS):
        for j in range(TOTAL_POS):
            wire_id = i * TOTAL_POS + j
            val_i = get_val_at_pos(full_result_str, i)
            val_j = get_val_at_pos(full_result_str, j)
            num_formed = f"{val_i}{val_j}"
            mapping[str(wire_id)] = num_formed
    return mapping

# --- THUẬT TOÁN V9: CẬP NHẬT THEO ID DÂY ---
def update_matrix_v9(full_result_list, gdb_loto):
    # Chuyển list 27 giải thành chuỗi số dính liền để lấy tọa độ
    full_str = "".join(full_result_list)
    loto_list = [n[-2:] for n in full_result_list]
    
    db = st.session_state['db']
    new_db = json.loads(json.dumps(db))
    current_map = get_current_mapping(full_str)
    
    for wire_id, num_formed in current_map.items():
        wire = new_db[wire_id]
        is_hit = num_formed in loto_list
        is_gdb = (num_formed == gdb_loto)

        if is_hit:
            wire["streak_loss"] = 0
            wire["streak_win"] += 1
            wire["history_hits"] += 1
            if is_gdb: wire["score"] += 2.0
            wire["score"] += float(loto_list.count(num_formed)) * 2.0 if wire["streak_win"] < 4 else -0.5
        else:
            wire["streak_win"] = 0
            wire["streak_loss"] += 1
            if wire["streak_loss"] >= 4: wire["score"] += 0.1

    st.session_state['db'] = new_db
    st.session_state['last_full_result'] = full_str

# --- HÀM TỔNG HỢP HIỂN THỊ (DYNAMIC) ---
def get_display_data_v9():
    if not st.session_state['last_full_result']: return None
    
    # Lấy mapping của kỳ CUỐI CÙNG để biết dây đang trỏ về số nào cho kỳ TIẾP THEO
    current_map = get_current_mapping(st.session_state['last_full_result'])
    db = st.session_state['db']
    total_periods = len(st.session_state['history'])
    
    num_power = {f"{i:02d}": 0.0 for i in range(100)}
    num_hardness = {f"{i:02d}": {"sum": 0.0, "count": 0} for i in range(100)}
    num_compression = {f"{i:02d}": 0 for i in range(100)}

    for wire_id, num_formed in current_map.items():
        wire = db[wire_id]
        
        # Điểm và Nén theo trạng thái của DÂY đang trỏ về số đó
        p_coef = 1.5 if wire["streak_win"] > 0 else 0.7
        num_power[num_formed] += (wire["score"] * p_coef)
        
        if wire["streak_loss"] > num_compression[num_formed]:
            num_compression[num_formed] = wire["streak_loss"]
            
        eff = (wire["history_hits"] / total_periods * 100) if total_periods > 0 else 0
        num_hardness[num_formed]["sum"] += eff
        num_hardness[num_formed]["count"] += 1

    # Trả về dataframe
    results = []
    for i in range(100):
        n = f"{i:02d}"
        hrd = num_hardness[n]["sum"] / num_hardness[n]["count"] if num_hardness[n]["count"] > 0 else 0
        results.append({"Số": n, "Điểm": num_power[n], "Cứng(%)": round(hrd, 1), "Nén": num_compression[n]})
    
    return pd.DataFrame(results)

# --- 2. GIAO DIỆN ---
st.set_page_config(page_title="Matrix V9 - Dynamic Mapping", layout="wide")
st.markdown("<h2 style='text-align: center; color: #00FFFF;'>🌐 MATRIX V9 - ÁNH XẠ ĐỘNG 11.449</h2>", unsafe_allow_html=True)

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
        # Lưu ý: Cần có full_result cuối cùng để mapping, nếu file cũ không có sẽ mặc định
        st.rerun()

    st.divider()
    st.session_state['raw_input'] = st.text_area("Nhập 27 giải (dạng số dính hoặc cách nhau):", value=st.session_state.get('raw_input', ""), height=150)
    st.session_state['gdb_val'] = st.text_input("GĐB (2 số cuối):", value=st.session_state.get('gdb_val', ""), max_chars=2)

    if st.button("🔥 PHÂN TÍCH ÁNH XẠ"):
        # Xử lý input thành list 27 giải
        raw_data = st.session_state['raw_input'].replace(",", " ").split()
        if len(raw_data) >= 27:
            full_list = raw_data[:27]
            
            # Đối soát (Lấy data trước khi update)
            df_old = get_display_data_v9()
            if df_old is not None:
                df_old = df_old.sort_values('Điểm', ascending=False).reset_index(drop=True)
            
            # Cập nhật
            update_matrix_v9(full_list, st.session_state['gdb_val'])
            
            # Ghi lịch sử (Nếu có bảng đối soát)
            if df_old is not None:
                slices = {"T5": (0,5), "T10": (5,10), "T20": (10,20), "Cao": (95,100)}
                def get_hit(targets, res_loto):
                    hits = [n for n in targets if n in res_loto]
                    return f"{len(hits)}({','.join(hits)})" if hits else "0"
                
                v_loto = [n[-2:] for n in full_list]
                entry = {"STT": len(st.session_state['history'])+1, "GĐB": st.session_state['gdb_val']}
                for k, (s, e) in slices.items():
                    entry[k] = get_hit(df_old.iloc[s:e]['Số'].tolist(), v_loto)
                st.session_state['history'].insert(0, entry)
            
            st.rerun()

# --- 3. HIỂN THỊ ---
df_display = get_display_data_v9()
if df_display is not None:
    c1, c2 = st.columns([1.5, 3.5])
    with c1:
        st.subheader("📊 TỔNG LỰC ĐỘNG")
        top_scores = sorted(df_display['Điểm'].unique(), reverse=True)[:3]
        def set_icon(row):
            if row['Nén'] > 15: return "🧨"
            if row['Điểm'] in top_3_scores: return "🚀"
            return "✅"
        # Sắp xếp theo điểm
        df_sorted = df_display.sort_values('Điểm', ascending=False).reset_index(drop=True)
        st.dataframe(df_sorted, use_container_width=True, height=600)

    with c2:
        st.subheader("📜 LỊCH SỬ")
        st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True)
        st.divider()
        st.download_button("💾 XUẤT JSON", data=json.dumps({"matrix": st.session_state['db'], "history": st.session_state['history']}), file_name="matrix_v9.json")
