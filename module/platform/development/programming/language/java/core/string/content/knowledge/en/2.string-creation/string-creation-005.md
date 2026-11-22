# Creating a `String` from a Code Point Array in Java

## 1. Objectives

When text data is represented as Unicode code point values (`int[]`), Java lets you create a `String` directly using the constructor `String(int[] codePoints, int offset, int count)`. This is especially useful when working with characters outside the Basic Multilingual Plane (BMP), such as many emojis, without manually assembling UTF-16 `char` pairs.

After this lesson, you will be able to:
- Distinguish **Unicode code points**, **UTF-16 code units (`char`)**, and `String` length.
- Create a string from all or a slice of an `int[]`.
- Understand the meaning and bounds of `offset` / `count`, possible exceptions, and how to validate inputs.
- Convert back and forth between `String` and a code point array when needed.

## 2. How Is a Code Point Different from a `char`?

A **Unicode code point** is an integer value identifying a Unicode code position, usually written as `U+XXXX` or `U+XXXXX`, for example:

| Character | Code point | `int` value in Java | Number of UTF-16 `char`s |
| --- | --- | --- | --- |
| `A` | `U+0041` | `0x0041` | 1 |
| `ế` (precomposed form) | `U+1EBF` | `0x1EBF` | 1 |
| `🚀` | `U+1F680` | `0x1F680` | 2 |
| `😀` | `U+1F600` | `0x1F600` | 2 |

Java uses **UTF-16** for `String`'s `char`-indexed operations. One `char` is a 16-bit *code unit*:
- Code points in the BMP (from `U+0000` to `U+FFFF`) usually occupy one code unit. Note that the surrogate range `U+D800..U+DFFF` does not represent standalone Unicode characters.
- Supplementary code points (from `U+10000` to `U+10FFFF`) require **two** code units, called a *surrogate pair*.
- Therefore, `String.length()` counts UTF-16 `char`s, **not** code points and **not** user-perceived characters. A letter with combining marks or a composite emoji can consist of multiple code points.

For example, the array `{0x0041, 0x1F680, 0x0042}` contains **3 code points** forming `A🚀B`, yet `"A🚀B".length()` is **4**.

## 3. Constructor `String(int[] codePoints, int offset, int count)`

Syntax:

```java
String text = new String(codePoints, offset, count);
```

| Parameter | Meaning |
| --- | --- |
| `codePoints` | An `int[]` array storing Unicode code point values in the desired order. |
| `offset` | Index of the **first element** to take from `codePoints` (zero-based). |
| `count` | **Number of `int` elements** to take, not the ending index and not the number of UTF-16 `char`s. |

The constructor converts each element in the slice `codePoints[offset .. offset + count)` into a string representation. For supplementary code points like `0x1F680`, Java automatically generates the corresponding surrogate pair.

To use the entire array:

```java
int[] points = {0x0048, 0x0069, 0x0021};
String greeting = new String(points, 0, points.length); // "Hi!"
```

There is no `new String(int[])` constructor; all three arguments must be passed. The index constraints are `offset >= 0`, `count >= 0`, and `offset + count <= codePoints.length`. When `count == 0` and the position is valid, the result is an empty string. The source array is converted into string content at creation time; modifying `int[]` afterward does not change the `String`.

## 4. Standalone Runnable Java 17+ Example

Save the following to `CodePointStringDemo.java`:

```java
public class CodePointStringDemo {
    public static void main(String[] args) {
        // H, i, space, rocket, exclamation mark.
        int[] points = {0x0048, 0x0069, 0x0020, 0x1F680, 0x0021};
        String text = new String(points, 0, points.length);

        System.out.println(text);
        System.out.println("length() = " + text.length());
        System.out.println("codePointCount() = "
                + text.codePointCount(0, text.length()));
        System.out.printf("codePointAt(3) = U+%X%n", text.codePointAt(3));

        // Omit leading/trailing stars; select 5 code points starting at index 1.
        int[] padded = {0x2605, 0x004A, 0x0061, 0x0076, 0x0061, 0x1F680, 0x2605};
        String selected = new String(padded, 1, 5);
        System.out.println("selected = " + selected);

        padded[1] = 0x0058; // Change 'J' in the array to 'X'.
        System.out.println("after array change = " + selected);

        System.out.println("empty = [" + new String(points, 0, 0) + "]");
    }
}
```

Compile and run (in a Unicode-capable terminal):

```bash
javac -encoding UTF-8 CodePointStringDemo.java
java CodePointStringDemo
```

Expected output:

```text
Hi 🚀!
length() = 6
codePointCount() = 5
codePointAt(3) = U+1F680
selected = Java🚀
after array change = Java🚀
empty = []
```

**Explanation:**
1. `points` has 5 elements, but `🚀` takes 2 UTF-16 code units: `text.length() == 6` while `text.codePointCount(0, text.length()) == 5`.
2. `codePointAt(3)` takes a **`char` index**, and index 3 is where the surrogate pair for `🚀` begins, so it returns `0x1F680`. Do not confuse `String` indices with indices in `int[]`.
3. `new String(padded, 1, 5)` takes 5 code points at indices 1, 2, 3, 4, 5, producing `Java🚀`; the leading/trailing `★` characters are excluded.
4. The result does not change after modifying the array because `String` is immutable and the constructor does not retain the `int[]` as live backing data.

## 5. Handling Code Points and Indices Properly

Several related APIs:

| API | Purpose |
| --- | --- |
| `text.length()` | Number of UTF-16 code units. |
| `text.codePointCount(0, text.length())` | Number of code points in the string (unpaired surrogates are also counted individually). |
| `text.codePointAt(charIndex)` | Gets the code point starting at a UTF-16 index. |
| `text.offsetByCodePoints(charIndex, delta)` | Moves by a number of code points and returns the new UTF-16 index. |
| `text.codePoints().toArray()` | Extracts an `int[]` of code points from a `String`. |
| `Character.toChars(codePoint)` | Converts one code point into one or two `char`s. |
| `StringBuilder.appendCodePoint(codePoint)` | Appends code points one by one when building a string incrementally. |

Round-trip conversion example:

```java
String original = "A🚀B";
int[] cps = original.codePoints().toArray();
String copy = new String(cps, 0, cps.length);

System.out.println(java.util.Arrays.toString(cps));
System.out.println(copy.equals(original));
System.out.println(copy.length() + " / " + cps.length);
```

Output of the illustration snippet when run inside a method (such as `main`):

```text
[65, 128640, 66]
true
4 / 3
```

`String.codePoints()` provides an `IntStream`. Do not use a `for (char c : text.toCharArray())` loop if you need to process each code point: that loop can split a supplementary character into two surrogate code units.

If you need to slice an existing string by **code point count**, convert the start/end positions with `offsetByCodePoints` and then call `substring`; `substring`'s arguments are still UTF-16 indices. By contrast, `offset` and `count` in the `int[]` constructor directly count array elements.

## 6. Data Validation and Common Exceptions

Constructor scenarios:

| Input | Behavior |
| --- | --- |
| `new String(new int[]{0x41}, 0, 1)` | `"A"`. |
| `new String(new int[]{0x41}, 1, 0)` | Empty string; `offset == length` is allowed when `count == 0`. |
| `new String(new int[]{0x41}, 0, 2)` | `IndexOutOfBoundsException`: exceeds array bounds. |
| `new String(new int[]{0x41}, -1, 1)` | `IndexOutOfBoundsException`: negative `offset`. |
| `new String(new int[]{0x110000}, 0, 1)` | `IllegalArgumentException`: exceeds maximum code point `U+10FFFF`. |
| `new String((int[]) null, 0, 0)` | `NullPointerException` when the code point array is `null`. |

Calling `new String(null, 0, 0)` **does not compile** because it is ambiguous among the `int[]`, `char[]`, and `byte[]` overloads; casting `(int[]) null` selects the constructor under discussion.

**Distinguishing Java-valid code points from Unicode scalar values:** `Character.isValidCodePoint(cp)` checks `0 <= cp <= 0x10FFFF`, so **surrogate values** `0xD800..0xDFFF` also pass this range check. A Java `String` can hold an unpaired surrogate, but that is not well-formed Unicode text. If input must represent standard text for interchange or external output, reject isolated surrogate code points.

The following utility method can be used when `int[]` data comes from an untrusted source and you only want to accept Unicode scalar values. This is a helper method to place inside a Java class:

```java
static String fromUnicodeScalars(int[] points, int offset, int count) {
    java.util.Objects.requireNonNull(points, "points");
    java.util.Objects.checkFromIndexSize(offset, count, points.length);

    for (int i = offset; i < offset + count; i++) {
        int cp = points[i];
        boolean surrogate = cp >= 0xD800 && cp <= 0xDFFF;
        if (!Character.isValidCodePoint(cp) || surrogate) {
            throw new IllegalArgumentException(
                    String.format("Invalid Unicode scalar: U+%X", cp));
        }
    }
    return new String(points, offset, count);
}
```

`Objects.checkFromIndexSize` validates the selected slice (Java 9+). The basic constructor already checks out-of-range code points; the additional check here is for requirements that **disallow unpaired surrogates**.

Do not confuse an `int[]` of code points with a UTF-8 `byte[]`: if the data is encoded bytes, decode it using an explicit charset such as `new String(bytes, java.nio.charset.StandardCharsets.UTF_8)`. Also do not cast every code point to `(char)`: casting truncates the upper bits of values greater than `0xFFFF`.

## 7. Choosing the Right Solution by Scenario

- **Already have an `int[]` of code points:** use `new String(points, offset, count)` directly; no need to build surrogate pairs manually.
- **Generating code points sequentially:** use `StringBuilder.appendCodePoint(cp)`, then `toString()`, which avoids repeated `String` concatenation in a loop.
- **Already have a `String` and want to operate per code point:** use `codePoints()`, `codePointAt`, `codePointCount`, and `offsetByCodePoints` as appropriate.
- **Have a `char[]`:** `new String(chars)` takes UTF-16 code units, which differs semantically from an `int[]` of code points.
- **Data is UTF-8/UTF-16 bytes:** decode using a charset API, rather than treating each byte as a code point.

Common misconceptions include thinking `count` is the ending index, assuming one code point always occupies one `char`, using `length()` to count code points, or assuming one code point always corresponds to one *visible character* (grapheme cluster). For instance, the letter `e` followed by a combining acute accent may be two code points while looking like one character; composite emojis can also contain multiple code points.

## 8. Knowledge Self-Check

Given the array:

```java
int[] cps = {0x0058, 0x0041, 0x1F600, 0x0042, 0x0059};
String s = new String(cps, 1, 3);
```

1. What is `s`? **`A😀B`**, because it takes the elements at indices 1, 2, and 3.
2. What is `s.length()`? **4** UTF-16 code units, because `😀` occupies two `char`s.
3. What is `s.codePointCount(0, s.length())`? **3** code points.
4. If `cps[1] = 0x005A` is modified afterward, does `s` change? **No**, because the `String` was created independently of the source array.
5. Is `new String(cps, 3, 3)` valid? **No**, because it requests three elements starting at index 3 in an array of length 5.

## References

- [Java SE 17 — `String(int[] codePoints, int offset, int count)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#%3Cinit%3E(int%5B%5D,int,int))
- [Java SE 17 — `Character`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
