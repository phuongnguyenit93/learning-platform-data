# NO_BACKSLASH_ESCAPES, Escaping, and Safe Literal Handling

An application stores the path `C:\temp\new`, the note `O'Reilly`, and a product name containing `%`. When concatenating these values directly into an SQL statement, a single quote or backslash can cause a syntax error, alter data, or open an SQL injection vulnerability. The issue becomes even more complex when different MySQL sessions use different SQL modes.

`NO_BACKSLASH_ESCAPES` is an SQL mode that changes how MySQL interprets the backslash (`\`) inside string literals. Understanding this mode helps write consistent SQL statements, though the most important safety rule remains passing values via prepared statements rather than constructing literals from input data. When dynamic SQL must be generated, clearly distinguish values, table/column names, and query control syntax.

## 1. SQL Mode Affects How MySQL Parses Statements

SQL mode is a set of options that alter how MySQL parses, validates, and executes SQL. Some modes affect data strictness; others change syntax or literal interpretation.

Check the current connection's SQL mode and the server-wide default:

```sql
SELECT
    @@SESSION.sql_mode AS session_sql_mode,
    @@GLOBAL.sql_mode AS global_sql_mode;
```

`@@SESSION.sql_mode` applies to the current connection. `@@GLOBAL.sql_mode` is the default value used when opening new connections; changing GLOBAL does not automatically alter already open sessions.

Check specifically for a mode:

```sql
SELECT
    FIND_IN_SET('NO_BACKSLASH_ESCAPES', @@SESSION.sql_mode) > 0
        AS no_backslash_escapes_enabled;
```

If the result is `1`, the mode is enabled in the session. If it is `0`, the mode is not in the current list.

## 2. Default String Literal Rules

String literals in MySQL are typically enclosed in single quotes (`'...'`). When `NO_BACKSLASH_ESCAPES` is not enabled, a backslash can begin an escape sequence.

Some common escape sequences:

| Written in SQL Literal | Character Produced in Default Mode |
|---|---|
| `\\` | One backslash (`\`) |
| `\'` | One single quote (`'`) |
| `\"` | One double quote (`"`) |
| `\n` | Line feed (LF) character |
| `\r` | Carriage return character |
| `\t` | Tab character |
| `\0` | NUL character |
| `\b` | Backspace character |
| `\Z` | Ctrl-Z character |

Example:

```sql
SELECT
    'A\nB' AS text_value,
    HEX('A\nB') AS bytes_value;
```

In default mode, `\n` is interpreted as an LF newline byte `0A`; the corresponding hex result is `410A42`.

For sequences that are not recognized escape sequences, MySQL follows its own rules: the `\` may be stripped when parsing the literal. Therefore, do not assume every `\x` pair is stored as two characters.

## 3. What Does NO_BACKSLASH_ESCAPES Change?

When `NO_BACKSLASH_ESCAPES` is enabled, `\` becomes an ordinary character inside string literals. It is no longer used to escape quotes or form escape sequences like `\n`, `\t`, and `\\`.

With the same example:

```sql
SELECT
    'A\nB' AS text_value,
    HEX('A\nB') AS bytes_value;
```

In this mode, the string contains four characters `A`, `\`, `n`, `B`; the hex result is `415C6E42`. The backslash is preserved literally.

| Literal Content | Default Mode | `NO_BACKSLASH_ESCAPES` |
|---|---|---|
| `'A\nB'` | `A`, newline, `B` | `A`, `\`, `n`, `B` |
| `'C:\\temp'` | One `\` before `temp` | Two `\` characters before `temp` |
| `'It\'s'` | Can represent an inner single quote | Does not escape the quote; statement terminates at that quote |
| `'It''s'` | One inner single quote | One inner single quote |

Key point: `NO_BACKSLASH_ESCAPES` does not alter the doubled single-quote rule. Writing `'It''s'` is the stable way to represent a string literal containing `It's` across both modes.

## 4. Setting and Restoring SQL Mode in a Session

For testing, change only the current session. The example below saves the old mode, adds `NO_BACKSLASH_ESCAPES` if absent, tests, and restores:

```sql
SET @saved_sql_mode = @@SESSION.sql_mode;

SET SESSION sql_mode = IF(
    FIND_IN_SET('NO_BACKSLASH_ESCAPES', @@SESSION.sql_mode) > 0,
    @@SESSION.sql_mode,
    CONCAT_WS(',', NULLIF(@@SESSION.sql_mode, ''), 'NO_BACKSLASH_ESCAPES')
);

SELECT @@SESSION.sql_mode;
SELECT HEX('A\nB') AS bytes_with_no_backslash_escapes;

SET SESSION sql_mode = @saved_sql_mode;
```

In production applications, do not arbitrarily change SQL mode between statements. If a connection is borrowed from a pool, session changes can persist when the connection is returned to the pool. Configure the mode at connection initialization or ensure state is restored before returning the connection.

### 4.1. SESSION and GLOBAL Differ

- `SET SESSION sql_mode = ...` affects only the current connection.
- `SET GLOBAL sql_mode = ...` changes the default for connections opened afterward; requires appropriate administrative privileges.
- Configuration at server startup establishes a stable default policy across restarts.

Do not replace the entire `sql_mode` just to enable one mode unless you intend to change other modes. Assigning a new list can accidentally disable `STRICT_TRANS_TABLES`, `ONLY_FULL_GROUP_BY`, or existing rules.

### 4.2. Stored Programs and Creation-Time SQL Mode

MySQL stores the SQL mode in effect when creating a stored procedure, function, trigger, or event. When these objects execute, they use the mode saved at creation time according to MySQL rules. Consequently, changing the SQL mode of the calling session does not necessarily change how literals inside the procedure were already parsed and stored.

When changing SQL mode policies, audit related stored programs. If a new mode must take effect, plan to recreate the objects in an appropriate environment and verify behavior after deployment.

## 5. Escaping Single Quotes Safely

### 5.1. Doubling Single Quotes

In SQL literals, a single quote inside a string is represented by two consecutive single quotes:

```sql
SELECT 'O''Reilly' AS publisher_name;
```

This syntax works whether `NO_BACKSLASH_ESCAPES` is enabled or disabled. When writing fixed literals in SQL scripts, this is the recommended method.

### 5.2. Do Not Use Backslashes to Quote Single Quotes When Mode May Vary

The following example depends on SQL mode:

```sql
SELECT 'O\'Reilly';
```

In default mode, `\'` escapes the single quote. When `NO_BACKSLASH_ESCAPES` is enabled, backslash does not escape the quote, so the statement can be misparsed or fail with a syntax error.

If a script must run across environments with different SQL modes, use the doubled single-quote form:

```sql
SELECT 'O''Reilly';
```

## 6. Escaping Backslashes and File Paths

Suppose an application needs to store the Windows path `C:\temp\new`.

In default mode, to store one `\` before each component, the literal must double the backslashes:

```sql
INSERT INTO file_jobs (file_path)
VALUES ('C:\\temp\\new');
```

When `NO_BACKSLASH_ESCAPES` is enabled, backslash is a normal character, so the corresponding literal can be written:

```sql
INSERT INTO file_jobs (file_path)
VALUES ('C:\temp\new');
```

These two SQL statements cannot be interchanged freely between the two SQL modes. If code builds SQL by string concatenation, changing the mode can cause the stored number of backslashes to differ from expectations.

For user-supplied data, never manually build path literals. Use parameter binding to pass the raw value intact, regardless of whether it contains backslashes, quotes, newlines, or Unicode.

## 7. LIKE Patterns and Wildcard Characters

In `LIKE`, two characters have special meaning:

- `%` matches zero or more characters.
- `_` matches exactly one character.

If you need to search for `%` or `_` as literal characters, use the `ESCAPE` clause with an explicitly designated escape character. This avoids depending on whether backslash is currently acting as an escape character.

Example of searching for a string containing `%`:

```sql
SELECT id, product_name
FROM products
WHERE product_name LIKE '%!%%' ESCAPE '!';
```

In the pattern above, `!%` means a literal `%` character; the two outer `%` signs remain wildcards.

Example of searching for an underscore:

```sql
SELECT id, product_name
FROM products
WHERE product_name LIKE '%!_%' ESCAPE '!';
```

When building a pattern from user input, escape the escape character `!` first, and then escape `%` and `_` according to application rules. For instance, if `!` is the escape character, replace `!` in the input with `!!`, `%` with `!%`, and `_` with `!_`; then bind the entire pattern using a prepared statement.

## 8. Literals, Identifiers, and Syntax Are Three Different Things

An SQL statement can contain:

- **Values/literals:** customer names, emails, prices, or note contents.
- **Identifiers:** database, table, column, or alias names.
- **SQL syntax:** keywords, operators, sort directions, function names, and query structure.

Prepared statement parameters represent values only. You cannot use `?` to substitute table names, column names, or SQL keywords.

### 8.1. String Literals Use Single Quotes

```sql
SELECT *
FROM customers
WHERE email = 'alice@example.com';
```

Single quotes are for strings. When writing fixed literals, double inner single quotes rather than relying on backslashes.

### 8.2. Identifiers Use Backticks

```sql
SELECT `order`, `customer name`
FROM `sales data`;
```

Backticks are used to quote identifiers. If an identifier contains a backtick inside its name, the backtick is doubled inside the quoted identifier. Do not use string literals in place of identifiers.

### 8.3. ANSI_QUOTES Is a Different Mode

When `ANSI_QUOTES` is enabled, double quotes (`"`) are interpreted as identifier quotes rather than string literals. Therefore:

```sql
SELECT "status" FROM orders;
```

can be interpreted as referencing the identifier `status` in `ANSI_QUOTES` mode; in standard mode, it is a string literal containing `status`.

To avoid mode dependence, use single quotes for strings and backticks for identifiers. Do not use double quotes as a way to write SQL strings.

## 9. Prepared Statements Are the Safe Way to Pass Values

When an application handles dynamic data, send the SQL statement with placeholders and pass values separately through the driver. The driver handles protocol encoding and data types; the application does not need to manually escape quotes or backslashes for SQL concatenation.

### 9.1. Java JDBC Example

```java
String sql = "INSERT INTO customers (full_name, note) VALUES (?, ?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, fullName);
    statement.setString(2, note);
    statement.executeUpdate();
}
```

If `fullName` is `O'Reilly` or `note` contains `C:\temp\new`, the driver transmits the values as data. Their content cannot close the quote to turn the rest into SQL syntax.

### 9.2. Parameterized Query Example

```java
String sql = "SELECT id, full_name FROM customers WHERE email = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, emailInput);

    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            long id = result.getLong("id");
            String name = result.getString("full_name");
        }
    }
}
```

Do not concatenate `emailInput` into the SQL string. Parameter binding also avoids quoting bugs when values contain Unicode, quotes, backslashes, or newlines.

### 9.3. Placeholders Cannot Substitute Identifiers

The following does not work as expected:

```java
String sql = "SELECT * FROM ? WHERE id = ?";
```

The first placeholder cannot represent a table name. If you need to choose a table or column based on user selection, use an allowlist mapping valid choices to fixed identifiers:

```java
Map<String, String> allowedTables = Map.of(
    "active", "active_customers",
    "archived", "archived_customers"
);

String table = allowedTables.get(requestedView);
if (table == null) {
    throw new IllegalArgumentException("Unsupported view");
}

String sql = "SELECT id, full_name FROM `" + table + "` WHERE id = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);
    // Execute the query...
}
```

The table name in the example comes strictly from a program-controlled allowlist; raw input is never concatenated directly as an identifier. For `ORDER BY`, `ASC`/`DESC` direction, or dynamic column names, use a similar allowlist.

## 10. Driver Escape APIs and Limits of Manual Escaping

Some drivers provide quote/escape functions to build literals. If you must generate SQL text, only use APIs designed for the exact connector and active connection; the connection charset and SQL mode must align with how the API escapes.

Do not use homegrown string replacement functions such as:

```java
input.replace("'", "\\'");
```

This code depends on backslash escaping and does not properly handle character sets, NUL bytes, escape sequences, or SQL mode differences. Nor does it protect identifiers or dynamic syntax.

Prepared statement parameter binding should be the default choice. Escape APIs are only for special cases where parameter binding is impossible, after reading the driver documentation and verifying connection configuration. Never implement a generic homegrown SQL escape function across database engines.

## 11. SQL Mode in Connection Pools and Stored Programs

SQL mode is session state. In applications using a connection pool, a single connection can be reused across multiple requests. If request A changes `sql_mode` and fails to restore it, request B may receive a connection with different literal parsing behavior.

Recommended practices:

- Configure SQL mode uniformly during connection initialization.
- Avoid changing SQL mode mid-way through business logic flows.
- If a change is unavoidable, save the old value and restore it in `finally` or an equivalent cleanup mechanism.
- When returning a connection to the pool, reset session state according to pool/driver capabilities.
- Check the actual SQL mode on a borrowed connection, not just `GLOBAL`.
- Inspect the mode stored with stored procedures, functions, triggers, and events when deploying changes.

Do not rely on `@@GLOBAL.sql_mode` to conclude that the current session uses the same mode. The two values can differ.

## 12. Testing Literal Behavior Under Both Modes

You can use a test session and `HEX()` to observe the actual bytes:

```sql
-- Save the initial SQL mode.
SET @old_mode = @@SESSION.sql_mode;

-- Enable NO_BACKSLASH_ESCAPES while keeping existing modes.
SET SESSION sql_mode = IF(
    FIND_IN_SET('NO_BACKSLASH_ESCAPES', @@SESSION.sql_mode) > 0,
    @@SESSION.sql_mode,
    CONCAT_WS(',', NULLIF(@@SESSION.sql_mode, ''), 'NO_BACKSLASH_ESCAPES')
);

SELECT HEX('A\nB') AS no_backslash_bytes;
SELECT 'O''Reilly' AS quoted_value;

-- Restore the initial mode.
SET SESSION sql_mode = @old_mode;

SELECT HEX('A\nB') AS default_mode_bytes;
```

When the mode is enabled, the bytes of `\n` are preserved as `5C6E`. After restoring default mode, the same literal is parsed as a newline character (`0A`). Perform this in a test session; if the client or tool has its own escaping mechanism, verify the actual SQL text sent to the server.

A test suite should cover:

- Data containing single quotes: `O'Reilly`.
- Data containing backslashes: `C:\temp\new`.
- Data containing `%` and `_` when searching with LIKE.
- Strings with Unicode and newline characters.
- Empty strings and SQL `NULL`.
- Prepared statements with all of the above data under both SQL modes.

## 13. Common Errors and Risks

| Symptom | Cause | Resolution |
|---|---|---|
| SQL fails with syntax error after enabling `NO_BACKSLASH_ESCAPES` | Legacy literal uses `\'` to quote single quotes | Use `''` or parameter binding |
| Path stores wrong number of backslashes | Code generating literals assumed a fixed SQL mode | Bind parameters; for static scripts, write literals matching the defined mode |
| `\n` stored as unexpected newline | Session uses default backslash escaping | Check `@@SESSION.sql_mode`; use parameter binding or choose literal intentionally |
| `%`/`_` search matches wrongly | Confusing wildcards with literal characters | Use `LIKE ... ESCAPE '!'` and escape input per application rules |
| Dynamic query vulnerable to SQL injection | Concatenating input into SQL text or identifiers | Bind values; allowlist identifiers and dynamic syntax |
| Another request gets unexpected SQL mode | Connection pool retained session state from previous request | Initialize/reset session state when borrowing/returning connections |
| Double-quoted string changes meaning | `ANSI_QUOTES` is enabled | Use single quotes for strings and backticks for identifiers |

## 14. Procedure for Migrating to NO_BACKSLASH_ESCAPES

When enabling this mode for an existing application, do not change production directly before auditing literals.

1. **Document current state:** collect `@@GLOBAL.sql_mode` and `@@SESSION.sql_mode` from every type of application connection.
2. **Locate SQL construction:** find string concatenation, manual escape functions, migration scripts, stored programs, and custom query builders.
3. **Audit backslash-dependent literals:** focus on `\'`, `\\`, `\n`, `\r`, `\t`, file paths, regexes, and LIKE patterns.
4. **Move dynamic values to parameter binding:** eliminate manual input quoting; use allowlists for identifiers and dynamic syntax.
5. **Standardize static literals:** use doubled single quotes; review backslashes against the target mode.
6. **Test both modes:** run test suites under the old and new modes on identical data; compare bytes with `HEX()` and verify business outcomes.
7. **Audit stored programs:** verify creation-time SQL mode and recreate objects if needed.
8. **Roll out by connection group:** update configuration, monitor syntax errors, corrupted writes, and connection pools; keep a rollback plan to the previous mode.

Enabling `NO_BACKSLASH_ESCAPES` does not by itself make an application safe from SQL injection. If an application still concatenates user data into SQL, the vulnerability remains; the mode only changes part of literal parsing rules.

## 15. Checklist for Writing Safe SQL Literals

- Does the session use `NO_BACKSLASH_ESCAPES`?
- Do statements rely on backslashes to escape quotes or produce newlines?
- Do string literals use single quotes and double inner single quotes?
- Are string literals ever confused with identifiers or SQL syntax?
- Are user-supplied values bound via prepared statements?
- Are dynamic identifiers selected from an allowlist and properly quoted?
- Do LIKE patterns use an explicit `ESCAPE` for literal `%` and `_`?
- Does the connection pool reset SQL mode and session state?
- Do stored programs have a creation-time SQL mode that differs from current configuration?
- Have actual bytes been tested with `HEX()` under the relevant modes?

## Conclusion

`NO_BACKSLASH_ESCAPES` makes backslash an ordinary character inside string literals; escape sequences like `\n` and `\'` no longer operate in the default way. Doubling single quotes (`''`) is the stable way to quote strings across both modes. For dynamic data, use prepared statements to pass values separately; for dynamic identifiers and syntax, use allowlists. Verify SQL mode on the right session, manage connection pool state, and test with `HEX()` before changing configurations to prevent data corruption and SQL parsing errors.
