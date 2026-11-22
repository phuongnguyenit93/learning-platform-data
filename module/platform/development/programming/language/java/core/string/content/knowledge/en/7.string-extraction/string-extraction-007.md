# Slicing by Character Cluster Using BreakIterator in Java

When you need to limit a line of text by the **number of characters perceived by a reader**—such as truncating display labels, taking part of a username, moving a cursor, or selecting text—`String.substring()` indices can cause you to cut in the wrong place. In Java, `String` is indexed by **UTF-16 code units**; a single user-perceived “character” can consist of **multiple code units** and **multiple Unicode code points**.

`java.text.BreakIterator.getCharacterInstance(...)` provides a way to find **character/grapheme boundaries** in text. You collect the boundary indices returned by the iterator and then call `substring(start, end)` at those exact positions. This avoids splitting many accented letter combinations and surrogate pairs; exact behavior, especially with complex emojis, also depends on the JDK version and the Unicode rule set it implements.

## 1. Why Can Regular `substring` Cut Incorrectly?

Consider a string constructed from:

- The letter `A`: one UTF-16 code unit, one code point.
- Combining acute accent `U+0301`: adds one code point/UTF-16 code unit; together with `A` it forms a cluster that appears to the eye as `Á`.
- Emoji 😀 (`U+1F600`): one code point, yet **two** UTF-16 code units (a surrogate pair).
- The letter `B`: one code unit, one code point.

In Java code:

```java
String text = "A\u0301" + new String(Character.toChars(0x1F600)) + "B";
```

Breakdown in UTF-16 units:

```text
UTF-16 index:  0     1         2       3       4       5
               |  A  | U+0301  | high  | low   |   B   |
               |-- cluster 1 -|-- cluster 2 --| cl. 3 |
Boundaries:    0               2               4       5
```

Values to distinguish:

| Measurement | Result | What Is Being Counted? |
|---|---:|---|
| `text.length()` | 5 | UTF-16 code units |
| `text.codePointCount(0, text.length())` | 4 | Unicode code points, counting a valid surrogate pair as one |
| Number of character clusters per `BreakIterator` (this example) | 3 | `A` + accent, emoji 😀, `B` |

Calling `text.substring(0, 1)` yields only `A`, **losing the combining mark**. Calling `text.substring(0, 3)` yields `A`, the combining mark, and **the first half of the surrogate pair**, producing a non-well-formed UTF-16 string. Using `offsetByCodePoints` preserves *code point* boundaries, yet can still cut between the base letter and its combining mark. Therefore, the problem of “taking N user-visible characters” needs segmentation at a higher level than code units or code points.

### Does a Grapheme Cluster Equal One Glyph?

Not entirely. A *grapheme cluster* is a **unit of text segmentation under Unicode rules**, close to a user's concept of “one character”. A cluster can contain a base letter plus accents, an emoji with a skin-tone modifier, a flag composed of regional indicators, or emojis joined by ZWJ. However, whether a font renders it into one or multiple shapes (*glyphs*) depends on the rendering environment. Thus, grapheme boundaries are not an exact measurement of display width or glyph count.

## 2. What Does `BreakIterator` Do?

`BreakIterator` in package `java.text` is a **stateful** iterator that locates **boundaries** in text. It does not directly return a `List<String>`. The values it returns are **UTF-16 offsets** suitable for passing to `String.substring(...)`.

Creating one for “character” boundaries:

```java
import java.text.BreakIterator;
import java.util.Locale;

BreakIterator iterator = BreakIterator.getCharacterInstance(Locale.ROOT);
iterator.setText("A\u0301B");
```

- `getCharacterInstance(locale)`: selects **character boundaries**; do not confuse with `getWordInstance` (word breaks), `getLineInstance` (line-wrap opportunities), or `getSentenceInstance` (sentences).
- `Locale.ROOT` keeps examples independent of the environment's default locale. In language-specific applications, pass an appropriate locale such as `Locale.forLanguageTag("vi-VN")`. Providers, JDK versions, and Unicode data can still affect results.
- `setText(text)`: sets the text to scan and resets the iterator to the first boundary. Create a new iterator or call `setText` again when processing a new string.

Key operations:

| Method | Effect |
|---|---|
| `first()` | Returns the first boundary, typically offset `0` for `String`. |
| `next()` | Returns the next boundary or `BreakIterator.DONE` at the end. |
| `last()` | Returns the last boundary, equal to `text.length()` for the set `String`. |
| `previous()` | Moves to the previous boundary; returns `DONE` if none remains. |
| `following(i)` | Finds the **first boundary strictly greater than** offset `i`, not greater-than-or-equal. |
| `preceding(i)` | Finds the **last boundary strictly less than** offset `i`. |
| `isBoundary(i)` | Checks whether offset `i` is a boundary recognized by the iterator. |
| `current()` | Gets the iterator's current boundary offset. |
| `BreakIterator.DONE` | Sentinel indicating completion, **not** a position to pass as a `substring` index. |

Note that `following`, `preceding`, and `isBoundary` can mutate the iterator's position. When iterating from start to finish, call `first()` then `next()` sequentially; do not interleave boundary probes without remembering that the state has moved.

## 3. Iterating Cluster by Cluster

Common loop pattern:

```java
BreakIterator it = BreakIterator.getCharacterInstance(Locale.ROOT);
it.setText(text);

int start = it.first();
for (int end = it.next(); end != BreakIterator.DONE; end = it.next()) {
    String cluster = text.substring(start, end);
    // Use cluster for display, counting, or processing
    start = end;
}
```

This is an **illustrative snippet**, assuming `text` is already declared. The sequence is:

1. `first()` returns the first boundary and assigns it to `start`.
2. `next()` returns the next boundary and assigns it to `end`.
3. `substring(start, end)` extracts the slice between **two consecutive boundaries**; `start` is inclusive, `end` is exclusive.
4. Move `start = end` to prepare for the next cluster.
5. Stop when `next()` returns `DONE`; never call `substring` with `DONE`.

Iterating this way keeps all spaces and punctuation as segments according to character boundary rules; it **does not strip** whitespace or split “words”. For an empty string, the iterator has a single boundary `0` and no content segments to iterate.

## 4. Complete Example: Splitting and Slicing by Character Cluster Index

The following program collects all boundaries into a `offsets` list. With that, you can:

- Split the string into a list of clusters via `splitClusters(text)`.
- Extract the slice from cluster `from` (**inclusive**) to cluster `to` (**exclusive**) via `sliceClusters(text, from, to)`.
- Take the first `N` clusters via `sliceClusters(text, 0, N)`.

Save the file **`GraphemeCutDemo.java`**:

```java
import java.text.BreakIterator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class GraphemeCutDemo {
    // Result includes both start and end boundaries, in UTF-16 indices.
    public static List<Integer> boundaries(String text) {
        BreakIterator iterator =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        iterator.setText(text);

        List<Integer> offsets = new ArrayList<>();
        for (int i = iterator.first();
                i != BreakIterator.DONE;
                i = iterator.next()) {
            offsets.add(i);
        }
        return offsets;
    }

    public static List<String> splitClusters(String text) {
        List<Integer> offsets = boundaries(text);
        List<String> result = new ArrayList<>();

        for (int i = 0; i + 1 < offsets.size(); i++) {
            result.add(text.substring(offsets.get(i), offsets.get(i + 1)));
        }
        return result;
    }

    // Slice range [from, to), in character cluster units.
    public static String sliceClusters(String text, int from, int to) {
        List<Integer> offsets = boundaries(text);
        int clusterCount = offsets.size() - 1;

        if (from < 0 || to < from || to > clusterCount) {
            throw new IndexOutOfBoundsException(
                    "Invalid cluster range: [" + from + ", " + to + ")");
        }

        return text.substring(offsets.get(from), offsets.get(to));
    }

    public static void main(String[] args) {
        String text = "A\u0301"
                + new String(Character.toChars(0x1F600))
                + "B";

        System.out.println("UTF-16 units: " + text.length());
        System.out.println("Code points: "
                + text.codePointCount(0, text.length()));
        System.out.println("Offsets: " + boundaries(text));
        System.out.println("Clusters: " + splitClusters(text).size());
        System.out.println("Lengths: "
                + splitClusters(text).stream().map(String::length).toList());

        System.out.println("First: " + sliceClusters(text, 0, 1).length());
        System.out.println("First 2: " + sliceClusters(text, 0, 2).length());
        System.out.println("Last 2: " + sliceClusters(text, 1, 3).length());
        System.out.println("Empty: " + sliceClusters(text, 2, 2).length());

        BreakIterator probe =
                BreakIterator.getCharacterInstance(Locale.ROOT);
        probe.setText(text);

        System.out.println("Boundary at 1: " + probe.isBoundary(1));
        System.out.println("Boundary at 3: " + probe.isBoundary(3));
        System.out.println("Following 2: " + probe.following(2));
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac -encoding UTF-8 GraphemeCutDemo.java
java GraphemeCutDemo
```

Output with basic segmentation in the example:

```text
UTF-16 units: 5
Code points: 4
Offsets: [0, 2, 4, 5]
Clusters: 3
Lengths: [2, 2, 1]
First: 2
First 2: 4
Last 2: 3
Empty: 0
Boundary at 1: false
Boundary at 3: false
Following 2: 4
```

Explanation:

- The boundary list `[0, 2, 4, 5]` produces **3** segments with UTF-16 lengths `[2, 2, 1]`.
- `sliceClusters(text, 0, 1)` captures **both `A` and the combining mark**, so its UTF-16 length is 2.
- `sliceClusters(text, 0, 2)` also includes the **entire emoji surrogate pair**, giving length 4.
- `sliceClusters(text, 1, 3)` returns the emoji together with `B`, totaling 3 UTF-16 code units.
- `sliceClusters(text, 2, 2)` returns an empty string because the half-open slice `[2, 2)` contains no clusters.
- Offset `1` falls between `A` and the combining mark; offset `3` falls inside the surrogate pair: neither is a boundary.
- `following(2)` returns `4` because it seeks the first boundary **greater than** `2`.

The sample data is built using Unicode escapes and `Character.toChars` so the counted results do not depend on whether the terminal has font support for emojis. This is a complete compilable program; short code snippets in other sections illustrate API usage.

### Why Two Lists: Boundaries and Clusters?

`boundaries` stores **offsets**, having `m + 1` elements for `m` clusters. Using two consecutive offsets as `substring` bounds loses no part of the string. The `splitClusters` list has exactly `m` segments; concatenating all segments in order reconstructs the original content:

```java
String original = "A\u0301B";
String reconstructed = String.join("", splitClusters(original));
System.out.println(original.equals(reconstructed)); // true
```

Note that the last snippet is a **usage illustration**, assuming it is called inside the same class or via `GraphemeCutDemo.splitClusters(...)` from another class.

## 5. Taking the First N Clusters and Handling Invalid Indices

Call:

```java
String firstTwo = sliceClusters(text, 0, 2);
```

if `text` has at least two clusters. The function in the example uses a **strict rule**:

- `from == to` is valid if within `0` to the cluster count; the result is an empty string.
- `from < 0`, `to < from`, or `to` greater than the cluster count throws `IndexOutOfBoundsException`.
- `sliceClusters("", 0, 0)` is valid and returns `""`.
- `sliceClusters("", 0, 1)` is invalid because an empty string has 0 clusters.

For UI limits like “at most N clusters” (such as text previews), you can choose a policy that **takes up to the end if N exceeds the cluster count**:

```java
static String takeUpToClusters(String text, int maxClusters) {
    if (maxClusters < 0) {
        throw new IllegalArgumentException("maxClusters must be >= 0");
    }

    BreakIterator it = BreakIterator.getCharacterInstance(Locale.ROOT);
    it.setText(text);

    int end = it.first();
    for (int n = 0; n < maxClusters; n++) {
        int next = it.next();
        if (next == BreakIterator.DONE) {
            break;
        }
        end = next;
    }
    return text.substring(0, end);
}
```

This is a **supplementary method** that can be added to `GraphemeCutDemo`, not a standalone runnable program. It only tracks the end offset and has minimal extra memory overhead; it is suitable when you only need a prefix without storing all boundaries. If `maxClusters` is 0, the result is an empty string; if it exceeds the cluster count, the result is the entire string.

Both policies are reasonable, but they must be named and documented clearly: **`sliceClusters` checks the range**, whereas **`takeUpToClusters` caps at a maximum**.

## 6. JDK 17 vs. JDK 20+: Notes on Complex Emojis

This is the most important limitation when using `BreakIterator`.

In **JDK 20**, the default character boundary implementation was updated to follow **Unicode Extended Grapheme Cluster** rules (UAX #29). Before that change, especially with **ZWJ emojis** and **flags composed of two regional indicators**, some older JDKs could return boundaries that split a rendered combination apart.

Example combinations:

```text
🇺🇸 👨‍👩‍👧‍👦
```

- On implementations supporting Extended Grapheme Clusters under current rules, the two combinations above split into **two clusters** (if written adjacent without spaces).
- On some JDKs prior to 20, the character `BreakIterator` may split them into smaller segments, even separating components joined by **ZWJ (U+200D)** or regional indicator symbols.

Therefore, **do not treat the cluster count output for complex emojis on one JDK version as a universal contract across all versions**. Check the JVM version, provider, Unicode data, and system requirements. If an application requires strict Unicode segmentation that is consistent across JDK versions, select and test an explicit implementation (such as ICU4J if appropriate) with a managed Unicode data version.

The demo in Section 4 intentionally uses a **base letter + combining mark** combination and a **supplementary emoji code point** rather than complex ZWJ emojis to demonstrate boundary principles with easily verifiable results across common JDKs.

This also shows that a “character cluster” is the result of **segmentation rules**, not merely counting code points or slicing each `char`.

## 7. Using `following`, `preceding`, and `isBoundary` with Cursor Offsets

An editor application may store a cursor position as a **UTF-16 offset**. Before slicing, moving, or deleting text, avoid leaving the offset inside a cluster:

```java
BreakIterator it = BreakIterator.getCharacterInstance(Locale.ROOT);
it.setText(text);

boolean valid = it.isBoundary(cursorUtf16Offset);
int nextBoundary = it.following(cursorUtf16Offset);
int previousBoundary = it.preceding(cursorUtf16Offset);
```

The snippet above illustrates the API, with `text` and `cursorUtf16Offset` already declared. Keep in mind:

- `isBoundary(i)` only accepts offsets within the text's range; out-of-range offsets may throw `IllegalArgumentException`.
- `following(i)` is the boundary **after** `i`, even when `i` is already a boundary. Do not use it if you want to keep a cursor that is already on a valid boundary.
- `preceding(i)` is the boundary **before** `i`, even when `i` is already a boundary.
- `following(text.length())` or `preceding(0)` returns `BreakIterator.DONE`. Check for `DONE` before turning the result into a `substring` index.
- Boundary-seeking calls can alter the iterator's state; do not assume `current()` stays at its old position after `isBoundary`.

In a UI, whether to “snap the cursor to the left or right boundary” is a UX decision, not a fixed rule of the API. Depending on the action and drag direction, choose `preceding`, `following`, or keep `i` when `isBoundary(i)` is `true`.

## 8. Locale, Unicode Normalization, and Input Validity

**Locale:** `BreakIterator.getCharacterInstance(locale)` accepts a `Locale` to select the segmentation service. This **does not convert the input string into that language** or translate content. `Locale.ROOT` is convenient for examples; in internationalized applications, use the text's locale and test real scripts.

**Unicode normalization:** `BreakIterator` finds boundaries; it **does not normalize** strings. The two representations `"\u00C1"` (a single code point Á) and `"A\u0301"` (A + acute accent) can look identical while differing in code point sequence, UTF-16 length, and `equals()` result. Both typically form one cluster during segmentation, yet after `substring` they retain their original code units. If the application needs canonical comparison, consider `java.text.Normalizer` with a dedicated policy; **do not silently normalize just to perform slicing**.

**Non-well-formed UTF-16:** A Java `String` can contain unpaired high/low surrogates. If input is malformed, do not conclude that finding a few boundaries means the Unicode data is valid. A separate validation step is needed when data will be encoded or exchanged with systems requiring valid Unicode scalar values.

**No guarantee of visual fit:** Preserving grapheme boundaries still does not guarantee a line of text fits pixel dimensions, has font support, or stays within a width limit. Measuring width requires layout/font tools; line wrapping uses its corresponding algorithm rather than `getCharacterInstance` as a substitute for width measurement.

## 9. Performance and Iterator Management

- **Match the need:** if only taking the first few clusters, an algorithm using one iterator and tracking `end` (Section 5) avoids allocating a list of all boundaries. If querying many slices on the same immutable string, computing and reusing the boundary list can save re-segmentation work.
- **Memory:** `splitClusters` creates a list and slice strings; `boundaries` creates an offset list proportional to the cluster count. `takeUpToClusters` keeps only a few variables besides the iterator object.
- **State:** a `BreakIterator` holds a traversal position and active text; do not share a single mutated instance across operations or threads without synchronization. Use separate instances for independent operations.
- **UTF-16 indices:** even though the API finds boundaries corresponding to user-facing character units, **the returned values are still UTF-16 offsets**. Never pass a cluster ordinal directly as an argument to `substring`.
- **String changes:** if the text changes, the offset list from an earlier segmentation pass is no longer guaranteed to be valid. Recompute boundaries after updating the string. `String` itself is immutable, though the `text` variable may be reassigned to a different string.
- **Unicode tests:** prepare test cases covering letters with combining marks, non-BMP characters, ZWJ emojis, flags, an empty string, line breaks, and scripts from real user sets. Pin library/JDK versions if reproducible segmentation results are required.

## 10. Common Mistakes

| Mistake | Why It Is Problematic | Correct Approach |
|---|---|---|
| `substring(0, n)` to get `n` displayed characters | `n` is interpreted as a UTF-16 offset | Find the `n`-th boundary first, then call `substring(0, boundary)` |
| Using `codePointCount` instead of cluster count | One cluster can have multiple code points | Iterate with character `BreakIterator` |
| Calling `substring(start, BreakIterator.DONE)` | `DONE` is not a valid offset | Stop iterating before calling `substring` |
| Calling `following(i)` hoping to keep `i` when already on a boundary | `following` finds strictly **greater than** `i` | Check `isBoundary(i)` first or apply an explicit policy |
| Splitting with `getWordInstance()` | Splits by word, not character cluster | Use `getCharacterInstance()` |
| Assuming ZWJ emojis are always one cluster on JDK 17 | Rules were significantly updated starting in JDK 20 | Check the JDK and segmentation rule version |
| Treating a grapheme as one monospace character width | Rendering and grapheme segmentation differ | Use layout measurement APIs when width is needed |
| Reusing an iterator after changing text content | Boundaries belong to the string set via `setText` | Call `setText` again or create a new instance |
| Thinking segmentation implies Unicode normalization | BreakIterator only computes boundaries | Handle normalization separately if required by business logic |

## 11. Self-Check Exercises

1. Given `String s = "A\u0301B";`, what are `s.length()` and the cluster count from `getCharacterInstance` in the example?
2. If the boundary list is `[0, 2, 4, 5]`, which cluster does `substring(2, 4)` extract? Why can `substring(2, 3)` cause an issue?
3. In `sliceClusters(text, from, to)`, why must `from == to` be accepted while `to > clusterCount` is rejected?
4. Why can code-point-based slicing still separate `A` and the combining accent `U+0301`?
5. What should you test before using character `BreakIterator` on JDK 17 to slice ZWJ-joined family emojis?

**Answer hints:** (1) `length() == 3` and there are 2 clusters (`A` + accent, `B`). (2) `substring(2, 4)` extracts the non-BMP emoji; `substring(2, 3)` keeps only the high surrogate, breaking the pair. (3) An empty slice is valid; exceeding the cluster count leaves no target boundary to slice to. (4) Code points differ from grapheme clusters. (5) Test actual boundaries on the target JDK; if extended grapheme clusters are required, use a suitable implementation such as JDK 20+ or another verified solution.

## 12. References

- [Oracle Java SE 17: `java.text.BreakIterator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html) — contract of `first`, `next`, `following`, `preceding`, `isBoundary`, and character boundary descriptions.
- [Oracle JDK 20 Release Notes: Grapheme Support in BreakIterator (JDK-8291660)](https://www.oracle.com/java/technologies/javase/20-relnote-issues.html) — changes to support Extended Grapheme Clusters and flag/ZWJ emoji examples.
- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://www.unicode.org/reports/tr29/) — segmentation principles and grapheme cluster boundaries.

**Key takeaway:** `String` indexes by UTF-16; `codePoints()` handles code points; `BreakIterator.getCharacterInstance(...)` finds character cluster boundaries according to the implementation's rules. To slice safely by cluster, **find two boundary offsets → call `substring(start, end)`**, and verify complex emoji behavior on your actual JDK version.
