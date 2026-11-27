# Text Blocks in Java 17: Solving the Multiline String Problem in Source Code

When writing Java programs, not every string is just one line long. A SQL query, an email notification, an HTML document, sample JSON, or test content often contains **multiple lines, double quotes, and indented structure**. If you represent them using traditional string literals, source code easily becomes hard to read because you have to concatenate multiple segments and manually add newline characters.

**Text blocks** allow you to write multiline content directly in Java source code in a form close to the actual text layout. This feature has been standardized since Java 15 (JEP 378) and works normally in **Java 17**, without enabling preview features.

This lesson focuses on the problem text blocks solve, basic syntax, how Java handles line breaks and whitespace, when to use them, and things to keep in mind when bringing multiline data into an application.

## 1. The problem: multiline strings before text blocks

Imagine a program needs to store the following SQL query:

```sql
SELECT id, title, author
FROM books
WHERE published = ?
ORDER BY title
```

With regular string literals, you might write:

```java
String sql = "SELECT id, title, author\n"
        + "FROM books\n"
        + "WHERE published = ?\n"
        + "ORDER BY title\n";
```

The code is valid, but the reader has to distinguish **the structure of the actual string** from the auxiliary parts in Java code: quotation marks, plus signs, `\n` characters, and indentation for the concatenation expression.

Another example is HTML:

```java
String html = "<div class=\"card\">\n"
        + "    <h2>Notification</h2>\n"
        + "    <p>Your order is ready.</p>\n"
        + "</div>\n";
```

Besides adding `\n`, the author also has to escape `"` as `\"`. When HTML gets longer, a single misplaced quote or plus sign makes the code difficult to maintain.

The problem lies in **representing and maintaining multiline text in source code**:

| Difficulty | Consequence |
| --- | --- |
| Having to concatenate multiple string literals with `+` | The actual text is fragmented by Java syntax. |
| Having to manually insert `\n` on each line | Easy to forget or add an extra newline character. |
| Having to escape many double quotes | HTML/JSON/SQL can be hard to read and hard to copy from source documents. |
| Wanting to align Java code without altering the data | Must manually control spaces inside each literal. |
| Editing a large block of text | Easy to introduce errors at literal boundaries or escape characters. |

**Text blocks** were designed to make such text blocks easier to read, not to change the nature of the `String` type.

## 2. Text block syntax in Java 17

A text block starts with **three double quotes** `"""`, which must be followed immediately by a line break. The content spans the following lines and ends with three double quotes `"""`:

```java
String sql = """
        SELECT id, title, author
        FROM books
        WHERE published = ?
        ORDER BY title
        """;
```

In this example, the opening `"""` stands on the declaration line; the content starts on the next line. The indentation used to lay out the source code is processed according to text block rules, so the resulting string is:

```text
SELECT id, title, author
FROM books
WHERE published = ?
ORDER BY title
```

The resulting string also has a `\n` newline character after `ORDER BY title` because the closing `"""` is placed on **its own line** below the content.

### 2.1. A text block still has type `String`

A text block does not create a new data type:

```java
String text = """
        Hello!
        This is multiline content.
        """;

System.out.println(text.length());
System.out.println(text.contains("multiline"));
System.out.println(text.isBlank());
```

Familiar `String` methods still work. You can pass a text block to a method expecting `String`, concatenate it with another string, compare using `equals()`, or use it with text-processing APIs.

### 2.2. A newline is required after the opening delimiter

Correct:

```java
String message = """
        Hello Java 17
        """;
```

Invalid syntax:

```java
// Intentional example that DOES NOT compile:
// String message = """Hello Java 17""";
```

For text blocks, Java requires a **line terminator** after the opening delimiter, optionally preceded by whitespace before the line break. This clearly distinguishes a text block from a regular `"..."` string literal.

If the content is just a short single line, `"Hello Java 17"` is usually simpler and offers no clear benefit when converted to a text block.

## 3. Direct before-and-after comparison

Example creating sample JSON data:

**Regular string literal**

```java
String jsonOld = "{\n"
        + "  \"name\": \"Lan\",\n"
        + "  \"active\": true,\n"
        + "  \"roles\": [\"student\", \"editor\"]\n"
        + "}\n";
```

**Text block**

```java
String jsonNew = """
        {
          "name": "Lan",
          "active": true,
          "roles": ["student", "editor"]
        }
        """;
```

Both approaches produce the **exact same character content**:

```java
System.out.println(jsonOld.equals(jsonNew)); // true
```

The biggest difference is readability, copyability, and editability. In the text block version, the JSON lines look like an actual JSON document, while the Java code can still be indented according to class and method structure.

**Text blocks do not automatically parse JSON or guarantee valid JSON.** It is just a way to declare a string. If the content needs to be validated, mapped to objects, or generated from dynamic data, the application still needs proper JSON handling.

## 4. How does Java process line breaks and indentation?

A text block does not simply preserve every character verbatim from the visible editor region. Java 17 applies processing rules so multiline text is convenient to use in indented source code.

Conceptually, the processing consists of:

1. **Normalize line terminators:** different line-ending forms in the text block content are normalized to `\n` (LF).
2. **Remove incidental indentation:** determine the common indentation level and strip the indentation used only to align source code; also handle trailing whitespace on each line according to text block rules.
3. **Process escape sequences:** after the whitespace processing step, Java interprets escapes such as `\n`, `\t`, `\s`, or `\` used for line continuation.

This order matters: some escapes are used specifically to **preserve whitespace** or **remove line breaks** that the default processing step would otherwise not keep.

### 4.1. Source indentation does not mean string indentation

Example:

```java
String text = """
        Main item
          Sub item
        End
        """;
```

Resulting content:

```text
Main item
  Sub item
End
```

The common indentation before the three lines is stripped; the **two relative spaces** before `Sub item` are preserved. This allows you to place a text block inside a deeply indented method without the actual content carrying all the Java code's leading whitespace.

### 4.2. Closing delimiter position affects indentation

The closing `"""` also participates in determining how much whitespace is considered incidental indentation.

```java
String withoutExtraIndent = """
        A
          B
        """;

String withExtraIndent = """
        A
          B
    """;
```

In the first case, the closing delimiter is aligned with `A`, so the common indentation is stripped and the result is `"A\n  B\n"`. In the latter case, the closing delimiter sits **to the left** of the content; part of the indentation before `A` and `B` is retained in the string. This allows intentionally keeping indentation when needed.

To avoid surprises when editing source code, choose a consistent placement for the closing delimiter. If you want to preserve an exact amount of indentation, pay attention to the alignment between the content lines and the closing delimiter.

### 4.3. Trailing newline character or not?

This is an easily overlooked difference:

```java
String withTrailingNewline = """
        first
        second
        """;

String withoutTrailingNewline = """
        first
        second""";

System.out.println(withTrailingNewline.endsWith("\n"));    // true
System.out.println(withoutTrailingNewline.endsWith("\n")); // false
```

When the closing delimiter is on **its own line** after the content line, the line terminator before it belongs to the string. When the closing delimiter is placed **immediately after the final content**, no extra trailing newline is added.

This affects string comparisons, tests, HTTP payloads, SQL statements, or configurations where a trailing newline is significant. Decide intentionally rather than assuming both declarations always produce the same string.

### 4.4. Line endings are normalized

Text blocks use `\n` as the newline character in the generated content, even when the source file is saved with CRLF line endings on Windows. Therefore:

```java
String lines = """
        one
        two
        """;

System.out.println(lines.equals("one\ntwo\n")); // true
```

Do not assume a text block produces `System.lineSeparator()` on each line. If a protocol or format requires a different line ending (such as CRLF), handle it explicitly according to that protocol's contract.

## 5. Escapes in text blocks: not a raw string

Text blocks reduce the number of characters that must be escaped, but they are **not completely raw strings**. Valid Java escapes are still processed.

### 5.1. Ordinary double quotes

Inside a text block, there is no need to escape individual `"` characters:

```java
String html = """
        <a href="https://example.com" title="Home">Open page</a>
        """;
```

This is a clear benefit for HTML and JSON. Only when the content contains **three consecutive double quotes** that could be interpreted as the closing delimiter do you need appropriate escaping, such as `\"""` to produce three double quotes in the text without ending the text block.

### 5.2. Common escapes

| Syntax in text block | Meaning |
| --- | --- |
| `\n` | Inserts an LF newline character at the specified position. |
| `\t` | Inserts a tab character. |
| `\\` | Inserts a backslash `\`. |
| `\"` | Inserts a double quote when escaping is needed, though most `"` in content do not require it. |
| `\s` | Inserts a space; useful for preserving trailing whitespace at the end of a line. |
| `\` immediately before a line break in source | Joins two lines of the text block into one resulting line without adding a newline there. |

Example of escape characters:

```java
String message = """
        First line\nNext line
        Column A\tColumn B
        """;
```

Here `\n` on the first line inserts an additional LF, while the actual line break in source code also creates its own LF. Account for both when you need exact content.

### 5.3. Preserving trailing spaces with `\s`

Whitespace at the end of text block lines is normally stripped during whitespace processing. If the content truly needs a space right before a newline, you can use `\s`:

```java
String text = """
        A\s
        B
        """;

System.out.println(text.equals("A \nB\n")); // true
```

The space is produced from `\s` **after** Java processes text block whitespace, so it is preserved in the resulting string. This is clearer than placing an invisible space at the end of a line in an editor.

### 5.4. Joining source lines without a resulting newline

When a sentence is too long and you want tidy source code, place `\` at the end of the line:

```java
String sentence = """
        This is a sentence split \
        across two lines in source code.
        """;

System.out.println(sentence);
```

Output:

```text
This is a sentence split across two lines in source code.
```

The trailing `\` removes the corresponding line terminator. In the example, the space before `\` is preserved so the two words do not run together. This technique is suitable when you need to **wrap lines for code readability** while keeping the output as a single line.

### 5.5. Backslashes in content

Text blocks still process Java escapes. If you need a backslash character in the string, you usually must write `\\`:

```java
String windowsPath = """
        C:\\work\\notes
        """;

System.out.println(windowsPath);
// C:\work\notes
```

If you paste a raw path containing `\n` into code without escaping, `\n` can be interpreted as a newline and produce unexpected output. For strings containing many `\` characters, pay attention to this rule even when using text blocks.

## 6. Practical use cases for text blocks

### 6.1. Multiline SQL

```java
String sql = """
        SELECT id, name, created_at
        FROM customers
        WHERE status = ?
          AND created_at >= ?
        ORDER BY created_at DESC
        """;
```

The query is nearly as readable as writing it in a SQL tool. Java preserves lines and meaningful relative indentation.

When search criteria come from users, **do not concatenate them directly into SQL**:

```java
// Assume connection, status, and startDate are already declared.
try (java.sql.PreparedStatement statement =
        connection.prepareStatement(sql)) {
    statement.setString(1, status);
    statement.setDate(2, java.sql.Date.valueOf(startDate));
    try (java.sql.ResultSet rows = statement.executeQuery()) {
        while (rows.next()) {
            System.out.println(rows.getString("name"));
        }
    }
}
```

Text blocks help **read and maintain SQL**, while `PreparedStatement` handles **binding parameters** for dynamic data. Text blocks do not prevent SQL injection on their own. Dynamic SQL identifiers such as table or column names require separate validation/allowlisting, not regular `?` placeholders.

### 6.2. Template-style HTML or email content

```java
String html = """
        <!doctype html>
        <html lang="en">
          <body>
            <h1>Order confirmed</h1>
            <p>Thank you for your purchase.</p>
          </body>
        </html>
        """;
```

Here, preserving the nested structure of HTML offers a major readability advantage over string concatenation.

If the content needs dynamic data inserted, you can use `formatted()`:

```java
String template = """
        <p>Hello %s!</p>
        <p>Your order: %s</p>
        """;

String htmlForCustomer = template.formatted("Lan", "A-102");
```

**Note:** `formatted()` only formats strings using `String.format`-style placeholders; it **does not automatically escape HTML**. For user-supplied data, perform context-appropriate HTML escaping/encoding or use a template engine that supports escaping.

### 6.3. Sample JSON in tests and API examples

```java
String payload = """
        {
          "userId": 17,
          "name": "Mai",
          "permissions": ["read", "write"]
        }
        """;
```

When writing unit tests or testing an API with a fixed payload, declaring JSON with a text block keeps sample data close to the JSON seen in documentation.

If a program needs to build JSON from objects with dynamic data or complex structures, prefer an appropriate JSON library instead of manually interpolating Java values into JSON; text blocks do not escape special characters or guarantee valid JSON output.

### 6.4. Multiline messages and CLI help text

```java
String help = """
        Usage:
          app --input <file>
          app --help

        Options:
          --input  Path to the file to process
          --help   Show help
        """;

System.out.print(help);
```

Blank lines, relative indentation, and content ordering are shown clearly in code. For strings with many instructions or option lists, this declaration style is easy to edit.

## 7. Complete Java 17 program

Create a file `TextBlockDemo.java`:

```java
public class TextBlockDemo {
    public static void main(String[] args) {
        String traditional = "Hello,\n"
                + "Your order is ready.\n"
                + "Thank you.\n";

        String textBlock = """
                Hello,
                Your order is ready.
                Thank you.
                """;

        System.out.println("Both are equal: "
                + traditional.equals(textBlock));
        System.out.println("Has trailing LF: "
                + textBlock.endsWith("\n"));

        String noFinalLf = """
                Line 1
                Line 2""";
        System.out.println("No trailing LF: "
                + !noFinalLf.endsWith("\n"));

        String json = """
                {
                  "id": 17,
                  "status": "ready"
                }
                """;
        System.out.println("Sample JSON:");
        System.out.print(json);

        String template = """
                Hello %s,
                Status: %s
                """;
        System.out.print(template.formatted("An", "Completed"));
    }
}
```

Compile and run with **JDK 17**:

```bash
javac TextBlockDemo.java
java TextBlockDemo
```

Output:

```text
Both are equal: true
Has trailing LF: true
No trailing LF: true
Sample JSON:
{
  "id": 17,
  "status": "ready"
}
Hello An,
Status: Completed
```

Through this example, you can see that a text block is still an ordinary `String`; what differs is **how multiline strings are declared in source code** and the accompanying whitespace rules.

## 8. When are text blocks not the best choice?

Text blocks fit **fixed** text segments that benefit from multiline presentation. However, they do not replace all forms of content management:

| Situation | Usually suitable choice |
| --- | --- |
| Short single-line string | Regular `"..."` string literal. |
| Fixed, moderately sized SQL, HTML, or sample JSON | Text block for source readability. |
| Large data or content edited without modifying Java code | External resource file read with an appropriate API. |
| Content requiring multi-language translation | Resource bundle or localization system. |
| Dynamic HTML pages with many display branches | Template engine or UI rendering tool. |
| JSON/XML generated from objects with dynamic data | Serializer or dedicated data-processing library. |
| SQL queries with untrusted data parameters | Text block combined with `PreparedStatement` and data validation. |

If a multiline text varies frequently or is edited often by non-programmers, storing it in a separate resource file may make more sense to separate content from Java logic.

## 9. Common mistakes when using text blocks

### 9.1. Forgetting the newline right after `"""`

```java
// Invalid:
// String wrong = """hello""";

// Valid:
String right = """
        hello
        """;
```

A text block requires a newline after the opening delimiter. This is a Java 17 syntax rule, independent of the IDE.

### 9.2. Extra or missing trailing LF

```java
String a = """
        alpha
        """;

String b = """
        alpha""";

System.out.println(a.equals(b)); // false
```

The two strings look identical when printed with `println`, yet `a` has a trailing LF while `b` does not. In unit tests, string comparisons, or sending data to another protocol, even a single-character difference can matter.

### 9.3. Assuming leading/trailing whitespace is preserved verbatim

Indentation and trailing whitespace are processed by Java. If a configuration file or format is whitespace-sensitive, do not simply look at aligned source code and conclude the output bytes always match the source text.

If you need to keep trailing spaces, use `\s` intentionally. If you need extra indentation, arrange the closing delimiter and lines so the desired indentation becomes part of the content.

### 9.4. Confusing text blocks with raw strings or template strings

Text blocks **still process Java escapes** and do not automatically interpolate variables:

```java
String name = "Lan";
String message = """
        Hello, name!
        """;
```

The result literally contains the word `name`, not replaced with `Lan`. To insert values, use `formatted()` or an appropriate string-building technique:

```java
String messageWithName = """
        Hello, %s!
        """.formatted(name);
```

At the same time, `\` characters are not preserved unconditionally; escape rules still apply.

### 9.5. Assuming text blocks automatically protect dynamic data

Text blocks do not automatically:

- prevent SQL injection when interpolating user data into SQL queries;
- escape HTML to defend against malicious content;
- produce syntactically valid JSON from user data;
- encode URLs, XML, or other data formats;
- perform localization or template management.

This feature **solves how multiline string literals are written**, while validation, encoding, and data handling must rely on purpose-built APIs.

### 9.6. Relying completely on OS line endings

If `\r\n` is needed for a specific protocol or format, a text block with normalized LF **does not automatically convert** to CRLF just because the code runs on Windows. Only convert line endings when the output contract requires it; for most text in source code, standard LF is sufficient.

## 10. Practice exercises

### Exercise 1 — Convert string concatenation to a text block

Original code:

```java
String menu = "Menu:\n"
        + "  1. View books\n"
        + "  2. Borrow books\n"
        + "  0. Exit\n";
```

Rewrite this using a text block, ensuring two spaces are preserved before each menu item and a trailing LF is kept.

Hint:

```java
String menu = """
        Menu:
          1. View books
          2. Borrow books
          0. Exit
        """;
```

### Exercise 2 — Predict the trailing newline

```java
String first = """
        A
        B
        """;

String second = """
        A
        B""";
```

What do the following two expressions return?

```java
first.endsWith("\n")
second.endsWith("\n")
```

**Answer:** `true` and `false`. A closing delimiter on its own line creates a trailing LF; a closing delimiter right after the last character does not.

### Exercise 3 — When is escaping needed?

Write a text block containing the following JSON:

```json
{
  "file": "report.txt",
  "enabled": true
}
```

Determine whether the `"` characters in key names and values need escaping.

**Hint:** Individual double quotes do not need escaping in a text block. If a JSON value contains backslash characters, remember escaping may be needed at **two layers of rules**: Java string rules and JSON rules.

### Exercise 4 — A long string on one resulting line

Use `\` at the end of a line in a text block so that the following sentence is split across two **source** lines while still producing **one resulting line**:

```text
This is a long sentence used to illustrate line continuation in a text block.
```

### Exercise 5 — Clear and safe SQL

Write a text block containing:

```sql
SELECT id, email
FROM users
WHERE active = ?
  AND role = ?
```

Explain why data for the two `?` placeholders should be passed through `PreparedStatement` instead of concatenating directly into SQL. Determine whether the SQL string needs a trailing LF based on how the application uses it.

## 11. Takeaways when working with multiline strings

Text blocks are official syntax in **Java 17** for representing a multiline `String` in a readable and maintainable way. Opened and closed with `"""`, a newline is mandatory after the opening delimiter; Java automatically strips incidental indentation and normalizes line terminators to LF. The closing delimiter's position determines whether a trailing LF is retained. Text blocks still support escapes such as `\n`, `\s`, and `\` line continuation, while remaining ordinary strings when passed to APIs.

For SQL, JSON, HTML, messages, and fixed sample data, text blocks keep source code close to the represented content. When dynamic data or complex formatting requirements arise, combine them with dedicated tools rather than treating text blocks as a template system or serializer.

### References

- [JEP 378: Text Blocks](https://openjdk.org/jeps/378) — standardized text blocks feature.
- [Java Language Specification, Java SE 17 — §3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6) — text block syntax, indentation handling, and escapes.
- [Java SE 17 API — `String.stripIndent()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#stripIndent()) — indentation stripping mechanism for strings.
- [Java SE 17 API — `String.translateEscapes()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#translateEscapes()) — interpreting Java string escapes.
- [Java SE 17 API — `String.formatted(Object...)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#formatted(java.lang.Object...)) — string formatting, usable with text blocks.
