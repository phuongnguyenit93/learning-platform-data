# Evaluating Index, Store Format, and Query Plan Changes When Upgrading Neo4j

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **upgrading Neo4j DBMS**, **database migration**, **changing store formats**, **index rebuilds**, and **changing Cypher versions**.
- Inventory schemas/indexes/constraints and evaluate requirements to convert **BTREE** from Neo4j 4.4 to appropriate **RANGE, TEXT, or POINT** indexes when moving to Neo4j 5.
- Recognize the `aligned`, `block`, `standard`, and `high_limit` store formats; understand version/edition support conditions, conversion cost, and internal ID reassignment risks.
- Build a benchmark query suite to compare `EXPLAIN`, `PROFILE`, `Rows`, `DB Hits`, index seeks/scans, runtimes, p95/p99, and resource costs before and after upgrading.
- Verify **Cypher 5** and **Cypher 25** compatibility, manage per-database default languages, and prevent unintended semantic shifts.
- Execute dry runs on a data copy, confirm `ONLINE` indexes, reconcile the property graph, run controlled performance tests, and define **go/no-go** criteria.
- Plan backups/restores, downtime, full-system rollback, and requirements for Java Driver/Spring Data Neo4j and plugins.

This lesson belongs to the **Upgrades and Migration** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module. Neo4j uses a **property graph** consisting of nodes, relationships, labels/types, and properties; Cypher leverages indexes, constraints, data statistics, and the query planner to find relationships and paths. A version change can affect **all three layers**: on-disk storage layout, index structures, and query execution strategies. Even if Java Driver or Spring Data Neo4j application code does not change by a single line, APIs can still suffer altered results, latency, or write behavior if unchecked beforehand.

> **Version note:** Content distinguishes Neo4j **4.4 → 5.x**, the **5.26 LTS** line, and **Calendar Versioning (2025.x/2026.x)** releases. Features such as `block`, Cypher 25 syntax, and newer vector indexes carry version/edition prerequisites. **Do not blindly apply migrate/index commands to production**. Cross-reference the official guide for your exact source and target versions and test on an independent copy first.

## 1. Upgrading the DBMS Differs from Migrating Databases and Changing Store Formats

A project might say "upgrade Neo4j", yet in practice this spans multiple distinct tasks:

| Concept | What changes? | When is it needed? |
| --- | --- | --- |
| **Upgrade DBMS** | Binary/container image, Java runtime, server config, compatible drivers/plugins | Moving software to a supported release |
| **Database migration** | Moving databases to a DBMS/version requiring store migration | Such as the **4.4 → 5** path |
| **Store format migration** | Changing how nodes, relationships, and properties are encoded on disk | For example, `aligned` → `block` |
| **Index migration/rebuild** | Changing index types/providers or rebuilding structures | Handling legacy BTREE, swapping providers, `FAILED` indexes |
| **Cypher compatibility** | Selecting `CYPHER 5` vs. `CYPHER 25` syntax/semantics, updating queries | Releases from 2025.06 onward |
| **Application compatibility** | Driver, Spring Boot/SDN, APOC/GDS, procedures, serialization | Keeping APIs functional and fast |

**Not every upgrade changes store format**. Per Neo4j docs, many server upgrades only swap binaries and restart, whereas **changing major store format** or migrating legacy stores is a separate step that may require offline execution.

~~~mermaid
flowchart TD
    A["Identify source/target Neo4j"] --> B["Inventory schema, store, queries, plugins"]
    B --> C{"Store or index migration needed?"}
    C -->|Yes| D["Backup + offline migration/rebuild lab"]
    C -->|No| E["Upgrade binaries in lab"]
    D --> F["Start up, verify indexes ONLINE"]
    E --> F
    F --> G["Reconcile graph + EXPLAIN/PROFILE"]
    G --> H{"Correctness + SLOs pass?"}
    H -->|No| I["Revise plan or roll back lab"]
    H -->|Yes| J["Approve rollout with recovery plan"]
~~~

An approach can be **functionally correct yet fail performance** or vice versa. Establish two independent verification gates.

## 2. Change Matrix to Check by Version and Edition

| Transition scope | What must be evaluated |
| --- | --- |
| **4.4 → 5.x** | Handle legacy BTREE and index-backed constraints; upgrade/migrate databases; schemas and Cypher statements; Log4j 2 config; drivers/plugins |
| **5.x before 5.22 → 5.22+** | `block` becomes the default for **new Enterprise databases** from 5.22; **existing databases are not automatically rewritten to block** merely by booting the new binary |
| **5.23+** | `standard` and `high_limit` are **deprecated**; plan migration off legacy formats before their documented end-of-support milestone |
| **5.26 LTS → 2025.x/2026.x** | Specific upgrade path, runtime/index provider changes, Java compatibility, and release guides |
| **2025.06+** | **Cypher 5 / Cypher 25** selection available; verify each database's default language and changed syntax |
| **2026.02+** | Newly shipped `neo4j.conf` templates set `CYPHER_25` as default for newly created databases; existing databases keep their setting |
| **Community ↔ Enterprise** | Cluster capabilities, store/index types, and admin procedures differ; never assume universal format/command parity |
| **AuraDB managed** | Cannot perform offline store or host filesystem interventions like self-managed; use tier-supported upgrade/snapshot workflows |

**Inspect existing databases and newly created databases separately.** A modern Neo4j Enterprise instance may create new `block` databases while an existing `aligned` database continues running on the older format until an explicit supported migration runs.

Read more: [Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/), [Store formats](https://neo4j.com/docs/operations-manual/current/database-internals/store-formats/), [Cypher default version](https://neo4j.com/docs/operations-manual/current/configuration/cypher-version-configuration/).

## 3. Capture a Baseline Before Upgrading

Do not start by running `neo4j-admin database migrate`. First gather a **reference baseline** from the current environment.

### 3.1. Inventory DBMS, Databases, and Store Formats

In an environment with appropriate privileges:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

~~~cypher
// The store column is available on supporting versions.
// Run in the appropriate administrative context.
SHOW DATABASES
YIELD name, currentStatus, store
RETURN name, currentStatus, store
ORDER BY name;
~~~

`store` shows the database format information in supporting versions. If an older release omits that column, use the store inspection tool matching your target version and Operations Manual; never guess the format from a database name. Record **actual source facts**:

- Full version, edition, Java runtime, OS/image, and server topology (standalone/cluster/Aura).
- Physical databases and `system`, aliases, access modes, and sizes of store/indexes/transaction logs.
- Each database's store format, extensions/plugins, and licenses used by applications.
- Node counts, relationship counts, labels/types, and properties serving as business keys.
- Heap, page cache, transaction timeout, query logging/metrics, and resource limit settings.

### 3.2. Capture Index and Constraint Schemas

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes,
      properties, indexProvider, state,
      populationPercent, owningConstraint
RETURN name, type, entityType, labelsOrTypes,
       properties, indexProvider, state,
       populationPercent, owningConstraint
ORDER BY type, name;
~~~

~~~cypher
SHOW CONSTRAINTS;
~~~

Exact columns and providers depend on version/edition; `SHOW INDEXES YIELD *` exposes full metadata when authorized. **`state`**, **`populationPercent`**, and **`indexProvider`** are crucial because a schema-defined index is not necessarily ready for immediate use.

Specifically flag:

- `BTREE` indexes and `native-btree-1.0` / `lucene+native-3.0` providers from Neo4j 4.4.
- **Constraint-owned indexes**; never manually `DROP INDEX` on a uniqueness constraint's backing index as if it were standalone.
- Indexes supporting business lookups (`customerId`, `orderId`), date/price ranges, TEXT search, geospatial POINT, full-text, and vector queries.
- Indexes already `POPULATING` or `FAILED` **prior to the upgrade**.
- Unused indexes or duplicate schemas; verify before dropping anything.

### 3.3. Capture Real Query Workloads

Do not record only `MATCH (n) RETURN count(n)`. A solid baseline includes:

| Query category | Example | Why it matters |
| --- | --- | --- |
| Lookup by ID | `MATCH (c:Customer {customerId:$id}) RETURN c` | Verifies index seek on business keys |
| Range + sort | Filtering `Order.createdAt`, `totalCents` | Query planner may choose a different scan + sort |
| Single- or multi-hop traversal | `Customer-[:PLACED]->Order-[:CONTAINS]->Product` | Fan-out and join ordering heavily affect cost |
| Path finding | Constrained path queries | Runtime/plan shifts can spike latency |
| Aggregation | `count`, `collect`, `DISTINCT`, group-by | Intermediate row cost and memory usage |
| Batch write | `UNWIND`, `MERGE`, constraints | Lock contention, tx logs, and write throughput |
| Full-text/vector search | `SEARCH`/procedures supported by current version | Providers and semantics may change |

For each query, store the **original parameterized text**, representative parameter sets, expected results, data distribution, p50/p95/p99, throughput, CPU/heap/GC/page cache, and when safe, `EXPLAIN`/`PROFILE` outputs.

## 4. Migrating from Neo4j 4.4 BTREE to Modern Neo4j 5 Indexes

**Technical blocker when moving 4.4 → 5:** Neo4j 5 removed the **BTREE** index type. Per the official migration guide:

- BTREE indexes using `native-btree-1.0` or `lucene+native-3.0` must be handled **before starting on Neo4j 5 binaries**.
- Neo4j 5 requires **equivalent indexes on the same schema** using the appropriate `RANGE`, `POINT`, or `TEXT` type before dropping legacy BTREE indexes.
- For legacy **index-backed constraints**, an equivalent constraint on the same schema backed by the **`range-1.0`** provider must exist, otherwise startup/migration can be blocked.
- The guide recommends creating replacement indexes/constraints **while still on 4.4** to reduce risk inside the upgrade window.

You cannot simply "rename BTREE to RANGE" because search capabilities differ per index type.

### 4.1. Choosing the Right New Index Type

| Cypher query pattern | Index to consider | Example |
| --- | --- | --- |
| Equality / ordering comparisons on properties | **RANGE** | `o.createdAt >= $from` |
| Prefix / suffix / substring string matching | **TEXT** | `p.name CONTAINS $term` |
| Spatial point properties and geospatial filters | **POINT** | `point.distance(...)` |
| Analyzer-driven full-text search | **FULLTEXT** | Full-text query per engine/version support |
| ANN / vector similarity | **VECTOR** | Embedding search; provider depends on version |
| Label / relationship type lookup | **LOOKUP** | Token lookup; does not replace property indexes |

Examples on a **Neo4j 5+ lab**:

~~~cypher
CREATE RANGE INDEX order_created_at IF NOT EXISTS
FOR (o:Order) ON (o.createdAt);

CREATE TEXT INDEX product_name_text IF NOT EXISTS
FOR (p:Product) ON (p.name);

CREATE POINT INDEX place_location_point IF NOT EXISTS
FOR (p:Place) ON (p.location);
~~~

**Create only indexes that the workload actually uses.** Indexes add write overhead, disk usage, and population work; adding three indexes without `PROFILE` evidence can slow migration without helping any API.

### 4.2. Index-Backed Constraints

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
~~~

In supporting versions, uniqueness constraints are backed by an index, simultaneously **enforcing uniqueness** and accelerating equality lookups. When migrating legacy constraints, identify the equivalent index provider/constraint and **never accidentally drop data protection**.

**Note on `IF NOT EXISTS`:** Idempotent DDL prevents errors if an equivalent object exists, yet **does not prove** the legacy schema matches the exact desired name, type, and provider. Afterwards, re-check `SHOW CONSTRAINTS` and `SHOW INDEXES`, including auto-named constraints.

### 4.3. When There Are Too Many BTREE Indexes to Handle Manually

The migration CLI includes `--force-btree-indexes-to-range` for **4.4 → 5** (verify exact flag name in your build). It forces BTREE indexes/constraints to convert to RANGE when needed, however:

- **RANGE is not always optimal** for every prior query pattern.
- Rebuilt indexes may **populate asynchronously after startup**.
- Queries may pick suboptimal plans or miss indexes until population reaches `ONLINE`.
- Never use the flag to skip **proper index design** and correctness/performance testing.

Prefer evaluating critical schemas individually. Force conversion is only a conditional operational fallback requiring validation.

Sources: [Breaking changes 4.4 → Neo4j 5](https://neo4j.com/docs/upgrade-migration-guide/current/version-5/migration/breaking-changes/), [Migrate a database](https://neo4j.com/docs/operations-manual/current/database-administration/standard-databases/migrate-database/).

## 5. Index Population, Providers, and Status Before Opening Traffic

After an upgrade or store migration, an index may be declared properly yet still be **`POPULATING`**, or enter `FAILED` due to data/resource errors.

~~~cypher
SHOW INDEXES
YIELD name, type, state, populationPercent, indexProvider,
      labelsOrTypes, properties
RETURN name, type, state, populationPercent,
       indexProvider, labelsOrTypes, properties
ORDER BY state, name;
~~~

| State | Operational meaning | Safe to open traffic immediately? |
| --- | --- | --- |
| **`ONLINE`** | Index is ready for planner consideration | Continue checking performance/plans |
| **`POPULATING`** | Index is currently building | Not guaranteed to meet SLOs for index-dependent queries |
| **`FAILED`** | Index build or maintenance failed | Check failure cause and version runbook; block affected rollout |

Index population causes **I/O, CPU, page cache pressure, and extended startup times**. Do not just count index names in the catalog: **application readiness** must confirm critical indexes have reached `ONLINE`.

### 5.1. Providers Can Change Across Releases

`indexProvider` identifies the underlying implementation, such as RANGE `range-1.0`; **VECTOR providers** also span multiple generations, including `vector-2026.08` in applicable releases. Previously created indexes may stay on an older provider rather than automatically upgrading simply because binaries changed.

~~~cypher
SHOW VECTOR INDEXES
YIELD name, type, indexProvider
RETURN name, type, indexProvider;
~~~

Before rebuilding a vector index:

- Check **dimensions**, similarity function, property types, vector config, and provider version.
- Measure **recall@k, precision@k, latency, and size** rather than checking `ONLINE` alone.
- Watch out for shifts in **approximate ranking results**; ANN can return different top-k items even without a bug.
- Use vector syntax matching your version; never copy HNSW settings from one release to another without verifying.

Similarly, FULLTEXT is affected by analyzers and data, and TEXT/POINT/RANGE have distinct semantics. **Never treat an index type name as proof of identical business behavior.**

## 6. Store Formats: aligned, block, standard, high_limit

**Store format** is how Neo4j encodes nodes, relationships, properties, and records on the filesystem. It impacts **disk layout, page cache I/O, entity limits, upgrade compatibility, and migration cost**, not merely an arbitrary config flag.

| Store format | General characteristics | Version/edition notes |
| --- | --- | --- |
| **`aligned`** | Record-based, improved memory layout over standard; data accessed via linked records | Current **Community** default; Enterprise default prior to 5.22 |
| **`block`** | Co-locates property data closer to nodes/relationships for locality; large-scale support | **Enterprise**; GA in 5.16, default for new Enterprise DBs from 5.22 |
| **`standard`** | Legacy record format | **Deprecated** in 5.23; plan migration off per roadmap |
| **`high_limit`** | Legacy format supporting higher entity limits than standard | Enterprise; **deprecated** in 5.23; plan move to block |

**Do not assume** "Neo4j 5.26 means every database is already on block". Existing databases may still remain on `aligned`/`standard`/`high_limit`. Neo4j docs state that support for legacy formats ends along a roadmap anchored to LTS milestones; when planning an upgrade to a **target release**, verify whether it still reads the legacy format or requires pre-migration.

### 6.1. Minor Store Upgrade vs. Major Format Migration

- **Minor format updates** within the same format may be upgraded automatically at startup by Neo4j in supporting versions.
- **Major format migrations** or **converting** between `aligned` and `block` require `neo4j-admin database migrate` or an equivalent official procedure.
- Setting `db.format=block` in configuration **does not automatically convert all existing databases to block**. The setting applies to newly created databases.
- In an Enterprise cluster, follow the **cluster runbook**; never arbitrarily stop one member and migrate in place, breaking replica/metadata compatibility.

Official docs: [Store formats](https://neo4j.com/docs/operations-manual/current/database-internals/store-formats/), [Migrate a database](https://neo4j.com/docs/operations-manual/current/database-administration/standard-databases/migrate-database/).

### 6.2. Changing Formats Is Heavy, Offline I/O Work

In a **standalone lab**, for example converting a verified eligible database `graph_lab` to `block`:

~~~cypher
// On the system database, executed by an authorized admin account.
// This takes the target database offline.
STOP DATABASE graph_lab;
~~~

~~~bash
# On the Neo4j host/lab with matching neo4j-admin binary version.
# Database is stopped; verified backup and headroom disk space exist.
neo4j-admin database migrate --to-format=block graph_lab
~~~

~~~cypher
// Only after migration succeeds and verification checks pass.
START DATABASE graph_lab;
~~~

Operational prerequisites:

1. **Restorable backup** and pre-migration state recorded.
2. **Stop the database** per procedure; never run on a database accepting WRITES.
3. Verify the graph **fits within entity limits** of the target format.
4. Provision enough disk for original data, converted data, temp files, and **index rebuilds**.
5. Measure store rewriting, index population, and app readiness durations, because **all of this counts toward database downtime**, not just CLI execution time.
6. Do not open traffic until critical indexes and constraints are ready.

These commands are **examples for a self-managed lab**; never run them directly on Aura and never apply them verbatim to a multi-server Enterprise cluster.

### 6.3. Internal ID Changes During Format Conversion

When migration changes store format, Neo4j may **reassign internal node and relationship IDs** because IDs depend on physical layout. Therefore:

~~~cypher
// Use only for diagnostics within one DB at the current point in time.
MATCH (o:Order {orderId: $orderId})
RETURN elementId(o) AS elementIdNow,
       o.orderId AS businessId;
~~~

**Never use `id(n)` or `elementId(n)` as durable IDs across migrations, exports/restores, or external APIs.** Use domain keys like `Order.orderId` and `Customer.customerId` backed by uniqueness constraints.

For Java/Spring Data Neo4j apps, review `@Id`, `@GeneratedValue` mappings, and external references. If another system persisted internal IDs in PostgreSQL, Redis, or Kafka, that is a **critical migration risk** and may require data model remediation before changing formats.

## 7. How Changing Store Formats Affects Query Plans

There is no rule that "switching to block makes every query faster". A format can improve locality for property-heavy queries, yet outcomes depend on graph structure, indexes, planner, cache, CPU, I/O, and concurrency.

Example:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
      -[:PLACED]->(o:Order)
RETURN o.orderId AS orderId,
       o.status AS status,
       o.totalCents AS totalCents
ORDER BY o.orderId
LIMIT 30;
~~~

Different cost sources:

| Cost source | What influences it | What to measure on format change |
| --- | --- | --- |
| Seek `Customer` node | Constraints/indexes, selectivity, statistics | Still using `NodeUniqueIndexSeek` or similar index seek? |
| Expand `PLACED` | Node degree, relationship count, data locality | `Rows`, `DB Hits`, page cache faults |
| Read `Order` properties | Property layout, cache | DB Hits, disk I/O, and latency |
| `ORDER BY` + `LIMIT` | Rows before sort, index ordering, planner | Large `Sort` present? Can the query short-circuit? |
| Java mapping | Record/field count, network, DTO/SDN entity graph | Bytes transferred, Java heap, response p95 |

Specifically, **`LIMIT 30` at the end does not guarantee Neo4j traverses only 30 relationships**. If it must sort tens of thousands of orders to pick the first 30, a new store format will not fix an unsuitable query shape.

## 8. Query Plans: EXPLAIN, PROFILE, and What to Compare

`EXPLAIN` plans without executing the query body; `PROFILE` **executes** the query and reports actual per-operator statistics.

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})
      -[:PLACED]->(o:Order)
RETURN o.orderId AS orderId
ORDER BY o.orderId
LIMIT 20;
~~~

~~~cypher
// Run PROFILE only on READ queries when safe.
PROFILE
MATCH (c:Customer {customerId: $customerId})
      -[:PLACED]->(o:Order)
RETURN o.orderId AS orderId
ORDER BY o.orderId
LIMIT 20;
~~~

**Never run `PROFILE` on `DELETE`/`SET` queries in production** merely to view plans: it actually mutates data if committed.

### 8.1. Reading Plans by Operator Group

| Operator / metric | Question to ask |
| --- | --- |
| `NodeByLabelScan` / `AllNodesScan` | Why is the planner scanning nodes instead of using a selective index? |
| `NodeIndexSeek` / `NodeUniqueIndexSeek` | Does the query leverage the business-key index? |
| `Expand(All)` / `Expand(Into)` | How many edges/intermediate rows does a root node fan out to? |
| `Filter` | Are predicates pushed down early or applied after huge traversals? |
| `Sort` / `Top` | Is it sorting massive row counts before `LIMIT`? |
| `NodeHashJoin` / `Apply` | Does join/subquery ordering multiply rows? |
| `Eager` | Is large materialization occurring for read/write isolation semantics? |
| **`Rows`** | How many actual rows flow through each operator? |
| **`DB Hits`** | How many storage engine accesses occur? |
| **Memory/Page cache** | Are RAM, cache, and I/O sufficient? |

Operators can be renamed or optimized differently across Cypher releases. **You do not need plan text to match 100%**; the objective is correctness, bounded work, latency, and resource usage within SLOs.

### 8.2. How to Compare Plans Across Versions

For **the same business query**:

1. Use the **same dataset snapshot**, size, and node-degree distribution (especially nodes with thousands of relationships).
2. Keep **representative parameters**, target indexes, and result limits identical.
3. Capture **query text**, `EXPLAIN`, `PROFILE`, statistics, runtime, and index providers.
4. Separate **cold cache** and **warm cache** runs; execute enough iterations to avoid startup skew.
5. Compare **p50/p95/p99**, throughput, and error rates under identical concurrency.
6. If the plan changes yet results are accurate, latency improves, and load stays healthy, do not force the old plan back.
7. If regression occurs, pinpoint the root cause (unpopulated index, stale stats, join order, Cypher language, plugins) before adding planner hints.

**Sample verification table:**

| Query ID | Metric | Pre-upgrade | Post-upgrade | Gate |
| --- | --- | ---: | ---: | --- |
| Q01 lookup customer | p95 (ms) | 18 | 20 | ≤ 30 |
| Q02 2-hop traversal | p95 (ms) | 140 | 310 | ≤ 200 → **FAIL** |
| Q02 2-hop traversal | DB Hits | 12,000 | 51,000 | Investigate |
| Q03 order write | p95 (ms) | 40 | 43 | ≤ 75 |
| Q04 search | recall@10 | 0.92 | 0.91 | ≥ 0.90 |

**These numbers are synthetic figures for learning**; substitute real measurements and business rules. Q02 FAILS even though the database is online and all constraints exist.

## 9. Query Plan Cache, Statistics, and Replanning

Neo4j maintains a query plan cache to avoid replanning identical queries. After restarts, schema changes, or store migrations, plans may need regeneration against **updated database statistics**.

Reasons plans change:

- **Index/constraint changes:** planner gains or loses access paths.
- **Cardinality/selectivity statistics shift:** node counts, relationship counts, distinct values, density, and skew differ from the old snapshot.
- **Cold cache:** query compiles and plans for the first time after restart.
- **Planner/runtime updates:** the new binary chooses different joins, operators, or runtimes.
- **Default Cypher language changes:** semantics and syntax behavior can shift.
- **Provider/index state changes:** a `POPULATING` index is not used by the planner like an `ONLINE` index.

Per Neo4j documentation, cached plans become eligible for replanning once sufficient time elapses and statistics diverge past thresholds; not every query replans simultaneously.

### 9.1. Forcing a Query Replan in the Lab

~~~cypher
// EXPLAIN does not execute MATCH; it only forces replanning.
CYPHER replan=force
EXPLAIN
MATCH (c:Customer {customerId: $id})
RETURN c.customerId AS id;
~~~

In supporting Cypher versions, `replan=force` bypasses valid cached plans so the planner re-evaluates. This does **not** guarantee "force always runs faster"; if stats or indexes are off, the new plan can still be worse.

### 9.2. Refreshing Statistics and Query Caches at the Right Time

Neo4j provides administrative procedures:

~~~cypher
// Clears query caches; does not alter graph data.
CALL db.clearQueryCaches();
~~~

~~~cypher
// Resamples indexes/statistics as supported by the running version,
// then marks caches for replanning on subsequent queries.
CALL db.prepareForReplanning();
~~~

**Never run these two commands casually in production**. Resampling indexes and triggering mass replanning consumes resources and can cause latency spikes while every cached query recompiles. Use them only when authorized, understanding the blast radius, after indexes stabilize, and after proving stale stats/plans caused the regression. On 2026.x, verify exact procedure names/signatures before automating.

Sources: [Statistics and execution plans](https://neo4j.com/docs/operations-manual/current/performance/statistics-execution-plans/), [Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/).

## 10. Cypher 5 and Cypher 25: Check Both Syntax and Results

From Neo4j **2025.06** onward, operators can choose **Cypher 5** or **Cypher 25** per database/query. Upgrading the **Neo4j server binary** does not require switching every query to Cypher 25 immediately.

### 10.1. Inspect Default Language per Database

~~~cypher
// Only on versions supporting the defaultLanguage column.
SHOW DATABASES
YIELD name, defaultLanguage
RETURN name, defaultLanguage
ORDER BY name;
~~~

For self-managed deployments, the setting name is:

~~~properties
# neo4j.conf - affects newly created databases per version semantics.
db.query.default_language=CYPHER_5
# Or, once ready to transition:
# db.query.default_language=CYPHER_25
~~~

From Neo4j **2026.02**, shipped `neo4j.conf` templates **explicitly set `CYPHER_25`** for newly created databases; existing databases do not switch defaults automatically just because the server ships a new config template. If omitted, the configuration-level default may remain `CYPHER_5`. Consequently, two databases on the same host can run **different default languages**.

### 10.2. Pin Cypher Version for Specific Queries

~~~cypher
CYPHER 5
MATCH (c:Customer {customerId: $id})
RETURN c.displayName AS displayName;
~~~

~~~cypher
CYPHER 25
MATCH (c:Customer {customerId: $id})
RETURN c.displayName AS displayName;
~~~

These examples require **a server supporting Cypher 25**. Version pinning isolates two test variables:

1. Compare **identical Cypher 5** across old and new binaries to isolate planner/runtime changes.
2. Compare **Cypher 5 vs. Cypher 25 on the same new binary** to evaluate language migration.

Never simultaneously **swap binaries, change store format, change indexes, and switch default language**, then guess which variable caused a regression. Staged experiments attribute root causes cleanly.

### 10.3. Changing Default Language Is an Administrative Change

On supporting versions:

~~~cypher
// Illustrative only on a test database with appropriate admin account.
ALTER DATABASE graph_lab
SET DEFAULT LANGUAGE CYPHER 25;
~~~

Before switching:

- Check syntax compatibility as well as `NULL` handling, type coercion, function/procedure availability, path/aggregation semantics, and ordering.
- Inspect generated Cypher from **Spring Data Neo4j**, APOC, GDS, and custom Cypher.
- Capture plans and measure p95/p99 on critical queries.
- Plan language rollback / reverting defaults **only where supported**, and verify the app has not started depending on Cypher 25-only features.

**Do not treat `CYPHER 25` as a pure performance compiler flag**. It carries language/feature semantics; switching requires correctness QA.

Sources: [Select Cypher version](https://neo4j.com/docs/cypher-manual/25/queries/select-version/), [Configure Cypher default version](https://neo4j.com/docs/operations-manual/current/configuration/cypher-version-configuration/).

## 11. Real-World Scenario: Traversal Query Slows Down After Upgrade

Suppose `Customer` has a `PLACED` relationship to `Order`, and each `Order` has a `CONTAINS` relationship to `Product`:

~~~mermaid
flowchart LR
    C["Customer<br/>customerId"] -->|PLACED| O["Order<br/>createdAt, totalCents"]
    O -->|CONTAINS| P["Product<br/>sku, name"]
~~~

Use case: list the 20 products most recently purchased by a customer:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
      -[:PLACED]->(o:Order)
      -[:CONTAINS]->(p:Product)
RETURN p.sku AS sku,
       p.name AS name,
       o.createdAt AS orderTime
ORDER BY orderTime DESC, sku
LIMIT 20;
~~~

Before upgrade, query p95 = 120 ms. After upgrade, p95 = 900 ms. Possible causes:

- `Customer.customerId` constraint is still `POPULATING`, forcing node scans.
- Planner picked a different join/expand order due to updated statistics.
- More high-degree customer nodes exist; post-upgrade benchmark data distribution differs.
- `Order.createdAt` lacks an appropriate index or cannot serve a Customer-rooted traversal.
- Page cache is cold or contending with index rebuild I/O.
- Cypher language or runtime changed.
- Java client connection pool/TLS/network shifted simultaneously—**not DB Hits**.

### 11.1. Diagnostic Workflow

1. **Confirm correctness**: results contain the exact 20 products/records and contracted ordering.
2. **Inspect index states**: `SHOW INDEXES`, especially the `Customer.customerId` constraint.
3. **Compare plans on both sides**: `PROFILE` on identical snapshots/params, checking seeks, expands, sorts, and DB Hits.
4. **Check intermediate row counts**: 1 customer → 20,000 orders → 160,000 products? Fan-out before `LIMIT` may dominate cost.
5. **Isolate cache**: benchmark cold vs. warm; inspect page cache and disk metrics.
6. **Isolate language**: run `CYPHER 5` on the new version before testing `CYPHER 25`.
7. **Test better query shapes in the lab** before rushing to add index hints:

~~~cypher
// Limit Order set before expanding to Product.
// Business semantics change to "products from the 20 newest orders".
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WITH o
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT 20
MATCH (o)-[:CONTAINS]->(p:Product)
RETURN p.sku AS sku, p.name AS name, o.createdAt AS orderTime
ORDER BY orderTime DESC, sku;
~~~

**Semantic warning:** This illustrative optimization **changed the contract**: from "20 newest product rows" to "products of the 20 newest orders". Use it only if product requirements permit. A faster plan returning different data is a **correctness regression**, not a successful optimization.

## 12. Before/After Testing Plan: Controlling Variables

A practical plan separates at least three test phases:

| Phase | Server binary | Store format | Indexes | Cypher version | Purpose |
| --- | --- | --- | --- | --- | --- |
| **A — Baseline** | Source | Source | Source schema | Source | Record correctness + performance |
| **B — Binary migration** | Target | Keep format if supported | Required conversions | Pin compatible version | Isolate binary/planner changes |
| **C — Store migration** | Target | Convert to `block` if eligible | Rebuild/populate | Keep as B | Measure format cost/benefit |
| **D — Cypher migration** | Target | Keep as C | Keep as C | Switch to 25 | Measure language/runtime differences |

Every phase must use representative data and workloads. Skip phase C if your edition or version **does not support block**; skip D if the application does not yet need or support Cypher 25.

### 12.1. Test Dataset

- Independently **reconciled and restored** backup/snapshot.
- Preserves labels, relationship types, property distributions, degree skew, and constraints/indexes.
- Includes **high-degree nodes**, multi-hop paths, and customers with 0, 1, or thousands of orders.
- Includes edge values: `null`, missing properties, Unicode strings, timestamps/timezones, and large numbers.
- Includes vector/fulltext queries if used by the app; never exclude them as "not basic Cypher".

### 12.2. What to Measure

| Area | Metrics | On failure |
| --- | --- | --- |
| **Correctness** | Node/relationship counts, business keys, sample queries, path integrity | **NO-GO** on any data discrepancy |
| **Schema** | Index/constraint names/types/providers/states, `ONLINE` | **NO-GO** for queries needing unready indexes |
| **Performance** | p50/p95/p99, READ/WRITE throughput, DB Hits, Rows, GC, disk | Investigate/tune before rollout |
| **Stability** | Error rate, timeouts, transient retries, pool pending | Unacceptable when breaching SLOs |
| **Operations** | Startup/recovery, index rebuild time, disk peak, backup/restore drill | Do not open traffic if exceeding downtime budget |
| **Integrations** | Java Driver, SDN, APOC/GDS, CDC, Kafka/ETL | Test contracts and retry/rebuild behavior |

**Never measure only averages**: if p50 holds at 10 ms while p99 spikes to 3 seconds, users can experience significantly more timeouts.

## 13. Java Driver and Spring Data Neo4j in the Migration Plan

New query plans do not only appear in Neo4j Browser. Java code can emit different Cypher than hand-written queries:

- Spring Data Neo4j repositories generate queries to map entity graphs, relationships, and projections.
- `Neo4jClient`, `@Query` repositories, and raw Java Driver calls may use different Cypher for the same endpoint.
- `RETURN c` can fetch a wider object graph than a DTO projecting only `c.customerId` and `c.displayName`.
- Java Driver handles transaction routing, bookmarks, retries, and connection pools; these affect latency whenever migration changes topology or TLS.

### 13.1. Example Java Driver Lookup Test Harness

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class CustomerLookup {
    private final Driver driver;

    public CustomerLookup(Driver driver) {
        this.driver = driver;
    }

    public String findName(String database, String customerId) {
        try (Session session = driver.session(
                SessionConfig.forDatabase(database))) {
            return session.executeRead(tx -> tx.run("""
                    MATCH (c:Customer {customerId: $id})
                    RETURN c.displayName AS name
                    """, Map.of("id", customerId))
                    .single()
                    .get("name")
                    .asString());
        }
    }
}
~~~

Measure **end-to-end `findName`** in the application separately from Cypher `PROFILE`. Across repeated benchmark iterations, **share the Driver** and open Sessions per request/test case—never create/close a Driver per iteration. Ensure the database name and test rows match, because `single()` throws if 0 or multiple rows return.

### 13.2. Read/Write Transactions and Retries

After upgrading, managed transactions `executeRead`/`executeWrite` may retry eligible transient errors. In benchmarks and rollouts:

- Report **user-perceived latency including retries**, not just a single Cypher execution.
- `executeWrite` callbacks must use stable IDs and avoid external side effects inside callbacks that may re-run.
- If migration altered **internal IDs**, update any code persisting those IDs across versions or external stores beforehand.
- For SDN entities, verify constructor/ID mappings, custom converters, index-backed constraints, and repository queries.
- For APOC/GDS plugins, verify JAR/license versions and procedure signatures against the target server; **never assume plugin compatibility merely because Bolt connects**.

### 13.3. Reconciling JSON/DTO Outputs

Do not check only HTTP 200 status. Compare:

1. Exact customer IDs and order IDs.
2. Returned relationship and node counts.
3. Missing or duplicated list items caused by unstable ordering.
4. Whether `null` or added/removed properties break Java mapping.
5. For queries without `ORDER BY`, never rely on "accidental" ordering stability as a correctness criterion.

## 14. Planning Cutover, Backup, Rollback, and Downtime

### 14.1. Why You Must Restore from a Pre-Upgrade Backup

Neo4j **does not support simple DBMS downgrades** by swapping binaries back after upgrading/migrating data. Rollback planning must include:

- **Pre-migration backups** restorable into the older environment/version.
- Saved configs, secrets, certificates, plugins, schema scripts, and admin metadata.
- A playbook to repoint applications to the old endpoint or restore backups into an authorized system.
- Reconciliation of **WRITES occurring after the backup cutoff**; rolling back data to the old snapshot risks losing those transactions.
- Defined RPO/RTO and stakeholder communication for stopping or shifting traffic.

**Never write new data after migration and then attempt to point older 4.4/5 binaries back at the store.** That path can be format-incompatible and cause data loss.

### 14.2. Controlled Cutover Sequence Pattern

~~~mermaid
flowchart TD
    B["Pre-upgrade backup + restore test"] --> F["Freeze schema / plugin versions"]
    F --> L["Migration rehearsal on copy"]
    L --> G{"Indexes + correctness + perf pass?"}
    G -->|No| R["Block rollout, fix schema/queries"]
    G -->|Yes| D["Select maintenance / cutover window"]
    D --> S["Quiesce writes per runbook"]
    S --> U["Upgrade/migrate per guide"]
    U --> I["Indexes ONLINE + DB online"]
    I --> T["Smoke tests + query benchmarks"]
    T --> X{"Release gates pass?"}
    X -->|Yes| O["Open traffic in stages"]
    X -->|No| Q["Rollback/restore per playbook"]
~~~

**Quiescing writes** is crucial when cutting over to a migrated copy: ensure zero committed writes are missed after snapshot capture. In cluster environments, a version-supported rolling upgrade path may exist, but never apply standalone/offline migration steps directly to a live cluster. Upgrading 4.4 → 5 is a major migration, not a rolling restart of all servers.

### 14.3. Resources to Budget

| Resource | Why it is needed |
| --- | --- |
| **Disk** | Holding old and converted stores, temp files, transaction logs, and rebuilt indexes |
| **CPU** | Rewriting stores, index population, query benchmarks |
| **RAM/heap/page cache** | Migration/recovery, cold/warm caches, GDS/plugins if used |
| **Network** | Transferring backups/copies/database seeds within clusters |
| **Downtime** | Stopping DB, store migration, index rebuilds, smoke tests, rollback buffer |
| **Staffing** | DBA, app owner, SRE/on-call, data owner, and go/no-go decision maker |

**Time estimates from a small 100 GB dataset do not scale linearly to a 1 TB graph**: index counts, high-degree nodes, storage tier, and I/O contention can all stretch durations.

## 15. Post-Migration Graph and Schema Verification

Run against the **restored/migrated database**, not `system`, when counting graph data.

### 15.1. Nodes, Relationships, and Business Constraints

~~~cypher
MATCH (c:Customer)
RETURN count(c) AS customerCount;
~~~

~~~cypher
MATCH (o:Order)
RETURN count(o) AS orderCount;
~~~

~~~cypher
MATCH (:Customer)-[r:PLACED]->(:Order)
RETURN count(r) AS placedRelationshipCount;
~~~

~~~cypher
SHOW CONSTRAINTS;
~~~

Counting queries can be expensive on huge graphs; use snapshot statistics, sampling, or batched checks where appropriate. **Matching counts alone are insufficient** to prove graph correctness: nodes might swap relationships, lose properties, or hide duplicate keys behind matching totals.

### 15.2. Reconciling by Business Keys and Paths

~~~cypher
MATCH (c:Customer {customerId: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN c.customerId AS customerId,
       count(DISTINCT o) AS orderCount;
~~~

~~~cypher
MATCH (o:Order {orderId: $orderId})
OPTIONAL MATCH (owner:Customer)-[:PLACED]->(o)
RETURN o.orderId AS orderId,
       o.status AS status,
       o.totalCents AS totalCents,
       collect(DISTINCT owner.customerId) AS ownerIds;
~~~

Spot-check multiple key categories, especially:

- High-degree nodes, isolated nodes, and nodes created close to backup time.
- Relationships carrying properties and directions used in path queries.
- Uniqueness and existence/type constraints where supported by edition.
- Temporal, spatial, list, large string, and critical Unicode fields.
- Indexes/search types and exact expected result counts for business queries.

### 15.3. Physical Consistency Check

Neo4j provides `neo4j-admin database check` and version-appropriate check modes. Running it typically requires **the database offline or a backup/dump artifact** depending on the command. Never run arbitrary flags against live online production; read your target version's docs and run against a copy/backup:

~~~text
Check 1: backup artifact has complete chain and metadata.
Check 2: restore/copy succeeds on test Neo4j.
Check 3: consistency checker finds zero store corruption.
Check 4: Cypher reconciles business keys and indexes/constraints.
Check 5: Java/Spring integration and latency meet SLOs.
~~~

The consistency checker **cannot prove business logic correctness**. A graph missing 50 `PLACED` edges can still be structurally valid on disk, making application-level reconciliation essential.

## 16. Common Errors and Diagnostic Directions

| Symptom | Common root cause | Diagnostic step |
| --- | --- | --- |
| Neo4j 5 refuses to start a 4.4 database | Unhandled legacy BTREE indexes/constraint providers or incomplete store migration | Check migration logs, `SHOW INDEXES/CONSTRAINTS` on source, and 4.4 → 5 guide |
| Lookups slow after upgrade | Index `POPULATING`/`FAILED`, planner scan, cold cache | `SHOW INDEXES`, `EXPLAIN/PROFILE`, page cache |
| Previously TEXT-indexed queries return different results | Different index type/provider or search semantics | Test contains/startsWith/fulltext behavior and Unicode data |
| Query p99 spikes despite index `ONLINE` | Statistics, plan/join order, runtime, data skew, network | Compare `Rows`, `DB Hits`, client pools, and cache |
| Store migration hits out-of-disk | Format change rewrites full store and repopulates indexes | Capacity, backup size, temp path, peak disk |
| `elementId` changed after migration | Internal IDs reassigned during format change | Switch to business keys and reconcile references |
| New DB uses Cypher 25, old DB uses Cypher 5 | Per-database default language and new config template defaults | `SHOW DATABASES YIELD name, defaultLanguage` |
| Vector index still uses old provider | Providers do not automatically upgrade with binaries | `SHOW VECTOR INDEXES`, plans, and recall@k |
| Java Driver connects OK, yet repositories fail | Incompatible generated queries/driver/SDN/plugin signatures | Integration tests, logs, dependency matrix |
| Rollback with old binary fails | Direct downgrade unsupported | Restore pre-upgrade backup per playbook |
| Index rebuild finished, yet query still scans | Predicate incompatible with index, stats/plan, or label mismatch | Check schema, parameters, `EXPLAIN`, and query shape |
| Cluster refuses writes post-upgrade | Lost quorum, discovery/routing, or incompatible member versions | Cluster runbook, `SHOW SERVERS/DATABASES`, networking |

### 16.1. When to Roll Back Instead of Tuning Further

Declare **NO-GO/rollback** if:

- Database fails to come online or fails required consistency checks.
- Business keys, relationships, properties, or critical constraints diverge.
- Key indexes stay `FAILED` or cannot finish populating within the downtime budget.
- Write APIs fail to commit cleanly, trigger duplicates/constraint errors, or retries cause side effects.
- p95/p99 and error rates severely breach SLOs with no safe fix ready.
- No trusted backup/restore exists, or the cluster lacks quorum after rollout.

**Never** close an incident merely because `SHOW DATABASES` reports `online` while correctness and SLOs remain unverified.

## 17. Hands-On Exercise: Evaluating Indexes, Formats, and Plans Before and After Upgrading

### 17.1. Scenario

A team runs Neo4j **4.4 Enterprise** with database `sales_graph` containing `Customer -[:PLACED]-> Order` and a Spring Data Neo4j application. They plan to move to a release supporting `block` and evaluate `CYPHER 25` where suitable. They have a `Customer.customerId` constraint, an index on `Order.createdAt`, a query fetching recent orders, and an `UNWIND` batch write job.

**Do not upgrade live production in this exercise.** Use a lab database or an isolated restored backup to practice verification.

### Step 1 — List the Change Inventory

Build a table:

| Item | 4.4 Baseline | Target | PASS condition |
| --- | --- | --- | --- |
| DBMS/driver | Exact versions | Approved versions | Connectivity/TLS/auth succeed |
| BTREE indexes | Names, providers, schema | Appropriate RANGE/TEXT/POINT | Zero legacy migration blockers |
| Uniqueness constraints | `Customer.customerId` | Equivalent constraint | Zero duplicates |
| Store format | Current format | Keep or migrate to block per plan | Migration tested and downtime known |
| Cypher | Legacy queries | Pin Cypher 5; evaluate 25 | Identical results |
| Query plans | Rows/DB Hits, p95 | New plan/runtime | Within performance gate |

### Step 2 — Capture Schema and Data

~~~cypher
SHOW INDEXES;
SHOW CONSTRAINTS;
~~~

Also record node/relationship counts, sample `Customer` nodes with 0, 10, and 10,000 orders, provider names, and index states.

### Step 3 — Convert Legacy Indexes in the Lab

Classify which BTREE indexes serve equality lookups, TEXT searches, POINT geography, and constraint backing. Follow the 4.4 guide to create equivalent indexes **before migration** and confirm them online; **never** drop a uniqueness constraint protecting live data.

### Step 4 — Migrate and Evaluate Format Conversion

Back up first, then upgrade to the target Neo4j via the official procedure. Run **a phase keeping the current format** first; if Enterprise/target supports it and disk/downtime allow, run a **separate phase** converting a copy to `block` via `neo4j-admin database migrate --to-format=block`. Record CLI duration, population duration, and time until application readiness.

### Step 5 — Compare Both Queries

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT 20;
~~~

~~~cypher
PROFILE
MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT 20;
~~~

Compare across equivalent data, low- and high-degree customer parameters, `Rows`/`DB Hits`, index seeks/scans, `Sort`, and p95/p99 under fixed concurrency.

### Step 6 — Test Cypher 5/25 Selection

On a target server **supporting** both:

~~~cypher
CYPHER 5
MATCH (o:Order {orderId: $orderId})
RETURN o.status AS status, o.totalCents AS totalCents;
~~~

~~~cypher
CYPHER 25
MATCH (o:Order {orderId: $orderId})
RETURN o.status AS status, o.totalCents AS totalCents;
~~~

Run with identical parameters and datasets; record outputs and plans. If switching language versions breaks a query, keep `CYPHER 5` for that use case and file a syntax migration ticket before changing the database default.

### Step 7 — Produce a Go/No-Go Report

~~~text
Target Neo4j version: ...
Edition / store format before -> after: ...
Indexes: total / ONLINE / POPULATING / FAILED
Constraints: before vs after
Data consistency: PASS / FAIL
Cypher 5 correctness: PASS / FAIL
Cypher 25 compatibility: PASS / FAIL / NOT APPLICABLE
Query p95/p99 regression: ...
Worst DB Hits / Rows increase: ...
Startup + index population + cutover time: ...
Restore drill before migration: PASS / FAIL
Go/No-Go: ...
Owner + timestamp + rollback point: ...
~~~

### Self-Check Questions

**1. Does simply setting `db.format=block` and restarting convert all existing Enterprise databases to block?**

No. Existing databases keep their format unless migrated via a supported procedure; major format changes are typically offline operations.

**2. Why does migrating from Neo4j 4.4 to 5 require checking BTREE indexes beforehand?**

Because legacy BTREE indexes were removed and migration requires equivalent indexes/constraints; leaving unsupported legacy schemas can block database startup.

**3. After migration, `SHOW INDEXES` lists every name, yet all show `POPULATING`. Can traffic open immediately?**

Not by default. Index-dependent queries may miss SLOs; monitor population until `ONLINE` and run smoke tests first.

**4. How do `EXPLAIN` and `PROFILE` differ?**

`EXPLAIN` builds the plan without running the query; `PROFILE` executes the query to collect actual Rows/DB Hits and runtime statistics. Running PROFILE on write queries performs writes if committed.

**5. If a 2026.x server defaults new databases to Cypher 25, do existing databases automatically switch to 25?**

No. Check each database's default language and configuration policy; existing databases can remain on Cypher 5.

**6. Why shouldn't `elementId` be stored in external APIs outside Neo4j?**

Because internal IDs can be reassigned during store format migrations; durable business keys backed by uniqueness constraints belong in external references.

**7. A query plan changed, yet p95 dropped and results remain accurate. Is this an upgrade failure?**

Not necessarily. Correctness, latency, and resource usage are the goals; differing operator names alone do not constitute a regression.

**8. Can you roll back simply by swapping binaries back to the old version after migrating a database?**

Never assume so. Neo4j does not support direct downgrades; rollback typically requires restoring a pre-migration backup and handling post-cutoff writes.

## 18. Release Readiness Checklist

- [ ] Identified **source/target versions, edition, and migration path** per official Neo4j docs.
- [ ] Separated **binary upgrade**, **store migration**, **index migration**, and **Cypher language changes** into independently measurable phases.
- [ ] Recorded baseline **SHOW DATABASES/INDEXES/CONSTRAINTS**, store formats, sizes, and critical queries.
- [ ] For 4.4 → 5, handled **legacy BTREE and index-backed constraints** per the migration guide.
- [ ] Selected RANGE/TEXT/POINT/FULLTEXT/VECTOR based on **predicates and semantics**, not mechanical renaming.
- [ ] Verified index states `ONLINE`, providers, `populationPercent`, and zero failures.
- [ ] Checked **aligned/block/standard/high_limit** formats per database, especially deprecated formats.
- [ ] Ensured format conversion has backups, ample disk/temp space, offline time, and index repopulation time.
- [ ] Avoided using internal IDs or `elementId` as durable keys across migrations.
- [ ] Captured `EXPLAIN`/`PROFILE`, Rows/DB Hits, cache, CPU, GC, and p95/p99 across varied parameters.
- [ ] Compared **Cypher 5** and **Cypher 25** separately and inspected each database's default language.
- [ ] Tested Java Driver, Spring Data Neo4j, APOC/GDS plugins, CDC, and batch imports if used.
- [ ] Verified correctness suites covering nodes, relationships, constraints, paths, DTOs, and edge data.
- [ ] Used representative snapshots and benchmarked cold/warm caches plus concurrent read/write loads.
- [ ] Set **go/no-go gates** for data, performance, downtime, and write health.
- [ ] Rehearsed backup/restore in an isolated environment; planned **restore-based** rollback, not binary swap alone.
- [ ] In clusters, followed the exact-version rolling/migration runbook and preserved quorum.
- [ ] Post-cutover, monitored p95/p99, errors, query plans, index population, replication, and rollback windows.

## Official References

- [Neo4j Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/)
- [Breaking changes between Neo4j 4.4 and 5 — Indexes](https://neo4j.com/docs/upgrade-migration-guide/current/version-5/migration/breaking-changes/)
- [Migrate a database / neo4j-admin database migrate](https://neo4j.com/docs/operations-manual/current/database-administration/standard-databases/migrate-database/)
- [Store formats and migration paths](https://neo4j.com/docs/operations-manual/current/database-internals/store-formats/)
- [Cypher — Show indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/list-indexes/)
- [Cypher — Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/)
- [Neo4j Operations — Statistics and execution plans](https://neo4j.com/docs/operations-manual/current/performance/statistics-execution-plans/)
- [Cypher 25 — Select Cypher version](https://neo4j.com/docs/cypher-manual/25/queries/select-version/)
- [Neo4j Operations — Configure default Cypher version](https://neo4j.com/docs/operations-manual/current/configuration/cypher-version-configuration/)
- [Cypher — Vector indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-indexes/vector-indexes/)
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)

**Conclusion:** Safe Neo4j upgrades require **simultaneously evaluating indexes, store formats, and query plans**, not just swapping binaries cleanly. From 4.4 → 5, legacy BTREE indexes must be resolved; in modern Enterprise deployments, teams must know when to adopt `block`, offline costs, and internal ID/index impacts; from 2025.06 onward, **Cypher 5/25** compatibility and query accuracy must be verified. **Baselines, dry runs, ONLINE indexes, graph reconciliation, realistic benchmarks, and restorable backups** are the prerequisites for making grounded release or rollback decisions.
