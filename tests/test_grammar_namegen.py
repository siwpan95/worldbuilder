"""文法式命名（Tracery 思路）测试：只验证"展开正确 / 递归收敛 / 修饰符 /
确定性"，不测"好不好听"。

GrammarGenerator 是 NameGenerator(Markov) 之外的另一种命名源——从产生式
规则而非语料产出字符串。自研，不搬 Tracery 的 JS 实现。
"""

import pytest

import worldbuilder as wb
from worldbuilder.namegen import GrammarGenerator, GrammarError


_GRAMMAR = {
    "origin": ["#adj# #noun#", "#noun# of #place#"],
    "adj": ["red", "old", "silent"],
    "noun": ["thorn", "river", "mount", "fen"],
    "place": ["the west", "the north"],
}


def test_deterministic_per_seed():
    a = wb.grammar_names(_GRAMMAR, 20, seed=1)
    b = wb.grammar_names(_GRAMMAR, 20, seed=1)
    assert a == b


def test_no_unexpanded_tokens():
    names = wb.grammar_names(_GRAMMAR, 50, seed=2)
    assert names, "应产出若干名字"
    for n in names:
        assert "#" not in n, f"名字里残留未展开符号：{n!r}"
        assert n.strip() == n


def test_recursion_resolves():
    # 多层引用：a -> x, b -> #c#, c -> y，最终应拼出 "x y"
    g = {"origin": ["#a# #b#"], "a": ["x"], "b": ["#c#"], "c": ["y"]}
    names = wb.grammar_names(g, 10, seed=0)
    for n in names:
        assert n.replace(" ", "") == "xy", n


def test_modifier_cap():
    g = {"origin": ["#noun.cap#"], "noun": ["thorn", "river"]}
    names = wb.grammar_names(g, 20, seed=3)
    for n in names:
        assert n[:1].isupper(), f"cap 修饰应首字母大写：{n!r}"


def test_modifier_a_article():
    g = {"origin": ["#noun.a#"], "noun": ["orc", "elf"]}
    names = wb.grammar_names(g, 20, seed=4)
    for n in names:
        assert n.startswith("a ") or n.startswith("an "), n


def test_list_rules_equal_weight():
    # 两个候选等概率，多次采样应两样都出现
    g = {"origin": ["alpha", "beta"]}
    seen = set(wb.grammar_names(g, 200, seed=5))
    assert {"alpha", "beta"}.issubset(seen)


def test_undefined_symbol_raises():
    with pytest.raises(GrammarError):
        GrammarGenerator({"origin": ["#ghost#"]}).generate(1)


def test_unknown_modifier_raises():
    with pytest.raises(GrammarError):
        GrammarGenerator({"origin": ["#noun.nope#"], "noun": ["x"]}).generate(1)


def test_missing_start_symbol_raises():
    with pytest.raises(ValueError):
        GrammarGenerator({"foo": ["x"]})


def test_self_reference_raises():
    # a -> #a# 永不收敛，应被深度护栏拦下（而不是死循环）
    with pytest.raises(GrammarError):
        GrammarGenerator({"origin": ["#a#"], "a": ["#a#"]}, max_depth=16).generate(1)


def test_generate_count():
    assert len(wb.grammar_names(_GRAMMAR, 7, seed=0)) == 7
