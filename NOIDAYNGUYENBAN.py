import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
from PIL import Image

# --- 1. CẤU HÌNH HỆ THỐNG & OCR ---
TOTAL_POS = 107 
AVG_WIRES = 114.5
WINDOW = 10 

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'])

def get_mapping_v11(full_str):
    if not full_str or len(full_str) < TOTAL_POS: return None
    return {str(i * TOTAL_POS + j): f"{full_str[i]}{full_str[j]}" for i in range(TOTAL_POS) for j in range(TOTAL_POS)}

def calculate_tier(losses, threshold_pct):
    if not losses: return 0
    losses_sorted = sorted(losses, reverse=True)
    idx = int(len(losses_sorted) * (threshold_pct / 100)) - 1
    return losses_sorted[max(0, idx)]

# --- 2. BỘ NÃO AI: THERMAL CORE (1,2,3) ---
def get_thermal_ai_set(df_raw):
    if df_raw is None or df_raw.empty: return pd.DataFrame()
    def scoring(row):
        s = 0
        if row['An'] in [2, 3]: s += 5
        elif row['An'] == 4: s += 3
        elif row['An'] in [0, 1]: s += 2
        if row['Tang'] in [1, 2, 3]: s += 5
        elif row['Tang'] > 3: s += 4
        if 30 <= row['DâySạch'] <= 119: s += 2
        elif row['DâySạch'] >= 120: s += 1
        if 9 <= row['Cứng(10k)'] <= 29: s += 5
        elif row['Cứng(10k)'] >= 30: s += 4
        return s
    
    df_copy = df_raw.copy()
    df_copy['AI_Score'] = df_copy.apply(scoring, axis=1)
    core_df = df_copy[df_copy['AI_Score'] == 17].copy()
    rem_df = df_copy[df_copy['AI_Score'] < 17].sort_values(['AI_Score', 'Điểm'], ascending=[False, False]).copy()
    
    final_df = core_df.copy()
    for _, row in rem_df.iterrows():
        if len(final_df) >= 59: break
        curr_avg = final_df['Cứng(10k)'].mean() if not final_df.empty else 24.0
        if curr_avg > 25.5:
            if row['Cứng(10k)'] < curr_avg: final_df = pd.concat([final_df, pd.DataFrame([row])])
        elif curr_avg < 22.5:
            if row['Cứng(10k)'] > curr_avg: final_df = pd.concat([final_df, pd.DataFrame([row])])
        else:
            final_df = pd.concat([final_df, pd.DataFrame([row])])
            
    while len(final_df) > 59 or (len(final_df) > 50 and (final_df['Cứng(10k)'].mean() < 20 or final_df['Cứng(10k)'].mean() > 28)):
        final_df = final_df.sort_values(['AI_Score', 'Điểm'], ascending=[True, True]).iloc[1:]
    return final_df

# --- 3. XỬ LÝ MA TRẬN (ĐỒNG BỘ JSON - FIX LỖI VỀ 0) ---
def process_matrix_v13_41():
    full_str = st.session_state.get('last_full_str', "0"*107)
    db = st.session_state.get('db', {})
    if not db: return None
    current_map = get_mapping_v11(full_str)
    
    # Khởi tạo stats dựa trên cấu hình JSON
    stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "clean_wire_count": 0, "clean_window_hits": 0, "all_losses": []} for i in range(100)}
    
    for wire_id, num in current_map.items():
        wire_data = db.get(str(wire_id))
        if not wire_data: continue
        
        s = stats[num]
        swin = int(wire_data.get("streak_win", 0))
        sloss = int(wire_data.get("streak_loss", 0))
        
        # Đồng bộ logic An và Tầng
        s["all_losses"].append(sloss if swin == 0 else 0)
        if swin > s["max_an"]: s["max_an"] = swin
        
        # Đồng bộ logic Cứng (hit_history)
        h_hist = wire_data.get("hit_history", [])
        s["clean_window_hits"] += sum(h_hist[-WINDOW:]) if h_hist else 0
        
        # Đồng bộ Dây và Điểm
        if swin == 0:
            s["clean_wire_count"] += 1
            s["total_score"] += float(wire_data.get("score", 1000.0))

    data_list = []
    for num, s in stats.items():
        c_count = s["clean_wire_count"] if s["clean_wire_count"] > 0 else 1
        do_cung = round((s["clean_window_hits"] / (WINDOW * AVG_WIRES)) * 100, 2)
        final_score = round((s["total_score"] / c_count) * (1 + do_cung/100), 2)
        data_list.append({
            "Số": num, "Điểm": final_score, "An": s["max_an"], 
            "Tang": calculate_tier(s["all_losses"], 65),
            "DâySạch": s["clean_wire_count"], "Cứng(10k)": do_cung
        })
    
    df = pd.DataFrame(data_list).sort_values("Điểm", ascending=False).reset_index(drop=True)
    df["Rank"] = df.index + 1
    st.session_state['df_raw'] = df
    return df

# --- 4. GIAO DIỆN (PHỤC HỒI NGUYÊN BẢN V13.21) ---
st.set_page_config(layout="wide", page_title="Matrix V13.41 Sync JSON")
st.markdown("<h1 style='text-align: center; color: red;'>Matrix V13.41 - JSON Sync Display</h1>", unsafe_allow_html=True)

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
            st.session_state['history'] = []; st.session_state['last_full_str'] = "0" * 107
            process_matrix_v13_41(); st.rerun()

    up_json = st.file_uploader("📥 Nạp JSON (Sử dụng cấu trúc V13.20)", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json)
        st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', [])
        st.session_state['last_full_str'] = data.get('last_full_str', "0"*107)
        process_matrix_v13_41(); st.rerun()

    st.divider()
    st.header("🧠 CHIẾN THUẬT AI")
    ai_on = st.toggle("Kích hoạt AI Cân bằng nhiệt", value=True)
    
    if not ai_on:
        f_rank = st.slider("Rank:", 0, 100, (0, 99))
        f_an = st.slider("An thông:", 0, 15, (0, 4))
        f_tang_min = st.slider("Tầng tối thiểu:", 0, 10, 1)
        f_hard = st.slider("Cứng%:", 0.0, 100.0, (8.0, 55.0))
        if st.button("✅ CHỐT DÀN TAY"): process_matrix_v13_41(); st.rerun()

    st.header("📸 QUÉT KQ")
    up_img = st.file_uploader("Chọn ảnh", type=['jpg', 'jpeg', 'png'])
    if up_img and st.button("🚀 OCR"):
        reader = load_ocr(); results = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
        if nums: st.session_state['raw_input'] = ", ".join(nums); st.session_state['gdb_val'] = nums[0][-2:]; st.rerun()

    st.session_state['raw_input'] = st.text_area("27 giải loto:", value=st.session_state.get('raw_input', ""), height=80)
    st.session_state['gdb_val'] = st.text_input("GĐB:", value=st.session_state.get('gdb_val', ""), max_chars=2)
    
    if st.button("🔥 PHÂN TÍCH KỲ MỚI"):
        df_now = process_matrix_v13_41()
        if df_now is not None:
            raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
            if len(raw_list) >= 27:
                gdb_val = st.session_state['gdb_val']
                row = df_now[df_now['Số'] == gdb_val].iloc[0] if gdb_val in df_now['Số'].values else None
                gdb_profile = f"{gdb_val} (R{int(row['Rank'])}-A{int(row['An'])}-D{int(row['DâySạch'])}-T{int(row['Tang'])}-C{int(row['Cứng(10k)'])}%)" if row is not None else gdb_val
                
                df_final = get_thermal_ai_set(df_now) if ai_on else df_now.head(55)
                ai_list = df_final["Số"].tolist()
                
                # Hàm đếm nổ chuẩn theo V13.20
                def get_hit_report(n_days):
                    hits = [h for h in st.session_state['history'][:n_days] if "A(" in str(h.get("Ai", ""))]
                    nums = [str(h.get("GĐB", ""))[:2] for h in hits]
                    return f"{len(hits)}({','.join(nums)})" if nums else "0"

                st.session_state['history'].insert(0, {
                    "STT": len(st.session_state['history'])+1, "GĐB": gdb_profile, 
                    "Ai": f"A({len(ai_list)})" if gdb_val in ai_list else f"T({len(ai_list)})",
                    "AvgC": round(df_final['Cứng(10k)'].mean(), 2) if not df_final.empty else 0,
                    "T5": get_hit_report(5), "T10": get_hit_report(10), "T15": get_hit_report(15), "T20": get_hit_report(20)
                })
                st.session_state['last_full_str'] = "".join(raw_list[:27]); process_matrix_v13_41(); st.rerun()

# --- 5. HIỂN THỊ KẾT QUẢ ---
if st.session_state.get('df_raw') is not None:
    df_raw_data = st.session_state['df_raw']
    df_display = get_thermal_ai_set(df_raw_data) if ai_on else df_raw_data.head(55)

    col_m, col_d = st.columns([2, 1])
    with col_m: st.metric("DÀN CHỐT", f"{len(df_display)} quân", f"AvgC: {df_display['Cứng(10k)'].mean():.2f}")
    with col_d: st.download_button("💾 LƯU .JSON", data=json.dumps({"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state.get('last_full_str')}), file_name="matrix_v13_41.json")
    
    st.code(", ".join(df_display.sort_values("Số")["Số"].tolist()))
    
    st.divider()
    c1, c2 = st.columns([1, 2.8])
    with c1: st.subheader("🎯 CHI TIẾT SỐ"); st.dataframe(df_display, use_container_width=True, hide_index=True)
    with c2: st.subheader("📜 LỊCH SỬ V13.20 SYNC"); st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True, height=800)
