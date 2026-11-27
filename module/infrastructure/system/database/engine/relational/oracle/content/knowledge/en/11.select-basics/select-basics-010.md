# Bind Variables, Literals, and Distinguishing Values from Object Names

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** SELECT Basics  
> **Objective:** Distinguish data values from SQL structure; use literals and bind variables properly in Oracle SQL, PL/SQL, and Java/JDBC; build safe dynamic SQL when table/column names must vary; avoid SQL injection, NLS bugs, and cursor reuse issues.

## 1. A SQL Statement Consists of Values and Structure

Consider the statement:

```sql
SELECT employee_id, first_name, salary
FROM employees
WHERE department_id = 50;
```

In this statement:

- `SELECT`, `FROM`, `WHERE` are SQL keywords and structure.
- `EMPLOYEES`, `EMPLOYEE_ID`, `FIRST_NAME`, `SALARY`, `DEPARTMENT_ID` are object names (identifiers).
- `50` is a data value, written directly as a numeric literal.

If the application needs to filter by a user-chosen department, it can write:

```sql
SELECT employee_id, first_name, salary
FROM employees
WHERE department_id = :p_department_id;
```

`:p_department_id` is a bind variable. The client passes the actual value at execution time.

Two kinds of information must be kept separate:

1. **Value to search for:** e.g., department ID equal to 50. This is data and can be bound.
2. **Object to query:** e.g., table `EMPLOYEES` and column `DEPARTMENT_ID`. This is SQL structure, resolved when Oracle parses the statement.

Bind variables substitute values—never table names, column names, schemas, keywords, or arbitrary fragments of SQL syntax.

## 2. Literals in Oracle SQL

A **literal** is a value written directly inside SQL text. Oracle supports literals across multiple data types.

### 2.1. Character Strings

Strings are enclosed in single quotes:

```sql
SELECT *
FROM employees
WHERE first_name = 'Steven';
```

To represent a single quote inside a string, double the quote:

```sql
SELECT 'O''Brien' AS customer_name
FROM dual;
```

The result is `O'Brien`. Never use Java or JavaScript escape rules in place of SQL literal syntax.

Oracle also supports alternative quoting with the `q` prefix:

```sql
SELECT q'[Customer's note: "call back"]' AS note_text
FROM dual;
```

The delimiter pair can be `[]`, `{}`, `()`, `<>`, or another suitable character. This is handy when a string contains many single quotes.

National character literals can be written with the `N` prefix:

```sql
SELECT N'Nguyễn Văn An' AS full_name
FROM dual;
```

Storing Unicode still depends on the character set and column data type; the `N` prefix does not replace proper charset design.

### 2.2. Numbers

Numeric literals use a period as the decimal separator:

```sql
SELECT 125, -42, 12.75, 1.25E3
FROM dual;
```

Do not write literals in localized display formats like `1.234,56` expecting every session to interpret them the same way. When an application passes numbers, use numerically typed binds. When parsing strings from external sources, use `TO_NUMBER` with explicit format masks and NLS parameters.

### 2.3. DATE and TIMESTAMP Literals

An ANSI DATE literal has the form `DATE 'YYYY-MM-DD'`:

```sql
SELECT *
FROM orders
WHERE order_date >= DATE '2026-11-14';
```

This literal is independent of `NLS_DATE_FORMAT` and represents 00:00:00 on that date. Oracle DATE includes hours, minutes, and seconds, not just a calendar date.

To select all rows within a day, use a half-open interval:

```sql
SELECT order_id, order_date
FROM orders
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15';
```

Timestamp literal:

```sql
SELECT TIMESTAMP '2026-11-14 09:30:45.123456'
FROM dual;
```

Timezone-aware timestamps can be created with `TO_TIMESTAMP_TZ` or an appropriate literal. When receiving values from an application, binding a properly typed timestamp is usually easier to control than concatenating and parsing strings.

### 2.4. NULL and INTERVAL

`NULL` means an unknown/missing value. Never write `column = NULL`; use `IS NULL`:

```sql
SELECT *
FROM employees
WHERE commission_pct IS NULL;
```

Durations use the INTERVAL type:

```sql
SELECT TIMESTAMP '2026-11-14 09:00:00'
       + INTERVAL '45' MINUTE AS end_time
FROM dual;
```

Do not confuse a point in time with a duration. Binding NULL into `column = :p_value` does not turn that condition into a NULL check either; SQL logic evaluates it to UNKNOWN.

## 3. What Is a Bind Variable?

A bind variable is a placeholder in a SQL statement whose value is supplied separately at execution time:

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE customer_id = :p_customer_id
  AND order_date >= :p_from_date
  AND order_date <  :p_to_date
  AND status = :p_status;
```

The SQL text stays identical as customer, date, or status values change. The client sends the bound values with appropriate data types.

| Aspect | Literal | Bind variable |
|---|---|---|
| Example | `department_id = 50` | `department_id = :p_dept` |
| Where value lives | Directly inside SQL text | Passed at execution time |
| SQL text when value changes | Usually changes | Unchanged if structure is unchanged |
| Cursor reuse | Less favorable when each value produces different SQL text | Favorable for cursor reuse |
| Input safety | Error-prone if concatenating unvalidated strings | Safer when bound properly |
| Good fit for | Fixed constants in SQL logic | Data from UI, APIs, batches, or applications |

Literals are not bad. A fixed condition like `status = 'ACTIVE'` inside a view or report can be completely appropriate. The rule is never to concatenate external data into SQL text when you can bind.

## 4. Why Are Bind Variables Important?

### 4.1. Parsing and Cursor Reuse

Oracle must parse a SQL statement to understand its structure, resolve objects, check privileges, and build an execution plan.

If an application generates distinct statements merely because filter values vary:

```sql
SELECT * FROM employees WHERE department_id = 10;
SELECT * FROM employees WHERE department_id = 20;
SELECT * FROM employees WHERE department_id = 30;
```

then the SQL text differs each time. This can increase hard parses and put pressure on the shared pool.

Using binds:

```sql
SELECT * FROM employees WHERE department_id = :p_dept;
```

keeps the SQL text identical and enables cursor/statement reuse. A **hard parse** builds a new cursor/plan when no reusable cursor matches; a **soft parse** reuses an existing cursor and avoids part of that work.

Binding does not guarantee every execution uses the exact same child cursor. Differences in data type, optimizer environment, metadata, or other factors can still cause Oracle to create separate child cursors.

### 4.2. Binding Does Not Make a Query Fast on Its Own

A SQL statement with binds can still do a full table scan, pick a suboptimal index, trigger implicit conversion, or wait on I/O. Binding primarily separates data from SQL text and improves cursor sharing.

Furthermore, a column with skewed data distribution can mean a single execution plan is not optimal for every bind value. Oracle provides mechanisms such as **bind peeking** and **adaptive cursor sharing** to evaluate certain bind-sensitive cases and potentially maintain multiple child cursors/plans.

When the same SQL runs fast for one value and slow for another, inspect the SQL ID, child cursors, bind data types, statistics/histograms, execution plans, logical reads, physical reads, and waits. Never disable binding or spray literals everywhere just because one plan was poor.

### 4.3. CURSOR_SHARING Does Not Replace Binding in Applications

Oracle has a `CURSOR_SHARING` parameter with options such as `EXACT` and `FORCE`. `FORCE` can replace certain literals with system-generated binds to increase cursor sharing. However, it does not replace `PreparedStatement`, does not protect dynamically concatenated identifiers, and does not fix SQL injection. It is a DBA configuration whose system-wide impact must be evaluated carefully.

## 5. Binds in SQL*Plus, SQLcl, and SQL Developer

SQL*Plus/SQLcl supports declaring bind variables with `VARIABLE`:

```sql
VARIABLE p_department_id NUMBER

EXEC :p_department_id := 50;

SELECT employee_id, first_name, department_id
FROM employees
WHERE department_id = :p_department_id;

PRINT p_department_id;
```

- `VARIABLE` creates a bind variable in the client session.
- `EXEC` assigns a value to the bind.
- The colon prefix references the bind in SQL.
- `PRINT` displays the bind value.

Date example:

```sql
VARIABLE p_from_date DATE
EXEC :p_from_date := DATE '2026-11-01';

SELECT order_id, order_date
FROM orders
WHERE order_date >= :p_from_date;
```

In SQL Developer Worksheet, running scripts with SQL*Plus commands like `VARIABLE` and `EXEC` may behave differently from Run Statement. Use Run Script mode when executing the entire block.

## 6. Binds in Java/JDBC

In JDBC, `PreparedStatement` uses question marks `?` as positional placeholders:

```java
String sql = """
    SELECT employee_id, first_name, salary
    FROM employees
    WHERE department_id = ?
      AND salary >= ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, departmentId);
    ps.setBigDecimal(2, minimumSalary);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            int employeeId = rs.getInt("EMPLOYEE_ID");
            String firstName = rs.getString("FIRST_NAME");
            BigDecimal salary = rs.getBigDecimal("SALARY");
            System.out.println(employeeId + " " + firstName + " " + salary);
        }
    }
}
```

Placeholder indices are 1-based. Setters must match the column data types:

| Oracle type | Common JDBC setter |
|---|---|
| NUMBER monetary/decimal | `setBigDecimal` |
| NUMBER integer within int/long range | `setInt` or `setLong` |
| VARCHAR2/CHAR | `setString` |
| DATE/TIMESTAMP | JDBC or Java time API matching column semantics |
| TIMESTAMP WITH TIME ZONE | `setObject` with `OffsetDateTime` if supported by driver, or Oracle JDBC API |
| BLOB/CLOB | `setBlob`/`setClob` or appropriate stream |

Do not convert every value to `String` and leave Oracle to perform implicit conversion. That can depend on NLS, fail, or force conversions on the column.

### 6.1. Binding NULL with the Proper Type

If a column allows NULL, JDBC can pass NULL along with its SQL type:

```java
String sql = """
    INSERT INTO employees_stage (employee_id, commission_pct)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, employeeId);
    ps.setNull(2, java.sql.Types.NUMERIC);
    ps.executeUpdate();
}
```

`setNull(index, sqlType)` tells the driver the type of the NULL value. For LOBs, UDTs, or specialized types, specific APIs may be required.

### 6.2. Do Not Concatenate Dates/Times into SQL Strings

Avoid:

```java
String sql = "SELECT * FROM orders WHERE order_date = '"
             + inputDate + "'";
```

Use `PreparedStatement` and bind an appropriate date/time type. Oracle `DATE` stores time down to seconds; if the column holds times of day, do not pass a Java `LocalDate` and inadvertently strip the time component. For `TIMESTAMP WITH TIME ZONE`, verify compatible mapping with your JDBC driver.

`PreparedStatement` separates SQL text from parameters and supports statement/cursor reuse, though one Java object does not permanently map 1-to-1 to a single cursor forever. Connection pools, statement caches, child cursors, and invalidations all affect actual lifecycle.

## 7. Binds in PL/SQL and Dynamic SQL

In PL/SQL, local variables can be used directly in static SQL:

```sql
DECLARE
    l_department_id NUMBER := 50;
BEGIN
    FOR r IN (
        SELECT employee_id, first_name
        FROM employees
        WHERE department_id = l_department_id
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r.employee_id || ': ' || r.first_name
        );
    END LOOP;
END;
/
```

For dynamic SQL, pass values via `USING`:

```sql
DECLARE
    l_department_id NUMBER := 50;
    l_min_salary    NUMBER := 5000;
    l_count         NUMBER;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM employees
         WHERE department_id = :1
           AND salary >= :2'
    INTO l_count
    USING l_department_id, l_min_salary;

    DBMS_OUTPUT.PUT_LINE('Count = ' || l_count);
END;
/
```

The SQL text defines the structure; `USING` supplies the values. For standard SQL statements in Native Dynamic SQL, bind arguments associate by placeholder position. When executing anonymous PL/SQL blocks or dynamic calls, placeholder rules differ; consult the SQL Reference rather than assuming duplicate placeholder names let you ignore order.

Dynamic SQL does not mean concatenating everything. Bind every value that can be bound; construct dynamically only the structural parts that genuinely need to vary.

## 8. Why Can't You Bind Table Names or Column Names?

Example:

```sql
VARIABLE table_name VARCHAR2(30)
EXEC :table_name := 'EMPLOYEES';

SELECT *
FROM :table_name;
```

`:table_name` is a bind value, not an identifier. The parser must know which table is referenced while parsing the SQL statement; binds are processed after structure is resolved.

Similarly:

```sql
SELECT :column_name
FROM employees;
```

This statement does not read the column whose name was passed in. It returns the bound string value as a constant expression for each row, rather than substituting a column name.

`ORDER BY :sort_column` likewise does not sort by the column named in the bind. If the bind is the string `'SALARY'`, it is a constant literal value, not the identifier token `SALARY`.

| Component | Can it be bound directly? | How to handle |
|---|---|---|
| Numeric value `salary = ?` | Yes | Numeric bind |
| String value `name = ?` | Yes | String bind |
| Start/end dates | Yes | Typed DATE/TIMESTAMP bind |
| Table name after FROM | No | Allowlist/validate identifier, then build dynamic SQL |
| Column name after SELECT/ORDER BY | No | Allowlist or use fixed queries |
| ASC/DESC, JOIN, WHERE | No | Pick from validated fixed tokens/structures |
| Schema/sequence name | No | Validate identifiers and privileges |
| LIKE value | Yes | Bind pattern; escape wildcards if needed |
| Elements in an IN list | Yes | One placeholder per element or a collection strategy |

Rule: **bind data; control SQL structure separately.**

## 9. SQL Injection and How to Prevent It

SQL injection occurs when input data is interpreted as SQL syntax. For example, an application concatenates `username`:

```java
String sql =
    "SELECT * FROM app_users WHERE username = '"
    + username
    + "'";
Statement st = connection.createStatement();
ResultSet rs = st.executeQuery(sql);
```

If a user enters `' OR '1'='1`, the SQL can become:

```sql
SELECT *
FROM app_users
WHERE username = '' OR '1'='1';
```

The condition is always true and can return unintended user accounts.

Fix with binding:

```java
String sql =
    "SELECT user_id, username " +
    "FROM app_users " +
    "WHERE username = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, username);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Process results.
        }
    }
}
```

The input string is passed as a username value, never becoming SQL syntax.

Manual string escaping is not a primary defense: applications span many data types, charsets, formats, and syntactic contexts. Use binds for values, allowlists for identifiers, enforce least privilege on database accounts, and never let users submit arbitrary SQL fragments for execution.

### 9.1. Binding Does Not Protect Dynamically Concatenated Identifiers

The following remains dangerous:

```java
String sql =
    "SELECT * FROM " + userSuppliedTable +
    " WHERE department_id = ?";

PreparedStatement ps = connection.prepareStatement(sql);
ps.setInt(1, departmentId);
```

`DEPARTMENT_ID` is safely bound, yet `userSuppliedTable` is still concatenated into SQL text. Table names must be validated separately.

## 10. Dynamic Identifiers: Allowlists and DBMS_ASSERT

### 10.1. Application-Layer Allowlists

Suppose a screen allows selecting only three reports:

```text
EMPLOYEES
ORDERS
PAYMENTS
```

Map the UI choice to a fixed identifier:

```java
Map<String, String> allowedTables = Map.of(
    "employees", "EMPLOYEES",
    "orders", "ORDERS",
    "payments", "PAYMENTS"
);

String tableName = allowedTables.get(requestedReport);
if (tableName == null) {
    throw new IllegalArgumentException("Unsupported report");
}

String sql =
    "SELECT * FROM " + tableName +
    " WHERE created_at >= ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setTimestamp(1, fromTimestamp);
    // Execute query...
}
```

The table name comes strictly from an approved map; the date value is still bound. A syntactically valid identifier can still point to an object the user is unauthorized to read, so an allowlist also enforces business authorization.

### 10.2. DBMS_ASSERT in PL/SQL

Oracle provides the `DBMS_ASSERT` package to validate or quote certain identifier/literal forms in dynamic SQL.

```sql
DECLARE
    l_table_name VARCHAR2(261) := 'EMPLOYEES';
    l_safe_name  VARCHAR2(261);
    l_count      NUMBER;
BEGIN
    l_safe_name := DBMS_ASSERT.SQL_OBJECT_NAME(l_table_name);

    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM ' || l_safe_name
        INTO l_count;

    DBMS_OUTPUT.PUT_LINE('Rows = ' || l_count);
END;
/
```

Selected functions:

- `DBMS_ASSERT.SQL_OBJECT_NAME`: validates a SQL object name and requires the object to exist.
- `DBMS_ASSERT.SIMPLE_SQL_NAME`: validates a simple SQL name.
- `DBMS_ASSERT.QUALIFIED_SQL_NAME`: validates a qualified name under supported syntax.
- `DBMS_ASSERT.ENQUOTE_NAME`: quotes an identifier.
- `DBMS_ASSERT.ENQUOTE_LITERAL`: quotes a string literal.

`DBMS_ASSERT` does not replace business allowlists, authorization checks, or verifying whether a user is permitted to pick that object.

### 10.3. Quoted Identifiers Are Not Binds

Oracle permits quoted object names:

```sql
CREATE TABLE "Monthly Sales" (
    "Order ID" NUMBER
);

SELECT "Order ID"
FROM "Monthly Sales";
```

Names with spaces or mixed casing make SQL harder to write and integrate. Application schemas should normally use simple, unquoted identifiers. Quoting a name does not turn an identifier into a bind variable either.

## 11. Dynamic ORDER BY

If users choose the sort column and direction, allowlist the tokens:

```java
Map<String, String> sortColumns = Map.of(
    "name", "FIRST_NAME",
    "salary", "SALARY",
    "hireDate", "HIRE_DATE"
);

String sortColumn = sortColumns.get(requestedSort);
if (sortColumn == null) {
    throw new IllegalArgumentException("Invalid sort field");
}

String direction;
if ("asc".equalsIgnoreCase(requestedDirection)) {
    direction = "ASC";
} else if ("desc".equalsIgnoreCase(requestedDirection)) {
    direction = "DESC";
} else {
    throw new IllegalArgumentException("Invalid sort direction");
}

String sql =
    "SELECT employee_id, first_name, salary " +
    "FROM employees " +
    "WHERE department_id = ? " +
    "ORDER BY " + sortColumn + " " + direction;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, departmentId);
    // Execute...
}
```

`sortColumn` and `direction` come from fixed sets; `departmentId` remains a bind.

With only a few sort options, you can use `CASE` in `ORDER BY` to keep the SQL text fixed:

```sql
SELECT employee_id, first_name, salary
FROM employees
WHERE department_id = :p_department
ORDER BY
    CASE WHEN :p_sort = 'NAME' THEN first_name END,
    CASE WHEN :p_sort = 'SALARY' THEN salary END;
```

This approach requires care regarding data types, NULLs, sort directions, and execution plans. It does not always exploit index ordering as cleanly as a direct ORDER BY.

## 12. Binds in an IN List

A bind variable holds a single value, not a SQL snippet containing multiple values.

```sql
SELECT *
FROM employees
WHERE employee_id IN (:p_ids);
```

If `:p_ids` receives the string `'10,20,30'`, Oracle treats it as one string; it does not split it into three numbers.

### 12.1. One Placeholder Per Element

For short lists:

```sql
SELECT *
FROM employees
WHERE employee_id IN (:id1, :id2, :id3);
```

Each placeholder receives one separate value. If the application builds the placeholder count from list size, build only the `?` placeholder syntax dynamically; every actual ID is still bound. JDBC does not automatically expand one `?` parameter into multiple parameters just because you pass a Java `List`.

### 12.2. Collections, Temporary Tables, or JSON_TABLE

Oracle supports collection/table expressions in suitable cases:

```sql
SELECT e.employee_id, e.first_name
FROM employees e
WHERE e.employee_id IN (
    SELECT column_value
    FROM TABLE(sys.odcinumberlist(10, 20, 30))
);
```

The example uses literals for illustration. Binding a SQL collection from Java depends on the Oracle JDBC API and SQL collection type; do not assume `setObject(List)` automatically turns a Java `List` into an Oracle collection.

For large or reused lists, you can load IDs into a global temporary table and join. Another option on supporting versions is binding a JSON document and shredding it into rows with `JSON_TABLE`. Test size limits, formatting, and performance against your workload.

## 13. LIKE, Wildcards, and NULL

### 13.1. LIKE Patterns

Binding a pattern in LIKE is valid:

```sql
SELECT employee_id, first_name
FROM employees
WHERE first_name LIKE :p_pattern;
```

`%` matches any string; `_` matches a single character. This is LIKE pattern behavior, not SQL injection. If you want an exact substring match on input that may contain `%` or `_`, escape the wildcards using a chosen escape character and Oracle syntax.

Example:

```sql
SELECT employee_id, first_name
FROM employees
WHERE first_name LIKE :p_pattern ESCAPE '\';
```

Build the pattern in the application by escaping the escape character first, then `%` and `_`. Searches like `LIKE '%text%'` rarely leverage a standard B-tree index well; for large text search, evaluate Oracle Text or an appropriate search architecture.

### 13.2. Optional Filters with NULL

You can write:

```sql
SELECT employee_id, first_name
FROM employees
WHERE (:p_department_id IS NULL
       OR department_id = :p_department_id);
```

If NULL is bound, the predicate allows all departments; if a value is bound, it filters by department. However, `OR` can make it harder for the optimizer to pick an ideal access path for every case. With only a few clear filter combinations, generating fixed SQL variants per active filter shape and binding values is often easier to tune.

Never write `= NULL`. Use `IS NULL` or `IS NOT NULL`.

## 14. Binds and NLS

### 14.1. Dates and Times

Do not rely on implicit conversion:

```sql
SELECT *
FROM orders
WHERE order_date >= '14/11/2026';
```

Oracle may parse the string using the session's `NLS_DATE_FORMAT`; another session may have a different format and misinterpret it or fail.

Prefer:

- DATE literal `DATE '2026-11-14'` for constants in SQL.
- `TO_DATE(text, format_mask)` when genuinely parsing strings.
- Typed DATE/TIMESTAMP binds in applications.

### 14.2. Numbers

The string `'1,25'` can be interpreted differently depending on `NLS_NUMERIC_CHARACTERS`. In Java, bind `BigDecimal` rather than formatting numbers into strings.

Binding does not validate domain rules on input. The application must still parse, validate ranges, and pass the correct data type.

## 15. Literals in Static SQL vs. Binds in Applications

You do not have to turn every literal in SQL code into a bind.

**Fixed constants belonging to statement logic** can be written directly:

```sql
SELECT employee_id, first_name
FROM employees
WHERE status = 'ACTIVE';
```

If ACTIVE is a fixed rule in a view or report, a literal is appropriate.

**Values that vary per request** should be bound:

```sql
SELECT employee_id, first_name, salary
FROM employees
WHERE department_id = :p_department
  AND hire_date >= :p_from_date
  AND salary >= :p_min_salary;
```

**Varying statement structure** such as table names, column names, or sort directions cannot be bound directly. Validate choices against an allowlist, map to fixed identifiers/tokens, assemble SQL text solely from controlled pieces, and bind all data values.

## 16. Common Anti-Patterns

| Anti-pattern | Problem | Proper approach |
|---|---|---|
| Concatenating user values into SQL | SQL injection, varying SQL text, quoting bugs | PreparedStatement / Binds |
| Binding table or column names | A bind is a value, not an identifier | Allowlist and controlled dynamic SQL |
| `ORDER BY :column` | Does not sort by the passed identifier | Allowlist sort columns/directions |
| One bind holding `'10,20,30'` for IN | Oracle sees one string, not a list | One placeholder per item or collection/table |
| Binding everything as VARCHAR2 | Implicit conversion and NLS issues | Bind the proper data type |
| Comparing `column = NULL` | Evaluates to UNKNOWN | `IS NULL` |
| Parsing dates via default NLS | Session-dependent behavior | DATE literal, format mask, or typed bind |
| Manually escaping input and concatenating SQL | Easy to miss escaping in other contexts | Bind data |
| Using MAX(id) to get a newly inserted ID | Concurrent sessions can insert in between | RETURNING clause or JDBC generated keys |
| Disabling binds to fix one slow plan | Increases hard parses and injection risk | Inspect child cursors, bind peeking, statistics, and plans |

## 17. Practice Exercises

Exercises use a sample schema or lab table; run only in an environment you are authorized to access.

### Exercise 1 — Same SQL, Multiple Bind Values

```sql
VARIABLE p_dept NUMBER
EXEC :p_dept := 10;

SELECT employee_id, first_name, department_id
FROM employees
WHERE department_id = :p_dept;

EXEC :p_dept := 20;

SELECT employee_id, first_name, department_id
FROM employees
WHERE department_id = :p_dept;
```

Observe: the SQL text stays identical while the bind value changes. Explain why this supports cursor reuse.

### Exercise 2 — Converting Literals to Binds in Java

Write two versions of a query: one concatenating department ID into the SQL text, and one using `PreparedStatement` with `setInt`. Compare SQL text, data types, injection risk, and statement reusability.

### Exercise 3 — Binding a Table Name

Try:

```sql
SELECT COUNT(*) FROM :p_table;
```

Explain why the parser does not treat the bind as an identifier. Design an allowlist permitting only `EMPLOYEES` and `DEPARTMENTS`, then write dynamic SQL in PL/SQL using `DBMS_ASSERT` appropriately.

### Exercise 4 — Filtering a Date with Time Components

Given an `ORDER_DATE DATE` column storing both date and time. Write a query fetching all rows on Nov 14, 2026 using a DATE literal, then write a version binding the two day boundaries. Explain why `ORDER_DATE = DATE '2026-11-14'` misses rows after 00:00:00.

### Exercise 5 — NULL

Write a query filtering for NULL `COMMISSION_PCT`. Then bind NULL in JDBC and explain why `commission_pct = ?` is not equivalent to `commission_pct IS NULL`.

### Exercise 6 — IN List

An API receives three employee IDs. Propose how to build three placeholders and bind three numbers; then list collection, temporary table, and `JSON_TABLE` options for large lists. Explain why one CSV string does not automatically expand into multiple binds.

### Exercise 7 — Dynamic ORDER BY

A screen lets users sort by `NAME` or `SALARY`, in `ASC` or `DESC` direction. Write the allowlist logic, construct SQL text from validated choices, and bind department ID. Explain why `ORDER BY :sort_column` does not sort by that column.

### Exercise 8 — SQL Injection

Given a login query with `username` and `password_hash`, describe the risk if both inputs are concatenated into strings, then rewrite it using `PreparedStatement` with two binds. Also note the least-privilege principle and never logging secrets.

## 18. Decision Tree: Bind or Dynamic SQL?

```text
What component needs to go into the SELECT statement?
|
+-- Data value (NUMBER, DATE, STRING, TIMESTAMP, NULL)
|       └── BIND VARIABLE
|
+-- LIKE pattern
|       └── Bind pattern; escape wildcards if needed
|
+-- Table / column / schema / sequence name
|       └── Cannot bind as identifier
|              └── Allowlist + validate/quote + dynamic SQL
|
+-- ASC / DESC / keyword / operator / SQL clause
|       └── Pick fixed token/structure from allowlist
|
+-- Multi-value list
        +-- Small, known length: one placeholder per element
        +-- Large/reusable: collection, temporary table, or JSON_TABLE
```

## 19. Core Takeaways

- **Literals** are values written directly in SQL, suitable for fixed constants.
- **Bind variables** pass values separately at execution time, keeping SQL text stable and reducing SQL injection risk.
- **Binds never substitute for table names, column names, schemas, keywords, or SQL syntax fragments.**
- **PreparedStatement** is the standard way in JDBC to bind values; use type-appropriate setters.
- **Dynamic SQL** can be safe when all data values are bound and only allowlisted, validated identifiers/tokens are interpolated.
- **DBMS_ASSERT** helps validate/quote identifiers in PL/SQL, but does not replace business allowlists and authorization.
- **NULL** requires dedicated logic; equality comparison with a bound NULL does not equal `IS NULL`.
- **IN lists** do not expand from a single bind holding a CSV string.
- **NLS** is a strong reason to avoid passing dates or numbers as unformatted strings.
- **Cursor reuse** helps performance, though it does not guarantee a single optimal execution plan for every value.
- **Never use MAX(id)** to retrieve a just-inserted ID; use `RETURNING` or JDBC generated keys.

### Oracle Documentation to Consult

- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — Literals, bind variables, expressions, dynamic SQL, and identifiers.
- [Oracle Database PL/SQL Language Reference](https://docs.oracle.com/en/database/) — Native Dynamic SQL, `EXECUTE IMMEDIATE`, and `USING`.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — `DBMS_ASSERT`.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — parsing, shared SQL area, library cache, and cursors.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — bind peeking, adaptive cursor sharing, and execution plans.
- [Oracle Database JDBC Developer's Guide](https://docs.oracle.com/en/database/) — PreparedStatement, bind data types, and statement caching.

Exact syntax and capabilities depend on the Oracle version, JDBC driver, and client tool. When implementing, verify against your active release; the invariant principle is **bind values, control SQL structure separately**.
