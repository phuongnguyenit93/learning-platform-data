# Lost Updates and Optimistic Locking Design with a Version Column

When multiple transactions concurrently read and update a row, one write can inadvertently overwrite the result of an earlier write. This phenomenon is called a **lost update**. Applications commonly run into this bug when reading data into memory, computing a new value at the Java layer, and writing back an absolute value without checking whether the underlying data has changed.

One way to detect that situation is **optimistic locking** using a `version` column. On each successful update, the application increments the version. The `UPDATE` statement is only allowed to write if the version in the database still matches the version the application read. If another transaction updated the row first, the condition no longer matches and the application detects the conflict instead of silently overwriting.

This is an important technique when building MySQL systems where multiple users concurrently edit data, such as inventory quantities, customer profiles, order statuses, or content updated by multiple staff members.

## 1. How Does a Lost Update Happen?

Suppose the `inventory` table currently has a product quantity of `10`. Two transactions A and B both read this quantity. A wants to deduct 2 units, B wants to deduct 3 units. Both applications compute the new value in memory:

- A reads `10`, computes `10 - 2 = 8`.
- B reads `10`, computes `10 - 3 = 7`.
- A writes `8` and commits.
- B writes `7` and commits afterward.

The final result is `7`, whereas if both deductions had been applied the quantity would be `5`. A's update was overwritten by B's later write.

| Time | Transaction A | Transaction B | Value in Table |
|---|---|---|---:|
| 1 | Reads quantity `10` |  | 10 |
| 2 |  | Reads quantity `10` | 10 |
| 3 | Computes new value `8` | Computes new value `7` | 10 |
| 4 | Writes `8`, commits |  | 8 |
| 5 |  | Writes `7`, commits | 7 |

The problem lies in B writing a value computed from stale data without verifying that the row is still in the state B read. If the write statement is a direct transformation on the column, such as `SET quantity = quantity - 3`, MySQL applies the subtraction to the current value of the row after acquiring a write lock; overwriting with an old in-memory value is avoided. However, for workflows that must read, validate, compute in the application, and then write back, a mechanism to detect changed data is still required.

## 2. Creating a Version Column

Add a `version` column to the table requiring protection. You can use `BIGINT` for a large increment space:

```sql
CREATE TABLE inventory (
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;
```

When creating a new row, `version` starts at `0`. This value represents the row's state version at read time. Each time a row is successfully modified, the application increments `version` by one.

If the table already contains data, you can add the column with:

```sql
ALTER TABLE inventory
ADD COLUMN version BIGINT NOT NULL DEFAULT 0;
```

Existing rows receive an initial version of `0`. From the moment optimistic locking is deployed, all write paths must follow the version-increment rule.

## 3. Conditional Update by Version

The optimistic locking workflow has three steps:

1. Read the data and the current `version` value.
2. Compute the change based on the data read.
3. Update with the condition `WHERE version = version_that_was_read`, while incrementing the version in the same statement.

Example where the application reads an inventory row:

```sql
SELECT product_id, quantity, version
FROM inventory
WHERE product_id = 9001;
```

Suppose the result is `quantity = 10` and `version = 4`. The application wants to set the quantity to `8`. The update statement must check the version:

```sql
UPDATE inventory
SET quantity = 8,
    version = version + 1
WHERE product_id = 9001
  AND version = 4;
```

After execution, the application checks the number of affected rows:

- **One row updated:** the version still matched. The change succeeded; the new version is `5`.
- **Zero rows updated:** the row may have been deleted or the version changed after the read. This is a conflict that must be handled.

The version-matching condition and the version increment sit inside the same `UPDATE` statement, so MySQL checks and modifies the row under InnoDB's concurrency rules. Two transactions that both read version `4` can both submit the statement above, but only one statement can update the row from version `4` to `5`. The other statement no longer matches `version = 4` and updates `0` rows.

General template:

```sql
UPDATE some_table
SET business_column = ?,
    version = version + 1
WHERE primary_key = ?
  AND version = ?;
```

Do not omit the version condition in other update paths. If one screen uses optimistic locking while a background job still updates data without incrementing `version`, conflict detection will no longer be reliable.

## 4. Simulating Two Competing Transactions

Suppose initially the row has `quantity = 10`, `version = 4`. Both A and B read version `4`:

```sql
-- Transaction A: application read version = 4
UPDATE inventory
SET quantity = 8,
    version = version + 1
WHERE product_id = 9001 AND version = 4;
-- A updates 1 row, version becomes 5
```

After A commits, B runs its statement based on the old version:

```sql
-- Transaction B: application also read version = 4
UPDATE inventory
SET quantity = 7,
    version = version + 1
WHERE product_id = 9001 AND version = 4;
-- B updates 0 rows because the current version is already 5
```

Thanks to the version condition, B cannot overwrite A's change. Application B must reload the latest data, report a conflict, or recompute according to business rules.

## 5. Handling Conflicts in Java/JDBC Applications

In JDBC, `executeUpdate()` returns the number of affected rows. With an optimistic locking statement that always increments `version`, a result of `1` means the update succeeded; a result of `0` means no row matched both the primary key and the read version.

The example below illustrates reading and updating within the same transaction:

```java
connection.setAutoCommit(false);

try {
    int quantity;
    long version;

    String selectSql = """
        SELECT quantity, version
        FROM inventory
        WHERE product_id = ?
        """;

    try (PreparedStatement select = connection.prepareStatement(selectSql)) {
        select.setLong(1, 9001L);

        try (ResultSet rs = select.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException("Product not found");
            }
            quantity = rs.getInt("quantity");
            version = rs.getLong("version");
        }
    }

    int newQuantity = quantity - 2;
    String updateSql = """
        UPDATE inventory
        SET quantity = ?, version = version + 1
        WHERE product_id = ? AND version = ?
        """;

    try (PreparedStatement update = connection.prepareStatement(updateSql)) {
        update.setInt(1, newQuantity);
        update.setLong(2, 9001L);
        update.setLong(3, version);

        int affectedRows = update.executeUpdate();
        if (affectedRows == 0) {
            throw new OptimisticLockException("Data has been modified");
        }
    }

    connection.commit();
} catch (SQLException | RuntimeException e) {
    connection.rollback();
    throw e;
}
```

`OptimisticLockException` in the example is an application-defined business exception or replaced by the appropriate exception type for the framework in use. The sample code focuses on how to check the affected row count; a production application also needs to manage `autoCommit` state, roll back on errors, and close resources properly over the `Connection` lifecycle.

If the update fails due to a conflict, there are several ways to handle it:

- Reload the latest row, display the updated data, and ask the user to confirm again.
- Automatically recompute and retry the update if business rules permit.
- Return a conflict error to the API so the client reloads the data.

Do not loop infinitely or resubmit the exact value computed from stale data. When retrying, you must read the new version and state, then recompute. Cap the retry count and use appropriate backoff to prevent many clients from continuously contending on the same row.

## 6. Optimistic Locking for Updates and Deletes

Optimistic locking applies to delete operations as well. If the application read a row at version `12`, the delete statement must match that version:

```sql
DELETE FROM inventory
WHERE product_id = 9001
  AND version = 12;
```

If someone else modified the row and incremented the version to `13`, the delete statement affects zero rows. The application can report that the record has changed and require a reload before deleting.

For multi-table updates within the same business operation, use a single transaction. If one of the version-checked update statements returns `0` rows, roll back the entire transaction so partial changes are not saved:

```sql
START TRANSACTION;

UPDATE orders
SET status = 'CONFIRMED',
    version = version + 1
WHERE order_id = 7001
  AND version = 3;

-- Application checks ROW_COUNT() right after UPDATE.
-- If the result is not 1: ROLLBACK.

UPDATE reservations
SET status = 'ALLOCATED',
    version = version + 1
WHERE reservation_id = 8001
  AND version = 6;

-- Continue checking the affected row count.
-- Only COMMIT if all version conditions match.

COMMIT;
```

In applications, obtain the affected row count from the statement-execution API rather than relying on a separate query executed later. If using `ROW_COUNT()` in SQL, read it immediately after the corresponding `UPDATE` statement because a subsequent statement can change the function's result.

## 7. When Should You Use Atomic Updates Instead of Version Locking?

Not every update needs to read data into the application and then use `version`. If the business operation is simply incrementing or decrementing a numeric value, the transformation can be expressed directly in SQL:

```sql
UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 9001
  AND quantity >= 2;
```

The condition and subtraction are executed on the current row within the same statement. The affected row count is `1` if the deduction succeeded, or `0` if the product does not exist or quantity is insufficient. This avoids the pattern of reading `10` into the application and writing back the absolute value `8`.

If you still need to increment the version so open screens can detect changed data, you can combine them:

```sql
UPDATE inventory
SET quantity = quantity - 2,
    version = version + 1
WHERE product_id = 9001
  AND quantity >= 2;
```

Optimistic locking is better suited when the application needs to inspect multiple fields, compute in the business layer, or protect an edit based on an earlier read. Atomic updates suit simple transformations that can be expressed completely in a single SQL statement.

## 8. Optimistic Locking vs. Pessimistic Locking

InnoDB provides row locks to coordinate concurrent writes. Another approach is pessimistic locking: acquiring locks right at read time so other transactions must wait before modifying the same row.

```sql
START TRANSACTION;

SELECT quantity
FROM inventory
WHERE product_id = 9001
FOR UPDATE;

-- Check and compute while holding the row lock.
UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 9001;

COMMIT;
```

| Criterion | Optimistic Locking with `version` | Pessimistic Locking with `FOR UPDATE` |
|---|---|---|
| When conflicts are detected/avoided | Detected at update time if version changed | Holds locks so other transactions must wait |
| Suitable when | Conflicts are rare, non-DB processing time is relatively long | Contention is high or read-then-write operations must be serialized |
| Main cost | May need to reload and retry on conflict | Can cause lock waits, longer lock hold times, and deadlock risk |
| Implementation requirement | Every write path must check and increment `version` | Transactions must hold locks until completion or rollback |

No single option is best for every situation. If many users frequently update the same row and retries are expensive, pessimistic locking may make sense. If most operations do not conflict and the application can handle stale-data cases, optimistic locking generally reduces lock hold duration.

## 9. Design Rules to Follow

1. **Increment the version in the update statement itself.** Do not split updating data and incrementing `version` into two separate statements.
2. **All write paths must comply.** APIs, background jobs, admin tools, and batch jobs modifying the table must all increment the version or follow an equivalent coordination protocol.
3. **Never reuse an old version.** On conflict, reload fresh data and the new version before retrying.
4. **Check affected row counts.** One row means success; zero rows means conflict or the record no longer exists. If the primary key guarantees uniqueness, a result greater than one indicates an issue with assumptions or the statement.
5. **Keep transactions short.** When multiple related operations exist, run them in a short transaction and roll back the entire transaction when any version check fails.
6. **Do not treat isolation level as a substitute for a version column.** Isolation level controls how transactions observe data; the version column verifies that the record the application intends to edit is still the version it read.

## 10. Self-Check

1. How does a lost update occur when two applications read the same value and write back absolute values?
2. Why does the `WHERE version = ?` condition help detect an update that occurred after the read?
3. In the optimistic locking pattern, why must `version` be incremented inside the same `UPDATE` statement?
4. What situations can `executeUpdate()` returning `0` represent?
5. When a conflict is detected, why should you not retry using the value computed from old data?
6. When should you use an atomic SQL update or pessimistic locking instead of optimistic locking?
