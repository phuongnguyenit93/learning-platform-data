# `String.length()` and `String.isEmpty()` in Java

A text-processing program often has to answer two questions: **how long is the string?** and **is the string empty?** Java provides two methods directly on the `java.lang.String` class:

- `int length()`: returns the **number of UTF-16 code units** in the string.
- `boolean isEmpty()`: returns `true` if and only if `length() == 0`.

Both methods do not modify the `String` content, take no parameters, and are well suited for common conditional checks. The most important thing is to understand the exact meaning of **“length”** and **“empty”** here, especially when the string contains spaces, emoji, or data that might be `null`.

## 1. What does `length()` return?

Syntax:

```java
int count = text.length();
```

`length()` returns a non-negative integer. For simple ASCII strings, the result usually matches the number of characters the reader sees:

```java
"".length()       // 0
"A".length()      // 1
"Java".length()   // 4
"Java 17".length() // 7: the space in the middle is also counted
"  ".length()     // 2: two spaces
"\n".length()     // 1: one newline character
"\r\n".length()   // 2: two code units (CR and LF)
```

These are illustrative expressions, not a standalone Java file. The result of `length()` includes **all** UTF-16 code units in the string, including whitespace and control characters; the method does not automatically strip, trim, or skip any character.

### Why not simply call it “number of characters”?

Java `String` uses a UTF-16 indexing model for `length()`, `charAt()`, and `substring()`. A Unicode character can be represented by **one** or **two** UTF-16 code units:

- Most common characters in the BMP (Basic Multilingual Plane), for example `A`, `á`, or common Chinese characters: **1** UTF-16 code unit.
- A Unicode character outside the BMP, for example many emoji: **2** UTF-16 code units, in the form of a *surrogate pair*.

Therefore, `length()` is **not** a count of Unicode code points, not the number of letters/graphemes the user sees, and also not the number of bytes when stored in UTF-8.

There are three distinct concepts:

| Metric | Meaning | How to check |
| --- | --- | --- |
| UTF-16 code units | Units used as indices in `String` | `s.length()` |
| Unicode code points | Logical Unicode values in a UTF-16 sequence | `s.codePointCount(0, s.length())` |
| Bytes in an encoding | Size when encoding the string into bytes | `s.getBytes(StandardCharsets.UTF_8).length` for UTF-8 |

A **grapheme cluster** (for example a letter combined with an accent or a multi-component emoji) can consist of multiple Unicode code points; therefore even `codePointCount()` does not guarantee an accurate count of characters as perceived by the user. When limiting the “number of visible characters”, an appropriate grapheme segmentation standard is needed, rather than relying solely on `length()`.

## 2. What does `isEmpty()` check?

Syntax:

```java
boolean empty = text.isEmpty();
```

For a non-`null` `String` object, the two conditions below are **equivalent in result**:

```java
text.isEmpty()
text.length() == 0
```

You can think of `isEmpty()` as a direct expression of intent: **“Does the string have length 0?”**.

Examples:

| String value | `length()` | `isEmpty()` | Explanation |
| --- | ---: | --- | --- |
| `""` | 0 | `true` | No code units at all. |
| `"Java"` | 4 | `false` | Four ASCII letters. |
| `" "` | 1 | `false` | Contains one space. |
| `"  "` | 2 | `false` | Contains two spaces. |
| `"\t"` | 1 | `false` | Contains one tab. |
| `"\n"` | 1 | `false` | Contains one newline character. |
| `" \t\n"` | 3 | `false` | Whitespace only, but still has content in terms of UTF-16 code units. |

`isEmpty()` does **not** automatically strip whitespace, and does **not** return `true` just because the string “looks like it has no letters”. If the business requirement is “a user entering only spaces is also considered as having entered nothing”, see `isBlank()` in the next section.

## 3. First Java 17+ program: length, emptiness, and whitespace

Create the file `LengthAndEmptyDemo.java`:

```java
public class LengthAndEmptyDemo {
    public static void main(String[] args) {
        String empty = "";
        String spaces = " \t";
        String text = "Java";

        System.out.println("empty.length = " + empty.length());
        System.out.println("empty.isEmpty = " + empty.isEmpty());

        System.out.println("spaces.length = " + spaces.length());
        System.out.println("spaces.isEmpty = " + spaces.isEmpty());
        System.out.println("spaces.isBlank = " + spaces.isBlank());

        System.out.println("text.length = " + text.length());
        System.out.println("text.isEmpty = " + text.isEmpty());

        String maybeNull = null;
        System.out.println(
            "null-or-empty = " + (maybeNull == null || maybeNull.isEmpty())
        );
        System.out.println(
            "has-text = " + (text != null && !text.isEmpty())
        );
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac LengthAndEmptyDemo.java
java LengthAndEmptyDemo
```

Output:

```text
empty.length = 0
empty.isEmpty = true
spaces.length = 2
spaces.isEmpty = false
spaces.isBlank = true
text.length = 4
text.isEmpty = false
null-or-empty = true
has-text = true
```

Points to observe:

1. `""` has no code units, so `length() == 0` and `isEmpty() == true`.
2. `" \t"` has two code units, so `isEmpty() == false` even though it has no letters. It is *blank* according to `isBlank()`.
3. The expression `maybeNull == null || maybeNull.isEmpty()` is safe thanks to **short-circuit evaluation**: if the first side is `true`, Java does not evaluate the second side, avoiding calling a method on `null`.
4. `text != null && !text.isEmpty()` returns `true` only when the reference exists and the string has a length greater than 0.

## 4. Distinguishing empty string, blank string, and `null`

Three common cases when processing input data:

**Empty string:** `String s = "";`. This is a valid `String` object with length 0; `s.isEmpty()` is `true`.

**Whitespace-only string — blank:** `String s = "  \t";`. The string has a length greater than 0, so `isEmpty()` is `false`; `isBlank()` is `true`.

**`null` reference:** `String s = null;`. There is no `String` object being referenced; calling `s.length()` or `s.isEmpty()` throws `NullPointerException`. You cannot say “`null` has length 0”: `null` is not an empty string.

### `isEmpty()` and `isBlank()`

`String.isBlank()` has been available since Java 11. It returns `true` if the string is empty **or** contains only Unicode code points considered whitespace by `Character.isWhitespace(int)`.

```java
String a = "";
String b = " \t\n";
String c = " Java ";

System.out.println(a.isEmpty()); // true
System.out.println(a.isBlank()); // true

System.out.println(b.isEmpty()); // false
System.out.println(b.isBlank()); // true

System.out.println(c.isEmpty()); // false
System.out.println(c.isBlank()); // false
```

This snippet is an example placed inside a method, and the comments indicate the corresponding printed output.

Choose the method based on the actual requirement:

- Only want to know whether **the string has length 0**: use `isEmpty()`.
- Want to treat **a whitespace-only string as having no content**: use `isBlank()` when it fits Java's whitespace rules.
- Want to strip leading and trailing whitespace before checking: consider `strip().isEmpty()` (Java 11+) or `trim().isEmpty()` depending on the desired standard. `strip()` and `trim()` identify leading/trailing characters differently; do not assume they are completely synonymous with each other or with `isBlank()` in all Unicode cases.

Note: the definition of whitespace in `Character.isWhitespace` **does not include every Unicode space character that may look like whitespace** (for example some non-breaking spaces). If a business rule needs to handle those characters, define and test a separate rule.

### Safe `null`-checking patterns

```java
// true if the variable references no String or points to an empty String:
boolean missing = s == null || s.isEmpty();

// true if the variable has a non-empty String:
boolean nonEmpty = s != null && !s.isEmpty();

// true if non-null and has at least one non-whitespace code point:
boolean hasNonBlankText = s != null && !s.isBlank();
```

This is a fragment inside a method where the variable `String s` has already been declared. Use the order above to avoid `NullPointerException`. If a rule needs to distinguish between `null` (no data provided) and `""` (empty data), keep them as **two separate states**; do not merge them by default.

## 5. UTF-16: `length()` can differ from the number of Unicode code points

Create the file `UnicodeLengthDemo.java`:

```java
import java.nio.charset.StandardCharsets;

public class UnicodeLengthDemo {
    public static void main(String[] args) {
        String ascii = "Java";
        String accented = "\u00E9";           // é, a code point in the BMP.
        String emoji = "\uD83D\uDE00";       // 😀, surrogate pair.
        String combining = "e\u0301";         // e + combining acute accent.

        printLengths("ascii", ascii);
        printLengths("accented", accented);
        printLengths("emoji", emoji);
        printLengths("combining", combining);

        String mixed = "A" + emoji + "B";
        System.out.println("mixed.length = " + mixed.length());
        System.out.println(
            "mixed.codePoints = " +
            mixed.codePointCount(0, mixed.length())
        );
        System.out.println(
            "highSurrogateAt1 = " +
            Character.isHighSurrogate(mixed.charAt(1))
        );
        System.out.println(
            "emojiSubstringEquals = " + mixed.substring(1, 3).equals(emoji)
        );
    }

    private static void printLengths(String name, String value) {
        System.out.println(
            name + ": units=" + value.length()
            + ", codePoints=" + value.codePointCount(0, value.length())
            + ", utf8Bytes=" +
            value.getBytes(StandardCharsets.UTF_8).length
        );
    }
}
```

Run:

```bash
javac UnicodeLengthDemo.java
java UnicodeLengthDemo
```

Output:

```text
ascii: units=4, codePoints=4, utf8Bytes=4
accented: units=1, codePoints=1, utf8Bytes=2
emoji: units=2, codePoints=1, utf8Bytes=4
combining: units=2, codePoints=2, utf8Bytes=3
mixed.length = 4
mixed.codePoints = 3
highSurrogateAt1 = true
emojiSubstringEquals = true
```

Explanation:

- `"\u00E9"` represents the character `é` which has one code point, one UTF-16 code unit, but **two bytes** when encoded in UTF-8.
- `"\uD83D\uDE00"` represents the emoji 😀 using a surrogate pair of two code units; it is **one code point**, **four UTF-8 bytes**.
- `"e\u0301"` contains the letter `e` and a combining acute accent. It usually **renders similarly** to `é` but has **two code points**, **two UTF-16 code units**, and **three UTF-8 bytes**. Thus, different `length()` values do not necessarily mean a different number of “characters” seen by the user.
- `mixed` is `"A" + emoji + "B"`. The corresponding UTF-16 indices: `A` at 0; the two surrogate halves at 1 and 2; `B` at 3. Hence `length() == 4` and `codePointCount(...) == 3`. `substring(1, 3)` takes both code units of the emoji, producing content equal to `emoji`.

**Do not split in the middle of a surrogate pair:** `mixed.substring(1, 2)` takes only one surrogate, not the intact emoji. When processing data by Unicode code point, consider `codePointAt()`, `codePoints()`, and ways to convert from a code point index to a UTF-16 index such as `offsetByCodePoints()`. For user-input strings containing combined emoji, grapheme segmentation is also needed if the operation is described in terms of “visible characters”.

## 6. Using `length()` as a bound when accessing strings

`charAt(index)` takes a **UTF-16 code unit** index, starting from 0. An index is valid only when `0 <= index < s.length()`; the value `length()` is the boundary **after** the last unit.

```java
String s = "Java";
if (!s.isEmpty()) {
    System.out.println(s.charAt(s.length() - 1)); // a
}
```

For an empty string, `length() - 1 == -1`, so `charAt(-1)` cannot be read. If `s` might be `null`, check `s != null && !s.isEmpty()` before calling. Checking negative indices, loops, and error handling are practiced thoroughly in the lesson **charAt and valid index conditions**; here, remember that `length()` measures *code units*, so `charAt(length() - 1)` may read a **low surrogate** instead of the entire code point when an emoji is at the end of the string.
## 7. Practical use cases

### Checking optional parameters

If an empty string means the user did not provide a value, you can use:

```java
static boolean isProvided(String value) {
    return value != null && !value.isEmpty();
}
```

If plain spaces should not be accepted, use `!value.isBlank()` instead of `!value.isEmpty()`. Set the rule according to data requirements: there are cases where a single space is actually valid data.

### Limiting input data length

```java
static boolean fitsUtf16Limit(String input, int maxUnits) {
    return input != null
        && maxUnits >= 0
        && input.length() <= maxUnits;
}
```

This method enforces a **UTF-16 code unit limit**. It is suitable if the data contract specifies that exact metric. If the system requires at most a certain number of Unicode code points, count with `input.codePointCount(0, input.length())`; if the payload limit is in UTF-8 bytes, check the byte length after encoding. Do not use `length()` to assert the byte size of data.

### Iterating over string content

```java
String s = "ABC";
for (int index = 0; index < s.length(); index++) {
    System.out.print(s.charAt(index));
}
System.out.println(); // ABC
```

This is a way to iterate over **UTF-16 code units**. It works well when operating by `char` index, but a different approach is needed if each step must handle a full Unicode code point or grapheme. Because `String` is immutable, `length()`, `isEmpty()`, and `charAt()` do not mutate the string object itself.

### Performance

In modern Java JDKs, `length()` and `isEmpty()` check the already-known length information without scanning the entire string content. Prefer **syntax that directly expresses your intent**: `isEmpty()` when asking if it is empty; `length()` when you actually need the number of code units or are working with indices. Conversely, `codePointCount()` must examine the code units in the range to detect surrogate pairs; checking byte length in an encoding requires performing the encoding.

There is no need to replace `isEmpty()` with `length() == 0` just to “optimize” without benchmark evidence, as both have the same meaning and usually make no meaningful difference.

## 8. Common mistakes

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| “`" ".isEmpty()` is `true`.” | A space is still a code unit. | Use `isBlank()` if you want to treat whitespace as empty for business logic. |
| “`null.isEmpty()` returns `true`.” | There is no object to call the method on; throws NPE. | Check `s == null` before calling. |
| “`length()` is the number of UTF-8 bytes.” | `length()` counts UTF-16 code units. | Use `getBytes(StandardCharsets.UTF_8).length` if you need UTF-8 bytes. |
| “`length()` always equals the number of Unicode code points.” | Characters outside the BMP require two code units. | Use `codePointCount(0, s.length())` for code points. |
| “The number of code points is always the number of visible characters.” | Combining accents and multi-component emoji can contain multiple code points. | Use a grapheme segmentation algorithm when needed. |
| “`s.charAt(s.length() - 1)` is always safe.” | An empty string produces index `-1`, and a `null` string throws NPE. | Check `s != null && !s.isEmpty()` first. |
| “`isEmpty()` strips whitespace before checking.” | It is strictly equivalent to `length() == 0`. | Explicitly apply the desired whitespace policy. |
| “`isBlank()` exists in every Java version.” | `String.isBlank()` was added in Java 11. | Available on Java 17+; use another approach on older JDKs. |

## 9. Self-check

**Exercise 1.** Given:

```java
String s = "  ";
System.out.println(s.length());
System.out.println(s.isEmpty());
System.out.println(s.isBlank());
```

Output:

```text
2
false
true
```

Explanation: two spaces are two UTF-16 code units; the string is not empty but consists only of whitespace.

**Exercise 2.** Given:

```java
String s = "";
boolean result = s == null || s.isEmpty();
System.out.println(result);
```

Output: `true`. If `s` is changed to `null`, the result is still `true` thanks to the short-circuiting `||` operator.

**Exercise 3.** Given `String s = "\uD83D\uDE00";`. What is `s.length()`, and what is `s.codePointCount(0, s.length())`?

The answers are **2** and **1**, respectively: one Unicode code point outside the BMP is represented by two UTF-16 code units.

**Exercise 4.** A form specifies a maximum password length of 20 **UTF-8 bytes**. Is `password.length() <= 20` correct?

Not yet. `length()` measures UTF-16 code units, not UTF-8 bytes. You must encode as UTF-8 and check the byte count, or let the data-receiving layer validate against the specified standard.

## Summary

- `length()` gives the **number of UTF-16 code units** in a `String`.
- `isEmpty()` only checks **`length() == 0`**.
- A whitespace-only string is not empty according to `isEmpty()`; `isBlank()` addresses a different need.
- `null` is not an empty string; check the reference before calling methods.
- When a requirement uses “length”, clarify whether it is counting **UTF-16 units**, **Unicode code points**, **grapheme clusters**, or **encoded bytes**.

## References

- [Java SE 21 API — `java.lang.String`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): contracts of `length()`, `isEmpty()`, `isBlank()`, `codePointCount()`, `charAt()`, and `substring()`.
- [Java SE 21 API — `java.lang.Character`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html): definitions of code points, surrogate pairs, and whitespace.
- [Java Language Specification §3.10.5 — String Literals](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.10.5): string syntax and escape sequences.
