# Role of Stored Procedures/Functions and Boundaries with Java Code

MySQL stored programs are SQL code stored in the database and executed on the server. The two commonly used routine types are **stored procedure** and **stored function**. A procedure is invoked with `CALL`, can accept `IN`, `OUT`, and `INOUT` parameters, and can return result sets. A function returns a scalar value and can be called inside SQL expressions like a built-in function.

Stored routines are suitable when a piece of logic is tightly coupled to the data and needs to be used consistently across multiple clients. Java should still retain the role of orchestrating use cases, validating application-level business rules, calling external services, managing APIs, and connecting components. Moving all logic into the database increases coupling to MySQL, makes independent testing/deployment harder, and can create CPU or concurrency bottlenecks on the database. Conversely, letting Java perform a series of discrete read-modify-write steps on its own can increase round-trips and weaken consistency if transaction boundaries are not designed properly.

The goal is to choose the right boundary: place data operations that need to stay close to the database into routines when the benefit is clear; keep orchestration and database-independent logic in Java; and clearly define which side owns the transaction.

## 1. What is a stored program?

A stored program is a program stored in a MySQL schema rather than residing entirely in application source code. MySQL supports several types of stored programs, such as:

- **Stored procedure:** a routine invoked with `CALL`; it can accept multiple parameters, execute multiple statements, and return one or more result sets.
- **Stored function:** a routine that returns a single value and can appear in SQL expressions, such as in `SELECT`, `WHERE`, or computed expressions.
- **Trigger:** a routine automatically activated when a DML event occurs on a table.
- **Event:** a task executed on a schedule by the MySQL Event Scheduler.

This lesson focuses on procedures/functions and how to divide responsibilities with Java. Triggers and events have their own activation mechanisms, lifecycles, and operational risks; they should not be used merely to replace an application call without clearly defined requirements.

Stored routines are stored as metadata in the database. When an application calls a routine, MySQL executes the routine body on the server using the current connection/session and privileges according to the routine's `SQL SECURITY`.

## 2. How do stored procedures and stored functions differ?

| Criterion | Stored procedure | Stored function |
| --- | --- | --- |
| How it is called | `CALL procedure_name(...)` | Used like an SQL expression, e.g. `SELECT function_name(...)` |
| Return value | Can return result sets, `OUT`/`INOUT` parameters, or multiple results | Must return a single value via `RETURN` |
| Parameters | `IN`, `OUT`, `INOUT` | Input parameters (`IN`) only |
| Typical purpose | Perform an action or data workflow | Compute a scalar value |
| Use in `SELECT`/`WHERE` | Cannot place a procedure directly as an expression | Can call a function inside SQL expressions |
| Transaction control | Can contain transaction control statements, but must coordinate clearly with the caller's transaction | Cannot use statements that start/end a transaction such as `START TRANSACTION`, `COMMIT`, `ROLLBACK` |
| Result set | Can return result sets directly | Cannot return result sets directly |
| Dynamic SQL | Stored procedures can use dynamic prepared statements within supported limits | Stored functions cannot use dynamic prepared statements |

Procedures suit multi-step actions or returning a set of rows. Functions suit computations that return a single value with clear semantics. Do not choose a function just for shorter call syntax; a function called in SQL can run multiple times per row and incur high cost.

## 3. When should you consider a stored procedure?

A procedure can be useful when:

1. A data operation consists of multiple SQL statements that need to execute close to the database.
2. Multiple applications or services need to share a standardized data workflow.
3. You want to grant `EXECUTE` privilege on the routine without granting broad direct privileges on the underlying tables.
4. You need to return multiple rows or multiple result sets to the caller.
5. You want to combine several round-trips into a single database call.
6. The workflow can be expressed clearly in SQL and does not need to call external services during processing.

For example, a procedure can accept `customer_id`, check data conditions, record a request, and return result information. If the workflow needs to send an email, call a payment gateway, or make an HTTP call, those actions still belong to orchestration in Java or a separate worker.

A procedure is not automatically faster than Java. If the procedure performs the same number of reads/writes and uses the same execution plan, the database cost still exists. Benefits may come from reducing round-trips, reducing intermediate data transfer, or performing set-based operations close to the data.

## 4. When should you consider a stored function?

A function is suitable for a scalar calculation with clear inputs/outputs, for example:

- Normalizing or computing a value from parameters.
- Computing a small, stable business expression reused across SQL queries.
- Returning a simple aggregated value when calling it inside an expression is genuinely convenient.
- Encapsulating an SQL calculation so multiple queries share the same definition.

Example function that calculates the total amount of an order:

```sql
DELIMITER //

CREATE FUNCTION fn_order_total(p_order_id BIGINT UNSIGNED)
RETURNS DECIMAL(13, 2)
READS SQL DATA
SQL SECURITY INVOKER
BEGIN
    DECLARE v_total DECIMAL(13, 2);

    SELECT COALESCE(SUM(oi.quantity * oi.unit_price), 0.00)
    INTO v_total
    FROM order_items AS oi
    WHERE oi.order_id = p_order_id;

    RETURN v_total;
END//

DELIMITER ;
```

Calling the function:

```sql
SELECT fn_order_total(1001) AS order_total;
```

The function returns a `DECIMAL` value, so it can be used inside SQL expressions. If you need to return multiple columns or multiple rows, use a procedure or a regular `SELECT` query.

## 5. Example schema used in this lesson

Subsequent examples use an orders table and an order items table:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_created (customer_id, created_at)
) ENGINE=InnoDB;

CREATE TABLE order_items (
    order_item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(13, 2) NOT NULL,
    PRIMARY KEY (order_item_id),
    KEY idx_order_items_order (order_id),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id) REFERENCES orders (order_id)
) ENGINE=InnoDB;
```

In a real system, tables may include additional constraints, currency, discount, tax, and rounding rules. This example only illustrates routine call boundaries.

SQL blocks with `BEGIN ... END` usually contain semicolons inside. When entering them in the MySQL command-line client, use the client command `DELIMITER` to temporarily change the statement terminator, such as `//`, then restore `DELIMITER ;` after creating the routine. `DELIMITER` is not an SQL statement sent to the server; when creating routines via JDBC or a migration framework, send the `CREATE PROCEDURE`/`CREATE FUNCTION` statement in the way that tool expects, without sending `DELIMITER` lines.

## 6. Procedure with IN parameters

`IN` is an input parameter. The procedure can read this value, but changes to the variable are not returned to the caller:

```sql
DELIMITER //

CREATE PROCEDURE sp_get_customer_orders(
    IN p_customer_id BIGINT UNSIGNED,
    IN p_limit INT
)
BEGIN
    SELECT
        order_id,
        status,
        created_at
    FROM orders
    WHERE customer_id = p_customer_id
    ORDER BY created_at DESC, order_id DESC
    LIMIT p_limit;
END//

DELIMITER ;
```

Call:

```sql
CALL sp_get_customer_orders(42, 20);
```

The procedure returns a result set containing order rows. The caller must read and close the result set before reusing the connection.

## 7. Procedure with OUT and INOUT parameters

`OUT` is used to return a value to the caller. Inside the procedure body, the parameter is assigned a value; the input value of the variable passed in is not used as an initial value.

```sql
DELIMITER //

CREATE PROCEDURE sp_count_customer_orders(
    IN p_customer_id BIGINT UNSIGNED,
    OUT p_order_count BIGINT
)
BEGIN
    SELECT COUNT(*)
    INTO p_order_count
    FROM orders
    WHERE customer_id = p_customer_id;
END//

DELIMITER ;
```

Calling in an SQL client:

```sql
CALL sp_count_customer_orders(42, @order_count);
SELECT @order_count AS order_count;
```

`INOUT` both receives an initial value and returns the modified value:

```sql
DELIMITER //

CREATE PROCEDURE sp_add_tax(
    INOUT p_amount DECIMAL(13, 2),
    IN p_tax_rate DECIMAL(7, 4)
)
BEGIN
    SET p_amount = ROUND(p_amount * (1 + p_tax_rate), 2);
END//

DELIMITER ;
```

```sql
SET @amount = 100.00;
CALL sp_add_tax(@amount, 0.1000);
SELECT @amount AS amount_with_tax;
```

The `@amount` variable is a user-defined session variable of the current connection. In an application, the driver supports registering OUT/INOUT parameters to receive results with explicit data types.

## 8. Local variables and scope in routines

Local variables are declared with `DECLARE` inside a `BEGIN ... END` block. Declarations must appear at the top of the block, before regular executable statements:

```sql
DELIMITER //

CREATE PROCEDURE sp_order_summary(
    IN p_order_id BIGINT UNSIGNED,
    OUT p_item_count BIGINT,
    OUT p_total DECIMAL(13, 2)
)
BEGIN
    SELECT
        COUNT(*),
        COALESCE(SUM(quantity * unit_price), 0.00)
    INTO p_item_count, p_total
    FROM order_items
    WHERE order_id = p_order_id;
END//

DELIMITER ;
```

`v_status` exists only within the routine block. Variable names should use a consistent prefix to distinguish parameters (`p_`), local variables (`v_`), and table columns. This avoids ambiguity when a parameter name matches a column name in an SQL condition.

## 9. Function returning a single value

A function must declare its return type with `RETURNS` and end with `RETURN` on every reachable execution branch:

```sql
DELIMITER //

CREATE FUNCTION fn_line_total(
    p_quantity INT,
    p_unit_price DECIMAL(13, 2)
)
RETURNS DECIMAL(13, 2)
DETERMINISTIC
NO SQL
BEGIN
    RETURN ROUND(p_quantity * p_unit_price, 2);
END//

DELIMITER ;
```

Call:

```sql
SELECT fn_line_total(3, 12500.00) AS line_total;
```

`DETERMINISTIC` declares that the same inputs always produce the same result; `NO SQL` declares that the routine does not read or write SQL data. These are characteristics declared by the author and must match the actual body. Do not mark a function `DETERMINISTIC` if it depends on table data, the current time, session state, or other changing sources.

## 10. SQL DATA ACCESS characteristics

A routine can declare its SQL access level:

| Characteristic | Declared meaning |
| --- | --- |
| `NO SQL` | Routine contains no SQL statements that access data |
| `CONTAINS SQL` | Contains SQL statements, but neither reads nor writes data |
| `READS SQL DATA` | May read SQL data |
| `MODIFIES SQL DATA` | May modify SQL data |

For example, a pure calculation function can declare `NO SQL`; a function reading a total table can declare `READS SQL DATA`; a procedure writing orders can declare `MODIFIES SQL DATA`.

These characteristics describe the behavior committed to by the routine. MySQL does not analyze the entire routine body to guarantee the declaration is always accurate. Misdeclaring them misleads operators and tools that rely on routine metadata.

## 11. Using functions in SELECT can incur per-row cost

A function can appear in a query expression:

```sql
SELECT
    o.order_id,
    fn_order_total(o.order_id) AS order_total
FROM orders AS o
WHERE o.customer_id = 42;
```

If the query returns 10,000 orders, the function may be called once for each row. If the function runs a `SELECT` inside to compute the item total, the application can inadvertently create a database-side N+1 pattern: one outer query plus many internal function queries.

For multi-row reports, a set-based query is usually more appropriate:

```sql
SELECT
    o.order_id,
    COALESCE(SUM(oi.quantity * oi.unit_price), 0.00) AS order_total
FROM orders AS o
LEFT JOIN order_items AS oi
  ON oi.order_id = o.order_id
WHERE o.customer_id = 42
GROUP BY o.order_id;
```

A function can be convenient for a single value or a small expression. When processing large datasets, measure the invocation count, actual rows, and execution plan; never assume a routine stored in the database is faster than a JOIN/aggregate.

## 12. Why procedures and functions are not interchangeable

A procedure is designed for an action or workflow; a function is designed to return a single value in an expression. You cannot call a procedure directly in `SELECT` like a function:

```sql
-- Valid if fn_line_total has been created:
SELECT fn_line_total(2, 100.00);

-- Invalid: a procedure is not an SQL expression:
-- SELECT sp_count_customer_orders(42);
```

A procedure can return result sets and multiple OUT parameters. A function returns one value and cannot return a result set directly. If you need to return multiple columns or rows, consider a procedure or writing a direct SELECT.

Do not create a function solely to wrap a simple query that the caller could write clearly. A routine has value when it establishes a shared contract, reduces duplicated logic, or provides controlled access privileges.

## 13. Boundary of responsibilities: MySQL routines and Java

A commonly sensible division of responsibilities:

| Responsibility | Typical suitable place | Reason |
| --- | --- | --- |
| HTTP/API, user authentication and authorization | Java/service | Tied to protocol, identity, and application policy |
| Multi-service orchestration, message broker, email, payment | Java/service or worker | MySQL routines should not make external network calls or hold transactions waiting for responses |
| Multi-step business rules directly involving data in the same database | Java transaction or procedure, depending on architecture | Need to choose one clear owner for flow and transaction |
| Set-based queries, aggregates, large JOINs | Direct SQL or routine | Database optimizes operations close to data |
| Small, stable scalar calculations needed in SQL | Function or SQL expression | Can be reused with the same semantics |
| Complex, frequently changing domain rules | Java domain/service layer | Easy to unit test, review, deploy, and observe at the application level |
| Basic data integrity rules | Schema constraints | Enforced for every client, independent of caller |
| Logging, tracing, retry policy, and orchestration | Java/platform | Requires request context and application observability |

This is a selection guideline, not a rigid rule. A system with multiple clients writing directly to the database may need more centralized logic in stored procedures. A system with a single Java service managing the schema can keep most orchestration in Java and use SQL only for reading/writing data.

## 14. Avoiding unnecessary round-trips for a single use case

Suppose a use case needs to read an order's status, validate a condition, and update the status. If Java executes multiple sequential SQL statements, each statement may incur a round-trip:

```text
Java -> SELECT order
Java -> validate
Java -> UPDATE order
Java -> INSERT audit row
```

If the steps require the same data state, Java must hold the same connection and transaction throughout the process. A procedure can combine the SQL steps into a single call, reducing round-trips and centralizing update rules.

However, if Java needs to call an external service between steps, you should not move the entire flow into a procedure. Define the atomic database portion, commit it, and emit an outbox/event for a worker to handle side effects.

Do not optimize round-trips by creating a huge procedure without clear boundaries. A routine needs well-defined inputs/outputs, error handling, and a stable contract.

## 15. Who owns the transaction: Java or the procedure?

An important rule: **a single unit of business work should have one clear transaction owner**.

There are two common models:

### 15.1. Java owns the transaction

Java acquires a connection, starts a transaction, and calls the procedure to execute DML statements without the procedure committing or rolling back itself. Java decides to commit when the entire use case succeeds or roll back on error.

This model fits when the transaction also includes other SQL statements outside the procedure or when multiple routines must participate in the same unit of work.

### 15.2. The procedure owns the transaction

The procedure starts the transaction, performs all database operations, and commits/rolls back internally. Java calls the procedure as an independent business command and does not wrap it in an outer transaction expecting to manage commit itself.

This model fits when the procedure represents a complete boundary and does not need to be combined with other Java-managed transactional operations.

Never let both Java and a procedure independently issue `COMMIT`. If Java has already started a transaction and the procedure runs `START TRANSACTION`, MySQL may commit the active transaction before starting a new one. A `COMMIT` inside a procedure can also commit earlier changes made by the caller on the same connection.

Stored procedures can contain transaction control; stored functions and triggers cannot use transaction control statements such as `COMMIT`, `ROLLBACK`, or `START TRANSACTION`. Define the transaction owner before designing the routine.

## 16. Example of a procedure owning the transaction

Example of a procedure recording an audit event and updating order status. The tables use InnoDB:

```sql
CREATE TABLE order_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    old_status VARCHAR(20) NOT NULL,
    new_status VARCHAR(20) NOT NULL,
    changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (audit_id),
    KEY idx_order_audit_order (order_id)
) ENGINE=InnoDB;
```

Procedure with a rollback handler on SQL exception:

```sql
DELIMITER //

CREATE PROCEDURE sp_mark_order_paid(IN p_order_id BIGINT UNSIGNED)
MODIFIES SQL DATA
SQL SECURITY INVOKER
BEGIN
    DECLARE v_old_status VARCHAR(20);
    DECLARE v_found BOOLEAN DEFAULT TRUE;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_found = FALSE;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    SELECT status
    INTO v_old_status
    FROM orders
    WHERE order_id = p_order_id
    FOR UPDATE;

    IF NOT v_found THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Order does not exist';
    END IF;

    IF v_old_status <> 'pending' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Order is not pending';
    END IF;

    UPDATE orders
    SET status = 'paid'
    WHERE order_id = p_order_id;

    INSERT INTO order_audit (order_id, old_status, new_status)
    VALUES (p_order_id, v_old_status, 'paid');

    COMMIT;
END//

DELIMITER ;
```

Call:

```sql
CALL sp_mark_order_paid(1001);
```

This procedure owns the transaction. The caller should not wrap the call in a larger transaction if Java expects to control commit/rollback. The `NOT FOUND` handler sets a flag when the order is missing; the subsequent `SIGNAL` raises a business error, which is caught by the `SQLEXCEPTION` handler to roll back and rethrow to the caller. This example illustrates transaction boundaries and exception handlers, not the only pattern for every schema.

If the workflow needs to call a payment gateway, execute the appropriate database transaction portion, write an outbox event, and commit. A worker handles the gateway after commit; the procedure should not hold locks while waiting on the network.

## 17. Error handling in routines and in Java

MySQL supports `DECLARE ... HANDLER` to handle conditions inside stored programs. A handler can handle exceptions, warnings, `NOT FOUND`, or specific SQLSTATEs.

Example general handler:

```sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    ROLLBACK;
    RESIGNAL;
END;
```

`EXIT` exits the current block after the handler runs. `CONTINUE` handles the condition and continues with the next statement in the block. `RESIGNAL` rethrows the current error so the caller still receives the SQL error.

Do not catch all errors and return a fake success value. If a routine swallows an exception, Java may assume the operation succeeded and commit or return an incorrect response.

In Java, classify errors by SQLSTATE/vendor code, roll back if the application owns the transaction, log with a correlation/request ID, and retry only appropriate transient errors. A deadlock may require retrying the entire transaction; validation or duplicate key errors usually require business-level handling rather than blind retries.

## 18. Calling stored procedures from Java with JDBC

Use `CallableStatement` and bind parameters; never concatenate SQL strings from input:

```java
String sql = "{call app_db.sp_count_customer_orders(?, ?)}";

try (CallableStatement statement = connection.prepareCall(sql)) {
    statement.setLong(1, customerId);
    statement.registerOutParameter(2, Types.BIGINT);

    statement.execute();

    long orderCount = statement.getLong(2);
    // Use orderCount in the use case.
}
```

For procedures returning a result set, read the result set from `CallableStatement`:

```java
String sql = "{call app_db.sp_get_customer_orders(?, ?)}";

try (CallableStatement statement = connection.prepareCall(sql)) {
    statement.setLong(1, customerId);
    statement.setInt(2, 20);

    boolean hasResultSet = statement.execute();
    if (hasResultSet) {
        try (ResultSet rs = statement.getResultSet()) {
            while (rs.next()) {
                long orderId = rs.getLong("order_id");
                String status = rs.getString("status");
                // Map data to objects in the repository layer.
            }
        }
    }
}
```

A procedure can return multiple result sets or update counts. When a routine produces multiple results, the JDBC caller should loop with `getMoreResults()` and check update counts until exhausted, closing every result set before reusing the connection. OUT parameters are typically read after all result sets have been processed, as required by the driver.

Specifying the schema name in the call avoids relying on `USE` or the connection pool's default database.

## 19. Calling stored functions from Java with PreparedStatement

A function is called like a normal SQL expression:

```java
String sql = "SELECT app_db.fn_line_total(?, ?) AS line_total";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setInt(1, quantity);
    statement.setBigDecimal(2, unitPrice);

    try (ResultSet rs = statement.executeQuery()) {
        if (rs.next()) {
            BigDecimal lineTotal = rs.getBigDecimal("line_total");
        }
    }
}
```

Binding parameters keeps data types explicit and reduces SQL injection risk. Never concatenate user values directly into the `SELECT` statement or dynamic routine names. Routine/schema names must typically be fixed identifiers controlled by the application; JDBC placeholders are for values, not for replacing table or column names.

## 20. Java owning the transaction when calling a procedure

If a procedure only executes DML and does not issue `START TRANSACTION`/`COMMIT`, Java can manage the transaction:

```java
try (Connection connection = dataSource.getConnection()) {
    boolean previousAutoCommit = connection.getAutoCommit();
    connection.setAutoCommit(false);

    try {
        try (CallableStatement statement = connection.prepareCall(
                "{call app_db.sp_update_order_details(?, ?)}")) {
            statement.setLong(1, orderId);
            statement.setString(2, newStatus);
            statement.execute();
        }

        // Other SQL statements for the same use case run on this connection.
        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    } finally {
        try {
            connection.setAutoCommit(previousAutoCommit);
        } catch (SQLException resetError) {
            // Log error; the pool may need to discard a connection that cannot be reset.
        }
    }
}
```

The example above assumes the procedure does not self-commit/rollback and all statements run on the same connection. In production applications, use the framework's transaction manager if available; avoid writing multiple overlapping transaction management layers.

If the connection drops while sending `COMMIT`, Java may not know whether the transaction committed. Use an idempotency key or unique business key to look up the outcome before retrying. Do not generate a new request with a different key and blindly re-execute.

## 21. EXECUTE privilege and SQL SECURITY

Stored routines can run under the privileges of the definer or the invoker:

- `SQL SECURITY DEFINER`: checks privileges on underlying objects against the account that defined the routine.
- `SQL SECURITY INVOKER`: checks privileges against the caller of the routine.

The default for routines is `DEFINER` if unspecified. Example creating a procedure with invoker security:

```sql
CREATE PROCEDURE sp_read_customer_summary(IN p_customer_id BIGINT UNSIGNED)
SQL SECURITY INVOKER
READS SQL DATA
BEGIN
    SELECT customer_id, customer_name, status
    FROM customers
    WHERE customer_id = p_customer_id;
END;
```

Granting privilege to call the procedure:

```sql
GRANT EXECUTE ON PROCEDURE app_db.sp_read_customer_summary
TO 'app_runtime'@'%';
```

With `DEFINER`, the application may only need `EXECUTE` privilege on the routine rather than direct privileges on all underlying tables, depending on how the routine is created and the definer's privileges. This is one way to expose a narrow data API. The definer must be managed as a security principal: least privilege, existing account, and migration processes that do not tie routines to personal accounts.

Do not grant broad `EXECUTE` privilege on all routines if the application only needs specific operations. Test privileges using the actual runtime user/role, not solely with a DBA account.

## 22. Stored routines and SQL injection

Routines do not automatically eliminate SQL injection. If a procedure concatenates input strings into dynamic SQL, it can still introduce vulnerabilities:

```sql
-- Unsafe: concatenating input directly into dynamic SQL.
-- SET @sql = CONCAT('SELECT ... WHERE name = ''', p_name, '''');
```

Prefer static SQL with routine parameters. In Java, use `PreparedStatement`/`CallableStatement` and bind values. If a procedure truly needs dynamic SQL, use prepared statements, validate identifiers against an allowlist, and never let arbitrary input dictate table/column names.

Placeholders bind values only, not identifiers. For example, `ORDER BY ?` does not make MySQL sort by a column name passed by the user; it is normally interpreted as an expression value. Map user sort selections through an allowlist of permitted identifiers in the application.

## 23. DETERMINISTIC characteristic and binary logging

Stored functions can declare `DETERMINISTIC` or `NOT DETERMINISTIC`, along with SQL data access characteristics. `DETERMINISTIC` means the same inputs always produce the same result under the same conditions; functions depending on tables, `NOW()`, `RAND()`, session variables, or mutable state should generally not be declared deterministic.

When binary logging is enabled, creating a function may be subject to determinism/privilege checks depending on configuration, such as `log_bin_trust_function_creators`. Do not falsely declare `DETERMINISTIC` just to bypass checks. DBAs should evaluate replication/binlog format, routine creation privileges, and routine correctness.

The characteristics `DETERMINISTIC`, `NO SQL`, and `READS SQL DATA` are metadata committed to by the author; MySQL does not prove that all logic actually satisfies those declarations. Specific settings and rules depend on the MySQL version.

## 24. Important limitations of stored functions

Stored functions are more restricted than procedures because they are invoked as SQL expressions:

- Must return a single scalar value via `RETURN`.
- Cannot return a result set directly.
- Cannot use transaction control such as `START TRANSACTION`, `COMMIT`, or `ROLLBACK`.
- Cannot use dynamic prepared statements (`PREPARE`/`EXECUTE`).
- Cannot invoke a stored procedure using `CALL` from within a function.
- Cannot modify a table already being used by the statement invoking the function, per MySQL restrictions.
- Can be invoked multiple times within a single query; functions that read data can incur heavy overhead.

Triggers share several similar limitations with functions, so do not assume all capabilities of a procedure are available inside a function or trigger.

## 25. Managing routines as schema code

Stored routines are part of the schema and should be managed as code:

1. Store `CREATE PROCEDURE`/`CREATE FUNCTION` in source control.
2. Deploy using ordered, repeatable migrations.
3. Use consistent naming conventions, such as `sp_` for procedures and `fn_` for functions.
4. Document inputs, outputs, errors, privileges, and transaction owner clearly.
5. Review SQL, access paths, and NULL/duplicate/boundary cases.
6. Test routines after modifying underlying tables.
7. Manage definers and `EXECUTE` privileges according to least privilege.
8. Monitor routine latency, invocation counts, and errors from the application.
9. Avoid uncontrolled duplication of the same rule logic between Java and SQL.

MySQL does not provide `CREATE OR REPLACE PROCEDURE`/`FUNCTION` syntax like views in commonly used versions. Migrations typically use `DROP ... IF EXISTS` followed by `CREATE`, or controlled routine deployment tooling. Replacing a routine can affect running consumers; deploy in a compatible order and verify privileges/definer after migration.

## 26. Versioning and compatibility between Java and routines

When Java calls routines by name and parameter position, signature changes can break older application versions. For example, swapping two parameters of the same type may not cause a Java compile error but silently changes semantics.

Guidelines:

- Never silently change parameter order or meaning.
- Prefer explicit, consistent data types matching Java (`BIGINT`/`Long`, `DECIMAL`/`BigDecimal`, `DATETIME`/time conventions).
- When incompatible changes are required, consider creating a new routine version, deploying consumers, and only then removing the old routine.
- Check NULLs and default values explicitly; do not rely on implicit defaults.
- Ensure migrations create routines before the new application version begins calling them.
- Test with the actual runtime account to catch missing `EXECUTE` or underlying privileges.

Routines also store part of their creation environment such as SQL mode and relevant charset/collation information. When deploying across different environments, check configurations and create routines via controlled migrations to prevent unexpected behavioral differences.

## 27. When should logic NOT be placed in stored routines?

Keep logic in Java when:

- Logic changes frequently with product requirements and needs independent deployment from the schema.
- It must call APIs, message brokers, email, the file system, or external services.
- Logic requires domain/crypto/serialization libraries unsuitable for SQL.
- Extensive unit testing, dependency injection, or orchestration across multiple aggregates/services is needed.
- Rules have complex branching and the team lacks strong stored routine review/versioning processes.
- Deeply nested routine calls make execution flow hard to trace.

Consider SQL/routines when:

- The work is primarily set-based operations on MySQL data.
- Multiple clients require the exact same standardized data operation.
- Reducing round-trips delivers measurable benefit.
- A narrow privilege surface via `EXECUTE` and `SQL SECURITY` is required.
- Logic is relatively stable and the team can safely test and migrate routines.

There is no absolute rule that "business logic always lives in Java" or "data logic always lives in stored procedures." Divide based on ownership, testability, performance, and consistency requirements.

## 28. Decision checklist: procedure, function, or Java

| Question | Initial choice direction |
| --- | --- |
| Need to return multiple rows or run multiple steps? | Procedure or SQL via Java |
| Need a scalar value inside an SQL expression? | Function or direct SQL expression |
| Does the logic need to call external services? | Java/service/worker |
| Must multiple clients share the same data rule? | Consider routine and constraints |
| Need one transaction spanning multiple repository calls? | Java transaction owner or one clear procedure boundary |
| Need permission only to invoke one action without reading tables directly? | Procedure with `EXECUTE` privilege and appropriate security |
| Will the function run across millions of rows? | Evaluate set-based SQL instead of a per-row function |
| Does logic change constantly and need unit tests/domain modeling? | Java |
| Need to manage schema code with migrations/versioning? | Routines are only suitable if the pipeline fully supports them |

## 29. Common mistakes and misconceptions

| Misconception / error | Reality | How to handle |
| --- | --- | --- |
| Procedures and functions are the same | Procedures are invoked with `CALL`; functions return scalars in expressions | Choose based on input/output type and call pattern |
| Functions can return multiple rows | Functions return one value; procedures can return result sets | Use a procedure or SELECT |
| Stored routines are always faster than Java | SQL still pays access path, I/O, and CPU costs; per-row functions can be very expensive | Measure round-trips and execution plans |
| Routines automatically guarantee transactions | Transaction boundaries depend on how the routine and caller control them | Designate one transaction owner |
| A procedure can commit without affecting the caller | `COMMIT` in a procedure can commit transactions on the same connection | Do not mix transaction ownership |
| External APIs can be called from a procedure | MySQL routines are not suitable for network orchestration | Use Java/worker and outbox |
| `SQL SECURITY DEFINER` is safe by default | The definer may hold broad privileges and persist long-term | Least privilege, manage definer and `GRANT EXECUTE` |
| Using stored procedures eliminates SQL injection | Dynamic SQL concatenating input remains dangerous | Static SQL, bind parameters, and identifier allowlists |
| `DETERMINISTIC` is just a harmless optimization | It is a commitment about outputs; false declarations can affect binlog/replication | Declare true behavior accurately |
| Catching every exception without reporting it is safe | The caller may receive a false success | Use `RESIGNAL` or return explicit contract error codes |
| Both Java and procedures can freely commit | Either side can terminate the other's transaction | Choose a single owner for commit/rollback |

## 30. Practice exercises

1. Create `sp_get_customer_orders` accepting `IN customer_id` and `IN limit`; invoke it with `CALL` and read the result set.
2. Create `sp_count_customer_orders` returning `OUT order_count`; invoke it with user variables and with JDBC `CallableStatement`.
3. Create a procedure with an `INOUT` parameter to update a monetary value; verify `DECIMAL` types and rounding rules.
4. Create `fn_line_total` returning `DECIMAL`; call it in `SELECT` and compare with a direct SQL expression.
5. Create `fn_order_total` reading the items table; call it for one order and for many orders; measure execution count/cost compared to `JOIN + GROUP BY`.
6. Write a procedure with `EXIT HANDLER FOR SQLEXCEPTION`, rollback, and `RESIGNAL`; test triggering an error in a lab environment.
7. Write a procedure with `SQL SECURITY INVOKER`, grant `EXECUTE`, and verify runtime user privileges.
8. Compare `DEFINER` and `INVOKER` using two accounts with different privileges.
9. Call a procedure from Java using `CallableStatement`; bind parameters, register OUT parameters, and close result sets.
10. Call a function from Java using `PreparedStatement` and `BigDecimal`.
11. Test the Java-owned transaction model with a non-committing procedure; verify Java can roll back all changes.
12. Test a procedure-owned transaction and verify Java does not wrap it in another transaction.
13. Design an order creation use case with an outbox; identify which parts belong to the procedure/database and which belong to the Java worker.
14. Write a migration creating a routine, change its signature in a new version, and test old/new consumers.

## 31. Key takeaways

A stored procedure is a routine invoked with `CALL`, suited for multi-step operations, result sets, and `IN`/`OUT`/`INOUT` parameters. A stored function returns a scalar value via `RETURN`, can be used inside SQL expressions, and accepts only input parameters. Functions should stay small with clear semantics; if called row-by-row while querying data internally, cost can escalate sharply compared to a set-based query.

Stored routines can encapsulate data logic, reduce round-trips, and expose a narrow privilege surface, but they are not automatically faster and do not replace Java. Java fits APIs, orchestration, complex domain logic, external service calls, tracing, and retry policies. MySQL fits constraints and set-based operations; procedures/functions are used when reuse, transaction, or access-privilege benefits are clearly established.

In particular, only one side should own the transaction for a unit of business work: Java or the procedure. Procedures can control transactions; functions cannot commit/rollback or return result sets. Use JDBC `CallableStatement` for procedures and `PreparedStatement` for functions, bind parameters, and manage result sets/connections carefully. Manage routines via source control and migrations, choose `SQL SECURITY` per least privilege, declare `DETERMINISTIC`/SQL data access honestly, and inspect execution plans before putting routines on high-load paths.
