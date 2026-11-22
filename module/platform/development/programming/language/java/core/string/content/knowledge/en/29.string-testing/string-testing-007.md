# Testing Split Keeping Empty Elements and splitWithDelimiters in Java

## 1. Problem and Testing Objective

In Java, `String.split(regex)` and `String.split(regex, limit)` use a **regular expression** to split a string. The result is a `String[]` containing the text segments between regex matches. A common source of bugs is assuming the result always preserves every empty field or every delimiter.

For example, simple CSV-like data:

```text
name,age,city,
```

The trailing comma may represent an **empty** final field. If you write:

```java
String[] fields = "name,age,city,".split(",");
```

then by default `split` **drops trailing empty elements**, leaving only `["name", "age", "city"]`. To assert the exact field count, you must choose an appropriate `limit`.

Starting in **Java 21**, Java also provides `String.splitWithDelimiters(regex, limit)` and `Pattern.splitWithDelimiters(input, limit)` to keep **the delimiter matches themselves** interleaved between fields. This is a different API from `split`: useful when parsing, testing, or reconstructing delimited data. **Java 17 does not have `splitWithDelimiters`**; examples using this API require JDK 21 or later.

After this lesson, you will know how to test: **leading, middle, and trailing** empty parts; zero, negative, and positive `limit` values; repeated delimiters; regex metacharacters; zero-length delimiter matches; and the difference between `split` and `splitWithDelimiters`.

## 2. Mechanics of split(regex, limit)

Two overloads on `String`:

```java
String[] split(String regex)
String[] split(String regex, int limit)
```

`split(regex)` is equivalent to `split(regex, 0)`. The `limit` value controls **how many times the delimiter is applied and whether trailing empty strings are kept**.

| `limit` | Number of splits | Trailing empty elements |
| --- | --- | --- |
| `0` (default) | Applies the regex as many times as possible | **Discards** consecutive trailing `""` elements |
| Negative, e.g. `-1` | Applies the regex as many times as possible | **Keeps** trailing `""` elements |
| Positive `n` | Applies the regex at most `n - 1` times, at most `n` elements | Keeps the remaining tail, including `""` if present |

The `limit` argument is **not** a character count and **not** the number of delimiters in the string. `limit = 2` means splitting at most at **one** delimiter match; the remainder becomes the final element.

```java
String text = "a,b,,";

System.out.println(java.util.Arrays.toString(text.split(",")));      // [a, b]
System.out.println(java.util.Arrays.toString(text.split(",", -1)));  // [a, b, , ]
System.out.println(java.util.Arrays.toString(text.split(",", 2)));   // [a, b,,]
```

`Arrays.toString` does not put quotes around each value, so empty strings are easy to misread. When writing tests, use `Arrays.equals` with an expected array or a helper that prints quotes as shown in the full program section.

### Distinguishing Three Kinds of Empty Fields

- **Leading:** `",a"` has a positive-length delimiter match right at index 0 → the leading empty field `""` **is kept**, even with `limit = 0`.
- **Middle:** `"a,,b"` has two adjacent commas → the empty field `""` between the two delimiters **is kept**.
- **Trailing:** `"a,b,"` has a trailing comma → `limit = 0` drops the trailing empty element; `limit = -1` keeps it.

Concrete example table:

| Input | Call | Exact Result |
| --- | --- | --- |
| `"a,b,,"` | `split(",")` | `["a", "b"]` |
| `"a,b,,"` | `split(",", 0)` | `["a", "b"]` |
| `"a,b,,"` | `split(",", -1)` | `["a", "b", "", ""]` |
| `"a,b,,"` | `split(",", 2)` | `["a", "b,,"]` |
| `",a,"` | `split(",")` | `["", "a"]` |
| `",a,"` | `split(",", -1)` | `["", "a", ""]` |
| `"a,,b,"` | `split(",", -1)` | `["a", "", "b", ""]` |
| `""` | `split(",", -1)` | `[""]` |

**Watch out for an empty string:** When the input is completely empty and a regex like `","` does not match, the result contains **a single empty-string element** `[""]`, not a zero-length array. Therefore assert both array length and element contents in these tests.

## 3. How Does splitWithDelimiters Work?

Starting in Java 21:

```java
String[] splitWithDelimiters(String regex, int limit)
```

This method also uses a regex as a separator, yet instead of discarding delimiters like `split`, it returns both **text segments and regex-matched delimiters**, in order of appearance.

Example:

```java
String input = "boo:::and::foo";
String[] parts = input.splitWithDelimiters(":+", -1);

// ["boo", ":::", "and", "::", "foo"]
```

`":+"` is a regex matching **one or more** consecutive colons, so `":::"` and `"::"` are preserved as two intact delimiters. They are not broken up into individual `":"` characters.

The result typically has the structure:

```text
[text segment, delimiter, text segment, delimiter, text segment]
```

A trailing delimiter is preserved if present, and `limit = -1` also preserves any trailing empty text segment. For example:

```java
String[] parts = "a,,b,".splitWithDelimiters(",", -1);

// ["a", ",", "", ",", "b", ",", ""]
```

The result accurately reflects both consecutive commas and the trailing comma.

### Comparison Table: split vs. splitWithDelimiters

For `"a,,b,"` and regex `","`:

| Method | `limit` | Result |
| --- | --- | --- |
| `split` | `0` | `["a", "", "b"]` |
| `split` | `-1` | `["a", "", "b", ""]` |
| `splitWithDelimiters` | `0` | `["a", ",", "", ",", "b", ","]` |
| `splitWithDelimiters` | `-1` | `["a", ",", "", ",", "b", ",", ""]` |
| `splitWithDelimiters` | `2` | `["a", ",", ",b,"]` |
| `splitWithDelimiters` | `1` | `["a,,b,"]` |

With `limit = 0`, `splitWithDelimiters` **discards trailing empty strings**, whether they are empty fields or empty delimiters. Non-empty delimiters (such as `","`) still remain in the array.

### Positive limit in splitWithDelimiters

Suppose `limit = n > 0`: the regex is applied to split at most `n - 1` times, so the result has **at most `2n - 1` elements**. The tail remains unsplit after the last delimiter used for splitting.

```java
System.out.println(
    java.util.Arrays.toString("boo:::and::foo".splitWithDelimiters(":+", 2))
);
// [boo, :::, and::foo]
```

In this example, only the first `":::"` delimiter is used; `"and::foo"` is the unsplit remainder. Do not assume `limit = 2` keeps at most 2 elements: the array can have length 3 because it includes the delimiter.

There is an equivalent API on `java.util.regex.Pattern`:

```java
java.util.regex.Pattern pattern =
        java.util.regex.Pattern.compile(":+");

String[] parts = pattern.splitWithDelimiters("boo:::and::foo", -1);
```

Using `Pattern` fits well when the same regex is reused many times or needs flags like `CASE_INSENSITIVE`. Both `Pattern.splitWithDelimiters` and `String.splitWithDelimiters` were introduced in Java 21.

## 4. Leading, Trailing, and Consecutive Delimiters

A delimiter **matching positive length at the start of input** produces a leading `""` element:

```java
String[] result = ",a,".splitWithDelimiters(",", -1);

// ["", ",", "a", ",", ""]
```

With `split(",", -1)`, the corresponding result is `["", "a", ""]` because delimiters are omitted from the array.

When multiple delimiters appear consecutively, check how the regex matches:

```java
String a = "a:::b";

System.out.println(java.util.Arrays.toString(
        a.splitWithDelimiters(":", -1)));
// [a, :, , :, , :, b]

System.out.println(java.util.Arrays.toString(
        a.splitWithDelimiters(":+", -1)));
// [a, :::, b]
```

With regex `":"`, empty segments appear between adjacent delimiters. With regex `":+"`, the entire `":::"` sequence is a single delimiter and **there are no empty segments between those characters**.

If business rules require splitting on each individual comma, do not accidentally use regex `",+"`, as it merges adjacent commas and hides empty columns. Assert in tests that both field count and empty-field positions match the specified format.

## 5. Regexes with Special Meaning and Zero-Width Matches

Both `split` and `splitWithDelimiters` accept a **regex**, not a literal separator character. A dot `.` in regex means “any character” (per regex rules), not a literal dot.

For example, to split on a literal dot:

```java
String input = "a.b.";
String[] items = input.split("\\.", -1);

// ["a", "b", ""]
```

`"\\."` escapes regex `\.` in a **Java string literal**. If the delimiter comes from user input and must be treated strictly as literal text, use:

```java
String delimiter = ".";
String regex = java.util.regex.Pattern.quote(delimiter);
String[] items = "a.b.".split(regex, -1);
```

When the regex is `"\\s+"`, each run of one or more whitespace characters counts as **one delimiter**. With `splitWithDelimiters`, the entire matched whitespace run is preserved in the delimiter element; this helps when whitespace must be kept to reconstruct original data.

### Zero-Width Regex Matches

Regexes such as lookahead `(?=b)` or word boundary `\\b` can match at a position **without consuming characters**. Java's rule has an important exception:

- When a delimiter has **positive length** and matches at the start of input, Java adds a leading `""` field.
- When a delimiter matches **zero length at the start of input**, Java **does not add** a leading empty field, and `splitWithDelimiters` likewise does not add a corresponding leading empty delimiter.

Example on Java 21+:

```java
String[] positive = "abc".splitWithDelimiters("a", -1);
// ["", "a", "bc"]

String[] zeroWidthAtStart =
        "abc".splitWithDelimiters("(?=a)", -1);
// ["abc"]
```

`(?=a)` is a positive lookahead matching the position before `a` without consuming `a`. Hence it produces no non-empty delimiter at index 0.

At the end of a string, regex `$` can also produce a zero-length match:

```java
String[] keep = "abc".splitWithDelimiters("$", -1);
// ["abc", "", ""]

String[] dropTrailing = "abc".splitWithDelimiters("$", 0);
// ["abc"]
```

The last two elements of `keep` are an empty delimiter and a trailing empty text segment. With `limit = 0`, trailing empty elements are discarded. Zero-width regex matches are subtle: test start/end of strings and empty inputs, and avoid assuming every match consumes at least one character.

## 6. Java 21+ Program for Testing Empty Elements Accurately

To make results easy to verify, the following example prints **double quotes** around every element rather than using `Arrays.toString`, which makes empty strings hard to spot.

Save as `SplitEmptyAndDelimitersDemo.java` in UTF-8:

```java
import java.util.StringJoiner;
import java.util.regex.Pattern;

public class SplitEmptyAndDelimitersDemo {
    private static String show(String[] items) {
        StringJoiner output = new StringJoiner(", ", "[", "]");
        for (String item : items) {
            String visible = item.replace("\\", "\\\\")
                                 .replace("\n", "\\n");
            output.add("\"" + visible + "\"");
        }
        return output.toString();
    }

    private static void print(String label, String[] items) {
        System.out.println(label + " = " + show(items));
    }

    public static void main(String[] args) {
        String csv = "a,b,,";
        print("split default", csv.split(","));
        print("split zero", csv.split(",", 0));
        print("split minus", csv.split(",", -1));
        print("split two", csv.split(",", 2));

        print("initial default", ",a,".split(","));
        print("initial minus", ",a,".split(",", -1));
        print("middle empty", "a,,b,".split(",", -1));
        print("empty input", "".split(",", -1));
        print("literal dot", "a.b.".split("\\.", -1));

        String repeated = "a,,b,";
        print("with -1", repeated.splitWithDelimiters(",", -1));
        print("with 0", repeated.splitWithDelimiters(",", 0));
        print("with 2", repeated.splitWithDelimiters(",", 2));
        print("with 1", repeated.splitWithDelimiters(",", 1));

        print("positive start",
                "abc".splitWithDelimiters("a", -1));
        print("zero width start",
                "abc".splitWithDelimiters("(?=a)", -1));

        Pattern runsOfColon = Pattern.compile(":+");
        print("colon all",
                runsOfColon.splitWithDelimiters("boo:::and::foo", -1));
        print("colon limit 2",
                runsOfColon.splitWithDelimiters("boo:::and::foo", 2));
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac -encoding UTF-8 SplitEmptyAndDelimitersDemo.java
java SplitEmptyAndDelimitersDemo
```

Expected output, where `""` denotes an empty string element:

```text
split default = ["a", "b"]
split zero = ["a", "b"]
split minus = ["a", "b", "", ""]
split two = ["a", "b,,"]
initial default = ["", "a"]
initial minus = ["", "a", ""]
middle empty = ["a", "", "b", ""]
empty input = [""]
literal dot = ["a", "b", ""]
with -1 = ["a", ",", "", ",", "b", ",", ""]
with 0 = ["a", ",", "", ",", "b", ","]
with 2 = ["a", ",", ",b,"]
with 1 = ["a,,b,"]
positive start = ["", "a", "bc"]
zero width start = ["abc"]
colon all = ["boo", ":::", "and", "::", "foo"]
colon limit 2 = ["boo", ":::", "and::foo"]
```

The program confirms four points at once: `split(regex)` equals `split(regex, 0)`; negative limit keeps trailing empties; `splitWithDelimiters` preserves matched delimiters; and zero-width matches at the start do not create a leading empty element.

## 7. Writing Assertions Instead of Just Inspecting Output

In automated tests, compare **arrays by value and order**, including empty strings. With JUnit 5, use `assertArrayEquals(expected, actual)`. In plain Java, `Arrays.equals` suffices for demonstration:

```java
import java.util.Arrays;

public class SplitAssertions {
    private static void check(String name, String[] expected, String[] actual) {
        if (!Arrays.equals(expected, actual)) {
            throw new AssertionError(name + ": expected "
                    + Arrays.toString(expected)
                    + " but got " + Arrays.toString(actual));
        }
        System.out.println(name + " = PASS");
    }

    public static void main(String[] args) {
        check("trailing fields",
                new String[] {"a", "b", "", ""},
                "a,b,,".split(",", -1));

        check("default removes trailing",
                new String[] {"a", "b"},
                "a,b,,".split(","));

        check("middle empty",
                new String[] {"a", "", "b"},
                "a,,b,".split(","));

        check("retain delimiters",
                new String[] {"a", ",", "", ",", "b", ",", ""},
                "a,,b,".splitWithDelimiters(",", -1));

        check("limit two",
                new String[] {"a", ",", ",b,"},
                "a,,b,".splitWithDelimiters(",", 2));

        check("empty source",
                new String[] {""},
                "".split(",", -1));
    }
}
```

Run with JDK 21+:

```bash
javac -encoding UTF-8 SplitAssertions.java
java SplitAssertions
```

Output:

```text
trailing fields = PASS
default removes trailing = PASS
middle empty = PASS
retain delimiters = PASS
limit two = PASS
empty source = PASS
```

This is a standalone test program requiring no JUnit setup. The key habit to carry over to JUnit is **asserting the entire array**, not just `array.length`. Two arrays of identical length with empty elements at different positions represent different data.

If an application must support Java 17, you can keep the `split` assertions on Java 17; however, remove or replace the `splitWithDelimiters` tests because that API does not exist in that JDK release.

## 8. Essential Boundary Test Suite for Projects

For code using `split` to parse a simple format, include these parallel test groups:

| Case | Typical Input and Regex | What to Assert |
| --- | --- | --- |
| No delimiter | `"abc"`, `","` | Single element `"abc"` |
| Empty input | `""`, `","` | `[""]` when the regex does not match |
| Leading delimiter | `",abc"`, `","` | Leading empty element kept if match has positive length |
| Trailing delimiter | `"abc,"`, `","` | Contrast `limit = 0` vs. `-1` |
| Two consecutive delimiters | `"a,,b"`, `","` | Empty field in the middle |
| Multiple trailing delimiters | `"a,b,,"`, `","` | `limit = -1` keeps all trailing empty fields |
| Positive limit | `"a,b,c"`, `","`, `2` | Remaining tail `"b,c"` is not split further |
| Regex with metacharacter | `"a.b"`, literal dot | Use `"\\."` or `Pattern.quote(".")` |
| Grouped delimiter regex | `"a:::b"`, `":+"` | Delimiter `":::"` kept as one element by `splitWithDelimiters` |
| Leading lookahead | `"abc"`, `"(?=a)"` | Does not create a leading empty part |
| End-of-string regex | `"abc"`, `"$"` | Check trailing empty strings according to `limit` |
| Unicode | Strings with multi-unit UTF-16 characters | Regex and expectations do not accidentally split surrogate pairs |
| Invalid delimiter | `"a[b"` with regex `"["` | Verify `PatternSyntaxException` is handled at the input boundary |

When testing business data, clarify whether “a trailing delimiter” represents a **valid empty field**, an invalid line, or simply a record terminator. Java's `split` cannot decide that policy for you.

**Especially for real CSV:** `split(",")` or `split(",", -1)` is **not a complete CSV parser**. CSV can allow commas inside quoted fields, escaped quotes, and embedded newlines. When data follows those rules, use a format-compliant CSV parser and test empty fields against that parser's contract. `split` is only appropriate when delimiters are simple and quoting context is unnecessary.

## 9. Reconstructing Strings and Checking Delimiters

With `splitWithDelimiters(regex, -1)`, the result retains every text segment and delimiter in order, so for suitable regexes and inputs, joining them reproduces the exact original input:

```java
String original = "left==right;next";
String[] tokens = original.splitWithDelimiters("==|;", -1);

String restored = String.join("", tokens);

System.out.println(original.equals(restored)); // true
```

This style of check is useful when writing a lightweight lossless tokenizer. It verifies **text preservation**, though it does not prove token classification matches business semantics: you still must assert individual elements and specific delimiters.

A good test can verify both:

```java
String original = "a,,b,";
String[] tokens = original.splitWithDelimiters(",", -1);

boolean sameContent = String.join("", tokens).equals(original);
boolean sameStructure = java.util.Arrays.equals(tokens,
        new String[] {"a", ",", "", ",", "b", ",", ""});

System.out.println(sameContent);   // true
System.out.println(sameStructure); // true
```

If you need **typed tokens** (text, delimiter, start/end offsets, whitespace), `splitWithDelimiters` only returns the strings, not offsets; when match positions are needed, use `Matcher.find()` with `start()/end()` to collect positions explicitly.

## 10. Common Mistakes

1. **Using `split(",")` to count columns that may be empty at the end.** The default overload drops trailing empties. Use `split(",", -1)` when the format treats them as columns.
2. **Relying on `Arrays.toString` to count empty items by eye.** Print with quotes or use `assertArrayEquals`.
3. **Using `limit = 1` expecting two parts.** Positive limit `1` yields at most one element, usually the entire input.
4. **Thinking `splitWithDelimiters`'s `limit` is also the maximum element count.** With positive limit `n`, the array can contain up to `2n - 1` elements because delimiters are retained.
5. **Confusing regex with literal text.** `.` or `|` has regex meaning; escape properly or use `Pattern.quote`.
6. **Expecting repeated delimiters to yield multiple empty fields when the regex is `,+`.** The regex can collapse the entire delimiter run into one match.
7. **Confusing `splitWithDelimiters` with capturing groups in `split`.** Java's `split` does not include capturing groups in the result; to retain delimiters use the Java 21 API or scan manually with `Matcher`.
8. **Forgetting zero-width matches at the start.** This rule does not generate a leading empty part like positive-length matches do.
9. **Ignoring `PatternSyntaxException`.** If regexes are supplied dynamically, have a clear validation/parsing policy.
10. **Using `splitWithDelimiters` and running on JDK 17.** The method does not exist in Java 17; Java 21+ or a backward-compatible alternative is required.
11. **Using `split` for CSV or complex quoted formats.** Fields containing quoted delimiters or quoted newlines must be handled by a compliant parser.

## 11. Self-Practice Questions and Exercises

**Exercise 1.** For `"x,y,,"`, how do these two calls differ?

```java
"x,y,,".split(",");
"x,y,,".split(",", -1);
```

**Answer:** The first returns `["x", "y"]`; the second returns `["x", "y", "", ""]`. The last two elements represent the two empty fields caused by the two trailing commas.

**Exercise 2.** For `"a,,b,".splitWithDelimiters(",", 2)`, how many elements are returned?

**Answer:** Three elements: `["a", ",", ",b,"]`. `limit = 2` allows the delimiter to be applied at most once and keeps the rest intact.

**Exercise 3.** What does `"a::b".splitWithDelimiters(":+", -1)` return?

**Answer:** `["a", "::", "b"]` because regex `:+` matches both colons as **one** delimiter.

**Exercise 4.** Why does `"abc".splitWithDelimiters("(?=a)", -1)` not start with `""`?

**Answer:** `(?=a)` is a zero-length match at the beginning; the API does not add a leading empty part or empty delimiter in that case.

**Exercise 5.** Can Java 17 call `String.splitWithDelimiters` directly?

**Answer:** No. The method was introduced in Java 21. On Java 17, use `split` when delimiters are not needed or scan with `Pattern`/`Matcher` if you need both text and delimiters.

## References

- [Java SE 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): both `split` overloads and `splitWithDelimiters`, definition of `limit`, zero-width match rules.
- [Java SE 21 — Pattern](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html): `split(input, limit)`, `splitWithDelimiters(input, limit)`, and regex examples.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `split` contract prior to `splitWithDelimiters`.

**Takeaway:** When **trailing empty fields** must be preserved, use `split(regex, -1)`. When **delimiters** must also be preserved and JDK 21+ is available, use `splitWithDelimiters(regex, -1)`; when testing, assert content, length, and element order across the entire array.
