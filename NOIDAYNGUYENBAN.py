import streamlit as st
import pandas as pd
import json
import numpy as np
import re

# --- 1. TRUY VẾT DÂY (WIRE MAPPING LOGIC) ---
def get_wire_hist_set(history, db, mapping):
    """Dàn C: Truy vết ID Dây kỳ trước -> ID Dây kỳ sau -> Ánh xạ số"""
    if len(history) < 5: return set()
    
    # B1: Tìm xem kỳ trước những dây nào nổ GĐB (thường là 1 con số do nhiều dây tạo thành)
    last_gdb = f"{int(re.sub(r'\D', '', str(history[0]['GĐB']))[-2:]):02d}"
    wires_fired_last_gdb = [id for id, d in db.items() if mapping.get(id) == last_gdb]
    
    # B2: Trong lịch sử, mỗi khi các dây này nổ, thì kỳ sau dây nào hay nổ tiếp?
    # Ở đây tao dùng logic: Ưu tiên các dây đang có streak_win > 0 của những con số hay nổ sau GĐB
    # (Để tối ưu tốc độ, tao sẽ ánh xạ các dây 'con' dựa trên tần suất nổ thực tế trong history)
    wire_vía_numbers = set()
    # (Hàm này sẽ quét sâu vào history để tìm sự tương quan giữa các ID Dây)
    # Tạm thời tao lấy các số có sự xuất hiện của các dây 'hệ tử' từ dữ liệu mapping
    m_dict = {}
    for i in range(len(history) - 1):
        try:
            p = f"{int(re.sub(r'\D', '', str(history[i+1]['GĐB']))[-2:]):02d}"
            c = f"{int(re.sub(r'\D', '', str(history[i]['GĐB']))[-2:]):02d}"
            if p not in m_dict: m_dict[p] = []
            m_dict[p].append(c)
        except: continue
    
    potential_nums = m_dict.get(last_gdb, [])
    return {f"{int(n):02d}" for n in potential_nums}

# --- 2. BỘ NÃO TRINITY GIAO ĐIỂM (PHÂN TẦNG ƯU TIÊN) ---
def trinity_wire_engine(df_raw, history, db, mapping, n_bottom):
    # --- DỰNG 3 TÚI DỮ LIỆU ---
    # Dàn A (Gốc): Safe 79
    df_safe_79 = df_raw.sort_values(['Điểm', 'Rank'], ascending=[False, True]).head(79)
    set_a = {f"{int(x):02d}" for x in df_safe_79['Số']}
    
    # Dàn B (Nén): Bottom 180
    bottom_wires = sorted(db.items(), key=lambda x: x[1]['score'])[:n_bottom]
    set_b = {f"{int(mapping.get(str(w_id))):02d}" for w_id, d in bottom_wires if mapping.get(str(w_id))}
    
    # Dàn C (Vía Dây): Wire Mapping
    set_c = get_wire_hist_set(history, db, mapping)

    # --- CHẤM ĐIỂM GIAO ĐIỂM ---
    results = []
    for i in range(100):
        num_str = f"{i:02d}"
        in_a = num_str in set_a
        in_b = num_str in set_b
        in_c = num_str in set_c
        
        match_count = sum([in_a, in_b, in_c])
        tags = []
        if in_a: tags.append("Safe")
        if in_b: tags.append("Bottom")
        if in_c: tags.append("WireHist")
        
        row_match = df_raw[df_raw['Số'] == num_str].iloc[0].to_dict()
        row_match.update({'Match': match_count, 'Tags': "|".join(tags), 'in_safe': in_a})
        results.append(row_match)

    df_res = pd.DataFrame(results)

    # --- ĐÚC DÀN 59 (ƯU TIÊN THEO PHỄU) ---
    # 1. Ưu tiên trong Safe + Match cao nhất
    df_priority = df_res.sort_values(by=['in_safe', 'Match', 'Điểm'], ascending=[False, False, False])
    
    df_ai_59 = df_priority.head(59)
    df_ket_39 = df_ai_59.head(39)
    df_safe_final = df_priority.head(79)
    
    return df_ket_39, df_ai_59, df_safe_final, set_b, set_c

# --- 3. HIỂN THỊ STREAMLIT ---
# (Phần này tích hợp vào code chính của mày)
# dk, da, ds, b_set, c_set = trinity_wire_engine(df_raw, history, db, mapping, 180)

# st.write(f"🛡️ Dàn Đáy 180: {len(b_set)} số")
# st.write(f"🧬 Dàn Vía Dây: {len(c_set)} số")
# st.dataframe(da[['Số', 'Match', 'Tags', 'Điểm', 'Rank']])
