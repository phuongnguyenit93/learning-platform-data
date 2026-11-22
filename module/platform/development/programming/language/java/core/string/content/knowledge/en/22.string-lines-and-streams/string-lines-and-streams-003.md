# Differences Between String.lines() and String.split() with the limit Parameter in Java



## 1. Lesson Objectives

Java provides two common ways to process a multi-line string:

- `String.lines()` (Java 11+) returns a `Stream<String>`, iterating over lines separated by **LF (`\n`), CR (`\r`), or CRLF (`\r\n`)**. This is a line-oriented operation; there is no `limit` parameter like `split`.
- `String.split(regex)` and `String.split(regex, limit)` return a **`String[]` array**, splitting by a **regular expression**. The `limit` parameter controls **how many times the regex is applied** and **whether trailing empty strings are kept or discarded**.

The most important differences are **empty data**, **how elements are limited**, **which newline characters are recognized**, and **how results are consumed**. You should not treat `lines()` as a completely equivalent shorthand for `split("\\R")`.

Quick example:

```java
String text = "A\n\nB\n";

System.out.println(text.lines().toList());            // [A, , B]
System.out.println(Arrays.toString(text.split("\\R")));    // [A, , B]
System.out.println(Arrays.toString(text.split("\\R", -1))); // [A, , B, ]
```

Although the first two lines look similar in this example, they **differ in return type and operating mode**. The last line has an extra `""` element representing the empty slot after the final newline character. When printing a `List` or array directly, empty elements are hard to spot; this lesson will use a custom `<...>` display format.

**Scope of this lesson:** `String.lines()` treats LF, CR, and CRLF as line endings and does not produce an empty line solely from a trailing newline. Detailed explanations of the terminators are in the lesson **lines and CR, LF, CRLF Line Endings**, and the boundary table for empty strings/trailing newlines is in the lesson **Empty Strings and Trailing Line Endings**. This lesson focuses on `limit` modes, return types, and element counts.

**Separator differences:** regex `\\R` recognizes Unicode linebreaks beyond LF/CR/CRLF, such as U+2028; `split("\\n")` only splits on LF and can therefore leave CR in the string before a CRLF. Choose the regex according to your input format.

## 2. String.split(regex, limit): Three limit Modes

Syntax:

```java
String[] parts = text.split(regex);         // Equivalent to text.split(regex, 0)
String[] all = text.split(regex, -1);       // Keeps trailing empty parts
String[] atMostTwo = text.split(regex, 2); // At most two elements
```

`regex` is a **regular expression** (not a literal separator string). To split on every Unicode linebreak supported by Java regex, use `"\\R"` in **Java source code**. Two backslashes `\\` in Java source produce a single `\` in the runtime string; `\R` is the regex syntax representing a Unicode linebreak sequence. Writing `"\R"` directly in source code will not compile because `\R` is not a Java string escape.

| `limit` value | How splitting works | Trailing empty parts |
| --- | --- | --- |
| `limit > 0` | The pattern is applied **at most `limit - 1` times**; the final element contains the entire remaining input | Kept if present in the resulting parts |
| `limit = 0` | The pattern is applied as many times as possible | **Discards all** trailing `""` elements |
| `limit < 0`, e.g., `-1` | The pattern is applied as many times as possible | **Keeps all** trailing `""` elements |

`text.split(regex)` is equivalent to `text.split(regex, 0)`. The `0` here does **not** mean returning zero elements; it is the mode that splits as much as possible while discarding trailing empty strings.

Concrete examples with `"A\n\nB\n"`:

- `split("\\R", 0)` → `["A", "", "B"]`. Keeps the blank line in the middle, but discards the trailing empty field.
- `split("\\R", -1)` → `["A", "", "B", ""]`. Also keeps the empty field after the final newline.
- `split("\\R", 2)` → `["A", "\nB\n"]`. Splits only at the **first** newline; the second element retains a newline before `B` and the trailing newline.
- `split("\\R", 1)` → a single-element array containing the entire `"A\n\nB\n"`. No splits are applied because `limit - 1 = 0`.

This shows that a positive `limit` in `split` is **not equivalent** to the number of lines taken from `lines().limit(n)`.

## 3. Runnable Example with Java 17+

Create the file **`LinesVsSplitDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class LinesVsSplitDemo {
    // Wrap each element in <> and show newline characters as \n, \r
    // to distinguish empty elements from an empty array/list.
    static String show(List<String> parts) {
        return parts.stream()
                .map(s -> "<" + s
                        .replace("\r", "\\r")
                        .replace("\n", "\\n") + ">")
                .collect(Collectors.joining(", ", "[", "]"));
    }

    static String show(String[] parts) {
        return show(Arrays.asList(parts));
    }

    public static void main(String[] args) {
        String input = "A\n\nB\n";

        System.out.println("lines       = " + show(input.lines().toList()));
        System.out.println("split(0)    = " + show(input.split("\\R")));
        System.out.println("split(-1)   = " + show(input.split("\\R", -1)));
        System.out.println("split(2)    = " + show(input.split("\\R", 2)));
        System.out.println("limit(2)    = " + show(input.lines().limit(2).toList()));

        System.out.println("mix         = "
                + show("A\r\nB\rC\nD".lines().toList()));

        System.out.println("empty lines = " + "".lines().count());
        System.out.println("empty split = " + "".split("\\R").length);

        String unicode = "A\u2028B"; // Unicode LINE SEPARATOR (U+2028)
        System.out.println("unicode lines = " + unicode.lines().count());
        System.out.println("unicode split = " + unicode.split("\\R").length);
    }
}
```

Compile and run in the directory containing the file:

```bash
javac --release 17 LinesVsSplitDemo.java
java LinesVsSplitDemo
```

**Stdout** (behavior of expressions verified with JShell/JDK):

```text
lines       = [<A>, <>, <B>]
split(0)    = [<A>, <>, <B>]
split(-1)   = [<A>, <>, <B>, <>]
split(2)    = [<A>, <\nB\n>]
limit(2)    = [<A>, <>]
mix         = [<A>, <B>, <C>, <D>]
empty lines = 0
empty split = 1
unicode lines = 1
unicode split = 2
```

Key results:

1. `lines()` keeps the **internal blank line** of `"A\n\nB\n"`, but does not create an extra blank line after the trailing `\n`.
2. `split("\\R", -1)` keeps the **trailing empty column**, suitable when you must distinguish a delimiter-terminated record from one without a trailing delimiter.
3. `split("\\R", 2)` retains `"\nB\n"` inside the last token; `lines().limit(2)` takes only the **first two lines**, `"A"` and `""`.
4. Empty input is a stark difference: `lines()` yields `0` lines, whereas `split("\\R")` yields an array with **one** element `""`. Printing `Arrays.toString` directly can make both look like `[]` even though their element counts differ.
5. The character U+2028 is recognized by `\\R` as a line break, whereas `lines()` does **not** recognize it as one of the three LF/CR/CRLF line terminators.

## 4. Easily Confused Differences When Using limit

### 5.1. lines().limit(n) Counts Lines, split(regex, n) Counts Maximum Parts

Given the input `"red\ngreen\nblue"`:

```java
String colors = "red\ngreen\nblue";

List<String> topTwo = colors.lines().limit(2).toList();
// ["red", "green"]

String[] twoParts = colors.split("\\R", 2);
// ["red", "green\nblue"]
```

`lines().limit(2)` skips the `blue` line because the terminal operation does not request beyond two elements. Conversely, `split("\\R", 2)` does not discard data after the first separator; the entire remainder `green\nblue` stays in the final element.

**When to use which?**

- Only need the first two lines for display, preview, or checking a header: `lines().limit(2)`.
- Want to split a **head** and the **remaining body**, for example first line as header and the rest as content: `split("\\R", 2)`. Handle empty input and the no-delimiter case according to your business logic.

### 5.2. Do Not Confuse split(..., 0) with Stream.limit(0)

`split("\\R", 0)` requests splitting in the mode that discards trailing empty fields; the result can still contain multiple elements. `lines().limit(0)` is a Stream with no elements at all. The two `0` values in these two APIs have completely different meanings:

```java
String data = "a\nb";
System.out.println(data.split("\\R", 0).length); // 2
System.out.println(data.lines().limit(0).count()); // 0
```

### 5.3. filter and limit Change Logical Order

```java
String input = "\nfirst\n\nsecond\nthird";

List<String> a = input.lines()
        .filter(s -> !s.isBlank())
        .limit(2)
        .toList();
// ["first", "second"]

List<String> b = input.lines()
        .limit(2)
        .filter(s -> !s.isBlank())
        .toList();
// ["first"]
```

In `a`, the program finds the first two **non-blank** lines; in `b`, it examines only the first two original lines and then filters them. The same rule applies to Stream pipelines in general.

## 5. Blank Lines: Table of Edge Cases

The table uses `<A>` for the string `"A"` and `<>` for the empty string. Square brackets `[...]` represent a list of elements; `[]` means no elements at all. All input strings below use actual `\n` characters.

| Input in Java | `lines()` | `split("\\R", 0)` | `split("\\R", -1)` |
| --- | --- | --- | --- |
| `""` | `[]` | `[<>]` | `[<>]` |
| `"A"` | `[<A>]` | `[<A>]` | `[<A>]` |
| `"A\n"` | `[<A>]` | `[<A>]` | `[<A>, <>]` |
| `"A\n\n"` | `[<A>, <>]` | `[<A>]` | `[<A>, <>, <>]` |
| `"\nA"` | `[<>, <A>]` | `[<>, <A>]` | `[<>, <A>]` |
| `"\n"` | `[<>]` | `[]` | `[<>, <>]` |
| `"A\nB"` | `[<A>, <B>]` | `[<A>, <B>]` | `[<A>, <B>]` |

You cannot replace `lines()` with `split("\\R", 0)` and expect to preserve 100% of the line structure in all cases. The two APIs differ especially on empty strings and when the input ends with multiple delimiters. If an application needs to store an exact list of fields/records, you must clearly define whether a trailing newline represents a new empty field or merely a **line terminator**.

For `split`, empty parts in the **middle** are kept by default; discarding applies only to **trailing** empty parts when `limit` is 0.

## 6. Choosing an API Based on Real Requirements

| Requirement | Approach to Consider | Reason |
| --- | --- | --- |
| Read lines from a string, filter, and take the first few lines | `text.lines().filter(...).limit(n)` | Lazy stream; `limit` stops iteration once enough elements are found |
| Collect all LF/CR/CRLF lines into a `List` | `text.lines().toList()` | Easy to chain `map`/`filter` for line-based processing |
| Need a `String[]` of parts separated by Unicode newlines, dropping trailing empties | `text.split("\\R")` | Regex splitting, default `limit=0` |
| Need to keep trailing empty fields in delimiter-separated data | `text.split("\\R", -1)` | Preserves the empty element position after the final delimiter |
| Need to split once to get header and remainder | `text.split("\\R", 2)` | Final element retains the unsplit remainder |
| Need to keep every character without regex semantics | Choose an appropriate literal API or handle indices directly | `split` takes a regex; special delimiters must be escaped |

**Performance note:** `String.lines()` is often better suited when you need a Stream pipeline and can stop early. `split` returns an array, creating all result parts before the caller processes them. For small inputs or when all parts are needed, choose based on semantics and verify with a benchmark if performance truly matters. Avoid claiming that Stream is always faster.

**Scope note:** Both APIs operate on a `String` **already in memory**; `String.lines()` does not read data from files or networks by itself. When processing very large files, `Files.lines(path)` (which returns a Stream reading from a file) is a different API with its own resource-management requirements.

## 7. Self-Check Exercises

**Exercise 1: Predict the element count.** Given `String input = "\n\n";`, consider:

```java
System.out.println(input.lines().count());
System.out.println(input.split("\\R", 0).length);
System.out.println(input.split("\\R", -1).length);
```

The respective answers are **2, 0, 3**. Two newlines terminate two empty lines; `split` with limit 0 discards all trailing empty strings, while a negative limit keeps all three empty parts before, between, and after the two delimiters.

**Exercise 2: Only need the first two valid lines.** Given `"\nalpha\n\nbeta\ngamma"`, write:

```java
List<String> result = "\nalpha\n\nbeta\ngamma"
        .lines()
        .filter(s -> !s.isBlank())
        .limit(2)
        .toList();
System.out.println(result); // [alpha, beta]
```

If you move `limit(2)` before `filter`, the result is only `[alpha]`, because only the first two source lines are examined.

**Exercise 3: Keep the body content intact after the header line.** Given `"HEADER\nbody line 1\nbody line 2"`, use:

```java
String[] parts = "HEADER\nbody line 1\nbody line 2"
        .split("\\R", 2);
System.out.println(parts[0]); // HEADER
System.out.println(parts[1]); // prints two body lines, keeping the \n between them
```

`split("\\R", 2)` is appropriate because the second element preserves `"body line 1\nbody line 2"`. Using `lines().limit(2)` would lose the second body line.

**Exercise 4: Empty input.** Explain why `"".lines().count()` equals 0 whereas `"".split("\\R").length` equals 1: `lines` defines **lines**, whereas `split`, when no delimiter matches, returns **the entire input** as a single token, even when that token is `""`.

## 8. Quick Summary

`String.lines()` is a tool for processing **LF/CR/CRLF lines with a lazy Stream**, suitable for pipelines and taking the first few lines. `String.split(regex, limit)` is a tool for **regex splitting into an array**; `limit=0` drops trailing empty fields, `limit<0` keeps trailing empty fields, and `limit>0` limits the number of splits while keeping the remainder in the last token. `Stream.limit(n)` limits the **number of emitted lines**; it does not have the same meaning as `split(..., n)`. Choose based on **which empty data must be kept**, **the actual newline types**, **the return type**, and **how the remaining data is used**.

**Official documentation:** [Java SE 17 — String.lines()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#lines()), [Java SE 17 — String.split(String, int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#split(java.lang.String,int)), [Java SE 17 — Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html), [Java SE 17 — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).
