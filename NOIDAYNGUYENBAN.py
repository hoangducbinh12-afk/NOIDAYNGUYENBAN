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

if 'db' not in st.session_state:
    st.session_state['db'] = {str(i): {"score": DEFAULT_SCORE, "streak_win": 0, "streak_loss": 0, "history_hits": 0} for i in range(TOTAL_WIRES)}
if 'history' not in st.session_state: st.session_state['history'] = []
if 'final_scores' not in st.session_state: st.session_state['final_scores'] = None
if 'hardness' not in st.session_state: st.session_state['hardness'] = None
if 'compression' not in st.session_state: st.session_state['compression'] = None

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'])

# --- HÀM LÀM MỚI DỮ LIỆU HIỂN THỊ (Dùng khi nạp file hoặc sau khi phân tích) ---
def refresh_display_data():
    if not st.session_state['db']: return
    
    db = st.session_state['db']
    actual_db = db.get('matrix', db) if isinstance(db.get('matrix'), dict) else db
    total_periods = len(st.session_state['history'])
    
    num_power = {f"{i:02d}": 0.0 for i in range(100)}
    hardness_map = {f"{i:02d}": 0.0 for i in range(100)}
    compression_map = {f"{i:02d}": 0 for i in range(100)}
    temp_hrd = {f"{i:02d}": {"sum": 0.0, "count": 0} for i in range(100)}

    for wire_id in range(TOTAL_WIRES):
        w_str = str(wire_id)
        if w_str in actual_db:
            wire = actual_db[w_str]
            num_formed = f"{wire_id % 100:02d}"
            
            # Tính Tổng Lực (Hệ số 1.5 cho dây đang nổ, 0.7 cho dây trượt)
            p_coef = 1.5 if wire.get("streak_win", 0) > 0 else 0.7
            num_power[num_formed] += (wire.get("score", DEFAULT_SCORE) * p_coef)
            
            # Tính Nén (Cực đại)
            if wire.get("streak_loss", 0) > compression_map[num_formed]:
                compression_map[num_formed] = wire.get("streak_loss", 0)
                
            # Tính Độ Cứng (Tần suất nổ tích lũy)
            hits = wire.get("history_hits", 0)
            eff = (hits / total_periods * 100) if total_periods > 0 else 0
            temp_hrd[num_formed]["sum"] += eff
            temp_hrd[num_formed]["count"] += 1

    for n in range(100):
        s = f"{n:02d}"
        if temp_hrd[s]["count"] > 0:
            hardness_map[s] = temp_hrd[s]["sum"] / temp_hrd[s]["count"]

    st.session_state['final_scores'] = num_power
    st.session_state['hardness'] = hardness_map
    st.session_state['compression'] = compression_map

# --- THUẬT TOÁN VẬN HÀNH THUẬN DÒNG ---
def update_matrix_v8_7(loto_list, gdb_loto):
    db = st.session_state['db']
    actual_db = db.get('matrix', db) if isinstance(db.get('matrix'), dict) else db
    new_matrix = json.loads(json.dumps(actual_db))
    
    for wire_id in range(TOTAL_WIRES):
        w_str = str(wire_id)
        if w_str not in new_matrix:
            new_matrix[w_str] = {"score": DEFAULT_SCORE, "streak_win": 0, "streak_loss": 0, "history_hits": 0}
        
        wire = new_matrix[w_str]
        num_formed = f"{wire_id % 100:02d}"
        is_hit = num_formed in loto_list
        is_gdb = (num_formed == gdb_loto)

        if is_hit:
            wire["streak_loss"] = 0
            wire["streak_win"] += 1
            wire["history_hits"] = wire.get("history_hits", 0) + 1
            if is_gdb: wire["score"] += 2.0
            wire["score"] += float(loto_list.count(num_formed)) * 2.0 if wire["streak_win"] < 4 else -0.5
        else:
            wire["streak_win"] = 0
            wire["streak_loss"] += 1
            if wire["streak_loss"] >= 4: wire["score"] += 0.1

    st.session_state['db'] = new_matrix
    refresh_display_data()

# --- 2. GIAO DIỆN CHÍNH ---
st.set_page_config(page_title="Matrix V8.7 Master", layout="wide")
st.markdown("<h2 style='text-align: center; color: #00FF00;'>📈 MATRIX V8.7 MASTER - FULL OPTION</h2>", unsafe_allow_html=True)

with st.sidebar:
    st.header("📂 HỆ THỐNG")
    if st.button("🚨 RESET ALL (XÓA HẾT)"):
        st.session_state.clear()
        st.rerun()

    up_json = st.file_uploader("📥 Nạp JSON dữ liệu", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP FILE"):
        data = json.load(up_json)
        st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', [])
        refresh_display_data()
        st.success("Đã nạp dữ liệu thành công!")
        st.rerun()

    st.divider()
    st.header("📸 QUÉT KẾT QUẢ")
    up_img = st.file_uploader("Chọn ảnh kết quả", type=['jpg', 'jpeg', 'png'])
    if up_img and st.button("BẮT ĐẦU QUÉT OCR"):
        with st.spinner("Đang nhận diện số..."):
            reader = load_ocr()
            results = reader.readtext(np.array(Image.open(up_img)), detail=0)
            nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
            if nums:
                st.session_state['raw_input'] = ", ".join(nums)
                st.session_state['gdb_val'] = nums[0][-2:]
        st.rerun()

    st.session_state['raw_input'] = st.text_area("27 giải:", value=st.session_state.get('raw_input', ""), height=100)
    st.session_state['gdb_val'] = st.text_input("GĐB:", value=st.session_state.get('gdb_val', ""), max_chars=2)

    if st.button("🔥 CHẠY PHÂN TÍCH KỲ MỚI"):
        raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
        if len(raw_list) >= 27:
            v_loto = [n[-2:] for n in raw_list[:27]]
            
            # Lưu điểm kỳ cũ để đối soát hạng
            old_scores = st.session_state['final_scores'] if st.session_state['final_scores'] else {f"{i:02d}": 100.0 for i in range(100)}
            df_old = pd.DataFrame(list(old_scores.items()), columns=['Số', 'Điểm']).sort_values(by='Điểm', ascending=False).reset_index(drop=True)
            
            # Cập nhật thuật toán
            update_matrix_v8_7(v_loto, st.session_state['gdb_val'])

            # Đối soát 16 vùng lịch sử
            slices = {
                "T5": (0, 5), "T10": (5, 10), "T15": (10, 15), "T20": (15, 20),
                "T25": (20, 25), "T30": (25, 30), "T35": (30, 35), "T40": (35, 40),
                "T45": (40, 45), "T50": (45, 50), "T60": (50, 60), "T70": (60, 70),
                "T80": (70, 80), "T90": (80, 90), "T95": (90, 95), "Cao": (95, 100)
            }

            def get_hit(targets, res):
                hits = [n for n in targets if n in res]
                nhay = sum([res.count(n) for n in hits])
                return f"{nhay}({','.join(sorted(list(set(hits))))})" if nhay > 0 else "0"

            rank_gdb = "-"
            try: rank_gdb = df_old[df_old['Số'] == st.session_state['gdb_val']].index[0]
            except: pass

            history_entry = {"STT": len(st.session_state['history'])+1, "GĐB": st.session_state['gdb_val'], "Hạng": rank_gdb}
            for label, (s, e) in slices.items():
                history_entry[label] = get_hit(df_old.iloc[s:e]['Số'].tolist(), v_loto)
            
            st.session_state['history'].insert(0, history_entry)
            st.rerun()

# --- 3. HIỂN THỊ KẾT QUẢ ---
if st.session_state.get('final_scores'):
    c1, c2 = st.columns([1.6, 3.4])
    
    # Chuẩn bị DataFrame
    df = pd.DataFrame([
        {
            "Số": n, 
            "Điểm": p, 
            "Cứng(%)": round(st.session_state['hardness'].get(n, 0), 1), 
            "Nén": st.session_state['compression'].get(n, 0)
        } 
        for n, p in st.session_state['final_scores'].items()
    ])
    
    # Định nghĩa Icon Trạng thái
    def set_status_icon(row):
        if row['Nén'] > 18: return "🧨" # Pháo nén kỷ lục
        top_scores = sorted(df['Điểm'].unique(), reverse=True)[:3]
        if row['Điểm'] in top_scores: return "🚀" # Top 3 sức mạnh
        if row['Cứng(%)'] > df['Cứng(%)'].mean(): return "🔋" # Độ cứng ổn định
        return "✅"

    df['T.Thái'] = df.apply(set_status_icon, axis=1)
    df_sorted = df.sort_values('Điểm', ascending=False).reset_index(drop=True)

    with c1:
        st.subheader("📊 TỔNG LỰC THUẬN DÒNG")
        st.dataframe(df_sorted, use_container_width=True, height=600)

    with c2:
        st.subheader("📜 LỊCH SỬ 16 PHÂN VÙNG (MỚI NHẤT TRÊN CÙNG)")
        if st.session_state['history']:
            st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True)
        
        st.divider()
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("🎯 TOP 5 LÒ XO (NÉN CĂNG)")
            df_compress = df.sort_values('Nén', ascending=False).head(5)
            st.table(df_compress[['Số', 'Nén', 'Điểm']])
        with col_b:
            st.subheader("💾 LƯU TRỮ & TRÍCH DÀN")
            save_data = {"matrix": st.session_state['db'], "history": st.session_state['history']}
            st.download_button("💾 XUẤT FILE JSON MỚI NHẤT", data=json.dumps(save_data), file_name="matrix_v8_7.json")
            
            st.write("---")
            num_get = st.number_input("Số lượng quân trích từ Top Điểm:", 1, 100, 10)
            st.code(", ".join(df_sorted.head(num_get)['Số'].tolist()))
