# Index, Performance, and Server Version Compatibility Regression Testing

A **Spring Data MongoDB** query can continue returning accurate data while growing dramatically slower after an index change, a MongoDB Server upgrade, or a Java driver swap. For instance, an endpoint fetching a customer's 20 newest events still returns the right 20 documents in tests, yet after an upgrade scans hundreds of thousands of documents or sorts in memory. This is a **performance regression** that unit tests and pure output assertions commonly miss.

The **Testing** chapter of **SPRING_DATA_MONGODB** distinguishes three kinds of evidence:

1. **Correctness regression:** queries, mappings, sorts, aggregations, and updates still yield expected business outputs.
2. **Index and execution plan regression:** required indexes still exist with the right definitions, and MongoDB uses them effectively for critical query shapes.
3. **Performance and version compatibility regression:** the same workload performs acceptably on the target **MongoDB Server** version, topology, **featureCompatibilityVersion (FCV)**, and Java driver.

This lesson uses **MongoTemplate**, repositories, Testcontainers, and **explain** to build a test strategy applicable whenever changing queries, indexes, or server versions. The goal is verifiable evidence; no single test can prove all production performance characteristics.

## 1. Choosing Tests by Risk

| Change or risk | Tests to run | Evidence required |
| --- | --- | --- |
| Changing filter criteria in a repository | Repository tests on real MongoDB | Right documents returned across edge cases |
| Adding/modifying compound, unique, TTL, or partial indexes | Index metadata and query behavior tests | Keys, field order, directions, options, and constraints match |
| Changing sort, pagination, or collation | Output verification + execution plan inspection | Stable ordering, no skips/duplicates, no unexpected expensive sorts |
| Changing document volume or data distribution | Benchmark with representative fixtures | p50/p95, throughput, keys/docs examined, resource usage |
| Upgrading MongoDB Server or FCV | Compatibility matrix + repository/integration tests | CRUD, queries, indexes, transactions, aggregations, and legacy data remain valid |
| Changing Spring Data MongoDB or Java driver | Build, mapping/query tests, and real connectivity checks | No broken APIs, codecs/BSON, auth/TLS, or serialization |
| Moving from standalone to replica set/sharded cluster | Integration tests on matching topology | Transactions, read/write concerns, routing, and feature limits verified |
| Using new server features | Contract tests on target version | Commands/operators work under target FCV, driver, and edition |

Scope guideline: **unit tests** suffice for pure Java logic; **`@DataMongoTest`** with real MongoDB verifies mapping, queries, and indexes; **`@SpringBootTest`** verifies driver config, services, transactions, security, or HTTP endpoints. Benchmarks run in dedicated environments with representative data and load.

~~~mermaid
flowchart TD
    A["Change in query, index, driver, or server"] --> B["Verify functional correctness"]
    B --> C["Verify index definitions"]
    C --> D["Inspect explain of real query"]
    D --> E{"Performance risk?"}
    E -- "Yes" --> F["Benchmark with representative data and load"]
    E -- "No" --> G["Version / FCV / topology matrix"]
    F --> G
    G --> H["Record evidence and deployment decision"]
~~~

## 2. Example: Querying Tenant Events

A multi-tenant system stores order events in collection **order_events**. An API fetches up to the 20 latest events for a tenant, sorted by **createdAt** descending. To break ties deterministically when two events share a timestamp, **_id** descending is added as a secondary key.

| Field | Purpose |
| --- | --- |
| tenantId | Mandatory logical partition in query predicates |
| createdAt | Event timestamp used to pick newest events |
| _id | Unique key breaking ties on identical createdAt |
| type | Event type illustrating returned payload |

Critical query shape:

~~~javascript
db.order_events.find(
  { tenantId: "tenant-a" }
).sort({ createdAt: -1, _id: -1 }).limit(20);
~~~

Candidate index to evaluate:

~~~javascript
db.order_events.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 },
  { name: "tenant_time_id_v1" }
);
~~~

Placing the equality predicate (**tenantId**) ahead of the sort fields is a sound candidate for this query shape. Real conclusions still require measurement when adding filters, collation, projections, sort directions, or varied data distributions.

Java model used in this lesson:

~~~java
package example.events;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "order_events")
public class OrderEvent {
    @Id
    private String id;
    private String tenantId;
    private Instant createdAt;
    private String type;

    protected OrderEvent() {
        // For MongoDB mapping.
    }

    public OrderEvent(
            String id, String tenantId, Instant createdAt, String type) {
        this.id = id;
        this.tenantId = tenantId;
        this.createdAt = createdAt;
        this.type = type;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public Instant getCreatedAt() { return createdAt; }
    public String getType() { return type; }
}
~~~

Query using **MongoTemplate**:

~~~java
package example.events;

import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderEventQuery {
    private final MongoTemplate template;

    public OrderEventQuery(MongoTemplate template) {
        this.template = template;
    }

    public List<OrderEvent> latest(String tenantId, int limit) {
        if (tenantId == null || tenantId.isBlank()
                || limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Invalid request");
        }

        Query query = Query.query(
            Criteria.where("tenantId").is(tenantId)
        ).with(Sort.by(
            Sort.Direction.DESC, "createdAt", "_id"
        )).limit(limit);

        return template.find(query, OrderEvent.class);
    }
}
~~~

Sorting by **_id** provides a consistent tie-breaker in this string-ID example; it does not imply **ObjectId** embedded timestamps can always replace **createdAt**. For real pagination, ensure filters, sorts, and cursors use identical key ordering.

## 3. Correctness Regression: Verify Data Before Measuring Speed

Before tuning indexes, verify the query returns the right documents. A small fixture should include:

- Two tenants with interleaved timestamps to catch missing **tenantId** filters.
- Two events sharing **createdAt** to test the **_id** tie-breaker.
- Empty result cases and counts below **limit**.
- Historical documents with null or missing sort fields if production allows them; verify expected BSON sort order before asserting.

Functional verification does not require millions of documents; the goal here is proving business semantics. Example:

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

// Runs inside @DataMongoTest connected to a real test MongoDB.
@DataMongoTest
class OrderEventQueryExample {
    @Autowired MongoTemplate template;

    @Test
    void returnsOnlyTenantEventsInStableOrder() {
        template.dropCollection(OrderEvent.class);
        Instant earlier = Instant.parse("2026-11-01T09:00:00Z");
        Instant later = Instant.parse("2026-11-01T10:00:00Z");

        template.insert(new OrderEvent("a1", "tenant-a", earlier, "CREATED"));
        template.insert(new OrderEvent("a2", "tenant-a", later, "PAID"));
        template.insert(new OrderEvent("a3", "tenant-a", later, "SHIPPED"));
        template.insert(new OrderEvent("b1", "tenant-b", later, "CREATED"));

        List<String> ids = new OrderEventQuery(template)
            .latest("tenant-a", 2).stream()
            .map(OrderEvent::getId).toList();

        assertEquals(List.of("a3", "a2"), ids);
    }
}
~~~

**Prerequisite:** this abridged example assumes the test connects to a MongoDB instance provided by Testcontainers or test infrastructure. **`@DataMongoTest`** does not supply a MongoDB Server by itself. The next section shows a concrete Testcontainers example.

Do not put **dropCollection** into tests sharing a database or running in parallel without isolation. In larger suites, give each test its own database/collection or manage fixtures carefully.

## 4. Index Regression: Verifying Actual Server Definitions

**@Indexed** or **@CompoundIndex** in Java expresses mapping intent, yet automatic index creation may be disabled across Spring Data MongoDB configurations. Tests must verify the index **actually exists in MongoDB** with exact keys and options, preferably by running the application's own migration/index initializer.

Extract index creation into a helper shared by deployment and tests:

~~~java
package example.events;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;

public final class OrderEventIndexes {
    private OrderEventIndexes() {}

    public static void ensure(MongoTemplate template) {
        Index index = new Index()
            .on("tenantId", Sort.Direction.ASC)
            .on("createdAt", Sort.Direction.DESC)
            .on("_id", Sort.Direction.DESC)
            .named("tenant_time_id_v1");
        template.indexOps(OrderEvent.class).ensureIndex(index);
    }
}
~~~

The test below illustrates **Spring Boot 3.x / Spring Data MongoDB 4.x** and **Testcontainers 1.x**. Newer major releases of Spring Boot and Testcontainers may change packages or connection mechanisms; use dependencies and BOMs matching your project.

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.*;
import java.util.ArrayList;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@DataMongoTest
@Testcontainers
class OrderEventIndexRegressionTest {

    @Container
    static final MongoDBContainer mongo = new MongoDBContainer(
        DockerImageName.parse("mongo:7.0")
    );

    @DynamicPropertySource
    static void mongoUri(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", mongo::getReplicaSetUrl);
    }

    @Autowired MongoTemplate template;

    @BeforeEach
    void createCleanCollectionAndIndex() {
        template.dropCollection(OrderEvent.class);
        OrderEventIndexes.ensure(template);
    }

    @Test
    void indexKeysAndDirectionsMustMatchContract() {
        List<Document> indexDocs = template
            .getCollection("order_events")
            .listIndexes(Document.class)
            .into(new ArrayList<>());

        Document index = indexDocs.stream()
            .filter(d -> "tenant_time_id_v1".equals(d.getString("name")))
            .findFirst().orElseThrow();

        Document expectedKeys = new Document("tenantId", 1)
            .append("createdAt", -1)
            .append("_id", -1);
        assertEquals(expectedKeys, index.get("key", Document.class));
    }
}
~~~

This test verifies **the index exists with the exact field order and directions** after running the initializer. When business rules depend on unique, partial, TTL, collation, wildcard, or hidden indexes, assert the index **options** too; comparing keys alone is insufficient.

Inspecting full index definitions in **mongosh**:

~~~javascript
db.order_events.getIndexes();

// Inspect one index by name.
db.order_events.getIndexes()
  .find(index => index.name === "tenant_time_id_v1");
~~~

**Common mistakes:**

| Definition error | Potential consequence |
| --- | --- |
| Swapping **tenantId** and **createdAt** | Index no longer efficiently serves the filter and sort together |
| Omitting **_id** from sort or index | Ties at identical timestamps lose deterministic order or force in-memory sort |
| Flipping direction in a compound index | May fail to serve the mixed-direction sort |
| Missing collation in index or query | Planner cannot use index for locale-aware string matching/sorting |
| Changing partial filter expression | Documents fall outside the index; queries must match compatible predicates |
| Altering unique/TTL without checking options | Loses data constraints or changes expiration timing |
| Editing annotations without running index migration | Database schema remains on the old index definition |

**Caution:** never drop and recreate production indexes automatically just to satisfy a test. When an index changes, prepare an explicit migration and rollout plan for existing indexes. Tests should exercise the exact index creation/upgrade mechanism used in deployment.

## 5. Execution Plan Regression: Reading Evidence from `explain`

Once a query returns accurate results, use **explain** to see how MongoDB traverses data. For our sample query:

~~~javascript
db.order_events.find({
  tenantId: "tenant-a"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20).explain("executionStats");
~~~

Inspect at least:

| Field / indicator | Interpretation |
| --- | --- |
| **queryPlanner.winningPlan** | Chosen execution tree, though exact JSON shape varies across engine/versions |
| **IXSCAN** or index branch | Whether the query scans an index; inspect exact index name and index bounds |
| **COLLSCAN** | Collection scan; reasonable on tiny collections, costly on large datasets |
| **SORT** | Potential blocking sort stage; review index alignment, filter, collation, and memory |
| **executionStats.nReturned** | Number of documents returned |
| **executionStats.totalKeysExamined** | Index keys scanned; unusually high counts suggest poor selectivity |
| **executionStats.totalDocsExamined** | Documents fetched; compare against `nReturned` to gauge scan cost |
| **executionStats.executionTimeMillis** | Elapsed time during explain; observational for that single run only |

**Read in context:** **IXSCAN** alone does not prove a query is fast. A query can scan an index yet examine hundreds of thousands of keys or fetch excessive documents for residual filtering. **COLLSCAN** is not always a bug: on tiny collections, the planner legitimately prefers a full scan. Stage fields differ between the **classic engine** and **slot-based execution (SBE)**; brittle tests matching the entire **winningPlan** JSON break easily across server upgrades.

### 5.1. Two `explain` Calls for Two Different Questions

Run the query **without a hint** to observe what the optimizer selects:

~~~javascript
db.order_events.find({ tenantId: "tenant-a" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
~~~

Also run **with a hint** to evaluate efficiency when forcing the intended index:

~~~javascript
db.order_events.find({ tenantId: "tenant-a" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .hint("tenant_time_id_v1")
  .explain("executionStats");
~~~

If the **hinted** run performs well yet the unhinted run picks another plan, the issue lies in planner selection, statistics, or query shape. Never run only a hinted explain and conclude production will use that index unless the application query actually specifies that hint. And if the app renames fields with **@Field**, verify the actual **BSON** field names sent to the server; the `mongosh` commands above use MongoDB field names.

### 5.2. Automating Plan Checks at the Right Level

In repository/integration suites, you can run `explain` via **MongoTemplate.executeCommand**:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

public class ExplainInspector {
    public static Document explainLatest(MongoTemplate template) {
        Document find = new Document("find", "order_events")
            .append("filter", new Document("tenantId", "tenant-a"))
            .append("sort", new Document("createdAt", -1)
                .append("_id", -1))
            .append("limit", 20);

        return template.executeCommand(
            new Document("explain", find)
                .append("verbosity", "executionStats")
        );
    }
}
~~~

**Note:** this illustrates the method inside a complete Java class; in real repositories, avoid duplicating a query shape that drifts from the live application path. If the service's `Query` uses collation, projections, or extra filters, the explained command must mirror them accurately. Use a command listener in tests to compare what the driver actually sends.

For durable **plan regression tests**, focus on meaningful invariants:

1. Index metadata remains accurate; queries return right results, sorting, and limits.
2. On a representative fixture, **totalDocsExamined** and **totalKeysExamined** stay within budgets agreed with operations.
3. If a specific index or absence of blocking sorts is mandatory, assert deliberately on a pinned server version with stage-inspection logic resilient to plan structure changes.
4. Never assert verbatim plan JSON strings, plan cache keys, or exact millisecond timings across server versions.

For example, with 100,000 events spread across tenants and a query fetching the newest 20, if a change jumps **totalDocsExamined** from a couple dozen to nearly the whole collection, investigate immediately. Specific thresholds depend on cardinality, selectivity, projections, and data shape; **never hardcode one magic number across every system**.

## 6. Performance Benchmarks: Separating Noise from Regressions

Single-run timing can spike due to noisy CI hosts, cold containers, un-warmed JIT, cold caches, or network jitter. Separate **per-PR functional tests** from **performance benchmarks run in controlled environments**.

| Factor | How to control |
| --- | --- |
| Data size and distribution | Record document count, tenant count, time distribution, null/missing ratio, and skew |
| Indexes and schema | Apply identical migrations and index options before every run |
| Versions | Record MongoDB Server, FCV, driver, Spring Data MongoDB, JDK, and CPU architecture |
| Topology | Compare on identical replica set/sharding layout, read preference, and write concern |
| Cache and warm-up | Warm up explicitly; distinguish cold-cache from warm-cache runs |
| Concurrency | Simulate representative client counts, QPS, and read/write mix |
| Execution environment | Minimize unrelated background noise; record CPU, RAM, I/O, and network |
| Results | Capture p50, p95/p99 (with sufficient samples), throughput, error rate, keys/docs examined |

**Avoid brittle CI assertions like:** “Query must finish under 10 ms on every laptop and CI runner.” Those fluctuate wildly and generate false failures. Enforce budgets on **keys/docs examined** against fixed CI fixtures, while using dedicated benchmark environments to validate latency and throughput against SLOs.

A baseline benchmark process:

1. Capture baseline metrics on the current version with identical data and indexes.
2. Run controlled warm-up, noting whether measurements are cold or warm cache.
3. Run repeated iterations under a consistent workload, recording latency distributions and server metrics.
4. Repeat on the target version after verifying identical schemas/indexes.
5. Flag regressions exceeding agreed thresholds; capture query shape, explain plans, logs/metrics, and versions for reproduction.

Sample report template (structure only—**not real measurements**):

| Workload | Baseline p95 | Target p95 | Docs examined/query | Conclusion |
| --- | --- | --- | --- | --- |
| Latest 20 events, hot tenant | Measure live | Measure live | Compare vs. baseline | Pass or investigate |
| Latest 20 events, small tenant | Measure live | Measure live | Compare vs. baseline | Pass or investigate |
| Aggregation by status | Measure live | Measure live | Compare vs. baseline | Pass or investigate |

Never treat **explain `executionTimeMillis`** as a full load benchmark. Explain differs from normal query execution and omits network overhead, serialization, Spring mapping, connection pool contention, and concurrency. Measure end-to-end from **MongoTemplate/repositories** or real endpoints alongside MongoDB server metrics.

## 7. MongoDB Server Version Compatibility Matrix

A successful server upgrade means more than establishing a connection. Version changes can affect the **query planner**, indexes, aggregation operators, collation results, transactions, server commands, BSON conversion, authentication, and driver compatibility.

Record at least:

- **MongoDB Server binary version** across all participating nodes.
- **featureCompatibilityVersion (FCV)** before, during, and after the upgrade.
- **Topology**: standalone, replica set, or sharded cluster; **mongos** version if present.
- **Edition and service**: Community, Enterprise, or Atlas; feature availability varies.
- **Java driver and Spring Data MongoDB versions**, including transitive dependencies and codecs/converters.
- **JDK**, connection string, TLS, auth mechanism, read/write concerns, and read preference.

You can inspect server details in **mongosh** when authorized:

~~~javascript
db.version();
db.adminCommand({ buildInfo: 1 });
db.adminCommand({ hello: 1 });

// May require admin privileges and may be restricted on managed services.
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
~~~

If `FCV` or `buildInfo` commands are restricted in managed environments, mark them **unverified** and confirm via approved operational configuration. Never guess FCV solely from the binary version string. Especially during **rolling upgrades**, nodes can run mixed binary versions before FCV advances; follow the official multi-step upgrade sequence carefully.

### 7.1. Minimum Compatibility Matrix

| Test environment | Objective |
| --- | --- |
| **Baseline**: current server version, current FCV | Establish reference results, index definitions, and metrics |
| **Target binary** at transitional FCV | Verify intermediate compatibility before enabling new version features |
| **Target binary + target FCV** | Verify features and workloads after upgrade completes |
| **Upgraded legacy dataset** | Ensure existing collections, indexes, BSON, and old schemas still read/write cleanly |
| **Production-like topology cluster** | Test transactions, sharding, read/write concerns, retries, and failover if in scope |

A fresh container running the target version only tests a **fresh install**. It **does not test upgrading existing data and indexes** or FCV transitions. For significant migrations, restore a sanitized snapshot into staging or rehearse the upgrade following MongoDB's supported procedure.

### 7.2. What to Re-Verify Across Version Changes

| Component | Regression questions |
| --- | --- |
| Derived repository methods | Do field names, queries, sorts, paging, and null/missing still behave right? |
| **MongoTemplate** | Do queries, updates, findAndModify, and bulk writes preserve outputs? |
| Aggregation pipelines | Are all stages/operators supported under the version and FCV, with expected output types? |
| Indexes | Are definitions, collations, partial filters, and TTL/unique constraints intact? |
| Query planner | Did index selection, blocking sorts, or keys/docs scanned regress? |
| Transactions | Do commit/rollback, sessions, and retry semantics work in topology? |
| Reactive access | Are publishers, backpressure, timeouts/retries, and connection pools stable? |
| Security / connections | Do TLS, auth, encryption, and driver compatibility meet policy? |

Never assume planner choices or **explain** formats remain identical across upgrades. Claim compatibility only after testing **the exact commands, indexes, and query shapes your application runs**.

## 8. Running Tests Across Multiple Versions with Testcontainers

With Spring Boot 3.x, Testcontainers 1.x, and a compatible MongoDB driver, pass the image tag via a CI environment variable to run the same suite across target versions.

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@DataMongoTest
@Testcontainers
class MongoVersionMatrixSmokeTest {
    private static final String IMAGE = System.getenv()
        .getOrDefault("MONGO_TEST_IMAGE", "mongo:7.0");

    @Container
    static final MongoDBContainer MONGO = new MongoDBContainer(
        DockerImageName.parse(IMAGE)
    );

    @DynamicPropertySource
    static void mongoProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", MONGO::getReplicaSetUrl);
    }

    @Autowired MongoTemplate template;

    @Test
    void indexAndQueryMustWorkOnSelectedServer() {
        template.dropCollection(OrderEvent.class);
        OrderEventIndexes.ensure(template);
        template.insert(new OrderEvent(
            "evt-1", "tenant-a",
            Instant.parse("2026-11-01T10:00:00Z"), "CREATED"
        ));

        assertEquals("evt-1", new OrderEventQuery(template)
            .latest("tenant-a", 20).get(0).getId());
    }
}
~~~

This is a **smoke test** running against the chosen image, proving basic index creation, writes, and reads; it does not replace the full repository/integration regression suite. Adjust packages and APIs for other Testcontainers/JUnit and Spring Boot versions. Do not launch a fresh container per test method without good reason; multiple tests can share a container with isolated databases/collections.

In CI pipelines, run the suite across pinned **MONGO_TEST_IMAGE** values:

~~~text
MONGO_TEST_IMAGE=mongo:7.0   # illustrative baseline
MONGO_TEST_IMAGE=mongo:8.0   # illustrative target
~~~

These tags **only illustrate a matrix**; choose supported upgrade pairs published by MongoDB. Pin exact patch tags or digests when strict reproducibility is needed. Testcontainers requires Docker or a compatible container runtime and sufficient CI resources.

**Container environment limits:** `MongoDBContainer` provides a single-node replica set for tests, yet **cannot replace** a sharded cluster, custom Atlas settings, rolling upgrades, or real replication lag. Features tied to specific editions or topologies need dedicated tests in matching environments.

## 9. Acceptance Thresholds: Define Upfront, Separate Bugs from Noise

A balanced review framework uses three groups of criteria:

| Group | Pass condition | Investigation trigger |
| --- | --- | --- |
| **Data correctness** | Identical fixtures produce exact query/sort/update/aggregation results | Wrong documents, unstable ordering, data loss, exceptions |
| **Indexes and plans** | Index definitions accurate; queries avoid excessive scanning on reference workload | Missing index or changed options, docs/keys examined spike, unexpected blocking sort |
| **Performance** | p95/p99, throughput, and error rates within agreed budget | Statistically significant latency regression across runs, resource exhaustion |

Never block every pull request with a rigid single-run **millisecond** threshold. When thresholds are necessary:

1. Measure baselines under representative data and load.
2. Record test conditions and variance across multiple runs.
3. Separate soft warnings (review needed) from hard failures (missing index, broken constraint, unsupported query).
4. Archive benchmark and explain artifacts so regressions can be traced.

When evaluating **`totalDocsExamined / nReturned`**, account for zero-result queries, projections, covered queries, `skip`, `$lookup`, and planner details; one simple ratio does not fit every workload. Pick metrics directly tied to the cost of each critical query.

## 10. Pitfalls Easily Missed During Upgrades

### 10.1. Tests Create Indexes Differently Than Production

If tests call `ensureIndex` while production relies on separate migrations or different `auto-index-creation` settings, tests can pass while production lacks the index. Reuse the exact production migration/index initializer in tests and verify deployment scripts actually execute.

### 10.2. Tiny Test Datasets Cause the Planner to Pick `COLLSCAN`

Fixtures with only a few rows often lead the planner to pick `COLLSCAN` while still completing instantly. Never treat every `COLLSCAN` as a regression without checking cardinality and data size. Use hinted explains to confirm index compatibility, and representative data with unhinted explains to inspect natural planner selection.

### 10.3. Diffing Raw `explain` JSON Across Server Versions

Query engines rename stages, nest branches, or shift to SBE layouts; giant JSON diffs produce false alarms. Compare **business results**, **index options**, **cost metrics**, and the essential plan properties instead.

### 10.4. Testing Only Fresh Containers

A brand-new collection lacks legacy BSON types, older index versions, collection options, and migration history. Test against sanitized production-like snapshots and rehearse staging upgrades following supported procedures.

### 10.5. Checking Only Driver Connectivity

Connecting with `MongoClient` does not guarantee all aggregation operators, retryable writes, transactions, or application mappings remain compatible. Exercise real business flows including error paths and boundary data.

### 10.6. Changing Indexes Without Measuring Write Impact

Adding indexes speeds up reads while increasing write amplification, storage footprint, and index build time. Benchmarks must include write and mixed read/write workloads; for new indexes on large collections, test build duration and resource load in staging.

### 10.7. Overlooking Collation, Partial Indexes, and Hints

An index with the right name still will not serve a query if collation differs, partial filter predicates are unsatisfied, or hints name the wrong index. Test with real query shapes, inspect `getIndexes`, and verify any application hints.

## 11. Complete Regression Workflow Example

Suppose the team updates **tenant_time_id_v1** to support filtering by event type while upgrading MongoDB Server. Recommended sequence:

1. **Record baseline:** using fixed fixtures, capture live `MongoTemplate` queries, sort/limit results, index definitions, explains, and controlled p95 metrics.
2. **Functional tests:** run repository tests covering tenant isolation, sort tie-breakers, limits, empty results, and the new filter.
3. **Verify indexes:** run the new migration against both an empty database and a database containing legacy data; check keys/options via `getIndexes`.
4. **Analyze query plans:** run hinted and unhinted explains on baseline and target, comparing `nReturned`, keys/docs examined, blocking sorts, and index usage.
5. **Benchmark:** measure multi-tenant, hot-tenant, and small-tenant workloads, including write load to measure index maintenance cost.
6. **Compatibility matrix:** run the same suite against current and target server versions; verify FCV, driver, topology, and active features.
7. **Upgrade rehearsal:** rehearse on staging with legacy data following the exact upgrade order; verify both transitional and post-FCV stages.
8. **Archive evidence:** document accepted shifts, regressions fixed, rollback steps, and go-live criteria.

Sample evidence record:

~~~text
Query: latest-events-by-tenant
Application: Spring Boot/Spring Data MongoDB <version>
Driver/JDK: <version>/<version>
Server/FCV: <version>/<fcv>
Topology/edition: <replica set/sharded>/<edition>
Dataset: <documents, tenants, size, distribution>
Index contract: <name, key, options>
Functional result: <PASS/FAIL>
Explain: <winning plan summary, keys/docs examined, nReturned>
Latency/throughput: <p50/p95/p99, ops/sec, error rate>
Comparison baseline: <version + artifact>
Decision: <PASS / INVESTIGATE / BLOCK>
~~~

**Critical rule:** metrics in this report must be **actually observed measurements**—never invent placeholder numbers in a deployment sign-off. If FCV cannot be queried, topology is unavailable, or legacy data was not tested, explicitly record those evidence gaps.

## 12. Practice Exercise

**Scenario:** For collection **order_events**, operations proposes revising the event-list index and upgrading MongoDB Server. Design a regression suite runnable in CI and staging.

**Tasks:**

1. Seed at least 4 documents across two tenants, including two documents sharing `createdAt`; assert `OrderEventQuery.latest` returns the right tenant, order, and limit.
2. Use `MongoTemplate.indexOps` to create `tenant_time_id_v1`, then inspect MongoDB metadata to assert key directions.
3. Generate a larger fixture (e.g., 10,000–100,000 documents depending on resources) distributed across tenants; run `explain("executionStats")` with and without hints. Record `nReturned`, `totalKeysExamined`, `totalDocsExamined`, and a plan summary.
4. Run the suite against pinned baseline and target server images. Verify actual version and FCV; note aspects containers cannot simulate.
5. Define pass/fail criteria distinguishing wrong results, missing indexes, increased scanned documents, and latency noise. Add a mixed workload measurement including inserts to observe index cost.
6. Propose how to test legacy data and production topology where fresh Testcontainers alone fall short.

**Acceptance criteria:** tests catch wrong queries and altered indexes; benchmarks use clear measurement and comparison methodology; and the version matrix logs server, FCV, driver, topology, and test-environment limits.

## 13. Operational Checklist

- [ ] Query shapes, business goals, and boundary data are identified.
- [ ] Repository/integration tests use real MongoDB for queries, sorts, mapping, and indexes.
- [ ] Index definitions (keys, directions, unique/TTL/partial/collation options) are verified directly from the database.
- [ ] Explains run **without hints** to observe the planner and **with hints** when verifying a specific index.
- [ ] Regression metrics and budgets match realistic fixtures and workloads.
- [ ] Benchmarks are separated from brittle millisecond assertions in CI.
- [ ] Server version, FCV, edition, topology, Spring Data, driver, and JDK are documented.
- [ ] At least baseline and target versions are tested; staging validates legacy data for real upgrades.
- [ ] Transactions, aggregations, and reactive paths are verified if relied upon by the app.
- [ ] Reports record outputs, explains, index metadata, performance deltas, and rollout decisions.

**Key takeaway:** index, performance, and server compatibility regressions are three related yet distinct dimensions. **Accurate results** do not prove a query is fast; **having an index** does not guarantee the planner chooses it sensibly; **running on a newer server** does not guarantee safe upgrades or production performance. Only approve rollout when evidence supports all three.
