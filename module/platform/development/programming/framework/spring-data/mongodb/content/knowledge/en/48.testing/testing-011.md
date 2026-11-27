# Testing `@Query`, Projections, Scrolling, and Aggregations

When building an order search API with **Spring Data MongoDB**, successfully calling `MongoRepository` or `MongoTemplate` only proves the code executes; it does not guarantee the query filters the right tenant, projections return the right fields, scrolling avoids duplicates or skipped rows, or aggregations compute the right totals. Such bugs often surface only with varied data, tied sort keys, missing optional fields, or multi-stage pipelines.

This lesson belongs to the **Testing** chapter and uses a single running example to test four mechanisms: **`@Query`, projections, scrolling, and aggregations**. The `SPRING_DATA_MONGODB` module covers connecting and mapping documents, operating on MongoDB via templates or repositories, queries/indexes/transactions/reactive access, and performance diagnostics; accordingly, this lesson emphasizes **integration tests against real MongoDB**, verifying mapped outputs, command observability, and data assumptions as datasets grow.

## 1. Which Layer Should Test What?

| Test level | Scope checked | What it catches | Limitations |
| --- | --- | --- | --- |
| Unit tests with fake/mock repositories | Business rules in services | Empty-result handling, authorization checks, DTO mapping | Does not prove JSON query syntax or MongoDB pipelines run properly |
| **Repository integration tests** | Repository/`MongoTemplate` + real MongoDB | `?0` binding, BSON mapping, field projections, sorting, scrolling, aggregations | Higher execution cost than unit tests |
| API integration tests | Security, controllers, services, repositories, and MongoDB | Tenant isolation, response DTOs, validation, pagination at HTTP boundaries | Requires booting web app and auth test setup |
| Performance tests | Queries, indexes, large datasets, concurrency | Latency, `explain`, index scans, memory usage in scrolling/aggregations | Does not replace data-correctness assertions |

**Recommendation:** use unit tests to guard service logic; use `@DataMongoTest` with a real test MongoDB to verify Spring Data MongoDB behavior. With Testcontainers, pin MongoDB and dependency versions in your project. The examples below use Spring Boot 3.x, compatible Spring Data MongoDB, JUnit 5, AssertJ, and Testcontainers; Testcontainers package names may differ across major versions, so use your project's dependency set.

### Minimal Requirements Matrix

| Mechanism | Positive cases | Edge cases or common bugs |
| --- | --- | --- |
| `@Query` | Returns expected status and tenant | Another tenant with same order ref, empty result, literals with special chars |
| Projection | Returns only required properties; exact BSON names | Missing fields, `@Field` mapping, hidden/default `_id` |
| Scrolling | Traverses entire set in deterministic order, each ID once | Multiple documents sharing sort key, missing tie-breaker, data changes between pages |
| Aggregation | `$match`/`$group`/`$project` return exact counts and sums | No matches, numeric types, misspelled field/stage, leaking another tenant's data |

## 2. Designing a Fixture That Exposes Bugs

Suppose the application stores multi-tenant orders in collection `test_orders`. Fields to test include `tenantId`, `status`, `amountCents`, and `createdAt`. Using **whole cents as `long`** avoids floating-point rounding noise in the example; if using `Decimal128` or `BigDecimal`, add dedicated conversion and precision tests.

```java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("test_orders")
public record OrderDocument(
        @Id String id,
        String tenantId,
        String externalRef,
        String status,
        long amountCents,
        Instant createdAt,
        String internalNote
) {}
```

Create data spanning **two tenants**, with five documents for tenant `alpha`. Tenant `beta` intentionally shares `externalRef` with `alpha` to catch missing tenant filters.

| `_id` | Tenant | External ref | Status | Amount (cents) | Timestamp |
| --- | --- | --- | --- | ---: | --- |
| `a-1` | alpha | INV-1 | PAID | 1,200 | 2026-01-01T00:00:01Z |
| `a-2` | alpha | INV-2 | NEW | 900 | 2026-01-01T00:00:02Z |
| `a-3` | alpha | INV-3 | PAID | 800 | 2026-01-01T00:00:03Z |
| `a-4` | alpha | INV-4 | PAID | 500 | 2026-01-01T00:00:04Z |
| `a-5` | alpha | INV-5 | NEW | 700 | 2026-01-01T00:00:05Z |
| `b-1` | beta | INV-1 | PAID | 9,900 | 2026-01-01T00:00:01Z |

From this fixture you can calculate by hand:

- `@Query` filtering `tenantId = alpha`, `status = PAID` must return exactly **3** IDs: `a-1`, `a-3`, `a-4`.
- Projection for tenant `alpha` must yield **5** items exposing only permitted DTO properties.
- Scrolling by `createdAt ASC, _id ASC` with page size 2 must return **2 + 2 + 1** documents in sequence.
- Aggregation of `PAID` orders for `alpha` must yield **3 orders, total 2,500 cents**; `beta`'s data must not be included.

Fixtures are far more effective when they intentionally include duplicate codes/names, null or missing optional fields, tied timestamps, and data from other tenants. Never create fixtures with only one tenant and one status, because broken queries can pass by coincidence.

## 3. Declaring Repository Methods Under Test

### 3.1. `@Query` Filtering Tenant and Status

`@Query` in Spring Data MongoDB accepts JSON-like filter expressions with positional parameter binding `?0`, `?1`, and corresponding binding mechanisms. Example:

```java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    @Query("{ 'tenantId': ?0, 'status': ?1 }")
    List<OrderDocument> findByTenantAndStatus(
            String tenantId, String status);
}
```

Parameters are handled by Spring Data's **binder**: never concatenate JSON strings from client input. Tenant filters must originate from the authenticated, authorized identity; repository tests only prove **the query includes the tenant filter**, not API/service authorization.

### 3.2. Projections for List Views

Projections should be tested at **two levels**: the returned object exposes only the expected getters, and the query sent to MongoDB requests only the appropriate fields when payload reduction is an objective.

```java
public interface OrderCard {
    String getExternalRef();
    String getStatus();
}
```

Add to `OrderRepository`:

```java
@Query(
    value = "{ 'tenantId': ?0 }",
    fields = "{ '_id': 1, 'externalRef': 1, 'status': 1 }"
)
List<OrderCard> findCards(String tenantId);
```

`OrderCard` is an **interface-based projection**. Getter names must match mapped properties or conversions. Returning an interface with two getters does not automatically prove the server returned fewer fields: here `fields` defines the projection in the MongoDB query. Even when an API needs a slim DTO, still strip internal fields in the service and never treat projections as an independent authorization boundary.

When a field is mapped under a different BSON name, for example:

```java
@Document("test_orders")
public record MappedOrder(
        @Id String id,
        @Field("external_ref") String externalRef
) {}
```

the actual BSON schema stores `external_ref` while Java uses `externalRef`; Spring Data mapping translates property paths via metadata when building queries/templates. Test actual queries and commands sent to the server, especially with custom aggregations, raw BSON, field aliases, or converters. In our main example, Java and BSON names match so the tests stay focused on `@Query` semantics.

### 3.3. Scrolling in Deterministic Order

Spring Data Commons provides `Window<T>` and `ScrollPosition`. On repositories supporting scrolling, declare a derived query limiting window size:

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

// Add inside OrderRepository:
Window<OrderDocument>
findFirst2ByTenantIdOrderByCreatedAtAscIdAsc(
        String tenantId, ScrollPosition position);
```

Here the sort includes `createdAt ASC` and `id ASC` to handle documents sharing the same timestamp. `id` is a unique tie-breaker; in MongoDB it maps to `_id`. **Keyset scrolling** requires the sort fields to be non-null and present in projected results. When combining projections with `Window<T>`, keep all sort keys and the ID; omitting them breaks cursor continuation.

Two scrolling modes differ:

- **Offset**: `ScrollPosition.offset()`; resumes by positional offset. Simple, though latency grows as offsets skip many rows and positions shift when data changes.
- **Keyset**: `ScrollPosition.keyset()`; next position is computed from the last item's sort keys. Well suited for deep traversal, provided sorting is deterministic, backed by a matching index, and keys are non-null.

### 3.4. Direct Aggregations in the Repository

`@Aggregation` lets you define pipeline stages in MongoDB syntax. Results map to a projection/DTO matching the fields emitted by the pipeline.

```java
import org.springframework.data.mongodb.repository.Aggregation;

public record PaidTotals(
        String tenantId,
        long orders,
        long cents
) {}

// Add inside OrderRepository:
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0, 'status': 'PAID' } }",
    "{ '$group': { '_id': '$tenantId', "
        + "'orders': { '$sum': 1 }, "
        + "'cents': { '$sum': '$amountCents' } } }",
    "{ '$project': { '_id': 0, 'tenantId': '$_id', "
        + "'orders': 1, 'cents': 1 } }"
})
List<PaidTotals> summarizePaid(String tenantId);
```

Add this method to `OrderRepository`; place the `PaidTotals` record in its own file or appropriate project type. This is an **aggregation pipeline** over `OrderDocument`'s collection. `$match` precedes `$group` to filter tenant and status before summing. In multi-tenant queries, omitting `tenantId` in `$match` is a severe bug even when totals appear plausible.

A group with zero matching documents returns an **empty list**, rather than synthesizing a row with `orders = 0` and `cents = 0`. If the API requires zeros, the service must handle the empty case explicitly.

## 4. Building Integration Tests with @DataMongoTest and Testcontainers

`@DataMongoTest` initializes the test slice for MongoDB repositories, `MongoTemplate`, and mapping. Paired with Testcontainers, tests run against a real MongoDB server, catching `@Query`, cursor, BSON conversion, and pipeline errors that mock repositories miss.

The example uses `MongoDBContainer` from Testcontainers 1.x. For Testcontainers 2.x, update imports and dependencies for your chosen version. Running it requires Docker or a Testcontainers-supported runtime. Pin a MongoDB image compatible with your application; `mongo:7.0` below is a reference test version.

```java
import java.time.Instant;
import java.util.List;

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

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
@Testcontainers
class OrderRepositoryIT {

    @Container
    static final MongoDBContainer MONGO =
            new MongoDBContainer(DockerImageName.parse("mongo:7.0"));

    @DynamicPropertySource
    static void mongoProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", MONGO::getReplicaSetUrl);
        registry.add("spring.data.mongodb.database",
                () -> "testing011");
    }

    @Autowired OrderRepository repository;
    @Autowired MongoTemplate mongoTemplate;

    private static Instant second(int second) {
        return Instant.parse(
                String.format("2026-01-01T00:00:%02dZ", second));
    }

    @BeforeEach
    void seedData() {
        repository.deleteAll();
        repository.saveAll(List.of(
            new OrderDocument("a-1", "alpha", "INV-1",
                    "PAID", 1200L, second(1), "note-a1"),
            new OrderDocument("a-2", "alpha", "INV-2",
                    "NEW", 900L, second(2), "note-a2"),
            new OrderDocument("a-3", "alpha", "INV-3",
                    "PAID", 800L, second(3), "note-a3"),
            new OrderDocument("a-4", "alpha", "INV-4",
                    "PAID", 500L, second(4), "note-a4"),
            new OrderDocument("a-5", "alpha", "INV-5",
                    "NEW", 700L, second(5), "note-a5"),
            new OrderDocument("b-1", "beta", "INV-1",
                    "PAID", 9900L, second(1), "note-b1")
        ));
    }

    // @Test methods from the following sections go here.
}
```

**Fixture explanation:** every test starts after `@BeforeEach` with deterministic data. `repository.deleteAll()` is appropriate for an **isolated test database**; never use such cleanup against production. If multiple test classes share a collection/database and run in parallel, `@BeforeEach` deletion can race; in that case give each suite its own collection/database, disable parallelism, or design isolated fixtures.

Never depend on test execution order. The IDs `a-1` through `b-1` are non-ObjectId strings, keeping assertions clear without relying on driver-generated IDs.

## 5. Testing @Query: Right Filters, Right Tenant Data

Add these two tests inside `OrderRepositoryIT`:

```java
@Test
void query_onlyReturnsPaidOrdersOfRequestedTenant() {
    List<OrderDocument> found =
            repository.findByTenantAndStatus("alpha", "PAID");

    assertThat(found).extracting(OrderDocument::id)
            .containsExactlyInAnyOrder("a-1", "a-3", "a-4");

    assertThat(found).allSatisfy(order -> {
        assertThat(order.tenantId()).isEqualTo("alpha");
        assertThat(order.status()).isEqualTo("PAID");
    });
}

@Test
void query_returnsEmptyInsteadOfLeakingOtherTenant() {
    assertThat(repository.findByTenantAndStatus(
            "alpha", "CANCELLED")).isEmpty();

    List<OrderDocument> beta =
            repository.findByTenantAndStatus("beta", "PAID");

    assertThat(beta).extracting(OrderDocument::id)
            .containsExactly("b-1");
}
```

These assertions verify **content and exact IDs**, rather than only `size() == 3`. If someone accidentally drops `tenantId` from `@Query`, the test catches it because `b-1` is also `PAID`.

Also add a binding test for inputs containing special characters:

```java
@Test
void query_bindsParameterAsValueRatherThanJsonFragment() {
    List<OrderDocument> found = repository.findByTenantAndStatus(
            "alpha", "PAID' }, { 'status': 'NEW");

    assertThat(found).isEmpty();
}
```

This verifies safe parameter binding on the tested query path. You still need API-level validation/authorization and must never grant tenant access based solely on client-supplied parameters.

### Unsorted Queries Must Not Assert Order

This `@Query` only filters (`$match`) without a `sort`; MongoDB **does not guarantee return ordering**. Hence the test uses `containsExactlyInAnyOrder(...)`. To assert ordering, add `Sort`, a sorted `Pageable`, or an explicit sort clause with a tie-breaker when needed.

## 6. Testing Projections: Returned Fields and Payload

Add the next test inside `OrderRepositoryIT`:

```java
@Test
void projection_returnsCardFieldsForTenant() {
    List<OrderCard> cards = repository.findCards("alpha");

    assertThat(cards).hasSize(5);
    assertThat(cards).extracting(OrderCard::getExternalRef)
            .containsExactlyInAnyOrder(
                    "INV-1", "INV-2", "INV-3", "INV-4", "INV-5");

    assertThat(cards).allSatisfy(card -> {
        assertThat(card.getExternalRef()).isNotBlank();
        assertThat(card.getStatus()).isIn("NEW", "PAID");
    });
}
```

This test guards the **projection interface contract** and tenant filter. Yet it **does not definitively prove** sensitive fields were excluded from the wire command or HTTP JSON, because that depends on projection/mapping mechanics and serialization. When reducing network payload or preventing internal fields from crossing the wire is a goal, also inspect the **actual `find` command sent to MongoDB** (via a `CommandListener`, profiler, or query logging) and the API response.

With `@Query(fields = "{ '_id': 1, 'externalRef': 1, 'status': 1 }")`, the command carries the matching projection document. When `internalNote` is excluded by projection, do not expect a projection interface to expose or reconstruct it. If projecting into a full entity class, remember a **partial entity** holds `null` or defaults for excluded fields; never save a partial entity back, or you risk overwriting and losing data.

### Testing Mapping When BSON Field Names Differ

Suppose `externalRef` on the entity changes to `@Field("external_ref")`; verify that stored data uses `external_ref` while queries and projections still populate Java getters properly. Checks to run:

1. Insert a document using the updated repository mapping.
2. Use raw `MongoTemplate.getCollection(...)` to read the document and assert the real BSON field name.
3. Call the projection repository and assert getter values.
4. If using `@Query(fields = ...)` or raw aggregations, check that commands/stages map field names accurately; any hardcoded BSON names must match the schema.

Avoid changing the fixture entity mid-suite without updating pipelines and expectations in other tests. This lesson keeps field names fixed so examples focus on the core mechanisms.

## 7. Testing Scrolling: Order, Cursors, and Result Sets

Scrolling traverses data in **windows**; it differs from loading the whole list via `findAll()` and differs from guaranteeing an immutable snapshot across requests. Two common bugs are **duplicated/skipped items** and **cursors unable to continue** because sort keys are missing.

### 7.1. Keyset Scrolling on Stable Data

Continue adding these tests inside `OrderRepositoryIT`. With five orders for `alpha` and window size 2, there must be three windows: `[a-1, a-2]`, `[a-3, a-4]`, `[a-5]`.

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

@Test
void keysetScroll_returnsAllRowsExactlyOnce() {
    Window<OrderDocument> first =
            repository.findFirst2ByTenantIdOrderByCreatedAtAscIdAsc(
                    "alpha", ScrollPosition.keyset());

    assertThat(first.getContent()).extracting(OrderDocument::id)
            .containsExactly("a-1", "a-2");
    assertThat(first.hasNext()).isTrue();

    Window<OrderDocument> second =
            repository.findFirst2ByTenantIdOrderByCreatedAtAscIdAsc(
                    "alpha", first.positionAt(first.size() - 1));

    assertThat(second.getContent()).extracting(OrderDocument::id)
            .containsExactly("a-3", "a-4");
    assertThat(second.hasNext()).isTrue();

    Window<OrderDocument> third =
            repository.findFirst2ByTenantIdOrderByCreatedAtAscIdAsc(
                    "alpha", second.positionAt(second.size() - 1));

    assertThat(third.getContent()).extracting(OrderDocument::id)
            .containsExactly("a-5");
    assertThat(third.hasNext()).isFalse();
}
```

This test proves: each window filters by `tenantId`, sorts as declared, and resumes cleanly to the next window when data is **unchanged**.

### 7.2. Including Multiple Documents with the Same createdAt to Test Tie-Breakers

If sorting only by `createdAt`, two documents sharing a timestamp can swap order or create ambiguous window boundaries. Add a document with the same timestamp as `a-3`, then scroll through the entire list:

```java
import java.util.ArrayList;
import java.util.List;

@Test
void keysetScroll_handlesEqualTimestampsWithIdTieBreaker() {
    repository.save(new OrderDocument(
            "a-6", "alpha", "INV-6",
            "PAID", 100L, second(3), "note-a6"));

    List<String> ids = new ArrayList<>();
    ScrollPosition position = ScrollPosition.keyset();

    while (true) {
        Window<OrderDocument> window =
                repository.findFirst2ByTenantIdOrderByCreatedAtAscIdAsc(
                        "alpha", position);

        ids.addAll(window.getContent().stream()
                .map(OrderDocument::id).toList());

        if (!window.hasNext()) {
            break;
        }
        position = window.positionAt(window.size() - 1);
    }

    assertThat(ids).containsExactly(
            "a-1", "a-2", "a-3", "a-6", "a-4", "a-5");
    assertThat(ids).doesNotHaveDuplicates();
}
```

Here `a-3` and `a-6` share `createdAt`, and `id` breaks the tie deterministically. Missing a tie-breaker or omitting `createdAt`/`id` from a projection causes edge-case bugs that fixtures with only distinct timestamps will never uncover.

### 7.3. Comparing Offset and Keyset Under Concurrent Changes

Suppose a client reads the first window `[a-1, a-2]`. Before reading window two, another request inserts `a-0` with an earlier `createdAt` than `a-1`.

- **Offset scrolling:** because the offset counts previously read items, the new row shifts positions; the next window may repeat `a-2` or skip items under concurrent edits.
- **Keyset scrolling:** the next window resumes from the sort keys after `a-2`; inserting a document **before the cursor** does not push the cursor backward. However, that newly inserted earlier document will not appear in subsequent windows either.
- **Neither is a multi-request transactional snapshot.** If an item's `createdAt` updates or it is deleted mid-scroll, results reflect those live changes.

A test demonstrating this inserts `a-0` right after window one and asserts keyset's second window still begins at `a-3`:

```java
@Test
void keysetScroll_continuesAfterCursorWhenEarlierRowInserted() {
    Window<OrderDocument> first =
            repository.findFirst2ByTenantIdOrderByCreatedAtAscIdAsc(
                    "alpha", ScrollPosition.keyset());

    repository.save(new OrderDocument(
            "a-0", "alpha", "INV-0",
            "NEW", 100L, second(0), "inserted-later"));

    Window<OrderDocument> second =
            repository.findFirst2ByTenantIdOrderByCreatedAtAscIdAsc(
                    "alpha", first.positionAt(first.size() - 1));

    assertThat(second.getContent()).extracting(OrderDocument::id)
            .containsExactly("a-3", "a-4");
}
```

For offset scrolling, start with `ScrollPosition.offset()` and pass `window.positionAt(window.size()-1)` for the next position; include equivalent tests when your API uses offset scrolling. On large datasets, also inspect `explain`/timing because deep offsets skip many records.

### 7.4. Rules for Safe Scrolling

| Condition | Why test it? |
| --- | --- |
| Deterministic sort ending with a unique key | Prevents duplicate/shifted items when timestamps collide |
| Keyset sort fields non-null and in projection | Cursor needs key values to resume |
| Tenant and filters stay identical across windows | Prevents mixing data or changing filters mid-scroll |
| Cursors created and verified by server/app | Never trust client-tampered cursors; validate tenant, filter, and sort |
| Inserts/deletes/updates happen mid-scroll | Clarifies contract: near-real-time traversal vs. consistent snapshot |
| End of data | `hasNext()` must become false; avoid infinite loops or redundant queries |

If a public API exposes serialized string cursors, define serialization, validation, and integrity protection (e.g., signing tenant, sort, and filter values) at the application layer. `ScrollPosition` is a query-continuation mechanism, **not proof of authorization**.

## 8. Testing Aggregations: Right Groups, Sums, and Scope

Aggregations hide subtler bugs than simple queries because multiple stages chain together: `$match` → `$group` → `$project` → `$sort`. In tests, **compute expectations directly from the fixture** rather than generating expected values with the same pipeline logic under test.

### 8.1. Verifying `@Aggregation` in the Repository

`OrderRepository.summarizePaid("alpha")` must sum `1200 + 800 + 500 = 2500` cents and count `3` orders:

```java
@Test
void aggregation_countsAndSumsOnlyPaidOrdersOfOneTenant() {
    List<PaidTotals> totals = repository.summarizePaid("alpha");

    assertThat(totals).singleElement().satisfies(row -> {
        assertThat(row.tenantId()).isEqualTo("alpha");
        assertThat(row.orders()).isEqualTo(3L);
        assertThat(row.cents()).isEqualTo(2500L);
    });
}

@Test
void aggregation_returnsEmptyWhenNoGroupMatches() {
    assertThat(repository.summarizePaid("missing-tenant")).isEmpty();
}
```

Having a `PAID` order of 9,900 cents for `beta` catches a missing tenant filter in `$match`. If `alpha` returned 12,400 cents, the pipeline likely leaked another tenant's data. If the sum matches yet the count is off, inspect status filters and grouping keys.

### 8.2. Testing Equivalent Pipelines via `MongoTemplate`

When pipelines are constructed dynamically, test `MongoTemplate.aggregate(...)` directly. Equivalent pipeline example:

```java
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;

import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

@Test
void mongoTemplateAggregation_matchesKnownFixture() {
    Aggregation pipeline = newAggregation(
            match(Criteria.where("tenantId").is("alpha")
                    .and("status").is("PAID")),
            group("tenantId")
                    .count().as("orders")
                    .sum("amountCents").as("cents"),
            project("orders", "cents")
                    .and("_id").as("tenantId")
                    .andExclude("_id")
    );

    AggregationResults<PaidTotals> result =
            mongoTemplate.aggregate(
                    pipeline, OrderDocument.class, PaidTotals.class);

    assertThat(result.getMappedResults())
            .singleElement()
            .satisfies(row -> {
                assertThat(row.tenantId()).isEqualTo("alpha");
                assertThat(row.orders()).isEqualTo(3L);
                assertThat(row.cents()).isEqualTo(2500L);
            });
}
```

When grouping by `tenantId`, MongoDB emits the group key under `_id`. The subsequent `project` stage renames `_id` to `tenantId` to map into the DTO. If a document field is renamed with `@Field`, verify field-path mapping to BSON in both the aggregation DSL and `@Aggregation`. Especially for handwritten JSON stages, never assume every path translates identically to derived queries.

### 8.3. Variants to Include in the Test Suite

| Case | Expectation |
| --- | --- |
| Tenant has 3 PAID and 2 NEW orders | Totals/counts include only the 3 PAID orders |
| Another tenant has matching externalRef | Does not affect the queried tenant's results |
| No matching documents | Empty list returned; service may convert to zero totals per contract |
| `amountCents` zero or negative (refund) | Sums match business rules rather than assuming all amounts are positive |
| Summed field is null/missing | Understand MongoDB `$sum` semantics and enforce business expectations |
| Grouping by multiple fields | Composite `_id` object; DTO/projection matches structure |
| `$unwind` on arrays with null/empty | Verify row counts before/after unwind and `preserveNullAndEmptyArrays` if needed |
| Query returning multiple groups | Explicit sort before asserting ordering |
| Large or decimal monetary values | Check BSON types, `Decimal128`/`BigDecimal` conversion, and overflow |

Note: MongoDB `$sum` has specific rules for non-numeric values and types; avoid using `null`/missing alone as your only fixture test. When currency requires exact decimals, use `Decimal128` or a fixed-scale integer representation and test conversions accordingly.

## 9. Indexes, `explain`, and Limits of Integration Tests

The tests written above focus on **correctness**. Passing on six documents does not mean queries will stay fast across six million documents. When moving to performance testing, provision indexes matching your filters and sorts.

For example, creating a compound index for tenant queries and scrolling:

```java
import org.springframework.data.domain.Sort.Direction;
import org.springframework.data.mongodb.core.index.Index;

// Run only in setup or migrations for an appropriate test environment.
mongoTemplate.indexOps(OrderDocument.class)
        .ensureIndex(new Index()
                .on("tenantId", Direction.ASC)
                .on("createdAt", Direction.ASC)
                .on("_id", Direction.ASC));
```

`findByTenantAndStatus` may need `{ tenantId: 1, status: 1 }` or a compound index incorporating sort fields depending on workload. Indexes for scrolling and aggregations can differ; never pick a single index solely because all functional tests pass.

Inspect `explain` on a query resembling production:

```java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

Document explain = mongoTemplate.getCollection("test_orders")
        .find(Filters.eq("tenantId", "alpha"))
        .sort(Sorts.ascending("createdAt", "_id"))
        .explain();

// Inspect queryPlanner / winningPlan / executionStats depending on verbosity.
```

Read `explain` to inspect the chosen plan and index, keys/documents examined under execution stats, and any expensive sort or full-scan stages. **Never hardcode assertions expecting one exact plan JSON** across all server versions and data sizes: optimizers can pick different plans. Performance tests need representative dataset sizes and dedicated thresholds separate from unit/slice tests.

## 10. Common Testing Traps That Cause False Passes

### Mocking Repositories or `MongoTemplate`

`when(repository.findByTenantAndStatus(...)).thenReturn(...)` only verifies the service interacted with the mock as stubbed; it **never runs the JSON in `@Query`**. Mocks work well for service unit tests, while repository integration tests must hit real MongoDB.

### Single-Tenant or Single-Status Fixtures

If every document belongs to `alpha`, forgetting the `tenantId` filter still passes. If every document is `PAID`, omitting `status` passes too. Fixtures must intentionally differentiate all conditions.

### Asserting Order Without a Sort

MongoDB does not guarantee a fixed natural return order. When `@Query` has no sort, use `containsExactlyInAnyOrder` or compare ID sets. For scrolling, declare explicit sorting with a tie-breaker.

### Computing Expected Results with the Same Broken Logic

If a test computes expected aggregate totals via a second aggregation built by the same helper, both can share the same bug. Compute expected numbers manually from fixtures or via an independent Java calculation over a small test dataset.

### Neglecting Field Names and BSON Types

`@Field("external_ref")`, `@Id`, `Instant`, `Decimal128`, custom converters, and projected DTOs all affect mapping. When failures appear only in production, inspect raw BSON in integration tests to verify actual stored fields. For `Instant`, watch BSON timestamp/date precision rounding and timezone consistency.

### Assuming Scrolling Is a Snapshot

Keyset scrolling resumes consistently from sort keys, yet **does not freeze data**. APIs requiring a consistent full export need snapshot semantics or checkpointing, or must document near-real-time traversal semantics and test that contract.

### Ignoring Runtime Execution Signals

Asserting no exception is not enough: with reactive APIs, subscribe and await the publisher; with transactions, verify commit/rollback; with aggregations or bulk writes, inspect actual persisted and returned state. When using `ReactiveMongoTemplate`, use Reactor Test's `StepVerifier` to wait for terminal signals before asserting results.

```java
// reactiveRepository: ReactiveMongoRepository for the same domain.
// Example verifying results rather than stopping at Flux creation.
StepVerifier.create(
        reactiveRepository.findByTenantIdAndStatus(
                "alpha", "PAID").collectList())
        .assertNext(found ->
                assertThat(found).hasSize(3))
        .verifyComplete();
```

## 11. Acceptance Criteria for `@Query`, Projections, Scrolling, and Aggregations

| Component | Must prove through tests |
| --- | --- |
| `@Query` | Correct binding, complete filters, no cross-tenant leakage, empty cases, and special-character inputs |
| Projection | Accurate getters/DTOs, query projects right fields, internal fields omitted from API, matching BSON mapping |
| Scrolling | Deterministic order, working cursors, exact ID set across windows, tie-breaker, clear semantics under concurrent edits |
| Aggregation | Correct stages/filters, accurate counts/sums/field names/types, empty-group handling, no cross-tenant mixing |
| Test infrastructure | Real MongoDB, isolated fixtures, matching server/driver versions, repeatable runs |
| Performance | Indexes and `explain` verified on representative workloads; never extrapolate production speed from tiny fixtures |

### Practice Exercise

1. Add a `@Query` finding orders by `tenantId`, `status`, and a minimum `amountCents` threshold; write tests covering all three conditions and a second tenant with overlapping data.
2. Create a projection exposing only `externalRef` and `status`; inspect the API response, raw BSON field mapping, and command projection.
3. Add two records sharing `createdAt`; scroll through everything via keyset in windows of two, asserting no duplicates or missing IDs. Insert an earlier record before the cursor between two windows and describe how keyset differs from offset.
4. Extend the aggregation to group by `status`, computing count and sum per group; calculate expected totals directly from fixtures and test empty groups and numeric fields.
5. Scale up document count to run `explain`, inspect index usage and timing, and keep performance conclusions separate from correctness assertions.

**Key takeaway:** Effective Spring Data MongoDB tests use deliberately discriminating fixtures to prove **`@Query` filters accurately, projections return the right shape, scrolling traverses cleanly, and aggregations compute exact totals**. `@DataMongoTest` against real MongoDB verifies both BSON mapping and the query engine; unit/service tests reinforce authorization and API contracts, while `explain`/performance tests examine behavior as data scales.
