# Batch DML, Standard JDBC Batching, and Handling BatchUpdateException

When a Java application writes many records to Oracle Database, sending individual INSERT, UPDATE, or DELETE statements can generate a large number of network round trips. Each executeUpdate call typically requires sending a command to the database and receiving a response. If an application processes tens of thousands of records, network round-trip and client-side processing costs can become a major share of total execution time.

**JDBC batching** lets you group multiple DML commands into a batch and send them for grouped processing by the database. This is especially effective with PreparedStatement when the same SQL is executed repeatedly with different sets of bind values. The Oracle JDBC driver uses standard JDBC batching to reduce round trips; with PreparedStatement, the driver can use array binding to transmit multiple bind sets in a single exchange.

Batching does not turn all commands into a single SQL statement, does not automatically make the entire transaction succeed atomically, and does not replace commit/rollback management. When a command in a batch fails, JDBC throws BatchUpdateException. The application must inspect update counts, determine which parts executed, decide whether to roll back or continue per transaction policy, and handle retries safely.

This lesson belongs to the **Oracle JDBC** group of Database Engine Relational Oracle. It covers Batch DML, standard JDBC batching, PreparedStatement, batch size, transaction boundaries, BatchUpdateException, update counts, error handling, and Oracle JDBC specifics.

After this lesson, you will be able to:

- Explain Batch DML and the benefit of reducing network round trips.
- Distinguish executeUpdate from addBatch/executeBatch.
- Use Statement and PreparedStatement batching properly.
- Prefer PreparedStatement for Oracle JDBC standard batching.
- Understand why Oracle-specific update batching is deprecated and became a no-op in driver 12.2 and above.
- Check whether a driver supports batch updates.
- Choose appropriate batch sizes and transaction chunk sizes.
- Manage auto-commit, commit, rollback, and savepoints.
- Read update counts and the SUCCESS_NO_INFO, EXECUTE_FAILED constants.
- Handle BatchUpdateException per the JDBC contract.
- Understand stop-on-error behavior of Oracle JDBC standard batching.
- Design retry/idempotency to prevent duplicate inserts or repeated updates.
- Handle constraint errors, invalid data, and connection errors.
- Use executeLargeBatch when long update counts are needed and supported by the driver.
- Compare JDBC batching with set-based SQL, PL/SQL FORALL, and bulk load tools.
- Measure performance and design reproducible hands-on exercises.

> **Scope of examples:** Java examples use standard JDBC and the Oracle Database 19c JDBC driver. Core APIs apply across many JDBC drivers, but performance and error-handling behavior during batches can vary by driver. Verify your actual JDK, Oracle JDBC driver, database version, and transaction configuration before deploying.

## 1. What is Batch DML?

DML consists of data manipulation statements:

- INSERT: add records.
- UPDATE: modify records.
- DELETE: delete records.
- MERGE: conditional insert/update combined.

Batch DML groups multiple DML executions into a single batch.

### 1.1. Executing one statement at a time

~~~java
String sql = "INSERT INTO app_order(order_id, customer_id, amount) VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (OrderRow row : rows) {
        ps.setLong(1, row.orderId());
        ps.setLong(2, row.customerId());
        ps.setBigDecimal(3, row.amount());
        ps.executeUpdate();
    }
}
~~~

If rows has 10,000 items, the application calls executeUpdate 10,000 times. Depending on driver, network, and statement lifecycle, this can produce many round trips.

### 1.2. Grouping commands into a batch

~~~java
String sql = "INSERT INTO app_order(order_id, customer_id, amount) VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (OrderRow row : rows) {
        ps.setLong(1, row.orderId());
        ps.setLong(2, row.customerId());
        ps.setBigDecimal(3, row.amount());
        ps.addBatch();
    }

    int[] updateCounts = ps.executeBatch();
}
~~~

The application still supplies each set of bind values, yet submits the batch for the driver to execute as a group.

### 1.3. Benefits

- Reduces network round trips.
- Reduces per-row JDBC API call overhead.
- Leverages PreparedStatement and bind variables.
- Reduces repeated parse/execute costs.
- Improves throughput for repetitive insert/update/delete workloads.

### 1.4. Batching is not parallel execution

Batching mainly groups sending and executing multiple commands. It does not automatically execute commands in parallel on the database. Never assume batching uses multiple CPU cores or opens multiple database sessions.

### 1.5. Batching does not guarantee transaction atomicity by itself

A batch can have several commands succeed before a later command fails. With auto-commit disabled, those successful changes remain in the active transaction until the application executes COMMIT or ROLLBACK.

Therefore, transaction boundaries must be designed separately from batch boundaries.

## 2. When should JDBC batching be used?

Batching fits when an application repeats the same DML statement across many datasets.

### 2.1. Suitable scenarios

- Importing data from CSV or files.
- Writing thousands of orders.
- Updating statuses on many records.
- Writing business logs in batches.
- Syncing data from external systems.
- Deleting records by a list of keys.
- Loading staging tables with PreparedStatement.

### 2.2. When not to batch?

- Only one or a few DML commands.
- Completely different SQL statements that cannot be grouped sensibly.
- Data can be processed with a single set-based SQL statement.
- A batch holds a transaction open too long or generates excessive locks/undo.
- Commands must return ResultSets or have semantics incompatible with batching.
- Application needs to process each individual result immediately after each command.

### 2.3. Set-based SQL is often better than loop batching

If the data already resides in the database, a single INSERT ... SELECT or MERGE statement can outperform fetching rows into Java and sending them back.

For example, instead of reading thousands of rows and updating one by one:

~~~sql
UPDATE app_order
SET status = 'EXPIRED'
WHERE status = 'PENDING'
  AND created_at < :cutoff_date;
~~~

A single UPDATE processes the entire dataset inside the database, avoiding moving data through the application.

**Selection rule:** If the data is already in Oracle and the operation can be expressed as a single set-based SQL statement, consider that SQL first. JDBC batching fits when the application holds many individual datasets to send to the database.

## 3. How does standard JDBC batching work?

JDBC provides standard APIs to add commands to a batch and execute it.

### 3.1. With Statement

Statement can queue SQL text:

~~~java
try (Statement st = connection.createStatement()) {
    st.addBatch("UPDATE app_order SET status = 'READY' WHERE order_id = 1001");
    st.addBatch("UPDATE app_order SET status = 'READY' WHERE order_id = 1002");
    st.addBatch("DELETE FROM app_order_stage WHERE batch_id = 20");

    int[] counts = st.executeBatch();
}
~~~

This is standard JDBC API, but with the Oracle JDBC driver, generic Statement lacks true batching efficiency comparable to PreparedStatement. Moreover, dynamically concatenated SQL text risks SQL injection and increases parse overhead.

### 3.2. With PreparedStatement

PreparedStatement uses a single fixed SQL statement with bind parameters:

~~~java
String sql =
    "UPDATE app_order SET status = ? WHERE order_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "READY");
    ps.setLong(2, 1001L);
    ps.addBatch();

    ps.setString(1, "READY");
    ps.setLong(2, 1002L);
    ps.addBatch();

    int[] counts = ps.executeBatch();
}
~~~

This is the form recommended by Oracle JDBC for standard update batching. Each addBatch call records one set of bind values for the same SQL.

### 3.3. Standard lifecycle

~~~text
prepareStatement(sql)
        |
        v
set parameter values
        |
        v
addBatch()
        |
        v
set next parameter values
        |
        v
addBatch()
        |
        v
... repeat ...
        |
        v
executeBatch()
        |
        v
inspect update counts
        |
        v
commit or rollback transaction
~~~

### 3.4. Key methods

| API | Purpose |
| --- | --- |
| addBatch() | Adds the current PreparedStatement bind set to the batch |
| addBatch(String sql) | Adds SQL text to a Statement's batch |
| executeBatch() | Submits the batch and returns int[] update counts |
| clearBatch() | Clears pending commands in the batch |
| executeLargeBatch() | Executes the batch and returns long[] update counts if supported by driver |
| getUpdateCounts() | Reads counts of executed commands when BatchUpdateException occurs |
| getLargeUpdateCounts() | Reads long update counts from BatchUpdateException |

### 3.5. Do not call executeUpdate after every addBatch

Calling executeUpdate inside the loop executes each DML individually. To batch commands, call addBatch for each dataset and call executeBatch when the batch size is reached.

## 4. Why use PreparedStatement?

The Oracle JDBC driver optimizes standard batching for PreparedStatement.

### 4.1. Same SQL, multiple bind sets

~~~java
String sql =
    "INSERT INTO employee_stage(employee_id, department_id, salary) VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (EmployeeRow row : employeeRows) {
        ps.setLong(1, row.employeeId());
        ps.setInt(2, row.departmentId());
        ps.setBigDecimal(3, row.salary());
        ps.addBatch();
    }

    ps.executeBatch();
}
~~~

The SQL is prepared once. Each addBatch adds the next set of bind values.

### 4.2. Parameters must be bound for every record

Do not skip a parameter merely because its value matches the previous record. Set every placeholder for each record:

~~~java
ps.setLong(1, row.employeeId());
ps.setInt(2, row.departmentId());
ps.setBigDecimal(3, row.salary());
ps.addBatch();
~~~

If a parameter is not reassigned, the previous value may remain depending on PreparedStatement state. Always setting all parameters prevents writing wrong data.

### 4.3. Use setNull for NULL values

~~~java
if (row.managerId() == null) {
    ps.setNull(4, Types.NUMERIC);
} else {
    ps.setLong(4, row.managerId());
}
~~~

Never pass the string `"NULL"` in place of SQL NULL.

### 4.4. Do not concatenate data into SQL

Avoid:

~~~java
String sql =
    "INSERT INTO app_user(user_name) VALUES ('" + userName + "')";
~~~

Prefer:

~~~java
String sql = "INSERT INTO app_user(user_name) VALUES (?)";
PreparedStatement ps = connection.prepareStatement(sql);
ps.setString(1, userName);
~~~

Bind parameters prevent SQL injection and enable statement reuse.

## 5. Oracle JDBC: standard batching vs. proprietary batching

This is an Oracle-specific detail critical to understand when upgrading drivers.

### 5.1. Legacy Oracle-specific update batching

Oracle previously offered proprietary update batching via Oracle JDBC-specific APIs/properties, such as configuring execute batch size on OraclePreparedStatement.

Oracle update batching was deprecated in Oracle Database 12c Release 1 (12.1). From Oracle Database 12c Release 2 (12.2) onward, this proprietary feature is a no-op: the specified batch size has no effect and applications can fall back to row-by-row execution.

### 5.2. Use standard JDBC batching

Oracle recommends standard JDBC APIs:

- PreparedStatement.addBatch()
- PreparedStatement.executeBatch()
- PreparedStatement.clearBatch()

Do not rely on proprietary setExecuteBatch or legacy APIs to optimize drivers 12.2 and above.

### 5.3. Which statement types get true batching in Oracle JDBC?

Oracle JDBC supports standard batching across Statement, PreparedStatement, and CallableStatement per the JDBC API, but the implementation does not perform true batching for generic Statement and CallableStatement. Significant batching performance gains come primarily from PreparedStatement.

Oracle's implementation supports CallableStatement batching when there are no OUT parameters within documented scope, yet you should not expect the same performance benefits as PreparedStatement.

### 5.4. Comparison table

| Usage | Oracle JDBC 19c |
| --- | --- |
| PreparedStatement + addBatch/executeBatch | Recommended choice; provides true batching |
| Statement + addBatch(String) | Standard API supported, but no true batching like PreparedStatement |
| CallableStatement batching | Limited; no true batching comparable to PreparedStatement |
| Oracle proprietary update batching | Deprecated since 12.1; no-op since 12.2 |

### 5.5. Checking the driver

You can check whether the JDBC driver supports batch updates:

~~~java
DatabaseMetaData meta = connection.getMetaData();

boolean supportsBatch = meta.supportsBatchUpdates();
System.out.println("Batch updates supported: " + supportsBatch);
~~~

This is a general driver capability check. It does not guarantee every Statement type has identical performance or semantics. With Oracle, prefer PreparedStatement.

## 6. Basic batch INSERT example

Example using Java 8+, PreparedStatement, and try-with-resources.

### 6.1. Data model

~~~java
import java.math.BigDecimal;

public class OrderRow {
    private final long orderId;
    private final long customerId;
    private final BigDecimal amount;

    public OrderRow(long orderId, long customerId, BigDecimal amount) {
        this.orderId = orderId;
        this.customerId = customerId;
        this.amount = amount;
    }

    public long getOrderId() {
        return orderId;
    }

    public long getCustomerId() {
        return customerId;
    }

    public BigDecimal getAmount() {
        return amount;
    }
}
~~~

### 6.2. Batch INSERT

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;

public class OrderBatchWriter {
    public int[] insertOrders(
            Connection connection,
            List<OrderRow> rows) throws SQLException {

        String sql =
            "INSERT INTO app_order(order_id, customer_id, amount) VALUES (?, ?, ?)";

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            for (OrderRow row : rows) {
                ps.setLong(1, row.getOrderId());
                ps.setLong(2, row.getCustomerId());
                ps.setBigDecimal(3, row.getAmount());
                ps.addBatch();
            }

            return ps.executeBatch();
        }
    }
}
~~~

This method only executes the batch. Transaction commit/rollback is managed by the caller. Separating transaction ownership out of repositories/helpers prevents unintended commits when called inside a larger transaction.

## 7. Managing transactions during batch DML

A batch may partially succeed before encountering an error. To control outcomes, disable auto-commit and manage transactions explicitly.

### 7.1. Auto-commit

By default, a JDBC Connection usually has auto-commit enabled. With auto-commit enabled, transactions commit automatically per the JDBC driver's statement-completion rules.

For batch DML, never rely on auto-commit if the application needs to roll back statements executed before a batch failure.

### 7.2. Disabling auto-commit

~~~java
connection.setAutoCommit(false);
~~~

After the batch succeeds:

~~~java
connection.commit();
~~~

On error:

~~~java
connection.rollback();
~~~

### 7.3. Complete transaction example

~~~java
import java.sql.BatchUpdateException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;

public class OrderBatchService {
    public void insertOrders(
            Connection connection,
            List<OrderRow> rows) throws SQLException {

        String sql =
            "INSERT INTO app_order(order_id, customer_id, amount) VALUES (?, ?, ?)";

        boolean originalAutoCommit = connection.getAutoCommit();

        try {
            connection.setAutoCommit(false);

            try (PreparedStatement ps = connection.prepareStatement(sql)) {
                for (OrderRow row : rows) {
                    ps.setLong(1, row.getOrderId());
                    ps.setLong(2, row.getCustomerId());
                    ps.setBigDecimal(3, row.getAmount());
                    ps.addBatch();
                }

                int[] counts = ps.executeBatch();
                System.out.println("Batch commands: " + counts.length);
            }

            connection.commit();

        } catch (BatchUpdateException e) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                e.addSuppressed(rollbackError);
            }

            logBatchFailure(e);
            throw e;

        } catch (SQLException e) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                e.addSuppressed(rollbackError);
            }

            throw e;

        } finally {
            connection.setAutoCommit(originalAutoCommit);
        }
    }

    private void logBatchFailure(BatchUpdateException e) {
        System.err.println("Batch failed: " + e.getMessage());
        System.err.println("SQLState: " + e.getSQLState());
        System.err.println("Vendor code: " + e.getErrorCode());
    }
}
~~~

This example assumes the method owns the transaction on the connection. If the connection is already participating in a transaction managed by a service/caller or Spring, do not arbitrarily change auto-commit, commit, or roll back the entire connection inside a repository method.

### 7.4. Rollback affects the current transaction

connection.rollback() rolls back all uncommitted changes in the transaction, not just the commands in the failed batch.

If prior uncommitted DML ran before the batch, it will also be rolled back. Place transaction boundaries properly at the service layer.

### 7.5. Savepoints when partial rollback is needed

If the transaction performed work before the batch and you only want to undo DML from the batch onward:

~~~java
Savepoint beforeBatch = connection.setSavepoint();

try {
    ps.executeBatch();
} catch (BatchUpdateException e) {
    connection.rollback(beforeBatch);
    throw e;
}
~~~

Savepoints only work when auto-commit is disabled and the database/driver supports them. They do not replace clear transaction design.

## 8. Batch size and transaction chunk size

Batch size is the number of commands added before each executeBatch. Transaction chunk size is the number of records committed per transaction. These two values can be the same or different.

### 8.1. Batch size too small

If a batch has only one or two commands, round-trip savings may be negligible.

### 8.2. Batch size too large

Very large batches can:

- Increase memory consumption on the Java client and JDBC driver.
- Increase buffer sizes.
- Increase latency before the batch is sent.
- Increase the amount of work executed at once.
- Make failures harder to isolate and retry.
- Pressure undo, redo, locks, and transaction duration if commits are too infrequent.

### 8.3. Oracle recommends batch sizes around 100 or less

Oracle JDBC 19c coding tips recommend keeping batch sizes around 100 or fewer. Larger batches typically yield little or no extra improvement and can degrade performance due to client resources required to process the batch.

This is a starting baseline, not a hard ceiling. Measure on your real workload, schema, network, and driver.

### 8.4. Start with empirical testing

You can benchmark:

| Batch size | Purpose |
| ---: | --- |
| 10 | Small baseline |
| 25 | Test round-trip reduction |
| 50 | Medium batch |
| 100 | Oracle's recommended starting point |
| 200 | Test whether larger batches help |

Do not choose batch size solely by row count. Row width, LOBs, network, driver, and transaction behavior all matter.

### 8.5. Chunk processing example

~~~java
private static final int BATCH_SIZE = 100;

public void insertInChunks(
        Connection connection,
        List<OrderRow> rows) throws SQLException {

    String sql =
        "INSERT INTO app_order(order_id, customer_id, amount) VALUES (?, ?, ?)";

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        int pending = 0;

        for (OrderRow row : rows) {
            ps.setLong(1, row.getOrderId());
            ps.setLong(2, row.getCustomerId());
            ps.setBigDecimal(3, row.getAmount());
            ps.addBatch();
            pending++;

            if (pending == BATCH_SIZE) {
                ps.executeBatch();
                connection.commit();
                ps.clearBatch();
                pending = 0;
            }
        }

        if (pending > 0) {
            ps.executeBatch();
            connection.commit();
            ps.clearBatch();
        }
    }
}
~~~

This snippet requires auto-commit to be disabled and the method to own transaction commits. In real applications, add error rollbacks and avoid committing inside repositories when transactions belong to the service layer.

### 8.6. Batch size vs. transaction size

Example:

~~~text
Transaction of 1,000 rows
    Batch 1: 100 rows -> executeBatch
    Batch 2: 100 rows -> executeBatch
    ...
    Batch 10: 100 rows -> executeBatch
    COMMIT
~~~

Ten executeBatch calls still belong to the same transaction if no commit occurs between batches.

Or:

~~~text
Chunk 1: 1,000 rows -> 10 batches -> COMMIT
Chunk 2: 1,000 rows -> 10 batches -> COMMIT
Chunk 3: 1,000 rows -> 10 batches -> COMMIT
~~~

Committing per chunk keeps transactions shorter, though the job is no longer atomic across the entire dataset. Design restart/checkpointing accordingly.

## 9. Update counts after executeBatch

executeBatch returns an int[]; each element corresponds to a command in the order of addBatch calls.

### 9.1. Non-negative values

An integer of 0 or greater represents the number of rows affected by that command.

Example:

~~~java
int[] counts = ps.executeBatch();

for (int count : counts) {
    System.out.println("Rows affected: " + count);
}
~~~

UPDATE can return 0 if WHERE matches no rows. This is not necessarily a SQL error.

### 9.2. SUCCESS_NO_INFO

Statement.SUCCESS_NO_INFO has the value -2. It indicates the command succeeded, yet the driver does not know how many rows were affected.

Never interpret -2 as zero rows.

### 9.3. EXECUTE_FAILED

Statement.EXECUTE_FAILED has the value -3. It indicates a command failed in cases where the driver continues processing subsequent commands after an error.

A driver that stops on error may return only counts for successful commands prior to the failure, with no EXECUTE_FAILED entry for the failed command.

### 9.4. Update counts table

| Value | Meaning |
| ---: | --- |
| 0 or positive integer | Number of rows affected |
| -2 / SUCCESS_NO_INFO | Succeeded, row count unknown |
| -3 / EXECUTE_FAILED | Command failed; appears only if driver continues after error |

### 9.5. Do not assume update count equals input row count

For UPDATE or DELETE, a single input record may affect:

- 0 rows: no matching row.
- 1 row: exactly one row.
- Multiple rows: WHERE matched multiple rows.
- SUCCESS_NO_INFO: driver does not supply count.

If business rules require exactly one row, check the count and apply an appropriate policy.

## 10. What is BatchUpdateException?

BatchUpdateException is a subclass of SQLException. JDBC throws this exception when a command in a batch fails to execute successfully.

### 10.1. Available information

- getMessage(): error message.
- getSQLState(): SQLState.
- getErrorCode(): vendor-specific error code, e.g., Oracle error code.
- getUpdateCounts(): int update counts.
- getLargeUpdateCounts(): long update counts.
- getNextException(): next SQLException in the exception chain.
- getCause(): root cause if present.

### 10.2. JDBC permits two behaviors after an error

Under the JDBC contract, a driver may:

1. Stop processing immediately upon encountering a failing command.
2. Continue processing remaining commands after a command fails.

Behavior must be consistent within a given DBMS/driver implementation.

If the driver stops:

- Update counts contain results for commands that succeeded prior to the error.
- The array is usually shorter than the original batch.

If the driver continues:

- The array has one element per command.
- Failing commands may be marked EXECUTE_FAILED.
- Successful commands with unknown row counts may be SUCCESS_NO_INFO.

### 10.3. Oracle JDBC standard batching behavior

Per Oracle Database 19c JDBC Developer's Guide for Oracle JDBC standard batching:

- If an operation in the batch errors or attempts to return a ResultSet during executeBatch, processing stops.
- BatchUpdateException is thrown.
- Update counts contain the successful executions before the error.
- If a batch has 5 records and the 4th fails, update counts has 3 elements representing the first 3 records that executed successfully.
- Commands after the failing record are not executed in that batch.

This is Oracle JDBC-specific behavior. Portable code should still inspect update counts and not hardcode an assumption that every JDBC driver stops like Oracle.

### 10.4. Update counts do not mean data is committed

Update counts only reflect commands executed within the transaction. With auto-commit disabled, changes can still be rolled back. Only after a successful commit are changes permanently committed.

## 11. Reading BatchUpdateException properly

### 11.1. Exception-catching example

~~~java
try {
    int[] counts = ps.executeBatch();
    System.out.println("Success commands: " + counts.length);

} catch (BatchUpdateException e) {
    int[] counts = e.getUpdateCounts();

    System.err.println("Batch failed: " + e.getMessage());
    System.err.println("SQLState: " + e.getSQLState());
    System.err.println("Oracle/vendor code: " + e.getErrorCode());
    System.err.println("Reported counts: " + counts.length);

    for (int i = 0; i < counts.length; i++) {
        System.err.println("Command " + i + " count=" + counts[i]);
    }

    throw e;
}
~~~

### 11.2. Handling drivers that either continue or stop

~~~java
int[] counts = e.getUpdateCounts();

for (int i = 0; i < counts.length; i++) {
    int count = counts[i];

    if (count == Statement.EXECUTE_FAILED) {
        System.err.println("Command " + i + " failed");
    } else if (count == Statement.SUCCESS_NO_INFO) {
        System.out.println("Command " + i + " succeeded; row count unknown");
    } else {
        System.out.println(
            "Command " + i + " affected " + count + " rows"
        );
    }
}
~~~

If the driver stops, the array may contain only the prefix of successful commands. Do not assume the last element in the array is the failing command; it may be the last successful command before the failing one.

### 11.3. Walking the exception chain

~~~java
SQLException next = e.getNextException();

while (next != null) {
    System.err.println("Chained SQL error: " + next.getMessage());
    System.err.println("SQLState: " + next.getSQLState());
    System.err.println("Vendor code: " + next.getErrorCode());
    next = next.getNextException();
}
~~~

Oracle errors typically carry vendor codes, for example:

- ORA-00001: unique constraint violated.
- ORA-01400: cannot insert NULL.
- ORA-02291: parent key not found.
- ORA-02292: child record found.
- ORA-12899: value too large for column.

Inspect both the message and the exception chain to find the true cause.

## 12. Mapping update counts to input records

When a batch is built from a List, the application often needs to know which input records executed.

### 12.1. Preserving input order

~~~java
List<OrderRow> batchRows = new ArrayList<>();

for (OrderRow row : inputRows) {
    ps.setLong(1, row.getOrderId());
    ps.setLong(2, row.getCustomerId());
    ps.setBigDecimal(3, row.getAmount());
    ps.addBatch();
    batchRows.add(row);
}
~~~

### 12.2. Mapping when executeBatch succeeds

On success, update counts follow the order of addBatch calls:

~~~java
int[] counts = ps.executeBatch();

for (int i = 0; i < counts.length; i++) {
    OrderRow row = batchRows.get(i);
    System.out.println(
        "orderId=" + row.getOrderId() +
        ", updateCount=" + counts[i]
    );
}
~~~

### 12.3. Mapping when Oracle driver stops on error

With Oracle JDBC behavior, if the exception counts have 3 elements, the first 3 commands executed successfully; the next command in the batch is the failing position in addBatch order. Subsequent commands were not executed.

Example 5-record batch:

| Input index | Order ID | Outcome |
| ---: | ---: | --- |
| 0 | 1001 | Succeeded |
| 1 | 1002 | Succeeded |
| 2 | 1003 | Succeeded |
| 3 | 1004 | Failed |
| 4 | 1005 | Not run |

In this case, Oracle JDBC's getUpdateCounts() may contain three elements corresponding to 1001, 1002, and 1003.

Do not apply this assumption to other drivers without reading that driver's documentation.

### 12.4. Do not use counts to blindly decide on commit

Some commands having executed does not mean the transaction should partially commit. Commit/rollback decisions must follow business atomicity:

- If the batch is one atomic business unit, roll back the entire transaction.
- If each record is independent and partial success is acceptable, commit per chunk and record checkpoints.
- If valid records must continue, isolate the failing record for separate handling after recovering the transaction per policy.

## 13. Error-handling pattern with rollback

This pattern fits when the entire batch is a single transaction unit: if any command fails, roll back all uncommitted changes.

~~~java
import java.sql.BatchUpdateException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;

public class AtomicBatchWriter {
    public void write(
            Connection connection,
            List<OrderRow> rows) throws SQLException {

        String sql =
            "INSERT INTO app_order(order_id, customer_id, amount) VALUES (?, ?, ?)";

        boolean originalAutoCommit = connection.getAutoCommit();

        try {
            connection.setAutoCommit(false);

            try (PreparedStatement ps = connection.prepareStatement(sql)) {
                for (OrderRow row : rows) {
                    ps.setLong(1, row.getOrderId());
                    ps.setLong(2, row.getCustomerId());
                    ps.setBigDecimal(3, row.getAmount());
                    ps.addBatch();
                }

                int[] counts = ps.executeBatch();
                logCounts(counts);
            }

            connection.commit();

        } catch (BatchUpdateException e) {
            rollbackPreservingOriginal(connection, e);
            logBatchException(e);
            throw e;

        } catch (SQLException e) {
            rollbackPreservingOriginal(connection, e);
            throw e;

        } finally {
            connection.setAutoCommit(originalAutoCommit);
        }
    }

    private void rollbackPreservingOriginal(
            Connection connection,
            SQLException original) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            original.addSuppressed(rollbackError);
        }
    }

    private void logCounts(int[] counts) {
        for (int i = 0; i < counts.length; i++) {
            System.out.println("index=" + i + ", count=" + counts[i]);
        }
    }

    private void logBatchException(BatchUpdateException e) {
        System.err.println(e.getMessage());
        System.err.println("SQLState=" + e.getSQLState());
        System.err.println("VendorCode=" + e.getErrorCode());

        int[] counts = e.getUpdateCounts();
        System.err.println("Successful/reported commands=" + counts.length);
    }
}
~~~

This is a transaction-owning service example. In systems with a transaction manager or Spring-managed transactions, do not set auto-commit or call commit/rollback directly inside a repository.

## 14. Partial success and retries

A batch can partially execute before failing. This is where applications need an explicit retry policy.

### 14.1. Never blindly retry the whole batch

Suppose:

- Batch has 100 records.
- 35 records already executed.
- The 36th record hits a unique constraint violation.
- The remaining 64 records have not executed on Oracle JDBC.

If the application resubmits all 100 records without rolling back the transaction or ensuring idempotency, the first records may be inserted twice.

### 14.2. If rolling back the whole transaction

When auto-commit is off and rollback succeeds:

- DML executed in the current transaction is rolled back.
- Bad data can be fixed and the transaction retried.
- Previously committed transactions (if using chunk commits) still remain.

### 14.3. If committing per chunk

Example: 10,000 rows, chunk 100:

~~~text
Chunk 1 -> execute -> commit
Chunk 2 -> execute -> commit
Chunk 3 -> error -> rollback current chunk
Chunk 4..N -> not yet run
~~~

Here the 200 rows from the first two chunks are already committed. Retries must resume from a checkpoint after chunk 2 or rely on upsert/idempotency mechanisms.

### 14.4. Idempotency

An idempotent operation can be re-executed without producing wrong results or duplicates.

Supporting techniques:

- Unique business key with a unique constraint.
- Import batch ID and source record ID.
- Staging table with processing status.
- MERGE by business key.
- Committed checkpoints.
- Transaction log recording which batches/chunks completed.

### 14.5. Never infer commit from update counts

If the connection drops right after the client sends COMMIT, the client may not know whether the database committed. Prior update counts do not resolve transaction outcome ambiguity.

When retrying after a connection error, reconcile transaction/business keys or checkpoints in the database. Never blindly resend data.

## 15. Savepoints and isolating single failing records

If business requirements allow keeping work before the batch while rolling back only the current batch, use a savepoint.

### 15.1. Example

~~~java
Savepoint beforeBatch = connection.setSavepoint();

try {
    ps.executeBatch();
    connection.releaseSavepoint(beforeBatch);
} catch (BatchUpdateException e) {
    connection.rollback(beforeBatch);
    throw e;
}
~~~

Rolling back to the savepoint undoes changes since the savepoint while keeping prior work in the same transaction.

### 15.2. Isolating failing records

Another strategy:

1. Attempt the batch.
2. On error, roll back the batch/chunk.
3. Identify the failing record using update counts and the Oracle error.
4. Write the failing record to a reject table or file.
5. Re-run the valid records in a new batch.

Do not automatically apply this strategy when the error is not a data error. Network errors, deadlocks, tablespace full, or database unavailability should not be classified as single-record data errors.

### 15.3. Smaller batches to isolate errors

If input data may contain occasional bad records, smaller batch sizes narrow the scope to investigate. The trade-off is more executeBatch calls and network round trips.

A binary-split batch strategy can locate bad records in a large set, provided transactions and DML idempotency are carefully controlled.

## 16. Using executeLargeBatch

JDBC 4.2 added executeLargeBatch and getLargeUpdateCounts to return long update counts.

### 16.1. When is it needed?

If a command may affect more than Integer.MAX_VALUE rows, int update counts cannot represent the count accurately.

### 16.2. Example

~~~java
long[] counts = ps.executeLargeBatch();

for (long count : counts) {
    System.out.println("Rows affected: " + count);
}
~~~

### 16.3. Exception handling

~~~java
try {
    long[] counts = ps.executeLargeBatch();
} catch (BatchUpdateException e) {
    long[] counts = e.getLargeUpdateCounts();
    System.err.println("Reported commands: " + counts.length);
}
~~~

### 16.4. Checking driver support

executeLargeBatch is a modern JDBC API method, but the driver/version must support it appropriately. If an application uses an older Oracle JDBC driver, verify JDBC compliance and driver documentation before adopting this API.

## 17. Batch INSERT with Oracle sequences

Oracle commonly uses sequences to generate primary keys.

### 17.1. Using a sequence in SQL

~~~java
String sql =
    "INSERT INTO app_order(order_id, customer_id, amount) " +
    "VALUES (app_order_seq.NEXTVAL, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (OrderRow row : rows) {
        ps.setLong(1, row.getCustomerId());
        ps.setBigDecimal(2, row.getAmount());
        ps.addBatch();
    }

    ps.executeBatch();
}
~~~

### 17.2. Sequences can have gaps

Sequences do not guarantee contiguous gap-free values. Rollbacks, caching, instance failures, or concurrent sessions can skip sequence values.

Never use a sequence to generate business sequence numbers that must be strictly contiguous.

### 17.3. Need to know generated IDs?

If the application needs to map generated IDs back to each input row:

- Allocate sequence values before addBatch.
- Use a separate key generation mechanism.
- Store a source key alongside the ID in a staging table.
- Verify batch generated-keys support for your Oracle JDBC driver/version.

Do not assume every driver returns batch generated keys with identical semantics. Test your specific driver before designing logic dependent on generated key ordering.

## 18. Batch UPDATE and DELETE

### 18.1. Batch UPDATE

~~~java
String sql =
    "UPDATE app_order SET status = ? WHERE order_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (OrderStatusChange change : changes) {
        ps.setString(1, change.status());
        ps.setLong(2, change.orderId());
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
}
~~~

### 18.2. Batch DELETE

~~~java
String sql = "DELETE FROM app_order_stage WHERE stage_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (Long stageId : stageIds) {
        ps.setLong(1, stageId);
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
}
~~~

### 18.3. UPDATE count of 0

If an update count is 0, possible reasons include:

- The record does not exist.
- The WHERE condition did not match.
- The record was already processed earlier.

This can be a valid outcome or a business error depending on requirements. The application must define it explicitly.

### 18.4. Optimistic locking

A version column can be used:

~~~sql
UPDATE app_order
SET status = ?, version_no = version_no + 1
WHERE order_id = ?
  AND version_no = ?
~~~

If the update count is 0, the data changed concurrently or the record does not exist. Batching does not bypass optimistic locking; it simply groups sending the commands.

## 19. Batching and Oracle constraints

Batch DML still obeys database constraints, triggers, indexes, and transaction rules.

### 19.1. Constraints

Common errors:

- Unique constraints.
- Foreign keys.
- NOT NULL.
- CHECK constraints.
- Data length/precision overflow.

Batching does not skip database validation.

### 19.2. Triggers

Triggers still fire per DML row/statement depending on trigger type. Batching does not mean a trigger fires only once for the whole batch.

### 19.3. Indexes

Every INSERT/UPDATE/DELETE still maintains related indexes. When loading very large data volumes, index maintenance can take longer than round-trip overhead.

### 19.4. Undo and redo

DML still generates undo/redo per database semantics. Batching does not make DML NOLOGGING and does not eliminate transaction logging.

### 19.5. Locks

If commits are too infrequent, row locks are held longer. This can block other transactions and cause contention.

## 20. Batch DML and bulk processing in Oracle

JDBC batching is only one of several ways to load data.

### 20.1. JDBC standard batching

Fits when:

- Data originates from a Java application.
- The same SQL executes with many bind sets.
- Reducing network round trips is desired.
- Transaction control is needed from Java.

### 20.2. Set-based SQL

Fits when data already resides in the database:

~~~sql
INSERT INTO app_order_archive(order_id, customer_id, amount)
SELECT order_id, customer_id, amount
FROM app_order
WHERE created_at < :cutoff_date;
~~~

The database processes the dataset in place, avoiding moving rows through Java.

### 20.3. PL/SQL FORALL

FORALL is bulk DML in PL/SQL. It lets PL/SQL bind multiple collection elements to one DML statement, reducing context switches between the PL/SQL and SQL engines.

Conceptual example:

~~~sql
DECLARE
    TYPE t_order_ids IS TABLE OF app_order.order_id%TYPE;
    l_ids t_order_ids := t_order_ids(1001, 1002, 1003);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT
        UPDATE app_order
        SET status = 'READY'
        WHERE order_id = l_ids(i);
END;
/
~~~

FORALL fits when logic and collections already live in PL/SQL. It is not a JDBC API and does not replace transaction boundaries.

### 20.4. SAVE EXCEPTIONS in FORALL

PL/SQL FORALL offers SAVE EXCEPTIONS to continue processing remaining iterations and record errors in SQL%BULK_EXCEPTIONS. This is a PL/SQL-specific mechanism, distinct from JDBC's BatchUpdateException.

### 20.5. SQL*Loader and external tables

For large files and millions of records, SQL*Loader or external tables can fit better than JDBC batching. They provide dedicated loading mechanisms, potential direct-path support, and efficient file processing.

### 20.6. Comparison

| Method | Data source | Strengths |
| --- | --- | --- |
| JDBC batching | Java application | Reduces round trips when sending many bind sets |
| Set-based SQL | Already inside database | Processes data directly in the database |
| PL/SQL FORALL | PL/SQL collections | Reduces context switches for bulk DML |
| SQL*Loader | Files outside database | Purpose-built bulk loading |
| External tables | Files read by database as tables | Combines SQL with file data |

## 21. Performance and how to measure it

Do not assume batching is faster solely because executeBatch is used. Measure on equivalent workloads.

### 21.1. Metrics to record

- Total input rows.
- Successfully committed rows.
- Batch size.
- Transaction chunk size.
- Total elapsed time.
- Rows per second.
- Number of executeBatch calls.
- Round-trip count if measurable.
- Client CPU and memory.
- Database CPU.
- Logical/physical reads.
- Redo/undo generation.
- Lock waits.
- Error and retry counts.

### 21.2. Comparing executeUpdate and executeBatch

Keep identical:

- Dataset.
- SQL.
- Bind values.
- Indexes/constraints.
- Transaction policy.
- Commit frequency.
- Network path.

Change only how DML is sent so results remain comparable.

### 21.3. Measuring elapsed time in Java

~~~java
long start = System.nanoTime();

int[] counts = ps.executeBatch();

long elapsedNanos = System.nanoTime() - start;
double elapsedMillis = elapsedNanos / 1_000_000.0;

System.out.println("Batch elapsed ms: " + elapsedMillis);
System.out.println("Commands: " + counts.length);
~~~

To measure the entire job, start the timer before reading input and stop after the final commit.

### 21.4. Warm-up and multiple runs

A single run can be skewed by:

- Cold caches.
- JIT compilation.
- Network fluctuations.
- Concurrent workloads.
- Parse/statement caches.
- Storage caches.

Run multiple iterations, separate warm-up from steady state, and report medians/percentiles as needed.

### 21.5. Do not increase batch size indefinitely

Larger batch sizes can reduce executeBatch calls while increasing memory and latency before sending. Measure throughput and memory together.

## 22. Troubleshooting

| Error/symptom | Possible cause | Resolution |
| --- | --- | --- |
| Batch no faster than executeUpdate | Using Statement or CallableStatement on Oracle | Use PreparedStatement standard batching |
| Batch size configured but still row-by-row | Using proprietary Oracle batching on driver 12.2+ | Switch to addBatch/executeBatch |
| BatchUpdateException | A command failed or tried to return a ResultSet | Read message, vendor code, update counts, and exception chain |
| ORA-00001 | Duplicate key in batch | Check input keys, unique constraints, and retry policy |
| ORA-01400 | NULL value for NOT NULL column | Validate input or set valid value |
| ORA-02291 | Foreign key parent not found | Ensure parent exists or fix load order |
| ORA-12899 | Value too long | Check length/encoding and schema |
| ORA-00060 | Deadlock | Check update order, transaction concurrency, and retry with backoff |
| OutOfMemoryError | Batch too large or retaining too much input/results | Reduce batch/chunk size and stream data |
| Undo tablespace pressure | Transactions too long or commits too infrequent | Choose an appropriate transaction chunk size |
| Lock contention | Multiple transactions updating the same rows | Shorten transaction duration, standardize lock ordering |
| Retries create duplicate rows | Missing idempotency or unclear transaction outcome | Use business keys/checkpoints and reconcile before retrying |
| Counts array shorter than batch | Driver stopped on failing command | Identify successful prefix and failure position per driver behavior |
| EXECUTE_FAILED appears | Driver continued after failing command | Inspect each element and handle per JDBC contract |
| executeLargeBatch fails to work | Unsupported driver/JDBC version | Check driver version and JDBC capabilities |

## 23. Common misconceptions

| Misconception | Reality |
| --- | --- |
| A batch is a single SQL statement | A batch is a group of commands sent/executed via batching APIs |
| Batches always run in parallel | No; batching mainly reduces round trips and overhead |
| A batch always commits all or nothing | No; commands can partially execute prior to an error |
| executeBatch auto-commits | Transaction behavior depends on auto-commit and driver |
| SUCCESS_NO_INFO means 0 rows | It means succeeded with an unknown row count |
| EXECUTE_FAILED always appears on error | Appears only when the driver continues processing after errors |
| BatchUpdateException always has counts for the whole batch | The array may hold only the prefix of successful commands |
| Oracle JDBC continues after errors like every driver | Oracle standard batching stops at the failing command per 19c docs |
| Update counts mean data is committed | Counts only confirm command execution; commit is separate |
| You can retry the entire batch after an error | Risks duplicates if earlier parts committed or outcome is unknown |
| Bigger batch size is always faster | Overly large batches can hurt performance and spike memory |
| Statement batching performs like PreparedStatement on Oracle | Oracle true batching is primarily for PreparedStatement |
| Oracle proprietary batching still works in new drivers | It is a no-op since 12.2 |
| JDBC batching replaces FORALL | The two mechanisms operate at different layers |
| Batch DML bypasses triggers/constraints | All database rules still apply |

## 24. Batch DML implementation checklist

**SQL design**

- Does the DML share a single structure suited for PreparedStatement?
- Could a single set-based SQL statement replace the loop?
- Does the WHERE clause have appropriate indexes?
- Are all bind parameters set completely for every record?
- Are generated keys needed?

**Driver and API**

- Is the Oracle JDBC driver version identified?
- Is standard addBatch/executeBatch used?
- Is proprietary Oracle update batching avoided?
- Was supportsBatchUpdates checked?
- Is PreparedStatement used for performance?

**Batch and transactions**

- Has batch size been benchmarked?
- Has transaction chunk size been determined?
- Is auto-commit managed properly?
- Who owns commit/rollback?
- Does BatchUpdateException trigger rollback?
- Are checkpoints saved when committing in chunks?

**Error handling**

- Are getUpdateCounts/getLargeUpdateCounts read?
- Are SUCCESS_NO_INFO and EXECUTE_FAILED handled?
- Are SQLState, vendor code, and nextException logged?
- Are counts mapped back to input order?
- Are retries idempotent?
- Are unknown commit outcomes handled?

**Operations**

- Are batch ID, chunk ID, and row counts logged?
- Are elapsed time/throughput metrics collected?
- Are memory and input buffering bounded?
- Are undo/redo/locks monitored?
- Were constraint errors and network errors tested?

## 25. Comprehensive hands-on lab

This lab creates a staging table, inserts multiple rows via PreparedStatement batching, triggers a unique constraint error, and reads BatchUpdateException.

### Step 1 — Create the table

~~~sql
CREATE TABLE jdbc_batch_lab (
    id          NUMBER PRIMARY KEY,
    description VARCHAR2(100) NOT NULL,
    amount      NUMBER(12,2)
);
~~~

### Step 2 — Create Java data

~~~java
List<LabRow> rows = new ArrayList<>();

for (int i = 1; i <= 250; i++) {
    rows.add(new LabRow(
        i,
        "row-" + i,
        new BigDecimal(i).setScale(2)
    ));
}
~~~

### Step 3 — Insert using PreparedStatement

~~~java
String sql =
    "INSERT INTO jdbc_batch_lab(id, description, amount) VALUES (?, ?, ?)";

connection.setAutoCommit(false);

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    int pending = 0;

    for (LabRow row : rows) {
        ps.setInt(1, row.id());
        ps.setString(2, row.description());
        ps.setBigDecimal(3, row.amount());
        ps.addBatch();
        pending++;

        if (pending == 100) {
            int[] counts = ps.executeBatch();
            System.out.println("Executed commands: " + counts.length);
            ps.clearBatch();
            pending = 0;
        }
    }

    if (pending > 0) {
        int[] counts = ps.executeBatch();
        System.out.println("Final commands: " + counts.length);
        ps.clearBatch();
    }

    connection.commit();

} catch (BatchUpdateException e) {
    connection.rollback();

    System.err.println("Batch error: " + e.getMessage());
    System.err.println("Oracle error code: " + e.getErrorCode());

    int[] counts = e.getUpdateCounts();
    System.err.println("Reported update counts: " + counts.length);

    throw e;
}
~~~

The lab above demonstrates a single transaction composed of multiple batches. If any batch fails, the entire uncommitted transaction rolls back.

### Step 4 — Verify data

~~~sql
SELECT COUNT(*) AS total_rows
FROM jdbc_batch_lab;

SELECT MIN(id), MAX(id)
FROM jdbc_batch_lab;
~~~

### Step 5 — Test duplicate key

Add an input row with an already-existing ID:

~~~java
rows.add(new LabRow(
    1,
    "duplicate-row",
    new BigDecimal("999.00")
));
~~~

Run the batch and observe BatchUpdateException.

### Step 6 — Read update counts

~~~java
catch (BatchUpdateException e) {
    int[] counts = e.getUpdateCounts();

    for (int i = 0; i < counts.length; i++) {
        int count = counts[i];

        if (count == Statement.EXECUTE_FAILED) {
            System.out.println("Failed command at index " + i);
        } else if (count == Statement.SUCCESS_NO_INFO) {
            System.out.println("Success, count unknown at index " + i);
        } else {
            System.out.println("Index " + i + " affected " + count);
        }
    }
}
~~~

With Oracle JDBC, inspect the length of counts to determine how many commands succeeded before the failing command per driver behavior.

### Step 7 — Compare batch sizes

Re-run the lab with batch sizes:

- 10.
- 25.
- 50.
- 100.
- 200.

Record elapsed time, throughput, and memory. Use identical data and transaction policy.

### Step 8 — Compare executeUpdate

Write a loop version calling executeUpdate with the same SQL and bind values. Compare timing against standard batching.

### Step 9 — Verify rollback

After intentionally triggering an error inside a transaction:

~~~sql
SELECT COUNT(*)
FROM jdbc_batch_lab;
~~~

Confirm that rollback undid changes from the uncommitted transaction.

## 26. Self-check questions

1. What is Batch DML?
2. Which costs does batching reduce?
3. Do batches automatically run in parallel?
4. Why does PreparedStatement suit Oracle JDBC batching?
5. How do addBatch and executeBatch differ?
6. What is clearBatch used for?
7. What is the status of Oracle-specific update batching since 12.2?
8. Does Oracle JDBC provide true batching for Statement and CallableStatement?
9. What does supportsBatchUpdates check?
10. How should auto-commit be managed when batch rollback is required?
11. How does batch size differ from transaction chunk size?
12. Why does Oracle recommend a batch size around 100 or less?
13. Is an update count of 0 always an error?
14. What does SUCCESS_NO_INFO mean?
15. Under what circumstances does EXECUTE_FAILED appear?
16. Which class is BatchUpdateException a subclass of?
17. Must a JDBC driver stop on a failing command?
18. How does Oracle JDBC standard batching handle failing commands?
19. What information does getUpdateCounts return?
20. Why do counts not prove a transaction committed?
21. When rolling back a connection, which DML statements are rolled back?
22. How do savepoints help when a batch fails?
23. Why should you never blindly retry an entire batch?
24. How does idempotency help batch imports?
25. When is executeLargeBatch needed?
26. Do sequences guarantee contiguous values?
27. Does Batch DML bypass triggers and constraints?
28. When is set-based SQL better than JDBC batching?
29. How does FORALL differ from JDBC batching?
30. Which metrics should be measured when tuning batch size?

**Suggested answers:**

1. Grouping multiple DML commands and executing them in a batch.
2. Network round trips and repeated JDBC/parse overhead.
3. Not automatically; batching primarily groups submission and execution.
4. The same SQL is reused across multiple bind sets and Oracle provides true batching for PreparedStatement.
5. addBatch queues a command; executeBatch sends and executes the group.
6. Clears pending commands queued in the batch.
7. Proprietary batching is a no-op; use standard JDBC batching.
8. No true batching like PreparedStatement in the Oracle driver.
9. Whether the driver supports JDBC batch updates.
10. Disable auto-commit and manage commit/rollback explicitly.
11. Batch size is commands per executeBatch; transaction chunk size is rows per transaction commit.
12. Larger batches yield diminishing returns and can increase client resource usage.
13. No; WHERE might match zero rows.
14. The command succeeded, but the row count is unknown.
15. When the driver continues processing after errors and marks failed commands.
16. SQLException.
17. No; drivers may stop or continue per the JDBC contract.
18. Stops at the failing operation and counts contain the preceding successful commands.
19. Update counts of successfully executed commands or statuses per driver behavior.
20. Counts reflect execution within the transaction; commit is a separate step.
21. All uncommitted changes in the current transaction.
22. Rolls back part of the transaction back to the savepoint.
23. Risks duplicating or re-executing already-committed DML.
24. Allows retries without causing duplicate side effects.
25. When update counts may exceed Integer.MAX_VALUE and the driver supports it.
26. No; rollbacks, caching, and concurrent sessions can leave gaps.
27. No; database constraints and triggers still apply.
28. When data already resides in the database and can be processed by a single SQL statement.
29. FORALL is bulk DML inside PL/SQL; JDBC batching sends DML from Java.
30. Elapsed time, throughput, batch size, memory, round trips, CPU, redo/undo, locks, and error rate.

## Oracle and JDBC reference documentation

- [Oracle Database 19c JDBC Developer's Guide — Performance Extensions / Update Batching](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/performance-extensions.html): standard batching, proprietary batching, Oracle driver behavior, and error handling.
- [Oracle Database 19c JDBC Developer's Guide — JDBC Coding Tips](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/JDBC-coding-tips.html): recommendation for batch sizes around 100 or fewer.
- [Oracle Database 19c JDBC Developer's Guide — JDBC Batching Error Handling](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/performance-extensions.html): BatchUpdateException and update counts in Oracle JDBC.
- [Java SE 21 API — BatchUpdateException](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/BatchUpdateException.html): getUpdateCounts, getLargeUpdateCounts, and stop/continue driver behavior.
- [Java SE 21 API — Statement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html): addBatch, executeBatch, executeLargeBatch, SUCCESS_NO_INFO, and EXECUTE_FAILED.
- [Oracle Database 19c PL/SQL Language Reference — FORALL Statement](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/FORALL-statement.html): bulk DML in PL/SQL.

**Principle to remember:** With Oracle JDBC, use PreparedStatement and standard addBatch/executeBatch to reduce network round trips. Start testing around a batch size of 100 or less and benchmark. Disable auto-commit when rollback control is needed. BatchUpdateException provides update counts, yet does not by itself decide whether a transaction commits. JDBC drivers generally may stop or continue after an error; Oracle JDBC standard batching stops at the failing command and returns counts for the preceding successful commands. Design transaction boundaries, idempotency, and retry policies before bringing batch DML into production.
