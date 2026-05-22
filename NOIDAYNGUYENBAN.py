import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
from PIL import Image

# --- 1. KHỞI TẠO ---
TOTAL_POS = 107
TOTAL_WIRES = TOTAL_POS * TOTAL_POS
DEFAULT_SCORE = 100.0

if 'db' not in st.session_state:
    st.session_state['db'] = {str(i): {"score": DEFAULT_SCORE, "streak_win": 0, "streak_loss": 0} for i in range(TOTAL_WIRES)}
if 'history' not in st.session_state: st.session_state['history'] = []
if 'final_scores' not in st.session_state: st.session_state['final_scores'] = None
if 'hardness' not in st.session_state: st.session_state['hardness'] = None

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'])
reader = load_ocr()

# --- THUẬT TOÁN ĐÁNH GIÁ CHẤT LƯỢNG DÂY (V7.1) ---
def update_matrix_v7_1(db, loto_list, gdb_loto):
    actual_db = db.get('matrix', db) if isinstance(db.get('matrix'), dict) else db
    new_matrix = json.loads(json.dumps(actual_db))
    
    num_power = {f"{i:02d}": 0.0 for i in range(100)}
    wire_quality_count = {f"{i:02d}": {"good": 0, "total": 0} for i in range(100)}

    for wire_id in range(TOTAL_WIRES):
        w_str = str(wire_id)
        wire = new_matrix[w_str]
        num_formed = f"{wire_id % 100:02d}"
        
        is_hit = num_formed in loto_list
        is_gdb = (num_formed == gdb_loto)

        # Quy tắc điểm Thưởng/Phạt
        if is_hit:
            wire["streak_loss"] = 0
            wire["streak_win"] += 1
            if is_gdb:
                wire["score"] -= 5.0 # Trừ 5đ nếu nổ đề (Lọc nhiễu)
            elif wire["streak_win"] < 4:
                wire["score"] += float(loto_list.count(num_formed))
            else:
                wire["score"] -= 1.0 # Phạt bệt
        else:
            wire["streak_win"] = 0
            wire["streak_loss"] += 1
            if wire["streak_loss"] >= 4:
                wire["score"] += 0.5 # Nén lò xo

        # Phân loại dây dựa trên phong độ (Hệ số P)
        p_coef = 0.5 # Mặc định Dây Chì
        is_good = False
        
        # Dây Vàng: Đang nén lâu hoặc vừa bùng nổ kỳ đầu
        if wire["streak_loss"] >= 4 or (wire["streak_win"] == 1 and is_hit):
            p_coef = 1.5
            is_good = True
        # Dây Bạc: Nổ ổn định dưới 4 kỳ
        elif 0 < wire["streak_win"] < 4:
            p_coef = 1.2
            is_good = True
        
        num_power[num_formed] += (wire["score"] * p_coef)
        wire_quality_count[num_formed]["total"] += 1
        if is_good:
            wire_quality_count[num_formed]["good"] += 1

    hardness_map = {n: (q["good"]/q["total"]*100) for n, q in wire_quality_count.items()}
    return new_matrix, num_power, hardness_map

# --- 2. GIAO DIỆN ---
st.set_page_config(page_title="Matrix V7.1 Pro", layout="wide")
st.markdown("<h2 style='text-align: center; color: #00FFCC;'>💎 MATRIX 11.449 V7.1 - SIÊU PHÂN LỚP ĐỘ CỨNG</h2>", unsafe_allow_html=True)

with st.sidebar:
    st.header("📂 HỆ THỐNG")
    if st.button("🚨 RESET MỚI HOÀN TOÀN"):
        st.session_state.clear()
        st.rerun()

    st.divider()
    uploaded_img = st.file_uploader("📸 Quét ảnh KQ", type=['jpg', 'jpeg', 'png'])
    if uploaded_img and st.button("OCR"):
        results = reader.readtext(np.array(Image.open(uploaded_img)), detail=0)
        nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
        if nums:
            st.session_state['raw_input'] = ", ".join(nums)
            st.session_state['gdb_val'] = nums[0][-2:]
        st.rerun()

    st.session_state['raw_input'] = st.text_area("27 giải:", value=st.session_state.get('raw_input', ""), height=100)
    st.session_state['gdb_val'] = st.text_input("GĐB:", value=st.session_state.get('gdb_val', ""), max_chars=2)

    if st.button("🔥 CHẠY PHÂN TÍCH"):
        raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
        if len(raw_list) < 27:
            st.error("Phải nhập đủ 27 giải!")
        else:
            v_loto = [n[-2:] for n in raw_list[:27]]
            
            # 1. Lấy bảng điểm cũ để đối soát TRƯỚC KHI cập nhật
            if st.session_state['final_scores'] is not None:
                old_scores = st.session_state['final_scores']
            else:
                old_scores = {f"{i:02d}": 100.0 for i in range(100)}
            
            df_old = pd.DataFrame(list(old_scores.items()), columns=['Số', 'Điểm']).sort_values(by='Điểm', ascending=False).reset_index(drop=True)
            
            # 2. Cập nhật dữ liệu mới
            new_db, power_scores, hardness_map = update_matrix_v7_1(st.session_state['db'], v_loto, st.session_state['gdb_val'])
            st.session_state['db'] = new_db
            st.session_state['final_scores'] = power_scores
            st.session_state['hardness'] = hardness_map

            # 3. Phân vùng lịch sử 16 lớp chuẩn yêu cầu
            slices = {
                "T5": (0, 5), "T10": (5, 10), "T15": (10, 15), "T20": (15, 20),
                "T25": (20, 25), "T30": (25, 30), "T35": (30, 35), "T40": (35, 40),
                "T45": (40, 45), "T50": (45, 50), "T60": (50, 60), "T70": (60, 70),
                "T80": (70, 80), "T90": (80, 90), "T95": (90, 95), "Cao": (95, 100)
            }

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
            
            st.session_state['history'].append(res)
            st.rerun()

# --- 3. HIỂN THỊ ---
if st.session_state.get('final_scores'):
    c_left, c_right = st.columns([1, 4])
    with c_left:
        st.subheader("📊 TỔNG LỰC & ĐỘ CỨNG")
        df_disp = pd.DataFrame([
            {"Số": n, "Điểm": p, "Cứng (%)": st.session_state['hardness'][n]} 
            for n, p in st.session_state['final_scores'].items()
        ])
        
        # Logic Icon mới để hiện Băng ❄️
        def set_icon(row):
            # Kim cương: Tổng lực mạnh + Dây bền
            if row['Điểm'] > 150 and row['Cứng (%)'] > 60: return "💎"
            # Lửa: Điểm vọt lên cực nhanh (thường do bệt hoặc nổ nháy kép)
            if row['Điểm'] > 130: return "🔥"
            # Băng: Độ cứng cao (>50%) nhưng điểm chưa quá nóng (vùng nén tiềm năng)
            if row['Cứng (%)'] > 50: return "❄️"
            return "⏳"
        
        df_disp['Loại'] = df_disp.apply(set_icon, axis=1)
        df_disp = df_disp.sort_values(by='Điểm', ascending=False).reset_index(drop=True)
        st.dataframe(df_disp, use_container_width=True, height=550)

    with c_right:
        st.subheader("📜 LỊCH SỬ 16 PHÂN LỚP CHI TIẾT")
        # Sử dụng dataframe để có thanh cuộn ngang cho 16 vùng
        st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True)
        
        st.divider()
        st.subheader("🎯 TRÍCH QUÂN DẪN ĐẦU")
        num = st.number_input("Số lượng:", 1, 100, 5)
        st.code(", ".join(df_disp.head(num)['Số'].tolist()))
        
        save_data = {"matrix": st.session_state['db'], "history": st.session_state['history']}
        st.download_button("💾 XUẤT JSON DỮ LIỆU BỀN", data=json.dumps(save_data), file_name="matrix_v7_1.json")
