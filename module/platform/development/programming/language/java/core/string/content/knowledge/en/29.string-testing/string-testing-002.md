# Testing Start–End Indices and Extraction Ranges in Java String

## 1. Objective and Testing Problem

When extracting part of a text with `substring`, `subSequence`, `charAt`, or copying characters with `getChars`, being off by a single index unit can yield wrong content, drop characters, or throw an exception. Bugs often stay hidden on normal cases and surface on empty strings, indices equal to length, equal-endpoint ranges, or Unicode characters that span multiple UTF-16 code units.

This lesson walks through how to **define index ranges**, **build a boundary-covering test suite**, **assert both return values and exceptions**, and **test a custom extraction function**. The primary subject is `java.lang.String` on Java 17+, extending to `CharSequence` and related operations where appropriate.

After this lesson, you will be able to:

- Accurately interpret the `[beginIndex, endIndex)` convention.
- Distinguish valid ranges of `substring`, `charAt`, `codePointAt`, and `getChars`.
- Design test cases for **start, middle, end, empty, out-of-bounds, and reversed start–end**.
- Contrast lengths in **UTF-16 code units** versus Unicode code points.
- Write a standalone test program, extend it into JUnit unit tests, and reason about invariants for an extracted range.

## 2. Foundation: String Indices Are UTF-16 Indices

In Java, `String.length()` returns the **number of UTF-16 code units**. For ASCII text such as `"ABCDE"`, each character occupies one code unit:

```text
String:   A  B  C  D  E
Index:    0  1  2  3  4
Boundary: 0  1  2  3  4  5
                                 length() = 5
```

The element at index `i` is accessed via `charAt(i)`; the last accessible index is `length() - 1` when the string is non-empty. Meanwhile, a **cut boundary** can legitimately sit at position `length()` (immediately after the last character).

Do not conflate these two kinds of indices:
- **Element index:** must satisfy `0 <= i < length()`.
- **Range boundary index:** may satisfy `0 <= boundary <= length()`.

That is why `"ABCDE".charAt(5)` is invalid whereas `"ABCDE".substring(5, 5)` is valid and returns `""`.

**UTF-16 is not identical to user-perceived characters.** A code point outside the Basic Multilingual Plane, such as emoji `😀`, requires **two code units** (a surrogate pair). Both `length()` and the positions passed to `substring` are measured in code units, not code points or grapheme clusters.

## 3. Key API Contracts

### 3.1. substring(beginIndex, endIndex)

Signature:

```java
public String substring(int beginIndex, int endIndex);
```

The extracted range is **half-open**, written mathematically as `[beginIndex, endIndex)`: **inclusive of `beginIndex`, exclusive of `endIndex`**.

Validity condition:

```text
0 <= beginIndex <= endIndex <= s.length()
```

The result contains `endIndex - beginIndex` UTF-16 code units, starting at `beginIndex` and stopping before `endIndex`.

```java
String s = "ABCDE";

System.out.println(s.substring(1, 4)); // BCD
System.out.println(s.substring(0, 5)); // ABCDE
System.out.println(s.substring(3, 3).isEmpty()); // true
System.out.println(s.substring(5, 5).isEmpty()); // true
```

`substring(1, 4)` takes positions 1, 2, and 3; it **excludes** position 4. To include the last element at position 4, pass `endIndex = 5`.

An **empty** range such as `[3, 3)` is completely valid; the result is `""`. Equal endpoints are not an error.

### 3.2. substring(beginIndex)

Single-argument overload:

```java
public String substring(int beginIndex);
```

Takes from `beginIndex` to the end of the string:

```java
String s = "ABCDE";

System.out.println(s.substring(2));  // CDE
System.out.println(s.substring(5));  // Empty line because the result is ""
```

Validity condition: `0 <= beginIndex <= s.length()`. A value equal to `length()` is allowed and returns an empty string; values greater than `length()` or negative are invalid.

### 3.3. subSequence(start, end)

`String` implements `CharSequence` and supports:

```java
public CharSequence subSequence(int start, int end);
```

The range **`[start, end)`** matches `substring(start, end)`. When called on a `String` object, the resulting content equals what `substring` returns:

```java
String s = "ABCDE";
CharSequence part = s.subSequence(1, 4);
System.out.println(part); // BCD
```

However, the variable `part` has declared type `CharSequence`; methods on other `CharSequence` implementations do not necessarily share the same memory representation or lifecycle as `String`. Test against the **contract of the actual object in use**.

### 3.4. charAt(index)

`charAt` accesses a single UTF-16 code unit **at one position**, rather than extracting a range:

```java
String s = "ABCDE";
System.out.println(s.charAt(0)); // A
System.out.println(s.charAt(4)); // E
// s.charAt(5); // StringIndexOutOfBoundsException
```

The validity condition is `0 <= index < s.length()`. On an empty string, there is no valid index for `charAt`.

### 3.5. Exceptions for Invalid Indices

`substring` and related operations belong to the `IndexOutOfBoundsException` family when bounds are out of range. OpenJDK/HotSpot typically throws `StringIndexOutOfBoundsException` for many `String` errors, yet a **portable test** can assert the API contract's exception type (`IndexOutOfBoundsException`) instead of depending on message wording details.

Exception messages (for example, `begin 6, end 5, length 5`) can change across JDK versions. Do not match exact exception message text when you only need to verify that invalid bounds are rejected.

## 4. Standard Test Case Matrix for substring

Use `"ABCDE"` with `length() = 5` as the reference string:

| Case | Call | Expected |
| --- | --- | --- |
| Start of string | `substring(0, 1)` | `"A"` |
| Middle of string | `substring(1, 4)` | `"BCD"` |
| Last character | `substring(4, 5)` | `"E"` |
| Whole string | `substring(0, 5)` | `"ABCDE"` |
| Empty range at start | `substring(0, 0)` | `""` |
| Empty range in middle | `substring(3, 3)` | `""` |
| Empty range at end | `substring(5, 5)` | `""` |
| Suffix from middle | `substring(2)` | `"CDE"` |
| Empty suffix | `substring(5)` | `""` |
| Negative begin | `substring(-1, 2)` | Throws `IndexOutOfBoundsException` |
| Negative end | `substring(0, -1)` | Throws `IndexOutOfBoundsException` |
| Begin greater than end | `substring(4, 3)` | Throws `IndexOutOfBoundsException` |
| End greater than length | `substring(1, 6)` | Throws `IndexOutOfBoundsException` |
| Begin greater than length | `substring(6)` | Throws `IndexOutOfBoundsException` |

The matrix must include **two kinds of checks**: exact return values for valid ranges and exceptions for invalid ranges. Checking only “no error thrown” is insufficient to catch an off-by-one bug.

A practical pattern is to always pick values around boundaries `0` and `length()`: `-1`, `0`, `1`, `length()-1`, `length()`, `length()+1` (whenever meaningful). For an empty string, `length()-1 = -1` is an invalid index; that is precisely a case worth testing.

## 5. Empty Strings and Coincident-Endpoint Ranges

This is a common source of bugs when code manually adds or subtracts `1`:

```java
String empty = "";

System.out.println(empty.substring(0, 0).isEmpty()); // true
System.out.println(empty.substring(0).isEmpty());    // true

// empty.charAt(0);      // Invalid: no elements
// empty.substring(0, 1); // Invalid: end > length
```

For any string `s`, every range of the form `s.substring(i, i)` yields an empty string **provided** `0 <= i <= s.length()`. That means an empty range at the end of the string can be valid.

Distinguish an **empty range** from an **empty source value**:
- `"ABCDE".substring(2, 2)` is empty even though the source is not empty.
- `"".substring(0, 0)` is empty because both source and range are empty.
- `"".substring(1, 1)` is still invalid because boundary 1 lies beyond length 0.

A custom slicing function may allow empty ranges (often sensible), or forbid them per business rules. If forbidden, document clearly that this is a **domain-specific constraint**, rather than attributing it to `String.substring`.

## 6. Writing a Custom Extraction Function with Clear Validation

Suppose you want to write a `slice` function operating on `[begin, end)`:

```java
static String slice(String source, int begin, int end) {
    if (source == null) {
        throw new IllegalArgumentException("source must not be null");
    }

    int length = source.length();
    if (begin < 0 || end < begin || end > length) {
        throw new IndexOutOfBoundsException(
                "Invalid range [" + begin + ", " + end
                        + ") for length " + length);
    }

    return source.substring(begin, end);
}
```

This is an **illustrative method snippet** that must be placed inside a Java class before compiling. The function explicitly throws `IllegalArgumentException` when `source == null`. That decision belongs to `slice`'s design; calling `String.substring` itself on a null reference fails with `NullPointerException` before entering the method.

The check combines three errors accurately:
- `begin < 0`: negative start index.
- `end < begin`: reversed range; also covers some negative end values.
- `end > length`: end point past the string; also prevents begin exceeding length when `end >= begin`.

You can add an explicit `begin > length` check for a clearer message, though for validity the three clauses above suffice because of `begin <= end`.

Important note when **writing a helper that converts inclusive ranges to exclusive**: if an inclusive end equals `Integer.MAX_VALUE`, adding `1` can overflow the integer. Validate that end is within string bounds **before adding** or use an overflow-safe check.

## 7. Standalone Automated Java 17+ Test Program

The following example provides a small test suite with no JUnit dependency. It shows clearly how to assert return values, exceptions, and Unicode lengths.

Create `StringRangeTest.java`, saved as UTF-8:

```java
import java.util.Objects;

public class StringRangeTest {
    private static int passed = 0;

    private static void equal(Object expected, Object actual, String name) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    name + " expected=" + expected + ", actual=" + actual);
        }
        passed++;
    }

    private static void check(boolean condition, String name) {
        if (!condition) {
            throw new AssertionError(name);
        }
        passed++;
    }

    private static void throwsType(
            Class<? extends Throwable> type,
            Runnable action,
            String name) {
        try {
            action.run();
        } catch (Throwable error) {
            if (type.isInstance(error)) {
                passed++;
                return;
            }
            throw new AssertionError(name + " wrong exception", error);
        }
        throw new AssertionError(name + " did not throw");
    }

    public static void main(String[] args) {
        String s = "ABCDE";

        equal("BCD", s.substring(1, 4), "middle");
        equal("ABCDE", s.substring(0, 5), "whole");
        equal("", s.substring(3, 3), "empty middle");
        equal("", s.substring(5, 5), "empty end");
        equal("", "".substring(0, 0), "empty source");
        equal("CDE", s.substring(2), "one-argument suffix");
        equal("BCD", s.subSequence(1, 4).toString(), "subSequence");
        equal('E', s.charAt(4), "last char");

        throwsType(IndexOutOfBoundsException.class,
                () -> s.substring(-1, 2), "negative begin");
        throwsType(IndexOutOfBoundsException.class,
                () -> s.substring(1, 6), "end after length");
        throwsType(IndexOutOfBoundsException.class,
                () -> s.substring(4, 3), "reversed range");
        throwsType(IndexOutOfBoundsException.class,
                () -> s.substring(6), "one-argument invalid begin");
        throwsType(IndexOutOfBoundsException.class,
                () -> s.charAt(5), "charAt at length");

        String unicode = "A😀B";
        equal("😀", unicode.substring(1, 3), "full surrogate pair");
        equal(2, unicode.substring(1, 3).length(),
                "emoji code-unit length");
        equal(1, unicode.codePointCount(1, 3),
                "emoji code-point count");
        check(Character.isHighSurrogate(
                unicode.substring(1, 2).charAt(0)),
                "partial surrogate boundary");

        System.out.println("PASS: " + passed + " tests");
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 StringRangeTest.java
java StringRangeTest
```

Stdout if all checks pass:

```text
PASS: 17 tests
```

The program uses `Objects.equals` to check return values, `throwsType` to accept exceptions of the **right family**, and `check` for Unicode properties. You do not need the `-ea` flag, because the helpers explicitly throw `AssertionError` on failure.

A failing test throws `AssertionError` and halts the program, ensuring a “PASS” line never hides earlier failures. In real projects, use a unit testing framework (such as JUnit 5) to collect full reports and run automatically in CI.

## 8. Testing UTF-16 and Slicing Across a Surrogate Pair

Consider a string containing a non-BMP emoji:

```java
String text = "A😀B";
System.out.println(text.length()); // 4
```

UTF-16 positions are as follows:

```text
index 0 : 'A'
index 1 : high surrogate of 😀
index 2 : low surrogate of 😀
index 3 : 'B'
boundary: 0 | 1 | 2 | 3 | 4
```

Therefore:
- `text.substring(1, 3)` captures **both code units** and represents the complete emoji.
- `text.substring(1, 2)` captures **an isolated high surrogate**. The call is valid in terms of indices, but the result contains an unpaired surrogate.
- `text.substring(2, 3)` captures only the low surrogate, also producing an incomplete surrogate sequence.
- `text.substring(3, 4)` returns `"B"`.

**Java `String` allows unpaired surrogates.** `substring` only enforces the UTF-16 index contract; it does not verify that cut points align with code point boundaries or visible character boundaries.

If the requirement is “take the first two Unicode code points” rather than “take the first two code units,” convert indices by code points:

```java
String text = "A😀B";
int end = text.offsetByCodePoints(0, 2);
String firstTwoCodePoints = text.substring(0, end);

System.out.println(end); // 3
System.out.println(firstTwoCodePoints); // A😀
```

`offsetByCodePoints(beginIndex, codePointOffset)` translates a code point count into a UTF-16 index. This is still **not equivalent to splitting grapheme clusters**: a base character plus combining marks, ZWJ emoji sequences, or flag emojis can span multiple code points yet render as a single cluster. When requirements are in terms of *user-perceived characters*, use text segmentation suited to Unicode, locale, and actual product needs.

## 9. getChars: Checking Both Source Range and Destination Position

In addition to `substring`, `String.getChars(srcBegin, srcEnd, dst, dstBegin)` copies the **range `[srcBegin, srcEnd)`** into a destination array:

```java
String s = "ABCDE";
char[] dst = {'_', '_', '_', '_', '_'};

s.getChars(1, 4, dst, 1);

System.out.println(String.valueOf(dst)); // _BCD_
```

The source range `[1,4)` has length **3**; it is copied into `dst[1]`, `dst[2]`, and `dst[3]`. Testing `getChars` must examine **both index systems**:

- Source: `0 <= srcBegin <= srcEnd <= s.length()`.
- Destination: `dstBegin >= 0` and `dstBegin + (srcEnd - srcBegin) <= dst.length`, performing addition safely without integer overflow if you write your own check.
- The `dst` array must exist; if null, accessing the array can cause `NullPointerException`.

To avoid overflow in custom validation logic, after confirming `0 <= dstBegin <= dst.length`, you can check `copyCount <= dst.length - dstBegin`.

Worthwhile test cases:
1. Copy into the middle of an array and verify positions outside the written region remain unchanged.
2. Copy an empty range with `srcBegin == srcEnd`.
3. `srcEnd > s.length()` or `srcBegin < 0`.
4. `dstBegin < 0` or destination lacks sufficient capacity.
5. Behavior with surrogate pairs, since `getChars` also copies by UTF-16 code unit.

Key difference: `substring` creates a `String` result, whereas `getChars` **mutates the destination array** across the selected span. Therefore, verify both the accuracy of the copied slice and the integrity of array elements outside that span.

## 10. indexOf-Based Extraction: Don't Introduce +1/-1 Bugs Yourself

Real-world code often locates boundaries dynamically:

```java
String input = "user=alice;role=admin";
int begin = input.indexOf('=') + 1;
int end = input.indexOf(';');
String user = input.substring(begin, end);

System.out.println(user); // alice
```

This example works for this specific format, but it is **unsafe for arbitrary inputs**. If `=` is missing, `indexOf('=')` returns `-1` and adding 1 yields `0`; a missing-delimiter bug can be masked. If `;` is missing, `end = -1` and `substring` throws an exception.

Validate before extracting:

```java
static String extractBeforeSemicolon(String input) {
    if (input == null) {
        throw new IllegalArgumentException("input is null");
    }

    int equal = input.indexOf('=');
    if (equal < 0) {
        throw new IllegalArgumentException("Missing '='");
    }

    int begin = equal + 1;
    int end = input.indexOf(';', begin);
    if (end < 0) {
        throw new IllegalArgumentException("Missing ';'");
    }

    return input.substring(begin, end);
}
```

This is an illustrative method that needs to sit inside a Java class. Under this rule, `"user=;role=admin"` validly yields an empty string because `begin == end`; if business rules forbid empty values, add a dedicated check.

Cases to test:
- Delimiters in normal positions.
- `=` immediately followed by `;` (empty value).
- Missing `=`, missing `;`.
- `;` appearing before `=`: thanks to `indexOf(';', begin)`, the method searches for the closing delimiter **after** `=`.
- Empty or `null` input.
- Multiple `=` or `;` characters: explicitly define the business rule for picking the first/valid delimiter.

Do not write tests only for a “pretty” string; what needs verification are the **assumptions about delimiter positions** before passing indices to `substring`.

## 11. Unit Testing with JUnit 5

In a project with **JUnit Jupiter** on the test classpath, you can use `assertEquals`, `assertThrows`, and `assertAll`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class StringBoundsTest {
    @Test
    void extractsHalfOpenRange() {
        String s = "ABCDE";

        assertEquals("BCD", s.substring(1, 4));
        assertEquals("", s.substring(5, 5));
        assertEquals("E", s.substring(4, 5));
    }

    @Test
    void rejectsInvalidBounds() {
        String s = "ABCDE";

        assertThrows(IndexOutOfBoundsException.class,
                () -> s.substring(-1, 2));
        assertThrows(IndexOutOfBoundsException.class,
                () -> s.substring(4, 3));
        assertThrows(IndexOutOfBoundsException.class,
                () -> s.substring(0, 6));
    }

    @Test
    void countsUtf16UnitsNotCodePoints() {
        String s = "A😀B";

        assertEquals(4, s.length());
        assertEquals("😀", s.substring(1, 3));
        assertEquals(2, s.substring(1, 3).length());
    }
}
```

This is a **test class for a project already configured with JUnit 5**, not a standalone program you compile with plain `javac` alone. JUnit must be in dependencies/classpath and tests run via Maven, Gradle, or your IDE per project setup. A standalone Java example with no dependencies is already provided in section 7.

Parameterized tests with `@ParameterizedTest` and `@CsvSource` fit well when the same rule applies to many begin/end pairs. However, keep **valid cases** and **exception-throwing cases** separate so failure messages remain clear.

## 12. Property-Based Thinking

Beyond isolated examples, verify the following **invariants** for any `String s` and any valid `begin, end` pair:

1. **Length:** `s.substring(begin, end).length() == end - begin`.
2. **Position-matching elements:** for every `i` in `[0, end - begin)`, `slice.charAt(i) == s.charAt(begin + i)`.
3. **Empty range:** `s.substring(i, i).isEmpty()` for every `0 <= i <= s.length()`.
4. **Reassembly preserves content:** `s.substring(0, begin) + s.substring(begin, end) + s.substring(end)` equals `s` in content.
5. **Full range:** `s.substring(0, s.length()).equals(s)`.
6. **Source preservation:** calling `substring` does not mutate `s` because `String` is immutable.

These properties also hold for strings with surrogate pairs when measuring and choosing boundaries by **UTF-16 code unit**. They do not guarantee that every slice has complete surrogate pairs, as that is an additional Unicode-level requirement.

You can generate **randomized tests** with a generator producing a `String` and two valid indices, e.g., picking `begin` in `[0, length]` and then `end` in `[begin, length]`. For invalid cases, generate out-of-range pairs. When using randomness, log or fix the seed on failure so it is reproducible.

To avoid tests that “verify the function using the function itself,” most properties should be checked independently using `length()`, `charAt()`, and a simple oracle model, or compared against the original data rules. There is no need to use randomness for a tiny function when a boundary matrix suffices; it is a helpful supplemental technique for custom text splitters.

## 13. Business Inclusive Indices vs. Java Exclusive APIs

Some business specifications say “take from position 2 **through** position 4.” When both endpoints are inclusive, convert to Java `substring(2, 5)`, not `substring(2, 4)`.

Example:

```java
String s = "ABCDEFG";
int firstInclusive = 2;
int lastInclusive = 4;

String result = s.substring(firstInclusive, lastInclusive + 1);
// CDE
```

Adding 1 is only safe after verifying `lastInclusive` is a valid character position, i.e. `0 <= lastInclusive < s.length()`. Testing the conversion logic must include:
- `firstInclusive == lastInclusive` (extracts exactly one character).
- `lastInclusive == s.length() - 1` (extracts through the last character).
- `firstInclusive > lastInclusive` (invalid range).
- `lastInclusive < 0` or `lastInclusive >= s.length()` (out of bounds).
- Empty string: **no element** exists to apply a non-empty inclusive range of at least one character.

A similar source of error is **1-based counting** in documents or UIs, while Java uses 0-based indexing. If a user selects “3rd to 5th character” using 1-based inclusive counting, the corresponding Java range is `substring(2, 5)`. Conversion rules must be clearly documented in both the API and tests.

## 14. Distinguishing Source/Array Ranges and Offset/Count

Not all Java APIs use a `begin, end` pair. Some APIs use **offset and count**: a starting position and a **number of elements**. For example:

```java
char[] chars = {'A', 'B', 'C', 'D', 'E'};

String a = String.valueOf(chars, 1, 3); // "BCD"
String b = new String(chars, 1, 3);      // "BCD"
```

In both calls above, the third argument is `count = 3`, **not `endIndex = 3`**. Confusing the two conventions can let a test pass by coincidence when `offset = 0`, only to break immediately when `offset > 0`.

| API | Index Parameters | Meaning |
| --- | --- | --- |
| `s.substring(begin, end)` | `begin, end` | Selects `[begin, end)` |
| `s.subSequence(start, end)` | `start, end` | Selects `[start, end)` |
| `s.getChars(srcBegin, srcEnd, dst, dstBegin)` | `srcBegin, srcEnd` | Selects `[srcBegin, srcEnd)` of source |
| `String.valueOf(chars, offset, count)` | `offset, count` | Selects `count` characters from `offset` |
| `new String(chars, offset, count)` | `offset, count` | Selects `count` characters from `offset` |
| `s.charAt(index)` | `index` | Selects one UTF-16 code unit at `index` |

When designing tests, first identify **what the second index/size parameter means**; do not apply `end - begin` logic to `count` or vice versa.

## 15. Common Mistakes in Index Testing

**1. Assuming `endIndex` is inclusive.** This drops the last element or causes wrong `end + 1` adjustments. For `substring`, the end point is always **exclusive**.

**2. Thinking `substring(length, length)` is an error.** It is a valid empty range. However, `charAt(length)` is still an error.

**3. Ignoring empty sources.** On `""`, only `substring(0, 0)` or `substring(0)` are valid ways to obtain an empty range within this scope.

**4. Testing only populated cases.** Off-by-one `+1/-1` errors usually appear at boundaries, single-character spans, or empty ranges.

**5. Comparing exception messages verbatim.** Message formatting can differ across JDKs; prefer asserting the exception type per contract and the failing condition.

**6. Treating `length()` as visible character count.** It is the UTF-16 code unit count. Splitting between two surrogates is index-valid yet can corrupt displayed data.

**7. Not checking for `indexOf` returning `-1`.** Adding 1 too early turns `-1` into `0`, making missing-delimiter bugs harder to notice.

**8. Ignoring null.** `source.substring(...)` on a null reference throws `NullPointerException` before any range check. A wrapper function can explicitly define its own exception or default value.

**9. Confusing offset/count with begin/end.** Passing `String.valueOf(chars, 2, 5)` thinking it stops at index 5 actually asks for **5** elements starting at 2, which can go out of bounds.

**10. Catching exceptions too broadly.** Catching any `Exception` can mask an unrelated failure. When testing specific behavior, assert the appropriate exception family and do not overlook mismatches.

## 16. Pre-Completion Testing Checklist

For each string-slicing function, confirm these questions:

- Does the range use **`[begin, end)`**, **inclusive/inclusive**, or **offset/count**?
- Is `length()` interpreted as UTF-16 code units, or does the program truly require code points/graphemes?
- Have **`0`**, **`length()`**, and **`length()-1`** been checked at the right positions?
- Are there tests for an empty string, empty ranges at start/middle/end, first/last character, and the full string?
- Have negative begin, out-of-bounds end, begin greater than end, and null input (if accepted by the API) been tested?
- If boundaries are computed from delimiters, have `indexOf == -1` and duplicate/overlapping delimiters been tested?
- If a destination array is mutated, have **elements outside the written region been verified untouched**?
- If Unicode correctness matters, have surrogate pairs been tested and the “character” unit defined?
- For invalid ranges, do tests check the **appropriate error type**, and for valid ranges, do tests compare **exact content** rather than just “no error”?

## 17. Takeaway

- Java's `String.substring(begin, end)`, `subSequence(start, end)`, and `getChars(srcBegin, srcEnd, ...)` use the **half-open range `[begin, end)`**.
- **Valid range:** `0 <= begin <= end <= length()`. **Valid character index:** `0 <= index < length()`.
- `end == length()` and `begin == end` are **valid** cases for `substring`; the returned value may be empty.
- Tests must cover **correct results** and **expected exceptions** at both ends of the range.
- `String` indices are based on **UTF-16 code units**; an emoji can be 2 code units long and can be split mid-surrogate.
- APIs using `offset, count` must be tested differently from APIs using `begin, end`.
- When computing bounds from `indexOf`, always handle `-1` before slicing.
- For custom extraction functions, use invariants such as length `end - begin`, content preservation, and exception checks to prevent off-by-one bugs.

Official references: [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [Java SE 17 — CharSequence](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/CharSequence.html), [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html), [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/).
