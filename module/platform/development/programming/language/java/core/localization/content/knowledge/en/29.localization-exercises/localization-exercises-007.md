# Truncating Text by Grapheme Cluster with BreakIterator in Java

## Objectives

A user types the letter **ắ**, yet in memory that string may be represented by **one code point** `U+1EAF` or by **three code points** `U+0061 U+0306 U+0301` (letter `a`, combining breve, combining acute). Likewise, an emoji can take two UTF-16 code units, and a composite emoji can span multiple joined code points.

If you slice text with `substring(0, n)`, `charAt`, or merely count `codePoints()`, you can split between a combining mark and its base letter, between two halves of a surrogate pair, or inside a multi-part emoji. The result is often orphaned accents, broken symbols, or text that no longer matches what the user expects.

To locate **character-cluster** boundaries using Java's text segmentation algorithm, we use **`java.text.BreakIterator.getCharacterInstance(Locale)`**. This is a comprehensive hands-on lesson on Unicode handling, localization, and safer string truncation in Core Java.

After this lesson, you will be able to:

- Distinguish **UTF-16 code unit**, **Unicode code point**, and **grapheme cluster** (a character cluster typically perceived as one visual unit).
- Explain why `String.length()`, `String.codePointCount(...)`, and the grapheme cluster count can differ.
- Use `BreakIterator.getCharacterInstance(locale)`, `setText`, `first`, `next`, and `DONE` to iterate boundaries in a `String`.
- Take prefixes or enforce length limits by cluster count rather than `char` count, preserving original order and bytes.
- Understand the **start-inclusive / end-exclusive** semantics of offsets returned by `BreakIterator`.
- Use `isBoundary`, `preceding`, and `following` when snapping cut points or caret positions.
- Recognize differences between character breaks, word/sentence/line breaks, as well as `Pattern.compile("\\X")` vs. `BreakIterator`.
- Design tests for NFC/NFD Vietnamese letters, surrogate pairs, emoji modifiers, ZWJ sequences, and regional indicators.
- Understand limitations across **JDK versions, Unicode data, and provider implementations** before claiming exact handling of all modern graphemes.

This lesson focuses on **splitting text by character cluster**; do not turn text segmentation into spell checking, glyph width measurement, or a complete text renderer.

## 1. A User-Perceived Character Differs from a Java char

In Java, `String` uses UTF-16 encoding at the API level:

- `String.length()` returns the **number of UTF-16 code units**. A `char` holds one 16-bit code unit; a code point outside the BMP typically needs two `char`s forming a surrogate pair.
- `codePointCount(0, length())` returns the **number of Unicode code points**.
- A **grapheme cluster**, specifically an *extended grapheme cluster* per Unicode Text Segmentation, is a sequence of code points typically perceived by users as a single displayed character.

These three counts are **not equivalent**.

### Decomposed Vietnamese Characters

The letter `ắ` can be constructed as:

```java
String composed = "\u1EAF";
String decomposed = "a\u0306\u0301";
```

This is an illustrative snippet inside a method. The precomposed form `composed` has `length() == 1` and one code point. The decomposed form `decomposed` has `length() == 3` and three code points. Yet a proper grapheme segmentation algorithm treats each string as **one character cluster**.

If you call:

```java
String broken = decomposed.substring(0, 1);
```

`broken` contains only `a`, dropping both diacritics. This slice leaves UTF-16 intact, yet **strips diacritic information** and produces text different from what the user entered.

If you call:

```java
String suffix = decomposed.substring(1);
```

`suffix` begins with two orphaned combining marks lacking a base character. Fonts or renderers may draw them awkwardly. That is why you should never slice by arbitrary `char` indices when the business unit is "user-visible characters."

### Emoji and Surrogate Pairs

The emoji `😀` is code point `U+1F600`, occupying two UTF-16 code units:

```java
String emoji = "\uD83D\uDE00";
System.out.println(emoji.length());
System.out.println(emoji.codePointCount(0, emoji.length()));
```

Stdout:

```text
2
1
```

Calling `emoji.substring(0, 1)` leaves an unpaired **high surrogate**. Although a different mechanism from Vietnamese combining marks, both demonstrate that `length()` does not express user-perceived character units.

Iterating `codePoints()` prevents splitting a surrogate pair in half; however, it still splits `a + ◌̆ + ◌́` into three separate code points. Counting code points improves upon counting `char`s, yet **does not constitute grapheme segmentation**.

## 2. Which Boundary Types Does BreakIterator Provide?

`java.text.BreakIterator` is the abstract class representing a text boundary locator. Java provides these standard factories:

| Factory | Segmentation Unit | Typical Use Case |
| --- | --- | --- |
| `getCharacterInstance(locale)` | Character cluster boundaries | Cluster truncation, caret snapping |
| `getWordInstance(locale)` | Word-related boundaries | Word navigation, basic tokenization |
| `getSentenceInstance(locale)` | Sentence boundaries | Sentence splitting per locale rules |
| `getLineInstance(locale)` | Line-break boundaries | Determining valid line-wrap points |

**Choose the right factory.** If the goal is "take the first 5 user-visible characters," `getCharacterInstance` is the right API to examine; `getWordInstance` does not yield one break per character, and `getLineInstance` finds line-wrapping opportunities rather than character-length truncation.

Never assume a *grapheme cluster* always equals one word, syllable, or glyph. In typography, multiple clusters can form a ligature, or one cluster can render as multiple glyphs. `BreakIterator` analyzes text boundaries—it **does not measure display width**.

### Choosing a Locale

Example:

```java
import java.text.BreakIterator;
import java.util.Locale;

Locale vietnamese = Locale.forLanguageTag("vi-VN");
BreakIterator iterator =
        BreakIterator.getCharacterInstance(vietnamese);
```

Passing an explicit locale expresses usage context and avoids depending on the JVM default locale. However, do not assume every character-break result differs between Vietnamese and English; many character-cluster rules depend on general Unicode properties. Locale and provider effects are much more pronounced for word, sentence, and line breaks.

**Do not infer from locale that diacritics are stripped or rewritten.** NFD Vietnamese text remains combining-mark data; `BreakIterator` only locates boundaries and does not convert NFD to NFC.

## 3. Mechanism for Advancing Through Boundaries

When an iterator is created, no string has been assigned yet. Call `setText`:

```java
BreakIterator it =
        BreakIterator.getCharacterInstance(Locale.forLanguageTag("vi-VN"));
it.setText(text);
```

where `text` is a non-null `String`. Key methods:

| API | Meaning |
| --- | --- |
| `setText(String)` | Assigns the input string to segment |
| `first()` | Moves cursor to the first boundary, normally index `0` |
| `last()` | Moves cursor to the final boundary, normally `text.length()` |
| `next()` | Advances to the next boundary; returns `BreakIterator.DONE` at the end |
| `previous()` | Moves to the previous boundary |
| `current()` | Reads the current boundary without moving |
| `following(offset)` | Boundary **after** the given offset |
| `preceding(offset)` | Boundary **before** the given offset |
| `isBoundary(offset)` | Checks whether an offset is an exact boundary |
| `next(int n)` | Advances `n` boundaries, moving backward if `n` is negative |
| `DONE` | Sentinel value indicating no further boundary |

A common traversal loop:

```java
for (int start = it.first(), end = it.next();
     end != BreakIterator.DONE;
     start = end, end = it.next()) {
    String cluster = text.substring(start, end);
    // Process one extracted cluster.
}
```

This snippet lives inside a method where `it` has had `setText(text)` called. Each iteration handles a **half-open interval** `[start, end)`:

- `start` is the starting offset of the cluster.
- `end` is the offset **immediately after** the cluster's last code unit.
- `substring(start, end)` extracts the exact slice for that cluster.

Do not add `+1` to `end`: `String.substring` is also end-exclusive.

### Offsets Are UTF-16 Indices, Not Code Point Counts

A boundary is a position within a `String`, meaning a UTF-16 index. For emoji `😀`, a cluster might span `start=4, end=6` despite being one code point. Never use `end` as an index into a code-point array without conversion.

The advantage is that `substring(start, end)` works directly with `BreakIterator` offsets, preserving both base letters and combining marks verbatim.

## 4. A Visual, Verifiable Boundary Example

Take the string:

```java
String text = "A" + "a\u0306\u0301" + "\uD83D\uDE00" + "B";
```

Logical Unicode sequence:

```text
A         U+0041
a         U+0061
breve     U+0306
acute     U+0301
😀        U+1F600 (surrogate pair in UTF-16)
B         U+0042
```

Totals:

- **7 UTF-16 code units**: `A` (1) + `a` (1) + two combining marks (2) + emoji (2) + `B` (1).
- **6 Unicode code points**: `A`, `a`, breve, acute, emoji, `B`.
- **4 grapheme clusters** on the tested JDK data: `A`, `a + breve + acute`, emoji, `B`.

Character `BreakIterator` under `vi-VN` in the test environment returns:

| Cluster | UTF-16 Start | UTF-16 End | Code Points in Cluster |
| --- | ---: | ---: | --- |
| `A` | 0 | 1 | `U+0041` |
| `a + ◌̆ + ◌́` | 1 | 4 | `U+0061 U+0306 U+0301` |
| `😀` | 4 | 6 | `U+1F600` |
| `B` | 6 | 7 | `U+0042` |

If a user asks for the **first two clusters**, the correct prefix is:

```text
A + a + U+0306 + U+0301
```

which spans **4 UTF-16 code units**. `substring(0, 2)` does not produce the right result: it keeps only `A` and `a`, dropping both accents; `substring(0, 4)` happens to align in this concrete example, yet the number `4` must never be hardcoded across arbitrary inputs.

### Why Not Normalize to NFC First and Slice by char?

`Normalizer.normalize(text, NFC)` can fold `a + breve + acute` into `ắ`, reducing code-unit counts in some cases. However, it **does not turn every grapheme into a single `char`**, especially non-BMP emojis, ZWJ emojis, flags, and multi-mark combinations across scripts.

Furthermore, Unicode normalization alters the code-point representation even while preserving canonical equivalence. If an application needs to retain exact user input, **truncate along boundaries without silently rewriting to NFC**. You can enforce a separate normalization policy at storage boundaries, which is an independent decision from segmentation.

## 5. Complete Java 17+ Program: Splitting and Taking Prefixes

Create `GraphemeBreakDemo.java`:

```java
import java.text.BreakIterator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public final class GraphemeBreakDemo {
    private static final Locale VI =
            Locale.forLanguageTag("vi-VN");

    private GraphemeBreakDemo() {}

    private static String codePoints(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static List<String> splitClusters(String text, Locale locale) {
        BreakIterator it = BreakIterator.getCharacterInstance(locale);
        it.setText(text);

        List<String> result = new ArrayList<>();
        for (int start = it.first(), end = it.next();
             end != BreakIterator.DONE;
             start = end, end = it.next()) {
            result.add(text.substring(start, end));
        }
        return result;
    }

    public static String takeClusters(
            String text, int maxClusters, Locale locale) {
        if (maxClusters < 0) {
            throw new IllegalArgumentException("Negative count");
        }
        if (maxClusters == 0 || text.isEmpty()) {
            return "";
        }

        BreakIterator it = BreakIterator.getCharacterInstance(locale);
        it.setText(text);
        int end = it.first();

        for (int i = 0; i < maxClusters; i++) {
            int next = it.next();
            if (next == BreakIterator.DONE) {
                break;
            }
            end = next;
        }
        return text.substring(0, end);
    }

    public static void main(String[] args) {
        String text = "A" + "a\u0306\u0301"
                + "\uD83D\uDE00" + "B";

        System.out.println("utf16=" + text.length());
        System.out.println("codepoints="
                + text.codePointCount(0, text.length()));

        BreakIterator it = BreakIterator.getCharacterInstance(VI);
        it.setText(text);

        int count = 0;
        for (int start = it.first(), end = it.next();
             end != BreakIterator.DONE;
             start = end, end = it.next()) {
            count++;
            System.out.println("[" + start + "," + end + ") "
                    + codePoints(text.substring(start, end)));
        }

        System.out.println("clusters=" + count);
        System.out.println("take2="
                + codePoints(takeClusters(text, 2, VI)));

        BreakIterator edge =
                BreakIterator.getCharacterInstance(VI);
        edge.setText(text);

        System.out.println("at5=" + edge.isBoundary(5)
                + ",following5=" + edge.following(5)
                + ",preceding5=" + edge.preceding(5));

        System.out.println("split count="
                + splitClusters(text, VI).size());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 GraphemeBreakDemo.java
java GraphemeBreakDemo
```

Deterministic stdout on the tested JDK with locale `vi-VN`:

```text
utf16=7
codepoints=6
[0,1) U+0041
[1,4) U+0061 U+0306 U+0301
[4,6) U+1F600
[6,7) U+0042
clusters=4
take2=U+0041 U+0061 U+0306 U+0301
at5=false,following5=6,preceding5=4
split count=4
```

### Explanation

1. `utf16=7` and `codepoints=6` differ because emoji `U+1F600` takes two UTF-16 code units.
2. `[1,4)` keeps `a` together with both combining marks without dropping accents.
3. `[4,6)` keeps the emoji surrogate pair intact.
4. `takeClusters(text, 2, VI)` returns the prefix of two clusters: `A` and `a` with its two combining marks, totaling four code units.
5. Offset `5` lies **between the two code units of the emoji**, so `edge.isBoundary(5)` is `false`; the next boundary is `6` and the preceding boundary is `4`.
6. `splitClusters` produces the list of clusters in logical order without NFC normalization or reordering code points.
7. Printing code points uses ASCII output so tests remain readable even if a terminal lacks emoji or diacritic glyphs.

This example verifies the simple segmentation model on the active JDK; for more complex Unicode sequences, test on the **exact JDK/provider version running in production**.

## 6. Designing a Truncation Function with a Clear Contract

`takeClusters` illustrates one policy: take at most `maxClusters` clusters from the start of `text`, **never split a cluster boundary**, and **preserve every code unit of the returned slice**.

Edge cases to specify:

| Input | Expected Outcome / Behavior |
| --- | --- |
| `text = ""` | Return empty string |
| `maxClusters = 0` | Return empty string |
| `maxClusters` greater than cluster count | Return full `text` |
| Negative `maxClusters` | Throw `IllegalArgumentException` |
| `text == null` | Define error explicitly; demo lets API call throw `NullPointerException` if unchecked |
| `locale == null` | Reject/validate explicitly instead of defaulting silently |

In public APIs, add `Objects.requireNonNull(text, "text")` and `Objects.requireNonNull(locale, "locale")` for clear diagnostics. Do not silently coerce `null` to `""` unless that is the application's documented contract.

### Truncating and Appending an Ellipsis

Some UIs cap cluster count and append `…` when text is truncated. Decide **whether the ellipsis counts toward the budget**.

For a 5-cluster budget:

- If only the **original content** is capped at 5 clusters before appending `…`, the result can have **6 clusters**.
- If the **entire output** is capped at 5 clusters, keep at most 4 content clusters plus `…` when truncation occurs.
- If `maxClusters = 0`, return `""` without appending an ellipsis.
- If nothing was truncated, return the original text without an ellipsis.

A helper illustrating the **ellipsis included in total budget** policy:

```java
static String ellipsize(
        String text, int maxClusters, Locale locale) {
    if (maxClusters < 0) {
        throw new IllegalArgumentException("Negative limit");
    }

    List<String> clusters = GraphemeBreakDemo.splitClusters(
            text, locale);

    if (clusters.size() <= maxClusters) {
        return text;
    }
    if (maxClusters == 0) {
        return "";
    }

    String prefix = String.join(
            "", clusters.subList(0, maxClusters - 1));
    return prefix + "\u2026";
}
```

This is an **illustrative method in the same package or a class with access to `GraphemeBreakDemo`**, assuming `List` and `Locale` are imported. It treats `…` as one cluster, which holds for the example. If UI constraints are measured in pixels, this is still **not a text-width measurement algorithm**.

### Truncating Without Materializing a Full List

`splitClusters` is clear to read, yet allocates a `String` per cluster and a `List` to hold them all. When only the **first `n` clusters** are needed, `takeClusters` stops after `n` boundaries without allocating a list for the entire text.

Conversely, when inspecting each cluster (e.g., counting, validating, highlighting), a `for` loop over the iterator can process each `substring(start, end)` directly without building a list.

## 7. Snapping Arbitrary Cut Offsets to Boundaries

A UI may receive an offset from a cursor, search hit, or selection range and need to snap it to the nearest cluster boundary.

Example:

```java
BreakIterator edge = BreakIterator.getCharacterInstance(
        Locale.forLanguageTag("vi-VN"));
edge.setText(text);
boolean safe = edge.isBoundary(offset);
```

This snippet belongs inside a method with valid `text` and `offset`. If `safe` is `false`, `offset` sits **inside a cluster** according to the iterator's rules.

Available operations:

- `preceding(offset)`: finds the boundary **strictly less than** `offset`.
- `following(offset)`: finds the boundary **strictly greater than** `offset`.
- `isBoundary(offset)`: checks whether `offset` is itself a boundary.

Note that `preceding` and `following` locate **strictly earlier/later** boundaries, rather than acting as inclusive floor/ceiling operations. To snap an offset to the **nearest boundary not exceeding `offset`**, check `isBoundary(offset)` first; keep it if `true`, and call `preceding(offset)` only if `false`.

Example with the demo string having an emoji at `[4,6)`:

```text
offset 4: start of emoji, is a boundary
offset 5: middle of surrogate pair, not a boundary
offset 6: after emoji, is a boundary
```

Results for offset `5`:

```text
isBoundary(5) = false
preceding(5)  = 4
following(5)  = 6
```

Never pass an out-of-range offset directly. Boundary APIs define specific exceptions/contracts for invalid offsets; UI code should validate `0..text.length()` beforehand.

### Truncating at an Arbitrary End Offset

Given an arbitrary cut index `cut`, two policies exist:

- **Round down** so the slice never exceeds the original UTF-16 limit: take the largest boundary `<= cut`.
- **Round up** to include the entire cluster containing `cut`: take the smallest boundary `>= cut`.

These two policies change the resulting text differently. Define the exact requirement instead of blindly picking `following` because it sounds "safe."

## 8. BreakIterator and Unicode Grapheme Clusters: Known Limits

Java documentation specifies `BreakIterator.getCharacterInstance` for character boundaries. For many inputs—such as letters with combining marks or standalone emojis—it matches user expectations. However, **never claim that every JDK from Java 17 onward, across all locales and providers, implements the latest Unicode Extended Grapheme Cluster specification identically**.

Cases requiring explicit testing:

| Category | Unicode Example | Challenge |
| --- | --- | --- |
| Letter + combining marks | `a + U+0306 + U+0301` | Keep accents attached to the base letter |
| Surrogate pair | `U+1F600` | Never split between high/low surrogates |
| Emoji modifier | Thumbs-up + skin tone | Group modifier sequences per target standard |
| Zero Width Joiner sequence | Woman + ZWJ + laptop | Keep composite profession emoji together if renderer treats it as one cluster |
| Regional indicators | Two characters forming a flag | Pair regional indicators properly |
| Variation selector | Symbol + VS16 | Do not detach selector from symbol |
| CRLF | `\r\n` | Dedicated cluster-break rule |
| Indic, Thai, Khmer scripts | Combining/virama sequences | Depends on Unicode segmentation and shaping |

On several tested JDKs, `BreakIterator` groups ZWJ emojis, modifiers, RI flags, and CRLF into single clusters; however, **never generalize those test runs into a universal guarantee** across every Java 17 build or Unicode version.

For products with strict modern emoji segmentation requirements, verify the **Unicode version** and actual Java runtime behavior. You may need a dedicated segmentation library synchronized with the Unicode specification or an official Unicode conformance test suite.

### Unicode Text Segmentation Is Not "One Glyph"

An *extended grapheme cluster* generally aligns with what users treat as one character during editing, yet:

- One cluster may be drawn using multiple glyphs.
- Multiple clusters may combine into a ligature during shaping.
- Combining marks may be positioned over a base glyph by the font.
- Emojis may or may not be supported as combined glyphs by the renderer.
- Cluster width depends on font, font size, script, and layout engine.

Therefore, **counting clusters is not pixel-width limiting**. If a UI requires a label to fit within 120 px, measure glyph/text layout and optionally step back along boundaries based on measured width; `BreakIterator` provides **valid break positions**, not pixel calculations.

## 9. Comparing with Pattern "\\X" and codePoints

Java's `java.util.regex.Pattern` supports `\\X` in Java regex strings to match an **extended grapheme cluster** as defined by Unicode (rather than an arbitrary single character).

Example:

```java
import java.util.regex.Pattern;

String decomposed = "a\u0306\u0301";

long matchedClusters = Pattern.compile("\\X")
        .matcher(decomposed)
        .results()
        .count();

System.out.println(matchedClusters);
```

Example stdout:

```text
1
```

Comparing tools:

| Approach | Unit Processed | When to Use |
| --- | --- | --- |
| `String.length()` | UTF-16 code unit | API limits/offsets defined in UTF-16 |
| `String.codePoints()` | Unicode code point | Character code inspection, Unicode categories |
| `BreakIterator.getCharacterInstance` | Character boundary per implementation/provider/locale | Iterating cut points, localization API integration |
| Regex `\\X` | Extended grapheme cluster per regex engine/JDK | Matching grapheme spans, pattern-based counting |
| `Normalizer.normalize` | NFC/NFD/NFKC normalization | Standardizing Unicode representation, not segmentation |

Regex `\\X` and `BreakIterator` may **not behave identically for every Unicode sequence across every JDK**. The two mechanisms take different code paths and can track different Unicode data versions; verify explicitly if strict parity is required.

Never replace `BreakIterator.getCharacterInstance` with `Pattern.compile(".")`: regex `.` does not define a grapheme cluster and has its own rules for newlines and supplementary code points.

## 10. Does Character Segmentation Depend on Locale?

`BreakIterator` accepts a `Locale` to pick segmentation rules. Applications should pass the text's or user's locale when instantiating the iterator. Still, keep these boundaries in mind:

- Many **character boundary** rules are general Unicode rules and do not change solely between Vietnamese and English.
- **Word boundary** and **line break** rules show much stronger locale impact (especially for languages without spaces between words).
- JDK/locale provider data can vary between environments.
- Relying implicitly on `Locale.getDefault()` makes behavior depend on JVM defaults; pass `Locale` explicitly for reproducibility.

Never assume `Locale.forLanguageTag("vi-VN")` checks spelling, enforces "hoà/hòa" tone-placement conventions, or strips accents. It configures the **segmentation provider**, not a full Vietnamese linguistic processor.

### Does BreakIterator Normalize Unicode Automatically?

Never treat `BreakIterator` as a guarantee of NFC/NFD conversion. The API returns **offsets** without mutating the original string. `takeClusters` preserves the exact code units of the retained slice.

If a system normalizes to NFC to avoid visually identical strings with different code points, normalize **at the data ingestion boundary** per policy and compute offsets/mappings afterward. Never normalize after storing offsets, because UTF-16 lengths can change.

## 11. Performance and Thread-Safety Considerations

`BreakIterator` is **stateful**: `setText` and traversal methods mutate the iterator's internal cursor. Never share one mutable instance across concurrent requests/threads calling `setText`.

Practical patterns:

1. **Create a new iterator per operation** — simple, properly scoped, and thread-safe.
2. **Clone** a preconfigured iterator if you want to reuse setup without sharing traversal state.
3. If sharing is unavoidable, synchronize the entire `setText`/traversal block—not just individual `next()` calls.
4. On long strings, iterate directly and stop once enough clusters are reached instead of always building a full list.

Segmentation cost also depends on text complexity and implementation; do not guess absolute cost or assume every `next()` call runs in constant time across all strings. Benchmark with realistic data including Vietnamese diacritics, emojis, and mixed-script text.

### Untrusted Input

When users submit long text, segmentation code should enforce input length limits, processing budgets, and resource caps per business rules. `BreakIterator` itself does not validate well-formed Unicode, detect invisible spoofing characters, or guarantee text is "safe to display."

If certain Unicode control characters must be forbidden in identifiers, validate against a dedicated schema. Never strip all combining marks merely to simplify segmentation, as that destroys Vietnamese diacritics.

## 12. Handling Control Characters, Whitespace, and Punctuation

A *grapheme cluster* is not necessarily a printable letter:

- Spaces can each form a cluster.
- Periods and commas can form clusters.
- Newlines or CRLF follow special rules.
- Format/zero-width characters can affect segmentation without producing visible glyphs.
- An orphaned combining mark at the start of text can form a cluster even without a valid linguistic base letter.

Consequently, a limit like `maxClusters = 20` **counts spaces and punctuation** whenever they stand as separate clusters. If a business rule means "20 letters" or "20 syllables," add a separate check defining which characters count; `BreakIterator` has no awareness of that domain unit.

In particular, never rely on segmentation alone to validate proper names. Validators may allow letters, combining marks, hyphens, and spaces depending on context. Cluster truncation is just one piece of UI/validation handling.

### Strings with Newlines

A `String` may contain `\n` or `\r\n`. When truncating near newlines, inspect the boundaries returned by your segmentation provider; if the UI must keep CRLF pairs intact, add explicit tests. Never assume `String.length()` or code-point count equals grapheme count for newline pairs in every context.

## 13. Cluster Limits Differ from Storage Byte Limits

A single input field might require:

- At most **100 grapheme clusters** for UX consistency.
- At most **255 UTF-8 bytes** due to protocol/column limits.
- Only characters from an allowed Unicode subset per schema.
- **NFC** normalization upon storage.
- Rejection of specific control characters.

These are **independent requirements**; a single check cannot satisfy all of them.

For example, one emoji cluster can occupy many UTF-8 bytes. One NFD Vietnamese letter spans multiple code points yet usually forms one cluster. Checking byte length via `text.getBytes(StandardCharsets.UTF_8).length` does not count graphemes.

A sensible input policy:

1. Select storage normalization form (if any).
2. Define the **length unit**: grapheme, code point, UTF-16, or byte.
3. Use `BreakIterator` or an appropriate segmenter to enforce grapheme limits.
4. If a byte limit applies, check byte length under the specified encoding.
5. Validate allowed character sets/schema and forbidden control characters.
6. When rendering long text, use text layout measurement to fit pixel bounds and ellipsize per an explicit policy.

### Do Not Rely on Grapheme Limits Alone for Resource Protection

A single grapheme cluster can accumulate many combining marks; a 1-cluster string can still be huge in code points or bytes. When accepting untrusted data, enforce a **coarse raw byte/code-point limit** alongside UX cluster limits to prevent oversized clusters from exhausting processing resources.

## 14. Comprehensive Testing with Java and Unicode

A practical test suite:

| Case | Sample Input | What to Verify |
| --- | --- | --- |
| Empty string | `""` | 0 clusters, empty prefix |
| ASCII | `ABC` | Boundaries as expected |
| Vietnamese NFC | `"\u1EAF"` | One cluster in basic cases |
| Vietnamese NFD | `"a\u0306\u0301"` | Breve/acute stay attached to `a` |
| Non-BMP emoji | `"\uD83D\uDE00"` | Surrogate pair is never split |
| Emoji + skin tone | Thumbs-up + modifier | Check whether JDK/provider groups properly |
| Emoji ZWJ | Woman + ZWJ + laptop | Check ZWJ rules and Unicode version |
| Regional indicator flags | Unicode RI pair | Check indicator pairing rules |
| Variation selector | Symbol + VS16 | Selector stays attached to symbol per policy |
| CRLF | `"\r\n"` | Verify boundary for newline pair |
| Leading combining mark | `"\u0301a"` | No crash; preserves content on truncation |
| Mixed-script text | Vietnamese + Arabic/Hebrew | Segmentation not confused with bidi reordering |
| Multiple stacked marks | `"a\u0301\u0302\u0303"` | Never arbitrarily split mid-cluster |
| Very long input | Many combining sequences | Latency/memory behavior and raw limits |

If strict compliance with a specific version of **Unicode `GraphemeBreakTest.txt`** is required, run the official test vectors against your segmentation engine. Never assume that because a few sample emojis work, all GB rules of UAX #29 are supported.

### Testing on the Exact Target Runtime

An application compiled with JDK 17 but deployed on another JDK may receive different segmentation data. In CI:

- Run tests on the **target runtime version**.
- Record JDK vendor, version, and locale provider in critical internationalization tests.
- Do not hardcode complex emoji outcomes across all runtimes without an explicit Unicode-version contract.
- Verify previews, caret movement, selection, and deletion in the real UI; correct backend segmentation does not guarantee the renderer handles every sequence properly.

## 15. Common Mistakes

| Mistake | Problem | Correct Approach |
| --- | --- | --- |
| Treating `String.length()` as visible character count | Counts UTF-16 code units | Pick the right unit for the limit |
| Assuming `codePoints()` equals grapheme count | Combining marks have their own code points | Use cluster segmentation |
| Assuming `substring(0, n)` always cuts safely | Can split diacritics or surrogates | Use boundaries from `BreakIterator` |
| Normalizing to NFC and slicing by `char` | Emojis and many sequences still span multiple code units | Segmentation is still necessary |
| Using `getWordInstance` for character slicing | Word breaks differ from character breaks | Use `getCharacterInstance` |
| Forgetting `setText` | Iterator has not analyzed the input | Call `setText` before iterating |
| Omitting `DONE` check | May pass `-1` offset to `substring` | Check the sentinel properly |
| Treating `end` as inclusive | `substring` is end-exclusive | Use `substring(start, end)` |
| Treating offsets as code-point indices | `BreakIterator` returns UTF-16 positions | Keep index units consistent |
| Calling `preceding` as an inclusive floor | Searches **strictly before** offset | Check `isBoundary` first |
| Sharing one iterator across threads | Iterator holds mutable state | Create/clone per task |
| Equating grapheme limits with byte limits | One cluster can take many bytes | Enforce byte limits separately |
| Equating cluster slicing with UI width | One cluster can span multiple glyphs | Use renderer/text layout |
| Assuming every JDK 17 matches the latest Unicode | Providers/Unicode versions vary | Test on the target runtime |
| Expecting segmentation to fix spelling | It only finds text boundaries | Perform linguistic validation separately |
| Stripping combining marks to simplify cutting | Destroys Vietnamese accents | Preserve data and slice at boundaries |

## 16. Practice Exercises

**Exercise 1 — Three units.** Construct `"\u1EAF"` and `"a\u0306\u0301"`. Measure `length()`, `codePointCount`, and cluster count via `BreakIterator.getCharacterInstance`. Explain why visually equivalent characters have different code-unit counts.

**Exercise 2 — Substring bug.** Given `"A" + "a\u0306\u0301" + "B"`, why does `substring(0, 2)` drop both accents? Write a method returning the first two clusters.

**Exercise 3 — Non-BMP emoji.** Use `"\uD83D\uDE00"`. Identify the index sitting inside the surrogate pair. Compare slicing by code unit versus slicing with `BreakIterator`.

**Exercise 4 — `isBoundary`.** Given the demo string with an emoji at `[4,6)`, predict `isBoundary(5)`, `preceding(5)`, and `following(5)`. Write a helper snapping a cut index down to the nearest boundary not exceeding the limit.

**Exercise 5 — Ellipsis.** Write a truncation helper with an 8-cluster budget **including** a trailing `…` when truncated. When no truncation occurs, omit the ellipsis. Test empty strings and budget `0`.

**Exercise 6 — Regex `\\X`.** Use `Pattern.compile("\\X")` to count graphemes and compare against `BreakIterator.getCharacterInstance` on NFC/NFD strings and a ZWJ emoji. If your JDK differs on any case, which part of the system needs a pinned policy?

**Exercise 7 — Storage limits.** A username allows at most 20 clusters while the database column allows 64 UTF-8 bytes. Why is a grapheme check alone insufficient? Propose validation order and user-facing error messages.

**Exercise 8 — Multilingual text.** Given text mixing Latin, accented Vietnamese, and Arabic, segment it with `BreakIterator`. Why does this result not replace `java.text.Bidi` for RTL display?

**Exercise 9 — JDK dependency.** Build a test covering modifiers, ZWJ sequences, RI flags, and CRLF, and run the same test across two Java versions. Record cluster counts and offsets, and discuss how to handle differences.

## 17. Conclusion

`BreakIterator.getCharacterInstance(Locale)` is the Core Java API for iterating **character boundaries** in text, essential when truncating strings without detaching combining marks from base letters or splitting surrogate pairs. When traversing with `first()/next()`, extract each segment with `substring(start, end)` using end-exclusive UTF-16 indices; never mistake cluster count for `String.length()`.

Text segmentation is **distinct from** Unicode normalization, spell checking, glyph-width measurement, and bidirectional layout. For modern UIs handling complex emojis, verify the exact capabilities of your JDK/provider and Unicode version; if strict conformance to a specific Extended Grapheme Cluster profile is required, select an appropriate segmentation engine and conformance test suite.

**Core principle:** *Slice text along cluster boundaries rather than arbitrary `char` indices; always track offset units carefully and test multi-code-point Unicode sequences.*

### References

- [`BreakIterator` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html)
- [`String` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`Pattern` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
- [Unicode Standard Annex #29: Unicode Text Segmentation](https://www.unicode.org/reports/tr29/)
