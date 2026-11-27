# Table Compression in Oracle: CPU Trade-offs, Capacity, and Feature/License Requirements

**Table compression** is a technique for reducing table storage consumption in Oracle Database by representing values or groups of values in compressed form. When the same amount of data occupies fewer blocks, the system can reduce physical I/O, shrink segment size, and sometimes improve memory cache efficiency. However, compressing and decompressing also consumes CPU, adds overhead during data writes/updates, and Oracle's compression modes carry **different technical prerequisites as well as licensing requirements**.

Therefore, deciding to compress a table is not just asking "how many GB will this save?". You must evaluate simultaneously: whether data has enough repetition to compress well, whether the table is read-heavy or write-heavy, how many blocks queries read, latency requirements, the cost of compressing existing data, partitioning design, Oracle version/edition, storage infrastructure type, and contractual feature entitlements.

This lesson focuses on **table data compression (table segment compression)** in Oracle Database storage. Backup compression, network compression, index compression, SecureFiles LOB compression, and In-Memory Column Store compression are mentioned to draw distinctions, not to be equated with table compression.

## 1. Where Does Table Compression Sit in the Storage Architecture?

Oracle organizes table data into **data blocks** inside **extents** belonging to a table or partition **segment**. A standard heap table stores records in row format, alongside block-management metadata, free space, and information needed for access/consistency.

Conceptual diagram:

~~~text
Logical table SALES
        |
        v
Table segment (or each partition has its own segment)
        |
   +----+----------+----------+
   |    |          |          |
 Extent 1       Extent 2    Extent ...
   |               |
   v               v
Data blocks     Data blocks
   |
   +-- Row data / metadata / free space
~~~

When a **row store compression** mode is enabled, Oracle stores row data inside blocks in a way that exploits repeated values or shorter representations, allowing more useful data to fit in the same number of blocks. In **Hybrid Columnar Compression (HCC)** modes, the organization and compression unit work differently: data is grouped into **compression units** and organized column-wise within each unit to achieve higher compression ratios for read-intensive data.

Key points:

- Compression **changes how data is stored on disk/storage**, not the logical table seen by applications through standard SQL.
- For the same table name and logical data, two compression modes can yield very different CPU costs, sizes, and DML characteristics.
- Compression does not create indexes, fix relational design, or eliminate the need for constraints, transactions, or optimizer statistics.
- Compression does not necessarily shrink **every** related object. Indexes, LOB segments, materialized views, and other structures have their own storage and compression mechanisms.

### 1.1 Why Is Data Compressible?

Consider an orders table with millions of records:

| order_id | status | region | channel |
|---:|---|---|---|
| 101 | PAID | HCM | WEB |
| 102 | PAID | HCM | WEB |
| 103 | PAID | HCM | WEB |
| 104 | CANCELLED | HN | APP |
| 105 | PAID | HCM | WEB |

Values like `PAID`, `HCM`, and `WEB` repeat frequently. Instead of storing full repeated strings identically for every row, compression techniques can reuse representations of identical values.

Conceptual illustration (not Oracle's exact physical block layout):

~~~text
Before compression:
PAID | HCM | WEB
PAID | HCM | WEB
PAID | HCM | WEB

After compression (conceptual):
Dictionary: #1=PAID, #2=HCM, #3=WEB
Rows:       #1/#2/#3, #1/#2/#3, #1/#2/#3
~~~

Actual compression depends on data types, repeated strings, value distribution, compression granularity, block size, load method, and specifics of each compression mode. Random data, data already compressed at another layer, or columns with mostly unique values may save very little.

## 2. Three Families of Table Compression to Distinguish

Oracle offers multiple compression mechanisms for different purposes. Syntax names, supportability, and usage rights vary by **release version, edition, cloud service, and storage hardware**.

| Compression Family | Primary Purpose | Suitable Write Path | Trade-offs |
|---|---|---|---|
| **Basic Table Compression** — typically `ROW STORE COMPRESS BASIC` | Reduce space for tables loaded/transformed via bulk or direct-path operations | CTAS, bulk/direct-path load, table/partition move | Conventional DML may not compress as effectively as bulk-created blocks; requires reorganization planning |
| **Advanced Row Compression** — `ROW STORE COMPRESS ADVANCED` | Compress row-formatted data while supporting read/write workloads with regular DML | Active tables with `INSERT`, `UPDATE`, `DELETE` | Additional CPU/metadata work when compressing or recompressing blocks; specific feature/license requirements |
| **Hybrid Columnar Compression (HCC)** — `COLUMN STORE COMPRESS FOR QUERY ...` or `... FOR ARCHIVE ...` | Aggressive compression for read-heavy, analytical, or historical archive data | Bulk load, cold data partitions, scans/reporting | Row-by-row updates are usually a poor fit; requires HCC-supported storage and specific license/edition checks |

These three families are not a mandatory ladder of "BASIC → ADVANCED → HCC." They serve **different operational patterns**. A constantly updated transactional table may fit Advanced Row Compression better than HCC; a read-mostly historical partition may fit HCC if infrastructure and licensing permit.

### 2.1 Quick Reference to SQL Syntax

Examples of declarations commonly seen on supported Oracle versions:

~~~sql
-- Basic Table Compression: data stored in row-store format.
CREATE TABLE orders_basic
ROW STORE COMPRESS BASIC
AS SELECT * FROM orders_source;

-- Advanced Row Compression: designed for row-store with DML.
CREATE TABLE orders_advanced
ROW STORE COMPRESS ADVANCED
AS SELECT * FROM orders_source;

-- HCC: requires compatible storage/edition environment.
CREATE TABLE orders_query_archive
COLUMN STORE COMPRESS FOR QUERY HIGH
AS SELECT * FROM orders_source;
~~~

These are **three separate illustrative options**, not a sequence to run back-to-back. `ORDERS_SOURCE` is merely a placeholder source name. Never test Advanced or HCC modes on a system without confirming usage rights and technical support. `CREATE TABLE ... AS SELECT` statements also create new tables, consume space, and do not automatically copy all constraints, indexes, triggers, or grants from the source table.

## 3. Basic Table Compression: Optimizing Large Bulk Loads

**Basic Table Compression** is a row-store compression format suited for data built or loaded in batches, rather than tables experiencing constant small interleaved updates.

### 3.1 Mechanism and Characteristics

Conceptually, Oracle uses compressed representations inside blocks to save space on repeated values. Operations structured as **direct-path/bulk** loads or segment rewrites are generally well-suited to producing compressed blocks.

Common scenarios include:

- Creating a new reporting table with `CREATE TABLE ... AS SELECT` (CTAS).
- Batch loading data through a direct-path write mechanism.
- Rewriting a table segment or partition using `ALTER TABLE ... MOVE` when operational procedures allow.
- Moving settled data to a historical partition and compressing it once it turns cold.

Note: **do not equate Basic Table Compression with "every INSERT is automatically compressed."** Under conventional-path DML, new or modified data may be stored differently from direct-path compressed blocks. Overall segment compression ratio can degrade over time if the workload continues heavy updates.

### 3.2 Read-Heavy, Write-Light Example

Suppose a company has a `SALES_HISTORY_2024` table loaded once after period close, and users primarily run:

~~~sql
SELECT region_code, SUM(net_amount) AS net_sales
FROM sales_history_2024
WHERE invoice_date >= DATE '2024-01-01'
  AND invoice_date <  DATE '2025-01-01'
GROUP BY region_code;
~~~

If compression lowers the table's block count, full table or partition scans can require less physical I/O. CPU still performs decompression/processing during reads. The result **can be faster** if I/O was the bottleneck, yet **can be slower** if CPU is already saturated or the data does not compress well.

## 4. Advanced Row Compression: Balancing Compression with Regular DML

**Advanced Row Compression** is designed to apply row-store compression in environments with conventional DML, not just bulk loads. Older docs or systems may mention **OLTP Table Compression** / `COMPRESS FOR OLTP`; modern syntax typically uses `ROW STORE COMPRESS ADVANCED`. Verify compatible syntax for your specific Oracle release.

### 4.1 How Does It Differ from Basic?

Suppose table `ORDERS` continuously receives orders and status changes:

~~~sql
INSERT INTO orders (order_id, customer_id, status)
VALUES (:p_order_id, :p_customer_id, 'NEW');

UPDATE orders
SET status = 'PAID'
WHERE order_id = :p_order_id;
~~~

In this workload, block organization must handle not just reads, but ongoing row inserts and updates over time. Advanced Row Compression includes mechanisms to manage compression alongside DML, avoiding the need to repeatedly run separate bulk operations to keep active data compressed.

However, "Advanced" **does not mean zero-cost DML**. Block compression or recompression can spike CPU at times, and updating a row still involves block space, undo/redo, transactions, and concurrency impacts. Workloads with highly volatile or poorly compressible data may not gain enough to offset the overhead.

### 4.2 Block-Level Compression and Update Effects

Inside a compressed block, repeated values can be referenced through shared structures. When a row is updated:

- The new value may match existing values or be completely distinct.
- The update can change the block's compressibility.
- The block may need extra management/recompression work per Oracle's algorithm.
- If insufficient space remains in place, row-management effects such as row migration can occur depending on storage and data growth.

Do not assume every `UPDATE` recompresses the entire table, or that one `UPDATE` always carries a fixed cost. Measure impact against real data and workloads.

### 4.3 When Is It Worth Considering?

Large tables with many repeated values across rows, read-heavy or mixed read/write workloads, and adequate CPU headroom are strong candidates to benchmark. Small tables, low-repetition data, ultra-tight write latency SLAs, or CPU-constrained systems usually require extra caution.

**Usage requirement:** Advanced Row Compression carries dedicated feature/licensing rules, typically tied to the **Oracle Advanced Compression** option in commercial licensing models. Never assume a feature is licensed just because a SQL statement succeeds; confirm entitlement by release, edition, cloud service, and contract before enabling on production data.

## 5. Hybrid Columnar Compression: Analytics and Cold Data Archival

**Hybrid Columnar Compression (HCC)** combines row-group organization (compression units) with columnar arrangement of values within each unit to compress aggressively, especially when columns hold repeated values or favorable distributions.

Concept of a compression unit:

~~~text
Logical rows:
row1: date1 | HCM | PAID | 150
row2: date2 | HCM | PAID | 200
row3: date3 | HCM | PAID | 400
row4: date4 | HCM | PAID | 500

HCC compression unit (illustrative):
date:   [date1, date2, date3, date4]
region: [HCM, HCM, HCM, HCM]  -> compresses efficiently
status: [PAID, PAID, PAID, PAID] -> compresses efficiently
amount: [150, 200, 400, 500]
~~~

This is strictly conceptual. Actual compression unit organization and algorithms are handled internally by Oracle; never infer physical byte layouts from illustrative diagrams.

### 5.1 Query Compression vs. Archive Compression

Typical HCC syntax choices:

~~~sql
-- Options geared toward analytical queries.
COLUMN STORE COMPRESS FOR QUERY LOW
COLUMN STORE COMPRESS FOR QUERY HIGH

-- Options geared toward archival / infrequent access.
COLUMN STORE COMPRESS FOR ARCHIVE LOW
COLUMN STORE COMPRESS FOR ARCHIVE HIGH
~~~

Typically, **query** modes balance compression efficiency with analytical read speed; **archive** modes prioritize maximum space savings, often at the cost of higher CPU and compression/decompression time. `LOW` and `HIGH` represent trade-off tiers within each group.

Do not treat these tiers as guaranteed absolute compression ratios. Actual savings depend on data, load method, storage, and version.

### 5.2 HCC and Row-by-Row Updates

HCC fits settled data regions loaded in batches and mostly scanned/read. When frequent single-row updates occur:

- Oracle may have to perform much heavier compressed-data handling than in row stores.
- New or modified rows may no longer stay stored in the original compression unit layout.
- Compression ratio and DML performance can degrade when data is repeatedly modified.
- Returning data to the desired compressed state may require bulk/reorganization operations via supported procedures.

Therefore, do not put a constantly updated orders table into HCC merely because a test snapshot achieved a high compression ratio.

### 5.3 Infrastructure and Licensing Requirements for HCC

HCC is a clear example of a feature where **you cannot look at SQL syntax alone to infer permission to use it**. Support depends on the database, storage type or Oracle service certified for HCC, edition, release, and entitlement rules. Specific Oracle engineered systems/services support HCC; do not assume any arbitrary disk or cloud service supports the same mechanism.

Before designing around HCC, ask:

1. Which exact **Oracle Database version/release update, edition, and deployment model** is in use?
2. Which **storage type** will hold the segment, and does Oracle support HCC on that exact configuration?
3. Which HCC modes do your contract and corresponding **Licensing Information User Manual** permit?
4. Are there restrictions on bulk loads, DML, data movement, or copying across storage types?
5. If moving tables/partitions to another system, is that compression mode still supported at the target?

Verify answers in Oracle documentation and your deployment's exact licensing terms; a general guide cannot substitute for that verification.

## 6. Table Compression Differs from Index, LOB, or In-Memory Compression

Multiple compression mechanisms can coexist in one database:

| Component | What to Distinguish |
|---|---|
| **Heap table / table partition** | Basic, Advanced Row Compression, or HCC in eligible environments |
| **B-tree index** | Has its own key/index compression mechanisms; does not automatically shrink at the same rate as the table |
| **SecureFiles LOB** | Dedicated compression for LOBs such as documents/images, with separate licensing conditions |
| **In-Memory Column Store** | Columnar in-memory representation to accelerate queries; in-memory compression differs from on-disk segment storage |
| **RMAN backup compression** | Compresses backup sets/pieces without altering live table segments used by the database |
| **Network/data transport compression** | Optimizes data sent between components; does not mean tables are stored compressed |

For example, suppose a table has a `BLOB` column storing ZIP/JPEG files that are already compressed: enabling row-store compression on the table **does not guarantee** large LOB capacity will drop, because LOB data can reside in a separate segment under different policies. Nor can you infer from a smaller backup size that table segments on disk are compressed.

When comparing savings, define the measurement scope clearly: **heap table only**, **table + indexes + LOBs**, **entire tablespace**, or **backup/storage bill**. Figures can differ dramatically.

## 7. CPU and I/O Trade-offs: Why Compression Is Sometimes Faster and Sometimes Slower

Compression trades **compute** for **storage footprint and data-movement volume**.

Suppose a report must read 60 GiB of uncompressed table data. After compression, the same logical data takes 24 GiB. If the workload is mainly I/O-bound, reading fewer blocks can deliver clear benefits. However, decompressing and processing compressed block formats spends CPU; if CPU is already saturated, runtime may fail to improve or even worsen.

### 7.1 Formulas for Measuring Compression Ratio

Let:

- `U` = size of table/data segment before compression, measured over the same scope.
- `C` = size after compression, same data and same measurement scope.

Two metrics:

\[
\text{Compression ratio} = \frac{U}{C}
\]

\[
\text{Space saving} = \frac{U-C}{U}\times 100\%
\]

If `U = 60 GiB` and `C = 24 GiB`:

- **Compression ratio:** `60 / 24 = 2.5:1`.
- **Space saving:** `(60 - 24) / 60 = 60%`.

The 60% figure is **space saved within the measured scope**—it does not prove query speed improves by 60%, CPU drops by 60%, or total storage bills drop by 60%.

### 7.2 Where Is CPU Spent?

Compression can raise compute cost during several activities:

- **Bulk load / CTAS / MOVE:** building compressed blocks or compression units.
- **Reading data:** decompressing or evaluating directly against compressed formats per engine mechanics.
- **Conventional DML:** updating rows, inserting rows, managing block space, and potentially recompressing.
- **Segment reorganization:** generating newly compressed data and rebuilding dependent structures.

Decompression efficiency depends on algorithm and hardware. For read-heavy data, extra CPU per block can be outweighed by I/O savings; for write-heavy loads or poorly compressible data, the outcome can be the opposite.

### 7.3 Two Contrasting Scenarios

**Scenario A — Analytical Data Warehouse**

- 200-million-row historical table.
- Many reports scanning older partitions.
- Repeated values across columns, few updates.
- Storage I/O is the bottleneck; CPU has headroom.

Compression is likely to reduce blocks read and storage footprint. If infrastructure and entitlements align, compare Basic, Advanced, and HCC by report latency.

**Scenario B — Hot Transactional Table**

- Heavy `INSERT`/`UPDATE` activity every second on active blocks.
- Strict p95/p99 transaction latency SLAs.
- CPU nearly saturated, table relatively small with high cache hit ratio.
- Columns hold mostly unique values or already-compressed payloads.

I/O and space savings may be outweighed by CPU/DML overhead and transaction latency impact. Choosing not to compress is an equally valid engineering decision.

## 8. Why Saving Space Does Not Equal Saving Total Cost

A smaller compressed table segment saves storage, yet total system cost includes:

| Cost Area | How Compression Can Affect It |
|---|---|
| **Table segment size** | Can usually decrease when data is sufficiently compressible |
| **Physical I/O on reads** | Can drop due to fewer stored blocks |
| **SGA buffer cache** | Some workloads can keep more logical data resident in the same cache size |
| **CPU** | Can increase due to compression/decompression and compressed-block management |
| **INSERT/UPDATE/DELETE latency** | Can rise or shift depending on compression mode and DML pattern |
| **UNDO/REDO** | No one-way rule; compressed writes, updates, moves, DDL, and logging generate varying workloads |
| **TEMP/PGA** | Does not automatically shrink at the table's compression ratio; sorts/hashes still build their own intermediate structures |
| **Index/LOB storage** | May remain unchanged unless configured separately |
| **Backup/replication** | Can bring savings or costs depending on tools, backup formats, log generation, and infrastructure |
| **Migration/rebuild** | Needs I/O, CPU, temporary space, and can impact ROWIDs/indexes and availability |
| **Licensing/service fees** | Certain compression modes require specific options/editions/storage or service tiers |

Therefore, never use a rule like "table shrank by 50%, so the system is 2× faster." Actual performance is the product of database, queries, data, concurrency, infrastructure, and operational policies combined.

### 8.1 Compression and Buffer Cache

In some access paths, Oracle can process data in compressed form inside blocks, allowing more logical data to be represented in fewer blocks. That helps when the working set is large and the buffer cache constantly pulls blocks from storage.

However, if queries already operate almost entirely in cache, reducing physical blocks slightly may yield little visible gain. Observe **logical reads, physical reads, CPU time, elapsed time**, and buffer cache state in the same test scenario.

### 8.2 Compression and Index Access

An OLTP query like:

~~~sql
SELECT status, total_amount
FROM orders
WHERE order_id = :p_order_id;
~~~

usually accesses via the primary-key index and fetches a single row. Even if the table is heavily compressed, logical reads for this query may barely change. Conversely, reports scanning most of the table have far more opportunity to benefit from I/O reduction.

Never treat compression as a replacement for indexes, partitioning, proper filter predicates, or sound SQL design.

## 9. Operations That Compress Existing Data vs. New Data

A long-lived table holds many previously stored blocks. **Changing the table's compression attribute does not immediately rewrite all existing blocks.**

### 9.1 Declaring Mode on the Table

On supported versions, the statement:

~~~sql
ALTER TABLE sales_history
ROW STORE COMPRESS BASIC;
~~~

changes the table's compression property for eligible subsequent operations. Existing rows in older blocks **are not guaranteed to convert to compressed form solely from a metadata change**.

Likewise, switching to Advanced or `NOCOMPRESS` does not automatically rewrite all existing blocks. One table can contain physical data written at different times under different compression states; dictionary views show the configured setting, not proof that every block uses that format.

### 9.2 Rewriting the Table Segment with MOVE

A common operation to apply compression to existing data is rebuilding the table segment:

~~~sql
-- Operational DDL illustration; do not run on production tables without a plan.
ALTER TABLE sales_history
MOVE ROW STORE COMPRESS BASIC;
~~~

`MOVE` can require extra free space during execution, generate substantial I/O/CPU, change row ROWIDs, and affect dependent index status depending on version/method. Online options and index maintenance clauses carry their own constraints. Therefore:

- Test on a copy or staging environment first.
- Verify sufficient space, maintenance window, and application tolerance for impact.
- Identify indexes/constraints/dependencies needing maintenance and confirm index status afterward.
- Prepare an appropriate backup/restore plan; do not confuse SQL `ROLLBACK` with undoing committed DDL.
- Ensure bulk/migration operations are logged, monitored, and compliant with feature entitlements.

### 9.3 CTAS for Testing Without Modifying the Source Table

`CREATE TABLE ... AS SELECT` lets you build compressed copies of data in a lab schema, though it **does not automatically preserve all properties of the source table**. Account for differences in indexes, constraints, grants, triggers, partitioning, LOB settings, and statistics when comparing.

For a fair comparison, build independent copies from the **same data snapshot**, run identical queries, and use identical object scopes when measuring size. Testing Advanced or HCC must be cleared against entitlements first.

## 10. Partition Compression: Hot for Writes, Cold for Reads

Partitioning and table compression solve two distinct problems:

- **Partitioning** organizes data into smaller logical/physical segments by criteria such as date or region, aiding manageability and potentially reducing data scanned via optimizer partition pruning.
- **Compression** reduces storage footprint/cost of data inside the corresponding segment.

Combining both works well when partitions have different lifecycles.

Example of a monthly orders system:

~~~text
ORDERS
 |
 +-- P_2026_11    [HOT]   new transactions, frequent updates
 +-- P_2026_10    [WARM]  mostly reads, some late updates
 +-- P_2026_09    [COLD]  almost exclusively reporting
 +-- P_2026_08    [COLD]  historical archive
 +-- ...
~~~

A policy might be:

1. Current-month data uses `NOCOMPRESS` or a DML-friendly row compression mode if licensed.
2. Once frequent modifications end, the partition transitions through a controlled bulk/reorganization process.
3. Historical partitions use Basic or HCC matching entitlements, storage, and query requirements.
4. Reports filter by date to leverage partition pruning; compression reduces I/O on the data actually read.

Illustrative syntax in a supported environment:

~~~sql
-- Verify exact partition and index impact before executing.
ALTER TABLE orders
MOVE PARTITION p_2026_08
ROW STORE COMPRESS BASIC;
~~~

`MOVE PARTITION` is DDL with physical impact, potentially affecting indexes (especially related index components) and availability. Depending on version, online/index-maintenance options differ. This example illustrates a data management strategy, not a command to execute in production without planning.

**Partitioning also has separate licensing/feature requirements depending on your Oracle environment.** Never assume that because Basic compression is allowed, all related partitioning features are automatically licensed as well.

## 11. Measuring Compression in an Isolated Lab

The following commands are meant for a **dedicated practice schema** with table creation privilege and adequate quota. The goal is observing compression ratios and query results, not tuning a user-facing database. Examples focus on **BASIC** to demonstrate the workflow; run them only if your environment licenses and supports that mode. For Advanced/HCC, verify entitlement before creating test copies.

### 11.1 Create Synthetic Data with Repetition

~~~sql
CREATE TABLE lab_sales_source AS
SELECT LEVEL AS sale_id,
       MOD(LEVEL - 1, 1000) + 1 AS customer_id,
       DATE '2026-01-01' + MOD(LEVEL, 300) AS sale_date,
       CASE MOD(LEVEL, 4)
           WHEN 0 THEN 'HCM'
           WHEN 1 THEN 'HN'
           WHEN 2 THEN 'DN'
           ELSE 'CT'
       END AS region_code,
       CASE MOD(LEVEL, 5)
           WHEN 0 THEN 'REFUNDED'
           WHEN 1 THEN 'PAID'
           ELSE 'COMPLETED'
       END AS sale_status,
       RPAD('STANDARD-SALES-RECORD', 160, 'X') AS repeated_text,
       ROUND(MOD(LEVEL * 37, 10000) / 100, 2) AS amount
FROM dual
CONNECT BY LEVEL <= 100000;
~~~

Here `REGION_CODE`, `SALE_STATUS`, and `REPEATED_TEXT` contain many repeated values; the lab is likely to demonstrate compression more clearly than random data. However, it **does not represent every workload**: real data has key skew, update churn, varying row sizes, and diverse column types.

### 11.2 Build Two Copies from the Same Source

~~~sql
-- Uncompressed heap copy.
CREATE TABLE lab_sales_plain
NOCOMPRESS
AS
SELECT * FROM lab_sales_source;

-- Basic Table Compression copy.
CREATE TABLE lab_sales_basic
ROW STORE COMPRESS BASIC
AS
SELECT * FROM lab_sales_source;
~~~

`CTAS` is a bulk-load segment creation method well-suited to observing Basic compression. Ensure both statements succeed with identical row counts and identical logical data before measuring. `LAB_SALES_SOURCE` only serves to generate the test dataset; exclude it when comparing sizes between `PLAIN` and `BASIC`.

### 11.3 Inspect Compression Metadata

Without needing database-wide privileges, the table owner can query:

~~~sql
SELECT table_name, compression, compress_for
FROM user_tables
WHERE table_name IN ('LAB_SALES_PLAIN', 'LAB_SALES_BASIC')
ORDER BY table_name;
~~~

Output reflects **object metadata**. It is not a measurement of the percentage of data actually compressed. If compression is enabled on a table that already contains old data, `COMPRESSION`/`COMPRESS_FOR` shows the configured mode without proving all older rows are compressed.

### 11.4 Measure Allocated Segment Size

~~~sql
SELECT segment_name,
       segment_type,
       bytes,
       ROUND(bytes / 1024 / 1024, 2) AS allocated_mb
FROM user_segments
WHERE segment_name IN ('LAB_SALES_PLAIN', 'LAB_SALES_BASIC')
ORDER BY segment_name;
~~~

`USER_SEGMENTS.BYTES` is **space allocated to the segment**, not total bytes of row payloads. For small tables, extent allocation, high-water mark, free space, and metadata can distort percentage comparisons. Two freshly CTAS'd tables with identical data give a cleaner direct comparison, though you should test sufficiently large datasets and re-measure under representative workloads.

For partitioned tables, never look only at table name assuming a single segment: each table partition/subpartition can have its own segment. Inspect partition metadata and sum across the exact scope.

### 11.5 Verify Identical Row Counts and Analytical Results

~~~sql
SELECT 'PLAIN' AS variant,
       COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM lab_sales_plain
UNION ALL
SELECT 'BASIC' AS variant,
       COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM lab_sales_basic;
~~~

Then run the same query on each table:

~~~sql
SELECT region_code,
       sale_status,
       COUNT(*) AS n,
       SUM(amount) AS total_amount
FROM lab_sales_basic
WHERE sale_date >= DATE '2026-01-01'
  AND sale_date < DATE '2026-07-01'
GROUP BY region_code, sale_status
ORDER BY region_code, sale_status;
~~~

Swap the table name from `LAB_SALES_BASIC` to `LAB_SALES_PLAIN` and measure under comparable conditions. Compressed data must never alter logically correct SQL output.

### 11.6 Gather Statistics and Inspect Execution Plans

With an account holding appropriate privileges in the lab schema:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(USER, 'LAB_SALES_PLAIN');
    DBMS_STATS.GATHER_TABLE_STATS(USER, 'LAB_SALES_BASIC');
END;
/
~~~

Then check the plan:

~~~sql
EXPLAIN PLAN FOR
SELECT region_code, SUM(amount) AS total_amount
FROM lab_sales_basic
GROUP BY region_code;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` is an **estimate**; it does not confirm actual blocks or CPU consumed. Proper performance evaluation requires executing the query, collecting elapsed time, logical/physical reads, and runtime plans where permitted. Never draw conclusions from a single run: the first run may hit cold cache, subsequent runs warm cache, and other SQL may run concurrently.

### 11.7 Clean Up Lab Data

Drop only the tables you created in the **lab schema** once confirmed nobody else is using them. `DROP TABLE` is DDL with an implicit commit and can remove data per Oracle's object-management rules; never run drop table statements on real schemas to repeat experiments.

## 12. Fair Performance Evaluation: What Must Be Measured?

A test measuring storage size alone is insufficient to decide on compressing a production table.

| Metric | Why Measure It? | Observation Hint |
|---|---|---|
| **Table segment size** | Assess table storage savings | `USER_SEGMENTS`/`DBA_SEGMENTS` for exact table/partitions |
| **Total object storage** | Indexes, LOBs, and other partitions may remain large | Aggregate exact table + index + LOB scope if that is the goal |
| **SELECT elapsed time** | Assess actual reporting speed | Multiple runs under matching cache/concurrency conditions |
| **CPU time** | Compression/decompression can raise CPU | Runtime SQL statistics / authorized monitoring tools |
| **Logical and physical reads** | Separate buffer cache vs. I/O impacts | Plan/runtime statistics; do not equate the two metrics |
| **DML throughput, p95/p99 latency** | Assess impact on transactional workloads | Load test INSERT/UPDATE/DELETE at representative concurrency |
| **Redo/undo generated** | Check cost of data changes and migration | Observe operations across equivalent workload windows |
| **Bulk load or MOVE duration** | Compressing legacy data can be resource-heavy | Measure duration, CPU, I/O, and extra free space required |
| **Backup/restore duration** | Impact on data protection workflows | Test separately with actual backup tool and backup compression type |
| **Licensing and platform fees** | Confirm cost and usage rights | Contracts, licensing guide per release/deployment |

### 12.1 Recommended Benchmark Sequence

1. **Lock down the workload:** e.g., 70% primary-key lookups, 25% daily reports, 5% status updates. Ratios are illustrative, not prescriptive.
2. **Freeze the dataset:** copies must use the exact same snapshot and data distribution; otherwise differences may come from data rather than compression.
3. **Verify structures and stats:** corresponding indexes/partitions/LOBs, session settings, statistics, plans, and bind values must all be recorded.
4. **Measure both cold and warm cache:** across the same scenario, without cherry-picking one favorable run to generalize.
5. **Measure under concurrent load:** a report that runs faster in isolation may lose its advantage when CPU is contended by DML.
6. **Measure data load/update phases:** not just `SELECT`; assess total operational cost of the compression mode.
7. **Conclude against SLAs:** capacity, CPU, I/O, p95/p99, batch windows, availability, and entitlement.

Never use a single "highest compression ratio" number as the sole criterion. Choosing a compression mode is a **multi-constraint optimization problem**.

## 13. Verifying Feature Prerequisites and Licensing

This is an engineering design component, not paperwork tacked onto the end of a project. In Oracle, two environments may both accept a DDL statement while **commercial usage rights are not identical**.

### 13.1 Variables Determining Entitlement

Before enabling any compression mode, verify at minimum:

| Information to Confirm | Why It Matters |
|---|---|
| **Oracle Database release and edition** | Feature sets and prerequisites vary by release/edition |
| **On-premises vs. cloud/managed database environment** | Some entitlements may be bundled in a cloud tier yet require a separate option elsewhere |
| **Actual storage infrastructure** | Especially for HCC, not every storage platform supports it |
| **Exact feature in use** | Basic Table Compression, Advanced Row Compression, HCC Query/Archive, SecureFiles LOB, and index compression are distinct scopes |
| **Contract/SKU and purchased options or subscribed services** | SQL succeeding does not mean usage rights were granted |
| **How copies/backups/data move across environments** | Target may differ in entitlements or storage support |
| **Oracle Licensing Information User Manual for that release** | Authoritative reference for technical limits and licensing scope |

For **Basic Table Compression**, do not infer from the word "Basic" that the feature is free in every Oracle edition. For **Advanced Row Compression**, check requirements for the **Advanced Compression option** or equivalent service-tier entitlement. For **HCC**, additionally verify storage/engine prerequisites and specific licensing rules. Even if a system licensed one option, a similarly named feature is not necessarily covered under the same entitlement.

### 13.2 "The Statement Executed" Is Not Proof of Licensing

A database may permit executing feature syntax in some cases because technical validation and commercial entitlement are two separate checks. Therefore:

- Do not test `ROW STORE COMPRESS ADVANCED` in production and ask about licensing afterward.
- Do not infer entitlement solely from `COMPRESSION`/`COMPRESS_FOR` values in the dictionary.
- Do not infer entitlement merely because a feature appears in a GUI.
- Do not treat successful statement execution as authorization from Oracle.
- Do not treat feature-usage tracking tables as automatic proof that the enterprise **holds** rights to use that feature.

Feature-usage tracking tools help with inventory, yet **licensing/entitlement terms must be verified independently** against official sources and your organization's contracts.

### 13.3 If Version Documentation and Project Architecture Conflict

Prioritize checking Oracle documentation specific to your system's release/edition/deployment, especially when using cloud services or engineered platforms. Entitlements evolve over time and across delivery models; never apply an outdated licensing claim across all releases.

A short decision flow before enabling compression:

~~~text
Need to compress a table
    |
    v
Identify data type / workload / SLA
    |
    v
Select candidate: BASIC / ADVANCED / HCC
    |
    v
Check version + edition + storage + entitlement
    |
    +-- Not supported / not entitled --> Stop using that mode, pick another approach
    |
    +-- Supported and entitled
            |
            v
    Benchmark real data and workload
            |
            v
    Decide rollout + rollback + monitoring
~~~

## 14. Operational Risks When Converting Live Tables to Compression

### 14.1 DDL, Implicit Commit, and Reversibility

`ALTER TABLE ... MOVE` and CTAS are DDL. Do not expect normal `ROLLBACK` to undo a completed table move. Converting live tables requires backup/restore readiness or a controlled new-table swap strategy, depending on availability and rollback requirements.

### 14.2 ROWIDs, Indexes, and Dependent Objects

Rewriting a table segment can change `ROWID`s and affect indexes. If an application stores ROWIDs long-term as business identifiers, that is already a design flaw needing revision; ROWIDs can change whenever data moves physically. Indexes must be maintained and their status verified per command and Oracle release; never assume they stay valid automatically after every type of MOVE.

### 14.3 Temporary Space and Resources During Conversion

Compressing to **save space in the end** can still require **extra space during conversion**: new segments, index rebuilds, undo/redo, backups, or auxiliary workspace. If the table is huge and storage is nearly full, a plan to "compress to free disk space" can fail for lack of working space upfront.

### 14.4 Will New Data Stay Compressed Properly?

After a bulk migration, regular workloads may insert and modify rows via different paths. With Basic or HCC, newly inserted or updated data can dilute overall compression efficiency. Therefore, monitor **segment size trends** and schedule lifecycle maintenance rather than measuring only right after initial compression.

### 14.5 Impact on Transactions and Availability

Running compression/reorganization at the wrong time can cause heavy I/O/CPU, contend with OLTP, and introduce DDL locks/disruptions subject to online limitations. Define maintenance windows, allowable load, privileges, and rollback/recovery tooling. Compressing a 2 TB table down to 900 GB can still cause an outage if the conversion strategy is flawed.

## 15. Strategy Matrix by Table Type

| Data Context | Candidate Worth Evaluating | Reason | What to Inspect Closely |
|---|---|---|---|
| Small transactional table, very heavy writes, high CPU | `NOCOMPRESS` or benchmark Advanced if entitled | DML latency may outweigh storage footprint | CPU, p95/p99, row migration, actual ratio |
| Very large transactional table, many repeated values, mixed read/write | Advanced Row Compression | Better mechanisms for regular DML than Basic | Advanced Compression entitlement, write throughput |
| Summary table rebuilt in batches | Basic Table Compression | Batch load/CTAS matches Basic mechanics | Load duration, scan queries, edition/license |
| Prior-year partitions, rarely updated | Basic or HCC (if supported) | Reduces stored blocks, leverages immutability | Late DML, HCC storage, query/archival SLAs |
| Historical archive for large scans, minimal DML | HCC Query or Archive (if supported/licensed) | Maximizes storage reduction for analytics/archival | Decompression CPU, storage, and entitlement |
| Table with very large BLOB/CLOB columns | Review SecureFiles LOB policy separately | Row-store compression may not address LOB portion | LOB storage, pre-compressed data types, license |
| Point lookups by PK, table fits in cache | Compression may be unnecessary | Physical I/O savings may be minimal | CPU, index lookups, actual workload |

These suggestions are **starting points for benchmarking**, not universal rules. The same logical table may warrant different modes in environments with different CPU, I/O, data skew, storage costs, and licensing.

## 16. Common Misconceptions

**"Table compression makes every SELECT run faster."** False. I/O-bound queries may benefit; CPU-bound queries or queries reading very few rows may see no gain or incur extra CPU cost.

**"Advanced always achieves a higher compression ratio than Basic."** Mode names reflect workload handling and compression mechanics, not a guaranteed ratio across every dataset. Measure on real data.

**"HCC is the same as In-Memory Column Store."** False. HCC is an on-disk compressed storage format using compression units on supported storage; In-Memory Column Store is an in-memory structure for query acceleration with its own feature/licensing model.

**"Running ALTER TABLE ... COMPRESS immediately compresses all old blocks."** False. Updating metadata and rewriting existing blocks are two different operations. Existing data requires an appropriate operation such as CTAS/MOVE or a supported procedure.

**"Measuring a 60% drop in USER_SEGMENTS means the whole database shrank by 60%."** False. A table is only part of total storage; indexes, LOBs, undo, redo, TEMP, backups, and other overhead have their own footprints.

**"Just add more CPU to offset compression overhead."** Not guaranteed. DML, locking, memory, I/O, redo, concurrency, and Oracle execution paths still govern outcomes.

**"Basic is free, Advanced is paid, and HCC is always available on every Oracle system."** This is an oversimplified licensing claim and can be wrong depending on release/edition/deployment. Check the licensing guide, storage rules, and actual entitlements.

**"A feature existing in the product means it is licensed for use."** False. Technical availability and commercial usage rights are two separate verifications.

## 17. Integrated Scenario

An enterprise runs Oracle Database for an e-commerce platform:

- `ORDERS_CURRENT` holds the last 3 months of orders with continuous status updates.
- `ORDERS_HISTORY` holds 5 years of older orders, mainly used in financial reporting and analytics.
- `ORDER_ATTACHMENTS` holds images, PDF invoices, and uploaded documents as LOBs.
- Storage is growing rapidly; peak-hour CPU utilization is already high.

The project team wants to compress all three tables at the maximum level to save storage costs.

### Sound Reasoning Approach

**For ORDERS_CURRENT:** test read/write impact and API latency; Advanced Row Compression is a candidate only if entitlements match. If CPU is already saturated and compression saves little, keeping `NOCOMPRESS` may be better.

**For ORDERS_HISTORY:** data changes rarely and is scanned periodically. Compare Basic and HCC if the environment allows. If partitioned, transition only closed-period partitions to an appropriate compression mode; measure both report read times and move/load times.

**For ORDER_ATTACHMENTS:** do not assume table compression will shrink already-compressed images/PDFs. Check LOB type, file formats, SecureFiles compression, and separate entitlements. Compressing already-compressed files may be ineffective.

**System-wide:** measure total allocated storage, CPU, I/O, transaction p99, and report runtimes. Never switch everything at once during peak hours; prepare a controlled rollout and rollback plan.

### Thought Exercises

1. Why shouldn't you measure `ORDERS_CURRENT` only during off-peak hours and conclude compression has zero OLTP impact?
2. If Basic gives `ORDERS_HISTORY` a 2.2:1 ratio while HCC Archive reaches 4.5:1 yet reports run significantly slower, which metrics should guide the decision?
3. If a 500 GB table shrinks to 250 GB after compression, is `MOVE` guaranteed to succeed when the tablespace has only 100 GB free?
4. When migrating a database from HCC-supported infrastructure to another environment, what must be verified before moving data?
5. Why must table segment measurements be separated from index segments and LOB segments?

**Answer hints:** evaluate concurrent workloads; balance ratio against SLAs and CPU; account for intermediate space during segment rewrites; verify target storage/edition/entitlements; and keep measurement scopes consistent to avoid misreporting savings.

## 18. Key Takeaways When Designing Table Compression

Table compression in Oracle is **a storage architecture and workload decision**, not merely a DDL clause. Basic fits batch-loaded data better; Advanced Row Compression targets compression even alongside conventional DML; HCC serves read-intensive analytical/archival data in supported environments. Choosing a mode must rely on real data, CPU/I/O headroom, write activity, partition management needs, and reporting SLAs.

Before deploying, define **the target data scope, how ratios are measured, SQL/DML performance, conversion resources, and the exact feature/licensing requirements of your Oracle environment**. A sound solution saves storage while preserving system SLAs and staying strictly within verified product entitlements.
