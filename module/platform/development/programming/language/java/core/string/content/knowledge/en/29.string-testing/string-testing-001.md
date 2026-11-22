# String Testing Matrix: Null, Empty, Blank, Single-Character, and Long Strings

## 1. Objective: Testing Error-Prone Input Classes

With Java `String`, testing only a few “normal” strings is not enough. A method taking a string might work well with `"hello"` yet produce wrong results or throw an exception when receiving `null`, `""`, `" "`, a single character, a non-BMP Unicode character, or a very long string. This lesson shows how to build an **equivalence-class and boundary-value test matrix**, interpret Java API results accurately, and pick valuable test cases instead of testing randomly.

Core input classes:

1. **`null`:** there is no `String` object on which to call methods.
2. **Empty `""`:** a `String` object exists, but `length() == 0`.
3. **Whitespace-only:** has at least one character, which may include spaces, tabs, LF, or other Unicode characters; whether it is “blank” depends on API rules.
4. **Single-character:** the smallest boundary of a non-empty string; one must distinguish a single UTF-16 `char` from a single Unicode code point.
5. **Long strings:** test correctness, performance, allocation, and length assumptions, without using oversized data that exhausts memory in routine tests.

Classification must be based on the **input contract of the function under test**. One program may treat `null` as an error, while another allows `null` as an “unprovided” value. There is no universal rule forcing every application to convert `null` into `""`.

## 2. Standard Input Matrix

| Case | Java Example | `length()` | `isEmpty()` | `isBlank()` | Meaning |
| --- | --- | ---: | --- | --- | --- |
| No string | `null` | Cannot call | Cannot call | Cannot call | Must check for `null` first |
| Empty string | `""` | 0 | `true` | `true` | Object exists, but has no characters |
| Single space | `" "` | 1 | `false` | `true` | Blank string, but not empty |
| Tab and LF | `"\t\n"` | 2 | `false` | `true` | Two whitespace characters |
| Single ASCII letter | `"Z"` | 1 | `false` | `false` | One UTF-16 code unit and one code point |
| Single emoji `😀` | `"\uD83D\uDE00"` | 2 | `false` | `false` | Two UTF-16 code units, but one code point |
| EM SPACE | `"\u2003"` | 1 | `false` | `true` | Unicode whitespace recognized by `Character.isWhitespace` |
| NBSP | `"\u00A0"` | 1 | `false` | `false` | Non-breaking space is not considered blank by `isBlank()` |
| Long string | `"a".repeat(100_000)` | 100000 | `false` | `false` | Tests length, operations, and resources |

The table above applies to **Java 17+** and Java's `String.isBlank()` rules. Cells marked “Cannot call” mean that calling `s.length()`, `s.isEmpty()`, or `s.isBlank()` directly when `s == null` throws `NullPointerException`; `null` is not a zero-length variant of `String`.

**Do not conflate** `null`, `""`, and `" "`: they have different meanings even when a UI sometimes renders all three as if there were no text.

## 3. Safe Classification When Values Can Be `null`

Check for `null` before calling any instance method:

```java
static String state(String s) {
    if (s == null) return "NULL";
    if (s.isEmpty()) return "EMPTY";
    if (s.isBlank()) return "BLANK";
    return "TEXT";
}
```

This is a **method snippet** that can be placed inside a Java class. Condition order matters greatly:

- If `s == null`, return state `NULL` and do not call any method on the object.
- If `s.isEmpty()` is `true`, return `EMPTY`.
- If the length is positive yet `s.isBlank()` is `true`, return `BLANK`.
- All remaining values are `TEXT`. The `TEXT` state here only means “not blank according to `String.isBlank()` rules,” not necessarily valid business text.

For example, an order code `"   "` might be rejected by input policy; a password containing only spaces might be valid or invalid depending on the product. Do not automatically call `strip()` before classifying if business logic treats whitespace as data to preserve.

### Distinguishing Ways to Compare

- `s == null` checks whether a reference is `null`.
- `"".equals(s)` is a null-safe way to check for an empty string when `s` might be `null`.
- `Objects.equals(a, b)` compares content safely when either side may be `null`.
- `a.equals(b)` can cause `NullPointerException` if `a == null`.
- `a == b` on two `String` references checks for the **same object**, not equal content; do not use it to assert string-processing results.

If the specification allows `null` and `""` to mean the same thing, state that clearly in the API and normalize intentionally. Do not blindly use `Objects.toString(value, "")` everywhere, as doing so erases the distinction between the two states.

## 4. Choosing the Right Whitespace Rule Before Testing

`isEmpty()` only checks `length() == 0`; `isBlank()` accepts an empty string or one whose code points all satisfy `Character.isWhitespace`. `trim()` removes character codes from `U+0000` through `U+0020` at both ends, whereas `strip()` removes Unicode whitespace at both ends according to `Character.isWhitespace`. Therefore `"\u2003"` (EM SPACE) is blank and is removed by `strip()`, but not by `trim()`; `"\u00A0"` (NBSP) is not treated as blank by `isBlank()` and is not removed by `strip()`.

~~~java
String emWrapped = "\u2003Z\u2003";
System.out.println(emWrapped.trim().equals("Z"));  // false
System.out.println(emWrapped.strip().equals("Z")); // true
System.out.println("\u00A0".isBlank());            // false
~~~

In the input matrix, test at least SPACE, TAB, LF, EM SPACE, and NBSP against the **published business rules**; do not assume all whitespace-looking characters behave identically. When you need to distinguish `lines()` from regex `\R` or handle different line-ending styles, use dedicated cases for CR/LF/CRLF and Unicode line separators.

## 5. Single Character and UTF-16 Boundaries

For a single-code-unit string `"Z"`, `charAt(0)` is valid, `charAt(1)` throws `StringIndexOutOfBoundsException`, and `substring(1)` is valid and returns `""`. For the empty string `""`, `charAt(0)` is invalid while `substring(0, 0)` returns empty. Test the **last element**, the **boundary immediately after the last element**, and an **empty range**.

~~~java
String single = "Z";
System.out.println(single.substring(1).isEmpty()); // true
String emoji = "\uD83D\uDE00";
System.out.println(emoji.length()); // 2 UTF-16 code units
System.out.println(emoji.codePointCount(0, emoji.length())); // 1
~~~

A non-BMP code point can take two UTF-16 code units, while a letter with a combining mark can consist of multiple code points. Choose a clear unit of measurement (code units, code points, graphemes, or bytes) before writing length limits or slicing operations; `length()` alone is insufficient for all display requirements.

## 6. Long Strings: Testing Correctness, Memory, and Time

A long-string case can look like:

```java
String longText = "a".repeat(100_000);

boolean correctLength = longText.length() == 100_000;
boolean prefix = longText.startsWith("aaa");
boolean suffix = longText.endsWith("aaa");
```

Here, `100_000` is a **controlled test size**, not the maximum limit of `String` or a general JVM limit. Actual limits also depend on string representation, runtime, memory, object/array limits, and the operation being performed. An extremely large string can trigger `OutOfMemoryError` or make tests take far too long. You should not allocate gigabyte-sized strings in daily test suites just to claim “we test long strings.”

Useful questions when testing long strings:

1. Does the function return the **exact expected result** for larger-than-normal input, or does it truncate or drop trailing characters?
2. Is there a published business limit (for example, maximum character count), and what happens when that limit is exceeded?
3. Are there index bugs, intermediate length calculation overflows, or head/tail handling errors?
4. Does an algorithm repeatedly use `+=` or `substring`/`replace` in a way that causes excessive copying and high cost?
5. Does it accidentally write entire sensitive or huge strings into logs, error responses, or caches?

For a business limit `maxLength`, include cases for **`maxLength - 1`, `maxLength`, and `maxLength + 1`** where appropriate, plus empty, single-character, and Unicode code-point/grapheme counts when those are the limiting units. Do not infer limits in bytes if the contract states “characters”: UTF-8 may require multiple bytes for the same number of code points.

For multi-part concatenation operations, consider `StringBuilder`, `String.join`, or a stream collector if appropriate for the problem. Measure performance with a proper benchmark (such as JMH) when performance is genuinely a criterion; a single `System.nanoTime()` measurement is easily skewed by JIT, GC, and runtime optimizations. Functional tests do not need to prove absolute wall-clock timings across every machine.

## 7. Standalone Java 17+ Test Program

Create `StringBoundaryMatrix.java`:

```java
import java.util.Objects;

public class StringBoundaryMatrix {
    static String state(String s) {
        if (s == null) return "NULL";
        if (s.isEmpty()) return "EMPTY";
        if (s.isBlank()) return "BLANK";
        return "TEXT";
    }

    static void require(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        String[] names = {
            "null", "empty", "space", "tabsLF", "oneASCII",
            "emoji", "emSpace", "nbsp", "long"
        };
        String[] values = {
            null, "", " ", "\t\n", "Z",
            "\uD83D\uDE00", "\u2003", "\u00A0", "a".repeat(100_000)
        };

        System.out.printf("%-10s | %-5s | %6s | %8s%n",
                "Case", "State", "length", "codePts");
        for (int i = 0; i < values.length; i++) {
            String value = values[i];
            String length = value == null ? "-" : "" + value.length();
            String codePoints = value == null ? "-"
                    : "" + value.codePointCount(0, value.length());
            System.out.printf("%-10s | %-5s | %6s | %8s%n",
                    names[i], state(value), length, codePoints);
        }

        require(!Objects.equals(null, ""), "null != empty");
        require("".isEmpty() && "".isBlank(), "empty is blank");
        require(!" ".isEmpty() && " ".isBlank(), "space is blank");
        require("\t\n".isBlank(), "tab and LF are blank");
        require(!"\u00A0".isBlank(), "NBSP is not isBlank whitespace");
        require("\u2003".isBlank(), "EM SPACE is blank");
        require("\u2003Z\u2003".strip().equals("Z"), "strip Unicode");
        require(!"\u2003Z\u2003".trim().equals("Z"), "trim differs");
        require("Z".charAt(0) == 'Z', "one ASCII char");
        require("\uD83D\uDE00".length() == 2, "emoji uses UTF-16 pair");
        require("\uD83D\uDE00".codePointCount(0, 2) == 1, "one code point");
        require(values[8].length() == 100_000, "long length");
        require(values[8].startsWith("aaa"), "long prefix");
        require(values[8].endsWith("aaa"), "long suffix");
        System.out.println("Checks: PASS");
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 StringBoundaryMatrix.java
java StringBoundaryMatrix
```

Verified stdout:

```text
Case       | State | length |  codePts
null       | NULL  |      - |        -
empty      | EMPTY |      0 |        0
space      | BLANK |      1 |        1
tabsLF     | BLANK |      2 |        2
oneASCII   | TEXT  |      1 |        1
emoji      | TEXT  |      2 |        1
emSpace    | BLANK |      1 |        1
nbsp       | TEXT  |      1 |        1
long       | TEXT  | 100000 |   100000
Checks: PASS
```

The `-` marks in the `length` and `codePts` columns for the `null` case mean **not applicable**, not negative numbers or zero length. The program does not print all 100,000 characters: it only prints metrics, avoiding console clutter and slow tests. `require` explicitly throws `AssertionError` if any condition fails; there is no need to enable the JVM `-ea` option as with the standard `assert` keyword.

Explanation of notable results:

- `empty`: both `isEmpty()` and `isBlank()` are true; classification prioritizes `EMPTY` so zero-length information is not lost.
- `space` and `tabsLF`: contain actual characters and are classified as `BLANK`.
- `emoji`: UTF-16 length is 2, yet it has only 1 code point.
- `emSpace` is blank and `nbsp` is not blank, matching `Character.isWhitespace`.
- `long` is 100000 code units and code points because it only repeats the ASCII letter `a`; non-BMP Unicode data does not necessarily have equal values for both counts.

## 8. Turning the Matrix into a Bug-Catching Test Suite

A good test table should link each case to a **specific risk**:

| Input | Commonly Exposed Bug | What to Verify |
| --- | --- | --- |
| `null` | Unintended `NullPointerException` | Whether the contract allows, rejects, or normalizes `null` |
| `""` | Out-of-bounds `charAt(0)` / `substring` | Empty branch, default result, and error message |
| `" "` / `"\t\n"` | Confusing blank with empty | Classification, validation, intentional normalization |
| Unicode whitespace | Handling ASCII only or assuming `trim` equals `strip` | `Character.isWhitespace` rules, NBSP, EM SPACE |
| Single char `"Z"` | Assuming the string has at least two characters | Index 0, index 1, head/tail slicing |
| Emoji or combining marks | Equating UTF-16 units with visible characters | `codePointCount`, code point boundaries, graphemes if needed |
| Long string | Truncation, repeated copying, wrong limit unit | Head/tail, length, resources, and published limits |

The same input can test multiple methods, but **expectations must be specific**: “does not throw an exception” does not prove the function returns the right result. For parsers, also check field contents; for validators, verify error codes; for formatters, check exact whitespace and Unicode characters; for web APIs, test both missing fields and fields containing an empty string in the payload.

### Testing Key Boundary Pairs

- **Present / absent:** `null` versus `""`.
- **Empty / blank:** `""` versus `" "`.
- **One / two characters:** `"Z"` versus `"ZZ"` to catch indexing and slicing bugs.
- **ASCII / Unicode:** `"Z"` versus `"😀"` or characters with combining marks.
- **Common whitespace / Unicode whitespace:** `" "`, `"\t"`, `"\u2003"`, `"\u00A0"`.
- **At limit / over limit:** `n-1`, `n`, `n+1` in the unit published by the contract.

When a bug is found, keep the smallest **regression test** case that reproduces it. There is no need to generate thousands of identical long variants if they do not explore an independent risk.

## 9. Designing String-Accepting Functions for Testability

Before writing tests, define the policies:

1. Is `null` allowed? If not, what exception type does the function throw, and at which boundary? Is `Objects.requireNonNull` used?
2. Is `""` valid or treated as “left empty”? Is there any default value?
3. Is leading/trailing whitespace meaningful? Should it be stripped or preserved?
4. Does “length” count UTF-16 code units, Unicode code points, graphemes, or encoded bytes?
5. Is there an input limit, such as `maxLength`? If exceeded, what error is returned and how are oversized allocations avoided?
6. Must the result be locale/charset-independent? Case comparisons and encoding/decoding need explicit rules.

For example, a policy stating “display name must not be whitespace-only, maximum 100 code points” can check `null`, blank, `strip()`, and `codePointCount` in order; however, if business rules specify a limit of 100 **UTF-8 bytes**, the check must instead count encoded bytes. One policy cannot be substituted for another merely because both use the word “length.”

When handling sensitive data, avoid printing the full input on test failure; logging the case label and length is sufficient in many situations. For long data, set a reasonable cap so the test suite runs reliably in CI.

## 10. Common Mistakes When Building a String Matrix

1. **Calling `null.isEmpty()` or `null.isBlank()`:** `null` is not a String object; check for null first.
2. **Treating `""` and `" "` as the same:** the first has length 0, the second has length 1.
3. **Assuming `isBlank()` recognizes everything that looks like space:** NBSP is a counterexample.
4. **Using `trim()` and `strip()` interchangeably:** they use different character sets.
5. **Using `length()` to count emoji or user-perceived characters:** `length()` counts UTF-16 code units; `codePointCount` is also not a general grapheme counter.
6. **Accessing `charAt(0)` before checking for an empty string:** causes `StringIndexOutOfBoundsException`.
7. **Using `==` to compare `String` content:** compares references, not content equality.
8. **Testing only one long string and claiming good performance:** must measure under controlled conditions, with resource limits and a representative workload.
9. **Testing character count only, forgetting byte count:** when I/O or protocols limit bytes, check encoded length with the right charset.
10. **Treating “no exception thrown” as a passing test:** still must assert output, side effects, ordering, and input-handling policies.

## 11. Checklist When Adding Tests for a String-Processing Function

- Define the contract for `null`, empty, blank, and leading/trailing whitespace.
- Add single-character, two-character, and non-BMP Unicode cases if logic involves indices or length.
- Explicitly state whether “length” means UTF-16, code points, graphemes, or bytes; test with the right unit.
- Add reasonably long strings and values right around published limits.
- Assert **expected results**, not merely “it runs”; keep tests deterministic and repeatable.
- When a bug is discovered, add the smallest regression test to prevent recurrence.

**Takeaway:** the **`null` → empty → blank → single-character → long** matrix is a starting framework for `String` testing, not a fixed suite for every business rule. Its value lies in clearly distinguishing states and verifying the boundaries where Java code most easily goes wrong.