# Distinguishing Persistent Data, Session State, and Temporary Data in PostgreSQL

## 1. Why Must You Distinguish These Three State Lifetimes?

In PostgreSQL, not everything created or changed by an SQL statement shares the same **lifecycle**. Some data must survive application disconnects and server restarts. Some state exists only for the lifetime of one connection. Still other temporary tables or temporary disk files serve short-lived work, and changes inside an open transaction can be undone on `ROLLBACK`.

For example, an order-processing application runs:

```sql
INSERT INTO orders (order_id, amount)
VALUES (1001, 250000.00);
```

Another session runs:

```sql
SET statement_timeout = '5s';
```

And a report creates:

```sql
CREATE TEMP TABLE selected_orders AS
SELECT * FROM orders WHERE amount >= 100000;
```

All three look like ordinary SQL statements, yet their effects differ fundamentally:

- `orders` is a regular table; its **committed** changes are designed to survive client disconnections and normal PostgreSQL restarts.
- `statement_timeout` set at session level affects only **the current connection** and does not become a permanent database configuration.
- `selected_orders` is a **temporary table**, private to the session that created it and normally dropped when that session ends.

Confusing these lifecycles causes subtle bugs: a batch job thinks it saved a report only for the table to vanish when the connection pool closes the socket; an HTTP request inherits the previous request's `search_path`; or a workflow uses an `UNLOGGED` table for business data and loses it after a crash.

> **Foundational principle:** in PostgreSQL, always ask separately **how long an object lives**, **who can see it**, **when changes commit or roll back**, and **whether it survives crash recovery**. These four questions are related, yet distinct.

## 2. Concept Map: Database, Session, Transaction, and Temporary Objects

PostgreSQL follows a client/server architecture. An application or `psql` opens a connection to the server to send queries. Each normal direct connection is served by a dedicated PostgreSQL backend process holding its own session state.

```text
                 PostgreSQL Server
        +------------------------------------+
        |                                    |
Client A ---> Backend / Session A            |
        |       |                            |
        |       +-- GUC: search_path         |
        |       +-- Prepared statements      |
        |       +-- Temporary table A        |
        |       +-- Current transaction      |
        |                                    |
Client B ---> Backend / Session B            |
        |       |                            |
        |       +-- GUC: statement_timeout   |
        |       +-- Temporary table B        |
        |       +-- Current transaction      |
        |                                    |
        |           Shared database          |
        |       +-------------------------+  |
        |       | Permanent tables        |  |
        |       | Indexes, catalog        |  |
        |       | WAL / durable storage   |  |
        |       +-------------------------+  |
        +------------------------------------+
```

Four concepts to distinguish:

| Concept | Meaning | Typical lifecycle |
| --- | --- | --- |
| **Regular database object** | Persistent tables, indexes, views, and data | Until altered/dropped via SQL or admin action |
| **Session** | A working connection to PostgreSQL plus its private state | From connection establishment until close/drop |
| **Transaction** | Group of operations requiring atomicity and isolation | From `BEGIN` to `COMMIT`/`ROLLBACK`, or one statement under autocommit |
| **Temporary object/data** | Temporary tables or intermediate workspace for a session/task | Depends on kind: typically per session; may be shorter per transaction or statement |

**A session is not a transaction.** One session can execute many sequential transactions. Conversely, a single transaction executes strictly on the connection running it; an application cannot start a transaction on connection A and expect SQL sent over connection B to join it automatically.

### 2.1. Nested lifecycles

```text
Session A (open connection)
│
├── SET statement_timeout = '5s'
│   └── Effective in session A until RESET / another SET / connection close
│
├── Transaction 1: BEGIN ... COMMIT
│   └── Committed changes become database changes
│
├── Transaction 2: BEGIN ... ROLLBACK
│   └── Changes in this transaction are rolled back
│
├── Temporary table session_report
│   └── Normally persists across multiple transactions in session A
│
└── Close connection
    ├── Session state disappears
    └── Session's temporary table is dropped

Database
└── Committed permanent table data remains
    across multiple sessions and normal restarts
```

This diagram makes clear that **`COMMIT` does not close a session**, and **closing a session does not delete committed regular table data**.

## 3. Persistent Data: Permanent Tables and Committed Transactions

### 3.1. Permanent tables are the default

In PostgreSQL, a table created with `CREATE TABLE` without `TEMP` or `UNLOGGED` is a **permanent table**.

```sql
CREATE SCHEMA IF NOT EXISTS lifecycle_lab;

CREATE TABLE IF NOT EXISTS lifecycle_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Data in this table persists as part of the database. Once a transaction writes and commits, authorized sessions can read the change per **MVCC and transaction isolation rules**.

Example:

```sql
BEGIN;

INSERT INTO lifecycle_lab.orders
    (order_id, customer_name, amount)
VALUES
    (1001, 'Nguyễn An', 250000.00);

COMMIT;
```

After the client closes the connection, row `order_id = 1001` **is not deleted merely because the session ended**.

In another session:

```sql
SELECT order_id, customer_name, amount
FROM lifecycle_lab.orders
WHERE order_id = 1001;
```

Session B sees the committed row provided it has `SELECT` privilege and is not pinned to an older snapshot by its isolation level.

### 3.2. Changes before commit are not committed data

Suppose Session A runs:

```sql
BEGIN;

INSERT INTO lifecycle_lab.orders
    (order_id, customer_name, amount)
VALUES (1002, 'Trần Bình', 160000.00);

-- Not COMMITted yet.
```

Meanwhile, Session B runs:

```sql
SELECT * FROM lifecycle_lab.orders WHERE order_id = 1002;
```

Under the default `READ COMMITTED` isolation level, B **does not see** A's uncommitted row. Once A runs:

```sql
COMMIT;
```

a new `SELECT` in B sees row 1002. If A runs `ROLLBACK` instead of `COMMIT`, that row never becomes committed data.

This highlights three distinct states:

- **Visible within the current transaction:** the writing session sees its own uncommitted writes.
- **Committed and visible to other sessions:** depends on commit, privileges, and snapshots.
- **Durable against crashes:** depends additionally on WAL and durability configuration.

### 3.3. WAL and durability mechanics

PostgreSQL uses the **Write-Ahead Log (WAL)** to recover changes after crashes. Conceptually:

```text
INSERT/UPDATE/DELETE
        |
        v
Changes in buffer cache and required WAL records
        |
        v
COMMIT: confirmed per active WAL write policy
        |
        v
When needed: flush data pages to disk
        |
        v
Crash recovery uses WAL to restore consistency
```

Under standard durability settings, PostgreSQL is engineered to preserve committed changes across a crash within WAL, OS, and storage guarantees.

**Never state "once committed, data can never be lost under any circumstance."** Exceptions and risks exist:

- `synchronous_commit = off` allows acknowledging commits before WAL is durably flushed, risking loss of recently acknowledged transactions on crash.
- Disabling `fsync` or using storage hardware that lies about flush completion undermines durability.
- Hardware failure, disk corruption, or administrative mistakes can still cause data loss.
- Replication and backups follow their own durability/recovery semantics; WAL does not replace backups.

Thus, **permanent** describes the table kind and expected lifecycle; **durable** is a transactional and storage property under specific settings.

### 3.4. What effect does closing a session or restarting have?

Given `lifecycle_lab.orders` exists and row 1001 is committed:

| Event | Permanent table and committed data |
| --- | --- |
| Closing `psql` or application connection | Continues to exist |
| Opening a new session | Readable per privileges and snapshot |
| `COMMIT` in another session | Does not delete the table |
| `ROLLBACK` of a read-only transaction | Does not undo previously committed data |
| Normal PostgreSQL restart | Data persists |
| Crash/recovery | Recovered per WAL and durability settings |
| Committed `DROP TABLE` | Object is dropped per SQL semantics |
| Committed `DELETE` | Row is deleted per predicate and MVCC rules |

"Persistent" does not mean "undeletable"; authorized SQL commands can still delete rows or drop tables.

## 4. What Is Session State?

A **session** is the working context tied to a PostgreSQL connection. It holds per-connection settings and resources the server maintains while that connection stays alive.

Examples of session state include:

- Configuration values changed with `SET` (GUCs, i.e., *Grand Unified Configuration* settings).
- `search_path`, date/time formatting, timezone, and timeouts.
- Prepared statements created via SQL `PREPARE`.
- Active cursors/portals within their respective lifecycles.
- Session-level advisory locks.
- `LISTEN` registrations on notification channels.
- Temporary tables owned by that session.
- Any active transaction, savepoints, and uncommitted writes.

### 4.1. Identifying a session by backend PID

In two separate `psql` windows:

```sql
SELECT
    pg_backend_pid() AS backend_pid,
    current_database() AS db_name,
    current_user AS db_user;
```

Each direct session normally has a distinct **backend PID**. Closing and reconnecting creates a new backend (though OS PIDs can eventually be recycled over time).

Never use a PID as a permanent user identifier. It only identifies a backend during its active lifetime.

### 4.2. How long does a session live in applications?

In interactive `psql`, a session normally lasts from connect until `\q` or disconnect.

In a Java application using a connection pool:

```text
HTTP request A -> borrow Connection #5
               -> SET search_path...
               -> return Connection #5 to pool

HTTP request B -> borrow Connection #5
               -> may see leftover session state
```

Returning a connection **to the pool** does not necessarily **close the server session**. When the pool hands that connection to the next caller, session-level settings can leak into the next request.

Some pools or proxies run reset policies; inspect your actual pool configuration rather than assuming every borrowed connection is a brand-new PostgreSQL session.

## 5. Clear Example of Session State: `SET` and `RESET`

Suppose connection A runs:

```sql
SHOW statement_timeout;

SET statement_timeout = '5s';

SHOW statement_timeout;
```

`statement_timeout` caps statement execution duration in the session. After `SET`, subsequent statements in Session A obey that limit until another `SET`, `RESET`, or session termination (also respecting transaction rollback rules).

In connection B:

```sql
SHOW statement_timeout;
```

B **does not inherit** the value A set. B uses its own setting from server/database/role/session defaults.

### 5.1. Session-level `SET`

```sql
SET search_path TO lifecycle_lab, public;
SET statement_timeout = '5s';
SET TIME ZONE 'Asia/Ho_Chi_Minh';
```

These changes apply from the time set until overridden/reset or session close. If `SET` runs inside a transaction that later rolls back, the `SET` effect is also undone per PostgreSQL transactional semantics.

Verify:

```sql
SHOW search_path;
SHOW statement_timeout;
SHOW TimeZone;
```

Distinguish `SET` from changing defaults via `ALTER ROLE ... SET` or `ALTER DATABASE ... SET`: those DDL commands change **default values for future matching sessions**, not merely temporary state on one connection.

### 5.2. `SET LOCAL` applies only within the current transaction

```sql
BEGIN;

SET LOCAL statement_timeout = '2s';

SHOW statement_timeout;

SELECT COUNT(*)
FROM lifecycle_lab.orders;

COMMIT;

SHOW statement_timeout;
```

Inside the transaction, `statement_timeout` is locally `2s`. After `COMMIT`, `SET LOCAL` expires and the session reverts to its prior setting.

**Do not run `SET LOCAL` outside a transaction block expecting it to guard subsequent SQL.** In PostgreSQL, `SET LOCAL` requires an explicit transaction block and emits a warning with no lasting effect outside one.

### 5.3. `RESET` and restoring defaults

```sql
SET statement_timeout = '5s';

RESET statement_timeout;

SHOW statement_timeout;
```

`RESET` restores the effective default for the session (per config precedence), not necessarily zero.

You can also run:

```sql
RESET ALL;
```

yet this only resets resettable GUC settings; it **does not** drop temporary tables, deallocate prepared statements, or clear other session resources.

### 5.4. `SET ROLE` is also session state

Where role grants permit, a session can switch its active role:

```sql
SET ROLE reporting_role;

SELECT current_user, session_user;

RESET ROLE;
```

`reporting_role` is an example name; the role must exist and the login role must be a member allowed to switch to it. Switching roles does not open a new connection. Forgetting to reset it causes subsequent statements on the same connection to run under an unintended privilege context.

## 6. Transaction State: Shorter Than a Session, Not Temporary Storage

A **transaction** is the atomic unit bounded by `BEGIN`, `COMMIT`, and `ROLLBACK`. Transaction state includes the active snapshot, uncommitted changes, locks, savepoints, and `SET LOCAL` settings.

```sql
BEGIN;

UPDATE lifecycle_lab.orders
SET amount = amount + 10000
WHERE order_id = 1001;

-- Only the current transaction sees its uncommitted change.

ROLLBACK;
```

After rollback, the previously committed `amount` remains unchanged without the +10000 increment.

### 6.1. One session can execute multiple transactions

```text
Connection A
   ├── BEGIN (Transaction 1)
   ├── UPDATE ...
   ├── COMMIT
   ├── SELECT ...
   ├── BEGIN (Transaction 2)
   ├── SET LOCAL ...
   ├── SELECT ...
   ├── ROLLBACK
   └── Connection stays open
```

**Ending a transaction does not close the session.** That is why session `SET` variables and `ON COMMIT PRESERVE ROWS` temporary tables survive `COMMIT`.

### 6.2. `SAVEPOINT` manages partial rollback

```sql
BEGIN;

UPDATE lifecycle_lab.orders
SET amount = amount + 1000
WHERE order_id = 1001;

SAVEPOINT before_optional_step;

UPDATE lifecycle_lab.orders
SET amount = amount + 5000
WHERE order_id = 1001;

ROLLBACK TO SAVEPOINT before_optional_step;

COMMIT;
```

The update after the savepoint is undone, while the earlier update commits. Savepoints belong to the **transaction** and vanish when the transaction ends.

### 6.3. Isolation level determines change visibility

Under `READ COMMITTED`, each statement receives a fresh snapshot seeing commits completed prior to that statement. Under `REPEATABLE READ`, the transaction keeps a consistent transaction-wide snapshot within isolation rules.

Consequently, Session B may **not yet see** changes A just committed if B is reading from an older snapshot, even though the table is permanent and the commit succeeded.

**Durability, visibility, and session lifecycle are three distinct properties.**

## 7. Temporary Tables: Session-Owned, Never Shared

PostgreSQL lets sessions create **temporary tables**:

```sql
CREATE TEMP TABLE work_ids (
    order_id bigint PRIMARY KEY
);
```

Or in full form:

```sql
CREATE TEMPORARY TABLE work_ids (
    order_id bigint PRIMARY KEY
);
```

It behaves structurally like a normal SQL table within its scope, except:

- Only the creating session can access that temporary table normally.
- Another session can create a temporary table with the **exact same name**, yet it is a completely separate object.
- Temporary tables are automatically dropped when the session ends.
- By default, PostgreSQL uses **`ON COMMIT PRESERVE ROWS`**, meaning `COMMIT` **keeps** rows inside the temporary table.
- You can instead specify `ON COMMIT DELETE ROWS` or `ON COMMIT DROP`.

### 7.1. Creating a temporary table to hold intermediate results

Suppose `lifecycle_lab.orders` is populated and you want to stage high-value orders:

```sql
CREATE TEMP TABLE high_value_orders AS
SELECT order_id, customer_name, amount
FROM lifecycle_lab.orders
WHERE amount >= 200000;

SELECT *
FROM high_value_orders
ORDER BY amount DESC, order_id;
```

`CREATE TEMP TABLE ... AS SELECT` materializes a **snapshot copy of the query results at creation time**, not a live view tracking the base table. Later edits to `orders` **do not automatically update** `high_value_orders`.

Avoid confusing these three:

- **View:** stores a query definition evaluated against underlying tables on read.
- **Temporary table:** stores private session-scoped rows.
- **CTE:** structures a single SQL statement, not a persistent temp table queryable across separate statements.

### 7.2. Temporary tables are never shared with other sessions

In Session A:

```sql
CREATE TEMP TABLE report_stage (
    id integer PRIMARY KEY,
    note text
);

INSERT INTO report_stage (id, note)
VALUES (1, 'Session A only');

SELECT * FROM report_stage;
```

In Session B (an independent connection):

```sql
SELECT * FROM report_stage;
```

B raises a relation-does-not-exist error unless another object with that name exists in B's search path. B **never sees A's temporary table** merely by connecting to the same database.

If B creates its own:

```sql
CREATE TEMP TABLE report_stage (
    id integer PRIMARY KEY,
    note text
);

INSERT INTO report_stage (id, note)
VALUES (2, 'Session B only');
```

both sessions own **two completely independent temporary tables** despite identical SQL names.

### 7.3. Using temporary tables without database-wide naming collisions

PostgreSQL assigns each session a private temporary schema internally, named like `pg_temp_N`. Within your own session, reference temporary tables unqualified or via the `pg_temp` alias:

```sql
SELECT * FROM pg_temp.report_stage;
```

`pg_temp` always resolves to the current session's temporary schema—it is not a shared global schema for exchanging temporary data across connections.

## 8. Three `ON COMMIT` Policies for Temporary Tables

Each temporary table can specify its behavior when a **transaction commits**:

| Policy | After `COMMIT` | After session closes |
| --- | --- | --- |
| `ON COMMIT PRESERVE ROWS` | Keeps table structure and committed rows | Table is dropped |
| `ON COMMIT DELETE ROWS` | Keeps table structure; deletes all rows | Table is dropped |
| `ON COMMIT DROP` | Drops the temporary table on commit | Already dropped or dropped at session end |

### 8.1. Default: `ON COMMIT PRESERVE ROWS`

```sql
CREATE TEMP TABLE stage_preserve (
    id integer PRIMARY KEY
) ON COMMIT PRESERVE ROWS;

BEGIN;

INSERT INTO stage_preserve (id)
VALUES (10);

COMMIT;

SELECT * FROM stage_preserve;
```

Within the same session, `id = 10` remains visible after commit. If you disconnect and open a new session, `stage_preserve` is gone.

### 8.2. `ON COMMIT DELETE ROWS`

```sql
CREATE TEMP TABLE stage_delete (
    id integer PRIMARY KEY
) ON COMMIT DELETE ROWS;

BEGIN;

INSERT INTO stage_delete (id)
VALUES (20);

SELECT COUNT(*) AS rows_before_commit
FROM stage_delete;

COMMIT;

SELECT COUNT(*) AS rows_after_commit
FROM stage_delete;
```

Inside the transaction, 1 row exists. After `COMMIT`, the table still exists yet holds zero rows: `rows_after_commit = 0`.

This fits workflows reusing the same temporary table definition across transactions while starting each transaction with an empty slate.

**Autocommit warning:** running `INSERT` into an `ON COMMIT DELETE ROWS` table without an explicit transaction commits immediately at statement end, wiping the rows right away. Always use `BEGIN` explicitly when inspecting rows prior to commit.

### 8.3. `ON COMMIT DROP`

```sql
BEGIN;

CREATE TEMP TABLE stage_drop (
    id integer PRIMARY KEY
) ON COMMIT DROP;

INSERT INTO stage_drop (id)
VALUES (30);

SELECT * FROM stage_drop;

COMMIT;
```

After `COMMIT`, `stage_drop` no longer exists:

```sql
-- After commit, in the same session:
SELECT * FROM stage_drop;
-- Expected error: relation does not exist.
```

**Important warning:** creating an `ON COMMIT DROP` table outside an explicit transaction in autocommit mode drops the table immediately after `CREATE TEMP TABLE` finishes. That is why the example places `BEGIN` **before** creating the table.

### 8.4. Why must you understand all three policies?

Consider a multi-step script:

```text
CREATE TEMP TABLE stage
INSERT rows
COMMIT
SELECT FROM stage
```

With `PRESERVE ROWS`, the rows are still there. With `DELETE ROWS`, the table exists but is empty. With `DROP`, `SELECT` fails because the table is gone.

Three completely different outcomes despite all three being called "temporary tables."

## 9. Temporary Tables Still Obey Transaction Rules

Although a temporary table has a **session lifecycle**, creating, altering, and writing rows to it still obey transaction semantics.

### 9.1. Rolling back inserted rows

In Session A:

```sql
CREATE TEMP TABLE temp_tx (
    id integer PRIMARY KEY
);

INSERT INTO temp_tx(id) VALUES (1);

BEGIN;

INSERT INTO temp_tx(id) VALUES (2);

ROLLBACK;

SELECT id FROM temp_tx ORDER BY id;
```

Only `id = 1` remains; `id = 2` is gone because row 1 committed in the prior statement (under autocommit), whereas row 2 ran inside the rolled-back transaction.

Temporary table data therefore **never** means "non-transactional" or "un-rollbackable."

### 9.2. Rolling back table creation

```sql
BEGIN;

CREATE TEMP TABLE temp_created_in_tx (
    id integer
);

INSERT INTO temp_created_in_tx(id)
VALUES (1);

ROLLBACK;
```

After `ROLLBACK`, `CREATE TEMP TABLE` itself is rolled back and `temp_created_in_tx` no longer exists in that session.

Conversely, a temporary table created and committed prior to a later transaction survives if that later transaction rolls back. Session lifecycle and transaction atomicity **coexist**, rather than contradicting each other.

### 9.3. `SAVEPOINT` with temporary tables

```sql
CREATE TEMP TABLE temp_savepoint (
    id integer PRIMARY KEY
);

BEGIN;

INSERT INTO temp_savepoint(id) VALUES (1);

SAVEPOINT before_second_insert;

INSERT INTO temp_savepoint(id) VALUES (2);

ROLLBACK TO SAVEPOINT before_second_insert;

COMMIT;

SELECT * FROM temp_savepoint ORDER BY id;
```

After commit, only `id = 1` remains—showing PostgreSQL protects temporary table writes with transactions and savepoints too.

## 10. Unlogged Tables: Neither Fully Permanent Nor Temporary

A third crucial table type in PostgreSQL is the **UNLOGGED table**:

```sql
CREATE UNLOGGED TABLE lifecycle_lab.import_stage (
    batch_id bigint NOT NULL,
    line_no integer NOT NULL,
    raw_value text NOT NULL,
    PRIMARY KEY (batch_id, line_no)
);
```

An `UNLOGGED` table:

- Has a named catalog object **persisting across sessions**.
- Can be accessed concurrently by other sessions subject to privileges and transactions.
- Normally survives **a clean shutdown and restart**.
- Skips writing WAL for **table data**, reducing WAL overhead.
- **Lacks crash recovery durability**: after a crash or unclean shutdown, PostgreSQL **truncates** unlogged table data.
- Does not stream data over **physical streaming replication** like logged permanent tables; never rely on it on standbys.

### 10.1. UNLOGGED does not mean TEMP

| Property | Permanent table | UNLOGGED table | TEMP table |
| --- | --- | --- | --- |
| Multiple sessions share the same object? | Yes, per privileges and MVCC | Yes, per privileges and MVCC | No; per-session object |
| Survives closing creating session? | Yes | Yes | No |
| Survives clean restart? | Yes | Yes | No |
| Data protected across crashes by standard WAL? | Yes, per durability config | No; truncated on crash recovery | No; session ends |
| Suitable for durable business records? | Yes | No, unless fully reproducible | No |
| Supports transactions for DML? | Yes | Yes | Yes |

`UNLOGGED` is suited for **reproducible or reloadable data** such as import staging tables—never unique data that cannot be rebuilt from another source.

### 10.2. Two-session example with UNLOGGED

Session A:

```sql
INSERT INTO lifecycle_lab.import_stage
    (batch_id, line_no, raw_value)
VALUES (7, 1, 'original file line');

COMMIT;
```

Under autocommit, `INSERT` commits immediately, so a trailing `COMMIT` outside a transaction only emits a warning. In real code, pick **one consistent transaction style**:

```sql
BEGIN;

INSERT INTO lifecycle_lab.import_stage
    (batch_id, line_no, raw_value)
VALUES (7, 2, 'another line');

COMMIT;
```

Session B can read both committed rows:

```sql
SELECT *
FROM lifecycle_lab.import_stage
WHERE batch_id = 7
ORDER BY line_no;
```

Unlogged data is not confined to Session A like a temporary table. Yet on a crash, its contents are wiped/truncated by PostgreSQL.

### 10.3. Rules for choosing UNLOGGED

Consider `UNLOGGED` only when all of these hold:

1. Data can be rebuilt completely from an authoritative source.
2. Impact of losing staging contents on crash is explicitly accepted.
3. Normal WAL-based replication to standbys is not required for this table.
4. Measured WAL reduction brings meaningful benefit to the workload.
5. Reload, cleanup, and job-recovery procedures exist.

Never convert orders, payments, or account balances to `UNLOGGED` merely for faster writes.

## 11. Comparing Along Three Axes: Lifecycle, Visibility, and Crash Recovery

To stay clear, separate three questions:

**Question A — Lifecycle:** when does data disappear?

- Permanent: persists until altered/deleted via SQL or admin operation.
- UNLOGGED: table definition persists, yet data is truncated after a crash.
- TEMP: vanishes on session close, or earlier on `ON COMMIT DROP`.
- `SET LOCAL`: expires when the transaction ends.
- Session `SET`: expires when the session closes or is changed/reset.

**Question B — Who sees it?**

- Permanent and UNLOGGED: multiple sessions, governed by privileges and MVCC.
- TEMP: only the creating session; other sessions cannot directly read that temp table.
- Session settings: only the corresponding connection.
- Uncommitted transaction changes: hidden from other sessions.

**Question C — Does it survive a crash?**

- Permanent tables: yes, subject to WAL and durability settings.
- UNLOGGED tables: no such data guarantee.
- Temporary tables and session state: gone because the connection terminated.
- Executor temporary files: intermediate workspace, never durable storage.

## 12. Inspecting Table Persistence via `pg_class`

PostgreSQL stores relation metadata in system catalogs. `pg_class.relpersistence` indicates persistence mode:

| Value | Meaning |
| --- | --- |
| `p` | Permanent |
| `u` | Unlogged |
| `t` | Temporary |

Inspect on a lab database:

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    c.relpersistence
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relname IN (
    'orders',
    'import_stage',
    'temp_tx',
    'stage_preserve'
)
ORDER BY n.nspname, c.relname;
```

If you run this from a session that did not create the temp tables, other sessions' temp tables can still appear in `pg_class` metadata, yet **that never means** your session can read another session's temporary table data. Separate catalog visibility from session data access.

### 12.1. Identifying your session's temp schema

```sql
SELECT
    pg_backend_pid() AS backend_pid,
    pg_my_temp_schema() AS my_temp_schema_oid;
```

`pg_my_temp_schema()` returns the OID of the current session's temp schema (or `0` if none has been created yet). You can look up its name in `pg_namespace` if needed:

```sql
SELECT nspname
FROM pg_namespace
WHERE oid = pg_my_temp_schema();
```

Seeing internal names like `pg_temp_3` is never an invitation to guess temp schema numbers to access another session's data. Always use your own `pg_temp` alias or unqualified temp table names.

## 13. Temporary Tables and Shadowed Object Names

Suppose a real permanent table exists:

```sql
CREATE TABLE lifecycle_lab.metrics (
    metric_name text PRIMARY KEY,
    metric_value integer NOT NULL
);

INSERT INTO lifecycle_lab.metrics
    (metric_name, metric_value)
VALUES ('daily_orders', 100);
```

Session A creates a temporary table with the same unqualified name:

```sql
CREATE TEMP TABLE metrics (
    metric_name text PRIMARY KEY,
    metric_value integer NOT NULL
);

INSERT INTO metrics
VALUES ('daily_orders', 999);
```

Inside Session A:

```sql
SELECT * FROM metrics;
```

resolves to the temporary table first due to `search_path` temp resolution rules.

To target the real permanent table unambiguously:

```sql
SELECT *
FROM lifecycle_lab.metrics;
```

To target the session's temporary table explicitly:

```sql
SELECT *
FROM pg_temp.metrics;
```

**Lesson:** when a temp table shadows a permanent table, unqualified SQL can read or write **the wrong object**. In critical code, always schema-qualify permanent objects and name temp tables clearly.

### 13.1. Security note on `search_path` and SECURITY DEFINER functions

Name resolution requires special attention in functions running with elevated privileges (`SECURITY DEFINER`). Never write privileged functions referencing unqualified table names that a caller's temporary table could hijack.

Always lock down `search_path` safely on privileged routines and schema-qualify critical objects. This is a security requirement, not just a style preference.

## 14. Distinguishing Temporary Tables from Temporary Files

PostgreSQL also creates **temporary disk files** during query execution when intermediate operations exceed memory limits. Examples:

- `ORDER BY` sorting a huge dataset.
- `GROUP BY` or hash joins spilling past memory budgets.
- Certain materialization or intermediate node spills.

```text
SELECT ... ORDER BY ...
         |
         v
Sort node
         |
         +-- Fits in memory: processed in-memory
         |
         +-- Not enough: creates temporary disk files
                        |
                        +-- Serves query/iterator
                        +-- Not an SQL table to SELECT
                        +-- Cleaned up per execution lifecycle
```

**Temporary disk files are not temporary tables**:

| Property | Temporary table | Executor temporary file |
| --- | --- | --- |
| Created explicitly in SQL? | Yes, `CREATE TEMP TABLE` | Created automatically by executor |
| Has an SQL relation name? | Yes | Not a queryable SQL relation |
| Can be `SELECT`ed repeatedly? | Yes, within the session | No |
| Spans multiple statements? | Yes, per `ON COMMIT` and session | Scoped to execution/internal need |
| Can have explicit indexes? | Yes | Not indexed like relations |
| Primary purpose | Deliberate intermediate staging data | Internal query sort/hash spills |

### 14.1. `work_mem` and spills

`work_mem` governs how much memory **each eligible query operator** such as a sort or hash can use before spilling to disk, subject to hash multiplier rules. It is not a hard RAM cap for the entire session.

```sql
SHOW work_mem;
```

You can adjust it temporarily for **one transaction** in tests:

```sql
BEGIN;

SET LOCAL work_mem = '32MB';

SELECT order_id, amount
FROM lifecycle_lab.orders
ORDER BY amount DESC;

COMMIT;
```

Never raise `work_mem` server-wide carelessly: many concurrent queries, each running multiple sort/hash nodes, can exhaust RAM together.

### 14.2. Monitoring temporary files

PostgreSQL tracks cumulative temp-file stats in `pg_stat_database`:

```sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_data_written
FROM pg_stat_database
WHERE datname = current_database();
```

`temp_files` and `temp_bytes` count temporary executor files tracked in that database's stats interval. They do **not** equal "number of temporary tables created" or "size of session temp tables."

Enabling `log_temp_files` logs executor temp files exceeding a threshold; because logging affects disk usage, follow operational guidelines before enabling it.

## 15. Session State Differs from Shared Caches and Shared Data

Another area causing confusion is **server shared memory and caches**.

PostgreSQL uses **shared buffers**, OS page cache, WAL buffers, and internal structures shared across backends. These differ from session state:

- Cached pages from a permanent table benefit all backends reading that table.
- Session A's `SET statement_timeout` never affects Session B merely because both touch the same cached pages.
- Session A's prepared statement never becomes Session B's prepared statement just because both run identical SQL.

Whether a page sits in RAM **does not decide** if a table is permanent or temporary. Temporary tables can still spill to disk, and permanent tables are routinely served from RAM cache. **Where pages are cached** and **logical data lifecycle/durability** are orthogonal dimensions.

## 16. Other Session-State Components to Know

### 16.1. SQL `PREPARE` and `EXECUTE`

`PREPARE` creates a session-level prepared statement:

```sql
PREPARE find_order (bigint) AS
SELECT order_id, customer_name, amount
FROM lifecycle_lab.orders
WHERE order_id = $1;

EXECUTE find_order(1001);
```

Within the same session, reuse it:

```sql
EXECUTE find_order(1002);
```

To free it:

```sql
DEALLOCATE find_order;
```

SQL `PREPARE` statements belong to the creating session, not Session B. Running `EXECUTE find_order(1001)` in Session B fails unless B prepared it too.

**Never confuse SQL `PREPARE` with two-phase commit prepared transactions (`PREPARE TRANSACTION`).** They are completely unrelated features with different lifecycles and semantics.

### 16.2. Session-level advisory locks

PostgreSQL provides advisory locks for application-defined coordination.

In Session A:

```sql
SELECT pg_advisory_lock(9001);
```

This is a **session-level** lock; it is not released when a transaction commits or rolls back. Release it explicitly:

```sql
SELECT pg_advisory_unlock(9001);
```

or wait until the session ends.

By contrast:

```sql
BEGIN;

SELECT pg_advisory_xact_lock(9002);

-- Perform coordinated work.
COMMIT;
```

`pg_advisory_xact_lock` is **transaction-scoped** and releases automatically when the transaction ends.

| Lock kind | Lifecycle |
| --- | --- |
| `pg_advisory_lock` | Session, until unlocked or session closes |
| `pg_advisory_xact_lock` | Transaction, until commit/rollback |
| Row locks from `SELECT ... FOR UPDATE` | Transaction |
| Internal DDL/DML locks | Appropriate mechanism and transaction boundaries |

Session-level advisory locks cause severe bugs if an app returns a connection to a pool **forgetting to unlock**: the next request borrowing that connection silently inherits ownership of that lock.

### 16.3. `LISTEN`/`NOTIFY`

A session can subscribe to notifications on a channel:

```sql
LISTEN order_events;
```

Another session can emit a notification:

```sql
NOTIFY order_events, 'order-1001-updated';
```

`LISTEN` registrations are session state; disconnecting drops the subscription. `NOTIFY` payloads also never replace **durable database rows** or message queues with retention and replay.

When events must not be missed while listeners are offline, persist events reliably in a table or proper message broker rather than relying solely on `NOTIFY`.

### 16.4. Cursors

A query cursor can be opened inside a transaction to fetch rows incrementally:

```sql
BEGIN;

DECLARE order_cursor CURSOR FOR
SELECT order_id, amount
FROM lifecycle_lab.orders
ORDER BY order_id;

FETCH 2 FROM order_cursor;

CLOSE order_cursor;

COMMIT;
```

Ordinary cursors are bound to the transaction. PostgreSQL also supports `WITH HOLD` cursors surviving commit under specific rules, yet they are still session-scoped—never a permanent table, and never usable from another session.

## 17. Connection Pooling: The Most Common Source of Session Confusion

With connection pools, a user request does not equal a fresh PostgreSQL session.

```text
Connection Pool
   +-------------+
   | Connection 1| -> Request A, then Request C
   | Connection 2| -> Request B, then Request D
   +-------------+
```

If A runs:

```sql
SET search_path TO tenant_a, public;
```

and returns the connection to the pool without resetting, Request C can run with `tenant_a` in `search_path` even while serving a different tenant. This is **session state leakage**, risking cross-tenant data bugs if authorization and routing are weak.

One way to limit leakage when altering settings for **one transaction**:

```sql
BEGIN;

SET LOCAL search_path TO tenant_a, public;

-- Business SQL for tenant_a inside the transaction.
-- Example assumes the schema and table actually exist.
SELECT COUNT(*) FROM orders;

COMMIT;
```

On commit, `SET LOCAL` ends. Still, applications must enforce **strict transaction boundaries, connection hygiene, and tenant/role authorization**, rather than relying on `search_path` alone.

### 17.1. Session pooling vs. transaction pooling

Proxies/poolers like PgBouncer offer distinct pooling modes:

| Pooling mode | General meaning |
| --- | --- |
| Session pooling | One server connection stays dedicated to a client session for its whole lifetime |
| Transaction pooling | Server connections can return to the pool and serve other clients **after each transaction** |

Under transaction pooling, never assume session `SET`, cross-transaction temp tables, SQL `PREPARE`, session-level advisory locks, or `LISTEN` stay pinned to the client across transactions. While modern poolers may track certain features (like prepared statements), actual support varies by version and config. Design strictly to the **documented pooling contract**, not luck.

### 17.2. Resetting a session

PostgreSQL provides:

```sql
DISCARD ALL;
```

This resets resettable session state—GUCs, prepared statements, temp objects, and more. `DISCARD ALL` **cannot run inside a transaction block**, and does not excuse sloppy pool lifecycle management.

Targeted reset commands also exist:

```sql
RESET ALL;
DEALLOCATE ALL;
DISCARD TEMP;
UNLISTEN *;
```

They are not identical:

- `RESET ALL` resets resettable configuration parameters.
- `DEALLOCATE ALL` frees SQL prepared statements in the session.
- `DISCARD TEMP` drops temporary tables/objects in the session.
- `UNLISTEN *` cancels `LISTEN` subscriptions in the session.

**Never run `DISCARD ALL` blindly on every single request.** It adds overhead and transaction constraints; follow your pool/driver's documented reset policies and measure real needs.

## 18. Choosing TEMP Tables vs. Permanent Tables in a Workflow

### 18.1. Output must survive after the job exits

Suppose a sales reporting job generates results that users will open tomorrow. Use a **permanent table** keyed by report/job ID:

```sql
CREATE TABLE lifecycle_lab.report_results (
    report_id bigint NOT NULL,
    order_id bigint NOT NULL,
    amount numeric(12,2) NOT NULL,
    PRIMARY KEY (report_id, order_id)
);
```

Once the job inserts and commits, authorized sessions can read the results anytime afterward.

**Never use a temporary table** for final outputs meant to be read across sessions.

### 18.2. Intermediate job workspace within one session

Suppose one job selects a subset of IDs, indexes them temporarily, and joins multiple times before finishing:

```sql
CREATE TEMP TABLE stage_order_ids
ON COMMIT PRESERVE ROWS
AS
SELECT order_id
FROM lifecycle_lab.orders
WHERE amount >= 200000;

CREATE INDEX ON stage_order_ids (order_id);

ANALYZE stage_order_ids;

SELECT o.order_id, o.amount
FROM lifecycle_lab.orders AS o
JOIN stage_order_ids AS s
    ON s.order_id = o.order_id
ORDER BY o.order_id;
```

A temporary table shines when intermediate results are **reused across multiple statements in one session**.

PostgreSQL's autovacuum **cannot vacuum or analyze another session's temporary tables** in normal operation; therefore, for large temp tables, running `ANALYZE` manually right after loading helps the planner pick good plans.

### 18.3. Reproducible data shared across multiple jobs

If staging data must be read by multiple sessions and can be reloaded after crashes, `UNLOGGED` may be worth evaluating—provided crash truncation, replication limits, and reload procedures are accounted for.

### 18.4. Intermediate logic inside a single query

A **CTE** is usually simpler than creating a temporary table:

```sql
WITH high_value AS (
    SELECT order_id, amount
    FROM lifecycle_lab.orders
    WHERE amount >= 200000
)
SELECT COUNT(*) AS order_count,
       COALESCE(SUM(amount), 0) AS total_amount
FROM high_value;
```

A CTE does not create a standalone table queryable across later statements. PostgreSQL may inline or materialize CTEs depending on query structure, version, and hints; never assume a CTE always writes a physical temporary table.

### 18.5. Decision table

| Requirement | Typically suitable choice |
| --- | --- |
| Orders/payments needing long-term durability | Permanent table |
| Finished reports opened from other sessions | Permanent table |
| Temp ID set reused across queries in one backend | TEMP table |
| Each transaction needs an empty temp table | TEMP `ON COMMIT DELETE ROWS` |
| Table needed for a single transaction only | TEMP `ON COMMIT DROP` |
| Reloadable data shared across sessions | Consider UNLOGGED |
| Timeout tuned for one transaction only | `SET LOCAL` |
| Settings for a managed connection | `SET` with proper pool reset |
| Intermediate subquery within one statement | Subquery or CTE |

## 19. Two-Session psql Lab: Observing Lifecycles Firsthand

Run this practice in a **dedicated lab database**. Never create/drop lab tables in production.

### 19.1. Preparing permanent data

In Connection A or a lab admin session:

```sql
CREATE SCHEMA IF NOT EXISTS lifecycle_lab;

CREATE TABLE IF NOT EXISTS lifecycle_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO lifecycle_lab.orders
    (order_id, customer_name, amount)
VALUES (1101, 'Customer A', 125000.00)
ON CONFLICT (order_id)
DO UPDATE SET
    customer_name = EXCLUDED.customer_name,
    amount = EXCLUDED.amount;
```

In a fresh lab, this creates the schema, table, and row. Because `IF NOT EXISTS` does not verify existing schemas match, use a clean isolated lab schema.

### 19.2. Session A: creating session state and a temporary table

Open Terminal A:

```bash
psql -h localhost -U lab_user -d lab_db
```

In Session A:

```sql
SELECT pg_backend_pid() AS session_a_pid;

SET statement_timeout = '5s';

CREATE TEMP TABLE temp_notes (
    note_id integer PRIMARY KEY,
    note text NOT NULL
) ON COMMIT PRESERVE ROWS;

INSERT INTO temp_notes (note_id, note)
VALUES (1, 'Only session A');

SELECT * FROM temp_notes;

SELECT * FROM lifecycle_lab.orders
WHERE order_id = 1101;
```

In A, both the temp table and `statement_timeout` are active.

### 19.3. Session B: verifying state is not shared

Open **Terminal B** with a new `psql` connection:

```bash
psql -h localhost -U lab_user -d lab_db
```

In Session B:

```sql
SELECT pg_backend_pid() AS session_b_pid;

SHOW statement_timeout;

SELECT * FROM lifecycle_lab.orders
WHERE order_id = 1101;
```

Session B reads the committed row in the permanent table (if privileged) and sees B's own `statement_timeout`, not what A set.

Continue:

```sql
SELECT * FROM temp_notes;
```

Expect an error that `temp_notes` does not exist unless B created its own table of that name. You do not even need to know A's temp schema name; A's temp data is never shared with B.

### 19.4. Session A: verifying COMMIT preserves default temp tables

In A:

```sql
BEGIN;

INSERT INTO temp_notes (note_id, note)
VALUES (2, 'Committed within A');

COMMIT;

SELECT * FROM temp_notes ORDER BY note_id;
```

A sees both rows 1 and 2 thanks to `ON COMMIT PRESERVE ROWS`.

In B, `SELECT * FROM temp_notes` still cannot access A's temp table.

### 19.5. Closing Session A and reconnecting

In A:

```text
\q
```

Open a new connection and run:

```sql
SELECT * FROM lifecycle_lab.orders
WHERE order_id = 1101;

SELECT * FROM temp_notes;
```

The permanent table still holds the committed row. `temp_notes` is gone in the new session, and `statement_timeout` reverts to the new session's default rather than inheriting A's `SET`.

**Takeaway:** permanent data, session settings, and TEMP tables obey three distinct lifecycles despite all using SQL syntax.

## 20. Common Failure Scenarios When Lifecycles Are Confused

### 20.1. "I ran COMMIT, yet my temporary table is still there"

That is expected when using `ON COMMIT PRESERVE ROWS` (the default). To clear rows on every commit, use `ON COMMIT DELETE ROWS`; to drop the table on commit, use `ON COMMIT DROP` inside an explicit transaction.

### 20.2. "I closed the connection and lost my report table"

If the report was built with `CREATE TEMP TABLE`, its data was session-scoped, so losing it on disconnect is by design. Store shared results in a permanent table.

### 20.3. "I created a temp table, and the next HTTP request couldn't find it"

The next request likely hit **another pooled connection** or another backend under transaction pooling. Temporary tables are never cross-request storage.

### 20.4. "I used UNLOGGED and lost all data after a crash"

`UNLOGGED` skips WAL for table data, so PostgreSQL truncates unlogged tables after crashes/unclean shutdowns. When durability is required, use permanent tables with proper backups/replication.

### 20.5. "I ran SET in request A, and request B got weird settings"

Both requests almost certainly reused the same pooled backend without resetting session state. Enforce pool reset policies or use `SET LOCAL` inside transactions where appropriate.

### 20.6. "I ran ROLLBACK, yet the temp table didn't disappear"

If the temporary table was created **before** the rolled-back transaction, rollback only undoes work inside that transaction. The table itself survives until session close or `DROP TABLE`/`DISCARD TEMP`.

### 20.7. "I see `temp_files` rising even though nobody ran `CREATE TEMP TABLE`"

The executor is likely spilling sorts/hashes to disk. Executor temporary disk files and SQL temporary tables are completely separate mechanisms. Inspect `EXPLAIN (ANALYZE, BUFFERS)` or stats where authorized.

### 20.8. "A temp table with the same name as a real table caused weird query results"

An unqualified temp table shadows a permanent table of the same name. Use explicit names, `pg_temp.table_name` for temp tables, or `real_schema.table_name` for permanent tables.

### 20.9. "I ran PREPARE in Session A, and Session B couldn't EXECUTE it"

SQL prepared statements belong to Session A. Session B must prepare its own, or use driver/pooler-level statement caching. SQL `PREPARE` does not register a database-wide named query.

### 20.10. "I used SET LOCAL, and after COMMIT the timeout disappeared"

That is literally what `SET LOCAL` is designed for: transaction-only scope. For session-wide effect, use `SET` with proper pool reset, or configure defaults administratively.

## 21. Practice Exercises

### Exercise 1: Classify objects

Given these statements:

```sql
CREATE TABLE public.a (id integer PRIMARY KEY);
CREATE UNLOGGED TABLE public.b (id integer PRIMARY KEY);
CREATE TEMP TABLE c (id integer PRIMARY KEY);
SET statement_timeout = '3s';
BEGIN;
SET LOCAL work_mem = '16MB';
COMMIT;
```

Classify each item:

| Component | Lifecycle category |
| --- | --- |
| `public.a` | Permanent table; data protected by WAL per durability config |
| `public.b` | UNLOGGED; shared across sessions, yet data not WAL-protected across crashes |
| `c` | TEMP table; scoped to session and dropped when session ends |
| `statement_timeout` | Session setting; effective until reset or session close |
| `work_mem` from `SET LOCAL` | Transaction-only; expires on commit |

### Exercise 2: What happens with `ON COMMIT DELETE ROWS`?

```sql
CREATE TEMP TABLE t (
    id integer
) ON COMMIT DELETE ROWS;

BEGIN;
INSERT INTO t VALUES (1), (2);
COMMIT;

SELECT COUNT(*) FROM t;
```

**Answer:** table `t` still exists with zero rows; `COUNT(*)` returns `0`.

### Exercise 3: What happens with `ON COMMIT DROP`?

```sql
BEGIN;

CREATE TEMP TABLE t_drop (
    id integer
) ON COMMIT DROP;

INSERT INTO t_drop VALUES (10);

COMMIT;
```

**Answer:** `t_drop` is dropped when the transaction commits. A subsequent `SELECT` in the same session fails with relation does not exist.

### Exercise 4: Do Session A and B share `SET`?

A:

```sql
SET statement_timeout = '7s';
```

B:

```sql
SHOW statement_timeout;
```

**Answer:** B does not automatically see A's 7-second timeout; B reflects its own defaults and session settings.

### Exercise 5: Can temporary table data be rolled back?

```sql
CREATE TEMP TABLE t_tx (id integer);

INSERT INTO t_tx VALUES (1);

BEGIN;
INSERT INTO t_tx VALUES (2);
ROLLBACK;

SELECT * FROM t_tx ORDER BY id;
```

**Answer:** only row `1` remains if autocommit committed the first insert. Temporary tables obey transaction rollback for DML.

### Exercise 6: Choosing a staging table read by multiple workers

A staging dataset must be read by multiple sessions and can be completely reloaded from object storage after a crash. What should you consider?

**Answer:** either use a permanent table for simple durability, or evaluate `UNLOGGED` if crash truncation and replication limits are acceptable. A `TEMP` table is unsuitable because it is locked to one session.

### Exercise 7: Report results needed tomorrow

Is `CREATE TEMP TABLE` suitable?

**Answer:** no, if the report must be read from other sessions after the generating job disconnects. Store it in a permanent table or durable storage.

### Exercise 8: Temp files vs. temp tables

`pg_stat_database.temp_bytes` spikes during a huge `ORDER BY` query, yet nobody ran `CREATE TEMP TABLE`.

**Answer:** the executor spilled sort/hash data to temporary disk files. Those are internal execution files, not SQL temporary tables.

### Exercise 9: Does `PREPARE` survive a server restart?

```sql
PREPARE find_order(bigint) AS
SELECT * FROM lifecycle_lab.orders WHERE order_id = $1;
```

**Answer:** no. SQL `PREPARE` statements live in session state; restarting terminates connections and discards all session state.

### Exercise 10: Why is `SET LOCAL` usually safer than `SET` with connection pools?

**Answer:** `SET LOCAL` expires automatically when the transaction ends, preventing configuration leakage to subsequent requests reusing the pooled connection. Applications must still enforce clean transactions and never rely on accidental leftover session state.

## 22. Summary

PostgreSQL manages **persistent data**, **per-connection session state**, and **temporary objects/workspace** side by side. Keeping these three scopes straight makes applications and operations far safer.

Most important principles:

1. **Permanent tables** retain committed data across sessions and normal restarts, backed by WAL and durability settings.
2. **Commit does not close a session.** Transactions have shorter lifecycles than sessions; `ROLLBACK` undoes transactional changes without necessarily dropping previously committed objects.
3. **Session state** includes `SET` variables, active role, prepared statements, advisory locks, and listeners; pooled connections can carry state across requests if not reset.
4. **`SET LOCAL`** scopes settings cleanly to one transaction; `SET` persists across the session until reset.
5. **TEMP tables** are private SQL tables bound to a session. They default to `ON COMMIT PRESERVE ROWS`, with `DELETE ROWS` and `DROP` offering shorter retention.
6. **UNLOGGED tables are not TEMP tables.** They are shared across sessions and survive clean restarts, yet truncate after crashes/unclean shutdowns.
7. **Executor temporary files** for sorts/hashes differ completely from SQL temporary tables.
8. **Never assume every HTTP request gets a fresh session.** Connection pools and transaction pooling demand explicit state-reset contracts.
9. **Pick the right storage:** shared/durable outputs belong in permanent tables; single-session scratch work fits TEMP tables; reloadable shared staging may fit UNLOGGED.
10. **Always ask four questions:** how long it lives, who sees it, how transactions affect it, and whether it survives a crash.

Clearly separating **database persistence**, **session scope**, and **temporary processing** helps you avoid classic operational bugs: lost data from wrong table types, missing tables across pooled connections, leaked settings between requests, and misconceptions about commit safety.
