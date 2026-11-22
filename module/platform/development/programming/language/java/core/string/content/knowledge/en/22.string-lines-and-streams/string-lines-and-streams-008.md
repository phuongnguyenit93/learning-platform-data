# Rebuilding a String with a StringBuilder Using appendCodePoint in Java

## 1. Objective

When processing text from `String.codePoints()` or an `IntStream` of Unicode code points, we often need to construct a `String` again. The direct approach is to use **`StringBuilder` as a buffer**, append each Unicode code point in order with **`appendCodePoint(int)`**, and then call `toString()`.

Basic pattern:

~~~java
String source = "A\uD83D\uDE80B"; // "A🚀B"
StringBuilder builder = new StringBuilder(source.length());
source.codePoints().forEach(builder::appendCodePoint);
String rebuilt = builder.toString();
~~~

This is an **illustrative snippet placed inside a method**, not a standalone Java file. `rebuilt.equals(source)` is `true`.

This approach is especially useful when the processing pipeline needs to **filter, map, or transform individual Unicode code points** before assembling a new string. For copying a string verbatim with no processing, there is no need to allocate a buffer; you already have the original string.

## 2. Distinguishing `char`, Code Point, and Display Character

Java `String` stores text in **UTF-16**. The following three units of measurement are distinct:

| Concept | Example / Characteristics |
| --- | --- |
| **UTF-16 code unit** | A 16-bit `char` value. `String.length()` returns the number of code units, which does not always equal the number of characters the user sees. |
| **Unicode code point** | The numeric value of a Unicode code position. May require **one** or **two** UTF-16 code units to represent. `String.codePoints()` returns an `IntStream` of `int` values. |
| **Grapheme cluster** (display character) | A unit perceived by the user as one character; may consist of **multiple code points**, such as `e` combined with acute accent `\u0301` or emoji joined with ZWJ. |

Examples:

- `"A"`: one code point U+0041, one UTF-16 code unit.
- `"★"`: U+2605, one code point, one code unit.
- `"🚀"`: U+1F680, one code point yet **two** code units (a surrogate pair).
- `"e\u0301"`: usually displays as one accented letter, yet contains **two code points** (`e` and U+0301), which are also two code units.

Therefore:

~~~java
String text = "A\uD83D\uDE80B"; // A🚀B
System.out.println(text.length());                       // 4
System.out.println(text.codePointCount(0, text.length())); // 3
~~~

`String.chars()` returns an `IntStream`, but each element is only **one UTF-16 code unit widened to int**, so a surrogate pair produces **two elements**. In contrast, `String.codePoints()` merges a valid surrogate pair into **one int element**. Therefore, when operating by code point, choose `codePoints()`.

A single `char` cannot hold an entire emoji such as U+1F680. Casting a supplementary code point with `(char) cp` discards information beyond 16 bits.

## 3. What Does `StringBuilder.appendCodePoint(int)` Do?

`StringBuilder.appendCodePoint(int codePoint)` appends the UTF-16 representation of the code point to the end of the builder:

1. For values in the **Basic Multilingual Plane (BMP)** such as U+0041 or U+2605, the method appends **one** UTF-16 code unit.
2. For supplementary code points such as U+1F680, the method produces **one surrogate pair**, i.e., **two** code units.
3. For values outside the code point range (such as `-1` or `0x110000`), the method throws `IllegalArgumentException`.

The method returns the `StringBuilder` itself so calls can be chained:

~~~java
StringBuilder b = new StringBuilder();
b.appendCodePoint(0x41)
 .appendCodePoint(0x1F680)
 .appendCodePoint(0x42);
String result = b.toString(); // A🚀B
~~~

On `StringBuilder`, `length()` measures the **number of UTF-16 code units appended**. Appending the emoji U+1F680 increases the length by **2**, not 1.

**Subtle note:** `Character.isValidCodePoint` and `appendCodePoint` check the code point range from U+0000 to U+10FFFF, which includes the surrogate range U+D800–U+DFFF. Appending a value in this range individually creates an **unpaired surrogate** in the UTF-16 string, which is not a valid Unicode scalar value for interchange across all encodings. For external text data, validate or control unpaired surrogates according to your processing contract.

## 4. Complete Java 17+ Example and Tests

Save the following program to **`AppendCodePointDemo.java`**. The tests run without external libraries; any failing case throws `AssertionError`.

~~~java
public class AppendCodePointDemo {
    private static final int ROCKET = 0x1F680; // U+1F680 🚀

    static String rebuild(String input) {
        StringBuilder result = new StringBuilder(input.length());
        input.codePoints().forEach(result::appendCodePoint);
        return result.toString();
    }

    static String removeRocket(String input) {
        StringBuilder result = new StringBuilder(input.length());
        input.codePoints()
                .filter(cp -> cp != ROCKET)
                .forEach(result::appendCodePoint);
        return result.toString();
    }

    static String rocketToStar(String input) {
        StringBuilder result = new StringBuilder(input.length());
        input.codePoints()
                .map(cp -> cp == ROCKET ? 0x2605 : cp) // U+2605 ★
                .forEach(result::appendCodePoint);
        return result.toString();
    }

    static String rebuildByIndex(String input) {
        StringBuilder result = new StringBuilder(input.length());
        for (int i = 0; i < input.length();) {
            int cp = input.codePointAt(i);
            result.appendCodePoint(cp);
            i += Character.charCount(cp);
        }
        return result.toString();
    }

    private static void check(String name, boolean condition) {
        if (!condition) {
            throw new AssertionError("Failed: " + name);
        }
    }

    public static void main(String[] args) {
        String text = "A\uD83D\uDE80B"; // A🚀B: 4 UTF-16 units, 3 code points

        check("UTF-16 length", text.length() == 4);
        check("code point count",
                text.codePointCount(0, text.length()) == 3);
        check("round trip stream", text.equals(rebuild(text)));
        check("round trip indexes", text.equals(rebuildByIndex(text)));
        check("remove rocket", "AB".equals(removeRocket(text)));
        check("replace rocket", "A\u2605B".equals(rocketToStar(text)));
        check("empty input", "".equals(rebuild("")));
        check("combining mark", "e\u0301".equals(rebuild("e\u0301")));
        String isolatedHighSurrogate = String.valueOf((char) 0xD83D);
        check("isolated surrogate retained",
                isolatedHighSurrogate.equals(rebuild(isolatedHighSurrogate)));

        StringBuilder supplementary = new StringBuilder();
        supplementary.appendCodePoint(ROCKET);
        check("supplementary uses two UTF-16 units",
                supplementary.length() == 2);

        boolean invalidRejected = false;
        try {
            new StringBuilder().appendCodePoint(0x110000);
        } catch (IllegalArgumentException expected) {
            invalidRejected = true;
        }
        check("invalid code point rejected", invalidRejected);

        System.out.println("utf16Length=" + text.length());
        System.out.println("codePointCount="
                + text.codePointCount(0, text.length()));
        System.out.println("roundTrip=" + text.equals(rebuild(text)));
        System.out.println("removedRocket=" + removeRocket(text));
        System.out.println("replacedRocket=" + rocketToStar(text));
        System.out.println("emojiUtf16Length=" + supplementary.length());
        System.out.println("invalidRejected=" + invalidRejected);
        System.out.println("PASS: 11 checks");
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 AppendCodePointDemo.java
java AppendCodePointDemo
~~~

Expected output when all 11 checks pass:

~~~text
utf16Length=4
codePointCount=3
roundTrip=true
removedRocket=AB
replacedRocket=A★B
emojiUtf16Length=2
invalidRejected=true
PASS: 11 checks
~~~

In the example:

- `rebuild` iterates over `codePoints()` and appends each code point in order, restoring the exact original string.
- `removeRocket` removes U+1F680 with `filter`; both UTF-16 code units forming the emoji are removed **together**, rather than filtering half of a surrogate pair.
- `rocketToStar` uses `map` to change a supplementary code point into BMP code point U+2605, so the UTF-16 length of the result changes even though the code point count stays the same.
- `rebuildByIndex` shows the equivalent approach when you need to track the **position in the original string**: `codePointAt(i)` reads the code point, and `Character.charCount(cp)` advances by 1 or 2 code units accurately.
- The checks also cover empty strings, combining marks, isolated surrogates, and codes beyond U+10FFFF. Isolated surrogate values are returned by `codePoints()` as code unit values, and `appendCodePoint` can write them back, so copying does not silently alter the original string.

Using `equals` assertions to verify actual results helps catch differences not easily spotted by eye, especially when data contains emoji or combining marks. Do not rely solely on Java's `assert` statement, because `assert` may be disabled if the JVM is not launched with `-ea`.

## 5. How It Coordinates with `IntStream`

`String.codePoints()` provides a sequential `IntStream`. Each `int` value represents a code point (or an isolated surrogate). `forEach(result::appendCodePoint)` is a concise shorthand for:

~~~java
StringBuilder result = new StringBuilder();
text.codePoints().forEach(cp -> result.appendCodePoint(cp));
String output = result.toString();
~~~

If you need conditions or mappings, place them before appending:

~~~java
StringBuilder result = new StringBuilder();
text.codePoints()
    .filter(cp -> cp != 0x1F680)          // Skip 🚀
    .map(cp -> cp == 'a' ? 'A' : cp)        // Convert a to A
    .forEach(result::appendCodePoint);
String output = result.toString();
~~~

Both snippets are **illustrative code inside a method**, where `text` is an existing `String` variable. In `map`, each output must be a valid code point value for `appendCodePoint`. If one input must expand into **multiple code points**, use a loop/`forEach` with multiple `appendCodePoint` calls or an appropriate structure; ordinary `IntStream.map` is a **one-to-one** transformation.

Important ordering note: the `forEach` pattern with a single `StringBuilder` uses a **sequential stream**. If you call `parallel()` and write to the same builder inside `forEach`, operations can race, lose ordering, and corrupt results because `StringBuilder` is not thread-safe. When parallel processing is needed, design a thread-safe, order-preserving collection strategy; do not simply add `parallel()` to this pattern.

## 6. Complexity, Memory, and Choosing a Loop

For an input of `n` UTF-16 code units with linear per-code-point processing, iterating and appending takes **O(n)** overall time. `StringBuilder` avoids the allocation of intermediate strings caused by repeated `String` concatenation with `result += ...` inside a large loop.

`new StringBuilder(input.length())` allocates initial capacity based on the **number of UTF-16 code units**, not the number of code points. When simply copying or filtering out code points, that capacity is usually sufficient for the result. If a code point can be replaced by multiple characters or a longer string, the builder grows automatically, though extra allocations may occur.

`StringBuilder` is mutable and well suited for building a result **within a single processing thread**. After `toString()`, the result is an immutable `String` independent of any subsequent mutations to the builder.

When you need to know the UTF-16 index in the input while processing, the following loop can be more convenient than a stream:

~~~java
StringBuilder out = new StringBuilder(input.length());
for (int index = 0; index < input.length();) {
    int cp = input.codePointAt(index);
    out.appendCodePoint(cp);
    index += Character.charCount(cp);
}
String rebuilt = out.toString();
~~~

This is a code snippet inside a method with variable `input`. **Do not unconditionally increment `index++`** when processing by code point: for a supplementary code point, you must advance by **two code units**. `Character.charCount(cp)` returns 2 for supplementary code points and 1 for BMP characters or isolated surrogates.

## 7. Common Pitfalls in Practice

1. **Using `chars()` when you intend to process full code points:** `chars()` inspects individual code units, which can split surrogate pairs during filtering and mapping. Use `codePoints()` when operating at the code point level.
2. **Casting `(char) cp` and appending:** loses information for values above U+FFFF. Use `appendCodePoint(cp)`.
3. **Confusing a code point with “one user-visible character”:** ZWJ emoji sequences or characters with combining marks can contain multiple code points. `codePoints()` does not group grapheme clusters; when processing by character cluster, consider `BreakIterator` or a suitable Unicode segmentation library.
4. **Iterating in parallel and writing to a shared builder:** `StringBuilder` is not safe for concurrent writes from multiple threads. Use a sequential pipeline or an order-preserving collection architecture.
5. **Forgetting `toString()`:** the builder is a mutable buffer; APIs expecting a `String` need the final `builder.toString()` result.
6. **Assuming every code point adds only one `char`:** supplementary code points require surrogate pairs. Both builder length and `String` indices are measured in UTF-16.
7. **Failing to validate code points produced by transformations:** negative values or values exceeding `0x10FFFF` cause `appendCodePoint` to throw `IllegalArgumentException`. When producing standard Unicode text, also watch out for isolated surrogates in U+D800–U+DFFF.
8. **Using a builder to reconstruct the exact original string with no transformation:** unnecessary when the application already has the `String` and can return it directly. A builder is useful when you actually need to construct a modified result.

## 8. Self-Check Exercises

**Exercise 1.** For `"x🚀y"`, what are `length()` and `codePoints().count()`?

Answer: `length() == 4` because `x` and `y` take one code unit each and the rocket takes two code units; `codePoints().count() == 3` because there are three code points.

**Exercise 2.** Why does `input.codePoints().filter(cp -> cp != 0x1F680).forEach(builder::appendCodePoint)` remove the 🚀 emoji cleanly?

Answer: the stream contains **a single int element U+1F680** for the entire surrogate pair. `filter` excludes this exact element; neither surrogate half is appended.

**Exercise 3.** If you replace U+1F680 with U+2605 via `map`, does the code point count change? Can the UTF-16 code unit count change?

Answer: one code point is mapped to one code point so the code point count stays unchanged, but U+1F680 uses two code units while U+2605 uses one, so `String.length()` decreases by one.

**Exercise 4.** How do you preserve order and avoid bugs when building a string with a builder from a stream?

Answer: use `codePoints()` **sequentially** and append sequentially; do not write concurrently into the same `StringBuilder`.

## 9. When Should You Use This Pattern?

Use `codePoints() → filter/map → StringBuilder.appendCodePoint() → toString()` when you need to **actively rebuild a String by code point**, such as stripping specific emoji, normalizing certain characters, replacing Unicode symbols, or filtering out disallowed code points. If you need to process by UTF-16 code unit, grapheme cluster, or natural-language rules, choose the corresponding level of abstraction.

**Rule of thumb:** `String.length()` counts UTF-16 code units, `String.codePoints()` iterates over code points, and `StringBuilder.appendCodePoint()` converts each `int` back into its proper-width UTF-16 representation. Maintain ordering, validate input codes, and construct the result sequentially to rebuild `String` safely.
