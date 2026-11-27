# Bind Variables and Distinguishing Input Data from Object Names

When an application builds a `SELECT` statement from user input, it must distinguish two kinds of input:

- **Data values**: customer ID, order status, search keyword, start date, and result count.
- **SQL structure**: schema name, table name, column name, sort direction, chosen expressions, or syntax clauses.

Bind variables (parameter binding) pass data values into a SQL statement whose structure is already defined. This mechanism lets the database treat values separately from statement syntax, preventing user content from being parsed as part of SQL and often allowing reuse of prepared statements.

Placeholders are not universal variables for arbitrary SQL components. In a MySQL prepared statement, a question mark represents a value in an appropriate expression position; it cannot replace a table name, column name, `ASC`/`DESC` keyword, or an entire condition clause. When dynamic query structure selection is needed, the application must choose from an allowlist and then assemble only controlled object names into the SQL.

This article focuses on MySQL and building safe `SELECT` queries in applications. Examples use SQL prepared statements, Java JDBC, and the Python connector to clarify the difference between bound values and dynamic identifiers.

## 1. Input Data and SQL Structure Are Two Different Things

Suppose an order search screen provides these features:

- Search by customer ID.
- Filter by status.
- Choose the sort column.
- Choose ascending or descending order.
- Choose the number of rows to display.

In this requirement, `customer_id`, `status`, and `page_size` are data values. They can change between executions without altering the structure of the SQL statement.

By contrast, `created_at` or `total` chosen as the sort column are column names. `ASC` or `DESC` are syntactic keywords. They alter the statement structure and cannot be passed into an ordinary value placeholder.

| Input | Category | How to Handle |
|---|---|---|
| customer_id = 42 | Data value | Bind parameter |
| status = 'PAID' | Data value | Bind parameter |
| Start/end dates | Data value | Bind parameter |
| LIMIT row count | Data value | Bind if driver and statement support it |
| Table name orders | Identifier | Select from allowlist, then quote with proper syntax |
| Column name created_at | Identifier | Select from allowlist, then quote with proper syntax |
| ASC or DESC | SQL structure | Select from a fixed set of values |
| AND status = ? | SQL structural fragment | Append only from application-controlled logic branches |

This rule is the foundation for both preventing SQL injection and keeping queries readable, testable, and maintainable.

## 2. How Parameter Binding Works

### 2.1. Fixed-Structure SQL Statements

Instead of concatenating values directly into the SQL string:

~~~sql
SELECT order_id, customer_id, status, total
FROM orders
WHERE customer_id = 42
  AND status = 'PAID';
~~~

The application prepares a statement with placeholders:

~~~sql
SELECT order_id, customer_id, status, total
FROM orders
WHERE customer_id = ?
  AND status = ?;
~~~

Then passes the two values in order:

~~~text
parameter 1 = 42
parameter 2 = "PAID"
~~~

The database receives the statement and values via the prepared statement/driver protocol. The value `'PAID'` is treated strictly as expression data, never re-parsed as SQL syntax.

### 2.2. Placeholders Have Positions and Data Types

In MySQL prepared statements, a question mark is a parameter marker. Markers are assigned sequentially in order of appearance, starting from the first position.

~~~sql
SELECT order_id, total
FROM orders
WHERE customer_id = ?
  AND created_at >= ?
  AND status IN (?, ?);
~~~

Bind order:

1. Customer ID.
2. Start timestamp.
3. First status.
4. Second status.

The number of bound values must match the number of placeholders and the order must be exact. If passed in the wrong order, the statement may still execute and return wrong data or fail with type-conversion errors.

### 2.3. Binding Does Not Automatically Enforce Business Validation

Parameter binding protects the boundary between syntax and values, but it does not automatically validate:

- Whether the user has permission to view that `customer_id`.
- Whether the start date precedes the end date.
- Whether the requested row count exceeds application limits.
- Whether the status belongs to the set of valid statuses.
- Whether the search string is too long or contains business-invalid content.

The application must still validate types, value domains, and access permissions before execution. Prepared statements protect SQL syntax; they do not replace business validation and authorization.

## 3. Why Should You Not Concatenate Data into SQL?

Suppose an application concatenates search input directly:

~~~java
String sql =
    "SELECT order_id, status FROM orders " +
    "WHERE status = '" + userStatus + "'";
~~~

If the input is:

~~~text
PAID' OR '1'='1
~~~

The concatenated SQL becomes:

~~~sql
SELECT order_id, status
FROM orders
WHERE status = 'PAID' OR '1'='1';
~~~

The always-true condition can cause the query to return far more rows than intended. Other payloads can alter query logic or cause syntax errors.

Use placeholders:

~~~java
String sql =
    "SELECT order_id, status FROM orders WHERE status = ?";

PreparedStatement statement = connection.prepareStatement(sql);
statement.setString(1, userStatus);
~~~

Now the string `PAID' OR '1'='1` is passed as a single data value. It cannot close the literal and inject additional SQL operators.

Do not manually escape strings by replacing quotes or stripping special characters and continuing to concatenate SQL. Escaping rules depend on character sets, SQL modes, and syntactic context; parameter binding enforces that boundary reliably.

## 4. Placeholders Cannot Replace Table Names or Column Names

### 4.1. Common Mistakes

This is not a valid way to choose a table:

~~~sql
SELECT *
FROM ?
WHERE customer_id = ?;
~~~

Similarly, you cannot use an ordinary placeholder to substitute a column name:

~~~sql
SELECT ?
FROM orders;
~~~

In the second statement, the marker is a value expression. If you bind the string `'total'`, the result is usually the literal `'total'` repeated on every row, not the data from a column named `total`.

You cannot use placeholders to substitute:

- Database, schema, table, or column names.
- Index names in syntax positions requiring an identifier.
- Keywords like `ASC`, `DESC`, `JOIN`, `GROUP BY`.
- Operators such as `=`, `>`, `LIKE`.
- A complete SQL clause such as `WHERE ... ORDER BY ...`.

### 4.2. Identifiers Are Syntactic Components

MySQL uses identifiers to name databases, tables, columns, indexes, and other objects. Identifiers may require quoting with backticks:

~~~sql
SELECT order_id, created_at
FROM shop.orders;
~~~

Backticks distinguish object names from keywords or special characters. If an identifier contains a backtick, the internal backtick must be escaped by doubling it according to MySQL rules.

Quoting an identifier does not make an arbitrary name business-safe. A syntactically valid but unauthorized name could still let a user access a table or column they are not permitted to query. Therefore, an allowlist is required before assembling an identifier.

## 5. Building Dynamic SELECT Safely with an Allowlist

### 5.1. Selecting the Sort Column from a Fixed List

Suppose the UI allows sorting orders by creation time or total amount. The application maps the UI selection to a column name defined in code:

~~~java
String orderByColumn;

switch (requestedSort) {
    case "created":
        orderByColumn = "created_at";
        break;
    case "total":
        orderByColumn = "total";
        break;
    default:
        throw new IllegalArgumentException("Unsupported sort field");
}
~~~

Sort direction must also be restricted:

~~~java
String direction;

if ("asc".equalsIgnoreCase(requestedDirection)) {
    direction = "ASC";
} else if ("desc".equalsIgnoreCase(requestedDirection)) {
    direction = "DESC";
} else {
    throw new IllegalArgumentException("Unsupported sort direction");
}
~~~

After validating the structure, assemble the chosen fragments into SQL while still binding filter values:

~~~java
String sql =
    "SELECT order_id, customer_id, status, total, created_at " +
    "FROM orders " +
    "WHERE customer_id = ? " +
    "ORDER BY " + orderByColumn + " " + direction + " " +
    "LIMIT ?";

PreparedStatement statement = connection.prepareStatement(sql);
statement.setLong(1, customerId);
statement.setInt(2, pageSize);
~~~

In this example, only two components selected from fixed sets are concatenated into SQL. `customerId` and `pageSize` are data values and are bound.

### 5.2. Allowlists Must Map Values, Not Just Perform Weak Checks

A clearer approach is using a map from UI keys to identifiers:

~~~java
Map<String, String> allowedSortColumns = Map.of(
    "created", "created_at",
    "total", "total",
    "status", "status"
);

String orderByColumn = allowedSortColumns.get(requestedSort);
if (orderByColumn == null) {
    throw new IllegalArgumentException("Unsupported sort field");
}
~~~

The application never concatenates `requestedSort` verbatim. It only retrieves identifiers from a developer-defined map. If a user sends `created_at DESC; DROP TABLE orders`, that value is absent from the map and rejected.

Do not rely solely on a regex check like "only allow letters, digits, and underscores." A syntactically valid identifier can still refer to an object outside the scope the feature is allowed to access.

### 5.3. Selecting a Table Dynamically

If a report is permitted to read from one of several predefined tables, map a logical name to the table name:

~~~java
Map<String, String> allowedTables = Map.of(
    "current", "orders",
    "archive", "orders_archive"
);

String tableName = allowedTables.get(requestedDataset);
if (tableName == null) {
    throw new IllegalArgumentException("Unsupported dataset");
}

String sql =
    "SELECT order_id, status, created_at FROM " + tableName +
    " WHERE customer_id = ?";

PreparedStatement statement = connection.prepareStatement(sql);
statement.setLong(1, customerId);
~~~

The table name is structural and therefore chosen from an allowlist. `customerId` remains data and is bound. If the two tables have different schemas or access permissions, the application must enforce appropriate authorization for each option.

## 6. Binding Values in SELECT Conditions

### 6.1. Equality Conditions

~~~sql
SELECT order_id, total
FROM orders
WHERE customer_id = ?;
~~~

Binding the lookup key lets the same SQL statement run across different `customer_id` values.

### 6.2. Value Ranges

~~~sql
SELECT order_id, created_at, total
FROM orders
WHERE created_at >= ?
  AND created_at < ?
ORDER BY created_at;
~~~

Both time bounds are data. Pass proper temporal types from the application rather than manually formatting and concatenating SQL strings.

### 6.3. LIKE and Wildcards

You can bind a pattern for `LIKE`:

~~~sql
SELECT customer_id, full_name
FROM customers
WHERE full_name LIKE ?;
~~~

To search for a substring, the application can construct `%keyword%` and bind it as a single value:

~~~text
parameter = "%An%"
~~~

Binding prevents keyword content from becoming SQL syntax, though `%` and `_` still retain `LIKE` wildcard semantics. If the requirement is to match literal `%` or `_` characters, escape wildcards according to `LIKE` rules and declare a matching `ESCAPE` clause.

Example using `!` as the escape character:

~~~sql
SELECT customer_id, full_name
FROM customers
WHERE full_name LIKE ? ESCAPE '!';
~~~

The application must transform `!` to `!!`, `%` to `!%`, and `_` to `!_` before wrapping with search wildcards according to the chosen rules. This addresses pattern semantics, distinct from SQL injection defense.

### 6.4. NULL

To search for `NULL` values, use `IS NULL`:

~~~sql
SELECT order_id
FROM orders
WHERE shipped_at IS NULL;
~~~

Do not use `shipped_at = ?` and bind `NULL` when the goal is checking for `NULL`. Equality comparison with `NULL` evaluates to `UNKNOWN`; SQL requires `IS NULL` or `IS NOT NULL`.

If the filter is optional, the application can choose between two fixed SQL statements:

~~~sql
-- When not filtering by shipped_at
SELECT order_id
FROM orders;

-- When fetching only unshipped rows
SELECT order_id
FROM orders
WHERE shipped_at IS NULL;
~~~

Do not try to turn `NULL` into an identifier or operator through a placeholder.

## 7. IN Lists and Placeholder Counts

A single placeholder represents one value, not a multi-value list:

~~~sql
-- Does not mean a list is bound
SELECT order_id
FROM orders
WHERE status IN (?);
~~~

If you bind the string `'PAID,SHIPPED'`, MySQL treats it as a single value rather than splitting it into two elements.

When a list has variable length, the application generates the exact number of placeholders and binds each value individually. The placeholder count is derived from list length, while each element's content is bound:

~~~java
List<String> statuses = List.of("PAID", "SHIPPED");

String placeholders = String.join(
    ", ",
    Collections.nCopies(statuses.size(), "?")
);

String sql =
    "SELECT order_id, status FROM orders " +
    "WHERE status IN (" + placeholders + ")";

PreparedStatement statement = connection.prepareStatement(sql);
for (int i = 0; i < statuses.size(); i++) {
    statement.setString(i + 1, statuses.get(i));
}
~~~

Empty lists must be handled separately. Never emit `IN ()`; return an empty result in the application layer or use an always-false fixed query such as `WHERE 1 = 0`, depending on design.

For very large lists containing hundreds or thousands of elements, consider a temporary table, staging table, or a suitable set-passing mechanism instead of building a SQL statement with excessive markers.

## 8. LIMIT and OFFSET

`LIMIT` controls how many rows are returned:

~~~sql
SELECT order_id, status
FROM orders
ORDER BY created_at DESC
LIMIT ? OFFSET ?;
~~~

In MySQL prepared statements, markers can be used for `LIMIT`/`OFFSET` values. Drivers and APIs may impose specific data type rules; pass integers and check connector support.

Applications should validate:

- `page_size` is a positive integer.
- `page_size` does not exceed the maximum allowed limit.
- `offset` is non-negative and within business limits.

Parameter binding does not stop a user from requesting `LIMIT 2000000000`. It prevents the value from altering syntax; validation is still needed to control query cost.

Large `OFFSET`s can force MySQL to read and skip many rows before returning a page. On large tables, consider keyset pagination:

~~~sql
SELECT order_id, created_at, status
FROM orders
WHERE (created_at, order_id) < (?, ?)
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
~~~

Cursor values and page size are both data and are bound. Ensure an index aligns with the filter/sort order and use columns that form a deterministic order, such as `created_at` paired with the primary key.

## 9. Prepared Statements in MySQL

### 9.1. SQL PREPARE, EXECUTE, and DEALLOCATE

MySQL supports SQL-level prepared statements:

~~~sql
PREPARE find_orders FROM
    'SELECT order_id, status, total
     FROM orders
     WHERE customer_id = ?
       AND status = ?';

SET @customer_id = 42;
SET @status = 'PAID';

EXECUTE find_orders USING @customer_id, @status;

DEALLOCATE PREPARE find_orders;
~~~

Steps:

1. `PREPARE` parses and prepares the SQL statement with markers.
2. `SET` assigns values to user variables used during execution.
3. `EXECUTE` passes values matching the marker order.
4. `DEALLOCATE PREPARE` releases the named prepared statement.

User variables in this example are session variables prefixed with `@`. They differ from local variables inside stored procedures.

### 9.2. Prepared Statements in Drivers

In applications, use your driver's prepared statement API. The driver manages sending statements, data types, and bound values according to its supported protocol.

JDBC example:

~~~java
String sql = """
    SELECT order_id, status, total
    FROM orders
    WHERE customer_id = ?
      AND status = ?
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);
    statement.setString(2, status);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            String orderStatus = resultSet.getString("status");
            BigDecimal total = resultSet.getBigDecimal("total");
        }
    }
}
~~~

JDBC uses 1-based indexing. Typed setters like `setLong`, `setString`, `setBigDecimal`, and `setTimestamp` let the driver transmit values with appropriate types. Use try-with-resources to close statements and result sets.

Python example using `mysql-connector-python`:

~~~python
sql = """
    SELECT order_id, status, total
    FROM orders
    WHERE customer_id = %s
      AND status = %s
"""

cursor.execute(sql, (customer_id, status))
rows = cursor.fetchall()
~~~

This Python connector uses `%s` as the placeholder in its driver API; it is not MySQL's server-side SQL `PREPARE` marker syntax. Exact placeholders depend on the library. Always read connector documentation and pass parameters as a separate argument to `execute`; never interpolate `%s` yourself with string formatting.

### 9.3. Server-Side vs. Client-Side Prepared Statements

Some drivers support server-side prepared statements over the binary protocol; some modes emulate or prepare statements client-side. Details depend on the connector, configuration, and version.

Regardless of the underlying implementation mechanism, applications should still use the official parameter-binding API. Never concatenate strings or manually quote values to simulate binding. When you need to verify whether server-side preparation is active, check driver configuration and documentation or inspect prepared statement metrics on the server.

## 10. Parameter Data Types and Conversion

Binding parameters with matching types helps MySQL evaluate expressions cleanly:

| Application Value | Suggested Bind Method |
|---|---|
| BIGINT key | setLong in JDBC |
| INT | setInt |
| VARCHAR | setString |
| DECIMAL | setBigDecimal |
| DATE | setDate |
| DATETIME/TIMESTAMP | setTimestamp or driver-appropriate temporal type |
| Boolean | setBoolean if mapping matches schema |

MySQL can perform type conversion inside expressions. However, binding the string `'42'` for a numeric column may force server-side conversion; passing a properly typed integer is cleaner.

Especially for dates and times, understand driver and session timezone behavior. JDBC `Timestamp` can be affected by JVM/Calendar timezones and driver settings; if storing `TIMESTAMP` or `DATETIME` in UTC, keep conversion policies consistent across both the application and the session.

For `DECIMAL`, use an exact decimal type in the application such as `BigDecimal` instead of `double` when handling currency. Proper binding does not substitute for choosing appropriate column precision and scale.

## 11. Safe Dynamic SQL for Multiple Filter Conditions

Not all dynamic queries are dangerous. The risk lies in the origin of the concatenated SQL fragments.

A safe implementation builds the statement from fixed, program-defined structural fragments while binding all values:

~~~java
StringBuilder sql = new StringBuilder(
    "SELECT order_id, customer_id, status, total " +
    "FROM orders WHERE 1 = 1"
);

List<Object> parameters = new ArrayList<>();

if (customerId != null) {
    sql.append(" AND customer_id = ?");
    parameters.add(customerId);
}

if (status != null) {
    sql.append(" AND status = ?");
    parameters.add(status);
}

if (createdAfter != null) {
    sql.append(" AND created_at >= ?");
    parameters.add(createdAfter);
}
~~~

The `AND ... = ?` fragments are hardcoded in source code; runtime logic only decides which fragments to append. Corresponding values are collected in `parameters`. When creating the `PreparedStatement`, the application binds each value in the order appended.

Never concatenate user content directly into `sql.append(...)`. When choosing columns, tables, or sort directions, use an allowlist as shown earlier.

## 12. Dynamic SQL in Stored Procedures

Stored procedures can use dynamic SQL with `PREPARE`. The following example allows selecting one of two sort columns:

~~~sql
DELIMITER //

CREATE PROCEDURE list_orders(
    IN p_customer_id BIGINT,
    IN p_sort_key VARCHAR(20),
    IN p_sort_direction VARCHAR(4)
)
BEGIN
    DECLARE v_order_clause VARCHAR(80);
    DECLARE v_sql TEXT;

    IF p_sort_key = 'created' THEN
        SET v_order_clause = 'created_at';
    ELSEIF p_sort_key = 'total' THEN
        SET v_order_clause = 'total';
    ELSE
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Unsupported sort field';
    END IF;

    IF UPPER(p_sort_direction) = 'ASC' THEN
        SET v_order_clause = CONCAT(v_order_clause, ' ASC');
    ELSEIF UPPER(p_sort_direction) = 'DESC' THEN
        SET v_order_clause = CONCAT(v_order_clause, ' DESC');
    ELSE
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Unsupported sort direction';
    END IF;

    SET v_sql = CONCAT(
        'SELECT order_id, customer_id, status, total, created_at ',
        'FROM orders WHERE customer_id = ? ORDER BY ',
        v_order_clause
    );

    SET @sql = v_sql;
    SET @bound_customer_id = p_customer_id;
    PREPARE order_stmt FROM @sql;
    EXECUTE order_stmt USING @bound_customer_id;
    DEALLOCATE PREPARE order_stmt;
END//

DELIMITER ;
~~~

This example illustrates key principles:

- `p_customer_id` is a data value and is bound using a marker.
- `p_sort_key` is mapped to a fixed identifier.
- `p_sort_direction` is validated and accepts only `ASC` or `DESC`.
- Caller input is never concatenated verbatim into SQL.

In stored programs, `PREPARE` accepts the statement from a string literal or user variable; therefore the example copies the local variable `v_sql` into the user variable `@sql` before calling `PREPARE`. `EXECUTE USING` also requires user variables rather than routine local variables directly. Prepared statements created inside a stored procedure should be deallocated after use. SQL prepared statements cannot be used this way inside stored functions or triggers.

If a procedure can exit early due to an error after `PREPARE`, design a handler to ensure the statement is properly deallocated. The example above focuses on binding and allowlists; production code should add project-standard error handling.

## 13. Identifier Quoting and Its Limitations

MySQL quotes identifiers with backticks:

~~~sql
SELECT order_id
FROM shop.orders;
~~~

If an identifier contains a backtick, double the internal backtick when quoting. However, do not write a simple identifier-quoting helper and apply it to arbitrary user input.

Correct workflow:

1. Define which objects the feature is permitted to select.
2. Map the logical choice to an application-defined identifier.
3. Quote the identifier according to MySQL syntax if needed.
4. Assemble the controlled identifier into SQL.
5. Bind all remaining data values.

Quoting only protects how the parser recognizes identifier boundaries. It does not replace allowlists, authorization, or schema checks.

## 14. Common Design Mistakes

### 14.1. Placing Placeholders Inside Quotes

Wrong:

~~~sql
SELECT order_id
FROM orders
WHERE status = '?';
~~~

Here the question mark sits inside a string literal, so it is not a parameter marker. Placeholders must appear in expression positions:

~~~sql
SELECT order_id
FROM orders
WHERE status = ?;
~~~

Never add quotes around a placeholder yourself. The driver transmits the value according to the protocol and data type.

### 14.2. Binding a Column Name Expecting MySQL to Treat It as an Identifier

Wrong for the goal:

~~~sql
SELECT ?
FROM orders;
~~~

If you bind `'total'`, the output is a string literal expression, not the `total` column. Select the identifier from an allowlist and assemble it into the SQL structure.

### 14.3. Binding an Entire ORDER BY Clause

Wrong:

~~~sql
SELECT order_id, total
FROM orders
ORDER BY ?;
~~~

The marker here is a value expression. It cannot substitute for `total DESC`. Choose the column and sort direction via an allowlist.

### 14.4. Binding a List via a Single Parameter

Semantically wrong:

~~~sql
SELECT order_id
FROM orders
WHERE status IN (?);
~~~

Binding `'PAID,SHIPPED'` does not produce two list items. Generate one marker per element and bind each value individually.

### 14.5. Concatenating Strings and Manually Escaping

Manually replacing quotes or stripping special characters is error-prone across varying character sets, SQL modes, and literal contexts. Use prepared statements for values; use allowlists for structure.

### 14.6. Thinking Parameter Binding Replaces Authorization

A properly bound query can still let a user read another customer's orders if the application skips permission checks. Include tenant, owner, or access-scope conditions in query logic and test authorization separately.

## 15. Checklist for Building Safe SELECT Queries

Before shipping a query in an application, verify:

1. Is the SQL statement structure as fixed as possible?
2. Are all data values passed via the parameter-binding API?
3. Are any placeholders placed inside quotes or used in place of identifiers?
4. Are table/column names, sort directions, and dynamic syntax fragments selected from an allowlist?
5. Do `IN` lists match placeholder count to value count and handle empty lists?
6. Are `LIKE` wildcards handled properly for literal vs. pattern search requirements?
7. Is `NULL` checked with `IS NULL`/`IS NOT NULL` where needed?
8. Are `LIMIT`/`OFFSET` validated to prevent oversized queries?
9. Are bind types compatible with column types?
10. Does the application enforce authorization and tenant/owner boundaries?
11. Are statements, result sets, and connections properly lifecycle-managed?
12. Have inputs containing quotes, comment markers, Unicode characters, and SQL injection payloads been tested?

## 16. Comprehensive Example: Searching Orders with Filters and Sorting

Requirement: search orders by customer, with optional status filtering, selectable sorting, and pagination.

Structural selection:

~~~java
Map<String, String> sortColumns = Map.of(
    "created", "created_at",
    "total", "total"
);

String orderBy = sortColumns.get(sortKey);
if (orderBy == null) {
    throw new IllegalArgumentException("Invalid sort key");
}

String direction;
if ("asc".equalsIgnoreCase(sortDirection)) {
    direction = "ASC";
} else if ("desc".equalsIgnoreCase(sortDirection)) {
    direction = "DESC";
} else {
    throw new IllegalArgumentException("Invalid sort direction");
}
~~~

Building the statement and binding values:

~~~java
StringBuilder sql = new StringBuilder(
    "SELECT order_id, customer_id, status, total, created_at " +
    "FROM orders WHERE customer_id = ?"
);

List<Object> values = new ArrayList<>();
values.add(customerId);

if (status != null) {
    sql.append(" AND status = ?");
    values.add(status);
}

sql.append(" ORDER BY ")
   .append(orderBy)
   .append(" ")
   .append(direction)
   .append(", order_id DESC LIMIT ?");

values.add(pageSize);

try (PreparedStatement statement = connection.prepareStatement(sql.toString())) {
    for (int i = 0; i < values.size(); i++) {
        Object value = values.get(i);
        if (value instanceof Long) {
            statement.setLong(i + 1, (Long) value);
        } else if (value instanceof String) {
            statement.setString(i + 1, (String) value);
        } else if (value instanceof Integer) {
            statement.setInt(i + 1, (Integer) value);
        }
    }

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            // Map result rows to application objects.
        }
    }
}
~~~

In production code, use strongly typed data-access classes or helpers rather than a generic `Object` list and `instanceof` chain. The example illustrates parameter order: `customerId`, `status` if present, then `pageSize`. Validate `pageSize` before binding.

Key points to remember:

- `customerId`, `status`, and `pageSize` are bound data.
- `orderBy` and `direction` are allowlisted structure.
- The table name is fixed in SQL.
- No user input is concatenated directly into uncontrolled SQL fragments.

## Conclusion

Bind parameters are for data values in SQL statements: IDs, search strings, dates/times, amounts, and pagination limits. Placeholders cannot replace table names, column names, keywords, or arbitrary SQL syntax fragments. When dynamic SQL is required, pick structural pieces from an allowlist, quote identifiers properly, and bind all remaining values.

Combining prepared statements, allowlists, type checking, and authorization keeps `SELECT` queries safe from SQL injection and easy to maintain. Always separate user-supplied data from application-permitted structural choices; this is the most critical boundary when building dynamic queries in MySQL.
