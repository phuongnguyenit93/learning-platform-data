# Database In-Memory, Column Store, and Differences from Buffer Cache

## 1. What Is Database In-Memory?

Oracle Database In-Memory is the capability to store a columnar representation of data in SGA memory to accelerate analytical queries. This feature is designed for workloads that scan many rows, read a subset of columns, filter, join, and aggregate over large datasets.

Oracle still stores durable data on datafiles in the traditional row-store format. Database In-Memory adds an in-memory representation for tables, partitions, or columns marked `INMEMORY`. The same data can be accessed via:

- **Row format:** columns of a row are stored together in database blocks; suited for OLTP, key lookups, and DML.
- **Columnar format:** values of the same column are organized together in the In-Memory Column Store (IM column store); suited for scans and analytics across many rows.

This is a dual-format architecture. Oracle can use the row format in the buffer cache and the columnar format in the IM column store depending on the SQL statement, execution plan, and population state. Both formats represent the same object's data—not two independent business copies that the application must manually synchronize.

## 2. How Does the Column Store Work?

### 2.1. Row Store and Column Store

Suppose table `SALES` has columns `SALE_ID`, `CUSTOMER_ID`, `SALE_DATE`, `REGION_ID`, `AMOUNT`, and `STATUS`.

In a row store, data is organized by row:

```text
Row 1: SALE_ID | CUSTOMER_ID | SALE_DATE | REGION_ID | AMOUNT | STATUS
Row 2: SALE_ID | CUSTOMER_ID | SALE_DATE | REGION_ID | AMOUNT | STATUS
Row 3: SALE_ID | CUSTOMER_ID | SALE_DATE | REGION_ID | AMOUNT | STATUS
```

In a column store, values of each column are grouped together:

```text
SALE_ID:      101 | 102 | 103 | 104 | ...
CUSTOMER_ID:  501 | 720 | 501 | 881 | ...
SALE_DATE:    ... | ... | ... | ... | ...
REGION_ID:    10  | 20  | 10  | 30  | ...
AMOUNT:       ... | ... | ... | ... | ...
STATUS:       ... | ... | ... | ... | ...
```

If a report only needs `REGION_ID` and `AMOUNT`, the column store can read just the two required columns without decoding all other columns in each row. For data with many repeated values or narrow value domains, columnar representation also offers strong compression opportunities.

### 2.2. In-Memory Compression Units

Oracle organizes columnar data in compression units called In-Memory Compression Units (IMCUs). An IMCU holds compressed columns for a group of rows. Metadata supports mapping and accessing values inside the IMCU.

Columnar format supports column-level scans, data filtering, vector processing, and aggregations. Instead of processing row by row in the traditional way, Oracle can process a batch of values at once using CPU-friendly vectorization techniques.

### 2.3. The Column Store Is Not an Index

The IM column store is neither a B-tree index nor a bitmap index. It is an in-memory representation of data organized by column. The optimizer can choose an In-Memory scan over a table scan or index access when costs and query conditions align.

Therefore:

- You do not need to create an index per column just to use the column store.
- Indexes remain valuable for OLTP queries looking up a few rows by key.
- The column store is especially beneficial for scans and aggregations across large row counts.
- Marking a table `INMEMORY` does not guarantee every query on that table will use the IM column store.

## 3. Differences Between IM Column Store and Buffer Cache

### 3.1. Buffer Cache

The database buffer cache is the SGA region holding database blocks read from datafiles. It is a core component of Oracle Database, serving both reads and writes in row format.

When a session reads a block, Oracle may find it in the buffer cache. If not present, the database reads the block from storage into the cache. DML modifies blocks in the buffer cache; modified blocks become dirty buffers and DBWR writes them back to datafiles via checkpoint/write-back mechanisms.

The buffer cache optimizes block reuse and row-store data access. For instance, a query fetching a single order by primary key usually needs one or a few blocks containing that row; indexes and the buffer cache are the right mechanism.

### 3.2. In-Memory Column Store

The IM column store is a dedicated SGA region for columnar data of objects enabled with `INMEMORY`. Data is populated from the row store into compressed columnar format.

When the optimizer chooses In-Memory access, Oracle reads the needed columns from the IM column store. Techniques such as In-Memory pruning, vectorized execution, and In-Memory aggregation can reduce processed data volume and accelerate analytical queries.

The IM column store does not replace the buffer cache and is not the sole durable data store. Datafiles still hold row format; the buffer cache continues serving normal database operations.

### 3.3. Direct Comparison

| Criterion | Buffer Cache | In-Memory Column Store |
|---|---|---|
| Primary format | Row-oriented database blocks | Columnar, compressed representation |
| Data scope | Blocks read/written on demand | Objects/partitions/columns declared `INMEMORY` and populated |
| Goal | Accelerate general block access, OLTP, and DML | Accelerate scans, filters, joins, and analytic aggregations |
| Durable data | Corresponding blocks stored in datafiles | Representation in SGA; source data remains in row store/datafiles |
| Allocation | Buffer cache in SGA | Dedicated IM column store pool in SGA |
| DML | Executed on row format/buffer cache | Maintains consistency of columnar representation via In-Memory mechanisms |
| Usage selection | Oracle uses buffer cache in normal read/write operations | Optimizer selects when query and object qualify and data is ready |
| Replaces indexes? | No | No; it is an in-memory storage format, not an index |

### 3.4. One Workload Can Use Both Formats

An application may have OLTP queries looking up by primary key and reporting queries scanning millions of rows on the same table. OLTP queries can use indexes and row blocks in the buffer cache; reporting queries can use columnar data in the IM column store.

The optimizer chooses access paths based on SQL, statistics, cardinality, object population, and cost. DBAs do not need to toggle a table back and forth between row store and column store when workloads shift; both formats coexist.

## 4. SGA and the INMEMORY_SIZE Parameter

### 4.1. The IM Column Store Is a Pool in the SGA

Oracle reserves a memory area in the SGA for the In-Memory Column Store. Its size is controlled by the `INMEMORY_SIZE` parameter.

Check configuration:

```sql
SHOW PARAMETER inmemory_size;

SELECT name,
       value,
       isdefault,
       issys_modifiable
FROM v$parameter
WHERE name = 'inmemory_size';
```

If `INMEMORY_SIZE=0`, the IM column store is allocated no space and objects may carry the `INMEMORY` attribute without being able to populate into the IM area until configured properly.

### 4.2. Allocating IM Column Store Space

Example configuring 4 GB in the SPFILE:

```sql
ALTER SYSTEM SET inmemory_size = 4G SCOPE=SPFILE;
```

Then restart the instance if the parameter in your running release is static:

```sql
SHUTDOWN IMMEDIATE;
STARTUP;
```

Follow your real environment's maintenance procedures; never restart production just to test a statement. `INMEMORY_SIZE` must fit within SGA limits and overall memory configuration. Ensure `SGA_MAX_SIZE`/`SGA_TARGET` and headroom for the buffer cache, shared pool, redo buffer, and other SGA components.

Do not size the IM area too large solely from on-disk table size. Columnar compression makes in-memory footprint differ from row-store segment size; measure `INMEMORY_SIZE`, actual `INMEMORY_SIZE` used, and `V$IM_SEGMENTS` after population.

### 4.3. Inspecting In-Memory Area Usage

```sql
SELECT *
FROM v$inmemory_area;
```

This view shows In-Memory pool areas, allocated size, and usage per version info. Exact columns may vary by release; check `DESC V$INMEMORY_AREA` or the corresponding Oracle Database Reference.

## 5. Enabling Database In-Memory for Tables, Partitions, and Columns

### 5.1. Enabling for an Entire Table

Example enabling In-Memory on a fact table:

```sql
ALTER TABLE sales.fact_sales
  INMEMORY
  MEMCOMPRESS FOR QUERY LOW
  PRIORITY HIGH;
```

Meaning:

- `INMEMORY`: marks the object eligible to populate into the IM column store.
- `MEMCOMPRESS FOR QUERY LOW`: selects a compression level geared toward query performance with lighter compression than capacity-focused modes.
- `PRIORITY HIGH`: prioritizes populating this object ahead of lower-priority objects.

This is an object attribute. Command success does not mean all data is populated immediately; check population status.

### 5.2. Disabling In-Memory for a Table

```sql
ALTER TABLE sales.fact_sales NO INMEMORY;
```

This removes the In-Memory attribute from the object. It does not drop the table or delete datafile data. Subsequent queries use appropriate row-store/index/buffer-cache access paths.

### 5.3. Placing Only Selected Columns into the IM Column Store

For wide tables, queries may use only a subset of columns. Oracle supports column-level In-Memory declarations in supported releases:

```sql
ALTER TABLE sales.fact_sales
  INMEMORY (
    sale_date,
    product_id,
    customer_id,
    region_id,
    amount
  )
  MEMCOMPRESS FOR QUERY LOW;
```

Column selection should reflect query workloads. Columns unnecessary for reporting do not need to occupy IM column store space. Verify syntax and column-level In-Memory support in your deployed Oracle release.

### 5.4. Selecting Partitions Instead of the Whole Table

For large partitioned tables, you can enable In-Memory on frequently queried partitions:

```sql
ALTER TABLE sales.fact_sales
  MODIFY PARTITION p2026q1
  INMEMORY MEMCOMPRESS FOR QUERY LOW PRIORITY HIGH;
```

Rarely accessed historical partitions can remain row-store only while recent partitions populate into the IM column store. This manages memory footprint around hot data regions.

### 5.5. Checking Object Attributes

```sql
SELECT owner,
       table_name,
       inmemory,
       inmemory_priority,
       inmemory_compression,
       inmemory_distribute,
       inmemory_duplicate
FROM dba_tables
WHERE owner = 'SALES'
  AND table_name = 'FACT_SALES';
```

For partitions:

```sql
SELECT table_owner,
       table_name,
       partition_name,
       inmemory,
       inmemory_priority,
       inmemory_compression
FROM dba_tab_partitions
WHERE table_owner = 'SALES'
  AND table_name = 'FACT_SALES'
ORDER BY partition_position;
```

Metadata columns and visibility depend on release and data dictionary privileges. Use `USER_TABLES`, `ALL_TABLES`, or corresponding partition views if DBA privileges are unavailable.

## 6. Compression and Population Priority

### 6.1. MEMCOMPRESS FOR QUERY

`MEMCOMPRESS FOR QUERY LOW` and `MEMCOMPRESS FOR QUERY HIGH` target query speed. Higher compression typically reduces memory footprint better, yet can increase decompression/processing CPU depending on workload.

### 6.2. MEMCOMPRESS FOR CAPACITY

`MEMCOMPRESS FOR CAPACITY LOW` and `MEMCOMPRESS FOR CAPACITY HIGH` prioritize saving IM area space. They fit when you need more data inside finite memory, yet require benchmarking because higher compression can impact CPU and query duration.

Example:

```sql
ALTER TABLE sales.fact_sales
  INMEMORY MEMCOMPRESS FOR CAPACITY HIGH
  PRIORITY MEDIUM;
```

There is no single optimal compression level for every table. Data with repeated values, different data types, and varying query patterns yield different compression ratios and performance.

### 6.3. PRIORITY

`PRIORITY` controls object population order. Common levels are `NONE`, `LOW`, `MEDIUM`, `HIGH`, and `CRITICAL`.

- `NONE`: object is typically populated when accessed per Oracle's population policy.
- Higher priority levels: objects are prioritized earlier when the database opens or the IM area becomes ready, in priority order.

Priority does not guarantee an object stays in memory if the IM area is insufficient or other operational conditions intervene. Verify actual population status and space.

### 6.4. Population Is Not Necessarily Instant After ALTER

When `INMEMORY` is enabled, Oracle must read the row store and build the columnar representation in the IM area. This can happen in the background or upon object access depending on priority/configuration. While population is incomplete, queries can still use other access paths.

For reports needing consistent performance, confirm objects/partitions are populated before workloads run. Do not check only `DBA_TABLES.INMEMORY='ENABLED'`; having the attribute enabled and having data populated in the IM area are two separate states.

## 7. Consistency When DML Modifies Data

### 7.1. Row Format Remains the Foundation for DML

Oracle continues executing DML on the row format and managing changes through standard transaction/undo/redo mechanisms. The IM column store is maintained so analytical queries can read the columnar representation with transactional consistency.

When data changes, Oracle tracks changes affecting In-Memory representations using metadata/journals and maintenance mechanisms. Queries must see consistent data per transaction semantics; applications never need to write simultaneously to both the buffer cache and IM column store.

### 7.2. DML Does Not Require Applications to Sync Two Formats

Applications simply run `INSERT`, `UPDATE`, and `DELETE` as usual. Oracle manages row store, undo/redo, and consistency of the columnar representation. Never write two SQL statements to update a "row copy" and a "column copy"; the IM column store is not an application-owned auxiliary table.

### 7.3. DML-Heavy Workloads May Be Unsuitable

Database In-Memory primarily optimizes analytical reads. On tables with very high DML rates, the overhead of maintaining columnar representations, memory, and population may not yield commensurate benefits. Measure read/write ratios, change rates, compression, and query latency before enabling In-Memory on hot OLTP tables.

## 8. How Does the Optimizer Use the Column Store?

### 8.1. The Cost-Based Optimizer Decides

When a query references an object with the `INMEMORY` attribute, the optimizer considers In-Memory scans alongside other access paths. Selection depends on:

- Whether the object/partition is already populated.
- Whether required columns are present in the IM column store.
- Predicates, joins, aggregations, and estimated row counts.
- Statistics and cardinality estimates.
- CPU, memory, and I/O costs.
- Compatibility of the query with In-Memory processing operations.

Thus, `INMEMORY` gives the optimizer an option to choose, not a guarantee forcing every SQL statement to read from the column store.

### 8.2. In-Memory Pruning

The column store can skip reading unneeded data regions based on value metadata inside IMCUs. If a predicate needs only a value range or small subset of data, Oracle can skip IMCUs that cannot contain matching results.

This mirrors partition pruning at another level: partition pruning skips irrelevant partitions; In-Memory pruning skips irrelevant columnar regions. Both mechanisms complement each other.

### 8.3. Vectorized Execution

Columnar representation allows Oracle to process batches of values at once instead of decoding and processing row by row traditionally. Vector processing can leverage CPU SIMD instructions for suitable filters and calculations.

### 8.4. In-Memory Aggregation and Vector Group-By

For aggregation queries across dimension/fact tables, Oracle can use In-Memory Aggregation or vector group-by to reduce intermediate data and accelerate aggregation. Exact capabilities depend on version and SQL shape; not every `GROUP BY` turns into a vector group-by.

## 9. Checking Population and IM Column Store Capacity

### 9.1. Inspecting Populated Segments

```sql
SELECT owner,
       segment_name,
       partition_name,
       segment_type,
       bytes,
       inmemory_size,
       bytes_not_populated,
       inmemory_priority,
       inmemory_compression
FROM v$im_segments
ORDER BY inmemory_size DESC;
```

`V$IM_SEGMENTS` shows segments with In-Memory representations and their sizes. `BYTES` is the row-store segment size; `INMEMORY_SIZE` is the columnar memory used; `BYTES_NOT_POPULATED` reveals unpopulated portions. Exact columns must be verified per release.

### 9.2. Inspecting Columns Configured In-Memory

```sql
SELECT owner,
       table_name,
       column_name,
       inmemory_compression
FROM dba_inmemory_column_level
WHERE owner = 'SALES'
  AND table_name = 'FACT_SALES'
ORDER BY column_name;
```

`DBA_INMEMORY_COLUMN_LEVEL` can inspect column-level configurations in supported releases. If the view does not exist in your version, check the corresponding In-Memory dictionary views for that release.

### 9.3. Inspecting the Memory Area

```sql
SELECT pool,
       alloc_bytes,
       used_bytes
FROM v$inmemory_area;
```

Compare allocated and used space against `INMEMORY_SIZE`. If objects fail to populate, check priority, whether IM area space suffices, whether the object type is supported, and check alert/trace logs for population errors.

## 10. Confirming the Execution Plan Uses In-Memory

### 10.1. Viewing the Execution Plan

Run the query with statistics gathering in a test environment:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       region_id,
       SUM(amount) AS total_amount
FROM sales.fact_sales
WHERE sale_date >= DATE '2026-01-01'
GROUP BY region_id;
```

Then inspect the cursor plan:

```sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    NULL,
    NULL,
    'ALLSTATS LAST +MEMSTATS'
  )
);
```

Depending on version and query, operations may appear as `TABLE ACCESS INMEMORY FULL` or related In-Memory/vector processing operations. Do not rely on a single operation name; read the full plan, predicates, row estimates, and runtime statistics.

### 10.2. Comparing with Buffer-Cache/Row-Store Access

Test the same query before and after enabling In-Memory on a test environment with representative data. Record:

- Elapsed time and CPU time.
- Logical reads and physical reads.
- Input/output row counts at each operation.
- TEMP usage and memory usage.
- Plan operations and In-Memory scan metrics if available.

Do not compare a first run before IM population completes against a post-population run and conclude solely from timing. Separate population cost from steady-state query execution time.

### 10.3. Do Not Force In-Memory Just to See the Operation

If the optimizer picks index access or buffer cache scan because its cost is lower, that may be the right choice. The goal is overall performance and resource efficiency, not forcing `INMEMORY` operations into every plan.

## 11. Designing Suitable Workloads

### 11.1. Workloads That Commonly Benefit

- Data warehouses and star schemas.
- Aggregate reporting on large fact tables.
- Queries reading a few columns from very wide tables.
- Ad-hoc analytics with many filters/group-bys.
- Mixed OLTP and analytical workloads needing access to current data.

### 11.2. Workloads That Benefit Little

- Queries fetching a single row by primary key.
- Queries returning very few rows with an effective index already present.
- Small tables already fitting entirely in the buffer cache without bottlenecks.
- Write-heavy workloads with few analytical queries.
- Unaccessed tables/partitions or insufficient memory to populate.

### 11.3. Choosing Tables/Partitions/Columns by Workload

Do not mark an entire schema `INMEMORY` by default. Use SQL workload analysis, AWR/ASH, or properly licensed monitoring tools to identify time-consuming queries and frequently scanned tables/partitions/columns. Then pick the dataset yielding the highest benefit per byte of IM area.

If reports only use 5 columns of an 80-column table, column-level In-Memory cuts memory footprint. If only the last 3 months of data are analyzed, partition-level In-Memory can be more effective than populating full history.

## 12. Oracle RAC and Distributing In-Memory Data

In RAC, each instance has its own SGA and IM column store. Determine how columnar data is distributed or duplicated across instances to balance memory, scan workloads, and availability.

Oracle provides In-Memory distribution options such as `DISTRIBUTE` and `DUPLICATE` in supported architectures/releases. Specific options can distribute data by partition or rowid range, or maintain duplicates across instances.

Illustrative configuration example:

```sql
ALTER TABLE sales.fact_sales
  INMEMORY
  MEMCOMPRESS FOR QUERY LOW
  DISTRIBUTE BY AUTO;
```

`DISTRIBUTE`/`DUPLICATE` options depend on version, RAC configuration, and object type. Never apply example statements without checking the release syntax/reference. Measure IM population distribution, memory utilization, and query execution per instance.

## 13. CDB/PDB and Operational Considerations

In multitenant environments, In-Memory attributes can be set on objects inside a PDB, while the IM column store is an instance/CDB memory resource per deployment architecture. Thus, capacity planning must sum the needs of all PDBs on an instance, not just one PDB in isolation.

Inspect containers and object attributes from the right PDB or from root using corresponding CDB views. In RAC, each instance has its own IM area; in a CDB, resource allocations and workloads across multiple PDBs can compete for space.

After an instance restart, columnar data must repopulate according to priorities and the release's population mechanism. Account for warm-up time before running critical SLA batches/reports.

## 14. Licensing and Version Availability

Database In-Memory is a conditionally supported and licensed feature depending on Oracle Database release, edition, cloud service, and contracts. Do not infer entitlement merely because `INMEMORY_SIZE` exists or `ALTER TABLE ... INMEMORY` parses.

Before enabling in production, check the Oracle Database Licensing Information for your exact version and offering; confirm the option/feature is licensed, especially for on-premises Enterprise Edition and cloud/BYOL services. Also check feature availability by release/RU because In-Memory capabilities have been added across versions.

Do not use AWR/ASH or management packs to evaluate workloads unless the organization has confirmed corresponding entitlement. Choose telemetry sources that are licensed and appropriate for the environment.

## 15. Database In-Memory Rollout Process

1. Identify analytical workloads bottlenecked on scans, joins, filters, or aggregations; do not start by enabling In-Memory on every table.
2. Confirm Oracle release/RU, edition, offering, and licensing for Database In-Memory.
3. Inspect SGA, `INMEMORY_SIZE`, headroom for buffer cache/shared pool, and overall memory settings.
4. Select tables, partitions, or columns based on workload and estimated post-compression size.
5. Enable `INMEMORY` with appropriate compression/priority in a test environment.
6. Wait for and confirm population via `V$IM_SEGMENTS`, `V$INMEMORY_AREA`, and dictionary attributes.
7. Run representative queries, inspect `DBMS_XPLAN.DISPLAY_CURSOR` and runtime statistics to verify the optimizer actually uses the column store when appropriate.
8. Measure elapsed/CPU, I/O, TEMP, memory, population time, and concurrency; compare against the row-store baseline.
9. Test concurrent DML, restart/population warm-up, OLTP workloads, and multiple PDBs/RAC instances if applicable.
10. Expand the object set gradually; monitor memory pressure and evict low-value objects if IM space runs tight.

## 16. Common Deployment Mistakes

### 16.1. Enabling INMEMORY Without Any Data Populating

Causes can include `INMEMORY_SIZE=0`, insufficient IM area, priority not triggering background population, or the object not yet accessed. Check parameters, memory areas, and `V$IM_SEGMENTS` rather than only inspecting `DBA_TABLES.INMEMORY`.

### 16.2. Thinking IM Column Store Replaces Buffer Cache

The buffer cache is still needed for row store, DML, and many OLTP queries. Shrinking the buffer cache excessively to allocate IM memory can slow down other workloads. SGA sizing must balance both.

### 16.3. Queries Not Using In-Memory Even Though Enabled

The optimizer may pick index/buffer-cache access due to lower cost; the object/partition may not be populated yet; queries may reference columns excluded from the IM column store or have unsuitable query shapes. Check plans, population, and statistics.

### 16.4. Choosing Overly Aggressive Compression

High compression saves memory yet can raise CPU/impact queries. Benchmark on real data rather than relying solely on theoretical compression ratios.

### 16.5. Populating Too Much Data

Selecting full historical tables can exhaust the IM area. Low-priority objects may remain unpopulated or compete for space. Choose partitions/columns delivering higher value per memory byte.

### 16.6. Ignoring Warm-Up Time After Restart

After a restart, columnar data must repopulate per Oracle's mechanism. If reports run immediately, they may miss performance targets. Factor population readiness into startup procedures and SLA checks.

## 17. Key Principles to Remember

- Database In-Memory adds a columnar representation in the SGA; durable data remains in row store on datafiles.
- Buffer cache holds database blocks in row format for normal reads/writes; IM column store serves scan/analytic workloads.
- Both formats coexist in a dual-format architecture; IM column store does not replace the buffer cache or indexes.
- Only objects/partitions/columns configured with `INMEMORY` are population candidates; enabling the attribute does not mean population is complete.
- `INMEMORY_SIZE` controls IM area capacity; balance it with the buffer cache/shared pool and total SGA.
- Compression and priority affect memory footprint, CPU, and population timing; benchmark both.
- Oracle maintains consistency between row-format DML and columnar queries; applications never sync two representations themselves.
- The optimizer decides whether to use In-Memory; confirm via execution plans and runtime metrics.
- Target high-value analytical data, considering column-level/partition-level In-Memory and RAC/CDB workloads.
- Verify feature availability and licensing for your exact release, edition, cloud offering, and contract before deploying.

## Oracle Reference Documentation

- [Oracle Database 19c Database In-Memory Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/inmem/)
- [Oracle Database 19c Database In-Memory Guide — In-Memory Column Store](https://docs.oracle.com/en/database/oracle/oracle-database/19/inmem/introduction-to-database-in-memory.html)
- [Oracle Database 19c Database Reference — INMEMORY_SIZE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/INMEMORY_SIZE.html)
- [Oracle Database 19c Database Reference — V$IM_SEGMENTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-IM_SEGMENTS.html)
- [Oracle Database 19c Database Reference — V$INMEMORY_AREA](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-INMEMORY_AREA.html)
- [Oracle Database 19c SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html)
- [Oracle Database 19c Licensing Information](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/)
