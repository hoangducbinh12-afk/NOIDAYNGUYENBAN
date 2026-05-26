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

# --- 2. BỘ NÃO AI V13.72: LINH HOẠT GIỮA AI VÀ LỌC TAY ---
def thermal_ai_engines(df_raw, ai_enabled=True, manual_filters=None):
    if df_raw is None or df_raw.empty: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    
    df_c = df_raw.copy()
    
    if ai_enabled:
        # LOGIC AI NÂNG CẤP
        def scoring(row):
            s = 0
            if row['An'] in [2, 3]: s += 5
            elif row['An'] == 4: s += 3
            elif row['An'] == 1: s += 2 
            if row['Tang'] in [2, 3]: s += 6
            elif row['Tang'] == 1: s += 4
            if 30 <= row['DâySạch'] <= 119: s += 2
            # Nới ngưỡng nhiệt cho Top Rank
            if row['Rank'] <= 15:
                if 9 <= row['Cứng(10k)'] <= 42: s += 5
            else:
                if 9 <= row['Cứng(10k)'] <= 29: s += 5
            return s
        
        df_c['AI_Score'] = df_c.apply(scoring, axis=1)
        # Khống chế quân số cứng
        df_ai = df_c.sort_values(['AI_Score', 'Rank'], ascending=[False, True]).head(59)
        df_ket = df_ai.head(39)
        df_safety = pd.concat([df_ai, df_c.sort_values('Rank').head(79)]).drop_duplicates().head(79)
        df_loai = df_c[~df_c['Số'].isin(df_safety['Số'])].sort_values('Rank', ascending=False).head(21)
    
    else:
        # LOGIC LỌC TAY (MANUAL)
        f = manual_filters
        df_filtered = df_c[
            (df_c['Rank'].between(f['rank'][0], f['rank'][1])) &
            (df_c['An'].between(f['an'][0], f['an'][1])) &
            (df_c['Tang'] >= f['tang_min']) &
            (df_c['Cứng(10k)'].between(f['hard'][0], f['hard'][1]))
        ].copy()
        
        df_ai = df_filtered.copy()
        df_ket = df_ai.head(39) if len(df_ai) > 39 else df_ai
        df_safety = df_ai.head(79) if len(df_ai) > 79 else df_ai
        df_loai = df_c[~df_c['Số'].isin(df_safety['Số'])].sort_values('Rank', ascending=False).head(21)

    return df_ket, df_ai, df_safety.reset_index(drop=True), df_loai

# --- 3. XỬ LÝ MA TRẬN ---
def process_matrix_v13_72():
    db = st.session_state.get('db', {})
    f_str = st.session_state.get('last_full_str', "")
    mapping = get_mapping_v11(f_str)
    stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "clean_wire_count": 0, "clean_window_hits": 0, "all_losses": []} for i in range(100)}
    for wire_id, w_data in db.items():
        num = mapping.get(str(wire_id))
        if num:
            s = stats[num]
            sw, sl = int(w_data.get("streak_win", 0)), int(w_data.get("streak_loss", 0))
            s["all_losses"].append(sl if sw == 0 else 0)
            if sw > s["max_an"]: s["max_an"] = sw
            s["clean_window_hits"] += sum(w_data.get("hit_history", [])[-WINDOW:])
            if sw == 0:
                s["clean_wire_count"] += 1
                s["total_score"] += float(w_data.get("score", 1000.0))
    res = []
    for num, s in stats.items():
        dc = s["clean_wire_count"] if s["clean_wire_count"] > 0 else 1
        hard = round((s["clean_window_hits"] / (WINDOW * AVG_WIRES)) * 100, 2)
        score = round((s["total_score"] / dc) * (1 + hard/100), 2)
        res.append({"Số": num, "Điểm": score, "An": s["max_an"], "Tang": calculate_tier(s["all_losses"], 65), "DâySạch": s["clean_wire_count"], "Cứng(10k)": hard})
    df = pd.DataFrame(res).sort_values("Điểm", ascending=False).reset_index(drop=True)
    df["Rank"] = df.index + 1
    st.session_state['df_raw'] = df
    return df

# --- 4. GIAO DIỆN ---
st.set_page_config(layout="wide", page_title="Matrix V13.72 Fixed")
st.markdown("<h1 style='text-align: center; color: red;'>Matrix V13.72 - Fix Lọc Tay & Siêu AI</h1>", unsafe_allow_html=True)

if 'db' not in st.session_state: st.session_state['db'] = {}
if 'history' not in st.session_state: st.session_state['history'] = []

with st.sidebar:
    st.header("📂 HỆ THỐNG")
    col1, col2 = st.columns(2)
    with col1: 
        if st.button("🚨 RESET"): st.session_state.clear(); st.rerun()
    with col2:
        if st.button("💎 KHỞI TẠO"):
            st.session_state['db'] = {str(i): {"score": 1000.0, "streak_win": 0, "streak_loss": 0, "hit_history": [0]*10} for i in range(11449)}
            st.session_state['last_full_str'] = ""; process_matrix_v13_72(); st.rerun()
    
    up_json = st.file_uploader("📥 Nạp JSON", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json); st.session_state['db'] = data.get('matrix', data); st.session_state['history'] = data.get('history', []); st.session_state['last_full_str'] = data.get('last_full_str', ""); process_matrix_v13_72(); st.rerun()
    
    st.divider()
    st.header("🧠 CHIẾN THUẬT")
    ai_on = st.toggle("AI Cân bằng nhiệt", value=True)
    m_filters = None
    if not ai_on:
        st.subheader("🕹️ LỌC TAY")
        f_rank = st.slider("Rank:", 0, 100, (11, 85))
        f_an = st.slider("An:", 0, 15, (0, 3))
        f_tang_min = st.slider("Tầng min:", 0, 10, 1)
        f_hard = st.slider("Cứng%:", 0.0, 100.0, (13.0, 45.0))
        m_filters = {'rank': f_rank, 'an': f_an, 'tang_min': f_tang_min, 'hard': f_hard}
        if st.button("✅ ÁP DỤNG BỘ LỌC"): process_matrix_v13_72(); st.rerun()

    st.header("📸 QUÉT KQ (OCR)")
    up_img = st.file_uploader("Chọn ảnh", type=['jpg', 'jpeg', 'png'])
    if up_img and st.button("🚀 CHẠY OCR"):
        reader = load_ocr(); results = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
        if nums: st.session_state['raw_input'] = ", ".join(nums); st.session_state['gdb_val'] = nums[0][-2:]; st.rerun()

    st.session_state['raw_input'] = st.text_area("27 giải loto:", value=st.session_state.get('raw_input', ""), height=80)
    st.session_state['gdb_val'] = st.text_input("GĐB:", value=st.session_state.get('gdb_val', ""), max_chars=2)
    
    if st.button("🔥 PHÂN TÍCH KỲ MỚI"):
        df_before = process_matrix_v13_72()
        dk, da, ds, dl = thermal_ai_engines(df_before, ai_enabled=ai_on, manual_filters=m_filters)
        raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
        if len(raw_list) >= 27:
            gv = st.session_state['gdb_val']; r_row = df_before[df_before['Số'] == gv].iloc[0] if gv in df_before['Số'].values else None
            g_p = f"{gv} (R{int(r_row['Rank'])}-A{int(r_row['An'])}-D{int(r_row['DâySạch'])}-T{int(r_row['Tang'])}-C{int(r_row['Cứng(10k)'])}%)" if r_row is not None else gv
            st.session_state['history'].insert(0, {
                "STT": len(st.session_state['history'])+1, "GĐB": g_p, 
                "Kết": "A" if gv in dk["Số"].tolist() else "T", 
                "Ai": "A" if gv in da["Số"].tolist() else "T", 
                "Safe": "A" if gv in ds["Số"].tolist() else "T",
                "AvgC": round(da['Cứng(10k)'].mean(), 2) if not da.empty else 0
            })
            update_matrix_state(st.session_state['db'], [n[-2:] for n in raw_list[:27]], get_mapping_v11(st.session_state.get('last_full_str', ""))); st.session_state['last_full_str'] = "".join(raw_list[:27]); process_matrix_v13_72(); st.rerun()

# --- 5. HIỂN THỊ CHÍNH ---
if st.session_state.get('df_raw') is not None:
    df_raw_cur = st.session_state['df_raw']
    dk, da, ds, dl = thermal_ai_engines(df_raw_cur, ai_enabled=ai_on, manual_filters=m_filters)
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: st.metric("KẾT", f"{len(dk)}")
    with col2: st.metric("AI", f"{len(da)}")
    with col3: st.metric("SAFE", f"{len(ds)}")
    with col4: st.metric("LOẠI", f"{len(dl)}")
    with col5: st.download_button("💾 JSON", data=json.dumps({"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state['last_full_str']}), file_name="matrix_v13_72.json")
    
    st.write("🎯 **Dàn Kết:**"); st.code(", ".join(dk.sort_values("Số")["Số"].tolist()))
    st.write("🤖 **Dàn Ai:**"); st.code(", ".join(da.sort_values("Số")["Số"].tolist()))
    st.write("🛡️ **Dàn An Toàn:**"); st.code(", ".join(ds.sort_values("Số")["Số"].tolist()))
    st.write("❌ **Dàn Loại:**"); st.code(", ".join(dl.sort_values("Số")["Số"].tolist()))
    
    st.divider()
    c_detail, c_hist = st.columns([1.5, 2.3])
    with c_detail: 
        st.subheader("🎯 CHI TIẾT DÀN"); st.dataframe(da, use_container_width=True, hide_index=True, height=750)
    with c_hist: 
        st.subheader("📜 LỊCH SỬ")
        h_df = pd.DataFrame(st.session_state['history'])
        if not h_df.empty:
            for col in ["STT", "GĐB", "Kết", "Ai", "Safe", "AvgC"]:
                if col not in h_df.columns: h_df[col] = "0"
            h_df = h_df[["STT", "GĐB", "Kết", "Ai", "Safe", "AvgC"]]
        st.dataframe(h_df, use_container_width=True, height=750)
