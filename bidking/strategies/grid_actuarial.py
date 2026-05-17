"""数格子精算法。

通过道具读数反推紫色物品的 (总格数 a, 物品数 b) 候选，
结合用户给定的各品质单格估价，估算仓库总价。

输入字段:
  T:       总格数 (总仓储空间 道具)
  B:       蓝色总格数 (良品扫描 道具)
  WG:      白绿总格数 (普品扫描 道具)
  purple_avg:    紫色平均格数 c (优品均格 道具, 2 位小数)
  purple_count_est: 用户预估紫色物品数 b_est
  v_jr:    金红每格估价
  v_p:     紫每格估价
  v_b:     蓝每格估价
  v_wg:    白绿每格估价

输出:
  candidates: 每个 (a, b) 候选包含 purple_total_grids, purple_count, gold_red_grids, estimated_value
  errors:     硬错误
  warnings:   软警告
"""
from __future__ import annotations

from typing import Any

from .base import StrategyBase


def find_purple_candidates(c: float, max_items: int = 80) -> list[tuple[int, int]]:
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


def pick_nearest_candidates(
    candidates: list[tuple[int, int]], b_est: int, k: int = 3
) -> list[tuple[int, int]]:
    """在所有候选中挑选 b 最接近 b_est 的 k 个候选。

    若 b_est 正好匹配某个候选的 b，优先返回该候选。
    """
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
        "purple_count_est": 10.0,
    }

    def compute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        errors: list[str] = []
        warnings: list[str] = []

        T = _to_int(inputs.get("T"))
        B = _to_int(inputs.get("B"))
        WG = _to_int(inputs.get("WG"))
        c = _to_float(inputs.get("purple_avg"))
        b_est = _to_int(inputs.get("purple_count_est"))
        v_jr = _to_float(inputs.get("v_jr"))
        v_p = _to_float(inputs.get("v_p"))
        v_b = _to_float(inputs.get("v_b"))
        v_wg = _to_float(inputs.get("v_wg"))

        if T is None or B is None or WG is None or c is None:
            return {"candidates": [], "errors": errors, "warnings": warnings}

        if B + WG > T:
            errors.append(f"蓝({B}) + 白绿({WG}) = {B+WG} 已经超过总格数 {T}")

        if c is not None and c > 0:
            rounded = round(c, 2)
            if abs(rounded - c) > 1e-9:
                warnings.append(f"紫色平均格数 {c} 超过 2 位小数，道具读数只有 2 位精度")

        if c is None or c <= 0:
            return {"candidates": [], "errors": errors, "warnings": warnings}

        all_candidates = find_purple_candidates(c)
        if not all_candidates:
            errors.append(f"紫色平均 {c} 反推不出任何合法 (a, b)")
            return {"candidates": [], "errors": errors, "warnings": warnings}

        picked = pick_nearest_candidates(all_candidates, b_est or 1, k=3)

        cand_dicts: list[dict[str, Any]] = []
        for a, b in picked:
            gold_red = T - B - WG - a
            cand: dict[str, Any] = {
                "purple_total_grids": a,
                "purple_count": b,
                "gold_red_grids": gold_red,
                "estimated_value": None,
            }
            if gold_red < 0:
                cand["error"] = f"金红格数 = {gold_red} < 0，紫色 a={a} 已经超额"
            else:
                if v_jr is None or v_p is None or v_b is None or v_wg is None:
                    cand["error"] = "估价参数缺失"
                else:
                    value = (
                        gold_red * v_jr
                        + a * v_p
                        + B * v_b
                        + WG * v_wg
                    )
                    cand["estimated_value"] = value
            cand_dicts.append(cand)

        cand_dicts.sort(key=lambda d: abs(d["purple_count"] - (b_est or d["purple_count"])))

        return {
            "candidates": cand_dicts,
            "errors": errors,
            "warnings": warnings,
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
