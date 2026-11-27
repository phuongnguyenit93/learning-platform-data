# Transaction Boundaries and Handling Errors Raised in Triggers

A trigger is a stored program automatically executed by MySQL when an INSERT, UPDATE, or DELETE event occurs on a table. A trigger runs as part of the statement that fired it. Therefore, a trigger does not own an independent transaction: transactional changes made by a trigger join the same transaction and statement boundary as the statement calling the trigger.

This has important consequences when an error occurs. If a trigger raises an unhandled error, the statement that fired the trigger fails. With InnoDB, MySQL rolls back the changes of that entire statement, including changes to the source table and any transactional tables written by the trigger. If the statement sits inside a larger transaction, previously successful statements remain active in the transaction; the caller must decide whether to COMMIT or ROLLBACK the entire business operation.

This lesson within DATABASE_MYSQL covers how triggers participate in the caller's transaction, distinguishing statement rollback from transaction rollback, controlling errors in BEFORE/AFTER triggers, using SIGNAL and handlers intentionally, and avoiding designs with irreversible side effects.

## 1. Triggers Execute in the Context of the Firing Statement

MySQL supports triggers across two timings and three events:

| Timing | Event | Meaning |
|---|---|---|
| BEFORE | INSERT | Runs before the new row is written |
| AFTER | INSERT | Runs after the new row is written successfully |
| BEFORE | UPDATE | Runs before the existing row is updated |
| AFTER | UPDATE | Runs after the row is updated successfully |
| BEFORE | DELETE | Runs before the row is deleted |
| AFTER | DELETE | Runs after the row is deleted successfully |

MySQL triggers are row-level triggers: each trigger is declared FOR EACH ROW. MySQL has no statement-level trigger that executes only once for the entire statement.

If an UPDATE modifies 500 rows, the corresponding trigger can be invoked 500 times. If one row during processing causes the trigger to raise an unhandled error, the statement can fail; with InnoDB, the changes of the whole statement are undone.

### 1.1. OLD and NEW

Triggers use OLD and NEW to access row values:

| Event | OLD | NEW |
|---|---|---|
| INSERT | No old row | Row about to be inserted |
| UPDATE | Value before update | Proposed value after update |
| DELETE | Row about to be deleted | No new row |

In BEFORE INSERT and BEFORE UPDATE, a trigger can assign values to NEW.column to normalize or apply defaults. OLD is read-only. In AFTER triggers, you cannot alter the already-written row through NEW.

Example:

~~~sql
DELIMITER //

CREATE TRIGGER bi_orders_normalize
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    SET NEW.order_code = UPPER(TRIM(NEW.order_code));
END//

DELIMITER ;
~~~

This trigger normalizes the order code before the row is written. Assigning NEW is part of the INSERT statement; it does not create a separate transaction.

### 1.2. Triggers Can Run Multiple Times in One Statement

Example:

~~~sql
UPDATE orders
SET status = 'EXPIRED'
WHERE expires_at < NOW(6)
  AND status = 'OPEN';
~~~

If 10,000 rows match the condition, the AFTER UPDATE trigger is called for each updated row. Never assume a trigger runs once for the entire statement.

This impacts:
- Audit write volume.
- Number of condition checks.
- Number of reads against related tables.
- Locks held and transaction duration.
- Risk of a single failing row failing the entire statement.

Keep triggers short, provide index support for lookups, and avoid unnecessary repeated queries.

## 2. Triggers Do Not Open Separate Transactions

Triggers cannot use transaction control commands such as:

- START TRANSACTION or BEGIN to open a new transaction.
- COMMIT.
- ROLLBACK.
- Other transaction control operations disallowed in triggers.

A trigger always executes in the transaction context of the statement calling it. If there is no explicit transaction, the statement usually auto-commits under autocommit. If the caller already opened a transaction, the trigger joins that transaction.

Example audit trigger:

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;

CREATE TABLE order_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    event_name VARCHAR(40) NOT NULL,
    recorded_at DATETIME(6) NOT NULL,
    PRIMARY KEY (audit_id),
    KEY idx_order_audit_order (order_id)
) ENGINE = InnoDB;
~~~

~~~sql
DELIMITER //

CREATE TRIGGER ai_orders_audit
AFTER INSERT ON orders
FOR EACH ROW
BEGIN
    INSERT INTO order_audit (
        order_id,
        event_name,
        recorded_at
    )
    VALUES (
        NEW.order_id,
        'ORDER_CREATED',
        NOW(6)
    );
END//

DELIMITER ;
~~~

When inserting into orders, the trigger adds an order_audit row in the same transaction. There is no separate COMMIT inside the trigger.

## 3. Autocommit and the Caller's Transaction

### 3.1. autocommit = 1

When autocommit is enabled and there is no explicit transaction, an INSERT/UPDATE/DELETE statement along with all triggers executes as a single unit. If the statement succeeds, transactional changes on the source table and triggers are committed together. If the statement fails, statement changes are rolled back.

~~~sql
INSERT INTO orders(customer_id, status, total_amount)
VALUES (1001, 'OPEN', 250.00);
~~~

If the AFTER INSERT trigger writes the audit successfully, both the orders row and order_audit row commit. If the trigger errors, the statement fails and transactional changes of the statement are undone.

### 3.2. Caller Opens an Explicit Transaction

~~~sql
START TRANSACTION;

INSERT INTO orders(customer_id, status, total_amount)
VALUES (1001, 'OPEN', 250.00);

-- Trigger ai_orders_audit already wrote the audit in the same transaction.

UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = LAST_INSERT_ID();

ROLLBACK;
~~~

After ROLLBACK, both the orders row and the order_audit row created by the trigger disappear because both tables use InnoDB and share the transaction. The UPDATE is also undone.

The trigger cannot commit its audit portion separately to keep it when the caller rolls back. This behavior is essential so business data and transactional audits do not drift apart.

### 3.3. Triggers Do Not Decide Commit Timing

A trigger does not know the application's full business workflow. It only knows the current statement and OLD/NEW data. A transaction may contain:
- Multiple statements from the application.
- One or more called procedures.
- Multiple trigger activations.
- Changes across multiple tables.

The caller is where committing or rolling back the entire transaction is decided, unless a procedure is specifically designed to own the transaction. A trigger must never decide on its own to end that transaction.

## 4. Statement Rollback When a Trigger Raises an Error

With InnoDB, the DML statement and transactional operations performed by the trigger form an atomic unit. If a trigger raises an unhandled error, the statement firing the trigger fails and the statement's changes are undone.

This applies whether the error occurs in a BEFORE trigger or an AFTER trigger.

### 4.1. Errors in a BEFORE Trigger

A BEFORE trigger runs before the row is written. If the trigger raises SIGNAL or a statement inside the trigger errors:
- The new row is not added, or the old row is not updated/deleted.
- Transactional changes of the statement are undone.
- The caller receives the error if the condition is not caught by a handler.

Example:

~~~sql
DELIMITER //

CREATE TRIGGER bi_orders_validate
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    IF NEW.total_amount <= 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Order amount must be positive';
    END IF;
END//

DELIMITER ;
~~~

Test:

~~~sql
INSERT INTO orders(customer_id, status, total_amount)
VALUES (1001, 'OPEN', 0);
~~~

The statement fails due to the business rule. No row is written.

### 4.2. Errors in an AFTER Trigger

An AFTER trigger runs after the base row operation, yet still inside the same statement. If an AFTER trigger errors, with InnoDB both the base row change and transactional changes already made by triggers belonging to that statement roll back.

Example modifying the audit trigger to intentionally reject a status:

~~~sql
DELIMITER //

CREATE TRIGGER ai_orders_audit
AFTER INSERT ON orders
FOR EACH ROW
BEGIN
    INSERT INTO order_audit (
        order_id,
        event_name,
        recorded_at
    )
    VALUES (
        NEW.order_id,
        'ORDER_CREATED',
        NOW(6)
    );

    IF NEW.status = 'REJECTED' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Rejected orders cannot be inserted';
    END IF;
END//

DELIMITER ;
~~~

Test:

~~~sql
INSERT INTO orders(customer_id, status, total_amount)
VALUES (1001, 'REJECTED', 250.00);
~~~

Even though the trigger executed INSERT into order_audit before SIGNAL, both the orders INSERT and the order_audit INSERT roll back if both tables use InnoDB. AFTER means after the row operation at the trigger level—it does not mean the statement has committed.

### 4.3. A Trigger Error Does Not Automatically Roll Back the Entire Transaction

If the statement runs inside an explicit transaction, a normal error in a trigger rolls back only the statement. Earlier successful statements in the transaction remain uncommitted and active.

~~~sql
START TRANSACTION;

UPDATE account
SET balance = balance - 50
WHERE account_id = 1;

-- This INSERT fires the trigger and the trigger raises an error.
INSERT INTO orders(customer_id, status, total_amount)
VALUES (1001, 'REJECTED', 250.00);

-- The transaction may still remain active after a regular statement error.
SELECT balance
FROM account
WHERE account_id = 1;

-- Caller decides:
ROLLBACK;
~~~

The earlier account UPDATE is not automatically undone merely because the INSERT failed. If the full business operation requires not keeping the balance deduction, the caller must ROLLBACK the transaction.

An important exception is a deadlock: InnoDB can roll back the entire transaction chosen as the deadlock victim. A lock wait timeout by default usually rolls back only the waiting statement, unless innodb_rollback_on_timeout changes that behavior.

## 5. Multi-Row Statements and Single-Row Errors

Because triggers are row-level, a multi-row statement can invoke a trigger multiple times.

~~~sql
INSERT INTO orders(customer_id, status, total_amount)
VALUES
    (1001, 'OPEN', 100.00),
    (1002, 'OPEN', 200.00),
    (1003, 'REJECTED', 300.00),
    (1004, 'OPEN', 400.00);
~~~

Suppose the AFTER INSERT trigger raises an error when NEW.status = 'REJECTED'. With InnoDB:
- The trigger runs for rows as the statement processes them.
- When the REJECTED row causes an unhandled error, the INSERT statement fails.
- Earlier rows inserted within the same statement are rolled back.
- Transactional audit rows written by the trigger within the same statement are also rolled back.
- No partial success of the statement is retained.

Do not design around an assumption like "the first three valid rows stay while the failing row is skipped" when using a single multi-row InnoDB statement. If each row needs independent acceptance, split into separate statements or process row by row within transactions according to an explicit policy.

### 5.1. One Multi-Row Statement Is Not Multiple Transactions

With autocommit enabled, a multi-row INSERT is still one statement and one automatic transaction. The trigger is invoked multiple times, yet all those invocations belong to the same statement transaction.

If each row needs an independent outcome, the application can:
- Send individual INSERTs with autocommit enabled.
- Batch in small groups with explicit transaction boundaries.
- Use a staging table, validate data first, and then move to the target table.
- Use a stored procedure processing row by row with savepoints/handlers where appropriate.

Each option has different round-trip cost, throughput, and error semantics.

## 6. Handlers Inside Triggers

A trigger is a stored program and can declare condition handlers inside a compound block. A handler can handle a condition and then CONTINUE or EXIT the block according to handler rules.

However, a handler does not create a new transaction and cannot COMMIT/ROLLBACK. Because the trigger belongs to the statement calling it, error handling decisions must uphold the statement's contract.

### 6.1. Handlers Should Not Swallow Data Errors

Example of a CONTINUE handler catching every SQLEXCEPTION:

~~~sql
DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
    SET @trigger_error = TRUE;
~~~

If used this way to swallow errors while writing audits, the base statement can proceed and commit even though the audit was never written. That produces an invalid business state when auditing is mandatory.

Never catch every error and silently continue. Only use CONTINUE when business rules clearly define that the condition is ignorable and the caller has a way to observe the outcome.

### 6.2. EXIT Handler and RESIGNAL

An EXIT handler can be used to re-raise an error so the condition propagates to the calling statement:

~~~sql
DELIMITER //

CREATE TRIGGER ai_orders_audit
AFTER INSERT ON orders
FOR EACH ROW
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        RESIGNAL;
    END;

    INSERT INTO order_audit (
        order_id,
        event_name,
        recorded_at
    )
    VALUES (
        NEW.order_id,
        'ORDER_CREATED',
        NOW(6)
    );
END//

DELIMITER ;
~~~

This handler does not alter the transaction scope. It merely re-raises the error. When the error escapes the trigger, the outer INSERT statement fails; with InnoDB, the statement rolls back.

If no extra handling is needed, letting the error propagate naturally is also clean and clear. Do not add handlers just to write boilerplate code.

### 6.3. GET DIAGNOSTICS Inside a Handler

When needing to classify errors or attach context, a handler can read diagnostics:

~~~sql
DECLARE v_sqlstate CHAR(5);
DECLARE v_errno INT;
DECLARE v_message TEXT;

DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    GET DIAGNOSTICS CONDITION 1
        v_sqlstate = RETURNED_SQLSTATE,
        v_errno = MYSQL_ERRNO,
        v_message = MESSAGE_TEXT;

    RESIGNAL;
END;
~~~

GET DIAGNOSTICS should be called before executing any other statement that might overwrite the diagnostics area. If you write a log row into an InnoDB table inside a handler and then RESIGNAL, that log row is also part of the transaction and can roll back with the statement. Never expect a transactional log row to survive statement rollback.

## 7. SIGNAL: Rejecting Operations by Business Rule

SIGNAL lets a trigger proactively raise a condition. SQLSTATE 45000 is commonly used for application-defined errors.

Example preventing excessive discounts:

~~~sql
DELIMITER //

CREATE TRIGGER bu_order_item_validate_discount
BEFORE UPDATE ON order_item
FOR EACH ROW
BEGIN
    IF NEW.discount_percent < 0
       OR NEW.discount_percent > 50 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Discount must be between 0 and 50';
    END IF;
END//

DELIMITER ;
~~~

When an UPDATE violates the rule:
- The trigger raises an error.
- The UPDATE statement fails.
- Transactional changes of the statement roll back.
- The caller receives SQLSTATE 45000 and the message.

### 7.1. Choosing Business Errors vs. Constraints

Use SIGNAL when expressing a business rule that cannot be modeled directly with CHECK, FOREIGN KEY, or UNIQUE constraints.

Prefer constraints for simple, universal data rules because constraints are enforced by the database across every write path. Triggers fit logic needing OLD/NEW references, audit generation, or coordination with other tables. Do not replace all constraints with triggers.

### 7.2. Stable Error Messages

Applications should classify errors by SQLSTATE or stable business error codes rather than parsing arbitrary message strings. Message wording can change across releases; SQLSTATE and error conventions should be managed as part of the contract.

## 8. Do Changes Inside a Trigger Roll Back with the Statement?

The answer depends on the storage engine of the tables touched by the trigger.

### 8.1. All Tables Use InnoDB

If both the base table and audit table are InnoDB:
- Base row changes.
- INSERT/UPDATE/DELETE statements executed by the trigger.
- Transactional changes from permitted called routines.

all participate in the same transaction. When the statement fails, transactional changes of the statement roll back. When the caller rolls back the transaction, all uncommitted changes also roll back.

### 8.2. A Non-Transactional Table Is Involved

If a trigger writes to a MyISAM table while the base table is InnoDB, you cannot expect ROLLBACK to undo the MyISAM change.

Example:

~~~sql
CREATE TABLE order_audit_nontransactional (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    order_id BIGINT UNSIGNED NOT NULL,
    event_name VARCHAR(40) NOT NULL
) ENGINE = MyISAM;
~~~

If the trigger INSERTs into the MyISAM table and then raises an error:
- InnoDB changes of the statement may roll back.
- The MyISAM change has no corresponding rollback guarantee and may persist.
- The audit may record an event for a business row that does not exist.

For consistent auditing, use InnoDB for both base and audit tables. Avoid mixing transactional and nontransactional engines in the same business operation requiring atomicity.

### 8.3. Side Effects Outside the Database

A MySQL transaction cannot undo:
- Emails already sent.
- HTTP requests already executed.
- Files already written.
- Messages pushed to an external broker outside the transaction.
- Actions in another system not sharing the transaction.

Triggers are not the right place to perform side effects outside the database. If a notification must be sent when an order is created, write an outbox event in the same InnoDB transaction and have a worker send it after COMMIT.

## 9. Designing Consistent Audit Triggers

An audit trigger typically records a row's old and new state. Example:

~~~sql
CREATE TABLE order_status_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    old_status VARCHAR(20) NOT NULL,
    new_status VARCHAR(20) NOT NULL,
    changed_at DATETIME(6) NOT NULL,
    PRIMARY KEY (audit_id),
    KEY idx_order_status_audit_order_time (order_id, changed_at)
) ENGINE = InnoDB;
~~~

~~~sql
DELIMITER //

CREATE TRIGGER au_orders_status_audit
AFTER UPDATE ON orders
FOR EACH ROW
BEGIN
    IF NOT (OLD.status <=> NEW.status) THEN
        INSERT INTO order_status_audit (
            order_id,
            old_status,
            new_status,
            changed_at
        )
        VALUES (
            NEW.order_id,
            OLD.status,
            NEW.status,
            NOW(6)
        );
    END IF;
END//

DELIMITER ;
~~~

The NULL-safe equality operator <=> compares safely when columns can be NULL. In this example status is NOT NULL, yet this comparison pattern is valuable when applied to nullable columns.

If the UPDATE fails after the trigger writes an audit, both the order change and the statement's audit roll back under InnoDB. If the caller rolls back a larger transaction, the audit rolls back too.

### 9.1. Audit Triggers Do Not Replace Comprehensive Security Auditing

Triggers record row changes at the database level, but may not know:
- Who the real end user is if the application shares one database account.
- The business reason for the change.
- The request ID or trace ID from the API layer.
- Authentication details external to the database.

If that information is needed, the application can pass metadata through a controlled mechanism or write audits at the application layer. Avoid relying on session user variables without managing connection pools and request boundaries.

## 10. Errors in BEFORE and AFTER Triggers: Different Timing, Same Transaction

| Aspect | BEFORE | AFTER |
|---|---|---|
| Timing | Before the row change is finalized | After the row operation at trigger level |
| Can assign NEW | Yes, for INSERT/UPDATE | Cannot modify row via NEW |
| Common purpose | Validate, normalize, set values | Audit, update secondary tables |
| On SIGNAL | Statement fails before finalizing row change | Statement fails even though row passed write step |
| InnoDB rollback | Statement rolls back | Statement rolls back, including transactional audit changes |

Never confuse AFTER with "committed". AFTER only describes trigger order relative to the row operation. COMMIT belongs to the caller's transaction and happens afterward.

## 11. Triggers and Multi-Row Statements

The following commands can fire triggers per row:
- Multi-row INSERT.
- INSERT ... SELECT.
- LOAD DATA.
- Multi-row UPDATE.
- Multi-row DELETE.
- REPLACE for the processed rows.

Verify whether trigger cost scales reasonably with row count. One per-row query inside a trigger can turn a bulk operation into thousands or millions of lookups.

### 11.1. Avoid Unindexed Queries Inside Triggers

If a trigger checks:

~~~sql
SELECT COUNT(*)
INTO v_count
FROM customer_order
WHERE customer_id = NEW.customer_id;
~~~

ensure customer_id has an appropriate index. Otherwise, every row firing the trigger can scan the related table.

### 11.2. Do Not Update the Table Used by the Statement

MySQL restricts triggers/functions from modifying a table already used by the statement calling them. For example, an UPDATE on orders firing a trigger that runs UPDATE on orders again can cause error 1442.

Do not use triggers to recursively update the table that fired the trigger. In BEFORE INSERT/UPDATE, assign NEW.column to adjust the current row. For multi-row update logic, write it explicitly in statements or procedures outside triggers.

### 11.3. Foreign Key Cascades Do Not Fire Triggers

Operations performed by foreign key ON DELETE CASCADE or ON UPDATE CASCADE do not fire triggers on the cascaded tables. If cascaded changes must also be audited, do not assume child-table triggers will run. Design auditing via another mechanism and test against actual foreign key relationships.

TRUNCATE TABLE is also not equivalent to row-by-row DELETE and does not fire DELETE triggers. If trigger auditing is required per deleted row, use DELETE with an appropriate condition.

## 12. Deadlocks and Lock Waits Caused by Triggers

Triggers can read or write additional tables, thereby expanding the set of locks required by a statement.

Example:
- Transaction A updates orders, and a trigger writes order_audit.
- Transaction B updates order_audit, and then updates orders.
- The two transactions lock in opposite orders and can deadlock.

To reduce risk:
- Keep triggers short.
- Access related tables in a consistent order.
- Create indexes for row-lookup predicates inside triggers.
- Avoid repeated logic or unnecessary updates across many tables.
- Never keep transactions open while the application waits for user input.
- Handle deadlocks by retrying the full transaction in the caller.

### 12.1. Deadlocks Differ from Regular Trigger Errors

If a trigger raises SIGNAL, typically the statement fails and rolls back. If InnoDB detects a deadlock, the entire victim transaction may roll back. The caller must distinguish error codes and not simply replay the last statement.

### 12.2. Lock Wait Timeout

A lock wait timeout by default usually rolls back only the waiting statement while the transaction may remain open. The innodb_rollback_on_timeout setting can change this behavior to roll back the entire transaction. Check the actual configuration:

~~~sql
SELECT
    @@GLOBAL.innodb_lock_wait_timeout,
    @@GLOBAL.innodb_rollback_on_timeout;
~~~

For multi-step business workflows, the safest policy is typically rolling back the entire transaction and retrying from the start if operations are idempotent.

## 13. CREATE/DROP TRIGGER DDL and Implicit Commit

CREATE TRIGGER and DROP TRIGGER are DDL statements that can cause an implicit commit. Never place them between DML operations expecting ROLLBACK to undo both data and trigger definitions.

Example that should not be treated as one rollbackable transaction:

~~~sql
START TRANSACTION;

UPDATE orders
SET status = 'PROCESSING'
WHERE order_id = 1001;

CREATE TRIGGER ai_orders_audit
AFTER INSERT ON orders
FOR EACH ROW
INSERT INTO order_audit(order_id, event_name, recorded_at)
VALUES (NEW.order_id, 'ORDER_CREATED', NOW(6));

ROLLBACK;
~~~

DDL can commit the transaction before executing. Trigger changes once created are not rolled back like DML. Trigger migrations should be deployed as a separate schema step with a verification and definition-recovery plan.

Before dropping or creating triggers in production:
- Check existing triggers with SHOW TRIGGERS.
- Back up definitions with SHOW CREATE TRIGGER.
- Check whether applications are actively writing to the table.
- Account for metadata locks and deployment timing.
- Verify triggers after migration completes.

## 14. Triggers and Replication

Triggers can affect how data changes are recorded in the binary log.

- With statement-based replication, the statement re-executes on the replica and corresponding triggers may run on the replica.
- With row-based replication, row changes produced by the source trigger are logged as row events; the replica applies those row events and does not re-run triggers for those row events.
- With MIXED, the server chooses the appropriate format per statement according to logging rules.

Therefore, do not design triggers assuming they always run once per server in a topology. In particular, under statement-based replication, triggers must behave deterministically and required data must be consistent.

Check:

~~~sql
SELECT
    @@GLOBAL.binlog_format AS binlog_format,
    @@GLOBAL.log_bin AS log_bin;
~~~

If a trigger writes audits, verify audit data on both source and replica for the active replication format. Do not add a replica job to re-write the same audit rows if row events already carry changes produced by source triggers, or duplicates may occur.

## 15. Security and Trigger Execution Privileges

Triggers have a DEFINER. When a trigger executes, MySQL runs with the definer's privileges according to stored object security rules. The creator of the trigger needs the TRIGGER privilege on the table plus the privileges needed for operations in the trigger body.

Safe operations:
- Use a dedicated definer with least privilege.
- Do not use root as definer.
- Verify the definer still exists after migrations/restores.
- Verify privileges on audit or secondary tables accessed by the trigger.
- Review SHOW CREATE TRIGGER when investigating permissions.
- Do not grant trigger-modification privileges to ordinary application accounts.

Example inspecting triggers:

~~~sql
SHOW TRIGGERS
FROM app_db
LIKE 'orders';
~~~

~~~sql
SHOW CREATE TRIGGER app_db.ai_orders_audit;
~~~

You can query metadata:

~~~sql
SELECT
    TRIGGER_SCHEMA,
    TRIGGER_NAME,
    EVENT_MANIPULATION,
    EVENT_OBJECT_TABLE,
    ACTION_TIMING,
    ACTION_STATEMENT,
    DEFINER
FROM information_schema.triggers
WHERE TRIGGER_SCHEMA = DATABASE()
ORDER BY EVENT_OBJECT_TABLE, ACTION_TIMING, EVENT_MANIPULATION;
~~~

## 16. Calling Triggers from Applications: Transaction Contract

Applications do not invoke triggers directly. They execute INSERT/UPDATE/DELETE on tables; MySQL runs triggers automatically. Therefore, the application's transaction contract must account for secondary changes generated by triggers.

JDBC example:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO orders(customer_id, status, total_amount) VALUES (?, ?, ?)")) {
        ps.setLong(1, customerId);
        ps.setString(2, "OPEN");
        ps.setBigDecimal(3, totalAmount);
        ps.executeUpdate();

        // Trigger writes order_audit in the same transaction.
        connection.commit();
    } catch (SQLException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
~~~

If a trigger raises an error, executeUpdate throws SQLException. The application rolls back the transaction to ensure prior statements in the same business operation are also undone if the contract requires it.

If there is only one INSERT with autocommit enabled, the statement and triggers commit or roll back as one unit. If the connection is participating in a larger transaction, a trigger error does not automatically decide that the whole transaction must roll back.

### 16.1. Do Not Let Connection Pools Retain Failed Transactions

After an exception:
- Determine whether a transaction is still active.
- Roll back if the caller owns the transaction and the operation failed.
- Restore autocommit/isolation if the application modified them.
- Return the connection to the pool only after state has been cleaned up per pool rules.

Never assume every trigger error automatically rolls back the entire transaction. Deadlocks and certain special errors behave differently from ordinary statement rollbacks.

## 17. Writing an Outbox Instead of External Side Effects in Triggers

If an event must be published when an order is created, a trigger can write a transactional outbox row:

~~~sql
CREATE TABLE event_outbox (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    aggregate_type VARCHAR(40) NOT NULL,
    aggregate_id BIGINT UNSIGNED NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    payload JSON NOT NULL,
    created_at DATETIME(6) NOT NULL,
    published_at DATETIME(6) NULL,
    PRIMARY KEY (event_id),
    KEY idx_outbox_unpublished (published_at, event_id)
) ENGINE = InnoDB;
~~~

~~~sql
DELIMITER //

CREATE TRIGGER ai_orders_outbox
AFTER INSERT ON orders
FOR EACH ROW
BEGIN
    INSERT INTO event_outbox (
        aggregate_type,
        aggregate_id,
        event_type,
        payload,
        created_at
    )
    VALUES (
        'ORDER',
        NEW.order_id,
        'ORDER_CREATED',
        JSON_OBJECT(
            'orderId', NEW.order_id,
            'customerId', NEW.customer_id,
            'totalAmount', NEW.total_amount
        ),
        NOW(6)
    );
END//

DELIMITER ;
~~~

When the orders INSERT commits, the outbox row commits as well. If the transaction rolls back, neither exists. An external worker reads the outbox after commit and dispatches messages.

The worker needs idempotency because it might re-send if it crashes between sending and marking published. Use event_id as an idempotency key on the consumer or receiving system. Triggers only write internal data and never call external services.

## 18. Common Errors

| Error or Misconception | Cause | How to Handle |
|---|---|---|
| AFTER trigger means data is already committed | AFTER only marks timing after row operation, before COMMIT | Understand triggers run in the caller's statement/transaction |
| Triggers have their own transaction | Triggers cannot START/COMMIT/ROLLBACK | Caller owns the transaction |
| Trigger error only rolls back the audit part | With InnoDB, the whole statement rolls back | Design around statement atomicity |
| Trigger error always rolls back whole transaction | Regular statement error does not necessarily roll back the transaction | Caller decides on full business ROLLBACK |
| CONTINUE handler swallows audit errors | Handler lets statement proceed | Catch only ignorable conditions; mandatory audit failures must fail statement |
| Logging in handler then RESIGNAL preserves the log | InnoDB log in same transaction may roll back | Use application logs or separate channel if durable logging is needed |
| MyISAM audit rolls back with InnoDB | MyISAM is nontransactional | Use InnoDB for audit tables |
| Trigger modifies table that fired it | Mutating-table restriction, typically error 1442 | Assign NEW in BEFORE or move logic outside |
| Multi-row INSERT keeps valid rows before failing row | InnoDB statement is an atomic unit | Split statements or process row by row intentionally |
| Triggers run when FK cascade deletes child rows | FK cascades do not fire triggers | Design separate auditing for cascades |
| TRUNCATE runs DELETE triggers | TRUNCATE is DDL, not row-by-row DELETE | Use DELETE when row-level triggers are needed |
| CREATE TRIGGER can be rolled back | DDL causes implicit commit | Deploy triggers via separate migrations |
| Trigger sends email and rollback recalls it | External side effects do not join DB transactions | Use a transactional outbox |
| Triggers cause replication to double-write audits | Confusing row-based and statement-based behavior | Check binlog format and topology |
| Each trigger runs once per statement | MySQL triggers are FOR EACH ROW | Estimate cost by number of affected rows |

## 19. Workflow for Designing Safe Error-Handling Triggers

1. Identify the event (INSERT, UPDATE, or DELETE) and timing (BEFORE/AFTER).
2. Confirm the trigger runs once per row and estimate maximum statement row count.
3. Use constraints for data rules expressible via PRIMARY KEY, UNIQUE, CHECK, or FOREIGN KEY.
4. Use BEFORE to validate or normalize NEW when appropriate.
5. Use AFTER for audits or secondary tables that must reflect written rows.
6. Ensure base tables and critical secondary tables use InnoDB.
7. Never use START TRANSACTION, COMMIT, or ROLLBACK inside triggers.
8. Determine which errors must fail the statement; use SIGNAL with stable SQLSTATE/messages.
9. Use CONTINUE handlers only for genuinely ignorable conditions.
10. Use RESIGNAL when errors must propagate to the caller.
11. Never modify a table already used by the statement firing the trigger.
12. Create indexes for all lookups inside triggers.
13. Avoid external side effects; use an outbox after commit.
14. Assess deadlocks and lock ordering between base and secondary tables.
15. Verify binlog_format and replica behavior.
16. Verify DEFINER and least-privilege grants.
17. Deploy CREATE/DROP TRIGGER as separate DDL migrations.
18. Test statement rollback, transaction rollback, and multi-row failure.
19. Verify JDBC/caller rollback and connection pool cleanup.
20. Monitor statement latency, lock waits, and trigger invocation counts.

## 20. Practice Exercises

### Exercise 1: Triggers and Autocommit

Create orders and order_audit both using InnoDB. Create an AFTER INSERT trigger writing audits. Run INSERT with autocommit enabled and inspect both tables. Confirm both changes committed together.

### Exercise 2: Transaction Rollback

Open START TRANSACTION, INSERT an order, inspect the audit, then ROLLBACK. Confirm both the orders row and order_audit row disappear.

### Exercise 3: BEFORE Trigger Raising SIGNAL

Create a BEFORE INSERT trigger rejecting total_amount <= 0. Test an invalid INSERT and confirm no row exists. Read SQLSTATE and message on the client.

### Exercise 4: AFTER Trigger Raising an Error

In an AFTER INSERT trigger, write an audit and then raise SIGNAL when status = 'REJECTED'. Test INSERT and verify neither base row nor audit row exists under InnoDB.

### Exercise 5: Statement Rollback vs. Transaction Rollback

Open a transaction and UPDATE one table first. Then run an INSERT firing a failing trigger. Verify the earlier UPDATE remains inside the transaction; finally ROLLBACK and confirm the UPDATE also disappears.

### Exercise 6: Multi-Row INSERT

Send a multi-row INSERT in which one row makes the trigger raise an error. Confirm the entire statement rolls back under InnoDB. Repeat with separate INSERTs to compare atomicity scope.

### Exercise 7: Handlers and RESIGNAL

Add an EXIT handler in a trigger to RESIGNAL errors. Verify the caller still receives the error. Try a deliberate CONTINUE handler for an optional condition and evaluate whether ignoring breaks consistency.

### Exercise 8: InnoDB and MyISAM

Have a trigger write audits into MyISAM and then raise an error. Observe the discrepancy between the InnoDB base table change and the MyISAM audit. Switch the audit table to InnoDB and rerun.

### Exercise 9: Mutating Table

Create a trigger attempting to UPDATE the table that fired it. Observe error 1442. Rewrite it by assigning NEW in a BEFORE trigger.

### Exercise 10: Foreign Key Cascades and TRUNCATE

Create a parent-child relationship with ON DELETE CASCADE and a DELETE trigger on the child table. Delete a parent row and check whether the child trigger runs. Try TRUNCATE and compare with DELETE.

### Exercise 11: Deadlocks via Triggers

Use two sessions updating the base table and audit table in opposite orders. Observe the deadlock, identify the victim transaction, and design a consistent access order.

### Exercise 12: Outbox

Create a trigger writing event_outbox when a new order is inserted. Roll back the transaction and confirm the outbox row is gone. Commit the transaction and use a simulated worker to read and mark the event published.

### Exercise 13: Replication

In a lab environment, inspect binlog_format. Compare trigger behavior under statement-based and row-based replication. Confirm audits are not duplicated on the replica.

## 21. Pre-Deployment Checklist

- [ ] Identified BEFORE/AFTER and INSERT/UPDATE/DELETE for triggers.
- [ ] Understood triggers are FOR EACH ROW, not statement-level.
- [ ] Confirmed triggers join the calling statement's transaction.
- [ ] No START TRANSACTION, COMMIT, or ROLLBACK inside triggers.
- [ ] Distinguished AFTER from COMMIT.
- [ ] Tested error paths in both BEFORE and AFTER.
- [ ] Verified statement rollback on InnoDB.
- [ ] Distinguished statement rollback from transaction rollback.
- [ ] Clarified whether caller or procedure owns the transaction.
- [ ] Tested multi-row statements and single-row errors.
- [ ] Ensured tables needing atomicity use InnoDB.
- [ ] Not writing mandatory audits to nontransactional engines.
- [ ] Handlers do not swallow mandatory errors.
- [ ] SIGNAL uses intentional SQLSTATE and messages.
- [ ] RESIGNAL is used when callers must receive errors.
- [ ] Not modifying a table already used by the firing statement.
- [ ] Verified FK cascades and TRUNCATE do not fire triggers like regular DELETE.
- [ ] Added indexes for lookups inside triggers.
- [ ] Assessed deadlock and lock wait risks.
- [ ] No external side effects executed directly inside triggers.
- [ ] Considered a transactional outbox.
- [ ] Verified binlog format and replication.
- [ ] Verified DEFINER and least privilege.
- [ ] CREATE/DROP TRIGGER deployed via separate migrations.
- [ ] Tested caller/JDBC rollback and connection pool cleanup.

## 22. Conclusion

A trigger runs as part of the INSERT, UPDATE, or DELETE statement that fired it. Triggers do not have independent transactions and cannot COMMIT or ROLLBACK on their own. With InnoDB, if a trigger raises an unhandled error, the entire statement fails and transactional changes performed by both the statement and triggers are undone. If the statement runs inside a larger transaction, earlier successful statements remain until the caller decides to COMMIT or ROLLBACK the whole business workflow.

Safe trigger design requires a uniform transactional storage engine, limited side effects, SIGNAL to reject bad data, and intentional handlers. Never swallow mandatory errors, never write transactional audits to MyISAM, never send emails/API requests from triggers, and never update back into a table already used by the statement. For side effects that must happen after commit, write an outbox row in the same transaction and process it in a worker. Deploy CREATE/DROP TRIGGER as separate migrations because DDL triggers an implicit commit.

## Official References

- [MySQL 8.4 Reference Manual – Trigger Syntax and Examples](https://dev.mysql.com/doc/refman/8.4/en/trigger-syntax.html)
- [MySQL 8.4 Reference Manual – Trigger Restrictions](https://dev.mysql.com/doc/refman/8.4/en/trigger-syntax.html#trigger-restrictions)
- [MySQL 8.4 Reference Manual – CREATE TRIGGER Statement](https://dev.mysql.com/doc/refman/8.4/en/create-trigger.html)
- [MySQL 8.4 Reference Manual – SIGNAL Statement](https://dev.mysql.com/doc/refman/8.4/en/signal.html)
- [MySQL 8.4 Reference Manual – Condition Handling](https://dev.mysql.com/doc/refman/8.4/en/condition-handling.html)
- [MySQL 8.4 Reference Manual – GET DIAGNOSTICS](https://dev.mysql.com/doc/refman/8.4/en/get-diagnostics.html)
- [MySQL 8.4 Reference Manual – RESIGNAL Statement](https://dev.mysql.com/doc/refman/8.4/en/resignal.html)
- [MySQL 8.4 Reference Manual – InnoDB Error Handling](https://dev.mysql.com/doc/refman/8.4/en/innodb-error-handling.html)
- [MySQL 8.4 Reference Manual – InnoDB Deadlocks](https://dev.mysql.com/doc/refman/8.4/en/innodb-deadlocks.html)
- [MySQL 8.4 Reference Manual – Statements That Cause an Implicit Commit](https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html)
- [MySQL 8.4 Reference Manual – Replication Formats](https://dev.mysql.com/doc/refman/8.4/en/replication-formats.html)
- [MySQL 8.4 Reference Manual – Stored Object Access Control](https://dev.mysql.com/doc/refman/8.4/en/stored-objects-security.html)
