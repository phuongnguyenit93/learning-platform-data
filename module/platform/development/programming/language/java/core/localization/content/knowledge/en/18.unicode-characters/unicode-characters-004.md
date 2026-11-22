# `length`, `codePointCount`, `codePoints`, and UTF-16 Indices in Java

## 1. Three Ways to "Count Characters" Are Not Always the Same

In Java, a `String` represents a sequence of **UTF-16 code units** at the API level. When handling localization, emojis, scripts outside the Basic Multilingual Plane (BMP), combining marks, and various Unicode characters, you must distinguish:

1. **UTF-16 code unit:** each Java `char` is a 16-bit code unit. `String.length()` counts these units.
2. **Unicode code point:** a numeric value identifying a position in the Unicode code space, such as `U+0041` (A) or `U+1F600` (grinning face emoji). `String.codePointCount(begin, end)` counts the code points represented in a UTF-16 segment; `String.codePoints()` provides a corresponding stream of `int`s.
3. **Grapheme cluster / user-perceived character:** a cluster that can consist of multiple code points yet is viewed and manipulated as one character, such as `e` + combining acute accent or a flag emoji made from two regional indicators. No `String.length()` or `codePointCount()` method counts grapheme clusters according to full Unicode rules by default.

**Example:** a string containing the letter `A`, emoji `U+1F600`, letter `e` followed by combining mark `U+0301`, then two regional indicators `U+1F1FB` and `U+1F1F3` forming the Vietnam flag:

~~~text
Code points:
U+0041 | U+1F600 | U+0065 | U+0301 | U+1F1FB | U+1F1F3

Code point count: 6
UTF-16 code units count: 9
Typically displayed grapheme clusters: 4
~~~

The four grapheme clusters in the example correspond to **A**, **grinning emoji**, **e with acute accent**, and **flag emoji**. The grapheme count depends on Unicode segmentation rules and rendering; do not rely on it to deduce a storage limit measured in UTF-16 code units.

When learning Java core, remember: **indices passed to many `String` APIs are UTF-16 indices**, even for APIs with *codePoint* in their names.

## 2. Why Can One Code Point Take Two `char`s?

Unicode has codes in the Basic Multilingual Plane BMP (from `U+0000` to `U+FFFF`) and supplementary codes (supplementary code points, greater than `U+FFFF`). In UTF-16:

- A code point in the BMP (outside the surrogate region when it is a valid Unicode scalar value) can be represented by **one** `char`.
- A supplementary code point requires **two** `char`s: a **high surrogate** followed by a **low surrogate**.
- High surrogates lie in `U+D800`–`U+DBFF`; low surrogates lie in `U+DC00`–`U+DFFF`.
- A single `char` is **insufficient** to represent every Unicode code point. `int` is the appropriate type when reading a code point.

For example, the emoji `U+1F600` has the UTF-16 pair:

~~~text
Code point           : U+1F600
High surrogate       : U+D83D
Low surrogate        : U+DE00
UTF-16 code units    : 2
Unicode code points  : 1
~~~

A string can contain an **unpaired surrogate** due to bad slicing, reading invalid data, or constructing `char`s directly. Note: Java's `String.codePointCount` and `String.codePoints()` **still count/return a lone surrogate as one item**. Therefore, *counting code points does not equate to verifying that text contains only valid Unicode scalar values*.

### 2.1. UTF-16 Indices of the Example

The code units in the six-code-point string are arranged as follows:

| UTF-16 index | Code unit (hex) | Belongs to which code point? |
| ---: | --- | --- |
| 0 | `U+0041` | A |
| 1 | `U+D83D` | High surrogate of `U+1F600` |
| 2 | `U+DE00` | Low surrogate of `U+1F600` |
| 3 | `U+0065` | e |
| 4 | `U+0301` | Combining acute accent |
| 5 | High surrogate of `U+1F1FB` | First regional indicator |
| 6 | Low surrogate of `U+1F1FB` | First regional indicator |
| 7 | High surrogate of `U+1F1F3` | Second regional indicator |
| 8 | Low surrogate of `U+1F1F3` | Second regional indicator |

The code point start positions (measured in `char`s) are **0, 1, 3, 4, 5, 7**; the position immediately after the last code point is **9**. Because some code points occupy two `char`s, code point indices and UTF-16 indices **cannot be interchanged**.

Internally in the JVM, the physical representation of some `String`s may be optimized (for example, Compact Strings). That **does not change the API contract**: `length()`, `charAt`, `substring`, and the indices described here remain in UTF-16 code units.

## 3. `String.length()`: Counts Code Units, Not Code Points

Method:

~~~java
int count = text.length();
~~~

This is an **illustrative snippet**; `text` is a declared `String`.

For the ASCII string `"Java"`, `length() == 4` and `codePointCount(0, 4) == 4`. Yet with a supplementary character, the result differs:

~~~java
String emoji = new String(Character.toChars(0x1F600));
System.out.println(emoji.length()); // 2
~~~

The example above runs inside a Java method. `Character.toChars(0x1F600)` returns two `char`s, so the `String`'s length is 2 even though the user sees one emoji.

Practical consequences:

- `String.length()` is suitable for calculating the **number of UTF-16 code units** when an API or data field capacity requires that type of size.
- `length()` does **not** count code points, grapheme clusters, letters, words, or UTF-8 bytes.
- Do not write `length() <= max` and claim "users can enter at most max visible characters" if the limit needs to be based on graphemes.
- If the rule concerns byte count when sending via an API or database, measure in the **actual charset** such as UTF-8 rather than inferring from `length()`.

### 3.1. `charAt` Also Reads One Code Unit

~~~java
char firstPart = text.charAt(1);
~~~

`charAt(1)` returns only the **high surrogate** `U+D83D` in the example, not the full `U+1F600`. If printed alone to a UI or passed through an encoding, the character can become a replacement symbol because the surrogate pair was split.

Use `Character.isHighSurrogate` and `Character.isLowSurrogate` to identify parts of a pair when operating at the UTF-16 level; when processing a code point, use appropriate code point APIs.

## 4. `codePointCount(beginIndex, endIndex)`: Counting Code Points in a UTF-16 Range

Syntax:

~~~java
int n = text.codePointCount(0, text.length());
~~~

**Both parameters are UTF-16 indices**, not code point indices:

- `beginIndex`: starting position, inclusive.
- `endIndex`: ending position, exclusive.
- The text slice examined is `[beginIndex, endIndex)`.
- If a complete surrogate pair falls inside the range, it counts as **one code point**.
- An unpaired surrogate inside the range counts as **one item**.
- Out-of-bounds parameters or `beginIndex > endIndex` throw `IndexOutOfBoundsException`.

With the string from Section 1:

~~~java
System.out.println(text.length());                        // 9
System.out.println(text.codePointCount(0, text.length())); // 6
~~~

This is an illustration inside a method; the complete program is in Section 8.

**Slicing right in the middle of a surrogate pair:** the range `[1, 2)` contains only the emoji's high surrogate, so `codePointCount(1, 2)` returns **1**, yet that slice is not a valid standalone scalar code point. Do not use the count result to prove that a Unicode slice is intact.

### 4.1. `codePointCount` Does Not Locate the nth Code Point

Counting code points of `text` only tells you **how many**, not the UTF-16 position of the 3rd code point. If you use:

~~~java
text.charAt(2)
~~~

then index 2 is still the emoji's **low surrogate**, not the second code point or second Unicode letter. To advance by n code points, use `offsetByCodePoints` (Section 6).

Do not write `for (int i = 0; i < text.codePointCount(0, text.length()); i++) text.charAt(i)` because this loop mixes two index unit systems.

## 5. `codePoints()`: An `int` Stream by Code Point

`String.codePoints()` returns an `IntStream`. When encountering a valid surrogate pair, the stream combines both code units into **one** `int` holding the supplementary code point value.

~~~java
int[] points = text.codePoints().toArray();
~~~

In the example with `A`, emoji, `e`, combining acute accent, and two regional indicators, this array contains:

~~~text
U+0041, U+1F600, U+0065, U+0301, U+1F1FB, U+1F1F3
~~~

**Comparison with `chars()`:**

- `text.chars()` returns an `IntStream` of **each UTF-16 code unit** (each `char` widened to `int`). It yields **9 elements** on the sample string.
- `text.codePoints()` merges surrogate pairs and yields **6 elements** on the sample string.
- Neither handles grapheme clusters automatically; combining mark `U+0301` remains a separate item in the code point stream.

If the input has an unpaired surrogate, `codePoints()` emits that surrogate value onto the stream as an `int`. It **does not validate**, nor does it fix invalid Unicode.

### 5.1. Why Use `IntStream` Instead of a `char` Loop?

When writing a code point range check or Unicode statistics, a code point stream avoids accidentally treating each half of an emoji as an independent character:

~~~java
long supplementaryCount = text.codePoints()
        .filter(Character::isSupplementaryCodePoint)
        .count();
~~~

This is an illustrative snippet inside a method with variable `text`. It counts the number of **supplementary code points**, not the number of emojis or grapheme clusters. Non-emoji characters can also lie outside the BMP; a composite emoji can also contain multiple code points, so you cannot deduce the emoji count from this number.

### 5.2. Do Not Cast a Code Point to `char`

~~~java
int cp = 0x1F600;
char broken = (char) cp; // Loses supplementary code point information.
~~~

This is an illustrative snippet of what not to do. Casting `int` to `char` retains only the lower 16 bits, no longer representing `U+1F600` properly.

To build a string from code points:

~~~java
String emoji = new String(Character.toChars(0x1F600));
String reconstructed = new String(
        new int[]{0x0041, 0x1F600, 0x0065}, 0, 3);
~~~

`Character.toChars` and the constructor `String(int[], offset, count)` let you create UTF-16 corresponding to valid code points; the `count` parameter in the constructor above is the **number of code point array elements**, not the code unit count of the resulting string.

## 6. `offsetByCodePoints`: Converting a Code Point Position to a UTF-16 Index

An essential API for moving through a `String` by code points:

~~~java
int utf16Index = text.offsetByCodePoints(0, 2);
~~~

In the example string, the result is **3**:

- The first code point `A` occupies UTF-16 index 0.
- The second code point `U+1F600` occupies UTF-16 indices 1 and 2.
- The position **after the first two code points** is UTF-16 index **3**.

`offsetByCodePoints(index, codePointOffset)` accepts:

- `index`: starting position **in UTF-16**.
- `codePointOffset`: how many **code points** to shift forward/backward; can be negative.
- Return value: the new position **in UTF-16**, not the code point ordinal.

If out of bounds, the method throws `IndexOutOfBoundsException`. In regions with unpaired surrogates, each is still counted as one code point in the shift.

### 6.1. Getting the nth Code Point (0-Based)

~~~java
int n = 2;
int utf16Index = text.offsetByCodePoints(0, n);
int point = text.codePointAt(utf16Index);
~~~

This is an illustrative snippet: n = 2 means the third code point, which in the example is `U+0065` (`e`); its UTF-16 index is 3. Condition: `0 <= n < text.codePointCount(0, text.length())`, otherwise out-of-range indices must be handled.

### 6.2. Slicing a Segment by Code Point Count Without Breaking Surrogate Pairs

~~~java
static String sliceByCodePoints(String s, int startCp, int endCp) {
    int start = s.offsetByCodePoints(0, startCp);
    int end = s.offsetByCodePoints(0, endCp);
    return s.substring(start, end);
}
~~~

This is an **illustrative method**, which must be placed inside a class. `startCp` and `endCp` are indices **by code point**, with exclusive end and range `0 <= startCp <= endCp <= totalCodePoints`. Validate parameter bounds if accepting untrusted input.

This function does not slice between **a valid surrogate pair** when starting from 0 and stepping along code point boundaries. However, it **can still slice inside a grapheme cluster** such as letter `e` and its combining acute accent, or two regional indicators forming a flag emoji.

Do **not** call `text.substring(0, 2)` to extract "the first two Unicode characters" in the sample string. It will grab `A` and **only the first half of the emoji**, producing a string with a lone surrogate.

### 6.3. The Input Index Must Still Sit on an Appropriate Boundary

`offsetByCodePoints` accepts any valid UTF-16 index and does not promise to snap a position **already in the middle of a surrogate pair** back to the start of the pair. If the start index already points to a low surrogate (such as index 2), shifting may treat that low surrogate as an independent unit within the traversed range.

When receiving an index from an editor/UI, verify whether it is a UTF-16 index, a code point index, or a grapheme index. Do not mix different index types directly without converting or aligning boundaries.

## 7. `codePointAt`, `codePointBefore`, `indexOf`, and `substring`: Index Constraints

### 7.1. Reading a Code Point at a UTF-16 Index

~~~java
int at = text.codePointAt(1);
int before = text.codePointBefore(3);
~~~

Both return `U+1F600` in the example:

- `codePointAt(1)` starts at the **high surrogate** and sees the following low surrogate, so it combines them into the full code point.
- `codePointBefore(3)` looks backward from position 3, sees the low surrogate at 2 and high at 1, so it combines them into the full code point.
- Do **not** call `codePointAt(2)` expecting `U+1F600`: position 2 is a low surrogate, so it is returned as a lone surrogate value.

Indices for both methods are **UTF-16**, and they have different boundary rules: `codePointAt(i)` requires `0 <= i < length()`, whereas `codePointBefore(i)` requires `1 <= i <= length()`.

### 7.2. `indexOf` Returns a UTF-16 Index

~~~java
String emoji = new String(Character.toChars(0x1F600));
int position = text.indexOf(emoji); // 1
~~~

The result **1** is the UTF-16 position where the emoji starts, not "code point #1" by API contract even though it happens to equal 1 in this string.

When searching for a character **after** the emoji, the two coordinate systems diverge: `text.indexOf("e")` returns UTF-16 index **3**, whereas `e` is the **3rd** code point if 1-based (code point index 2 if 0-based).

`String.indexOf(int ch)` can also accept **a Unicode code point** (even if its value is above the BMP), yet the **return value is still a UTF-16 index**.

### 7.3. `substring` Always Takes UTF-16 Indices

`substring(beginIndex, endIndex)` likewise uses the range `[beginIndex, endIndex)` in UTF-16:

~~~java
String fullEmoji = text.substring(1, 3);   // Two chars, one code point.
String brokenHalf = text.substring(1, 2);  // High surrogate only.
~~~

`fullEmoji.length() == 2`, yet `fullEmoji.codePointCount(0, 2) == 1`. Meanwhile `brokenHalf.length() == 1`; `Character.isHighSurrogate(brokenHalf.charAt(0))` returns `true`.

**Improperly sliced data can pass through many APIs** without throwing an exception immediately. Failures often only appear when converting to UTF-8, rendering UI, verifying signatures, or saving to a system requiring valid Unicode scalar values. Slice at code point boundaries and control encoding at the start and end of the pipeline.

## 8. Complete Java 17 Program: Observing 9 Code Units and 6 Code Points

Place the following in the file **`Utf16IndexDemo.java`**. The program builds the string from a **code point array**, avoiding reliance on terminal/source editor emoji input capability. All stdout uses `U+...` codes for stable comparison.

~~~java
import java.util.Locale;
import java.util.stream.Collectors;

public class Utf16IndexDemo {
    static String hex(int codePoint) {
        return String.format(Locale.ROOT, "U+%04X", codePoint);
    }

    public static void main(String[] args) {
        int[] values = {
                0x0041, 0x1F600, 0x0065,
                0x0301, 0x1F1FB, 0x1F1F3
        };
        String text = new String(values, 0, values.length);
        String emoji = new String(Character.toChars(0x1F600));

        System.out.println("length=" + text.length());
        System.out.println("codePointCount=" +
                text.codePointCount(0, text.length()));
        System.out.println("codePoints=" + text.codePoints()
                .mapToObj(Utf16IndexDemo::hex)
                .collect(Collectors.joining(", ")));

        System.out.println("charAt(1)=" + hex(text.charAt(1)));
        System.out.println("charAt(2)=" + hex(text.charAt(2)));
        System.out.println("codePointAt(1)=" +
                hex(text.codePointAt(1)));
        System.out.println("codePointBefore(3)=" +
                hex(text.codePointBefore(3)));

        System.out.println("offsetByCodePoints(0,2)=" +
                text.offsetByCodePoints(0, 2));
        System.out.println("indexOf(emoji)=" + text.indexOf(emoji));

        String correct = text.substring(1, 3);
        String broken = text.substring(1, 2);
        System.out.println("valid substring length=" + correct.length()
                + ", codePoints=" +
                correct.codePointCount(0, correct.length()));
        System.out.println("broken substring length=" + broken.length()
                + ", highSurrogate=" +
                Character.isHighSurrogate(broken.charAt(0)));
        System.out.println("index at code point #4=" +
                text.offsetByCodePoints(0, 4));
    }
}
~~~

Compile and run with **JDK 17 or higher**:

~~~bash
javac -encoding UTF-8 Utf16IndexDemo.java
java Utf16IndexDemo
~~~

**Stdout verified on Java:**

~~~text
length=9
codePointCount=6
codePoints=U+0041, U+1F600, U+0065, U+0301, U+1F1FB, U+1F1F3
charAt(1)=U+D83D
charAt(2)=U+DE00
codePointAt(1)=U+1F600
codePointBefore(3)=U+1F600
offsetByCodePoints(0,2)=3
indexOf(emoji)=1
valid substring length=2, codePoints=1
broken substring length=1, highSurrogate=true
index at code point #4=5
~~~

**Why are the results like this?**

1. `length=9`: three code points in the BMP occupy one code unit each (`A`, `e`, `U+0301`), plus three supplementary code points occupying two code units each (grinning emoji and two regional indicators): `3 × 1 + 3 × 2 = 9`.
2. `codePointCount=6`: the code point stream contains exactly the six values in the array.
3. `charAt(1)` and `charAt(2)` are the two surrogates `D83D` and `DE00`; `codePointAt(1)` combines them into `U+1F600`.
4. `codePointBefore(3)` reads the whole emoji preceding UTF-16 position 3.
5. Moving two code points from UTF-16 index 0 reaches index 3 because the emoji occupies two `char`s.
6. `substring(1, 3)` preserves the emoji; `substring(1, 2)` breaks the surrogate pair.
7. The starting position of **code point index 4** (0-based) is **UTF-16 index 5**.

Do not look at rendered glyphs to measure code point count. The flag emoji in the example is built from **two regional indicators**, each being a supplementary code point. A terminal may render a flag, two separate symbols, or replacement characters; the Unicode content of the code point array does not change.

## 9. Unicode Code Points Still Differ from Grapheme Clusters

A "letter" perceived by a user can consist of **multiple code points**:

- `e` plus `U+0301` represents an e with acute accent using two code points; it may look equivalent to precomposed `é` (`U+00E9`), yet length and code point count differ.
- The Vietnam flag in the example is the regional indicator pair `U+1F1FB` and `U+1F1F3`, not a single code point.
- Some emojis that users view as a single icon are combined from multiple code points using a **zero-width joiner (ZWJ)**, `VS16` variation selector, skin-tone modifiers, or other Unicode rules.

Therefore, the three counts can differ completely:

| Rule to measure | API/approach | Notes |
| --- | --- | --- |
| Number of UTF-16 units | `String.length()` | Suitable for limits measured in UTF-16 |
| Number of traversed code points | `codePointCount(0, length())`, `codePoints()` | May count lone surrogates as one item each |
| Number of user-perceived characters | Grapheme segmenter per Unicode UAX #29 | Must verify supporting version/implementation |
| Number of UTF-8 bytes | `getBytes(StandardCharsets.UTF_8).length` | Accurate only if text is encoded under a defined invalid-character handling policy |
| Number of "letters" | Specific linguistic/Unicode property criteria | Differs from both code points and graphemes |

Java has `java.text.BreakIterator` for various text boundaries, yet do not assume the segmenter in **every** JDK/locale accurately covers all *extended grapheme cluster* rules, especially modern emojis. If a product needs cursor/delete/"visible character" counting per UAX #29, pick a library or environment verified against the Unicode version the product requires.

### 9.1. Unicode Normalization Does Not Solve Everything

`java.text.Normalizer` can convert certain equivalent representations to NFC/NFD. For example, `e + U+0301` can be normalized to `é` (`U+00E9`) under NFC, changing `length()` and `codePointCount()` while the user still sees the same letter.

However, normalization **is not** a way to turn every emoji sequence or grapheme cluster into one code point. Nor should you automatically normalize every ID, secret, signature, path, or sensitive field if the contract has not specified it: changing Unicode form can affect equality and stored values.

## 10. Data Limits and Safe Operations

### 10.1. When a System Limits Character Count

Before checking `length()`, clarify the requirement:

- **UTF-16 code unit limit:** use `length()`, such as APIs reporting Java `String` length.
- **Unicode code point limit:** use `codePointCount(0, length())`, while also validating surrogates if the source requires valid Unicode scalar values.
- **Grapheme cluster limit:** use an appropriate grapheme segmentation algorithm.
- **Byte limit when sending/storing:** encode with the charset and measure bytes; with UTF-8, non-BMP characters usually take four bytes, though the byte/char/code-point relationship is not fixed.

Do not use a limit named "100 characters" and implicitly equate it with every method. When an application supports Vietnamese, emojis, Indic scripts, and international users, confusion can lead to corrupting text when slicing or unfairly rejecting lengths.

### 10.2. Extracting a Character Slice Without Breaking Surrogate Pairs

When limiting by code points, the basic rule is to compute the boundary with `offsetByCodePoints` before calling `substring`. For example, taking at most `n` code points from the start:

~~~java
static String firstCodePoints(String s, int n) {
    if (n < 0) {
        throw new IllegalArgumentException("n must be >= 0");
    }
    int total = s.codePointCount(0, s.length());
    int end = s.offsetByCodePoints(0, Math.min(n, total));
    return s.substring(0, end);
}
~~~

This is **an illustrative method** that needs to be placed inside a class. It avoids splitting a valid surrogate pair in half when starting from index 0; it **does not** guarantee avoiding splitting a grapheme cluster. If the input already has a lone surrogate, the method also does not remove the invalid part.

### 10.3. Loop Iterating Code Points Without Creating an Array

~~~java
for (int i = 0; i < s.length(); ) {
    int cp = s.codePointAt(i);
    // Process cp.
    i += Character.charCount(cp);
}
~~~

This is an **illustrative snippet**, with `s` being a `String`. `Character.charCount(cp)` returns 2 for a supplementary code point and 1 for BMP/lone surrogate. The loop advances along code point boundaries; with valid data, it does not split surrogate pairs.

If you only need to process code point values and do not need the UTF-16 index, `s.codePoints().forEach(cp -> ...)` can be easier to read. If you need the index, use this loop or deliberately combine with `offsetByCodePoints`.

### 10.4. Locating Positions in UI and Data

When a library/editor sends back a caret position or selection, confirm the index unit:

- Some APIs return a **UTF-16 offset**, suitable directly for `String.substring`.
- Some APIs return a **code point ordinal** or **grapheme offset**.
- Some systems store a **byte offset** in UTF-8.

Do not convert "code point index 4" directly into `substring(4)` if the preceding text contains supplementary code points. In the example, code point index 4 corresponds to UTF-16 index 5. Likewise, do not infer a `char` offset from a byte offset.

Bugs commonly happen in text selection ranges, search result highlighting, validation error positions, password/username lengths, and Unicode content pagination.

## 11. Common Mistakes and Misconceptions

| Mistake/error | Consequence | Correct approach |
| --- | --- | --- |
| `length()` counts an emoji as 1 | Supplementary emoji takes two `char`s | Use `codePointCount` when code points are needed |
| `charAt(i)` always returns a complete Unicode character | Can return a high/low surrogate | Use `codePointAt` on a proper boundary |
| Using `codePointCount` then passing the result to `substring` as a UTF-16 index | Slices at the wrong position or breaks a surrogate | Use `offsetByCodePoints` to convert indices |
| `codePoints()` counts graphemes | Combining marks and flag emojis still have multiple code points | Use grapheme segmentation if the UI requires it |
| Lone surrogates are automatically fixed by `codePoints()` | Invalid Unicode data still passes through the stream | Validate and apply a reject/replace policy |
| `indexOf` returns a code point index | `indexOf` returns a **UTF-16 offset** | Convert units explicitly before using |
| `codePointAt(i)` accepts a code point ordinal | Parameter i is a UTF-16 index | Use `offsetByCodePoints` first |
| Casting a supplementary `int` down to `char` | Data loss | Use `Character.toChars` or a String constructor from code points |
| Counting bytes with `length()` | Wrong for UTF-8 and many encodings | Encode first, then count bytes |
| Slicing by code point and assuming ZWJ emojis stay intact | Can break grapheme clusters | Use a grapheme algorithm for caret/UI |
| Trusting every `BreakIterator` to be accurate with new emojis | Segmentation can lag behind Unicode versions | Test the chosen segmenter |
| Taking a UTF-16 index starting at a low surrogate and stepping code points | Initial boundary is already invalid for the surrogate pair | Normalize/operate along proper boundaries |

### 11.1. The Case of Lone Surrogates

A Java `String` can contain a `char` in the surrogate range without a valid partner. In that case:

- `length()` still counts code units.
- `codePointCount()` treats the lone surrogate as one item.
- `codePoints()` emits the surrogate value as an `int`, and **does not** turn it into a valid Unicode scalar value.
- When encoding to UTF-8 via an encoder, the outcome for a lone surrogate depends on the **malformed input handling policy** (report, replace, or other); control it explicitly if data must be preserved or sanitized.

For input requiring valid Unicode, validate surrogate pairs or use a decoder/encoder configured to report errors. `codePointCount` does not perform that job.

### 11.2. Measurements Can Change Under Normalization

The string `e + U+0301` has `length() == 2` and `codePointCount(...) == 2`, even though in the UI it typically looks like one accented letter. If NFC-normalized to `U+00E9`, `length() == 1` and `codePointCount(...) == 1`. Therefore, you must decide whether to normalize Unicode **before** enforcing any promised limit rules.

## 12. Practice Exercises

1. Create `String smile = new String(Character.toChars(0x1F600));`; compare `smile.length()`, `smile.codePointCount(0, smile.length())`, `smile.chars().count()`, and `smile.codePoints().count()`.
2. From the program in Section 8, try `text.codePointAt(2)`. Explain why the result is a **low surrogate** rather than the complete emoji.
3. Compute `text.offsetByCodePoints(0, 5)`. Find the corresponding UTF-16 index and verify against the index table in Section 2.
4. Slice `text.substring(3, 5)`: which code points does it contain? Is that one or multiple grapheme clusters?
5. Write `sliceByCodePoints` with `startCp`, `endCp` and test cases `0`, total code points, negative indices, and `startCp > endCp`.
6. Use `Character.isSurrogatePair(high, low)` to detect the surrogate pair of `U+1F600`; try splitting half the pair to see how output encoding reacts.
7. Use `java.text.Normalizer` to convert `"e\u0301"` to NFC; compare `length()` and `codePointCount` before and after.
8. Create a ZWJ emoji sequence and compare `codePoints().count()` with the number of icons seen in the UI. Do not draw conclusions solely from its appearance in a single console.
9. Measure `text.getBytes(StandardCharsets.UTF_8).length` for the sample string (when valid), comparing with `length()` and `codePointCount()`.
10. Write tests for a "10 characters" limit rule: express three separate test versions for UTF-16 units, code points, and grapheme clusters.
11. Prove `text.indexOf("e") == 3` even though `e` is the code point at ordinal 2 in the sample string.
12. Given a caret offset from a UI: determine which coordinate system it belongs to before slicing or highlighting text.

## 13. Summary

**`String.length()` counts UTF-16 code units; `codePointCount(begin, end)` counts code points in a range specified by UTF-16 indices; `codePoints()` emits an `int` stream by code point; and many methods such as `charAt`, `codePointAt`, `substring`, and `indexOf` still accept/return UTF-16 offsets.**

To convert from a code point ordinal to a `String` index, use `offsetByCodePoints`; to iterate over code points without splitting surrogate pairs, use `codePoints()` or a loop with `codePointAt` and `Character.charCount`. When "user-perceived characters" are required, you must account for **grapheme clusters** and Unicode segmentation rules, because many emojis and combining marks consist of multiple code points.

Clearly separating **code units, code points, grapheme clusters, and bytes** keeps multilingual applications from corrupting text, mixing up indices, and enforcing wrong input limits.

**References:**

- Java SE 17, `String`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html
- Java SE 17, `Character`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html
- Java SE 17, `BreakIterator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html
- Java SE 17, `Normalizer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html
- Unicode Standard Annex #29 (Text Segmentation): https://unicode.org/reports/tr29/
