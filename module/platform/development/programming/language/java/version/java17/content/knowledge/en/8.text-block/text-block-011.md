# Keeping Input Data Safe with Parameterization Instead of String Concatenation — Java 17 Text Blocks

When a Java application interacts with a database, it frequently inserts user-supplied data into SQL statements: finding an account by email, filtering orders by status, updating a name, or deleting a record. If input data is concatenated directly into a SQL string, special characters can alter the statement's structure. This is a common cause of **SQL injection**.

The standard way to handle this in JDBC is using **`PreparedStatement` and parameter binding** to separate SQL structure from data values. Java 17 offers **text blocks** (multiline strings, `"""` syntax) that make SQL layouts easier to read. However, text blocks only improve how strings are written. They **do not automatically parameterize, escape data, or prevent SQL injection**. For safety, combine text blocks with `PreparedStatement`.

## 1. Text blocks solve SQL presentation

Before Java 15, a multiline SQL query usually had to use string concatenation:

```java
String sql =
        "SELECT id, email, display_name " +
        "FROM users " +
        "WHERE status = ? " +
        "ORDER BY created_at DESC";
```

Java 17 supports text blocks:

```java
String sql = """
        SELECT id, email, display_name
        FROM users
        WHERE status = ?
        ORDER BY created_at DESC
        """;
```

Both approaches create a `String` object. Text blocks make SQL statements look close to how they are written in database administration tools, making them convenient to read and maintain. A text block opens with `"""`, holds multiline content, and ends with a closing `"""`. Java applies rules for leading whitespace and trailing lines; common indentation is stripped.

A text block is still just a string. Java does not parse this content into a SQL statement, nor does it automatically distinguish which parts are input data.

## 2. Why is concatenating strings with user data dangerous?

Suppose an application looks up an account by email. The following approach is unsafe:

```java
String email = inputFromUser;

String sql = "SELECT id, email FROM users WHERE email = '"
        + email + "'";

try (Statement statement = connection.createStatement();
     ResultSet result = statement.executeQuery(sql)) {
    // Read results...
}
```

The application has mixed **SQL structure** with **data values** in the same string. If a normal email is `lan@example.com`, the query appears to work.

However, a user can enter a value containing SQL syntax, for example:

```text
' OR '1'='1
```

After concatenation, the SQL statement can become:

```sql
SELECT id, email FROM users
WHERE email = '' OR '1'='1'
```

The condition `'1'='1'` is always true, so the query may return many accounts instead of only the requested account. Depending on the statement and database account privileges, SQL injection can lead to unintended reading, modification, or deletion of data.

Do not try to fix this by manually replacing single quotes or writing custom escaping functions for every input type. Escaping rules depend on context and the database engine; incomplete manual handling easily leaves vulnerabilities.

## 3. Combining text blocks with PreparedStatement

Instead of concatenating email into the SQL string, write a `?` as a parameter placeholder:

```java
String sql = """
        SELECT id, email
        FROM users
        WHERE email = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);

    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            System.out.println(result.getLong("id"));
            System.out.println(result.getString("email"));
        }
    }
}
```

There are two separate parts:

1. **SQL template:** a statement with fixed structure and `?` parameter positions.
2. **Parameter value:** passed via `setString(1, email)`.

The database recognizes the bound value as parameter data, not part of SQL syntax to be re-parsed. If the user enters `' OR '1'='1`, that entire string is compared as an email value; it does not turn into an `OR` operator or a new condition.

### Parameter indices start at 1

In JDBC, `?` parameter indices start at **1**, not 0.

```java
String sql = """
        SELECT id, email
        FROM users
        WHERE email = ?
          AND status = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);
    statement.setString(2, "ACTIVE");

    try (ResultSet result = statement.executeQuery()) {
        // Process results...
    }
}
```

The first parameter is `email`, and the second parameter is `status`. The order of `set...` calls must match the order of `?` markers in the SQL statement.

### Do not put quotes around question marks

**Incorrect:**

```java
String sql = """
        SELECT id, email
        FROM users
        WHERE email = '?'
        """;
```

`'?'` is a literal character string in SQL, not a parameter placeholder. JDBC cannot bind `email` into that position as intended.

**Correct:**

```java
String sql = """
        SELECT id, email
        FROM users
        WHERE email = ?
        """;
```

Do not add quotes around placeholders yourself. The driver handles how values are transmitted based on the bound data type.

## 4. Complete example: finding a user by email

The following example uses standard JDBC, text blocks, and `PreparedStatement`. The method accepts a `Connection` supplied by the caller; it does not close that connection itself.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;

public class UserRepository {

    public record User(long id, String email, String displayName) {
    }

    public static Optional<User> findByEmail(
            Connection connection,
            String email
    ) throws SQLException {

        String sql = """
                SELECT id, email, display_name
                FROM users
                WHERE email = ?
                """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setString(1, email);

            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    return Optional.empty();
                }

                User user = new User(
                        result.getLong("id"),
                        result.getString("email"),
                        result.getString("display_name")
                );

                return Optional.of(user);
            }
        }
    }
}
```

Key points to note:

- The SQL statement is written multiline using a text block, making it easy to read.
- `email` data is not concatenated into the SQL statement.
- `setString(1, email)` binds `email` to the first placeholder.
- `PreparedStatement` and `ResultSet` are closed with try-with-resources.
- `Connection` belongs to the caller; closing it here could break a transaction or other operation using it.

The snippet assumes the `users` table has `id`, `email`, and `display_name` columns. Actual table names, column names, and data types must match the application's schema.

## 5. Text blocks do not make SQL safe on their own

A common misconception is thinking that switching from concatenated strings to a text block solves SQL injection.

**Incorrect — still splices untrusted input:**

```java
String sql = """
        SELECT id, email
        FROM users
        WHERE email = '%s'
        """.formatted(email);
```

`String.formatted` merely formats strings. If `email` contains SQL syntax, it is still inserted directly into the statement.

**Incorrect — text blocks do not turn concatenation into parameters:**

```java
String sql = """
        SELECT id, email
        FROM users
        WHERE email = '""" + email + """
        '
        """;
```

The snippet above still concatenates strings. Using `"""` delimiters does not change the nature of concatenation.

**Correct — keep placeholders in the text block and bind separately:**

```java
String sql = """
        SELECT id, email
        FROM users
        WHERE email = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);
    try (ResultSet result = statement.executeQuery()) {
        // ...
    }
}
```

| Component | Role | Prevents SQL injection on its own? |
| --- | --- | --- |
| Text block `"""` | Write readable multiline strings. | No. |
| `String.format` / `formatted` | Insert formatted values into a string. | No. |
| String concatenation `+` | Join string fragments. | No. |
| `PreparedStatement` with bound parameters | Separate data values from SQL statement structure. | Yes, for properly bound values. |

## 6. Binding the right data types

JDBC provides multiple methods to bind typed values:

| Common Java type | JDBC method |
| --- | --- |
| `String` | `setString(index, value)` |
| `int` | `setInt(index, value)` |
| `long` | `setLong(index, value)` |
| `boolean` | `setBoolean(index, value)` |
| `BigDecimal` | `setBigDecimal(index, value)` |
| `LocalDate` | Convert via `java.sql.Date.valueOf(value)` then use `setDate` |
| `LocalDateTime` | Convert via `java.sql.Timestamp.valueOf(value)` then use `setTimestamp` |
| `null` value | `setNull(index, Types.TYPE)` with appropriate SQL type |

Example searching orders by status, customer ID, and creation date:

```java
import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;

public class OrderSearch {

    static void search(
            Connection connection,
            long customerId,
            String status,
            LocalDate createdOn
    ) throws SQLException {

        String sql = """
                SELECT id, customer_id, status, created_at
                FROM orders
                WHERE customer_id = ?
                  AND status = ?
                  AND created_at >= ?
                ORDER BY created_at DESC
                """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setLong(1, customerId);
            statement.setString(2, status);
            statement.setDate(3, Date.valueOf(createdOn));

            try (ResultSet result = statement.executeQuery()) {
                while (result.next()) {
                    System.out.println(
                            result.getLong("id") + " "
                            + result.getString("status")
                    );
                }
            }
        }
    }
}
```

Typed binding lets the driver pass values matching the SQL column type. Avoid converting everything into strings and adding quotes into the statement yourself.

The example above assumes `created_at` has a date type compatible with `java.sql.Date`. If the column is a timestamp, choose the corresponding Java/JDBC type, such as `LocalDateTime` paired with `Timestamp.valueOf` or a time API supported by the database engine.

If a parameter can be `null`, clearly define the business semantics. For instance, to find rows where `deleted_at` is SQL NULL, use `IS NULL`; do not write `deleted_at = ?`, pass `null`, and expect it to behave like `IS NULL` in SQL.

## 7. Parameterizing INSERT, UPDATE, and DELETE statements

The parameter-binding principle does not apply only to `SELECT`.

### INSERT

```java
String sql = """
        INSERT INTO users (email, display_name, status)
        VALUES (?, ?, ?)
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);
    statement.setString(2, displayName);
    statement.setString(3, "ACTIVE");

    int insertedRows = statement.executeUpdate();
    System.out.println("Inserted rows: " + insertedRows);
}
```

`executeUpdate()` returns the affected row count for data modification statements such as `INSERT`, `UPDATE`, and `DELETE`.

### UPDATE

```java
String sql = """
        UPDATE users
        SET display_name = ?, status = ?
        WHERE id = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, displayName);
    statement.setString(2, status);
    statement.setLong(3, userId);

    int updatedRows = statement.executeUpdate();
    System.out.println("Updated rows: " + updatedRows);
}
```

### DELETE

```java
String sql = """
        DELETE FROM users
        WHERE id = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, userId);

    int deletedRows = statement.executeUpdate();
    System.out.println("Deleted rows: " + deletedRows);
}
```

With `UPDATE` and `DELETE`, pay special attention to the `WHERE` clause. Parameterization protects input values from becoming SQL syntax, yet does not guarantee the statement targets the right scope. A `DELETE` missing a `WHERE` clause can still delete an entire table.

## 8. Table names, column names, and SQL keywords cannot be bound with placeholders

`PreparedStatement` placeholders are for **data values**, not table names, column names, operators, keywords, or sort directions.

**Incorrect — attempting to bind a column name:**

```java
String sql = """
        SELECT id, email
        FROM users
        ORDER BY ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "email");
}
```

In many database engines, the statement above does not sort by the `email` column as intended. The placeholder is interpreted as an expression value, not an identifier substituting SQL structure.

**Incorrect — directly concatenating a user-submitted column name:**

```java
String sortColumn = inputFromUser;

String sql = """
        SELECT id, email
        FROM users
        ORDER BY
        """ + sortColumn;
```

If `sortColumn` is unvalidated, a user can inject SQL syntax into a structural position.

### The right way: whitelist allowed identifiers

If an application allows sorting by a fixed set of fields, map input to column names defined in code:

```java
import java.util.Map;

public class UserSort {

    private static final Map<String, String> SORT_COLUMNS = Map.of(
            "email", "email",
            "created", "created_at",
            "name", "display_name"
    );

    static String buildQuery(String requestedSort, boolean ascending) {
        String column = SORT_COLUMNS.get(requestedSort);

        if (column == null) {
            throw new IllegalArgumentException("Invalid sort field");
        }

        String direction = ascending ? "ASC" : "DESC";

        return """
                SELECT id, email, display_name
                FROM users
                ORDER BY %s %s
                """.formatted(column, direction);
    }
}
```

Here, `requestedSort` is only mapped to constant strings declared in code; `direction` can only be `ASC` or `DESC`. In this example, `formatted` is used strictly for whitelisted, tightly controlled identifiers and keywords. **Data values** such as email, user name, or order ID must still be bound with `PreparedStatement`.

If dynamic sorting is unnecessary, it is best to write the SQL query with fixed columns and sort direction.

## 9. Searching with LIKE: bind the value, but understand wildcards

You can bind a search pattern for `LIKE`:

```java
String sql = """
        SELECT id, display_name
        FROM users
        WHERE display_name LIKE ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "%" + keyword + "%");

    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            System.out.println(result.getString("display_name"));
        }
    }
}
```

Concatenating `"%" + keyword + "%"` here builds **the parameter's value**, not SQL structure. The placeholder is still bound safely.

However, `%` and `_` are `LIKE` wildcard characters in many database systems: `%` matches zero or more characters; `_` matches a single character. If business logic requires literal matching, escape those wildcards using the `ESCAPE` syntax supported by your database engine. This is a **search semantics** concern, separate from SQL injection.

## 10. IN queries with a variable number of parameters

You cannot pass a list of IDs by binding a comma-separated string and expecting SQL to split it into multiple values.

**Incorrect:**

```java
String sql = "SELECT id FROM users WHERE id IN (?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "10,20,30");
}
```

`?` is **one value**. The string `"10,20,30"` does not turn into three SQL parameters.

### Generating placeholder count based on list size

The number of `?` markers can be built from **the element count**, while each individual value is still bound separately:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Collections;
import java.util.List;

public class UserBatchSearch {

    static void findByIds(
            Connection connection,
            List<Long> ids
    ) throws SQLException {

        if (ids.isEmpty()) {
            return;
        }

        String placeholders = String.join(
                ", ",
                Collections.nCopies(ids.size(), "?")
        );

        String sql = """
                SELECT id, email
                FROM users
                WHERE id IN (%s)
                """.formatted(placeholders);

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            for (int i = 0; i < ids.size(); i++) {
                statement.setLong(i + 1, ids.get(i));
            }

            try (ResultSet result = statement.executeQuery()) {
                while (result.next()) {
                    System.out.println(result.getLong("id"));
                }
            }
        }
    }
}
```

With a list of three IDs, the SQL template becomes:

```sql
SELECT id, email
FROM users
WHERE id IN (?, ?, ?)
```

The values `10`, `20`, and `30` are bound to positions 1, 2, and 3 respectively. The dynamic SQL text depends solely on the **number of elements**, never on the data contents of each ID.

Notes:

- Handle empty lists before creating `IN ()`; that syntax is not accepted by all database engines.
- Bound the list size to avoid exceeding database or driver parameter limits.
- For very large lists, consider batching, temporary tables, or a mechanism suited to your database engine.
- Never concatenate ID values into the SQL string.

## 11. Avoid `Statement` for untrusted data

JDBC provides three common statement types:

| Type | How created | How used |
| --- | --- | --- |
| `Statement` | `connection.createStatement()` | Executes a complete SQL string; has no positional parameter-binding API. |
| `PreparedStatement` | `connection.prepareStatement(sql)` | Uses `?` placeholders and `set...` methods to bind values. |
| `CallableStatement` | `connection.prepareCall(sql)` | Calls stored procedures; supports parameters per JDBC rules. |

For SQL statements involving external input, prefer `PreparedStatement`. Text blocks work with both `Statement` and `PreparedStatement`, yet safety depends on how data is supplied.

**Incorrect:**

```java
String sql = """
        SELECT id
        FROM users
        WHERE email = '%s'
        """.formatted(email);

try (Statement statement = connection.createStatement()) {
    statement.executeQuery(sql);
}
```

**Correct:**

```java
String sql = """
        SELECT id
        FROM users
        WHERE email = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);
    statement.executeQuery();
}
```

For fixed SQL queries containing no untrusted input, `Statement` remains a valid JDBC API. The key rule is never putting untrusted data into SQL structure via string concatenation.

## 12. Parameterization does not replace transactions

`PreparedStatement` separates data from SQL syntax, yet does not create a transaction or guarantee that multiple statements succeed or fail together.

If a business operation requires multiple SQL steps such as transferring funds, creating an order with line items, or updating multiple tables, manage transactions via `Connection`:

- Start a transaction by disabling auto-commit when appropriate.
- Execute each statement with `PreparedStatement` and bound values.
- Call `commit()` when all work succeeds.
- Call `rollback()` if any step fails.
- Restore connection state according to ownership and application conventions.

Connection pools, transaction frameworks, or ORMs may manage transactions instead of direct JDBC code. Do not manually commit a connection belonging to a transaction managed by the caller.

## 13. Common misconceptions

| Misconception | Reality |
| --- | --- |
| Using a text block prevents SQL injection. | Text blocks are just a multiline `String` syntax; parameter binding is still required. |
| Using `PreparedStatement` means you can concatenate arbitrary data into SQL. | Only values placed at placeholders are bound. Dynamic identifiers and syntax must be whitelisted or safely designed. |
| `?` can be used for table names or column names. | `?` is a slot for values, not identifiers. |
| Passing `"1,2,3"` into one placeholder acts like three `IN` elements. | That is a single string value. Generate individual placeholders and bind each element. |
| Bound data needs no business validation. | Parameterization prevents altering SQL syntax; it does not replace validation, authorization, or scope checks. |
| `LIKE ?` disables wildcards. | `%` and `_` still act as `LIKE` wildcards; escape them if literal matching is needed. |
| Manual quote escaping replaces string concatenation risks. | Manual escaping is error-prone across contexts and does not replace parameterization. |
| `PreparedStatement` automatically starts and closes transactions. | Transactions remain managed by the connection and application. |

## 14. Additional security principles

Parameterization is essential, yet safe database querying in an application requires additional principles.

### Grant only necessary database privileges

The application account should have only the permissions required for its role. For instance, a read-only reporting component should not use an account allowed to drop tables or alter schemas. If a SQL flaw occurs, least privilege limits potential damage.

### Enforce record-level authorization

A parameterized query can still let a user view another account's data if authorization predicates are missing:

```java
String sql = """
        SELECT id, email
        FROM users
        WHERE id = ?
          AND tenant_id = ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, userId);
    statement.setLong(2, currentTenantId);
    // ...
}
```

`userId` and `currentTenantId` must come from an authenticated and authorized context. Never trust a client-supplied tenant ID without verifying caller permissions.

### Do not log sensitive data carelessly

Avoid logging full emails, tokens, passwords, card numbers, or personal data unnecessarily. Logs should provide diagnostic value without exposing sensitive information.

### Validation is still required

For example, binding `quantity = -100` is safe structurally in SQL, yet may violate business rules. Validate bounds, formats, permissions, and state before executing operations.

### Do not return raw database errors to users

Detailed SQL error messages can leak table names, column names, schema layout, or internal details. Log errors server-side according to security policy and return safe messages to clients.

## 15. Practice exercises

The exercises below use Java 17 and JDBC. You will need a test database with corresponding tables and an appropriate JDBC driver to run queries. Illustrative SQL statements use standard syntax; column types, table names, and connection settings may need adjustment for your database engine.

### Exercise 1 — convert a concatenated query to parameterized SQL

Given unsafe code:

```java
String sql = """
        SELECT id, email
        FROM users
        WHERE email = '%s'
        """.formatted(email);
```

Tasks:

1. Replace `%s` with a JDBC placeholder.
2. Create a `PreparedStatement` from the SQL query.
3. Bind `email` with `setString`.
4. Execute the query and iterate over the `ResultSet`.

### Exercise 2 — multiple parameters of different types

Write the query:

```sql
SELECT id, total
FROM orders
WHERE customer_id = ?
  AND status = ?
  AND total >= ?
```

Bind `long customerId`, `String status`, and `BigDecimal minimumTotal` in order. Use the right JDBC method for each type.

### Exercise 3 — sorting by a chosen column

Allow clients to choose one of three values: `email`, `name`, or `created`. Write a whitelist mapping them to SQL columns defined in code. If the value is not in the list, reject the request.

Never concatenate client-supplied strings directly into `ORDER BY`.

### Exercise 4 — keyword search

Write the SQL query:

```sql
SELECT id, display_name
FROM users
WHERE display_name LIKE ?
```

Bind the pattern `"%" + keyword + "%"`. Explain why this concatenation builds a parameter value rather than SQL syntax. Then explore how to escape wildcards if literal string matching is required.

### Exercise 5 — querying a list of IDs

Given a variable-length `List<Long> ids`, handle the empty-list case, generate the placeholder count matching the number of IDs, and bind each ID into `PreparedStatement`.

Do not bind the entire list as a comma-separated string.

## 16. Quick reference

| Need | How to do it |
| --- | --- |
| Write readable multiline SQL | Use a Java text block `""" ... """`. |
| Pass user values into SQL | Use `PreparedStatement` with `?`. |
| Bind a string | `statement.setString(1, value)`. |
| Bind an integer | `setInt` or `setLong` as appropriate. |
| Insert/update/delete data | Use `executeUpdate()` and check affected row count. |
| Read data | Use `executeQuery()` and close `ResultSet`. |
| Dynamic column/table name or sort direction | Whitelist allowed identifiers and keywords. |
| List for `IN` | Generate placeholders matching element count and bind each value. |
| `LIKE` search handling | Bind search pattern; handle `%` and `_` wildcard semantics separately. |
| Multiple operations must succeed together | Manage transactions via `Connection`. |

**Core principle:** Text blocks make SQL statements in Java 17 readable; `PreparedStatement` is the mechanism that separates data from SQL syntax. Keep query structure fixed, bind all input values using appropriate JDBC methods, and build any dynamic SQL fragments strictly from whitelisted options.
