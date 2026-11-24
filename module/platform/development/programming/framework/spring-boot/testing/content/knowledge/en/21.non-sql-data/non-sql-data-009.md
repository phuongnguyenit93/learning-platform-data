# Service versions, mapping, and emulator limitations when testing non-SQL data

> **Module:** Spring Boot – testing  
> **Group:** Non-SQL Data  
> **Topic:** Service versions, mapping, and emulator limitations  
> **Objective:** Distinguish mocks, fakes, emulators/embedded servers, and real services; understand why server versions, Spring Data mappings, serializers, indexes, queries, and transaction semantics determine a test's value; choose MongoDB/Redis/Elasticsearch Testcontainers appropriately. The main example uses Java 17, Spring Boot 3.5, and MongoDB 7 with a Mockito service unit test and an integration test running the real engine.

## 1. The problem: emulated tests are green, yet production still breaks

Non-SQL data stores are not merely a `Map<String,Object>`. Depending on the technology, systems enforce specific protocols, versions, data types, and server behaviors. An emulator or fake can return expected values while silently skipping critical constraints of the real database.

Typical examples:

- A mocked `MongoRepository` is stubbed to return an order list; the test passes even though `tenantId` is persisted as `tenant_id` differently from the real query.
- An in-memory fake stores money as `BigDecimal`, whereas production MongoDB BSON expects `Decimal128`; the test misses serialization/converter errors.
- A fake builds no unique index, so inserting two orders with duplicate external references succeeds.
- An emulated server lacks optimistic locking/transaction isolation, so concurrent updates miss lost-update bugs.
- A `HashMap`-based Redis fake fails to model TTL, eviction, atomic Lua, key types, and race conditions of real Redis.
- An Elasticsearch mock returns documents from a hardcoded list; the test fails to protect analyzers, tokenization, mappings, refreshes, and relevance scoring of a real cluster.
- Integration tests run against a different MongoDB/Redis/Elasticsearch version than production, causing an operator, index option, or protocol mismatch.
- Spring Data/Jackson converters are configured differently between tests and production; values read back from the real server change type, precision, or timezone.

**Central principle:** Tests only prove the behavior of components **actually executed**. Mocking a service does not prove persistence mapping; faking a database does not prove server semantics; a container running the real server engine proves many real behaviors, yet still does not verify production cluster topology, security, performance, or version if they differ.

## 2. From mocks to production-like environments: four distinct levels

| Level | Example | Tests real mapping/server? | Strengths | Major limitations |
| --- | --- | --- | --- | --- |
| **Mock/stub** | Mockito `when(repository.find...)` | No, unless real collaborators are invoked | Very fast; verifies interactions/service logic | Hardcoded responses; runs no queries or serializers |
| **In-memory fake** | Hand-written `Map<String, Order>`, fake Redis cache | Usually not | Tests domain workflows, controlled failures, and time | Skips dialects/protocols/indexes/collations/TTLs/locking |
| **Embedded/emulator** | Embedded Mongo alternative, Redis emulator, local API emulator | Partially, depending on implementation/version | Convenient offline, simulates parts of the API | Not guaranteed equivalent to full server; unsupported behaviors |
| **Real service for tests** | MongoDB/Redis/Elasticsearch via Testcontainers | Yes, within the container's version/config | Executes real drivers, wire protocol, mappers, indexes/queries/locking | Does not recreate clusters, managed features, IAM, or heavy load |
| **Staging/production-like** | Dedicated cluster with matching policies/data | Higher when configurations align | TLS, networking, multi-node, upgrades, operational behavior | Slow/expensive; requires data and permission isolation |

A fake can be the **right** choice for a unit test. The mistake is labeling a test "MongoDB 7 tested" when no MongoDB server ever started.

### 2.1. A mock is not a fake, and a fake is not an emulator

- **Mock** focuses on interactions, e.g., checking `verify(repository).findBy...` and returning canned data.
- **Stub** supplies canned responses without necessarily verifying interactions; Mockito supports both mocking and stubbing.
- **Fake** is an alternative working implementation with simplified behavior, e.g., storing records in a `Map`.
- **Emulator** reproduces a subset of a service's protocol/API/behavior, often as a standalone process; compatibility levels must be proven.
- **Testcontainers** is not "mock Docker". The container runs **the real service** inside a test environment, subject to topology/config/data boundaries.
- **Contract tests** verify client–provider expectations at boundaries; contract tests do not replace persistence integration tests.

### 2.2. Which test answers which question?

```text
OrderLookupService
     |
     +-- Mockito OrderRepository
     |      → Does the service pass the right tenant/status?
     |      → Is OrderSummary mapping logic correct?
     |
     +-- MongoDB Testcontainers (MongoDB 7)
     |      → Do queries use the right BSON field names?
     |      → Are Decimal128/Instant mappings correct?
     |      → Do unique indexes and @Version take effect?
     |      → Which driver/server versions are running?
     |
     +-- Staging MongoDB cluster
            → Are auth/TLS/replica set/production indexes right?
            → Are upgrades, network failover, and load behaviors sound?
```

The differences among these answers must be reflected clearly in test names, QA reports, and CI pipelines.

## 3. Which versions actually matter?

A Spring Boot application interacting with NoSQL involves **multiple versions simultaneously**, not just one dependency in `pom.xml`:

1. **Spring Boot version:** governs auto-configuration and managed dependency versions.
2. **Spring Data module version:** e.g., Spring Data MongoDB, Redis, Elasticsearch; governs query derivation, mapping, repositories, and converters.
3. **Java client/driver version:** MongoDB Java Driver, Lettuce/Jedis, Elasticsearch Java API Client; governs wire protocol, authentication, serialization, retries, and error translation.
4. **Server version:** MongoDB major/minor, Redis 6/7/8, Elasticsearch cluster 7/8/9 depending on product; governs APIs, storage behavior, and query syntax.
5. **Server configuration/topology:** standalone/replica set/sharded MongoDB, Redis standalone/cluster/sentinel, multi-node Elasticsearch, TLS/auth/ACL, collations, timezones.
6. **Data/index/schema version:** collection validators, indexes, aliases, analyzers, serializer schemas, key naming, and migration scripts.
7. **External hosted service version:** managed providers introduce feature flags, API compatibility layers, access policies, or engine forks differing from vanilla OSS.

**One version pair does not determine all behavior.** A single-node MongoDB 7 container and a MongoDB 7 sharded production cluster may behave alike on simple CRUD while differing on routing, shard keys, transactions, latency, and failover.

### 3.1. A version test matrix worth recording

| Item | Illustrative example | Verified via |
| --- | --- | --- |
| Spring Boot | `3.5.0` | `pom.xml`/dependency tree |
| Java runtime | `17` | `java -version` |
| MongoDB server | `7.0.x` | Container image and `db.runCommand({buildInfo:1})` |
| MongoDB driver | Version managed by Boot BOM | `mvn dependency:tree` |
| MongoDB topology | Test single node; production replica set | Integration environment metadata |
| Index policy | Compound unique tenant + externalRef | Server index catalog / duplicate-write test |
| BSON currency | `Decimal128` | Inspect raw `org.bson.Document` |
| Schema rollout | Versioned migrations/initialization | Migration/rollout job and catalog assertions |
| Security | Test-only connection | Separate staging auth/TLS tests |

The `mongo:7.0` image example is an **illustrative version line**, not a claim that all production MongoDB deployments should run MongoDB 7. When upgrading server versions, update the matrix and test used features rather than bumping image tags blindly just because a newer tag appeared.

### 3.2. Never use floating image tags

`mongo:latest`, `redis:latest`, or `elasticsearch:latest` can make CI run a different engine today than yesterday. For integration tests, pin major/minor tags or digests per organizational policy. During upgrades, run a version matrix over a transition period:

```text
Target production now: MongoDB version A
Next planned target:   MongoDB version B

CI:
  1) Fast unit tests with mocks/fakes
  2) Container integration tests on A
  3) Compatibility/upgrade tests on B
  4) Staging rollout and telemetry checks
```

**Never assume old APIs behave identically on newer servers.** Deprecations, changed defaults, removed server commands, altered index/aggregation behavior, or new driver compatibility rules can all apply.

### 3.3. Query version info straight from the server

MongoDB shell example:

```javascript
db.runCommand({ buildInfo: 1 })
```

This returns metadata including `version`, `gitVersion`, etc.; when testing version-specific behavior, assert the actual server version rather than looking only at the POM. MongoDB driver version does not equal MongoDB server version.

For Redis, query `INFO server` (subject to ACL permissions). For Elasticsearch, query the root/cluster info endpoint or Java client equivalent; verify version metadata from the **real running service in the test**, not from a hardcoded string.

## 4. Mapping: a Java object is not BSON / Redis bytes / an Elasticsearch document

In a Spring Data application, data passes through several conversions:

```text
Java entity / DTO
   │
   ▼
Spring Data MappingContext + MongoConverter / RedisSerializer / ES mapping
   │
   ▼
Wire type: BSON document / Redis bytes / JSON request
   │
   ▼
Real server storage/index/query
   │
   ▼
Driver deserialize + Spring Data mapping
   │
   ▼
Java object returned to service
```

A fake storing Java objects directly in a `Map` skips **both directions of conversion**. Consequently, fakes miss renamed fields, precision overflow, missing/null differences, enum converters, TTL expiration, and index mismatches.

### 4.1. MongoDB: Spring property names differ from BSON fields

Example:

```java
@Field("tenant_id")
private String tenantId;
```

The Java property is `tenantId`, whereas the MongoDB field is `tenant_id`. With Spring Data's derived query `findByTenantId(...)`, mapping infrastructure translates the property to the stored field name. With raw BSON `Document` or native JSON queries, you must use the real stored key.

A test mocking the repository to return `OrderDocument` directly never exercises the mapper. Integration tests should inspect **raw server BSON** to confirm `tenant_id` is present and `tenantId` did not leak unexpectedly.

### 4.2. MongoDB: BigDecimal does not become Decimal128 inside a fake

Spring Data MongoDB handles type conversion. For money/amounts, to store `BigDecimal` as BSON `Decimal128`, specify it explicitly:

```java
@Field(value = "total_amount", targetType = FieldType.DECIMAL128)
private BigDecimal totalAmount;
```

After `MongoTemplate` writes to real MongoDB, verify the raw type:

```java
Document raw = mongoTemplate.getCollection("orders")
        .find(new Document("_id", "ord-1"))
        .first();

assertThat(raw.get("total_amount"))
        .isInstanceOf(Decimal128.class);
```

This is a **snippet inside a test with an injected `mongoTemplate`**, requiring imports for `org.bson.Document`, `org.bson.types.Decimal128`, and AssertJ. The full project in Section 9 includes this case. A fake Java `Map<String,BigDecimal>` never verifies real BSON types.

### 4.3. MongoDB: `@Id String`, ObjectId, and identifier conversions

MongoDB stores primary keys in `_id` by default, not necessarily an `id` field. Spring Data Mongo has rules for `String` identifiers: if a String represents a valid ObjectId hex string, the mapper may convert it to BSON `ObjectId`; other strings may stay as strings depending on mapping/configuration.

Therefore, never assume every `@Id String` is stored as a BSON String. If consumers require raw string IDs, consider `@MongoId` or explicit mapping and test with 24-hex-character lookalike strings as well. The example uses IDs like `"ord-1"`, which do not look like ObjectIds, keeping raw BSON assertions unambiguous.

### 4.4. MongoDB: Instant, Date, and precision

Java `Instant` carries higher precision than BSON Date's millisecond resolution. On write/read, nanoseconds can be truncated or converted depending on driver/converter behavior. Tests should pick a clean fixed instant:

```java
Instant.parse("2026-06-17T10:00:00Z")
```

If an API needs microsecond/nanosecond fidelity, choose another storage design or extra field; never let a fake `Map` trick you into thinking BSON Date preserves nanoseconds. Never call `Instant.now()` and assert exact equality across the DB without controlling clock precision.

### 4.5. Null and missing fields are not identical

A MongoDB document can be:

```json
{"_id":"ord-1","note":null}
```

or:

```json
{"_id":"ord-1"}
```

In raw storage, an absent field and an explicit `null` field behave differently in queries, indexes, and migrations. A converter may omit null fields on write, whereas a fake Java object hides that distinction entirely. Test `raw.containsKey("note")` whenever missing-vs-null matters to the contract.

### 4.6. Redis: bytes + serializer form the storage contract

Redis does not store Java objects. A `RedisTemplate<String, Order>` can use JDK serialization, JSON, String, or a custom serializer. Same Java object, different bytes — meaning older data can become unreadable after a deploy:

```text
Java Order
   ├── JDK serializer  → binary encoding
   ├── Jackson JSON    → JSON bytes / optional type metadata
   └── String format   → UTF-8 fields

Redis stores bytes; fake Map stores Java Order directly.
```

Real tests must confirm key prefixes, serialization formats, TTLs, and backward compatibility when changing serializers. Never test parsers using live production data. With polymorphic JSON type metadata, evaluate deserialization security and versioning carefully.

### 4.7. Elasticsearch: mappings + analyzers + refresh

Elasticsearch `keyword` and `text` are not interchangeable; they differ in tokenization, filtering, and aggregations. A mocked search response can return the right ID while skipping all of:

- Index mappings, dynamic fields, and keyword subfields.
- Analyzers/tokenizers, lowercasing, stemming, and accent folding.
- Query DSL semantics, relevance scoring, and tie-breaking.
- Refresh policies: newly indexed documents are not automatically searchable right away.
- Aliases/rollovers and index templates.
- Version/cluster compatibility.

When search behavior matters, write integration tests with a matching Elasticsearch container/cluster and verify real mappings and queries. Never cite `List.stream().filter(s -> s.contains(...))` as proof of analyzer behavior.

## 5. Limitations commonly missing from emulators and fakes

| Aspect | What fakes/mocks usually do | What the real service can do |
| --- | --- | --- |
| Wire protocol | Sends nothing through driver | Validates types, commands, encoding, auth |
| Schema/BSON mapping | Keeps Java object intact | Converts to BSON/JSON/bytes and back |
| Server version | No server exists | Enables/removes features by version |
| Indexes | Scans a `Map`/`List` | Unique, compound, TTL, full-text indexes |
| Constraints | Checks nothing | Rejects duplicate/invalid writes or enforces validation |
| Ordering | Usually insertion order | Sorts by query/sort/collation; unstable ties |
| Concurrency | Single-threaded or synchronized fake | Concurrent writes, atomic ops, optimistic conflicts |
| TTL | Never expires or deletes via fake clock | Scheduled expiry, eventual background cleanup |
| Transactions | Absent or simplified | Supported depending on topology/engine/config |
| Search relevance | Substring matching | Analyzers, scoring, refresh, and shards |
| Serialization | Object `equals` | Network bytes/BSON types/converters |
| Retries/timeouts | Returns success immediately | Network timeouts, pool exhaustion, failover |
| Security | Ignores users/ACLs | Authentication, TLS, roles, namespaces |
| Observability | Emits no metadata | Latency, errors, metrics, logs, traces |
| Operational upgrades | Behavior stays static | Migrations/compatibility/rollover |

**The simpler the fake, the narrower the test claim must be.** A unit-test fake is completely valid for protecting business logic; server compatibility must be protected at another layer.

## 6. Wrong and right examples at the service boundary

Suppose a service returns the newest orders for a tenant. A Mockito unit test:

```java
when(repository.findByTenantIdAndStatusOrderByCreatedAtDesc(
        "team-a", OrderStatus.NEW))
        .thenReturn(List.of(orderB, orderA));
```

This confirms the service passes the right tenant and enum and maps the returned list, yet **does not** verify Spring Data builds a BSON query against `tenant_id`, does not confirm MongoDB sorts by `created_at`, and does not check driver `Decimal128` mapping.

An integration test using MongoDB Testcontainers:

```text
1. Save three BSON documents into the real engine
2. Query through the real repository
3. Assert tenant/status filtering and descending createdAt
4. Inspect raw BSON types
5. Test duplicate-key index rejection and optimistic updates
6. Record the actual server version via buildInfo
```

Mocks cannot prove any of those steps, no matter how richly their stubs are populated.

## 7. Sample project: Spring Boot 3.5 + MongoDB Testcontainers

This project runs with **Java 17, Maven, Spring Boot 3.5.0**, Spring Data MongoDB, and Testcontainers MongoDB. All data is synthetic in a test-only database. Docker/container runtime must be active for integration tests; the Mockito unit test needs no Docker.

### 7.1. Directory tree

```text
non-sql-version-mapping-lab/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/nosql/
    │       ├── NoSqlLabApplication.java
    │       ├── OrderStatus.java
    │       ├── OrderDocument.java
    │       ├── OrderRepository.java
    │       ├── OrderSummary.java
    │       └── OrderLookupService.java
    └── test/
        └── java/com/example/nosql/
            ├── OrderLookupServiceUnitTest.java
            └── OrderMongoIntegrationTest.java
```

Each public class/record/enum sits in its own matching file under package `com.example.nosql`. The project defines no HTTP controller because its focus is **storage mapping and service boundaries**, not web routing. There are no production credentials or external managed endpoints.

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>non-sql-version-mapping-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-mongodb</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-testcontainers</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>mongodb</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-data-mongodb` supplies Spring Data MongoDB and the driver; `spring-boot-starter-test` provides JUnit Jupiter/Mockito/AssertJ; `spring-boot-testcontainers` adds Spring Boot service connection support; Testcontainers MongoDB + JUnit 5 launches the test server.

**Do not override the MongoDB driver version manually** when using Spring Boot dependency management unless executing a deliberate version-compatibility plan. MongoDB server version belongs to the container image, not the POM.

### 7.3. `NoSqlLabApplication.java`

```java
// src/main/java/com/example/nosql/NoSqlLabApplication.java
package com.example.nosql;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NoSqlLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(NoSqlLabApplication.class, args);
    }
}
```

### 7.4. `OrderStatus.java`

```java
// src/main/java/com/example/nosql/OrderStatus.java
package com.example.nosql;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
```

### 7.5. `OrderDocument.java`: explicit BSON mapping

```java
// src/main/java/com/example/nosql/OrderDocument.java
package com.example.nosql;

import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document(collection = "orders")
@CompoundIndex(
        name = "uq_tenant_external_ref",
        def = "{'tenant_id': 1, 'external_ref': 1}",
        unique = true)
public class OrderDocument {

    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("external_ref")
    private String externalRef;

    @Field(
            value = "total_amount",
            targetType = FieldType.DECIMAL128)
    private BigDecimal totalAmount;

    @Field("created_at")
    private Instant createdAt;

    @Field("status")
    private OrderStatus status;

    @Version
    private Long version;

    protected OrderDocument() {
    }

    public OrderDocument(
            String id,
            String tenantId,
            String externalRef,
            BigDecimal totalAmount,
            Instant createdAt,
            OrderStatus status) {
        this.id = id;
        this.tenantId = tenantId;
        this.externalRef = externalRef;
        this.totalAmount = totalAmount;
        this.createdAt = createdAt;
        this.status = status;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getExternalRef() { return externalRef; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public Instant getCreatedAt() { return createdAt; }
    public OrderStatus getStatus() { return status; }
    public Long getVersion() { return version; }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }
}
```

**Intentional mappings:**

- `@Document(collection="orders")` targets the `orders` collection.
- `@Id String id` maps to `_id`. Test IDs use `ord-...` so they are never implicitly converted to ObjectId.
- `tenantId` ↔ BSON `tenant_id`; `externalRef` ↔ `external_ref`.
- `BigDecimal totalAmount` is stored as BSON `Decimal128`, unlike a fake storing a plain Java object.
- `Instant createdAt` is stored as a BSON date/time type, with precision critical when testing timestamps.
- `status` maps to its enum string value in BSON under the example's default converter.
- `@Version Long version` provides optimistic locking on save/update; it does not turn the system into distributed transactions.
- `@CompoundIndex` enforces uniqueness on the **pair** of tenant + external reference, allowing different tenants to share the same external ref.

**Important warning:** Spring Data MongoDB does not unconditionally create every annotated index. Auto-index creation is disabled by default in many Spring Data versions; the test **explicitly** sets `spring.data.mongodb.auto-index-creation=true`. Production should manage index creation/rollout through dedicated schema migrations. Having `@CompoundIndex` in code does not prove the real database has that index.

### 7.6. `OrderRepository.java`

```java
// src/main/java/com/example/nosql/OrderRepository.java
package com.example.nosql;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    List<OrderDocument>
    findByTenantIdAndStatusOrderByCreatedAtDesc(
            String tenantId, OrderStatus status);
}
```

Spring Data Mongo query derivation must resolve Java properties `tenantId`, `status`, and `createdAt` through the mapping context to generate a MongoDB query/sort on fields `tenant_id`, `status`, and `created_at`. A Mockito stub cannot prove any of this.

### 7.7. `OrderSummary.java`

```java
// src/main/java/com/example/nosql/OrderSummary.java
package com.example.nosql;

import java.math.BigDecimal;

public record OrderSummary(
        String id,
        String externalRef,
        BigDecimal totalAmount) {
}
```

The response domain DTO deliberately omits tenant, status, version, and unnecessary persistence internals. Omitting tenant from the summary **is not** authorization; the service must ensure tenant inputs are verified at a real boundary.

### 7.8. `OrderLookupService.java`

```java
// src/main/java/com/example/nosql/OrderLookupService.java
package com.example.nosql;

import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class OrderLookupService {

    private final OrderRepository repository;

    public OrderLookupService(OrderRepository repository) {
        this.repository = repository;
    }

    public List<OrderSummary> latestNew(String tenantId) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException(
                    "Tenant is required");
        }

        return repository
                .findByTenantIdAndStatusOrderByCreatedAtDesc(
                        tenantId, OrderStatus.NEW)
                .stream()
                .map(order -> new OrderSummary(
                        order.getId(),
                        order.getExternalRef(),
                        order.getTotalAmount()))
                .toList();
    }
}
```

The service has a **unit-testable contract**: reject blank tenants, forward the exact tenant/status to the repository, and map returned entities into summaries. It does not execute database queries itself; that responsibility belongs to the repository, driver, and server.

**Never trust a client-supplied raw `X-Tenant-Id` header for real data access.** Production apps must extract the tenant from an authenticated principal/verified token and enforce resource-level authorization. This example focuses solely on mapping and testing boundaries.

## 8. Unit test with Mockito: fast, with clear limits

### 8.1. `OrderLookupServiceUnitTest.java`

```java
// src/test/java/com/example/nosql/OrderLookupServiceUnitTest.java
package com.example.nosql;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class OrderLookupServiceUnitTest {

    private OrderDocument order(
            String id, String externalRef,
            String amount) {
        return new OrderDocument(
                id,
                "team-a",
                externalRef,
                new BigDecimal(amount),
                Instant.parse("2026-06-17T10:00:00Z"),
                OrderStatus.NEW);
    }

    @Test
    void passesTenantAndMapsRepositoryResults() {
        OrderRepository repository =
                mock(OrderRepository.class);
        OrderLookupService service =
                new OrderLookupService(repository);

        when(repository
                .findByTenantIdAndStatusOrderByCreatedAtDesc(
                        "team-a", OrderStatus.NEW))
                .thenReturn(List.of(
                        order("ord-2", "ext-2", "20.00"),
                        order("ord-1", "ext-1", "10.00")));

        List<OrderSummary> result =
                service.latestNew("team-a");

        assertThat(result)
                .extracting(OrderSummary::id)
                .containsExactly("ord-2", "ord-1");

        assertThat(result.get(0).totalAmount())
                .isEqualByComparingTo("20.00");

        verify(repository)
                .findByTenantIdAndStatusOrderByCreatedAtDesc(
                        "team-a", OrderStatus.NEW);
    }

    @Test
    void rejectsMissingTenantWithoutQueryingRepository() {
        OrderRepository repository =
                mock(OrderRepository.class);
        OrderLookupService service =
                new OrderLookupService(repository);

        assertThatThrownBy(() -> service.latestNew(" "))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Tenant is required");

        verifyNoInteractions(repository);
    }
}
```

**Proven:** service validation, argument forwarding, DTO mapping, and result ordering **given the stubbed return list**.

**Not proven:** that MongoDB actually sorts correctly, that Spring Data maps BSON fields accurately, that the unique index exists, that `Decimal128` preserves precision, that optimistic locking works, or that the server supports the feature.

An in-memory fake could keep a `List` and filter/sort in Java, yet still skip MongoDB BSON, indexes, and query semantics. Never promote an elaborate stub into a "MongoDB emulator" merely because it implements many methods.

### 8.2. When to use a fake instead of a mock?

Fakes help when multiple business services interact with a persistence port needing shared state across calls, while the test is not testing MongoDB behavior. For example, an `InMemoryOrderStore` keeping copies of `Order` in a `Map` to test event-emitting workflows or price calculations.

Fake limitations must be stated explicitly:

- Does it enforce duplicate keys or not?
- Does it copy data on save/find or return the same mutable reference?
- Does it share ordering/null/missing semantics?
- Does it enforce optimistic version checks?
- Does it model TTLs/collisions/concurrency?

If the answer is "no", **never** use the fake test to prove those guarantees. Back them up with the real integration test in the next section.

## 9. Integration test on real MongoDB 7 using Testcontainers

### 9.1. `OrderMongoIntegrationTest.java`

```java
// src/test/java/com/example/nosql/OrderMongoIntegrationTest.java
package com.example.nosql;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.bson.Document;
import org.bson.types.Decimal128;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataMongoTest(properties = {
        "spring.data.mongodb.auto-index-creation=true",
        "spring.data.mongodb.database=orders_test"
})
@Import(OrderLookupService.class)
@Testcontainers
class OrderMongoIntegrationTest {

    @Container
    @ServiceConnection
    static final MongoDBContainer mongo =
            new MongoDBContainer("mongo:7.0");

    @Autowired
    OrderRepository repository;

    @Autowired
    OrderLookupService service;

    @Autowired
    MongoTemplate mongoTemplate;

    @BeforeEach
    void cleanDataWithoutDroppingIndexes() {
        repository.deleteAll();
    }

    private OrderDocument order(
            String id, String tenant, String externalRef,
            String amount, String instant, OrderStatus status) {
        return new OrderDocument(
                id,
                tenant,
                externalRef,
                new BigDecimal(amount),
                Instant.parse(instant),
                status);
    }

    @Test
    void storesExpectedBsonFieldNamesAndDecimal128() {
        OrderDocument created = repository.save(
                order("ord-1", "team-a", "ext-1",
                        "12.50", "2026-06-17T10:00:00Z",
                        OrderStatus.NEW));

        assertThat(created.getVersion()).isNotNull();

        Document raw = mongoTemplate.getCollection("orders")
                .find(new Document("_id", "ord-1"))
                .first();

        assertThat(raw).isNotNull();
        assertThat(raw.getString("tenant_id"))
                .isEqualTo("team-a");
        assertThat(raw.getString("external_ref"))
                .isEqualTo("ext-1");
        assertThat(raw.containsKey("tenantId")).isFalse();
        assertThat(raw.get("total_amount"))
                .isInstanceOf(Decimal128.class);
        assertThat(((Decimal128) raw.get("total_amount"))
                .bigDecimalValue())
                .isEqualByComparingTo("12.50");
        assertThat(raw.getDate("created_at").toInstant())
                .isEqualTo(
                        Instant.parse("2026-06-17T10:00:00Z"));

        OrderDocument reloaded =
                repository.findById("ord-1").orElseThrow();

        assertThat(reloaded.getTotalAmount())
                .isEqualByComparingTo("12.50");
        assertThat(reloaded.getStatus())
                .isEqualTo(OrderStatus.NEW);
    }

    @Test
    void derivedQueryUsesMappedFieldsAndRealSorting() {
        repository.saveAll(List.of(
                order("ord-1", "team-a", "ext-1", "10.00",
                        "2026-06-17T10:00:00Z", OrderStatus.NEW),
                order("ord-2", "team-a", "ext-2", "20.00",
                        "2026-06-17T12:00:00Z", OrderStatus.NEW),
                order("ord-3", "team-a", "ext-3", "30.00",
                        "2026-06-17T13:00:00Z", OrderStatus.PAID),
                order("ord-4", "team-b", "ext-4", "40.00",
                        "2026-06-17T14:00:00Z", OrderStatus.NEW)));

        assertThat(service.latestNew("team-a"))
                .extracting(OrderSummary::id)
                .containsExactly("ord-2", "ord-1");

        assertThat(service.latestNew("team-b"))
                .extracting(OrderSummary::id)
                .containsExactly("ord-4");
    }

    @Test
    void compoundUniqueIndexRejectsOnlySameTenantDuplicate() {
        repository.save(
                order("ord-1", "team-a", "same-ref", "10.00",
                        "2026-06-17T10:00:00Z", OrderStatus.NEW));

        repository.save(
                order("ord-2", "team-b", "same-ref", "20.00",
                        "2026-06-17T10:00:00Z", OrderStatus.NEW));

        assertThatThrownBy(() -> repository.save(
                order("ord-3", "team-a", "same-ref", "30.00",
                        "2026-06-17T10:00:00Z", OrderStatus.NEW)))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void optimisticVersionRejectsStaleUpdate() {
        repository.save(
                order("ord-1", "team-a", "ext-1", "10.00",
                        "2026-06-17T10:00:00Z", OrderStatus.NEW));

        OrderDocument first =
                repository.findById("ord-1").orElseThrow();
        OrderDocument stale =
                repository.findById("ord-1").orElseThrow();

        first.setStatus(OrderStatus.PAID);
        repository.save(first);

        stale.setStatus(OrderStatus.CANCELLED);
        assertThatThrownBy(() -> repository.save(stale))
                .isInstanceOf(
                        OptimisticLockingFailureException.class);

        assertThat(repository.findById("ord-1")
                .orElseThrow().getStatus())
                .isEqualTo(OrderStatus.PAID);
    }

    @Test
    void verifiesActualMongoServerMajorVersion() {
        Document info = mongoTemplate.getDb()
                .runCommand(new Document("buildInfo", 1));

        assertThat(info.getString("version"))
                .startsWith("7.");
    }
}
```

**Intentional test suite:**

1. `storesExpectedBsonFieldNamesAndDecimal128` proves raw BSON names/types/dates and Java readback.
2. `derivedQueryUsesMappedFieldsAndRealSorting` proves derived repository query filtering by tenant/status and server-side sorting.
3. `compoundUniqueIndexRejectsOnlySameTenantDuplicate` protects the **compound unique index** unknown to mocks; identical values across two tenants succeed while same-tenant duplicates are rejected.
4. `optimisticVersionRejectsStaleUpdate` protects `@Version` and optimistic write failures across two independent instances reading the same prior version.
5. `verifiesActualMongoServerMajorVersion` confirms the test connects to MongoDB 7.x rather than trusting an image string in code blindly.

### 9.2. Why does `@DataMongoTest` still need `@Import`?

`@DataMongoTest` loads MongoDB mappers/templates and repositories, yet **does not scan all business `@Service` beans**. We add `@Import(OrderLookupService.class)` because the integration test routes through real service → real repository → real MongoDB.

Unlike the unit test, `OrderRepository` is not mocked. Replacing the repository with `@MockitoBean` here would stop the tests from verifying BSON/indexes/server behavior.

### 9.3. Role of `@ServiceConnection`

`@ServiceConnection` on the static `MongoDBContainer` gives Spring Boot MongoDB connection details from the running container; the test app never hardcodes `localhost:27017` or reads production URIs.

`spring.data.mongodb.database=orders_test` only picks the test database name rather than authenticating a container. The container holds an ephemeral database per lifecycle; Testcontainers supplies the URI/port. Avoid adding production `spring.data.mongodb.uri` into `src/test/resources`.

### 9.4. Why is `auto-index-creation=true` needed?

`@CompoundIndex` declares index metadata, yet annotation-driven auto-index creation is **not enabled by default** in Spring Data MongoDB 3+.

The test sets:

```properties
spring.data.mongodb.auto-index-creation=true
```

so the unique index is present inside the ephemeral test database. Production should manage indexes deliberately (migrations/initialization), especially on populated collections where index builds are expensive.

**Very important:** `repository.deleteAll()` in `@BeforeEach` deletes documents without dropping collections/indexes. If a test calls `mongoTemplate.dropCollection(...)` after indexes were created, indexes can disappear; never assume a unique test fails for the right reason if the index vanished.

### 9.5. Optimistic locking is not a cross-document transaction

`@Version` adds a version check on a single entity's update, blocking certain stale writes. It does not automatically guarantee atomicity across two collections or rollback side effects when a remote call fails.

MongoDB multi-document transactions impose deployment/topology, replica set/sharded cluster, and session configuration requirements. When production uses transactions, configure a replica-set container per Testcontainers/Spring Data docs and test explicit transaction boundaries. This sample **does not** claim multi-document transactions just because `@Version` passed.

### 9.6. Running tests and reading results

```bash
java -version
mvn -version

# Unit test needing no MongoDB/Docker:
mvn -Dtest=OrderLookupServiceUnitTest test

# Integration test needing Docker/container runtime:
docker info
mvn -Dtest=OrderMongoIntegrationTest test

# Both suites:
mvn test
```

The project contains **7 `@Test` methods**: 2 in `OrderLookupServiceUnitTest` and 5 in `OrderMongoIntegrationTest`. These are method counts from the illustrative code, **not a build execution log**. Maven may need to download dependencies and Docker may need to pull the image; output, ports, and execution times vary per environment.

If Docker is unavailable, integration tests will fail startup; never swap them for mocked repositories and report "MongoDB integration PASS". CI reports must separate unit-only, integration pass, integration skipped, and integration failed.

## 10. Limitations of a MongoDB container vs. production

Even when running the real MongoDB engine in Docker, a single-container test does not prove everything:

| What needs verification | Single MongoDB container | When other tests are required |
| --- | --- | --- |
| Basic CRUD & BSON mapping | Good | When production-specific converters exist |
| Query/aggregation operators | Good for pinned version | When operators depend on Atlas/server flavors |
| Unique/compound indexes | Testable | When legacy data or complex index migrations exist |
| Optimistic locking | Testable | Under multi-service concurrent workloads |
| Multi-document transactions | Requires replica-set topology | Test transactions on a replica set |
| Sharding/cluster routing | Not enabled by default | Cluster integration tests |
| TLS/IAM/ACL | Not enabled by default | Staging/security tests |
| Failover/elections | Absent on single node | Multi-node failure tests |
| Large datasets/performance | Not representative | Load/EXPLAIN/profiling tests |
| Managed extensions | Not guaranteed | Provider-specific staging |

**A fast test verifying BSON correctness is not a stress test.** Keep correctness tests separate from performance, operability, and security testing.

### 10.1. Version pinning and upgrade tests

If production runs MongoDB version A, container tests should prioritize version A. When moving to B, run CI against both A and B for critical repositories. Changes can alter defaults, query planners, feature compatibility versions (FCV), auth modes, indexes, or driver support.

Never test a production upgrade using production credentials from a laptop or CI test. Use an isolated staging database or test-only container/cluster.

### 10.2. Mapping converters change across versions

An unchanged Java class can still produce different BSON if mappers, converters, Mongo drivers, or default type representations change during a dependency bump. Things to test:

- Raw `_id` type: String vs. ObjectId.
- `BigDecimal`: String vs. Decimal128.
- `Instant`: BSON Date precision/timezone.
- Collections/maps: nested fields and keys containing dots or dollar signs.
- Null/missing semantics.
- Enum naming and custom converters.
- Version fields and optimistic locking semantics.
- Index definitions and collection validators.

Verify with *raw Document assertions* plus Java object round-trips; round-trip alone can miss bugs where both write and read invert identically.

## 11. Redis: fake limits for TTL, atomicity, and serialization

Redis differs from MongoDB in its data model. A fake Java Map commonly models `GET`/`SET`, whereas real Redis includes TTLs, eviction policies, server time, key types, transactions/pipelines, pub/sub, Lua scripts/Redis functions, and cluster routing.

### 11.1. TTL is a time-based contract

Suppose code runs:

```java
redisTemplate.opsForValue()
        .set("reset-token:demo", "value",
                Duration.ofMinutes(5));
```

This is an illustrative snippet outside the runnable MongoDB project; it requires `RedisTemplate` and imports. In a fake, you might simulate expiry with an injected `Clock`, yet that **does not** prove the real Redis server sets expiration accurately or deletes keys at the exact millisecond.

Redis TTL represents a **lifetime limit** rather than a promise of instant disk deletion at timestamp T: expiration uses lazy and active deletion alongside access-time checks. Tests should verify `TTL/PTTL`/`GET` behavior per contract, rather than asserting a background thread deleted the key the instant the clock crossed the deadline.

### 11.2. Atomicity of `SET NX EX` and Lua

A fake:

```java
if (!map.containsKey(key)) {
    map.put(key, value);
}
```

is not atomic across concurrent threads unless synchronized, and still never tests Redis across processes. Redis executes server-side atomic commands such as `SET key value NX EX seconds`. For distributed locks or idempotency, a single-threaded unit fake never proves race-safety.

Real Redis tests need multiple clients/concurrent operations, key expiration, retry policies, and cleanup. Never rely on a single-threaded fake to declare a lock correct. Note that a simple single-instance Redis lock does not automatically guarantee full distributed failure semantics either.

### 11.3. Key serialization/prefix

`StringRedisSerializer`, Jackson JSON serializers, and custom binary formats produce different byte layouts. A cache may work in a Java fake yet fail in production when prefixes, charsets, or serializers shift.

Real tests must verify:

- Keys are actually written under the expected prefix/namespace.
- Serializers read back older/versioned entries.
- TTLs are set properly rather than accidentally staying permanent.
- Null/sentinel values, key types, and Unicode encoding work.
- Cache eviction/fallback preserves business invariants.

### 11.4. Testcontainers Redis

Spring Boot can extract connection details from a Redis container; with Testcontainers `GenericContainer`, image metadata/name matters when using `@ServiceConnection(name = "redis")`. This is an **architectural extension**, not declared in the MongoDB project's dependencies in Section 7.

Redis integration tests should use a version matching production and a real `RedisTemplate`, not a `Map`. Cluster/sentinel behavior, ACLs, TLS, and failover still need higher-tier environments.

## 12. Elasticsearch: mappings, analyzers, and refresh cannot be faked with a list

In a search index, results are not simply "string contains keyword". A fake might use Java `contains` and sort by ID, whereas real Elasticsearch relies on:

- `text` vs. `keyword` mappings and multi-fields.
- Analyzers/normalizers, case folding, stop words, n-grams, and stemming.
- Query DSL `match`/`term`/`range`/`exists` and array/null semantics.
- `_score` relevance, tie-breakers, and `search_after` pagination.
- Refresh: newly indexed documents are not necessarily searchable immediately.
- Index templates, aliases, shard settings, and mapping evolution.
- Cluster version/API compatibility and authorization.

### 12.1. A misleading test

```java
List<Product> matches = products.stream()
        .filter(p -> p.name().contains("cafe"))
        .toList();
```

This is an illustrative Java snippet. It proves nothing about how production Elasticsearch analyzers handle "café/Cafe/cafe". To test search semantics, create a test index with production-like mappings/analyzers, index fixtures, refresh per contract, run real queries, and assert IDs/scores or controlled ordering.

### 12.2. Version mismatches and query DSL

Elasticsearch Java client versions, server versions, and JSON DSL APIs carry compatibility constraints. A mocked client returning `SearchResponse` passes even if the cluster rejects the request or index mappings changed. Run an engine/server version compatible with production (e.g., Elasticsearch Testcontainers) and test mapping creation, queries, sorting, and refreshes.

**Do not force a fake search service to reimplement the entire query DSL.** That wastes effort and rarely matches the real engine. Use fakes for business flows, and containers/clusters for search contracts.

### 12.3. Never treat a single-node container as a cluster test

Shards, replicas, node failures, rolling upgrades, role-based access, and storage performance require dedicated staging/cluster scenarios. Single-node containers cover index mappings and many DSL assertions, not failover and sizing.

## 13. Version compatibility and mapping checklist by service

| Service | Versions to align | Mappings to test | Behaviors never to delegate to fakes |
| --- | --- | --- | --- |
| **MongoDB** | Server, driver, Spring Data Mongo | BSON fields, Decimal128, ID types, indexes, converters | Aggregations, unique indexes, optimistic locking, transactions |
| **Redis** | Server, Lettuce/Jedis, Spring Data Redis | Key prefixes, serializers, TTL units, hash fields | Atomic NX, Lua, expiration, eviction, pub/sub |
| **Elasticsearch** | Server/cluster, Java client, Spring Data ES | Index mappings, analyzers, aliases, nested fields | Query DSL, scoring, refresh, pagination |
| **Cassandra** | Cluster, driver, CQL schema | Partition/clustering keys, codecs, TTLs | Consistency levels, tombstones, paging |
| **Neo4j** | Server, Bolt driver, SDN mapping | Nodes/relationships, labels, Cypher | Transactions/constraints/Cypher planner |
| **DynamoDB** | Service API version/emulator capabilities, SDK | Attribute values, key/index schemas | Conditional writes, eventual TTL behavior, streams, IAM |
| **OpenSearch** | Server/client and managed distro | Index settings/DSL/analyzers | Scoring, refresh, permissions, extensions |

This table guides **test-layer selection**; never assume these products share an abstraction interchangeable enough to substitute for one another. For your real target database, consult the official docs and compatibility matrix for your exact version.

## 14. Choosing between unit tests, slices, integration, and staging

| Goal | Recommended tool | Meaningful PASS signal |
| --- | --- | --- |
| Service validation, DTO mapping | JUnit + Mockito | Service logic and interactions |
| Lightweight stateful workflows | In-memory fake behind persistence port | Domain flow under fake contract |
| MongoDB mappers/repositories | `@DataMongoTest` + MongoDB container | BSON/queries/uniqueness/locking on test engine |
| Redis keys/TTLs/atomicity | Redis container + Spring Data Redis | Key bytes/TTLs/command behavior |
| Elasticsearch queries/relevance | ES container + real client | Index mapping/DSL behavior |
| HTTP/controllers + persistence | `@SpringBootTest` with containers | Spring wiring and request flow |
| Auth/TLS/cluster failover | Isolated staging | Operational/security/topology behavior |
| Migrations/upgrades | Old/new version matrix, staging | Backward compatibility and rollout |
| Performance | Representative dataset + metrics | Latency/throughput resource behavior |

**Not every unit test needs Docker.** What matters is that every claim of "tested" backs onto the right environment rather than substituting mock results for server proof.

### 14.1. `@DataMongoTest` does not auto-rollback like the JPA slice

Unlike `@DataJpaTest`'s transactional rollback, the MongoDB test slice **does not automatically roll back** writes after each test. When tests share a container/database, explicitly clean up data and avoid order dependencies.

In the project, `@BeforeEach repository.deleteAll()` clears documents before each test without dropping indexes. With multiple collections, enforce database/collection isolation and clean up test-only data; never call `dropDatabase()` on a connection not verified as ephemeral.

### 14.2. Testcontainers also has resource limits

Docker runtime availability, image pulls, CPU/memory, networking, and platform security can slow or break tests when environments are constrained. Separate:
- **Test code failure** due to wrong mapping/index/query.
- **Environment failure** due to Docker unavailable or registry access denied.
- **Skipped tests** due to disabled integration profiles.

Never interpret "tests skipped" as integration PASS. Name/tag jobs clearly and surface helpful logs without exposing secrets.

### 14.3. Testing with embedded/emulated services

If an organization mandates emulators due to Docker restrictions in CI:

1. Document the emulator name, version, and supported capabilities.
2. List known incompatibilities or untested behaviors.
3. Keep smoke contract tests running against the real service in another pipeline.
4. Avoid writing emulator workarounds that unnecessarily alter production behavior.
5. Update compatibility tests whenever upgrading drivers or servers.

For MongoDB, an embedded alternative is not the production MongoDB engine unless it literally runs that server version. A "compatible API" only guarantees a documented subset.

## 15. Negative tests needed because fakes routinely miss them

### 15.1. Duplicate keys and unique indexes

In the MongoDB sample, the unique index covers the **pair `(tenant_id,external_ref)`**. Write a positive test for two different tenants sharing `externalRef`, and a negative test for the same tenant. A `HashMap` fake keyed only by `externalRef` might **wrongly forbid** cross-tenant duplication; a fake keyed by `id` might **wrongly allow** duplicate business keys.

### 15.2. Stale optimistic updates

If two reads from a fake return **the exact same mutable object reference**, modifying the first mutates the "stale" reference too, making conflict detection impossible. Real Mongo tests obtain two separate snapshots at the same version, update one, and save the stale one expecting `OptimisticLockingFailureException`.

### 15.3. Mapping mismatches when renaming fields

When changing `@Field("tenant_id")` to `@Field("tenantId")`, a mock keeps returning expected objects. Raw BSON and derived query tests on real Mongo must detect the schema contract change. To test backward compatibility, seed legacy-schema documents using the raw driver and read them with the new mapper.

### 15.4. Time precision and nulls

For `Instant`, test nanosecond boundaries if required by the contract; when storing millisecond BSON Dates, define truncation/rounding rules explicitly. For missing vs. null, assert raw fields rather than only Java object fields.

### 15.5. TTL and expiry

For Redis or Mongo TTL indexes, never assert "data vanishes at the exact millisecond" when the engine performs background deletion. Test the storage contract, TTL configuration, and eventual expiry within a bounded window; use an isolated fake clock for business deadline logic.

### 15.6. Network failures and cancellation

Making a mock throw an exception does not prove the driver raises that same exception class during real timeouts or dropped connections. Use fault injection or Testcontainers `Toxiproxy`/network proxies at the integration tier. Avoid `Thread.sleep` to manufacture races or unrealistic hardcoded network timeouts.

## 16. Testing before/after scenarios when upgrading services

Suppose a team prepares to upgrade a MongoDB major version. An upgrade-readiness checklist:

1. List old/new server versions alongside Boot/Spring Data/driver dependency versions.
2. Read server and driver release notes, focusing on commands and features your app uses.
3. Pin container version A and version B in separate CI jobs.
4. Seed datasets with legacy BSON types and documents faithfully representing existing schemas.
5. Run raw BSON mappings, derived repository queries, aggregations, indexes, sorting, and optimistic locking.
6. Run authorization/transaction tests if the app relies on replica sets/ACLs.
7. Rehearse migrations/index builds against test-only data.
8. Test rollback/downgrade **only if** vendor-supported; never assume downgrades are always safe.
9. Measure latency, query plans, and key/index sizes in staging.
10. Perform a canary rollout with metrics and a rollback runbook.

**Never use the `latest` tag to represent a future server.** Target versions must be the exact versions your team intends to deploy, pinned with review dates.

### 16.1. A Spring Boot upgrade is also a mapping upgrade

Minor or major Spring Data changes can alter converter behavior, query derivation, warnings, or default serializers. Upgrading Spring Boot is therefore never just bumping dependencies and re-running pure unit tests; integration tests on the real engine catch regressions early.

### 16.2. Backward-compatible documents

During rolling deployments, old and new app instances read and write simultaneously. Maintain fixtures covering:

- Older document versions missing new fields.
- Unknown fields added by newer versions.
- Legacy enum values removed from new code.
- Legacy `Decimal128` vs. String representations.
- Changed key naming conventions.
- Optional/null semantics and timestamp precision.
- Index migrations when legacy data contains uniqueness violations.

A fake instantiating objects from the current Java class rarely produces these legacy shapes. Seed raw BSON fixtures in test containers and define explicit fallback/migration policies.

## 17. Common symptoms and diagnostics

| Symptom | Possible cause | Check or fix |
| --- | --- | --- |
| Mockito test green, Mongo query returns empty | Property ↔ BSON field mapping mismatch | Inspect raw BSON + real repository query |
| `BigDecimal` stored as String instead of `Decimal128` | Converter/target type not configured | `@Field(targetType=DECIMAL128)` + raw BSON test |
| Duplicate insert still succeeds | Index not created or wrong index definition | Index management test + duplicate write |
| Mongo test throws "connection refused" | Container not running / wrong URI | `@ServiceConnection` and runtime logs |
| Service test missing bean | `@DataMongoTest` skips ordinary services | `@Import` exact service without loading full app |
| Fake shares object reference, optimistic test passes/fails wrong | No copy/version semantics | Real Mongo `@Version` test |
| Mongo tests interfere across suite | No default rollback / broken cleanup | Delete test data without dropping indexes |
| New driver fails reading old documents | BSON/serializer schema shifted | Legacy fixtures + version matrix |
| Mongo transaction fails in tests | Container topology lacks replica set | Configure proper replica-set test environment |
| Redis TTL fake passes, prod key never expires | TTL omitted, serializer or expiry semantics wrong | Redis container `PTTL`/`GET` test |
| Redis lock gets double-acquired | In-memory check-then-put not atomic | Real Redis atomic command/concurrency test |
| Elasticsearch "cafe" misses/hits "café" wrong | Analyzer/mapping differs from fake | Real index/analyzer/query test |
| Newly written Elasticsearch doc not searchable | Refresh timing differs from fake | Refresh policy or bounded await |
| Staging cluster differs from container | TLS, roles, shards/replicas, cloud features differ | Staging-specific tests |
| CI green yet integration never ran | Docker unavailable, tags skipped | Separate PASS/FAIL/SKIPPED in reports |
| Tests too slow due to Docker per method | Poor container lifecycle | Static container per test class, safe reuse policy |
| Version upgrade breaks queries | Server/driver/mapper incompatibility | Pin A/B matrix, release notes, contract tests |

## 18. Practice exercises

### Exercise 1: Catch a field mapping mismatch

On a learning branch, rename `@Field("tenant_id")` to something else. Run both `OrderLookupServiceUnitTest` and `OrderMongoIntegrationTest`.

**To explain:** The unit mock still passes because it bypasses converters and the real DB. The raw BSON integration test must catch the key mismatch or query miss when fixtures/schemas are verified independently.

### Exercise 2: Switch Decimal128 to another storage type

Try removing `targetType=FieldType.DECIMAL128` from the entity. Inspect the raw `total_amount` type and round-trip behavior. Record the actual Spring Data version behavior rather than guessing `BigDecimal` always turns into BSON String in every release.

### Exercise 3: Turn off auto index creation

Remove `spring.data.mongodb.auto-index-creation=true`. In a clean database without indexes, duplicate writes succeed. Explain why `@CompoundIndex` alone does not guarantee a real index exists.

**Note:** When practicing, use a fresh test-only container/database rather than reusing a collection whose index already exists from an earlier run; otherwise duplicate writes still fail and mislead you.

### Exercise 4: Optimistic locking and two copies

Load two `OrderDocument` copies, modify and save the first, then modify and save the second. Predict the exception and final version. Write a test that does not rely on a fake returning the same object reference.

### Exercise 5: Server version

Run the `buildInfo` command against the MongoDB test container and compare server version to the image tag. When switching image A → B, log the actual result instead of hardcoding a string constant in the test.

### Exercise 6: Redis TTL

Design a `CachePort` for business code. Test deadline logic with a fake clock; test serializer + TTL + key names with a Redis container. State clearly what each tier proved.

### Exercise 7: Elasticsearch search

Create a test-only index with a `text` mapping and chosen analyzer. Index three documents, refresh per contract, query with a real client, and assert IDs. Contrast with a Java `contains` fake to observe the difference.

### Exercise 8: Backward compatibility

Use raw `Document` to insert an order with an older schema (`total_amount` as String), then read it back with the new converter. Decide the policy: accept and convert, one-time migration, or reject with a clear error, and test that exact policy.

## 19. Self-check questions

**1.** Why does a passing Mockito `OrderRepository` test fail to prove MongoDB mapping?

**Answer:** Mockito neither produces BSON, sends queries through a driver/server, nor enforces indexes; it simply returns stubbed objects.

**2.** Is Testcontainers a MongoDB mock?

**Answer:** No. It runs a real MongoDB server in a container, though typically with fewer nodes, simpler config, and less data than production.

**3.** Does `@DataMongoTest` auto-scan ordinary `@Service` beans?

**Answer:** Not like a full application context. When a real service is needed in the Mongo slice, `@Import` it explicitly.

**4.** What does `@Field(targetType=FieldType.DECIMAL128)` protect?

**Answer:** It instructs Spring Data's converter to store `BigDecimal` as BSON `Decimal128`. A raw `Document` assertion confirms the server received that exact type.

**5.** Does having `@CompoundIndex(unique=true)` in code guarantee MongoDB has the index?

**Answer:** Not yet. Index creation must actually be configured/executed; auto-index creation is not always enabled by default.

**6.** Why does a fake Redis Map fail to prove a distributed lock?

**Answer:** Check-then-put on a Map is not equivalent to atomic Redis server commands under concurrency, and fakes rarely model TTLs or failures.

**7.** Why is testing Elasticsearch with `String.contains` insufficient?

**Answer:** It ignores index mappings, analyzers, query DSL, scoring, and engine refresh semantics.

**8.** Does a MongoDB 7 container prove production multi-node failover?

**Answer:** No. Single-container tests validate CRUD/mapping/indexes/queries, not cluster elections, sharding, and operational failures.

**9.** Why do upgrades of Spring Boot or MongoDB require a version matrix in tests?

**Answer:** Mapper/driver/server changes can alter BSON types, command support, indexes, or defaults; testing both old and target versions catches regressions.

**10.** When is a fake still better than a container?

**Answer:** When testing pure business logic, stateful workflows, or controlled exception paths without needing to verify storage semantics. Reserve containers for real service contracts.

## 20. Code review and CI checklist

- [ ] Test names and reports state clearly whether mocks, fakes, emulators, or real services ran.
- [ ] Server versions/container images are pinned to the target compatibility matrix.
- [ ] Driver and Spring Data versions come cleanly from the BOM/dependency tree.
- [ ] BSON/Redis bytes/ES index mappings are tested on the real engine when contractual.
- [ ] Both serialization and deserialization/round-trip are tested against independent expectations.
- [ ] Null/missing, UUID/ObjectId, Decimal128, date precision, and enum converters are accounted for.
- [ ] Unique/index/TTL features are initialized and verified, not merely annotated.
- [ ] Mongo integration tests keep real repositories/mappers instead of mocking the persistence boundary.
- [ ] Negative tests cover duplicates, stale updates, wrong types, and missing context where appropriate.
- [ ] Never expect `@DataMongoTest` to auto-rollback like `@DataJpaTest`.
- [ ] Never use shared mutable fake references to claim concurrency correctness.
- [ ] Redis TTL/atomicity and Elasticsearch analyzers/refresh are tested with real services when needed.
- [ ] Test data stays in isolated databases/indexes/namespaces, never touching production.
- [ ] Docker unavailable ≠ integration PASS; CI reports FAIL vs. SKIPPED transparently.
- [ ] Clustering/auth/TLS/failover/performance are tested separately in staging when relevant.
- [ ] Server/driver/mapper upgrades include a version matrix and legacy fixtures.
- [ ] No real tokens, passwords, or PII live inside test fixtures or logs.

## 21. References

- [Spring Boot 3.5 – Auto-configured Data MongoDB Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@DataMongoTest`, `MongoTemplate`, and Mongo repositories.
- [Spring Boot 3.5 – Testcontainers and Service Connections](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection` and `MongoConnectionDetails`.
- [Spring Data MongoDB – Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): BSON, `@Field`, `@Id`, and conversions.
- [Spring Data MongoDB – Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html): `BigDecimal`/`Decimal128` and custom conversion rules.
- [Spring Data MongoDB – Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html): default auto-index behavior and index lifecycle.
- [Spring Data MongoDB – Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `@Version`, version checks, and write acknowledgement.
- [Testcontainers for Java – MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/): `MongoDBContainer` and replica-set notes.
- [MongoDB Manual – BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/): BSON Date, ObjectId, and Decimal128.
- [MongoDB Manual – Indexes](https://www.mongodb.com/docs/manual/indexes/): compound/unique/TTL index behavior.
- [Redis Documentation – EXPIRE and TTL](https://redis.io/docs/latest/commands/expire/): expiry semantics and key lifetimes.
- [Elasticsearch Reference – Mapping](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping.html): mappings, text/keyword, and analyzer behavior.

**Conclusion:** **An emulator or fake is appropriate when serving unit tests, yet never as proof that a real NoSQL service aligns on version, mapping, and server behavior.** Use mocks/fakes for business logic, real MongoDB/Redis/Elasticsearch in Testcontainers for driver, mapper, query, index, and TTL contracts, and staging clusters for auth, failover, upgrades, and performance. State the exact evidence level of each test honestly to avoid "false green" confidence.
