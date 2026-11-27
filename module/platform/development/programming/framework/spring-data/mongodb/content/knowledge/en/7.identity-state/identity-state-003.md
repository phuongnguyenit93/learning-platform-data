# Strings Can Convert to ObjectId and Mismatched-Type Query Errors

> **Chapter:** Identity and State  
> **Module:** `SPRING_DATA_MONGODB` — using Spring Data MongoDB to map documents and access MongoDB via `MongoTemplate` or repositories, as well as designing queries, testing, and diagnosing data errors.  
> **Objective:** Explain why a Java `String id` field does not guarantee MongoDB stores `_id` as BSON `string`; distinguish `@Id` from `@MongoId`; find the root cause when `findById()` returns empty; choose a consistent identifier type; and safely handle collections with mixed `_id` types.

## 1. The Problem: IDs Look Identical but Queries Return Different Results

MongoDB stores documents as **BSON**. Each document in a collection typically has a uniquely indexed `_id` field. BSON encodes **data type** information, so two values displaying the exact same character sequence can still be distinct:

~~~javascript
// _id is a BSON ObjectId (12 bytes, displayed as 24 hex characters).
{ _id: ObjectId("507f1f77bcf86cd799439011"), kind: "object-id" }

// _id is a BSON string whose content looks like an ObjectId.
{ _id: "507f1f77bcf86cd799439011", kind: "string-id" }
~~~

Both documents above can coexist in the same collection: `ObjectId("507f...")` is **different** from the string `"507f..."` for `_id` matching, even though they look alike visually. MongoDB does not automatically convert strings into `ObjectId` during a standard `mongosh` query.

For example:

~~~javascript
db.identity_type_demo_003.findOne({
  _id: "507f1f77bcf86cd799439011"
});
// Matches only documents whose _id has type string.

db.identity_type_demo_003.findOne({
  _id: ObjectId("507f1f77bcf86cd799439011")
});
// Matches only documents whose _id has type objectId.
~~~

In **Spring Data MongoDB**, an additional mapping layer can convert between Java `String` and BSON `ObjectId`. As a result, the same Java `String id` field declared differently with `@Id`/`@MongoId` can send queries down to MongoDB with **different BSON types**.

## 2. Understanding BSON `ObjectId` Accurately

`ObjectId` is a dedicated BSON type, commonly used as the default `_id`. An `ObjectId` value consists of **12 bytes**, typically displayed as **24 hexadecimal characters** (0–9, a–f). A 24-character string is not necessarily a valid ObjectId code: all characters must be hex digits. Even when it is valid hex, that still **does not prove** the data is stored as BSON `objectId`.

| Value | BSON Type | Meaning |
| --- | --- | --- |
| `ObjectId("507f1f77bcf86cd799439011")` | `objectId` | ObjectId-typed ID |
| `"507f1f77bcf86cd799439011"` | `string` | 24-character hex string |
| `"order-001"` | `string` | Business ID not in ObjectId format |
| `123` | Typically a numeric type in BSON | Numeric ID, not equal to the string `"123"` |

Length or visual appearance is no substitute for checking the **BSON type**. When investigating query failures, always verify both **value** and **type** on the MongoDB side.

### 2.1. Isolated Practice Dataset

The examples use `mongosh` on a test database. Run them in a learning environment, not on business collections:

~~~javascript
use spring_data_mongodb_lab

const demo = db.identity_type_demo_003;
const HEX_ID = "507f1f77bcf86cd799439011";

// If you already ran the previous exercise, create another test collection
// or clean up only the documents you created before reloading.
demo.insertMany([
  {
    _id: ObjectId(HEX_ID),
    kind: "object-id",
    description: "Document storing _id as BSON ObjectId"
  },
  {
    _id: HEX_ID,
    kind: "string-id",
    description: "Document storing _id as BSON string"
  },
  {
    _id: "order-001",
    kind: "business-id",
    description: "Business ID that cannot be converted to ObjectId"
  }
]);
~~~

The first two documents intentionally share the same textual value `507f1f77bcf86cd799439011` with different types. Because `_id` uniqueness is evaluated by BSON value, both inserts can succeed. If you run `insertMany` again, you will encounter `E11000 duplicate key` since the data already exists; do not call `drop()` on collections outside your test scope.

### 2.2. Queries Demonstrating the Difference

~~~javascript
// Query by string: kind = "string-id".
demo.findOne({ _id: HEX_ID });

// Query by ObjectId: kind = "object-id".
demo.findOne({ _id: ObjectId(HEX_ID) });

// Business string: kind = "business-id".
demo.findOne({ _id: "order-001" });

// Count documents with different _id types.
demo.countDocuments({ _id: { $type: "string" } });   // 2
demo.countDocuments({ _id: { $type: "objectId" } }); // 1
~~~

`$type` directly checks the BSON type. With the initial sample dataset, there are two strings (the hex string and `order-001`) and one ObjectId. When using `find({ _id: { $type: "objectId" } })`, the results contain only documents whose `_id` actually has the ObjectId type.

You can also inspect the type of each value in a single query:

~~~javascript
demo.aggregate([
  {
    $project: {
      _id: 1,
      kind: 1,
      idBsonType: { $type: "$_id" }
    }
  },
  { $sort: { kind: 1 } }
]);
// idBsonType: "string" or "objectId".
~~~

This is a reliable verification step when two records display identical-looking ID strings in the UI.

## 3. Spring Data MongoDB `_id` Mapping Rules

When working through `MongoTemplate` or repositories, Spring Data uses `MappingMongoConverter` to convert between Java objects and BSON documents. Under default mapping rules:

- A property annotated with Spring Data's `@Id` (`org.springframework.data.annotation.Id`) maps to `_id`.
- A property named `id` without special annotations is also typically recognized as the identifier and mapped to `_id`.
- For a Java `String` identifier using the standard `@Id` mechanism, Spring Data **attempts to convert** the value into a BSON `ObjectId` if possible. If it cannot be converted, the value is stored as `string`.
- `@MongoId` lets you control the target type instead of relying on the automatic conversion attempt above.

Crucially, the **Java property type** and the **actual BSON type of `_id`** do not necessarily match. This also affects the **query filters** Spring Data generates, not only `insert` and `save` operations.

### 3.1. `@Id String`: Uses `ObjectId` When Convertible

~~~java
package com.example.identity;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "identity_type_demo_003")
public class AutoIdDocument {
    @Id
    private String id;
    private String kind;

    protected AutoIdDocument() { }

    public AutoIdDocument(String id, String kind) {
        this.id = id;
        this.kind = kind;
    }

    public String getId() { return id; }
    public String getKind() { return kind; }
}
~~~

Suppose the application saves using:

~~~java
String hexId = "507f1f77bcf86cd799439011";

template.insert(
    new AutoIdDocument(hexId, "object-id")
);
~~~

With default mapping configuration, `hexId` is a string convertible to `ObjectId`, so `_id` **is stored as BSON ObjectId**. If `"order-001"` is passed into the same `@Id String id` property, the value cannot be converted to ObjectId and will be stored as a BSON string.

> **Note about the example:** The practice collection in Section 2 already has the corresponding ObjectId document. The `insert` snippet here only illustrates the mapping result—**do not run it directly on the already-populated collection**, as it will cause a duplicate `_id` error.

A system using `@Id String` can inadvertently produce **two ID types in a single collection** if IDs are sometimes 24-character hex strings and other times business codes. That is why choosing `String` in the entity alone is not enough to define the storage policy.

### 3.2. Default `@MongoId`: Preserves the Actual Java Type

~~~java
package com.example.identity;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "identity_type_demo_003")
public class StringIdDocument {
    @MongoId
    private String id;
    private String kind;

    protected StringIdDocument() { }

    public StringIdDocument(String id, String kind) {
        this.id = id;
        this.kind = kind;
    }

    public String getId() { return id; }
    public String getKind() { return kind; }
}
~~~

`@MongoId` defaults to `FieldType.IMPLICIT`, meaning it preserves the property's actual value type; with `String id`, `_id` is stored as a BSON string **even when** the string looks like a valid ObjectId.

You can make this intent explicit with the annotation:

~~~java
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@MongoId(FieldType.STRING)
private String id;
~~~

`@MongoId(FieldType.STRING)` clearly expresses the policy "the ID is a business string"; it is especially useful when an ID could accidentally match a 24-character hex format.

### 3.3. `@MongoId(FieldType.OBJECT_ID)`: Targets ObjectId Storage

When an application wants to keep a Java `String` API while storing `_id` as a BSON `ObjectId`:

~~~java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "identity_type_demo_003")
public class ExplicitObjectIdDocument {
    @MongoId(FieldType.OBJECT_ID)
    private String id;
    private String kind;

    protected ExplicitObjectIdDocument() { }

    public ExplicitObjectIdDocument(String id, String kind) {
        this.id = id;
        this.kind = kind;
    }

    public String getId() { return id; }
    public String getKind() { return kind; }
}
~~~

For a valid hex `String` value, mapping attempts to convert it to `ObjectId` for storage and querying. The API receiving IDs from users should **validate the format before use**; do not assume any arbitrary business ID string is a valid ObjectId. If the whole system mandates ObjectId, using a `org.bson.types.ObjectId` property makes the data type contract even clearer.

### 3.4. Comparing the Mapping Options

| Java Declaration | `_id` when ID value is valid hex string | `_id` when value is `"order-001"` | Notes |
| --- | --- | --- | --- |
| `@Id String id` | Attempts conversion to BSON `objectId` | Stores BSON `string` | Can produce mixed-type data |
| `@MongoId String id` | BSON `string` | BSON `string` | Preserves Java type |
| `@MongoId(FieldType.STRING) String id` | BSON `string` | BSON `string` | Sets an explicit string policy |
| `@MongoId(FieldType.OBJECT_ID) String id` | Attempts conversion to BSON `objectId` | Should not use invalid IDs | Requires input validation |
| `@Id ObjectId id` | BSON `objectId` | Cannot assign `"order-001"` directly | Fits a consistent ObjectId model |

Key takeaway: choose one policy for the **entire collection and entity lifecycle**, including creation, reading, updating, deletion, and references from other documents. Never change an annotation merely to "make one query work" without checking existing data in MongoDB.

## 4. Why Can `findById()` Return `null` / `Optional.empty()`?

Suppose the collection contains **both** documents:

~~~javascript
{ _id: ObjectId("507f1f77bcf86cd799439011"), kind: "object-id" }
{ _id: "507f1f77bcf86cd799439011", kind: "string-id" }
~~~

On the Spring Data side:

~~~java
String id = "507f1f77bcf86cd799439011";

// With @Id String: converter attempts to use ObjectId for the query.
AutoIdDocument objectDoc = template.findById(id, AutoIdDocument.class);
// With the sample data: kind = "object-id".

// With @MongoId String: converter keeps BSON string.
StringIdDocument stringDoc = template.findById(id, StringIdDocument.class);
// With the sample data: kind = "string-id".
~~~

Both calls receive the same Java `String` variable and target the same collection, yet the **entity metadata differs**. `MongoTemplate` applies the converter based on the target entity type when constructing the query. In this case:

~~~text
AutoIdDocument  (@Id String):
  _id = ObjectId("507f1f77bcf86cd799439011")

StringIdDocument (@MongoId String):
  _id = "507f1f77bcf86cd799439011"
~~~

If the collection **only** has a BSON string `_id` record while the entity uses `@Id String`, `findById(hexId, AutoIdDocument.class)` can return `null` even though you see a document with the exact same ID string. Similarly, if the collection only holds ObjectIds while the entity enforces `@MongoId(FieldType.STRING)`, the query may fail to match.

### 4.1. Repositories Are Also Affected by Mapping

~~~java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface AutoIdRepository
        extends MongoRepository<AutoIdDocument, String> {
}

public interface StringIdRepository
        extends MongoRepository<StringIdDocument, String> {
}
~~~

~~~java
String hexId = "507f1f77bcf86cd799439011";

// Typically targets the BSON objectId document.
var a = autoIdRepository.findById(hexId);

// Targets the BSON string document.
var b = stringIdRepository.findById(hexId);
~~~

`MongoRepository.findById()` uses the mapping metadata corresponding to the domain class, so having a generic ID type of `String` **does not guarantee** querying against a BSON string. Additionally, `existsById()` and `deleteById()` must be checked within the same mapping context; with an incompatible `_id` type, those operations may miss the document you intended to target.

### 4.2. `Criteria.where("id")` and `Criteria.where("_id")` Are Not an Automatic "Escape Hatch"

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

String id = "507f1f77bcf86cd799439011";

// MappingMongoConverter maps the Java id property to _id.
Query mapped = Query.query(Criteria.where("id").is(id));

AutoIdDocument result = template.findOne(mapped, AutoIdDocument.class);
~~~

Spring Data maps both **field names** and **data types** in `Query` based on the entity. Thus, changing the field string in `Criteria` from `"id"` to `"_id"` does not guarantee the value remains a `String` if you are still querying through an entity mapping that applies ID conversion rules.

When you need to verify exact BSON, use `mongosh` or the MongoDB Java Driver API directly. When you need predictable behavior at the Spring Data layer, the proper solution is choosing a mapping consistent with the stored type.

## 5. Comparing Direct Queries and Spring Data Queries

### 5.1. `mongosh` Does Not Auto-Convert Types in Equality Filters

~~~javascript
const raw = "507f1f77bcf86cd799439011";

// Matches string only.
demo.findOne({ _id: raw });

// Matches BSON ObjectId only.
demo.findOne({ _id: ObjectId(raw) });

// Inspect the _id type of each record directly.
demo.find({}, { _id: 1, kind: 1 });
~~~

### 5.2. Java Driver: Selecting the Exact Filter Type

If you are handling a mixed-type dataset and need to inspect exact BSON without Spring Data mapping:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.types.ObjectId;

String hexId = "507f1f77bcf86cd799439011";
MongoCollection<Document> rawCollection = template.getDb()
    .getCollection("identity_type_demo_003");

// Document with _id of type BSON string.
Document stringMatch = rawCollection
    .find(Filters.eq("_id", hexId))
    .first();

// Document with _id of type BSON objectId.
Document objectIdMatch = rawCollection
    .find(Filters.eq("_id", new ObjectId(hexId)))
    .first();
~~~

Here `template.getDb().getCollection(...)` returns the MongoDB Java Driver API, and `Filters.eq()` accepts a strongly typed value. The code above is for **diagnostics or deliberate raw operations**; in normal business logic, prefer entity models and repositories with consistent ID types.

### 5.3. Checking Whether a String Can Convert to ObjectId

~~~java
import org.bson.types.ObjectId;

String rawId = "507f1f77bcf86cd799439011";

if (ObjectId.isValid(rawId)) {
    ObjectId objectId = new ObjectId(rawId);
    // Use objectId only when the storage contract requires BSON ObjectId.
}
~~~

`ObjectId.isValid(rawId)` only checks **whether the string format can represent an ObjectId**. It **does not access the database** and does not prove that the document with that ID is stored as BSON ObjectId. For example, `rawId` can have a valid format while the document is still `{ _id: rawId }`.

Do not convert every 24-character string into an ObjectId out of habit. First determine which identification policy the collection/entity enforces.

## 6. Mismatched-Type Query Errors Affect More Than `find`

An incompatible `_id` type affects all CRUD operations:

| Operation | Consequence if filter uses wrong BSON type |
| --- | --- |
| `findOne` / `findById` | Document not found; returns `null` or `Optional.empty()` |
| `countDocuments` / `existsById` | Returns 0 or `false` even when a document with the same display value exists |
| `updateOne` / `MongoTemplate.updateFirst` | `matchedCount = 0`; no update performed |
| `deleteOne` / `deleteById` | `deletedCount = 0` or fails to delete the intended record |
| `replaceOne` | Does not match the existing document |
| `upsert: true` | May insert an extra document with a different BSON `_id` type, causing a business duplicate |
| `save` | May write a different document instead of updating the one you thought existed, depending on metadata and ID type |

The following example easily introduces a logic bug:

~~~javascript
// Existing document:
{ _id: "507f1f77bcf86cd799439011", status: "DRAFT" }

// A BSON ObjectId filter will not match the string _id above.
db.identity_type_demo_003.updateOne(
  { _id: ObjectId("507f1f77bcf86cd799439011") },
  { $set: { status: "PUBLISHED" } }
);
// If only the string document exists: matchedCount = 0.
~~~

In the practice dataset from Section 2, **both** ObjectId and string exist, so the operation above would instead match the other ObjectId document. That is a greater risk than returning empty: a request could **read or overwrite the wrong record** if two `_id` types are allowed to coexist with the same display content.

Be especially careful with `upsert: true`: the same business "code" can spawn two valid documents in MongoDB because `_id` differs in BSON type. The default unique index on `_id` does not automatically catch this business-level duplication.

## 7. How to Diagnose When the Application Cannot Find a Document

Suppose an HTTP endpoint receives `GET /orders/507f1f77bcf86cd799439011` and `repository.findById(id)` returns empty, yet an operator sees the document in the MongoDB UI.

### Step 1 — Confirm the Correct Database and Collection

~~~javascript
db.getName();
db.getCollectionNames();
db.identity_type_demo_003.findOne({});
~~~

In the Spring Data application, check `@Document(collection = "...")` or collection naming conventions, the database in the connection URI, the active profile, and which `MongoTemplate` is injected. Pointing to the wrong environment also produces "query finds nothing" symptoms unrelated to ID conversion.

### Step 2 — Inspect the Underlying BSON Type

~~~javascript
const id = "507f1f77bcf86cd799439011";

db.identity_type_demo_003.findOne({ _id: id });
db.identity_type_demo_003.findOne({ _id: ObjectId(id) });

db.identity_type_demo_003.aggregate([
  {
    $match: {
      _id: { $in: [id, ObjectId(id)] }
    }
  },
  {
    $project: {
      _id: 1,
      kind: 1,
      idType: { $type: "$_id" }
    }
  }
]);
~~~

If only one query returns a result, you have identified the direction of the type mismatch. If both return results, the collection holds **two documents with the same ID text** but different types. If both are empty, verify the ID value, database, collection, and actual data.

### Step 3 — Audit Java Annotations and ID Types

~~~text
@Id String id
    => may convert hex String to ObjectId

@MongoId String id
    => defaults to keeping String

@MongoId(FieldType.STRING) String id
    => requests String target type

@MongoId(FieldType.OBJECT_ID) String id
    => attempts conversion to ObjectId

@Id ObjectId id
    => explicit ObjectId representation in Java
~~~

Also check the repository's generic type, such as `MongoRepository<OrderDocument, String>` vs. `MongoRepository<OrderDocument, ObjectId>`. This generic parameter governs the ID type at the API level, while **the entity's mapping metadata** determines how `_id` is converted.

### Step 4 — Trace Write Entry Points

Find the data flow that created the document:

- Written via `MongoRepository.save()` or `MongoTemplate.insert()` on an entity with `@Id String`?
- Imported via `mongosh`, MongoDB Compass, raw driver, or an ETL job assigning `_id` as a string?
- Did a previous application version use `@MongoId(FieldType.STRING)`, while the new version switched to `@Id`?
- Do multiple services share the collection while declaring different ID types?

If the writer and reader use two different mapping rules, the bug will recur even after patching one query. Both **the write path and read path** must be standardized.

### Step 5 — Check Operation Results Instead of Guessing From HTTP Status

For updates or deletes, inspect `matchedCount`, `modifiedCount`, `deletedCount`, and the returned document itself. An API returning 200 does not prove the filter matched a record; tie result checks into business logic.

## 8. Designing Consistent Identification From the Start

Choose the ID type based on the **data contract**, then apply it uniformly across mappers, repositories, DTOs, events, and reference fields.

### Option A — All `_id` Values Are BSON ObjectId

~~~java
package com.example.identity;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
public class OrderDocument {
    @Id
    private ObjectId id;
    private String state;

    public ObjectId getId() { return id; }
    public String getState() { return state; }
}
~~~

Repository:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, ObjectId> {
}
~~~

When receiving a string ID from an API, validate and convert at the boundary:

~~~java
import org.bson.types.ObjectId;

public ObjectId parseOrderId(String rawId) {
    if (rawId == null || !ObjectId.isValid(rawId)) {
        throw new IllegalArgumentException("Invalid MongoDB ObjectId");
    }
    return new ObjectId(rawId);
}
~~~

This is a clean choice when MongoDB is the primary ID generator. Values sent in API responses can use `objectId.toHexString()`; there is no need to force the entity's internal type to `String` solely because URLs carry text.

### Option B — All `_id` Values Are BSON string

~~~java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document("orders")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;
    private String state;

    public String getId() { return id; }
    public String getState() { return state; }
}
~~~

Corresponding repository:

~~~java
public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {
}
~~~

This option fits when `_id` is a string UUID, system-issued order code, or external identifier. Even if a code happens to be 24 hex characters long, `@MongoId(FieldType.STRING)` preserves the BSON string type.

**Mandatory rule:** do not declare two `OrderDocument` classes with the same name in one file; the declarations above are **two alternative designs** for separate projects. Pick one design before storing data.

### Option C — Java Uses `String`, MongoDB Uses BSON ObjectId

~~~java
@Document("orders")
public class OrderDocument {
    @MongoId(FieldType.OBJECT_ID)
    private String id;
    private String state;
}
~~~

This design is useful when the Java layer wants to expose IDs as `String` while storage uses ObjectId. However, the API must still validate 24-character hex strings and keep mapping rules consistent across all repositories/templates.

| Criterion | True ObjectId (`ObjectId id`) | True String (`@MongoId(FieldType.STRING)`) |
| --- | --- | --- |
| Desired BSON type | `objectId` | `string` |
| ID generation | MongoDB/driver can generate ObjectId | Application typically assigns business ID explicitly |
| Receiving ID over HTTP | Parse hex string into `ObjectId` | Use string directly after business validation |
| Implicit conversion risk | Low when entity type is accurate | Low when using `@MongoId` explicitly |
| Non-hex external codes | Unsuitable as ObjectId | Suitable |

Neither type is universally "better" for every system. Consistency between **stored data** and **mapping metadata** matters far more than how an ID looks on screen.

## 9. Data Already Mixes `ObjectId` and `string`: How to Handle It?

If production already contains `_id` values of different types, **do not simply replace `@Id` with `@MongoId`** and deploy immediately. Changing annotations alters the filter types Spring Data generates; legacy records may stop being found or updated.

A safe path consists of the following steps.

### 9.1. Inventory Before Changing Anything

On a database approved for analysis, count types:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: { $type: "$_id" },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
~~~

Cross-check with write sources: which entities write, which import jobs write, and whether any documents reference the ID as `String` or `ObjectId` in other fields. Check whether the same hex value simultaneously exists under both types, as that represents a **logical duplicate** the `_id` unique index does not prevent.

### 9.2. Define the Target State

Suppose you choose BSON string `_id` system-wide because the ID is an order code. Conventions:

1. All new writers use `@MongoId(FieldType.STRING)`.
2. Legacy read paths are supported during the transition via a controlled compatibility mechanism.
3. Every place storing a reference key uses the same representation convention.
4. APIs facing ambiguity due to duplicate representations of both `_id` types have a resolution rule defined prior to migration.

### 9.3. You Cannot `$set` `_id` Directly

MongoDB does not allow updating an existing document's `_id` value with `$set`:

~~~javascript
// Invalid: _id cannot be replaced via a normal update.
db.orders.updateOne(
  { _id: ObjectId("507f1f77bcf86cd799439011") },
  { $set: { _id: "507f1f77bcf86cd799439011" } }
);
~~~

Changing the `_id` type fundamentally requires **creating a new document with the target ID**, validating the data, updating related references if any, and then handling the old document. If both types already coexist, you cannot insert the target document with the same target `_id` type/value without a policy to merge, reject, or prioritize.

Do not blindly copy/delete production data following an example: you need backups, concurrent-write handling, idempotency, uniqueness verification, and an appropriate rollback plan. MongoDB transactions can help guarantee atomicity for certain operations within the same cluster if topology and requirements allow, but they do not automatically resolve references in external systems.

### 9.4. Post-Migration Verification

- Re-run `$type` aggregation on `_id` to confirm no non-conforming types remain.
- Compare document counts and business keys before/after.
- Test `findById`, `existsById`, `updateFirst`, `deleteById`, and `save` via the official entities/repositories.
- Verify aggregation queries, events, APIs, and collections containing references to old IDs.
- Monitor unexpected "not found" errors and upsert counts during the transition window.

The goal is restoring **one end-to-end identification rule**, avoiding long-term operation with two interpretations of the same code.

## 10. Regression Testing to Prevent Recurring Bugs

This is a prime case for writing **integration tests** with a real MongoDB instance or MongoDB Testcontainers, because the behavior depends on BSON serialization in the MongoDB driver and Spring Data converters. Mocking repositories usually fails to catch `_id` type mismatches.

Example test harness:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootTest
class IdTypeMappingIntegrationTest {
    private static final String COLLECTION = "identity_type_demo_003";
    private static final String HEX = "507f1f77bcf86cd799439011";

    @Autowired MongoTemplate template;

    @Test
    void idMappingDeterminesWhichBsonTypeIsQueried() {
        // Prepare fixtures in an isolated test database.
        // Each run must ensure only this test's fixture documents are present.
        var collection = template.getDb().getCollection(COLLECTION);
        collection.deleteMany(new Document("_id",
            new Document("$in", java.util.List.of(HEX, new ObjectId(HEX)))));
        collection.insertOne(new Document("_id", HEX)
            .append("kind", "string-id"));
        collection.insertOne(new Document("_id", new ObjectId(HEX))
            .append("kind", "object-id"));

        AutoIdDocument mappedToObjectId =
            template.findById(HEX, AutoIdDocument.class);
        StringIdDocument mappedToString =
            template.findById(HEX, StringIdDocument.class);

        assertThat(mappedToObjectId).isNotNull();
        assertThat(mappedToObjectId.getKind()).isEqualTo("object-id");
        assertThat(mappedToString).isNotNull();
        assertThat(mappedToString.getKind()).isEqualTo("string-id");
    }
}
~~~

This test depends on the mapping classes from Section 3, a configured test MongoDB connection, and collection write permissions. **Run only against an isolated test database**: the setup step deletes two documents with matching IDs in the collection. In a real test suite, prefer giving each test its own collection/namespace, cleaning fixtures via `try/finally` or test lifecycle hooks, and avoiding hardcoded IDs that collide with other tests.

Also add test cases for `@Id String` with a non-hex ID (`order-001`), `@MongoId(FieldType.STRING)` with a hex ID, and direct BSON inspection via the raw driver. These cases clarify read/write behavior after upgrading Spring Data.

## 11. Quick Diagnostic Table

| Symptom | Possible Cause | How to Verify |
| --- | --- | --- |
| `findById(hex)` returns `Optional.empty()` but Compass shows the document | Entity converts `String` to ObjectId while DB stores BSON string (or vice versa) | Query in `mongosh` with `String` and `ObjectId` in turn; check `$type` |
| `findById("order-001")` works, but `findById(hex)` fails | `@Id String` only converts valid hex IDs to ObjectId | Inspect both ID shapes with `$type` |
| `updateFirst` reports `matchedCount = 0` | `_id` filter has wrong BSON type or wrong database | Compare raw filter with the Spring Data query |
| `upsert` creates a record with an already-existing code | `_id` uses a different BSON type, bypassing the `_id` unique index | Count IDs by `$type`, search for both variants |
| After changing `@Id` to `@MongoId`, many records disappear | Application query rule changed while legacy data was not migrated | Check old and new `_id` BSON; plan a migration |
| ID is a string but API sends a different `ObjectId` value | ID parsing does not match the data contract | Use `ObjectId.isValid` only when the app actually uses ObjectId |
| `findById` returns empty for every ID | Could be wrong database/collection, not just wrong type | Check URI, `@Document`, raw data, permissions |

## 12. Practice Exercises

### Exercise 1 — Classify the Types

Given two documents:

~~~javascript
{ _id: ObjectId("64a1f34b60cc1200441a0222"), state: "NEW" }
{ _id: "64a1f34b60cc1200441a0222", state: "PAID" }
~~~

Question: Do these two documents violate the `_id` unique index? Which query finds `state: "PAID"`?

**Answer:** No, because `_id` has different BSON types. `findOne({ _id: "64a1f34b60cc1200441a0222" })` finds the string document, whereas `ObjectId("...")` finds the `NEW` document.

### Exercise 2 — Changing Annotations

A service stored `@Id String id` with value `"64a1f34b60cc1200441a0222"`. Later it was refactored to `@MongoId(FieldType.STRING) String id` without migrating data. What can happen?

**Answer:** Legacy records were stored as BSON ObjectId under `@Id` mapping, while new queries attempt to use BSON string. `findById` may return empty; other operations may fail to match, and an upsert call can create a second record. You must inventory data types, establish the ID convention, and either migrate or build deliberate compatibility handling.

### Exercise 3 — Choosing an Identification Policy

A system has IDs like `"order-001"`, `"order-002"`, and occasionally an external code that is exactly 24 hex characters long. Which ID declaration keeps the data consistent?

**Suggested Answer:** `@MongoId(FieldType.STRING) String id` is the intuitive choice if all codes are treated as business strings. Do not use `@Id String` and assume "every ID will be a BSON string".

### Exercise 4 — Fixing the Query

The actual database stores:

~~~javascript
{ _id: ObjectId("64a1f34b60cc1200441a0222"), total: 100 }
~~~

Write a `mongosh` command to find that exact document and explain why `{ _id: "64a1f34b60cc1200441a0222" }` does not match.

**Answer:**

~~~javascript
db.orders.findOne({
  _id: ObjectId("64a1f34b60cc1200441a0222")
});
~~~

Because MongoDB compares by BSON type, a string filter and an ObjectId are two different values.

## References

- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): `_id` mapping rules and `String`/`ObjectId` conversion in `MappingMongoConverter`.
- [Spring Data MongoDB — `@MongoId` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/MongoId.html): `FieldType.IMPLICIT`, `STRING`, `OBJECT_ID`, and identifier conversion policies.
- [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/): BSON types and `ObjectId` representation.
- [MongoDB Manual — `$type` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/type/): querying documents by BSON type.
- [Spring Data MongoDB — Template CRUD Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): queries, updates, and `MongoTemplate` APIs.
