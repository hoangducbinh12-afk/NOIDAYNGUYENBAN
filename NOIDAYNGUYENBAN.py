import streamlit as st
import pandas as pd
import json
import numpy as np

# --- 1. HÀM CÔNG CỤ ---
TOTAL_POS = 107 

def get_mapping_v10(full_str):
    if not full_str or len(full_str) < TOTAL_POS: return None
    mapping = {}
    for i in range(TOTAL_POS):
        for j in range(TOTAL_POS):
            wire_id = str(i * TOTAL_POS + j)
            num_formed = f"{full_str[i]}{full_str[j]}"
            mapping[wire_id] = num_formed
    return mapping

def refresh_display_v10():
    if not st.session_state.get('last_full_str'): return
    
    current_map = get_mapping_v10(st.session_state['last_full_str'])
    db = st.session_state['db']
    total_periods = len(st.session_state['history'])
    
    # Khởi tạo kho chứa cho 100 số
    stats = {f"{i:02d}": {
        "total_score": 0.0,
        "max_an": 0,
        "max_gan": 0,
        "wire_count": 0,
        "total_hits": 0
    } for i in range(100)}

    # Quét từng sợi dây để phân bổ vào 100 số
    for wire_id, num in current_map.items():
        wire = db.get(wire_id, {"score": 100.0, "streak_win": 0, "streak_loss": 0, "history_hits": 0})
        
        s = stats[num]
        s["wire_count"] += 1
        s["total_hits"] += wire.get("history_hits", 0)
        
        # Tính điểm có hệ số phong độ
        p_coef = 1.5 if wire.get("streak_win", 0) > 0 else 0.7
        s["total_score"] += (wire.get("score", 100.0) * p_coef)
        
        # Tìm Max An và Max Gan của các dây thành phần
        if wire.get("streak_win", 0) > s["max_an"]: s["max_an"] = wire.get("streak_win", 0)
        if wire.get("streak_loss", 0) > s["max_gan"]: s["max_gan"] = wire.get("streak_loss", 0)

    # Chuyển thành DataFrame để lọc
    data_list = []
    for num, s in stats.items():
        # Tính độ cứng trung bình (%)
        hardness = (s["total_hits"] / (s["wire_count"] * total_periods) * 100) if total_periods > 0 else 0
        data_list.append({
            "Số": num,
            "Điểm": round(s["total_score"], 1),
            "An": s["max_an"],
            "Nén": s["max_gan"],
            "Dây": s["wire_count"],
            "Cứng(%)": round(hardness, 1)
        })
    
    df = pd.DataFrame(data_list)
    
    # --- ÁP DỤNG BỘ LỌC CHIẾN THUẬT CỦA MÀY ---
    # 1. Lọc Độ cứng >= 23.5%
    df_filtered = df[df["Cứng(%)"] >= 23.5].copy()
    
    # 2. Lọc An thuộc {1, 2, 3}
    df_filtered = df_filtered[df_filtered["An"].isin([1, 2, 3])]
    
    if len(df_filtered) > 10:
        # Sắp xếp theo điểm để xác định Top Gan điểm cao/thấp
        df_sorted_by_score = df_filtered.sort_values("Điểm", ascending=False)
        
        # Lấy 5 thằng Gan cao nhất trong đám điểm cao nhất (Top đầu) để loại
        top_5_high_score = df_sorted_by_score.head(5).index
        
        # Lấy 4 thằng Gan cao nhất trong đám điểm thấp nhất (Top cuối) để loại
        top_4_low_score = df_sorted_by_score.tail(4).index
        
        # Thực hiện loại trừ
        df_final = df_filtered.drop(index=top_5_high_score.union(top_4_low_score))
    else:
        df_final = df_filtered

    st.session_state['df_final'] = df_final.sort_values("Điểm", ascending=False)

# --- GIAO DIỆN STREAMLIT ---
st.set_page_config(layout="wide")
st.title("🌐 MATRIX V10 - CHIẾN THUẬT ELIMINATOR")

if 'db' not in st.session_state: st.session_state['db'] = {}
if 'history' not in st.session_state: st.session_state['history'] = []

with st.sidebar:
    up_json = st.file_uploader("Nạp dữ liệu JSON", type=['json'])
    if up_json and st.button("XÁC NHẬN"):
        data = json.load(up_json)
        st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', [])
        st.session_state['last_full_str'] = data.get('last_full_str', "")
        refresh_display_v10()
        st.rerun()

if st.session_state.get('df_final') is not None:
    df = st.session_state['df_final']
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("🎯 DANH SÁCH QUÂN BÀI CHIẾN THUẬT")
        st.write(f"Đã lọc còn: {len(df)} quân (Tiêu chí: An 1-3, Cứng >= 23.5%, Loại trừ Gan biên)")
        st.dataframe(df, use_container_width=True, height=500)
    
    with col2:
        st.subheader("📊 PHÂN TÍCH MẬT ĐỘ (DÂY)")
        # Biểu đồ mật độ dây để xem con nào "dày" nhất
        st.bar_chart(df.set_index("Số")["Dây"])
        
        st.subheader("💡 GỢI Ý CỦA TAO")
        # Gợi ý con số có mật độ dây cao nhất trong nhóm đã lọc
        if not df.empty:
            best_wire = df.sort_values("Dây", ascending=False).iloc[0]
            st.success(f"Số có mật độ dây hội tụ cao nhất: **{best_wire['Số']}** ({best_wire['Dây']} dây)")
            
            best_gan = df.sort_values("Nén", ascending=False).iloc[0]
            st.error(f"Số có áp suất nén cao nhất trong nhóm: **{best_gan['Số']}** (Nén {best_gan['Nén']} kỳ)")
