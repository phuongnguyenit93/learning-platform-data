# Negative, Out-of-Length, or Reversed Boundary Cases When Extracting Substrings

When extracting a portion of content with `String.substring(...)` in Java, the most common mistake is not the character to extract, but the **index range**: a negative start position, an end position exceeding the length, or two reversed positions. These cases must be distinguished from **valid but empty** ranges, as well as ranges that are valid in UTF-16 but slice through the middle of a Unicode character.

This lesson focuses on the boundary rules of `substring(beginIndex)`, `substring(beginIndex, endIndex)`, and `subSequence(start, end)`, how to interpret errors, how to validate input data, and practical scenarios such as extracting suffixes, using `indexOf()` results, or extracting text containing emojis.

## 1. Index Conventions to Keep in Mind Before Checking Errors

`substring(begin, end)` takes the half-open interval `[begin, end)` measured in UTF-16 code units: `begin` is included, `end` is excluded, and the length is `end - begin` when valid. For a source of length `n`, valid **boundaries** can take values from `0` to `n`, even though the last character's index is `n - 1`.

```java
String s = "Java";
System.out.println(s.substring(1, 3)); // av
System.out.println(s.substring(4, 4).isEmpty()); // true
```

The focus of error handling is distinguishing **valid but empty boundaries** from negative, out-of-length, and reversed boundaries. `substring(begin)` is equivalent in content to `substring(begin, s.length())` when valid.

## 2. Three Required Conditions for the Range `[begin, end)`

The validity formula for `text.substring(begin, end)` is:

```text
0 <= begin <= end <= text.length()
```

If even **one** of the following conditions occurs, the range is invalid:

1. **Negative index:** `begin < 0`, or `end < 0`. For example, `substring(-1, 2)`, `substring(0, -1)`.
2. **Exceeds length:** `end > length()` or `begin > length()`. For example, a string of length 4 given `substring(0, 5)`, `substring(5)`.
3. **Reversed order:** `begin > end`, even when both lie between 0 and `length()`. For example, `substring(3, 1)`.

Java reports **`IndexOutOfBoundsException`** when the index contract of `substring` is violated. Exception message details can vary across JDK versions; business logic should not depend on that message string. The exception occurs **at the extraction call**, before any resulting string is returned.

For a quick check, you can use the expression:

```java
boolean valid = begin >= 0
        && begin <= end
        && end <= text.length();
```

This is an **illustrative snippet**, assuming `text != null`. If all three clauses are true, both `begin` and `end` lie within valid boundaries; there is no need to add `begin <= text.length()` because it already follows from `begin <= end <= text.length()`. If `text == null`, accessing `text.length()` throws `NullPointerException`, which is a different error from an index error.

### Do Not Confuse an Invalid Range with an Empty Range

- `begin == end` is **valid**, yielding `""`.
- `begin > end` is **invalid**; Java throws an exception.
- The source string `""` has length 0, so it has only one valid range: `substring(0, 0)`; for the single-parameter version, `substring(0)`.
- `substring(0, length())` is always a valid range if the source string is non-null.
- `substring(length(), length())` is also always valid; many algorithms need this case to represent “an empty tail with no characters”.

## 3. Java 17+ Example Checking Each Boundary Case

Save the following file as **`SubstringBoundsDemo.java`**:

```java
public class SubstringBoundsDemo {
    private static void test(String source, int begin, int end) {
        try {
            String part = source.substring(begin, end);
            System.out.println("[" + begin + "," + end + ") -> <"
                    + part + "> (length=" + part.length() + ")");
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("[" + begin + "," + end + ") -> INVALID");
        }
    }

    public static void main(String[] args) {
        String value = "Java";
        System.out.println("source length: " + value.length());

        test(value, 0, 4);
        test(value, 1, 3);
        test(value, 2, 2);
        test(value, 4, 4);

        test(value, -1, 2);
        test(value, 0, -1);
        test(value, 0, 5);
        test(value, 5, 5);
        test(value, 3, 2);

        test("", 0, 0);
    }
}
```

Compile and run in the directory containing the file:

```bash
javac SubstringBoundsDemo.java
java SubstringBoundsDemo
```

**Stdout:**

```text
source length: 4
[0,4) -> <Java> (length=4)
[1,3) -> <av> (length=2)
[2,2) -> <> (length=0)
[4,4) -> <> (length=0)
[-1,2) -> INVALID
[0,-1) -> INVALID
[0,5) -> INVALID
[5,5) -> INVALID
[3,2) -> INVALID
[0,0) -> <> (length=0)
```

In the example, `IndexOutOfBoundsException` is caught solely to **demonstrate classifying** the cases. In real applications, it is better to validate arguments or define an error policy before calling `substring()`; catching and ignoring every exception can hide programming bugs.

## 4. Comparing Index Domains to Avoid Misusing APIs

| API | Validity Condition | Point to Check |
| --- | --- | --- |
| `s.substring(begin)` | `0 <= begin <= n` | `begin == n` yields an empty string |
| `s.substring(begin, end)` | `0 <= begin <= end <= n` | Order of the two bounds must be valid |
| `s.subSequence(begin, end)` | `0 <= begin <= end <= n` | Declared return type is `CharSequence` |
| `s.charAt(index)` | `0 <= index < n` | `charAt(n)` is invalid |

The same offset `n` can be valid as a **boundary** for `substring` yet invalid for `charAt`. Likewise, `substring(k, k)` does not read the code unit at `k`; it returns an empty segment, whereas `substring(k, k + 1)` takes one code unit if `k < n`. These methods do not automatically adjust invalid indices.

## 5. Off-by-One Error: `end` Is Exclusive

Off-by-one errors often happen by mistaking `end` for the position of the last character **included**. For example, to take characters at positions 1, 2, and 3 of `"Java"`:

```java
"Java".substring(1, 3); // "av": only takes positions 1 and 2
"Java".substring(1, 4); // "ava": takes positions 1, 2, 3
```

All expressions above are illustrative snippets.

If an external requirement gives an **inclusive** ending index `lastInclusive`, extraction can use `substring(begin, lastInclusive + 1)` **only after** verifying that `lastInclusive` is an actual element index—meaning `0 <= lastInclusive < length` and `begin <= lastInclusive`. Never blindly add 1 to an arbitrary value, as that can exceed `length()` or cause integer overflow for very large values.

Another type of requirement is “take **count** code units starting from position **start**”. The natural form is `substring(start, start + count)`, but you must guard:

- `start >= 0`;
- `count >= 0`;
- `start <= length()`;
- `count <= length() - start`.

Checking `count <= length() - start` avoids computing `start + count` before ensuring there is no integer overflow. Compute the sum only after validation.

## 6. Validating Input Before Extraction

There are two reasonable approaches depending on the business contract: **reject invalid ranges** with a clear exception message, or **allow adjusting the range** if the problem requirements permit. Never silently clamp every invalid index into bounds when the caller needs to know the input data is erroneous.

### 6.1. Strict Policy: Invalid Ranges Must Report an Error

**`StrictSliceDemo.java`**

```java
import java.util.Objects;

public class StrictSliceDemo {
    private static String slice(String text, int begin, int end) {
        Objects.requireNonNull(text, "text");

        if (begin < 0 || end < begin || end > text.length()) {
            throw new IllegalArgumentException(
                    "Invalid slice: [" + begin + "," + end
                    + ") for length " + text.length());
        }

        return text.substring(begin, end);
    }

    public static void main(String[] args) {
        System.out.println("<" + slice("Java", 1, 3) + ">");
        System.out.println("<" + slice("Java", 4, 4) + ">");
        System.out.println("<" + slice("", 0, 0) + ">");

        try {
            slice("Java", 3, 2);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected reversed bounds");
        }

        try {
            slice("Java", -1, 2);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected negative begin");
        }
    }
}
```

```bash
javac StrictSliceDemo.java
java StrictSliceDemo
```

**Stdout:**

```text
<av>
<>
<>
Rejected reversed bounds
Rejected negative begin
```

In `slice`, the combined condition is sufficient to block negative `begin`, `end` preceding `begin`, or `end` exceeding length. If `begin > length`, it cannot simultaneously satisfy `end >= begin` and `end <= length`, so that is also blocked. Here the code **explicitly** throws `IllegalArgumentException` for arguments violating the helper function's contract; this is not claiming that `substring` itself throws that exception. An API may choose a different exception type or return type to match its design.

### 6.2. Range-Clamping Policy: Only When the Specification Allows It

Suppose the requirement is “take at most the first `maxUnits` code units”; if `maxUnits` exceeds the length, take the whole string, while a negative value remains invalid input:

**`PrefixLimitDemo.java`**

```java
import java.util.Objects;

public class PrefixLimitDemo {
    private static String prefixAtMost(String text, int maxUnits) {
        Objects.requireNonNull(text, "text");
        if (maxUnits < 0) {
            throw new IllegalArgumentException("maxUnits must be >= 0");
        }

        int end = Math.min(maxUnits, text.length());
        return text.substring(0, end);
    }

    public static void main(String[] args) {
        System.out.println("<" + prefixAtMost("Java", 2) + ">");
        System.out.println("<" + prefixAtMost("Java", 10) + ">");
        System.out.println("<" + prefixAtMost("Java", 0) + ">");
        System.out.println("<" + prefixAtMost("", 3) + ">");
    }
}
```

```bash
javac PrefixLimitDemo.java
java PrefixLimitDemo
```

**Stdout:**

```text
<Ja>
<Java>
<>
<>
```

`Math.min(maxUnits, text.length())` fits because the function's name and contract clearly state **“at most”**. If the caller requested **exactly 10 characters** and the string was only 4 long, silently truncating to 4 could hide data errors. Do not swap `begin/end`, take the absolute value of negative indices, or arbitrarily clamp every range without business authorization.

## 7. Negative Cases Arising from Arithmetic and Search APIs

### 7.1. Taking the Last `n` Characters When `n` Exceeds Length

Familiar pattern:

```java
String tail = text.substring(text.length() - n);
```

This is only correct when `0 <= n <= text.length()`. If `text = "Java"` and `n = 5`, the start position is `4 - 5 = -1`, causing an exception. If `n = -1`, the start position is `5`, also exceeding the length. For `n = 0`, the valid result is `""`.

Strict checked version:

**`SuffixBoundsDemo.java`**

```java
import java.util.Objects;

public class SuffixBoundsDemo {
    private static String lastUnits(String text, int n) {
        Objects.requireNonNull(text, "text");
        if (n < 0 || n > text.length()) {
            throw new IllegalArgumentException("Invalid suffix length: " + n);
        }
        return text.substring(text.length() - n);
    }

    public static void main(String[] args) {
        System.out.println("<" + lastUnits("Java", 2) + ">");
        System.out.println("<" + lastUnits("Java", 4) + ">");
        System.out.println("<" + lastUnits("Java", 0) + ">");

        try {
            lastUnits("Java", 5);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected suffix longer than source");
        }
    }
}
```

```bash
javac SuffixBoundsDemo.java
java SuffixBoundsDemo
```

**Stdout:**

```text
<va>
<Java>
<>
Rejected suffix longer than source
```

The name `lastUnits` makes clear that `n` is a **count of UTF-16 code units**, not necessarily the number of user-visible characters; the Unicode section below highlights this limitation.

### 7.2. `indexOf()` Returns `-1` When Not Found

Many negative-boundary bugs stem from taking the result of `indexOf()` and passing it straight into `substring()`:

```java
String line = "name=value";
int separator = line.indexOf(':'); // -1 because there is no ':'
String head = line.substring(0, separator); // wrong: end = -1
```

This is an intentionally buggy illustrative snippet, not a complete program. `-1` is a **not-found sentinel**, not a valid index. Handle it first:

**`DelimiterDemo.java`**

```java
public class DelimiterDemo {
    private static void showAfterColon(String line) {
        int separator = line.indexOf(':');
        if (separator < 0) {
            System.out.println("No delimiter");
            return;
        }

        String value = line.substring(separator + 1);
        System.out.println("Value=<" + value + ">");
    }

    public static void main(String[] args) {
        showAfterColon("user:admin");
        showAfterColon("user:");
        showAfterColon("user=admin");
        showAfterColon(":start");
    }
}
```

```bash
javac DelimiterDemo.java
java DelimiterDemo
```

**Stdout:**

```text
Value=<admin>
Value=<>
No delimiter
Value=<start>
```

When the delimiter is at the very end, `separator + 1 == length()` is still a valid boundary, giving an empty string. When at the beginning, `substring(1)` is valid if the string has one or more code units. Only when not found should you return a different status or report an error according to application requirements.

## 8. Arithmetically Valid Bounds Are Not Necessarily Valid Unicode Bounds

Checking `0 <= begin <= end <= length` only protects UTF-16 ranges. For `"A😊B"`, `length() == 4` and `substring(1, 2)` is completely **index-valid**, yet it only captures the high surrogate of the emoji. To extract a full code point at UTF-16 position `1`, you can write:

```java
String text = "A😊B";
int end = text.offsetByCodePoints(1, 1);
String emoji = text.substring(1, end); // extracts the full emoji
```

When validating input, separate the question **“are the offsets within valid bounds?”** from **“do the offsets split a code point or grapheme cluster?”**. Code point APIs handle surrogate pairs; grapheme segmentation additionally handles combining marks and multi-code-point emojis.

## 9. How to Design and Test Boundary Cases

### 9.1. Define Policy Before Implementation

Before writing any extraction function, answer:

1. Are the parameters **UTF-16 offsets**, code point counts, or visible character cluster counts?
2. Is the end position **exclusive**, or is the caller supplying an **inclusive** last index?
3. If input is negative, exceeds length, or is reversed, will the function **throw an exception**, return a failure indicator, or clamp to the nearest boundary?
4. Are empty strings and `begin == end` ranges valid under the requirements?
5. If arithmetic bounds are valid but split a surrogate/grapheme, must the function reject or adjust the boundary?

The same `substring` can be used for either a strict API or an “up to N” API; the outer wrapper function decides the input policy. If text comes from users or external systems, avoid letting an untrusted index turn into an unhandled exception. If indices come from internal code that should always be correct, an exception can be a useful signal for catching programming bugs.

### 9.2. Quick Test Matrix

For `text = "Java"`, `n = 4`, essential test cases include:

| Case | Input | Expected Result |
|---|---|---|
| Entire string | `[0, 4)` | `"Java"` |
| Middle slice | `[1, 3)` | `"av"` |
| Empty range in middle | `[2, 2)` | `""` |
| Empty range at end | `[4, 4)` | `""` |
| Negative start index | `[-1, 2)` | Exception |
| Negative end index | `[0, -1)` | Exception |
| End exceeds length | `[0, 5)` | Exception |
| Both exceed length | `[5, 5)` | Exception |
| Reversed order | `[3, 2)` | Exception |
| Empty string | `""` and `[0, 0)` | `""` |
| Empty string, index 1 | `""` and `[0, 1)` | Exception |
| Non-BMP character | `"A😊B"`, `[1, 2)` | Valid range, but splits surrogate |

These tests verify **boundaries**, **empty cases**, **length**, and **Unicode correctness** separately. Do not treat `substring()` not throwing an exception as proof that the slice matches the product's meaning of “character”.

### 9.3. Common Traps When Fixing Bugs

- **Swapping parameters automatically** when `begin > end`: you cannot tell whether the caller made a typo or passed a reversed range intentionally; silent fixing can alter the meaning of the result.
- **Turning a negative index into 0** when the error came from `indexOf() == -1`: this can make the program extract the wrong data instead of recognizing that the delimiter is missing.
- **Clamping to `length`** in a function requiring an exact number of characters: missing data will be masked. Only clamp when the function's contract permits it.
- **Using `charAt(length)` because `substring(length)` is valid**: the two APIs have different index domains.
- **Forgetting exclusive end:** `substring(0, length - 1)` drops the last character; `substring(0, length + 1)` goes out of bounds.
- **Using `length()` as the count of “visible characters”**: strings with surrogate pairs or combining marks make that calculation diverge from what a reader perceives.

## 10. Self-Check

Predict the output or exception cases when `s = "ABCD"`:

```java
String s = "ABCD";

System.out.println("<" + s.substring(1, 1) + ">");
System.out.println("<" + s.substring(s.length()) + ">");
System.out.println("<" + s.substring(0, s.length()) + ">");

// Consider each line below separately:
// s.substring(-1, 2);
// s.substring(2, 5);
// s.substring(3, 2);
// s.substring(4, 4);
// s.charAt(4);
```

**Answers:**

- The three `println` statements print `<>`, `<>`, and `<ABCD>`, respectively.
- `substring(-1, 2)` is invalid because the start is negative.
- `substring(2, 5)` is invalid because `end = 5 > length = 4`.
- `substring(3, 2)` is invalid because `begin > end`.
- `substring(4, 4)` is valid and returns `""`.
- `charAt(4)` is invalid because the valid domain of `charAt` is only `0..3`.

**Quick rule of thumb:**

```text
substring(begin, end):
    0 <= begin <= end <= length

substring(begin):
    0 <= begin <= length

charAt(index):
    0 <= index < length
```

Remember one extra step: the inequalities above protect **UTF-16 ranges**; to extract a complete code point or visible character cluster, use the corresponding Unicode boundaries. When an application clearly distinguishes negative indices, out-of-length indices, reversed order, empty ranges, and Unicode limits, extraction operations become easy to test and unlikely to introduce silent data corruption.
