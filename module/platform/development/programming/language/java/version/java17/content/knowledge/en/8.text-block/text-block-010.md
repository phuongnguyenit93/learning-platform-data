# Organizing Readable JSON, SQL, and HTML Templates with Text Blocks in Java 17

## 1. What problem do text blocks solve?

When a Java program needs to create multiline content such as JSON, SQL statements, or HTML documents, traditional string syntax often makes source code hard to read:

~~~java
String json = "{\n"
        + "  \"name\": \"Lan\",\n"
        + "  \"active\": true\n"
        + "}";
~~~

Every line must be joined with a plus sign, newlines must be written as `\n`, and double quotes inside the content must be escaped. As templates grow, the JSON or HTML structure gets obscured by Java string syntax.

**Text blocks** allow you to write multiline strings directly between triple double quotes `"""`. This feature was finalized and became stable in Java 15, so it works normally in **Java 17**, without enabling preview features:

~~~java
String json = """
        {
          "name": "Lan",
          "active": true
        }
        """;
~~~

The content looks much closer to the actual JSON format. A text block still produces a `String`; it does not parse JSON, execute SQL, render HTML, or automatically escape dynamic data.

In this lesson, we use text blocks to organize three common content types:

- **JSON:** structured data exchanged between applications and APIs.
- **SQL:** multiline queries that are easy to read and review.
- **HTML:** page layouts or HTML emails with nested elements.

The key point is separating **string formatting in source code** from **safety rules of the target format**. Text blocks make the template readable; JSON serializers, JDBC `PreparedStatement`, and HTML escaping remain responsible for handling data properly.

## 2. Basic syntax

A text block looks like:

~~~java
String message = """
    This is the first line.
    This is the second line.
    This is the third line.
    """;
~~~

A few syntax rules:

1. The opening `"""` must be followed by a line terminator. Do not put content right after the opening delimiter on the same line.
2. Content can span multiple lines and contain single or double quotes without escaping them as in regular strings.
3. The closing `"""` marks the end of the content. The closing delimiter's indentation affects how leading whitespace is stripped.
4. A text block is an expression yielding a `String`, so it can be assigned to variables, returned from methods, or passed as arguments like any other string.

**Invalid** example:

~~~java
// Invalid: opening delimiter must have a line terminator immediately after it.
String invalid = """Hello""";
~~~

Valid way:

~~~java
String valid = """
        Hello
        """;
~~~

### A text block is not a separate data type

~~~java
String text = """
        Java
        17
        """;

System.out.println(text instanceof String); // true
~~~

You can still call `String` methods such as `length()`, `contains()`, `strip()`, or `formatted()`. The variable's type is `String`, not `TextBlock`.

## 3. Leading whitespace and closing delimiter position

This is the most important aspect to understand when creating indented templates. The Java compiler applies the **incidental indentation** (*non-meaningful indentation*) rule to strip common leading whitespace, allowing code to live inside a class without adding all the Java code's indentation into the resulting string.

Example:

~~~java
String html = """
        <section>
            <h1>Orders</h1>
        </section>
        """;
~~~

The string value looks like:

~~~text
<section>
    <h1>Orders</h1>
</section>
~~~

The common leading spaces before each content line have been stripped; the relative indentation of `<h1>` is preserved.

### 3.1. The closing delimiter participates in determining indentation

Compare two ways of placing the closing delimiter.

**Closing delimiter aligned with content:**

~~~java
String first = """
        alpha
        beta
        """;
~~~

Output:

~~~text
alpha
beta
~~~

**Closing delimiter at column 0:**

~~~java
String second = """
        alpha
        beta
""";
~~~

In the second case, the closing delimiter has no leading whitespace. The minimum common indentation becomes 0, so the eight spaces before `alpha` and `beta` are kept in the string value.

Therefore, when you want text block content free of unintended leading spaces, align the closing delimiter appropriately with the content.

### 3.2. Blank lines and trailing whitespace

Java handles blank lines when computing indentation; whitespace-only lines do not reduce the common indentation the way a content line does. Trailing whitespace on lines is stripped from text block content. This prevents templates from accidentally carrying alignment spaces from an editor.

If a space at the end of a line **is meaningful**, do not type a literal space hoping the editor preserves it. Express it explicitly with the `\s` escape:

~~~java
String withTrailingSpace = """
        value\s
        next
        """;
~~~

`\s` creates exactly one space in the resulting string. This is a Java escape sequence, not special JSON or SQL syntax.

### 3.3. Line-ending normalization

In text blocks, content line terminators are normalized to line feed `\n` in the resulting string. Thus source code can be checked out on Windows or Linux without string contents directly depending on the file's line-ending style.

If a protocol or output format specifically requires CRLF, convert line endings explicitly at the output step. Do not assume a text block preserves CRLF from the source file.

## 4. Escape sequences in text blocks

Text blocks reduce the need to escape double quotes, yet **do not turn off Java's escape rules**. Escape sequences are still processed when building the resulting string.

| Written in source code | Character / value in `String` |
|---|---|
| `\n` | Line feed (newline). |
| `\t` | Tab. |
| `\"` | One double quote. |
| `\\` | One backslash `\`. |
| `\s` | One U+0020 space. |
| `\` immediately before line terminator | Joins lines, omitting that line terminator and post-processed leading indentation of the next line. |

### 4.1. Joining lines with a backslash

When you want to wrap a long line across multiple source lines while keeping the result on one line, use line continuation:

~~~java
String sql = """
        SELECT id, \
        status, \
        created_at
        FROM orders
        """;
~~~

The `SELECT` portion in the result is a single line:

~~~text
SELECT id, status, created_at
FROM orders
~~~

Line continuation deletes the line terminator immediately after `\`; it does not automatically insert a space. Therefore, to prevent words from running together, place a space **before** `\` as shown above. For SQL, JSON, or HTML, keeping each logical line on its own output line is usually clearer to read and debug; only join lines when the target format requires it.

### 4.2. Backslashes in JSON

JSON uses `\` to represent escapes such as `\"`, `\\`, and `\n`. However, text blocks also process Java escapes. So to make the resulting string contain the two characters `\` and `n`, Java source must say `\\n`.

Example:

~~~java
String json = """
        {
          "message": "first line\\nsecond line",
          "path": "C:\\\\temp\\\\orders"
        }
        """;
~~~

In the resulting Java string, the JSON payload has the content:

~~~json
{
  "message": "first line\nsecond line",
  "path": "C:\\temp\\orders"
}
~~~

Here, `\n` and `\\` remain **JSON** escapes when the string is parsed. Java already processed one layer of escapes earlier:

- Java source `\\n` → Java String contains `\n` (backslash and `n`) → JSON parser interprets that as a line feed inside the value.
- Java source `\\\\` → Java String contains `\\` (two backslashes) → JSON parser interprets that as one `\` in the path.

This is a frequent reason a JSON template looks right in source code yet fails to parse: you must distinguish **Java language** escapes from **JSON** escapes.

### 4.3. Double quotes in JSON, HTML, and SQL

Inside text blocks, single and double quotes can be written directly:

~~~java
String json = """
        {
          "title": "Java 17",
          "description": "Text blocks make multiline strings readable"
        }
        """;
~~~

You do not need to write `\"title\"` just to quote JSON property names. Java only cares about three consecutive double quotes that close the text block; if content truly needs to contain `"""`, escape at least one quote so the text block does not end prematurely.

## 5. Organizing JSON templates

JSON often contains multiple levels of objects, arrays, and values, so text blocks make templates noticeably easier to read.

### 5.1. Static JSON template

~~~java
String response = """
        {
          "id": 105,
          "status": "PAID",
          "items": [
            {
              "sku": "BOOK-17",
              "quantity": 2
            },
            {
              "sku": "PEN-02",
              "quantity": 5
            }
          ],
          "active": true
        }
        """;
~~~

When data is completely fixed, a text block is a straightforward way to write it. You can pass `response` to an HTTP client or JSON library for parsing or verification.

### 5.2. Do not splice dynamic data carelessly into JSON

A tempting shortcut is using `formatted()`:

~~~java
String json = """
        {
          "customer": "%s",
          "status": "PAID"
        }
        """.formatted(customerName);
~~~

This is safe only if `customerName` is controlled data guaranteed not to contain characters that break JSON. `String.formatted()` merely substitutes the `%s` placeholder; it **does not JSON-escape strings**, does not validate JSON, and does not turn data into valid JSON values.

For instance, if `customerName` contains double quotes, newlines, or backslashes, the resulting string can become invalid JSON or have an unintended structure. Do not try to patch this by ad-hoc replacement of a few characters.

For dynamic data in real applications, use a **JSON serializer** (such as Jackson or Gson) so the library handles escaping and proper type representation. Text blocks are suitable for:

- Writing fixed sample payloads in documentation, examples, or test fixtures.
- Creating static JSON in an internal tool with controlled input.
- Keeping illustrative structures close to real JSON for easy comparison.

### 5.3. Dynamic JSON: distinguishing templates from serializers

If you need to produce a response object from data:

~~~java
record CustomerResponse(long id, String name, boolean active) {
}
~~~

pass that object to the JSON library your project uses instead of interpolating each field into a text block. A serializer handles quotes, escapes, `null`, numbers, booleans, collections, and nested objects according to JSON rules.

Text blocks do not replace a JSON library. JDK 17 has no general-purpose JSON API in Java SE to automatically serialize arbitrary objects to JSON.

### 5.4. When is `formatted()` useful?

`String.formatted()` has been available since Java 15 and works in Java 17:

~~~java
String template = """
        {
          "service": "%s",
          "version": %d
        }
        """;

String example = template.formatted("orders", 17);
~~~

It is helpful for display templates or controlled data. Keep in mind:

- `%s`, `%d`, `%f` are Java formatter placeholders, not JSON syntax.
- A literal `%` in a format string must be written as `%%`.
- Argument order must match placeholders.
- `formatted()` is not a serializer and does not JSON-escape values.

## 6. Organizing multiline SQL statements

SQL often spans many clauses: `SELECT`, `FROM`, `JOIN`, `WHERE`, `GROUP BY`, `ORDER BY`. Text blocks keep each clause on its own line, making conditions and joins easy to review.

### 6.1. Static SQL template

~~~java
String sql = """
        SELECT
            o.id,
            o.status,
            o.created_at,
            c.name AS customer_name
        FROM orders o
        JOIN customers c
            ON c.id = o.customer_id
        WHERE o.created_at >= DATE '2026-01-01'
          AND o.status <> 'CANCELLED'
        ORDER BY o.created_at DESC
        """;
~~~

Text blocks do not validate SQL syntax; the database and JDBC driver still verify whether the query is valid for the target dialect. The example above illustrates query layout and alignment without assuming all database systems support identical syntax.

### 6.2. Using `PreparedStatement` for dynamic data

When filter values come from users or external data, **never concatenate strings directly into SQL**:

~~~java
// Unsafe: avoid splicing input into the statement.
String sql = "SELECT id FROM users WHERE email = '" + email + "'";
~~~

Instead, use `?` placeholders and bind parameters via JDBC:

~~~java
String sql = """
        SELECT id, email, display_name
        FROM users
        WHERE email = ?
        """;

try (var statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);

    try (var resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long id = resultSet.getLong("id");
            String displayName = resultSet.getString("display_name");
            System.out.println(id + ": " + displayName);
        }
    }
}
~~~

In this example:

- The text block keeps the SQL query in a readable multiline layout.
- `?` is a positional parameter supported by JDBC.
- `setString(1, email)` passes the value for the first placeholder.
- `PreparedStatement` separates data from SQL structure, helping prevent SQL injection via **parameter values**.
- `try-with-resources` closes the statement and result set automatically.

`connection` is a `java.sql.Connection` already established by the application. The snippet demonstrates the query part and does not include connection or driver setup.

### 6.3. Placeholders cannot be used for table or column names

JDBC placeholders represent **values**, not SQL identifiers. For example:

~~~java
String sql = "SELECT * FROM ? WHERE id = ?";
~~~

cannot use the first parameter to pass a table name. If a column or table name must vary, select it from a program-defined allowlist:

~~~java
String sortColumn = switch (requestedSort) {
    case "date" -> "created_at";
    case "name" -> "display_name";
    default -> "created_at";
};

String sql = """
        SELECT id, display_name
        FROM users
        ORDER BY %s
        """.formatted(sortColumn);
~~~

This example is safe only when `sortColumn` is chosen strictly from program-controlled constants as shown above. Never pass arbitrary column names from a request directly into `formatted()`. For values like email, ID, dates, and status, use placeholders and parameter binding.

### 6.4. Text blocks do not replace query logic verification

A clean SQL template does not guarantee a correct query. Always verify:

- Whether tables and aliases are correct.
- Whether `JOIN` conditions could unexpectedly duplicate rows.
- Whether `WHERE` enforces the proper data scope and access control.
- Whether filter conditions handle `NULL` properly according to SQL logic (`= NULL` is not equivalent to `IS NULL`).
- Whether dynamic values use appropriate placeholders or allowlists.
- Whether the query has proper indexes and result limits.

Text blocks only make **source code containing SQL readable**; they do not optimize queries or protect against injection on their own.

## 7. Organizing HTML templates

HTML has deeply nested tags and is often verbose. Text blocks keep document structure close to what the browser receives.

### 7.1. Static HTML template

~~~java
String html = """
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Order report</title>
          </head>
          <body>
            <main>
              <h1>Order report</h1>
              <p class="status">PAID</p>
            </main>
          </body>
        </html>
        """;
~~~

This is a fixed template, suitable for illustration or generating static content. Tags and indentation remain clear in Java code.

### 7.2. Dynamic data must be escaped for HTML context

Never insert user names, comments, addresses, or request data directly into HTML:

~~~java
// Unsafe if customerName comes from user input.
String html = """
        <h1>Welcome, %s</h1>
        """.formatted(customerName);
~~~

If `customerName` contains text resembling HTML tags or scripts, the browser may interpret it as markup instead of text. This is an XSS (*cross-site scripting*) risk.

In real web applications:

- Prefer a template engine with **auto-escaping** enabled, such as an engine safely configured for HTML.
- If constructing HTML manually, use an escaping library suited to the **context** (text body, HTML attribute, URL, JavaScript, or CSS).
- Do not rely on one simple character-replacement function for all contexts; escaping rules for attributes, URLs, and JavaScript differ.
- Avoid putting untrusted data into `<script>`, event attributes like `onclick`, CSS, or URLs without specialized handling.

A text block can hold a **static HTML skeleton**; dynamic data should be inserted via a safe template mechanism. `String.formatted()` does not automatically HTML-escape.

### 7.3. Example of the boundary between template and data

A template can be stored in a text block:

~~~java
String template = """
        <!doctype html>
        <html lang="en">
          <body>
            <h1>Order report</h1>
            <p class="customer">CUSTOMER_PLACEHOLDER</p>
          </body>
        </html>
        """;
~~~

This illustrates structure. In a real application, do not replace placeholders by ad-hoc string concatenation if the value may be untrusted. Pass the template through a template engine or apply context-appropriate HTML escaping before placing data into its slot.

## 8. Comparing the three formats and text block usage

| Format | Where are text blocks helpful? | What needs dedicated handling? |
|---|---|---|
| JSON | Sample payloads, fixtures, nested objects/arrays. | Serialize dynamic data and JSON-escape properly; text blocks are not a JSON serializer. |
| SQL | Queries with many clauses, CTEs, joins, and filters. | `PreparedStatement` for values; allowlists for dynamic table/column names; check dialect and data permissions. |
| HTML | Static documents, email templates, or page skeletons. | Auto-escaping/template engines; context-aware escaping to prevent XSS. |

A sound workflow:

1. Write the static structure with a text block for readability.
2. Identify which positions hold dynamic data and whether the data source is trusted.
3. Use the corresponding serializer, prepared statement, or template engine.
4. Verify the output using a real parser, database, or browser.
5. Write tests for output content and special characters.

Do not use the same string substitution approach across all three formats: JSON, SQL, and HTML have different syntaxes and risks.

## 9. Combining text blocks with methods and constants

If a template is reused across multiple places, place it in a constant or method to avoid duplication:

~~~java
public final class Templates {
    private Templates() {
    }

    public static final String HEALTH_RESPONSE = """
            {
              "status": "ok",
              "version": 17
            }
            """;

    public static String selectOrdersByStatus() {
        return """
                SELECT id, status
                FROM orders
                WHERE status = ?
                ORDER BY created_at DESC
                """;
    }
}
~~~

Choose `static final` when content is a reusable constant independent of runtime data. Use a method if you need to return a template tailored to a configuration or variant. Avoid storing one overly huge generic template just because it is a text block; split constants or methods by responsibility for easier maintenance.

### 9.1. Combining with `formatted()`

Methods can be chained directly after a text block's closing delimiter:

~~~java
String report = """
        Report: %s
        Total: %d
        """.formatted("Orders", 12);
~~~

This produces the resulting string with placeholders replaced. When using format strings, literal `%` characters in static content must be written as `%%` so they are not parsed as placeholder starts. For example:

~~~java
String progress = """
        Completion: 100%%
        """.formatted();
~~~

`formatted()` is still purely string formatting. It does not replace a JSON serializer, SQL parameter binding, or HTML escaping.

## 10. Running an example in Java 17

Create file `TextBlockDemo.java`:

~~~java
public final class TextBlockDemo {
    private TextBlockDemo() {
    }

    public static void main(String[] args) {
        String json = """
                {
                  "service": "orders",
                  "enabled": true,
                  "version": 17
                }
                """;

        String sql = """
                SELECT id, status
                FROM orders
                WHERE status = ?
                ORDER BY created_at DESC
                """;

        String html = """
                <!doctype html>
                <html lang="en">
                  <body>
                    <h1>Order report</h1>
                    <p>Static example</p>
                  </body>
                </html>
                """;

        String escapedJson = """
                {
                  "message": "first line\\nsecond line",
                  "path": "C:\\\\temp\\\\orders"
                }
                """;

        System.out.println("JSON:");
        System.out.println(json);
        System.out.println("SQL:");
        System.out.println(sql);
        System.out.println("HTML:");
        System.out.println(html);
        System.out.println("JSON with escapes:");
        System.out.println(escapedJson);
    }
}
~~~

From the terminal in the directory containing the file, run:

~~~bash
javac --release 17 -encoding UTF-8 TextBlockDemo.java
java TextBlockDemo
~~~

`--release 17` instructs the compiler to emit bytecode and use APIs compatible with Java 17. If using JDK 17, you can check versions beforehand with:

~~~text
java -version
javac -version
~~~

The example requires no Maven, Gradle, or third-party libraries. It illustrates how text blocks produce static JSON, SQL, and HTML strings; dynamic data and database/web interactions still require the dedicated mechanisms covered above.

## 11. Common mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Syntax error at `"""` | Using a JDK/target older than Java 15 or placing content right after opening delimiter. | Use Java 17 and put a line terminator immediately after the opening delimiter. |
| Resulting string has extra leading spaces | Closing delimiter sits at a lower column than expected, or common indent is 0. | Align closing delimiter with desired margin. |
| JSON template turns `\n` into an actual newline inside a value | Wrote Java `\n` when intending to keep JSON `\n` escape. | Write `\\n` in Java source. |
| Windows path inside JSON fails to parse | Missing `\` escapes for both Java and JSON. | Write both escape layers properly, or use a JSON serializer. |
| SQL fails near `?` | Placed placeholder at a table/column name or forgot to bind parameter. | Placeholders are only for values; use an allowlist for identifiers. |
| SQL injection despite using a text block | Concatenating untrusted data directly into the SQL string. | Use `PreparedStatement` and bind values. |
| HTML renders tags/scripts from user data | Dynamic data was not escaped or template engine lacks auto-escaping. | Use a safe template engine and context-aware escaping. |
| `formatted()` throws a format error | `%` placeholder doesn't match argument or literal `%` wasn't written as `%%`. | Check placeholders and arguments; skip formatting if unnecessary. |
| Assuming text blocks are raw strings | Java escape sequences are still processed. | Distinguish Java string syntax from target format escapes. |

### Distinguishing whitespace and line continuation

When output is unexpected, inspect three things in order:

1. Placement of opening and closing delimiters.
2. Indentation levels of content lines.
3. `\s`, `\n`, `\\` escapes, or `\` line continuation.

Do not randomly add or delete spaces to "make it work". Determine the exact character sequence you expect and adjust source code accordingly.

## 12. Practice exercises

### Exercise 1 — Convert concatenated string to text block

Convert:

~~~java
String html = "<ul>\n"
        + "  <li>Java</li>\n"
        + "  <li>SQL</li>\n"
        + "</ul>";
~~~

into a text block so the resulting string keeps the same structure and has no extra leading whitespace.

### Exercise 2 — Two-layer JSON escaping

Write a text block producing JSON with:

- Property `message` containing two lines of text separated by JSON escape `\n`.
- Property `path` containing Windows path `D:\data\orders`.

Explain why Java source needs more `\` characters than appear in the JSON value.

### Exercise 3 — Safe SQL

Write a multiline query finding orders by `customer_id` and `status`, sorted newest first. Use `?` for both values, then write the `PreparedStatement` code binding parameters in order. Explain why `?` cannot be used to pass the sort column name.

### Exercise 4 — HTML with dynamic data

Write a text block as an HTML skeleton for a page displaying a customer's name. Then describe how to insert the customer's name using a template engine with auto-escaping or an appropriate escaping library. Explain the risk of calling `.formatted(customerName)` directly.

### Exercise 5 — Indentation and closing delimiter

Create two text blocks with content `alpha` and `beta`: one with the closing delimiter aligned with the content, and one with the closing delimiter at column 0. Predict the number of leading spaces in both results and verify by printing square brackets around the strings.

### Self-check hints

- Exercise 1: Use a text block with the closing delimiter aligned to the common indentation; the result has three HTML lines.
- Exercise 2: Java source `\\n` produces the two characters `\` and `n` for JSON; Java source `\\` produces one `\` in an ordinary string, while JSON needs `\\` to represent one `\` in a value.
- Exercise 3: `WHERE customer_id = ? AND status = ?`; bind with `setLong(1, customerId)` and `setString(2, status)`. Column names are SQL structure, not values.
- Exercise 4: `.formatted()` does not HTML-escape; use a safe template/escaping mechanism.
- Exercise 5: The closing delimiter participates in indentation calculation; at column 0, content indentation is preserved.

## 13. Principles to apply in projects

- Use text blocks when strings have multiline structure and keeping source close to actual content helps readability.
- Align the closing delimiter to control leading spaces; use `\s` when a trailing space is meaningful.
- Distinguish Java escapes from JSON, SQL, or HTML escapes.
- For dynamic JSON, use a serializer; for dynamic SQL, use `PreparedStatement`; for dynamic HTML, use a template engine with auto-escaping or context-aware escaping.
- Do not treat `formatted()` as a security mechanism or serializer. It only substitutes string placeholders.
- Verify final output using a JSON parser, database, or browser; a string that looks readable in source code is not automatically valid in the receiving system.
- Java 17 supports text blocks stably; no preview flag is required.

Text blocks make JSON, SQL, and HTML templates clear, readable, and easy to edit. The greatest value comes from pairing this syntax with the right data-processing tools: serializers for JSON, parameterization for SQL, and context-aware escaping for HTML.

### References

- [Java Language Specification, Java SE 17 — Section 3.10.6: Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6).
- [Oracle Java 17 — Text Blocks](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html).
- [JDBC API — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html).
- [Java SE 17 API — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html).
