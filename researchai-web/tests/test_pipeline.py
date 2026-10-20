from app.pipeline import strip_heading, summarize_claims


def test_strip_heading_removes_repeated_title_lines():
    assert strip_heading("## Tartışma\n\nMetin [1].", "Tartışma") == "Metin [1]."
    assert strip_heading("Tartışma:\nMetin.", "Tartışma") == "Metin."
    assert strip_heading("Tartışma bulguları şunu gösterir.", "Tartışma") == "Tartışma bulguları şunu gösterir."


def test_summarize_counts_flags_and_verdicts():
    claims = [{"refs": [1], "flag": None, "verdicts": {"1": {"v": "yes"}}},
              {"refs": [], "flag": "not_in_results", "verdicts": {}},
              {"refs": [2], "flag": None, "verdicts": {"2": {"v": "no"}}}]
    s = summarize_claims(claims)
    assert (s["cited"], s["yes"], s["no"], s["not_in_results"]) == (2, 1, 1, 1)


def test_pick_databases_filters_unknown_and_falls_back():
    from app.pipeline import pick_databases
    out = pick_databases([{"name": "eric", "reason": "eğitim"}, {"name": "yok"}, "eric", "openalex"])
    assert [d["name"] for d in out] == ["eric", "openalex"]
    assert out[0]["reason"] == "eğitim"
    assert [d["name"] for d in pick_databases(None)] == ["openalex", "crossref", "semantic_scholar", "arxiv", "trdizin"]
