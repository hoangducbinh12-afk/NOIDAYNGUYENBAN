import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
from PIL import Image

# --- 1. KHỞI TẠO HỆ THỐNG ---
BIT_COUNT = 107
TOTAL_WIRES = BIT_COUNT * BIT_COUNT 
DEFAULT_SCORE = 100.0

if 'db' not in st.session_state:
    st.session_state['db'] = {str(i): {"score": DEFAULT_SCORE, "streak_win": 0, "streak_loss": 0} for i in range(TOTAL_WIRES)}
if 'raw_input' not in st.session_state: st.session_state['raw_input'] = ""
if 'gdb_val' not in st.session_state: st.session_state['gdb_val'] = ""
if 'final_scores' not in st.session_state: st.session_state['final_scores'] = None
if 'v_loto' not in st.session_state: st.session_state['v_loto'] = []
if 'history' not in st.session_state: st.session_state['history'] = []
if 'last_rank_info' not in st.session_state: st.session_state['last_rank_info'] = ""

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'])
reader = load_ocr()

def update_matrix(db, loto_list, gdb_loto):
    actual_db = db.get('matrix', db) if isinstance(db.get('matrix'), dict) else db
    new_matrix = json.loads(json.dumps(actual_db))
    num_scores = {f"{i:02d}": 0.0 for i in range(100)}
    for wire_id in range(TOTAL_WIRES):
        w_str = str(wire_id); wire = new_matrix[w_str]
        num_formed = f"{wire_id % 100:02d}"
        is_hit = num_formed in loto_list; is_gdb = (num_formed == gdb_loto)
        if is_hit:
            wire["streak_loss"] = 0; wire["streak_win"] += 1
            if wire["streak_win"] <= 3:
                if is_gdb: wire["score"] += 5.0
                wire["score"] += float(loto_list.count(num_formed))
            else: wire["score"] -= 0.5
        else:
            wire["streak_win"] = 0; wire["streak_loss"] += 1
            if wire["streak_loss"] >= 4: wire["score"] += 0.5
        num_scores[num_formed] += wire["score"]
    return new_matrix, num_scores

# --- 2. GIAO DIỆN ---
st.set_page_config(page_title="Matrix 11.449", layout="wide")
st.title("⚡ MATRIX 11.449 - HỆ THỐNG ĐỐI SOÁT CHUẨN")

with st.sidebar:
    st.header("📂 DỮ LIỆU ĐẦU VÀO")
    
    # NẠP FILE JSON
    load_file = st.file_uploader("📥 Nạp dữ liệu cũ (.json)", type=['json'])
    if load_file is not None:
        if st.button("XÁC NHẬN NẠP FILE"):
            try:
                data = json.load(load_file)
                st.session_state['db'] = data.get('matrix', data)
                st.session_state['gdb_val'] = data.get('last_gdb', "")
                st.session_state['history'] = data.get('history', [])
                st.success(f"Đã nạp thành công!")
            except: st.error("Lỗi cấu trúc file!")

    # NÚT RESET - ĐÃ QUAY TRỞ LẠI
    st.divider()
    if st.button("🚨 RESET MỚI HOÀN TOÀN"):
        for key in st.session_state.keys():
            del st.session_state[key]
        st.rerun()

    st.divider()
    uploaded_img = st.file_uploader("📸 Quét ảnh kết quả", type=['jpg', 'jpeg', 'png'])
    if uploaded_img and st.button("BẮT ĐẦU QUÉT OCR"):
        results = reader.readtext(np.array(Image.open(uploaded_img)), detail=0)
        nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
        if nums:
            st.session_state['raw_input'] = ", ".join(nums)
            st.session_state['gdb_val'] = nums[0][-2:]
        st.rerun()

    st.session_state['raw_input'] = st.text_area("27 giải:", value=st.session_state['raw_input'], height=100)
    st.session_state['gdb_val'] = st.text_input("GĐB Kỳ Này:", value=st.session_state['gdb_val'], max_chars=2)

    if st.button("🔥 CHẠY MA TRẬN & LƯU"):
        raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
        v_loto = [n[-2:] for n in raw_list[:27]]
        st.session_state['v_loto'] = v_loto
        
        # LẤY BẢNG ĐIỂM CŨ ĐỂ SOI HẠNG (RANK)
        if st.session_state['final_scores'] is not None:
            old_scores = st.session_state['final_scores']
        else:
            old_scores = {f"{i:02d}": sum(st.session_state['db'][str(j)]["score"] for j in range(TOTAL_WIRES) if j % 100 == i) for i in range(100)}

        old_df = pd.DataFrame(list(old_scores.items()), columns=['Số', 'Điểm']).sort_values(by='Điểm', ascending=False).reset_index(drop=True)
        
        # Tìm hạng GĐB
        try:
            rank_val = old_df[old_df['Số'] == st.session_state['gdb_val']].index[0]
            st.session_state['last_rank_info'] = f"GĐB {st.session_state['gdb_val']} nằm ở hạng {rank_val} kỳ trước."
        except: rank_val = "-"; st.session_state['last_rank_info'] = ""

        # CẬP NHẬT ĐIỂM
        new_matrix, scores = update_matrix(st.session_state['db'], v_loto, st.session_state['gdb_val'])
        st.session_state['db'] = new_matrix
        st.session_state['final_scores'] = scores
        
        # Đếm nháy theo dàn kỳ trước
        def get_hit_info(target_nums, result_list):
            hits = [n for n in target_nums if n in result_list]
            nhay = sum([result_list.count(n) for n in hits])
            no = sorted(list(set(hits)))
            return f"{nhay} ({','.join(no)})" if nhay > 0 else "0"

        res = {
            "STT": len(st.session_state['history']) + 1,
            "GĐB": st.session_state['gdb_val'],
            "Hạng": rank_val,
            "Top 10": get_hit_info(old_df.head(10)['Số'].tolist(), v_loto),
            "10 Nhì": get_hit_info(old_df.iloc[10:20]['Số'].tolist(), v_loto),
            "7 Ba": get_hit_info(old_df.iloc[20:27]['Số'].tolist(), v_loto),
            "20 Né": get_hit_info(old_df.tail(20)['Số'].tolist(), v_loto)
        }
        st.session_state['history'].append(res)

# --- 3. HIỂN THỊ ---
if st.session_state['final_scores']:
    c_left, c_right = st.columns([1, 2])
    with c_left:
        st.subheader("📊 BẢNG 100 SỐ")
        df_display = pd.DataFrame(list(st.session_state['final_scores'].items()), columns=['Số', 'Điểm'])
        df_display['TT'] = df_display['Số'].apply(lambda x: "🔥" if x in st.session_state['v_loto'] else "⏳")
        df_display = df_display.sort_values(by='Điểm', ascending=False).reset_index(drop=True)
        st.dataframe(df_display, use_container_width=True, height=450)

    with c_right:
        st.subheader("📜 LỊCH SỬ ĐỐI SOÁT")
        if st.session_state['last_rank_info']: st.warning(st.session_state['last_rank_info'])
        st.table(pd.DataFrame(st.session_state['history']))
        
        st.divider()
        st.subheader("🎯 TRÍCH XUẤT QUÂN")
        num_pick = st.number_input("Số lượng:", 1, 100, 10)
        st.code(", ".join(df_display.head(num_pick)['Số'].tolist()))
        
        save_data = {"matrix": st.session_state['db'], "last_gdb": st.session_state['gdb_val'], "history": st.session_state['history']}
        st.download_button("💾 XUẤT JSON", data=json.dumps(save_data), file_name="matrix_final.json")
