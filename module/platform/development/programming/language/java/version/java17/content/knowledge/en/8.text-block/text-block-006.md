# Quotes, Backslashes, and Triple-Quote Content in Java Text Blocks

A **text block** is a syntax for creating a `String` value from multiline content in Java source code. This feature was standardized in Java 15 (JEP 378), so it is a standard feature in **Java 17**. Text blocks are useful when writing SQL, JSON, HTML, templates, multiline messages, or text containing many quotes and backslashes.

An important point to remember is that a text block **is still an ordinary Java String**. It is not a raw string: escape sequences such as `\n`, `\t`, and `\\` are still processed; ordinary double quotes can be written directly, but a sequence of three consecutive double quotes must be handled so it is not mistaken for the closing text block delimiter.

Basic example:

```java
String message = """
        Hello,
        Java 17!
        """;
```

The value of `message` contains two lines of text and the trailing newline before the closing delimiter. There is no need to concatenate multiple strings with `+` or manually place `\n` after each line.

## 1. Text block syntax and the two delimiters

A text block starts with **three double quotes** `"""`, followed by a line terminator. The content sits between the opening delimiter and the closing delimiter; the closing delimiter is also three double quotes.

```java
String text = """
    First line content.
    Second line content.
    """;
```

Basic syntax rules:

1. The opening delimiter must be three consecutive double quotes.
2. After the opening delimiter there must be a line terminator. Spaces or tabs are allowed between the opening delimiter and the line break.
3. The closing delimiter is three consecutive double quotes.
4. Content is written between the two delimiters and produced as a `String` value.
5. Line terminators in the content are normalized to LF (`\n`) in the text block's value.

### 1.1. A newline after the opening delimiter is mandatory

This is a valid text block:

```java
String greeting = """
    Hello Java
    """;
```

The following **is not** valid text block syntax in Java 17:

```java
// Invalid: missing line terminator after opening delimiter.
// String greeting = """Hello Java""";
```

If you only need a short single-line string, use an ordinary string literal:

```java
String greeting = "Hello Java";
```

### 1.2. Closing delimiter placement affects the trailing newline

When the closing delimiter sits on its own line, the newline right before it is part of the content:

```java
String withFinalNewline = """
    Java
    17
    """;
```

The value is equivalent to a string with a newline after `17`:

```text
Java\n17\n
```

If you place the closing delimiter immediately after the last content character, there is no trailing newline:

```java
String withoutFinalNewline = """
    Java
    17""";
```

Equivalent value:

```text
Java\n17
```

This difference matters when generating HTTP payloads, writing files, comparing strings, computing checksums, or building protocol messages. Do not assume every text block automatically ends with a newline; check the closing delimiter's position.

## 2. Double quotes inside a text block

In a regular string literal, double quotes delimit the string, so you must write `\"` if you want one to appear as data:

```java
String regular = "The username is \"Lan\".";
```

Inside a text block, one or two double quotes can be written directly:

```java
String sentence = """
    The user said: "Hello".
    The attribute has the value "" (empty string).
    """;
```

The result preserves the quotes intact:

```text
The user said: "Hello".
The attribute has the value "" (empty string).
```

Because single double quotes do not terminate a text block, code is much easier to read when writing JSON, HTML, or prose containing quoted text.

### 2.1. Three consecutive double quotes are a special case

The closing delimiter of a text block is also three double quotes `"""`. Therefore, if content needs to contain three consecutive double quotes literally, you must **escape at least one quote** so the compiler does not mistake it for the closing delimiter.

The usual approach is placing a backslash before the first quote:

```java
String delimiterText = """
    The text block delimiter consists of three quotes: \"""
    """;
```

In the value of `delimiterText`, `\"""` in source code becomes three double-quote characters:

```text
The text block delimiter consists of three quotes: """
```

Here, `\"` is an escape sequence producing one double quote; the next two quotes are ordinary quote characters. All three become **content of the String**, not the end of the text block.

### 2.2. No need to escape every quote

Do not put `\` before every double quote simply out of habit from regular string literals:

```java
String json = """
    {
      "name": "Lan",
      "active": true
    }
    """;
```

In the text block example, the double quotes around keys and values are direct content. You only need to handle triple-quote sequences that could be parsed as a closing delimiter and backslashes that act as escapes.

## 3. Backslashes and escape sequences

Text blocks do not disable Java's escape rules. A backslash `\` begins an escape sequence; if you want the result to contain a literal backslash character, you usually must write **two backslashes in source code**: `\\`.

Common escape sequences:

| Written in source code | Character in String value |
| --- | --- |
| `\n` | LF newline. |
| `\r` | Carriage return. |
| `\t` | Tab. |
| `\b` | Backspace. |
| `\f` | Form feed. |
| `\"` | Double quote. |
| `\'` | Single quote. |
| `\\` | One backslash. |
| `\s` | One space, supported since Java 15. |
| `\` immediately before a line terminator | Joins source lines without putting that newline into the result. |

These escape sequences are processed when constructing the string value. Consequently, counting backslashes in **source code** and counting backslashes in the **resulting String** are two different things.

### 3.1. Windows paths

Windows paths often contain backslashes. In Java, you cannot write a single backslash before letters such as `t`, `n`, or `u` and expect it to stay literal, because certain combinations have special escape meanings.

```java
String path = """
    C:\\Users\\Public\\Documents\\notes.txt
    """;

System.out.println(path);
```

Printed value:

```text
C:\Users\Public\Documents\notes.txt
```

Each `\\` pair in source code produces one `\` in the value. This rule also applies to ordinary string literals.

If you do not want to worry about path escaping, you can use forward slashes (Java on Windows generally accepts such paths) or the `Path.of(...)` API to join path components for the platform:

```java
import java.nio.file.Path;

Path notes = Path.of(
        "C:/", "Users", "Public", "Documents", "notes.txt"
);
```

Text blocks serve to represent multiline strings; they do not replace the operating system's path-handling APIs.

### 3.2. Regular expressions (regex)

Regex frequently uses `\d`, `\w`, `\s`, `\.`. However, `\d` and `\w` are not valid Java escape sequences. If written directly in a text block, the compiler reports an illegal escape error.

Valid example:

```java
String regex = """
    \\d{4}-\\d{2}-\\d{2}
    """;
```

The value of `regex` is:

```text
\d{4}-\d{2}-\d{2}
```

Usage example:

```java
import java.util.regex.Pattern;

String dateRegex = """
    \\d{4}-\\d{2}-\\d{2}
    """;

boolean valid = Pattern.matches(dateRegex, "2026-11-15");
System.out.println(valid); // true
```

The reason for writing `\\d` in source code is that Java translates `\\` into a single backslash; the regex engine then receives `\d` and recognizes it as the digit class.

### 3.3. JSON with quotes and escapes inside values

JSON uses double quotes around keys and string values. Text blocks let you write JSON structure naturally, yet if **the JSON content needs an escaped quote inside a value**, you must ensure the backslash survives in the Java string:

```java
String json = """
    {
      "message": "He said: \\\"hello\\\"",
      "path": "C:\\\\temp"
    }
    """;
```

Explanation:

- `\\\"` in Java code produces two characters: a backslash and a double quote; JSON needs that pair to represent a quote inside a string value.
- `\\\\` in Java code produces two backslashes in the JSON content; JSON needs to escape its own backslash.
- Quotes surrounding keys and values do not need escaping in text block source.

This illustrates **two syntax layers**: Java processes escapes first, and then the JSON parser reads the resulting string. When working with real JSON, use a JSON library to serialize dynamic data; text blocks fit fixed sample JSON or illustrative payloads.

## 4. Text block's special escape sequence: `\s`

When creating multiline content, Java strips trailing whitespace at the end of lines to prevent accidental whitespace in source files from changing results. This is inconvenient if the content genuinely needs to end with one or more spaces.

Java 15 added the `\s` escape sequence to represent **one intentional space**:

```java
String padded = """
    key\s
    """;
```

The output has one space after `key` before the trailing newline:

```text
key ·\n
```

In the illustration above, `·` denotes a space; there is no dot character in the actual String.

### 4.1. Why not just press Space at the end of the line?

Example:

```java
String notPadded = """
    key
    """;
```

If you type ordinary spaces after `key` at the end of a source line, they are treated as trailing whitespace and not kept as meaningful content. To represent trailing spaces explicitly, use `\s`.

### 4.2. Distinguishing `\s` in Java from `\s` in regex

Two different contexts:

- In **text block source**, `\s` is a Java escape sequence producing one space.
- In **regex**, `\s` is the regex engine's whitespace character-class token.

If you want the resulting String to contain the characters `\s` for a regex engine, source code must say:

```java
String whitespaceRegex = """
    \\s+
    """;
```

If you write `\s+` directly in a text block, Java produces a space followed by `+`; the regex receives a literal space, not the `\s` token.

## 5. Joining lines without producing a newline

Text blocks retain newlines inside content. Sometimes, however, you want a line break in **source code** for readability while keeping the result on one line. You can place a line-continuation escape sequence: a backslash right before a line terminator.

```java
String oneLine = """
    This is a long sentence \
    split across two lines in source code.
    """;
```

Value of `oneLine`:

```text
This is a long sentence split across two lines in source code.\n
```

The backslash and the line terminator after it are omitted from the string. Leading whitespace on the second line is processed under incidental indentation rules before forming the final content.

**Note:** the backslash must sit right before the line terminator. If extra characters or spaces are placed after the backslash, it is no longer the intended line-continuation syntax. Check the exact character position in source.

Line continuation differs from:

```java
String twoLines = """
    First line
    Second line
    """;
```

In the second example, the newline between the two lines remains in the String value.

## 6. Leading whitespace and closing delimiter position

Text blocks are designed so content can be indented with source code structure without forcing the String value to retain all that whitespace. Java removes **incidental white space** using minimum indentation rules.

When calculating incidental indentation, the closing delimiter position plays an important role. The compiler determines the minimum indentation from non-blank content lines and the closing delimiter line if that line contains only whitespace before the delimiter; it then strips that indentation amount from the lines. Trailing whitespace on each line is also removed. Line endings are normalized before escapes are processed.

### 6.1. Common indentation example

```java
String html = """
        <html>
            <body>
                <h1>Hello</h1>
            </body>
        </html>
        """;
```

In the example above, the content has a common indentation of 8 spaces from the source margin; Java removes that common margin. Resulting value:

```text
<html>
    <body>
        <h1>Hello</h1>
    </body>
</html>
```

Relative indentation inside the HTML is preserved.

### 6.2. Moving the closing delimiter can change the output

```java
String indented = """
        first
            second
        """;

String preserved = """
        first
            second
""";
```

In `indented`, the closing delimiter is indented by 8 spaces, so the minimum removable indentation is 8. In `preserved`, the closing delimiter sits at column 0, so the minimum indentation is 0; the leading spaces on content lines are retained.

Illustrated values:

```text
indented:
first
    second

preserved:
        first
            second
```

Therefore, when generating content with meaningful indentation, such as sample code or YAML, **do not move the delimiter casually**. Source formatting and closing delimiter placement can change the output data.

### 6.3. Blank lines and trailing whitespace

Blank lines should not be relied upon to determine indentation the way a non-blank content line does. Whitespace at the end of every line is stripped; if you want a trailing space, represent it with `\s`. If content has blank lines to separate sections, place them visually and inspect the resulting value whenever whitespace is part of the format.

Example:

```java
String poem = """
        First line

        Third line
        """;
```

The blank line between the two lines of text remains a blank line in the result. You do not need to insert `\n` manually just to create an empty line.

## 7. Processing order: indentation before escapes

To understand edge cases, remember the specification's text block processing order:

1. **Identify delimiters and content.** Opening delimiter, closing delimiter, and body characters define the text block.
2. **Normalize line terminators.** Source line endings are normalized to LF within the content.
3. **Strip incidental white space.** Common indentation and trailing whitespace are removed.
4. **Interpret escape sequences.** For example `\\`, `\n`, `\s`, and line continuations are converted to their respective characters.

This order explains why ordinary trailing spaces are removed while `\s` still creates a trailing space: escapes are processed **after** trailing whitespace removal.

Additionally, Unicode escapes of the form backslash-u followed by four hexadecimal digits are processed during an earlier source-translation stage than tokenization and text block processing. Text blocks do not turn those sequences into raw data. When you need to include a literal sequence shaped like a Unicode escape, understand the JLS Unicode escape rules and verify the actual source; do not assume every backslash in a text block is only handled at the String escape stage.

## 8. Practical example: multiline SQL

Text blocks bring SQL queries close to the formatting commonly seen in database administration tools:

```java
String sql = """
        SELECT id, full_name, email
        FROM customer
        WHERE status = ?
          AND created_at >= ?
        ORDER BY created_at DESC
        """;
```

This can be used with `PreparedStatement`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.sql.Timestamp;

class CustomerRepository {
    private static final String FIND_ACTIVE = """
            SELECT id, full_name, email
            FROM customer
            WHERE status = ?
              AND created_at >= ?
            ORDER BY created_at DESC
            """;

    static void findActive(Connection connection, Instant from)
            throws SQLException {
        try (PreparedStatement statement =
                     connection.prepareStatement(FIND_ACTIVE)) {
            statement.setString(1, "ACTIVE");
            statement.setTimestamp(2, Timestamp.from(from));

            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    System.out.println(rows.getString("full_name"));
                }
            }
        }
    }
}
```

Text blocks only make SQL queries easier to read. They **do not automatically escape data, prevent SQL injection, or replace query parameterization**. Always use `?` placeholders with JDBC `setString` and `setTimestamp` methods.

## 9. Practical example: HTML with quotes and multiline content

```java
String html = """
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="UTF-8">
            <title>"Java 17"</title>
          </head>
          <body>
            <p class="message">Hello!</p>
          </body>
        </html>
        """;
```

Double quotes in HTML attributes and titles do not need escaping inside text block source. The HTML content preserves lines and can be passed to file-writing or HTTP APIs.

However, text blocks do not automatically encode dynamic data against XSS:

```java
String userName = request.getParameter("name");

// Unsafe if userName can contain arbitrary HTML/JavaScript:
String page = """
        <p>Hello, %s!</p>
        """.formatted(userName);
```

`formatted` only substitutes placeholders; it does not escape HTML. When inserting user data into HTML, use a library or template engine with context-appropriate encoding.

## 10. Are text blocks raw strings or templates?

No. Several common misconceptions:

| Misconception | Reality in Java 17 |
| --- | --- |
| Text blocks keep every backslash verbatim. | No; Java escape sequences are still processed. |
| Double quotes always require `\"`. | No; one or two double quotes can be written directly. Three consecutive quotes require escaping so they don't close the block. |
| Opening delimiter and content can be on the same line. | No; the opening delimiter must be followed by a line terminator. |
| Source line breaks are always ignored. | No; newlines are normally part of the String value. |
| Moving the closing delimiter does not affect data. | It can affect indentation and the trailing newline. |
| Variables can be embedded by name like a template literal. | No; Java 17 text blocks have no variable interpolation. Use concatenation, `formatted`, or a proper template engine. |
| Text blocks automatically protect SQL/HTML/JSON. | No; use parameterized APIs or proper serializers/encoders. |

### 10.1. Using `formatted` for simple value substitution

```java
String template = """
        Hello, %s!
        Your score is %d.
        """;

String message = template.formatted("Lan", 95);
```

`String.formatted(...)` has been available since Java 15 and works in Java 17. It processes placeholders according to `Formatter` rules, **not** as a general interpolation mechanism or safe encoder for HTML, SQL, shell, or JSON.

## 11. Comparing string literals, concatenation, and text blocks

| Approach | Best suited when | Points to watch |
| --- | --- | --- |
| String literal `"..."` | Short, single-line strings. | Must escape double quotes and newlines per Java rules. |
| String concatenation with `+` | Joining a few small parts or simple expressions. | Multiple concatenated lines quickly get cluttered and hard to align. |
| Text block `""" ... """` | Multiline, structured content with many quotes. | Must understand indentation, newlines, trailing whitespace, and escapes. |
| Purpose-built APIs (Path, JDBC parameters, JSON serializer, HTML encoder) | Handling data with domain semantics. | Use the right API for the job; text blocks are just a String syntax. |

Do not convert every string into a text block. Single-line strings like status codes, keys, or short messages are usually clearest as ordinary string literals.

## 12. Comprehensive example: quotes, backslashes, triple quotes, and newlines

Save the following program into **`TextBlockDetails.java`**:

```java
public class TextBlockDetails {
    public static void main(String[] args) {
        String quotes = """
                A normal quote: "hello"
                Two quotes: ""
                Three quotes: \"""
                """;

        String windowsPath = """
                C:\\Users\\Public\\notes.txt
                """;

        String regex = """
                \\d{4}-\\d{2}-\\d{2}
                """;

        String padded = """
                key\s
                """;

        System.out.println("QUOTES:");
        System.out.print(quotes);

        System.out.println("PATH:");
        System.out.println(windowsPath);

        System.out.println("REGEX:");
        System.out.println(regex);

        System.out.println("PADDED:");
        System.out.println("[" + padded.replace(" ", "·") + "]");
    }
}
```

Compile and run:

```bash
javac --release 17 TextBlockDetails.java
java TextBlockDetails
```

The program demonstrates several rules applied together:

- `"hello"` and `""` are written directly.
- `\"""` produces literal triple-quote content.
- `\\` produces one backslash in the path.
- `\\d` produces the regex token `\d`.
- `\s` produces an intentional trailing space.

## 13. Common mistakes and fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Compiler error near `"""Hello...`. | Opening delimiter lacks a line terminator after it. | Put content on the next line or use a single-line string literal. |
| Text block closes prematurely at triple quotes. | Three quotes inside content are parsed as the closing delimiter. | Escape at least one quote, e.g. `\"""`, to keep three quotes in output. |
| Compiler reports illegal escape for `\d` or `\w`. | These are regex escapes, not valid Java escapes. | Write `\\d` or `\\w` so the String receives a single backslash. |
| Windows path loses backslashes or triggers escape errors. | Backslashes in source start escape sequences. | Use `\\\\` in source for each backslash needed in output, or use `Path.of(...)`. |
| Text block has unexpected indentation. | Indentation depends on content lines and closing delimiter position. | Align delimiters, check incidental indentation, and inspect the String value. |
| Trailing spaces on lines disappear. | Trailing whitespace is stripped. | Use `\s` for intentional spaces. |
| Output has an unexpected trailing newline. | Closing delimiter position determines whether trailing newline is in content. | Put closing delimiter on its own line if trailing newline is wanted; immediately after content if not. |
| Assuming text blocks do not process escapes. | Confusing text blocks with raw strings. | Remember Java still interprets escape sequences after stripping indentation. |
| Dynamic HTML/SQL data has security bugs. | Treating text blocks as data escaping. | Use prepared statements, serializers, or context-aware encoders. |

## 14. Practice exercises

### Exercise 1 — Convert concatenated strings to a text block

Convert the following into a text block while preserving the lines and quotes in the content:

```java
String config = "{\n"
        + "  \"app\": \"demo\",\n"
        + "  \"enabled\": true\n"
        + "}";
```

Then explain why the quotes surrounding `app` do not need escaping inside a text block.

### Exercise 2 — Write a Windows path

Create a text block containing:

```text
C:\Program Files\Java\jdk-17
```

Write the source code so the String value has exactly one backslash between path segments. Explain why writing `\t` directly can create a tab instead of a backslash and the letter `t`.

### Exercise 3 — Create a date regex

Create a text block for the regex:

```text
\d{4}-\d{2}-\d{2}
```

Use `Pattern.matches(...)` to test `2026-11-15` and an invalid string. In source code, how many backslashes must be written for each `\d` token?

### Exercise 4 — Include triple quotes in content

Write a text block containing the sentence:

```text
The delimiter is """
```

Explain why escaping a single quote is enough to stop the compiler from closing the text block at that point.

### Exercise 5 — Keep a trailing space

Create a text block containing the word `key` followed by exactly one space and one newline. Use `\s` and explain why typing an ordinary Space at the end of a source line is not a reliable way to preserve trailing whitespace.

### Exercise 6 — Controlling newlines

Write two text blocks with the same two source lines:

- One value keeping the newline between the two lines.
- One value using line continuation to join the content into one line.

Print both values wrapped in square brackets to observe the trailing newline.

## 15. Official Java 17 documentation

- [JLS Java SE 17, §3.10.6 — Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6): syntax, delimiters, incidental indentation, escape processing, and text block content rules.
- [JEP 378 — Text Blocks](https://openjdk.org/jeps/378): design goals, syntax, and standardized status since JDK 15.
- [Java 17 Language Guide — Text Blocks](https://docs.oracle.com/en/java/javase/17/language/text-blocks.html): guide to using text blocks in Java 17.
- [JLS Java SE 17, §3.3 — Unicode Escapes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.3): explains the Unicode escape translation stage in source compilation.
- [Java SE 17 API — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): look up string methods such as `formatted`, `stripIndent`, and String operations.

When working with Java 17 text blocks, separate three layers of concerns: **delimiters decide what is content; indentation and closing delimiter placement decide whitespace and newlines; escape sequences decide special characters in the String value**. Ordinary double quotes can be written directly, three consecutive quotes require escaping one quote, and backslashes must be doubled when they should appear literally in the output. Mastering these three layers lets you create SQL, JSON, HTML, regexes, and multiline text cleanly while avoiding mistakes from thinking text blocks are raw strings.
