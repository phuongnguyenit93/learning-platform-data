# Partition-Wise Joins and Organizing Queries by Data Regions in Oracle Database

In data warehouses and large transactional systems, two joined tables can hold tens or hundreds of millions of rows. If Oracle has to redistribute all data across parallel execution servers before joining, data transfer, CPU, and memory costs can be enormous. **Partition-wise join** helps reduce this work by splitting the JOIN along corresponding data regions of partitioned tables.

The core idea is: if two tables are compatibly partitioned on the JOIN key, Oracle can join each corresponding pair of partitions independently. A massive query is thus split into smaller joins that can execute in parallel. If only one side is partitioned on the JOIN key, Oracle can also use a **partial partition-wise join** by redistributing the other side to match the existing partitions.

To design effectively, distinguish among:

- **Partitioning:** how a table's data is divided into partitions.
- **Partition pruning:** skipping partitions that do not need to be read thanks to predicates or JOIN conditions.
- **Partition-wise join:** performing the JOIN per matching partition, reducing or avoiding large-scale data redistribution.
- **Parallel execution:** using multiple processes to handle partitions or data slices concurrently.

Partition-wise joins do not happen automatically just because two tables are partitioned. Partition key, partitioning method, partition count and boundaries, JOIN conditions, statistics, and cost all influence the optimizer's decision.

## 1. Why Are Partition-Wise Joins Needed?

Suppose there are two tables:

- SALES: hundreds of millions of transactions.
- CUSTOMERS: millions of customers.

Query:

~~~sql
SELECT c.customer_id,
       c.customer_name,
       SUM(s.amount) AS total_amount
FROM customers c
JOIN sales s
  ON s.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name;
~~~

If both tables are compatibly partitioned on CUSTOMER_ID, Oracle can match data in each corresponding customer region. For instance, partition 1 of SALES only needs to join with partition 1 of CUSTOMERS, partition 2 with partition 2, and so on.

~~~text
CUSTOMERS partition 1  <---->  SALES partition 1
CUSTOMERS partition 2  <---->  SALES partition 2
CUSTOMERS partition 3  <---->  SALES partition 3
...
CUSTOMERS partition N  <---->  SALES partition N

          Each pair is joined independently
          Can run in parallel
~~~

Potential benefits:

- Reduces data transferred between parallel execution servers.
- Breaks one huge JOIN into multiple smaller JOINs.
- Reduces memory required per JOIN when data is partitioned sensibly.
- Leverages partition pruning if predicates exist on the partition key.
- Improves scalability for analytical queries on large tables.

Actual benefits depend on data size, skew level, JOIN method, and execution plan. For small tables, broadcast joins or nested loops may be cheaper.

## 2. What Is a Partition-Wise Join?

A partition-wise join is a JOIN execution technique where Oracle divides work by table partitions. Rather than gathering or redistributing both entire datasets before joining, Oracle operates on corresponding data regions.

There are two main forms:

1. **Full partition-wise join:** both tables are compatibly partitioned (equipartitioned) on the JOIN key, enabling matching partition pairs to join without repartitioning either side for that JOIN.
2. **Partial partition-wise join:** only one side has suitable partitioning; Oracle redistributes the other side to match the partitioning of the partitioned side.

### 2.1 Full partition-wise join

For example, both tables are hash-partitioned on CUSTOMER_ID with the same number of partitions and the same partitioning scheme:

~~~text
CUSTOMERS                         SALES
hash(customer_id), 8 partitions  hash(customer_id), 8 partitions

C_P01  ------------------------  S_P01
C_P02  ------------------------  S_P02
C_P03  ------------------------  S_P03
C_P04  ------------------------  S_P04
C_P05  ------------------------  S_P05
C_P06  ------------------------  S_P06
C_P07  ------------------------  S_P07
C_P08  ------------------------  S_P08
~~~

Because the same CUSTOMER_ID maps to the corresponding partition in both tables, Oracle can join each partition pair.

### 2.2 Partial partition-wise join

If SALES is hash-partitioned on CUSTOMER_ID while CUSTOMERS is a nonpartitioned heap table, Oracle does not have pre-aligned partition pairs. In a parallel partial partition-wise join plan, data from the nonpartitioned side can be redistributed to match the partitions of SALES.

~~~text
CUSTOMERS (nonpartitioned)
          |
          | redistribute by JOIN key
          v
  customer rows split by region
          |
          +------> SALES partition 1
          +------> SALES partition 2
          +------> SALES partition 3
          ...

JOIN per SALES partition
~~~

Only one side has compatible partitioning upfront; the other side must be redistributed. Hence this is a partial, not a full, partition-wise join.

### 2.3 Not every JOIN between two partitioned tables is a full partition-wise join

Two tables may both be partitioned yet:

- Partition on different columns.
- Use different partitioning methods.
- Have mismatched partition counts or boundaries.
- Lack the required relationship to the partition key in the JOIN condition.

In such cases, the optimizer may have to hash-redistribute data, broadcast one side, or pick another JOIN plan. Both tables having partitions is insufficient to conclude a full partition-wise join will occur.

## 3. Conditions for a Full Partition-Wise Join

### 3.1 Both tables must be compatibly partitioned

For Oracle to perform a full partition-wise join, tables must be equipartitioned on the JOIN condition. With standard partitioning, verify:

- Same partitioning key or equivalent mapping to the join key.
- Same compatible partitioning method.
- Same number of corresponding partitions.
- Matching partition boundaries/definitions if using range or list partitioning.
- With composite partitioning, subpartition structures must be compatible for the corresponding JOIN.

Exact support details depend on partitioning type and Oracle version. Do not just eyeball partition names or counts; verify metadata and execution plans.

### 3.2 JOIN conditions must connect the partition keys

Suitable example:

~~~sql
SELECT ...
FROM sales s
JOIN customers c
  ON s.customer_id = c.customer_id;
~~~

If both tables are compatibly partitioned by CUSTOMER_ID, the JOIN condition enables pairing corresponding partitions.

Example that does not leverage this design:

~~~sql
SELECT ...
FROM sales s
JOIN customers c
  ON s.region_id = c.region_id;
~~~

If tables are partitioned by CUSTOMER_ID but joined on REGION_ID, two partitions with the same sequence number do not necessarily hold matching rows. Oracle cannot treat them as matching pairs merely because partition names match.

### 3.3 Partition keys may comprise multiple columns

If a table is partitioned on a composite key of multiple columns, the JOIN conditions and partition structures must provide enough linkage for Oracle to prove corresponding regions. Do not assume joining on only a subset of a composite key always suffices for a full partition-wise join.

For example, a table partitioned by `HASH(tenant_id, customer_id)` joined only on `CUSTOMER_ID` cannot guarantee two rows with the same customer reside in the same partition if `TENANT_ID` differs.

### 3.4 Reference partitioning

Oracle supports reference partitioning so a child table inherits partitioning via its foreign key relationship to a parent table. This structure can help parent-child JOINs on the referential key because related data is co-located by design. You still need to verify JOIN type, constraints, and actual execution in the plan.

## 4. Distinguishing Partition-Wise Joins and Partition Pruning

The two techniques often appear together but solve different problems.

### 4.1 Partition pruning

Partition pruning reduces the number of partitions that must be read:

~~~sql
SELECT *
FROM sales
WHERE sale_date >= DATE '2026-01-01'
  AND sale_date <  DATE '2026-02-01';
~~~

If SALES is range-partitioned by SALE_DATE, Oracle can read only the January partition instead of scanning all partitions.

### 4.2 Partition-wise join

Partition-wise join reduces data coordination cost between the two sides of a JOIN by processing matching partition pairs.

Example:

~~~sql
SELECT c.customer_id,
       SUM(s.amount)
FROM customers c
JOIN sales s
  ON s.customer_id = c.customer_id
GROUP BY c.customer_id;
~~~

If both tables are compatibly partitioned by CUSTOMER_ID, Oracle can perform the JOIN per matching partition even if the query does not eliminate any partitions.

### 4.3 They can be used together

If tables are compatibly partitioned by CUSTOMER_ID and the query filters a single customer:

~~~sql
SELECT c.customer_id,
       SUM(s.amount)
FROM customers c
JOIN sales s
  ON s.customer_id = c.customer_id
WHERE c.customer_id = :p_customer_id
GROUP BY c.customer_id;
~~~

Oracle can prune down to the partition holding that CUSTOMER_ID on both tables and join within the selected data region. This combines pruning and partition-wise join; the actual plan must confirm partition start/stop and join operations.

### 4.4 Partitioning by one key does not mean every query prunes

If SALES is partitioned by CUSTOMER_ID while a query filters only on SALE_DATE, Oracle cannot prune by date unless suitable partitioning/subpartitioning exists or predicates imply the partition key.

Partition-wise join also does not automatically restrict how many partitions are read. It can join every pair across all partitions.

## 5. Choosing Partitioning Keys for JOIN Workloads

The partitioning key is an architectural decision. For partition-wise joins to deliver value, analyze large JOINs and their actual frequencies.

### 5.1 Choose a frequently joined key

If SALES frequently joins CUSTOMERS on CUSTOMER_ID, partitioning both tables by CUSTOMER_ID can enable full partition-wise joins.

However, CUSTOMER_ID may not be a good key if:

- Queries predominantly filter by SALE_DATE.
- Data is heavily skewed across CUSTOMER_ID.
- The dimension table is small and a broadcast join is cheaper.
- Data governance requires monthly drops/archives.

Do not pick a partition key based on one query. Balance query workload, data lifecycle, administration, and distribution capability.

### 5.2 Hash partitioning for key-based distribution

Hash partitioning is often suitable when you want relatively even distribution on a key and support for equality JOINs on that key.

Example:

~~~sql
CREATE TABLE customers (
    customer_id   NUMBER NOT NULL,
    customer_name VARCHAR2(100),
    CONSTRAINT pk_customers PRIMARY KEY (customer_id)
)
PARTITION BY HASH (customer_id)
PARTITIONS 8;
~~~

~~~sql
CREATE TABLE sales (
    sale_id     NUMBER NOT NULL,
    customer_id NUMBER NOT NULL,
    sale_date   DATE NOT NULL,
    amount      NUMBER(12,2)
)
PARTITION BY HASH (customer_id)
PARTITIONS 8;
~~~

Both tables use the same hash key and the same partition count. This is the basic design pattern giving Oracle the opportunity for a full partition-wise join on CUSTOMER_ID.

Hash partitioning does not guarantee perfectly even distribution in every scenario. Customers with disproportionate transaction counts still create skew in their assigned partition.

### 5.3 Range partitioning when time-based administration is required

A SALES table is often partitioned by SALE_DATE to:

- Prune data by time intervals.
- Archive or drop old partitions.
- Load data periodically.
- Manage retention.

If CUSTOMERS is partitioned by CUSTOMER_ID, the two tables are not equipartitioned on the same JOIN key. When joining on CUSTOMER_ID, a full partition-wise join is not feasible. The optimizer may use partial/repartition/broadcast or another JOIN strategy.

### 5.4 Composite partitioning

A table can be partitioned by SALE_DATE and subpartitioned by `HASH(CUSTOMER_ID)`:

~~~sql
CREATE TABLE sales_by_month_customer (
    sale_id     NUMBER NOT NULL,
    customer_id NUMBER NOT NULL,
    sale_date   DATE NOT NULL,
    amount      NUMBER(12,2)
)
PARTITION BY RANGE (sale_date)
SUBPARTITION BY HASH (customer_id)
SUBPARTITIONS 8
(
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION pmax     VALUES LESS THAN (MAXVALUE)
);
~~~

Composite partitioning can simultaneously support time-based administration and customer-based distribution within each monthly partition. However, for a full partition-wise join with another table, the other table's partition/subpartition structure must be compatible under Oracle's rules; merely sharing a subpartition key is not enough to assert full equipartitioning.

## 6. Partial Partition-Wise Joins and Data Distribution

### 6.1 One partitioned table, one nonpartitioned table

Suppose SALES is hash-partitioned by CUSTOMER_ID, while CUSTOMERS is a heap table:

~~~sql
SELECT c.customer_id,
       c.customer_name,
       SUM(s.amount) AS total_amount
FROM customers c
JOIN sales s
  ON s.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name;
~~~

In a parallel partial partition-wise join, Oracle can distribute rows from CUSTOMERS by CUSTOMER_ID to the parallel servers processing the corresponding partitions of SALES. The JOIN then executes along the partitions of SALES.

### 6.2 Broadcast join is not the same as partial partition-wise join

If CUSTOMERS is small, Oracle can broadcast dimension data to all parallel servers so each server joins it with its assigned slice of SALES. Broadcast is a data distribution strategy in parallel execution; it can appear in a JOIN plan, but not every broadcast join should be called a partial partition-wise join.

Comparison:

| Strategy | Redistributed side | When potentially useful |
|---|---|---|
| Full partition-wise join | Neither table needs repartitioning for that JOIN | Both tables are equipartitioned |
| Partial partition-wise join | Redistributes unaligned side to match partitioned side | One side is suitably partitioned |
| Broadcast join | Replicates small dataset to multiple parallel servers | One side is small; broadcast is cheap |
| Standard hash repartition join | Redistributes both sides on join key | No compatible partition alignment |

The optimizer chooses the strategy based on cost, cardinality, data size, and DOP.

### 6.3 Cost of redistribution

Redistribution can consume interconnect bandwidth between parallel execution servers, buffers, and TEMP space. On large datasets, transfer and distribution costs can be substantial. Full partition-wise joins avoid part of this work because data is already co-located in matching regions.

Partial partition-wise joins reduce redistribution work compared to repartitioning both tables, though the moved side still incurs distribution cost.

## 7. Partition-Wise Joins with Parallel Execution

### 7.1 Parallel execution servers

Oracle can divide queries into operations running across multiple parallel execution servers (PX servers). With partition-wise joins, each server or group of servers processes one or more partition pairs.

~~~text
Query coordinator
       |
       v
Parallel execution servers
   |       |       |
   v       v       v
  P01     P02     P03  ... partition pairs
   |       |       |
   v       v       v
 JOIN    JOIN    JOIN
   |       |       |
   +-------+-------+
           |
           v
   Aggregate / return results
~~~

### 7.2 Degree of parallelism (DOP)

DOP is the level of parallelism requested or selected for an operation. DOP does not have to equal the partition count:

- More partitions than DOP: one server can process multiple partitions or granules.
- DOP larger than partition count: may limit effective parallelism for certain partition-level operations.
- Many tiny partitions do not automatically guarantee faster queries.
- High DOP consumes extra CPU, PX servers, memory, and interconnect.

### 7.3 Partition granules

Oracle divides parallel work into granules, typically block-range or partition granules depending on operation and structure. With partition-wise joins, partition granules can assign data regions to PX servers. Exact assignment depends on the plan, partition type, and version.

### 7.4 When is parallel execution not beneficial?

For small tables or predicates returning only a few rows, the overhead of spawning PX servers, transferring data, and synchronizing can outweigh the gains. Serial execution using an index range scan or nested loops can be faster.

Do not add `PARALLEL` hints or raise DOP simply because tables are partitioned. Measure elapsed time, CPU, I/O, and impact on concurrent queries.

## 8. Skew and Imbalance Across Partitions

Partition-wise joins divide work by data region, but if partitions differ sharply in size, completion time is dominated by the heaviest partition.

Example:

| Partition | SALES rows |
|---|---:|
| P01 | 10 million |
| P02 | 9 million |
| P03 | 11 million |
| P04 | 70 million |
| P05 | 10 million |
| P06 | 10 million |

P04 is much larger than the other partitions. PX servers processing smaller partitions may finish early and sit idle waiting on the server handling P04.

### 8.1 Causes of skew

- A few customers/tenants have disproportionate transaction volumes.
- NULL or default values cluster into one group.
- Hash keys have uneven distributions or a small value domain.
- One time window experiences abnormally high data volume.
- One value in the join key appears in most rows.

### 8.2 Measuring partition distribution

Estimated row counts per partition can be viewed via:

~~~sql
SELECT partition_name,
       num_rows,
       blocks,
       last_analyzed
FROM user_tab_statistics
WHERE table_name = 'SALES'
  AND partition_name IS NOT NULL
ORDER BY partition_position;
~~~

Numbers depend on when stats were gathered. To assess skew accurately, combine partition statistics, distribution queries on the join key, and runtime plans.

### 8.3 Handling skew

- Choose a partition key with a more balanced distribution.
- Use composite partitioning if distribution within each administrative region is needed.
- Handle hot keys with a dedicated data-design strategy when justified.
- Consider broadcast or skew-aware distribution if suited to the query.
- Tune DOP and granule sizing to the workload.
- Do not create excessive partitions trying to split a hot key if doing so inflates administrative cost.

## 9. Lab: Designing a Full Partition-Wise Join

### 9.1 Create two compatible tables

In a dedicated lab schema:

~~~sql
CREATE TABLE lab_customers (
    customer_id   NUMBER NOT NULL,
    customer_name VARCHAR2(100),
    CONSTRAINT pk_lab_customers PRIMARY KEY (customer_id)
)
PARTITION BY HASH (customer_id)
PARTITIONS 8;
~~~

~~~sql
CREATE TABLE lab_sales (
    sale_id     NUMBER NOT NULL,
    customer_id NUMBER NOT NULL,
    sale_date   DATE NOT NULL,
    amount      NUMBER(12,2)
)
PARTITION BY HASH (customer_id)
PARTITIONS 8;
~~~

Both tables are partitioned on the same key with the same partition count. In real environments, ensure partition definitions are compatible and verify full partition-wise join eligibility in the plan.

### 9.2 Load data

~~~sql
INSERT INTO lab_customers
SELECT LEVEL,
       'Customer ' || LEVEL
FROM dual
CONNECT BY LEVEL <= 10000;

INSERT INTO lab_sales
SELECT LEVEL,
       MOD(LEVEL, 10000) + 1,
       DATE '2026-01-01' + MOD(LEVEL, 365),
       MOD(LEVEL, 1000) + 1
FROM dual
CONNECT BY LEVEL <= 1000000;

COMMIT;
~~~

### 9.3 Gather statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'LAB_CUSTOMERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        cascade          => TRUE
    );

    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'LAB_SALES',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        cascade          => TRUE
    );
END;
/
~~~

Accurate statistics help the optimizer estimate cardinality and cost better. On partitioned tables, you may need to verify both global and partition statistics per your system's statistics policy.

### 9.4 Run the JOIN

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id,
       c.customer_name,
       SUM(s.amount) AS total_amount
FROM lab_customers c
JOIN lab_sales s
  ON s.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name;
~~~

After running, view the cursor plan:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARTITION +PARALLEL +PREDICATE +ALIAS'
    )
);
~~~

Check operations and PX distribution. Exact operation names vary by version and plan; look for signs that partitions are processed in aligned pairs and see whether redistribution occurs. Do not infer a full partition-wise join solely from seeing `TABLE ACCESS FULL` on partitioned tables.

### 9.5 Check pruning

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id,
       SUM(s.amount) AS total_amount
FROM lab_customers c
JOIN lab_sales s
  ON s.customer_id = c.customer_id
WHERE c.customer_id = 42
GROUP BY c.customer_id;
~~~

Because both tables are hash-partitioned by `CUSTOMER_ID`, Oracle can pinpoint the partition to access. In the plan, inspect PSTART/PSTOP or corresponding partition start/stop indicators. This demonstrates pruning combined with a JOIN; the full-dataset JOIN earlier can run partition-wise without pruning any partitions.

## 10. Example of a Partial Partition-Wise Join

### 10.1 Create a nonpartitioned dimension table

~~~sql
CREATE TABLE lab_customers_heap (
    customer_id   NUMBER PRIMARY KEY,
    customer_name VARCHAR2(100)
);
~~~

Load data from the existing table:

~~~sql
INSERT INTO lab_customers_heap
SELECT customer_id,
       customer_name
FROM lab_customers;
COMMIT;
~~~

`SALES` remains partitioned by `CUSTOMER_ID`; `CUSTOMERS_HEAP` is nonpartitioned. The JOIN condition remains `CUSTOMER_ID`.

### 10.2 Query

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id,
       c.customer_name,
       SUM(s.amount) AS total_amount
FROM lab_customers_heap c
JOIN lab_sales s
  ON s.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name;
~~~

The optimizer may choose a partial partition-wise join if a distribution plan is advantageous. With a small dimension table, the optimizer may also choose a broadcast join. Outcome depends on cardinality, DOP, memory, and statistics.

### 10.3 View plan and distribution

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARTITION +PARALLEL +PREDICATE'
    )
);
~~~

Observe `PX SEND`, `PX RECEIVE`, `HASH JOIN`, or partition-related operations. Having PX operations alone does not prove a partial partition-wise join; read the entire plan tree to see which table is redistributed and which partitions are processed.

## 11. Partition-Wise Joins with Range and Composite Partitioning

### 11.1 Two compatibly range-partitioned tables

If two tables are both partitioned by `SALE_DATE` with matching time boundaries and joined on `SALE_DATE` or conditions compatible with the partitioning, Oracle can process matching partition pairs.

Monthly partition example:

~~~text
ORDERS:
  P2026_01: sale_date < 2026-02-01
  P2026_02: sale_date < 2026-03-01

ORDER_LINES:
  P2026_01: sale_date < 2026-02-01
  P2026_02: sale_date < 2026-03-01
~~~

In practice, `ORDER_LINES` is often partitioned by `ORDER_DATE` inherited from `ORDERS` via reference partitioning or using a matching structure. Design relationships and partition boundaries accurately; two tables with identical partition names but differing boundaries do not create equipartitioning.

### 11.2 Composite partitioning

If both tables share the same time-based range partitions and hash subpartitions on `CUSTOMER_ID` with matching structure, Oracle can exploit partition/subpartition alignment for eligible queries. However, exact eligibility depends on how composite partitioning is defined and on join predicates.

### 11.3 Reference partitioning

With parent and child tables linked by a foreign key, reference partitioning lets the child be partitioned according to the parent table's partitions. This is a natural way to co-locate relational data, especially when queries frequently join parent and child. Creating the FK must still satisfy application constraint and index requirements.

## 12. Join Method Inside Each Partition Pair

Partition-wise join describes how data regions are divided for a JOIN; it does not mandate a single join method.

Inside each partition pair, Oracle can still choose:

- **Nested loops:** suited when one side is very small or index access fetches few rows.
- **Hash join:** typically suited when both datasets are large and a hash table can be built.
- **Sort merge join:** suited in certain cases when data is already ordered or sort/merge costs are favorable.

Example:

~~~text
Partition pair P01:
    HASH JOIN(CUSTOMERS_P01, SALES_P01)

Partition pair P02:
    HASH JOIN(CUSTOMERS_P02, SALES_P02)

Partition pair P03:
    HASH JOIN(CUSTOMERS_P03, SALES_P03)
~~~

Partition-wise does not equate to hash join; it is a way of dividing join work by partition. The exact join method is chosen independently by the optimizer based on cost.

## 13. Global Indexes, Local Indexes, and Partition-Wise Joins

### 13.1 Local index

A local index is partitioned in alignment with table partitions. It simplifies partition administration and can assist queries within each partition.

~~~sql
CREATE INDEX ix_lab_sales_customer_local
ON lab_sales (customer_id)
LOCAL;
~~~

A local index can assist index access inside a partition, but a local index by itself does not produce a full partition-wise join. The core requirement remains the partitioning of the tables and the JOIN itself.

### 13.2 Global index

A global index has partitioning/structure independent of the table's partitions. It can aid lookups by keys that do not match the partition key, though partition maintenance operations can affect global index status depending on statements and options.

### 13.3 Do not confuse index partitioning with table partition alignment

Partition-wise join operates on row sources/table partitions during a JOIN. Two indexes both being local does not mean the two tables are equipartitioned on the join key. Inspect table partition definitions, not just indexes.

## 14. Reading Execution Plans to Verify

### 14.1 Collect actual statistics

Run the query with `GATHER_PLAN_STATISTICS`:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       ...
FROM ...
JOIN ... ON ...;
~~~

Then:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARTITION +PARALLEL +PREDICATE +ALIAS'
    )
);
~~~

### 14.2 What to inspect

- **Operation:** `HASH JOIN`, `NESTED LOOPS`, `PARTITION HASH ALL`, `TABLE ACCESS FULL`, etc.
- **PSTART/PSTOP:** partition start/stop, showing partition pruning or partition range.
- **PX SEND/PX RECEIVE:** data transferred between parallel execution servers.
- **Distribution method:** `HASH`, `BROADCAST`, `PARTITION`, or other distribution displayed in the plan.
- **E-Rows/A-Rows:** estimated and actual row counts.
- **Buffers/Reads:** logical and physical I/O.
- **TempSpc:** estimated/displayed temporary space for certain operations.

Operation names and display layout vary across versions, plans, and partition types. Read the plan tree top-down by parent/child relationships rather than searching for a single keyword.

### 14.3 Signs of a full partition-wise join

The primary expectation is that both sides of the JOIN are processed by corresponding partitions without repartitioning both datasets on the join key. With parallel execution, the plan may display partition-wise distribution/operations. Verify:

1. Both tables are genuinely equipartitioned on the join key.
2. Join predicates include the required partition key linkage.
3. The plan shows no unnecessary redistribution of both sides before the JOIN.
4. Actual rows/buffers align with expectations.

No single operation name appears across all versions to identify every full partition-wise join.

### 14.4 Signs of a partial partition-wise join

Identify the partitioned side, the nonpartitioned or unaligned side, and verify the plan redistributes the remaining side to match the partitioned side. Distinguish this from dimension broadcast or standard hash repartitioning.

## 15. Organizing Queries by Data Regions

Partition-wise joins work best when both query design and data design respect partition boundaries.

### 15.1 Use predicates on the partition key when possible

For example, on a `SALES` table range-partitioned by `SALE_DATE`:

~~~sql
SELECT ...
FROM sales
WHERE sale_date >= :p_from_date
  AND sale_date <  :p_to_date;
~~~

Using a half-open interval `[from, to)` clearly defines boundaries and typically supports partition pruning. Avoid wrapping the partition key in functions if it prevents Oracle from deriving partition ranges, unless an expression-based partitioning design matches it.

### 15.2 Keep JOIN conditions clear

~~~sql
ON s.customer_id = c.customer_id
~~~

Direct JOIN conditions on the partition key help the optimizer recognize partition alignment. If data type conversions or functions are applied to join keys, verify whether the optimizer can still deduce the relationship and use a partition-wise join.

### 15.3 Avoid forcing join order or DOP without evidence

Hints such as `LEADING`, `USE_HASH`, and `PARALLEL` can alter plans. Use them only when verified on representative workloads and with clear justification. A hint can help one bind value while slowing down other queries.

### 15.4 Organizing data regions by tenant

In multi-tenant applications, partitioning by `TENANT_ID` can isolate data and enable tenant pruning. If multiple large tables are compatibly partitioned by `TENANT_ID` and joined on tenant plus business keys, partition-wise joins can reduce redistribution.

However, exceptionally large tenants can cause skew. Subpartitions or separate strategies for huge tenants may be needed, balanced against administrative cost and partition compatibility.

## 16. Performance and Practical Limits

Partition-wise joins can cut communication costs, yet they do not automatically lower every cost:

- Total rows to join remain the same.
- One oversized partition can become a bottleneck.
- Hash joins still need memory and can spill to `TEMP`.
- Excessive partition counts increase metadata and management overhead.
- High DOP can contend for CPU, I/O, and interconnect.
- Stale statistics can lead the optimizer to pick poor join methods or distributions.
- Data skew can make some PX servers run far longer than others.
- Partition-wise joins do not replace partition pruning, indexing, or query rewrites.

### 16.1 Partition count

Do not pick partition counts strictly by CPU core count. Consider:

- Total data size and growth rate.
- Target DOP.
- Average partition size and skew.
- Number of involved tables and equipartitioning feasibility.
- Maintenance, backup, recovery, and statistics duration.

### 16.2 Table-level and partition-level statistics

Partitioned tables require accurate statistics at both partition and global levels. If global stats or partition stats are inconsistent, the optimizer may misestimate row counts, pruning, and join costs.

Gathering statistics:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        granularity      => 'AUTO',
        cascade          => TRUE
    );
END;
/
~~~

`GRANULARITY => 'AUTO'` directs Oracle to choose a collection scope suited to partitioning. Specific stats strategies also depend on incremental statistics, global stats, and data loading methods.

### 16.3 Incremental statistics

For large partitioned tables, incremental statistics can maintain global statistics by aggregating information from modified partitions rather than rescanning the entire table in supported cases. This feature requires configuring preferences and evaluating version/licensing/system settings; do not enable it based solely on a single example.

## 17. Common Misconceptions

| Misconception | Reality | Resolution |
|---|---|---|
| Any two partitioned tables get full partition-wise join | Must be compatibly partitioned on join key | Check partition key/method/boundaries |
| Partition-wise join and partition pruning are the same | One splits the JOIN; the other skips partitions | Analyze each benefit separately |
| Same partition count is enough | Compatible partitioning scheme is also required | Confirm equipartitioning |
| Local indexes create partition-wise joins | Joins rely on table partitioning and JOIN conditions | Inspect table partition metadata |
| Full partition-wise join is always faster | With small tables or skew, other plans may be cheaper | Compare actual runtime/cost |
| Partial partition-wise join equals broadcast join | Partial redistributes unaligned side compatibly; broadcast is a distinct strategy | Read PX distribution |
| Partition-wise joins always need parallel query | Can process per partition; parallelism is one way to scale throughput | Check plans and workloads |
| Having partitions guarantees automatic pruning | Predicates/conditions must be able to resolve partitions | Check PSTART/PSTOP |
| Identical partition names mean compatibility | Names do not prove identical boundaries or hash mappings | Compare partition definitions |
| Hash partitions are always perfectly balanced | Hot keys can cause skew | Measure row and block counts per partition |
| Raising DOP always lowers runtime | Can increase contention and communication | Benchmark against SLAs |
| Partition-wise joins eliminate all network traffic | Partial joins and later steps may still redistribute | Inspect `PX SEND`/`RECEIVE` |
| Repartitioning both tables is always needed | Full partition-wise joins can avoid that step | Design equipartitioning |

## 18. Design and Analysis Checklist

When intending to use partition-wise joins, verify:

1. Which large JOIN queries actually consume major resources?
2. Which join keys are used frequently and what are their data distributions?
3. Can the large tables be compatibly partitioned on the join key?
4. Does the partitioning key also serve pruning, retention, and data governance?
5. Do both tables share the same partitioning method, partition count, and matching boundaries?
6. Do join predicates connect the partition keys properly?
7. Is a full partition-wise join possible, or only partial?
8. If one side is small, is broadcast cheaper than redistribution?
9. Do partition sizes and join-key distributions exhibit skew?
10. Are DOP and partition counts well-matched?
11. Are global/partition statistics gathered completely?
12. Does the execution plan show expected partition access and PX distribution?
13. Are E-Rows close to A-Rows?
14. How do Buffers, Reads, TEMP, and elapsed time change?
15. Do DML, index maintenance, and partition operations incur significant extra cost?
16. After adding partitions or altering boundaries, do related tables remain equipartitioned?

## 19. Self-Practice Exercises

**Question 1 — Concept.** Which cost does a partition-wise join reduce when two tables are compatibly partitioned?

Hint: Reduces the need to redistribute data across PX servers and splits the JOIN across partition pairs.

**Question 2 — Full join.** Two tables are both hash-partitioned on `CUSTOMER_ID`, with identical partition counts and mapping; joined on `CUSTOMER_ID`. Which form is eligible?

Hint: Eligible for full partition-wise join; still requires optimizer selection and plan verification.

**Question 3 — Incompatible.** `SALES` is partitioned by `SALE_DATE`, `CUSTOMERS` by `CUSTOMER_ID`; joined on `CUSTOMER_ID`. Is it eligible for a full partition-wise join?

Hint: Not from this design alone; the two tables are not partitioned on the same join key.

**Question 4 — Partial join.** `SALES` is partitioned by `CUSTOMER_ID`, while `CUSTOMERS` is a heap table. What can happen?

Hint: Oracle can redistribute `CUSTOMERS` to match `SALES` partitions in a partial partition-wise join; or pick broadcast/another plan.

**Question 5 — Pruning.** A JOIN on `CUSTOMER_ID` has no filter on the partition key. Can a partition-wise join still occur?

Hint: Yes. Partition-wise join does not require partition pruning; it can join all partition pairs.

**Question 6 — Skew.** What issue arises when one partition holds 10x more rows than the others?

Hint: The PX server handling the oversized partition can become a bottleneck while other servers wait.

**Question 7 — Local index.** Two tables have identically named local indexes, yet incompatible partition schemes. Are they eligible for a full partition-wise join?

Hint: No. Check table partitioning rather than inferring from indexes.

**Question 8 — DOP.** There are 4 partitions, but DOP 16 is requested. Are all 16 servers guaranteed independent partition work?

Hint: No. Granules and work assignment depend on partitions; partition count does not always equate to active useful PX servers.

**Question 9 — Broadcast.** Is sending a small dimension table to every PX server a partial partition-wise join?

Hint: Not necessarily. Broadcast is a separate distribution strategy; inspect the plan.

**Question 10 — Verification.** Beyond `EXPLAIN PLAN`, what should be inspected to evaluate performance?

Hint: Actual rows, buffers, reads, `TEMP`, PX distribution, and runtime via `DBMS_XPLAN.DISPLAY_CURSOR`.

## 20. Summary

Partition-wise joins organize JOIN execution along partitioned data regions to reduce data movement and coordination work:

- **Full partition-wise joins** are possible when two tables are compatibly equipartitioned on the join key; Oracle joins matching partition pairs.
- **Partial partition-wise joins** apply when one side is suitably partitioned and the other side is redistributed to match.
- **Partition pruning** reduces partitions read; it is distinct from partition-wise join and can be combined with it.
- **Parallel execution** processes partition pairs concurrently, though DOP must match partition counts, data sizes, and resources.
- **Skew** can turn a single partition into a bottleneck even when a JOIN is split by partition.
- Local indexes assist access within partitions, yet do not automatically create partition-wise joins.
- Execution plans, PX distribution, PSTART/PSTOP, actual rows, buffers, and reads provide the evidence to inspect before drawing conclusions.

Good partition-wise join design starts from the workload: pick a partition key serving major JOINs while still supporting pruning, retention, and data governance. Then confirm equipartitioning, measure skew, gather statistics, and inspect actual execution plans. Partitioning is valuable only when data organization aligns with real queries and total operational cost.
