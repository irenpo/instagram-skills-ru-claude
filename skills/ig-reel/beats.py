#!/usr/bin/env python3
"""
beats.py - превращает сценарий рилс в покадровый тайминг до съёмки.

Русская адаптация beats.py из github.com/Jakeschincariol/instagram-agent-skill
(MIT, коммит d03c56b). Понимает русский и английский. Темп по умолчанию
150 слов в минуту (средняя русская речь в кадре), свой темп задаётся --wpm.
Одна строка сценария = один бит. Никаких сетевых запросов.

Запуск
  python3 beats.py script.txt --target 30
  python3 beats.py script.txt --wpm 140 --target 45
  python3 beats.py script.txt --json

Original description:

Estimates how long each line takes to say, stacks them into timecodes, and
flags the four things that kill a Reel in the edit: a hook that runs past the
three-second mark, a beat long enough for the viewer to leave, a run of lines
with nothing concrete in them, and a total length that does not match what you
said you were making.

The timings are an estimate from word count at a words-per-minute rate. They
are close enough to plan an edit and not a substitute for recording it. Set
your own rate with --wpm once you have timed yourself reading a script out
loud: most people land between 150 and 200, and the default here is 165.

Usage
  python3 beats.py script.txt
  python3 beats.py script.txt --target 30
  python3 beats.py script.txt --wpm 185 --target 45
  pbpaste | python3 beats.py -
  python3 beats.py script.txt --json
"""

import argparse
import json
import re
import sys

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9$₽%'’-]+")
SENT_RE = re.compile(r"[^.!?]+[.!?]*")
CONCRETE_RE = re.compile(r"\$\s?\d|\d|₽|(?<!^)(?<![.!?] )\b[A-ZА-ЯЁ][a-zа-яё]{2,}\b|\b[A-Z][A-Za-z]*[A-Z0-9][A-Za-z0-9]*\b"
                         r"|\b(?:тысяч|миллион|рубл|процент|вдвое|втрое|полтора|полгода)", re.MULTILINE | re.IGNORECASE)
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on", "for",
    "with", "that", "this", "it", "is", "are", "was", "were", "be", "been",
    "you", "your", "i", "my", "me", "we", "our", "they", "them", "he", "she",
    "so", "just", "not", "no", "do", "did", "does", "have", "has", "had",
    "will", "can", "at", "as", "by", "from", "out", "up", "off", "one", "all",
    "и", "а", "но", "или", "в", "во", "на", "с", "со", "к", "ко", "по", "за", "из", "у",
    "о", "об", "от", "до", "для", "про", "без", "что", "это", "этот", "эта", "так", "как",
    "я", "ты", "вы", "мы", "он", "она", "они", "мне", "меня", "тебе", "тебя", "вам", "вас",
    "мой", "моя", "мои", "твой", "твоя", "ваш", "наш", "не", "ни", "да", "нет", "же", "ли",
    "бы", "уже", "еще", "ещё", "все", "всё", "вот", "тут", "там", "был", "была", "было",
    "есть", "будет", "просто", "только", "очень", "когда", "если", "чтобы", "потому",
}

HOOK_WINDOW = 3.0        # seconds. Past this, the thumb has already decided.
MAX_BEAT = 4.0           # seconds on one idea with no change on screen.
ABSTRACT_RUN = 3         # beats in a row with nothing checkable in them.


def words(text):
    # «60 000» и «$18,000» произносятся как одно число, считаем одним словом.
    return WORD_RE.findall(re.sub(r"(?<=\d)[ \u00a0\u202f,](?=\d{3}\b)", "", text))


def stem(w):
    # Грубая основа слова: русские окончания меняются, «свадьба» и «свадьбу» — одно.
    w = w.lower().replace("ё", "е")
    return w[:5] if re.match(r"[а-я]", w) else w


def pretty(token):
    """Put the thousands separator back for display."""
    return re.sub(r"(\d)(?=(\d{3})+$)", r"\1 ", token)


def tc(seconds):
    m, s = divmod(seconds, 60)
    return f"{int(m)}:{s:04.1f}"


def split_beats(raw, wps):
    """One line is one beat, unless a line is too long to be one."""
    beats = []
    for line in [l.strip() for l in raw.splitlines()]:
        if not line:
            continue
        if len(words(line)) / wps <= MAX_BEAT * 1.5:
            beats.append(line)
            continue
        # Long paragraph: break it at sentence ends so the timings mean
        # something, and let the report say it was split.
        parts = [p.strip() for p in SENT_RE.findall(line) if p.strip()]
        buf = ""
        for part in parts:
            candidate = (buf + " " + part).strip()
            if buf and len(words(candidate)) / wps > MAX_BEAT:
                beats.append(buf)
                buf = part
            else:
                buf = candidate
        if buf:
            beats.append(buf)
    return beats


def analyse(raw, wpm=150, target=None):
    wps = wpm / 60.0
    beats = split_beats(raw, wps)
    if not beats:
        return None

    rows, clock = [], 0.0
    for i, text in enumerate(beats):
        n = len(words(text))
        dur = n / wps
        rows.append({
            "n": i + 1,
            "start": round(clock, 2),
            "dur": round(dur, 2),
            "words": n,
            "text": text,
            "concrete": len(CONCRETE_RE.findall(text)),
            "label": "",
            "flags": [],
        })
        clock += dur
    total = clock

    # Label the structural positions a Reel is actually built around.
    for r in rows:
        if r["n"] == 1 or r["start"] + r["dur"] <= HOOK_WINDOW:
            r["label"] = "ХУК"
    rows[-1]["label"] = "ПРИЗЫВ" if rows[-1]["label"] != "ХУК" else "ХУК/ПРИЗ"
    half = total / 2
    for r in rows:
        if not r["label"] and r["start"] <= half < r["start"] + r["dur"]:
            r["label"] = "СЕРЕДИНА"

    notes = []
    if rows[0]["dur"] > HOOK_WINDOW:
        rows[0]["flags"].append(f"хук идёт {rows[0]['dur']:.1f} с, дольше {HOOK_WINDOW:.0f} с")
        notes.append(f"Бит 1 звучит {rows[0]['dur']:.1f} с. Сократи до "
                     f"{int(HOOK_WINDOW * wps)} слов, иначе хук прозвучит, когда "
                     "зритель уже решил листать.")
    if rows[0]["concrete"] == 0:
        notes.append("В бите 1 нет ни цифры, ни имени. Хуки без проверяемой "
                     "конкретики пролистывают.")

    for r in rows:
        if r["dur"] > MAX_BEAT:
            r["flags"].append(f"{r['dur']:.1f} с на одном бите")
    long_beats = [r["n"] for r in rows if r["dur"] > MAX_BEAT]
    if long_beats:
        notes.append(f"Бит(ы) {', '.join(map(str, long_beats))} дольше {MAX_BEAT:.0f} с. "
                     "Раздели фразу или поменяй картинку внутри неё (зум на тебя, плашка за спиной). "
                     "На статичном кадре зрители уходят.")

    run, start = 0, None
    for r in rows:
        if r["concrete"] == 0:
            run += 1
            start = start if start is not None else r["n"]
            if run == ABSTRACT_RUN:
                notes.append(f"В битах {start}-{r['n']} нет конкретики. "
                             "Добавь цифру, имя или цену хотя бы в один.")
        else:
            run, start = 0, None

    # Does the last line hand you back to the first one?
    first = {stem(w): w for w in words(rows[0]["text"]) if w.lower() not in STOPWORDS}
    last = {stem(w) for w in words(rows[-1]["text"]) if w.lower() not in STOPWORDS}
    loop = sorted(pretty(first[s]) for s in set(first) & last)
    if loop:
        notes.append(f"Есть петля: последний бит повторяет «{', '.join(loop[:3])}» из хука. "
                     "Повторные просмотры — бесплатный охват.")
    else:
        notes.append("Петли нет. Последний бит не повторяет ни одного слова из хука, ролик "
                     "обрывается. Повтори одно слово из бита 1 — это самый дешёвый повторный просмотр.")

    if target:
        delta = total - target
        if abs(delta) <= target * 0.1:
            notes.append(f"Длина в цель ({total:.1f} с при цели {target} с).")
        elif delta > 0:
            notes.append(f"На {delta:.1f} с длиннее цели. Убери примерно {int(delta * wps)} слов.")
        else:
            notes.append(f"На {-delta:.1f} с короче цели. Добавь {int(-delta * wps)} слов "
                         "или оставь коротким. Обычно короткий вариант лучше.")

    return {
        "wpm": wpm, "target": target,
        "total_seconds": round(total, 2),
        "total_words": sum(r["words"] for r in rows),
        "beats": rows,
        "notes": notes,
    }


def render(a, out=sys.stdout):
    head = (f"ТАЙМИНГ  ·  {a['total_words']} слов  ·  ~{a['total_seconds']:.1f} с "
            f"при {a['wpm']:g} сл/мин" + (f"  ·  цель {a['target']:g} с" if a["target"] else ""))
    print("\n" + head, file=out)
    print("=" * max(len(head), 72), file=out)
    for r in a["beats"]:
        label = f"{r['label']:<9}" if r["label"] else " " * 9
        print(f"  {tc(r['start'])}  {r['dur']:4.1f}с  {label}{r['text']}", file=out)
        for f in r["flags"]:
            print(f"  {'':>6}  {'':>5}  {'':<9}^ {f}", file=out)
    print("-" * max(len(head), 72), file=out)
    for n in a["notes"]:
        print(f"  - {n}", file=out)
    print("", file=out)


def main():
    ap = argparse.ArgumentParser(description="Time a Reel script into a beat sheet.")
    ap.add_argument("input", nargs="?", default="-", help="script file, or - for stdin")
    ap.add_argument("--wpm", type=float, default=150, help="темп речи, слов в минуту (по умолчанию 150)")
    ap.add_argument("--target", type=float, help="target length in seconds")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    a = analyse(raw, wpm=args.wpm, target=args.target)
    if not a:
        print("пустой сценарий", file=sys.stderr)
        sys.exit(2)
    if args.json:
        print(json.dumps(a, indent=2, ensure_ascii=False))
    else:
        render(a)
    sys.exit(0)


if __name__ == "__main__":
    main()
