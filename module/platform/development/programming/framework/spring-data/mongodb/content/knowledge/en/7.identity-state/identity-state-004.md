# `@MongoId` for Controlling Identifier Types

In MongoDB, every document has an `_id` field used to uniquely identify it **within a collection**. With **Spring Data MongoDB**, a Java property such as `id` is typically mapped to `_id`. However, **the type declared in Java does not necessarily match the actual BSON type stored in MongoDB Server**. For instance, a 24-character hex string can be stored as a BSON `String` or a BSON `ObjectId`; those two values look identical when printed, yet **they are not the same value when matching**.

The `@MongoId` annotation gives you control over how Spring Data MongoDB represents identifier values during reads and writes. This lesson belongs to the **Identity and State** chapter of the `SPRING_DATA_MONGODB` module. We will explore the difference between `@MongoId` and `@Id`, choosing identifiers based on business requirements, querying via repositories or `MongoTemplate`, spotting mismatched-type data, testing against real MongoDB, and considerations when changing stored `_id` types.

After this lesson, you will be able to:

- Explain the roles of `_id`, `ObjectId`, `String`, and ID mapping rules in Spring Data MongoDB.
- Distinguish `@Id`, default `@MongoId`, and `@MongoId(FieldType.OBJECT_ID)`.
- Design entities with **verbatim string IDs** or **BSON ObjectId storage** under an explicit convention.
- Inspect actual BSON types using `mongosh` and the driver, avoiding "same text, different type" bugs.
- Know when to keep IDs stable, handle references, indexes, updates, testing, and data migrations.

## 1. What Is `_id` and Why Does the BSON Type Matter?

Within a collection, MongoDB uses `_id` as the document identifier key. If an insert operation omits `_id`, the driver or MongoDB can generate an `ObjectId` value. Nevertheless, MongoDB **does not force every document to use an `ObjectId` `_id`**: applications can use strings, numbers, or many other supported BSON types, as long as `_id` constraints are satisfied.

MongoDB automatically maintains a **unique index** on `_id` in standard collections. No two documents in the same collection may share the same `_id` value. Because the data type is part of comparison, the following two IDs are **different**:

```javascript
// Document A: _id is a BSON String
{
  _id: "507f1f77bcf86cd799439011",
  name: "Customer A"
}

// Document B: _id is a BSON ObjectId
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  name: "Customer B"
}
```

In `mongosh`, the two queries below search for **two different BSON types**:

```javascript
db.customers.findOne({ _id: "507f1f77bcf86cd799439011" });
db.customers.findOne({ _id: ObjectId("507f1f77bcf86cd799439011") });
```

An `ObjectId` is commonly displayed as **24 hex characters**, representing 12 bytes of data. A 24-character hex string is a **representation** that can be parsed into an ObjectId, but a Java string itself does not automatically become a BSON ObjectId; whether conversion happens depends on the mapping/codec in use.

> **Key takeaway:** when investigating an ID lookup failure, check both the **value** and the **BSON type** of `_id`. Simply logging `id.toString()` or comparing hex strings can hide the issue.

## 2. How Do `@Id` and `@MongoId` Differ?

Spring Data MongoDB recognizes identifier properties in several ways:

1. `@Id` from `org.springframework.data.annotation.Id` marks the ID property and applies Spring Data MongoDB's default ID conversion rules.
2. `@MongoId` from `org.springframework.data.mongodb.core.mapping.MongoId` also identifies the ID property, but lets you specify the **target BSON type** via `FieldType`.
3. A property named `id` or `_id` can be mapped by convention when no annotation is present; when explicit type control is required, declare the appropriate annotation.

Three common patterns:

| Java Declaration | Value is a valid 24-char hex string | BSON `_id` type typically written |
| --- | --- | --- |
| `@Id String id` | Spring Data applies default conversion; convertible strings become `ObjectId` | `ObjectId` |
| `@MongoId String id` | Uses implicit type (`FieldType.IMPLICIT`), does not coerce hex strings to `ObjectId` | `String` |
| `@MongoId(FieldType.OBJECT_ID) String id` | Requests converting the ID to ObjectId form when possible | `ObjectId` |
| `@MongoId ObjectId id` | The Java property itself is already `ObjectId` | `ObjectId` |

The rules above describe **Spring Data MongoDB with its default mapping converter**. Custom converters or framework changes can alter behavior; for a specific project, verify with integration tests and inspect the actual stored BSON data. Never guess the `_id` type solely from a `String` declaration.

### 2.1. `@Id`: Default Conversion

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "legacyCustomers")
public record LegacyCustomer(
        @Id String id,
        String name
) {}
```

If you save a `LegacyCustomer` with `id` equal to `"507f1f77bcf86cd799439011"`, Spring Data typically converts this value into a BSON `ObjectId` on write. For a string that is **not valid ObjectId format**, the mapper can keep it as a String.

This easily leads to a collection with **mixed `_id` types** if the application accepts both free-form IDs and IDs that look like ObjectIds. Therefore, when intentionally using **business string codes**, default `@MongoId` is a clearer choice.

### 2.2. `@MongoId`: Preserving String IDs as Declared

```java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "customers")
public record Customer(
        @MongoId String id,
        String name,
        int loyaltyLevel
) {}
```

When saving a `Customer` with ID `"CUS-1001"` or `"507f1f77bcf86cd799439011"`, the target BSON type remains **String**. This is the right fit when IDs originate from an external system, follow custom business code rules, or must always be persisted verbatim as strings.

In metadata terms, `@MongoId` defaults to `FieldType.IMPLICIT`: it preserves representation according to the Java type and default converter, **without applying `@Id`'s rule of converting 24-hex strings to ObjectId**.

### 2.3. `@MongoId(FieldType.OBJECT_ID)`: Requesting BSON ObjectId

```java
import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "auditEvents")
public record AuditEvent(
        @MongoId(FieldType.OBJECT_ID) String id,
        String action,
        Instant occurredAt
) {}
```

When `id` equals `"507f1f77bcf86cd799439011"`, Spring Data can convert it to BSON `ObjectId("507f1f77bcf86cd799439011")` before writing. Java code continues operating on a `String` field, while the value stored on the server is `ObjectId`.

**Do not treat `FieldType.OBJECT_ID` as an input validation tool.** For a string that cannot be converted into an ObjectId, default conversion rules may fall back to storing it as a String instead of guaranteed failure in every situation. Therefore, if the goal is a collection containing strictly ObjectId `_id` values, **validate the input format** or use a Java `ObjectId` property directly.

## 3. Choosing an ID Type From Business Requirements

Pick the ID type **before real data exists** and document it as a convention per collection:

| Requirement | Recommendation | Reason |
| --- | --- | --- |
| Internal documents with no pre-existing business ID | `ObjectId` or controlled ObjectId-backed strings | Natural compatibility with the MongoDB ecosystem |
| Customer or order codes supplied by an external system | `@MongoId String id` | Keeps string IDs verbatim, including those that happen to look like ObjectId |
| External API accepts/returns hex IDs while server stores ObjectId | `@MongoId(FieldType.OBJECT_ID) String id` | Java/API uses String, MongoDB uses ObjectId for valid IDs |
| Strict enforcement of BSON ObjectId | `@MongoId ObjectId id` with conversion at the API boundary | Java type enforces the requirement; rejects arbitrary Strings |
| Mutable SKUs, emails, or names | Usually keep in a separate field, indexed if needed | `_id` is a stable identifier and cannot be updated in place |

Note: `ObjectId` is neither an access permission nor a secret. Do not rely on unpredictable IDs as a substitute for **authentication/authorization** checks. In multi-tenant systems, ID lookups typically require tenant predicates or authorization checks.

## 4. End-to-End Example: String IDs for Customers

Suppose we want the `customers` collection to store string IDs verbatim, even when a partner system sends IDs resembling ObjectIds. We use the `Customer` entity with `@MongoId String id` from Section 2.2.

Repository:

```java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerRepository
        extends MongoRepository<Customer, String> {

    List<Customer> findByLoyaltyLevelGreaterThanEqual(int level);
}
```

Service for saving and reading:

```java
import org.springframework.stereotype.Service;

@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer createSample() {
        return repository.save(
                new Customer("507f1f77bcf86cd799439011", "Lan", 2)
        );
    }

    public Customer find(String id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Customer not found"));
    }
}
```

MongoDB will hold a document like:

```javascript
{
  _id: "507f1f77bcf86cd799439011", // BSON String
  name: "Lan",
  loyaltyLevel: 2
}
```

The following operations in `mongosh` clearly distinguish how it is stored:

```javascript
db.customers.findOne({ _id: "507f1f77bcf86cd799439011" });
// Finds the document saved with @MongoId String.

db.customers.findOne({
  _id: ObjectId("507f1f77bcf86cd799439011")
});
// Does not find the same document if _id is a BSON String.
```

`MongoRepository<Customer, String>` declares the **ID type of the Java model**. It does not force `_id` in the database to be a BSON String for every entity; the mapping annotations determine the conversion rules. Nor does the repository create another unique index, since MongoDB already provides a unique index on `_id`.

### 4.1. Dynamic Queries With `MongoTemplate`

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class CustomerLookup {
    private final MongoTemplate mongoTemplate;

    public CustomerLookup(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public Customer findById(String customerId) {
        Query query = Query.query(Criteria.where("id").is(customerId));
        return mongoTemplate.findOne(query, Customer.class);
    }
}
```

Given `Customer.class`, `MongoTemplate` knows the entity's mapping metadata. `Criteria.where("id")` is mapped to `_id`; the `@MongoId` rule ensures the parameter value is represented with the chosen BSON type.

**Distinction:** when using the Java Driver directly (such as `MongoCollection<Document>`), Spring Data **does not participate in query conversion**. Driver code must supply the exact BSON type itself:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;

// 'collection' is a MongoCollection<Document> obtained from MongoDatabase.
Document found = collection.find(
        Filters.eq("_id", "507f1f77bcf86cd799439011")
).first();
```

If the actual stored data is a BSON ObjectId, the driver requires `new ObjectId("507f1f77bcf86cd799439011")` as the filter value. This difference between Spring Data queries and Java Driver queries is why you must inspect the actual BSON format when debugging.

## 5. Example: Java String ID Stored as BSON ObjectId

In an events collection, the application wants to store `_id` as ObjectId while still passing/reading hex strings in the service layer. Using `AuditEvent` from Section 2.3:

```java
import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.stereotype.Service;
import org.springframework.data.mongodb.core.MongoTemplate;

@Service
public class AuditEventService {
    private final MongoTemplate mongoTemplate;

    public AuditEventService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public AuditEvent append(String hexId, String action) {
        if (hexId == null || !ObjectId.isValid(hexId)) {
            throw new IllegalArgumentException("ID must be 24 hex characters");
        }
        return mongoTemplate.insert(
                new AuditEvent(hexId, action, Instant.now())
        );
    }
}
```

The `ObjectId.isValid` guard rejects malformed input before calling Spring Data. When IDs are created by the application, you can also call `new ObjectId().toHexString()` to generate a new identifier and pass it to the method.

Once stored, queries in `mongosh` use **ObjectId**, not a string:

```javascript
db.auditEvents.findOne({
  _id: ObjectId("507f1f77bcf86cd799439011")
});

db.auditEvents.aggregate([
  { $match: { _id: ObjectId("507f1f77bcf86cd799439011") } },
  { $project: { action: 1, bsonIdType: { $type: "$_id" } } }
]);
// Expected bsonIdType: "objectId"
```

The Java code in this example uses `String` as the ID at the application interface, while BSON stores `ObjectId` thanks to `@MongoId(FieldType.OBJECT_ID)`. If stronger typing is desired, you can design the entity with `@MongoId ObjectId id` and convert ObjectId ↔ string only at the Controller/DTO boundary.

## 6. Impact on Insert, Save, Upsert, and Updates

### 6.1. Insert and Missing IDs

With `insert`, the application can supply an ID upfront or let the driver/server and mapping framework generate one when supported by the ID field. **`@MongoId` primarily controls ID type mapping; it is not a sequence-generation annotation and does not define business ID generation rules.**

In cases where you must be certain of the ID type, proactively supply a valid ID value before inserting. For business string IDs, establish a clear ID generation policy; for `ObjectId`, either generate it in the application or use the appropriate default mechanism, then verify the type/value.

### 6.2. `save` and `upsert` Depend on the Existing ID

`MongoRepository.save` or `MongoTemplate.save` can insert a new document or update an existing one depending on entity state and identity. When an existing document has a String `_id` while updated mapping sends an ObjectId `_id` filter, update queries may **fail to match the old document**.

A dangerous scenario:

1. The legacy database holds `_id: "507f1f77bcf86cd799439011"` (**String**).
2. Code changes from `@MongoId String id` to `@MongoId(FieldType.OBJECT_ID) String id`.
3. Requests loading/saving that ID under the new mapping query `_id` as **ObjectId**, failing to find the old String document.
4. If the operation has create/upsert semantics, the system risks inserting an extra document with a BSON ObjectId despite the identical hex text.

Therefore, **changing annotations is not data migration**. Verify actual generated queries and stored state before deploying.

### 6.3. Do Not Change `_id` Directly via Update

MongoDB does not permit updating the `_id` value of an existing document with a normal update. Changing a representation from String to ObjectId requires a **controlled migration process** (creating a new document with the target ID, updating related references, verifying, and then handling the old document), avoiding ad-hoc `$set` updates on `_id`.

`@Version` (optimistic locking) and `@MongoId` solve different problems: `@Version` tracks version state on writes, while `@MongoId` controls identifier type mapping. Do not use `@Version` to fix `_id` type mismatch queries.

## 7. Inspecting Stored BSON Types and ID Lookup Errors

### 7.1. Inspecting With `mongosh`

Assuming you are logged into a **test database** with the `customers` collection:

```javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      name: 1,
      bsonIdType: { $type: "$_id" }
    }
  },
  { $limit: 20 }
]);
```

The `bsonIdType` field will show values like `"string"` or `"objectId"`. You can aggregate across the whole collection to detect mixed-type data:

```javascript
db.customers.aggregate([
  { $group: { _id: { $type: "$_id" }, total: { $sum: 1 } } },
  { $sort: { total: -1 } }
]);
```

If both `string` and `objectId` appear, trace the cause to mapping rules, import/migration history, or writes made by the Java Driver and Spring Data under differing conventions. Do not perform bulk conversions before knowing which type other collections reference.

### 7.2. Inspecting With the Java Driver

Inspecting raw data directly in a test environment confirms that mapping behaves as intended:

```java
import static com.mongodb.client.model.Filters.eq;

import org.bson.Document;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;

// 'mongoTemplate' is injected in a test or diagnostic service.
Document rawStringId = mongoTemplate.getCollection("customers")
        .find(eq("_id", "507f1f77bcf86cd799439011"))
        .first();

Document rawObjectId = mongoTemplate.getCollection("auditEvents")
        .find(eq("_id", new ObjectId("507f1f77bcf86cd799439011")))
        .first();

if (rawStringId != null) {
    System.out.println(rawStringId.get("_id") instanceof String);
}
if (rawObjectId != null) {
    System.out.println(rawObjectId.get("_id") instanceof ObjectId);
}
```

This snippet only checks the ID data type; avoid logging full documents containing sensitive fields in production logs. The Java Driver works directly with BSON, separating storage details from Spring Data's mapping layer.

### 7.3. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `findById` misses a document that exists in `mongosh` | Query uses ObjectId while actual `_id` is String, or vice versa | Inspect BSON type with `$type`, compare against annotations/converters; fix mapping or migrate cleanly |
| Only 24-hex IDs fail to query | `@Id String` converts them to ObjectId while other strings stay String | Adopt a consistent convention; consider `@MongoId String` if business IDs must stay verbatim |
| Two documents show identical IDs when exported as text | One String document and one ObjectId document | Check types rather than display strings; plan consolidation/migration if needed |
| Invalid ID saves without error | `FieldType.OBJECT_ID` is not a strict validator for all inputs | Validate format at the boundary, or use `ObjectId` directly as the Java type |
| `save` creates another document instead of updating | ID mapped to a different BSON type than legacy data | Inspect write queries, actual stored IDs, unique constraints, and annotation history |
| Reference from order to customer fails to match | `customerId` and `customers._id` have different types | Align both sides and converters/lookups; test against real documents |
| Same ID appears across different collections | `_id` is only unique per collection | Never assume database-wide uniqueness; specify namespace/collection |

## 8. IDs, References, Indexes, and Aggregations

### 8.1. Logical References Must Share the Same Type

Suppose `orders.customerId` stores the string `"507f1f77bcf86cd799439011"` while `customers._id` is a BSON ObjectId. A `$lookup` joining these two fields **does not automatically convert strings to ObjectId**:

```javascript
db.orders.aggregate([
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  }
]);
```

The `customer` array may come back empty even though the hex strings look identical. The durable fix is **designing matching BSON types for linked keys** or converting explicitly; `@DocumentReference`/`@DBRef` also do not eliminate the need for consistent types and reference rules.

### 8.2. An Index on `_id` Does Not Solve Every Query

MongoDB provides an index for `_id` out of the box; you do not need to add an extra `{ _id: 1 }` index just because you use `@MongoId`. However, queries filtering on `email`, `customerId`, `createdAt`, or aggregations still require separate index evaluation.

```javascript
db.orders.createIndex({ customerId: 1, createdAt: -1 });

db.orders.find({ customerId: "CUS-1001" })
  .sort({ createdAt: -1 })
  .limit(20);
```

A compound index can support both filtering by `customerId` and sorting by `createdAt`. When queries are slow, run `explain("executionStats")` on representative data; do not blame performance solely on choosing String versus ObjectId.

### 8.3. Transactions Do Not Fix Mismatched ID Types

When modifying multiple documents, Spring Data MongoDB can coordinate transactions on supported MongoDB deployments. However, a transaction does not turn `"507..."` into `ObjectId("507...")`, fix mismatched-type references, or make `_id` mutable. Mapping rules must still be right before designing atomic workflows.

With reactive access, `ReactiveMongoRepository` or `ReactiveMongoTemplate` still uses Spring Data's ID metadata and executes operations via the Reactive Streams Driver. Reactive changes to a non-blocking I/O model, but does not alter BSON type comparison rules.

## 9. Migrating When the Wrong `_id` Type Was Chosen

Suppose a historical collection stored `_id` as BSON String, while a new application version wants BSON ObjectId. A safe approach must be **designed before running on real data**:

1. **Audit:** measure actual BSON types, document counts, percentage of convertible IDs, representation duplicates, and collections referencing the ID.
2. **Define the target standard:** decide which collections store String and which store ObjectId; do not base this solely on JSON formatting.
3. **Build a tested migration job:** transform each document using deterministic mapping; handle non-ObjectId strings, unique errors, and references.
4. **Update links:** fields like `orders.customerId`, caches, events, and APIs must be reviewed; when IDs change, related references must match the same type.
5. **Choose a rollout strategy:** you may use a new collection and compatibility reads/writes during the transition; avoid silent in-request conversions without observability.
6. **Verify and deploy:** reconcile record counts, foreign keys, queries, indexes, missing-record rates, and rollback plans before shifting full traffic.

**Do not use normal updates to change `_id` in place.** MongoDB treats `_id` as immutable. Copying/migrating can impact unique constraints and transactions; run in a test environment first, log old → new ID mappings, and remove legacy documents only after verification.

If the system already uses a stable string ID convention, **keeping String with `@MongoId`** is often much less risky than converting everything to ObjectId. Base the decision on integration requirements and existing data.

## 10. Testing Mapping Against a Real MongoDB Instance

To confirm `@MongoId` behaves properly, write isolated integration tests against a real MongoDB instance, such as `@DataMongoTest` paired with Testcontainers in an appropriate environment. Unit tests that only mock repositories cannot prove `_id` was encoded as the expected BSON type.

A minimal test matrix:

| Test Case | Input Data | Expectation |
| --- | --- | --- |
| Verbatim string | `Customer` with ID `"CUS-1001"` | BSON String `_id`; string lookup succeeds |
| ObjectId-like string | `Customer` with ID `"507f1f77bcf86cd799439011"` | Still stored as BSON String with default `@MongoId` |
| Explicit ObjectId requested | `AuditEvent` with `@MongoId(FieldType.OBJECT_ID)` and 24-hex ID | BSON ObjectId `_id`; ObjectId lookup succeeds |
| Invalid ID | Empty string, non-hex chars, or wrong length | Service validation rejects before insert |
| Cross-type query | Search for a String document using BSON ObjectId | Does not match the String document |
| Legacy mixed-type data | Read documents before/after mapping change | Discrepancy detected instead of silently mis-updating |

Example assertions in a test configured with `MongoTemplate` and a clean database:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static com.mongodb.client.model.Filters.eq;

import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
class MongoIdMappingTest {

    @Autowired MongoTemplate template;

    @Test
    void stringIdKeepsBsonString() {
        String id = "507f1f77bcf86cd799439011";
        template.insert(new Customer(id, "Lan", 2));

        Document raw = template.getCollection("customers")
                .find(eq("_id", id))
                .first();

        assertThat(raw).isNotNull();
        assertThat(raw.get("_id")).isInstanceOf(String.class);
    }

    @Test
    void requestedObjectIdUsesBsonObjectId() {
        String id = "507f1f77bcf86cd799439012";
        template.insert(new AuditEvent(id, "LOGIN", java.time.Instant.now()));

        Document raw = template.getCollection("auditEvents")
                .find(eq("_id", new ObjectId(id)))
                .first();

        assertThat(raw).isNotNull();
        assertThat(raw.get("_id")).isInstanceOf(ObjectId.class);
    }
}
```

The `Customer` and `AuditEvent` entities were defined in earlier examples and must be accessible/registered for mapping in the test context. `@DataMongoTest` provides the test slice, but **requires a configured connection to a real test MongoDB instance**; the annotation alone does not spin up a MongoDB Server in every project. Never point tests at a production database.

## 11. Decision Summary

Answer these in order:

1. Is this ID a **business code** that must remain intact, or a **technical ID** generated for MongoDB?
2. Should BSON `_id` be **String** or **ObjectId** given existing data and integrated systems?
3. If using String, must 24-hex strings remain String-typed in the database?
4. If using ObjectId, are input IDs validated and conversions standardized at the API boundary?
5. Do repositories, `MongoTemplate`, the Java Driver, and reference fields share the **same BSON type convention**?
6. Have you verified the stored `_id` type, `findById`/`save` behavior, and legacy data with integration tests?

**Rule to remember:** `@Id String` may convert valid hex strings to BSON ObjectId under default rules; `@MongoId String` keeps IDs verbatim as String; `@MongoId(FieldType.OBJECT_ID) String` requests ObjectId when convertible. **Choose one clear convention per collection, verify the actual BSON type, and never treat an annotation change as a data migration.**
