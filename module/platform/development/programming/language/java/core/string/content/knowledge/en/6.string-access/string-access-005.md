# `String.offsetByCodePoints()` — Stepping by Unicode Code Points in Java

## 1. Goal: UTF-16 position differs from code point count

In Java, a `String` is a sequence of **UTF-16 code units** (`char`). The indices used by `String.charAt()`, `substring()`, `codePointAt()`, and `offsetByCodePoints()` are all **UTF-16 indices**. A Unicode code point in the Basic Multilingual Plane (BMP) normally occupies one `char`; a code point outside the BMP occupies **two `char`s** (a pair of *high surrogate* and *low surrogate*).

Therefore, advancing an index by `1` UTF-16 unit (`index++`) does not always mean advancing by one code point. `offsetByCodePoints` solves this exact problem: **it takes an initial UTF-16 position and the number of code points to step through, and returns a new UTF-16 position**.

Example with the string `"A🙂B"`:

```text
Visible content:          A       🙂        B
Unicode code point:      U+0041  U+1F642   U+0042
UTF-16 length:              1       2        1

UTF-16 index:             0   1   2   3   4
                          | A |  🙂   | B |
Valid positions between
code points:             ^   ^       ^   ^
                         0   1       3   4

index 2 lies BETWEEN the two chars forming the emoji.
```

`"A🙂B".length()` equals **4**, while `codePointCount(0, length())` equals **3**. To move two code points from the beginning of the string, you must reach UTF-16 index **3**, not **2**.

## 2. Signature and contract of `offsetByCodePoints`

API on `java.lang.String` (available since Java 5, used directly in Java 17+):

```java
public int offsetByCodePoints(int index, int codePointOffset)
```

| Parameter / result | Unit | Meaning |
| --- | --- | --- |
| `index` | UTF-16 index | Starting position to move from; valid in the range `0..length()`, **inclusive** of `length()` |
| `codePointOffset` | Number of code points | Number of code points to traverse: positive moves toward the end, negative moves toward the start, 0 stays put |
| Return value `int` | UTF-16 index | New position that can be passed to APIs expecting UTF-16 offsets, such as `substring` |
| Exception | — | `IndexOutOfBoundsException` if the initial position is invalid or the requested steps exceed the remaining text in the direction of movement |

Examples to build intuition (assuming `String text = "A🙂B";`):

```java
text.offsetByCodePoints(0, 0);  // 0: no movement
text.offsetByCodePoints(0, 1);  // 1: steps past 'A'
text.offsetByCodePoints(0, 2);  // 3: steps past 'A' and '🙂'
text.offsetByCodePoints(0, 3);  // 4: steps past all three code points
text.offsetByCodePoints(4, -1); // 3: steps back past 'B'
text.offsetByCodePoints(4, -2); // 1: steps back past 'B' and '🙂'
text.offsetByCodePoints(4, -3); // 0: back to the start of the string
```

The lines above are **expression snippets**, not a standalone program. Key point to remember: the second parameter is measured in **code points**, while **the result is still a UTF-16 index**.

`offsetByCodePoints` does not modify the `String`, does not return a code point, does not return a character count, and does not slice the string. It only computes a new offset from the current position.

## 3. Mechanism of stepping forward and backward across surrogate pairs

A code point outside the BMP is encoded in UTF-16 as two consecutive `char` units:
- *High surrogate*: a `char` value in the range `U+D800..U+DBFF`.
- *Low surrogate*: a `char` value in the range `U+DC00..U+DFFF`.

When starting at a **valid code point boundary**:
- Stepping **forward** past a normal BMP character increases the UTF-16 index by 1; stepping forward past a valid surrogate pair increases it by 2.
- Stepping **backward** past a normal BMP character decreases the index by 1; stepping backward past a valid surrogate pair decreases it by 2.
- If the UTF-16 sequence has an **unpaired lone surrogate**, Java counts each lone surrogate as one code point when stepping. The method does not automatically normalize or repair input data.

Therefore you cannot generally replace it with `index + codePointOffset`, even when the string “looks like” it only has a few characters. The Unicode content determines how many UTF-16 units must be traversed.

### Standalone Java 17+ example: stepping forward, backward, and slicing on boundaries

Save as `OffsetByCodePointsDemo.java`:

```java
public class OffsetByCodePointsDemo {
    public static void main(String[] args) {
        String text = "A🙂B";

        int p0 = 0;
        int p1 = text.offsetByCodePoints(p0, 1);
        int p2 = text.offsetByCodePoints(p1, 1);
        int p3 = text.offsetByCodePoints(p2, 1);

        System.out.println("UTF-16 length: " + text.length());
        System.out.println(
                "Code points: " + text.codePointCount(0, text.length()));
        System.out.println(
                "Boundaries: " + p0 + " -> " + p1 + " -> " + p2 + " -> " + p3);
        System.out.println("Forward 2: " + text.offsetByCodePoints(0, 2));
        System.out.println(
                "Back 2: " + text.offsetByCodePoints(text.length(), -2));
        System.out.println("Emoji: " + text.substring(p1, p2));
        System.out.println(
                "Code point: U+" +
                Integer.toHexString(text.codePointAt(p1)).toUpperCase());
    }
}
```

Compile and run with JDK 17+ (UTF-8 source encoding):

```bash
javac -encoding UTF-8 OffsetByCodePointsDemo.java
java OffsetByCodePointsDemo
```

```text
UTF-16 length: 4
Code points: 3
Boundaries: 0 -> 1 -> 3 -> 4
Forward 2: 3
Back 2: 1
Emoji: 🙂
Code point: U+1F642
```

Index `p1 = 1` is immediately before the emoji; because the emoji occupies two `char`s, `p2 = 3`. `substring(p1,p2)` extracts the exact two UTF-16 units representing **one** emoji code point. `codePointAt(p1)` reads the code point at UTF-16 index 1, returning `0x1F642`; `charAt(p1)` would only return the high surrogate.

## 4. Stepping one code point at a time in a loop

### Forward traversal

When writing an algorithm to iterate over each code point, use an `int index` variable representing the **UTF-16 position at the start of the next code point**. Start at 0 and continue until `index == text.length()`:

```java
for (int index = 0; index < text.length(); ) {
    int codePoint = text.codePointAt(index);
    // Process codePoint here.
    index = text.offsetByCodePoints(index, 1);
}
```

Do not put `index++` at the end of the loop: the number of `char`s of the code point just read can be 1 or 2. You can replace the step with `index += Character.charCount(codePoint)` when `codePoint` is read directly via `codePointAt(index)`, but `offsetByCodePoints` directly expresses the intent of stepping by code point and also supports negative directions.

### Backward traversal

To walk backward from the end of the string, set `index = text.length()` and step back one code point **before** calling `codePointAt`:

```java
for (int index = text.length(); index > 0; ) {
    index = text.offsetByCodePoints(index, -1);
    int codePoint = text.codePointAt(index);
    // Process codePoint here.
}
```

The position `length()` is valid for `offsetByCodePoints`; it is the boundary **after the last character**. However, `text.codePointAt(text.length())` is invalid, because `codePointAt` needs the position of an actual `char` element, from 0 to `length()-1`.

### Standalone bidirectional example

Save as `WalkCodePoints.java`:

```java
public class WalkCodePoints {
    public static void main(String[] args) {
        String value = "A🙂B";

        StringBuilder forward = new StringBuilder();
        for (int i = 0; i < value.length(); ) {
            int next = value.offsetByCodePoints(i, 1);
            forward.append('[').append(value, i, next).append(']');
            i = next;
        }

        StringBuilder backward = new StringBuilder();
        for (int i = value.length(); i > 0; ) {
            int previous = value.offsetByCodePoints(i, -1);
            backward.append(value, previous, i);
            i = previous;
        }

        System.out.println(forward);
        System.out.println(backward);
    }
}
```

```bash
javac -encoding UTF-8 WalkCodePoints.java
java WalkCodePoints
```

```text
[A][🙂][B]
B🙂A
```

The step `append(value, i, next)` takes a `CharSequence` slice by **UTF-16 indices [i, next)**, so the emoji is never cut between the two surrogates. The backward loop collects the code points in reverse order. However, reversing **code point** order is not always equivalent to reversing **visible characters** (for example characters with combining marks), because one grapheme cluster can contain multiple code points.

## 5. Using `offsetByCodePoints` with `substring`

`String.substring(beginIndex, endIndex)` takes **UTF-16 indices**. If a business requirement says “extract from the `a`-th code point up to before the `b`-th code point”, do not pass `a` and `b` directly into `substring`.

The right approach is:
1. Validate the code-point-based indices against the total number of code points.
2. Convert the start code point offset to a UTF-16 index via `offsetByCodePoints(0, beginCodePoint)`.
3. From the start boundary, advance `endCodePoint - beginCodePoint` code points to find the end boundary.
4. Call `substring(beginUtf16, endUtf16)`.

Complete example, save `SliceByCodePoints.java`:

```java
import java.util.Objects;

public class SliceByCodePoints {
    static String slice(String text, int beginCodePoint, int endCodePoint) {
        Objects.requireNonNull(text, "text");

        int total = text.codePointCount(0, text.length());
        if (beginCodePoint < 0
                || endCodePoint < beginCodePoint
                || endCodePoint > total) {
            throw new IndexOutOfBoundsException("Invalid code point range");
        }

        int beginUtf16 = text.offsetByCodePoints(0, beginCodePoint);
        int endUtf16 = text.offsetByCodePoints(
                beginUtf16, endCodePoint - beginCodePoint);
        return text.substring(beginUtf16, endUtf16);
    }

    public static void main(String[] args) {
        String text = "A🙂B🚀";

        System.out.println(slice(text, 1, 3));
        System.out.println(slice(text, 0, 2));
        System.out.println(slice(text, 3, 4));
        System.out.println(slice(text, 2, 2).isEmpty());
    }
}
```

```bash
javac -encoding UTF-8 SliceByCodePoints.java
java SliceByCodePoints
```

```text
🙂B
A🙂
🚀
true
```

This function treats `beginCodePoint` as the start position **counted in code points**, and `endCodePoint` as the **exclusive** end boundary. It converts both positions to UTF-16 offsets before slicing. Indices in `substring` are 0-based in `char` units; the start/end indices accepted by `slice` are 0-based by code point boundary. The two coordinate systems must not be mixed.

**When data contains lone surrogates:** Java's counting and stepping still follow consistent rules (each lone surrogate counts as one code point), but the function above is not a validator for well-formed Unicode strings. Applications requiring valid Unicode scalar values should validate the data separately.

## 6. Boundaries and exceptions

`offsetByCodePoints(index, codePointOffset)` throws `IndexOutOfBoundsException` if:
- `index < 0` or `index > text.length()`.
- `codePointOffset > 0` and there are not enough code points remaining after `index`.
- `codePointOffset < 0` and there are not enough code points preceding `index`.

Typical cases with `String text = "A🙂B";`:

| Call | Result | Why |
| --- | --- | --- |
| `text.offsetByCodePoints(0, 0)` | `0` | Keeps start position unchanged |
| `text.offsetByCodePoints(4, 0)` | `4` | Keeps end position unchanged |
| `text.offsetByCodePoints(0, 3)` | `4` | Traverses exactly 3 code points |
| `text.offsetByCodePoints(4, -3)` | `0` | Steps back exactly 3 code points |
| `text.offsetByCodePoints(4, 1)` | Exception | No code points remaining after |
| `text.offsetByCodePoints(0, -1)` | Exception | No code points preceding |
| `text.offsetByCodePoints(0, 4)` | Exception | String has only 3 code points |
| `text.offsetByCodePoints(5, 0)` | Exception | UTF-16 index out of range |

If you need to handle “not enough steps” as a normal business outcome, check the available code points beforehand using `codePointCount(index, length())` when moving forward, or `codePointCount(0, index)` when moving backward, **provided `index` is already on an appropriate code point boundary**. Do not swallow every `IndexOutOfBoundsException`: an exception can indicate that the program mixed up UTF-16 indices and code point indices.

### It does not automatically fix a position in the middle of a surrogate pair

This is a subtle case. From the API's perspective, `index` only needs to satisfy `0 <= index <= length()`; the method **does not require checking** that `index` starts on a code point boundary and **does not automatically shift** it to the start of the surrogate pair.

With `text = "A🙂B"`, `index = 2` lies on the **low surrogate** of the emoji:

```java
String text = "A🙂B";
System.out.println(Character.isLowSurrogate(text.charAt(2))); // true
System.out.println(text.offsetByCodePoints(2, 1));            // 3
System.out.println(text.offsetByCodePoints(2, -1));           // 1
```

This is a snippet placed inside `main`. When stepping forward from the middle of the pair, the low surrogate half ahead is counted as an unpaired unit within the traversed range; when stepping backward, the high surrogate half behind is also counted separately. The result **does not** mean position 2 is a sensible boundary for processing the whole emoji.

**Practical rule:** always initialize cursors from the start or end of the string and step with `offsetByCodePoints`; or convert a code point position to UTF-16 once before using it. Never take an arbitrary `charAt` index and assume it sits at the start of a code point.

## 7. Lone surrogates and what `offsetByCodePoints` does not do

A Java string can contain a high surrogate without an accompanying valid low surrogate, or an isolated low surrogate. Within the range examined by `offsetByCodePoints`, **a lone surrogate is counted as one code point** per Java's contract. This does not turn it into a valid Unicode scalar value and does not mean Java “repairs” text.

Standalone example, save `UnpairedSurrogateDemo.java`:

```java
public class UnpairedSurrogateDemo {
    public static void main(String[] args) {
        char[] chars = {'A', '\uD83D', 'B'};
        String text = new String(chars);

        System.out.println(text.length());
        System.out.println(text.codePointCount(0, text.length()));
        System.out.println(text.offsetByCodePoints(1, 1));
        System.out.println(
                Integer.toHexString(text.codePointAt(1)));
    }
}
```

```bash
javac -encoding UTF-8 UnpairedSurrogateDemo.java
java UnpairedSurrogateDemo
```

```text
3
3
2
d83d
```

The array has three UTF-16 units: `'A'`, a lone high surrogate `\uD83D`, then `'B'`. The method counts three code points per Java's rules and moves from offset 1 to 2 across the lone surrogate. This shows how the API handles unpaired data, not an example of a valid Unicode character with code U+D83D.

Another limitation: **a code point is not synonymous with a grapheme cluster**. For example, `"e\u0301"` is the letter `e` followed by a combining acute accent. It has **two code points** yet typically displays as a single letter “é”. Advancing by one code point stops between the base letter and the combining mark. ZWJ-joined emoji sequences or flag symbols can also consist of multiple code points for a single user-perceived character. If the requirement is to move by *grapheme cluster* for caret/text-selection handling, a Unicode-compliant character segmentation algorithm is needed; `offsetByCodePoints` only operates at the code point level.

## 8. Side by side with related methods

| API | What index unit is the input? | What is the output? | Purpose |
| --- | --- | --- | --- |
| `length()` | None | Number of UTF-16 **`char`s** | Logical storage length in UTF-16 |
| `charAt(i)` | UTF-16 | One `char` | Read exactly one UTF-16 unit |
| `codePointAt(i)` | UTF-16 | One code point `int` | Read the code point at the start position (pairs if high surrogate is followed by low) |
| `codePointBefore(i)` | UTF-16 boundary after element | One code point `int` | Read the code point immediately before that position |
| `codePointCount(begin,end)` | Two UTF-16 indices | **Count** of code points in the slice | Count, does not return an index |
| `offsetByCodePoints(index,n)` | UTF-16 + **count** of code points | UTF-16 index | Move the cursor |
| `substring(begin,end)` | Two UTF-16 indices | `String` | Extract slice over the provided boundaries |
| `codePoints()` | None | `IntStream` | Iterate over code point values |
| `chars()` | None | `IntStream` of `char` units | Iterate over individual UTF-16 units |

In particular, distinguish these two calls:

```java
int howMany = text.codePointCount(0, text.length()); // COUNT
int where = text.offsetByCodePoints(0, 2);           // UTF-16 POSITION
```

Do not pass `howMany` straight into `substring` as a UTF-16 index. `codePointCount` and `offsetByCodePoints` are two different operations: **counting** and **computing a new position after stepping**.

If you only want to iterate sequentially through the entire string by code point without needing positions, `text.codePoints()` can be simpler. If you need positions to interact with `substring`, `regionMatches`, or track a UTF-16 cursor, `offsetByCodePoints` is useful.

Java also provides `Character.offsetByCodePoints(CharSequence seq, int index, int codePointOffset)`; this version accepts a `CharSequence`, allowing algorithms to work with implementations beyond `String`. There is also an overload for a `char[]` subarray with `start`, `count`, and `index`; there, you must respect the boundaries **of the specified array region**, not assume the entire array. Regardless of which API is used, the returned index type is still an offset in UTF-16 units.

## 9. Designing safe navigation functions

An API that stores positions pointing into a `String` should define its coordinate system clearly. For example:
- Name `utf16Offset` for positions passed to `charAt`/`substring`/`offsetByCodePoints`.
- Name `codePointOffset` or `codePointIndex` for step counts or code point ordinals.
- When converting from the `k`-th code point to a UTF-16 index, use `text.offsetByCodePoints(0, k)` after verifying `0 <= k <= text.codePointCount(0,text.length())`.
- When converting from a UTF-16 position `p` to which code point ordinal from the start it corresponds to, use `text.codePointCount(0,p)` **if `p` is a proper boundary**; if `p` splits a surrogate pair, this is no longer an intact position conversion.
- If you must take many consecutive steps, keep and update the current position; avoid rescanning from 0 on every step.

Regarding performance, `offsetByCodePoints` must inspect the content in the traversed range to recognize surrogate pairs; do not assume accessing the `k`-th code point is constant time. Sequential traversal with an updated position is the clear choice; if you need random access to many code point positions on the same large text, consider caching precomputed boundary indices or using an appropriate data representation, and measure in practice before optimizing.

With a mutable `StringBuilder`, the data can change and old UTF-16 positions become inaccurate after insertions or deletions. Do not traverse using previously computed offsets while the content is changing without an appropriate position-updating rule.

## 10. Common mistakes

1. **Using `index++` to move to “the next Unicode character”.** When encountering emoji outside the BMP, the index moves into the middle of the surrogate pair. Use `offsetByCodePoints(index,1)` from a valid boundary.
2. **Confusing the return value with a code point count.** The result of `offsetByCodePoints` is a UTF-16 offset; the number of code points in a slice comes from `codePointCount`.
3. **Using code point indices directly with `substring`.** Convert both endpoints of the slice to UTF-16 positions first.
4. **Calling `codePointAt(length())`.** The end position is valid as a **starting point** for stepping backward, but invalid for reading a code point ahead.
5. **Forgetting negative steps.** Negative `codePointOffset` values are valid and necessary for backward traversal; they can throw an exception if stepping past the start.
6. **Assuming any UTF-16 index is at the start of a code point.** The method does not auto-correct when the starting point lies between a surrogate pair.
7. **Assuming the API always receives valid Unicode data.** Lone surrogates can exist in a `String` and are counted as one code point by Java's related APIs.
8. **Confusing code points with visible characters.** Combining marks, flags, and ZWJ emoji can contain multiple code points; use grapheme segmentation if the problem requires it.
9. **Assuming the cost is like array element indexing.** Stepping by code points requires scanning the content between boundaries; avoid recomputing from the start unnecessarily.

## 11. Self-check questions

With `String s = "X🙂Y";`, answer the following:

1. How do `s.length()` and `s.codePointCount(0,s.length())` differ?
2. What index does `s.offsetByCodePoints(0,2)` return? Why is it not `2`?
3. What index does `s.offsetByCodePoints(s.length(),-2)` return?
4. If you want to extract only the emoji using `substring`, which two UTF-16 indices must you pass?
5. Why is `s.offsetByCodePoints(2,1)` not the right way to step **from the start of the emoji** to the next code point?

Answers: (1) `4` and `3`; (2) `3`; (3) `1`; (4) `substring(1,3)`; (5) position `2` already lies between the two surrogates of the emoji, not on a code point boundary to start traversing from.

**Rule to remember:** `offsetByCodePoints` takes the **current UTF-16 offset** and a **number of code point steps**, then returns a **new UTF-16 offset**. Generate and maintain positions on code point boundaries when bridging between Unicode traversal and Java APIs that use `char` indices.

## Official API documentation (Java SE 17)

- [`String.offsetByCodePoints`, `codePointAt`, `codePointCount`, `substring` — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`Character.offsetByCodePoints`, `charCount`, surrogate helpers — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
- [`CharSequence` and `codePoints()` — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/CharSequence.html)
