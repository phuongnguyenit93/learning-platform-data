# PGA Memory, Work Areas, and Sort or Hash Processing in Oracle Database

An SQL statement can read data very quickly yet take a long time to **sort**, **join two tables**, or **aggregate groups**. The cause does not necessarily lie in table-read speed: Oracle must allocate memory to process intermediate operations. If the data volume exceeds the processing capacity of the allocated memory, Oracle may write intermediate portions down to the **temporary tablespace (TEMP)** and read them back later, causing extra I/O and slowing the query down.

In Oracle architecture, the private memory area of a process serving SQL is called the **PGA (Program Global Area)**. Inside Oracle-managed memory, there are **SQL work areas** dedicated to operations such as sorting or hash joins. Understanding PGA and work areas helps answer practical questions:

- Why do two `SELECT` statements returning the same number of rows consume vastly different amounts of memory?
- Why do `ORDER BY` or `HASH JOIN` sometimes run entirely in memory and sometimes use substantial TEMP?
- Why is a query fast when run alone yet slow when many users run it concurrently?
- What do `PGA_AGGREGATE_TARGET`, `PGA_AGGREGATE_LIMIT`, and `WORKAREA_SIZE_POLICY` mean?
- Which tools observe work area execution modes and TEMP reads/writes?

This lesson explains the path of data from SQL execution operations to PGA/TEMP, with Oracle SQL examples, observation queries, and tuning guidance when sorts or hashes consume excessive resources.

## 1. Placing the PGA in Oracle Memory Architecture

Oracle Database uses **instance-wide shared memory** and **process-private memory**. The two key regions are the SGA and the PGA.

| Component | Nature | Typical Contents/Role | Sharing Characteristics |
|---|---|---|---|
| **SGA — System Global Area** | Instance-level shared memory | Database buffer cache, shared pool, redo log buffer, and other pools depending on configuration | Accessed by multiple processes of the instance |
| **PGA — Program Global Area** | Private memory of a single Oracle process | Data for private processing: SQL work areas, process allocations, and other private structures | Not a shared data cache across multiple server processes |
| **UGA — User Global Area** | Area storing session-related state | Session state information, part of cursor/private SQL area info, etc. | Location depends on connection architecture: typically in PGA for dedicated server; in SGA, potentially in the large pool when configured, for shared server |
| **TEMP tablespace** | Temporary storage space on disk or corresponding storage system | Temporary segments when operations cannot be processed entirely in memory | Not part of the PGA; managed by Oracle on storage |

Conceptual diagram with **dedicated server**:

~~~text
                  ORACLE INSTANCE
        +--------------------------------+
        |             SGA                |
        | buffer cache / shared pool /   |
        | redo log buffer / ...          |
        +--------------------------------+
             ^                 ^
             |                 |
     +-------+------+   +------+-------+
     | Server       |   | Server       |
     | Process A    |   | Process B    |
     |              |   |              |
     | PGA A        |   | PGA B        |
     | - SQL area   |   | - SQL area   |
     | - work area  |   | - work area  |
     +-------+------+   +------+-------+
             |                 |
             +--------+--------+
                      v
               TEMP tablespace
         (when operations spill)
~~~

The diagram illustrates architectural relationships; it does not imply every process always has exactly one work area or must always use TEMP. One execution plan can require multiple work areas; multiple statements can also execute sequentially on the same process.

### 1.1 PGA Belongs to a Process, Not a Fixed Block Allocated per User

The PGA is **private memory belonging to a server/background process**. In the commonly seen dedicated server model, one session works with a dedicated server process, and that process's PGA serves operations requiring private memory. With shared server, multiple sessions may be served sequentially by shared server processes; UGA placement and session-to-process mapping differ from dedicated server.

Therefore, do not oversimplify by saying "each user gets exactly 100 MB of PGA", "every session has an identical separate PGA", or "setting PGA to 8 GB means every SQL statement can use 8 GB". Actual allocated memory varies with:

- The number of processes and currently executing SQL operations.
- The type of operation needing sort/hash and the size of intermediate data.
- Work area management policy and instance-wide memory pressure.
- Query degree of parallelism.
- Other PGA allocations beyond SQL work areas.

Oracle manages aggregate demand across many processes; memory allocation and reclamation are not like pre-slicing a fixed chunk for each connection.

### 1.2 PGA Does Not Replace the Buffer Cache

The SGA buffer cache holds copies of read/modified data blocks so multiple SQL statements can reuse them. PGA work areas primarily hold **intermediate data serving execution algorithms**, such as rows/keys to be sorted or the hash table for one side of a join.

For example, an SQL query reads 100,000 rows from a table:

- Blocks containing table data may be accessed via the SGA buffer cache or another appropriate read mechanism.
- If the SQL needs to sort 100,000 rows, the sort operation can use an SQL work area in the serving process's PGA.
- If the work area is insufficient for the entire operation, Oracle may write intermediate runs/partitions to TEMP.

Thus, buffer cache shortages and work area shortages **have different causes, different observation signals, and different tuning approaches**.

## 2. What Is an SQL Work Area?

An **SQL work area** is a memory region used by an execution plan operation to process intermediate datasets. It is a major consumer of PGA activity, yet **not the entirety of the PGA**.

In an execution plan, several operations commonly require a work area:

| Execution Plan Operation | Goal | Typical Intermediate Data Requiring Memory |
|---|---|---|
| `SORT ORDER BY` | Sort data per `ORDER BY` | Sort keys/rows and row reference info |
| `SORT GROUP BY` | Group rows using a sort algorithm | Rows or group keys in processing order |
| `SORT UNIQUE` | Eliminate duplicates via sorting | Values/keys needed for comparison and deduplication |
| `WINDOW SORT` | Support certain analytic/window functions | Partition/order data serving the window |
| `HASH JOIN` | Join datasets using a hash table | Hash table of the build side and partitions if needed |
| `HASH GROUP BY` | Group rows using a hash structure | Hash table containing group keys and aggregate values |

These are **operations that may appear**, not a mandatory list for every `ORDER BY`, `JOIN`, or `GROUP BY`. The optimizer may choose a different algorithm: for instance, a query reading data already ordered from an index may not need a separate sort, or a small/selective join may use nested loops instead of a hash join.

### 2.1 One SQL Statement Can Have Multiple Work Areas

Consider:

~~~sql
SELECT c.region,
       SUM(s.amount) AS sales_amount
FROM sales s
JOIN customers c
  ON c.customer_id = s.customer_id
WHERE s.sale_date >= DATE '2026-01-01'
GROUP BY c.region
ORDER BY sales_amount DESC;
~~~

A valid execution plan might look like:

~~~text
SORT ORDER BY                <- sort total sales descending
  HASH GROUP BY              <- compute SUM by region
    HASH JOIN                <- join SALES with CUSTOMERS
      TABLE ACCESS ... SALES
      TABLE ACCESS ... CUSTOMERS
~~~

If the optimizer chooses this structure, the SQL has multiple operations potentially requiring work areas: `HASH JOIN`, `HASH GROUP BY`, and `SORT ORDER BY`. They do not necessarily consume peak memory all at the same instant; active timing depends on how the engine executes the plan.

The key point is that **the number of work areas relates to physical operations and actual execution instances**, not just the number of SQL statements or tables in the query.

### 2.2 Work Areas Are Typically Allocated Dynamically

Under automatic policy, Oracle estimates and manages memory sizes appropriate to operations while adapting to overall demand. A small work area may finish in the PGA. The exact same operation under high concurrent load may receive less memory and have to read/write TEMP.

A work area finishing its work does not mean the server process immediately returns all of its PGA to the operating system. Oracle and its memory allocator can reuse allocated chunks; hence **PGA allocated** and **PGA currently used** are two distinct concepts.

## 3. What Happens When Oracle Sorts Data?

Suppose:

~~~sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE order_date >= DATE '2026-01-01'
ORDER BY total_amount DESC, order_id;
~~~

Oracle must return results in the requested order. If the access path does not already produce the required ordering, the execution plan may include `SORT ORDER BY`.

### 3.1 Sufficient Memory Case: In-Memory Sort

Conceptually, the steps are:

1. Oracle retrieves qualifying rows after applying pushable predicates.
2. The sort operation holds the required structures inside its work area.
3. Oracle compares the `total_amount` and `order_id` keys in the requested order.
4. Rows are returned in sorted order.

When memory suffices for the execution algorithm, the operation can finish **without writing intermediate sort data down to TEMP**. This is typically called **optimal** work area execution. "Optimal" here classifies the operation's memory/TEMP usage; it does not assert that the overall SQL has the best possible execution plan.

### 3.2 Insufficient Memory Case: External Sort and TEMP

When the work area cannot hold all the data:

1. Oracle sorts a portion of the data in memory.
2. Processed portions can be written out as intermediate runs in TEMP.
3. Oracle reads and merges the runs to produce the ordered result.
4. If available memory is very small relative to the data, the process may require multiple read/write passes.

~~~text
Row source with many rows
         |
         v
    SORT work area (PGA)
         |
   +-----+------+
   |            |
Enough mem   Not enough mem
   |            |
Sort in      Create runs and
PGA          write to TEMP
   |            |
   |       Read/merge from TEMP
   |            |
   +-----+------+
         v
     ORDER BY result
~~~

Data in TEMP here is **intermediate scratch data for computation**, not a persistent copy of business data. Once the operation and related resources finish, Oracle manages freeing/reusing temporary space via its internal mechanisms.

### 3.3 Factors That Make Sorting Memory-Intensive

Sorting 10,000 narrow keys is not the same as sorting 10,000 wide rows. Work area demand depends significantly on:

- **Input row count** after filtering, not just the row count shown on screen.
- **Row width and sort expressions** that the plan must carry through.
- **Number of columns and ordering rules**, including distinguishing many equal values.
- **Operations preceding/following the sort**, such as a join expanding the dataset.
- **Concurrent executions** and the resources Oracle can allocate to work areas.

For example, `SELECT * ... ORDER BY ...` on rows with many large columns can create substantially different processing demand than sorting only narrow keys. However, the optimizer may defer fetching columns or choose plan variants, so rely on the **actual execution plan** rather than multiplying row count by row size and treating that as exact PGA usage.

### 3.4 Does Every ORDER BY Produce a SORT ORDER BY?

No. An index can provide ordering aligned with the filter predicates and sort direction. For example:

~~~sql
CREATE INDEX idx_orders_customer_date
ON orders (customer_id, order_date DESC, order_id DESC);

SELECT order_id, order_date, total_amount
FROM orders
WHERE customer_id = :p_customer_id
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

When appropriate, Oracle can leverage index order to fetch a customer's most recent records without sorting the entire result set. Yet it is **not forced** to choose this index: the decision still depends on statistics, selectivity, and cost.

Queries using `FETCH FIRST 20 ROWS ONLY` can also be optimized with top-N strategies such as `SORT ORDER BY STOPKEY`, which differs from sorting the entire result set to return all rows. Creating an index solely to eliminate a sort also carries costs: storage, DML maintenance overhead, and sometimes poor efficiency for reports scanning most of a table.

## 4. Hash Join: How Work Areas Store Hash Tables

When joining two datasets with equality conditions, the optimizer may select a **hash join**. The basic model usually has two phases:

1. **Build:** take one side of the join—typically the side predicted to be smaller or better suited as the build input—and build an in-memory hash table on the join key inside the work area.
2. **Probe:** read the other side; hash its join key, look up matching rows in the hash table, and verify join conditions to emit results.

Example:

~~~sql
SELECT c.segment, SUM(s.amount) AS total_amount
FROM sales s
JOIN customers c
  ON s.customer_id = c.customer_id
GROUP BY c.segment;
~~~

Assuming `CUSTOMERS` is small and `SALES` is large:

~~~text
CUSTOMERS (build input)                 SALES (probe input)
        |                                      |
        v                                      |
Build hash table in SQL work area (PGA)        |
        |                                      |
        +------------- HASH JOIN <-------------+
                           |
                           v
                    Matched join rows
                           |
                           v
                    HASH GROUP BY
~~~

This illustrates a hash join plan; the optimizer is free to choose build/probe order and other strategies. Hash join is particularly attractive when joining relatively large datasets, whereas nested loops can perform better when the outer side is small and the inner side has a highly selective index.

### 4.1 When the Hash Table Fits in PGA

Oracle can keep the required hash structure in the work area and probe directly. This avoids intermediate I/O caused by the hash join, making the operation fast when other factors are equal.

### 4.2 When the Hash Table Exceeds Allocated Memory

Oracle can split the join inputs into **hash partitions**, spill intermediate partitions down to TEMP, and process them piece by piece as memory allows:

~~~text
Build + Probe inputs
        |
        v
  Hash partitioning
        |
        +----> Partitions processed in PGA
        |
        +----> Partitions written to TEMP
                              |
                         read back / join
                              |
                              v
                         Join results
~~~

If the work area is heavily constrained, partitions may need further recursive partitioning or multiple passes. Increased intermediate reads/writes are one reason hash joins slow down under high PGA pressure.

**A hash join query using TEMP does not mean the base table was "moved to TEMP".** Oracle is only using TEMP for the algorithm's intermediate data.

### 4.3 Data and Statistics Affecting Hash Joins

Important factors include:

- Actual size of the build input after filtering and column projection.
- Distribution of the join key, including overly frequent keys causing skew.
- Discrepancy between optimizer-estimated rows and actual rows.
- Join cost relative to alternatives such as nested loops or sort-merge join.
- Work area allocation availability as query concurrency changes.
- Parallel execution potentially creating additional work areas across multiple parallel execution servers.

If the optimizer misestimates data volume, the plan may choose an unsuitable strategy. The first things to inspect are **statistics and actual cardinality**, rather than automatically increasing PGA or forcing `USE_HASH` hints on every join.

## 5. Hash Group By, Sort Group By, and Analytical Data

`GROUP BY` can be executed in several ways. Two common ones are:

**Hash group by:** builds a hash structure keyed by the group-by columns; for each input row, locates or creates the group and updates aggregates such as `SUM`, `COUNT`, `MIN`, and `MAX`. The work area can grow substantially when the number of distinct groups is huge or aggregate state is complex.

**Sort group by:** sorts by the group-by keys so rows belonging to the same group sit together. Cost depends on row/key count and sort strategy.

Example:

~~~sql
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM orders
WHERE order_date >= DATE '2026-01-01'
GROUP BY customer_id;
~~~

If there are one million orders across only 200 customers, the final number of groups is relatively small. If one million orders correspond to nearly one million customers, the group count is huge. Both cases have the same input row count, yet memory demand for hash aggregation can differ dramatically.

After `GROUP BY`, `ORDER BY total_amount DESC` can introduce **another sort operation** to order the groups by total amount. Do not confuse hash group by with sorted output: **GROUP BY does not guarantee output order**. Use `ORDER BY` only when business logic actually requires ordering.

`DISTINCT`, set operations, or window functions can also require similar sorts or hashes. However, identical SQL syntax does not lock in a single fixed operator: read the actual execution plan for your Oracle version and live data.

## 6. Three Work Area Execution Modes: Optimal, One-Pass, Multi-Pass

Oracle commonly classifies each work area execution according to allocated memory versus operation demand:

| Mode | Conceptual Meaning | Typical Impact |
|---|---|---|
| **Optimal** | Operation executes within allocated memory, requiring no TEMP writes/reads for its intermediate data | Minimal intermediate I/O, usually fastest under equal conditions |
| **One-pass** | Memory cannot hold all intermediate data; operation uses TEMP yet can complete required processing with one extra algorithmic pass | Adds TEMP I/O and wait time |
| **Multi-pass** | Memory is far too small for the data/algorithm, forcing repeated partitioning/merging over multiple passes | Intermediate I/O climbs substantially; usually a sign to investigate |

This is a general classification, not a formula saying "optimal = 1 table scan, one-pass = 2 table scans". Passes refer to **processing the work area's intermediate data**, not necessarily counting scans of the base table. Sort and hash algorithms also do not execute identically.

### 6.1 Example: Same SQL, Different Memory Conditions

A customer-grouping report might execute as follows:

~~~text
                        SAME SQL
                           |
         +-----------------+-----------------+
         |                 |                 |
   Plenty of free RAM   Higher concurrency   High memory pressure
         |                 |                 |
   Large work area   Smaller work area   Tiny work area
         |                 |                 |
      OPTIMAL           ONE-PASS           MULTI-PASS
         |                 |                 |
   Little/no TEMP    Additional TEMP     Multiple passes
   for operation       read/write          through TEMP
~~~

The diagram only illustrates how execution mode can shift. Oracle can also change plans, adjust dynamic allocations, change DOP, or apply other optimizations, so the mode is not determined solely by "free RAM".

### 6.2 When Is TEMP Usage a Problem?

Not every use of TEMP is an error. A large historical report might deliberately use TEMP to complete accurately when keeping all intermediate data in RAM would be impractical. Whether it is a problem depends on:

- Report completion time SLA.
- TEMP I/O rate, TEMP space consumed, and work area pass counts.
- Whether multi-pass executions or spikes appear when multiple SQLs run concurrently.
- Impact on business transactions sharing the same instance.
- Available memory/storage and the cost of changing the query plan.

## 7. How Does Oracle Automatically Manage PGA and Work Areas?

Three commonly encountered parameters:

### 7.1 PGA_AGGREGATE_TARGET — Instance-Wide Memory Target

`PGA_AGGREGATE_TARGET` defines an **aggregate target** for Oracle to coordinate PGA usage across eligible components, particularly under automatic work area management. It is a **target, not a hard per-session limit, per-query limit, or even an absolute immutable ceiling on total PGA**.

For example, assuming a PGA target of 4 GiB:

- It does not mean every session gets 4 GiB.
- It does not mean Oracle pre-reserves 4 GiB of idle RAM.
- It does not guarantee 10 concurrent queries will each receive 400 MiB.
- Actual total PGA can exceed the target due to various allocation types and pressure.

Oracle must balance many processes and operations, so **total concurrent load** matters more than the memory figure of a single query running in isolation.

### 7.2 WORKAREA_SIZE_POLICY — AUTO vs. MANUAL

`WORKAREA_SIZE_POLICY` controls how SQL work areas are sized:

| Value | Meaning | When Used |
|---|---|---|
| **AUTO** | Oracle automatically manages memory sizing for SQL work areas according to configured mechanisms/limits | Standard and preferred approach in most modern systems |
| **MANUAL** | Work area sizing relies on manual settings such as `SORT_AREA_SIZE` and `HASH_AREA_SIZE` | Mainly needed to understand legacy systems or controlled testing |

The parameters `SORT_AREA_SIZE` and `HASH_AREA_SIZE` **are not direct per-sort/per-hash tuning knobs when AUTO is active**. Switching to MANUAL just to force one query faster can destabilize concurrency management, so it is not the default tuning path.

### 7.3 PGA_AGGREGATE_LIMIT — Protective Limit

`PGA_AGGREGATE_LIMIT` sets a total PGA threshold acting as a **protective limit** depending on Oracle feature and version. When total PGA exceeds the limit and cannot be reclaimed through management mechanisms, Oracle may abort the call or terminate eligible sessions/processes; certain process types are handled differently according to Oracle rules.

Key distinction:

~~~text
PGA_AGGREGATE_TARGET  = target level for Oracle to manage and balance
PGA_AGGREGATE_LIMIT   = protective ceiling on total PGA, with enforcement when exceeded
~~~

Do not treat `LIMIT` as a "pre-allocation" for an SQL statement; nor should you raise it endlessly just to hide a memory-hungry query. If you hit PGA limit errors, investigate the SQL, concurrency, other PGA consumers, and available host memory.

### 7.4 Overall Memory Management Modes

Some deployments also use `MEMORY_TARGET` so Oracle coordinates memory between SGA and PGA via Automatic Memory Management. Other environments set `SGA_TARGET` and `PGA_AGGREGATE_TARGET` separately or have memory managed by the database service.

Therefore, before proposing a PGA increase, verify the **version, edition, deployment environment (on-premises/managed service), current memory configuration, and actual RAM limits**. A configuration valid on one Oracle instance does not necessarily apply verbatim to another instance or a PDB in a multitenant system.

## 8. Why Do Parallelism and High Session Counts Quickly Create PGA Pressure?

Suppose an SQL statement uses a hash join followed by a sort. When one session runs it, Oracle may allocate enough work area memory to avoid TEMP. When many sessions run the same query or other reports concurrently, memory demand rises across the entire instance.

With **Parallel Query**, a single SQL statement can be divided across multiple parallel execution servers. Each of those processes can have its own work areas for its portion of the work, plus coordination and data-transfer overhead. Process count, operation count, and plan shape determine actual consumption; you cannot reliably assume "SQL PGA = DOP × one work area" while ignoring other plan and coordination allocations.

~~~text
                          One report
                              |
                     Parallel execution
                   /          |          \
              PX server   PX server   PX server
               PGA          PGA          PGA
            hash/sort     hash/sort     hash/sort
                   \          |          /
                        Combined result

    + Other OLTP sessions and reports sharing the same instance
~~~

Increasing parallelism can sometimes shorten **one** report when resources are plentiful, yet slow the whole system when multiple reports run together because CPU, I/O, PGA, and TEMP become contended. Evaluating parallelism requires concurrency testing, not just benchmarking one query on an idle machine.

## 9. Observing PGA Configuration and Usage via SQL

The following examples primarily **read information** from dynamic performance views. Ordinary accounts may lack privileges on `V$` views; use an appropriately authorized account or ask a DBA to run the queries. Do not grant `SELECT ANY DICTIONARY` or `SYSDBA` to an application solely for diagnostics.

### 9.1 Viewing Active Parameters

~~~sql
SELECT name, display_value
FROM v$parameter
WHERE name IN (
    'pga_aggregate_target',
    'pga_aggregate_limit',
    'workarea_size_policy',
    'memory_target',
    'sga_target'
)
ORDER BY name;
~~~

The output shows how Oracle is configured to manage memory. Displayed values may use Oracle units/formatting; convert appropriately when comparing. This query **does not change configuration**.

### 9.2 Monitoring Instance-Wide Usage with V$PGASTAT

~~~sql
SELECT name, value, unit
FROM v$pgastat
WHERE name IN (
    'aggregate PGA target parameter',
    'aggregate PGA auto target',
    'global memory bound',
    'total PGA allocated',
    'total PGA inuse',
    'maximum PGA allocated',
    'over allocation count',
    'cache hit percentage',
    'extra bytes read/written'
)
ORDER BY name;
~~~

Several values in `V$PGASTAT` are cumulative or depend on startup time and version; when investigating trends, collect **multiple samples over time** rather than drawing conclusions from a single snapshot.

| Metric | Conceptual Reading |
|---|---|
| `total PGA allocated` | Total PGA currently allocated by Oracle at measurement time, including in-use and reusable portions |
| `total PGA inuse` | Portion of PGA actively in use by processes at measurement time |
| `maximum PGA allocated` | Peak total PGA allocated recorded within the statistics interval |
| `aggregate PGA auto target` | Portion of PGA target Oracle currently reserves for automatic work area management |
| `global memory bound` | Calculated per-work-area memory ceiling under automatic management; dropping values can indicate high memory contention |
| `over allocation count` | Counter reflecting times Oracle had to exceed the PGA target under corresponding conditions |
| `extra bytes read/written` | Additional read/write volume for work areas that did not execute completely optimal |
| `cache hit percentage` | Aggregate work area efficiency metric, **not the SGA buffer cache hit ratio** |

Do not use a fixed percentage threshold to declare every system "has enough PGA". For instance, a high cache hit percentage during quiet hours says nothing about behavior when many analytical queries run concurrently. Watch counters, growth rates, query durations, and TEMP activity.

### 9.3 Observing PGA per Server Process

In the dedicated server model, sessions can be joined to processes:

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.program,
       ROUND(p.pga_used_mem / 1024 / 1024, 1) AS pga_used_mb,
       ROUND(p.pga_alloc_mem / 1024 / 1024, 1) AS pga_alloc_mb,
       ROUND(p.pga_max_mem / 1024 / 1024, 1) AS pga_max_mb
FROM v$session s
JOIN v$process p
  ON p.addr = s.paddr
WHERE s.type = 'USER'
ORDER BY p.pga_alloc_mem DESC;
~~~

`PGA_USED_MEM`, `PGA_ALLOC_MEM`, and `PGA_MAX_MEM` show different perspectives of used, allocated, and peak recorded memory at the process level. With shared server or parallel execution, do not mechanically assume **one user session = one process = the entire SQL's work areas**. Some work areas may belong to processes other than the one seen on the main session.

### 9.4 Viewing Executed Work Areas via V$SQL_WORKAREA

`V$SQL_WORKAREA` provides aggregate metrics by SQL and operation using a work area:

~~~sql
SELECT sql_id,
       operation_id,
       operation_type,
       policy,
       last_execution,
       total_executions,
       optimal_executions,
       onepass_executions,
       multipasses_executions,
       ROUND(last_memory_used / 1024 / 1024, 1) AS last_memory_mb,
       ROUND(last_tempseg_size / 1024 / 1024, 1) AS last_temp_mb
FROM v$sql_workarea
WHERE sql_id = :p_sql_id
ORDER BY operation_id;
~~~

Here `:p_sql_id` is a **bind parameter** supplied by the client. The `SQL_ID` can be found from active SQL info, SQL monitoring, or an appropriate view if authorized. Rows represent metrics of **work area operations**, not necessarily the exact total memory of the entire SQL statement at every instant.

The optimal/one-pass/multi-pass counters show execution distribution across modes, which is more informative than looking solely at the most recent execution. `LAST_TEMPSEG_SIZE` can be `NULL` if no temporary segment was used for that operation/run. Statistics retention and readability depend on configuration, version, and cursor lifetime in the shared pool.

### 9.5 Viewing Active Work Areas

When looking for which operation is currently consuming memory/TEMP at observation time:

~~~sql
SELECT sid,
       sql_id,
       operation_type,
       ROUND(actual_mem_used / 1024 / 1024, 1) AS actual_mb,
       ROUND(max_mem_used / 1024 / 1024, 1) AS max_mb,
       ROUND(tempseg_size / 1024 / 1024, 1) AS temp_mb,
       number_passes
FROM v$sql_workarea_active
ORDER BY actual_mem_used DESC;
~~~

This view is an **instantaneous snapshot** of currently active work areas, so a very brief query may finish before sampling. Seeing zero rows does not prove no sort/hash spill happened during the past hour.

### 9.6 Observing TEMP Segments

TEMP is used for multiple purposes, including sort/hash spills. You can inspect sessions currently holding temporary segments:

~~~sql
SELECT username,
       sql_id,
       tablespace,
       segtype,
       blocks
FROM v$tempseg_usage
ORDER BY blocks DESC;
~~~

`BLOCKS` is a block count, not automatically bytes or MB. When converting, you must know the block size of the corresponding tablespace; never hardcode multiplication by 8 KiB unless configuration confirms it. Beyond sort/hash, other reasons can also increase TEMP usage, so combine `SQL_ID`, operation type, and plan before blaming `ORDER BY`.

## 10. Reading Execution Plans to Find Sort, Hash, and Memory/TEMP

An execution plan answers **which physical operations Oracle chose** to execute the SQL. Example:

~~~text
Id  Operation
--  ----------------------------
 0  SELECT STATEMENT
 1   SORT ORDER BY
 2    HASH GROUP BY
 3     HASH JOIN
 4      TABLE ACCESS FULL SALES
 5      TABLE ACCESS FULL CUSTOMERS
~~~

Seeing `SORT ORDER BY` means the SQL has a sorting step. Seeing `HASH JOIN` means it has a hash-based join step. However, **merely seeing the operation name does not prove it spilled to TEMP** or how much PGA it used.

### 10.1 EXPLAIN PLAN vs. Actual Execution Plan

~~~sql
EXPLAIN PLAN FOR
SELECT customer_id, SUM(total_amount) AS total_amount
FROM orders
GROUP BY customer_id
ORDER BY total_amount DESC;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` describes an estimated plan in the explain context, not proof of all operations actually executed or how much PGA was allocated. It can differ from the actual running SQL's plan, especially when bind conditions and statistics differ.

To observe actual runtime statistics, you can collect them for a practice query:

~~~sql
SELECT /*+ gather_plan_statistics */
       customer_id,
       SUM(total_amount) AS total_amount
FROM orders
GROUP BY customer_id
ORDER BY total_amount DESC;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(NULL, NULL, 'ALLSTATS LAST +MEMSTATS')
);
~~~

Depending on version and cursor privileges, output can include estimated/actual per-operation info and memory/TEMP columns such as `OMem`, `1Mem`, `Used-Mem`, and `Used-Tmp`. Displaying these columns depends on the plan, statistics gathering, and supported features. If a query must fetch all results to complete an operation, fetching only the first few rows may mean runtime stats do not reflect a full execution.

`DBMS_XPLAN.DISPLAY_CURSOR` may require read privileges on related dynamic performance views. If the "last cursor" does not point to the query you want to inspect, locate the exact `SQL_ID` and child cursor via monitoring tools and pass both values to `DISPLAY_CURSOR`.

### 10.2 Reading Estimated vs. Actual Rows

When execution statistics are available, compare optimizer-predicted rows against actual rows at each plan branch:

- Underestimating rows on the hash join build side can lead to choosing a suboptimal algorithm.
- Unselective filters send more rows into a sort than expected.
- Multiple joins before `GROUP BY` can multiply intermediate row counts before aggregation.
- Skewed key distributions can degrade join/aggregation efficiency.

Investigate table/column statistics, predicates, indexes, and data characteristics before trying to increase memory.

## 11. Hands-On Practice in a Private Oracle Schema

This section uses **synthetic data** to observe operations the optimizer may choose. Run DDL only in an authorized practice schema; never run it in a business schema containing real data. Table creation statements carry an implicit commit, so `ROLLBACK` cannot undo a `CREATE TABLE` once it succeeds.

### 11.1 Creating Two Sample Tables

~~~sql
CREATE TABLE pga_lab_customers AS
SELECT LEVEL AS customer_id,
       CASE MOD(LEVEL, 4)
           WHEN 0 THEN 'RETAIL'
           WHEN 1 THEN 'SMB'
           WHEN 2 THEN 'ENTERPRISE'
           ELSE 'PARTNER'
       END AS segment
FROM dual
CONNECT BY LEVEL <= 1000;

CREATE TABLE pga_lab_sales AS
SELECT LEVEL AS sale_id,
       MOD(LEVEL - 1, 1000) + 1 AS customer_id,
       DATE '2026-01-01' + MOD(LEVEL, 300) AS sold_on,
       ROUND(MOD(LEVEL * 37, 10000) / 100, 2) AS amount,
       RPAD('X', 120, 'X') AS note
FROM dual
CONNECT BY LEVEL <= 100000;
~~~

`PGA_LAB_CUSTOMERS` has 1,000 rows; `PGA_LAB_SALES` has 100,000 rows, each with simulated sales data. These counts are illustrative; on configurations with plenty of RAM, both queries may finish without needing TEMP.

If the schema permits, gather statistics so the optimizer has metrics:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(USER, 'PGA_LAB_CUSTOMERS');
    DBMS_STATS.GATHER_TABLE_STATS(USER, 'PGA_LAB_SALES');
END;
/
~~~

Creating data, gathering statistics, and running large SQLs must respect the learning environment's quotas/resource limits. Never intentionally set `PGA_AGGREGATE_TARGET` ultra-low or fill up TEMP just to "trigger an error" on a shared database.

### 11.2 Query That May Require SORT ORDER BY

~~~sql
SELECT /*+ gather_plan_statistics */
       sale_id,
       amount,
       note
FROM pga_lab_sales
ORDER BY amount DESC, sale_id;
~~~

When no access path already provides the requested ordering, the plan may display `SORT ORDER BY`. This example itself returns many rows, so run it only if the output volume and resource usage are acceptable. An application usually only needs top-N or pagination, requiring query redesign rather than loading every row into the UI.

After running and fetching all rows, use `DBMS_XPLAN.DISPLAY_CURSOR` as shown in section 10 to view the actual plan/memory if authorized.

If you only want a small number of rows:

~~~sql
SELECT sale_id, amount
FROM pga_lab_sales
ORDER BY amount DESC, sale_id
FETCH FIRST 20 ROWS ONLY;
~~~

The optimizer may use top-N optimization. The two queries **do not have the same physical requirements**, so do not take memory stats from the top-N query and conclude the sort cost for returning all 100,000 rows.

### 11.3 Query That May Use HASH JOIN and HASH GROUP BY

~~~sql
SELECT /*+ gather_plan_statistics */
       c.segment,
       COUNT(*) AS sale_count,
       SUM(s.amount) AS total_amount
FROM pga_lab_sales s
JOIN pga_lab_customers c
  ON c.customer_id = s.customer_id
GROUP BY c.segment
ORDER BY total_amount DESC;
~~~

Inspect the actual plan. You may see `HASH JOIN`, `HASH GROUP BY`, `SORT ORDER BY`, or another equivalent plan. This depends on version, optimizer, statistics, and environment; do not consider the absence of a specific operator an SQL error.

If you have access to `V$SQL_WORKAREA`, look up the exact `SQL_ID` of the query above and inspect `OPERATION_TYPE`, `LAST_EXECUTION`, and the optimal/one-pass/multi-pass counters. That links the work area concept directly to the executed operation.

### 11.4 Observations to Record

| Observation Question | Where to Look | Appropriate Conclusion |
|---|---|---|
| Did the SQL use sort or hash? | Actual execution plan | Identify the exact operator rather than guessing from SQL syntax |
| Was TEMP used for the operation? | Memory stats, `V$SQL_WORKAREA`, `V$SQL_WORKAREA_ACTIVE` | Read TEMP amount and execution mode if metrics are available |
| At runtime, how much PGA did the instance use? | `V$PGASTAT` | Read snapshot or compare sample series, distinguishing allocated vs. inuse |
| Is there database-wide TEMP pressure? | `V$TEMPSEG_USAGE`, DBA storage metrics | Associate TEMP consumption with the right session/SQL/operator |
| Is there contention under concurrent runs? | SQL duration, CPU, I/O, PGA/TEMP activity | Compare single-user run against concurrent runs |

After practice, if you need to clean up tables, follow practice-schema management procedures and confirm nobody else is using them. Never copy dangerous data-deletion commands into production scripts just for lab cleanup.

## 12. Optimizing Sorts/Hashes That Consume Excessive PGA or TEMP

When you see a query with `SORT ORDER BY` or `HASH JOIN` using huge TEMP, reasoning should start from **the data and the actual SQL requirements**.

### 12.1 Reduce Data Entering the Work Area

For example, a query sorting all orders:

~~~sql
SELECT order_id, customer_id, total_amount
FROM orders
ORDER BY created_at DESC;
~~~

If the user only needs one customer's orders from the last 30 days and the 20 newest rows, express the exact requirement:

~~~sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE customer_id = :p_customer_id
  AND created_at >= :p_from_date
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Gains can come from early filtering, fewer rows, top-N optimization, and an appropriate index. Fixing the query requirement is usually far better than trying to find enough RAM to sort the entire table.

### 12.2 Choose Suitable Access Paths and Algorithms

- **Indexes supporting filtering and ordering:** can avoid or reduce sorting, especially for transactions fetching a few rows. However, indexes carry DML cost and make little sense for large full-scan reports.
- **Verify join conditions:** avoid under-constrained joins that unexpectedly multiply row counts, bloating hash tables and input to subsequent sorts.
- **Optimizer statistics:** cardinality and data distribution metrics help choose proper join orders and access methods.
- **Narrow intermediate width:** carry only needed columns through pipeline steps when query semantics permit.
- **Partitioning or pre-aggregation:** for large historical data, partition pruning or materialized views/analytical summaries can reduce rows requiring processing.

Do not force the optimizer to use nested loops, hash joins, or indexes on every query with hints just because a single plan looked slow. Compare using data, binds, and concurrency matching production.

### 12.3 Distinguishing Three Remediation Paths

| Symptom | Possible Cause | First Direction to Check |
|---|---|---|
| Sorting an overly large result set | Query lacks filters/pagination; ordering everything | Verify requirement, predicates, indexes, top-N |
| Abnormally large hash join build input | Bad join order/cardinality estimate, skewed data | Actual rows, statistics, filters, and join structure |
| Query is fast alone yet spills when many run together | Work area/PGA contention; instance-wide pressure | Concurrency, `V$PGASTAT`, `V$SQL_WORKAREA`, parallelism |
| TEMP grows rapidly during analytics | Sort/hash spills or other operations using TEMP | `V$TEMPSEG_USAGE`, actual plan, and operators |
| High PGA allocated yet noticeably lower PGA inuse | Processes holding reusable allocated memory | Distinguish allocated/inuse and trend series; avoid declaring a leak from one snapshot |
| PGA limit exceeded errors | Total usage too high relative to limit policy | Top consuming processes/sessions, target/limit config, heavy queries |

### 12.4 When Should You Adjust Memory?

Consider increasing the PGA budget only when evidence shows:

1. Multiple business-justified operations consistently run one-pass/multi-pass.
2. CPU/I/O and especially TEMP show significant intermediate overhead.
3. The host still has adequate physical memory after accounting for SGA, the OS, and other processes.
4. The change will not harm stability for concurrent loads or other applications sharing the instance.

Raising `PGA_AGGREGATE_TARGET` can reduce spills on some systems, yet **does not guarantee every query will receive enough memory**; concurrency, limits, and algorithms still govern outcomes. Conversely, over-allocating relative to physical RAM can push the host into swapping/paging or starve the SGA/OS, slowing the entire system down.

Changing instance/PDB parameters is an operationally impactful task requiring DBA evaluation and change control. This lesson uses only read/observation SQL queries and does not prescribe blind `ALTER SYSTEM` commands.

## 13. Distinguishing PGA/TEMP from Other Errors and Phenomena

### ORA-01652: Unable to Extend Temp Segment

This error can occur when an operation needs more temporary space and the corresponding tablespace cannot allocate it. Causes include TEMP running out of capacity, file autoextend limits, multiple sessions occupying TEMP, or a query generating huge intermediate data. **Do not jump to concluding that increasing PGA alone will eliminate the error**: identify who is consuming TEMP, the plan, and storage policies.

### ORA-04036: PGA Memory Used by the Instance Exceeds PGA_AGGREGATE_LIMIT

This is an indicator tied to the total PGA ceiling. Examine pressure at error time, consuming processes/sessions, SQL operations, parallelism, and limit policies. It is distinct from running out of TEMP storage space.

### ORA-04030: Out of Process Memory

May relate to a memory allocation failure for a process; do not equate it with a sort simply spilling to TEMP. Investigate the error and trace/diagnostic info under actual operating conditions.

### ORA-01555: Snapshot Too Old

This error relates to providing a consistent-read image from UNDO for a query, commonly seen with long-running queries and concurrent data changes. It is **different** from insufficient PGA or insufficient TEMP. A query slowed down by sort/hash can indirectly widen the risk window, yet there is no equivalence "sort spill = ORA-01555".

### Slow SQL Even Without Spills

Even an `OPTIMAL` operation can still be slow due to reading large base data, heavy CPU, high I/O, lock waits, network/fetch overhead, or an unsuitable query plan. PGA tuning is only one part of SQL tuning.

## 14. Common Misconceptions

**"PGA is a shared cache for all SQL, like the buffer cache."** Incorrect. PGA is private memory per process; the buffer cache belongs to the shared SGA. Work areas process intermediate data and do not replace the SGA.

**"If PGA_AGGREGATE_TARGET = 8 GB, every SQL statement can use 8 GB."** Incorrect. It is an instance-wide aggregate target managed across many concurrent processes and workloads.

**"Every ORDER BY writes to TEMP."** Incorrect. Sorting can complete in PGA, use top-N optimization, or read data already in the needed order without a separate sort.

**"HASH JOIN is always faster than NESTED LOOPS."** Incorrect. Hash join typically suits large datasets under certain conditions; nested loops can be more efficient with a small outer set and selective indexes.

**"TEMP usage means Oracle has run out of RAM."** Incorrect. An operation may be given a smaller work area under concurrent pressure or management bounds even when the host still has memory; there are also many different reasons TEMP is used.

**"ONE-PASS means Oracle scans the base table exactly once."** Incorrect. Pass classification describes how intermediate data is processed with available memory, not the number of scans on the base table.

**"Increasing PARALLEL makes reports faster without affecting OLTP."** Incorrect. Parallel execution can increase CPU, PGA, I/O, and TEMP contention against other SQL statements.

**"Just increasing PGA optimizes the query."** Incorrect. If an SQL statement joins extra rows or sorts huge amounts of unnecessary data, adding RAM only trims part of the cost of an unsuitable plan.

## 15. Synthesis Scenario: Revenue Report Slows Down the API

Suppose an ordering application uses Oracle Database for two workloads:

- An order-creation API running continuously that requires low latency.
- A revenue report running a `JOIN` across several large tables, `GROUP BY` customer, and then `ORDER BY` revenue.

When the report runs alone, execution time is acceptable. During peak hours, multiple dashboard sessions run concurrently and `V$SQL_WORKAREA` shows rising one-pass/multi-pass ratios; `V$TEMPSEG_USAGE` records many TEMP segments; API latency also rises, even without many row lock waits.

Investigation steps:

1. **Verify actual activity:** `SQL_ID`, plan, row counts across each join, work area types, execution time, and TEMP metrics; compare quiet periods against peak hours.
2. **Check report semantics:** does the dashboard really need to scan all history and sort every customer, or only fetch the top 20 for the current month?
3. **Evaluate joins and aggregation:** are there early filters, accurate statistics, row multiplication from missing join conditions, or an unusually large group count?
4. **Evaluate concurrency and parallelism:** are too many sessions running the same SQL, or is DOP inflating memory/CPU/TEMP demand?
5. **Select a strategy:** tune queries and indexes, throttle concurrency, use materialized views/summary tables, isolate analytical workloads, or adjust PGA if supported by evidence and resources.
6. **Re-measure under the same load:** report completion time, API latency (especially p95/p99), PGA allocated/inuse, pass counts, and TEMP I/O.

An improvement is meaningful only when the report produces **accurate figures**, meets freshness requirements, and the API does not degrade past acceptable thresholds. Achieving optimal mode for one sort does not by itself prove the whole system is tuned.

## 16. Self-Practice Questions

**Question 1.** Two queries return 100 rows, yet query A reads 100 rows from an index while query B scans 5 million rows and takes the top 100 after sorting. Must their PGA usage be identical?

*Hint:* No. The number of rows returned to the client does not directly reflect the row count and data width passing through earlier operators. B may use a larger work area, even with top-N optimization.

**Question 2.** An SQL query has `HASH JOIN` and `SORT ORDER BY`, yet `V$SQL_WORKAREA` shows both recent executions were optimal. Can we conclude the SQL used zero PGA?

*Hint:* No. Optimal specifically means processing the operation within appropriate memory; it does not mean "zero memory used". PGA also holds allocations beyond work areas.

**Question 3.** When scaling from one report to 30 concurrent reports, one-pass executions rise. Should `SORT_AREA_SIZE` be increased immediately?

*Hint:* Check `WORKAREA_SIZE_POLICY`, instance-wide PGA pressure, and process/parallelism counts. Under AUTO, `SORT_AREA_SIZE` is not the direct tuning knob assumed here. Reduce/tune workload and only adjust the PGA budget with solid justification.

**Question 4.** Why can `ORA-01652` and `ORA-04036` not be resolved with a single generic fix?

*Hint:* One error involves temporary segment space; the other involves the instance's total PGA limit. They can appear together under heavy workloads yet require separate diagnostics and remedies.

**Question 5.** When `EXPLAIN PLAN` shows `HASH JOIN`, why can you not conclude that the hash join just spilled 2 GiB to TEMP?

*Hint:* EXPLAIN PLAN is an estimated plan; memory/TEMP usage are runtime metrics. You need the actual plan, work area statistics, and TEMP usage data tied to the specific run.

## 17. Conclusion

In Oracle, the **PGA** is process-private memory, while an **SQL work area** is the memory portion serving operations such as `SORT ORDER BY`, `HASH JOIN`, and `HASH GROUP BY`. An operation can complete in memory (**optimal**) or spill to **TEMP** and execute across one or multiple passes when memory is insufficient. PGA and TEMP usage vary with intermediate data size, execution plan, resources, and concurrent workload.

To troubleshoot a slow sort/hash query, identify the exact operation in the **actual execution plan**, cross-reference **PGA/workarea statistics and TEMP usage**, and then optimize data volume, joins, group bys, and concurrency. Adjust the PGA budget only after understanding real demand and host memory capacity. This approach addresses the root cause of slowness and avoids speeding up one SQL statement at the expense of pressuring the entire Oracle Database.
