import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
import re
from PIL import Image

# --- 1. CÀI ĐẶT CƠ BẢN ---
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

# --- 2. BỘ NÃO TRUY VẾT DÂY BỆT (WIRE-TO-WIRE LINEAGE) ---

def get_wire_lineage_v2(db, history, mapping, n_top=180):
    """
    Dàn Bệt: Truy vết nổ gần nhất của từng dây để tìm hệ quả kỳ sau
    """
    if not history or not db: return set()
    
    try:
        # B1: Tìm con số GĐB kỳ vừa rồi
        last_gdb_raw = str(history[0].get('GĐB', "")).split()[0]
        last_gdb = f"{int(re.sub(r'\D', '', last_gdb_raw)[-2:]):02d}"
        
        # B2: Tập hợp các ID dây đã nổ con số này (Dây Cha)
        parent_wires = [w_id for w_id, d in db.items() if mapping.get(w_id) == last_gdb and d.get('streak_win', 0) > 0]
        
        if not parent_wires: return set()

        # B3: Truy vết lịch sử nổ gần nhất của từng Dây Cha
        wire_scores = {}
        
        # Giả lập truy vết (Trong thực tế, AI quét qua 11.449 dây và điểm Score/Hit History)
        # Vì file JSON chỉ lưu hit_history 10 kỳ gần nhất, AI sẽ quét trong phạm vi này
        for w_id in parent_wires:
            hit_hist = db[w_id].get('hit_history', [])
            # Tìm vị trí nổ gần nhất (số 1 cuối cùng trước kỳ hiện tại)
            # Giả sử hit_hist[-1] là kỳ vừa nổ, ta xem hit_hist của các dây khác
            for other_id, other_data in db.items():
                other_hist = other_data.get('hit_history', [])
                # Nếu dây 'other' nổ ngay sau khi dây 'w_id' nổ trong 10 kỳ qua
                for t in range(len(hit_hist)-1):
                    if hit_hist[t] == 1 and other_hist[t+1] == 1:
                        wire_scores[other_id] = wire_scores.get(other_id, 0) + 1

        # B4: Lấy 180 dây điểm cao nhất
        top_wires = sorted(wire_scores.items(), key=lambda x: x[1], reverse=True)[:n_top]
        
        # B5: Trích xuất ánh xạ số
        bet_nums = {mapping.get(w_id) for w_id, score in top_wires if mapping.get(w_id)}
        return {f"{int(x):02d}" for x in bet_nums if x}
    except:
        return set()

# --- 3. BỘ NÃO HỘI TỤ TRINITY V13.75 ---

def thermal_ai_engines_v75(df_raw, history, db, mapping, n_wire):
    if df_raw is None or df_raw.empty: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), [], [], pd.DataFrame()

    # Dàn A (Gốc): Safe 79
    df_safe_orig = df_raw.sort_values(['Điểm', 'Rank'], ascending=[False, True]).head(79)
    set_safe = {f"{int(x):02d}" for x in df_safe_orig['Số']}

    # Dàn B (Đáy): 180 dây điểm thấp nhất
    bottom_wires = sorted(db.items(), key=lambda x: x[1]['score'])[:n_wire]
    set_bottom = {f"{int(mapping.get(str(w_id))):02d}" for w_id, d in bottom_wires if mapping.get(str(w_id))}
    
    # Dàn C (Bệt): Wire-to-Wire Lineage
    set_bet = get_wire_lineage_v2(db, history, mapping, n_wire)

    # Chấm điểm giao điểm
    res_list = []
    for i in range(100):
        num_str = f"{i:02d}"
        in_s, in_b, in_t = (num_str in set_safe), (num_str in set_bottom), (num_str in set_bet)
        match_count = sum([in_s, in_b, in_t])
        
        tags = []
        if in_s: tags.append("Safe")
        if in_b: tags.append("Đáy")
        if in_t: tags.append("Bệt")
        
        row_find = df_raw[df_raw['Số'] == num_str].iloc[0].to_dict()
        row_find.update({'Match': match_count, 'Tags': "|".join(tags), 'is_safe': 1 if in_s else 0})
        res_list.append(row_find)

    df_res = pd.DataFrame(res_list)
    df_sorted = df_res.sort_values(by=['is_safe', 'Match', 'Điểm'], ascending=[False, False, False])

    return df_sorted.head(39), df_sorted.head(59), df_sorted.head(79), sorted(list(set_bottom)), sorted(list(set_bet)), df_res

# --- 4. GIAO DIỆN HIỂN THỊ (GIỮ NGUYÊN OCR VÀ CÁC Ô) ---
st.set_page_config(layout="wide", page_title="Matrix V13.75 Lineage")
st.title("🔥 Matrix V13.75 - Wire-to-Wire Lineage")

if 'db' not in st.session_state: st.session_state['db'] = {}
if 'history' not in st.session_state: st.session_state['history'] = []
if 'last_full_str' not in st.session_state: st.session_state['last_full_str'] = ""

with st.sidebar:
    st.header("📂 DỮ LIỆU")
    up_json = st.file_uploader("Nạp JSON", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json)
        st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', [])
        st.session_state['last_full_str'] = data.get('last_full_str', "")
        st.rerun()

    n_val = st.slider("Số lượng dây (Bệt/Đáy):", 100, 300, 180)
    
    st.header("📸 QUÉT KQ")
    up_img = st.file_uploader("Chọn ảnh kết quả", type=['jpg', 'png', 'jpeg'])
    if up_img and st.button("🚀 CHẠY OCR"):
        reader = load_ocr()
        res = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in res if n.isdigit() and 2 <= len(n) <= 5]
        if nums:
            st.session_state['raw_input'] = ", ".join(nums)
            st.session_state['gdb_val'] = nums[0][-2:]
            st.rerun()

    raw_input_val = st.text_area("Loto 27 giải:", value=st.session_state.get('raw_input', ""), height=100)
    gdb_input_val = st.text_input("GĐB:", value=st.session_state.get('gdb_val', ""))

    if st.button("🔥 PHÂN TÍCH & LƯU"):
        raw_list = [x.strip() for x in raw_input_val.replace(",", " ").split() if x]
        if len(raw_list) >= 27 and gdb_input_val:
            mapping = get_mapping_v11(st.session_state['last_full_str'])
            st.session_state['history'].insert(0, {"STT": len(st.session_state['history'])+1, "GĐB": gdb_input_val})
            update_matrix_state(st.session_state['db'], [n[-2:] for n in raw_list[:27]], mapping)
            st.session_state['last_full_str'] = "".join(raw_list[:27])
            st.rerun()

# --- HIỂN THỊ ---
if st.session_state['last_full_str']:
    # Hàm tính matrix thô
    def get_matrix_raw():
        db = st.session_state['db']; mapping = get_mapping_v11(st.session_state['last_full_str'])
        stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "clean_wire_count": 0, "clean_window_hits": 0, "all_losses": []} for i in range(100)}
        for w_id, w_d in db.items():
            num = mapping.get(str(w_id))
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

    df_raw_val = get_matrix_raw()
    mapping_val = get_mapping_v11(st.session_state['last_full_str'])
    dk, da, ds, dbottom, dbet, df_full = thermal_ai_engines_v75(df_raw_val, st.session_state['history'], st.session_state['db'], mapping_val, n_val)

    st.subheader("🛡️ HỆ THỐNG 5 DÀN SỐ V13.75")
    c1, c2, c3 = st.columns(3)
    with c1: st.success("🎯 Dàn Kết 39"); st.code(", ".join(dk.sort_values("Số")["Số"].tolist()))
    with c2: st.info("🤖 Dàn AI 59"); st.code(", ".join(da.sort_values("Số")["Số"].tolist()))
    with c3: st.warning("🛡️ Dàn An Toàn 79"); st.code(", ".join(ds.sort_values("Số")["Số"].tolist()))

    c4, c5 = st.columns(2)
    with c4: st.error("📉 Dàn 180 Dây Đáy (Điểm Nhỏ)"); st.code(", ".join(dbottom))
    with c5: st.error("📈 Dàn 180 Dây Bệt (Wire-to-Wire)"); st.code(", ".join(dbet))

    st.divider()
    t1, t2 = st.tabs(["📊 CHI TIẾT HỘI TỤ", "📜 LỊCH SỬ"])
    with t1: st.dataframe(df_full.sort_values(['Match', 'Điểm'], ascending=False), use_container_width=True, hide_index=True)
    with t2: st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True)

    st.download_button("💾 XUẤT JSON", data=json.dumps({"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state['last_full_str']}, ensure_ascii=False), file_name="matrix_v13_75.json")
