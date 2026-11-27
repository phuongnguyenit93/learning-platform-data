# INSERT ON DUPLICATE KEY UPDATE and the Meaning of the Conflict Key

MySQL provides \`INSERT ... ON DUPLICATE KEY UPDATE\` to perform an upsert operation: attempt to insert a new row; if a primary key or unique key value duplicates an existing row, switch to updating the conflicting row instead. This syntax is commonly used for data synchronization, idempotent re-imports, updating records by business key, and maintaining summary tables.

An important detail is that MySQL does not allow specifying a particular conflict target in this syntax. Any PRIMARY KEY or UNIQUE index violation can trigger the UPDATE branch. Therefore, the table's key design directly determines which row can be updated.

This lesson falls within the DATABASE_MYSQL scope: safe data modification, understanding primary and unique keys, handling conflicts under concurrent writes, controlling data imported from external systems, and using prepared statements in applications.

## 1. What Is an Upsert?

Upsert is a combined term for UPDATE and INSERT. From a business standpoint, an upsert operation typically means:

- If a record does not exist for the identifying key, create a new record.
- If a record already exists for the identifying key, update the specified attributes.

In MySQL, the common syntax is:

~~~sql
INSERT INTO table_name (column_a, column_b, column_c)
VALUES (value_a, value_b, value_c)
ON DUPLICATE KEY UPDATE
    column_b = value_b,
    column_c = value_c;
~~~

Example table storing synchronization records:

~~~sql
CREATE TABLE customer_sync (
    customer_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(254) NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL DEFAULT 1,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customer_sync_email (email)
) ENGINE = InnoDB;
~~~

Attempt to write a customer:

~~~sql
INSERT INTO customer_sync
    (customer_id, email, display_name, source_version, updated_at)
VALUES
    (101, 'an@example.com', 'Nguyen An', 1, NOW(6))
ON DUPLICATE KEY UPDATE
    display_name = 'Nguyen An',
    source_version = 1,
    updated_at = NOW(6);
~~~

If no conflicting row exists, MySQL INSERTs the new row. If customer_id already exists or email is already used by another row, the UPDATE branch is triggered according to the violated unique key. A later section explains why having multiple unique keys requires special care.

## 2. What Counts as a Conflict Key?

The ON DUPLICATE KEY UPDATE branch is triggered when an INSERT causes a duplicate key on:

- PRIMARY KEY.
- Any UNIQUE index on the table.

Non-unique indexes such as regular INDEXes do not trigger this branch. Two rows with the same value in a column that only has a regular index can still be inserted.

Example:

~~~sql
CREATE TABLE product_catalog (
    product_id BIGINT UNSIGNED NOT NULL,
    sku VARCHAR(50) NOT NULL,
    barcode VARCHAR(50) NULL,
    product_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_product_sku (sku),
    UNIQUE KEY uq_product_barcode (barcode),
    KEY idx_product_name (product_name)
) ENGINE = InnoDB;
~~~

An INSERT can conflict on product_id, sku, or barcode. The index idx_product_name is non-unique, so duplicate product names do not trigger the UPDATE branch.

### 2.1. PRIMARY KEY Conflict

~~~sql
INSERT INTO product_catalog
    (product_id, sku, barcode, product_name)
VALUES
    (1, 'SKU-001', '893000000001', 'Mechanical keyboard')
ON DUPLICATE KEY UPDATE
    product_name = 'Mechanical keyboard new version';
~~~

If product_id = 1 already exists, MySQL switches to updating that row.

### 2.2. UNIQUE Index Conflict

~~~sql
INSERT INTO product_catalog
    (product_id, sku, barcode, product_name)
VALUES
    (2, 'SKU-001', '893000000002', 'Another keyboard')
ON DUPLICATE KEY UPDATE
    product_name = 'Updated keyboard';
~~~

Even though product_id = 2 does not exist yet, sku = 'SKU-001' is already in use. The unique key on sku causes a conflict, and the UPDATE branch executes on the existing row that owns that sku.

This differs from what many people assume: the UPDATE branch does not necessarily update a row with the same primary key as the incoming row. Another unique key can locate the target row instead.

## 3. MySQL Has No Conflict Target in This Syntax

Some database management systems allow explicitly specifying which constraint serves as the conflict target. MySQL's \`ON DUPLICATE KEY UPDATE\` syntax has no clause like \`ON CONFLICT (column_name)\`.

This means:
- MySQL evaluates the PRIMARY KEY and all UNIQUE indexes.
- Any violated unique key can trigger the UPDATE branch.
- You cannot instruct the syntax to handle only conflicts on uq_product_sku and ignore conflicts on uq_product_barcode.

Therefore, if a table has multiple unique keys, identify all possible conflict paths and ensure they all resolve to the same business row or share a safe handling strategy.

### 3.1. Risk When Multiple Unique Keys Point to Different Rows

Suppose the table has two rows:

| product_id | sku | barcode |
|---:|---|---|
| 1 | SKU-A | BAR-A |
| 2 | SKU-B | BAR-B |

The application sends a new row:

~~~sql
INSERT INTO product_catalog
    (product_id, sku, barcode, product_name)
VALUES
    (1, 'SKU-B', 'BAR-C', 'New product')
ON DUPLICATE KEY UPDATE
    product_name = 'Updated';
~~~

The incoming data matches product_id of row 1 but sku of row 2. The statement cannot express whether the application intends to handle the product_id conflict or the sku conflict; you should never rely on a unique index priority order to pick the target row. If the UPDATE branch modifies a unique column to a value owned by another row, the update itself can violate a unique key and fail with a duplicate key error. Resolve cases where keys identify two distinct entities before performing the upsert.

Do not design business logic around an assumption that MySQL will pick the exact unique key the application expects. If different unique keys can identify different entities, inspect and resolve conflicts beforehand, or use a transaction with explicitly controlled SELECT/UPDATE/INSERT steps.

### 3.2. Designing Keys for Unambiguous Upserts

A clean upsert model usually has one clear business identifier key, such as:

- Customer ID from a source system.
- Supplier's unique product code.
- External event ID.
- A tenant_id + external_id key.

Example:

~~~sql
CREATE TABLE imported_customer (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_system VARCHAR(40) NOT NULL,
    external_customer_id VARCHAR(100) NOT NULL,
    email VARCHAR(254) NULL,
    display_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_source_customer (
        source_system,
        external_customer_id
    )
) ENGINE = InnoDB;
~~~

The application upserts by the source key:

~~~sql
INSERT INTO imported_customer
    (source_system, external_customer_id, email, display_name)
VALUES
    ('CRM_A', 'C-1001', 'an@example.com', 'Nguyen An')
ON DUPLICATE KEY UPDATE
    email = 'an@example.com',
    display_name = 'Nguyen An';
~~~

Here the composite unique key clearly identifies a customer within a source system. If email must also be globally unique, determine whether an email conflict could indicate a different customer. If so, handle it separately instead of letting an upsert pick the target record automatically.

## 4. NULL in Unique Keys and Upserts

MySQL allows multiple NULL values in a unique index. Consequently, NULL in a unique column normally does not cause a duplicate key conflict.

Example:

~~~sql
CREATE TABLE optional_reference (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    external_code VARCHAR(80) NULL,
    description VARCHAR(150) NOT NULL,
    UNIQUE KEY uq_external_code (external_code)
);
~~~

The following two statements can create two distinct rows:

~~~sql
INSERT INTO optional_reference (external_code, description)
VALUES (NULL, 'No code yet');

INSERT INTO optional_reference (external_code, description)
VALUES (NULL, 'Still no code');
~~~

Because NULL is not treated as a duplicate value in a unique index, the ON DUPLICATE KEY UPDATE branch is not triggered simply because external_code is NULL in both rows.

For a composite unique key, if one or more components are NULL, multiple combinations can coexist. If the application intends to use a column as an upsert key, ensure that key always has a value, typically by declaring it NOT NULL.

Do not use a nullable unique key as the sole identifying key for an upsert when records might omit the key value.

## 5. Updating with Values from the Incoming Row

When a duplicate key occurs, the UPDATE branch can reference:
- Existing values in the target row.
- Values from the row being inserted.
- Computed expressions combining both.

Distinguish the two sides clearly to avoid overwriting with the wrong value.

### 5.1. Using a Row Alias in MySQL 8.0.19+

Row alias syntax for the incoming row is supported starting in MySQL 8.0.19:

~~~sql
INSERT INTO customer_sync
    (customer_id, email, display_name, source_version, updated_at)
VALUES
    (101, 'an@example.com', 'Nguyen An New', 2, NOW(6)) AS incoming
ON DUPLICATE KEY UPDATE
    email = incoming.email,
    display_name = incoming.display_name,
    source_version = incoming.source_version,
    updated_at = incoming.updated_at;
~~~

The incoming alias represents the row being inserted. On conflict, expressions such as incoming.email and incoming.display_name read the incoming row's values to assign to the existing row.

This is the preferred syntax on modern MySQL because it is clear and avoids relying on the deprecated VALUES() function.

### 5.2. VALUES(column) in Legacy Syntax

Before row aliases were supported, the common syntax was:

~~~sql
INSERT INTO customer_sync
    (customer_id, email, display_name, source_version, updated_at)
VALUES
    (101, 'an@example.com', 'Nguyen An New', 2, NOW(6))
ON DUPLICATE KEY UPDATE
    email = VALUES(email),
    display_name = VALUES(display_name),
    source_version = VALUES(source_version),
    updated_at = VALUES(updated_at);
~~~

The VALUES(column) function returns the value that INSERT intended to insert for the corresponding column.

Starting in MySQL 8.0.20, using VALUES() in the ON DUPLICATE KEY UPDATE clause is deprecated. It still exists in current MySQL releases for compatibility, but you should migrate to row aliases. On MySQL 5.7, row aliases are not supported and VALUES(column) is the standard form.

Do not confuse VALUES(column) in this context with the VALUES keyword in the INSERT clause. MySQL documentation marks this function for referencing the incoming row's value as deprecated.

### 5.3. Using Existing Column Names and the Incoming Row Alias

~~~sql
INSERT INTO inventory (
    product_id,
    quantity,
    updated_at
)
VALUES (10, 5, NOW(6)) AS incoming
ON DUPLICATE KEY UPDATE
    quantity = inventory.quantity + incoming.quantity,
    updated_at = incoming.updated_at;
~~~

On duplicate:
- inventory.quantity is the quantity currently stored in the target row.
- incoming.quantity is the quantity from the new insert.
- The new value is the sum of both quantities.

Qualifying columns with the table name distinguishes the old value from the new value. If using a table alias in INSERT, follow MySQL's supported alias syntax and avoid ambiguous naming.

## 6. Overwrite, Accumulate, or Update Only When Newer?

ON DUPLICATE KEY UPDATE does not decide the update policy on its own. You must write expressions that match business semantics.

### 6.1. Overwrite with the New Value

~~~sql
INSERT INTO customer_sync
    (customer_id, email, display_name, source_version, updated_at)
VALUES
    (101, 'an@example.com', 'Nguyen An New', 2, NOW(6)) AS incoming
ON DUPLICATE KEY UPDATE
    email = incoming.email,
    display_name = incoming.display_name,
    source_version = incoming.source_version,
    updated_at = incoming.updated_at;
~~~

Use this when data arriving from the source is considered the latest authoritative state.

### 6.2. Accumulate Quantity

~~~sql
INSERT INTO inventory (
    product_id,
    quantity,
    updated_at
)
VALUES (10, 5, NOW(6)) AS incoming
ON DUPLICATE KEY UPDATE
    quantity = inventory.quantity + incoming.quantity,
    updated_at = incoming.updated_at;
~~~

Use this when each write represents an incremental change. Remember that replaying the same request can add the quantity multiple times; this is an idempotency concern, explained in section 12.

### 6.3. Accept Only a Newer Version

~~~sql
INSERT INTO customer_sync (
    customer_id,
    email,
    display_name,
    source_version,
    updated_at
)
VALUES (
    101,
    'an@example.com',
    'Nguyen An Version 3',
    3,
    NOW(6)
) AS incoming
ON DUPLICATE KEY UPDATE
    email = IF(
        incoming.source_version > customer_sync.source_version,
        incoming.email,
        customer_sync.email
    ),
    display_name = IF(
        incoming.source_version > customer_sync.source_version,
        incoming.display_name,
        customer_sync.display_name
    ),
    updated_at = IF(
        incoming.source_version > customer_sync.source_version,
        incoming.updated_at,
        customer_sync.updated_at
    ),
    source_version = GREATEST(
        customer_sync.source_version,
        incoming.source_version
    );
~~~

This example illustrates the rule of accepting only a higher version. When writing multiple assignments that depend on the same column being updated, pay attention to MySQL's UPDATE assignment evaluation order. To prevent a later expression from reading a value already mutated by an earlier assignment, order assignments carefully or structure the statement so conditions read columns not yet modified. For complex logic, prefer a transaction with an explicit UPDATE after locating the target row.

### 6.4. Keep the Old Value If the New Value Is NULL

If a NULL incoming email means the source did not provide a change, you can write:

~~~sql
email = COALESCE(incoming.email, customer_sync.email)
~~~

However, if NULL means "clear the email," COALESCE eliminates the ability to clear it. Distinguish:
- NULL means the field was not sent.
- NULL means clear the value.
- The field was omitted from INSERT.
- The field was sent with a specific value.

A single nullable column cannot represent both "unchanged" and "clear to NULL" without an additional indicator. Use update flags, a staging table, or a dedicated UPDATE statement when clear semantics are needed.

## 7. Multiple Rows in a Single INSERT Statement

ON DUPLICATE KEY UPDATE works with multi-row INSERTs:

~~~sql
INSERT INTO inventory (
    product_id,
    quantity,
    updated_at
)
VALUES
    (10, 5, NOW(6)),
    (11, 3, NOW(6)),
    (10, 2, NOW(6))
AS incoming
ON DUPLICATE KEY UPDATE
    quantity = inventory.quantity + incoming.quantity,
    updated_at = incoming.updated_at;
~~~

MySQL processes each row in the list:
- If product_id does not exist, the row is inserted.
- If product_id already exists, the corresponding row is updated.
- Later rows in the same statement can encounter rows just inserted or updated earlier in the list.

In the example, if product_id 10 does not yet exist, the first row sets quantity to 5; the third row then conflicts on the key and adds 2, resulting in 7. If product_id 10 already had quantity 4, the two conflicting rows add 5 and 2 in sequence, resulting in 11.

### 7.1. A Multi-Row Statement Can Still Fail

Suppose updating one row violates another unique key; the statement can fail. With InnoDB and a standard multi-row INSERT, a constraint error normally rolls back the statement; do not assume earlier rows were committed.

If IGNORE is added:

~~~sql
INSERT IGNORE INTO ...
VALUES (...)
ON DUPLICATE KEY UPDATE ...;
~~~

certain duplicate errors arising in the UPDATE branch may be downgraded to warnings while MySQL continues processing remaining rows. This alters error semantics and can produce partial results under IGNORE rules. Only use IGNORE when warning inspection is explicitly implemented and partial error skipping is acceptable.

## 8. Affected Rows and How to Verify Results

For each row processed by INSERT ... ON DUPLICATE KEY UPDATE, the usual affected-rows rule is:

| Case | Affected Rows |
|---|---:|
| New row inserted | 1 |
| Existing row updated and values actually changed | 2 |
| Existing row updated but values unchanged | 0 |

If the client connection enables the CLIENT_FOUND_ROWS flag, an UPDATE with no value changes may be reported as 1 instead of 0.

With a multi-row INSERT, affected rows is the sum across all processed rows. Therefore, do not interpret affected rows simply as the count of newly created records.

### 8.1. Do Not Rely Solely on Affected Rows to Infer Business Branch

Affected rows depends on:
- Whether the row was inserted or updated.
- Whether values actually changed.
- The client's CLIENT_FOUND_ROWS flag.
- The number of rows in a multi-row statement.
- How the JDBC driver interprets update counts.

If the application needs to know whether a record already existed or was newly created, design an explicit status mechanism or re-read the row by key afterward. Do not infer business state from a single affected-rows number without controlling client flags.

## 9. AUTO_INCREMENT and LAST_INSERT_ID()

If a table has AUTO_INCREMENT, an upsert can affect the AUTO_INCREMENT counter even when it takes the UPDATE branch. Therefore, do not assume ID values increase without gaps or that every allocated value corresponds to a newly inserted row.

Example:

~~~sql
CREATE TABLE device_registry (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    device_key VARCHAR(100) NOT NULL,
    device_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_device_key (device_key)
) ENGINE = InnoDB;
~~~

Upsert:

~~~sql
INSERT INTO device_registry (device_key, device_name)
VALUES ('DEVICE-001', 'Meeting room device')
ON DUPLICATE KEY UPDATE
    device_name = 'Meeting room device';
~~~

If device_key already exists, the existing row is updated and its ID stays unchanged. However, the AUTO_INCREMENT counter may have allocated or consumed a value during the INSERT attempt. Gaps in the ID sequence are normal behavior, not a data bug.

MySQL supports LAST_INSERT_ID() with INSERT ... ON DUPLICATE KEY UPDATE. When a table has AUTO_INCREMENT and the statement inserts or updates a row, LAST_INSERT_ID() can return an AUTO_INCREMENT value associated with that row. If the application relies on this behavior, test it with your exact server version and driver, especially for multi-row statements.

A common technique is:

~~~sql
INSERT INTO device_registry (device_key, device_name)
VALUES ('DEVICE-001', 'Meeting room device')
ON DUPLICATE KEY UPDATE
    id = LAST_INSERT_ID(id),
    device_name = 'Meeting room device';

SELECT LAST_INSERT_ID();
~~~

The assignment id = LAST_INSERT_ID(id) sets the connection's LAST_INSERT_ID to the updated row's ID, allowing the application to retrieve the existing ID after an upsert. Ensure the connection is not returned to the pool or reused concurrently by another statement between the two calls.

## 10. INSERT ... ON DUPLICATE KEY UPDATE vs. REPLACE

REPLACE also handles duplicate keys, but its semantics differ significantly.

| Criterion | INSERT ... ON DUPLICATE KEY UPDATE | REPLACE |
|---|---|---|
| On key conflict | Updates existing row | Deletes conflicting row, then inserts new row |
| Preserves un-updated columns | Yes, if not reassigned | May lose old values and apply DEFAULTs |
| AUTO_INCREMENT | Existing row usually keeps its ID on UPDATE | May generate a new ID |
| Triggers / foreign keys | Fires INSERT and UPDATE behaviors accordingly | Performs DELETE then INSERT |
| Cascade risk | Follows UPDATE | DELETE may trigger ON DELETE |
| Goal | Update existing row | Replace row with a new row |

Do not use REPLACE as a shorthand for upsert when you want to keep the existing row intact. Because REPLACE can delete and re-insert, it can trigger cascading deletes, alter AUTO_INCREMENT, and lose omitted column values.

## 11. Impact on Triggers, Constraints, and Foreign Keys

ON DUPLICATE KEY UPDATE must still satisfy all table constraints:
- NOT NULL.
- Enforced CHECK constraints.
- FOREIGN KEYs.
- Remaining UNIQUE indexes.
- Data types and conversion rules.

If the UPDATE branch produces a value that violates a constraint, the statement can fail.

Triggers must also be tested. For each processed row, BEFORE INSERT fires first; if there is no duplicate and the row is inserted, the INSERT path completes with AFTER INSERT. If a duplicate is detected and MySQL switches to updating, it fires BEFORE UPDATE and AFTER UPDATE for the updated row. Thus, an upsert can pass through INSERT triggers first and then UPDATE triggers depending on the key check result. If triggers write audit logs, update timestamps, or have side effects, test both paths in a staging environment.

## 12. Atomicity, Concurrency, and Idempotency

### 12.1. Why Upserts Help Under Concurrent Writes

A common manual pattern:

~~~sql
SELECT id
FROM customer_sync
WHERE customer_id = 101;

-- If no row exists, INSERT.
-- If a row exists, UPDATE.
~~~

Between SELECT and INSERT, another transaction can insert the same customer_id. Both processes then think the row does not exist and both attempt to INSERT; one process hits a duplicate key error.

With InnoDB, an INSERT ... ON DUPLICATE KEY UPDATE paired with a unique constraint handles the conflict in a single write operation. It is usually better suited for "insert if absent, update if present" cases.

However, an atomic statement does not mean deadlocks, lock wait timeouts, or multi-unique-key errors cannot happen. Applications still need transaction error handling and an appropriate retry policy.

### 12.2. Atomic Does Not Mean Idempotent

An idempotent operation is one that can be executed repeatedly while leaving the final state identical to executing it once.

Overwrite example:

~~~sql
ON DUPLICATE KEY UPDATE
    display_name = incoming.display_name
~~~

If the same payload is sent again, the final result is normally the same. This form is easier to make idempotent.

By contrast, accumulation:

~~~sql
ON DUPLICATE KEY UPDATE
    quantity = inventory.quantity + incoming.quantity
~~~

If the application retries the same request due to a timeout, quantity will be added twice. Upsert handles key conflicts safely, but it does not automatically prevent duplicate event processing.

### 12.3. Using Event IDs to Prevent Duplicate Application

If each inventory intake is a distinct event, store a unique event_id:

~~~sql
CREATE TABLE inventory_event (
    event_id BINARY(16) NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity_delta INT NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (event_id),
    KEY idx_inventory_event_product (product_id)
) ENGINE = InnoDB;
~~~

Inside one transaction:
1. INSERT the event with event_id.
2. Only when the new event is successfully recorded, update inventory.
3. If event_id already exists, do not add the quantity again.
4. Commit both changes together.

Skeleton workflow example:

~~~sql
START TRANSACTION;

INSERT INTO inventory_event
    (event_id, product_id, quantity_delta, created_at)
VALUES
    (?, ?, ?, NOW(6));

UPDATE inventory
SET quantity = quantity + ?
WHERE product_id = ?;

COMMIT;
~~~

If the event INSERT hits a duplicate, the application catches the error and treats the event as already received without running the cumulative UPDATE again. A separate upsert pattern can be used to record event state, provided the duplicate branch does not repeat side effects.

Ensure the transaction rolls back if the inventory UPDATE fails so the event is not marked processed while inventory remains unchanged.

### 12.4. Deadlocks and Retries

When multiple transactions upsert multiple keys in different orders, InnoDB can detect a deadlock and abort one transaction. The application should:
- Catch deadlock errors (typically MySQL error 1213) and lock wait timeouts per policy.
- Roll back the failed transaction.
- Retry the entire transaction with bounded attempts and backoff.
- Maintain a consistent lock acquisition order when possible.
- Never blindly retry data errors such as unexpected secondary unique key duplicates.

If an operation triggers external side effects (sending email, calling APIs), do not repeat external side effects during a transaction retry. Use an outbox pattern or appropriate coordination mechanism.

## 13. Upserts with Conditions and Expressions

The UPDATE branch can use IF(), CASE, GREATEST(), LEAST(), or other expressions.

### 13.1. Updating Only When Incoming Data Is Newer

~~~sql
INSERT INTO device_state (
    device_key,
    state_value,
    observed_at
)
VALUES (
    'DEVICE-001',
    'ONLINE',
    '2025-04-01 10:00:00'
) AS incoming
ON DUPLICATE KEY UPDATE
    state_value = IF(
        incoming.observed_at > device_state.observed_at,
        incoming.state_value,
        device_state.state_value
    ),
    observed_at = GREATEST(
        device_state.observed_at,
        incoming.observed_at
    );
~~~

The goal is to prevent older events from overwriting newer state. When writing multiple assignments referencing the same column, watch the assignment evaluation order and craft expressions carefully. Use a separate UPDATE statement inside a transaction if complex multi-step logic is needed.

### 13.2. Incrementing a Counter

~~~sql
INSERT INTO page_view_counter (page_id, view_count)
VALUES (100, 1) AS incoming
ON DUPLICATE KEY UPDATE
    view_count = page_view_counter.view_count + incoming.view_count;
~~~

This is an atomic row-level counter increment. However, if a request is retried, the count can increment twice. If exact per-request counting is required, store a unique request/event ID to deduplicate.

### 13.3. Avoiding Timestamp Updates When Values Match

You can use a condition to retain the old timestamp if nothing changed:

~~~sql
INSERT INTO customer_sync
    (customer_id, display_name, updated_at)
VALUES
    (101, 'Nguyen An', NOW(6)) AS incoming
ON DUPLICATE KEY UPDATE
    updated_at = IF(
        customer_sync.display_name <> incoming.display_name,
        incoming.updated_at,
        customer_sync.updated_at
    ),
    display_name = incoming.display_name;
~~~

For nullable columns, `<>` can evaluate to UNKNOWN. If NULL values must also be compared safely, use the NULL-safe operator `<=>` to detect differences:

~~~sql
NOT (customer_sync.display_name <=> incoming.display_name)
~~~

The `<=>` operator returns TRUE when both sides are NULL, FALSE when only one side is NULL or values differ, and TRUE when both values are equal under the applicable comparison rules.

## 14. Using INSERT ... ON DUPLICATE KEY UPDATE with JDBC

PreparedStatement binds input values and keeps the statement separate from data.

Example:

~~~java
String sql = """
    INSERT INTO customer_sync
        (customer_id, email, display_name, source_version, updated_at)
    VALUES (?, ?, ?, ?, NOW(6)) AS incoming
    ON DUPLICATE KEY UPDATE
        email = incoming.email,
        display_name = incoming.display_name,
        source_version = incoming.source_version,
        updated_at = incoming.updated_at
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    ps.setString(2, email);
    ps.setString(3, displayName);
    ps.setLong(4, sourceVersion);

    int affectedRows = ps.executeUpdate();
}
~~~

Placeholders represent values only. You cannot use placeholders to bind table names, column names, or SQL keywords. If a table name must vary by tenant or source type, select it from an application-defined allowlist.

### 14.1. Retrieving the ID After an Upsert

If using the LAST_INSERT_ID(id) technique, read it on the same connection:

~~~java
try (PreparedStatement upsert = connection.prepareStatement(sql)) {
    // Bind parameters and execute.
    upsert.executeUpdate();
}

try (Statement statement = connection.createStatement();
     ResultSet rs = statement.executeQuery("SELECT LAST_INSERT_ID()")) {
    if (rs.next()) {
        long id = rs.getLong(1);
    }
}
~~~

Both operations must run on the same physical connection with no intervening statements. With connection pools, keep the connection checked out within the same operation scope. Never read LAST_INSERT_ID from a different connection.

### 14.2. Versions Supporting Row Aliases

The incoming row alias syntax used in the examples requires MySQL 8.0.19 or later. If the application connects to MySQL 5.7, use the older VALUES(column) syntax. Starting in MySQL 8.0.20, VALUES(column) in ON DUPLICATE KEY UPDATE is deprecated; plan to migrate to row aliases during upgrades.

Check the server version:

~~~sql
SELECT VERSION();
~~~

Test the syntax on your exact target MySQL version and driver, especially when using MariaDB or MySQL-compatible services whose syntax support history may differ.

## 15. When Should You Avoid ON DUPLICATE KEY UPDATE?

Avoid using it directly when:

- The table has multiple unique keys and an incoming row could conflict with different business rows.
- You only want to handle duplicates on one specific unique key, yet MySQL could trigger on another key.
- Multiple business rules must be evaluated before deciding between INSERT and UPDATE.
- You need to reliably return created vs. updated status across multiple branches.
- The update has non-idempotent side effects requiring deduplication.
- Conflict resolution requires data from multiple tables or external sources.

In those cases, use a transaction:
1. Look up the row by an explicit business key.
2. Lock the required row or range with SELECT ... FOR UPDATE if appropriate.
3. Decide between INSERT and UPDATE.
4. Handle duplicate races via unique constraints and exception handling.
5. Commit or roll back the entire unit of work.

SELECT ... FOR UPDATE does not lock a non-existent row in a simple way across all isolation levels and access paths. Understand InnoDB locking, gap/next-key locks, and the active isolation level. A unique constraint remains the final safeguard for uniqueness.

## 16. Common Mistakes

| Mistake or Misconception | Cause | Fix |
|---|---|---|
| Thinking only PRIMARY KEY triggers UPDATE | UNIQUE indexes also trigger it | List every unique key on the table |
| Thinking a conflict target can be specified | MySQL has no dedicated target syntax | Design keys and conflict resolution explicitly |
| Updating the wrong row by email | Email matches a different row than the incoming primary key | Check all unique keys before upserting |
| Multiple NULLs do not trigger upsert | UNIQUE indexes allow multiple NULLs | Use NOT NULL keys when unique identification is required |
| VALUES(column) emits deprecation warning | Legacy syntax as of MySQL 8.0.20 | Use row aliases on 8.0.19+ |
| Overwriting data with NULL | Incoming row has NULL and UPDATE assigns directly | Define NULL semantics; use COALESCE or update flags |
| Counter doubles after a retry | Cumulative upsert is not idempotent | Use a unique event/request ID |
| Affected rows = 2 misread as two rows | An UPDATE with changed values counts as 2 | Understand the 1/2/0 rule and CLIENT_FOUND_ROWS |
| Gaps appear in AUTO_INCREMENT | Values may be consumed during duplicate attempts | Never require gapless IDs as a business rule |
| Multi-row statement fails | One row's UPDATE violates a unique/check/FK constraint | Validate data beforehand and handle transactions |
| IGNORE hides errors | Duplicate update errors can become warnings | Use only when warnings are handled intentionally |
| Upserts still deadlock | Concurrent transactions lock keys in different orders | Retry transactions with bounds; standardize lock order |

## 17. Safe Upsert Design Checklist

Before shipping a statement to production:

1. Identify the business key used to recognize an entity.
2. Inspect the PRIMARY KEY and every UNIQUE index on the table.
3. Ensure other unique keys cannot accidentally point to a different entity.
4. Check whether key columns allow NULL; upsert keys should usually be NOT NULL.
5. Choose the duplicate policy: overwrite, accumulate, accept newer only, or ignore.
6. Use a row alias for incoming values on MySQL 8.0.19+.
7. Avoid deprecated VALUES(column) on MySQL 8.0.20+.
8. Define whether NULL means unchanged, clear value, or missing information.
9. Verify affected rows, AUTO_INCREMENT, and LAST_INSERT_ID if the application relies on them.
10. For multi-row INSERTs, verify which unique keys each row could conflict with.
11. Handle deadlocks, lock timeouts, and retries.
12. If the operation accumulates values or has side effects, design an event ID to prevent duplicate processing.
13. Use a transaction when updating multiple tables as a single unit.
14. Use PreparedStatement and parameter binding.
15. Test on the actual server version, storage engine, and JDBC driver.

## 18. Practice Exercises

### Exercise 1: Upsert by PRIMARY KEY

Create the customer_sync table. Insert customer_id 101 for the first time, then run it again with a new display_name. Verify the row count and final values.

### Exercise 2: Upsert by Secondary UNIQUE Key

Try INSERTing a new customer_id using an already-existing email. Identify which row gets updated. Explain why the UNIQUE email also triggers the UPDATE branch.

### Exercise 3: Conflicting Multiple Unique Keys

Create a table with a primary key, unique email, and unique username. Insert two distinct rows, then send a new row matching the primary key of the first row and the email of the second row. Observe the error and explain why the upsert no longer has a single clear target row.

### Exercise 4: NULL in a Unique Key

Create a table with a UNIQUE NULL external_code. Insert multiple rows with NULL, then attempt an upsert with NULL. Explain why the UPDATE branch is not triggered by NULL alone.

### Exercise 5: Incoming Row Values

Write an upsert using the incoming alias to overwrite email and display_name. Run it on MySQL 8.0.19+, then rewrite it using VALUES(column) on an older compatible environment. Check for deprecation warnings if the version supports them.

### Exercise 6: Accumulating Inventory

Create an inventory table with product_id PRIMARY KEY and quantity. Use an upsert to add quantity. Send the same request twice and observe the result. Propose an event_id design to prevent double counting.

### Exercise 7: Affected Rows

Run three cases: fresh INSERT, UPDATE that changes data, and UPDATE that leaves data unchanged. Record affected rows from your SQL client/JDBC. If possible, test with CLIENT_FOUND_ROWS.

### Exercise 8: LAST_INSERT_ID

Create an AUTO_INCREMENT table with a unique device_key. Test the id = LAST_INSERT_ID(id) technique in the UPDATE branch and read LAST_INSERT_ID() on the same connection.

### Exercise 9: Concurrency

Use two connections to send upserts for the same key almost simultaneously. Confirm that the unique constraint prevents duplicate-key rows. Extend with a multi-table transaction and observe deadlocks/retries if they occur.

### Exercise 10: JDBC

Write a PreparedStatement for a multi-column upsert. Bind values with proper types, inspect update counts, and handle unexpected duplicate key errors from secondary unique indexes.

## 19. Pre-Deployment Checklist

- [ ] Identified the business key used for upserting.
- [ ] Inspected the PRIMARY KEY and all UNIQUE indexes.
- [ ] Analyzed whether different unique keys could point to two different rows.
- [ ] Upsert key is NOT NULL when the business requires mandatory identification.
- [ ] Understood that NULL in a unique index does not conflict like ordinary values.
- [ ] Decided between overwrite, accumulate, or conditional update.
- [ ] Used a row alias for incoming values on supported versions.
- [ ] Planned replacement for deprecated VALUES(column).
- [ ] Verified semantics when input is NULL or a column is omitted.
- [ ] Understood affected rows and CLIENT_FOUND_ROWS.
- [ ] Evaluated AUTO_INCREMENT and LAST_INSERT_ID behavior.
- [ ] Tested multi-row INSERT and constraint errors on a single row.
- [ ] Understood the impact of IGNORE and warnings if used.
- [ ] Designed idempotency for cumulative operations or side effects.
- [ ] Implemented bounded deadlock and transaction retry handling.
- [ ] Used PreparedStatement in application code.
- [ ] Tested on the exact server version, storage engine, and JDBC driver.

## 20. Conclusion

\`INSERT ... ON DUPLICATE KEY UPDATE\` performs an INSERT when there is no PRIMARY KEY or UNIQUE key conflict; if a conflict occurs, MySQL switches to updating the conflicting row. Because any unique index can trigger the update branch and MySQL does not allow specifying a conflict target, key design directly determines upsert safety.

Use a clear business key, inspect all unique keys, understand NULL behavior, and define an explicit update policy. On MySQL 8.0.19 and later, prefer row aliases to reference incoming row values; VALUES(column) in the UPDATE branch is deprecated starting in 8.0.20. Under concurrent writes, upserts resolve conflicts in a single statement, yet deadlock handling is still necessary. For cumulative operations, atomic does not mean idempotent: use an event ID or request ID to prevent applying the same event multiple times.

## Official References

- [MySQL 8.4 Reference Manual – INSERT Statement](https://dev.mysql.com/doc/refman/8.4/en/insert.html)
- [MySQL 8.4 Reference Manual – INSERT ... ON DUPLICATE KEY UPDATE](https://dev.mysql.com/doc/refman/8.4/en/insert-on-duplicate.html)
- [MySQL 8.4 Reference Manual – INSERT Syntax and Row Aliases](https://dev.mysql.com/doc/refman/8.4/en/insert.html)
- [MySQL 8.4 Reference Manual – InnoDB AUTO_INCREMENT Handling](https://dev.mysql.com/doc/refman/8.4/en/innodb-auto-increment-handling.html)
- [MySQL 8.4 Reference Manual – Information Functions: LAST_INSERT_ID()](https://dev.mysql.com/doc/refman/8.4/en/information-functions.html#function_last-insert-id)
- [MySQL 8.4 Reference Manual – InnoDB Locking](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking.html)
- [MySQL 8.4 Reference Manual – InnoDB Deadlocks](https://dev.mysql.com/doc/refman/8.4/en/innodb-deadlocks.html)
- [MySQL 8.4 Reference Manual – InnoDB Transaction Model](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-model.html)
- [MySQL 8.4 Reference Manual – Prepared Statements](https://dev.mysql.com/doc/refman/8.4/en/sql-prepared-statements.html)
