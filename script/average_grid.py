def generate_lookup_table(c, max_items=80):
    """
    根据显示的平均格子数，反推可能的总格子数和物品个数。
    
    :param c: 道具显示的平均值 (保留两位小数)
    :param max_items: 预估单场拍卖中紫色物品的最高可能个数 (可根据游戏实际情况调整)
    """
    print(f"\n--- 当道具显示紫装平均占用 {c} 格时 ---")
    print(f"{'总格子数 (a)':<15} | {'物品个数 (b)':<15} | {'实际平均值 (a/b)':<15}")
    print("-" * 50)
    
    results_found = False
    
    # 遍历可能的物品个数 b
    for b in range(1, max_items + 1):
        # 因为 c <= a/b <= c + 0.01
        # 所以 c * b <= a <= (c + 0.01) * b
        
        # 确定 a 的搜索范围，稍微放宽一点范围防止浮点数精度问题漏算
        min_a = int(c * b)
        max_a = int((c + 0.01) * b) + 2
        
        for a in range(min_a, max_a):
            # 浮点数计算会有极小的误差，这里用 round 处理一下
            actual_avg = a / b
            
            # 判断是否满足 c <= x <= c + 0.01
            if c <= round(actual_avg, 4) <= c + 0.01:
                print(f"{a:<15} | {b:<15} | {actual_avg:<15.4f}")
                results_found = True
                
    if not results_found:
        print("在设定的物品数量范围内，没有找到符合条件的组合。")
    print("-" * 50)

# ==========================================
# 使用方法：在这里修改你游戏中看到的数值
# ==========================================
if __name__ == "__main__":
    # 假设你在游戏中看到的平均值是 2.33
    target_c = 2.91
    
    # 如果你觉得仓库里的紫装不可能超过 30 个，可以保持 max_items=30 不变
    # 如果仓库很大，可以把 30 改成 50 或 100
    generate_lookup_table(c=target_c, max_items=80)