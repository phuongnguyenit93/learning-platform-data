# Slicing Strings by Code Point Instead of Splitting Surrogate Pairs in Java

When extracting part of a `String` containing emojis, rare scripts, or Unicode characters outside the Basic Multilingual Plane (BMP), slicing by arbitrary `char` indices can split a **surrogate pair** in half. The result is still a valid `String` object at the Java API level, but it contains a malformed UTF-16 sequence that easily renders as a replacement character or gets mishandled during encoding.

The solution is to determine boundaries using **Unicode code points**, then convert those code point positions into the appropriate **UTF-16 indices** before calling `substring()`. This lesson focuses on the mechanism, safe slicing, and the limits of this approach.

## 1. Distinguishing `char`, UTF-16 Code Unit, and Unicode Code Point

Java `String` provides many APIs indexed by **UTF-16 code units**, not by the number of characters a user sees.

- **Unicode code point** is a value from `U+0000` to `U+10FFFF`; the values reserved for surrogates (`U+D800`–`U+DFFF`) are not valid *Unicode scalar values* representing standalone characters.
- **UTF-16 code unit** is a 16-bit unit. Unicode values in the BMP that are not surrogates are encoded with one code unit. Values outside the BMP are encoded with two code units, forming a **surrogate pair**.
- **`char` in Java** is a 16-bit value type representing **one UTF-16 code unit**. A single `char` cannot hold a non-BMP code point on its own.
- **`int`** is commonly used when working with Unicode code point values, for example via `String.codePointAt()`, `String.codePoints()`, or `Character.toChars()`.

The two halves of a surrogate pair fall within these ranges:

| Component | Range |
| --- | --- |
| High surrogate (first half) | `U+D800`–`U+DBFF` |
| Low surrogate (second half) | `U+DC00`–`U+DFFF` |
| Code points requiring a surrogate pair in UTF-16 | `U+10000`–`U+10FFFF` |

For example, the emoji 😀 is code point `U+1F600`, encoded in UTF-16 as two code units `D83D DE00`. Therefore, the string `"A😀B"` has **4 UTF-16 code units** but only **3 code points**: `A`, `😀`, `B`.

```text
Content:           A         😀                B
Code point:      U+0041   U+1F600           U+0042
UTF-16 unit:     0041     D83D    DE00       0042
UTF-16 index:      0        1       2          3       (end = 4)
Code-point index:  0        1                  2       (end = 3)
```

Code point positions are **logical code-point indices**; `String.substring()` **does not accept** that kind of index directly.

## 2. Why Can `length()`, `charAt()`, and `substring()` Be Misleading?

`String.length()` returns the number of **UTF-16 code units**, and `charAt(index)` returns one `char` at the corresponding code unit position. `substring(beginIndex, endIndex)` also uses two UTF-16 indices, with `beginIndex` inclusive and `endIndex` exclusive.

With `"A😀B"`:

```java
String text = "A" + new String(Character.toChars(0x1F600)) + "B";

System.out.println(text.length());                           // 4
System.out.println(text.codePointCount(0, text.length()));    // 3
System.out.println(Character.isHighSurrogate(text.charAt(1))); // true
System.out.println(Character.isLowSurrogate(text.charAt(2)));  // true
```

This is an **illustrative snippet inside a method body**. `Character.toChars(0x1F600)` produces the exact two `char`s for the emoji without depending on typing the emoji directly in source files.

### Mistake: Treating a Code Point Index as a UTF-16 Index

Suppose you want the **first two code points** (`A` and `😀`), and write:

```java
String unsafe = text.substring(0, 2); // WRONG if the goal is two code points
```

`substring(0, 2)` only takes code units at indices 0 and 1: the letter `A` plus the **high surrogate** `D83D`. It drops the low surrogate `DE00`, leaving an unpaired surrogate in the resulting string. Java does not automatically fix this during `substring()`.

Similarly, wanting only the emoji and calling `text.substring(1, 2)` yields only the high surrogate; the correct UTF-16 range must be `[1, 3)`.

Do not demonstrate the bug by printing an unpaired surrogate directly to the console: how it renders depends on encoding and terminal. Instead, check it programmatically:

```java
String unsafe = text.substring(0, 2);

System.out.println(unsafe.length()); // 2
System.out.println(Character.isHighSurrogate(
        unsafe.charAt(unsafe.length() - 1))); // true
```

## 3. Java APIs for Slicing by Code Point

| API | Role | Index System |
| --- | --- | --- |
| `s.length()` | Counts UTF-16 code units | Number of code units |
| `s.charAt(i)` | Gets one code unit | `i` is a UTF-16 index |
| `s.substring(start, end)` | Extracts a character range | `start`, `end` are UTF-16 indices |
| `s.codePointCount(start, end)` | Counts code points in a UTF-16 range | Arguments are UTF-16 indices |
| `s.offsetByCodePoints(index, offset)` | Moves `offset` code points from a UTF-16 index | Returns a UTF-16 index |
| `s.codePointAt(index)` | Reads the code point starting at UTF-16 position `index` | Argument is a UTF-16 index; returns `int` |
| `Character.charCount(cp)` | Number of UTF-16 code units to represent a code point | Usually 1 or 2 |
| `s.codePoints()` | Iterates over the string's code point values via `IntStream` | Does not directly provide UTF-16 indices |
| `StringBuilder.appendCodePoint(cp)` | Appends a code point value to the builder | Avoids manually assembling surrogate halves |

Especially useful is `offsetByCodePoints`. Example:

```java
String text = "A" + new String(Character.toChars(0x1F600)) + "B";
int startUtf16 = text.offsetByCodePoints(0, 1);
int endUtf16 = text.offsetByCodePoints(0, 2);

System.out.println(startUtf16); // 1
System.out.println(endUtf16);   // 3
```

`startUtf16 = 1` stands before the high surrogate, and `endUtf16 = 3` stands **after** the low surrogate. Thus `text.substring(1, 3)` extracts the whole emoji without breaking the surrogate pair.

`offsetByCodePoints` can accept a negative `offset` to move backward, though the position and offset must be valid; Java throws `IndexOutOfBoundsException` when out of range.

## 4. Safe Code-Point-Range Slicing Function

Let's define a clear API: accept `fromInclusive` and `toExclusive` as **code point indices from the start of the string**, both following the inclusive-start/exclusive-end rule. This is a suitable choice when callers need to extract a string slice by code point count.

```java
import java.util.Objects;

public final class CodePointSlices {
    private CodePointSlices() {
    }

    public static String sliceByCodePoints(
            String source, int fromInclusive, int toExclusive) {

        Objects.requireNonNull(source, "source");

        int total = source.codePointCount(0, source.length());
        if (fromInclusive < 0
                || toExclusive < fromInclusive
                || toExclusive > total) {
            throw new IndexOutOfBoundsException(
                    "Invalid code-point range [" + fromInclusive
                    + ", " + toExclusive + "), total=" + total);
        }

        int startUtf16 = source.offsetByCodePoints(0, fromInclusive);
        int endUtf16 = source.offsetByCodePoints(
                startUtf16, toExclusive - fromInclusive);

        return source.substring(startUtf16, endUtf16);
    }
}
```

This is a **standalone utility class** that can be saved in `CodePointSlices.java`. How it works:

1. `codePointCount(0, source.length())` gets the total number of code points in the entire string.
2. Checks `0 <= fromInclusive <= toExclusive <= total` to prevent out-of-bounds slicing and define clear behavior for invalid indices.
3. `offsetByCodePoints(0, fromInclusive)` converts the starting code-point position into a UTF-16 index.
4. Advances by `toExclusive - fromInclusive` code points from the starting position to obtain the ending UTF-16 index.
5. Uses `substring(startUtf16, endUtf16)` on the **correct UTF-16 boundaries**.

The condition allows `fromInclusive == toExclusive`, in which case it returns an empty string. `source == null` is handled explicitly with `NullPointerException` from `Objects.requireNonNull`. The function does not silently alter or clamp invalid indices.

**Note on scope of guarantee:** For input strings with valid surrogate pairs, the function will not cut **between the two code units of a pair**. It does not validate or repair an already malformed UTF-16 string (containing unpaired surrogates). Section 8 explains further.

## 5. Complete Java 17 Program and Exact Output

To compile and run a single file directly, use the following version in `SafeCodePointSliceDemo.java`. The output intentionally prints code points in hexadecimal so it does not depend on how a terminal displays emojis.

```java
import java.util.Objects;

public class SafeCodePointSliceDemo {
    static String sliceByCodePoints(
            String source, int fromInclusive, int toExclusive) {

        Objects.requireNonNull(source, "source");

        int total = source.codePointCount(0, source.length());
        if (fromInclusive < 0
                || toExclusive < fromInclusive
                || toExclusive > total) {
            throw new IndexOutOfBoundsException("Invalid code-point range");
        }

        int start = source.offsetByCodePoints(0, fromInclusive);
        int end = source.offsetByCodePoints(
                start, toExclusive - fromInclusive);
        return source.substring(start, end);
    }

    public static void main(String[] args) {
        String text = "A" + new String(Character.toChars(0x1F600)) + "B";

        System.out.println("UTF-16 length = " + text.length());
        System.out.println("code points = "
                + text.codePointCount(0, text.length()));

        String broken = text.substring(0, 2);
        System.out.println("broken length = " + broken.length());
        System.out.println("broken ends high surrogate = "
                + Character.isHighSurrogate(
                        broken.charAt(broken.length() - 1)));

        int emojiStart = text.offsetByCodePoints(0, 1);
        int emojiEnd = text.offsetByCodePoints(0, 2);
        System.out.println("emoji UTF-16 range = ["
                + emojiStart + ", " + emojiEnd + ")");

        String emoji = sliceByCodePoints(text, 1, 2);
        System.out.printf("emoji code point = U+%X%n", emoji.codePointAt(0));

        String firstTwo = sliceByCodePoints(text, 0, 2);
        System.out.println("first two code points = "
                + firstTwo.codePointCount(0, firstTwo.length()));
        System.out.println("last code point = "
                + sliceByCodePoints(text, 2, 3));
        System.out.println("whole string unchanged = "
                + sliceByCodePoints(text, 0, 3).equals(text));
        System.out.println("empty slice length = "
                + sliceByCodePoints(text, 1, 1).length());
    }
}
```

Run with JDK 17 or newer:

```bash
javac SafeCodePointSliceDemo.java
java SafeCodePointSliceDemo
```

Expected output:

```text
UTF-16 length = 4
code points = 3
broken length = 2
broken ends high surrogate = true
emoji UTF-16 range = [1, 3)
emoji code point = U+1F600
first two code points = 2
last code point = B
whole string unchanged = true
empty slice length = 0
```

Explanation: The original string has 4 code units but 3 code points. `substring(0, 2)` leaves a lone high surrogate. Converting code point positions `1` and `2` into UTF-16 indices `1` and `3` extracts the complete emoji; valid slices never break surrogate pairs.

## 6. Ways to Iterate by Code Point

If you do not need `substring` over a specific range, you can iterate sequentially using `codePointAt` and `Character.charCount`.

```java
String text = "A" + new String(Character.toChars(0x1F600)) + "B";

for (int utf16Index = 0; utf16Index < text.length();) {
    int cp = text.codePointAt(utf16Index);
    System.out.printf("U+%X%n", cp);
    utf16Index += Character.charCount(cp);
}
```

Output:

```text
U+41
U+1F600
U+42
```

Why increment `utf16Index` by `Character.charCount(cp)`: non-BMP values take two code units. If you use `utf16Index++` as in a `char` loop, you will step onto the low surrogate and process boundaries incorrectly.

A more concise alternative is `String.codePoints()` (available since Java 9):

```java
text.codePoints().forEach(cp -> System.out.printf("U+%X%n", cp));
```

This produces the same three lines of output as the example above. `codePoints()` yields `int` values, making it convenient for inspecting, filtering, or building output. However, if you need the UTF-16 index of each code point, you still need to track code unit lengths or use `offsetByCodePoints`.

### Building Strings from Code Points Without Manually Assembling Surrogates

```java
String text = "A" + new String(Character.toChars(0x1F600)) + "B";
StringBuilder result = new StringBuilder();

text.codePoints()
        .limit(2)
        .forEach(cp -> result.appendCodePoint(cp));

String prefix = result.toString(); // "A" + emoji U+1F600
System.out.println(prefix.codePointCount(0, prefix.length())); // 2
```

`appendCodePoint` handles UTF-16 encoding for the code point value, avoiding manual construction of surrogate halves. When you only need to slice a range, `offsetByCodePoints + substring` usually expresses the intent more clearly; the stream example illustrates the approach of *building* a string by code point.

## 7. Boundary Cases to Check

| Input / Requirement | Expected Result |
| --- | --- |
| `source = ""`, slice `[0, 0)` | Returns `""` |
| `source = "ABC"`, slice `[1, 3)` | Returns `"BC"` |
| `source = "A😀B"`, slice `[1, 2)` | Returns the complete emoji 😀 |
| `source = "A😀B"`, slice `[0, 2)` | Returns `A` and the complete emoji 😀 |
| `source = "A😀B"`, slice `[2, 3)` | Returns `B` |
| `source = "A😀B"`, slice `[2, 2)` | Returns `""` |
| Negative index, start > end, or exceeding total code points | Throws `IndexOutOfBoundsException` in the example function |
| `source = null` | Throws `NullPointerException` with message mentioning `source` |

**Do not mix the two index systems.** If the system stores offsets returned by `String.indexOf(...)` or `Matcher.start()`, those are normally **UTF-16 indices**; do not pass them into `sliceByCodePoints` as if they were code point ordinals. Conversely, `offsetByCodePoints` takes a **starting UTF-16 position** and a **number of code points to move**, not two pure code-point indices.

If an external API specifies a count of “characters”, first clarify whether “character” means a UTF-16 code unit, a Unicode code point, or a **grapheme cluster** (a user-perceived character).

## 8. Two Important Limitations: Broken UTF-16 and Grapheme Clusters

### 8.1. Slicing by Code Point Does Not Fix Strings Already Containing Unpaired Surrogates

A Java `String` can contain high or low surrogate code units that do not form a valid pair, such as creating a string with a single `char`:

```java
String malformed = new String(new char[] {'A', '\uD83D'});
System.out.println(malformed.length()); // 2
System.out.println(malformed.codePointCount(0, malformed.length())); // 2
```

The `codePointCount` API counts an unpaired surrogate as one unit; `codePoints()` likewise returns that lone surrogate value as an `int` rather than synthesizing a valid emoji code point. Thus, choosing boundaries by code point only prevents **introducing** a split pair from a valid pair. If source data is already malformed, you need a policy to **validate, reject, or replace** invalid data before processing, depending on the input contract.

Do not call `new String(Character.toChars(...))` with a code point outside the Unicode range. `Character.toChars(int)` throws `IllegalArgumentException` for values that are not valid code points; treating surrogate code points as standalone characters also does not yield valid Unicode scalar values. Define the validity criteria for your input data.

### 8.2. One Code Point Is Not Necessarily One “Visible Character”

Some displayed characters are formed from **multiple code points**. For example, the letter `e` plus a combining acute accent:

```java
String combined = "e\u0301";
System.out.println(combined.length()); // 2
System.out.println(combined.codePointCount(0, combined.length())); // 2
```

This text usually displays much like “é”, yet it consists of two code points: `U+0065` and `U+0301`. Slicing by code point `[0, 1)` extracts only `e` and separates the combining acute accent. Similarly, many emojis with skin-tone modifiers, variation selectors, or zero-width joiner sequences contain multiple code points while being perceived by users as **one display cluster**.

Therefore, distinguish two goals:

- **Do not split surrogate pairs:** use code point APIs like `offsetByCodePoints` to obtain valid UTF-16 boundaries.
- **Do not split user-perceived character clusters:** you need a **grapheme cluster** segmentation algorithm conforming to Unicode rules and the runtime's Unicode version. Do not assume slicing by code points suffices for cursor character selection/deletion in an editor or for limiting displayed character counts.

`java.text.BreakIterator.getCharacterInstance(...)` can help identify text boundaries via the JDK API, though support for complex graphemes and emojis can depend on the JDK version/Unicode data. If full compliance with **extended grapheme clusters** and modern emoji sequences is required, verify results against real test data or use an appropriate Unicode segmentation library.

## 9. Notes on Performance and API Design

`offsetByCodePoints` may have to scan code units from the starting point to find the target position; `codePointCount` also scans the counted range. For occasional slices or typical strings, the clarity of `sliceByCodePoints` is a good priority. If performing many random-access queries on the same very long string, benchmark and consider prebuilding a **code-point index → UTF-16 index** lookup table to avoid repeated scanning.

When publishing an API, name parameters clearly, such as `fromCodePointIndex` and `toCodePointIndexExclusive`. If taking UTF-16 indices, name them `beginUtf16Index`/`endUtf16Index`. Clear naming prevents mixing indices from different APIs.

For operations that only select the **start/end by code point**, you can optimize the call using `offsetByCodePoints` from an appropriate starting position. Do not write `utf16Index + numberOfCodePoints` when the segment passes through emojis or non-BMP characters, because code point counts do not equal UTF-16 code unit counts.

## 10. Common Mistakes and Fixes

1. **Using `substring(0, n)` to get `n` code points.** `n` is interpreted as a number of code units. Fix with `substring(0, s.offsetByCodePoints(0, n))` after checking valid range.
2. **Using `s.length()` as the number of code points.** `length()` counts UTF-16 code units. To count code points, use `s.codePointCount(0, s.length())`.
3. **Incrementing the loop index `i++` after `codePointAt(i)`.** For non-BMP code points, increment by `Character.charCount(cp)` to skip the entire pair.
4. **Calling `charAt(i)` and treating the result as a complete Unicode character.** A `char` can be just half of a surrogate pair; use `codePointAt(i)` at code point boundaries.
5. **Counting code points and passing the index directly to `substring`.** Those are two different coordinate systems; convert with `offsetByCodePoints`.
6. **Assuming code-point processing always preserves visible characters.** Combining marks and multi-code-point emojis require grapheme cluster segmentation if that is the goal.
7. **Assuming slicing by code point fixes all invalid UTF-16.** It does not repair lone surrogates already present in the input; validate separately when data must be valid Unicode scalar values.
8. **Not validating bounds and `null`.** Clear error messages and half-open range conventions help API callers avoid off-by-one bugs.

## 11. Self-Check

For the string `"X😀YZ"` consisting of code points `X`, `😀`, `Y`, `Z`:

- `length()` equals **5** (1 + 2 + 1 + 1 code units).
- `codePointCount(0, length())` equals **4**.
- Code point range `[1, 3)` should return **the emoji 😀 followed by `Y`**.
- Correspondingly, the two UTF-16 indices passed to `substring` are **1** and **4**.
- `substring(1, 3)` extracts only the emoji 😀 because UTF-16 range `[1, 3)` covers the two surrogate halves.
- `substring(0, 2)` takes `X` along with the high surrogate and drops the low surrogate: this is the result to avoid.

**Key takeaway:** `String` is indexed by **UTF-16 code units**, whereas a problem may require **Unicode code points**. To extract by code point, **convert code point boundaries to UTF-16 indices with `offsetByCodePoints` before calling `substring`**. If you need to keep user-perceived characters intact, also consider **grapheme cluster** boundaries.
