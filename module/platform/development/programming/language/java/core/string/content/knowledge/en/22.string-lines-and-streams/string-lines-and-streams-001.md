# String.lines() and CR, LF, CRLF Line Endings



## 1. Lesson Objectives

A Java string can contain multiple lines of text: configuration file contents, downloaded HTTP messages, command outputs, or data copied from another operating system. A “line break” in this data is not necessarily a single character. The three common forms are **LF**, **CR**, and **CRLF**. When processing multiple lines, we need to know what characters the string contains, which methods treat them as line boundaries, and whether blank lines are preserved.

Since **Java 11**, `String.lines()` lets you iterate over the lines in a `String` via a `Stream<String>`. This lesson focuses on:
- Understanding `\n` (LF), `\r` (CR), and `\r\n` (CRLF) accurately.
- Knowing which strings `String.lines()` returns and how it removes line terminators.
- Predicting cases with **blank lines in the middle of text**, **empty strings**, and **trailing line terminators**.
- Processing lines with Stream, comparing with `split("\\R")`, and choosing the right approach for cross-platform data.

## 2. What Are CR, LF, and CRLF?

| Name | Full Name | Escape in Java String | Unicode Code | Character |
| --- | --- | --- | --- | --- |
| LF | Line Feed | `\n` | `U+000A` | A line feed control character |
| CR | Carriage Return | `\r` | `U+000D` | A control character that historically returns the print head to the start of a line |
| CRLF | Carriage Return + Line Feed | `\r\n` | `U+000D U+000A` | **Two consecutive characters**, usually treated as **a single** line ending |

In practice, Unix/Linux-style text commonly uses LF, Windows text commonly uses CRLF, and standalone CR was formerly common on classic Macintosh systems. These are common conventions, not immutable rules: a file can be created, synced, or transferred across other systems and contain any form.

Note that `"\r\n"` has length **2** in a Java `String`, but many text-processing APIs treat this pair as **a single line boundary**. You should not treat CR and LF inside a CRLF pair as two independent lines.

```java
String lf = "A\nB";
String cr = "A\rB";
String crlf = "A\r\nB";

System.out.println(lf.length());   // 3
System.out.println(cr.length());   // 3
System.out.println(crlf.length()); // 4
```

All three strings represent two lines according to `String.lines()`, but the number of characters inside differs. The escapes `\n` and `\r` are written in **Java source code**; the runtime value contains actual control characters, not the two characters `\` and `n`/`r`.

## 3. How Does String.lines() Work?

API signature:

```java
public Stream<String> lines()
```

This is an **instance method** of `java.lang.String`, available since Java 11. It returns a `Stream<String>` containing the lines of the source string in order of appearance. Each element is the line content, **excluding line terminators**.

In the definition of `String.lines()`, a *line terminator* is **one of three forms**: LF (`\n`), CR (`\r`), or CRLF (`\r\n`). A CRLF pair is consumed together as a single line terminator, even though it consists of two characters.

Intuitively, a line is:
1. Zero or more characters preceding a line terminator, **or**
2. Zero or more characters at the end of the string, after the last line terminator if any characters remain.

However, **a trailing line terminator at the end of a string does not by itself produce an extra final blank line**. This is a common point of confusion when comparing with `String.split(..., -1)`.

```java
import java.util.List;

String text = "start\nend";
List<String> lines = text.lines().toList();

System.out.println(lines);       // [start, end]
System.out.println(lines.size()); // 2
```

`Stream.toList()` has been available since Java 16, so this example is suitable for Java 17+. On Java 11, you can replace `.toList()` with `.collect(Collectors.toList())`.

## 4. Practical Example: Mixing CR, LF, and CRLF

Create a file `LinesDemo.java` (saved as UTF-8) with the following complete code:

```java
import java.util.List;

public class LinesDemo {
    private static void show(String label, String input) {
        List<String> lines = input.lines().toList();
        System.out.println(label + " = " + lines.size() + " lines");

        for (int i = 0; i < lines.size(); i++) {
            System.out.println("  " + i + ": [" + lines.get(i) + "]");
        }
    }

    public static void main(String[] args) {
        show("LF", "A\nB");
        show("CR", "A\rB");
        show("CRLF", "A\r\nB");
        show("mixed", "one\ntwo\r\nthree\rfour");
        show("blank middle", "A\n\nB");
        show("trailing LF", "A\n");
        show("empty", "");
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 LinesDemo.java
java LinesDemo
```

Stdout:

```text
LF = 2 lines
  0: [A]
  1: [B]
CR = 2 lines
  0: [A]
  1: [B]
CRLF = 2 lines
  0: [A]
  1: [B]
mixed = 4 lines
  0: [one]
  1: [two]
  2: [three]
  3: [four]
blank middle = 3 lines
  0: [A]
  1: []
  2: [B]
trailing LF = 1 lines
  0: [A]
empty = 0 lines
```

The program prints `[ ]` around each line so empty content is easy to spot; in the output, `[]` is a line string of length 0. Line order is preserved as elements pass through the Stream.

Observe the differences:
- `"A\nB"`, `"A\rB"`, and `"A\r\nB"` all produce two lines `"A"` and `"B"`.
- `"A\n\nB"` contains **two consecutive line terminators**; the gap between them is a valid blank line.
- `"A\n"` ends right after an LF; `lines()` returns only `"A"`.
- `""` has no characters and no lines; the Stream is empty.

### Scope Boundaries with Deep-Dive Lessons

The table of blank lines and trailing newline characters is examined in detail in the lesson **Empty Strings and Trailing Line Endings**. If you need to distinguish `split(regex, 0)`, `split(regex, -1)`, and `lines().limit(n)`, see the lesson **Differences Between lines and split with limit**. In the current lesson, the main focus is how LF, CR, and CRLF are recognized as line boundaries and the impact of normalizing them.

## 5. Processing Lines with Stream

Because `lines()` returns `Stream<String>`, you can directly chain `map`, `filter`, `count`, `forEach`, `limit`, `collect`, etc. to perform line-by-line operations.

### Counting Lines

```java
String text = "alpha\nbeta\r\ngamma";
long count = text.lines().count(); // 3
```

The value here is the **number of line elements** produced by `lines()`, not the number of occurrences of the `\n` character. In the string above, CRLF is a single line ending; there are three lines in total.

### Filtering Out Empty or Whitespace-Only Lines

```java
import java.util.List;

String text = "  Java  \n\n  \r\nStream\n";
List<String> nonBlank = text.lines()
        .map(String::strip)
        .filter(line -> !line.isEmpty())
        .toList();

System.out.println(nonBlank); // [Java, Stream]
```

In this example:
- `strip()` removes Unicode whitespace according to `Character.isWhitespace` from both ends of the string (Java 11+).
- `filter(...)` drops lines that become empty after stripping.
- `toList()` collects the results into a list (Java 16+).

If you need to **keep** blank lines to preserve the original layout, do not apply `filter`. If you only want to skip blank lines according to `String.isBlank()` while preserving whitespace on other lines, you can use `.filter(line -> !line.isBlank())`.

### Adding Line Numbers

```java
import java.util.List;
import java.util.stream.IntStream;

List<String> lines = "first\nsecond\nthird".lines().toList();
List<String> numbered = IntStream.range(0, lines.size())
        .mapToObj(i -> (i + 1) + ". " + lines.get(i))
        .toList();

System.out.println(numbered);
// [1. first, 2. second, 3. third]
```

This is an illustrative snippet placed inside a method or `main`; a complete standalone runnable example was already shown in section 4.

### Joining Lines Back Together

```java
import java.util.stream.Collectors;

String original = "A\r\nB\nC";
String normalized = original.lines()
        .collect(Collectors.joining("\n"));

System.out.println(normalized.equals("A\nB\nC")); // true
```

After splitting, the CR, LF, or CRLF characters **are no longer present in the line elements**. To join them back together, you must actively choose a new separator. This result does not preserve the exact original line terminators. If the original text ended with a newline, joining the lines will normally **not** recreate the trailing newline. If you need to preserve every byte of the source text, do not call `lines()` and then join without recording the line-terminator information.

## 6. Avoid Confusing with System.lineSeparator()

`System.lineSeparator()` returns the **default line-ending string of the running platform**. Typically on Windows this is `"\r\n"`, while on modern Linux/macOS it is `"\n"`. This value is meant for **generating platform-appropriate output**, not for determining which terminators `String.lines()` can read.

```java
String output = String.join(
        System.lineSeparator(), "first", "second");
```

The snippet above creates text using the system line separator. However, if a `String` already contains CRLF or CR from another source, `lines()` still recognizes them, regardless of which operating system the machine is running on.

Similarly, `%n` in `String.format(...)`/`Formatter` prints the platform-specific line separator, and `println(...)` also emits the environment's line ending. These ways of **generating line breaks** are different from the **reading/splitting line break** rules of `String.lines()`.

## 7. Lines, Streams, and Resources

`String.lines()` operates on a **string already in memory**. It does not read files on its own, open connections, or close OS streams. The returned Stream supports pipelined operations, preserves the order of the source text, and finds line boundaries lazily as the Stream is consumed.

Example taking only the first two lines:

```java
import java.util.List;

String text = "one\ntwo\nthree\nfour";
List<String> firstTwo = text.lines().limit(2).toList();

System.out.println(firstTwo); // [one, two]
```

A Stream is consumed by a terminal operation such as `toList()` or `count()`; **you must not reuse the same Stream object** after a terminal operation has run:

```java
import java.util.stream.Stream;

String text = "A\nB";
Stream<String> stream = text.lines();

long count = stream.count(); // 2
// stream.toList(); // Error: Stream has already been operated upon
```

To process the text a second time, call `text.lines()` again. `String.lines()` creates a Stream from a `String`; `String` itself is immutable, so it is not altered by reading lines.

**For very large files:** reading an entire file into a `String` can consume a lot of memory. When incremental processing is needed, choose `Files.lines(path, charset)` or `BufferedReader.lines()` and manage the file/reader lifecycle with `try-with-resources`. `Files.lines` needs its Stream closed because it holds I/O resources; `String.lines` has no file resources to close. File-reading line APIs and `String.lines` share the goal of working with lines of text, but their cost and resource lifecycles differ.

## 8. Practical Rules for Normalizing Line Endings

When receiving text from multiple sources, determine the **output requirements** before converting:
1. **Only need line-based computation** (counting, filtering, searching): `String.lines()` is usually appropriate.
2. **Need to normalize content for display or comparison:** use `lines()` and join with `"\n"` or your chosen output rule, accepting changes to original line endings and the potential loss of a trailing newline.
3. **Need to preserve the exact original format, including mixed CRLF/CR/LF or trailing newline:** keep the original string; if parsing is required, use an algorithm that retains delimiters or a reading mechanism that preserves line terminators.
4. **Need to handle multiple Unicode linebreak types:** consider regex `\R` and check requirements regarding trailing empty elements.
5. **Need to parse according to a specific standard** (multiline CSV inside quoted fields, HTTP headers, multiline logs): do not assume every line break is a record boundary; use a standards-compliant parser.

A typical example: if you need to check how many **non-blank lines** a configuration has, you can write:

```java
String config = "# sample\r\nhost=localhost\n\r\nport=8080\n";
long nonBlankLines = config.lines()
        .filter(line -> !line.isBlank())
        .count();

System.out.println(nonBlankLines); // 3
```

This is a task of **counting non-blank visible lines**, not parsing the semantics of a configuration file. If you need to read keys/values, comments, or escapes according to a format specification, you must use the corresponding parser.

## 9. Practice Exercises with Answers

**Exercise 1.** Predict the number of elements in the three Streams:

```java
"A\r\nB".lines().count();
"A\n\nB".lines().count();
"A\n".lines().count();
```

Answers respectively: **2**, **3**, **1**. CRLF is a single line terminator; two consecutive LFs create a blank line in between; a trailing LF does not add a new line.

**Exercise 2.** How many lines does `"\r\n\n".lines()` have and what is the content of each line?

Answer: **2 lines**, both are `""`. CRLF creates the first empty line; the following LF creates the second empty line.

**Exercise 3.** Given `String text = "x\r\ny\n";`, retrieve a list of lines without terminators.

```java
import java.util.List;

String text = "x\r\ny\n";
List<String> values = text.lines().toList();
// ["x", "y"]
```

**Exercise 4.** If you want to keep the empty element **after the trailing LF** to distinguish `"A"` from `"A\n"`, which approach should you use?

A simple way when the data matches the linebreaks recognized by regex:

```java
String[] values = "A\n".split("\\R", -1);
// ["A", ""]
```

When you must preserve the exact original CR/LF/CRLF for re-export, `split("\\R", -1)` still **does not preserve the delimiter type**: you must use a solution that stores the delimiters as well.

**Exercise 5.** Determine how many non-empty lines a string has after stripping leading/trailing whitespace.

```java
String text = "A\n   \r\n B \n";
long count = text.lines()
        .map(String::strip)
        .filter(s -> !s.isEmpty())
        .count();
// 2
```

**Exercise 6.** Compare on the string `"A\u2028B"`: do `lines()` and `split("\\R")` produce the same number of elements?

Answer: **no**. `lines()` produces one line; `split("\\R")` produces two elements, because regex `\R` recognizes Unicode LINE SEPARATOR (`U+2028`).

## 10. Key Takeaways

- **LF = `\n`**, **CR = `\r`**, **CRLF = `\r\n`**; CRLF consists of two characters but is treated as a single line terminator.
- **`String.lines()` from Java 11** creates a `Stream<String>` in line order, automatically removing LF/CR/CRLF from each element.
- **Empty string → 0 lines; a single terminator alone → 1 empty line; a trailing terminator after content → does not produce an extra final line**.
- **Leading/middle blank lines are preserved**, unless you explicitly filter them out with Stream.
- **`split("\\R")` recognizes more Unicode linebreaks; `split("\\R", -1)` keeps empty elements after a trailing terminator**, but does not preserve the exact line-terminator type.
- **`System.lineSeparator()` is a choice of line ending when generating text** for the current platform, and does not restrict which terminators `String.lines()` recognizes.
- If you must reconstruct text **exactly**, including trailing newlines and mixed CR/LF/CRLF, keep the original source or store the delimiters as well.

Official references: [Java SE 17 — String.lines()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#lines()), [Java SE 17 — Pattern (\\R)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html), [Java SE 17 — Files.lines()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path)).
