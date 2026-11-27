# Fixtures, Indexes, Validators, and Test Collections

In a **Spring Data MongoDB** application, a repository test can pass while the real system still fails: test data was not prepared with the right BSON types, unique indexes were never created, the collection has no schema validator, or tests share data and interfere with one another. Conversely, a test that only exercises `MongoTemplate.insert(...)` does not prove that MongoDB rejects malformed records or executes queries using the intended index.

This lesson builds a **reproducible test environment** for a MongoDB collection, consisting of four parts working together:

1. **Fixtures**: controlled input documents and expected outcomes.
2. **Test collection**: an actual namespace storing data, with an explicit create/cleanup lifecycle.
3. **Indexes**: constraints and access paths such as unique, compound, or TTL indexes.
4. **Validator**: server-side MongoDB rules checking document shape and BSON types.

The examples use `MongoTemplate`, repositories, JUnit 5, and Testcontainers. They test CRUD operations, queries, indexes, and BSON conversion against real MongoDB in isolation, while showing how to avoid false-positive or order-dependent tests.

## 1. Why Test Fixtures, Indexes, and Validators Together?

Suppose a service stores products in the `products` collection:

```javascript
{
  _id: "p-001",
  sku: "SKU-001",
  name: "Keyboard",
  priceInCents: NumberLong("129900"),
  active: true
}
```

Business rules:

- Each `sku` appears **at most once** in the collection.
- `sku` is a non-empty string; `priceInCents` is a non-negative 64-bit integer; `active` is a Boolean.
- Querying a product by `sku` must return the exact document even when other products exist.
- Tests must be repeatable with no leftover data from earlier runs.

If you rely solely on Java validation such as `@NotBlank` or `@PositiveOrZero`, the application validates when Bean Validation is triggered, yet direct writes via the driver, scripts, or another service can bypass it. A **MongoDB collection validator** adds a database-level validation layer. A **unique index** is what guarantees uniqueness under concurrent writes; calling `existsBySku(...)` then `save(...)` does not prevent race conditions.

| Component | What does it guarantee? | What can it not replace? |
| --- | --- | --- |
| Fixture | Tests have standard data, edge cases, and expected outcomes | Does not enforce data constraints on MongoDB |
| Test collection | Provides storage and isolation/cleanup mechanisms | Does not automatically include required indexes or validators |
| Unique index | MongoDB rejects duplicate keys on matching documents | Does not validate arbitrary BSON types or business rules |
| Schema validator | MongoDB checks structure, data types, and required fields | Does not create unique indexes |
| Assertions | Compare real behavior against requirements | Meaningless if fixture setup is unrepresentative |

## 2. Choosing the Test Level

Not every test needs to start MongoDB:

| Level | Objective | Suggested tools |
| --- | --- | --- |
| Unit test | Query-building helpers, value logic, service rules | JUnit, Mockito, no database needed |
| Spring Data slice test | Entity mapping, repositories, `MongoTemplate`, and queries on MongoDB | `@DataMongoTest` with a real test MongoDB |
| Integration test | Unique indexes, validators, transactions, aggregations, concurrency, server execution | Testcontainers or dedicated test MongoDB configured close to production |
| End-to-end test | HTTP/API through MongoDB with collaborating components | `@SpringBootTest`, appropriate integration environment |

Mocking `MongoRepository` verifies how a service handles return values, yet cannot test whether MongoDB creates an index or rejects an invalid schema. Features such as `$jsonSchema`, unique indexes, aggregations, and transactions should have tests running against **real MongoDB**. Avoid assuming an in-memory fake or mock implements every operator, BSON behavior, or MongoDB Server limitation.

With Spring Boot, `@DataMongoTest` narrows the application context to needed MongoDB components; the annotation **does not start a MongoDB server by itself**. You can supply the connection from Testcontainers. The examples below follow a general pattern; actual dependencies, Testcontainers APIs, and connection settings must match your Spring Boot, Spring Data, and MongoDB Java Driver versions.

## 3. Designing Repeatable Fixtures

A fixture is purposeful data designed to exercise one or more behaviors. A good fixture has these qualities:

- **Deterministic:** use fixed `_id`, `sku`, status, amounts, and timestamps. If current time is needed, inject a controllable `Clock` into services instead of calling `Instant.now()` directly across tests.
- **Distinctive:** each record has a clear purpose—for example, active/inactive products, zero price, large boundary price, and similar-looking SKUs.
- **Independent:** every test starts from the same baseline state or uses its own database/collection; it never depends on what another test inserted or deleted.
- **BSON-accurate:** when a test requires `long`, ensure the value is stored as BSON Int64 rather than the string `"129900"`.
- **Includes positive and negative cases:** wrong types or duplicate keys are negative fixtures and do not belong in the shared valid baseline fixture.
- **Small yet meaningful:** a handful of deliberate documents is better for functional tests than thousands of random records; large datasets for query plans/performance belong in a separate fixture.

Example initial state:

| `_id` | `sku` | `name` | `priceInCents` | `active` | Purpose |
| --- | --- | --- | ---: | --- | --- |
| `p-001` | `SKU-001` | Keyboard | 129900 | `true` | Successful lookup by SKU |
| `p-002` | `SKU-002` | Mouse | 0 | `false` | Check zero price and inactive status |
| `p-003` | `SKU-003` | Monitor | 4999000 | `true` | Additional value to test filtering |

**Avoid** generating unpredictable fixture strings with `UUID.randomUUID()` or wall-clock timestamps when randomness is not what is being tested. When random or property-based data is needed, fix the seed and log it on failure so runs are reproducible.

## 4. Sample Entity and Repository

In modern Spring Data MongoDB versions supporting Java records, a simple document can be modeled as:

```java
package example.catalog;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("products")
public record Product(
    @Id String id,
    @Indexed(unique = true, name = "ux_products_sku") String sku,
    String name,
    long priceInCents,
    boolean active
) {}
```

Repository:

```java
package example.catalog;

import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository
        extends MongoRepository<Product, String> {

    Optional<Product> findBySku(String sku);
}
```

`@Document("products")` sets the collection; `@Id` maps `id` to `_id`; `@Indexed(unique = true)` declares intent to create a unique index. However, **Spring Data MongoDB does not guarantee automatic index creation in every configuration**; in modern versions, auto-index creation is commonly off by default. Tests must explicitly create indexes or execute the same migration/index-management mechanism used in production. If auto-index creation is enabled, make sure annotation definitions and index names match manually created indexes to avoid configuration conflicts.

`long priceInCents` is stored as BSON Int64 under standard Java Driver mapping. Using the smallest currency unit avoids floating-point rounding errors in this example. If the application stores `BigDecimal`, test BSON Decimal128 mapping or custom conversions against the actual configuration rather than guessing from the Java type.

## 5. Connecting to Test MongoDB via Testcontainers

Illustrative configuration for Spring Boot + JUnit 5:

```java
package example.catalog;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@DataMongoTest
@Testcontainers
class ProductRepositoryTest {

    @Container
    static final MongoDBContainer mongo =
        new MongoDBContainer("mongo:7.0");

    @DynamicPropertySource
    static void mongoProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            () -> mongo.getReplicaSetUrl("catalog_test")
        );
    }

    @Autowired
    MongoTemplate mongoTemplate;

    @Autowired
    ProductRepository repository;

    // @BeforeEach and @Test methods are added in later sections.
}
```

Additional imports for `MongoTemplate` and JUnit:

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.junit.jupiter.api.BeforeEach;
```

Prepare the matching dependencies in **test scope**: Spring Boot Test, Spring Data MongoDB, JUnit 5, Testcontainers MongoDB, and Testcontainers JUnit Jupiter integration. The test runner needs an available container runtime. `@ServiceConnection` can replace `@DynamicPropertySource` on compatible Spring Boot/Testcontainers versions; choose **one** approach to avoid conflicting URI configs.

The example uses `mongo:7.0` to illustrate a real server environment, which does not mean every project must use that tag. For version-dependent MongoDB features (validators, collation, transactions, search, etc.), pick an image matching production and pin its version in CI. Avoid `latest` when reproducibility matters.

## 6. Explicitly Creating the Collection and Validator

MongoDB can auto-create a collection on first insert, but an auto-created collection will lack the schema validator expected by the application. For tests verifying schema rules, **create the collection before seeding fixtures**.

The schema below requires:

- `sku` is present, a String, with minimum length 1;
- `priceInCents` is present, BSON Int64, and non-negative;
- `active` is present and a Boolean;
- `name`, if present, must be a String.

Java Driver code using the same `MongoDatabase` that `MongoTemplate` connects to:

```java
import java.util.List;

import com.mongodb.client.model.CreateCollectionOptions;
import com.mongodb.client.model.ValidationAction;
import com.mongodb.client.model.ValidationLevel;
import com.mongodb.client.model.ValidationOptions;
import org.bson.Document;

private void createValidatedProductsCollection() {
    Document properties = new Document()
        .append("sku", new Document("bsonType", "string")
            .append("minLength", 1))
        .append("name", new Document("bsonType", "string"))
        .append("priceInCents", new Document("bsonType", "long")
            .append("minimum", 0))
        .append("active", new Document("bsonType", "bool"));

    Document jsonSchema = new Document("bsonType", "object")
        .append("required", List.of("sku", "priceInCents", "active"))
        .append("properties", properties);

    ValidationOptions validation = new ValidationOptions()
        .validator(new Document("$jsonSchema", jsonSchema))
        .validationLevel(ValidationLevel.STRICT)
        .validationAction(ValidationAction.ERROR);

    CreateCollectionOptions options = new CreateCollectionOptions()
        .validationOptions(validation);

    mongoTemplate.getDb().createCollection("products", options);
}
```

`$jsonSchema` uses BSON type names like `"long"` and `"bool"`; this is not standard JSON Schema `type: "integer"` syntax. BSON `int` (Int32) and `long` (Int64) are distinct types. If a fixture writes `new Document("priceInCents", 129900)`, that value is typically Int32 and will be rejected by the validator above, whereas `129900L` is a Java `Long` encoded as BSON Int64.

Pay special attention to these options:

| Setting | Meaning during tests |
| --- | --- |
| `validationAction: "error"` | Validator violations fail the write; suitable when tests assert constraint enforcement |
| `validationAction: "warn"` | Writes still succeed while logging warnings; unsuitable if assertions expect failure |
| `validationLevel: "strict"` | Applies validation to inserts and updates per MongoDB rules |
| `validationLevel: "moderate"` | Behaves differently when updating existing invalid documents; test per migration goal |
| `required` | Requires field presence; to reject `null`, also choose a `bsonType` that disallows `null` |
| `additionalProperties: false` | Rejects unlisted fields; watch out for `_id`, `_class`, and framework-written fields |

**Important limitation:** creating or modifying a validator does not retroactively fix old invalid data. When using `collMod` to add a validator to an existing collection, decide how to handle legacy documents and update behavior. Never use schema validators as a substitute for unit testing complex business logic.

## 7. Creating Indexes Before Running Queries and Fixtures

Creating an index with `MongoTemplate`:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.index.Index;

private void createProductsIndexes() {
    mongoTemplate.indexOps("products").ensureIndex(
        new Index()
            .on("sku", Sort.Direction.ASC)
            .unique()
            .named("ux_products_sku")
    );
}
```

`sku` must be unique. Attempting to insert a duplicate SKU raises a duplicate key error from the database, typically **MongoDB error code 11000**. Spring Data translates many driver errors into `DataAccessException` types; for example, duplicate keys appear as `DuplicateKeyException` at the `MongoTemplate`/repository layer.

Types of indexes to test depending on your application:

| Type | Example | Notes |
| --- | --- | --- |
| Unique | `{ sku: 1 }` | Test duplicate inserts and updates that produce duplicate keys |
| Compound | `{ active: 1, priceInCents: -1 }` | Check query shape including filter, sort, projection; field order matters |
| Partial | Unique only for `active: true` | Fixture must include records both inside and outside the partial filter |
| Sparse | Index skips documents missing the field | Verify `null` and uniqueness behavior for your server version/rules |
| TTL | Deletes expired documents based on a date field | Deletion by the TTL monitor is asynchronous; never assert instant deletion at expiration |
| Text / geospatial | Keyword or coordinate lookups | Requires data and assertions matching real operators and indexes |

**A unique index is not equivalent to checking uniqueness in Java.** MongoDB enforces it at the collection level and protects across concurrent writers from multiple services. A test inserting duplicate data after creating the index exercises this constraint directly. If duplicate records are inserted **before** creating a unique index, index creation fails; that is a migration/indexing case worth testing separately too.

## 8. Building and Resetting Fixtures Before Each Test

For sequential tests sharing a dedicated database for the test class, `@BeforeEach` can reinitialize the collection. Place the methods below **inside `ProductRepositoryTest`**:

```java
@BeforeEach
void prepareCollectionAndFixtures() {
    if (mongoTemplate.collectionExists("products")) {
        mongoTemplate.dropCollection("products");
    }

    // Create schema and indexes BEFORE inserting fixtures.
    createValidatedProductsCollection();
    createProductsIndexes();

    mongoTemplate.insert(
        new Product("p-001", "SKU-001", "Keyboard", 129900L, true)
    );
    mongoTemplate.insert(
        new Product("p-002", "SKU-002", "Mouse", 0L, false)
    );
    mongoTemplate.insert(
        new Product("p-003", "SKU-003", "Monitor", 4999000L, true)
    );
}
```

Why this order?

1. If the previous test modified the collection or indexes, dropping clears that state.
2. Recreating the collection **restores the validator**, because `dropCollection` deletes both the collection and its indexes/validator.
3. Creating indexes before seeding immediately catches fixtures that violate uniqueness.
4. Inserting records with fixed `_id` values keeps assertions clear and exposes data leaking across tests.

Drop-and-recreate fits **isolated test databases whose data is disposable**. Never point such setup at a database serving real users or holding persistent data. If multiple test classes run in parallel against the same database and collection name, one test's drop can break another. For parallel tests, give each test class its own database/collection or scope fixtures appropriately.

### 8.1. Removing Documents vs. Dropping the Collection

These two reset approaches serve different goals:

```java
// Delete documents while PRESERVING the collection, validator, and indexes.
mongoTemplate.remove(new Query(), "products");

// Delete the entire collection, along with its validator and indexes.
mongoTemplate.dropCollection("products");
```

Import for `Query`:

```java
import org.springframework.data.mongodb.core.query.Query;
```

When you only need to reset data while keeping schema/index configuration fixed, removing documents and re-seeding is usually faster. When a test verifies **the creation of the validator, indexes, or collection itself**, rebuilding from scratch is safer. Never drop a collection and then assume its unique index or validator survived from an earlier test.

## 9. Testing Reads, Unique Indexes, and Schema Validators

### 9.1. Reading Fixtures with the Repository

A basic test confirms the initial baseline data:

```java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

@Test
void findsProductBySku() {
    Product product = repository.findBySku("SKU-001").orElseThrow();

    assertThat(product.id()).isEqualTo("p-001");
    assertThat(product.name()).isEqualTo("Keyboard");
    assertThat(product.priceInCents()).isEqualTo(129900L);
    assertThat(product.active()).isTrue();
}
```

If this test passes without creating the unique index, it only proves *correct reading* over the current fixture. It does not prove uniqueness enforcement or query plans.

### 9.2. Duplicate Keys Must Be Rejected

```java
import org.springframework.dao.DuplicateKeyException;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Test
void rejectsDuplicateSku() {
    assertThatThrownBy(() ->
        repository.save(
            new Product("p-new", "SKU-001", "Another product", 1000L, true)
        )
    ).isInstanceOf(DuplicateKeyException.class);

    // No extra document may be written after the failed insert.
    assertThat(mongoTemplate.getCollection("products")
        .countDocuments()).isEqualTo(3L);
}
```

This test verifies the constraint enforced by the **database**. Do not call `repository.existsBySku` before inserting; doing so could mask a missing index.

### 9.3. Validator Rejects Wrong BSON Types

Use the raw MongoDB Driver to craft an invalid-type document intentionally, preventing Spring Data converters from normalizing it before writing:

```java
import com.mongodb.MongoWriteException;
import org.bson.Document;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@Test
void rejectsInvalidBsonType() {
    MongoWriteException error = assertThrows(
        MongoWriteException.class,
        () -> mongoTemplate.getCollection("products").insertOne(
            new Document("_id", "bad-001")
                .append("sku", "SKU-BAD")
                .append("name", "Invalid")
                .append("priceInCents", "129900") // String instead of Long
                .append("active", true)
        )
    );

    assertEquals(121, error.getCode()); // DocumentValidationFailure
}
```

Code 121 is the standard MongoDB error code for document validation failure; in integration tests, asserting the error code is more reliable than matching message strings verbatim, since wording can vary across versions or include specific details.

Add a missing required field case:

```java
@Test
void rejectsMissingRequiredField() {
    MongoWriteException error = assertThrows(
        MongoWriteException.class,
        () -> mongoTemplate.getCollection("products").insertOne(
            new Document("_id", "bad-002")
                .append("sku", "SKU-NO-PRICE")
                .append("active", true)
        )
    );

    assertEquals(121, error.getCode());
}
```

An omitted `priceInCents` field is rejected by the validator. A `null` value is also rejected under this schema because `bsonType: "long"` does not allow BSON Null. If the business rules allow null, declare the allowed types accordingly and test separately.

### 9.4. Confirming the Unique Index Actually Exists

Having `@Indexed` in source code is not proof that the index was created:

```java
import java.util.ArrayList;
import java.util.List;
import org.bson.Document;

@Test
void createsUniqueSkuIndex() {
    List<Document> indexes = mongoTemplate.getCollection("products")
        .listIndexes()
        .into(new ArrayList<>());

    Document skuIndex = indexes.stream()
        .filter(index -> "ux_products_sku".equals(index.getString("name")))
        .findFirst()
        .orElseThrow();

    assertThat(skuIndex.get("key", Document.class))
        .containsEntry("sku", 1);
    assertThat(skuIndex.getBoolean("unique")).isTrue();
}
```

Testing the **existence and configuration** of an index differs from testing **whether MongoDB actually chooses that index at query time**. On a collection with only three documents, the planner may pick a collection scan as cheaper, so do not hardcode an `explain` assertion demanding `IXSCAN`. To inspect query plans, build a suitable dataset, read `explain("executionStats")`, and interpret results based on dataset size and query selectivity.

## 10. Testing Compound Indexes and Sorted Queries

When the application frequently fetches active products sorted by price descending, a candidate index is:

```javascript
db.products.createIndex({ active: 1, priceInCents: -1 });
```

Create the same index with Spring Data:

```java
mongoTemplate.indexOps("products").ensureIndex(
    new Index()
        .on("active", Sort.Direction.ASC)
        .on("priceInCents", Sort.Direction.DESC)
        .named("ix_products_active_price_desc")
);
```

Query:

```java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(Criteria.where("active").is(true))
    .with(Sort.by(Sort.Direction.DESC, "priceInCents"))
    .limit(10);

List<Product> products = mongoTemplate.find(query, Product.class);
```

To verify results, the fixture needs multiple `active = true` products with distinct prices; assert the returned order and count. To check index efficiency, use a larger dataset and inspect `totalDocsExamined`, `totalKeysExamined`, `IXSCAN`/`SORT` stages, and returned document count. Creating an index in a tiny test only proves the index-creation API works, not that the production plan is optimal.

## 11. Transactions, References, and Multiple Collections

When a business operation spans multiple collections such as `orders` and `orderItems`, fixtures must describe **relationships between documents**:

- Seed parent records before children if code looks up parent keys; check ID consistency.
- Clean all involved collections along with their indexes/validators. Ensure cleanup does not race with active reader threads.
- If using `@DBRef` or `@DocumentReference`, test actual reference resolution; MongoDB does not enforce foreign key constraints like relational databases.
- MongoDB transactions require a compatible topology and configuration, such as a replica set; running against standalone without transaction support yields errors that do not reflect replica-set behavior.
- For concurrency tests and unique constraints, initialize shared fixtures before launching concurrent tasks, wait for all tasks to complete, and assert final document counts. Avoid asserting thread completion order without an explicit contract.

A `@Transactional` service test proves transactions only when `MongoTransactionManager` is properly configured and operations participate in a real transaction. Never take the mere presence of the annotation as proof that MongoDB rolls back.

## 12. Collection Validators and Updating Legacy Data

For collections that already hold data, you sometimes add a schema validator via `collMod`. Illustrative `mongosh` command:

```javascript
db.runCommand({
  collMod: "products",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["sku", "priceInCents", "active"],
      properties: {
        sku: { bsonType: "string", minLength: 1 },
        priceInCents: { bsonType: "long", minimum: 0 },
        active: { bsonType: "bool" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

Tests should verify:

1. Valid pre-migration documents remain readable and updatable.
2. Existing invalid documents are **not automatically repaired** when adding a validator.
3. New inserts/updates violating the schema are rejected under `strict/error`.
4. If using `moderate` or `warn` while transitioning legacy data, test the exact accept/reject semantics.
5. When migrating BSON from String to Long or Decimal128, verify migrated documents satisfy the new validator before enabling strict error blocking.

Some privileged clients can pass `bypassDocumentValidation` in authorized contexts. Therefore negative tests must follow the application's actual write path without inadvertently bypassing validation.

Note that a validator is a **MongoDB rule**, distinct from Jakarta Bean Validation annotations on entities. Both layers can coexist and must be tested independently if the application relies on both.

## 13. Avoiding Flaky Tests

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Passes alone, fails in suite | Tests share a database and leave data behind | Use isolated fixtures, clean owned collections, or separate databases |
| Duplicate SKU still inserts | Unique index missing or created on wrong field/filter | Inspect `listIndexes()`; create indexes before seeding |
| Validator test throws no error | Collection auto-created without validator; `warn` mode; wrong collection | Create collection with explicit options and verify settings |
| Test expects BSON Long but receives Int32 | Fixture used Java `int` literal or wrong `Document` type | Use `129900L` and verify raw BSON when needed |
| Date/time tests fail intermittently | Relying on wall-clock time or local timezone | Use fixed `Instant`/`Clock` and explicit timezone |
| TTL test slow or flaky | TTL monitor does not delete the instant a document expires | Do not assert synchronous immediate deletion on expiration |
| Query plan test demands `IXSCAN` | Dataset too small or planner chose another valid plan | Test correctness separately; evaluate plans with representative workloads |
| Tests cannot run in CI | Missing Docker/container runtime, pull failure, or wrong version | Declare environment prerequisites, pin images, and prepare CI |
| Transaction test fails | Server topology lacks transaction support | Use a replica set/Testcontainers setup and transaction config |
| Parallel tests lose collections unexpectedly | One test drops a collection another test is using | Isolate namespaces per class/test and coordinate parallelism |

### Separating Setup and Assertion Responsibilities

A pragmatic structure:

- **Fixture factory** builds entities/documents with fixed baseline data, making each test's specific changes obvious.
- **Collection initializer** creates validators and indexes matching the schema version deployed in production; tests should not invent a schema different from production.
- **Test setup** resets state before each test rather than turning business tests into long migration scripts.
- **Test assertions** verify both success outcomes and database-level rejections rather than merely asserting a method was called.

However, do not over-abstract every fixture into a complex custom framework. When a test only needs three documents, simple builders or short helpers are easier to read than multi-layer factory hierarchies.

## 14. Practice Exercise

**Problem:** Build repository tests for the `products` collection with two requirements: look up products by SKU, and ensure the database rejects duplicate SKUs as well as documents missing `priceInCents` or storing it with the wrong type.

Steps:

1. Create `Product`, `ProductRepository`, and a `@DataMongoTest` slice test using MongoDB from Testcontainers.
2. Create the `products` collection with `$jsonSchema` in `strict/error` mode and a unique index on `sku`; inspect metadata to verify both.
3. Seed three deterministic documents with fixed `_id` values and `priceInCents` as Long.
4. Write tests for SKU lookup, duplicate SKU insert, missing required field, and inserting a String into the BSON Long field.
5. Run tests individually and then run the full suite multiple times; if parallel execution is enabled, isolate databases or collections to prevent conflicts.
6. Add compound index `{ active: 1, priceInCents: -1 }` and a sorted query; test result ordering over a rich fixture.
7. Test inserting duplicate fixtures before creating the unique index, observe index-creation failure, and explain how to prevent it during migrations.

Sample expected results:

| Test | Expectation |
| --- | --- |
| `findBySku("SKU-001")` | Returns product `p-001` with exact price and active status |
| Second insert of `SKU-001` | Duplicate key error; no new document persisted |
| Insert `priceInCents: "129900"` | Rejected by MongoDB due to BSON String type |
| Insert missing `priceInCents` | Rejected by MongoDB due to `required` rule |
| `listIndexes()` | Contains index `ux_products_sku` with `unique: true` |
| Second suite run | Outcome does not depend on data from the previous run |

**Completion criteria:** tests run against real MongoDB with verified index and validator settings; fixtures are recreated deterministically; both valid and invalid writes have assertions; and tests do not rely on execution order or asynchronous behavior like instant TTL deletion.

## 15. Key Takeaways

- **Repeatable fixtures are the foundation of integration tests.** Use deterministic IDs, timestamps, and BSON types, and isolate data between tests.
- **Indexes and validators belong to collection configuration**; they do not appear automatically just because entities have annotations or inserts succeed.
- **Create collections, validators, and indexes before seeding** when testing MongoDB constraints from the start.
- **Unique indexes** and **`$jsonSchema`** protect two distinct concerns: uniqueness and document structure/types.
- **`@DataMongoTest` + real test MongoDB** suits verifying repositories/`MongoTemplate`; mocks fit components that do not need server behavior.
- **Dropping a collection also deletes its indexes and validator.** Choose document removal vs. collection recreation by test objective and control parallel runs.
- **Test values and configuration separately**: reading data correctly does not prove indexes exist; having an index does not guarantee the planner chooses it for every dataset.
