#!/usr/bin/env python3
"""
hookscore.py - оценка первой фразы рилс по пяти свойствам сильных хуков
и ранжирование нескольких вариантов друг против друга.

Русская адаптация hookscore.py из github.com/Jakeschincariol/instagram-agent-skill
(MIT, коммит d03c56b). Понимает русский и английский текст. Длинное тире «—»
допустимо и не штрафуется.

Что это: пять локальных эвристик, считаются на твоём компьютере только по
тексту. Никаких сетевых запросов. Они измеряют то, что объединяет удерживающие
хуки: длину, которую можно сказать за 2-3 секунды, конкретику (цифра, имя,
цена), ставку (что можно потерять), полезное слово в начале фразы и обращение
к зрителю.

Чего это НЕ делает: не предсказывает просмотры. Автор оригинала проверил его на
74 реальных хуках: отличать откровенно слабые хуки от нормальных он умеет
(AUC 0.83), а выбрать победителя из двух хороших почти не может (AUC 0.56).
Используй его, чтобы отсеять приветствия, разгон, абстракцию и слишком длинные
фразы. Какой из двух нормальных хуков выстрелит, решают лицо, монтаж, звук и
показ. Верь графику удержания больше, чем этому скрипту.

Каждая проверка даёт от 0 до 100, больше — лучше.

Запуск
  python3 hookscore.py hooks.txt              # по одному хуку в строке, рейтинг
  python3 hookscore.py --hook "40 000 ₽ — столько мне стоила одна свадьба."
  python3 hookscore.py hooks.txt --json
"""

import argparse
import json
import re
import statistics
import sys

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9$₽%'’-]+")
NUMBER_RE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?"
    r"|\b\d[\d,.]*\s?"
    r"(?:%|₽|руб\w*|тыс\w*|к\b|k\b|x\b|×|раз\w*|час\w*|мин\w*|сек\w*|дн\w*|день|недел\w*|месяц\w*|лет|год\w*"
    r"|hrs?\b|hours?\b|mins?\b|minutes?\b|days?\b|weeks?\b|months?\b|years?\b)?",
    re.IGNORECASE)
PROPER_RE = re.compile(r"(?<!^)(?<![.!?] )(?<![.!?]  )\b[A-ZА-ЯЁ][a-zа-яё]{2,}\b|\b[A-Z][A-Za-z]*[A-Z0-9][A-Za-z0-9]*\b")
HASHTAG_RE = re.compile(r"(?:^|\s)#\w+")
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")


def norm(w):
    return w.lower().strip("'’-").replace("ё", "е")


def stem_hit(token, stems):
    return any(token.startswith(s) for s in stems)


# Числа, сказанные словами, так же конкретны, как цифры.
SPOKEN_NUMBERS = {
    "zero", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "fifteen", "twenty", "thirty", "forty", "fifty",
    "sixty", "seventy", "eighty", "ninety", "hundred", "thousand", "million",
    "billion", "dozen", "half", "twice", "triple",
    "ноль", "два", "две", "двух", "три", "трех", "четыре", "четырех", "пять", "пяти",
    "шесть", "шести", "семь", "семи", "восемь", "восьми", "девять", "девяти",
    "десять", "десяти", "двенадцать", "пятнадцать", "двадцать", "тридцать", "сорок",
    "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто", "сто", "двести",
    "триста", "пятьсот", "полтора", "полторы", "вдвое", "втрое", "дважды", "трижды",
    "половина", "половину", "полгода", "сотня", "сотни", "дюжина",
}
NUMBER_STEMS = ("тысяч", "миллион", "миллиард", "сотн")
MONEY_WORDS = {
    "dollars", "dollar", "bucks", "grand", "percent", "cents",
    "millionaire", "billionaire", "revenue", "profit", "salary", "rent",
    "чек", "₽",
}
MONEY_STEMS = ("руб", "тыс", "процент", "гонорар", "зарплат", "бюджет", "прибыл",
               "выручк", "доход", "аренд", "предоплат", "скидк", "смет", "прайс")

# Слова, которые создают ставку: потерю, запрет, конфликт, отрицание.
STAKES = {
    "stop", "never", "wrong", "mistake", "mistakes", "lost", "lose", "losing",
    "cost", "costs", "broke", "broken", "failed", "failure", "fail", "nobody",
    "no", "not", "don't", "dont", "doesn't", "didn't", "can't", "won't",
    "quit", "quitting", "fired", "deleted", "delete", "killed", "kills", "kill",
    "replaced", "replaces", "cut", "beat", "free", "paid", "charged", "hired",
    "saved", "first", "banned", "illegal", "worst", "hate", "hated", "wasted",
    "waste", "scam", "lie", "lied", "lying", "truth", "secret", "hidden", "stole",
    "stolen", "before", "until", "instead", "but", "except", "unless", "problem",
    "risk", "danger", "warning", "regret", "wish", "should", "shouldn't",
    "still", "already", "only", "without", "versus", "vs", "actually",
    "не", "нет", "ни", "но", "а", "без", "уже", "только", "еще", "до", "пока",
    "вместо", "кроме", "против", "стоп", "хватит", "нельзя", "надо", "зря",
}
STAKES_STEMS = (
    "никогда", "никто", "ничего", "ошиб", "потер", "теря", "стоил", "стоит", "обошл",
    "провал", "слил", "слива", "уволи", "удали", "убива", "убил", "замени", "бесплатн",
    "дорог", "дешев", "запрет", "худш", "ненави", "впуст", "обман", "врут", "вран",
    "правд", "секрет", "скрыва", "скрыт", "украл", "украд", "проблем", "риск", "опасн",
    "предупреж", "жале", "должн", "перестан", "заплат", "сэконом", "экономи", "переплат",
    "на самом деле", "вообще", "молча", "бесит", "страш", "боя", "потрат",
)

# Открывающие слова, которые тратят первую секунду впустую.
WEAK_OPENERS = [
    "so", "ok", "okay", "hey", "hi", "hello", "guys", "yo", "alright",
    "welcome", "today", "basically", "honestly", "look", "listen", "um",
    "just", "let", "lets", "let's", "i wanted", "i want", "one of",
    "have you", "did you", "do you", "are you", "in this", "in today",
    "the thing", "a lot", "there is", "there are", "this is", "it is",
    "as a", "when it", "if you've", "you know",
    "привет", "всем привет", "здравствуйте", "доброе", "итак", "так вот", "ну",
    "короче", "сегодня", "давайте", "давай", "я хочу", "хочу", "в этом", "в общем",
    "кстати", "честно говоря", "наверное", "как вы знаете", "многие", "друзья",
    "ребята", "девочки", "всем", "в сегодняшнем", "ну вот", "я решила", "я тут",
]

IMPERATIVES = {
    "stop", "steal", "copy", "delete", "try", "watch", "read", "save",
    "use", "build", "make", "write", "send", "take", "start", "quit",
    "never", "always", "don't", "dont", "do", "put", "run", "check",
    "стоп", "хватит", "перестань", "перестаньте", "забирай", "забирайте", "сохрани",
    "сохраняй", "сохраните", "попробуй", "попробуйте", "смотри", "смотрите", "удали",
    "используй", "сделай", "напиши", "пиши", "проверь", "начни", "брось", "не",
    "никогда", "запомни", "держи", "лови", "включи", "выключи", "отключи", "поставь",
    "сними", "снимай", "перешли", "отправь", "купи", "не покупай",
}

YOU_RE = re.compile(r"(?i)\b(you|your|you're|youre|yourself|ты|тебя|тебе|тобой|твой|твоя|твое|твоё|твои|"
                    r"твоих|твоим|вы|вас|вам|вами|ваш|ваша|ваше|ваши|ваших|вашим)\b")
ME_RE = re.compile(r"(?i)\b(i|my|me|we|our|я|мой|моя|моё|мое|мои|мне|меня|мной|мы|наш|наша|наше|наши|нас|нам)\b")

DEALBREAKERS = [
    (re.compile(r"(?i)^\s*(?:stop scrolling|don'?t scroll|стоп,? не листай|не листай|не пролистывай|"
                r"подожди,? не листай|досмотри до конца)"),
     "Начинается с «не листай». Просить внимание — значит признать, что ты его ещё не заслужила."),
    (re.compile(r"(?i)\b(?:in (?:this|today'?s) (?:video|reel)|i'?m going to show you|i'?ll show you how|"
                r"в (?:этом|сегодняшнем) (?:видео|ролике|рилсе|рилс)|сейчас я (?:вам |тебе )?(?:расскажу|покажу)|"
                r"я (?:хочу )?(?:вам |тебе )?(?:расскажу|рассказать|показать) (?:о|про|как))\b"),
     "Разгон в духе «в этом видео я расскажу». Удали и начни сразу с главного."),
    (re.compile(r"(?i)^\s*(?:hey |hi |what'?s up |welcome |привет|всем привет|здравствуйте|доброе утро|добрый день|"
                r"добрый вечер|хэй|хай)"),
     "Приветствие. В ленту никто не приходит, чтобы с ним поздоровались."),
    (HASHTAG_RE,
     "Хэштег в хуке. Хэштегам место в конце подписи, если они вообще нужны."),
    (EMOJI_RE,
     "Эмодзи в хуке. В тексте на экране хватает места либо на слова, либо на эмодзи."),
]


def clamp(n):
    return max(0.0, min(100.0, n))


def words(text):
    # «60 000» и «$18,000» произносятся как одно число, считаем одним словом.
    text = re.sub(r"(?<=\d)[   ,](?=\d{3}\b)", "", text)
    return WORD_RE.findall(text)


def is_number_word(t):
    return t in SPOKEN_NUMBERS or stem_hit(t, NUMBER_STEMS)


def is_money_word(t):
    return t in MONEY_WORDS or stem_hit(t, MONEY_STEMS)


def is_stake_word(t):
    return t in STAKES or stem_hit(t, STAKES_STEMS)


def check_length(text):
    """Хук должен прозвучать раньше, чем палец двинется. Примерно 2-3 секунды."""
    w = words(text)
    n = len(w)
    secs = n / 2.5                       # ~150 слов в минуту, русская речь
    chars = len(text.strip())
    if 4 <= n <= 11:
        score = 100.0
    elif n < 4:
        score = clamp(100 - (4 - n) * 20)
    else:
        score = clamp(100 - (n - 11) * 11)
    if chars > 70:                       # больше двух строк крупного текста
        score -= 12
    return clamp(score), f"{n} слов, {chars} знаков, ~{secs:.1f} с вслух (нужно 4-11 слов)"


def check_specificity(text):
    """Одна конкретная вещь сильнее трёх абстрактных."""
    nums = [n.strip() for n in NUMBER_RE.findall(text) if n.strip() and re.search(r"\d", n)]
    propers = set(PROPER_RE.findall(text))
    low = [norm(w) for w in words(text)]
    spoken = [w for w in low if is_number_word(w) or is_money_word(w)]
    hits = len(nums) + len(propers) + len(spoken)
    score = 15.0 if hits == 0 else clamp(45 + hits * 30)
    found = ", ".join(nums[:2] + sorted(propers)[:2] + spoken[:2])
    return score, (f"конкретики: {hits}" + (f" ({found})" if found else
                   " — ни цифры, ни имени, ничего проверяемого"))


def check_stakes(text):
    """Напряжение, цена, отрицание. То, что зритель может потерять."""
    w = [norm(x) for x in words(text)]
    hits = [x for x in w if is_stake_word(x)]
    low = text.lower().replace("ё", "е")
    hits += [s for s in STAKES_STEMS if " " in s and s in low]
    markers = sorted(set(hits))
    if re.search(r"\$\s?\d|\d[\d\s]*(?:₽|руб|тыс|к\b)", text):
        markers.append("цена")
    n = len(markers)
    score = {0: 20.0, 1: 70.0}.get(n, 100.0)
    detail = f"маркеров ставки: {n}" + (f" ({', '.join(markers[:4])})" if markers else
                                         " — в этой фразе ничего не стоит на кону")
    return clamp(score), detail


def check_frontload(text):
    """Главное слово не может стоять девятым."""
    w = words(text)
    if not w:
        return 0.0, "пусто"
    low = [norm(x) for x in w]
    opener = " ".join(low[:2])
    penalty = 0
    hit_opener = None
    for weak in WEAK_OPENERS:
        wk = weak.replace("ё", "е")
        if opener == wk or opener.startswith(wk + " ") or low[0] == wk:
            penalty, hit_opener = 30, weak
            break
    payload = None
    for i, token in enumerate(low):
        if (is_stake_word(token) or is_number_word(token) or is_money_word(token)
                or re.search(r"\d", w[i]) or (i and PROPER_RE.match(w[i]))):
            payload = i
            break
    if payload is None:
        base = 30.0
        where = "в фразе нет ни одного цепляющего слова"
    elif payload <= 3:
        base = 100.0
        where = f"главное слово на {payload + 1}-м месте"
    elif payload <= 6:
        base = 70.0
        where = f"главное слово на {payload + 1}-м месте, можно ближе к началу"
    else:
        base = 40.0
        where = f"главное слово на {payload + 1}-м месте, слишком поздно"
    detail = where + (f"; слабое начало «{hit_opener}»" if hit_opener else "")
    return clamp(base - penalty), detail


def check_address(text):
    """Обращение к одному зрителю или фраза в пустоту."""
    w = [norm(x) for x in words(text)]
    if YOU_RE.search(text):
        return 100.0, "обращается к зрителю"
    if w and w[0] in IMPERATIVES:
        return 90.0, f"начинается с призыва («{w[0]}»)"
    if ME_RE.search(text):
        return 70.0, "от первого лица, зритель не назван"
    return 35.0, "в третьем лице, в комнате никого нет"


CHECKS = ["LENGTH", "SPECIFICITY", "STAKES", "FRONTLOAD", "ADDRESS"]
LABELS = {"LENGTH": "ДЛИНА", "SPECIFICITY": "КОНКРЕТИКА", "STAKES": "СТАВКА",
          "FRONTLOAD": "НАЧАЛО", "ADDRESS": "ОБРАЩЕНИЕ"}


def run(text):
    results = {
        "LENGTH": check_length(text),
        "SPECIFICITY": check_specificity(text),
        "STAKES": check_stakes(text),
        "FRONTLOAD": check_frontload(text),
        "ADDRESS": check_address(text),
    }
    flags = [msg for pattern, msg in DEALBREAKERS if pattern.search(text)]
    scores = [results[c][0] for c in CHECKS]
    overall = statistics.mean(scores) * 0.6 + min(scores) * 0.4 - len(flags) * 15
    overall = clamp(overall)
    verdict = "STRONG" if overall >= 70 and min(scores) >= 55 and not flags else (
        "OK" if overall >= 50 else "WEAK")
    return results, overall, verdict, flags


VERDICT_RU = {"STRONG": "СИЛЬНЫЙ", "OK": "НОРМ", "WEAK": "СЛАБЫЙ"}


def bar(score, width=24):
    filled = round(score / 100 * width)
    return "#" * filled + "." * (width - filled)


def render_one(text, results, overall, verdict, flags, out=sys.stdout):
    print("\nОЦЕНКА ХУКА", file=out)
    print("=" * 62, file=out)
    print(f"  «{text.strip()}»\n", file=out)
    for name in CHECKS:
        score, detail = results[name]
        print(f"  {LABELS[name]:<13} {bar(score)} {score:5.1f}", file=out)
        print(f"  {'':<13} {detail}", file=out)
    print("-" * 62, file=out)
    print(f"  {'ИТОГ':<13} {bar(overall)} {overall:5.1f}   {VERDICT_RU[verdict]}", file=out)
    for f in flags:
        print(f"\n  СТОП-ФАКТОР  {f}", file=out)
    if verdict != "STRONG":
        weakest = min(CHECKS, key=lambda c: results[c][0])
        print(f"\n  Слабее всего: {LABELS[weakest]}. Исправь это и проверь снова.", file=out)
    print("", file=out)


def render_table(rows, out=sys.stdout):
    print("\nРЕЙТИНГ ХУКОВ\n" + "=" * 78, file=out)
    for i, r in enumerate(rows, 1):
        mark = "->" if i == 1 else "  "
        hook = r["hook"] if len(r["hook"]) <= 62 else r["hook"][:59] + "..."
        print(f"{mark} {r['score']:5.1f} {VERDICT_RU[r['verdict']]:<8} {hook}", file=out)
        print(f"        слабее всего: {LABELS[r['weakest']]} ({r['checks'][r['weakest']]['score']:.0f})", file=out)
        for f in r["flags"]:
            print(f"        стоп-фактор: {f}", file=out)
    print("\nСнимай первый. Если у первого меньше 50, хука среди них пока нет.\n", file=out)


def main():
    ap = argparse.ArgumentParser(description="Оценка хука рилс по пяти свойствам.")
    ap.add_argument("input", nargs="?", default="-", help="файл, по одному хуку в строке, или -")
    ap.add_argument("--hook", help="оценить один хук из командной строки")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.hook:
        lines = [args.hook]
    else:
        raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
    if not lines:
        print("нечего оценивать", file=sys.stderr)
        sys.exit(2)

    payload = []
    for line in lines:
        results, overall, verdict, flags = run(line)
        payload.append({
            "hook": line,
            "checks": {k: {"score": round(v[0], 1), "detail": v[1]} for k, v in results.items()},
            "weakest": min(CHECKS, key=lambda c: results[c][0]),
            "flags": flags,
            "score": round(overall, 1),
            "verdict": verdict,
        })

    if args.json:
        print(json.dumps(payload if len(payload) > 1 else payload[0], indent=2, ensure_ascii=False))
        return

    if len(payload) == 1:
        results, overall, verdict, flags = run(lines[0])
        render_one(lines[0], results, overall, verdict, flags)
    else:
        render_table(sorted(payload, key=lambda r: -r["score"]))

    sys.exit(0 if max(p["score"] for p in payload) >= 70 else 1)


if __name__ == "__main__":
    main()
