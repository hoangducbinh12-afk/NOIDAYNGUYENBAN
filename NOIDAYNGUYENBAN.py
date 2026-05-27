import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
import re
from PIL import Image

# --- 1. SETTINGS & OCR ---
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

def get_wire_lineage_v2(db, history, mapping, n_top_bet):
    if not history or not db or n_top_bet == 0: return set()
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

# --- 2. LOGIC HẠ DÀN (BẢO HIỂM T0 & A5) ---
def thermal_ai_engines_v75(df_raw, history, db, mapping, cfg):
    if df_raw is None or df_raw.empty: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), [], [], pd.DataFrame()
    
    # A. Vùng Đáy/Bệt
    set_bottom = set()
    if cfg['bot'] > 0:
        bottom_wires = sorted(db.items(), key=lambda x: x[1]['score'])[:cfg['bot']]
        set_bottom = {f"{int(mapping.get(str(w_id))):02d}" for w_id, d in bottom_wires if mapping.get(str(w_id))}
    set_bet = get_wire_lineage_v2(db, history, mapping, cfg['bet'])
    set_overlap = set_bottom.intersection(set_bet)
    
    # B. Gán nhãn các chỉ số đặc biệt
    df_raw['is_overlap'] = df_raw['Số'].isin(set_overlap).astype(int)
    df_raw['is_outside'] = (~df_raw['Số'].isin(set_bottom) & ~df_raw['Số'].isin(set_bet)).astype(int)
    df_raw['in_bet_wire'] = df_raw['Số'].isin(set_bet).astype(int)
    
    # Lõi kỹ thuật
    df_raw['core_39'] = ((df_raw['Tang'].isin([1, 2])) & (df_raw['An'].isin([2, 3])) & (df_raw['Cứng'] > 8.0)).astype(int)
    df_raw['core_59'] = ((df_raw['Tang'].isin([1, 2, 3])) & (df_raw['An'].isin([2, 3])) & (df_raw['Cứng'] > 8.0)).astype(int)
    # Lõi 79 nới lỏng để bao phủ
    df_raw['core_79'] = ((df_raw['Tang'].isin([0, 1, 2, 3])) & (df_raw['An'].isin([1, 2, 3, 4, 5])) & (df_raw['Cứng'] > 7.0)).astype(int)

    # C. CƠ CHẾ BẢO HIỂM (RISK SHIELD)
    # Thẻ bài miễn tử cho T=0 mà Rank cao (Top 10)
    df_raw['shield_T0'] = ((df_raw['Tang'] == 0) & (df_raw['Rank'] <= 10)).astype(int)
    # Thẻ bài miễn tử cho A=5 nằm trong Dây Bệt
    df_raw['shield_A5'] = ((df_raw['An'] >= 5) & (df_raw['in_bet_wire'] == 1)).astype(int)
    
    # D. LOGIC GỌT DÀN 79 CẢI TIẾN
    # Safety Score: Ưu tiên Shield (200đ) > Lõi 79 (100đ) > Outside (10đ) - Overlap (-50đ)
    df_raw['safety_score_79'] = (
        (df_raw['shield_T0'] * 200) + 
        (df_raw['shield_A5'] * 200) + 
        (df_raw['core_79'] * 100) + 
        (df_raw['is_outside'] * 10) - 
        (df_raw['is_overlap'] * 50)
    )
    
    ds_79 = df_raw.sort_values(by=['safety_score_79', 'Điểm'], ascending=[False, False]).head(79)
    set_79 = set(ds_79['Số'].tolist())
    df_raw['in_79'] = df_raw['Số'].isin(set_79).astype(int)

    # E. HẠ DÀN 59 & 39 (GIỮ NGUYÊN NESTING TRONG 79)
    df_raw['p_59'] = (df_raw['core_59'] * 20) + (df_raw['is_outside'] * 5)
    da_59 = df_raw[df_raw['in_79'] == 1].sort_values(by=['p_59', 'Điểm'], ascending=[False, False]).head(59)
    set_59 = set(da_59['Số'].tolist())
    df_raw['in_59'] = df_raw['Số'].isin(set_59).astype(int)

    df_raw['p_39'] = (df_raw['core_39'] * 20) + (df_raw['is_outside'] * 5)
    dk_39 = df_raw[df_raw['in_59'] == 1].sort_values(by=['p_39', 'Điểm'], ascending=[False, False]).head(39)
    
    return dk_39, da_59, ds_79, sorted(list(set_bottom)), sorted(list(set_bet)), df_raw

# --- 3. UI ---
st.set_page_config(layout="wide", page_title="Matrix Risk Shield")
st.title("🛡️ Matrix V13.75 - Risk Shield (T0 & A5 Fix)")

if 'cfg' not in st.session_state:
    st.session_state['cfg'] = {"tier": 68, "win": 10, "hard": 7.99, "bot": 40, "bet": 40}
if 'db' not in st.session_state: st.session_state['db'] = {}
if 'history' not in st.session_state: st.session_state['history'] = []
if 'last_full_str' not in st.session_state: st.session_state['last_full_str'] = ""
if 'prev_sets' not in st.session_state: st.session_state['prev_sets'] = {}

with st.sidebar:
    if st.button("🚨 RESET ALL", use_container_width=True): st.session_state.clear(); st.rerun()
    st.header("📂 1. DỮ LIỆU")
    up_json = st.file_uploader("Nạp JSON", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json)
        st.session_state['db'], st.session_state['history'] = data.get('matrix', data), data.get('history', [])
        st.session_state['last_full_str'] = data.get('last_full_str', ""); st.rerun()

    st.header("📸 2. QUÉT KQ")
    up_img = st.file_uploader("Ảnh KQ", type=['jpg', 'png', 'jpeg'])
    if up_img and st.button("🚀 CHẠY OCR"):
        reader = load_ocr()
        res_ocr = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in res_ocr if n.isdigit() and 2 <= len(n) <= 5]
        if nums: st.session_state['raw_input'], st.session_state['gdb_val'] = ", ".join(nums), nums[0][-2:]; st.rerun()

    st.divider()
    if st.button("🔥 PHÂN TÍCH & LƯU", type="primary", use_container_width=True):
        raw_val, gdb_val = st.session_state.get('raw_input', ""), st.session_state.get('gdb_val', "")
        raw_list = [x.strip() for x in raw_val.replace(",", " ").split() if x]
        if len(raw_list) >= 27 and gdb_val:
            mapping = get_mapping_v11(st.session_state['last_full_str'])
            gdb_num = f"{int(re.sub(r'\D', '', gdb_val)[-2:]):02d}"
            p = st.session_state.get('prev_sets', {})
            check = lambda d: "A" if gdb_num in (d or []) else "T"
            st.session_state['history'].insert(0, {
                "STT": len(st.session_state['history']) + 1, "GĐB": gdb_val,
                "Dan39": check(p.get('d39')), "Dan59": check(p.get('d59')), "Dan79": check(p.get('d79')),
                "180thap": check(p.get('dthap')), "180cao": check(p.get('dcao'))
            })
            update_matrix_state(st.session_state['db'], [n[-2:] for n in raw_list[:27]], mapping)
            st.session_state['last_full_str'] = "".join(raw_list[:27]); st.rerun()

    st.header("⚙️ 4. BỘ LỌC")
    st.session_state['cfg']['tier'] = st.slider("Tầng (%):", 50, 80, 68)
    st.session_state['cfg']['win'] = st.slider("Kỳ:", 5, 20, 10)
    st.session_state['cfg']['hard'] = st.slider("Cứng (C%):", 0.0, 15.0, 7.99)
    st.session_state['cfg']['bot'] = st.slider("Đáy:", 0, 350, 40)
    st.session_state['cfg']['bet'] = st.slider("Bệt:", 0, 350, 40)

# --- 4. DISPLAY ---
if st.session_state['last_full_str']:
    def get_matrix_df(t_val, w_val):
        db, mapping = st.session_state['db'], get_mapping_v11(st.session_state['last_full_str'])
        stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "clean_wire_count": 0, "clean_window_hits": 0, "all_losses": []} for i in range(100)}
        for w_id, w_d in db.items():
            num = mapping.get(str(w_id))
            if num:
                s = stats[num]; sw, sl = int(w_d.get("streak_win", 0)), int(w_d.get("streak_loss", 0))
                s["all_losses"].append(sl if sw == 0 else 0); s["max_an"] = max(s["max_an"], sw)
                s["clean_window_hits"] += sum(w_d.get("hit_history", [])[-w_val:])
                if sw == 0: s["clean_wire_count"] += 1; s["total_score"] += float(w_d.get("score", 1000.0))
        res = []
        for num, s in stats.items():
            dc = max(1, s["clean_wire_count"]); hard = round((s["clean_window_hits"] / (w_val * (11449/100))) * 100, 2)
            score = round((s["total_score"] / dc) * (1 + hard/100), 2)
            res.append({"Số": num, "Điểm": score, "Tang": calculate_tier(s["all_losses"], t_val), "An": s["max_an"], "DâySạch": s["clean_wire_count"], "Cứng": hard})
        df = pd.DataFrame(res).sort_values("Điểm", ascending=False).reset_index(drop=True)
        df["Rank"] = df.index + 1
        return df

    df_raw_val = get_matrix_df(st.session_state['cfg']['tier'], st.session_state['cfg']['win'])
    dk, da, ds, d_thap, d_cao, df_full = thermal_ai_engines_v75(df_raw_val, st.session_state['history'], st.session_state['db'], get_mapping_v11(st.session_state['last_full_str']), st.session_state['cfg'])
    
    st.session_state['prev_sets'] = {'d39': dk["Số"].tolist(), 'd59': da["Số"].tolist(), 'd79': ds["Số"].tolist(), 'dthap': d_thap, 'dcao': d_cao}

    c1, c2, c3 = st.columns(3)
    c1.success(f"🎯 Kết 39 ({len(dk)})\nLõi T1,2 A2,3 Outside"); c1.code(", ".join(dk["Số"].tolist()))
    c2.info(f"🤖 AI 59 ({len(da)})\nNested in 79 + Core 59"); c2.code(", ".join(da["Số"].tolist()))
    c3.warning(f"🛡️ Safe 79 ({len(ds)})\nRisk Shield T0-A5 Active"); c3.code(", ".join(ds["Số"].tolist()))
    
    st.divider()
    t1, t2 = st.tabs(["📜 LỊCH SỬ ĂN/TRƯỢT", "📊 CHI TIẾT RISK SHIELD"])
    with t1:
        if st.session_state['history']:
            df_hist = pd.DataFrame(st.session_state['history'])
            cols = ["STT", "GĐB", "Dan39", "Dan59", "Dan79", "180thap", "180cao"]
            for c in cols: 
                if c not in df_hist.columns: df_hist[c] = "T"
            st.dataframe(df_hist[cols], use_container_width=True, hide_index=True)
    with t2:
        # Hiển thị các cột bảo hiểm để mày theo dõi
        st.dataframe(df_full.sort_values(by=['safety_score_79', 'Điểm'], ascending=[False, False]), use_container_width=True, hide_index=True)

    st.download_button("💾 LƯU JSON", data=json.dumps({"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state['last_full_str']}, ensure_ascii=False), file_name="matrix_risk_shield.json", use_container_width=True)
