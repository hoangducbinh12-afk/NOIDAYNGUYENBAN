import streamlit as st
import pandas as pd
import numpy as np
import json

# --- 1. GIAO DIỆN HỆ THỐNG CẢNH BÁO ---
st.set_page_config(page_title="CANH BAO 8 BIT V9.0", layout="wide")
st.markdown("""
    <style>
    html, body, [class*="st-"] { color: #000000 !important; background-color: #ffffff !important; font-size: 0.72rem !important; }
    .stButton button { 
        width: 100%; border-radius: 4px; height: 38px; font-weight: 700; 
        background-color: #000080 !important; color: #ffffff !important;
    }
    .alert-safe { background-color: #d1fae5; border-left: 5px solid #10b981; padding: 10px; color: #065f46; font-weight: 700; border-radius: 5px; }
    .alert-danger { background-color: #fee2e2; border-left: 5px solid #ef4444; padding: 10px; color: #991b1b; font-weight: 700; border-radius: 5px; }
    .bit-card { background-color: #ffffff; border: 1px solid #d1d5db; border-radius: 5px; padding: 4px; margin-bottom: 2px; }
    .dan-box { background-color: #f1f5f9; border: 1px solid #000080; border-radius: 5px; padding: 8px; font-weight: 700; color: #000080; text-align: center; font-size: 1.1rem; }
    .rank-indicator { font-size: 0.8rem; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- 2. CORE LOGIC V9.0 ---
SO_THUONG = [2,3,4,6,8,13,15,17,18,19,20,24,25,26,28,30,31,35,37,39,40,42,46,47,48,51,52,53,57,59,60,62,64,68,69,71,73,74,75,79,80,81,82,84,86,91,93,95,96,97]
BIT_LABELS = ["Đ.CL", "Đu.CL", "T.CL", "Đ.TB", "Đu.TB", "T.TB", "Hệ", "Hi.TB"]

def get_8bit(n):
    val = int(n); d, u = val // 10, val % 10
    return [1 if d % 2 != 0 else 0, 1 if u % 2 != 0 else 0, 1 if (d+u) % 2 != 0 else 0,
            1 if d >= 5 else 0, 1 if u >= 5 else 0, 1 if (d+u) % 10 >= 5 else 0,
            1 if val in SO_THUONG else 0, 1 if (d-u+10) % 10 >= 5 else 0]

def analyze_v90(history, last_n):
    if len(history) < 30: return None
    all_bits = np.array([get_8bit(h["Số"]) for h in history])
    curr_bits = np.array(get_8bit(last_n))
    
    # --- CỐ ĐỊNH NHỊP 66-22-11 ---
    L11, L22, L66 = 11, 22, 66
    
    # 1. Ý TƯỞNG 3: CHAOS DETECTION (ĐỘ ỔN ĐỊNH)
    ranks = [h.get("Rank", 50) for h in history[-10:]]
    entropy = np.std(ranks)
    is_chaotic = entropy > 25 or np.mean(ranks) > 60

    # 2. Ý TƯỞNG 2: TẦN SỐ BIT CỘNG HƯỞNG (BIT RESONANCE)
    # Tìm xem 10 kỳ qua Bit nào đang nổ gắt nhất (lệch nhất)
    recent_10 = all_bits[-10:]
    bit_resonance = []
    for i in range(8):
        freq = np.mean(recent_10[:, i])
        resonance_score = abs(freq - 0.5) * 2 # Càng gần 1 hoặc 0 càng cộng hưởng mạnh
        bit_resonance.append(resonance_score)
    
    results = []
    for i in range(8):
        # Tiền tuyến 4K (11 mẫu)
        s4 = "".join(map(str, all_bits[-4:, i].astype(int)))
        m4 = [all_bits[k+4, i] for k in range(len(all_bits)-5) if "".join(map(str, all_bits[k:k+4, i].astype(int))) == s4]
        m4_lim = m4[-L11:]
        p4 = np.mean(m4_lim) if len(m4_lim) > 0 else 0.5

        # Trung quân 3K (22 mẫu)
        s3 = "".join(map(str, all_bits[-3:, i].astype(int)))
        m3 = [all_bits[k+3, i] for k in range(len(all_bits)-4) if "".join(map(str, all_bits[k:k+3, i].astype(int))) == s3]
        m3_lim = m3[-L22:]
        p3 = np.mean(m3_lim) if len(m3_lim) > 0 else 0.5

        # Hậu phương 22K (66 mẫu đối trọng)
        pm_pair = []
        for j in range(8):
            if i == j: continue
            matches = [all_bits[k+1, i] for k in range(len(all_bits)-1) if all_bits[k, i] == curr_bits[i] and all_bits[k, j] == curr_bits[j]]
            pm_pair.extend(matches[-L66:])
        p_base = np.mean(pm_pair) if len(pm_pair) > 0 else 0.5

        # Nhịp nóng 10K
        p_mom = np.mean(all_bits[-10:, i])

        # CÔNG THỨC V9.0: Kết hợp Tần số Bit cộng hưởng
        # Nếu Bit i đang có độ cộng hưởng cao, ưu tiên nhịp 10K và 4K
        res_w = bit_resonance[i]
        w4 = 0.40 + (0.1 * res_w)
        wm = 0.20 + (0.1 * res_w)
        f_prob = (p4 * w4) + (p_mom * wm) + (p3 * 0.20) + (p_base * (1 - w4 - wm - 0.20))
        
        results.append({"l": BIT_LABELS[i], "f": f_prob, "res": res_w, "p4": p4, "p3": p3, "p_base": p_base, "p_mom": p_mom})
        
    return results, is_chaotic, entropy

# --- 3. SESSION STATE ---
if 'history' not in st.session_state: st.session_state.history = []
if 'last_n' not in st.session_state: st.session_state.last_n = -1
if 'next_ky' not in st.session_state: st.session_state.next_ky = 1

# --- 4. SIDEBAR & FILE ---
with st.sidebar:
    st.header("⚡ HỆ THỐNG V9.0")
    up = st.file_uploader("Nạp Master Data:", type="json")
    if up:
        data = json.load(up); raw = data.get("history", [])
        st.session_state.history = sorted([{"Kỳ": int(h["Kỳ"]), "Số": f"{int(h['Số']):02d}", "Rank": int(h.get("Rank", 0))} for h in raw], key=lambda x: x["Kỳ"])
        st.session_state.last_n = int(st.session_state.history[-1]["Số"])
        st.session_state.next_ky = int(st.session_state.history[-1]["Kỳ"]) + 1
    if st.button("🔴 RESET"):
        st.session_state.history = []; st.session_state.last_n = -1; st.session_state.next_ky = 1; st.rerun()

# --- 5. APP GIAO DIỆN ---
st.title("🚨 CANH BAO 8 BIT - QUANTUM INTELLIGENCE")

if st.session_state.history:
    res_data, is_chaotic, entropy = analyze_v90(st.session_state.history, st.session_state.last_n)
    
    # --- HIỂN THỊ CẢNH BÁO CHAOS (Ý TƯỞNG 3) ---
    st.subheader("📡 Trạng thái lồng quay")
    if is_chaotic:
        st.markdown(f"<div class='alert-danger'>⚠️ CẢNH BÁO: Lồng quay đang LOẠN NHỊP (Entropy: {entropy:.2f}). Nên đánh dàn rộng (59-64 số) hoặc nghỉ tay.</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='alert-safe'>✅ ỔN ĐỊNH: Nhịp đang chạy đúng quy luật (Entropy: {entropy:.2f}). Tự tin với dàn Tinh Anh 20-30 số.</div>", unsafe_allow_html=True)

    # --- NHẬP LIỆU ---
    st.divider()
    c1, c2, c3 = st.columns([1, 1, 2])
    n_in = c1.text_input("Số vừa nổ:")
    ky_in = c2.number_input("Kỳ:", value=st.session_state.next_ky)
    if c3.button("🚀 PHÂN TÍCH & LƯU KẾT QUẢ"):
        if n_in:
            val = int(n_in[-2:]); r_v = 0
            # Tính Rank thực tế dựa trên v9.0
            probs = [r["f"] for r in res_data]
            scr = [{"S": f"{i:02d}", "M": sum(get_8bit(i)[j]*probs[j] + (1-get_8bit(i)[j])*(1-probs[j]) for j in range(8))} for i in range(100)]
            df_t = pd.DataFrame(scr).sort_values("M", ascending=False); df_t['R'] = range(1, 101)
            r_v = df_t[df_t['S'] == f"{val:02d}"]['R'].values[0]
            st.session_state.history.append({"Kỳ": int(ky_in), "Số": f"{val:02d}", "Rank": r_v})
            st.session_state.last_n = val; st.session_state.next_ky = int(ky_in) + 1; st.rerun()

    # --- HIỂN THỊ DÀN & BIT ---
    tab1, tab2 = st.tabs(["🎯 DÀN CHIẾN THUẬT", "📊 CHI TIẾT CỘNG HƯỞNG"])
    with tab1:
        probs = [r["f"] for r in res_data]
        res_rank = [{"S": f"{i:02d}", "M": sum(get_8bit(i)[j]*probs[j] + (1-get_8bit(i)[j])*(1-probs[j]) for j in range(8))} for i in range(100)]
        df_rank = pd.DataFrame(res_rank).sort_values("M", ascending=False)
        
        st.markdown(f"### 🔥 DÀN TINH ANH {30 if not is_chaotic else 59} SỐ")
        target_n = 30 if not is_chaotic else 59
        st.markdown(f"<div class='dan-box'>{' '.join(df_rank.head(target_n)['S'].tolist())}</div>", unsafe_allow_html=True)
        
    with tab2:
        cols = st.columns(4)
        for i, r in enumerate(res_data):
            with cols[i % 4]:
                st.markdown(f"""
                <div class='bit-header'>{r['l']}</div>
                <div class='bit-card'>Cộng hưởng: {int(r['res']*100)}%</div>
                <div class='bit-card'>4K (11m): {int(r['p4']*100)}%</div>
                <div class='bit-card'>Hậu (66m): {int(r['p_base']*100)}%</div>
                <div class='bit-card' style='background:#e0f2fe'><b>Hội tụ: {int(r['f']*100)}%</b></div>
                """, unsafe_allow_html=True)
else:
    st.info("Vui lòng nạp Master Data ở Sidebar để bắt đầu hệ thống CẢNH BÁO.")