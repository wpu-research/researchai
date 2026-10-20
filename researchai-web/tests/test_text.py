from app import text


def test_cite_numbers_lists_and_ranges():
    assert text.cite_numbers("A [3]. B [2, 5] ve [4-6].") == [3, 2, 5, 4, 6]


def test_sentences_split_turkish():
    s = text.sentences("Birinci cümle [1]. İkinci cümle ölçüldü [2].\n\nÜçüncü paragraf.")
    assert s == ["Birinci cümle [1].", "İkinci cümle ölçüldü [2].", "Üçüncü paragraf."]


def test_renumber_by_first_appearance():
    secs, order = text.renumber([{"title": "G", "text": "x [7]. y [3, 7]."}, {"title": "S", "text": "z [12]."}])
    assert order == [7, 3, 12]
    assert secs[0]["text"] == "x [1]. y [2, 1]." and secs[1]["text"] == "z [3]."


def test_similarity_flags_copied_sentence_only():
    src = {1: "the sublime in digital art transforms our relation to nature and technology in the anthropocene"}
    sents = ["The sublime in digital art transforms our relation to nature and technology [1].",
             "Bu cümle tamamen özgün ve kaynakla hiçbir ortak dizisi olmayan bir yorumdur."]
    flags = text.similarity_report(sents, src)
    assert [f["sentence_index"] for f in flags] == [0] and flags[0]["source"] == 1


def test_apa_and_bibtex():
    p = {"title": "Yüce ve Doğa", "authors": ["Özselçuk, Ceren", "Ali Veli"], "year": 2023, "venue": "Sanat Dergisi",
         "doi": "10.1/x_y"}
    assert text.apa(p) == "Özselçuk, C., & Veli, A. (2023). Yüce ve Doğa. *Sanat Dergisi*. https://doi.org/10.1/x_y"
    used = set()
    k1, k2 = text.bibkey(p, used), text.bibkey(p, used)
    assert k1 == "ozselcuk2023yuce" and k2 == "ozselcuk2023yuceb"
    assert "doi = {10.1/x_y}" in text.bibtex(p, k1)


def test_latex_escapes_and_cites():
    tex = text.to_latex("A & B", "öz", [{"title": "Giriş", "text": "%50 oran [4]."}], {4: "k4"}, "tr")
    assert r"\%50 oran \cite{k4}." in tex and r"A \& B" in tex and "[turkish]{babel}" in tex
