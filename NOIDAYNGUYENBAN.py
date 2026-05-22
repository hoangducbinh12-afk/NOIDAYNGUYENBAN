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

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'])
reader = load_ocr()

# --- THUẬT TOÁN ĐÁNH GIÁ CHẤT LƯỢNG DÂY (V7) ---
def update_matrix_v7(db, loto_list, gdb_loto):
    actual_db = db.get('matrix', db) if isinstance(db.get('matrix'), dict) else db
    new_matrix = json.loads(json.dumps(actual_db))
    
    # num_power: Tổng lực sau khi nhân hệ số P
    # num_hardness: % dây bền (Vàng + Bạc)
    num_power = {f"{i:02d}": 0.0 for i in range(100)}
    wire_quality_count = {f"{i:02d}": {"good": 0, "total": 0} for i in range(100)}

    for wire_id in range(TOTAL_WIRES):
        w_str = str(wire_id)
        wire = new_matrix[w_str]
        
        # 1. Xác định số con số mà dây này tạo ra (Tĩnh theo tọa độ)
        # Giả sử dây id tạo ra số: (wire_id % 100)
        num_formed = f"{wire_id % 100:02d}"
        
        is_hit = num_formed in loto_list
        is_gdb = (num_formed == gdb_loto)

        # 2. Quy tắc Thưởng / Phạt điểm gốc
        if is_hit:
            wire["streak_loss"] = 0
            wire["streak_win"] += 1
            
            if is_gdb:
                wire["score"] -= 5.0 # Nổ GĐB: Trừ 5đ (Lọc nhiễu)
            elif wire["streak_win"] < 4:
                wire["score"] += float(loto_list.count(num_formed)) # Nổ bình thường: +1đ/nháy
            else:
                wire["score"] -= 1.0 # Nổ bệt >= 4: Trừ 1đ
        else:
            wire["streak_win"] = 0
            wire["streak_loss"] += 1
            if wire["streak_loss"] >= 4:
                wire["score"] += 0.5 # Khan >= 4: Cộng 0.5đ (Nén lò xo)

        # 3. Phân loại chất lượng dây (Hệ số P)
        p_coef = 0.5 # Mặc định là Dây Chì
        is_good = False
        
        if wire["streak_loss"] >= 4 or (wire["streak_win"] == 1 and is_hit):
            p_coef = 1.5 # Dây Vàng: Khan dài hoặc vừa bứt phá
            is_good = True
        elif 0 < wire["streak_win"] < 4:
            p_coef = 1.2 # Dây Bạc: Nổ ổn định
            is_good = True
        
        # 4. Tính Tổng lực (Total Power)
        num_power[num_formed] += (wire["score"] * p_coef)
        
        # 5. Tính Độ cứng (Hardness)
        wire_quality_count[num_formed]["total"] += 1
        if is_good:
            wire_quality_count[num_formed]["good"] += 1

    # Tính toán lại độ cứng %
    hardness_map = {}
    for n in num_power:
        q = wire_quality_count[n]
        hardness_map[n] = (q["good"] / q["total"] * 100) if q["total"] > 0 else 0

    return new_matrix, num_power, hardness_map

# --- 2. GIAO DIỆN ---
st.set_page_config(page_title="Matrix V7 Pro", layout="wide")
st.markdown("<h2 style='text-align: center; color: #FFD700;'>💎 MATRIX 11.449 V7 - CHẤT LƯỢNG DÂY</h2>", unsafe_allow_html=True)

with st.sidebar:
    st.header("📂 DỮ LIỆU")
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

    if st.button("🔥 PHÂN TÍCH V7"):
        raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
        v_loto = [n[-2:] for n in raw_list[:27]]
        
        # Lấy bảng điểm cũ để đối soát
        if st.session_state['final_scores'] is not None:
            old_data = st.session_state['final_scores']
        else:
            old_data = {f"{i:02d}": 100.0 for i in range(100)}

        old_df = pd.DataFrame(list(old_data.items()), columns=['Số', 'Điểm']).sort_values(by='Điểm', ascending=False).reset_index(drop=True)
        
        # Cập nhật Ma trận
        new_db, power_scores, hardness_map = update_matrix_v7(st.session_state['db'], v_loto, st.session_state['gdb_val'])
        st.session_state['db'] = new_db
        st.session_state['final_scores'] = power_scores
        st.session_state['hardness'] = hardness_map

        # Đối soát lịch sử (16 vùng như V6)
        def get_hit_info(target_nums, result_list):
            hits = [n for n in target_nums if n in result_list]
            nhay = sum([result_list.count(n) for n in hits])
            return f"{nhay}({','.join(sorted(list(set(hits))))})" if nhay > 0 else "0"

        # (Phần này giữ logic phân slice từ V6 nhưng áp dụng cho kết quả V7)
        slices = {"T5": (0,5), "T10": (5,10), "T20": (10,20), "T50": (20,50), "Cao": (95,100)}
        res = {"STT": len(st.session_state['history']) + 1, "GĐB": st.session_state['gdb_val']}
        for k, (s, e) in slices.items():
            res[k] = get_hit_info(old_df.iloc[s:e]['Số'].tolist(), v_loto)
        
        st.session_state['history'].append(res)
        st.rerun()

# --- 3. HIỂN THỊ ---
if st.session_state.get('final_scores'):
    c_left, c_right = st.columns([1, 2])
    with c_left:
        st.subheader("📊 TỔNG LỰC & ĐỘ CỨNG")
        df_display = pd.DataFrame([
            {"Số": n, "Tổng Lực": p, "Độ Cứng (%)": st.session_state['hardness'][n]} 
            for n, p in st.session_state['final_scores'].items()
        ])
        
        # Thêm Icon nhận diện
        def get_icon(row):
            if row['Tổng Lực'] > 150 and row['Độ Cứng (%)'] > 70: return "💎"
            if row['Tổng Lực'] > 120: return "🔥"
            if row['Độ Cứng (%)'] > 80: return "❄️"
            return "⏳"
        
        df_display['Loại'] = df_display.apply(get_icon, axis=1)
        df_display = df_display.sort_values(by='Tổng Lực', ascending=False).reset_index(drop=True)
        st.dataframe(df_display, use_container_width=True, height=500)

    with c_right:
        st.subheader("📜 LỊCH SỬ ĐỐI SOÁT V7")
        st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True)
        
        st.divider()
        st.subheader("🎯 TRÍCH QUÂN SIÊU CẤP")
        num = st.number_input("Số lượng quân:", 1, 100, 5)
        top_list = df_display.head(num)['Số'].tolist()
        st.code(", ".join(top_list))
        
        # Lưu file để giữ "phong độ" dây
        save_data = {"matrix": st.session_state['db'], "history": st.session_state['history']}
        st.download_button("💾 LƯU DỮ LIỆU BỀN", data=json.dumps(save_data), file_name="matrix_v7_power.json")
