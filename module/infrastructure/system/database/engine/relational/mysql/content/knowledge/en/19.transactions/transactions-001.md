# Business Unit of Work and ACID Properties

A transaction is a unit of work consisting of one or more data read/write operations processed as a unified whole. When the transaction succeeds, changes are confirmed with `COMMIT`; when it needs to be aborted before confirmation, `ROLLBACK` can be used. With a transaction-capable storage engine like InnoDB, this mechanism ensures multiple related operations either succeed together or are canceled together, while also controlling the impact between concurrent transactions.

A good transaction typically corresponds to a complete business unit: transferring money between two accounts, creating an order along with its order items and deducting inventory, or recording a payment along with the invoice status. Operations must be in the same transaction if the system must not leave a partial state when one step fails.

ACID represents four foundational properties that describe the desired behavior of a transaction: Atomicity, Consistency, Isolation, and Durability. MySQL InnoDB provides critical mechanisms to implement these properties, but the application must still define proper business boundaries, validate conditions, and handle errors.

## 1. A Transaction Is a Business Unit of Work

Consider transferring 100.00 from account A to account B. From a business perspective, this is a single action, but it requires multiple data operations:

1. Verify that both accounts exist and are eligible to transact.
2. Verify that account A has sufficient balance.
3. Deduct 100.00 from A.
4. Add 100.00 to B.
5. Record the transaction in the history ledger.

If deducting from A succeeds but adding to B fails, the system loses money. If adding to B succeeds but recording the history fails, reconciliation data no longer accurately reflects the transaction. These steps should be executed within a single database transaction so they commit or roll back together.

Conversely, you should not bundle every operation of a long workflow into a single transaction. Sending emails, calling external payment gateways, or waiting for user confirmation can take a long time and cannot be rolled back by MySQL's `ROLLBACK`. Transaction boundaries should enclose the data changes that require atomicity within the same database.

## 2. The Four ACID Properties

ACID describes four characteristics of a reliable transaction:

| Property | Meaning | Question to Answer |
| --- | --- | --- |
| Atomicity | Changes in a transaction are accepted as a unit; an error before commit can cancel transactional changes | If one step fails, is half a transaction left behind? |
| Consistency | A transaction brings data from one valid state to another valid state according to defined rules | After the transaction, do constraints and business invariants still hold? |
| Isolation | Concurrent transactions must not observe intermediate states that violate the chosen isolation level | Can two users operating on the same data produce incorrect results? |
| Durability | Once a commit is confirmed successful, changes are protected against failures within the guarantees of the storage configuration | After a server crash, is committed data still preserved? |

ACID does not mean all application bugs are automatically fixed. The database can guarantee atomic transactions, but the application must still check affected row counts, handle deadlocks, enforce business rules, and avoid sending the same request multiple times without an idempotency mechanism.

## 3. Atomicity: All or Nothing

Atomicity ensures that transactional changes within a transaction are processed as a single unit. If the transaction rolls back, the changes made within the transaction are discarded. If it commits successfully, all changes are confirmed.

For example, creating an order requires writing to the `orders` and `order_items` tables:

```sql
START TRANSACTION;

INSERT INTO orders (id, customer_id, total_amount, status)
VALUES (1001, 42, 250000.00, 'pending');

INSERT INTO order_items (order_id, product_id, quantity, unit_price)
VALUES
    (1001, 10, 2, 75000.00),
    (1001, 11, 1, 100000.00);

COMMIT;
```

If an insert statement fails and the application decides to abort the transaction, it can run:

```sql
ROLLBACK;
```

When the rollback succeeds, the order row and order item rows written in the transaction are all discarded. This is only true when the involved tables use a storage engine that supports transactions, such as InnoDB, and the operations have not yet been committed.

If a table uses a non-transactional engine, writes to that table are not protected by rollback like InnoDB. Therefore, you should check the engine of all tables belonging to the same business unit.

## 4. Consistency: Maintaining Data and Business Rules

Consistency means a transaction must transition the database from a state that satisfies defined rules to another state that also satisfies those rules. Rules can be enforced at multiple layers:

- `PRIMARY KEY` and `UNIQUE` ensure identifiers or values do not duplicate according to index rules.
- `FOREIGN KEY` ensures valid referential relationships.
- `NOT NULL`, `CHECK`, and data types restrict allowed values.
- Application logic checks business invariants that constraints cannot express.
- Transactions group related operations so intermediate states are not exposed.

For example, an account must not have a negative balance. You can declare `CHECK (balance >= 0)` on MySQL 8.0.16 or later, while still needing conditional balance updates and checking statement results. Constraints do not replace full transfer rules such as transfer limits, account status, or user permissions.

A transaction does not automatically know about an undeclared business rule. If the application forgets to check a condition and the schema also lacks a corresponding constraint, MySQL can commit a state that is invalid for the business yet still valid according to the database structure.

## 5. Isolation: Controlling Impact Between Concurrent Transactions

Multiple connections can read and write the same data at the same time. Isolation defines to what extent one transaction is allowed to observe another transaction's data and how competing operations are coordinated.

For example, two staff members simultaneously order the last item in stock. If both read the stock quantity as 1 and both decide to sell it, the system may record two orders when only one item remains. You need transactions, locks, or conditional updates to protect inventory invariants.

InnoDB combines MVCC (multi-version concurrency control), record locks, and range locks to implement isolation levels. A regular read query can read a consistent snapshot without locking rows like a locking read; an update operation or `SELECT ... FOR UPDATE` can acquire locks to coordinate competing transactions.

## 6. Durability: Committed Data Is Protected

Durability ensures that changes from a committed transaction are stored persistently according to the system's configuration and guarantees. InnoDB uses the redo log to recover committed changes after a crash; the log flushing mechanism and synchronization with the OS/hardware affect the actual level of protection.

In a common configuration prioritizing durability, `innodb_flush_log_at_trx_commit = 1` requires InnoDB to flush and sync the redo log to storage at every commit. Setting a different value can improve performance at the cost of a data loss window if the server or operating system crashes. This setting must be decided based on RPO requirements and storage capabilities.

If the binary log is used for replication or point-in-time recovery, `sync_binlog` also affects binary log durability. Syncing the redo log and binary log are two separate aspects; they need to be configured consistently with recovery requirements. A successful commit on the primary also does not automatically mean every asynchronous replica has received and applied the transaction.

Durability does not replace backups, restore testing, replication, or disaster recovery plans. It protects committed transactions via storage mechanisms, not against a user accidentally deleting data in a valid transaction and committing it.

## 7. Prerequisite: Using a Transaction-Capable Storage Engine

In MySQL, transactions are implemented at the storage engine level. InnoDB supports transactions, commit, rollback, savepoints, locking, and crash recovery. Non-transactional engines like MyISAM do not provide the same rollback guarantees for write operations.

Check the engine of tables:

```sql
SHOW TABLE STATUS
WHERE Name IN ('orders', 'order_items');
```

Or:

```sql
SELECT
    TABLE_NAME,
    ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('orders', 'order_items');
```

For business data requiring ACID, you should use InnoDB for all tables participating in the same transaction. Even a single table using a non-transactional engine can break the "all or nothing" expectation of the entire workflow.

## 8. Autocommit and Explicit Transactions

MySQL typically has `autocommit` enabled by default. When `autocommit = 1`, each successful SQL statement executes as its own transaction and commits automatically if no explicit transaction is open.

Check the status:

```sql
SELECT @@SESSION.autocommit;
```

With autocommit enabled, the following two statements are two independent transactions:

```sql
UPDATE accounts SET balance = balance - 100 WHERE account_id = 101;
UPDATE accounts SET balance = balance + 100 WHERE account_id = 202;
```

If the second statement fails, the first statement has already committed and cannot be undone by a subsequent `ROLLBACK` command. This is why an explicit transaction must be started when multiple operations together form a business unit.

You can start a transaction with:

```sql
START TRANSACTION;
-- or
BEGIN;
```

Then end it with `COMMIT` or `ROLLBACK`. While an explicit transaction is open, subsequent statements on the same connection participate in that transaction until the transaction ends.

## 9. Basic Lifecycle: START TRANSACTION, COMMIT, and ROLLBACK

An explicit transaction typically has the structure:

```sql
START TRANSACTION;

-- Read required data
SELECT ...;

-- Write one or more related changes
INSERT ...;
UPDATE ...;
DELETE ...;

-- Only confirm when all business conditions are met
COMMIT;
```

If any step fails to meet conditions and the application decides to abort:

```sql
ROLLBACK;
```

`COMMIT` confirms the transaction's changes. `ROLLBACK` discards uncommitted transactional changes. Once a commit succeeds, you cannot use rollback to undo the finished transaction; to fix it, you need a compensating transaction or a new business operation.

Always handle both SQL errors and application-layer errors. If the application detects an invalid step, it must proactively roll back before returning the connection to the pool.

## 10. Full Example: Transferring Money Between Two Accounts

Create the accounts and transfer ledger tables:

```sql
CREATE TABLE accounts (
    account_id BIGINT UNSIGNED NOT NULL,
    owner_name VARCHAR(120) NOT NULL,
    balance DECIMAL(15, 2) NOT NULL,
    PRIMARY KEY (account_id)
) ENGINE=InnoDB;

CREATE TABLE account_transfers (
    transfer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    from_account_id BIGINT UNSIGNED NOT NULL,
    to_account_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (transfer_id),
    CONSTRAINT fk_transfers_from_account
        FOREIGN KEY (from_account_id) REFERENCES accounts (account_id),
    CONSTRAINT fk_transfers_to_account
        FOREIGN KEY (to_account_id) REFERENCES accounts (account_id)
) ENGINE=InnoDB;
```

Insert sample data:

```sql
INSERT INTO accounts (account_id, owner_name, balance)
VALUES
    (101, 'Lan', 1000.00),
    (202, 'Minh', 500.00);
```

Workflow to transfer 100.00:

```sql
START TRANSACTION;

-- Lock both accounts in account_id order to reduce deadlock risk
SELECT account_id, balance
FROM accounts
WHERE account_id IN (101, 202)
ORDER BY account_id
FOR UPDATE;

-- Application checks: exactly two accounts exist, amount > 0,
-- source account has sufficient balance, and both accounts are allowed to transact.

UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 101
  AND balance >= 100.00;

-- Application must verify affected rows = 1; otherwise ROLLBACK.

UPDATE accounts
SET balance = balance + 100.00
WHERE account_id = 202;

-- Application must verify affected rows = 1; otherwise ROLLBACK.

INSERT INTO account_transfers
    (from_account_id, to_account_id, amount)
VALUES
    (101, 202, 100.00);

COMMIT;
```

The SQL snippet above describes the sequence of operations; the comments stating "Application checks" represent mandatory steps for the program calling the database. If the updated row count is incorrect, an account does not exist, balance is insufficient, or the history insert fails, the application must execute `ROLLBACK` instead of committing.

After committing, verify:

```sql
SELECT account_id, balance
FROM accounts
WHERE account_id IN (101, 202)
ORDER BY account_id;

SELECT *
FROM account_transfers
ORDER BY transfer_id DESC
LIMIT 1;
```

The total balance of the two accounts remains unchanged because the transfer only moves value between the two accounts. The transfer ledger records a corresponding transfer entry.

## 11. Why Lock Rows When Reading Before Updating?

If two transactions read the balance at the same time before updating, both might make decisions based on the same stale value. This is a race condition.

`SELECT ... FOR UPDATE` is a locking read. Inside an InnoDB transaction, it acquires locks on the rows read along the access path and holds them until the transaction commits or rolls back. Other transactions trying to update or acquire conflicting locks on those rows must wait or may encounter a deadlock.

Example:

```sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 101
FOR UPDATE;

-- Application checks the balance and performs the appropriate UPDATE.

COMMIT;
```

The lock must be acquired within the same transaction as the validation and update operations. If you read on one connection, end the transaction, and then update on another connection, the lock no longer protects the subsequent step.

For operations that need to lock multiple rows, try to access rows in a consistent order, such as ascending by primary key. This does not eliminate all deadlocks, but it helps reduce the likelihood of two transactions locking the same set of rows in opposite orders.

## 12. Transaction Isolation Levels in InnoDB

MySQL InnoDB supports four standard isolation levels:

| Isolation level | Key Characteristics | Notes |
| --- | --- | --- |
| `READ UNCOMMITTED` | Can read uncommitted changes from other transactions (dirty read) | Lowest isolation level; rarely suitable for business logic requiring reliable data |
| `READ COMMITTED` | Each regular consistent read takes a fresh snapshot at the start of the statement; does not read uncommitted data | A transaction may see newly committed data in a subsequent SELECT |
| `REPEATABLE READ` | Regular consistent reads in the transaction use the same snapshot created at the first consistent read | Common default in InnoDB; locking reads have different semantics from consistent reads |
| `SERIALIZABLE` | Stricter level that converts regular read operations into appropriate locking behavior while a transaction is open | Can increase lock waits and reduce concurrency |

Check the current isolation level:

```sql
SELECT @@SESSION.transaction_isolation;
```

In MySQL InnoDB, the default is typically `REPEATABLE-READ`, though the configuration can vary by server or session. Always verify instead of assuming.

### 12.1. Dirty Read

A dirty read occurs when a transaction reads a change that has not yet been committed by another transaction. If the writing transaction subsequently rolls back, the reading transaction has observed a value that never became confirmed data.

`READ UNCOMMITTED` can allow dirty reads. InnoDB's `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE` levels do not allow regular consistent reads to see uncommitted changes.

### 12.2. Non-Repeatable Read

A non-repeatable read occurs when the same transaction reads a row again and sees a different value because another transaction committed an update between the two reads.

In `READ COMMITTED`, each consistent read gets a fresh snapshot, so this phenomenon can occur. In `REPEATABLE READ`, regular consistent reads within the same transaction read from the same snapshot, so they do not see changes committed after that snapshot.

### 12.3. Phantom Read

A phantom read occurs when the same range query condition returns a different set of rows because another transaction inserted or deleted matching rows.

InnoDB `REPEATABLE READ` uses snapshots for consistent reads and uses next-key/gap locking in appropriate locking reads to protect ranges. Do not assume every read query locks a range; regular consistent reads and locking reads work via different mechanisms.

## 13. MVCC and Consistent Read

InnoDB uses MVCC to allow multiple transactions to read consistent versions of data without locking every row being read. A regular `SELECT` inside a transaction at an isolation level supporting consistent reads can read from a snapshot instead of waiting for all writing transactions to finish.

Example in `REPEATABLE READ`:

```sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 101;

-- Another connection updates balance and executes COMMIT.

SELECT balance
FROM accounts
WHERE account_id = 101;

COMMIT;
```

Two regular `SELECT` statements in the same transaction can see the same snapshot version, even if another connection committed a new value after the first read. This is a characteristic of consistent reads in `REPEATABLE READ`.

If you need to read the latest committed version and lock the row to prepare for an update, consider a locking read like `SELECT ... FOR UPDATE`. Do not confuse the expectations of a consistent read with a locking read; they serve different purposes.

## 14. SET TRANSACTION: Choosing an Isolation Level

You can set the isolation level for the next transaction:

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

-- Transaction operations

COMMIT;
```

Or set it for the session:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
```

A session change affects subsequent transactions on that connection. Setting it globally affects the default for new connections and requires appropriate administrative privileges. With a connection pool, isolation must be configured per connection or per transaction in a controlled manner.

You should not lower the isolation level merely to reduce lock waits without understanding your business invariants. Sometimes the right solution is adding an index, shortening transactions, using conditional updates, or locking the right rows rather than changing the overall isolation level.

## 15. SAVEPOINT: Partial Transaction Rollback

`SAVEPOINT` creates a marker within a transaction. You can roll back to that marker while keeping changes made before the marker in the transaction:

```sql
START TRANSACTION;

INSERT INTO orders (id, customer_id, total_amount, status)
VALUES (2001, 42, 150000.00, 'pending');

SAVEPOINT after_order;

INSERT INTO order_items (order_id, product_id, quantity, unit_price)
VALUES (2001, 10, 2, 75000.00);

-- If you need to undo operations after the savepoint:
ROLLBACK TO SAVEPOINT after_order;

-- You can continue other operations and then end the transaction.
COMMIT;
```

`ROLLBACK TO SAVEPOINT` does not end the entire transaction. Changes before the savepoint remain and are only confirmed upon commit. You can remove a marker that is no longer needed with `RELEASE SAVEPOINT after_order`.

A savepoint is not a nested transaction. MySQL/InnoDB does not provide independent nested transactions; a transaction has only one final commit/rollback, while savepoints allow partial rollback.

## 16. DDL and Implicit Commit

Not every statement can be rolled back like DML on InnoDB. Many DDL statements and administrative commands cause an implicit commit, meaning they end any open transaction before or after execution according to the rules of that statement.

Common examples include:

- `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`.
- `TRUNCATE TABLE`.
- `RENAME TABLE`.
- Certain user management, privilege, and server configuration statements.

For example, you should not expect the following commands to roll back the DDL as well:

```sql
START TRANSACTION;

INSERT INTO audit_notes (note)
VALUES ('Preparing schema change');

ALTER TABLE orders ADD COLUMN source_code VARCHAR(30) NULL;

ROLLBACK;
```

`ALTER TABLE` can cause an implicit commit; therefore, the subsequent `ROLLBACK` does not necessarily undo the insert before the DDL and does not revert the schema change. Run DDL migrations as a separate deployment step with a schema backup/rollback plan, rather than mixing them into a DML transaction expecting atomicity.

Implicit commit details have exceptions depending on statement type and version. Before placing DDL into a transactional workflow, check the official documentation for your exact MySQL version.

Modern MySQL versions have the concept of atomic DDL: a DDL operation is protected so that if the server crashes during execution, metadata and data dictionary state do not end up in a half-finished state. This does not mean DDL becomes something that can be rolled back together with a user's DML transaction. DDL can still trigger an implicit commit according to its rules.

## 17. Transactions Belong to a Connection

A transaction is managed on a single MySQL connection/session. Statements must execute on the same connection to participate in the same transaction.

A common bug in applications using a connection pool:

1. Connection A runs `START TRANSACTION`.
2. The application sends the next `UPDATE` statement, but the pool provides connection B.
3. The update on B runs in a different transaction or its own autocommit mode.
4. The application calls `COMMIT` on A and assumes both statements were confirmed together.

As a result, the transaction boundary is broken. Borrow a connection from the pool, start the transaction on that connection, execute all operations and commit/roll back on that exact connection, and only then return the connection to the pool.

When a transaction fails, the application must roll back before reusing the connection. Never allow a connection with an open transaction to return to the pool in an unclear state.

## 18. Deadlock, Lock Wait Timeout, and Retry

A deadlock occurs when transactions hold locks that other transactions need, forming a wait cycle. For example:

- Transaction A locks row 1 and waits for row 2.
- Transaction B locks row 2 and waits for row 1.
- Neither transaction can proceed unless one side releases its lock.

InnoDB detects deadlocks and chooses one transaction as a victim to roll back. The application needs to catch deadlock errors and can then retry the **entire transaction** with a retry limit and appropriate backoff. Do not merely re-run the last statement because earlier operations in the transaction have already been rolled back.

A lock wait timeout occurs when a transaction waits for a lock longer than the configured duration. Depending on configuration and error type, the application needs to determine whether the transaction is still active or has been rolled back; the safe approach is usually to explicitly roll back and then retry the entire business unit if possible.

In InnoDB, when a lock wait times out, by default only the waiting statement is rolled back; the transaction may still remain open. If `innodb_rollback_on_timeout` is enabled, the entire transaction is rolled back. Conversely, when InnoDB detects a deadlock, the chosen victim transaction is usually rolled back entirely. Because the behaviors differ, applications should handle errors by error type, explicitly roll back when needed, and never assume every SQL error automatically terminates the transaction.

Another scenario is when the connection drops right while sending `COMMIT`. The application might not know whether the server committed or not because the response was lost in transit. Do not blindly resend a non-idempotent operation. Use a unique request ID with a `UNIQUE` constraint, a request tracking table, or an idempotency mechanism to check the outcome before retrying.

Reduce deadlock risk by:

- Accessing multiple rows in the same order across all processing paths.
- Creating appropriate indexes to avoid unintended wide range locks.
- Keeping transactions short and locking only necessary rows.
- Not waiting on network calls, users, or external services while holding an open transaction.
- Handling errors and implementing bounded retries with idempotency when needed.

A deadlock is not necessarily a severe design flaw; in concurrent systems, applications still need a proper deadlock handling strategy.

## 19. Designing Short and Safe Transactions

A transaction should enclose operations that must succeed or fail together. Some principles:

1. Open the transaction as close as possible to the start of data operations.
2. Complete input validation that does not require locks before opening the transaction.
3. Acquire locks in a consistent order when multiple rows are needed.
4. Read/write only the necessary rows; ensure filter conditions have appropriate indexes.
5. Do not make HTTP calls, send emails, wait for users, or perform heavy work while holding locks.
6. Commit or roll back early; do not leave transactions hanging across multiple application processing steps.
7. Handle errors, deadlocks, and retries at the full-transaction level.
8. Use an idempotency key or unique constraint when clients might resend requests after a timeout.
9. Log business transaction identifiers for reconciliation; do not confuse application logs with a rollback mechanism.

Long transactions retain undo history and can slow down purge, hold locks for a long time, increase lock waits, and put pressure on storage. Monitor long-running open transactions in operations, especially when a connection is abandoned without committing or rolling back.

## 20. Transactions in Systems with External Services

A MySQL transaction cannot automatically roll back an operation that already happened in another system. For example, if a transaction updates an order and then calls a payment API, `ROLLBACK` only discards data in MySQL; it cannot automatically refund or cancel the transaction at the payment gateway.

For multi-service workflows, appropriate coordination patterns are needed:

- Write the state and an outbox event within the same database transaction.
- Have a worker read the outbox and dispatch events after commit.
- Have the receiving service process idempotently to avoid duplicate application when messages are redelivered.
- Use a saga/compensating action for distributed steps that require compensating actions.

These are system-level architectural patterns; the ACID guarantees of an InnoDB transaction still protect only the data within that transaction. Do not keep a database transaction open while waiting for an external service to respond.

## 21. Inspecting Transactions and Related Configuration

Some queries to observe state and configuration:

```sql
SELECT
    @@SESSION.autocommit AS autocommit_mode,
    @@SESSION.transaction_isolation AS isolation_level;
```

Check table engines:

```sql
SELECT TABLE_NAME, ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'BASE TABLE';
```

Check durability-related variables:

```sql
SHOW VARIABLES LIKE 'innodb_flush_log_at_trx_commit';
SHOW VARIABLES LIKE 'sync_binlog';
```

In an operational environment, DBAs can view active transactions and locks via appropriate system tables, such as `performance_schema` and `information_schema.innodb_trx` depending on version. Do not query or modify internal system tables arbitrarily; use monitoring tools and the minimum required privileges.

## 22. Common Mistakes and Misconceptions

| Misconception / Mistake | Reality | How to Handle |
| --- | --- | --- |
| Multiple consecutive UPDATE statements automatically form a transaction | With autocommit enabled, each individual statement can auto-commit | Use `START TRANSACTION` when steps belong to the same business unit |
| ROLLBACK can undo everything | Only discards uncommitted transactional changes; DDL can cause implicit commit | Separate DDL migrations from DML transactions |
| MySQL automatically enforces all business rules | The database only enforces declared rules and executed logic | Design comprehensive constraints and validation |
| Every storage engine supports ACID | Engines like MyISAM do not have transactional rollback like InnoDB | Use InnoDB for tables participating in transactions |
| A regular SELECT always locks rows | InnoDB consistent reads typically use an MVCC snapshot | Use locking reads when needing to protect a read-modify step |
| REPEATABLE READ means every SELECT sees the latest data | Consistent reads can use a snapshot; locking reads have different semantics | Distinguish consistent reads from `FOR UPDATE` |
| Nested START TRANSACTION creates nested transactions | MySQL does not support independent nested transactions | Use SAVEPOINT for partial rollback |
| A successful commit on primary means replicas have applied it | Asynchronous replicas may still have lag | Define replication consistency requirements separately |
| A deadlock only requires re-running the last statement | InnoDB may roll back the entire victim transaction | Retry the entire transaction with a retry limit |
| You can keep a transaction open while calling external APIs | Locks are held for a long time and rollback cannot undo external services | Use outbox/saga or process outside the transaction |

## 23. Practice Exercises

1. Create two InnoDB tables `accounts` and `account_transfers`; perform a transfer inside a single transaction.
2. Test rolling back after deducting funds but before crediting funds; verify that balances do not change.
3. Enable autocommit and run two separate UPDATE statements; observe why the second statement failing does not undo the first statement.
4. Use `START TRANSACTION`, update two tables, and commit; verify all changes appear together.
5. Open two connections and attempt to update the same account; compare consistent read with `SELECT ... FOR UPDATE`.
6. Test `READ COMMITTED` and `REPEATABLE READ` across two sessions to observe different snapshot behavior.
7. Create a `SAVEPOINT`, perform two changes, roll back to the savepoint, and then commit; verify which change remains.
8. Observe a DDL statement like `ALTER TABLE` while a transaction is open in a lab environment; verify implicit commit and do not use important data.
9. Create a controlled deadlock scenario across two connections; inspect the error and build full-transaction retry logic.
10. Check `@@SESSION.autocommit`, isolation level, table engines, and durability variables.
11. Design transaction boundaries for an order-creation workflow that deducts inventory and sends a notification after commit.

## 24. Key Takeaways

A transaction is a business unit of work that needs to be committed or rolled back as a unified whole. ACID comprises Atomicity (changes succeed or fail together), Consistency (maintaining data rules), Isolation (controlling concurrent interactions), and Durability (protecting committed changes according to storage configuration).

With MySQL, use InnoDB for tables that require transactions. `autocommit` is usually enabled by default, so multiple separate statements do not automatically become a shared business unit; use `START TRANSACTION`, `COMMIT`, and `ROLLBACK` for multi-step workflows. Understand isolation levels, MVCC, and locking reads to handle concurrency; use `SAVEPOINT` for partial rollbacks; avoid assuming DDL can be rolled back; keep transactions short, handle deadlocks by retrying the entire transaction, and remember that a transaction belongs to a single connection. ACID is the foundation for reliable data, yet you still need appropriate constraints, application logic, backups, monitoring, and error-handling procedures.
