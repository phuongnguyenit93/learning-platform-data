# `String.codePoints()` Combines Surrogate Pairs into Code Points in Java

## 1. The Problem: One Unicode Character Can Occupy Two `char`s

In Java, the primitive type `char` is **16 bits**, and a `String` is stored as **UTF-16 code units**. For characters in the Basic Multilingual Plane (BMP), such as `A` (U+0041), one UTF-16 code unit is usually enough to represent the character. However, code points outside the BMP, like the emoji `😃` (U+1F603), require **two consecutive UTF-16 code units**, called a **surrogate pair**.

Example:

~~~java
String text = "A😃B";
System.out.println(text.length());             // 4 UTF-16 code units
System.out.println(text.codePoints().count()); // 3 code points
~~~

We **see three symbols** `A`, `😃`, `B`, yet `length()` returns `4` because `😃` occupies **two `char`s**. This is why you cannot assume `charAt(i)` returns a complete Unicode code point.

**Main takeaway:** `String.codePoints()` creates an `IntStream` of Unicode code points read from the string. Whenever it encounters a **high surrogate** immediately followed by a **low surrogate**, it combines those two code units into **one `int` value** in the stream. Code units that do not form a valid pair are emitted individually.

## 2. Three Easily Confused Concepts

| Concept | In Java | Example with `A😃B` |
| --- | --- | --- |
| UTF-16 **code unit** | 16-bit `char`, observed by `length()`, `charAt()`, `chars()` | 4 units: U+0041, U+D83D, U+DE03, U+0042 |
| Unicode **code point** | Integer representing a Unicode code value, usually handled as `int` | 3 codes: U+0041, U+1F603, U+0042 |
| **Grapheme cluster** (user-perceived character unit) | Unicode text segmentation concept, not equivalent to `char` or code point | Can contain multiple code points while displaying as a single character |

Not every code point is a standalone visible character. For example, `e` + combining acute accent `\u0301` is **two code points** that can combine to render a single `é` on screen. Emoji with skin-tone modifiers, variation selectors, or Zero Width Joiner (ZWJ) sequences can also consist of multiple code points while displaying as one symbol.

`codePoints()` helps read **code points**; it does **not** group code points into grapheme clusters and does not normalize Unicode automatically.

## 3. What Is a Surrogate Pair?

In UTF-16, code points from U+10000 to U+10FFFF are encoded using **two `char`s**:

- **High surrogate**: value in the range U+D800–U+DBFF.
- **Low surrogate**: value in the range U+DC00–U+DFFF.

The two values must appear **in high-then-low order and adjacent to each other** to form a valid surrogate pair. Combination formula:

~~~text
codePoint = 0x10000
          + ((high - 0xD800) << 10)
          +  (low  - 0xDC00)
~~~

For `😃` (U+1F603), UTF-16 contains:

~~~text
High surrogate: U+D83D
Low surrogate : U+DE03
Combined      : U+1F603
~~~

Java already provides `Character.isHighSurrogate(char)`, `Character.isLowSurrogate(char)`, `Character.isSurrogatePair(char, char)`, `Character.toCodePoint(high, low)`, and `Character.toChars(int)`. Prefer standard APIs rather than writing the combining formula manually in application code.

Standalone illustrative snippet (statements placed inside a `main` method):

~~~java
String emoji = "😃";
char high = emoji.charAt(0);
char low = emoji.charAt(1);

System.out.println(Character.isHighSurrogate(high));   // true
System.out.println(Character.isLowSurrogate(low));     // true
System.out.println(Character.isSurrogatePair(high, low)); // true
System.out.println(Character.toCodePoint(high, low) == 0x1F603); // true
~~~

**Note:** a code point in the BMP (such as the letter `A`) is represented by one code unit; the range U+D800–U+DFFF is reserved for surrogates and therefore does not represent valid Unicode scalar values on its own.

## 4. Comparing `chars()` and `codePoints()`

Both return `IntStream`, but the **meaning of each `int`** differs.

### `String.chars()`

`chars()` emits each UTF-16 code unit as an `int` by widening the `char` value to an unsigned integer. It **does not combine** surrogate pairs.

~~~java
"A😃B".chars()
       .mapToObj(cp -> String.format("U+%04X", cp))
       .forEach(System.out::println);
~~~

Output:

~~~text
U+0041
U+D83D
U+DE03
U+0042
~~~

### `String.codePoints()`

`codePoints()` examines consecutive `char` elements. If it encounters an adjacent high surrogate and low surrogate, it emits **one supplementary code point `int`**; otherwise it emits the individual code unit value.

~~~java
"A😃B".codePoints()
       .mapToObj(cp -> String.format("U+%04X", cp))
       .forEach(System.out::println);
~~~

Output:

~~~text
U+0041
U+1F603
U+0042
~~~

| Method | Element count for `A😃B` | Unit Iterated |
| --- | ---: | --- |
| `text.length()` | 4 | Length in UTF-16 code units |
| `text.chars().count()` | 4 | Each `int` is one code unit |
| `text.codePoints().count()` | 3 | Each `int` is one decoded code point |
| `text.codePointCount(0, text.length())` | 3 | Counts code points within a UTF-16 index range |

`String.codePoints()` was added in Java 9, while the material here uses Java 17+ for consistent examples. `IntStream` processes code points in string order during sequential traversal.

## 5. Complete Runnable Java 17+ Example

Save the file as `CodePointsDemo.java` (UTF-8 source encoding):

~~~java
import java.util.stream.Collectors;

public class CodePointsDemo {
    private static String hex(int value) {
        return String.format("U+%04X", value);
    }

    public static void main(String[] args) {
        String text = "A😃B";

        System.out.println("length=" + text.length());
        System.out.println("chars=" + text.chars().count());
        System.out.println("codePoints=" + text.codePoints().count());

        System.out.println("units=" +
                text.chars()
                    .mapToObj(CodePointsDemo::hex)
                    .collect(Collectors.joining(", ")));

        System.out.println("points=" +
                text.codePoints()
                    .mapToObj(CodePointsDemo::hex)
                    .collect(Collectors.joining(", ")));

        System.out.println("charAt1=" + hex(text.charAt(1)));
        System.out.println("pointAt1=" + hex(text.codePointAt(1)));
        System.out.println("before3=" + hex(text.codePointBefore(3)));
        System.out.println("offsetAfter2=" +
                text.offsetByCodePoints(0, 2));

        System.out.println("supplementary=" +
                text.codePoints()
                    .filter(Character::isSupplementaryCodePoint)
                    .count());

        String unpaired = new String(new char[] {
                '\uD83D', 'X', '\uDE03'
        });
        System.out.println("unpaired=" +
                unpaired.codePoints()
                        .mapToObj(CodePointsDemo::hex)
                        .collect(Collectors.joining(", ")));
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 CodePointsDemo.java
java CodePointsDemo
~~~

Expected output:

~~~text
length=4
chars=4
codePoints=3
units=U+0041, U+D83D, U+DE03, U+0042
points=U+0041, U+1F603, U+0042
charAt1=U+D83D
pointAt1=U+1F603
before3=U+1F603
offsetAfter2=3
supplementary=1
unpaired=U+D83D, U+0058, U+DE03
~~~

Explanation:

1. `charAt(1)` returns the **high surrogate** U+D83D, which is only **half** of the emoji.
2. `codePointAt(1)` looks ahead at the low surrogate at position 2 and returns the code point U+1F603.
3. `codePointBefore(3)` reads backward from index 3, combining the two code units at positions 1 and 2 into U+1F603.
4. `offsetByCodePoints(0, 2)` advances by **two code points** starting from UTF-16 index 0 and therefore returns UTF-16 index `3`, the position of the letter `B`.
5. `filter(Character::isSupplementaryCodePoint)` counts one code point outside the BMP.
6. The `unpaired` example intentionally places a high surrogate, the letter `X`, and a low surrogate **non-adjacently**. `codePoints()` does not merge them into one code point; it emits U+D83D, U+0058, U+DE03 in sequence.

These lines display code points in hexadecimal to clearly distinguish Unicode values from characters rendered by the terminal.

## 6. How to Traverse and Process Code Points Properly

### 6.1. Traversing with a Stream

If you only care about the actual code points, use `codePoints()`:

~~~java
String s = "A😃B";
s.codePoints().forEachOrdered(cp -> {
    System.out.println(String.format("U+%04X", cp));
});
~~~

Output:

~~~text
U+0041
U+1F603
U+0042
~~~

The `codePoints()` method is a **data source** for an `IntStream` pipeline. You can use `filter`, `map`, `distinct`, `count`, or `toArray` just as with other primitive streams. The stream does not automatically turn into a list of single-character `String`s.

Example filtering code points outside the BMP:

~~~java
long count = "A😃B".codePoints()
        .filter(Character::isSupplementaryCodePoint)
        .count();
System.out.println(count); // 1
~~~

Note that `Character.isLetter(int)`, `Character.isDigit(int)`, and `Character.getType(int)` accept `int codePoint`, making them suitable for checking Unicode properties of each code point.

### 6.2. Reconstructing a `String` from Code Points

Do not convert a supplementary code point into a single `char` by casting, because that loses information:

~~~java
int smile = 0x1F603;
// char broken = (char) smile; // Casting loses the upper bits: not 😃.
String restored = new String(Character.toChars(smile));
System.out.println(restored.codePointAt(0) == smile); // true
~~~

`Character.toChars(int)` converts a non-BMP code point into a surrogate pair. When appending multiple code points to a string, use `StringBuilder.appendCodePoint(int)`:

~~~java
int[] points = "A😃B".codePoints().toArray();
StringBuilder builder = new StringBuilder();

for (int point : points) {
    builder.appendCodePoint(point);
}

System.out.println(builder.toString().equals("A😃B")); // true
~~~

Distinguish `append((char) point)` from `appendCodePoint(point)`: the first adds only **one code unit**, whereas the second adds one or two UTF-16 code units as needed for the code point.

### 6.3. UTF-16 Indices and Code Point Indices Are Not the Same

APIs such as `charAt`, `substring`, `indexOf`, and `codePointAt` accept/report **UTF-16 indices** of `String`, not the code point's ordinal position.

~~~java
String s = "A😃B";

// Starting at UTF-16 index 1, skip exactly one code point (the emoji).
int afterEmoji = s.offsetByCodePoints(1, 1);
System.out.println(afterEmoji);        // 3
System.out.println(s.charAt(afterEmoji)); // B
~~~

If you need the `k`-th Unicode element (0-based), use `offsetByCodePoints(0, k)` to find its UTF-16 position, then `codePointAt(index)` to read the code point. Ensure `k` is in bounds before accessing; these methods throw `IndexOutOfBoundsException` when indices are invalid.

Example extracting **exactly one code point** as a `String`:

~~~java
String text = "A😃B";
int start = text.offsetByCodePoints(0, 1);
int end = text.offsetByCodePoints(start, 1);
String emoji = text.substring(start, end);

System.out.println(emoji.codePoints().count()); // 1
~~~

`substring(1, 2)` would capture only the high surrogate, whereas `substring(1, 3)` captures both code units for the emoji in this example.

## 7. Unpaired Surrogates: An Important Limitation of `codePoints()`

A Java `String` can contain **invalidly paired** UTF-16 data, such as a high surrogate not immediately followed by a low surrogate, or an isolated low surrogate.

~~~java
String invalid = new String(new char[]{'\uD83D', 'X'});
System.out.println(invalid.length());            // 2
System.out.println(invalid.codePoints().count()); // 2
~~~

Java **does not silently drop**, pair across non-adjacent positions, or repair isolated surrogates when running `codePoints()`. By the contract of `String.codePoints()`, an **unpaired** surrogate is emitted as an `int` value by widening its own code unit (e.g., U+D83D).

Things to distinguish:

- An isolated surrogate can become an element in the `IntStream` returned by `codePoints()`.
- Values from U+D800 to U+DFFF are **not valid Unicode scalar values** when standing alone, even though Java allows `String` to hold them.
- Therefore, do not treat calling `codePoints()` as a **UTF-16 validation step** or a fix for malformed Unicode data.
- If inputs might be malformed, decide your policy explicitly: detect/reject, replace with the replacement character U+FFFD, or apply a library's decoding policy. Encoding to UTF-8 bytes can also apply its own invalid-character replacement policy.

You can check for unpaired surrogates while traversing `codePoints()`:

~~~java
String invalid = new String(new char[]{'\uD83D'});
boolean hasUnpairedSurrogate = invalid.codePoints()
        .anyMatch(cp -> cp >= 0xD800 && cp <= 0xDFFF);
System.out.println(hasUnpairedSurrogate); // true
~~~

When encountering only valid high–low pairs, `codePoints()` returns their non-BMP code points and does not emit the two surrogate values separately.

## 8. A Code Point Differs from a User-Visible Character

`codePoints()` solves the **UTF-16 surrogate pair** problem, but it does not solve every problem related to counting “characters”.

Example:

~~~java
String composed = "é";       // U+00E9
String decomposed = "e\u0301"; // U+0065 then U+0301

System.out.println(composed.codePoints().count());   // 1
System.out.println(decomposed.codePoints().count()); // 2
~~~

Two strings can look identical yet have different Unicode representations. If an application needs canonical equivalence, consider `java.text.Normalizer` (e.g., NFC) before comparing per business rules; `codePoints()` **does not normalize automatically**.

A multi-component emoji or a flag formed by regional indicators can also have **multiple code points** while displaying as one symbol. For cursor movement, deleting a user-visible character, or enforcing length limits by **grapheme cluster**, you need an appropriate Unicode segmentation tool, such as a library supporting Unicode grapheme boundaries. Do not use `codePoints().count()` as the grapheme cluster count.

## 9. Common Mistakes and How to Avoid Them

| Mistake | Why It Is Wrong | Correct Approach |
| --- | --- | --- |
| `length()` is the code point count | `length()` counts UTF-16 code units | `codePointCount(0, length())` or `codePoints().count()` |
| `charAt(i)` always returns a full Unicode character | May return half of a surrogate pair | `codePointAt(i)` when `i` is a valid UTF-16 index |
| `chars()` and `codePoints()` are identical | `chars()` splits every code unit | `codePoints()` combines valid surrogate pairs |
| Casting `(char) cp` to rebuild an emoji | `char` is too small for non-BMP code points | `Character.toChars(cp)` or `appendCodePoint(cp)` |
| Passing a code point index to `substring` | `substring` expects UTF-16 indices | Convert via `offsetByCodePoints` |
| `codePoints()` fixes all broken surrogates | It still emits isolated surrogates | Validate or handle errors separately |
| Every code point is one grapheme | Combining characters and complex emoji have multiple code points | Segment graphemes according to requirements |

### Self-Check Checklist

- For `A😃B`: `length() == 4` and `codePoints().count() == 3`.
- `chars()` emits U+D83D and U+DE03 separately; `codePoints()` emits U+1F603.
- `codePointAt(1)` returns U+1F603; `charAt(1)` returns only U+D83D.
- `offsetByCodePoints(0, 2)` returns UTF-16 index `3`.
- A high and low surrogate separated by another character **do not combine**; the stream still carries the isolated surrogates.
- `codePoints()` counts code points and **does not count grapheme clusters** or normalize Unicode.

**Conclusion:** `String.codePoints()` lets you process Java strings by Unicode code point instead of by UTF-16 `char`. It merges **adjacent high surrogate + low surrogate** into one `int`, making iteration over emoji and non-BMP characters accurate. However, `String` indices remain UTF-16 based, malformed surrogates still require separate handling, and recognizing “one visible character” requires grapheme cluster analysis.
