# READ ONLY / READ WRITE and Choosing Transaction Characteristics

In MySQL, a transaction can be declared as `READ ONLY` or `READ WRITE`. This is the **access mode** of the transaction: whether the transaction only reads data from regular tables, or is permitted to read and modify data. MySQL also lets you choose the **isolation level** to control how concurrent transactions observe each other's changes.

When operating a relational database, choosing these characteristics properly gives reporting queries a consistent read scope while giving business transactions explicit write permission. Understand that read/write mode and isolation level are two separate choices: `READ ONLY` does not automatically mean `SERIALIZABLE`, and `READ WRITE` does not automatically mean `READ COMMITTED`.

## 1. Two Transaction Access Modes

### `READ ONLY`

A `READ ONLY` transaction is declared to read data from regular tables. MySQL does not allow this transaction to modify non-temporary tables. Temporary tables are an exception: the transaction can still insert, update, or delete data in temporary tables.

Example of a read-only transaction to aggregate a report:

```sql
START TRANSACTION READ ONLY;

SELECT COUNT(*) AS order_count
FROM orders
WHERE created_at >= '2026-01-01';

SELECT SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= '2026-01-01';

COMMIT;
```

The transaction can execute multiple `SELECT` statements before ending. With InnoDB, declaring upfront that the transaction is read-only also allows the engine to apply certain optimizations tailored for read-only transactions.

If you attempt to update a regular table inside this transaction, MySQL rejects the statement:

```sql
START TRANSACTION READ ONLY;

UPDATE orders
SET total_amount = total_amount + 10000
WHERE order_id = 1001;

ROLLBACK;
```

`UPDATE` is not executed because the transaction was declared `READ ONLY`. `ROLLBACK` ends the transaction.

### `READ WRITE`

A `READ WRITE` transaction is permitted to read and modify data, provided the account has appropriate privileges and data constraints are satisfied. This is the default mode when MySQL starts a transaction unless configured otherwise.

```sql
START TRANSACTION READ WRITE;

UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 9001;

INSERT INTO stock_movements (product_id, quantity_change, reason)
VALUES (9001, -2, 'Sale');

COMMIT;
```

Both changes are grouped in the same transaction. If the workflow detects an error before committing, the application can `ROLLBACK` to discard the executed transactional changes.

`READ WRITE` only declares that the transaction is allowed to write. It does not bypass access privileges, locks, foreign key constraints, unique constraints, or other statement errors.

## 2. Declaring the Mode Directly When Starting a Transaction

MySQL allows passing transaction characteristics directly to `START TRANSACTION`:

```sql
START TRANSACTION READ ONLY;
-- Read-only statements
COMMIT;

START TRANSACTION READ WRITE;
-- Statements that can read and write
COMMIT;
```

If neither `READ ONLY` nor `READ WRITE` is specified, the transaction uses the active default access mode. You can also specify `WITH CONSISTENT SNAPSHOT` when needing to create a consistent snapshot for InnoDB at an appropriate isolation level:

```sql
START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;

SELECT COUNT(*) FROM orders;
SELECT COUNT(*) FROM order_items;

COMMIT;
```

`WITH CONSISTENT SNAPSHOT` only takes effect in InnoDB when the isolation level is `REPEATABLE READ`. If another isolation level is used, MySQL ignores this option. With `REPEATABLE READ`, the option creates a consistent snapshot immediately at the start of the transaction instead of waiting until the first consistent read.

## 3. Setting Characteristics for the Next Transaction or the Session

Besides declaring them on `START TRANSACTION`, MySQL provides `SET TRANSACTION` to configure transaction characteristics. The scope of effect depends on the accompanying keyword:

| Statement | Scope of Effect |
|---|---|
| `SET TRANSACTION ...` | Only the next transaction in the current session |
| `SET SESSION TRANSACTION ...` | Default for subsequent transactions in the current session |
| `SET GLOBAL TRANSACTION ...` | Default for new sessions created afterward; does not change existing sessions |

Example setting the next transaction to read-only mode:

```sql
SET TRANSACTION READ ONLY;

START TRANSACTION;
SELECT * FROM orders WHERE order_id = 1001;
COMMIT;
```

Example setting the default for subsequent transactions on the current connection:

```sql
SET SESSION TRANSACTION READ ONLY;

START TRANSACTION;
SELECT COUNT(*) FROM orders;
COMMIT;
```

When writes are needed, you can reset the session or override for a specific transaction:

```sql
START TRANSACTION READ WRITE;
UPDATE orders
SET total_amount = 150000.00
WHERE order_id = 1001;
COMMIT;
```

A `SESSION` setting persists on the connection until changed or the connection terminates. A `GLOBAL` setting requires appropriate administrative privileges and only affects new connections. Do not confuse changing characteristics for the next transaction with altering an already started transaction.

## 4. Choosing the Transaction Isolation Level

The `READ ONLY`/`READ WRITE` mode answers whether a transaction is allowed to write. The isolation level answers how a transaction sees data from other transactions. MySQL supports four standard isolation levels:

| Isolation Level | Key Behavior | When to Consider Using |
|---|---|---|
| `READ UNCOMMITTED` | Can read uncommitted changes from other transactions (dirty read) | Consider only when transient data is acceptable and risks are well understood |
| `READ COMMITTED` | Does not read uncommitted data; each consistent read in the transaction can see a fresh snapshot | When you need to see recently committed changes between reads |
| `REPEATABLE READ` | Consistent reads in the same transaction use the same snapshot established at the first consistent read | When stable repeatable read results are needed; this is InnoDB's common default |
| `SERIALIZABLE` | Behaves more strictly so transactions yield results equivalent to a serial execution order | When correctness demands high isolation and more lock waits are acceptable |

Phenomena commonly used to understand isolation levels:

- **Dirty read:** reading data that a writing transaction has not yet committed; the writing transaction may later roll back.
- **Non-repeatable read:** the same query reads a row twice and receives different values because another transaction committed an update in between.
- **Phantom read:** re-running a query condition and seeing additional or missing matching rows because another transaction modified that set of rows.

In InnoDB, `REPEATABLE READ` uses MVCC-based consistent reads so regular reads inside the transaction share the same snapshot. Locking read statements such as `SELECT ... FOR UPDATE` or `SELECT ... FOR SHARE` have their own read and locking rules; do not equate them with regular consistent reads.

InnoDB's default isolation level in MySQL is usually `REPEATABLE READ`, though server or session configuration can alter this value. Check the actual environment before relying on the default.

## 5. Setting the Isolation Level with `SET TRANSACTION`

You can set the isolation level for the next transaction:

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION READ ONLY;
SELECT COUNT(*) FROM orders;
COMMIT;
```

Or set the default for subsequent transactions in the current session:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
```

If an administrator needs to apply a default for new sessions, the `GLOBAL` scope can be used:

```sql
SET GLOBAL TRANSACTION ISOLATION LEVEL READ COMMITTED;
```

The `GLOBAL` command requires appropriate privileges. It does not alter the isolation level of already open connections; existing sessions must reset it themselves using the `SESSION` scope if they want the new value.

You can set both isolation level and access mode in a single statement:

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ ONLY;
START TRANSACTION;

SELECT order_id, total_amount
FROM orders
WHERE created_at >= CURRENT_DATE - INTERVAL 7 DAY;

COMMIT;
```

In this example, the next transaction uses `READ COMMITTED` and `READ ONLY`. The two characteristics are chosen independently but can be declared together.

## 6. Combining Access Mode with Business Transactions

### Reports Needing a Consistent View

Suppose a report reads total orders and total order items. If consistent reads within a single snapshot are needed, you can use InnoDB with `REPEATABLE READ` and `WITH CONSISTENT SNAPSHOT`:

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;

SELECT COUNT(*) AS order_count
FROM orders;

SELECT COUNT(*) AS item_count
FROM order_items;

COMMIT;
```

Consistent reads inside the transaction view data according to the snapshot created at the start. The transaction ends with `COMMIT` because there are no changes to undo; `ROLLBACK` can also end a read-only transaction.

### Data Updates Requiring Error Control

A business transaction typically needs `READ WRITE` and an isolation level matching data rules:

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION READ WRITE;

UPDATE accounts
SET balance = balance - 50000
WHERE account_id = 10;

UPDATE accounts
SET balance = balance + 50000
WHERE account_id = 20;

COMMIT;
```

This only illustrates how to declare characteristics. A real application must verify the source account exists, balance is sufficient, affected row counts match, and handle every error before committing. If a business condition is not met, roll back to avoid completing only half of the money transfer.

## 7. Operational Notes

**Do not treat `READ ONLY` as a transaction that does not need closing.** A read-only transaction still holds a snapshot and can retain resources or affect purging old row versions in InnoDB. Finish with `COMMIT` or `ROLLBACK` as soon as reading is done, especially for long reports.

**Do not leave transactions open while waiting for users.** Avoid opening a transaction and then waiting for user input, calling external services, or performing long-running tasks. Long open transactions can hold locks (if any) and increase the cost of maintaining read views.

**Be careful with connection pools.** `SET SESSION TRANSACTION ...` changes connection state. When the connection is returned to the pool, session settings may persist and affect the next user. Configure consistently upon connection creation/checkout or restore session state according to the pool's policy.

**Do not expect `ROLLBACK` to undo every kind of statement.** MySQL has DDL statements that cause an implicit commit. Never place `CREATE TABLE`, `ALTER TABLE`, or `DROP TABLE` between DML operations expecting rollback to restore the entire prior state.

**Do not start nested transactions with `START TRANSACTION`.** MySQL does not support nested transactions where an inner `START TRANSACTION` automatically creates a new transaction layer. Starting a new transaction can end an open transaction via implicit commit. If you need rollback points inside a transaction, look into `SAVEPOINT`, `ROLLBACK TO SAVEPOINT`, and `RELEASE SAVEPOINT`.

## 8. Quick Selection Table

| Need | Access Mode | Suggested Isolation Level | Notes |
|---|---|---|---|
| Reporting queries without modifying tables | `READ ONLY` | `REPEATABLE READ` if the same snapshot is needed across multiple reads | Can add `WITH CONSISTENT SNAPSHOT` for InnoDB |
| Reading data while seeing newly committed data on each read | `READ ONLY` | `READ COMMITTED` | Each consistent read can receive a fresh snapshot |
| Updating multiple tables in a business operation | `READ WRITE` | Choose according to invariants and concurrency behavior to protect | Verify results and roll back when business logic fails |
| Workflow requiring strict isolation | `READ WRITE` or `READ ONLY` | `SERIALIZABLE` | Evaluate lock wait and throughput impact |

There is no single isolation level suitable for every query. Start from business consistency requirements, decide whether the transaction needs writes, and then choose the isolation level and keep transaction duration as short as possible.

## 9. Self-Check

1. Does `READ ONLY` allow inserting data into a temporary table? Why?
2. What is the difference between `SET TRANSACTION READ ONLY` and `SET SESSION TRANSACTION READ ONLY`?
3. Why are `READ ONLY` and `REPEATABLE READ` not two names for the same characteristic?
4. In what scenario does `WITH CONSISTENT SNAPSHOT` take effect with InnoDB?
5. Why should you pay attention to session settings when using a connection pool?
6. Why should you avoid leaving a read-only transaction open for a long time?
