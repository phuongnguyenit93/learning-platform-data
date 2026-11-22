# Directional Runs and Embedding Levels in Java

## 1. The problem: a single line can contain multiple text directions

In internationalized interfaces, not all text is read from left to right (**LTR, left-to-right**). Vietnamese, English, and most Latin scripts typically run LTR; Hebrew and Arabic typically run **RTL, right-to-left**. A single sentence can contain both, interspersed with numbers, punctuation, product codes, or URLs:

~~~text
abc אבג 123 xyz
~~~

The string above is written here in the **logical order** of its characters: `a b c`, a space, three Hebrew letters, a space, `1 2 3`, a space, `x y z`. On an interface supporting the Unicode Bidirectional Algorithm (**UBA**), elements may appear in a **visual order** different from their storage order. The placement of punctuation, parentheses, and digits also depends on the **paragraph base direction**, adjacent characters, and any directional control marks provided.

Java provides the standard API `java.text.Bidi` to **analyze directionality and embedding levels** for bidirectional text, as well as Java2D APIs such as `TextLayout` to support layout and rendering. This lesson focuses on understanding **directional runs**, **embedding levels**, **paragraph direction**, how to inspect them in Java, and how to apply them safely in UIs.

**Remember from the start:** do not reverse a `String` yourself to display Hebrew/Arabic. **Keep data in logical order** and use BiDi-aware display components together with an appropriate direction policy.

## 2. Logical order and visual order are two distinct concepts

| Concept | Meaning | Application example |
| --- | --- | --- |
| **Logical order** | The order in which characters are stored in a string and indexed | `String`, database records, copy/paste results |
| **Visual order** | The left-to-right layout order of segments/characters on a display line after the bidi algorithm | Layout in a GUI, browser, PDF renderer |
| **Base direction** | The baseline direction of a paragraph, typically LTR or RTL | An English chat message vs. an Arabic chat message |
| **Directional run** | A contiguous span sharing the same resolved bidi level | A Latin slice, a Hebrew slice, a digit group |
| **Embedding level** | An integer indicating even/odd direction and nested context | Levels `0`, `1`, `2` on the same line |
| **Isolation** | Separating a text slice from the directional influence of surrounding content | Inserting a username of unknown language into a sentence |
| **Glyph shaping** | Converting characters into glyph forms, joining strokes, selecting contextual shapes by font | Connected Arabic letter forms |

Three layers of processing must be separated:

1. **Data:** preserve logical code point order, content, and identifiers.
2. **Bidi layout:** determine runs and directional ordering.
3. **Rendering:** draw glyphs, select fonts, shape text, position marks, handle caret and hit testing.

`java.text.Bidi` supplies information at layer 2; it is **not** itself a complete Arabic rendering API. Reversing a `String` or reversing individual `char` values does not solve shaping, combining marks, emoji clusters, brackets, or caret positions.

## 3. How does the Unicode Bidirectional Algorithm classify characters?

The UBA does not merely ask "which language is this?" It uses **each character's directional property**, context, and directional resolution rules.

Key categories to know:

| Direction type | Examples | Role |
| --- | --- | --- |
| Strong LTR | Latin letters `a`, `b`, `c` | Provide strong LTR direction |
| Strong RTL | Many Hebrew, Arabic letters | Provide strong RTL direction |
| Numeric/weak | Digits `0–9` and some numeric separators | Have dedicated rules; not simply "RTL because inside an RTL sentence" |
| Neutral | Whitespace, many parentheses and punctuation marks | Apparent direction can be governed by neighbors |
| Explicit formatting | `RLE`, `LRE`, `RLO`, `LRO`, `PDF`, isolates | Change directional context or isolation under UBA |

Java provides `Character.getDirectionality(int codePoint)` and `Character.DIRECTIONALITY_*` constants to inspect the **Unicode directional class** of a single code point. However, **a single character's property is not its final embedding level**: `Bidi` still has to apply paragraph-wide rules.

For example, a number `123` between Hebrew words can receive an **even** level so its digits retain a sensible reading sequence, while the RTL letters receive an **odd** level. Boundary spaces may belong to a different run than a beginner would guess.

### Paragraph direction and the first strong character

The algorithm needs to determine the paragraph's base direction. There are two common ways:

- **Set the base direction explicitly** using UI metadata (for instance, an RTL/LTR input field) or a `Bidi` parameter.
- **Let the algorithm infer it** from the first strong character; if no strong character exists, use a fallback direction.

Do not infer the entire paragraph's direction solely from the language of a few words at the end of a sentence. A paragraph whose first strong character is Latin can be given an LTR base even if a long RTL section follows.

## 4. Embedding levels: even is LTR, odd is RTL

`Bidi` resolves embedding levels for character spans. Intuitive rule:

- **Even levels:** LTR direction, such as `0`, `2`, `4`.
- **Odd levels:** RTL direction, such as `1`, `3`, `5`.
- A higher level means the segment sits in a more deeply nested directional context; it is **not** a character count or the number of `String.substring` calls.
- The base direction usually corresponds to level `0` for an LTR-base paragraph or `1` for an RTL-base paragraph.

For example, level `2` can appear for an **LTR digit group** inside a level `1` RTL region. Thus a line that looks like it has only two languages can still have **more than two levels**.

**Do not confuse this:** encountering an RTL word does not always create "level 1" and encountering digits does not always create "level 2" in every case. Actual levels are computed from the full bidi context, base direction, and directional controls; the values above are simply common cases.

### What is a Run in Bidi?

A **level run** is a contiguous range sharing the same resolved level. `java.text.Bidi` has these methods:

| API | Meaning |
| --- | --- |
| `getBaseLevel()` | Base level of the paragraph: typically `0` or `1` |
| `baseIsLeftToRight()` | Check if base direction is LTR |
| `isLeftToRight()` | Paragraph is purely LTR with an LTR base |
| `isRightToLeft()` | Paragraph is purely RTL with an RTL base |
| `isMixed()` | Has mixed directions requiring handling |
| `getRunCount()` | Number of contiguous level runs |
| `getRunStart(i)` | Starting index of the `i`-th run, inclusive |
| `getRunLimit(i)` | **Exclusive** ending index of the run |
| `getRunLevel(i)` | Embedding level of the run |
| `getLevelAt(index)` | Resolved level at a character index |
| `getLength()` | Length of the analyzed segment |

**Java `Bidi` indices are based on UTF-16 character positions**, just like `String.substring(start, end)`. If a string contains non-BMP characters (such as emojis), a single code point can occupy **two code units**, so do not treat run indices as visible grapheme positions.

## 5. Runnable example: inspecting runs and embedding levels in Java 17+

Create the file `BidiRunsDemo.java`:

~~~java
import java.text.Bidi;

public class BidiRunsDemo {
    public static void main(String[] args) {
        // abc + a Hebrew word + digits + xyz, in logical order.
        String text = "abc \u05D0\u05D1\u05D2 123 xyz";

        Bidi bidi = new Bidi(
                text, Bidi.DIRECTION_LEFT_TO_RIGHT);

        System.out.println("Length: " + text.length());
        System.out.println("Base level: " + bidi.getBaseLevel());
        System.out.println("Mixed: " + bidi.isMixed());
        System.out.println("Runs: " + bidi.getRunCount());

        for (int i = 0; i < bidi.getRunCount(); i++) {
            int start = bidi.getRunStart(i);
            int limit = bidi.getRunLimit(i);
            int level = bidi.getRunLevel(i);

            System.out.printf("Run %d: [%d,%d) level=%d %s%n",
                    i, start, limit, level,
                    level % 2 == 0 ? "LTR" : "RTL");
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 BidiRunsDemo.java
java BidiRunsDemo
~~~

Output with Java's algorithm verified on the JDK:

~~~text
Length: 15
Base level: 0
Mixed: true
Runs: 4
Run 0: [0,4) level=0 LTR
Run 1: [4,8) level=1 RTL
Run 2: [8,11) level=2 LTR
Run 3: [11,15) level=0 LTR
~~~

Explanation of segments by **logical position**:

- `[0,4)` holds `abc` and a space, level 0 (LTR).
- `[4,8)` holds three Hebrew characters and a space per the example's resolution, level 1 (RTL).
- `[8,11)` is `123`, level 2 (LTR inside an RTL context).
- `[11,15)` holds a space and `xyz`, level 0.

This is crucial evidence: **a level-2 run can sit right between LTR/RTL regions**, and the runs supplied by `Bidi` are **intervals in logical order**. Do not treat the order returned by `getRunStart` as already being **visual order**.

Note: the string in source uses `\u05D0\u05D1\u05D2` instead of literal Hebrew so readers clearly see the code points and avoid copy-paste ordering confusion in the document. Java converts these escapes into the corresponding Hebrew characters.

## 6. Different base directions can produce different levels

`Bidi` supports paragraph direction parameters:

| Constant | Policy |
| --- | --- |
| `Bidi.DIRECTION_LEFT_TO_RIGHT` | Choose LTR base |
| `Bidi.DIRECTION_RIGHT_TO_LEFT` | Choose RTL base |
| `Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT` | Infer direction from strong content; fall back to LTR if undecided |
| `Bidi.DIRECTION_DEFAULT_RIGHT_TO_LEFT` | Infer direction from strong content; fall back to RTL if undecided |

This is a **paragraph** policy, not a command to "turn every character into LTR" or "reverse the string." An RTL-base paragraph can still contain numbers and URLs that must retain LTR order.

### Runnable example: same string, two base directions

Create `BidiBaseDirectionDemo.java`:

~~~java
import java.text.Bidi;

public class BidiBaseDirectionDemo {
    public static void main(String[] args) {
        String text = "abc \u05D0\u05D1\u05D2 123 xyz";

        Bidi ltr = new Bidi(
                text, Bidi.DIRECTION_LEFT_TO_RIGHT);
        Bidi rtl = new Bidi(
                text, Bidi.DIRECTION_RIGHT_TO_LEFT);

        System.out.println("LTR base: " + ltr.getBaseLevel());
        System.out.println("LTR run count: " + ltr.getRunCount());
        System.out.println("RTL base: " + rtl.getBaseLevel());
        System.out.println("RTL run count: " + rtl.getRunCount());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 BidiBaseDirectionDemo.java
java BidiBaseDirectionDemo
~~~

Verified output:

~~~text
LTR base: 0
LTR run count: 4
RTL base: 1
RTL run count: 5
~~~

Both objects analyze **the exact same logical data**, yet spaces and boundary runs can be resolved differently depending on the base. For UIs, set base direction according to **user context / field type**, rather than relying solely on an arbitrary first character when reliable context is already known.

### Automatic direction has limits

The `DIRECTION_DEFAULT_*` modes are helpful when direction is not known ahead of time, but a string starting with a **Latin product code** followed by an Arabic sentence can be inferred as LTR. Conversely, when text consists only of digits and neutral marks, the algorithm needs a fallback. That is why field/paragraph direction metadata remains important.

## 7. Reordering: do not confuse "run analysis" with "drawing text"

`Bidi.reorderVisually(byte[] levels, int levelStart, Object[] objects, int objectStart, int count)` can reorder **objects** based on computed levels, such as text segments managed by a renderer.

### Complete example testing only reordering

Save `BidiReorderDemo.java`:

~~~java
import java.text.Bidi;
import java.util.Arrays;

public class BidiReorderDemo {
    public static void main(String[] args) {
        Object[] runs = {"A", "B", "C"};
        byte[] levels = {0, 1, 2};

        Bidi.reorderVisually(levels, 0, runs, 0, runs.length);

        System.out.println(Arrays.toString(runs));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 BidiReorderDemo.java
java BidiReorderDemo
~~~

Output:

~~~text
[A, C, B]
~~~

This is an example of **swapping the positions of objects representing runs**, not drawing glyphs. `reorderVisually` **does not shape Arabic letters**, does not turn logical text into a string fit for database storage, and has no business mutating the original text value.

### Things you should not do yourself

- `new StringBuilder(text).reverse()` to display an RTL sentence.
- Reversing the whole string and then reversing Latin words individually.
- Reversing code unit order inside a grapheme, losing combining marks/emojis.
- Manually reversing phone numbers, URLs, or product ID tags.
- Writing reordered text back to a database as a "localized version."

The UBA computes **layout for a single line**; the display engine also handles line breaking, bracket positioning, shaping, fonts, and caret movement. Visual order is a presentation result and **must not become source data**.

## 8. Whole-paragraph Bidi vs. per-line Bidi after line breaking

A paragraph can be broken into multiple **display lines** depending on text box width, font size, and device. When that happens, visual reordering must be applied **per line**, rather than simply reordering the whole paragraph and slicing the string by character count.

`Bidi.createLineBidi(int lineStart, int lineLimit)` creates a bidi object for a line range (with indices relative to the analyzed paragraph). This is a helper step for renderers.

### Runnable Java 17+ example

Create `BidiLineDemo.java`:

~~~java
import java.text.Bidi;

public class BidiLineDemo {
    public static void main(String[] args) {
        String text = "abc \u05D0\u05D1\u05D2 123 xyz";
        Bidi paragraph = new Bidi(
                text, Bidi.DIRECTION_LEFT_TO_RIGHT);

        // Suppose the first line contains [0,11).
        Bidi line = paragraph.createLineBidi(0, 11);

        System.out.println("Line base: " + line.getBaseLevel());
        System.out.println("Line length: " + line.getLength());
        System.out.println("Line runs: " + line.getRunCount());

        for (int i = 0; i < line.getRunCount(); i++) {
            System.out.printf("[%d,%d) level=%d%n",
                    line.getRunStart(i),
                    line.getRunLimit(i),
                    line.getRunLevel(i));
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 BidiLineDemo.java
java BidiLineDemo
~~~

Output verified against the JDK:

~~~text
Line base: 0
Line length: 11
Line runs: 3
[0,4) level=0
[4,8) level=1
[8,11) level=2
~~~

The range `[0,11)` here is a **hypothetical line boundary** to illustrate the API. In a real UI, line breaks must be calculated from rendered width, font, and line-breaking rules; do not split lines after 11 code units and treat that as proper line breaking for every language.

**Distinguish the two steps:** analyze bidi per paragraph; when laid out across multiple lines, the renderer handles visual ordering line by line from the result. Having an even/odd run does not itself tell you at which pixel a glyph must be drawn.

## 9. AttributedString, RUN_DIRECTION, and BIDI_EMBEDDING

Java also has an attributed text model via `AttributedString` and `java.awt.font.TextAttribute`. These tools let text/Java2D APIs understand **paragraph direction** and explicit embedding requests.

Two attributes to distinguish:

| Attribute | Role |
| --- | --- |
| `TextAttribute.RUN_DIRECTION` | Sets the base direction of **the entire paragraph**; uses `RUN_DIRECTION_LTR` or `RUN_DIRECTION_RTL` |
| `TextAttribute.BIDI_EMBEDDING` | Supplies an explicit embedding/override level for a text range per the API contract |

`RUN_DIRECTION` should have **the same value across the entire paragraph**. Setting multiple different values within one paragraph has undefined behavior according to Java documentation, so do not use it as a "flip direction word by word" mechanism by painting attributes onto individual characters.

`BIDI_EMBEDDING` can use positive levels for embedding or negative levels for overrides. It is an **advanced** mechanism; let the UBA compute levels automatically unless you have a specific layout requirement. Setting wrong levels can produce unreadable results or enlarge spoofing risk surfaces.

### Complete example: specifying an RTL base direction

Save `AttributedBidiDemo.java`:

~~~java
import java.awt.font.TextAttribute;
import java.text.AttributedString;
import java.text.Bidi;

public class AttributedBidiDemo {
    public static void main(String[] args) {
        String text = "abc \u05D0\u05D1\u05D2 123 xyz";
        AttributedString attributed = new AttributedString(text);

        attributed.addAttribute(
                TextAttribute.RUN_DIRECTION,
                TextAttribute.RUN_DIRECTION_RTL
        );

        Bidi bidi = new Bidi(attributed.getIterator());

        System.out.println("Attributed base: "
                + bidi.getBaseLevel());
        System.out.println("Mixed: " + bidi.isMixed());
        System.out.println("Runs: " + bidi.getRunCount());
    }
}
~~~

Compile/run on Java 17+:

~~~bash
javac -encoding UTF-8 AttributedBidiDemo.java
java AttributedBidiDemo
~~~

Verified output:

~~~text
Attributed base: 1
Mixed: true
Runs: 5
~~~

This snippet shows `AttributedString` can carry **RTL base direction** information without modifying the source string. `TextAttribute` belongs to the Java Desktop module (`java.desktop`) in a full JDK; `java.text.Bidi` belongs to `java.base`.

### BIDI_EMBEDDING on internal ranges

You can specify a level for a range when a renderer requires it:

~~~java
AttributedString a = new AttributedString(text);
a.addAttribute(
        TextAttribute.BIDI_EMBEDDING,
        Integer.valueOf(2),
        from, to
);
~~~

This is a **snippet inside a method**, with `text` of type `String` and `from/to` as valid UTF-16 offsets, not a standalone runnable class. Requires importing `java.text.AttributedString` and `java.awt.font.TextAttribute`.

**Do not use carelessly:** the `TextAttribute` documentation notes that when `BIDI_EMBEDDING` is set anywhere in a paragraph, traditional Unicode embedding/override controls such as `RLE/LRE/RLO/LRO/PDF` are ignored by that attribute mechanism; runs without the attribute are treated as level 0. Thus mixing both mechanisms without understanding precedence can corrupt results.

If you are building a UI in Swing, JavaFX, or HTML, prefer the **framework's built-in bidi support** over manually intervening in per-character levels.

## 10. Unicode bidi controls: embedding, override, mark, and isolate

In plain text, Unicode defines several **non-visible** control characters that can affect how letters and punctuation are placed:

| Group | Name | Code point | General effect |
| --- | --- | --- | --- |
| Mark | LRM | `U+200E` | Local LTR direction mark |
| Mark | RLM | `U+200F` | Local RTL direction mark |
| Mark | ALM | `U+061C` | Local Arabic letter direction mark |
| Embedding | LRE | `U+202A` | Start an LTR embedding region |
| Embedding | RLE | `U+202B` | Start an RTL embedding region |
| Termination | PDF | `U+202C` | Close a traditional embedding/override region |
| Override | LRO | `U+202D` | Force LTR directional interpretation |
| Override | RLO | `U+202E` | Force RTL directional interpretation |
| Isolate | LRI | `U+2066` | Isolate an LTR region |
| Isolate | RLI | `U+2067` | Isolate an RTL region |
| Isolate | FSI | `U+2068` | Isolate according to the first strong char in the region |
| Termination | PDI | `U+2069` | End the corresponding isolate region |

These characters **do not alter stored letters** in the sense of turning `a` into `b`; they alter **visual layout**. Certain controls can become hard to spot during copy/paste or code review because they have zero width.

### How is embedding different from override?

- **Embedding** only establishes a directional context for a region, while the algorithm still considers the directional properties of characters inside.
- **Override** forces directional interpretation, which can display character sequences counterintuitively; use only in very special cases.
- **Isolate** lets an inserted region have independent directionality without reciprocally disturbing surrounding text. For inserted content of unknown language, this is usually a better approach than traditional embedding.

**Security warning:** `RLO/LRO` and invisible controls can be used to deceive readers about **filenames, displayed strings, or source code structure** (bidi spoofing). Do not insert override controls into user data just to "fix the UI," and do not treat a visually observed string as reliable proof of stored code point order.

### Isolate in plain text

In terms of Unicode UAX #9 semantics:

~~~text
FSI + text with unknown direction + PDI
~~~

requests isolating a text slice and inferring direction from the first strong character within that slice. In Java, control characters can be written with Unicode escapes:

~~~java
String isolated = "\u2068" + userText + "\u2069";
~~~

This is a **snippet inside a method**; `userText` is a pre-existing `String` variable. In real use, you must check whether the target display component **properly supports isolate controls**. In particular, do not assume every version of `java.text.Bidi`, every terminal, or every widget implements the exact same version of Unicode UBA.

With HTML, using dedicated directional markup is usually easier to maintain than storing control characters inside translations or usernames.

## 11. HTML/Web UI: setting container direction and isolating inserts

When a Java backend supplies text for a web UI, browsers have dedicated mechanisms for managing direction:

~~~html
<section dir="rtl">
  <p>نص عربي: <bdi dir="auto">Order ABC-123</bdi></p>
</section>
~~~

This is an illustrative **HTML snippet**, not Java code. The `<bdi>` element isolates text of unknown direction; `dir="auto"` allows the browser to infer the content's direction. `dir="rtl"` defines the container's direction.

In real UIs:

1. Determine the **paragraph/block** direction from the display language or field type.
2. Isolate **interpolated values** (person names, titles, product codes) when they may carry a different direction from the container.
3. For values with a fixed direction such as LTR technical codes, explicitly specify `dir="ltr"` on the appropriate element.
4. Always **HTML-escape** untrusted data before inserting into markup; `bdi` does not replace HTML injection/XSS defenses.
5. Test boundary symbols too: parentheses, colons, commas, prefixes, suffixes, file extensions.

**Do not "fix direction" by reversing a `String` in Java before emitting HTML.** Once data is reversed, the browser can run bidi **a second time**, yielding unpredictable results.

For Swing/Java2D, use component text directionality and `TextLayout`; for JavaFX or another UI framework, consult that framework's own direction/orientation properties.

## 12. Renderers, shaping, and fonts: why java.text.Bidi is not enough

A real renderer must combine:

- **Bidi reordering:** determining the visual display sequence of runs.
- **Shaping:** selecting appropriate glyphs and joining forms, especially for Arabic script.
- **Font fallback:** if a font lacks needed glyphs, the renderer may need to pick another font.
- **Combining marks:** attaching diacritics to base letters at proper positions.
- **Line breaking:** wrapping lines according to width and language rules.
- **Cursor/selection:** mapping between logical positions in `String` and visual positions on screen.
- **Mirroring:** rendering parentheses/symbols with mirrored behavior in bidi contexts when required.

Therefore, a custom function that reads `getRunLevel` and concatenates `substring` results in a new order is **not enough** to replace a multilingual layout engine.

### TextLayout in Java2D

Java provides `java.awt.font.TextLayout` to handle text layout with fonts and rendering context. A text layout can be constructed as follows:

~~~java
Font font = new Font("Serif", Font.PLAIN, 20);
FontRenderContext frc = new FontRenderContext(null, true, true);
TextLayout layout = new TextLayout(text, font, frc);
~~~

This is a **snippet inside a method**, requiring imports for `java.awt.Font`, `java.awt.font.FontRenderContext`, and `java.awt.font.TextLayout`; variable `text` is an existing `String`. Actually drawing requires `Graphics2D`, a drawing surface, and a suitable font. The snippet illustrates API usage, **not a complete renderer**.

Specifically, if the interface uses HTML/a browser, there is no need to construct `TextLayout` in the Java backend just for the browser to draw text: return the **logical string** along with appropriate direction metadata.

## 13. Inspecting invisible directional characters when debugging

A string can contain `RLO`, `LRE`, `FSI`, or `PDI` that normal logs do not visibly show. If a UI displays a filename with a "flipped extension" or jumping punctuation, inspect the actual code points instead of guessing from a screenshot.

### Complete Java 17+ example: detecting specific bidi controls

Create `BidiControlAuditDemo.java`:

~~~java
import java.util.Set;

public class BidiControlAuditDemo {
    private static final Set<Integer> BIDI_CONTROLS = Set.of(
            0x061C, 0x200E, 0x200F,
            0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
            0x2066, 0x2067, 0x2068, 0x2069
    );

    public static void main(String[] args) {
        String input = "report\u202Etxt\u202C";

        System.out.println("Code units: " + input.length());
        input.codePoints()
                .filter(BIDI_CONTROLS::contains)
                .forEach(cp ->
                        System.out.printf("Bidi control: U+%04X%n", cp)
                );
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 BidiControlAuditDemo.java
java BidiControlAuditDemo
~~~

Output:

~~~text
Code units: 11
Bidi control: U+202E
Bidi control: U+202C
~~~

Why `11`? `report` has 6 characters, `RLO` has 1, `txt` has 3, `PDF` has 1: 11 UTF-16 code units total. Both control characters are still **present in the string**, even though they usually have no visible glyph.

**This is an auditing example**, not a recipe to "strip all controls." Some systems genuinely need valid directional characters; some protocols forbid them. Apply rules according to data type:

- Technical codes/IDs/filenames: may forbid or warn on a specific set of controls by schema.
- Multilingual natural prose: may need to retain valid controls, though metadata/markup is preferable if available.
- Logs and security review screens: display/escape controls so reviewers notice logical order.
- If removing or transforming them, understand the impact on readability, traceability, and identifiers.

## 14. Practical scenario: UI sentence inserting names, numbers, and URLs

Suppose an application builds a notification inside an RTL container:

~~~text
[Arabic sentence] + [English username] + [order number] + [punctuation]
~~~

If you simply concatenate strings:

~~~java
String message = prefix + username + " (" + orderId + ")";
~~~

this is a **snippet inside a method** with three `String` variables. The content in logical order may still be accurate, yet on screen you can see **parentheses, colons, or symbols** placed unexpectedly when inserted parts have a different direction.

Better design:

1. **Keep each variable separate** (`username`, `orderId`) in the model.
2. **Use full-sentence translations** or locale-appropriate message patterns rather than concatenating grammatical fragments.
3. **Supply the container/paragraph direction** according to the display language.
4. **Isolate inserted parts** when the UI framework supports it, especially strings of unknown direction.
5. **Test neutral marks** (parentheses, colons, hyphens, commas) and digit-only strings.
6. **Never use string reversal** to compensate for display bugs.

### Numbers, currency, and paths

Digit groups generally behave LTR even inside an RTL paragraph. Do not write code to reverse digits `123` into `321`. For currency, such as `123.45 USD` or numbers in Arabic-Indic digits, separate two concerns: **locale-based number formatting** and **bidi directional layout**. Changing digits by locale with `NumberFormat` does not by itself define the entire visual order of a sentence.

URLs, product codes, and emails usually need to be read with LTR syntax. When placed in an RTL sentence, give them an isolated display region with the appropriate direction without altering content like `user@example.com` or code `AB-123`.

## 15. Do not equate text direction with language, script, and locale

A `Locale` like `ar-EG` or `he-IL` can suggest a language/region that typically uses RTL scripts, yet **does not** replace analyzing the string itself. An Arabic message can contain plenty of Latin words and digits; an English app can quote Hebrew text.

Three distinct pieces of information:

- **Locale:** language/region and content conventions.
- **Script:** writing system, e.g. Latin, Arabic, Hebrew.
- **Text direction:** presentation direction of a paragraph/run under bidi rules.

Do not assume "every string in an Arabic locale has RTL direction" and reverse all content yourself. Instead, set the **paragraph direction** for the UI and let the bidi algorithm resolve each run's direction.

If receiving user-authored content in chat, each message's direction can differ; user language metadata alone is not enough to decide the direction of every sentence a user writes.

## 16. Common mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Reversing the entire `String` when Hebrew/Arabic is present | Numbers, combining marks, emojis, URLs, logical order break | Keep string logical; use a bidi renderer |
| Thinking RTL means every character inside is RTL | Digits and Latin parts get mishandled | Let UBA resolve runs/levels |
| Treating `getRunCount` as word count or language count | Misconception: a digit group can form its own run | A run is a span with the same embedding level |
| Reading returned runs in order as visual order | Wrong display because runs are indexed logically | Use line layout/reordering |
| Thinking level 2 means "priority level 2" character | Misunderstanding embedding | Even/odd indicates direction; numbers also reflect nesting context |
| Assigning paragraph direction by the last character | Punctuation/inserted parts become unstable | Set base direction explicitly or use first-strong as required |
| Wrapping lines after reversing the whole string | End-of-line segments appear out of order | Lay out line by line per UBA |
| Using `Bidi` as an Arabic text-drawing tool | Missing shaping/glyphs/line breaking | Use `TextLayout` or an appropriate UI renderer |
| Using `RLO` control to "fix" every parenthesis | Can cause text spoofing, hard to debug | Use direction metadata/isolate/markup |
| Mixing `TextAttribute.BIDI_EMBEDDING` with embedding controls arbitrarily | Unpredictable precedence rules | Pick one API-backed strategy |
| Assuming `String.length()` is the count of visible glyphs | Wrong for surrogate pairs/combining marks | Distinguish UTF-16, code points, and graphemes |
| Not checking invisible controls in sensitive inputs | Risk of misreading filenames, source code, or IDs | Audit and apply an identifier profile |
| Treating locale as a string-reversal command | Leads to data corruption | Locale, script, and direction are three separate layers |
| Using HTML strings while forgetting to escape data | XSS, unrelated directly to bidi | Escape and use standards-compliant directional markup |

## 17. Testing workflow for a bidi-aware feature

A useful checklist for GUIs/APIs with multilingual text:

1. Test **LTR** and **RTL** base paragraphs with the same interpolated parts.
2. Use a Latin sentence mixed with Hebrew, an Arabic sentence mixed with Latin, and a digits/punctuation-only sentence.
3. Inspect **run levels** with `Bidi.getRunLevel` and verify `getRunStart/getRunLimit` boundaries.
4. Run `createLineBidi` under actual line-wrapping scenarios.
5. Test positions of **parentheses, colons, hyphens**, numbers, and currency symbols.
6. Test **URLs, emails, and product codes** inside RTL sentences.
7. Test combining marks, emojis, ZWJ, and non-BMP content to avoid splitting UTF-16 incorrectly.
8. Test usernames with a different direction from the container using proper isolation.
9. Check copy/paste: does logical order after copying match the source data?
10. Test caret position, selection, and deletion behavior in editable widgets.
11. Review **invisible bidi controls** and security policies for filenames, code, and logs.
12. Test on the **actual renderer** (Swing/JavaFX/browser/mobile), not just reading `Bidi` in the console.

### Exercises

1. Why does `"abc \u05D0\u05D1\u05D2 123 xyz"` in `BidiRunsDemo` produce runs at levels 0, 1, and 2 even though it only contains Latin letters, Hebrew, and digits?
2. Compare `DIRECTION_LEFT_TO_RIGHT` and `DIRECTION_RIGHT_TO_LEFT` on the same string. Why can the base level and run count differ?
3. Use `getRunStart`, `getRunLimit`, and `getRunLevel` to print a run table. Why must you not treat it as visual order?
4. Explain the meaning of even and odd levels. Does level `3` necessarily mean a different RTL language from level `1`?
5. Given `reorderVisually` and levels `{0,1,2}`, explain why the example outputs `[A, C, B]` yet does not render complete Arabic text.
6. Create an `AttributedString` with `RUN_DIRECTION_RTL`. Why is that different from applying `BIDI_EMBEDDING` to a small slice?
7. Distinguish `RLE...PDF` from `RLI...PDI`. In a web UI inserting a username of unknown direction, why is `bdi` the right choice?
8. Find bidi controls in a filename using `codePoints()`, then propose separate validation policies for filenames and comment text.
9. Design a UI displaying an Arabic sentence containing `user@example.com`. Outline the data-handling, direction-marking, and rendering steps.
10. Explain why parentheses and numbers must be tested **after per-line layout**, not only via `String.equals`.

**Remember:** mixed LTR/RTL text is stored in **logical order** yet can be displayed in **visual order** determined by the Unicode Bidirectional Algorithm. `java.text.Bidi` analyzes base direction, runs, and embedding levels; **even levels are LTR, odd levels are RTL**, while higher levels reflect nested contexts. `TextAttribute`/`TextLayout` and UI frameworks handle display support. Prefer direction metadata and **isolation** for inserted parts instead of reversing strings or injecting invisible overrides; always check security and Unicode behavior when handling user data.

### References

- [Java SE 17 — Bidi](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Bidi.html) — constructors, embedding levels, runs, `createLineBidi`, and `reorderVisually`.
- [Java SE 17 — TextAttribute](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/font/TextAttribute.html) — `RUN_DIRECTION`, `BIDI_EMBEDDING`, and precedence rules.
- [Java SE 17 — TextLayout](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/font/TextLayout.html) — complex text layout.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html) — `getDirectionality` and code points.
- [Unicode Standard Annex #9 — Unicode Bidirectional Algorithm](https://www.unicode.org/reports/tr9/) — standard for paragraphs, embedding, overrides, isolates, and visual order.
- [W3C — Strings on the Web: Language and Direction Metadata](https://www.unicode.org/TR/string-meta/) — direction metadata for text and web applications.
