# Using `formatted()` with Text Blocks to Substitute Values and Its Limits When Building SQL

In Java 17, **text blocks** make multiline SQL queries easy to read, while **`String.formatted(...)`** substitutes format specifiers such as `%s` and `%d` with arguments. These two features are frequently combined to construct a clearly structured SQL string.

However, two responsibilities must be separated:

- `formatted()` only **produces a string with format specifiers replaced**. It does not understand SQL, add quotes automatically, escape data according to database rules, or bind parameters.
- For **values supplied by users or external systems**, use `PreparedStatement` and `?` parameter placeholders. That is how JDBC passes values separately from the SQL statement.

This lesson focuses on where to use `formatted()` appropriately, its limitations when building SQL, and how to combine text blocks with JDBC safely in Java 17.

> **Version:** Both text blocks and `String.formatted(...)` have been standard since Java 15, so they work stably in Java 17 without `--enable-preview`.

## 1. Text blocks and `formatted()` do two different jobs

A text block is a multiline string syntax opened with three double quotes `"""`. Example:

~~~java
String sql = """
        SELECT id, name
        FROM users
        WHERE active = true
        ORDER BY name
        """;
~~~

This string is easier to read than concatenating multiple pieces with `+` or manually writing `\n` newline characters.

`formatted()` is a method on `String` that uses formatting syntax similar to `String.format(...)`:

~~~java
String message = "Hello, %s!".formatted("An");
System.out.println(message);
~~~

Output:

~~~text
Hello, An!
~~~

You can call that method directly on a text block:

~~~java
String message = """
        Hello, %s!
        You are learning Java %d.
        """.formatted("An", 17);
~~~

Here:

- The text block supplies the multiline content.
- `%s` and `%d` are **format specifiers**.
- The arguments `"An"` and `17` are placed into the corresponding positions.
- The returned value is still a `String` object; the original template string is not mutated.

**Do not treat `formatted()` as special SQL syntax.** It operates on any Java string and does not parse database statement semantics.

## 2. Syntax and common format specifiers

Usage:

~~~java
String result = "Template %s has %d items".formatted("A", 3);
~~~

Equivalent in meaning to:

~~~java
String result = String.format("Template %s has %d items", "A", 3);
~~~

`String.formatted(...)` was added in Java 15. It uses `Formatter`'s formatting mechanism.

| Specifier | Data type / meaning | Example |
|---|---|---|
| `%s` | String representation via `toString()` | `"Java".formatted()` with no argument fails if `%s` exists; use `"Hello %s".formatted("Java")` |
| `%d` | Decimal integer | `"ID=%d".formatted(25)` |
| `%f` | Decimal floating-point number | `"Price=%.2f".formatted(12.5)` |
| `%b` | Boolean value | `"active=%b".formatted(true)` |
| `%c` | Character | `"Char=%c".formatted('A')` |
| `%n` | Platform-specific line separator | Usually unnecessary in SQL text blocks |
| `%%` | Literal percent sign | `"Completed %d%%".formatted(80)` yields `80%` |

Example:

~~~java
String report = """
        ID: %d
        Name: %s
        Score: %.2f
        Completed: %d%%
        """.formatted(1024, "Java", 8.756, 80);

System.out.println(report);
~~~

Resulting content:

~~~text
ID: 1024
Name: Java
Score: 8.76
Completed: 80%
~~~

### 2.1. Argument indices and ordering

Normally, specifiers consume arguments in order of appearance:

~~~java
String text = "%s has ID %d".formatted("An", 12);
~~~

You can specify argument positions:

~~~java
String text = "%2$d - %1$s".formatted("An", 12);
~~~

Output:

~~~text
12 - An
~~~

This is helpful when reordering display output. For SQL statements, avoid complex format templates so readers can clearly tell which component is inserted into the statement.

### 2.2. Width and precision formatting

Some examples:

~~~java
String a = "%08d".formatted(42);       // 00000042
String b = "%.2f".formatted(3.14159);  // 3.14
String c = "%-10s".formatted("Java");  // Java left-aligned
~~~

Flags, width, and precision serve **display formatting**. They do not validate business data or SQL column types.

For example, `%.2f` rounds a floating-point representation according to formatting rules; it is not a standard way to turn a monetary amount into a SQL literal.

### 2.3. Formatting errors occur at runtime

If a format specifier does not match its argument, `formatted()` can throw an exception in the `IllegalFormatException` family.

~~~java
// Error: %d expects an integer type, but the argument is a String.
String sql = "WHERE id = %d".formatted("ABC");
~~~

Common mistakes:

- Missing an argument for a specifier, e.g., `"ID=%d".formatted()`.
- Passing an incompatible argument type, e.g., `%d` with a string.
- Writing malformed specifier syntax.
- Forgetting to double a literal percent sign as `%%` when a string is processed by `Formatter`.

These are **Java string formatting** errors, not SQL syntax errors.

## 3. Using text blocks with `formatted()` to build SQL templates

Syntactically, you can write:

~~~java
String template = """
        SELECT id, name
        FROM users
        WHERE status = '%s'
        """;

String sql = template.formatted("ACTIVE");
~~~

The result is a SQL string with `%s` replaced by `ACTIVE`.

However, this example only demonstrates string substitution. **Never use this approach to put runtime data into executable SQL**, even when the value is wrapped in single quotes. `formatted()` does not escape quotes, backslashes, or special SQL syntax.

### 3.1. `%s` does not automatically add SQL quotes

The snippet:

~~~java
String query = "WHERE name = %s".formatted("An");
~~~

produces:

~~~sql
WHERE name = An
~~~

If written as:

~~~java
String query = "WHERE name = '%s'".formatted("An");
~~~

then the result is:

~~~sql
WHERE name = 'An'
~~~

Single quotes are present because **the template author typed them**, not because `%s` understands SQL strings.

The problem is that input data can contain characters that alter the query structure. For example, the name `O'Brien` prematurely closes the SQL literal if inserted directly into the string. Maliciously crafted data can even change conditions or statement structure.

**Do not solve this by manually replacing quotes or adding quotes around values.** Escaping rules depend on literal type and database engine; manual handling easily misses edge cases.

### 3.2. `%d` and `%f` are not parameter binding either

One might think inserting numbers with `%d` is safe because there are no quotes:

~~~java
// Do not use this to pass runtime values into SQL.
String sql = "SELECT * FROM orders WHERE id = %d".formatted(orderId);
~~~

Even when `orderId` is an integer, this approach still mixes data with SQL structure, generates a new string for every value, and bypasses JDBC's typed parameter binding. It also fails to leverage driver-level parameter handling.

With `double` or `float`, formatting can also depend on the default locale—for instance, the decimal separator may vary across environments. SQL needs values handled per DB/driver rules, not display-formatted number strings.

Use `PreparedStatement` for **all runtime values**, whether strings, numbers, dates, or booleans.

## 4. The right way: text blocks for structure, PreparedStatement for values

This is the recommended pattern in Java 17 applications:

~~~java
String sql = """
        SELECT id, name, email
        FROM users
        WHERE email = ?
          AND status = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);
    statement.setString(2, status);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long id = resultSet.getLong("id");
            String name = resultSet.getString("name");

            System.out.println(id + ": " + name);
        }
    }
}
~~~

Explanation:

1. The text block keeps the SQL query multiline, readable, and easy to maintain.
2. `?` is a JDBC **parameter marker**, representing a value.
3. `setString(1, email)` binds the value for the first question mark.
4. `setString(2, status)` binds the value for the second question mark.
5. The driver receives the SQL statement and parameter values separately, then handles them according to the protocol and corresponding types.

A value like `O'Brien` is transmitted as data and cannot close a literal to alter SQL syntax.

**Parameter numbering starts at 1**, not 0. If you reorder `?` placeholders in SQL, you must update the corresponding `setXxx` indices.

### 4.1. Using the same parameter in multiple places

Each `?` is a separate position. If the same value must appear twice, you usually bind it twice:

~~~java
String sql = """
        SELECT id, name
        FROM users
        WHERE created_by = ?
           OR updated_by = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, username);
    statement.setString(2, username);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("name"));
        }
    }
}
~~~

JDBC does not support named parameter syntax like `:username` in standard `PreparedStatement`. Question marks are numbered sequentially by appearance. Some libraries add named parameters, but that is a library feature rather than standard `String.formatted()` syntax.

### 4.2. Null values and data types

When binding data, use the appropriate setter:

| Java type / data | Common JDBC setter |
|---|---|
| `String` | `setString(index, value)` |
| `int` | `setInt(index, value)` |
| `long` | `setLong(index, value)` |
| `BigDecimal` | `setBigDecimal(index, value)` |
| `LocalDate` | `setObject(index, value)` (depends on driver/JDBC) |
| Boolean | `setBoolean(index, value)` |

For null values with a specific SQL type, you can use `setNull(index, Types.VARCHAR)`, `setNull(index, Types.INTEGER)`, etc. Choosing the right SQL type helps the driver handle null accurately.

Do not turn null into the literal string `"null"` via `formatted("%s")`; that value is completely different from SQL `NULL`.

## 5. Key limitation: `?` only binds values, not table/column names

A common design mistake is assuming placeholders work for every SQL element:

~~~java
// Does not work as intended: ? cannot represent a table or column name.
String sql = """
        SELECT *
        FROM ?
        ORDER BY ?
        """;
~~~

In JDBC, `?` represents a **data value**, not a SQL identifier or keyword. The driver will not substitute the first question mark with a table name and the second with a column name that way.

Elements that typically cannot be bound via parameter markers:

- Database, schema, table, and column names.
- Keywords such as `ASC` or `DESC`.
- Operators, function names, or SQL syntax fragments.
- A multi-item list like `1, 2, 3` via a single parameter.

### 5.1. For dynamic identifiers, use an allowlist

If an application lets users choose a sort column, map that choice to column names **controlled by the program**:

~~~java
enum UserSort {
    NAME,
    CREATED_AT
}

String orderColumn = switch (sort) {
    case NAME -> "name";
    case CREATED_AT -> "created_at";
};

String orderDirection = descending ? "DESC" : "ASC";

String sql = """
        SELECT id, name, created_at
        FROM users
        WHERE status = ?
        ORDER BY %s %s
        """.formatted(orderColumn, orderDirection);

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, status);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("id"));
        }
    }
}
~~~

In this example:

- `sort` is an enum, so only predefined options exist.
- `orderColumn` can only be `name` or `created_at`.
- `orderDirection` can only be `ASC` or `DESC`.
- `status` is still bound with `?`.

This is an appropriate case for `formatted()`: inserting **program-controlled SQL structure**, never arbitrary data. In real systems, identifiers may also require database-specific quoting rules; allowlisting remains the first control step.

**Do not** write:

~~~java
// DANGEROUS: do not pass raw input directly into an identifier.
String sql = """
        SELECT id, name
        FROM users
        ORDER BY %s
        """.formatted(userProvidedColumn);
~~~

Even when a user specifies a column name, map it through an enum or allowlist map before building the SQL query.

### 5.2. Using `formatted()` to generate placeholder counts, not values

A useful case is an `IN (...)` clause with a variable number of elements. You can generate **the count of question marks** matching the list size and then bind each value individually:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Collections;
import java.util.List;

static void findUsersByIds(Connection connection, List<Long> ids)
        throws SQLException {

    if (ids == null || ids.isEmpty()) {
        // IN () is usually invalid; business decision here is no results.
        return;
    }

    String placeholders = String.join(
            ", ",
            Collections.nCopies(ids.size(), "?")
    );

    String sql = """
            SELECT id, name
            FROM users
            WHERE id IN (%s)
            """.formatted(placeholders);

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        for (int i = 0; i < ids.size(); i++) {
            statement.setLong(i + 1, ids.get(i));
        }

        try (ResultSet rs = statement.executeQuery()) {
            while (rs.next()) {
                System.out.println(
                        rs.getLong("id") + ": " + rs.getString("name")
                );
            }
        }
    }
}
~~~

For example, if the list has three IDs, the generated placeholder string becomes:

~~~sql
WHERE id IN (?, ?, ?)
~~~

The actual values are bound sequentially with `setLong(1, ...)`, `setLong(2, ...)`, `setLong(3, ...)`.

Here `formatted()` receives only the placeholder string generated by the program from the **element count**. It never receives ID values. This is a controlled way to combine text blocks, `formatted()`, and `PreparedStatement`.

Define empty-list behavior clearly: return empty results, omit the condition, or use an always-false predicate as required. Never emit `IN ()` expecting all databases to handle it identically.

## 6. Percent signs in SQL and `formatted()`

`Formatter` treats `%` as the start of a format specifier. Therefore, when `.formatted(...)` is called on a text block, literal percent signs must be written as `%%`.

Pure formatting example:

~~~java
String template = "WHERE score >= %d%%";
String result = template.formatted(80);
~~~

Result:

~~~sql
WHERE score >= 80%
~~~

In SQL, `%` can also be a `LIKE` wildcard. If you **actually** call `formatted()` on a template containing a literal wildcard, you must write `%%` so `Formatter` outputs one `%`:

~~~java
String displayOnly = """
        SELECT id
        FROM users
        WHERE name LIKE '%%'
        """.formatted();
~~~

After formatting, the string contains:

~~~sql
WHERE name LIKE '%'
~~~

The example above only illustrates the `Formatter` rule. In real queries, write:

~~~java
String sql = """
        SELECT id
        FROM users
        WHERE name LIKE ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "%" + searchTerm + "%");

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("id"));
        }
    }
}
~~~

In this `PreparedStatement` query, `.formatted()` is not called, so the SQL wildcard uses a normal single `%`. The pattern value is bound as a parameter.

## 7. Do text blocks strip whitespace automatically?

Text blocks follow **incidental indentation** rules: Java determines non-meaningful indentation and strips the common margin based on content lines and the closing delimiter position. It does not understand or reformat SQL.

Example:

~~~java
String sql = """
        SELECT id, name
        FROM users
        WHERE active = true
        """;
~~~

Source indentation primarily helps readers. The resulting string still retains lines and newlines per text block rules.

Points to keep in mind:

- The closing `"""` position affects how much indentation is stripped.
- Blank lines and spaces can affect the resulting content.
- A trailing newline is usually preserved if the closing delimiter sits on its own line as shown.
- Text blocks still process escape sequences like regular Java strings.
- Text blocks do not strip spaces inside SQL literals, fix column names, or validate SQL syntax.

If you need to inspect the actual generated SQL string, print it in a dev environment or use an appropriate logger. When logging parameterized queries, avoid logging sensitive data such as passwords, tokens, or personal information.

### 7.1. Special escape sequences in text blocks

Two escapes worth knowing:

| Escape | Meaning |
|---|---|
| `\s` | Produces one space, useful for preserving trailing spaces at the end of a line |
| `\` before a newline | Joins source lines without putting that newline into the resulting string |

Example:

~~~java
String text = """
        SELECT id, \
        name
        FROM users
        """;
~~~

`SELECT id, \` is joined onto the same line in the resulting string. However, for multiline SQL, keeping line breaks is usually clearer than unnecessary line continuation.

## 8. Limitations of `formatted()` when building SQL

You can use the table below to decide what to do and what not to do:

| Need | Use `formatted()`? | Appropriate approach |
|---|---|---|
| Write readable multiline SQL | Not needed just for this | Text block |
| Insert user-supplied String values into `WHERE` | **No** | `PreparedStatement` + `setString` |
| Insert runtime IDs, quantities, dates | **No** | Parameter markers + appropriate setters |
| Insert user-supplied column or table names | **Not directly** | Allowlist/enum before building structure |
| Insert `ASC`/`DESC` from a choice | Only after mapping to a valid constant set | Allowlist/enum |
| Generate `?` count for an `IN` list | Possible | Generate placeholders by element count, bind each value |
| Generate DDL or migration SQL from trusted metadata | Possible, with controls | Validate identifiers and dialect |
| Generate messages or preview SQL for debugging | Possible | Never execute that string as a substitute for binding data |

Key limitations:

1. **No parameter binding:** the method only substitutes string contents before sending SQL.
2. **No SQL escaping:** `%s` does not handle quotes, comments, semicolons, or special characters.
3. **No SQL syntax checking:** the generated string can be syntactically invalid or wrong for the dialect.
4. **No column type checking:** `%d` and `%f` only format Java values; they do not replace database type checking.
5. **Can depend on locale:** numeric formats like `%f` can use the default locale's rules.
6. **`%` has special meaning to Formatter:** literal percent signs must be written `%%` if `formatted()` is called.
7. **Does not replace query builders or ORMs:** for complex queries, dedicated libraries manage structure, dialect, and parameters better.

### 8.1. Why not escape manually and then use `formatted()`?

A common attempt is replacing single quotes in data before inserting into a string. This is not a general solution:

- Literal escaping rules depend on the database and data type.
- Encoding, Unicode, control characters, and special literal syntax can create hard-to-handle edge cases.
- Data is still merged into SQL, leaving security responsibility in application code.
- Dialect or driver changes can invalidate old assumptions.

Let the JDBC driver handle binding values. `PreparedStatement` is the API designed for this purpose.

## 9. Complete example: safe filtering and sorting

The following example combines both approaches:

- A text block creates the multiline SQL structure.
- `formatted()` inserts column name and sort direction mapped from an enum.
- `PreparedStatement` binds the search values.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

enum UserSort {
    NAME,
    CREATED_AT
}

public class UserRepositoryExample {

    public void search(
            Connection connection,
            String status,
            String searchTerm,
            UserSort sort,
            boolean descending
    ) throws SQLException {

        String orderColumn = switch (sort) {
            case NAME -> "name";
            case CREATED_AT -> "created_at";
        };

        String orderDirection = descending ? "DESC" : "ASC";

        String sql = """
                SELECT id, name, email, created_at
                FROM users
                WHERE status = ?
                  AND name LIKE ?
                ORDER BY %s %s
                """.formatted(orderColumn, orderDirection);

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, status);
            statement.setString(2, "%" + searchTerm + "%");

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    System.out.printf(
                            "%d | %s | %s%n",
                            rs.getLong("id"),
                            rs.getString("name"),
                            rs.getString("email")
                    );
                }
            }
        }
    }
}
~~~

Everything passed into `formatted()` consists of fixed options controlled by the program. Everything coming from callers (`status`, `searchTerm`) is bound as parameters.

In a real application, ensure `sort` is non-null or define an appropriate default. If receiving sort options as strings from a request, parse them into the enum and reject values outside the allowlist.

## 10. Quick checklist when working with SQL templates

When writing a text block with `.formatted()`, ask yourself:

1. Is each `%...` a specifier or a literal percent sign?
2. Does each argument match the type required by its specifier?
3. Is the inserted value **runtime data** or **a program-controlled syntax fragment**?
4. If it is runtime data, why isn't `PreparedStatement` being used?
5. If it is a table/column name or keyword, has that value passed through an allowlist?
6. Has the SQL been tested on the actual target database engine and dialect?
7. If using floating-point numbers or dates, am I confusing Java display formatting with SQL data representation?

An easy rule of thumb:

~~~text
Text block        -> write multiline SQL
formatted()       -> substitute format specifiers in a String
PreparedStatement -> bind runtime values
Allowlist         -> control dynamic identifiers / SQL keywords
Database driver   -> handle parameters according to data types
~~~

## 11. Practice exercises

### Exercise 1: Read the result of `formatted()`

Given:

~~~java
String template = """
        SELECT id
        FROM users
        WHERE status = '%s'
          AND age >= %d
        """;

String result = template.formatted("ACTIVE", 18);
~~~

**Question:** What content does `result` contain? Should this approach be used for values received from an HTTP request?

**Hint:** The resulting string contains literal `'ACTIVE'` and `18` in the SQL. Do not use this for request data because `formatted()` does not bind or escape SQL. Change those two spots to `?` and bind via `PreparedStatement`.

### Exercise 2: Fix a query safely

Original code:

~~~java
String sql = """
        SELECT id, name
        FROM users
        WHERE email = '%s'
        """.formatted(email);
~~~

**Task:** Rewrite using JDBC.

**Reference answer:**

~~~java
String sql = """
        SELECT id, name
        FROM users
        WHERE email = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("name"));
        }
    }
}
~~~

### Exercise 3: Sorting by user selection

Requirement: support sorting by name or creation time, ascending or descending.

**Question:** Why can't you write `ORDER BY ? ?` and bind the column name and sort direction?

**Hint:** JDBC question marks represent data values, not identifiers or keywords. Map an enum to fixed strings `name`/`created_at` and `ASC`/`DESC`, then use `formatted()` for the controlled structural part.

### Exercise 4: Generate a placeholder list

Given a list of four IDs, generate `?, ?, ?, ?` in Java, then bind the four values into a `PreparedStatement`.

**Reference answer:**

~~~java
List<Long> ids = List.of(10L, 20L, 30L, 40L);

String placeholders = String.join(
        ", ",
        Collections.nCopies(ids.size(), "?")
);

String sql = """
        SELECT id
        FROM users
        WHERE id IN (%s)
        """.formatted(placeholders);

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    for (int i = 0; i < ids.size(); i++) {
        statement.setLong(i + 1, ids.get(i));
    }

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("id"));
        }
    }
}
~~~

Remember to handle an empty list before constructing the query.

### Exercise 5: Percent signs in format strings

Given:

~~~java
String template = "WHERE discount >= %d%%";
String sql = template.formatted(20);
~~~

**Question:** Why is `%%` needed? What is the result?

**Answer:** `Formatter` uses `%` to begin a format specifier. To get a literal percent sign in the result, write `%%`. The result is `WHERE discount >= 20%`.

### Exercise 6: Pick the right tool

Match the need with the solution:

| Need | Solution |
|---|---|
| Write a multiline SQL statement | Text block |
| Display a report containing numbers and strings | `formatted()` |
| Look up a user by input email | `PreparedStatement` |
| Choose a sort column from an allowed set of options | Enum/allowlist then construct SQL structure |
| Bind a variable-sized list of values | Generate placeholders, bind each value |

## 12. References

- [Oracle Java SE 17 — Text Blocks](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html): text block syntax, incidental indentation, and escape sequences.
- [Oracle Java SE 17 — String API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#formatted(java.lang.Object...)): `String.formatted(Object... args)` method.
- [Oracle Java SE 17 — Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html): format specifiers, conversions, flags, width, precision, and locale.
- [Oracle Java SE 17 — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): JDBC parameter-binding API.
- [Oracle Java SE 17 — JDBC Basics: Prepared Statements](https://docs.oracle.com/javase/tutorial/jdbc/basics/prepared.html): using prepared statements in JDBC.
- [OWASP — SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html): parameterized query principles and allowlisting for dynamic SQL elements.
