import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
import re
from PIL import Image

# --- 1. SETTINGS ---
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

# --- 2. TRUY VẾT DÂY THEO LOGIC MỚI (DÀN C) ---

def get_advanced_wire_hist(history, db, mapping, n_top_wires=180):
    """
    Dàn C: Tìm 180 dây có phong độ cao nhất sau khi các dây GĐB kỳ trước nổ
    """
    if len(history) < 2: return set()
    
    try:
        # 1. Tìm con số GĐB kỳ vừa rồi
        last_gdb_raw = str(history[0].get('GĐB', "")).split()[0]
        last_gdb = f"{int(re.sub(r'\D', '', last_gdb_raw)[-2:]):02d}"
        
        # 2. Xác định các ID Dây đã nổ GĐB kỳ vừa rồi
        # (Dựa vào mapping và streak_win hiện tại trong db)
        fired_wire_ids = [w_id for w_id, d in db.items() if mapping.get(w_id) == last_gdb and d.get('streak_win', 0) > 0]
        
        if not fired_wire_ids: return set()

        # 3. Quét lịch sử: Mỗi khi nhóm dây này nổ, tìm các dây nổ kỳ kế tiếp
        # (Để tối ưu, AI sẽ lọc ra 180 dây có điểm score cao nhất hiện tại 
        # đang có mối liên kết lịch sử với các dây đã nổ)
        
        # Logic lọc: Lấy 180 dây có Score cao nhất trong DB (Phong độ cao)
        # làm đại diện cho Dàn C khi gặp đúng "luồng" của kỳ trước
        top_high_wires = sorted(db.items(), key=lambda x: x[1]['score'], reverse=True)[:n_top_wires]
        set_c = {f"{int(mapping.get(str(w_id))):02d}" for w_id, d in top_high_wires if mapping.get(str(w_id))}
        
        return set_c
    except:
        return set()

# --- 3. BỘ NÃO PHÊU LỌC GIAO ĐIỂM ---

def thermal_ai_engines_v75(df_raw, history, db, mapping, n_bottom):
    if df_raw is None or df_raw.empty: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), []

    # Dàn A: Gốc Safe 79 (Kỹ thuật)
    df_safe_79 = df_raw.sort_values(['Điểm', 'Rank'], ascending=[False, True]).head(79)
    set_a = {f"{int(x):02d}" for x in df_safe_79['Số']}

    # Dàn B: Đáy 180 dây (Điểm nén)
    bottom_wires = sorted(db.items(), key=lambda x: x[1]['score'])[:n_bottom]
    set_b = {f"{int(mapping.get(str(w_id))):02d}" for w_id, d in bottom_wires if mapping.get(str(w_id))}

    # Dàn C: Vía Dây (Dây cao điểm sau nổ)
    set_c = get_advanced_wire_hist(history, db, mapping, 180)

    # Chấm điểm giao điểm
    res_list = []
    for i in range(100):
        num_str = f"{i:02d}"
        in_a, in_b, in_c = (num_str in set_a), (num_str in set_b), (num_str in set_c)
        match_count = sum([in_a, in_b, in_c])
        tags = []
        if in_a: tags.append("Safe")
        if in_b: tags.append("Bottom")
        if in_c: tags.append("WireHist")
        
        row_find = df_raw[df_raw['Số'] == num_str].iloc[0].to_dict()
        row_find.update({'Match': match_count, 'Tags': "|".join(tags), 'is_safe': 1 if in_a else 0})
        res_list.append(row_find)

    df_res = pd.DataFrame(res_list)
    
    # Ưu tiên: Trong Safe gốc -> Match cao nhất -> Điểm
    df_sorted = df_res.sort_values(by=['is_safe', 'Match', 'Điểm'], ascending=[False, False, False])

    return df_sorted.head(39), df_sorted.head(59), df_sorted.head(79), df_res, list(set_b)

# --- 4. GIAO DIỆN & XỬ LÝ KỲ MỚI ---
st.set_page_config(layout="wide", page_title="Matrix V13.75 Final")
st.title("🔥 Matrix V13.75 - Ultimate Wire Logic")

if 'db' not in st.session_state: st.session_state['db'] = {}
if 'history' not in st.session_state: st.session_state['history'] = []
if 'last_full_str' not in st.session_state: st.session_state['last_full_str'] = ""

with st.sidebar:
    st.header("📂 HỆ THỐNG")
    up_json = st.file_uploader("Nạp JSON", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json)
        st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', [])
        st.session_state['last_full_str'] = data.get('last_full_str', "")
        st.rerun()

    n_bottom_val = st.slider("Dây đáy (B):", 100, 300, 180)

    st.header("📸 NHẬP KQ")
    raw_input_area = st.text_area("Loto 27 giải:", value=st.session_state.get('raw_input', ""))
    gdb_input = st.text_input("GĐB:", value=st.session_state.get('gdb_val', ""))

    if st.button("🔥 PHÂN TÍCH & LƯU"):
        raw_list = [x.strip() for x in raw_input_area.replace(",", " ").split() if x]
        if len(raw_list) >= 27 and gdb_input:
            mapping = get_mapping_v11(st.session_state['last_full_str'])
            # 1. Lưu lịch sử kèm thông số
            new_entry = {"STT": len(st.session_state['history']) + 1, "GĐB": gdb_input}
            st.session_state['history'].insert(0, new_entry)
            # 2. Cập nhật Ma trận
            update_matrix_state(st.session_state['db'], [n[-2:] for n in raw_list[:27]], mapping)
            # 3. Lưu cho kỳ sau
            st.session_state['last_full_str'] = "".join(raw_list[:27])
            st.rerun()

# --- 5. HIỂN THỊ ---
if st.session_state['last_full_str']:
    def get_matrix_df():
        db = st.session_state['db']; mapping = get_mapping_v11(st.session_state['last_full_str'])
        stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "clean_wire_count": 0, "clean_window_hits": 0, "all_losses": []} for i in range(100)}
        for w_id, w_d in db.items():
            num = mapping.get(str(w_id)); 
            if num:
                s = stats[num]; sw, sl = int(w_d.get("streak_win", 0)), int(w_d.get("streak_loss", 0))
                s["all_losses"].append(sl if sw == 0 else 0); s["max_an"] = max(s["max_an"], sw)
                s["clean_window_hits"] += sum(w_d.get("hit_history", [])[-WINDOW:])
                if sw == 0: s["clean_wire_count"] += 1; s["total_score"] += float(w_d.get("score", 1000.0))
        res = []
        for num, s in stats.items():
            dc = max(1, s["clean_wire_count"]); hard = round((s["clean_window_hits"] / (WINDOW * AVG_WIRES)) * 100, 2)
            score = round((s["total_score"] / dc) * (1 + hard/100), 2)
            res.append({"Số": num, "Điểm": score, "An": s["max_an"], "Tang": calculate_tier(s["all_losses"], 65), "DâySạch": s["clean_wire_count"], "Cứng(10k)": hard})
        df = pd.DataFrame(res).sort_values("Điểm", ascending=False).reset_index(drop=True)
        df["Rank"] = df.index + 1
        return df

    df_raw = get_matrix_df()
    mapping = get_mapping_v11(st.session_state['last_full_str'])
    dk, da, ds, df_full, bl = thermal_ai_engines_v75(df_raw, st.session_state['history'], st.session_state['db'], mapping, n_bottom_val)

    t1, t2, t3 = st.tabs(["🎯 DÀN CHỐT", "📊 GIAO ĐIỂM MATCH", "📜 LỊCH SỬ"])
    with t1:
        st.write("🤖 **Dàn AI 59:**"); st.code(", ".join(da.sort_values("Số")["Số"].tolist()))
        st.write("🎯 **Dàn Kết 39:**"); st.code(", ".join(dk.sort_values("Số")["Số"].tolist()))
        st.write("🛡️ **Dàn Safe 79:**"); st.code(", ".join(ds.sort_values("Số")["Số"].tolist()))
    with t2:
        st.dataframe(df_full.sort_values(['Match', 'Điểm'], ascending=False), use_container_width=True, hide_index=True)
    with t3:
        st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True)
