# The loanword lexicon

`--lexicon lexicon.tsv` collapses the model's own spelling variants of a
borrowed word onto one form. It is off by default, it is domain-specific, and
it can corrupt ordinary words if you add rows carelessly. This document is how
to add rows that do not.

## The problem it solves

Lithuanian business and event speech is full of English borrowings that have no
settled written form. The model has to write them down anyway, and it does not
write them down the same way twice. Measured on one corpus:

| word | occurrences | distinct spellings |
|---|---|---|
| email | 180 | 19 |
| notification | 80 | 9 |
| invoice | 27 | 7 |
| podcast | 63 | 15 |
| brand | — | 39 |

Every variant costs you a word, and nothing downstream can catch it: `meilo`,
`emeilą` and `įmeilas` are all perfectly ordinary-looking Lithuanian strings.
Search fails, counts are wrong, and a reader trips over the same word rendered
three ways on one page.

**This is not a model bug you can prompt away.** The instability is learned —
the training transcripts spell these words inconsistently themselves, and only
28% of borrowings in that corpus follow the apostrophe convention. The real fix
is upstream, in the training targets. The lexicon is what you use in the
meantime.

It is also *not* spell-correction and not an orthography. Each canonical form
is whichever spelling **this model already produces most often**, so the table
removes inconsistency without taking a side in an open question.

## Why published svetimybės lists do not drop in

VLKK and similar prescriptive lists exist and are well made, but they do not
bridge this gap directly. The written corpus uses English orthography
(`podcastą`), the model emits the phonetic form (`vorkšopai`), and the phonetic
forms occur **zero** times in the written corpus. A list keyed on one side
cannot find the other. You can mine such a list for *candidate* headwords —
that is where `vorkšop` came from — but the variants have to come from your own
transcripts.

## Format

Tab-separated, three columns, `#` starts a comment:

```
canonical<TAB>variant[,variant...]<TAB>blocked_prefix[,blocked_prefix...]
```

```
email	e-mail,emeil,įmeil
invois	invas,invoic,invoj,induosi
kensl	kencer
aul	aūl,aūn
```

The third column is optional and is the safety catch — see below.

## What matching actually does

- **Stems, not whole words.** A variant matches as a *prefix* of the word, and
  only the prefix is replaced, so the Lithuanian ending survives:
  `emeilą → emailą`, `aūloje → auloje`.
- **Longest variant first**, so a specific row beats a general one.
- **Case of the first letter is preserved**: `Juzeris → Uzeris`.
- **A leading `„ " ' (` is skipped** before matching, and put back after.
- **Blocked prefixes win.** If the lowercased word starts with any prefix in
  column three, the row is skipped entirely.
- **Orphan fragments are absorbed.** The model sometimes splits a borrowing in
  two (`e` + `meilų`). When the word before a rewrite is a ≤2-character prefix
  of the canonical form, it is removed rather than left stranded.
- One rewrite per word: the first matching row wins.

## The rule that matters

**A stem match is blunt and it fails silently.** These are all real, all found
the hard way:

- `meil → email` also rewrites `meilės` (love — 610 occurrences in 10M tokens
  of Lithuanian), the adjective `meilus`, and the surname `Meilūnas`. There is
  no blocklist that separates them, because `meilas` is genuinely both an email
  form and a surname. **That row was deleted, not fixed.** Losing ~4 fixes per
  recording is the better trade against silently renaming a person.
- `kancl → kensl` hits `kancleris` (chancellor, 191 occurrences). Narrowed to
  the verb-forming `kanclerin` only.
- `induos → invois` hits `induose` ("in vessels"). Narrowed to `induosi`.

Note what these have in common: the damage is invisible. The output is a
grammatical Lithuanian word, so no confidence filter, no spell check and no
proofread catches it. The only defence is to look at what the table does before
you ship it.

## Adding a row

### 1. Transcribe without the lexicon

```bash
python transcribe_kmynas.py recording.m4a --model kmynas-parakeet-lt-v3.nemo
```

### 2. Find the variants

Read the transcript. The variants of a borrowing usually cluster in one
recording. To count them across several:

```bash
cat transcripts/*.txt | tr ' ' '\n' | tr -d '.,!?„"' \
  | grep -iE '^(e?meil|imeil|įmeil)' | sort | uniq -c | sort -rn
```

### 3. Pick the canonical form

Whichever spelling **the model emits most often**, not the one you think is
correct — the point is consistency, not orthography. Two documented exceptions:

- `aul` over the majority `aūl`, because *aula* is an ordinary Lithuanian noun
  and the `ū` is a decoding artefact rather than a spelling.
- `vorkšop`, where the model had no majority (one occurrence each of `švakšop`
  and `vokšop`), so the row took VLKK's documented Lithuanian form.

### 4. Check it against text it must not touch

This is the step that is not optional.

```bash
python lexicon_check.py reference.txt
```

Any large body of ordinary Lithuanian works — a public corpus, your own past
transcripts, news text. Exit status is 1 if the table rewrote anything, so this
also works as a pre-commit guard. Every rewrite it reports is a suspect until
you have justified it.

### 5. Narrow, or drop the row

If step 4 finds a collision: narrow the variant (`induos` → `induosi`), add the
colliding prefix to column three, or delete the row. Prefer narrowing —
a blocklist only covers the collisions you thought of.

### 6. Confirm the row earns its place

```bash
python lexicon_check.py transcripts/*.txt
```

If a row rewrites nothing on your own material, it is pure risk. Delete it.

### 7. Run it

```bash
python transcribe_kmynas.py recording.m4a \
    --model kmynas-parakeet-lt-v3.nemo --lexicon lexicon.tsv
```

The run prints how many spellings it normalised, so a row that suddenly starts
firing hundreds of times is visible.

## Try it now

`docs/lexicon_demo.txt` is a small fixture with both halves of the problem —
variants that should be collapsed, and near-misses that must not be:

```bash
python lexicon_check.py docs/lexicon_demo.txt --context 2
```

```
22 variant stems from lexicon.tsv
56 words read from 1 file(s)
9 rewrites, 0 orphan fragments absorbed

  emeilą  ->  emailą   (1x)
      … Atsiuntė [emeilą] vakar, o …
  įmeilas  ->  emailas   (1x)
      … vakar, o [įmeilas] taip ir …
  Notifikėšinai  ->  Notificationai   (1x)
      … ir neatėjo. [Notifikėšinai] neveikia, invoicą …
  invoicą  ->  invoisą   (1x)
      … Notifikėšinai neveikia, [invoicą] reikia kensluoti …
  Juzeris  ->  Uzeris   (1x)
      … iki penktadienio. [Juzeris] pasakė, kad …
  opšinalas  ->  opšinolas   (1x)
      … tai visiškai [opšinalas] dalykas. Susitikom …
  aūloje,  ->  auloje,   (1x)
      … dalykas. Susitikom [aūloje,] kur vyko …
  švakšopas,  ->  vorkšopas,   (1x)
      … kur vyko [švakšopas,] o antrą …
  vokšopą  ->  vorkšopą   (1x)
      … o antrą [vokšopą] vedė kolega. …
```

The last three lines of the fixture contain `meilės`, `meilus`, `Meilūnas`,
`Kancleris` and `induose`, and the table leaves all five alone. That is what
the third column and the narrowed variants are for.

## What ships in `lexicon.tsv`

Eight word families in nine rows, all measured on Lithuanian conference,
event and business speech: email, notification, invoice, user, optional,
cancel (two rows — noun and verb stems differ), aula, workshop.
Over a 425,565-form reference the whole table makes 13 rewrites, all of them
legitimate. Treat it as a worked example rather than a standard — your domain
will have different words, and the canonical forms are specific to this
checkpoint's habits.
