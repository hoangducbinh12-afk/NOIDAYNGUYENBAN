import streamlit as st
import pandas as pd
import json
import numpy as np
import re

# --- 1. BỘ NÃO AI TỐI ƯU DÀN 50-59 ---
def ai_optimizer_50_59(history, df_raw):
    # Cấu hình mặc định theo yêu cầu của mày
    f_purity = 70
    f_an = (0, 4)
    f_hard_min = 9.0
    
    if len(history) < 5:
        return (0, 99), 1, (0, 250), (f_hard_min, 45.0), "⚠️ Đang dùng cấu hình thô (Cần nạp lịch sử)"

    # AI Quét lịch sử để tìm vùng nổ của R, D, T, AvgC
    r_h, d_h, t_h, c_h = [], [], [], []
    for h in history:
        match = re.search(r"R(\d+)-A(\d+)-D(\d+)-T(\d+)-C(\d+)", h.get('GĐB', ''))
        if match:
            r_h.append(int(match.group(1))); d_h.append(int(match.group(3)))
            t_h.append(int(match.group(4))); c_h.append(int(match.group(5)))

    # AI bắt đầu "ép" các chỉ số phụ để dàn rơi vào khoảng 50-59 số
    # Ưu tiên mở rộng Tầng (T) và Dây (D) trước, sau đó mới siết Rank (R)
    f_t = 1
    f_d = (int(np.percentile(d_h, 5)) if d_h else 0, 250)
    f_r_max = 99
    
    # Vòng lặp giả lập để điều chỉnh Rank sao cho dàn đạt 50-59 số
    temp_df = df_raw[
        (df_raw["An"] >= f_an[0]) & (df_raw["An"] <= f_an[1]) & 
        (df_raw["Cứng(10k)"] >= f_hard_min) & (df_raw["Tang"] >= f_t)
    ]
    
    # Siết dần Rank từ 99 xuống cho đến khi dàn còn ~55 số
    for r in range(99, 40, -1):
        if len(temp_df[temp_df["Rank"] <= r]) <= 59:
            f_r_max = r
            break
            
    f_r = (0, f_r_max)
    f_c = (f_hard_min, 50.0) # Độ cứng tối đa AI phỏng đoán theo thị trường
    
    msg = f"🛡️ AI Safety Mode: Đã tối ưu dàn {len(temp_df[temp_df['Rank'] <= f_r_max])} số. Ưu tiên Rank {f_r} để giữ an toàn cao nhất."
    return f_r, f_t, f_d, f_c, msg

# --- 2. GIAO DIỆN V13.22 ---
with st.sidebar:
    st.header("🧠 SIÊU AI 50-59 (70%)")
    st.info("Mặc định: Purity 70% | An 0-4 | Cứng > 9%")
    
    ai_safe_mode = st.toggle("Kích hoạt AI Tối ưu an toàn", value=True)
    
    # Ghi đè Purity về 70% khi xử lý dữ liệu
    st.session_state['f_strict_val'] = 70 

    if ai_safe_mode and 'df_raw' in st.session_state:
        f_rank, f_tang_min, f_day, f_hard_range, msg = ai_optimizer_50_59(st.session_state['history'], st.session_state['df_raw'])
        f_an = (0, 4) # Luôn cố định An 0-4 theo ý mày
        st.success(msg)
    else:
        st.header("🎛️ ĐIỀU CHỈNH TAY")
        f_rank = st.slider("Hạng (Rank):", 0, 100, (0, 99))
        f_an = st.slider("An thông:", 0, 15, (0, 4))
        f_tang_min = st.slider("Tầng tối thiểu:", 0, 10, 1)
        f_hard_range = st.slider("Khoảng Cứng %:", 0.0, 100.0, (9.0, 50.0))
        f_day = (0, 250)

# --- 3. HIỂN THỊ KẾT QUẢ ---
# (Phần xử lý hiển thị dàn số giữ nguyên như V13.21 để đảm bảo đầy đủ cột Ai và Lịch sử)
