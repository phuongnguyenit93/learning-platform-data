# Adding Integration Tests, Load Tests, and a Performance Dossier to the Neo4j Capstone

## Learning Objectives

By the end of this lesson in the **Capstone Project** chapter, you will be able to:

1. Turn business requirements into **test cases and measurable quality gates**, separating correctness from raw speed.
2. Test against a **real Neo4j instance** instead of mocking repositories: nodes, relationships, constraints, transaction rollbacks, idempotency, access control, and dirty data.
3. Use **JUnit 5 + Testcontainers** to run integration tests for Java Driver / Spring Data Neo4j against an isolated database with deterministic seeding and cleanup.
4. Design **baseline, load, stress, spike, and soak** scenarios with data skew and query mixes resembling real systems.
5. Use **k6** to drive API requests with payload checks, defining thresholds for p95/p99, error rate, throughput, and dropped iterations.
6. Explain results using **Cypher EXPLAIN/PROFILE**, DB Hits, Rows, indexes, fan-out, heap, page cache, I/O, and connection pools.
7. Write a **reproducible performance dossier**: environment, dataset, versions, configuration, workload, results, before–after comparisons, limitations, and go/no-go decision.
8. Place tests at the right CI stages, protect data, and avoid risky load tests against production.

The **DATABASE_ENGINE_GRAPH_NEO4J** module uses Neo4j to model **property graphs** and query links/paths with Cypher, combining constraints, indexes, data ingestion, Java Driver, and Spring Data Neo4j. This lesson brings those skills together into the **acceptance phase** of a capstone that already has an API and graph model: proving not just “the demo runs,” but **functional correctness, stability under target load, diagnosed bottlenecks, and verifiable evidence**.

> **Scope and compatibility:** Java snippets illustrate APIs from Spring Boot 3.x, JUnit 5, modern Neo4j Java Driver, and compatible Testcontainers. Artifact/package names in Testcontainers and `@ServiceConnection` registration can vary across major lines. Pick a consistent BOM, pin the Neo4j tag, and consult docs for your exact versions. This lesson **never asks you to run load tests on production**. All numbers and metrics below are illustrative learning examples, not Neo4j performance guarantees.

## 1. Sample Project and Required Deliverables

Consider a **Graph Commerce** application:

- `Customer` nodes place `Order` nodes.
- Orders link to `Product` nodes via `CONTAINS` relationships carrying a `quantity` property.
- A Java/Spring API creates orders, lists orders per customer, views product details on an order, and queries co-purchased products.
- Neo4j stores the graph keyed by business IDs; the API uses Java Driver or Spring Data Neo4j. If PostgreSQL is the authoritative order store and Neo4j is a read model, tests must also cover **eventual consistency / CDC** instead of assuming source commit time equals graph visibility time.

~~~mermaid
flowchart LR
    C["Customer<br/>customerId"] -->|PLACED| O["Order<br/>orderId, status, totalCents"]
    O -->|"CONTAINS {quantity}"| P["Product<br/>sku, name, category"]
    API["Spring Boot API"] -->|Neo4j Driver / SDN| G[("Neo4j")]
    G --> C
    G --> O
    G --> P
    TEST["JUnit + Testcontainers"] -.->|Integration test| G
    LOAD["k6"] -->|HTTP workload| API
    MET["Metrics + profiling"] -.-> G
    MET -.-> API
~~~

**Recommended acceptance deliverables:**

| Artifact | Required contents | Evidence |
| --- | --- | --- |
| **Test matrix** | Functional cases, invariants, failure modes, data sources | Table of case ID → expected result |
| **Integration suite** | Real Neo4j connection, seed, tests, teardown, rollback/constraints | Pass/fail logs with version and commit |
| **Load scripts** | Workload profile, arrival rate, duration, auth/test data, thresholds | Versioned script and exact run command |
| **Raw performance results** | p50/p95/p99, errors, throughput, dropped iterations, resource metrics | Timestamped raw result files, not just screenshots |
| **Cypher plans** | `EXPLAIN`/`PROFILE` for representative queries | Operators, Rows, DB Hits, index usage |
| **Performance dossier** | Baseline, environment, comparison, conclusion, limitations | Measurement tables + go/no-go + recommendations |
| **Recovery / verification notes** | Dataset cleanup, restore steps, regression checks | Test runbook and post-fix checklist |

**Overall standard:** A capstone does not pass merely because a container starts or an API returns HTTP 200. You need **assertions on graph and data state**, performance thresholds, load-test evidence, and root-cause explanations whenever a threshold is missed.

## 2. Turning Requirements into a Test Contract

Before writing tests, lock down domain invariants:

1. `Customer.customerId`, `Order.orderId`, and `Product.sku` are stable, unique **business keys**.
2. Each order is placed by **exactly one customer** in this lab model; `PLACED` points from `Customer` to `Order`.
3. `CONTAINS` edges connect `Order` to `Product`; `quantity` must be a positive integer.
4. Re-creating an order with the **same ID and payload** is safely idempotent; conflicting payloads must be rejected or handled per an explicit policy.
5. Every order creation runs inside one **transaction**, leaving zero partial state if an intermediate step fails.
6. Users may read/write only data belonging to their **authorized tenant** in multi-tenant setups.
7. Paginated/limited API endpoints enforce **deterministic ordering** so pages never duplicate or skip items.

### 2.1. Illustrative Test Case Matrix

| ID | Test case | Expected result | Test level |
| --- | --- | --- | --- |
| IT-01 | Create Customer and Order, link `PLACED` | 1 Customer, 1 Order, 1 correctly directed edge | Integration |
| IT-02 | Resend same `orderId` and payload | No duplicate nodes or edges | Integration |
| IT-03 | Same `orderId` with different payload | Conflict returned; no silent overwrite | Integration/API |
| IT-04 | Attempt two Orders with duplicate business key | Constraint blocks the second transaction | Integration |
| IT-05 | Exception between multiple Cypher statements in one tx | Entire transaction rolls back | Integration |
| IT-06 | Order with zero Products or missing property | Response/validation matches contract | Integration |
| IT-07 | `CONTAINS.quantity <= 0` | API rejects input; graph unchanged | API/Service |
| IT-08 | Tenant A user queries Tenant B data | Denied or returns no cross-tenant data | Security integration |
| IT-09 | Query Customer with 0 / 1 / 10,000 Orders | Accurate results without over-fetching the graph | Integration + perf |
| LT-01 | 80 READ + 20 WRITE at 100 req/s total | Meets latency and error SLOs | Load |
| LT-02 | Ramp load up to saturation | Identifies breaking point and recovery behavior | Stress |
| LT-03 | Hold steady load for 60 minutes | No memory leak, pool leak, or unbounded backlog | Soak |

Counts and ratios are **examples establishing the contract**. Performance tests must reflect your capstone's expected traffic rather than picking an arbitrary RPS just for pretty charts.

### 2.2. Separating Correctness from Non-Functional Requirements

- **Correctness gate:** API returns exact business IDs, status, relationships/directions, uniqueness, rollbacks, and access boundaries.
- **Reliability gate:** zero duplicates on retries, timeout handling, clear error codes, and clean recovery after disconnects.
- **Performance gate:** p95/p99 latency, throughput, error rate, resource utilization, and projection freshness.
- **Operational gate:** logging, tracing, metrics, backup/cleanup procedures, and reproducible benchmark steps.

If p95 is tiny while 25% of relationships are missing, that is a **FAIL**, not a tuning win. Conversely, if data is accurate while p99 breaches SLA, the capstone is **not yet ready for sign-off**.

## 3. Testing Strategy: Unit, Integration, API, and Load

A balanced test suite never relies on a single layer:

| Level | Environment | What to verify | What it cannot prove |
| --- | --- | --- | --- |
| **Unit** | Mocked parser/service/validator | Input validation, DTO building, standalone auth policies | Real Neo4j transactions, Cypher syntax/indexes |
| **Repository/Driver integration** | Real Neo4j Testcontainers | Constraints, MERGE, relationships, mapping, commit/rollback | Full HTTP/auth/network stack |
| **API integration** | Spring app + Neo4j container | JSON, HTTP status, auth, service/repo, error mapping | Sustaining 100 req/s under load |
| **End-to-end** | Isolated services and dependencies | Real workflows, CDC/outbox if present, eventual consistency | Every production failure mode |
| **Performance/load** | Staging matching prod on key variables | Throughput, p95/p99, bottlenecks, error rate under load | Transaction correctness on edge paths without explicit assertions |
| **Recovery/failure** | Lab / test cluster | Restarts, retries, backlog drain, recovery | Real HA behavior if topology differs |

**Unit tests mocking a Neo4j repository do not prove Cypher even parses or runs.** Integration tests with a real container verify parser/planner, indexes, and transactions. Conversely, single-request integration tests do not prove a service handles sustained load.

### 3.1. Isolated Environments and Reproducible Data

- Run test containers/databases **strictly for testing**, never connected to production.
- Pin image tags and versions to your deployment target, or use digests for exact reproducibility.
- Seed with a **fixed random seed / dataset version**; never depend on shifting live data.
- Clean up before each test only inside a verified dedicated test database/container.
- Never run tests in parallel against the same database if `@BeforeEach` wipes the whole graph.
- Avoid running “read-only tests against production” to save setup time; performance and security become uncontrolled.

For Neo4j multi-database or clustered deployments, single-container integration suites **do not test failover or quorum**; spin up a dedicated test cluster if HA is in scope.

## 4. Graph Model, Schema, and Fixtures

Your project first needs a **minimal schema and deterministic fixture data** so tests never flake randomly.

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;

CREATE CONSTRAINT product_sku_unique IF NOT EXISTS
FOR (p:Product)
REQUIRE p.sku IS UNIQUE;

CREATE RANGE INDEX order_created_at IF NOT EXISTS
FOR (o:Order) ON (o.createdAt);
~~~

Small fixture example:

~~~cypher
MERGE (c:Customer {customerId: 'C-101'})
SET c.displayName = 'Lan';

MERGE (o:Order {orderId: 'O-901'})
SET o.status = 'CREATED',
    o.totalCents = 150000,
    o.createdAt = datetime('2026-11-01T10:00:00Z');

MERGE (p:Product {sku: 'P-BOOK-1'})
SET p.name = 'Graph Book', p.category = 'Books';

MATCH (c:Customer {customerId: 'C-101'})
MATCH (o:Order {orderId: 'O-901'})
MATCH (p:Product {sku: 'P-BOOK-1'})
MERGE (c)-[:PLACED]->(o)
MERGE (o)-[r:CONTAINS]->(p)
SET r.quantity = 2;
~~~

### 4.1. Fixtures Must Cover Boundaries and Data Skew

| Fixture type | Example | Bugs exposed |
| --- | --- | --- |
| Zero edges | New Customer with no Orders | `MATCH` instead of `OPTIONAL MATCH` drops the Customer |
| Single edge | 1 Customer → 1 Order | Inverted relationship direction or mapping bugs |
| High degree | 1 Customer → 10,000 Orders | Fan-out, sorting cost, over-fetching, p99 tail latency |
| Nested fan-out | Order → 20 Products | N+1 queries, duplicate rows, bloated `collect` |
| Null/absent data | Null `displayName`, missing `createdAt` | Java DTO mapping, sorting, validation errors |
| Unicode values | Accented names and emojis | Encoding, search, or analyzer bugs |
| Business key conflict | 2 requests with same `orderId` | Constraint, idempotency, retry bugs |
| Multi-tenant | Same ID across tenants | Cross-tenant graph leakage |

Never insert 10,000 orders in one giant transaction. Seed in bounded batches using `UNWIND`:

~~~cypher
UNWIND $orders AS item
MERGE (c:Customer {customerId: item.customerId})
MERGE (o:Order {orderId: item.orderId})
SET o.status = item.status,
    o.totalCents = item.totalCents,
    o.createdAt = datetime(item.createdAt)
MERGE (c)-[:PLACED]->(o);
~~~

In integration tests, `$orders` comes from a **fixed test seed**. Re-running identical data via `MERGE` should avoid duplicates, yet seed scripts must never clobber runtime state unintentionally. For versioned performance datasets, verify record counts **before starting measurements**.

### 4.2. Neo4j Constraints and Indexes Must Actually Be Online

~~~cypher
SHOW INDEXES
YIELD name, type, state, populationPercent, labelsOrTypes, properties
RETURN name, type, state, populationPercent, labelsOrTypes, properties
ORDER BY name;
~~~

If a critical index is still `POPULATING` or `FAILED`, benchmark numbers reflect **index building** rather than steady-state performance. Record when index population finishes, then measure cold-cache and warm-cache runs separately.

## 5. Testcontainers and JUnit 5: Running Real Neo4j

### 5.1. Dependencies Setup

Gradle (Groovy DSL) example, assuming the Spring Boot plugin and dependency management or BOM pin compatible versions:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-neo4j'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:neo4j'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

**Version note:** the artifact/package names above match the Testcontainers 1.x line widely used with Spring Boot 3.x; Testcontainers 2.x may alter module/package names. Use the BOM for your chosen line—never mix 1.x and 2.x JARs. Testcontainers requires a **working Docker runtime** on dev/CI machines; without Docker, container tests cannot run automatically.

With Spring Boot 3.x and `spring-boot-testcontainers`, `@ServiceConnection` can supply `Neo4jConnectionDetails` automatically. The example below uses `@DynamicPropertySource` so every connection property is explicit without special configuration classes.

### 5.2. A Compact Service Under Test

Java example assuming an appropriate package and Spring component scanning:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.springframework.stereotype.Service;

@Service
public final class GraphOrderService {
    private final Driver driver;

    public GraphOrderService(Driver driver) {
        this.driver = driver;
    }

    public void createOrder(
            String orderId, String customerId, long totalCents) {
        if (orderId == null || orderId.isBlank()
                || customerId == null || customerId.isBlank()
                || totalCents < 0) {
            throw new IllegalArgumentException("Invalid order");
        }
        var params = Map.<String, Object>of(
                "orderId", orderId,
                "customerId", customerId,
                "totalCents", totalCents);

        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            session.executeWriteWithoutResult(tx -> {
                var rows = tx.run("""
                    MERGE (c:Customer {customerId: $customerId})
                    MERGE (o:Order {orderId: $orderId})
                    ON CREATE SET
                      o.customerId = $customerId,
                      o.totalCents = $totalCents,
                      o.status = 'CREATED'
                    WITH c, o
                    WHERE o.customerId = $customerId
                      AND o.totalCents = $totalCents
                    MERGE (c)-[:PLACED]->(o)
                    RETURN o.orderId AS orderId
                    """, params).list();
                if (rows.size() != 1) {
                    throw new IllegalArgumentException(
                            "Order ID conflicts with existing payload");
                }
            });
        }
    }

    public long countOrders(String orderId) {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx -> tx.run("""
                MATCH (o:Order {orderId: $id})
                RETURN count(o) AS n
                """, Map.of("id", orderId))
                .single().get("n").asLong());
        }
    }

    public long countPlaced(String orderId) {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(tx -> tx.run("""
                MATCH (:Customer)-[:PLACED]->(o:Order {orderId: $id})
                RETURN count(*) AS n
                """, Map.of("id", orderId))
                .single().get("n").asLong());
        }
    }
}
~~~

Key design points in this example:

- Uses the **shared Spring-managed Driver**; opens a dedicated `Session` per operation.
- `executeWriteWithoutResult` executes all Cypher in **one managed transaction**, rolling back on exception.
- `MERGE` uses business IDs backed by **uniqueness constraints**; never `elementId` for cross-system keys.
- Re-sending an `orderId` with an identical payload creates no extra Order or edge in this simplified model.
- Conflicting payloads throw an exception and roll back; production APIs should map this to HTTP `409 Conflict` and define explicit Order state transitions.

**Scope to upgrade for real systems:** This snippet models only a single immutable owner per order—it does not handle order line items, ownership transfers, deletions, multi-step workflows, multi-tenancy, or high-concurrency writes. Never treat this example as a full domain spec. `MERGE` plus constraints prevent duplicate IDs, yet multiple concurrent writers targeting the same aggregate still need retry/lock ordering and concurrency tests.

### 5.3. Integration Test with an Isolated Container

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.Neo4jContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class GraphOrderIntegrationTest {
    @Container
    static Neo4jContainer<?> neo4j =
            new Neo4jContainer<>("neo4j:5.26")
                    .withAdminPassword("test-only-password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.neo4j.uri", neo4j::getBoltUrl);
        registry.add("spring.neo4j.authentication.username", () -> "neo4j");
        registry.add("spring.neo4j.authentication.password",
                () -> "test-only-password");
    }

    @Autowired Driver driver;
    @Autowired GraphOrderService service;

    @BeforeEach
    void resetGraphAndSchema() {
        // ONLY on a dedicated test container: NEVER run in prod!
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            session.run("MATCH (n) DETACH DELETE n").consume();
            session.run("""
                CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
                FOR (c:Customer) REQUIRE c.customerId IS UNIQUE
                """).consume();
            session.run("""
                CREATE CONSTRAINT order_id_unique IF NOT EXISTS
                FOR (o:Order) REQUIRE o.orderId IS UNIQUE
                """).consume();
        }
    }

    @Test
    void createAndReplaySameOrderIsIdempotent() {
        service.createOrder("O-T1", "C-T1", 125_000L);
        service.createOrder("O-T1", "C-T1", 125_000L);

        assertEquals(1L, service.countOrders("O-T1"));
        assertEquals(1L, service.countPlaced("O-T1"));
    }

    @Test
    void conflictingPayloadDoesNotOverwriteExistingOrder() {
        service.createOrder("O-T2", "C-T2", 100_000L);

        assertThrows(IllegalArgumentException.class,
                () -> service.createOrder("O-T2", "C-T2", 200_000L));
        assertEquals(1L, service.countOrders("O-T2"));
        assertEquals(1L, service.countPlaced("O-T2"));
    }

    @Test
    void exceptionRollsBackEntireNeo4jTransaction() {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            assertThrows(IllegalStateException.class,
                    () -> session.executeWriteWithoutResult(tx -> {
                        tx.run("""
                            CREATE (:Order {orderId: 'O-ROLLBACK'})
                            """).consume();
                        throw new IllegalStateException("forced rollback");
                    }));
        }
        assertEquals(0L, service.countOrders("O-ROLLBACK"));
    }
}
~~~

Tests target the **`neo4j` database inside an isolated container**. `MATCH (n) DETACH DELETE n` intentionally wipes the graph **only in this test container**; never copy it into a shared database. This test class **must not run in parallel with another test class sharing the same wipe hook**. For large suites, use isolated databases per suite/container and controlled fixtures/rollbacks.

### 5.4. Additional Assertions Still Needed

- **Real constraints:** try `CREATE`ing a second `Order` with an existing `orderId`; assert Neo4j throws a constraint error and rolls back the failing transaction.
- **Relationship direction:** `(c)-[:PLACED]->(o)` exists and was never created backward.
- **Order–Product:** `quantity > 0` validated before writes; no duplicate relationships violating contract.
- **Read sorting/pagination:** identical datasets return deterministic order; `LIMIT` never drops valid edges silently.
- **Concurrent requests:** two threads submitting the same order ID never create duplicates; capture results/exceptions to distinguish conflicts from transient faults.
- **Security:** block cross-tenant API calls; never read tenant ID from unverified payloads.
- **Error mapping:** `ClientException`/constraint errors map to proper HTTP codes without leaking raw Cypher or secrets.

Tests that only assert “no exception thrown” are insufficient. Always **assert the final graph state** after requests, including rollback and retry paths.

## 6. Spring Data Neo4j: Testing Mapping and Transaction Lifecycles

With Spring Data Neo4j (SDN), test **real repositories/`Neo4jClient`** and entity-graph mapping:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;
import java.util.HashSet;
import java.util.Set;

@Node("Customer")
public class Customer {
    @Id
    private String customerId;
    private String displayName;

    @Relationship(type = "PLACED", direction =
            Relationship.Direction.OUTGOING)
    private Set<Order> orders = new HashSet<>();

    // Constructors/getters/setters required by your SDN version.
}

@Node("Order")
public class Order {
    @Id
    private String orderId;
    private String status;
    // Constructors/getters/setters required by your SDN version.
}
~~~

**These two classes are mapping fragments**, not complete compilable Java until constructors, getters, and setters are added. Prefer Java records/DTOs on read endpoints where full entity-graph hydration is unnecessary.

### 6.1. `@DataNeo4jTest` vs. `@SpringBootTest`

| Test annotation | Best suited for | Excluded by default |
| --- | --- | --- |
| `@DataNeo4jTest` | Slice tests for repositories, mappings, converters, `Neo4jClient` | Controllers, security, services outside the slice |
| `@SpringBootTest` | Full Spring context, services, transaction manager, driver integration | Real HTTP sockets unless webEnvironment is set |
| `@SpringBootTest(webEnvironment=RANDOM_PORT)` | E2E HTTP API tests inside Spring app | External dependencies like Kafka/PostgreSQL if unstarted |
| Direct Java Driver + Testcontainers | Cypher, constraints, transactions, read/write | SDN mapping or Controllers unless invoked |

When using `@ServiceConnection` on `Neo4jContainer`, add `spring-boot-testcontainers` matching your Spring Boot version per official docs. With `@DynamicPropertySource`, register URI/username/password as in section 5.

### 6.2. Test Transaction Rollbacks Can Mislead

Some test frameworks open a transaction around a test method and roll it back afterward. However:

- If a service uses a **different transaction manager**, or invokes a separate connection/process, it does not automatically share the test method's transaction.
- HTTP tests running against a **server on another thread** commit their own transactions; `@Transactional` on the test method cannot roll back server-side commits.
- **Java Driver** managed transactions open and commit independently of JUnit/Spring Test transactions.
- Testcontainers tearing down afterward **never substitutes** for asserting rollback behavior inside the test itself.

Always **re-query graph state** after injecting an error; for test isolation, reset the test container or use unique fixtures/keys rather than trusting implicit test-framework rollbacks.

### 6.3. Testing Over-Fetching and DTO Projections

An endpoint needing only `orderId`, `status`, and `totalCents` might accidentally load entire `Customer.orders` and `Order.items` trees through a repository. Add tests verifying:

- For high-degree Customers, the API returns only the **contracted Order page**, never all orders.
- DTOs expose only contracted fields and leak no sensitive properties.
- Queries use deterministic `ORDER BY` and proper `LIMIT`/cursor bounds.
- Measure wire rows/bytes and `DB Hits` to avoid **N+1** fetches across Orders.

Never conclude a query does not over-fetch just because “JSON serialization felt fast on a tiny fixture.” Test against **high-degree nodes** under load.

## 7. API Integration: Covering HTTP, Security, and Graph State

Sample API contract (**illustrative only**):

| Method | Endpoint | Behavior |
| --- | --- | --- |
| `POST` | `/v1/orders` | Accepts `orderId, customerId, totalCents`; creates order; identical payload replays idempotently |
| `GET` | `/v1/customers/{customerId}/orders?limit=20` | Lists Orders in defined order |
| `GET` | `/v1/orders/{orderId}/products` | Returns Products and quantities |
| `GET` | `/actuator/health/readiness` | Checks required dependencies per config |

Sample JSON contract:

~~~json
{
  "customerId": "C-101",
  "orders": [
    {
      "orderId": "O-901",
      "status": "CREATED",
      "totalCents": 150000
    }
  ],
  "hasMore": false
}
~~~

Real APIs must explicitly define:

- `201 Created` on new creation; `200 OK` (or chosen idempotent status) on replay; `409 Conflict` when `orderId` collides with a different payload.
- `400 Bad Request` for invalid inputs, `403 Forbidden` for unauthorized tenants, `404 Not Found` for missing resources per contract.
- How `hasMore`, sort fields, and cursors behave to avoid duplicates/skips during concurrent writes.
- Error payloads with correlation IDs, **never exposing raw Cypher, stack traces, or secrets**.

### 7.1. HTTP Tests Must Go Beyond Status Codes

A thorough API integration test should:

1. Send an HTTP request with valid auth credentials/roles.
2. Assert status code, JSON schema, business fields, pagination, and headers.
3. Re-query Neo4j by **business key** to verify persisted transaction effects.
4. Send replay and invalid requests; assert zero duplicates and intact edges.
5. In multi-tenant setups, assert cross-tenant IDs **are inaccessible**.

If production streams Orders into Neo4j via Kafka/CDC, tests must **wait with bounded polling and check version/watermark**, never assuming synchronous consistency with the source DB. Never use a fixed `Thread.sleep(3000)` as proof of consistency.

## 8. Workload Design: Measure Realistic Behavior, Not Blind HTTP Flooding

A load test script must specify **arrival patterns, request mix, dataset skew, and system state**.

### 8.1. Illustrative Operation Mix

| Operation | Target share | Data shape | Complexity |
| --- | ---: | --- | --- |
| Lookup Customer | 40% | Existing IDs, 5% non-existent | Index seek |
| List Orders | 30% | 10% high-degree Customers | Expand + sort + pagination |
| Order details / products | 10% | 1–20 Products/Order | 2-hop traversal |
| Create Order | 15% | Unique business ID per request | `MERGE`/constraint + transaction |
| Idempotent replay / conflict | 5% | Existing keys with controlled payloads | Constraint/retry/error path |

This is a **reference mix**; do not sample all IDs uniformly if production traffic skews heavily toward a handful of Customers.

### 8.2. Open vs. Closed Arrival Models

| Model type | Tool example | Meaning |
| --- | --- | --- |
| **Closed model** | k6 `constant-vus`, `ramping-vus` | Fixed VUs send the next request only after the previous finishes; when SUT slows, arrival rate drops automatically |
| **Open model** | k6 `constant-arrival-rate` | Targets iterations started per second independent of latency; closer to external user traffic |

**The coordinated omission problem:** If the generator waits for responses before starting new requests, slow SUT responses throttle the arrival rate, hiding latency and errors under target load. Arrival-rate executors expose **intended load** accurately, provided you monitor `dropped_iterations`: if VUs run out or SUT stalls severely, the generator **fails to sustain the target rate**.

### 8.3. Separating Read and Write Workloads

In Neo4j, WRITES involve:

- Transaction log flushes and index maintenance.
- Locking and constraint checks on business keys.
- Disk I/O and contention impacting concurrent READs via CPU/cache pressure.

READS involve:

- Index seeks, relationship expansions, sorting/aggregation, and serialization.
- Page cache warm/cold hits, traversed edge counts, and fan-out.

Therefore, benchmark **READ-only**, **WRITE-only**, and **mixed READ/WRITE** runs rather than reporting one blended “total RPS” figure.

## 9. Controlled Load Execution: Environment and Data Preparation

Before running k6 / Gatling / JMeter:

1. Target a **dedicated staging URL** explicitly authorized for load testing.
2. Record Neo4j, Java Driver, Spring Boot, and JVM versions, CPU/RAM/heap/page cache, disk type, topology, and connection pool settings.
3. Seed a dataset with **representative scale and skew**; confirm critical indexes are `ONLINE`.
4. Warm up long enough for JVM/JIT, connection pools, and caches to stabilize; measure cold-cache explicitly only when cold-cache is the test goal.
5. Run the generator on a host with ample CPU/network; monitor generator CPU/RAM/network to rule out **load-generator bottlenecks**.
6. Assign a unique **run ID**, business ID range, and cleanup policy; never reuse write IDs across runs unintentionally.
7. Set safety guardrails: max RPS, max duration, abort thresholds, resource alerts, and stop authority.
8. Log timestamps, Git commit/config, workload mix, and parameter distributions.

### 9.1. Dataset State Shapes Results

Two runs at the same RPS—one with 1,000 Orders and another with 10 million Orders—**are not directly comparable**. Node/relationship counts, index sizes, property lengths, degree skew, and hot keys all alter query plans, cache hit rates, and lock contention.

For READs, pick a fixed yet representative ID distribution; for WRITEs, generate fresh `orderId` values per iteration so you do not accidentally benchmark idempotent `MERGE` replays. Measure replays/conflicts in a **separate scenario**, since they typically do different work than fresh creations.

### 9.2. Authorization and Safety Hygiene

- Never put real PII or passwords into test payloads, dashboards, or raw logs.
- Never fire load traffic from public internet hosts at a production Bolt endpoint.
- Never trigger scripts that charge real payments or send unintended emails/SMS.
- Isolate load-test accounts from admin roles; scope tenants, datasets, and rate limits.
- Never allow unbounded auto-scaling of VUs that could overwhelm the generator or SUT uncontrollably.
- Keep an **emergency stop procedure** and monitor disk/transaction log capacity before long write runs.

## 10. k6 Script: HTTP Workload with Checks and Thresholds

This script assumes the API from section 7 is deployed in **staging**, returning `201` for new Orders and `200` with an `orders` array for GETs. Adjust paths, status codes, and schemas to match your real application.

~~~javascript
import http from 'k6/http';
import { check } from 'k6';
import exec from 'k6/execution';

// Target 40 READ + 10 WRITE iterations/s for 5 minutes.
// This is a simulated target rate, not a guaranteed SLA.
export const options = {
  scenarios: {
    read_orders: {
      executor: 'constant-arrival-rate',
      exec: 'readOrders',
      rate: 40,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 50,
      maxVUs: 150,
    },
    create_orders: {
      executor: 'constant-arrival-rate',
      exec: 'createOrder',
      rate: 10,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 20,
      maxVUs: 80,
    },
  },
  thresholds: {
    'http_req_failed{operation:readOrders}': ['rate<0.005'],
    'http_req_duration{operation:readOrders}': [
      'p(95)<250', 'p(99)<500'
    ],
    'http_req_failed{operation:createOrder}': ['rate<0.01'],
    'http_req_duration{operation:createOrder}': ['p(95)<600'],
    checks: ['rate>0.99'],
    dropped_iterations: ['count==0'],
  },
};

const baseUrl = __ENV.BASE_URL;
const runId = __ENV.RUN_ID;
const customerId = __ENV.CUSTOMER_ID || 'C-101';

export function setup() {
  if (!baseUrl || !runId) {
    throw new Error('BASE_URL and unique RUN_ID are required');
  }
}

function requestHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  if (__ENV.TEST_TOKEN) {
    headers.Authorization = 'Bearer ' + __ENV.TEST_TOKEN;
  }
  return headers;
}

function isExpectedReadResponse(response) {
  if (response.status !== 200) return false;
  try {
    const body = response.json();
    return body.customerId === customerId
      && Array.isArray(body.orders)
      && body.orders.length <= 20;
  } catch (_error) {
    return false;
  }
}

export function readOrders() {
  const url = baseUrl + '/v1/customers/'
    + encodeURIComponent(customerId) + '/orders?limit=20';
  const response = http.get(url, {
    headers: requestHeaders(),
    tags: { operation: 'readOrders' },
  });
  check(response, {
    'read status=200 and valid page': isExpectedReadResponse,
  });
}

export function createOrder() {
  // iterationInTest is the zero-based iteration index in the scenario.
  // Use a unique RUN_ID per test run to avoid reusing business IDs.
  const orderId = 'O-K6-' + runId + '-'
    + exec.scenario.iterationInTest;
  const payload = {
    orderId,
    customerId,
    totalCents: 150000,
  };
  const response = http.post(
    baseUrl + '/v1/orders',
    JSON.stringify(payload),
    {
      headers: requestHeaders(),
      tags: { operation: 'createOrder' },
    }
  );
  check(response, {
    'create status=201': (r) => r.status === 201,
  });
}
~~~

**Running from a machine with k6 and staging load-test authorization** (illustrative only, not a real measured run):

~~~bash
# Use a lab/staging token only; never commit secrets into the repository.
export BASE_URL='https://staging-graph.example.org'
export RUN_ID='lab-run-001'
export CUSTOMER_ID='C-101'

k6 run --summary-export=graph-load-summary.json graph-load.js
~~~

Key details to understand:

- `constant-arrival-rate` schedules **iterations started per second**; k6 allocates VUs up to `maxVUs` to sustain arrival when responses slow down.
- Each iteration here sends **one HTTP request**; if you add extra requests inside a function, `iterations/s` no longer equals `requests/s`.
- `preAllocatedVUs` and `maxVUs` **cap generator capacity**. If insufficient, `dropped_iterations` rises—treat that as a FAIL/INCONCLUSIVE condition to investigate rather than silently reporting latency of completed iterations.
- `checks` verify **contract payloads**, whereas `http_req_failed` tracks HTTP failure status codes. A `200` returning the wrong customer passes HTTP status checks yet **fails `checks`**.
- `{operation:...}` threshold filters work via per-request `tags`. Never put per-request business IDs in metric tags (high-cardinality explosion).
- `http_req_duration` measures sending + waiting + receiving, **excluding initial DNS/connect/TLS**. Inspect `http_req_blocked`, `http_req_connecting`, `http_req_tls_handshaking`, and server-side timings for full end-to-end breakdown.
- `RUN_ID` must be **unique per run**; reusing an ID accidentally benchmarks `MERGE` replays instead of new writes.
- `setup()` validates inputs but **does not seed the Customer**. Seed `C-101` in staging beforehand and verify database and permissions.

> **Key takeaway:** Never assume 50 req/s was achieved merely because `rate` totaled 50. Verify `http_reqs`, `iterations`, `dropped_iterations`, active VUs, and errors. If the generator hits 100% CPU, results reflect generator starvation rather than Neo4j limits.

### 10.1. Keeping WRITE Measurements Meaningful

The script above creates **one new Order per WRITE iteration**. Over 5 minutes at 10 WRITE/s, ideally ~3,000 new Orders are written if zero iterations drop and all succeed. Use this as an **expected sanity check**, not a substitute for actual reconciliation.

Reconcile afterward using a **dedicated test label/dataset** or defined ID prefix. Staging Neo4j verification example:

~~~cypher
MATCH (o:Order)
WHERE o.orderId STARTS WITH $runOrderPrefix
RETURN count(o) AS createdOrders;
~~~

Pass `$runOrderPrefix` = `O-K6-lab-run-001-`. Ensure `orderId` cannot be spoofed in production and this prefix scan does not run during peak hours; on large datasets, track a separate test ID list or an indexed `testRunId` property.

With k6 sending HTTP alone, **HTTP 201 responses** still do not prove Neo4j holds all intended relationships. Verify `PLACED` edge counts, absence of duplicates, and valid post-load state.

## 11. Five Load Test Types and Execution Order

| Type | Goal | Typical execution | What to capture |
| --- | --- | --- | --- |
| **Baseline** | Reference point under light load | 1–5 req/s, steady mix | Latency, CPU, DB Hits, index state |
| **Load** | Prove operational targets | e.g., 50 req/s mixed for 5–15 min | p95/p99, errors, throughput, saturation |
| **Stress** | Find breaking point under rising load | Stepped ramp with monitoring, stop on guardrail | First failing step, saturation behavior |
| **Spike** | Observe response to sudden bursts | Step-change arrival for a bounded window | Queueing, pool pending, recovery |
| **Soak** | Catch leaks/accumulation over time | Steady load for 30–60 min or per risk | Heap trend, disk/log growth, timeouts over time |

### 11.1. Stress Testing vs. Breaking the System Recklessly

**Stress testing does not mean “push until the machine crashes.”** Define:

- Stop thresholds: e.g., error rate > 5% across 3 windows, p99 exceeding timeout, free disk dropping below safety floor.
- Authority to abort the job and shed load for recovery.
- Dedicated test accounts, tenants, and datasets.
- **Cleanup and checkpointing** for tens of thousands of newly created Orders.
- A table recording achieved arrival/throughput and resource state at **every load step**.

A service may accept more incoming requests while **completed throughput stops rising** as queues and p99 climb. That signals saturation, not healthy scaling.

### 11.2. Recovery Is Part of the Result

After ending a spike or stress test, keep observing:

- Does API error rate return to baseline?
- Does the Java Driver connection pool/pending queue drain?
- Do Neo4j heap/GC, page cache, and disk I/O stabilize?
- Are there lingering transactions, constraint violations, or event backlogs needing replay?
- Does the graph still hold **exact expected nodes/relationships** after retries?

**Time to recover** is a critical metric; never stop collecting telemetry the instant k6 exits.

## 12. Instrumenting Observability to Explain Load Results

A credible benchmark correlates **timestamped data** across all layers:

~~~mermaid
flowchart TB
    K["k6 generator<br/>RPS, latency, errors, dropped"] --> A["Spring API<br/>HTTP, threads, connection pool, GC"]
    A --> D[("Neo4j<br/>Bolt, tx, queries, page cache, disk")]
    K -.-> M["Metrics / dashboard / report"]
    A -.-> M
    D -.-> M
    H["Host/container<br/>CPU, memory, I/O, network"] -.-> M
~~~

### 12.1. Minimum Metrics per Layer

| Layer | Metrics to record | Helps distinguish |
| --- | --- | --- |
| **k6** | `http_reqs`, `http_req_duration` p50/p95/p99, `http_req_failed`, `checks`, `dropped_iterations` | Did SUT sustain rate? Were payloads valid? |
| **Spring API** | HTTP latency per operation, errors, threads/queues, JVM heap/GC, CPU | Overhead before/after Neo4j queries |
| **Neo4j Java Driver** | Connection acquisition/pool pending, retries, timeouts, routing/handshakes | Client-side vs. server-side waiting |
| **Neo4j database** | Transactions, Bolt connections, active/blocked txs, index state, query log | Locks, I/O, or schema issues |
| **Neo4j process** | Heap, GC pauses, page cache hits/misses, CPU, disk reads/writes | Saturation, cache pressure, I/O |
| **Host/container** | CPU throttling, OOMs, disk free/latency, network RTT | Infrastructure bottlenecks |
| **CDC/outbox (if any)** | Lag, event age, replay errors, DLQ, `sourceVersion` | Does the graph converge fast enough after WRITE? |

Specific metrics vary across Neo4j versions and editions. On **self-managed Neo4j Enterprise**, inspect JMX/Prometheus exporters and Neo4j Ops Manager per supported version; **Aura** exposes plan-specific dashboards/APIs. On the Java side, driver pool metrics depend on Micrometer/tracing setup; never assume a specific metric name is enabled out of the box.

### 12.2. Common Bottleneck Signatures

| Observation | Top hypothesis | Verification |
| --- | --- | --- |
| p99 rises, Neo4j CPU low, app pool pending rises | Connection pool or network/routing | Pool acquisition time, active/idle counts, TLS/network |
| p99 rises, DB Hits/Rows jump sharply | Cypher plan or data fan-out | `PROFILE`, high-degree params, schema |
| READs slow as WRITEs climb, high tx wait | Lock/contention on hot nodes | `SHOW TRANSACTIONS`, query mix, batch sizes |
| Heap/GC climbs steadily during soak without dropping | Retained objects/Results/graph projections | Memory telemetry, heap dump analysis, query lifecycle |
| Disk I/O spikes, page cache misses rise | Working set exceeds page cache or competing imports | Page cache stats, disk latency, dataset size |
| `dropped_iterations` rises while server is idle | Generator starved for VUs/CPU or bad arrival config | k6 host metrics, `preAllocatedVUs`/`maxVUs`, network |
| WRITE returns 201 yet graph projection misses new Orders | Outbox/CDC lag or misleading async response | Source commit log, consumer apply rate, watermark |

**Never conclude from a single metric.** One slow request combines DNS, HTTP queueing, Java serialization, pool wait, Bolt round-trips, Cypher execution, and response transfer. Correlate trace/correlation IDs and timestamps during analysis.

### 12.3. Tracing and Transaction Metadata

When Java Driver supports `TransactionConfig`, attach **non-sensitive** metadata to transactions:

~~~java
import java.time.Duration;
import java.util.Map;
import org.neo4j.driver.TransactionConfig;

var cfg = TransactionConfig.builder()
        .withTimeout(Duration.ofSeconds(5))
        .withMetadata(Map.of(
                "operation", "listCustomerOrders",
                "testRunId", "lab-run-001"))
        .build();

// Assumes session is an open Session on the target database.
var rows = session.executeRead(tx -> tx.run("""
    MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
    RETURN o.orderId AS orderId
    ORDER BY o.orderId
    LIMIT 20
    """, Map.of("id", "C-101")).list(), cfg);
~~~

This is a **code fragment** requiring an open `session`. Metadata appears in query logs and `SHOW TRANSACTIONS` depending on privileges and config. Never attach emails, tokens, card numbers, or sensitive business IDs to tracing tags. Avoid high-cardinality `testRunId` tags on long-lived metrics across many runs; keep them in bounded-retention logs/traces.

## 13. EXPLAIN/PROFILE: Proving Root Cause in Cypher

Consider the query serving `GET /v1/customers/{id}/orders?limit=20`:

~~~cypher
MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId,
       o.status AS status,
       o.totalCents AS totalCents
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT 20;
~~~

To inspect the plan **without executing**:

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId,
       o.status AS status,
       o.totalCents AS totalCents
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT 20;
~~~

To measure Rows/DB Hits, **run only on safe READ queries in lab/approved conditions**:

~~~cypher
PROFILE
MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId,
       o.status AS status,
       o.totalCents AS totalCents
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT 20;
~~~

**`EXPLAIN` only plans; `PROFILE` actually runs the query with instrumentation overhead.** `PROFILE` on `CREATE`/`SET`/`DELETE` writes data—never run it in production just to view a plan.

### 13.1. Query Plan Evidence Checklist

| Operator / metric | Evidence provided | Investigation focus |
| --- | --- | --- |
| `NodeIndexSeek` / `NodeUniqueIndexSeek` | Uses index/constraint on `customerId`? | If absent, check predicates, index type, or param types |
| `NodeByLabelScan` | Scanning many nodes instead of seeking? | Check labels, indexes, and selectivity |
| `Expand(All)` | How many Orders expand per Customer? | High-degree skew, fan-out, traversal bounds |
| `Sort` / `Top` | Sorting thousands of Orders before `LIMIT`? | Adjust query shape if semantics permit |
| `Rows` | Intermediate row counts per operator? | N+1, Cartesian/aggregation inflation, filter placement |
| `DB Hits` | Storage-layer access work? | Compare against baseline and alternative queries |
| Page cache hits/misses | Hitting disk outside page cache? | Warm/cold cache state, comparable dataset |
| Memory / timing | Which operator dominates cost? | Joins/ordering, sorts, wide projections |

Operator names and columns can vary across Neo4j/Cypher versions. **Identical plan text across versions is not required**; gates depend on correctness, latency, and cost.

### 13.2. Schema Verification Queries

~~~cypher
SHOW INDEXES
YIELD name, type, state, populationPercent, labelsOrTypes, properties
RETURN name, type, state, populationPercent, labelsOrTypes, properties
ORDER BY name;
~~~

~~~cypher
SHOW CONSTRAINTS;
~~~

Indexes in `POPULATING` or `FAILED` state cannot be used by the planner like `ONLINE` indexes. Always record **index state at measurement time** in your dossier, rather than merely claiming “index created.”

### 13.3. Trap: LIMIT Does Not Guarantee Only 20 Rows Are Touched

Suppose Customer `C-HOT` has 70,000 Orders:

~~~cypher
MATCH (c:Customer {customerId: 'C-HOT'})-[:PLACED]->(o:Order)
RETURN o.orderId
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

The planner may still expand and sort tens of thousands of Orders before picking 20. To cut cost, redesign the **data/access path for the query pattern** (e.g., keyset pagination, materialized summaries, or indexed properties on appropriate nodes) while **preserving the exact business contract**.

Never replace “20 newest Orders” with “20 arbitrary Orders” just to celebrate lower p95.

## 14. Designing Fair Before–After Comparison Experiments

**Good experiments control variables**—never run once before and once after across two different environments and claim an optimization win.

### 14.1. Variables to Hold Constant or Disclose

| Variable | Why it matters |
| --- | --- |
| **Neo4j version, edition, runtime, store format** | Planner, operators, and index providers evolve across releases |
| **Java Driver, Spring Boot/SDN, JDK** | Query generation, pooling, retries, JIT, serialization |
| **CPU, RAM, heap, page cache, disk** | Directly governs saturation and I/O limits |
| **Dataset counts and skew** | High-degree nodes drive traversal cost and p99 |
| **Constraints/indexes + state** | `ONLINE` status and selectivity alter execution plans |
| **Network / generator placement** | RTT, TLS overhead, generator CPU, and dropped iterations |
| **READ/WRITE workload ratio** | Writes add locks/index I/O; reads consume CPU/cache |
| **Warm-up / cold-cache state** | First-query compilation and cold cache differ from steady state |
| **Concurrency / arrival rate** | Alters queueing and saturation behavior |
| **Background jobs** | Backups, imports, GDS, or CDC compete for resources |

Whenever a variable cannot be held fixed, document **the discrepancy and interpretation risk** in the dossier.

### 14.2. Illustrative A/B Workflow

~~~text
1) Prepare dataset snapshot D1 with indexes ONLINE.
2) Run warm-up under an identical profile.
3) Run A (baseline query/index) at 10, 30, 50 req/s.
4) Capture metrics, query plans, timestamps, CPU/GC/disk.
5) Reset the graph to snapshot D1 or equivalent state.
6) Run B (tuned Cypher/index) at the exact same load levels.
7) Repeat runs to observe variance; alternate A/B order when practical.
8) Compare correctness, p95/p99, throughput, errors, DB Hits/Rows.
9) Check for regressions on WRITEs and unrelated endpoints.
10) Decide whether to keep B, iterate further, or roll back to A.
~~~

**Running A strictly before B can give B a cache/JIT advantage.** Use warm-ups and repeated trials where possible to limit bias; a single run cannot prove a 5% difference is real.

### 14.3. Comparing Across Database Versions

When upgrading Neo4j 5 to 2025/2026 while also changing Cypher versions, indexes, or store formats:

1. Compare **old vs. new binaries** with identical queries and equivalent indexes first.
2. Then test the **new store format** if your edition supports it.
3. Finally compare **Cypher 5 vs. Cypher 25** on supported versions.

Never bundle every change into one measurement; if p99 regresses, you will not know which change caused it.

## 15. SLIs, SLOs, and Acceptance Thresholds for the Capstone

### 15.1. Metric Definitions

- **Latency:** p50 captures median; p95/p99 capture tail latency. Specify separately per READ/WRITE operation.
- **Throughput:** requests/transactions **completed successfully** per second, not merely attempted.
- **Error rate:** rate of HTTP failures, timeouts, failed transactions, and failed assertions; report categories separately.
- **Availability SLI:** valid requests meeting success criteria / total valid requests in the measurement window.
- **Freshness:** when Neo4j is a projection, lag from source commit until the graph reflects that version.
- **Saturation:** the load point where rising arrival no longer increases throughput while p99, errors, and queues climb.

Example:

\[
\mathrm{SLI_{success}}=\frac{\text{valid requests completed accurately and on time}}{\text{total valid requests}}
\]

`HTTP 200` returning the wrong customer or missing Orders **does not count as a business success**. Conversely, rejecting malformed client inputs per contract can be tracked separately rather than misclassified as a service failure.

### 15.2. Illustrative SLOs and Failure Gates

| Operation | Illustrative SLO | Failure gate |
| --- | --- | --- |
| `GET Customer Orders` | p95 < 250 ms, p99 < 500 ms | Breached at 40 READ/s workload |
| `POST Create Order` | p95 < 600 ms, error < 1% | Breached at 10 WRITE/s workload |
| API correctness | 100% critical domain assertions | Wrong relationship, tenant leak, or bad business ID |
| Dropped iterations | 0 at target arrival rate | Load generator fails to sustain target rate |
| Transaction integrity | Zero duplicates per `orderId` | Duplicate writes after retries |
| Projection freshness (with CDC) | 99% of events visible within 10 s | Backlog or freshness breaches target |

**All numbers above are educational examples.** Do not pick 250 ms merely because it appears in this script; set SLOs from application needs, realistic traffic, and hardware budget with business-owner approval.

### 15.3. Common Percentile Mistakes

- **A 100 ms mean does not prove a healthy p99.** A handful of 10-second outliers can still trigger timeouts and outages.
- **p99 over 20 requests** is statistically unreliable for tail behavior; collect adequate samples and repeated runs.
- **You cannot average per-minute percentiles to compute the whole-test p95.** Aggregate raw distributions/histograms or use your load tool's global summary.
- **Dropped iterations lack request latencies for p99.** Always report `dropped_iterations` and achieved throughput alongside latency.
- If driver retries mask transient errors, HTTP 200 may hide rising latency; record **retry rates** and end-to-end user latency.

## 16. Performance Dossier: Structure of a Verifiable Report

A *performance dossier* enables another engineer to **reproduce your measurements** and make a release call. It is far more than a Grafana screenshot.

### 16.1. Report Template

~~~text
PERFORMANCE DOSSIER — Graph Commerce
Report ID / timestamp UTC:
Owner / reviewer:
Application Git commit / tag:
Neo4j version / edition / deployment:
Java version / Driver / SDN version:
API deployment config / pod replicas:
Neo4j CPU / RAM / heap / page cache / disk:
Driver pool / tx timeout / retry config:
Graph dataset ID + seed + checksum:
Node counts / relationship counts / high-degree distribution:
Index / constraint list + state:
Load generator version / host / CPU / network:
Endpoints and operation mix:
Auth / test data policy (no secrets in report):
Warm-up / steady / stress / recovery windows:
Arrival targets and achieved RPS:
Errors + failed correctness checks:
Dropped iterations:
Latency p50 / p95 / p99 by operation:
Resource bottleneck evidence:
EXPLAIN/PROFILE snapshots:
Comparison with accepted baseline:
Assumptions, invalid runs, confounders:
Business correctness verification after load:
Decision: PASS / FAIL / INCONCLUSIVE
Follow-ups + owners + rerun conditions:
~~~

Report **PASS** when both correctness and load thresholds pass under valid experimental conditions; **FAIL** when any gate fails; **INCONCLUSIVE** when samples are insufficient, the generator saturated, or variables/data were uncontrolled. Never force an invalid run to PASS.

### 16.2. Illustrative Summary Table (Not Measured Results)

| Scenario | Target RPS | Achieved RPS | READ p95/p99 | WRITE p95 | Errors | Dropped | Conclusion |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| Baseline | 10 | 10 | 58 / 95 ms | 110 ms | 0.00% | 0 | PASS |
| Load A | 50 | 49.8 | 230 / 420 ms | 520 ms | 0.30% | 0 | PASS per sample SLO |
| Stress B | 100 | 83 | 710 / 1,900 ms | 1,400 ms | 7.20% | 1,050 | FAIL; past saturation point |
| Optimized A | 50 | 49.9 | 135 / 290 ms | 530 ms | 0.20% | 0 | PASS, verify correctness |

All figures are **hypothetical**, illustrating how to inspect results holistically:

- `Achieved RPS` can fall below target due to dropped iterations, failures, or generator limits.
- “Optimized A” cuts READ latency while WRITE ticks up slightly from 520 to 530 ms; confirm writes remain within SLO without excessive resource growth.
- Stress B reveals **the limit under that specific configuration**, not a universal claim that Neo4j tops out at 83 RPS.

### 16.3. Query Plan Dossier

| Query ID | Param category | Plan before | Plan after | DB Hits before/after | p95 before/after | Conclusion |
| --- | --- | --- | --- | --- | --- | --- |
| Q-READ-01 | Low-degree Customer | Index seek + expand | Index seek + expand | 85 / 82 | 40 / 38 ms | Negligible change |
| Q-READ-02 | Customer with 10,000 Orders | Expand + Sort | Better Filter/Top | 40,000 / 9,500 | 340 / 125 ms | Improved in lab |
| Q-WRITE-01 | New Order | MERGE + constraint | MERGE + constraint | 600 / 615 | 510 / 530 ms | Slight rise, within SLO |

These figures/plans **illustrate dossier formatting**, not guaranteed plans for any given query. For each row, attach **query text, anonymized sample params, versions, index states, and raw plans** so reviewers can audit them.

## 17. Evidence-Driven Root-Cause Analysis and Optimization

Suppose after a load run, `GET Customer Orders` hits p99 = 1,400 ms while `POST Create Order` still passes. Investigate in order:

1. **Check the generator:** did dropped iterations climb or k6 CPU peg? If yes, fix generator capacity and re-run before blaming the DB.
2. **Check the app:** pool pending time, HTTP queues, serialization, and repository call counts. If app p99 is high while Neo4j queries are fast, focus on app/network.
3. **Check the query:** run `PROFILE` on a high-degree Customer; inspect Rows, DB Hits, Sorts, and whether index seeks fire.
4. **Check resources:** page cache misses, disk I/O, CPU, GC pauses, and concurrent background tasks.
5. **Propose one change:** add a truly useful index, reshape query/pagination, switch to DTOs, batch N+1 calls, or paginate.
6. **Run an A/B test on the same dataset and load**, verifying semantics stay intact and WRITEs do not regress.
7. **Record evidence in the dossier:** plans, metrics, and the keep/revert decision.

### 17.1. Avoiding Misplaced Optimizations

Query example:

~~~cypher
MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

To return the “20 most recent Orders” deterministically, define a tie-breaker and handle null `createdAt` cases. Updated form:

~~~cypher
MATCH (c:Customer {customerId: $id})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT 20;
~~~

Fixing ordering makes results **deterministic**, yet does not by itself shrink fan-out. Measure `Rows`/`DB Hits`; for Customers with tens of thousands of Orders, revisit the **access-pattern data model** rather than piling on redundant indexes.

### 17.2. When Should You Scale Out?

If a single query is expensive due to missing indexes or over-fetching, adding secondaries rarely **makes that single query cheap**. In a Neo4j Enterprise cluster, secondaries distribute independent READ traffic, boosting throughput when routing and CPU/RAM/disk are properly sized. **A standard database still has one writer at a time**, so adding primaries does not multiply WRITE throughput.

Measure before/after and document topology/failure domains instead of guessing from pod/container counts.

## 18. CI/CD: Which Quality Gates Belong Where?

### 18.1. Suggested Pipeline

~~~mermaid
flowchart LR
    PR["Pull request"] --> U["Unit tests"]
    U --> I["Testcontainers integration"]
    I --> C{"Correctness gate"}
    C -->|FAIL| X["Block merge"]
    C -->|PASS| B["Build artifact"]
    B --> S["Deploy staging"]
    S --> L["Authorized & quota-bounded load test"]
    L --> P["Raw metrics + dossier"]
    P --> G{"Performance go/no-go"}
    G -->|FAIL| R["Investigate / revert"]
    G -->|PASS| A["Release approval"]
~~~

Recommended tiering:

| Pipeline | Tests | Rationale |
| --- | --- | --- |
| **PR / merge request** | Unit + Testcontainers integration + schema/constraint checks | Fast feedback; catches correctness regressions |
| **Nightly** | Full API integration, edge-case datasets, concurrency, and CDC (if used) | Protects multi-component workflows |
| **Pre-release** | Staging load/stress close to prod scale, profiling, dossier | Drives SLO and go/no-go decisions |
| **Scheduled ops** | Soak tests, synthetic read/write probes, performance trend tracking | Catches long-term leaks and gradual regressions |

Running a 60-minute soak on every PR commit is usually **uneconomical**; conversely, never skip load testing before shipping a new traversal over a large graph.

### 18.2. Illustrative Commands

~~~bash
# Run inside an application repo configured with Testcontainers/JUnit.
# Never run these commands without confirming you are targeting a test environment.
./gradlew test

# On a staging runner with k6 installed and load testing authorized:
k6 run --summary-export=graph-load-summary.json graph-load.js
~~~

These commands are **examples for learners to implement in their own repos**. This lesson does not assume a Gradle Wrapper or `graph-load.js` already exists, nor does it claim tests have been run. Real CI integrations need artifact uploads, environment variables, runner permissions, and job timeouts.

### 18.3. What CI Gates Should Inspect

- **JUnit/test runner exit code** and skipped/failed counts; never pass a build if integration tests were skipped because Docker was missing.
- **k6 threshold exit code** and `dropped_iterations`; if k6 misses target arrival due to generator limits, mark the run **inconclusive/fail per policy**.
- **Performance report artifacts** storing environment, dataset ID, and timestamps—not just the last 30 lines of console logs.
- **Post-load correctness:** reconcile Order counts, `PLACED` edges, conflict/replay behavior, and zero data loss.
- **Baseline comparisons** using pre-declared regression thresholds rather than moving goalposts after seeing results.

**Never** let CI create/wipe a production database or fire stress traffic from public runners at customer-facing endpoints.

## 19. Failure and Recovery Testing (Capstone Extension)

A system passing happy-path load tests may still misbehave during faults.

| Scenario | Safe lab test | Expected result |
| --- | --- | --- |
| Neo4j container paused / restarted | Interrupt isolated test node, never prod | App surfaces clean error / bounded retry, then recovers |
| Driver drops connection near commit | Simulate network drop with lab proxy | No duplicate Orders; check business ID before replay |
| API receives duplicate create request | Send identical payload and idempotency key | Single Order, single `PLACED` relationship |
| Constraint violated | Attempt `CREATE` with duplicate business ID | Transaction fails; zero half-written graph state |
| Transaction exceeds timeout | Enforce tight lab timeout on slow query | Rolls back and releases resources cleanly |
| Index not yet `ONLINE` | Create index in lab with test data | Health/perf gate refuses false PASS |
| Source-of-truth / CDC lags | Pause simulated consumer | API/metrics surface staleness; backlog catches up cleanly |
| Unauthorized tenant request | Spoofed tenant/credentials test | Blocked from unauthorized subgraph |

### 19.1. Protecting Transactions Under Retries

Neo4j Driver can automatically retry managed transactions (`executeRead`/`executeWrite`) on recognized transient failures. Because callbacks can execute more than once:

- Rely on **business IDs / constraints** instead of generating fresh random IDs inside the callback on each retry.
- Never send emails, charge cards, or publish broker messages inside the callback without idempotency/outbox guards.
- On exceptions near commit, never assume “nothing was written”: **re-query the business key** and apply safe retry logic.
- Assert graph state **after** errors/retries, not just Java exception types.

**Lab caveat:** Exact disconnects right at commit can be hard to reproduce reliably; if clean fault injection is unavailable, document test boundaries and add a runbook/manual drill rather than reporting a fake PASS.

### 19.2. Never Use Chaos Tests to Wreck Production Clusters

Never stop two of three primaries “to test quorum” in production; never delete transaction logs or store files; never fill disks intentionally. If HA is in scope, build a **staging/test cluster** matching your edition and test primaries/secondaries, read/write routing, and failover per official runbooks.

## 20. Milestone-Based Capstone Implementation Roadmap

| Milestone | Tasks | Verifiable output |
| --- | --- | --- |
| **M1** | Lock use cases, invariants, API contract, and SLOs | Test matrix and acceptance thresholds |
| **M2** | Build schema/fixtures, pin versions, set up Testcontainers | IT-01 through IT-05 passing against real Neo4j |
| **M3** | Add API/security tests and data-skew cases | IT-06 through IT-09 with raw test logs |
| **M4** | Seed staging, instrument API/Neo4j, prepare load generator | Time-aligned dashboards, dataset card |
| **M5** | Run baseline/load/stress/spike/soak with guardrails | Raw k6 metrics, per-step observations |
| **M6** | `PROFILE` hot queries, tune with controlled A/B tests | Before–after Rows/DB Hits/p95/p99 |
| **M7** | Reconcile post-load state, write dossier, go/no-go review | Acceptance record and runbook |

### 20.1. Practical Execution Sequence

**Step 1 — Lock requirements:** Document graph schema, endpoints, test datasets, and read/write mixes. Define “order created successfully” and replay semantics.

**Step 2 — Build the integration suite:** Ensure containers boot real Neo4j with schema, seeds, and cleanup. Assert graph state via Cypher after service/API calls; verify rollbacks and conflicts before running load.

**Step 3 — Standardize the dataset:** Fix dataset ID, random seed, Customer/Order/Product counts, fan-out, and skew ratios. Document bootstrap/checksum steps and verify all indexes are `ONLINE`.

**Step 4 — Capture baseline:** Record environment, commit, query plans, CPU/heap/page cache, and response times under light load. If correctness fails, **stop here**—never run load over broken logic.

**Step 5 — Run target load:** Configure k6 arrival rates and thresholds. Record both achieved throughput and dropped iterations; verify the load generator is never saturated.

**Step 6 — Diagnose:** For failing operations, run `PROFILE` on representative datasets/params, inspecting Rows/DB Hits, lock waits, pools, and host resources. Form a hypothesis and make one reasoned change.

**Step 7 — Re-measure:** Reset to identical dataset state, run A/B checks, and watch for regressions on other endpoints; never change multiple variables at once.

**Step 8 — Submit dossier:** State PASS/FAIL/INCONCLUSIVE, experimental limits, root causes, and next steps; attach artifacts per team conventions.

## 21. Suggested Capstone Grading Rubric (100 Points)

| Criterion | Points | Full credit requires |
| --- | ---: | --- |
| Domain invariants & test matrix | 15 | Covers happy paths, conflicts, edge cases, tenant/error cases |
| Real Neo4j integration tests | 25 | Testcontainers, constraints, edges, rollbacks, idempotency; reproducible setup |
| API integration & security | 10 | Asserts HTTP **and** final graph state |
| Dataset & workload realism | 15 | Skewed data, READ/WRITE mix, open/closed models, unthrottled generator |
| Metrics & query profiling | 15 | k6 + app + Neo4j metrics; `EXPLAIN/PROFILE` with DB Hits/Rows |
| Performance dossier & A/B | 15 | Raw results, test conditions, thresholds, comparisons, analysis, verdict |
| Operational safety, CI, reproducibility | 5 | Zero prod risk, cleanup/runbooks/owners |
| **Total** | **100** | **Correctness is a mandatory gate for acceptance** |

**Blocking rule:** Regardless of total score, if testing leaks cross-tenant data, duplicates orders on retries, or wipes non-lab data, the capstone must be **fixed before release**.

## 22. Common Mistakes When Testing Neo4j

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Mocking repositories only | Leaves Cypher, constraints, real transactions untested | Testcontainers + real Neo4j |
| Skipping cleanup or seeding | Test outcomes depend on prior test order | Deterministic dataset, isolated DB |
| Running `DETACH DELETE` against prod | Graph wiped | Check namespaces/containers and credentials |
| Benchmarking 100 tiny Customers | Misses fan-out on high-degree nodes | Seed realistic degree skew |
| Reporting only average latency | Hides timeouts, p99 spikes, poor UX | Track p95/p99 + errors + dropped |
| Calling constant VUs “fixed 100 req/s” | Arrival drops whenever SUT slows down | Pick right executor; report achieved RPS |
| Ignoring generator CPU | Mistakes k6 bottleneck for Neo4j | Monitor k6 host and dropped iterations |
| Treating HTTP 200 as correctness | API may return wrong edges or tenants | Payload checks + graph reconciliation |
| Reusing `orderId` across all WRITEs | Measures idempotent MERGE instead of new inserts | Unique `RUN_ID`, separate replay test |
| Benchmarking while indexes are `POPULATING` | Unstable plans and I/O interference | Wait for `ONLINE` or state test goal |
| Running `PROFILE` on WRITEs in prod | Mutates live data unexpectedly | Profile WRITEs only in controlled lab transactions |
| Adding indexes without measuring | Increases disk usage and write cost | Compare plans/DB Hits and write regressions |
| Changing data between A and B | Results become incomparable | Identical snapshot/seed version |
| k6 PASS while Neo4j lacks Orders | False HTTP success or async lag | Post-load correctness reconciliation |
| Discarding raw reports | Impossible to reproduce or audit | Archive scripts, datasets, configs, raw metrics |

## 23. Final Acceptance Checklist

- [ ] Every API has explicit **input/output contracts and domain invariants**.
- [ ] Compatible versions of Neo4j, Java Driver, Spring Boot/SDN, and Testcontainers are pinned.
- [ ] Integration tests run against **real Neo4j** in an **isolated** database/container, never mocks alone.
- [ ] Uniqueness constraints are active; tests assert nodes, relationships, directions, and properties.
- [ ] Tested replays, payload conflicts, rollbacks, concurrent writes, and invalid inputs.
- [ ] Security/multi-tenant tests verify unauthorized reads/writes are blocked.
- [ ] Seed data includes **high-degree nodes, nulls, Unicode, varied item counts**, and fixed random seeds.
- [ ] API tests assert **business payloads** and post-commit graph state.
- [ ] Load scripts specify workload mix, arrival model, duration, `RUN_ID`, thresholds, and guardrails.
- [ ] Baseline, load, stress/spike, and soak runs executed safely without touching production.
- [ ] Reported **target/achieved RPS, p50/p95/p99, errors, checks, and dropped iterations**.
- [ ] Aligned API, Driver, Neo4j, and OS/container metrics along one timeline to locate bottlenecks.
- [ ] Critical indexes verified `ONLINE`; `EXPLAIN/PROFILE` captured for hot queries.
- [ ] Distinguished `Rows`, `DB Hits`, pool waits, cache misses, and app/network time.
- [ ] A/B comparisons used identical datasets/workloads without changing multiple variables at once.
- [ ] Post-load reconciliation confirmed **Order/PLACED/CONTAINS** integrity with zero duplicates or data loss.
- [ ] If using CDC/outbox, verified freshness, backlog drain, idempotency, and delayed events.
- [ ] CI enforces quality gates, exit codes, and artifacts; skipped tests never count as passes.
- [ ] Performance dossier documents environment, git commit, configs, dataset, limitations, and verdict.
- [ ] Stated PASS/FAIL/INCONCLUSIVE against SLOs and correctness, with owners and improvement plans.
- [ ] Cleanup/restore runbooks exist, and fault injection runs strictly in authorized labs.

## References

- [Neo4j Java Driver — Transactions, retries, and session lifecycle](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver — Connect to the database](https://neo4j.com/docs/java-manual/current/connect/)
- [Spring Data Neo4j — Testing with Spring Boot](https://docs.spring.io/spring-data/neo4j/reference/testing/testing-with-spring-boot.html)
- [Spring Boot — Testcontainers and DynamicPropertySource/ServiceConnection](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Testcontainers — Neo4j module](https://java.testcontainers.org/modules/databases/neo4j/)
- [Neo4j Cypher — Understanding query execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j Cypher — Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/)
- [Neo4j Cypher — Constraints](https://neo4j.com/docs/cypher-manual/current/constraints/)
- [Neo4j Operations — Monitoring and metrics](https://neo4j.com/docs/operations-manual/current/monitoring/)
- [Grafana k6 — Scenarios and executors](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/)
- [Grafana k6 — Constant arrival rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/)
- [Grafana k6 — Metrics reference](https://grafana.com/docs/k6/latest/using-k6/metrics/reference/)
- [Grafana k6 — Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/)

**Conclusion:** The final stage of a Neo4j capstone is about far more than adding a few tests and capturing one latency chart. A quality dossier must **test the real property graph**, verify transactions, constraints, and relationships, reproduce workloads on realistically skewed datasets, measure p95/p99 and errors under load, and diagnose behavior using **EXPLAIN/PROFILE, indexes, DB Hits, Rows, and resource metrics**. Only when correctness, reliability, performance, and operational safety are all backed by evidence does a team have a solid basis for a **go/no-go** release decision rather than trusting a happy-path demo.
