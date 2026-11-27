# SQL Injection, Prepared Statements, and Controlling Dynamic Identifiers

SQL injection happens when input data alters the structure of a SQL statement. In MySQL, the core defense is separating the statement from data values using prepared statements. When an application needs to vary a table name, column name, or sort direction, it must select those SQL fragments from an allow-list defined in source code; placeholders cannot substitute for SQL identifiers or keywords.

This lesson belongs to the **Security** chapter of the `DATABASE_MYSQL` module. It focuses on building safe queries in applications using MySQL, especially in commonly overlooked areas such as dynamic sorting, list filtering, and dynamic SQL inside stored procedures.

In the DATABASE_MYSQL module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control, while also practicing reading execution plans, query optimization, privilege management, backups, and handling relational database operational issues. This lesson focuses on the query-security aspect of that path: keeping input data separate from SQL syntax and constraining dynamic identifiers.

## 1. How Does SQL Injection Happen?

A SQL statement has both **structure** and **values**. Structure consists of keywords, table names, column names, operators, and clauses. Values are data such as emails, customer IDs, or creation dates. Injection flaws occur when an application concatenates untrusted data directly into the structural part.

The following example is unsafe:

~~~js
const email = req.query.email;
const sql =
  "SELECT id, email FROM users WHERE email = '" + email + "'";
const [rows] = await pool.query(sql);
~~~

If a user supplies a value containing a single quote, an `OR 1=1` expression, and a SQL comment marker, the concatenated string can become:

~~~sql
SELECT id, email
FROM users
WHERE email = '' OR 1=1 -- ';
~~~

The `OR 1=1` condition causes the query to return more rows than intended. Depending on where the string was concatenated and the privileges of the database connection account, an attacker may read out-of-scope data, modify or delete data, or affect additional statements.

Common attack forms include:

- **In-band injection:** query results or SQL errors are returned directly to the application.
- **UNION-based injection:** attempts to append results from another query onto the current result set.
- **Blind injection:** infers data through differences in responses, status codes, or timing.
- **Second-order injection:** malicious data is stored first, then triggers injection later when another workflow concatenates that stored data into SQL.

Data already stored in the database should not be treated as trusted. It may have originated from an external request or another system.

## 2. Use Prepared Statements for All Data Values

Prepared statements keep the SQL structure fixed and pass values via separate parameters. MySQL treats parameters strictly as data, so quotes, semicolons, or SQL-like strings inside a parameter cannot turn into new operators or clauses.

With the **mysql2** library for Node.js, use **execute()** to run a prepared statement:

~~~js
const email = req.query.email;

const sql =
  "SELECT id, email FROM users WHERE email = ?";

const [rows] = await pool.execute(sql, [email]);
~~~

The **?** marker is a placeholder for a **value**. The order of elements in the array must match the order of placeholders in the SQL statement. Even if the input contains single quotes, `OR 1=1`, and SQL comment markers, MySQL searches for an email matching that literal value rather than interpreting it as a new condition.

A query with multiple parameters:

~~~js
const sql =
  "SELECT id, status, created_at " +
  "FROM orders " +
  "WHERE customer_id = ? " +
  "AND status = ? " +
  "AND created_at >= ? " +
  "ORDER BY created_at DESC " +
  "LIMIT ? OFFSET ?";

const [orders] = await pool.execute(sql, [
  customerId,
  status,
  fromDate,
  limit,
  offset
]);
~~~

In this example, all parameters are data values. The application must still validate types and domains: `customerId` must be a valid customer ID, `status` must belong to the supported status set, and `limit` and `offset` must be integers within permitted bounds.

### Limitations to Remember

A placeholder does not represent an arbitrary SQL fragment. The following patterns do not substitute for column names or table names:

~~~sql
-- Cannot select a column by passing a value into a placeholder
SELECT id, email FROM users ORDER BY ?;

-- Cannot select a table using a placeholder
SELECT id FROM ? WHERE id = ?;
~~~

In the first statement, MySQL sorts by the constant parameter value rather than treating the parameter as a column name. In the second statement, a placeholder cannot become a table name. Likewise, you cannot bind `ASC`, `DESC`, operators, or partial SQL clauses directly.

Also do not wrap quotes around a placeholder:

~~~sql
-- Wrong: ? is inside a string literal
SELECT id FROM users WHERE email = '?';

-- Correct
SELECT id FROM users WHERE email = ?;
~~~

Do not write your own escaping function and concatenate strings in place of prepared statements. Manual escaping is error-prone across different character sets, data types, and SQL contexts.

## 3. Controlling Dynamic Column Names, Table Names, and Sort Directions

A listing screen often lets users pick a sort column or ascending/descending order. This requires constructing part of the SQL statement dynamically. Because placeholders cannot be used for identifiers, the application must map external choices to developer-controlled SQL constants.

Safe example with mysql2:

~~~js
const sortColumns = Object.freeze({
  createdAt: "created_at",
  total: "total_amount",
  status: "status"
});

const sortKey = req.query.sortBy;
if (!Object.hasOwn(sortColumns, sortKey)) {
  throw new Error("Unsupported sort column");
}
const sortColumn = sortColumns[sortKey];

const sortDirections = Object.freeze({
  asc: "ASC",
  desc: "DESC"
});

const directionKey = req.query.direction;
if (!Object.hasOwn(sortDirections, directionKey)) {
  throw new Error("Invalid sort direction");
}
const sortDirection = sortDirections[directionKey];

const limit = Number(req.query.limit);
const offset = Number(req.query.offset);

if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) {
  throw new Error("limit must be between 1 and 100");
}
if (!Number.isSafeInteger(offset) || offset < 0) {
  throw new Error("offset must be a non-negative integer");
}

const sql =
  "SELECT id, status, total_amount, created_at " +
  "FROM orders ORDER BY " + sortColumn + " " + sortDirection +
  " LIMIT ? OFFSET ?";

const [rows] = await pool.execute(sql, [limit, offset]);
~~~

There are two distinct handling paths:

1. `sortBy` and `direction` are mapped strictly to constant strings predefined in source code. Unknown values are rejected.
2. `limit` and `offset` are data values, so they are bound via placeholders while also validated against allowed bounds.

The column names in the map are constants defined by the application. If an identifier needs quoting, place the fixed quoting syntax directly inside the map values. Quoting does not replace an allow-list: only predefined names may enter the SQL statement.

Apply the same rule to table names. For instance, if an API accepts a resource type of `orders` or `invoices`, map those two choices to two fixed table names. Never concatenate `req.params.table`, `req.query.table`, or any user-supplied string directly into a query.

**Decision rule:** if an input piece determines *SQL structure*, map it through an allow-list. If it is a *value being compared, inserted, or updated*, pass it via a placeholder.

## 4. Dynamic SQL in MySQL Stored Procedures

Stored procedures occasionally need to choose a table based on a business entity kind. MySQL does not allow binding a table name into a prepared statement placeholder. Dynamic SQL can be built by picking the table name from an allow-list and then binding filter values normally.

Illustrative example:

~~~sql
DELIMITER //

CREATE PROCEDURE read_entity(
  IN p_kind VARCHAR(20),
  IN p_owner_id BIGINT
)
BEGIN
  DECLARE v_table VARCHAR(64);

  SET v_table = CASE p_kind
    WHEN 'orders' THEN 'orders'
    WHEN 'invoices' THEN 'invoices'
    ELSE NULL
  END;

  IF v_table IS NULL THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Unsupported entity';
  END IF;

  SET @sql = CONCAT(
    'SELECT id, status FROM ',
    v_table,
    ' WHERE owner_id = ?'
  );
  SET @bound_owner_id = p_owner_id;

  PREPARE entity_stmt FROM @sql;
  EXECUTE entity_stmt USING @bound_owner_id;
  DEALLOCATE PREPARE entity_stmt;
END//

DELIMITER ;
~~~

Here, `p_kind` is used only to select one of two fixed table names. Invalid values are rejected. `p_owner_id` is passed through a placeholder and therefore cannot alter the statement structure.

In MySQL, `PREPARE` takes a SQL string or user variable; `EXECUTE ... USING` takes user variables as parameters. Prepared statements are connection-session scoped, so release them with `DEALLOCATE PREPARE` after execution. In real deployments, name statements and user variables according to application conventions to avoid collisions within the same session.

Never pass a parameter-supplied table name directly into `CONCAT()`. When business requirements add a new table, explicitly update the allow-list and verify the database account's privileges.

## 5. Common Query Scenarios

### Filtering a List with IN

You cannot pass an entire array as a single placeholder for an `IN` clause. Generate the exact number of placeholders matching the element count while still binding each individual value:

~~~js
const ids = input.ids;

if (!Array.isArray(ids) || ids.length > 100) {
  throw new Error("Invalid ID list");
}

if (ids.length === 0) {
  return [];
}

if (!ids.every((id) => Number.isSafeInteger(id) && id > 0)) {
  throw new Error("List contains an invalid ID");
}

const placeholders = ids.map(() => "?").join(", ");
const sql = "SELECT id, status FROM orders WHERE id IN (" +
  placeholders + ")";

const [rows] = await pool.execute(sql, ids);
~~~

Only the count of placeholders is generated dynamically; each ID value is still bound. Cap the array size to prevent overly large queries and define explicit behavior for empty lists.

### Searching with LIKE

Prepared statements still prevent injection when using `LIKE`:

~~~js
const sql = "SELECT id, name FROM products WHERE name LIKE ?";
const [rows] = await pool.execute(sql, ["%" + keyword + "%"]);
~~~

The `%` and `_` characters act as wildcards in `LIKE`. If the business requirement is to match literal substrings, the application must escape wildcards according to MySQL rules and declare the corresponding `ESCAPE` clause. That is a search-semantics concern; it is separate from SQL injection.

### Updating Data

Bind both the new values and record keys:

~~~js
const sql =
  "UPDATE orders SET status = ? " +
  "WHERE id = ? AND customer_id = ?";

const [result] = await pool.execute(sql, [
  newStatus,
  orderId,
  customerId
]);
~~~

Beyond input validation, the `customer_id` condition scopes the record by owner inside the query itself. Do not rely solely on the UI hiding other users' records.

## 6. Implementation Mistakes to Avoid

| Practice | Problem | How to Fix |
|---|---|---|
| Concatenating input into SQL strings | Input can alter syntax | Bind values with prepared statements |
| Using `ORDER BY ?` to select a column | Placeholder is a value, not an identifier | Map column names via an allow-list |
| Concatenating table names directly from requests | Users control query structure | Use a fixed table-name map |
| Manual escaping plus string concatenation | Error-prone across charsets and contexts | Use placeholders for values |
| Only disabling multi-statements | Does not stop single-statement injection techniques | Fix how queries are constructed |
| Returning raw MySQL errors to clients | Can leak table names, columns, and internal structure | Return generic errors; record details in controlled internal logs |

Disabling `multipleStatements` in driver configuration is a useful mitigation layer if the application does not need to run multiple statements in one call. However, it does not replace prepared statements and allow-lists.

## 7. Defense in Depth

Prepared statements are the primary measure for separating data from SQL syntax. Combine them with the following practices:

- **Business-level input validation:** validate type, length, value range, and format before querying. Validation ensures data makes business sense; parameterization is the mechanism preventing values from becoming SQL syntax.
- **Least privilege:** application accounts should hold only the privileges needed on the schemas and tables the feature uses. Never use administrative accounts like `root` for application connections.
- **Data-scope enforcement:** include tenant, owner, or access-scope conditions in the query itself and enforce authorization at the business layer.
- **Error and log management:** never expose SQL, stack traces, or connection details to users. Logs should capture enough detail for investigation while protecting sensitive data and credentials.
- **Audit every SQL construction point:** inspect reads, writes, reports, search, exports, stored procedures, and background jobs. Dynamic SQL can live outside the main HTTP request path.

Do not assume an ORM automatically protects every query. Raw query helpers, hand-written SQL expressions, and dynamic sorting still must obey the same rules.

## 8. How to Test Query Safety

You can test the following cases in a test environment:

1. Submit values containing quotes, hyphens, semicolons, and SQL-like condition strings into search fields. The application must treat them as literal data; row counts and scope must not change outside search logic.
2. Submit `sortBy` with valid column names, nonexistent column names, and strings containing SQL characters. Only options in the allow-list should be accepted.
3. Submit `direction` with `asc`, `desc`, and arbitrary strings. Only the two supported choices should map to SQL keywords.
4. Test `limit` and `offset` with negative numbers, decimals, strings, oversized numbers, and empty values.
5. Test `IN` lists when empty, with one element, multiple elements, and exceeding the size limit.
6. Verify the application account cannot read or modify tables outside its granted privileges.

When reviewing source code, search for string concatenation into `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `ORDER BY`, `GROUP BY`, and dynamic SQL statements. At each spot, identify clearly which parts are constants, which are allow-listed identifiers, and which are bound values.

## 9. Key Takeaways

| Query Component | How to Handle |
|---|---|
| Email, customer ID, dates, status | Prepared statement / placeholder |
| Values in `LIMIT`, `OFFSET` | Placeholder plus domain validation |
| List for `IN` | Generate placeholder count matching list size, bind each value |
| Table names, column names | Allow-list mapped to SQL constants |
| `ASC`, `DESC`, operators, keywords | Select from a fixed choice set |
| `LIKE` search strings | Bind value; handle wildcards per business requirements |

When designing a MySQL query, classify every input before assembling the SQL statement: data is bound, and every choice affecting query structure must be controlled by an allow-list. This separation prevents SQL injection right where statements are constructed and makes query behavior easier to audit.
