# Verifying Spring Data Behavior Against Actual BSON, Queries, and Indexes in MongoDB

## 1. Why Verify All the Way Down to MongoDB?

Spring Data MongoDB enables Java code to work with MongoDB through `MongoRepository`, `MongoTemplate`, `Criteria`, and mapping annotations. However, compiling cleanly, returning results from a repository, or passing unit tests with mocks **does not guarantee** the system stores the right BSON types, sends the expected query, or uses the intended index.

Suppose an entity declares:

```java
@Field(name = "total", targetType = FieldType.DECIMAL128)
private BigDecimal amount;
```

Essential questions:

1. Does Java `amount` actually persist in BSON field `total` as type `decimal`/Decimal128?
2. Does derived method `findByAmountGreaterThanEqual` emit a filter on `total`?
3. Does Spring Data actually bind a `BigDecimal` parameter as BSON Decimal128?
4. Does `@Indexed` or `@CompoundIndex` in source code guarantee the index exists on the server?
5. Even when the index exists, does the query planner select it?
6. Do `null`, missing fields, Date timezones, embedded objects, or arrays produce surprises?
7. Is there cross-tenant data leakage via `$or` predicates or data loss from saving a partial entity?

Verification requires checking **multiple layers of evidence**:

```text
Java: entity @Document, @Field, @MongoId
          |
          v
Spring Data: MappingMongoConverter / QueryMapper
          |
          v
Driver: actual BSON command
          |
          v
MongoDB: persisted BSON document
          |
          v
Index catalog: keys + options
          |
          v
Query planner: explain("executionStats")
          |
          v
Integration test + staging performance benchmark
```

### Lesson Objectives

After this lesson, you will be able to:

- Set up a Spring Data MongoDB lab connected to a real MongoDB instance.
- Compare Java entities against raw `org.bson.Document`, `$type`, and collection options.
- Distinguish `@Id`, `@MongoId`, `@Field`, BSON String/ObjectId, Decimal128, Date/Instant, and null vs missing fields.
- Cross-check results across derived queries, `@Query`, `MongoTemplate`, and `mongosh`.
- Inspect the actual emitted command/filter/projection rather than relying on method names.
- Confirm real indexes exist via `getIndexes()`/`listIndexes`.
- Read `IXSCAN`, `COLLSCAN`, `FETCH`, `SORT`, `nReturned`, `totalKeysExamined`, and `totalDocsExamined`.
- Verify unique, compound, partial, TTL, and collation indexes.
- Write integration tests using `@DataMongoTest`, Testcontainers, or an isolated test database.
- Avoid brittle plan assertions on tiny datasets.
- Establish a post-release/post-migration schema, query, and index verification workflow.

**Scope:** focuses on Spring Data MongoDB in Java; query and index execution semantics are ultimately governed by MongoDB Server.

---

## 2. Distinguishing Five Layers of Evidence

| Layer | What It Verifies | Tools | Does NOT Prove by Itself |
| --- | --- | --- | --- |
| Entity metadata | How the developer intends Java mapping | `@Document`, `@Field`, `@MongoId` | Server data matches expectations |
| Persisted BSON | What types and fields MongoDB actually stores | `mongosh`, `$type`, raw `Document` | Queries use an index |
| Emitted command | Which filter/sort/projection was sent | Driver `CommandListener`, redacted query logs | Command executes quickly |
| Index catalog | Index exists with the right options | `getIndexes`, `listIndexes`, `IndexOperations` | Planner picks that index |
| Execution | How the server scanned keys and documents | `explain("executionStats")`, profiler | End-to-end app HTTP p95/p99 |

### 2.1. Three Commonly Misleading Claims

- **"We added `@Indexed`"** is source-code evidence, not index-catalog evidence.
- **"The index exists"** is catalog evidence, not proof MongoDB uses it for a specific query.
- **"Explain shows `IXSCAN`"** proves an index scan occurred, not that keys examined is small or optimal under production traffic.

### 2.2. Mocks Do Not Verify MongoDB Behavior

```java
when(repository.findByTenantIdAndStatus("A", "PAID"))
    .thenReturn(List.of(fakeOrder));
```

Mocks test service logic yet **completely skip** Spring Data's query parser, BSON converters, MongoDB filters, unique constraints, index catalog, and query planner. Exercises therefore require **integration tests against a real MongoDB instance**, alongside unit tests.

---

## 3. Environment and Dependencies

Examples use:

- Java **17+**, using `record` for concise entity definitions.
- Compatible Spring Boot / Spring Data MongoDB versions.
- `spring-boot-starter-data-mongodb` for the imperative API.
- MongoDB Server compatible with the driver; MongoDB 8.0 is a solid lab choice.
- `mongosh`, JUnit 5, AssertJ.
- Testcontainers depending on local/CI setup.

In Gradle Kotlin DSL:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "<approved-boot-version>"
    id("io.spring.dependency-management") version "<approved-version>"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-mongodb")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Placeholders **are not buildable versions**. Real projects must specify approved versions verified for compatibility across Boot, Spring Data, driver, and MongoDB Server. The Spring Boot BOM typically manages the Java Driver.

Lab MongoDB configuration:

```properties
spring.data.mongodb.uri=mongodb://127.0.0.1:27017/spring_data_bson_lab
```

Connection property prefixes may differ across Spring Boot major versions. Consult the reference docs for your exact release when connecting to Atlas or production.

**Practice safely:** run `drop()`, `insertMany()`, `createIndex()`, and destructive tests **only in a lab**. Never expose public access, hardcode passwords in URIs in source control, log raw BSON containing PII, or run heavy `explain` queries on production without authorization.

---

## 4. Entity: Deliberately Naming Java Properties Differently from BSON Fields

A clear way to observe mapping in action is choosing Java property names **that differ from MongoDB's stored field names**.

### 4.1. OrderDoc.java

```java
package com.example.mongo;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record OrderDoc(
    @MongoId(FieldType.STRING)
    String id,

    String tenantId,

    @Field("order_no")
    String orderNo,

    String status,

    @Field(name = "total", targetType = FieldType.DECIMAL128)
    BigDecimal amount,

    @Field("created_at")
    Instant createdAt,

    @Field("ship")
    Shipping shipping,

    List<LineItem> items,

    String note
) {}

record Shipping(String city, String district) {}

record LineItem(String sku, int quantity) {}
```

Three records share a package to illustrate the domain model; organize files and public visibility per project conventions.

### 4.2. Mapping Contract

| Java Property | BSON Field | Expected BSON Type |
| --- | --- | --- |
| `id` | `_id` | `string` via `@MongoId(FieldType.STRING)` |
| `tenantId` | `tenantId` | `string` |
| `orderNo` | `order_no` | `string` |
| `status` | `status` | `string` |
| `amount` | `total` | `decimal` (Decimal128) |
| `createdAt` | `created_at` | `date` |
| `shipping` | `ship` | `object` |
| `shipping.city` | `ship.city` | `string` |
| `items` | `items` | `array` |
| `note` | `note` | `string`, `null`, or missing depending on document |

### 4.3. `@Id` and `@MongoId` Are Not Identical

With `@Id String id`, Spring Data MongoDB converts String values to BSON `ObjectId` automatically when formatted as a valid 24-hex ObjectId string. With `@MongoId(FieldType.STRING)`, storing `_id` as a BSON String is declared explicitly.

An ID such as `"507f1f77bcf86cd799439011"` can be checked with:

```javascript
db.orders.findOne({ _id: "507f1f77bcf86cd799439011" });
db.orders.findOne({ _id: ObjectId("507f1f77bcf86cd799439011") });
```

These two BSON values have **different types** and do not match the same key. Never switch ID mapping without measuring and migrating existing data.

### 4.4. `BigDecimal` and `Decimal128`

`BigDecimal` is a Java type; BSON `Decimal128` is MongoDB's representation. `@Field(targetType = FieldType.DECIMAL128)` specifies the conversion strategy explicitly—essential when monetary amounts require exact decimal precision.

Never construct monetary `BigDecimal` values from a `double` like `new BigDecimal(19.99)` expecting exact decimal representation. Use `new BigDecimal("19.99")` or parsed inputs per business policy.

### 4.5. `Instant` and `Date`

BSON `Date` stores UTC epoch timestamps at millisecond precision. `Instant` has nanosecond resolution; sub-millisecond nanoseconds can be truncated on round-trip. For filtering by "calendar day in Vietnam time", convert local day boundaries into UTC intervals before querying.

### 4.6. `_class` Metadata

Spring Data may write a `_class` field via its default type mapper. This helps polymorphic mapping yet can clutter documents shared across non-Spring services. Disabling or customizing the type mapper must be tested carefully against inheritance, subtypes, and schema migrations.

---

## 5. Building a BSON Fixture Independently of Spring Data

Seed test data from `mongosh` so Java tests do not rely on the very converter under test to build their own oracle.

**The following drops the lab collection: never run on production.**

```javascript
const lab = db.getSiblingDB("spring_data_bson_lab");
lab.orders.drop();

lab.orders.insertMany([
  {
    _id: "A-001", tenantId: "A",
    order_no: "ORD-A-001", status: "PAID",
    total: NumberDecimal("125.50"),
    created_at: ISODate("2026-11-10T08:00:00Z"),
    ship: { city: "Hà Nội", district: "Ba Đình" },
    items: [
      { sku: "PEN", quantity: 2 },
      { sku: "BOOK", quantity: 1 }
    ],
    note: "ready"
  },
  {
    _id: "A-002", tenantId: "A",
    order_no: "ORD-A-002", status: "NEW",
    total: NumberDecimal("15.00"),
    created_at: ISODate("2026-11-11T08:00:00Z"),
    ship: { city: "Đà Nẵng", district: "Hải Châu" },
    items: [{ sku: "PEN", quantity: 1 }]
    // note missing
  },
  {
    _id: "A-003", tenantId: "A",
    order_no: "ORD-A-003", status: "PAID",
    total: NumberDecimal("200.00"),
    created_at: ISODate("2026-11-12T08:00:00Z"),
    ship: { city: "Hà Nội", district: "Cầu Giấy" },
    items: [{ sku: "BOOK", quantity: 5 }],
    note: null
  },
  {
    _id: "A-004", tenantId: "A",
    order_no: "ORD-A-004", status: "CANCELLED",
    total: NumberDecimal("5.00"),
    created_at: ISODate("2026-11-13T08:00:00Z"),
    ship: { city: "Cần Thơ", district: "Ninh Kiều" },
    items: []
  },
  {
    _id: "A-005", tenantId: "A",
    order_no: "ORD-A-005", status: "PAID",
    total: NumberDecimal("75.25"),
    created_at: ISODate("2026-11-12T08:00:00Z"),
    ship: { city: "Hải Phòng", district: "Lê Chân" },
    items: [{ sku: "PEN", quantity: 3 }]
  },
  {
    _id: "B-001", tenantId: "B",
    order_no: "ORD-B-001", status: "PAID",
    total: NumberDecimal("999.99"),
    created_at: ISODate("2026-11-10T09:00:00Z"),
    ship: { city: "Hà Nội", district: "Long Biên" },
    items: [{ sku: "BOOK", quantity: 2 }]
  },
  {
    _id: "B-002", tenantId: "B",
    order_no: "ORD-B-002", status: "PAID",
    total: NumberDecimal("30.00"),
    created_at: ISODate("2026-11-11T09:00:00Z"),
    ship: { city: "TP. Hồ Chí Minh", district: "Quận 1" },
    items: []
  },
  {
    _id: "B-003", tenantId: "B",
    order_no: "ORD-B-003", status: "NEW",
    total: NumberDecimal("15.00"),
    created_at: ISODate("2026-11-13T09:00:00Z"),
    ship: { city: "Đà Nẵng", district: "Sơn Trà" },
    items: [{ sku: "PEN", quantity: 1 }]
  }
]);

lab.orders.countDocuments({});
// 8
```

### 5.1. Oracle for Integration Tests

| Condition | Expected IDs | Count |
| --- | --- | ---: |
| All documents | A-001..A-005 and B-001..B-003 | 8 |
| Tenant A | A-001..A-005 | 5 |
| Tenant B | B-001..B-003 | 3 |
| Tenant A and PAID | A-001, A-003, A-005 | 3 |
| Tenant A and total >= 100 | A-001, A-003 | 2 |
| Ship city is Hà Nội | A-001, A-003, B-001 | 3 |
| note missing | A-002, A-004, A-005, B-001, B-002, B-003 | 6 |
| note explicit null | A-003 | 1 |
| note equals null under MongoDB equality | Missing + explicit null | 7 |
| Same element sku=BOOK and quantity >= 3 | A-003 | 1 |

Do not assert result ordering on queries lacking a sort specification.

---

## 6. Verifying Raw BSON with `$type`

### 6.1. Inspecting Directly on the Server

```javascript
lab.orders.aggregate([
  {
    $project: {
      idType: { $type: "$_id" },
      orderNoType: { $type: "$order_no" },
      amountType: { $type: "$total" },
      dateType: { $type: "$created_at" },
      shipType: { $type: "$ship" },
      itemsType: { $type: "$items" },
      noteType: { $type: "$note" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
```

Expected types:

- `_id` -> `string`.
- `order_no` -> `string`.
- `total` -> `decimal`.
- `created_at` -> `date`.
- `ship` -> `object`.
- `items` -> `array`.
- `note` -> `string`, `null`, or `missing`.

### 6.2. Checking Decimal Values

```javascript
lab.orders.countDocuments({
  total: { $type: "decimal" }
});
// 8

lab.orders.find({
  tenantId: "A",
  total: { $gte: NumberDecimal("100.00") }
}).sort({ _id: 1 });
// A-001 and A-003
```

Seeing `125.50` rendered in a GUI **does not prove** the stored type is `Decimal128`; legacy data with mixed types might hold a double or string.

### 6.3. Checking Null vs Missing

```javascript
lab.orders.countDocuments({ note: null });
// 7

lab.orders.countDocuments({
  note: { $exists: false }
});
// 6

lab.orders.countDocuments({
  note: { $type: "null" }
});
// 1
```

MongoDB `{ note: null }` matches both explicit `null` **and missing fields**. A Java entity maps both to `note == null` under standard configs, so inspecting mapped Java objects alone cannot distinguish them.

### 6.4. Inspecting Collection Metadata

```javascript
lab.getCollectionInfos({ name: "orders" });
lab.orders.getIndexes();
```

Both commands inspect actual server collection and index metadata; never infer them solely from entity annotations.

---

## 7. Verifying BSON Directly from Java

Spring Data normally maps BSON into Java entities. To inspect **raw stored data**, use the MongoDB Java Driver via `MongoTemplate.getDb()`:

```java
import org.bson.Document;
import org.bson.types.Decimal128;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import java.util.Date;

MongoCollection<Document> rawCollection =
    mongoTemplate.getDb().getCollection("orders");

Document raw = rawCollection.find(
    Filters.eq("_id", "A-001")
).first();

if (raw == null) {
    throw new AssertionError("Missing test document A-001");
}

System.out.println(raw.get("_id").getClass());
// class java.lang.String

System.out.println(raw.get("total").getClass());
// class org.bson.types.Decimal128

System.out.println(raw.get("created_at").getClass());
// class java.util.Date
```

Here `mongoTemplate` is injected from the Spring context. Returning a raw driver `Document` bypasses entity mapping into `OrderDoc`, offering an independent view.

### 7.1. Comparing Both Views of One Document

```java
OrderDoc mapped =
    mongoTemplate.findById("A-001", OrderDoc.class);

Document raw =
    mongoTemplate.getDb()
        .getCollection("orders")
        .find(Filters.eq("_id", "A-001"))
        .first();

assert mapped != null;
assert raw != null;

System.out.println(mapped.amount());   // BigDecimal
System.out.println(raw.get("total"));  // Decimal128

System.out.println(mapped.createdAt());     // Instant
System.out.println(raw.get("created_at"));  // Date
```

### 7.2. `Converter.write` Only Shows Serialization Intent

```java
Document serialized = new Document();
mongoTemplate.getConverter().write(orderDoc, serialized);
System.out.println(serialized.toJson());
```

This reveals what the converter intends to emit, yet **does not verify the server accepted and stored the write**. After `insert`/`save`, always read back the persisted raw document.

### 7.3. Never Ignore `@Field` Remapping

A Java query on `amount` must translate into BSON `total`; a Java query on `shipping.city` must translate into BSON `ship.city`. When writing raw driver queries directly, always use **BSON field names**, never Java property names.

---

## 8. Verifying Java Save -> MongoDB -> Java Round-Trip

Construct an entity and persist via the converter:

```java
OrderDoc newOrder = new OrderDoc(
    "A-100",
    "A",
    "ORD-A-100",
    "NEW",
    new BigDecimal("19.99"),
    Instant.parse("2026-11-14T08:00:00Z"),
    new Shipping("Hà Nội", "Ba Đình"),
    List.of(new LineItem("PEN", 2)),
    null
);

mongoTemplate.insert(newOrder);
```

Then verify in `mongosh`:

```javascript
lab.orders.findOne(
  { _id: "A-100" },
  { total: 1, created_at: 1, ship: 1 }
);

lab.orders.aggregate([
  { $match: { _id: "A-100" } },
  {
    $project: {
      amountType: { $type: "$total" },
      createdAtType: { $type: "$created_at" }
    }
  }
]).toArray();
```

Expect BSON `total` to be `Decimal128`, `created_at` to be `Date`, and `_id` to be `String`. Back in Java, read with `mongoTemplate.findById()` and compare decimals using `BigDecimal.compareTo()` or AssertJ's `isEqualByComparingTo`.

### 8.1. `Instant` May Lose Sub-Millisecond Precision

```java
Instant t =
    Instant.parse("2026-11-14T08:00:00.123456789Z");
```

BSON `Date` stores milliseconds, so `.456789` nanoseconds are not preserved. Round-trip tests must assert the documented precision contract (e.g., millisecond precision).

### 8.2. Computing Date Ranges in a Business Timezone

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant from = LocalDate.of(2026, 11, 14)
    .atStartOfDay(zone)
    .toInstant();

Instant until = LocalDate.of(2026, 11, 15)
    .atStartOfDay(zone)
    .toInstant();
```

Query `[from, until)` using `$gte` and `$lt` for "November 14 in Vietnam time". Never rely on the JVM default timezone or mistake local dates for UTC.

---

## 9. Derived Queries: Java Names vs BSON Names

Repository:

```java
package com.example.mongo;

import java.math.BigDecimal;
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDoc, String> {

    List<OrderDoc> findByTenantIdAndStatus(
        String tenantId,
        String status
    );

    List<OrderDoc> findByTenantIdAndAmountGreaterThanEqual(
        String tenantId,
        BigDecimal minimum
    );

    List<OrderDoc> findByShipping_City(String city);

    List<OrderDoc> findByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
        String tenantId,
        String status
    );

    long countByTenantIdAndStatus(
        String tenantId,
        String status
    );

    boolean existsByTenantIdAndOrderNo(
        String tenantId,
        String orderNo
    );
}
```

### 9.1. Comparing Against Native Queries

| Java Method | Native BSON Filter / Option |
| --- | --- |
| `findByTenantIdAndStatus("A","PAID")` | `{tenantId:"A",status:"PAID"}` |
| `findByTenantIdAndAmountGreaterThanEqual("A",100)` | `{tenantId:"A",total:{$gte:NumberDecimal("100")}}` |
| `findByShipping_City("Hà Nội")` | `{"ship.city":"Hà Nội"}` |
| `countByTenantIdAndStatus("A","PAID")` | Count scoped by tenant and status |
| `existsByTenantIdAndOrderNo("A","ORD-A-001")` | Existence check on `tenantId` and `order_no` |
| `...OrderByCreatedAtDescIdDesc` | Sort `{created_at:-1,_id:-1}` |

Expected counts for tenant A: PAID = **3**; total >= 100 = **A-001, A-003**.

### 9.2. Nested Paths and Underscores

`findByShipping_City` explicitly separates `shipping.city`; the mapper translates root property `shipping` into BSON `ship`. If the entity also happened to have a Java property named `shippingCity`, `findByShippingCity` would be ambiguous to the parser. Using an underscore disambiguates nested path traversal.

### 9.3. Reserved ID Methods

`findById` is a reserved repository method targeting the **identifier property**, not an arbitrary unannotated field coincidentally named `id`. Whenever refactoring entity IDs, test both `findById` and raw `_id` queries explicitly.

### 9.4. Derived Queries Do Not Automatically Guard Tenant Scope

A derived method like `findByTenantIdAndStatusOrActive` can resolve to:

```javascript
{
  $or: [
    { tenantId: "A", status: "PAID" },
    { active: true }
  ]
}
```

The `active` branch drops the tenant filter and can leak tenant B's data. Write explicit grouping and integration tests for **negative cross-tenant cases**.

---

## 10. `@Query`: Declaring Filters and Verifying Parameter Binding

Spring Data lets you declare MongoDB JSON queries:

```java
import org.springframework.data.mongodb.repository.Query;

@Query("{ 'tenantId': ?0, 'amount': { '$gte': ?1 } }")
List<OrderDoc> amountByQuery(
    String tenantId,
    BigDecimal minimum
);
```

- `?0`: first method argument.
- `?1`: second method argument.
- Spring Data binds arguments and maps field names against entity metadata.

**Do not mistake** the annotation string for the final wire BSON command: `amount` must still map to raw `total`, alongside any sort, projection, or command options.

### 10.1. Properly Scoped OR Queries

```java
@Query("""
    {
      'tenantId': ?0,
      '$or': [
        { 'status': ?1 },
        { 'amount': { '$gte': ?2 } }
      ]
    }
    """)
List<OrderDoc> findTenantCandidates(
    String tenantId,
    String status,
    BigDecimal minimum
);
```

Every returned document must match the requested `tenantId`. Placing the tenant filter inside **only one `$or` branch** creates an access-control breach.

### 10.2. String Parameters and Injection

Spring Data docs state that bound String parameters are escaped during binding, so passing strings containing `$ne` does not automatically turn them into MongoDB operators. However, SpEL `?#{...}` expressions can construct richer queries/subdocuments; sanitize and restrict dynamic inputs, and never concatenate raw JSON from user input.

### 10.3. Field Projections

```java
@Query(
    value = "{ 'tenantId': ?0, 'status': ?1 }",
    fields = "{ 'status': 1, 'amount': 1, 'createdAt': 1 }"
)
List<OrderDoc> findLightweight(
    String tenantId,
    String status
);
```

Spring Data maps field names to their BSON counterparts where supported. Verify the actual emitted projection. Returned entities leave unprojected fields `null` because they were **not loaded**. **Never call `save` on a partial entity**; prefer read-only interface/DTO projections for list endpoints.

---

## 11. `MongoTemplate`, `Criteria`, and `QueryMapper`

Spring Data's fluent query API:

```java
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Criteria;

Query query = new Query(
    Criteria.where("tenantId").is("A")
        .and("amount").gte(new BigDecimal("100.00"))
);

List<OrderDoc> result =
    mongoTemplate.find(query, OrderDoc.class);
```

`Query` is constructed using **Java property names**. `Query.getQueryObject()` reflects the unmapped application-level query object **before field mapping**.

### 11.1. Inspecting the Mapped Query

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.convert.QueryMapper;

var converter = mongoTemplate.getConverter();
var mappingContext = converter.getMappingContext();
var entity = mappingContext.getPersistentEntity(OrderDoc.class);

QueryMapper mapper = new QueryMapper(converter);

Document mapped = mapper.getMappedObject(
    query.getQueryObject(),
    entity
);

System.out.println(mapped.toJson());
// Expect BSON field "total", not Java "amount".
```

This verifies **filter field mapping**, not the server's actual execution plan or the complete wire command including sort, skip, limit, or session metadata.

### 11.2. Reading the Emitted Command via a Driver Listener

The MongoDB Java Driver provides `CommandListener` with `CommandStartedEvent`, `CommandSucceededEvent`, and `CommandFailedEvent`.

```java
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import com.mongodb.event.CommandFailedEvent;
import java.util.concurrent.TimeUnit;

public final class SafeCommandListener implements CommandListener {

    @Override
    public void commandStarted(CommandStartedEvent event) {
        System.out.println(
            "command=" + event.getCommandName()
            + " db=" + event.getDatabaseName()
        );
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        System.out.println(
            "completed=" + event.getCommandName()
            + " nanos=" + event.getElapsedTime(TimeUnit.NANOSECONDS)
        );
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        System.err.println(
            "failed=" + event.getCommandName()
        );
    }
}
```

Attach the listener via `MongoClientSettings.Builder.addCommandListener(...)` inside an appropriate client configuration or Spring Boot customizer.

In an **isolated non-sensitive lab**, you can temporarily inspect `event.getCommand().toJson()` to verify mapped filters, sorts, and projections. In production, **never log raw command literals**, which expose emails, tenant IDs, literals, credentials, and business data.

### 11.3. Do Not Equate Three Different Artifacts

- `query.getQueryObject()` = expression constructed by application code.
- `QueryMapper.getMappedObject(...)` = mapped BSON filter expression.
- `CommandStartedEvent.getCommand()` = actual wire command sent by the driver, including filter, sort, projection, and session metadata.

Even a correct wire command does not prove fast execution; capture server execution evidence.

---

## 12. Indexes Must Actually Exist, Not Just Sit in Annotations

Spring Data supports index annotations such as:

```java
@Indexed
String status;
```

```java
@CompoundIndex(
    name = "ix_tenant_status",
    def = "{ 'tenantId': 1, 'status': 1 }"
)
```

Yet **automatic index creation is disabled by default since Spring Data MongoDB 3.0**. Having `@Indexed` on an entity does not prove the collection holds that index.

### 12.1. Verifying Directly on the Server

```javascript
lab.orders.getIndexes();

lab.runCommand({ listIndexes: "orders" });
```

Right after `insertMany`, expect only the default `_id_` index unless another process created indexes.

### 12.2. Creating Indexes for the Lab

```javascript
lab.orders.createIndex(
  { tenantId: 1, order_no: 1 },
  {
    name: "uq_tenant_order_no",
    unique: true
  }
);

lab.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    created_at: -1,
    _id: -1
  },
  {
    name: "ix_tenant_status_time"
  }
);

lab.orders.getIndexes();
```

Each serves a distinct purpose:

- Unique key `(tenantId, order_no)` guards business identifier uniqueness.
- Compound key `(tenantId, status, created_at, _id)` serves tenant/status filtering plus chronological sorting with a deterministic tie-breaker.

### 12.3. `IndexOperations` in Spring Data

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.index.Index;

mongoTemplate.indexOps(OrderDoc.class).ensureIndex(
    new Index()
        .on("tenantId", Sort.Direction.ASC)
        .on("orderNo", Sort.Direction.ASC)
        .unique()
        .named("uq_tenant_order_no")
);

mongoTemplate.indexOps(OrderDoc.class).ensureIndex(
    new Index()
        .on("tenantId", Sort.Direction.ASC)
        .on("status", Sort.Direction.ASC)
        .on("createdAt", Sort.Direction.DESC)
        .on("id", Sort.Direction.DESC)
        .named("ix_tenant_status_time")
);
```

After running, **read back `getIndexes()`** to confirm Spring Data mapped `orderNo` to `order_no`, `createdAt` to `created_at`, and `id` to `_id`.

Never use `ensureIndex` ad hoc in production to alter an existing index's definition under the same name. When options or data conflict, use a reviewed migration plan and change window.

### 12.4. Why Not Leave Auto-Index Always Enabled?

- Index builds consume CPU, disk I/O, and memory.
- Unique index builds fail if existing data contains duplicates.
- Dropping/recreating a collection while an app is live does not automatically trigger index recreation.
- Production needs controlled migration ordering and rollback.
- Sharded clusters impose unique-index and shard-key constraints.
- Workloads often need hidden, partial, or collated indexes.

**Source annotations state intent; the index catalog records reality.**

---

## 13. Explain: Is the Index Actually Used?

Repository call:

```java
repository.findByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
    "A", "PAID"
);
```

Equivalent MongoDB BSON query:

```javascript
lab.orders.find({
  tenantId: "A",
  status: "PAID"
})
.sort({
  created_at: -1,
  _id: -1
})
.explain("executionStats");
```

Key metrics/stages to inspect:

| Metric / Stage | Meaning |
| --- | --- |
| `nReturned` | Documents returned by the execution |
| `totalKeysExamined` | Index keys scanned |
| `totalDocsExamined` | Documents scanned |
| `executionTimeMillis` | Runtime of this single explain execution |
| `IXSCAN` | Index scan executed |
| `COLLSCAN` | Full collection scan executed |
| `FETCH` | Document lookup following index scan |
| `SORT` | Separate in-memory/blocking sort stage |
| `winningPlan` | Plan selected by the query optimizer |

### 13.1. 8 Records May Still Pick `COLLSCAN`

MongoDB may legitimately pick `COLLSCAN` on an 8-document collection even with a perfect index present, because scanning 8 documents directly can cost less than traversing an index tree. Never write brittle assertions demanding `IXSCAN` on tiny test fixtures.

### 13.2. Using `hint` to Verify Index Capability

```javascript
lab.orders.find({
  tenantId: "A",
  status: "PAID"
})
.sort({
  created_at: -1,
  _id: -1
})
.hint("ix_tenant_status_time")
.explain("executionStats");
```

`hint` forces a candidate index during testing; it **proves index compatibility**, not that the planner will pick it unhinted or that it is fastest for every workload.

### 13.3. Computing Targeting Ratio

\[
\text{Docs per result} =
\frac{\text{totalDocsExamined}}{\text{nReturned}}
\]

For instance, examining 100,000 documents to return 20 gives a ratio of 5,000. Note that when `nReturned = 0`, the denominator is zero; report docs scanned and zero results separately rather than inventing a fake ratio.

### 13.4. An `IXSCAN` Can Still Perform Poorly

```text
IXSCAN keysExamined=400000
FETCH docsExamined=250000
nReturned=5
```

Using an index with poor selectivity or the wrong prefix still scans far too many entries. Inspect predicates, sort keys, cardinality, index size, and representative data distributions.

### 13.5. Explain JSON Evolves Across Server Versions

MongoDB uses multiple execution engines (classic / SBE) whose explain output structure varies by server release and query shape. Avoid brittle tests coupled to internal `winningPlan` JSON paths without a version-compatibility strategy.

---

## 14. Compound Indexes: Filters and Sorts Must Align

Index:

```javascript
{
  tenantId: 1,
  status: 1,
  created_at: -1,
  _id: -1
}
```

Matches:

```javascript
lab.orders.find({
  tenantId: "A",
  status: "PAID"
}).sort({
  created_at: -1,
  _id: -1
});
```

Whereas:

```javascript
lab.orders.find({ status: "PAID" })
  .sort({ created_at: -1 });
```

lacks an equality predicate on the leading field `tenantId`, so this index is not efficient for that query.

### 14.1. Index Field Order

`{tenantId:1,status:1,created_at:-1}` differs fundamentally from `{created_at:-1,tenantId:1,status:1}`. Order keys intentionally using equality/range/sort alignment, query patterns, cardinality, and write costs.

### 14.2. Sort Tie-Breaker

In the fixture, A-003 and A-005 share the exact same `created_at` timestamp, so sorting solely by timestamp allows page order to fluctuate. Adding `_id` as a tie-breaker guarantees deterministic ordering over stable data.

### 14.3. Covered Queries

A query can be satisfied purely from the index when every filtered and projected field resides in the index and satisfies planner rules:

```javascript
lab.orders.find(
  { tenantId: "A", status: "PAID" },
  { tenantId: 1, status: 1, created_at: 1, _id: 0 }
);
```

If `total` must also be returned while absent from the index, a `FETCH` stage is required. Never assume a Spring Data interface projection automatically produces a covered query.

---

## 15. Unique Indexes: Verifying with Duplicate Errors

Create the unique index:

```javascript
lab.orders.createIndex(
  { tenantId: 1, order_no: 1 },
  { unique: true, name: "uq_tenant_order_no" }
);
```

Attempt inserting a duplicate business key with a distinct `_id` **only in the lab**:

```javascript
lab.orders.insertOne({
  _id: "A-DUP",
  tenantId: "A",
  order_no: "ORD-A-001",
  status: "NEW",
  total: NumberDecimal("1.00"),
  created_at: ISODate("2026-11-14T08:00:00Z")
});
```

Expect MongoDB to reject the insert with a duplicate-key error (`E11000`) and leave the collection unchanged.

### 15.1. `existsBy` Does Not Prevent Races

```java
if (!repository.existsByTenantIdAndOrderNo(
        "A", "ORD-A-001")) {
    repository.save(newOrder);
}
```

Two concurrent requests can both observe `false` and then insert duplicates. Only a **unique index** enforces protection in the database, paired with explicit application handling of `DuplicateKeyException`.

### 15.2. Unique Index Creation Can Fail

If legacy data holds duplicates, `createIndex(..., {unique: true})` fails. Before migrating:

1. Profile existing duplicates.
2. Define business merge or cleanup policies.
3. Audit `null` and missing values on business-key fields.
4. Check collation implications.
5. Build the index on staging with representative data.
6. Assess write and index-build resource overhead.
7. Execute under an approved change window with rollback ready.

---

## 16. Partial Indexes: Not Every Document Is Indexed

A partial index includes only documents matching `partialFilterExpression`.

```javascript
lab.orders.createIndex(
  { tenantId: 1, created_at: -1 },
  {
    name: "ix_paid_recent",
    partialFilterExpression: {
      status: "PAID"
    }
  }
);
```

### 16.1. Query Eligible for the Partial Index

```javascript
lab.orders.find({
  tenantId: "A",
  status: "PAID"
}).sort({ created_at: -1 });
```

Queries matching the partial filter subset can use this partial index.

### 16.2. Query Ineligible for the Partial Index

```javascript
lab.orders.find({
  tenantId: "A"
}).sort({ created_at: -1 });
```

Using a partial index containing only `PAID` documents to return **all** tenant A orders would silently omit `NEW` and `CANCELLED` orders. Therefore the planner refuses to use it when completeness cannot be guaranteed.

### 16.3. Verification

- Inspect `partialFilterExpression` via `getIndexes()`.
- Compare `explain` with and without the `PAID` filter predicate.
- Never force `hint()` on a partial index for an unmatching query and treat incomplete output as valid.
- In Spring Data, verify emitted commands still preserve the partial predicate after repository refactors.

---

## 17. TTL Indexes: Deletion Timing Is Not Deterministic

MongoDB's TTL monitor deletes eligible documents **asynchronously** in background passes, not at the exact expiration millisecond.

Separate lab-only `sessions` example:

```javascript
lab.sessions.drop();

lab.sessions.insertMany([
  {
    _id: "S-old",
    createdAt: ISODate("2026-01-01T00:00:00Z")
  },
  {
    _id: "S-future",
    createdAt: ISODate("2030-01-01T00:00:00Z")
  }
]);

lab.sessions.createIndex(
  { createdAt: 1 },
  {
    name: "ttl_sessions_1day",
    expireAfterSeconds: 86400
  }
);
```

### 17.1. Testing Properly

- Verify the stored field is a BSON `date`.
- Verify the index carries `expireAfterSeconds`.
- When testing actual deletion, poll with a generous timeout rather than asserting removal within 1 second.
- Respect TTL index-type constraints; do not attach TTL options arbitrarily to compound indexes.
- When business security demands **immediate** expiry of stale sessions, filter `expiresAt` in application queries instead of relying solely on background TTL cleanup.

### 17.2. Spring `@Indexed(expireAfter)`

Spring Data provides TTL annotation attributes in supported versions, yet annotations never prove the live index exists. Check `getIndexes()` and confirm BSON `Date` storage on the server.

---

## 18. Collation and Unicode: Queries and Indexes Must Match

Collation governs locale-specific string comparison, case sensitivity, and diacritics.

```javascript
lab.orders.createIndex(
  { "ship.city": 1 },
  {
    name: "ix_city_collated",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
```

Query:

```javascript
lab.orders.find({
  "ship.city": "hà nội"
}).collation({
  locale: "en",
  strength: 2
});
```

Locale `en` here illustrates syntax only; **do not assume it is the right default for Vietnamese**. For Vietnamese business rules, validate locale and Unicode normalization behavior with real data.

### 18.1. Index Collation vs Query Collation

An index whose collation differs from a query's collation may not accelerate string comparisons or sorts as expected. Verify:

- Collation recorded in `getIndexes()`.
- Collation emitted in the actual wire command.
- Index chosen in `explain`.
- Edge-case tests covering uppercase/lowercase, diacritics, and Unicode normalization forms.

### 18.2. `@Query` Collation

```java
@Query(
    value = "{ 'shipping.city': ?0 }",
    collation = "en"
)
List<OrderDoc> byCityWithCollation(String city);
```

In production code, apply the policy-approved locale and confirm Spring Data maps `shipping.city` to BSON `ship.city`. Never treat case-insensitive regexes as equivalent to collation-based equality.

---

## 19. Array Queries: Use `$elemMatch` When Requiring the Same Element

Fixture:

```javascript
{
  items: [
    { sku: "PEN", quantity: 2 },
    { sku: "BOOK", quantity: 1 }
  ]
}
```

Query:

```javascript
{
  "items.sku": "BOOK",
  "items.quantity": { $gte: 2 }
}
```

matches the document above across **two distinct array elements**, even though no `BOOK` item has `quantity >= 2`.

Instead use:

```javascript
{
  items: {
    $elemMatch: {
      sku: "BOOK",
      quantity: { $gte: 3 }
    }
  }
}
```

Expected match in fixture: **A-003**.

Spring Data:

```java
@Query("""
{
  'tenantId': ?0,
  'items': {
    '$elemMatch': {
      'sku': ?1,
      'quantity': { '$gte': ?2 }
    }
  }
}
""")
List<OrderDoc> findWithLineItem(
    String tenantId,
    String sku,
    int minQty
);
```

When using a multikey index on an array field, check compound multikey bounds, `$elemMatch`, and `explain`. Never verify only Java result lists without understanding MongoDB's array matching semantics.

---

## 20. `Page`, `Slice`, Sort, and Count Queries

Repository method:

```java
Page<OrderDoc> findByTenantIdAndStatus(
    String tenantId,
    String status,
    Pageable pageable
);
```

Called with:

```java
Pageable pageRequest = PageRequest.of(
    0, 2,
    Sort.by(Sort.Direction.DESC, "createdAt")
        .and(Sort.by(Sort.Direction.DESC, "id"))
);
```

`Page` returns both content and total count. Spring Data **can issue an additional count query** to compute `totalElements`, though optimizations may skip it in edge cases—so do not hardcode assertions expecting "always two commands".

### 20.1. `Slice` Avoids Computing Total Count

```java
Slice<OrderDoc> findSliceByTenantIdAndStatus(
    String tenantId,
    String status,
    Pageable pageable
);
```

`Slice` only needs to know whether a next page exists, typically fetching `pageSize + 1` documents and skipping the full count query.

**Never declare two methods with the same name and parameters differing only in `Page` vs `Slice` return type**: Java does not permit overloading solely by return type.

### 20.2. Sorting Uses Java Property Names

`Sort.by("createdAt", "id")` translates to BSON `created_at` and `_id`. Sorting solely by `createdAt` is unstable when timestamps collide (A-003 and A-005 in our fixture share `created_at`).

### 20.3. Deep Offsets Are Expensive

`PageRequest.of(50000, 20)` translates into a massive `skip`. When concurrent writes mutate data between requests, offset paging yields duplicates or skipped rows. For large feeds, prefer keyset/scroll pagination over `(created_at, _id)` backed by a matching index.

---

## 21. Partial Projections and the Risk of `save` Overwrites

A `@Query(fields=...)` may load only `_id`, `status`, and `total`:

```java
@Query(
    value = "{ 'tenantId': ?0 }",
    fields = "{ 'status': 1, 'amount': 1 }"
)
List<OrderDoc> findLightweight(String tenantId);
```

Omitted fields map to `null` or defaults in Java. If a service mutates one field and invokes `repository.save(partial)`, `save` can **replace the document with missing fields wiped out**.

Remedies:

- Use DTO or interface projections for read endpoints.
- Never treat a partial entity as a full domain aggregate.
- For mutations, use targeted `MongoTemplate.updateFirst`/`@Update` with explicit filters and update operators.
- Combine `@Version` or conditional update predicates when concurrency protection is needed.

Targeted update example:

```java
Query q = new Query(
    Criteria.where("id").is("A-002")
        .and("tenantId").is("A")
);

Update update = new Update().set("status", "PAID");

mongoTemplate.updateFirst(
    q,
    update,
    OrderDoc.class
);
```

Spring Data maps Java `id` to BSON `_id`.

---

## 22. Optimistic Locking and Concurrent Writes

Entity:

```java
@Document("versioned_orders")
public class VersionedOrder {
    @MongoId(FieldType.STRING)
    private String id;

    @Version
    private Long version;

    private String status;

    // Constructors/getters/setters...
}
```

Spring Data includes the version in save predicates; when two clients read the same version and both save changes, the stale update is rejected once the version increments.

Verify this with an integration test under an acknowledged write concern; low-level bulk operations and custom updates **do not automatically carry identical semantics** to saving a `@Version` entity via repository `save`.

### 22.1. Test Scenario

1. Create document `id=V-1` with an initial version.
2. Have two sessions or operations load the same version.
3. Writer A changes `status` and saves.
4. Writer B attempts to save its stale copy.
5. Assert Writer B fails with an optimistic-locking exception per API.
6. Read the raw document to verify only the valid winning state persisted.

Mocked repositories cannot verify this behavior.

---

## 23. Transactions Must Be Verified on a Supported Topology

Calling `repository.save()` twice across two collections **does not form an atomic multi-document transaction**.

Spring Data supports `MongoTransactionManager`/`@Transactional` once configured, and multi-document transactions require a supporting MongoDB deployment (replica set or sharded cluster meeting version prerequisites).

### 23.1. Rollback Test

1. Start the transaction.
2. Insert the order.
3. Insert the audit event.
4. Throw an exception prior to commit.
5. Query the raw database outside the transaction.
6. Assert zero partial writes persisted.

Never run transaction tests on standalone MongoDB assuming it mirrors replica-set behavior. Verify write concern, read concern, session lifecycle, and retry semantics.

---

## 24. Verifying with `@DataMongoTest`

Spring Boot's `@DataMongoTest` creates a focused test slice for Spring Data MongoDB mapping and repositories.

Illustrative example using Spring Boot 3.x imports:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
class OrderRepositoryMappingTest {

    @Autowired
    MongoTemplate template;

    @Autowired
    OrderRepository repository;

    @Test
    void databaseIsLab() {
        assertThat(template.getDb().getName())
            .isEqualTo("spring_data_bson_lab");
    }
}
```

**Important:** the test slice does not automatically seed our 8 fixture documents; seed explicitly against an isolated test URI. Under Spring Boot 4 or other releases, test auto-configuration package paths may differ.

### 24.1. Testcontainers for Isolated Environments

Example for **Testcontainers 1.x + Spring Boot 3.x** (package paths may differ in Testcontainers 2.x):

```java
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;

import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@Testcontainers
@DataMongoTest
class OrderRepositoryIT {

    @Container
    static final MongoDBContainer mongo =
        new MongoDBContainer(
            DockerImageName.parse("mongo:8.0")
        );

    @DynamicPropertySource
    static void dbProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            mongo::getReplicaSetUrl
        );
    }

    // Inject MongoTemplate and OrderRepository.
    // Seed fixtures in @BeforeEach or equivalent setup.
    // Assert raw BSON, derived queries, and indexes.
}
```

Do not mix Testcontainers 1.x and 2.x binary APIs or imports. CI must have a container runtime or a dedicated isolated MongoDB test cluster.

**Never silently fall back** to a production MongoDB URI if Docker or the test container fails to start.

---

## 25. Integration Test 1: Verifying Field Names and BSON Types

Assuming `mongoTemplate` is autowired in the test class:

```java
@Test
void persistsDecimal128AndMappedFields() {
    OrderDoc order = new OrderDoc(
        "A-TYPE",
        "A",
        "ORD-A-TYPE",
        "PAID",
        new BigDecimal("125.50"),
        Instant.parse("2026-11-14T08:00:00Z"),
        new Shipping("Hà Nội", "Ba Đình"),
        List.of(new LineItem("BOOK", 2)),
        "ok"
    );

    mongoTemplate.insert(order);

    Document raw = mongoTemplate.getDb()
        .getCollection("orders")
        .find(Filters.eq("_id", "A-TYPE"))
        .first();

    assertThat(raw).isNotNull();
    assertThat(raw.get("_id"))
        .isInstanceOf(String.class);
    assertThat(raw.get("total"))
        .isInstanceOf(Decimal128.class);
    assertThat(raw.get("created_at"))
        .isInstanceOf(Date.class);
    assertThat(raw.containsKey("amount")).isFalse();
    assertThat(raw.containsKey("createdAt")).isFalse();

    OrderDoc reread =
        mongoTemplate.findById("A-TYPE", OrderDoc.class);

    assertThat(reread.amount())
        .isEqualByComparingTo("125.50");
}
```

Required imports include `org.bson.Document`, `org.bson.types.Decimal128`, `com.mongodb.client.model.Filters`, `java.util.Date`, `java.time.Instant`, `java.math.BigDecimal`, `java.util.List`, and AssertJ.

This verifies the **BSON storage contract**, not merely a Java return value.

---

## 26. Integration Test 2: Derived Queries vs `@Query`

Assuming the fixture is seeded in the test database:

```java
List<OrderDoc> derived =
    repository.findByTenantIdAndAmountGreaterThanEqual(
        "A", new BigDecimal("100.00")
    );

List<OrderDoc> annotated =
    repository.amountByQuery(
        "A", new BigDecimal("100.00")
    );

Set<String> derivedIds = derived.stream()
    .map(OrderDoc::id)
    .collect(Collectors.toSet());

Set<String> annotatedIds = annotated.stream()
    .map(OrderDoc::id)
    .collect(Collectors.toSet());

assertThat(derivedIds)
    .containsExactlyInAnyOrder("A-001", "A-003");

assertThat(annotatedIds)
    .isEqualTo(derivedIds);
```

With `@Query`:

```java
@Query("{ 'tenantId': ?0, 'amount': { '$gte': ?1 } }")
List<OrderDoc> amountByQuery(
    String tenantId,
    BigDecimal minimum
);
```

Also cross-check against a native query referencing BSON field `total` as an independent oracle. If Spring Data fails to map fields as expected, the test fails immediately.

### 26.1. Testing Nested Mapping

```java
Set<String> ids =
    repository.findByShipping_City("Hà Nội")
        .stream()
        .map(OrderDoc::id)
        .collect(Collectors.toSet());

assertThat(ids).containsExactlyInAnyOrder(
    "A-001", "A-003", "B-001"
);
```

### 26.2. Testing Tenant Isolation

Every tenant-A endpoint must return only `tenantId == A` even with `$or`, sorts, or projections. Seed tenants A and B and run negative conditions matching only tenant B records to catch cross-tenant leaks.

---

## 27. Integration Test 3: Index Catalog and Duplicates

After creating indexes in test setup, verify:

```java
import org.springframework.data.mongodb.core.index.IndexInfo;

List<IndexInfo> infos =
    mongoTemplate.indexOps(OrderDoc.class)
        .getIndexInfo();

assertThat(infos)
    .extracting(IndexInfo::getName)
    .contains("uq_tenant_order_no", "ix_tenant_status_time");
```

To confirm exact **key order** and `unique` options, inspect the raw catalog:

```java
List<Document> rawIndexes =
    mongoTemplate.getDb()
        .getCollection("orders")
        .listIndexes()
        .into(new ArrayList<>());

rawIndexes.forEach(index ->
    System.out.println(index.toJson())
);
```

An index matching by name yet holding the wrong `key`, `collation`, or `partialFilterExpression` still breaks queries or uniqueness.

### 27.1. Duplicate Key Test

With A-001 and the unique index present:

```java
assertThatThrownBy(() ->
    repository.save(new OrderDoc(
        "A-DUP",
        "A",
        "ORD-A-001",
        "NEW",
        new BigDecimal("1.00"),
        Instant.parse("2026-11-14T08:00:00Z"),
        new Shipping("Hà Nội", "Ba Đình"),
        List.of(),
        null
    ))
).isInstanceOf(DuplicateKeyException.class);
```

If the test database lacks the index, the save succeeds and this assertion **exposes the missing index provisioning**.

---

## 28. Integration Test 4: Do Not Assert `IXSCAN` on a Tiny Fixture

With just 8 documents, the planner may quite reasonably choose `COLLSCAN`. Do not write brittle assertions forcing:

```java
// Do not treat this as a correctness contract across all datasets:
assertThat(explain.toJson()).contains("IXSCAN");
```

Instead, split verification cleanly:

1. **Correctness:** returns expected IDs, BSON types, and null/missing handling.
2. **Index catalog:** key order, uniqueness, collation, TTL, and partial options exist.
3. **Index capability:** use `hint` in lab tests with `explain` to verify the index can serve the query.
4. **Performance:** generate a representative dataset and measure examined keys/docs and p95/p99 across multiple runs.
5. **Production:** monitor logs/Atlas metrics post-rollout with rollback ready on regressions.

`executionTimeMillis` from a single `explain` call is not API p99 latency. Profilers and APM capture real workload latency.

---

## 29. When Production Data Drifts from Schema

Legacy data:

```javascript
{
  _id: "LEGACY-1",
  tenantId: "A",
  amount: 125.50,
  createdAt: "2026-11-10",
  status: "PAID"
}
```

New entity expectation:

```javascript
{
  _id: "LEGACY-1",
  tenantId: "A",
  total: NumberDecimal("125.50"),
  created_at: ISODate("2026-11-10T00:00:00Z"),
  status: "PAID"
}
```

Consequences:

- Entity mapping may read `amount` as `null` or raise conversion failures.
- Derived queries filtering `amount` translate to `total` and miss legacy documents.
- Date strings do not compare identically to BSON Dates.
- An index on `total` does not accelerate lookups for documents still storing legacy `amount`.
- A naive rewrite migration risks losing decimal precision if accidentally routed through `double`.

### 29.1. Profiling Schema Drift

```javascript
lab.orders.aggregate([
  {
    $group: {
      _id: {
        totalType: { $type: "$total" },
        createdAtType: { $type: "$created_at" }
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]).toArray();
```

In large production collections, consider resource impact—sample, run on staging, or schedule an approved batch job.

### 29.2. Migration Plan

1. Inventory legacy vs target field names and BSON types.
2. Profile raw documents grouped by `$type`.
3. Design converters/migrations that preserve decimal precision and timezone semantics.
4. Maintain backward compatibility during rolling deploys.
5. Prepare backups, rollback plans, and monitoring.
6. Test BSON round-trips and repository queries.
7. Apply index migrations.
8. Monitor query errors, duplicates, and latency.
9. Remove compatibility shims once all services upgrade.

Never run a massive production `updateMany()` before validating data distributions and recovery procedures.

---

## 30. Verification Matrix for a Release

| Contract | Test Data | Evidence |
| --- | --- | --- |
| ID type | Plain strings and 24-hex strings | Raw `_id` + `$type` |
| Java `amount` -> BSON `total` | 125.50, 19.99 | Raw BSON `Decimal128` |
| Java `createdAt` -> `created_at` | UTC boundaries | BSON `Date` + range |
| Nested `shipping.city` | Hà Nội / Đà Nẵng | Raw `ship.city` |
| Missing vs null | missing and explicit null `note` | `$exists`/`$type` |
| Same array element | `BOOK` and `quantity >= 3` | `$elemMatch` |
| Derived query accuracy | Tenant A + `total >= 100` | Expected ID set |
| `@Query` accuracy | Same criteria as derived | Set equality + command |
| Tenant isolation | A/B + OR filters | Negative integration tests |
| Unique business key | Duplicate tenant/`order_no` | Index spec + `E11000` |
| Live indexes | Compound index name/keys | `getIndexes` |
| Index usage | Filter + sort | Explain / Profiler |
| Field projections | Subset of fields | Emitted command + raw payload |
| Page count | Page size 2 | `Page` + command metrics |
| Deterministic sort | Identical `created_at` | `_id` tie-breaker |
| TTL option | `expireAfterSeconds` | Catalog + eventual expiry test |
| Partial index | `PAID` vs all statuses | Catalog + Explain |
| Collation | Upper/lower case, diacritics | Query + index collation |
| Optimistic version | Two stale writers | Real concurrent test |
| Transaction | Injected failure rollback | Raw post-transaction read |
| Performance | Production-scale dataset | p95/p99 + scan counts + resources |

**Key takeaway:** every row in this matrix merits an independent assertion and clear test data rather than bundling everything into a single `assertNotNull`.

---

## 31. Common Mistakes

| False Assumption | Reality |
| --- | --- |
| "Passing repository mocks proves BSON is right." | Mocks bypass mappers and MongoDB Server. |
| "Java property names always match BSON fields." | `@Field` renames fields. |
| "`@Id String` always stores a BSON string." | Spring applies `ObjectId` conversion rules to valid hex strings. |
| "`BigDecimal` defaults to `Decimal128` automatically." | Requires explicit mapping/`targetType` and raw verification. |
| "`Instant` preserves all nanoseconds in MongoDB." | BSON `Date` stores millisecond precision. |
| "Java `null` separates missing fields from explicit nulls." | Both deserialize to Java `null`. |
| "`IsNull` only matches explicit nulls." | Null equality matches missing fields too. |
| "Two array dot-path predicates always match one element." | Requires `$elemMatch` for same-element matching. |
| "`@Indexed` guarantees the index exists." | Auto-index creation is off by default since 3.0. |
| "An existing index guarantees queries use it." | The optimizer still chooses among plans. |
| "`IXSCAN` automatically means optimal performance." | An index scan can still inspect too many keys. |
| "`COLLSCAN` on 8 docs proves the index is broken." | Tiny collections often favor collection scans. |
| "`Query.getQueryObject` equals the wire command." | It sits pre-mapping and lacks command options. |
| "JSON `@Query` runs faster than derived queries." | Equivalent query plans yield equivalent server performance. |
| "`Page` never triggers a count query." | It often runs an extra count query. |
| "Partial indexes accelerate every query." | Queries must imply the partial filter predicate. |
| "TTL deletes documents at the exact expiry second." | Background TTL sweeps are asynchronous. |
| "`existsBy` prevents duplicate-key race conditions." | Only a database unique index prevents races. |
| "Partial projections can safely be saved back." | Unloaded fields risk being overwritten. |
| "Case-insensitive regex always uses indexes efficiently." | Depends on anchoring, regex structure, and collation. |
| "One Explain run equals production p99." | Must benchmark realistic workloads. |
| "Mocks eliminate the need for Testcontainers." | Integration tests must exercise real MongoDB behavior. |
| "Logging full commands in production is harmless." | Leaks sensitive literals, PII, and credentials. |
| "Schema migrations only change Java model classes." | Existing data and index catalogs must migrate too. |

---

## 32. Practice Exercises

### Exercise 1 — Evidence Layers

List at least five layers from Java entities down to execution plans that must be inspected when verifying Spring Data MongoDB behavior.

### Exercise 2 — Java Property vs BSON Field

`OrderDoc.amount` uses `@Field(name="total", targetType=DECIMAL128)`. What field name and BSON type does MongoDB store?

**Answer:** `total`, BSON Decimal128.

### Exercise 3 — 24-Hex IDs

Compare raw `_id` values persisted using `@Id String` vs `@MongoId(FieldType.STRING)` for the same 24-hex ID string.

### Exercise 4 — Raw BSON

Write Java code using `MongoTemplate.getDb().getCollection("orders")` to fetch Document A-001 and inspect the runtime Java/BSON class of `total`.

### Exercise 5 — Converter vs Persisted Data

Why isn't calling `converter.write()` sufficient proof that the server stored the document as expected?

### Exercise 6 — `$type`

Write an aggregation returning the BSON types of `_id`, `order_no`, `total`, `created_at`, `ship`, and `items`.

### Exercise 7 — Fixture Counts

How many documents belong to Tenant A? How many belong to Tenant A with status `PAID`?

**Answer:** 5 and 3.

### Exercise 8 — Decimal128 Ranges

Write both a native query and a derived repository method retrieving Tenant A orders with total >= 100.

**Answer:** A-001 and A-003.

### Exercise 9 — `Instant`

Compute the UTC interval corresponding to November 14, 2026 in Vietnam time (`Asia/Ho_Chi_Minh`). Why use `[from, to)`?

### Exercise 10 — Milliseconds

`Instant` carries nanoseconds; does BSON `Date` preserve all of them?

**Answer:** No.

### Exercise 11 — Missing vs Null

In our fixture, how many documents have missing `note`, how many have explicit `null`, and how many match `{note: null}`?

**Answer:** 6, 1, 7.

### Exercise 12 — Nested Paths

What BSON path does Java `shipping.city` map to?

**Answer:** `ship.city`.

### Exercise 13 — `$elemMatch`

Why use `$elemMatch` when matching `sku=BOOK` and `quantity>=3` on the same line item?

### Exercise 14 — Derived vs `@Query` Equivalence

Write two methods querying `tenantId=A, total>=100` and compare both returned ID sets and emitted commands.

### Exercise 15 — `QueryMapper`

Explain why `Query.getQueryObject()` can differ from the final filter sent to MongoDB Server.

### Exercise 16 — `CommandListener`

Design a listener logging command names and durations without logging literal query values or PII.

### Exercise 17 — Index Catalog

Create unique `(tenantId, order_no)` and inspect `getIndexes()` to confirm the `unique` option.

### Exercise 18 — Auto-Index Creation

Does Spring Data create indexes automatically from `@CompoundIndex` by default?

**Answer:** No, automatic creation is disabled by default since 3.0.

### Exercise 19 — Tiny Datasets

An index exists yet `explain` on 8 documents picks `COLLSCAN`. Does that prove the index is wrong?

**Answer:** No.

### Exercise 20 — Hinting

What does `hint("ix_tenant_status_time")` prove, and what does it NOT prove?

### Exercise 21 — Query Targeting

100,000 docs examined for 20 results -> what is the ratio?

**Answer:** 5,000 docs/result.

### Exercise 22 — Compound Prefixes

When does an index on `(tenantId, status, created_at)` assist a query that omits `tenantId`?

### Exercise 23 — Covered Queries

When can MongoDB avoid the `FETCH` stage? Why doesn't specifying a projection automatically make a query covered?

### Exercise 24 — `existsBy` Races

Two concurrent requests both see `exists=false` and insert duplicates; what actually enforces protection?

**Answer:** A unique index plus duplicate-key handling.

### Exercise 25 — Partial Indexes

Why can't a partial index containing only `PAID` orders serve a query listing all order statuses?

### Exercise 26 — TTL

Create a 24h TTL index on `sessions`. Why shouldn't tests assert deletion at the exact expiry second?

### Exercise 27 — Collation

How can a mismatch between index collation and query collation affect query plans?

### Exercise 28 — Saving Partial Entities

Explain the hazard of reading a field-projected entity and passing it to `save()`.

### Exercise 29 — Versioning

Design a concurrency test for `@Version`: one writer succeeds while the stale writer fails.

### Exercise 30 — Transactions

Insert an order and audit record in a transaction, throw an exception, and inspect the raw database to verify rollback.

### Exercise 31 — `Page` vs `Slice`

For a "Load more" UI, how does `Slice` avoid count query overhead?

### Exercise 32 — Tenant Isolation

Write a negative test catching `(tenant=A AND status=PAID) OR amount>=100` leaking Tenant B data.

### Exercise 33 — Legacy Data

Legacy documents store `amount` as `double`, while the new entity maps `total` as `Decimal128`. List at least three possible failures.

### Exercise 34 — Testcontainers

Why do integration tests need a real MongoDB instance? What should you check regarding Testcontainers 1.x vs 2.x imports?

### Exercise 35 — Index Migrations

Local has the unique index, while staging does not. Draft a preflight checklist before building it on staging.

### Exercise 36 — Explain Regressions

After building a new index, p99 latency climbs. Which metrics and plan details should you collect?

### Exercise 37 — Stable Sorting

A-003 and A-005 share identical `created_at` values. Why include `_id` in pagination sorts?

### Exercise 38 — Collection Validation

Inspect live validators via `getCollectionInfos()` and test inserting a mistyped document in the lab to verify enforcement.

### Exercise 39 — Performance Benchmarking

Generate ~100k representative documents and measure p95/p99, `docsExamined`, `keysExamined`, index storage footprint, and write overhead.

### Exercise 40 — Capstone

Design a release checklist for renaming Java property `amount` -> `grossAmount` while preserving BSON field `total` as `Decimal128`, adding a range query and compound index, guaranteeing tenant isolation, and verifying mapping, queries, indexes, and `explain` pre-rollout.

---

## 33. Production Verification Checklist

### Java / BSON

- [ ] Entity mapping annotations match actual database schema.
- [ ] String vs ObjectId IDs verified via raw `$type`.
- [ ] `Decimal128`, `Date`, null/missing, nested fields, and arrays verified.
- [ ] Mocks are never used as evidence of MongoDB behavior.
- [ ] `_class` and custom converters verified for cross-service interop.
- [ ] Schema migration plan exists for legacy records.

### Queries

- [ ] Derived queries reference valid Java property paths.
- [ ] `@Query` bindings and mapped BSON field names verified.
- [ ] Tenant scope enforced across every OR branch, write, and delete.
- [ ] Sorts include a deterministic tie-breaker.
- [ ] `Page`/count query cost evaluated.
- [ ] Partial entities are never passed to full `save()`.
- [ ] Large collections are never materialized unbounded.
- [ ] Logs and query tracing redact sensitive values.

### Indexes and Execution

- [ ] Required indexes exist in the live catalog.
- [ ] Key order, options, uniqueness, collation, partial, and TTL settings match specs.
- [ ] Auto-index behavior is explicitly controlled rather than guessed.
- [ ] Versioned index migrations and rollback plans exist.
- [ ] `explain` verified against the actual emitted command's filter, sort, and projection.
- [ ] `nReturned`, `docsExamined`, `keysExamined`, and plan stages reviewed.
- [ ] No brittle `IXSCAN` assertions on tiny fixtures.
- [ ] `hint` is not hardcoded carelessly in production.
- [ ] Write and replication impact of indexes monitored.

### Testing and Operations

- [ ] Integration tests run against real MongoDB in an isolated environment.
- [ ] Seed oracle verifies expected BSON types and ID sets.
- [ ] Tests cover duplicates, null/missing, nested arrays, and tenant isolation.
- [ ] Transactions and `@Version` concurrency tested if used.
- [ ] Benchmarked with representative corpus size and concurrency.
- [ ] App p95/p99, errors, pool waits, and DB CPU/disk monitored.
- [ ] Rollback plans prepared for schema, index, and query changes.
- [ ] Zero PII, passwords, or unredacted commands logged in production.

---

## 34. Summary

Verifying Spring Data MongoDB requires observing **actual MongoDB behavior**, rather than trusting Java declarations or mocked repositories alone.

1. **Mapping is not storage:** use raw BSON and `$type` to verify `@Field`, `@MongoId`, `Decimal128`, `Date`, and nested fields.
2. **Query code is not the wire command:** derived methods, `@Query`, and `MongoTemplate` pass through converters and mappers; inspect mapped filters or driver commands whenever uncertain.
3. **Index annotations are not the catalog:** automatic index creation defaults to off since Spring Data MongoDB 3.0; inspect `getIndexes()`/`listIndexes()`.
4. **An existing index does not prove usage:** run `explain`, evaluate scanned counts and sorts, and test against representative volumes instead of demanding `IXSCAN` on 8 documents.
5. **Correctness spans multiple semantics:** missing vs `null`, array `$elemMatch`, collations, tenant scoping, unique constraints, transactions, and optimistic locking.
6. **Integration tests against real MongoDB** provide trustworthy evidence for mapping, queries, and indexes; mocks cover only unit-level business flow.
7. **Performance must be measured under realistic load**, combining app p95/p99, pool wait times, and MongoDB server metrics.

The ultimate question to keep asking is:

> **"What BSON did MongoDB actually store, which wire command did it receive, which indexes actually exist, and how did it execute the query?"**

### Official Documentation and References

- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html) — `MappingMongoConverter`, `@Id`, `@MongoId`, `@Field`, conversion.
- [Spring Data MongoDB — Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html) — auto-index defaults, `IndexResolver`, `IndexOperations`.
- [Spring Data MongoDB — Repository Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html) — derived methods, `@Query`, binding, pagination.
- [Spring Data MongoDB — MongoTemplate Query Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html) — `Criteria`, `Query`, fields, hints, collation.
- [Spring Data MongoDB — Projections](https://docs.spring.io/spring-data/mongodb/reference/repositories/projections.html) — DTO and interface projections.
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — sessions and transaction management.
- [Spring Boot — MongoDB](https://docs.spring.io/spring-boot/reference/data/nosql.html) — starters and configuration.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html) — integration testing support.
- [MongoDB — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/) — ObjectId, Date, Decimal128, null.
- [MongoDB — Query Operators](https://www.mongodb.com/docs/manual/reference/operator/query/) — `$type`, `$exists`, `$elemMatch`, ranges.
- [MongoDB — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — `IXSCAN`, `COLLSCAN`, execution stats.
- [MongoDB — Indexes](https://www.mongodb.com/docs/manual/indexes/) — compound, partial, unique, TTL, collation.
- [MongoDB — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — `partialFilterExpression`.
- [MongoDB — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — uniqueness enforcement.
- [MongoDB — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/) — TTL monitor.
- [MongoDB — Collation](https://www.mongodb.com/docs/manual/reference/collation/) — locale-based comparisons.
- [MongoDB Java Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/) — command listeners and pool events.
- [Testcontainers — MongoDB](https://java.testcontainers.org/modules/databases/mongodb/) — isolated test database.
