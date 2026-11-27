# Affected Rows vs. Matched Rows Semantics and Client Option Effects

When running an `UPDATE` statement, MySQL may match many rows satisfying the `WHERE` condition yet actually modify only a subset of them. For instance, a statement matches 5 orders already in `PAID` status, and setting status to `PAID` again makes no data change. If an application receives only a single number without understanding how it is calculated, it might mistakenly conclude that no orders were found, when in reality 5 rows matched the condition.

MySQL distinguishes between found/matched rows (*matched/found rows*) and rows that actually changed (*changed rows*). The number returned to the client also depends on the connection flag `CLIENT_FOUND_ROWS`. In MySQL Connector/J, the `useAffectedRows` property controls whether this flag is sent. Consequently, the exact same SQL statement can return different update counts when executed from two different applications or two different connection configurations.

This lesson belongs to the `DATABASE_MYSQL` module, focusing on design, SQL querying, transactions, concurrency control, and relational database operations. Properly understanding row-count semantics helps you write accurate repositories, APIs, batch jobs, bulk updates, and optimistic locking mechanisms.

After this lesson, you will be able to:

- Distinguish between matched rows and changed/affected rows.
- Explain `UPDATE` results when the new value equals the existing value.
- Read `Rows matched`, `Changed`, and `Warnings` metrics from the MySQL client.
- Use `ROW_COUNT()` at the right time and understand its limitations.
- Explain the impact of `CLIENT_FOUND_ROWS` and Connector/J's `useAffectedRows`.
- Understand row counts for `INSERT`, `DELETE`, and `INSERT ... ON DUPLICATE KEY UPDATE`.
- Use `executeUpdate()` in JDBC without drawing wrong conclusions about record existence.
- Design optimistic locking and handle update results inside transactions.

## 1. Three Concepts to Distinguish

In the context of `UPDATE`, these three concepts are not synonymous:

| Concept | Meaning | Example |
| --- | --- | --- |
| Matched rows / found rows | Number of rows satisfying the `WHERE` condition and considered for update | 5 rows with `status = 'PAID'` |
| Changed rows | Number of rows where at least one value actually changed after applying `SET` | Only 2 rows transitioned from `NEW` to `PAID` |
| Affected rows / update count | The count returned to the client or API; for `UPDATE`, calculation depends on `CLIENT_FOUND_ROWS` | Could be 2 or 5 in the example above |

By default at the MySQL protocol/API level, `UPDATE` reports the number of rows actually changed. If the client connects with the `CLIENT_FOUND_ROWS` flag, the returned count is the number of rows matching `WHERE`, even when values remain unchanged.

This is a difference in how results are reported to the client. It does not alter the `WHERE` condition, written data, or SQL semantics of the `UPDATE` statement.

## 2. Basic Example: More Matched Than Changed

Create a test table:

```sql
DROP TABLE IF EXISTS row_count_demo;

CREATE TABLE row_count_demo (
    id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    note VARCHAR(100) NOT NULL,
    PRIMARY KEY (id)
) ENGINE = InnoDB;

INSERT INTO row_count_demo (id, status, note) VALUES
(1, 'NEW',  'New order'),
(2, 'PAID', 'Paid'),
(3, 'PAID', 'Paid'),
(4, 'NEW',  'Pending'),
(5, 'PAID', 'Paid');
```

Run the statement:

```sql
UPDATE row_count_demo
SET status = 'PAID'
WHERE id BETWEEN 1 AND 5;
```

5 rows match `WHERE`, yet only rows 1 and 4 change from `NEW` to `PAID`. The remaining three rows already hold `PAID`, so no change needs to be written.

| Metric | Result |
| --- | ---: |
| Matched rows | 5 |
| Changed rows | 2 |
| Default update count without `CLIENT_FOUND_ROWS` | 2 |
| Update count with `CLIENT_FOUND_ROWS` | 5 |

MySQL detects when a column is assigned its exact existing value and performs no data modification for that row. Therefore, a syntactically successful `UPDATE` statement can return an update count of 0.

### 2.1. Updating to the Same Value

After all rows have `status = 'PAID'`, run again:

```sql
UPDATE row_count_demo
SET status = 'PAID'
WHERE id BETWEEN 1 AND 5;
```

Now matched rows is still 5, while changed rows is 0. A client using changed-rows semantics receives 0; a client using found-rows semantics receives 5.

This is a common source of application bugs: if code assumes `updateCount == 0` always means "record not found", it will misreport errors when the record exists and already has the desired value.

## 3. Observing Output in the MySQL Command-Line Client

When running an `UPDATE` via the `mysql` command-line client, the output typically looks like:

```text
Query OK, 2 rows affected
Rows matched: 5  Changed: 2  Warnings: 0
```

These three numbers provide distinct information:

- `Rows matched`: number of rows matching the update condition.
- `Changed`: number of rows actually modified.
- `Warnings`: number of warnings generated during execution.

`Rows matched` and `Changed` are helpful when verifying data or investigating bulk updates. In JDBC applications, `executeUpdate()` returns only a single integer update count; it does not return both figures separately like the MySQL client's detailed summary.

When using the C API, `mysql_info()` can provide the info string showing matched, changed, and warning counts. The `CLIENT_FOUND_ROWS` flag governs how the affected-rows value returned by the API is computed.

## 4. ROW_COUNT() and Timing of Retrieval

`ROW_COUNT()` returns the number of rows affected by the most recent statement according to the connection's row-count semantics. For `UPDATE`, it is affected by `CLIENT_FOUND_ROWS` just like the affected-rows value MySQL reports to the client.

Example:

```sql
UPDATE row_count_demo
SET note = 'Checked'
WHERE id IN (1, 2);

SELECT ROW_COUNT() AS update_count;
```

Call `ROW_COUNT()` immediately after the statement being measured. If another SQL statement runs in between, `ROW_COUNT()` will reflect the newer statement rather than the original `UPDATE` result.

Some general return values:

| Immediately Preceding Statement | `ROW_COUNT()` Result |
| --- | --- |
| `UPDATE`, `INSERT`, `DELETE` | Number of affected rows per statement and connection semantics |
| `CREATE TABLE`, `DROP TABLE` | `0` |
| `SELECT` returning a result set | `-1` |
| `SELECT ... INTO OUTFILE` | Number of rows written to file |

Do not confuse `ROW_COUNT()` with `FOUND_ROWS()`. `FOUND_ROWS()` relates to the row count of a `SELECT` with `LIMIT` and the `SQL_CALC_FOUND_ROWS` mechanism, which has been deprecated in MySQL. It is not a function for retrieving matched rows of an `UPDATE` statement.

## 5. What Is CLIENT_FOUND_ROWS?

`CLIENT_FOUND_ROWS` is a capability flag sent by the client during connection handshake with MySQL Server. This flag asks the server to report the number of rows found by an `UPDATE`'s `WHERE` condition rather than only the rows actually changed.

| Connection | Behavior for an `UPDATE` That Modifies No Values |
| --- | --- |
| Without `CLIENT_FOUND_ROWS` | Update count equals changed rows; a no-op returns `0` |
| With `CLIENT_FOUND_ROWS` | Update count equals matched rows; a no-op can still return greater than `0` |

This is a connection-level option decided when the client connects. It is neither a `SET sql_mode` setting nor a clause in an SQL statement. Two connections to the same server can exhibit different row-count behaviors.

`CLIENT_FOUND_ROWS` does not cause `UPDATE` to modify extra rows. It only changes the reported affected-rows count. If a row does not satisfy `WHERE`, this flag does not cause it to be counted as matched either.

## 6. Impact of MySQL Connector/J

For Java applications, the MySQL Connector/J connection property named `useAffectedRows` controls whether the driver sends `CLIENT_FOUND_ROWS`.

| Connector/J Property | Default Value | Flag Sent to Server | Update Count of `UPDATE` |
| --- | --- | --- | --- |
| `useAffectedRows=false` | Yes | Sends `CLIENT_FOUND_ROWS` | Number of matched rows |
| `useAffectedRows=true` | No | Does not send `CLIENT_FOUND_ROWS` | Number of actually changed rows |

The property name is easily misunderstood. When `useAffectedRows=true`, the driver omits `CLIENT_FOUND_ROWS` in order to use MySQL's changed-rows semantics. Connector/J documentation explicitly notes that this option is non-JDBC-compliant in how it changes row counts, can break applications expecting found-rows behavior, yet yields the update count matching MySQL's rules for `INSERT ... ON DUPLICATE KEY UPDATE`.

Example connection URLs:

```text
# Default behavior: found rows
jdbc:mysql://localhost:3306/shop

# MySQL changed-rows behavior
jdbc:mysql://localhost:3306/shop?useAffectedRows=true
```

When a URL has multiple properties, join them with `&`:

```text
jdbc:mysql://localhost:3306/shop?useSSL=true&useAffectedRows=true
```

This property must be configured consistently across the connection pool. Changing configuration in a file without recreating the pool or physical connections can leave the application using the old behavior.

### 6.1. Verifying Behavior via JDBC

```java
String sql = "UPDATE row_count_demo SET status = ? WHERE id BETWEEN ? AND ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "PAID");
    statement.setLong(2, 1L);
    statement.setLong(3, 5L);

    int updateCount = statement.executeUpdate();
    System.out.println("Update count = " + updateCount);
}
```

Run this snippet with two different connection pools or URLs:

- With `useAffectedRows=false`, if all 5 rows match, update count is 5.
- With `useAffectedRows=true`, if only 2 rows change, update count is 2; if run again with no remaining changes, update count is 0.

To avoid tests depending on stale data, reset sample data before each run and inspect the table state after the `UPDATE`.

### 6.2. executeUpdate(), executeLargeUpdate(), and Batches

JDBC provides the following APIs:

- `executeUpdate()` returns an `int` update count for a DML statement.
- `executeLargeUpdate()` returns a `long` update count, appropriate when row counts may exceed `int` range and the driver supports it.
- `getUpdateCount()` or `getLargeUpdateCount()` retrieves the current result's update count when using the general `execute` API.
- `executeBatch()` returns an array of update counts per batch element; drivers may return `Statement.SUCCESS_NO_INFO` or `Statement.EXECUTE_FAILED` per JDBC rules.

Do not assume every value in a batch array is an exact row count. Handle status constants and inspect `BatchUpdateException` when part of a batch fails.

## 7. Row Counts of Other DML Statements

`UPDATE` row-count semantics are the most easily confused, yet `INSERT`, `DELETE`, and combined statements also have their own rules.

| Statement | Common Row-Count Interpretation |
| --- | --- |
| `INSERT` | Number of rows successfully inserted |
| `DELETE` | Number of rows deleted |
| Default `UPDATE` | Number of rows actually changed |
| `UPDATE` with `CLIENT_FOUND_ROWS` | Number of rows matching `WHERE` |
| `REPLACE` | Can count 2 for one row deleted due to key conflict and then reinserted |
| `INSERT ... ON DUPLICATE KEY UPDATE` | 1 for new insert, 2 when existing duplicate row is updated, 0 when duplicate row is unchanged; with `CLIENT_FOUND_ROWS`, unchanged case is 1 |

### 7.1. INSERT ... ON DUPLICATE KEY UPDATE

Example:

```sql
DROP TABLE IF EXISTS upsert_demo;

CREATE TABLE upsert_demo (
    id BIGINT UNSIGNED NOT NULL,
    label VARCHAR(50) NOT NULL,
    PRIMARY KEY (id)
) ENGINE = InnoDB;
```

Insert a new row:

```sql
INSERT INTO upsert_demo (id, label)
VALUES (1, 'alpha') AS incoming
ON DUPLICATE KEY UPDATE label = incoming.label;
```

Row count is `1` because one row was inserted. Run again with a new value:

```sql
INSERT INTO upsert_demo (id, label)
VALUES (1, 'beta') AS incoming
ON DUPLICATE KEY UPDATE label = incoming.label;
```

Row count is `2` when the existing row is updated. Run once more with the exact same value:

```sql
INSERT INTO upsert_demo (id, label)
VALUES (1, 'beta') AS incoming
ON DUPLICATE KEY UPDATE label = incoming.label;
```

The result is `0` if the connection does not send `CLIENT_FOUND_ROWS`; if the flag is sent, the result is `1`. For multi-row statements, the rule is evaluated per row and summed.

When using row alias syntax after `VALUES`, ensure your MySQL version supports it. Avoid using `VALUES(column)` in new examples targeting modern MySQL, as that function is deprecated inside `ON DUPLICATE KEY UPDATE` in newer MySQL releases.

### 7.2. INSERT IGNORE and Warnings

`INSERT IGNORE` can skip rows violating certain constraints or adjust invalid values to the nearest valid value depending on error type, while emitting warnings. The row count only reflects rows processed per the statement's rules; it does not directly report full skipped row counts.

After a statement needing investigation, check warnings immediately:

```sql
SHOW WARNINGS;
```

If you need counts of valid, duplicate, and rejected records, design an import workflow with a staging table and dedicated metrics. Do not rely on update count alone as a data-quality report.

## 8. LIMIT in UPDATE Counts Matched Rows

In an `UPDATE` with `LIMIT`, the limit applies to the number of matching rows found, not the number of rows actually modified.

Example:

```sql
UPDATE row_count_demo
SET status = 'PAID'
WHERE status = 'PAID'
ORDER BY id
LIMIT 3;
```

MySQL stops after finding 3 matching rows, even when all 3 already have `status = 'PAID'` and undergo no change. Thus, the update count can be 0 under changed-rows semantics even though `LIMIT 3` found 3 rows.

When updating in batches, do not use `LIMIT` while assuming update count equals the number of scanned rows. If batch progress tracking is needed, design explicit pagination keys or checkpoints, such as ascending primary key ranges.

## 9. Impact on Application Logic

### 9.1. Do Not Use Update Count 0 to Conclude a Record Does Not Exist

The following code can be wrong:

```java
int updated = repository.updateStatus(orderId, "PAID");
if (updated == 0) {
    throw new NotFoundException("Order not found");
}
```

If the order exists and is already in `PAID` status, the `UPDATE` may make no changes and return 0 under changed-rows semantics. Concluding "not found" is wrong.

Clarify what business semantics you actually need:

- If you need to know whether any row matched the condition, configure found-rows behavior or use an appropriate check query.
- If you need to know whether data actually changed, use changed-rows behavior.
- If you need to distinguish "not found", "already in desired state", and "changed", design the API/repository to return an explicit business outcome instead of a raw integer.

A possible result type is:

```java
public enum UpdateOutcome {
    NOT_FOUND,
    UNCHANGED,
    CHANGED
}
```

To distinguish these three cases accurately under concurrent updates, design appropriate transactions and locking; do not run a separate `SELECT` check and assume the state stays unchanged until the subsequent `UPDATE`.

### 9.2. Optimistic Locking with a Version Column

Optimistic locking commonly uses a `version` column to prevent overwriting another session's changes:

```sql
CREATE TABLE inventory_versioned (
    item_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    version BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (item_id)
) ENGINE = InnoDB;

UPDATE inventory_versioned
SET quantity = ?,
    version = version + 1
WHERE item_id = ?
  AND version = ?;
```

If the update count is 1, the row matched both ID and version, and the version was incremented. If the update count is 0, no row matched both ID and current version; either the row does not exist or another transaction updated it first.

Because `version` always increments on every successful update, every matched row is also a changed row. Hence, this pattern avoids confusion between no-op updates and matched rows. The repository still needs to decide how to distinguish a missing record from a version conflict if business logic requires two separate error paths.

JDBC example:

```java
String sql = """
    UPDATE inventory_versioned
    SET quantity = ?, version = version + 1
    WHERE item_id = ? AND version = ?
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setInt(1, newQuantity);
    statement.setLong(2, itemId);
    statement.setLong(3, expectedVersion);

    int changed = statement.executeUpdate();
    if (changed == 0) {
        // No row matched item_id and expectedVersion.
        // Handle not-found or optimistic-lock conflict per application contract.
    } else if (changed == 1) {
        // Update succeeded; version has been incremented.
    }
}
```

With `useAffectedRows=false`, matched-rows semantics still return 1 when the condition matches. Because the statement increments version, changed-rows semantics also return 1. This makes optimistic locking insensitive to row-count configuration differences.

### 9.3. Update Count Does Not Mean the Transaction Has Committed

`executeUpdate()` returns the result of the DML statement within the current transaction. If the connection is in manual transaction mode, that count does not yet prove the change has been durably committed.

```java
connection.setAutoCommit(false);
try {
    int changed = statement.executeUpdate();
    // Inspect changed according to business rules.
    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
}
```

If rolled back, InnoDB changes inside the transaction are undone even though `executeUpdate()` previously returned 1. Distinguish "the statement affected rows inside the transaction" from "the transaction committed successfully".

## 10. What If Both Matched Count and Changed Count Are Needed?

JDBC `executeUpdate()` returns a single update count; there is no standard API returning both matched and changed counts simultaneously. Several approaches exist:

1. **Use CLI tools or the C API when investigating:** the MySQL client can show `Rows matched`, `Changed`, and `Warnings`; the C API has `mysql_info()`.
2. **Choose one semantic for the application:** configure `useAffectedRows` consistently if business logic only needs matched or changed count.
3. **Count separately under control:** if both numbers are needed for business logic, count expected matching rows and execute the update within the same transaction using an appropriate locking strategy. Account for isolation levels, locking, and concurrency; running `SELECT COUNT(*)` before an `UPDATE` outside a transaction does not guarantee the two numbers describe the same row set.
4. **Model business outcomes:** for status transitions, versions, or approval flows, store audit events or before/after states to know what actually occurred.

Do not issue two separate SQL queries and add/subtract update counts to infer matched rows if concurrent transactions can modify data between the two statements.

## 11. This Is Not an SQL Mode

The chapter title mentions "SQL Modes and Semantics", yet make sure to distinguish clearly:

- `sql_mode` is a session/global variable controlling how MySQL handles certain syntax and data rules, such as strict mode, `ONLY_FULL_GROUP_BY`, or compatibility modes.
- `CLIENT_FOUND_ROWS` is a capability flag at the client/server connection level.
- Connector/J `useAffectedRows` is a driver property controlling whether the `CLIENT_FOUND_ROWS` flag is sent.

Changing `sql_mode` does not switch `UPDATE` between changed-rows and found-rows semantics. Two connections with identical `sql_mode` yet differing `CLIENT_FOUND_ROWS` settings can still receive different update counts for the same SQL statement.

Check SQL mode separately:

```sql
SELECT @@global.sql_mode, @@session.sql_mode;
```

Check Connector/J via the URL or DataSource configuration used by the application. You cannot infer `useAffectedRows` from `@@sql_mode` alone.

## 12. Troubleshooting When Two Environments Return Different Row Counts

When the same `UPDATE` returns different row counts between local, test, and production, check in order:

1. Confirm identical schema, data, and SQL statement.
2. Check how many rows actually match `WHERE` using a `SELECT` query with the same condition.
3. Determine whether any rows already hold the value being assigned by `SET`.
4. Identify the driver/client and version in use.
5. For Connector/J, check `useAffectedRows` in the URL or DataSource configuration.
6. Verify whether the connection pool was recreated after changing connection properties.
7. Compare JDBC's update count against the MySQL client output on identical data.
8. Check warnings, transaction commit/rollback behavior, and triggers if the result remains unexplained.

Example queries to inspect the matched row set beforehand:

```sql
SELECT COUNT(*) AS matched_rows
FROM row_count_demo
WHERE id BETWEEN 1 AND 5;

SELECT COUNT(*) AS already_paid
FROM row_count_demo
WHERE id BETWEEN 1 AND 5
  AND status = 'PAID';
```

These two queries help inspect current data, though in systems with concurrent updates they only reflect the snapshot/point-in-time of each statement. When numbers must be consistent with a write operation, design transactions and locking as required.

## 13. Practice Exercises

1. Create the `row_count_demo` table and sample data from section 2. Run an `UPDATE` setting all statuses to `PAID`.
2. Observe `Rows matched`, `Changed`, and `Warnings` output via the MySQL command-line client.
3. Run the same `UPDATE` again and explain why changed rows is 0 while matched rows remains 5.
4. Call `SELECT ROW_COUNT()` immediately after `UPDATE`. Run another statement first and call it again to observe the value changing.
5. Create two JDBC configurations: default `useAffectedRows=false` and `useAffectedRows=true`. Run the same `UPDATE` and compare `executeUpdate()`.
6. Practice `INSERT ... ON DUPLICATE KEY UPDATE` across three cases: new insert, updating to a different value, and updating to an identical value. Record row counts under both JDBC configurations.
7. Write a status-updating repository. Demonstrate why `updateCount == 0` does not always mean the record does not exist.
8. Add a `version` column and implement optimistic locking. Open two connections reading the same version and attempt sequential updates.
9. Run an `UPDATE` inside a transaction, observe the update count, and then roll back. Verify the final data and explain the difference between statement count and commit.
10. Write configuration documentation for an application specifying the exact row-count semantics expected by business code.

## 14. Pre-Production Checklist

- [ ] Determined whether business logic expects matched rows or changed rows.
- [ ] Avoided using update count 0 to conclude a record is missing without verifying semantics.
- [ ] Recorded `CLIENT_FOUND_ROWS` or Connector/J `useAffectedRows` configuration.
- [ ] All connections in the pool share a uniform row-count configuration.
- [ ] `INSERT ... ON DUPLICATE KEY UPDATE` logic tested for no-op cases.
- [ ] Batch updates handle `SUCCESS_NO_INFO`, `EXECUTE_FAILED`, and `BatchUpdateException`.
- [ ] Optimistic locking includes a version predicate and increments version in the same `UPDATE`.
- [ ] Row count is distinguished from transaction commit/rollback outcome.
- [ ] Integration tests include data that already holds the target value prior to updating.
- [ ] Logs and metrics explicitly document count semantics to prevent miscomparison across environments.

## 15. Completion Criteria

You complete this lesson when you can explain with examples why matched rows can exceed changed rows, determine how MySQL reports update counts with and without `CLIENT_FOUND_ROWS`, configure and verify `useAffectedRows` in Connector/J, understand the special row counts of upserts, and write JDBC logic that does not confuse a no-op update with a missing record. You should also know how to use a version column for optimistic locking and distinguish DML statement results from transaction commit status.

## References

- [MySQL 8.4 Reference Manual — Information Functions (`ROW_COUNT()`)](https://dev.mysql.com/doc/refman/8.4/en/information-functions.html)
- [MySQL 8.4 Reference Manual — UPDATE Statement](https://dev.mysql.com/doc/refman/8.4/en/update.html)
- [MySQL 8.4 Reference Manual — INSERT ... ON DUPLICATE KEY UPDATE](https://dev.mysql.com/doc/refman/8.4/en/insert-on-duplicate.html)
- [MySQL Connector/J Developer Guide — Connection Property `useAffectedRows`](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-connection.html)
