"""Canlı altın küme: gerçek / yazarı değiştirilmiş / uydurma atıflar. Ağ gerektirir."""
import asyncio, json, sys
from researchai_mcp.verify import Citation, verify_citation

REAL = [  # (başlık, yazarlar, yıl, doi)
 ("Visual indeterminacy in GAN art", ["Hertzmann, A."], 2020, "10.1162/leon_a_01930"),
 ("Deconstructing the algorithmic sublime", ["Ames, M. G."], 2018, "10.1177/2053951718779194"),
 ("Geology of mankind", ["Crutzen, P. J."], 2002, "10.1038/415023a"),
 ("Atlas of AI", ["Crawford, K."], 2021, "10.12987/9780300252392"),
 ("The digital sublime: Myth, power, and cyberspace", ["Mosco, V."], 2004, None),
 ("American technological sublime", ["Nye, D. E."], 1994, None),
 ("Caspar David Friedrich and the subject of landscape", ["Koerner, J. L."], 2009, None),
 ("AI art: Machine visions and warped dreams", ["Zylinska, J."], 2020, None),
 ("Purposeful sampling for qualitative data collection and analysis in mixed method implementation research", ["Palinkas, L. A."], 2015, None),
 ("Sanat ve tasarım alanında üretken yapay zeka sistemleri", ["Coşkun, C."], 2024, "10.21602/sduarte.1480840"),
 # Türkçe, DOI'siz (başlık araması TR Dizin'e de düşer)
 ("Sanat ve tasarım alanında üretken yapay zeka sistemleri", ["Coşkun, C."], 2024, None),
 ("Antroposen çağında ekolojik sanat: David Buckland, Terike Haapoja ve Mel Chin'in ekolojik sanat projeleri", ["Çakıroğlu, E."], 2022, None),
 ("Tasarımda yeni yaklaşımlar: Refik Anadol ve makine hatıraları", ["Çelenk, A.", "Kurak Açıcı, F."], 2022, None),
]
WRONG_AUTHOR = [(t, ["Kowalski, Z."], y, None) for t, _, y, _ in REAL[:5] + REAL[10:12]]  # doi'siz: aranmalı
FABRICATED = [
 ("Recursive pigeon aesthetics in the post-digital Anthropocene sublime", ["Varga, L."], 2021, None),
 ("Algorithmic romanticism and the thermodynamics of generative landscapes", ["Okonkwo, T."], 2022, None),
 ("Immersive hyperobjects: a neural phenomenology of scale", ["Lindqvist, A."], 2023, None),
 ("Algoritmik romantizmin postdijital Antroposen estetiğinde yinelemeli güvercin kuramı", ["Demirtaş, K."], 2022, None),
]

async def one(kind, row):
    t, a, y, d = row
    r = await verify_citation(Citation(t, a, y, d))
    return kind, t[:55], r["status"], r["confidence"]

async def main():
    out = []
    for kind, rows in (("REAL", REAL), ("WRONG_AUTHOR", WRONG_AUTHOR), ("FABRICATED", FABRICATED)):
        for row in rows:
            out.append(await one(kind, row)); await asyncio.sleep(0.5)
    for o in out: print(*o, sep=" | ")
    from collections import Counter
    print(Counter((k, s) for k, _, s, _ in out))
asyncio.run(main())
