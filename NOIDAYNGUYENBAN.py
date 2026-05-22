import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
from PIL import Image

# --- 1. KHỞI TẠO HỆ THỐNG ---
TOTAL_POS = 107
TOTAL_WIRES = TOTAL_POS * TOTAL_POS
DEFAULT_SCORE = 100.0

# Khởi tạo session_state nếu chưa có
if 'db' not in st.session_state:
    st.session_state['db'] = {str(i): {"score": DEFAULT_SCORE, "streak_win": 0, "streak_loss": 0} for i in range(TOTAL_WIRES)}
if 'history' not in st.session_state: st.session_state['history'] = []
if 'final_scores' not in st.session_state: st.session_state['final_scores'] = None
if 'hardness' not in st.session_state: st.session_state['hardness'] = None
if 'compression' not in st.session_state: st.session_state['compression'] = None

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'])

# --- THUẬT TOÁN V8.3: CẬP NHẬT ĐIỂM & NÉN ---
def update_matrix_v8_3(db, loto_list, gdb_loto):
    # Đảm bảo lấy đúng cấu trúc ma trận
    actual_db = db.get('matrix', db) if isinstance(db.get('matrix'), dict) else db
    new_matrix = json.loads(json.dumps(actual_db))
    
    num_power = {f"{i:02d}": 0.0 for i in range(100)}
    wire_quality_count = {f"{i:02d}": {"good": 0, "total": 0} for i in range(100)}
    max_compression = {f"{i:02d}": 0 for i in range(100)}

    for wire_id in range(TOTAL_WIRES):
        w_str = str(wire_id)
        # Nếu nạp file cũ thiếu id, tự tạo mới
        if w_str not in new_matrix:
            new_matrix[w_str] = {"score": DEFAULT_SCORE, "streak_win": 0, "streak_loss": 0}
            
        wire = new_matrix[w_str]
        num_formed = f"{wire_id % 100:02d}"
        
        is_hit = num_formed in loto_list
        is_gdb = (num_formed == gdb_loto)

        if is_hit:
            wire["streak_loss"] = 0
            wire["streak_win"] += 1
            if is_gdb: wire["score"] += 2.0
            if wire["streak_win"] < 4:
                wire["score"] += float(loto_list.count(num_formed)) * 2.0
            else:
                wire["score"] -= 0.5
        else:
            wire["streak_win"] = 0
            wire["streak_loss"] += 1
            if wire["streak_loss"] >= 4:
                wire["score"] += 0.1

        # Độ cứng (Tốt nếu đang nổ hoặc trượt ngắn < 7)
        is_good = (wire["streak_win"] > 0 or wire["streak_loss"] < 7)
        
        if wire["streak_loss"] > max_compression[num_formed]:
            max_compression[num_formed] = wire["streak_loss"]

        # Hệ số uy tín thuận dòng
        p_coef = 1.5 if 0 < wire["streak_win"] < 4 else 0.7
        num_power[num_formed] += (wire["score"] * p_coef)
        
        wire_quality_count[num_formed]["total"] += 1
        if is_good: wire_quality_count[num_formed]["good"] += 1

    hardness_map = {n: (q["good"]/q["total"]*100) for n, q in wire_quality_count.items()}
    return new_matrix, num_power, hardness_map, max_compression

# --- 2. GIAO DIỆN ---
st.set_page_config(page_title="Matrix V8.3 Pro", layout="wide")
st.markdown("<h2 style='text-align: center; color: #00FF00;'>📈 MATRIX V8.3 - FULL OPTION</h2>", unsafe_allow_html=True)

with st.sidebar:
    st.header("📂 DỮ LIỆU HỆ THỐNG")
    
    # Nạp dữ liệu JSON (Sửa lỗi nạp không được)
    uploaded_file = st.file_uploader("📥 Nạp JSON dữ liệu", type=['json'])
    if uploaded_file is not None:
        if st.button("XÁC NHẬN NẠP FILE"):
            try:
                data = json.load(uploaded_file)
                # Tương thích cả file chỉ có ma trận hoặc file full
                st.session_state['db'] = data.get('matrix', data)
                st.session_state['history'] = data.get('history', [])
                st.session_state['final_scores'] = None # Reset để tính lại theo data mới
                st.success("Nạp dữ liệu thành công!")
                st.rerun()
            except Exception as e:
                st.error(f"Lỗi nạp file: {e}")

    if st.button("🚨 RESET MỚI HOÀN TOÀN"):
        st.session_state.clear()
        st.rerun()

    st.divider()
    st.header("📸 NHẬP KẾT QUẢ")
    
    # Trả lại ô load ảnh OCR
    uploaded_img = st.file_uploader("Quét ảnh kết quả", type=['jpg', 'jpeg', 'png'])
    if uploaded_img:
        if st.button("BẮT ĐẦU OCR"):
            with st.spinner("Đang quét ảnh..."):
                reader = load_ocr()
                results = reader.readtext(np.array(Image.open(uploaded_img)), detail=0)
                nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
                if nums:
                    st.session_state['raw_input'] = ", ".join(nums)
                    st.session_state['gdb_val'] = nums[0][-2:]
            st.rerun()

    st.session_state['raw_input'] = st.text_area("27 giải:", value=st.session_state.get('raw_input', ""), height=100)
    st.session_state['gdb_val'] = st.text_input("GĐB:", value=st.session_state.get('gdb_val', ""), max_chars=2)

    if st.button("🔥 PHÂN TÍCH KỲ MỚI"):
        raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
        if len(raw_list) < 27:
            st.error("Chưa đủ 27 giải!")
        else:
            v_loto = [n[-2:] for n in raw_list[:27]]
            
            # Đối soát bảng điểm của kỳ TRƯỚC
            old_scores = st.session_state['final_scores'] if st.session_state['final_scores'] else {f"{i:02d}": 100.0 for i in range(100)}
            df_old = pd.DataFrame(list(old_scores.items()), columns=['Số', 'Điểm']).sort_values(by='Điểm', ascending=False).reset_index(drop=True)
            
            # Cập nhật điểm kỳ NÀY
            new_db, power_scores, hardness_map, compression_map = update_matrix_v8_3(st.session_state['db'], v_loto, st.session_state['gdb_val'])
            st.session_state['db'] = new_db
            st.session_state['final_scores'] = power_scores
            st.session_state['hardness'] = hardness_map
            st.session_state['compression'] = compression_map

            # Phân lớp lịch sử
            slices = {"T5": (0,5), "T10": (5,10), "T15": (10,15), "T20": (15,20), "T30": (20,30), "T50": (30,50), "T80": (50,80), "Cao": (95,100)}
            def get_hit_str(targets, results):
                hits = [n for n in targets if n in results]
                nhay = sum([results.count(n) for n in hits])
                return f"{nhay}({','.join(sorted(list(set(hits))))})" if nhay > 0 else "0"

            rank_gdb = "-"
            try: rank_gdb = df_old[df_old['Số'] == st.session_state['gdb_val']].index[0]
            except: pass

            res = {"STT": len(st.session_state['history']) + 1, "GĐB": st.session_state['gdb_val'], "Hạng": rank_gdb}
            for label, (start, end) in slices.items():
                res[label] = get_hit_str(df_old.iloc[start:end]['Số'].tolist(), v_loto)
            
            st.session_state['history'].insert(0, res)
            st.rerun()

# --- 3. HIỂN THỊ ---
if st.session_state.get('final_scores'):
    c_left, c_right = st.columns([1.5, 3.5])
    with c_left:
        st.subheader("📊 TỔNG LỰC & NÉN")
        df_disp = pd.DataFrame([
            {"Số": n, "Điểm": p, "Cứng(%)": round(st.session_state['hardness'][n], 1), "Nén": st.session_state['compression'][n]} 
            for n, p in st.session_state['final_scores'].items()
        ])
        
        def set_status(row):
            if row['Nén'] > 15: return "🧨"
            if row['Điểm'] > 180: return "🚀"
            if row['Cứng(%)'] > 70: return "🔋"
            return "✅"
        
        df_disp['T.Thái'] = df_disp.apply(set_status, axis=1)
        df_disp = df_disp.sort_values(by='Điểm', ascending=False).reset_index(drop=True)
        st.dataframe(df_disp, use_container_width=True, height=600)

    with c_right:
        st.subheader("📜 LỊCH SỬ (MỚI NHẤT TRÊN CÙNG)")
        st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True)
        
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("🎯 TOP LÒ XO CĂNG")
            df_compress = df_disp.sort_values(by='Nén', ascending=False).head(5)
            st.table(df_compress[['Số', 'Nén', 'Điểm']])
        with col2:
            st.subheader("💾 LƯU TRỮ JSON")
            save_data = {"matrix": st.session_state['db'], "history": st.session_state['history']}
            st.download_button("💾 TẢI FILE DỮ LIỆU", data=json.dumps(save_data), file_name="matrix_v8_3.json")
            
            st.write("---")
            num = st.number_input("Trích quân Top:", 1, 50, 10)
            st.code(", ".join(df_disp.head(num)['Số'].tolist()))
