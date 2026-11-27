# Inspecting Actual Documents to Verify Field Names and Data Types

## 1. Why Inspect Stored Data?

In **Spring Data MongoDB**, Java classes describe how the application *intends* to map data, whereas BSON documents in MongoDB reflect what the application *actually wrote*. The two representations are not guaranteed to match completely:

- Java property `customerId` may be stored under `customer_id` via `@Field`.
- Java property `id` is typically stored in MongoDB's `_id` field; the BSON type may be `string` or `objectId` depending on declarations and written values.
- `BigDecimal` can be stored in multiple types depending on mapping/converters; to be sure it is stored as BSON `decimal`, you must declare it and **inspect actual values**.
- `Instant` should be checked to confirm whether it is stored as BSON Date or a character string; BSON Date has millisecond precision.
- Nested objects and `List`s create subdocuments and arrays, though custom converters can alter representations.
- Older documents may lack fields, hold `null`, or use different types than newer documents.

Therefore, the right verification workflow compares **three layers**:

1. **Java model:** fields, record components, `@Id`, `@MongoId`, `@Field`, converters.
2. **Stored BSON:** field names, types, nested structures, and values in the collection.
3. **Java object after read:** whether data reconstructed by Spring Data matches expectations.

This lesson belongs to the **Basic Mapping** chapter, using module **SPRING_DATA_MONGODB**: connecting and mapping documents, accessing via repositories or `MongoTemplate`, and then using queries, aggregations, indexes, tests, and diagnostics to detect discrepancies. This section focuses on **verifying current storage state** before diving deep into optimization or migrations.

## 2. Scenario: An Order with Different Data Types

Suppose an application manages orders consisting of an order ID, customer ID, order placement timestamp, total amount, payment status, and line items. The goal is to know the exact field names and BSON types MongoDB stores.

### 2.1. Java Model with Explicit Mapping

The example uses Java 17+ and Spring Data MongoDB. The `import` statements below are the ones required for the model:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record OrderDocument(
    @MongoId(FieldType.STRING)
    String id,

    @Field("customer_id")
    String customerId,

    @Field("placed_at")
    Instant placedAt,

    @Field(value = "total_amount", targetType = FieldType.DECIMAL128)
    BigDecimal totalAmount,

    @Field("is_paid")
    Boolean paid,

    List<OrderLine> items
) {
    public record OrderLine(
        @Field("product_id")
        String productId,

        int quantity,

        @Field(value = "unit_price", targetType = FieldType.DECIMAL128)
        BigDecimal unitPrice
    ) {}
}
```

Key points:

- `@Document(collection = "orders")` selects the `orders` collection.
- `@MongoId(FieldType.STRING)` declares `id` as a BSON string in the `_id` field. This expresses an explicit intent for string IDs; using only `@Id String` in common setups/operations can convert strings shaped like valid ObjectIds into BSON `ObjectId`.
- `@Field("customer_id")` and `@Field("placed_at")` change the **stored name in MongoDB** without changing Java field names.
- `@Field(targetType = FieldType.DECIMAL128)` requests storing `BigDecimal` values as BSON Decimal128 via the corresponding mapping.
- `List<OrderLine>` represents an array of subdocuments; `productId` becomes `product_id` inside each element.
- `Boolean paid` allows representing missing/null values in the Java layer. In real business logic, you can enforce non-null flags via validation and schema rules.

When a repository calls `save` or `insert` under Spring Data's default mapping, the document may also include metadata fields such as `_class`. That depends on `MappingMongoConverter`/type mapper settings and type mapping behavior; do not conclude from the Java class alone.

### 2.2. Expected BSON Document Example

In `mongosh`, create test data on a **database dedicated to learning/testing**, never running sample write commands against a live environment:

```javascript
db.orders.insertOne({
  _id: "ord-1001",
  customer_id: "cust-01",
  placed_at: ISODate("2026-11-20T01:00:00Z"),
  total_amount: NumberDecimal("1250000.50"),
  is_paid: true,
  items: [
    {
      product_id: "sku-7",
      quantity: NumberInt(2),
      unit_price: NumberDecimal("625000.25")
    }
  ]
});
```

`mongosh`'s `insertOne` command **writes directly**, bypassing Spring Data's converter. It is handy for creating a sample document with explicitly specified BSON types, but it **does not prove** the repository writes data the same way. To verify Java mapping, write using a repository or `MongoTemplate` and then inspect raw data from MongoDB.

## 3. Viewing Raw Documents and BSON Types with mongosh

### 3.1. Choosing the Right Database, Collection, and Record

In a terminal where `mongosh` is connected to the test environment:

```javascript
db.getName();
db.getCollectionNames();
db.orders.findOne({ _id: "ord-1001" });
```

Verify the current database before reading or running write commands. If `findOne` returns `null`, first check the collection, `_id` value, and **ID type**; an identical-looking BSON string differs from a BSON ObjectId.

If the ID is stored as an ObjectId, the filter must use the matching type:

```javascript
// Use only when _id is actually a BSON ObjectId:
db.orders.findOne({ _id: ObjectId("64b000000000000000000001") });

// If _id is a BSON string, query with a string:
db.orders.findOne({ _id: "64b000000000000000000001" });
```

The two queries above are not type-equivalent. Check the actual BSON; do not blindly convert every ID into an ObjectId.

### 3.2. Printing Extended JSON to Clearly See BSON Types

In `mongosh`, special values may be displayed using helpers such as `ISODate(...)`, `Long(...)`, or `Decimal128(...)`. When you need to record diagnostic output or compare types unambiguously, use **Extended JSON (EJSON)**:

```javascript
const doc = db.orders.findOne({ _id: "ord-1001" });

if (doc != null) {
  print(EJSON.stringify(doc, null, 2, { relaxed: false }));
}
```

Canonical mode (`relaxed: false`) represents BSON types using Extended JSON tags, for example:

| BSON Type | Indicator in Canonical Extended JSON |
| --- | --- |
| `ObjectId` | `{"$oid":"..."}` |
| `Date` | `{"$date":{"$numberLong":"..."}}` |
| `Decimal128` | `{"$numberDecimal":"1250000.50"}` |
| `Int32` | `{"$numberInt":"2"}` |
| `Int64` | `{"$numberLong":"2"}` |
| `Double` | `{"$numberDouble":"2.0"}` |
| `String` | Standard JSON string, e.g. `"cust-01"` |
| `Boolean` | `true` or `false` |
| `Null` | `null` |

**EJSON is a representation for inspection and exchange**, not the native binary BSON stored on disk. Inside MongoDB, type information resides in BSON; a string looking like `2026-11-20T01:00:00Z` remains a BSON string if written as a string, and does not automatically become a Date.

### 3.3. Inspecting Types Using Aggregation `$type`

To verify multiple fields at once, use `$type` in an aggregation pipeline:

```javascript
db.orders.aggregate([
  { $match: { _id: "ord-1001" } },
  {
    $project: {
      _id: 0,
      idType: { $type: "$_id" },
      customerType: { $type: "$customer_id" },
      placedAtType: { $type: "$placed_at" },
      totalType: { $type: "$total_amount" },
      paidType: { $type: "$is_paid" },
      itemsType: { $type: "$items" },
      missingFieldType: { $type: "$field_not_present" }
    }
  }
]);
```

For the sample document, the expected result is:

```json
{
  "idType": "string",
  "customerType": "string",
  "placedAtType": "date",
  "totalType": "decimal",
  "paidType": "bool",
  "itemsType": "array",
  "missingFieldType": "missing"
}
```

`$type` in **aggregation** reports the type of the expression being evaluated. When a field does not exist, it returns `"missing"`; for a BSON null value, the result is `"null"`. By contrast, the `$type` operator in a **query filter** has document-matching semantics and behaves differently when evaluating array elements.

### 3.4. Inspecting Types of Nested Fields

Do not merely check that `items` is an array and conclude all array elements are valid. Check the types of inner fields:

```javascript
db.orders.aggregate([
  { $match: { _id: "ord-1001" } },
  { $unwind: "$items" },
  {
    $project: {
      _id: 0,
      productIdType: { $type: "$items.product_id" },
      quantityType: { $type: "$items.quantity" },
      unitPriceType: { $type: "$items.unit_price" }
    }
  }
]);
```

With the sample data, the corresponding types are `string`, `int`, and `decimal`. If the array has multiple lines, `$unwind` emits one result per line; a document containing inconsistent elements will expose the discrepancy in the output.

## 4. Do Not Confuse Java Field Names with MongoDB Field Names

Spring Data maps Java properties to BSON via `MappingMongoConverter`. Before troubleshooting data issues, review the sources determining stored names:

| Java Declaration | Common BSON Field Name | Notes |
| --- | --- | --- |
| `@MongoId String id` | `_id` | MongoDB identifier; type depends on declaration and converter |
| `@Field("customer_id") String customerId` | `customer_id` | Name specified by annotation |
| `Instant placedAt`, without `@Field` | `placedAt` | By default convention when no custom naming strategy is set |
| `@Field("placed_at") Instant placedAt` | `placed_at` | Customized name |
| `List<OrderLine> items` | `items` | Array; nested elements are still mapped |
| `@Transient String temporaryValue` | Field is not stored | Transient in Spring Data mapping |
| `@Field(value="unit_price", targetType=DECIMAL128)` | `unit_price` as BSON decimal | Verify directly after writing |

In applications using a **field naming strategy**, custom converters, or other mappings, outcomes may differ from default rules. Therefore, rule tables are hypotheses to be verified against actual documents.

Common naming mistake example:

```javascript
// Wrong for a model with @Field("customer_id"):
db.orders.find({ customerId: "cust-01" });

// Right for the stored sample document:
db.orders.find({ customer_id: "cust-01" });
```

When using `MongoTemplate` to query by entity, Spring Data can map **Java property** names to BSON field names:

```java
Query query = Query.query(
    Criteria.where("customerId").is("cust-01")
);

List<OrderDocument> orders =
    mongoTemplate.find(query, OrderDocument.class);
```

The snippet above assumes `mongoTemplate` and imports for `Query`, `Criteria`, and `List` are available. When routed through `OrderDocument` mapping, `customerId` is translated to `customer_id`. With raw queries in `mongosh`, aggregation builders using raw BSON, or direct driver commands, understand which steps apply mapping; do not assume every API translates Java names automatically.

### Should the `_class` Field Appear?

By default, many Spring Data MongoDB configurations write `_class` as a type hint when persisting documents. This helps resolve types when mapping back, especially for polymorphic types. A manually created document in `mongosh` lacking `_class` does not mean the Spring Data application disabled it.

When checking:

```javascript
db.orders.find(
  { _id: "ord-1001" },
  { _id: 1, _class: 1, customer_id: 1 }
);
```

Projection will not return `_class` if it does not exist. Do not arbitrarily delete or add `_class` just to make documents "look tidy": this field's behavior is part of the mapping configuration and can affect reading different types and backward compatibility.

## 5. Cross-Checking Field Names and Data Types in Java, Not Only mongosh

### 5.1. Write via Repository, Then Read Raw via MongoDB Java Driver

This is the most important check to confirm **Java-to-BSON mapping**. The example below assumes `OrderRepository` extends `MongoRepository<OrderDocument, String>` and `MongoTemplate` is connected to a test database.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.bson.Document;
import org.bson.types.Decimal128;
import org.springframework.data.mongodb.core.MongoTemplate;

import static com.mongodb.client.model.Filters.eq;

OrderDocument order = new OrderDocument(
    "ord-2001",
    "cust-02",
    Instant.parse("2026-11-20T01:00:00Z"),
    new BigDecimal("1250000.50"),
    true,
    List.of(new OrderDocument.OrderLine(
        "sku-7", 2, new BigDecimal("625000.25")
    ))
);

orderRepository.insert(order);

// Obtain collection directly from the driver to see actual BSON names/types.
Document raw = mongoTemplate.getCollection("orders")
    .find(eq("_id", "ord-2001"))
    .first();

if (raw == null) {
    throw new IllegalStateException("Written document not found");
}

System.out.println(raw.toJson());
System.out.println(raw.keySet());
System.out.println(raw.get("total_amount").getClass().getName());

if (!(raw.get("total_amount") instanceof Decimal128)) {
    throw new IllegalStateException("total_amount is not Decimal128");
}
```

With the declared mapping, you should observe:

- `_id` as BSON string `"ord-2001"` and `customer_id` as BSON string `"cust-02"`.
- `placed_at` as BSON Date; when read by the Java Driver into a `Document`, the value is typically `java.util.Date`.
- `total_amount` as `org.bson.types.Decimal128`; the `BigDecimal` read back must remain exact per currency rules.
- `items` as a `List` whose elements are documents, with `unit_price` also as Decimal128.
- Neither `customerId` nor `totalAmount` present, unless another configuration/converter alters the output.

**Distinguishing the two read paths:** `mongoTemplate.findById("ord-2001", OrderDocument.class)` returns a **converted** Java object. That proves read mapping works, but does not by itself prove the exact BSON stored. `getCollection("orders")` returns the driver collection and bypasses Spring Data's entity conversion layer, making it suited for inspecting raw data. When calling `Document.toJson()`, remember formatting depends on `JsonWriterSettings`; checking raw Java value types remains valuable.

### 5.2. Verifying via Integration Tests

You can write real tests against a test MongoDB (for example, MongoDB in Testcontainers) to catch regressions when changing annotations, converters, or library versions.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.bson.Document;
import org.bson.types.Decimal128;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

import static com.mongodb.client.model.Filters.eq;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class OrderMappingIntegrationTest {
    @Autowired MongoTemplate mongoTemplate;
    @Autowired OrderRepository orderRepository;

    @Test
    void writesExpectedFieldNamesAndBsonTypes() {
        String id = "mapping-check-001";
        OrderDocument input = new OrderDocument(
            id, "cust-02",
            Instant.parse("2026-11-20T01:00:00Z"),
            new BigDecimal("1250000.50"),
            true,
            List.of(new OrderDocument.OrderLine(
                "sku-7", 2, new BigDecimal("625000.25")
            ))
        );
        orderRepository.insert(input);

        Document raw = mongoTemplate.getCollection("orders")
            .find(eq("_id", id))
            .first();

        assertThat(raw).isNotNull();
        assertThat(raw.get("_id")).isEqualTo(id);
        assertThat(raw).containsKey("customer_id")
                       .doesNotContainKey("customerId");
        assertThat(raw.get("placed_at")).isInstanceOf(java.util.Date.class);
        assertThat(raw.get("total_amount")).isInstanceOf(Decimal128.class);

        List<?> items = raw.getList("items", Document.class);
        Document first = (Document) items.get(0);

        assertThat(first.get("product_id")).isEqualTo("sku-7");
        assertThat(first.get("quantity")).isInstanceOf(Integer.class);
        assertThat(first.get("unit_price")).isInstanceOf(Decimal128.class);

        OrderDocument roundTrip = orderRepository.findById(id)
            .orElseThrow();
        assertThat(roundTrip.totalAmount())
            .isEqualByComparingTo("1250000.50");
    }
}
```

The example assumes a clean test database or unique ID, an actual MongoDB connected to Spring Boot, and proper repository configuration. If Testcontainers is used, configure the MongoDB container and Spring Boot connection separately; environment setup is omitted above. This lesson provides a **test template**, not a claim that the test was executed.

Benefit of testing: it distinguishes two different situations:

- **Wrong write, seemingly "right" read:** a custom converter might gracefully parse an old type, making the read entity look normal even though BSON violates the new storage standard.
- **Right write, wrong read:** constructor mapping, enum converters, or property names can yield null or wrong types on the object even when BSON is right.

## 6. Most Commonly Confused BSON Types

### 6.1. String vs. ObjectId for `_id`

In MongoDB, `_id` can have many BSON types; not every `_id` is an ObjectId. `@Id String id` and `@MongoId(FieldType.STRING)` express different mapping intents.

If you only check `findById` on a repository, the converter can mask the difference. For raw documents, try:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: { $type: "$_id" },
      count: { $sum: 1 }
    }
  }
]);
```

A collection having both `string` and `objectId` in `_id` usually signals data ingested from multiple sources or application versions. Migrations must examine references, query paths, and uniqueness before changing ID types.

### 6.2. Decimal128, double, int, long, and Numeric Strings

The value **1,250,000.50** can be stored under several BSON types:

```javascript
db.mapping_type_samples.insertMany([
  { _id: "decimal", amount: NumberDecimal("1250000.50") },
  { _id: "double",  amount: 1250000.50 },
  { _id: "string",  amount: "1250000.50" },
  { _id: "long",    amount: NumberLong("1250000") }
]);

db.mapping_type_samples.aggregate([
  {
    $project: {
      _id: 1,
      amountType: { $type: "$amount" }
    }
  }
]);
```

The values above are **not equivalent** in type, precision, or arithmetic behavior. For money, use `BigDecimal` in Java mapped to Decimal128, or store minor units as integers per business rules. If a value exceeds Decimal128 range, conversion can fail; do not assume every `BigDecimal` can be saved.

Filters to locate non-conforming documents:

```javascript
db.orders.find({ total_amount: { $type: "string" } });
db.orders.find({ total_amount: { $type: "double" } });
db.orders.find({ total_amount: { $type: "decimal" } });
```

Inspect schemas, invalid data, and reporting figures before bulk-converting types; do not blindly run an update script across every string.

### 6.3. BSON Date vs. Timestamp Strings

`ISODate("2026-11-20T01:00:00Z")` writes a BSON Date, whereas `"2026-11-20T01:00:00Z"` writes a String. Java `Instant` typically maps to BSON Date under standard conversion configuration; verify whenever custom converters or codecs are present.

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: { $type: "$placed_at" },
      count: { $sum: 1 }
    }
  }
]);
```

BSON Date stores a UTC timestamp at millisecond resolution. For `Instant` values with sub-millisecond nanoseconds, write/read round-trips may truncate precision below milliseconds. Types such as `LocalDateTime` carry no time zone and depend further on configured conversions; define time zones and representations explicitly. Do not confuse BSON's internal `timestamp` type with BSON `date` used for business timestamps.

### 6.4. Boolean, null, and Missing Fields

A field has three important states:

```javascript
// Field exists and equals true:
db.orders.find({ is_paid: true });

// Field exists and BSON type is null:
db.orders.find({ is_paid: { $type: "null" } });

// Field is_paid is absent:
db.orders.find({ is_paid: { $exists: false } });
```

The condition `{ is_paid: null }` in MongoDB typically matches both documents with a null value **and** documents missing the field. Thus do not use it when you need to distinguish those two cases.

If the Java field is primitive `boolean`, its default `false` can erase the distinction between "no data yet" and "confirmed false". Use `Boolean`, validation, default values, and migrations according to business meaning; wrapper types are not mandatory for every boolean.

### 6.5. Arrays, Nested Objects, UUIDs, and Enums

- For `List`, BSON data is `array`; elements can be documents, scalars, or null. Check with `$unwind`, or inspect the first element if data is uniform enough.
- For nested Java objects, BSON is normally `object`/subdocument; inner fields can be affected by `@Field` and converters.
- UUIDs usually have a BSON Binary representation with a subtype and UUID representation policy; data from older clients/drivers may differ from newer representations. Inspect **both binary type and subtype**, not only the UUID string printed after reading.
- Enums are normally written as string names by standard converters, though custom converters can use other values. Renaming enum constants can break reading legacy data without a compatibility strategy.

## 7. Scanning the Entire Collection: Detecting Different Data Generations

Inspecting a single document is the first step. If data was created by multiple application versions, the same field may carry multiple types or names.

### 7.1. Type Statistics per Field

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        customerIdType: { $type: "$customer_id" },
        totalType: { $type: "$total_amount" },
        placedAtType: { $type: "$placed_at" }
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

The output reveals documents where `total_amount` is `decimal`, `string`, or `missing`. This method scans data to compute counts and can be resource-intensive on large collections; run it in permitted environments, limit data, or schedule inspections carefully.

### 7.2. Finding Misnamed Fields or Missing New Names

```javascript
// Data still using the old camelCase name:
db.orders.find(
  { totalAmount: { $exists: true } },
  { _id: 1, totalAmount: 1, total_amount: 1 }
);

// Data lacking the new name:
db.orders.find(
  { total_amount: { $exists: false } },
  { _id: 1, total_amount: 1 }
);

// Data containing both names at the same time:
db.orders.find({
  totalAmount: { $exists: true },
  total_amount: { $exists: true }
});
```

Distinguish clearly:

- Missing field due to an **older schema generation** not yet migrated.
- Missing field due to **write rules skipping nulls** or `@Transient` fields.
- Missing field due to **wrong query name**, wrong collection, or manually entered data.
- Two fields with the same meaning under different names, resulting in one side updating while the other stays stale.

When heterogeneous data exists, the application needs conversion rules for old data, schema versioning, or a verified migration. Never rename fields in bulk based on inspecting just one sample document.

### 7.3. Checking Line-Item Structure

For documents with an `items` array, gather type statistics on each item:

```javascript
db.orders.aggregate([
  { $unwind: "$items" },
  {
    $group: {
      _id: {
        productIdType: { $type: "$items.product_id" },
        quantityType: { $type: "$items.quantity" },
        unitPriceType: { $type: "$items.unit_price" }
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

If `items` is missing, null, or an empty array, `$unwind` by default emits no rows; therefore results only reflect **unwound elements**. To audit missing/empty arrays as well, check separately with `$type` and `$size` (with an array-type guard where needed).

## 8. When to Use Repository, MongoTemplate, and Raw Driver?

| Tool | Best Suited For | Key Reminder |
| --- | --- | --- |
| `MongoRepository`/`CrudRepository` | Saving/reading entities in the Java model, testing round trips | Results have already passed through the converter |
| `MongoTemplate.find(...)` | Querying entities with Java property and type mapping | Still goes through the converter when returning entities |
| `MongoTemplate.getCollection("orders")` | Accessing `MongoCollection<Document>` directly | Reveals raw structure; does not auto-map per Java entity |
| `mongosh findOne`, `EJSON` | Inspecting actual BSON names/types with an independent tool | Must use the right DB, collection, ID, and permissions |
| `mongosh aggregate` with `$type` | Counting/detecting non-conforming types across many records | Can scan data and incur cost |
| Integration tests with raw BSON | Automatically catching mapping regressions | Needs test MongoDB, isolated data, and clear assertions |

An easily confused example:

```java
// Query by Java property, routed through OrderDocument mapping:
Query mapped = Query.query(Criteria.where("customerId").is("cust-02"));
mongoTemplate.find(mapped, OrderDocument.class);

// Raw driver query: must use actual BSON name:
mongoTemplate.getCollection("orders")
    .find(com.mongodb.client.model.Filters.eq("customer_id", "cust-02"));
```

When debugging, note exactly which API builds the query; do not compare `Criteria.where("customerId")` in `MongoTemplate` with `db.orders.find({customerId: ...})` in `mongosh` as if both ran through the same translation layer.

## 9. Diagnosing Common Mapping Errors

| Symptom | Causes Worth Checking | How to Verify |
| --- | --- | --- |
| Repository reads the entity, yet `mongosh` lacks a matching Java-named field | `@Field` or naming strategy renamed it | Check BSON fields via `findOne` and `$type` |
| `findById` misses expected record | BSON string/ObjectId mismatch, wrong DB/collection/ID | `findOne` per type and `$type: "$_id"` |
| Total amount reads as null or wrong number | Missing/renamed field; string/double/decimal mapping mismatch | Canonical EJSON, `$type`, raw `Decimal128` |
| Time shifted or losing sub-second precision | Stored as string instead of Date; timezone/converter; precision limits | `$type`, EJSON, `Instant` round-trip check |
| `_class` appears unexpectedly | Default type mapper or polymorphic types | Read actual BSON and application converter config |
| Old documents fail while new documents succeed | Heterogeneous data from multiple schema versions | Aggregation grouping `$type` and checking missing fields |
| Array operations yield strange results | Elements missing fields or having mismatched types | `$unwind` and `$type` on nested fields |
| Slow queries despite right mapping | Missing index, filtering wrong field name, unmatched sort | Inspect `getIndexes()` and `explain("executionStats")` |
| Reactive repository behaves differently from imperative one | Different converter/config/client; non-equivalent tests | Write through each path, read raw BSON, compare |

### Confirming Indexes and Query Plans After Checking Names

Indexes in MongoDB bind to **BSON field names**:

```javascript
db.orders.getIndexes();

db.orders.createIndex({
  customer_id: 1,
  placed_at: -1
});

db.orders.find({ customer_id: "cust-02" })
         .sort({ placed_at: -1 })
         .limit(20)
         .explain("executionStats");
```

The `createIndex` command is purely illustrative on a test database. An index mistakenly declared on `customerId` instead of `customer_id` can exist validly yet fail to serve the intended query. When using annotations like `@Indexed` or `@CompoundIndex`, confirm the index actually exists; Spring Data does not guarantee automatic index creation across all settings and versions.

## 10. Data Types Also Affect Aggregations and Transactions

An aggregation pipeline can produce wrong results if monetary fields are strings in some documents or timestamps are strings in others. Example summarizing types before summing amounts:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: { $type: "$total_amount" },
      documents: { $sum: 1 }
    }
  }
]);
```

When moving on to revenue totals, use proper BSON numeric types, status filters, currencies, and refund rules. Do not ignore mistyped documents just because a pipeline finishes without error: many operators/expressions handle non-numeric values with specific semantics.

A MongoDB **single-document** write is atomic, yet that **does not confirm** field names/types are right, nor does it ensure data across other documents updates together. When business rules require multi-document transactions, Spring Data MongoDB supports `MongoTransactionManager` in an appropriate MongoDB deployment. With Reactive MongoDB, use `ReactiveMongoTemplate`/`ReactiveMongoRepository` and `ReactiveMongoTransactionManager` when reactive transactions are needed.

Whether using the imperative or reactive API, the mapping verification flow is identical: **write via the real application path → read raw BSON → compare round-trip data → verify actual indexes and queries**. Reactive access supports an asynchronous execution model; it does not automatically fix data-type mismatches or speed up queries.

## 11. What to Do When Inconsistent Types or Names Are Found?

Before migrating, measure the scope and identify authoritative source data. A technically safe workflow:

1. **Categorize:** identify existing BSON types (`string`, `decimal`, `double`, `missing`, `null`, etc.) and old/new field names.
2. **Define the standard contract:** names, BSON types, required fields, ID/money/date representations, and schema version.
3. **Choose transformation rules:** for instance, convert only valid numeric strings matching an accepted format; do not auto-convert ambiguous strings, missing values, or domain-invalid records.
4. **Ensure rollout compatibility:** if old and new code run concurrently, establish a period able to read both formats or coordinate release/migration ordering.
5. **Test on copied data in a staging environment**, with before-and-after counts and an appropriate rollback/recovery plan.
6. **Re-inspect actual BSON** and round-trips after migration, then monitor slow queries, conversion errors, and business outputs.

Consider a collection validator with `$jsonSchema` to prevent future bad-type writes:

```javascript
// Illustrative validator structure; account for legacy data before applying:
{
  $jsonSchema: {
    bsonType: "object",
    required: ["customer_id", "placed_at", "total_amount"],
    properties: {
      customer_id: { bsonType: "string" },
      placed_at: { bsonType: "date" },
      total_amount: { bsonType: "decimal" },
      items: { bsonType: "array" }
    }
  }
}
```

This is a **configuration fragment**, not a directly runnable command. Validators enforce schema at the MongoDB layer, but do not replace Bean Validation, business logic, or migrating existing data. Validation strictness, legacy document handling, and update ordering must be planned upfront.

## 12. Self-Check Practice Exercise

Create a dedicated database/collection, then perform step by step:

1. Create `OrderDocument` with the annotations in section 2 and a corresponding repository.
2. Insert an order via the repository. Read it back via the repository and record the returned values.
3. Use `mongosh` or the raw driver to read that exact `_id`. List the actual BSON names and try `EJSON.stringify(..., {relaxed:false})`.
4. Use `$type` to inspect `_id`, `customer_id`, `placed_at`, `total_amount`, `is_paid`, `items`, and `items.unit_price`.
5. Try inserting a new document where `total_amount` is a string using `mongosh`; run an aggregation counting grouped types. Observe how one collection can contain heterogeneous data.
6. Try searching by `customerId` in `mongosh` and by `customerId` via `MongoTemplate` using the entity; explain the difference in name mapping.
7. Write an integration test verifying BSON Date, Decimal128, string `_id`, and `BigDecimal` round-trip.
8. Inspect `getIndexes()`, then evaluate a filter/sort query with `explain("executionStats")`; cross-check indexed field names against actual BSON names.

**Outcomes you should be able to explain:** why a Java class alone is insufficient to conclude what is stored; which fields were renamed; the BSON types of ID, timestamps, and money; which fields are missing or null; and why you must check **both writes and reads**.

## 13. Checklist Before Finalizing a Mapping Change

| Question | How to Verify |
| --- | --- |
| Which BSON name does the Java property map to? | Check annotations/config; inspect raw document |
| Does `id` store BSON string or ObjectId? | `$type` on `_id` and raw driver |
| Is money stored as decimal, int/long, double, or string? | Canonical EJSON, `$type`, raw `Decimal128` |
| Are timestamps stored as Date or string? | `$type` on time fields; round-trip check |
| Is a field missing, null, or defaulted? | `$exists`, `$type:"null"`, test edge cases |
| Do arrays and subdocuments match expected structure? | `$unwind`, `$type` on nested fields |
| Do legacy documents share the same format? | Aggregation grouped by type, searching for old/missing fields |
| Does the converter differ from actual BSON? | Write via repository/template, then read raw collection |
| Do indexes use the right BSON names? | `getIndexes()` and `explain("executionStats")` |
| Are there regression tests after schema changes? | Integration test checking write/read-back names + BSON types |

Reliable mapping is more than a Java class that compiles or a repository that returns objects. With **Spring Data MongoDB**, inspect **actual BSON documents**, verify field names, data types, and nested structures, and test two-way conversions. Once backed by clear evidence, query design, aggregations, indexes, transactions, reactive access, and performance diagnostics rest on the system's true data structure.
