"""数格子精算法。

通过道具读数反推紫色物品的 (总格数 a, 物品数 b) 候选 (优品均格);
若提供金色平均格数 (极品均格), 还能反推金色 (a, b), 进一步拆出红色剩余格数。
结合用户给定的各品质单格估价, 估算仓库总价。

输入字段:
  T:       总格数 (总仓储空间 道具)
  B:       蓝色总格数 (良品扫描 道具)
  WG:      白绿总格数 (普品扫描 道具)
  purple_avg:       紫色平均格数 c_p  (优品均格 道具, 2 位小数)
  purple_count_est: 用户预估紫色物品数 b_p_est
  gold_avg:         金色平均格数 c_g  (极品均格 道具, 可选, 2 位小数)
  gold_count_est:   用户预估金色物品数 b_g_est (可选)

价格输入:
  v_wg:    白绿每格估价
  v_b:     蓝每格估价
  v_p:     紫每格估价
  v_jr:    金红混合每格估价 (当未提供 c_g 时使用)
  v_g:     金每格估价 (当提供 c_g 时使用)
  v_r:     红每格估价 (当提供 c_g 时使用)

输出结构:
  purple_candidates: [{purple_total_grids, purple_count}, ...]
  gold_candidates:   [{gold_total_grids, gold_count}, ...] (空表示未启用金反推)
  errors:   list[str]
  warnings: list[str]

GUI 根据用户选中的 (purple_idx, gold_idx) 调用 compute_estimate 算最终估值。
"""
from __future__ import annotations

from typing import Any

from .base import StrategyBase


def find_candidates(c: float, max_items: int = 80) -> list[tuple[int, int]]:
    """反推满足 c <= a/b <= c+0.01 的所有 (a, b) 正整数对。

    c 是道具显示的 2 位小数。返回按 b 升序的列表。
    """
    if c <= 0:
        return []
    results: list[tuple[int, int]] = []
    upper = c + 0.01
    for b in range(1, max_items + 1):
        min_a = int(c * b)
        max_a = int(upper * b) + 2
        for a in range(min_a, max_a):
            if a <= 0:
                continue
            avg = a / b
            if c <= round(avg, 4) <= upper:
                results.append((a, b))
    return results


# 兼容旧名字
find_purple_candidates = find_candidates


def pick_nearest_candidates(
    candidates: list[tuple[int, int]], b_est: int, k: int = 3
) -> list[tuple[int, int]]:
    """在所有候选中挑选 b 最接近 b_est 的 k 个候选。"""
    if not candidates:
        return []
    sorted_by_dist = sorted(candidates, key=lambda ab: (abs(ab[1] - b_est), ab[1]))
    return sorted_by_dist[:k]


class GridActuarial(StrategyBase):
    name = "数格子精算法"
    defaults = {
        "v_wg": 100.0,
        "v_b": 800.0,
        "v_p": 2000.0,
        "v_jr": 20000.0,
        "v_g": 10000.0,
        "v_r": 30000.0,
        "purple_count_est": 10.0,
        "gold_count_est": 5.0,
    }

    def compute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        errors: list[str] = []
        warnings: list[str] = []

        T = _to_int(inputs.get("T"))
        B = _to_int(inputs.get("B"))
        WG = _to_int(inputs.get("WG"))
        c_p = _to_float(inputs.get("purple_avg"))
        b_p_est = _to_int(inputs.get("purple_count_est"))
        c_g = _to_float(inputs.get("gold_avg"))
        b_g_est = _to_int(inputs.get("gold_count_est"))

        if T is None or B is None or WG is None or c_p is None:
            return {
                "purple_candidates": [],
                "gold_candidates": [],
                "errors": errors,
                "warnings": warnings,
            }

        if B + WG > T:
            errors.append(f"蓝({B}) + 白绿({WG}) = {B+WG} 已经超过总格数 {T}")

        if c_p is not None and c_p > 0:
            rounded = round(c_p, 2)
            if abs(rounded - c_p) > 1e-9:
                warnings.append(f"紫色平均 {c_p} 超过 2 位小数, 道具读数只有 2 位精度")
        if c_g is not None and c_g > 0:
            rounded = round(c_g, 2)
            if abs(rounded - c_g) > 1e-9:
                warnings.append(f"金色平均 {c_g} 超过 2 位小数, 道具读数只有 2 位精度")

        purple_candidates: list[dict[str, Any]] = []
        if c_p is not None and c_p > 0:
            all_p = find_candidates(c_p)
            if not all_p:
                errors.append(f"紫色平均 {c_p} 反推不出任何合法 (a, b)")
            picked = pick_nearest_candidates(all_p, b_p_est or 1, k=3)
            for a, b in picked:
                purple_candidates.append({"purple_total_grids": a, "purple_count": b})

        gold_candidates: list[dict[str, Any]] = []
        if c_g is not None and c_g > 0:
            all_g = find_candidates(c_g, max_items=40)
            if not all_g:
                errors.append(f"金色平均 {c_g} 反推不出任何合法 (a, b)")
            picked_g = pick_nearest_candidates(all_g, b_g_est or 1, k=3)
            for a, b in picked_g:
                gold_candidates.append({"gold_total_grids": a, "gold_count": b})

        return {
            "purple_candidates": purple_candidates,
            "gold_candidates": gold_candidates,
            "errors": errors,
            "warnings": warnings,
        }

    @staticmethod
    def compute_estimate(
        inputs: dict[str, Any],
        purple_cand: dict[str, Any] | None,
        gold_cand: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """根据当前选中的 (purple, gold) 候选, 计算金红/红剩余格数和总估值。

        gold_cand=None 时按 "金红混合" 模式 (v_jr); 否则按 "金红拆分" 模式 (v_g + v_r)。
        """
        T = _to_int(inputs.get("T")) or 0
        B = _to_int(inputs.get("B")) or 0
        WG = _to_int(inputs.get("WG")) or 0
        v_wg = _to_float(inputs.get("v_wg")) or 0.0
        v_b = _to_float(inputs.get("v_b")) or 0.0
        v_p = _to_float(inputs.get("v_p")) or 0.0
        v_jr = _to_float(inputs.get("v_jr")) or 0.0
        v_g = _to_float(inputs.get("v_g")) or 0.0
        v_r = _to_float(inputs.get("v_r")) or 0.0

        if purple_cand is None:
            return {
                "purple_grids": 0, "gold_grids": 0, "red_grids": 0,
                "gold_red_grids": 0, "estimated_value": None,
                "split_mode": gold_cand is not None,
                "error": "未选紫色候选",
            }

        a_p = purple_cand["purple_total_grids"]
        gold_red = T - B - WG - a_p

        if gold_cand is not None:
            a_g = gold_cand["gold_total_grids"]
            a_r = gold_red - a_g
            err = None
            if a_r < 0:
                err = f"红色格数 = {a_r} < 0, 紫+金已经超额"
            value = WG * v_wg + B * v_b + a_p * v_p + a_g * v_g + max(a_r, 0) * v_r
            return {
                "purple_grids": a_p, "gold_grids": a_g, "red_grids": a_r,
                "gold_red_grids": gold_red, "estimated_value": value,
                "split_mode": True, "error": err,
            }
        else:
            err = None
            if gold_red < 0:
                err = f"金红剩余 = {gold_red} < 0, 紫色已超额"
            value = WG * v_wg + B * v_b + a_p * v_p + max(gold_red, 0) * v_jr
            return {
                "purple_grids": a_p, "gold_grids": 0, "red_grids": 0,
                "gold_red_grids": gold_red, "estimated_value": value,
                "split_mode": False, "error": err,
            }


def _to_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
