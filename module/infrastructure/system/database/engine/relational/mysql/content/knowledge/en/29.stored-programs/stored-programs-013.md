# Returning Multiple Result Sets and Application Call Contracts

MySQL stored procedures can return multiple result sets in a single `CALL` invocation. Every `SELECT` inside a procedure that does not use `INTO` to assign variables sends a result set back to the client. This is useful when a business operation needs to return both a summary and a detail list together, or return several related datasets without forcing the application to issue multiple separate requests.

Once a procedure becomes an application API, result set ordering, column names, data types, `NULL` semantics, filtering rules, input/output parameters, and error handling all form part of the contract. The application must read every result in the right order and handle update counts or errors raised between result sets. If a procedure adds a debug `SELECT` or swaps two `SELECT` statements, client code can read the wrong data even though the SQL statement executes without error.

This lesson belongs to the `DATABASE_MYSQL` module, focusing on table design, data types, keys, SQL queries, indexes, transactions, concurrency control, execution plan reading, query tuning, and relational database operations. The goal is to design stored procedures that return multiple result sets with a stable structure and invoke them safely from applications, especially Java/JDBC.

After this lesson, you will be able to:

- Distinguish result sets sent to the client from values returned via `OUT`/`INOUT` parameters.
- Create procedures returning summary and detail together in one `CALL`.
- Explain why result set order and column metadata are part of the API contract.
- Distinguish regular `SELECT` from `SELECT ... INTO` inside stored programs.
- Use `CallableStatement.execute()` and `getMoreResults()` to consume all results.
- Handle update counts, empty result sets, and mid-stream errors.
- Define transactions, execution privileges, and data consistency for invocations.
- Design versioning, contract testing, and avoid breaking existing clients.

## 1. A single CALL can return multiple result sets

A stored procedure can contain multiple `SELECT` statements that return data:

In the example, `DELIMITER` is a MySQL command-line client directive to change the statement terminator while entering a procedure body containing `;`. It is not an SQL statement sent to the server; with migration tools or drivers, use the tool's API to submit the entire `CREATE PROCEDURE` statement.

```sql
DELIMITER //

CREATE PROCEDURE sp_demo_multiple_results(IN p_customer_id BIGINT UNSIGNED)
BEGIN
    SELECT customer_id, customer_name
    FROM customers
    WHERE customer_id = p_customer_id;

    SELECT order_id, order_date, total_amount
    FROM orders
    WHERE customer_id = p_customer_id
    ORDER BY order_date DESC, order_id DESC;
END//

DELIMITER ;
```

Calling the procedure:

```sql
CALL sp_demo_multiple_results(42);
```

The client receives sequentially:

1. First result set: customer information.
2. Second result set: order list.

If the customer exists but has no orders, the second result set still exists structurally with 0 rows. This differs from the procedure failing to emit a second result set. Applications must distinguish an "empty result set" from "no result set at the expected position."

`CALL` is a single statement capable of producing multiple results. Client/server protocol and drivers must support multiple results. Connector/J supports reading stored procedure result sets via JDBC; you do not need to enable semicolon-separated multi-statement execution merely because a procedure returns multiple result sets.

## 2. SELECT returns a result set while SELECT ... INTO does not

Inside a stored procedure, a regular `SELECT` sends data back to the client:

```sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = p_customer_id;
```

In contrast, `SELECT ... INTO` assigns values into local variables or appropriately declared variables; it does not send a data result set to the client:

```sql
BEGIN
    DECLARE v_order_count BIGINT UNSIGNED DEFAULT 0;

    SELECT COUNT(*)
    INTO v_order_count
    FROM orders
    WHERE customer_id = p_customer_id;
END;
```

The snippet above is the body inside a procedure with parameter `IN p_customer_id`. Within the same `BEGIN ... END` block, that local variable can be included in a subsequent result set:

```sql
SELECT
    p_customer_id AS customer_id,
    v_order_count AS order_count;
```

This distinction is critical when designing contracts. A `SELECT` meant for internal calculation must not accidentally become the first result set the client has to read. When you do not want to emit data, use `SELECT ... INTO`, `SET`, or an appropriate statement.

## 3. Designing a procedure returning summary and detail

The example below uses a hypothetical orders table with columns `order_id`, `customer_id`, `order_date`, `order_status`, and `total_amount`.

```sql
DELIMITER //

CREATE PROCEDURE sp_customer_order_report(
    IN p_customer_id BIGINT UNSIGNED,
    IN p_from_date DATE,
    IN p_to_date DATE
)
READS SQL DATA
SQL SECURITY INVOKER
BEGIN
    IF p_from_date IS NULL
       OR p_to_date IS NULL
       OR p_from_date >= p_to_date THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Invalid reporting date range';
    END IF;

    -- Result set 1: summary, always returns exactly one row.
    SELECT
        p_customer_id AS customer_id,
        p_from_date AS period_start,
        p_to_date AS period_end_exclusive,
        COUNT(*) AS order_count,
        COALESCE(
            SUM(CASE WHEN order_status = 'PAID'
                     THEN total_amount ELSE 0 END),
            0
        ) AS paid_total
    FROM orders
    WHERE customer_id = p_customer_id
      AND order_date >= p_from_date
      AND order_date < p_to_date;

    -- Result set 2: detail, may contain 0 or more rows.
    SELECT
        order_id,
        order_date,
        order_status,
        total_amount
    FROM orders
    WHERE customer_id = p_customer_id
      AND order_date >= p_from_date
      AND order_date < p_to_date
    ORDER BY order_date DESC, order_id DESC;
END//

DELIMITER ;
```

Call:

```sql
CALL sp_customer_order_report(42, '2026-11-01', '2026-12-01');
```

The date range is half-open: `>= p_from_date` and `< p_to_date`. Thus, boundary dates are never double-counted across adjacent reporting periods.

### 3.1. Result set contract of the example

| Order | Logical name | Columns in order | Cardinality |
| --- | --- | --- | --- |
| 1 | `customer_summary` | `customer_id`, `period_start`, `period_end_exclusive`, `order_count`, `paid_total` | Always 1 row because aggregate has no `GROUP BY` |
| 2 | `order_details` | `order_id`, `order_date`, `order_status`, `total_amount` | 0..N rows |

The first result set uses an aggregate without `GROUP BY`, so it returns one row even when no orders match. `COUNT(*)` is `0` when empty; `SUM` would be `NULL` and is normalized to `0` via `COALESCE`. The second result set is still emitted with full column metadata, though it may contain zero rows.

Applications should never infer a result set's meaning merely from row count. Rely on position and the published contract.

## 4. Ordering and metadata are part of the API contract

When an application calls a procedure, the first result set does not carry a separate logical name over the protocol the way a JSON API does. Clients receive result sets in emission order. Therefore, the order of `SELECT` statements inside a procedure is part of the interface.

The contract should specify for each result set:

- Ordinal position and logical name defined by API documentation.
- Column names and column order.
- MySQL/JDBC data types and nullability.
- Meaning of each column, currency/time units, and timezone if applicable.
- Cardinality: 0..1, exactly 1, 0..N, or 1..N.
- Sorting, filtering, and pagination rules.
- Conditions under which a result set may be empty.
- Contract version and compatibility policy.

Example contract table:

| Result set | Column | Expected type | Nullable | Meaning |
| --- | --- | --- | --- | --- |
| 1 | `customer_id` | `BIGINT UNSIGNED` | No | Requested customer key |
| 1 | `order_count` | `BIGINT` | No | Order count in period |
| 1 | `paid_total` | `DECIMAL(14,2)` | No | Total amount of `PAID` orders, in system-standard currency unit |
| 2 | `order_id` | `BIGINT UNSIGNED` | No | Order ID |
| 2 | `order_date` | `DATE` | No | Order date |
| 2 | `order_status` | `VARCHAR(20)` | No | Business status |
| 2 | `total_amount` | `DECIMAL(12,2)` | No | Order total amount |

Use explicit aliases so column names do not change unexpectedly when SQL expressions are refactored. Avoid `SELECT *` in public procedures: adding a column to the base table can alter result set metadata and break positional clients.

## 5. Empty result set, no result set, and NULL

These three cases are distinct:

1. **Result set with 0 rows:** the procedure ran `SELECT`; column metadata is sent, but there are zero records.
2. **No result set:** the current statement produced no result set, e.g. the procedure only ran `UPDATE` or `SELECT ... INTO`.
3. **Result set with rows containing NULL:** records exist, but one or more field values are `NULL`.

Clients must handle each case accurately. For example, finding no orders can be represented by an empty detail result set while summary still contains one row with `order_count = 0` and `paid_total = 0`.

Never emit an unexpected extra result set just to return a debug message. If business status is needed, include it in the summary result set or an `OUT` parameter defined in the contract.

## 6. OUT and INOUT parameters are separate data channels

Stored procedures can return data via result sets, `OUT` parameters, or `INOUT` parameters. These are separate mechanisms:

- Result sets suit 0..N rows and multiple columns.
- `OUT` parameters suit a single output value with a known name and type.
- `INOUT` parameters accept an input value and return the updated value.

Example procedure using an `OUT` parameter:

```sql
DELIMITER //

CREATE PROCEDURE sp_count_customer_orders(
    IN p_customer_id BIGINT UNSIGNED,
    OUT p_order_count BIGINT UNSIGNED
)
READS SQL DATA
BEGIN
    SELECT COUNT(*)
    INTO p_order_count
    FROM orders
    WHERE customer_id = p_customer_id;
END//

DELIMITER ;
```

Calling from an SQL client:

```sql
CALL sp_count_customer_orders(42, @order_count);
SELECT @order_count AS order_count;
```

`@order_count` is a user-defined session variable on the current connection. In JDBC, register `OUT` parameters on `CallableStatement` instead of managing user variables manually if the driver supports callable parameter mapping.

Do not return the exact same data via both a result set and an `OUT` parameter unless there is an explicit compatibility reason. Duplicate value sources complicate the contract and can drift if the procedure updates only one side.

## 7. Calling multi-result-set procedures with Java JDBC

In JDBC, use `CallableStatement` and `execute()` to invoke procedures that can return multiple result types. Do not use `executeQuery()` when a procedure returns multiple result sets or may interleave update counts.

Example processing result sets in order:

```java
String sql = "{call sp_customer_order_report(?, ?, ?)}";

try (CallableStatement call = connection.prepareCall(sql)) {
    call.setLong(1, customerId);
    call.setDate(2, java.sql.Date.valueOf(fromDate));
    call.setDate(3, java.sql.Date.valueOf(toDate));

    boolean hasResultSet = call.execute();
    int resultSetNumber = 0;

    while (true) {
        if (hasResultSet) {
            resultSetNumber++;

            try (ResultSet rs = call.getResultSet()) {
                if (resultSetNumber == 1) {
                    while (rs.next()) {
                        long id = rs.getLong("customer_id");
                        long count = rs.getLong("order_count");
                        BigDecimal paidTotal = rs.getBigDecimal("paid_total");
                        // Map to CustomerSummary.
                    }
                } else if (resultSetNumber == 2) {
                    while (rs.next()) {
                        long orderId = rs.getLong("order_id");
                        java.sql.Date orderDate = rs.getDate("order_date");
                        String status = rs.getString("order_status");
                        BigDecimal amount = rs.getBigDecimal("total_amount");
                        // Map to OrderDetail.
                    }
                } else {
                    throw new SQLException("Unexpected result set: " + resultSetNumber);
                }
            }
        } else {
            int updateCount = call.getUpdateCount();
            if (updateCount == -1) {
                break; // No more result sets or update counts.
            }
            // Process or log update count if specified by contract.
        }

        hasResultSet = call.getMoreResults(Statement.CLOSE_CURRENT_RESULT);
    }

    if (resultSetNumber != 2) {
        throw new SQLException("Expected 2 result sets, got " + resultSetNumber);
    }
}
```

The loop handles both result kinds:

- `hasResultSet == true`: retrieve the current `ResultSet` and read all rows.
- `hasResultSet == false`: inspect `getUpdateCount()`. A value of `-1` indicates no further results.

`getMoreResults(Statement.CLOSE_CURRENT_RESULT)` advances to the next result and closes the current result set. The example above maps by column name for readability; the contract still requires stable metadata. If mapping by index, reordering columns can silently cause clients to read wrong data without type errors.

### 7.1. Do not stop after the first result set

A common bug is calling `execute()`, reading `getResultSet()`, and immediately closing `CallableStatement` after reading the summary. The detail result set remains unconsumed. Depending on driver and connection management, abandoning unread results can leave the statement/connection unprepared for subsequent queries or waste resources.

Always iterate through all result sets and update counts per contract before returning the connection to the pool. Even if the application does not need details, still consume or close remaining results per driver API.

### 7.2. Distinguishing multiple result sets from multiple statements

A procedure with multiple `SELECT`s returns multiple result sets via a single `CALL`. This is not equivalent to the client sending a multi-statement string like `SELECT ...; SELECT ...;`. Driver options allowing multi-query execution normally control sending multiple separate statements in a single request; do not enable that option merely because a procedure returns multiple result sets.

## 8. Reading OUT parameters with JDBC

Example:

```java
try (CallableStatement call = connection.prepareCall(
        "{call sp_count_customer_orders(?, ?)}")) {
    call.setLong(1, customerId);
    call.registerOutParameter(2, Types.BIGINT);

    call.execute();

    long orderCount = call.getLong(2);
    if (call.wasNull()) {
        // Handle NULL if permitted by contract.
    }
}
```

For procedures returning both result sets and `OUT` parameters, register `OUT` parameters before `execute()`. Read and consume all result sets according to driver guidance, then retrieve `OUT` values once the driver guarantees result processing is complete. Test behavior with the exact MySQL Connector/J version deployed by the application.

SQL and JDBC types must be compatible. For instance, `BIGINT UNSIGNED` has a larger range than Java signed `BIGINT` (`long`); if values may exceed `Long.MAX_VALUE`, map to `BigInteger` or an appropriate type rather than assuming `getLong()` is always safe.

## 9. Update counts and non-row-returning statements

Stored procedures can interleave `SELECT` with `INSERT`/`UPDATE`/`DELETE`:

```sql
DELIMITER //

CREATE PROCEDURE sp_refresh_customer_flag(IN p_customer_id BIGINT UNSIGNED)
MODIFIES SQL DATA
BEGIN
    UPDATE customers
    SET has_recent_order = EXISTS (
        SELECT 1
        FROM orders
        WHERE customer_id = p_customer_id
          AND order_date >= CURRENT_DATE - INTERVAL 30 DAY
    )
    WHERE customer_id = p_customer_id;

    SELECT customer_id, has_recent_order
    FROM customers
    WHERE customer_id = p_customer_id;
END//

DELIMITER ;
```

The driver may report an update count between result sets. Clients must not assume `getMoreResults()` always returns `true`. Iterate through result states using the loop pattern and do not ignore update counts if they are part of the contract.

If the application only needs the final result, consider designing the procedure so internal DML statements do not produce unwanted output, and test actual update count behavior with the driver.

## 10. Errors and partial results

Suppose a procedure executes:

1. `SELECT` summary.
2. `SELECT` detail.
3. Another operation that can fail.

If an error happens after a result set has already been sent, the client may have read partial data before receiving the exception. Applications must not treat a partial payload as a complete successful response.

The error contract should specify:

- SQLSTATE/error codes used for input errors, business errors, and system errors.
- Which business cases cause `SIGNAL`/`RESIGNAL` versus returning a status result set.
- That the client must discard the entire payload if the call ends in `SQLException`.
- Whether retries are allowed, and whether retries are safe/idempotent.
- Where transactions roll back if the procedure modifies data.

Input error example:

```sql
IF p_customer_id IS NULL THEN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'customer_id is required';
END IF;
```

Do not mix both error-reporting styles without clear rules. Technical failures should normally be thrown as exceptions for the application to handle; business outcomes such as "no orders found" usually suit an empty result set or a defined status field.

## 11. Transactions and consistency across result sets

Multiple result sets can be read at different points in time if transaction boundaries are not clearly defined. For example, summary is computed first, another transaction inserts an order, and then detail is read. If both `SELECT`s do not share a consistent snapshot, summary and detail may disagree.

When all result sets must reflect the exact same data state:

- Define whether the caller or the procedure owns the transaction.
- If caller-owned, open the transaction on the same connection before `CALL` and prevent the procedure from unexpectedly self-`COMMIT`ting.
- Choose an appropriate isolation level. Under InnoDB `REPEATABLE READ`, consistent reads in the same transaction normally share the same read view; `READ COMMITTED` creates a fresh snapshot for each consistent read.
- Do not mix locking reads for one part and consistent reads for another without understanding snapshot/lock differences.
- End the transaction only after all result sets have been read and related work is done.

Do not casually embed `START TRANSACTION`, `COMMIT`, or `ROLLBACK` into a shared procedure. Self-managed transactions inside a procedure can conflict with transactions opened by the application. If a routine truly owns the transaction, document it in the contract and test error paths.

## 12. Execution privileges and SQL SECURITY

Applications normally need `EXECUTE` privilege on the procedure. Access privileges on internal tables also depend on the `SQL SECURITY` attribute:

- `SQL SECURITY DEFINER`: the routine runs with the definer's privileges; this is the default unless specified otherwise.
- `SQL SECURITY INVOKER`: the routine runs with the caller's privileges; the caller needs required privileges on accessed objects.

Example granting call privilege:

```sql
GRANT EXECUTE
ON PROCEDURE reporting_db.sp_customer_order_report
TO 'report_app'@'%';
```

Choose `DEFINER` or `INVOKER` according to the authorization model. With `DEFINER`, manage the definer account and routine privileges carefully; avoid accounts with unnecessarily broad privileges. With `INVOKER`, ensure callers receive proper table privileges.

The application contract should document which roles call the routine, which schema holds it, whether special session variables or SQL modes are required, and how definers are deployed in staging/production.

## 13. Designing stable contracts and version compatibility

A stored procedure is an interface with dependent clients. Changing a procedure can break clients even without renaming the routine.

### 13.1. Breaking changes

- Changing the order of result sets.
- Inserting a new result set between existing result sets.
- Renaming or reordering columns.
- Changing data types, `DECIMAL` precision, or nullability.
- Changing `NULL` semantics, default values, or units of measurement.
- Changing sorting, filtering, pagination, or timezone rules.
- Replacing an empty result set by omitting the `SELECT` altogether.
- Adding a debug `SELECT` or a `SELECT` inside an error handler.
- Changing parameter count/order or `IN`/`OUT`/`INOUT` modes.
- Changing `SQL SECURITY` or execution privileges in a way that revokes access from existing callers.

### 13.2. Safe ways to evolve

- Keep the order and schema of existing result sets intact.
- When adding data, consider appending nullable columns at the end of a result set if client mapping supports it; still test all consumers.
- For major changes to order, structure, or semantics, create a new routine version such as `sp_customer_order_report_v2`.
- Publish the contract version and deprecation window for older versions.
- Use explicit aliases and explicit data types.
- Never return columns depending on debug flags, server variables, or internal state outside the API.
- Maintain integration tests against the exact production driver and MySQL version.

Do not rely on physical column order in base tables or use `SELECT *`. Procedures should define outputs independent of unrelated internal schema changes.

## 14. Pagination and limiting result set size

A procedure returning 0..N detail rows can inadvertently send millions of rows over the network. The contract must bound data volume:

- Add `IN p_limit` and `IN p_offset` or cursor/keyset pagination on a stable key.
- Define a deterministic `ORDER BY` with a unique tie-breaker such as `order_id`.
- Return total row count only if the application truly requires it; avoid full `COUNT` scans solely for page rendering.
- Enforce a maximum cap on page size.
- Consider keeping the summary result set separate from the paginated detail result set.

Example:

```sql
SELECT order_id, order_date, order_status, total_amount
FROM orders
WHERE customer_id = p_customer_id
  AND order_date >= p_from_date
  AND order_date < p_to_date
ORDER BY order_date DESC, order_id DESC
LIMIT p_limit OFFSET p_offset;
```

With large offsets, keyset pagination can be more efficient when backed by a suitable index. The contract must specify the page token/cursor if using keyset pagination, as well as behavior when data changes between calls.

## 15. Streaming, consuming results, and connection lifecycle

Large result sets can be buffered entirely by the driver or streamed incrementally depending on API/configuration. Streaming reduces application memory usage but keeps the statement and connection busy until the result set is consumed or closed.

Operational rules:

- Read and close each `ResultSet` before moving to the next result per driver contract.
- Never return a connection to the pool while unread result sets remain.
- Never hold transactions open long because a client processes rows slowly; consider pagination or batching results.
- Set query timeouts and result size limits.
- If the client aborts mid-stream, close statement/connection properly and let the pool discard the connection if protocol state is no longer safe.
- Test streaming mode with your actual Connector/J version; how streaming is enabled depends on the driver.

A procedure returning multiple result sets does not mean the application can read all sets concurrently on one connection. The protocol is sequential; typically the current result must be consumed or closed before advancing to the next.

## 16. Testing procedure contracts

A contract test should verify both SQL output and driver behavior.

| Test category | What to verify |
| --- | --- |
| Result set count | Exact count and order match the contract |
| Metadata | Column names, order, SQL types, precision/scale, and nullability are accurate |
| Cardinality | Summary has 1 row; detail has 0..N rows |
| Empty case | No detail rows still returns an empty second result set |
| Boundary | Start date inclusive, end date exclusive |
| `NULL` | `NULL` values map properly without confusion with `0`/empty string |
| `OUT` parameters | Exact types and values after `CALL` |
| Update counts | Client properly handles interleaved update counts if any |
| Error path | SQLSTATE/message match; client discards partial payload |
| Transactions | Result sets share a consistent snapshot as required |
| Security | Application role holds `EXECUTE` and proper object privileges |
| Compatibility | Older consumers continue working when changes deploy |

### 16.1. Verifying metadata with JDBC

`ResultSetMetaData` lets you verify the output schema:

```java
ResultSetMetaData meta = rs.getMetaData();
int columnCount = meta.getColumnCount();

for (int i = 1; i <= columnCount; i++) {
    System.out.printf(
        "%d: %s, jdbcType=%d, typeName=%s, nullable=%d%n",
        i,
        meta.getColumnLabel(i),
        meta.getColumnType(i),
        meta.getColumnTypeName(i),
        meta.isNullable(i)
    );
}
```

Run metadata tests in CI or integration tests after every migration that modifies procedures. Compare both column labels and types/precision/scale; checking column names alone is insufficient.

## 17. Checklist for designing and calling multi-result procedures

- [ ] Clearly defined the count and order of result sets.
- [ ] Documented each result set's logical name, column schema, and cardinality.
- [ ] Used regular `SELECT` only when emitting a result set; used `SELECT ... INTO` for internal calculations.
- [ ] No debug `SELECT` or off-contract `SELECT` in procedures/handlers.
- [ ] Clearly defined `OUT`/`INOUT` parameter usage without redundant data duplication.
- [ ] Client uses `execute()` and consumes all result sets/update counts.
- [ ] Client treats an empty result set differently from a missing result set.
- [ ] Client closes `ResultSet`/`CallableStatement` and never returns connections with unread results.
- [ ] Defined transaction owner and isolation level for cross-result-set consistency.
- [ ] Aligned on `SQL SECURITY` and `EXECUTE` privileges.
- [ ] Bounded detail result set size and pagination rules.
- [ ] Tested SQLSTATE, mid-stream errors, and partial result handling.
- [ ] Tested metadata with the exact MySQL Connector/J version.
- [ ] Established a versioning strategy for breaking changes.

## 18. Practice exercises

1. Create `sp_customer_order_report` returning summary and detail. Call it from an SQL client and note the order of the two result sets.
2. Test a customer with orders and a customer with no orders. Verify the empty detail result set still exists.
3. Convert a count `SELECT` to `SELECT ... INTO`; verify the client no longer receives an extra result set.
4. Create `sp_count_customer_orders` with an `OUT` parameter. Call it using a user variable and via JDBC `registerOutParameter`.
5. Write Java `CallableStatement` code iterating through multiple result sets using `getMoreResults()`; add an assertion on expected result set count.
6. Insert an `UPDATE` between two `SELECT`s and observe the update count returned by the driver.
7. Intentionally trigger `SIGNAL` after the first result set; determine when the client receives the exception and ensure partial payloads are discarded.
8. Run `CALL` under `REPEATABLE READ` and `READ COMMITTED` transactions while simulating another session inserting an order between the two queries to observe snapshot behavior.
9. Use `ResultSetMetaData` to log column labels, JDBC types, precision/scale, and nullability for each result set.
10. Change an output column in the procedure in a lab environment; write a contract test that catches the change.
11. Add pagination to the detail result set and verify stable ordering when multiple orders share the same date.
12. Design `sp_customer_order_report_v2` for a breaking change and outline a client migration plan.

## 19. Completion criteria

You complete this lesson when you can build a stored procedure returning at least two purpose-built result sets, accurately specify their ordering/schema/cardinality, distinguish result sets from `OUT` parameters, invoke and consume all results with JDBC, handle update counts and mid-stream errors, and ensure proper transaction/security/connection lifecycle management. You should also have contract tests capable of catching metadata or ordering changes that could break applications.

## References

- [MySQL 8.4 Reference Manual — CALL Statement](https://dev.mysql.com/doc/refman/8.4/en/call.html)
- [MySQL 8.4 Reference Manual — CREATE PROCEDURE and CREATE FUNCTION](https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html)
- [MySQL 8.4 Reference Manual — Stored Routine Syntax](https://dev.mysql.com/doc/refman/8.4/en/stored-programs-defining.html)
- [MySQL Connector/J Developer Guide — Stored Procedures](https://dev.mysql.com/doc/connector-j/en/connector-j-usagenotes-statements-callable.html)
- [Java JDBC API — CallableStatement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/CallableStatement.html)
