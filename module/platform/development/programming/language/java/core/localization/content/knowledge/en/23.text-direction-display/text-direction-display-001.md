# Logical Order vs. Visual Order in Bidirectional (BiDi) Text — Java Localization

## 1. Why can a string be displayed out of storage order?

In Unicode, **logical order** is the order in which characters/code points appear in the source data. It is the order in which a program typically reads through a `String`, iterates `codePoints()`, stores in a database, sends over the network, and parses.

**Visual order** is the way components of text are laid out from left to right or right to left on a line when **rendered** for the reader. For left-to-right (**LTR**) languages such as Vietnamese or English, the two orders usually look the same. For right-to-left (**RTL**) languages such as Hebrew or Arabic, and especially when mixing RTL with Latin letters/digits, they **do not necessarily match**.

A piece of text may contain:

- Latin letters (usually LTR).
- Hebrew or Arabic letters (usually RTL).
- Digits `123`, which are normally presented in LTR order even inside an RTL segment.
- Spaces, parentheses, colons, hyphens, and symbols whose display direction is determined from **context**.
- Unicode directional control characters that do not produce visible glyphs but can affect how the reader sees the string.

An illustrative example of **logical order**:

~~~text
Source stored in order:
"a" "b" "c" " " ALEF BET GIMEL " " "1" "2" "3" " " "x" "y" "z"

ALEF = U+05D0, BET = U+05D1, GIMEL = U+05D2 (Hebrew)

In a line with an LTR base direction:
- The "abc " segment is at an LTR level.
- The Hebrew segment is at an RTL level.
- The digit segment "123" is at a nested LTR level.
- The " xyz" segment is back at an LTR level.
~~~

You should not predict screen order by reversing the entire `String`, nor should you rely on how a console displays Hebrew glyphs in a screenshot. Rendering software may apply the **Unicode Bidirectional Algorithm (UAX #9)** along with segment properties, fonts, symbols, base direction, and line wrapping.

**First takeaway:** BiDi is a matter of **laying out text for display**, not a rule for reversing strings for storage. Users may see glyphs in an order that does not match the character-by-character order in data, yet the text still has a consistent logical order for exchange between systems.

## 2. Four concepts to distinguish

| Concept | Meaning | Example |
| --- | --- | --- |
| Logical order | The order of code points/code units in data | `abc`, followed by Hebrew `U+05D0 U+05D1 U+05D2`, then `123` |
| Base paragraph direction | The base direction of a paragraph (LTR or RTL) | Vietnamese content can use an LTR base; an Arabic paragraph can choose RTL |
| Embedding level / directional run | The nesting level of segments sharing the same display rules | Even levels are usually LTR; odd levels are usually RTL |
| Visual order | The layout order of runs/glyphs after the algorithm, line breaking, and shaping | In the Java example, the digit run can be presented before the Hebrew run in an LTR line |

Do not confuse **paragraph direction** with **individual character direction**. An RTL paragraph can still contain the word `Java` or the number `123` that must preserve its internal LTR order. Conversely, an LTR paragraph can contain an RTL Hebrew/Arabic phrase.

### 2.1. Logical order is data order

Suppose:

~~~java
String hebrew = "\u05D0\u05D1\u05D2";
String paragraph = "abc " + hebrew + " 123 xyz";
~~~

These two statements are a **snippet** inside a method, not a standalone class. In a Java `String`, the UTF-16 order of the segment consists of `abc`, a space, three Hebrew letters, a space, three digits, a space, and `xyz`.

APIs such as `length()`, `charAt()`, `substring()`, `indexOf()`, `codePoints()`, `equals()`, and serialization **do not switch to visual order** just because a string contains RTL letters. Those APIs operate on logical content per the Java contract.

### 2.2. Base direction is not Locale

`Locale.forLanguageTag("ar")` describes the Arabic locale; `Locale.forLanguageTag("he")` describes the Hebrew locale. However, a **language tag alone does not fully determine the layout direction for every real-world paragraph**: a string may consist solely of numbers, product codes, Latin words, or user-supplied content. In a UI, paragraph direction (`dir`) and the direction of inserted fragments must be based on **semantics and layout context**, not just changing the `Locale`.

`Locale` is useful for choosing text/translation resources and cultural conventions; BiDi handles the directional properties of **text data and containers**.

## 3. How the Unicode Bidirectional Algorithm (UAX #9) works conceptually

The Unicode BiDi algorithm analyzes characters according to their directional properties and context to compute **embedding levels** and per-line visual order. General flow:

1. Determine **paragraph boundaries** and **base direction**.
2. Classify characters by bidi properties: strong LTR, strong RTL, weak numbers/formatting, neutral, and controls.
3. Process explicit embedding/override/isolate information (if present).
4. Resolve the direction of weak or neutral characters based on surrounding characters and Unicode rules.
5. Determine the **level** of text units: **even** levels represent LTR direction, **odd** levels represent RTL.
6. Once line boundaries are known, reorder the segments by level for **each line**, combined with shaping, glyphs, and line layout from the renderer.

Conceptual diagram:

~~~text
Unicode string (logical order in memory)
            |
            v
  Base direction + strong/weak/neutral characters
            |
            v
  Unicode BiDi -> embedding levels
            |
            v
  Line breaking -> reorder by levels
            |
            v
  Font/shaping/glyph layout -> screen

The source string remains in logical order.
~~~

**Level 1 does not simply mean "reverse every code point by hand."** BiDi together with text shaping has rules to preserve combining marks, ligatures, brackets, mirrored glyphs, and semantically correct cursor/caret behavior. A `StringBuilder.reverse()` call does not replace this algorithm.

### 3.1. Strong, weak, and neutral

- **Strong:** Latin letters usually have direction class L; Hebrew usually R; Arabic usually AL. They play the decisive role in determining the direction of neighboring regions.
- **Weak:** digits and some numeric symbols can depend on context; do not treat every digit character as an "RTL character" just because it sits inside an Arabic sentence.
- **Neutral:** spaces, many punctuation marks, parentheses, etc. can receive a level from surrounding characters.
- **Formatting controls:** certain code points such as `U+2066`, `U+2067`, `U+2068`, and `U+2069` are used to manage isolates; they usually produce no visible glyph but are still **real characters in the string**.

Because weak/neutral types take context into account, even a tiny change in content (adding a person's name, invoice code, colon `:`, or parentheses) can make characters shift or appear to flip direction.

### 3.2. Paragraph direction and the first strong character

If an application lets the base direction be **automatically determined from the first strong character**, a line starting with Latin can choose LTR, while a line starting with Hebrew/Arabic can choose RTL. However, text with no strong characters—for example containing only digits and punctuation—needs a **fallback direction** according to container policy or a flag.

In Java, `java.text.Bidi` provides four constants:

| `Bidi` Flag | Role |
| --- | --- |
| `DIRECTION_LEFT_TO_RIGHT` | Force LTR base direction |
| `DIRECTION_RIGHT_TO_LEFT` | Force RTL base direction |
| `DIRECTION_DEFAULT_LEFT_TO_RIGHT` | Choose from the first strong char; fall back to LTR if none |
| `DIRECTION_DEFAULT_RIGHT_TO_LEFT` | Choose from the first strong char; fall back to RTL if none |

Using a `DIRECTION_DEFAULT_...` flag does not mean **every character in the paragraph switches to the same direction**. It only decides the base direction. Inner LTR/RTL runs are still resolved by the algorithm.

## 4. Java SE 17: java.text.Bidi for directional analysis without mutating data

The `java.text.Bidi` class implements the bidirectional algorithm used in layout. It provides information about **base level**, **run boundaries**, and **run levels**, not a complete image-rendering API suite.

~~~java
import java.text.Bidi;

String text = "abc " + "\u05D0\u05D1\u05D2" + " 123 xyz";

Bidi bidi = new Bidi(
        text, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);
~~~

This is an **illustrative snippet inside a method**, requiring the import above; a standalone program is in section 8.

### 4.1. Key methods

| API | How to interpret |
| --- | --- |
| `new Bidi(String, flags)` | Analyze a paragraph with the requested base direction |
| `baseIsLeftToRight()` | Return `true` if the base direction is LTR |
| `getBaseLevel()` | Base level: 0 for LTR, 1 for RTL |
| `isLeftToRight()` | Line/paragraph is purely LTR with an LTR base |
| `isRightToLeft()` | Line/paragraph is purely RTL with an RTL base |
| `isMixed()` | Neither of the pure cases above; usually mixed directions or base differs from run direction |
| `getRunCount()` | Number of directional runs |
| `getRunStart(i)` | Starting UTF-16 offset of the i-th run in logical order |
| `getRunLimit(i)` | UTF-16 offset **immediately after** run i |
| `getRunLevel(i)` | Embedding level of run i |
| `getLevelAt(offset)` | Resolved level at the UTF-16 offset |
| `createLineBidi(start, limit)` | Create Bidi information for a **line** of the paragraph |
| `requiresBidi(char[], start, limit)` | Check whether a character range needs bidi analysis |
| `reorderVisually(levels, ..., objects, ...)` | Reorder **objects** by level, such as a list of directional runs |

**`getRunStart`, `getRunLimit`, and `getLevelAt` use UTF-16 offsets.** This is important when passing them to `String.substring(start, limit)` or converting between Java `char` and code point APIs.

### 4.2. Even and odd levels

In the Unicode BiDi system:

- Level `0`: LTR at the normal base layer.
- Level `1`: RTL.
- Level `2`: LTR nested inside an RTL context.
- Level `3`: deeper nested RTL, and so on.

A sentence **does not have just one level**. Data containing Hebrew and digits in the same sentence can yield runs at level `1` and level `2`; setting a base `LTR` flag does not erase those levels.

Do not assume `getRunCount()` equals the number of words, the number of Unicode code points, or the number of selectable UI elements. A run is a contiguous span sharing the same **resolved bidi level**, not a linguistic token.

### 4.3. Why not reverse the string yourself?

A wrong approach:

~~~java
String reversed = new StringBuilder(text).reverse().toString();
~~~

This is an example **you should not use** for BiDi display. Reversing mutates **logical order** and creates new data; it lacks any algorithm to handle base direction, weak/neutral characters, isolate boundaries, shaping, or line breaking. Even if a few Hebrew letters look "right" in a terminal for a short example, strings mixing digits/punctuation/Latin will easily break.

The right approach is to keep the logical `String` and let a Unicode BiDi-aware UI renderer lay out the text. `java.text.Bidi` is useful when you are **writing a custom layout component** or need to debug runs/levels.

## 5. Visual runs and digit order in an RTL segment

With the demo string:

~~~text
logical = "abc " + HEBREW(aleph,bet,gimel) + " 123 xyz"
UTF-16 length = 15
base = LTR
~~~

Runs computed by Java on the tested JDK:

| Run in logical order | UTF-16 range [start, limit) | Level | Logical content |
| --- | --- | --- | --- |
| `r0` | `[0,4)` | 0 (LTR) | `abc ` |
| `r1` | `[4,8)` | 1 (RTL) | 3 Hebrew letters and space |
| `r2` | `[8,11)` | 2 (LTR) | `123` |
| `r3` | `[11,15)` | 0 (LTR) | ` xyz` |

**Logical run order:** `r0, r1, r2, r3`.

After using the levels to **sort the run objects for display on a single line**, `Bidi.reorderVisually` yields:

~~~text
visual run order = r0, r2, r1, r3
~~~

This **does not mean** the stored string has `"123"` before Hebrew. The source string still contains Hebrew before `123`. Single-line layout sees level 1 RTL enclosing a level 2 LTR run, causing the order of the **run objects** to change.

Do not conclude that Hebrew words are displayed by arbitrarily reversing each Unicode code point. The renderer may apply combining-character handling, contextual shaping, and its own glyph placement. The table above describes **run-level reordering**, not pixel coordinates or the complete final visual appearance.

If a paragraph wraps across multiple lines, Unicode BiDi operates **line by line** after breaking, so a single run table for the whole paragraph cannot fully describe the visual result. `createLineBidi` is useful once the layout engine knows line boundaries.

## 6. Unicode controls: when are they needed and why be cautious?

In most natural text, the BiDi algorithm based on strong/weak/neutral types is sufficient. When an independent text fragment with unknown direction is inserted into a sentence with a different directional context, **isolation** is sometimes needed so it does not cause unintended effects on surrounding punctuation or text.

Some common control characters:

| Code point | Name | General meaning |
| --- | --- | --- |
| `U+200E` | LRM — Left-to-Right Mark | Zero-glyph LTR directional mark |
| `U+200F` | RLM — Right-to-Left Mark | Zero-glyph RTL directional mark |
| `U+061C` | ALM — Arabic Letter Mark | Zero-glyph Arabic directional mark |
| `U+2066` | LRI — Left-to-Right Isolate | Start an LTR isolate |
| `U+2067` | RLI — Right-to-Left Isolate | Start an RTL isolate |
| `U+2068` | FSI — First Strong Isolate | Start an isolate determined from the first strong char |
| `U+2069` | PDI — Pop Directional Isolate | Close an isolate |
| `U+202A`/`U+202B` | LRE/RLE | Legacy embedding |
| `U+202D`/`U+202E` | LRO/RLO | Directional override, carries risk of visual deception |
| `U+202C` | PDF | End embedding/override |

`FSI`/`PDI` isolates (or `LRI`/`RLI` when the direction is known) are recommended for plain text containing arbitrary inserted fragments when directional control is genuinely needed. Legacy embedding/override mechanisms easily affect surrounding text more strongly than intended.

**Do not automatically add invisible characters into transactional/identifier data without a contract.** Those code points get stored, can survive copy/paste/URLs, or affect string comparison, signatures, search, and audits. In HTML, it is usually better to use **directional attributes and semantic elements** rather than inserting control characters directly.

### 6.1. HTML: isolating elements by direction with bdi, dir

In HTML UI, when inserting a name or code of unknown direction into a sentence, a useful pattern is:

~~~html
<p dir="rtl">
  <span>...</span>
  <bdi dir="auto">user-supplied-name</bdi>
  <span>...</span>
</p>
~~~

This is **illustrative HTML markup**; in practice, user strings must be **escaped or inserted via textContent** to prevent HTML injection. `<bdi>` isolates the direction of its content from the surrounding context; `dir="auto"` picks the direction based on the content. For strings that are always LTR such as codes/IDs, consider a dedicated `dir="ltr"` element or the appropriate CSS mechanism for the component.

Do not use `text-align: right` as a substitute for **direction**: alignment is a layout concern and does not resolve the ordering of characters and neutral punctuation within the content.

## 7. Data, indices, caret, and security issues

### 7.1. Do not convert a logical index to a visual index by simple reversal

Many Java APIs use **UTF-16 offsets** for positioning:

~~~java
int index = paragraph.indexOf("123");  // UTF-16 offset in the original string
~~~

In the demo string, `index` is 8. Even though on screen the `123` run can be placed before the Hebrew run, `indexOf("123")` still returns **8**, without automatically converting to visual coordinates.

Caret movement, selection, highlighting, delete/backspace, and mouse clicks in BiDi text require **mapping between logical positions and visual caret positions** performed by the text layout/editor engine. A single visual position can correspond to different logical positions at run boundaries; do not use `length - index` or run order to drive the caret manually.

In Swing/AWT or other renderers, rely on BiDi- and shaping-aware text/layout components rather than rewriting the entire algorithm yourself.

### 7.2. Do not "fix" Hebrew/Arabic data by reversing the string before saving

A browser/renderer may display an RTL sentence in a different order than code point order. That is not evidence that the data is wrong.

If you reverse text yourself before saving:

- Copy/paste across other systems can produce a string in the wrong logical order.
- Searching, extraction, comparison, and language processing break.
- Strings mixing numbers, Latin, parentheses, and RTL letters easily render even more garbled.
- When a renderer applies BiDi again, the effect can look like "double reversal."

**Preserve logical order** and handle presentation concerns at the UI boundary.

### 7.3. BiDi control characters can be abused

Invisible control characters such as `U+202E` (RLO) or certain isolate/override combinations can make **text display in a different order from the data read by a parser or compiler**. This is a class of risk in code review, filenames, extensions, logs, IDs, URLs, and user-supplied content. For example, a filename containing a directional control can appear to have a different extension than its actual byte or `String` structure.

Protection principles:

1. **Inspect source/logs in logical order** or render formatting controls with explicit code names in a safe viewer.
2. **Do not trust what characters look like visually** as proof of a filename, domain, extension, command, or signature content.
3. For sensitive fields (identifiers, source code, extensions, paths, tokens), consider **rejecting or warning on** disallowed bidi control characters per policy; do not blindly strip them from natural prose.
4. When rendering user data in HTML, you still must escape against injection; BiDi isolation **does not** replace HTML escaping.
5. Rules for confusable detection, Unicode normalization, canonicalization, and access control are separate responsibilities; do not assume `Bidi` solves them automatically.

### 7.4. Search and collation still rely on logical data

`String.equals`, `indexOf`, tokenization, and `Collator` process strings according to their respective API contracts, not based on **the glyph order visible on screen**. Locale-based collation is also not the same task as Unicode BiDi.

An RTL snippet that looks reversed when pasted does not mean you should sort code points by visual position. Separate the **data model**, **search/collation**, and **text layout**.

## 8. Standalone Java 17 example: Bidi runs, levels, and visual order

Create the file **`BidiOrderDemo.java`** with contents:

~~~java
import java.text.Bidi;
import java.util.Arrays;
import java.util.Locale;
import java.util.stream.Collectors;

public class BidiOrderDemo {
    static String codePoints(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format(Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String hebrew = "\u05D0\u05D1\u05D2";
        String paragraph = "abc " + hebrew + " 123 xyz";
        Bidi bidi = new Bidi(
                paragraph, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

        System.out.println("logical code points: " + codePoints(paragraph));
        System.out.println("utf16 length=" + paragraph.length());
        System.out.println("requiresBidi=" + Bidi.requiresBidi(
                paragraph.toCharArray(), 0, paragraph.length()));
        System.out.println("base level=" + bidi.getBaseLevel());
        System.out.println("isMixed=" + bidi.isMixed());
        System.out.println("run count=" + bidi.getRunCount());

        Object[] names = new Object[bidi.getRunCount()];
        byte[] levels = new byte[bidi.getRunCount()];
        for (int i = 0; i < bidi.getRunCount(); i++) {
            int start = bidi.getRunStart(i);
            int end = bidi.getRunLimit(i);
            int level = bidi.getRunLevel(i);
            names[i] = "r" + i;
            levels[i] = (byte) level;
            System.out.println("run " + i + ": [" + start + "," + end
                    + ") level=" + level
                    + " codes=" + codePoints(
                            paragraph.substring(start, end)));
        }

        Bidi.reorderVisually(levels, 0, names, 0, names.length);
        System.out.println("run order on display=" +
                Arrays.toString(names));

        Bidi rtl = new Bidi(
                hebrew, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);
        System.out.println("hebrew base level=" + rtl.getBaseLevel());
        System.out.println("hebrew rightToLeft=" + rtl.isRightToLeft());
        System.out.println("storage unchanged=" +
                paragraph.equals("abc " + hebrew + " 123 xyz"));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 BidiOrderDemo.java
java BidiOrderDemo
~~~

**Verified stdout** on a JDK with the corresponding BiDi algorithm:

~~~text
logical code points: U+0061 U+0062 U+0063 U+0020 U+05D0 U+05D1 U+05D2 U+0020 U+0031 U+0032 U+0033 U+0020 U+0078 U+0079 U+007A
utf16 length=15
requiresBidi=true
base level=0
isMixed=true
run count=4
run 0: [0,4) level=0 codes=U+0061 U+0062 U+0063 U+0020
run 1: [4,8) level=1 codes=U+05D0 U+05D1 U+05D2 U+0020
run 2: [8,11) level=2 codes=U+0031 U+0032 U+0033
run 3: [11,15) level=0 codes=U+0020 U+0078 U+0079 U+007A
run order on display=[r0, r2, r1, r3]
hebrew base level=1
hebrew rightToLeft=true
storage unchanged=true
~~~

**Explanation:**

1. `logical code points` prints Unicode code points in the order **actually stored** in `String`; Hebrew glyphs are not printed to prevent BiDi console layout from confusing the output.
2. Length `15` is **15 UTF-16 code units**; the characters in the example are in the BMP.
3. `requiresBidi=true` because the mixed paragraph has RTL characters requiring directional analysis.
4. The first strong character is Latin, so the base level is `0` (LTR); `isMixed=true` because there are multiple directions.
5. Runs `r0`–`r3` are listed **in logical order**, with `[start,limit)` as UTF-16 indices.
6. `reorderVisually` changes the order of the **`names` array describing the runs**, producing `[r0, r2, r1, r3]` for a single line. It does **not** modify `paragraph`, render glyphs, or produce a fully shaped sentence.
7. When containing only Hebrew, the first strong char is RTL so the base level is `1`, and `isRightToLeft()` is `true`.
8. `storage unchanged=true` confirms that analyzing and reordering the run-name array does not alter the source string.

**Advisory:** level and run results can depend on the Unicode algorithm/data version in the runtime and the line-layout context. This lesson uses a small example on a tested JDK to teach how to read the API; do not hardcode the run order of a fixed snippet for general UI rendering.

## 9. Why Java Bidi alone is not enough to draw a paragraph

`java.text.Bidi` provides **bidi analysis**; it is not a complete text rendering library. Accurate drawing also requires:

- **Measuring glyph widths** with the actual font.
- **Script-specific shaping** such as Arabic contextual forms and ligatures.
- **Grapheme clustering** so combining marks/caret/delete do not split clusters incorrectly.
- **Line breaking** before reordering each line.
- **Mirroring** and handling brackets/punctuation in RTL contexts.
- **Logical-to-visual mapping** for caret, selection, hit testing, and accessibility.
- **Font fallback** and glyph selection when a font does not support a script.

Therefore, Swing/AWT/browser/Android systems or dedicated layout libraries should generally handle drawing. Avoid rewriting the entire Unicode BiDi Algorithm if you only want to display names, translations, or sentences with RTL parts.

### 9.1. Line-creation APIs

`Bidi.createLineBidi(lineStart, lineLimit)` takes **UTF-16 offsets** within the paragraph and creates a line analysis object, suitable once **the layout engine has determined line boundaries**. This is not a method that measures width and wraps lines automatically.

At the layout layer, a paragraph may split into different lines depending on the display area size; thus the visual order of a long paragraph cannot be obtained by a single full-string reversal.

### 9.2. Accessibility and clipboard

Seeing text on screen is only one channel. Screen readers, the clipboard, search features, keyboard navigation, and serialization also need **logical** order. In a UI, keep text in its original content order and let accessibility/layout tools interpret bidi. If you export "visual order text" by reversing characters, many screen readers and downstream tools will receive corrupted data.

## 10. Common mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Reversing a `String` to display RTL | Breaks when mixing digits, Latin, punctuation, shaping | Keep logical order; hand rendering to a BiDi-aware UI |
| Assuming `Locale` dictates all text direction | Mixed-script content or numbers need separate handling | Choose base direction and isolation by context |
| Mistaking `getRunStart` for a visual index | Selection/highlighting shifts out of place | Run offsets are logical UTF-16 |
| Mistaking `getRunCount` for word count | Broken tokenization logic | A run is a span with the same resolved bidi level |
| Treating `reorderVisually` as producing a finished display sentence | Missing shaping, glyphs, line breaks | Renderer/layout engine handles subsequent steps |
| Using `text-align:right` instead of direction | Punctuation and mixed words remain out of order | Use text-direction semantics |
| Failing to isolate user-inserted names/words in an opposite-direction sentence | Surrounding punctuation/text can be affected | `<bdi dir="auto">` or an equivalent isolation mechanism |
| Manually adding RLO/LRO to data to "fix layout" | Invisible characters can spoof display, break copy/paste | Use layout protocol, sanitize per field |
| Stripping all RTL characters in user-generated text | Blocks real languages | Only restrict **format controls** in fields needing protection |
| Relying on screenshots to verify byte/logical order | Glyphs may be reordered | Inspect code points/logical representation |
| Using `length - i` to convert a caret index | Ignores multiple runs, levels, graphemes | Hit testing with dedicated text layout |
| Sorting data by visual order | Inconsistent comparison results | Use `Collator`/search rules on logical text |

## 11. Testing and exercises

### Practical tests you should have

1. **Pure LTR text:** Vietnamese/English sentence, LTR base, content unchanged.
2. **Pure RTL text:** Hebrew/Arabic paragraph, check base direction and proper rendering.
3. **Mixed RTL/LTR:** Hebrew sentence containing `Java` and `123`, Vietnamese sentence containing an Arabic name.
4. **Weak/neutral:** `:`, `-`, parentheses, spaces at run boundaries.
5. **Control characters:** with/without isolates, LRM/RLM, and test cases where invisible Unicode controls could mislead.
6. **Source data:** compare `String.codePoints()` before and after display; the renderer must not mutate source data.
7. **Selection/caret:** test selecting text across run boundaries, backspace/delete, and mouse interaction.
8. **Line wrapping:** same paragraph in narrow vs. wide viewports, checking visual order per line.
9. **Font/shaping:** Arabic contextual forms, combining marks, ligatures, fallback.
10. **HTML input:** RTL username inside an LTR sentence and vice versa; `<bdi>` combined with HTML escaping.
11. **Security:** filename/source/log containing bidi overrides; verify the ability to reveal hidden character code names.
12. **Regression:** pin the runtime/layout engine if the product tests output against exact coordinates or screenshots.

### Exercise 1 — change base direction

Run the demo but change the `DIRECTION_DEFAULT_LEFT_TO_RIGHT` flag to `DIRECTION_RIGHT_TO_LEFT`. Read `getBaseLevel()`, `getRunCount()`, `getRunLevel(i)`, and the run-order array; explain why **the logical order of code points still does not change**.

### Exercise 2 — reorder source segments

Move Hebrew to the start of `paragraph`, then use `DIRECTION_DEFAULT_LEFT_TO_RIGHT`. Because the first strong char is Hebrew, the base direction can be RTL. Print `getBaseLevel()` and compare it with the Latin-first version.

### Exercise 3 — logical indices

Find `paragraph.indexOf("123")` (`8` in the demo), then check `Bidi.getLevelAt(8)`. Explain why index **8** remains valid even though the digit run may be placed at a different visual position.

### Exercise 4 — HTML isolation

Create an RTL notification containing a user-entered Latin account name. Render two versions: one placing the name directly in a `span`, and one wrapping it in `<bdi dir="auto">`. Inspect punctuation before/after the name. Make sure to escape/insert text safely in both.

### Exercise 5 — check invisible controls

Write a function that inspects the code points of a technical ID and warns if `U+202A`–`U+202E` or `U+2066`–`U+2069` is present. Distinguish **free-form UI data** from identifier fields with strict policies; do not blindly strip all valid RTL characters.

### Exercise 6 — rendering is not reversing

Try `new StringBuilder(paragraph).reverse()`, then compare the code points of the new string against `paragraph`. Show that the data actually changed, yet the new result is not a `Bidi.reorderVisually` and cannot replace rendering.

## 12. Summary

**Logical order is the order in which Unicode data is stored and processed; visual order is how a renderer arranges runs/glyphs so users can read bidirectional text.** They can differ when mixing Hebrew/Arabic with Latin, digits, and punctuation. Base direction, character classes, embedding levels, isolate controls, and line boundaries affect layout, but do not require reversing the source string.

Java `java.text.Bidi` lets you read base direction, levels, offsets, and reorder **run objects** into visual order. Those indices still follow **UTF-16 logical offsets**; `Bidi` does not itself render glyphs, perform shaping, or handle full caret movement. In multilingual applications, keep source text intact, use BiDi-capable UI/layout engines, isolate inserted fragments when needed, and inspect invisible controls in sensitive fields to reduce the risk of confusion or abuse.

**References:**

- Java SE 17, `java.text.Bidi`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Bidi.html
- Java SE 17, `java.lang.String`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html
- Unicode Standard Annex #9 — Unicode Bidirectional Algorithm: https://www.unicode.org/reports/tr9/
- Unicode Security Considerations (UTR #36): https://unicode.org/reports/tr36/
- W3C Internationalization — Working with text direction: https://www.unicode.org/International/articles/inline-bidi-markup/
