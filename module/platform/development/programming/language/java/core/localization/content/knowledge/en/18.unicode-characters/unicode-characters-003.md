# Surrogate Pairs and Non-BMP Characters in Java

## 1. Why Does a "Character" Sometimes Take Two `char`s?

During localization, a Java application must handle Vietnamese, Japanese, Arabic, mathematical symbols, emojis, and many other scripts. A common mistake is assuming that **every Unicode character always corresponds to one `char` in Java**. That is incorrect.

Java `String` uses **UTF-16** representation. For a Unicode code point in the region commonly known as the **BMP** (Basic Multilingual Plane), it can be represented by **one UTF-16 code unit**. However, many code points **outside the BMP** require **two code units**, called a **surrogate pair**.

Examples:

- `A` is U+0041: one UTF-16 code unit.
- `中` is U+4E2D: one UTF-16 code unit.
- `😀` is U+1F600: **two** UTF-16 code units.
- `𐐷` is U+10437: **two** UTF-16 code units.

Therefore:

```java
String text = "A\uD83D\uDE00\u4E2D"; // A😀中
System.out.println(text.length()); // 4
```

There are **three Unicode code points**, yet `String.length()` returns **4** because it returns the number of **UTF-16 code units**, not the number of characters visible on screen.

This lesson covers Unicode structure, how UTF-16 uses surrogate pairs, Java 17 APIs for handling code points, risks when slicing/iterating strings, converting to UTF-8, checking for malformed surrogates, and the difference between a code point and a **grapheme cluster** (a user-perceived character).

## 2. Key Vocabulary: Code Point, Code Unit, BMP, and Grapheme

| Concept | Meaning | Example |
| --- | --- | --- |
| **Unicode code point** | A numeric position from U+0000 to U+10FFFF in the Unicode code space | `U+1F600` |
| **Unicode scalar value** | A code point **not** in the surrogate range U+D800–U+DFFF | `U+0041`, `U+1F600` |
| **BMP** | Plane 0, from U+0000 to U+FFFF | `A`, `中`, `é` |
| **Supplementary planes** | Planes 1–16, from U+10000 to U+10FFFF | `😀`, `𐐷` |
| **UTF-16 code unit** | A 16-bit unit of the UTF-16 representation | Java `char` |
| **Surrogate pair** | A high surrogate + low surrogate pair representing one supplementary code point | `\uD83D\uDE00` = U+1F600 |
| **Grapheme cluster** | A cluster of code points typically perceived by users as one character | `e` + combining mark `◌́`; composite emoji |
| **UTF-8 code unit** | One byte in a UTF-8 encoded sequence | Emoji U+1F600 encodes to 4 bytes |

**Distinguishing "code point" from "scalar value":** Unicode includes the surrogate positions U+D800–U+DFFF, yet they are not valid for standalone use as text characters. Thus **not every number in the code point range is a scalar value**. `Character.isValidCodePoint(int)` only checks the range U+0000–U+10FFFF and **does not exclude surrogate code points**; checking for a scalar value also requires excluding U+D800–U+DFFF.

Another point: even "one code point" does not necessarily equal "one letter" perceived by a user. For instance, `e\u0301` consists of the letter `e` and the combining acute accent U+0301—**two code points**—yet usually displays as a single letter `é`. A family emoji can consist of multiple code points joined by a zero width joiner (ZWJ) yet display as a single icon.

In most Unicode string processing, we must clearly answer whether we are counting **UTF-16 units**, **code points**, or **grapheme clusters**.

## 3. BMP and Non-BMP Characters

Unicode divides the code space into 17 planes (plane 0 through 16), each with up to 65,536 code positions. The BMP is plane 0, from U+0000 to U+FFFF. Supplementary planes run from U+10000 to U+10FFFF.

Examples:

| Character | Code point | Plane region | UTF-16 code units |
| --- | --- | --- | ---: |
| `A` | U+0041 | BMP | 1 |
| `Đ` | U+0110 | BMP | 1 |
| `中` | U+4E2D | BMP | 1 |
| `€` | U+20AC | BMP | 1 |
| `😀` | U+1F600 | Non-BMP | 2 |
| `🚀` | U+1F680 | Non-BMP | 2 |
| `𐐷` | U+10437 | Non-BMP | 2 |

**Do not confuse BMP with ASCII:** ASCII is only a small subset of the BMP. Most accented Vietnamese letters in precomposed form still belong to the BMP, yet that **does not guarantee** every Vietnamese letter is always one code point: a character can exist in decomposed form such as base letter + combining mark.

**Do not equate non-BMP characters with emojis:** emojis are a visible example, yet many historic scripts, musical symbols, mathematical symbols, and rare characters also belong to the supplementary planes. Meanwhile, some characters participating in emojis lie inside the BMP; emoji rendering also depends on variation selectors and ZWJ sequences.

## 4. How Does UTF-16 Encode Supplementary Code Points Using Surrogate Pairs?

A supplementary code point `U` in the range U+10000–U+10FFFF is represented by two code units:

1. Subtract `0x10000` to obtain `U'` in the range `0x00000` to `0xFFFFF` (20 bits).
2. Add the upper 10 bits to `0xD800` to form the **high surrogate** (U+D800–U+DBFF).
3. Add the lower 10 bits to `0xDC00` to form the **low surrogate** (U+DC00–U+DFFF).

Formula:

```text
U' = U - 0x10000

high = 0xD800 + (U' >> 10)
low  = 0xDC00 + (U' & 0x3FF)

U = 0x10000
    + ((high - 0xD800) << 10)
    + (low - 0xDC00)
```

Example with `😀` (U+1F600):

```text
U  = 0x1F600
U' = 0x0F600

high = 0xD800 + (0x0F600 >> 10) = 0xD83D
low  = 0xDC00 + (0x0F600 & 0x3FF) = 0xDE00

UTF-16 = D83D DE00
```

A high surrogate does **not** independently represent the character `😀`; neither does a low surrogate. Only the **properly ordered pair** constitutes a supplementary code point. A UTF-16 string with an unmatched high surrogate or an isolated low surrogate is **ill-formed UTF-16**, even though a Java `String` can still hold such a `char`.

Validity conditions for a pair:

- First code unit in `0xD800..0xDBFF`.
- Second code unit in `0xDC00..0xDFFF`.
- Do not reverse their order and do not split them when slicing strings, storing fragments, or passing across another encoding layer.

### What Is Java `char`?

`char` is an unsigned 16-bit value representing **one UTF-16 code unit**, not "an arbitrary Unicode character":

```java
char letter = 'A';            // U+0041: one code unit
char high = '\uD83D';         // high surrogate of 😀
char low = '\uDE00';          // low surrogate of 😀
int emoji = 0x1F600;          // Unicode code point
```

A supplementary code point cannot fit completely in **one** `char`. When you need to represent a code point, use `int` or `String`.

## 5. Java APIs You Must Know

| API | Unit / result | Key notes |
| --- | --- | --- |
| `s.length()` | Number of UTF-16 code units | Not the number of Unicode code points |
| `s.charAt(index)` | One `char`/UTF-16 code unit | May return half of a surrogate pair |
| `s.codePointAt(index)` | `int` code point starting at UTF-16 index | If pointing to the high surrogate of a valid pair, returns the non-BMP code point |
| `s.codePointBefore(index)` | Code point immediately before UTF-16 index | `index` is the position after the character to read |
| `s.codePointCount(begin, end)` | Counts code points in a range of UTF-16 indices | Does not count grapheme clusters |
| `s.offsetByCodePoints(index, offset)` | Converts a number of code point steps to a UTF-16 index | Useful for slicing by code point |
| `s.codePoints()` | `IntStream` of code points | Not a stream of `char`s |
| `s.chars()` | `IntStream` of code units widened to int | Produces two elements for an emoji |
| `Character.charCount(cp)` | 1 or 2 UTF-16 units for the code point | Helps increment indices properly |
| `Character.isHighSurrogate(c)` | Checks for high surrogate | Insufficient to verify a pair without the next character |
| `Character.isLowSurrogate(c)` | Checks for low surrogate | Requires checking the preceding position |
| `Character.isSurrogatePair(high, low)` | Checks a pair of two code units | Can be combined with `toCodePoint` |
| `Character.toCodePoint(high, low)` | Combines a pair into an `int` code point | Ensure the pair is valid before calling |
| `Character.toChars(cp)` | Converts a code point into 1–2 `char`s | Not itself a Unicode scalar validator |
| `StringBuilder.appendCodePoint(cp)` | Appends the UTF-16 representation of a code point | More convenient than casting to `char` |

**Note on indices:** `String.indexOf(int codePoint)` can search for supplementary code points as well, yet the **returned index is still a UTF-16 index**. `substring(begin, end)` likewise takes UTF-16 indices, not code point ordinals.

### 5.1. `codePointAt` Requires the Correct Index

For the string `"A😀中"`:

```text
UTF-16 index:       0        1        2        3
code unit:         0041     D83D     DE00     4E2D
                  ('A')    (high)   (low)    ('中')

Code points:       U+0041   U+1F600          U+4E2D
```

- `s.codePointAt(1)` returns `0x1F600` when encountering a valid high + low pair.
- `s.charAt(1)` returns only `0xD83D`.
- `s.charAt(2)` returns only `0xDE00`.
- `s.codePointAt(2)` starts at the **low surrogate**, so it sees an isolated surrogate code and **does not look backward to return U+1F600**. That is why you should always traverse along **valid code point boundaries**, rather than arbitrarily incrementing the index by one `char` and calling `codePointAt`.

## 6. Standalone Java 17 Example: Counting UTF-16 Units and Code Points

Create the file `SurrogatePairDemo.java`:

```java
import java.util.Locale;

public class SurrogatePairDemo {
    public static void main(String[] args) {
        // A + 😀 + 中. Escapes prevent source from depending on editor fonts.
        String text = "A\uD83D\uDE00\u4E2D";

        System.out.println("utf16Units=" + text.length());
        System.out.println("codePoints=" +
                text.codePointCount(0, text.length()));
        System.out.println("highAt1=" +
                Character.isHighSurrogate(text.charAt(1)));
        System.out.println("lowAt2=" +
                Character.isLowSurrogate(text.charAt(2)));

        System.out.printf(
                Locale.ROOT,
                "codePointAt1=U+%04X%n",
                text.codePointAt(1));
        System.out.printf(
                Locale.ROOT,
                "charAt2=U+%04X%n",
                (int) text.charAt(2));

        System.out.println("afterTwoCodePoints=" +
                text.offsetByCodePoints(0, 2));
        System.out.println("emojiUtf16Units=" +
                Character.toChars(0x1F600).length);
    }
}
```

Compile and run on JDK 17+:

```bash
javac -encoding UTF-8 SurrogatePairDemo.java
java SurrogatePairDemo
```

Exact stdout:

```text
utf16Units=4
codePoints=3
highAt1=true
lowAt2=true
codePointAt1=U+1F600
charAt2=U+DE00
afterTwoCodePoints=3
emojiUtf16Units=2
```

Explanation:

- `A` occupies one unit, `😀` two units, `中` one unit → total **4**.
- There are three code points → `codePointCount` equals **3**.
- The emoji starts at UTF-16 index **1**, occupying indices **1 and 2**.
- After **two code points** from index 0 (A and 😀), the next position is UTF-16 index **3**.
- `Character.toChars(0x1F600)` returns a `char[]` of length 2; you cannot squeeze the whole emoji into one `char`.

A note for learners: in Java source, the escape sequence `\uD83D\uDE00` is translated by Java into a paired set of two `char`s. They still describe **one** valid Unicode code point when read properly via code-point-aware APIs.

## 7. Iterating Strings: Why Is a `charAt(i++)` Loop Not Enough?

A simple approach that is **semantically wrong** if the goal is per code point:

```java
for (int i = 0; i < text.length(); i++) {
    char c = text.charAt(i);
    // For an emoji, the loop sees high and low surrogates separately.
}
```

This is an illustrative snippet with `text` provided externally. It is not automatically a bug if the business logic genuinely wants to iterate over **UTF-16 units**, yet it is a bug when trying to count "Unicode characters", check `Character.isLetter` on non-BMP characters, or process each visible character.

### 7.1. Iterating by Code Point

```java
for (int i = 0; i < text.length(); ) {
    int cp = text.codePointAt(i);
    // Process the complete code point here.
    i += Character.charCount(cp);
}
```

The index `i` remains a UTF-16 index. When `cp` is outside the BMP, `Character.charCount(cp)` equals 2, skipping over the whole pair. For BMP, it increments by 1.

### 7.2. Runnable Java 17 Example: Iterating and Printing Code Points

File `CodePointIterationDemo.java`:

```java
import java.util.Locale;
import java.util.stream.Collectors;

public class CodePointIterationDemo {
    public static void main(String[] args) {
        String text = "A\uD83D\uDE00\u4E2D";

        for (int i = 0; i < text.length(); ) {
            int cp = text.codePointAt(i);
            System.out.printf(
                    Locale.ROOT,
                    "utf16Index=%d codePoint=U+%04X%n", i, cp);
            i += Character.charCount(cp);
        }

        String values = text.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(", "));

        System.out.println("stream=" + values);
        System.out.println("unitsStream=" + text.chars().count());
        System.out.println("pointsStream=" + text.codePoints().count());
    }
}
```

```bash
javac -encoding UTF-8 CodePointIterationDemo.java
java CodePointIterationDemo
```

Stdout:

```text
utf16Index=0 codePoint=U+0041
utf16Index=1 codePoint=U+1F600
utf16Index=3 codePoint=U+4E2D
stream=U+0041, U+1F600, U+4E2D
unitsStream=4
pointsStream=3
```

**`chars()` and `codePoints()` differ:** `chars()` feeds each UTF-16 code unit into an `IntStream`, whereas `codePoints()` combines valid surrogate pairs into a single `int` element. When you need to call `Character.isLetter(int)`, `Character.isDigit(int)`, or analyze Unicode properties, prefer code points rather than forcing a non-BMP character into a `char`.

**Limitation:** `codePoints()` does not automatically turn an **ill-formed** UTF-16 string into a valid one. For an unpaired surrogate, the stream may still contain that surrogate value as an `int`; applications receiving untrusted data must validate separately.

## 8. Slicing Strings: Two Different Kinds of "Safe"

When calling `substring(begin, end)`, Java interprets `begin` and `end` as **UTF-16 indices**. It does not guarantee that the start and end cuts land on valid code point boundaries. Example:

```text
"A😀B"
UTF-16: A | HIGH | LOW | B
index:  0     1     2    3  (end=4)
```

Calling `text.substring(0, 2)` keeps `A` and **only the high surrogate**, leaving the resulting string no longer well-formed UTF-16. Although Java does not necessarily throw an exception, the string can suffer character substitution, encoding errors, or replacement character display in other systems.

### 8.1. Slicing Exactly N Code Points

If you want the **first N code points**, use `offsetByCodePoints`:

```java
int endUtf16 = text.offsetByCodePoints(0, n);
String prefix = text.substring(0, endUtf16);
```

This snippet belongs inside a method with valid `text` and `n`. You must verify `n` is between 0 and `codePointCount`; if exceeded, `offsetByCodePoints` can throw `IndexOutOfBoundsException`.

### 8.2. Slicing by a UTF-16 Budget Without Splitting a Surrogate Pair

Some storage systems or protocols limit length in **UTF-16 units**, such as 30,000 units/fragment. When forced to slice by capacity, check the boundary of the two units at the cut point. If the end of a fragment is a **high surrogate** and the start of the remainder is a **low surrogate**, decrement end by one unit to move the **entire pair** into the next fragment.

Note: this provides only **code point** safety, **not yet** **grapheme cluster** safety (ZWJ emojis or combining marks).

### Java 17 Example: Comparing Broken and Safe Slicing

File `SafeSliceDemo.java`:

```java
public class SafeSliceDemo {
    static String prefixByUtf16Budget(String text, int maxUnits) {
        if (maxUnits < 0) {
            throw new IllegalArgumentException("Negative budget");
        }

        int end = Math.min(text.length(), maxUnits);

        if (end > 0 && end < text.length()
                && Character.isHighSurrogate(text.charAt(end - 1))
                && Character.isLowSurrogate(text.charAt(end))) {
            end--; // Push the whole pair to the next part.
        }

        return text.substring(0, end);
    }

    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B";

        String broken = text.substring(0, 2);
        String safe = prefixByUtf16Budget(text, 2);
        String firstTwoPoints = text.substring(
                0, text.offsetByCodePoints(0, 2));

        System.out.println("brokenHighAtEnd=" +
                Character.isHighSurrogate(
                        broken.charAt(broken.length() - 1)));
        System.out.println("safeUnits=" + safe.length());
        System.out.println("safePoints=" +
                safe.codePointCount(0, safe.length()));
        System.out.println("twoPointsUnits=" +
                firstTwoPoints.length());
        System.out.println("twoPointsCount=" +
                firstTwoPoints.codePointCount(0, firstTwoPoints.length()));
    }
}
```

```bash
javac -encoding UTF-8 SafeSliceDemo.java
java SafeSliceDemo
```

Stdout:

```text
brokenHighAtEnd=true
safeUnits=1
safePoints=1
twoPointsUnits=3
twoPointsCount=2
```

- `broken` is `A` plus a **lone high surrogate**; `substring` does not report an error on its own.
- `safe` keeps only `A` because a budget of 2 UTF-16 units cannot fit `A` (1) **and** `😀` (2).
- `firstTwoPoints` consists of `A😀` and occupies **3** UTF-16 units, because it slices by code point count rather than by a 2-unit budget.

If you write a general fragment-splitting function by `maxUnits`, you must also handle the case where the budget is too small to hold the next code point (e.g., `maxUnits=1` when the next section starts with an emoji). Avoid an infinite loop when the cut point decrements back to the fragment's start; fail with an error or change the budget policy.

## 9. UTF-8, UTF-16, and Length Counting

UTF-8 and UTF-16 are **two ways to encode the same Unicode scalar values**, using different units:

- UTF-8 represents each scalar value with **1–4 bytes**.
- UTF-16 represents each scalar value with **1 or 2 16-bit code units**, typically corresponding to 2 or 4 bytes when serialized as actual UTF-16 data.
- Java `String.length()` counts **the string's code units**, not bytes when outputting UTF-8.
- `String.getBytes(StandardCharsets.UTF_8).length` counts **bytes after UTF-8 encoding**, which usually differs from `String.length()` and the code point count.

Example `😀`:

| Metric | Value |
| --- | --- |
| Unicode code point | `U+1F600` |
| UTF-16 code units in Java String | 2 |
| UTF-16 high/low | `D83D DE00` |
| UTF-8 bytes | `F0 9F 98 80` |
| UTF-8 byte count | 4 |
| Grapheme cluster count of this single emoji | 1 |

### Standalone Java 17 Example: UTF-8 Bytes of an Emoji

File `Utf8VsUtf16Demo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class Utf8VsUtf16Demo {
    public static void main(String[] args) {
        String emoji = new String(Character.toChars(0x1F600));
        byte[] utf8 = emoji.getBytes(StandardCharsets.UTF_8);

        StringBuilder hex = new StringBuilder();
        for (byte b : utf8) {
            if (hex.length() > 0) {
                hex.append(' ');
            }
            hex.append(String.format(
                    Locale.ROOT, "%02X", Byte.toUnsignedInt(b)));
        }

        System.out.println("utf16Units=" + emoji.length());
        System.out.println("codePoints=" +
                emoji.codePointCount(0, emoji.length()));
        System.out.println("utf8Bytes=" + utf8.length);
        System.out.println("utf8Hex=" + hex);
    }
}
```

```bash
javac -encoding UTF-8 Utf8VsUtf16Demo.java
java Utf8VsUtf16Demo
```

Stdout:

```text
utf16Units=2
codePoints=1
utf8Bytes=4
utf8Hex=F0 9F 98 80
```

Do not use `String.length()` to estimate UTF-8 payload size. Conversely, if a system specifies a limit in UTF-16 units, do not use UTF-8 byte length to decide where to slice.

When passing JSON across platforms, document the length-counting protocol: JavaScript `String.length` typically counts UTF-16 units like Java, whereas many other languages and libraries have different Unicode code point or byte semantics. **The data contract must state the unit of measurement.**

## 10. Unpaired Surrogates: `String` Can Hold Them, Yet the Text Is Invalid

A Java `String` can contain a lone high surrogate:

```java
String invalid = "\uD83D";
```

`invalid.length()` is still 1; Java does not automatically reject ill-formed strings upon object creation. However, a lone surrogate **does not represent a valid Unicode scalar value**, and converting it to UTF-8, JSON, XML, logs, or passing it to another library can cause errors or replacement characters.

**Do not treat `Character.isValidCodePoint(0xD83D)` as a valid scalar check**, because it only checks the code point range, and U+D83D is inside the surrogate range. If you need to verify that UTF-16 text has valid pairs, check the high/low ordering:

```text
If a high surrogate is encountered:
  The next character must be a low surrogate.
  Skip both and continue.
If a low surrogate is encountered without an immediately preceding high:
  The string is not well-formed.
Other BMP chars:
  Accept.
```

### Java 17 Example: Reporting an Error When Encoding a Lone Surrogate

File `MalformedUtf16Demo.java`:

```java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class MalformedUtf16Demo {
    static boolean isWellFormedUtf16(String s) {
        for (int i = 0; i < s.length(); i++) {
            char ch = s.charAt(i);

            if (Character.isHighSurrogate(ch)) {
                if (i + 1 >= s.length()
                        || !Character.isLowSurrogate(s.charAt(i + 1))) {
                    return false;
                }
                i++; // Two units make one code point.
            } else if (Character.isLowSurrogate(ch)) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        String valid = "\uD83D\uDE00";
        String loneHigh = "\uD83D";

        System.out.println("validPair=" +
                isWellFormedUtf16(valid));
        System.out.println("loneHighWellFormed=" +
                isWellFormedUtf16(loneHigh));

        boolean rejected = false;
        try {
            StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(loneHigh));
        } catch (CharacterCodingException ex) {
            rejected = true;
        }

        System.out.println("encoderRejected=" + rejected);
    }
}
```

```bash
javac -encoding UTF-8 MalformedUtf16Demo.java
java MalformedUtf16Demo
```

Stdout:

```text
validPair=true
loneHighWellFormed=false
encoderRejected=true
```

Here `CharsetEncoder` is configured with `CodingErrorAction.REPORT`, so it reports an error upon encountering a lone surrogate. Some convenience encoding APIs may use a **replacement** character instead of throwing an exception; to prevent silent data loss, choose an explicit encoding strategy and validate before sending.

Do not silently replace all lone surrogates with `?` in systems requiring data integrity; design a policy to reject, normalize, or sanitize input at trusted boundaries.

## 11. Code Point Does NOT Equal Grapheme Cluster

This is a very important distinction for localization.

### 11.1. Letters with Combining Marks

Two strings can display identically:

```text
precomposed: "é"      U+00E9
decomposed:  "e◌́"     U+0065 U+0301
```

In decomposed form, this is **two code points** and two UTF-16 units, yet users typically read it as **one letter**. If an input limit allows 10 "visible characters", `codePointCount` is not enough to compute the grapheme cluster count properly.

In Vietnamese, an accented syllable can use a precomposed code point or a sequence of combining marks. Search, validation, and comparison systems should not assume all text is already Unicode-normalized.

### 11.2. Composite Emojis and Variation Selectors

For instance, an emoji of a person with skin tone, a national flag, and a family emoji can consist of multiple code points:

- A symbol combining an **emoji modifier** (skin tone) can form one grapheme cluster.
- A flag consists of two **regional indicator** code points forming a flag image in many environments.
- A family emoji can use **ZWJ** U+200D to join multiple people into one cluster.
- A character can be accompanied by **variation selector** U+FE0F to request emoji-style presentation.

An algorithm that merely avoids "splitting between a surrogate pair" can still split between a person and a modifier, between the two regional indicators of a flag, or between the ZWJ components of a family. The UTF-16 result is **still well-formed**, yet it **displays incorrectly or differently from intended**.

### 11.3. Java Support for Grapheme Handling

Java 17 regex `java.util.regex.Pattern` supports `\X` for a **Unicode extended grapheme cluster**. Example:

File `GraphemeDemo.java`:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GraphemeDemo {
    public static void main(String[] args) {
        String text = "e\u0301";

        int count = 0;
        Matcher matcher = Pattern.compile("\\X").matcher(text);
        while (matcher.find()) {
            count++;
        }

        System.out.println("utf16Units=" + text.length());
        System.out.println("codePoints=" +
                text.codePointCount(0, text.length()));
        System.out.println("graphemes=" + count);
    }
}
```

```bash
javac -encoding UTF-8 GraphemeDemo.java
java GraphemeDemo
```

Stdout:

```text
utf16Units=2
codePoints=2
graphemes=1
```

Notice `graphemes=1`: `e` and the combining mark are one cluster. `BreakIterator.getCharacterInstance(locale)` is another API for locale-aware character boundaries, though segmentation details and support for newer emojis can vary across Unicode versions/data. For strict UI requirements, test on the exact Java version and real Unicode data of the product.

**A grapheme cluster is still not guaranteed to equal "one user-understood character":** complex scripts, cursor experience, font shaping, and text ordering have additional rules. When handling caret movement, backspace, or message truncation, use a segmenter/library compatible with UI requirements and test with native users.

## 12. Unicode Normalization Is Not Surrogate Processing

`java.text.Normalizer` supports Unicode normalization forms such as `NFC`, `NFD`, `NFKC`, and `NFKD`. Normalization addresses canonical/compatibility equivalent representations of **sequences of code points**, **not** a substitute for handling surrogate pairs.

Example:

```java
String combined = "\u00E9"; // precomposed é
String split = "e\u0301";    // e + combining acute accent

boolean equalBefore = combined.equals(split); // false
String normalized = java.text.Normalizer.normalize(
        split, java.text.Normalizer.Form.NFC);
boolean equalAfter = combined.equals(normalized); // true
```

This is an illustrative snippet inside a method. Two strings can look alike, yet `String.equals` compares code units and does not automatically perform canonical equivalence. `NFC` normalization is often useful for text matching, though it must follow a contract (for passwords, signatures, and identifiers, normalization may have special rules).

Do not use `Normalizer` to "fix" an unpaired surrogate, and do not confuse normalization with charset conversion. Each problem has a different scope.

## 13. Handling Indices, Search, and Safe String Operations

### `String.indexOf(int codePoint)`

You can call:

```java
int emojiIndex = text.indexOf(0x1F600);
```

It searches for the code point `😀` yet returns a **UTF-16 index**. For `"A😀中"`, the result is 1. If you use `text.indexOf('\uD83D')`, you are searching for the **high surrogate code unit** rather than the emoji code point; that can match half of a pair or a malformed surrogate.

### `String.substring`

Start and end indices are UTF-16 indices. Always slice on **code point boundaries** if the string requires well-formed UTF-16, or on **grapheme boundaries** if the operation is user-facing.

### `StringBuilder.reverse()`

Java's `StringBuilder.reverse()` includes logic for handling **valid surrogate pairs** so it does not blindly reverse the two halves of an emoji char-by-char. However, it **does not guarantee** preserving the meaning of **grapheme clusters**, combining marks, ZWJ emojis, or natural language text order. Do not treat reversing code units as accurately "reversing visible letters".

### `String.toUpperCase(Locale)` / `toLowerCase(Locale)`

A case mapping operation can **change string length** (some characters become multiple code points) and follow locale rules. After changing case, do not reuse old UTF-16 indices or code-point offsets without rechecking.

### Comparison and Length

- `String.equals` / `compareTo` do not automatically apply canonical normalization or linguistic collation.
- `String.length()` is UTF-16 length; `codePointCount` is code point count; regex `\X` relates to grapheme clusters.
- For natural-language search/sorting, consider `java.text.Collator` or ICU per policy, instead of code unit order comparison.
- Payload byte limits, DB length, and "user-entered character count" must be **three separately stated requirements**.

## 14. API Design, Storage, and Testing

### 14.1. State Limit Units Explicitly

An unclear contract:

```text
username maxLength = 20
```

Developers might interpret that as 20 bytes, 20 UTF-16 units, 20 code points, or 20 grapheme clusters. Better to specify clearly:

```text
username maximum: 20 Unicode grapheme clusters
storage limit: measured separately in UTF-8 bytes
normalization: NFC before comparison
reject ill-formed UTF-16 input
```

This is a policy example; individual products may choose different limits. Do not blindly apply every constraint above to names or passwords; security and UX policies must decide individually.

If storing in a DB with `VARCHAR(n)`, do not assume all DBs/encodings count the same unit. Different DBs and collations have different semantics; check the actual database and connector documentation.

### 14.2. Data Leaving the JVM

When outputting JSON, UTF-8, XML, or transmitting over HTTP, keep charset and validation consistent:

1. Validate well-formed strings if data is untrusted or risks containing lone surrogates.
2. Only format/encode at the boundary using the declared charset, typically UTF-8 for JSON/HTTP.
3. Do not store the two surrogate halves in two separate fields or unrelated fragments if downstream requires well-formed Unicode strings.
4. If forced to split fragments by UTF-16 capacity, avoid boundaries **between high and low surrogates** and preserve order when reassembling.
5. Do not use byte length as code-point length. When truncating UI text, consider both grapheme clusters and rendering issues.
6. When sources have differing Unicode normalization, check canonical equivalence per policy instead of just visual appearance.

### 14.3. Real-World Scenario: 30,000 UTF-16 Unit Fragment Limit

Suppose you have a long `String content` and a per-fragment limit of `maxUnits=30000`. Minimum safe splitting algorithm:

```text
start = 0
while start < content.length():
    end = min(start + maxUnits, content.length())
    if end < content.length()
       and content[end-1] is HIGH surrogate
       and content[end] is LOW surrogate:
        end = end - 1
    if end <= start:
        fail: one complete code point cannot fit
    save content.substring(start, end)
    start = end
```

The condition here preserves surrogate pairs. Afterward, join fragments **without adding any separator** to reconstruct the exact original string. If there is also a requirement not to split grapheme clusters, a more advanced segmentation algorithm is needed and an earlier cut point may have to be chosen.

**An important note:** the algorithm does not turn ill-formed content into well-formed content. If the original string already contains an unpaired surrogate, preserving boundaries of valid pairs **is not enough**; validate the source data first.

### 14.4. Minimum Test Suite

| Test case | Expectation |
| --- | --- |
| `"A"` | UTF-16 units = 1, code points = 1 |
| `"中"` | Units = 1, code points = 1 |
| `"😀"` | Units = 2, code points = 1 |
| `"A😀中"` | Units = 4, code points = 3 |
| `"e\u0301"` | Units = 2, code points = 2, graphemes = 1 |
| `"A😀B"` truncated at 2 UTF-16 units | Does not retain half a surrogate; safe prefix `"A"` |
| Lone high surrogate | Rejected by validation / REPORT encoder |
| Lone low surrogate | Rejected by validation |
| High + high + low | First high is an error; do not mis-pair |
| Valid high + low | `codePointAt` and `toCodePoint` return the right code point |
| ZWJ emojis and emoji modifiers | Do not use `codePointCount` as grapheme count |
| Split/join fragments | Exact UTF-16 unit concatenation without losing or adding characters |
| NFC/NFD | Comparison follows normalization policy |
| Convert to UTF-8 | Accurate byte count and round-trip for well-formed UTF-16 |

### 14.5. Standalone Exercises on Surrogates and Code Points

**Exercise 1.** For `s = "X😀Y"`, what are `s.length()` and `s.codePointCount(0, s.length())`?

**Answer:** 4 UTF-16 units, 3 code points (X = 1, emoji = 2, Y = 1).

**Exercise 2.** Why is `s.charAt(1)` not `😀`?

**Answer:** `charAt` returns only one UTF-16 code unit. At index 1 is the emoji's high surrogate, which must be combined with the low surrogate at index 2.

**Exercise 3.** Given high `0xD83D` and low `0xDE00`, what is the code point?

**Answer:** U+1F600. You can use `Character.toCodePoint((char)0xD83D, (char)0xDE00)` after validating the pair.

**Exercise 4.** What problem does `substring(0, 2)` on `"A😀B"` cause?

**Answer:** End index 2 falls in the middle of the pair; the result retains the high surrogate without the low surrogate, making the string ill-formed UTF-16.

**Exercise 5.** `"e\u0301"` has `codePointCount=2`. Do users necessarily see two letters?

**Answer:** No. This is one grapheme cluster that usually displays as the letter é; code points differ from grapheme clusters.

**Exercise 6.** The emoji `😀` has two UTF-16 units and four UTF-8 bytes. If an API limits to 10 characters, is using `String.length()` always right?

**Answer:** Only right if the contract actually defines "character" as UTF-16 units. If the limit is code points, grapheme clusters, or bytes, the corresponding measurement must be used.

**Exercise 7.** When is `Character.isValidCodePoint(cp)` insufficient to confirm `cp` is a Unicode scalar value?

**Answer:** When `cp` lies in U+D800–U+DFFF. These are surrogate code points (within the Unicode code point range), yet cannot be used standalone as scalar values.

**Exercise 8.** A family emoji has 7 code points yet usually renders as one icon. What can happen if you slice after 3 code points?

**Answer:** It can split the ZWJ sequence and cause the emoji to break apart or lose its intended meaning even without splitting a surrogate pair. For UI operations, grapheme segmentation is needed.

## 15. Common Errors and Misconceptions

| Misconception | Reality |
| --- | --- |
| "Java `char` is always one Unicode character." | `char` is one UTF-16 code unit; non-BMP characters need two units |
| "`String.length()` returns the number of emojis/letters." | Returns the number of UTF-16 units |
| "An emoji always takes two `char`s." | One supplementary code point takes two units, yet composite emojis can have multiple code points |
| "`codePointCount` equals the number of visible characters." | No, a grapheme cluster can contain multiple code points |
| "`substring` prevents slicing in the middle of a surrogate pair." | It takes UTF-16 indices and therefore can slice incorrectly |
| "`codePointAt(i)` automatically finds the high surrogate even if i is at low." | No; it must point to a code point start boundary |
| "`chars()` is the same as `codePoints()`." | `chars()` iterates code units; `codePoints()` iterates code points |
| "`UTF-8 byte length` equals Java `String.length()`." | Two different metrics |
| "`Character.isValidCodePoint` excludes all surrogates." | No; scalars must be checked separately |
| "A lone surrogate will always throw immediately inside a String." | Java can store it; errors typically surface when encoding or validating |
| "Avoiding pair splitting is enough to truncate UI emojis." | Insufficient if emojis are composed with modifiers/ZWJs |
| "`Normalizer` fixes all ill-formed UTF-16." | Normalization and UTF-16 well-formed validation are two separate tasks |
| "`StringBuilder.reverse()` always reverses visible characters properly." | It handles surrogate pairs, yet does not guarantee reversing by grapheme cluster |
| "Every DB counts VARCHAR by Java `char`." | Length depends on the database, charset, and contract |

## 16. Takeaways

- **Unicode code points outside the BMP (U+10000–U+10FFFF) require a surrogate pair in UTF-16.**
- **High surrogates** belong to U+D800–U+DBFF, and **low surrogates** belong to U+DC00–U+DFFF. A valid pair combines into one supplementary code point.
- Java `char` is a **UTF-16 code unit**. `String.length()` and `substring` use UTF-16 units/indices, not code points.
- When processing individual code points, use `codePointAt` + `Character.charCount`, `offsetByCodePoints`, or `String.codePoints()`.
- **Do not slice between a high and low surrogate** when splitting strings. If limiting display by "user-perceived characters", also account for **grapheme clusters**.
- **UTF-8 byte count, UTF-16 unit count, code-point count, and grapheme count are four distinct measurements.**
- A Java `String` can contain unpaired surrogates; when valid text is required, validate and choose an explicit encoder strategy.
- Separate encoding, normalization, collation, and grapheme segmentation; they solve different problems in localization.

### Official Java 17 Documentation

- [Character — Unicode code points and surrogate handling](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
- [String — length, charAt, codePointAt, codePoints, substring](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Pattern — Unicode grapheme clusters (`\X`)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
- [StandardCharsets — UTF-8](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [Normalizer — Unicode normalization forms](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
