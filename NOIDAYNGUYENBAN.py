import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
from PIL import Image

# --- 1. KHỞI TẠO HỆ THỐNG V9.1 ---
TOTAL_POS = 107 
TOTAL_WIRES = TOTAL_POS * TOTAL_POS
DEFAULT_SCORE = 100.0

if 'db' not in st.session_state:
    st.session_state['db'] = {str(i): {"score": DEFAULT_SCORE, "streak_win": 0, "streak_loss": 0, "history_hits": 0} for i in range(TOTAL_WIRES)}
if 'history' not in st.session_state: st.session_state['history'] = []
if 'final_scores' not in st.session_state: st.session_state['final_scores'] = None
if 'last_full_str' not in st.session_state: st.session_state['last_full_str'] = None

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'])

# --- HÀM MAPPING ĐỘNG ---
def get_mapping_v9(full_str):
    if not full_str or len(full_str) < TOTAL_POS: return None
    mapping = {}
    for i in range(TOTAL_POS):
        for j in range(TOTAL_POS):
            wire_id = i * TOTAL_POS + j
            num_formed = f"{full_str[i]}{full_str[j]}"
            mapping[str(wire_id)] = num_formed
    return mapping

# --- HÀM LÀM MỚI HIỂN THỊ (DYNAMIC REFRESH) ---
def refresh_display_v9():
    if not st.session_state['last_full_str']: return
    
    current_map = get_mapping_v9(st.session_state['last_full_str'])
    db = st.session_state['db']
    total_periods = len(st.session_state['history'])
    
    num_power = {f"{i:02d}": 0.0 for i in range(100)}
    num_compression = {f"{i:02d}": 0 for i in range(100)}
    temp_hrd = {f"{i:02d}": {"sum": 0.0, "count": 0} for i in range(100)}

    for wire_id, num_formed in current_map.items():
        wire = db.get(wire_id, {"score": 100.0, "streak_win": 0, "streak_loss": 0, "history_hits": 0})
        
        # Sức mạnh dây
        p_coef = 1.5 if wire["streak_win"] > 0 else 0.7
        num_power[num_formed] += (wire["score"] * p_coef)
        
        # Độ nén (Lấy cực đại của dây trỏ về số đó)
        if wire["streak_loss"] > num_compression[num_formed]:
            num_compression[num_formed] = wire["streak_loss"]
            
        # Độ cứng (Tần suất dây)
        eff = (wire["history_hits"] / total_periods * 100) if total_periods > 0 else 0
        temp_hrd[num_formed]["sum"] += eff
        temp_hrd[num_formed]["count"] += 1

    hardness_map = {n: (temp_hrd[n]["sum"]/temp_hrd[n]["count"]) if temp_hrd[n]["count"] > 0 else 0 for n in num_power}
    
    st.session_state['final_scores'] = num_power
    st.session_state['hardness'] = hardness_map
    st.session_state['compression'] = num_compression

# --- THUẬT TOÁN CẬP NHẬT THEO DÂY ---
def update_matrix_v9_1(raw_27_list, gdb_loto):
    full_str = "".join(raw_27_list)
    loto_list = [n[-2:] for n in raw_27_list]
    
    # Sử dụng mapping của kỳ TRƯỚC để tính Win/Loss cho DÂY
    if not st.session_state['last_full_str']:
        # Nếu là kỳ đầu tiên, khởi tạo mapping tĩnh tạm thời để có dữ liệu
        st.session_state['last_full_str'] = full_str
        
    current_map = get_mapping_v9(st.session_state['last_full_str'])
    new_db = json.loads(json.dumps(st.session_state['db']))
    
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
    st.session_state['last_full_str'] = full_str # Cập nhật full_str mới cho kỳ sau
    refresh_display_v9()

# --- 2. GIAO DIỆN ---
st.set_page_config(page_title="Matrix V9.1 Master", layout="wide")
st.markdown("<h2 style='text-align: center; color: #00FFFF;'>🌐 MATRIX V9.1 - MASTER DYNAMIC MAPPING</h2>", unsafe_allow_html=True)

with st.sidebar:
    st.header("📂 HỆ THỐNG")
    if st.button("🚨 RESET ALL"):
        st.session_state.clear()
        st.rerun()

    up_json = st.file_uploader("📥 Nạp JSON dữ liệu", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json)
        st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', [])
        st.session_state['last_full_str'] = data.get('last_full_str', None)
        refresh_display_v9()
        st.success("Đã nạp dữ liệu!")
        st.rerun()

    st.divider()
    st.header("📸 QUÉT KQ")
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

    st.session_state['raw_input'] = st.text_area("Nhập 27 giải (cách nhau):", value=st.session_state.get('raw_input', ""), height=100)
    st.session_state['gdb_val'] = st.text_input("GĐB:", value=st.session_state.get('gdb_val', ""), max_chars=2)

    if st.button("🔥 PHÂN TÍCH ÁNH XẠ"):
        raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
        if len(raw_list) >= 27:
            # Lấy data cũ đối soát
            old_df = get_display_data_v9_tmp() # Hàm hỗ trợ lấy df hiện tại
            
            update_matrix_v9_1(raw_list[:27], st.session_state['gdb_val'])
            
            # Ghi lịch sử
            slices = {"T5": (0,5), "T10": (5,10), "T20": (10,20), "T50": (20,50), "Cao": (95,100)}
            def get_hit_str(targets, res_loto):
                hits = [n for n in targets if n in res_loto]
                return f"{len(hits)}({','.join(hits)})" if hits else "0"
            
            if old_df is not None:
                v_loto = [n[-2:] for n in raw_list[:27]]
                res = {"STT": len(st.session_state['history'])+1, "GĐB": st.session_state['gdb_val']}
                df_sorted_old = old_df.sort_values('Điểm', ascending=False).reset_index(drop=True)
                for k, (s, e) in slices.items():
                    res[k] = get_hit_str(df_sorted_old.iloc[s:e]['Số'].tolist(), v_loto)
                st.session_state['history'].insert(0, res)
            st.rerun()

def get_display_data_v9_tmp():
    if st.session_state.get('final_scores'):
        df = pd.DataFrame([{"Số": n, "Điểm": p, "Cứng(%)": round(st.session_state['hardness'][n], 1), "Nén": st.session_state['compression'][n]} for n, p in st.session_state['final_scores'].items()])
        return df
    return None

# --- 3. HIỂN THỊ ---
df_disp = get_display_data_v9_tmp()
if df_disp is not None:
    c1, c2 = st.columns([1.6, 3.4])
    with c1:
        st.subheader("📊 TỔNG LỰC ĐỘNG")
        top_scores = sorted(df_disp['Điểm'].unique(), reverse=True)[:3]
        def set_status(row):
            if row['Nén'] > 18: return "🧨"
            if row['Điểm'] in top_scores: return "🚀"
            if row['Cứng(%)'] > df_disp['Cứng(%)'].mean(): return "🔋"
            return "✅"
        df_disp['T.Thái'] = df_disp.apply(set_status, axis=1)
        st.dataframe(df_disp.sort_values('Điểm', ascending=False).reset_index(drop=True), use_container_width=True, height=600)

    with c2:
        st.subheader("📜 LỊCH SỬ CUỘN NGƯỢC")
        st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True)
        st.divider()
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("🎯 TOP 5 LÒ XO CĂNG")
            st.table(df_disp.sort_values('Nén', ascending=False).head(5)[['Số', 'Nén', 'Điểm']])
        with col_b:
            st.subheader("💾 LƯU TRỮ")
            save_data = {"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state['last_full_str']}
            st.download_button("💾 XUẤT JSON", data=json.dumps(save_data), file_name="matrix_v9_1.json")
            num = st.number_input("Trích Top:", 1, 100, 10)
            st.code(", ".join(df_disp.sort_values('Điểm', ascending=False).head(num)['Số'].tolist()))
