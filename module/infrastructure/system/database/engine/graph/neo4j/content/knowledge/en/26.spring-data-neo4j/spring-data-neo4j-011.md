# Integration Testing and Verifying Actual Cypher Executed by the Application

A **Spring Data Neo4j (SDN)** repository method may be only a single line of Java, yet at runtime it can generate a Cypher query with multiple `MATCH`, `WHERE`, `WITH`, `RETURN`, or relationship-loading clauses. A unit test that merely mocks the repository proves the service **invoked the expected method**, but cannot verify whether **the Cypher executes cleanly on real Neo4j**, returns the right number of nodes/relationships, maps properly to Java objects, or triggers unintended writes.

This lesson belongs to the **Spring Data Neo4j** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. In a Neo4j property graph system, applications query nodes and relationships, filter, aggregate, leverage indexes/constraints, and manage transactions. Effective integration testing must therefore validate **both business outcomes and actual graph state**, and then inspect the **actual Cypher sent by SDN/the driver to Neo4j**. It also shows how to use application logs, server query logs, and `EXPLAIN`/`PROFILE` to investigate slow or row-multiplying queries.

> **Version scope:** The primary Java examples target **Spring Boot 3.5 / Spring Data Neo4j 7.5**, Java 17+, JUnit 5, Testcontainers, and Neo4j 5.x. Spring Boot 4 / SDN 8 reorganizes packages and test modules; review the compatibility section before copying code into your project. Always match dependency versions to your Spring Boot BOM.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish unit tests, repository slice tests, and full integration tests through services/APIs.
2. Combine `@DataNeo4jTest` with **Neo4j Testcontainers** to run real queries locally and in CI.
3. Seed deterministic graph fixtures, invoke repositories, and cross-check results with independent Cypher.
4. Test **derived queries** from method names, explicit `@Query` queries, and variations in relationship loading.
5. Inspect the **actual Cypher and parameters** on the application or server side instead of guessing from method names.
6. Feed observed Cypher into `EXPLAIN`/`PROFILE` to diagnose cardinality, index, and sorting issues.
7. Keep tests isolated from transaction rollback surprises, caching, pre-existing data, and environment drift.

## 2. Three Testing Tiers to Distinguish

| Tier | Real components | Runs Cypher on Neo4j? | Best at catching |
|---|---|---|---|
| **Service unit test** | Service, mocked repositories | **No** | Business rules, exception handling, method call contracts |
| **Repository slice test** | `@DataNeo4jTest`, SDN mapping, repositories, real Neo4j | **Yes** when wired to a real instance | Derived queries, `@Query`, mappings, save/load, transactions |
| **Full integration test** | `@SpringBootTest`, services, controllers, real DB | **Yes** | Multi-bean wiring, service transactions, response mapping, security/config |

`@DataNeo4jTest` is a **test slice**: Spring initializes only Neo4j infrastructure and related components per slice rules; it does not automatically load all `@Service`, `@Controller`, or full application configuration beans. When testing a REST endpoint or real service transaction boundaries, use `@SpringBootTest` or explicitly import the required components.

**Key point:** `@DataNeo4jTest` **does not start an embedded Neo4j database automatically**. You must provide a real Neo4j instance, such as Testcontainers or Neo4j Test Harness. Adding the annotation while mocking the driver still does not test Cypher execution.

~~~mermaid
flowchart TD
    U["Unit test + mock repository"] --> R["Verify service logic"]
    S["@DataNeo4jTest + Neo4j container"] --> C["Repository / SDN mapping"]
    C --> D["Real Neo4j Bolt / Cypher"]
    F["@SpringBootTest + Neo4j container"] --> A["API / Service / Transaction"]
    A --> C
    D --> V["Verify nodes, relationships, results"]
    D --> L["Observe executed query, EXPLAIN / PROFILE"]
~~~

## 3. Setting Up a Test Project with Real Neo4j

### 3.1. Gradle Dependencies

Example for **Spring Boot 3.5**, using `spring-boot-starter-data-neo4j` and BOM-managed test libraries:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-neo4j'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:neo4j'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Your project may already declare the Neo4j starter and BOM; if so, add only the missing test dependencies. **Never mix arbitrary standalone versions** of Spring Data Neo4j, Neo4j Java Driver, and Spring Boot BOM. In CI, Testcontainers requires a working container runtime (Docker or compatible).

### 3.2. Pick a Test Version Close to Production

If production runs Neo4j 5.26, tests should target the same Neo4j line and matching Cypher/schema settings rather than picking a random newer release:

~~~java
@Container
@ServiceConnection
static Neo4jContainer<?> neo4j = new Neo4jContainer<>("neo4j:5.26");
~~~

`@ServiceConnection` supplies the container's connection details to Spring Boot, including URI and credentials, overriding static application connection properties. Testing against other versions is useful, but it should be an **intentional** compatibility check.

With JUnit `@Testcontainers` and a `static @Container` field, the container lifecycle is tied to the test class. If multiple test classes share a cached Spring `ApplicationContext`, the container may stop while the context is still reused. For **large test suites**, consider declaring the container as a **Spring test bean** so its lifecycle matches the context, or design controlled lifecycle sharing. The minimal example below covers **a single test class**.

## 4. Java Data Model for Testing

Suppose an application manages books by `isbn`, `title`, and `price`. We want a repository method to find books at or above a price threshold, sorted by ascending price.

**Entity:**

~~~java
package example.catalog;

import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("CatalogBook")
public class CatalogBook {
    @Id
    private String isbn;
    private String title;
    private long price;

    protected CatalogBook() {
    }

    public CatalogBook(String isbn, String title, long price) {
        this.isbn = isbn;
        this.title = title;
        this.price = price;
    }

    public String getIsbn() { return isbn; }
    public String getTitle() { return title; }
    public long getPrice() { return price; }
}
~~~

`@Node` maps the Java class to the `CatalogBook` label. `@Id` designates the entity key; `@GeneratedValue` is omitted because `isbn` is assigned by the business domain in this example. In real systems, add a **uniqueness constraint** in Neo4j on `isbn`; the entity annotation **does not replace** a database constraint.

**Repository:**

~~~java
package example.catalog;

import java.util.List;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface CatalogBookRepository
        extends Neo4jRepository<CatalogBook, String> {

    List<CatalogBook> findByPriceGreaterThanEqualOrderByPriceAsc(long minPrice);
}
~~~

`findByPriceGreaterThanEqualOrderByPriceAsc` is **parsed by SDN** to generate a query. You cannot tell the exact clauses and aliases of the final Cypher solely from the Java signature; SDN factors in entity metadata, library version, and parameters. The test verifies **semantics** first, and then we inspect the exact Cypher emitted.

## 5. Integration Test with `@DataNeo4jTest` + Testcontainers

Here is a **complete illustrative test class targeting Spring Boot 3.5**. It seeds data via `Neo4jClient` inside the test transaction, invokes the repository, and verifies both source graph state and returned results:

~~~java
package example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.testcontainers.containers.Neo4jContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@DataNeo4jTest
class CatalogBookRepositoryIT {
    @Container
    @ServiceConnection
    static Neo4jContainer<?> neo4j =
            new Neo4jContainer<>("neo4j:5.26");

    @Autowired
    CatalogBookRepository repository;

    @Autowired
    Neo4jClient client;

    @BeforeEach
    void seedGraph() {
        client.query("""
                UNWIND $books AS row
                CREATE (:CatalogBook {
                    isbn: row.isbn,
                    title: row.title,
                    price: row.price
                })
                """)
                .bindAll(Map.of("books", List.of(
                        Map.of("isbn", "B01", "title", "Graph Basics",
                               "price", 120_000L),
                        Map.of("isbn", "B02", "title", "Intro Cypher",
                               "price", 80_000L),
                        Map.of("isbn", "B03", "title", "Neo4j Patterns",
                               "price", 150_000L))))
                .run();
    }

    @Test
    void derivedQueryFiltersAndOrdersByPrice() {
        var actual =
                repository.findByPriceGreaterThanEqualOrderByPriceAsc(
                        100_000L);

        assertThat(actual)
                .extracting(CatalogBook::getIsbn)
                .containsExactly("B01", "B03");

        assertThat(actual)
                .extracting(CatalogBook::getPrice)
                .containsExactly(120_000L, 150_000L);

        var count = client.query("""
                MATCH (b:CatalogBook)
                RETURN count(b) AS total
                """)
                .fetchAs(Long.class)
                .one();
        assertThat(count).contains(3L);
    }
}
~~~

**What this test actually proves:**

1. Spring instantiates the repository and connects to Neo4j using container connection details.
2. Fixture setup creates **three nodes** with known prices and keys.
3. SDN translates the derived method into a Cypher query that executes on real Neo4j.
4. Results exclude `B02` (80,000) and return `B01` then `B03` in ascending price order.
5. Property mapping from real Neo4j nodes into `CatalogBook` populates accurate field values.

**What this test does not yet prove:** the exact generated Cypher text, DB hit count, whether indexes are used, behavior when multiple relationships match, production latency, or end-to-end service/API correctness.

### Why Seed Fixtures via `Neo4jClient`?

`Neo4jClient` is provided by Spring Data Neo4j to run Cypher directly within the same Spring transaction infrastructure. Seeding via Cypher establishes exact input graph state and lets you test the repository through an **independent path** separate from repository writes. If you only seed via `repository.save(...)` and read back via `repository.find...`, both paths can share a symmetric mapping bug that goes undetected.

In other tests, you should still test `repository.save` and `Neo4jTemplate`, but always clarify the **system under test** (save, load, or mapping) and verify underlying graph state independently.

## 6. Testing Hand-Written `@Query` Methods

Beyond derived methods, repositories can declare explicit Cypher:

~~~java
import java.util.List;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface CatalogBookRepository
        extends Neo4jRepository<CatalogBook, String> {

    List<CatalogBook> findByPriceGreaterThanEqualOrderByPriceAsc(long minPrice);

    @Query("""
        MATCH (b:CatalogBook)
        WHERE b.price >= $minPrice
        RETURN b
        ORDER BY b.price ASC, b.isbn ASC
        """)
    List<CatalogBook> findPremiumBooks(@Param("minPrice") long minPrice);
}
~~~

This is an **extended version** of the interface from Section 4: add `findPremiumBooks` to the same repository rather than creating a second interface with the same name.

Additional test:

~~~java
@Test
void customQueryUsesNamedParameter() {
    var actual = repository.findPremiumBooks(100_000L);

    assertThat(actual)
            .extracting(CatalogBook::getIsbn)
            .containsExactly("B01", "B03");
}
~~~

This verifies that `@Param("minPrice")` binds properly and the query executes cleanly on Neo4j. Still, **passing on three nodes** does not guarantee correctness on larger data: add test cases for price ties, null properties, invalid data, and one-to-many relationships as needed by the domain.

## 7. Testing Relationship Mappings, Row Counts, and Edge-Case Data

In a graph, a node can connect to many relationships. A `MATCH` expanding two independent branches can **multiply rows**. SDN must also assemble Cypher rows into object graphs; when a `@Query` omits variables, nodes, or relationships needed by the mapper, hydrated objects can miss relationships or load differently from expectations.

Suppose the model is:

~~~cypher
(:Customer {customerId: 'C01'})
  -[:PLACED]->(:Order {orderId: 'O01', amount: 120000})
  -[:PLACED]->(:Order {orderId: 'O02', amount: 180000})

(:Customer {customerId: 'C01'})
  -[:WROTE]->(:Review {reviewId: 'R01'})
  -[:WROTE]->(:Review {reviewId: 'R02'})
  -[:WROTE]->(:Review {reviewId: 'R03'})
~~~

The following query generates **6 rows** for a customer with 2 orders and 3 reviews:

~~~cypher
MATCH (c:Customer {customerId: 'C01'})
MATCH (c)-[:PLACED]->(o:Order)
MATCH (c)-[:WROTE]->(r:Review)
RETURN count(o) AS orderCount,
       count(r) AS reviewCount,
       sum(o.amount) AS totalAmount;
// Wrong for counting distinct nodes by business rule:
// orderCount = 6, reviewCount = 6, totalAmount = 900000.
~~~

If a Java method returns an order summary DTO, **integration tests must assert the exact aggregated values**, not merely `assertThat(result).isNotNull()`. With the numbers above, counting each order once yields `2` orders, `3` reviews, and `300000` total amount. Fix the Cypher by aggregating each branch separately (or equivalent) before considering the test green.

**Edge cases to include in fixtures:**

| Data case | Defects commonly caught |
|---|---|
| Zero relationships | `MATCH` drops the root node instead of using `OPTIONAL MATCH` |
| Node with multiple relationships of the same type | Row multiplication, duplicate items in mapper |
| Two one-to-many branches | Wrong `count`/`sum` due to Cartesian product |
| Multiple nodes with equal price/score | Missing tie-breaker in `ORDER BY`, unstable pagination |
| Null / absent properties | Java primitive mapping errors, filters dropping unexpected nulls |
| Duplicate identifier keys | Missing uniqueness constraint and server error handling |
| Unexpected relationship direction | Wrong `@Relationship`, `MATCH`, or projection |
| Persisted node loaded partially into object | Overwriting/deleting relationships when saving a partially loaded entity |

Specifically for `@Query` methods returning entities with relationships, consult SDN documentation on **custom query mapping**: the return clause often must include **the root node plus related relationships and target nodes** for the mapper to reconstruct the graph. Returning only `RETURN b` does not guarantee all relationships of `b` are populated; never pass a partially loaded entity into `save` to overwrite the graph without understanding SDN's save semantics.

## 8. Viewing the **Actual Cypher** Executed by SDN

This is the core step of the lesson: **never guess the executed query from the Java method name**. Depending on data access style, SDN may vary variable aliases, filter predicates, `WITH`, `RETURN`, relationship-loading subqueries, and parameters.

### 8.1. Enabling Application-Side Logging in the Test Profile

Example **`src/test/resources/application-test.yml`**:

~~~yaml
logging:
  level:
    org.springframework.data.neo4j: DEBUG
    org.springframework.data.neo4j.cypher: DEBUG
    org.neo4j.driver: INFO
~~~

Activate the profile via `@ActiveProfiles("test")` or equivalent test runner configuration. Exact log categories and output details vary across versions; verify them in practice. Per SDN documentation, the `org.springframework.data.neo4j.cypher` logger records Cypher statements executed by SDN along with server notifications. **This is an application-side observation point**, not a guarantee that every raw driver call or every parameter value is always logged.

When the test runs:

~~~java
repository.findByPriceGreaterThanEqualOrderByPriceAsc(100_000L);
~~~

search the log output for entries mentioning `CatalogBook` or the running method. The generated query may use different variable aliases than `b`, bind parameters instead of literal `100000`, and include extra clauses. **Never treat a hand-written example like `MATCH (b:CatalogBook) ...` as proof of what SDN actually sent.**

### 8.2. Inspecting **Neo4j Server** Query Logs

When you need proof of **exactly which queries the server received and executed**, Neo4j's query log is the authoritative reference. On **Neo4j Enterprise** or environments supporting query logging, enable scoped logging on an **isolated test database**:

~~~properties
# neo4j.conf -- example for test observability environment
db.logs.query.enabled=INFO
db.logs.query.threshold=0s
db.logs.query.parameter_logging_enabled=false
~~~

Setting `INFO` with `0s` logs completed queries without a minimum duration threshold. Setting `parameter_logging_enabled=false` prevents sensitive parameter values from leaking into logs. In newer Neo4j versions, `VERBOSE` logs query start as well as completion; follow version-specific documentation and avoid leaving verbose logging on in production unnecessarily.

Server query logs capture every query **received by Neo4j**, including when a single repository call fans out into multiple queries. When correlating, check **database**, **username**, **timestamp**, **query text**, **transaction metadata**, **status/elapsed time**, and **parameters where policy permits**.

**Note two limitations:**

1. Server query logging may require **Enterprise Edition**, host/log access, and environment configuration. On Community Edition or managed services without query logs, rely on application loggers or approved driver-level instrumentation.
2. Logging parameters, literals, or errors can expose customer data, tokens, or passwords. Enable detailed logging only in test environments with synthetic data; never paste sensitive logs into issue trackers or CI artifacts.

### 8.3. Correlating a Request with Log Entries

When multiple tests run in parallel, searching for `MATCH` in logs will not tell you which test issued which query. You can attach transaction metadata at the driver/service layer for explicitly managed transactions—such as `requestId` or `operation`—and search for it in query logs:

~~~java
TransactionConfig txConfig = TransactionConfig.builder()
        .withMetadata(Map.of(
                "operation", "catalog-filter-test",
                "requestId", requestId))
        .build();
~~~

This snippet illustrates the **Neo4j Java Driver** API for configuring a transaction with `txConfig`; it does not automatically attach metadata to every SDN transaction. To correlate across SDN repositories, integrate with your transaction manager, driver instrumentation, or version-supported metadata hooks.

## 9. From Observed Cypher to `EXPLAIN` and `PROFILE`

After capturing the **actual query** and **representative parameter values**, re-run it against the same database snapshot to inspect its execution plan. Never analyze only the Cypher you *assume* SDN generates.

For instance, if the **observed** query has this form:

~~~cypher
MATCH (b:CatalogBook)
WHERE b.price >= $minPrice
RETURN b
ORDER BY b.price ASC;
~~~

you can run:

~~~cypher
EXPLAIN
MATCH (b:CatalogBook)
WHERE b.price >= $minPrice
RETURN b
ORDER BY b.price ASC;
~~~

In Neo4j Browser, define the parameter first:

~~~cypher
:param minPrice => 100000
~~~

`EXPLAIN` builds the plan **without executing** the query. `PROFILE` executes it and adds actual row and hit metrics:

~~~cypher
PROFILE
MATCH (b:CatalogBook)
WHERE b.price >= $minPrice
RETURN b
ORDER BY b.price ASC;
~~~

This is an **illustrative query**; it represents the real workload only if logs from the prior step confirmed this exact shape. Whenever logs show `WITH`, `DISTINCT`, `LIMIT`, longer patterns, or multiple `MATCH` clauses, include all of them verbatim in your analysis.

### What Should You Read in the Plan?

| Metric / operator | Practical question |
|---|---|
| `NodeByLabelScan`, `NodeIndexSeek`, `NodeIndexScan` | Is Neo4j scanning the label or using a property index? |
| `Filter` | How many rows are discarded after reading nodes? |
| `Expand(All)` / `Expand(Into)` | Which relationships inflate intermediate row counts? |
| `Sort`, `Top` | Does `ORDER BY`/`LIMIT` sort large row sets? |
| `Rows` | Do actual rows flowing between operators spike unexpectedly? |
| `DB Hits` | Which operator accesses storage the most in the plan? |
| `Estimated Rows` vs. actual `Rows` | Did the optimizer misestimate due to stale stats or data skew? |

`DB Hits` **does not equal** physical disk reads; wall-clock time also depends on page cache, data volume, load, and network. When validating index changes or query rewrites, keep the database snapshot and parameters constant and run multiple iterations on representative data.

**Never run `PROFILE` recklessly on write Cypher**: `PROFILE` **executes the query**, so `CREATE`/`MERGE`/`DELETE` will mutate live data. Analyze write queries on a test database, inside controlled transactions, or on a copy first.

## 10. Verifying Persisted Results **After `save`** via an Independent Read

When testing `repository.save(entity)`, asserting that the returned object has an ID is not enough. Verify the **actual persisted data in the graph**:

~~~java
@Test
void savePersistsExpectedProperties() {
    repository.save(new CatalogBook(
            "B04", "Graph Transactions", 220_000L));

    var price = client.query("""
            MATCH (b:CatalogBook {isbn: $isbn})
            RETURN b.price AS price
            """)
            .bind("B04").to("isbn")
            .fetchAs(Long.class)
            .one();

    assertThat(price).contains(220_000L);
}
~~~

Here the method executes **inside the test's own transaction**, so the `Neo4jClient` query sees uncommitted changes made just prior to the end-of-test rollback. If you instead open a **separate Java Driver/session outside that transaction** to inspect the database, that external query **will not see uncommitted data**. That is transaction isolation, not evidence that SDN failed to save.

This test illustrates adding a method to the test class from Section 5. Its `@BeforeEach` still seeds `B01`–`B03`, while `B04` is created within this test. If your practice database already contains `B04` from another test or runs suites concurrently, use isolated fixture keys or clean test databases for determinism.

## 11. Transactions and Rollbacks in Tests Commonly Misunderstood

With imperative `@DataNeo4jTest`, Spring Boot runs each test inside a transaction and **rolls it back at the end of the test** by default. While helpful for fixture isolation, remember these edge cases:

| Case | What to remember |
|---|---|
| `repository.save` followed by `Neo4jClient` in the same Spring transaction | Sees uncommitted changes from the active test transaction |
| Opening a separate driver connection/session in the test | Cannot see uncommitted changes from the test transaction |
| Calling a service that opens an **independent transaction** like `REQUIRES_NEW` | Commits outside the test transaction and **will not roll back with the test** |
| Testing `@TransactionalEventListener` or post-commit callbacks | Default test rollback may never trigger commit-bound callbacks |
| Using reactive Neo4j repositories | Default imperative `@Transactional` on the test slice **does not manage** reactive publisher transactions |
| Using `@SpringBootTest` | Never assume an entire HTTP test call runs inside the test's rollback transaction |

When you need to verify **post-commit** effects, design explicit boundaries. In imperative Spring tests, you can use `TestTransaction.flagForCommit()` and `TestTransaction.end()` inside an active test transaction, or run the workflow in an isolated environment and clean up afterward. Tests running near shared data should never disable rollback without a reliable cleanup mechanism.

**For reactive repositories**, use `TransactionalOperator` or proper reactive transaction configuration; do not rely on imperative `@Transactional` test annotations to roll back a `Mono`/`Flux` pipeline.

## 12. Comparing Queries and Results by Evidence Confidence Level

When claiming "the application executes Cypher X and returns result Y," distinguish levels of evidence:

| Evidence | Claim it supports | Limitation |
|---|---|---|
| Repository method in source code | Developer's intended query | Does not reflect the actual post-mapping query |
| Unit test with mocks | Service calls the repository properly | Proves nothing about Neo4j execution |
| Integration test + object assertions | SDN returns expected objects for the fixture | Does not reveal the exact Cypher generated |
| `org.springframework.data.neo4j.cypher` log | Statements SDN invokes and server notifications under that config | May omit direct driver/plugin operations |
| Server query log | Queries Neo4j **actually received and executed** within log filters | Subject to edition, permissions, thresholds, and config |
| `EXPLAIN` on captured query | Planned execution operators for that Cypher/parameters | Contains no runtime statistics |
| `PROFILE` on captured query | Runtime execution cost and actual row counts for that run | Mutates data if query writes; timing varies with environment |

For highest confidence, **combine** three layers: (1) integration tests proving domain outcomes, (2) logs confirming exact queries sent, and (3) execution plans showing how Neo4j processed them. No single layer replaces the other two.

## 13. Workflow for Investigating a Slow or Incorrect Repository

1. **Reproduce on a small fixture** with an explicit graph: exact node counts, relationship branches, cardinalities, and properties.
2. **Write correctness assertions**: row counts, totals, ordering, relationship mappings; include 0, 1, and many-relationship cases.
3. **Enable application Cypher logging in tests** and invoke **the exact problematic repository/service call**.
4. **Capture the actual query** along with parameters, target database, and SDN/Neo4j versions. Distinguish individual queries if multiple fire.
5. **Inspect server query logs** if supported by your environment to verify what Neo4j executed.
6. **Run `EXPLAIN`/`PROFILE`** on the captured query with realistic parameter types; examine indexes, `Rows`, `DB Hits`, and `Sort`.
7. **Change one thing intentionally**: the query, entity mapping, index/constraint, or graph-loading strategy; re-run all assertions.
8. **Compare before and after on identical data** to avoid optimizing the wrong semantics or merely measuring warm page-cache effects.

### Example: Catching a Query Not Using an Expected Index

Suppose a repository filters by `CatalogBook.price` and returns few nodes. If `PROFILE` shows a label scan across large data, evaluate adding a **range index** in a test database:

~~~cypher
CREATE RANGE INDEX catalog_book_price_idx IF NOT EXISTS
FOR (b:CatalogBook) ON (b.price);
~~~

Once the index reaches `ONLINE`, re-run the **exact logged query** and compare plans. On a tiny three-node fixture, the optimizer may skip the index altogether—so never write brittle assertions requiring `NodeIndexSeek` across every dataset size. Test **index existence and status** separately as schema checks, and test performance plans on representative data volumes.

## 14. Verifying Real Schema and Data Instead of Trusting Annotations Alone

SDN mappings tell the application how to turn nodes into Java objects; integrity rules like **uniqueness constraints** must exist in Neo4j itself. Many projects apply schema migrations or setup scripts before starting the application.

Inspect constraints:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties
RETURN name, type, labelsOrTypes, properties
ORDER BY name;
~~~

In the `CatalogBook` domain, if `isbn` must be unique, the expected schema includes:

~~~cypher
CREATE CONSTRAINT catalog_book_isbn_unique IF NOT EXISTS
FOR (b:CatalogBook)
REQUIRE b.isbn IS UNIQUE;
~~~

Never run schema DDL **inside the same data-manipulation test transaction** expecting test rollback to clean up constraints. Apply schema during test database initialization before seeding fixtures and running assertions. If test schema diverges from production, constraint and performance tests lose validity.

## 15. Test Data and CI-Friendly Configuration

Reliable integration tests must **produce identical results across repeated runs**:

- Use **explicit identifying keys** such as `isbn`, `customerId`, and `orderId`; never depend on `elementId()` staying constant across runs.
- Use deterministic test values rather than random numbers or current `datetime()` for ordering assertions unless controlled.
- Isolate databases or use unique fixture namespaces/keys per parallel test.
- Manage container lifecycles cleanly; never share a stopped container across cached Spring `ApplicationContext` instances.
- Separate commit-verifying tests from default rollback tests.
- Ensure Neo4j is ready and schema is applied before sending queries; Testcontainers helps coordinate startup readiness.
- Run tests against the supported Neo4j/SDN versions; add dedicated compatibility checks when upgrading.
- Avoid brittle absolute latency assertions in CI such as `< 10ms`, since container and cache conditions fluctuate. Benchmark plans and large workloads in dedicated environments.

### Common Environment Pitfalls

| Symptom | Likely cause | What to check |
|---|---|---|
| `@DataNeo4jTest` fails to connect to DB | Missing connection details or Neo4j not started | `@ServiceConnection`, container, URI, credentials |
| Test passes alone, fails in full suite | Shared state, container lifecycle, or overlapping transactions | Fixture isolation, context caching, parallel execution |
| Query runs yet Java values are wrong | Property mapping, types, converters, or query omitting nodes/edges | Compare Cypher output directly against entity mapping |
| Query returns more rows than nodes | Relationship expansion combined with aggregations | Check `Rows`; deduplicate/group properly |
| SDN queries missing from logs | Logger/profile disabled or wrong log level | Check `application-test.yml`, logger names, library version |
| Queries missing from server query log | Edition, threshold, or permissions | Check query logging settings and executed server queries |
| Test sees object yet direct read misses data | Two transactions/sessions have different isolation views | Shared Spring transaction, commit/rollback, connection setup |
| Assuming an index is used just because it exists | Planner chose a different plan | `SHOW INDEXES` + `EXPLAIN`/`PROFILE` |

## 16. Spring Boot 4 and SDN 8 Compatibility Notes

The main examples use **Spring Boot 3.5** packages and modules:

~~~java
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.testcontainers.containers.Neo4jContainer;
~~~

In **Spring Boot 4**, the Neo4j test slice moved to the dedicated module `spring-boot-data-neo4j-test`, and the annotation is imported from:

~~~java
import org.springframework.boot.data.neo4j.test.autoconfigure.DataNeo4jTest;
~~~

With **Testcontainers 2.x**, the Neo4j container also moved to its module-specific package:

~~~java
import org.testcontainers.neo4j.Neo4jContainer;
~~~

Never mix Boot 3.5 dependency coordinates with Boot 4 package names or mismatched Testcontainers versions without checking the BOM. Always consult documentation matching your exact Spring Boot, SDN, Neo4j, and Testcontainers versions; entity and repository concepts remain consistent, while test infrastructure coordinates must align.

## 17. Practice Exercises

### Exercise 1 — Is Unit Testing Enough?

A developer mocks `CatalogBookRepository` to return two books priced above 100,000 and claims `findByPriceGreaterThanEqualOrderByPriceAsc` is verified. Is that conclusion valid?

<details>
<summary>Suggested answer</summary>

Not enough. The unit test only verifies how the service handles mocked outputs. You need `@DataNeo4jTest` against real Neo4j, seed at least three books above and below the threshold, invoke the method, and assert results—then inspect the executed query in logs.

</details>

### Exercise 2 — Testing Aggregations with Multiple Relationships

Customer `C01` has two orders (120,000 and 180,000) and three reviews. A query expands both `MATCH` branches and computes `count(o)` and `sum(o.amount)`. Predict the output and write the assertions needed.

<details>
<summary>Suggested answer</summary>

There are `2 × 3 = 6` intermediate rows. `count(o) = 6` and `sum(o.amount) = 900000` are wrong if business rules count each order once. Tests must assert `orderCount = 2`, `reviewCount = 3`, and `totalAmount = 300000`, forcing the query to be fixed.

</details>

### Exercise 3 — Verifying the Real Query

A repository defines `findByNameContainingIgnoreCase`. A teammate hand-writes `WHERE toLower(n.name) CONTAINS toLower($keyword)` and runs `PROFILE`, claiming it represents the application's query plan. What step is missing?

<details>
<summary>Suggested answer</summary>

You must execute the **actual repository method** with logging enabled and capture the exact Cypher and parameters SDN sends; if possible, cross-check the server query log. Only then should you run `EXPLAIN`/`PROFILE` on the observed query. A hand-guessed query can differ from what SDN actually executes.

</details>

### Exercise 4 — Why Did a Direct Read Return Null?

A `@DataNeo4jTest` calls `repository.save(...)`, then opens a brand-new Java Driver session to look up the node and finds nothing. Does that prove `save` failed?

<details>
<summary>Suggested answer</summary>

No. Imperative `@DataNeo4jTest` methods usually run in a transaction that rolls back at test end; a separate external session cannot see uncommitted data. Read via `Neo4jClient` inside the same transaction, or design an intentional commit test and verify from an independent session.

</details>

### Exercise 5 — Choosing the Right Observation Method

You have three goals: (a) verify repository filtering logic, (b) see which queries the Neo4j server received, and (c) find which operator generates excessive `DB Hits`. Which tool serves each goal?

<details>
<summary>Suggested answer</summary>

(a) Integration tests with deterministic fixtures and result assertions; (b) server query logs where supported alongside application Cypher logging; (c) `PROFILE` on the **actual captured query** with matching parameters and data. All three complement one another.

</details>

## 18. Versioned References

- [Spring Data Neo4j — Testing with Spring Boot and @DataNeo4jTest](https://docs.spring.io/spring-data/neo4j/reference/testing/testing-with-spring-boot.html)
- [Spring Data Neo4j — Logging](https://docs.spring.io/spring-data/neo4j/reference/appendix/logging.html)
- [Spring Data Neo4j — Defining Query Methods](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-methods-details.html)
- [Spring Boot 3.5 — Auto-configured Data Neo4j Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — Testcontainers and @ServiceConnection](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)
- [Spring Boot 4 — Auto-configured Data Neo4j Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Neo4j Operations Manual — Query Logging](https://neo4j.com/docs/operations-manual/current/monitoring/logging/)
- [Neo4j Cypher Manual — Query Tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/)

`current` URLs may point to newer versions as Spring or Neo4j release updates. In real projects, consult documentation matching your exact versions and verify actual logs and procedures rather than assuming identical behavior across releases.

## 19. Key Takeaways

- **Test real repositories against real Neo4j** to verify Cypher and mappings; mocked repositories verify neither.
- **`@DataNeo4jTest` is a test slice** that rolls back imperative test transactions by default and requires you to supply a real database/Testcontainers instance.
- **Fixtures must be independent and cross-checkable**: include zero/many relationships, null values, duplicate keys, price ties, and aggregated totals.
- **Observe the actual Cypher** via application logs and, when available, server query logs—never infer it solely from method names or hand-written guesses.
- **`EXPLAIN`/`PROFILE` are meaningful only on the exact captured query and parameters** over representative data; remember `PROFILE` executes writes if the query mutates data.
- **Transactions, mappings, schema, and library versions all shape test outcomes**. Distinguish query logic bugs from rollback, isolation, or test-environment effects.
