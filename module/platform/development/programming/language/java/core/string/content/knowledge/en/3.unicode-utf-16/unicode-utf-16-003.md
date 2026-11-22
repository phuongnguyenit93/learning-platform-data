# BMP, Supplementary Characters, and Surrogate Pairs in Java String

Java stores and processes text using the Unicode model, in which each **code point** is identified by a value such as `U+0041` (letter A), `U+4E2D` (character 中), or `U+1F600` (😀). However, a large portion of Java's `String` API uses **UTF-16 code units** as the unit for counting and indexing. Because of this, a single Unicode character can occupy **two `char` elements** in a `String`.

Understanding the Basic Multilingual Plane (BMP), supplementary characters, and surrogate pairs helps you handle `length()`, `charAt()`, `substring()`, loops, and conversions between `char`, `int`, and `String` correctly.

## 1. Distinguishing Code Points, Code Units, and User-Perceived Characters

- **Unicode code point**: a code position in the space `U+0000` to `U+10FFFF`; usually written as `U+XXXX` or `U+XXXXX`/`U+XXXXXX`. In Java, a code point should be stored as an `int`.
- **Unicode scalar value**: a code point **not in** the surrogate range `U+D800`–`U+DFFF`. Every scalar value can be validly represented in UTF-16.
- **UTF-16 code unit**: a 16-bit unit. Java's primitive `char` type holds **one** UTF-16 code unit (values `0x0000`–`0xFFFF`). A `char` does not necessarily correspond to a complete code point.
- **Grapheme cluster** (display character cluster): what a reader typically perceives as one character; it can be formed from multiple code points, such as `e` + combining acute accent or an emoji joined with a connector character.

These three counts are not always equal. `String.length()` counts **UTF-16 code units**, `String.codePointCount(...)` counts **code points according to Java's UTF-16 handling**, while the number of display character clusters requires dedicated grapheme segmentation rules.

Quick examples:

| Text | Code points | UTF-16 code units | `String.length()` |
| --- | --- | ---: | ---: |
| `A` | `U+0041` | 1 | 1 |
| `中` | `U+4E2D` | 1 | 1 |
| `😀` | `U+1F600` | 2 | 2 |
| `é` (letter e + combining acute accent) | `U+0065`, `U+0301` | 2 | 2 |

The last row has two code points in the BMP yet typically renders as a single accented letter. Therefore, **counting code points is still not the same as counting user-perceived characters**.

## 2. BMP and Supplementary Planes

Unicode divides the code point space into **17 planes**, each capable of holding 65,536 code positions:

| Partition | Value range | Meaning |
| --- | --- | --- |
| BMP (plane 0) | `U+0000`–`U+FFFF` | Contains most common letters, symbols, and the range reserved for surrogates |
| Supplementary planes (planes 1–16) | `U+10000`–`U+10FFFF` | Contains many historic scripts, musical symbols, emojis, and other character sets |
| Surrogate code points (inside BMP) | `U+D800`–`U+DFFF` | Values **reserved for UTF-16**, not to be used as standalone Unicode scalar values |

**BMP does not mean every position in the BMP is a valid displayable character.** Surrogate positions are reserved code points and are not Unicode scalar values; additionally, there are unassigned positions or positions not meant for ordinary text characters.

A Unicode scalar value in the BMP (excluding the surrogate range) is encoded as **one UTF-16 code unit**. A code point in the supplementary planes is encoded as **two UTF-16 code units**, called a **surrogate pair**. There is no valid Unicode code point greater than `U+10FFFF`.

Examples:

- `U+0061` (a), `U+00E9` (é), `U+4E2D` (中): all belong to the BMP; each code point takes one `char`.
- `U+1F600` (😀), `U+1D11E` (𝄞, musical G clef symbol): all belong to the supplementary planes; each code point requires two `char`s.

## 3. How Is a Surrogate Pair Assembled?

UTF-16 uses two reserved code groups:

- **High surrogate (leading surrogate):** `U+D800`–`U+DBFF`.
- **Low surrogate (trailing surrogate):** `U+DC00`–`U+DFFF`.

For a code point `cp` from `U+10000` to `U+10FFFF`, the encoding process is described as follows:

1. Compute `x = cp - 0x10000` (a 20-bit value).
2. Extract the upper 10 bits: `high = 0xD800 + (x >> 10)`.
3. Extract the lower 10 bits: `low = 0xDC00 + (x & 0x3FF)`.
4. Store **high surrogate first, then low surrogate**.

To decode a valid pair:

```text
codePoint = 0x10000
          + ((high - 0xD800) << 10)
          +  (low  - 0xDC00)
```

Example with the 😀 emoji (`U+1F600`):

```text
Code point           : U+1F600
UTF-16 high surrogate: U+D83D
UTF-16 low surrogate : U+DE00
In Java String       : [\uD83D] [\uDE00]  (2 code units/chars)
```

Only when a **high surrogate immediately precedes a low surrogate** can Java combine the two units into a supplementary code point. A standalone high surrogate, a standalone low surrogate, or two surrogates in the wrong order is an **ill-formed UTF-16** code unit sequence. Java's `String` type can still hold such unpaired code units; applications must not assume every `String` has properly paired UTF-16.

Related APIs in `Character`:

| Method | Purpose |
| --- | --- |
| `Character.isHighSurrogate(char)` | Checks whether a `char` is in the high surrogate range |
| `Character.isLowSurrogate(char)` | Checks whether a `char` is in the low surrogate range |
| `Character.isSurrogatePair(high, low)` | Checks the correct high + low pair order |
| `Character.toCodePoint(high, low)` | Combines a **valid surrogate pair** into a code point as `int` |
| `Character.toChars(int)` | Encodes a code point into a `char[]` array of length 1 or 2 |
| `Character.charCount(int)` | Returns 2 if the code point is in the supplementary range, otherwise returns 1 |

Note: `Character.toCodePoint()` assumes the input is a valid pair; if you receive uncertain data, call `isSurrogatePair()` first.

## 4. Java Example: One Code Point with Two `char`s

File `UnicodeBasics.java` (Java 17+):

```java
public class UnicodeBasics {
    public static void main(String[] args) {
        String bmp = "\u4E2D"; // U+4E2D: a BMP character
        String supplementary = new String(Character.toChars(0x1F600));

        System.out.printf(
                "BMP: length=%d, codePoints=%d%n",
                bmp.length(), bmp.codePointCount(0, bmp.length())
        );
        System.out.printf(
                "Supplementary: length=%d, codePoints=%d%n",
                supplementary.length(),
                supplementary.codePointCount(0, supplementary.length())
        );

        char high = supplementary.charAt(0);
        char low = supplementary.charAt(1);

        System.out.printf("charAt(0)=U+%04X%n", (int) high);
        System.out.printf("charAt(1)=U+%04X%n", (int) low);
        System.out.println("valid pair=" + Character.isSurrogatePair(high, low));
        System.out.printf("codePointAt(0)=U+%X%n",
                supplementary.codePointAt(0));
        System.out.printf("toCodePoint=U+%X%n",
                Character.toCodePoint(high, low));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 UnicodeBasics.java
java UnicodeBasics
```

Expected output:

```text
BMP: length=1, codePoints=1
Supplementary: length=2, codePoints=1
charAt(0)=U+D83D
charAt(1)=U+DE00
valid pair=true
codePointAt(0)=U+1F600
toCodePoint=U+1F600
```

Here the emoji's `String.length()` returns **2**, because it counts two UTF-16 code units. Meanwhile, `codePointCount(0, length())` returns **1** because a valid surrogate pair is one code point.

`charAt(0)` and `charAt(1)` return only individual parts of the code pair. Never assume a single `charAt(index)` is always a complete Unicode character. `String.codePointAt(index)` can assemble the pair when `index` sits at a **high surrogate** immediately followed by a **low surrogate**; if called starting at a low surrogate, it does not look backward to pair with the preceding high part.

You can create the same emoji using escapes in a string literal:

```java
String smile = "\uD83D\uDE00";
```

The escaped string above provides two UTF-16 code units. Using `new String(Character.toChars(0x1F600))` often makes it clearer that you are starting from a **code point**.

## 5. `char` Index vs. Code Point Position

APIs such as `charAt(int)`, `substring(int, int)`, the index-accepting/returning overloads of `indexOf(...)`, and `String.length()` work with **UTF-16 code unit indices**. Yet a supplementary code point occupies two consecutive indices.

Consider the string `A😀B`:

```text
UTF-16 index     :  0         1          2         3
Code unit        : 'A'    high D83D   low DE00    'B'
Code point       : U+0041        U+1F600         U+0042
Code point index :  0              1             2
```

In total `length() == 4`, yet there are only **3 code points**.

Here is an example of iterating properly by code points using `codePointAt()` combined with `Character.charCount()`:

File `CodePointIteration.java`:

```java
public class CodePointIteration {
    public static void main(String[] args) {
        String text = "A" + new String(Character.toChars(0x1F600)) + "B";

        System.out.println("length=" + text.length());
        System.out.println("codePoints=" +
                text.codePointCount(0, text.length()));

        for (int charIndex = 0; charIndex < text.length();) {
            int codePoint = text.codePointAt(charIndex);
            System.out.printf("charIndex=%d -> U+%X%n", charIndex, codePoint);
            charIndex += Character.charCount(codePoint);
        }

        int afterTwoCodePoints = text.offsetByCodePoints(0, 2);
        System.out.println("offsetByCodePoints(0, 2)=" + afterTwoCodePoints);

        String emojiOnly = text.substring(1, 3);
        System.out.printf("substring(1, 3)=U+%X%n",
                emojiOnly.codePointAt(0));
    }
}
```

Run:

```bash
javac -encoding UTF-8 CodePointIteration.java
java CodePointIteration
```

Output:

```text
length=4
codePoints=3
charIndex=0 -> U+41
charIndex=1 -> U+1F600
charIndex=3 -> U+42
offsetByCodePoints(0, 2)=3
substring(1, 3)=U+1F600
```

The loop advances the UTF-16 index by **1** for BMP code points and by **2** for supplementary code points. Calling `offsetByCodePoints(0, 2)` translates a position **two code points** from UTF-16 index 0 into UTF-16 index **3**; this result is useful when slicing a string at code point boundaries.

You can iterate concisely using `text.codePoints()`, which returns an `IntStream` containing `int` values:

```java
text.codePoints().forEach(cp ->
        System.out.printf("U+%X%n", cp)
);
```

The snippet above is an illustrative fragment to place inside a method where `text` is already declared. For `A😀B`, it prints `U+41`, `U+1F600`, `U+42` in order (each value on its own line).

**Distinguishing `chars()` and `codePoints()`:**

- `text.chars()` produces a stream of `int` values representing **each UTF-16 code unit**. For `A😀B`, the stream has **4** elements: `0x41`, `0xD83D`, `0xDE00`, `0x42`.
- `text.codePoints()` attempts to combine **valid surrogate pairs**; for the same example, the stream has **3** elements: `0x41`, `0x1F600`, `0x42`.

If the string contains an unpaired surrogate, `codePoints()` can still emit the unpaired surrogate value itself as an `int`; do not assume every element is a valid Unicode scalar value.

## 6. Slicing Strings Without Breaking Surrogate Pairs

The two indices of `substring(beginIndex, endIndex)` are UTF-16 positions, **begin inclusive, end exclusive**. For `A😀B`, `substring(1, 3)` keeps the entire emoji, while `substring(1, 2)` extracts only the **high surrogate** and creates a UTF-16 string with a split pair.

If business logic needs the **first n code points**, convert the code point count to a UTF-16 index before calling `substring()`:

```java
public class SafeSubstring {
    static String firstCodePoints(String text, int count) {
        int end = text.offsetByCodePoints(0, count);
        return text.substring(0, end);
    }

    public static void main(String[] args) {
        String text = "A" + new String(Character.toChars(0x1F600)) + "B";
        String firstTwo = firstCodePoints(text, 2);

        System.out.println("UTF16 length=" + firstTwo.length());
        System.out.println("codePoints=" +
                firstTwo.codePointCount(0, firstTwo.length()));
        System.out.printf("lastCodePoint=U+%X%n",
                firstTwo.codePointBefore(firstTwo.length()));
    }
}
```

Save as `SafeSubstring.java`, compile and run with `javac -encoding UTF-8 SafeSubstring.java` and `java SafeSubstring`. Output:

```text
UTF16 length=3
codePoints=2
lastCodePoint=U+1F600
```

`offsetByCodePoints()` can throw `IndexOutOfBoundsException` when the code point offset goes out of valid bounds. Real-world usage should verify `count >= 0` and `count <= text.codePointCount(0, text.length())` before slicing, or explicitly define how invalid input is handled.

The solution above protects **code point** boundaries, yet does not necessarily preserve a **grapheme cluster**. For example, slicing between `e` and the combining mark `U+0301` can still break visual display even though it does not split a surrogate pair.

## 7. Detecting Unpaired Surrogates and Invalid Code Values

A `String` can store a standalone high surrogate without an accompanying low surrogate:

```java
String broken = "\uD83D";
System.out.println(broken.length());                     // 1
System.out.println(Character.isHighSurrogate(broken.charAt(0))); // true
System.out.printf("U+%X%n", broken.codePointAt(0));      // U+D83D
```

These are illustrative statements to place inside a Java method. `codePointAt()` returns the unpaired code unit value when no valid surrogate pair is present, so the `U+D83D` result here **is not a Unicode scalar value**. When writing this kind of data to another encoding or system, how invalid characters are handled can depend on the encoder and error-handling configuration. Do not rely on unpaired surrogates being transmitted intact.

To recognize surrogate pairs when iterating by `char`:

```java
static boolean hasWellFormedUtf16(String text) {
    for (int i = 0; i < text.length(); i++) {
        char current = text.charAt(i);

        if (Character.isHighSurrogate(current)) {
            if (i + 1 >= text.length() ||
                    !Character.isLowSurrogate(text.charAt(i + 1))) {
                return false;
            }
            i++; // Skip the low surrogate just paired with the high surrogate
        } else if (Character.isLowSurrogate(current)) {
            return false; // Standalone low surrogate
        }
    }
    return true;
}
```

This is an **illustrative method** that needs to be placed inside a class. It validates the well-formedness of **UTF-16 pairs**, not whether a code point has been assigned a specific character by Unicode.

In addition:

- `Character.isValidCodePoint(cp)` only checks that the integer falls within `U+0000`–`U+10FFFF`; this check **does not exclude the surrogate range**. To accept only Unicode scalar values, you must additionally exclude `U+D800`–`U+DFFF`.
- `Character.isSupplementaryCodePoint(cp)` recognizes the range `U+10000`–`U+10FFFF`.
- `Character.toChars(cp)` rejects values outside the Unicode range with `IllegalArgumentException`, but it should not be used alone as a scalar value validator. For a surrogate value, it can still produce an unpaired surrogate `char`.
- Being in the BMP does not mean Unicode has assigned a displayable meaning to that position. Furthermore, glyph availability also depends on the font and rendering environment.

## 8. Do Not Equate Code Points with Byte Length or Display Characters

Three representation layers must be distinguished:

| Question | Appropriate API/concept |
| --- | --- |
| How many UTF-16 code units does the string have? | `text.length()` |
| How many code points are there under Java's surrogate pairing rules? | `text.codePointCount(0, text.length())` or `text.codePoints().count()` |
| What code point is at a given UTF-16 index? | `text.codePointAt(charIndex)` |
| Shift n code points from a UTF-16 index? | `text.offsetByCodePoints(charIndex, n)` |
| How many bytes does the string's UTF-8 encoding have? | `text.getBytes(StandardCharsets.UTF_8).length`, noting that ill-formed UTF-16 data may be replaced when encoding |
| How many "characters" does the user see? | Grapheme cluster segmentation under appropriate Unicode rules |

For example, `😀` takes **2 UTF-16 code units** but **4 UTF-8 bytes** when validly encoded. `String.length()` is neither the byte count of a file or HTTP request, nor the internal memory footprint of the `String` object. The JVM may optimize string storage using another internal representation, but the public API contract still relies on UTF-16 indices.

With combining marks:

```java
String decomposed = "e\u0301"; // e + COMBINING ACUTE ACCENT
String composed = "\u00E9";   // precomposed é

System.out.println(decomposed.length()); // 2
System.out.println(composed.length());   // 1
```

Two strings can appear visually similar yet have different code point sequences and will not be `equals()` unless normalized under an appropriate rule. **Unicode normalization** is a related topic, independent of surrogate pair assembly.

## 9. Common Mistakes

**Mistake 1 — Treating `char` as a complete Unicode character.** A `char` is only a 16-bit code unit. A supplementary code point requires two consecutive `char`s.

**Mistake 2 — Using `length()` as the number of code points.** When supplementary characters are present, `length()` is greater than the code point count; use `codePointCount()` to count code points according to Java's model.

**Mistake 3 — Incrementing `i++` and calling `codePointAt(i)`.** The loop can land on a low surrogate and misprocess each half of the character. Advance using `Character.charCount(codePoint)` or iterate with `codePoints()`.

**Mistake 4 — Slicing with `substring()` in the middle of a surrogate pair.** Use `offsetByCodePoints()` to convert a code point position to a UTF-16 index before slicing. If display operations require keeping grapheme clusters intact, a higher-level segmentation solution is needed.

**Mistake 5 — Believing every surrogate belongs to a valid pair.** A `String` can contain unpaired surrogates. External input should be validated or have an invalid-character handling policy defined when needed.

**Mistake 6 — Confusing code unit count, code point count, grapheme clusters, and bytes.** These four quantities serve different needs: Java API indexing, Unicode code values, text display experience, and storage/transmission.

## 10. Self-Check Questions

**Question 1.** Why does `"😀".length()` equal 2 while `"😀".codePointCount(0, "😀".length())` equals 1?

**Answer:** Emoji `U+1F600` is a supplementary code point, so UTF-16 represents it with two code units `U+D83D` and `U+DE00`. `length()` counts the two code units; `codePointCount()` recognizes one valid pair and counts one code point.

**Question 2.** What does `charAt(1)` return in the string `A😀B`?

**Answer:** The high surrogate `U+D83D`, not the entire code point `U+1F600`. To read the entire emoji, use `codePointAt(1)` and receive an `int` value.

**Question 3.** Why is `substring(1, 2)` on `A😀B` problematic, whereas `substring(1, 3)` is not?

**Answer:** `substring()` indices are measured in UTF-16 code units. Range `[1,2)` takes only the high surrogate; range `[1,3)` captures both the high and low surrogates.

**Question 4.** Is a `String` with 5 code points guaranteed to display as 5 characters?

**Answer:** No. Combining marks, variation selectors, or joined emoji sequences can contain multiple code points while displaying as fewer grapheme clusters.

**Key takeaway:** BMP scalar values use **one** UTF-16 code unit; supplementary code points use **two** code units forming a **high + low surrogate** pair. In Java, `char` and `String` indices operate at the UTF-16 code unit level; when you need to process complete code points, prefer `int`, `codePointAt()`, `codePointCount()`, `offsetByCodePoints()`, `Character.charCount()`, or `codePoints()`.