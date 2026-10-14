#!/usr/bin/env python3
"""
caption.py - проверка подписи к посту Instagram и показ того, что видно в ленте
до «... ещё».

Русская адаптация caption.py из github.com/Jakeschincariol/instagram-agent-skill
(MIT, коммит d03c56b). Понимает русские призывы («пиши ПРОМПТ в комментариях»,
«сохрани», «ссылка в шапке»), русские хэштеги и домены (.ru, .рф, boosty.to).
Длинное тире «—» допустимо и не считается ошибкой. Никаких сетевых запросов.

Запуск
  python3 caption.py caption.txt
  python3 caption.py caption.txt --keywords "монтаж свадьбы,нейросеть для видеографа"
  python3 caption.py caption.txt --json

Original description:
caption.py - lint an Instagram caption and show exactly what the feed shows
before the "... more".

Instagram gives a caption about 125 characters in the feed and hides the rest
behind a tap. Almost every caption that fails, fails there: the hook is in
sentence three, or the first line is a greeting, or the whole thing opens on a
hashtag. This prints the visible window as a box so you can read it the way a
scrolling stranger does, then checks the eight things that are worth checking.

The 125-character cut is an approximation. The real number moves with the
device, the font size and where your line breaks fall, which is exactly why
you want a margin rather than a caption engineered to end at 125. Change it
with --truncate if you want to test a tighter one.

Usage
  python3 caption.py caption.txt
  python3 caption.py caption.txt --keywords "proposal software,client contract"
  pbpaste | python3 caption.py -
  python3 caption.py caption.txt --json
"""

import argparse
import json
import re
import sys
import textwrap

LIMIT = 2200             # Instagram's hard caption limit.
TRUNCATE = 125           # Roughly where the feed cuts to "... more".
HASHTAG_LIMIT = 5        # Instagram's cap per post or reel since 18 Dec 2025,
                         # down from 30. Announced by the @Creators account:
                         # "using fewer (up to 5) more targeted hashtags,
                         # rather than many generic ones, can improve both your
                         # content's performance and people's experience".

HASHTAG_RE = re.compile(r"(?:^|\s)(#\w+)")
MENTION_RE = re.compile(r"(?:^|\s)(@[A-Za-z0-9_.]+)")
LINK_RE = re.compile(r"https?://\S+|\bwww\.\S+|\b[a-zа-я0-9-]+\.(?:com|co|io|net|org|ai|app|ru|рф|su|to|me|by|kz|cc)\b/?\S*",
                     re.IGNORECASE)
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF☀-➿←-⇿️]")
CONCRETE_RE = re.compile(r"\$\s?\d|\d+|(?<!^)(?<![.!?] )\b[A-ZА-ЯЁ][a-zа-яё]{2,}\b|\b[A-Z][A-Za-z]*[A-Z0-9][A-Za-z0-9]*\b", re.MULTILINE)

ASKS = [
    (re.compile(r"(?i:\b(?:пиши|напиши|пишите|напишите|оставь|оставьте|отправь|отправьте|жми|кидай|кинь)\b)"
                r"[^.!?\n]{0,40}?[«\"“]?\b[A-ZА-ЯЁ0-9]{3,}\b"), "comment a keyword"),
    (re.compile(r"(?i)\b(?:пиши|напиши|напишите|пишите) (?:мне )?(?:в )?(?:директ|личк|лс)\w*"), "DM me"),
    (re.compile(r"(?i)\b(?:сохрани|сохраните|сохраняй|сохраняйте)\b"), "save this"),
    (re.compile(r"(?i:\b(?:отправь|отправьте|перешли|перешлите|поделись|поделитесь|покажи (?:это|подруге|другу))\b)(?![^.!?\n]{0,40}?\b[A-ZА-ЯЁ]{3,}\b)"), "share this"),
    (re.compile(r"(?i)\bподпи(?:шись|шитесь|сывайся|сывайтесь)\b"), "follow"),
    (re.compile(r"(?i)\bссылк\w* (?:в|во) (?:шапке|профиле|био|описании профиля)\b"), "link in bio"),
    (re.compile(r"(?i)\b(?:листай|листайте|лист(?:ай)? (?:вправо|влево)|свайп\w*)\b"), "swipe or tap"),
    (re.compile(r"(?i)\b(?:а (?:ты|вы|у тебя|у вас)\b[^.!?\n]{0,60}\?|расскажи(?:те)?\b|как (?:думаешь|думаете)|напиши(?:те)? в комментари\w*,? (?:как|что|какой|какая|какие))"), "answer a question"),
    (re.compile(r"(?i)\bcomment (?:the word |\")?[A-Z0-9]{2,}\b"), "comment a keyword"),
    (re.compile(r"(?i)\b(?:dm|message) me\b"), "DM me"),
    (re.compile(r"(?i)\bsave (?:this|it)\b"), "save this"),
    (re.compile(r"(?i)\bshare (?:this|it)\b"), "share this"),
    (re.compile(r"(?i)\bfollow (?:me|for)\b"), "follow"),
    (re.compile(r"(?i)\blink in (?:my )?bio\b"), "link in bio"),
    (re.compile(r"(?i)\b(?:swipe|tap) (?:through|left|right|for|to)\b"), "swipe or tap"),
    (re.compile(r"(?i)\btell me\b|\bwhat would you\b|\bwhich one\b"), "answer a question"),
]

FILLER_TAGS = {"#viral", "#fyp", "#explore", "#explorepage", "#foryou", "#foryoupage",
               "#trending", "#instagood", "#love", "#follow", "#like4like", "#reels",
               "#reelsinstagram", "#viralreels", "#instadaily",
               "#рек", "#реки", "#рекомендации", "#хочуврек", "#хочувтоп", "#врек", "#топ",
               "#популярное", "#тренды", "#рилс", "#рилсы", "#инстаграм", "#лайк", "#подписка",
               "#взаимнаяподписка", "#лайкзалайк", "#втоп", "#хочувпопулярное", "#вреки"}


ASK_RU = {"comment a keyword": "кодовое слово в комментариях", "DM me": "написать в директ",
          "save this": "сохранить", "share this": "отправить другу", "follow": "подписаться",
          "link in bio": "ссылка в шапке", "swipe or tap": "листать", "answer a question": "ответить на вопрос"}
STATUS_RU = {"PASS": "ОК", "WARN": "ВНИМ", "FAIL": "ОШИБКА"}
VERDICT_RU = {"READY": "ГОТОВО", "REVIEW": "ПРОВЕРЬ ПРЕДУПРЕЖДЕНИЯ", "FIX": "ИСПРАВЬ"}
CHECK_RU = {"LENGTH": "ДЛИНА", "FIRST LINE": "ПЕРВАЯ СТРОКА", "HOOK IS CONCRETE": "КОНКРЕТИКА",
            "HASHTAGS": "ХЭШТЕГИ", "TAG PLACEMENT": "МЕСТО ХЭШТЕГОВ", "LINKS": "ССЫЛКИ",
            "ONE ASK": "ОДИН ПРИЗЫВ", "EMOJI": "ЭМОДЗИ", "SEARCH TERMS": "ПОИСКОВЫЕ СЛОВА"}


def _stem(w):
    # Русские окончания меняются: «монтаж свадьбы» должно находить «монтажа свадеб».
    w = w.lower().replace("ё", "е")
    if re.match(r"[а-я]", w) and len(w) > 4:
        return w[:max(4, len(w) - 3)][:6]
    return w


def term_in(term, text):
    """Поисковая фраза есть в тексте, если все её слова есть в нём с любыми окончаниями."""
    stems = [_stem(w) for w in re.findall(r"\w+", term) if len(w) > 2]
    if not stems:
        return term.lower() in text.lower()
    tokens = [w.lower().replace("ё", "е") for w in re.findall(r"\w+", text)]
    return all(any(tok.startswith(s) for tok in tokens) for s in stems)


def visible_window(text, cut):
    """What the feed shows. Instagram cuts mid-word, so this does too."""
    flat = text.strip()
    return flat if len(flat) <= cut else flat[:cut]


def render_box(window, truncated, out=sys.stdout, width=52):
    print("\n  ЧТО ВИДНО В ЛЕНТЕ", file=out)
    print("  +" + "-" * (width + 2) + "+", file=out)
    lines = []
    for raw in window.split("\n"):
        lines.extend(textwrap.wrap(raw, width) or [""])
    for line in lines[:8]:
        print(f"  | {line:<{width}} |", file=out)
    tail = "... ещё" if truncated else "(подпись видна целиком)"
    print("  +" + "-" * (width + 2 - len(tail) - 2) + f" {tail} " + "+", file=out)


def analyse(text, cut=TRUNCATE, keywords=None):
    text = text.rstrip()
    stripped = text.strip()
    chars = len(stripped)
    lines = [l for l in stripped.split("\n")]
    first_line = lines[0].strip() if lines else ""
    tags = HASHTAG_RE.findall(stripped)
    mentions = MENTION_RE.findall(stripped)
    links = LINK_RE.findall(stripped)
    emoji = EMOJI_RE.findall(stripped)
    window = visible_window(stripped, cut)
    truncated = chars > cut
    asks = [name for pattern, name in ASKS if pattern.search(stripped)]
    filler = [t for t in tags if t.lower() in FILLER_TAGS]
    keywords = [k.strip() for k in (keywords or []) if k.strip()]

    checks = []

    def add(name, status, detail):
        checks.append({"check": name, "status": status, "detail": detail})

    add("LENGTH", "FAIL" if chars > LIMIT else "PASS",
        f"{chars} / {LIMIT} знаков" + (f", на {chars - LIMIT} больше лимита"
                                           if chars > LIMIT else ""))

    if not first_line:
        add("FIRST LINE", "FAIL", "подпись начинается с пустой строки")
    elif first_line.startswith("#") or first_line.startswith("@"):
        add("FIRST LINE", "FAIL",
            "начинается с хэштега или упоминания, а это единственное место, где нужна фраза")
    elif len(first_line) > cut:
        add("FIRST LINE", "WARN",
            f"{len(first_line)} знаков, обрежется на {cut} посреди мысли. "
            "Нормально, если обрыв интригует, плохо, если режется придаточное")
    else:
        add("FIRST LINE", "PASS", f"{len(first_line)} знаков, видна целиком")

    add("HOOK IS CONCRETE", "PASS" if CONCRETE_RE.search(window) else "WARN",
        f"цифр или имён в видимой части: {len(CONCRETE_RE.findall(window))}"
        + ("" if CONCRETE_RE.search(window) else " — до нажатия нет ничего конкретного"))

    if len(tags) > HASHTAG_LIMIT:
        add("HASHTAGS", "FAIL", f"{len(tags)} хэштегов, лимит Instagram — {HASHTAG_LIMIT}. "
                                "После пятого не работают, а блок выглядит устаревшим")
    elif len(tags) == HASHTAG_LIMIT and filler:
        add("HASHTAGS", "WARN", f"{len(tags)} хэштегов, ровно лимит, и "
                                f"{len(filler)} из них пустые. Потрать пять на темы")
    elif filler:
        add("HASHTAGS", "WARN", f"{len(tags)} хэштегов, {len(filler)} пустых "
                                f"({', '.join(filler[:3])}). Они ничего не описывают")
    else:
        add("HASHTAGS", "PASS", f"хэштегов {len(tags)}" + (f": {' '.join(tags)}" if tags else ""))

    if not tags:
        add("TAG PLACEMENT", "PASS", "хэштегов нет")
    elif any(re.search(r"(?:^|\s)" + re.escape(t) + r"\b", window) for t in tags):
        add("TAG PLACEMENT", "WARN", "хэштег в видимой части ленты, "
                                     "место потрачено на ярлык")
    else:
        add("TAG PLACEMENT", "PASS", "хэштеги под «ещё»")

    add("LINKS", "WARN" if links else "PASS",
        f"ссылок в подписи: {len(links)}, а в подписи они не кликаются. "
        f"Перенеси в шапку профиля или в директ (бот по кодовому слову)" if links else "мёртвых ссылок нет")

    if len(asks) == 1:
        add("ONE ASK", "PASS", f"один призыв: {ASK_RU[asks[0]]}")
    elif not asks:
        add("ONE ASK", "WARN", "призыва нет. Реши, зачем этот пост")
    else:
        add("ONE ASK", "WARN", f"призывов: {len(asks)} ({', '.join(ASK_RU[a] for a in asks)}). "
                               "Два призыва — то же, что ни одного")

    density = len(emoji) * 100 / max(chars, 1)
    add("EMOJI", "WARN" if density > 4 else "PASS",
        f"эмодзи: {len(emoji)}, {density:.1f} на 100 знаков"
        + (" — читается как украшательство" if density > 4 else ""))

    if keywords:
        found = [k for k in keywords if term_in(k, stripped)]
        missing = [k for k in keywords if not term_in(k, stripped)]
        in_window = [k for k in found if term_in(k, window)]
        status = "PASS" if not missing else ("WARN" if found else "FAIL")
        add("SEARCH TERMS", status,
            f"есть {len(found)} из {len(keywords)}"
            + (f", в видимой части: {len(in_window)}" if found else "")
            + (f". Нет: {', '.join(missing)}" if missing else ""))

    fails = sum(1 for c in checks if c["status"] == "FAIL")
    warns = sum(1 for c in checks if c["status"] == "WARN")
    verdict = "FIX" if fails else ("REVIEW" if warns else "READY")

    return {
        "characters": chars, "limit": LIMIT, "truncate_at": cut,
        "visible": window, "truncated": truncated,
        "first_line_chars": len(first_line),
        "hashtags": tags, "mentions": mentions, "links": links,
        "emoji": len(emoji), "asks": asks,
        "checks": checks, "verdict": verdict,
    }


def render(a, out=sys.stdout):
    head = (f"ПРОВЕРКА ПОДПИСИ  ·  {a['characters']} / {a['limit']} знаков  ·  "
            f"хэштегов {len(a['hashtags'])}  ·  призывов {len(a['asks'])}")
    print("\n" + head, file=out)
    print("=" * max(len(head), 62), file=out)
    render_box(a["visible"], a["truncated"], out=out)
    print("", file=out)
    for c in a["checks"]:
        print(f"  {STATUS_RU[c['status']]:<6} {CHECK_RU[c['check']]:<17} {c['detail']}", file=out)
    print("-" * max(len(head), 62), file=out)
    print(f"  ИТОГ  {VERDICT_RU[a['verdict']]}\n", file=out)


def main():
    ap = argparse.ArgumentParser(description="Lint an Instagram caption.")
    ap.add_argument("input", nargs="?", default="-", help="caption file, or - for stdin")
    ap.add_argument("--truncate", type=int, default=TRUNCATE,
                    help=f"characters shown before '... more' (default {TRUNCATE})")
    ap.add_argument("--keywords", default="", help="comma-separated terms you want to be found for")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    a = analyse(raw, cut=args.truncate, keywords=args.keywords.split(","))
    if args.json:
        print(json.dumps(a, indent=2, ensure_ascii=False))
    else:
        render(a)
    sys.exit(0 if a["verdict"] == "READY" else 1)


if __name__ == "__main__":
    main()
