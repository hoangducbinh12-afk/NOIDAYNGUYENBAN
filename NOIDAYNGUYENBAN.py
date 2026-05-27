import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
import re
from PIL import Image

# --- 1. SETTINGS & OCR (KHÔI PHỤC) ---
@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'])

def get_mapping_v11(full_str, total_pos=107):
    if not full_str or len(full_str) < total_pos:
        return {str(i): f"{i % 100:02d}" for i in range(11449)}
    return {str(i * total_pos + j): f"{full_str[i]}{full_str[j]}" for i in range(total_pos) for j in range(total_pos)}

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
            hist = w_data.get("hit_history", [0]*20)
            hist.append(1); w_data["hit_history"] = hist[-20:]
        else:
            w_data["streak_loss"] = w_data.get("streak_loss", 0) + 1
            w_data["streak_win"] = 0
            w_data["score"] = w_data.get("score", 1000.0) + 1.0
            hist = w_data.get("hit_history", [0]*20)
            hist.append(0); w_data["hit_history"] = hist[-20:]

# --- 2. LOGIC TRUY VẾT DÂY BỆT ---
def get_wire_lineage_v2(db, history, mapping, n_top_bet):
    if not history or not db: return set()
    try:
        last_gdb_raw = str(history[0].get('GĐB', "")).split()[0]
        last_gdb = f"{int(re.sub(r'\D', '', last_gdb_raw)[-2:]):02d}"
        parent_wires = [w_id for w_id, d in db.items() if mapping.get(w_id) == last_gdb and d.get('streak_win', 0) > 0]
        if not parent_wires: return set()
        wire_scores = {}
        for w_id in parent_wires:
            hit_hist = db[w_id].get('hit_history', [])
            for other_id, other_data in db.items():
                other_hist = other_data.get('hit_history', [])
                for t in range(len(hit_hist)-1):
                    if hit_hist[t] == 1 and other_hist[t+1] == 1:
                        wire_scores[other_id] = wire_scores.get(other_id, 0) + 1
        top_wires = sorted(wire_scores.items(), key=lambda x: x[1], reverse=True)[:n_top_bet]
        return {f"{int(mapping.get(w_id)):02d}" for w_id, score in top_wires if mapping.get(w_id)}
    except: return set()

# --- 3. PHỄU LỌC TRINITY ---
def thermal_ai_engines_v75(df_raw, history, db, mapping, n_bottom, n_bet, hard_threshold):
    if df_raw is None or df_raw.empty: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), [], [], pd.DataFrame()
    df_safe_orig = df_raw[df_raw['Cứng'] >= hard_threshold].sort_values(['Điểm', 'Rank'], ascending=[False, True]).head(79)
    if len(df_safe_orig) < 79:
        df_safe_orig = df_raw.sort_values(['Điểm', 'Rank'], ascending=[False, True]).head(79)
    set_safe = {f"{int(x):02d}" for x in df_safe_orig['Số']}
    set_bottom = {f"{int(mapping.get(str(w_id))):02d}" for w_id, d in sorted(db.items(), key=lambda x: x[1]['score'])[:n_bottom] if mapping.get(str(w_id))}
    set_bet = get_wire_lineage_v2(db, history, mapping, n_bet)
    res_list = []
    for i in range(100):
        num_str = f"{i:02d}"
        in_s, in_b, in_t = (num_str in set_safe), (num_str in set_bottom), (num_str in set_bet)
        row = df_raw[df_raw['Số'] == num_str].iloc[0].to_dict()
        row.update({'Match': int(sum([in_s, in_b, in_t])), 'Tags': f"{'S' if in_s else ''}{'B' if in_b else ''}{'T' if in_t else ''}", 'in_safe': 1 if in_s else 0})
        res_list.append(row)
    df_res = pd.DataFrame(res_list)
    df_sorted = df_res.sort_values(by=['in_safe', 'Match', 'Điểm'], ascending=[False, False, False])
    return df_sorted.head(39), df_sorted.head(59), df_sorted.head(79), sorted(list(set_bottom)), sorted(list(set_bet)), df_res

# --- 4. GIAO DIỆN (ĐẦY ĐỦ Ô LOAD ẢNH) ---
st.set_page_config(layout="wide", page_title="Matrix Final Perfect")
st.title("🛡️ Matrix V13.75 - Final Perfect Edition")

if 'db' not in st.session_state: st.session_state['db'] = {}
if 'history' not in st.session_state: st.session_state['history'] = []
if 'last_full_str' not in st.session_state: st.session_state['last_full_str'] = ""
if 'prev_sets' not in st.session_state: st.session_state['prev_sets'] = {}

with st.sidebar:
    st.header("📂 DỮ LIỆU")
    up_json = st.file_uploader("Nạp JSON", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json)
        st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', [])
        st.session_state['last_full_str'] = data.get('last_full_str', "")
        st.rerun()

    st.header("📸 QUÉT KQ")
    up_img = st.file_uploader("Chọn ảnh kết quả", type=['jpg', 'png', 'jpeg'])
    if up_img and st.button("🚀 CHẠY OCR"):
        reader = load_ocr()
        res_ocr = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums_ocr = [n for n in res_ocr if n.isdigit() and 2 <= len(n) <= 5]
        if nums_ocr:
            st.session_state['raw_input'] = ", ".join(nums_ocr)
            st.session_state['gdb_val'] = nums_ocr[0][-2:]
            st.rerun()

    st.header("⚙️ CHỈ SỐ")
    val_tier = st.slider("Mật độ Tầng (%):", 50, 80, 65)
    val_window = st.slider("Window soi (Kỳ):", 5, 20, 10)
    val_hard = st.slider("Ngưỡng Cứng (C%):", 0.0, 15.0, 8.0)
    n_bottom_val = st.slider("Dây ĐÁY:", 50, 500, 180)
    n_bet_val = st.slider("Dây BỆT:", 50, 500, 180)
    
    st.header("📝 NHẬP KQ")
    raw_input_area = st.text_area("27 giải:", value=st.session_state.get('raw_input', ""), height=80)
    gdb_input = st.text_input("GĐB (Full):", value=st.session_state.get('gdb_val', ""))

    if st.button("🔥 PHÂN TÍCH & LƯU"):
        raw_list = [x.strip() for x in raw_input_area.replace(",", " ").split() if x]
        if len(raw_list) >= 27 and gdb_input:
            mapping = get_mapping_v11(st.session_state['last_full_str'])
            gdb_num = f"{int(re.sub(r'\D', '', gdb_input)[-2:]):02d}"
            p = st.session_state.get('prev_sets', {})
            check = lambda d: "A" if gdb_num in (d or []) else "T"
            st.session_state['history'].insert(0, {
                "STT": len(st.session_state['history']) + 1, "GĐB": gdb_input, 
                "Dan39": check(p.get('d39')), "Dan59": check(p.get('d59')), 
                "Dan79": check(p.get('d79')), "180thap": check(p.get('dthap')), "180cao": check(p.get('dcao'))
            })
            update_matrix_state(st.session_state['db'], [n[-2:] for n in raw_list[:27]], mapping)
            st.session_state['last_full_str'] = "".join(raw_list[:27]); st.rerun()

# --- 5. HIỂN THỊ ---
if st.session_state['last_full_str']:
    def get_matrix_df(t_val, w_val):
        db = st.session_state['db']; mapping = get_mapping_v11(st.session_state['last_full_str'])
        stats = {f"{i:02d}": {"total_score": 0.0, "clean_wire_count": 0, "clean_window_hits": 0, "all_losses": []} for i in range(100)}
        for w_id, w_d in db.items():
            num = mapping.get(str(w_id))
            if num:
                s = stats[num]; sw, sl = int(w_d.get("streak_win", 0)), int(w_d.get("streak_loss", 0))
                s["all_losses"].append(sl if sw == 0 else 0)
                s["clean_window_hits"] += sum(w_d.get("hit_history", [])[-w_val:])
                if sw == 0: s["clean_wire_count"] += 1; s["total_score"] += float(w_d.get("score", 1000.0))
        res = []
        for num, s in stats.items():
            dc = max(1, s["clean_wire_count"])
            hard = round((s["clean_window_hits"] / (w_val * (11449/100))) * 100, 2)
            score = round((s["total_score"] / dc) * (1 + hard/100), 2)
            res.append({"Số": num, "Điểm": score, "Tang": calculate_tier(s["all_losses"], t_val), "DâySạch": s["clean_wire_count"], "Cứng": hard, "Rank": 0})
        df = pd.DataFrame(res).sort_values("Điểm", ascending=False).reset_index(drop=True)
        df["Rank"] = df.index + 1
        return df

    df_raw_val = get_matrix_df(val_tier, val_window)
    mapping_v = get_mapping_v11(st.session_state['last_full_str'])
    dk, da, ds, d_thap, d_cao, df_full = thermal_ai_engines_v75(df_raw_val, st.session_state['history'], st.session_state['db'], mapping_v, n_bottom_val, n_bet_val, val_hard)
    st.session_state['prev_sets'] = {'d39': dk["Số"].tolist(), 'd59': da["Số"].tolist(), 'd79': ds["Số"].tolist(), 'dthap': d_thap, 'dcao': d_cao}

    st.subheader("🛡️ HỆ THỐNG DÀN SỐ")
    c1, c2, c3 = st.columns(3)
    c1.success(f"🎯 Kết 39 ({len(dk)})"); c1.code(", ".join(dk["Số"].tolist()))
    c2.info(f"🤖 AI 59 ({len(da)})"); c2.code(", ".join(da["Số"].tolist()))
    c3.warning(f"🛡️ Safe 79 ({len(ds)})"); c3.code(", ".join(ds["Số"].tolist()))
    c4, c5 = st.columns(2)
    c4.error(f"📉 Đáy {n_bottom_val} ({len(d_thap)})"); c4.code(", ".join(d_thap))
    c5.error(f"📈 Bệt {n_bet_val} ({len(d_cao)})"); c5.code(", ".join(d_cao))

    st.divider()
    t1, t2 = st.tabs(["📜 LỊCH SỬ", "📊 CHI TIẾT"])
    with t1:
        if st.session_state['history']:
            df_hist = pd.DataFrame(st.session_state['history'])
            req_cols = ["STT", "GĐB", "Dan39", "Dan59", "Dan79", "180thap", "180cao"]
            for col in req_cols:
                if col not in df_hist.columns: df_hist[col] = "T"
            st.dataframe(df_hist[req_cols], use_container_width=True, hide_index=True)
    with t2:
        st.dataframe(df_full.sort_values(['Match', 'Điểm'], ascending=False), use_container_width=True, hide_index=True)

    st.download_button("💾 LƯU JSON", data=json.dumps({"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state['last_full_str']}, ensure_ascii=False), file_name="matrix_final.json")
