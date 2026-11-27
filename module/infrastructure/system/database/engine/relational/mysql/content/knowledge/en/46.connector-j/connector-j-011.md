# Generated Keys, AUTO_INCREMENT, and Connection Boundaries

When a Java application inserts a row into a MySQL table with an AUTO_INCREMENT column, it frequently needs the newly generated ID to insert child rows, return an API response, or record a transaction audit trail. With MySQL Connector/J, the standard approach is requesting JDBC to return generated keys and reading them from the exact PreparedStatement that executed the INSERT. If using LAST_INSERT_ID(), the query must run on the exact same physical connection as the INSERT. Understanding the boundaries between statements, transactions, and connections prevents retrieving the wrong ID under concurrent requests, connection pools, or batch inserts.

This lesson belongs to the **Connector/J** chapter of the **DATABASE_MYSQL** module. Along the path to mastering MySQL—from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, execution plans, query tuning, authorization, backups, and operations—Connector/J serves as the connectivity layer enabling Java applications to execute these operations. This lesson focuses on generated keys, AUTO_INCREMENT allocation rules, and how MySQL session state is scoped to a connection.

## 1. How Is AUTO_INCREMENT Allocated?

An AUTO_INCREMENT column is an integer column for which MySQL automatically assigns a value when an INSERT omits an explicit value for that column:

~~~sql
CREATE TABLE customers (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  email VARCHAR(254) NOT NULL,
  display_name VARCHAR(120) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_customers_email (email)
) ENGINE=InnoDB;
~~~

The application can insert a row without supplying `id`:

~~~sql
INSERT INTO customers (email, display_name)
VALUES ('linh@example.com', 'Linh Nguyen');
~~~

MySQL allocates a value for `id` and stores the row. In JDBC, the application can retrieve the generated key via the `getGeneratedKeys()` API.

AUTO_INCREMENT is an identifier-allocation mechanism, not a row counter and not a gapless business sequence. Gaps can occur because:

- A transaction inserts a row and then rolls back.
- An INSERT fails or skips rows due to duplicates/IGNORE.
- Multiple connections insert concurrently.
- A single INSERT allocates multiple values or a batch is split across multiple statements.
- The application deletes rows that were already assigned IDs.
- `auto_increment_increment` and `auto_increment_offset` settings produce steps other than 1, commonly seen in certain replication topologies.

Never use IDs to infer row counts, commit order, or strict business sequence. If business regulations require gapless invoice numbers, design a dedicated numbering mechanism with appropriate locking and controls; AUTO_INCREMENT does not guarantee a contiguous sequence.

### Choosing Data Types and Growth Limits

Select an integer type based on expected maximum row count and retention period:

| Type | UNSIGNED Range | When to consider |
|---|---:|---|
| TINYINT | 0 to 255 | Very small lookup tables, few rows |
| SMALLINT | 0 to 65,535 | Small datasets |
| MEDIUMINT | 0 to 16,777,215 | Systems with well-bounded growth |
| INT | 0 to 4,294,967,295 | Many business applications |
| BIGINT | 0 to 18,446,744,073,709,551,615 | Large tables, long lifespans, or high headroom needs |

These limits are for UNSIGNED types. For signed types, the positive range is lower. When a schema uses `BIGINT UNSIGNED`, Java can read via `ResultSet.getLong()` if values stay within Java's signed 64-bit range. MySQL's BIGINT UNSIGNED range exceeds `Long.MAX_VALUE`; if a system can surpass that bound, use a representation such as `BigInteger` and convert carefully from driver return values.

Do not pick BIGINT merely because "bigger is better" without considering index size, foreign keys, and network payload. Parent-child key columns must have compatible types. Equally, do not choose INT when projected growth could exhaust its range within the expected operational lifetime.

## 2. Retrieving Generated Keys via JDBC

JDBC provides the `Statement.RETURN_GENERATED_KEYS` flag. Pass this flag when creating the PreparedStatement, execute the INSERT, and read the ResultSet returned by `getGeneratedKeys()`:

The Java examples use text blocks (`"""`), supported since Java 15. If your project targets an older JDK, replace text blocks with regular Java strings while preserving placeholders.

~~~java
String sql = """
    INSERT INTO customers (email, display_name)
    VALUES (?, ?)
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         sql,
         Statement.RETURN_GENERATED_KEYS
     )) {

    statement.setString(1, "linh@example.com");
    statement.setString(2, "Linh Nguyen");

    int affectedRows = statement.executeUpdate();
    if (affectedRows != 1) {
        throw new SQLException(
            "Expected one inserted customer, got " + affectedRows
        );
    }

    try (ResultSet keys = statement.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("MySQL did not return a generated key");
        }

        long customerId = keys.getLong(1);
        if (keys.wasNull()) {
            throw new SQLException("Generated key is NULL");
        }

        System.out.println("Created customer id = " + customerId);
    }
}
~~~

Key points:

1. Create the statement with `Statement.RETURN_GENERATED_KEYS`; if generated keys are not requested, do not assume the driver always returns them.
2. Use `executeUpdate()` for INSERT/UPDATE/DELETE.
3. Call `getGeneratedKeys()` on the exact statement that executed the INSERT.
4. Check that the ResultSet has a row before reading.
5. Read the first column using `getLong(1)` or a Java type matching the ID column.
6. Read generated keys before closing the statement and connection.

You can specify generated key column names using the `prepareStatement(sql, new String[] {"id"})` overload if needed. For ordinary AUTO_INCREMENT columns, `Statement.RETURN_GENERATED_KEYS` is concise and standard.

Never use `SELECT MAX(id)` to find the newly inserted ID. Another connection could insert a row between your INSERT and the MAX query, causing the application to grab another request's ID. Generated keys are scoped to the current statement and avoid that race condition.

## 3. Retrieving IDs via LAST_INSERT_ID()

MySQL provides the `LAST_INSERT_ID()` function, which returns the first AUTO_INCREMENT value generated by the most recent INSERT statement in the **current session**:

~~~sql
INSERT INTO customers (email, display_name)
VALUES ('linh@example.com', 'Linh Nguyen');

SELECT LAST_INSERT_ID();
~~~

The result is valid only for the session that ran the INSERT. Each MySQL connection maintains its own LAST_INSERT_ID state; another connection inserting rows does not alter the current session's value.

In JDBC, both statements can execute on the same Connection:

~~~java
long customerId;

try (Connection connection = dataSource.getConnection()) {
    try (PreparedStatement insert = connection.prepareStatement(
            "INSERT INTO customers (email, display_name) VALUES (?, ?)")) {
        insert.setString(1, "linh@example.com");
        insert.setString(2, "Linh Nguyen");
        insert.executeUpdate();
    }

    try (Statement query = connection.createStatement();
         ResultSet result = query.executeQuery("SELECT LAST_INSERT_ID()")) {
        if (!result.next()) {
            throw new SQLException("LAST_INSERT_ID() returned no row");
        }
        customerId = result.getLong(1);
    }
}
~~~

This works, provided the exact same Connection is kept across both statements. Never call `connection.close()` after the INSERT and borrow a fresh Connection from the pool to run `SELECT LAST_INSERT_ID()`; the new connection is a different session with separate LAST_INSERT_ID state.

In JDBC, prefer `getGeneratedKeys()` because the API directly associates the INSERT with its generated key. Use LAST_INSERT_ID() when there is a specific reason, such as reading session state or integrating with a specialized SQL statement.

### LAST_INSERT_ID() and Multi-Row INSERTs

For a multi-row INSERT statement, `LAST_INSERT_ID()` returns the first AUTO_INCREMENT value generated by that statement, not a list of all IDs. Never compute subsequent IDs by mechanically adding 1: auto-increment settings, concurrency, INSERT variants, and ID allocation mechanics can create gaps or step increments.

If exact mapping from each input record to its output ID is required, use generated keys and verify Connector/J behavior for your exact driver version and batch mode. When deterministic mapping is needed regardless of driver batch rewriting, include a stable application-generated business key/UUID in the data to query the mapping back, or execute individual INSERTs and read each key directly.

## 4. Boundaries Between Connection, Statement, and ResultSet

JDBC involves three directly related objects:

- **Connection:** represents one session connected to MySQL. Transaction state, session variables, temporary tables, and LAST_INSERT_ID() belong to this session.
- **Statement/PreparedStatement:** executes an SQL statement on the Connection. Generated keys are retrieved from the statement that requested and executed the INSERT.
- **ResultSet:** holds returned rows, including the generated keys ResultSet. It must be read before closing the parent resources.

Lifecycle diagram:

~~~text
DataSource
    |
    | getConnection()
    v
Connection (one MySQL session)
    |
    +--> PreparedStatement (INSERT ... RETURN_GENERATED_KEYS)
    |          |
    |          +--> executeUpdate()
    |          |
    |          +--> getGeneratedKeys()
    |                    |
    |                    v
    |               ResultSet: id
    |
    +--> Can continue using the same Connection
    |    for child-row INSERT / LAST_INSERT_ID()
    |
    v
commit or rollback
    |
    v
close Connection
    |
    +--> With pool: returns logical connection to pool
    +--> Without pool: closes physical connection
~~~

With a connection pool, `dataSource.getConnection()` usually returns a logical connection borrowed from the pool. Calling `close()` returns the connection to the pool for reuse rather than necessarily closing the TCP connection. The pool is responsible for resetting certain states on return; the application must still commit/rollback properly and drop references after closing.

Never store a session ID in a static variable or shared cross-request variable. Each request must use its own Connection for all operations requiring the same transaction or session state.

## 5. Inserting Parent and Child Rows in the Same Transaction

A generated key is commonly used to insert a parent row and then insert child rows referencing it. Both operations require the same Connection and same transaction to ensure atomicity.

Example creating a customer and an order:

~~~java
String insertCustomerSql = """
    INSERT INTO customers (email, display_name)
    VALUES (?, ?)
    """;

String insertOrderSql = """
    INSERT INTO orders (order_no, customer_id, total_amount)
    VALUES (?, ?, ?)
    """;

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        long customerId;

        try (PreparedStatement customerInsert =
                 connection.prepareStatement(
                     insertCustomerSql,
                     Statement.RETURN_GENERATED_KEYS
                 )) {

            customerInsert.setString(1, "linh@example.com");
            customerInsert.setString(2, "Linh Nguyen");

            int rows = customerInsert.executeUpdate();
            if (rows != 1) {
                throw new SQLException("Customer insert did not affect one row");
            }

            try (ResultSet keys = customerInsert.getGeneratedKeys()) {
                if (!keys.next()) {
                    throw new SQLException("Missing customer generated key");
                }
                customerId = keys.getLong(1);
                if (keys.wasNull()) {
                    throw new SQLException("Customer id is NULL");
                }
            }
        }

        try (PreparedStatement orderInsert =
                 connection.prepareStatement(insertOrderSql)) {
            orderInsert.setString(1, "ORD-2026-0001");
            orderInsert.setLong(2, customerId);
            orderInsert.setBigDecimal(3, new BigDecimal("125000.00"));

            int rows = orderInsert.executeUpdate();
            if (rows != 1) {
                throw new SQLException("Order insert did not affect one row");
            }
        }

        connection.commit();
    } catch (SQLException | RuntimeException error) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;
    }
}
~~~

Characteristics of this flow:

- The customer ID is read before commit, so it can immediately be used to insert the order within the same transaction.
- If inserting the order fails and rollback succeeds, neither the customer nor the order is committed.
- Allocated AUTO_INCREMENT values may not be reused after rollback; gaps in the ID sequence are normal.
- Never publish the ID to external systems or emit "created successfully" events before the transaction commits successfully.

If the connection drops right at COMMIT, the client may not know whether the server committed. Never blindly retry the entire business operation without an idempotency mechanism; use a unique request key or business key to query and verify the outcome before retrying.

In transaction-managed frameworks like Spring, let the framework control commit/rollback and retrieve generated keys inside that transaction. Never manually open a separate Connection outside the transaction manager and expect both connections to share one transaction.

## 6. INSERT ON DUPLICATE KEY UPDATE and Retrieving Existing Row IDs

A special case is upsert: if the unique key does not exist, INSERT creates a new row; if it already exists, MySQL executes the UPDATE branch. On duplicate, the application may need the existing row's ID.

Example:

~~~sql
INSERT INTO customers (email, display_name)
VALUES (?, ?)
ON DUPLICATE KEY UPDATE
  id = LAST_INSERT_ID(id);
~~~

If INSERT creates a new row, MySQL sets LAST_INSERT_ID to the newly generated ID. If the UPDATE branch executes, the expression `LAST_INSERT_ID(id)` places the existing row's ID into the session's LAST_INSERT_ID state.

JDBC can then read the value on the same Connection:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement upsert = connection.prepareStatement("""
         INSERT INTO customers (email, display_name)
         VALUES (?, ?)
         ON DUPLICATE KEY UPDATE
           id = LAST_INSERT_ID(id)
         """)) {

    upsert.setString(1, "linh@example.com");
    upsert.setString(2, "Linh Nguyen");
    upsert.executeUpdate();

    try (Statement query = connection.createStatement();
         ResultSet result = query.executeQuery("SELECT LAST_INSERT_ID()")) {
        if (!result.next()) {
            throw new SQLException("No customer id returned");
        }
        long customerId = result.getLong(1);
    }
}
~~~

Apply this pattern only when the duplicate key unambiguously identifies a single row per business rules. If a table has multiple unique indexes and input could conflict with different rows across different unique keys, clarify which row may be updated. Never use upsert as a substitute for validation.

Affected row counts for INSERT ... ON DUPLICATE KEY UPDATE vary depending on insert/update/no-op and the CLIENT_FOUND_ROWS flag. Never assume affectedRows equal to 1 always means a fresh insert or 2 always means an update. If business logic must distinguish them, use a unique correlation key and verify the outcome explicitly.

## 7. Generated Keys with Batch Inserts

JDBC lets you add multiple commands to a batch:

~~~java
String sql = """
    INSERT INTO customers (email, display_name)
    VALUES (?, ?)
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         sql,
         Statement.RETURN_GENERATED_KEYS
     )) {

    statement.setString(1, "a@example.com");
    statement.setString(2, "Customer A");
    statement.addBatch();

    statement.setString(1, "b@example.com");
    statement.setString(2, "Customer B");
    statement.addBatch();

    int[] counts = statement.executeBatch();

    try (ResultSet keys = statement.getGeneratedKeys()) {
        while (keys.next()) {
            long id = keys.getLong(1);
            System.out.println("Generated id: " + id);
        }
    }
}
~~~

Batching reduces round trips and boosts throughput when loading many rows. However, be cautious when mapping generated keys back to individual input items:

- Connector/J may optimize batches by rewriting multiple INSERTs into a single multi-row INSERT if `rewriteBatchedStatements` is enabled.
- Batch results may contain `SUCCESS_NO_INFO` or `EXECUTE_FAILED` depending on the driver and errors.
- Duplicates, INSERT IGNORE, upserts, or mid-batch failures complicate the relationship between input entries and actual inserted rows.
- How the driver returns generated keys depends on the Connector/J version and how statements are rewritten.

If the entire batch must succeed or fail together, run it inside an explicit transaction using `setAutoCommit(false)`, committing when all commands succeed and rolling back on error. `executeBatch()` alone does not guarantee atomicity across all auto-commit configs or driver batch modes.

If the application requires strict 1-to-1 per-record mapping, test with your exact Connector/J version, URL properties, and MySQL version. Verify key counts, ordering, and partial failure handling. For critical operations, insert row by row and read each key immediately, or use a stable application-generated correlation key to query back results.

Never synthesize ID sequences by taking the first ID and adding row offsets. That is unsafe when auto_increment_increment differs from 1, under concurrent allocations, batch rewrites, or skipped rows.

## 8. Cases Where You Should Not Assume Generated Keys

| Situation | What to watch out for |
|---|---|
| INSERT supplies an explicit ID | Value is not necessarily a new AUTO_INCREMENT-generated ID |
| INSERT IGNORE skips duplicates | Not every input creates a row or yields a corresponding key |
| ON DUPLICATE KEY UPDATE | May update an existing row; must resolve that row's ID |
| Multi-row INSERT | LAST_INSERT_ID() gives only the first ID; do not infer the rest |
| Partial batch failure | Cannot assume every input entry has exactly one key |
| Transaction rollback | Allocated IDs may become gaps; never treat that ID as a persisted record |
| Connection reconnect | Prior session state, including LAST_INSERT_ID(), is no longer guaranteed |
| Connection returned to pool | Never use a new connection to read session state from a returned connection |

Some INSERT statements pass `0` for an AUTO_INCREMENT column, which MySQL interprets as a request to auto-generate an ID unless SQL mode `NO_AUTO_VALUE_ON_ZERO` is enabled. If applications or import files can pass 0, check SQL mode and standardize conventions. Never let ID semantics silently depend on environment settings.

## 9. Connector/J and Connection Pool Configuration

Java connections are usually created from a DataSource or JDBC URL. Minimal URL example:

~~~text
jdbc:mysql://db.example.internal:3306/appdb
~~~

In production, also configure TLS, authentication, timeouts, and connection pooling per system policy. Properties such as `rewriteBatchedStatements` can alter how the driver sends batches, so include them in benchmarks and generated-key tests.

Key principles:

- Each business operation borrows a Connection from the DataSource and returns it with try-with-resources.
- Never store a Connection globally across the application or share it concurrently across threads.
- Never call close and continue using a closed Connection or Statement.
- Never assume two `getConnection()` calls return the same physical session.
- Never use `autoReconnect` to mask connection errors inside transactions; reconnecting opens a new session and does not restore prior transaction/session state.
- Set connection timeout, socket timeout, and pool lifetime per environment, then test server restart/failover scenarios.
- When a transaction errors, roll back before returning the connection to the pool; if connection state is uncertain, let the pool evict it via its standard mechanism.

You can run `SELECT CONNECTION_ID()` in test environments to observe whether two operations ran on the same MySQL session. Never use connection ID as a business key; it is strictly for session diagnostics.

## 10. Common Checks and Troubleshooting

### No generated key returned

Check:

1. Was the statement created with `Statement.RETURN_GENERATED_KEYS`?
2. Did the INSERT actually create a new row, or was it skipped / routed to a duplicate branch?
3. Is the column AUTO_INCREMENT or a generated column whose return the driver supports?
4. Was `getGeneratedKeys()` called on the exact statement that executed the INSERT?
5. Is the Connector/J driver compatible with the running MySQL Server and JDBC API versions?

If no key is returned, never fall back to `SELECT MAX(id)`. Log the SQL operation, affected rows, and driver version, and handle per statement semantics.

### LAST_INSERT_ID() returns a stale value

Common causes are running the query on a different connection, an INSERT that generated no new AUTO_INCREMENT value, or the current operation hitting a duplicate/update. Confirm the Connection was not closed/reacquired between statements and inspect the actual SQL branch executed.

### Wrong ID retrieved under concurrent requests

Common causes are applications using static/shared variables to hold the last ID, calling MAX(id), or sharing a single Connection across threads. Use generated keys from each request's own statement and keep transactions within dedicated Connections.

### Gaps appear in AUTO_INCREMENT

Gaps are normal. Rollbacks, errors, concurrent inserts, and row deletes do not cause MySQL to reuse IDs to guarantee continuity. Never run ALTER TABLE to reset AUTO_INCREMENT just to fill gaps; doing so can cause collisions or break system assumptions.

### Batch returns a different number of keys than input rows

Check per-item batch errors, duplicate handling, rewriteBatchedStatements, and driver version. If exact mapping is required, change the write pattern to use correlation keys or execute individual INSERTs. Never rely on the assumption that key count always equals the number of addBatch calls.

## 11. Implementation Checklist

**During schema design**

- [ ] Choose INT/BIGINT based on growth rate and data retention.
- [ ] Place AUTO_INCREMENT on an appropriate primary or unique key.
- [ ] Ensure foreign key types match referenced keys.
- [ ] Do not use IDs as gapless business sequence numbers.
- [ ] Check auto_increment_increment, auto_increment_offset, and SQL mode if replication/imports may alter them.

**When writing JDBC**

- [ ] Create PreparedStatement with Statement.RETURN_GENERATED_KEYS.
- [ ] Read getGeneratedKeys() from the exact statement that ran the INSERT.
- [ ] Verify ResultSet contains a key and read with the right data type.
- [ ] Use the same Connection for parent-child operations and LAST_INSERT_ID().
- [ ] Commit before publishing the ID as a completed transaction.
- [ ] Roll back when transactions fail and avoid reusing connections with uncertain state.
- [ ] Test batches with the exact Connector/J version and URL properties.

**In operations**

- [ ] Record Connector/J, MySQL, and pool configurations.
- [ ] Monitor insert errors, duplicates, rollbacks, and connection resets.
- [ ] Never use SELECT MAX(id) or global variables to fetch IDs.
- [ ] Maintain idempotency/correlation keys for retries when COMMIT outcome is unknown.
- [ ] Treat AUTO_INCREMENT gaps as normal behavior.

## 12. Key Takeaways

- AUTO_INCREMENT allocates IDs; it does not produce a gapless sequence or reflect commit order.
- Use `Statement.RETURN_GENERATED_KEYS` and `PreparedStatement.getGeneratedKeys()` to retrieve IDs from the current INSERT.
- `LAST_INSERT_ID()` is MySQL session-scoped state; it must execute on the same physical connection as the INSERT.
- Never use `SELECT MAX(id)` because concurrent connections can insert other rows.
- Keep the same Connection for parent-child operations within one transaction; read keys before committing and publish success only after commit.
- Rollbacks do not guarantee reuse of allocated AUTO_INCREMENT values.
- Upserts, IGNORE, multi-row INSERTs, and batches have distinct generated-key semantics; test with your exact driver version.
- Connection pools return logical connections to the pool on close; never assume the next borrow shares the same session.
- Never share a Connection across threads and never reuse a connection after closing it.

Retrieving generated keys accurately is fundamentally about statement and session boundaries. When applications read keys from the inserting statement itself, keep transactions on an explicit Connection, and handle batches according to Connector/J's actual behavior, parent-child key creation and business retries become far more reliable.

## References

- [MySQL Connector/J Developer Guide: Using AUTO_INCREMENT](https://dev.mysql.com/doc/connector-j/en/connector-j-usagenotes-last-insert-id.html)
- [MySQL Connector/J Developer Guide: JDBC API Implementation Notes](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-implementation-notes.html)
- [MySQL Connector/J Developer Guide: Performance Extensions and rewriteBatchedStatements](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-performance-extensions.html)
- [MySQL 8.0 Reference Manual: Information Functions — LAST_INSERT_ID()](https://dev.mysql.com/doc/refman/8.0/en/information-functions.html#function_last-insert-id)
- [MySQL 8.0 Reference Manual: InnoDB AUTO_INCREMENT Handling](https://dev.mysql.com/doc/refman/8.0/en/innodb-auto-increment-handling.html)
- [Java JDBC API: Statement.getGeneratedKeys()](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html#getGeneratedKeys())
