#!/usr/bin/env python3
"""Replay a lexicon over text and print every rewrite it would make.

A lexicon row matches a *stem*, which is blunt: `meil -> email` also rewrites
`meilės` (love) and the surname `Meilūnas`. That failure is silent — the output
is a perfectly ordinary-looking Lithuanian word — so a row can corrupt a
recording for months without anyone noticing. The only defence is to look at
what the table actually does before shipping it.

Two ways to run it, and a row is not finished until you have run both:

  1. Over ordinary Lithuanian text the table must NOT touch — a reference
     corpus, past transcripts, anything long and normal. Every rewrite it
     reports there is a suspect. Exit status is 1 if there were any, so this
     works as a guard.

         python lexicon_check.py reference.txt

  2. Over your own model transcripts. The rewrites there are the fixes you are
     buying. If a row earns nothing on your material, it is only risk.

         python lexicon_check.py transcripts/*.txt

Uses the pipeline's own matching code, so what it prints is exactly what
`transcribe_kmynas.py --lexicon` would do.
"""
from __future__ import annotations

import argparse
import collections
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from transcribe_kmynas import load_lexicon, normalise_lexicon  # noqa: E402


def read_tokens(paths: list[str]) -> list[str]:
    toks: list[str] = []
    for p in paths:
        text = pathlib.Path(p).read_text(encoding="utf-8", errors="replace")
        toks.extend(text.split())
    return toks


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Show every rewrite a lexicon would make over some text.")
    ap.add_argument("files", nargs="+", help="plain text or transcript .txt")
    ap.add_argument("--lexicon", default=str(HERE / "lexicon.tsv"))
    ap.add_argument("--context", type=int, default=3,
                    help="words of context to show either side (0 = none)")
    ap.add_argument("--examples", type=int, default=2,
                    help="context lines per distinct rewrite")
    args = ap.parse_args()

    pairs = load_lexicon(args.lexicon)
    tokens = read_tokens(args.files)
    if not tokens:
        sys.exit("no words read")

    # normalise_lexicon mutates in place, so keep the original for context.
    original = list(tokens)
    words = [{"w": t} for t in tokens]
    kept, subs = normalise_lexicon(words, pairs)

    print(f"{len(pairs)} variant stems from {args.lexicon}")
    print(f"{len(tokens):,} words read from {len(args.files)} file(s)")
    print(f"{len(subs)} rewrites, {len(tokens) - len(kept)} orphan fragments absorbed")

    if not subs:
        print("\nno rewrites — the table does not touch this text")
        return

    where = collections.defaultdict(list)
    for i, t in enumerate(original):
        where[t].append(i)

    print()
    counts = collections.Counter(subs)
    for (old, new), n in counts.most_common():
        print(f"  {old}  ->  {new}   ({n}x)")
        for i in where.get(old, [])[:args.examples]:
            if args.context:
                lo, hi = max(0, i - args.context), i + args.context + 1
                left = " ".join(original[lo:i])
                right = " ".join(original[i + 1:hi])
                print(f"      … {left} [{old}] {right} …")

    print("\nRead every line above. On reference text they are false positives;\n"
          "on your own transcripts they are the fixes. Anything you cannot\n"
          "justify, narrow the variant or add the prefix to the row's third\n"
          "tab-separated column.")
    sys.exit(1)


if __name__ == "__main__":
    main()
