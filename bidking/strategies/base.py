"""策略抽象基类。

每个策略定义：
- name: 唯一标识，用作记录的 "strategy" 字段
- defaults: 价格输入字段的默认值（持久化到 config）
- compute(inputs): 由当前输入计算输出（候选、总价等）
- build_input_widget / build_output_widget: 由各自策略提供自己的 UI 区域

MVP 只有一个策略，但保留抽象以便未来无痛扩展。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class StrategyBase(ABC):
    name: str = ""
    defaults: dict[str, float] = {}

    @abstractmethod
    def compute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """根据输入计算输出。

        返回 dict 至少包含:
          - candidates: list[dict]  # 每个候选 (a, b) 及其衍生字段
          - errors: list[str]       # 硬错误（输入矛盾）
          - warnings: list[str]     # 软警告
        具体字段由各策略约定。
        """
        ...
