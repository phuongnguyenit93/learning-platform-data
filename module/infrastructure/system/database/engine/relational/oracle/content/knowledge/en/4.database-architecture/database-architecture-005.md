# SGA Memory: Buffer Cache, Shared Pool, Redo Log Buffer, and Additional Areas

When an application sends SQL to Oracle Database, the database management system does not necessarily re-read every data block from disk or re-parse the entire SQL statement from scratch. Oracle uses the **System Global Area (SGA)**, a shared memory region of the **Oracle instance**, to hold actively accessed blocks, share SQL structures, and prepare redo records for recovery after a failure.

The SGA is the key to explaining many seemingly contradictory phenomena: a query running faster the second time than the first; `COMMIT` completing before datafiles are updated; multiple sessions using the same SQL cursor; and adding RAM not guaranteeing the system runs faster.

After this lesson, you will be able to:

- Distinguish **SGA**, **PGA**, **instance**, and data files on disk.
- Explain the purpose and stored contents of the **database buffer cache**, **shared pool**, and **redo log buffer**.
- Trace the path of `SELECT`, `UPDATE`, and `COMMIT` through memory and background processes.
- Recognize the **large pool**, **Java pool**, **Streams pool**, **fixed SGA**, and several optional areas.
- Understand SGA allocation modes and observe memory via Oracle views without altering configuration.
- Avoid incorrect conclusions from cache hit ratios, hard parses, redo, checkpoints, and wait events.

> Examples focus on modern Oracle Database architecture, including the Oracle Database Free learning environment. Available sizes, parameters, memory characteristics, and privileges to use a feature depend on the specific version, edition, platform, and configuration. Querying `V$` dynamic performance views may require administrative privileges or appropriate `SELECT` grants.

## 1. Placing the SGA in the Oracle Database Picture

An **Oracle database** is the collection of data stored in datafiles and the required control/redo files. An **Oracle instance** is the memory and Oracle processes used to open, manage, and serve that database.

An instance comprises:

1. **SGA:** shared memory for processes and sessions serving the database.
2. **Background processes:** such as Database Writer (`DBWn`), Log Writer (`LGWR`), Checkpoint (`CKPT`), System Monitor (`SMON`), and others.

When an application connects, a server process works with the SGA while also needing a **Program Global Area (PGA)**, a private memory region for process operations such as sort/hash work areas or session-serving state depending on connection architecture.

```text
Application / SQL client
        │ SQL and bind data
        ▼
  Server process ──── PGA (process private memory)
        │
        ▼
┌──────────────── ORACLE INSTANCE ─────────────────┐
│                                                  │
│  ┌────────────────── SGA ──────────────────────┐  │
│  │ Database buffer cache                     │  │
│  │ Shared pool                               │  │
│  │ Redo log buffer                           │  │
│  │ Large / Java / Streams pools              │  │
│  │ Fixed SGA and optional areas              │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  Background processes: DBWn, LGWR, CKPT, ...     │
└──────────────┬─────────────────────┬─────────────┘
               │ DBWn                │ LGWR
               ▼                     ▼
           Datafiles           Online redo logs
              └──────────────────────┘
                  Database storage
```

**The SGA belongs to the instance, not to a single table or schema.** In CDB/PDB architecture, multiple PDBs can be served by the same instance and share memory resources at the instance level, though PDB-level resource management mechanisms exist in applicable versions/editions. In **Oracle RAC**, each cluster instance has its own SGA while instances can access the same database; exchanging blocks across instances is an additional RAC mechanism.

### 1.1. How Does the SGA Differ from the PGA?

| Characteristic | SGA | PGA |
| --- | --- | --- |
| Scope | Instance-wide shared memory | Private memory of a single Oracle process |
| What does it contain? | Cached data blocks, SQL cursors, metadata, redo records, and other shared areas | SQL work areas, execution state, and process-private memory |
| Common parameters | `SGA_TARGET`, `SGA_MAX_SIZE` | `PGA_AGGREGATE_TARGET`, `PGA_AGGREGATE_LIMIT` |
| Does the app read/write directly? | Through Oracle server process mechanisms | Through the Oracle process handling the request |
| What does increasing size do? | Can reduce certain block reads/parses or support other components | Can reduce the need to spill certain sort/hash operations to TEMP |

Not every byte of RAM consumed by Oracle resides in the SGA. When budgeting RAM for a database, also account for PGA, OS overhead, auxiliary processes, and memory used by other software.

## 2. Map of Memory Areas Inside the SGA

| Component | Primary Contents | Why Is It Needed? |
| --- | --- | --- |
| **Database buffer cache** | Copies of database blocks currently in use; includes modified blocks not yet written to datafiles | Reduces repeated I/O and holds actively processed blocks |
| **Shared pool** | Shared SQL areas, SQL cursors and plans, shared PL/SQL, data dictionary cache, and internal structures | Reuses parse work, metadata, and compiled code |
| **Redo log buffer** | Redo records describing changes for recovery | Buffers redo in RAM for LGWR to write to online redo logs |
| **Large pool** | Specialized allocations, e.g., RMAN, shared server, parallel execution | Serves large buffers / dedicated needs |
| **Java pool** | Memory supporting Java inside Oracle Database | Serves Oracle JVM / Java features when used |
| **Streams pool** | Certain data streaming, capture/replication, and buffered queue mechanisms | Supports specialized features by version |
| **Fixed SGA** | Essential instance control structures | Coordinates internal operations |
| **Optional areas** | E.g., In-Memory Column Store, Result Cache, or KEEP/RECYCLE buffer pools | Supports specific workload patterns if enabled/supported |

The first three areas are critical and **do not replace one another**: the buffer cache holds *data blocks*; the shared pool holds *SQL processing structures and metadata*; the redo log buffer holds *change-recovery information*.

## 3. Database Buffer Cache: Memory Area Holding Database Blocks

### 3.1. How Does Oracle Access Blocks?

Table data, indexes, and many other structures are stored on disk in **database blocks**. When an SQL statement needs blocks:

1. Oracle determines the data access path from the execution plan.
2. If the needed block is already in the buffer cache, Oracle can use the in-memory copy.
3. If the block is not present, Oracle can read it from a datafile into the cache.
4. Certain read paths such as **direct path read** can bypass the normal buffer cache path; not every physical read puts blocks into the cache.

```text
      Datafiles on disk
    [A] [B] [C] [D] [E]
         │       │
         │ read required blocks
         ▼       ▼
  ┌───────────────────────┐
  │  Database buffer cache│
  │       [B] [D]         │
  └───────────┬───────────┘
              │
              ▼
       Process SELECT/JOIN...
              │
              ▼
         Return results
```

When subsequent SQL statements reuse blocks already in the cache, part of the disk read cost can be avoided. However, the cache does not keep every block forever: Oracle manages and replaces buffers via internal mechanisms to serve the workload.

**Important distinction:** the database buffer cache holds database blocks. It **does not by default cache the exact result row set of each `SELECT` statement**. Query Result Cache (if enabled and applicable) is a different mechanism.

### 3.2. Logical Read Is Not the Same as Physical Read

A **logical read** reflects block access at Oracle's logical level, typically encompassing access forms such as consistent gets or current gets. A **physical read** reflects having to read data through an I/O path as defined by the specific counter.

| Scenario | What Can Happen |
| --- | --- |
| First time a block not in cache is needed | Requires a physical read and may cache the block |
| Multiple queries needing blocks still in cache | Can leverage memory while still generating logical reads |
| Cache churn due to other workloads | Older blocks may be evicted and later have to be re-read |
| Large full scan or direct path | May perform I/O via a path bypassing the normal buffer cache |

Do not treat the instance-wide `cache hit` ratio as the single answer to every performance issue. An SQL statement reading too many blocks due to a poor execution plan can still be slow even when most blocks are already in RAM.

### 3.3. Clean, Dirty, and Pinned Buffers

A **clean buffer** is a block copy containing no changes still needing to be written down to a datafile. A **dirty buffer** holds in-RAM modifications not yet fully written to the corresponding datafile. A buffer may also currently be **pinned** or accessed by a process under synchronization mechanisms.

Example:

```text
Initially:
  Datafile:  balance = 500
  Cache:     balance = 500  (clean)

After UPDATE:
  Datafile:  balance = 500
  Cache:     balance = 450  (dirty)

After DBWn writes block:
  Datafile:  balance = 450
  Cache:     synchronized with data in file
```

This is a conceptual illustration only; Oracle involves many details of concurrency, undo, and consistent reads. The algorithm for finding free/reusable buffers is also more sophisticated than a pure LRU list.

### 3.4. Who Writes Dirty Buffers to Datafiles?

The **Database Writer (`DBWn`)** process writes dirty blocks from the buffer cache down to datafiles when needed—for instance, to make buffers available for reuse, respond to I/O pressure, or service checkpoints. **CKPT** coordinates checkpoint information and updates appropriate metadata; it is not the process writing all dirty blocks in place of DBWn.

Key point: **`COMMIT` does not require DBWn to immediately write every dirty block of the transaction down to datafiles**. Durability for standard synchronous commit generally relies on redo having been written by LGWR to the online redo log before reporting success.

### 3.5. How Do Consistent Read and Undo Relate?

Oracle supports **read consistency** so queries see data appropriate to the statement or transaction snapshot, depending on isolation level. If the current block contains changes incompatible with that snapshot, Oracle can use **undo** to construct a consistent-read version of the block.

Undo is stored in database undo segments/tablespaces; undo blocks themselves can be cached and accessed through the buffer cache mechanism. **There is no separate SGA region named "undo pool"** analogous to the buffer cache. Undo serves rollback and read consistency; redo serves recovery of required changes. The two are related, yet their responsibilities differ.

## 4. Shared Pool: Sharing SQL, PL/SQL, and Metadata

The shared pool provides shared structures for parsing, optimizing, executing, and managing SQL. Two common sub-areas are:

- **Library cache:** holds shared SQL areas/cursors, execution plans, compiled PL/SQL code, and shared structures.
- **Data dictionary cache** (row cache): holds frequently needed metadata about objects, users, privileges, definitions, and internal information.

```text
                         SHARED POOL
             ┌─────────────────────────────┐
             │ Library cache               │
             │ • SQL cursor / SQL area     │
             │ • Execution plan            │
             │ • Shared PL/SQL             │
             ├─────────────────────────────┤
             │ Data dictionary cache       │
             │ • Table, column, priv meta  │
             │ • Other object metadata     │
             ├─────────────────────────────┤
             │ Other shared allocations    │
             └─────────────────────────────┘
```

### 4.1. Parse, Hard Parse, and Soft Parse

Upon receiving SQL, Oracle must check syntax/semantics, objects, and privileges, look up a reusable cursor structure, choose/apply an execution plan, and execute.

A **hard parse** performs the work of creating new cursor/plan structures when no compatible cursor exists for reuse. This work can consume significant CPU and cause contention. A **soft parse** can usually reuse shared structures, skipping several steps; soft parse does not mean the database does zero work.

Cursor shareability is affected by many factors: SQL text, schema, privileges, bind data types, settings, metadata, object state, and optimizer mechanisms. Two SQL statements that look identical do not necessarily share the exact same child cursor.

### 4.2. Bind Variables Reduce the Need to Generate Distinct SQLs

Suppose table `orders` has column `order_id`:

```sql
SELECT order_id, amount FROM orders WHERE order_id = 101;
SELECT order_id, amount FROM orders WHERE order_id = 102;
```

The two statements contain different literals. An application executing this repeatedly can use:

```sql
SELECT order_id, amount
FROM orders
WHERE order_id = :order_id;
```

And supply `:order_id` as 101 and 102 in turn. This typically increases SQL/cursor sharing opportunities, reduces parse cost, and helps prevent SQL injection when parameters are bound properly. It **does not guarantee a single execution plan**: Oracle can create multiple child cursors/plans when justified, such as differing bind types or data characteristics.

An SQL statement may also require a hard re-parse after DDL or when metadata/cursors are invalidated. Therefore, high hard-parse rates must be investigated across SQL design, invalidations, and workload—not just shared pool sizing.

### 4.3. How Does the Data Dictionary Cache Help?

Consider the statement:

```sql
SELECT customer_id
FROM customers
WHERE customer_id = :id;
```

Oracle needs to know which schema owns `customers`, its column definitions, what privileges the user holds, and what metadata is needed for planning. Such information can be cached and reused in shared pool structures to avoid repeated lookups.

**The shared pool does not store entire table rows directly in place of the database buffer cache.** The shared pool focuses on SQL structures, code, and metadata; the buffer cache focuses on data blocks.

### 4.4. What Happens When the Shared Pool Is Under Pressure?

Symptoms can include high hard parses, library cache contention, or `ORA-04031` allocation errors under certain conditions. `ORA-04031` can involve insufficient memory, fragmentation, specialized allocations, or pool configuration; adding RAM is not always the sole remedy.

Measure parse frequency, non-reusable SQL count, invalidations, allocation patterns, and pool status before tuning `SHARED_POOL_SIZE`.

## 5. Redo Log Buffer: Buffer for Recovery

### 5.1. What Are Redo Records?

**Redo records** carry information about the changes needed so Oracle can recover the database after a failure. Redo **is not simply a verbatim copy of the SQL text**. Oracle generates appropriate redo for data/undo block changes and related structures via its internal logging mechanism.

These redo records are placed into the **redo log buffer** in the SGA. The **Log Writer (`LGWR`)** process writes redo to **online redo log files** (on disk or ASM).

```text
       INSERT / UPDATE / DELETE
                 │
       ┌─────────┴─────────┐
       ▼                   ▼
Database buffer cache   Redo log buffer
   (dirty data/undo)      (redo records)
       │                   │
       │ DBWn              │ LGWR
       ▼                   ▼
   Datafiles         Online redo logs
```

The buffer cache and redo log buffer hold two different kinds of information, written by two different processes to two different groups of files.

### 5.2. What Does `COMMIT` Actually Wait For?

With a **standard synchronous commit**:

1. DML modifies the relevant blocks in the buffer cache and generates corresponding redo.
2. The transaction requests `COMMIT`; Oracle generates the required commit information.
3. LGWR writes the transaction's required redo, including the commit record, out to the online redo log.
4. Once the required redo write completes, Oracle can report `COMMIT` success.
5. DBWn may write the dirty data blocks down to datafiles afterward.

This is the principle of **write-ahead logging**: Oracle must ensure appropriate redo is durably recorded before the related data modifications are considered safe within the write/recovery mechanism. If the instance crashes before DBWn finishes writing all dirty blocks, Oracle can use redo to recover committed changes during recovery.

> There are commit options whose wait/write behavior differs from the default synchronous mode. Within the scope of this lesson, the description above applies to standard synchronous commit; do not infer that every configuration guarantees durability at the exact same moment.

### 5.3. Does LGWR Only Write on Commit?

No. Oracle can also flush redo under other conditions such as buffer usage thresholds, background intervals, log switches, and internal requests. Exact thresholds and implementation details can vary by release.

**The redo log buffer is a short-lived RAM area.** It is not a permanent transaction history log. **Online redo log files** are where redo is durably stored, and online redo log groups are rotated in use. When the database runs in `ARCHIVELOG` mode, eligible redo logs can be archived into **archived redo logs** via the archiving process.

### 5.4. Distinguishing "Log" Components

| Component | Location | Role |
| --- | --- | --- |
| Redo log buffer | In SGA/RAM | Temporarily holds redo before LGWR writes |
| Online redo log files | On disk/ASM | Stores redo for instance recovery |
| Archived redo logs | Archive storage when configured | Serves recovery/backup per policy |
| Undo segments | Datafiles/undo tablespace; blocks can be cached | Rollback and read consistency |
| Database buffer cache | In SGA/RAM | Holds database blocks being processed |
| Application logs | Managed by the application | Records business/technical events; does not replace Oracle redo |

Do not confuse an application `COMMIT` with all datafiles already having been updated; and do not confuse the redo log buffer with online redo log files.

## 6. Tracing a Transaction Through the Three Main Memory Areas

Suppose table `accounts(account_id, balance)` exists. Example transferring 100 units:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
```

This is an architectural illustration only. A real application must also validate balances, locking, transactions, and roll back on error.

| Step | Participating Component | Activity |
| --- | --- | --- |
| 1. Receive SQL | Shared pool | Locate shared cursor, check metadata, or perform parse/optimization when needed |
| 2. Locate rows | Buffer cache and I/O | Read/locate blocks, reading from datafiles if not yet in cache |
| 3. Modify | Buffer cache and undo | Update affected blocks, manage info for rollback/read consistency |
| 4. Generate redo | Redo log buffer | Record redo records needed for the changes |
| 5. Commit | LGWR and online redo logs | Write required redo; once synchronous commit conditions are met, confirm to client |
| 6. Write datafiles | DBWn and datafiles | Write dirty blocks when appropriate, possibly after commit |

```text
SQL UPDATE
  │
  ├── Parse/cursor ──► SHARED POOL
  │
  ├── Modify block ──► BUFFER CACHE ── DBWn ──► DATAFILES
  │
  └── Generate redo ─► REDO LOG BUFFER ─ LGWR ──► ONLINE REDO
                               ▲
                               │
                            COMMIT
```

In a crash scenario after commit but before the corresponding datafile write, redo is essential for instance recovery. If a transaction had not committed, recovery must also undo the incomplete changes using undo mechanisms.

This path cleanly separates **datafile read performance**, **parse frequency**, and **redo/commit write latency**: they involve different SGA regions.

## 7. Additional Areas in the SGA

### 7.1. Large Pool

The **large pool** serves specialized allocations, typically related to:

- Buffers for certain **RMAN backup/restore** operations.
- **User Global Area (UGA)** in certain **shared server** configurations.
- Message buffers for **parallel execution** depending on model and version.

Isolating certain large allocations from the shared pool can reduce pressure on the shared pool from objects with different allocation patterns than SQL cursors. However, not all RMAN/parallel query operations use the large pool identically; it depends on version and configuration.

Common parameter: `LARGE_POOL_SIZE`.

### 7.2. Java Pool

The **Java pool** is used when the database runs Java inside Oracle, such as Oracle JVM or Java stored procedures when available. It is completely distinct from **the JVM heap of a Java/Spring Boot application**: the application JVM runs in an external process outside the database, not in the SGA.

Common parameter: `JAVA_POOL_SIZE`.

### 7.3. Streams Pool

The **Streams pool** supports certain data streaming, capture, replication, or buffered queue mechanisms in specific Oracle configurations. Its name originates historically from Oracle Streams. **Do not infer that legacy Oracle Streams is still supported merely because an instance has a Streams pool**; the components using the pool change across versions.

Common parameter: `STREAMS_POOL_SIZE`.

### 7.4. Fixed SGA

The **Fixed SGA** contains essential internal control structures for the instance. Overview views often display a `Fixed Size` entry. This is not an area where applications store arbitrary data, nor should an administrator resize it manually like `DB_CACHE_SIZE`.

### 7.5. In-Memory Column Store, Result Cache, and Buffer Pools

The **In-Memory Column Store (IMCS)**, if permitted by version/edition and licensing, can maintain columnar data representations in the SGA for certain analytical workloads. It complements traditional row-format storage; **it does not convert the entire database buffer cache into a column store**.

**Result Cache**, when enabled and appropriate, can store query/function results for reuse and manage invalidation as dependent data changes. Result Cache differs from the **database buffer cache**: one stores computed results, while the other primarily stores database blocks. How result cache memory is allocated within the SGA/shared pool depends on design and version.

**DEFAULT, KEEP, and RECYCLE** are buffer pools that can appear in database buffer cache management. They are policies/sub-regions of the **buffer cache**, not cursor pools like the shared pool. The name KEEP is not a guarantee that every block will stay in RAM forever; configure it only after understanding block access patterns.

## 8. Managing SGA Size

Oracle can allocate memory in **granules** and resize certain components depending on the management mode. Granule size depends on configuration and platform; pools do not resize byte-by-byte arbitrarily.

### 8.1. Parameters to Know

| Parameter | Purpose | Notes |
| --- | --- | --- |
| `SGA_TARGET` | Target total SGA under **Automatic Shared Memory Management (ASMM)** | Oracle redistributes memory among several components |
| `SGA_MAX_SIZE` | Upper limit of SGA over the instance lifetime | Changing this ceiling typically requires a restart |
| `DB_CACHE_SIZE` | Configures the default database buffer cache size | Under ASMM, an explicit value typically acts as a minimum floor |
| `SHARED_POOL_SIZE` | Configures the shared pool size | Under ASMM, an explicit value typically acts as a minimum floor |
| `LOG_BUFFER` | Configured size of the redo log buffer | Follows its own management rules; does not auto-resize arbitrarily like ASMM components |
| `LARGE_POOL_SIZE` | Configures the large pool | Appropriate when workloads actually use this area |
| `JAVA_POOL_SIZE` | Configures the Java pool | Relevant for in-database Java |
| `STREAMS_POOL_SIZE` | Configures the Streams pool | Relevant for specialized features |
| `MEMORY_TARGET` | Target for **Automatic Memory Management (AMM)** managing both SGA and PGA overall | Differs from `SGA_TARGET`; support depends on OS/configuration |
| `MEMORY_MAX_TARGET` | Memory ceiling for AMM | Subject to specific rules when changing |
| `PGA_AGGREGATE_TARGET` | Target total PGA | PGA is not inside the SGA |

### 8.2. ASMM, AMM, and Manual Management

**Manual SGA component management:** When `SGA_TARGET=0` and AMM is not used, the administrator must explicitly size required areas using component parameters.

**ASMM:** When `SGA_TARGET>0` and `MEMORY_TARGET=0`, Oracle can automatically adjust sizes of certain SGA components within the shared budget, while PGA is managed separately. Manually set component values can act as lower bounds limiting how much Oracle may shrink them.

**AMM:** When `MEMORY_TARGET>0` and the platform supports it, Oracle can distribute the overall memory target between SGA and PGA. This does not mean actual total database/OS RAM usage will always equal `MEMORY_TARGET` to the byte.

On Linux, AMM interacts with HugePages/shared memory; in containers, you must also account for memory limits and runtime-provided shared memory mounts. Never copy a parameter set from another server blindly onto a small-memory lab machine.

### 8.3. Why Not Just Increase Every Pool?

- Extra RAM dedicated to the SGA leaves less for PGA, the operating system, and other software. If the OS swaps, the system can become slower.
- A larger buffer cache does not fix unnecessary SQL scans or missing indexes.
- A larger shared pool does not eliminate the root cause of an application generating distinct SQLs with literals.
- A larger redo log buffer does not make the disk holding online redo logs write faster.
- Some components have min/max limits or separate restart requirements; edition limits must also be respected.

Resizing decisions should be based on **workload, metrics, and actual allocation capability**, not a single cache hit ratio.

## 9. Observing SGA Memory via SQL

The following queries are **read-only** and inspect operational data. They generally require an account with appropriate privileges on `V$` dynamic performance views. Do not grant `DBA` to an application user just to run this practice exercise.

### 9.1. Overall SGA Size

```sql
SELECT name,
       ROUND(value / POWER(1024, 2), 2) AS mb
FROM v$sga;
```

Results typically show entries such as `Fixed Size`, `Variable Size`, `Database Buffers`, and `Redo Buffers`. **`Variable Size` is not "free RAM"**—it is a summary category in Oracle's overall report.

Further detail:

```sql
SELECT name,
       ROUND(bytes / POWER(1024, 2), 2) AS mb,
       resizeable
FROM v$sgainfo
ORDER BY name;
```

The `RESIZEABLE` column describes whether the reported memory area supports resizing, not permission to alter configuration immediately.

### 9.2. Resizable SGA Components

```sql
SELECT component,
       ROUND(current_size / POWER(1024, 2), 2) AS current_mb,
       ROUND(user_specified_size / POWER(1024, 2), 2) AS user_specified_mb
FROM v$sga_dynamic_components
WHERE current_size > 0
ORDER BY current_size DESC;
```

`CURRENT_SIZE` reports the component's current size as recorded by the view; `USER_SPECIFIED_SIZE` is the user-specified size if set. Do not expect this view to list every box in an SGA diagram: it lists dynamic components, not the entire memory taxonomy.

### 9.3. Allocations Within Pools

```sql
SELECT NVL(pool, '(no pool)') AS memory_pool,
       name,
       ROUND(bytes / POWER(1024, 2), 2) AS mb
FROM v$sgastat
ORDER BY bytes DESC
FETCH FIRST 30 ROWS ONLY;
```

`V$SGASTAT` lists many types of allocations inside the SGA. Any `free memory` figure must be interpreted within the context of each pool, allocator, and resizing mechanism; never treat a single `free memory` row as total usable RAM across all of Oracle.

### 9.4. Checking Parameters

In SQL*Plus or SQLcl:

```sql
SHOW PARAMETER memory_target
SHOW PARAMETER sga_target
SHOW PARAMETER sga_max_size
SHOW PARAMETER db_cache_size
SHOW PARAMETER shared_pool_size
SHOW PARAMETER log_buffer
SHOW PARAMETER pga_aggregate_target
```

Or using SQL:

```sql
SELECT name, display_value, isdefault, issys_modifiable
FROM v$parameter
WHERE name IN (
    'memory_target',
    'memory_max_target',
    'sga_target',
    'sga_max_size',
    'db_cache_size',
    'shared_pool_size',
    'log_buffer',
    'pga_aggregate_target'
)
ORDER BY name;
```

The value currently active in the instance may differ from a value written in the SPFILE awaiting restart. `ISDEFAULT` and `ISSYS_MODIFIABLE` help administrators interpret parameter status, though they do not replace checking the modification rules for each parameter.

### 9.5. Statistics Comparable Over Time

```sql
SELECT name, value
FROM v$sysstat
WHERE name IN (
    'session logical reads',
    'physical reads',
    'parse count (total)',
    'parse count (hard)'
)
ORDER BY name;
```

These counters typically accumulate over the lifetime of the instance. Take the **delta between two timestamps during the same workload window** to assess trends. Aggregate numbers alone do not pinpoint whether a specific SQL statement is slow due to buffer cache or shared pool, and physical reads do not always equal device-level physical disk operations.

## 10. Identifying Performance Symptoms

| Symptom | What to Check First | Conclusion to Avoid |
| --- | --- | --- |
| Query reads very many blocks, high I/O | SQL plan, indexes, access path, buffer cache, and workload | "Definitely just need to increase `DB_CACHE_SIZE`" |
| Many hard parses, high parse CPU | SQL literals/binds, cursor sharing, metadata invalidations, and shared pool | "Increasing `SHARED_POOL_SIZE` will always fix it" |
| `ORA-04031` | Allocations/fragmentation in the failing pool, SQL/cursors, and configuration | "Every `ORA-04031` is just insufficient total RAM" |
| High `log file sync` waits | Commit frequency, LGWR, redo write latency | "Just increase `LOG_BUFFER`" |
| High `log buffer space` waits | Redo generation rate, LGWR, and redo write path | "No need to check storage devices" |
| `free buffer waits` | Buffer reuse rate, DBWn/I/O speed, workload | "Every free buffer issue is caused by a small cache" |
| `buffer busy waits` | Multiple sessions contending on hot blocks/buffers | "Block contention means insufficient SGA" |
| OS swapping or database fails to start | Total SGA/PGA/OS, VM/container limits, and host RAM | "Make all pools larger" |

For instance, two waits containing the word **buffer** differ significantly: `free buffer waits` relates to finding a reusable buffer; `buffer busy waits` can relate to concurrent contention on the same block. Remediation must be driven by metrics, not by keywords in wait names.

A sound investigation workflow:

1. Identify the slow operation: parsing, read queries, DML, or `COMMIT`.
2. Measure during the window when the workload actually occurs and save a baseline.
3. Combine SQL plans, CPU, I/O, waits, and relevant memory statistics.
4. Change one justified factor at a time, re-measure results, and account for OS resources.

Some deep analysis tools/features such as AWR/ASH carry edition, privilege, and licensing conditions. You can start with the dynamic performance views permitted in your practice environment.

## 11. Misconceptions to Discard

**"The SGA is all the RAM Oracle uses."** False: there is also PGA, process memory, and OS memory.

**"The buffer cache stores all SELECT results."** False: the buffer cache stores database blocks; query result cache is a separate mechanism.

**"Once COMMIT finishes, every block is already in the datafile."** False for standard synchronous commit: durability relies on required redo having been written by LGWR; DBWn can update datafiles later.

**"The redo log buffer and online redo log are the same thing."** False: the buffer is in RAM; online redo logs are on persistent storage.

**"The shared pool holds full table/index data."** False: the shared pool holds cursors, plans, metadata, and shared structures; data blocks generally pass through the buffer cache.

**"The PGA is a pool inside the SGA."** False: the PGA is process-private memory with its own allocation mechanism.

**"With enough cache, zero I/O is needed."** False: redo must still be written, dirty blocks still need to be flushed, and direct path / TEMP accesses and large workloads still generate I/O.

**"Increasing the SGA always makes things faster."** False: starving the PGA or triggering OS swapping can slow down the entire system.

## 12. Safe Observation Practice Exercise

**Prerequisites:** Oracle Database is running; if inspecting `V$SGA`, `V$SGAINFO`, or `V$SGA_DYNAMIC_COMPONENTS`, use a user granted access to those views. This exercise does not require modifying instance configuration.

**Step 1 — Identify the current instance and PDB.**

```sql
SELECT SYS_CONTEXT('USERENV', 'INSTANCE_NAME') AS instance_name,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name
FROM dual;
```

If connected to a PDB, the container result usually shows the PDB name. Remember that observing instance-level SGA metrics does not mean the current PDB exclusively owns the entire SGA.

**Step 2 — View SGA sizes.**

```sql
SELECT name, ROUND(value / POWER(1024, 2), 1) AS mb
FROM v$sga;
```

Look for rows related to database buffers, redo buffers, and variable size. Next, inspect dynamic components:

```sql
SELECT component, ROUND(current_size / POWER(1024, 2), 1) AS mb
FROM v$sga_dynamic_components
WHERE current_size > 0
ORDER BY current_size DESC;
```

If you hit a privilege error, note it and ask an administrator to run the query; do not grant `DBA` to an application account just to inspect a view.

**Step 3 — Explain the path of a SELECT statement.**

```sql
SELECT COUNT(*) FROM orders;
```

Assuming table `orders` exists, explain how the shared pool can reuse the cursor/metadata, how the buffer cache can serve blocks, and why Oracle might still choose direct path read. There is no need to run the SQL on a nonexistent table.

**Step 4 — Explain an UPDATE and COMMIT.**

```sql
UPDATE orders SET status = 'DONE' WHERE order_id = 100;
COMMIT;
```

Assuming the table/column exist and the transaction succeeds, answer for yourself:

1. Which blocks can become dirty in the buffer cache?
2. Which SGA area holds redo records before LGWR writes them?
3. Which files does LGWR write to, and which files does DBWn write to?
4. Why can the transaction be confirmed durable after commit even if DBWn has not written all dirty blocks yet?

**Step 5 — Formulate performance hypotheses.**

If an application generates SQL with new literals on every execution, what cost might the shared pool incur? If row-by-row `COMMIT` is slow, how should you investigate commit frequency and LGWR I/O? If the OS is swapping, why might increasing `SGA_TARGET` be the wrong move?

These questions connect each memory area's role directly to real measured metrics.

## 13. Mental Model

```text
SGA = shared memory of the Oracle instance

Buffer cache    → holds database blocks, may contain dirty blocks
Shared pool     → holds shared SQL cursors/plans, PL/SQL, and metadata
Redo log buffer → holds redo records before LGWR writes to online redo
Large pool      → specialized/large allocations
Java pool       → supports Java inside Oracle Database
Streams pool    → supports certain streaming/capture features
Fixed SGA       → core instance control information
```

Relationships to remember:

- **Queries:** the shared pool supports SQL cursors/metadata; data is read via the buffer cache or an appropriate I/O path.
- **DML:** Oracle modifies blocks in the buffer cache and generates redo for logged changes.
- **Synchronous commit:** LGWR writes required redo before Oracle confirms success; DBWn can write to datafiles later.

Understanding these three paths lays the groundwork for deeper study of background processes, checkpoints, undo/redo recovery, memory management, and Oracle Database performance diagnostics.
