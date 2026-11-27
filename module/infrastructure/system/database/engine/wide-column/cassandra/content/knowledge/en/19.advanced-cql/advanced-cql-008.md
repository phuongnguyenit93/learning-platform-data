# Materialized View Creation, Update Rules, and Version Limits in Apache Cassandra

> **Chapter:** Advanced CQL  
> **Scope:** **Apache Cassandra** Materialized Views (MVs), focusing on CQL syntax, primary key and `WHERE` requirements, synchronization mechanics from the base table, safety limits, and version differences. Examples target Apache Cassandra 4.1/5.0 in a **lab with MVs enabled**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish a **base table** from a **materialized view**, understanding why a view is a physical storage table with a different primary key rather than just a saved `SELECT`.
2. Validate `CREATE MATERIALIZED VIEW` requirements: `SELECT`, `WHERE`, `PRIMARY KEY`, keyspace, and table properties.
3. Describe accurately how `INSERT`, `UPDATE`, `DELETE`, and TTL affect view data, and know what **cannot be written directly** to an MV.
4. Explain consistency limitations of base -> view updates, the initial build over existing data, and `nodetool viewbuildstatus`.
5. Interpret **experimental** notices, enable/disable flags, and limitations across Cassandra 3.x, 4.0, 4.1, and 5.0.
6. Walk through an MV lifecycle in CQL and choose an appropriate data modeling option for Java applications.

## 2. What Problem Do Materialized Views Solve?

Cassandra is a distributed wide-column database optimized for queries specifying a matching **partition key**. If the main orders table is keyed by `tenant_id` and `order_id`, looking up orders by `customer_id` lacks the base table's partition key access path.

A materialized view (MV) lets you define **an automatically maintained data table** derived from a base table, rearranging the partition key and clustering key to serve a different query pattern.

~~~text
             App writes to base table
                       |
                       v
  orders  PRIMARY KEY ((tenant_id), order_id)
                       |
                 updates MV
                       v
  orders_by_customer
  PRIMARY KEY ((customer_id), tenant_id, order_id)

Read by tenant_id             Read by customer_id
    -> orders                  -> orders_by_customer
~~~

**Difference from a direct CQL `SELECT`:** An MV actually stores data, writes SSTables, and runs replication/compaction like an internal table. An MV does not re-evaluate `SELECT` at read time. Consequently, each view adds **storage overhead and write cost**, and takes time to update whenever the base table changes.

### MVs vs. Alternatives

| Approach | Who Maintains Secondary Data? | Best Fit When | Main Limitation |
|---|---|---|---|
| App-managed denormalized table | Application or consumer/CDC | You need full control over lifecycle, retries, backfill, and drift checks | Must design idempotency and reconciliation yourself |
| Materialized view | Cassandra generates view mutations automatically | Research or systems explicitly accepting version-specific MV risks | Experimental; key/`WHERE` limits; lag and base-view divergence risk |
| SAI (Cassandra 5.0+) | Cassandra maintains storage-attached secondary indexes | Flexible filters on non-partition-key columns | Does not create a physical table with an arbitrary partition key |
| Query base by partition key | No secondary copy needed | Primary access path already knows the partition | Cannot serve arbitrary reverse lookups |

> **Product status:** Official Apache Cassandra 4.1 and 5.0 configuration docs classify MVs as **experimental** and **not recommended for production**; `materialized_views_enabled` defaults to `false`. The existence of MV syntax in CQL does not mean a Cassandra cluster enables it or considers it safe enough. The hands-on exercises below are intended for lab clusters.

## 3. Designing the Base Table for the Running Example

In a single-node lab (RF=1), create the keyspace and table:

~~~sql
CREATE KEYSPACE IF NOT EXISTS mv_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS mv_lab.orders (
    tenant_id text,
    order_id uuid,
    customer_id text,
    amount int,
    state text,
    PRIMARY KEY ((tenant_id), order_id)
);
~~~

In `orders`, each row is identified by `(tenant_id, order_id)`, with `tenant_id` as the partition key. A second query is needed: "Find orders for `customer_id`, without knowing `tenant_id` upfront."

Corresponding MV:

~~~sql
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_lab.orders_by_customer AS
    SELECT tenant_id, order_id, customer_id, amount, state
    FROM mv_lab.orders
    WHERE tenant_id IS NOT NULL
      AND order_id IS NOT NULL
      AND customer_id IS NOT NULL
    PRIMARY KEY ((customer_id), tenant_id, order_id)
    WITH comment = 'Lab: lookup orders by customer';
~~~

Key rules illustrated:

- The view resides in **the same keyspace** `mv_lab` as the base table.
- All base keys (`tenant_id`, `order_id`) **remain in the view's `PRIMARY KEY`**, even though their order changes.
- The view adds **exactly one non-base-PK column** (`customer_id`) to the primary key—here used as the new partition key.
- `WHERE` ensures **every component of the view's primary key is NOT NULL**.
- `SELECT` includes only base columns, covering all required keys.

`SELECT` used once the view is built and converged:

~~~sql
SELECT tenant_id, order_id, amount, state
FROM mv_lab.orders_by_customer
WHERE customer_id = 'customer-A';
~~~

No `ALLOW FILTERING` is needed because the **view's** partition key is supplied. However, if a single `customer_id` accumulates too many orders, the view partition can also grow large. Designing an MV does not exempt you from avoiding hot or oversized partitions.

## 4. Validity Checklist for CREATE MATERIALIZED VIEW

### 4.1. Requirements for SELECT

The `SELECT` clause in a view definition is subject to Cassandra restrictions:

- Only **existing columns from the base table** may be selected. No arithmetic expressions, aggregates, functions, casts, literals, or aliases like `SELECT amount * 2 AS total`.
- `SELECT *` is allowed **only if the base table has no static columns**. **Static columns cannot be included in an MV**, so `SELECT *` fails if the base table defines any static column.
- Do not use `ORDER BY`, `LIMIT`, or `ALLOW FILTERING` inside the view **definition's** `SELECT`.
- You cannot build a view from a join or subquery; the source is a single base table.

Invalid example:

~~~sql
-- INVALID: computed expression and alias in SELECT.
CREATE MATERIALIZED VIEW mv_lab.orders_by_total AS
    SELECT tenant_id, order_id, customer_id, amount * 2 AS doubled
    FROM mv_lab.orders
    WHERE tenant_id IS NOT NULL
      AND order_id IS NOT NULL
      AND customer_id IS NOT NULL
    PRIMARY KEY ((customer_id), tenant_id, order_id);
~~~

**Note:** When `SELECT` omits non-key columns, deleting an **unselected column** in the base table can trigger consistency issues in certain versions/scenarios involving repair or hints (issue CASSANDRA-13826). Section 9 explains why that design requires extra caution.

### 4.2. Requirements for PRIMARY KEY

Every view must define a `PRIMARY KEY` satisfying these principles:

1. Include **all** `PRIMARY KEY` components of the base table, both partition key and clustering columns.
2. Add **at most one column not in the base `PRIMARY KEY`** to the view's `PRIMARY KEY`, per official Apache Cassandra 5.0 limits.
3. May **reorder and reassign partition/clustering roles** among allowed components to create a new access path.
4. Columns included in the view's primary key must be part of the `SELECT` list and non-NULL for any row included in the view.

**Valid examples** for base `PRIMARY KEY ((tenant_id), order_id)`:

~~~sql
-- View key uses both base columns and adds customer_id.
PRIMARY KEY ((customer_id), tenant_id, order_id)

-- Reverses base keys only, adding no new column.
PRIMARY KEY ((order_id), tenant_id)
~~~

**Invalid examples:**

~~~sql
-- Invalid: omits order_id, which is part of the base key.
PRIMARY KEY ((customer_id), tenant_id)

-- Invalid: adds two non-base-key columns to the view key.
PRIMARY KEY ((customer_id, state), tenant_id, order_id)
~~~

Do not extrapolate these rules from documentation of third-party customized Cassandra forks. Always verify against **Apache Cassandra** and the exact version you operate.

### 4.3. Requirements for WHERE

`WHERE` in an MV definition follows different rules from an ordinary `SELECT`:

- Must guarantee that columns in the **view `PRIMARY KEY`** are non-NULL. The clearest way to review this is writing explicit `col IS NOT NULL` checks for **all** view key columns.
- A column **not in the base `PRIMARY KEY`** may only be constrained with `IS NOT NULL`; you cannot use value predicates like `state = 'PAID'` or `amount > 100` to create a general filtered MV.
- For columns belonging to the **base `PRIMARY KEY`**, certain predicates beyond `IS NOT NULL` may be allowed by CQL per version rules, while remaining valid and preserving non-null guarantees. This lesson uses `IS NOT NULL` throughout for clarity and verifiability.
- No **bind markers** `?` are permitted in the definition, since this is static DDL rather than a parameterized prepared `SELECT`.
- No `ALLOW FILTERING` is permitted to bypass syntax limits.

~~~sql
-- INVALID: state is not part of the base key,
-- so WHERE state = 'PAID' is not supported for this MV.
CREATE MATERIALIZED VIEW mv_lab.orders_paid_mv AS
    SELECT tenant_id, order_id, customer_id, amount, state
    FROM mv_lab.orders
    WHERE tenant_id IS NOT NULL
      AND order_id IS NOT NULL
      AND customer_id IS NOT NULL
      AND state = 'PAID'
    PRIMARY KEY ((customer_id), tenant_id, order_id);

-- INVALID: view PK contains customer_id but omits
-- the condition guaranteeing customer_id IS NOT NULL.
CREATE MATERIALIZED VIEW mv_lab.orders_bad_null AS
    SELECT tenant_id, order_id, customer_id, amount, state
    FROM mv_lab.orders
    WHERE tenant_id IS NOT NULL
      AND order_id IS NOT NULL
    PRIMARY KEY ((customer_id), tenant_id, order_id);
~~~

### 4.4. Keyspace and Table Property Rules

An MV must live in the **same keyspace** as its base table. Internally an MV is implemented like a table, so you can specify supported **table options** (`WITH comment`, compaction/caching, and other version-valid options). Do not assume every base table option can be copied to a view, or that a view automatically inherits all base options.

`IF NOT EXISTS` only suppresses errors when a **view with the same name already exists**; it **does not** compare or upgrade an existing definition. If a view of that name exists with a different `WHERE`/`PRIMARY KEY`/`SELECT`, the statement silently skips while leaving the wrong schema in place.

## 5. How Is an MV Maintained When the Base Table Changes?

A materialized view **is not a logical view that re-runs `SELECT` on every read**. The base table generates corresponding view mutations that must be delivered to the replicas owning the view's partitions. Since the view's partition key can differ from the base partition key, **the replica sets storing base and view rows can differ**.

~~~text
Application
   |
   | INSERT/UPDATE/DELETE into orders
   v
Base coordinator
   |
   v
Replicas of orders (by tenant_id)
   |
   | Inspect row state and view PK to create/replace
   v
Mutation for orders_by_customer
   |
   v
Replicas of view (by customer_id)
   |
   v
SELECT from view once view mutation takes effect
~~~

**View updates are asynchronous** relative to the write's success on the base table. An `INSERT` succeeding at the base table's consistency level **does not guarantee** an immediate `SELECT` on the view sees the row. If base/view nodes experience outages, network partitions, or dropped mutations, the view can lag or diverge and require deeper investigation.

### 5.1. INSERT: Rows Enter the View Only When Key Requirements Hold

~~~sql
INSERT INTO mv_lab.orders
    (tenant_id, order_id, customer_id, amount, state)
VALUES (
    'tenant-1',
    11111111-1111-1111-1111-111111111111,
    'customer-A', 150, 'NEW'
);

INSERT INTO mv_lab.orders
    (tenant_id, order_id, amount, state)
VALUES (
    'tenant-1',
    22222222-2222-2222-2222-222222222222,
    250, 'NEW'
);
~~~

Row `1111...` has a non-NULL `customer_id`, so it qualifies for the MV. Row `2222...` **lacks `customer_id`**, so it **does not appear in the view**, even though it exists in the base table.

~~~sql
SELECT * FROM mv_lab.orders
WHERE tenant_id = 'tenant-1';

SELECT * FROM mv_lab.orders_by_customer
WHERE customer_id = 'customer-A';
~~~

During hands-on tests, inspect the view after **the initial build finishes** and after allowing time for view mutations to propagate. Never treat a single `SELECT` missing a row as proof that it is safe to delete the base record.

### 5.2. Updating a Regular Column: View Keeps the Key, Updates the Value

~~~sql
UPDATE mv_lab.orders
SET state = 'PAID', amount = 175
WHERE tenant_id = 'tenant-1'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

`state` and `amount` are projected into the view, yet **not** part of the view `PRIMARY KEY`. Thus the same `(customer-A, tenant-1, order_id)` key reflects the new values once the view mutation arrives and takes effect. Queries reading base and view during the transition window can see different versions.

### 5.3. Updating a Column in the View PRIMARY KEY: The Row Relocates

~~~sql
UPDATE mv_lab.orders
SET customer_id = 'customer-B'
WHERE tenant_id = 'tenant-1'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

The base primary key stays the same, while the **view partition key changes**:

~~~text
Before: orders_by_customer(customer-A, tenant-1, 1111...) -> row

UPDATE base customer_id = customer-B
    |
    +-> delete/shadow view copy under old key customer-A
    +-> write view copy under new key customer-B

After convergence:
  customer-A -> order 1111... gone
  customer-B -> has order 1111...
~~~

Because these are **two distinct view keys**, never expect an atomic handoff across all clients reading the view. During propagation, readers may see brief lag, temporary missing rows, or stale entries. For business requirements demanding uniqueness and instant visibility, design an independently verified consistency mechanism.

### 5.4. Updating to NULL, DELETE, and TTL

If you set the extra view-key column to NULL, the row no longer satisfies the MV's `WHERE` clause and must be removed from the view:

~~~sql
UPDATE mv_lab.orders
SET customer_id = null
WHERE tenant_id = 'tenant-1'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

This deletes the column value via a tombstone in the base table; it does not alter `tenant_id` or `order_id`. When deleting **an entire base row** with `DELETE`, the corresponding view row must also be removed:

~~~sql
DELETE FROM mv_lab.orders
WHERE tenant_id = 'tenant-1'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

With TTL, base values expire according to TTL/tombstone rules, and the view must also reflect that the data is no longer valid. **Do not assume varying TTL mutations or `UPDATE`/`DELETE` combinations produce identical expiration timestamps across base and MV in every version.** Historical bugs in row liveness and repair are one reason MVs remain marked experimental.

### 5.5. Cannot Write Directly to an MV

~~~sql
-- INVALID: a view is read-only from CQL's perspective.
INSERT INTO mv_lab.orders_by_customer
    (customer_id, tenant_id, order_id, amount, state)
VALUES ('customer-C', 'tenant-1',
        33333333-3333-3333-3333-333333333333, 500, 'NEW');

-- INVALID: cannot update view data directly.
UPDATE mv_lab.orders_by_customer
SET amount = 500
WHERE customer_id = 'customer-A'
  AND tenant_id = 'tenant-1'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Applications must apply data changes through the **base table**. Every `SELECT` against an MV is independent of whichever consistency level the application used when writing to the base table.

## 6. CREATE VIEW on Existing Data: Initial Build

An MV can be created **after the base table already holds data**. Cassandra must **scan historical data to build** the initial view state while also tracking new writes arriving at the base table.

~~~text
Base already has 3 million rows
          |
CREATE MATERIALIZED VIEW
          |
          +---- backfill: scan base and generate view rows
          |
          +---- new mutations keep arriving at base
          |                   |
          |                   v
          |          generate view updates
          v
Initial build completes + view updates gradually converge
          |
Only now should apps depend on view results
~~~

In practice, check the **build status**:

~~~bash
nodetool viewbuildstatus mv_lab orders_by_customer
~~~

The command takes the form `nodetool viewbuildstatus <keyspace> <view>` and is documented in Apache Cassandra 5.0. Verify completion across all involved nodes with zero build errors—not merely that `CREATE MATERIALIZED VIEW` returned success. For large datasets, builds consume CPU/disk/network; Cassandra exposes `concurrent_materialized_view_builders` and `getconcurrentviewbuilders`/`setconcurrentviewbuilders`, though changing concurrency requires separate evaluation.

**Never rely on a single `COUNT` or spot `SELECT` to declare an MV complete.** On high-partition-count views, a full `COUNT` can be expensive and cannot by itself verify row-by-row accuracy.

## 7. ALTER and DROP MATERIALIZED VIEW

`ALTER MATERIALIZED VIEW` modifies **table options** supported by the running version—not the view's `SELECT`, `WHERE`, or `PRIMARY KEY`.

~~~sql
-- Valid: updates the view's comment option.
ALTER MATERIALIZED VIEW mv_lab.orders_by_customer
WITH comment = 'Lab view: query by customer';
~~~

Need to switch a view from `PRIMARY KEY ((customer_id), tenant_id, order_id)` to another partition key, or change its selected columns or filter? You must **design and build a new view** (or drop/recreate in a planned change), because `ALTER` cannot change those definition clauses.

~~~sql
-- Clean up the lab environment after testing.
DROP MATERIALIZED VIEW IF EXISTS mv_lab.orders_by_customer;

-- Only afterward drop the base table/keyspace if no longer needed.
~~~

`DROP MATERIALIZED VIEW` removes only the view and its view data; **it does not delete base table data**. Conversely, altering a base schema with dependent views can be restricted—especially dropping columns; never treat base `ALTER` operations as independent of views.

## 8. Limits and Changes Across Apache Cassandra Versions

MVs have a longer history than SAI, yet product maturity varies across releases. **Syntax introduced in Cassandra 3.0 does not mean it became production-ready in 4.x or 5.0.**

| Version Line | MV Capabilities and Status | Config / Syntax Notes |
|---|---|---|
| **3.0** | Materialized Views introduced in 3.x; design and consistency fixes evolved in later releases | Do not apply 5.0 examples/assumptions blindly to 3.0 |
| **3.11** | MVs already marked experimental; value filtering on regular columns tightened | Cassandra 3.11 NEWS notes **disabling value-based view filters on non-base-PK columns** |
| **4.0** | MVs remain experimental with creation warnings; creation rules tightened | Requires explicit base PK columns in the view and NOT NULL conditions; legacy `enable_materialized_views` used here |
| **4.1** | Apache docs advise **against production use**, disabled by default | `materialized_views_enabled: false` by default; parameter name changed from legacy |
| **5.0** | Still **experimental**, even though CQL supports CREATE/ALTER/DROP MV | `materialized_views_enabled: false` by default; verify `nodetool viewbuildstatus` and 5.0 doc limits |

### 8.1. Why Does the Exact Minor Version Matter?

MV bug fixes have touched **timestamps, row liveness, column deletions, and repair**. For instance, 4.x NEWS highlights edge cases around view-key column deletion during repair after upgrades, and **CASSANDRA-13826** involves deleting a base column omitted from the view's `SELECT`. When upgrading an older cluster with MVs, read `NEWS.txt` across **every intermediate version**, catalog exactly which views promote non-key columns into the view PK, and plan repair/rebuilds per release guidance.

**Do not conclude "Cassandra 5.0 fixed all MV bugs"** just because it is a newer release. In official 5.0 documentation, MVs are still marked experimental.

### 8.2. The MV Feature Flag and Lab Safety Boundaries

Sample configuration for a lab cluster **authorized to test experimental features**:

~~~yaml
# cassandra.yaml (Cassandra 4.1/5.0; lab illustration)
materialized_views_enabled: true
~~~

If left at the default `false`, `CREATE VIEW` will be rejected; inspect the returned error and node configuration. Never modify `cassandra.yaml` and restart arbitrarily in production. In a multi-node cluster, having some nodes enabled and others disabled simultaneously can break schema/update behavior; verify configuration uniformly across the cluster per operational procedures.

Because property names changed across generations, never copy 4.1/5.0 settings into 3.x/4.0 without checking version-specific documentation. On Cassandra 4.1/5.0, `materialized_views_enabled` **only allows creating MVs**—it does not turn MV updates into synchronous transactions with the base table.

## 9. Consistency Limits and Situations Requiring Extra Care

### 9.1. Base and View Do Not Form a Cross-Table ACID Transaction

Suppose:

~~~text
App: INSERT base order
      |
      v
Base replicas meet CL ACKs -> App receives SUCCESS
      |
      |   propagation lag / update delivery error
      v
View replicas later receive and apply mutation
      |
      v
App: SELECT from view -> order appears
~~~

Because a view can use a different partition key, a `LOCAL_QUORUM` write to the base table **does not mean** an immediate `LOCAL_QUORUM` read from the view will see the new write. Quorum rules apply to **a single table/replica set**, without turning into synchronous guarantees across two physical tables.

When nodes fail or during hints, repair, bootstrap, or version-bug edge cases, views can diverge longer than normal propagation time. Therefore, do not use MVs for requirements like **uniqueness constraints, immediately consistent financial balances, or mission-critical order state reads that cannot tolerate stale reads** without additional safeguards.

### 9.2. Risk of Deleting Columns Omitted from SELECT

Cassandra's official MV documentation notes limitation **CASSANDRA-13826**: deleting a base column **omitted from the view's `SELECT`** can shadow delayed mutations of other columns arriving via hints/repair. When a base table has an MV and the workload regularly deletes individual columns, this is a concrete design risk to evaluate; selecting all columns avoids that specific **unselected column** hazard, yet still does not make MVs strongly consistent.

Conceptual risk example:

~~~sql
-- Suppose the view only SELECTs tenant_id, order_id, customer_id,
-- omitting amount; example base operation:
DELETE amount
FROM mv_lab.orders
WHERE tenant_id = 'tenant-1'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Do not claim every version or every `DELETE` always corrupts the view. The issue is an **incompatibility scenario with delayed mutations**, not that every single delete breaks immediately.

### 9.3. Do Not Confuse Base Repair with Fixing Every View Divergence

Repair synchronizes replicas of a given table; because view mutations derive via custom base-to-view logic, you cannot assume `nodetool repair` on the base table always regenerates every previously dropped view mutation. Certain versions/configs support replaying view mutations during streaming; `materialized_views_on_repair_enabled` must be evaluated per version and data state. Never flip repair flags solely to cut load without understanding consistency risks.

If you suspect a view has diverged, inspect **version, build history, topology changes, node outages, hints, repairs, and delete/TTL patterns**. Remediation depends on the specific root cause and may involve base-view auditing, data reconciliation, or a planned view rebuild. Never "patch" by trying to `UPDATE` the view directly.

### 9.4. Execution Cost

| Impact | Cost Source | Observable Symptom |
|---|---|---|
| Slow writes or timeouts | Reading base row state to compute view mutations and writing to view replicas | Higher base write latency/timeouts |
| Extra disk usage | View stores rows/SSTables with its own replication and compaction | Higher disk utilization, compaction backlog |
| Hot view partitions | Poorly distributed view key, e.g., partitioning solely by `status` | Specific nodes/partitions absorb heavy read/write load |
| Long initial build | Scanning existing base data | Elevated CPU/disk/network; incomplete view until finished |
| Slow read convergence | Asynchronous propagation, node drops/hints/repair | View `SELECT` temporarily missing or showing stale data |

**Changing the view key does not automatically optimize data distribution.** For instance, a view partitioned by `state` with only `'NEW'`/`'PAID'`/`'FAILED'` creates massive partitions; choose partition keys based on cardinality and real query paths.

## 10. End-to-End Lab Walkthrough on Cassandra 4.1/5.0

**Prerequisite:** a lab cluster configured to permit MVs; never flip experimental flags in production. Use keyspace `mv_lab` and table `orders` from section 3.

### Step 1: Check Version and Node Status

~~~bash
nodetool version
nodetool status
~~~

Verify the exact parameter name in `cassandra.yaml` for your running version. Cassandra 4.1/5.0 normally requires `materialized_views_enabled: true` to run `CREATE MV` in a lab; if creation reports the feature is disabled, note the error and check the environment rather than altering clusters outside authorized scope.

### Step 2: Write Rows Before Creating the MV, Then Create the View

~~~sql
INSERT INTO mv_lab.orders
    (tenant_id, order_id, customer_id, amount, state)
VALUES ('tenant-1',
        11111111-1111-1111-1111-111111111111,
        'customer-A', 150, 'NEW');

INSERT INTO mv_lab.orders
    (tenant_id, order_id, amount, state)
VALUES ('tenant-1',
        22222222-2222-2222-2222-222222222222,
        250, 'NEW');

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_lab.orders_by_customer AS
    SELECT tenant_id, order_id, customer_id, amount, state
    FROM mv_lab.orders
    WHERE tenant_id IS NOT NULL
      AND order_id IS NOT NULL
      AND customer_id IS NOT NULL
    PRIMARY KEY ((customer_id), tenant_id, order_id)
    WITH comment = 'Lab view by customer';
~~~

This tests **initial build**: rows existing before `CREATE` must enter the MV if they satisfy `WHERE`.

### Step 3: Verify Build Completion Before Reading

~~~bash
nodetool viewbuildstatus mv_lab orders_by_customer
~~~

Once status confirms the build finished across the required nodes, check:

~~~sql
SELECT tenant_id, order_id, customer_id, amount, state
FROM mv_lab.orders
WHERE tenant_id = 'tenant-1';

SELECT tenant_id, order_id, customer_id, amount, state
FROM mv_lab.orders_by_customer
WHERE customer_id = 'customer-A';
~~~

**Expected upon convergence:** The view contains order `1111...` under `customer-A`; order `2222...` is absent because it lacks `customer_id`. While build or propagation is incomplete, results may not match yet.

### Step 4: Update Regular Columns and the View Key

~~~sql
UPDATE mv_lab.orders
SET amount = 175, state = 'PAID'
WHERE tenant_id = 'tenant-1'
  AND order_id = 11111111-1111-1111-1111-111111111111;

UPDATE mv_lab.orders
SET customer_id = 'customer-B'
WHERE tenant_id = 'tenant-1'
  AND order_id = 11111111-1111-1111-1111-111111111111;

SELECT order_id, customer_id, amount, state
FROM mv_lab.orders_by_customer
WHERE customer_id = 'customer-A';

SELECT order_id, customer_id, amount, state
FROM mv_lab.orders_by_customer
WHERE customer_id = 'customer-B';
~~~

**Expected upon convergence:** The old view entry under `customer-A` disappears; `customer-B` now holds order `1111...` with `amount=175` and `state='PAID'`. Repeat controlled checks in the lab to observe lag; never turn polling loops into an application consistency mechanism.

### Step 5: Bring a Previously Ineligible Row into the MV

~~~sql
UPDATE mv_lab.orders
SET customer_id = 'customer-B'
WHERE tenant_id = 'tenant-1'
  AND order_id = 22222222-2222-2222-2222-222222222222;

SELECT order_id, customer_id, amount
FROM mv_lab.orders_by_customer
WHERE customer_id = 'customer-B';
~~~

Row `2222...` now has `customer_id`, so it enters the view once the mutation is processed. Next test deletion:

~~~sql
DELETE FROM mv_lab.orders
WHERE tenant_id = 'tenant-1'
  AND order_id = 22222222-2222-2222-2222-222222222222;

SELECT order_id, customer_id, amount
FROM mv_lab.orders_by_customer
WHERE customer_id = 'customer-B';
~~~

After convergence, row `2222...` is gone from the view. Do not try `DELETE FROM mv_lab.orders_by_customer` since views are not directly writable.

### Step 6: ALTER Options, DROP When Finished with the Lab

~~~sql
ALTER MATERIALIZED VIEW mv_lab.orders_by_customer
WITH comment = 'Lab completed';

DROP MATERIALIZED VIEW IF EXISTS mv_lab.orders_by_customer;
~~~

Verify the base table still exists:

~~~sql
SELECT * FROM mv_lab.orders
WHERE tenant_id = 'tenant-1';
~~~

Every CQL step here can run in an isolated lab. If objects with the same names remain from an earlier session, `IF NOT EXISTS` does not check schema equality: inspect the actual table/view definitions before running `UPDATE`.

## 11. Using the Java Driver with Base Tables and Views

Java Driver 4.x sends normal CQL statements. The application writes to the **base table** and reads from the **view** via `SELECT`; there is no special API to manually "refresh an MV."

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.util.UUID;

public final class OrderQueries {
    // CqlSession is created and reused by the application.
    public static void updateState(
            CqlSession session, String tenantId, UUID orderId, String state) {
        SimpleStatement update = SimpleStatement.builder(
                "UPDATE mv_lab.orders SET state = ? " +
                "WHERE tenant_id = ? AND order_id = ?")
            .addPositionalValues(state, tenantId, orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .build();
        session.execute(update);
    }

    public static ResultSet findByCustomer(
            CqlSession session, String customerId) {
        SimpleStatement read = SimpleStatement.builder(
                "SELECT order_id, tenant_id, state " +
                "FROM mv_lab.orders_by_customer WHERE customer_id = ?")
            .addPositionalValue(customerId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(100)
            .build();
        return session.execute(read);
    }
}
~~~

**Example warning:** The `mv_lab` keyspace was created with RF=1, so `LOCAL_QUORUM` equals one replica in that lab. With higher RF, reading a view at `LOCAL_QUORUM` **still does not** guarantee seeing an immediate base write right away. For strict read-after-write, re-query the **base table by its primary key** or use a data architecture with explicit synchronization/reconciliation.

Configure local datacenter, timeouts, retries, and paging sensibly in the driver. Never issue `UPDATE`/`INSERT` directly to an MV; coordinate feature rollouts so applications do not depend on a view still undergoing initial build.

## 12. Interview Scenarios and Common Errors

| Scenario | Explanation and Resolution |
|---|---|
| `CREATE MV` reports feature disabled | Cassandra 4.1/5.0 disables MVs by default; check exact version/config and environment policy |
| `WHERE` lacks `NOT NULL` for a view PK column | Add explicit `IS NOT NULL` for **every** view key component |
| `PRIMARY KEY` omits a base key column | MV must include **all** base PK columns, including clustering columns |
| `PRIMARY KEY` adds two non-key base columns | Apache Cassandra MVs allow at most **one** non-base-PK column |
| `CREATE MV` uses `WHERE state='PAID'` when `state` is not in the base PK | Value filtering on regular base columns is disallowed; only `IS NOT NULL` per MV limits |
| Direct `INSERT` into MV | Views are read-only via CQL; write to the **base table** |
| Base write succeeds, but view `SELECT` misses the row immediately | Asynchronous propagation and initial build; base CL does not guarantee instant view visibility |
| Changing `customer_id` temporarily shows row under old/new key | View key moved and mutations to old/new keys are not a global atomic transaction |
| `ALTER MV` to change `PRIMARY KEY` | `ALTER` only updates options; changing keys/`WHERE` requires building a new view |
| Dropped MV, yet base data remains | `DROP MATERIALIZED VIEW` does not delete the base table |
| Running base repair assuming MV always matches | Data repair does not guarantee replaying every previously lost view mutation; verify explicitly |
| Wanting to enable MVs on a new 5.0 production cluster | Review official experimental warnings; prefer controlled alternatives |

### Self-Check

1. Base has `PRIMARY KEY ((company_id, shard), event_id)` and regular column `kind`. Which columns must an MV partitioned by `kind` include in its view `PRIMARY KEY`?
2. Can an MV add both `kind` and `severity` (both regular columns) to its `PRIMARY KEY`? Why or why not?
3. When updating `customer_id` from A to B, how many view key locations are affected?
4. Why does `LOCAL_QUORUM` when reading an MV not guarantee immediate read-after-write from the base table?
5. Why is `CREATE MATERIALIZED VIEW IF NOT EXISTS` not a schema migration tool?
6. Give a scenario where you must check `nodetool viewbuildstatus` before enabling Java queries against a view.

**Answer guide:** (1) `company_id`, `shard`, `event_id`, and `kind`; (2) No, due to the limit of at most one non-base-PK column; (3) Key A must be removed and key B must be added; (4) Base and view have separate replica sets and asynchronous propagation; (5) It does not compare against an existing definition; (6) When creating an MV on a table that already has data requiring an initial build.

## 13. Key Points to Remember

~~~text
Valid MV:
  SELECT picks base columns only, no aggregates/functions/static
  WHERE enforces IS NOT NULL for all view PK columns
  View PRIMARY KEY contains the entire base PK
  View PRIMARY KEY adds at most 1 non-base-PK column
  View lives in the same keyspace as the base table

Writing data:
  Write INSERT/UPDATE/DELETE to base
  Base mutation -> view mutation (can arrive later)
  Never write directly to MV, never equate base CL with view CL

Lifecycle:
  CREATE -> initial build -> check viewbuildstatus -> app reads view
  ALTER only changes options -> DROP view does not DROP base

Versions:
  Apache Cassandra 4.1/5.0: MV is experimental, disabled by default
  Older 3.x/4.x lines: always check NEWS and version-specific docs
~~~

Cassandra is designed around **partition keys and query-driven tables**; MVs are a secondary-table maintenance mechanism with limits and risks you must clearly understand. For production workloads demanding high consistency, compare the cost and control of application-managed denormalized tables, CDC/consumers with reconciliation, and SAI (when suitable for Cassandra 5.0), then choose according to consistency, query, and version requirements.

## References

- [Apache Cassandra 5.0 — Materialized Views](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/mvs.html) — `SELECT`, `WHERE`, `PRIMARY KEY`, `ALTER`/`DROP`, and CASSANDRA-13826 limits.
- [Apache Cassandra 4.1 — cassandra.yaml, materialized_views_enabled](https://cassandra.apache.org/doc/4.1/cassandra/configuration/cass_yaml_file.html) — experimental status and `false` default.
- [Apache Cassandra 5.0 — cassandra.yaml](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html) — production warnings, MV/repair settings.
- [Apache Cassandra 5.0 — nodetool viewbuildstatus](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/viewbuildstatus.html) — checking initial build progress.
- [Apache Cassandra 4.1 — Configuration parameter naming](https://cassandra.apache.org/doc/4.1/cassandra/configuration/configuration.html) — renaming `enable_materialized_views` to `materialized_views_enabled`.
- [Apache Cassandra NEWS (4.1 branch)](https://apache.googlesource.com/cassandra/+/refs/heads/cassandra-4.1/NEWS.txt) — experimental warnings, view creation rule changes, and legacy restrictions.
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html) — `INSERT`, `UPDATE`, `DELETE`, TTL, and timestamps.
