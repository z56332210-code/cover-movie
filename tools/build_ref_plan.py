"""Reference shot list (cut times from frame_features block-diff + 0.5 s contact sheets, read by eye) -> scene_plan.json draft.
Times are video-frame times + 0.033 s (video stream starts 1 frame after audio), so they sit on the audio clock.
Lengths are converted to beats/bars on the reference grid (152 BPM, 4/4)."""
import json
import numpy as np

A = json.load(open("data/ref_analysis.json"))
DB0, BEAT = A["downbeats"][0], 60 / 152.0
OFF = 0.033
# t0(raw video time), type, lyric method, transition into this shot, section, note
# types: A colour / B mono manga / C silhouette / D magenta-solid or black / E grey+motion blur
# methods: 1 navy box + white text, 1b small white horizontal (no box), 2 vertical + black bars, 2b small white vertical (no bar),
#          3 diagonal band along a prop, 4 giant cut glyphs, 5 small text in ink-blot centre, 6 magenta bold slanted (keyword/credit), - none
S = [
 (0.00, "D", "-", "start", "silence", "black"),
 (1.20, "D", "-", "flash_magenta", "silence", "magenta solid 0.4s"),
 (1.60, "C", "title", "cut", "intro", "key visual: silhouette + props around, handwritten title logo, tiny glitch strips"),
 (13.80, "D", "-", "black", "intro", "black gap ~1 beat"),
 (14.27, "A", "1b", "cut", "verse1", "prop close-up (sheep/syringe/pill), ink + halftone, slow pan"),
 (20.13, "A", "3", "cut", "verse1", "prop close-up guitar/harp, band text along guitar neck, words revealed in chunks"),
 (23.23, "D", "-", "black", "verse1", "black gap"),
 (23.73, "A", "1", "cut", "verse1", "character close-up (eye bar), navy box text right, fast zoom-out then settle"),
 (26.47, "D", "-", "black", "verse1", "black gap"),
 (26.93, "C", "2b", "cut", "verse1", "key visual silhouette, frequent glitch strips"),
 (32.70, "D", "-", "black", "verse1", "black gap"),
 (33.20, "A", "1b", "cut", "verse1", "prop close-up harp/guitar, small white text"),
 (39.10, "D", "-", "black", "verse1", "black gap"),
 (39.50, "A", "3", "cut", "verse1", "props mid, two-line diagonal band"),
 (42.27, "D", "-", "black", "verse1", "black gap"),
 (42.70, "A", "1", "cut", "verse1", "character close-up, navy box text left"),
 (45.17, "D", "-", "black", "pre", "black gap"),
 (45.47, "A", "5", "cut", "pre", "lavender + magenta ink blot, small vertical text in blot centre"),
 (47.13, "C", "2b", "cut", "pre", "silhouette bust in ink, small vertical text both sides"),
 (50.50, "C", "2b", "ink_wipe", "pre", "magenta ink blobs grow in steps (~0.1s) to cover frame in ~1s"),
 (51.47, "D", "-", "flash_navy", "pre", "navy solid 0.27s"),
 (51.73, "C", "2b", "cut", "pre", "key visual silhouette, small vertical text"),
 (57.00, "C", "6", "cut", "pre", "big white slanted 'ベノベノム' over silhouette (no cut, text event)"),
 (57.80, "D", "small", "flash_magenta", "pre", "magenta solid, tiny text"),
 (58.87, "D", "-", "cut", "pre", "navy solid"),
 (59.27, "D", "-", "black", "pre", "black, framed manga panel flickers in (B inset) then magenta ink blobs"),
 (60.90, "D", "small", "ink_wipe", "pre", "magenta solid + white italic 'あらま' (pickup)"),
 (61.53, "A", "4", "cut", "chorus1", "character wide + giant cut glyphs magenta/navy, one glyph per syllable, pop-in"),
 (66.37, "A", "5", "cut", "chorus1", "ink blot centre text"),
 (67.90, "A", "4", "cut", "chorus1", "giant glyphs 存在感 then ink blobs"),
 (68.80, "D", "2b", "ink_wipe", "chorus1", "magenta ink field, white vertical text"),
 (69.47, "A", "2b", "cut", "chorus1", "props + ink, white vertical text"),
 (70.17, "D", "small", "black", "chorus1", "black + tiny text"),
 (71.03, "A", "4", "cut", "chorus1", "giant 愛/哀 split magenta|navy"),
 (73.80, "A", "4", "cut", "chorus1", "close-up 'めっ!' navy glyphs"),
 (74.23, "A", "-", "cut", "interlude1", "props wide + ink, no lyric, slow zoom"),
 (86.43, "D", "-", "black", "interlude1", "black gap"),
 (86.87, "B", "1", "cut", "verse2", "mono manga props, white bg + halftone, navy box text"),
 (90.00, "B", "4", "cut", "verse2", "giant black glyph rows over manga props (text event)"),
 (92.77, "D", "-", "black", "verse2", "black gap"),
 (93.17, "B", "4", "cut", "verse2", "mono character + giant black glyphs"),
 (98.80, "D", "-", "black", "verse2", "black gap"),
 (99.33, "B", "2", "cut", "pre2", "mono character, magenta accents kept, vertical text on black bars"),
 (106.00, "B", "6", "cut", "pre2", "giant magenta slanted glyphs over mono character (text event)"),
 (111.53, "D", "-", "black", "pre2", "black + magenta ink blobs"),
 (112.40, "D", "6", "ink_wipe", "pre2", "magenta solid, big white italic 'あら'"),
 (113.63, "A", "4", "cut", "chorus2", "character wide + giant glyphs (chorus1 layout reused)"),
 (118.47, "A", "5", "cut", "chorus2", "ink blot centre text"),
 (120.00, "A", "4", "cut", "chorus2", "giant 存在 then ink blobs"),
 (120.90, "D", "2b", "ink_wipe", "chorus2", "magenta field, white vertical text"),
 (121.57, "A", "2b", "cut", "chorus2", "props + ink, white vertical text"),
 (122.27, "D", "small", "black", "chorus2", "black + tiny text"),
 (123.13, "A", "4", "cut", "chorus2", "giant 愛/哀 split"),
 (125.90, "A", "4", "cut", "chorus2", "close-up 'めっ!'"),
 (126.33, "A", "credit", "cut", "interlude2", "character wide, credits one by one (vocal/mix/Illustration/Movie), ~4 bars each"),
 (151.60, "E", "4", "cut", "bridge", "grey character + motion blur on white, blurred giant magenta glyphs, magenta slice glitch"),
 (157.90, "A", "4", "cut", "chorus3", "character wide + giant glyphs, pills denser"),
 (164.17, "E", "-", "grey_blur", "chorus3", "white/grey motion-blur whip 0.6s"),
 (164.83, "A", "4", "cut", "chorus3", "giant glyphs, navy pills fill background"),
 (169.03, "A", "5", "cut", "chorus3", "ink blot centre text"),
 (170.57, "A", "4", "cut", "chorus3", "giant 存在 then ink blobs -> magenta field"),
 (172.13, "A", "2b", "cut", "chorus3", "props + ink, white vertical text"),
 (172.83, "D", "small", "black", "chorus3", "black + tiny text"),
 (173.70, "A", "4", "cut", "chorus3", "giant 愛/哀 split"),
 (176.47, "A", "2", "cut", "chorus3", "tighter character crop, vertical black bars, 'さけぶベノム' magenta"),
 (179.60, "A", "6", "cut", "outro", "face close-up (only once), title logo then 'music' credit"),
 (195.50, "D", "-", "ink_wipe_black", "end", "black ink blobs close the frame"),
 (196.07, "D", "-", "black", "end", "black to end"),
]
END = 203.25
shots = []
for i, (t0, ty, m, tr, sec, note) in enumerate(S):
    t1 = S[i + 1][0] if i + 1 < len(S) else END
    a, b = t0 + OFF, t1 + OFF
    shots.append(dict(i=i, t0=round(a, 3), t1=round(min(b, END), 3), dur=round(b - a, 3),
                      beats=round((b - a) / BEAT, 2), bars=round((b - a) / BEAT / 4, 2),
                      start_bar=round((a - DB0) / BEAT / 4, 2), type=ty, method=m, trans_in=tr, section=sec, note=note))
sections = {}
for s in shots:
    d = sections.setdefault(s["section"], dict(t0=s["t0"], t1=s["t1"]))
    d["t1"] = s["t1"]
json.dump(dict(source="reference.mp4 (Venom cover), 203.25 s, 1280x720 30fps",
               bpm=152.0, beat_s=round(BEAT, 5), bar_s=round(4 * BEAT, 5), first_downbeat=DB0, cut_lead_frames=2,
               palette={"lav": "#F1B5FB", "mag": "#EB008D", "navy": "#15183C", "white": "#FFFFFF", "black": "#000000"},
               sections=sections, shots=shots), open("scene_plan.json", "w"), ensure_ascii=False, indent=1)
print(len(shots), "shots")
