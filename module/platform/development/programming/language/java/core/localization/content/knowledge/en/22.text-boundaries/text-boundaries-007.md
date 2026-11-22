# Language-Aware Line Breaking and UI Width Layout in Java

## 1. Two Different Questions When Text Must Wrap

A long paragraph needs to be split into multiple lines to display inside a card, window, dialog, document, or report. Yet "line wrapping" actually involves **two distinct decisions**:

1. **Linguistic/semantic:** Which positions in the string are **allowed line-break boundaries** according to language and Unicode rules? Can a line break at a space, between two CJK characters, before punctuation, inside an emoji, or inside a Thai word?
2. **UI layout:** Given the **actual width**, font, font size, kerning, shaping, spacing, direction, and available space, **which break position should be chosen** so the line fits the drawing area?

In Java, two APIs typically represent these two roles:

- `java.text.BreakIterator.getLineInstance(Locale)`: identifies **potential line-break positions** in a string for a locale, **without taking a display area width**.
- `java.awt.font.LineBreakMeasurer`: produces `TextLayout` segments that **fit within a wrapping width**, taking Java 2D text metrics and break points into account. It needs font/attributes and a `FontRenderContext`, and can accept an application-specified `BreakIterator`.

**Core point:** `BreakIterator` cannot know whether a box is 120 px or 480 px wide. Conversely, computing width while ignoring language line-breaking rules can split words, break character clusters, or misplace punctuation.

### Learning Objectives

After this lesson, you will be able to distinguish "valid" break boundaries from "fits the width" layout decisions, use `BreakIterator.getLineInstance(locale)`, understand how `LineBreakMeasurer` and `TextLayout` work, choose where wrapping should be handled in Swing/Java 2D or a frontend, and avoid confusing `String.length()` with display width.

## 2. Four Boundary Levels in Text

Java provides `BreakIterator` for multiple segmentation types, each answering a different question:

| Factory | Question | Use When |
| --- | --- | --- |
| `BreakIterator.getCharacterInstance(locale)` | Character cluster boundaries for cursor movement / character slicing | Moving the caret, selecting text; test newer Unicode |
| `BreakIterator.getWordInstance(locale)` | Word / segment-unit boundaries recognized by the segmenter | Highlighting, word-level actions, basic search |
| `BreakIterator.getLineInstance(locale)` | Positions **where lines may break** | Language-aware line wrapping |
| `BreakIterator.getSentenceInstance(locale)` | Sentence boundaries | Sentence-level analysis/presentation |

Do not interchange these factories:

- A **word boundary** does not equal a **line-break opportunity**.
- A **character boundary** does not mean a line break is allowed there in a paragraph.
- A **sentence boundary** does not mean the UI must start a new line at the end of every sentence.
- A **line-break boundary** does not dictate that the UI actually breaks a line at that position.

All four operations involve text, yet they carry different meanings. An application wanting to highlight individual words should not use a line-break iterator in place of a word processor; an application wanting natural wrapping should not start a new line after every code point.

### Terminology: Opportunity, Soft Wrap, Hard Break

- **Line-break opportunity:** a position eligible for breaking under linguistic rules.
- **Soft wrap:** wrapping caused by **insufficient width**; does not necessarily insert newline characters into the underlying data string.
- **Hard break / explicit break:** the data author inserted a newline or separator intending a new line or paragraph.
- **Overflow:** a segment that cannot be split cleanly yet still exceeds the width; the UI needs a scrolling, truncation, forced-break, or alternate display policy.
- **Hyphenation:** breaking a word at a valid position and optionally inserting a hyphen; a distinct linguistic capability not handled completely out-of-the-box by every Java formatter.

A line-break iterator can return many allowed break points while the UI chooses **not** to break at any of them because the entire line fits.

## 3. Why Does Line Breaking Depend on Language?

Each language and script has different conventions:

| Context | Typical Considerations |
| --- | --- |
| English and many space-delimited languages | Prefer breaking between words; avoid stranding punctuation incorrectly |
| Vietnamese | Spaces usually separate syllables; a visually valid line break does not necessarily match semantic word splitting |
| Japanese | Can break between certain characters, though many punctuation/small-kana pairs are constrained by *kinsoku* rules |
| Chinese | Usually omits spaces between words; punctuation and character-class rules matter |
| Thai and Khmer | Can write multiple words without spaces; require dictionary/model-based segmentation or appropriate language data |
| Arabic / Hebrew | Beyond break points, text direction and shaping must be handled |
| Emojis / combining-mark sequences | Avoid splitting a grapheme cluster, surrogate pair, or composite emoji |
| URLs / file paths / long identifiers | May need a policy for strings lacking ordinary break opportunities |

**Not every space permits a break.** For example, U+00A0 NO-BREAK SPACE separates components visually while forbidding a line break there under normal rules. Conversely, U+200B ZERO WIDTH SPACE can mark a break opportunity without displaying whitespace.

**Not every hyphen forces a line break.** Ordinary hyphens can influence break opportunities; soft hyphen U+00AD is a conditional hint, and whether a hyphen is rendered when breaking depends on the engine. Do not assume the JDK's `BreakIterator` provides standard hyphenation for every language or inserts hyphen characters into text automatically.

### Unicode Rules Are Not "Break After Every Code Point"

Unicode Standard Annex #14 defines the Unicode Line Breaking Algorithm, consisting of line-breaking classes and many rules permitting or forbidding breaks. Engines may additionally apply locale tailoring or dictionary data. This explains why a regex such as `"\\s+"` or `String.split(" ")` is usually insufficient for Chinese, Japanese, Thai, and special characters.

Java's algorithms and datasets can change across JDK versions, CLDR/providers, and locale support. Therefore, when a product requires exact line breaks for a specific language, test **on the actual runtime and rendering engine**.

## 4. `BreakIterator.getLineInstance(Locale)`: Finding Allowed Break Points

Basic API:

```java
Locale locale = Locale.forLanguageTag("vi-VN");

BreakIterator breaker =
        BreakIterator.getLineInstance(locale);

breaker.setText("Một đoạn văn tiếng Việt để kiểm tra ngắt dòng.");
```

`BreakIterator` uses **offsets in a UTF-16 string**. Calling `first()` gets the start point, `next()` returns each boundary in turn and `BreakIterator.DONE` at the end. `last()` gives the final boundary of the range.

A typical traversal loop:

```java
int start = breaker.first();

for (int end = breaker.next();
        end != BreakIterator.DONE;
        start = end, end = breaker.next()) {

    String segment = text.substring(start, end);
    // A segment between two consecutive break opportunities.
    // NOT YET a width-laid-out line.
}
```

This is an illustrative snippet inside a method with `text` and `breaker` already declared. The returned `segment`s are regions between boundaries, **not** "the lines" the UI will necessarily display.

### Useful Methods

| Method | Role |
| --- | --- |
| `getLineInstance(locale)` | Creates a locale-specific line-break iterator |
| `setText(String)` | Assigns the text to analyze |
| `first()` / `last()` | Moves to the first/last boundary |
| `next()` / `previous()` | Traverses across boundaries |
| `following(offset)` | First boundary **after** `offset` |
| `preceding(offset)` | Last boundary **before** `offset` |
| `isBoundary(offset)` | Checks whether `offset` is a boundary |
| `current()` | Current position, which can change when calling APIs |
| `BreakIterator.DONE` | Sentinel value indicating no more boundaries |

**Note:** `isBoundary` and boundary-lookup calls can mutate the internal traversal position. If you need to preserve loop positions, manage `start`/`end` separately or create an appropriate iterator/clone.

### 4.1. Runnable Java 17: Proving Line Boundaries Are Not Viewport Lines

File `LineBoundaryDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class LineBoundaryDemo {
    public static void main(String[] args) {
        String text = "Hello world, welcome to Java.";

        BreakIterator breaker =
                BreakIterator.getLineInstance(Locale.US);
        breaker.setText(text);

        int start = breaker.first();
        int end = breaker.last();

        System.out.println("startAtZero=" + (start == 0));
        System.out.println("endAtLength=" +
                (end == text.length()));
        System.out.println("startBoundary=" +
                breaker.isBoundary(0));
        System.out.println("endBoundary=" +
                breaker.isBoundary(text.length()));

        int previous = breaker.first();
        int opportunities = 0;
        boolean increasing = true;

        for (int next = breaker.next();
                next != BreakIterator.DONE;
                next = breaker.next()) {

            increasing &= next > previous;
            previous = next;
            opportunities++;
        }

        System.out.println("orderedBoundaries=" + increasing);
        System.out.println("hasEndBoundary=" +
                (previous == text.length()));
        System.out.println("hasOpportunities=" +
                (opportunities > 0));
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 LineBoundaryDemo.java
java LineBoundaryDemo
```

Stable stdout:

```text
startAtZero=true
endAtLength=true
startBoundary=true
endBoundary=true
orderedBoundaries=true
hasEndBoundary=true
hasOpportunities=true
```

The program checks only **general boundary invariants**, without hardcoding a specific locale provider's list of break positions. The output has no `viewportWidth` variable at all — because `BreakIterator` **takes no width parameter**.

If you want to observe the actual candidate boundaries, you can print each `next`, `substring(previous, next)`, and UTF-16 codes; exact results can vary across JDK/provider/locale. In a content-rendering program, these candidates must be combined with text measurement rather than inserting `"\n"` after every candidate.

## 5. UI Width Belongs to a Different Layer

A 160-unit-wide textbox and a 480-unit-wide panel contain **the same string**. The linguistic break opportunities may be identical, yet the displayed line count typically differs.

```text
ORIGINAL TEXT
"Internationalization needs careful line breaking."

       |
       +--> BreakIterator(locale)
       |       └── Linguistically allowed break boundaries
       |
       +--> Layout context
                font + size + shaping + text direction
                + available width + padding + scaling
                        |
                        ├── narrow region → more soft-wrapped lines
                        └── wide region   → fewer soft-wrapped lines
```

Do not compute width using `String.length()`, `codePointCount()`, or "average 8 px per letter". Fonts have varying narrow/wide glyphs, kerning, ligatures, emojis, combining marks, and fallback fonts. The same count of Unicode code points can occupy very different widths.

### Comparing Different Kinds of Sizes

| Measurement | Example API | What Is It For? |
| --- | --- | --- |
| UTF-16 unit count | `s.length()` | Indexing inside `String`; **not** width |
| Unicode code point count | `s.codePointCount(0, s.length())` | Counting code points; **not** width |
| Grapheme cluster count | Regex `\X` or an appropriate segmenter | Counting user-perceived character clusters; **not** pixel width |
| Font advances / glyph metrics | `TextLayout`, `FontRenderContext` | Measurements needed for text layout |
| Wrapping width | Layout region size in rendering coordinate space | Actual horizontal limit |
| Displayed line count | Text layout result | Depends on both break points and width/font |

For example, `"WWWW"` and `"iiii"` are both 4 UTF-16 units long, yet in many proportional fonts their actual widths differ dramatically. Do not implement line wrapping by slicing after every 20 `char`s when the goal is maintaining accurate visual width.

### Width Is Not Just CSS Pixels

In Java 2D, `LineBreakMeasurer.nextLayout(float wrappingWidth)` takes width in **the coordinate space of the text layout / render context**, typically matching the user-space coordinates of the drawing operation. If displaying on a HiDPI screen, with transforms, scaling, or different font rendering, manage measurements using the same render context as drawing. Do not assume `100f` is always 100 device pixels independent of all transforms.

## 6. `LineBreakMeasurer`: Bringing Language Boundaries into Layout

Java 2D provides `java.awt.font.LineBreakMeasurer`. It accepts:

- an `AttributedCharacterIterator` for **one paragraph** with font/formatting attributes;
- a `FontRenderContext` to measure glyphs in the rendering environment;
- an optional `BreakIterator` for line-break opportunities.

Example object creation:

```java
AttributedString attributed = new AttributedString(text);
attributed.addAttribute(
        TextAttribute.FONT, new Font("Dialog", Font.PLAIN, 16));

FontRenderContext frc = new FontRenderContext(
        new AffineTransform(), true, true);

LineBreakMeasurer measurer = new LineBreakMeasurer(
        attributed.getIterator(),
        BreakIterator.getLineInstance(locale),
        frc);
```

This is an illustrative snippet inside a method, requiring imports from `java.awt.Font`, `java.awt.font.*`, `java.awt.geom.AffineTransform`, `java.text.*`, and `java.util.Locale`.

`nextLayout(width)` returns a `TextLayout` representing the slice of characters that fits on one line within the requested width, and **advances the position** inside the measurer. You can iterate until `getPosition() == iterator.getEndIndex()`.

If a word is too long to fit even at the start of a line, `LineBreakMeasurer`'s default policy can take a partial word to guarantee forward progress. Therefore, **do not assert that every line breaks strictly at a word boundary**. Oracle documentation notes that it prefers whole words when they fit, yet when the first word is too long it can force a split so characters can be placed on the line.

### API Comparison

| API | Takes width? | Measures glyphs/fonts? | Returns laid-out lines? |
| --- | --- | --- | --- |
| `BreakIterator.getLineInstance(locale)` | No | No | No; returns boundaries |
| `LineBreakMeasurer.nextLayout(width)` | **Yes** | **Yes** | **Yes**, `TextLayout` |
| `TextLayout.getAdvance()` | Not a wrap algorithm | Represents advance along the line axis | Metric of an already-created layout |
| `String.length()` | No | No | No |
| `String.split("\\R")` | No | No | Splits only **existing newline markers** |
| `JTextArea`/Swing UI | Component size | Via UI engine | Can auto-wrap depending on configuration |

### 6.1. Runnable Java 17 Program: Width Changes Line Count

File `WidthLayoutDemo.java`:

```java
import java.awt.Font;
import java.awt.font.FontRenderContext;
import java.awt.font.LineBreakMeasurer;
import java.awt.font.TextAttribute;
import java.awt.font.TextLayout;
import java.awt.geom.AffineTransform;
import java.text.AttributedString;
import java.text.BreakIterator;
import java.util.Locale;

public class WidthLayoutDemo {
    record Result(int lines, String reconstructed) {}

    private static Result layout(
            String text, float width,
            Font font, FontRenderContext frc) {

        AttributedString styled = new AttributedString(text);
        styled.addAttribute(TextAttribute.FONT, font);

        LineBreakMeasurer measurer = new LineBreakMeasurer(
                styled.getIterator(),
                BreakIterator.getLineInstance(Locale.US),
                frc);

        StringBuilder recovered = new StringBuilder();
        int lines = 0;

        while (measurer.getPosition() < text.length()) {
            int start = measurer.getPosition();
            TextLayout line = measurer.nextLayout(width);

            if (line == null) {
                throw new IllegalStateException(
                        "Layout did not advance");
            }

            int end = measurer.getPosition();
            recovered.append(text, start, end);
            lines++;
        }

        return new Result(lines, recovered.toString());
    }

    public static void main(String[] args) {
        String paragraph =
                "A quick brown fox jumps over the lazy dog. "
                + "A quick brown fox jumps over the lazy dog.";

        Font font = new Font("Dialog", Font.PLAIN, 18);
        FontRenderContext frc = new FontRenderContext(
                new AffineTransform(), true, true);

        Result narrow = layout(paragraph, 100f, font, frc);
        Result wide = layout(paragraph, 400f, font, frc);

        System.out.println("narrowPreserved=" +
                narrow.reconstructed().equals(paragraph));
        System.out.println("widePreserved=" +
                wide.reconstructed().equals(paragraph));
        System.out.println("narrowHasLines=" +
                (narrow.lines() > 0));
        System.out.println("wideHasLines=" +
                (wide.lines() > 0));
    }
}
```

Save source as UTF-8, compile and run in a JDK 17 environment containing the `java.desktop` module:

```bash
javac -encoding UTF-8 WidthLayoutDemo.java
java WidthLayoutDemo
```

Expected stdout:

```text
narrowPreserved=true
widePreserved=true
narrowHasLines=true
wideHasLines=true
```

Neither layout **modifies the original text**, because `reconstructed` joins the slices cut at the measurer's offsets. Actual line counts can vary by font and rendering environment; the demo intentionally does not hardcode `narrow.lines()` or `wide.lines()`. To observe them, add:

```java
System.out.println("narrowLines=" + narrow.lines());
System.out.println("wideLines=" + wide.lines());
```

That is an addition **inside `main`**. Typically a 100-unit region produces more lines than a 400-unit region, though exact values depend on the font and metrics. In a production UI, use the **exact actual width** after subtracting padding/insets/scrollbars, and render with the same `FontRenderContext` you used to measure.

### 6.2. `TextLayout` Does Not Draw Everything Automatically

`LineBreakMeasurer.nextLayout` returns a layout, yet the client still must position each line, handle height, baseline, ascent/descent/leading, and draw `layout.draw(Graphics2D, x, y)` at the right coordinates. You also need to handle alignment, tabs, paragraph spacing, clipping, and text direction as required.

For a multi-line paragraph, a layout loop can accumulate:

```java
baseline += layout.getAscent();
layout.draw(g2d, x, baseline);
baseline += layout.getDescent() + layout.getLeading();
```

This is an illustrative snippet inside a paint method; `layout`, `g2d`, `baseline`, and `x` must already exist. It is not a standalone `main` program.

## 7. Explicit Newlines Differ from Soft Wrapping

Consider the text:

```text
Hello world.
Next paragraph.
```

If there is a `\n` character between the two sentences, that is **the data author's decision**. If there is no newline and the UI is narrow enough that the word "Next" wraps to the next line, that is a **soft wrap**.

**Do not insert newlines into the model when you only want responsive layout.** When the window resizes, pre-inserted newlines become hard breaks and can ruin layout on wide screens.

Several line-ending markers exist in Unicode or platform conventions:

- LF: `\n` (U+000A);
- CR: `\r` (U+000D);
- CRLF: two code units `\r\n`, which should usually be treated as one sequence;
- U+0085 NEXT LINE, U+2028 LINE SEPARATOR, U+2029 PARAGRAPH SEPARATOR may need explicit policies depending on the data source.

Do not call `String.split("\n")` and conclude you have handled every newline convention. Java regex `\R` matches any Unicode linebreak sequence as defined by `Pattern`, including CRLF.

### Runnable Java 17: Splitting Hard Breaks

File `ExplicitLineBreakDemo.java`:

```java
public class ExplicitLineBreakDemo {
    public static void main(String[] args) {
        String text = "First\r\nSecond\nThird";

        String[] logicalLines = text.split("\\R", -1);

        System.out.println("lines=" + logicalLines.length);
        System.out.println("first=" + logicalLines[0]);
        System.out.println("second=" + logicalLines[1]);
        System.out.println("third=" + logicalLines[2]);
    }
}
```

```bash
javac -encoding UTF-8 ExplicitLineBreakDemo.java
java ExplicitLineBreakDemo
```

Stdout:

```text
lines=3
first=First
second=Second
third=Third
```

`split("\\R", -1)` splits on already-present line terminators; it does **not** lay out lines by width. Nor does it **preserve the line-break characters themselves** in the resulting array; if you need verbatim round-tripping, preserve the separators or keep the original text.

When using `LineBreakMeasurer`, the API documentation requires the iterator to represent **a single paragraph**. Therefore, split on hard breaks first, then lay out **each paragraph separately**. For consecutive blank lines, rendering should preserve blank lines per UI policy rather than letting a library silently drop them.

## 8. Why Can't Character Count Replace Width Measurement?

Common flawed approach:

```java
int columns = 20;
for (int i = 0; i < text.length(); i += columns) {
    String line = text.substring(
            i, Math.min(i + columns, text.length()));
    // Display line ...
}
```

This is an illustrative snippet inside a method, **not an appropriate UI wrapping algorithm** because:

1. `String.length()` counts UTF-16 code units, not glyph widths.
2. An emoji `U+1F600` takes two units; slicing mid-pair creates ill-formed UTF-16.
3. Letters with combining marks or ZWJ emojis can span multiple code points yet form one grapheme cluster.
4. Proportional fonts give `W` and `i` different widths; font fallback changes metrics.
5. Japanese, Chinese, and Thai do not obey "break every N characters".
6. Punctuation is not always allowed at the start or end of a line.
7. Bidirectional text has a visual display order different from code unit order.
8. Font size, letter spacing, kerning, zoom, and DPI affect actual layout.

A variant that "counts code points and slices" avoids the surrogate-pair bug, yet **still does not replace** font- and language-rule-based layout.

### When Is Slicing by Character Count Valid?

If a contract specifies a **monospace terminal** with character columns, you still need to consider East Asian width, combining marks, control characters, and emoji widths. Even "one code point per column" is not always true. For graphical display boxes, the right approach is text layout using pixel/user-space metrics.

## 9. Languages Without Spaces Between Words

### 9.1. Chinese and Japanese

Many Chinese/Japanese sentences have no spaces between words. An algorithm looking only for space characters treats the whole sentence as one token and either overflows width or splits arbitrarily.

A line-break iterator can yield boundaries based on Unicode line breaking, including allowed points between CJK characters. Yet there are also rules for brackets, punctuation, small kana, prolonged sound marks, or pairs that should not be separated. Use appropriate locale/provider data and test with real sentences.

For example, do not move a closing parenthesis or punctuation mark that belongs with the preceding word onto the start of the next line just to fill width.

### 9.2. Thai and Khmer

Text can consist of adjacent words with no spaces. Word/line boundaries sometimes require dictionary- or model-based segmentation. Java's `BreakIterator.getLineInstance(Locale)` is a high-level API, yet results depend on the runtime's language support. Do not assume every JDK segments Thai, Khmer, and Lao with equal effectiveness.

For products requiring high accuracy, compare results against native test data and consider ICU4J or an appropriate segmentation engine. Do not fall back to a space-only regex and accept whole sentences running off the screen.

### 9.3. Vietnamese: Spaces Are Not Necessarily Word Boundaries

Vietnamese usually has spaces between syllables. A multi-syllable word like `"công nghệ"` is written as two space-separated blocks. A visually valid line break does not mean linguistic "words" have been accurately analyzed for search or NLP. Thus `getLineInstance` and `getWordInstance` serve different purposes, and deeper word semantics require a separate processor.

## 10. Emojis, Combining Marks, and Grapheme Clusters

Unicode does not equate to "one code point is one visible character":

- `e\u0301` is `e` plus a combining acute accent, which can display as one grapheme.
- `😀` is a supplementary code point, represented by a **surrogate pair** in Java UTF-16.
- Emojis with skin-tone modifiers consist of multiple code points.
- Family emojis can use ZWJ `U+200D` to join multiple people/symbols into one grapheme cluster.
- Flag emojis can be pairs of regional indicators.

If a layout engine hits a "no word fits the width" fallback and splits by character, be careful: **do not slice between high and low surrogates** or inside a grapheme cluster. A modern text-layout engine normally handles shaping/clusters, yet the supported Unicode/emoji scope must be tested on the exact deployed runtime and fonts.

Java has `BreakIterator.getCharacterInstance(locale)` for character boundaries, and since Java 9 the regex `\X` means Unicode extended grapheme cluster within library capabilities. Still, the latest segmentation, ZWJ sequences, and font rendering behavior can vary by Unicode/JDK version.

**Tip:** If the UI truncates or ellipsizes a string at a specific width, prefer a real layout engine capable of handling grapheme clusters and overflow. Do not arbitrarily run `substring(0, 10)` to truncate person names or emojis.

## 11. Bidirectional Text and Glyph Layout

For Arabic, Hebrew, and mixed Latin/digit strings:

- **Logical order** is the character order in `String`.
- **Visual order** is the glyph order after applying the Unicode Bidirectional Algorithm and shaping.
- **Line break** splits a paragraph into display spans, which can affect per-line bidi processing.
- **Alignment** is a UI decision: left/right/start/end, which can vary with text direction.

`BreakIterator` provides only boundaries; it **does not perform full directionality and glyph drawing**. `TextLayout` / Java 2D handles glyph layout and complex text support at the rendering system level. When bidi control is needed, Java also provides `java.text.Bidi`.

Do not reverse a `String` with `reverse()` to produce RTL. That is not how Arabic is rendered; it can also corrupt surrogate pairs, combining marks, or semantic order. Use bidi-aware rendering, supporting fonts, and test strings mixing Arabic with numbers, punctuation, and URLs.

An RTL UI still must select line-break opportunities according to the language; text direction and breakability are **two distinct data dimensions**.

## 12. Swing, Java 2D, Web, and Server: Choosing the Responsible Layer

### 12.1. Swing Components

For `JTextArea`, Java provides:

```java
JTextArea area = new JTextArea(text);
area.setLineWrap(true);
area.setWrapStyleWord(true);
```

This is an illustrative snippet inside a UI method requiring `import javax.swing.JTextArea`. `setLineWrap(true)` enables wrapping when width is constrained; `setWrapStyleWord(true)` requests preferring word boundaries. Do not treat "word" here as an exact linguistic word analyzer for all languages and cases; still test with international text and the real UI.

Other Swing components like `JLabel` or `JTextPane` have different layout mechanisms; do not assume they all take the same two flags. For custom painting onto `Graphics2D`, `LineBreakMeasurer` is the directly relevant API.

### 12.2. Java 2D Custom Painting

For PDF previews, canvas drawing, custom editors, or printing with Java 2D, an application may have to manage paragraph breaks, font attributes, `LineBreakMeasurer`, `TextLayout`, margins, alignment, and painting itself. `BreakIterator` supplies allowed boundaries, while `LineBreakMeasurer` picks segments fitting the width.

### 12.3. Web Frontends and CSS

When a Java backend sends text to a browser, the browser already has a layout engine, font metrics, CSS, and actual width. Usually you should **not** have Java insert newlines into content merely to fit a guessed screen width. The browser can wrap according to Unicode/CSS and real dimensions.

CSS properties such as `white-space`, `overflow-wrap`, `word-break`, `line-break`, and `hyphens` affect wrapping, whitespace handling, segmentation, or hyphenation differently. Choose them deliberately by design and test each language rather than using `word-break: break-all` as a default blanket fix for all international content.

For special content like ultra-long URLs, inline code, or identifiers, a specific overflow policy may be needed to prevent breaking layout; that is a **display decision**, not a reason to alter the underlying data string.

### 12.4. Server Generating Fixed-Width Email / Plain Text

A `text/plain` email or terminal report may require a column limit. Check whether the contract specifies **monospace columns**, a byte limit, or actual visual width. Without knowing the recipient's exact font and viewport, a server struggles to produce line wrapping that looks right on every device. Prefer letting the client wrap on display unless a protocol standard requires hard wrapping.

### 12.5. PDF and Printing

Page size, margins, columns, fonts, rendering context, and page breaks make width more fixed than in responsive web UIs. In those cases server-side text layout can make sense, provided you use the exact fonts and sizes that will be drawn to the PDF/paper. When rendering PDF with a separate library, do not assume Java 2D measurements match another PDF library identically.

## 13. Line Breaks and Hard Breaks in Data Content

Do not conflate three behaviors:

| Behavior | Marker in Data | Depends on Width? | Example |
| --- | --- | --- | --- |
| Author inserts newline | `\n`, `\r\n`, or another separator | No | Manual line break |
| Renderer soft-wrap | Usually inserts no characters into the string | Yes | Narrow textbox |
| Layout engine breaks at allowed points | Based on linguistically allowed boundaries | Indirectly when renderer picks a point | Breaking at a space |

If an application saves soft breaks as hard newlines in the database, copy/paste can carry extra newlines, search/comparison can break, and text will not reflow when resized. Separate the **data model** from the **layout model**.

When hard breaks genuinely need to be saved, preserve the user's explicit choices. If normalizing line endings to `\n`, treat that as a contractual transformation step separate from soft wrapping.

### Boundaries Belong to UTF-16 Indexes

`BreakIterator` returns offsets for use with `String.substring` and `java.text.CharacterIterator`; in Java, these are **UTF-16 code unit positions**. This differs from code point counts and width. If using `String.codePoints()`, convert indexes properly; do not treat `BreakIterator` offsets as the n-th index of a code point `IntStream`.

## 14. Difference Between "Allowed" and "Should"

An English example has break opportunities between words:

```text
Paragraph: "A quick brown fox jumps over the lazy dog."

Candidates: many positions between words and at the end of the paragraph

Very wide region:
"A quick brown fox jumps over the lazy dog."

Narrow region:
"A quick brown"
"fox jumps over"
"the lazy dog."
```

This is a **conceptual illustration**, not the exact output of `LineBreakMeasurer` for a specific font and width. An actual engine may break lines differently depending on font, font size, and measurement.

A renderer typically tries to fit as many words as possible on one line. Yet a publishing typesetting algorithm might pick different breaks to balance line lengths, avoid widows/orphans, or handle hyphenation and justification. `BreakIterator` does not decide those typographic aesthetics; `LineBreakMeasurer` provides a standard policy for text layout, not a universal typography engine.

## 15. Customization and Limits of `LineBreakMeasurer`

### 15.1. `nextLayout` and `nextOffset`

- `nextLayout(width)`: returns the next `TextLayout` and **advances `position`**.
- `nextOffset(width)`: estimates the ending offset of the next layout **without updating `position`**.
- `setPosition(index)`: sets the next starting point within the iterator's range.
- `nextLayout(width, offsetLimit, requireNextWord)`: supplies an offset limit and a policy requiring a whole word when appending text to an existing line.
- `insertChar` / `deleteChar`: updates for a single text edit with a new iterator; not an automatic mutation of internal text inside the measurer.

Per the documentation, `nextLayout(width, limit, true)` can return `null` when the entire next word does not fit the remaining width; handle `null` rather than reading `getPosition()` and looping forever.

### 15.2. Tabs and Custom Line Policies

`LineBreakMeasurer` treats tabs under its own policy, and an application with tab stops may need to bound the offset per segment. Do not assume `\t` always equals 4 spaces or the same width across all fonts/renderers. If a UI supports rich text and tabs, design tab handling explicitly.

### 15.3. When Width Is Zero or Negative

A drawing region with no usable width must be handled at the layout layer before invoking the measurer. Avoid loops that fail to advance `position` or pass invalid values. You can check `width > 0`, lay out empty paragraphs per UI policy, and show a placeholder/scrollbar when the region is too small.

### 15.4. Rich Text: Multiple Fonts on the Same Line

`AttributedString` can contain spans with different fonts. When fonts, font sizes, and glyph metrics vary within one paragraph, width is no longer a simple function of character count. `TextLayout` needs accurate attributes, and line breaks can shift if a user bolds a word.

### 15.5. Not Every System Has `java.desktop`

`BreakIterator` belongs to the `java.base` module. `LineBreakMeasurer`, `TextLayout`, and `FontRenderContext` belong to `java.desktop`. If an application runs on a `jlink` custom runtime containing only selected modules, the Java 2D portion may be absent. Determine whether text layout is needed on the server or client; do not pull in graphics modules if the backend only needs text-boundary semantics.

## 16. Performance, Caching, and Thread Safety

Both boundary analysis and glyph layout have a cost. For large UIs or rapidly changing text, base optimizations on profiling:

- `BreakIterator` holds mutable position and analyzed text state. Do not share one instance and call `setText` across concurrent requests.
- `LineBreakMeasurer` is a stateful iterator/layout helper for **one paragraph**; do not use a single instance concurrently across multiple paragraphs or change text without refreshing or using supported update APIs.
- `FontRenderContext` and font attributes must match rendering; cache layouts by width when width/font/text/locale are unchanged, and invalidate on changes.
- When text/locale/provider differ, boundaries can change; do not use a cache key based solely on the text string.
- Do not hardcode one pre-wrapped newline array for both mobile and desktop.
- Do not benchmark with a single un-warmed call; for heavy workloads use JMH or real UI profiling.

Calling zero-arg `BreakIterator.getLineInstance()` uses the environment's default locale. In multi-user apps, pass the chosen locale explicitly; do **not** call `Locale.setDefault` per HTTP request because the default is shared JVM state.

## 17. Common Pitfalls

| Misconception | Correct Understanding |
| --- | --- |
| "`BreakIterator.getLineInstance` automatically splits a paragraph into 200-px lines." | It returns only break opportunities; it takes no width |
| "Every returned boundary is one line." | One line can span many segments between boundaries |
| "20 `char`s always fit 20 columns." | `char` is a UTF-16 code unit, not glyph width |
| "`String.split(" ")` wraps lines correctly for all languages." | Many scripts have no spaces between words; punctuation/Unicode have rules |
| "Word boundaries always equal line boundaries." | The two segmentations serve different purposes |
| "Newlines in the model and UI soft wraps are the same." | Hard breaks live in data; soft wraps depend on layout |
| "Breaking inside a surrogate pair is fine if no exception occurs." | It can produce ill-formed UTF-16 |
| "One code point is one visible character." | A grapheme cluster can contain multiple code points |
| "Picking a `Locale` is enough to know character width." | Width requires font, size, shaping, and render context |
| "Using English layout for Thai will always work." | Appropriate segmentation/locale/data is needed |
| "RTL glyphs only need `String.reverse()`." | Bidi-aware shaping and rendering are required |
| "Backend wrapping makes sense for responsive web." | Usually the browser/layout engine should decide using actual width |
| "`LineBreakMeasurer` never splits a word." | It can split when the first word exceeds the width |
| "`LineBreakMeasurer` handles all hard paragraph breaks itself." | Split paragraphs and lay out each segment per contract |
| "Changing fonts does not affect line breaks." | Glyph metrics change, so break points can shift |
| "Whenever a valid break opportunity exists, the UI must break." | Actual breaking also depends on width and layout |

## 18. Practical Testing

### 18.1. Linguistic Boundary Layer

- Run `BreakIterator.getLineInstance` with `en-US`, `vi-VN`, `ja-JP`, `zh-CN`, and `th-TH` on native data.
- Verify offsets strictly increase, stay within UTF-16 bounds, and reach the end of the text cleanly.
- Test punctuation clusters, non-breaking spaces, zero-width spaces, hyphens, and spaceless strings.
- Verify surrogate pairs, combining marks, and ZWJ emojis are not split contrary to committed runtime rules/capabilities.
- Pin the runtime/provider or allow for boundary variations when Unicode/locale data updates.
- When dictionary-based segmentation is needed, test with a real corpus; do not extrapolate from one English sentence.

### 18.2. Layout Layer

- With **the same text/locale/font**, measure line counts across different widths.
- Change font, font size, rich text, or DPI/scale and verify re-wrapping.
- Test long labels, URLs, emojis, very long words, spaces, and NBSP.
- Ensure layout never advances past the paragraph or enters an infinite loop when the region is too narrow.
- If truncating/ellipsizing, verify graphemes are not torn or important content hidden unexpectedly.
- Test LTR/RTL and mixed letters with digits/punctuation.
- Verify height, baseline, ascent/descent, and clipping; a line that fits width can still clip if height is insufficient.

### 18.3. Data Layer

- Soft-wrapped text can reflow on resize **without altering the original text**.
- Hard breaks are preserved as required; CRLF does not turn into two accidental blank lines.
- Copy/paste does not include soft-wrap newlines if the design wraps only at render time.
- APIs/DB store canonical text; UI layout does not inject unintended fragments into data.
- Account for client browser and backend having different font/rendering engines: do not expect identical exact line counts.

### 18.4. Accessibility and Multilingual Layer

- For screen readers, reading order follows logical text, unaffected by visual reordering.
- Do not insert forced newlines that break the meaning of a long sentence.
- Test translations longer than English so the UI scales properly.
- When users enlarge text size, wrapping adjusts while keeping information unclipped.
- Test mixed languages within the same paragraph and paragraph direction.

## 19. Self-Practice Exercises and Answers

**Exercise 1.** `BreakIterator.getLineInstance(Locale.US)` receives text and returns multiple boundaries. Is that the number of lines displayed in a 250-px-wide textbox?

**Answer:** No. It provides only candidate break positions. Line count requires width, font, shaping, and a layout engine.

**Exercise 2.** For the same text, when width increases from 160 to 480 units, does the set of candidate boundaries necessarily change?

**Answer:** No. If text/locale/segmentation algorithm stay unchanged, boundary opportunities do not depend on width. Only the points **chosen** for wrapping can change.

**Exercise 3.** Why isn't `text.substring(i, i + 20)` a good wrapping strategy?

**Answer:** Because counting UTF-16 units is not glyph width; it also risks splitting surrogate pairs, grapheme clusters, punctuation, or words that should not be broken.

**Exercise 4.** To lay out a paragraph in Java 2D for a specific width, what should you use?

**Answer:** Use `AttributedCharacterIterator` with font attributes, `FontRenderContext`, `LineBreakMeasurer`, and `TextLayout`; you can pass `BreakIterator.getLineInstance(locale)`.

**Exercise 5.** Suppose a string contains `\r\n`. Should `BreakIterator` and wrapping treat it the same as a UI soft break?

**Answer:** No. `\r\n` is a hard break in the data. Split and preserve paragraph/line semantics before soft-wrapping each part.

**Exercise 6.** A Thai text has no spaces, and `split(" ")` produces one very long string. Should you insert a newline every 10 characters?

**Answer:** No. You need language-aware segmentation and actual layout; forcing by character count can tear character clusters and ignores width.

**Exercise 7.** Why might `LineBreakMeasurer` have to split a word even when given a `BreakIterator`?

**Answer:** When the word at the start of a line does not fit within the requested width; layout policy normally must produce a segment to ensure forward progress. Long tokens, overflow, and application semantics must be handled.

**Exercise 8.** A Java backend generates text for rendering in a mobile browser. Should it insert newlines based on an assumed desktop width or let the client wrap?

**Answer:** Usually let the browser use actual width/fonts and appropriate CSS. The backend preserves text and meaningful hard breaks without storing soft wraps.

**Exercise 9.** `BreakIterator` returns UTF-16 indexes, while the UI needs to slice by grapheme cluster. Can you take any returned index and slice anywhere?

**Answer:** No. Check whether that boundary matches grapheme requirements and runtime behavior; do not cut inside a surrogate pair or user character cluster.

**Exercise 10.** If you change the font or increase font size, do you need to recompute `LineBreakMeasurer`?

**Answer:** Yes, because glyph metrics changed. The set of linguistic break points may remain similar, yet the line count and chosen wrap positions can differ.

## 20. Key Takeaways

- **Language-aware line breaking** answers **"where is breaking allowed?"**; **width-based layout** answers **"where should we break so the line fits?"**.
- `BreakIterator.getLineInstance(locale)` provides candidate boundaries and **takes no width**. Do not treat segments between boundaries as UI lines.
- `LineBreakMeasurer` combines paragraph text, font/render context, and wrapping width to build a `TextLayout` per line. A locale-specific `BreakIterator` can be passed in.
- Existing newlines are **hard breaks**; wrapping caused by a narrow region is a **soft wrap** and should not mutate canonical text.
- `String.length()`, code point counts, and grapheme cluster counts are **not** glyph width. Avoid slicing text by `char` count to simulate wrapping.
- CJK, Thai/Khmer, punctuation, NBSP/ZWSP, emojis, and RTL require testing appropriate to the language and rendering engine.
- For responsive frontends, usually let the UI engine lay out text using actual width; for Java 2D/PDF/printing, measure with the exact font, width, and metrics.
- **Do not collapse text boundaries, language rules, Unicode encoding, and UI width into a single calculation.** Pick the tool matching the exact question.

### Java 17 and Unicode References

- [BreakIterator — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html)
- [LineBreakMeasurer — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/font/LineBreakMeasurer.html)
- [TextLayout — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/font/TextLayout.html)
- [FontRenderContext — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/font/FontRenderContext.html)
- [Pattern — Java regex `\R` and `\X`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
- [Unicode Line Breaking Algorithm — UAX #14](https://www.unicode.org/reports/tr14/)
