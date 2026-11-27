# ANSI_QUOTES, Identifiers, and Double Quotes

## Objectives

After this lesson, you will be able to:

- Explain the differences between single quotes, double quotes, and backticks in MySQL.
- Describe how the `ANSI_QUOTES` SQL mode changes how the parser interprets double quotes.
- Write queries that clearly distinguish string literals from identifiers.
- Avoid `Unknown column` and syntax errors when `ANSI_QUOTES` is enabled.
- Inspect and modify SQL mode at the session/global level in a controlled manner.
- Write DDL, dynamic queries, and migrations that are more portable across MySQL environments.

## 1. Identifiers and String Literals Are Two Distinct Elements

In SQL, an **identifier** is the name of a database object, such as a database, table, column, index, or alias name. A **string literal** is a text value written directly in a statement, such as `'Nguyen An'` or `'PAID'`.

Example:

```sql
SELECT customer_name
FROM customers
WHERE status = 'ACTIVE';
```

In this statement:

- `customer_name`, `customers`, and `status` are identifiers.
- `'ACTIVE'` is a string literal.

MySQL has multiple ways to write identifiers and literals. Single quotes are always the standard way to write string literals. Backticks are used to quote identifiers in MySQL syntax. Double quotes have meaning that depends on the SQL mode, specifically `ANSI_QUOTES`.

## 2. Default MySQL Rules

When `ANSI_QUOTES` is not enabled:

- Single quotes `'...'` represent a string literal.
- Double quotes `"..."` also represent a string literal.
- Backticks `` `...` `` represent an identifier.

Example:

```sql
SELECT
    'hello' AS single_quoted_text,
    "hello" AS double_quoted_text,
    `customer_name` AS customer_name_column
FROM customers;
```

Here, both `'hello'` and `"hello"` are fixed strings. `` `customer_name` `` is a column name. If the table has no `customer_name` column, the statement fails with an error.

An easily confusing example:

```sql
SELECT "customer_name"
FROM customers;
```

In default mode, the statement above returns the text string `customer_name` for every row rather than reading the column's value. To read the column, write:

```sql
SELECT customer_name
FROM customers;

-- Or quote the identifier using MySQL syntax
SELECT `customer_name`
FROM customers;
```

When reading legacy code, you cannot look at double quotes alone and assume it is a column name. You need to know the SQL mode of the session executing the statement.

## 3. ANSI_QUOTES Changes the Meaning of Double Quotes

`ANSI_QUOTES` is a MySQL SQL mode. When this mode is enabled, double quotes are used to quote identifiers, similar to how standard SQL uses double quotes. Double quotes **can no longer be used to write string literals**.

When `ANSI_QUOTES` is enabled:

- `'...'` remains a string literal.
- `"..."` is an identifier.
- `` `...` `` remains an identifier in MySQL syntax.

Example:

```sql
-- With ANSI_QUOTES enabled, "customer_name" is a column name
SELECT "customer_name"
FROM customers
WHERE "status" = 'ACTIVE';
```

In this statement, `"customer_name"` and `"status"` are identifiers; `'ACTIVE'` remains a string literal.

Conversely, the following statement no longer means a fixed string when `ANSI_QUOTES` is enabled:

```sql
SELECT "hello" AS greeting;
```

MySQL interprets `"hello"` as an identifier named `hello`. If there is no matching column or identifier in that context, the statement may report `Unknown column 'hello' in 'field list'`. To obtain the string `hello`, you must use:

```sql
SELECT 'hello' AS greeting;
```

### 3.1. Comparison Before and After Enabling the Mode

Suppose there is a table:

```sql
CREATE TABLE customers (
    customer_id BIGINT NOT NULL,
    customer_name VARCHAR(150) NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;
```

| Statement | Without `ANSI_QUOTES` | With `ANSI_QUOTES` |
|---|---|---|
| `SELECT "customer_name" FROM customers;` | Returns the string `customer_name` on every row | Reads column `customer_name` |
| `SELECT 'customer_name' FROM customers;` | Returns the string `customer_name` on every row | Returns the string `customer_name` on every row |
| ``SELECT `customer_name` FROM customers;`` | Reads column `customer_name` | Reads column `customer_name` |
| `WHERE status = "ACTIVE"` | Compares with string literal `ACTIVE` | Interprets `ACTIVE` as an identifier; may error if it does not exist |
| `WHERE status = 'ACTIVE'` | Compares with string literal `ACTIVE` | Compares with string literal `ACTIVE` |

This is why an application may run normally in a development environment yet fail after deployment: the two environments have different `sql_mode` settings.

## 4. Quoting Identifiers Properly

### 4.1. Using Backticks in MySQL Syntax

Backticks are MySQL's traditional way to quote identifiers and continue to work when `ANSI_QUOTES` is enabled:

```sql
SELECT `order`, `group`, `select`
FROM `sales-data`.`order details`;
```

This example illustrates names with spaces, hyphens, or keyword collisions. In new designs, avoid names with spaces or keyword collisions unless there is a clear reason. Quoting identifiers helps the parser recognize the name accurately, though it does not make the name easier to maintain.

### 4.2. Using Double Quotes When ANSI_QUOTES Is Enabled

With `ANSI_QUOTES`, you can use double quotes to quote identifiers:

```sql
SELECT "customer_name"
FROM "customers";
```

If compatibility across servers/sessions with differing SQL modes is needed, backticks are usually the more predictable MySQL-specific choice. If intentionally using ANSI syntax, ensure the mode is configured consistently across all connections and environments.

### 4.3. Escaping Quote Characters Inside Identifiers

When an identifier name contains the same character used to quote it, double that quote character.

With backticks:

```sql
SELECT `column``name`
FROM `sample``table`;
```

With double quotes in `ANSI_QUOTES` mode:

```sql
SELECT "column""name"
FROM "sample""table";
```

Do not arbitrarily use backslashes to escape identifiers. Identifier quoting rules differ from string literal escaping rules.

### 4.4. Quoting Identifiers Does Not Change Case Sensitivity

Quoting an identifier does not automatically make a table or column name case-sensitive. Case sensitivity rules for database/table names can depend on the operating system and `lower_case_table_names`; column names follow MySQL's own rules. Do not try to solve case-sensitivity differences by adding backticks or double quotes.

## 5. Writing String Literals Safely

### 5.1. Using Single Quotes

To write text in SQL statements, use single quotes:

```sql
SELECT customer_id, customer_name
FROM customers
WHERE status = 'ACTIVE';
```

This rule remains true when `ANSI_QUOTES` is enabled. Thus, using single quotes for literals makes statements less dependent on SQL mode.

### 5.2. Escaping Single Quotes Inside Strings

A single quote inside a string literal can be represented by two consecutive single quotes:

```sql
SELECT 'Customer''s order' AS description;
```

The result is `Customer's order`. This syntax clearly follows standard SQL quoting rules. Backslash behavior inside string literals depends on modes like `NO_BACKSLASH_ESCAPES`, so you should not build SQL strings by manual concatenation and escaping.

### 5.3. Do Not Use Double Quotes for String Literals in New Code

The following code easily runs in a default environment but breaks when `ANSI_QUOTES` is enabled:

```sql
-- Avoid using for string literals
SELECT "PAID" AS payment_status;

-- More stable approach
SELECT 'PAID' AS payment_status;
```

When standardizing a codebase, locate literals written with double quotes and switch them to single quotes after confirming they are genuinely text values rather than identifiers.

## 6. Checking the Current SQL Mode

SQL mode is a collection of options that alter how MySQL parses or processes SQL. `ANSI_QUOTES` is one member of this list.

Check at both SESSION and GLOBAL scope:

```sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;
```

Or:

```sql
SHOW GLOBAL VARIABLES LIKE 'sql_mode';
SHOW SESSION VARIABLES LIKE 'sql_mode';
```

Specifically check whether `ANSI_QUOTES` is enabled in the session:

```sql
SELECT FIND_IN_SET('ANSI_QUOTES', @@SESSION.sql_mode) > 0
       AS ansi_quotes_enabled;
```

A result of `1` means enabled; `0` means this mode is absent from the session list. Do not infer the server's SQL mode from client configuration or from another connection.

## 7. Enabling ANSI_QUOTES in a Test Session

To test without affecting other connections, you can modify the SQL mode of the current session. First, save the old value:

```sql
SET @saved_sql_mode = @@SESSION.sql_mode;

SET SESSION sql_mode = IF(
    FIND_IN_SET('ANSI_QUOTES', @@SESSION.sql_mode) > 0,
    @@SESSION.sql_mode,
    CONCAT_WS(',', NULLIF(@@SESSION.sql_mode, ''), 'ANSI_QUOTES')
);
```

This snippet adds `ANSI_QUOTES` if not already present while preserving other session modes. Verify:

```sql
SELECT @@SESSION.sql_mode;
SELECT 'hello' AS string_literal;
```

Once enabled, you can test:

```sql
-- "customer_name" is an identifier
SELECT "customer_name"
FROM customers;

-- "hello" is interpreted as an identifier, not a string literal
SELECT "hello" AS greeting;
```

The second statement will only run if a matching identifier exists in that context; otherwise, it errors. To restore the original mode in the test session:

```sql
SET SESSION sql_mode = @saved_sql_mode;
```

The `@saved_sql_mode` variable exists only within the current connection. When the connection closes, the session state and this user variable end.

Do not run `SET SESSION sql_mode = 'ANSI_QUOTES'` in an application if the goal is only to add this mode: that statement replaces the session's entire mode list and can accidentally drop modes like `STRICT_TRANS_TABLES`.

## 8. GLOBAL Scope and Application Impact

`SET GLOBAL sql_mode = ...` changes the default for sessions created afterward; already open sessions generally retain their current `@@SESSION.sql_mode`. Therefore, enabling `ANSI_QUOTES` globally does not guarantee all running connection pools immediately use the new mode.

Before changing GLOBAL or persistent configuration, you need to:

1. Check the current mode at both GLOBAL and SESSION scopes.
2. Audit applications, jobs, migration tools, and clients for double-quoted string literals.
3. Test in a staging environment with the same driver, ORM, migrations, and server version.
4. Plan how to roll out to connection pools and handle existing sessions.
5. Monitor syntax errors and `Unknown column` errors after the change.

To preserve configuration across restarts, use the configuration file or the persistence mechanism appropriate for your MySQL version and environment configuration management workflow. Do not change GLOBAL in production just to test the syntax of a single statement.

## 9. ANSI_QUOTES in Views, Routines, and Migrations

SQL mode can affect how a statement is parsed at object creation time. MySQL stores the relevant SQL mode when creating stored procedures, functions, triggers, and events; these objects execute using the mode recorded at creation time. Views also store the creation mode and use it when processing the view definition.

This means subsequent GLOBAL changes do not automatically rewrite quoting in existing objects. When migrating environments or standardizing SQL modes, examine all of the following:

- Stored procedures and functions.
- Triggers and events.
- Views.
- Migration scripts and schema initialization scripts.
- SQL generated by ORMs, query builders, or applications.

If a routine was created without `ANSI_QUOTES`, double quotes inside the routine body may have been interpreted as string literals. Simply enabling `ANSI_QUOTES` on the server later does not turn the stored definition into identifiers. Conversely, a routine created while the mode is enabled may depend on that identifier interpretation. Inspect and recreate objects with verified DDL when standardizing.

## 10. Prepared Statements and Dynamic Queries

Prepared statements separate data values from SQL statement structure. The `?` placeholder is used for values, not to substitute table names, column names, or keywords.

Java JDBC example:

```java
String sql = "SELECT customer_id, customer_name "
           + "FROM customers WHERE status = ?";

try (var statement = connection.prepareStatement(sql)) {
    statement.setString(1, "ACTIVE");
    try (var result = statement.executeQuery()) {
        while (result.next()) {
            long id = result.getLong("customer_id");
            String name = result.getString("customer_name");
        }
    }
}
```

The value `'ACTIVE'` is passed via a parameter; there is no need to manually add single or double quotes.

If you need to select columns or tables dynamically, you cannot write `SELECT ? FROM ?` and expect placeholders to be substituted with identifiers. Map selections from a fixed allowlist:

```java
String selectedColumn = switch (requestedSort) {
    case "name" -> "customer_name";
    case "created" -> "created_at";
    default -> throw new IllegalArgumentException("Unsupported sort field");
};

String sql = "SELECT customer_id, customer_name FROM customers ORDER BY `"
           + selectedColumn + "`";
```

This example only concatenates an identifier selected from an application-controlled allowlist. Never insert user-supplied column or table names directly into SQL. If dynamic identifiers must be quoted, use the driver/database's proper quoting function and still validate names against an allowlist; quoting does not replace input validation.

## 11. Conventions for Portable SQL

To reduce errors across environments with `ANSI_QUOTES` enabled or disabled, apply these conventions:

- Use single quotes for all string literals.
- Use backticks for identifiers when MySQL-specific quoting syntax is needed.
- Avoid table/column names with spaces, hyphens, or keyword collisions in new schemas.
- Do not assume SQL mode on one machine matches another environment; check `@@SESSION.sql_mode` from the actual connection.
- Do not replace the entire `sql_mode` just to add one mode; preserve existing modes.
- Review routines, triggers, events, views, and migration scripts when changing modes.
- Use prepared statements for values; use allowlists for dynamic identifiers.

Example query following these conventions:

```sql
SELECT
    `customer_id`,
    `customer_name`
FROM `customers`
WHERE `status` = 'ACTIVE'
  AND `created_at` >= '2026-01-01';
```

The statement above uses backticks for identifiers and single quotes for literals, making it independent of whether `ANSI_QUOTES` is enabled.

## 12. Checklist When Enabling ANSI_QUOTES or Switching Environments

- [ ] Recorded `@@GLOBAL.sql_mode` and `@@SESSION.sql_mode`.
- [ ] Searched for string literals currently written with double quotes.
- [ ] Verified whether remaining double-quoted tokens are identifiers.
- [ ] Converted literals to single quotes in code requiring compatibility.
- [ ] Checked identifier names, keywords, and quoting in DDL.
- [ ] Audited views, stored procedures, functions, triggers, and events.
- [ ] Tested migrations, ORMs, and generated queries on staging.
- [ ] Planned how to update connection pools and existing sessions.
- [ ] Prepared an SQL mode rollback plan if the application encounters errors.

## 13. Conclusion

`ANSI_QUOTES` changes the meaning of double quotes in MySQL: when the mode is off, double quotes represent string literals; when enabled, they quote identifiers. Single quotes continue to denote string literals and backticks continue to quote identifiers in MySQL syntax.

Use single quotes for text, quote identifiers consistently, check SQL mode from the actual session, and test all changes in an equivalent environment before deployment. These conventions keep SQL readable, reduce `Unknown column` errors, and prevent unintended dependence on SQL mode configuration.
