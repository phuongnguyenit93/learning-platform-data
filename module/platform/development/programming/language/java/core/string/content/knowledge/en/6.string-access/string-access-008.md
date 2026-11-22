# Choosing the Right Index Unit Before Iterating or Slicing a String in Java

When iterating over or slicing a `String`, the first question is not “use `charAt()` or `substring()`?” but rather **what unit does a position in the business requirement represent?** Java provides indexing by **UTF-16 code unit**, APIs for handling **Unicode code points**, and text-segmentation tools for **user-perceived characters** (grapheme clusters). These three units sometimes have the same length for ASCII letters, but they diverge with emoji, combining marks, and many writing systems.

Choosing the wrong unit can cause a program to split emoji in half, drop Vietnamese accents, miscount lengths, or place a cursor at an improper position. This lesson focuses on how to identify the right unit **before iterating or slicing a string**, and then select the corresponding API.

## 1. Three units to distinguish

| Unit | Meaning | API or tool in Java | When to use |
| --- | --- | --- | --- |
| **UTF-16 code unit** | A 16-bit code unit, corresponding to a `char` value | `length()`, `charAt()`, `substring()`, `toCharArray()`, `chars()` | Working with Java APIs that accept `String` indices, ASCII characters, or data already defined in terms of `char` |
| **Unicode code point** | A Unicode value; may require one or two UTF-16 code units | `codePointAt()`, `codePointCount()`, `offsetByCodePoints()`, `codePoints()`, `Character.charCount()` | Iterating over Unicode code points, identifying non-BMP emoji/code points, computing slice bounds by code point count |
| **Grapheme cluster** | A character cluster typically perceived by users as a single displayed character | Text segmentation tools such as `BreakIterator`; for full UAX #29 compliance, consider ICU4J or a tested library | Placing a cursor, deleting “one character” in a UI, limiting user-visible character count, truncating display labels |

**No single index unit is right for every situation.** If a Java API expects `beginIndex` of `substring()`, it needs a **UTF-16 offset**. If the requirement is “take the first three Unicode code points”, you must convert the code-point-based position into a UTF-16 offset before calling `substring()`. If it is “delete exactly one character the user sees”, even a code point can be too small because a visible cluster can consist of multiple code points.

Additional note: **UTF-8 bytes are not `String` indices**. Byte positions in a file or stream are a fourth unit, computed after encoding; they cannot be used directly as `substring()` indices.

## 2. Foundational example: one string, three ways to count

Use the following Java string:

~~~java
String text = "A😀e\u0301B";
~~~

In the code, `e\u0301` is the letter `e` followed by the combining acute accent `U+0301`. When rendered, they usually look like one letter “é”, yet **they are two code points**. The string has this structure:

| UTF-16 index | `char` element | Role |
| ---: | --- | --- |
| 0 | `A` | One code unit, one code point |
| 1 | `\uD83D` | High surrogate of 😀 |
| 2 | `\uDE00` | Low surrogate of 😀 |
| 3 | `e` | Code point for letter e |
| 4 | `\u0301` | Code point for combining acute accent |
| 5 | `B` | One code unit, one code point |

Therefore:

- **6 UTF-16 code units:** `text.length() == 6`.
- **5 Unicode code points:** A, 😀, e, combining acute accent, B.
- **Typically 4 grapheme clusters:** A, 😀, e + acute accent, B (rendering and cluster boundaries must be determined according to the relevant segmentation standard).

The emoji 😀 is code point `U+1F600`, outside the Basic Multilingual Plane (BMP), so it needs **two UTF-16 code units** (a surrogate pair). By contrast, the letter `e` and the accent `U+0301` each need only one code unit yet combine into one cluster perceived by the reader as a single character.

The precomposed letter `"é"` (`U+00E9`) differs in code point sequence from `"e\u0301"`. Two strings may look identical, while their Java lengths and code point contents differ. Unicode normalization, such as NFC, can help handle certain canonically equivalent representations; normalization **does not replace** determining grapheme cluster boundaries.

## 3. If your target is UTF-16 indices: use charAt and substring

Common APIs operate directly on **UTF-16 code unit** indices:

- `text.length()`: number of UTF-16 units, not automatically the number of visible characters.
- `text.charAt(index)`: returns exactly **one `char`** at `index`. Valid indices run from `0` to `length() - 1`.
- `text.substring(beginIndex, endIndex)`: extracts the slice **[beginIndex, endIndex)**, inclusive of start, exclusive of end. `beginIndex == endIndex` is valid if in range and returns an empty string.
- `text.subSequence(begin, end)` also uses UTF-16 index units.
- `text.chars()` returns an `IntStream` containing the UTF-16 `char` values widened to `int`; **different** from `codePoints()`.

With the example above:

~~~java
String text = "A😀e\u0301B";
System.out.println(text.length());                  // 6
System.out.println(text.substring(1, 3).equals("😀")); // true
System.out.println(text.substring(1, 2).length());  // 1
System.out.println(
        Character.isHighSurrogate(text.substring(1, 2).charAt(0))); // true
~~~

This is an **illustrative code snippet placed inside a method**, not a standalone Java class. The results are `6`, `true`, `1`, and `true`, respectively.

The region `[1, 3)` takes both the high and low surrogates, keeping the emoji 😀 intact. The region `[1, 2)` takes only **one half** of the surrogate pair. Java can still construct a `String` containing a lone surrogate, but it is no longer a complete emoji; when encoded or displayed, replacement characters may appear. Similarly, the region `[3, 4)` takes the letter e without the accent at `[4, 5)`.

**Rule:** UTF-16 indices are appropriate when the API or data contract is specified in terms of `char`. When slicing natural text, verify that start/end points **do not split a surrogate pair** and, when important for the UI, **do not split a visible character cluster**.

## 4. If your target is Unicode code points: iterate with codePointAt

A Unicode code point outside the BMP occupies **two** UTF-16 `char`s. Therefore, the loop `for (int i = 0; i < text.length(); i++)` combined with `charAt(i)` is a loop by **code unit**, not by code point.

To iterate over consecutive code points, use `codePointAt(offset)` and advance the offset by `Character.charCount(cp)`:

~~~java
String text = "A😀e\u0301B";

// Code inside a Java method:
for (int offset = 0; offset < text.length(); ) {
    int cp = text.codePointAt(offset);
    System.out.printf("U+%04X%n", cp);
    offset += Character.charCount(cp);
}
~~~

Output:

~~~text
U+0041
U+1F600
U+0065
U+0301
U+0042
~~~

At the position of 😀, `codePointAt(1)` merges the high and low surrogates into `U+1F600`; `Character.charCount(0x1F600)` equals `2`, so the index jumps from 1 to 3. For A, e, combining acute accent, and B, `charCount(cp)` equals `1`.

**Important:** `codePointAt(index)` accepts a **UTF-16 index**, not a “code point index”. It returns the **code point starting at that offset** (if it is a high surrogate immediately followed by a low surrogate); calling it with an index pointing to a low surrogate returns only the low surrogate value. Therefore, always convert offsets properly before accessing.

### Two other options: codePoints and codePointCount

- `text.codePoints()` creates an `IntStream` iterating over code points. Use this when you want `map`, `filter`, or stream processing without manually updating UTF-16 offsets.
- `text.codePointCount(beginIndex, endIndex)` counts code points in a region whose boundaries are still **UTF-16 offsets**. For an intact string, `text.codePointCount(0, text.length())` gives the code point count.
- `text.chars()` creates a stream of code units, so when non-BMP emoji are present, it emits **two elements** instead of one.

A `String` can contain lone surrogates; Java's code point APIs treat an unpaired surrogate as a distinct value when counting/iterating. Do not assume every Java string holds a valid sequence of Unicode scalar values if input data can be malformed.

## 5. If you want to slice by code point count: convert to UTF-16 offsets

`substring()` **has no overload accepting code point indices**. You must convert from code-point positions to UTF-16 offsets using `offsetByCodePoints()`:

~~~java
String text = "A😀e\u0301B";
int begin = text.offsetByCodePoints(0, 1); // 1 code point from the start of the string
int end = text.offsetByCodePoints(begin, 1); // after the emoji, UTF-16 offset = 3
String emoji = text.substring(begin, end);
System.out.println(emoji.equals("😀")); // true
~~~

Explanation: `offsetByCodePoints(index, codePointOffset)` takes a **UTF-16 index** and a step count measured in **code points**, returning a new **UTF-16 index**. This handles valid surrogate pairs; if requested to move outside the valid range, the method throws `IndexOutOfBoundsException`.

Common pattern to convert two boundaries:

~~~java
int utf16Start = text.offsetByCodePoints(0, startPointIndex);
int utf16End = text.offsetByCodePoints(utf16Start, pointCount);
String part = text.substring(utf16Start, utf16End);
~~~

This is an **illustrative code snippet**: `startPointIndex` and `pointCount` must be validated beforehand. The value `pointCount` is the **number of code points to extract**, distinct from an “end index”.

### Utility method with range checking

~~~java
static String sliceByCodePoints(String text, int startPoint, int count) {
    java.util.Objects.requireNonNull(text, "text");
    int total = text.codePointCount(0, text.length());

    if (startPoint < 0 || count < 0 || startPoint > total - count) {
        throw new IndexOutOfBoundsException("Invalid code point range");
    }

    int begin = text.offsetByCodePoints(0, startPoint);
    int end = text.offsetByCodePoints(begin, count);
    return text.substring(begin, end);
}
~~~

This is an **illustrative method**, placed inside a Java class. Checking `startPoint > total - count` avoids using addition `startPoint + count` that could overflow `int`. An empty range at the end `startPoint == total, count == 0` is valid. If `count` is negative or the selection exceeds the code point count, the function proactively reports an error.

**Limitation of this solution:** it keeps **code points** intact, yet it can still cut between the letter e and its combining accent if only one code point is requested. When you need to preserve a visible character, segment by grapheme cluster.

## 6. Standalone Java 17+ program

Create the file **StringIndexUnitsDemo.java**:

~~~java
import java.util.Objects;

public class StringIndexUnitsDemo {
    static String sliceByCodePoints(String text, int startPoint, int count) {
        Objects.requireNonNull(text, "text");
        int total = text.codePointCount(0, text.length());
        if (startPoint < 0 || count < 0 || startPoint > total - count) {
            throw new IndexOutOfBoundsException("Invalid code point range");
        }
        int begin = text.offsetByCodePoints(0, startPoint);
        int end = text.offsetByCodePoints(begin, count);
        return text.substring(begin, end);
    }

    public static void main(String[] args) {
        String text = "A😀e\u0301B";

        System.out.println("UTF-16 units = " + text.length());
        System.out.println("Code points = "
                + text.codePointCount(0, text.length()));
        System.out.println("index 1 is high surrogate = "
                + Character.isHighSurrogate(text.charAt(1)));
        System.out.println("substring(1, 2) keeps whole emoji = "
                + text.substring(1, 2).equals("😀"));
        System.out.println("substring(1, 3) keeps whole emoji = "
                + text.substring(1, 3).equals("😀"));

        String firstTwo = sliceByCodePoints(text, 0, 2);
        String emoji = sliceByCodePoints(text, 1, 1);
        String accentPair = sliceByCodePoints(text, 2, 2);

        System.out.println("firstTwo code points = "
                + firstTwo.codePointCount(0, firstTwo.length()));
        System.out.println("emoji UTF-16 units = " + emoji.length());
        System.out.println("accentPair code points = "
                + accentPair.codePointCount(0, accentPair.length()));
        System.out.println("accentPair UTF-16 units = " + accentPair.length());

        String onePoint = sliceByCodePoints(text, 2, 1);
        System.out.println("onePoint includes combining accent = "
                + onePoint.equals("e\u0301"));

        StringBuilder codePoints = new StringBuilder();
        text.codePoints().forEach(cp -> {
            if (codePoints.length() > 0) {
                codePoints.append(' ');
            }
            codePoints.append(String.format("U+%04X", cp));
        });
        System.out.println("Values = " + codePoints);
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac -encoding UTF-8 StringIndexUnitsDemo.java
java StringIndexUnitsDemo
~~~

Output:

~~~text
UTF-16 units = 6
Code points = 5
index 1 is high surrogate = true
substring(1, 2) keeps whole emoji = false
substring(1, 3) keeps whole emoji = true
firstTwo code points = 2
emoji UTF-16 units = 2
accentPair code points = 2
accentPair UTF-16 units = 2
onePoint includes combining accent = false
Values = U+0041 U+1F600 U+0065 U+0301 U+0042
~~~

**Interpretation:** `substring(1, 2)` cuts off the low surrogate so it does not preserve the emoji; `substring(1, 3)` captures the whole pair. `sliceByCodePoints()` reliably selects the full emoji as one code point, yet when selecting only the code point e, it **does not automatically pull along the combining acute accent** at the next code point. This proves that *code-point-safe slicing is not yet sufficient for visible-character-safe slicing*.

## 7. If you need a character the user sees: grapheme cluster

Grapheme clusters are the better unit when an application needs to:

- Delete the character at the cursor in a text box the way users expect.
- Limit display name length by perceived character count, rather than `char` or code points.
- Truncate labels or messages without separating combining marks or complex emoji sequences.
- Move a cursor across character clusters in multilingual text.

Examples of things that can consist of **multiple code points** yet form one displayed cluster: `e\u0301` (letter and accent), flags built from *regional indicators*, emoji with skin-tone modifiers, or emoji sequences with a *zero-width joiner* (ZWJ). Code point indexing sees each individual piece; the boundary of a visible character requires additional Unicode segmentation rules.

Java has `java.text.BreakIterator.getCharacterInstance(Locale)` to find character boundaries depending on locale and JDK version. The API returns **UTF-16 offsets**, so they work directly with `substring()`. However, segmentation behavior for ZWJ emoji, flags, and newer Unicode cases can depend on the JDK, Unicode data, and locale. When requiring **full Extended Grapheme Clusters per Unicode UAX #29** or cross-platform UI consistency, test real cases and consider an up-to-date segmentation library such as ICU4J.

### How to use BreakIterator boundary by boundary

~~~java
import java.text.BreakIterator;
import java.util.Locale;

// Code snippet inside a Java method:
String text = "Cafe\u0301!";
BreakIterator boundaries = BreakIterator.getCharacterInstance(Locale.ROOT);
boundaries.setText(text);

int start = boundaries.first();
for (int end = boundaries.next();
     end != BreakIterator.DONE;
     start = end, end = boundaries.next()) {
    String cluster = text.substring(start, end);
    System.out.println(cluster);
}
~~~

This is an **illustrative code snippet**, not a standalone program. `BreakIterator` returns `[start, end)` ranges as **UTF-16 indices** and `substring()` extracts the corresponding slice. Exact segmentation results are determined by the segmenter's version/configuration; applications should test on real text before using it to limit or edit content.

**Do not use “one `char` = one user character”.** Likewise, do not assume “one Unicode code point = one user character”. For complex display clusters, the grapheme unit is closest to UI expectations.

### Three illustrative slices for the same text

Given `String text = "A😀e\u0301B";`:

| Actual requirement | Unit to choose | Approach |
| --- | --- | --- |
| Get the `char` at UTF-16 offset 1 | UTF-16 code unit | `text.charAt(1)` → high surrogate, **not a complete emoji** |
| Get the second Unicode code point | Code point | Convert the second point to a UTF-16 offset, `codePointAt(offset)` → `U+1F600` |
| Get the third cluster as displayed | Grapheme cluster | Segment into clusters A, 😀, e+accent, B using an appropriate grapheme algorithm, then slice by the returned boundaries |
| Get content in UTF-16 range `[3, 5)` | UTF-16 code unit | `text.substring(3, 5)` → e plus combining accent, still two code points |
| Get two code points starting at code point index 2 | Code point | `sliceByCodePoints(text, 2, 2)` → e plus accent; correct because the requirement specifically asks for two code points |

In the table, “second” and “third” use **1-based** counting in natural language; Java APIs still count offsets from **0**. Input conventions must be agreed upon before writing code.

## 8. Choosing the unit by practical goal

| Situation | Recommended decision | Reason |
| --- | --- | --- |
| Receiving indices from `String.indexOf()` or passing into `substring()` | Keep **UTF-16 offsets** | APIs return/accept positions in the same unit; avoid mixing index units |
| Iterating over `char`s for ASCII data or ASCII-constrained formats | **Code unit**, assuming ASCII has been verified | Each ASCII character occupies one UTF-16 unit |
| Counting/iterating Unicode code points of text | **Code point** | A code point outside the BMP can require two `char`s |
| Taking the first *n* code points of a string | **Code point** + `offsetByCodePoints()` | Safely convert to a UTF-16 offset before calling `substring()` |
| Truncating by “n user-visible characters” | **Grapheme cluster** | Avoids splitting combining marks, joined emoji, and multi-code-point clusters |
| Computing file size or protocol byte limit | **Bytes in a specified charset** | `length()` does not count UTF-8 bytes |
| Truncating a string by display width in a terminal | Also need **glyph/cell width** | Even grapheme count does not necessarily equal terminal display cells |
| Finding word/sentence boundaries | **Word/sentence** segmentation, not just graphemes | Word/sentence boundaries follow separate rules |

**Important example with `indexOf()`:** if `int p = text.indexOf("B");`, the value `p` is a UTF-16 offset; you can immediately call `text.substring(0, p)`. Do not treat `p` as a code point count and pass it into `offsetByCodePoints(0, p)`, because when emoji are present, “converting a second time” leads to the wrong position or an exception.

## 9. Common mistakes

1. **Iterating with `charAt(i)` and treating each step as a Unicode character.** With non-BMP emoji, the code processes two surrogates separately. If you need code points, use `codePointAt()` and advance `i` by `Character.charCount(cp)`, or use `codePoints()`.
2. **Using `substring(0, n)` to take n code points.** `n` in the call is a UTF-16 offset. Convert via `offsetByCodePoints()`.
3. **Counting with `length()` to enforce a “max 10 visible characters” rule.** UI rules typically require grapheme clusters and sometimes product-specific policies; `length()` only counts code units.
4. **Receiving a code point offset and passing it straight into `charAt()`.** `charAt()` always requires a UTF-16 index.
5. **Assuming a code point always corresponds to one glyph.** Combining marks, ZWJ sequences, variation selectors, flags, and supplementary emoji can combine multiple code points into one display cluster.
6. **Using `codePoints()` to truncate displayed text without checking clusters.** It does not break surrogate pairs, yet can still detach accents or emoji components.
7. **Assuming `BreakIterator` on every JDK gives identical boundaries for complex emoji.** Test the specific JDK version, locale, and Unicode dataset for your requirements.
8. **Mixing UTF-8 byte positions with `String` indices.** Byte offsets must be decoded/mapped via the charset; they cannot serve as direct `substring()` indices.
9. **Forgetting to check bounds and negative numbers.** For `charAt()`, negative indices or indices equal to `length()` throw `StringIndexOutOfBoundsException`; `substring()` also fails for out-of-range regions or `begin > end`. For code-point slicing helpers, check the actual code point count.
10. **Forgetting that `String` can contain lone surrogates.** Java APIs can still observe these values, so when receiving text from untrusted sources, validate if well-formed Unicode data is required.

## 10. Checklist before writing a loop or substring

Answer these questions in order:

1. **What is the requirement?** Java `char`, Unicode code point, UI character, or file byte?
2. **Which API produces the index?** If it comes from `indexOf()`, `Matcher.start()`, `BreakIterator`, or `substring()`, check the UTF-16 index contract; if it is a number from a business rule, verify which unit is being counted.
3. **Can non-BMP Unicode appear?** Test with an emoji like 😀 to catch loops that split surrogate pairs.
4. **Can combining marks or ZWJ emoji appear?** Test `e\u0301` and composite emoji to check whether code points suffice or grapheme clusters are needed.
5. **Are the boundaries valid?** For UTF-16: `0 <= begin <= end <= length()`. For code points: `0 <= startPoint`, `0 <= count`, `startPoint + count <= totalCodePoints` (check safely using subtraction if needed).
6. **Every conversion must be explicit.** Variable names like `utf16Offset`, `codePointIndex`, `graphemeBoundary` help prevent unit mix-ups.
7. **Test with diverse sample inputs.** Empty string, ASCII, Vietnamese, non-BMP emoji, base letter + combining mark, composite emoji, and data with lone surrogates if possible.

## 11. Self-check questions

**Question 1.** Given `String s = "😀X";`, why does `s.charAt(1)` not return X?

**Answer:** the emoji occupies UTF-16 offsets 0 and 1; `s.charAt(1)` is the low surrogate, while X is at offset 2.

**Question 2.** Does `s.substring(0, 1)` mean “take the first Unicode code point”?

**Answer:** no. It takes one UTF-16 code unit, which may be only a high surrogate. To take one code point, use `s.substring(0, s.offsetByCodePoints(0, 1))`.

**Question 3.** Why does the string `"e\u0301"` have `length() == 2` and `codePointCount(0, 2) == 2` yet usually render as a single letter?

**Answer:** the letter e and the combining acute accent are two BMP code points, each occupying one UTF-16 code unit; together they typically form one visible grapheme cluster.

**Question 4.** If `indexOf("B")` returns offset 5 in `"A😀e\u0301B"`, do you need to convert 5 to a code point index before calling `substring(0, 5)`?

**Answer:** no. Both `indexOf()` and `substring()` use UTF-16 offsets, so the value 5 is used directly.

**Question 5.** The UI requires limiting input to “no more than 20 visible characters”. Does `codePointCount()` guarantee correctness?

**Answer:** not yet. A visible character can consist of multiple code points. You need to choose an appropriate grapheme cluster segmenter and test composite emoji, combining marks, and target languages.

## References

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `length()`, `charAt()`, `substring()`, `codePointAt()`, `codePointCount()`, `offsetByCodePoints()`, `chars()`, and `codePoints()`.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): surrogate pairs, `charCount()`, code points, and UTF-16.
- [Java SE 17 — BreakIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html): finding character, word, and sentence boundaries based on locale.
- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://unicode.org/reports/tr29/): grapheme cluster, word, and sentence segmentation rules.
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://unicode.org/reports/tr15/): equivalent Unicode representations and normalization.
