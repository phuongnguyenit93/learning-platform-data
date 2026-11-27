# Reproducing Bugs and Running Regression Tests After Model or Version Changes

## 1. Why is regression testing especially critical in Neo4j?

In systems powered by **Neo4j**, data-model changes go far beyond renaming a column. A change can promote a property into a relationship, flip edge direction, alter a relationship type, introduce a constraint, change traversal paths, or adjust indexes. A **Cypher** query can still execute without errors while returning the wrong nodes, duplicating rows, dropping paths, or consuming far more resources.

Similarly, when upgrading **Neo4j Server**, the **Java Driver**, **Spring Data Neo4j**, **APOC**, or **Graph Data Science (GDS)**, syntax, planner behavior, APIs, and compatibility can shift. A test checking only that "the database starts up" does not prove the application still works properly.

This lesson belongs to the **Testing** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. Its goal is designing a workflow to:

1. **Reproduce bugs** under controlled input data, versions, and execution conditions.
2. **Lock down required business behavior** before changing the graph model or upgrading versions.
3. **Run automated regression tests** against a real Neo4j database, not just mocked Java repositories.
4. **Verify both correctness and performance**, including contention, dirty data, and cluster connectivity.
5. **Enforce deployment gates** with a recovery plan whenever a change fails checks.

**Guiding principle:** a valuable test does not merely mirror the current implementation; it catches **violations of business contracts** even after source code or graph schemas evolve.

## 2. Classifying bugs to reproduce

| Bug category | Example in Neo4j | Minimum evidence |
|---|---|---|
| **Query semantics bug** | After reversing **[:PLACED]**, a Customer's order list misses items | Fixture, query, parameters, expected result set |
| **Duplicate / missing data** | Migration creates two Order nodes sharing the same business key | Constraints, counts, invariants, before–after data |
| **Wrong relationship direction / type** | Traversing **DEPENDS_ON** backward by mistake | Directed edge diagram and verification query |
| **Compatibility change** | Cypher/Java Driver/APOC no longer accepts old syntax or API | Exact versions, exception, failure location |
| **Performance regression** | Query degrades from index seek to wide scan; p95 spikes | Identical workload, `PROFILE`, DB Hits, timings |
| **Transaction and concurrency bug** | Two concurrent requests create duplicate keys, deadlock, or lost update | Concurrent schedule, locks, final state |
| **Routing / cluster bug** | Immediate read after write via replica misses the update | Routing URI, bookmark, topology, timing |
| **Import/export & plugin bug** | `LOAD CSV` handles nulls unexpectedly; missing GDS/APOC procedure | Source file, plugin config, versions, and logs |

Never rely solely on **`assertEquals(expectedCount, actualCount)`** for every problem. Two result sets with the same row count can contain **different nodes**, wrong edge directions, or wrong tenants.

### 2.1. One symptom can have multiple root causes

The symptom "API cannot find Order O-1" could stem from:

- Migration omitted the relationship linking Customer to Order.
- The new query uses **<-** instead of **->**.
- The request carried the wrong **tenantId**.
- Data was not committed yet or a replica has not caught up to the bookmark.
- The index is not **ONLINE**, causing the request to time out even though the data exists.

Before "fixing the bug", write a minimal test that distinguishes these causes; otherwise, the team may tweak the wrong Cypher query or raise timeouts without fixing the root issue.

## 3. What makes a bug report reproducible

Information template for a Neo4j bug:

| Field | Details to capture |
|---|---|
| **Description** | User action, expected behavior, and actual behavior |
| **Versions** | Neo4j Server, Java Driver, SDN, APOC/GDS if used, Java runtime |
| **Cypher language** | **Cypher 5** or **Cypher 25** if the server supports selection |
| **Topology** | Standalone, cluster, Aura; URI **neo4j://** vs. **bolt://** |
| **Schema** | Constraints, indexes, and **ONLINE** status |
| **Minimal dataset** | Exact nodes, relationships, and properties triggering the bug, scrubbed of sensitive data |
| **Reproduction steps** | Seed statements, Cypher query, parameters, transaction order |
| **Diagnostics** | Exception/code, message, query plan, timings, sanitized logs |
| **Expected invariant** | E.g., "each Order has exactly one Customer in the same tenant" |

For load-dependent bugs, also capture **worker count**, concurrency schedule, latency, timeouts, and reproduction rate. For post-upgrade bugs, record both the **previous version** and the **target version**.

### 3.1. Checking version, schema, and state

In an authorized environment:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties
RETURN name, type, labelsOrTypes, properties
ORDER BY name;
~~~

~~~cypher
SHOW INDEXES
YIELD name, type, state, populationPercent
RETURN name, type, state, populationPercent
ORDER BY name;
~~~

These three outputs answer: which server version is running, whether constraints exist, and whether indexes are ready. A **POPULATING** or **FAILED** index cannot be evaluated as if it were **ONLINE**.

**Never paste raw full logs** containing passwords, tokens, signed URLs, personal data, or customer payloads into public issues. Prefer a minimal synthetic graph that reproduces the bug.

### 3.2. Distinguishing deterministic vs. intermittent bugs

Tag every bug with at least one of these labels:

- **Deterministic:** given identical data and execution steps, the bug reproduces reliably.
- **Concurrency-sensitive:** requires two or more overlapping transactions to manifest.
- **Environment-sensitive:** occurs only under specific topology, OS, plugin setup, version, or data volume.

Never paper over a test by dropping in arbitrary **`Thread.sleep(2000)`** calls. Fixed sleeps cannot control OS scheduling or replica lag; when concurrency ordering matters, use **barriers**, **latches**, event logs, or a deterministic test harness.

## 4. End-to-end example: migrating from a foreign key property to a relationship

Suppose the legacy model stores a Customer ID directly on Order:

~~~text
(:DemoRegressionOrder {
  tenantId: 'shop-a',
  orderId: 'O-1',
  legacyCustomerId: 'C-1'
})
~~~

The new model represents this as a graph relationship:

~~~text
(:DemoRegressionCustomer)
  -[:DEMO_REG_PLACED]->
(:DemoRegressionOrder)
~~~

**Business contract to preserve:** when asked "Which orders did Customer C-1 in tenant shop-a place?", both old and new queries must return **O-1, O-2**, never leaking orders from another tenant. Additionally, running the migration twice must never create duplicate relationships.

### 4.1. Small dataset capable of catching bugs

Run **once in a dedicated test database**, never directly on real data:

~~~cypher
CREATE CONSTRAINT demo_reg_customer_key IF NOT EXISTS
FOR (c:DemoRegressionCustomer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_reg_order_key IF NOT EXISTS
FOR (o:DemoRegressionOrder)
REQUIRE (o.tenantId, o.orderId) IS UNIQUE;
~~~

~~~cypher
CREATE
  (c1:DemoRegression:DemoRegressionCustomer {
    tenantId: 'shop-a', customerId: 'C-1'
  }),
  (c2:DemoRegression:DemoRegressionCustomer {
    tenantId: 'shop-a', customerId: 'C-2'
  }),
  (c3:DemoRegression:DemoRegressionCustomer {
    tenantId: 'shop-b', customerId: 'C-1'
  }),
  (:DemoRegression:DemoRegressionOrder {
    tenantId: 'shop-a', orderId: 'O-1', legacyCustomerId: 'C-1'
  }),
  (:DemoRegression:DemoRegressionOrder {
    tenantId: 'shop-a', orderId: 'O-2', legacyCustomerId: 'C-1'
  }),
  (:DemoRegression:DemoRegressionOrder {
    tenantId: 'shop-a', orderId: 'O-3', legacyCustomerId: 'C-2'
  }),
  (:DemoRegression:DemoRegressionOrder {
    tenantId: 'shop-b', orderId: 'O-4', legacyCustomerId: 'C-1'
  });
~~~

Why does the fixture include **shop-b / C-1**? Without duplicate Customer IDs across tenants, a new query missing the **tenantId** filter could accidentally pass every test.

### 4.2. Legacy query and golden result

~~~cypher
MATCH (o:DemoRegressionOrder {
  tenantId: $tenantId,
  legacyCustomerId: $customerId
})
RETURN o.orderId AS orderId
ORDER BY orderId;
~~~

With **tenantId = 'shop-a'** and **customerId = 'C-1'**, the golden result is:

~~~text
O-1
O-2
~~~

This is the **golden result** expressing the business contract—not merely a blind snapshot from the legacy version assumed always right. If the legacy query had known bugs, record the business-approved expected output before writing regression tests.

### 4.3. Migration: creating relationships from the legacy property

~~~cypher
MATCH (c:DemoRegressionCustomer)
MATCH (o:DemoRegressionOrder)
WHERE c.tenantId = o.tenantId
  AND c.customerId = o.legacyCustomerId
MERGE (c)-[:DEMO_REG_PLACED]->(o);
~~~

**`MERGE`** runs on both matched endpoints. If re-executed on the same graph without other code creating duplicate edges, it matches the existing relationship rather than adding a second one.

In real systems with millions of records, never scan every Customer and Order with an unbatched pattern like this. Plan **batching**, use indexes/constraints to look up endpoints by business key, reconcile row counts, and track **unmatched Orders missing a Customer** before running the migration.

### 4.4. New query and critical assertions

~~~cypher
MATCH (c:DemoRegressionCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})-[:DEMO_REG_PLACED]->(o:DemoRegressionOrder)
RETURN o.orderId AS orderId
ORDER BY orderId;
~~~

On the seeded fixture, the minimum assertions are:

| Check | Expected |
|---|---|
| **shop-a / C-1** | **[O-1, O-2]** |
| **shop-a / C-2** | **[O-3]** |
| **shop-b / C-1** | **[O-4]** |
| Total Orders in fixture | **4** |
| **DEMO_REG_PLACED** edges after migration | **4** |
| Relationship count after second migration run | **Still 4** |
| Relationships linking different tenants | **0** |

Cross-tenant audit query:

~~~cypher
MATCH (c:DemoRegressionCustomer)-[r:DEMO_REG_PLACED]->
      (o:DemoRegressionOrder)
WHERE c.tenantId <> o.tenantId
RETURN count(r) AS crossTenantRelationships;
~~~

The result must be **0**. Also verify the **Customer → Order** direction, relationship type, and proper isolation when two different Orders or Customers share IDs across tenants.

### 4.5. Injecting an intentional bug to prove the test catches it

Try replacing the new query with:

~~~cypher
// INTENTIONALLY WRONG: omits tenant filter, may mix results across tenants.
MATCH (c:DemoRegressionCustomer {customerId: $customerId})
      -[:DEMO_REG_PLACED]->(o:DemoRegressionOrder)
RETURN o.orderId AS orderId
ORDER BY orderId;
~~~

For **customerId = 'C-1'**, the buggy query also returns **O-4** from shop-b. If the suite still passes, either an assertion is missing or the fixture lacks crucial edge cases.

In multi-tenant distributed systems, **tenant-isolation tests** can matter even more than simple total-node comparisons.

## 5. Combining test levels effectively

| Level | What it verifies | Tooling | Boundary |
|---|---|---|---|
| **Unit tests** | ID normalization, DTO mappers, Cypher parameter builders, retry policies | JUnit, Mockito | Does not prove Cypher executes accurately |
| **Cypher integration tests** | Patterns, indexes, constraints, transactions, graph results | Real Neo4j + Java Driver | Higher startup/seed cost than mocks |
| **Repository/service tests** | SDN mapping, custom queries, transaction boundaries | Spring Test + Neo4j/Testcontainers | Requires compatible Spring config and versions |
| **Migration tests** | Model conversion, before/after reconciliation, safe re-runs | Snapshots/fixtures + Cypher migrations | Must preserve state from legacy layout |
| **Contract/API tests** | Same request returns consistent semantics, HTTP status, auth | API tests + Neo4j test DB | Introduces dependencies on neighboring services |
| **Concurrency tests** | Lost updates, deadlocks, idempotency, uniqueness | Multiple transactions, latches/barriers | Thread schedules remain non-deterministic |
| **Performance regression** | p95, DB Hits, Rows, memory, timeouts | `EXPLAIN`/`PROFILE` + representative load | Sensitive to caches and infrastructure |
| **Upgrade/cluster tests** | Routing, bookmarks, failover, plugin compatibility | Staging cluster environment | One standalone container cannot simulate a cluster |

Not every change needs a massive end-to-end suite on every file save. An effective workflow runs **small, fast tests** on every commit; **integration tests** on pull requests; and **migration, performance, and cluster checks** as release gates.

## 6. JUnit 5, Neo4j Java Driver, and Testcontainers

### 6.1. Why a real database is required

Mocking **Session**, **Transaction**, or repositories tests Java control flow, but fails to reproduce:

- How Neo4j matches Cypher patterns and relationship directions.
- **`MERGE`**, uniqueness constraints, null semantics, and transaction rollbacks.
- Index usage, query planner choices, or server error codes.
- Behavioral differences across Cypher and Neo4j versions.

**Testcontainers** launches Neo4j inside a Docker container with a chosen image, giving you a test database close to real deployments. It requires Docker or a supported container runtime locally and in CI.

In **Testcontainers Java 2.x**, the Neo4j module uses artifact **`org.testcontainers:testcontainers-neo4j`** and class **`org.testcontainers.neo4j.Neo4jContainer`**. In **Testcontainers 1.x**, artifact and package names differ. Align **Testcontainers, JUnit 5, and the Neo4j Java Driver** via your project's dependency management—never mix imports across two major versions.

Gradle example (pin exact versions via your version catalog/BOM after verifying compatibility):

~~~groovy
dependencies {
    implementation("org.neo4j.driver:neo4j-java-driver")
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.testcontainers:testcontainers-neo4j")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Never put both **Testcontainers 1.x** and **2.x** on the same classpath. Testing against Neo4j **Community** suffices for many standard Cypher queries; Enterprise-only features require an approved image, license, and test environment.

### 6.2. Reusable integration test example

This Java snippet illustrates **JUnit 5 + Testcontainers 2.x + modern Java Driver**, running against **`neo4j:5.26`**; you can swap the version via property **`neo4j.test.image`** to test a target release. When upgrading, pin exact patch tags or image digests instead of relying on **`latest`**.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.SessionConfig;
import org.testcontainers.neo4j.Neo4jContainer;

class ModelMigrationIT {
    private static final String PASSWORD = "test-only-password";
    private static final String IMAGE =
        System.getProperty("neo4j.test.image", "neo4j:5.26");

    private static final Neo4jContainer<?> NEO4J =
        new Neo4jContainer<>(IMAGE).withAdminPassword(PASSWORD);
    private static Driver driver;

    private static final String OLD_QUERY = """
        MATCH (o:DemoRegressionOrder {
          tenantId: $tenant, legacyCustomerId: $customer
        })
        RETURN o.orderId AS id ORDER BY id
        """;
    private static final String NEW_QUERY = """
        MATCH (c:DemoRegressionCustomer {
          tenantId: $tenant, customerId: $customer
        })-[:DEMO_REG_PLACED]->(o:DemoRegressionOrder)
        RETURN o.orderId AS id ORDER BY id
        """;
    private static final String MIGRATION = """
        MATCH (c:DemoRegressionCustomer)
        MATCH (o:DemoRegressionOrder)
        WHERE c.tenantId = o.tenantId
          AND c.customerId = o.legacyCustomerId
        MERGE (c)-[:DEMO_REG_PLACED]->(o)
        """;

    @BeforeAll
    static void startServer() {
        NEO4J.start();
        driver = GraphDatabase.driver(
            NEO4J.getBoltUrl(),
            AuthTokens.basic("neo4j", PASSWORD)
        );
        driver.verifyConnectivity();
        try (var session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            session.run("""
                CREATE CONSTRAINT demo_reg_customer_key IF NOT EXISTS
                FOR (c:DemoRegressionCustomer)
                REQUIRE (c.tenantId, c.customerId) IS UNIQUE
                """).consume();
            session.run("""
                CREATE CONSTRAINT demo_reg_order_key IF NOT EXISTS
                FOR (o:DemoRegressionOrder)
                REQUIRE (o.tenantId, o.orderId) IS UNIQUE
                """).consume();
        }
    }

    @AfterAll
    static void stopServer() {
        if (driver != null) driver.close();
        NEO4J.stop();
    }

    @BeforeEach
    void resetFixture() {
        try (var session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            session.executeWriteWithoutResult(tx -> {
                // Only delete nodes carrying the fixture marker label.
                tx.run("""
                    MATCH (n:DemoRegression)
                    DETACH DELETE n
                    """).consume();
                tx.run("""
                    CREATE
                      (:DemoRegression:DemoRegressionCustomer {
                        tenantId:'shop-a', customerId:'C-1'
                      }),
                      (:DemoRegression:DemoRegressionCustomer {
                        tenantId:'shop-a', customerId:'C-2'
                      }),
                      (:DemoRegression:DemoRegressionCustomer {
                        tenantId:'shop-b', customerId:'C-1'
                      }),
                      (:DemoRegression:DemoRegressionOrder {
                        tenantId:'shop-a', orderId:'O-1',
                        legacyCustomerId:'C-1'
                      }),
                      (:DemoRegression:DemoRegressionOrder {
                        tenantId:'shop-a', orderId:'O-2',
                        legacyCustomerId:'C-1'
                      }),
                      (:DemoRegression:DemoRegressionOrder {
                        tenantId:'shop-a', orderId:'O-3',
                        legacyCustomerId:'C-2'
                      }),
                      (:DemoRegression:DemoRegressionOrder {
                        tenantId:'shop-b', orderId:'O-4',
                        legacyCustomerId:'C-1'
                      })
                    """).consume();
            });
        }
    }

    private List<String> orders(String query, String tenant, String customer) {
        try (var session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx -> tx.run(
                query, Map.of("tenant", tenant, "customer", customer)
            ).list(row -> row.get("id").asString()));
        }
    }

    private void migrate() {
        try (var session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            session.executeWriteWithoutResult(
                tx -> tx.run(MIGRATION).consume());
        }
    }

    private long relationshipCount() {
        try (var session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx -> tx.run("""
                MATCH (:DemoRegressionCustomer)
                      -[r:DEMO_REG_PLACED]->
                      (:DemoRegressionOrder)
                RETURN count(r) AS total
                """).single().get("total").asLong());
        }
    }

    @Test
    void newModelKeepsBusinessAnswers() {
        List<String> before = orders(OLD_QUERY, "shop-a", "C-1");
        assertEquals(List.of("O-1", "O-2"), before);

        migrate();

        assertEquals(before, orders(NEW_QUERY, "shop-a", "C-1"));
        assertEquals(List.of("O-3"), orders(NEW_QUERY, "shop-a", "C-2"));
        assertEquals(List.of("O-4"), orders(NEW_QUERY, "shop-b", "C-1"));
    }

    @Test
    void migrationIsIdempotent() {
        migrate();
        migrate();
        assertEquals(4L, relationshipCount());
    }
}
~~~

**How to read this code:**

1. The container runs an explicitly specified Neo4j version, never a shared development database.
2. **`@BeforeEach`** rebuilds the fixture from a clean state so tests are order-independent.
3. Uniqueness constraints belong to the real Neo4j schema, not mocks.
4. The first test compares **legacy and new business results**, including duplicate Customer IDs across tenants.
5. The second test requires an **idempotent** migration—running twice still leaves exactly four relationships.
6. **`Session`** instances close after every task while **`Driver`** is reused across the class.

This sample assumes tests in the class execute **sequentially** and no other test mutates fixtures inside the container. If enabling JUnit parallel execution, **isolate a database or container per test** or implement strict isolation. Never wipe real data with **`MATCH (n) DETACH DELETE n`** in a shared environment.

### 6.3. Running the same tests across two versions

Gradle example (illustrative; replace tags with approved project releases):

~~~bash
./gradlew test -Dneo4j.test.image=neo4j:5.26
./gradlew test -Dneo4j.test.image=neo4j:2026.10.2
~~~

To forward system properties to the test JVM, configure the Gradle `Test` task or pass properties via your build setup. If Gradle does not propagate **`-Dneo4j.test.image`** into the test JVM automatically, set **`systemProperty`** explicitly inside the **`test`** task. In CI, run a separate matrix job per image—never run both commands against the same dirty database.

**Note:** running tests on fresh databases across two versions **does not replace** testing **in-place data migration** from the older version. Upgrade tests must include a separate stage restoring an older snapshot and executing the real upgrade path.

## 7. Designing fixtures to catch bugs, not just pass easily

A minimal yet high-value fixture must contain cases where broken logic **produces different output**:

| Scenario | Why it is required |
|---|---|
| Two Customers in different tenants sharing **customerId** | Catches missing tenant scope |
| Two Orders belonging to one Customer | Catches queries returning only a single Order |
| A Customer with no Orders | Tests empty results and `OPTIONAL MATCH`/null handling |
| An Order with no matching Customer | Detects broken links during migration |
| Reversed relationship direction | Catches confusing **->** with **<-** |
| Two paths to the same node | Catches missing **`DISTINCT`** when required by business rules |
| IDs with leading zeros, Unicode, and special characters | Catches normalization or type-casting bugs |
| Missing timestamps/dates or timezone boundaries | Catches null defaults and temporal conversion bugs |
| Two requests sharing an idempotency key | Catches duplicate creation and retry handling bugs |

For path/route tests, include a small graph where you can verify **hop counts**, relationship direction, and total weights if using GDS. When multiple tied shortest paths exist, assert against the **set of valid paths** or required constraints rather than pinning one arbitrary path when the algorithm makes no tie-breaking guarantee.

### 7.1. Negative data tests

Do not test only valid records. For instance, attempt to create an Order with a duplicate business key:

~~~cypher
CREATE (:DemoRegression:DemoRegressionOrder {
  tenantId: 'shop-a', orderId: 'O-1', legacyCustomerId: 'C-1'
});
~~~

When O-1 already exists and the uniqueness constraint is active, the statement must **fail**. This negative test is essential: a system is not automatically correct just because read queries return expected rows.

Similarly, test inputs missing keys, mistyped properties, cross-tenant edges, and concurrent writes. Assert **error categories or postconditions** rather than coupling tests to exact message strings that vary across versions.

### 7.2. Testing invariants instead of brittle snapshots

Durable invariants to enforce long-term:

- Each **(tenantId, orderId)** has at most one Order.
- Each Order links to its exact corresponding Customer once migration completes.
- **`DEMO_REG_PLACED`** relationships always point Customer → Order.
- Zero relationships connect two different tenants.
- Running migration a second time increases neither node nor relationship counts.
- Retrying an order-creation API with the same key causes no extra side effects.

Distinguish **"at most one"** from **"exactly one"**: a uniqueness constraint enforces uniqueness, yet cannot alone guarantee every Order has a Customer relationship.

## 8. Testing rollbacks, transactions, and mid-run failures

### 8.1. A failing migration may not roll back earlier batches

If a migration executes with **`CALL { ... } IN TRANSACTIONS`**, each batch commits independently. A failure in batch three does not roll back the first two committed batches. Therefore, verify:

1. Can the migration be re-run **safely** after fixing bad records?
2. Does re-running create duplicate relationships or orphan nodes?
3. Are skipped records reported visibly instead of silently losing data?
4. Can the application temporarily read both old and new models during transition?

Never write a migration test that runs once on clean data alone; that does not prove recovery from mid-process failures.

### 8.2. Contention, locks, and lost updates

For concurrent transactions, test at minimum:

- Two transactions concurrently calling **`MERGE`** on a node with a business key protected by a uniqueness constraint.
- Two transactions concurrently incrementing a counter without losing an update.
- Two transactions modifying nodes in opposite orders, potentially triggering a deadlock.
- Retrying after a transient error without executing external side effects twice.

Use **`CountDownLatch`/`CyclicBarrier`** or controlled synchronization with strict timeouts. Never leave unbounded non-deterministic deadlock tests running in CI. Verify the **accurate, duplicate-free final state** after all attempts complete rather than counting exceptions alone.

### 8.3. Never use a standalone Testcontainer to certify cluster behavior

A single standalone Neo4j container tests **Cypher**, constraints, the Java Driver, and basic transactions. It does **not** reproduce:

- Multi-server cluster routing tables.
- Reader/writer replication lag or causal consistency bookmarks via replicas.
- Leader election and re-routing after failover.
- Production cluster topology, Enterprise privileges, and recovery behavior.

Those features require dedicated topology tests and appropriately configured environments. Never claim "failover tested" after simply restarting a standalone container.

## 9. Performance regressions: right results, slower execution

### 9.1. What do `EXPLAIN` and `PROFILE` measure?

~~~cypher
EXPLAIN
MATCH (o:DemoRegressionOrder {
  tenantId: $tenantId,
  legacyCustomerId: $customerId
})
RETURN o.orderId AS orderId;
~~~

~~~cypher
PROFILE
MATCH (c:DemoRegressionCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})-[:DEMO_REG_PLACED]->(o:DemoRegressionOrder)
RETURN o.orderId AS orderId;
~~~

**`EXPLAIN`** builds the plan **without executing the query**. **`PROFILE`** runs the query and reports **`Rows`**, **`DB Hits`**, and memory/operator metrics when supported by the runtime. Running **`PROFILE` on a write query** still **mutates data**—never profile migration writes in production without assessing impact.

Key metrics to inspect:

| Metric | Question |
|---|---|
| **`Rows`** | Did intermediate rows explode due to fan-out? |
| **`DB Hits`** | Does the new access path read significantly more data? |
| **`Index Seek/Scan`** | Does the query find nodes via an index or scan a huge label? |
| **`Expand / VarLengthExpand`** | Does traversal follow the right type/direction with bounded depth? |
| **`Estimated Rows` vs. `Rows`** | Did the planner severely misestimate selectivity? |
| **Memory / page cache** | Is there memory or I/O pressure? |
| **p50/p95/p99 latency** | Do users experience higher latency under representative load? |

**Never compare execution plans character-for-character** across two Neo4j versions and assume one version is broken. The planner can rename operators, reorder execution, and change runtimes while staying accurate and faster. Regression tests should check **semantics**, **performance budgets**, and critical invariants like avoiding full scans on huge labels.

### 9.2. Measurements must be apples-to-apples

- Use the same dataset in **size, skew, and selectivity**.
- Use the same parameter mix (both common and rare keys, not one cherry-picked ID).
- Hold CPU/RAM/disk, configuration, connection counts, and background load constant.
- Separate **cold cache** from **warm cache**; run sufficient warm-up iterations.
- Collect multiple samples and inspect distributions rather than single-run timings.
- Isolate **schema/index migration impact** from **server upgrade impact** whenever possible.

Creating or dropping indexes/constraints triggers replanning, and updated data statistics shift planner decisions. Thus, a plan change after a schema migration **does not automatically mean** a performance bug; measure actual workload behavior.

### 9.3. Setting meaningful regression thresholds

Example team policy (thresholds must be chosen by your project, not treated as universal Neo4j standards):

| Check | Illustrative acceptance criterion |
|---|---|
| **Correctness** | 100% of required invariants pass |
| **Core API query p95** | Within committed SLO |
| **DB Hits on keyed lookups** | No abnormal jump under fixed data/distribution |
| **Migration duration** | Fits within approved maintenance window |
| **Storage and memory** | Within infrastructure budget |
| **Transient errors / retries** | Within acceptable bounds |

On a 7-node fixture, **`DB Hits` and timings** prove nothing about production performance; maintain a separate **large, representative, anonymized** dataset for performance regression suites.

## 10. Upgrading Neo4j and Cypher versions: mandatory checks

### 10.1. Lock down every environment component

A **test matrix** should explicitly document:

| Component | Before change | After change |
|---|---|---|
| **Neo4j Server** | Current version | Target version, pinned tag/patch |
| **Cypher language** | Cypher 5 or current mode | Cypher 5 / Cypher 25 if supported |
| **Java Driver** | Prior major/minor | Compatible target version |
| **Spring Data Neo4j** | Framework version | Target version |
| **APOC / GDS** | Compatible plugin versions | Plugins matched to target server |
| **Schema** | Existing indexes/constraints | Post-migration schema |
| **Data** | Legacy snapshot/fixture | Data after real migration |

Starting with **Neo4j 2025.06**, the server supports choosing **Cypher 5** or **Cypher 25**. Never send **`CYPHER 25`** to older servers that do not support it.

~~~cypher
// Run on a server supporting this language option.
CYPHER 5
MATCH (n:DemoRegressionOrder)
RETURN count(n) AS total;
~~~

~~~cypher
// Run only on Neo4j 2025.06+ supporting Cypher 25.
CYPHER 25
MATCH (n:DemoRegressionOrder)
RETURN count(n) AS total;
~~~

Changing both the server version and default Cypher language simultaneously makes root-causing failures difficult. Test first with **the same Cypher language** across old and new servers (where possible), and separately test switching **Cypher 5 → Cypher 25**.

### 10.2. Never assume upgrades can be downgraded

Per Neo4j operational guidelines, **downgrades are unsupported**. A rollback plan for an upgraded database must rely on a **pre-upgrade backup/snapshot** and a rehearsed **restore** procedure—not simply reinstalling the old binary against upgraded store files.

When upgrading from older Neo4j versions to 2025–2026 releases, follow **LTS checkpoints** and official upgrade paths for your exact source/target versions. For example, upgrading from versions prior to **Neo4j 5.26 LTS** into 2025–2026 must pass through the required checkpoint per official docs. Never skip steps just because a fresh test container starts cleanly.

### 10.3. Upgrade tests differ from fresh-init tests

**Fresh-database test:** build the fixture from scratch inside the target Neo4j image and run Cypher.

**Real upgrade test:** start or restore a **database created by the source version**, run the supported upgrade procedure, and then:

- Confirm the database and schema come online with healthy indexes.
- Run the **same golden queries** and invariants.
- Run model migrations if applicable and check idempotency.
- Verify the driver, SDN, plugins, authorized procedures, and topology routing.
- Check performance, logs, and deprecation/removal warnings.
- Rehearse **restoring the pre-upgrade backup** in a staging environment.

Passing tests on **two independent fresh containers** does not validate **store format compatibility, historical data, or the upgrade path**.

## 11. Safe workflow for changing data models

A low-risk approach is **expand → migrate → verify → contract**:

~~~mermaid
flowchart LR
  A["Baseline: old query + invariants"] --> B["Expand: add new schema/read path"]
  B --> C["Migrate: backfill data in batches"]
  C --> D{"Verify: reconcile + regression"}
  D -->|"PASS"| E["Contract: remove old path per plan"]
  D -->|"FAIL"| F["Halt rollout, fix or restore per plan"]
~~~

### 11.1. Baseline

Before changing anything:

1. Define business questions, golden datasets, and invariants clearly.
2. Save legacy queries, expected outputs, versions, and schema.
3. Record baseline p95 and DB Hits for critical queries.
4. Ensure a test environment and recoverable backup exist.

### 11.2. Expand

Add the new schema in a **backward-compatible** manner—for example, adding **`DEMO_REG_PLACED`** relationships without removing **`legacyCustomerId`** yet. In production, remember the new representation will be incomplete during the backfill window.

### 11.3. Migrate

Run repeatable migrations, typically batched on large graphs. Reconcile migrated node counts, created relationship counts, records missing endpoints, and constraint failures. If the system accepts live writes during migration, use controlled **dual-writes** or **change capture** so concurrent changes are not missed.

### 11.4. Verify

Before switching all traffic to the new model:

- Compare old vs. new query results across multiple tenants and representative datasets.
- Re-run the migration to confirm idempotency.
- Verify identity constraints, relationship direction/type, and data invariants.
- Run concurrency and performance regression suites.
- Verify Java Driver behavior, SDN repository mapping, and API contracts.

### 11.5. Contract

Remove legacy properties, old indexes, or legacy code branches only after proving the new queries cover business rules, no readers/workers/consumers still depend on the old layout, and the observation window passes cleanly. **Never bundle "add new relationship" and "drop old property" into one big-bang deploy** when the system requires multi-step rollout.

**Note:** even when every step is tested, production migrations and schema changes still need a dedicated backup/restore plan; Neo4j transactions cannot roll back batches that have already committed.

## 12. Running regression suites in CI/CD

Conceptual pipeline example:

~~~text
Pull request:
  - Compile + static checks
  - Unit tests for mapping/validation
  - Testcontainers: Cypher + constraints + small migration
  - Idempotency / tenant isolation tests

Release candidate:
  - Neo4j/driver/Cypher version matrix
  - Rehearse upgrade on old data snapshot
  - Contract/API tests
  - Performance regression with representative dataset
  - Verify plugins, security, and clustering if used

Production deployment:
  - Tested backup and restore plan
  - Step-by-step expand/migrate/verify/contract
  - Monitor errors, latency, and sanitized query logs
  - Halt rollout if any invariant or SLO is violated
~~~

**CI rules:**

- Every job gets its own database/container or strictly isolated namespace.
- Pin Neo4j images and dependencies; record versions in test reports.
- Keep fixtures immutable or rebuilt before each test; never depend on test order.
- On failure, capture anonymized seeds, stack traces, queries, and non-sensitive parameters as artifacts.
- Run benchmarks on comparable runners and avoid overly noise-sensitive thresholds.
- Never issue test writes or deletes against production.

### 12.1. Report template for a regression test

| Field | Value to record |
|---|---|
| **Test ID** | E.g., `REG-ORDER-MIGRATION-001` |
| **Source/target version** | Neo4j, Java Driver, Cypher mode |
| **Fixture** | Dataset name, hash/checksum, or reference commit |
| **Change** | Migration script, query edit, or binary upgrade |
| **Expected** | Business outcome and invariants |
| **Actual** | Observed result and delta |
| **Performance** | p95, DB Hits, Rows, load, dataset size |
| **Status** | PASS / FAIL / BLOCKED |
| **Rollback evidence** | Which backup was restore-tested |

Not every test needs benchmarks; performance metrics can be required only in the **performance suite**. What matters most is that every bug is captured by a test that **actually fails on the buggy version and passes after the fix**.

## 13. Common mistakes when writing Neo4j tests

1. **Testing only with mocked repositories.** Mocks miss inverted Cypher directions, null semantics, and server constraint errors.
2. **Using pre-existing developer data.** Tests become machine- and order-dependent and fail to reproduce in CI.
3. **Not pinning Neo4j/driver/plugin versions.** Version-specific bugs lose diagnostic evidence.
4. **Comparing counts instead of node/relationship sets.** Matching counts can still hide wrong tenants.
5. **Overly clean fixtures.** Without cross-tenant ID collisions, missing properties, or wrong directions, buggy code passes.
6. **Updating assertions to match new output without consulting business owners.** Tests turn regressions into "accepted behavior".
7. **Omitting `ORDER BY` yet asserting exact list order.** Cypher makes no ordering promise unless explicitly requested.
8. **Asserting exact error messages or exact query plans.** Both change across releases while semantics stay valid.
9. **Forgetting to test running migrations twice.** Non-idempotent steps duplicate nodes/relationships on retry.
10. **Using `Thread.sleep` to force race conditions.** Tests flake based on OS scheduler and CI speed.
11. **Running `PROFILE` on production write statements.** `PROFILE` executes the query rather than just planning it.
12. **Testing only fresh images without testing upgrades of old data.** Misses store format and historical data issues.
13. **Assuming standalone Testcontainers simulates a cluster.** Misses replica lag, bookmarks, and real failover.
14. **Assuming binary upgrades can downgrade for rollback.** Neo4j requires a proper restore strategy.
15. **Ignoring `POPULATING` or `FAILED` indexes.** Timing and performance tests produce misleading conclusions.

## 14. Practice exercises

### Exercise 1 — Creating a minimal reproducible case

After a migration, an API returns orders from tenant `shop-b` when querying Customer `C-1` in `shop-a`. Write three minimal Customer/Order nodes and two Cypher queries sufficient to reproduce the bug. Specify the parameter values and the assertion that fails when **`tenantId`** is omitted.

### Exercise 2 — Golden tests and idempotent migrations

Seed the Section 4 fixture, record the legacy query output, run the migration to **`DEMO_REG_PLACED`**, compare the new query, and run the migration a second time. Explain why having four final relationships is necessary yet **not sufficient** to prove correct tenants and edge direction.

### Exercise 3 — Finding gaps in a test suite

A test checks only **`count(Order) = 4`** before and after migration. List at least four data bugs that this test misses and propose corresponding invariants.

### Exercise 4 — Regressions when changing Cypher language

An application upgrades from Neo4j 5.26 to a 2026 release supporting Cypher 5 and Cypher 25. Design a matrix running the same queries under both Cypher configurations, separating syntax errors, behavioral changes, result differences, and performance changes. Why pin the language mode in the first comparison?

### Exercise 5 — Contention and retries

Two workers concurrently create Orders with business key **`(tenantId, orderId)`**. Propose an integration test with a uniqueness constraint that intentionally sends two competing transactions. Afterward, which conditions must be checked to prove no duplicate nodes and no repeated side effects occurred?

### Exercise 6 — Rehearsing an upgrade

You have a pre-upgrade Neo4j snapshot, the target server version, and new Java Driver/SDN and APOC versions. Outline the step-by-step verification from snapshot restore, guided startup, index readiness, and golden tests through verifying rollback using the old backup.

### Exercise 7 — Performance regression

A query still returns the exact same set of Orders, yet p95 latency triples after adding relationships. List how to collect **`PROFILE`**, intermediate row counts, **`DB Hits`**, index status, and data distribution to distinguish planner bugs, fan-out growth, and test-environment shifts.

## 15. Key takeaways

Controlling regressions when changing a **property graph model** or **Neo4j version** starts with **a reproducible bug**, a **fixture designed to expose failures**, and **explicit business invariants**. Solid tests cover nodes, relationships, direction, types, business keys, transactions, tenant scope, and retry behavior.

The Java Driver, JUnit 5, and Testcontainers let you run Cypher on real Neo4j in a repeatable environment. Yet a fresh container cannot substitute for testing **legacy store migrations, cluster topologies, or large-scale load**. Before deploying, run **golden queries, idempotent migration checks, constraint checks, and behavioral/performance regressions**, and prepare **backup/restore** procedures since Neo4j upgrades do not support simple downgrades.

### Official references

- [Neo4j Cypher Manual – MERGE and data handling](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Neo4j Cypher Manual – Constraints](https://neo4j.com/docs/cypher-manual/current/constraints/)
- [Neo4j Cypher Manual – EXPLAIN/PROFILE and execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j Cypher Manual – Query plan caching](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/caching/)
- [Neo4j Upgrade and Migration Guide – Introduction](https://neo4j.com/docs/upgrade-migration-guide/current/)
- [Neo4j Upgrade and Migration Guide – Neo4j 2025–2026](https://neo4j.com/docs/upgrade-migration-guide/current/version-2025-2026/)
- [Neo4j Operations Manual – Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/)
- [Neo4j Java Driver Manual – Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Testcontainers for Java – Neo4j module](https://java.testcontainers.org/modules/databases/neo4j/)
- [JUnit 5 – User Guide](https://junit.org/junit5/docs/current/user-guide/)
