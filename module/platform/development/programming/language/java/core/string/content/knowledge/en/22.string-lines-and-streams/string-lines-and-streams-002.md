# Empty Strings and Trailing Line Endings with String.lines() in Java



## 1. Why Are Line Counts Easy to Misunderstand?

In Java, `String.lines()` (available since Java 11) creates a `Stream<String>` containing the **text lines** of a string. Each element is the content of a line **without the line terminator**. However, an **empty string**, an **empty line**, and a **string with a trailing newline character** are not the same three cases.

Consider three inputs:

```text
""          string with 0 characters
"Java\n"    word Java, followed by one LF newline character
"Java\n\n"  word Java, followed by two consecutive LF characters
```

In the snippet above, `\n` is the representation of a newline character in a Java string literal, not the two characters backslash and letter `n`.

Different results:

- `"".lines()` produces **0 elements**: there are no lines.
- `"Java\n".lines()` produces **1 element** `"Java"`: the final line terminator does not create an extra empty line on its own.
- `"Java\n\n".lines()` produces **2 elements**: `"Java"` and `""`; the second LF terminates an empty line after `Java`.

The most important takeaway of this lesson: **`String.lines()` does not automatically append an empty string just because the input ends with a newline.** However, when there are **multiple consecutive line terminators**, they still represent real empty lines.

## 2. Edge-Case Table

To see clearly, each line value below is placed in double quotes. The notation `[]` means **no elements**, while `[""]` means **one element that is the empty string**.

| Input string (Java literal) | Elements from `lines().toList()` | Line count |
| --- | --- | ---: |
| `""` | `[]` | 0 |
| `"Java"` | `["Java"]` | 1 |
| `"Java\n"` | `["Java"]` | 1 |
| `"Java\n\n"` | `["Java", ""]` | 2 |
| `"\n"` | `[""]` | 1 |
| `"\n\n"` | `["", ""]` | 2 |
| `"\r\n"` | `[""]` | 1 |
| `"one\n\ntwo"` | `["one", "", "two"]` | 3 |
| `"one\r\ntwo\r\n"` | `["one", "two"]` | 2 |
| `"first\nsecond"` | `["first", "second"]` | 2 |

Explanation of two special cases:

- `"\n"` is an **empty line with a terminator**: the stream contains one element `""`. Meanwhile, `""` contains no lines, so the stream is empty.
- `"Java\n\n"` consists of the line `Java` terminated by the first LF, followed by an **empty line** terminated by the second LF. The second LF is also the final terminator, so no third empty line is produced.

**The number of newline characters does not always equal the number of lines.** With `"Java\n"` there is one LF and one line; with `"Java"` there is no LF yet still one line. With an empty string there are 0 lines.

## 3. Complete Java 17+ Program

Save the following code as `StringLinesEdgeCases.java`:

```java
import java.util.Arrays;
import java.util.List;

public class StringLinesEdgeCases {
    private static void show(String label, String input) {
        List<String> visible = input.lines()
                .map(line -> "\"" + line + "\"")
                .toList();

        System.out.println(label + " => count=" +
                visible.size() + ", lines=" + visible);
    }

    public static void main(String[] args) {
        show("empty", "");
        show("no terminator", "Java");
        show("one trailing LF", "Java\n");
        show("two trailing LF", "Java\n\n");
        show("only LF", "\n");
        show("two LF", "\n\n");
        show("only CRLF", "\r\n");
        show("mixed blanks", "one\n\ntwo");
        show("CRLF final", "one\r\ntwo\r\n");

        String[] byDefault = "Java\n".split("\\R");
        String[] keepTrailing = "Java\n".split("\\R", -1);
        System.out.println("split default count: " + byDefault.length);
        System.out.println("split keep count: " + keepTrailing.length);
        System.out.println("split keep last empty: " +
                keepTrailing[1].isEmpty());
        System.out.println("empty split count: " +
                "".split("\\R", -1).length);

        String original = "one\r\ntwo\r\n";
        String reconstructed = String.join("\n",
                original.lines().toList());
        System.out.println("reconstructed equals original: " +
                reconstructed.equals(original));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac StringLinesEdgeCases.java
java StringLinesEdgeCases
```

Expected output:

```text
empty => count=0, lines=[]
no terminator => count=1, lines=["Java"]
one trailing LF => count=1, lines=["Java"]
two trailing LF => count=2, lines=["Java", ""]
only LF => count=1, lines=[""]
two LF => count=2, lines=["", ""]
only CRLF => count=1, lines=[""]
mixed blanks => count=3, lines=["one", "", "two"]
CRLF final => count=2, lines=["one", "two"]
split default count: 1
split keep count: 2
split keep last empty: true
empty split count: 1
reconstructed equals original: false
```

The `show` method wraps each line's content in double quotes so we can distinguish `[]` from `[""]`. This is just a visual aid for learning; `String.lines()` itself returns the raw lines without adding quotes.

`toList()` is the `Stream.toList()` method available in Java 16+, so the program runs on Java 17. Prior to Java 16, you can collect into a list with `collect(Collectors.toList())`. The core API of this lesson, `String.lines()`, has been available since Java 11.

### From Lines to Split Fields

Here you only need to know that `lines()` does not create an extra line after a trailing newline, whereas `split("\\R", -1)` can retain an empty field after the delimiter. `split("\\R")` discards trailing empty fields by default; for the empty string `""` itself, `split` still returns one empty element, whereas `lines()` returns an empty stream. Positive `limit` behavior and the Unicode linebreak set belong to the lesson **Differences Between lines and split with limit**.

## 4. Distinguishing Empty Strings, Empty Lines, and Whitespace-Only Lines

These three concepts are commonly checked with different APIs:

- **Empty input string:** `input.isEmpty()` returns `true` when the string length is 0.
- **Empty line:** for each `line` from `input.lines()`, `line.isEmpty()` returns `true` if the line has 0 characters.
- **Blank line:** `line.isBlank()` returns `true` if the line consists only of whitespace according to Java's definition, or is empty.

Example:

```java
String text = "first\n \n\nlast\n";

long allLines = text.lines().count();
long emptyLines = text.lines()
        .filter(String::isEmpty)
        .count();
long blankLines = text.lines()
        .filter(String::isBlank)
        .count();

System.out.println(allLines);   // 4
System.out.println(emptyLines); // 1
System.out.println(blankLines); // 2
```

Explanation: the lines are `"first"`, `" "` (a single space), `""`, and `"last"`. The line `" "` is **blank** but not **empty**. The final `\n` does not create a fifth empty line.

**Note:** each call to `text.lines()` in the example creates a new stream. A `Stream` that has already run a terminal operation such as `count()` is consumed; do not call `count()` again on the same stream object.

## 5. What If You Need to Preserve the Exact Trailing Newline?

`String.lines()` returns the **line contents** and strips each line's terminator. After splitting, you can no longer tell from the list of lines whether the original input used `\n`, `\r`, or `\r\n`, nor can you always tell whether there was a trailing newline at the end.

Example:

```java
String original = "one\r\ntwo\r\n";
String reconstructed = String.join("\n",
        original.lines().toList());

System.out.println(reconstructed.equals(original)); // false
```

`reconstructed` is `"one\ntwo"`; it no longer has CRLF and no longer has a terminator after `two`. Therefore, **do not use `String.join("\n", text.lines().toList())` assuming it restores the exact original text**.

If you only want to know whether the original string ends with one of the three terminator types recognized by `String.lines()`, check the original string directly **before iterating over lines**:

```java
boolean endsWithLineTerminator =
        text.endsWith("\n") || text.endsWith("\r");
```

That expression also returns `true` for CRLF, because `"\r\n"` ends with `"\n"`. If you want to distinguish all three types accurately to record them:

```java
String terminal;
if (text.endsWith("\r\n")) {
    terminal = "\r\n";
} else if (text.endsWith("\n")) {
    terminal = "\n";
} else if (text.endsWith("\r")) {
    terminal = "\r";
} else {
    terminal = "";
}
```

This only checks the **trailing terminator**; it does not store all the different terminators inside the string. If you must preserve exact bytes, preserve mixed line-ending formats, or reconstruct text without losing a single character, keep the original source or use a delimiter-preserving parser; do not rely solely on `lines()`.

### 9.1. Input Parsing or Record-Processing Cases

For ordinary text documents, a trailing newline usually just closes the last line. For a protocol or format where **the part after the final delimiter** is considered an empty record/field, the business logic may need to keep this empty element; in that case, splitting with `split("\\R", -1)` (after confirming the terminator set is appropriate) fits the “delimiter-separated fields” model better.

For example, the input `"A\nB\n"` has:
- Two lines according to `String.lines()`: `A` and `B`.
- Three elements according to `split("\\R", -1)`: `A`, `B`, and `""`.

Both results have their own rationale. Decide in advance whether the final terminator represents a **line ending** or a **delimiter creating an empty field** in your specific data format.

## 6. Self-Check Exercises

Before running the code, predict the results of the expressions:

| Expression | Result |
| --- | ---: |
| `"".lines().count()` | `0` |
| `"\r".lines().count()` | `1` |
| `"\r\n".lines().count()` | `1` |
| `"x\r\n".lines().count()` | `1` |
| `"x\r\n\r\n".lines().count()` | `2` |
| `"x\n\n\ny".lines().count()` | `4` |
| `" x \n".lines().findFirst().orElse("?")` | `" x "` |
| `"x\n".split("\\R", -1).length` | `2` |

Extra practice: write a method that takes an input string and reports the total number of lines, the number of empty lines, the number of whitespace-only lines, and a boolean indicating whether the input ends with LF or CR. Test it with `""`, `"\n"`, `"a\n"`, `"a\n\n"`, and `"a\r\nb\r\n"`.

## 7. Key Takeaways

- **`String.lines()` on an empty string yields 0 lines**, whereas a string consisting solely of one LF yields 1 empty line.
- A **single trailing terminator** does not produce an extra empty element; **two consecutive terminators** preserve the empty line between them.
- `String.lines()` recognizes `\n`, `\r`, and `\r\n`; the regex `\R` recognizes a broader set of linebreaks.
- **`split("\\R", -1)` keeps the trailing empty element**, unlike `String.lines()`'s line-splitting behavior; on an empty string, `split` produces one empty element.
- `isEmpty()` and `isBlank()` serve two different definitions of empty lines and blank lines.
- `String.lines()` strips line terminators; if you need to know or preserve the trailing newline and CR/LF/CRLF style, you must retain that information from the original input.
