# Extended Grapheme Clusters, Combining Marks, and Emoji Sequences in Java

## 1. Why Can a "Character" on Screen Consist of Multiple Parts?

In multilingual interfaces, users commonly treat the letter `é`, the symbol `😀`, the flag `🇻🇳`, the hand gesture `👍🏽`, or the family `👩‍👩‍👧‍👦` as single units that can be selected or deleted together. However, these representations do not necessarily consist of one Unicode code point, nor do they necessarily occupy one Java `char`.

For example, `e\u0301` is the letter `e` followed by the **combining acute accent** `U+0301`. It consists of two code points yet is normally recognized by readers as a single accented letter. The flag `🇻🇳` consists of two **regional indicator** code points, and the family emoji can consist of four emojis along with three **zero-width joiner** (ZWJ) characters.

When handling **text boundaries**, there are three separate questions:

1. How many **UTF-16 code units** are there? That is what `String.length()` returns.
2. How many **Unicode code points** are there? That is what `codePointCount()` measures.
3. How many **extended grapheme clusters** are there? That is the segmentation unit closest to "one user-perceived character".

This lesson focuses on the third question: **extended grapheme clusters, combining marks, emoji modifiers, and emoji sequences**. We will use `java.util.regex.Pattern` with the `\\X` expression in Java 17+, understand Unicode Text Segmentation (UAX #29), inspect boundaries, slice strings safely, and distinguish segmentation from actual glyph rendering.

**Rule:** to limit the number of "characters" a user enters, delete a piece of text, or place a cursor naturally, do not blindly use `String.length()`, `charAt()`, or `codePoints()` as the UI unit.

## 2. Three Representation Layers and an Example Table

Unicode distinguishes a **code point** (a `U+...` value) from a **code unit** (an encoding unit) and a **grapheme cluster** (a cluster of code points according to segmentation rules).

| Content | UTF-16 code units | Code points | Grapheme clusters |
| --- | ---: | ---: | ---: |
| `A` | 1 | 1 | 1 |
| Precomposed `é` `U+00E9` | 1 | 1 | 1 |
| `e\u0301`: letter + combining mark | 2 | 2 | 1 |
| `😀` | 2 | 1 | 1 |
| `👍🏽`: emoji + skin tone modifier | 4 | 2 | 1 |
| `🇻🇳`: regional indicator pair | 4 | 2 | 1 |
| `👩‍👩‍👧‍👦`: ZWJ emoji sequence | 11 | 7 | 1 |
| `❤️`: heart + variation selector | 2 | 2 | 1 |
| `1️⃣`: keycap emoji sequence | 3 | 3 | 1 |

The table illustrates results from the grapheme algorithm supported by Java regex `\\X` in the tested JVM. Segmentation results for some **newer emoji sequences** may vary between Unicode/JDK versions; visual display also depends on fonts and platforms.

For example, for `👩‍👩‍👧‍👦`:

- Four person emojis outside the Basic Multilingual Plane (BMP), each using two UTF-16 code units → 8 total.
- Three `U+200D` (ZWJ) characters inside the BMP, each using one code unit → 3 more.
- Total **11 code units**, **7 code points**, yet normally segmented into **one extended grapheme cluster**.

One cluster can contain multiple code points; one code point does not necessarily equal one glyph; and one glyph does not necessarily occupy one screen column. These are distinct concepts with separate purposes.

## 3. What Is an Extended Grapheme Cluster?

Unicode Standard Annex #29 (UAX #29) describes text segmentation rules, including **extended grapheme clusters**. This concept models many cases where a user wants to operate on **one text unit**, even when that unit is a sequence of code points.

For example:

~~~text
e + ◌́             -> one cluster: é
👍 + 🏽             -> one cluster: 👍🏽
🇻 + 🇳             -> one cluster: 🇻🇳
👩 + ZWJ + 👩 + ZWJ + 👧 + ZWJ + 👦 -> one cluster
~~~

The standard rules are not simply "attach every mark to the preceding character". They evaluate many Unicode properties and contexts: **Extend** (continuation marks), **SpacingMark**, **Prepend**, **Regional_Indicator**, **Extended_Pictographic**, and conditions involving ZWJ, Hangul, or complex scripts.

**Extended grapheme cluster** is a segmentation term. It does not mean every browser will draw the cluster as a single complete glyph. If a font or OS does not yet support an emoji sequence, users may see separate shapes while the segmentation algorithm still treats the entire sequence as one cluster.

When defining the unit the UI calls a "character", specify that it is a **grapheme cluster under a specific algorithm/Unicode version** or an explicit product rule; never write "each character is one char" in a data contract.

## 4. Combining Marks: An Accented Letter Is Not Necessarily One Code Point

Unicode can represent accented letters in canonically equivalent ways. For `é`:

~~~text
U+00E9                 é (precomposed)
U+0065 U+0301          e + combining acute accent
~~~

The two strings usually look identical when displayed, but in Java's representation:

| Metric | `"\u00E9"` | `"e\u0301"` |
| --- | ---: | ---: |
| `String.length()` | 1 | 2 |
| `codePointCount()` | 1 | 2 |
| Cluster count via `\\X` | 1 | 1 |

The mark `U+0301` is a **combining mark**: it can be positioned over the base letter instead of appearing as a separate shape. Vietnamese frequently has combinations of a base letter, a vowel diacritic, and a tone mark. Therefore, a length check based on code points can still overcount relative to user intuition.

Do not delete or slice off a combining mark on its own if the operation is described as "delete one character". For example, slicing `"e\u0301"` at the boundary between `e` and `U+0301` can leave a stray acute accent or a different representation.

**Normalization does not replace segmentation:** `Normalizer.normalize(text, NFC)` can combine some letters with marks into a single precomposed code point, but it cannot combine **every** grapheme cluster (such as flags or ZWJ emojis) into one code point. To operate by cluster, you still must use a segmentation algorithm.

## 5. Emoji Modifiers: One Symbol Can Consist of Two Code Points

The `👍🏽` emoji illustrates a **skin tone modifier**:

~~~text
U+1F44D  THUMBS UP SIGN
U+1F3FD  EMOJI MODIFIER FITZPATRICK TYPE-4
~~~

Both code points lie outside the BMP, producing **4 UTF-16 code units**. Supporting rendering software typically displays this combination as a single symbol; the grapheme cluster algorithm likewise treats the combination as one cluster in the example above.

If a delete operation acts on one code point, it might remove only the modifier or only the base character, altering the symbol in a way the user did not intend. Use grapheme boundaries when the goal is to delete the symbol as a unit.

A modifier is neither a Vietnamese diacritic nor a ZWJ joiner: it is a different kind of code point with specific emoji combination rules. During data processing, these elements must stay in the exact order, especially during copy, cut, and paste.

## 6. Emoji Flags: Two Regional Indicators Form One Cluster

The `🇻🇳` flag is the sequence:

~~~text
U+1F1FB  REGIONAL INDICATOR SYMBOL LETTER V
U+1F1F3  REGIONAL INDICATOR SYMBOL LETTER N
~~~

Each code point requires two UTF-16 code units. Therefore `🇻🇳` consists of **4 code units**, **2 code points**, and typically **1 extended grapheme cluster**.

The Regional Indicator segmentation rule is not "all adjacent regional indicators form one cluster". RI characters are **paired contextually**, so a long sequence can break into multiple clusters. Do not split an RI run at an arbitrary code point position and assume cluster pairing remains unchanged across that boundary.

Nor should you assume an arbitrary RI cluster is guaranteed to render as the flag of a recognized country; symbol support and region-code semantics depend on the emoji standard and platform.

## 7. Emoji Sequences with ZWJ: One Cluster Can Contain Multiple Emojis

`U+200D`, **zero-width joiner** (ZWJ), can join certain pictographic sequences into a composite symbol. For example, `👩‍👩‍👧‍👦` consists of:

~~~text
WOMAN + ZWJ + WOMAN + ZWJ + GIRL + ZWJ + BOY
~~~

Four emojis and three ZWJs = **7 code points**, and in UTF-16 it is **11 code units**. In the verified runtime, the `\\X` expression recognizes the entire sequence as one cluster.

Not **every** `emoji + ZWJ + emoji` sequence is a standardized emoji sequence rendered as a single glyph. Grapheme segmentation and the emoji sequence list are related but **not identical**. A font/rendering engine may lack the combined glyph; segmentation operations still must inspect cluster boundaries based on the runtime's Unicode rules.

Similarly, variation selector `U+FE0F` can affect emoji presentation—for instance `❤️` consists of `U+2764` and `U+FE0F`; keycap `1️⃣` consists of `1`, `U+FE0F`, `U+20E3`. They have **2 and 3 code points** respectively, yet one grapheme cluster in the examples. Do not strip a variation selector or combining keycap mid-sequence when the goal is to preserve the symbol.

## 8. Java String Counts UTF-16 Code Units, Not Clusters

For `String`:

- `length()` returns the number of UTF-16 code units.
- `charAt(index)` gets **one** code unit at a UTF-16 position.
- `substring(begin, end)` slices by code unit indexes.
- `codePointAt(index)` reads a code point at a UTF-16 index.
- `codePointCount(begin, end)` counts code points in a range.
- `offsetByCodePoints(index, n)` moves by code points and returns a UTF-16 index.

Using `codePointAt` is better than `charAt` when iterating Unicode scalar values; it avoids splitting a supplementary code point into two surrogate code units. However, **a code point boundary is not guaranteed to be a grapheme boundary**, for example between `e` and a combining mark, between two regional indicators, or between an emoji and a modifier.

If the UI needs to slice by "user-visible units", use **grapheme segmentation** instead of relying solely on `offsetByCodePoints`.

## 9. Java 17+: Using Regex `\\X` to Count Extended Grapheme Clusters

Since Java 9, `java.util.regex.Pattern` supports `\\X` to match one **Unicode extended grapheme cluster**. In a Java string literal, you must write `"\\X"` (two backslashes in Java source code) so the regex receives one backslash and `X`.

Program `GraphemeCountDemo.java`:

~~~java
import java.util.regex.Pattern;

public class GraphemeCountDemo {
    public static void main(String[] args) {
        String[] names = {
            "ASCII", "ACCENT", "EMOJI", "SKIN",
            "FLAG", "FAMILY", "HEART", "KEYCAP"
        };

        String[] values = {
            "A",
            "e\u0301",
            "\uD83D\uDE00",
            "\uD83D\uDC4D\uD83C\uDFFD",
            "\uD83C\uDDFB\uD83C\uDDF3",
            "\uD83D\uDC69\u200D\uD83D\uDC69\u200D"
                + "\uD83D\uDC67\u200D\uD83D\uDC66",
            "\u2764\uFE0F",
            "1\uFE0F\u20E3"
        };

        Pattern grapheme = Pattern.compile("\\X");

        for (int i = 0; i < values.length; i++) {
            String text = values[i];
            long clusters = grapheme.matcher(text)
                .results().count();

            System.out.printf(
                "%s: units=%d points=%d clusters=%d%n",
                names[i],
                text.length(),
                text.codePointCount(0, text.length()),
                clusters);
        }
    }
}
~~~

Save with UTF-8 encoding as `GraphemeCountDemo.java`; run on JDK 17+:

~~~bash
javac -encoding UTF-8 GraphemeCountDemo.java
java GraphemeCountDemo
~~~

Stdout according to the verified JVM Unicode data:

~~~text
ASCII: units=1 points=1 clusters=1
ACCENT: units=2 points=2 clusters=1
EMOJI: units=2 points=1 clusters=1
SKIN: units=4 points=2 clusters=1
FLAG: units=4 points=2 clusters=1
FAMILY: units=11 points=7 clusters=1
HEART: units=2 points=2 clusters=1
KEYCAP: units=3 points=3 clusters=1
~~~

Here `Matcher.results()` is an API available since Java 9, so it works on Java 17. `Pattern` is compiled once; each `matcher(text)` creates a new matcher for the data to segment.

**Do not confuse:** `\\X` is a regex based on a segmentation algorithm, not a measure of pixel width or glyph count. Nor is it a normalization step; the string `e\u0301` still has 2 code points even though the regex recognizes 1 cluster.

## 10. Finding Actual Boundaries: Returned Indexes Are Still UTF-16

A `\\X` matcher can return `start()` and `end()` for each cluster. Both values are **still UTF-16 code-unit indexes** in `String`, not code point indexes or cluster numbers.

Example `GraphemeBoundaryDemo.java`:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GraphemeBoundaryDemo {
    public static void main(String[] args) {
        String text = "A" + "e\u0301"
            + "\uD83C\uDDFB\uD83C\uDDF3";

        Pattern pattern = Pattern.compile("\\X");
        Matcher matcher = pattern.matcher(text);

        System.out.println("all=" + text.length()
            + "/" + text.codePointCount(0, text.length())
            + "/" + pattern.matcher(text).results().count());

        while (matcher.find()) {
            String cluster = matcher.group();
            System.out.println(matcher.start() + ".."
                + matcher.end() + " => "
                + cluster.length() + "/"
                + cluster.codePointCount(0, cluster.length()));
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 GraphemeBoundaryDemo.java
java GraphemeBoundaryDemo
~~~

Stdout:

~~~text
all=7/5/3
0..1 => 1/1
1..3 => 2/2
3..7 => 4/2
~~~

Explanation:

- `A` in UTF-16 range `[0, 1)`: 1 code unit / 1 code point.
- `e\u0301` in range `[1, 3)`: 2 code units / 2 code points, yet 1 cluster.
- `🇻🇳` in range `[3, 7)`: 4 code units / 2 code points, yet 1 cluster.

The boundaries are **half-open intervals**: `start` is inclusive, `end` is exclusive. Using `substring(matcher.start(), matcher.end())` extracts the whole cluster along the detected boundaries without adding or subtracting units manually.

## 11. Slicing Text by Cluster Count Instead of Code Unit Count

Text truncation features often do something like `text.substring(0, limit)`. If `limit` is interpreted as **the number of user-visible characters**, that approach can be wrong: splitting a surrogate pair in half, leaving an orphan combining mark, or breaking an emoji sequence.

We can advance a `Matcher` to find **the ending boundary of the Nth cluster** and slice once.

Program `GraphemePrefixDemo.java`:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GraphemePrefixDemo {
    private static final Pattern GRAPHEME =
        Pattern.compile("\\X");

    static String firstClusters(String text, int limit) {
        if (text == null || limit < 0) {
            throw new IllegalArgumentException("invalid input");
        }

        Matcher matcher = GRAPHEME.matcher(text);
        int end = 0;
        int count = 0;

        while (count < limit && matcher.find()) {
            end = matcher.end();
            count++;
        }
        return text.substring(0, end);
    }

    static void describe(String label, String value) {
        System.out.println(label + "=" + value.length() + "/"
            + value.codePointCount(0, value.length())
            + "/" + GRAPHEME.matcher(value).results().count());
    }

    public static void main(String[] args) {
        String text = "A" + "e\u0301"
            + "\uD83C\uDDFB\uD83C\uDDF3";

        describe("original", text);
        describe("first2", firstClusters(text, 2));
        describe("first3", firstClusters(text, 3));
        describe("first0", firstClusters(text, 0));
    }
}
~~~

Save `GraphemePrefixDemo.java` and run:

~~~bash
javac -encoding UTF-8 GraphemePrefixDemo.java
java GraphemePrefixDemo
~~~

Stdout:

~~~text
original=7/5/3
first2=3/3/2
first3=7/5/3
first0=0/0/0
~~~

The function takes at most `limit` clusters while keeping all code points inside them intact. If `limit` exceeds the available cluster count, the result is the whole string. If `limit == 0`, the result is empty. `null` input or a negative limit is explicitly rejected.

This approach works well for taking a grapheme-based prefix in certain problems; real UI truncation also needs to consider ellipses (`…`), display width, and product rules. If a limit is defined in **network bytes**, **code units**, or **code points**, use the measurement matching that requirement rather than always using graphemes.

## 12. Backspace, Caret, and Text Selection

Suppose a string contains only `"e\u0301"`. An operation like `substring(0, text.length() - 1)` removes the acute accent and leaves `e`; that is, it deleted **one code unit**, not one grapheme. With the flag emoji `🇻🇳`, deleting one code unit can leave an unpaired surrogate.

Deleting by **code point** using `offsetByCodePoints` avoids splitting surrogate pairs, yet can still split `e\u0301` into `e` and the acute mark, or split a regional indicator pair in half. To implement Backspace by cluster, find **the cluster boundary immediately before the cursor position**, then delete the entire corresponding UTF-16 span.

For caret and selection, there are more UI considerations:

- Users can place the caret only at positions permitted by the editing engine, not arbitrarily at every code unit.
- One cluster is not guaranteed to correspond to exactly one glyph or one monospace cell.
- Scripts such as Arabic, Indic, and bidirectional text have complex layout, reading-order, and navigation rules.
- The operating system or browser may support editing behavior different from a server-side Java algorithm.

Therefore, **grapheme clusters are a foundational layer** for editing, not a complete recipe for caret placement or rendering.

## 13. Normalization Changes Code Point Counts but Does Not Solve Every Cluster

`java.text.Normalizer` supports NFC, NFD, NFKC, and NFKD. For the letter `é`, NFC can turn `e\u0301` into `U+00E9`; the code point / UTF-16 code unit count drops from 2 to 1. Both forms remain **1 grapheme cluster**.

Standalone example `GraphemeNormalizationDemo.java`:

~~~java
import java.text.Normalizer;
import java.util.regex.Pattern;

public class GraphemeNormalizationDemo {
    static String metrics(String s) {
        long clusters = Pattern.compile("\\X")
            .matcher(s).results().count();
        return s.length() + "/"
            + s.codePointCount(0, s.length()) + "/"
            + clusters;
    }

    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("equals="
            + composed.equals(decomposed));
        System.out.println("before=" + metrics(decomposed));

        String nfc = Normalizer.normalize(
            decomposed, Normalizer.Form.NFC);

        System.out.println("after=" + metrics(nfc));
        System.out.println("nfcEqual=" + composed.equals(nfc));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 GraphemeNormalizationDemo.java
java GraphemeNormalizationDemo
~~~

Stdout:

~~~text
equals=false
before=2/2/1
after=1/1/1
nfcEqual=true
~~~

This is the difference between **data structure** and **user perception**. Do not normalize solely to "turn every visible character into one code point": that cannot be achieved for many emoji sequences.

If you need to preserve exact source data (for example, documents whose letters and accents were entered in decomposed form), keep the original before normalizing. An NFC-normalized value typically no longer reveals the original code point representation even though it preserves canonical equivalence.

## 14. BreakIterator and Differences Between Segmenters

Beyond regex, Java provides `java.text.BreakIterator.getCharacterInstance(locale)` to find character boundaries. This is a different API from `Pattern.compile("\\X")`, and results depend on the rules/datasets used by the specific implementation.

The following snippet is **illustrative inside a method** with variables `String text`, `Locale locale`, and import `java.text.BreakIterator`:

~~~java
BreakIterator iterator =
    BreakIterator.getCharacterInstance(locale);
iterator.setText(text);

for (int start = iterator.first(),
         end = iterator.next();
     end != BreakIterator.DONE;
     start = end, end = iterator.next()) {

    String segment = text.substring(start, end);
    // Process segment according to returned boundaries.
}
~~~

Do not assume `BreakIterator` on every JDK/locale handles **every new emoji ZWJ sequence** identically to `\\X`; test against the target Unicode data version and runtime. Depending on requirements, you can use ICU4J or a library updated against a managed Unicode version.

Whichever approach you use, `start/end` indexes on `String` remain **UTF-16 indexes**. Do not mix them with code point positions or cluster counts when slicing strings.

## 15. Unicode Versions and New Emojis

UAX #29 rules evolve with the Unicode standard; the list of emoji sequences and rendering support also change across Unicode/emoji versions. An older JVM may know how to segment many common emojis, yet not necessarily understand the properties of the newest emojis.

Practical consequences:

1. Your test suite should include the emoji sequences your product actually supports.
2. Pin or document the JDK/ICU/Unicode data version when segmentation behavior is part of a contract.
3. Do not test only a lone `😀`; include combining marks, RI flags, modifiers, ZWJ, and variation selectors.
4. Do not treat a symbol rendering as separate shapes as proof that the regex segmented wrongly; it may be a font/renderer difference.
5. If you rely on a grapheme count limit in stored data, upgrading the Unicode version may require re-checking stored data and boundary cases.

Any code assuming every emoji has length `2` UTF-16 units will fail on composite sequences; any code assuming every glyph is one grapheme is also unreliable on complex scripts.

## 16. Grapheme Clusters and Input Field Length Limits

A product requirement like "Display name max 20 characters" is missing **the unit of measurement**. It could mean:

| Actual Requirement | How to Measure in Java |
| --- | --- |
| Max 20 UTF-16 code units | `text.length()` |
| Max 20 Unicode code points | `text.codePointCount(0, text.length())` |
| Max 20 extended grapheme clusters | `Pattern.compile("\\X").matcher(text).results().count()` |
| Max 20 UTF-8 bytes | `text.getBytes(StandardCharsets.UTF_8).length` |
| Max pixel width | Layout/font APIs, not the counts above |

The units are not equivalent. A family emoji can consume **11 code units** while being only **1 grapheme cluster**. If a product promises a limit of "20 user-visible characters" while the server checks `length() <= 20`, the experience can feel unfair or confusing.

Conversely, if a database or protocol imposes a byte limit, then even if the UI counts one cluster, the system must still check **byte count** before storing or transmitting. Thus you need both technical validation and UX policy, rather than trying to substitute one for the other.

**Note:** `\\X` does not itself validate whether a Unicode string has well-formed UTF-16 surrogate pairs. If input may contain lone surrogates or decoding errors, a separate validation/decoder policy is needed.

## 17. Not Every Display Unit Has the Same Width

An important localization point: **"one grapheme cluster" does not mean "one terminal cell" or "one glyph".** For example:

- The Latin letter `A` typically occupies one column in a monospace terminal.
- Many CJK characters can occupy two columns.
- Emojis may render using color glyphs or multi-character fallbacks.
- One grapheme cluster can have multiple components drawn by a shaping engine as multiple glyphs.
- A font ligature can draw multiple characters as one glyph while grapheme segmentation still keeps them as separate clusters.
- Accented text and complex scripts require handling mark positioning, BiDi, or line rules.

Therefore, if you are doing terminal column alignment, tab alignment, text box layout, or pixel-based truncation, use an appropriate **display-width measurement** library. Do not use `Matcher.results().count()` as pixel size or column count.

In machine-to-machine string processing, conversely, you may need to store UTF-8 bytes or Unicode scalar values without caring how a font draws them. Choose the right metric for the task.

## 18. Boundaries Can Depend on Data on Both Sides

Grapheme segmentation cannot always be computed by segmenting each piece separately and summing their cluster counts.

For example:

- A combining mark at the start of the second piece can attach to the base letter at the end of the first piece after concatenation.
- Two regional indicators in two separate pieces can form a flag when joined.
- An emoji sequence with ZWJ at the boundary can merge into a single cluster when the parts are concatenated.

Thus, `countGraphemes(part1 + part2)` **does not necessarily equal** `countGraphemes(part1) + countGraphemes(part2)`. If you must split data into chunks for transmission or storage, split at safe boundaries or re-segment after reassembling the full string. Do not rely on summing per-chunk cluster counts when an exact count for the final string is needed.

When text data arrives as a stream (*streaming*), a proper segmenter may need to retain some context across chunk boundaries to decide breaks. Slicing purely by code unit or code point can break user-perceived units.

## 19. Common Misconceptions

| Misconception | Reality | How to Handle |
| --- | --- | --- |
| `String.length()` counts screen characters | It counts UTF-16 code units | Use grapheme segmentation when needed |
| One code point equals one visible character | Combining marks, RIs, and emoji sequences can span multiple code points | Distinguish the layers |
| `offsetByCodePoints` always slices at glyph boundaries | It only moves by code point | Use cluster boundaries for UI |
| Every combining mark starts a new cluster | Marks can belong to the same cluster as the base letter | Follow UAX #29 |
| A flag is one code point | Example RI flag has two code points | Inspect the actual encoded sequence |
| A ZWJ emoji is always one glyph on every device | Rendering depends on font/platform | Test rendering separately |
| An emoji is always 2 code units | Emoji sequences can be much longer | Count according to your actual target |
| `\\X` counts terminal columns | Clusters differ from display width | Use layout/width APIs |
| NFC turns every cluster into one code point | Does not work for most emoji sequences | Do not confuse normalization with segmentation |
| `BreakIterator` and regex are always identical | Implementations/data versions can differ | Test on target runtime |
| You can sum cluster counts of fragments | Boundaries can change upon concatenation | Re-segment the combined string |
| Testing a single simple emoji is enough | Bugs often hide in modifiers, flags, ZWJ | Test combinations |
| `\\X` validates well-formed Unicode | Segmentation regex does not replace a validator | Validate source separately |

## 20. Testing Checklist

A test suite should cover:

1. **Basic letter:** `A` → 1 unit, 1 point, 1 cluster.
2. **Combining mark:** `e\u0301` → 2 units, 2 points, 1 cluster.
3. **Precomposed:** `é` → 1 unit, 1 point, 1 cluster.
4. **Single emoji:** `😀` → 2 units, 1 point, 1 cluster.
5. **Emoji modifier:** `👍🏽` → 4 units, 2 points, 1 cluster.
6. **RI flag:** `🇻🇳` → 4 units, 2 points, 1 cluster.
7. **ZWJ family:** `👩‍👩‍👧‍👦` → 11 units, 7 points, 1 cluster on the tested runtime.
8. **Emoji variation selector:** `❤️` → 2 units, 2 points, 1 cluster.
9. **Keycap:** `1️⃣` → 3 units, 3 points, 1 cluster.
10. **Boundaries:** `Matcher.start()/end()` do not split surrogate pairs or detach accents in the examples.
11. **Limits:** taking 0, 1, 2, N clusters; empty input; negative limits rejected.
12. **Normalization:** `e\u0301` and `é` match under NFC yet have different raw code point counts.
13. **Fragment boundary:** combining marks, RIs, or ZWJ at concatenation points do not break logic.
14. **Unicode version:** test newer emoji sequences on the target JDK and platform.
15. **UI vs. server:** server counting matches UI requirements while separately enforcing byte limits.

### Exercises

1. Modify `GraphemeCountDemo` to add `"\r\n"` and check how the algorithm treats the CRLF pair during segmentation. Explain why text boundaries are not just printable characters.
2. Add two consecutive pairs of regional indicators to a string, print `Matcher.start()/end()`, and observe how they pair into clusters.
3. Write a function `lastCluster(String s)` that retrieves the last cluster using `Pattern.compile("\\X")` and test it with `e\u0301`, `👍🏽`, and the family emoji.
4. Compare `firstClusters(s, 1)` with `s.substring(0, 1)` when `s` starts with a non-BMP emoji or a combining mark; analyze the bugs that can occur.
5. Build a validator for "at most 10 extended grapheme clusters" and a separate validator for "at most 100 UTF-8 bytes". Write tests where the two accept/reject differently.
6. Compare `BreakIterator.getCharacterInstance(locale)` with regex `\\X` on the exact JDK version you use; record differences rather than assuming the two APIs are completely equivalent.
7. Try replacing `e\u0301` with a Vietnamese string containing a letter + multiple combining marks, then check unit, point, and cluster counts before/after NFC.
8. Create a string with ZWJ joining emojis and explain why rendering can differ across devices even though the Unicode string is identical.

## 21. Summary

A **grapheme cluster** is the essential text segmentation unit when building UIs that operate on "user-visible characters". It can contain **one or more Unicode code points**; each code point in turn uses **one or two UTF-16 code units** in Java. Combining marks, regional indicator flags, emoji skin tone modifiers, variation selectors, and ZWJ sequences make this distinction appear frequently.

In Java 17+, use `Pattern.compile("\\X")` to find extended grapheme cluster boundaries according to the runtime's Unicode data; `Matcher.start()` and `end()` return UTF-16 indexes used directly with `substring`. Use `codePointCount()` when you actually need the code point count, `String.length()` when you need code units, and count bytes if a protocol sets byte limits.

Finally, **segmentation is not rendering**: a grapheme cluster is not guaranteed to equal one glyph, one terminal cell, or a fixed pixel width. Test multilingual strings and emojis on the exact JDK, fonts, and platforms of your product, and apply segmentation algorithms only where they match business requirements.

## References

- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://www.unicode.org/reports/tr29/)
- [Unicode Technical Standard #51 — Unicode Emoji](https://www.unicode.org/reports/tr51/)
- [Oracle Java 21 — Pattern, `\\X` expression](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html)
- [Oracle Java 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Oracle Java 21 — BreakIterator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/BreakIterator.html)
- [Oracle Java 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html)
