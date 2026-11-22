# `Character.toChars`, `charCount`, and Working with Unicode Code Points in Java

## 1. What Will You Be Able to Do After This Lesson?

You will convert accurately between **Unicode code points** (`int`) and **UTF-16 code units** (`char`), use `Character.toChars`/`Character.charCount` to build and traverse strings, and choose the right `String`, `Character`, and `StringBuilder` APIs when processing text with characters outside the Basic Multilingual Plane (BMP). This lesson also explains common mistakes: using `charAt` as if it always returns a complete character, incrementing an index by 1 when stepping past an emoji, splitting surrogate pairs in half, and confusing code point count with user-perceived characters.

## 2. Background: Code Points Differ from `char`

Unicode assigns **code points** written as `U+XXXX` for values in the range `U+0000` to `U+10FFFF`. Java typically uses `int` to hold a code point value. Meanwhile, each `char` is a **16-bit UTF-16 code unit**, with values from `0x0000` to `0xFFFF`.

In UTF-16:

| Value range | `char`s needed to represent | Example |
| --- | ---: | --- |
| BMP: `U+0000` to `U+FFFF` (excluding standalone surrogate validity when used as an independent character) | 1 code unit | `U+0041` → `A`, `U+03A9` → `Ω` |
| Supplementary: `U+10000` to `U+10FFFF` | 2 code units forming a **surrogate pair** | `U+1F600` → 😀 |
| Values outside `0x0000..0x10FFFF` | Not a valid Unicode code point | `0x110000` |

The two code units of a surrogate pair have distinct roles:

- **High surrogate** lies in `U+D800..U+DBFF`.
- **Low surrogate** lies in `U+DC00..U+DFFF`.
- A high-then-low pair encodes **one** supplementary code point. For example, `U+1F600` → `U+D83D U+DE00`.
- Code points in `U+D800..U+DFFF` are **surrogate code points**: Java's `Character.isValidCodePoint` still considers those numeric values within the valid code point range, yet a standalone surrogate **is not a Unicode scalar value** and cannot represent a valid independent Unicode character in text interchange.

Distinguishing three ways to count:

| Question | Java API | For the string `"A😀B"` |
| --- | --- | ---: |
| How many UTF-16 code units? | `s.length()` | 4 |
| How many Unicode code points in the range? | `s.codePointCount(0, s.length())` | 3 |
| How many character clusters (grapheme clusters) does the user see? | Needs an appropriate clustering algorithm | 3 in this example |

For example, `"e\u0301"` has two code points (letter `e` and combining acute accent) even though it typically displays as **one character cluster**. Therefore, code points are not synonymous with grapheme clusters; and `String.length()` is even further from “length in user-perceived characters”.

## 3. `Character.toChars(int codePoint)`: From Code Point to UTF-16

Method:

~~~java
public static char[] Character.toChars(int codePoint)
~~~

Returns a `char[]` array representing the code point in UTF-16:

- If in the BMP, returns an array of length **1** with one code unit equal to the code point value.
- If in a supplementary plane, returns an array of length **2**, in the order **high surrogate then low surrogate**.
- If `codePoint` is outside `U+0000..U+10FFFF`, throws `IllegalArgumentException`.
- If the code point number is a BMP surrogate value, the method still returns a single surrogate `char`; it does not automatically enforce “Unicode scalar value” requirements for data interchange.

Short example:

~~~java
char[] a = Character.toChars(0x0041);   // {'A'}, length = 1
char[] omega = Character.toChars(0x03A9); // {'Ω'}, length = 1
char[] face = Character.toChars(0x1F600); // {0xD83D, 0xDE00}, length = 2

String emojiText = new String(face);    // one code point, two UTF-16 chars
String alsoEmoji = Character.toString(0x1F600); // available since Java 11
~~~

Do not cast `(char) 0x1F600` to “convert an emoji to `char`”: the cast truncates the upper bits and does not create a proper surrogate pair. If the target is a `String`, using `new String(Character.toChars(cp))` or `Character.toString(cp)` (Java 11+) is more convenient.

### Writing into an existing `char[]` array

Second overload:

~~~java
public static int Character.toChars(int codePoint, char[] dst, int dstIndex)
~~~

It writes **1 or 2** UTF-16 units starting at `dstIndex` and returns **the number of units actually written**, not the code point:

~~~java
char[] buffer = new char[4];
buffer[0] = '[';

int written = Character.toChars(0x1F600, buffer, 1); // written == 2
buffer[1 + written] = ']';

String wrapped = new String(buffer); // "[😀]"
~~~

You must ensure the destination array has enough space, especially for supplementary code points. This overload can throw `NullPointerException` if `dst` is null, `IndexOutOfBoundsException` if the index/capacity is invalid, and `IllegalArgumentException` if the code point is outside the valid range. This approach suits controlled UTF-16 buffer construction; for regular text, `StringBuilder.appendCodePoint` is usually simpler.

## 4. `Character.charCount(int codePoint)`: How Many `char`s Are Needed?

`Character.charCount(cp)` returns:

- `1` if `cp < 0x10000`.
- `2` if `cp >= 0x10000`.

It **does not validate** whether `cp` is in the Unicode code point range:

~~~java
Character.charCount(0x0041);   // 1
Character.charCount(0x1F600);  // 2
Character.charCount(0x110000); // 2: still returns 2 even though the value is invalid
Character.isValidCodePoint(0x110000); // false
~~~

Therefore, `charCount` determines **the expected UTF-16 width**, not validity. If `cp` comes from an external source, check `Character.isValidCodePoint(cp)` before calling `toChars` or `appendCodePoint`.

When `cp` is obtained via `s.codePointAt(offset)` at a valid code point boundary, you can use `offset += Character.charCount(cp)` to advance to the next code point.

## 5. Complete, Compilable, and Runnable Java 17+ Example

Create the file **`CodePointDemo.java`**:

~~~java
public class CodePointDemo {
    public static void main(String[] args) {
        int emoji = 0x1F600; // U+1F600, GRINNING FACE
        char[] pair = Character.toChars(emoji);
        String value = "A" + new String(pair) + "B";

        System.out.println("valid=" + Character.isValidCodePoint(emoji));
        System.out.println("supplementary=" + Character.isSupplementaryCodePoint(emoji));
        System.out.println("charCount=" + Character.charCount(emoji));
        System.out.printf("pair=U+%04X U+%04X%n", (int) pair[0], (int) pair[1]);
        System.out.println("pairValid=" + Character.isSurrogatePair(pair[0], pair[1]));
        System.out.printf("restored=U+%X%n", Character.toCodePoint(pair[0], pair[1]));

        System.out.println("length=" + value.length());
        System.out.println("codePointCount=" + value.codePointCount(0, value.length()));
        System.out.printf("at1=U+%X%n", value.codePointAt(1));
        System.out.printf("at2=U+%X%n", value.codePointAt(2));
        System.out.println("nextIndex=" + value.offsetByCodePoints(1, 1));

        for (int i = 0; i < value.length();) {
            int cp = value.codePointAt(i);
            System.out.printf("index=%d cp=U+%X%n", i, cp);
            i += Character.charCount(cp);
        }

        StringBuilder copy = new StringBuilder();
        value.codePoints().forEach(copy::appendCodePoint);
        System.out.println("roundTrip=" + value.contentEquals(copy));

        String decomposed = "e\u0301";
        System.out.println("combiningCodePoints="
                + decomposed.codePointCount(0, decomposed.length()));
    }
}
~~~

Run commands:

~~~bash
javac -encoding UTF-8 CodePointDemo.java
java CodePointDemo
~~~

Verified `stdout` when compiling/running:

~~~text
valid=true
supplementary=true
charCount=2
pair=U+D83D U+DE00
pairValid=true
restored=U+1F600
length=4
codePointCount=3
at1=U+1F600
at2=U+DE00
nextIndex=3
index=0 cp=U+41
index=1 cp=U+1F600
index=3 cp=U+42
roundTrip=true
combiningCodePoints=2
~~~

Explanation:

1. `0x1F600` is a valid supplementary code point. `toChars` produces two code units: high `D83D` and low `DE00`. `isSurrogatePair` confirms the right order; `toCodePoint` combines the pair into `1F600`.
2. For `"A😀B"`, the **UTF-16 indices** are `0: A`, `1: high surrogate`, `2: low surrogate`, `3: B`. Thus `length() == 4`, yet `codePointCount(...) == 3`.
3. `codePointAt(1)` sits at the **high surrogate**, so it combines with the following low surrogate and returns `U+1F600`. `codePointAt(2)` sits at the **low surrogate**, so it returns only `U+DE00`; the API does not look backward to pair.
4. `offsetByCodePoints(1, 1)` moves **one code point** from UTF-16 index `1` and returns UTF-16 index `3`; hence the loop visits indices `0`, `1`, `3`.
5. `String.codePoints()` provides an `IntStream` by code points; `StringBuilder.appendCodePoint` encodes each `int` back into UTF-16. `roundTrip=true` shows the original string is reconstructed.
6. `e` plus a combining acute accent forms two code points even though the human eye usually sees one character cluster.

## 6. Code-Point-Related APIs and How to Choose

| API | Input/index | Meaning |
| --- | --- | --- |
| `Character.isValidCodePoint(cp)` | `int` | `true` when `0 <= cp <= 0x10FFFF`; **does not exclude surrogate code points** |
| `Character.isBmpCodePoint(cp)` | `int` | Within `U+0000..U+FFFF`, including the surrogate range |
| `Character.isSupplementaryCodePoint(cp)` | `int` | Within `U+10000..U+10FFFF` |
| `Character.toChars(cp)` | `int` | Code point → array of 1 or 2 UTF-16 `char`s |
| `Character.charCount(cp)` | `int` | Returns 1/2 based on threshold `0x10000`; does not validate |
| `Character.isHighSurrogate(ch)` / `isLowSurrogate(ch)` | `char` | Checks each half of a surrogate pair |
| `Character.isSurrogatePair(hi, lo)` | two `char`s | Validates a high-low pair |
| `Character.toCodePoint(hi, lo)` | two `char`s | Combines into `int`; **does not validate the pair** |
| `Character.highSurrogate(cp)` / `lowSurrogate(cp)` | supplementary `int` | Gets the two UTF-16 halves; for non-supplementary `cp`, the result is not specified for use |
| `s.charAt(i)` | UTF-16 index | Returns **one code unit**, which may be only half of a surrogate |
| `s.codePointAt(i)` | UTF-16 index | Reads the code point starting at `i`; pairs if `i` is a high surrogate immediately followed by a low surrogate |
| `s.codePointBefore(i)` | UTF-16 index **right after** the character to read | Reads the code point immediately before `i`; pairs if immediately before is a low surrogate preceded by a high surrogate |
| `s.codePointCount(begin, end)` | Two UTF-16 offsets, `end` exclusive | Counts code points in the range; an unpaired surrogate counts as one |
| `s.offsetByCodePoints(i, delta)` | UTF-16 index + number of code points to shift | Returns the **new UTF-16 index**, `delta` may be negative |
| `s.chars()` / `s.codePoints()` | Takes no index | `IntStream` by **code units** / **code points** respectively |
| `sb.appendCodePoint(cp)` | `int` | Appends a code point to `StringBuilder` as 1 or 2 code units |

### Converting from a surrogate pair back to a code point

When you already have two `char`s:

~~~java
char high = '\uD83D';
char low = '\uDE00';

if (Character.isSurrogatePair(high, low)) {
    int cp = Character.toCodePoint(high, low); // 0x1F600
}
~~~

`Character.toCodePoint` **does not check** the input pair. If you are not sure the two `char`s are in high-low order, call `isSurrogatePair` first to avoid producing an incorrect number.

The mathematical formula behind combining a valid pair:

~~~text
codePoint = 0x10000
          + (high - 0xD800) * 0x400
          + (low  - 0xDC00)
~~~

Normally, prefer using standard APIs rather than writing the formula and handling edge cases yourself.

### Iterating in reverse

If you need to traverse from the end of a string to the beginning by code points, `codePointBefore` and `charCount` give a symmetric pattern:

~~~java
String s = "A" + Character.toString(0x1F600) + "B";

for (int end = s.length(); end > 0;) {
    int cp = s.codePointBefore(end);
    System.out.printf("U+%X%n", cp);
    end -= Character.charCount(cp);
}
~~~

This snippet prints `U+42`, `U+1F600`, `U+41` in order. Note that the `end` parameter of `codePointBefore` sits **after** the unit to read, whereas `codePointAt` takes the starting position.

## 7. Slicing Strings and Handling Indices Properly

Every `String` index in standard APIs such as `charAt`, `substring`, and `length` remains a **UTF-16 position**. “Take the first two code points” does not mean `substring(0, 2)` if the prefix contains a supplementary character.

Example:

~~~java
String s = "A" + Character.toString(0x1F600) + "B";

// First two code points: 'A' and U+1F600.
int end = s.offsetByCodePoints(0, 2);
String firstTwoCodePoints = s.substring(0, end); // "A😀", end == 3
~~~

General pattern when code point indices are non-negative and within string bounds:

~~~java
static String sliceByCodePoints(String s, int from, int count) {
    int start = s.offsetByCodePoints(0, from);
    int end = s.offsetByCodePoints(start, count);
    return s.substring(start, end);
}
~~~

This function relies directly on the API contract: if `from` or `count` causes out-of-bounds access, `offsetByCodePoints` throws `IndexOutOfBoundsException`. For defensive input validation, additionally verify `from >= 0` and `count >= 0` per business rules. Slice endpoints are computed from code point boundaries, avoiding cutting across a valid surrogate pair. This is still **not** a grapheme-cluster slicing algorithm.

**Range boundary warning:** `codePointCount(begin, end)` operates on the given UTF-16 slice. If `begin` or `end` cuts right between a high and low surrogate, the API only sees the portion inside the slice and may count an unpaired surrogate as a code point. When working with code-point-based interfaces, convert and maintain valid boundaries first.

## 8. Malformed Data: Validation and Unpaired Surrogates

The methods in `Character` do not share the same error policy.

~~~java
System.out.println(Character.isValidCodePoint(0x110000)); // false
System.out.println(Character.charCount(0x110000));        // 2, does not validate
// Character.toChars(0x110000); // throws IllegalArgumentException

System.out.println(Character.isValidCodePoint(0xD800));   // true
System.out.println(Character.isSurrogate((char) 0xD800));  // true
~~~

The surrogate range `0xD800..0xDFFF` lies within the code point numbers accepted by `Character.isValidCodePoint`, yet each standalone value **is not a Unicode scalar value**. To reject both out-of-range numbers and surrogate code points when a system requires a scalar value:

~~~java
static boolean isUnicodeScalarValue(int cp) {
    return Character.isValidCodePoint(cp)
            && (cp < 0xD800 || cp > 0xDFFF);
}
~~~

A Java string can contain **unpaired** surrogate `char`s (for instance, from truncated data or direct construction). `codePointAt`, `codePointBefore`, `codePoints()`, and `codePointCount` have rules for handling them: unpaired surrogates are read or counted as individual `char` values, **without automatically repairing the string into valid UTF-16**. If an application must output strict Unicode data, it needs rules to validate or replace malformed data according to the target protocol.

Additionally, `Character.highSurrogate(cp)` and `lowSurrogate(cp)` should only be used when `Character.isSupplementaryCodePoint(cp)` is true; for non-supplementary inputs, the API does not guarantee a meaningful surrogate half. Similarly, before `toCodePoint(high, low)`, validate with `isSurrogatePair`.

## 9. Common Mistakes and How to Fix Them

**Mistake 1 — iterating over a `String` with `charAt(i)` and treating each `char` as a Unicode character.**

Wrong when emojis or supplementary-plane letters are present, because `charAt` returns only one code unit. If the goal is to iterate over code points:

~~~java
for (int i = 0; i < s.length();) {
    int cp = s.codePointAt(i);
    // Process cp as a Unicode code point
    i += Character.charCount(cp);
}
~~~

Or use `s.codePoints().forEach(cp -> ...)` if you do not need UTF-16 indices.

**Mistake 2 — using `new String(new char[] {(char) cp})` for any `cp`.** Casting down to `char` keeps only 16 bits; use `new String(Character.toChars(cp))` to support supplementary code points.

**Mistake 3 — using `charCount(cp)` to validate input.** This function does not check validity; apply `isValidCodePoint` and, if needed, exclude surrogate code points separately.

**Mistake 4 — checking character categories using `char` overloads.** For example, `Character.isLetter(char)` cannot inspect a full supplementary code point. For text with non-BMP Unicode, prefer the `Character.isLetter(int cp)` overload after reading with `codePointAt` or `codePoints()`.

**Mistake 5 — counting code points to infer “displayed character count” or limit username length.** Letter+mark combinations, variation-selector emojis, ZWJ sequences, and flags can consist of multiple code points while displaying as one grapheme cluster. If the requirement is to slice or count by user-perceived character clusters, use an appropriate Unicode grapheme segmentation algorithm; `codePointCount` solves a different problem.

**Mistake 6 — combining a surrogate pair without checking order.** `Character.toCodePoint` does not verify the pair; call `Character.isSurrogatePair` first or read code points directly through `String`.

## 10. Self-Check Questions

1. **What do `Character.toChars(0x1F600).length` and `Character.charCount(0x1F600)` return?**  
   Both are `2`; a supplementary code point needs two UTF-16 code units.
2. **Why is `"A😀B".length()` equal to 4 while `codePointCount(0, length)` is 3?**  
   The two BMP letters occupy 1 `char` each, while the emoji occupies 2 `char`s yet only one code point.
3. **What does `Character.charCount(0x110000)` return, and does it guarantee a valid number?**  
   Returns `2`; **no**. `Character.isValidCodePoint(0x110000)` is `false`, and `toChars` throws an exception.
4. **Does `String.codePointAt(i)` take a code point index or a `char` index?**  
   It takes a **UTF-16 index**. At a high surrogate, it can pair with the following low surrogate; starting at a low surrogate does not pair backward.
5. **When you need to extract the first 5 code points of a `String`, what should you use?**  
   `int end = s.offsetByCodePoints(0, 5);` then `s.substring(0, end)`, provided the string has at least 5 code points.
6. **Is `Character.isValidCodePoint(0xD800)` enough to treat the character as a Unicode scalar?**  
   No. The value lies in the surrogate range and must be excluded separately if a scalar value is required.

## 11. Official References

- [Java SE 17 — `Character` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): `toChars`, `charCount`, `isValidCodePoint`, `isSurrogatePair`, `toCodePoint`, and `int`-accepting overloads.
- [Java SE 17 — `String` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `codePointAt`, `codePointBefore`, `codePointCount`, `offsetByCodePoints`, `chars`, and `codePoints`.
- [Java SE 17 — `StringBuilder` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): `appendCodePoint`.
- [Unicode Standard — Encoding Forms](https://www.unicode.org/versions/latest/core-spec/chapter-3/): UTF-16, surrogate pairs, code points, scalar values.

**Key takeaway:** A `char` is **one UTF-16 code unit**, whereas a code point is represented by `int` and may require **one or two** `char`s. Use `toChars` to encode, `charCount` to advance by the right number of code units, `String.codePointAt`/`codePoints` to read, and `offsetByCodePoints` to convert indices before slicing strings.