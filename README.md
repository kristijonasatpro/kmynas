# kmynas 🌾 — Lithuanian speech-to-text, Parakeet-TDT

Long recordings to a punctuated, speaker-labelled transcript plus
`.srt` / `.vtt` / `.json`. Runs on your own machine; nothing is uploaded.

Built around **Kmynas v3**, a fine-tune of
[`nvidia/parakeet-tdt-0.6b-v3`](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)
on 1,392 effective hours of Lithuanian: the LIEPA-3 corpus (1,196 h) plus 65.4 h
of conference and podcast speech, upweighted ×3.

The model punctuates and capitalises by itself — no second tagger — and decodes
at a real-time factor around **0.03**, so a 35-minute recording takes about a
minute.

```
[00:12] Kalbėtojas 1: Labas rytas, pradėkime nuo pirmojo klausimo.

[00:19] Kalbėtojas 2: Ačiū. Manau, kad reikėtų pažiūrėti, kaip tai
veikia praktiškai, ir tik tada spręsti.
```

Most of this repository is not the model. It is the long-form harness around
it, because transducer decoding of a one-hour recording fails in specific,
reproducible ways that a naive "cut into chunks and decode" loop walks straight
into. Each of those is documented below with what was measured, and several
plausible fixes that turned out to be worse are documented in the code so they
are not retried blind.

## Install

NeMo pins versions that conflict with most other ASR stacks, so give it its own
environment.

```bash
git clone https://github.com/kristijonasatpro/kmynas
cd kmynas
python -m venv .venv-nemo
.venv-nemo/bin/pip install -r requirements.txt   # ffmpeg must also be on PATH
```

Budget 5–10 minutes; NeMo is a large install.

## Get the model

```bash
huggingface-cli download kristijonas/kmynas-parakeet-lt-v3 kmynas-parakeet-lt-v3.nemo \
    --local-dir .
```

| checkpoint | notes |
|---|---|
| [**v3**](https://huggingface.co/kristijonas/kmynas-parakeet-lt-v3) | current |
| [v2](https://huggingface.co/kristijonas/kmynas-parakeet-lt-v2) | **crashes in fp16** — run it with `--dtype fp32` |
| [v3 mid-run](https://huggingface.co/kristijonas/kmynas-parakeet-lt-v3-checkpoints) | steps 5,000 / 12,552 / 15,104, for checkpoint comparisons — **private**, ask for access |

Point the pipeline at any `.nemo` Parakeet checkpoint with `--model`, or set
`$KMYNAS_MODEL` once:

```bash
export KMYNAS_MODEL=/path/to/kmynas-parakeet-lt-v3.nemo
```

Nothing downloads itself — pass a local file.

## Transcribe

```bash
.venv-nemo/bin/python transcribe_kmynas.py recording.m4a --speakers 2
```

Writes `recording.txt`, `.srt`, `.vtt` and `.json` (word-level timings) beside
the input, or into `--out-dir`.

Two things are worth doing every time:

**Pass `--speakers N`.** Letting the clustering threshold guess is unreliable —
it has returned 35 speakers on a two-person phone call. If you do not know the
count, run `--no-diar` first (it is fast), read enough to count the voices, then
do one real run.

**Leave `--dtype` alone.** The default fp16 halves device memory and decodes
about 15% faster, and it is a wash on accuracy — see below. v2 checkpoints are
the exception: they crash in fp16 and need `--dtype fp32`.

## Flags

| flag | default | what it does |
|---|---|---|
| `--speakers N` | `-1` | known speaker count; far better than letting the threshold guess |
| `--no-diar` | off | skip speaker labels entirely |
| `--vad-target` | `60` | target block length in seconds |
| `--no-vad` | off | fall back to the older fixed-target chunker |
| `--min-confidence` | `0.98` | hallucination filter threshold; `0` disables |
| `--lexicon FILE` | none | loanword spelling table — see below |
| `--dtype` | `fp16` | half the memory, ~15% faster, a wash on accuracy; v2 needs `fp32` |
| `--diar-min-off` | `0.5` | seconds a voice must go quiet before a speaker change is believed |
| `--overlap` | `1.3` | block overlap in seconds (ignored in VAD mode) |
| `--block-secs` | `35` | max block length in non-VAD mode |
| `--out-dir` | beside input | where to write the four output files |
| `--boost-file` | none | domain term list — measured ineffective, kept documented |

## The loanword lexicon

Lithuanian business and event speech is full of English borrowings with no
settled written form, and the model does not spell them the same way twice.
Measured on one corpus: **email 180 times across 19 spellings**, notification 9
ways, podcast 15 ways in 63 occurrences. Every variant costs you a word, and
nothing downstream catches it — `emeilą`, `įmeilas` and `meilo` are all
perfectly ordinary-looking Lithuanian strings.

`--lexicon` collapses the variants onto one form:

```bash
python transcribe_kmynas.py recording.m4a --lexicon lexicon.tsv
```

```
  lexicon: 10 loanword spellings normalised; aūloj -> auloj (x8), švakšopai -> vorkšopai (x1) …
```

The table is tab-separated. Only the *stem* is replaced, so the Lithuanian
ending survives (`emeilą → emailą`), and the canonical form is whichever
spelling **this model already produces most often** — it removes inconsistency
without imposing an orthography.

```
canonical<TAB>variant[,variant...]<TAB>blocked_prefix[,blocked_prefix...]
```

**That third column is the whole safety story.** Stem matching is blunt and it
fails silently: `meil → email` also rewrites `meilės` (love, 610 occurrences in
10M tokens) and the surname `Meilūnas`, and the result is a grammatical
Lithuanian word that no proofread will flag. That row was deleted rather than
patched. `kancl` collides with `kancleris`; `induos` with `induose`. Both were
narrowed.

So before adding a row, replay the table over text it must **not** touch:

```bash
python lexicon_check.py reference.txt          # exit 1 if it rewrote anything
python lexicon_check.py transcripts/*.txt      # what the row actually earns you
```

There is a runnable fixture in the repo:

```bash
python lexicon_check.py docs/lexicon_demo.txt --context 2
```

It collapses nine variants and leaves `meilės`, `meilus`, `Meilūnas`,
`Kancleris` and `induose` alone — which is the point.

The shipped `lexicon.tsv` is eight word families measured on Lithuanian
conference and business speech. Treat it as a worked example, not a standard;
your domain will have different words. **[docs/lexicon.md](docs/lexicon.md) is
the full guide** — format, exact matching semantics, how to find the variants in
your own transcripts, how to pick a canonical form, and the validation loop.

One thing the lexicon is not: a fix. The model's instability is *learned* — the
training transcripts spell these words inconsistently themselves, and only 28%
of borrowings there follow the apostrophe convention. The real repair is
upstream, in the training targets. This is what you use in the meantime.

## Why it is not just "cut into blocks and decode"

**Blocks are placed by voice activity, not by a timer** (`--vad-target`,
default 60 s). Every block starts at a speech onset and ends at a speech offset,
and the non-speech between two blocks is dropped rather than split. This matters
because the model normalises features *per utterance*: `normalize: per_feature`
z-scores each mel bin over every frame of the block, so silence inside a block
shifts the features of every speech frame in it. A cut through the middle of a
pause damages both neighbours; cutting at the pause's edges damages neither.
Measured: cutting at the longest pause's *centre* took seam errors from 12% back
up to 21%.

An energy threshold cannot find those edges. On real recordings room tone and
quiet speech overlap in RMS — p5 of room tone 0.00055 against 0.00053–0.00081
for quiet words — so an adaptive gate deletes real speech. Silero VAD does it
instead: 462K parameters, CPU, roughly 237× real time.

**Overlapping blocks are merged by word midpoint plus an n-gram seam pass**
(`--overlap`, default 1.3 s; ignored in VAD mode, where boundaries already sit
in silence). A word straddling a cut is decoded whole by both neighbours and
kept once. Without it, cuts land mid-word and the orphaned tail is capitalised
as a new sentence: 31 of 60 seams did that on one 35-minute recording. The
n-gram pass is restricted to runs that straddle a boundary *and* fall inside the
overlap window, so genuine disfluent repetition survives. Seam errors: 52% → 12%
of seams.

**Hallucinated non-words are filtered** (`--min-confidence`, default 0.98). On
breath, laughter or applause the model has no way to emit nothing, so it emits
short consonant clusters — `chl`, `sxchn`, `Zl`. A word is dropped only when it
is *both* low-confidence *and* orthographically impossible in Lithuanian
(contains no vowel), with acronyms and `m`/`h`/`n` fillers whitelisted. Either
test alone is too blunt: confidence alone costs ~1.9% of correct words, because
quietly spoken real words score low too. Together they removed 63 tokens across
five recordings without touching a real word. (Word-level confidence is folded
from token confidences by matching accumulated text, because NeMo's own word
aggregator crashes on this tokenizer's output.)

**Words fused to an opening quote are split.** The checkpoint writes
`žodis„kitas`, and sometimes carries a whole quoted phrase inside one
timestamped word. Everything downstream treats a word as atomic, so the pair
would stay fused in the transcript and count as one word.

**The model is freed before diarization.** It is ~5 GB in fp32 and nothing after
decoding touches it, but it used to stay resident on the device through the
diarization pass. Peak swap 5.1 → 3.1 GB, identical output.

### Things that looked right and measured worse

Documented in the code with their numbers, so they are not retried:

- Adaptive RMS silence gate — deletes real speech (see above).
- Block length matched to the model's training `max_duration` of 20 s —
  20.34% WER against 19.56% for longer blocks.
- Decode-time word boosting — four distinctive domain terms at alpha 1.0
  changed exactly one word, and none of its targets.
- Beam search (`malsd_batch`, beam 2 and 4) — WER identical to greedy.
- NeMo stateful streaming — better on content words, 20× worse on garbage, and
  its script does not serialise confidence, so the filter cannot be applied.

## What it does not fix

**Overlapping speech.** When two people talk over each other the model hears a
mixture and emits one shorter, garbled stream — words get collapsed rather than
split (`tu buvai matęs` → `tubo`). No amount of block placement or filtering
reaches it, because the damage happens inside a block, not at its edges.
Diarization degrades in the same places for the same reason: while both people
are speaking there is no silence to detect, so a frame goes to whichever voice
dominates and short interjections land on the wrong speaker. `--diar-min-off`
helps when turns are *fast* but not overlapping; it does nothing for genuine
overlap. Fixing it properly needs source separation or an overlap-trained model.

**Rare foreign proper nouns.** Product and vendor names come out phonetically.
Boosting was measured and did not help.

**Numbers are always words**, never digits (`du tūkstančiai`), following the
LIEPA convention the model was trained on.

## Precision: fp16 against fp32

Measured on 39 minutes of Lithuanian conference, podcast and telephone speech,
5,826 words of transcript, on Apple MPS.

**Accuracy is a wash.** 32 spans differ, 0.55% of positions — and 9 of those are
punctuation or capitalisation only, leaving **0.39% actual word changes**. Read
end to end, neither side is consistently better: fp32 recovers two Lithuanian
discourse markers that fp16 turns into junk (`Tai daryk` → `Hidaryk`), and fp16
recovers three English borrowings that fp32 mangles (`forvyų` → `forum. Review`,
`staidžis` → `staiges`). One 100-second recording came out byte-identical.

**fp16 costs about half the device memory** and decodes roughly 15% faster
(RTF 0.026 against 0.030 on a 34-minute file). Peak device allocation:

| recording | fp32 | fp16 |
|---|---|---|
| 7 min | 4.06 GiB | **2.22 GiB** |
| 34 min | 6.16 GiB | **3.34 GiB** |

**It does not crash.** v2 died in fp16 deterministically — an id from the
blank/duration slots leaking into a hypothesis and killing detokenization. v3
decoded the exact recording that killed v2 clean, all 34 minutes and 3,698
words. The pipeline installs a guard anyway when a half dtype is used, so an
out-of-vocabulary id is dropped rather than raised; an id the vocabulary cannot
express carries no text to lose.

So: leave the default alone. Use `--dtype fp32` for **v2** checkpoints, which
still need it.

## Memory

Block length is the memory knob, and attention cost is quadratic in it. On a
16 GB machine 60 s blocks are comfortable; 120 s works but pushes several GB
into swap for no measured accuracy gain. Single-pass decoding of a whole file
with no blocks at all is fine to about 5 minutes and gets the process OOM-killed
well before 10.

**The checkpoint is restored to CPU and cast there before it moves to the
device.** Restoring straight onto the device leaves a full fp32 copy of the
weights in its allocator, and that dead copy sets the high-water mark for the
whole run — which is why `--dtype fp16` used to buy nothing at all. Same
transcripts, word timings included; on a 7-minute recording peak fell from
6.12 to 4.06 GiB at fp32 and from 6.13 to 2.22 GiB at fp16.

On Apple Silicon this memory does **not** appear in RSS — `ps` will show 0.0 GB
while the process holds 11. Watch `sysctl -n vm.swapusage` instead, and do not
run two decodes at once.

## Accuracy

Short-form held-out WER, from the model card, same protocol for both:

| set | v2 | **v3** |
|---|---|---|
| LIEPA validation | 15.13 | **14.19** |
| Telephone | 6.83 | **6.08** |
| Dialect | 26.84 | **24.95** |
| Event register (held-out channels) | 15.06 | **14.28** |
| FLEURS lt (986) | 17.85 | **17.15** |

FLEURS references contain digits and this model writes numbers as words, which
costs roughly 4 WER on the digit-bearing 18% of that set for transcriptions that
are often correct. Digit-free subset: **13.11**.

Long-form, through this pipeline, on 489 segments of conference, podcast and
telephone speech:

| slice | v1 | v2 | **v3** |
|---|---|---|---|
| all | 21.82 | 18.64 | **16.31** |
| telephone | 29.18 | 20.68 | **18.49** |
| conference | 16.58 | 12.53 | **11.36** |

Read those as *relative* numbers only: the references are machine transcripts
from a commercial engine, not human, and they were never verified. They are
useful for comparing checkpoints and useless as an absolute.

Against human references — the `meldynamics/liepa-asr` test split, 240 clips —
v3 scores **7.25%** on sentences and **10.91%** on single words, with zero
garbage tokens including on the 118 clips under two seconds. Treat that as
optimistic: LIEPA is almost certainly inside v3's own training data.

v2 emitted `⁇` (the unknown token) at quote positions. **v3 emits none.**

## Comparing checkpoints

`eval_kmynas.py` runs two `.nemo` files over identical blocks and reports the
things a single WER number hides — unknown-token rate, word count (coverage:
a drop usually means dropped speech), a readable word-level diff, and speed.

```bash
python eval_kmynas.py --a v2.nemo --b v3.nemo --name-a v2 --name-b v3 audio/*.m4a
```

Read the diff. A WER that moves by half a point tells you almost nothing about
whether a change helped on your own material.

## Colab

`notebooks/colab_kmynas.ipynb` — clone, install, fetch the checkpoint, upload
audio, transcribe, download the four files. Set the runtime to a T4 GPU; CPU
works but is roughly 30× slower. **Untested**, so treat the first run as the
test.

## What is in here

| | |
|---|---|
| `transcribe_kmynas.py` | the pipeline — VAD blocks, decode, seam dedup, filtering, lexicon, diarization, writers |
| `lexicon.tsv` | loanword spelling table |
| `lexicon_check.py` | replay a lexicon over text and print every rewrite it would make |
| `eval_kmynas.py` | compare two checkpoints on the same audio |
| `docs/lexicon.md` | the full lexicon guide |
| `chunk_longform.py` | pause scoring and cut-point selection |
| `transcribe_file.py` | audio loading, diarization, speaker smoothing, turn assembly and the `.txt`/`.srt`/`.vtt`/`.json` writers |
| `punct_restore.py` | ONNX punctuation tagger |

The last three are shared, unmodified, with
[paprika](https://github.com/kristijonasatpro/paprika) — the sibling repository
for the Whisper fine-tune of the same corpus, which also has the live-subtitle
pipeline. `transcribe_file.py` and `punct_restore.py` are used here for
everything *after* decoding, so the two produce identically laid-out transcripts
and cannot drift apart. Kmynas does not use the punctuation tagger; the model
punctuates itself.

Which to reach for: on clean, prepared speech the Whisper pipeline still reads
better, and it handles rare proper nouns more gracefully. Kmynas is ~10× faster,
has a smaller footprint, punctuates without a second model, and holds up better
on spontaneous speech than the benchmarks suggest. Run both on your own audio —
they fail differently, and no single number captures the difference.

## Requirements

Python 3.10+ and ffmpeg. Memory depends on block length rather than on the
length of the recording — at the 60 s default and the fp16 default, peak device
allocation stays between 2 and 3.5 GiB on everything measured here; see
**Memory** above.
CUDA and Apple MPS are used automatically when present; CPU works but is slow.
Diarization is ONNX-only and always runs on CPU.

## Licence

Code Apache-2.0. Model weights CC BY 4.0, inheriting the LIEPA-3 corpus
(VU / raštija.lt) and the `nvidia/parakeet-tdt-0.6b-v3` attribution chain.
