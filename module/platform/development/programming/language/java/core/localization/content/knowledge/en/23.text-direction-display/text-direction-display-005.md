# Boundaries of Bidi Handling When the UI Already Has a Text Layout Engine in Java

## 1. Framing the problem: who is responsible for text direction?

A Java application may display a Vietnamese sentence containing an Arabic personal name, or a Hebrew interface containing phone numbers, order codes, and URLs in Latin script. **Left-to-right** (LTR) and **right-to-left** (RTL) segments coexist in **a single logical string**. When placing that string on screen, the visible character order may differ from the code point order in memory.

Unicode defines the **Bidirectional Algorithm (UBA)** to determine how directionally mixed text segments are ordered for display. In core Java, the `java.text.Bidi` class can **analyze direction**, embedding levels, and runs of a text paragraph. However, a modern UI typically already has a **text layout engine** that performs Bidi, line segmentation, shaping, glyph selection, positioning, and caret management.

Therefore, the problem is not "whenever you see Arabic, call `Bidi` and reverse the `String`." The better question is:

> **When the UI already owns the text layout step, what data and context should the Java application supply, and what work should it avoid redoing?**

**Core idea:** keep strings in **logical order**, select **paragraph direction / isolation context** at the appropriate layer, delegate computing **visual order** to a full-featured text renderer; only use `java.text.Bidi` directly when you genuinely must analyze direction yourself or build a specialized text-rendering component.

### Lesson objectives

After this lesson, you can:

1. Distinguish **logical order**, **visual order**, **base paragraph direction**, **embedding level**, and **directional run**.
2. Know what information `java.text.Bidi` returns, and what it **does not** return.
3. Explain why you must not reverse a `String` or reorder it yourself before passing it to a Bidi-capable UI engine.
4. Identify the distinct roles of Unicode Bidi, Arabic shaping, font layout, line breaking, and text editing.
5. Apply direction and isolation properly to standalone elements such as names, emails, numbers, order codes, or URLs inside an RTL line.
6. Design sensible handling for Swing/Java2D, JavaFX, Android, or web UIs when a layout engine already exists.
7. Test mixed text and stay alert to directional control characters that can misrepresent data, logs, or source code.

## 2. Logical order and visual order are not the same

**Logical order** is the order of characters/code points in `String` data, files, APIs, or databases. This order carries structural meaning, enabling searching, parsing, and data serialization.

**Visual order** is the order of glyphs displayed on a line after applying the Bidi algorithm, shaping, and layout. A renderer can display an RTL segment in the opposite direction from an adjacent Latin segment **without modifying the contents of the `String`**.

Suppose the data is:

```text
Logical string: "ABC " + [Alef][Bet][Gimel]
Unicode:        U+0041 U+0042 U+0043 U+0020 U+05D0 U+05D1 U+05D2
```

The code point sequence remains in that order in memory. Yet for readers to see the Hebrew segment in the right order, the UI must resolve direction and position glyphs accordingly.

**You should not store the "as seen on screen" order as a reversed string.** If you transform logical data yourself to mimic visual order, copy/paste, searching, text selection, screen-reader output, line wrapping, and display elsewhere can all break.

### One string, many ways to wrap lines

The UBA resolves direction and reordering per paragraph/line according to context. When UI width changes, runs may split differently, and punctuation/digit segments may shift relative positions. Hence **there is no single "pre-reversed string suitable for rendering at every width"** that fits every layout.

A renderer can produce different visual lines from the same logical string when:

- The window narrows or widens.
- The font or font size changes.
- Content wraps at a different spot.
- The paragraph's base direction changes.
- A segment is placed in a container with different directional isolation.

Any "preprocessing" that reverses code point order before UI rendering risks **double reordering** or corrupting meaning.

## 3. UBA, shaping, and layout are different stages

| Task | Question solved | Typical output |
| --- | --- | --- |
| **Bidi analysis** | What directional levels do characters/runs have in the paragraph? | Embedding levels, directional runs, visual-order constraints. |
| **Script shaping** | Which glyphs do code points produce per script/context? | Connected Arabic forms, ligatures, diacritic placement. |
| **Font fallback** | Which font contains the needed glyphs? | Font selection by script/glyph coverage. |
| **Line breaking** | How is text split into lines? | Wrap points based on width, line/language rules. |
| **Glyph positioning** | At what coordinates are glyphs placed, with what advance? | On-line layout and drawing metrics. |
| **Hit-testing/caret** | Which logical offset does a click at this pixel point to? | Caret position, selection, keyboard navigation. |
| **Accessibility** | In what content order should text be read? | Logical text, semantic roles, proper reading order. |

`java.text.Bidi` **does not** replace the entire table above. It supplies directional data, not a complete text widget. It does not select an appropriate font, shape Arabic letters, handle pointer hit-testing, or draw glyphs on a device.

A UI framework with a layout engine usually **integrates** several of the components above. If an app runs Bidi itself, reverses the string, and then passes it to that framework, you duplicate a step the framework already owns—and likely get it wrong.

### Arabic script example

Arabic letters change shape and connect depending on context. **Reversing character codes does not create proper letter joining.** Shaping is a separate responsibility from computing Bidi run order. If an app only has `Bidi`, it still needs fonts and a shaping engine to draw Arabic completely.

Similarly, combining marks attach to base glyphs, emojis can consist of multiple code points forming a cluster, and caret movement must avoid splitting grapheme clusters. A `StringBuilder.reverse()` call is not an engine solving those problems; even though Java handles surrogate pairs in certain reverse operations, that does not turn string reversal into the Bidi algorithm or grapheme layout.

## 4. What can Java's java.text.Bidi do?

The `java.text.Bidi` class analyzes the bidirectional structure of a text paragraph. One way to create an instance:

```java
String mixed = "ABC \u05D0\u05D1\u05D2";
Bidi analysis = new Bidi(
        mixed,
        Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);
```

This code belongs inside a Java method with `import java.text.Bidi;`.

APIs worth knowing:

| API | Meaning |
| --- | --- |
| `Bidi(String paragraph, int flags)` | Analyze a paragraph with a chosen/inferred base direction. |
| `DIRECTION_LEFT_TO_RIGHT` | Choose an explicit LTR base direction. |
| `DIRECTION_RIGHT_TO_LEFT` | Choose an explicit RTL base direction. |
| `DIRECTION_DEFAULT_LEFT_TO_RIGHT` | Base on the first strong character; default to LTR if undetermined. |
| `DIRECTION_DEFAULT_RIGHT_TO_LEFT` | Base on the first strong character; fall back to RTL when needed. |
| `getBaseLevel()` | Base embedding level (even is LTR, odd is RTL). |
| `isMixed()` | Whether the paragraph has mixed directions per analysis. |
| `isLeftToRight()` / `isRightToLeft()` | Paragraph directionality characteristics from the analysis result. |
| `getRunCount()` | Number of analyzed directional runs. |
| `getRunStart(i)` / `getRunLimit(i)` | Logical start/end offset interval of the run. |
| `getRunLevel(i)` | Embedding level of the run. |
| `getLevelAt(offset)` | Level at the corresponding character position. |
| `Bidi.requiresBidi(char[], start, limit)` | Convenience check for whether a char sequence needs bidirectional processing. |
| `Bidi.reorderVisually(...)` | Helps reorder **objects/runs** by level, not render an entire `String` into display text. |
| `createLineBidi(start, limit)` | Create Bidi analysis for a line slice based on an already-analyzed paragraph. |

**Be sure to distinguish:** `getRunStart`/`getRunLimit` offsets are positions in a UTF-16 string, with `limit` as an **exclusive** endpoint. Do not confuse them with code point indices, UTF-8 byte counts, or pixels.

### Why is Bidi alone not enough to render?

Suppose there are two runs, one LTR and one RTL. `Bidi` tells you the direction of those runs, yet actual display still needs:

- Knowing how wide each glyph is and where to place it.
- Computing shaping and glyph order within the respective scripts.
- Wrapping lines according to container dimensions.
- Rules for neutral characters such as spaces, punctuation, and parentheses.
- Mapping pixels back to logical positions for copy/selection/caret.
- Adjusting levels when content is embedded in another paragraph.

Therefore, reading `getRunCount()` and concatenating `substring(...)` in reverse order is **not** how you build a full-featured text renderer.

## 5. Standalone Java 17+ example: analyzing direction without redrawing

Create the file **`BidiLayoutBoundaryDemo.java`**:

```java
import java.text.Bidi;

public class BidiLayoutBoundaryDemo {

    public static void main(String[] args) {
        String mixed = "ABC \u05D0\u05D1\u05D2";

        Bidi analysis = new Bidi(
                mixed, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

        System.out.println("utf16Length=" + mixed.length());
        System.out.println("baseLevel=" + analysis.getBaseLevel());
        System.out.println("isMixed=" + analysis.isMixed());
        System.out.println("runCount=" + analysis.getRunCount());

        for (int index = 0;
             index < analysis.getRunCount();
             index++) {
            System.out.println(
                    "run[" + index + "]="
                    + analysis.getRunStart(index)
                    + ".." + analysis.getRunLimit(index)
                    + " level=" + analysis.getRunLevel(index));
        }

        System.out.println("requiresMixed="
                + Bidi.requiresBidi(
                        mixed.toCharArray(), 0, mixed.length()));

        String latin = "ABC 123";
        System.out.println("requiresAscii="
                + Bidi.requiresBidi(
                        latin.toCharArray(), 0, latin.length()));

        Bidi hebrew = new Bidi(
                "\u05D0\u05D1\u05D2",
                Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);
        System.out.println("hebrewBaseLevel="
                + hebrew.getBaseLevel());

        System.out.println("sourceUnchanged="
                + mixed.equals("ABC \u05D0\u05D1\u05D2"));
    }
}
```

Compile and run from the directory containing the file with JDK 17 or newer:

```bash
javac -encoding UTF-8 BidiLayoutBoundaryDemo.java
java BidiLayoutBoundaryDemo
```

**Stdout verified with Java 17:**

```text
utf16Length=7
baseLevel=0
isMixed=true
runCount=2
run[0]=0..4 level=0
run[1]=4..7 level=1
requiresMixed=true
requiresAscii=false
hebrewBaseLevel=1
sourceUnchanged=true
```

### Explaining the output

1. `utf16Length=7`: `ABC` has 3 UTF-16 code units, space has 1, three Hebrew letters have 1 each; 7 total.
2. `baseLevel=0` because the first strong character is Latin LTR.
3. `isMixed=true` and `runCount=2`: the paragraph contains both LTR and RTL runs.
4. `run[0]=0..4 level=0` covers the Latin part plus the space; `run[1]=4..7 level=1` covers the Hebrew part.
5. `requiresMixed=true` for the string with RTL letters; `requiresAscii=false` for the pure Latin/digits string in the example.
6. `hebrewBaseLevel=1`: when only Hebrew letters are present, the first strong character is RTL so the base level is set accordingly.
7. `sourceUnchanged=true`: analysis neither reverses nor modifies the `String` contents.

This is a program that **reads and prints analysis data**, not code for drawing text. Printing the Hebrew string directly in a terminal makes the visible order depend on the terminal/font/console; thus the example prints **offsets and levels in ASCII** to avoid confusing algorithm output with the environment's rendering capability.

## 6. Key limitations of Bidi.requiresBidi

`Bidi.requiresBidi(...)` is an API for quickly detecting whether a `char[]` range needs Bidi. It is useful when deciding whether to take a specialized analysis branch in **a self-managed text pipeline**. However, you should not use it to drive your entire UI policy.

What it **does not** solve:

- **Does not determine the user's locale** or the primary language of a paragraph.
- **Does not tell you exactly how to draw a line**; layout, shaping, and line breaking are still needed.
- **Does not substitute for a container's direction attribute**.
- **Does not verify the safety of Unicode bidi controls** in user text.
- **Does not guarantee it is only needed when Hebrew/Arabic characters exist**; digits, neutral characters, punctuation, and paragraph context can all affect visual placement.
- **Does not let the app bypass the layout engine** just because the method returns `false`; even text with no RTL mix still requires fonts, caret handling, and line wrapping.

If a widget already has text layout and decides for itself whether to run Bidi, the application usually **does not need to call `requiresBidi` before rendering**. Repeating that step can add complexity without benefit.

## 7. When the UI already has a text layout engine: separation of responsibilities

Depending on the platform, API names vary, yet the principles are largely the same.

| Layer | Responsibility it should own |
| --- | --- |
| **Domain / model** | Store logical strings, IDs, data order; never alter to "look right." |
| **Localization** | Choose translations, placeholder order, locale, grammatically correct RTL/LTR messages. |
| **UI component / container** | Set base direction, layout direction, or `dir` by context; isolate standalone inserts where appropriate. |
| **Text layout engine** | Run Bidi, shaping, line wrapping, glyph positioning, caret, selection. |
| **Accessibility** | Use logical/semantic text; never pass "reversed-for-display" strings to screen readers. |
| **Validation / security** | Inspect Unicode controls in data, format logs clearly, guard against spoofing and misleading display. |

When a UI component handles **Bidi + shaping**, the application must not feed it a handcrafted "visual order string." Supply the **logical string** and **directional context**.

### What if a UI only accepts strings and has no explicit direction method?

If a rendering API genuinely lacks Bidi support, the solution is not to reverse the `String` by default. You may need to:

- Switch to a component/text engine that supports Bidi.
- Use rich text or framework-provided paragraph direction attributes.
- Build a custom renderer based on `TextLayout`/font shaping alongside the proper Bidi algorithm, **only when you genuinely must own the pipeline**.
- Test Arabic shaping, mixed text, selection, and line breaking in the target environment.

**Do not mix the two strategies**: manually reordering the string while also asking the engine to reorder it again.

## 8. Swing, Java2D, JavaFX, Android, and web: where to configure it

### 8.1. Swing/Java2D

Swing text components and Java2D have text-handling mechanisms and can provide support for direction, fonts, and run layout. When using them:

- Prefer directional APIs/`ComponentOrientation` or the appropriate text components rather than reversing data.
- For rich text, check which paragraph/style attributes the component supports.
- When drawing text directly, `java.awt.font.TextLayout` can participate in complex layout; **`java.text.Bidi` alone cannot draw glyphs**.
- Use coordinates/hit-tests produced by text layout for caret and selection rather than computing pixel positions from `String.length()`.

No single Swing property guarantees every custom component or hand-drawn canvas handles every script flawlessly. Test with the exact controls, fonts, and target JDK.

### 8.2. JavaFX

With JavaFX controls, use **layout nodes and text controls** for display. Check the node/paragraph direction mechanisms supported by your target JavaFX version. Never construct a character-reversed `String` before passing it into `Text`, `TextFlow`, or layout-enabled controls.

`TextFlow` and rich text can also place segments across multiple nodes, each with different fonts/styles; ensure continuity of the Bidi context and inspect results at node boundaries. When bugs appear, identify precisely which component performs layout instead of randomly inserting direction-flipping characters.

### 8.3. Android

Android `TextView` and corresponding text components typically include bidi/layout; `textDirection`, `layoutDirection`, and contextual directional-formatting APIs each play distinct roles. For an isolated fragment such as an email address or product code inside an RTL sentence, Android/AndroidX bidi-formatting utilities can be used when suitable for the target API.

Do not run `java.text.Bidi` yourself and reverse the string before assigning it to a `TextView`. That can break caret/selection, punctuation, and copy/paste. Also distinguish **container layout direction** (placement of icons, buttons) from **text direction** (how characters are analyzed).

### 8.4. Web/HTML

If Java produces content for the web, **the browser** owns Bidi text layout. HTML provides the `dir` attribute and the `bdi` element to manage the direction of standalone content.

Example:

```html
<p dir="rtl">
  <span>متن</span>
  <bdi dir="auto">user-123@example.com</bdi>
</p>
```

Here `dir="rtl"` sets the paragraph's contextual direction; `bdi dir="auto"` isolates the value's direction as an independent element. The browser computes visual order; Java does not have to reverse the email address before emitting HTML.

**Note:** rendering dynamic text in HTML must properly escape/encode to prevent XSS; `bdi` and `dir` are not anti-injection measures, and you must not concatenate raw user text into HTML strings. Use a template engine or DOM API with safe escaping rules. If you do not control the markup, establish a clear policy separating data from structure.

### Do not equate container direction with data direction

In an RTL UI, elements like navigation buttons, "back" icons, menu order, or flex regions may need layout following container direction. Yet a URL, email address, account number, or SKU code may need to remain grouped and receive independent directional handling. **Flipping container layout** does not mean **reversing the code points of every `String`**.

## 9. Embedding, isolates, and inserting LTR data into RTL sentences

### 9.1. Common problem

Suppose an RTL translation has a placeholder to insert an `orderId` in Latin letters/digits. If you concatenate raw text without an isolation context, punctuation, parentheses, hyphens, or neutral characters next to the value can be pulled by the surrounding RTL segment.

A sound approach is usually to **isolate the direction of the standalone segment** at the UI or formatting layer, without reversing `orderId`. Design guidelines:

1. Keep `orderId` in accurate logical order so it can be copied and compared.
2. Ensure the main paragraph has a base direction suited to the translation.
3. Place `orderId` inside a bidi-isolated region when the UI supports it, such as `bdi` on the web.
4. Test preceding/trailing punctuation, negative signs, parentheses, periods, and separators.
5. Do not inject Unicode control characters if the widget already applies rich-text isolation; avoid double handling.

### 9.2. Unicode bidi controls

Unicode defines directional control characters, such as:

| Code point | Name | General purpose |
| --- | --- | --- |
| `U+200E` | LEFT-TO-RIGHT MARK (LRM) | Mark assisting an LTR context. |
| `U+200F` | RIGHT-TO-LEFT MARK (RLM) | Mark assisting an RTL context. |
| `U+202A` | LEFT-TO-RIGHT EMBEDDING (LRE) | Start legacy LTR embedding. |
| `U+202B` | RIGHT-TO-LEFT EMBEDDING (RLE) | Start legacy RTL embedding. |
| `U+202D` | LEFT-TO-RIGHT OVERRIDE (LRO) | Force direction on some text; prone to abuse. |
| `U+202E` | RIGHT-TO-LEFT OVERRIDE (RLO) | Force direction; carries visual spoofing risk. |
| `U+202C` | POP DIRECTIONAL FORMATTING (PDF) | End the corresponding embedding/override. |
| `U+2066` | LEFT-TO-RIGHT ISOLATE (LRI) | Isolate an LTR segment. |
| `U+2067` | RIGHT-TO-LEFT ISOLATE (RLI) | Isolate an RTL segment. |
| `U+2068` | FIRST STRONG ISOLATE (FSI) | Choose isolate direction from the first strong character. |
| `U+2069` | POP DIRECTIONAL ISOLATE (PDI) | End the corresponding isolate. |

Modern Unicode isolates separate the directional influence of an inserted segment from surrounding text better than many legacy embedding cases. However, **they are real data characters** that can be stored, copied/pasted, logged, or sent over APIs; they are not UI markup.

**Prefer renderer-level isolation mechanisms** when available: `bdi` on the web, a framework's official bidi formatter, or text spans/paragraph attributes. Add LRI/RLI/FSI/PDI to plain text only when the transmitted text format genuinely requires it and you have verified the receiving platform's behavior. Ensure isolates are properly closed with PDI and avoid creating uncontrolled nested layers of controls.

### 9.3. Why not use overrides as a "quick fix"?

`LRO/RLO` aggressively override directional display. Using them to "force" a mixed snippet to look right in one place can break it elsewhere and cause content to display out of logical order. For external data, they also carry security risks. Do not use Unicode override controls as a default UI solution for RTL.

## 10. Security warning: visual strings can deceive readers

Bidirectional formatting has legitimate uses, yet certain control characters can make the visible order **differ substantially** from logical order. This is especially sensitive for:

- Filenames or file extensions.
- Security system logs.
- Source code strings and code comments.
- Usernames, document names, order codes.
- Warnings or transaction summaries requiring exact confirmation.

**Trojan Source** style attacks exploit bidi controls so humans read code in a different visual order than the compiler processes it. An interface rendering Unicode properly does not automatically guarantee content is non-misleading.

### Safe handling principles

- **Do not ban all RTL characters**: Hebrew/Arabic and bidi formatting have valid needs.
- Have a policy for directional control characters in sensitive fields; distinguish free-form prose from identifiers with narrow grammars.
- For a field allowing only ASCII IDs, **validate the ASCII grammar** instead of trying to use `Bidi` to cope with anomalous input.
- When audits/logs must reveal control characters, add a **diagnostic representation** (code point names/hex or escapes), while preserving original data if storage policy requires.
- For filenames, transaction codes, or addresses, prevent visual presentation from deceiving critical confirmation steps.
- If input goes into HTML or a terminal, also handle context-appropriate escaping, control characters, and injection defense; `Bidi` does not replace those protections.
- Test screen readers and copy/paste behavior: logical data and displayed text must let users verify what they are actually submitting/saving.

**Bidi is a display feature, not an operation that alters business values.** Validation and security layers need to recognize bidi controls, but should not silently "pretty-fix" data by reversing strings or stripping all RTL scripts.

## 11. Bidi and Unicode normalization are two different problems

Unicode **normalization** (NFC, NFD, ...) handles canonically or compatibility equivalent code point representations. It **does not determine visual order**, and does not convert a Hebrew/Arabic segment into Latin.

Similarly:

- `toLowerCase(Locale.ROOT)` is case conversion, not bidi layout.
- `Collator` is locale-aware collation/sorting, not Bidi.
- `BreakIterator` deals with text segmentation, not a complete Bidi renderer.
- UTF-8/UTF-16 are encodings, carrying no meaning of "draw right-to-left."
- `Bidi` does not alter URL/JSON parsing or the parameter order of a translated sentence.

When encountering display errors, classify the bug first:

| Symptom | Possible source of the issue |
| --- | --- |
| Arabic letters fail to join properly | Shaping/font/rendering, not just Bidi order. |
| Parentheses/digits sit unexpectedly at line end | Base direction, isolation, or neutral-character handling. |
| Text turns into `Ã...` | Decode/charset mismatch, not Bidi. |
| Same-looking text has different code point sequences | Normalization, combining marks. |
| Cannot select the intended text range on click | Hit-testing/caret logic in the layout engine. |
| Copied string has a different order from what is drawn | Logical order vs. visual order difference; inspect the copy pipeline. |
| Entire UI navigation buttons are flipped | Container/layout direction, not necessarily text Bidi. |
| Icon or punctuation attaches to the wrong SKU | Token direction, isolation, and adjacent context. |

The right fix depends on the layer causing the problem—not calling `Bidi` and reversing characters on every text bug.

## 12. Application design: logical strings, locale, direction, and layout

A clean design for mixed text can include:

1. **Model:** store logical strings and identifier variables per schema.
2. **ResourceBundle/translator:** select messages, preserving parameter order and natural phrasing for the language.
3. **UI adapter:** receive locale, paragraph direction or layout direction, and necessary isolation boundaries.
4. **Text layout engine:** handle bidi, shaping, line breaks, glyph placement, caret, and selection.
5. **Input handling:** return logical strings and required metadata, never taking visual reordering as the stored value.
6. **Security/validation:** check identifiers, sensitive control chars, and display/logging/audit policies.
7. **QA:** test RTL/LTR combinations, digits, punctuation, and rich text.

### "Right role" example when inserting an ID into a translation

Suppose `orderId` is `AB-1234/56` and the app has an RTL translation:

- The translated message keeps a placeholder for the ID.
- The ID is stored as `AB-1234/56`, not reversed to `65/4321-BA`.
- The UI treats the ID slice as standalone content and applies isolation when needed.
- The renderer decides glyph order and caret behavior; the app does not stitch visual runs into a replacement string.
- When the user copies the ID, the clipboard receives `AB-1234/56` in logical order.
- When the backend processes it, validation checks the ID against its grammar rather than screenshots or visual order.

A test should verify **the exact value copied and submitted**, not only whether it "looks reasonable" at one screen size.

## 13. Common mistakes and how to avoid them

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Calling `StringBuilder.reverse()` whenever RTL appears | Reversing code units/graphemes is not Unicode Bidi; can corrupt logical data order. | Keep `String`, hand layout to the renderer. |
| Reordering runs yourself and passing them to a Bidi-capable UI | Can cause double reordering, broken punctuation and wrapping. | Pick one layer to own layout. |
| Using `Bidi` to "draw text" | `Bidi` only analyzes direction, not shaping/glyph placement. | Use a text layout/shaping engine. |
| Converting Strings to visual order before saving to DB | Search, copy, serialization, and accessibility break. | Store logical order. |
| Assuming `Locale` determines all base direction | Language locale, text direction, and UI layout are separate contexts. | Set paragraph/container direction explicitly. |
| Using container direction to reverse every value | URLs, emails, and IDs may need independent handling. | Isolate standalone tokens within the line. |
| Inserting LRO/RLO indiscriminately | Applies strong override, risking confusion/display hijacking. | Use appropriate isolation APIs. |
| Believing `Bidi.requiresBidi` is mandatory for every `TextView` | Text components typically already analyze and lay out text. | Avoid redundant algorithm passes when unneeded. |
| Computing caret position from visual index | Visual order does not match UTF-16 offsets. | Use the layout engine's hit-testing/caret API. |
| Blaming missing font glyphs for misplaced punctuation | Usually a direction/isolation issue, not merely font coverage. | Diagnose layer by layer. |
| Stripping all Hebrew/Arabic letters to stop Trojan Source | Blocks legitimate content and confuses scripts with controls. | Target policies at control characters and high-risk fields. |
| Testing only a single fixed line | Wrapping, fonts, and screen width change results. | Test across multiple widths and contents. |

## 14. Testing Bidi when the UI already has a layout engine

To test properly, separate **unit tests on logical data** from **integration/UI tests on the renderer**.

| Test type | Sample input | What to confirm |
| --- | --- | --- |
| Java unit | `"ABC "` + three Hebrew letters | `Bidi` identifies runs and levels as expected in the test environment. |
| String model | Mixed RTL/LTR | Source data is not reversed while passing through the pipeline. |
| UI integration | RTL sentence containing a Latin ID | ID displays and copies properly; punctuation does not bleed onto the wrong side. |
| UI integration | LTR sentence containing an Arabic/Hebrew name | Joining/marks/reading render properly for the font and script. |
| UI responsive | Same text across multiple widths | Wrapping and caret remain accurate after reflow. |
| UI direction | LTR/RTL containers | Navigation/icon layout and text direction are handled separately. |
| Formatting | Numbers, times, minus signs, URLs, and emails | Token boundaries are right without altering ID bytes. |
| Keyboard | Caret movement, selection, Backspace/Delete | Does not corrupt graphemes or select the wrong range. |
| Clipboard | Copy/paste mixed-direction tokens | Logical order is preserved. |
| Accessibility | Screen reader and selection | Reading order reflects content and semantics. |
| Security | `U+202E`, unclosed isolates, sensitive controls | Detection and display/audit policies are clear. |
| Unicode | ZWJ emojis, combining marks, surrogate pairs | Character clusters are not split apart. |

### Bidi unit tests do not replace UI tests

In the Java program in section 5, `getRunCount()==2` proves the parser identifies those specific runs. It does **not** prove:

- The Hebrew letters are drawn with accurate glyphs in the target font.
- Punctuation in an actual translation lands properly after line wrapping.
- Selecting text with mouse/caret returns accurate logical offsets.
- HTML `bdi` or an Android `TextView` is configured properly.
- Real-world emojis, combining marks, URLs, and directional control characters produce good results.

Only integration/UI tests on the actual renderer verify those requirements. When testing UIs, avoid relying solely on image snapshots: also cross-check clipboard contents, selection offsets, and IDs sent to the backend.

## 15. Self-practice exercises

**Exercise 1 — Logical vs. visual:** create the string `"ABC \u05D0\u05D1\u05D2"`. Use `java.text.Bidi` to print base level, run count, and run start/limit/level. Write an explanation of why you should not construct a new `String` from those runs to pass to a Bidi-capable component.

**Exercise 2 — Changing base direction:** try `DIRECTION_LEFT_TO_RIGHT`, `DIRECTION_RIGHT_TO_LEFT`, and `DIRECTION_DEFAULT_LEFT_TO_RIGHT` on sentences with different initial strong characters. Observe neutral characters near periods, parentheses, and numbers. Do not confuse base direction with locale.

**Exercise 3 — RTL UI containing an order code:** create an RTL translation containing `orderId="AB-1234/56"`. Use the UI's appropriate isolation mechanism and compare against raw string concatenation; verify copy/paste and display on a narrow screen. Do not reverse `orderId`.

**Exercise 4 — HTML:** create a page with `dir="rtl"` and a `<bdi dir="auto">` token. Test when the token starts with Latin, Arabic, or a neutral character. Comment on cases requiring explicit direction instead of `auto`. Ensure dynamic text is rendered with safe escaping.

**Exercise 5 — Text editor:** in a mixed-text input box, test the caret at run boundaries, range selection, character deletion, pasting multi-code-point emojis, and resizing the window. Note what breaks if the app computes pixel coordinates directly from UTF-16 offsets.

**Exercise 6 — Inspecting controls:** create test data containing `U+202E`, `U+2066`, and `U+2069` in a safe test environment. Observe how it displays and how to log a string as code points. Design a policy for filenames/identifiers that distinguishes misleading controls from valid RTL letters.

**Exercise 7 — Comparing failure layers:** describe three cases: disconnected Arabic letters, UTF-8 mis-decoded into `Ã...`, and misplaced parentheses in RTL/LTR text. Identify shaping, charset, or Bidi/isolation respectively as the layer to diagnose.

### Completion checklist

- [ ] Understand that logical order differs from visual order and never reverse a `String` to "fix" RTL.
- [ ] Know that `java.text.Bidi` analyzes embedding levels/runs rather than shaping or drawing itself.
- [ ] Distinguish base direction, locale, layout direction, and text direction.
- [ ] Never run reordering a second time when the UI already has a text layout engine.
- [ ] Use the UI's isolation capabilities for standalone tokens when needed.
- [ ] Do not inject Unicode control characters into data arbitrarily.
- [ ] Know how to detect risky bidi controls in sensitive data without banning valid RTL letters.
- [ ] Pick the right layer to handle each concern: model, localization, text layout, input/clipboard, security.
- [ ] Test actual rendering, wrapping, caret, copy/paste, fonts, and accessibility.
- [ ] Know when core `Bidi` is useful: building/diagnosing specialized text layout, not replacing Bidi-capable widgets.

**Conclusion:** when a UI already has a **Bidi-aware text layout engine**, the application should **keep text in logical order**, supply appropriate paragraph direction/isolation, and let the renderer decide visual order, shaping, line breaks, and caret behavior. `java.text.Bidi` is a useful **analysis** tool when you genuinely need pipeline control—not an extra step to run on every RTL `String`, and certainly never a reason to reverse or overwrite character data.
