import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
import re
from PIL import Image

# --- 1. THÔNG SỐ HỆ THỐNG ---
TOTAL_POS = 107 
AVG_WIRES = 114.5
WINDOW = 10 

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'])

def get_mapping_v11(full_str):
    if not full_str or len(full_str) < TOTAL_POS:
        return {str(i): f"{i % 100:02d}" for i in range(11449)}
    return {str(i * TOTAL_POS + j): f"{full_str[i]}{full_str[j]}" for i in range(TOTAL_POS) for j in range(TOTAL_POS)}

def calculate_tier(losses, threshold_pct):
    if not losses: return 0
    losses_sorted = sorted(losses, reverse=True)
    idx = int(len(losses_sorted) * (threshold_pct / 100)) - 1
    return losses_sorted[max(0, idx)]

def update_matrix_state(db, results_27, mapping):
    for wire_id, w_data in db.items():
        num = mapping.get(str(wire_id))
        if num in results_27:
            w_data["streak_win"] = w_data.get("streak_win", 0) + 1
            w_data["streak_loss"] = 0
            w_data["score"] = w_data.get("score", 1000.0) - 2.7
            hist = w_data.get("hit_history", [0]*10)
            hist.append(1); w_data["hit_history"] = hist[-10:]
        else:
            w_data["streak_loss"] = w_data.get("streak_loss", 0) + 1
            w_data["streak_win"] = 0
            w_data["score"] = w_data.get("score", 1000.0) + 1.0
            hist = w_data.get("hit_history", [0]*10)
            hist.append(0); w_data["hit_history"] = hist[-10:]

# --- 2. HÀM TRUY VẾT DÂY (DÀN C) ---
def get_wire_hist_set(history):
    if not history: return set()
    try:
        # Lấy 2 số cuối của GĐB kỳ gần nhất
        last_gdb_raw = str(history[0].get('GĐB', '')).split()[0]
        last_gdb_clean = f"{int(re.sub(r'\D', '', last_gdb_raw)[-2:]):02d}"
        
        # Tìm trong lịch sử những con số hay nổ sau last_gdb_clean
        m_dict = {}
        for i in range(len(history) - 1):
            p_val = str(history[i+1].get('GĐB', '')).split()[0]
            c_val = str(history[i].get('GĐB', '')).split()[0]
            if p_val and c_val:
                p = f"{int(re.sub(r'\D', '', p_val)[-2:]):02d}"
                c = f"{int(re.sub(r'\D', '', c_val)[-2:]):02d}"
                if p not in m_dict: m_dict[p] = set()
                m_dict[p].add(c)
        return m_dict.get(last_gdb_clean, set())
    except: return set()

# --- 3. BỘ NÃO TRINITY PHỄU LỌC ---
def thermal_ai_engines_v75(df_raw, history, db, mapping, n_bottom):
    if df_raw is None or df_raw.empty: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), []
    
    # Dàn A (Safe 79)
    df_safe_79 = df_raw.sort_values(['Điểm', 'Rank'], ascending=[False, True]).head(79)
    set_a = {f"{int(x):02d}" for x in df_safe_79['Số']}
    
    # Dàn B (Bottom 180)
    bottom_wires = sorted(db.items(), key=lambda x: x[1]['score'])[:n_bottom]
    set_b = {f"{int(mapping.get(str(w_id))):02d}" for w_id, d in bottom_wires if mapping.get(str(w_id))}
    
    # Dàn C (WireHist)
    set_c = get_wire_hist_set(history)

    results = []
    for i in range(100):
        num_str = f"{i:02d}"
        in_a, in_b, in_c = (num_str in set_a), (num_str in set_b), (num_str in set_c)
        match_count = sum([in_a, in_b, in_c])
        tags = []
        if in_a: tags.append("Safe")
        if in_b: tags.append("Bottom")
        if in_c: tags.append("Wire")
        
        row_raw = df_raw[df_raw['Số'] == num_str].iloc[0].to_dict()
        row_raw.update({'Match': int(match_count), 'Tags': "|".join(tags), 'in_safe': 1 if in_a else 0})
        results.append(row_raw)
    
    df_res = pd.DataFrame(results)
    # Ưu tiên theo PHỄU: in_safe (Safe làm gốc) -> Match (Giao điểm) -> Điểm
    df_sorted = df_res.sort_values(by=['in_safe', 'Match', 'Điểm'], ascending=[False, False, False])
    
    return df_sorted.head(39), df_sorted.head(59), df_sorted.head(79), df_res, list(set_b)

# --- 4. GIAO DIỆN & XỬ LÝ SỰ KIỆN ---
st.set_page_config(layout="wide", page_title="Matrix V13.75 ULTIMATE")
st.title("🛡️ Matrix V13.75 - Trinity Ultimate (Fix Match & History)")

if 'db' not in st.session_state: st.session_state['db'] = {}
if 'history' not in st.session_state: st.session_state['history'] = []
if 'last_full_str' not in st.session_state: st.session_state['last_full_str'] = ""

with st.sidebar:
    st.header("📂 DỮ LIỆU JSON")
    up_json = st.file_uploader("Nạp file", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json)
        st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', [])
        st.session_state['last_full_str'] = data.get('last_full_str', "")
        st.rerun()

    n_bottom_val = st.slider("Số lượng dây đáy (B):", 100, 300, 180)
    
    st.header("📸 NHẬP KẾT QUẢ")
    up_img = st.file_uploader("Quét ảnh", type=['jpg', 'png', 'jpeg'])
    if up_img and st.button("🚀 CHẠY OCR"):
        reader = load_ocr()
        res = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in res if n.isdigit() and 2 <= len(n) <= 5]
        if nums:
            st.session_state['raw_input'] = ", ".join(nums)
            st.session_state['gdb_val'] = nums[0][-2:]
            st.rerun()

    raw_input_area = st.text_area("Loto 27 giải:", value=st.session_state.get('raw_input', ""))
    gdb_input = st.text_input("GĐB (2 số cuối):", value=st.session_state.get('gdb_val', ""))

    if st.button("🔥 PHÂN TÍCH & LƯU KỲ MỚI"):
        raw_list = [x.strip() for x in raw_input_area.replace(",", " ").split() if x]
        if len(raw_list) >= 27 and gdb_input:
            mapping = get_mapping_v11(st.session_state['last_full_str'])
            # 1. Lưu lịch sử
            new_entry = {"STT": len(st.session_state['history']) + 1, "GĐB": gdb_input}
            st.session_state['history'].insert(0, new_entry)
            # 2. Cập nhật ma trận Score
            update_matrix_state(st.session_state['db'], [n[-2:] for n in raw_list[:27]], mapping)
            # 3. Lưu chuỗi 27 giải cho kỳ sau
            st.session_state['last_full_str'] = "".join(raw_list[:27])
            st.session_state['raw_input'] = ""
            st.session_state['gdb_val'] = ""
            st.success("Đã phân tích và lưu lịch sử!")
            st.rerun()

# --- 5. HIỂN THỊ KẾT QUẢ ---
if st.session_state['last_full_str']:
    def get_df_raw():
        db = st.session_state['db']
        mapping = get_mapping_v11(st.session_state['last_full_str'])
        stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "clean_wire_count": 0, "clean_window_hits": 0, "all_losses": []} for i in range(100)}
        for w_id, w_d in db.items():
            num = mapping.get(str(w_id))
            if num:
                s = stats[num]; sw, sl = int(w_d.get("streak_win", 0)), int(w_d.get("streak_loss", 0))
                s["all_losses"].append(sl if sw == 0 else 0)
                s["max_an"] = max(s["max_an"], sw)
                s["clean_window_hits"] += sum(w_d.get("hit_history", [])[-WINDOW:])
                if sw == 0: s["clean_wire_count"] += 1; s["total_score"] += float(w_d.get("score", 1000.0))
        res = []
        for num, s in stats.items():
            dc = max(1, s["clean_wire_count"])
            hard = round((s["clean_window_hits"] / (WINDOW * AVG_WIRES)) * 100, 2)
            score = round((s["total_score"] / dc) * (1 + hard/100), 2)
            res.append({"Số": num, "Điểm": score, "An": s["max_an"], "Tang": calculate_tier(s["all_losses"], 65), "DâySạch": s["clean_wire_count"], "Cứng(10k)": hard})
        df = pd.DataFrame(res).sort_values("Điểm", ascending=False).reset_index(drop=True)
        df["Rank"] = df.index + 1
        return df

    df_raw = get_df_raw()
    mapping = get_mapping_v11(st.session_state['last_full_str'])
    dk, da, ds, df_full, b_list = thermal_ai_engines_v75(df_raw, st.session_state['history'], st.session_state['db'], mapping, n_bottom_val)

    # Hiển thị
    c1, c2, c3 = st.columns(3)
    c1.metric("KẾT (39)", len(dk)); c2.metric("AI (59)", len(da)); c3.metric("SAFE (79)", len(ds))

    tab1, tab2, tab3 = st.tabs(["🎯 DÀN CHỐT", "📊 CHI TIẾT MATCH", "📜 LỊCH SỬ"])
    with tab1:
        st.write("🤖 **Dàn AI 59:**"); st.code(", ".join(da.sort_values("Số")["Số"].tolist()))
        st.write("🎯 **Dàn Kết 39:**"); st.code(", ".join(dk.sort_values("Số")["Số"].tolist()))
        st.write("🛡️ **Dàn Safe 79:**"); st.code(", ".join(ds.sort_values("Số")["Số"].tolist()))
    with tab2:
        st.dataframe(df_full.sort_values('Match', ascending=False), use_container_width=True, hide_index=True)
    with tab3:
        st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True, hide_index=True)

    st.download_button("💾 TẢI FILE JSON", data=json.dumps({"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state['last_full_str']}, ensure_ascii=False), file_name="matrix_v13_75_final.json")
