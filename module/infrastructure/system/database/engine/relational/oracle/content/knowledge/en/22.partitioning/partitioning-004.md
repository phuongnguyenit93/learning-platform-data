# Partition Keys by Time, Customer, or Data Domain

A partition key is the column or group of columns Oracle uses to determine which partition of a table a row belongs to. Choosing the partition key directly affects partition pruning capability, data distribution, lifecycle storage, maintenance cost, and the ability to leverage indexes or partition-wise joins.

Three common design directions are:

- **By time:** uses the date or timestamp when data occurs, suited for continuously growing data with a clear retention lifecycle.
- **By customer:** uses customer ID or tenant ID, suited when queries frequently filter on a single customer and data needs to be distributed across multiple partitions.
- **By data domain:** uses geographic region, business unit, business type, or a stable classification domain, suited when queries and operations are commonly divided by those domains.

No single partition key fits every workload. The key must reflect how applications read, write, store, and delete data. This lesson uses Oracle Database 19c syntax as a reference context; some DDL options and operations may differ across versions.

## 1. What Is a Partition Key?

A partitioned table is one logical table divided into multiple physical partitions. Each partition stores a subset of the table's data, while applications still query the table by its normal table name.

Example transaction table:

~~~sql
CREATE TABLE sales (
    sale_id      NUMBER(12) NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER(12) NOT NULL,
    region_code  VARCHAR2(20),
    amount       NUMBER(14,2) NOT NULL
);
~~~

If partitioned by SALE_DATE, Oracle uses the date value to determine which partition holds the row. If partitioned by CUSTOMER_ID, the customer value determines the partition. If partitioned by REGION_CODE, the data domain code determines the partition.

A partition key can consist of one or more columns. The partitioning type determines how Oracle interprets the key value:

| Type | Division method |
|---|---|
| RANGE | By bounded value ranges |
| LIST | By a declared list or group of values |
| HASH | Uses a hash function to distribute key values |
| COMPOSITE | Combines two levels, such as RANGE-HASH or RANGE-LIST |

### 1.1 Partitioning is physical storage organization

A partition key is not an automatic application filter. A query with an appropriate condition on the partition key can allow Oracle to skip irrelevant partitions (*partition pruning*).

Example of a monthly partitioned table:

~~~sql
SELECT SUM(amount)
FROM sales
WHERE sale_date >= DATE '2026-03-01'
  AND sale_date <  DATE '2026-04-01';
~~~

Oracle can read only the March 2026 partition instead of scanning all partitions. However, if a query filters only by CUSTOMER_ID without a SALE_DATE condition, Oracle may have to read many or all time partitions.

### 1.2 Partition keys must come from the workload

Before choosing a key, answer:

1. Which columns do queries frequently filter on?
2. Along which dimension does data grow: time, customer, region, or business type?
3. Is periodic deletion or archiving of old data needed?
4. Is data distribution balanced across key values?
5. How many rows and how many GB is one partition expected to hold?
6. Will many sessions write concurrently into a single partition?
7. Can major JOINs align on the partition key?
8. Is the key stable throughout a row's lifecycle?

Choosing a key merely because a column has many distinct values or for a single isolated query often leads to a design that is difficult to operate.

## 2. Choosing a Time-Based Partition Key

Time-based partitioning is very common for transaction tables, events, logs, invoices, measurement history, and continuously generated data.

Commonly used columns:

- ORDER_DATE.
- SALE_DATE.
- CREATED_AT.
- EVENT_TIMESTAMP.
- BUSINESS_DATE.

### 2.1 Why is time often a good partition key?

Time-based partitioning works well when:

- Queries frequently restrict date/month/quarter ranges.
- New data is continuously appended.
- Old data can be archived or deleted periodically.
- Reports commonly run by day, month, or year.
- Periods can be managed via partition maintenance operations.

For example, a sales system keeps 24 months of hot data. When a new month starts, the system creates a new partition; data past retention can be archived and the corresponding partition dropped according to the retention policy.

### 2.2 Monthly RANGE partitioning

Example of creating a monthly partitioned table:

~~~sql
CREATE TABLE sales_by_month (
    sale_id      NUMBER(12) NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER(12) NOT NULL,
    amount       NUMBER(14,2) NOT NULL
)
PARTITION BY RANGE (sale_date) (
    PARTITION p_before_2026
        VALUES LESS THAN (DATE '2026-01-01'),
    PARTITION p2026_01
        VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02
        VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION p2026_03
        VALUES LESS THAN (DATE '2026-04-01'),
    PARTITION p_future
        VALUES LESS THAN (MAXVALUE)
);
~~~

RANGE partitions use exclusive upper bounds. Partition P2026_01 contains values from its lower bound (after the previous partition) up to before 2026-02-01. Because DATE values include a time component, monthly reporting predicates should generally use a half-open interval:

~~~sql
WHERE sale_date >= DATE '2026-03-01'
  AND sale_date <  DATE '2026-04-01'
~~~

Avoid using:

~~~sql
WHERE TRUNC(sale_date, 'MM') = DATE '2026-03-01'
~~~

if the goal is filtering partitions on a regular SALE_DATE column. Wrapping a function around the partition key can hinder pruning or require other transformations. A half-open interval covers every instant in the month while avoiding reliance on 23:59:59 on the last day.

### 2.3 INTERVAL partitioning for time-growing data

If data continuously arrives for future periods, INTERVAL partitioning lets Oracle create partitions automatically as needed:

~~~sql
CREATE TABLE sales_interval (
    sale_id      NUMBER(12) NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER(12) NOT NULL,
    amount       NUMBER(14,2) NOT NULL
)
PARTITION BY RANGE (sale_date)
INTERVAL (NUMTOYMINTERVAL(1, 'MONTH')) (
    PARTITION p_before_2026
        VALUES LESS THAN (DATE '2026-01-01')
);
~~~

The first partition defines the transition point. When inserting data beyond this point, Oracle can create interval partitions corresponding to monthly intervals. Partition names created by Oracle may be system-generated; if operations require human-readable names, review metadata management and appropriate naming strategies.

INTERVAL does not replace monitoring storage, statistics, indexes, and retention policies. Check whether new partitions are created in the expected periods and with the desired storage attributes.

### 2.4 Choosing granularity: day, month, quarter, or year?

| Granularity | Suitable when | Risk |
|---|---|---|
| Day | Very large data, daily queries and retention | Partition count grows rapidly |
| Month | Monthly reporting and retention workload | A single month can become too large on massive systems |
| Quarter | Moderate data, quarterly reporting | One-month queries must scan a larger partition |
| Year | Moderate/smaller data, long retention | Limited pruning for short queries and coarse maintenance |

There is no universal optimal partition count. Choose granularity based on total size, data growth rate, projected partition count over multiple years, management overhead, and operational capability.

### 2.5 Late-arriving data and historical data

Real-time systems can receive late-arriving transactions:

- Prior-month transactions arriving after the prior-month partition was already processed.
- Historical import data with old dates.
- Events with timestamps from unsynchronized device clocks.

Partitioning by occurrence time requires a handling path for late data. You may need a historical partition, an appropriate catch-all partition, or a staging workflow to move data into the target partition.

If a MAXVALUE partition is used to catch future data, adding new partitions requires splitting MAXVALUE via the appropriate procedure. With interval partitioning, Oracle creates corresponding partitions for values beyond the transition point.

### 2.6 DATE, TIMESTAMP, and time zones

Choose the right temporal data type:

- DATE stores date and time down to seconds, without time zone.
- TIMESTAMP has higher fractional-second precision but does not carry a time zone by itself.
- TIMESTAMP WITH TIME ZONE stores time zone information.
- TIMESTAMP WITH LOCAL TIME ZONE is normalized to the database time zone and displayed in the session time zone.

If data arrives from multiple time zones, establish a storage standard—typically UTC or a uniform convention—before partitioning. Avoid having the same business instant land in different partitions simply because sessions use different time zones.

### 2.7 Retention and partition maintenance

Time-based partitioning enables period-by-period operations:

~~~sql
ALTER TABLE sales_by_month
TRUNCATE PARTITION p2026_01;
~~~

TRUNCATE PARTITION removes data inside a partition without row-by-row DELETE. When a period has expired and the partition structure no longer needs to be kept:

~~~sql
ALTER TABLE sales_by_month
DROP PARTITION p2026_01;
~~~

These operations are DDL and have an implicit commit boundary in Oracle. They cannot be rolled back like an uncommitted DELETE. Before executing, verify retention, archiving, backup/recovery, and index maintenance.

## 3. Choosing a Customer-Based Partition Key

Partitioning by CUSTOMER_ID or TENANT_ID suits SaaS, CRM, billing, account data, or multi-tenant platforms where most queries are scoped to a single customer.

Example:

~~~sql
SELECT order_id, order_date, total_amount
FROM orders
WHERE customer_id = :customer_id;
~~~

If the table is partitioned by CUSTOMER_ID, Oracle can pinpoint the relevant partition and avoid reading other customers' data.

### 3.1 HASH partitioning by customer_id

With a large or continuously growing customer count, a separate LIST partition per customer is usually not a good choice. HASH partitioning distributes key values across a fixed number of partitions:

~~~sql
CREATE TABLE customer_events (
    event_id     NUMBER(14) NOT NULL,
    customer_id  NUMBER(12) NOT NULL,
    event_time   TIMESTAMP NOT NULL,
    event_type   VARCHAR2(30),
    payload      CLOB
)
PARTITION BY HASH (customer_id)
PARTITIONS 32;
~~~

Equality queries on customer_id can be hash-pruned to the corresponding partition:

~~~sql
SELECT event_id, event_time, event_type
FROM customer_events
WHERE customer_id = :customer_id;
~~~

HASH partitioning fits when:

- There are very many customer IDs.
- You want to distribute customers across a fixed number of partitions.
- You do not need to name/manage a separate partition per customer.
- Queries commonly use equality or a list of key values.

### 3.2 HASH does not split a single customer's data

Important point: all rows with the same CUSTOMER_ID hash to the same partition. HASH distributes different customers across partitions; it does not split a single huge customer across multiple partitions.

If one customer generates 40% of all events, the partition holding that customer can still grow disproportionately large. This is key skew. Increasing the partition count does not cause a single customer ID to spread across multiple partitions.

For very large customers, consider:

- Designing a subpartition on another key if queries accept reading multiple subpartitions.
- Separating the workload or data of exceptional customers using a dedicated model.
- Aggregating/archiving historical data.
- Distributing by event key if the goal is spreading write load, while accepting that customer queries may have to read more partitions.

Do not add a column to the partition key just to make partitions smaller if doing so breaks pruning or data management requirements.

### 3.3 RANGE partitioning by customer_id

RANGE partitioning by ID can be useful when IDs have a clear value domain and queries frequently access ID ranges:

~~~sql
CREATE TABLE customer_archive (
    customer_id NUMBER(12) NOT NULL,
    customer_name VARCHAR2(200),
    created_at TIMESTAMP
)
PARTITION BY RANGE (customer_id) (
    PARTITION p_customer_0_99999
        VALUES LESS THAN (100000),
    PARTITION p_customer_100k_199k
        VALUES LESS THAN (200000),
    PARTITION p_customer_200k_299k
        VALUES LESS THAN (300000),
    PARTITION p_customer_other
        VALUES LESS THAN (MAXVALUE)
);
~~~

This fits ID-range queries or ID-group management better. However, sequentially increasing IDs can send all new INSERTs to the final partition, creating a write hotspot. RANGE by customer ID also does not guarantee equal row counts per partition because different customers can generate vastly different data volumes.

### 3.4 LIST partitioning for a few large tenants

LIST partitioning can make sense when there is a small, stable set of large tenants requiring separate management:

~~~sql
CREATE TABLE tenant_transactions (
    transaction_id NUMBER(14) NOT NULL,
    tenant_code    VARCHAR2(30) NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    amount         NUMBER(14,2)
)
PARTITION BY LIST (tenant_code) (
    PARTITION p_tenant_a VALUES ('TENANT_A'),
    PARTITION p_tenant_b VALUES ('TENANT_B'),
    PARTITION p_other VALUES (DEFAULT)
);
~~~

LIST fits a manageable set of classification values. If there are tens of thousands or millions of tenants, creating a partition per tenant makes metadata, DDL, indexes, and operations overly complex.

### 3.5 Customer partitioning and tenant security

Partitioning does not replace data access control:

- TENANT_ID conditions in SQL must still be enforced.
- Virtual Private Database (VPD), row-level security, or appropriate application authorization mechanisms may be needed.
- Do not treat placing each tenant in its own partition as a security boundary.
- Prevent SQL injection or clients tampering with tenant IDs to read another tenant's data.

Partition pruning is a storage/access optimization, not authorization.

## 4. Choosing a Data-Domain Partition Key

A data domain can be:

- REGION_CODE or COUNTRY_CODE.
- BUSINESS_UNIT.
- PRODUCT_CATEGORY.
- TRANSACTION_TYPE.
- SOURCE_SYSTEM.
- A stable business data grouping.

If applications frequently query by domain and each domain has substantial volume, LIST partitioning can help organize data cleanly.

### 4.1 LIST partitioning by region

~~~sql
CREATE TABLE regional_sales (
    sale_id      NUMBER(12) NOT NULL,
    region_code  VARCHAR2(20) NOT NULL,
    sale_date    DATE NOT NULL,
    amount       NUMBER(14,2) NOT NULL
)
PARTITION BY LIST (region_code) (
    PARTITION p_north VALUES ('NORTH'),
    PARTITION p_central VALUES ('CENTRAL'),
    PARTITION p_south VALUES ('SOUTH'),
    PARTITION p_other VALUES (DEFAULT)
);
~~~

The query:

~~~sql
SELECT SUM(amount)
FROM regional_sales
WHERE region_code = 'SOUTH';
~~~

can be pruned to the SOUTH partition.

### 4.2 Choose domains with stable values

A domain-based partition key should:

- Have a finite or manageable number of values.
- Rarely change over a row's lifetime.
- Be meaningful in queries or operations.
- Have a reasonably balanced data distribution.
- Have a clear process for adding new domains.

If a row frequently changes REGION_CODE, it may have to move across partitions. If one domain holds 90% of the data, the other partitions remain tiny while the large partition becomes a hotspot.

### 4.3 Avoid LIST partitioning on frequently changing statuses

For example, order status:

~~~text
NEW -> PAID -> SHIPPED -> COMPLETED
~~~

If partitioned by STATUS, every status transition can force row movement between partitions. This generates extra DML cost, index maintenance, and row movement overhead; time-based historical queries also may not prune well.

Status-based partitioning should only be considered when statuses are stable, data is cleanly segmented by status, and workloads/maintenance genuinely benefit. For frequently changing statuses, an appropriate index or time-based partitioning is usually an alternative worth comparing.

### 4.4 Data domain does not mean partitioning by high-cardinality values

Columns like EMAIL, DEVICE_ID, or ORDER_ID have millions of distinct values. Creating LIST partitions per value creates far too many partitions and is unmanageable. If distribution across a high-cardinality key is needed, HASH is usually more appropriate; if querying a specific value is the goal, an index may suffice.

## 5. Combining Time with Customer or Data Domain

A large system may need both date-based pruning and distribution by customer or region. Composite partitioning enables a two-level split.

### 5.1 RANGE-HASH: time at outer level, customer at inner level

~~~sql
CREATE TABLE sales_range_hash (
    sale_id      NUMBER(14) NOT NULL,
    sale_date    DATE NOT NULL,
    customer_id  NUMBER(12) NOT NULL,
    amount       NUMBER(14,2) NOT NULL
)
PARTITION BY RANGE (sale_date)
SUBPARTITION BY HASH (customer_id)
SUBPARTITIONS 8 (
    PARTITION p2026_01
        VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02
        VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION p2026_03
        VALUES LESS THAN (DATE '2026-04-01')
);
~~~

This design serves two goals:

- RANGE on SALE_DATE for period pruning and retention management.
- HASH on CUSTOMER_ID to distribute different customers' data within each time partition.

Queries filtering by date and customer can prune both the time partition and the hash subpartition if the optimizer can resolve the keys:

~~~sql
SELECT SUM(amount)
FROM sales_range_hash
WHERE sale_date >= DATE '2026-02-01'
  AND sale_date <  DATE '2026-03-01'
  AND customer_id = :customer_id;
~~~

Note that all rows for the same customer within a month still land in the same hash subpartition for that month. This design distributes multiple customers within a period; it does not split one large customer across multiple hash subpartitions.

### 5.2 RANGE-LIST: time and data domain

When reporting and retention are monthly while operations are regional:

~~~sql
CREATE TABLE sales_range_list (
    sale_id      NUMBER(14) NOT NULL,
    sale_date    DATE NOT NULL,
    region_code  VARCHAR2(20) NOT NULL,
    amount       NUMBER(14,2) NOT NULL
)
PARTITION BY RANGE (sale_date)
SUBPARTITION BY LIST (region_code)
SUBPARTITION TEMPLATE (
    SUBPARTITION sp_north VALUES ('NORTH'),
    SUBPARTITION sp_central VALUES ('CENTRAL'),
    SUBPARTITION sp_south VALUES ('SOUTH'),
    SUBPARTITION sp_other VALUES (DEFAULT)
)
(
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01')
);
~~~

SUBPARTITION TEMPLATE applies the same domain structure to the time partitions created under the definition. Before using in a target environment, verify syntax and support for your specific Oracle version.

### 5.3 Choosing the order of the two levels

The ordering of partitions and subpartitions has operational significance:

- RANGE outer, HASH inner: generally advantageous when time-based retention and pruning are primary priorities.
- RANGE outer, LIST inner: fits when organizing individual domains inside each time period.
- HASH outer, RANGE inner: can be used when customer distribution is the top priority while still subdividing time within each group.

Do not pick the order based on a single query. Evaluate common queries, maintenance, partition/subpartition counts, and partition-wise join potential.

### 5.4 Composite partitioning increases object counts

With 120 monthly partitions and 16 subpartitions each, a table has 1,920 subpartitions. Account for total partition/subpartition counts over multiple years, index partitions, metadata, statistics, and maintenance time.

Increasing partition counts is not free. Only add a subpartition level when it solves a concrete issue such as data distribution, parallelism, or pruning.

## 6. Comparing the Three Partition Key Directions

| Criterion | By time | By customer | By data domain |
|---|---|---|---|
| Typical type | RANGE or INTERVAL | HASH, occasionally RANGE/LIST | LIST or RANGE |
| Queries benefiting | Date/month/quarter ranges | Equality on customer/tenant | Filtering by region/business unit/type |
| Retention | Very convenient by period | Requires customer-level policy or separate archiving | Convenient if lifecycle aligns with domain |
| Data distribution | New data may concentrate in the newest partition | HASH distributes many customer keys | Depends on balance across domains |
| Skew risk | One period experiences a spike | Large customer creates a hot partition | One domain holds most of the data |
| Does the key change? | Business dates rarely change, though historical edits can occur | Customer/tenant IDs are usually stable | Region/status can change |
| Maintenance | Create, archive, drop partitions by period | Adding/changing hash partition count usually requires planning | Adding domain values and managing DEFAULT |
| Off-key queries | May have to read many partitions | May have to read many partitions | May have to read many partitions |

### 6.1 Sample workload patterns

| Workload | Design to consider |
|---|---|
| Sales transactions, monthly reporting, 7-year retention | RANGE/INTERVAL by transaction date |
| SaaS with millions of small tenants, queries by tenant ID | HASH by tenant ID |
| A few large tenants requiring dedicated management | LIST by major tenant or tiered design |
| Event logs queried by month and customer | RANGE by time, HASH subpartition by customer |
| Data split by stable regions, regional reporting | LIST by region |
| Domain-segmented data requiring monthly retention | RANGE-LIST |
| Sequentially increasing IDs, ID-range queries | RANGE by ID if write hotspot and distribution are acceptable |

These are design directions to test, not formulas to apply blindly.

## 7. Partition Pruning and How the Partition Key Affects Queries

Partition pruning is Oracle's ability to skip partitions that do not need to be read based on predicates and partition metadata.

### 7.1 Static pruning

When filter values can be determined at parse/optimization time, Oracle can identify the partitions to read early.

~~~sql
SELECT COUNT(*)
FROM sales_by_month
WHERE sale_date >= DATE '2026-01-01'
  AND sale_date <  DATE '2026-02-01';
~~~

With date literals and matching RANGE partitions, the plan can target a single partition.

### 7.2 Dynamic pruning

When partition key values are only known at execution time—for example via bind variables, nested-loop joins, or subqueries—Oracle can determine the partitions to read at runtime. The plan may display dynamic partition start/stop indicators depending on the operation.

Do not conclude dynamic pruning is absent solely because EXPLAIN PLAN does not show a fixed partition number. Inspect the actual cursor plan and predicates.

### 7.3 Inspecting PSTART and PSTOP

Example:

~~~sql
EXPLAIN PLAN FOR
SELECT SUM(amount)
FROM sales_by_month
WHERE sale_date >= DATE '2026-03-01'
  AND sale_date <  DATE '2026-04-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

In a partitioned plan, pay attention to:

- PSTART: starting partition accessed.
- PSTOP: ending partition accessed.
- A specific number or narrow range generally indicates pruning.
- KEY/KEY(I) or other dynamic symbols indicate partitions are determined at runtime.

Symbol meanings depend on the operation and version; read alongside Predicate Information and the actual plan.

### 7.4 Predicates must be compatible with the partition key

Partitioned by SALE_DATE:

~~~sql
WHERE sale_date >= :from_date
  AND sale_date <  :to_date
~~~

is generally more favorable than:

~~~sql
WHERE TO_CHAR(sale_date, 'YYYY-MM') = '2026-03'
~~~

The second expression converts the column to a string, which can prevent simple pruning and depends on NLS/format settings. Pass binds with proper DATE/TIMESTAMP types and filter by value ranges.

### 7.5 Filtering only on non-partition-key columns

If a table is partitioned by SALE_DATE but the query only has:

~~~sql
WHERE customer_id = :customer_id
~~~

Oracle may have to read every time partition because it does not know which periods contain the customer. A local index on CUSTOMER_ID in each partition or a global index can help find the data, but date-based partition pruning cannot happen without a time condition.

This is why the partition key must reflect the primary workload, with indexes serving as complementary access paths.

## 8. Indexes on Partitioned Tables

Partitioning affects index organization. Oracle provides two main categories:

- **Local index:** each index partition is aligned with the corresponding table partition.
- **Global index:** the index spans multiple or all table partitions; it can be a nonpartitioned global index or a global partitioned index.

### 8.1 Local index

Example:

~~~sql
CREATE INDEX ix_sales_local_customer
ON sales_by_month(customer_id)
LOCAL;
~~~

Oracle creates one index partition for each table partition. Once a query prunes to a partition, Oracle only needs to examine the corresponding local index partition.

Advantages:

- Index structure aligns with table partitions.
- Easy partition-level maintenance across many lifecycle operations.
- Can reduce the index scope accessed after table partition pruning.

Considerations:

- If a query lacks the partition key, it may have to probe multiple local index partitions.
- A unique local index must include the necessary partition key columns to ensure proper uniqueness per partition.
- Maintenance operations still require checking index status and specific DDL options.

### 8.2 Global index

A global index can locate keys across multiple partitions without knowing the row's partition beforehand:

~~~sql
CREATE INDEX ix_sales_global_sale_id
ON sales_by_month(sale_id);
~~~

If SALE_ID is globally unique across the table without containing SALE_DATE, a global unique index can enforce uniqueness across all partitions.

Advantages:

- Supports queries on non-partition-key columns.
- Can enforce table-wide uniqueness even when the partition key is excluded from the unique key.

Trade-offs:

- Some DROP/TRUNCATE/SPLIT/MERGE partition operations can affect global indexes.
- Requires appropriate maintenance options or index rebuilds when needed.
- Global indexes can incur additional cost and availability impact during partition maintenance.

### 8.3 Unique constraints and the partition key

Suppose a table is partitioned by SALE_DATE:

~~~sql
PARTITION BY RANGE (sale_date)
~~~

And you want a unique key on SALE_ID alone:

~~~sql
UNIQUE (sale_id)
~~~

A local unique index cannot guarantee SALE_ID uniqueness across all partitions if SALE_DATE is not part of the unique key. Two rows in two different partitions could share the same SALE_ID.

Design options:

1. Include the partition key in the unique key if business semantics permit, such as UNIQUE(SALE_DATE, SALE_ID).
2. Use a global unique index to enforce table-wide uniqueness of SALE_ID.
3. Design an appropriate registry/sequence key table if another global identification mechanism is required.

Do not alter a unique key solely to satisfy local index rules if doing so weakens data integrity rules.

### 8.4 Partition maintenance and global indexes

When dropping or truncating a partition, check whether global indexes become UNUSABLE and whether indexes should be maintained within the same DDL. Some versions support options such as `UPDATE INDEXES`; exact syntax and behavior depend on the operation, version, and index type.

Illustrative operation example:

~~~sql
ALTER TABLE sales_by_month
DROP PARTITION p2026_01
UPDATE INDEXES;
~~~

Consult documentation for your target Oracle version before running in production. After maintenance, confirm index status:

~~~sql
SELECT index_name,
       status,
       partitioned
FROM user_indexes
WHERE table_name = 'SALES_BY_MONTH';
~~~

For local index partitions, inspect the status of each index partition:

~~~sql
SELECT index_name,
       partition_name,
       status
FROM user_ind_partitions
WHERE index_name LIKE 'IX_SALES%';
~~~

## 9. Partition Keys and Constraints

The partition key affects how Oracle enforces PRIMARY KEY and UNIQUE constraints.

### 9.1 Primary key without the partition key

If the primary key does not include the partition key, the database still must enforce uniqueness across the entire table. A local unique index cannot guarantee that by checking each partition independently. Oracle may require a global index or a different key design.

### 9.2 Primary key containing the partition key

If business rules allow a composite key:

~~~sql
PRIMARY KEY (sale_date, sale_id)
~~~

and the table is partitioned by SALE_DATE, a local unique index can be an appropriate choice because the key includes the partition key.

However, this changes key semantics: the same SALE_ID could appear on two different dates and still form distinct composite keys. Use this only when the true business identifier is the date-and-ID pair.

### 9.3 Foreign keys and partitioning

Partitioning does not disable foreign keys. However, partition maintenance operations like DROP/TRUNCATE PARTITION can interact with referential constraints and require appropriate options or procedures.

Before dropping a partition, determine:

- Does the partition contain data referenced by child rows?
- Does the child table need to be archived synchronously?
- Is reference partitioning in use?
- Does the DDL require CASCADE or ordered execution?
- Are constraints and indexes still VALID/USABLE afterward?

Do not drop a partition based solely on data age without checking referential relationships and retention policies.

## 10. Changing the Partition Key and Row Movement

If updating a partition key moves a row from one partition to another, Oracle needs to perform row movement.

Example on a table partitioned by SALE_DATE:

~~~sql
UPDATE sales_by_month
SET sale_date = DATE '2026-03-15'
WHERE sale_id = 1001;
~~~

If the row resides in the January partition and moves to the March partition, the operation can be rejected if row movement is not enabled.

You can enable it:

~~~sql
ALTER TABLE sales_by_month
ENABLE ROW MOVEMENT;
~~~

With row movement enabled, Oracle can relocate the row to the target partition when the partition key changes. The row's ROWID can change, so applications must not treat ROWID as a long-term business identifier.

### 10.1 Row movement is not free

Updating a partition key can trigger:

- Deleting the old entry and inserting a new entry in the target partition.
- Maintaining local/global indexes.
- Generating redo/undo.
- Trigger, foreign key, and concurrency impacts depending on the operation.

If transaction dates are frequently corrected across periods, date-based partitioning can increase update costs. You may need a staging/correction table or a historical adjustment workflow.

### 10.2 Avoid frequently changing partition keys

Good partition key columns are usually stable:

- Confirmed business date.
- Immutable tenant ID.
- Rarely changing region code.
- Data type assigned at creation that seldom changes.

Columns such as processing status, current assignee, or priority change frequently; weigh carefully before using them as partition keys.

## 11. Partition-Wise Joins and Partition Keys

Partition-wise join is a technique Oracle can use to join compatibly partitioned tables, processing matching partition pairs rather than shuffling entire datasets as one large unit.

Example of two tables both partitioned by SALE_DATE with matching boundaries:

~~~sql
CREATE TABLE sales_header (
    sale_id   NUMBER,
    sale_date DATE,
    customer_id NUMBER,
    amount NUMBER(14,2)
)
PARTITION BY RANGE (sale_date) (
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01')
);

CREATE TABLE sales_detail (
    sale_id   NUMBER,
    sale_date DATE,
    line_no   NUMBER,
    product_id NUMBER,
    quantity NUMBER
)
PARTITION BY RANGE (sale_date) (
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01')
);
~~~

Join with conditions on the corresponding keys:

~~~sql
SELECT h.sale_date,
       h.sale_id,
       SUM(d.quantity) AS total_quantity
FROM sales_header h
JOIN sales_detail d
  ON d.sale_id = h.sale_id
 AND d.sale_date = h.sale_date
GROUP BY h.sale_date, h.sale_id;
~~~

If partitioning and join keys are compatible, Oracle can process each corresponding pair of partitions (*partition-wise join*). Benefits can include reduced data exchange between parallel servers and bounded processing scope.

### 11.1 Partition-wise joins do not happen automatically just because both tables are partitioned

Compatible conditions are required for partition keys, partitioning types, partition boundaries or subpartitioning, and join predicates. If two tables are partitioned on unrelated keys, Oracle cannot arbitrarily pair partition 1 of table A with partition 1 of table B.

Read the execution plan to confirm a partition-wise join or corresponding parallel operations. Do not infer it from DDL alone.

### 11.2 Reference partitioning

In a parent-child model, Oracle supports reference partitioning based on a supported foreign key. A child table can be partitioned to mirror the parent table's partitions without duplicating an independent partition key column.

For example, orders and order details have a parent-child relationship; reference partitioning keeps detail rows co-located with their parent order's partition. This is a specialized design requiring verification of foreign key requirements, partitioning types, and version limits.

## 12. Partition Keys, NULL Data, and Out-of-Domain Values

NULL values and values outside declared lists/ranges must be handled explicitly.

### 12.1 RANGE partitions

RANGE partitions distribute values according to boundaries. NULL values follow Oracle's comparison rules and typically land in the lowest matching range partition; if no partition covers the value, INSERT can fail for lack of a target partition.

### 12.2 LIST partitions

LIST partitions can declare DEFAULT to accept values not belonging to any listed partition:

~~~sql
PARTITION p_other VALUES (DEFAULT)
~~~

If there is no DEFAULT and a value matches no partition, INSERT can fail with an error indicating no matching partition was found. DEFAULT helps accept new domains, but it can also mask typos or unapproved domain codes; monitor row counts in the DEFAULT partition.

### 12.3 HASH partitions

HASH partitions use a hash function to route key values. For NULL keys or specific values, Oracle still determines the partition using hash rules. HASH does not create ordered value regions readable by range like RANGE does.

### 12.4 Input data validation

If SALE_DATE is mandatory, declare NOT NULL. If REGION_CODE must belong to a valid domain list, use a foreign key or appropriate constraint. Partitioning does not replace data validation.

## 13. Skew, Hotspots, and Data Distribution

A design that looks balanced on paper can still become imbalanced in practice.

### 13.1 Time skew

Some periods have major sales campaigns, year-end peaks, or special events. That month's partition may be several times larger than other months.

Solutions to consider:

- Finer granularity for peak periods.
- Composite partitioning.
- Subpartitioning by customer or region.
- Appropriate storage allocation and parallel workload tuning.

There is no need to split every month more finely if only a few special periods have high volume; weigh operational overhead.

### 13.2 Customer skew

HASH(customer_id) distributes different customers, yet a single customer with huge data volume still concentrates in one hash partition. Measure row counts and size per customer:

~~~sql
SELECT customer_id,
       COUNT(*) AS row_count,
       SUM(DBMS_LOB.GETLENGTH(payload)) AS payload_bytes
FROM customer_events
GROUP BY customer_id
ORDER BY row_count DESC
FETCH FIRST 20 ROWS ONLY;
~~~

The example above assumes PAYLOAD is a CLOB and measures content length; for other data types, substitute the appropriate calculation. Aggregation queries can be resource-intensive on large tables, so run them in a controlled scope and schedule.

### 13.3 Domain skew

If the SOUTH region holds 80% of the data, LIST partitioning on REGION_CODE creates one huge partition and two small ones. Pruning still helps regional queries, but the large partition can cause uneven load.

You can combine time-based RANGE with regional LIST, or HASH subpartitions within domains, if the workload truly needs it. Also consider whether a region might change codes or split territories.

### 13.4 Write-driven hot partitions

Continuously increasing timestamp-based RANGE partitioning typically directs all new INSERTs into the current last partition. This is predictable behavior and usually aligns with lifecycle management, though at very high write rates you should watch contention on indexes, blocks, sequences, segments, and parallel inserts.

HASH subpartitions can help spread some write workloads within a period, though effectiveness depends on the subpartition key and write pattern. Hashing by customer still funnels one customer into one subpartition; choosing a different key may distribute writes better while reducing customer-query pruning.

## 14. Managing Partition Counts

Too few partitions can make each partition too large, diminishing pruning and maintenance benefits. Too many partitions increase metadata, index partitions, statistics, parse/maintenance time, and operational complexity.

Estimate:

- Current partition count.
- Partition count after 1, 3, 5, or 10 years.
- Subpartitions per partition.
- Corresponding index partitions.
- Frequency of partition creation, split, merge, exchange, and drop operations.
- Number of partitions queries typically open.

For example, daily partitioning over 10 years creates more than 3,600 partitions. If each partition also has 16 subpartitions, total subpartitions exceed 58,000. That may be justified for an exceptionally large workload, but metadata and operations must be carefully evaluated.

## 15. Statistics and the Optimizer on Partitioned Tables

The optimizer requires statistics at the table, partition, and index levels to estimate cardinality and cost. As data grows or new partitions are created, statistics must be gathered according to an appropriate strategy.

Key concepts:

- Global table statistics describe the entire table.
- Partition-level statistics describe each partition.
- Subpartition statistics describe the inner level if present.
- Local index statistics correspond to index partitions.
- Global index statistics describe global indexes.

If a new partition has a different distribution, stale global stats can cause optimizer misestimates. Monitor stats after partition maintenance and large loads.

### 15.1 Checking partition metadata

~~~sql
SELECT partition_name,
       partition_position,
       high_value,
       num_rows,
       blocks,
       last_analyzed
FROM user_tab_partitions
WHERE table_name = 'SALES_BY_MONTH'
ORDER BY partition_position;
~~~

HIGH_VALUE is stored as a metadata expression and may display as LONG in some views; not all tools can filter or format this column directly like a regular VARCHAR2. The query above illustrates basic metadata fields.

### 15.2 Gathering statistics

Illustrative example:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_BY_MONTH',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => TRUE,
        granularity      => 'AUTO'
    );
END;
/
~~~

DBMS_STATS offers many options and incremental statistics policies. Follow DBA policies, especially for large tables, new partitions, and global statistics. Do not run ad-hoc stats gathers in production just to test a plan.

## 16. Designing Partition Keys and Indexes for Typical Queries

Suppose the primary query is:

~~~sql
SELECT customer_id,
       SUM(amount)
FROM sales
WHERE sale_date >= :from_date
  AND sale_date <  :to_date
  AND customer_id = :customer_id
GROUP BY customer_id;
~~~

Designs to consider:

- RANGE/INTERVAL on SALE_DATE for period pruning.
- HASH subpartitioning on CUSTOMER_ID to distribute customers within each period.
- Local index on CUSTOMER_ID if queries and data demonstrate a benefit.
- Other local/global indexes for identifier keys per uniqueness requirements.

However, if the primary query is:

~~~sql
SELECT *
FROM sales
WHERE sale_id = :sale_id;
~~~

then time partitioning does not provide pruning if SALE_DATE is unknown. A global index on SALE_ID may be an option, or the application must also supply the partition key when querying.

### 16.1 Do not mechanically duplicate indexes on the partition key

If partitioned by RANGE(SALE_DATE), a local index on SALE_DATE alone may add little value when queries already prune and perform direct partition scans. An index can still help in certain queries, but verify the access pattern.

An index on (CUSTOMER_ID, SALE_DATE) can serve customer lookups inside partitions; a global index on SALE_ID can serve global lookups. Every index adds DML and storage overhead, so each must have a clear justification.

## 17. Partition Key Selection Process

~~~mermaid
flowchart TD
    A["Collect query and DML workload"] --> B["Identify common filter predicates"]
    B --> C{"Time-based queries and retention?"}
    C -->|Yes| D["Evaluate RANGE / INTERVAL by date"]
    C -->|No| E{"Equality by customer or tenant?"}
    E -->|Yes| F["Evaluate HASH or LIST by tenant scale"]
    E -->|No| G{"Finite and stable data domain?"}
    G -->|Yes| H["Evaluate LIST / RANGE by domain"]
    G -->|No| I["Consider no partitioning or alternative design"]
    D --> J["Measure distribution and skew"]
    F --> J
    H --> J
    I --> K["Check indexes, constraints, and maintenance"]
    J --> K
    K --> L["Benchmark with actual execution plan"]
    L --> M["Finalize design and operational procedures"]
~~~

Specific steps:

1. Collect real queries, frequencies, row counts, and runtimes.
2. Identify common filter, join, group by, and sort columns.
3. Determine retention/archiving/deletion requirements.
4. Measure row count distributions across candidate key values.
5. Choose RANGE, LIST, HASH, or composite based on workload.
6. Define local/global indexes and unique constraint requirements.
7. Check row movement and key mutations.
8. Design DDL maintenance, stats, backup, and recovery.
9. Benchmark on data with a distribution close to production.
10. Verify pruning and actual plans post-deployment.

## 18. Common Design Mistakes

| Wrong choice | Consequence | How to rethink |
|---|---|---|
| Partitioning on a column absent from predicates | Queries scan many partitions | Choose key from actual workload |
| LIST partitioning by customer for millions of tenants | Excessive partitions and metadata | Use HASH or an alternative model |
| HASH(customer_id) when one customer holds most data | One partition remains huge | Measure per-customer skew, consider a dedicated strategy |
| RANGE on sequentially increasing ID | INSERTs pile into the last partition | Evaluate write hotspots and workload |
| LIST on frequently changing STATUS | Increased row movement and maintenance | Choose a more stable key |
| Time partitioning when queries filter only by ID | No date pruning | Index/global access path or include partition key condition |
| Daily partitioning for small data | Partition count grows fast | Choose monthly/quarterly granularity if suitable |
| Creating too many subpartitions | Complex metadata and maintenance | Add a level only for measurable benefits |
| Using TRUNC(date_col) in predicates | Can hinder pruning | Use half-open date ranges |
| Forgetting global indexes when dropping partitions | Indexes may become unusable or require maintenance | Plan index maintenance |
| Unique key excluding partition key with only a local unique index | Cannot guarantee table-wide uniqueness | Use global unique index or design business-valid key |
| Enabling row movement without considering ROWID | Applications may cache stale ROWIDs | Use stable business keys |
| Treating partitions as security boundaries | Risk of cross-tenant access | Use authorization/row-level security |
| Assuming partitioning always speeds up queries | Can add overhead when pruning does not happen | Measure actual plans and workloads |

## 19. Self-Check Practice Exercises

The exercises use a test schema. Do not run destructive DDL on production tables.

### Exercise 1 — Monthly RANGE

Create a table partitioned by SALE_DATE with three monthly partitions. Insert rows in each month and query one month using a half-open range. Inspect PSTART/PSTOP in DBMS_XPLAN.

### Exercise 2 — INTERVAL partitioning

Create a monthly INTERVAL table with a transition point. Insert a row in a future period. Query USER_TAB_PARTITIONS to confirm the partition was created.

### Exercise 3 — HASH by customer

Create a HASH-partitioned table with 16 or 32 partitions by CUSTOMER_ID. Insert data for multiple customers. Run an equality query for one customer and check partition pruning.

### Exercise 4 — Measuring skew

Create one customer with far more rows than others. Count rows per customer and explain why HASH(customer_id) still produces one large partition.

### Exercise 5 — LIST by region

Create LIST partitions for NORTH, CENTRAL, SOUTH, and DEFAULT. Insert known and new region codes. Inspect which partitions receive the data, then propose a process to govern DEFAULT.

### Exercise 6 — RANGE-HASH

Create a table partitioned by month and HASH-subpartitioned by customer. Compare a date-only query against a query filtering both date and customer. Inspect partition/subpartition pruning.

### Exercise 7 — Row movement

Create a RANGE table by date. Insert a row in January and try updating SALE_DATE to February while row movement is off. Enable row movement in the test schema, rerun, and observe the result.

### Exercise 8 — Local and global indexes

Create a local index on CUSTOMER_ID and a global index on SALE_ID. Compare a customer query with a date condition against a sale ID query without a date. Record access paths.

### Exercise 9 — Unique constraints

Create a date-partitioned table and try a unique key on SALE_ID alone. Investigate why a local unique index requires the partition key, then compare with a global unique index.

### Exercise 10 — Retention

In the test table, archive a partition's data and then DROP or TRUNCATE the partition. Inspect index status, constraints, and remaining data. Note explicitly that DDL performs an implicit commit and cannot be rolled back like DML.

### Exercise 11 — Partition-wise join

Create two tables both RANGE-partitioned by date with identical boundaries. Join on the appropriate keys. Inspect the plan and determine whether Oracle uses a partition-wise join.

### Exercise 12 — Comparing against a non-partitioned table

Load identical data into a regular table and a partitioned table. Run a narrow date-filtered query and an unfiltered-date query. Compare plans, partition pruning, buffers, reads, and elapsed time. Do not compare EXPLAIN PLAN cost alone.

## 20. Pre-Deployment Partition Key Checklist

**Workload**

- Do critical queries have predicates on the partition key?
- What are query frequencies by time, customer, and data domain?
- Are there join keys that need aligned partitions?
- Are there queries that must locate data without knowing the partition key?

**Data distribution**

- Expected row count and storage size per partition?
- Largest partition compared to the average?
- Does a single customer/region account for most of the data?
- Do INSERTs concentrate into one partition or subpartition?

**Lifecycle**

- How long is data retained?
- Is data archived before dropping?
- How is late-arriving data handled?
- Who creates new partitions and monitors future partitions?

**Indexes and constraints**

- Which indexes are local and which are global?
- Does the unique key include the partition key?
- How does partition maintenance affect global indexes?
- Are there foreign keys or child tables that must be handled together?

**Applications**

- Is the partition key ever updated?
- Is ENABLE ROW MOVEMENT required?
- Do applications persist ROWIDs long-term?
- What mechanism protects tenant security beyond partitioning?

**Verification**

- Does the actual plan show partition pruning?
- Do PSTART/PSTOP match expectations?
- Is there a large discrepancy between E-Rows and A-Rows?
- Have queries both on and off the partition key been benchmarked?
- Have DML throughput and partition maintenance been tested?

## 21. Key Takeaways

| Key direction | When suitable | What to verify |
|---|---|---|
| Time | Period-based queries, continuously growing data, time-based retention | Granularity, late data, intervals, time zones, final partition |
| Customer/tenant | Equality queries by tenant, distributing many customers | HASH distributes customers but does not split one large customer |
| Data domain | Finite, stable domain values, domain-based queries/maintenance | Skew, new values, DEFAULT, and row movement |
| RANGE-HASH | Time pruning and customer distribution | Subpartition count, customer skew, partition-wise access |
| RANGE-LIST | Periodic retention and domain-based operations | Domain count, DEFAULT, subpartition count |

A good partition key allows Oracle to skip irrelevant data, helps operations teams manage data lifecycles, and maintains balanced resource usage. Choose keys from real queries and workflows, measure skew before deciding, and design indexes/constraints alongside partitioning. Time-based RANGE, customer-based HASH, and domain-based LIST are common patterns, but only execution plans, runtime metrics, and testing on representative data confirm whether a design truly fits.
