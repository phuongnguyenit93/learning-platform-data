# Transactions Involving Non-Transactional Tables and External Operations

This lesson belongs to the **Transactions** chapter of the **DATABASE_MYSQL** module. The module aims to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query optimization, privilege management, backups, and handling relational database operational issues. A transaction can only guarantee rollback for changes belonging to resources that genuinely participate in the transaction mechanism. When a statement touches a non-transactional table or calls an external system, the atomic boundary extends beyond the capability of regular COMMIT and ROLLBACK.

After this lesson, you will be able to identify transactional and non-transactional tables, predict outcomes when mixing InnoDB with MyISAM, handle incomplete rollback warnings, detect statements causing implicit commits, and design workflows coordinating the database with email, message brokers, payment APIs, files, or other services using Transactional Outbox, Idempotency, Saga, or XA where appropriate.

## 1. Boundaries of a MySQL Transaction

A local MySQL transaction coordinates changes across tables using a storage engine that supports transactions. With InnoDB, uncommitted changes can be undone with ROLLBACK.

Example:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

If all involved tables are managed by InnoDB, both updates belong to the same transaction. If the second statement fails and the application decides to ROLLBACK, the changes of the first statement are also undone.

However, a MySQL transaction does not automatically include:

- Tables using a storage engine that does not support transactions.
- Another database connection unless coordinated via a distributed transaction mechanism.
- An HTTP request to an external service.
- Sending an email or SMS.
- Sending a message to a broker.
- Writing files, uploading objects, or filesystem operations.
- A call to a payment gateway or partner system.

ROLLBACK only instructs MySQL to undo changes that the transactional engine can undo. It cannot recall an already sent email or reverse a payment already confirmed by another system.

## 2. Transactional and Non-Transactional Storage Engines

The storage engine determines how MySQL stores and manages a table's data.

| Engine | Supports Transactions | Can Roll Back DML? | Notes |
|---|---|---|---|
| InnoDB | Yes | Yes | Common default engine, supports ACID and foreign keys |
| MyISAM | No | No | Changes are written immediately; does not participate in transaction rollback |
| MEMORY | No | No | Data resides in memory; no transactions |
| NDB | Yes | Yes | Transactional engine for MySQL NDB Cluster with specific operational characteristics |

Do not infer transaction capability from SQL syntax. Two tables with identical structure but different ENGINEs can exhibit completely different COMMIT/ROLLBACK behavior.

### Checking a Table's Engine

Use SHOW CREATE TABLE:

~~~sql
SHOW CREATE TABLE orders;
~~~

In the output, look for the ENGINE=InnoDB or ENGINE=MyISAM part.

You can check quickly with:

~~~sql
SHOW TABLE STATUS LIKE 'orders';
~~~

The Engine column indicates the table's storage engine.

Check multiple tables in the current database:

~~~sql
SELECT
    TABLE_NAME,
    ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN (
      'orders',
      'order_items',
      'legacy_audit'
  );
~~~

Check engines supported by the server:

~~~sql
SHOW ENGINES;
~~~

Verify the engine after table creation or after import/migration. If the desired engine is unsupported or disabled on the server, configuration and SQL mode may cause the table to be created with a fallback engine. Never assume that specifying ENGINE=InnoDB in a script guarantees the actual table is InnoDB.

## 3. What Happens When Mixing InnoDB and MyISAM in the Same Transaction?

Suppose a business operation writes to two places:

- The orders table uses InnoDB to store orders.
- The legacy_audit table uses MyISAM to record audit trails.

A transaction executes:

~~~sql
START TRANSACTION;

INSERT INTO orders (order_id, customer_id, total_amount)
VALUES (1001, 42, 500.00);

INSERT INTO legacy_audit (event_name, reference_id)
VALUES ('ORDER_CREATED', 1001);

ROLLBACK;
~~~

Outcome:

- The row in orders is rolled back because InnoDB supports transactions.
- The row in legacy_audit still exists because MyISAM does not support rollback.
- MySQL may emit the warning ER_WARNING_NOT_COMPLETE_ROLLBACK.

Changes on a non-transactional table are saved as soon as the statement executes, regardless of whether autocommit is on or off. Therefore, placing a MyISAM INSERT inside START TRANSACTION does not turn MyISAM into a transactional table.

### Table Illustration

| Point in Time | InnoDB: orders | MyISAM: legacy_audit |
|---|---|---|
| Before transaction | No order 1001 | No event |
| After first INSERT | Has uncommitted change | No change yet |
| After second INSERT | Still uncommitted | Event already written immediately |
| After ROLLBACK | Order 1001 disappears | Event still exists |

This is a business-inconsistent state: the audit log says the order was created, yet the orders table has no such order.

### ROLLBACK Does Not Mean Everything Was Undone

Typical warning message:

~~~text
Warning: Some non-transactional changed tables couldn't be rolled back
~~~

This warning has practical significance: one or more tables in the transaction do not support transactions, so MySQL could not undo changes made there.

If an application only checks that the ROLLBACK command was sent and ignores the Warning, it may report the entire business operation failed while secondary data was still written.

After ROLLBACK, check Warnings before running another regular SQL statement:

~~~sql
ROLLBACK;
SHOW WARNINGS;
~~~

Only afterward inspect the data:

~~~sql
SELECT * FROM orders WHERE order_id = 1001;
SELECT * FROM legacy_audit WHERE reference_id = 1001;
~~~

Expected result: the orders query returns no rows, while legacy_audit contains the event.

## 4. Practice Lab: Observing Incomplete Rollback

Create a lab database and two tables with different engines:

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_mixed_transaction_lab;
USE mysql_mixed_transaction_lab;

CREATE TABLE orders_innodb (
    order_id INT NOT NULL PRIMARY KEY,
    customer_id INT NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE audit_myisam (
    audit_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    event_name VARCHAR(50) NOT NULL,
    reference_id INT NOT NULL
) ENGINE=MyISAM;
~~~

Confirm the engines:

~~~sql
SHOW TABLE STATUS LIKE 'orders_innodb';
SHOW TABLE STATUS LIKE 'audit_myisam';
~~~

Execute the transaction:

~~~sql
START TRANSACTION;

INSERT INTO orders_innodb
    (order_id, customer_id, total_amount)
VALUES
    (1001, 42, 500.00);

INSERT INTO audit_myisam
    (event_name, reference_id)
VALUES
    ('ORDER_CREATED', 1001);

ROLLBACK;
SHOW WARNINGS;
~~~

Verify the data:

~~~sql
SELECT * FROM orders_innodb;
SELECT * FROM audit_myisam;
~~~

Expected results:

- orders_innodb no longer has row 1001.
- audit_myisam still retains the ORDER_CREATED event.
- ROLLBACK may return a Warning about non-transactional changes that could not be rolled back.

### Comparison with an InnoDB-Only Transaction

~~~sql
CREATE TABLE audit_innodb (
    audit_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    event_name VARCHAR(50) NOT NULL,
    reference_id INT NOT NULL
) ENGINE=InnoDB;

START TRANSACTION;

INSERT INTO orders_innodb
    (order_id, customer_id, total_amount)
VALUES
    (1002, 42, 300.00);

INSERT INTO audit_innodb
    (event_name, reference_id)
VALUES
    ('ORDER_CREATED', 1002);

ROLLBACK;

SELECT * FROM orders_innodb WHERE order_id = 1002;
SELECT * FROM audit_innodb WHERE reference_id = 1002;
~~~

Both queries return no rows. Because both tables use InnoDB, the transaction can undo both business and audit changes.

### Cleanup

~~~sql
DROP DATABASE mysql_mixed_transaction_lab;
~~~

Run this only on the newly created lab database. This command drops the practice tables and data.

## 5. autocommit Does Not Make Non-Transactional Tables Transactional

MySQL usually runs with:

~~~sql
SELECT @@SESSION.autocommit;
~~~

When autocommit = 1, each standalone statement is automatically committed if it succeeds.

You can disable autocommit in the session:

~~~sql
SET autocommit = 0;
~~~

With transactional tables like InnoDB, uncommitted changes can be rolled back.

However, with non-transactional tables like MyISAM, changes are still written immediately. Example:

~~~sql
SET autocommit = 0;

INSERT INTO audit_myisam (event_name, reference_id)
VALUES ('IMPORT_STARTED', 500);

ROLLBACK;

SELECT *
FROM audit_myisam
WHERE reference_id = 500;

SET autocommit = 1;
~~~

The MyISAM row still exists. autocommit = 0 only affects transaction management for engines that support transactions; it does not add rollback capability to other engines.

### Session Scope

autocommit is a session-scoped variable. One connection in a connection pool can hold a different state from another connection. The application must manage transactions and session state on the exact right connection.

The START TRANSACTION, DML, and COMMIT/ROLLBACK steps must execute on the same connection. If an application opens a second connection to run a statement, changes on that connection do not automatically join the first connection's transaction.

## 6. Do Not Mix Multiple Storage Engines in an Operation Requiring Atomicity

The safest approach for a business transaction is using tables belonging to a single transaction-safe storage engine, typically InnoDB.

Example:

~~~sql
START TRANSACTION;

INSERT INTO orders_innodb
    (order_id, customer_id, total_amount)
VALUES
    (1003, 42, 800.00);

INSERT INTO audit_innodb
    (event_name, reference_id)
VALUES
    ('ORDER_CREATED', 1003);

COMMIT;
~~~

If one statement fails and the application rolls back, both changes can be undone.

MySQL also recommends that transactions operate on tables managed by a single transaction-safe storage engine. Even when using multiple engines that all support transactions, mixing engines can introduce limitations on atomicity and change visibility depending on the isolation level. Do not assume that multiple transactional engines always behave identically to a simple transaction on a single engine.

MySQL further notes: when a transaction uses multiple transaction-safe engines and the isolation level is not SERIALIZABLE, another transaction may observe a partial set of committed changes from the first transaction. If you must use multiple transactional engines, evaluate isolation levels and concurrency access patterns per MySQL documentation; the simpler choice remains keeping business tables in the same engine.

### What If You Must Keep a Legacy MyISAM Table?

There are three common approaches:

1. **Convert the table to InnoDB:** the best option if the table holds business data needing rollback, foreign keys, or consistency.
2. **Decouple secondary data from the main transaction:** record processing intent in an InnoDB outbox table and let a worker update the legacy system after commit.
3. **Accept eventual consistency:** if the secondary table is only statistics/cache, design synchronization jobs and discrepancy-repair procedures.

Do not use MyISAM to store business audit records that must remain atomically synchronized with primary data.

## 7. DDL Can Implicitly COMMIT a Transaction

Another mistake is thinking every SQL statement between START TRANSACTION and ROLLBACK can be undone.

Many DDL statements cause an implicit commit. This means MySQL ends the current transaction as if COMMIT were executed before running the DDL statement. Most of these statements also commit upon completion.

Statements to watch out for include:

- CREATE TABLE
- ALTER TABLE
- DROP TABLE
- TRUNCATE TABLE
- CREATE INDEX
- DROP INDEX
- CREATE DATABASE
- DROP DATABASE
- CREATE VIEW, DROP VIEW

Example:

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

ALTER TABLE accounts
ADD COLUMN note VARCHAR(100) NULL;

ROLLBACK;
~~~

Do not assume the UPDATE will be rolled back. ALTER TABLE triggers an implicit commit before running, so the account change may have already been committed before the ALTER executed.

### CREATE TEMPORARY TABLE Is a Limited Exception

CREATE TEMPORARY TABLE and DROP TEMPORARY TABLE do not trigger an implicit commit under standard rules. However, creating or dropping a temporary table still cannot be rolled back. If you create a temporary table inside a transaction and then ROLLBACK, the temporary table still exists in the session.

Thus, this exception does not mean DDL becomes transactional.

### Practical Rules

- Do not run DDL between DML steps that must roll back together.
- Separate migrations/schema changes from business transactions.
- Check the list of statements with implicit commit before writing administrative scripts.
- Never use ROLLBACK to try to undo CREATE/ALTER/DROP in a real environment.

## 8. External Operations Outside the Database: Why ROLLBACK Is Not Enough

An application often coordinates MySQL with many other systems:

- Sending order confirmation emails.
- Sending SMS or push notifications.
- Calling a payment gateway.
- Publishing messages to Kafka, RabbitMQ, or another message broker.
- Uploading images or documents to object storage.
- Writing files on a server.
- Calling an inventory or shipping service.

These systems do not automatically participate in MySQL's local transaction. A ROLLBACK command cannot ask them to erase effects already performed.

### Calling an External Service Before COMMIT

Example:

~~~text
BEGIN TRANSACTION
  update inventory
  call payment API successfully
  INSERT order fails
ROLLBACK
~~~

Outcome:

- Inventory is rolled back.
- Order is not created.
- The payment may still have been charged.

This is a dangerous situation: the system charged money, yet the database has no corresponding order.

### Calling an External Service After COMMIT

Example:

~~~text
BEGIN TRANSACTION
  create order
  deduct inventory
COMMIT

send confirmation email
~~~

If the process stops right after COMMIT but before sending the email, the database has the order yet the customer never receives the email.

If sending the email succeeds yet the application loses connection before recording the send status, a retry may send the email a second time.

### Two Failure Gaps

| Ordering | Possible Failure | Result |
|---|---|---|
| External call before COMMIT | External service succeeds, COMMIT fails | External effect exists while database rolls back |
| COMMIT first, external call after | Database succeeds, external service fails | Data is committed while external effect never happened |
| External service succeeds, app crashes before recording | Worker or app retries | May send/charge/process twice |

This is a multi-resource coordination problem that cannot be solved merely by putting ROLLBACK inside a catch block.

## 9. Error-Prone Pattern in Applications

Pseudocode example:

~~~java
connection.setAutoCommit(false);

try {
    insertOrder(connection, order);

    // HTTP call inside MySQL transaction
    paymentGateway.charge(order.payment());

    connection.commit();
} catch (Exception ex) {
    connection.rollback();
    throw ex;
}
~~~

There are two problems:

1. If the payment gateway already charged and COMMIT fails, ROLLBACK does not refund the money.
2. Database connections and locks may be held throughout the HTTP wait, increasing latency and contention.

Do not keep a MySQL transaction open while waiting on a slow network service without a very clear reason. Wait times can drag on, time out, or become indeterminate.

A variant that makes the HTTP call after COMMIT avoids holding the transaction during network waits, yet still leaves a crash gap between COMMIT and HTTP. You need a mechanism to persist sending intent and retry.

## 10. Transactional Outbox: Recording Sending Intent in the Same Transaction

Transactional Outbox bridges the gap between committing business data and requesting an external system to process an event.

Concept:

1. Write business data to an InnoDB table.
2. Write an event to be published to an InnoDB outbox table in the same transaction.
3. COMMIT once for both.
4. A worker reads the outbox after commit.
5. The worker sends the event to the external system.
6. The worker records delivery status and retries when needed.

If the transaction rolls back, both business data and the outbox event disappear. If the transaction commits, both exist together so the worker can process the event.

### Flow Diagram

~~~mermaid
flowchart TD
    A[Application receives request] --> B[START TRANSACTION]
    B --> C[Modify InnoDB business data]
    C --> D[INSERT event into InnoDB outbox]
    D --> E{COMMIT succeeded?}
    E -->|No| F[ROLLBACK: both changes disappear]
    E -->|Yes| G[Worker reads outbox]
    G --> H[Send message/call external API]
    H --> I{Received successfully?}
    I -->|Yes| J[Mark SENT]
    I -->|No| K[Schedule retry or FAILED]
    K --> G
~~~

Outbox does not make the message broker or API part of the MySQL transaction. It ensures the intent to publish an event is durably saved alongside business data, after which the worker is responsible for delivering the event.

### Creating Business and Outbox Tables

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE outbox_events (
    event_id CHAR(36) NOT NULL PRIMARY KEY,
    aggregate_type VARCHAR(50) NOT NULL,
    aggregate_id BIGINT UNSIGNED NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSON NOT NULL,
    status ENUM('PENDING', 'PROCESSING', 'SENT', 'FAILED')
        NOT NULL DEFAULT 'PENDING',
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    available_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    lease_until DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    sent_at DATETIME(6) NULL,
    KEY idx_outbox_dispatch (status, available_at, created_at)
) ENGINE=InnoDB;
~~~

Mandatory requirement: the business table and outbox table must reside within the same commit/rollback transaction scope. If the outbox uses MyISAM, rollback failures reappear.

### Writing Data and Event in the Same Transaction

~~~sql
START TRANSACTION;

INSERT INTO orders
    (customer_id, total_amount, status)
VALUES
    (42, 500.00, 'PENDING');

SET @new_order_id = LAST_INSERT_ID();

INSERT INTO outbox_events
    (
        event_id,
        aggregate_type,
        aggregate_id,
        event_type,
        payload
    )
VALUES
    (
        UUID(),
        'ORDER',
        @new_order_id,
        'OrderCreated',
        JSON_OBJECT(
            'orderId', @new_order_id,
            'customerId', 42,
            'totalAmount', 500.00
        )
    );

COMMIT;
~~~

If the outbox INSERT fails, the application rolls back and the order is not created either. If COMMIT succeeds, the worker can find the OrderCreated event.

### Worker Fetching Events to Send

The worker should fetch an event, mark it as processing in a short transaction, and commit before making network calls.

Example under a one-worker-one-event model:

~~~sql
START TRANSACTION;

SELECT
    event_id,
    event_type,
    payload
FROM outbox_events
WHERE status = 'PENDING'
  AND available_at <= CURRENT_TIMESTAMP(6)
ORDER BY created_at, event_id
LIMIT 1
FOR UPDATE SKIP LOCKED;
~~~

The application reads the event_id of the selected row. If a row is found, update its status in the same transaction:

~~~sql
UPDATE outbox_events
SET
    status = 'PROCESSING',
    attempts = attempts + 1,
    lease_until = CURRENT_TIMESTAMP(6) + INTERVAL 1 MINUTE
WHERE event_id = ?;

COMMIT;
~~~

If SELECT returns no rows, the worker ends the short transaction and waits for the next polling cycle.

FOR UPDATE SKIP LOCKED allows multiple workers to pick different rows without waiting on rows locked by another worker. This feature suits queue models; do not use SKIP LOCKED as a general-purpose consistent read. This syntax requires a MySQL version supporting locking reads with SKIP LOCKED.

After COMMIT, the worker calls the message broker or API using the read payload. Do not hold transactions or row locks during network waits.

### Recording Delivery Results

If sending succeeds:

~~~sql
UPDATE outbox_events
SET
    status = 'SENT',
    sent_at = CURRENT_TIMESTAMP(6),
    lease_until = NULL
WHERE event_id = ?
  AND status = 'PROCESSING';
~~~

If sending fails transiently, reset to PENDING with a next retry timestamp:

~~~sql
UPDATE outbox_events
SET
    status = 'PENDING',
    available_at = CURRENT_TIMESTAMP(6) + INTERVAL 30 SECOND,
    lease_until = NULL
WHERE event_id = ?
  AND status = 'PROCESSING';
~~~

After a set number of attempts, transition to FAILED and raise an alert for operators to investigate. Never retry infinitely without limits, backoff, or monitoring.

If a worker dies while in PROCESSING status, another worker can reclaim the row once lease_until expires. The lease mechanism must be designed carefully so two workers do not process the same event under normal conditions.

In this design, a worker or a recovery process must return expired leases back to the queue before queries pick only PENDING rows:

~~~sql
UPDATE outbox_events
SET
    status = 'PENDING',
    available_at = CURRENT_TIMESTAMP(6),
    lease_until = NULL
WHERE status = 'PROCESSING'
  AND lease_until < CURRENT_TIMESTAMP(6);
~~~

Only perform recovery after the lease expires. If the old worker is still sending slowly, a new worker might resend the same event; therefore, keep leases sufficiently long, extend leases for long processing, and always enforce idempotency on the receiving side.

### Why Can Outbox Still Send Duplicates?

Suppose:

1. The worker sends the message successfully.
2. The broker receives the message.
3. The worker crashes before updating status to SENT.
4. The lease expires and another worker resends the same event.

The message may be delivered twice. Therefore, Outbox usually provides at-least-once delivery, not automatic exactly-once guarantees for external effects.

Use event_id as an idempotency key. The receiving service must be able to detect and ignore already-processed requests.

## 11. Idempotency: Retrying Without Repeating Business Effects

An idempotent operation can be executed multiple times with a business outcome equivalent to executing it once.

Examples:

- Creating an order with a unique request_id.
- Sending an event with a unique event_id.
- Requesting a payment with an idempotency key supported by the payment gateway.
- A consumer saving the processed event_id in the same transaction as its business changes.

### Deduplication Table on the Consumer

~~~sql
CREATE TABLE processed_messages (
    event_id CHAR(36) NOT NULL PRIMARY KEY,
    processed_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB;
~~~

The consumer can process messages transactionally:

~~~sql
START TRANSACTION;

INSERT INTO processed_messages (event_id)
VALUES ('f8a8a2d0-7f00-4c12-9f51-6eecf16d12a1');

-- Only if INSERT succeeds, proceed to update business data.
UPDATE shipment_requests
SET status = 'READY'
WHERE order_id = 1001;

COMMIT;
~~~

If the same event is redelivered, INSERT hits a duplicate primary key. The consumer catches the duplicate error and skips the already-processed event per application rules.

When INSERT reports a duplicate, the consumer does not run the subsequent business UPDATE in that branch. It ends the current transaction and acknowledges the message as previously processed. Errors other than duplicate key must be handled as real errors and never treated as a completed message.

Ensure writing to processed_messages and updating business data are in the same InnoDB transaction. If you record the processed marker first and the business update fails without sharing the same transaction, a retry might skip the message even though business logic never finished.

For payment APIs or external services, a deduplication table in your application's database cannot prevent the external service from charging twice. You must pass an idempotency key that the external service understands and supports.

## 12. Saga: Coordinating Multi-Step Workflows with Compensating Actions

Not every service supports XA or full idempotency. For long workflows spanning multiple services, Saga can be used.

Saga splits a business workflow into local transactions. If a later step fails, the system executes compensating actions for already completed steps.

Order placement example:

| Step | Action | Compensating Action |
|---|---|---|
| 1 | Create order in PENDING status | Cancel order |
| 2 | Reserve stock in inventory | Release reserved stock |
| 3 | Charge payment | Refund payment |
| 4 | Create shipping request | Cancel shipping request |

Saga is not an atomic rollback. A compensating action is a new business operation that can itself fail and also needs retries, idempotency, and auditing.

For example, refunding does not delete the history of the collected payment. It creates a separate refund transaction. Therefore, workflow state must clearly represent pending, completed, compensating, or requiring manual intervention.

Saga is suitable when:

- The workflow spans multiple services over time.
- A distributed transaction cannot be held open for a long period.
- Participating systems provide business APIs to compensate.
- Intermediate states and eventual consistency are acceptable.

## 13. XA and Distributed Transactions

XA is a distributed transaction protocol allowing multiple transactional resources to participate in a single global transaction coordinated by a Transaction Manager.

In this model:

- **Resource Manager (RM):** a transaction-capable resource, such as a database.
- **Transaction Manager (TM):** coordinates commit or rollback across resource managers.
- **Global transaction:** a business operation comprising multiple local transaction branches.

MySQL supports XA via the two-phase commit protocol:

1. **Prepare:** resource managers prepare and confirm they can commit.
2. **Commit or Rollback:** the transaction manager decides to complete or abort the branches.

With MySQL, XA support is limited to InnoDB. MyISAM tables cannot participate in XA as a transactional resource.

Conceptual XA commands:

~~~sql
XA START 'xid-1001';

-- DML on InnoDB tables

XA END 'xid-1001';
XA PREPARE 'xid-1001';

-- Transaction Manager decides:
XA COMMIT 'xid-1001';
-- or:
-- XA ROLLBACK 'xid-1001';
~~~

Do not run these commands manually like a regular transaction without a Transaction Manager managing XIDs, PREPARED states, timeouts, and recovery.

### When Is XA Appropriate?

XA can be appropriate when:

- All participating resources support XA.
- A reliable Transaction Manager is in place.
- The business operation genuinely requires atomic commit across multiple transactional resources.
- Operations teams have procedures to handle transactions stuck in the PREPARED state.

### When Should XA Not Be Used?

- Regular HTTP APIs do not provide an XA resource manager.
- Email or SMS cannot participate in XA by default.
- Filesystems or object storage are typically not XA resources.
- MyISAM tables do not support transactions.
- Long workflows with many business steps usually fit Saga/Outbox better.

XA incurs coordination and operational overhead. PREPARED transactions can hold resources until committed/rolled back. Monitoring and recovery are required; do not treat XA as simply adding COMMIT at the end of a code block.

## 14. Distinguishing Coordination Strategies

| Scenario | Suitable Approach |
|---|---|
| Multiple InnoDB tables in one database | Local transaction |
| InnoDB business table and MyISAM auxiliary table | Convert to InnoDB or separate auxiliary writes via outbox |
| Database and email/message broker | Transactional Outbox + retry + idempotency |
| Two XA-capable databases requiring atomic commit | XA with a Transaction Manager |
| Long workflow across services with compensating steps | Saga |
| External API without idempotency | Design reconciliation and verification mechanisms; do not assume retries are safe |
| Writing files or object storage | Store metadata/intent in DB, handle upload separately, retry and clean up orphans |

There is no single pattern for every system. Choose based on each resource's transactional capabilities, consistency requirements, workflow duration, and compensation capability.

## 15. Inspecting and Handling Incomplete ROLLBACK

When the application reports a transaction rolled back yet data still appears, proceed in order:

### Step 1: Verify the Engine of All Tables

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN (
      'orders',
      'order_items',
      'audit_log'
  );
~~~

Do not check only the main table. An audit, staging, or history table may be using a different engine.

### Step 2: Read Actual Table Definitions

~~~sql
SHOW CREATE TABLE orders;
SHOW CREATE TABLE audit_log;
~~~

Verify the ENGINE and constraints.

### Step 3: Check Which Engines the Server Supports

~~~sql
SHOW ENGINES;
~~~

If a table was expected to use InnoDB but actually uses MyISAM, check server configuration, disabled engines, and warnings during table creation.

### Step 4: Read Warnings Immediately After ROLLBACK

~~~sql
ROLLBACK;
SHOW WARNINGS;
~~~

Look for messages about nontransactional changes that couldn't be rolled back. Do not run SELECT or regular SQL statements before reading diagnostics if you need to preserve ROLLBACK's warnings.

### Step 5: Inspect Leftover Data

~~~sql
SELECT * FROM orders WHERE order_id = 1001;
SELECT * FROM audit_log WHERE reference_id = 1001;
~~~

Identify which rows were rolled back and which rows still exist.

### Step 6: Reconcile by Business Key

Do not automatically delete leftover rows without determining business state. The non-transactional row might record a valid event, or an external action might already have occurred.

Generate a reconciliation report by request ID, order ID, or idempotency key to determine:

- Whether primary data committed or not.
- Whether secondary data was written or not.
- Whether the external API received the request or not.
- Whether the broker received the message or not.
- Whether to retry or perform a compensating action.

## 16. Practice Lab: Simulating Transactions and Outbox

This lab helps distinguish non-rollbackable changes from recording event-dispatch intent.

### Part A: MyISAM Table Rollback

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_external_workflow_lab;
USE mysql_external_workflow_lab;

CREATE TABLE business_records (
    record_id INT NOT NULL PRIMARY KEY,
    description VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE legacy_events (
    event_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    record_id INT NOT NULL,
    event_name VARCHAR(50) NOT NULL
) ENGINE=MyISAM;

START TRANSACTION;

INSERT INTO business_records (record_id, description)
VALUES (1, 'Record one');

INSERT INTO legacy_events (record_id, event_name)
VALUES (1, 'RECORD_CREATED');

ROLLBACK;
SHOW WARNINGS;

SELECT * FROM business_records;
SELECT * FROM legacy_events;
~~~

Note the difference between the two results and explain why autocommit does not determine MyISAM's rollback capability.

### Part B: Saving Events in an InnoDB Outbox

~~~sql
CREATE TABLE outbox_events (
    event_id CHAR(36) NOT NULL PRIMARY KEY,
    aggregate_id INT NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    payload JSON NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB;

START TRANSACTION;

INSERT INTO business_records (record_id, description)
VALUES (2, 'Record two');

INSERT INTO outbox_events
    (event_id, aggregate_id, event_type, payload)
VALUES
    (
        UUID(),
        2,
        'RecordCreated',
        JSON_OBJECT('recordId', 2, 'description', 'Record two')
    );

COMMIT;

SELECT * FROM business_records WHERE record_id = 2;
SELECT * FROM outbox_events WHERE aggregate_id = 2;
~~~

Both the business record and the event-publishing intent exist together after COMMIT.

### Part C: Demonstrating Both Roll Back Together

~~~sql
START TRANSACTION;

INSERT INTO business_records (record_id, description)
VALUES (3, 'Record three');

INSERT INTO outbox_events
    (event_id, aggregate_id, event_type, payload)
VALUES
    (
        UUID(),
        3,
        'RecordCreated',
        JSON_OBJECT('recordId', 3, 'description', 'Record three')
    );

ROLLBACK;

SELECT * FROM business_records WHERE record_id = 3;
SELECT * FROM outbox_events WHERE aggregate_id = 3;
~~~

Both queries return no rows because both tables use InnoDB.

### Part D: Simulating Worker and Idempotency

Create a table recording processed events:

~~~sql
CREATE TABLE processed_events (
    event_id CHAR(36) NOT NULL PRIMARY KEY,
    processed_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB;
~~~

Select an event from the outbox:

~~~sql
SELECT
    event_id,
    event_type,
    payload
FROM outbox_events
WHERE status = 'PENDING'
ORDER BY created_at
LIMIT 10;
~~~

In the application, for each event:

1. Use event_id as the idempotency key.
2. Call the event-receiving service.
3. If the service confirms success, update status to SENT.
4. On timeout or transient error, schedule a retry.
5. If the same event_id is resent, the receiver must recognize and skip the already-processed effect.

Simulate the consumer saving the processed marker inside a transaction:

~~~sql
START TRANSACTION;

INSERT INTO processed_events (event_id)
VALUES ('f8a8a2d0-7f00-4c12-9f51-6eecf16d12a1');

COMMIT;
~~~

Try INSERTing the same event_id again. The primary key prevents creating a duplicate processed record. In the application, catch the duplicate error by exact error type and treat it as an already-processed event; do not ignore other database errors.

### Cleanup

~~~sql
DROP DATABASE mysql_external_workflow_lab;
~~~

Run this only on the newly created lab database.

## 17. Checklist for Designing Multi-Resource Transactions

- [ ] Verified ENGINE of every table modified by DML in the transaction.
- [ ] Tables needing atomic rollback all use a transactional engine, typically InnoDB.
- [ ] Do not rely on ROLLBACK to undo MyISAM or non-transactional engines.
- [ ] Checked Warnings after rollback when non-transactional tables are involved.
- [ ] Do not let DDL causing implicit commit intrude mid-business-transaction.
- [ ] Transaction operations run on the same database connection.
- [ ] Do not hold transactions open while waiting on HTTP or message brokers unless strictly necessary.
- [ ] Identified failure ordering scenarios between COMMIT and external calls.
- [ ] Implemented an outbox or durable intent-recording mechanism when events must be emitted post-commit.
- [ ] Outbox and business data both use a transaction-safe engine.
- [ ] Workers implement retry, backoff, lease/timeout, and terminal error states.
- [ ] Events carry a stable ID to serve as an idempotency key.
- [ ] Consumers or external APIs have deduplication mechanisms.
- [ ] Reconciliation and handling procedures exist for FAILED events.
- [ ] Use XA only when every resource genuinely supports XA and a Transaction Manager exists.
- [ ] Use Saga when long workflows require compensating actions rather than a prolonged distributed transaction.

## 18. Principles to Remember

1. START TRANSACTION does not make non-transactional tables transactional.
2. Changes on MyISAM are written immediately and cannot be undone by ROLLBACK.
3. When rolling back a transaction mixing InnoDB and MyISAM, InnoDB changes are undone while MyISAM changes persist.
4. The ER_WARNING_NOT_COMPLETE_ROLLBACK warning is a signal to investigate leftover data.
5. Use a single transaction-safe storage engine for tables requiring atomicity.
6. DDL such as CREATE, ALTER, DROP, and TRUNCATE can trigger an implicit commit.
7. ROLLBACK cannot undo emails, HTTP requests, messages, files, or payments already executed in another system.
8. Calling an external service before COMMIT risks creating external effects even if the database rolls back.
9. Calling an external service after COMMIT risks the database committing without the event ever being sent.
10. Transactional Outbox saves business data and event-publishing intent in the same transaction.
11. Outbox typically provides at-least-once delivery; idempotency is required to handle duplicate messages.
12. Saga uses compensating actions for multi-step workflows; it is not an atomic rollback.
13. XA requires XA-capable resource managers and a Transaction Manager; MySQL XA supports only InnoDB.
14. Designing reconciliation and recovery workflows is part of system consistency.

## Official References

Behaviors in this lesson are cross-checked against the **MySQL 9.7 Reference Manual** as of **2026-11-19**:

1. [START TRANSACTION, COMMIT, and ROLLBACK Statements](https://dev.mysql.com/doc/refman/9.7/en/commit.html): local transactions, autocommit, limitations when mixing transactional and non-transactional tables, incomplete rollback warnings, and the binary log.
2. [Rollback Failure for Nontransactional Tables](https://dev.mysql.com/doc/refman/9.7/en/nontransactional-tables.html): incomplete rollback messages and how to inspect storage engines.
3. [Statements That Cause an Implicit Commit](https://dev.mysql.com/doc/refman/9.7/en/implicit-commit.html): DDL, administrative statements, and implicit commit cases.
4. [XA Transactions](https://dev.mysql.com/doc/refman/9.7/en/xa.html): distributed transactions, Resource Manager, and Transaction Manager.
5. [Restrictions on XA Transactions](https://dev.mysql.com/doc/refman/9.7/en/xa-restrictions.html): XA restrictions and InnoDB support.
6. [SHOW ENGINES Statement](https://dev.mysql.com/doc/refman/9.7/en/show-engines.html): checking storage engines supported by the server.
7. [INFORMATION_SCHEMA TABLES](https://dev.mysql.com/doc/refman/9.7/en/information-schema-tables-table.html): checking table engines via metadata.
