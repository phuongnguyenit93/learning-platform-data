# `String.splitWithDelimiters()` — splitting strings while keeping delimiters (Java 21)

When you need to divide a string into parts, `String.split(regex)` is often enough. However, if you want to **preserve the characters or substrings used as separators** (commas, colons, whitespace, multi-character delimiters, etc.), Java 21 provides `String.splitWithDelimiters(regex, limit)`. This method returns both the content segments and the regex matches in exact order of appearance.

## 1. API and meaning

```java
public String[] splitWithDelimiters(String regex, int limit)
```

- `regex`: a **regular expression** describing the delimiter to find; it is not treated as an ordinary literal string by default.
- `limit`: controls the number of splits and whether trailing empty strings are kept or discarded.
- Return value: a `String[]` alternating between **content segment, regex-matched delimiter, content segment, delimiter, ...**; each delimiter keeps the exact characters that actually matched.
- Available since **Java 21**. There is no single-argument `splitWithDelimiters(regex)` overload like `split(regex)`; you must pass `limit`.

For example, with `"red:::green::blue"` and regex `":+"`, the result is `["red", ":::", "green", "::", "blue"]`. The two delimiters `":::"` and `"::"` are kept as separate elements because `:+` matches **one or more** consecutive colons.

`String.splitWithDelimiters(regex, limit)` has the same semantics as `Pattern.compile(regex).splitWithDelimiters(input, limit)`. The `Pattern` version is useful when reusing a regex many times.

## 2. How does it differ from `split()`?

| Call with `s = "a::b:c"` | Result |
| --- | --- |
| `s.split(":+", -1)` | `["a", "b", "c"]` |
| `s.splitWithDelimiters(":+", -1)` | `["a", "::", "b", ":", "c"]` |

`split()` discards the regex-matched segments; `splitWithDelimiters()` stores them in the array. Thus the new method is suited for reconstructing the exact original string, parsing logs, preserving punctuation, or identifying each delimiter variant.

Visualizing the processing flow:

```text
String:    red ::: green :: blue
Returned:  [red][:::][green][::][blue]
Type:      [CONTENT][DELIMITER][CONTENT][DELIMITER][CONTENT]
```

Each time a delimiter is found, the result appends the **preceding** content segment followed by the matched delimiter itself. If no delimiter matches, the array has only one element containing the entire input string.

## 3. Standalone Java 21 example

Create the file `SplitWithDelimitersDemo.java`:

```java
import java.util.Arrays;
import java.util.regex.Pattern;

public class SplitWithDelimitersDemo {
    public static void main(String[] args) {
        String input = "red:::green::blue";

        System.out.println("split       = "
                + Arrays.toString(input.split(":+", -1)));
        System.out.println("with        = "
                + Arrays.toString(input.splitWithDelimiters(":+", -1)));
        System.out.println("limit 2     = "
                + Arrays.toString(input.splitWithDelimiters(":+", 2)));

        String[] parts = input.splitWithDelimiters(":+", -1);
        System.out.println("round-trip  = "
                + input.equals(String.join("", parts)));

        // Literal dot character, not regex wildcard.
        System.out.println("literal dot = "
                + Arrays.toString(
                        "a.b.c".splitWithDelimiters(Pattern.quote("."), -1)));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 SplitWithDelimitersDemo.java
java SplitWithDelimitersDemo
```

Expected output:

```text
split       = [red, green, blue]
with        = [red, :::, green, ::, blue]
limit 2     = [red, :::, green::blue]
round-trip  = true
literal dot = [a, ., b, ., c]
```

`String.join("", parts)` concatenates all content segments and delimiters in sequence without inserting anything. For normal splitting regexes, this verifies that the exact original input was preserved. The `limit 2` result shows that only the first `:::` was split out; the remaining `green::blue` stays intact.

## 4. Understanding the `limit` parameter accurately

`limit` is **not the maximum number of elements** in the array, nor is it the maximum length of each element.

| `limit` | Behavior | Consequence |
| --- | --- | --- |
| `> 0` | Applies the regex at most `limit - 1` times | Array length is at most `2 * limit - 1` elements; last element holds the entire remainder |
| `= 0` | Splits as many times as possible | Discards **trailing empty strings** from the array, whether empty content or empty delimiter |
| `< 0` | Splits as many times as possible | Keeps trailing empty strings as well |

With the string `"a,b,"` and regex `","`:

| Call | Returned array (using double quotes so empty strings are visible) |
| --- | --- |
| `splitWithDelimiters(",", 1)` | `["a,b,"]` |
| `splitWithDelimiters(",", 2)` | `["a", ",", "b,"]` |
| `splitWithDelimiters(",", 0)` | `["a", ",", "b", ","]` |
| `splitWithDelimiters(",", -1)` | `["a", ",", "b", ",", ""]` |

Note that at `limit = 0`, **the trailing comma remains** because it is the string `","`, which is non-empty; only the empty content `""` after the comma is removed. `limit = -1` keeps the `""` element to distinguish ending immediately after a delimiter.

With `limit = 1`, no splits occur, so the result is a one-element array containing the whole string. With `limit > 1`, the maximum number of splits is `limit - 1`, and each split can add **two elements** (content and delimiter); hence the length cap is `2 * limit - 1`, unlike `String.split(regex, limit)`.

## 5. How the regex determines which delimiters are kept

- Regex `","` matches only a single comma. With `"a,,b"` and `limit = -1`, you get `["a", ",", "", ",", "b"]`. The empty content in the middle carries information: two consecutive commas.
- Regex `",+"` matches a run of consecutive commas. The same string `"a,,b"` becomes `["a", ",,", "b"]`. Choose `","` or `",+"` depending on whether you want to distinguish individual delimiters or collapse runs.
- Regex `"[,;]\\s*"` matches a comma **or** semicolon followed by any adjacent whitespace. `"milk, bread; eggs".splitWithDelimiters("[,;]\\s*", -1)` returns `["milk", ", ", "bread", "; ", "eggs"]`. Whitespace is included in the delimiter so it is not lost.
- Characters `.`, `|`, `*`, `+`, `?`, `(`, `)`, `[`, `]`... have special meaning in regex. To split on a **literal period character**, use `"\\."` in Java source or `Pattern.quote(".")`; passing `"."` matches almost every single character.

If the regex can match the **empty string** (zero-width match), the result has boundary rules to watch out for. Specifically, a **non-empty** match right at the start of the string produces a leading empty content element; a **zero-width** match right at the start of the string does **not** produce a leading empty content or empty delimiter element. Do not assume every regex produces the same array shape as examples using real character delimiters.

## 6. Important edge cases

| Input | Regex | `limit` | Result |
| --- | --- | --- | --- |
| `",A"` | `","` | `-1` | `["", ",", "A"]` |
| `"A,"` | `","` | `-1` | `["A", ",", ""]` |
| `"A,"` | `","` | `0` | `["A", ","]` |
| `"A,,B"` | `","` | `-1` | `["A", ",", "", ",", "B"]` |
| `"ABC"` | `","` | `-1` | `["ABC"]` |

These results illustrate the difference between **empty content segments** and **delimiters**. With `limit = 0`, only empty elements **at the very end** are removed; empty content between two delimiters is still kept.

## 7. Practical use case: processing tokens while preserving separators

Suppose you want to style each part of a string while keeping commas, semicolons, and trailing spaces intact:

```java
String input = "milk, bread; eggs";
String[] tokens = input.splitWithDelimiters("[,;]\\s*", -1);

for (int i = 0; i < tokens.length; i++) {
    boolean isDelimiter = (i % 2 == 1);
    System.out.printf("%s: <%s>%n",
            isDelimiter ? "DELIMITER" : "TEXT",
            tokens[i]);
}
```

This is a **code snippet for use inside a method or JShell**, not a standalone Java file. Output:

```text
TEXT: <milk>
DELIMITER: <, >
TEXT: <bread>
DELIMITER: <; >
TEXT: <eggs>
```

With delimiter-preserving splitting, elements at even indices (`0, 2, 4...`) are content segments, and odd indices (`1, 3, 5...`) are delimiters. When a regex can match empty strings, zero-width rules must also be considered; when `limit = 0` strips trailing empty content, the array may end right after a delimiter.

These elements can be used for syntax highlighting UIs, normalizing certain log formats, or counting and identifying individual delimiters. If you want to keep the original data intact for further processing, `limit = -1` is typically chosen.

## 8. Common mistakes and choosing the right API

1. **Confusing regex with literal strings:** `"."` is a wildcard in regex; use `Pattern.quote(".")` or `"\\."` when looking for a real dot.
2. **Assuming `limit = 2` means two elements:** the method can return three elements `[before, delimiter, remainder]`.
3. **Thinking `limit = 0` removes a trailing delimiter:** it only removes trailing **empty strings**, not real delimiter characters.
4. **Overlooking empty content between two delimiters:** `"a,,b"` differs from `"a,b"` if data rules treat empty fields as significant.
5. **Using complex regexes for structured data:** this method **does not replace a proper CSV parser** (especially with quoted strings or escaped delimiters) or a parser for nested syntax.
6. **Repeating the same regex on large datasets:** precompile a `Pattern` and call `pattern.splitWithDelimiters(input, limit)` to reuse it; avoid regexes with expensive backtracking.

**Choose `split()`** when you only need the values after removing delimiters. **Choose `splitWithDelimiters()`** when the positions and exact text of delimiters are also information you need to keep.

## 9. Self-check

- What does `"x|y".splitWithDelimiters("\\|", -1)` return? → `["x", "|", "y"]`.
- Why does `"x,,y".splitWithDelimiters(",", -1)` have an `""` element? → Two consecutive comma matches with no content between them.
- When you want to keep trailing empty fields as well, which `limit` should you choose? → A negative value, typically `-1`.
- With `limit = 3`, what is the maximum array length? → `2 * 3 - 1 = 5`.
- When no delimiter matches, what is the result? → A single-element array containing the original string.

**Official API reference:** [`String.splitWithDelimiters` in Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#splitWithDelimiters(java.lang.String,int)) and [`Pattern.splitWithDelimiters` in Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html#splitWithDelimiters(java.lang.CharSequence,int)).