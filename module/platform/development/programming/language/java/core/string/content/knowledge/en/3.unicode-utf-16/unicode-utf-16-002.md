# `String` Uses Indexing by UTF-16 `char` Units

## 1. Objectives and Key Takeaways

In Java, `String` indices such as the parameters to `charAt`, `substring`, `indexOf`, and `codePointAt` are measured in **UTF-16 code units** (16-bit `char` units), not by default in Unicode code points or user-perceived characters.

For example, the string `"A🚀B"` has 3 Unicode code points, but `length() == 4`, because the `🚀` character requires two UTF-16 code units. Therefore, the position of `B` in the string is **3**, not **2**.

This lesson helps you read and work accurately with Java indices, avoid splitting surrogate pairs in half, and convert positions when you want to process by code points.

## 2. Three Concepts to Distinguish

- **UTF-16 code unit:** a 16-bit unit. Java's `char` type holds exactly one code unit, with values from `0x0000` to `0xFFFF`.
- **Unicode code point:** an integer value used to identify a Unicode code position, such as `U+0041` (`A`) and `U+1F680` (`🚀`). A code point in the supplementary range `U+10000..U+10FFFF` is represented by **two** UTF-16 code units called a *surrogate pair*.
- **Grapheme cluster:** a cluster of characters that a reader typically perceives as a single display character. A cluster can contain multiple code points, such as a base letter + combining mark or an emoji joined by a connector.

| Text | UTF-16 code units (`length`) | Code points | Meaning |
| --- | ---: | ---: | --- |
| `"ABC"` | 3 | 3 | Each ASCII character takes one `char`. |
| `"A🚀B"` | 4 | 3 | `🚀` requires two `char` values. |
| `"é"` (U+00E9) | 1 | 1 | Accent is precomposed in one code point. |
| `"e\u0301"` (U+0065 + U+0301) | 2 | 2 | Letter `e` and combining acute accent; may look like `é`. |

Java stores strings immutably and provides APIs that operate on **UTF-16 units**. Note: the JVM's internal physical storage may be optimized (for example, Compact Strings), but **the public indexing behavior still follows UTF-16**.

## 3. Index Diagram: `"A🚀B"`

The Unicode code point for rocket is `U+1F680`, encoded by the surrogate pair `\uD83D` and `\uDE80`:

| `char` index (UTF-16) | `charAt(index)` value | Meaning |
| ---: | --- | --- |
| 0 | `U+0041` | `A` |
| 1 | `U+D83D` | *High surrogate* of `🚀` |
| 2 | `U+DE80` | *Low surrogate* of `🚀` |
| 3 | `U+0042` | `B` |

The boundaries for slicing the string into complete code points are `0 | A | 1 | 🚀 | 3 | B | 4`. **Position 2 lies in the middle of the surrogate pair** and is not a safe boundary to split the rocket into two strings.

From this example:
- `text.length()` → `4`: number of UTF-16 code units.
- `text.codePointCount(0, text.length())` → `3`: number of code points.
- `text.charAt(1)` → a `char` with value `U+D83D`; **not** the entire rocket.
- `text.codePointAt(1)` → `U+1F680`, because index 1 starts a valid surrogate pair.
- `text.codePointAt(2)` → `U+DE80`: starts at the low surrogate, so it **does not look backward** to combine with the preceding element.
- `text.indexOf("B")` → `3`: UTF-16 index of `B`.
- `text.substring(1, 3)` → `"🚀"`: range `[1, 3)` captures both code units.

If you use `substring(1, 2)`, the result contains only the high surrogate. Java still allows creating strings containing an unpaired surrogate, but such text does not represent a complete Unicode scalar value; its rendering and encoding on external output may behave unexpectedly.

## 4. APIs That Use UTF-16 Indices

| API | What unit are its arguments or results in? | Example with `"A🚀B"` |
| --- | --- | --- |
| `length()` | Returns the **number of UTF-16 `char` units**. | `4` |
| `charAt(index)` | `index` is a `char` position in `[0, length())`. | `charAt(1) == '\uD83D'` |
| `substring(beginIndex, endIndex)` | Both endpoints are UTF-16 positions, end exclusive. | `substring(1, 3)` is `🚀` |
| `subSequence(start, end)` | Both endpoints are UTF-16 positions. | `subSequence(1, 3)` is `🚀` |
| `indexOf(String)` and `lastIndexOf(String)` | Returns the **`char` position** of the matching substring, or `-1`. | `indexOf("B") == 3` |
| `indexOf(int codePoint)` | Argument is a code point, but **the result is a UTF-16 index**. | `indexOf(0x1F680) == 1` |
| `codePointAt(index)` | `index` is a UTF-16 position; reads the code point starting there when a valid pair is present. | `codePointAt(1) == 0x1F680` |
| `codePointBefore(index)` | `index` is a UTF-16 boundary; reads the code point immediately before it. | `codePointBefore(3) == 0x1F680` |
| `codePointCount(begin, end)` | Range `[begin, end)` is specified **in UTF-16**; result is the number of code points. | `codePointCount(0, 4) == 3` |
| `offsetByCodePoints(index, offset)` | Takes a UTF-16 `index` and a **code point** offset; returns the new **UTF-16 index**. | `offsetByCodePoints(0, 2) == 3` |

Some APIs have overloads taking `fromIndex`, such as `indexOf(ch, fromIndex)` or `lastIndexOf(str, fromIndex)`. `fromIndex` is also a UTF-16 index. Range-based APIs like `StringBuilder.delete(start, end)` and positions returned by `java.util.regex.Matcher.start()/end()` also typically use UTF-16 indices.

Do not assume that an arbitrary index is a code point boundary. `offsetByCodePoints` advances by code points starting from the position you provide; if the starting position is already *inside* a surrogate pair, that shift does not automatically repair a split sequence.

## 5. Java 17+ Demonstration Program

Save the file `Utf16IndexDemo.java` with the following content:

```java
import java.util.Arrays;

public class Utf16IndexDemo {
    public static void main(String[] args) {
        String text = "A🚀B";

        System.out.println("length = " + text.length());
        System.out.println("code points = "
                + text.codePointCount(0, text.length()));

        for (int i = 0; i < text.length(); i++) {
            System.out.printf("charAt(%d) = U+%04X%n",
                    i, (int) text.charAt(i));
        }

        System.out.printf("codePointAt(1) = U+%X%n",
                text.codePointAt(1));
        System.out.printf("codePointAt(2) = U+%X%n",
                text.codePointAt(2));
        System.out.println("indexOf(B) = " + text.indexOf("B"));
        System.out.println("indexOf(rocket) = " + text.indexOf("🚀"));

        int begin = text.offsetByCodePoints(0, 1);
        int end = text.offsetByCodePoints(begin, 1);
        System.out.println("slice = " + text.substring(begin, end));
        System.out.println("slice range = " + begin + ".." + end);

        String brokenHalf = text.substring(1, 2);
        System.out.println("high surrogate only = "
                + Character.isHighSurrogate(brokenHalf.charAt(0)));
        System.out.println("codePoints array = "
                + Arrays.toString(text.codePoints().toArray()));
    }
}
```

Compile and run in a UTF-8 display environment:

```bash
javac -encoding UTF-8 Utf16IndexDemo.java
java Utf16IndexDemo
```

Expected output:

```text
length = 4
code points = 3
charAt(0) = U+0041
charAt(1) = U+D83D
charAt(2) = U+DE80
charAt(3) = U+0042
codePointAt(1) = U+1F680
codePointAt(2) = U+DE80
indexOf(B) = 3
indexOf(rocket) = 1
slice = 🚀
slice range = 1..3
high surrogate only = true
codePoints array = [65, 128640, 66]
```

**What to observe:** `charAt(1)` and `charAt(2)` are two halves of a single code point; `substring(1, 3)` is valid because it includes both, whereas `substring(1, 2)` splits the pair in half. `indexOf("🚀")` and `indexOf(0x1F680)` both point to UTF-16 position **1**, while `indexOf("B")` returns **3**.

## 6. Slicing a String by Code Points Without Splitting Surrogate Pairs

When the requirement is "take `count` code points, starting from the `from`-th code point", do **not** call `substring(from, from + count)` directly. First, convert the code point indices into UTF-16 indices.

The following helper method is **part of a Java class** (for example, placed inside `Utf16IndexDemo`), not a standalone runnable file:

```java
static String sliceByCodePoints(String text, int from, int count) {
    java.util.Objects.requireNonNull(text, "text");

    int total = text.codePointCount(0, text.length());
    java.util.Objects.checkFromIndexSize(from, count, total);

    int beginUtf16 = text.offsetByCodePoints(0, from);
    int endUtf16 = text.offsetByCodePoints(beginUtf16, count);
    return text.substring(beginUtf16, endUtf16);
}
```

Example calls inside `main`:

```java
String text = "A🚀B";
System.out.println(sliceByCodePoints(text, 1, 1)); // 🚀
System.out.println(sliceByCodePoints(text, 1, 2)); // 🚀B
System.out.println(sliceByCodePoints(text, 3, 0).isEmpty()); // true
```

Explanation:
1. `codePointCount` computes the total number of code points, used to verify that the range `[from, from + count)` is within valid bounds.
2. `offsetByCodePoints(0, from)` finds the UTF-16 boundary after the first `from` code points.
3. `offsetByCodePoints(beginUtf16, count)` finds the boundary after another `count` code points.
4. `substring(beginUtf16, endUtf16)` slices using **the exact index type** required by this API.

The method preserves supplementary code points when the input string has valid surrogate pairs. If the input already contains unpaired surrogates, Java may count an unpaired surrogate as a code point when using these APIs; the method is not a well-formed Unicode validator.

## 7. Iterating Over a String: `char` or Code Point?

**Iterate by UTF-16 code units** when handling low-level positions or interacting with APIs requiring `char` indices:

```java
String text = "A🚀B";
for (int i = 0; i < text.length(); i++) {
    char unit = text.charAt(i);
    // A loop may receive a high or low surrogate individually.
}
```

**Iterate by Unicode code points** when you need to process intact code points:

```java
String text = "A🚀B";
text.codePoints().forEach(cp ->
        System.out.printf("U+%X%n", cp));
```

Output of the second snippet:

```text
U+41
U+1F680
U+42
```

`text.chars()` returns an `IntStream` of **UTF-16 code units**, whereas `text.codePoints()` returns an `IntStream` of **code points** (combining valid surrogate pairs). Therefore, `chars()` and `codePoints()` are not interchangeable when a string contains characters outside the BMP.

If you need to track **both the UTF-16 position and the code point**, iterate by variable step size:

```java
String text = "A🚀B";
for (int i = 0; i < text.length(); ) {
    int cp = text.codePointAt(i);
    System.out.printf("UTF-16 index %d -> U+%X%n", i, cp);
    i += Character.charCount(cp);
}
```

Output:

```text
UTF-16 index 0 -> U+41
UTF-16 index 1 -> U+1F680
UTF-16 index 3 -> U+42
```

`Character.charCount(cp)` returns `2` when the code point is outside the BMP, and `1` otherwise. This traversal keeps the index at the start of each code point if started from a valid boundary.

## 8. "One Displayed Character" Can Still Be Multiple Code Points

Do not mechanically replace every "character" problem with counting code points. For example:

```java
String composed = "\u00E9"; // é: one code point
String decomposed = "e\u0301"; // e + combining acute accent: two code points

System.out.println(composed.length()); // 1
System.out.println(decomposed.length()); // 2
System.out.println(decomposed.codePointCount(0, decomposed.length())); // 2
System.out.println(composed.equals(decomposed)); // false
```

Two strings can look identical visually yet differ in their code unit and code point sequences. If you need to compare canonically equivalent Unicode forms, you can consider normalizing with `java.text.Normalizer`, such as `Normalizer.normalize(text, Normalizer.Form.NFC)`. Normalization does not turn indexing APIs into grapheme cluster APIs.

If business logic needs cursor movement or length limits **by user-perceived characters**, you need a grapheme cluster segmentation algorithm following the appropriate Unicode rules. Do not treat `length()` or `codePointCount()` as the default answer for all languages and combined emojis.

## 9. Common Mistakes and How to Avoid Them

| Mistake | Consequence | How to Handle |
| --- | --- | --- |
| Assuming `length()` is the number of code points. | Overcounts for `🚀`, `😀`, and many non-BMP characters. | Use `codePointCount` when you genuinely need the code point count. |
| Using `charAt(i)` to iterate "each Unicode character". | Surrogate pairs are split into two reads. | Use `codePointAt` with a `Character.charCount` step or `codePoints()`. |
| Passing code point indices directly to `substring`. | Slices at the wrong position or splits a surrogate pair. | Convert boundaries with `offsetByCodePoints` before calling `substring`. |
| Thinking `indexOf` returns a code point position. | Index shifts after supplementary characters. | Treat the result as a UTF-16 index, compatible with `substring` / `charAt`. |
| Calling `codePointAt` at the low surrogate of a valid pair. | Receives only the low surrogate value. | Point to the high surrogate (start of the code point) or iterate from the start. |
| Assuming "1 code point = 1 displayed character". | Mishandles combining marks and emojis with variation selectors/joiners. | Determine whether the task needs code units, code points, or grapheme clusters before choosing an API. |

Calls such as `charAt(-1)`, `charAt(length())`, and `substring` with invalid indices throw an index exception (`IndexOutOfBoundsException` or a subclass). Even when an index is within bounds, it **can still lie between two surrogates**, so bounds checking alone does not guarantee a sensible Unicode boundary.

## 10. Self-Check Exercises

Given the code snippet:

```java
String s = "Hi😀!";
```

1. What is `s.length()`? **5**: `H` and `i` are 2 `char`s, `😀` is 2 `char`s, `!` is 1 `char`.
2. What is `s.codePointCount(0, s.length())`? **4**.
3. What does `s.indexOf("!")` return? **4**, because it is a UTF-16 index.
4. What does `s.substring(2, 4)` return? **`"😀"`**, consisting of exactly the two code units of the surrogate pair.
5. Does `s.substring(2, 3)` extract the complete emoji? **No**, it only takes the high surrogate.
6. What is `s.offsetByCodePoints(0, 3)`? **4**, the boundary after the third code point.
7. If you want to extract the third code point (code point index `2`), what should you do? Use `int start = s.offsetByCodePoints(0, 2); int end = s.offsetByCodePoints(start, 1);` and then `s.substring(start, end)`.

## References

- [Java SE 17 — `String` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17 — `Character` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://www.unicode.org/reports/tr29/)