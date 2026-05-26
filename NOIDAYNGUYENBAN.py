import streamlit as st
import pandas as pd
import json
import numpy as np

# --- 1. BỘ NÃO DỰ BÁO (AI PREDICTOR) ---
def predict_next_avgc(history):
    if len(history) < 5:
        return 13.0, 35.0  # Mặc định an toàn nếu chưa đủ dữ liệu
    
    # Lấy 10 kỳ gần nhất
    recent_avgc = [h.get('Nhiệt(AvgC)', 20.0) for h in history[:10]]
    current_avg = np.mean(recent_avgc)
    std_dev = np.std(recent_avgc)
    
    # Chiến thuật: Dự báo hồi quy
    last_val = recent_avgc[0]
    
    if last_val < current_avg - (0.5 * std_dev):
        # Thị trường đang quá nguội -> Dự báo sẽ ấm lên (Hồi nhiệt)
        low_bound = last_val + 2.0
        high_bound = current_avg + std_dev
        trend = "🔥 DỰ BÁO HỒI NHIỆT (Ưu tiên số ấm)"
    elif last_val > current_avg + (0.5 * std_dev):
        # Thị trường đang quá nóng -> Dự báo sẽ nguội đi (Xả nhiệt)
        low_bound = current_avg - std_dev
        high_bound = last_val - 2.0
        trend = "❄️ DỰ BÁO XẢ NHIỆT (Ưu tiên số nén)"
    else:
        # Thị trường ổn định
        low_bound = current_avg - (1.5 * std_dev)
        high_bound = current_avg + (1.5 * std_dev)
        trend = "⚖️ THỊ TRƯỜNG ỔN ĐỊNH (Đánh dàn chuẩn)"
        
    return max(11.0, low_bound), min(45.0, high_bound), trend

# --- 2. CẬP NHẬT GIAO DIỆN V13.14 ---
# (Giữ nguyên các hàm process_data và mapping từ bản V13.13)

with st.sidebar:
    st.header("🤖 AI PREDICTIVE MODE")
    ai_mode = st.toggle("Kích hoạt AI Dự báo Nhịp", value=True)
    
    if ai_mode and len(st.session_state.get('history', [])) > 0:
        low, high, trend = predict_next_avgc(st.session_state['history'])
        st.success(f"Trạng thái: {trend}")
        st.info(f"Vùng Cứng AI khuyên dùng: {low:.1f}% - {high:.1f}%")
        f_hard_range = (low, high)
    else:
        f_hard_range = st.slider("Cài tay Khoảng Cứng %:", 0.0, 100.0, (13.0, 40.0))

    # Các bộ lọc khác giữ nguyên...
    f_rank = st.slider("Hạng (Rank):", 0, 100, (11, 85))
    f_an = st.slider("An thông (Ngày):", 0, 15, (0, 3))
    f_tang_min = st.slider("Tầng tối thiểu (T):", 0, 10, 1)

# --- 3. HIỂN THỊ DÀN ---
if st.session_state.get('df_raw') is not None:
    df_f = st.session_state['df_raw']
    # Áp dụng bộ lọc AI hoặc bộ lọc tay
    df_f = df_f[
        (df_f["Rank"] >= f_rank[0]) & (df_f["Rank"] <= f_rank[1]) & 
        (df_f["An"] >= f_an[0]) & (df_f["An"] <= f_an[1]) & 
        (df_f["Tang"] >= f_tang_min) & 
        (df_f["Cứng(10k)"] >= f_hard_range[0]) & (df_f["Cứng(10k)"] <= f_hard_range[1])
    ].copy()
    
    st.metric("DÀN DO AI CHỐT", f"{len(df_f)} quân")
    # ... (Hiển thị bảng và mã số)
