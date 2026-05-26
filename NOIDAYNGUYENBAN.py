import streamlit as st
import pandas as pd
import json
import numpy as np
import easyocr
import re
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

# --- 2. BỘ NÃO AI HYBRID (HISTORY SCAN + PATTERN PREDICTION) ---
def ai_hybrid_engine(history):
    if len(history) < 5:
        return (11, 85), (0, 3), 1, (45, 115), (13.0, 45.0), "⚠️ Đang dùng cấu hình an toàn (Cần thêm lịch sử)"

    # --- TẦNG 1: DEEP HISTORY SCAN (THỐNG KÊ VÙNG TỐI ƯU) ---
    r_h, a_h, d_h, t_h, c_h = [], [], [], [], []
    for h in history:
        match = re.search(r"R(\d+)-A(\d+)-D(\d+)-T(\d+)-C(\d+)", h.get('GĐB', ''))
        if match:
            r_h.append(int(match.group(1))); a_h.append(int(match.group(2)))
            d_h.append(int(match.group(3))); t_h.append(int(match.group(4)))
            c_h.append(int(match.group(5)))

    if not r_h: return (11, 85), (0, 3), 1, (45, 115), (13.0, 45.0), "⚠️ Lịch sử chưa có định dạng R-A-D-T-C"

    # Tính vùng mật độ 80%
    base_r = (int(np.percentile(r_h, 10)), int(np.percentile(r_h, 90)))
    base_c = (float(np.percentile(c_h, 10)), float(np.percentile(c_h, 90)))
    
    # --- TẦNG 2: PATTERN PREDICTION (DỰ ĐOÁN HỆ QUẢ NHỊP) ---
    # Phân tích nhịp A & T của 3 kỳ gần nhất
    recent_A = np.mean(a_h[:3])
    recent_T = np.mean(t_h[:3])
    
    # Logic hệ quả: Nếu nhịp đang nén (A, T thấp) -> Dự báo vùng nổ rộng hơn
    f_r, f_a, f_t, f_d, f_c = base_r, (0, 4), 1, (min(d_h), max(d_h)), base_c
    
    if recent_A < 1.0: # Nhịp quá tĩnh
        f_c = (base_c[0] + 2.0, base_c[1] + 5.0) # Dự báo nổ ở con "ấm" hơn
        trend_msg = "🔥 Dự báo Hồi Nhiệt"
    elif recent_A > 2.5: # Nhịp quá động
        f_c = (base_c[0] - 3.0, base_c[1] - 1.0) # Dự báo nổ ở con "nguội" hơn
        trend_msg = "❄️ Dự báo Xả Nhiệt"
    else:
        trend_msg = "⚖️ Nhịp Ổn Định"

    final_msg = f"🧠 AI Hybrid: {trend_msg} | Dựa trên {len(history)} kỳ. Vùng tối ưu: R{f_r}, C{f_c}%"
    return f_r, f_a, f_t, f_d, f_c, final_msg

# --- 3. HÀM XỬ LÝ MA TRẬN CHÍNH ---
def process_matrix_v13_20():
    full_str = st.session_state.get('last_full_str', "0"*107)
    db = st.session_state.get('db', {})
    if not db: return None
    current_map = get_mapping_v11(full_str)
    threshold_pct = st.session_state.get('f_strict_val', 71)
    
    stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "max_gan": 0, "clean_wire_count": 0, "clean_window_hits": 0, "all_losses": []} for i in range(100)}
    for wire_id, num in current_map.items():
        wire = db.get(str(wire_id), {"score": 1000.0, "streak_win": 0, "streak_loss": 0, "hit_history": [0]*10})
        s = stats[num]
        s_win, s_loss = wire.get("streak_win", 0), wire.get("streak_loss", 0)
        s["all_losses"].append(s_loss if s_win == 0 else 0)
        if s_win > s["max_an"]: s["max_an"] = s_win
        if s_loss > s["max_gan"]: s["max_gan"] = s_loss
        s["clean_window_hits"] += sum(wire.get("hit_history", [])[-WINDOW:])
        if s_win == 0:
            s["clean_wire_count"] += 1
            s["total_score"] += wire.get("score", 1000.0) 

    data_list = []
    denominator = WINDOW * AVG_WIRES 
    for num, s in stats.items():
        c_count = s["clean_wire_count"] if s["clean_wire_count"] > 0 else 1
        tang_val = calculate_tier(s["all_losses"], threshold_pct)
        avg_score_db = s["total_score"] / c_count
        do_cung_10 = s["clean_window_hits"] / denominator if denominator > 0 else 0
        multiplier = {3: 1.15, 2: 1.10, 4: 1.10, 1: 1.05}.get(s["max_an"], 1.0)
        final_score = (avg_score_db + (avg_score_db * do_cung_10)) * multiplier
        data_list.append({"Số": num, "Điểm": round(final_score, 2), "An": s["max_an"], "Gan": s["max_gan"], "Tang": tang_val, "DâySạch": s["clean_wire_count"], "Cứng(10k)": round(do_cung_10 * 100, 2)})
    
    df = pd.DataFrame(data_list).sort_values("Điểm", ascending=False).reset_index(drop=True)
    df["Rank"] = df.index + 1
    st.session_state['df_raw'] = df
    return df

# --- 4. GIAO DIỆN STREAMLIT ---
st.set_page_config(layout="wide", page_title="Matrix V13.20 Hybrid AI")
st.markdown("<h1 style='text-align: center; color: red;'>Matrix V13.20 - Hybrid AI Predictive</h1>", unsafe_allow_html=True)

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
            process_matrix_v13_20(); st.rerun()

    up_json = st.file_uploader("📥 Nạp JSON", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json)
        st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', [])
        st.session_state['last_full_str'] = data.get('last_full_str', "0"*107)
        process_matrix_v13_20(); st.rerun()

    st.divider()
    st.header("🧠 CHẾ ĐỘ AI HYBRID")
    ai_on = st.toggle("Kích hoạt AI (History + Pattern)", value=True)
    
    if ai_on:
        f_rank, f_an, f_tang_min, f_day, f_hard, msg = ai_hybrid_engine(st.session_state['history'])
        st.success(msg)
    else:
        st.header("🎛️ BỘ LỌC TAY")
        f_rank = st.slider("Hạng (Rank):", 0, 100, (11, 85))
        f_an = st.slider("An thông:", 0, 15, (0, 3))
        f_tang_min = st.slider("Tầng tối thiểu:", 0, 10, 1)
        f_day = st.slider("Dây Sạch (D):", 0, 250, (45, 115))
        f_hard = st.slider("Khoảng Cứng %:", 0.0, 100.0, (13.0, 40.0))

    st.session_state['f_strict_val'] = st.slider("Độ tinh khiết (%):", 50, 100, 71)

    if st.button("✅ ÁP DỤNG & RA DÀN"):
        process_matrix_v13_20(); st.rerun()

    st.divider()
    st.header("📸 QUÉT KQ (OCR)")
    up_img = st.file_uploader("Chọn ảnh kết quả", type=['jpg', 'jpeg', 'png'])
    if up_img and st.button("🚀 CHẠY OCR"):
        reader = load_ocr(); results = reader.readtext(np.array(Image.open(up_img)), detail=0)
        nums = [n for n in results if n.isdigit() and 2 <= len(n) <= 5]
        if nums:
            st.session_state['raw_input'] = ", ".join(nums)
            st.session_state['gdb_val'] = nums[0][-2:]; st.rerun()

    st.session_state['raw_input'] = st.text_area("27 giải loto:", value=st.session_state.get('raw_input', ""), height=80)
    st.session_state['gdb_val'] = st.text_input("GĐB (2 số):", value=st.session_state.get('gdb_val', ""), max_chars=2)
    
    if st.button("🔥 PHÂN TÍCH KỲ MỚI"):
        df_now = process_matrix_v13_20()
        if df_now is not None:
            raw_list = [x.strip() for x in st.session_state['raw_input'].replace(",", " ").split() if x]
            if len(raw_list) >= 27:
                loto_list = [n[-2:] for n in raw_list[:27]]; gdb_val = st.session_state['gdb_val']
                total_c = sum([df_now[df_now['Số'] == n]['Cứng(10k)'].values[0] for n in loto_list if n in df_now['Số'].values])
                avg_c = round(total_c / 27, 2)
                gdb_info = gdb_val
                if gdb_val in df_now['Số'].values:
                    r = df_now[df_now['Số'] == gdb_val].iloc[0]
                    gdb_info = f"{gdb_val} (R{int(r['Rank'])}-A{int(r['An'])}-D{int(r['DâySạch'])}-T{int(r['Tang'])}-C{int(r['Cứng(10k)'])}%)"
                
                entry = {"STT": len(st.session_state['history'])+1, "GĐB": gdb_info, "Nhiệt(AvgC)": avg_c}
                for t in [5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100]:
                    sub = df_now.head(t); found = [n for n in loto_list if n in sub['Số'].values]
                    entry[f"T{t}"] = f"{len(found)}({','.join(set(found))})" if found else "0"
                st.session_state['history'].insert(0, entry)
                
                # Cập nhật nhịp ma trận... (logic DB giữ nguyên)
                st.session_state['last_full_str'] = "".join(raw_list[:27])
                process_matrix_v13_20(); st.rerun()

# --- 5. HIỂN THỊ KẾT QUẢ ---
if st.session_state.get('df_raw') is not None:
    df_f = st.session_state['df_raw']
    df_f = df_f[
        (df_f["Rank"] >= f_rank[0]) & (df_f["Rank"] <= f_rank[1]) & 
        (df_f["An"] >= f_an[0]) & (df_f["An"] <= f_an[1]) & 
        (df_f["Tang"] >= f_tang_min) & (df_f["DâySạch"] >= f_day[0]) & (df_f["DâySạch"] <= f_day[1]) &
        (df_f["Cứng(10k)"] >= f_hard[0]) & (df_f["Cứng(10k)"] <= f_hard[1])
    ].copy()
    
    col_m, col_d = st.columns([2, 1])
    with col_m: st.metric("DÀN KẾT QUẢ AI CHỐT", f"{len(df_f)} quân")
    with col_d: st.download_button("💾 LƯU DỮ LIỆU .JSON", data=json.dumps({"matrix": st.session_state['db'], "history": st.session_state['history'], "last_full_str": st.session_state['last_full_str']}), file_name="matrix_v13_20.json")
    
    st.code(", ".join(df_f.sort_values("Số")["Số"].tolist()) if not df_f.empty else "Dàn trống")
    
    st.divider()
    c1, c2 = st.columns([1, 2.5])
    with c1:
        st.subheader("🎯 CHI TIẾT SỐ")
        st.dataframe(df_f, use_container_width=True, height=500, hide_index=True)
    with c2:
        st.subheader("📜 TRUY VẾT & NHIỆT KẾ")
        st.dataframe(pd.DataFrame(st.session_state['history']), use_container_width=True, height=800)
