import streamlit as st
import pandas as pd
import json

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

def process_data_v101():
    if not st.session_state.get('last_full_str'): return
    
    current_map = get_mapping_v10(st.session_state['last_full_str'])
    db = st.session_state['db']
    total_periods = len(st.session_state['history'])
    
    stats = {f"{i:02d}": {"total_score": 0.0, "max_an": 0, "max_gan": 0, "wire_count": 0, "total_hits": 0} for i in range(100)}

    for wire_id, num in current_map.items():
        wire = db.get(wire_id, {"score": 100.0, "streak_win": 0, "streak_loss": 0, "history_hits": 0})
        s = stats[num]
        s["wire_count"] += 1
        s["total_hits"] += wire.get("history_hits", 0)
        p_coef = 1.5 if wire.get("streak_win", 0) > 0 else 0.7
        s["total_score"] += (wire.get("score", 100.0) * p_coef)
        if wire.get("streak_win", 0) > s["max_an"]: s["max_an"] = wire.get("streak_win", 0)
        if wire.get("streak_loss", 0) > s["max_gan"]: s["max_gan"] = wire.get("streak_loss", 0)

    data_list = []
    for num, s in stats.items():
        hardness = (s["total_hits"] / (s["wire_count"] * total_periods) * 100) if total_periods > 0 else 0
        data_list.append({
            "Số": num, "Điểm": round(s["total_score"], 1), "An": s["max_an"], 
            "Nén": s["max_gan"], "Dây": s["wire_count"], "Cứng(%)": round(hardness, 1)
        })
    
    df_all = pd.DataFrame(data_list)
    st.session_state['df_all'] = df_all.sort_values("Điểm", ascending=False)

    # --- ÁP DỤNG BỘ LỌC CHIẾN THUẬT ---
    # 1. Cứng >= 23.5% + An 1,2,3
    df_f = df_all[(df_all["Cứng(%)"] >= 23.5) & (df_all["An"].isin([1, 2, 3]))].copy()
    
    if len(df_f) > 9:
        df_f = df_f.sort_values("Điểm", ascending=False)
        # Loại 5 thằng đầu bảng (Gan cao nhất trong đám điểm cao)
        idx_to_drop_top = df_f.sort_values("Nén", ascending=False).head(5).index
        df_f = df_f.drop(index=idx_to_drop_top)
        # Loại 4 thằng cuối bảng (Gan cao nhất trong đám điểm thấp)
        if len(df_f) > 4:
            idx_to_drop_bot = df_f.sort_values("Nén", ascending=False).tail(4).index
            df_f = df_f.drop(index=idx_to_drop_bot)
            
    st.session_state['df_strategy'] = df_f.sort_values("Điểm", ascending=False)

# --- GIAO DIỆN ---
st.set_page_config(layout="wide")
st.title("🌐 MATRIX V10.1 - KHÔI PHỤC HIỂN THỊ")

if 'db' not in st.session_state: st.session_state['db'] = {}
if 'history' not in st.session_state: st.session_state['history'] = []

with st.sidebar:
    up_json = st.file_uploader("Nạp JSON", type=['json'])
    if up_json and st.button("XÁC NHẬN NẠP"):
        data = json.load(up_json)
        st.session_state['db'] = data.get('matrix', data)
        st.session_state['history'] = data.get('history', [])
        st.session_state['last_full_str'] = data.get('last_full_str', "")
        process_data_v101()
        st.rerun()

if st.session_state.get('df_all') is not None:
    c1, c2 = st.columns([1, 1])
    
    with c1:
        st.subheader("📊 TỔNG LỰC 100 SỐ (CỘT DÂY)")
        st.dataframe(st.session_state['df_all'], use_container_width=True, height=600)
        
    with c2:
        st.subheader("🎯 LỌC CHIẾN THUẬT (AN 1-3, CỨNG 23.5%)")
        df_s = st.session_state.get('df_strategy')
        if df_s is not None and not df_s.empty:
            st.success(f"Tìm thấy {len(df_s)} quân thỏa mãn!")
            st.dataframe(df_s, use_container_width=True, height=400)
        else:
            st.warning("⚠️ Không có quân nào thỏa mãn bộ lọc GẮT này. Mày nên kiểm tra cột Cứng hoặc An ở bảng bên trái!")

        st.divider()
        st.subheader("📜 LỊCH SỬ KỲ")
        st.dataframe(pd.DataFrame(st.session_state['history']).head(10), use_container_width=True)
