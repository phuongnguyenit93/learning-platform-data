# Designing Small, Deterministic, and Independent Fixtures for MongoDB Testing

A MongoDB test may pass on a developer's machine yet fail in CI, when test execution order changes, or when re-run a few minutes later. In many cases MongoDB itself is not misbehaving; rather, the test **fixture** depends on external state: leftover documents in a collection, auto-generated IDs on every run, shifting wall-clock time, Test A deleting Test B's data, missing unique indexes, or unsorted queries whose tests rely on result ordering.

A **fixture** is the known input state deliberately established before executing a test. In MongoDB, a fixture may encompass documents, collections, indexes, validators, BSON types, a fixed timestamp, and—where needed—test environment topology and permissions.

This lesson belongs to the **Testing** chapter of the **MongoDB Document Database Engine** module and focuses on three core properties:

1. **Minimal:** only the data and configuration needed to prove the behavior under test.
2. **Deterministic:** the same inputs and critical preconditions yield the same expected outcome.
3. **Independent (isolated/repeatable):** running alone, re-running, reordering, or running in parallel causes zero interference.

Examples use mongosh, MongoDB Java Sync Driver, JUnit 5, and a test MongoDB environment. **Never run potentially destructive seed or cleanup commands against production.**

## 1. How Does a Fixture Differ from Seed Data, Mocks, and the Test Environment?

| Concept | Role |
| --- | --- |
| Fixture | Known state of the system prior to the test |
| Seed script | Mechanism for populating fixture data |
| Factory/builder | Helper creating Document/POJO fixtures |
| Mock | Fake object replacing a dependency |
| Stub | Fake dependency returning predefined data |
| Test database | Namespace holding the fixture |
| Test environment | MongoDB server, topology, driver, credentials, and dependencies |
| Assertion oracle | Expected value/outcome, independent of the code under test |

A unit test can use a mocked repository to test a pure function. However, verifying **MongoDB query semantics, unique indexes, $elemMatch, transactions, or TTL** requires a corresponding integration test against a real server.

### 1.1. Test Cycle

~~~text
Arrange:
  Allocate isolated namespace
  Create required collections, indexes and validators
  Seed minimal documents

Act:
  Call repository/service method

Assert:
  Check exact values, order and persisted invariants

Cleanup:
  Remove only owned resources
  Close sessions, cursors and clients
~~~

### 1.2. A Fixture Is a Precondition Contract

Every test must know the initial `_id`s, field types, indexes, and critical state. Assuming “`order-test` is probably already on CI” without knowing who created it leaves the test without a trustworthy precondition.

## 2. Why Should Fixtures Be Small?

Suppose the requirement is: return only **PAID orders belonging to tenant-a**.

Only three documents are needed:

| _id | tenantId | status |
| --- | --- | --- |
| o-001 | tenant-a | PAID |
| o-002 | tenant-a | PENDING |
| o-003 | tenant-b | PAID |

Expected result: only **o-001**.

- If the code omits the status filter, it also returns o-002.
- If the code omits the tenant filter, it also returns o-003.
- If the code is correct, only o-001 is returned.

### 2.1. Every Document Has a Purpose

In a well-designed fixture, a reader can answer: “What bug does this record help catch?” If removing a record does not reduce bug-detection capability, it may be redundant data.

### 2.2. Include Both Positive and Negative Controls

A fixture containing only a single valid record often fails to catch missing filter predicates. Negative controls distinguish a correct implementation from an overly permissive one.

### 2.3. Minimal Is Different from Happy-Path Only

Depending on the test, a small fixture may still require:

- Values just below and above thresholds.
- Missing fields and null fields.
- Documents belonging to another tenant.
- Two records sharing a timestamp to test tie-breakers.
- A product with insufficient stock.
- A nested array where predicates could match two different elements.

### 2.4. Do Not Copy an Entire Production Collection

One million documents slow setup, obscure expected results, and increase PII exposure risks. Representative datasets for performance/load testing are a separate artifact from small logic fixtures.

## 3. Determinism: Fixing Factors That Affect Outcomes

A test is deterministic when:

~~~text
Fixture version F
+ input I
+ preconditions P
+ behavior under test B
= expected output O
~~~

Common sources of non-determinism:

- **new Date()** or **Instant.now()** inside fixtures.
- Uncontrolled **ObjectId()**, UUID, or random IDs.
- Unseeded **Random()**.
- Asserting result order on **find()** without sorting.
- Asynchronous TTL monitor runs.
- Slow Change Stream / event consumer delivery.
- Secondary reads subject to replication lag.
- Parallel writes whose outcomes depend on thread scheduling.
- Shared mutable Java Document/List instances.
- Unpinned MongoDB server/driver versions.
- Default timezone/locale on the CI machine.

You do not need to eliminate concurrency or time from every test. What matters is **asserting the right contract**: some places require exact-value checks, while others require bounded-deadline eventual state checks.

## 4. Independence Across Runs

A test should pass when:

1. Run in isolation.
2. Run after another test.
3. Run before another test.
4. Run two or more times consecutively.
5. Run concurrently with other tests if the framework permits.
6. Run in CI against a clean MongoDB test environment.

### 4.1. Test Order Dependence Is a Bug

Anti-pattern:

~~~text
Test A: insert order o-001
Test B: assume o-001 exists
Test C: delete o-001
~~~

If B runs before A, it fails; if C runs before B, it fails. A test must never delegate its setup to another test.

### 4.2. Tests Set Up Their Own Preconditions

~~~text
Test B:
  @BeforeEach -> insert order o-001
  @Test -> perform read/assert
  @AfterEach -> delete/drop own state
~~~

### 4.3. Shared Fixtures Make Sense Only When Immutable

Immutable factories and configs can be shared. Shared mutable documents or a single collection mutated/wiped by multiple tests is a major source of flakiness.

## 5. Three Practical Isolation Tiers

| Strategy | Description | Advantage | Risk |
| --- | --- | --- | --- |
| Per-document | Unique IDs per test | Low overhead | Broad queries or buggy cleanup can collide |
| Per-collection | Dedicated collection per test | Separates indexes and documents | Must create/drop collections |
| Per-database | Dedicated database per test | Clear isolation, simple setup/teardown | Many namespaces, DDL overhead |
| Per-deployment | Dedicated container/cluster | Isolates server/topology | Higher startup and operational cost |

### 5.1. Sensible Default Choice

For Java CRUD integration tests, a **per-test database** on a controlled test server is an easy-to-reason-about default. Unit tests that do not need real MongoDB need no database at all.

### 5.2. Random Namespaces with Deterministic Results

A database name with a random UUID suffix solely for isolation is perfectly fine as long as that name **never appears in expected business output**. Documents, timestamps, and assertions inside remain fixed.

### 5.3. Parallel Execution

Two tests both using `_id="o-001"` remain independent when placed in separate databases. If they share a collection, both can trigger duplicate key errors or wipe each other's data.

## 6. Sample Orders Fixture

Using a dedicated lab database:

~~~javascript
use mongo_fixture_lab

db.orders.insertMany([
  {
    _id: "o-001",
    tenantId: "tenant-a",
    externalId: "EXT-001",
    status: "PAID",
    totalMinor: NumberLong(150000),
    createdAt: ISODate("2026-01-15T08:00:00Z")
  },
  {
    _id: "o-002",
    tenantId: "tenant-a",
    externalId: "EXT-002",
    status: "PENDING",
    totalMinor: NumberLong(90000),
    createdAt: ISODate("2026-01-15T09:00:00Z")
  },
  {
    _id: "o-003",
    tenantId: "tenant-b",
    externalId: "EXT-001",
    status: "PAID",
    totalMinor: NumberLong(200000),
    createdAt: ISODate("2026-01-15T10:00:00Z")
  }
]);
~~~

**Use only on an empty, writable lab database.** In automated suites, create a separate database per test instead of seeding everything into a shared `mongo_fixture_lab`.

### 6.1. Fixed IDs

`_id` values like `o-001` keep expected outputs readable without tracing random generated values.

### 6.2. Fixed Timestamps

All dates use UTC ISO-8601, independent of the system date when tests run.

### 6.3. Consistent Numeric Types for Totals

`NumberLong` represents a 64-bit integer. If production uses `Decimal128`, fixtures and tests must also use `Decimal128`.

### 6.4. Purposeful Tenant-b

`externalId` `EXT-001` repeats in `tenant-b` under a different tenant, testing tenant-scoped uniqueness and queries.

## 7. Creating Indexes as Part of the Fixture

Example of per-tenant unique business identity:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, externalId: 1 },
  {
    unique: true,
    name: "uq_tenant_external_id"
  }
);
~~~

### 7.1. Indexes Affect Correctness

If a test expects duplicate keys to be rejected without creating the index, it does not model the real schema. Unique indexes belong in setup rather than assuming “previous CI runs created it.”

### 7.2. Create Indexes Before Seeding

This typically catches duplicate fixture rows immediately during insert rather than waiting for an index build afterward.

### 7.3. Do Not Create Every Production Index in Every Test

Create the indexes needed for the behavior or constraint under test. Use a fuller representative setup for dedicated performance tests.

### 7.4. Index Options Matter Too

An index can be unique, partial, sparse, collated, or TTL. Never inspect only the index name when a test depends on specific index behavior.

## 8. Querying for Exact Expected IDs

~~~javascript
db.orders.find(
  {
    tenantId: "tenant-a",
    status: "PAID"
  },
  { _id: 1 }
).sort({ _id: 1 });
~~~

Expected: **["o-001"]**.

### 8.1. Do Not Assert Only Contains

If a test only checks that `o-001` is present, a buggy query returning `o-001`, `o-002`, and `o-003` would still pass. Compare the complete result set/list.

### 8.2. Keep the Expected Oracle Independent of Implementation

If a repository uses a buggy filter and the test computes its expected result using that identical filter, both are wrong and the test still passes. Derive expected values directly from the fixture and requirements.

### 8.3. Separate Act from Oracle

In repository integration tests, Act must invoke the **repository method under test**, rather than running a duplicate query in the test and claiming the repository was tested.

## 9. Simple Java Fixture Factory

~~~java
import org.bson.Document;
import java.time.Instant;
import java.util.Date;
import java.util.List;

public final class OrderFixtures {
    private OrderFixtures() {}

    private static Date date(String iso) {
        return Date.from(Instant.parse(iso));
    }

    public static Document paidTenantA() {
        return new Document("_id", "o-001")
            .append("tenantId", "tenant-a")
            .append("externalId", "EXT-001")
            .append("status", "PAID")
            .append("totalMinor", 150000L)
            .append(
                "createdAt",
                date("2026-01-15T08:00:00Z")
            );
    }

    public static Document pendingTenantA() {
        return new Document("_id", "o-002")
            .append("tenantId", "tenant-a")
            .append("externalId", "EXT-002")
            .append("status", "PENDING")
            .append("totalMinor", 90000L)
            .append(
                "createdAt",
                date("2026-01-15T09:00:00Z")
            );
    }

    public static Document paidTenantB() {
        return new Document("_id", "o-003")
            .append("tenantId", "tenant-b")
            .append("externalId", "EXT-001")
            .append("status", "PAID")
            .append("totalMinor", 200000L)
            .append(
                "createdAt",
                date("2026-01-15T10:00:00Z")
            );
    }

    public static List<Document> defaultOrders() {
        return List.of(
            paidTenantA(),
            pendingTenantA(),
            paidTenantB()
        );
    }
}
~~~

### 9.1. Return a Fresh Object Every Time

Never share a static mutable `Document` across tests that mutate it. Factories return a new `Document`, and nested objects/dates should likewise be freshly created or deep-copied.

### 9.2. Date Is Mutable

A new `Date` is instantiated per factory call; never share one `Date` instance across tests that might mutate it.

### 9.3. Java Long and BSON

`150000L` maps to BSON Int64. If the schema requires `Decimal128`, use the proper codec/type instead of substituting a String.

### 9.4. Expressive Factory Names

Names like `paidTenantA` and `pendingTenantA` immediately convey why the document exists.

## 10. Builder Factory with Overrides

When many tests vary state:

~~~java
public static Document order(
    String id,
    String tenant,
    String externalId,
    String status,
    long totalMinor
) {
    return new Document("_id", id)
        .append("tenantId", tenant)
        .append("externalId", externalId)
        .append("status", status)
        .append("totalMinor", totalMinor)
        .append(
            "createdAt",
            Date.from(
                Instant.parse("2026-01-15T00:00:00Z")
            )
        );
}
~~~

Example:

~~~java
Document cancelled = order(
    "o-cancelled",
    "tenant-a",
    "EXT-CANCELLED",
    "CANCELLED",
    120000L
);
~~~

### 10.1. Avoid Mega Factories

A function with 25 optional arguments or booleans makes tests unreadable. Prefer intent-named factory methods or a small builder with clear defaults.

### 10.2. Explicit Values for Critical Fields

When testing a state transition, write the initial status explicitly in the test instead of relying on a hidden default in a factory.

### 10.3. Deep Copy When Necessary

A `Document` can contain `List<Document>` and nested `Document`s. Shallow copies can share nested references, causing Test A's array edit to leak into Test B.

## 11. Never Rely on Natural Order of find

A flawed test:

~~~java
List<Document> actual = orders.find(
    Filters.eq("tenantId", "tenant-a")
).into(new ArrayList<>());

assertEquals(
    "o-001",
    actual.get(0).getString("_id")
);
~~~

MongoDB does not guarantee natural result order as a business contract. Sort explicitly:

~~~java
List<Document> actual = orders.find(
    Filters.eq("tenantId", "tenant-a")
).sort(
    Sorts.ascending("_id")
).into(
    new ArrayList<>()
);
~~~

### 11.1. When Order Does Not Matter

You can compare sets of IDs, while still verifying counts or absence of duplicates if required.

### 11.2. When Pagination Matters

Sort by `createdAt` and add an `_id` tie-breaker so ordering is unambiguous when timestamps collide.

### 11.3. Do Not Rely on Index Order

Query planners and indexes can change; never treat an index scan order as an API guarantee if the query does not specify a sort.

## 12. Fixing Time with java.time.Clock

Avoid writing expected values based on scattered `Instant.now()` calls:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixed = Clock.fixed(
    Instant.parse("2026-01-15T10:00:00Z"),
    ZoneOffset.UTC
);
~~~

A service can accept `Clock` via its constructor:

~~~java
public final class OrderService {
    private final Clock clock;

    public OrderService(Clock clock) {
        this.clock = clock;
    }

    public Instant currentTime() {
        return clock.instant();
    }
}
~~~

### 12.1. Why Is Injection Better?

Tests assert exact timestamps; production supplies `Clock.systemUTC()` or the appropriate dependency.

### 12.2. Server-Side Time Differs from Application Time

`Clock.fixed` **does not** control the MongoDB server clock, `$currentDate`, the TTL monitor, or other server-generated timestamps.

### 12.3. Testing `$currentDate`

If behavior depends on server time, assert the timestamp falls within a controlled interval and document the tolerance rather than comparing against `Clock.fixed`.

### 12.4. Timezone and Locale

Use `Instant`/UTC to represent instants in time. If the application formats for a user timezone, test formatting separately without depending on CI's default system timezone.

## 13. Controlling Randomness and Auto-Generated IDs

If random data generation is unavoidable:

~~~java
import java.util.Random;

Random random = new Random(20260115L);
int quantity = random.nextInt(5) + 1;
~~~

### 13.1. Seed Is Input Data

Log the seed on failure so cases are reproducible. With property-based testing, also record the shrunk minimal counterexample.

### 13.2. Randomness Is Unnecessary for Most Fixtures

If you need `quantity=3`, declaring `3` directly makes the expected output far clearer than randomizing it.

### 13.3. UUIDs for Namespaces

`UUID.randomUUID()` works well to avoid database name collisions since the database name is not compared as business output.

### 13.4. ObjectId

When a test needs an exact `_id` comparison, use a fixed `ObjectId`:

~~~java
import org.bson.types.ObjectId;

ObjectId id = new ObjectId(
    "65a000000000000000000001"
);
~~~

When testing ID generation itself, assert non-null/uniqueness rather than hardcoding a generated value.

### 13.5. ObjectId Type Differs from String

Filtering by the string `"65a..."` is not equivalent to filtering by an `ObjectId` with the same hex representation.

## 14. Per-Test Database Isolation

Each test can allocate a unique namespace:

~~~text
Test 1: it_orders_0fe8... / orders
Test 2: it_orders_6dc2... / orders
Test 3: it_orders_a2d1... / orders
~~~

Inside each database, tests can reuse identical IDs without colliding.

### 14.1. Recreate Required Indexes and Schemas

A fresh database starts empty. Setup must not rely on migrations executed by another test.

### 14.2. Teardown Drops Only Owned Databases

If a test stores `databaseName=it_orders_0fe8...`, only that database is dropped after the test.

### 14.3. Random Database Names and Determinism

Business fixtures remain exact; random namespaces used purely for isolation do not alter test results.

### 14.4. Production Guardrails

Even with an `it_` database prefix, a test URI can still be misconfigured. Real safety comes from isolated test deployments, restricted credentials, and cluster identity checks.

## 15. JUnit 5 Lifecycle

Annotations:

- **@BeforeAll:** set up resources shared across the class/suite.
- **@BeforeEach:** set up an isolated fixture before each test.
- **@Test:** execute behavior and assertions.
- **@AfterEach:** clean up after each test.
- **@AfterAll:** release shared resources.

Recommended structure:

~~~text
@BeforeEach
  verify test environment
  create unique DB
  create indexes
  insert fixed documents

@Test
  call repository
  assert exact results

@AfterEach
  stop owned workers
  drop owned DB
  close owned cursors/client
~~~

### 15.1. Do Not Turn @BeforeAll into a Default Shared Mutable Database

If tests mutate the same database set up in `@BeforeAll`, parallel runs or reordering will interfere. Share only immutable configs or containers/servers, keeping state isolated.

### 15.2. Cleanup Must Run Even When Tests Fail

JUnit `@AfterEach` runs cleanup even when assertions fail. If `@BeforeEach` fails midway, teardown must check which resources were already created.

### 15.3. Tests Must Not Depend on `@Order`

If a workflow has multiple dependent steps, place them inside one test with clear Arrange/Act/Assert rather than chaining separate test methods.

## 16. JUnit 5 + Java Sync Driver: Independent Fixture

This integration test example connects to a test MongoDB deployment via **MONGODB_TEST_URI**. Configure dedicated test credentials and networking; never use a production connection string.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import com.mongodb.client.model.Sorts;

import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.Date;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderRepositoryIT {
    private MongoClient client;
    private MongoDatabase database;
    private MongoCollection<Document> orders;
    private String databaseName;

    @BeforeEach
    void setUp() {
        String uri = System.getenv(
            "MONGODB_TEST_URI"
        );

        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                "MONGODB_TEST_URI must point to a test DB"
            );
        }

        // Test infrastructure must additionally ensure
        // deployment identity and restricted credentials.
        databaseName = "it_orders_" +
            UUID.randomUUID().toString()
                .replace("-", "");

        client = MongoClients.create(uri);
        database = client.getDatabase(databaseName);
        orders = database.getCollection("orders");

        orders.createIndex(
            Indexes.compoundIndex(
                Indexes.ascending("tenantId"),
                Indexes.ascending("externalId")
            ),
            new IndexOptions().unique(true)
        );

        orders.insertMany(List.of(
            order("o-001", "tenant-a", "EXT-001",
                  "PAID", 150000L,
                  "2026-01-15T08:00:00Z"),
            order("o-002", "tenant-a", "EXT-002",
                  "PENDING", 90000L,
                  "2026-01-15T09:00:00Z"),
            order("o-003", "tenant-b", "EXT-001",
                  "PAID", 200000L,
                  "2026-01-15T10:00:00Z")
        ));
    }

    static Document order(
        String id,
        String tenant,
        String externalId,
        String status,
        long totalMinor,
        String createdAt
    ) {
        return new Document("_id", id)
            .append("tenantId", tenant)
            .append("externalId", externalId)
            .append("status", status)
            .append("totalMinor", totalMinor)
            .append(
                "createdAt",
                Date.from(
                    Instant.parse(createdAt)
                )
            );
    }

    @Test
    void returnsOnlyPaidOrdersFromTenantA() {
        List<Document> actual = orders.find(
            Filters.and(
                Filters.eq("tenantId", "tenant-a"),
                Filters.eq("status", "PAID")
            )
        ).sort(
            Sorts.ascending("_id")
        ).into(
            new ArrayList<>()
        );

        List<String> actualIds = actual.stream()
            .map(doc -> doc.getString("_id"))
            .toList();

        assertEquals(
            List.of("o-001"),
            actualIds
        );
    }

    @AfterEach
    void tearDown() {
        try {
            if (database != null) {
                // Drop only the database this test owns.
                database.drop();
            }
        } finally {
            if (client != null) {
                client.close();
            }
        }
    }
}
~~~

### 16.1. Safety Is a Prerequisite

**MONGODB_TEST_URI** must target a test deployment protected by proper networking and credentials. A random database prefix alone is not enough to protect production.

### 16.2. Why Use a UUID?

Each test method execution receives its own database so concurrent or repeated runs never collide. IDs and dates inside remain fixed.

### 16.3. Why Create the Index Before Inserting?

The unique index is an application precondition. If seed data violates uniqueness, the insert fails immediately and clearly.

### 16.4. Java Version

`Stream.toList()` requires a compatible Java version, such as JDK 17. On older Java versions, use `Collectors.toList()`.

### 16.5. Real Tests Must Call the Repository

The example above illustrates the MongoDB operation. When testing a real repository method, replace the `actual` query with **repository.findPaidByTenant("tenant-a")**, keeping `expectedIds` independent.

## 17. Example of a Negative Test

Within the same class, this test gets its own fresh setup via `@BeforeEach`:

~~~java
@Test
void cannotSeePaidOrderOfAnotherTenant() {
    List<String> ids = orders.find(
        Filters.and(
            Filters.eq("tenantId", "tenant-a"),
            Filters.eq("status", "PAID")
        )
    ).sort(
        Sorts.ascending("_id")
    ).map(
        d -> d.getString("_id")
    ).into(new ArrayList<>());

    assertEquals(
        List.of("o-001"),
        ids
    );
}
~~~

### 17.1. Negative Controls Are Mandatory

If `o-003` belonging to `tenant-b` were omitted from the fixture, a query lacking the tenant filter would still pass.

### 17.2. Assert the Entire Result

Never assert only that `o-001` is contained; a query that also returns `o-003` is a security bug.

### 17.3. Never Repeat the Implementation as Expected Logic

Expected values come from known fixture records. When testing a real repository, Act must not re-implement the query under test.

## 18. Testcontainers Provisioning Disposable MongoDB

Testcontainers can provide a dedicated MongoDB process per suite or class. The snippet below is illustrative; exact module coordinates, Java class names, and APIs must match your project's Testcontainers version.

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.containers.MongoDBContainer;

@Testcontainers
class MongoContainerIT {
    @Container
    static MongoDBContainer mongo =
        new MongoDBContainer(
            "mongo:PIN_A_SUPPORTED_TEST_VERSION"
        );

    @Test
    void usesDisposableMongo() {
        String uri = mongo.getReplicaSetUrl();

        // Open MongoClient for the test server,
        // create an isolated database, seed and test.
    }
}
~~~

### 18.1. Avoid "latest" When Reproducibility Matters

Pin the MongoDB server image tag as well as the Java driver and Testcontainers module versions.

### 18.2. Simulation Boundaries

A MongoDB container suits most integration tests; it does not automatically simulate full Atlas, sharded clusters, cross-region failover, or production networking.

### 18.3. Shared Container, Isolated State

A MongoDB container can be reused across a suite to cut startup cost, while still creating a separate database per mutating test.

### 18.4. Readiness

Let the container/framework wait until the server is genuinely ready instead of sleeping a fixed number of seconds.

## 19. Pinning Versions and Topology

A reproducible test environment should record:

~~~text
JDK: pinned compatible release
MongoDB Java Sync Driver: pinned release
MongoDB server/image: pinned release
Testcontainers module: pinned release
Topology: standalone or replica set
Feature Compatibility Version: recorded if relevant
Deployment settings: recorded if relevant
~~~

### 19.1. Transactions Do Not Run on Every Topology

Multi-document transactions require a supported replica set or sharded cluster; a standalone server may reject them.

### 19.2. Change Streams Have Topology Requirements

A Change Stream integration test should not run on a standalone deployment if the server/topology does not support it.

### 19.3. Matrix Tests

Suites can run against current and target server versions, provided each run records the exact version used so behavior differences are not mistaken for fixture bugs.

## 20. Schema Validation Belongs in the Fixture

If production enforces a MongoDB JSON Schema validator, integration tests should set up the corresponding validator.

Lab example:

~~~javascript
db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "tenantId",
        "externalId",
        "status"
      ],
      properties: {
        tenantId: {
          bsonType: "string"
        },
        externalId: {
          bsonType: "string"
        },
        status: {
          enum: ["PENDING", "PAID", "CANCELLED"]
        }
      }
    }
  }
});
~~~

### 20.1. Valid Baseline Fixture and Invalid Test Cases

Do not place invalid documents into the shared baseline if seeding will fail. In a “reject missing tenant” test, attempt inserting the invalid document during Act and assert the validation error.

### 20.2. Never Disable Validators Just to Pass Tests

If the system relies on a validator, turning it off in integration tests hides real bugs.

### 20.3. Collection Options

Collation, TTL, time-series/capped options, or view definitions can also be preconditions for the behavior under test.

## 21. Null, Missing, and BSON Types

MongoDB distinguishes:

~~~javascript
{ _id: "null", discount: null }
{ _id: "missing" }
{ _id: "zero", discount: 0 }
{ _id: "string", discount: "0" }
~~~

### 21.1. eq(null)

MongoDB equality with `null` matches both null fields and missing fields. Fixtures need both so you know the code handles those semantics properly.

### 21.2. exists(false)

Commonly used to select missing fields, distinct from explicit `null`.

### 21.3. Numeric Types

Integer, Long, Double, and Decimal128 each have distinct serialization and precision semantics. Never seed prices as Strings if production stores BSON numeric types.

### 21.4. BSON Date

A string `"2026-01-15T10:00:00Z"` is not the same as a BSON Date for that instant. Date-range query tests must use proper `Date`/`Instant` mapping.

### 21.5. Unicode

If the domain handles Vietnamese text, add a few accented fixtures to test collation and normalization; a large corpus is unnecessary for standard CRUD checks.

## 22. Nested Arrays and $elemMatch

Two-element fixture:

~~~javascript
{
  _id: "order-array-001",
  items: [
    { sku: "BOOK-001", qty: 1 },
    { sku: "BOOK-002", qty: 3 }
  ]
}
~~~

Query requiring the same element to have `sku` `BOOK-001` and `qty >= 2`:

~~~javascript
{
  items: {
    $elemMatch: {
      sku: "BOOK-001",
      qty: { $gte: 2 }
    }
  }
}
~~~

**Does not match**, because `BOOK-001` only has `qty=1`.

### 22.1. A Fixture That Catches a Common Bug

Two separate dot-path predicates can match across different array elements. Two items suffice to distinguish a buggy query from a proper `$elemMatch`.

### 22.2. Long Arrays Are Unnecessary

If the test checks same-element semantics, a 100-item array hurts readability without adding meaningful coverage.

### 22.3. Nested Java Objects Must Be Independent

A static `List<Document>` shared across fixtures can be mutated in Test A, altering Test B's state. Always return a fresh `List`/`Document` or deep copy.

## 23. Pagination Fixture with Tie-Breaker

~~~javascript
[
  {
    _id: "o-101",
    tenantId: "tenant-a",
    createdAt: ISODate("2026-01-15T10:00:00Z")
  },
  {
    _id: "o-102",
    tenantId: "tenant-a",
    createdAt: ISODate("2026-01-15T10:00:00Z")
  },
  {
    _id: "o-103",
    tenantId: "tenant-a",
    createdAt: ISODate("2026-01-14T10:00:00Z")
  }
]
~~~

Sorting `createdAt` descending then `_id` descending yields: **o-102, o-101, o-103**.

### 23.1. Why Duplicate `createdAt`?

Without a tie, the test will not catch code missing an `_id` tie-breaker.

### 23.2. Keyset Pagination

With page size 2: page 1 returns `o-102`/`o-101`; cursor at `o-101`, next page returns `o-103`.

### 23.3. Concurrent Updates Are a Separate Test

Static pagination fixtures test the pagination algorithm. Testing inserts occurring mid-pagination belongs in a dedicated case with explicit concurrency requirements.

## 24. Fixed Time Is No Magic Bullet for TTL

The MongoDB TTL monitor runs asynchronously and uses the server clock.

### 24.1. TTL Can Delete Fixture Data Unexpectedly

If a document has `expiresAt` in the past and a TTL index is active, the record may vanish between Arrange and Assert.

### 24.2. Never Test TTL with sleep(1000)

MongoDB does not guarantee deletion at the exact 1-second mark. Use bounded polling until the condition holds or times out.

### 24.3. Test TTL in Isolation

Never seed expired documents into the shared fixture used by all repository tests. Use a dedicated collection/database for TTL tests.

### 24.4. `Clock.fixed` Does Not Freeze the Server Clock

Injecting a fixed `Clock` in Java controls application time, not the clock `mongod` uses for TTL expiration.

## 25. Eventual Consistency and Bounded Polling

Systems with Change Streams, background consumers, or asynchronously updated search indexes require deadline-bounded tests.

~~~text
deadline = now + timeout
repeat:
  observe condition
  if expected: PASS
  if deadline elapsed: FAIL with diagnostic
  wait a bounded interval
~~~

### 25.1. Avoid Long Fixed Sleeps

Sleeping 10 seconds in every test slows the suite down, while sleeping 200 ms causes flakiness in CI. Poll the actual condition instead.

### 25.2. Explicit Timeouts

Never wait indefinitely; on failure, log expected vs observed state and elapsed duration.

### 25.3. Consistency Contract

If behavior is eventual, do not assert immediate consistency; if behavior is synchronous, do not hide bugs behind polling.

## 26. Change Stream Fixture

Example contract:

~~~text
Given:
  Test collection is empty
  Consumer has subscribed and is ready
  Event identity is known

When:
  Update one known document

Then:
  A corresponding change event is observed
  Event identifies the expected document
  No unrelated tenant data is exposed
~~~

### 26.1. Resume Tokens Are Not Arbitrarily Portable

Do not hardcode a resume token from another cluster and expect it to work. Tokens are tied to the stream, history, and topology per MongoDB semantics.

### 26.2. Assert Business Invariants

If event processing follows at-least-once semantics, tests may need to assert final state and idempotency rather than demanding the callback fires strictly once.

### 26.3. Do Not Rely on Cross-Consumer Ordering

Across multiple workers or partitions, global ordering may not be part of the contract. Assert by event ID and true causal relationships.

## 27. Minimal Concurrency Fixture

Testing atomic `$inc` may need only a single counter document:

~~~javascript
{
  _id: "counter-001",
  value: 0
}
~~~

After N successful atomic increments, expected `value=N`.

### 27.1. Coordinated Concurrent Start

Use `CountDownLatch`/`CyclicBarrier` so multiple workers start together instead of running sequentially.

### 27.2. Assert Final State, Not Thread Order

You cannot guarantee Thread 1 finishes before Thread 2. What matters is that every increment persists and the final value is exact.

### 27.3. Worker Cleanup

Wait for all futures to finish or cancel/shut down the executor before dropping the test database.

### 27.4. Passing Once Does Not Prove Every Interleaving

You can run multiple seeds or stress suites, yet the fixture data and invariant should remain small and clear.

## 28. Java Concurrency Test Sketch

This helper assumes a `MongoCollection` inside an isolated test database without an existing `counter-001`.

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

public static void verifyAtomicCounter(
    MongoCollection<Document> collection
) throws Exception {
    collection.insertOne(
        new Document("_id", "counter-001")
            .append("value", 0)
    );

    int workers = 8;
    ExecutorService pool =
        Executors.newFixedThreadPool(workers);

    CountDownLatch ready =
        new CountDownLatch(workers);

    CountDownLatch start =
        new CountDownLatch(1);

    List<Future<?>> futures =
        new ArrayList<>();

    try {
        for (int i = 0; i < workers; i++) {
            futures.add(pool.submit(() -> {
                ready.countDown();
                if (!start.await(
                    5, TimeUnit.SECONDS
                )) {
                    throw new IllegalStateException(
                        "Start timed out"
                    );
                }

                collection.updateOne(
                    Filters.eq("_id", "counter-001"),
                    Updates.inc("value", 1)
                );
                return null;
            }));
        }

        if (!ready.await(
            5, TimeUnit.SECONDS
        )) {
            throw new IllegalStateException(
                "Workers not ready"
            );
        }

        start.countDown();

        for (Future<?> future : futures) {
            future.get(10, TimeUnit.SECONDS);
        }

        Document doc = collection.find(
            Filters.eq("_id", "counter-001")
        ).first();

        assertEquals(
            workers,
            doc.getInteger("value")
        );
    } finally {
        start.countDown();
        pool.shutdownNow();
    }
}
~~~

### 28.1. Shared Client Across Threads

`MongoClient` and `MongoCollection` in the Java Sync Driver are thread-safe and designed for reuse; do not create a separate client per worker.

### 28.2. Bounded Test Timeouts

The ready latch, futures, and executor all have bounded waits and cleanup. Never let CI hang indefinitely.

### 28.3. Per-Test Fixtures

Two tests both using `counter-001` in separate databases will never collide.

## 29. Optimistic Locking with Version

One document suffices:

~~~javascript
{
  _id: "product-001",
  tenantId: "tenant-a",
  version: 5,
  stock: 10
}
~~~

Two updates filtering on `version=5`:

~~~java
Bson filter = Filters.and(
    Filters.eq("_id", "product-001"),
    Filters.eq("tenantId", "tenant-a"),
    Filters.eq("version", 5)
);

Bson update = Updates.combine(
    Updates.set("stock", 9),
    Updates.inc("version", 1)
);
~~~

### 29.1. Expected State

When executed twice sequentially:

- First update: `matchedCount=1`.
- Second update: `matchedCount=0`.
- Final `version` is `6`.
- Final `stock` is `9`.

### 29.2. Do Not Reuse Data from a Prior Test

If `version` is already `6` from another test, the case no longer tests `expectedVersion=5` as intended.

### 29.3. Assert Persistence

Do not merely assert the API returned a conflict; re-read the document and verify `version` and `stock` did not change again.

## 30. Transaction Fixtures and Topology

Fixture for an order-creation / stock-deduction test:

~~~text
products:
  product-001 available=2

orders:
  empty

On success:
  decrement available by 1
  insert order-001
  commit
  -> available=1, order exists

On failure:
  abort
  -> available=2, order absent
~~~

### 30.1. Topology Must Support Transactions

Multi-document transactions require a suitable deployment/topology; do not assume a standalone `mongod` supports them like a replica set.

### 30.2. Do Not Wrap Every Test in a Transaction as General Cleanup

DDL, index builds, background consumers, or service code opening its own session may bypass the test transaction. Per-test namespaces are clearer in most integration tests.

### 30.3. External Side Effects

MongoDB transactions do not automatically roll back emails or payments. Tests need sandboxes or fake integrations and must check idempotency/outbox behavior.

### 30.4. Separate Abort Case

An abort test needs a fresh fixture with `available=2`. Never run it after the success case and expect stock to remain `2`.

## 31. Upsert and Unique Index Fixture

Fixture:

~~~text
products:
  p-001 tenant-a sku=BOOK-001

Unique index:
  (tenantId, sku)

Test A:
  upsert tenant-a/BOOK-001
  -> existing p-001 updated

Test B:
  upsert tenant-a/BOOK-002
  -> new document inserted

Test C:
  insert duplicate tenant-a/BOOK-001
  -> duplicate key rejected

Test D:
  insert tenant-b/BOOK-001
  -> allowed
~~~

### 31.1. Test Both Insert and Update Branches of Upsert

Checking `upsertedId` alone is insufficient for the matched-existing branch. Verify document count, state, and `createdAt` semantics.

### 31.2. Race Conditions

When multiple writers upsert the same key concurrently, the unique index enforces uniqueness; the application must handle duplicate key errors according to its contract.

### 31.3. Seeding Should Not Blindly Upsert Everything

Use upsert when upsert is the behavior under test. When setting up a clean DB, inserting fixed documents exposes fixture bugs more clearly.

## 32. Soft-Delete Fixture

~~~javascript
[
  {
    _id: "p-live",
    tenantId: "tenant-a",
    name: "Live"
  },
  {
    _id: "p-deleted",
    tenantId: "tenant-a",
    name: "Deleted",
    deletedAt: ISODate("2026-01-01T00:00:00Z")
  },
  {
    _id: "p-other",
    tenantId: "tenant-b",
    name: "Other"
  }
]
~~~

### 32.1. Expected

Querying visible products for `tenant-a` returns only `p-live`.

### 32.2. Missing/Null Conventions

If active records omit `deletedAt`, the fixture reflects missing. If the design uses `deletedAt: null`, adjust the test to match that schema.

### 32.3. Avoid Accidental TTL Activation

A soft-delete visibility test should not rely on TTL deleting documents by wall-clock time; test TTL separately.

## 33. Fixtures for Joins and $lookup

When a repository uses an aggregation lookup:

~~~text
customers:
  c-001 tenant-a name=Alice
  c-002 tenant-a name=Bob

orders:
  o-001 tenant-a customerId=c-001
  o-002 tenant-a customerId=c-002
  o-003 tenant-a customerId=c-missing
~~~

### 33.1. Deliberate Orphan Record

Document `o-003` verifies behavior when a referenced record is missing.

### 33.2. Keep Only Necessary Fields

If the pipeline only needs `customerId` and `name`, omit lengthy customer profiles from the fixture.

### 33.3. Tenant-Aware Joins

If business keys can collide across tenants, add a `tenant-b` record as a negative control to catch unscoped lookups.

## 34. Fixtures for Business Invariants

Stock reservation example:

~~~text
Given:
  Product available=2

When:
  Request quantity=3

Then:
  Reservation rejected
  Product available remains 2
  No confirmed order inserted
~~~

Success case:

~~~text
Given:
  Product available=2

When:
  Request quantity=2

Then:
  Reservation accepted
  Available becomes 0
  One expected order inserted
~~~

### 34.1. Assert Database State After Action

A service might throw the expected exception yet still leave a partial write behind. Verify persisted state.

### 34.2. Independent Setup Per Case

Never reuse `remaining stock=0` from a success test as the precondition for a failure test.

### 34.3. Multiple Documents

If a business operation updates multiple documents, assertions must verify all invariants and transaction/compensation semantics.

## 35. Fixtures for Idempotency

~~~text
Before:
  operationId = reserve-001
  available = 5
  no reservation

Act:
  Call reserve(operationId, qty=2) twice

Expected:
  One logical reservation
  available = 3
  Both responses satisfy idempotency contract
~~~

### 35.1. Same Operation ID for Retries

Generating a new operation ID on each call fails to test duplicate suppression.

### 35.2. Can Be Tested Concurrently

Send two requests with the same `operationId` concurrently and assert final state/invariants without depending on which request wins.

### 35.3. Outbox and External Effects

If reservation emits an outbox event, fixtures and assertions must verify no duplicate logical side effects occur per contract.

## 36. File Fixtures: JSON, Extended JSON, and Java Code

Possible layout:

~~~text
src/test/resources/fixtures/
  orders-basic.json
  orders-null-missing.json
  products-stock.json
  aggregation-join.json
~~~

### 36.1. Java Code

Ideal for small fixtures with reusable factories, fixed `Clock`, and explicit BSON types.

### 36.2. JSON

Good for fixtures with many records or fields that readers inspect directly.

### 36.3. Extended JSON

Plain JSON loses BSON type fidelity for `ObjectId`, `Date`, `Decimal128`, and `Binary`. Use Extended JSON or codecs when type fidelity matters.

### 36.4. Avoid a Single Mega Fixture

One giant shared file couples every test to unrelated data and makes schema evolution painful.

### 36.5. Version Fixtures Alongside Code

Fixtures are test artifacts that should be reviewed alongside repository and schema migrations. Never pull live runtime data and treat it as a stable fixture.

## 37. Why Never Use Production Data Directly?

- Contains PII, secrets, or sensitive business data.
- May violate retention and access policies.
- Mutating data makes expected outputs non-deterministic.
- Risks leaking data into CI logs and artifacts.
- Makes tests slow and hard to minimize on failure.

### 37.1. Synthetic Fixtures

Prefer deliberately crafted fake names, IDs, emails, and amounts.

### 37.2. If Production-Like Data Is Necessary

Follow an approved extraction and anonymization pipeline with controlled access and lifecycle management. Never copy raw backups into a test repository.

### 37.3. Even Small Data Can Be Sensitive

A single document holding a real email address or token is still a security risk.

## 38. Cleanup with Clear Ownership

~~~text
Test owns:
  Database it_orders_<unique>
  Its collections, indexes and docs

Test teardown:
  Stop test-owned background workers
  Close cursors and sessions
  Drop only it_orders_<unique>
  Close owned client
~~~

### 38.1. Partial Setup Failure

If `MongoClient` was created before database setup failed, teardown must still close the client without attempting to drop an uninitialized database.

### 38.2. Cleanup Failure Is Also a Failure

Do not silently swallow all exceptions in teardown. If a namespace cannot be dropped, log it clearly so CI/retention processes can handle it.

### 38.3. Stop Workers Before Cleanup

If an executor keeps running after `database.drop()`, workers can recreate documents or fail unpredictably.

### 38.4. Jobs Killed Before Teardown

A cancelled CI job may skip `@AfterEach`. Disposable containers, namespace TTLs, and ownership-based cleanup handle leftovers.

## 39. Preventing Tests from Accidentally Writing to Production

At minimum:

1. Use a dedicated **MONGODB_TEST_URI** variable with no fallback to `MONGODB_URI`.
2. Keep test deployments in a separate network/project.
3. Ensure test credentials have zero privileges in production.
4. Verify deployment identity/control plane.
5. Give test database names a clear prefix.
6. Drop only namespaces created by the test.
7. Require explicit approval for destructive commands.
8. Never run test seeds with production CI secrets.
9. Maintain observability/auditing for bulk data operations.

### 39.1. Localhost Is Not Automatically Safe

A port-forward or tunnel can point to production. Never infer environment safety from the hostname alone.

### 39.2. Prefixing Alone Is Not Enough

Even if a database is named `it_test`, if the URI points to production with broad credentials, `dropDatabase` remains dangerous.

### 39.3. Never Drop Just to Debug an Error

If the target environment is uncertain, halt and verify the connection rather than attempting to drop collections or databases.

## 40. CI Workflow

~~~text
Checkout + build
     |
     v
Start pinned MongoDB test deployment
     |
     v
Wait for readiness, not fixed sleep
     |
     v
Run tests with isolated fixtures
     |
     v
Collect sanitized diagnostics
     |
     v
Cleanup owned resources
~~~

### 40.1. Pin Dependency Versions

Different server, driver, or Testcontainers versions can alter behavior. Record exact versions for every CI run.

### 40.2. Parallel Jobs

Use distinct namespaces per test/job. Never share one collection and wipe each other's data.

### 40.3. Re-Run and Reorder

A trustworthy suite passes when run individually, repeatedly, or in randomized execution order.

### 40.4. Investigate Intermittent Failures

A flaky test often signals a data race or missing isolation. Passing on a second retry does not mean the root cause is gone.

## 41. Correctness Fixtures vs Performance Datasets

| Purpose | Size | Primary requirement |
| --- | --- | --- |
| Unit | No real MongoDB needed | Pure logic |
| Integration CRUD | A few documents | Exact assertions |
| Unique index | 2-4 documents | Constraint correctness |
| Array matching | 1-2 documents | Semantics |
| Concurrency | 1-3 documents + many writes | Invariants |
| Transaction | Few documents across collections | Atomicity |
| TTL/Change Stream | Few documents and async events | Eventual behavior |
| Load/performance | Large representative data | P95/throughput |
| DR/failover | Topology, backups | Recovery behavior |

### 41.1. Never Infer Production Query Speed from Small Data

With three documents, the server may quite reasonably choose a `COLLSCAN`. Index performance must be measured separately on a sufficiently representative dataset.

### 41.2. Do Not Put Performance Volumes into Every Correctness Test

Doing so slows down the suite, wastes CI resources, and complicates debugging.

## 42. Workflow for Designing a Fixture from a Requirement

Requirement: “Users can view only PAID orders of their own tenant, sorted by newest createdAt.”

### Step 1 — Express Behavior

~~~text
Given orders from two tenants and multiple statuses
When finding paid orders for tenant-a
Then return only tenant-a paid orders
And order by createdAt descending, _id descending
~~~

### Step 2 — Choose Minimal Records

~~~text
o-001 tenant-a PAID    10:00
o-002 tenant-a PAID    10:00
o-003 tenant-a PENDING 11:00
o-004 tenant-b PAID    12:00
~~~

### Step 3 — Fix Data Types

String IDs, UTC BSON Dates, valid status strings.

### Step 4 — Predict Expected Result

By `createdAt` desc, `_id` desc: **o-002, o-001**.

### Step 5 — Independent Setup

Create a dedicated database, indexes, and seed the four documents.

### Step 6 — Call the Method Under Test

Invoke `repository.findPaidByTenant("tenant-a")` or the corresponding public service API.

### Step 7 — Assert the Complete Result

Compare exact ordered IDs and critical fields.

### Step 8 — Cleanup

Drop only the owned database and close resources.

## 43. Detecting State Leakage

Proactive ways to uncover fixture bugs:

- Run a single test alone.
- Run a test twice consecutively.
- Shuffle test method and class order.
- Run in parallel.
- Run against a completely empty test environment.
- Intentionally make a preceding test fail midway and verify the next test stays independent.
- Monitor remaining databases/containers after runs.
- Compare outputs across multiple CI runs with identical versions and seeds.

### 43.1. Reproducibility Report

Record test name, code revision, fixture version, seed, fixed Clock, driver/server versions, namespace, and sanitized failure details.

### 43.2. Never Add Sleep to Mask Races

Sleeps slow tests down and merely shift timing failures. Use proper setup isolation or bounded behavioral waiting.

### 43.3. Minimize Fixtures on Test Failure

If a bug only reproduces with 100 random documents, shrink it to a minimal counterexample and turn it into a deterministic regression fixture.

## 44. Sample Log on Test Failure

~~~text
test: OrderRepositoryIT.returnsPaidTenantOrders
fixture: orders-basic-v1
serverVersion: pinned-test-release
driverVersion: pinned-driver-release
namespace: it_orders_<run-id>
clockUtc: 2026-01-15T10:00:00Z
seed: none
expectedIds: [o-001]
actualIds: [o-001, o-003]
result: FAIL
~~~

### 44.1. Logs Sufficient to Reproduce

Expected/actual IDs plus environment context separate query bugs from server version mismatches or state leakage.

### 44.2. Never Log Credentials or PII

Use synthetic IDs and strip passwords, tokens, and raw customer details from test artifacts.

### 44.3. Diagnostic Ordering

Sort IDs/fields in failure reports when order is irrelevant to reduce diff noise across runs.

## 45. Common Mistakes

| Mistake | Consequence | Improvement |
| --- | --- | --- |
| Fixture with thousands of unused documents | Slow, hard to understand | Minimal counterexamples |
| Happy path only | Buggy queries still pass | Negative controls |
| `new Date()` in expected values | Time flakiness | Fixed `Clock` |
| Unseeded Random | Non-reproducible | Fixed seed / log seed |
| Hardcoded assertions against auto-generated ObjectId | Mismatch | Fixed ID / assert properties |
| Unsorted `find` | Order-dependent | Explicit sort |
| String instead of BSON Date in fixture | Wrong range behavior | Accurate BSON types |
| Static mutable Document | Cross-test mutation | Fresh factories |
| Test B depends on Test A | Order-dependent | Per-test Arrange |
| Shared database | Parallel collisions | Unique namespaces |
| Cleaning the whole shared DB | Deletes other tests' data | Drop owned DB only |
| Unique index omitted from setup | False pass | Include index in fixture |
| Validator omitted from setup | Invalid writes slip through | Relevant schema setup |
| Plain JSON representing ObjectId as string | Type mismatch | Extended JSON / codecs |
| Computing expected output with implementation query | Shared bug | Independent oracle |
| Fixed sleep for TTL tests | Flaky | Bounded polling |
| Change Stream tests on wrong topology | Unsupported error | Supported replica set |
| Asserting thread execution order | Flaky | Final invariants |
| Not joining workers before cleanup | Background races | Join/cancel first |
| Transactions on standalone | Feature error | Correct topology |
| Container tag `latest` | Version drift | Pin versions |
| Raw production fixtures | Privacy risk | Synthetic/anonymized data |
| Test URI falling back to production | Data loss risk | Restricted test deployment |
| Setup fails, teardown skips cleanup | Leaked resources | Defensive teardown |
| CI kill leaves DB behind | Resource leak | Disposable infra / TTL |
| Drawing performance conclusions from tiny fixtures | Invalid evidence | Separate load suite |

## 46. Minimal Fixture Exercises

### Exercise 1 — Tenant Filter

Design three orders to catch both bugs: missing `tenantId` filter and missing `status` filter. Write the exact expected result.

### Exercise 2 — Range Boundary

Filter `price >= 100` and `price < 200`. Pick the minimal set of prices distinguishing `gt`/`gte` and `lt`/`lte`.

### Exercise 3 — Unique Business Key

Design a fixture proving `unique(tenantId, externalId)` blocks duplicates within a tenant while allowing duplicates across tenants.

### Exercise 4 — Null/Missing

Create four documents for field `discount`: `null`, missing, `0`, `"0"`. Predict `eq(null)` and `exists(false)`.

### Exercise 5 — Arrays

Construct an `items` array where two dot-path predicates match yet `$elemMatch` does not match.

### Exercise 6 — Pagination

Given two orders with identical `createdAt`, design the expected order when sorting `createdAt` desc, `_id` desc.

## 47. Determinism Exercises

### Exercise 7 — Fixed Clock

Replace `Instant.now()` in a service with an injectable `Clock` and test with a fixed timestamp.

### Exercise 8 — Random Seed

An unseeded `Random()` generator fails in CI. Capture the seed, reproduce the failure, and shrink the fixture to a minimal example.

### Exercise 9 — ObjectId

When should you use a fixed `ObjectId`, and when should you only assert non-null/uniqueness?

### Exercise 10 — BSON Types

Explain why an ISO string and a BSON Date are not interchangeable in range query tests.

### Exercise 11 — Sorting

A test asserts on the first element returned by an unsorted `find`. Fix it to produce stable results.

### Exercise 12 — Mutable Fixtures

Two tests share a static `Document` containing a nested `List`. Identify the bug and fix the factory.

## 48. Isolation and CI Exercises

### Exercise 13 — Test Order

Test A creates `o-001`, and Test B reads `o-001`. Rewrite so Test B can run completely on its own.

### Exercise 14 — Parallelism

Two tests both use `_id=o-001`. Design per-test database names and cleanup.

### Exercise 15 — Setup Failure

`@BeforeEach` created `MongoClient` but `createIndex` failed. How should `@AfterEach` handle cleanup?

### Exercise 16 — Production Safety

`MONGODB_TEST_URI` accidentally points to production. Beyond an `it_` database prefix, what layers of defense prevent destructive tests?

### Exercise 17 — Testcontainers

Design a CI job that pins a MongoDB image, waits for readiness, seeds, runs tests, and cleans up.

### Exercise 18 — Leaked DBs

A CI job is killed and skips teardown. How can leftover databases be detected and safely cleaned up by ownership?

## 49. Concurrency and Asynchronous Behavior Exercises

### Exercise 19 — TTL

Design a TTL test using bounded polling instead of a fixed sleep.

### Exercise 20 — Change Streams

A change event may arrive with delay. How do you assert using event IDs and a deadline?

### Exercise 21 — Atomic `$inc`

Start with `counter=0` and run 100 concurrent increments. What is the expected state, and how are latches/futures used?

### Exercise 22 — Optimistic Locking

Two updates filter on `version=5`. What are the expected final state, `matchedCount`, and `version`?

### Exercise 23 — Transactions

Using one product and one order, design independent commit and abort test cases.

### Exercise 24 — Idempotency

Call `reserve` twice with the same `operationId`, and verify stock, reservation, and outbox do not double-count.

### Exercise 25 — Performance

Why is a three-document fixture insufficient to prove an index suits 1 million orders? Which test suite is required instead?

## 50. MongoDB Fixture Design Checklist

### Small and Focused

1. Every record serves an assertion or negative control.
2. No unrelated fields are kept.
3. Edge cases and boundaries are included to distinguish bugs.
4. Each scenario is separated into its own small fixture.
5. Expected results are independent of the implementation.

### Deterministic

6. Fixed IDs for values requiring exact comparisons.
7. Fixed UTC timestamps and an injected `Clock` where appropriate.
8. Randomness is seeded or eliminated.
9. No reliance on MongoDB natural order.
10. Explicit sort and tie-breakers when order matters.
11. BSON types are strictly controlled.
12. Server, driver, and container versions are recorded.
13. TTL and Change Streams use eventual assertions with timeouts.
14. Concurrency tests assert invariants, not thread ordering.

### Independent

15. Each test sets up its own preconditions.
16. Zero dependence on test execution order.
17. Mutating tests use isolated namespaces.
18. Factories return fresh objects without shared mutable state.
19. Indexes and validators are part of setup.
20. Cleanup removes only test-owned resources.
21. Teardown handles partial setup failures safely.
22. Workers are joined/stopped before cleanup.
23. CI cleans up leaked resources when jobs are cancelled.
24. Tests still pass on re-runs and parallel runs.

### Safety and Operations

25. Dedicated URI and credentials for test deployments.
26. Test URI never falls back to production.
27. Never copy raw production PII into fixtures.
28. Never run `dropDatabase` outside authorized test namespaces.
29. Failure logs include seed, version, and expected vs actual.
30. Performance/load testing uses dedicated datasets and suites.

## 51. Runbook Applied to Every Integration Test

~~~text
INPUT:
  Behavior under test
  Small document set
  Required indexes/validators
  Fixed IDs/Clock/seed
  Expected exact result/invariant

SETUP:
  Verify dedicated test environment
  Allocate unique namespace
  Create collection/index/schema
  Insert minimal fixture

ACT:
  Call real repository/service method

ASSERT:
  Exact IDs/values and order
  Negative controls excluded
  Persisted business invariants
  Expected error type/code if failure case

CLEANUP:
  Stop background tasks
  Close sessions/cursors
  Drop owned namespace only
  Release resources

REPORT:
  Test ID and fixture version
  Server/driver version
  Seed/Clock
  Expected vs actual
  Sanitized diagnostics
~~~

## 52. Conclusion

A good MongoDB fixture is more than “a bit of data so the test runs.” It is an **explicit precondition contract** that makes every assertion meaningful.

- **Minimal:** includes sufficient positive, negative, and boundary examples without excess noise.
- **Deterministic:** IDs, timestamps, random seeds, BSON types, and result ordering are controlled.
- **Independent:** each test creates its own state and cleans up its own resources without depending on other tests or prior runs.
- **MongoDB-specific:** unique indexes, validators, array semantics, transactions, TTL, Change Streams, and topology belong in setup whenever the behavior requires them.
- **Safe:** isolated test deployments, restricted credentials, and zero destructive commands against production.

Applied consistently, small, deterministic, and independent fixtures reduce flaky tests, shorten debugging time, and make repository and schema changes much safer. A failing test then points to a genuine bug in logic or verified preconditions rather than an unreproducible chain of side effects from other tests.

## References

- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [MongoDB Java Sync Driver — Query Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/)
- [MongoDB Java Sync Driver — Indexes](https://www.mongodb.com/docs/drivers/java/sync/current/indexes/)
- [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Testcontainers MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/)
