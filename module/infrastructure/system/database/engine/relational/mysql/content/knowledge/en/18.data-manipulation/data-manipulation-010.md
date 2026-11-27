# Affected Rows and Identifying Unchanged-Data Cases

In MySQL, a data modification statement can succeed while reporting zero affected rows. This commonly occurs when an `UPDATE` finds a matching record whose new values equal its already stored values, or when the `WHERE` condition matches no records at all. If an application looks only at the returned number without understanding how MySQL counts rows, it can report incorrect update status or mishandle data conflicts.

The `DATABASE_MYSQL` module aims to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control; learners also practice reading execution plans, optimizing queries, managing privileges, backups, and handling relational database operational issues. In the **Data Manipulation** chapter, understanding *affected rows* accurately helps verify the outcome of `INSERT`, `UPDATE`, and `DELETE` and build safe application logic when multiple users modify data concurrently.

After this lesson, you will be able to:

- Distinguish *matched rows* from *changed rows*.
- Read DML results and retrieve row counts with `ROW_COUNT()`.
- Explain why a successful `UPDATE` statement reports 0 affected rows.
- Recognize the effect of `CLIENT_FOUND_ROWS` and the counting rules of special write statements.
- Use affected rows to verify conditional updates, detect conflicts, and coordinate with transactions.

## 1. What Are Affected Rows?

*Affected rows* is the row count MySQL reports as impacted by the most recently executed statement. Its exact meaning depends on the statement type and connection configuration. For `UPDATE`, three concepts must be distinguished:

| Concept | Meaning |
| --- | --- |
| Matched rows | Number of rows satisfying the `WHERE` condition. |
| Changed rows | Number of rows whose stored values actually changed after applying `SET`. |
| Affected rows | Number of rows MySQL reports to the client or counting function; for `UPDATE`, this defaults to changed rows. Connection settings can make this reflect matched rows. |

For example, suppose the table has a product with `quantity = 10`. The following statement locates the product, but assigns the exact same value already stored:

```sql
UPDATE inventory
SET quantity = 10
WHERE sku = 'KB-01';
```

One row matched the condition, yet no stored value changed. By default, MySQL reports 0 affected rows. This is a valid statement that executed successfully; 0 does not automatically mean a SQL error.

Conversely, if no product has SKU `UNKNOWN`, the following statement also reports 0:

```sql
UPDATE inventory
SET quantity = 5
WHERE sku = 'UNKNOWN';
```

Both situations report the same affected rows, yet for different reasons:

- **Matched row, no change:** the statement found the row, but the post-update values match the current values.
- **No matching row:** the `WHERE` condition selected no rows to update.

Therefore, an affected row count of 0 is a signal to interpret alongside the query condition and data state, not a complete diagnosis on its own.

## 2. Practice: Identifying the Three UPDATE Outcomes

Create a small inventory table to observe the results:

```sql
CREATE TABLE inventory (
    id       BIGINT PRIMARY KEY AUTO_INCREMENT,
    sku      VARCHAR(30) NOT NULL UNIQUE,
    quantity INT NOT NULL
) ENGINE = InnoDB;

INSERT INTO inventory (sku, quantity)
VALUES
    ('KB-01', 10),
    ('MS-02', 5),
    ('HD-03', 0);
```

### Case A: Row Matched, Data Unchanged

```sql
UPDATE inventory
SET quantity = 10
WHERE sku = 'KB-01';

SELECT ROW_COUNT() AS affected_rows;
```

Default result:

```text
affected_rows
-------------
0
```

The condition `sku = 'KB-01'` matches one row. However, `quantity` is already 10, so no actual change occurred. In the MySQL client, the update summary line can show matched and changed counts separately, such as `Rows matched: 1  Changed: 0`.

### Case B: Row Matched and Data Actually Changed

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'KB-01'
  AND quantity > 0;

SELECT ROW_COUNT() AS affected_rows;
```

Result:

```text
affected_rows
-------------
1
```

One row was found and `quantity` changed from 10 to 9. Affected rows is 1, even if the statement updates multiple columns simultaneously; MySQL counts affected rows, not changed columns.

### Case C: No Rows Matched

```sql
UPDATE inventory
SET quantity = 5
WHERE sku = 'UNKNOWN';

SELECT ROW_COUNT() AS affected_rows;
```

The result is 0 because no row satisfies the condition. No record was updated.

The three cases can be summarized as follows:

| Situation | Matched Rows | Default Changed Rows | Default Affected Rows |
| --- | ---: | ---: | ---: |
| Matched one row, assigned the same value | 1 | 0 | 0 |
| Matched one row, value changed | 1 | 1 | 1 |
| No matching rows | 0 | 0 | 0 |

## 3. Reading Row Counts with ROW_COUNT()

MySQL provides the `ROW_COUNT()` function to read the number of rows affected by the most recent statement on the same connection:

```sql
UPDATE inventory
SET quantity = quantity + 2
WHERE sku = 'MS-02';

SELECT ROW_COUNT() AS affected_rows;
```

Call `ROW_COUNT()` immediately after the statement you want to inspect. Another statement running in between can change the context the function reads. For example, if you run a `SELECT` returning a result set first and only then call `ROW_COUNT()`, the returned value is -1 because the most recent statement was a result-set-returning `SELECT`.

Key return values to remember:

| Most Recent Statement | `ROW_COUNT()` Value |
| --- | --- |
| `INSERT`, `UPDATE`, `DELETE` | Number of affected rows per statement and connection rules. |
| `CREATE TABLE`, `DROP TABLE` (DDL) | 0 |
| `SELECT ...` returning a result set | -1 |
| `SELECT ... INTO OUTFILE` | Number of rows written to the file |

Do not confuse `ROW_COUNT()` with `FOUND_ROWS()`. `ROW_COUNT()` reads the rows affected by the most recent statement. `FOUND_ROWS()` relates to the row count of a `SELECT` query and is often mentioned alongside `SQL_CALC_FOUND_ROWS`; both `SQL_CALC_FOUND_ROWS` and `FOUND_ROWS()` are deprecated in MySQL 8.4. When you need the total count of matching records, consider a separate `COUNT(*)` query.

If you need to retain the count for later use, capture it right after the DML statement:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'MS-02'
  AND quantity > 0;

SET @changed_rows = ROW_COUNT();

-- The variable can be reused in subsequent statements.
SELECT @changed_rows AS changed_rows;
```

## 4. Counting Rules Across DML Statements

Not every write statement uses the same counting rule. The following table summarizes common MySQL cases:

| Statement | How Affected Rows Is Calculated |
| --- | --- |
| `INSERT` | Number of new rows successfully inserted. |
| `UPDATE` | Defaults to rows actually changed; can switch to matched rows via `CLIENT_FOUND_ROWS`. |
| `DELETE` | Number of rows deleted. |
| `INSERT ... ON DUPLICATE KEY UPDATE` | Per row: 1 if newly inserted, 2 if an existing row is updated, 0 if an existing row is assigned its current values. |
| `REPLACE` | When replacing an existing row on key conflict, affected rows is 2 because the operation deletes the old row and inserts a new row. |

For `INSERT ... ON DUPLICATE KEY UPDATE`, consider a row whose unique key already exists:

```sql
INSERT INTO inventory (sku, quantity)
VALUES ('KB-01', 10) AS incoming
ON DUPLICATE KEY UPDATE
    quantity = incoming.quantity;

SELECT ROW_COUNT() AS affected_rows;
```

If `KB-01` did not exist yet, the new insert counts as 1. If it existed and `quantity` changed, the count for that row is 2. If it existed and `quantity` remained 10, the default count is 0. For multi-row statements, these per-row values are summed across processed rows.

Note that `REPLACE` has delete-then-insert semantics for conflicting rows and should not be treated as another syntax for `UPDATE`. When choosing a statement, evaluate keys, constraints, and side effects rather than looking only at the affected rows number.

## 5. CLIENT_FOUND_ROWS and Client Differences

By default, for `UPDATE`, MySQL returns the number of rows actually changed. When a client connects with the `CLIENT_FOUND_ROWS` flag, affected rows is reported as the number of rows matched by `WHERE`. In that case, assigning `quantity = 10` to a row that already had `quantity = 10` can report 1 instead of 0.

This flag also affects the unchanged case in `INSERT ... ON DUPLICATE KEY UPDATE`: 0 is reported as 1 for an existing row whose values stayed the same. This is a connection/client-layer option, not a SQL clause added to an `UPDATE` statement.

Consequently, the exact same SQL statement can return different affected row counts if the application and a MySQL CLI client use different connection settings. When checking counts in an application, check your connector's documentation and configuration, especially if business logic relies on distinguishing "found" from "changed." Never assume every library returns the same meaning without verifying configuration.

## 6. Using Affected Rows to Detect Update Conflicts

Affected rows is very useful when multiple users or processes can modify the same record concurrently. A common pattern is *optimistic locking*: each record carries a `version` column, and the application updates only if the version still equals the value it originally read.

Suppose an orders table has `id`, `status`, and `version` columns. The application read an order with `id = 101`, status `PENDING`, and version 4. When confirming the order, it runs:

```sql
UPDATE orders
SET status = 'CONFIRMED',
    version = version + 1
WHERE id = 101
  AND status = 'PENDING'
  AND version = 4;

SELECT ROW_COUNT() AS affected_rows;
```

Interpreting the result:

- **1 row:** the condition still held and the record was updated. The application can proceed to the next step in the transaction.
- **0 rows:** the record does not exist, its status changed, or the version was incremented by another operation. This signals that the update precondition no longer holds; the application must re-read the state and handle the conflict per business rules.

Incrementing `version` ensures a valid update always modifies the record. As a result, a 0 outcome in this pattern indicates a failed guard condition rather than merely assigning identical values. The version column also catches cases where a user attempts to overwrite newer state based on stale reads.

Affected rows describes only the outcome of the current statement. If an operation spans multiple statements, wrap them in an appropriate transaction and confirm business success only after `COMMIT` succeeds. If the transaction executes `ROLLBACK`, changes made earlier in the transaction are undone even if an earlier `UPDATE` reported affected rows.

## 7. Diagnostic Procedure When UPDATE Reports 0 Rows

When an application receives 0 affected rows, check in this order:

1. **Confirm the statement executed without error.** Distinguish a 0 return value from a SQL error or connection failure. Rely on driver error codes/exceptions to detect errors.
2. **Inspect the `WHERE` condition.** Verify the identifier key, status, time bounds, and bound parameters are as expected.
3. **Distinguish no-match from unchanged.** If diagnosis is needed, query the record with the same condition to inspect current values. Consider transactions or appropriate locking if another client could change the row between inspection and update.
4. **Check connection counting settings.** Determine whether the client enabled `CLIENT_FOUND_ROWS` and verify whether the API returns matched or changed rows.
5. **Evaluate transaction state.** A statement returning affected rows > 0 does not prove data has been durably committed.

Another detail: if a statement assigns both business columns and an audit column such as `updated_at`, changing `updated_at` alone makes the row count as changed, even when main business values stayed identical. Conversely, if every assigned column keeps its stored value, `UPDATE` can report 0 by default.

Do not use affected rows alone to conclude that a record definitely exists or definitely does not exist. A result of 0 can stem from multiple causes; cross-check conditions, data, and connection settings.

## 8. Checklist for Reading DML Results

- [ ] Identified whether you need matched rows or actually changed rows.
- [ ] For `UPDATE`, accounted for the case where new values match existing values.
- [ ] Read `ROW_COUNT()` immediately after the statement being checked.
- [ ] Checked the connector's `CLIENT_FOUND_ROWS` configuration if counts differ from expectations.
- [ ] Treated 0 affected rows as valid rather than a SQL error when the statement succeeded.
- [ ] When using affected rows for concurrency control, included version/status predicates in `WHERE` and handled the 0-row case.
- [ ] Confirmed the transaction committed before reporting business operation completion.

## 9. Self-Check

**Scenario 1.** A row has `quantity = 8`. The statement `UPDATE inventory SET quantity = 8 WHERE sku = 'MS-02'` matches that exact row. By default, how many affected rows does MySQL report?

**Answer:** 0. One row matched, but zero rows changed.

**Scenario 2.** A statement updates `quantity = quantity + 1` for an existing product SKU with `quantity = 8`. What is the default result?

**Answer:** 1. One row was updated and its stored value changed.

**Scenario 3.** An application updates an order with `id = 101 AND version = 4`, and affected rows is 0. Can it conclude the order does not exist?

**Answer:** No. The order might not exist, or another process may have updated it so version is no longer 4, or another condition in `WHERE` no longer holds. The application needs to inspect the current state and handle the conflict.

**Scenario 4.** An `UPDATE` ran, then the application ran a `SELECT` returning a result set, and only then called `ROW_COUNT()`. Why can it return -1?

**Answer:** Because `ROW_COUNT()` inspects the most recent statement. At that point the most recent statement is a `SELECT` returning a result set, so the value is -1. Read or save `ROW_COUNT()` immediately after the DML statement.

## References

- [MySQL 8.4 Reference Manual — Information Functions: ROW_COUNT()](https://dev.mysql.com/doc/refman/8.4/en/information-functions.html#function_row-count)
- [MySQL 8.4 Reference Manual — UPDATE Statement](https://dev.mysql.com/doc/refman/8.4/en/update.html)
- [MySQL 8.4 Reference Manual — INSERT ... ON DUPLICATE KEY UPDATE](https://dev.mysql.com/doc/refman/8.4/en/insert-on-duplicate.html)
