# `String.getChars()`: Copying a Region of a String to `char[]`

## 1. Objectives

`String.getChars(int srcBegin, int srcEnd, char[] dst, int dstBegin)` copies **a contiguous region of a `String` into a caller-provided `char[]` character array**. This API is useful when you need to place a portion of text into an existing buffer, keep the rest of the buffer intact, or integrate with an API that accepts `char[]`.

Most important point: the `String` indices and the copy region length are measured in **UTF-16 code units** (`char`), not in Unicode code points or user-visible characters. You need to know this so you do not accidentally split a non-BMP character such as `🚀` in half.

After this lesson, you will know:
- The exact meaning of the four parameters and the **`[srcBegin, srcEnd)`** boundary.
- How to check the source range, destination position, and array capacity.
- Why `getChars` can copy *one half of a surrogate pair*.
- How to intentionally copy along code point boundaries.
- When to use `getChars` instead of `toCharArray()`, `substring()`, or `getBytes()`.

## 2. Syntax and mechanism

Method on a `String` object:

```java
public void getChars(int srcBegin, int srcEnd,
                     char[] dst, int dstBegin)
```

Short example:

```java
String source = "Java Core";
char[] buffer = {'_', '_', '_', '_', '_', '_', '_', '_'};

source.getChars(0, 4, buffer, 2);
System.out.println(new String(buffer)); // "__Java__"
```

Explanation:
1. From the source string `"Java Core"`, take the range **`[0, 4)`**, i.e., four code units `J`, `a`, `v`, `a`.
2. Write starting at element **`buffer[2]`**. Elements `buffer[2]` through `buffer[5]` are replaced with `J`, `a`, `v`, `a`.
3. Elements `buffer[0]`, `buffer[1]`, `buffer[6]`, `buffer[7]` keep their `_` characters.
4. The method returns **`void`**: it **mutates the destination array's contents**; it does not return a new array and does not modify the source `String`.

### Meaning of the four parameters

| Parameter | Meaning | Example |
| --- | --- | --- |
| `srcBegin` | First UTF-16 index in the source string, **inclusive**. | `0` starts from the beginning of the string. |
| `srcEnd` | UTF-16 index immediately after the last element to copy, **exclusive**. | `4` copies up to before position 4. |
| `dst` | Existing destination `char[]` array; elements are overwritten in the target range. | `buffer` |
| `dstBegin` | Index in the destination array where writing begins. | `2` writes starting at `buffer[2]`. |

The number of elements copied is:

\[
n = \text{srcEnd} - \text{srcBegin}
\]

With `i` running from `0` to `n - 1`, the effect on content is equivalent to:

```java
dst[dstBegin + i] = source.charAt(srcBegin + i);
```

This is an explanation of the operation, **not** a requirement to write a manual loop. Using `getChars` directly clearly expresses the intent to copy a region.

## 3. Start/end indices and destination position

Look at the example `"Java Core"` at each `char` position:

| UTF-16 index | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Character | J | a | v | a | space | C | o | r | e |

Calling `source.getChars(5, 9, buffer, 0)` extracts **`"Core"`** because `srcEnd = 9` is the boundary **after** the letter `e`. For a source of length `9`, `srcEnd == source.length()` is completely valid.

### Common boundary cases

- `source.getChars(0, source.length(), dst, 0)`: copies the entire string, provided `dst` has enough room.
- `source.getChars(2, 2, dst, 0)`: empty source region, **writes no characters**.
- `source.getChars(source.length(), source.length(), dst, dst.length)`: an empty region at the end of the string and end of the array is also valid.
- `source.getChars(2, 5, dst, 4)`: copies `3` `char`s into destination positions `4, 5, 6`; the destination array must have at least `7` elements.

Do not mistake `srcEnd` for the number of elements to copy. If you want to copy `count` elements starting from `start`, use `srcBegin = start` and `srcEnd = start + count`, after validating the range.

## 4. Validity conditions and exceptions

With `int n = srcEnd - srcBegin`, the index conditions are:

```text
0 <= srcBegin <= srcEnd <= source.length()
0 <= dstBegin <= dst.length
n <= dst.length - dstBegin
```

Here, `n` is measured in the number of **UTF-16 `char`s** to write. The final condition prevents writing past the destination array's size.

| Scenario | Example | Result |
| --- | --- | --- |
| Valid source region | `"abc".getChars(0, 2, new char[2], 0)` | Copies `a`, `b`. |
| Negative `srcBegin` | `"abc".getChars(-1, 2, new char[3], 0)` | `IndexOutOfBoundsException`. |
| `srcBegin > srcEnd` | `"abc".getChars(2, 1, new char[3], 0)` | `IndexOutOfBoundsException`. |
| `srcEnd` exceeds length | `"abc".getChars(0, 4, new char[4], 0)` | `IndexOutOfBoundsException`. |
| Negative `dstBegin` | `"abc".getChars(0, 1, new char[3], -1)` | `IndexOutOfBoundsException`. |
| Insufficient space in destination | `"abc".getChars(0, 3, new char[3], 1)` | `IndexOutOfBoundsException`. |
| `null` destination array | `"abc".getChars(0, 1, null, 0)` | `NullPointerException`. |
| Empty copy | `"abc".getChars(3, 3, new char[0], 0)` | Copies nothing; valid. |

When **multiple conditions are invalid at once**, do not rely on a specific exception message or internal check order. The API documentation states the contract; your program should validate both the source bounds and destination capacity.

Note: if computing `start + count` from very large integer data, `int` addition can overflow. You can check without overflow using `Objects.checkFromIndexSize(start, count, source.length())` (Java 9+) before computing boundaries, then validate the destination region similarly.

## 5. Standalone Java 17+ program

Save the following code to `GetCharsDemo.java`:

```java
import java.util.Arrays;

public class GetCharsDemo {
    public static void main(String[] args) {
        String text = "A🚀B";
        char[] target = {'_', '_', '_', '_', '_', '_'};

        // Copy the entire emoji, consisting of two UTF-16 code units.
        text.getChars(1, 3, target, 2);

        System.out.println("original = " + text);
        System.out.println("length = " + text.length());
        System.out.println("copied = [" + new String(target) + "]");
        System.out.println("target length = " + target.length);
        System.out.printf("dst[2] = U+%04X%n", (int) target[2]);
        System.out.printf("dst[3] = U+%04X%n", (int) target[3]);

        // An unsafe range: copies only the high surrogate.
        char[] partial = new char[1];
        text.getChars(1, 2, partial, 0);
        System.out.println("partial high surrogate = "
                + Character.isHighSurrogate(partial[0]));

        // An empty range does not modify the destination array.
        char[] unchanged = {'?', '?', '?'};
        text.getChars(2, 2, unchanged, 1);
        System.out.println("empty region = "
                + Arrays.toString(unchanged));
    }
}
```

Compile and run in a terminal that supports Unicode:

```bash
javac -encoding UTF-8 GetCharsDemo.java
java GetCharsDemo
```

Expected output:

```text
original = A🚀B
length = 4
copied = [__🚀__]
target length = 6
dst[2] = U+D83D
dst[3] = U+DE80
partial high surrogate = true
empty region = [?, ?, ?]
```

**Why does it produce this output?**
- The displayed string is `A🚀B`, yet `length() == 4` because the emoji `🚀` is code point `U+1F680`, which has two UTF-16 code units: **high surrogate `U+D83D`** at index `1` and **low surrogate `U+DE80`** at index `2`.
- `getChars(1, 3, target, 2)` takes the range `[1, 3)`, i.e., **two `char`s** of the emoji, and puts them into `target[2]` and `target[3]`. The first two underscores and last two underscores remain intact.
- `getChars(1, 2, partial, 0)` copies only the **high surrogate**. The method copies by code unit, so it does not automatically pair or supply the missing low surrogate.
- When `srcBegin == srcEnd`, the number of elements copied is `0`; `unchanged` still holds three question marks.

The program intentionally inspects code units using `%04X` instead of printing each surrogate half separately, because a lone surrogate may display as a replacement character or question mark depending on the environment.

## 6. `getChars` copies `char`s, not automatically by code point

To understand the indexing rule, examine the string `"A🚀B"`:

| UTF-16 index | `0` | `1` | `2` | `3` |
| --- | --- | --- | --- | --- |
| `charAt(index)` | `'A'` | `'\uD83D'` | `'\uDE80'` | `'B'` |

The complete code point boundaries are `0, 1, 3, 4`. Position `2` lies **between** the emoji's surrogate pair.

`String.getChars` **does not validate surrogate pair boundaries** and has no mode to automatically translate code point indices:

```java
String text = "A🚀B";

char[] correct = new char[2];
text.getChars(1, 3, correct, 0); // Both chars of 🚀.

char[] broken = new char[1];
text.getChars(1, 2, broken, 0); // High surrogate only.
```

Therefore:
- Use indices directly if your target truly is **UTF-16 code units**.
- If your target is **Unicode code points**, compute the proper UTF-16 boundaries first.
- If your target is a **visible character** (grapheme cluster) made of multiple code points, code-point-level operations can still split the cluster; use appropriate text segmentation rules.

### Converting a code point range to a UTF-16 range before calling `getChars`

The following is a **helper method** placed inside a Java class:

```java
static char[] copyCodePoints(String text, int from, int count) {
    java.util.Objects.requireNonNull(text, "text");

    int total = text.codePointCount(0, text.length());
    java.util.Objects.checkFromIndexSize(from, count, total);

    int startUtf16 = text.offsetByCodePoints(0, from);
    int endUtf16 = text.offsetByCodePoints(startUtf16, count);

    char[] result = new char[endUtf16 - startUtf16];
    text.getChars(startUtf16, endUtf16, result, 0);
    return result;
}
```

Example call from a `main`:

```java
String text = "A🚀B";
char[] rocket = copyCodePoints(text, 1, 1);
System.out.println(new String(rocket)); // 🚀
System.out.println(rocket.length);       // 2
```

Explanation: `from = 1` starts at the second code point (`🚀`). `offsetByCodePoints` converts code point positions to UTF-16 indices: start `1`, end `3`. The array needs `3 - 1 = 2` `char`s to hold the entire emoji.

**Limitation:** `codePointCount` and `offsetByCodePoints` treat a lone surrogate present in the string as one code point according to `String`'s handling. They do not automatically repair Unicode text that already contains unpaired surrogates, nor do they segment grapheme clusters.

## 7. Destination buffer: overwrite the exact region, keep the rest untouched

`getChars` is advantageous when you need to reuse an array or build a message from multiple parts. For example:

```java
String source = "học Java";
char[] destination = "........".toCharArray();

source.getChars(4, 8, destination, 2);
System.out.println(new String(destination)); // "..Java.."
```

The destination array initially contains eight dots. The four code units of `"Java"` are written into cells `2, 3, 4, 5`; the other cells are not overwritten.

To avoid bugs when reusing a buffer:
1. Compute `n = srcEnd - srcBegin` (after checking valid indices).
2. Ensure `dstBegin + n` does not exceed `dst.length` (you can check `n <= dst.length - dstBegin` to avoid integer overflow).
3. Track the **actual data length** currently inside the buffer separately. `new String(dst)` builds a string from the **entire** array, including unwritten `char`s (`'\u0000'` in an array freshly created with `new char[size]`).
4. If you only want to turn the newly written portion into a `String`, use `new String(dst, dstBegin, n)` or manage valid slices as needed.

Example:

```java
char[] buffer = new char[10];
String text = "Hello";
text.getChars(0, text.length(), buffer, 3);

String copiedOnly = new String(buffer, 3, text.length());
System.out.println(copiedOnly); // Hello
```

`new String(buffer, 3, 5)` takes the exact five code units written into the array. By contrast, `new String(buffer)` would also include the unwritten `'\u0000'` elements; they often do not show up clearly on the console.

A `char[]` array is **mutable**. If multiple threads write to the same array, the threads must synchronize or partition non-conflicting regions and coordinate publishing/combining data. The immutability of the source `String` does **not** make the destination buffer thread-safe.

## 8. Comparison with commonly used APIs

| API | Output or effect | When to use |
| --- | --- | --- |
| `text.getChars(begin, end, dst, dstBegin)` | Writes `end - begin` code units into an **existing** array; returns `void`. | Need to copy a region into a buffer at a specific position. |
| `text.toCharArray()` | Returns a **new** `char[]` containing all UTF-16 code units of the string. | Want an array copy of the entire string. |
| `text.substring(begin, end)` | Returns a `String` containing the specified range by UTF-16 indices. | Want to continue processing the result as a `String`. |
| `text.getBytes(StandardCharsets.UTF_8)` | Returns a `byte[]` with **UTF-8 encoded** data. | Writing files/sending byte data with a specified charset. |
| `text.codePoints().toArray()` | Returns an `int[]` by code point (combining valid surrogate pairs). | Need code point values instead of `char` units. |

Side-by-side example:

```java
String text = "A🚀B";

char[] chars = text.toCharArray(); // 4 UTF-16 chars.
int[] points = text.codePoints().toArray(); // 3 code points.

System.out.println(chars.length);  // 4
System.out.println(points.length); // 3
```

Do not use `getChars` to “decode UTF-8”: it does not accept `byte[]` and performs no charset conversion. For bytes, use appropriate encoding/decoding APIs.

Regarding performance, `getChars` avoids allocating a new `char[]` **if you already have a destination array**. It is not guaranteed to always be faster than other APIs; choose based on return-type requirements, memory allocation, maintainability, and measure performance in your actual context.

## 9. Common mistakes and how to fix them

**Mistake 1: Confusing `srcEnd` with count.**

```java
String text = "abcdef";
char[] dst = new char[3];
text.getChars(2, 5, dst, 0); // Correct: "cde", 3 chars.
```

`srcEnd = 5` is the **exclusive end index**; the count is `5 - 2 = 3`, not `5`.

**Mistake 2: Creating an array smaller than the slice to copy.**

```java
String text = "Hello";
char[] tooSmall = new char[3];
// text.getChars(0, 5, tooSmall, 0); // IndexOutOfBoundsException.
```

The array needs at least **5 free elements** from `dstBegin = 0` to hold all of `"Hello"`.

**Mistake 3: Using the code point count as the `char` count.**

```java
String text = "A🚀B";
int pointCount = text.codePointCount(0, text.length()); // 3
char[] tooShortForWholeString = new char[pointCount];  // 3
// text.getChars(0, text.length(), tooShortForWholeString, 0);
// Not enough: the source slice has 4 code units.
```

If copying the whole string, the array needs `text.length()` elements, **which does not necessarily equal** `codePointCount`.

**Mistake 4: Splitting a surrogate pair in half.**

```java
String text = "A🚀B";
char[] half = new char[1];
text.getChars(1, 2, half, 0); // High surrogate only.
```

If you want a complete code point outside the BMP, you must specify a UTF-16 range that includes both the high and low surrogates, such as `[1, 3)` in the example.

**Mistake 5: Printing the entire destination array and misunderstanding unwritten slots.**

`new char[10]` contains ten `'\u0000'` characters before values are assigned. If you only copy three code units, the remaining elements do not vanish on their own. Track the valid character count or construct the string from only the written slice using `new String(dst, offset, count)`.

**Mistake 6: Assuming the `String` content is modified.**

`getChars` writes into the **destination array**. Overwriting an element of `dst` afterward does not change the `String` used as the source or a new string created independently from the array.

## 10. Self-check exercises

### Exercise 1: Predict the destination region

```java
String text = "abcdef";
char[] out = {'-', '-', '-', '-', '-', '-'};
text.getChars(1, 4, out, 2);
System.out.println(new String(out));
```

**Answer:** `"--bcd-"`. Source `[1, 4)` takes `"bcd"` (3 `char`s), writing into elements `2..4`; the first two elements and the last element remain `'-'`.

### Exercise 2: Copying a string with emoji

```java
String text = "Hi😀!";
char[] out = new char[2];
text.getChars(2, 4, out, 0);
System.out.println(new String(out));
```

**Answer:** `"😀"`. The emoji `😀` occupies two UTF-16 `char`s at positions `2` and `3`, so the range `[2, 4)` captures it completely.

### Exercise 3: Enough capacity or not?

```java
String text = "Hello";
char[] out = new char[5];
text.getChars(1, 5, out, 2);
```

**Answer:** Not enough. Copying `4` code units starting from `dstBegin = 2` requires destination indices `2, 3, 4, 5`, whereas an array of length `5` only has indices `0..4`. The call throws `IndexOutOfBoundsException`.

### Exercise 4: Empty copy

```java
char[] out = {'x', 'y'};
"abc".getChars(3, 3, out, 2);
System.out.println(java.util.Arrays.toString(out));
```

**Answer:** `[x, y]`. Both source position `3` and destination position `2` are valid boundaries at the end; the number of elements to copy is `0`.

### Exercise 5: Copying by code point

Given `String text = "A🚀B";`. If you want to copy the **second code point** (1-based) into a `char[]` without hardcoding UTF-16 indices, what do you do?

**Answer:** Get `int from = text.offsetByCodePoints(0, 1);`, `int to = text.offsetByCodePoints(from, 1);`, allocate `char[] out = new char[to - from];`, and then call `text.getChars(from, to, out, 0);`. The result is an array of length `2` holding both units of `🚀`.

## 11. Remember

- `getChars(srcBegin, srcEnd, dst, dstBegin)` copies **`srcEnd - srcBegin` UTF-16 code units** into an existing array.
- The source slice is **`[srcBegin, srcEnd)`**: inclusive start, exclusive end.
- Writing begins at `dst[dstBegin]`; destination elements outside the written slice are not modified.
- The method returns `void`, mutates the destination `char[]`, and **does not modify the source `String`**.
- Check both **source bounds** and **destination capacity**; an empty range is valid if the indices are valid.
- For characters outside the BMP, one code point can occupy **two `char`s**. When working by code point, convert boundaries using `offsetByCodePoints` before copying.

## References

- [Java SE 17 — `String.getChars(int, int, char[], int)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#getChars(int,int,char%5B%5D,int))
- [Java SE 17 — `String`, `length` and `offsetByCodePoints` methods](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17 — `Character` and UTF-16 surrogates](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
