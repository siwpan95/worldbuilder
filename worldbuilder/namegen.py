"""名字生成器：基于音节拼接，支持多种风格。"""
from __future__ import annotations

import numpy as np

_STYLES = {
    "fantasy": {
        "pre": ["A", "Be", "Ca", "Dra", "E", "Fen", "Gal", "Is", "Mor", "Tho", "Vor", "Zy"],
        "mid": ["a", "el", "il", "om", "ar", "ith", "or", "un", "ae", "yn"],
        "suf": ["dor", "wyn", "ric", "thas", "mir", "loth", "wen", "dil", "rion", "vyn"],
    },
    "sci": {
        "pre": ["X", "Kr", "V", "Z", "Q", "N", "T", "Ar", "Cy", "Bl"],
        "mid": ["o", "ex", "ix", "an", "or", "ul", "ev", "in"],
        "suf": ["on", "ix", "ar", "us", "ex", "oid", "an", "yx"],
    },
    "eastern": {
        "pre": ["长", "风", "青", "玄", "白", "墨", "凌", "苏", "沈", "顾"],
        "mid": ["月", "云", "雪", "川", "夜", "羽", "霜", "霄"],
        "suf": ["轩", "瑶", "尘", "澜", "然", "霜", "璃", "辰"],
    },
}

# 马尔可夫训练语料（每种风格若干样例词，用于字符级转移学习）
_CORPUS = {
    "fantasy": ["aiden", "bard", "caelan", "draven", "elwin", "fenris", "galen",
                "isolde", "morgana", "thorin", "vorian", "zyra", "alwin", "briar",
                "cedric", "elena", "freya", "rowan", "tamsin", "wren"],
    "sci": ["xandar", "krell", "vexis", "zorin", "quill", "nyx", "atlas", "cyber",
            "blip", "orbit", "vega", "zenith", "pulsar", "nova", "ion", "cipher"],
    "eastern": ["changfeng", "qingyun", "xuanye", "baishuang", "moyu", "lingshuang",
                "suyue", "guchen", "shenlan", "fengyao", "yunxi", "hanli"],
}


def _build_markov(words, order: int = 2) -> dict:
    """由语料构建 order 阶字符转移表：key -> [next_char, ...]。"""
    trans = {}
    for w in words:
        w = "^" + w + "$"
        for i in range(len(w) - order):
            key = w[i:i + order]
            trans.setdefault(key, []).append(w[i + order])
    return trans


def _markov_name(trans, rng, min_len: int = 4, max_len: int = 10,
                 order: int = 2, _tries: int = 0) -> str:
    """从转移表采样一个名字（首字母大写）。带长度下限与重试上限。"""
    if _tries > 50:
        return rng.choice(list(trans.keys())).strip("^").capitalize()
    starts = [k for k in trans if k.startswith("^")] or list(trans.keys())
    first = rng.choice(starts)
    out = [first[1:]]          # 去掉起始哨兵 '^'
    key = first                # 滑动窗口，长度恒为 order
    while len(out) < max_len:
        nxts = trans.get(key)
        if not nxts:
            break
        c = rng.choice(nxts)
        if c == "$":
            break
        out.append(c)
        key = (key + c)[-order:]
    name = "".join(out).capitalize()
    return name if len(name) >= min_len else _markov_name(
        trans, rng, min_len, max_len, order, _tries + 1)


class NameGenerator:
    """名字生成器（音节拼接 / 马尔可夫两种算法）。

    参数：
        style:    'fantasy' / 'sci' / 'eastern'
        seed:     随机种子
        syllables: 音节数量（默认 2），仅 syllable 方法使用
        method:   'syllable'（默认，音节拼接）或 'markov'（字符级转移学习）

    示例：
        ng = NameGenerator(style='fantasy', syllables=2)
        names = ng.generate(10)
        mk = NameGenerator(style='sci', method='markov')
        names = mk.generate(10)
    """

    def __init__(self, style: str = "fantasy", seed: int = 0, syllables: int = 2,
                 method: str = "syllable"):
        if style not in _STYLES:
            raise ValueError(f"未知风格: {style}，可选 {list(_STYLES)}")
        if method not in ("syllable", "markov"):
            raise ValueError(f"未知方法: {method}，可选 syllable/markov")
        if syllables < 1:
            raise ValueError("syllables 必须 >= 1")
        self.style = style
        self.parts = _STYLES[style]
        self.syllables = syllables
        self.method = method
        self.rng = np.random.RandomState(seed)
        if method == "markov":
            self._trans = _build_markov(_CORPUS.get(style, _CORPUS["fantasy"]))

    def _one_syllable(self) -> str:
        parts = []
        for i in range(self.syllables):
            p = self.rng.choice(self.parts["pre"])
            if i > 0:
                p = p.lower()  # 仅首音节首字母大写，保证 istitle
            m = self.rng.choice(self.parts["mid"]) if self.rng.rand() < 0.6 else ""
            parts.append(p + m)
        s = self.rng.choice(self.parts["suf"])
        return "".join(parts) + s

    def _one(self) -> str:
        if self.method == "markov":
            return _markov_name(self._trans, self.rng)
        return self._one_syllable()

    def generate(self, n: int = 1) -> list[str]:
        return [self._one() for _ in range(n)]


# ---------------------------------------------------------------------------
# 文法式命名（Tracery 思路，Apache-2.0）：自研，不搬 Tracery 的 JS 实现。
# 只借"产生式规则 + #符号# 递归展开 + 可选修饰符"这一思路。
# ---------------------------------------------------------------------------
import re

_TOKEN = re.compile(r"#([A-Za-z_][A-Za-z0-9_]*)(?:\.([A-Za-z_][A-Za-z0-9_]*))?#")

#: 修饰符：展开后对结果做的小变换。名字场景常用的几个。
_MODIFIERS = {
    "cap": lambda s: s[:1].upper() + s[1:] if s else s,    # 首字母大写
    "title": lambda s: s.title(),                          # 每个词首字母大写
    "upper": lambda s: s.upper(),                          # 全大写
    "lower": lambda s: s.lower(),                          # 全小写
    "a": lambda s: (("an " if s[:1].lower() in "aeiou" else "a ") + s)
                  if s else s,                             # 加不定冠词
    "s": lambda s: s + ("es" if s.endswith(("s", "x", "z", "ch", "sh")) else "s"),
}


class GrammarError(ValueError):
    """文法非法：符号未定义 / 修饰符未知 / 递归不收敛。"""


class GrammarGenerator:
    """Tracery 风格的文法生成器（自研思路版）。

    文法是一张 ``符号 -> 候选展开`` 的字典；候选可以是字符串或字符串列表
    （列表里等概率随机选）。展开字符串里用 ``#符号#`` 引用别的符号，
    可附加修饰符 ``#符号.修饰#``（见 ``_MODIFIERS``）。

    示例::

        g = GrammarGenerator({
            "origin": ["#adj# #noun#", "#noun# of #place#"],
            "adj":   ["red", "old", "silent"],
            "noun":  ["thorn", "river", "mount", "fen"],
            "place": ["the west", "the north"],
        }, seed=0)
        names = g.generate(10)

    与 ``NameGenerator`` 的 Markov 方法并列，作为另一种"从规则而非语料"
    产出名字的来源。
    """

    def __init__(self, grammar: dict, *, seed: int = 0, start: str = "origin",
                 max_depth: int = 24):
        if start not in grammar:
            raise ValueError(f"起始符号 {start!r} 不在文法中")
        self.grammar = {
            k: (list(v) if isinstance(v, (list, tuple)) else [v])
            for k, v in grammar.items()
        }
        self.rng = np.random.RandomState(seed)
        self.start = start
        self.max_depth = max_depth

    def _expand(self, text: str, depth: int) -> str:
        if depth > self.max_depth:
            raise GrammarError(
                f"展开超过最大深度 {self.max_depth}（文法可能含自指循环）")

        def repl(m: "re.Match") -> str:
            sym = m.group(1)
            mod = m.group(2)
            if sym not in self.grammar:
                raise GrammarError(f"文法未定义符号：{sym}")
            choice = str(self.rng.choice(self.grammar[sym]))
            expanded = self._expand(choice, depth + 1)
            if mod is not None:
                fn = _MODIFIERS.get(mod)
                if fn is None:
                    raise GrammarError(f"未知修饰符：{mod}")
                expanded = fn(expanded)
            return expanded

        return _TOKEN.sub(repl, text)

    def _one(self) -> str:
        return self._expand(f"#{self.start}#", 0).strip()

    def generate(self, n: int = 1) -> list[str]:
        return [self._one() for _ in range(int(n))]


def grammar_names(grammar: dict, n: int = 1, *, seed: int = 0,
                  start: str = "origin") -> list[str]:
    """文法命名的一行式入口（等价 ``GrammarGenerator(...).generate(n)``）。"""
    return GrammarGenerator(grammar, seed=seed, start=start).generate(n)
