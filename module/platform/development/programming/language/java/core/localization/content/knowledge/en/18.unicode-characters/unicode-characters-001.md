# Unicode, Code Points, UTF-16 Code Units, and User-Perceived Characters in Java

## 1. Why Does a "Character" Not Necessarily Have a Length of 1?

In multilingual text processing, the word **character** can refer to several different concepts. Suppose the screen displays the letter **é**, the emoji **😀**, the flag **🇻🇳**, or the family icon **👩‍👩‍👧‍👦**. Each example may look like a single standalone character to the reader, yet their internal storage and number of Unicode elements are completely different.

In Java, `String.length()` returns the **number of UTF-16 code units**, not the number of code points and certainly not the number of user-perceived characters. Using `length()` as a character count in an input field, or slicing a string with `substring(0, 1)`, can introduce bugs with emojis, combining diacritics, flags, and strings written in complex scripts.

This lesson clarifies three layers:

1. **Unicode code point**: an identifier value in the Unicode code space; for example, the letter `A` is `U+0041`, and the emoji 😀 is `U+1F600`.
2. **UTF-16 code unit**: the 16-bit unit used in `char` and Java string indices; a *supplementary* code point requires **two** consecutive code units.
3. **Grapheme cluster**, close to a *user-perceived character*: a cluster can contain **multiple code points**, such as `e` + combining acute accent or an emoji sequence with joiners.

**Key takeaway:** code units, code points, and grapheme clusters are three different counting units. Choosing a unit must be based on your goal: working with UTF-16 representation, processing Unicode scalars, or editing text that the user perceives as a single unit.

## 2. Overview with Examples

The following table uses Java 17+ and `java.util.regex.Pattern` with the expression `\\X` to count **extended grapheme clusters**:

| Sample string | Interpretation | UTF-16 code units (`length()`) | Code points | Grapheme clusters (`\\X`) |
| --- | --- | ---: | ---: | ---: |
| `A` | Basic Latin letter | 1 | 1 | 1 |
| `é` (U+00E9) | Precomposed accented letter | 1 | 1 | 1 |
| `e\u0301` | `e` + combining acute accent | 2 | 2 | 1 |
| `😀` | Non-BMP emoji | 2 | 1 | 1 |
| `🇻🇳` | Two regional indicators forming a flag | 4 | 2 | 1 |
| `👍🏽` | Emoji + skin tone modifier | 4 | 2 | 1 |
| `👩‍👩‍👧‍👦` | Four emojis + three ZWJs | 11 | 7 | 1 |

The numbers are not interchangeable. For example, with the flag `🇻🇳`:

- **4 code units** because both regional indicators are outside the BMP and each uses a surrogate pair.
- **2 code points** because the flag in the example is encoded with two regional indicators.
- **1 extended grapheme cluster** according to the Unicode segmentation rules applied to a pair of regional indicators.

The family sequence `👩‍👩‍👧‍👦` consists of four emoji code points (each taking two UTF-16 code units) and three *zero-width joiner* characters `U+200D` (each taking one code unit): a total of **11 code units** and **7 code points**, yet it is typically displayed as **one emoji cluster** on systems that support it.

A grapheme cluster is **not guaranteed** to always occupy exactly one monospace character cell, one glyph in a font, or one cursor position in every browser. Rendering output also depends on fonts, operating systems, Unicode versions, shaping engines, and emoji support.

## 3. What Is a Unicode Code Point?

A code point is a numeric value in the range from `U+0000` to `U+10FFFF`. Code points are written in hexadecimal with the `U+` prefix.

Examples:

- `U+0041` — Latin letter `A`.
- `U+0065` — lowercase letter `e`.
- `U+0301` — *combining acute accent*.
- `U+00E9` — precomposed letter `é`.
- `U+1F600` — grinning face emoji 😀.
- `U+200D` — *zero-width joiner* (ZWJ) used to link certain emoji sequences and text presentation.

Not every code point is a visible letter or symbol. There are control code points, combining marks, non-printing characters, unassigned codes, and reserved values.

Within the code point space, the range from `U+D800` to `U+DFFF` is reserved for **surrogate code points**; they are **not** Unicode scalar values that can appear standalone in valid Unicode text. A Unicode scalar value is a code point outside the surrogate range.

Although Unicode assigns a name to many characters by a single code point, a grapheme cluster can consist of multiple code points, and the text rendering process can combine or split glyphs depending on the script and font. You should not define "a visible character" simply as "one code point".

## 4. UTF-16 and Java `char`: Why Does an Emoji Take Two Elements?

UTF-16 encodes:

- Code points in the **Basic Multilingual Plane (BMP)** outside the surrogate range using **one** 16-bit code unit.
- Code points in the range `U+10000` to `U+10FFFF` using **two** code units: a **high surrogate** (`U+D800`–`U+DBFF`) and a **low surrogate** (`U+DC00`–`U+DFFF`).

In Java:

- `char` represents **one UTF-16 code unit**, i.e., a 16-bit value. It **does not always represent a complete code point**.
- `String.length()` counts code units.
- `String.charAt(index)` returns the code unit at a UTF-16 index.
- `String.substring(start, end)` uses **code unit indices**.
- `String.codePointAt(index)` reads the code point at a code unit position, combining a valid surrogate pair when present.
- `String.codePointCount(beginIndex, endIndex)` counts code points in a range of UTF-16 indices.
- `String.offsetByCodePoints(index, codePointOffset)` moves by code points and returns a **code unit index**.

The emoji string 😀 has code point `U+1F600`, which is UTF-16 encoded as:

```text
U+1F600
  -> high surrogate U+D83D
  -> low  surrogate U+DE00
```

Therefore `"😀".length() == 2` even though it is a single code point.

**Do not confuse a UTF-16 code unit with a byte.** A `char` is 16 bits; when serialized to UTF-8, the byte count is different (the emoji 😀 takes 4 UTF-8 bytes). `String.length()` does not measure the byte count of content on the network or in a file.

## 5. Java 17+ Program: Iterating Over Code Points Properly

Create the file `CodePointWalkDemo.java`. So that the program does not depend on typing emojis directly in source code, the example uses Unicode escapes for the surrogate pair:

```java
public class CodePointWalkDemo {
    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B"; // A + 😀 + B

        System.out.println("units=" + text.length()
                + " points="
                + text.codePointCount(0, text.length()));

        for (int index = 0; index < text.length();) {
            int cp = text.codePointAt(index);
            int width = Character.charCount(cp);

            System.out.printf("index=%d U+%X units=%d%n",
                    index, cp, width);
            index += width;
        }

        int end = text.offsetByCodePoints(0, 2);
        System.out.println("first2units="
                + text.substring(0, end).length());
    }
}
```

Save as `CodePointWalkDemo.java`, compile and run with Java 17+:

```bash
javac -encoding UTF-8 CodePointWalkDemo.java
java CodePointWalkDemo
```

Verified stdout:

```text
units=4 points=3
index=0 U+41 units=1
index=1 U+1F600 units=2
index=3 U+42 units=1
first2units=3
```

Reading the output:

- The string `A😀B` has **4 UTF-16 code units**, but **3 code points**.
- The code unit index of `A` is `0`, of 😀 is `1`, and of `B` is `3`.
- `Character.charCount(U+1F600)` equals `2`, so the loop jumps from index `1` to `3`.
- The first two code points are `A` and 😀, yet the slice `substring(0, end)` requires **3 code units**.

If you write `for (int i=0; i<text.length(); i++)` and treat `text.charAt(i)` as an independent Unicode character, the loop will step through both surrogate halves of the emoji. When you need to process code points, use the traversal above or `text.codePoints()`.

**Limitation:** iterating by code point can still split a grapheme cluster into multiple parts. For the string `e\u0301`, the loop will see `e` and `U+0301` as two code points even though the reader typically sees a single letter `é`.

## 6. `charAt`, Surrogate Pairs, and Error-Prone String Slicing

With `String smile = "\uD83D\uDE00";`:

```java
char first = smile.charAt(0);  // high surrogate: U+D83D
char second = smile.charAt(1); // low surrogate:  U+DE00
int whole = smile.codePointAt(0); // U+1F600
```

This is an **illustrative snippet inside a method**, with the variable `smile` declared as at the start of the snippet. You can verify:

```java
Character.isHighSurrogate(first); // true
Character.isLowSurrogate(second); // true
Character.toCodePoint(first, second); // 0x1F600
Character.charCount(whole); // 2
```

The calls above demonstrate the API; these expressions are not a standalone program that prints to stdout.

**Incorrect slicing:**

```java
String broken = smile.substring(0, 1);
```

`broken` contains only the high surrogate, not a complete emoji. A Java string can contain an isolated surrogate code unit, but that is an **invalid UTF-16 string in terms of surrogate pairs for ordinary Unicode text**. When encoded to UTF-8, libraries may replace the invalid part with a replacement character or apply an error policy; you should not rely on any particular display representation.

**Slicing by code point:**

```java
int end = smile.offsetByCodePoints(0, 1);
String complete = smile.substring(0, end);
```

`end == 2`, which preserves the code point 😀. However, if the string is `"e\u0301"`, slicing after one code point still drops the combining acute accent. When operating on "user-perceived characters", you need **grapheme cluster** segmentation, not merely stepping over surrogate pairs.

**Building a string from a code point:** `Character.toChars(0x1F600)` returns two `char` values corresponding to the surrogate pair. `StringBuilder.appendCodePoint(0x1F600)` is the proper way to append a code point without manually computing high/low surrogates. Always validate external data if it might contain lone surrogates.

## 7. `String.codePoints()`: Iterating Over Code Points with a Stream

Since Java 9, `String.codePoints()` returns an `IntStream` iterating over code points. For a segment containing a valid surrogate pair, the stream emits **one `int`** for the entire pair, rather than two numbers for the two `char` values.

Example:

```java
public class CodePointStreamDemo {
    public static void main(String[] args) {
        String s = "A\uD83D\uDE00B";

        s.codePoints()
                .forEach(cp ->
                        System.out.printf("U+%X%n", cp));
    }
}
```

Save as `CodePointStreamDemo.java` and run:

```bash
javac -encoding UTF-8 CodePointStreamDemo.java
java CodePointStreamDemo
```

Stdout:

```text
U+41
U+1F600
U+42
```

Compare with `s.chars()`: the `chars()` stream returns **each UTF-16 code unit** as an `int`; for an emoji, that stream contains the high surrogate and low surrogate separately. The name `chars()` is easily misleading, as it is not equivalent to `codePoints()`.

An `int` code point allows representing values outside the BMP; that is why Java Unicode APIs typically return `int` rather than `char`.

## 8. Grapheme Cluster: The Unit Closest to a "User-Perceived Character"

Unicode defines an algorithm for segmenting into *extended grapheme clusters* (UAX #29) to support many text editing and navigation operations. A grapheme cluster can include:

- A single letter such as `A`.
- A base letter and multiple combining marks: `e` + `U+0301`.
- An emoji and a modifier, such as `👍🏽`.
- A pair of regional indicators forming a flag, such as `🇻🇳`.
- An emoji sequence with *zero-width joiner* `U+200D`, such as the family emoji `👩‍👩‍👧‍👦`.

These components **do not necessarily represent multiple characters in the user's perception**, even though the code point count is greater than 1.

**Key distinctions:**

- **Code point** is a unit of the Unicode coded character model.
- **Grapheme cluster** is a string segmentation unit close to how a person interacts with characters in a UI.
- **Glyph** is the visual shape drawn by a font and text shaping engine. A cluster can be rendered using multiple glyphs or different shapes depending on the system.
- **Terminal display column count**, pixel dimensions, and caret positions **cannot** be inferred directly from the number of extended grapheme clusters.

You can use libraries following UAX #29/CLDR or Java's `\\X` regex for segmentation. For complex UIs, you must test against the actual Unicode/JDK version, fonts, browsers, and real text types.

## 9. Java 17+: Counting Code Units, Code Points, and Graphemes with `\\X`

Java `java.util.regex.Pattern` supports `\\X` as a **Unicode extended grapheme cluster**. The pattern `\\X` matches one cluster as the regex scans through the string; in Java source code you must write `"\\X"` (two backslashes in a string literal) so the regex engine receives the proper symbol.

Create the file `UnicodeCountDemo.java`:

```java
import java.util.regex.Pattern;

public class UnicodeCountDemo {
    public static void main(String[] args) {
        String[] names = {
                "ASCII", "NFC", "NFD", "EMOJI",
                "FLAG", "SKIN", "FAMILY"
        };

        String[] values = {
                "A",
                "\u00E9",
                "e\u0301",
                "\uD83D\uDE00",
                "\uD83C\uDDFB\uD83C\uDDF3",
                "\uD83D\uDC4D\uD83C\uDFFD",
                "\uD83D\uDC69\u200D\uD83D\uDC69\u200D"
                        + "\uD83D\uDC67\u200D\uD83D\uDC66"
        };

        Pattern grapheme = Pattern.compile("\\X");

        for (int i = 0; i < values.length; i++) {
            String s = values[i];
            long clusters = grapheme.matcher(s)
                    .results().count();

            System.out.printf(
                    "%s | units=%d | points=%d | graphemes=%d%n",
                    names[i],
                    s.length(),
                    s.codePointCount(0, s.length()),
                    clusters
            );
        }
    }
}
```

Save `UnicodeCountDemo.java` with UTF-8 and run:

```bash
javac -encoding UTF-8 UnicodeCountDemo.java
java UnicodeCountDemo
```

Stdout confirmed by the JVM:

```text
ASCII | units=1 | points=1 | graphemes=1
NFC | units=1 | points=1 | graphemes=1
NFD | units=2 | points=2 | graphemes=1
EMOJI | units=2 | points=1 | graphemes=1
FLAG | units=4 | points=2 | graphemes=1
SKIN | units=4 | points=2 | graphemes=1
FAMILY | units=11 | points=7 | graphemes=1
```

The names `NFC`/`NFD` here are labels for the precomposed `é` and `e` + combining mark examples, not proof that all strings are automatically normalized.

`Matcher.results()` exists in Java 9+; the code runs on Java 17. A `Pattern` can be reused, whereas `Matcher` is a stateful object created per string. In the example, `grapheme` is compiled once and each loop iteration uses a new matcher.

**Unicode version limitation:** `\\X` relies on the Unicode algorithm supported by the Java runtime. Emoji/grapheme rules are updated across Unicode versions, so newer emoji sequences may exhibit different segmentation behavior across JDKs. Do not assume every environment will always count every new emoji as a single cluster.

## 10. Slicing Strings by Grapheme Cluster Instead of by Code Point

When a UI needs to take the "first user-perceived character", `offsetByCodePoints(0,1)` is insufficient for `e\u0301` or flag emojis. You can obtain cluster boundaries using a matcher for `\\X`:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class FirstGraphemeDemo {
    public static String firstCluster(String input) {
        Matcher matcher = Pattern.compile("\\X")
                .matcher(input);
        return matcher.find() ? matcher.group() : "";
    }

    public static void main(String[] args) {
        String accent = "e\u0301";
        String flag = "\uD83C\uDDFB\uD83C\uDDF3";

        String firstAccent = firstCluster(accent);
        String firstFlag = firstCluster(flag);

        System.out.println(
                "accent units=" + firstAccent.length());
        System.out.println(
                "accent points=" + firstAccent.codePointCount(
                        0, firstAccent.length()));
        System.out.println(
                "flag units=" + firstFlag.length());
        System.out.println(
                "flag points=" + firstFlag.codePointCount(
                        0, firstFlag.length()));
    }
}
```

Run:

```bash
javac -encoding UTF-8 FirstGraphemeDemo.java
java FirstGraphemeDemo
```

Stdout:

```text
accent units=2
accent points=2
flag units=4
flag points=2
```

By taking `matcher.group()`, the program does not sever the acute accent from the letter `e` or split the pair of regional indicators of the flag in these examples.

If you are building an editor, grapheme deletion, caret placement, or input length limiting, you also need to consider handling CRLF, ZWJ, emoji variants, complex scripts, and the actual Unicode configuration. Regex segmentation is a basic step; UI editing also depends on the platform's layout engine.

## 11. Unicode Normalization: Visually Identical Does Not Mean String-Equal

Unicode allows certain text to have **multiple canonically equivalent representations**. The letter `é` is a classic example:

```text
Precomposed: U+00E9            (é)
Decomposed:  U+0065 + U+0301   (e + combining acute accent)
```

These two strings usually look very similar, but Java `String.equals` checks the **sequence of code units**, so they are not equal before normalization.

The `java.text.Normalizer` API supports forms such as `NFC`, `NFD`, `NFKC`, and `NFKD`:

- **NFC** (*Canonical Composition*): normalizes and tends to compose canonical combinations into precomposed forms when possible.
- **NFD** (*Canonical Decomposition*): performs canonical decomposition.
- **NFKC/NFKD** add compatibility transformations and **can alter presentation/semantic distinctions**, so they should not be applied indiscriminately to all data types such as personal names or free-form character content.

### Runnable Example with Normalizer

```java
import java.text.Normalizer;

public class UnicodeNormalizationDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println(
                "equals=" + composed.equals(decomposed));

        String normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println(
                "NFC equals=" + composed.equals(normalized));
        System.out.println("units: "
                + composed.length() + " vs "
                + decomposed.length());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 UnicodeNormalizationDemo.java
java UnicodeNormalizationDemo
```

Stdout:

```text
equals=false
NFC equals=true
units: 1 vs 2
```

Normalization is not transliteration, not language translation, and not a complete security measure against visually similar characters (*confusables*). When you need search, comparison, identifiers, or security handling, design a normalization/case folding/collation policy suited to the data type and target system.

In particular, normalization **does not** mean collapsing every grapheme cluster into a single code point. Flag emojis and many ZWJ emoji sequences still consist of multiple code points after NFC.

## 12. UTF-8 Size Differs from UTF-16 Size

A Java string is indexed by UTF-16 code units, whereas when saving files or transmitting over HTTP, the encoding is typically **UTF-8**. The byte count is completely different from the number of `char` values, code points, or clusters.

Examples:

| String | UTF-16 code units | Code points | UTF-8 byte count |
| --- | ---: | ---: | ---: |
| `A` | 1 | 1 | 1 |
| Precomposed `é` | 1 | 1 | 2 |
| `e\u0301` | 2 | 2 | 3 |
| `😀` | 2 | 1 | 4 |
| `🇻🇳` | 4 | 2 | 8 |

You can verify this in Java:

```java
import java.nio.charset.StandardCharsets;

public class UnicodeBytesDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";
        String emoji = "\uD83D\uDE00";

        System.out.println(
                "NFC bytes=" + composed.getBytes(
                        StandardCharsets.UTF_8).length);
        System.out.println(
                "NFD bytes=" + decomposed.getBytes(
                        StandardCharsets.UTF_8).length);
        System.out.println(
                "EMOJI bytes=" + emoji.getBytes(
                        StandardCharsets.UTF_8).length);
    }
}
```

Save `UnicodeBytesDemo.java`, compile and run:

```bash
javac -encoding UTF-8 UnicodeBytesDemo.java
java UnicodeBytesDemo
```

Stdout:

```text
NFC bytes=2
NFD bytes=3
EMOJI bytes=4
```

Note: UTF-8 is not one byte per code point. For non-ASCII Unicode characters, a code point can require 2 to 4 UTF-8 bytes; basic ASCII requires 1 byte. Byte count depends on the **sequence of code points and the encoding**, not solely on the number of graphemes.

When checking HTTP payload limits, file limits, or database columns with byte limits, measure **bytes in the actual charset**. When checking UTF-16 code unit limits of Java/Google Sheets, use the metric published by the target system. Do not interchange the three counts.

## 13. BreakIterator and Text Segmentation Libraries

Java provides `java.text.BreakIterator.getCharacterInstance(locale)` to find character boundaries for iterating over or editing text. API example:

```java
BreakIterator iterator =
        BreakIterator.getCharacterInstance(locale);
iterator.setText(text);

int start = iterator.first();
for (int end = iterator.next();
        end != BreakIterator.DONE;
        start = end, end = iterator.next()) {
    String segment = text.substring(start, end);
    // Process segment at boundaries returned by BreakIterator.
}
```

This is **illustrative code inside a method**, assuming `locale` is a `java.util.Locale` and `text` is a `String`, with `import java.text.BreakIterator;`. It is not a standalone runnable program.

Both `BreakIterator` and the `\\X` regex aim at text segmentation rules, though details may differ by runtime/provider and Unicode version, especially for newer ZWJ emoji sequences. If a product handles chat, editors, or multi-script input at scale, test the actual behavior of the JDK in use; consider ICU4J or a segmenter tied to a Unicode version controlled by the product.

Do not use `BreakIterator` to infer display width. Terminal columns, glyphs, and caret operations are additional UI concerns.

## 14. Invalid UTF-16 Data and How to Validate It

A Java `String` can contain a lone surrogate, such as just `"\uD83D"`. This is not a valid sequence of Unicode scalar values. APIs such as `codePointAt` or `codePoints()` may still treat the UTF-16 sequence as in-memory data and return the surrogate code unit value when it does not form a valid pair.

Therefore, **`codePointCount` is not a validator for Unicode string validity**. It may count an unpaired surrogate as a single element. When receiving data from potentially faulty sources, validate surrogate pairs or use a decoder with an explicit error-reporting policy.

Example checking whether any code unit is orphaned:

```java
public class SurrogateValidationDemo {
    public static boolean isWellFormedUtf16(String text) {
        for (int i = 0; i < text.length(); i++) {
            char unit = text.charAt(i);

            if (Character.isHighSurrogate(unit)) {
                if (i + 1 >= text.length()
                        || !Character.isLowSurrogate(
                                text.charAt(i + 1))) {
                    return false;
                }
                i++;
            } else if (Character.isLowSurrogate(unit)) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        System.out.println(isWellFormedUtf16("A\uD83D\uDE00B"));
        System.out.println(isWellFormedUtf16("\uD83D"));
    }
}
```

Run:

```bash
javac -encoding UTF-8 SurrogateValidationDemo.java
java SurrogateValidationDemo
```

Stdout:

```text
true
false
```

This function only checks for **well-formed UTF-16 surrogate pairs**. It does not verify that the text is normalized, does not filter control characters, does not validate an allowlist of scripts, and does not detect visually confusable characters. Those policies must be designed separately.

## 15. Error-Prone Operations in Real-World Applications

### 15.1. "Maximum 20 Characters" Limit on an Input Field

You must define what "character" means here:

- If the protocol limits **UTF-8 bytes**, count `getBytes(StandardCharsets.UTF_8).length`.
- If a Java API/constraint limits **UTF-16 code units**, use `String.length()`.
- If the requirement concerns the number of **code points**, use `codePointCount(0, length())`.
- If you want to limit the units **a user can manipulate as a single cluster**, use an appropriate grapheme segmenter; `\\X` can be an option for Java 17+.
- If the UI has a physical width constraint, measure text layout/fonts; do not rely on any of the unit counts above.

Do not declare "20 characters" without clearly defining the counting unit. A family emoji is 11 UTF-16 code units but can be just one grapheme cluster; a UI that counts using `length()` will consume 11/20 of the quota for a single icon.

### 15.2. Deleting One Character from the End of a String

`substring(0, s.length()-1)` deletes **one code unit**, which can leave behind an orphaned surrogate or a combining mark. Deleting one code point via `offsetByCodePoints` avoids splitting a surrogate pair, yet can still split a cluster; an editor's Backspace behavior usually needs to handle grapheme boundaries and platform rules.

### 15.3. Reversing a String

Reversing by raw code units can swap the order of high/low surrogates. `StringBuilder.reverse()` handles preserving valid surrogate pairs, yet **does not guarantee reversing grapheme clusters properly**; letters with combining marks or ZWJ emoji sequences can be reversed into different clusters. Reversing natural text also depends on writing direction, BiDi, and linguistic semantics.

### 15.4. Normalization and Comparison

Two strings that render nearly identically are not guaranteed to return `equals()` true. Use normalization when the problem requires canonical equivalence, but do not turn NFC/NFKC into an automatic system for handling all search, user identification, or protection against Unicode confusable attacks.

### 15.5. Slicing at Byte Boundaries

Avoid slicing UTF-8 bytes in the middle of a multi-byte sequence; if you need to split a payload, preserve code point boundaries when decoding. Still, preserving code point boundaries does not guarantee avoiding splitting a grapheme cluster.

## 16. Common Misconceptions

| Misconception | Reality | Appropriate Approach |
| --- | --- | --- |
| `char` is a complete Unicode character | `char` is a UTF-16 code unit | Use `int` code points when processing scalars |
| `String.length()` is the number of visible letters | It counts UTF-16 code units | Choose code points or graphemes based on the goal |
| `substring(0,1)` always gets the first character | It may take half of a surrogate pair | Use code point/grapheme boundaries |
| Every emoji equals one code point | Flags, modifiers, and ZWJ sequences can have multiple code points | Understand extended grapheme clusters |
| `codePointCount` always counts user characters | Combining marks and ZWJ create multiple code points per cluster | Use `\\X` or a segmentation API |
| UTF-8 bytes and UTF-16 code units are the same | They are two encodings with different sizes | Count bytes when measuring payloads, units when measuring UTF-16 |
| Two visually identical strings have `equals` true | NFC/NFD can have different code unit sequences | Normalize intentionally |
| Regex `\\X` guarantees one glyph/terminal cell | A cluster is not equivalent to layout width | Measure layout if the goal is display |
| `codePointCount` detects invalid surrogates | It can still count isolated surrogate elements | Validate UTF-16 / use a decoder if needed |
| Emojis display identically on every system | Depends on font, Unicode version, and renderer | Test on target platforms |
| Every valid character must fit in the BMP | Supplementary code points are very common | Support surrogate pairs properly |
| `Normalizer` solves all Unicode security issues | It only normalizes according to the chosen form | Apply dedicated security/linguistic policies |

## 17. Testing Checklist

For multilingual string processing code, test at least:

1. **ASCII**: `A`, `abc` — 1 code unit per basic character.
2. **Precomposed accented BMP**: `é` (`U+00E9`) — 1 unit / 1 point / 1 cluster.
3. **Combining mark**: `e\u0301` — 2 units / 2 points / 1 cluster.
4. **Supplementary emoji**: 😀 — 2 units / 1 point / 1 cluster.
5. **Regional indicator flag**: 🇻🇳 — 4 units / 2 points / 1 cluster.
6. **Emoji modifier**: 👍🏽 — 4 units / 2 points / 1 cluster.
7. **ZWJ emoji**: 👩‍👩‍👧‍👦 — 11 units / 7 points / 1 cluster on the tested runtime.
8. **Code point slicing**: `offsetByCodePoints` does not split a surrogate pair in half.
9. **Grapheme slicing**: regex `\\X` does not split `e\u0301` in the example.
10. **Normalization**: NFC of `e\u0301` equals `é`.
11. **Malformed UTF-16**: a lone high surrogate is rejected by validation.
12. **UTF-8 size**: precomposed `é` is 2 bytes, decomposed is 3 bytes, 😀 is 4 bytes.
13. **Version**: test newer emoji clusters on the exact JDK/Unicode version the data will run on.
14. **UI behavior**: caret, Backspace, text selection, and character width are not inferred directly from `String.length()`.

### Practice Exercises

- Write a function that prints each code point of the string `"Chào 😀"` as `U+XXXX`; compare the code unit count with the code point count.
- Write a function `firstCodePoint(String s)` using `offsetByCodePoints`, and `firstGrapheme(String s)` using `Pattern.compile("\\X")`. Test with `"e\u0301"` and a flag emoji, and explain why the results differ.
- Write a validator for a limit of **10 grapheme clusters** and compare its result with a validator limiting **10 UTF-16 code units** on the family emoji.
- Normalize a list of strings with `Normalizer.Form.NFC`, and check `equals` before/after. Explain why using NFKC indiscriminately can alter compatibility forms.
- Try creating a string containing only a high surrogate (`"\uD83D"`) and confirm `isWellFormedUtf16` returns false. Find out why `codePointCount` is not a validator.
- Try counting UTF-8 bytes and code units of the same string containing Vietnamese text, emojis, and combining marks. Decide which limit type fits the UI and the API.
- Build a prototype Backspace button that deletes only one code point, then compare it with Backspace in an editor using grapheme clusters; evaluate cases with combining marks.

## 18. Conclusion

To handle Unicode correctly in Java, you must know which **layer** you are working at:

- `String.length()`, `charAt()`, `substring()`: **UTF-16 code units and code unit indices**.
- `codePointAt()`, `codePointCount()`, `codePoints()`, `offsetByCodePoints()`: **Unicode code points**.
- `Pattern.compile("\\X")` or an appropriate Unicode segmenter: **extended grapheme clusters**, close to the text unit perceived by users.
- `Normalizer`: handles **canonical/compatibility normalization**, not counting or glyph rendering.
- `getBytes(StandardCharsets.UTF_8)`: **encoded byte size**, not character count.

Every counting, slicing, or formatting operation must be tied to the exact business requirement: **memory/serialization length, Unicode processing, or operations on visible text**. Do not use a single counting method for every situation, and do not assume "one code point = one user-perceived character".

## References

- [Oracle Java 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Oracle Java 21 — Character](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html)
- [Oracle Java 21 — Pattern (Unicode grapheme `\\X`)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html)
- [Oracle Java 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html)
- [Oracle Java 21 — BreakIterator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/BreakIterator.html)
- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://www.unicode.org/reports/tr29/)
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://www.unicode.org/reports/tr15/)
