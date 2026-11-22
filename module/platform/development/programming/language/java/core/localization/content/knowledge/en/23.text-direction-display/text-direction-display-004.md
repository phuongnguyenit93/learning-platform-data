# Mixing Left-to-Right, Right-to-Left, Numbers, and Punctuation in Java

A string containing both Vietnamese or English (written **left-to-right**, LTR), Arabic or Hebrew (typically written **right-to-left**, RTL), digits, and punctuation cannot be displayed properly by a rule that "prints each character from left to right." Unicode defines the **Bidirectional Algorithm (UAX #9)** to determine **visual order** from the **logical order** of the source string. In Java, the **java.text.Bidi** class helps analyze base direction, segments sharing the same directional level (runs), and supports laying out bidirectional text; by itself it **does not** replace a text-rendering system, does not curve/join Arabic strokes, and does not reverse or modify `String` content.

Problems especially tend to surface when an RTL sentence mixes in **order codes**, **URLs**, **phone numbers**, **prices**, **colons**, **parentheses**, and **hyphens**. Many punctuation marks are **neutral** (carrying no strong direction), so their visual position depends on surrounding characters and the base direction. Digits have their own bidi rules and are not simply "like LTR" or "like RTL" in every scenario.

This article explains the mechanism, how to apply it in Java 17+, verifiable examples, choosing display direction in UI/web, the difference between directional marks and isolates, data input/output considerations, and safety when handling mixed text.

## 1. Logical order and visual order are two different things

Consider a UI label containing an English word and an Arabic word:

~~~text
Order 123: مرحبا
~~~

In a Java `String`, code points appear in the **logical order** dictated by stored data: **O, r, d, e, r, space, 1, 2, 3, colon, space, the Arabic characters**. The text-rendering engine looks at the paragraph base direction, Unicode bidi classes, and contextual rules to determine the visual order when drawing each segment.

Visual representation cannot be reliably described using a redrawn ASCII string inside Markdown: the browser, terminal, and font viewing the Markdown may run the bidi algorithm themselves an extra time. Therefore **every mixed-text example in this article distinguishes "logical string" from "visual rendering,"** and uses Unicode code points/runs to inspect behavior rather than trying to guess punctuation placement by eye alone.

| Concept | Role |
| --- | --- |
| **Logical order** | The sequence of characters in a `String`, file, JSON, or database |
| **Paragraph base direction** | The LTR or RTL baseline of a paragraph |
| **Bidi class** | The Unicode directional class assigned to each character |
| **Embedding level** | The directional level used when determining visual order; even levels typically correspond to LTR, odd levels to RTL |
| **Directional run** | A contiguous segment assigned the same bidi level by the algorithm |
| **Visual order** | The display order of segments/characters after applying the algorithm |
| **Text shaping** | Selecting glyphs, joining/changing letter forms, especially critical for cursive scripts |
| **Text layout** | Placing glyphs, handling fonts, lines, containers, direction, and line wrapping |

**Consequence:** the order a reader sees does not necessarily match character indices in a Java `String`. When a user places a caret, selects text, or copies, the application must map between logical positions and on-screen positions.

## 2. Typically LTR scripts, RTL scripts, and characters without strong direction

Unicode classifies characters by **bidirectional class**. Some basic categories:

| Group | Unicode Bidi Class | Examples and meaning |
| --- | --- | --- |
| LTR letters | **L** | Latin such as A, B, Vietnamese letters with diacritics |
| RTL letters | **R** | Most Hebrew letters |
| Arabic letters | **AL** | Many Arabic letters, using dedicated RTL rules |
| European digits | **EN** | ASCII 0–9 |
| Arabic-Indic digits | **AN** | Certain digit forms used in Arabic text |
| Whitespace | **WS** | Whitespace separator characters |
| Other neutrals | **ON** | Certain marks/symbols without strong direction |
| Number separators | **ES / CS / ET** | Certain plus, minus, comma, colon, percent, or currency symbols depending on the character |
| Combining marks | **NSM** | Unicode nonspacing marks, usually following the preceding character's context |
| Paragraph/line controls | **B / S** and other classes | Participate in determining paragraph boundaries and handling |

This is a **technical classification**, not a rule table saying "each character always sits on the left/right." For instance, EN digits have multiple rules for interacting with RTL text; a colon is typically a **common separator (CS)**, while parentheses have dedicated bidi and paired-bracket rules. You cannot directly deduce screen position from a single bidi class in isolation.

**Vietnamese data** is LTR, yet a Vietnamese interface can still contain Arabic addresses, Hebrew names, filenames, or international codes. When data contains multiple scripts, a line of text requires bidi layout even if most of the application is LTR.

## 3. Paragraph base direction differs from individual word direction

A paragraph can have an **LTR base direction** yet contain an RTL phrase. Conversely, an RTL sentence can contain an LTR **email, URL, or product code**.

Base direction helps determine the ordering and anchoring of weak/neutral character regions. It can be:

1. Explicitly specified by the display region: a field or paragraph is treated as LTR or RTL.
2. Chosen based on the **first strong character** when using auto-detection mode.
3. Inherited from layout structure if the UI does not specify it individually.

**Do not equate base direction with text alignment.** Right-aligning a box does not necessarily set the bidi algorithm inside that box to RTL. Similarly, picking an Arabic font does not turn a string into a properly ordered RTL paragraph. You must specify the right **text direction** or use a bidi-aware layout system.

In a UI mixing an RTL segment and an LTR order code, treat each semantically distinct piece as an independent directional segment if the platform allows it. Simply adding spaces or changing alignment can still leave punctuation out of place.

### 3.1. Automatic direction detection has limits

**Default LTR** mode does not mean forcing every character to LTR. It typically searches for a strong directional character to pick the base direction; if no qualifying strong character exists, it falls back to LTR.

For example, a paragraph starting with digits **123:** followed by an RTL word. The digit sequence is not a strong LTR character like the letter A, so auto-detected base direction can be governed by the RTL word that follows. This is why a UI holding all-numeric identifiers should not rely blindly on "the first visible character" to decide direction.

## 4. Numbers do not simply run backward in RTL

In RTL text, digits like **12345** normally still keep an internal order readable as a number (they do not turn into **54321** just because the sentence reads right to left). However, the position of **the entire numeric group** relative to words, minus signs, currency symbols, and separators can vary by context.

Examples of data to test:

~~~text
Code: 123-45
Invoice #2026-10
Phone: +84 901 234 567
USD 1,250.50
رقم 123
~~~

They contain different kinds of marks and groups:

- **Hyphenated codes:** the minus/hyphen may be interpreted by the algorithm in a numeric or punctuation context.
- **Phone numbers:** plus signs, spaces, parentheses, and digit sequences often need to be treated as a dedicated LTR data component.
- **Dates and times:** slashes, colons, and prefix characters sit adjacent to digits and RTL letters.
- **Currency:** currency symbols, decimal points, and grouping separators can involve both locale and bidi rules.
- **Technical identifiers:** colons/hyphens may belong to an ID string rather than sentence prose.

**Do not reverse individual digits.** If receiving the string **12345** from machine data, that value must keep its logical order inside the `String`. Display belongs to bidi layout, not calling **new StringBuilder(text).reverse()**.

### 4.1. Western digits and Arabic digits are not identical

Unicode distinguishes **European Number (EN)** and **Arabic Number (AN)** along with several related classes. **Locale** can govern which digit set `NumberFormat` or `DateTimeFormatter` renders, yet **locale-based number formatting** and **bidi ordering** are two separate stages/aspects.

For example:

- **NumberFormat** can produce numbers with grouping separators or localized digits.
- **Bidi layout** decides where that number group is placed inside a sentence containing RTL.
- **The font/text renderer** decides glyphs, stroke joining, and final appearance.

If an app formats a number under an Arabic locale and inserts it into an English paragraph, the direction of the whole paragraph still has to be considered. Do not assume `NumberFormat` handles all of bidi automatically.

## 5. Punctuation and parentheses are where display bugs happen most often

A mixed sentence like:

~~~text
Status (مرحبا): 123
~~~

has Latin letters, parentheses, an RTL word, a colon, and digits. Parentheses are not strong LTR/RTL letters; the Unicode Bidirectional Algorithm has rules for neutrals and paired brackets to decide how they are drawn. Thus parentheses can be displayed in an orientation or glyph-mirrored form suited to the bidi level.

**Distinguish three things:**

1. **Character order:** opening and closing parentheses remain characters at their logical positions in the `String`.
2. **Bidi reordering:** on-screen positions of segments and characters shift due to the algorithm.
3. **Glyph mirroring:** certain symbols like parentheses may select a symmetric glyph when in an RTL direction.

**You must not use String.replace('(', ')')** to "fix" parentheses in an RTL segment. That corrupts the original data and breaks again if the content is displayed in another directional context.

Punctuation such as **:**, **;**, **,**, **.**, **-**, parentheses, and spaces can end up in positions readers do not expect if a mixed segment is placed in a region with the wrong base direction. Test with **complete sentences**, not only isolated RTL words.

### 5.1. Minus signs and hyphens play different roles

The **-** character can be a minus sign on a number, a connector in a product code, or a dash in a sentence. The bidi algorithm classifies by character and context, yet does not understand the business meaning of an order code or arithmetic expression.

For technical elements like **INV-2026-12**, keep a single logical string and place it in a region with an explicit direction per the display contract, rather than relying on surrounding RTL sentence punctuation to guess its placement.

## 6. Java 17: checking bidi class with Character

**Character.getDirectionality(int codePoint)** returns a directional constant for a Unicode code point, for example:

- **Character.DIRECTIONALITY_LEFT_TO_RIGHT**.
- **Character.DIRECTIONALITY_RIGHT_TO_LEFT**.
- **Character.DIRECTIONALITY_RIGHT_TO_LEFT_ARABIC**.
- **Character.DIRECTIONALITY_EUROPEAN_NUMBER**.
- **Character.DIRECTIONALITY_ARABIC_NUMBER**.
- **Character.DIRECTIONALITY_COMMON_NUMBER_SEPARATOR**.
- **Character.DIRECTIONALITY_OTHER_NEUTRALS**.

This is helpful when debugging mixed strings. However, **a code point's directionality is not its final screen position**: the full string and base direction are needed to run the Unicode Bidirectional Algorithm.

**File DirectionalityKinds.java**

~~~java
public class DirectionalityKinds {
    public static void main(String[] args) {
        System.out.println("latin="
                + (Character.getDirectionality('A')
                == Character.DIRECTIONALITY_LEFT_TO_RIGHT));

        System.out.println("arabic="
                + (Character.getDirectionality('\u0645')
                == Character.DIRECTIONALITY_RIGHT_TO_LEFT_ARABIC));

        System.out.println("digit="
                + (Character.getDirectionality('1')
                == Character.DIRECTIONALITY_EUROPEAN_NUMBER));

        System.out.println("colon="
                + (Character.getDirectionality(':')
                == Character.DIRECTIONALITY_COMMON_NUMBER_SEPARATOR));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 DirectionalityKinds.java
java DirectionalityKinds
~~~

Stdout with Java 17:

~~~text
latin=true
arabic=true
digit=true
colon=true
~~~

These compare against API constants so they illustrate bidi classes independently of how the terminal draws Arabic letters. For instance, the colon belongs to the common number separator class in Unicode data, which does not mean "a colon always sticks to the right" in every sentence.

**When handling non-BMP data**, pass an `int` code point to `getDirectionality`; do not iterate by **`char`** where you might accidentally split a surrogate pair.

## 7. java.text.Bidi handles multi-directional paragraphs

The **java.text.Bidi** class provides character/paragraph-level bidi analysis based on Unicode data and base direction. It offers constructors and APIs:

| API | Purpose |
| --- | --- |
| **new Bidi(String paragraph, int flags)** | Create a bidi analyzer for a string |
| **Bidi.DIRECTION_LEFT_TO_RIGHT** | Explicit LTR base direction hint |
| **Bidi.DIRECTION_RIGHT_TO_LEFT** | Explicit RTL base direction hint |
| **Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT** | Detect strong direction; fall back to LTR if none |
| **Bidi.DIRECTION_DEFAULT_RIGHT_TO_LEFT** | Detect strong direction; fall back to RTL if none |
| **baseIsLeftToRight()** | Query whether the selected base direction is LTR |
| **getBaseLevel()** | Get the paragraph's base embedding level |
| **getRunCount()** | Number of runs under the current analysis |
| **getRunStart(int run)** | Logical start index of the numbered run |
| **getRunLimit(int run)** | Logical index immediately after the end of the run |
| **getRunLevel(int run)** | Embedding level of the run |
| **getLength()** | Length of the input segment managed by `Bidi` |
| **requiresBidi(char[], start, limit)** | Preliminary check whether a data slice needs bidi processing |
| **createLineBidi(int start, int limit)** | Create an analysis for a sub-line |
| **reorderVisually(...)** | Order run objects according to the supplied levels |

**Do not assume getRunCount equals word count or script count.** Punctuation and digits can introduce run boundaries at positions that do not match word boundaries. Run count, run positions, and levels are outputs of the whole string, base direction, and runtime algorithm.

### 7.1. Java example verifying base direction and bidi requirement

**File BidiBasics.java**

~~~java
import java.text.Bidi;

public class BidiBasics {
    public static void main(String[] args) {
        String english = "Hello";
        String arabic = "\u0645\u0631\u062D\u0628\u0627";
        String mixed = "Ticket 123: " + arabic;

        Bidi ltr = new Bidi(
                english, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);
        Bidi rtl = new Bidi(
                arabic, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

        System.out.println(
                "english-ltr=" + ltr.baseIsLeftToRight());
        System.out.println(
                "arabic-ltr=" + rtl.baseIsLeftToRight());

        char[] chars = mixed.toCharArray();
        System.out.println(
                "mixed-requires-bidi="
                + Bidi.requiresBidi(chars, 0, chars.length));

        System.out.println(
                "logical-prefix=" + mixed.substring(0, 6));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 BidiBasics.java
java BidiBasics
~~~

Stdout:

~~~text
english-ltr=true
arabic-ltr=false
mixed-requires-bidi=true
logical-prefix=Ticket
~~~

The program avoids printing a mixed line as "proof" of visual order, because **terminals and log viewers can apply different bidi rules from the production UI**. Instead, it proves:

- A purely Latin segment is given an LTR base.
- A purely Arabic segment has an RTL base direction, even when choosing the "default-left-to-right" flag because that flag checks strong characters.
- A mixed segment contains characters needing bidi processing.
- **substring** still reads the input `String`'s logical order accurately.

**Bidi.requiresBidi** is a technical check, not a validator determining whether content is Arabic/Hebrew or whether a sentence must be right-aligned. An RTL string needs directional handling even when the overall UI is LTR.

## 8. Run analysis and logical index mapping

When writing a custom text viewer, we need to know the runs in a paragraph:

~~~java
Bidi bidi = new Bidi(
        mixed, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

for (int run = 0; run < bidi.getRunCount(); run++) {
    int begin = bidi.getRunStart(run);
    int end = bidi.getRunLimit(run);
    int level = bidi.getRunLevel(run);

    String logicalPart = mixed.substring(begin, end);
    System.out.println(
            "run=" + run
            + ", logical=[" + begin + "," + end + ")"
            + ", level=" + level
            + ", utf16Length=" + logicalPart.length());
}
~~~

This snippet is **illustrative**, requiring **`import java.text.Bidi`** and a **`String mixed`** variable. Printed run counts/levels depend on the string and runtime Unicode data, so a fixed stdout is not prescribed here.

Note carefully:

1. **start/limit** indices are positions in the input string in **UTF-16 units**.
2. **limit** is an **exclusive** end index.
3. The order of runs in visual layout differs from the order of substrings in the `String`, depending on levels.
4. Runs do not yet include glyph shaping or pixel coordinates; they are solely bidi analysis data.
5. A **non-BMP emoji** can take two `char`s; do not split a surrogate pair when handling custom text ranges.
6. For text editors, click/hit-testing positions need mappings supplied by the layout engine rather than inferring from **run index** yourself.

**Bidi.reorderVisually** sorts an array of objects according to supplied levels. It **does not draw glyphs itself**, does not split/combine marks, and does not handle Arabic shaping or fonts. When rendering is needed, use a layout system that supports text shaping such as the corresponding UI/text component.

## 9. Why not reverse RTL strings yourself?

An error-prone approach:

~~~java
String wrong =
        new StringBuilder(userText).reverse().toString();
~~~

This is an illustrative snippet inside a method with variable **`String userText`**. **StringBuilder.reverse** changes the order of logical string elements according to its own algorithm, without running UAX #9 and without knowing which parts are LTR/RTL, punctuation, or digits that should preserve internal order.

Bugs that can arise:

- Phone numbers, product codes, and IDs have their digits reversed.
- English words inside an Arabic sentence have their letters reversed.
- Parentheses can be misplaced and processed a second time by the renderer.
- Combining marks and grapheme clusters may no longer attach properly to their base letters.
- Copied text becomes different data from the original.
- The same string renders reversed differently between terminal and web.

**Store strings in logical order; let the text layout engine decide visual order.** If a protocol format with a specific byte sequence is required, it must be explicitly specified and not depend on how it "looks" on screen.

## 10. Non-printing directional marks: LRM, RLM, and ALM

Certain Unicode characters influence the bidi algorithm while usually having no visible glyph:

| Code point | Name | General purpose |
| --- | --- | --- |
| **U+200E** | LEFT-TO-RIGHT MARK (**LRM**) | Invisible strong LTR mark |
| **U+200F** | RIGHT-TO-LEFT MARK (**RLM**) | Invisible strong RTL mark |
| **U+061C** | ARABIC LETTER MARK (**ALM**) | Arabic-specific directional mark |
| **U+202A** | LEFT-TO-RIGHT EMBEDDING (**LRE**) | LTR embedding control (legacy mechanism) |
| **U+202B** | RIGHT-TO-LEFT EMBEDDING (**RLE**) | RTL embedding control (legacy mechanism) |
| **U+202C** | POP DIRECTIONAL FORMATTING (**PDF**) | Terminate certain embeddings/overrides |
| **U+202D** | LEFT-TO-RIGHT OVERRIDE (**LRO**) | Force directional interpretation inside |
| **U+202E** | RIGHT-TO-LEFT OVERRIDE (**RLO**) | Force directional interpretation inside |

**LRM/RLM/ALM** can help weak/neutral marks anchor on the right side in a mixed sentence. However, **do not insert these marks into every string arbitrarily**: they change display behavior, can cause surprises during copy/paste, and make raw `String` comparisons differ.

Legacy **embedding/override** forms are powerful tools but easily cause bugs if unclosed or improperly nested. In particular, **RLO/LRO** can make segments appear reversed even though logical content differs; this is why untrusted input text must be treated with caution.

**Prefer structural tools of the display platform** (such as HTML **`bdi`** and text component direction) instead of mixing directional controls into source data purely to prettify the UI.

## 11. Isolates: LRI, RLI, FSI, and PDI

Modern bidi isolation lets a text region determine its own direction with less impact on punctuation and content outside the region than legacy embedding forms.

| Code point | Name | Purpose |
| --- | --- | --- |
| **U+2066** | LEFT-TO-RIGHT ISOLATE (**LRI**) | Open an LTR isolate region |
| **U+2067** | RIGHT-TO-LEFT ISOLATE (**RLI**) | Open an RTL isolate region |
| **U+2068** | FIRST STRONG ISOLATE (**FSI**) | Choose direction from the first strong character in the region |
| **U+2069** | POP DIRECTIONAL ISOLATE (**PDI**) | Close an isolate region |

A logical model:

~~~text
Application-controlled sentence
   + [start isolate] + user-supplied content + [end isolate]
   + remaining punctuation/sentence from the application
~~~

For sentences containing a username of unknown language, isolation helps limit inserted content from pulling outer sentence punctuation out of place. **This is layout**, not a security mechanism against all malicious inputs.

### 11.1. Creating strings with FSI/PDI in Java

~~~java
String userLabel = "\u0645\u0631\u062D\u0628\u0627";
String isolated = "\u2068" + userLabel + "\u2069";
~~~

This is an illustrative snippet inside a method. String **`isolated`** wraps the content with **FSI** and **PDI**. However, **support for displaying these controls depends on the renderer and Unicode bidi version**. Do not assume every terminal, Java component, or string-processing API supports isolates identically to a modern browser. Test on the target display platform.

If the UI already supports structured direction/isolation regions, using that feature is usually preferable to storing FSI/PDI inside a database username column. Keeping raw data makes searching, comparison, and auditing easier to control.

## 12. HTML: dir and bdi in mixed-direction interfaces

When a Java backend generates text for a web UI, browsers natively handle Unicode bidi and CSS/layout. For example:

~~~html
<p dir="ltr">
  Sender: <bdi dir="auto">مرحبا</bdi> (code 123-45)
</p>
~~~

**Note:** this HTML example illustrates the principle and is not Java syntax. **dir="ltr"** sets the paragraph's base direction, while **bdi dir="auto"** isolates the sender's name and automatically determines the content's direction. Code **123-45** may need its own LTR region if punctuation placement is affected in a particular layout.

With CSS properties, you may encounter:

~~~css
.message-label {
    direction: rtl;
    unicode-bidi: isolate;
}
~~~

This CSS snippet illustrates setting direction/isolation. However, CSS **direction** is not synonymous with **text-align**. Using only **text-align: right** to fix an RTL field is insufficient.

Pay special attention to untrusted user content: you must **HTML-escape** text when putting it into the DOM, using safe templating or `textContent` equivalents. **`bdi`** handles display direction, not XSS escaping. For interpolated strings containing usernames, both **injection protection** and **bidi boundary protection** must be considered.

## 13. Rich text, Swing, JavaFX, and terminals are not the same renderer

On the JVM, a text segment's path can look like:

~~~text
Java String (logical order)
       |
       +-> Console / log viewer
       |
       +-> Swing / Java2D text layout
       |
       +-> JavaFX text layout
       |
       +-> HTML/browser or mobile client
       |
       +-> File/JSON API
~~~

Each environment has its own renderer and shaping/bidi support. **java.text.Bidi** can supply analysis information, yet does not make renderers behave identically by itself.

- **Console:** may depend on terminal, font, viewport, and bidirectional rendering support. Do not use terminal screenshots to conclusively verify bidi ordering.
- **Swing/Java2D:** use text layout components/engines suited for international text rather than computing character positions manually.
- **JavaFX:** explicitly configure nodes, component directionality, and actual text layout support.
- **Browser:** prefer semantic HTML, **dir**, and **bdi**, or platform-provided text-direction APIs.
- **File/JSON:** usually needs to **preserve logical order**, not convert into "visual order" before saving.

**Do not normalize rendering by reversing Strings in the backend.** The same payload might render right on the web yet wrong in a console; the fix belongs in the rendering layer, not silently mutating protocol data.

## 14. Distinguishing bidi from Arabic shaping

Bidi and shaping are related but not identical:

1. **Bidi:** determines visual order and directional levels of segments.
2. **Shaping:** determines glyph shapes, stroke joining, and mark/glyph placement suited to the script.
3. **Font fallback:** selecting a font that contains the required glyphs.
4. **Line breaking:** determining line-wrap points, which can affect per-line bidi computation.

Arabic requires different letter forms depending on position within a word. If a program only uses **Bidi.reorderVisually** and draws raw characters individually, Arabic letters can appear disconnected or malformed. Only a text renderer supporting shaping handles this completely.

Similarly, accented Vietnamese text and scripts with many combining marks require proper mark/glyph placement logic. **java.text.Bidi is not a diacritic-attaching/glyph-shaping library**.

## 15. Locale and text direction are related yet separate concepts

A **Locale** such as `ar` or `he-IL` can hint at a language/region that commonly uses RTL scripts, yet **does not** replace analyzing the string itself. An Arabic message can contain numerous Latin words and digits; an English app can quote Hebrew text.

Example:

~~~java
Locale locale = Locale.forLanguageTag("ar");
NumberFormat price = NumberFormat.getCurrencyInstance(locale);
String amount = price.format(1234.5);
~~~

This snippet is illustrative inside a method, requiring imports for **`Locale`** and **`NumberFormat`**. It creates a currency string following locale rules supported by the runtime. Yet when inserting that string into a sentence mixing LTR and RTL, **base direction, punctuation, and isolation remain the responsibility of the display layer**.

Therefore:

| Question | Where to resolve it? |
| --- | --- |
| Which comma or decimal separator to use? | `NumberFormat`/`DecimalFormatSymbols`/`Locale` |
| Which day/month names to use? | `DateTimeFormatter`/`Locale` |
| Which translated text to use? | `ResourceBundle`/i18n system |
| Is the sentence LTR or RTL? | Paragraph/UI text direction, Unicode bidi |
| Which side do parentheses/colons land on? | Bidi resolution in context |
| Do Arabic letters join strokes properly? | Font/text shaping |
| How are ID values stored? | Data contract, keeping logical order |

An application cannot answer every one of these questions using a single locale variable.

## 16. Bidi and invisible Unicode characters: how to debug

If a string "looks right yet compares unequal" or "punctuation jumps around," print code points instead of only logging mixed text directly.

**File BidiCodePoints.java**

~~~java
import java.util.Locale;

public class BidiCodePoints {
    private static void dump(String text) {
        text.codePoints().forEach(cp ->
                System.out.printf(
                        Locale.ROOT, "U+%04X%n", cp));
    }

    public static void main(String[] args) {
        String text = "A" + "\u200F" + ":123";
        dump(text);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 BidiCodePoints.java
java BidiCodePoints
~~~

Stdout:

~~~text
U+0041
U+200F
U+003A
U+0031
U+0032
U+0033
~~~

**U+200F** is RLM, which has no normal visible glyph. Using **String.codePoints()** helps detect its presence and other controls in data.

**String.length()** counts UTF-16 code units, while **codePoints()** treats valid surrogate pairs as single code points. When debugging offsets from **Bidi.getRunStart/getRunLimit**, do not arbitrarily convert between code point counts and `String` indices.

### 16.1. Copy/paste bugs

Users may copy a name from a UI: the copied logical string may or may not contain marks/isolates depending on the UI component. A system using regex to detect unwanted characters must recognize that format characters like `U+200F` can appear intentionally in international text.

**Do not blindly strip all "zero width" or direction marks when saving every kind of text.** Doing so can alter valid content in certain languages. For technical identifier fields, you can enforce a strict character set, provided the input contract is stated clearly.

## 17. Security: strings can display differently from logical order

Bidi override characters can make code, filenames, extensions, or identifiers **look different from their logical order**. This is a security/anti-spoofing issue, often associated with **Trojan Source** attacks or disguised filenames.

Different surfaces must be protected appropriately:

- **Source code/review:** enable warnings or highlight unwanted bidi control characters, especially LRO/RLO and unbalanced controls.
- **Filenames/attachments:** display the true extension based on structured metadata, not merely a visually rendered string that might be visually reordered.
- **Identifiers, URLs, emails:** do not rely on visible character order to judge equality; follow parsing/normalization/security contracts.
- **Logs/audits:** consider recording code points or escaping control characters in diagnostic mode so investigators are not misled by rendering.
- **Natural text:** still support valid RTL; do not blindly ban entire scripts or marks.

**Do not treat the presence of RTL characters as malicious behavior.** Arabic/Hebrew text is completely normal; the goal is distinguishing **untrusted data contexts** from **controls that alter visual appearance** on sensitive surfaces.

### 17.1. Bidi does not replace escaping or validation

If embedding content in HTML, escape HTML; if using SQL, parameterize queries; if handling filenames, validate paths and filesystem rules. **Bidi isolation** only limits display-direction influence and does not address injection, path traversal, or access control.

In addition, using **Normalizer.NFKC** to sanitize characters does not by itself solve bidi security. Unicode normalization and the Unicode Bidirectional Algorithm address two distinct scopes.

## 18. When to use marks, and when to use isolates?

Some practical guidelines:

| Scenario | Approach |
| --- | --- |
| Web UI with an RTL person name in an LTR sentence | Use **`bdi dir=auto`** for user content |
| LTR-structured product code/URL inside an RTL sentence | Use an explicit LTR region or UI-level isolation |
| A complete RTL-directed sentence | Set RTL base direction on the container |
| Terminal shows odd punctuation | Check code points and renderer capability; do not reverse `String` |
| Stored technical fields | Keep logical value, define input validation |
| Sensitive text containing Unicode controls | Show warnings/escapes in audits |
| Need a single mark to adjust punctuation at a specific spot | Add LRM/RLM/ALM only after testing on the target renderer |
| Need to separate context between two untrusted segments | Prefer isolation at the layout layer |
| Need Arabic glyph shaping/joining | Use text shaping, not `Bidi` alone |

**Why prefer isolates?** They treat a text region as a scoped component, limiting the effect of inner content on outer text. Still, do not claim isolation is an "absolute security lock": you still must test renderers, untrusted data, and nested bidi controls.

## 19. Common mistakes

### Mistake 1: Reversing a String with reverse() to "fix" RTL

Reversing breaks logical order and corrupts URLs, IDs, and numbers. Let Unicode bidi layout determine visual order.

### Mistake 2: Treating RTL as reversing all digits

Digit groups follow their own rules. **123** does not mean it becomes **321** when inside an Arabic sentence.

### Mistake 3: Right-aligning without setting base direction

**text-align:right** affects alignment only and is insufficient for bidi ordering. Proper direction/paragraph orientation is needed.

### Mistake 4: Replacing '(' with ')' yourself in RTL

Glyph mirroring and bracket layout are the renderer's job. Mutating data corrupts the original and easily backfires.

### Mistake 5: Thinking Character.getDirectionality returns visual order

It only gives the code point's bidi class. Display order depends on the entire paragraph, punctuation, base direction, and controls.

### Mistake 6: Thinking java.text.Bidi draws Arabic letters by itself

`Bidi` handles directional analysis, not fonts/shaping; a text layout engine is required.

### Mistake 7: Injecting U+200E/U+200F into every person's name

Invisible marks alter the string and can make copy/paste unpredictable. Prefer UI-layer isolation when available.

### Mistake 8: Forgetting punctuation outside a dynamic RTL string

An RTL name concatenated directly with a colon can affect punctuation placement outside the name. Isolate the dynamic name region rather than endlessly tweaking spaces.

### Mistake 9: Using Locale as a substitute for specifying direction

`Locale` selects localized data; it does not automatically fix every `String`'s direction when rendered. Both locale and UI base direction are needed.

### Mistake 10: Testing only in a terminal

Terminals can render bidi differently from browsers/apps. Test on the real renderer with target fonts and languages.

### Mistake 11: Slicing substrings by visible character direction

`String` offsets are in logical order; on-screen click/caret positions are a separate matter. Use layout/hit-testing APIs rather than doing index arithmetic manually.

### Mistake 12: Stripping all invisible characters for "security"

Some marks/controls serve valid textual roles. Build policies by data category; technical codes can be stricter than natural prose.

### Mistake 13: Relying on rendered images to compare account codes

Bidi can change visual placement without altering the underlying `String`. Identifiers must rely on their defined data representation.

### Mistake 14: Failing to test minus signs, product codes, and currency

Punctuation and numbers are where bidi bugs surface easily. Test realistic strings containing `123-45`, `12:30`, phone numbers, currency codes, and parentheses.

## 20. Recommended test matrix

| Scenario | What to verify |
| --- | --- |
| Pure Latin letters | LTR base, no reversal errors |
| Pure Arabic/Hebrew letters | Proper RTL base when auto-detected or explicit |
| Latin text + Arabic name | Punctuation sits on the right side for the context |
| RTL segment + **12345** | Internal digit order preserved |
| RTL segment + **INV-2026-12** | Technical code displays and copies correctly |
| Phone number **+84 ...** in an RTL sentence | Plus sign/parentheses do not shift improperly |
| Price with grouping/decimal separators | Locale formatting combines properly with bidi layout |
| Parentheses wrapping an RTL name | Proper position/paired-bracket mirroring |
| Heading with dynamic name **bdi dir=auto** | Name region does not pull outer punctuation |
| No strong characters | Consistent fallback direction |
| U+200E/U+200F/U+061C | Display/diagnostic strategy in place |
| U+2066/U+2067/U+2068/U+2069 | Renderer supports isolation properly |
| U+202E or other overrides in sensitive input | Audit warning/escaping present |
| Cursive Arabic text | Shaping and font fallback work |
| Copy/paste from UI | Logical order and controls handled intentionally |
| Non-BMP Unicode/emoji | No split surrogate pairs, valid caret/hit testing |
| Vietnamese UI with RTL names | Do not assume Vietnamese locale alone suffices |
| Browser, app, and terminal | Renderer differences understood |

### 20.1. Functional tests and visual tests

**Functional tests (deterministic):** verify code points, specified base direction, unchanged original `String`, ID data, and properties of the `Bidi` API. No specific font is required.

**Rendering tests:** visually inspect on supported platforms, ideally with reference screenshots or manual review by someone fluent in the target language. Test LTR/RTL regions, font fallback, punctuation, long lines, and wrapping.

**Do not make terminal stdout your sole golden test** for Unicode bidi. Operating systems, terminals, and browsers can use different renderers; a string printed to the console in logical order may still be drawn differently.

### 20.2. Data-preservation tests

When taking a label from the database to the UI and letting users copy it back, verify that:

1. Technical code values do not have characters reversed.
2. LRM/RLM/FSI/PDI are not added to source data if they belong only to the UI layer.
3. Parentheses and colons remain in their logical positions.
4. Saved values do not depend on font or `text-align`.
5. Intentional directional characters in natural prose follow an explicit policy.
6. When exporting JSON/APIs, Unicode strings retain their data structure rather than outputting synthesized "visual order."

## 21. Java 17+ implementation checklist for mixed content

- [ ] Distinguish `String` **logical order** from renderer **visual order**.
- [ ] Know bidi classes **L, R, AL, EN, AN, NSM, neutral**.
- [ ] Choose an appropriate base direction; do not treat text alignment as paragraph direction.
- [ ] Use **java.text.Bidi** to inspect base level and runs when directional analysis is needed.
- [ ] Do not treat **Bidi** as a font-shaping engine.
- [ ] Do not reverse Strings or manually swap parentheses for RTL.
- [ ] Keep numbers/IDs/URLs in logical order; specify display-region direction.
- [ ] Check punctuation and spaces at boundaries between LTR and RTL.
- [ ] Understand LRM, RLM, ALM, and bidi controls, using them only for clear reasons.
- [ ] Prefer structured isolation regions when embedding person names/dynamic content.
- [ ] For the web, consider **dir=auto**, **bdi**, and semantic markup.
- [ ] HTML-escape untrusted content; bidi does not replace injection defense.
- [ ] Use **String.codePoints()** when investigating invisible characters.
- [ ] Distinguish Locale-formatted numbers from bidi-laid-out numbers.
- [ ] Test on a real renderer with supported fonts and languages.
- [ ] Preserve source strings for storage/APIs/audits; never emit reversed "visual strings."
- [ ] Have a policy against misleading bidi controls in source code, filenames, and identifiers.
- [ ] Do not strip valid RTL text solely because it contains marks or another language.

## 22. Conclusion

Mixing LTR, RTL, numbers, and punctuation is a problem of the **Unicode Bidirectional Algorithm and text layout**, not manually reordering characters. **Java `String` data should be kept in logical order**; base direction, bidi classes, runs, and isolation help the renderer present content on screen in the right context. In Java 17+, **Character.getDirectionality** lets you inspect a code point's directional class, while **java.text.Bidi** lets you analyze bidirectional paragraphs, levels, and runs; viewing Arabic properly also requires fonts and text shaping.

For interfaces, set the right direction on containers and isolate dynamic segments/technical identifiers where needed, testing parentheses, colons, phone numbers, and currency values. For data, do not reverse strings, do not inject invisible controls arbitrarily, and do not equate visual appearance with data identity. By combining code point tests with renderer tests, a multilingual Java application can both preserve data integrity and display LTR/RTL segments naturally, legibly, and more safely.
