# Rolling Out Backward-Compatible Changes Between Application and Data

## 1. Why Must Graph and Application Changes Roll Out in Stages?

Neo4j stores a property graph using nodes, relationships, labels, types, and properties; Java applications query it with Cypher via **Neo4j Java Driver** or map entities via **Spring Data Neo4j (SDN)**. When a feature renames a property, adds a relationship type, changes a constraint, or refactors graph structure, not every application instance and not every database record updates at the exact same instant.

Suppose an API currently reads `(:Customer {legacyName})`. The team wants to rename it to `displayName` and then remove `legacyName`. If a migration deletes the old property before all Java services upgrade:

- An older application reading `c.legacyName` gets `null` or fails to display names.
- Newer instances reading `c.displayName` still miss nodes not yet backfilled.
- An older background job still writing `legacyName` can make `displayName` **stale**, even after a one-time backfill.
- With SDN `repository.save(entity)` on an entity with partially loaded relationships, schema shifts can trigger unintended relationship updates.
- When a client retries a transaction or an ingestion event, data can duplicate without business keys and idempotency.

That is why the **Upgrades and Migration** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module needs a **step-by-step compatible rollout process between application and data**. The goal is not "running the fastest single script", but **preserving a verifiable upgrade path and rollback path** while multiple application versions operate concurrently.

**Learning outcomes:**

1. Distinguish **Neo4j server/driver upgrades**, **graph schema migrations**, and **application deployments**.
2. Build a compatibility matrix pairing application versions with data states.
3. Execute the **expand → migrate → contract** strategy for properties, indexes, constraints, and relationships.
4. Design dual-read, dual-write, batched backfills, reconciliation, and data auditing.
5. Write idempotent Cypher and Java/Spring Data Neo4j code with explicit transaction boundaries.
6. Pinpoint when to switch reads, when to retire legacy writers, and **the boundary where old-code rollback stops working**.
7. Plan canaries, feature flags, observability, rollback drills, and approved cleanup.

> **Scope:** examples target Neo4j 5+ and compatible Java 17+/Java Driver/SDN releases. Cypher features, constraint options, APOC, drivers, and rolling upgrade ordering vary by version, edition, and topology. Always check documentation for your exact release. All data-creating, updating, and deleting statements below are **for isolated practice databases only**; never use them directly as production rollout commands.

## 2. Three Independent Axes of Change

| Axis | Example | Compatibility requirement | Risk |
|---|---|---|---|
| **Application** | Java service V0/V1/V2, API DTOs, SDN entities, new queries | Running releases must understand any data shape they encounter | Nulls, mapper failures, legacy callers still writing |
| **Data and graph schema** | Adding `displayName`, indexes, constraints; changing relationship types | Graph must support both old and new queries during transition | Dropped properties, data divergence, double-counted relationships |
| **Neo4j platform** | Changing server/cluster, Java Driver, Cypher syntax, APOC | Client, store format, plugins, and edition must be supported | Startup failures, procedure errors, hard or impossible store downgrades |

**Do not shift all three major axes in one release** if you can separate them. For example, renaming a property on the same day as a major Neo4j server upgrade and a Spring Boot/SDN bump makes it hard to tell whether failures stem from queries, converters, or the server.

A sound roadmap places **gates** after every step: verify graph correctness, app health, error counts, latency, and rollback readiness before advancing.

## 3. The Expand → Migrate → Contract Strategy

~~~mermaid
flowchart TD
    A["B0 — Old app + old data"] --> B["EXPAND: add new schema/index/property while keeping old"]
    B --> C["Deploy bridge app: read old-first, write both"]
    C --> D["Retire all old-only writers"]
    D --> E["MIGRATE: backfill and reconcile both data versions"]
    E --> F{"Full checks pass, zero divergence?"}
    F -->|No| G["Keep old source of truth, fix issues, re-reconcile"]
    G --> E
    F -->|Yes| H["Canary switch to new-first reads, keep dual-write"]
    H --> I["Widen new reads, keep rollback window"]
    I --> J["CONTRACT: remove old dependencies, then drop old data/schema"]
    J --> K["Clean up and close runbook after verification"]
~~~

### EXPAND — Extend Without Breaking the Old Contract

- Add new properties, new indexes, or new labels/relationship types if needed; **do not immediately delete** old fields or edge types.
- Allow older application instances to keep working while newer ones roll out gradually.
- Configure uniqueness constraints on business keys before large backfills.
- Ship code aware of both formats, yet **do not switch read sources immediately**.

### MIGRATE — Transition Data and Behavior Under Control

- Run application builds capable of reading/writing both fields cleanly.
- Ensure zero legacy writers remain writing only one format, or maintain CDC/reconcilers anchored to the source of truth.
- Backfill in batches, reconcile missing/duplicate/divergent records, and handle concurrency and transient errors.
- Test against real graphs, not only mocked repositories.

### CONTRACT — Remove the Old Contract After the Rollback Window

- All readers, writers, and jobs use the new format; zero calls touch old properties or relationships.
- Backup/restore runbooks, admin scripts, materialized views, and external integrations are updated.
- Confirmed there is no need to roll back to an app version expecting only old data.
- Gradually remove old indexes, constraints, and properties in separate approved changes.

**Key rule:** *Contract is usually the hardest step to undo.* Deleting legacy data is not like toggling a feature flag: once old data is gone, old application releases can no longer run properly.

## 4. Compatibility Matrix: Which App Reads Which Data State?

Consider a concrete scenario:

- **V0:** reads/writes `legacyName`.
- **V1 (bridge):** reads **`legacyName` first**, falls back to `displayName`; writes **both**.
- **V2 (cutover):** reads **`displayName` first**, falls back to `legacyName`; still writes **both**.
- **V3 (contract):** reads/writes **only `displayName`**.

Data states:

- **D0:** only `legacyName`.
- **D1:** mixed records; some have both, some only old.
- **D2:** all required records hold **both values in sync**.
- **D3:** only `displayName` remains; old property deleted or no longer updated.

| Version | D0: old | D1: mixed | D2: both synced | D3: new |
|---|---|---|---|---|
| **V0: old-only** | Compatible | Reads old field; **can cause field drift** on writes | Reads cleanly, yet old-only writes **break sync** | **Incompatible** |
| **V1: old-first, dual-write** | Compatible, populates new field on writes | Compatible while `legacyName` is source of truth | Compatible | Falls back only until all legacy dependencies are gone; **not final target** |
| **V2: new-first, dual-write** | Fallback reads work, yet fails coverage gate | Safe only if missing/divergence are controlled | **Compatible** | May keep writing legacy property until dual-write stops |
| **V3: new-only** | **Incompatible** | **Incompatible** for records missing new field | Compatible | Compatible |

This table is not an automatic proof for every application. It **assumes identical business keys, exact property names, zero rogue writers, and atomic updates inside one transaction**.

### 4.1. Critical Trap: V0 Keeps Writing After V1 Dual-Wrote

Suppose C002 already holds:

~~~text
legacyName  = "Binh"
displayName = "Binh"
~~~

A remaining V0 instance writes:

~~~cypher
MATCH (c:QA008Customer {customerId:'C002'})
SET c.legacyName = 'Binh Edited';
~~~

Result:

~~~text
legacyName  = "Binh Edited"
displayName = "Binh"
~~~

If V2 begins **reading new-first** right now, users see the **stale** name. Running a backfill filtering only `displayName IS NULL` **will not fix it** because the new field is non-null yet divergent.

**Mitigation:** while V0 and V1 coexist, keep `legacyName` as the source of truth; drain every V0 writer (including crons, batch imports, and retry workers) and then **reconcile divergent values**, not merely missing nulls. If old writers cannot be retired cleanly, use versioning/events/CDC or a centralized write layer guaranteeing point-in-time sync.

## 5. Define Phase-Transition Criteria Using Data Invariants

"The migration script finished" is merely a technical milestone. Advancing to V2 or V3 requires proving **invariants**:

| Invariant | How to measure | Gate before new-first reads |
|---|---|---|
| All nodes have valid business IDs | Count null/duplicate IDs, constraints | **0** invalid |
| All required nodes have new name | `displayName IS NULL` on target cohort | **0** missing |
| Both fields match during dual-write window | `legacyName <> displayName` | **0** divergent |
| Zero old-only writers remain | Deployment inventory, version/caller metrics, audit logs | **0** V0 writers |
| New index ready for queries | `SHOW INDEXES` and query plans | `ONLINE` if queries rely on it |
| Dual-version APIs compatible with data | Integration/contract tests | PASS |
| Rollback has been rehearsed | Test flag toggle / app revert on staging | PASS |
| Error budget available for rollout | Error rate, p95/p99, retries | Within budget |

Use an **observation window** after counters hit zero rather than a single `COUNT`. In particular, a rarely run legacy worker may only wake up after the main migration finishes.

## 6. Cypher Fixture: Legacy Data with Ground-Truth Answers

Practice in a dedicated database. Use labels `QA008Customer`, `QA008Order`, and relationship `QA008_PLACED` so real models stay untouched.

### 6.1. Clean Up Old Fixture (Isolated Lab Only)

~~~cypher
MATCH (n)
WHERE n:QA008Customer OR n:QA008Order
DETACH DELETE n;
~~~

~~~cypher
DROP CONSTRAINT qa008_customer_id_unique IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa008_order_id_unique IF EXISTS;
~~~

~~~cypher
DROP INDEX qa008_customer_display_name IF EXISTS;
~~~

Never run this in a real database or any database sharing these labels. Deleting relationships via `DETACH DELETE` is **destructive**, so confine it strictly to an isolated lab.

### 6.2. Business Keys and Data

~~~cypher
CREATE CONSTRAINT qa008_customer_id_unique IF NOT EXISTS
FOR (c:QA008Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT qa008_order_id_unique IF NOT EXISTS
FOR (o:QA008Order)
REQUIRE o.orderId IS UNIQUE;
~~~

~~~cypher
UNWIND [
  {id:'C001', name:'An'},
  {id:'C002', name:'Binh'},
  {id:'C003', name:'Chi'},
  {id:'C004', name:'Dung'},
  {id:'C005', name:'Em'},
  {id:'C006', name:'Giang'}
] AS row
CREATE (:QA008Customer {
  customerId:row.id,
  legacyName:row.name
});
~~~

~~~cypher
UNWIND [
  {id:'O001', amount:100, customer:'C001'},
  {id:'O002', amount:200, customer:'C002'},
  {id:'O003', amount:300, customer:'C002'}
] AS row
MATCH (c:QA008Customer {customerId:row.customer})
CREATE (o:QA008Order {
  orderId:row.id,
  amount:row.amount
})
CREATE (c)-[:QA008_PLACED]->(o);
~~~

### 6.3. Baseline D0 Ground Truth

~~~cypher
MATCH (c:QA008Customer)
RETURN count(c) AS customers,
       count(c.legacyName) AS oldPresent,
       count(c.displayName) AS newPresent;
~~~

| customers | oldPresent | newPresent |
|---:|---:|---:|
| **6** | **6** | **0** |

~~~cypher
MATCH (o:QA008Order)
RETURN count(o) AS orders, sum(o.amount) AS sumAmount;
~~~

**Expected:** `orders=3`, `sumAmount=600`.

~~~cypher
MATCH ()-[r:QA008_PLACED]->()
RETURN count(r) AS relationships;
~~~

**Expected:** `relationships=3`; C001 has one order, C002 has two orders, and C003–C006 have none. When migrating **only the name property**, these counts **must remain unchanged**.

## 7. EXPAND Phase: Add Capabilities Without Deleting Old Formats

### 7.1. Keep Both Properties During Transition

For Neo4j to accept `displayName`, **no RDBMS-style `ALTER TABLE` is required**: property graphs allow nodes to hold varying property sets.

However, if new queries filter by `displayName`, an index may be needed:

~~~cypher
CREATE RANGE INDEX qa008_customer_display_name IF NOT EXISTS
FOR (c:QA008Customer) ON (c.displayName);
~~~

This is an **index**, not a constraint forcing every node to carry the new field. Create it only when workloads need it, measure write maintenance overhead, and check its state:

~~~cypher
SHOW INDEXES
YIELD name, type, state, labelsOrTypes, properties
WHERE name='qa008_customer_display_name'
RETURN name, type, state, labelsOrTypes, properties;
~~~

Wait for `ONLINE` before treating lookups on the new property as ready. On a 6-node fixture, an index yields no meaningful performance benchmark.

### 7.2. Do Not Add Mandatory Property Constraints Too Early

Before backfill, D0 nodes lack `displayName`. Enforcing a rule requiring every node to carry the new name breaks new writes or legacy operations; some property existence constraints also depend on **Enterprise Edition** and version.

Safe sequence:

1. Create non-breaking indexes if needed.
2. Deploy dual-write application code to production.
3. Backfill and repair divergences.
4. Confirm all readers/writers use the new format.
5. **Only afterward** evaluate existence/type constraints on `displayName` per edition capabilities.

Likewise, `IF NOT EXISTS` only makes DDL re-runnable; it **does not verify** an existing index/constraint matches your intended type, properties, or options. Inspect actual `SHOW INDEXES`/`SHOW CONSTRAINTS`.

## 8. V1 Bridge Application Phase: Read Old-First, Write Both Fields

Compatible read while `legacyName` remains source of truth:

~~~cypher
MATCH (c:QA008Customer {customerId:$id})
RETURN c.customerId AS customerId,
       coalesce(c.legacyName,c.displayName) AS name;
~~~

`coalesce` returns the first non-null value. While V0 still runs, prioritizing the old field avoids serving stale new names. Yet never mistake `coalesce` for a synchronization check: it can mask data divergence. Track dedicated metrics instead.

Dual-write **inside the same transaction**:

~~~cypher
MERGE (c:QA008Customer {customerId:$id})
SET c.legacyName=$name,
    c.displayName=$name
RETURN c.customerId AS customerId;
~~~

Updating both properties in one Neo4j transaction commits or rolls back both together. Never update `legacyName` in transaction A and `displayName` in transaction B: between commits, readers observe split state, and a failure on step two leaves fields out of sync.

**Note on `MERGE`:** match on `customerId` backed by a uniqueness constraint; under concurrent workloads, clients still need proper retries and constraint error handling. Never use arbitrary `CREATE` inside retried transaction functions, and never place email/payment side effects inside write callbacks.

## 9. Java Driver: Code Compatible with Old and New Data

Java applications use a long-lived `Driver`, short-lived `Session`, and explicit database selection. Example using Driver 5.x synchronous API:

~~~java
import java.util.Optional;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

public final class CustomerCompatibility {

    public static Optional<String> readLegacyFirst(
            Driver driver, String database, String id) {
        try (Session session = driver.session(
                SessionConfig.forDatabase(database))) {
            return session.executeRead(tx -> {
                var result = tx.run("""
                    MATCH (c:QA008Customer {customerId:$id})
                    RETURN coalesce(
                        c.legacyName,c.displayName
                    ) AS name
                    """, Values.parameters("id", id));

                if (!result.hasNext()) {
                    return Optional.empty();
                }
                var name = result.next().get("name");
                return name.isNull()
                    ? Optional.empty()
                    : Optional.of(name.asString());
            });
        }
    }

    public static void upsertBoth(
            Driver driver, String database,
            String id, String name) {
        try (Session session = driver.session(
                SessionConfig.forDatabase(database))) {
            session.executeWrite(tx -> {
                tx.run("""
                    MERGE (c:QA008Customer {customerId:$id})
                    SET c.legacyName=$name,
                        c.displayName=$name
                    """, Values.parameters(
                        "id", id, "name", name
                    )).consume();
                return null;
            });
        }
    }
}
~~~

**Why is this safer than string concatenation?**

- `$id`/`$name` are parameters, never concatenated from HTTP inputs.
- `executeWrite` manages transactions and retries; both properties update atomically in one transaction.
- `Result` is consumed inside the transaction without leaking cursors outside the session.
- `SessionConfig.forDatabase` avoids hitting the wrong home database.
- The reader returns `Optional<String>` so callers distinguish missing nodes; real APIs may also distinguish **node exists with null name** from missing node.

**Required additions for production:** ID and name validation, authorization, timeouts, observability, idempotency keys if APIs retry, and integration tests alongside active app versions. Never print PII via `System.out` during rollout debugging.

### 9.1. V2 Switches Only Read Preference, Not Stopping Dual-Write

Once data reaches D2 and V0 is completely retired:

~~~cypher
MATCH (c:QA008Customer {customerId:$id})
RETURN coalesce(c.displayName,c.legacyName) AS name;
~~~

Keep the fallback during a rollout window to catch missing records, while **monitoring fallback rate**. If fallbacks rise, halt the rollout: a stray old writer or incomplete backfill likely exists.

## 10. Spring Data Neo4j: Mapping Both Properties During Transition

In SDN, never merely rename a Java field expecting the database property to rename itself. Whenever graph property names differ from Java fields, declare `@Property` explicitly.

Example transition entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Property;

@Node("QA008Customer")
public class Customer {
    @Id
    private String customerId;

    @Property("legacyName")
    private String legacyName;

    @Property("displayName")
    private String displayName;

    protected Customer() {}

    public String nameForLegacyReaders() {
        return legacyName != null
            ? legacyName : displayName;
    }

    public String nameForNewReaders() {
        return displayName != null
            ? displayName : legacyName;
    }
}
~~~

**Points to test:**

- Repository reads D0 nodes with `displayName=null` without mapping errors.
- Repository reads D2 nodes with both values accurate.
- Entity uses `@Id` on the business key, never accidentally substituting internal/element IDs.
- If the entity also declares `@Relationship`, verify whether custom queries hydrate the full graph before calling `save`.
- Spring transactions manage repositories/`Neo4jClient`; opening a separate `Driver.session()` transaction **does not automatically join** Spring's `@Transactional`.

For targeted updates touching **only two scalar properties**, an explicit `@Query` or `Neo4jClient` Cypher query is usually safer than `repository.save(entity)` when entity graphs carry many relationships.

Example write via `Neo4jClient`:

~~~java
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerNameWriter {
    private final Neo4jClient client;

    public CustomerNameWriter(Neo4jClient client) {
        this.client = client;
    }

    @Transactional
    public void rename(String id, String name) {
        client.query("""
            MERGE (c:QA008Customer {customerId:$id})
            SET c.legacyName=$name,
                c.displayName=$name
            RETURN c.customerId AS id
            """)
            .bind(id).to("id")
            .bind(name).to("name")
            .fetchAs(String.class)
            .mappedBy((typeSystem, record) ->
                record.get("id").asString())
            .one()
            .orElseThrow();
    }
}
~~~

If this method shares `@Transactional` with other SDN calls, they can participate in the configured Spring transaction. Never mix in a standalone Java Driver transaction expecting Spring rollback to undo both.

## 11. MIGRATE Phase: Re-Runnable Batched Backfill

Only after **retiring V0 writers**—or establishing source-of-truth guarantees and concurrent write handling—should you backfill from the old value.

### 11.1. Test First on Two Customers

~~~cypher
MATCH (c:QA008Customer)
WHERE c.customerId IN ['C001','C002']
SET c.displayName = c.legacyName;
~~~

Check:

~~~cypher
MATCH (c:QA008Customer)
RETURN count(c) AS total,
       count(c.legacyName) AS oldPresent,
       count(c.displayName) AS newPresent;
~~~

**D1 output:** `total=6`, `oldPresent=6`, `newPresent=2`.

### 11.2. Batch Query for Missing or Divergent Rows

~~~cypher
MATCH (c:QA008Customer)
WHERE c.legacyName IS NOT NULL
  AND (
    c.displayName IS NULL OR
    c.displayName <> c.legacyName
  )
WITH c
ORDER BY c.customerId
LIMIT $batchSize
SET c.displayName = c.legacyName
RETURN count(c) AS repaired;
~~~

The job invokes this with a reasonable `batchSize` such as 100 or 500, commits each batch, and loops until `repaired=0`. The logic is idempotent: once every record matches on both fields, re-running modifies nothing.

**Never run this unconditionally while writers exist for opposing sources of truth.** This query treats `legacyName` as canonical; if V2 or V3 already started writing **only the new field**, newer values would be overwritten by older ones. Under concurrent writes, enforce a single source of truth via event queues/versions/checkpoints or an approved write freeze.

### 11.3. Expected Result After Full Backfill

~~~cypher
MATCH (c:QA008Customer)
RETURN count(c) AS total,
       count(c.legacyName) AS oldPresent,
       count(c.displayName) AS newPresent;
~~~

| total | oldPresent | newPresent |
|---:|---:|---:|
| **6** | **6** | **6** |

Every customer holds both names; order and relationship counts **remain 3 and 3**. Property backfills must never alter node/relationship counts.

### 11.4. Why Not One Transaction for Millions of Nodes?

Oversized transactions inflate:

- Transaction state memory and lock hold durations.
- Transaction log pressure, checkpoints, and CPU/index maintenance.
- Rollback/retry time and blast radius when a single statement fails.
- Write amplification and tail latency for live API traffic.

Batch work and measure `repaired/s`, commit latency, business p95/p99, lock waits, and transient errors. You can use `CALL { ... } IN TRANSACTIONS` when supported by your Cypher version, noting **it uses an implicit transaction model** and scope syntax evolved across Neo4j 5/Cypher 25; never wrap it inside `executeWrite` or an outer Spring transaction.

Example for Cypher versions supporting **variable-scope CALL**:

~~~cypher
MATCH (c:QA008Customer)
WHERE c.legacyName IS NOT NULL
CALL (c) {
  SET c.displayName = c.legacyName
} IN TRANSACTIONS OF 100 ROWS;
~~~

This illustrates a **stable lab database**. On older servers, use the corresponding `CALL { WITH c ... }` syntax; run `EXPLAIN` and check exact version docs. In production, implement retries, checkpoints, and logging rather than running a full-dataset query blindly just because the snippet is short.

## 12. Data Reconciliation: Counting Missing, Divergent, and Invalid Records

### 12.1. Accurately Count Migration States

~~~cypher
MATCH (c:QA008Customer)
RETURN
  count(c) AS total,
  count(CASE WHEN c.legacyName IS NULL
                AND c.displayName IS NULL THEN 1 END)
    AS missingBoth,
  count(CASE WHEN c.legacyName IS NOT NULL
                AND c.displayName IS NULL THEN 1 END)
    AS missingNew,
  count(CASE WHEN c.legacyName IS NOT NULL
                AND c.displayName IS NOT NULL
                AND c.legacyName <> c.displayName
             THEN 1 END)
    AS divergent;
~~~

On D0: `total=6`, `missingBoth=0`, `missingNew=6`, `divergent=0`.

After backfill D2: `total=6`, `missingBoth=0`, `missingNew=0`, `divergent=0`.

**Note:** A record holding `displayName` without `legacyName` is not counted in `missingNew` or `divergent`. While V1/V2 still dual-write and the legacy field remains required, also measure **missingOld**:

~~~cypher
MATCH (c:QA008Customer)
WHERE c.legacyName IS NULL
  AND c.displayName IS NOT NULL
RETURN count(c) AS missingOld;
~~~

In D2 before contract, expect `missingOld=0`. After D3, `missingOld` grows and **is no longer an error** once the contract has fully switched.

### 12.2. Detect Missing IDs and Anomalous Records

~~~cypher
MATCH (c:QA008Customer)
WHERE c.customerId IS NULL
RETURN count(c) AS missingIds;
~~~

~~~cypher
MATCH (c:QA008Customer)
WITH c.customerId AS id, count(*) AS amount
WHERE id IS NOT NULL AND amount > 1
RETURN id, amount
ORDER BY amount DESC
LIMIT 10;
~~~

A uniqueness constraint only blocks duplicates among **non-null values**; it does not automatically require every node to carry `customerId`. Never treat `SHOW CONSTRAINTS` output as proof of zero missing properties.

### 12.3. Logical Checksums on Large Datasets

Matching `count` does not prove every node is right. Beyond counts:

- Take deterministic seeded samples by `customerId`.
- Compare canonical field values per record ID.
- Reconcile business aggregates (order counts, total amounts, relationship counts).
- Track client error counts and retried records.
- If full-dataset hashing/checksums are required, use a deterministic, null/encoding-normalized, memory-bounded pipeline. Never build one giant `collect` to hash an entire graph in a single transaction.

## 13. Demonstrating Divergence Caused by a Lingering Legacy Writer

This exercise demonstrates a bug missed by null-only backfills.

Suppose the graph is at D2, and **one V0 lab instance** runs:

~~~cypher
MATCH (c:QA008Customer {customerId:'C002'})
SET c.legacyName = 'Binh Edited';
~~~

Inspect:

~~~cypher
MATCH (c:QA008Customer)
WHERE c.legacyName IS NOT NULL
  AND c.displayName IS NOT NULL
  AND c.legacyName <> c.displayName
RETURN c.customerId AS id,
       c.legacyName AS legacy,
       c.displayName AS newer;
~~~

**Result:** one row, `id='C002'`; `legacy='Binh Edited'` and `newer='Binh'`. A query checking only `c.displayName IS NULL` returns 0, even though **one divergence** exists.

After confirming all old-only writers stopped and `legacyName` remains canonical, run the repair batch query from section 11.2. Post-repair check:

~~~cypher
MATCH (c:QA008Customer {customerId:'C002'})
RETURN c.legacyName AS legacy,
       c.displayName AS newer;
~~~

Both must equal **"Binh Edited"**. Then `divergent=0`. Do not switch to new-first reads until multiple observation checks pass, not just one immediate post-fix count.

## 14. Shifting Read Sources with Canaries and Feature Flags

Once gates pass:

1. **Lock canonical definition:** V0 retired, V1/V2 still dual-write; no forgotten legacy writers.
2. **Reconcile:** all required nodes hold `displayName`, `divergent=0`, new index `ONLINE` if needed.
3. **Canary:** enable `coalesce(displayName,legacyName)` on a small slice of requests/instances.
4. **Compare:** identical business IDs, response payloads, error rates, p95/p99, read/write throughput, and fallback rate.
5. **Widen gradually:** 1% → 5% → 25% → 100% (illustrative percentages depending on org policy).
6. **Keep dual-write:** while the rollback window to V1 stays open, keep updating `legacyName`.
7. **Close observation window:** only after multiple full cron/queue/import cycles confirm zero V0 writers remain.

**Feature flags do not automatically guarantee consistency.** If one instance flips `readNew` on while another has not backfilled or dual-written properly, APIs can return conflicting values for the same ID. Manage flags per environment/workflow with fast kill-switches and dedicated error metrics.

### 14.1. Observe Fallbacks Instead of Silently Hiding Errors

~~~cypher
MATCH (c:QA008Customer)
RETURN
  count(CASE WHEN c.displayName IS NULL
             AND c.legacyName IS NOT NULL
             THEN 1 END) AS needFallback,
  count(CASE WHEN c.displayName IS NOT NULL
             THEN 1 END) AS readyNew;
~~~

In the D2 fixture, `needFallback=0` and `readyNew=6`. In production, measure this over **the active subset users actually query**, not just total graph counts; even 0.01% missing can be severe if it affects top customers.

## 15. Relationship Migration: Data Can Be Double-Counted

Renaming a property usually carries less blast radius than **changing an edge type**, e.g. from:

~~~cypher
(c:Customer)-[:PLACED]->(o:Order)
~~~

to:

~~~cypher
(c:Customer)-[:ORDERED]->(o:Order)
~~~

If both edge types coexist on the same node pair, both old and new queries find the order, yet an aggregate query using:

~~~cypher
MATCH (c)-[:PLACED|ORDERED]->(o)
RETURN count(*) AS edges;
~~~

can **double-count** an order because two edges carry the same business meaning. When multiple relationships can legitimately connect the same nodes, do not treat `count(DISTINCT o)` as a universal "fix" if business logic distinguishes transactions; establish explicit relationship identity instead.

### 15.1. Controlled Relationship Migration in the Lab

The fixture uses `QA008_PLACED`. Adding a new type `QA008_ORDERED` can be illustrated idempotently:

~~~cypher
MATCH (c:QA008Customer)-[:QA008_PLACED]->(o:QA008Order)
MERGE (c)-[:QA008_ORDERED]->(o);
~~~

On the fixture, `QA008_ORDERED` creates **3** new relationships if absent. `QA008_PLACED` remains 3; total across both types is 6, yet only 3 logical customer/order pairs exist.

~~~cypher
MATCH (c:QA008Customer)-[:QA008_PLACED|QA008_ORDERED]->
      (o:QA008Order)
RETURN count(*) AS rawEdges,
       count(DISTINCT o) AS distinctOrders;
~~~

**Illustrative result:** `rawEdges=6`, `distinctOrders=3` in this fixture because each order belongs to exactly one customer.

**Caution:** `MERGE (c)-[:REL]->(o)` does not enforce uniqueness across all relationship types nor deduplicate pre-existing duplicates; verify invariants before and after. If relationships carry properties (`role`, `createdAt`, `amount`), copy values accurately by business key rather than creating "empty" edges that lose data.

### 15.2. Designing Safe Relationship Transitions

- Keep old apps reading `QA008_PLACED`, while new apps read both with **business-key deduplication**.
- If dual-writing both relationship types, perform both writes inside one transaction.
- Once old-only writers are gone, batch-backfill new edges and verify completeness.
- Once all readers switch to the new type, retain old edges for the rollback window.
- Delete old relationships only when zero dependencies remain and backups/forward recovery are ready.

If creating duplicate edges is unacceptable, use a **Cypher read bridge** or API mapping layer during transition instead of defaulting to dual-writing relationships.

## 16. Indexes and Constraints: "Additive" Changes Also Need Preparation

A migration may simultaneously swap unique keys, such as transitioning from `customerId` to `externalKey`.

**Risk:** not every node has `externalKey` yet; new values may contain duplicates or nulls; creating the unique constraint fails, or succeeds while leaving nodes **missing the property** because uniqueness does not imply existence.

Procedure:

1. Define the new key, data type, normalization rules, and uniqueness scope.
2. Backfill `externalKey` from an authoritative source and log failing records.
3. Check for missing/duplicate values **before** creating the new constraint.
4. Create the new constraint/index **with a distinct name** and wait for `ONLINE`.
5. Roll out readers/writers using the new key while preserving the old key during transition.
6. Test `MERGE`, concurrency, idempotency, and Cypher execution plans.
7. Drop the old index/constraint only after the rollback window closes.

For graphs querying relationships and paths, changing an index on the **starting label/node** can change query plans. Run `EXPLAIN`/`PROFILE` on critical queries **across both old and new apps** while indexes coexist.

### Do Not Drop Old Indexes Too Early

Legacy indexes may still serve queries from un-upgraded instances. Merging code into Git does not prove every background worker or batch script has deployed. Use query logs, repository inventories, and metrics to verify zero remaining dependencies before dropping an index.

## 17. Migration Must Not Treat the Database as the Entire System

Clients that may still depend on the old model:

| Component | Dependency example | Verification |
|---|---|---|
| Direct Java API via Driver | `RETURN c.legacyName` | Search Cypher in running services and jobs |
| Spring Data Neo4j | `@Property("legacyName")`, `@Query` repositories | Entities/projections, mappings, and `save` |
| CSV / batch imports | Header `legacy_name` mapped to property | Pipelines, schedulers, replay data |
| Kafka/CDC/outbox | Legacy event schemas | Consumer versioning, offsets, replays |
| Reports/BI | Scheduled Cypher queries | Report engines, dashboards, schedules |
| Manual/admin queries | APOC procedures, ops scripts | Runbooks, permissions, maintenance jobs |
| Downstream caches/search | Old display name field in index | Rebuilds/invalidations and drift checks |
| Backups and DR sites | Restoring old DB while new app runs | Test restores and post-restore migrations |

**Goal:** zero "hidden" write paths breaking invariants. Maintain a **versioned deployment manifest** recording app releases, background jobs, event schemas, Neo4j DBMS/Driver/SDN versions, and feature flag activation times.

Even a "successful" migration can fail business startup if a D0 backup restores into an environment running only V3. Disaster recovery runbooks must know how to restore old data and run expand/backfill before starting V3 apps, or retain D2/D3 backups per policy.

## 18. Rolling Deployments Across Multiple App Instances and Neo4j Clusters

### 18.1. Roll Applications Carefully, Contract Data Later

In Kubernetes or multi-VM deployments, never assume all instances update simultaneously. When deploying V1:

- V0 and V1 pods serve requests side by side.
- In-flight requests, queue consumers, and scheduled jobs still run legacy logic.
- Rollback readiness requires **data to still satisfy V0's contract**.

Design the mixed-version application phase intentionally; never confuse "rolling restart of app pods" with "atomic data migration".

### 18.2. Rolling Neo4j Server Upgrades Differ from Schema Migrations

Upgrading **Neo4j DBMS/clusters** is a separate discipline. Some releases support rolling upgrades within documented compatibility bounds; other transitions require offline store upgrades/migrations or restrict mixing member versions.

Never claim "just upgrade one primary at a time" works for every version pair. Before executing:

1. Verify source version, target version, edition, topology, and vendor-supported upgrade path.
2. Verify Java Driver, Spring Boot/SDN, APOC, GDS/custom procedures, Cypher deprecations, index providers, and store formats.
3. Back up all required databases, including system metadata if recovery requires it.
4. Rehearse an upgrade on a restored production dataset or equivalent staging environment.
5. Test schema/logic and client failover/routing after changing versions.
6. Never expect to **downgrade store formats** simply by reinstalling the old binary.

**Application rollback** and **DBMS rollback** are not the same. Once a store upgrades past backward compatibility, recovery may require **restoring from a verified backup**, carrying its own RPO/RTO implications.

### 18.3. Limitations When Handling Multiple Databases

When splitting across multiple databases or tenants, each database may sit in a different migration state. V2 code reading two databases simultaneously must rely on explicit **compatibility contracts**; cross-database operations are not atomic distributed transactions by default. Implement sagas, outboxes, or reconciliation when workflows span databases.

## 19. Observing Migration via Metrics and Logs

Collect **data correctness** and **application experience** metrics together:

| Metric | Meaning |
|---|---|
| `missingNew`, `missingOld`, `divergent` | Record migration state and consistency |
| Active V0/V1/V2/V3 writer counts | Measures whether live write streams remain compatible |
| Backfill batches/s, rows/s, retry rate | Migration progress and DB load |
| Read fallback count/rate | Catches unmigrated records when shifting read source |
| API p50/p95/p99, errors/timeouts | Alerts on service degradation |
| Neo4j transactions/lock waits/commit latency | Detects contention caused by backfill |
| CPU, heap/GC, page cache, disk log I/O | Checks if backfill starves resources |
| Index population/state | Confirms new queries have ready schemas |
| Cluster bookmark/routing errors | Ensures clients read-their-writes accurately |
| Query logs still referencing old property | Reveals unmigrated readers or jobs |

Illustrative hypothetical "gates" before widening canary traffic:

- 100% of new-reading instances use exact target config and database.
- `missingNew=0` and `divergent=0` across multiple check cycles.
- Zero legacy writers observed across at least one full cycle of all scheduled jobs.
- Error rates and p95 remain within defined baselines/SLOs.
- Zero constraint/index incidents, lock timeouts, or retry storms.

Never place real customer names or emails into metric labels or debug logs. On large graphs, scanning the entire graph every second for divergence wastes resources; use batched scans, sampling, and periodic full audits in safe windows.

## 20. Rollback: When Can You Revert the App, and When Can't You?

| Point in rollout | Can roll app back to V1/V0? | Data to preserve | Warning |
|---|---|---|---|
| After EXPAND, before backfill | Usually **yes** if old contract intact | `legacyName` | New index can stay temporarily; no need to drop immediately |
| During V1 dual-write, V0 retired | **V1** yes; **V0** only if accepting new divergence risk | Both, old canonical | Rolling back to V0 requires re-reconciliation before cutover |
| During V2 new-first reads, still dual-writing | **V1** usually yes; V0 needs evaluation | Both synced values | Disable readNew and audit divergence |
| Stopped old writes, field not yet deleted | Reverting to V1/V0 may need reverse backfill | `legacyName` must stay updated | Old names may already be stale |
| Deleted `legacyName` (D3) | **Cannot** simply roll back to V0/V1 and run | Need restored/reconstructed old data | Prefer forward-fix or restore per runbook |
| Major Neo4j store upgraded | Depends on version pair; may **not** downgrade | Pre-upgrade compatible backup | Reverting binary does not guarantee reading new store |

**Rolling back via database restore risks losing business updates.** Hence application rollback via feature flags is far less risky than database rollback—**but only while the data still honors the old contract**.

### 20.1. Forward-Fix Instead of Deleting Data

If V2 encounters records missing `displayName`, toggle off `readNew`, fix the pipeline, and backfill/reconcile affected rows. That is a **controlled forward-fix**.

Never run `REMOVE c.displayName` in production to "go back to V0" once newer writers have treated `displayName` as source of truth; that wipes updates absent from `legacyName`.

## 21. CONTRACT Phase: Delete Legacy Only After All Consumers Migrate

Minimum prerequisites:

1. Inventory confirms zero read/write code, batch jobs, event consumers, or admin scripts need `legacyName`.
2. V3 runs stably and `displayName` is populated completely and accurately.
3. No intention remains to roll back to V0/V1, or approved restore/forward-transform plans exist.
4. Backup/DR runbooks align with D3; pre- and post-migration restores have been tested.
5. Queries use the new index reliably; old indexes can retire with impact evaluated before dropping.

### 21.1. Destructive Cleanup Illustration — Lab Only

In the practice database, once V3 no longer needs `legacyName`:

~~~cypher
MATCH (c:QA008Customer)
WHERE c.legacyName IS NOT NULL
WITH c
ORDER BY c.customerId
LIMIT $batchSize
REMOVE c.legacyName
RETURN count(c) AS removed;
~~~

Run in batches until `removed=0`. **Never run this in production straight from a lesson example**: it erases the legacy field and eliminates code rollback paths. Replace with a reviewed, tested, backed-up, and approved migration job.

After D3 contract on 6 nodes:

~~~cypher
MATCH (c:QA008Customer)
RETURN count(c) AS customers,
       count(c.legacyName) AS oldPresent,
       count(c.displayName) AS newPresent;
~~~

**Result:** `customers=6`, `oldPresent=0`, `newPresent=6`.

When dropping legacy constraints/indexes, re-evaluate `EXPLAIN`/`PROFILE` for `MATCH`/`MERGE` queries on new keys. Never drop the fixture's `qa008_customer_id_unique` constraint if the system still identifies customers by `customerId`: a constraint is not "legacy" merely because its name resembles migration fixtures.

## 22. Test the Upgrade Strategy Before Production Rollout

### 22.1. Minimum Integration Test Matrix

| Case | Setup | Required outcome |
|---|---|---|
| V0 reads D0 | Only legacyName | Returns accurate names |
| V1 reads D0 | Fallback before dual-write runs | Returns accurate names |
| V1 writes D1 | Update C001 | Both properties update atomically |
| V0 writes after D2 | Simulate old-only writer | Divergence query detects mismatch |
| Backfill after stopping V0 | C002 diverged | Resyncs C002; count returns to 0 |
| V2 reads D2 | New-first | Returns new values; fallback=0 |
| V2 rolls back to V1 | Both properties synced | Zero errors or lost updates |
| V3 reads D3 | Only displayName | Every node has name |
| V0 reads D3 | No legacyName | **Test must prove incompatibility** |
| Old/new edges coexist | Both types on same pair | Aggregate queries never double-count |
| Unique constraint / null ID | Invalid input data | Exact expected write error; zero duplicate nodes |
| Migration interrupted midway | Partial batches committed | Idempotent resume; zero data loss |

Do not rely solely on hand-crafted DTO unit tests. Use Neo4j Testcontainers or staging with fixtures running real Java Driver, SDN repositories/custom `@Query`, schema commands, and transactions.

### 22.2. Testing Rollback Does Not Always Require DROP/DELETE

To verify reverting to V1, **toggle feature flags** without deleting new properties. Simulate D3/contract only in an isolated test database. Never use production to "prove rollback is impossible" by deleting data.

### 22.3. Performance and Concurrency

Run before/after workloads on identical datasets, client concurrency, and server versions. Measure:

- `read fallback`, `p95/p99`, and `DB Hits` when using `coalesce`.
- Extra write overhead from dual-write and new indexes.
- Backfill duration, lock waits, transaction log volume, page cache, and CPU/GC.
- Retries/timeouts across `executeWrite` and Spring transactions.
- Correctness across rows updated concurrently during backfill.

With a 6-node fixture, **never use millisecond timings as performance benchmarks**. Use representative datasets for benchmarking and fixtures for logic verification.

## 23. Multi-Gate Rollout Runbook

A runbook can be structured as:

| Step | Action | PASS criteria | On FAIL |
|---|---|---|---|
| **0** | Inventory apps/jobs/schemas, capture baseline & restore-tested backup | Clear source of truth and rollback path | Do not deploy |
| **1** | Expand auxiliary indexes/properties/constraints | Legacy code works, indexes `ONLINE` | Halt; do not contract |
| **2** | Canary V1 old-first dual-write | APIs accurate, zero permission/mapping errors | Roll back V1; keep additive schema |
| **3** | Roll out V1 100%, retire V0 writers | Zero old-only writers via deploy+metrics | Do not backfill/switch source yet |
| **4** | Backfill and reconcile batches | MissingNew=0, divergent=0 steadily | Shrink batch; fix sources/locks |
| **5** | Canary V2 new-first dual-write | Low/zero fallbacks, p95 and errors healthy | Toggle flag back to old-first |
| **6** | Widen V2, observe across batch schedules | Zero divergence | Audit writers / event replay |
| **7** | Switch to V3 new-only | Zero old consumers; DR backups updated | Do not delete legacy yet |
| **8** | Contract: approved batched legacy cleanup | Data/schema and DR tests PASS | Halt cleanup; prefer forward-fix |
| **9** | Close migration and update documentation | SLOs healthy, alerts clear, restore drill passed | Do not declare complete |

At each step, record approver, UTC timestamp, deployed versions, record counts, and observed errors. Never wait until contract to write a rollback plan; **the exit path must be ready from step 0**.

## 24. Common Errors and Troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| V2 occasionally reads old names | V0 still writes legacy-only while V2 prefers new | Stop V0, measure divergence, and reconcile |
| `missingNew=0` yet data is wrong | Backfill only filled nulls, skipping divergent values | Compare both values, not just nullness |
| New constraint fails | Duplicates, nulls, or type mismatches | Audit and clean data before creating |
| `IF NOT EXISTS` succeeds yet schema differs | Another index/constraint claimed the name | Reconcile via `SHOW INDEXES/CONSTRAINTS` |
| Some jobs still write legacy format | Updated HTTP APIs but missed schedulers/consumers | Inventory all writers, query logs, and versions |
| SDN save drops relationships | Entity loaded partially or mapping shifted | Test relationships; use targeted Cypher scalar updates |
| Dual-write leaves new field null | Two writes ran in separate transactions or missed code path | Atomic dual-write and rollback tests |
| Data doubles after relationship migration | Both edge types coexist | Count by business key; manage dual-read/write phase |
| Rolling back to V0 fails after dropping old property | Crossed the contract boundary | Forward-fix or restore per runbook |
| Migration causes heavy DB load | Oversized batches, locks/IOPS/index maintenance | Throttle, shrink batches, watch p95 and lock waits |
| Cannot downgrade after major Neo4j upgrade | Store format changed; downgrade unsupported | Restore compatible backup per upgrade guide |
| D0 backup fails with V3 app | DR lacks post-restore migration steps | Add compatibility gates to restore runbook |

## 25. Exercises with Solutions

### Exercise 1 — Rollout Ordering

A V0 app knows only `legacyName`. The team wants to delete it and use `displayName`. Should they delete the old field before deploying the new app?

**Answer:** No. First expand/deploy V1 compatibility and dual-write, retire legacy writers, backfill/validate, switch reads in V2, and contract only once zero dependencies remain.

### Exercise 2 — D0 Fixture Data

The fixture has six customers, three orders, and three relationships. Right after creating the fixture, what is `count(c.displayName)`?

**Answer:** **0**, because only `legacyName` exists. `count(c.legacyName)=6`; orders and relationships are both 3.

### Exercise 3 — Partial Backfill

Run backfill for C001 and C002. How many customers hold both fields, and how many still lack the new field?

**Answer:** **2** customers hold both, **4** customers still lack `displayName`; total remains 6.

### Exercise 4 — Old-Only Writer Bug

After D2, V0 edits `C002.legacyName` from "Binh" to "Binh Edited" without updating `displayName`. Does a query counting `displayName IS NULL` detect this bug?

**Answer:** No. `displayName` is still non-null ("Binh"); you must count `legacyName <> displayName`. Switch reads only after retiring old writers and reconciling.

### Exercise 5 — Idempotent Backfill

Why can the batch query in section 11.2 re-run without creating extra customers?

**Answer:** It `MATCH`es existing nodes and `SET`s properties without `CREATE`, modifying only missing/divergent rows. Source-of-truth governance and concurrent write control remain required.

### Exercise 6 — Java Transactions

Why is writing `legacyName` and `displayName` in **two separate transactions** dangerous?

**Answer:** One transaction can commit while the other fails; readers observe mismatched values. Wrap both updates inside one transaction with idempotent retries.

### Exercise 7 — Relationship Migration

Three customer/order pairs carry both `QA008_PLACED` and `QA008_ORDERED`. What are `count(*)` over the dual-type pattern and `count(DISTINCT o)`?

**Answer:** `count(*)=6` edges, yet `count(DISTINCT o)=3` unique orders in the fixture. Depending on domain rules, identify relationships properly rather than blindly masking duplicates with DISTINCT everywhere.

### Exercise 8 — When to Drop Legacy?

If V2 reads the new field while a weekly batch job still reads only `legacyName`, can you delete the old field after two days?

**Answer:** No. You have not passed the "all consumers migrated" gate. Upgrade the batch job, observe across an appropriate cycle, and test rollback/restore before contracting.

### Exercise 9 — New Index and Old Queries

Why not drop the old index immediately after creating the index on `displayName`?

**Answer:** Legacy instances/jobs still query `legacyName` and may depend on the old index. Measure `EXPLAIN/PROFILE`, inventory dependencies, and drop only when zero legacy readers remain.

### Exercise 10 — Server Version Upgrades

A cluster just underwent a major Neo4j upgrade. Can you revert to the old binary just like rolling back a Java app?

**Answer:** Not by default. Store-format/version compatibility may forbid direct downgrades; follow only supported paths or restore compatible backups.

### Exercise 11 — Rollback After D3

All nodes dropped `legacyName`. The team reverts to app V0 due to a UI bug. Is that safe?

**Answer:** No. V0 reads a deleted field. Forward-fix, deploy a compatible app, or perform controlled data restoration/transformation rather than merely swapping app images.

### Exercise 12 — Valid Test Assertions

A test only asserts that two app versions return the same name string without checking expected values from the fixture. Is that sufficient verification?

**Answer:** Not yet. Both could return the exact same wrong value. Assert expected literals per business ID, inspect real graph state, and reconcile nulls/divergence/relationships.

## 26. Cleaning Up Practice Data and Official References

### 26.1. Cleanup — Test Database Only

After completing the lesson, you may remove **only the fixture**:

~~~cypher
MATCH (n)
WHERE n:QA008Customer OR n:QA008Order
DETACH DELETE n;
~~~

~~~cypher
DROP INDEX qa008_customer_display_name IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa008_customer_id_unique IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa008_order_id_unique IF EXISTS;
~~~

Verify:

~~~cypher
MATCH (n)
WHERE n:QA008Customer OR n:QA008Order
RETURN count(n) AS remaining;
~~~

**Expected:** `remaining=0`. If you tested new relationship types, `DETACH DELETE` removes those edges too. Never run cleanup in a database sharing test labels with other data.

### 26.2. Official Version-Specific References

- [Neo4j Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/): server/store upgrade paths, backup prep, and compatibility limits.
- [Neo4j Operations Manual — Upgrade and migration](https://neo4j.com/docs/operations-manual/current/upgrade/): version/edition/topology procedures and safe operations.
- [Neo4j Operations Manual — Schema indexes](https://neo4j.com/docs/cypher-manual/current/indexes/): creating, monitoring, and evaluating indexes for queries.
- [Neo4j Cypher Manual — Constraints](https://neo4j.com/docs/cypher-manual/current/constraints/): uniqueness, property constraints, and edition limits.
- [Neo4j Cypher Manual — CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/): batching, implicit transactions, and version-specific syntax.
- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/): managed transactions, retries, and idempotency.
- [Neo4j Java Driver Manual — Performance](https://neo4j.com/docs/java-manual/current/performance/): Driver reuse, batching, and database selection.
- [Spring Data Neo4j Reference — Object mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/): `@Node`, `@Property`, `@Relationship`, and converters.
- [Spring Data Neo4j Reference — Custom queries](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html): custom Cypher, graph projections, and partial-hydration risks.
- [Neo4j Operations Manual — Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/): backups and recovery drills per version/edition.

**Key takeaway:** A compatible rollout is not just adding a property or running one script. It is **a contract across multiple application versions, data states, and Neo4j**, safeguarded by **expand → migrate → contract**, writer inventories, atomic dual-writes, idempotent backfills, missing/divergence checks, canaries, metrics, and rollback readiness. **Delete legacy formats only when zero readers/writers remain and recovery plans are updated.**
