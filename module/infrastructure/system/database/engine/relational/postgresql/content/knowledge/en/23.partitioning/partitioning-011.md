# Distinguishing Partitioning, Table Inheritance, and Sharding

In PostgreSQL, **partitioning**, **table inheritance**, and **sharding** can all place data across multiple tables or multiple storage units. However, the three mechanisms differ fundamentally in **management boundaries, data routing, consistency guarantees, SQL optimization capabilities, and operational cost**.

- **Declarative partitioning** splits one logical table into multiple partitions inside **a single PostgreSQL database/cluster**, using `RANGE`, `LIST`, or `HASH`.
- **Table inheritance** lets child tables inherit columns and certain constraints from a parent table. It does not automatically act as a date- or tenant-based data router.
- **Sharding** distributes data across **multiple PostgreSQL servers/clusters** coordinated by a router, coordinator, or distributed database layer.

Creating 1,000 partitions on a single PostgreSQL primary **does not mean 1,000 machines are handling writes concurrently**. Conversely, multiple machines storing different slices of data do not automatically form a declarative partitioned table with single-node transactions and a global unique index.

This lesson belongs to the **Partitioning** chapter of the *Database Engine Relational PostgreSQL* module. Its goal is to understand each model's mechanics, practice with SQL, and choose an architecture based on queries, write load, retention, and business constraints.

## 1. Diagram of the Three Models

~~~text
A. DECLARATIVE PARTITIONING — SINGLE CLUSTER

Application
    |
    v
PostgreSQL primary
    |
    orders [PARTITION BY RANGE(order_date)]
       +-- orders_2026_01
       +-- orders_2026_02
       +-- orders_2026_03
       +-- orders_default


B. TABLE INHERITANCE — PARENT/CHILD IN ONE CLUSTER

PostgreSQL
    |
    events_parent [ordinary table, can hold rows]
       +-- events_child_a INHERITS(parent)
       +-- events_child_b INHERITS(parent)

INSERT into parent does not auto-route to children by CHECK.


C. SHARDING — MULTIPLE CLUSTERS

Application / Router
    |
    +---- PostgreSQL A: tenant group 1
    +---- PostgreSQL B: tenant group 2
    +---- PostgreSQL C: tenant group 3

Router picks the server; some queries hit multiple servers.
~~~

### 1.1. Identifying Question

A design is partitioning if PostgreSQL automatically chooses the partition table based on **partition bounds**. It is table inheritance if an `INHERITS` relationship uses parent/child semantics without built-in routing. It is sharding if **subsets of data live on independent servers/clusters** with a mechanism deciding which server to access.

## 2. Comparison Table

| Criterion | Declarative Partitioning | Table Inheritance | Sharding |
|---|---|---|---|
| Primary layer | Tables within one cluster | Parent/child relation | Multiple clusters |
| Declaration | `PARTITION BY`, `PARTITION OF` | `INHERITS` | Router/extension/distributed system |
| Distribution rule | Partition key and bounds | No built-in router | Shard key and shard map |
| INSERT via parent | Auto-routing | Writes parent unless manually routed | Routes to target shard |
| SELECT via parent | Reads matching partitions | Usually includes descendants | Queries one or more shards |
| Skipping irrelevant slices | Partition pruning | Constraint exclusion when eligible | Shard routing |
| Multi-slice transactions | Single PostgreSQL transaction | Single PostgreSQL transaction | Depends on distributed guarantees |
| Global uniqueness | Restricted by partition key | Does not auto-span children | Not global by default |
| Scales writable primaries | No | No | Yes (potentially) |
| Automatic HA | No | No | No; each shard still needs HA |
| Primary overhead | Partition count, indexes, DDL | Manual triggers, constraints, indexes | Rebalancing, cross-shard JOINs, consistency |

## 3. Distinguishing Cluster, Database, and Shard

A **PostgreSQL database cluster** in traditional server terminology is the set of databases managed by one server instance and data directory. It does not mean PostgreSQL automatically distributes write load across multiple machines.

Inside a cluster sit databases, schemas, tables, indexes, and partitions. A partitioned table normally lives in **one database**; leaf partitions can be placed on different tablespaces, yet transactions and WAL are still managed by that single cluster.

~~~text
Primary server
  Database shop
    Schema sales
      orders (partitioned parent)
      orders_2026_01 (leaf)
      orders_2026_02 (leaf)
~~~

**Different tablespaces do not mean different shards.** Placing data across two volumes or storage paths still gives you only one writable primary.

## 4. How Does Declarative Partitioning Work?

PostgreSQL uses a partition key and declared bounds to manage the child tables holding rows.

~~~sql
CREATE TABLE audit_events (
    event_id BIGINT NOT NULL,
    occurred_on DATE NOT NULL,
    action TEXT NOT NULL
) PARTITION BY RANGE(occurred_on);

CREATE TABLE audit_events_2026_01
PARTITION OF audit_events
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE audit_events_2026_02
PARTITION OF audit_events
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
~~~

Inserting via the parent:

~~~sql
INSERT INTO audit_events(event_id, occurred_on, action)
VALUES (1, DATE '2026-02-10', 'login');
~~~

PostgreSQL routes the row to the February child. The partitioned parent table holds only logical metadata/definition; rows reside in leaf partitions.

**If no partition matches and there is no DEFAULT partition, INSERT fails.** PostgreSQL does not auto-create next month's partition on the fly.

## 5. RANGE, LIST, and HASH

### 5.1. RANGE: Partitioning by Contiguous Ranges

~~~sql
CREATE TABLE metrics (
    id BIGINT,
    measured_on DATE NOT NULL
) PARTITION BY RANGE(measured_on);

CREATE TABLE metrics_jan
PARTITION OF metrics
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
~~~

Inclusive lower bound, exclusive upper bound:

~~~text
2026-01-01 <= measured_on < 2026-02-01
~~~

RANGE suits daily, monthly, quarterly time-series, or bounded numeric intervals.

### 5.2. LIST: Explicit Discrete Values

~~~sql
CREATE TABLE regional_jobs (
    id BIGINT,
    region TEXT NOT NULL
) PARTITION BY LIST(region);

CREATE TABLE regional_jobs_north
PARTITION OF regional_jobs
FOR VALUES IN ('north', 'northeast');

CREATE TABLE regional_jobs_south
PARTITION OF regional_jobs
FOR VALUES IN ('south', 'southeast');
~~~

LIST fits a small, stable set of categories; rapidly growing value sets increase partition management overhead.

### 5.3. HASH: Grouping via Hash Modulus

~~~sql
CREATE TABLE tenant_messages (
    message_id BIGINT,
    tenant_id INTEGER NOT NULL,
    body TEXT
) PARTITION BY HASH(tenant_id);

CREATE TABLE tenant_messages_p0
PARTITION OF tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE tenant_messages_p1
PARTITION OF tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE tenant_messages_p2
PARTITION OF tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE tenant_messages_p3
PARTITION OF tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
~~~

**Do not compute `tenant_id % 4` in application code assuming it matches PostgreSQL's HASH partition placement.** PostgreSQL applies its internal hash function rather than raw integer modulo.

### 5.4. Choosing Based on Goal

| Workload | Direction to Evaluate |
|---|---|
| 18-month retention, drop old months | Monthly RANGE |
| A few fixed geographic regions | LIST |
| Equality queries by tenant, even distribution | HASH |
| One tenant generates most data | Handle skew explicitly |
| Queries filtering by both tenant and date | Suitable indexes, possibly subpartitioning |

## 6. Partition Pruning: Why Can It Be Faster?

**Partition pruning** lets PostgreSQL skip partitions that cannot contain rows matching query predicates.

~~~sql
SELECT *
FROM audit_events
WHERE occurred_on >= DATE '2026-02-01'
  AND occurred_on < DATE '2026-03-01';
~~~

If the table has 36 monthly partitions, the engine can scan only February.

~~~text
WHERE date in February
       |
Partition pruning
       |
Select audit_events_2026_02
       |
Seq Scan / Index Scan on selected partition
~~~

### 6.1. Pruning vs. Indexes

- **Pruning**: eliminates whole child relations outside predicate bounds.
- **Index scan**: locates rows inside a surviving relation.

If a query filters by tenant and date, date pruning and a local tenant index complement each other.

### 6.2. Without the Partition Key, Pruning Is Limited

If partitioned on `occurred_on` and a query filters solely by `tenant_id = 42`, PostgreSQL cannot infer from time bounds alone which months hold that tenant.

### 6.3. Write Pruning-Friendly Predicates

~~~sql
WHERE occurred_on >= DATE '2026-02-01'
  AND occurred_on < DATE '2026-03-01'
~~~

generally enables pruning far more reliably than wrapping the column in functions like `to_char(occurred_on,'YYYY-MM') = '2026-02'`. Behavior depends on planner/version; verify with `EXPLAIN`.

### 6.4. Planning-Time and Execution-Time Pruning

Some pruning happens during query planning; some happens in the executor once bind parameters are known. When reading `EXPLAIN`, check `Subplans Removed` or `(never executed)` nodes rather than merely counting partition names listed in the plan text.

## 7. Why Does Partitioning Not Scale Writes Across Multiple Machines?

~~~text
Single PostgreSQL primary
  +-- 120 monthly/daily partitions
  +-- one WAL/transaction engine
  +-- one primary handling all writes
~~~

Splitting into multiple relations can shrink scans, improve cache/index locality, and simplify maintenance. Yet one primary server still processes writes for every partition.

**Partition count is not server count.** Spreading writes across independent writable primaries requires sharding or a distributed architecture.

## 8. Table Inheritance Is a Different Feature

Inheritance uses `INHERITS`:

~~~sql
CREATE TABLE raw_events (
    event_id BIGINT,
    event_date DATE NOT NULL,
    content TEXT
);

CREATE TABLE raw_events_2026 (
    CHECK (
        event_date >= DATE '2026-01-01'
        AND event_date < DATE '2027-01-01'
    )
) INHERITS(raw_events);
~~~

Children inherit columns, `NOT NULL`, and CHECK constraints per PostgreSQL inheritance rules. However, the parent **is an ordinary table capable of storing rows directly**.

### 8.1. SELECT on Parent Reads Descendants

~~~sql
SELECT * FROM raw_events;
~~~

Normally, querying the parent includes rows from all descendant tables.

### 8.2. ONLY Reads Only the Parent

~~~sql
SELECT * FROM ONLY raw_events;
~~~

Excludes descendants.

### 8.3. INSERT into Parent Does Not Auto-Route to Children

~~~sql
INSERT INTO raw_events(event_id, event_date, content)
VALUES (1, DATE '2026-02-01', 'parent row');
~~~

This row lands directly in the **parent**, even though it satisfies the 2026 child's CHECK constraint.

### 8.4. Parent PK/UNIQUE Does Not Automatically Span Descendants

PRIMARY KEYs, UNIQUE indexes, foreign keys, and regular indexes on a legacy inheritance parent **do not automatically** extend across all descendants as global constraints/indexes.

### 8.5. CHECK Constraints Are Not Routers

CHECK constraints reject invalid rows inserted directly into that child; they never redirect an INSERT targeted at the parent into a child.

## 9. Legacy Inheritance-Based Partitioning

Before declarative partitioning became standard, a manual inheritance design typically involved:

1. An ordinary parent table.
2. Multiple children with `INHERITS`.
3. Date-range CHECK constraints on each child.
4. Triggers or rules routing INSERTs.
5. Constraint exclusion so the planner skips non-matching children.
6. Maintenance scripts creating monthly children and indexes.

~~~sql
CREATE TABLE raw_events_jan (
    CHECK (
        event_date >= DATE '2026-01-01'
        AND event_date < DATE '2026-02-01'
    )
) INHERITS(raw_events);
~~~

### 9.1. Constraint Exclusion

The planner compares child CHECK constraints against query WHERE clauses to prove a child cannot satisfy the query, skipping it in the plan.

### 9.2. Difference from Declarative Partition Pruning

Declarative partition pruning relies on specialized partition bound metadata; constraint exclusion relies on general CHECK constraint proofs at plan time. They are distinct mechanisms even though both avoid scanning irrelevant tables.

### 9.3. Risks of the Manual Approach

- CHECK ranges can accidentally overlap or leave gaps.
- Routing triggers can have bugs.
- Parent INSERTs can quietly store rows in the parent itself.
- Indexes and constraints can drift out of sync across children.
- Cross-child uniqueness, PKs, and FKs are hard to guarantee.
- Schema migrations must explicitly update the entire hierarchy.

For standard RANGE/LIST/HASH use cases on modern PostgreSQL, declarative partitioning is almost always the better starting point.

## 10. Partitions and Inheritance Share Catalog Roots

Declarative partition hierarchies still appear in parent-child catalog metadata such as `pg_inherits`. That **does not make the two features equivalent**.

| Catalog / Attribute | Meaning |
|---|---|
| `pg_class.relkind='p'` | Partitioned parent |
| `pg_class.relispartition` | Relation is a declarative partition |
| `pg_partitioned_table` | Partitioning strategy and key |
| `pg_inherits` | Parent-child link for both inheritance and partitioning |
| `pg_get_partkeydef` | Reads partition key definition |
| `pg_partition_tree` | Traverses partition hierarchy on supported versions |

Querying `pg_inherits` alone is insufficient to tell whether descendants enjoy declarative auto-routing.

## 11. Lab 1: Creating Real RANGE Partitions

Use a **practice database**. If schema `partition_lab` already exists, switch to another database/schema or rename it instead of dropping non-lab objects.

~~~sql
CREATE SCHEMA partition_lab;

CREATE TABLE partition_lab.order_events (
    event_id BIGINT NOT NULL,
    occurred_on DATE NOT NULL,
    tenant_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    PRIMARY KEY(event_id, occurred_on)
) PARTITION BY RANGE(occurred_on);

CREATE TABLE partition_lab.order_events_2026_01
PARTITION OF partition_lab.order_events
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE partition_lab.order_events_2026_02
PARTITION OF partition_lab.order_events
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

CREATE TABLE partition_lab.order_events_2026_03
PARTITION OF partition_lab.order_events
FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE TABLE partition_lab.order_events_default
PARTITION OF partition_lab.order_events DEFAULT;
~~~

### 11.1. Insert Through the Parent

~~~sql
INSERT INTO partition_lab.order_events(
    event_id, occurred_on, tenant_id, event_type, amount
)
VALUES
    (101, DATE '2026-01-15', 10, 'created', 120),
    (102, DATE '2026-01-20', 10, 'paid',    120),
    (103, DATE '2026-02-02', 20, 'created', 300),
    (104, DATE '2026-02-18', 10, 'paid',    300),
    (105, DATE '2026-03-05', 30, 'created',  75),
    (106, DATE '2026-04-01', 10, 'created',  44);
~~~

### 11.2. Inspect Where Rows Are Stored

~~~sql
SELECT
    tableoid::regclass AS physical_partition,
    event_id,
    occurred_on,
    tenant_id,
    amount
FROM partition_lab.order_events
ORDER BY event_id;
~~~

January rows land in `order_events_2026_01`; February in `order_events_2026_02`; March in `order_events_2026_03`; and `2026-04-01` lands in the default partition.

### 11.3. Query the Parent

~~~sql
SELECT event_id, tenant_id, amount
FROM partition_lab.order_events
WHERE occurred_on >= DATE '2026-02-01'
  AND occurred_on < DATE '2026-03-01';
~~~

Applications still reference one logical table name. PostgreSQL uses bounds to choose leaf relations.

## 12. Lab 2: EXPLAIN Partition Pruning

~~~sql
ANALYZE partition_lab.order_events;

EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM partition_lab.order_events
WHERE occurred_on >= DATE '2026-02-01'
  AND occurred_on < DATE '2026-03-01';
~~~

Verify whether the plan eliminates January, March, and default partitions.

### 12.1. Compare with a Query Lacking the Partition Key

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM partition_lab.order_events
WHERE tenant_id = 10;
~~~

The query must touch multiple partitions because every month could contain tenant 10.

### 12.2. Indexes and Pruning Complement Each Other

~~~sql
CREATE INDEX order_events_tenant_date_idx
ON partition_lab.order_events(tenant_id, occurred_on);

EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM partition_lab.order_events
WHERE tenant_id = 10
  AND occurred_on >= DATE '2026-01-01'
  AND occurred_on < DATE '2026-03-01';
~~~

The parent index definition creates child indexes. Because the lab table is tiny, Seq Scan may still beat Index Scan in cost; do not expect an Index Scan solely on 6 rows.

### 12.3. EXPLAIN ANALYZE Actually Executes the Statement

On SELECTs in the lab this is safe. However, `EXPLAIN ANALYZE INSERT/UPDATE/DELETE` runs live DML, so run it only in a test database or inside a rolled-back transaction.

## 13. Lab 3: HASH Partitioning by Tenant

~~~sql
CREATE TABLE partition_lab.tenant_messages (
    message_id BIGINT NOT NULL,
    tenant_id INTEGER NOT NULL,
    body TEXT,
    PRIMARY KEY(message_id, tenant_id)
) PARTITION BY HASH(tenant_id);

CREATE TABLE partition_lab.tenant_messages_p0
PARTITION OF partition_lab.tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE partition_lab.tenant_messages_p1
PARTITION OF partition_lab.tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE partition_lab.tenant_messages_p2
PARTITION OF partition_lab.tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE partition_lab.tenant_messages_p3
PARTITION OF partition_lab.tenant_messages
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
~~~

Load data and inspect distribution:

~~~sql
INSERT INTO partition_lab.tenant_messages(
    message_id, tenant_id, body
)
SELECT n, (n % 20) + 1, 'message-' || n::text
FROM generate_series(1,100) AS gs(n);

SELECT tableoid::regclass AS physical_partition,
       COUNT(*) AS number_of_rows
FROM partition_lab.tenant_messages
GROUP BY tableoid
ORDER BY physical_partition;
~~~

This still lives inside one PostgreSQL database. HASH partitions do not turn into multiple physical servers.

## 14. Lab 4: Demonstrating How Inheritance Differs from Partitioning

~~~sql
CREATE SCHEMA inheritance_lab;

CREATE TABLE inheritance_lab.events(
    event_id BIGINT,
    occurred_on DATE NOT NULL,
    action TEXT NOT NULL
);

CREATE TABLE inheritance_lab.events_jan (
    CHECK (
        occurred_on >= DATE '2026-01-01'
        AND occurred_on < DATE '2026-02-01'
    )
) INHERITS(inheritance_lab.events);

CREATE TABLE inheritance_lab.events_feb (
    CHECK (
        occurred_on >= DATE '2026-02-01'
        AND occurred_on < DATE '2026-03-01'
    )
) INHERITS(inheritance_lab.events);
~~~

### 14.1. INSERT into Parent

~~~sql
INSERT INTO inheritance_lab.events(event_id, occurred_on, action)
VALUES (1, DATE '2026-01-10', 'parent');
~~~

The row lands directly in the parent.

### 14.2. INSERT into Children

~~~sql
INSERT INTO inheritance_lab.events_jan(event_id, occurred_on, action)
VALUES (2, DATE '2026-01-11', 'child');

INSERT INTO inheritance_lab.events_feb(event_id, occurred_on, action)
VALUES (3, DATE '2026-02-03', 'child');
~~~

### 14.3. SELECT Without ONLY

~~~sql
SELECT tableoid::regclass, event_id, occurred_on
FROM inheritance_lab.events
ORDER BY event_id;
~~~

Returns rows from both parent and children.

### 14.4. SELECT ONLY

~~~sql
SELECT *
FROM ONLY inheritance_lab.events;
~~~

Returns only the row stored directly in the parent. This distinction is critical when maintaining inheritance hierarchies.

## 15. PRIMARY KEY and UNIQUE in Declarative Partitioning

A fundamental design limitation: standard PostgreSQL **does not have a single global physical unique B-tree index** spanning every leaf partition of a partitioned table.

If partitions are split by date, two local child indexes on `event_id` could each permit `event_id=777` independently without seeing the duplicate in the sibling child.

### 15.1. Why Must a PK Include the Partition Key?

With partition key `occurred_on`, a valid common PK is:

~~~sql
PRIMARY KEY(event_id, occurred_on)
~~~

Because rows sharing the same pair must map to the same partition, a local unique index on each partition suffices to enforce pair uniqueness.

### 15.2. Typical Invalid Example

~~~sql
CREATE TABLE invalid_events (
    event_id BIGINT PRIMARY KEY,
    occurred_on DATE NOT NULL
) PARTITION BY RANGE(occurred_on);
~~~

This **intentionally illustrates the restriction**: a parent partitioned by `occurred_on` cannot enforce uniqueness solely on `event_id` via an implicit global index.

### 15.3. What If event_id Must Be Globally Unique Across the Cluster?

Options to consider:

- Use a composite key and update application references.
- Choose a partition key that aligns with the PK.
- Maintain a non-partitioned registry table tracking global IDs transactionally.
- Leave the table unpartitioned if global uniqueness outweighs partitioning benefits.
- Pair ID generation with uniqueness enforcement; never treat UUIDs/sequences alone as a strict constraint substitute.

### 15.4. Inheritance Has Additional Restrictions

A PRIMARY KEY on an ordinary inheritance parent does not enforce uniqueness across children at all; integrity must be designed separately.

## 16. FOREIGN KEY, CHECK, and Row Movement

### 16.1. Foreign Keys

Modern PostgreSQL supports foreign keys referencing or declared on partitioned tables within applicable version/structural rules.

For example, a child table referencing the lab's composite PK:

~~~sql
CREATE TABLE partition_lab.event_notes (
    note_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id BIGINT NOT NULL,
    occurred_on DATE NOT NULL,
    note TEXT NOT NULL,
    FOREIGN KEY (event_id, occurred_on)
        REFERENCES partition_lab.order_events(event_id, occurred_on)
);
~~~

Do not repeat outdated claims that "partitioned tables do not support foreign keys at all." However, FKs on ordinary inheritance parents do not cover descendants as applications often expect.

### 16.2. Updating the Partition Key

~~~sql
UPDATE partition_lab.order_events
SET occurred_on = DATE '2026-02-11'
WHERE event_id = 101
  AND occurred_on = DATE '2026-01-15';
~~~

Modern PostgreSQL versions move the row to the destination partition matching the new key. Internally this involves delete/insert semantics across leaves, interacting with constraints, triggers, and concurrency.

### 16.3. ON CONFLICT Limitations

Certain `INSERT ... ON CONFLICT DO UPDATE` updates that change the partition key to move rows across partitions have version-specific limits. Never assume UPSERT supports every cross-partition move just like regular UPDATE; test on your target server version.

### 16.4. WHERE Without the Partition Key

~~~sql
UPDATE partition_lab.order_events
SET amount = amount + 1
WHERE tenant_id = 10;
~~~

This must scan multiple partitions. Partitioning does not automatically make every DML statement cheaper.

## 17. Retention: DROP/DETACH vs. DELETE

Monthly time-series data often follows an 18–24 month retention policy.

In a non-partitioned table, deleting hundreds of millions of old rows requires batched DELETEs, generates heavy WAL and dead tuples, and burdens VACUUM and index cleanup.

With RANGE partitions, you can retire **an entire table** representing one month at once.

### 17.1. DETACH PARTITION

~~~sql
ALTER TABLE partition_lab.order_events
DETACH PARTITION partition_lab.order_events_2026_01;
~~~

Once detached, the child remains as an independent table, invisible to parent SELECTs. Run this command **only after completing any lab exercises that still need January data**.

### 17.2. ATTACH PARTITION

~~~sql
ALTER TABLE partition_lab.order_events
ATTACH PARTITION partition_lab.order_events_2026_01
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
~~~

Run only if the child is currently detached, matches schema/constraints/bounds, and overlaps no existing partition on the parent.

### 17.3. ATTACH May Scan Data

PostgreSQL must validate that existing rows satisfy the bounds. A matching validated CHECK constraint can skip some validation scans. When a DEFAULT partition exists, attaching a new bound may scan DEFAULT to verify it holds no rows falling in the new range.

### 17.4. DETACH CONCURRENTLY

Supported versions provide `DETACH PARTITION ... CONCURRENTLY`, with constraints around transaction blocks, default partitions, and lock behavior. Never slap `CONCURRENTLY` into automated migration scripts blindly.

### 17.5. DROP Does Not Automatically Archive

If compliance requires retaining data, export, back up, and verify before dropping; DDL never replaces retention and backup governance.

## 18. Indexes, VACUUM, and ANALYZE per Partition

Each leaf partition is an independent physical relation with local indexes, statistics, and storage.

### 18.1. Parent Index vs. Local Indexes

~~~sql
CREATE INDEX order_events_amount_idx
ON partition_lab.order_events(amount);
~~~

The parent index definition automatically governs corresponding local indexes on leaf partitions. It is still not a single global index.

### 18.2. Maintenance Advantages

You can VACUUM, REINDEX, or ANALYZE a hot leaf individually or archive a cold leaf, scoping locks and I/O to where they are needed.

### 18.3. Parent Statistics

~~~sql
ANALYZE partition_lab.order_events;
~~~

Autovacuum/autoanalyze maintain leaf statistics, yet inherited parent summary statistics may not update automatically when only child tables change. Workloads relying on parent-level stats should explicitly schedule `ANALYZE` on the parent.

### 18.4. Too Many Partitions Slow Things Down

Each partition adds relations, indexes, and catalog entries. Planning time, relcache memory, lock tables, autovacuum scheduling, and DDL complexity all pay overhead. Never design "a partition every 100 rows."

## 19. Multi-Level Subpartitioning

Example:

~~~text
orders PARTITION BY RANGE(order_date)
  orders_2026_01 PARTITION BY HASH(tenant_id)
     orders_2026_01_p0
     orders_2026_01_p1
     orders_2026_01_p2
     orders_2026_01_p3
  orders_2026_02 PARTITION BY HASH(tenant_id)
     orders_2026_02_p0
     orders_2026_02_p1
     orders_2026_02_p2
     orders_2026_02_p3
~~~

Two levels can fit queries filtering by both tenant and date alongside monthly retention.

However:

\[
36\ \text{months}\times 32\ \text{buckets}=1{,}152\ \text{leaf partitions}
\]

And that is before counting indexes. Subpartitioning still runs on **one cluster** unless paired with distributed sharding.

## 20. What Is Sharding and How Does a Router Work?

Sharding distributes disjoint sets of rows across multiple independent PostgreSQL servers. Each request relies on a **shard key** or consults a metadata directory.

~~~text
tenant_id=1450
     |
     v
Router / shard map
     |
     v
PostgreSQL B
     |
     v
orders WHERE tenant_id=1450
~~~

### 20.1. Queries with a Shard Key

Can route straight to a single shard, avoiding fanout.

### 20.2. Queries Without a Shard Key

May need to fan out to A, B, and C and aggregate results. This is **scatter-gather**; network latency and partial node failures become part of normal query execution.

### 20.3. The Shard Key Defines Data Locality

Sharding by `tenant_id` keeps a tenant's orders, customers, and line items colocated, keeping JOINs and transactions local. Sharding by `order_id` optimizes single-order lookups while complicating per-tenant analytics.

### 20.4. Shard Key vs. Partition Key

The partition key selects **which table inside a cluster**; the shard key selects **which server/cluster**. A system can employ both keys independently.

## 21. Sharding Strategies

### 21.1. Range Sharding

~~~text
tenants 1-1000      -> A
tenants 1001-2000   -> B
tenants 2001-3000   -> C
~~~

Simple to understand, though big tenants or sequential ID growth hotspots quickly create uneven load.

### 21.2. Hash Sharding

~~~text
stable_hash(tenant_id) -> bucket
bucket -> shard
~~~

Spreads keys more evenly when tenant sizes are balanced, though changing the physical shard count requires remapping and rebalancing data.

### 21.3. Virtual Buckets

Instead of hashing modulo *N* physical machines directly, map keys into many logical buckets and map buckets onto machines. Adding a machine only moves a subset of buckets.

### 21.4. Directory-Based Sharding

~~~text
tenant_id | shard_id
42        | A
1450      | B
3001      | C
~~~

Allows moving individual tenants cleanly, at the cost of maintaining directory synchronization, cache invalidation, and clean cutovers.

### 21.5. Geographic Sharding

Shards by region to reduce latency or satisfy data residency laws. Cross-region networking, failover, and compliance must be designed explicitly.

## 22. Sharding vs. Replication

**Replication** duplicates the same data, whereas sharding splits disjoint data.

~~~text
REPLICATION
Primary A (entire dataset)
   +-- Standby A1 (replica)
   +-- Standby A2 (replica)

SHARDING
Primary A (tenants 1..1000)
Primary B (tenants 1001..2000)
Primary C (tenants 2001..3000)
~~~

Read replicas scale read throughput and aid HA, without adding writable primaries for the same dataset.

Both are commonly combined:

~~~text
Shard A primary -> A standby
Shard B primary -> B standby
Shard C primary -> C standby
~~~

Each shard still maintains its own replication, failover, recovery, and monitoring.

## 23. postgres_fdw and Distributed Extensions

PostgreSQL includes `postgres_fdw` to query foreign tables on remote PostgreSQL servers.

~~~text
PostgreSQL A
   -> postgres_fdw
   -> PostgreSQL B (remote table)
~~~

### 23.1. What FDW Can Help With

Reading and writing configured foreign tables, pushing down supported filters/joins/aggregates, and joining local tables with remote datasets.

### 23.2. FDW Is Not a Complete Sharding Solution

Out of the box it does not automatically provide shard routing, rebalancing, global uniqueness, global FKs, cross-server ACID, HA, or coordinated cluster-wide backups.

### 23.3. Multi-Server Transactions

Do not assume statements touching multiple foreign servers automatically participate in an atomic distributed two-phase commit simply because a client issued `BEGIN`. Verify actual failure semantics and handle partial failures.

### 23.4. Distributed PostgreSQL Solutions

Certain extensions and distributed products add coordinators, distributed tables, shard placement, and query pushdown/routing. However, SQL compatibility, FKs, JOINs, transaction semantics, index behavior, and failover vary significantly by product and version—never generalize across all tools.

## 24. Cross-Shard JOINs and Co-Location

Consider:

~~~sql
SELECT o.order_id, SUM(i.quantity)
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.tenant_id = 42
GROUP BY o.order_id;
~~~

If tenant 42's `orders` and `order_items` reside on the same shard A, the JOIN runs locally.

If `orders` sits on A and `order_items` on C, a distributed engine must ship rows over the network or coordinate a distributed join.

### 24.1. Choose Shard Keys Around Transaction Boundaries

Tables routinely joined or updated together should be co-located wherever feasible.

### 24.2. Global Analytics

Cluster-wide `SUM` can compute partial sums locally per shard and merge them. `DISTINCT`, window functions, global `ORDER BY`, and exact percentiles become significantly harder.

### 24.3. Reference Tables

Some distributed platforms replicate small shared lookup/reference tables across all workers, requiring care around update propagation and consistency.

## 25. Transactions Within One Cluster vs. Across Shards

### 25.1. Single-Cluster Partitioning

~~~sql
BEGIN;

UPDATE partition_lab.order_events
SET amount = amount + 1
WHERE event_id = 102
  AND occurred_on = DATE '2026-01-20';

UPDATE partition_lab.order_events
SET amount = amount + 1
WHERE event_id = 103
  AND occurred_on = DATE '2026-02-02';

COMMIT;
~~~

Two updates spanning two different partitions execute inside **one atomic PostgreSQL transaction**.

### 25.2. Single-Cluster Inheritance

Similarly, ordinary parent/child tables in one database participate in one transaction, even though routing and constraint behavior differ from declarative partitioning.

### 25.3. Multi-Primary Sharding

~~~text
Shard A: debit account X by 100, COMMIT.
Network failure.
Shard B: credit account Y by 100 never runs.
~~~

Two independent local COMMITs are not globally atomic.

### 25.4. Protection Strategies

- Co-locate entities needing atomic updates.
- Use a distributed transaction protocol supported by your distributed platform.
- Use Sagas and compensating transactions.
- Use the transactional outbox pattern and idempotency keys.
- Maintain double-entry ledgers and periodic reconciliation.
- Explicitly define strong vs. eventual consistency per workflow.

Never treat "every standalone query returned OK" as proof of cross-machine workflow atomicity.

## 26. Global Uniqueness and Foreign Keys Under Sharding

### 26.1. Local UNIQUE Is Not Global UNIQUE

~~~text
Shard A has username='alice'
Shard B has username='alice'

Each server enforces UNIQUE(username).
System-wide, duplicate usernames exist.
~~~

### 26.2. Per-Tenant Uniqueness Is Easier with Co-Location

If you only require `UNIQUE(tenant_id,username)` and all rows of a tenant live on one shard, local unique constraints protect the required scope.

### 26.3. System-Wide Uniqueness

Requires a central registry/lookup service or distributed uniqueness protocol; generating UUIDs does not replace uniqueness checks on usernames, emails, or business keys.

### 26.4. Cross-Shard Foreign Keys

A local PostgreSQL foreign key on server A cannot natively enforce references to a row living on server B inside a single local transaction. Co-locate data, rely on a distributed platform's FK support where available, or enforce via application protocols and reconciliation.

### 26.5. Pre-Checks Suffer from Race Conditions

Checking a customer row on B and then inserting an order on A is non-atomic; the customer could be modified or deleted right after the pre-check without coordination.

## 27. Hot Shards and Data Skew

If tenant 42 produces 80% of write traffic and sharding hashes by `tenant_id`:

~~~text
tenant 42 -> hits a single shard
80% writes -> hammer that one shard
~~~

Hashing does not split one giant tenant across multiple servers.

### 27.1. Mitigations

- Dedicated shard for whale tenants.
- Sub-sharding by `order_id` or time where business logic allows.
- Read replicas and caching for read hotspots.
- Separating OLTP from analytics.
- Rebalancing virtual buckets across servers.
- Eliminating contention on hot rows/indexes/business keys.

### 27.2. Locality Trade-Offs

Splitting a giant tenant across shards makes cross-shard JOINs and transactions for that tenant much harder.

### 27.3. Measure Skew Explicitly

Track QPS, WAL bytes/sec, CPU, IOPS, relation sizes, replication lag, and top tenants—not just shard counts.

## 28. Rebalancing Across Machines

Adding shard D alongside A/B/C typically requires migrating tenants or buckets off existing shards.

### 28.1. Core Steps

1. Identify the data subset to move.
2. Backfill historical data.
3. Capture ongoing live writes.
4. Catch up and sync deltas.
5. Verify row counts, checksums, and invariants.
6. Cut over the router/shard map.
7. Drain/handle in-flight requests cleanly.
8. Monitor post-cutover health.
9. Keep a verified rollback path.
10. Purge old source copies once verified safe.

### 28.2. Stale Metadata

If one application instance routes tenant 42 to A while an updated router sends it to D, writes split across both servers, losing updates or duplicating records. Shard maps need explicit versioning and synchronized cutover protocols.

### 28.3. Rebalancing Is Not ATTACH

Partition `ATTACH`/`DETACH` is local cluster DDL. Resharding is **live data migration across a network**, carrying partial failure and split-brain risks.

## 29. Backups, HA, and Replication Lag

### 29.1. Backing Up a Partitioned Cluster

Single-cluster PostgreSQL backups naturally cover the entire partition hierarchy atomically; point-in-time recovery follows standard cluster backup tooling.

### 29.2. Backing Up a Sharded Platform

If shard A backs up at 10:00 and shard B at 10:05, a distributed transaction occurring at 10:03 may restore inconsistently across those two uncoordinated snapshots.

### 29.3. RPO and RTO

Recovery objectives must cover the entire platform—shard map, primaries, replicas, backups, and reconciliation—not just single servers in isolation.

### 29.4. Replica Lag

A client writing to a primary and immediately reading a standby before WAL replays sees stale data. That is a replication/read-consistency issue, unrelated to partition pruning.

### 29.5. Per-Shard HA

Losing shard B's primary affects only its subset of tenants, yet shard B still needs standby failover and recovery. Having 100 partitions on a single primary provides zero HA.

## 30. Inspecting Partition Hierarchies in the Catalog

### 30.1. pg_partition_tree

~~~sql
SELECT *
FROM pg_partition_tree(
    'partition_lab.order_events'::regclass
);
~~~

### 30.2. Partition Key

~~~sql
SELECT pg_get_partkeydef(
    'partition_lab.order_events'::regclass
);
~~~

### 30.3. pg_partitioned_table

~~~sql
SELECT
    partrelid::regclass AS parent,
    partstrat
FROM pg_partitioned_table
WHERE partrelid =
    'partition_lab.order_events'::regclass;
~~~

### 30.4. pg_inherits

~~~sql
SELECT
    inhparent::regclass AS parent,
    inhrelid::regclass AS child
FROM pg_inherits
WHERE inhparent =
    'partition_lab.order_events'::regclass;
~~~

### 30.5. relkind and relispartition

~~~sql
SELECT oid::regclass, relkind, relispartition
FROM pg_class
WHERE oid IN (
    'partition_lab.order_events'::regclass,
    'partition_lab.order_events_2026_01'::regclass,
    'inheritance_lab.events'::regclass,
    'inheritance_lab.events_jan'::regclass
);
~~~

A declarative parent shows `relkind='p'`; an ordinary inheritance parent cannot be distinguished by checking `pg_inherits` alone.

### 30.6. Bounds

~~~sql
SELECT
    c.oid::regclass AS child,
    pg_get_expr(c.relpartbound, c.oid) AS bound
FROM pg_class AS c
JOIN pg_inherits AS i ON i.inhrelid=c.oid
WHERE i.inhparent =
    'partition_lab.order_events'::regclass;
~~~

## 31. Checking Partition Storage Sizes

Because a partitioned parent holds no heap rows of its own, querying `pg_relation_size(parent)` misses the actual stored dataset.

~~~sql
SELECT
    inhrelid::regclass AS partition_name,
    pg_size_pretty(
        pg_total_relation_size(inhrelid)
    ) AS total_size
FROM pg_inherits
WHERE inhparent =
    'partition_lab.order_events'::regclass;
~~~

With multi-level hierarchies, aggregate **leaf partitions** rather than direct level-1 children alone.

- `pg_relation_size` measures the relation/fork per argument.
- `pg_indexes_size` measures attached indexes.
- `pg_total_relation_size` combines table, index, and TOAST storage.

Monitor the default partition, oversized partitions, and index bloat to catch routing issues or skew early.

## 32. Schema Migrations: Single Machine vs. Multi-Machine

### 32.1. Declarative Partitioning

Running `ALTER TABLE parent` propagates structurally down the hierarchy per PostgreSQL rules, though you must still manage locks, index validation, and constraints.

### 32.2. Legacy Inheritance

Must explicitly verify children, routing triggers, CHECK bounds, indexes, and column types. Never assume parent changes create desired child indexes or constraints automatically.

### 32.3. Sharding

A migration can succeed on shards A and B while failing on C:

~~~text
A schema version 12
B schema version 12
C schema version 11
~~~

Applications must tolerate mixed-schema windows or rely on coordinated orchestration and rollback.

### 32.4. Expand-Contract Pattern

Add backward-compatible columns/structures first, deploy code reading/writing both versions, backfill, flip read/write paths, and clean up old schema later.

### 32.5. Watch Out for Downtime and Locks

`CREATE INDEX`, `ATTACH`, `DETACH`, and `ALTER` enforce version-specific lock and transaction rules. Use `lock_timeout` and `statement_timeout` safely, never mistaking timeouts for an actual online schema-change plan.

## 33. Security and Tenant Isolation

Partitioning by tenant or sharding by tenant **does not replace authorization**.

### 33.1. Partitioning

A user can still query another tenant's rows if SQL grants, RLS policies, or application checks permit it. Never mistake a partition key for a security boundary.

### 33.2. Sharding

Multiple tenants often share the same shard. Routing to the right server does not prevent an API bug from exposing another co-resident tenant's rows.

### 33.3. RLS, GRANT, and Direct Child Access

Understand privileges across parent vs. partitions, how RLS evaluates, and what happens if clients hold direct grants on leaf partitions. Never assume parent-level policies automatically protect direct queries to leaf tables in every circumstance.

### 33.4. Compliance

Isolating tenants onto dedicated servers or regions helps meet data residency mandates while multiplying backup, HA, and operational overhead. Analyze requirements explicitly.

## 34. When Should You Use Partitioning?

Usually a good fit when:

- A single primary handles total write throughput.
- The table is large and queries filter heavily by the partition key.
- Time-based retention/archival applies.
- You want scoped `VACUUM`, `REINDEX`, or maintenance per partition.
- You need single-cluster ACID transactions and full SQL.
- You do not immediately need independent writable primaries.

For example, audit logs with 18-month retention where most queries inspect the past 7 days: monthly or weekly RANGE partitioning is well worth benchmarking.

**Do not** partition a few-thousand-row table just because you can, nor split into 10,000 partitions without measuring planner and catalog overhead.

## 35. When Is Inheritance Appropriate?

Some legacy applications use inheritance for parent-child data models or older partitioning setups. Maintaining it may be necessary for compatibility, provided you verify:

- Whether the parent holds rows directly.
- Whether routing triggers/rules exist.
- Whether child CHECK ranges overlap or leave gaps.
- Whether UNIQUE, FK, and index scopes are properly covered.
- Whether SELECT/UPDATE queries use `ONLY` correctly.
- Whether schema migrations propagate cleanly to all children.

For new RANGE/LIST/HASH setups on modern PostgreSQL, declarative partitioning requires far less manual glue.

## 36. When Do You Truly Need Sharding?

Worth evaluating when:

- Primary write throughput exceeds reasonable vertical scale-up limits.
- Total storage, WAL volume, or retention outgrows one cluster.
- Tenant isolation demands independent writable primaries.
- Geographic data residency or blast-radius isolation requires separate clusters.
- Most queries and transactions carry an explicit shard key.
- Engineering and ops are prepared to manage distributed consistency.

First measure gains from query/index tuning, declarative partitioning, read replicas, connection pooling, archival, and analytics offloading.

**Sharding is never free**: cross-shard JOINs, global uniqueness, transactions, backup consistency, rebalancing, and failover become dramatically more complex than on one cluster.

## 37. Combining Both: Shard by Tenant, Partition by Time

~~~text
Request: tenant_id=1450, occurred_on='2026-02-10'
    |
Shard router -> PostgreSQL B
    |
Partition router -> events_2026_02 on B
~~~

Two tiers:

1. **Shard key** `tenant_id` selects PostgreSQL server B.
2. **Partition key** `occurred_on` selects the February leaf table on B.

Benefits: writes scale horizontally across primaries, monthly retention stays fast, and queries carrying both tenant and date get locality plus partition pruning.

Costs: partitions must be managed across every shard; synchronized migrations, per-shard HA/backups, cross-tenant fanout reports, and global uniqueness remain operational concerns.

## 38. Migrating from a Regular Table to Partitioning

If an existing table uses `PRIMARY KEY(order_id)` and you want to partition by `order_date`, re-evaluate uniqueness invariants first.

A typical migration plan:

1. Create the new partitioned parent.
2. Create partitions and indexes.
3. Redesign PK/FK constraints to include the partition key where required.
4. Backfill historical data in controlled batches.
5. Synchronize concurrent live writes during backfill.
6. Verify row counts, checksums, and constraints.
7. Cut over the application.
8. Keep a tested rollback path.
9. Drop the legacy table only after validation.

Do not treat this as a simple table rename; ORMs, triggers, sequences, defaults, RLS, and UPSERT behavior may all be affected.

## 39. Migrating from Inheritance to Declarative Partitioning

Critical pre-flight checks:

- `SELECT COUNT(*) FROM ONLY parent`: does the parent directly hold rows?
- Are child CHECK bounds valid, contiguous, and non-overlapping?
- Do column data types and defaults align identically?
- How must child indexes and constraints be converted?
- Do PK/UNIQUE/FK definitions include the partition key?
- Which legacy routing triggers/rules must be dropped?
- How much validation scanning will `ATTACH` trigger?
- How will cutover coordinate with concurrent writes?
- Are backup, rollback, and application compatibility verified?

Inheritance partitioning never upgrades itself just by swapping `INHERITS` for `PARTITION OF`.

## 40. Common Misconceptions

1. **"Partitioning is sharding."** False: one splits tables inside a cluster; the other splits data across independent servers.
2. **"More partitions means more primaries."** False.
3. **"`INHERITS` works just like `PARTITION OF`."** False regarding auto-routing and constraints.
4. **"Child CHECK constraints automatically route parent INSERTs."** False.
5. **"SELECT on an inheritance parent reads only the parent."** False; use `ONLY` when needed.
6. **"A PK on an inheritance parent enforces uniqueness across children."** False.
7. **"A partitioned parent always maintains a global unique index."** False.
8. **"`PK(event_id)` is always valid when partitioned by date."** False under standard declarative partitioning rules.
9. **"With partition pruning, you don't need indexes."** False.
10. **"`WHERE tenant_id` automatically prunes time partitions."** False without partition key bounds.
11. **"Four HASH partitions equal four machines."** False.
12. **"HASH by tenant spreads a whale tenant across partitions."** False.
13. **"More partitions is always faster."** False; planner and catalog overhead scale up.
14. **"`DETACH` deletes rows like `DELETE`."** False.
15. **"Default partitions don't need monitoring."** False.
16. **"Replication is sharding."** False.
17. **"Read replicas add writable primaries."** False.
18. **"FDWs provide global ACID out of the box."** False.
19. **"Two COMMITs on two shards are atomic."** False.
20. **"Per-shard uniqueness guarantees platform-wide uniqueness."** False.
21. **"A local foreign key on A can natively reference a row only on B."** False by default.
22. **"UUIDs replace all uniqueness constraints."** False.
23. **"Routing to the right shard replaces authorization."** False.
24. **"Backing up each shard individually guarantees a globally consistent restore."** False.
25. **"Just add another server; no rebalancing needed."** False in most sharded designs.

## 41. Practice Exercises

### Exercise 1 — Definitions

Distinguish declarative partitioning, inheritance, and sharding in three sentences.

**Hint:** Single-cluster child tables with bounds/routing; `INHERITS` parent-child; multi-server data distribution.

### Exercise 2 — RANGE

Does a January partition `FROM('2026-01-01') TO('2026-02-01')` include `2026-02-01`?

**Answer:** No; the upper bound is exclusive.

### Exercise 3 — Parent Storage

Do rows in a declarative partitioned table reside primarily in the parent heap or in leaf partitions?

**Answer:** Leaf partitions.

### Exercise 4 — Pruning

Table is partitioned by `occurred_on`; `WHERE` filters only `tenant_id=42`. Will PostgreSQL prune away other months?

**Answer:** No, not from time bounds when filtering only by tenant.

### Exercise 5 — Indexes

Why are `tenant_id` indexes still valuable inside time partitions?

**Hint:** They reduce rows scanned within each surviving leaf.

### Exercise 6 — tableoid

Write SQL to discover which physical relation holds `event_id=101`.

~~~sql
SELECT tableoid::regclass, event_id
FROM partition_lab.order_events
WHERE event_id=101;
~~~

### Exercise 7 — HASH

Should you evaluate `tenant_id % 4` in application logic to predict exact PostgreSQL HASH partition placement?

**Answer:** No.

### Exercise 8 — Inheritance Insert

Does an INSERT into an ordinary inheritance parent automatically route into a child whose CHECK matches?

**Answer:** No.

### Exercise 9 — ONLY

How does `SELECT ... FROM ONLY parent` differ from `SELECT ... FROM parent` under inheritance?

**Hint:** It reads only rows stored directly in the parent.

### Exercise 10 — Constraint Exclusion

Which mechanism uses CHECK constraints to skip non-matching legacy children?

**Answer:** Constraint exclusion.

### Exercise 11 — PK

With `occurred_on` as partition key, is `PRIMARY KEY(event_id)` valid as a default global unique constraint?

**Answer:** No.

### Exercise 12 — Valid PK

Propose a valid PK using `event_id` and `occurred_on`.

**Hint:** `PRIMARY KEY(event_id, occurred_on)`.

### Exercise 13 — Global IDs

Why do UUIDs not fully replace uniqueness constraints on business keys?

**Hint:** Business keys differ from UUIDs and duplicate records can be ingested or entered manually.

### Exercise 14 — Key Update

What can happen when updating `occurred_on` from January to February?

**Answer:** Cross-partition row movement.

### Exercise 15 — Retention

Why does dropping or detaching a monthly partition differ from running `DELETE` across millions of rows?

**Hint:** Relation-level DDL rather than row-by-row DML.

### Exercise 16 — Default Partition

A default partition accumulates a full year of rows because the partition-creation job failed. What risks arise?

**Hint:** Storage growth, degraded pruning, costly ATTACH validation, broken retention drops.

### Exercise 17 — Catalog

Which function displays the declarative partition hierarchy?

**Answer:** `pg_partition_tree` on supported versions.

### Exercise 18 — pg_inherits

Is `pg_inherits` used exclusively for declarative partitioning?

**Answer:** No.

### Exercise 19 — Storage

Why does checking only `pg_relation_size(parent)` underestimate total table size?

**Hint:** Actual heap rows live inside leaf partitions.

### Exercise 20 — Subpartitions

How many leaf tables result from 36 months × 32 hash buckets?

**Answer:** 1,152.

### Exercise 21 — Shard Key

A multi-tenant SaaS runs 90% of queries filtered by `tenant_id`. Which shard key should you evaluate first?

**Hint:** `tenant_id`, while checking for whale/hot tenants.

### Exercise 22 — Scatter-Gather

What does a cluster-wide query lacking the shard key require?

**Hint:** Fanout across shards and result aggregation.

### Exercise 23 — Co-Location

Why does co-locating `orders` and `order_items` on the same shard by tenant speed up JOINs?

**Hint:** Avoids cross-network data movement.

### Exercise 24 — Hot Tenant

One tenant generates 80% of writes. Does hashing by `tenant_id` spread that tenant across multiple servers?

**Answer:** No.

### Exercise 25 — Replication

Does a physical standby hold a replica of the same data or a different shard?

**Answer:** A replica of the same primary's data.

### Exercise 26 — FDW

Does `postgres_fdw` natively supply global unique indexes and full distributed commit coordination?

**Answer:** Not by default.

### Exercise 27 — Global Uniqueness

Does `UNIQUE(email)` on each shard guarantee email uniqueness platform-wide?

**Answer:** No.

### Exercise 28 — FK

Can a local foreign key on shard A natively reference a row stored solely on shard B like a local row?

**Answer:** Not by default.

### Exercise 29 — Distributed Transfer

Shard A debits money and COMMITs, then the network fails before shard B credits. What solutions address this?

**Hint:** Co-location, distributed transaction protocols, or Sagas, outbox, idempotency, and reconciliation.

### Exercise 30 — Rebalancing

How do virtual buckets help when adding a new server?

**Hint:** Migrate a subset of buckets and update the bucket-to-shard mapping.

### Exercise 31 — Backups

Do separate backups of shard A at 10:00 and shard B at 10:05 form a single globally consistent snapshot?

**Answer:** Not necessarily.

### Exercise 32 — HA

Does a cluster with 100 partitions on one primary and zero standbys have automatic HA?

**Answer:** No.

### Exercise 33 — RLS

Does partitioning by `tenant_id` prevent tenant A from reading tenant B's rows?

**Answer:** No; enforce authorization, RLS, and GRANTs explicitly.

### Exercise 34 — Combined Architecture

With sharding by tenant and partitioning by date, what are the two routing tiers?

**Answer:** The shard router picks the server by tenant; PostgreSQL picks the leaf partition by date.

### Exercise 35 — Migration

List five checks required before migrating legacy inheritance to declarative partitioning.

**Hint:** Rows directly in parent, valid non-overlapping CHECK ranges, index/constraint alignment, legacy routing triggers, schema compatibility.

### Exercise 36 — Choosing an Architecture

| Requirement | Direction to Evaluate |
|---|---|
| Drop monthly data on a primary with ample capacity | Declarative RANGE |
| Legacy parent-child hierarchy | Inheritance (understanding limitations) |
| Write throughput exceeds one primary | Sharding |
| Scale read QPS when one primary handles writes | Read replicas |
| Scale writes out and drop monthly data | Sharding + partitions per shard |

## 42. Decision Checklist

1. Identify the bottleneck: scans, retention drops, bloat, write throughput, or HA.
2. Measure workload: row counts, CPU, WAL, IOPS, p95/p99 latency.
3. Group queries by date filters, tenant filters, and global ID lookups.
4. Inventory PK, UNIQUE, FK, and transaction invariants.
5. Evaluate query/index tuning, archival, and read replicas first.
6. If partitioning: choose key, RANGE/LIST/HASH, and granularity.
7. Measure pruning with `EXPLAIN` and statistics.
8. Automate future partition pre-creation, default monitoring, and retention.
9. Monitor leaf indexes, `ANALYZE`, `VACUUM`, and planner overhead.
10. If using inheritance: verify CHECKs, `ONLY`, and INSERT routing.
11. If sharding: select shard keys around locality and skew.
12. Design router, shard map, and metadata versioning.
13. Classify single-shard vs. cross-shard queries.
14. Protect global uniqueness, FKs, and distributed transactions.
15. Engineer per-shard HA, replication, and backup/recovery.
16. Plan rebalancing, online migrations, and rollbacks.
17. Verify RLS, privileges, and tenant isolation.
18. Stress-test concurrent writes and network partitions.
19. Benchmark before/after on representative datasets.
20. Re-evaluate architecture as data distribution evolves.

## 43. Quick Reference Table

| Concept | Key Takeaway |
|---|---|
| Declarative partitioning | `PARTITION BY RANGE/LIST/HASH` |
| Leaf partition | Physical table storing actual rows |
| Partition key | Selects child table |
| RANGE bounds | Inclusive lower, exclusive upper |
| Partition pruning | Skips partitions incapable of matching |
| Local index | Index per leaf relation |
| Parent partitioned index | Definition managing local leaf indexes |
| DEFAULT partition | Catches rows outside explicit bounds |
| ATTACH/DETACH | Connects/separates partitions in hierarchy |
| INHERITS | Legacy table inheritance |
| ONLY | Targets ordinary parent only in eligible queries |
| Constraint exclusion | Uses CHECK constraints to skip legacy children |
| `tableoid` | Identifies physical relation holding a row |
| Global uniqueness | Not automatically provided across local indexes |
| Sharding | Distributes data across multiple servers |
| Shard key | Selects server/cluster |
| Shard map | Maps key/bucket -> server |
| Scatter-gather | Queries multiple shards and merges results |
| Co-location | Keeps joined data on the same shard |
| Hot shard | One server overloaded by traffic skew |
| Rebalance | Migrates tenants/buckets across servers |
| Replication | Copies data for HA and read scaling |
| `postgres_fdw` | Queries remote foreign tables |
| Distributed transaction | Coordinates consistency across servers |
| Global FK | Requires distributed engine support or co-location |
| RPO/RTO | Recovery point and time objectives |
| `pg_partition_tree` | Inspects declarative hierarchy |
| `pg_inherits` | Parent/child catalog metadata |
| `pg_partitioned_table` | Partition strategy/key catalog metadata |
| `EXPLAIN` | Inspects query plans and pruning |
| `ANALYZE` | Refreshes planner statistics |

---

## Conclusion

**Partitioning, inheritance, and sharding are three distinct mechanisms—combinable where appropriate, but never interchangeable.**

**Declarative partitioning** divides a logical table into child partitions inside a single PostgreSQL cluster. It automates INSERT routing, enables partition pruning, and streamlines period-based retention. It fits large tables with clean access keys or lifecycles, yet **does not add writable primaries** and constrains PK/UNIQUE definitions to include the partition key.

**Table inheritance** creates parent-child relations via `INHERITS`. Parents can store rows directly, SELECTs normally include descendants, INSERTs do not auto-route, and unique/foreign keys/indexes do not span the tree automatically. It is a distinct feature once used for manual partitioning, not an older syntax equivalent for declarative partitioning.

**Sharding** spreads data across independent PostgreSQL servers/clusters. It scales write throughput and storage capacity, at the cost of routing complexity, cross-shard JOINs, global constraint enforcement, distributed transactions, per-shard HA, coordinated backups, and rebalancing. Specific distributed PostgreSQL solutions automate pieces of this stack, though exact guarantees must be verified per product and version.

Start architectural choices from **actual workload, consistency requirements, query shapes, and operational capacity**—not raw partition or server counts. Understanding what each technique actually solves lets you apply partitioning inside a cluster, inheritance where parent-child semantics are genuinely wanted, and sharding when horizontal multi-machine scaling is truly required.
