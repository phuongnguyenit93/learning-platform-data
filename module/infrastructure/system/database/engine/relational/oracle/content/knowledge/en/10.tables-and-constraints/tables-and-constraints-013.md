# Global and Private Temporary Tables, Data Lifecycle, and Version Requirements

In an order-processing workflow, an application may need to **gather an intermediate dataset**, filter it repeatedly, compute totals, and write the final result into business tables. That working dataset does not need to survive after the transaction or session ends. Oracle Database provides **global temporary tables (GTT)** and, in newer releases, **private temporary tables (PTT)** to address such needs.

Both table types are easily misunderstood: *global* does **not** mean every user sees the same rows, and *private* does **not** merely mean a table created in a private schema. The core difference lies in **the persistence scope of the table definition** and **the lifecycle of temporary rows**, especially around `COMMIT`, `ROLLBACK`, and connection pools.

After this lesson, you will be able to:

1. Distinguish permanent tables, GTTs, and PTTs by metadata, data, and session scope.
2. Use `ON COMMIT DELETE ROWS` and `ON COMMIT PRESERVE ROWS` properly on GTTs.
3. Use `ON COMMIT DROP DEFINITION` and `ON COMMIT PRESERVE DEFINITION` on PTTs in supporting releases.
4. Predict outcomes across `COMMIT`, `ROLLBACK`, session termination, and JDBC connection reuse.
5. Check Oracle version, table naming prefixes, and metadata before running code that depends on PTTs.

**Practice Scope:** `CREATE`, `INSERT`, and `DROP` commands in this lesson are intended only for a practice schema/PDB with appropriate privileges. Never run illustrative DDL directly in production databases.

## 1. What Are Temporary Tables Used For?

A typical scenario:

~~~mermaid
flowchart LR
    A["Source data"] --> B["Intermediate dataset for request/batch"]
    B --> C["Multi-step filtering / JOIN / aggregation"]
    C --> D["Write finalized results"]
    B --> E["Temporary data cleaned per transaction/session"]
~~~

For example, a pricing batch:

- Step 1 collects eligible `ORDER_ID`s across multiple tables.
- Step 2 attaches discount rates and validation flags.
- Step 3 computes totals and filters out invalid records.
- Step 4 updates business tables or exports a report.

When the same intermediate set is referenced across **multiple SQL statements**, a temporary table can be cleaner than repeating a huge query. Still, not every problem needs a temporary table: `WITH` CTEs, inline views, or a single `INSERT ... SELECT` can be simpler. Temporary tables are a design choice, not an automatic speedup trick.

### 1.1 Two Layers to Keep Separate

Ask yourself:

**Definition layer (metadata):** Do the table name, columns, and structure still exist after the session closes?

**Data layer (rows):** Are rows inserted by one session still visible after `COMMIT`, `ROLLBACK`, or session termination?

These are two **independent** axes. A GTT keeps its definition across sessions while discarding data quickly. A PTT can automatically drop **even its definition** at transaction or session end.

## 2. Quick Comparison: Permanent Tables, GTTs, and PTTs

| Attribute | Permanent Table | Global Temporary Table (GTT) | Private Temporary Table (PTT) |
|---|---|---|---|
| Creation command | `CREATE TABLE` | `CREATE GLOBAL TEMPORARY TABLE` | `CREATE PRIVATE TEMPORARY TABLE` |
| Definition after creating session closes | Persists | **Persists** | **Automatically disappears** per chosen scope |
| Who can see the definition? | Authorized sessions | Authorized sessions within the database/PDB | **Only the session that created the PTT** |
| Are rows shared across sessions? | Per privileges and transaction isolation | **No**: each session sees only its own temporary rows | **No**: other sessions see neither table nor rows |
| Data lifecycle | Until changed by DML/DDL | End of transaction or session, per `ON COMMIT` | Same transaction/session scope as PTT definition |
| `ON COMMIT` clause | Not applicable to this temp model | `DELETE ROWS` / `PRESERVE ROWS` | `DROP DEFINITION` / `PRESERVE DEFINITION` |
| Version requirement | Long-standing core feature | Available in older Oracle releases, including 11g | **Introduced in Oracle Database 18c** |
| Typical use case | Persistent business data | Reusable staging schema structure | Ad-hoc, session-private staging structure |

The word **global** emphasizes that **the GTT definition is a shared database object** within schema/privilege scope; multiple sessions reference the same `LAB_GTT_WORK` name while session A's rows never mix with session B's rows. The word **private** on a PTT means both the temporary table definition/name and its rows are confined to the creating session.

~~~mermaid
flowchart TD
    G["GTT Metadata: LAB_GTT_WORK"] --> A["Session A: temp data A"]
    G --> B["Session B: temp data B"]
    A -. "Rows never shared" .- B
    C["Session C creates ORA$PTT_WORK"] --> D["PTT metadata + data visible only in C"]
    E["Session D"] -. "Cannot see C's PTT" .-> D
~~~

## 3. Global Temporary Tables: Persistent Definition, Temporary Rows

A GTT is created once in an authorized schema, just like a regular database object with persistent metadata. When a session runs `INSERT`, Oracle allocates temporary space for that session/transaction. Other sessions share **the same definition** yet cannot read rows inserted by the first session.

Two modes exist:

| GTT Mode | Per-Session Row Lifecycle | When Appropriate? |
|---|---|---|
| `ON COMMIT DELETE ROWS` | Rows are cleared/truncated when the transaction ends—specifically on `COMMIT`; `ROLLBACK` also reverts transaction rows | Staging needed only within **a single transaction** |
| `ON COMMIT PRESERVE ROWS` | Rows survive `COMMIT` within **the same session**, cleared when the session ends or explicitly truncated/deleted | Staging needed across **multiple transactions** in one session |

Omitting `ON COMMIT` on a GTT defaults to **`DELETE ROWS`**. In practice and lessons, write it explicitly so readers never have to guess.

### 3.1 Transaction-Scoped GTT: ON COMMIT DELETE ROWS

Create a practice table in a schema with `CREATE TABLE` privilege:

~~~sql
CREATE GLOBAL TEMPORARY TABLE lab_gtt_tx (
    batch_id   NUMBER(10),
    item_id    NUMBER(10),
    amount     NUMBER(12,2)
)
ON COMMIT DELETE ROWS;
~~~

**Create the table only once.** Then, on the **same connection**:

~~~sql
INSERT INTO lab_gtt_tx (batch_id, item_id, amount)
VALUES (1, 101, 50000);

INSERT INTO lab_gtt_tx (batch_id, item_id, amount)
VALUES (1, 102, 70000);

SELECT COUNT(*) AS rows_before_commit,
       SUM(amount) AS total_amount
FROM lab_gtt_tx;
~~~

Provided autocommit is off, the query before `COMMIT` returns 2 rows totaling 120,000:

~~~text
ROWS_BEFORE_COMMIT   TOTAL_AMOUNT
------------------   ------------
2                    120000
~~~

End the transaction:

~~~sql
COMMIT;

SELECT COUNT(*) AS rows_after_commit
FROM lab_gtt_tx;
~~~

Result: `ROWS_AFTER_COMMIT = 0`. **Table `LAB_GTT_TX` still exists**; only this session's transaction data was cleared. You can start the next transaction and `INSERT` again without recreating the GTT.

**Autocommit warning:** If your SQL client auto-commits immediately after each `INSERT`, rows in a `DELETE ROWS` GTT vanish before your next `SELECT` runs. Use explicit transaction control for this exercise.

### 3.2 Session-Scoped GTT: ON COMMIT PRESERVE ROWS

Create another table:

~~~sql
CREATE GLOBAL TEMPORARY TABLE lab_gtt_session (
    batch_id   NUMBER(10),
    item_id    NUMBER(10),
    amount     NUMBER(12,2)
)
ON COMMIT PRESERVE ROWS;
~~~

Run:

~~~sql
INSERT INTO lab_gtt_session (batch_id, item_id, amount)
VALUES (2, 201, 30000);

COMMIT;

SELECT COUNT(*) AS rows_after_commit
FROM lab_gtt_session;
~~~

Within the same session, `ROWS_AFTER_COMMIT` remains `1`. If you start another transaction and insert more rows, previously committed rows persist in **this session**.

Now completely close the session and open a fresh session to the same PDB/schema:

~~~sql
SELECT COUNT(*) AS rows_new_session
FROM lab_gtt_session;
~~~

The new session can still query the **`LAB_GTT_SESSION` definition** if granted access, yet its temporary dataset **starts empty**. The previous session's rows are never kept as permanent business data.

### 3.3 How Does ROLLBACK Behave?

`ROLLBACK` undoes uncommitted DML, including on temporary tables. For example, on a `PRESERVE ROWS` GTT:

~~~sql
-- Assume the current session already has 1 COMMITted row.
INSERT INTO lab_gtt_session (batch_id, item_id, amount)
VALUES (2, 202, 40000);

SELECT COUNT(*) AS before_rollback
FROM lab_gtt_session;

ROLLBACK;

SELECT COUNT(*) AS after_rollback
FROM lab_gtt_session;
~~~

The uncommitted `ITEM_ID = 202` row is rolled back, while the earlier committed `ITEM_ID = 201` row remains in the session. On a `DELETE ROWS` GTT, transaction-scoped rows disappear at transaction end; never use it to persist state across transactions.

**Do not confuse two facts:** `COMMIT` does not make `PRESERVE ROWS` data survive past session end; `ROLLBACK` does not erase **already-committed** rows from earlier transactions in a `PRESERVE ROWS` GTT.

## 4. Two Sessions Share the Same GTT Without Mixing Rows

Suppose `LAB_GTT_SESSION` exists and two users open **two separate physical database sessions** to the same PDB:

| Step | Session A | Session B |
|---|---|---|
| 1 | `INSERT` row with `ITEM_ID = 1001` | Nothing inserted |
| 2 | `COMMIT` | `SELECT COUNT(*)` from GTT → 0 |
| 3 | `SELECT` from GTT → sees row 1001 | `INSERT` row with `ITEM_ID = 2001` |
| 4 | `SELECT` → still sees only row 1001 | `COMMIT`, `SELECT` → sees only row 2001 |
| 5 | Close session | Still sees row 2001 in Session B |

Both reference **`LAB_GTT_SESSION`**, yet Oracle maintains isolated temporary data per session. When Session A closes, A's temporary data disappears while the GTT definition remains in the schema and Session B keeps its own rows.

This is **not** row-level security or partitioning by `USER_ID`. Row isolation is built directly into Oracle's session/transaction architecture. Conversely, if two HTTP requests share **the same physical database session recycled by a connection pool**, request B can see leftover `PRESERVE ROWS` data from request A unless the application cleans up.

### 4.1 Be Careful with DDL on GTTs

Because a GTT definition is a shared object, create it once during schema deployment rather than running `CREATE GLOBAL TEMPORARY TABLE` on every HTTP request. The GTT stays until an authorized `DROP TABLE` runs.

Oracle restricts altering or dropping a GTT while any session holds a binding to it (having used the GTT). Commands like `ALTER TABLE`, `DROP TABLE`, or `CREATE INDEX` fail with errors such as `ORA-14452: attempt to create, alter or drop an index on temporary table already in use`. Wait for sessions to finish/release bindings and coordinate maintenance windows rather than modifying live production GTT structures.

With `PRESERVE ROWS` GTTs, clearing rows and releasing bindings may involve `TRUNCATE` inside the owning session; always understand transaction and release behavior before running cleanup DDL.

## 5. Private Temporary Tables: Both Definition and Rows Are Temporary

**Private temporary tables** were introduced in **Oracle Database 18c**. A session creates its own PTT name, uses it for temporary work, and lets Oracle automatically drop the table at the declared boundary. Other sessions cannot see the PTT **definition**, even if two sessions create PTTs with the same name.

In environments supporting PTTs, table names must begin with the `PRIVATE_TEMP_TABLE_PREFIX` parameter value. The default is `ORA$PTT_`, e.g., `ORA$PTT_STAGE_TX` or `ORA$PTT_STAGE_SESSION`.

If privileged to read system parameters:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'private_temp_table_prefix';
~~~

Examples below assume the default prefix `ORA$PTT_`. If your database configures a different prefix, **adjust the example table names accordingly**; never assume `ORA$PTT_` works blindly everywhere.

### 5.1 Transaction-Scoped PTT: ON COMMIT DROP DEFINITION

In a practice schema/PDB on Oracle 18c+:

~~~sql
CREATE PRIVATE TEMPORARY TABLE ora$ptt_stage_tx (
    item_id   NUMBER(10),
    amount    NUMBER(12,2)
)
ON COMMIT DROP DEFINITION;
~~~

This is the **default** PTT mode if `ON COMMIT` is omitted. Both the PTT definition and rows are transaction-scoped. After creation, **before commit**:

~~~sql
INSERT INTO ora$ptt_stage_tx (item_id, amount)
VALUES (501, 100000);

SELECT COUNT(*) AS rows_before_commit
FROM ora$ptt_stage_tx;
~~~

Expected result: 1 row. When you run:

~~~sql
COMMIT;
~~~

Oracle drops **both the contents and the definition** of `ORA$PTT_STAGE_TX`. Trying afterward:

~~~sql
-- Illustrative query that fails because the PTT was auto-dropped.
SELECT * FROM ora$ptt_stage_tx;
~~~

raises `ORA-00942: table or view does not exist`. This is expected for `ON COMMIT DROP DEFINITION`, **differing from a `DELETE ROWS` GTT**: the GTT table stays around for more `INSERT`s, whereas this PTT must be recreated in the next transaction.

**Crucial transaction detail:** Under Oracle rules for transaction-specific PTTs, `CREATE PRIVATE TEMPORARY TABLE ... ON COMMIT DROP DEFINITION` **does not perform an implicit commit** and can execute inside an open transaction. Manage transaction boundaries carefully and disable autocommit if you need the table across multiple statements before committing.

### 5.2 Session-Scoped PTT: ON COMMIT PRESERVE DEFINITION

Create a session-scoped PTT:

~~~sql
CREATE PRIVATE TEMPORARY TABLE ora$ptt_stage_session (
    item_id   NUMBER(10),
    amount    NUMBER(12,2)
)
ON COMMIT PRESERVE DEFINITION;
~~~

Then:

~~~sql
INSERT INTO ora$ptt_stage_session (item_id, amount)
VALUES (601, 210000);

COMMIT;

SELECT COUNT(*) AS rows_after_commit
FROM ora$ptt_stage_session;
~~~

Within **the same session**, the table remains and committed rows stay readable, yielding 1. When **the session terminates**, both the definition and rows are cleaned up. If you open a new physical connection and `SELECT` that name without recreating the PTT in the new session, Oracle reports the table does not exist.

**Key DDL difference:** Per the Oracle SQL Language Reference, **creating a PTT with `ON COMMIT PRESERVE DEFINITION` performs an implicit commit**, whereas creating one with `ON COMMIT DROP DEFINITION` does not. Therefore, never create a `PRESERVE DEFINITION` PTT mid-way through an open business transaction without accounting for the implicit commit.

### 5.3 Manually Dropping a PTT

To explicitly release a PTT inside the **owning session** before it expires automatically:

~~~sql
DROP TABLE ora$ptt_stage_session;
~~~

This works only while the table still exists in the current session; you cannot run it from another session to drop the original session's PTT. Supported DDL on PTTs is much more restricted than on regular tables; in Oracle 19c, allowed DDL on PTTs is essentially `CREATE`, `DROP`, and `TRUNCATE`.

## 6. The Four Lifecycle Modes: Most Important Summary Table

| Type and Declaration | On `COMMIT` | After Closing Session | Does Definition Exist for Other Sessions? |
|---|---|---|---|
| GTT `ON COMMIT DELETE ROWS` | **Rows disappear**, GTT remains | GTT remains; session's rows cleared | **Yes**, if granted privileges |
| GTT `ON COMMIT PRESERVE ROWS` | **Rows persist** in session | GTT remains; session's rows cleared | **Yes**, if granted privileges |
| PTT `ON COMMIT DROP DEFINITION` | **Both table and rows disappear** | Gone | **No** |
| PTT `ON COMMIT PRESERVE DEFINITION` | **Both table and rows persist** in session | **Both table and rows disappear** | **No** |

The two "survive commit" modes are easy to confuse:

- GTT `PRESERVE ROWS` preserves **rows** across commits; the GTT definition is already permanent.
- PTT `PRESERVE DEFINITION` preserves **both the PTT definition and the session's rows** across commits; both vanish when the session ends.

The two "transaction-only" modes also differ:

- GTT `DELETE ROWS` clears **rows**, leaving the table reusable.
- PTT `DROP DEFINITION` clears **both definition and rows**, requiring `CREATE` again next time.

### 6.1 Lifecycle Timeline Diagram

~~~mermaid
sequenceDiagram
    participant S as Oracle session
    participant GT as GTT DELETE ROWS
    participant GS as GTT PRESERVE ROWS
    participant PT as PTT DROP DEFINITION
    participant PS as PTT PRESERVE DEFINITION
    S->>GT: INSERT 1 row
    S->>GS: INSERT 1 row
    S->>PT: CREATE + INSERT 1 row
    S->>PS: CREATE + INSERT 1 row
    Note over S,PS: Conceptual comparison; creating PTT PRESERVE commits implicitly, so do not chain in this exact order
    S->>S: COMMIT
    GT-->>S: 0 rows; definition remains
    GS-->>S: 1 row; definition remains
    PT-->>S: Table gone
    PS-->>S: 1 row; definition remains in session
    S->>S: Close session
    GS-->>S: Session data cleared
    PS-->>S: Data + definition cleared
~~~

**Read the diagram as a side-by-side comparison**, not as a single script creating all four tables sequentially. Creating a `PRESERVE DEFINITION` PTT performs an implicit commit, which alters any active transaction-scoped temporary tables in the same transaction.

## 7. Impact of COMMIT, ROLLBACK, Autocommit, and Transactions

### 7.1 COMMIT Is Not Just a "Side Event"

For permanent business data, `COMMIT` persists transaction changes. For temporary tables, `COMMIT` **is also a lifecycle boundary** governed by `ON COMMIT`.

Typical workflow:

~~~text
BEGIN TRANSACTION
    INSERT into transaction-scoped temp table
    SELECT/JOIN/compute results from temp table
    INSERT/UPDATE target business tables
COMMIT
    Transaction-scoped temp table is cleared per rules
~~~

Moving `COMMIT` right after inserting into the temp table causes the subsequent query to see **0 rows** or **no table at all**, depending on GTT vs. PTT. Commit placement is part of workflow design.

### 7.2 ROLLBACK Is Not "Close Session"

`ROLLBACK` reverts uncommitted DML in the current transaction. On a `PRESERVE ROWS` GTT, it does not delete rows committed in earlier transactions of the same session. On a transaction-specific GTT, transaction rows clear when the transaction ends.

With a `DROP DEFINITION` PTT, table scope is the transaction; once the transaction ends, neither definition nor rows are available in subsequent transactions. Whenever distinguishing rollback vs. DDL behavior on a specific release, test in a dedicated schema with clear transaction markers and consult that release's Oracle docs.

### 7.3 JDBC Autocommit Can Wipe Temp Tables Before Reading

In JDBC, a `Connection` typically defaults to `autoCommit = true` unless configured otherwise. Each DML statement becomes its own auto-committed transaction: on a `DELETE ROWS` GTT, newly inserted rows vanish right after the statement; on a `DROP DEFINITION` PTT, the table drops at transaction end.

Pitfall code:

~~~java
// Illustrates the risk when autoCommit=true.
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO lab_gtt_tx (batch_id, item_id, amount) VALUES (?, ?, ?)")) {
    ps.setLong(1, 9L);
    ps.setLong(2, 901L);
    ps.setBigDecimal(3, new java.math.BigDecimal("1000"));
    ps.executeUpdate(); // May auto-commit right after the statement.
}

// A SELECT in the same session may see 0 rows in a DELETE ROWS GTT.
~~~

To run multiple SQL statements against a transaction-scoped temporary table, all of them must share **the same connection** and the same uncommitted transaction:

~~~java
boolean oldAutoCommit = connection.getAutoCommit();
connection.setAutoCommit(false);

try {
    // 1. INSERT into transaction-scoped GTT.
    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO lab_gtt_tx (batch_id, item_id, amount) VALUES (?, ?, ?)")) {
        ps.setLong(1, 9L);
        ps.setLong(2, 902L);
        ps.setBigDecimal(3, new java.math.BigDecimal("2000"));
        ps.executeUpdate();
    }

    // 2. Read temp table before COMMIT on the exact same connection.
    try (PreparedStatement ps = connection.prepareStatement(
            "SELECT COUNT(*) FROM lab_gtt_tx");
         ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            long count = rs.getLong(1);
            System.out.println(count);
        }
    }

    // 3. End transaction only after all business steps finish.
    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
} finally {
    connection.setAutoCommit(oldAutoCommit);
}
~~~

This snippet assumes a valid `Connection`, JDBC imports, and privileges on the GTT. It demonstrates direct transaction management and **should not be copied verbatim into Spring code controlled by a transaction manager**; in Spring, keep the whole DML/SELECT sequence inside one managed transaction boundary sharing the same physical connection.

Restoring `autoCommit` can interact with transaction state per JDBC rules; only restore it after cleanly committing or rolling back so connections never return to the pool with dangling transactions.

## 8. Connection Pools: Does "Closing a Connection" End the Session?

In Java/Spring apps, calling `connection.close()` usually returns a **logical** connection to the connection pool rather than closing the underlying physical database session. One Oracle session can outlive thousands of HTTP requests.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant P as JDBC connection pool
    participant O as Physical Oracle session
    participant B as Request B
    A->>P: Borrow connection
    P->>O: SELECT/INSERT into GTT PRESERVE ROWS
    A->>O: COMMIT
    A->>P: close() -> return connection
    B->>P: Borrow same physical connection
    B->>O: SELECT GTT PRESERVE ROWS
    O-->>B: May still see rows from A
~~~

With a `PRESERVE ROWS` GTT, committed rows **remain inside the physical session**, so Request B can see Request A's leftover staging rows unless the pool resets session state or the app clears them. This causes **wrong results or cross-request data leaks** within the shared session.

A `PRESERVE DEFINITION` PTT is likewise scoped to the physical session. If the pool keeps the session alive, the PTT lingers after Request A finishes. By contrast, `DELETE ROWS` GTTs and `DROP DEFINITION` PTTs fit single-transaction workflows under tight commit control.

Safe practices:

1. **Prefer transaction-scoped temp tables** when intermediate data lives within one controlled transaction.
2. When using session-scoped temp tables, **explicitly clear data or drop the PTT** before returning the connection to the pool; never assume `close()` ends the Oracle session.
3. Ensure all SQL steps for a task use **the same connection**; borrowing another connection from the pool misses the first connection's temporary rows.
4. Never use GTTs/PTTs for cross-request persistence, cross-session sharing, or crash recovery.
5. For sensitive data, enforce explicit cleanup and timeouts rather than relying on physical session teardown.

If data must persist across separate requests **regardless of which pooled connection serves them**, session-scoped temp tables are the wrong storage. Use a permanent table keyed by `JOB_ID`/`REQUEST_ID` with proper access control and cleanup jobs.

## 9. Definition Lifecycle: When to CREATE or DROP?

| Task | GTT | PTT |
|---|---|---|
| Deploy table definition via migration/schema | **Usually created once** | Not required: can be created in-session on demand |
| Create on every request | Generally **wrong**, since metadata persists and names collide | Acceptable if version and transaction/session lifecycle are managed |
| Two sessions use the same table name | Share definition, separate data | Each session has its own private definition |
| Need to alter table schema | `ALTER`/`DROP` when no sessions are bound, per privileges | Supported DDL is limited; typically drop and recreate in-session |
| Session terminates | GTT definition persists | PTT definition vanishes |
| Application restarts | GTT needs no recreation if object exists | New session must recreate PTT before use |

Common deployment bug:

~~~sql
-- Do not run this on every HTTP request:
CREATE GLOBAL TEMPORARY TABLE lab_gtt_tx (
    id NUMBER
) ON COMMIT DELETE ROWS;
~~~

After the first run, the GTT definition already exists; subsequent runs fail with object-exists errors such as `ORA-00955`. For GTTs, **create once in schema migrations**, and let each transaction perform only DML against its private rows.

For PTTs, creating per session or transaction can be part of the workflow. Remember, creating an `ON COMMIT PRESERVE DEFINITION` PTT commits implicitly; never invoke it accidentally inside an open business transaction holding uncommitted DML.

## 10. Version Requirements and PTT-Specific Restrictions

### 10.1 PTTs Require Oracle 18c or Later

GTTs have existed in Oracle for decades. PTTs were introduced in **Oracle Database 18c**; environments on **Oracle 11g, 12.1, or 12.2** do not support `CREATE PRIVATE TEMPORARY TABLE`. You cannot simply swap one keyword to turn a PTT into a GTT on older versions, because their metadata lifecycles differ.

Before choosing PTTs, verify the **Oracle Database server** version, not just your client tool version:

~~~sql
SELECT banner
FROM v$version;
~~~

Or, if privileged:

~~~sql
SELECT instance_name, version
FROM v$instance;
~~~

In CDB/PDB environments, verify the active container too:

~~~sql
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS current_container,
       SYS_CONTEXT('USERENV','SERVICE_NAME') AS current_service
FROM dual;
~~~

If you lack privileges on `V$VERSION` or `V$INSTANCE`, ask your DBA to confirm server release; never assume a modern SQL Developer client implies server support for PTTs.

### 10.2 PTTs Must Follow the Prefix Parameter

`PRIVATE_TEMP_TABLE_PREFIX` defaults to `ORA$PTT_`. Thus:

~~~sql
-- Valid with the default prefix:
CREATE PRIVATE TEMPORARY TABLE ora$ptt_demo (
    id NUMBER
) ON COMMIT DROP DEFINITION;
~~~

Do not name a PTT `LAB_TEMP` while the default prefix is `ORA$PTT_`. If your PDB/database configures another prefix, match the active setting. The `$` character in the prefix is standard Oracle syntax—do not confuse the prefix with a schema name.

### 10.3 Key Restrictions in Oracle 19c

Per the Oracle 19c SQL Language Reference, beyond general temporary-table restrictions, PTTs carry notable limitations:

| Requirement | Oracle 19c PTT |
|---|---|
| Creating indexes on a PTT | **Not supported** |
| Defining columns with `DEFAULT` | **Not supported** |
| Materialized views or zone maps on a PTT | **Not supported** |
| Referencing a PTT in persistent objects (views/triggers) | **Not supported** |
| Accessing a PTT over a database link | **Not supported** |
| DDL beyond `CREATE`, `DROP`, `TRUNCATE` | **Not supported** |
| Foreign keys on temporary tables | Generally restricted; **not supported** per 19c docs |

Never translate a complex GTT DDL containing indexes, constraints, or defaults into a PTT merely by changing `GLOBAL` to `PRIVATE`. When a workload requires indexes or persistent schema features, GTTs are usually a better fit; always verify exact version limits.

Do not use `SYS` to test creating PTTs; Oracle requires PTTs to be created by users other than `SYS`. Practice in an authorized schema per organizational policy.

### 10.4 Newer Releases May Adjust Specifics

Limits for PTTs/GTTs, memory/temp management, monitoring views, and syntax can evolve across Oracle 18c, 19c, 21c, 23ai, and newer releases. This lesson uses **Oracle 19c as the reference syntax**, so verify against your production release, patch level, edition, and database policies.

## 11. Inspecting Metadata: Identifying Temporary Table Types

### 11.1 GTTs in the Data Dictionary

Because GTT definitions persist in the schema, inspect them in dictionary views:

~~~sql
SELECT table_name,
       temporary,
       duration
FROM user_tables
WHERE table_name IN ('LAB_GTT_TX', 'LAB_GTT_SESSION')
ORDER BY table_name;
~~~

For GTTs, `TEMPORARY = 'Y'`, and `DURATION` shows `SYS$TRANSACTION` (transaction-scoped) or `SYS$SESSION` (session-scoped). This describes **table type**, not the current session's row count.

To inspect a GTT in another schema where permitted:

~~~sql
SELECT owner, table_name, temporary, duration
FROM all_tables
WHERE table_name = 'LAB_GTT_TX';
~~~

`ALL_TABLES` lists objects visible to your user; container scope and privileges shape results. Do not look in `USER_TABLES` for another session's PTT, because PTTs do not store shared persistent metadata like GTTs.

### 11.2 PTTs in Session-Specific Dictionary Views

On Oracle 18c+ supporting this view:

~~~sql
SELECT table_name, duration
FROM user_private_temp_tables
ORDER BY table_name;
~~~

`USER_PRIVATE_TEMP_TABLES` lists PTTs belonging to the **current session**. `DURATION` distinguishes `TRANSACTION` vs. `SESSION` scope. Once you commit a `DROP DEFINITION` PTT, it **disappears from the view** because its definition was dropped.

Administrators have `DBA_PRIVATE_TEMP_TABLES` to view PTTs within allowed scope, including session ID and instance ID depending on release. **Knowing another session's PTT name still does not let normal users read its rows.**

### 11.3 Metadata Does Not Prove Rows Exist in Your Session

~~~sql
SELECT COUNT(*) AS current_session_rows
FROM lab_gtt_session;
~~~

This returns the row count **for the current session**. `USER_TABLES` proves the GTT exists with `DURATION = SYS$SESSION`, yet cannot replace `COUNT(*)` when checking how many rows your session currently holds.

Optimizer statistics on GTTs and sessions follow special Oracle mechanisms; never interpret `NUM_ROWS` in the data dictionary as "live row count across all sessions."

## 12. GTTs and PTTs Use Temp Storage, Yet Are Not Free

Even though rows are temporary, inserting into GTTs/PTTs can allocate **temporary segments**, perform I/O, consume memory, and generate undo/redo per Oracle rules. A temporary table **is not an in-memory Java variable**, nor is it guaranteed to avoid disk I/O.

Typically, temporary table segments are allocated when a session begins populating rows; transaction-scoped segments release at transaction end, while session-scoped segments release at session end. TEMP usage depends on row volume, operations, configuration, and workload.

Design precautions:

- **TEMP tablespace is finite.** Many concurrent sessions loading large staging sets can exhaust TEMP space.
- **Never treat temporary tables as business backups.** Temporary data lacks permanent backup/recovery guarantees; never build applications assuming temp rows survive session loss or instance failure.
- **Do not assume GTTs always beat CTEs.** Speed depends on optimizer plans, access paths, indexing, I/O, and application flow.
- **Do not assume temp operations generate zero redo.** Metadata, undo, and Oracle internals still incur work; measure performance empirically rather than repeating slogans like "temporary = no logging."

Authorized DBAs can inspect `V$TEMPSEG_USAGE` to observe active temporary segment consumption per session at query time; never extrapolate a single snapshot into full-day TEMP usage history.

## 13. Common Errors and Confusing Scenarios

| Symptom | Likely Cause | What to Check |
|---|---|---|
| `DELETE ROWS` GTT returns 0 right after insert | Client/JDBC auto-committed or transaction ended | Check autocommit, `COMMIT` boundaries, and connection reuse |
| `PRESERVE ROWS` GTT still holds rows on next request | Pool reused physical session without cleanup | Check physical session, cleanup logic, and transactions |
| `DROP DEFINITION` PTT raises `ORA-00942` after commit | Table **was automatically dropped** by design | Recreate PTT in the next transaction |
| `PRESERVE DEFINITION` PTT invisible in a new session | PTT definition is **private to the creating session** | Create PTT in the new session; never expect shared metadata |
| `CREATE PRIVATE TEMPORARY TABLE` rejected | Server older than 18c, syntax error, or missing privileges | Check server version and release SQL Language Reference |
| Invalid PTT name | Missing or wrong `PRIVATE_TEMP_TABLE_PREFIX` | Check parameter value and use matching prefix |
| Creating index or column default on PTT rejected | PTT restriction in current release | Consider GTT or alternative staging design |
| `ORA-00955` when creating GTT | GTT definition already exists permanently | Create GTT once in migrations; run DML per request |
| DDL on active GTT rejected, e.g. `ORA-14452` | One or more sessions are bound to the GTT | Coordinate session completion/release; never force DROP |
| Two sessions query same GTT and get different `COUNT(*)` | Temporary data is isolated per session | Compare `SESSION_USER`, physical connection, and timing |
| Data in temp table lost on restart | Data was temporary by design | Persist durable data in regular tables with proper transactions |
| Same table name works in one PDB and errors in another | GTT/PTT definitions belong to each container/schema | Check `CON_NAME`, service, and privileges |

### 13.1 Quick Diagnostic Flowchart

~~~mermaid
flowchart TD
    A["Temp table SQL fails or returns 0 rows"] --> B{"GTT or PTT?"}
    B -->|GTT| C["Query USER_TABLES: TEMPORARY, DURATION"]
    B -->|PTT| D["Check 18c+ version, prefix, USER_PRIVATE_TEMP_TABLES"]
    C --> E{"DELETE ROWS or PRESERVE ROWS?"}
    D --> F{"DROP DEFINITION or PRESERVE DEFINITION?"}
    E --> G["Check COMMIT/ROLLBACK and physical connection"]
    F --> G
    G --> H["Match transaction and session state at failure time"]
    H --> I["Fix lifecycle or data design; never blindly escalate privileges"]
~~~

## 14. Step-by-Step Practice Lab

**Step 1 — Verify environment.** Log into your practice PDB/schema and check container and server version. If you lack system view access, ask your DBA to confirm; do not run PTT statements on servers below 18c.

~~~sql
SELECT USER AS login_user,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

**Step 2 — Test transaction-scoped GTT.** Create `LAB_GTT_TX`, disabling client autocommit if needed. `INSERT` two rows, run `SELECT COUNT(*)`, then `COMMIT` and run `SELECT COUNT(*)` again. Why is the table still queryable while its row count drops to 0?

**Step 3 — Test session-scoped GTT.** Create `LAB_GTT_SESSION`, insert, and commit. Run `SELECT COUNT(*)` on the same connection, then read from a **new connection**. Why do the two connections return different counts despite sharing the schema?

**Step 4 — Test rollback.** On the `PRESERVE ROWS` GTT, commit one row, insert a second row, and then `ROLLBACK`. Identify which row remains and explain using transaction boundaries.

**Step 5 — Test transaction-scoped PTT on Oracle 18c+.** Create `ORA$PTT_STAGE_TX`, insert a row, and select before commit. After committing, run a separate select; explain why "table or view does not exist" is the expected behavior.

**Step 6 — Test session-scoped PTT.** Create `ORA$PTT_STAGE_SESSION`, insert, commit, and select in the same session. Truly close the session and open a fresh one; why must the table be recreated?

**Step 7 — Inspect metadata.** Compare `USER_TABLES` for GTTs with `USER_PRIVATE_TEMP_TABLES` for PTTs. Match `DURATION` to the observed behaviors.

**Step 8 — Simulate a connection pool.** Request A uses a `PRESERVE ROWS` GTT and returns the connection to the pool. Request B borrows the same physical connection. Describe the risk and design a cleanup/transaction strategy.

**Step 9 — Compatibility design.** A project runs Oracle 12.2 in production and Oracle 19c in dev, while a module creates a PTT on every request. Propose an alternative avoiding PTTs for production and explain how metadata lifecycle changes.

### Post-Lab Answer Hints

1. **Why does `ON COMMIT DELETE ROWS` differ from `ON COMMIT DROP DEFINITION`?** GTT clears only rows, whereas PTT drops the entire table definition too.
2. **Why do two sessions sharing a GTT never see each other's rows?** Temporary data is isolated per session despite shared metadata.
3. **Why may `connection.close()` fail to clear `PRESERVE ROWS` data?** Pools keep physical sessions open and reuse them.
4. **Why shouldn't you create a GTT on every request?** A GTT definition is persistent; recreating it causes name collisions and DDL overhead.
5. **Why can't you assume PTT works on every Oracle server?** PTTs require Oracle 18c+, valid prefix naming, privileges, and adherence to release restrictions.

## 15. When to Choose GTT, PTT, or Another Approach?

| Requirement | Recommended Choice |
|---|---|
| Staging schema shared by many sessions/programs **in definition**, with isolated rows | **GTT** created once via migration |
| Data needed only inside a single transaction, table already deployed | GTT `ON COMMIT DELETE ROWS` |
| Data needed across commits in one physical session | GTT `ON COMMIT PRESERVE ROWS` with explicit cleanup |
| Ad-hoc staging table whose definition is needed only for one transaction (Oracle 18c+) | PTT `ON COMMIT DROP DEFINITION` |
| Ad-hoc staging table whose definition spans commits in one session (Oracle 18c+) | PTT `ON COMMIT PRESERVE DEFINITION` (watch implicit commit on CREATE) |
| Data must be readable across arbitrary sessions or pooled requests | **Permanent** table keyed by job/request ID with access control |
| Short single-query SQL transformation | Consider `WITH` CTE, inline view, or a single SQL statement |
| Must support Oracle 11g/12c simultaneously | Use GTT or compatible design; **do not rely on PTT** |
| Complex indexes or column defaults needed on staging table | Evaluate GTT or permanent tables; **never assume PTT supports them** |

Key principle: **pick the right lifecycle before optimizing performance**. Decide whether temporary data belongs to *one transaction*, *one session*, or *multiple sessions*. Only then choose GTT vs. PTT and design commit points, cleanup, pooling, privileges, and metadata.

## 16. Final Takeaways

- **GTT:** *global definition, session-private data*. `DELETE ROWS` clears rows on transaction commit; `PRESERVE ROWS` keeps rows across commits within the session. Table definition persists after the session ends.
- **PTT (Oracle 18c+):** *private definition and data*. `DROP DEFINITION` drops the entire table on commit; `PRESERVE DEFINITION` keeps table and rows until session termination. Names must match `PRIVATE_TEMP_TABLE_PREFIX`, defaulting to `ORA$PTT_`.
- **PTT DDL behavior is asymmetric:** creating a transaction-scoped `DROP DEFINITION` PTT does not implicitly commit, whereas creating a `PRESERVE DEFINITION` PTT does implicitly commit under Oracle 19c rules.
- **JDBC autocommit and connection pooling can completely upend lifecycle expectations.** Same physical connection and explicit transaction boundaries are essential for multi-step temp-table logic.
- **Temporary tables are not durable storage**, are not guaranteed to skip TEMP/I/O overhead, and never bypass privilege or version constraints.

### Official References

- Oracle Database 19c, *SQL Language Reference — CREATE TABLE*: https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html
- Oracle Database 19c, *Administrator's Guide — Managing Tables (Temporary Tables)*: https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-tables.html
- Oracle Database 19c, *Database Reference — USER_PRIVATE_TEMP_TABLES*: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_PRIVATE_TEMP_TABLES.html

During rollout, verify the target server release and PDB, define temp tables to match real data lifecycles, control transactions/sessions tightly, and test workflows against your application's actual **physical connection** pooling behavior. That prevents "disappearing temp tables," "empty temp tables," and "cross-request data leaks" even when every individual SQL statement looks valid.
