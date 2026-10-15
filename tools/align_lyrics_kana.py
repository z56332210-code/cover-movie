"""kana() normaliser shared by align_lyrics.py and render.py"""
import pykakasi
kks = pykakasi.kakasi()
def kana(s):
    s = s.replace("IQ", "あいきゅー").replace("THE END", "じえんど").replace("My God", "まいごっど").replace("Oh my god", "おーまいごっど")
    s = s.replace("I want you", "あいうぉんちゅー").replace("I hate you", "あいへいちゅー").replace("Gott ist tot", "ごっといすとと")
    out = "".join(x["hira"] for x in kks.convert(s))
    out = out.replace("ぅ", "う").replace("ぃ", "い").replace("ゅ", "ゆ").replace("ょ", "よ").replace("ゃ", "や").replace("っ", "つ").replace("ー", "う")
    return "".join(ch for ch in out if "ぁ" <= ch <= "ゟ")

