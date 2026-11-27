# Session State, Temporary Tables, and Prepared Statements Under Pooling in PostgreSQL

An API handling two consecutive requests can look like two completely independent tasks:

```text
Request A: view orders for tenant 10
Request B: view orders for tenant 20
```

Yet if both reuse the same **physical PostgreSQL connection** from a pool, **session-scoped** settings and objects created by Request A may still exist when Request B starts. For instance, A runs `SET search_path`, creates temporary table `temp_report`, calls `PREPARE`, or acquires a session-level advisory lock. Simply calling `Connection.close()` on a pooled connection **does not automatically close the real PostgreSQL session**; normally it just returns the connection to the pool.

This is the intersection of **application connection management**, **session state**, **transaction lifecycles**, **temporary tables**, and **prepared statements**. Mistakes here can leak data across requests, trigger random errors under PgBouncer transaction pooling, hold locks longer than expected, or yield inconsistent results.

```text
                 APPLICATION
     Request A              Request B
         |                      |
         v                      v
     borrow conn           borrow conn
         |                      |
         +----------+-----------+
                    |
                    v
          APPLICATION CONNECTION POOL
          (HikariCP, container pool, ...)
                    |
           PostgreSQL connections
                    |
                optional
                    v
                PgBouncer
              /     |      \
         session transaction statement
          pool      pool       pool
              \     |      /
                    v
        POSTGRESQL BACKEND SESSIONS
           PID 5411      PID 5412
           TEMP          PREPARE
           SET           LISTEN
           LOCKS         PORTALS
```

This lesson belongs to the **Application Connections** chapter of the *Database Engine Relational PostgreSQL* module. The focus is not merely "should we use a pool?", but rather **which objects belong to a session, which belong to a transaction, who is responsible for cleanup, and which pooling modes support each feature**.

After finishing this lesson, you will be able to:

- Distinguish **logical connection handle**, **client connection**, **server connection**, **backend session**, and **transaction**.
- Explain why `SET`, `SET LOCAL`, `RESET`, and `DISCARD ALL` have different effects.
- Choose the right lifecycle for temporary tables using `ON COMMIT PRESERVE ROWS`, `DELETE ROWS`, or `DROP`.
- Understand SQL `PREPARE`/`EXECUTE`/`DEALLOCATE`, JDBC `PreparedStatement`, protocol-level named prepared statements, and `pg_prepared_statements`.
- Identify differences among application pooling and PgBouncer **session/transaction/statement pooling**.
- Design safely around `search_path`, tenant context, RLS, time zones, session locks, `LISTEN`, and cursors.
- Avoid bugs when retrying after a failed statement, when pools reuse connections, and when schemas change.
- Write a JDBC transaction with context using `SET LOCAL`/`set_config(..., true)`.
- Diagnose "prepared statement already exists", "does not exist", vanishing temporary tables, and aborted transactions.
- Build a configuration checklist, integration tests, and runbooks when deploying with PgBouncer.

> **Safety:** Examples create schema `pool_state_lab` and temporary objects in a PostgreSQL test database. Never run `DISCARD ALL`, `RESET ROLE`, `search_path`/RLS changes, or PgBouncer edits in production without a deployment plan. Some examples intentionally trigger errors and are noted to run in isolation. Pool config snippets are **illustrative**; verify exact versions and drivers before rollout.

---

## 1. Distinguishing Five Easily Confused Concepts

### 1.1. Application Connection Handle

In JDBC:

```java
try (Connection connection = dataSource.getConnection()) {
    // Execute SQL.
}
```

The `connection` variable is a Java object used by request code. If `dataSource` is a pool, `connection.close()` normally **returns the handle to the pool** rather than destroying the underlying socket or PostgreSQL backend.

### 1.2. Physical Connection in the Application Pool

HikariCP or an equivalent JDBC pool manages a set of physical connections to the database endpoint. One physical connection can be borrowed by requests **sequentially**:

```text
10:00:00 Request A borrows connection #3
10:00:01 Request A returns connection #3
10:00:02 Request B borrows connection #3
```

If #3 stays connected directly to the same PostgreSQL backend session, session-level objects persist across both leases unless the driver, pool, or app resets the relevant state.

### 1.3. PostgreSQL Backend Session

A direct connection to PostgreSQL corresponds to one server backend process/session. You can observe it with:

```sql
SELECT
    pg_backend_pid() AS backend_pid,
    current_database() AS database_name,
    current_user AS effective_role,
    session_user AS login_role;
```

`pg_backend_pid()` identifies the backend executing the statement. However, one **logical client connection through PgBouncer transaction pooling** may execute different transactions on different backends.

### 1.4. Transaction

`BEGIN ... COMMIT` or `ROLLBACK` defines an atomic unit of data change. Multiple SQL statements in the same transaction use one backend held by PgBouncer transaction pooling for that transaction's duration.

A transaction is not a session:

- One session can run many transactions.
- One session can retain temporary tables, SQL prepared statements, or session settings across commits.
- `SET LOCAL` and transaction-scoped advisory locks apply only inside the transaction.

### 1.5. Pool Mode

Pool mode determines **when** a PostgreSQL server connection returns to an intermediary pool:

- **Session pooling:** client holds one server connection for as long as the client session stays alive.
- **Transaction pooling:** server connection is held only from transaction start to transaction end.
- **Statement pooling:** server connection returns after each statement; multi-statement transactions are unsupported in this mode's model.

An application pool and PgBouncer can coexist:

```text
Application request
      |
      v
JDBC Connection from HikariCP
      |
      v
TCP connection to PgBouncer
      |
      v
PostgreSQL backend may change after COMMIT
```

Therefore, "I kept the same JDBC `Connection` object" **does not mean** "I kept the same PostgreSQL backend PID" when transaction pooling sits underneath.

---

## 2. Lifecycle Scope Table: What Lives How Long?

| Object / State | Normal Scope | Survives `COMMIT`? | Notes |
|---|---|---|---|
| `SET parameter = ...` | Session | Yes if transaction containing `SET` commits | Can leak into the next lease |
| `SET LOCAL parameter = ...` | Transaction | No | Must be set inside a real transaction |
| `SET ROLE` | Session | Yes per `SET` semantics | Requires reset/privilege discipline |
| `SET LOCAL ROLE` | Transaction | No | Usable when role switching is permitted |
| `CREATE TEMP TABLE ... ON COMMIT PRESERVE ROWS` | Session | Yes | PostgreSQL default is `PRESERVE ROWS` |
| `CREATE TEMP TABLE ... ON COMMIT DELETE ROWS` | Session; data per transaction | Table stays, rows cleared at `COMMIT` | Does not solve transaction pooling |
| `CREATE TEMP TABLE ... ON COMMIT DROP` | Transaction for the created table | No | Suitable for single-transaction batches |
| SQL `PREPARE name AS ...` | Session | Yes | Exists only on the backend where prepared |
| Protocol-level named prepared statement | Backend, unless pooler supports remapping | Yes on same backend | PgBouncer version/config matters |
| `pg_advisory_lock(...)` | Session | Yes | Must unlock or end session |
| `pg_advisory_xact_lock(...)` | Transaction | No | Automatically released at transaction end |
| `LISTEN channel` | Session | Yes | Unsuitable when backends switch per transaction |
| `NOTIFY channel` | Statement/transaction | Dispatched when transaction commits | Does not require client to `LISTEN` |
| Regular cursor without `WITH HOLD` | Transaction | No | Cannot be used after `COMMIT` |
| Cursor `WITH HOLD` | Session | Yes | Unsuitable for transaction pooling |
| Normal row locks | Transaction | No | Released on commit/rollback |
| Custom session GUC `app.tenant_id` | Session if `SET` | Yes | Not authorization on its own |

**Rule to remember:** Pools **do not automatically convert** session resources into transaction resources. Any feature relying on a session must be evaluated against the pooling mode in use.

---

## 3. Preparing the Test Environment

### 3.1. Verify Environment

```sql
SELECT
    current_database(),
    current_user,
    pg_backend_pid(),
    current_setting('server_version') AS version;
```

When using PgBouncer, separate **SQL sent through PgBouncer to PostgreSQL** from administrative commands sent to the **PgBouncer admin console**. Never run PgBouncer commands like `SHOW POOLS` as regular SQL against your business database.

### 3.2. Create the Test Schema

```sql
CREATE SCHEMA pool_state_lab;

CREATE TABLE pool_state_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    status TEXT NOT NULL CHECK (status IN ('draft', 'paid'))
);

INSERT INTO pool_state_lab.orders
    (tenant_id, amount, status)
VALUES
    (10, 100.00, 'paid'),
    (10,  50.00, 'draft'),
    (20, 200.00, 'paid');
```

Run only in a test database that does not already have schema `pool_state_lab`. If it already exists, use a fresh test database; never wipe someone else's schema with `DROP ... CASCADE`.

### 3.3. Verify the Data

```sql
SELECT order_id, tenant_id, amount, status
FROM pool_state_lab.orders
ORDER BY order_id;
```

This dataset illustrates tenant context. The table itself has no RLS yet; filtering by `tenant_id` in the lab is SQL filtering, not production multi-tenant security.

### 3.4. Isolate the Experiments

Examples for `SET`, `PREPARE`, and `CREATE TEMP TABLE` must run **on the same backend session** when testing session scope. If your tool swaps backends via transaction pooling, that instability itself demonstrates the point of the lesson.

---

## 4. Identifying the Backend Session With `pg_backend_pid()`

### 4.1. Open Two `psql` Terminals

In **Terminal A**:

```sql
SELECT pg_backend_pid() AS pid_a;
```

In **Terminal B**:

```sql
SELECT pg_backend_pid() AS pid_b;
```

Two concurrent direct connections to PostgreSQL normally show different PIDs.

### 4.2. Connecting Through an Application Pool

In a direct JDBC pool, the same physical connection keeps the same PID across checkouts. With PgBouncer transaction pooling, the **same client connection** may get a different backend on the next transaction.

### 4.3. PID Is Not an API Contract

Never store `pg_backend_pid()` as a user or transaction identifier:

- Backend PIDs change on reconnects.
- Poolers can switch backends.
- PIDs are not business data.
- OS PIDs are recycled over the server's lifetime.

Use PIDs for diagnostics, not data consistency.

### 4.4. Unchanged Output Does Not Prove Session Pinning

Under transaction pooling, calling `pg_backend_pid()` twice can still return the same PID by chance if the pooler picks the same backend again. Prove compatibility via **pool mode and semantics**, not a lucky matching-PID check.

---

## 5. What Is Session State?

A PostgreSQL session holds far more state than committed table rows:

```text
PostgreSQL backend session
├── Current GUC settings (search_path, TimeZone, statement_timeout...)
├── Effective/session role
├── Temporary tables and their data
├── SQL prepared statements / protocol-level statements
├── Open cursors and portals
├── Session-level advisory locks
├── LISTEN subscriptions
├── Cached plans / sequence caches
└── Transaction state (idle, in transaction, aborted...)
```

When a request returns a logical connection to the pool, **session-scoped items can remain on the physical backend**. No simple `ROLLBACK` erases every kind of state left over from prior transactions.

---

## 6. `SET` and `SET LOCAL`: Differences at Transaction Boundaries

### 6.1. Plain `SET` Is Session-Scoped

```sql
SHOW TimeZone;

SET TimeZone = 'Asia/Ho_Chi_Minh';

SHOW TimeZone;
```

Once `SET` succeeds, the session value persists across subsequent commits until reset, overwritten, or the session ends.

### 6.2. `SET` Inside a Transaction Followed by `COMMIT`

```sql
BEGIN;

SET TimeZone = 'UTC';

COMMIT;

SHOW TimeZone;
```

If the transaction containing `SET` commits, the session-level setting `TimeZone = 'UTC'` remains active.

### 6.3. `SET` Inside a Transaction Followed by `ROLLBACK`

```sql
BEGIN;

SET TimeZone = 'Asia/Ho_Chi_Minh';

ROLLBACK;
```

Because the transaction rolled back, the `SET` change is undone per `SET` semantics.

### 6.4. `SET LOCAL` Applies Only Within the Transaction

```sql
BEGIN;

SET LOCAL TimeZone = 'UTC';

SHOW TimeZone;

COMMIT;

SHOW TimeZone;
```

After `COMMIT`, the previous session-level or default value takes effect again.

### 6.5. `SET LOCAL` Outside a Transaction

```sql
-- Do not use this to configure a single autocommit request:
-- SET LOCAL TimeZone = 'UTC';
```

Outside an actual transaction block, `SET LOCAL` emits a warning and does not persist for the next `SELECT` as a developer might hope.

### 6.6. `SET` Followed by `SET LOCAL` in the Same Transaction

```sql
BEGIN;

SET TimeZone = 'Asia/Ho_Chi_Minh';
SET LOCAL TimeZone = 'UTC';

SHOW TimeZone; -- UTC inside transaction

COMMIT;

SHOW TimeZone; -- Asia/Ho_Chi_Minh because SET committed
```

`SET LOCAL` temporarily shadows the session's `SET` for that transaction; once the transaction ends, the session-level `SET` resumes.

### 6.7. `SET LOCAL` and Savepoints

If you `ROLLBACK TO SAVEPOINT` created **before** `SET LOCAL`, the local change can also be rolled back.

Never assume a GUC remains set after a partial rollback without verifying.

### 6.8. Comparison

| Statement | Scope | After `COMMIT` | After `ROLLBACK` |
|---|---|---|---|
| `SET x = value` outside tx | Session | Persists | No rollback applies |
| `SET x = value` inside tx | Session if tx commits | Persists | Reverts to pre-tx value |
| `SET LOCAL x = value` inside tx | Transaction | Restores pre-LOCAL value | Restores pre-LOCAL value |
| `RESET x` | Corresponding session setting | Persists if committed | Follows tx rollback |
| `RESET ALL` | Many GUC settings | Does not drop all session objects | Not equivalent to `DISCARD ALL` |

---

## 7. How Can One Request Leak Session State?

### 7.1. Scenario

```text
Request A (tenant 10)
  SET app.tenant_id = '10';
  SELECT ...
  return connection to pool

Request B (tenant 20)
  SELECT current_setting('app.tenant_id');
  -> may still return '10'
```

This happens whenever physical sessions are reused and the pool does not reset that custom GUC.

### 7.2. Custom GUCs

PostgreSQL lets you define dotted custom setting names such as:

```sql
SET app.tenant_id = '10';

SELECT current_setting('app.tenant_id') AS tenant_context;
```

That is merely a session configuration variable—it **does not prove the user is authorized to access tenant 10**.

### 7.3. Session-Only Experiment

Run on a single direct PostgreSQL connection:

```sql
SET app.tenant_id = '10';

SELECT
    pg_backend_pid(),
    current_setting('app.tenant_id', true) AS tenant_context;

COMMIT; -- if no transaction is open, this only warns.

SELECT current_setting('app.tenant_id', true);
```

The session-level `SET` value stays alive. Never mistake `COMMIT` for a command that resets all GUCs.

### 7.4. Right Pattern for Request-Scoped State

```sql
BEGIN;

SET LOCAL app.tenant_id = '10';

SELECT
    order_id, amount, status
FROM pool_state_lab.orders
WHERE tenant_id = current_setting('app.tenant_id')::integer;

COMMIT;
```

When the transaction ends, the `app.tenant_id` set via `SET LOCAL` does not survive as a session-level assignment.

### 7.5. Once `SET LOCAL` Ends

For a custom GUC never previously set in the session, `current_setting(..., true)` may return NULL or an empty string depending on placeholder lifecycle once reset. Never write an RLS policy assuming "unset" always casts cleanly to an integer.

A policy must handle **missing, empty, invalid type, and untrusted state** safely.

---

## 8. Designing Safe Tenant Context: `SET LOCAL` Is Not Authorization

### 8.1. When Are GUCs Useful?

A transaction can use a custom GUC to pass context into SQL functions or policies:

```sql
BEGIN;

SET LOCAL app.tenant_id = '10';

SELECT current_setting('app.tenant_id', true) AS tenant_context;

ROLLBACK;
```

The benefit is sharing context across statements inside the transaction without threading `tenant_id` through every internal function signature.

### 8.2. Caller-Set GUCs Are Not Trusted Identity

If an ordinary SQL role can freely run:

```sql
SET LOCAL app.tenant_id = '20';
```

then an RLS policy reading `current_setting('app.tenant_id')` **is not enough** to prove the caller truly belongs to tenant 20.

Your security contract must specify who can connect, who is permitted to set context, and what binds context to an authenticated principal.

### 8.3. Passing Context to RLS Is a Security Decision

Practical patterns:

- Separate database roles per tenant/permission tier, with RLS tied to database identity.
- An API tier authenticates the request, passes tenant context inside the transaction, and restricts the runtime role via privileges/interfaces from altering context arbitrarily.
- A privileged procedure validates caller/tenant against a trusted source before performing controlled work.

Writing `CREATE POLICY` arbitrarily while letting callers freely run `SET app.tenant_id` is insufficient.

### 8.4. Fail Closed When Context Is Missing

If a policy depends on context, missing or invalid context must **deny access**, never open it. For example, a controlled parsing helper should raise an error on missing context instead of falling back to `COALESCE(..., '0')`.

### 8.5. `SECURITY DEFINER` Introduces Extra Boundaries

A `SECURITY DEFINER` routine executes with the owner's privileges, which can affect RLS and tenant scoping. Never assume caller-side `SET LOCAL` guarantees a definer routine only sees one tenant.

Inspect owner privileges, RLS behavior, qualified names, `search_path`, and context validation inside such routines.

---

## 9. `application_name`, `TimeZone`, `search_path`, and Timeouts

### 9.1. GUCs Frequently Modified by Applications

```sql
SHOW application_name;
SHOW TimeZone;
SHOW search_path;
SHOW statement_timeout;
SHOW lock_timeout;
SHOW idle_in_transaction_session_timeout;
```

Sensitivity:

| GUC | Why It Matters |
|---|---|
| `search_path` | Unqualified table/function names may resolve to the wrong schema |
| `TimeZone` | Timestamp formatting and implicit casts can shift |
| `DateStyle` | Date text parsing/formatting can change |
| `statement_timeout` | Queries may cancel unexpectedly or run too long |
| `lock_timeout` | Lock wait tolerances change |
| `application_name` | Monitoring and attribution break if state leaks |
| `app.tenant_id` | Wrong tenant context becomes a security bug |
| `row_security` | Affects RLS enforcement depending on privileges and config |

### 9.2. What Should Be Used at Request Scope?

When a setting needs to change for one multi-statement unit of work:

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';
SET LOCAL TimeZone = 'UTC';

SELECT ...
FROM pool_state_lab.orders;

COMMIT;
```

This is a syntax example; do not run the placeholder `SELECT ...` verbatim.

### 9.3. Connections Can Use Startup Parameters

Parameters such as `application_name` or `TimeZone` can be passed when opening a PostgreSQL connection and tracked by proxies/poolers per version and configuration.

**Never assume every session `SET` is tracked and reapplied by PgBouncer transaction pooling on new backends.** For critical GUCs, check the parameter-tracking list for your exact PgBouncer and PostgreSQL versions and test.

### 9.4. `TimeZone` Is a Special Case Worth Understanding

PgBouncer tracks several core startup parameters including `TimeZone`, yet behavior of additional parameters and `track_extra_parameters` depends on PostgreSQL version and which variables PostgreSQL reports via protocol.

Do not generalize from "`TimeZone` is tracked" to "all custom GUCs are synced".

---

## 10. Temporary Tables Are Session-Local, Not Request-Local

### 10.1. `CREATE TEMP`

```sql
CREATE TEMP TABLE temp_selected_orders (
    order_id BIGINT PRIMARY KEY
);
```

A temporary table is bound to the **PostgreSQL session that created it**. Other sessions cannot read it directly like a normal application-schema table.

### 10.2. Default Is `ON COMMIT PRESERVE ROWS`

When `ON COMMIT` is omitted, PostgreSQL defaults to **`PRESERVE ROWS`**:

```sql
CREATE TEMP TABLE temp_selected_orders (
    order_id BIGINT PRIMARY KEY
) ON COMMIT PRESERVE ROWS;
```

After `COMMIT`, both the table and committed rows survive in that session until dropped or the session closes.

### 10.3. Why Do They Leak Easily in an Application Pool?

Suppose Request A creates/inserts a temporary table and returns the connection without dropping it:

```text
Backend P1
    Request A: temp_selected_orders holds [1,2]
    COMMIT
    return connection
    Request B: SELECT * FROM temp_selected_orders
               -> can still see [1,2]
```

This is **state leakage between two logical requests sharing one backend**, not data shared across two independent PostgreSQL sessions.

### 10.4. Temp Tables Also Affect Name Resolution

When a temp table shares a name with a permanent table, PostgreSQL searches the temp schema first for **relation names** unless `pg_temp` is explicitly positioned otherwise in `search_path`.

Never name a temp table identically to a business table while running unqualified SQL in privileged code.

---

## 11. Three `ON COMMIT` Modes

| Option | After `COMMIT` | When to Use |
|---|---|---|
| `ON COMMIT PRESERVE ROWS` | Table remains, rows remain | Intentionally working across multiple transactions **on the same session** |
| `ON COMMIT DELETE ROWS` | Table remains, rows deleted | Intentionally reusing the **same session**, fresh rows per transaction |
| `ON COMMIT DROP` | Table dropped | Creating, using, and discarding the table in **one transaction** |

### 11.1. `PRESERVE ROWS`

```sql
BEGIN;
CREATE TEMP TABLE demo_preserve (id integer)
ON COMMIT PRESERVE ROWS;
INSERT INTO demo_preserve VALUES (1);
COMMIT;

SELECT * FROM demo_preserve; -- 1 on the same session
```

Expected behavior, yet unsafe if the app assumes closing the logical handle wipes all request data.

### 11.2. `DELETE ROWS`

```sql
BEGIN;
CREATE TEMP TABLE demo_delete_rows (id integer)
ON COMMIT DELETE ROWS;
INSERT INTO demo_delete_rows VALUES (1);
SELECT * FROM demo_delete_rows; -- 1 inside transaction
COMMIT;

SELECT COUNT(*) FROM demo_delete_rows; -- 0 on the same session
```

The table still exists, so running `CREATE TEMP TABLE demo_delete_rows` again on the same backend fails with relation-already-exists.

### 11.3. `DROP`

```sql
BEGIN;
CREATE TEMP TABLE demo_drop (id integer)
ON COMMIT DROP;
INSERT INTO demo_drop VALUES (1);
SELECT * FROM demo_drop; -- 1
COMMIT;

-- After COMMIT, demo_drop has been dropped on this backend.
```

This is usually the right option for a workflow needing a staging table only within one transaction.

### 11.4. `ON COMMIT DROP` and Autocommit

If a JDBC connection is in autocommit mode:

```sql
CREATE TEMP TABLE auto_drop (id integer) ON COMMIT DROP;
```

commits immediately after the `CREATE`, dropping the table **before the next `INSERT`/`SELECT`**. Always create and use it inside one real transaction.

### 11.5. `ON COMMIT DELETE ROWS` Is Not `ON COMMIT DROP`

Two different behaviors:

```text
DELETE ROWS: session still holds the table object.
DROP: object is gone after commit.
```

Under transaction pooling, keeping the table object past `COMMIT` still ties code to a backend session; `DELETE ROWS` **does not** become transaction-pool-safe merely because its rows were cleared.

---

## 12. Temporary Tables Under Transaction Pooling

### 12.1. Working Within One Transaction

PgBouncer transaction pooling holds one server connection for the transaction's duration:

```sql
BEGIN;

CREATE TEMP TABLE tmp_ids (
    id bigint
) ON COMMIT DROP;

INSERT INTO tmp_ids VALUES (1), (2);

SELECT COUNT(*) FROM tmp_ids; -- 2

COMMIT;
```

Every statement inside the transaction runs on the same backend and sees the temp table; `ON COMMIT DROP` cleans up the object before the backend returns to the pool.

### 12.2. Never Span a Temp Table Across Two Transactions

```sql
BEGIN;

CREATE TEMP TABLE tmp_report (
    id bigint
) ON COMMIT PRESERVE ROWS;

INSERT INTO tmp_report VALUES (1);

COMMIT;

BEGIN;

-- Never rely on tmp_report existing on this next backend.
-- SELECT * FROM tmp_report;

ROLLBACK;
```

Under PgBouncer transaction pooling, the second transaction may get a different backend and miss `tmp_report`. If it happens to land on the same backend, leftover tables cause flaky behavior and cross-client state pollution.

### 12.3. Clear Recommendations

- **Use `ON COMMIT DROP`** whenever a temporary table is needed only inside one transaction.
- Avoid `PRESERVE ROWS` and `DELETE ROWS` under transaction pooling.
- Never use temp tables as "user session storage" across requests with a transaction pool.
- If state must persist across requests, use a permanent table with proper scoping, row ownership, TTL/cleanup, and permissions.

### 12.4. Statement Pooling Is Even Stricter

Statement pooling forbids standard multi-statement transactions like the example above. Thus `CREATE TEMP TABLE → INSERT → SELECT → COMMIT` is incompatible with statement pooling.

---

## 13. Session Pooling Still Needs Temp Table Cleanup

### 13.1. PgBouncer Session Pooling

One PgBouncer client connection holds the same PostgreSQL server connection until the client disconnects. Temp tables, SQL `PREPARE`, and session GUCs work cleanly **within that client connection's lifetime**.

### 13.2. Application Pools Extend Lifetimes

If HikariCP keeps 20 connections to a PgBouncer session pool open for hours, 20 PostgreSQL backends stay pinned for hours. Session pooling does not turn a physical JDBC connection into "one request = one fresh session".

### 13.3. Clean Up Before Returning the Connection

If a workflow uses a temp table:

```sql
DROP TABLE IF EXISTS pg_temp.temp_selected_orders;
```

Handle errors and transaction boundaries carefully. Using `ON COMMIT DROP` minimizes the risk of forgetting to drop in single-transaction workflows.

### 13.4. Avoid Unqualified `DROP TABLE`

If both a temporary table and a permanent table share a name, qualifying with `pg_temp.table_name` targets the temp table unambiguously. Never run unqualified `DROP TABLE orders` on a connection with a complex search path guessing which table it drops.

### 13.5. Do Not Automatically Run `DISCARD ALL` on Every Checkout

`DISCARD ALL` clears temp objects and prepared plans, yet also wipes other session caches and cannot run inside a transaction block. Running it on a JDBC connection where the driver caches server-prepared statement names can desync the cache unless the driver expects or handles that reset.

Any reset strategy must align with **pool + driver + PgBouncer**, not just tack on a "just in case" SQL command.

---

## 14. Not Every Temporary Table Is Necessary

### 14.1. Replace Temporary Tables With CTEs

When intermediate data is needed only within a single SQL statement:

```sql
WITH selected AS (
    SELECT order_id, amount
    FROM pool_state_lab.orders
    WHERE tenant_id = 10
      AND status = 'paid'
)
SELECT COUNT(*) AS paid_count, SUM(amount) AS paid_total
FROM selected;
```

A CTE is part of the query; it creates no session-scoped temporary table.

### 14.2. Use `VALUES` / `unnest` / Array Parameters

To pass a short list of IDs:

```sql
SELECT o.order_id, o.amount
FROM pool_state_lab.orders AS o
JOIN (VALUES (1::bigint), (3::bigint)) AS ids(order_id)
  ON ids.order_id = o.order_id;
```

In application code, use an array parameter and `unnest($1::bigint[])` with a supporting driver instead of creating a temp table per request.

### 14.3. When Temp Tables Still Shine

Temporary tables make sense when:

- One transaction joins large intermediate datasets across multiple steps.
- Indexes or statistics on temporary staging data are needed.
- Avoiding shipping a large dataset back and forth through the application.
- Cleanup is strictly aligned with transaction or session scope.

Do not "ban all temp tables"; match their lifetime to your pooling mode.

---

## 15. SQL `PREPARE`: Prepared Statements Are Session Objects

### 15.1. Creating a SQL Prepared Statement

```sql
PREPARE find_order(bigint) AS
SELECT order_id, tenant_id, amount, status
FROM pool_state_lab.orders
WHERE order_id = $1;
```

### 15.2. Executing

```sql
EXECUTE find_order(1);
EXECUTE find_order(2);
```

`PREPARE` retains parse/analyze metadata and allows PostgreSQL to evaluate generic vs. custom plan reuse.

### 15.3. Cleaning Up With `DEALLOCATE`

```sql
DEALLOCATE find_order;
```

Without `DEALLOCATE`, a SQL prepared statement persists until the backend session ends or is properly reset.

### 15.4. `PREPARE` Is Not Transaction-Bound

```sql
BEGIN;

PREPARE count_orders(integer) AS
SELECT COUNT(*)
FROM pool_state_lab.orders
WHERE tenant_id = $1;

COMMIT;

EXECUTE count_orders(10);
```

On the **same direct PostgreSQL session**, the statement survives `COMMIT`. That is precisely why this pattern fails across transaction boundaries under PgBouncer transaction pooling.

### 15.5. Names Must Be Unique Within a Session

Running:

```sql
PREPARE find_order(bigint) AS SELECT ...;
```

twice with the same name on one backend without `DEALLOCATE` raises `duplicate_prepared_statement` (`SQLSTATE 42P05`).

### 15.6. `EXECUTE` on a Backend Without `PREPARE`

If the backend lacks that name, `EXECUTE find_order(1)` raises `invalid_sql_statement_name` (`SQLSTATE 26000`).

Both errors frequently occur when applications misunderstand session-prepared statement lifetimes or switch pooler modes.

---

## 16. `pg_prepared_statements`: Observing SQL and Protocol Prepared Statements

### 16.1. Inspecting Prepared Statements in the Current Session

```sql
SELECT
    name,
    statement,
    from_sql,
    generic_plans,
    custom_plans
FROM pg_prepared_statements
ORDER BY name;
```

This view shows prepared statements existing **in the current session**, not a cluster-wide inventory across all clients' backends.

### 16.2. What Does `from_sql` Mean?

- `from_sql = true`: created via SQL `PREPARE`.
- `from_sql = false`: created via PostgreSQL's extended query protocol (protocol-level).

This signal helps diagnose driver behavior.

### 16.3. Generic Plans vs. Custom Plans

PostgreSQL can choose:

- **Custom plan** tailored to specific parameter values.
- **Generic plan** shared across multiple executions.

`generic_plans` and `custom_plans` show the plan-selection history for that prepared statement in the session.

### 16.4. `EXPLAIN EXECUTE`

```sql
PREPARE explain_order(bigint) AS
SELECT *
FROM pool_state_lab.orders
WHERE order_id = $1;

EXPLAIN EXECUTE explain_order(1);

DEALLOCATE explain_order;
```

Do not assume preparing a statement always makes the query faster. It primarily saves parse/planning overhead when applicable.

### 16.5. Replanning Can Occur

DDL changes, planner statistics updates, or `search_path` changes can trigger re-analysis/replanning per PostgreSQL rules. A prepared statement is not a permanent snapshot of table structure.

Because of name resolution and schema shadowing, changing `search_path` or DDL can cause surprises with unqualified SQL. Use schema-qualified statements in sensitive code paths.

---

## 17. JDBC `PreparedStatement` Is Not Equivalent to SQL `PREPARE`

### 17.1. JDBC API

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT order_id, amount FROM pool_state_lab.orders WHERE order_id = ?")) {
    ps.setLong(1, 1L);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("order_id"));
        }
    }
}
```

This is a **parameter-binding API**; it does not mean the driver always sends SQL text `PREPARE find_order(...) AS ...`.

### 17.2. Three Layers Often Confused

1. **JDBC `PreparedStatement` object:** Java object holding parameter bindings.
2. **PostgreSQL extended query protocol:** `Parse`/`Bind`/`Execute`, potentially using unnamed statements/portals.
3. **Server-side named prepared statement:** the driver may cache a name and reuse it on the same server session after a configured threshold.

The driver decides how these layers map. Never infer from a Java `PreparedStatement` that PostgreSQL holds a durable SQL `PREPARE` name.

### 17.3. pgJDBC `prepareThreshold`

pgJDBC has a `prepareThreshold` option controlling when server-side named prepared statements activate based on execution count. A common default is 5, though you should check **your actual driver version and DataSource/URL**.

Example URL:

```text
jdbc:postgresql://localhost:5432/appdb?prepareThreshold=0
```

Per PgBouncer compatibility guidance, `prepareThreshold=0` disables threshold-based server-side named prepares in pgJDBC when avoiding session dependence. **It does not disable parameter binding**: applications still use `PreparedStatement` to pass data values safely.

### 17.4. Prepared Statement Caching in Drivers/Pools

Drivers can cache metadata and prepared statement names per physical connection. If the server resets/discards state behind the driver's back, invalid-statement errors can occur.

Never run `DEALLOCATE ALL` or `DISCARD ALL` manually on a connection with an active driver cache unless you understand how the driver recovers.

### 17.5. Java `PreparedStatement` Prevents SQL Injection

Parameter binding secures **data values**; it cannot bind arbitrary schema or table names:

```java
// Data is bound safely:
PreparedStatement ps = connection.prepareStatement(
    "SELECT * FROM pool_state_lab.orders WHERE tenant_id = ?");
ps.setInt(1, 10);
```

If table names vary by tenant, use an explicit allowlist/authorization model—never concatenate untrusted input into SQL strings.

---

## 18. PgBouncer Transaction Pooling and the Two Types of Prepared Statements

This is the easiest area to get wrong when integrating drivers with PgBouncer.

### 18.1. SQL `PREPARE`/`EXECUTE` Is Incompatible With Session Assumptions

```sql
PREPARE count_by_tenant(integer) AS
SELECT COUNT(*)
FROM pool_state_lab.orders
WHERE tenant_id = $1;

-- Next transaction may land on another backend:
EXECUTE count_by_tenant(10);
```

In transaction pooling, two statements in different transactions **are not guaranteed to share a backend**. `EXECUTE` can fail to find the prepared statement or collide with a name from another client.

### 18.2. Conditional Support for Protocol-Level Named Prepared Statements

Starting in **PgBouncer 1.21.0**, PgBouncer can track **protocol-level named prepared statements** in transaction pooling and map them onto backend prepared statements **when `max_prepared_statements` is non-zero**.

This applies to compatible client/driver protocol prepares; **it does not mean SQL text `PREPARE ...; EXECUTE ...; DEALLOCATE ...` magically works across transactions**.

### 18.3. Role of `max_prepared_statements`

Example PgBouncer config:

```ini
[pgbouncer]
pool_mode = transaction
max_prepared_statements = 100
```

This value illustrates the mechanism; picking the right limit depends on workload, query shape cardinality, and memory overhead. Verify against your **actual PgBouncer version, driver, and deployment**.

### 18.4. What Does PgBouncer Do When Enabled?

Conceptually:

```text
Client C1:
  protocol Parse name=stmt_A, SQL=SELECT ... WHERE id=$1
            |
            v
PgBouncer tracks client name and SQL/query identity
            |
        transaction #1
            |
            v
Backend P1: internal named prepared statement

        transaction #2
            |
            v
Backend P2: PgBouncer ensures corresponding protocol
            prepared statement is available/rebound
```

The pooler maps client statement names to actual backend prepared statements within its configured capacity. This adds overhead and limits, and does not replace other session-state rules.

### 18.5. When Disabled

If `max_prepared_statements = 0` or an older PgBouncer lacks support, drivers using cross-transaction named server-side prepares will error. Options:

- Enable the feature on a compatible PgBouncer version and test thoroughly.
- Or disable server-side named prepares in the driver, e.g., `prepareThreshold=0` in pgJDBC.
- Or use session pooling / direct connections for workloads requiring session semantics.

### 18.6. Do Not Assume "PgBouncer Supports Prepared" Means All Session Features Work

Even with protocol-level prepared statement tracking enabled, SQL `PREPARE`, session `LISTEN`, `ON COMMIT PRESERVE ROWS` temp tables, and session-level advisory locks **remain unsafe across transaction boundaries**.

### 18.7. Different Client Libraries

Never apply one JDBC driver setting blindly across every client stack. PHP/PDO, libpq, Python drivers, Go drivers, and ORMs vary in protocol usage and caching by version. Read PgBouncer's compatibility FAQ and test with your exact driver version.

---

## 19. PgBouncer Compatibility Table by Pool Mode

This table summarizes core concepts; exact support depends on PgBouncer version and configuration. It does not replace official documentation.

| Feature | Session Pooling | Transaction Pooling | Statement Pooling |
|---|---|---|---|
| Multi-statement transaction | Yes | Yes | Not supported by design |
| Arbitrary session `SET`/`RESET` across transactions | Yes, when reset properly | Must not rely upon | Must not rely upon |
| `SET LOCAL` inside transaction | Yes | Yes | Unsuitable for multi-statement workflows |
| Temp `ON COMMIT DROP` in same transaction | Yes | Yes | Unsuitable for multi-statement workflows |
| Temp `PRESERVE ROWS` across commits | Yes while client/server session holds | No | No |
| Temp `DELETE ROWS` keeping table object | Yes within session | No | No |
| SQL `PREPARE`/`EXECUTE` across commits | Yes while session holds | No | No |
| Protocol-level named prepared | Yes | Conditional with support & config | Conditional per version/config |
| Session `LISTEN` | Yes | No | No |
| `NOTIFY` | Yes | Yes | Within statement scope |
| Session-level advisory lock | Yes if actively unlocked | No | No |
| Transaction-level advisory lock | Yes | Yes | Only within supported transaction |
| Non-`WITH HOLD` cursor in one transaction | Yes | Yes | No for multi-statement transactions |
| Cursor `WITH HOLD` across commits | Yes | No | No |
| Stable backend PID throughout client connection | Yes | Not guaranteed | Not guaranteed |

### 19.1. Do Not Pick a Pool Mode From One Throughput Benchmark Alone

Transaction pooling cuts server backend counts for large client populations, yet if an app depends heavily on session features, switching blindly to transaction pooling introduces correctness bugs. **Functional compatibility** comes before throughput tuning.

### 19.2. Session Pooling and Application Pools

When HikariCP keeps connections open continuously to a PgBouncer session pool, each client connection pins a backend, reducing multiplexing gains relative to transaction pooling. Even so, session mode fits workloads needing SQL `PREPARE`, session temp tables, or `LISTEN`.

---

## 20. Connection Resets: `RESET`, `DEALLOCATE`, and `DISCARD` Differ

### 20.1. `RESET`

```sql
RESET TimeZone;
RESET search_path;
RESET ALL;
```

`RESET ALL` resets resettable run-time parameters per session semantics. It **is not** a complete cleanup of temporary objects, prepared statements, or advisory locks.

### 20.2. `DEALLOCATE`

```sql
DEALLOCATE ALL;
```

Removes prepared statements in the current session. It does not drop temp tables or reset session GUCs.

### 20.3. `DISCARD PLANS`

```sql
DISCARD PLANS;
```

Drops cached execution plans so they replan later. It differs from `DEALLOCATE ALL`, as prepared statement definitions remain rather than being deallocated.

### 20.4. `DISCARD TEMP`

```sql
DISCARD TEMP;
```

Drops temporary tables in the current session. Never run it while the application still needs them.

### 20.5. `DISCARD ALL`

```sql
DISCARD ALL;
```

PostgreSQL uses `DISCARD ALL` for a broad session reset, covering GUC changes, SQL/protocol prepared state, temp objects, portals, `LISTEN` subscriptions, advisory locks, and cached plans per command semantics.

**`DISCARD ALL` cannot be executed inside a transaction block.**

### 20.6. Reset Comparison

| Command | GUCs | Temp Tables | Prepared Statements | Session Advisory Locks | `LISTEN` |
|---|---|---|---|---|---|
| `RESET ALL` | Reset | No | No | No | No |
| `DEALLOCATE ALL` | No | No | Dropped | No | No |
| `DISCARD PLANS` | No | No | Keeps names, clears cached plans | No | No |
| `DISCARD TEMP` | No | Dropped | No | No | No |
| `UNLISTEN *` | No | No | No | No | Cancels subscriptions |
| `pg_advisory_unlock_all()` | No | No | No | Releases session advisory locks | No |
| `DISCARD ALL` | Broad reset | Dropped | Dropped | Released | Canceled |

### 20.7. Driver Cache Issues After Reset

If the driver tracks client-side metadata assuming prepared statement `S_42` exists on the backend, an external `DISCARD ALL` wipes `S_42` without the driver knowing. Either the driver must detect and re-prepare, or the pool must use a compatible reset mechanism.

Never inject manual `DISCARD ALL` into app transaction cleanup without understanding driver behavior.

---

## 21. PgBouncer `server_reset_query`

### 21.1. Session Pooling

PgBouncer configuration:

```ini
[pgbouncer]
pool_mode = session
server_reset_query = DISCARD ALL
```

In session pooling, the reset query runs when PgBouncer returns the PostgreSQL server connection to the pool after the client session ends. It cleans state so the next client never inherits objects or settings from the previous session.

### 21.2. Reset Queries Do Not Always Run

In transaction pooling, by default PgBouncer **does not run `server_reset_query` at the end of every transaction**. Transaction pooling requires clients not to depend on incompatible session features and relies on session-free protocols. An option `server_reset_query_always` exists for special cases, yet should not be treated as legitimizing arbitrary session-state patterns.

### 21.3. When a JDBC Pool Keeps the PgBouncer Client Session Open

While HikariCP keeps TCP connections open to a PgBouncer session pool, PgBouncer sees no client disconnect, so **`server_reset_query` does not run yet**. Session state persists across logical JDBC connection checkouts and returns.

### 21.4. Distinguishing the Two Reset Layers

```text
Request A -> Hikari logical close
              |
              +-- Hikari resets some tracked JDBC states
              |   but does not guarantee clearing custom GUCs/temp/PREPARE
              |
              v
        Hikari physical connection stays open
              |
              v
        PgBouncer client session stays open
              |
              v
        session-mode server_reset_query has not run
```

### 21.5. How to Handle It

Pick **one clear state contract**:

- Avoid session-scoped state in request code.
- Use `SET LOCAL` and `ON COMMIT DROP`.
- Manage any remaining required session state with tested hooks.
- Recycle physical connections when full session cleanup is required.
- Isolate workloads needing long-lived session state into dedicated pools.

---

## 22. JDBC/HikariCP: One Transaction With Local Context

The snippet below illustrates **one request flow** using a `DataSource`. It does not require manually issuing SQL `PREPARE`.

### 22.1. Illustrative Java Code

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class OrderReportService {
    private final DataSource dataSource;

    public OrderReportService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public BigDecimal paidTotalForTenant(int tenantId) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            boolean previousAutoCommit = connection.getAutoCommit();
            connection.setAutoCommit(false);

            try {
                // SET LOCAL semantics: true means transaction-local.
                try (PreparedStatement context =
                        connection.prepareStatement(
                            "SELECT set_config('app.tenant_id', ?, true)")) {
                    context.setString(1, Integer.toString(tenantId));
                    context.executeQuery().close();
                }

                BigDecimal total;
                try (PreparedStatement query =
                        connection.prepareStatement(
                            "SELECT COALESCE(SUM(amount), 0) " +
                            "FROM pool_state_lab.orders " +
                            "WHERE tenant_id = " +
                            "current_setting('app.tenant_id')::integer " +
                            "AND status = 'paid'")) {
                    try (ResultSet rs = query.executeQuery()) {
                        if (!rs.next()) {
                            throw new SQLException("Aggregate returned no row");
                        }
                        total = rs.getBigDecimal(1);
                    }
                }

                connection.commit();
                return total;
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            } finally {
                // Restore JDBC state for pool. The actual transaction-local
                // tenant context is cleared by COMMIT/ROLLBACK.
                try {
                    connection.setAutoCommit(previousAutoCommit);
                } catch (SQLException resetFailure) {
                    // In production, let the pool discard a broken connection
                    // and log this failure through the service error policy.
                    throw resetFailure;
                }
            }
        }
    }
}
```

### 22.2. Why Use `set_config(..., true)`?

`set_config(setting_name, value, is_local)` sets a GUC. The third argument:

- `true`: transaction-local, akin to `SET LOCAL`.
- `false`: session-level, akin to `SET`.

`PreparedStatement` binds the tenant ID string as a **data value**, avoiding unsupported placeholders in `SET LOCAL some_guc = ?`.

### 22.3. Why Call `setAutoCommit(false)` First?

So all statements from setting context through the `SELECT` share one transaction. If autocommit is true, the first statement's transaction-local GUC **expires before the next `SELECT`**.

### 22.4. Why Roll Back in `catch`?

A query error puts the transaction into an aborted state; without rollback, subsequent checkouts may break if the pool/driver does not clean up properly.

### 22.5. Why Restore JDBC State?

`setAutoCommit(false)` is a property of the JDBC `Connection`. Pools usually reset tracked JDBC properties, yet the application should follow a clean contract and never return a connection with an open transaction.

### 22.6. Notes on `finally` and Exceptions

This snippet demonstrates the flow; in production, enforce a consistent policy for **rollback failures, unknown commit outcomes, state resets, and connection invalidation**. If `setAutoCommit(previousAutoCommit)` fails, it can mask the original exception seen by callers; logging/monitoring should preserve the root cause. Do not treat this snippet as a full transaction framework.

### 22.7. SECURITY CAVEAT

This code accepts `tenantId` from the service; it does not prove the caller is authorized for that tenant. Authenticate and authorize before calling. When using GUC-based RLS, design runtime SQL privileges and context sources so callers cannot pick arbitrary tenants.

---

## 23. HikariCP and Session Settings

### 23.1. HikariCP Can Reset Some JDBC Properties

A JDBC pool can track and restore properties like `autoCommit`, `readOnly`, `transactionIsolation`, catalog/schema, and network timeout per driver/pool support. Yet **never assume it tracks arbitrary SQL `SET` statements run by the app**.

For example:

```sql
SET app.tenant_id = '10';
SET search_path = tenant_10, public;
```

These execute on the backend; the pool has no complete registry of custom SQL GUC mutations.

### 23.2. `connectionInitSql` Is Not a Per-Request Reset

HikariCP's `connectionInitSql` runs when **a new physical connection is created**, not on every logical checkout.

Never configure:

```text
connectionInitSql=SET app.tenant_id='10'
```

expecting Request B for tenant 20 to be reset on every borrow.

### 23.3. Set Baselines at Connect Time

Defaults like application name, timezone, or baseline schema can be initialized on connection creation for the **entire connection lifetime**.

Request-varying context such as tenant IDs, per-query deadlines, and dynamic roles should not be pinned onto long-lived physical connections unless backed by strict multi-tenant isolation and cleanup.

### 23.4. Do Not Rely on `close()` as Your Only Rollback Guarantee

Code should always end transactions explicitly via `commit()` or `rollback()` before returning handles. Pools may attempt rollback on dirty returns, yet that safety net is not normal control flow.

### 23.5. Broken Physical Connections

A killed backend/socket, network drop, or failover wipes all prepared statements, temp tables, and session locks. The driver/pool must evict broken connections or reconnect cleanly, never blindly replaying half of an old transaction.

---

## 24. Failed PostgreSQL Transactions and `SQLSTATE 25P02`

### 24.1. A Failing Statement Inside a Transaction

```sql
BEGIN;

SELECT 1 / 0;

-- Continuing here is rejected because the transaction is aborted:
-- SELECT * FROM pool_state_lab.orders;

ROLLBACK;
```

After `division_by_zero`, the transaction enters an aborted state; subsequent statements fail with "current transaction is aborted, commands ignored until end of transaction block" (`SQLSTATE 25P02`) until rolled back or recovered validly.

### 24.2. Why Is This Dangerous With Pools?

If an app swallows the exception and returns the connection still stuck in an aborted transaction, the next request can receive a physical connection unable to run normal SQL.

### 24.3. Minimum Cleanup

In `catch`:

```java
try {
    connection.rollback();
} catch (SQLException rollbackFailure) {
    // Record failure; connection might be unusable.
}
```

Only after rollback succeeds can the connection be considered reusable.

### 24.4. `SAVEPOINT` for Partial Recovery

```sql
BEGIN;

SAVEPOINT before_optional_work;

-- Optional statement that might fail.

-- If the optional statement failed and the caller handles it:
-- ROLLBACK TO SAVEPOINT before_optional_work;

COMMIT;
```

Savepoints allow continuing a transaction after rolling back to a marker, provided code checks accurately and preserves business invariants. Never use savepoints to swallow mandatory errors and commit anyway.

---

## 25. Advisory Locks: Session vs. Transaction Are Completely Different

### 25.1. Session-Level Advisory Lock

```sql
SELECT pg_advisory_lock(901);

-- Protected work.

SELECT pg_advisory_unlock(901);
```

A lock acquired by `pg_advisory_lock` is **session-scoped**. Neither `COMMIT` nor `ROLLBACK` releases it. Forgetting to unlock and returning the connection to the pool carries the lock over to another logical request.

### 25.2. Transaction-Level Advisory Lock

```sql
BEGIN;

SELECT pg_advisory_xact_lock(901);

-- Work inside transaction.

COMMIT; -- lock releases automatically
```

This is usually the better choice when a lock only needs to span a single transaction.

### 25.3. Transaction Pooling

In PgBouncer transaction pooling:

- Session-level advisory locks are **incompatible** with returning the server connection to other clients after the transaction.
- Transaction-level advisory locks work within the same transaction per PostgreSQL semantics.

### 25.4. `ROLLBACK` Does Not Release Session Advisory Locks

```sql
BEGIN;

SELECT pg_advisory_lock(902);

ROLLBACK;

-- Session-level lock can still remain on this backend.
SELECT pg_advisory_unlock(902);
```

This detail is easily missed by developers assuming "rollback undoes all state".

### 25.5. `pg_advisory_unlock_all()`

```sql
SELECT pg_advisory_unlock_all();
```

Releases all session advisory locks held by the current backend. It is a cleanup tool, not a substitute for transaction logic or lock ownership tracking when components intentionally hold session locks.

---

## 26. `LISTEN`/`NOTIFY` and Connection Lifetimes

### 26.1. `LISTEN` Is Session-Scoped

```sql
LISTEN order_events;
```

The subscription binds to the PostgreSQL session. If the client shifts to another backend after `COMMIT`, it is no longer on the session registered with `LISTEN`.

### 26.2. Do Not Use `LISTEN` Through a Transaction Pool for Continuous Receiving

PgBouncer transaction pooling does not pin one PostgreSQL backend for the client's lifetime, so `LISTEN` subscriptions **are unsuitable** for long-lived listeners on that endpoint.

### 26.3. Proper Topology

```text
Application request pool
       |
       +--> transaction pooling (short queries)

Dedicated notification listener
       |
       +--> direct connection or session pooling
              |
              +--> LISTEN order_events
```

Listeners need reconnect logic to re-issue `LISTEN` whenever a new connection establishes.

### 26.4. `NOTIFY` Differs From `LISTEN`

```sql
NOTIFY order_events, 'order_changed';
```

Sending `NOTIFY` works inside transaction pooling per PostgreSQL commit semantics; **receiving** notifications via `LISTEN` requires a stable session registration.

### 26.5. `UNLISTEN`

```sql
UNLISTEN *;
```

Cancels subscriptions on the current backend session when needed. `DISCARD ALL` also clears `LISTEN` state.

---

## 27. Cursors and `WITH HOLD`

### 27.1. Cursors Inside a Transaction

```sql
BEGIN;

DECLARE cur_orders CURSOR FOR
SELECT order_id, amount
FROM pool_state_lab.orders
ORDER BY order_id;

FETCH 2 FROM cur_orders;

CLOSE cur_orders;

COMMIT;
```

Standard cursors belong to the transaction and die at `COMMIT`; in transaction pooling they work **when all operations stay within one transaction**.

### 27.2. `WITH HOLD`

```sql
BEGIN;

DECLARE cur_orders_hold CURSOR WITH HOLD FOR
SELECT order_id, amount
FROM pool_state_lab.orders
ORDER BY order_id;

COMMIT;

-- On the same direct backend session:
FETCH ALL FROM cur_orders_hold;

CLOSE cur_orders_hold;
```

`WITH HOLD` keeps the cursor alive past `COMMIT` on **the same backend session**, making it unsafe under transaction pooling where the backend can switch before `FETCH`.

### 27.3. JDBC Streaming `ResultSet`

Some drivers use server-side cursors/fetch sizes when autocommit and transaction settings permit. When using a streaming `ResultSet`:

- Keep the transaction open for the `ResultSet`'s lifetime.
- Never return the connection to the pool before finishing reads.
- Never commit mid-fetch unless driver/cursor semantics support it.
- Avoid keeping transactions idle for too long.

Never tune fetch sizes blindly by rule of thumb without understanding driver and proxy behavior.

---

## 28. SQL `PREPARE` and Connection Resets in Practice

### 28.1. Normal Sequence on a Direct Session

```sql
PREPARE sum_paid(integer) AS
SELECT COALESCE(SUM(amount),0)
FROM pool_state_lab.orders
WHERE tenant_id = $1 AND status = 'paid';

EXECUTE sum_paid(10);

SELECT name, from_sql FROM pg_prepared_statements;

DEALLOCATE sum_paid;
```

### 28.2. In a Direct Application Pool

A request can `PREPARE`, use it, and `DEALLOCATE` before returning the connection. Yet if the driver uses server-side prepare caching, never mix driver-managed names carelessly with SQL `DEALLOCATE ALL`.

### 28.3. `PREPARE` Cache Is Not a Result Cache

Server-side prepared statements **do not cache `SELECT` rows**. On `EXECUTE`, PostgreSQL executes the query against live data under current transaction snapshot rules.

### 28.4. DDL and Cached Plans

A schema migration can make an old plan obsolete or change return types. PostgreSQL invalidates and replans automatically where supported, yet structural changes can still raise errors such as invalid cached plan result types.

Never treat a "prepared statement cache" as automatically refreshing application SQL contracts. Migrations require managing driver/server connections, rolling app deployments, and error handling.

### 28.5. Versions and Generic Plans

`plan_cache_mode` includes `auto`, `force_generic_plan`, and `force_custom_plan`. This is a performance tuning tool; never force generic plans to "fix" pooling bugs.

---

## 29. Relationship Among Pools, Backend Count, and Performance

### 29.1. Do Not Equate Requests With Connections

An app can serve 10,000 concurrent requests through a 100-connection pool. Conversely, 50 service instances × 20 connections can open 1,000 physical connections.

### 29.2. Every PostgreSQL Backend Consumes Resources

Backends consume memory, file descriptors, transaction state, and management overhead. Connection pooling reuses sessions and bounds concurrency, yet cannot speed up expensive queries on its own.

### 29.3. Oversized Pools

An overly large pool can:

- Inflate backend count.
- Increase lock, CPU, and I/O contention.
- Cause memory pressure and context-switching thrash.
- Mask slow queries behind queues of waiting clients.

### 29.4. Undersized Pools

Too small a pool makes requests queue for checkout even while the database has spare capacity. Measure queue latency, DB execution latency, and workload rather than guessing numbers.

### 29.5. When Does Transaction Pooling Pay Off?

When many client connections execute short transactions with no cross-transaction session state, PgBouncer multiplexes them onto far fewer backends.

Never put a long-lived stateful session workflow onto transaction pooling expecting SQL state to stay on one backend.

---

## 30. Monitoring: Tracking Sessions, Transactions, and Poolers

### 30.1. Inspecting PostgreSQL Backends

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST, pid;
```

Role privileges and PostgreSQL policies govern how much detail you see for other sessions.

### 30.2. `idle in transaction`

`state = 'idle in transaction'` indicates a backend holding an open transaction while currently running no statement. This pins locks/snapshots and causes bloat or blocking.

Never return a connection to the pool with an unresolved transaction. Consider `idle_in_transaction_session_timeout` for eligible workloads, keeping in mind timeouts terminate sessions and require app recovery.

### 30.3. PgBouncer `SHOW POOLS`

When authorized and connected to the **PgBouncer administrative database/console**, PgBouncer supports commands such as:

```text
SHOW POOLS;
SHOW CLIENTS;
SHOW SERVERS;
SHOW STATS;
```

These are **PgBouncer admin console commands**, not queries you send to the PostgreSQL application database.

### 30.4. Metrics to Track

| Metric | Meaning |
|---|---|
| Client connections | Clients connected to the pooler |
| Active server connections | Backends currently serving requests |
| Idle server connections | Backends ready for reuse |
| Waiting clients | Clients queued for a backend |
| `maxwait` | Longest wait time in the pool queue |
| Pool checkout latency | Time app waits for a JDBC `Connection` |
| Query p95/p99 | Actual SQL latency |
| Transaction duration | Time holding backend and locks |
| Invalid prepared statement errors | Signal of protocol/pool mismatch |
| Duplicate prepared name errors | Signal of broken session cache/cleanup |
| Temp files and temp tables | Resource pressure and lifetime issues |

### 30.5. Query `pg_prepared_statements` in the Right Place

`pg_prepared_statements` reflects only the backend session running that query. Two consecutive queries through transaction pooling can hit different backends; never treat its output as a cluster-wide inventory.

---

## 31. Common Errors and How to Diagnose Them

### 31.1. `prepared statement does not exist`

Example `SQLSTATE 26000`:

```text
ERROR: prepared statement "stmt_17" does not exist
```

Possible causes:

- Client ran `PREPARE` on backend A, `EXECUTE` on backend B.
- PgBouncer transaction pooling lacks protocol-prepare support or config.
- Session/backend reset or reconnected.
- `DEALLOCATE`/`DISCARD ALL` wiped prepared statements unknown to the driver.

Inspect pool mode, driver settings, `max_prepared_statements`, and SQL `PREPARE` vs. protocol prepares.

### 31.2. `prepared statement already exists`

Example `SQLSTATE 42P05`:

```text
ERROR: prepared statement "stmt_17" already exists
```

Often caused by re-preparing a name on a backend that still holds that name from an earlier client/request, improper reset policy, or driver/pooler state desync.

Never "fix" this by generating unbounded random names per request; that causes session bloat if statements are never deallocated.

### 31.3. `relation does not exist`

Example `SQLSTATE 42P01`:

```text
ERROR: relation "tmp_ids" does not exist
```

Common causes:

- Temp table was created on a different backend.
- `ON COMMIT DROP` dropped the table before the next statement.
- Session reset or reconnected.
- Different `search_path`.
- Table was not created yet in the current transaction.

### 31.4. `relation already exists`

```text
ERROR: relation "tmp_ids" already exists
```

Often caused by a `PRESERVE ROWS` or `DELETE ROWS` temporary table left over from an earlier request on the same session.

### 31.5. `current transaction is aborted`

`SQLSTATE 25P02` is normally a **consequence** of an earlier error inside the transaction. Find the root error and roll back. Never keep sending `SET` or `SELECT` as though the transaction were healthy.

### 31.6. Vanished Session

Network drops, connection resets, backend termination, or failovers erase prepared statements, temp tables, and session state. Retrying business transactions requires idempotency and commit-outcome checking—never reconnect and resume at statement three.

### 31.7. Missed Notifications

Apps running `LISTEN` through a PgBouncer transaction pool lack a stable listener session. Move to a dedicated connection and re-subscribe on reconnect.

### 31.8. Advisory Lock Held Too Long

Check for un-unlocked session-level `pg_advisory_lock`; switch to `pg_advisory_xact_lock` if the business scope is a single transaction.

---

## 32. Choosing a Pooling Strategy per Workload

| Workload | Option to Consider | Rationale |
|---|---|---|
| CRUD APIs, short transactions, no session state | PgBouncer transaction pooling | High backend multiplexing when app complies |
| API with `TEMP ON COMMIT DROP` in one transaction | Transaction pooling works | Backend stays bound for that transaction |
| Multi-transaction job sharing the same temp table | Direct/session pooling or refactor | Requires session pinning |
| Dedicated `LISTEN`/`NOTIFY` receiver | Direct/session pooling | `LISTEN` is session state |
| JDBC using protocol named prepares in tx pooling | Supporting PgBouncer version + `max_prepared_statements` | Pooler maps names and prepares on backends |
| SQL `PREPARE` across commits | Direct/session pooling or refactor | SQL `PREPARE` is session-bound |
| `CURSOR WITH HOLD` across commits | Direct/session pooling | Cursor belongs to session |
| Advisory lock inside a transaction | `pg_advisory_xact_lock` | Releases automatically at `COMMIT` |
| Multi-tenant request-scoped GUC | Explicit transaction + `SET LOCAL` | Prevents state leaks; still needs authorization |
| DDL migrations or session-custom scripts | Dedicated pool/connection | Often requires session pinning or long locks |

### 32.1. Splitting Pools by Workload Is Normal

One system may run:

```text
web-api-pool        -> PgBouncer transaction pooling
notification-listen -> direct connection
migration-runner    -> direct connection / controlled admin session
long-reporting      -> dedicated read pool with tailored limits
```

One endpoint and one pool mode do not have to serve every workload.

### 32.2. Transaction Pooling Is Not a Universal Accelerator

It does not make slow queries fast; it optimizes PostgreSQL backend utilization. If a workload is I/O- or lock-bound, tune SQL, indexes, and transaction durations alongside pooling.

---

## 33. Plan for Migrating From Session Pool to Transaction Pool

### 33.1. Audit Session Features

Search application code, ORMs, and scripts for:

- `SET search_path`, `SET ROLE`, custom `SET`.
- `CREATE TEMP TABLE` and `ON COMMIT` clauses.
- SQL `PREPARE`/`EXECUTE`.
- JDBC server-side named prepare/caching.
- `LISTEN`.
- `pg_advisory_lock`.
- `DECLARE CURSOR WITH HOLD`.
- Long-lived transactions and streaming `ResultSet`s.
- DDL migrations or extension calls relying on session state.

### 33.2. Move Session State to Transaction Scope

- Request-local `SET` → `SET LOCAL` where appropriate.
- Cross-transaction temp tables → `ON COMMIT DROP` in one transaction or persistent staging tables.
- Session advisory locks → transaction advisory locks or dedicated connections.
- `LISTEN` → dedicated direct/session connection.
- Cross-transaction SQL `PREPARE` → remove dependency, use compatible driver protocol, or keep on session mode.

### 33.3. Verify Prepared Statement Compatibility

Confirm the **exact**:

1. PgBouncer version.
2. Pool mode.
3. `max_prepared_statements`.
4. Driver/ORM version.
5. Driver server-side prepare flags.
6. Statement type (SQL `PREPARE` vs. protocol prepared).

Never rely on "a couple of test queries passed".

### 33.4. Test Under Concurrency

Run interleaved requests across multiple physical connections. For transaction pooling, verify backend reassignment actually happens during tests rather than testing one client on one idle backend.

### 33.5. Rollout and Rollback

Roll out service by service, monitor `SQLSTATE`s and correctness, and preserve a fast fallback to session/direct endpoints if incompatibilities surface.

### 33.6. Never Switch Modes for Migrations Without Testing

DDL and schema migrations often need long transactions, temp objects, or session settings. Run migrations via a verified pooler or direct connection rather than assuming they behave like CRUD APIs.

---

## 34. Resetting a Contaminated Connection

### 34.1. When Should a Physical Connection Be Discarded?

Evict a connection instead of returning it to the pool when:

- Transaction outcome or session state is uncertain.
- Backend/server disconnected.
- `rollback()` failed.
- Application is unsure whether session locks, temp objects, or role state remain.
- Driver/server prepare caches fell out of sync with no safe recovery.

### 34.2. Never Run `DISCARD ALL` Inside a Transaction

```sql
BEGIN;

-- Invalid inside a transaction:
-- DISCARD ALL;

ROLLBACK;
```

`DISCARD ALL` only works outside transaction blocks when no business work is active.

### 34.3. Driver Protocol State Issues

Sending raw `DISCARD ALL` after every request on a JDBC connection whose driver caches named statements leaves the driver unaware its cache was wiped.

Prefer pool/driver-supported reset APIs, or **close the physical connection** to establish a clean session when state cannot be synchronized.

### 34.4. Confirm Ownership Before Resetting

`DISCARD ALL` destroys role settings, temp objects, `LISTEN` registrations, and locks held intentionally by other components. In shared-session architectures, mistimed resets break callers.

### 34.5. Separate Business Errors From Connection Hygiene

A transaction rejected by a business constraint requires rollback. A broken or state-contaminated connection requires eviction or reset. Both actions may happen together, yet **do not replace each other**.

---

## 35. Common Mistakes

**1. "JDBC pool `Connection.close()` always closes the PostgreSQL backend session."** False. It normally returns the logical handle to the pool.

**2. "`COMMIT` clears all session state."** False. It ends the transaction without wiping session GUCs, `PRESERVE ROWS` temp tables, SQL `PREPARE`, `LISTEN`, or session advisory locks.

**3. "`SET` and `SET LOCAL` are identical."** False. Their scopes and rollback behaviors differ.

**4. "`SET LOCAL` outside a transaction carries over to the next query."** False.

**5. "Custom GUC `app.tenant_id` proves tenant authorization on its own."** False. Callers might set it themselves; authorization is required.

**6. "`TimeZone` and `search_path` only affect display."** False. They affect parsing, name resolution, and query results.

**7. "Pools always reset every ad-hoc SQL `SET`."** Never assume this by default.

**8. "`connectionInitSql` reruns for every request."** False; it runs on physical connection initialization.

**9. "Temporary tables are request-local."** False. By default they are session-local.

**10. "Temporary tables auto-drop on `COMMIT` by default."** False. PostgreSQL defaults to `ON COMMIT PRESERVE ROWS`.

**11. "`ON COMMIT DELETE ROWS` drops the table too."** False. The table stays in the session.

**12. "`ON COMMIT DROP` works across multiple autocommit statements."** False. The table drops right after the `CREATE` statement commits.

**13. "`PRESERVE ROWS` is safe across transactions with PgBouncer transaction pooling."** False.

**14. "`DELETE ROWS` temp tables are safe because rows are cleared."** False; the table object remains session-bound.

**15. "Transaction pooling swaps backends between two statements inside a normal transaction."** False by contract; the server connection stays bound for the transaction.

**16. "Statement pooling allows multi-statement transactions just like session mode."** False.

**17. "Seeing the same PID twice proves the backend is permanently pinned."** False; the pooler may have picked it again by chance.

**18. "`PREPARE` caches `SELECT` result rows."** False. It caches prepared structure/plans; queries still execute.

**19. "JDBC `PreparedStatement` always sends SQL `PREPARE`."** False.

**20. "PgBouncer transaction pooling never supports any prepared statements."** No longer true: protocol-level named prepared statements have conditional support since PgBouncer 1.21.

**21. "Non-zero `max_prepared_statements` makes cross-session SQL `PREPARE`/`EXECUTE` work."** False. That supports protocol-level named statements; SQL `PREPARE` is separate.

**22. "`prepareThreshold=0` strips JDBC's ability to bind parameters."** False. It turns off pgJDBC's threshold-based server named prepares, not the `PreparedStatement` API.

**23. "`pg_prepared_statements` lists all prepared statements in the cluster."** False. It reflects only the current session.

**24. "`DISCARD PLANS` and `DEALLOCATE ALL` are equivalent."** False.

**25. "`RESET ALL` drops temp tables."** False.

**26. "`DISCARD ALL` runs inside a transaction."** False.

**27. "`DISCARD ALL` is always safe when the driver caches named statements."** False if client/server state goes out of sync.

**28. "PgBouncer `server_reset_query` always runs after every transaction."** False by default under transaction pooling.

**29. "Using session pooling with Hikari means PgBouncer resets the backend after every web request."** False while Hikari keeps the physical connection open.

**30. "`ROLLBACK` releases session-level `pg_advisory_lock`."** False.

**31. "`LISTEN` works reliably over transaction pooling."** False.

**32. "`NOTIFY` cannot work in transaction pooling because `LISTEN` doesn't."** They are distinct; `NOTIFY` works fine.

**33. "`CURSOR WITH HOLD` doesn't need the same session after `COMMIT`."** False.

**34. "A failed transaction can keep running `SELECT`s if exceptions are ignored."** False; rollback is required (`25P02`).

**35. "Return a connection to the pool even if `rollback()` fails."** Dangerous; evict connections when state is uncertain.

**36. "A prepared statement created on one backend can always `EXECUTE` on another."** False without pooler protocol remapping.

**37. "`SQLSTATE 26000` and `42P05` are the same error."** False. One is missing statement name; the other is duplicate name.

**38. "All custom GUCs are tracked automatically by PgBouncer."** False; depends on version, protocol reporting, and config.

**39. "`search_path` is tenant authorization."** False.

**40. "Unqualified prepared statements always keep referencing the exact same object regardless of DDL/`search_path`."** False; conditional reparse/replan rules apply.

**41. "A larger pool always boosts throughput."** False once the database saturates.

**42. "Switching pool modes needs no driver-version testing."** False.

**43. "`idle in transaction` has no impact on the database."** False; holds locks/snapshots and causes bloat/contention.

**44. "Application pools and PgBouncer are always the same kind of pool."** False. Two layers have different lifetimes and reset points.

**45. "Every error after switching pool mode means the database is slow."** False; many are session-state contract mismatches.

---

## 36. Practice Exercises With Solutions

### Exercise 1 — Logical Close

**Question:** Does `Connection.close()` in HikariCP automatically terminate the PostgreSQL backend session?

**Answer:** No. It normally returns the logical connection to the pool while the physical session stays alive for reuse.

### Exercise 2 — Scope of `SET`

```sql
BEGIN;
SET TimeZone = 'UTC';
COMMIT;
```

**Question:** Does the session keep UTC after `COMMIT`?

**Answer:** Yes, per `SET` semantics when the transaction containing `SET` commits.

### Exercise 3 — `SET LOCAL`

```sql
BEGIN;
SET LOCAL TimeZone = 'UTC';
COMMIT;
```

**Answer:** The `LOCAL` setting expires when the transaction ends; the session reverts to its pre-`LOCAL` value.

### Exercise 4 — Request Context

**Task:** Set tenant context for one transaction only.

```sql
BEGIN;
SET LOCAL app.tenant_id = '10';
SELECT current_setting('app.tenant_id');
COMMIT;
```

### Exercise 5 — `SET LOCAL` in JDBC

**Question:** Why must `setAutoCommit(false)` be called before setting local context and running `SELECT`?

**Answer:** So `SET LOCAL` and `SELECT` share one transaction; autocommit ends the local scope right after the first statement.

### Exercise 6 — GUCs and Security

**Question:** Can `current_setting('app.tenant_id')` serve as proof of tenant authorization?

**Answer:** No, if clients/roles can arbitrarily `SET` values. Proper authentication, authorization, and database policies are required.

### Exercise 7 — Default Temp `ON COMMIT`

**Answer:** PostgreSQL defaults temporary tables to `ON COMMIT PRESERVE ROWS` when unspecified.

### Exercise 8 — `ON COMMIT DELETE ROWS`

**Question:** After `COMMIT`, does the table still exist?

**Answer:** Yes, the table object remains while its rows are cleared per `DELETE ROWS` semantics.

### Exercise 9 — `ON COMMIT DROP`

**Question:** After `COMMIT`, does the table still exist?

**Answer:** No, the table has been dropped.

### Exercise 10 — Temp Tables Under Transaction Pooling

**Task:** Create and use a temp table inside one transaction.

```sql
BEGIN;
CREATE TEMP TABLE tmp_lab (id bigint) ON COMMIT DROP;
INSERT INTO tmp_lab VALUES (1);
SELECT * FROM tmp_lab;
COMMIT;
```

### Exercise 11 — Temp Tables Across Transaction Boundaries

**Question:** Can a `PRESERVE ROWS` temp table from transaction 1 be relied upon in transaction 2 under PgBouncer transaction pooling?

**Answer:** No; transaction 2 can hit a different backend where the table does not exist.

### Exercise 12 — Autocommit

**Question:** Why can `CREATE TEMP TABLE ... ON COMMIT DROP` under autocommit cause the next `INSERT` to report relation-not-found?

**Answer:** The table drops immediately when the `CREATE` statement's implicit transaction commits.

### Exercise 13 — SQL `PREPARE`

```sql
PREPARE lookup_order(bigint) AS
SELECT * FROM pool_state_lab.orders WHERE order_id = $1;

EXECUTE lookup_order(1);

DEALLOCATE lookup_order;
```

**Answer:** SQL `PREPARE` creates a session object, `EXECUTE` runs it by name on that backend, and `DEALLOCATE` frees it.

### Exercise 14 — Prepared Statements Across `COMMIT`

**Question:** Does SQL `PREPARE` survive `COMMIT` on the same direct backend session?

**Answer:** Yes, until `DEALLOCATE`, session end, or an appropriate reset.

### Exercise 15 — Prepared Statements in PgBouncer Transaction Mode

**Question:** Can you run SQL `PREPARE` before `COMMIT` and `EXECUTE` in a later transaction?

**Answer:** Do not rely on it; the backend may change.

### Exercise 16 — Protocol-Level Prepared Statements

**Question:** Since PgBouncer 1.21, what conditions enable named protocol prepared statements in transaction pooling?

**Answer:** A supporting PgBouncer version, a driver using compatible protocol-level statements, non-zero `max_prepared_statements`, and matching compatibility settings.

### Exercise 17 — `max_prepared_statements` and SQL `PREPARE`

**Question:** Does setting `max_prepared_statements=100` make session-scoped SQL `PREPARE`/`EXECUTE` work across transactions?

**Answer:** No. That support covers protocol-level named statements.

### Exercise 18 — JDBC Parameter Binding

**Question:** Does `prepareThreshold=0` prevent using `PreparedStatement.setInt(...)`?

**Answer:** No. It changes pgJDBC's server-side named prepare behavior without disabling the parameter-binding API.

### Exercise 19 — `pg_prepared_statements`

```sql
SELECT name, from_sql
FROM pg_prepared_statements;
```

**Answer:** Inspects prepared statements in the current session and whether they came from SQL or protocol level.

### Exercise 20 — Duplicate Prepared Name

**Question:** What does `SQLSTATE 42P05` indicate?

**Answer:** A prepared statement with that name already exists in the session; inspect re-prepare logic, resets, and pooler state.

### Exercise 21 — Missing Prepared Name

**Question:** Where can `SQLSTATE 26000` come from?

**Answer:** `EXECUTE` or the driver referenced a statement name not prepared on the current backend or cleared by reset/deallocate.

### Exercise 22 — `RESET ALL`

**Question:** Does `RESET ALL` drop temp tables and SQL `PREPARE` statements?

**Answer:** No. It resets settings, not full session state.

### Exercise 23 — `DISCARD ALL`

**Question:** Can `DISCARD ALL` run inside an open transaction?

**Answer:** No. It is disallowed inside transaction blocks.

### Exercise 24 — `DISCARD PLANS`

**Question:** Is `DISCARD PLANS` equivalent to `DEALLOCATE ALL`?

**Answer:** No. It clears cached plans without deallocating prepared statement names.

### Exercise 25 — PgBouncer Reset Query

**Question:** Does `server_reset_query=DISCARD ALL` run by default after every commit in PgBouncer transaction pooling?

**Answer:** No. By default, reset queries apply to session pooling when server connections return after a client session ends, not after every transaction.

### Exercise 26 — Hikari + PgBouncer Session Mode

**Question:** Why could Request B still see Request A's temp table?

**Answer:** Hikari reuses the physical client connection holding the same PgBouncer/backend session; PgBouncer's `server_reset_query` has not run because the client connection never disconnected.

### Exercise 27 — Session Advisory Lock

**Question:** Does `ROLLBACK` release `pg_advisory_lock(901)`?

**Answer:** No. It is a session-level advisory lock requiring explicit unlock or session termination.

### Exercise 28 — Transaction Advisory Lock

```sql
BEGIN;
SELECT pg_advisory_xact_lock(901);
COMMIT;
```

**Answer:** The lock releases automatically at transaction end.

### Exercise 29 — `LISTEN`

**Question:** Should a long-lived `LISTEN` receiver use transaction pooling?

**Answer:** No. Use a dedicated direct connection or session pool with backend pinning and re-subscribe on reconnect.

### Exercise 30 — `NOTIFY`

**Question:** Does `NOTIFY` share the same session-lifetime constraint as `LISTEN`?

**Answer:** No. Sending `NOTIFY` works in transaction pooling; `LISTEN` subscribers need a stable session.

### Exercise 31 — `CURSOR WITH HOLD`

**Question:** Why is `FETCH` after `COMMIT` with a `WITH HOLD` cursor unsuitable for transaction pooling?

**Answer:** The cursor lives on the old backend session; the next transaction may hit a different backend.

### Exercise 32 — `25P02` Error

**Question:** After a statement fails inside a transaction, what is the standard cleanup step?

**Answer:** Capture the root error and `ROLLBACK` before reusing the connection; never continue running `SELECT`s as if nothing failed.

### Exercise 33 — `pg_backend_pid`

**Question:** Do two matching PID calls prove PgBouncer is in session pooling?

**Answer:** No. A transaction pool can pick the same backend again by chance.

### Exercise 34 — Connection Pool Sizing

**Question:** Does raising Hikari pool size from 20 to 200 always increase throughput?

**Answer:** No. Database contention on CPU, I/O, or locks can make higher backend counts slower. Measure workload, queueing, and DB latency.

### Exercise 35 — Migrating Pooling Modes

**Task:** Name four areas to audit before switching to transaction pooling.

**Answer:** (1) session `SET`/tenant GUCs/`search_path`, (2) temporary tables and `ON COMMIT`, (3) server-side prepared statement mode/driver/PgBouncer versions, (4) session locks/`LISTEN`/cursors. Also review migrations, transaction durations, and cleanup.

### Exercise 36 — Multi-Step Temp Table Solution

**Scenario:** Need `CREATE TEMP → INSERT → SELECT` in one unit of work.

**Answer:** Place everything inside one transaction, use `ON COMMIT DROP`, and use a pooling mode supporting multi-statement transactions.

### Exercise 37 — Connection Init

**Question:** Why should you not set `connectionInitSql=SET app.tenant_id='10'` in a multi-tenant system?

**Answer:** It sets baseline state only when a physical connection initializes, does not update tenant context per request, and risks cross-tenant leaks.

### Exercise 38 — Testing Compatibility

**Task:** Design a test for PgBouncer transaction pooling with a driver using named prepares.

**Answer:** Use multiple concurrent client connections running many short transactions interleaving parameterized queries; record `pg_backend_pid()` to confirm backend reassignment occurs across runs, watch for `SQLSTATE 26000`/`42P05`, verify `max_prepared_statements` and driver `prepareThreshold`, and assert correct query results. Never conclude from a single run with an unchanged PID.

---

## 37. Checklist for PostgreSQL Applications Using Pools

### Connection / Transaction Contract

1. Verify whether borrowing/returning a **logical** connection opens a fresh physical session.
2. When using PgBouncer, know the actual **`pool_mode`**.
3. Know the PgBouncer endpoint and version.
4. Count total physical connections across all service instances.
5. Never return a connection with an uncommitted/un-rolled-back transaction.
6. Handle rollback failures with proper connection eviction.
7. Configure timeouts and monitor checkout latency.

### GUCs and Security

8. Never use session-level `SET` for per-request context without guaranteed resets.
9. Use `SET LOCAL` inside a real transaction where appropriate.
10. Verify `set_config(..., true)` runs before queries needing the context.
11. Never treat custom GUCs as authentication or authorization.
12. Test RLS, `SECURITY DEFINER`, and `search_path` using the real application role.
13. Know which GUCs your PgBouncer version/config actually tracks.
14. Never assume pools automatically reset all custom SQL `SET` commands.
15. Separate migration/admin roles from runtime roles.

### Temporary Tables

16. Remember PostgreSQL defaults to `ON COMMIT PRESERVE ROWS`.
17. For transaction lifetime, specify `ON COMMIT DROP`.
18. Never create `ON COMMIT DROP` tables under autocommit across separate statements.
19. Never rely on `PRESERVE`/`DELETE ROWS` under transaction pooling.
20. Prefer CTEs/`VALUES`/`unnest` when temp tables are unnecessary.
21. Never let temp tables shadow trusted permanent relations via `search_path`.
22. Enforce session cleanup/retention when using session pooling.

### Prepared Statements

23. Distinguish SQL `PREPARE` from JDBC `PreparedStatement`.
24. Distinguish protocol-level named prepares from SQL `PREPARE`.
25. Verify pgJDBC `prepareThreshold` and driver version.
26. For PgBouncer transaction pools, verify `max_prepared_statements` and feature support.
27. Never assume SQL `PREPARE` across commits is remapped automatically.
28. Never trigger unexpected `DISCARD`/`DEALLOCATE` that desyncs driver caches.
29. Monitor `SQLSTATE 26000`, `42P05`, and schema migration errors.
30. Never mistake prepared statements for `SELECT` result caches.

### Other Session State

31. Never hold session advisory locks in a transaction pool.
32. Prefer `pg_advisory_xact_lock` for transaction-scoped locks.
33. Isolate long-lived `LISTEN` receivers.
34. Never use `WITH HOLD` cursors over a transaction pool.
35. Close `ResultSet`s and cursors before returning connections.
36. Monitor `idle in transaction` sessions.

### Operations

37. Know the differences among `RESET ALL`, `DEALLOCATE ALL`, `DISCARD TEMP`, and `DISCARD ALL`.
38. Never execute `DISCARD ALL` inside a transaction.
39. Never assume `server_reset_query` runs in every pool mode.
40. Test reset behavior across both the app pool and PgBouncer.
41. Test multiple concurrent clients, backend reassignment, retries, and failovers.
42. Keep a runbook to fall back to session/direct endpoints if incompatible features surface.
43. Measure actual query latency, queue waits, server backends, and resource usage.
44. Never use pool sizing as a substitute for fixing slow SQL or long lock-holding transactions.

---

## 38. Conclusion: Session-Scoped Resources Must Be Treated as Session State

The distinction among **logical request**, **database transaction**, and **physical PostgreSQL session** determines whether a feature works cleanly behind a connection pool.

**Remember five core rules:**

1. **Never assume logical connection `close()` closes the physical session.** HikariCP and application pools reuse connections.
2. **Use transaction scope for per-request state.** `SET LOCAL`, `ON COMMIT DROP`, and transaction advisory locks minimize leftover state—provided transaction boundaries are right.
3. **Transaction pooling does not guarantee session pinning across `COMMIT`.** `PRESERVE`/`DELETE ROWS` temp tables, SQL `PREPARE`, `LISTEN`, session advisory locks, and `WITH HOLD` cursors cannot span transactions as on direct connections.
4. **Prepared statements come in multiple forms.** PgBouncer 1.21+ conditionally supports **protocol-level named prepared statements** with non-zero `max_prepared_statements`; this does not make SQL `PREPARE`/`EXECUTE` session-independent.
5. **Resets must account for driver and pooler state.** `RESET ALL` is not `DISCARD ALL`, `DISCARD PLANS` is not `DEALLOCATE ALL`, and server-side resets can desync client-side prepare caches.

A pragmatic design rule:

```text
Does a request need temporary state?
             |
             v
Can it be expressed inside one single transaction?
         /                         \
       Yes                          No
       |                             |
       v                             v
  SET LOCAL, TEMP               Does it truly need session
  ON COMMIT DROP,               state across commits?
  xact locks                     /               \
       |                       Yes                No
       v                        |                  |
Transaction pooling             v                  v
  can work when           Session/direct      Refactor to
  driver is compatible    connection pool     transactional /
                          with cleanups       persistent state
```

**Final self-check question:** When Request A returns its JDBC `Connection`, which data was **committed to business tables**, which state **ended with the transaction**, and which objects **still remain inside the PostgreSQL backend session**? Only when your application, pool, and PgBouncer share one clear answer to all three questions can connection reuse be trusted as safe and correct.

### Official Documentation and References

- [PostgreSQL — SET (SESSION and LOCAL)](https://www.postgresql.org/docs/current/sql-set.html).
- [PostgreSQL — RESET](https://www.postgresql.org/docs/current/sql-reset.html).
- [PostgreSQL — DISCARD](https://www.postgresql.org/docs/current/sql-discard.html).
- [PostgreSQL — CREATE TABLE (Temporary tables and ON COMMIT)](https://www.postgresql.org/docs/current/sql-createtable.html).
- [PostgreSQL — PREPARE](https://www.postgresql.org/docs/current/sql-prepare.html).
- [PostgreSQL — EXECUTE](https://www.postgresql.org/docs/current/sql-execute.html).
- [PostgreSQL — DEALLOCATE](https://www.postgresql.org/docs/current/sql-deallocate.html).
- [PostgreSQL — pg_prepared_statements](https://www.postgresql.org/docs/current/view-pg-prepared-statements.html).
- [PostgreSQL — Session information functions](https://www.postgresql.org/docs/current/functions-info.html).
- [PostgreSQL — Advisory locks](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS).
- [PostgreSQL — LISTEN](https://www.postgresql.org/docs/current/sql-listen.html).
- [PostgreSQL — NOTIFY](https://www.postgresql.org/docs/current/sql-notify.html).
- [PostgreSQL — DECLARE cursor](https://www.postgresql.org/docs/current/sql-declare.html).
- [PostgreSQL — pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html).
- [PostgreSQL — Row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).
- [PgBouncer — Pooling Modes and Feature Compatibility](https://www.pgbouncer.org/features.html).
- [PgBouncer — Configuration: pool_mode, max_prepared_statements, server_reset_query](https://www.pgbouncer.org/config.html).
- [PgBouncer — FAQ: JDBC prepared statement compatibility](https://www.pgbouncer.org/faq.html).
- [PgBouncer — Administrative Console](https://www.pgbouncer.org/usage.html).
- [pgJDBC — Connection Parameters](https://jdbc.postgresql.org/documentation/use/).
