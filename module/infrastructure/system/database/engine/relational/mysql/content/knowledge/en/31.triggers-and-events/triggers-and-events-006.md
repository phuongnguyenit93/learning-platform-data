# REPLACE/Upsert and the Actual Trigger Chain Fired

In MySQL, two statements commonly used for "insert if not present, otherwise handle existing" writes are `REPLACE` and `INSERT ... ON DUPLICATE KEY UPDATE`. Both can encounter PRIMARY KEY or UNIQUE key conflicts, yet their data semantics and trigger chains are very different.

`REPLACE` has delete-then-insert semantics for conflicting rows. As a result, a single REPLACE can fire both INSERT triggers and DELETE triggers. `INSERT ... ON DUPLICATE KEY UPDATE` attempts to insert; if a duplicate key is detected, it switches to the UPDATE branch. For each input row, MySQL always fires BEFORE INSERT first, then either runs AFTER INSERT, or runs both BEFORE UPDATE and AFTER UPDATE.

This difference directly affects audit logs, summary tables, data synchronization, foreign keys, AUTO_INCREMENT, and triggers fired indirectly on other tables. Looking only at the statement name or affected row count makes it easy to misread whether old data was deleted, existing data was updated, or which triggers actually ran.

This lesson walks through each execution branch, builds an observable multi-table trigger chain, and provides a testing workflow and safe operational rules.

The examples use server-side SQL syntax. When creating triggers with a BEGIN ... END body in the mysql command-line client, change the client delimiter (for example to //) before the CREATE statement and restore the delimiter afterward. DELIMITER is a mysql client command, not SQL sent to the server. In application drivers, send the entire CREATE TRIGGER statement as a single statement via the driver API.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish REPLACE from INSERT ... ON DUPLICATE KEY UPDATE.
- Explain why REPLACE carries DELETE + INSERT semantics.
- List the triggers fired in the insert, duplicate-update, and replace branches.
- Trace the per-row BEFORE/AFTER sequence of a multi-row statement.
- Understand how a trigger writing to another table can fire downstream triggers.
- Distinguish UPDATE triggers from DELETE/INSERT triggers across the two upsert styles.
- Recognize the impact of multiple UNIQUE indexes on REPLACE and upsert.
- Evaluate the impact of REPLACE on AUTO_INCREMENT and foreign keys.
- Use row aliases in ON DUPLICATE KEY UPDATE instead of the deprecated VALUES() function.
- Understand FOLLOWS and PRECEDES when multiple triggers share the same timing/event.
- Identify trigger limitations, atomicity, and behavior when a trigger fails.
- Inspect trigger metadata and design a test matrix for each branch.

## 1. Triggers React to Row Operations, Not Just Statement Names

MySQL defines triggers around three types of row operations:

- INSERT: a new row is added to the table.
- UPDATE: an existing row is modified.
- DELETE: an existing row is removed.

Triggers also have a timing:

- BEFORE: runs before the row operation.
- AFTER: runs after the row operation succeeds.

Every trigger has FOR EACH ROW. MySQL does not support statement-level triggers that run once for an entire SQL statement. If an INSERT statement adds 500 rows, the corresponding trigger can run 500 times for each triggered type.

Core matrix:

| Statement | Row operation | Basic trigger sequence |
|---|---|---|
| Successful INSERT | Insert | BEFORE INSERT → AFTER INSERT |
| UPDATE | Update | BEFORE UPDATE → AFTER UPDATE |
| DELETE | Delete | BEFORE DELETE → AFTER DELETE |
| REPLACE, no duplicate | Insert | BEFORE INSERT → AFTER INSERT |
| REPLACE, with duplicate | Delete old row then insert new row | BEFORE INSERT → BEFORE DELETE/AFTER DELETE for conflicting row → AFTER INSERT |
| INSERT ... ON DUPLICATE KEY UPDATE, no duplicate | Insert | BEFORE INSERT → AFTER INSERT |
| INSERT ... ON DUPLICATE KEY UPDATE, with duplicate | Update old row | BEFORE INSERT → BEFORE UPDATE → AFTER UPDATE |

Key point: REPLACE never switches to UPDATE triggers. INSERT ... ON DUPLICATE KEY UPDATE never switches to DELETE triggers. The two statements resolve duplicates in fundamentally different ways.

## 2. REPLACE Deletes Conflicting Rows and Inserts a New Row

REPLACE is a MySQL extension. When a new row has a value colliding with a PRIMARY KEY or UNIQUE index, MySQL deletes the conflicting row and retries inserting the new row.

Common syntax:

    REPLACE INTO product (
        product_id,
        product_name,
        price
    )
    VALUES (
        101,
        'Keyboard',
        49.90
    );

If product_id 101 does not exist yet, this is a normal insert. If it already exists, the old row is deleted and the new row is inserted.

### 2.1. Trigger Sequence When REPLACE Encounters a Duplicate

For a single input row, the logical sequence can be read as:

1. MySQL attempts to insert the new row; BEFORE INSERT runs for the attempted row.
2. If a PRIMARY KEY or UNIQUE index collides, MySQL locates the conflicting row.
3. BEFORE DELETE runs for the old row about to be deleted.
4. The old row is deleted; AFTER DELETE runs.
5. MySQL retries inserting the new row.
6. Once the new row is inserted successfully, AFTER INSERT runs.

Diagram:

    REPLACE
       |
       v
    BEFORE INSERT
       |
       v
    Duplicate key?
       |
       +---- No -------------------------+
       |                                 |
       |                                 v
       |                            Insert row
       |                                 |
       |                                 v
       |                            AFTER INSERT
       |
       +---- Yes
             |
             v
        BEFORE DELETE
             |
             v
          Delete old row
             |
             v
        AFTER DELETE
             |
             v
        Retry insert new row
             |
             v
        AFTER INSERT

Thus, when REPLACE replaces a row, audits can record both the deletion of the old row and the insertion of the new row. Do not create only an AFTER INSERT trigger and conclude that replacement operations are fully audited.

If BEFORE INSERT raises an error, the row operation has not occurred and there is no AFTER INSERT. If BEFORE DELETE or AFTER DELETE raises an error, REPLACE fails according to trigger error rules; with transactional tables, statement changes roll back.

### 2.2. REPLACE Uses New Values for the Entire Row

REPLACE takes values for the new row from the specified columns. Omitted columns receive their DEFAULT just as in INSERT. It does not automatically preserve old column values absent from the column list.

Example:

    CREATE TABLE product (
        product_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
        product_name VARCHAR(100) NOT NULL,
        price DECIMAL(12,2) NOT NULL,
        description VARCHAR(500) DEFAULT 'No description',
        updated_at TIMESTAMP NOT NULL
            DEFAULT CURRENT_TIMESTAMP
    ) ENGINE = InnoDB;

Old row:

    INSERT INTO product (
        product_id, product_name, price, description
    )
    VALUES (
        101, 'Keyboard', 49.90, 'Mechanical keyboard'
    );

REPLACE passes only three columns:

    REPLACE INTO product (
        product_id, product_name, price
    )
    VALUES (
        101, 'Keyboard Pro', 59.90
    );

The new row gets description = 'No description' from DEFAULT. The old description value is not preserved.

If you want to keep existing columns and modify only a few columns on duplicate, INSERT ... ON DUPLICATE KEY UPDATE is usually more appropriate.

### 2.3. REPLACE Can Delete Multiple Rows

A table with multiple UNIQUE indexes can cause one REPLACE row to conflict with multiple different existing rows.

Example:

    CREATE TABLE account_alias (
        account_id BIGINT NOT NULL PRIMARY KEY,
        email VARCHAR(200) NOT NULL,
        external_ref VARCHAR(100) NOT NULL,
        UNIQUE KEY uq_email (email),
        UNIQUE KEY uq_external_ref (external_ref)
    ) ENGINE = InnoDB;

Initial data:

    INSERT INTO account_alias
        (account_id, email, external_ref)
    VALUES
        (1, 'a@example.test', 'EXT-A'),
        (2, 'b@example.test', 'EXT-B');

Command:

    REPLACE INTO account_alias
        (account_id, email, external_ref)
    VALUES
        (3, 'a@example.test', 'EXT-B');

The new row conflicts on email with account 1 and on external_ref with account 2. The REPLACE algorithm may delete each conflicting row and retry inserting until the new row succeeds. Consequently, both old rows can be deleted before account 3 is inserted.

This is a major data risk when using REPLACE on tables with multiple unique keys representing distinct entities. Never treat REPLACE as "update the row with the same business key" when multiple UNIQUE indexes exist.

### 2.4. Privileges Required for REPLACE

The account running REPLACE needs both:

- INSERT on the target table.
- DELETE on the target table.

This follows from delete-and-insert semantics. An account with only INSERT and no DELETE can run normal INSERTs but lacks sufficient privileges for REPLACE.

### 2.5. Affected Row Count

REPLACE returns an affected row count equal to the sum of deleted rows and inserted rows:

| Outcome | Typical affected rows |
|---|---:|
| New insert, zero rows deleted | 1 |
| One old row deleted, one new row inserted | 2 |
| Two old rows deleted, one new row inserted | 3 |

Do not use this number as a stable business status code. One new row can replace multiple old rows due to multiple UNIQUE indexes; furthermore, storage engine implementation details can affect certain internal status counters.

## 3. INSERT ... ON DUPLICATE KEY UPDATE Branches to INSERT or UPDATE

INSERT ... ON DUPLICATE KEY UPDATE attempts to insert the new row. If a PRIMARY KEY or UNIQUE index collides, MySQL updates the corresponding existing row.

Example:

    INSERT INTO product (
        product_id,
        product_name,
        price
    )
    VALUES (
        101,
        'Keyboard Pro',
        59.90
    ) AS incoming
    ON DUPLICATE KEY UPDATE
        product_name = incoming.product_name,
        price = incoming.price;

If product_id 101 does not exist yet, the row is inserted. If it already exists, the columns listed in the UPDATE clause are updated on the existing row.

### 3.1. Trigger Sequence When Upsert Inserts Successfully

When there is no duplicate key:

1. BEFORE INSERT runs.
2. The row is inserted.
3. AFTER INSERT runs.

There is no BEFORE UPDATE or AFTER UPDATE in this branch.

### 3.2. Trigger Sequence When Upsert Hits a Duplicate

When the input row violates a PRIMARY KEY or UNIQUE index:

1. BEFORE INSERT still runs for the input row.
2. MySQL detects the duplicate key.
3. BEFORE UPDATE runs for the row to be updated.
4. The old row is updated according to the UPDATE clause and any modifications made in BEFORE UPDATE.
5. AFTER UPDATE runs.

There is no AFTER INSERT in the duplicate branch. Nor is there any BEFORE DELETE or AFTER DELETE.

Diagram:

    INSERT ... ON DUPLICATE KEY UPDATE
       |
       v
    BEFORE INSERT
       |
       v
    Duplicate key?
       |
       +---- No -------------------------+
       |                                 |
       |                                 v
       |                            Insert row
       |                                 |
       |                                 v
       |                            AFTER INSERT
       |
       +---- Yes
             |
             v
        BEFORE UPDATE
             |
             v
          Update old row
             |
             v
         AFTER UPDATE

A BEFORE INSERT trigger can run even when no new row is ultimately inserted. Therefore, do not place "new row was created" logic in BEFORE INSERT if an upsert statement can enter the UPDATE branch.

### 3.3. OLD and NEW in Each Trigger

Pseudo-rows carry meaning by event:

| Trigger | OLD | NEW |
|---|---|---|
| BEFORE INSERT | No old row | Row values about to be inserted |
| AFTER INSERT | No old row | Newly inserted row |
| BEFORE UPDATE | Row before update | Proposed value after update |
| AFTER UPDATE | Row before update | Row after update |
| BEFORE DELETE | Row about to be deleted | No new row |
| AFTER DELETE | Deleted row | No new row |

In an upsert's BEFORE INSERT, NEW describes the input row. If there is a duplicate, BEFORE UPDATE proceeds with OLD as the existing row and NEW as the proposed post-UPDATE value. Consequently, a value modified in BEFORE INSERT can participate in the upsert process; if you normalize business keys, carefully verify how it affects duplicate detection and the UPDATE clause.

In BEFORE UPDATE, you can assign NEW.column = value to alter the value about to be written. OLD is read-only. In AFTER triggers, the row has already been written, so you cannot modify NEW with SET.

## 4. Comparing REPLACE and ON DUPLICATE KEY UPDATE

| Criterion | REPLACE | INSERT ... ON DUPLICATE KEY UPDATE |
|---|---|---|
| When no duplicate | INSERT | INSERT |
| When duplicate | Deletes conflicting row(s) then INSERTs new row | UPDATEs conflicting row |
| Duplicate branch triggers | BEFORE INSERT, BEFORE/AFTER DELETE, AFTER INSERT | BEFORE INSERT, BEFORE/AFTER UPDATE |
| UPDATE triggers on duplicate | No | Yes |
| DELETE triggers on duplicate | Yes | No |
| Preserves unspecified old columns | No, receives DEFAULT | Yes, if not assigned in UPDATE clause |
| Base privileges | INSERT + DELETE | INSERT + UPDATE |
| Typical affected rows on single-row duplicate | 2 | 2 if changed; 0 if unchanged |
| Can delete multiple rows via multiple unique keys | Yes | Updates only one row; outcome can be ambiguous |

Choose the statement by data semantics:

- Use REPLACE when the true intent is to delete conflicting rows and create a new row from all supplied values.
- Use INSERT ... ON DUPLICATE KEY UPDATE when you want to preserve the existing entity and update selected columns.
- Use INSERT IGNORE when you want to skip duplicate rows or turn certain errors into warnings; this is not an upsert.

Do not pick REPLACE just because the word "replace" sounds like updating. It can fire delete triggers, foreign key cascades, and delete multiple rows.

## 5. Using Row Aliases in ON DUPLICATE KEY UPDATE

Since MySQL 8.0.19, you can specify a row alias after VALUES to reference the input row's values:

    INSERT INTO product (
        product_id,
        product_name,
        price
    )
    VALUES (
        101,
        'Keyboard Pro',
        59.90
    ) AS incoming
    ON DUPLICATE KEY UPDATE
        product_name = incoming.product_name,
        price = incoming.price;

You can also specify column aliases:

    INSERT INTO product (
        product_id,
        product_name,
        price
    )
    VALUES (
        101,
        'Keyboard Pro',
        59.90
    ) AS incoming(id, name, amount)
    ON DUPLICATE KEY UPDATE
        product_name = name,
        price = amount;

The row alias must differ from the table name. Column aliases must not collide with the row alias name and must be used consistently.

### 5.1. VALUES(column) Is Deprecated

Old style:

    INSERT INTO product(product_id, price)
    VALUES (101, 59.90)
    ON DUPLICATE KEY UPDATE
        price = VALUES(price);

The VALUES(column) function inside ON DUPLICATE KEY UPDATE has been deprecated since MySQL 8.0.20. Use a row alias or column aliases in new code to avoid warnings and prepare for future versions.

## 6. Multiple UNIQUE Indexes Make Upserts Unpredictable

ON DUPLICATE KEY UPDATE has no syntax to specify which unique index serves as the "business key" identifying the row to update. If a table has multiple unique indexes, an input row can collide in multiple ways.

Example:

    CREATE TABLE customer_identity (
        customer_id BIGINT NOT NULL PRIMARY KEY,
        email VARCHAR(200) NOT NULL,
        external_ref VARCHAR(100) NOT NULL,
        display_name VARCHAR(100) NOT NULL,
        UNIQUE KEY uq_customer_email (email),
        UNIQUE KEY uq_customer_external (external_ref)
    ) ENGINE = InnoDB;

If email matches row A while external_ref matches row B, MySQL updates only one matching row according to the statement's duplicate-key resolution; the outcome can resemble UPDATE ... WHERE email = ... OR external_ref = ... LIMIT 1. Never treat such an upsert as merging two entities.

Additionally, MySQL marks certain forms of INSERT ... ON DUPLICATE KEY UPDATE on tables with multiple unique/primary keys as unsafe for statement-based replication.

Recommendations:

- Design one clear business key for upserts.
- If multiple identifiers must be reconciled, implement entity resolution separately using explicit transactions and appropriate locking.
- Do not use multiple unique keys as an implicit OR condition to pick a row.
- Check warnings and replication safety before deploying.

## 7. REPLACE, AUTO_INCREMENT, and Foreign Keys

### 7.1. AUTO_INCREMENT

REPLACE can generate a new AUTO_INCREMENT value when a row is replaced due to another unique key and the auto-increment column is not supplied. If REPLACE collides on the primary key itself and supplies the same id value, the new row can retain that value; however, never infer insert/delete counts from gaps in the sequence.

With INSERT ... ON DUPLICATE KEY UPDATE, InnoDB may increment the AUTO_INCREMENT counter even when the statement takes the UPDATE branch due to a duplicate. Thus, gaps in ID sequences do not prove rows were deleted.

If generated IDs are needed, use an appropriate ID-retrieval mechanism and understand LAST_INSERT_ID() per statement rather than inferring from affected row counts.

### 7.2. ON DELETE CASCADE Can Delete Child Rows

If REPLACE deletes an old parent row, a foreign key's ON DELETE CASCADE action can delete related child rows. When the new parent row is inserted, cascade-deleted child rows are not automatically recreated.

Example:

    CREATE TABLE customer (
        customer_id BIGINT NOT NULL PRIMARY KEY,
        email VARCHAR(200) NOT NULL UNIQUE
    ) ENGINE = InnoDB;

    CREATE TABLE customer_order (
        order_id BIGINT NOT NULL PRIMARY KEY,
        customer_id BIGINT NOT NULL,
        FOREIGN KEY (customer_id)
            REFERENCES customer(customer_id)
            ON DELETE CASCADE
    ) ENGINE = InnoDB;

If you REPLACE a customer with a duplicate email but a new customer_id, MySQL deletes the old customer. Orders belonging to the old customer may be deleted via ON DELETE CASCADE, and then the new customer is inserted. This is why REPLACE can cause loss of related data even when the command looks like rewriting a customer record.

### 7.3. Foreign Key Cascades Do Not Fire Triggers

MySQL does not fire triggers for operations performed by foreign key cascade actions. If ON DELETE CASCADE deletes rows in customer_order, DELETE triggers on customer_order do not run for the cascade-deleted rows.

Therefore, if the system needs to audit all child row changes, you cannot rely solely on child-table DELETE triggers when foreign key cascades exist. Design auditing at the business layer or capture parent operations appropriately.

## 8. Building a Real Multi-Table Trigger Chain

A trigger can write to another table. If that operation modifies a table that has triggers, triggers on the target table can fire as well. Such chains help separate auditing and aggregation, yet can also cause an initial SQL statement to trigger more operations than expected.

Let us build an example:

- inventory: inventory table.
- inventory_audit: insert/update/delete history.
- daily_inventory_activity: daily activity counters.

Flow:

    INSERT / UPDATE / REPLACE / UPSERT
                    |
                    v
              inventory trigger
                    |
                    v
             INSERT audit row
                    |
                    v
          inventory_audit trigger
                    |
                    v
       UPDATE daily activity counter

### 8.1. Creating the Tables

    CREATE TABLE daily_inventory_activity (
        activity_date DATE NOT NULL PRIMARY KEY,
        insert_count BIGINT NOT NULL DEFAULT 0,
        update_count BIGINT NOT NULL DEFAULT 0,
        delete_count BIGINT NOT NULL DEFAULT 0
    ) ENGINE = InnoDB;

    CREATE TABLE inventory (
        product_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
        sku VARCHAR(40) NOT NULL,
        quantity INT NOT NULL,
        updated_at TIMESTAMP NOT NULL
            DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_inventory_sku (sku)
    ) ENGINE = InnoDB;

    CREATE TABLE inventory_audit (
        audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        product_id BIGINT UNSIGNED NOT NULL,
        event_type VARCHAR(10) NOT NULL,
        old_quantity INT NULL,
        new_quantity INT NULL,
        event_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_audit_event_time (event_time)
    ) ENGINE = InnoDB;

### 8.2. Trigger Auditing Inserts

    CREATE TRIGGER inventory_after_insert
    AFTER INSERT ON inventory
    FOR EACH ROW
    INSERT INTO inventory_audit (
        product_id,
        event_type,
        old_quantity,
        new_quantity
    )
    VALUES (
        NEW.product_id,
        'INSERT',
        NULL,
        NEW.quantity
    );

### 8.3. Trigger Auditing Updates

    CREATE TRIGGER inventory_after_update
    AFTER UPDATE ON inventory
    FOR EACH ROW
    INSERT INTO inventory_audit (
        product_id,
        event_type,
        old_quantity,
        new_quantity
    )
    VALUES (
        NEW.product_id,
        'UPDATE',
        OLD.quantity,
        NEW.quantity
    );

### 8.4. Trigger Auditing Deletes

    CREATE TRIGGER inventory_after_delete
    AFTER DELETE ON inventory
    FOR EACH ROW
    INSERT INTO inventory_audit (
        product_id,
        event_type,
        old_quantity,
        new_quantity
    )
    VALUES (
        OLD.product_id,
        'DELETE',
        OLD.quantity,
        NULL
    );

### 8.5. Summary Trigger When an Audit Row Is Inserted

    CREATE TRIGGER inventory_audit_after_insert
    AFTER INSERT ON inventory_audit
    FOR EACH ROW
    BEGIN
        INSERT INTO daily_inventory_activity (
            activity_date,
            insert_count,
            update_count,
            delete_count
        )
        VALUES (
            DATE(NEW.event_time),
            NEW.event_type = 'INSERT',
            NEW.event_type = 'UPDATE',
            NEW.event_type = 'DELETE'
        )
        AS incoming
        ON DUPLICATE KEY UPDATE
            insert_count =
                insert_count + incoming.insert_count,
            update_count =
                update_count + incoming.update_count,
            delete_count =
                delete_count + incoming.delete_count;
    END;

The last trigger uses an upsert to create the daily summary row or increment counters if the date already exists. This is a nested trigger chain across distinct tables. It is not a recursive loop calling the inventory trigger back on itself.

### 8.6. Sequence on a Normal INSERT

Run:

    INSERT INTO inventory (
        product_id, sku, quantity
    )
    VALUES (
        501, 'SKU-501', 20
    );

Sequence:

1. BEFORE INSERT on inventory if present.
2. Insert inventory row.
3. AFTER INSERT on inventory.
4. Trigger inventory_after_insert inserts a row into inventory_audit.
5. AFTER INSERT on inventory_audit runs.
6. Trigger inventory_audit_after_insert upserts daily_inventory_activity.
7. If daily_inventory_activity has matching triggers, those can run next as well.

A single INSERT into inventory can therefore generate multiple operations on other tables.

### 8.7. Sequence When UPSERT Encounters a Duplicate

Suppose inventory already contains product_id 501. Run:

    INSERT INTO inventory (
        product_id, sku, quantity
    )
    VALUES (
        501, 'SKU-501', 25
    ) AS incoming
    ON DUPLICATE KEY UPDATE
        quantity = incoming.quantity;

Sequence:

1. BEFORE INSERT on inventory.
2. MySQL detects duplicate product_id.
3. BEFORE UPDATE on inventory.
4. Inventory row is updated.
5. AFTER UPDATE on inventory.
6. AFTER UPDATE trigger inserts an audit row with event_type UPDATE.
7. AFTER INSERT on inventory_audit runs.
8. The update_count counter is incremented.

There is no DELETE trigger and no AFTER INSERT on inventory in the duplicate branch.

### 8.8. Sequence When REPLACE Encounters a Duplicate

Suppose inventory already contains product_id 501. Run:

    REPLACE INTO inventory (
        product_id, sku, quantity
    )
    VALUES (
        501, 'SKU-501', 30
    );

Logical sequence:

1. BEFORE INSERT on inventory.
2. MySQL detects duplicate product_id.
3. BEFORE DELETE on inventory.
4. Old row is deleted.
5. AFTER DELETE on inventory.
6. AFTER DELETE trigger inserts an audit row with event_type DELETE.
7. AFTER INSERT on inventory_audit updates delete_count.
8. MySQL inserts the new inventory row.
9. AFTER INSERT on inventory.
10. AFTER INSERT trigger inserts an audit row with event_type INSERT.
11. AFTER INSERT on inventory_audit updates insert_count.

In the audit table, a single REPLACE can produce two records: DELETE of the old row and INSERT of the new row. Both delete_count and insert_count increment.

### 8.9. Why Observe the Entire Chain?

If a dashboard only counts AFTER INSERT on inventory, a REPLACE can bump the insert count without reflecting that the old row was deleted. If code only watches UPDATE, duplicate upserts will not be captured as updates if only insert triggers are tracked. Design audits around actual row events, not the SQL statement name called by the application.

## 9. BEFORE Triggers Can Modify Input Rows

In BEFORE INSERT and BEFORE UPDATE, you can assign values to NEW columns:

    CREATE TRIGGER inventory_before_insert
    BEFORE INSERT ON inventory
    FOR EACH ROW
    SET NEW.sku = UPPER(TRIM(NEW.sku));

With an upsert, BEFORE INSERT runs for each input row even if execution later switches to the UPDATE branch. BEFORE UPDATE can also normalize values on the existing row when the duplicate branch is taken.

Do not place the same normalization in multiple triggers without explicit ordering. If multiple BEFORE INSERT triggers modify NEW.sku, the result depends on trigger order.

Notes:

- OLD is read-only.
- In BEFORE triggers, NEW can be modified if appropriate UPDATE privileges are held.
- AFTER triggers cannot modify the written row via SET NEW.
- NEW for an AUTO_INCREMENT column in BEFORE INSERT is 0, not yet the final allocated sequence number.
- Triggers cannot reference generated columns via OLD/NEW in the usual writable way.

## 10. Multiple Triggers for the Same Event and Timing

MySQL 8.4 allows multiple triggers on the same table with the same event and timing, such as two BEFORE UPDATE triggers.

By default, triggers with the same event and timing execute in creation order. You can control order with:

- FOLLOWS other_trigger_name: the new trigger runs after the specified trigger.
- PRECEDES other_trigger_name: the new trigger runs before the specified trigger.

Example:

    CREATE TRIGGER inventory_before_insert_validate
    BEFORE INSERT ON inventory
    FOR EACH ROW
    SET NEW.quantity = GREATEST(NEW.quantity, 0);

    CREATE TRIGGER inventory_before_insert_normalize
    BEFORE INSERT ON inventory
    FOR EACH ROW FOLLOWS inventory_before_insert_validate
    SET NEW.sku = UPPER(TRIM(NEW.sku));

FOLLOWS and PRECEDES only order triggers sharing the same event and timing on the same table. They do not create a global ordering between BEFORE INSERT and AFTER INSERT or between triggers on different tables.

When adding a new trigger to a system that already has multiple triggers, verify actual execution order and test every REPLACE/upsert branch.

## 11. Multi-Row INSERT/REPLACE/UPSERT Runs Row by Row

Example:

    INSERT INTO inventory (
        product_id, sku, quantity
    )
    VALUES
        (501, 'SKU-501', 10),
        (502, 'SKU-502', 20),
        (503, 'SKU-503', 30)
    AS incoming
    ON DUPLICATE KEY UPDATE
        quantity = incoming.quantity;

Each input row follows its own branch:

- Row 501 may insert.
- Row 502 may collide and update.
- Row 503 may insert.

Therefore, the same statement can fire both the INSERT chain and the UPDATE chain. With multi-row REPLACE, each row may have zero duplicates, one duplicate, or multiple conflicting rows. Total trigger invocations depend on the rows actually affected, not just the number of SQL statements.

When triggers write audits, design the audit table to capture each row event. Never assume a multi-row statement produces exactly one audit record.

## 12. Trigger Errors and Statement Atomicity

MySQL handles trigger errors according to these principles:

- If a BEFORE trigger errors, the corresponding row operation is not performed.
- AFTER triggers run only when the BEFORE trigger and row operation succeed.
- An error in a BEFORE or AFTER trigger causes the invoking statement to fail.
- With transactional tables such as InnoDB, statement failure rolls back the statement's changes, including transactional changes made by triggers.
- With nontransactional tables, changes made before the error point cannot be rolled back.

For example, AFTER INSERT on inventory inserts an audit row and the audit trigger updates the summary. If the summary trigger errors and all tables are InnoDB, the entire initial statement fails and related changes in the statement's transaction roll back.

Do not mix InnoDB and MyISAM tables in a trigger chain if atomicity is required. If a trigger has already written to a nontransactional table and the statement later fails, the nontransactional change may persist.

### 12.1. Triggers Do Not Manage Transactions Themselves

Triggers must not execute statements that start or end transactions, such as:

- START TRANSACTION
- COMMIT
- ROLLBACK

A trigger executes as part of the statement that fired it. Never create an independent transaction inside a trigger.

ROLLBACK TO SAVEPOINT has specific rules and is allowed in some contexts, but does not turn a trigger into an independent transaction owner.

### 12.2. Do Not Modify a Table Used by the Triggering Statement

A stored function or trigger cannot modify a table that is already being used for reading or writing by the statement that fired the trigger. For example, a trigger on inventory cannot run another UPDATE on inventory while the original statement is modifying inventory.

Designing trigger chains across separate tables like inventory → inventory_audit → daily_inventory_activity is easier to reason about and control. Avoid creating cycles like A → B → A or mutual dependencies across multiple triggers.

## 13. Trigger Chains Can Arise from Operations on Other Tables

Triggers do not only run for the initial table. If trigger A performs DML on table B and B has matching triggers, the operation on B can fire B's triggers.

Example:

    CREATE TRIGGER order_after_insert
    AFTER INSERT ON orders
    FOR EACH ROW
    INSERT INTO order_audit(order_id, event_type)
    VALUES (NEW.order_id, 'INSERT');

    CREATE TRIGGER order_audit_after_insert
    AFTER INSERT ON order_audit
    FOR EACH ROW
    UPDATE daily_order_count
    SET total_count = total_count + 1
    WHERE activity_date = CURRENT_DATE();

Actual chain:

    INSERT orders
      -> AFTER INSERT orders
        -> INSERT order_audit
          -> AFTER INSERT order_audit
            -> UPDATE daily_order_count

Each step can add locks, I/O, trigger execution, and potential failure points. Document a dependency diagram so operators know which tables a simple INSERT command can touch.

Do not leave trigger chains dependent on accidental ordering. When ordering is needed among multiple triggers on the same event/timing, use FOLLOWS/PRECEDES and record it in migrations.

## 14. Operations That Do Not Fire Triggers as Expected

| Operation | Related Triggers |
|---|---|
| INSERT | INSERT triggers |
| LOAD DATA | INSERT triggers for loaded rows |
| REPLACE | INSERT and DELETE triggers per actual branch |
| INSERT ... ON DUPLICATE KEY UPDATE | BEFORE INSERT, then INSERT or UPDATE triggers |
| UPDATE | UPDATE triggers |
| DELETE | DELETE triggers |
| TRUNCATE TABLE | Does not fire DELETE triggers |
| DROP TABLE | Does not fire DELETE triggers |
| Drop partition | Does not fire DELETE triggers per row |
| Foreign key cascade | Does not fire triggers on child table for cascaded operations |
| Data changes via APIs bypassing MySQL SQL | Do not fire SQL triggers |

If the system uses TRUNCATE to purge data, you cannot rely on DELETE triggers to audit each removed row. If auditing is required, design a separate workflow before truncating.

## 15. Triggers and Replication

Trigger behavior on a replica depends on the replication format:

- Statement-based replication: the statement executes on the replica; corresponding triggers on the replica can also run.
- Row-based replication: triggers on the source already produced the row changes; those row changes are logged and applied on the replica, so triggers on the replica do not re-run for changes caused by the source statement.
- Mixed mode: MySQL selects the appropriate logging format based on the statement and safety rules.

Do not assume audit triggers will run twice on a replica. Conversely, do not configure differing triggers between source and replica under row-based replication if data consistency is expected.

Certain REPLACE ... SELECT and INSERT ... SELECT ... ON DUPLICATE KEY UPDATE statements may be flagged unsafe for statement-based replication because outcomes depend on row order or unique key conditions. Check warnings, binlog format, and replication plans before using these forms in critical workloads.

## 16. Privileges and Trigger Security Context

Triggers have a DEFINER. When a trigger runs, privileges are checked under the DEFINER's security context, not solely the application account that issued INSERT/UPDATE/DELETE.

Privileges to review:

- TRIGGER on the attached table to create the trigger.
- SELECT if the body reads OLD/NEW or reads tables.
- UPDATE if assigning SET NEW.column = value.
- Required DML privileges on audit, summary, or other tables accessed by the trigger.

Do not use root as DEFINER merely so the trigger can write to any table. Create a dedicated account with least privilege. The application account may need only DML privileges on business tables; the trigger executes audit writes under the DEFINER's privileges.

Inspect DEFINER with:

    SHOW CREATE TRIGGER inventory_after_insert;

    SELECT
        TRIGGER_NAME,
        EVENT_MANIPULATION,
        EVENT_OBJECT_TABLE,
        ACTION_TIMING,
        DEFINER,
        ACTION_ORDER,
        SQL_MODE
    FROM information_schema.TRIGGERS
    WHERE TRIGGER_SCHEMA = DATABASE()
    ORDER BY EVENT_OBJECT_TABLE,
             EVENT_MANIPULATION,
             ACTION_TIMING,
             ACTION_ORDER;

## 17. Limitations Inside a Trigger Body

Triggers run synchronously inside the statement that invoked them. Key limitations:

- Triggers cannot return a result set to the client.
- Triggers cannot use dynamic SQL such as PREPARE/EXECUTE.
- Triggers cannot call procedures that return result sets to the client or use dynamic SQL.
- Triggers cannot execute START TRANSACTION, COMMIT, or ROLLBACK.
- Triggers cannot modify a table already used by the triggering statement.
- Triggers have no RETURN to return a value; use LEAVE to exit a labeled block when needed.
- Triggers attach to regular tables, not directly to views or TEMPORARY tables.

Because triggers run synchronously, avoid long logic, calling external services, or heavy processing. Keep the body short with predictable cost.

## 18. When to Choose REPLACE vs. Upsert

| Need | Usually Suitable Choice | Reason |
|---|---|---|
| Create row if missing, update a few columns if present | INSERT ... ON DUPLICATE KEY UPDATE | Preserves existing row and modifies only specified columns |
| Replace entire row from new payload, accepting delete/insert semantics | REPLACE | Old row is deleted, new row is created |
| Simply ignore duplicates | INSERT IGNORE | Neither updates nor deletes old row |
| Merge across multiple business keys | Explicit transaction and logic | Avoids ambiguous row selection from multiple UNIQUE indexes |
| Require accurate insert/update/delete auditing | Upsert with triggers and audits designed per event | Each branch has distinct event triggers |

Before using REPLACE, answer:

- Do foreign keys reference the replaced row?
- Are there DELETE triggers writing audits or deleting related data?
- Could multiple UNIQUE indexes match different rows?
- Will omitted columns be reset to DEFAULT?
- Must created_at, owner_id, version, or current state be preserved?
- Are affected rows and AUTO_INCREMENT interpreted correctly by the application?

Before using upsert, answer:

- Which duplicate key identifies the row to update?
- Does the table have multiple UNIQUE indexes?
- Does BEFORE INSERT run side logic even when ultimately updating?
- Do BEFORE/AFTER UPDATE triggers write audits properly?
- Could the UPDATE clause unintentionally overwrite columns the caller did not intend to change?
- Has VALUES() been replaced with a row alias in new code?

## 19. Workflow for Testing a Trigger Chain

Do not verify only the final state of the primary table. Check audit tables, summary tables, foreign keys, and affected rows too.

### 19.1. Preparing Baseline Data

    DELETE FROM inventory;
    DELETE FROM inventory_audit;
    DELETE FROM daily_inventory_activity;

    INSERT INTO inventory(product_id, sku, quantity)
    VALUES (501, 'SKU-501', 10);

Verify the audit has one INSERT event.

### 19.2. Testing a New INSERT

    INSERT INTO inventory(product_id, sku, quantity)
    VALUES (502, 'SKU-502', 15);

Expected:

- inventory has row 502.
- audit has one INSERT event for 502.
- summary increments insert_count.
- No UPDATE or DELETE audit for 502.

### 19.3. Testing a Duplicate UPSERT

    INSERT INTO inventory(product_id, sku, quantity)
    VALUES (501, 'SKU-501', 18) AS incoming
    ON DUPLICATE KEY UPDATE
        quantity = incoming.quantity;

Expected:

- Row 501 remains the same entity by product_id.
- quantity changes to 18.
- audit has an UPDATE event.
- summary increments update_count.
- No DELETE audit for 501.
- Both BEFORE INSERT and BEFORE UPDATE may have run.

### 19.4. Testing a Duplicate REPLACE

    REPLACE INTO inventory(product_id, sku, quantity)
    VALUES (501, 'SKU-501', 25);

Expected:

- Old row 501 is deleted per REPLACE semantics.
- New row 501 is inserted.
- audit has DELETE and INSERT.
- summary increments delete_count and insert_count.
- UPDATE triggers do not run for the REPLACE duplicate branch.

### 19.5. Testing Duplicate via Secondary UNIQUE Key

Create a row with a different product_id but an existing SKU. Try REPLACE and confirm the exact conflicting row is deleted. If multiple unique indexes exist, construct data where two indexes conflict with two different rows to verify the risk of multiple rows being deleted.

### 19.6. Testing Trigger Errors

Temporarily add a trigger intentionally raising SIGNAL when quantity is negative. Verify:

- If a BEFORE trigger errors, the row is not written.
- If an AFTER trigger errors, the statement fails.
- With InnoDB, audit and summary changes created by that statement also roll back.
- The application receives the error and does not mark the request successful.

Do not test by modifying production triggers. Use a test schema or sandbox database.

## 20. Common Mistakes

- Thinking REPLACE is equivalent to UPDATE.
- Thinking the duplicate branch of REPLACE runs UPDATE triggers.
- Thinking the duplicate branch of upsert runs DELETE triggers.
- Thinking BEFORE INSERT does not run when upsert switches to UPDATE.
- Auditing only AFTER INSERT and missing the update branch of upsert.
- Auditing only UPDATE and missing the delete/insert of REPLACE.
- Thinking REPLACE keeps omitted old columns.
- Failing to realize REPLACE can delete multiple rows due to multiple UNIQUE indexes.
- Forgetting to grant DELETE privilege to accounts using REPLACE.
- Ignoring ON DELETE CASCADE when running REPLACE on a parent row.
- Expecting child triggers to run when foreign key cascade deletes rows.
- Using affected rows to infer a single business action without considering branches.
- Using VALUES(column) in new code despite deprecation.
- Upserting on tables with multiple UNIQUE indexes without disambiguating the target row.
- Forgetting triggers run FOR EACH ROW for every row in a multi-row statement.
- Not controlling FOLLOWS/PRECEDES when multiple triggers share event/timing.
- Creating trigger loops across tables or modifying the table already used by the statement.
- Writing audits to nontransactional tables and assuming rollback will delete the audit.
- Relying on DELETE triggers to audit TRUNCATE or foreign key cascades.
- Failing to test differences between statement-based and row-based replication.

## 21. Pre-Production Checklist for REPLACE/Upsert

- Confirmed whether the statement truly needs insert, update, or delete-and-insert.
- Inspected all PRIMARY KEY and UNIQUE indexes.
- Evaluated cases where multiple unique keys match different rows.
- Inspected INSERT, UPDATE, and DELETE triggers on the target table.
- Mapped the BEFORE/AFTER chain for both insert and duplicate branches.
- Checked triggers writing to other tables and downstream trigger chains.
- Verified ordering of multiple triggers sharing event/timing.
- Evaluated omitted columns in REPLACE receiving DEFAULT.
- Verified AUTO_INCREMENT and LAST_INSERT_ID() behavior.
- Verified foreign key cascades and impact on child rows.
- Confirmed child table triggers do not run for foreign key cascades.
- Confirmed all tables in chains requiring atomicity are transactional.
- Checked trigger DEFINER and grants.
- Replaced VALUES(column) with row aliases in new code.
- Checked affected rows, warnings, and replication format.
- Tested new insert, duplicate update, replace duplicate, and trigger errors.
- Inspected main, audit, and summary tables after each test.
- Measured the cost of the trigger chain under multi-row workloads.

## 22. References

- MySQL 8.4 Reference Manual — REPLACE Statement: https://dev.mysql.com/doc/refman/8.4/en/replace.html
- MySQL 8.4 Reference Manual — INSERT ... ON DUPLICATE KEY UPDATE: https://dev.mysql.com/doc/refman/8.4/en/insert-on-duplicate.html
- MySQL 8.4 Reference Manual — CREATE TRIGGER Statement: https://dev.mysql.com/doc/refman/8.4/en/create-trigger.html
- MySQL 8.4 Reference Manual — Trigger Syntax and Examples: https://dev.mysql.com/doc/refman/8.4/en/trigger-syntax.html
- MySQL 8.4 Reference Manual — Restrictions on Stored Programs: https://dev.mysql.com/doc/refman/8.4/en/stored-program-restrictions.html
- MySQL 8.4 Reference Manual — Replication and Triggers: https://dev.mysql.com/doc/refman/8.4/en/replication-features-triggers.html

REPLACE resolves duplicates by deleting conflicting rows and inserting a new row, so it can fire BEFORE INSERT, DELETE triggers for old rows, and AFTER INSERT. INSERT ... ON DUPLICATE KEY UPDATE always runs BEFORE INSERT, followed by either AFTER INSERT, or BEFORE UPDATE and AFTER UPDATE. Triggers writing to other tables can form downstream trigger chains; foreign key cascades do not fire child table triggers. For accurate auditing and aggregation, design around actual per-row events and verify all UNIQUE indexes, trigger ordering, transactional engines, and replication format. Use REPLACE only when delete-and-insert is genuinely desired; if you need to preserve the entity and selectively update columns, upsert usually expresses the intent properly.
