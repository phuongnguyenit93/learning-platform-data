# Spring Boot testing — @DataMongoTest and testing documents, mapping, and queries

## 1. Why does MongoDB need a separate persistence testing style?

Spring Data MongoDB lets you write Java repositories much like Spring Data JPA. However, MongoDB does not store data in SQL tables/rows, but as **BSON documents** in collections, with nested objects, arrays, BSON types such as ObjectId/Date, indexes, query operators, and transaction semantics that differ from relational databases.

For example, a document might look like:

```json
{
  "_id": {"$oid": "65a000000000000000000001"},
  "item_code": "CAM-001",
  "title": "Camera",
  "category": "camera",
  "price_cents": 3500000,
  "tags": ["new", "sale"],
  "details": {
    "brand": "ACME",
    "fragile": true
  },
  "created_at": {"$date": "2026-11-08T02:30:00Z"}
}
```

This is **illustrative Extended JSON** for readability; the BSON wire format is not raw JSON text. The `_id` value is an example and must not be hardcoded in tests. `created_at` in MongoDB is a BSON Date representing a point in time in milliseconds since the UTC epoch; the original timezone information is not preserved as an `OffsetDateTime` unless stored separately.

A Java class might use `itemCode`, `priceCents`, and `createdAt`, while the actual stored document uses `item_code`, `price_cents`, and `created_at`. At the same time, the repository method `findByCategoryAndPriceCentsGreaterThanEqualOrderByPriceCentsAsc(...)` must be parsed by Spring Data MongoDB, map the Java properties to the right BSON fields, and send the appropriate query to the server.

A unit test that only calls methods on a mocked `MongoRepository` **does not prove** any of the above. This lesson focuses on **`@DataMongoTest`** — a Spring Boot test slice for MongoDB persistence that verifies document mapping, query derivation, `@Query`, and `MongoTemplate` against an isolated test MongoDB server.

**Key takeaway:** `@DataMongoTest` auto-configures MongoDB-related beans; **it does not mean Spring Boot 3.3 will automatically start an embedded MongoDB**. You need to provide a real MongoDB instance in the test environment, such as Testcontainers MongoDB or a dedicated test server.

## 2. Learning objectives

After this lesson, you will be able to:

1. Explain the scope of `@DataMongoTest` and compare it with Mockito unit tests, `@SpringBootTest`, and `@DataJpaTest`.
2. Create a `@Document` with `@Id`, `@Field`, nested record/document, arrays, date field, and a unique index.
3. Use `MongoRepository` to `save`, `findById`, find by business key, filter/sort/paginate, and delete.
4. Write derived queries using the right Java property names, understanding that BSON field names differ from Java names.
5. Write `@Query` JSON using `?0` parameters, and distinguish repository queries from the `MongoTemplate` query DSL.
6. Inspect the document **actually stored in MongoDB** using `org.bson.Document`, rather than only comparing objects returned by mocks.
7. Use MongoDB Testcontainers with `@ServiceConnection`/`@DynamicPropertySource` on Spring Boot 3.3.
8. Know why `@Indexed` does not automatically mean an index has been created; run a real duplicate-key test.
9. Understand that MongoDB writes are not rolled back by default after each `@DataMongoTest` like JPA tests.
10. Keep tests independent, clean up data in the right collection, detect the wrong database, and avoid connecting to production.
11. Evaluate type conversion (`ObjectId`/`String`, `Instant`/BSON Date, null, enum, nested object) and query behavior.
12. Know when to expand from JPA-style repository syntax to MongoDB-specific integration tests.

## 3. A comparison table of testing boundaries

| Test approach | Has Spring context? | Has MongoDB server? | What does it prove? |
| --- | --- | --- | --- |
| Plain JUnit + mock repository | Not needed | No | Business logic with fake data |
| JUnit unit test for custom converter | Maybe not | No | Individual value conversions within the converter's scope |
| `@DataMongoTest` + MongoDB Testcontainers | Yes, **Mongo slice** | Yes, real MongoDB in a container | Mapping, repository, queries, BSON, real indexes |
| `@SpringBootTest` + MongoDB container | Yes, full app | Yes | Service, repository, cross-bean interaction |
| Live HTTP + MongoDB container | Yes, app + HTTP server | Yes | HTTP contract and persistence end-to-end |
| Testing directly against staging database | Depends | Yes | Real engine, but requires clear isolation/credentials |

**The two dimensions are independent:** `@DataMongoTest` decides **which Spring beans are loaded**; Testcontainers decides **which MongoDB server is used**. You do not need a full `@SpringBootTest` context just to use a real MongoDB instance.

## 4. What does `@DataMongoTest` do in Spring Boot 3.3?

In Boot 3.3, the annotation is located at:

```java
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
```

According to the Spring Boot 3.3 documentation, by default it:

- Limits auto-configuration to what is relevant to MongoDB data access.
- Configures an imperative `MongoTemplate` when the appropriate dependencies are on the classpath.
- Scans `@Document` classes and Spring Data MongoDB repositories.
- Configures `MongoClient`/mapping/converter/repository infrastructure via the slice's auto-configurations.
- Does not scan regular `@Component` beans or `@ConfigurationProperties` as a full app would. `@EnableConfigurationProperties` can be used to add a needed properties bean.
- Supports adding appropriate test configuration/converters via `@Import` and valid Spring TestContext mechanisms.
- **Does not guarantee an embedded MongoDB server**.
- **Does not wrap every test method in a rolling-back transaction by default** like `@DataJpaTest`.

Compact template:

```java
@DataMongoTest
class InventoryMongoTest {
    @Autowired MongoTemplate mongoTemplate;
    @Autowired CatalogItemRepository repository;
}
```

The template above only illustrates the annotation. It still needs a configured MongoDB server and repository/document classes. Without a server at the configured URI/host, the first database operation will fail when the client cannot connect.

### 4.1. Why don't regular services appear?

Suppose a `@Service InventoryService` depends on `CatalogItemRepository`, and the test only writes:

```java
@DataMongoTest
class InventoryServiceTest {
    @Autowired InventoryService service;
}
```

The context may fail because `InventoryService` is not scanned by the slice. This is not a MongoDB repository bug. When you want to test the service on real MongoDB data, you can `@Import(InventoryService.class)` into the slice if the dependency graph is small, or use `@SpringBootTest` if many application components are needed.

**Do not stack `@DataMongoTest` with `@SpringBootTest` on the same class** to "combine scopes". Choose one bootstrap strategy according to the goal.

### 4.2. Is MongoDB needed inside a JUnit method?

A `@DataMongoTest` test can load the context without performing immediate I/O; do not treat that as proof that the MongoDB server is running. A real read/write or a `ping` command sent to the database is needed to confirm connectivity.

If a Mongo server exists but credentials/database are wrong, context initialization does not guarantee that queries will return the right results. The sample lesson will `save`, inspect the raw `Document`, and query back via the repository to avoid false positives.

## 5. The MongoDB model: document, collection, _id, BSON, and mapping

In Spring Data MongoDB:

- `@Document(collection="inventory_items")` binds a Java class to a MongoDB collection.
- `@Id` maps Java identity to BSON `_id`.
- `@Field("item_code")` maps the `itemCode` property to the `item_code` field.
- `@Indexed(unique=true)` declares index metadata for a property; **whether the index is actually created on the server depends on the index creation configuration**.
- A nested Java POJO/record can become an embedded BSON document.
- `List<String>` usually becomes a BSON array.
- `Instant` can be mapped to a BSON Date; BSON Date has **millisecond resolution**, and does not automatically preserve nanosecond precision beyond that.

Spring Data MongoDB uses **`MappingMongoConverter`** and mapping metadata. This is not the same serializer layer as Jackson used for REST JSON. Therefore:

- `@Field("item_code")` targets the MongoDB BSON document.
- `@JsonProperty("item_code")` targets the Jackson JSON payload.
- `@JsonNaming`/`@JsonInclude` do not automatically rename BSON fields.
- A REST DTO and a MongoDB document entity may intentionally have different naming conventions.

### 5.1. `@Id String` is not always a BSON String

MongoDB commonly uses BSON `ObjectId` for `_id`. Spring Data MongoDB has a mechanism to convert a `String` ID to `ObjectId` when the string is a valid hex representation, and supports `@MongoId` to control ID mapping to the desired type.

For example, tests should:

- Assert that the generated Java ID is non-null.
- Query the repository with `findById(saved.getId())`.
- Observe that raw `_id` is non-null.
- **Do not** assume raw `_id` is always a String when the Java field is `@Id String`.

If the API requires a string ID with a special structure, explicitly specify `@MongoId(FieldType.STRING)` or an appropriate custom conversion and test the raw BSON type against the contract.

### 5.2. BSON Date does not store a regional timezone

The value `Instant.parse("2026-11-08T02:30:00Z")` is an absolute point in time. MongoDB BSON Date stores milliseconds on the UTC timeline. If the frontend needs to restore the source timezone `Asia/Ho_Chi_Minh` or a user-declared offset, the application must store appropriate extra metadata; BSON Date does not automatically record the full `ZoneId`.

For nanosecond precision, choose a truncate/round policy or use an additional field. This lesson's test uses timestamps with whole seconds, so round-tripping is exact at millisecond resolution.

### 5.3. Nested documents are not JPA relationships

MongoDB allows storing:

```json
{
  "item_code": "CAM-001",
  "details": {
    "brand": "ACME",
    "fragile": true
  }
}
```

This is an embedded document inside a document. It is **not** a foreign key / JPA `@ManyToOne`. When a domain model has references to other documents, consider `@DocumentReference`/`@DBRef`, but choosing reference vs. embed should be based on access patterns, update consistency, and domain lifecycle.

## 6. `MongoRepository`: derived queries and method names

The repository can look familiar:

```java
public interface CatalogItemRepository
        extends MongoRepository<CatalogItem, String> {
    Optional<CatalogItem> findByItemCode(String itemCode);

    List<CatalogItem>
        findByCategoryAndPriceCentsGreaterThanEqualOrderByPriceCentsAsc(
                String category, long minPriceCents);
}
```

Even though the BSON fields may be `item_code` and `price_cents`, **derived query method names rely on Java property names**: `itemCode`, `priceCents`. Spring Data maps property names to MongoDB fields according to the metadata.

Examples:

| Method fragment | Meaning |
| --- | --- |
| `findByItemCode` | Match business key |
| `findByCategory` | Filter by category |
| `PriceCentsGreaterThanEqual` | Filter price greater than or equal to threshold |
| `OrderByPriceCentsAsc` | Sort ascending by Java property `priceCents` |
| `findByCategory(String, Pageable)` | Paginated data and dynamic sorting |
| `countByCategory` | Count documents matching condition |
| `existsByItemCode` | Prove a matching document exists |

**Do not confuse method names with JSON field literals.** Writing `findByPrice_cents` is not the standard way to express `@Field("price_cents")`. Query derivation parses the Java property path.

## 7. `@Query` JSON queries and `?0` parameters

When a derived method gets too long or needs explicit conditions, Spring Data MongoDB supports:

```java
@Query("{ 'category': ?0, 'price_cents': { '$lte': ?1 } }")
List<CatalogItem> findAffordableInCategory(
        String category,
        long maximumPriceCents);
```

`?0` is the first method parameter, `?1` is the second parameter. Spring Data performs parameter binding to avoid fragile manual query string concatenation. The syntax here is a MongoDB JSON-like query string supported by the framework's parser; property names can be mapped according to `MongoPersistentEntity`.

If you call:

```java
repository.findAffordableInCategory("camera", 25000L);
```

the logical query is category equal to "camera" **and** `price_cents` less than or equal to 25000. You do not need to mock the repository to return hardcoded data; create real fixture documents and check the result set.

### 7.1. Do not build queries by concatenating input strings

Avoid styles like:

```java
String queryText =
        "{ 'category': '" + userInput + "' }";
```

This is an **anti-pattern**, never use it in production. When input contains quotes/operators, the query can break or become an injection risk. Use repository parameters, the `Query`/`Criteria` DSL, or framework-supported named parameters.

### 7.2. `@Query` projection is a different contract

You can use `@Query(fields=...)` to fetch only certain fields:

```java
@Query(
    value = "{ 'category': ?0 }",
    fields = "{ 'item_code': 1, 'title': 1 }")
List<CatalogItem> findPartialByCategory(String category);
```

This is an **illustrative snippet**, do not add it to the runnable repository in the sample project. When returning the domain type while selecting only some fields, Java properties excluded from the projection will be null or primitive defaults, easily creating a "document object" with missing data. For APIs using projections, prefer a well-designed projection interface/DTO and test which fields are actually returned.

## 8. `MongoTemplate`: Query/Criteria, reading raw BSON, and detailed operations

`MongoRepository` fits common CRUD/query methods. When you need dynamic queries, projections, aggregations, or update operators, `MongoTemplate` often expresses them directly:

```java
Query query = Query.query(
        Criteria.where("category").is("camera")
                .and("priceCents").gte(10000L));

List<CatalogItem> items =
        template.find(query, CatalogItem.class);
```

This snippet goes inside a test that has `MongoTemplate template`; imports:

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
```

In a mapped query for `CatalogItem.class`, `priceCents` can be converted to the stored field `price_cents`. This is a benefit of mapping metadata, unlike raw driver queries which must directly use the exact BSON field key.

**Distinguish two test layers:**

- `MongoTemplate.find(Query, CatalogItem.class)` → document is mapped to the Java type.
- `template.getCollection("inventory_items").find(new Document(...))` → driver interacts directly with the **raw BSON Document**.

When you want to verify actual `@Field` mapping, a raw BSON assertion carries more weight than comparing two Java objects through the same mapper.

### 8.1. Can MongoDB commands be tested directly?

`template.getDb().runCommand(new Document("ping", 1))` sends a command to the database. It confirms MongoDB responds, but does **not yet** prove mapping or repository logic. Tests with `save`/`find` + raw BSON checks provide much stronger evidence.

## 9. Unique indexes and why tests must check a real server

Declaring:

```java
@Indexed(unique = true)
@Field("item_code")
private String itemCode;
```

is metadata for Spring Data MongoDB. However, **since Spring Data MongoDB 3.0**, automatic index creation is **disabled by default**. Therefore, a duplicate key test may **fail to fail** if the index has not been created.

For this lesson using an empty test container, we explicitly enable index creation:

```java
@DataMongoTest(properties = {
    "spring.data.mongodb.auto-index-creation=true"
})
class CatalogItemMongoTest { }
```

Once the Mongo mapping context knows about `@Document` and the `@Indexed` property, auto index creation can create the index on the collection. For real-world applications, index management should be controlled in deployments/migrations; do not enable auto index creation across all of production just to get green tests without reviewing performance and index creation privileges.

**The right test writes two documents with different IDs but the same business key**, requiring MongoDB to return a duplicate key error. Checking only that the Java annotation exists does not prove the index is enforced in the database.

### 9.1. Duplicate key error ≠ Java validation error

When a real index is created, MongoDB emits a duplicate key error (typically server code 11000). Spring Mongo exception translation can convert this into `org.springframework.dao.DuplicateKeyException`. This is a database-layer error, distinct from a constructor or Bean Validation rejecting a value.

Do not assert the exact server error message because collection/index naming may vary across versions. Assert the appropriate exception type and do not continue using a failed transaction in an invalid way.

### 9.2. Indexes are part of the operational contract

If the application queries by `item_code` across millions of documents, a missing index can allow correctness tests to pass while production performance is terrible. Beyond duplicate-key tests, for critical queries inspect index definitions on the MongoDB test server and consider explain plan/performance tests in an environment reflecting real data, not just a few fixture records.

## 10. Runnable example project: Java 17, Spring Boot 3.3.0, MongoDB Testcontainers

The project below uses a MongoDB container to test document mapping and queries. All read/write operations actually go to MongoDB inside Docker. Because learners' machine setups vary, the MongoDB test class is enabled only when `RUN_MONGO_TESTS=true`; when this variable is absent, **JUnit skips the Mongo tests instead of pretending MongoDB was tested**.

This uses Spring Boot release **3.3.0** so imports/Gradle remain consistent; production should use a version supported by your organization and kept up to date with security patches.

### 10.1. Directory structure

```text
mongo-slice-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/mongo/
    │   ├── MongoLabApplication.java
    │   ├── ItemDetails.java
    │   ├── CatalogItem.java
    │   └── CatalogItemRepository.java
    └── test/java/example/mongo/
        └── CatalogItemMongoTest.java
```

### 10.2. `settings.gradle`

```groovy
rootProject.name = 'mongo-slice-lab'
```

### 10.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:mongodb'

    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-data-mongodb` provides imperative Spring Data MongoDB, the MongoDB Java driver, and mapping/repository infrastructure. `spring-boot-testcontainers` adds `@ServiceConnection` support in Spring Boot 3.3. The two `org.testcontainers` modules provide `MongoDBContainer` and JUnit 5 lifecycle integration.

**Execution prerequisites:** JDK 17, a compatible Gradle Wrapper (e.g., Gradle 8.5), Docker/compatible Testcontainers runtime when tests are enabled, and permission to pull image `mongo:7.0`. The example does not put production Mongo credentials in source. For projects using cloud MongoDB/Atlas, replace with an isolated test URI and test database in a test profile; never point tests at a production cluster.

### 10.4. `MongoLabApplication.java`

**`src/main/java/example/mongo/MongoLabApplication.java`:**

```java
package example.mongo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MongoLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(MongoLabApplication.class, args);
    }
}
```

This class is the primary Boot configuration in the same `example.mongo` package as the document/repository/tests. `@DataMongoTest` uses slice filters, so it does not automatically load every ordinary service even though the application class has `@SpringBootApplication`.

### 10.5. Nested value object `ItemDetails.java`

**`src/main/java/example/mongo/ItemDetails.java`:**

```java
package example.mongo;

public record ItemDetails(String brand, boolean fragile) {}
```

A Java 17 record is an immutable value object. Spring Data MongoDB can map it to a nested BSON object. In the demo, the two fields are stored inside the `details` document, with no separate collection for `ItemDetails`.

### 10.6. Document `CatalogItem.java`

**`src/main/java/example/mongo/CatalogItem.java`:**

```java
package example.mongo;

import java.time.Instant;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "inventory_items")
public class CatalogItem {
    @Id
    private String id;

    @Indexed(unique = true)
    @Field("item_code")
    private String itemCode;

    private String title;
    private String category;

    @Field("price_cents")
    private long priceCents;

    private List<String> tags;

    @Field("created_at")
    private Instant createdAt;

    private ItemDetails details;

    protected CatalogItem() {
        // Spring Data mapping constructor.
    }

    public CatalogItem(
            String itemCode,
            String title,
            String category,
            long priceCents,
            List<String> tags,
            Instant createdAt,
            ItemDetails details) {
        this.itemCode = itemCode;
        this.title = title;
        this.category = category;
        this.priceCents = priceCents;
        this.tags = List.copyOf(tags);
        this.createdAt = createdAt;
        this.details = details;
    }

    public String getId() {
        return id;
    }

    public String getItemCode() {
        return itemCode;
    }

    public String getTitle() {
        return title;
    }

    public String getCategory() {
        return category;
    }

    public long getPriceCents() {
        return priceCents;
    }

    public List<String> getTags() {
        return tags;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public ItemDetails getDetails() {
        return details;
    }
}
```

Explanation:

- `@Document(collection="inventory_items")` fixes the collection name.
- `@Id String id` uses Spring Data MongoDB ID mapping, which can be converted to BSON ObjectId.
- `@Field("item_code")`, `@Field("price_cents")`, and `@Field("created_at")` set BSON keys different from the Java names.
- `@Indexed(unique=true)` declares index metadata, but you must ensure the index is actually created in tests.
- `tags` becomes an array, `details` becomes a nested BSON document, and `Instant` becomes a BSON Date with millisecond precision.
- The `protected` no-arg constructor is used for materialization if needed; getters let tests observe state.
- `List.copyOf(tags)` creates an immutable snapshot, which does not mean the MongoDB array is immutable after being saved.

If the domain allows null tags, the sample constructor would throw an NPE; in the demo, fixtures always supply a non-null list. This is a limitation of the test model, not a rule enforced by MongoDB itself.

### 10.7. Repository `CatalogItemRepository.java`

**`src/main/java/example/mongo/CatalogItemRepository.java`:**

```java
package example.mongo;

import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface CatalogItemRepository
        extends MongoRepository<CatalogItem, String> {

    Optional<CatalogItem> findByItemCode(String itemCode);

    List<CatalogItem>
        findByCategoryAndPriceCentsGreaterThanEqualOrderByPriceCentsAsc(
                String category, long minimumPriceCents);

    @Query("{ 'category': ?0, 'price_cents': { '$lte': ?1 } }")
    List<CatalogItem> findAffordableInCategory(
            String category, long maximumPriceCents);

    Page<CatalogItem> findByCategory(
            String category, Pageable pageable);
}
```

`MongoRepository<CatalogItem,String>` creates a CRUD repository. `findByItemCode` uses the `itemCode` property mapped to BSON `item_code`. The derived price query uses `priceCents` and sorts ascending. `@Query` writes a Mongo filter by category and `$lte`. `findByCategory` with `Pageable` tests paging/sorting.

## 11. Runnable test file: @DataMongoTest + MongoDBContainer

**`src/test/java/example/mongo/CatalogItemMongoTest.java`:**

```java
package example.mongo;

import java.time.Instant;
import java.util.List;

import org.bson.Document;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@EnabledIfEnvironmentVariable(
        named = "RUN_MONGO_TESTS",
        matches = "true"
)
@Testcontainers
@DataMongoTest(properties = {
        "spring.data.mongodb.auto-index-creation=true"
})
class CatalogItemMongoTest {
    @Container
    @ServiceConnection
    static MongoDBContainer mongo =
            new MongoDBContainer("mongo:7.0");

    @Autowired
    CatalogItemRepository repository;

    @Autowired
    MongoTemplate template;

    private static final Instant FIXED_TIME =
            Instant.parse("2026-11-08T02:30:00Z");

    private CatalogItem item(
            String code, String category, long price) {
        return new CatalogItem(
                code,
                "Item " + code,
                category,
                price,
                List.of("new"),
                FIXED_TIME,
                new ItemDetails("ACME", false));
    }

    @BeforeEach
    void cleanBefore() {
        repository.deleteAll();
    }

    @AfterEach
    void cleanAfter() {
        repository.deleteAll();
    }

    @Test
    void savesAndReloadsMappedDocument() {
        CatalogItem original = new CatalogItem(
                "CAM-001",
                "Camera",
                "camera",
                3500000L,
                List.of("new", "sale"),
                FIXED_TIME,
                new ItemDetails("ACME", true));

        CatalogItem saved = repository.save(original);

        assertNotNull(saved.getId());

        Document raw = template
                .getCollection("inventory_items")
                .find(new Document("item_code", "CAM-001"))
                .first();

        assertNotNull(raw);
        assertNotNull(raw.get("_id"));
        assertEquals("CAM-001", raw.getString("item_code"));
        assertEquals("Camera", raw.getString("title"));
        assertEquals("camera", raw.getString("category"));
        assertEquals(3500000L,
                ((Number) raw.get("price_cents")).longValue());
        assertEquals(
                List.of("new", "sale"),
                raw.getList("tags", String.class));
        assertFalse(raw.containsKey("itemCode"));
        assertFalse(raw.containsKey("priceCents"));

        Document nested =
                raw.get("details", Document.class);
        assertNotNull(nested);
        assertEquals("ACME", nested.getString("brand"));
        assertTrue(nested.getBoolean("fragile"));

        CatalogItem reloaded = repository
                .findByItemCode("CAM-001")
                .orElseThrow();

        assertEquals(saved.getId(), reloaded.getId());
        assertEquals(3500000L, reloaded.getPriceCents());
        assertEquals(FIXED_TIME, reloaded.getCreatedAt());
        assertEquals("ACME", reloaded.getDetails().brand());
        assertTrue(reloaded.getDetails().fragile());
    }

    @Test
    void derivedQueryUsesJavaPropertiesAndSortsPrice() {
        repository.saveAll(List.of(
                item("CAM-LOW", "camera", 10000L),
                item("CAM-MID", "camera", 25000L),
                item("CAM-HIGH", "camera", 90000L),
                item("ACC-ONE", "accessory", 5000L)));

        List<CatalogItem> result = repository
                .findByCategoryAndPriceCentsGreaterThanEqualOrderByPriceCentsAsc(
                        "camera", 20000L);

        assertEquals(
                List.of("CAM-MID", "CAM-HIGH"),
                result.stream().map(CatalogItem::getItemCode)
                        .toList());
    }

    @Test
    void annotatedMongoQueryBindsParameters() {
        repository.saveAll(List.of(
                item("CAM-LOW", "camera", 10000L),
                item("CAM-MID", "camera", 25000L),
                item("CAM-HIGH", "camera", 90000L),
                item("ACC-ONE", "accessory", 5000L)));

        List<CatalogItem> affordable = repository
                .findAffordableInCategory(
                        "camera", 25000L);

        assertEquals(
                java.util.Set.of("CAM-LOW", "CAM-MID"),
                affordable.stream()
                        .map(CatalogItem::getItemCode)
                        .collect(java.util.stream.Collectors.toSet()));
    }

    @Test
    void mongoTemplateCriteriaMapsPropertyNames() {
        repository.saveAll(List.of(
                item("CAM-LOW", "camera", 10000L),
                item("CAM-HIGH", "camera", 90000L),
                item("ACC-ONE", "accessory", 120000L)));

        Query query = Query.query(
                Criteria.where("category").is("camera")
                        .and("priceCents").gte(50000L));

        List<CatalogItem> result =
                template.find(query, CatalogItem.class);

        assertEquals(1, result.size());
        assertEquals("CAM-HIGH",
                result.get(0).getItemCode());
    }

    @Test
    void pageableQuerySortsWithoutDependingOnNaturalOrder() {
        repository.saveAll(List.of(
                item("CAM-LOW", "camera", 10000L),
                item("CAM-MID", "camera", 25000L),
                item("CAM-HIGH", "camera", 90000L)));

        Page<CatalogItem> firstPage = repository.findByCategory(
                "camera",
                PageRequest.of(0, 2,
                        Sort.by(Sort.Direction.DESC, "priceCents")));

        assertEquals(3, firstPage.getTotalElements());
        assertEquals(2, firstPage.getContent().size());
        assertEquals(
                List.of("CAM-HIGH", "CAM-MID"),
                firstPage.getContent().stream()
                        .map(CatalogItem::getItemCode)
                        .toList());
    }

    @Test
    void uniqueIndexRejectsDuplicateBusinessKey() {
        repository.save(
                item("UNIQUE-ITEM", "camera", 10000L));

        assertThrows(DuplicateKeyException.class,
                () -> repository.save(
                        item("UNIQUE-ITEM", "accessory", 20000L)));
    }

    @Test
    void deletingOneDocumentDoesNotDeleteOthers() {
        CatalogItem first = repository.save(
                item("DEL-ONE", "camera", 10000L));

        CatalogItem second = repository.save(
                item("DEL-TWO", "camera", 20000L));

        repository.deleteById(first.getId());

        assertFalse(repository.findById(first.getId())
                .isPresent());
        assertTrue(repository.findById(second.getId())
                .isPresent());
    }

    @Test
    void mongoServerReallyAnswersCommands() {
        Document result = template.getDb()
                .runCommand(new Document("ping", 1));

        assertEquals(
                1.0d,
                ((Number) result.get("ok")).doubleValue());
    }
}
```

**Total of 8 test methods** in this class. When `RUN_MONGO_TESTS=true` and Docker/runtime are ready, all 8 are expected to pass against the MongoDB server started by Testcontainers. When the variable is not enabled, JUnit **skips** the class: there is no proof that queries ran against MongoDB in that run.

### 11.1. Why use a single test class and static container

A static `@Container` is normally managed by the Testcontainers JUnit extension for the class lifecycle. Spring's TestContext can cache application contexts longer than a container's lifecycle; if a context is shared with a connection to a static container that stopped in an earlier test class, another test class can hit connection refused.

In this lab, only one `@DataMongoTest` class declares the Mongo container, so the lifecycle is straightforward. In larger projects, consider a shared container bean managed by Spring Boot or a singleton container lifecycle consistent with context caching and test isolation.

### 11.2. What makes a "raw BSON" test stronger than a mock test?

`savesAndReloadsMappedDocument` simultaneously verifies:

1. The repository actually writes a document with a non-null `_id`.
2. The collection is named `inventory_items`.
3. The BSON keys are `item_code` and `price_cents`, not the Java property names `itemCode`/`priceCents`.
4. `tags` becomes a BSON array, and `details` becomes a nested document.
5. The raw MongoDB document stores the right values and the repository loads them back into a Java object.
6. `Instant` round-trips for a fixed timestamp matching BSON millisecond precision.

If you only use `when(repository.findByItemCode(...)).thenReturn(Optional.of(...))`, you have zero evidence for any of these six things.

### 11.3. Why assert ordered results in query A but not in query B?

The derived query method declares `OrderByPriceCentsAsc`, so it has a clear expected order. The `@Query`-annotated method in `findAffordableInCategory` **does not specify a sort**, so the test compares a `Set` of codes rather than assuming MongoDB returns documents in insertion order.

**Never** rely on MongoDB's "natural order" as an API contract. If ordering is needed, declare a `Sort` or sort in the query; with paging, use a stable sort (and potentially a tie-breaker) to avoid duplicates or skipped items when data changes.

### 11.4. Why enable auto-index-creation in the test?

The duplicate key test needs a real MongoDB unique index on `item_code`. `@Indexed(unique=true)` provides the metadata; configuring `spring.data.mongodb.auto-index-creation=true` lets Spring Data create the index from that metadata in the test context. Without the index, two documents with different `_id`s but the same `item_code` can be saved without error.

In production, indexes should be managed via proper migrations/deployments, with reviewed index names and rolling changes. Tests can use `template.indexOps(CatalogItem.class).getIndexInfo()` to inspect created indexes.

## 12. Running tests and understanding the SKIP state

### 12.1. Without Docker

Linux/macOS:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

If `RUN_MONGO_TESTS` is not set, `CatalogItemMongoTest` is **disabled** by `@EnabledIfEnvironmentVariable`. Gradle may report a successful build, but **no MongoDB integration tests were executed**. This is a safe design so the example does not accidentally connect to a local/prod server when a machine lacks Docker.

### 12.2. With Docker, explicitly enabling Mongo tests

Linux/macOS:

```bash
RUN_MONGO_TESTS=true ./gradlew test \
    --tests example.mongo.CatalogItemMongoTest
```

Windows PowerShell:

```powershell
$env:RUN_MONGO_TESTS = 'true'
.\gradlew.bat test --tests example.mongo.CatalogItemMongoTest
Remove-Item Env:RUN_MONGO_TESTS
```

**8 tests are expected to pass** if the environment has a compatible Docker/Testcontainers runtime, the `mongo:7.0` image can be pulled, and Maven Central dependencies are accessible.

**This result is expected behavior, not an execution result measured while writing this article.** Never fabricate a MongoDB port/container ID, actual log output, or execution time.

### 12.3. Want CI to always require running Mongo tests?

Do not use conditional skipping if CI policy treats *database integration as mandatory*. In that case, remove `@EnabledIfEnvironmentVariable` and run on a CI agent that always has Docker; if MongoDB fails to start, the test **must fail** rather than be skipped. You can separate Gradle tasks/source sets for fast unit tests and integration tests, while clearly reporting executed/skipped counts.

## 13. `@ServiceConnection` vs. `@DynamicPropertySource`

`@ServiceConnection` comes from Spring Boot 3.3 Testcontainers integration. On a typed `MongoDBContainer`, it supplies `MongoConnectionDetails` so the auto-configured Mongo client points to the right container. Connection details take precedence over certain regular connection properties.

Configuration in the lab:

```java
@Container
@ServiceConnection
static MongoDBContainer mongo =
        new MongoDBContainer("mongo:7.0");
```

You do not need to manually call `mongo.getReplicaSetUrl()` to set `spring.data.mongodb.uri` when using this approach.

If you do not use `@ServiceConnection`, you can replace it with Spring TestContext's `@DynamicPropertySource`:

```java
@Container
static MongoDBContainer mongo =
        new MongoDBContainer("mongo:7.0");

@DynamicPropertySource
static void mongodbProperties(
        DynamicPropertyRegistry registry) {
    registry.add(
            "spring.data.mongodb.uri",
            mongo::getReplicaSetUrl);
}
```

The snippet above is an **alternative** inside a `@Testcontainers` class (requires `DynamicPropertySource`/`DynamicPropertyRegistry` imports). **Do not apply both** approaches to the same container unless required and you clearly understand precedence.

### 13.1. MongoDBContainer and replica set

Testcontainers `MongoDBContainer` typically provides a MongoDB instance and connection URL suitable for tests, with support for replica set configuration in the container module. Using a replica set matters if you later want to test MongoDB transactions or change streams. However, a typical `@DataMongoTest` performing the CRUD/queries above **does not automatically open a Mongo transaction** just because a replica set exists.

### 13.2. Do not accidentally connect to local 27017

If a test omits connection details and the MongoDB driver is present, Spring Boot may fall back to default connection settings such as localhost `27017` (depending on version/config). If a MongoDB process happens to be running there on the machine, the test might **pass against the wrong database** or delete other test data.

With Testcontainers, supply the URI from the container via service connection or dynamic properties and control the test environment. Do not rely on localhost 27017 always being empty or safe.

## 14. Why don't MongoDB tests auto-rollback like @DataJpaTest?

With `@DataJpaTest` and a relational transaction manager, the Spring Boot test slice usually starts a test-managed transaction and **rolls back after the test method**. With MongoDB, `@DataMongoTest` **does not provide the same rollback mechanism by default**.

MongoDB transactions have their own requirements:

- The MongoDB deployment needs a topology that supports transactions (such as a replica set or appropriate sharded cluster).
- Spring Data MongoDB usually needs `MongoTransactionManager`/reactive transaction manager and properly configured session/transaction participation.
- A test method annotated with `@Transactional` without a suitable transaction manager **does not** turn writes into automatic rollbacks.
- Data written outside an appropriate transaction persists until deleted, the collection is dropped, or the database is destroyed.

In the lab:

```java
@BeforeEach
void cleanBefore() {
    repository.deleteAll();
}

@AfterEach
void cleanAfter() {
    repository.deleteAll();
}
```

These two callbacks ensure the test container's collection contains only the current method's fixtures, assuming **no other concurrent writer is accessing the same database**.

**Never use `repository.deleteAll()` against staging/production MongoDB.** The data in the lab belongs to an isolated test container. With a shared DB, use a separate database-per-test or logical database, unique keys, and cleanup only for documents created by the test; MongoDB does not have SQL schemas in the JPA sense.

### 14.1. Should you use `template.dropCollection(CatalogItem.class)`?

If you drop the collection, you also delete **its indexes**. Subsequent duplicate key tests may lose the unique index if auto index creation only ran when the mapping context initialized.

The sample project uses `deleteAll()` to **delete documents while keeping the collection and indexes**. If a test needs to drop the collection, manage recreating the index intentionally (e.g., `ensureIndex`) or create a fresh database/container.

### 14.2. Cleanup on both sides does not create automatic transaction isolation

In parallel tests sharing a Mongo container/database, two methods can delete each other's data. `@BeforeEach`/`@AfterEach` keep sequential tests independent, **they are not a concurrency solution**.

For parallel tests, use a separate database/collection per test or an appropriate Testcontainers isolation strategy. Do not enable JUnit parallel execution on shared Mongo state and try to patch it with `Thread.sleep`.

## 15. `@Indexed`, collection lifecycle, and persistence index tests

### 15.1. Auto-index-creation is off by default

Spring Data MongoDB documentation states that auto index creation must be explicitly enabled from version 3.0 onward. This prevents unexpected collection/index changes when the application starts.

Therefore, `uniqueIndexRejectsDuplicateBusinessKey` only passes for the right reason if the index actually exists. It is an **important integration test** because the annotation alone does not guarantee the MongoDB server created the index.

### 15.2. Creating an index with MongoTemplate when needed

In an advanced test/sandbox:

```java
template.indexOps(CatalogItem.class)
        .ensureIndex(
                new Index()
                        .on("itemCode", Sort.Direction.ASC)
                        .unique());
```

This **illustrative** snippet needs imports `org.springframework.data.mongodb.core.index.Index` and `org.springframework.data.domain.Sort`, run in a context with `template`. Index operations can map the `itemCode` property to field `item_code`; verify against actual `getIndexInfo()` when standardizing index conventions.

Do not run this indiscriminately on production/shared DBs in every test. When a collection already contains duplicate documents, creating a unique index will fail — that is a data state requiring migration/cleanup, not just changing an annotation.

### 15.3. Index uniqueness on null/missing

MongoDB unique indexes have specific rules regarding missing/null values, compound indexes, partial filters, and sparse indexes. If `item_code` is optional, a standard unique index may reject multiple documents missing the field in a way that differs from a SQL unique constraint. Design a `partialFilterExpression` or sparse index matching the business contract if multiple documents without the key are allowed.

The sample project always supplies a non-null `itemCode`, so do not infer full optional unique key semantics from that duplicate test.

## 16. Null, missing, arrays, and query semantics in MongoDB

In a document database:

```json
{"details": null}
```

is stored differently from:

```json
{}
```

For some MongoDB queries, the predicate `{field: null}` can match both explicit null and missing fields. To distinguish them, use `$exists` and appropriate conditions, verified on a real server.

In Java:

- A `null` property may be omitted from the BSON document depending on mapping behavior/config.
- Primitives like `long priceCents` default to 0 and do not explicitly represent missing data.
- `List<String>` and arrays can map to BSON arrays.
- Equality queries on an array field have special semantics: matching a scalar can match an array containing that scalar.
- `$elemMatch` is required when multiple conditions must apply to the **same element** of an array of embedded documents.
- `$in`, `$nin`, `$exists`, `$type`, and `$regex` should be tested with edge cases if they belong to the public query contract.

**Do not impose SQL NULL semantics onto MongoDB.** Null vs. absent cases should use raw document tests and specific MongoDB predicates.

### 16.1. Experimenting with `exists`

Snippet using `MongoTemplate`:

```java
Query missingDetails = Query.query(
        Criteria.where("details").exists(false));

List<CatalogItem> result =
        template.find(missingDetails, CatalogItem.class);
```

This illustrative snippet requires documents without the `details` field; the default lab always creates `details`, so there is no fixture for this case. Add raw BSON fixtures and clear expectations before asserting.

### 16.2. Date queries and timezones

BSON Date stores instants in milliseconds. If you filter events starting from the beginning of day "2026-11-08" in `Asia/Ho_Chi_Minh`, you must convert the local day boundary to UTC instants using `ZoneId` and then query `createdAt` by range.

Do not use local `LocalDateTime` and assume it is UTC. For daylight-saving zones, a day boundary can have 23 or 25 hours; choose `ZonedDateTime`/`ZoneId` per business rules and test DST transition days.

## 17. Mapping tests, JSON REST tests, and converter tests are not the same

Entity example:

```java
@Field("item_code")
private String itemCode;
```

When saved to MongoDB, the key is `item_code`. However, if a controller returns `CatalogItem` directly via Jackson without configuring Jackson naming, the JSON response may be `itemCode`, because Jackson uses bean property names.

This is not necessarily a bug if the REST contract and storage schema differ. How to test each:

- **`@DataMongoTest`:** assert raw BSON field `item_code` and Spring Data mapping.
- **`@JsonTest`:** assert Jackson JSON property names, enums, and date formats of the REST DTO.
- **`@WebMvcTest`/`@WebFluxTest`:** assert inbound/outbound HTTP JSON mapping.
- **`@SpringBootTest`:** verify the service coordinating database + controller if that is the goal.

Do not use `ObjectMapper.writeValueAsString(entity)` to conclude that a BSON document has those keys; Jackson and `MappingMongoConverter` are two separate mechanisms.

### 17.1. Custom conversions

If storing a `Money` value object or a `UUID`/`Instant` in a custom format, Spring Data MongoDB provides `MongoCustomConversions` and `@ReadingConverter`/`@WritingConverter`. When testing with `@DataMongoTest`, ensure custom converters are **actually present in the slice context** via an appropriate configuration (possibly `@Import`). If a converter is a regular `@Component` outside the slice scan, the test may fall back to default conversion and behave differently from the full app.

Converter tests should cover both directions:

1. Java value → raw BSON type/value.
2. Raw BSON → Java value.
3. Negative cases: unsupported format or precision overflow.
4. Query mapping checks if the converter affects query criteria.

## 18. `@Version` and optimistic locking in MongoDB

Spring Data MongoDB supports `@Version` for optimistic locking: when updating a versioned document, the update query checks the current version and rejects stale updates.

Entity snippet addition:

```java
@Version
private Long version;
```

This is a **snippet**, not part of the runnable class in Section 10. It needs `import org.springframework.data.annotation.Version`, a getter, and version persistence per mapping conventions. For an optimistic locking test:

1. Save the document initially and capture its version.
2. Read two independent snapshots.
3. Modify and save snapshot A.
4. Attempt to save stale snapshot B, expecting an optimistic locking failure.
5. Verify the persisted document was not overwritten by the stale version.

Some accompanying conditions:

- Write concern must be sufficient to detect unmatched updates/version conflicts.
- Transaction/driver behavior can influence how the error surfaces.
- Do not assert the version field only on an in-memory object; read back the server state.

The sample project focuses on mapping/queries, so it does not add optimistic locking to the entity to avoid mixing behaviors outside the main scope.

## 19. Sorting, paging, projections, and changing data

`Page<CatalogItem>` from `MongoRepository` can execute both a page query and a count query. In the lab, paging is asserted with:

```java
PageRequest.of(
        0,
        2,
        Sort.by(Sort.Direction.DESC, "priceCents"))
```

Ordering relies on the Java property `priceCents`, which Spring Data maps to the stored field. When two documents have the same price, their relative order may be unstable; in real APIs, add a tie-breaker (e.g., `itemCode` or `_id`) if stable paging is required:

```java
PageRequest.of(
        0, 20,
        Sort.by(Sort.Direction.DESC, "priceCents")
            .and(Sort.by("itemCode")))
```

This is an illustrative snippet; check indexes/ordering and schema against real data volumes. In continuously updated systems, offset pagination can duplicate or skip items across requests if documents are inserted/updated; cursor/keyset pagination is more appropriate for some flows.

### 19.1. Projections do not always return a full entity

A projection query selecting only `item_code`/`title` will leave unselected fields as null/zero if materialized into a full entity type. Use a projection interface/DTO with a clear contract; test the exact fields returned, and never treat a partial entity as a complete entity to save back to the database.

### 19.2. Aggregation pipelines when query logic exceeds derived methods

MongoDB has aggregation stages `$match`, `$group`, `$unwind`, `$project`, and `$sort`. Spring Data provides the `Aggregation` DSL and `@Aggregation` repositories. For complex aggregations:

- Test the pipeline on a real MongoDB server with fixtures covering edge cases.
- Check output shape and numeric types (`int`/`long`/`Decimal128`).
- Verify indexes/query plans when performance is a requirement.
- Do not treat a mocked `List` result as proof that an aggregation expression is valid.

## 20. MongoDB transactions: when are they needed and when not?

MongoDB supports multi-document transactions on suitable deployments such as replica sets/sharded clusters, though they carry overhead and specific limitations. `@DataMongoTest` does not automatically provide a transaction manager the way `@DataJpaTest` does for SQL.

If a business use case requires atomic multi-document updates:

- Configure `MongoTransactionManager` or reactive transaction manager for the stack in use.
- Use a Mongo deployment that supports transactions.
- Write tests verifying commit/rollback by reading data back from the server after the transaction.
- Deliberately trigger an error between two writes and assert partial updates do not remain upon rollback.
- Avoid using test cleanup via `deleteAll()` as proof that transactions rolled back: cleanup and transaction logic are two separate things.

**Do not put `@Transactional` on a Mongo test and assume all writes roll back.** Tests must actually verify the transaction manager, session participation, and server behavior.

### 20.1. Single-document atomicity

Even without multi-document transactions, MongoDB provides **single-document atomicity** for single-document write operations. When a use case only updates fields within one document, you can use atomic update operators or find-and-modify as appropriate instead of opening a multi-document transaction.

Tests should verify the actual outcome of `$inc`, `$set`, concurrency, and versioning if business rules require them; full-document repository `save` is not always equivalent to an atomic conditional update.

## 21. Reactive MongoDB: do not mix two stacks in one sample test

MongoDB also has a reactive driver, `ReactiveMongoTemplate`, and `ReactiveMongoRepository`, along with Reactor `Mono`/`Flux`. `@DataMongoTest` can involve reactive MongoDB data auto-configurations depending on the classpath/test slice; however, this runnable lesson **only uses imperative `MongoRepository` and `MongoTemplate`** from `spring-boot-starter-data-mongodb`.

If a project uses reactive repositories:

- Add `spring-boot-starter-data-mongodb-reactive` per Boot version.
- Use `ReactiveMongoRepository`/`ReactiveMongoTemplate`.
- Use `StepVerifier` to assert Publisher signals, and never call `block()` on a production event loop.
- Keep driver/configurations and Testcontainers MongoDB URI consistent.
- Design transaction/context propagation according to reactive semantics rather than extrapolating from imperative thread-local transactions.

**Do not copy a `MongoRepository` method returning `List` into reactive code and treat it as equivalent to `Flux` in a nonblocking stack.**

## 22. Why can a real server still give false confidence?

A `@DataMongoTest` with a MongoDB container gives much stronger evidence than mocks, yet still does not prove everything on its own:

- The container MongoDB version may differ from MongoDB Atlas/production cluster.
- Sharding, replica set topology, transaction settings, or user roles may differ.
- The test database has few documents, so slow queries/index scans will not show up.
- A test container does not represent production TLS, auth, proxies, or network latency.
- `@DataMongoTest` does not load business services/controllers outside the slice.
- Custom converters/index migrations or application listeners may not be loaded by the slice.
- Failover/replication consistency, eventual consistency, and timeouts require separate tests.
- Atlas Search, change streams, vector indexes, and provider-specific features require an environment with matching server capabilities.
- The sample project has not tested migrations/index rollout, only enabling auto-index-creation for testing.

Passing tests should only be interpreted within **the configured and observed boundaries**.

## 23. Connecting to a test MongoDB server other than Testcontainers

If CI does not have Docker, a dedicated test MongoDB instance can be used. However, explicitly configure the URI via a test profile/environment, do not use production credentials, and do not allow tests to accidentally connect to localhost 27017.

Example **for illustration only, unusable URL**:

```properties
spring.data.mongodb.uri=mongodb://test-db.example.invalid:27017/inventory_test
```

If real authentication/TLS is used, use environment variables or a secret manager rather than hardcoding passwords in source. To protect tests:

- Separate database per test run or namespace/collection prefix.
- A user restricted to test databases only.
- Clean up only documents/collections owned by the test.
- Verify cluster identity, database name, or safe connection parameters.
- Never run `dropDatabase`/`deleteAll` on a shared production database.
- Have timeouts and fail-fast handling if MongoDB is unreachable.

Testcontainers is usually more convenient because it spins up an isolated MongoDB, though nothing forces Docker if the organization already provides a safe test DB.

## 24. Troubleshooting: which layer is the test failing at?

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` for service | `@DataMongoTest` does not scan ordinary services | Intentional `@Import` or `@SpringBootTest` |
| `MongoTimeoutException`/server selection timeout | MongoDB server not running, wrong URI, network blocked | Check Testcontainers/URI/credentials |
| `Could not find a valid Docker environment` | Docker missing or runtime not permitted | Run Mongo tests on a Docker-enabled CI node |
| Test skipped while Gradle stays green | `RUN_MONGO_TESTS` not enabled | Distinguish SKIPPED from PASSED |
| Raw BSON field is not `item_code` | Incorrect `@Field`/converter | Inspect Mongo mapping metadata, raw Document |
| Repository query does not match `price_cents` | Wrong derived property path or `@Query` field key | Check Java property vs. BSON key |
| `DuplicateKeyException` does not occur | Unique index not created | Enable index creation in test or `ensureIndex` |
| Duplicate key fails immediately on index creation | DB already has duplicate data | Clean up before index migration, use separate DB |
| Test passes alone, fails in suite | Shared collection, context cache, container lifecycle | Per-class/run isolation, intentional cleanup |
| Mongo writes remain after test | No default test-managed rollback | Delete/separate DB, do not assume JPA-like behavior |
| Java String ID differs from raw ObjectId | Mongo ID conversion | Use `findById` and `@MongoId` if a specific type is needed |
| BSON Date differs in nanoseconds | Millisecond precision of BSON Date | Standardize precision in contract |
| `getIndexInfo` lacks annotated index | Auto-index-creation off or collection recreated | Configure explicit index management |
| Custom converter not applied | Converter bean not scanned in slice | `@Import` test config with conversions |
| Upgrading to Boot 4 gives `DataMongoTest` package error | Test modules/packages restructured | Use matching BOM/starter/imports for Boot 4 |
| MongoDB authentication fails | Wrong credentials/auth database | Use test account and separate URI/config |
| JSON REST fields differ from BSON fields | Jackson vs. Mongo converter differ | Test `@JsonTest` separately and raw Mongo mapping |

### 24.1. Connection errors are not query errors

If MongoDB is unreachable, the driver may wait for server selection and then throw a timeout; this does **not** prove the repository method signature is wrong. Before changing `@Query`:

1. Check whether the MongoDB server/container is running.
2. Verify URI/port, database, and authentication.
3. Run a real `ping`.
4. Check whether the collection contains fixture data.
5. Only then inspect raw BSON field names/query conditions.

### 24.2. An empty query result is not necessarily a query syntax error

MongoDB normally returns an empty cursor when there are no matches. A query targeting the wrong field might not throw an exception and instead just return an empty list. Therefore, create both **positive and negative fixtures** in tests and assert the exact result set, not just `assertNotNull(result)`.

### 24.3. Analyze indexes before changing queries

If a query is correct but slow, it may be missing an index, have low selectivity, or an uncovered sort. Do not alter business query rules just to micro-benchmark H2-like data. Inspect the MongoDB explain plan with a dataset and indexes close to realistic conditions.

## 25. Best practices for fixtures and data isolation

1. Use unique business keys in each test (e.g., `CAM-001`, `CAM-HIGH`) or add a run ID prefix when running in parallel.
2. Use a fixed `Instant` instead of `Instant.now()` to avoid flaky time comparisons.
3. Insert only the documents needed for verification; do not create long purposeless fixtures.
4. Query tests must include both matching and nonmatching documents.
5. When order matters, specify an explicit sort rather than relying on insertion/natural order.
6. Check raw BSON for critical mappings, especially `@Field` and nested types.
7. Do not share mutable Mongo documents across tests if they can be updated.
8. Clean up data inside an isolated test database; do not drop collections/indexes that do not belong to the test.
9. With Testcontainers, pin the MongoDB major image matching production and document the Docker environment.
10. Never leak Mongo credentials or JDBC-like URIs with secrets in logs.
11. If using MongoDB index migrations, test the real migration rather than just annotations.
12. When using transactions, assert commit/rollback via server state after the transaction.
13. Count executed/disabled tests; never report "all Mongo tests passed" if the class was skipped.
14. Do not use `@DirtiesContext` as a way to wipe MongoDB data: it clears the Spring context cache, not necessarily MongoDB server state.

## 26. Practice exercises

### Exercise 1 — Prove the exact stored field names

Run `savesAndReloadsMappedDocument`, then temporarily change `@Field("item_code")` to `@Field("itemCode")` on a learning branch. The raw BSON assertions `raw.getString("item_code")` and `raw.containsKey("itemCode")` will demonstrate that the contract changed. Restore the annotation.

**Lesson:** Java property names are not automatically identical to MongoDB stored field names.

### Exercise 2 — Derived query with boundary threshold

In `derivedQueryUsesJavaPropertiesAndSortsPrice`, change the minimum from 20000 to 25000. `CAM-MID` with price exactly 25000 must remain in the result because the predicate is greater-than-or-equal. If you change it to `GreaterThan`, how does the expected result change?

### Exercise 3 — `@Query` with dynamic input

Add a category containing special characters (such as a single quote) to the fixture and call `findAffordableInCategory`. Verify that Spring Data's `?0` binding preserves the scalar value cleanly and avoids parser injection from string concatenation.

### Exercise 4 — Remove sorting and observe the test

Remove `OrderByPriceCentsAsc` from the repository method while keeping the list order assertion. The test may pass by chance in a small environment, yet it no longer enforces an ordering contract. Restore the sort and explain why natural order is unsafe.

### Exercise 5 — Disable auto index creation

Temporarily remove the `spring.data.mongodb.auto-index-creation=true` property. Run against a **new, empty MongoDB test database** and observe the duplicate-key test. Why is the `@Indexed(unique=true)` annotation insufficient by itself? Restore the property.

### Exercise 6 — Null vs. missing

Create one raw `Document` with `details=null` and one document without the `details` field. Use a `MongoTemplate` query with `Criteria.where("details").exists(false)` and an appropriate `$eq: null` check. Note the differences in MongoDB query semantics.

### Exercise 7 — Enable Testcontainers in CI

Set `RUN_MONGO_TESTS=true` and run tests on a Docker-enabled agent. Record the actual passing method count (8) and distinguish it from a build that only has disabled tests when the environment variable is unset.

### Exercise 8 — Add `@Version`

Add a version field to the entity, write a test that reads two snapshots, saves snapshot A, and then attempts to save stale snapshot B. Assert the optimistic locking failure and persisted data. Note write concern/context requirements.

### Exercise 9 — Nested document query

Add a query filtering by `details.brand` (e.g., `Criteria.where("details.brand").is("ACME")`), create one ACME item and one other item. Assert the exact result set; no separate `ItemDetails` collection is needed.

### Exercise 10 — Service integration

Create `InventoryService` using the repository. Write a JUnit unit test mocking the repository for business decisions and a `@DataMongoTest` with `@Import(InventoryService.class)` to test the persistence path. Explain why the service bean is not auto-scanned by the slice.

### Exercise 11 — Reactive query

Create a branch using `spring-boot-starter-data-mongodb-reactive`, `ReactiveMongoRepository`, and `StepVerifier`. Compare `Mono`/`Flux` against synchronous `Optional`/`List`, without calling `block()` on an application event loop.

### Exercise 12 — From right tests to right migrations

Create an explicit index migration for `item_code`, disable auto index creation in the migration test, and run against a fresh MongoDB container. Assert the real index is created, duplicate keys are rejected, and the collection is not unintentionally dropped.

## 27. Checklist before marking QA PASS

- [ ] I know which MongoDB server and database the test runs against.
- [ ] `@DataMongoTest` loads only the Mongo persistence slice, not mistaken for a full application test.
- [ ] The test has a real MongoDB instance or is explicitly marked skipped when the environment is missing.
- [ ] I do not claim Spring Boot 3.3 automatically starts embedded MongoDB.
- [ ] The `@Document` entity has the right collection and `@Id` mapping.
- [ ] The test inspects at least one raw BSON document when field mapping is the goal.
- [ ] `@Field` mappings match the published storage schema names.
- [ ] Derived queries use Java property names and assert positive/negative fixtures.
- [ ] `@Query` parameters are bound, not built by concatenating input strings.
- [ ] Unsorted queries are tested without relying on ordering.
- [ ] Explicit sorting is present when paging/ordering is part of the contract.
- [ ] Nested document/array/date mappings are verified in both BSON and Java where meaningful.
- [ ] I understand `@Indexed` does not create a unique index if index creation is off.
- [ ] Duplicate-key tests actually trigger an error from the MongoDB server.
- [ ] Mongo tests have cleanup/collection isolation rather than relying on default JPA rollback.
- [ ] Collections/indexes are not randomly dropped between test methods.
- [ ] MongoDB Testcontainers connection details are not overridden by localhost/production URIs.
- [ ] Testcontainers lifecycle and Spring context caching match the container sharing strategy.
- [ ] If custom converters are used, the test scope includes the conversion config.
- [ ] If transactions are used, a suitable transaction manager/topology and post-rollback assertions are in place.
- [ ] Test reports state exact run/skip counts, without treating skipped as passed.
- [ ] When upgrading Spring Boot major versions, I check imports/test modules and MongoDB driver compatibility.

## 28. Final selection rules

```text
What do you need to prove?
    |
    +--> Business logic with a fake repository?
    |      -> JUnit + Mockito; MongoDB not needed.
    |
    +--> Document mapping, @Field, MongoRepository,
    |    derived query, @Query, MongoTemplate, index?
    |      -> @DataMongoTest + MongoDB test server.
    |
    +--> Service coordinating multiple repositories/beans?
    |      -> @DataMongoTest + @Import service when small,
    |         or @SpringBootTest with Mongo test server.
    |
    +--> HTTP/JSON + MongoDB end to end?
    |      -> @SpringBootTest(RANDOM_PORT) and real client,
    |         with MongoDB Testcontainers.
    |
    +--> MongoDB transactions/sharding/failover/prod index plan?
           -> Environment with matching topology/engine/version,
              targeted tests with proper isolation and data.
```

**Core message:** `@DataMongoTest` is a **Spring context slice** for MongoDB; it does not turn a mock repository into a real database and does not automatically start an embedded server. By combining MongoDB Testcontainers with assertions on raw BSON, repository queries, indexes, and cleanup, you can accurately verify mapping/query behavior at lower cost than a full application test — while avoiding JPA rollback assumptions and never touching databases outside the test scope.

## 29. Official documentation

- Spring Boot 3.3 — Testing Spring Boot Applications, `@DataMongoTest`: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Test Slices auto-configuration: https://docs.spring.io/spring-boot/3.3/appendix/test-auto-configuration/slices.html
- Spring Boot 3.3 — Testcontainers and `@ServiceConnection`: https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html
- Spring Boot 3.3 — MongoDB configuration: https://docs.spring.io/spring-boot/3.3/reference/data/nosql.html
- Spring Data MongoDB — MongoDB object mapping: https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html
- Spring Data MongoDB — Index creation: https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html
- Spring Data MongoDB — Query methods and `@Query`: https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html
- Spring Data MongoDB — MongoTemplate query DSL: https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html
- Spring Data MongoDB — MongoDB transactions: https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html
- MongoDB — BSON Date and Extended JSON: https://www.mongodb.com/docs/manual/reference/bson-types/
- MongoDB — Unique indexes: https://www.mongodb.com/docs/manual/core/index-unique/
- Testcontainers Java — MongoDB module: https://java.testcontainers.org/modules/databases/mongodb/
- JUnit Jupiter — Conditional test execution: https://docs.junit.org/current/user-guide/
