# Java Text Blocks Do Not Interpolate Variables or Escape for Target Formats Automatically

## 1. Text blocks are string literals, not self-executing templates

Since Java 15 (stable), a **text block** is syntax for writing multiline strings using triple double quotes (`"""`). The resulting value is still a `String` object. Text blocks make source code easier to read when writing HTML, JSON, SQL, XML, or long messages; **they do not automatically interpolate variables, execute expressions, or protect content for external formats**.

Example:

```java
String name = "Lan";

String message = """
        Hello, {{name}}!
        """;

System.out.println(message.strip()); // Hello, {{name}}!
```

`{{name}}` is merely characters inside the string. Java does not look up the variable `name` to substitute it there. Likewise, notations like `%s`, `$name`, `#{name}`, or `{{expression}}` inside a text block **have no special meaning to the text block itself**. They only act as placeholders if a developer explicitly uses an API designed to process them.

**Two questions to keep separate:**

1. **Interpolation / inserting data:** How do we put a variable's value into a string? We can use `String.formatted`, `String.format`, `String.replace`, or an appropriate template engine.
2. **Escaping / encoding for the target format:** How must that value be represented so it does not break syntax or alter the meaning of HTML, JSON, SQL, XML, URI…? We need the right encoder, serializer, parameterization, or parser for the *target context*.

Solving question (1) **does not mean** you have solved question (2).

## 2. How does Java process a text block?

Typical syntax:

```java
String lines = """
        First line
        Second line
        """;
```

A valid text block requires a newline after the opening `"""`. Java applies text block processing rules at compile time: normalizing line terminators, stripping unnecessary common indentation (*incidental indentation*), and then processing Java escape sequences. Therefore, a text block is **not a raw string** in the sense that "every character written is preserved verbatim."

Things to remember:

- If the closing `"""` is on **its own line**, the LF immediately before the closing delimiter belongs to the content. If you only need to strip a single trailing LF, adjust the closing delimiter or remove that exact character after checking `endsWith`; `stripTrailing()` can remove other whitespace as well.
- Java still processes escapes such as LF, tab, a single backslash, the `\s` space escape, and backslash line continuation. These are Java escapes, not HTML, JSON, or SQL escapes.
- Text blocks make writing `"` inside content easier than regular Java strings, yet three consecutive double quotes used as the delimiter require appropriate escaping if they need to appear as data.
- A text block evaluates to a `String`; it has no built-in feature to invoke Java expressions, capture variables from scope, act as a dynamic template, or perform format conversion.

An illustrative path string:

```java
String path = """
        C:\\temp\\notes.txt
        """;
```

In the example, every **two consecutive backslashes** in Java source are decoded into **one backslash** in the string. A single backslash before `t` can produce a tab, and before `n` can produce a newline. Text blocks still follow Java's escape rules.

## 3. Inserting values with `formatted()` or similar APIs

A convenient method since Java 15 is `String.formatted(Object... args)`. It formats according to `Formatter` rules, just like `String.format`. This syntax is still an **explicit method call**, not an automatic interpolation feature of text blocks:

```java
String name = "Lan";
int score = 95;

String report = """
        Learner: %s
        Score: %d
        """.formatted(name, score);

System.out.print(report);
// Learner: Lan
// Score: 95
```

Here `%s` and `%d` are only processed **when calling** `formatted(name, score)`. Without that call, the text block still contains literal `%s` and `%d`. If the formatted text needs a literal percent sign when calling `formatted`, write `%%` in the format string; for instance, `"Progress: 80%%".formatted()` returns `"Progress: 80%"`. Invalid format specifiers or missing arguments can throw `IllegalFormatException` and its subclasses.

You can use `replace("{{name}}", name)` for simple cases, since `String.replace` substitutes literal substrings. Yet that approach also **does not escape** the inserted content automatically. Furthermore, a real template system may need conditionals, loops, valid variable names, and HTML contexts; do not turn `replace` into a general template engine without an explicit design.

## 4. Standalone Java 17+ program

Create `TextBlockContextDemo.java`:

```java
public class TextBlockContextDemo {
    // Only use when inserting into an HTML text node, not every HTML context.
    private static String escapeHtmlText(String input) {
        return input.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;");
    }

    public static void main(String[] args) {
        String name = "Lan <Admin> & Co";

        // No interpolation: placeholder remains intact.
        String literal = """
                Hello, {{name}}!
                """;
        System.out.println("Literal placeholder: " + literal.strip());

        // Inserts data, but does not escape HTML yet.
        String htmlTemplate = """
                <p>Hi, %s!</p>
                """;
        System.out.println("HTML raw: "
                + htmlTemplate.formatted(name).strip());

        // Escape for the HTML text node context before inserting.
        System.out.println("HTML escaped: "
                + htmlTemplate.formatted(escapeHtmlText(name)).strip());

        // Inserting a name with " directly breaks JSON string syntax.
        String jsonTemplate = """
                {"name":"%s"}
                """;
        String jsonName = "Lan \"A\"";
        System.out.println("JSON raw: "
                + jsonTemplate.formatted(jsonName).strip());

        // Text blocks still process Java escapes.
        String path = """
                C:\\temp\\notes.txt
                """;
        System.out.println("Path: " + path.strip());

        // With the closing delimiter on its own line, the text block has a trailing newline.
        System.out.println("Trailing newline: "
                + literal.endsWith("\n"));

        System.out.println("Placeholder unchanged: "
                + literal.contains("{{name}}"));
    }
}
```

Compile and run (Java 17 or newer):

```bash
javac TextBlockContextDemo.java
java TextBlockContextDemo
```

Output:

```text
Literal placeholder: Hello, {{name}}!
HTML raw: <p>Hi, Lan <Admin> & Co!</p>
HTML escaped: <p>Hi, Lan &lt;Admin&gt; &amp; Co!</p>
JSON raw: {"name":"Lan "A""}
Path: C:\temp\notes.txt
Trailing newline: true
Placeholder unchanged: true
```

The `HTML raw` line shows that passing `name` into `%s` only inserts data. If rendered as HTML, characters like `<` and `&` in the data can be interpreted as markup or entities instead of being displayed as plain text. The `escapeHtmlText` helper intentionally demonstrates the **text node context**, where `&`, `<`, and `>` are encoded accordingly. It is not an encoder for every HTML context such as attributes, URLs, JavaScript, or CSS.

The `JSON raw` line produces **invalid JSON** because the double quotes inside `jsonName` are not JSON-escaped. You should not treat the resulting string as a properly serialized JSON object.

## 5. Java escapes differ from target format escapes

When writing JSON, HTML, or queries inside a text block, there can be **two processing layers**:

1. **Java source layer:** The text inside the text block is turned into a `String` by Java, handling newlines, indentation, and Java escape sequences.
2. **Target format layer:** The `String` contents are handed to another reader (an HTML browser, JSON parser, database, etc.), so they must obey the syntax and encoding rules of the receiving system.

An example with `\\` in JSON:

```java
String jsonLiteral = """
        {"path":"C:\\\\data\\\\file.txt"}
        """;
System.out.println(jsonLiteral.strip());
// {"path":"C:\\data\\file.txt"}
```

In this example, **four consecutive backslashes** in Java source become **two backslashes** in the JSON text. The two backslashes in JSON represent one backslash in the path value once the JSON is parsed. This is only an example with static content; for dynamic data, use a JSON serializer.

For **dynamic** data, delegate JSON generation to a serializer library: pass Java values such as `String`, numbers, lists, or objects into the library's API so the serializer produces quotes and standard-compliant escapes. `String.formatted` does not know whether the insertion sits inside a JSON string, a JSON number, or outside a JSON value.

## 6. Escape according to the exact context where data appears

| Target format | Risk when inserting data directly into a text block | Right approach |
| --- | --- | --- |
| HTML **text node** | `<`, `&` can be parsed as markup/entities. | Escape text for the HTML text context, or use an API that creates safe text nodes. |
| HTML attribute | `"` or `'` can close the attribute value; URL attributes also have scheme policies. | Use an attribute-context encoder and validate URLs/schemes when needed; prefer DOM/template APIs with context-aware auto-escaping. |
| JSON | `"`, `\\`, control characters, and newlines in data corrupt the JSON string if inserted raw. | A JSON serializer or JSON writer API that distinguishes values/objects/arrays. |
| XML | Special characters and text vs. attribute positions have distinct rules. | XML APIs/serializers; avoid building XML with ad-hoc string concatenation. |
| SQL | Data containing `'` or SQL syntax can alter the query when concatenated/formatted into SQL text. | `PreparedStatement` with **bound parameters**, do not use `formatted` to insert SQL values. |
| URI / URL | Spaces, `?`, `&`, `#` act as URI component delimiters. | Use URI-building APIs and encode each component properly (path, query parameter, etc.). |
| Regular expression | `.`, `*`, `[`, `\\` are regex operators; replacement strings also treat `$` specially. | `Pattern.quote` for literal search patterns, `Matcher.quoteReplacement` for literal replacements. |

Note that a value that has been "HTML-escaped" is **not thereby safe in JavaScript or SQL**. Escaping rules belong to the **receiving** language/context, not to text block syntax. Do not encode arbitrarily multiple times or apply the same encoder everywhere, as that can corrupt data or introduce double-encoding bugs.

### SQL: text blocks make queries readable, bound parameters pass data safely

This is an illustrative snippet inside a method that already has `Connection connection` and `String username` from `java.sql`:

```java
String sql = """
        SELECT id, username
        FROM users
        WHERE username = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, username);
    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            System.out.println(result.getLong("id"));
        }
    }
}
```

The `PreparedStatement` and `ResultSet` types must be imported from `java.sql`. This is illustrative code that depends on a connection/database, **not a standalone runnable program**. `?` is a placeholder for **a bound SQL value**, not a symbol interpolated by the text block. Even if `username` contains quotes or SQL characters, `setString` passes it through JDBC's parameter mechanism. For **dynamic table or column names**, value placeholders cannot replace identifiers; use an explicit allowlist of valid names rather than concatenating arbitrary identifiers from input.

### JSON: prefer a serializer when values come from outside

With:

```java
String name = "Lan \"A\"";
String json = """
        {"name":"%s"}
        """.formatted(name);
```

`json` contains `{"name":"Lan "A""}` and is invalid. Replacing `"` with `\\"` in a single ad-hoc case still fails to cover `\\`, control characters, newlines, and complex data types. Use a JSON serializer, pass `name` as a **`String` value**, and let the library generate valid JSON text instead of concatenating or formatting strings manually.

## 7. Common misconceptions

**Thinking `{{name}}` or `%s` is substituted right at declaration.** Text blocks do not process templates. Only an explicit call to `formatted`, `replace`, or a dedicated template engine performs substitution.

**Thinking `formatted` escapes HTML/JSON automatically.** `formatted` follows `Formatter` rules and is unaware of target syntax contexts; values containing `<`, `"`, `$`, newlines, or format escapes can make the result broken or unsafe.

**Thinking text blocks are raw strings.** Java still processes Java escapes, strips common indentation, and may keep a trailing LF. Verify the actual string value before passing it to a target-format parser.

**Confusing Java escapes with JSON escapes.** A `\\` sequence in Java source must go through the Java layer **before** the text is read by a JSON parser. When hand-crafting JSON, it is very easy to under- or over-escape; prefer a JSON serializer.

**Using text blocks as SQL injection protection.** Text blocks only make multiline SQL easier to read. Inserting `username` via `formatted(username)` inside SQL provides no parameterization; parameters must be bound via `PreparedStatement`.

**Placing data in the wrong HTML context.** Encoding meant for an HTML text node is not automatically valid for HTML attributes, URLs, JS, or CSS. Choose an encoder or template engine appropriate for the data's position.

**Forgetting percent signs when calling `formatted`.** The string `"Scored 90%"` in a text block is a normal string, yet when passed to `formatted()`, `%` is treated as starting a format specifier. If you want a literal percent sign in a format string, use `%%`.

## 8. Check-your-understanding exercises

1. Given `String user = "Mai"; String s = """` followed by content `Hi, {{user}}!` and the closing delimiter on its own line. Does `s` automatically become `"Hi, Mai!"`? Why?
2. Write a text block representing the HTML snippet `<p>Hello, %s</p>`. Explain when `formatted` inserts data and what step must be performed to protect the **HTML text node**.
3. Given `name = "Lan \\"A\\""`, explain why `{"name":"%s"}`.formatted(name) does not automatically produce valid JSON.
4. Given SQL in a text block `WHERE email = ?`, explain the role of `PreparedStatement.setString` and why you should not change it to `WHERE email = '%s'` with `formatted(email)`.
5. For a path containing `\\`, explain the difference between **escaping in Java source** and **escaping in runtime JSON**.

**Remember:** Text blocks are syntax for writing readable multiline `String` values. Variable insertion requires calling an explicit API; escaping or parameterization must match **the target format and context**. These two responsibilities must never be confused.