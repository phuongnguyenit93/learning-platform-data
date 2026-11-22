# java.text.Bidi and Base Direction in Java

## Lesson Objectives

A Java string can contain both **left-to-right** (LTR) scripts, such as Vietnamese and English, and **right-to-left** (RTL) scripts, such as Hebrew or Arabic. Numbers usually have a left-to-right reading order even when placed inside an RTL sentence; parentheses, periods, colons, and spaces do not carry a strong independent direction on their own. Consequently, **character order in memory** and **the order seen on screen** do not always coincide.

`java.text.Bidi` is the Java class that supports analysis under the *Unicode Bidirectional Algorithm* (UBA). It determines **paragraph base direction**, **embedding levels**, and **runs sharing the same level** (*directional runs*), providing the basis for display systems to arrange mixed text for readers.

After this lesson, you can:

- Explain the difference between logical `String` order and bidirectional visual order.
- Distinguish *base direction*, strong/weak/neutral character directionality, and embedding level.
- Use the four options `DIRECTION_LEFT_TO_RIGHT`, `DIRECTION_RIGHT_TO_LEFT`, `DIRECTION_DEFAULT_LEFT_TO_RIGHT`, and `DIRECTION_DEFAULT_RIGHT_TO_LEFT`.
- Read the results of `getBaseLevel()`, `baseIsLeftToRight()`, `getRunCount()`, `getRunStart()`, `getRunLimit()`, and `getRunLevel()`.
- Understand why `isMixed()` does not simply mean "the string contains two different alphabets."
- Know when to use `createLineBidi(...)`, `requiresBidi(...)`, and `reorderVisually(...)`, and their limitations.
- Avoid reversing strings with `StringBuilder.reverse()` or manually reordering RTL characters.
- Handle practical scenarios: Arabic/Hebrew labels mixed with numbers, URLs, product codes, punctuation, user-entered text, Unicode bidi controls, and UI testing.
- Distinguish **bidi analysis** from **glyph shaping**, font selection, GUI layout, and UI directional attributes.

This lesson belongs to the **Text Direction and Display** section. The goal is to understand and use `Bidi` within its proper scope, not to rebuild an entire Unicode text-drawing engine.

## 1. Why does a string need a bidirectional algorithm?

Consider an illustrative text in logical order:

```text
ABC שלום XYZ
```

Here `שלום` is a Hebrew string read RTL. The logical order in `String` remains:

```text
A B C [space] ש ל ו ם [space] X Y Z
```

Characters are stored in **content order**; Java does not reorder Hebrew letters in a `String` merely because they belong to an RTL script. When the rendering system draws, it must handle each run's direction so the text displays naturally.

Several details make "reversing the entire string" wrong:

- Latin letters `ABC` are still read LTR.
- Hebrew letters are presented RTL.
- A number such as `2026` can keep its numeric reading order when inside an RTL sentence.
- Parentheses, colons, and spaces depend on context; they do not necessarily land in the right places if you just reverse the character array.
- An RTL run can contain an LTR sub-run at a deeper level.
- Combining characters and emojis may consist of multiple code points; reversing individual `char` values can break graphemes or surrogate pairs.

**Bidi does not alter the storage order of a `String`**. It provides information so the layout engine can decide how to present text segments according to Unicode rules.

## 2. Three foundational concepts: character direction, base direction, and level

### 2.1. Character direction

The bidi algorithm uses the Unicode directional property (*Bidi_Class*) of each code point. Notable classes include:

| Class | Meaning | Example |
| --- | --- | --- |
| `L` | Strong left-to-right | Latin letters in Vietnamese, English |
| `R` | Strong right-to-left | Most Hebrew letters |
| `AL` | Arabic right-to-left | Many Arabic letters |
| `EN` | European number | Digits `0–9` |
| `AN` | Arabic number | Certain Arabic-Indic digits |
| `WS` | Whitespace | Spaces |
| `ON` and other neutral classes | Context-dependent marks/symbols | Certain parentheses, punctuation |
| `NSM` | Nonspacing mark | Many Unicode combining marks |

`L`, `R`, or `AL` characters are called **strong directional characters**. Many punctuation marks, digits, and whitespace characters are **weak** or **neutral**: how they are handled depends on nearby characters and paragraph direction.

Therefore, looking at a leading digit in a string is not enough to decide "this paragraph is definitely LTR." When using automatic direction, the choice is typically based on the **first strong character**, not the first character regardless of type.

### 2.2. Base direction

**Paragraph base direction** determines the baseline direction used to resolve segments without a clear strong direction, especially punctuation, spaces, and mixed combinations. There are two main base directions:

- **LTR:** base level is `0`, an even level.
- **RTL:** base level is `1`, an odd level.

Base direction does not mean every run in the paragraph flows in that direction. An RTL sentence can still contain LTR runs; likewise, an English sentence can contain a Hebrew proper name.

Example:

```text
Paragraph A: ABC שלום XYZ    -> first strong character is A (LTR)
Paragraph B: שלום Hello      -> first strong character is ש (RTL)
Paragraph C: 123 - 45        -> no strong letters in this content
```

With default direction selection based on the first strong character, A has an LTR base, B has an RTL base, and C needs a **chosen fallback**.

### 2.3. Embedding level

The bidirectional algorithm assigns a **resolved embedding level** to text positions. Simple reading rule:

- **Even** levels denote an LTR run.
- **Odd** levels denote an RTL run.
- Higher levels can represent a run inside an opposite-direction context at a deeper nesting depth.

For example, level `2` is still LTR, but it may be an LTR segment inside a level `1` RTL context. Do not oversimplify this into "0 is Latin, 1 is Hebrew"; a level is **the result of the algorithm and context**, not a language tag.

`Bidi` exposes runs sharing the same level via `getRunCount()` and the run-query methods. Levels provide the information needed for **visual reordering** during layout.

## 3. Four base-direction constants of Bidi

Simple constructor:

```java
import java.text.Bidi;

Bidi bidi = new Bidi(paragraph, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);
```

This is an illustrative snippet inside a method, with variable `paragraph` of type `String`. The second parameter chooses the base-direction policy.

| Constant | Meaning |
| --- | --- |
| `Bidi.DIRECTION_LEFT_TO_RIGHT` | Force LTR base direction, base level `0` |
| `Bidi.DIRECTION_RIGHT_TO_LEFT` | Force RTL base direction, base level `1` |
| `Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT` | Find the first strong character; fall back to LTR if none |
| `Bidi.DIRECTION_DEFAULT_RIGHT_TO_LEFT` | Find the first strong character; fall back to RTL if none |

**Important distinction:** The two constants containing `DEFAULT` **do not force** every string to LTR/RTL. Both still examine the first strong character; they only differ in the fallback direction when **no qualifying strong character is found**.

For example, `"שלום Hello"` starts with Hebrew, so its base direction is RTL under both `DIRECTION_DEFAULT_LEFT_TO_RIGHT` and `DIRECTION_DEFAULT_RIGHT_TO_LEFT`.

By contrast, `"123 - 45"` has only digits/neutral characters in the example and no strong L/R/AL, so the two defaults return different base levels.

### Illustrative selection table

| Logical text | Flag | Base level |
| --- | --- | --- |
| `ABC שלום XYZ` | `DEFAULT_LEFT_TO_RIGHT` | `0` |
| `שלום Hello` | `DEFAULT_LEFT_TO_RIGHT` | `1` |
| `שלום Hello` | `LEFT_TO_RIGHT` | `0` |
| `ABC שלום XYZ` | `RIGHT_TO_LEFT` | `1` |
| `123 - 45` | `DEFAULT_LEFT_TO_RIGHT` | `0` |
| `123 - 45` | `DEFAULT_RIGHT_TO_LEFT` | `1` |

"Force" only means **choosing the base direction of the paragraph**; it does not mean converting Hebrew letters into logical LTR order or turning every mark in the string into RTL.

### When should you choose an explicit direction?

If a UI field has a **fixed context** (for example, the entire screen is Hebrew/Arabic, or a technical code input is always LTR), you can explicitly pass the base direction so punctuation/numbers and content alignment are handled consistently.

If a field accepts **free-form multilingual text**, choosing based on the first strong character may be more appropriate, though you should define a fallback direction matching the UI when the user enters only digits or symbols.

Do not infer text direction solely from `Locale`: the user's UI locale and the paragraph's content do not necessarily share the same language. A user on a Vietnamese UI might enter an Arabic sentence; a user on an Arabic UI might still enter an English URL.

## 4. Creating Bidi and reading base direction

A short example:

```java
String hebrew = "\u05E9\u05DC\u05D5\u05DD"; // שלום
Bidi left = new Bidi("ABC " + hebrew,
        Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

Bidi right = new Bidi(hebrew + " Hello",
        Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

System.out.println(left.getBaseLevel());
System.out.println(right.getBaseLevel());
```

These statements are inside a method with `import java.text.Bidi;`. Stdout:

```text
0
1
```

Three methods to understand:

- `getBaseLevel()` returns the base level: `0` for LTR and `1` for RTL.
- `baseIsLeftToRight()` returns `true` if the base direction is LTR.
- `isLeftToRight()` returns `true` when **the entire line** is LTR **and** the base direction is LTR.

The third point often causes confusion: `baseIsLeftToRight()` does not imply `isLeftToRight()`. A paragraph with an LTR base containing an RTL Hebrew run satisfies:

```text
baseIsLeftToRight() = true
isLeftToRight()     = false
isMixed()           = true
```

Similarly, `isRightToLeft()` only returns `true` if the line is completely RTL and the base is RTL. `isMixed()` returns `true` when it is neither purely LTR nor purely RTL; per the API contract, it can also be `true` if the base direction differs from the direction of a single run.

Therefore, do not use `isMixed()` to conclude "there are definitely two alphabets, Latin and Arabic" or "there are at least two runs." Read the **actual base and runs**.

## 5. Reading runs and embedding levels

A `Bidi` object processing a paragraph/line provides the following methods:

| API | Meaning |
| --- | --- |
| `getLength()` | Length of text in the line by `String` index |
| `getBaseLevel()` | Base level: 0 or 1 |
| `getLevelAt(offset)` | Resolved level at the offset position |
| `getRunCount()` | Number of runs sharing the same level |
| `getRunStart(run)` | Starting offset of the run |
| `getRunLimit(run)` | Offset **immediately after** the last character of the run |
| `getRunLevel(run)` | Embedding level of the run |
| `baseIsLeftToRight()` | Check base direction |
| `isLeftToRight()` / `isRightToLeft()` | Check whether the line is purely one direction with the matching base |
| `isMixed()` | Check whether the line falls outside the two pure cases above |

Run offsets use **half-open** intervals `[start, limit)`. You can pass them directly to `substring(start, limit)` to inspect the logical-order text of each run.

For example, with:

```text
ABC שלום XYZ
```

On the tested JDK, `Bidi` returns three runs:

| Run index | Start | Limit | Level | Logical text segment |
| --- | --- | --- | --- | --- |
| 0 | 0 | 4 | 0 | `ABC ` |
| 1 | 4 | 8 | 1 | `שלום` |
| 2 | 8 | 12 | 0 | ` XYZ` |

Run `1` has an odd level, so it is RTL. Runs `0` and `2` have even levels, so they are LTR.

**Do not read the run list order as a "fully rendered display string."** `getRunStart/getRunLimit` indicate the logical slice of a run, while arranging runs into visual order and drawing glyphs are subsequent steps of the presentation engine.

### Offsets are Java UTF-16 indices

`String.length()` and `substring(...)` use UTF-16 offsets, not the number of user-perceived graphemes. `getRunStart` and `getRunLimit` also use offsets within the paragraph analyzed by `Bidi`.

The Hebrew example `שלום` in this lesson has four BMP characters, so each letter corresponds to one code unit. When emojis or supplementary code points are present in a string, you must not assume each user-perceived character occupies one offset. Avoid using `Bidi` offsets as code point indices when working with `String.codePoints()` without conversion.

## 6. Standalone Java 17+ example

Create the file `BidiBaseDirectionDemo.java`. The Hebrew characters use Unicode escapes in source so it compiles easily without depending on how the terminal displays them. The program prints **run indices** rather than trying to print a "visual RTL string," because terminal display also depends on the console.

```java
import java.text.Bidi;
import java.util.Arrays;

public class BidiBaseDirectionDemo {
    public static void main(String[] args) {
        String hebrew = "\u05E9\u05DC\u05D5\u05DD";
        String text = "ABC " + hebrew + " XYZ";

        Bidi bidi = new Bidi(
                text, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

        System.out.println("base=" + bidi.getBaseLevel());
        System.out.println("mixed=" + bidi.isMixed());

        for (int run = 0; run < bidi.getRunCount(); run++) {
            System.out.println("run " + run
                    + "=[" + bidi.getRunStart(run)
                    + "," + bidi.getRunLimit(run) + ")"
                    + " level=" + bidi.getRunLevel(run));
        }

        Bidi rtlFirst = new Bidi(
                hebrew + " Hello",
                Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

        System.out.println(
                "first RTL base=" + rtlFirst.getBaseLevel());

        String neutral = "123 - 45";

        System.out.println("neutral default LTR="
                + new Bidi(neutral,
                    Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT)
                  .getBaseLevel());

        System.out.println("neutral default RTL="
                + new Bidi(neutral,
                    Bidi.DIRECTION_DEFAULT_RIGHT_TO_LEFT)
                  .getBaseLevel());

        Bidi forced = new Bidi(
                text, Bidi.DIRECTION_RIGHT_TO_LEFT);

        System.out.println("forced base="
                + forced.getBaseLevel());

        Object[] pieces = {"A", "B", "C", "D"};
        byte[] levels = {0, 1, 1, 0};
        Bidi.reorderVisually(
                levels, 0, pieces, 0, pieces.length);

        System.out.println("visual runs="
                + Arrays.toString(pieces));

        System.out.println("requires Hebrew="
                + Bidi.requiresBidi(
                    hebrew.toCharArray(), 0, hebrew.length()));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 BidiBaseDirectionDemo.java
java BidiBaseDirectionDemo
```

Verified stdout:

```text
base=0
mixed=true
run 0=[0,4) level=0
run 1=[4,8) level=1
run 2=[8,12) level=0
first RTL base=1
neutral default LTR=0
neutral default RTL=1
forced base=1
visual runs=[A, C, B, D]
requires Hebrew=true
```

### Interpreting each group

- `base=0`: the first strong character of `ABC שלום XYZ` is `A`, so the base direction is LTR.
- `mixed=true`: the text includes an RTL Hebrew run between LTR Latin runs.
- The `run` lines report offsets and levels in logical order: run 0 `[0,4)`, run 1 `[4,8)`, run 2 `[8,12)`.
- `first RTL base=1`: when the first strong character is Hebrew, the default base direction is RTL.
- The two `neutral` lines show the difference between LTR and RTL fallbacks when input `123 - 45` has no strong L/R/AL.
- `forced base=1`: choosing `DIRECTION_RIGHT_TO_LEFT` fixes the base direction to RTL even when the string starts with Latin.
- `visual runs=[A, C, B, D]` illustrates how `reorderVisually` reorders **four simulated objects/runs** with levels `{0,1,1,0}`: the two objects at level 1 swap order during visual reordering.
- `requires Hebrew=true` proves the Hebrew segment requires bidi handling; it does not prove it has been rendered with the right glyphs.

The program demonstrates API output rather than implementing a full renderer. Do not infer from `[A, C, B, D]` that you should reverse individual characters of source text.

## 7. requiresBidi is a fast check, not display

`Bidi.requiresBidi(char[] text, int start, int limit)` checks whether a character range requires bidi analysis. It can help skip creating a `Bidi` object in a layout pipeline that only has simple LTR data.

Example:

```java
char[] latin = "Hello".toCharArray();
char[] hebrew = "\u05E9\u05DC\u05D5\u05DD".toCharArray();

System.out.println(Bidi.requiresBidi(
        latin, 0, latin.length));
System.out.println(Bidi.requiresBidi(
        hebrew, 0, hebrew.length));
```

Inside a method with `import java.text.Bidi;`, the output is:

```text
false
true
```

**However, `requiresBidi` is not a language parser, does not validate Unicode, does not check for dangerous characters, and does not decide whether the UI must align left or right.** It is a check for layout optimization. `false` does not mean the string contains only ASCII or lacks Vietnamese diacritics; plenty of Unicode text can still be completely LTR.

Do not call `requiresBidi` and then mutate bytes or reverse the `String` when it returns `true`. It does not perform the rendering step for you.

## 8. reorderVisually: reordering runs, not reversing code points

The static method:

```java
Bidi.reorderVisually(
        byte[] levels,
        int levelStart,
        Object[] objects,
        int objectStart,
        int count);
```

shown above reorders **objects representing runs** into visual order based on their corresponding levels. It does not know the Unicode contents inside an object and does not generate glyphs, attach combining marks, or perform Arabic shaping.

An easy-to-observe example:

```java
Object[] pieces = {"A", "B", "C", "D"};
byte[] levels = {0, 1, 1, 0};

Bidi.reorderVisually(levels, 0, pieces, 0, pieces.length);
System.out.println(Arrays.toString(pieces));
```

Inside a method importing `Bidi` and `Arrays`, the result is:

```text
[A, C, B, D]
```

Swapping the positions of objects `B` and `C` comes from the contiguous odd-level range; it is not an arbitrary string reversal.

Distinguish clearly:

- **Logical order:** original position of characters in the `String`.
- **Resolved levels:** direction and nesting depth after applying the algorithm.
- **Visual order of runs:** layout order of runs after analysis.
- **Visual order/glyphs within each run:** the work of the text layout engine, combining shaping, fonts, script rules, and rendering.

`reorderVisually` only supports one part of the pipeline. Do not replace the bidirectional algorithm with `Collections.reverse` or use `StringBuilder.reverse()` on Arabic/Hebrew segments: those operations break logical order and can corrupt combining marks or surrogate pairs.

## 9. createLineBidi: paragraph direction and line wrapping

The Unicode bidi algorithm is tied to **paragraphs** and **display lines**. When laying out long text, an application can:

1. Analyze the paragraph with the appropriate base direction.
2. Choose line-break points based on width, font, and line-breaking rules.
3. Generate bidi information for each line to be drawn.
4. Order and draw the runs on each line.

`Bidi.createLineBidi(lineStart, lineLimit)` creates a Bidi object representing a **sub-line** within an already-analyzed paragraph:

```java
Bidi paragraphBidi = new Bidi(
        paragraph, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

Bidi lineBidi = paragraphBidi.createLineBidi(
        lineStart, lineLimit);
```

This is an illustrative snippet inside a method where `paragraph`, `lineStart`, and `lineLimit` have already been determined by the layout engine. The two offsets simply bound the line's text slice within the paragraph; they are not pixel coordinates on screen.

If the entire paragraph fits on one line, you do not have to call `createLineBidi`. However, when text wraps across multiple lines, per-line bidi processing can have rules adjusting characters at line ends (such as whitespace) and differs from using a single run list of the whole paragraph as though it were one line.

**Do not split a paragraph by a fixed number of `char`s and assume it is laid out properly.** Line breaking also involves glyph widths, fonts, ligatures, grapheme clusters, hyphenation, punctuation, and line-breaking rules. `Bidi` does not provide full multi-line text presentation.

## 10. Other constructors and text attributes

Beyond `Bidi(String, flags)`, Java also provides constructors for complex text pipelines:

```java
new Bidi(
        char[] text,
        int textStart,
        byte[] embeddings,
        int embStart,
        int paragraphLength,
        int flags);
```

and:

```java
new Bidi(AttributedCharacterIterator paragraph);
```

These are illustrative constructor signatures, not standalone calls with undeclared variables.

The array-taking constructor lets you supply embedding information; the constructor taking `AttributedCharacterIterator` can read text attributes. Relevant attributes from `java.awt.font.TextAttribute` include:

- `TextAttribute.RUN_DIRECTION`: specified base direction.
- `TextAttribute.BIDI_EMBEDDING`: embedding or override information when needed.
- `TextAttribute.NUMERIC_SHAPING`: request numeric shaping in related pipelines.

These features are meant for layout systems with real requirements and need compatibility testing. For simply analyzing a text string and base direction, the `Bidi(String, flags)` constructor is usually clear enough.

### Embedding is not the same as mutating the source string

Embedding levels add interpretation/layout metadata; they do not turn Hebrew code points into Latin characters. Do not edit the character sequence in a `String` just to "apply" a level. When exporting data to an API or database, store the string in **logical order**, and store direction metadata separately if needed to reproduce display behavior.

## 11. Numbers, punctuation, and RTL segments

Marks such as `:`, `(`, `)`, `-`, spaces, and quotation marks usually lack a strong direction. The same string containing numbers can display those marks differently under an RTL vs. LTR base.

Some common scenarios:

### 11.1. Hebrew/Arabic labels with numbers

For example, an RTL sentence with an order code `AB-123`. The technical code is an LTR string with a hyphen, while the surrounding sentence is RTL. If you simply concatenate strings:

```java
String message = rtlText + ": " + orderId;
```

this is an illustrative snippet inside a method with existing variables. How the colon, hyphen, and code render can depend on the UI's base direction and bidi context. In a real interface, place the code inside a component with **explicit direction/isolation** rather than relying on tweaking spaces to fix the visuals.

### 11.2. URLs, emails, and filenames

URLs like `https://example.com/a?x=1`, email addresses, file paths, and product codes are usually data with LTR syntax. When they appear in an RTL sentence, how to **isolate** that data slice may need to be defined at the rendering layer.

You should not reverse URLs at the data layer or manually reverse segments of them. The logical order of a URL must stay intact so links, copy/paste, and parsers are not broken.

### 11.3. A segment containing only numbers or neutral marks

With `"123 - 45"`, `DIRECTION_DEFAULT_LEFT_TO_RIGHT` and `DIRECTION_DEFAULT_RIGHT_TO_LEFT` can yield two different base levels because there are no strong letters to decide direction.

If an input field only accepts numbers yet is displayed inside an RTL page, a dedicated direction policy may be needed (especially with minus signs, percent signs, units). **Do not use a numeric sign as a basis for automatically inferring the direction of the entire paragraph.**

### 11.4. Parentheses

Parentheses can be processed under the Unicode algorithm's bracket-pair rules. Numbers and Latin letters mixed in an RTL sentence can cause parentheses to appear to move or be mirrored during drawing.

`Bidi` supplies levels/runs, while displaying the proper mirrored glyphs and font/rendering details still belongs to the text layout engine. Do not assume `Bidi` has a method that automatically "fixes parentheses" inside a `String`.

## 12. Bidi analysis is not text rendering

This is an important technical boundary:

| Task to perform | Does `java.text.Bidi` solve it directly? |
| --- | --- |
| Determine the base direction of a paragraph | Yes |
| Determine levels and directional run boundaries | Yes |
| Support reordering objects/runs by level | Yes, via `reorderVisually` |
| Choose a font containing Hebrew/Arabic glyphs | No |
| Join Arabic letter forms by context (*shaping*) | No, not a renderer |
| Measure glyph widths for line wrapping | No |
| Draw characters on screen | No |
| Decide left/right alignment of a widget | No |
| Choose the display `Locale` for a user | No |
| Protect against all forms of Unicode spoofing | No |

In a GUI application, rendering systems such as Java2D text layout, Swing, or a UI framework usually provide dedicated processing layers. Depending on the component, you may need UI direction and component orientation properties, text layout, font shaping, and caret behavior.

If the app generates HTML, the corresponding browser-layer mechanisms include `dir`, isolation for mixed-direction content, and related layout properties. Java's `Bidi` does not automatically set `dir` on the DOM; that is the responsibility of the HTML output layer.

**Do not use the result of `getBaseLevel()` as a substitute for all UI layout logic.** An RTL-base paragraph does not necessarily mean every widget is right-aligned, every column swaps sides, or every icon is mirrored. Full RTL design also covers flow layout, control placement, tab order, navigation icons, and accessibility.

## 13. Automatic direction and UI direction: two different decisions

Suppose an application has a Vietnamese UI, yet a user enters an Arabic title. If the content field uses the `DIRECTION_DEFAULT_LEFT_TO_RIGHT` policy, the title's first strong character can cause the paragraph to choose an RTL base. This can be helpful for drawing the sentence.

However:

- **The UI language** can still be Vietnamese.
- **The input content direction** can be RTL.
- **The form's layout direction** can still be LTR.
- **The direction of a technical code inside the sentence** may need LTR isolation.

You should not call `Locale.setDefault` to "flip the whole app's direction" per user. A `Locale` holds language/region information, not a switch replacing bidi controls for every component.

An application needs a clear policy for each field type:

| Data type | Suggested policy |
| --- | --- |
| Free-form prose | Automatic direction by first strong character, fallback by UI context |
| Email address, URL, ID with LTR grammar | Render in an isolated LTR region |
| Translated application labels | Direction according to the label language / screen design |
| Numeric field with minus signs, units | Test in practice against the form's direction |
| Plain text with only symbols | Fallback base direction should be explicitly set rather than guessed |

These examples are **design guidelines**, not mandatory rules for every application. You need to test on your specific framework because widget layout behavior can vary.

## 14. Unicode bidi controls and display safety

Unicode has directional control characters that affect how text is displayed, including:

| Group | Some code points | General role |
| --- | --- | --- |
| Mark | `LRM U+200E`, `RLM U+200F`, `ALM U+061C` | Mark direction in context |
| Embedding/override | `LRE U+202A`, `RLE U+202B`, `LRO U+202D`, `RLO U+202E`, `PDF U+202C` | Legacy embedding/override controls |
| Isolate | `LRI U+2066`, `RLI U+2067`, `FSI U+2068`, `PDI U+2069` | Isolate a directional segment in the Unicode algorithm |

These characters may **not appear as ordinary visible glyphs**, yet still influence visual order. Overrides in particular can make text display in a different order than a reader infers from logical characters.

### Visual spoofing risk

In filenames, log messages, code snippets, or user-supplied content, a bidi control sequence can cause a file extension, punctuation mark, or sentence fragment to be viewed in an unexpected position. This is one of the risks of **visual spoofing** when content looks different from its storage order.

Therefore:

1. **Preserve logical order of data** when storing and transmitting.
2. Do not arbitrarily insert override characters to "fix display."
3. When displaying untrusted content, use appropriate **text isolation or container direction** at the rendering layer.
4. In developer/auditing tools, it may be necessary to reveal or escape control characters when debugging, for instance as `U+202E`.
5. For identifiers with security requirements, explicitly specify which control characters are permitted and enforce it via schema; do not silently allow arbitrary invisible controls.
6. When sanitizing input, do not blindly "strip all bidi control characters" if they are meaningful in valid multilingual text; apply domain-specific policies.

**`Bidi` is not an anti-spoofing API**. Correctly analyzing runs does not prove a message is safe to display in all cases. Systems must combine input validation, isolation, escaping, font/rendering, and displaying non-printable characters where appropriate.

### Isolation vs. override

*Isolate* lets a segment be treated as an independent directional region, limiting unintended impact of its contents on the surrounding context. *Override* forces the directional class of characters within its scope. They have different meanings and cannot be substituted arbitrarily.

In modern UIs, isolation mechanisms at the presentation layer are usually preferable to injecting override characters into source text. On the other hand, Java 17's `Bidi` and the active renderer should be tested with specific modern controls; do not assume every legacy engine implements all UAX #9 versions identically.

## 15. Testing bidi properly

Bidi testing should not rely solely on looking at console stdout text: a terminal may apply its own algorithm, font, and directional context, causing observed order to differ across Windows Terminal, IDEs, and CI.

You can separate three test layers:

### 15.1. Algorithm/metadata unit tests

Verify deterministic values of `Bidi`:

- `getBaseLevel()` for strings starting with Latin, Hebrew/Arabic, and strings of only neutral characters.
- `getRunCount()`, `getRunStart()`, `getRunLimit()`, and `getRunLevel()` on controlled examples.
- `baseIsLeftToRight()` vs. `isLeftToRight()`/`isMixed()`.
- `requiresBidi(...)` for LTR text and RTL text.
- `reorderVisually(...)` with simulated level sets.
- `createLineBidi(...)` when a paragraph wraps into multiple lines.

Do not hardcode detailed level results for arbitrary real-world Unicode strings across every JDK version unless the program pins the corresponding Unicode rules/data set. Simple illustrative cases are useful checkpoints, while production systems also require visual QA.

### 15.2. Renderer integration tests

Test the output of the framework you use with:

- Hebrew/Arabic sentences containing Latin numbers.
- URLs or emails inside an RTL sentence.
- Parentheses around an LTR word inside an RTL sentence.
- Text with multiple spaces and neutral punctuation at both ends.
- Paragraphs wrapped onto two or more lines.
- Cursor/caret, range selection, copy/paste, and screen-reader output.
- Font fallback and glyph shaping for Arabic/Hebrew.
- Content containing bidi controls, including untrusted data.

### 15.3. Data and security tests

Verify:

- Strings after formatting still keep **logical order** when saved/exchanged.
- User-entered text slices are isolated from surrounding formatting text.
- Filenames, domains, IDs, and log messages do not mislead when containing invisible controls.
- Policies for special bidi characters do not accidentally break valid RTL language input.
- Accessibility descriptions and copy/paste are not logically reversed relative to the original data.

Screenshots can be helpful in UI tests, but **do not replace** printing code points or inspecting raw strings when investigating data bugs.

## 16. Common pitfalls

| Pitfall | Why it is wrong | Appropriate approach |
| --- | --- | --- |
| Reversing a `String` to display Hebrew/Arabic | Breaks logical order and nested-direction content | Use bidi-aware text layout |
| Assuming `Bidi` draws text | The class only supplies analysis/reordering info | Use a renderer with shaping/font/layout |
| Equating RTL base with all runs being RTL | Even-level LTR runs can exist inside | Read runs and levels |
| Thinking `DIRECTION_DEFAULT_LEFT_TO_RIGHT` is always LTR | Still inspects the first strong character | Understand fallback applies only when no strong char exists |
| Thinking the first character always decides direction | The start of the string may be a digit/neutral mark | Consider strong characters and context |
| Thinking `isMixed()` means "at least two languages" | Can be mixed when base differs from a single run | Use the API definition and runs |
| Treating run indices as a visual-order string | Run offsets reference logical-order text | Combine levels with a renderer |
| Using `getRunLimit` as an inclusive end offset | Limit is exclusive | Use `substring(start, limit)` |
| Confusing UTF-16 offsets with grapheme counts | Supplementary code points/combining marks differ in length | Convert indices properly |
| Using `Locale` to infer all UI direction | Content and UI language can differ | Maintain an explicit direction policy |
| Manually reversing URLs or numbers in an RTL sentence | Breaks grammar and copy/paste | Isolate the LTR run at the render layer |
| Modifying parentheses in data to "fix" bidi | Can corrupt logical order | Let the layout engine handle mirroring |
| Treating `requiresBidi` as a security check | Only indicates need for bidi analysis | Separate validation/security |
| Adding RLO/LRO to format every line | Increases spoofing risk and unpredictable layout | Prefer isolation/container direction |
| Checking only console stdout | Console can render differently from the UI | Combine metadata tests and visual QA |
| Using `reorderVisually` to reverse characters | The method sorts objects/runs by level | Does not replace shaping/rendering engines |

## 17. Practice exercises

**Exercise 1 — default direction.** Create three `Bidi` instances from `"ABC שלום"`, `"שלום ABC"`, and `"123 - 45"` with `DIRECTION_DEFAULT_LEFT_TO_RIGHT`. Predict the base levels; then switch the neutral string to `DIRECTION_DEFAULT_RIGHT_TO_LEFT` and explain the result.

**Exercise 2 — forced direction.** Using the same `"ABC שלום XYZ"`, create one instance with `DIRECTION_LEFT_TO_RIGHT` and one with `DIRECTION_RIGHT_TO_LEFT`. Compare `getBaseLevel()`, `getRunCount()`, and any levels that change. Why should you not modify the original `String`?

**Exercise 3 — run analysis.** Using the Java example above, record the three `[start, limit)` intervals. Extract each run's text with `substring` and explain level parity. Why is `getRunLimit` not an inclusive index?

**Exercise 4 — pure direction and mixed.** Create all-Latin, all-Hebrew, and mixed strings. Check `isLeftToRight()`, `isRightToLeft()`, `isMixed()`, and `baseIsLeftToRight()`. Explain the case where a paragraph has an LTR base yet is not purely LTR.

**Exercise 5 — reorderVisually.** Given objects `{"A","B","C","D"}` and levels `{0,1,1,0}`, predict the order after `reorderVisually`. Why is this sorting objects by level rather than reversing individual code points?

**Exercise 6 — numbers and URLs.** Design an Arabic label containing a monetary amount and an English URL. Which parts need an RTL base direction, and which parts need LTR isolation? Why shouldn't you simply concatenate strings and add spaces if punctuation lands in the wrong place?

**Exercise 7 — multi-line.** Suppose a paragraph has mixed text and wraps into multiple lines. What information does `createLineBidi` provide for each line? What information is still needed from glyph measurement and line breaking?

**Exercise 8 — security check.** A filename contains `U+202E` or another bidi control. Propose how to display it to users and log it for developers to avoid extension spoofing while still handling valid RTL text properly.

## 18. Conclusion

`java.text.Bidi` performs **Unicode bidirectional analysis** on a paragraph of text, determining base direction, embedding levels, and runs used to lay out mixed LTR/RTL text. Base direction can be specified explicitly or inferred from the first strong character with an appropriate fallback.

**Base direction is not the direction of every character.** Even inside an RTL sentence there can be numbers and LTR Latin runs. `getBaseLevel()`, `getRunLevel()`, and run offsets describe **organization for display**, without mutating the logical order of `String`.

In real applications, keep text in logical order, use a renderer that supports bidi and shaping, isolate embedded opposite-direction content, define UI direction policy separately from locale, and test both metadata and the rendered UI. Do not use string reversal or arbitrary bidi overrides to compensate for layout bugs.

**Rule to remember:** *Bidi analyzes direction for display; data retains logical order; base direction is a baseline, not a command to reverse the entire string.*

### References

- [`java.text.Bidi` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Bidi.html)
- [Unicode Bidirectional Algorithm – UAX #9](https://www.unicode.org/reports/tr9/)
- [Unicode FAQ: Writing Direction and Bidirectional Text](https://www.unicode.org/faq/bidi.html)
