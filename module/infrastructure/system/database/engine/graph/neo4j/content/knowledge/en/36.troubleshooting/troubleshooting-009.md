# Indexes Not Ready or Not Selected by the Query Planner

A slow Cypher query does not necessarily mean Neo4j is “ignoring the index”. There are two very different problem categories: **the index cannot serve queries yet** because it is still populating or failed, and **the index is ready yet the query planner does not choose it** due to cost estimates, predicate types, data types, or query structure. Confusing the two leads operations teams to repeatedly drop and recreate indexes without improving performance—often increasing load and downtime.

This lesson belongs to the **Troubleshooting** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. Neo4j stores nodes, relationships, and properties in a **property graph**, uses Cypher to traverse relationships and paths, relies on indexes/constraints to accelerate lookups and enforce invariants, and integrates with applications via the Java Driver and Spring Data Neo4j. The focus here is identifying the true cause, measuring execution plans, and applying verified fixes rather than tuning queries by intuition.

After this lesson, you will be able to:

- Inspect `SHOW INDEXES` and distinguish `ONLINE`, `POPULATING`, `FAILED`, and failure messages.
- Read `EXPLAIN`/`PROFILE` to tell whether the planner uses an index seek, index scan, or label scan.
- Explain why an `ONLINE` index is still not chosen: selectivity, composite keys, functions on properties, index types, parameter types, predicates, and post-traversal cost.
- Distinguish range, text, full-text, point, lookup, vector, and relationship indexes at a practical usage level.
- Build safe runbooks for long-populating indexes, failed indexes, unexpected query plans, and post-deploy performance regressions.
- Integrate index checks into migrations, monitoring, and Java Driver / Spring Data Neo4j testing.

> **Scope:** examples target Neo4j 5.x and newer releases supporting the corresponding syntax; `SHOW INDEXES` columns, plan operator names, index providers, and full-text/vector features can differ across versions. Run admin/schema commands only on practice databases or through approved change procedures. This lesson does not require GDS.

## 1. Start from the Symptom, Not from DROP INDEX

A report saying “the index isn't working” can mean several distinct things:

| Observed symptom | Primary possibility | First check |
| --- | --- | --- |
| Index was just created, yet queries stay slow. | Index is still `POPULATING` or not ready yet. | `SHOW INDEXES` and population progress. |
| `SHOW INDEXES` reports `FAILED`. | Build failure or resource/data/provider failure. | `failureMessage`, logs, and disk/I/O. |
| Index is `ONLINE`, yet `PROFILE` shows a label scan. | Planner chose a scan due to lower cost or incompatible predicate. | `WHERE` predicates, cardinality, types, plan. |
| Query is fast for parameter A, slow for parameter B. | Skewed value distribution, fan-out, parameter types, or suboptimal plan. | Compare plans, `Rows`, and `DB Hits` across representative parameters. |
| Index appears in the plan, yet query remains slow. | Cost sits in expansion, sorting, aggregation, eager ops, or network. | Full `PROFILE`, not just the first operator. |
| Index works in staging, fails in production. | Differences in data, version, database, schema, stats, or load. | Confirm target database/environment and compare baselines. |
| Migration fails with uniqueness or index creation error. | Existing data violates constraint, lacks resources, or invalid DDL. | Specific error message and duplicate/missing data. |
| Text search query ignores a full-text index. | Full-text indexes are not auto-selected for plain `WHERE`. | Check the corresponding search procedure/API. |

**Safety rule:** never delete index files from the filesystem, never drop constraints to “test speed”, and never drop/recreate critical indexes without recording their names, owners, and recovery paths. A uniqueness constraint can own a backing index; changing it affects data integrity.

## 2. General Diagnostic Flow

~~~text
Slow query or suspected unused index
                    |
                    v
   Confirm database + query + parameters
                    |
                    v
      SHOW INDEXES by name/schema
                    |
       +------------+--------------+
       |            |              |
   POPULATING     FAILED         ONLINE
       |            |              |
       v            v              v
    Monitor     Inspect cause   EXPLAIN / PROFILE
   progress      + remediate       |
   and load                        v
                           +------+------+
                           |             |
                      Index not       Index
                        used           used
                           |             |
                           v             v
                    Check predicates  Find costly stage:
                     / types / cost   expand / sort /
                     / stats          aggregate / I/O
                           |             |
                           +------+------+
                                  |
                                  v
                     Re-measure on representative
                        data + record baseline
~~~

Any credible diagnosis must cite **evidence**: index name, state at measurement time, query text and parameter shape, plan, `Rows`, `DB Hits`, duration/p95, and post-change impact.

## 3. Reproducible Practice Dataset

We use two node labels and one relationship type:

~~~text
(:IndexDemoUser {
  tenantId, userId, emailNorm,
  displayName, active, bio
})
        |
        | [:INDEX_DEMO_PLACED]
        v
(:IndexDemoOrder {
  tenantId, orderId, createdAt,
  status, amountMinor
})
~~~

Conventions:

- `tenantId` isolates organization scope.
- `userId` and `orderId` are per-tenant business keys.
- `emailNorm` is the email normalized per application-approved rules.
- `createdAt` is the order placement timestamp.
- `INDEX_DEMO_PLACED` points **User → Order**.

Run the following setup statements only in a **test database where schema changes are permitted**; never use these labels for production data. The fixture uses `example.test` emails and fictional names.

### 3.1. Demo Constraints and Indexes

~~~cypher
CREATE CONSTRAINT idx_demo_user_key IF NOT EXISTS
FOR (u:IndexDemoUser)
REQUIRE (u.tenantId, u.userId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT idx_demo_order_key IF NOT EXISTS
FOR (o:IndexDemoOrder)
REQUIRE (o.tenantId, o.orderId) IS UNIQUE;
~~~

~~~cypher
CREATE RANGE INDEX idx_demo_user_tenant_email IF NOT EXISTS
FOR (u:IndexDemoUser)
ON (u.tenantId, u.emailNorm);
~~~

~~~cypher
CREATE RANGE INDEX idx_demo_order_tenant_created IF NOT EXISTS
FOR (o:IndexDemoOrder)
ON (o.tenantId, o.createdAt);
~~~

The two constraints enforce key-pair uniqueness when properties are non-null. **Standard uniqueness does not imply an existence constraint**: the application must still validate key presence or use existence/key constraints where supported by edition/version. Range indexes speed up property-based lookups; they do not automatically make every relationship traversal fast.

### 3.2. Load Nodes

~~~cypher
UNWIND [
  {
    tenantId:'T1', userId:'U01',
    emailNorm:'an@example.test',
    displayName:'An Nguyễn', active:true,
    bio:'Interested in graph databases'
  },
  {
    tenantId:'T1', userId:'U02',
    emailNorm:'binh@example.test',
    displayName:'Bình Trần', active:true,
    bio:'Learning Cypher and Java'
  },
  {
    tenantId:'T1', userId:'U03',
    emailNorm:'chi@example.test',
    displayName:'Chi Phạm', active:false,
    bio:'Connected data applications'
  },
  {
    tenantId:'T1', userId:'U04',
    emailNorm:'dung@example.test',
    displayName:'Dung Lê', active:true,
    bio:'Text search'
  },
  {
    tenantId:'T2', userId:'U01',
    emailNorm:'another@example.test',
    displayName:'An Other Org', active:true,
    bio:'Independent organization'
  }
] AS row
MERGE (u:IndexDemoUser {
  tenantId: row.tenantId,
  userId: row.userId
})
SET u.emailNorm = row.emailNorm,
    u.displayName = row.displayName,
    u.active = row.active,
    u.bio = row.bio;
~~~

~~~cypher
UNWIND [
  {orderId:'O01', userId:'U01',
   at:'2026-01-05T10:00:00Z', amount:125000, status:'PAID'},
  {orderId:'O02', userId:'U01',
   at:'2026-01-07T14:00:00Z', amount:34000, status:'PAID'},
  {orderId:'O03', userId:'U01',
   at:'2026-02-11T09:00:00Z', amount:99000, status:'OPEN'},
  {orderId:'O04', userId:'U02',
   at:'2026-01-22T08:00:00Z', amount:77000, status:'PAID'},
  {orderId:'O05', userId:'U02',
   at:'2026-03-01T15:00:00Z', amount:50000, status:'OPEN'},
  {orderId:'O06', userId:'U03',
   at:'2026-02-14T07:00:00Z', amount:12000, status:'CANCELLED'},
  {orderId:'O07', userId:'U04',
   at:'2026-03-12T12:00:00Z', amount:32000, status:'PAID'}
] AS row
MATCH (u:IndexDemoUser {
  tenantId:'T1',
  userId:row.userId
})
MERGE (o:IndexDemoOrder {
  tenantId:'T1',
  orderId:row.orderId
})
SET o.createdAt = datetime(row.at),
    o.amountMinor = row.amount,
    o.status = row.status
MERGE (u)-[:INDEX_DEMO_PLACED]->(o);
~~~

Verify the fixture:

~~~cypher
MATCH (u:IndexDemoUser)
RETURN u.tenantId AS tenantId,
       count(u) AS userCount
ORDER BY tenantId;
~~~

~~~cypher
MATCH (u:IndexDemoUser {tenantId:'T1'})
      -[r:INDEX_DEMO_PLACED]->
      (o:IndexDemoOrder {tenantId:'T1'})
RETURN count(r) AS relationships,
       count(DISTINCT o) AS orders;
~~~

On a fresh fixture, expect **T1 has 4 users, T2 has 1 user**, and **T1 has 7 relationships to 7 orders**. On such a tiny set, the planner may **deliberately pick a label scan as cheaper**; that is not proof an index is broken. To benchmark performance, use a large test dataset with realistic degree and property distributions.

## 4. Indexes Have a Lifecycle: Not Ready Yet vs. Not Chosen

Neo4j builds indexes asynchronously or across phases. When creating an index over existing data, population may not complete instantaneously.

### 4.1. Querying Index State

~~~cypher
SHOW INDEXES
YIELD name, type, entityType,
      labelsOrTypes, properties,
      state, populationPercent
RETURN name, type, entityType,
       labelsOrTypes, properties,
       state, populationPercent
ORDER BY name;
~~~

You can filter by a specific name:

~~~cypher
SHOW INDEXES
YIELD name, type, state, populationPercent
WHERE name = 'idx_demo_user_tenant_email'
RETURN name, type, state, populationPercent;
~~~

| State | Typical meaning | Action |
| --- | --- | --- |
| **`POPULATING`** | Neo4j is building the required index entries. | Monitor progress, I/O, CPU, disk, and errors; do not declare the index ready. |
| **`ONLINE`** | Index is ready for the queries and predicate types it supports. | Inspect the query plan next; `ONLINE` does not guarantee the planner selects it. |
| **`FAILED`** | Index failed to build or hit an error rendering it unusable. | Gather the failure message, logs, version, and resource state before acting. |

Some versions support `SHOW INDEXES YIELD failureMessage` to read errors:

~~~cypher
SHOW INDEXES
YIELD name, state, failureMessage
WHERE state = 'FAILED'
RETURN name, state, failureMessage;
~~~

If your running version does not expose a column, inspect `SHOW INDEXES YIELD *` and your version's docs rather than relying on memorized column names. Share error messages only in authorized operational channels, as they can contain technical details or sensitive data.

### 4.2. Is a Newly Created Index Immediately Ready?

Not always. On large graphs, index population takes time. If a deployment pipeline runs:

~~~text
CREATE INDEX
  -> Immediately route heavy traffic
  -> Slow queries or unexpected access plans
~~~

add a **bounded wait-and-verify `ONLINE` gate** before enabling features that depend on the index. On versions supporting it, Neo4j provides a helper procedure:

~~~cypher
CALL db.awaitIndexes(300);
~~~

This waits up to roughly 300 seconds per the procedure's contract. Never treat that timeout as a universal SLA for every index. A full-text or vector index over millions of records has completely different build time and space needs than a tiny range index.

**Gate criterion:** critical indexes are `ONLINE` **and** business queries exhibit acceptable plans and latency. Waiting for the procedure alone without checking live queries can still miss a planner skipping the index.

## 5. Runbook A — Index Staying in POPULATING Too Long

### 5.1. Confirm the Exact Index and Progress

Record:

- Database name and index name.
- Index type, label/type, properties, and index provider if visible.
- `state` and `populationPercent` across multiple timestamps.
- Elapsed population time, rate of change, and comparison to prior runs.
- Data/index size, free disk, CPU, I/O latency, and concurrent write rate.

If `populationPercent` climbs slowly yet steadily, it may simply be a large dataset. If it stalls or logs errors, investigate **root causes** rather than assuming failure merely because it has not reached 100 yet.

### 5.2. Categorize Possible Causes

| Category | Signals | What to check |
| --- | --- | --- |
| Large data volume | Many nodes or relationships to scan and index. | Check entity counts and historical population baselines. |
| Low disk space | Low free bytes, I/O errors, index goes `FAILED`. | Check volumes holding database/indexes/temp; add safe headroom. |
| I/O saturation | Deep disk queues, rising p95/p99 latency. | Correlate with imports, backups, write jobs, and storage limits. |
| CPU/memory pressure | GC pauses, OOM, throttling, or memory starvation. | Check actual container memory/page cache/CPU, not just host RAM. |
| Specialized index types | Full-text analyzers or vector dimensions/types have specific rules. | Verify syntax, provider, and indexed property values. |
| Concurrent writes | Ongoing imports mutate indexed properties mid-build. | Watch write rate, population throughput, and maintenance windows. |
| Storage/cluster | Slow volume/network/backend, uneven member behavior. | Inspect each server's health, volumes, and storage path. |

### 5.3. Safe Actions

1. Ensure adequate disk space and restorable backups before schema changes.
2. Weigh the impact of waiting vs. deferring features that depend on the index.
3. Temporarily throttle non-essential write/import jobs if approved and safe.
4. Collect logs to distinguish a genuine build error from slow ongoing progress.
5. Rebuild only after identifying the root cause and securing a maintenance window.
6. Once `ONLINE`, verify query plans and p95/p99 rather than checking percent alone.

**Do not:** delete index files directly, slash transaction log retention arbitrarily, loop `DROP/CREATE INDEX` while volumes are full, or drop constraint-backed indexes without understanding the impact.

## 6. Runbook B — Index in FAILED State

A `FAILED` state must be treated as an **evidence-backed schema incident**, not a vague “database is slow” symptom.

### 6.1. Collect State Before Changing Anything

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes,
      properties, state, failureMessage
WHERE state = 'FAILED'
RETURN name, type, entityType, labelsOrTypes,
       properties, state, failureMessage;
~~~

Also inspect the constraint catalog:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
~~~

An index backing a uniqueness/node-key constraint cannot be treated as a disposable secondary index. Indexes and constraints have ownership and lifecycle ties; inspect `owningConstraint` if your version exposes it, or cross-check the schema catalog.

### 6.2. Classify the Failure

- **Resource failure:** disk full, I/O error, memory pressure, file permissions, storage backend failure.
- **Schema/constraint failure:** duplicate data during uniqueness constraint creation, property violating requirements, or unsupported index usage.
- **Provider/configuration failure:** invalid index config or analyzer, version/provider/plugin mismatch, or migration error.
- **Operational failure:** process killed mid-build, mixed rollout versions, or recovery state requiring admin tools.

**Do not guess** the cause from `FAILED` alone. Read `failureMessage` and logs; if engine bugs or store corruption are suspected, follow Neo4j support procedures and preserve evidence rather than tampering with files.

### 6.3. Why Uniqueness Constraints Differ from Regular Indexes

Suppose two nodes exist:

~~~text
(:IndexDemoUser {tenantId:'T1', userId:'U01'})
(:IndexDemoUser {tenantId:'T1', userId:'U01'})
~~~

When creating:

~~~cypher
CREATE CONSTRAINT idx_demo_user_key IF NOT EXISTS
FOR (u:IndexDemoUser)
REQUIRE (u.tenantId, u.userId) IS UNIQUE;
~~~

constraint creation fails due to duplicate keys. In that case, **verify the key, preserve valid business data, and clean up duplicates carefully**—never swap in a regular index just to hide a uniqueness violation. A range index does not enforce uniqueness.

### 6.4. Conditional Index Rebuild

For a standalone regular index **confirmed not to belong to a constraint**, after backing up, checking load, and entering a change window, you may consider:

~~~cypher
// Example ONLY on a test database, once this regular index
// is confirmed not to back a constraint.
DROP INDEX idx_demo_user_tenant_email IF EXISTS;
~~~

~~~cypher
CREATE RANGE INDEX idx_demo_user_tenant_email IF NOT EXISTS
FOR (u:IndexDemoUser)
ON (u.tenantId, u.emailNorm);
~~~

This is **not** a blanket cure for every `FAILED` state. If the cause is a full disk, recreating fails again and leaves queries without an index plan in the meantime. Record schema, state, query plans, and impact before and after.

## 7. Distinguish “Index Selected” from “Index Actually Makes It Fast”

Neo4j's planner is a **cost-based planner**: it estimates row counts and costs for starting lookups, filtering, relationship expansion, sorting, and aggregation to pick a low-cost overall plan. An available index is not a command forcing the planner to use it.

Example:

~~~cypher
MATCH (u:IndexDemoUser {tenantId: $tenantId})
RETURN u.userId AS userId;
~~~

If nearly every user in the database belongs to one tenant, an index lookup may be no cheaper than a label scan with a filter. On a tiny fixture with a handful of nodes, a scan is even more sensible. Conversely, when one user out of millions has a specific `emailNorm`, an index seek is usually far better.

### 7.1. Common Plan Operators

| Operator / plan tendency | Meaning | What to inspect next |
| --- | --- | --- |
| `NodeIndexSeek` | Locates nodes via index on property predicates. | Returned rows, DB Hits, and whether it used the expected index. |
| `NodeUniqueIndexSeek` | Seeks via a uniqueness index where applicable. | Compare plan/cost with real queries after downstream filters. |
| `NodeIndexScan` | Scans index ranges/entries per planner strategy. | Is it scanning most of the index? |
| `NodeByLabelScan` | Scans all nodes of a label, possibly filtering afterward. | Label row count, selectivity, predicate/index compatibility. |
| `AllNodesScan` | Scans every node in the store. | Is a label or better starting point missing? |
| `RelationshipIndexSeek` | Locates relationships by property via an index. | Should the query really start from relationships? |
| `Expand(All)` / `Expand(Into)` | Traverses relationships from known nodes. | Fan-out, node degree, and intermediate rows. |
| `Filter` | Evaluates predicates on rows. | Are filters pushed close to the start? |
| `Sort` / `Top` | Sorts or picks top results. | Must it read and sort huge sets before `LIMIT`? |
| `Eager` / `Aggregation` | Materializes or aggregates inside the plan. | Memory and intermediate row counts, not just initial index. |

Operator names and runtimes vary across Neo4j versions; never build brittle scripts matching exact operator strings without testing. A label scan is not automatically a bug, and an index seek does not guarantee the entire query is fast.

## 8. Reading EXPLAIN and PROFILE Methodically

### 8.1. EXPLAIN: Inspect the Plan Without Executing the Query

~~~cypher
EXPLAIN
MATCH (u:IndexDemoUser)
WHERE u.tenantId = $tenantId
  AND u.emailNorm = $emailNorm
RETURN u.userId AS userId,
       u.displayName AS displayName;
~~~

Supply representative test parameter shapes, e.g., `tenantId = 'T1'` and `emailNorm = 'an@example.test'`. `EXPLAIN` reveals which index the planner intends to start on and estimated rows, though it provides **no actual runtime or actual `Rows`/`DB Hits`**.

### 8.2. PROFILE: Real Execution, Real Measurements

~~~cypher
PROFILE
MATCH (u:IndexDemoUser)
WHERE u.tenantId = $tenantId
  AND u.emailNorm = $emailNorm
RETURN u.userId AS userId,
       u.displayName AS displayName;
~~~

With `PROFILE`, inspect at least:

1. **Starting operator:** index seek, index scan, or label scan?
2. **`Estimated Rows` vs. `Rows`:** are cardinality estimates far off from reality?
3. **`DB Hits`:** which operator drives data-access cost?
4. **Rows after each `Expand`:** is there a supernode or fan-out explosion?
5. **Sort, aggregation, eager:** where do time and memory concentrate?
6. **Total time and application p95/p99:** is one isolated run representative?

`PROFILE` **executes the query**, so never run it on `DELETE`, `SET`, or production writes just to view cost outside a safe environment. Even for read queries, prefer a test database or safe window if the query might scan huge datasets.

### 8.3. Baselines Must Compare Like with Like

Before-and-after comparison table:

| Attribute | Before | After | Interpretation |
| --- | --- | --- | --- |
| Neo4j version / database | ... | ... | Confirm no unintended runtime/schema difference. |
| Index state | ... | ... | Record exact state in both runs. |
| Query text and parameter shape | ... | ... | Avoid comparing different queries or types. |
| `Rows` / `Estimated Rows` | ... | ... | Check cardinality estimation skew. |
| `DB Hits` | ... | ... | Internal storage work, not absolute latency. |
| Node/relationship counts | ... | ... | Different data scale justifies different plans. |
| p50/p95/p99 latency | ... | ... | Measure under equivalent concurrency. |
| CPU / page cache / disk latency | ... | ... | Separate infrastructure bottlenecks from query plans. |
| Business results | ... | ... | Confirm optimization did not alter semantics. |

Never compare a cold-cache first `PROFILE` run against a warm-cache second run and credit the new index for all gains. Query compilation, page cache, network, and GC all affect timings.

## 9. Which Predicate Matches Which Index Type?

An index serves only the predicates and access paths supported by its **index type**. You cannot create arbitrary indexes and expect the planner to turn every expression into a seek.

| Index type | Typical usage | Notes |
| --- | --- | --- |
| **LOOKUP** | Node lookup by label / relationship lookup by type. | Does not replace property indexes for selective property filters. |
| **RANGE** | Equality, range, and order on indexed properties when plan fits. | Composite order, data types, and expressions govern seek vs. scan. |
| **TEXT** | String matching with `CONTAINS`/`ENDS WITH` on supported versions. | Not full-text linguistic analysis or relevance scoring. |
| **POINT** | Spatial queries using point and spatial predicates. | Does not replace range indexes for general properties. |
| **FULLTEXT** | Tokenized text search and relevance ranking. | Typically invoked via procedures/APIs, not auto-used by plain `WHERE`. |
| **VECTOR** | Nearest-neighbor search over stored embeddings. | Does not generate embeddings or serve general equality/range. |

### 9.1. Equality on Indexed Properties

~~~cypher
MATCH (u:IndexDemoUser)
WHERE u.tenantId = $tenantId
  AND u.emailNorm = $emailNorm
RETURN u.userId AS userId;
~~~

This aligns with `idx_demo_user_tenant_email` in label and property order. With sufficient data and high selectivity, the planner can pick an index seek. On tiny fixtures, another plan can still be optimal.

### 9.2. Range Predicates with Temporal Values

~~~cypher
MATCH (o:IndexDemoOrder)
WHERE o.tenantId = $tenantId
  AND o.createdAt >= $fromTime
  AND o.createdAt < $toTime
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt
ORDER BY o.createdAt ASC
LIMIT 50;
~~~

Pass `$fromTime` and `$toTime` as Neo4j-driver-supported temporal types, or convert them carefully **without wrapping the indexed property itself in a function**. If the app passes strings and compares them to `DateTime` properties, verify conversions and results; never assume the two types compare identically.

### 9.3. Functions on Properties Can Prevent Index Seeks

Scan-prone example:

~~~cypher
MATCH (u:IndexDemoUser)
WHERE toLower(u.emailNorm) = $emailNorm
RETURN u.userId;
~~~

If data is already normalized in `emailNorm`, prefer:

~~~cypher
MATCH (u:IndexDemoUser)
WHERE u.tenantId = $tenantId
  AND u.emailNorm = $emailNorm
RETURN u.userId;
~~~

Why: indexes store property values, not automatically the outputs of arbitrary functions like `toLower(property)`. Wrapping a property in a function often prevents direct index seeks. Normalizing on write or maintaining a dedicated lookup property is usually cleaner for repeated lookups.

**Do not claim every function is “unindexable”:** engine capabilities and specialized indexes vary by version. Always **inspect the plan**, compare against a clean property-predicate variant, and ensure semantics stay identical.

### 9.4. NULL, Existence, and COALESCE

~~~cypher
MATCH (u:IndexDemoUser)
WHERE coalesce(u.emailNorm, '') = $emailNorm
RETURN u.userId;
~~~

`coalesce` changes the evaluated expression; the planner will not necessarily seek `emailNorm` as it would for direct equality. If email is mandatory, validate inputs and use supported existence/key constraints instead of injecting fallback empty strings in queries. If email is optional, define null semantics explicitly and measure the resulting plan.

Indexes and constraints may index only entries satisfying certain value conditions; **never assume `IS NULL` is always accelerated by a property index**. Check the index type and actual plan.

### 9.5. `OR` and Negations

~~~cypher
MATCH (u:IndexDemoUser)
WHERE u.emailNorm = $emailNorm
   OR u.active = true
RETURN u.userId;
~~~

`OR` across two distinct properties can push the planner toward broad plans, multi-branch unions, or skipping the expected index. Do not blindly rewrite every `OR` into `UNION`: doing so can alter deduplication, ordering, plans, and total cost. If testing a rewrite, verify `DISTINCT` semantics and benchmark on real data.

## 10. Composite Indexes: Property Order Matters

Index:

~~~cypher
CREATE RANGE INDEX idx_demo_user_tenant_email IF NOT EXISTS
FOR (u:IndexDemoUser)
ON (u.tenantId, u.emailNorm);
~~~

has order **`tenantId` then `emailNorm`**. This fits when the primary workload looks up emails **within a tenant**.

| Query | Interaction with the composite index |
| --- | --- |
| `tenantId = $t AND emailNorm = $e` | Usually ideal for seeking on both properties. |
| `tenantId = $t` | Can use the index prefix, depending on planner cost and stats. |
| `emailNorm = $e`, without `tenantId` | Not an ideal prefix seek for this index; planner may scan/filter or pick another index. |
| `tenantId = $t AND emailNorm STARTS WITH $p` | May support range/prefix search depending on version and plan. |
| `tenantId = $t AND toLower(emailNorm) = $e` | Function on the second property makes direct seeking less suitable. |

Not every query mentioning both properties uses the index. For instance, the planner may choose another index or a label scan if estimated cardinality is very large.

### 10.1. Querying Only the Trailing Property

~~~cypher
EXPLAIN
MATCH (u:IndexDemoUser)
WHERE u.emailNorm = $emailNorm
RETURN u.userId;
~~~

If **global** email lookup is an important, authorized use case (without breaking tenant isolation), you may need a separate index on `emailNorm` or a query identifying the tenant first. Keep in mind each extra index adds disk and write-update cost. **Never create a new index to support a global lookup if that query is actually missing a mandatory tenant authorization filter.**

### 10.2. Composite Indexes Do Not Solve Every ORDER BY

~~~cypher
MATCH (o:IndexDemoOrder)
WHERE o.tenantId = $tenantId
  AND o.createdAt >= $fromTime
RETURN o.orderId AS id,
       o.createdAt AS createdAt
ORDER BY o.createdAt DESC, o.orderId ASC
LIMIT 20;
~~~

Index `(tenantId, createdAt)` helps with the range predicate and ordering on `createdAt`. Yet `orderId` is a tie-breaker **not present in this index**; the planner may still need sorting or tie handling. Align pagination keys and indexes with real sort orders rather than assuming “having an index on `createdAt` handles everything”.

## 11. Low Selectivity: Sometimes a Label Scan Is the Right Choice

Suppose there are 10 million users and 9.9 million have `active = true`. Adding:

~~~cypher
CREATE RANGE INDEX idx_demo_user_active IF NOT EXISTS
FOR (u:IndexDemoUser)
ON (u.active);
~~~

does not guarantee this query becomes fast:

~~~cypher
MATCH (u:IndexDemoUser)
WHERE u.active = true
RETURN u.userId
LIMIT 100;
~~~

Because almost every record matches, going through an index barely cuts the work—and for an unordered `LIMIT 100`, the planner can often stop early with a scan anyway.

Illustrative **selectivity** formula:

\[
\text{selectivity}(P)
=\frac{\text{nodes matching predicate }P}
{\text{nodes in evaluated scope}}.
\]

When a predicate matches nearly all nodes, indexing a low-cardinality property adds little value. What counts as “selective enough” depends on the plan, resources, and real data; there is no universal percentage cutoff.

### 11.1. Uneven Scale and Distribution

In a multi-tenant system:

| Tenant | User count | Active ratio |
| --- | ---: | ---: |
| T1 | 100 | 90% |
| T2 | 10,000 | 90% |
| T3 | 2,000,000 | 99% |

The same query `WHERE tenantId = $t AND active = true` matches vastly different row counts per tenant. If cardinality estimates miss the giant tenant, a plan fine for T1 can perform poorly for T3. Benchmark across small, medium, giant, and skewed tenants.

**Security warning:** “dropping `tenantId` to look up faster” is both bad for performance and a data leak risk. Always enforce tenant/authorization filters from the authenticated context.

## 12. Do Not Confuse Lookup Indexes with Full-Text and Vector Indexes

### 12.1. Text Indexes and Substring Search

For practice, you can create:

~~~cypher
CREATE TEXT INDEX idx_demo_user_name_text IF NOT EXISTS
FOR (u:IndexDemoUser)
ON (u.displayName);
~~~

Illustrative query:

~~~cypher
MATCH (u:IndexDemoUser)
WHERE u.displayName CONTAINS $partOfName
  AND u.tenantId = $tenantId
RETURN u.userId AS id,
       u.displayName AS name
LIMIT 20;
~~~

A `TEXT` index can accelerate substring operators such as `CONTAINS`/`ENDS WITH` on supporting versions. Yet the planner may still choose another path when filtering by tenant or on tiny datasets. **Substring matching** is not equivalent to tokenized full-text search with linguistic analyzers and relevance scoring.

### 12.2. Full-Text Indexes Usually Require Explicit Procedures

~~~cypher
CREATE FULLTEXT INDEX idx_demo_user_fulltext IF NOT EXISTS
FOR (u:IndexDemoUser)
ON EACH [u.displayName, u.bio];
~~~

On versions supporting the procedure:

~~~cypher
CALL db.index.fulltext.queryNodes(
  'idx_demo_user_fulltext',
  $queryText
)
YIELD node, score
WHERE node.tenantId = $tenantId
RETURN node.userId AS userId,
       node.displayName AS name,
       score
ORDER BY score DESC
LIMIT 20;
~~~

Never expect `MATCH ... WHERE u.bio CONTAINS $term` to **automatically** use this full-text index. Full-text indexes use analyzers, tokenizers, and scoring; `CONTAINS` has different string-matching semantics.

**Privilege/isolation boundary:** filtering `tenantId` after the procedure returns does not stop the index from scanning cross-tenant entries internally; for strict tenant isolation or giant tenants, consider tenant-scoped search architectures, endpoint controls, and data inference risks.

### 12.3. Vector Indexes Are Not Equality Indexes

For nodes holding fixed-dimension numeric embeddings in `embedding`, on Neo4j versions supporting vector indexes:

~~~cypher
CREATE VECTOR INDEX idx_demo_user_embedding IF NOT EXISTS
FOR (u:IndexDemoUser)
ON (u.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 64,
    `vector.similarity_function`: 'cosine'
  }
};
~~~

Example vector query procedure on supporting versions:

~~~cypher
CALL db.index.vector.queryNodes(
  'idx_demo_user_embedding',
  20,
  $queryEmbedding
)
YIELD node, score
RETURN node.userId AS id, score
ORDER BY score DESC;
~~~

This assumes `$queryEmbedding` matches the stored embeddings' dimensions, type, and normalization. Creating the index does not generate vectors automatically. Newer Neo4j versions may add native Cypher vector search syntax; check your deployed version's docs before coding. Never treat “the planner didn't use a range index” in a nearest-neighbor query as the same problem.

### 12.4. Point Indexes and Spatial Data

For distance/region filtering, you need a `POINT` index and spatial predicates instead of range indexes on longitude/latitude strings. Stored `point` values must use valid spatial types and consistent coordinate reference systems (CRS). An `ONLINE` index cannot fix wrong results caused by mixing geographic and Cartesian coordinates.

## 13. Relationship Property Indexes: Use the Right Starting Point

Neo4j supports indexing **relationship properties** depending on version. For example, if purchase edges carry `channel` or `createdAt` and queries search across all edges:

~~~cypher
CREATE RANGE INDEX idx_demo_rel_channel IF NOT EXISTS
FOR ()-[r:INDEX_DEMO_PLACED]-()
ON (r.channel);
~~~

Our fixture does not populate `r.channel`, so this index is not meaningful to benchmark here without real channel data.

Example query:

~~~cypher
MATCH (u:IndexDemoUser)
      -[r:INDEX_DEMO_PLACED]->
      (o:IndexDemoOrder)
WHERE r.channel = $channel
RETURN u.userId, o.orderId
LIMIT 50;
~~~

If searching across all relationships for a very rare `channel`, a relationship index helps. However, if the app already pinpoints one user by key and that user has only a few orders, **expanding edges from that user** can be much cheaper than scanning relationships by channel and joining back. The cost planner has good reason to skip the relationship index in that case.

**Important:** a relationship index does not turn relationships into nodes or change edge direction. Cypher still requires the exact type and arrow direction, and edge property predicates remain distinct from node property predicates.

## 14. Why Is an ONLINE Index Still Not Selected?

This is the core of the second problem category. Check in priority order:

### 14.1. Index Belongs to Another Database or Label

An index with the expected name on staging does not guarantee it exists in production. Queries may also target the wrong label or property:

~~~cypher
// Index exists on :IndexDemoUser(emailNorm)
// yet the query filters on a differently named property.
MATCH (u:IndexDemoUser)
WHERE u.email = $email
RETURN u.userId;
~~~

`email` is not `emailNorm`. The query is syntactically valid yet cannot use the `emailNorm` index for that predicate. Verify:

- Which database the session/driver connects to.
- Labels/types in the index vs. the query.
- Property names, casing, and escaping rules.
- Whether the index is a node or relationship index.
- That the index is genuinely `ONLINE` in the queried database.

### 14.2. Predicate Incompatible with the Index

Common patterns to inspect:

- `toLower(n.property) = ...`, `trim(n.property) = ...`, or `coalesce(...)`.
- Comparing numbers against strings due to Java/JSON type mismatches.
- `CONTAINS`/`ENDS WITH` without a compatible index type.
- Full-text search attempted through plain Cypher `WHERE`.
- Arithmetic on properties like `n.price * 1.1 > $x`.
- Checking list membership in ways the index does not cover.
- `OR`/`NOT` across multiple properties widening candidate sets.

Never apply a rigid rule like “any function forces a scan” across all versions. Test every hypothesis with `EXPLAIN`/`PROFILE`.

### 14.3. Result Set Too Broad

An index seek offers no benefit when almost all nodes match or massive property stores must be read. The planner may choose a scan quite sensibly.

### 14.4. Cardinality, Statistics, or Cached Plans

Neo4j relies on cardinality estimates and statistics for planning. After a huge import, a bulk delete/merge migration, or creating a new index, statistics or cached plans may not immediately match the new distribution.

Some versions trigger **query replanning** when statistics shift sufficiently or per cache policy, and provide admin mechanisms to clear query caches. **Never clear caches blindly as a first step**, as forcing recompilation across live traffic spikes CPU and latency; verify version behavior, evidence, and safe timing first.

### 14.5. The Index Is Used, Yet the Cost Comes Afterward

~~~cypher
MATCH (u:IndexDemoUser {
  tenantId:$tenantId,
  emailNorm:$emailNorm
})-[:INDEX_DEMO_PLACED]->(o:IndexDemoOrder)
RETURN o.status AS status,
       count(o) AS total
ORDER BY total DESC;
~~~

An index finds the user instantly, yet if that user is a **supernode with millions of orders**, expansion and aggregation are the real bottleneck. Adding a second index on email will not shrink the edges traversed afterward.

Never stop reading the plan at the first `NodeIndexSeek`. Inspect `Rows`/`DB Hits` at `Expand`, `Aggregation`, and `Sort`, and evaluate data modeling, time-bounded queries, or pre-aggregated summaries if business rules permit.

## 15. Step-by-Step Workflow for Unexpected Query Plans

### Step 1 — Lock Down the Query and Parameters

Capture the **PII-redacted** query text, data case, parameter shapes/types, and expected result count. In multi-tenant systems, note typical data distributions without pasting sensitive IDs onto shared dashboards.

### Step 2 — Read the Exact Catalog

~~~cypher
SHOW INDEXES
YIELD name, type, entityType,
      labelsOrTypes, properties, state
WHERE state = 'ONLINE'
RETURN name, type, entityType,
       labelsOrTypes, properties, state
ORDER BY name;
~~~

Confirm the index has the **right type** and lives in the active database.

### Step 3 — EXPLAIN First, PROFILE Second

Compare semantically equivalent query variants:

~~~cypher
// Option A: function on the property.
EXPLAIN
MATCH (u:IndexDemoUser)
WHERE u.tenantId = $tenantId
  AND toLower(u.emailNorm) = $emailNorm
RETURN u.userId;
~~~

~~~cypher
// Option B: property normalized on write.
EXPLAIN
MATCH (u:IndexDemoUser)
WHERE u.tenantId = $tenantId
  AND u.emailNorm = $emailNorm
RETURN u.userId;
~~~

Treat the two options as equivalent only if **all stored `emailNorm` values already follow the normalization rule** and parameters are normalized identically. If mixed-case or null values exist in the store, Option B returns different results than A; migrate and test before switching queries.

### Step 4 — Measure Selectivity and Fan-Out

Sample checks on a fixture (**never run repeated full counts indiscriminately on production**):

~~~cypher
MATCH (u:IndexDemoUser {tenantId:$tenantId})
RETURN count(u) AS tenantUsers;
~~~

~~~cypher
MATCH (u:IndexDemoUser {
  tenantId:$tenantId,
  emailNorm:$emailNorm
})
RETURN count(u) AS matchingUsers;
~~~

~~~cypher
MATCH (u:IndexDemoUser {
  tenantId:$tenantId,
  userId:$userId
})-[:INDEX_DEMO_PLACED]->(o:IndexDemoOrder)
RETURN count(o) AS outgoingOrders;
~~~

These counts tell you whether the index narrows down to a few nodes while traversal is costly, or whether the filter matches nearly the entire tenant.

### Step 5 — Make the Minimal Intervention

Fix in priority order:

1. Label, property, tenant, or data-type bugs.
2. Predicates blocking seeks (where a semantically equivalent form exists).
3. Composite index property order vs. query patterns, backed by workload measurements.
4. Queries narrowing node sets before relationship expansion.
5. Stats/replanning, index hints, or new indexes **only when supported by evidence**.

### Step 6 — Re-Verify

Compare plans, `Rows`, `DB Hits`, p95/p99, and business correctness. If a giant tenant regresses, never ship the change just because small test tenants got faster.

## 16. Index Hints: A Verification Tool, Not a Magic Wand

Neo4j Cypher supports index hints in appropriate cases. Using our demo range index:

~~~cypher
MATCH (u:IndexDemoUser)
USING INDEX u:IndexDemoUser(tenantId, emailNorm)
WHERE u.tenantId = $tenantId
  AND u.emailNorm = $emailNorm
RETURN u.userId AS userId;
~~~

This is a **planner hint**: it does not create a new index, fix a `FAILED` index, make an incompatible predicate indexable, or guarantee faster execution. When a hint cannot be satisfied (mismatched index, type, or predicate), Cypher may reject the query or fail to produce the hoped-for plan depending on version.

Consider long-term hints only when:

- The exact index is `ONLINE` across every environment where code runs.
- The bad automatic plan is reproducible after checking stats/data and ruling out parameter differences.
- The hinted plan achieves better latency and load across diverse data slices.
- Tests guard against schema changes or unready indexes during deployments.
- An owner is assigned to update hints when schemas evolve or Neo4j upgrades.

A hint can **lock a query onto one index** even as data distribution shifts. Today's cost-based planner choice may beat last year's hint; never use hints to mask modeling or CPU/I/O issues.

## 17. When Adding Indexes Actually Slows the System Down

Every index carries costs:

| Cost | Manifestation |
| --- | --- |
| Storage footprint | Extra index store size, population/rebuild peaks, heavier backups/restores. |
| Write amplification | Neo4j updates indexes whenever indexed properties/relationships change. |
| Index population | Consumes CPU, I/O, and time; competes with live traffic. |
| Schema operations | Requires migrations, state monitoring, and failure recovery plans. |
| Planning overhead | More access paths to evaluate; requires plan governance on big changes. |

For example, creating 12 indexes across every property “just to be safe” forces node-creation transactions to maintain a dozen structures—raising I/O and write latency even when only two queries use them.

### 17.1. Pre-CREATE Checklist

- Is there a **specific slow query** with a compatible predicate?
- Is the index duplicated or already covered by an existing index or constraint?
- Are record counts, selectivity, and per-tenant distributions representative?
- Do you need a node, relationship, text, full-text, point, or vector index?
- Is there enough disk headroom for population and backups?
- How much does write cost increase in benchmarks?
- If the index goes `FAILED`, who handles it and how long does a rebuild take?
- Should the index be added to migrations/alerts and wait for `ONLINE` before traffic opens?

## 18. Rolling Out Indexes Safely Alongside Java Applications

### 18.1. Dependency Rollout Sequence

A new feature querying `emailNorm` can roll out as follows:

~~~text
T0: Normalize existing data (controlled backfill)
                |
T1: Create new index; keep old index intact
                |
T2: Monitor SHOW INDEXES, wait for ONLINE with timeout
                |
T3: EXPLAIN/PROFILE query on representative data
                |
T4: Canary app using new query
                |
T5: Watch p95/p99, errors, DB Hits, resources
                |
T6: Approve full rollout
                |
T7: Drop old index only after confirming zero dependencies
~~~

If T2 fails, **do not** enable features assuming the index is ready. If T4 regresses, roll back the query/app rather than hastily dropping the new index mid-incident unless safely justified and impact-assessed.

### 18.2. Java Driver: Monitoring Index States

~~~java
import java.util.List;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class IndexStateMonitor {
    private final Driver driver;

    public IndexStateMonitor(Driver driver) {
        this.driver = driver;
    }

    public List<Record> findProblematicIndexes() {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.run("""
                SHOW INDEXES
                YIELD name, type, state, populationPercent
                WHERE state <> 'ONLINE'
                RETURN name, type, state, populationPercent
                ORDER BY name
                """).list();
        }
    }
}
~~~

This assumes the Java Driver has valid TLS/URI/credentials and the monitor account has schema-read privileges on the target database. Production code should map into DTOs, enforce timeouts, distinguish `POPULATING` (often normal during rollouts) from `FAILED` (alertable), and never log PII or secrets.

### 18.3. Java Driver: Capturing EXPLAIN Plans

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.summary.ResultSummary;

public final class IndexPlanProbe {
    private final Driver driver;

    public IndexPlanProbe(Driver driver) {
        this.driver = driver;
    }

    public String rootOperator() {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            ResultSummary summary = session.run("""
                EXPLAIN
                MATCH (u:IndexDemoUser)
                WHERE u.tenantId = $tenantId
                  AND u.emailNorm = $emailNorm
                RETURN u.userId
                """, Map.of(
                "tenantId", "T1",
                "emailNorm", "an@example.test"
            )).consume();

            return summary.plan().operatorType();
        }
    }
}
~~~

With `EXPLAIN`, the plan is accessed via `ResultSummary.plan()` in the driver API. **The root operator is typically `ProduceResults`**, not the index seek; walk the full plan tree when verifying index usage. Never write assertions checking `rootOperator() == "NodeIndexSeek"`.

To capture runtime stats, run `PROFILE` on safe read queries and inspect profile details in the result summary where supported by driver/version, comparing `Rows` and `DB Hits`. Plan/profile APIs vary across versions; align your driver library with the deployed server.

### 18.4. Spring Data Neo4j and Query Mapping

Spring Data Neo4j repositories and `Neo4jClient` do not pick indexes based on method names. SDN builds/sends Cypher; **the Neo4j planner chooses the access path**. Example service using `Neo4jClient`:

~~~java
import java.util.Optional;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;

@Service
public final class UserLookupService {
    private final Neo4jClient client;

    public UserLookupService(Neo4jClient client) {
        this.client = client;
    }

    public Optional<String> findIdByTenantAndEmail(
            String tenantId, String emailNorm) {
        // tenantId already verified by service authorization.
        return client.query("""
                MATCH (u:IndexDemoUser)
                WHERE u.tenantId = $tenantId
                  AND u.emailNorm = $emailNorm
                RETURN u.userId AS userId
                """)
            .bind(tenantId).to("tenantId")
            .bind(emailNorm).to("emailNorm")
            .fetchAs(String.class)
            .mappedBy((typeSystem, record) ->
                record.get("userId").asString())
            .one();
    }
}
~~~

This is an illustrative read API in the module, **not a complete authentication system**. Never trust a client-supplied `tenantId` without authorization checks. `emailNorm` must be normalized identically on write and read; uniqueness on `(tenantId, userId)` does not automatically make `(tenantId, emailNorm)` unique. If business logic expects at most one match, enforce uniqueness/validation accordingly.

When slow, log operation names, trace IDs, and durations per policy—never log parameters containing PII. Separate pool/driver/network time from Neo4j execution time so connection timeouts are not mistaken for index bugs.

## 19. Observing Indexes in Operations

An operational dashboard can track:

| Metric | Purpose |
| --- | --- |
| Count of `FAILED` indexes | Alerts on schema failures. |
| `POPULATING` indexes and elapsed/percent | Detects stalled or unusually long builds. |
| Index store size and free disk/headroom | Evaluates build/rebuild capacity. |
| Latency / DB Hits of key queries | Tracks planner/query regressions. |
| Node/relationship counts and tenant sizes | Reveals shifting cardinality distributions. |
| CPU/I/O, page cache, GC/heap | Separates hardware/resource limits from query plans. |
| Query errors, p50/p95/p99 | Measures user impact. |
| Deploy/migration/index-change markers | Correlates incidents with recent changes. |
| Backup age and restorability | Ensures recovery path if schema changes fail badly. |
| Metric collector liveness | Prevents treating missing metrics as `0`. |

**Never invent standard Prometheus metric names** if your exporter/version does not expose them. Build dashboards from real available fields tagged with source, instance, database, and timestamp; when data is absent, display **unknown**.

### 19.1. Context-Aware Alerting

- `FAILED > 0`: alert promptly, prioritizing indexes backing core workloads or constraints.
- `POPULATING` exceeding baseline for size/type: investigate rather than paging on every normal migration.
- Rising query latency alongside plan shift from seek to scan and rising DB Hits: investigate regression.
- Low free disk during population: escalate as a higher-severity capacity alert than “slow index”.
- Concurrent transaction failures, OOMs, or backup errors: investigate system-wide rather than tweaking one query.

To cut false positives, use **sustained duration windows**, representative baselines, and migration schedules. However, maintenance windows must never mute critical disk-full or database-down alerts.

## 20. Test and Fault-Reproduction Matrix

Practice in a **dedicated database**; never intentionally trigger `FAILED` indexes or full disks in production.

| ID | Scenario | Expected verification |
| --- | --- | --- |
| I01 | `CREATE` range index on fixture. | Initially `POPULATING`, then `ONLINE`. |
| I02 | Run `db.awaitIndexes` where supported. | Waits with timeout; reports not-ready if exceeded. |
| I03 | Equality query with right label and composite key. | Exact results; plan recorded (may scan on tiny fixture). |
| I04 | Query using `toLower(property)`. | Plan may differ; compare raw-property variant and semantics. |
| I05 | Query filtering only second composite property. | Evaluate plan/cost; do not assume index seek. |
| I06 | Query filtering low-selectivity `active`. | Do not treat label scan as a bug if total cost is lower. |
| I07 | `CONTAINS` query and `TEXT` index. | Match supported index type and plan. |
| I08 | Full-text procedure. | Returns analyzer-based score; not equated with substring search. |
| I09 | Relationship property index. | Distinguish edge-first lookup vs. node-first expansion. |
| I10 | Check index state after restart. | Never assume `ONLINE` without reading back state. |
| I11 | Load large data volume in staging. | Compare plans, cardinality, and DB Hits before/after. |
| I12 | Multi-order skewed tenant sizes. | Representative queries on giant tenants stay within SLO. |
| I13 | Index seek followed by huge expansion. | Identify fan-out downstream of the seek. |
| I14 | Simulated `FAILED` index in test/monitor layer. | Alerts on exact index/database without auto-dropping. |
| I15 | Query change accidentally drops tenant filter. | Security/result tests fail per policy. |
| I16 | Code rollout attempted before index is `ONLINE`. | Deployment gate blocks feature enablement. |
| I17 | Java Driver `EXPLAIN`. | Plan returned; full tree inspected, not just root. |
| I18 | Spring Data Neo4j query with wrong parameter type. | Type error or wrong result caught before production. |
| I19 | Index rebuild attempted with low disk headroom (simulated). | Runbook blocks risky action and routes to storage team. |
| I20 | Metric collector stops reporting. | Missing-data alert fires instead of reporting “zero errors”. |

### 20.1. Test Report Template

A report should record:

~~~text
Test ID:
Neo4j version / edition / database:
Index name / type / properties:
State before / after:
Query text (PII redacted):
Parameter types + data distribution:
Main plan operators:
Rows / Estimated Rows / DB Hits:
p50 / p95 / p99:
Business impact:
Verdict: PASS / FAIL / INCONCLUSIVE
Action and owner:
~~~

If test data is not representative enough, mark **INCONCLUSIVE** rather than declaring an index universally fast or slow.

## 21. Resolving Staging vs. Production Discrepancies

Staging often has few nodes, few relationships, queries hitting one tenant, and an always-warm page cache. Production can be totally different:

| Dimension | Staging | Production |
| --- | --- | --- |
| Data | Thousands of nodes, few supernodes. | Millions of nodes/edges, skewed distributions. |
| Tenants | 1–2 sample tenants. | Many tenants, some massive. |
| Indexes | Freshly built, all `ONLINE`. | Legacy indexes/constraints, cached plans, migrations. |
| Resources | Low CPU/RAM/I/O contention. | Concurrent imports, backups, CDC, and peak queries. |
| Versions | Possibly newer or different plugins. | Pinned versions and formal upgrade cycles. |
| Queries | Clean test parameters. | Diverse parameter values/types and data skew. |

When only production is slow:

1. Confirm indexes share identical names/types/schemas **on the exact target database**.
2. Compare query fingerprints and parameter shapes securely.
3. Measure plans and `Rows`/`DB Hits` on both small and giant tenants.
4. Check CPU, page cache, disk latency, and lock contention.
5. Check recent batch jobs, data shifts, deploys, or index builds near onset.
6. Reproduce in staging **using representative synthetic data**, never copying raw PII recklessly.
7. Ship hints, reindexes, or schema fixes only after canary validation and rollback readiness.

Never assume Neo4j is malfunctioning solely because the planner picks different plans across environments: it may be responding rationally to **different sizes, cardinalities, and load**.

## 22. Severity-Based Incident Runbooks

### 22.1. Level 1 — Slow Queries, Database Still Serving

**Goal:** diagnose without causing further disruption.

1. Record the operation, timestamp, p95, and redacted representative query.
2. Check index states, database health, and recent deploys/imports.
3. Run `EXPLAIN` first, then `PROFILE` on safe read queries.
4. Determine whether cost lies in scanning, seeking, expansion, or aggregation.
5. Test minimal predicate or query adjustments that preserve semantics.
6. Benchmark, canary, and keep a query rollback path ready.

### 22.2. Level 2 — Critical Index Stuck POPULATING or FAILED

**Goal:** protect live workloads and recovery paths.

1. Check disk headroom, CPU, and I/O; avoid rebuilding if space is tight.
2. Record `failureMessage` and relevant logs.
3. Check whether the index backs a constraint and which apps depend on it.
4. If `POPULATING`, consider deferring dependent traffic and monitor progress.
5. If `FAILED`, fix the root cause; rebuild only after change review.
6. Verify `ONLINE`, plans, query correctness, and latency before closing.

### 22.3. Level 3 — Disk/Transaction Failures or Unserviceable Queries

**Goal:** prioritize data durability.

1. Escalate to SRE/DBA; throttle non-essential writers/jobs per approved runbook.
2. Keep database store, index, and transaction-log files intact; **never delete via OS**.
3. Check storage/free bytes, backups, and restorability.
4. Restore disk headroom, services, privileges, and database health before tuning indexes.
5. Verify consistency, transactions, index readiness, and core business queries.
6. Document incident timeline, root cause, and regression tests.

An index failure can be a symptom of **full storage or failing I/O**; blindly recreating the index while storage remains broken makes things worse.

## 23. Practice Exercises

**Exercise 1 — State Diagnostics.** Create the demo range index and inspect `SHOW INDEXES`. Explain `POPULATING`, `ONLINE`, and `FAILED`, and state the criteria before an app may enable index-dependent features.

**Exercise 2 — Composite Indexes.** Create `(tenantId, emailNorm)` and compare `EXPLAIN` for three queries: `tenantId` only; `tenantId + emailNorm`; and `emailNorm` only. Why can you not claim the index will definitely be chosen on a five-user fixture?

**Exercise 3 — Functions and Normalization.** Compare `toLower(u.emailNorm) = $e` against `u.emailNorm = $e`. Build a test verifying stored data is normalized before switching the query, and prove results remain identical for uppercase/NULL emails.

**Exercise 4 — Selectivity and Fan-Out.** Build a dataset of 100,000 users with 99% `active = true`, plus one user holding 20,000 orders. Separate the cost of locating the user by index from expanding orders, and list which plan operators/metrics to inspect.

**Exercise 5 — Index Types.** A system runs `WHERE bio CONTAINS 'graph'` while only a full-text index exists on `bio`. Explain why the planner should not be assumed to use full-text there, and rewrite using the full-text procedure with a tenant check.

**Exercise 6 — FAILED and Constraints.** A `FAILED` index shares the name of a uniqueness constraint's backing index. Write a safe checklist to verify ownership, backups, cause, privileges, and next steps; why can you not drop it like an ordinary index?

**Exercise 7 — Post-Migration Query Plans.** A batch import grows Users from 10,000 to 10 million; the query stays unchanged yet the planner switches from seek to scan. Explain how to verify changes in cardinality, caching, types, stats, and CPU/I/O without assuming the planner is broken.

**Exercise 8 — Java Driver / SDN.** Write a Java Driver job listing non-`ONLINE` indexes and logging states per database; then use `Neo4jClient` to look up users by tenant/email. How do you enforce parameter types and avoid logging real emails?

**Exercise 9 — Alerting.** Design alerts for `FAILED` indexes, slow `POPULATING`, post-deploy `DB Hits` jumps, and low free disk; explain why critical disk alerts must not be silenced during index maintenance.

**Exercise 10 — Change Governance.** An engineer wants to add `USING INDEX` to every query because “the index is ONLINE yet the planner skipped it”. Define evidence requirements, per-tenant benchmarks, schema-change risks, and rollback policy before approving hints.

## 24. Summary Checklist

1. **Right database confirmed:** do the index, query, session/driver, and parameters all target the investigated environment?
2. **State classified:** `ONLINE`, `POPULATING`, or `FAILED`, with `failureMessage` and timestamp?
3. **Index type matched:** does range/text/full-text/point/vector/lookup/node/relationship match the predicate?
4. **Schema verified:** are labels, relationship types, properties, composite order, and constraint ownership exact?
5. **Query checked:** functions on properties, `OR`/`NULL`, parameter types, negations, and tenant filters?
6. **Full plan read:** index seek/label scan, filters, expansion, aggregation, and sort—never stopping at the first operator?
7. **Data measured:** cardinality, selectivity, supernodes, tenant skew, volume, and real distributions?
8. **Resources checked:** CPU, page cache, disk I/O, free disk, imports/backups, and long transactions?
9. **Plan cache/stats considered:** verified root cause and controlled replanning before intervening?
10. **Hints evaluated carefully:** never using hints to mask `FAILED` indexes or incompatible predicates?
11. **Correctness preserved:** optimizations do not alter results, privileges, or business semantics?
12. **Rollout gates in place:** wait for `ONLINE` with timeouts and verify plans/latency before enabling features?
13. **Recovery path ready:** backups, change review, app/schema rollback, and migration-failure owner?
14. **Monitoring active:** alerts for `FAILED`/`POPULATING`, DB Hits/p95, disk headroom, and silent metric collectors?
15. **Cause separated:** is the query slow because the index is not ready, the planner picked another path, or cost sits downstream of the index?

**Conclusion:** when Neo4j queries run slowly, first verify **whether the index is ready**, then check **whether the planner chose it**, and finally pinpoint **where the real cost occurs**. `SHOW INDEXES` reports index state; `EXPLAIN`/`PROFILE` reveal plans and runtime metrics. A label scan can be a sound choice, while an index seek can still precede an expensive traversal. A proper fix targets **the real root cause, preserves query semantics and data permissions, benchmarks before/after, and enforces safe migration gates and runbooks**—never blindly adding or dropping indexes.
