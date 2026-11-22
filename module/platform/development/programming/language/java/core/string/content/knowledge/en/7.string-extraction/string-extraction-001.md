# `String.substring(beginIndex)`: Extracting a Substring from a Position to the End in Java

## 1. Problem and Meaning of `substring(beginIndex)`

When you already have a string and only need to keep the part **starting from a specific position to the last character**, Java provides the method:

```java
public String substring(int beginIndex)
```

This method belongs to the `java.lang.String` class. It returns a `String` representing the **remainder of the string**, starting **at** `beginIndex`, including the character at that position (if any) and all characters after it.

```java
String text = "Java Core";
String part = text.substring(5);

System.out.println(part); // Core
```

The string `"Java Core"` has the following positions:

```text
Chars:  J  a  v  a     C  o  r  e
Index:  0  1  2  3  4  5  6  7  8
```

Index `5` points to the letter `C`. Therefore, `text.substring(5)` returns `"Core"`.

**Key point:** `beginIndex` is the **starting** index, counted from `0`. With the **single-parameter** version, you do not need to specify an end point: Java automatically takes everything to the end of the string.

## 2. Syntax and Return Value

Common form:

```java
String original = "abcdef";
String suffix = original.substring(2); // "cdef"
```

- **Target object:** `original` is of type `String`, not `null`.
- **Parameter:** `beginIndex` is an `int` integer, representing the starting position.
- **Result:** A `String` value containing the characters from position `beginIndex` to the end.
- **Original string:** Unchanged, because `String` is an **immutable** object.

In index-range notation, with `length = original.length()`, the selected part has the range **`[beginIndex, length)`**: the starting position is included, while `length` is the *exclusive* end boundary. This is half-open interval notation; there is no character at position `length`.

### Valid Indices

The method requires:

\[
0 \leq \texttt{beginIndex} \leq \texttt{length()}
\]

| `beginIndex` | Result | Reason |
|---|---|---|
| `0` | Entire string content | Starts from the first character |
| `1` to `length() - 1` | Suffix starting from the corresponding index | Skips the preceding part |
| `length()` | Empty string `""` | No characters remain after the starting mark |
| Negative number | Throws `StringIndexOutOfBoundsException` | Lies before the start of the string |
| Greater than `length()` | Throws `StringIndexOutOfBoundsException` | Exceeds the end point |

**Do not confuse `length()` with the index of the last character.** For a non-empty string, the index of the last character is `length() - 1`. However, `substring(length())` is **still valid** and returns an empty string.

For example, the string `"Java"` has length `4`:

```java
String s = "Java";

s.substring(0); // "Java"
s.substring(1); // "ava"
s.substring(2); // "va"
s.substring(3); // "a"
s.substring(4); // ""
// s.substring(5); // StringIndexOutOfBoundsException
```

The lines above illustrate expressions inside a method; they are **not** a standalone Java file.

## 3. Step-by-Step Mechanism

Consider:

```java
String word = "Programming";
String remainder = word.substring(7);
```

Zero-based indexing:

```text
P  r  o  g  r  a  m  m  i  n  g
0  1  2  3  4  5  6  7  8  9  10
                     ^
                   index 7: m
```

`word.substring(7)` returns `"ming"` (consisting of the characters at indices 7, 8, 9, and 10). The `"Program"` part before the starting mark is not in the result. `word` remains `"Programming"`.

This can be understood in three steps:

1. Determine the string length (`word.length()` is `11`).
2. Check whether `beginIndex` is in the range from `0` to `11`, inclusive of `11`.
3. Return the content from `beginIndex` to the end; if starting at `11`, the result is `""`.

You do not need to call `.substring(beginIndex, word.length())` for this common case; the single-parameter form clearly expresses the intent to **take until the end**.

## 4. Complete, Runnable Java 17+ Example

Create the file **`SubstringToEndDemo.java`**:

```java
public class SubstringToEndDemo {
    public static void main(String[] args) {
        String text = "Java Core";

        String suffix = text.substring(5);
        System.out.println("part=" + suffix);
        System.out.println("original=" + text);

        System.out.println("all=" + text.substring(0));
        System.out.println("atEnd=[" + text.substring(text.length()) + "]");

        String fileName = "report.csv";
        int lastDot = fileName.lastIndexOf('.');
        String extension = lastDot == -1
                ? "(none)"
                : fileName.substring(lastDot + 1);
        System.out.println("extension=" + extension);

        String path = "/users/42";
        int lastSlash = path.lastIndexOf('/');
        String lastSegment = path.substring(lastSlash + 1);
        System.out.println("lastSegment=" + lastSegment);

        String unicode = "A😀B";
        String afterA = unicode.substring(1);
        System.out.println("utf16Length=" + unicode.length());
        System.out.println("suffixCodePoints="
                + afterA.codePointCount(0, afterA.length()));

        try {
            text.substring(text.length() + 1);
        } catch (StringIndexOutOfBoundsException ex) {
            System.out.println("badIndex="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

In the directory containing the file, compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 SubstringToEndDemo.java
java SubstringToEndDemo
```

**Expected stdout:**

```text
part=Core
original=Java Core
all=Java Core
atEnd=[]
extension=csv
lastSegment=42
utf16Length=4
suffixCodePoints=2
badIndex=StringIndexOutOfBoundsException
```

Notable points explained:

- `text.substring(5)` returns `"Core"`. Printing `text` again shows that the original string is unchanged.
- `text.substring(0)` takes the entire content.
- `text.substring(text.length())` returns `""`, so when wrapped in `[...]` we see `[]`.
- `lastIndexOf('.')` returns the position of the last dot; `substring(lastDot + 1)` takes the part **after** the dot, yielding `"csv"`.
- `lastIndexOf('/')` finds the last separator of an illustrative path, and then `substring(lastSlash + 1)` extracts `"42"`.
- The string `"A😀B"` has **4 UTF-16 code units** (`A` = 1, emoji = 2, `B` = 1). The suffix after `A` contains **2 Unicode code points** (the emoji and `B`).
- An index greater than the length causes `StringIndexOutOfBoundsException`; the example catches the exception so the demonstration can continue running.

> Note: The example uses `/` in a simple path string to teach extraction. Parsing real URLs, OS file paths, or encoded paths requires the appropriate specialized APIs depending on context.

## 5. Extracting the Suffix After a Separator Character

A practical use is to **find the starting point and take the entire remainder**. For example:

```java
String record = "ID:12345";
int colon = record.indexOf(':');

if (colon >= 0) {
    String value = record.substring(colon + 1);
    System.out.println(value); // 12345
}
```

Why `+ 1`? `indexOf(':')` returns the position of `:`. If you call `substring(colon)`, the result will still include the separator (`":12345"`). Use `colon + 1` to start at the next character.

You must distinguish between two goals:

```java
String text = "key=value";
int equal = text.indexOf('=');

String includingSeparator = text.substring(equal);     // "=value"
String excludingSeparator = text.substring(equal + 1); // "value"
```

These are illustrative snippets inside a method, with an input string already known to contain `=`. If the separator is **not guaranteed to exist**, always check the search result.

### Handling the Case Where the Separator Is Not Found

`indexOf(...)` and `lastIndexOf(...)` return `-1` when the target character or string is not found. Usually you must check:

```java
static String valueAfterColon(String input) {
    int colon = input.indexOf(':');
    if (colon < 0) {
        return "";
    }
    return input.substring(colon + 1);
}
```

The method above returns `""` when there is no `:`. This is just **one design choice**; depending on the problem, you may also want to return the entire string, an `Optional<String>`, or report malformed input.

A subtle bug to avoid: if you write `substring(indexOf(':') + 1)` without checking, when the separator is not found `indexOf` returns `-1`, adding `1` yields `0`, and the method silently returns the **entire string**. It does not throw an exception, so it can easily mask invalid input data.

## 6. Using Length to Get the Last N Characters

To get the **last `n` UTF-16 code units**, the starting point is typically:

\[
\texttt{start = text.length() - n}
\]

For example:

```java
String code = "INV-2026";
String year = code.substring(code.length() - 4);

System.out.println(year); // 2026
```

Because `"INV-2026"` is `8` code units long, `start = 8 - 4 = 4`; the suffix from index `4` is `"2026"`.

To be safe, ensure `0 <= n <= text.length()`:

```java
static String lastUnits(String text, int n) {
    if (n < 0 || n > text.length()) {
        throw new IllegalArgumentException("n is outside string length");
    }
    return text.substring(text.length() - n);
}
```

The `lastUnits` method operates on **code units**, which does not guarantee always extracting `n` human-perceived Unicode characters. With emojis or supplementary characters represented by surrogate pairs, the cut point might fall in the middle of a pair. The next section explains how to avoid this issue.

## 7. `String` Indices Use UTF-16

`String.length()` and `substring` offsets count **UTF-16 code units**, not necessarily the number of Unicode code points or displayed characters. For instance, `"A😀B"` has length `4`: the emoji occupies two code units. `substring(1)` starts cleanly at the emoji, whereas `substring(2)` starts in the middle of the surrogate pair and can leave an unpaired surrogate.

When you need to slice by **code points**, convert the code point count into a UTF-16 offset using `offsetByCodePoints` before slicing:

```java
String text = "A😀B";
int start = text.offsetByCodePoints(0, 2);
System.out.println(text.substring(start)); // B
```

This is an illustrative snippet inside a method. Slicing by code points can still split letter clusters with combining marks or multi-code-point emojis; those display cases require separate grapheme segmentation.

## 8. Edge Cases and Common Mistakes

### Mistake A: Thinking Indices Start at 1

**Wrong intent:**

```java
String s = "Java";
System.out.println(s.substring(1)); // ava
```

To get all of `"Java"`, start from **`0`**, not `1`.

### Mistake B: Assuming an Index Equal to `length()` Is Invalid

```java
String s = "abc";
System.out.println("[" + s.substring(3) + "]"); // []
```

An index equal to the length is valid and returns an empty string. Only an index **greater than** `length()` is out of bounds.

### Mistake C: Ignoring the Return Value

```java
String s = "abcdef";
s.substring(3);
System.out.println(s); // abcdef
```

`String` is immutable, so `substring` **does not modify in place**. If you want to keep the suffix:

```java
s = s.substring(3);
System.out.println(s); // def
```

Reassigning changes the value of the variable `s`, rather than modifying the content of the original `String` object.

### Mistake D: Using the Result of `indexOf` Without Checking

```java
String s = "no-separator";
int index = s.indexOf(':'); // -1
String part = s.substring(index + 1); // Evaluates to "no-separator"
```

There is no `:`, yet `-1 + 1` becomes `0`. You must check `index >= 0` if a missing separator needs special handling.

### Mistake E: Passing a Negative Index or One Exceeding Length

```java
String s = "abc";
// s.substring(-1); // Throws StringIndexOutOfBoundsException
// s.substring(4);  // Throws StringIndexOutOfBoundsException
```

You can check bounds before calling:

```java
static String fromIndex(String text, int beginIndex) {
    if (beginIndex < 0 || beginIndex > text.length()) {
        throw new IllegalArgumentException("Invalid beginIndex");
    }
    return text.substring(beginIndex);
}
```

This wrapper method illustrates choosing an application-level exception. If you call `substring` directly with an invalid index, Java throws `StringIndexOutOfBoundsException`.

### Mistake F: Calling the Method on `null`

```java
String s = null;
// s.substring(0); // Throws NullPointerException
```

`null` is not a `String` object, so no method can be called on it. This is a **different** error from an invalid index. Validate input if `null` is allowed in the program's design.

### Mistake G: Confusing `substring(int)` with `substring(int, int)`

Two ways to call:

```java
String s = "abcdefgh";

s.substring(3);    // "defgh": from 3 to the end
s.substring(3, 6); // "def": takes indices 3, 4, 5; excludes 6
```

The two-parameter form lets you specify an explicit end point (`endIndex` is exclusive). The single-parameter form **always** takes up to the end, so choose it when that matches your intent instead of unnecessarily computing the end index.

## 9. Distinguishing from Similar Operations

| Problem | Appropriate Method | Example |
|---|---|---|
| Take the part from an index to the end | `substring(beginIndex)` | `"abcdef".substring(3)` → `"def"` |
| Take the part between two marks | `substring(beginIndex, endIndex)` | `"abcdef".substring(1, 4)` → `"bcd"` |
| Get the starting position of a segment | `indexOf(...)` | `"a:b".indexOf(':')` → `1` |
| Get the last occurrence position | `lastIndexOf(...)` | `"a:b:c".lastIndexOf(':')` → `3` |
| Find the number of UTF-16 code units | `length()` | `"Java".length()` → `4` |
| Extract from a code-point-based position | `offsetByCodePoints(...)` then `substring(...)` | Avoids cutting in the middle of a surrogate pair |

`substring` only **extracts a defined range**. If you do not yet know where the starting point is, combine it with `indexOf`/`lastIndexOf` or an algorithm that locates the position according to data rules.

## 10. Notes on Performance and the Returned Object

`substring` returns an immutable `String` value; there is no public guarantee that the result is always a new instance, always the source instance, or backed by a specific memory mechanism. An implementation may optimize taking the whole string or an empty string. Therefore, when comparing content, use `equals` instead of `==`.

For large-scale string processing, measure performance and allocation on the target JDK with real data. Do not create extra copies solely on the assumption that `substring` necessarily shares or copies memory buffers.

## 11. Exercises and Answers

**Exercise 1.** Given `String s = "Hello World";`, extract `"World"`.

**Answer:**

```java
String result = s.substring(6);
```

The space is at index `5`, and `W` is at index `6`.

**Exercise 2.** Given `"ABC"`, what are the three results of `substring(0)`, `substring(2)`, and `substring(3)`?

**Answer:** `"ABC"`, `"C"`, and `""`, respectively.

**Exercise 3.** Given `"token:abc:def"`, extract all characters after the **first `:`**.

**Answer:**

```java
String input = "token:abc:def";
int p = input.indexOf(':');
String value = p < 0 ? "" : input.substring(p + 1);
// value = "abc:def"
```

If you need everything after the **last** `:`, change `indexOf(':')` to `lastIndexOf(':')`, in which case the value is `"def"`.

**Exercise 4.** Why does `"A😀B".substring(2)` require caution?

**Answer:** Index `2` falls between the two UTF-16 code units representing the emoji, which can break the surrogate pair. Determine the code point (or grapheme, depending on the problem) boundary before slicing.

**Exercise 5.** What does the following snippet print?

```java
String s = "12345";
s.substring(3);
System.out.println(s);
```

**Answer:** `12345`. The value `"45"` is returned but discarded, while the original string remains unchanged.

## 12. Key Takeaways

`String.substring(beginIndex)` can be read as: **“Take the string from index `beginIndex` (inclusive) to the end”**. Indices start at `0`, the valid range is **`0` to `length()` (inclusive on both ends)**, starting at `length()` produces an empty string, and going out of bounds throws `StringIndexOutOfBoundsException`. The result is a `String` value that must be stored or used; the original string remains immutable. When data contains emojis or supplementary Unicode characters, remember that `String` indices measure **UTF-16 code units**, not necessarily visible characters.
