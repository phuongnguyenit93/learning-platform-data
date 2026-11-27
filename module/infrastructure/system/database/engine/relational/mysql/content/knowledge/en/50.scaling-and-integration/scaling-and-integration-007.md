# Partitioning Data by Tenant/Key and Distinguishing Sharding from Partitioning

As MySQL data grows, a large table can become difficult to manage, query, or maintain within a single server's resource limits. Two techniques are commonly discussed: **partitioning** and **sharding**. Partitioning splits a table into multiple partitions managed by the same MySQL instance; sharding distributes subsets of data across multiple independent MySQL instances or clusters. Both techniques can coexist in the same system, yet they solve different problems.

Choosing a tenant ID or a business key as the partitioning/sharding key determines which data resides together, which queries require routing, and which operations can run inside a local transaction. A good shard key keeps frequent queries touching few servers, distributes load relatively evenly, and keeps related transactions within the same data scope. A poor shard key can create hot shards, fan-out queries, difficulties enforcing uniqueness, or costly expansion.

This lesson belongs to the **Scaling the System** chapter of the DATABASE_MYSQL module. The module covers table design, data types, keys, SQL queries, indexes, transactions, concurrency control, query tuning, privileges, backups, and relational database operations. Examples focus on MySQL 8.0 and InnoDB; verify partitioning limits, DDL behavior, and replication behavior on your actual deployed version.

After this lesson, you will be able to:

- Distinguish single-instance partitioning from multi-instance sharding.
- Select a tenant ID or business key as a partition key/shard key.
- Compare range, hash, and directory-based partitioning/sharding.
- Design primary keys, unique keys, and indexes for multi-tenant data.
- Use partition pruning and inspect it with `EXPLAIN PARTITIONS`.
- Identify hot tenants, hot keys, skew, and queries that must fan out.
- Understand how sharding affects transactions, joins, and uniqueness.
- Plan data migration, resharding, and post-cutover verification.

## 1. Why Split Data?

When tables grow to hundreds of millions of rows or workloads serve many tenants, several issues can emerge:

- Indexes and data consume significant storage, lengthening backup/restore times.
- Queries targeting a single tenant still scan overly large data ranges.
- A single server nears its CPU, memory, IOPS, or network limits.
- One large tenant generates far more read/write load than other tenants.
- Maintaining and purging old data becomes time-consuming.
- One workload degrades latency for other workloads.

Splitting data can improve locality, lifecycle management, and resource distribution. However, it also increases complexity across schemas, routing, migrations, backups, monitoring, and queries. Never split merely because a table is large; first measure bottlenecks and determine whether the split supports actual access patterns.

Questions to answer first:

1. Do common queries filter by tenant, customer, account, time, or another key?
2. Must a tenant's data be processed together within a transaction?
3. Is load balanced across tenants?
4. Could a single tenant grow large enough to need its own shard?
5. Are there system-wide aggregate queries or cross-tenant joins?
6. Is the goal table management, scan reduction, capacity growth, or load isolation?
7. Does the operations team have the capability to manage multiple MySQL instances and data migration workflows?

## 2. What Is Partitioning?

Partitioning splits a logical table into multiple physical partitions managed by the same MySQL Server. The application still accesses the table under a single name:

~~~sql
SELECT order_id, status
FROM sales.orders
WHERE tenant_id = 42;
~~~

MySQL determines which partitions to read based on the partitioning expression and query predicates. When the optimizer determines that certain partitions cannot contain matching rows, it can exclude them from the access plan. This mechanism is called **partition pruning**.

All partitions still belong to the same instance:

- Same server process and CPU resources.
- Same memory, buffer pool, and InnoDB management structures.
- Same storage subsystem and server I/O limits.
- Same instance failure domain.
- Same administrative privileges and database connections.

Thus, partitioning helps manage a large table and can reduce the amount of data scanned for suitable queries, yet it does not automatically distribute CPU or memory to other servers.

### 2.1. Common Partitioning Types

| Type | How it splits | Suitable use cases |
|---|---|---|
| `RANGE` | Splits by value ranges | Time-series data, IDs, or business thresholds. |
| `RANGE COLUMNS` | Splits by ranges of one or more columns | Date/time or column values without needing arithmetic expressions. |
| `LIST` | Splits by explicit lists of values | A predefined set of value groups. |
| `LIST COLUMNS` | Splits by lists of column values | Grouping by region code, category, or classification attribute. |
| `HASH` | Uses a hash expression to distribute rows | Needing relatively even distribution across a numeric value. |
| `KEY` | MySQL uses an internal hashing algorithm on key columns | Distributing by columns such as tenant ID, including supported string types. |

Choose the type based on how data is queried and managed. `RANGE` is typically advantageous for dropping old data by range; `KEY`/`HASH` are better suited when even distribution by key is needed. No single type automatically optimizes every query.

## 3. What Is Sharding?

Sharding splits data horizontally across multiple independent database instances or clusters. Each shard stores a subset of rows of the same logical data model. The application or a routing layer determines which shard to access.

Example four-shard system:

~~~text
                  Application
                     |
                Shard Router
          ___________|___________
         |           |           |
       Shard 0     Shard 1     Shard 2     Shard 3
      tenant A    tenant B    tenant C    tenant D
~~~

Each shard can have:

- Its own MySQL Server or its own HA cluster.
- Its own buffer pool, CPU, storage, and connection pool.
- A schema matching the other shards.
- Its own backups, replication, monitoring, and maintenance schedule.
- An assigned set of tenants or keys.

Sharding scales capacity and throughput by adding servers while isolating portions of load. In return, the application must route queries, handle cross-shard data, and manage uniform schemas across multiple shards.

A shard does not have to be a single server. In production, each logical shard is typically a primary/replica group or an HA cluster. Sharding splits data across groups; replication provides copies and availability within each group. The two concepts do not replace each other.

## 4. Comparing Partitioning and Sharding

| Criterion | Partitioning | Sharding |
|---|---|---|
| Scope | One table inside one MySQL instance | Multiple instances/clusters |
| Connection management | A standard single database endpoint | Router or routing logic |
| CPU/memory resources | Shared within one instance | Distributed across multiple servers |
| Partition pruning | Can skip irrelevant partitions | Router selects shard; each shard still optimizes internal queries |
| Transactions | InnoDB transactions within the same instance | Local transactions within a shard; cross-shard is more complex |
| Joins | Standard SQL joins across tables in the same instance | Cross-shard joins require fan-out or application-layer assembly |
| Uniqueness | Constrained by partitioned table unique key rules | Typically requires ID/registry design to enforce system-wide uniqueness |
| Capacity scaling | Still bounded by a single server | Can add shards to expand total resources |
| Operations | Managing partitions and DDL | Managing routing, rebalancing, multiple backups, and multiple topologies |

A table can be partitioned inside each shard. For example, an application shards tenants across eight shards; within each shard, the event table is partitioned by month for retention management. Have a concrete reason for combining both layers, as each layer adds complexity.

## 5. Choosing a Data Partitioning/Sharding Key

The data-splitting key (partition key or shard key) determines how rows are partitioned or routed. A good key typically has these traits:

- Appears in most critical queries.
- Stable, changing rarely or never after row creation.
- Sufficient cardinality to distribute load.
- Does not concentrate most data or writes onto a single value.
- Co-locates rows frequently accessed together in the same partition/shard.
- Aligns with business unique keys and transactions.
- Can be propagated consistently across application layers.

Do not pick a key merely because it is the existing primary key. A primary key optimizes identifying a row; a shard key optimizes routing and locality. Both roles can share the same column, though it is not required.

### 5.1. Tenant ID as the Key

For multi-tenant SaaS, `tenant_id` is often a natural choice because most business queries belong to one tenant:

~~~sql
SELECT order_id, status, total_amount
FROM sales.orders
WHERE tenant_id = 42
  AND order_id = 9001;
~~~

If all data for a tenant resides on the same shard, operations such as reading a tenant's customers, orders, and payments occur within one local database. This reduces fan-out queries and keeps many transactions within a single shard.

Advantages:

- Clear routing from authenticated requests.
- A tenant's data can be co-located.
- Easy to enforce per-tenant unique keys.
- A single tenant can be migrated to another shard without splitting the entire system.

Risks:

- A large tenant can become a hot tenant.
- A tenant can outgrow the capacity of its assigned shard.
- System-wide administrative queries must aggregate across many shards.
- If `tenant_id` is omitted from a query, the application may read the wrong data or scan too broadly.

### 5.2. Business Keys Such as Customer ID or Account ID

If workloads primarily access data by customer or account, that key can yield better locality than `tenant_id`. For instance, a customer analytics system might route by `customer_id`.

However, if a transaction frequently updates multiple customers belonging to the same tenant, the data may span multiple shards and business operations become distributed. Examine transaction units and common join queries before deciding.

### 5.3. Composite Keys

Some systems shard by tenant while identifying rows with tenant-local IDs. In that case, the logical key can be `(tenant_id, order_id)`.

~~~sql
CREATE TABLE sales.orders (
  tenant_id BIGINT UNSIGNED NOT NULL,
  order_id BIGINT UNSIGNED NOT NULL,
  customer_id BIGINT UNSIGNED NOT NULL,
  status VARCHAR(24) NOT NULL,
  total_amount DECIMAL(19,2) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (tenant_id, order_id),
  KEY idx_tenant_created (tenant_id, created_at),
  KEY idx_tenant_customer (tenant_id, customer_id)
) ENGINE=InnoDB;
~~~

Queries by tenant and order ID use both key components. When designing repositories, APIs, and cache keys, always carry `tenant_id` alongside the entity ID to avoid treating `order_id` as globally unique if it is only unique within a tenant.

## 6. Tenant Isolation Does Not Come Automatically from Partitioning/Sharding

Placing tenant data in separate partitions or shards does not automatically create a security boundary. A query with the wrong tenant can still read unauthorized data if the account has privileges and the SQL lacks proper filtering.

Required protective layers:

1. Derive `tenant_id` from the authenticated identity/context; never trust client-supplied values directly.
2. Require `tenant_id` in repositories/queries for tenant-scoped tables.
3. Use composite primary/unique keys when uniqueness applies only within a tenant.
4. Verify tenant ownership before entity-ID read/write operations.
5. Include `tenant_id` in cache keys, messages, audit logs, and background jobs.
6. Test cross-tenant access at both API and persistence layers.
7. Use separate database accounts/instances if stronger isolation is required.

Tenant-scoped query example:

~~~sql
SELECT order_id, status
FROM sales.orders
WHERE tenant_id = ?
  AND order_id = ?;
~~~

If querying only `WHERE order_id = ?`, a colliding ID across two tenants can return another tenant's data if the key is not globally unique. Partitioning is a data organization and access optimization technique, not a row-level security mechanism.

## 7. Partitioning by Tenant with `KEY`

MySQL `KEY` partitioning works well when distributing rows by one or more key columns. For example, all rows for the same tenant go into the same partition:

~~~sql
CREATE TABLE sales.orders_partitioned (
  tenant_id BIGINT UNSIGNED NOT NULL,
  order_id BIGINT UNSIGNED NOT NULL,
  external_ref VARCHAR(80) NOT NULL,
  status VARCHAR(24) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  PRIMARY KEY (tenant_id, order_id),
  UNIQUE KEY uq_tenant_external_ref (tenant_id, external_ref),
  KEY idx_tenant_created (tenant_id, created_at)
) ENGINE=InnoDB
PARTITION BY KEY (tenant_id)
PARTITIONS 16;
~~~

With `PARTITION BY KEY (tenant_id)`, MySQL uses an internal hash function to map `tenant_id` values to one of 16 partitions. Rows sharing the same `tenant_id` reside in the same partition of this table.

Notes:

- All 16 partitions still reside inside the same MySQL instance.
- Partition count is neither shard count nor CPU core count.
- Increasing partition count does not automatically make queries faster.
- When changing partition counts, MySQL may redistribute data and execute resource-intensive DDL.
- Verify partitioning limits, indexing, and support on your running version.

### 7.1. Unique Key Rules for Partitioned Tables

In MySQL, every unique key on a partitioned table must include all columns used in the partitioning expression. For example, if partitioning by `tenant_id`, both the primary key and every unique key must contain `tenant_id`.

In the example above:

- `PRIMARY KEY (tenant_id, order_id)` includes the partition key.
- `UNIQUE (tenant_id, external_ref)` also includes the partition key.

Adding `UNIQUE(order_id)` without `tenant_id` will be rejected by MySQL for that partition layout. This is a critical rule affecting ID and uniqueness modeling.

If the business requires `external_ref` to be globally unique across the entire system, a per-tenant unique key only guarantees uniqueness within each tenant. Across multiple shards, the database also cannot automatically enforce a global unique index across shards. You need globally unique IDs or an appropriate registry/constraint service.

## 8. Time-Based Partitioning with `RANGE COLUMNS`

Time-based partitioning is useful for event tables, logs, or data with monthly/quarterly retention. Example:

~~~sql
CREATE TABLE analytics.events (
  tenant_id BIGINT UNSIGNED NOT NULL,
  event_id BIGINT UNSIGNED NOT NULL,
  created_at DATETIME(6) NOT NULL,
  event_type VARCHAR(80) NOT NULL,
  payload JSON NOT NULL,
  PRIMARY KEY (tenant_id, created_at, event_id),
  KEY idx_tenant_created (tenant_id, created_at)
) ENGINE=InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
  PARTITION p_before_2026 VALUES LESS THAN ('2026-01-01'),
  PARTITION p2026q1 VALUES LESS THAN ('2026-04-01'),
  PARTITION p2026q2 VALUES LESS THAN ('2026-07-01'),
  PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
~~~

`RANGE` partitions are defined by upper bounds; the first partition catches all values below the first boundary. `p_future` receives data from the preceding boundary onward.

Queries should filter using direct time ranges on the partition key:

~~~sql
SELECT event_id, event_type
FROM analytics.events
WHERE created_at >= '2026-01-01'
  AND created_at < '2026-02-01';
~~~

This range predicate gives the optimizer an opportunity to prune irrelevant partitions. Avoid wrapping the partition column in functions unnecessarily:

~~~sql
-- Typically harder to utilize range access/pruning than a direct predicate
WHERE DATE(created_at) = '2026-01-15'
~~~

Rewrite it as explicit start and end timestamps to keep the predicate sargable.

### 8.1. Impact on Unique Keys

In the `RANGE` example by `created_at`, every unique key must contain `created_at`. `PRIMARY KEY (tenant_id, created_at, event_id)` satisfies this rule.

This means `event_id` is not guaranteed unique across the entire table by this primary key alone. If the business requires `event_id` to be unique within a tenant across all dates, an additional mechanism is required—such as an unpartitioned registry table, globally generated IDs, or a different key design. You cannot add `UNIQUE(tenant_id, event_id)` because it lacks the partition column `created_at` and violates partitioning rules.

This is a key trade-off: time-based partitioning simplifies retention, yet can change how uniqueness is expressed.

## 9. Partition Pruning and Inspecting Execution Plans

Partition pruning is the optimizer's ability to skip partitions guaranteed not to contain matching rows. It depends on the partitioning expression and the query's predicates.

Example:

~~~sql
EXPLAIN PARTITIONS
SELECT event_id, event_type
FROM analytics.events
WHERE created_at >= '2026-01-01'
  AND created_at < '2026-02-01';
~~~

The `partitions` column in the output shows which partitions the plan expects to access. When filtering directly on `created_at`, the optimizer can select only the partition covering that range.

If a query filters only on `event_type` with no predicate on `created_at`, it may have to access many or all partitions. Partitioning does not replace indexes. You still need appropriate indexes for the workload's filter, join, and sort predicates.

Verify:

- Does the query have a predicate on the partition key?
- Can the optimizer evaluate the predicate for pruning?
- Is the partition key wrapped in functions or unnecessary type casts?
- Are suitable indexes present inside the partitions?
- Does the number of accessed partitions actually decrease?
- Does query duration improve when measured on representative data?

Use `EXPLAIN` and measure actual timings; never draw conclusions solely from the number of partitions created.

## 10. Partition Lifecycle Management

An operational benefit of `RANGE` partitioning is dropping old data via partition operations instead of `DELETE`-ing millions of rows. Example:

~~~sql
ALTER TABLE analytics.events
DROP PARTITION p_before_2026;
~~~

This command removes all data in that partition. It is a destructive operation; confirm retention policies, backups, and legal holds before executing. Even though metadata operations can be faster than row-by-row `DELETE`s, the DDL can still require metadata locks and impact replication or active workloads.

When a `MAXVALUE` partition exists, to carve out a new range before new data arrives, reorganize the future partition:

~~~sql
ALTER TABLE analytics.events
REORGANIZE PARTITION p_future INTO (
  PARTITION p2026q3 VALUES LESS THAN ('2026-10-01'),
  PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
~~~

Schedule partition creation ahead of when it is needed. If new data exceeds the last partition boundary and no matching partition exists, inserts can fail.

Never drop a partition just because its name looks old. Check exact range boundaries, data inside the partition, and recovery plans before running DDL.

## 11. Tenant Sharding

With tenant sharding, a router maps `tenant_id` to a shard. Example shard map:

| Tenant | Shard |
|---|---|
| 1001 | mysql-shard-a |
| 1002 | mysql-shard-a |
| 2001 | mysql-shard-b |
| 3001 | mysql-shard-c |
| 4001 | mysql-shard-d |

Once a request is authenticated, the application reads `tenant_id` from the security context and looks up the shard map:

~~~text
tenant_id
    |
    v
Shard directory / routing map
    |
    v
shard_id
    |
    v
Shard DataSource or connection pool
    |
    v
MySQL instance
~~~

One tenant lives on one shard in the simple model. Queries for that tenant need only one pool and one database. As a tenant grows, it can be migrated to another shard or subdivided by a sub-key if business logic permits.

Never take a shard ID directly from an unauthenticated client parameter. The router must determine the shard from the authenticated tenant and a system-managed mapping.

### 11.1. Shard Directory

There are two common ways to route:

- Compute the shard from a hash function of the shard key.
- Look up a directory/map to determine which shard owns the key.

Direct hashing is simple, but changing shard counts can relocate many keys. A directory is more flexible because individual tenants or key groups can move without changing a global formula, at the cost of managing and caching the mapping.

If using a directory, define:

- The authoritative data source for the mapping.
- Caching and invalidation when a tenant moves shards.
- Mapping versioning to prevent requests from using stale routes.
- Procedures to update mappings synchronously with data cutover.
- Resilience when the directory is unreachable.

## 12. Hash Sharding, Range Sharding, and Directory-Based Sharding

| Approach | Distribution method | Advantages | Risks |
|---|---|---|---|
| Range | Key ranges assigned to shards | Easy range routing, ordered locality | Hot ranges, skew when keys grow sequentially |
| Hash | `Hash(key)` maps to shard | Relatively even distribution if key/hash fit | Hard range scans, changing shard counts can move many keys |
| Directory | Looks up key or tenant in a shard map | Flexible tenant/key movement | Directory requires HA, caching, and synchronization |
| Consistent hashing/virtual buckets | Keys map to virtual buckets, buckets map to shards | Reduces data movement when adding shards | Requires careful bucket map and migration management |

### 12.1. Modulo Hashing

Simple example:

~~~text
shard_id = hash(tenant_id) % 4
~~~

Increasing from 4 shards to 5 changes the modulo output for many tenants; most data may need to move. This is why plain modulo hashing is difficult to scale when topology changes frequently.

### 12.2. Virtual Buckets

You can create more logical buckets than physical shards:

~~~text
tenant_id -> hash -> virtual_bucket
virtual_bucket -> shard_id
~~~

For example, 1,024 logical buckets distributed across 8 shards. When adding a shard, the system moves only a selected subset of buckets instead of recomputing every tenant against the new shard count.

Virtual buckets do not move data automatically. You still need a process to copy, reconcile, switch routes, and handle concurrent writes during migration.

## 13. Hot Tenants, Hot Keys, and Data Skew

A good hash function cannot balance load on its own if one tenant generates far more traffic than others. For instance, 1% of tenants may account for 70% of requests or data. If those tenants land on the same shard, that shard becomes a bottleneck even if total storage is evenly distributed.

Monitor per shard and per tenant:

- Row counts and table/index storage size.
- Read/write rates, QPS, and bytes transferred.
- CPU, memory, IOPS, and disk latency.
- Connection counts, active transactions, and lock waits.
- Replica lag and binary log growth.
- p95/p99 query latency.
- Top tenants by traffic and storage.

Mitigations for hot tenants:

- Move large tenants to dedicated shards.
- Sub-partition a tenant by a sub-key such as `account_id`, `region`, or `project_id` if business logic allows.
- Cache hot read data with clear invalidation policies.
- Offload analytical workloads from the transactional database.
- Throttle or rate-limit tenant background workloads.
- Add read replicas or reader groups if the consistency model permits.

Never split a single tenant across multiple shards if that tenant's transactions must atomically update data spanning those parts without proper coordination mechanisms.

## 14. Designing Indexes and Queries for Shard Keys

The shard key should generally lead indexes serving per-tenant queries. Example:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON sales.orders (tenant_id, status, created_at);
~~~

Corresponding query:

~~~sql
SELECT order_id, total_amount
FROM sales.orders
WHERE tenant_id = ?
  AND status = ?
  AND created_at >= ?
ORDER BY created_at DESC
LIMIT 100;
~~~

Composite indexes follow the leftmost prefix rule. Column ordering must match actual predicates, sorts, and cardinality. Do not prepend `tenant_id` to every index out of habit if that index does not serve a specific query or constraint.

With sharding, the router selects the shard first, and then MySQL's optimizer selects indexes within that shard. Verify both steps separately:

1. Does routing select the exact single shard or minimal set of shards?
2. Does the query inside the shard use indexes and return an appropriate row volume?

If a query lacks the shard key, the system may have to broadcast it to every shard (scatter-gather). Results are then merged, sorted, or paginated at the application layer. This is resource-intensive and its latency is bound by the slowest shard.

## 15. Cross-Shard Queries, Joins, and Transactions

Sharding complicates cross-shard operations.

### 15.1. Cross-Shard Joins

Standard SQL `JOIN` works only across tables accessible within the same server. If two tables reside on different shards, the application must:

- Query each shard separately and merge results in code.
- Maintain replicated/denormalized copies so queries stay within one shard.
- Use a search/analytics service for cross-cutting aggregate queries.
- Revise the shard key so frequently joined data is co-located.

Fan-out queries must cap shard count, returned row count, timeouts, and merge memory. A query broadcast to 32 shards multiplies load by 32 and completes at the speed of the slowest shard.

### 15.2. Cross-Shard Transactions

Standard InnoDB transactions guarantee atomicity within a single MySQL instance. If a business flow updates two shards, two local transactions do not automatically form one global transaction.

XA/two-phase commit can be used in suitable environments, though it increases complexity, state hold duration, and operational overhead. Many systems adopt sagas, transactional outboxes, event-driven workflows, and compensating actions to coordinate distributed processes.

Good designs keep updates requiring atomicity within the same shard. If a business flow must span shards, explicitly define intermediate states, retries, deduplication, timeouts, and failure-handling behavior.

## 16. Global IDs and Uniqueness

Within one MySQL instance, `AUTO_INCREMENT` generates unique IDs per table. When splitting data across shards, two independent shards can generate identical `AUTO_INCREMENT` values.

Global ID design approaches:

- UUID/UUIDv7 or ULID generated in the application/library.
- Snowflake-style IDs combining timestamp, worker ID, and sequence.
- IDs with shard prefixes or pre-allocated per-shard ID ranges.
- A centralized ID allocation service, if that dependency is acceptable.

Each approach trades off index size, locality, time ordering, collision risk, and availability. Random UUIDs can fragment B-trees; time-ordered IDs improve locality but require careful generator and clock design.

Even with global IDs, retain local unique constraints to protect data integrity inside each shard. If business uniqueness depends on a system-wide value such as email, a registry or global uniqueness workflow is needed; local unique indexes alone are insufficient.

## 17. Moving a Tenant or Key to Another Shard

Resharding migrates a subset of data from a source shard to a target shard. Moving a tenant can proceed in stages:

1. Identify the tenant's dataset and dependencies.
2. Create matching schemas/indexes on the target shard.
3. Copy an initial snapshot.
4. Capture and apply ongoing changes occurring during copy via CDC, binlog, or controlled dual-write.
5. Reconcile row counts, checksums, and business invariants.
6. Switch the routing map to the target shard at a controlled cutover point.
7. Monitor error rates and latency post-cutover.
8. Delete source data only after the rollback window expires and backups/retention are verified.

If using dual-write, handle cases where a write succeeds on source yet fails on target or vice versa. Outbox/CDC plus reconciliation is generally easier to control than issuing two uncoordinated writes without deduplication.

### 17.1. Avoiding Split Ownership During Cutover

At any moment, it must be unambiguous which shard is the authoritative writer for the tenant. If both source and target accept writes simultaneously, data can diverge.

Migration states can be tracked in the directory:

| State | Routing |
|---|---|
| `SOURCE_ACTIVE` | Read/write on source shard |
| `COPYING` | Source accepts writes; changes are captured to target |
| `CUTOVER` | Briefly pause/coordinate writes, reconcile, and switch route |
| `TARGET_ACTIVE` | Read/write on target shard |
| `CLEANUP` | Source retains data only for rollback/retention window |

Exact states depend on the architecture. What matters is that the router, migration workers, and application share the same understanding of states and mapping versions.

## 18. Combining Partitioning and Sharding

An architecture can combine:

- Tenant sharding to distribute load across multiple MySQL instances.
- Time-based partitioning inside each shard to manage events/logs.
- Indexes by tenant and time to serve local queries.

Example:

~~~text
                    Tenant Router
                         |
             ____________|____________
            |            |            |
          Shard A      Shard B      Shard C
            |            |            |
        MySQL 8.0     MySQL 8.0     MySQL 8.0
            |            |            |
        events       events       events
        partitions   partitions   partitions
        by month     by month     by month
~~~

You do not need to partition every table. Partition only large event tables while keeping customer/order tables unpartitioned to support foreign keys and intra-shard transactions.

Notably, MySQL 8.0 InnoDB has an important limitation: user-partitioned tables do not support foreign keys and cannot be referenced by foreign keys from other tables. If a model relies heavily on foreign keys, evaluate carefully before partitioning those tables. Confirm exact limits against your deployed MySQL version.

## 19. Operations, Backups, and Schema Migrations

With multiple shards, operational tasks must be coordinated:

- Monitor the same metric and alert suite across every shard.
- Verify backups and restore tests independently for each shard.
- Manage uniform schema versions while allowing phased rollouts.
- Track shard maps, replica topologies, and tenant migration status.
- Monitor capacity growth and skew thresholds.
- Plan MySQL/Connector/J upgrades by shard batch.
- Ensure background jobs and crons do not run redundantly across every shard unnecessarily.
- Include shard ID, protected tenant ID, and request ID in logs.

Schema migrations must remain compatible during rolling deployments. One upgraded shard may run the new schema while another remains on the old schema. Application code must support both states during the rollout window, or traffic must be routed by schema version.

Never run heavy DDL simultaneously across all shards without evaluating load and metadata locks. Roll out in shard batches, observe results, and have a halt plan if latency or replication lag climbs.

## 20. Workflow for Choosing a Data-Splitting Strategy

Follow this workflow before deciding:

### Step 1: Measure the Workload

Collect query digests, top queries, QPS, read/write ratio, table/index sizes, tenant distribution, p95/p99 latency, CPU, IOPS, and replica lag.

### Step 2: Group Queries by Key

Determine what percentage of requests carry `tenant_id`, `customer_id`, `account_id`, time ranges, or run system-wide. Find the key present in most critical queries.

### Step 3: Identify Transaction Units

List tables commonly updated together. Choose a shard key that keeps atomic operations within the same shard whenever possible.

### Step 4: Evaluate Skew and Hot Keys

Measure row counts, storage, and traffic per tenant/key. Model the largest tenant, not just averages.

### Step 5: Try Partitioning Before Sharding if the Goal Is Table Management

If the bottleneck is retention or scanning a large table, test `RANGE`/`KEY` partitioning in staging and check partition pruning. If the bottleneck is instance-wide CPU/IO or independent scaling is needed, evaluate sharding.

### Step 6: Evaluate Cross-Shard Costs

Model joins, transactions, unique constraints, global reports, backups, migrations, and resharding. If many critical workflows require fan-out or cross-shard transactions, reconsider the shard key.

### Step 7: Prototype and Set Thresholds

Benchmark on production-like data distributions. Define thresholds for moving tenants, adding shards, throttling migrations, and rolling back.

## 21. Practice Exercises

### Exercise 1: Choosing a Shard Key for SaaS

A system has 10,000 tenants. Most requests query orders, customers, and invoices for a single tenant. A few tenants are hundreds of times larger than average. Propose a shard key, how to detect hot tenants, and a plan to move large tenants to dedicated shards.

### Exercise 2: Partitioning by Tenant

Create a test table with `PARTITION BY KEY(tenant_id) PARTITIONS 8`. Insert data for multiple tenants, and run queries with and without a tenant predicate. Use `EXPLAIN PARTITIONS` to observe which partitions are accessed.

### Exercise 3: Time-Based Partitioning

Create an event table partitioned by `RANGE COLUMNS(created_at)`. Write a time-range query and compare it against a query wrapping `DATE(created_at)`. Practice adding a new partition via `REORGANIZE` and verify data integrity.

### Exercise 4: Unique Keys and Partition Keys

Attempt to create a partitioned table with `UNIQUE(order_id)` while partitioning by `tenant_id`. Observe the error, then design `UNIQUE(tenant_id, order_id)`. Explain the difference between per-tenant uniqueness and system-wide uniqueness.

### Exercise 5: Simulating Shard Routing

Create four test databases or four separate schemas/endpoints. Implement a router mapping `tenant_id` to a shard. Verify tenant queries reach only the assigned shard and requests cannot specify another tenant to read unauthorized data.

### Exercise 6: Resharding a Tenant

Copy one tenant's data from shard A to shard B in a test environment. Simulate new writes during copy, apply the change log, reconcile data, and then switch the routing map. Verify zero data loss or duplication.

## 22. Pre-Production Partitioning/Sharding Checklist

- [ ] Workload measured and real bottleneck identified.
- [ ] Partition key/shard key chosen based on query and transaction patterns.
- [ ] Cardinality, load distribution, hot tenants, and data skew evaluated.
- [ ] Single-instance partitioning clearly distinguished from multi-instance sharding.
- [ ] Partitioned table unique key rules verified.
- [ ] InnoDB partitioned table foreign key limitations reviewed.
- [ ] Partition pruning verified using `EXPLAIN PARTITIONS`.
- [ ] Composite indexes designed around access patterns.
- [ ] `tenant_id` derived from authenticated context and enforced in required queries.
- [ ] Shard router has clear mapping, cache invalidation, and versioning.
- [ ] Global ID and uniqueness strategies defined.
- [ ] Fan-out queries bounded with result merging designed.
- [ ] Cross-shard transaction handling designed.
- [ ] Per-shard and per-tenant metrics exist to detect hotspots.
- [ ] Backfill, CDC/dual-write, reconciliation, and cutover workflows exist.
- [ ] Backup/restore and schema migrations tested on each shard.
- [ ] Rollback plan and post-resharding source retention window defined.
- [ ] Tenant isolation and accurate shard routing tested.

Partitioning splits a large table into parts managed by the same MySQL instance; sharding distributes data across multiple instances to scale resources and isolate load. `tenant_id` is often a natural shard key when business flows access data by tenant and need locality, yet large tenants, global queries, and cross-shard transactions must be accounted for. Choose the key from access patterns, verify partition pruning or routing with realistic data, and execute migrations with clear checkpoints, reconciliation, and cutover procedures.
