# Choosing a Partition Key by Time or Data Domain

Partitioning splits a logical table into multiple partitions managed within the same MySQL table. When the right partition key is chosen, MySQL can skip partitions irrelevant to a query (partition pruning), while DBAs can manage data by time intervals or value domains. However, partitioning does not automatically make all queries faster, does not replace indexes, and does not distribute data across multiple servers.

For the DATABASE_MYSQL module, choosing a partition key must stem from how the application filters data, data lifecycle requirements, and key constraints. This lesson compares time-based partitioning with domain-based partitioning, guides choosing among RANGE, LIST, HASH, or KEY, and highlights important MySQL limitations to account for before designing a schema.

## 1. What Does the Partition Key Determine?

The partition key is the column or expression MySQL uses to determine which partition a row belongs to. For example:

- created_at can place orders into monthly partitions.
- region_code can place data into regional partitions.
- tenant_id can be hashed to distribute tenants across a fixed number of partitions.

The partition key directly affects:

1. MySQL's ability to eliminate partitions that do not need to be read.
2. The number of rows a query must search inside the remaining partitions.
3. How old data is retained, archived, or deleted.
4. Which PRIMARY KEY and UNIQUE constraints the table can declare.
5. The ability to use foreign keys and other schema features.
6. Maintenance overhead when adding, merging, splitting, or dropping partitions.

A good partition key typically appears in common filter predicates and has a value domain and lifecycle aligned with data management strategies. Choosing a key merely because a column has many distinct values or to split a table into roughly equal parts is not enough.

## 2. Partitioning Is Not Sharding and Does Not Replace Indexes

Partitioning is horizontal division of a table within a single MySQL instance. Partitions belong to the same logical table, share one table name, and are queried with standard SQL.

Sharding distributes data across multiple servers or database instances, typically requiring a routing layer and distributed management. Partitioning does not increase CPU, RAM, or write throughput by moving data onto other machines.

Partitioning also does not replace indexes:

- Partition pruning eliminates irrelevant partitions based on partition key conditions.
- Indexes locate rows inside the selected partitions.
- A query can prune down to a single partition and still need a full scan if that partition lacks a suitable index.
- A query with a good index but no partition key condition may still have to search across many partitions.

In MySQL, indexes on a partitioned table are organized per partition; there is no global index covering all partitions as a single unified structure. Queries that do not filter on the partition key may have to access indexes across multiple partitions. Therefore, both the partition key and indexes must be designed around the actual workload.

## 3. Start from Query Patterns and Data Lifecycle

Before choosing a key, gather the most frequent queries:

| Question | Implication for the partition key |
|---|---|
| Does the application usually filter by creation date, transaction date, or expiration date? | Consider a time column |
| Do users usually query by tenant, region, data type, or customer ID? | Consider a domain column |
| Do queries always supply the partition key? | Determines pruning effectiveness |
| Is old data purged monthly, quarterly, or yearly? | Time-based RANGE may be advantageous |
| Is there a need to keep each data domain operationally independent? | Consider LIST or KEY |
| Do queries need to enforce UNIQUE on a column that does not contain the partition key? | May conflict with MySQL's unique key rules |
| Are foreign keys needed to or from this table? | Strongly impacts the feasibility of InnoDB partitioning |

Do not start with the question "how many partitions should we split into?". First determine which queries need pruning, how long data is retained, and which schema constraints cannot be relaxed.

## 4. Time-Based Partitioning: A Common Choice for Lifecycle Data

Time-based partitioning fits tables whose data grows continuously and is queried by time intervals, such as:

- Orders by created_at.
- System events by event_time.
- Financial transactions by transaction_date.
- Application logs by logged_at.

If data must be kept for 13 months, a DBA can create monthly partitions and drop old partitions once the retention period expires. Dropping a partition can be much faster than deleting millions of rows with DELETE, though it is a destructive DDL operation requiring clear backup and retention procedures.

### Monthly RANGE COLUMNS Example

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    created_at DATETIME NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_id, created_at),
    KEY idx_orders_customer_created (customer_id, created_at),
    KEY idx_orders_status_created (status, created_at)
) ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p_before_2026 VALUES LESS THAN ('2026-01-01 00:00:00'),
    PARTITION p2026_01 VALUES LESS THAN ('2026-02-01 00:00:00'),
    PARTITION p2026_02 VALUES LESS THAN ('2026-03-01 00:00:00'),
    PARTITION p2026_03 VALUES LESS THAN ('2026-04-01 00:00:00'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
~~~

RANGE COLUMNS(created_at) divides rows by DATETIME values. Partition p_before_2026 receives values prior to the start of 2026; p2026_01 receives values from the start of the year up to before the start of February; subsequent boundaries cover contiguous non-overlapping intervals. p_future catches all values from the start of April onward.

Filter predicates should be written as half-open intervals:

~~~sql
SELECT order_id, customer_id, created_at, total_amount
FROM orders
WHERE created_at >= '2026-02-01 00:00:00'
  AND created_at <  '2026-03-01 00:00:00';
~~~

MySQL can determine that only partition p2026_02 is relevant to the query. Half-open intervals avoid guessing the last timestamp of a day or month and work reliably for DATETIME with or without microseconds.

### Which Time Column Should You Choose?

Not every time column is suitable:

- created_at: suitable if queries and retention are based on record creation time.
- event_time: suitable for event data when event occurrence time is the primary query criterion.
- business_date: suitable when business operations partition periods by accounting date or transaction date.
- updated_at: changes frequently; if used as a partition key, UPDATE statements may have to move rows across partitions and complicate management.

Choose a column whose meaning is stable with respect to the record's lifecycle. If data arrives late or is backfilled, clarify whether its partition is determined by event time or ingestion time.

## 5. Choosing Partition Granularity: Day, Month, or Year?

Granularity determines how long a time span each partition holds.

| Granularity | Suitable when | Trade-offs |
|---|---|---|
| Daily | Daily data volume is large; retention or processing is daily | Many partitions and pre-creation work |
| Monthly | Reporting workloads and retention are monthly; medium/large data volume | Deleting daily slices requires in-partition handling |
| Quarterly | Slow data growth; quarterly business cycles | Monthly queries still read the whole quarter's partition |
| Yearly | Low data volume or yearly lifecycle | Large partitions; harder to maintain and remove small portions |

There is no single right granularity for every table. Balance per-partition size, total partition count, query frequency, and operational practices. Too many partitions increase metadata and planning overhead; too few partitions may limit pruning or retention flexibility.

For fast-growing tables, estimate row counts and storage size per period before choosing granularity. Also make sure to create future partitions before data reaches new boundaries.

## 6. Using RANGE for Numeric or Time Domains

RANGE works well when the value domain has a natural ordering and can be divided into non-overlapping intervals:

- Auto-incrementing or sequential IDs.
- Days/months/years.
- Monetary amounts or score bands.
- Temperature or measurement intervals.

Example splitting customer activity by numeric ID ranges:

~~~sql
CREATE TABLE customer_activity (
    customer_id BIGINT UNSIGNED NOT NULL,
    activity_id BIGINT UNSIGNED NOT NULL,
    activity_time DATETIME NOT NULL,
    PRIMARY KEY (customer_id, activity_id)
) ENGINE=InnoDB
PARTITION BY RANGE (customer_id) (
    PARTITION p_low VALUES LESS THAN (1000000),
    PARTITION p_mid VALUES LESS THAN (5000000),
    PARTITION p_high VALUES LESS THAN (10000000),
    PARTITION p_max VALUES LESS THAN (MAXVALUE)
);
~~~

Queries filtering customer_id within a range can prune to the corresponding partitions. However, if queries typically filter by activity_time without customer_id, partitioning by customer_id will not help prune those queries.

For DATE/DATETIME types, RANGE COLUMNS is usually clearer than wrapping the column in a numeric function. For numeric types, either RANGE(column) or RANGE COLUMNS(column) can be used depending on requirements and data types.

## 7. Using LIST When the Domain Has a Small, Stable Set of Values

LIST is appropriate when partition key values belong to a known set of discrete values, such as sales regions or data categories:

~~~sql
CREATE TABLE regional_sales (
    region_code VARCHAR(20) NOT NULL,
    sale_id BIGINT UNSIGNED NOT NULL,
    sale_date DATE NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (region_code, sale_id)
) ENGINE=InnoDB
PARTITION BY LIST COLUMNS (region_code) (
    PARTITION p_north VALUES IN ('NORTH', 'NORTHEAST'),
    PARTITION p_central VALUES IN ('CENTRAL'),
    PARTITION p_south VALUES IN ('SOUTH', 'SOUTHWEST')
);
~~~

When a query filters region_code = 'NORTH', MySQL can read only partition p_north. LIST COLUMNS allows using column values directly, including strings.

LIST suits finite, well-governed value sets. If the system frequently adds new regions or tenants, each addition may require DDL to extend partitions. Rows with unlisted values cannot be inserted into the table unless a matching partition exists.

Do not create one partition per customer if customer count can grow to tens of thousands or millions. In that case, consider KEY/HASH with a fixed partition count or a different model.

## 8. Using HASH or KEY for Even Distribution Across a Domain

If there are no natural ranges or fixed category lists, HASH or KEY can distribute rows across a fixed number of partitions.

### HASH

~~~sql
CREATE TABLE tenant_events (
    tenant_id BIGINT UNSIGNED NOT NULL,
    event_id BIGINT UNSIGNED NOT NULL,
    event_time DATETIME NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (tenant_id, event_id)
) ENGINE=InnoDB
PARTITION BY HASH (tenant_id)
PARTITIONS 16;
~~~

MySQL evaluates the hash expression to select a partition. HASH typically uses an integer expression. With 16 partitions, data is distributed according to hash output, which does not mean every partition always contains exactly 1/16 of the rows.

### KEY

~~~sql
CREATE TABLE tenant_events_by_key (
    tenant_id VARCHAR(64) NOT NULL,
    event_id BIGINT UNSIGNED NOT NULL,
    event_time DATETIME NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (tenant_id, event_id)
) ENGINE=InnoDB
PARTITION BY KEY (tenant_id)
PARTITIONS 16;
~~~

KEY uses MySQL's internal hash function over the specified columns and supports more data types than HASH. There is no need to write a custom hashing expression.

HASH/KEY can spread data across partitions, but usually do not help with time-based retention. If old data must be purged monthly, time-based partitioning is generally better suited. When querying by tenant_id, HASH/KEY can prune by tenant if the optimizer resolves the target partition.

## 9. Comparing RANGE, LIST, HASH, and KEY

| Partitioning type | When to consider | Example partition keys | Constraints to consider |
|---|---|---|---|
| RANGE / RANGE COLUMNS | Ordered data with clear value intervals | created_at, transaction_date, numeric ID | Boundaries must be managed; values past the last partition fail without MAXVALUE |
| LIST / LIST COLUMNS | Small, finite, stable value domain | region_code, event_type | New values must be mapped or new partitions added |
| HASH | Distribution by integer expression | tenant_id, customer_id | Hard to purge data by time; perfectly even distribution is not guaranteed |
| KEY | Distribution by internal hash on one or more columns | String tenant_id or composite key | Less control over hashing logic; does not replace sharding |

Choose the partitioning type according to the problem to solve. If monthly retention is the primary goal, HASH is not equivalent to RANGE. If splitting by a handful of fixed regions, LIST expresses intent more clearly than HASH.

## 10. Partition Pruning: The Key Condition for Partitioning to Help

Partition pruning is MySQL's ability to eliminate partitions that cannot contain rows satisfying query conditions. It reduces the number of partitions accessed, though it does not guarantee that the number of rows read inside a partition is small.

Example with an orders table partitioned by created_at:

~~~sql
-- Direct condition on the partition key: favorable for pruning
SELECT order_id, total_amount
FROM orders
WHERE created_at >= '2026-02-01'
  AND created_at < '2026-03-01';

-- No partition key condition: may have to inspect many partitions
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 42;
~~~

The second query can still use an index on customer_id inside each partition, yet lacks a time predicate to eliminate other partitions. Depending on version and plan, MySQL may have to probe indexes across many partitions.

Keep predicates directly derivable from the partition key. For instance, instead of:

~~~sql
WHERE YEAR(created_at) = 2026
~~~

use a range:

~~~sql
WHERE created_at >= '2026-01-01'
  AND created_at < '2027-01-01'
~~~

Wrapping the column in a function can make pruning harder or prevent it from working as expected. Writing direct ranges is clearer and generally favors both partition pruning and index range access.

## 11. Verifying Which Partitions Are Used

Use EXPLAIN to check selected partitions:

~~~sql
EXPLAIN
SELECT order_id, customer_id, created_at
FROM orders
WHERE created_at >= '2026-02-01'
  AND created_at < '2026-03-01';
~~~

In tabular EXPLAIN output, the partitions column lists the partitions considered by the optimizer for the query. If the condition covers only one month yet multiple partitions still appear, inspect data types, the partitioning expression, and predicate syntax.

Partition structure can be inspected in metadata:

~~~sql
SELECT
    PARTITION_NAME,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    PARTITION_DESCRIPTION,
    TABLE_ROWS
FROM INFORMATION_SCHEMA.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY PARTITION_ORDINAL_POSITION;
~~~

InnoDB TABLE_ROWS is an estimate, not an exact count. Use COUNT(*) with appropriate filters if exact figures are required, keeping cost in mind on large tables.

## 12. Critical Rule: Every Unique Key Must Include the Partition Key

MySQL requires every column used in the partitioning expression to appear in every unique key on the table, including the PRIMARY KEY. This means the partition key affects how table-wide uniqueness can be enforced.

For example, an orders table partitioned by created_at cannot use:

~~~sql
-- Invalid if the table is partitioned by created_at
PRIMARY KEY (order_id)
~~~

Instead, the example uses:

~~~sql
PRIMARY KEY (order_id, created_at)
~~~

However, this composite key only guarantees uniqueness of the (order_id, created_at) pair; it does not enforce uniqueness of order_id alone across the whole table. If business rules require globally unique order_id values, another mechanism must be designed—such as an unpartitioned registry table with UNIQUE(order_id), or globally unique ID generation from the application or an ID service. A registry table must be updated in the same transaction to avoid data drift.

Check this rule before adopting partitioning. If the existing schema has multiple unique keys that do not include the partition key, partitioning may force redesigning keys and how other tables reference the data.

## 13. Foreign Keys and Schema Limitations of InnoDB Partitioning

In MySQL, InnoDB tables with user-defined partitioning cannot contain foreign keys and cannot be referenced by foreign keys from other tables. This is an architectural constraint that must be evaluated early.

If the current orders table has:

- PRIMARY KEY(order_id)
- FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
- UNIQUE(order_ref)

then partitioning by created_at is not just adding a PARTITION BY clause. You must resolve:

1. Whether the PRIMARY KEY and every unique key can include created_at.
2. Whether the application can tolerate losing database-level foreign key constraints.
3. Which application layer, transaction, or data model will take over referential integrity checks.
4. Whether JOIN queries and delete/update operations preserve consistency.

If foreign keys are a strict requirement, an InnoDB partitioned table may not be appropriate. Do not drop foreign keys solely to gain partition pruning if data integrity risks outweigh the benefits.

## 14. Time-Based Partition Maintenance

One operational advantage of RANGE partitioning is adding new ranges or removing old data ranges using partition DDL operations.

### Splitting the Future Partition to Create a New Month

For an orders table with p_future = MAXVALUE, before entering April 2026 you can split the future partition:

~~~sql
ALTER TABLE orders
REORGANIZE PARTITION p_future INTO (
    PARTITION p2026_04 VALUES LESS THAN ('2026-05-01 00:00:00'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
~~~

Rows already in p_future are redistributed into the new partition or p_future according to their created_at value. This operation can take significant time and resources depending on how much data must be moved; test in a production-like environment and plan capacity.

### Dropping an Old Partition

~~~sql
ALTER TABLE orders DROP PARTITION p2026_01;
~~~

DROP PARTITION removes all data residing in that partition. It is a destructive operation, not equivalent to a DELETE that can be rolled back via ROLLBACK inside a transaction. Verify retention rules, backups, audit requirements, and replication state before running it.

Partition DDL is DDL; do not rely on application transactions to roll back these operations. Check your MySQL version documentation, atomic DDL behavior, and replication/backup impact before modifying partitions on large tables.

## 15. Domain-Based Partitioning: Common Scenarios

### By Region

LIST COLUMNS(region_code) fits when the number of regions is small and changes infrequently. Regional queries can prune partitions. If nationwide reporting is required, queries still need to read partitions across all regions.

### By Tenant

If there are millions of tenants, do not create one partition per tenant. KEY/HASH(tenant_id) with a fixed partition count can be used, but only helps if queries consistently pass tenant_id and distribution is reasonably balanced. Remember that this still lives inside one MySQL instance and does not provide tenant isolation like sharding.

### By Event Type

LIST(event_type) fits when the set of event types is small and stable. If new event types appear regularly, a process for adding partitions or mappings must be maintained; otherwise inserts can fail.

### By Increasing ID

RANGE(id) can fit when querying by ID ranges and managing old data by range. However, if queries primarily filter by time, partitioning by ID may not help with date-based pruning.

## 16. Criteria Not to Overlook When Choosing a Partition Key

Evaluate each candidate against these criteria:

| Criterion | Question to answer |
|---|---|
| Query alignment | Do common WHERE conditions filter on the partition key? |
| Pruning | Can MySQL determine which partitions to read from literals or parameters? |
| Retention | Can data be dropped or archived by partition without affecting data that must be kept? |
| Cardinality | Do the value count and distribution fit RANGE/LIST/HASH/KEY? |
| Skew | Is there a risk of one partition growing much larger than others? |
| Unique constraints | Can every PRIMARY KEY/UNIQUE key include the partition key? |
| Foreign keys | Does the table need to declare or be referenced by foreign keys? |
| Joins | Do related tables share compatible access patterns, or will queries scan many partitions? |
| Maintenance | Who creates new partitions, when, and how are out-of-range values handled? |
| Operations | Do backup, restore, replication, monitoring, and migration workflows support the new process? |

Never choose a partition key solely on cardinality. A column with millions of distinct values that never appears in filter predicates and has no relation to retention may yield no benefit.

## 17. Common Misconceptions

| Misconception | Reality |
|---|---|
| Splitting into many partitions makes every query faster | Only queries that prune partitions reduce read scope; others may access many partitions |
| Partitioning automatically distributes load across multiple servers | MySQL partitioning lives within one instance; sharding is a separate problem |
| Having partitions removes the need for indexes | Indexes are still needed to locate rows inside partitions |
| HASH always distributes data evenly | Distribution depends on input values and hash function; equal row counts per partition are not guaranteed |
| You can keep UNIQUE(order_id) when partitioning by created_at | MySQL requires the partition key to be included in every unique key |
| InnoDB partitioned tables still use foreign keys normally | User-defined InnoDB partitioned tables do not support foreign keys in either direction |
| DROP PARTITION is just like DELETE | DROP PARTITION removes all partition data via DDL and cannot be rolled back like a DML transaction |
| You should create one partition per tenant | Large tenant counts complicate metadata and operations; consider KEY/HASH or sharding |

## 18. Process for Designing and Validating a Partition Key

1. Gather representative queries, WHERE clauses, JOINs, ORDER BYs, and retention requirements.
2. List candidate columns: time, ID, tenant, region, or data type.
3. Select RANGE/LIST/HASH/KEY based on value domain and lifecycle.
4. Verify that every PRIMARY KEY/UNIQUE key can include the partition key.
5. Check foreign key limitations and required schema features.
6. Estimate rows/storage per partition and total partition count over multiple years.
7. Design in-partition indexes based on actual queries.
8. Create representative test data, including skewed data and boundary values.
9. Use EXPLAIN to check whether the partitions column eliminates unnecessary partitions.
10. Use EXPLAIN ANALYZE in an appropriate environment to measure actual rows and execution time.
11. Test adding, reorganizing, and dropping partitions on a copy of the data.
12. Build jobs to pre-create future partitions, alert on missing partitions, and define recovery procedures.

## 19. Practice Exercises

1. Create an orders table partitioned by RANGE COLUMNS(created_at) with a pre-2026 partition, three monthly partitions, and a future partition.
2. Load data spanning different months; run EXPLAIN for a single-month query and inspect the partitions list.
3. Run a query filtering only on customer_id without created_at; observe why monthly partitioning does not prune partitions.
4. Try writing YEAR(created_at) = ... and then rewrite it as a half-open range; compare the plans.
5. Create a regional_sales table with LIST COLUMNS(region_code); try inserting an undeclared region and observe the result.
6. Create a tenant_events table with KEY(tenant_id) PARTITIONS 16; test queries with tenant_id and queries without tenant_id.
7. Try declaring PRIMARY KEY(order_id) on a table partitioned by created_at; explain why it is invalid, then change it to a composite key.
8. Try designing a foreign key for an InnoDB partitioned table; note the limitation and evaluate alternative data modeling options.
9. Use REORGANIZE PARTITION to split p_future into a new monthly partition on test data.
10. Use DROP PARTITION on a copy of the data; compare row counts before and after, and describe the required backup/approval steps.

You have completed this lesson when you can select a partition key based on queries and data lifecycle, explain the trade-offs between time-based and domain-based partitioning, verify pruning with EXPLAIN, and identify unique key and foreign key constraints prior to deployment. Partitioning should only be applied when access or operational benefits have been measured and outweigh schema change costs.
