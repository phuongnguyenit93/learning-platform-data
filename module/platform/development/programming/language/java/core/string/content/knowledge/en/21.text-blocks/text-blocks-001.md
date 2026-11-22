# Text blocks are syntax for creating multiline `String` values in Java

## 1. What is a text block?

A **text block** is a way to write **multiline string literals** in Java source code using three double-quote delimiters (`"""`). This feature became **standard in Java 15** (having previously been tested in preview releases). From Java 17 onward, text blocks can be used directly without enabling preview features.

Instead of concatenating multiple literals with the `+` operator or manually inserting `\n`, you can write text in a layout close to the content you want to store:

~~~java
String html = """
        <html>
          <body>
            <h1>Hello Java</h1>
          </body>
        </html>
        """;
~~~

The `html` variable still has the type **`java.lang.String`**, just like a string written with regular double quotes. A text block does **not** create a new data type, does not turn the string into a mutable object, and does not automatically parse HTML, JSON, or SQL. It is simply **a syntax for representing a `String` value** that is easier to read when the text spans multiple lines.

The equivalent written with regular string literals:

~~~java
String html = "<html>\n"
        + "  <body>\n"
        + "    <h1>Hello Java</h1>\n"
        + "  </body>\n"
        + "</html>\n";
~~~

The two `html` variables in the two separate snippets have the exact same content. The `\n` in the traditional example is the newline character; in a text block, those newlines mainly come directly from the multiline layout of the source code.

## 2. Syntax and delimiters

Basic form:

~~~java
String message = """
        First line
        Second line
        """;
~~~

Rules to remember:

1. **The opening delimiter `"""` must be followed by a line terminator** (whitespace is allowed between the opening delimiter and the end of the line). The actual text begins on the next line.
2. **The closing delimiter `"""` ends the text block.** It can be on its own line or immediately after the last character of text.
3. **The newline after the opening delimiter is not automatically added to the beginning of the string.** The first line of content starts with `First line`.
4. **The newline immediately before the closing delimiter** becomes part of the string when the closing delimiter is on its own line. If it closes right after the content, that trailing newline is not included.
5. Common leading indentation across lines is automatically handled by Java so that source code can sit neatly inside a code block.

Example of **two different string values**:

~~~java
String withNewline = """
        Hello
        """;

String withoutNewline = """
        Hello""";

System.out.println(withNewline.equals("Hello\n"));     // true
System.out.println(withoutNewline.equals("Hello"));    // true
~~~

The following form is **invalid Java syntax** because there is no line break after the opening delimiter:

~~~java
// Does not compile:
String invalid = """Hello""";
~~~

For a single-line string, you can use a regular `"Hello"` literal. Text blocks are most useful when the content is genuinely long or spans multiple lines.

## 3. Indentation (incidental indentation)

A text block usually sits inside a method, so the source lines must be indented for readability. Java strips **common incidental indentation**, while preserving the relative difference between lines:

~~~java
String menu = """
        Main dish
          Side dish
        """;
System.out.println(menu.equals("Main dish\n  Side dish\n")); // true
~~~

The `Side dish` line still has two leading spaces in the resulting value, even though the source code is indented deeper. When the closing `"""` is on its own line, its column position also participates in determining the common indentation; moving the closing delimiter to the left can preserve extra spaces at the start of the content. Trailing whitespace on source lines is normally stripped, while the `\s` escape lets you keep an intentional space.

The lesson **Incidental indentation whitespace and closing delimiter position** explains the exact calculation along with cases involving tabs, blank lines, and misaligned closing delimiters.

## 4. Do text blocks automatically create newlines?

Text blocks use LF (`\n`) as the line terminator in the resulting value, even when the source file uses CRLF. The mandatory newline **after the opening delimiter** does not automatically create a blank line at the start of the string. If the closing delimiter is on its own line, the LF before the closing delimiter belongs to the content; if it closes directly against the last line, that final LF does not appear:

~~~java
String a = """
        one
        two
        """;
String b = """
        one
        two""";
System.out.println(a.equals("one\ntwo\n")); // true
System.out.println(b.equals("one\ntwo"));   // true
~~~

To split a long sentence across multiple source lines without producing an LF at the split point, place `\` at the end of the content line; place `\s` before the continuation backslash if you need to keep a space. The lessons **Line ending normalization**, **Space escape and line continuation**, and **Final line with or without a newline character** examine each rule and edge case separately.

## 5. Double quotes, escapes, and non-“raw” behavior

Text blocks reduce the need to escape double quotes inside the content:

~~~java
String json = """
        {
          "name": "An",
          "active": true
        }
        """;

System.out.println(json.contains("\"name\": \"An\"")); // true
~~~

Inside a text block, `"name"` is written directly; there is no need to change it to `\"name\"` as in a traditional literal. However, a text block is **not a raw string**: Java still processes escapes such as `\n`, `\t`, `\\`, `\"`, and `\s`. If the content needs to contain **three consecutive double quotes**, you must escape them appropriately so they are not interpreted as the closing `"""`.

For example, a path containing backslashes must be written properly:

~~~java
String path = """
        C:\\temp\\data.txt
        """;

System.out.println(path.equals("C:\\temp\\data.txt\n")); // true
~~~

If you write `C:\temp\data.txt` directly inside a text block, `\t` can turn into a tab and `\d` is an invalid Java escape. Text blocks let you write multiple lines; they **do not exempt you from Java escape rules**.

The same applies to regex: if you want to create a string containing the regular expression `\d+`, you still have to write `\\d+` in the text block, for example:

~~~java
String regex = """
        \\d+""";
System.out.println(regex.equals("\\d+")); // true
~~~

Placing the closing delimiter on the same line as `\\d+` ensures there is no trailing newline at the end of the regex.

## 6. Complete, compilable and runnable Java 17+ program

Save as `TextBlockDemo.java`:

~~~java
public class TextBlockDemo {
    public static void main(String[] args) {
        String greeting = """
                Hello,
                Java!
                """;

        String withoutEnd = """
                Hello,
                Java!""";

        String indented = """
                item
                  detail
                """;

        String joined = """
                One \
                line.
                """;

        String space = """
                A\s
                B
                """;

        String path = """
                C:\\temp\\data.txt
                """;

        String json = """
                {
                  "name": "An",
                  "active": true
                }
                """;

        System.out.println(greeting.equals("Hello,\nJava!\n"));
        System.out.println(withoutEnd.equals("Hello,\nJava!"));
        System.out.println(indented.equals("item\n  detail\n"));
        System.out.println(joined.equals("One line.\n"));
        System.out.println(space.equals("A \nB\n"));
        System.out.println(path.equals("C:\\temp\\data.txt\n"));
        System.out.println(json.contains("\"name\": \"An\""));
        System.out.println(
                "Hello, %s!".formatted("An")
                        .equals("Hello, An!"));
    }
}
~~~

Compile and run commands:

~~~bash
javac -encoding UTF-8 TextBlockDemo.java
java TextBlockDemo
~~~

`stdout` output:

~~~text
true
true
true
true
true
true
true
true
~~~

Eight `true` results demonstrate that: a text block has or does not have a trailing newline depending on the closing delimiter's position; relative indentation is preserved; `\` at the end of a source line joins two lines into one; `\s` preserves a trailing space; `\\` produces an actual backslash; double quotes in JSON do not need escaping; and `formatted` can insert data into a `String` template.

The core cases in the program have been compiled and verified on Java with Java 17 source compatibility level.

## 7. Using text blocks in practice

### 7.1. JSON, HTML, or XML

Structured multiline text becomes much easier to read:

~~~java
String payload = """
        {
          "event": "user.created",
          "id": 101,
          "enabled": true
        }
        """;
~~~

A text block keeps formatting easy to inspect, but it **does not validate JSON syntax** and **does not automatically escape dynamic data**. When building real JSON from objects or user values, you should use a JSON serializer (such as Jackson) to handle escaping and data structure properly.

### 7.2. Multiline SQL

~~~java
String sql = """
        SELECT id, name, email
        FROM users
        WHERE status = ?
        ORDER BY name
        """;
~~~

The SQL query is easier to read and keeps the `?` characters as placeholders for `PreparedStatement`. Text blocks **do not prevent SQL injection**; binding parameters with `PreparedStatement` is still required. Never concatenate user values directly into SQL just because you are using a text block.

### 7.3. Parameterized content templates

Text blocks do not support automatic variable interpolation like `${name}` as in some other languages. You can combine them with `String.formatted(...)` or `String.format(...)`:

~~~java
String template = """
        Hello %s!
        You have %d new notifications.
        """;

String result = template.formatted("An", 3);
System.out.print(result);
~~~

Output:

~~~text
Hello An!
You have 3 new notifications.
~~~

`formatted` uses format syntax with `%s`, `%d`…, and **does not** change the escape or indentation rules of text blocks. The data passed to formatting must match the placeholders; a literal `%` character in a format string must be written as `%%`.

### 7.4. Defining messages and test data

Text blocks are convenient for representing email templates, CLI help text, HTML/JSON fixtures, or multiline expected outputs in unit tests. However, in exact-match tests, you should explicitly decide whether a trailing `\n`, trailing spaces on lines, and platform-specific line endings are expected.

## 8. Common misconceptions

| Misconception | Reality and how to handle it |
| --- | --- |
| A text block is a new data type | It is still a `String`, immutable like every other Java `String` |
| The opening `"""` can be on the same line as content | There must be a line terminator after the opening delimiter |
| A text block always ends with a newline | It depends on the closing delimiter position and line-continuation syntax |
| Source indentation is preserved 100% | Java strips common incidental indentation; the closing delimiter also affects it |
| A text block is a raw string | Java escape sequences are still interpreted |
| You can use `\d` or Windows paths without escaping | To get an actual backslash, you must write `\\` in source |
| A text block automatically substitutes variables inside its content | Use `formatted`, `format`, or an appropriate template engine |
| JSON or SQL in a text block is validated and safe | A text block only represents a string; serializers, validation, and parameter binding are still needed |
| Text blocks cannot be used for single-line strings | They can, though a normal literal is usually simpler |

## 9. When should and shouldn't you use them?

**Use them** when storing text that spans multiple lines or contains many double quotes: HTML, illustrative JSON, SQL, messages, sample source code, or test content. The main benefits are reducing `+` string concatenation, reducing manual `\n` escapes, and improving code readability.

**Consider using a regular literal** for a very short snippet without newlines, or when you need to see every character escape clearly on a single line. For long content that needs to change independently of source code, resource files or a template engine may be a better fit than a text block.

**Remember:** A text block starts with `"""` followed by a newline, evaluates to a normal `String`, handles common indentation automatically, and preserves Java's escape rules. The position of the closing delimiter largely determines indentation and the trailing newline. To avoid discrepancies, check the **compiled string value**, especially when character-by-character matching is required.
