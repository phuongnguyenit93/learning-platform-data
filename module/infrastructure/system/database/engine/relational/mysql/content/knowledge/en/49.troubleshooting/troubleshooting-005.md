# Duplicate Entry and PRIMARY/UNIQUE Conflicts

This lesson belongs to the **DATABASE_MYSQL** module. A **Duplicate entry** error occurs when a write operation produces a value that violates a primary key (`PRIMARY KEY`) or a unique index (`UNIQUE`). In MySQL, the error typically carries code **1062** and `SQLSTATE` **23000**. It can happen because the data already exists, two concurrent requests insert the same record, collation comparison rules treat two values as equal, a composite key collides, or an application retries an operation that already succeeded.

The right fix depends on business semantics. Sometimes it is a conflict that should be returned to the user; sometimes it is a duplicate retry that needs idempotent handling; and sometimes legacy data already violates a new rule and must be cleaned before adding a `UNIQUE` index. Do not treat every 1062 error as a system crash, and do not suppress all duplicate errors with `INSERT IGNORE` without assessing the impact.

## 1. What Do PRIMARY KEY and UNIQUE Protect?

Primary keys and unique indexes both enforce uniqueness, but they serve different roles.

- **PRIMARY KEY:** uniquely identifies every row in a table. Each table can have only one primary key; primary key columns cannot be `NULL`.
- **UNIQUE:** guarantees no two rows share the same value under the index's comparison rules. A table can have multiple unique indexes.
- **Unique composite key:** guarantees that the combination of column values is unique, without requiring each individual column to be unique.

Example:

~~~sql
CREATE TABLE users (
    user_id BIGINT NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT NOT NULL,
    email VARCHAR(255) NOT NULL,
    external_ref VARCHAR(80) NULL,
    display_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_users_tenant_email (tenant_id, email),
    UNIQUE KEY uq_users_external_ref (external_ref)
) ENGINE=InnoDB;
~~~

In this table:

- `user_id` is the unique identifier for each row.
- A single tenant cannot have two rows with the same email under the column's collation.
- `external_ref` must be unique when non-`NULL`; MySQL permits multiple `NULL` values in a unique index.
- Two rows with the same email belonging to different tenants are valid because the unique key is the composite `(tenant_id, email)`.

If the application requires emails to be globally unique across the entire system, the unique key must be defined on `email` rather than `(tenant_id, email)`. Constraints must accurately reflect the business uniqueness scope.

## 2. Recognizing Duplicate Entry Errors

An insert colliding on a primary key:

~~~sql
CREATE TABLE account_demo (
    account_id BIGINT PRIMARY KEY,
    account_name VARCHAR(100) NOT NULL
);

INSERT INTO account_demo (account_id, account_name)
VALUES (10, 'An');

INSERT INTO account_demo (account_id, account_name)
VALUES (10, 'Binh');
~~~

The second statement is rejected because `account_id = 10` already exists. MySQL typically returns an error like:

~~~text
ERROR 1062 (23000): Duplicate entry '10' for key 'account_demo.PRIMARY'
~~~

Creating a unique index on `email` can also trigger the error:

~~~sql
CREATE TABLE account_email_demo (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    UNIQUE KEY uq_account_email (email)
);

INSERT INTO account_email_demo VALUES (1, 'user@example.com');
INSERT INTO account_email_demo VALUES (2, 'user@example.com');
~~~

The error can appear during these operations:

- `INSERT` creating a row with an already-existing key.
- `UPDATE` changing a key value to match another row's value.
- `INSERT ... ON DUPLICATE KEY UPDATE` triggering the update branch on conflict.
- Adding a unique index to a table that already contains duplicate data.
- Import or replication applying an event that creates a duplicate key on the target.

Example `UPDATE` causing a conflict with another row:

~~~sql
UPDATE users
SET email = 'taken@example.com'
WHERE user_id = 102;
~~~

If another row in the same tenant already has `email = 'taken@example.com'`, the update will be rejected by the unique key `(tenant_id, email)`.

Code 1062 indicates that a unique constraint was violated. By itself, it does not tell you whether the root cause was a retried request, user duplicate input, bad migration data, or a concurrency race.

### 2.1. Distinguishing from Other Key/Constraint Errors

| Error | Meaning |
|---|---|
| 1062 / SQLSTATE 23000 | Duplicate entry: `PRIMARY` or `UNIQUE` violation |
| 1452 | Cannot add/update a child row because the referenced parent row is missing (foreign key) |
| 1451 | Cannot delete/update a parent row while referencing child rows still exist |
| 1213 | Deadlock: InnoDB chose a transaction as the victim to break a deadlock |
| 1205 | Lock wait timeout |
| 1048 | Non-nullable column received `NULL` |

Do not handle 1213, 1205, or foreign key errors as duplicate errors. Each type has its own cause and remediation strategy.

## 3. Identifying Which Unique Key Was Violated

Start by reading the table definition and its indexes:

~~~sql
SHOW CREATE TABLE users\G
SHOW INDEX FROM users;
~~~

In `SHOW INDEX` output, `Non_unique = 0` indicates a unique index. `Key_name` is the index name; `Seq_in_index` shows column order in the index; `Column_name` shows the corresponding column.

You can query metadata:

~~~sql
SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX,
       COLUMN_NAME, SUB_PART, COLLATION
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'users'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

For composite unique indexes, inspect all columns in exact order. Do not conclude a single column is unique merely because it participates in a composite unique index.

For example, the unique index `(tenant_id, email)` allows:

~~~sql
INSERT INTO users
    (user_id, tenant_id, email, external_ref, display_name)
VALUES
    (101, 1, 'same@example.com', NULL, 'User A'),
    (102, 2, 'same@example.com', NULL, 'User B');
~~~

These two rows do not conflict because `tenant_id` differs. Inserting a new row with both `tenant_id = 1` and the same email as the first row will cause MySQL to report a duplicate.

### 3.1. Finding Duplicate Groups

For a single-column unique key:

~~~sql
SELECT email, COUNT(*) AS duplicate_count
FROM users
GROUP BY email
HAVING COUNT(*) > 1;
~~~

For a composite unique key:

~~~sql
SELECT tenant_id, email, COUNT(*) AS duplicate_count
FROM users
GROUP BY tenant_id, email
HAVING COUNT(*) > 1;
~~~

`GROUP BY` applies the comparison rules of the expressions/columns. If a column uses a case-insensitive collation, values like `User@example.com` and `user@example.com` are grouped together. Check this when investigating duplicates whose strings appear visually different.

For nullable columns, a `NULL` group may appear in `GROUP BY` output, but that does not mean a unique index forbids multiple `NULL`s. MySQL's unique index rules permit multiple `NULL`s; interpret results according to the actual index definition.

### 3.2. Finding the Specific Conflicting Row

If the application sends email `user@example.com`, query using conditions matching the unique key:

~~~sql
SELECT user_id, tenant_id, email, external_ref
FROM users
WHERE tenant_id = 1
  AND email = 'user@example.com';
~~~

For a composite unique key, check all components. With a case-insensitive collation, the comparison may match a value with different casing that the index still considers a duplicate.

Do not rely solely on the duplicate value snippet in the error message. With multi-column indexes or transformed/normalized strings, the message is not always sufficient to reproduce the exact conflict rule.

## 4. Collation and Data Normalization

Unique indexes follow the comparison rules of the column's collation and data type. Thus, two strings spelled differently may still be treated as equal.

Check charset and collation:

~~~sql
SHOW FULL COLUMNS FROM users;
~~~

Or:

~~~sql
SELECT COLUMN_NAME, CHARACTER_SET_NAME, COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'users';
~~~

A collation ending in `_ci` is typically case-insensitive. The suffix `_ai` is typically accent-insensitive. Some collations handle trailing spaces differently; always check the exact collation in use rather than inferring from displayed strings alone.

For example, if `email` is compared under a case-insensitive collation, the two values below will conflict:

~~~sql
INSERT INTO users (user_id, tenant_id, email, display_name)
VALUES (201, 1, 'Alice@example.com', 'Alice');

INSERT INTO users (user_id, tenant_id, email, display_name)
VALUES (202, 1, 'alice@example.com', 'alice');
~~~

If business rules consider both addresses the same identity, that behavior is desirable. If the business must distinguish them, choose an intentional comparison mode/collation and test uppercase, lowercase, accented, and whitespace cases.

### 4.1. Normalizing Data Before Creating a Unique Key

You may need to normalize emails, external codes, or phone numbers before storing them. For instance, the application can trim leading/trailing whitespace and apply an agreed casing rule.

Do not blindly apply `LOWER()` to every field without evaluating business rules. In particular, emails, usernames, and identifiers may have dedicated normalization policies.

One implementation pattern stores both the original value and a normalized column:

~~~sql
CREATE TABLE customer_contacts (
    contact_id BIGINT PRIMARY KEY,
    email_original VARCHAR(255) NOT NULL,
    email_normalized VARCHAR(255) NOT NULL,
    UNIQUE KEY uq_email_normalized (email_normalized)
);
~~~

The application is responsible for producing `email_normalized` using a single agreed normalization function. If multiple systems write to the table, ensure all writers apply the exact same rule. A generated column can be considered if the expression is supported by MySQL and appropriately deterministic.

Before changing normalization rules, search for existing values that would become duplicates. You cannot simply add a unique index and expect MySQL to choose which row to keep.

## 5. Why Checking Before INSERT Still Causes Duplicates

A common anti-pattern is checking with a `SELECT` before inserting:

~~~sql
SELECT user_id
FROM users
WHERE tenant_id = 1
  AND email = 'new@example.com';

-- If no row is found, the application executes INSERT
INSERT INTO users (user_id, tenant_id, email, display_name)
VALUES (301, 1, 'new@example.com', 'New User');
~~~

Under concurrent requests, two transactions can both read and neither sees the row. Then both insert. The unique index allows only one transaction to succeed; the other receives a duplicate error.

~~~text
Request A                    Request B
---------                    ---------
SELECT: no row found         SELECT: no row found
INSERT email X               INSERT email X
COMMIT succeeds              receives duplicate 1062
~~~

This is a race condition between the check step and the write step. Raising the isolation level or adding another `SELECT` before `INSERT` cannot replace a unique constraint. The unique index in MySQL/InnoDB is the final line of defense for uniqueness.

### 5.1. The Right Way to Handle It

- Keep `PRIMARY`/`UNIQUE` constraints in the database.
- Perform the write directly according to business intent.
- Catch error 1062 and translate it into an appropriate business outcome, such as "email already in use".
- If intentional duplicate requests occur, use an idempotency key or an upsert with clear semantics.
- If you need to read back the existing row, do so after handling the conflict inside an appropriate transaction.

Never treat a `SELECT` result prior to `INSERT` as proof that the `INSERT` is guaranteed to succeed.

## 6. Handling Duplicate Entry in Java/JDBC

With JDBC, `SQLException` exposes `SQLState` and the vendor error code. For MySQL's standard duplicate error:

- Vendor code: 1062.
- SQLState: 23000 (integrity constraint violation).

Example:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO users (user_id, tenant_id, email, display_name) "
      + "VALUES (?, ?, ?, ?)")) {

    ps.setLong(1, userId);
    ps.setLong(2, tenantId);
    ps.setString(3, email);
    ps.setString(4, displayName);
    ps.executeUpdate();

} catch (SQLException e) {
    if (e.getErrorCode() == 1062) {
        throw new EmailAlreadyUsedException(email, e);
    }
    throw e;
}
~~~

This example assumes the unique conflict involves `email`. In practice, a table may have multiple unique indexes; do not assume every 1062 error means the email already exists. Identify the violated constraint from statement context or driver-supplied error metadata, then map to the appropriate business exception.

Do not rely solely on parsing error message text for control logic. Message wording can change across versions, schema names, table names, and index names.

### 6.1. Spring and Hibernate

In Spring, the error may be translated into a `DataAccessException` subclass, such as `DuplicateKeyException` or a `DataIntegrityViolationException` depending on the execution path and exception translator.

Example handling in a service/controller:

~~~java
try {
    userRepository.save(user);
    userRepository.flush();
} catch (DataIntegrityViolationException ex) {
    if (isDuplicateKey(ex)) {
        throw new EmailAlreadyRegisteredException(user.getEmail(), ex);
    }
    throw ex;
}
~~~

`save()` may not immediately send SQL because Hibernate defers flushing until the end of the transaction. Calling `flush()` inside the catch scope detects it earlier, though it does not allow a failed transaction to continue safely. After a constraint error, the transaction usually must roll back; do not keep using the persistence context as if the operation succeeded.

The `isDuplicateKey` helper should inspect the cause chain and JDBC driver error code specifically. Do not catch every `DataIntegrityViolationException` and blindly return "already exists", because that exception can also represent `NOT NULL`, foreign key, or other constraint failures.

## 7. Choosing INSERT, INSERT IGNORE, or ON DUPLICATE KEY UPDATE

These three statement forms behave differently. Choose based on business semantics, not merely to avoid exceptions.

### 7.1. Plain INSERT

~~~sql
INSERT INTO users (user_id, tenant_id, email, display_name)
VALUES (401, 1, 'new@example.com', 'New User');
~~~

If a unique key is violated, the statement fails. This is the right choice when a duplicate is genuinely a conflict that must be reported to the caller.

### 7.2. INSERT IGNORE

~~~sql
INSERT IGNORE INTO users (user_id, tenant_id, email, display_name)
VALUES (401, 1, 'new@example.com', 'New User');
~~~

On a duplicate key, MySQL skips the conflicting row and emits a warning instead of failing with an error. However, `IGNORE` can also downgrade certain other data errors into warnings or coerce values depending on the situation. That can allow invalid data to be accepted silently in hard-to-notice ways.

If used, check `ROW_COUNT()`, warnings, and the actual number of inserted rows. Never use `INSERT IGNORE` as a blanket way to hide errors.

### 7.3. INSERT ... ON DUPLICATE KEY UPDATE

Use when business logic explicitly requires updating the existing row if a unique key conflicts:

~~~sql
INSERT INTO inventory (product_id, quantity)
VALUES (501, 5)
ON DUPLICATE KEY UPDATE
    quantity = quantity + 5;
~~~

If `product_id = 501` does not exist, MySQL inserts a new row with `quantity = 5`. If it already exists, MySQL increments `quantity` by 5.

This statement is atomic at the database level and is often useful for counters or cumulative aggregations. However, inspect every unique index on the table: any `PRIMARY`/`UNIQUE` conflict can trigger the `UPDATE` branch. If a table has multiple unique keys matching different existing rows, the result may not correspond to the identity the application intended to update. Safe upsert design avoids ambiguous secondary unique keys or guarantees all conflicts point to the same business row.

In MySQL 8.0.19 and later, row alias syntax is available to reference the new row in the `UPDATE` branch. Check version support before using it; `VALUES(column)` in the update clause was deprecated in MySQL 8.0.20. Do not copy newer syntax into systems requiring compatibility with older versions without testing.

### 7.4. REPLACE INTO Is Not UPDATE

~~~sql
REPLACE INTO users (user_id, tenant_id, email, display_name)
VALUES (401, 1, 'new@example.com', 'New Name');
~~~

`REPLACE` deletes the conflicting row and inserts a new row. If it conflicts with multiple unique indexes, it can affect multiple rows. Deleting and re-inserting can fire triggers, trigger foreign key cascades, change auto-increment values, and lose values in omitted columns.

Do not use `REPLACE` simply because its name sounds like "replace a few columns". If the goal is updating an existing row, `UPDATE` or `ON DUPLICATE KEY UPDATE` usually expresses the intent properly.

## 8. Designing Idempotency to Handle Retried Requests

Duplicate entry errors often arise when clients retry requests due to timeouts, dropped connections, or missed responses even though the transaction already committed. If the application creates orders, payments, or event records, retries can create duplicates.

A common pattern uses a unique idempotency key per business request:

~~~sql
CREATE TABLE payment_requests (
    request_key VARCHAR(100) NOT NULL,
    payment_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (request_key),
    UNIQUE KEY uq_payment_id (payment_id)
);
~~~

The application sends the same `request_key` when retrying the same request. The database guarantees only one row per key. On receiving a duplicate, the application reads the stored result and returns the corresponding response instead of executing the payment again.

Idempotency design must define:

- Whether the key is generated client-side or server-side and has sufficient entropy/unpredictability.
- Whether the key is scoped per tenant, user, or endpoint.
- How the same key with a different payload is handled.
- How business outcomes and final states are stored.
- Key retention period and handling of late retries.
- Which business mutations share the transaction with the idempotency record.

Do not just add a unique key and ignore errors. Ensure recording the key and the business outcome occur in the same transaction or have a clear recovery flow so a recorded key never exists without completed business state.

## 9. Handling Duplicate Data Before Adding a UNIQUE Index

A migration can fail when adding a unique index because legacy data already contains duplicates:

~~~sql
ALTER TABLE users
ADD UNIQUE KEY uq_users_email (email);
~~~

Before running it, check:

~~~sql
SELECT email, COUNT(*) AS duplicate_count
FROM users
GROUP BY email
HAVING COUNT(*) > 1;
~~~

For a composite unique key:

~~~sql
SELECT tenant_id, external_ref, COUNT(*) AS duplicate_count
FROM orders
WHERE external_ref IS NOT NULL
GROUP BY tenant_id, external_ref
HAVING COUNT(*) > 1;
~~~

If duplicates exist, do not delete rows arbitrarily. First determine:

1. Which rows are valid records that must be kept.
2. What foreign key, history, payment, or audit relationships the rows have.
3. Whether data can be merged or separate rows must be retained.
4. Whether external systems reference the IDs of rows being removed.
5. Whether a new normalization rule creates additional duplicates.

A cleanup plan should include backups, a staging table or data copy, criteria for choosing surviving records, ID mapping if merging, and before/after row count verification.

### 9.1. Finding Duplicates with ROW_NUMBER on MySQL 8.0+

You can number rows within each duplicate group to build a review list:

~~~sql
WITH ranked AS (
    SELECT
        user_id,
        tenant_id,
        email,
        ROW_NUMBER() OVER (
            PARTITION BY tenant_id, email
            ORDER BY user_id
        ) AS row_num
    FROM users
)
SELECT *
FROM ranked
WHERE row_num > 1;
~~~

The query above only produces a candidate list of duplicates; it does not decide that rows with `row_num > 1` are safe to delete. `ORDER BY user_id` is merely an illustrative ordering rule. Retention criteria must be based on business state, related records, and audit requirements.

On MySQL 5.7 without window functions, use `GROUP BY` to find duplicate groups and join back to the base table to inspect details.

### 9.2. Adding the UNIQUE Index After Cleanup

Once data is normalized and free of duplicates, create the unique index:

~~~sql
ALTER TABLE users
    ADD UNIQUE KEY uq_users_tenant_email (tenant_id, email);
~~~

For large tables, evaluate storage, metadata locks, DDL duration, and replication impact before deploying. Adding a unique index may scan the table and fail if a concurrent transaction inserts a duplicate while the index is building. Coordinate write throttling/blocking or use an online migration workflow appropriate for the version and workload.

After creating it, verify:

~~~sql
SHOW INDEX FROM users;
SHOW CREATE TABLE users\G
~~~

## 10. Duplicates with AUTO_INCREMENT and Composite Keys

### 10.1. AUTO_INCREMENT Does Not Guarantee Every INSERT Is Unique

Normally MySQL automatically allocates a fresh `AUTO_INCREMENT` value, yet duplicates can still happen when:

- The application explicitly supplies an existing primary key value.
- Imported data contains IDs already present on the target.
- Two independent write sources generate colliding IDs in a multi-source architecture.
- `auto_increment_increment`/`auto_increment_offset` variables in multi-writer topologies are misconfigured.
- Data is restored or synced with an inconsistent auto-increment state.

Check current value and definition:

~~~sql
SHOW CREATE TABLE orders\G

SELECT AUTO_INCREMENT
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders';
~~~

Do not adjust `AUTO_INCREMENT` just to dodge a duplicate error without identifying the ID source. In multi-writer architectures, design unique ID allocation via ID ranges, controlled increment/offset, or distributed IDs.

### 10.2. Composite Primary Keys

For a many-to-many join table:

~~~sql
CREATE TABLE user_roles (
    user_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    assigned_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (user_id, role_id)
);
~~~

A `(user_id, role_id)` pair can be assigned only once. A duplicate here typically means the application is assigning an already-existing role. If business logic permits safe idempotent assignment, treat it as "already assigned" after verifying the existing row rather than inserting another record.

If historical assignments and revocations must be recorded multiple times, this model is insufficient. Use a dedicated `assignment_id` and a state- or time-aware unique constraint matching business rules. Never drop the unique constraint just to allow duplicate rows if uniqueness remains a business requirement.

## 11. Transactions and Concurrency Contention

InnoDB uses locks and unique index checks to protect uniqueness across concurrent transactions. When two transactions concurrently insert the same new key, one transaction may have to wait for the other to finish. If the first commits, the waiting operation receives a duplicate error; if the first rolls back, the waiting operation can proceed and succeed.

Logical example:

~~~text
Transaction A                  Transaction B
-------------                  -------------
BEGIN                          BEGIN
INSERT key = K                 INSERT key = K
                               waits for lock/index outcome
COMMIT                         receives duplicate 1062
~~~

This behavior protects data integrity. Never try to remove unique indexes just to avoid waits or errors.

### 11.1. Do Not Blindly Retry Duplicate Errors

Error 1062 is usually a deterministic data conflict, not a transient error suited for infinite retries. Retrying the exact same `INSERT` with the same values will normally keep failing.

Only retry when business logic identifies it as a duplicate request that should return the stored outcome, or when input data has been changed through a controlled process. For deadlock 1213, transaction retry strategies can be appropriate, provided the entire transaction is retried and the operation is idempotent.

### 11.2. Check-Then-Update

If business logic needs "create if absent, update if present", use an atomic upsert aligned with the unique key instead of multi-step `SELECT` then `INSERT` then `UPDATE`. If the update branch requires complex conditions, use transactions and row locking according to your designed model.

`SELECT ... FOR UPDATE` can lock existing rows, but it is not a universal way to lock a nonexistent row across all isolation levels and access paths. Understand next-key/gap locks, isolation levels, and query indexes before relying on it to prevent race conditions.

## 12. Production Investigation Procedure

When a duplicate error occurs, gather information before modifying data:

1. Record timestamp, request/correlation ID, statement or SQL template, and error code.
2. Identify the violated table and `PRIMARY` or `UNIQUE` key name.
3. Read `SHOW CREATE TABLE` and `SHOW INDEX` for full index definitions.
4. Locate the existing row using all columns of the unique key and the right collation.
5. Check whether the request was retried, double-submitted, run in parallel, or reprocessed from a queue.
6. Check whether import jobs, batches, replication, or background jobs write to the same table.
7. Classify the duplicate as a valid conflict, legacy data, race condition, or ID generation bug.
8. Pick the business-aligned fix: return conflict, return idempotent result, upsert, or clean up data.
9. Monitor 1062 error counts by constraint and endpoint after deploying the fix.

Do not log full sensitive data just to investigate duplicates. Log constraint name, request ID, and masked/hashed values per policy.

## 13. Example: Account Registration API

Suppose each tenant may have only one account per email. Schema:

~~~sql
CREATE TABLE tenant_users (
    id BIGINT NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT NOT NULL,
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_tenant_users_email (tenant_id, email)
) ENGINE=InnoDB;
~~~

The service does not need to rely on a pre-check query to prevent duplicates. It can execute `INSERT` and handle the unique constraint error:

~~~java
public User register(long tenantId, String email, String displayName) {
    try {
        return userRepository.insertNew(tenantId, email, displayName);
    } catch (DuplicateKeyException ex) {
        throw new EmailAlreadyRegisteredException(tenantId, email, ex);
    }
}
~~~

If the API must return the same result when a client retries, add a separate request idempotency key. Unique email and idempotency keys solve two different problems:

- Unique email: prevents a single tenant from registering the same email twice.
- Idempotency key: prevents a retried request from being processed as a new business operation.

If a different tenant registers the same email, the composite unique key allows it. If business rules require globally unique emails, change the constraint and validate existing data before migrating.

## 14. Duplicate Entry Troubleshooting Checklist

- [ ] Captured the MySQL error code and confirmed whether it is 1062.
- [ ] Identified the exact table and `PRIMARY`/`UNIQUE` index name.
- [ ] Read `SHOW CREATE TABLE` and all columns of the unique key.
- [ ] Checked collation, charset, and string comparison rules.
- [ ] Determined whether the unique key is single-column or composite.
- [ ] Checked `NULL` values and MySQL unique index rules.
- [ ] Queried the existing row using the full key and matching comparison semantics.
- [ ] Checked request retries, batches, queues, and concurrent writers.
- [ ] Distinguished business conflicts from transient errors like deadlocks/timeouts.
- [ ] Selected `INSERT`, `INSERT IGNORE`, or `ON DUPLICATE KEY UPDATE` based on true semantics.
- [ ] Assessed the impact of `REPLACE` if anyone proposed using it.
- [ ] Designed idempotency if requests can be retried.
- [ ] Cleaned and reconciled data before adding a `UNIQUE` index.
- [ ] Prepared backups, testing, and rollback plans for migrations.
- [ ] Monitored duplicate errors per constraint after deploying the fix.

## 15. Self-Check

1. How do `PRIMARY KEY` and `UNIQUE` indexes differ in count, `NULL` allowance, and role?
2. Why can two rows with the same email still be valid when the unique key is `(tenant_id, email)`?
3. What do error 1062 and `SQLSTATE 23000` indicate?
4. Why can two strings with different letter casing violate the same unique index?
5. Why does a pre-`INSERT` `SELECT` fail to prevent a race condition?
6. When should you use `ON DUPLICATE KEY UPDATE` vs. returning a conflict error?
7. Why can `INSERT IGNORE` mask data errors beyond duplicates?
8. How does `REPLACE INTO` differ from an upsert, and how can it affect foreign keys/triggers?
9. Why is an idempotency key needed for APIs that may be retried after timeouts?
10. Outline a data cleanup procedure before adding a unique key `(tenant_id, email)` on a table with tens of millions of rows.

When encountering a Duplicate entry error, start from the violated constraint and the index's actual comparison rules. Then determine whether the conflict stems from existing data, retries, or concurrent contention; choose the business-appropriate handling and keep unique constraints as the final safeguard for data integrity.
