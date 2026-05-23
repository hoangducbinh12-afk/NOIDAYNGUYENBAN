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
    st.session_state['db'] = {str(i): {"score": DEFAULT_SCORE, "streak_win": 0, "streak_loss": 0, "history_hits": 0} for i in range(TOTAL_WIRES)}
if 'history' not in st.session_state: st.session_state['history'] = []
if 'final_scores' not in st.session_state: st.session_state['final_scores'] = None
if 'hardness' not in st.session_state: st.session_state['hardness'] = None
if 'compression' not in st.session_state: st.session_state['compression'] = None
if 'last_full_str' not in st.session_state: st.session_state['last_full_str'] = None

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'])

# --- 2. HÀM CÔNG CỤ MASTER ---

def get_mapping_v9(full_str):
    if not full_str or len(full_str) < TOTAL_POS: return None
    mapping = {}
    for i in range(TOTAL_POS):
        for j in range(TOTAL_POS):
            wire_id = i * TOTAL_POS + j
            num_formed = f"{full_str[i]}{full_str[j]}"
            mapping[str(wire_id)] = num_formed
    return mapping

def refresh_display_v94():
    """TÍNH TOÁN HIỂN THỊ - FIX LỖI NÉN GIỐNG NHAU"""
    if not st.session_state['last_full_str']: return
    
    current_map = get_mapping_v9(st.session_state['last_full_str'])
    db = st.session_state['db']
    total_periods = len(st.session_state['history'])
    
    num_power = {f"{i:02d}": 0.0 for i in range(100)}
    # Khởi tạo nén với giá trị cực lớn để tìm Min của các Max, hoặc dùng logic Win
    num_compression = {f"{i:02d}": [] for i in range(100)} 
    temp_hrd = {f"{i:02d}": {"sum": 0.0, "count": 0} for i in range(100)}

    for wire_id, num_formed in current_map.items():
        wire = db.get(wire_id, {"score": DEFAULT_SCORE, "streak_win": 0, "streak_loss": 0, "history_hits": 0})
        
        # 1. Tổng lực
        p_coef = 1.5 if wire.get("streak_win", 0) > 0 else 0.7
        num_power[num_formed] += (wire.get("score", DEFAULT_SCORE) * p_coef)
        
        # 2. Thu thập tất cả streak_loss của các dây trỏ về số này
        num_compression[num_formed].append(wire.get("streak_loss", 0))
            
        # 3. Độ cứng
        eff = (wire.get("history_hits", 0) / total_periods * 100) if total_periods > 0 else 0
        temp_hrd[num_formed]["sum"] += eff
        temp_hrd[num_formed]["count"] += 1

    # CHỐT ĐỘ NÉN: Nếu có dây nổ (loss=0), nén phải giảm. 
    # Ở đây tao lấy trung bình cộng độ nén của các dây để thấy sự biến động mượt mà nhất
    final_comp = {}
    for n, losses in num_compression.items():
        if not losses: 
            final_comp[n] = 0
        else:
            # Nếu có dây vừa nổ (0), nó sẽ kéo trung bình nén xuống ngay lập tức
            final_comp[n] = int(sum(losses) / len(losses))

    st.session_state['hardness'] = {n: (temp_hrd[n]["sum"]/temp_hrd[n]["count"]) if temp_hrd[n]["count"] > 0 else 0 for n in num_power}
    st.session_state['final_scores'] = num_power
    st.session_state['compression'] = final_comp

def get_current_df_full():
    if st.session_state.get('final_scores'):
        df = pd.DataFrame([
            {
                "Số": n, 
                "Điểm": p, 
                "Cứng(%)": round(st.session_state['hardness'].get(n, 0), 1), 
                "Nén": st.session_state['compression'].get(n, 0)
            } 
            for n, p in st.session_state['final_scores'].items()
        ])
        return df
    return None

# --- 3. GIAO DIỆN ---
st.set_page_config(page_title="Matrix V9.4 Red Fix", layout="wide")
st.markdown("<h2 style='text-align: center; color: #FF0000;'>🌐 MATRIX V9.4 - FIX NÉN TUYỆT ĐỐI</h2>", unsafe_allow_html=True)

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
        refresh_display_v94()
        st.success("Đã đồng bộ ánh xạ & Fix nén!")
        st.rerun()

    st.divider()
    st.header("📸 QUÉT KQ")
    up_img = st.file_uploader("Chọn ảnh", type=['jpg', 'jpeg', 'png'])
    if up_img and st.button("OCR"):
        reader = load_ocr()
        results = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
        if nums:
            st.session_state['raw_input'] = ", ".join(nums)
            st.session_state['gdb_val'] = nums[0][-2:]
        st.rerun()

    st.session_state['raw_input'] = st.text_area("Dữ liệu 27 giải:", value=st.session_state.get('raw_input', ""), height=100)
    st.session_state['gdb_val'] = st.text_input("GĐB:", value=st.session_state.get('gdb_val', ""), max_chars=2)

    if st.button("🔥 PHÂN TÍCH ÁNH XẠ ĐỘNG"):
        raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
        if len(raw_list) >= 27:
            full_str_new = "".join(raw_list[:27])
            loto_list = [n[-2:] for n in raw_list[:27]]
            
            old_df = get_current_df_full()
            
            if not st.session_state['last_full_str']:
                st.session_state['last_full_str'] = full_str_new
                
            current_map = get_mapping_v9(st.session_state['last_full_str'])
            new_db = json.loads(json.dumps(st.session_state['db']))
            
            for wire_id, num_formed in current_map.items():
                wire = new_db[wire_id]
                is_hit = num_formed in loto_list
                if is_hit:
                    wire["streak_loss"] = 0
                    wire["streak_win"] += 1
                    wire["history_hits"] += 1
                    if num_formed == st.session_state['gdb_val']: wire["score"] += 2.0
                    wire["score"] += float(loto_list.count(num_formed)) * 2.0 if wire["streak_win"] < 4 else -0.5
                else:
                    wire["streak_win"] = 0
                    wire["streak_loss"] += 1
                    if wire["streak_loss"] >= 4: wire["score"] += 0.1

            st.session_state['db'] = new_db
            st.session_state['last_full_str'] = full_str_new
            refresh_display_v94()
            
            if old_df is not None:
                df_sorted_old = old_df.sort_values('Điểm', ascending=False).reset_index(drop=True)
                slices = {"T5": (0, 5), "T10": (5, 10), "T15": (10, 15), "T20": (15, 20), "T25": (20, 25), "T30": (25, 30), "T35": (30, 35), "T40": (35, 40), "T45": (40, 45), "T50": (45, 50), "T60": (50, 60), "T70": (60, 70), "T80": (70, 80), "T90": (80, 90), "T95": (90, 95), "Cao": (95, 100)}
                def check_hit(targets, res):
                    hits = [n for n in targets if n in res]; nhay = sum([res.count(n) for n in hits])
                    return f"{nhay}({','.join(sorted(list(set(hits))))})" if nhay > 0 else "0"
                
                rank_gdb = "-"
                try: rank_gdb = df_sorted_old[df_sorted_old['Số'] == st.session_state['gdb_val']].index[0]
                except: pass

                history_entry = {"STT": len(st.session_state['history'])+1, "GĐB": st.session_state['gdb_val'], "Hạng": rank_gdb}
                for label, (s, e) in slices.items():
                    history_entry[label] = check_hit(df_sorted_old.iloc[s:e]['Số'].tolist(), loto_list)
                st.session_state['history'].insert(0, history_entry)
            st.rerun()

# --- 4. HIỂN THỊ ---
df_final = get_current_df_full()
if df_final is not None:
    c1, c2 = st.columns([1.6, 3.4])
    top_scores = sorted(df_final['Điểm'].unique(), reverse=True)[:3]
    def set_icon(row):
        if row['Nén'] > 18: return "🧨"
        if row['Điểm'] in top_scores: return "🚀"
        if row['Cứng(%)'] > df_final['Cứng(%)'].mean(): return "🔋"
        return "✅"
    df_final['T.Thái'] = df_final.apply(set_icon, axis=1)
    df_sorted = df_final.sort_values('Điểm', ascending=False).reset_index(drop=True)

    with c1:
        st.subheader("📊 TỔNG LỰC DÂY (FIXED)")
        st.dataframe(df_sorted, use_container_width=True, height=600)
    with c2:
        st.subheader("📜 LỊCH SỬ 16 VÙNG")
        st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True)
        st.divider()
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("🎯 TOP LÒ XO")
            st.table(df_sorted.sort_values('Nén', ascending=False).head(5)[['Số', 'Nén', 'Điểm']])
        with col_b:
            st.subheader("💾 DỮ LIỆU")
            save_data = {"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state['last_full_str']}
            st.download_button("💾 XUẤT JSON V9.4", data=json.dumps(save_data), file_name="matrix_v9_4.json")
            num = st.number_input("Trích quân:", 1, 100, 10)
            st.code(", ".join(df_sorted.head(num)['Số'].tolist()))
