# Blank Lines, Trailing Whitespace, and Newlines in Java 17 Text Blocks

When writing multiline strings with **text blocks** (`"""`) in Java 17, the formatting of the source code directly affects the generated `String` value. A blank line can produce an extra newline character; trailing whitespace at the end of a line is usually stripped; and the position of the closing `"""` determines whether the string ends with a newline.

These differences are especially important for **HTML, SQL, JSON, CSV, emails, text formatting, configuration files, and protocols sensitive to spaces/newlines**. If you only inspect output via `System.out.println`, it is easy to miss a single extra or missing space or `\n` character.

**Text blocks are a standard feature in Java 17**, standardized since Java 15 (JEP 378). The examples below compile normally with JDK 17 without `--enable-preview`.

## 1. Review of text block syntax

A text block starts with three double quotes and **must have a line terminator after the opening delimiter**:

~~~java
String message = """
        Hello,
        Java 17!
        """;
~~~

The resulting string is equivalent to:

~~~java
String message = "Hello,\nJava 17!\n";
~~~

In the example, the indentation used to format the Java code **does not automatically become** leading spaces in the string; Java strips incidental indentation (*incidental indentation*) before producing the `String`.

The following syntax is **invalid** because content appears immediately after the opening delimiter instead of a line break:

~~~java
// Invalid text block syntax:
// String message = """Hello!""";
~~~

If the content is just a single line, you can use a regular string literal:

~~~java
String message = "Hello!";
~~~

Or still use a text block with the opening delimiter on its own line:

~~~java
String message = """
        Hello!""";
~~~

Both of these last two cases have the content `Hello!` and **no** trailing newline character.

## 2. Three steps Java uses to process text block content

You can understand how Java 17 builds a `String` from a text block in three stages:

1. **Normalize line terminators:** physical line terminators in source code `CRLF` (`\r\n`) and `CR` (`\r`) are normalized to `LF` (`\n`) in the text block content.
2. **Strip incidental whitespace:** Java determines the common indentation to remove, and removes trailing whitespace at the end of each line according to text block rules.
3. **Interpret escape sequences:** such as `\n`, `\t`, `\s`, and `\` used for line continuation are processed after the whitespace removal step.

**The processing order is very important.** In particular, `\s` is the two-character sequence `\` and `s` during the whitespace removal phase; at the escape interpretation phase, it becomes **an actual space**. Therefore `\s` can preserve trailing whitespace that directly typed spaces cannot.

Example:

~~~java
String text = """
        Java\s
        17
        """;
~~~

The resulting value is:

~~~text
"Java \n17\n"
~~~

In the string above, right before the first `\n` there is **one U+0020 space**, produced by `\s`.

In this document, when showing exact string values, we use the notation:

| Symbol in explanations | Meaning |
| --- | --- |
| `\n` | One LF newline character (U+000A) |
| `\r` | One carriage return character (U+000D) |
| `\t` | One tab character (U+0009) |
| `␠` | One U+0020 space; visual marker only, not in the string |
| `⏎` | Line break position; visual marker only |

When writing `"A\nB\n"` in explanations, that is **the Java string literal notation for the string value**, not a claim that the text block contains the two printable characters `\` and `n`.

## 3. Trailing newline: depends on closing `"""` placement

This is the first distinction to master when writing text blocks.

### 3.1. Closing delimiter on its own line: usually has trailing `\n`

~~~java
String withFinalNewline = """
        alpha
        beta
        """;
~~~

Value:

~~~java
"alpha\nbeta\n"
~~~

There are two `\n` characters: one after `alpha`, one after `beta`. The final `\n` appears because the line containing `beta` ends before the line holding the closing `"""`.

### 3.2. Closing delimiter immediately after content: no trailing `\n` added

~~~java
String withoutFinalNewline = """
        alpha
        beta""";
~~~

Value:

~~~java
"alpha\nbeta"
~~~

Here, `beta` sits on the same line as the closing `"""`. There is no physical line terminator between `beta` and the closing delimiter, so the string has no trailing `\n`.

### 3.3. Comparing programmatically

~~~java
public class ClosingDelimiterDemo {
    public static void main(String[] args) {
        String a = """
                alpha
                beta
                """;

        String b = """
                alpha
                beta""";

        System.out.println(a.equals("alpha\nbeta\n")); // true
        System.out.println(b.equals("alpha\nbeta"));    // true
        System.out.println(a.length()); // 11
        System.out.println(b.length()); // 10
    }
}
~~~

Save as `ClosingDelimiterDemo.java` and run:

~~~bash
javac --release 17 -encoding UTF-8 ClosingDelimiterDemo.java
java ClosingDelimiterDemo
~~~

Output:

~~~text
true
true
11
10
~~~

In the example above, the length differs by exactly one character because string `a` has the extra trailing `\n`.

### 3.4. Business significance of the trailing newline

| Situation | Usually needed? | How to write |
| --- | --- | --- |
| Text files following the convention of ending every line with LF | Trailing `\n` | Place closing `"""` on a new line |
| Short messages requiring exact string match | Possibly no trailing `\n` | Place closing `"""` right after content |
| SQL sent to JDBC | Often both with/without trailing LF are accepted by parsers | Choose consistently, verify in string comparisons |
| Signed payloads, checksums, snapshot tests | Every byte matters | Specify final character and charset explicitly |

**Do not casually call `strip()` just to "remove an extra newline"**: `strip()` removes both leading and trailing whitespace across the *entire string*, which can erase meaningful characters. If the contract only requires omitting a single trailing `\n`, handle it intentionally or place the closing delimiter at the right position in source code.

## 4. Blank lines inside a text block

A **blank line** is a line with no visible content between two line terminators. When you write an actual blank line inside a text block, that line still contributes to the string value.

~~~java
String paragraph = """
        First paragraph.

        Second paragraph.
        """;
~~~

Equivalent value:

~~~java
"First paragraph.\n\nSecond paragraph.\n"
~~~

Two consecutive `\n` characters between two paragraphs produce one blank line. To create **two blank lines** between them, three consecutive `\n` characters are needed.

### 4.1. A blank line differs from a space

The following values are not equal:

~~~java
String blankLine = "A\n\nB";
String spaceLine = "A\n \nB";

System.out.println(blankLine.equals(spaceLine)); // false
~~~

The second value has a space on the middle line. However, if you **type spaces directly on a blank line in text block source**, whitespace processing may strip them. Therefore, do not rely on invisible spaces to represent significant data.

### 4.2. A blank line containing a real space when needed

If a format strictly requires a line containing one space, you can use the `\s` escape on that line:

~~~java
String lineWithSpace = """
        A
        \s
        B
        """;
~~~

Value:

~~~java
"A\n \nB\n"
~~~

The middle line is no longer zero-length: it contains exactly one space character. Using `\s` lets readers see an intentional space and prevents editors from stripping it.

### 4.3. Confusion when displaying blank lines

~~~java
String content = """
        A

        B
        """;

System.out.print(content);
~~~

Console displays:

~~~text
A

B
~~~

However, looking at a terminal makes it hard to distinguish a string **with a trailing LF** from one **without a trailing LF**, since both can look identical visually. When exact inspection is needed, use `equals()`, `length()`, or an escape-visualization helper as shown later; do not judge spacing by eye on a terminal.

## 5. Trailing whitespace on lines is usually stripped

A defining feature of text blocks is how Java handles **trailing whitespace** in source. Spaces and tabs typed directly at the end of a line can be removed when the text block becomes a `String`.

For example, the meaning of:

~~~java
String text = """
        left
        right
        """;
~~~

is:

~~~java
"left\nright\n"
~~~

If an author adds several spaces after `left` before pressing Enter, Java still strips trailing whitespace during normal text block processing. Therefore, you should not try to produce `"left  \n"` by typing two invisible spaces after `left`.

**Practical impact:**

- In Markdown, two trailing spaces sometimes signify a forced line break.
- In fixed-width column formats (*fixed-width*), trailing spaces in a field can be data.
- In emails or text-based protocols, trailing whitespace can affect byte comparisons, signatures, or checksums.
- In tests, expected strings can fail if the author assumes invisible trailing spaces were retained.

If trailing spaces are required, use the `\s` escape.

## 6. Preserving trailing spaces with `\s`

In Java 17, `\s` is an escape representing **one ordinary space** (U+0020). This escape is valid in both string literals and text blocks.

~~~java
String text = """
        item:\s
        next
        """;
~~~

Result:

~~~java
"item: \nnext\n"
~~~

There is one space right after `:` and right before the LF character.

### 6.1. Preserving multiple spaces

~~~java
String twoSpaces = """
        value\s\s
        next
        """;

System.out.println(twoSpaces.equals("value  \nnext\n")); // true
~~~

Two `\s` escapes produce two spaces at the end of the line. This notation makes intent far clearer than placing two invisible spaces in source code.

### 6.2. Using `\s` to preserve spaces after a word

~~~java
String aligned = """
        code:\s\s
        17
        """;
~~~

Value:

~~~java
"code:  \n17\n"
~~~

Note that the space produced by `\s` **is not a newline character**. It is strictly U+0020. Newlines still come from physical line endings in the text block.

### 6.3. Tabs and spaces are not the same

Java has `\t` for tab U+0009; `\s` for space U+0020.

~~~java
String withTab = """
        A\tB
        """;

String withSpaces = """
        A\s\s\s\sB
        """;

System.out.println(withTab.equals(withSpaces)); // false
~~~

Although they may look similar in a terminal, the underlying data differs. For fixed-width formats, specify whether tabs or spaces are required rather than relying on editor display width.

### 6.4. Why does `\s` survive whitespace removal?

In source code, `value\s` ends with the character `s`, not an actual space. Java removes trailing whitespace **before** interpreting escapes. After the whitespace removal step, `\s` is converted into a space in the resulting string.

This ordering explains why writing `\s` at the end of a line works, whereas typing a literal space at the end of a line does not.

## 7. Common indentation vs. intentional indentation

Leading indentation is normally added so Java code is readable. Text blocks remove that **incidental** indentation while preserving **meaningful** indentation.

~~~java
String text = """
        first
          second
        third
        """;
~~~

Equivalent value:

~~~java
"first\n  second\nthird\n"
~~~

The two spaces before `second` represent an **intentional indentation offset** relative to `first` and `third`, so they are preserved.

### 7.1. Closing delimiter position also affects indentation

Consider:

~~~java
String normal = """
        A
          B
        """;
~~~

Value:

~~~java
"A\n  B\n"
~~~

But if you move the closing delimiter closer to the left margin:

~~~java
String padded = """
        A
          B
    """;
~~~

Value:

~~~java
"    A\n      B\n"
~~~

When the closing delimiter sits on its own line, its indentation participates in determining the incidental indentation to remove. In the second example, the closing delimiter is indented by only four spaces, so each content line keeps four extra spaces compared to the first example.

Therefore, **changing the position of the closing `"""` can alter the string content**, not just source formatting. Keep this in mind when an IDE auto-formats code or when moving blocks of code.

### 7.2. Blank lines cannot be used to preserve indentation

Blank or whitespace-only lines are treated specially when computing incidental indentation. Typing many spaces on a blank line is not a reliable way to create indentation in the resulting data.

If you need a "blank" line containing spaces, use `\s` as shown in section 4; if you need special indentation for a content line, express the relative spacing explicitly.

## 8. Line-ending normalization to LF

Operating systems and editors may store line endings in source files in several ways:

| Line ending in source | Typical char/sequence | Text block content after normalization |
| --- | --- | --- |
| LF | `\n` | `\n` |
| CRLF | `\r\n` | `\n` |
| CR | `\r` | `\n` |

Consequently, Java 17 text blocks produce content with LF newline characters, even when the source file is saved with CRLF on Windows.

For example, with a text block containing two lines and the closing delimiter on its own line:

~~~java
String text = """
        A
        B
        """;
~~~

The expected value is:

~~~java
"A\nB\n"
~~~

This makes multiline strings from text blocks less dependent on the OS's physical line endings.

### 8.1. If an external system strictly requires CRLF

Some protocols require `\r\n` sequences. Do not assume a text block automatically uses CRLF when running on Windows. Perform conversion explicitly at the **output boundary**:

~~~java
String message = """
        Line 1
        Line 2
        """;

String withCrlf = message.replace("\n", "\r\n");

System.out.println(withCrlf.equals("Line 1\r\nLine 2\r\n"));
// true
~~~

This conversion works when the input is already normalized to LF, like this text block. If input data might already contain CRLF, normalize it before replacing to avoid turning `\r\n` into `\r\r\n`.

When writing files, specify the charset explicitly:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

String content = """
        Line 1
        Line 2
        """;

Files.writeString(
        Path.of("output.txt"),
        content,
        StandardCharsets.UTF_8
);
~~~

This writes the existing LF characters in `content` encoded as UTF-8; `Files.writeString` does not automatically convert these LFs to CRLF just because the OS is Windows.

### 8.2. Distinguishing data newlines from display newlines

`System.out.println(text)` always appends a newline **after the entire printed string**. If `text` already has a trailing LF, that call can make it look like there is an extra blank line.

~~~java
String text = """
        Hello
        """;

System.out.println(text);
~~~

`text` is already equivalent to `"Hello\n"`; `println` appends another line terminator from the print method, so the output can appear to have a blank line.

When you want to see the exact text block content without the print API adding a newline, use:

~~~java
System.out.print(text);
~~~

The distinction here is between **the `String`'s data** and **the character added by the print call**.

## 9. Joining two source lines into one string line using `\`

Sometimes you want a line break in **Java code** for readability without a line break in the **String value**. In Java 17 text blocks, placing a `\` right before a line terminator expresses **line continuation**.

~~~java
String joined = """
        Hello, \
        Java 17!
        """;
~~~

Value:

~~~java
"Hello, Java 17!\n"
~~~

The trailing `\` on the first line ensures the physical newline between `Hello, ` and `Java 17!` **does not appear** in the result.

Compare:

~~~java
String separate = """
        Hello,
        Java 17!
        """;

String joined = """
        Hello, \
        Java 17!
        """;

System.out.println(separate.equals("Hello,\nJava 17!\n")); // true
System.out.println(joined.equals("Hello, Java 17!\n"));    // true
~~~

### 9.1. Spaces before `\` still matter

In `Hello, \`, there is a space between the comma and `\`. That space comes before the escape, not as trailing whitespace that gets removed, so the result retains `Hello, Java 17!`.

If written as:

~~~java
String joined = """
        Hello,\
        Java 17!
        """;
~~~

Then the result is:

~~~java
"Hello,Java 17!\n"
~~~

There is no space between `Hello,` and `Java`.

### 9.2. `\` line continuation vs. `\n` line addition

| Syntax inside text block | Effect |
| --- | --- |
| Pressing Enter to end a line | Produces LF in string |
| Writing `\n` at a position | Produces an additional LF character at the escape |
| Writing `\` right before line end | Does not produce LF at that line end |
| Writing `\s` | Inserts a regular space |

Clearly distinguish these two opposite roles:

- `\n` **adds** a newline character to the string.
- `\` line continuation **removes** the newline from the source line ending.

A common mistake is putting `\n` at the end of a line that already has a physical line break, accidentally creating **two consecutive LFs**.

~~~java
String text = """
        A\n
        B
        """;

System.out.println(text.equals("A\n\nB\n")); // true
~~~

When you want a blank line between `A` and `B`, it is usually much clearer to leave **an actual blank line** in the text block (section 4), rather than appending `\n` at the end of a line and also pressing Enter.

### 9.3. Do not add characters after the line-continuation backslash

For `\` line continuation to work, it must stand directly before the escaped line terminator. If there is invisible whitespace after `\`, it is no longer the intended line-continuation escape and may cause a syntax error or unexpected output.

Configure your formatter and editor rules to make trailing whitespace visible, and write tests for strings where newlines are significant.

## 10. Combining blank lines, `\s`, and closing delimiters in practical examples

Consider a Markdown content sample:

~~~java
String markdown = """
        # Release notes

        Version: 17

        - Fixed bug
        - Added feature
        """;
~~~

The result contains the lines:

~~~text
# Release notes
[blank]
Version: 17
[blank]
- Fixed bug
- Added feature
[trailing LF]
~~~

The labels in square brackets in the diagram above are explanatory only and are not part of the actual string.

If you want to preserve two Markdown spaces at the end of a line to create a hard line break:

~~~java
String markdown = """
        Line one\s\s
        Line two
        """;
~~~

Value:

~~~java
"Line one  \nLine two\n"
~~~

The two trailing spaces on `Line one` are created intentionally. If you merely typed two literal spaces at the end of the source line, the text block result could lose them.

### 10.1. Multiline SQL

~~~java
String sql = """
        SELECT id, full_name
        FROM customers
        WHERE status = ?
        ORDER BY id
        """;
~~~

The value has an LF after every line, including `ORDER BY id`. This is a readable way to format SQL in Java 17 code. When using `PreparedStatement`, `?` is a parameter marker for binding values; never concatenate user data directly into SQL via string interpolation.

If a library or snapshot test requires SQL **without a trailing LF**, place the closing `"""` immediately after the last line:

~~~java
String sql = """
        SELECT id, full_name
        FROM customers
        WHERE status = ?
        ORDER BY id""";
~~~

The two variables above are not equal according to `String.equals()` because the first has a trailing LF. In test suites that assert verbatim SQL strings, this difference must be accounted for.

### 10.2. Column-aligned content

~~~java
String report = """
        ITEM      QTY
        Apple       2
        Orange      10
        """;
~~~

Whitespace **between** tokens is preserved as meaningful content after Java strips common indentation; text blocks do not collapse consecutive internal spaces into a single space. Only incidental leading whitespace and trailing whitespace require attention.

### 10.3. A combined example with an exact value

~~~java
String payload = """
        BEGIN\s
       
        DATA=17\s\s
        END""";
~~~

In the source above, the line between `BEGIN` and `DATA=17` is left blank; readers should not rely on invisible spaces there. The value to understand is:

~~~java
"BEGIN \n\nDATA=17  \nEND"
~~~

- After `BEGIN` there is **one space** thanks to `\s`.
- Between `BEGIN` and `DATA=17` there is **one blank line**.
- After `DATA=17` there are **two spaces** thanks to `\s\s`.
- After `END` there is **no** trailing LF because the closing delimiter is on the same line.

If the string is used for digital signing or byte comparison, all four details affect the outcome.

## 11. How to observe hidden characters accurately

### 11.1. Compare with a standard string literal

The simplest check is:

~~~java
String text = """
        A

        B
        """;

System.out.println(text.equals("A\n\nB\n")); // true
~~~

This check verifies both the number of blank lines and the trailing newline simultaneously.

### 11.2. Display characters in visible form

Create file **`TextBlockInspector.java`**:

~~~java
public final class TextBlockInspector {

    private TextBlockInspector() {
    }

    static String visible(String value) {
        return value
                .replace(" ", "␠")
                .replace("\t", "\\t")
                .replace("\r", "\\r")
                .replace("\n", "\\n\n");
    }

    public static void main(String[] args) {
        String text = """
                A\s\s

                B
                """;

        System.out.print(visible(text));
        System.out.println("length=" + text.length());
    }
}
~~~

Run with Java 17:

~~~bash
javac --release 17 -encoding UTF-8 TextBlockInspector.java
java TextBlockInspector
~~~

Expected output:

~~~text
A␠␠\n
\n
B\n
length=7
~~~

The string has seven characters: `A` (1), two spaces (2), two LFs before `B` (2), `B` (1), and the trailing LF (1). In the output, `\n` is printed as two visible characters, while the actual LF advances to the next display line.

**Note:** `visible()` above is a demonstration utility, not a general escaping format: a source string containing an actual `␠` character would be hard to tell apart from a replaced space. To compare protocol bytes, inspect the byte array with a hex tool or dedicated test suite.

### 11.3. Counting LF characters

~~~java
String text = """
        one

        two
        """;

long count = text.chars()
        .filter(c -> c == '\n')
        .count();

System.out.println(count); // 3
~~~

Counting LFs reveals blank lines and trailing newlines regardless of how a terminal renders output.

### 11.4. Understanding the limitation of `String.lines()`

`String.lines()` splits a string into a stream of content lines; it is not a tool that preserves every line delimiter intact. For instance:

~~~java
String text = "A\nB\n";

System.out.println(text.lines().toList()); // [A, B]
~~~

The list result cannot tell you whether there was originally a trailing LF just by looking at the two elements. When the goal is checking **exact original data**, use `equals()`, character counts, or `split("\n", -1)` to preserve an empty trailing element:

~~~java
String text = "A\nB\n";

String[] pieces = text.split("\n", -1);
System.out.println(pieces.length); // 3
System.out.println(pieces[2].isEmpty()); // true
~~~

This technique is useful in unit tests for newline-sensitive serializers, parsers, or templates.

## 12. Common mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Text block fails to compile | Content appears immediately after opening `"""` with no line terminator | Break the line right after the opening delimiter |
| String has an unwanted trailing LF | Closing `"""` is placed on its own line | Move closing delimiter right after the last content character |
| String is missing a trailing LF | Closing delimiter is on the same line as the last content | Move closing delimiter to its own line or add LF intentionally |
| Two lines split when one line was wanted | Physical newline exists between them | Use `\` line continuation or a single-line string |
| Two lines run together with no space | Used `\` line continuation without a needed space | Add a space before `\` or restructure the text |
| Trailing spaces on a line disappear | Trailing whitespace was stripped by Java | Use `\s` for each space you want to keep |
| Extra blank line appears | An actual blank line exists or `\n` was added on a line ending with a newline | Check string with `equals`, remove redundant newlines |
| String gets unwanted indentation | Closing delimiter was moved left or indentation is uneven | Check common indentation and closing delimiter position |
| Wanted CRLF on Windows but got LF | Text blocks normalize line endings to LF | Convert intentionally at the output boundary |
| `println` adds a big gap at the end | String already ends with LF, and `println` adds another line terminator | Use `print` or control trailing LF intentionally |
| Snapshot test fails even though screen output looks identical | Differs in spaces, tabs, or newlines | Inspect length, character codes, escapes, or raw bytes |
| Editor automatically deletes trailing spaces | Literal spaces are fragile at the ends of source lines | Express significant whitespace using `\s` |

For byte-sensitive text block content, avoid casually applying cleanup calls like `trim()`, `strip()`, or `stripTrailing()` after every string creation. Those methods serve specific purposes and can strip meaningful spaces and needed line terminators.

## 13. Practice exercises

### Exercise 1 — Determine the trailing newline

Given two text blocks:

~~~java
String first = """
        A
        B
        """;

String second = """
        A
        B""";
~~~

Write the equivalent regular string literals, compute `length()`, and explain why the two strings differ even though the visible lines are both `A` and `B`.

### Exercise 2 — Blank lines

Create a text block containing three headings `Title`, `Body`, and `Footer`, with **one blank line** between each pair; keep the trailing LF. Use `equals()` to compare against:

~~~java
"Title\n\nBody\n\nFooter\n"
~~~

Then replace each blank line with a line containing `\s` and observe the difference in the String value.

### Exercise 3 — Trailing whitespace

Write a text block with the exact value:

~~~java
"Name: An  \nAge: 17 \n"
~~~

Requirement: use `\s` to keep two spaces after `An` and one space after `17`, without placing invisible spaces directly at the ends of source lines.

### Exercise 4 — Adjusting the closing delimiter and indentation

Create a text block with two lines where the second line is indented **three spaces** deeper than the first. Move the closing delimiter from being aligned with the content lines to closer to the left margin. Use `equals()` to explain how the value changes.

### Exercise 5 — CRLF for protocol output

Create a text block with content:

~~~text
HEADER
BODY
END
~~~

with a trailing LF. Convert all LFs to CRLF before writing as UTF-8. Write an assertion verifying the converted string equals:

~~~java
"HEADER\r\nBODY\r\nEND\r\n"
~~~

### Exercise 6 — Suppressing a newline with line continuation

Use `\` at the end of a source line to produce the value:

~~~java
"Hello, Java 17!\n"
~~~

from a text block with `Hello,` and `Java 17!` on **two separate source lines**. Explain why one trailing LF is still retained even though the newline between the two parts of the sentence was removed.

## 14. Key rules to remember

A Java 17 text block is an ordinary `String` at runtime, but its value is derived from source code after **line-ending normalization**, **incidental/trailing whitespace handling**, and **escape sequence interpretation**.

- Real blank lines produce consecutive LFs; do not confuse a blank line with a line containing a space.
- A closing `"""` on its own line usually gives the string a trailing LF; placing it right after the final content omits that LF.
- Spaces/tabs typed directly at the end of a line may be stripped; use `\s` to retain meaningful spaces.
- Text blocks normalize physical CR/CRLF to LF; if a protocol requires CRLF, convert explicitly on output.
- `\` at the end of a source line suppresses that line's newline, whereas `\n` adds a newline character.
- When character-by-character accuracy matters, use equality checks, length checks, or byte inspection rather than relying on console appearance.

Mastering these rules lets you take advantage of text blocks' readability in Java 17 while keeping exact control over spaces, blank lines, and newlines in the final data.
