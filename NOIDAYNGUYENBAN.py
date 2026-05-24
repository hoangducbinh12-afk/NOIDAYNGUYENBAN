def process_data_v12_9():
    # ... (Giữ nguyên đoạn mapping và db) ...
    
    for wire_id, num in current_map.items():
        wire = db.get(str(wire_id), {"score": 1000.0, "streak_win": 0, "streak_loss": 0, "hit_history": []})
        s = stats[num]
        # Luôn lấy An, Gan từ toàn bộ dây để soi nhịp
        if wire.get("streak_win", 0) > s["max_an"]: s["max_an"] = wire.get("streak_win", 0)
        if wire.get("streak_loss", 0) > s["max_gan"]: s["max_gan"] = wire.get("streak_loss", 0)
        
        # Chỉ tính điểm cho Dây Sạch (Loại trừ dây vừa nổ)
        if wire.get("streak_win", 0) == 0:
            s["clean_wire_count"] += 1
            s["clean_window_hits"] += sum(wire.get("hit_history", [])[-WINDOW:])
            s["total_score"] += wire.get("score", 1000.0)

    data_list = []
    for num, s in stats.items():
        if s["clean_wire_count"] == 0: continue
        
        avg_score_db = s["total_score"] / s["clean_wire_count"]
        do_cung_10 = s["clean_window_hits"] / (WINDOW * AVG_WIRES)
        
        # 1. TÍNH ĐIỂM CƠ BẢN
        final_score = avg_score_db + (avg_score_db * do_cung_10)
        
        # 2. CƠ CHẾ TURBO BOOST (ÉP RANK)
        # Thay vì cộng 5đ, mình nhân hệ số % để tạo đột biến Rank
        m_an = s["max_an"]
        multiplier = 1.0
        if m_an == 3: multiplier = 1.15   # Thưởng 15% (Vùng GĐB trọng điểm)
        elif m_an in [2, 4]: multiplier = 1.10 # Thưởng 10%
        elif m_an == 1: multiplier = 1.05 # Thưởng 5%
        
        final_score *= multiplier
        
        # ... (đóng gói data_list và sort Rank) ...
