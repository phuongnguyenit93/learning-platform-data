# ObjectId and String Mismatch Even When IDs Look Identical

A subtle bug in **Spring Data MongoDB** happens when a document exists in the collection, its `_id` in the admin UI looks identical to the ID string received by an API, yet `findById(...)` or `MongoTemplate.findOne(...)` returns empty. A common cause is **identical display text backed by different BSON types**: one record stores an `ObjectId`, while another stores a `String`.

MongoDB compares values using **BSON type and content**, not the string rendered by an administration tool. Therefore, `ObjectId("64b7f37a4e92b315c21d0abc")` and `"64b7f37a4e92b315c21d0abc"` are two distinct `_id` values. Spring Data MongoDB also applies ID conversion rules between Java and BSON, which can hide the discrepancy when mapping an `ObjectId` into a `String` field on an entity.

In this lesson from the **Errors and Diagnostics** chapter of `SPRING_DATA_MONGODB`, we trace from HTTP ID → repository/`MongoTemplate` → MongoDB driver → BSON, choose a consistent ID model, write verification tests, and plan safe migrations for legacy data when needed.

## 1. Two IDs That Look Alike Are Not Equal

Consider two documents in the same `orders` collection:

```javascript
// Document A: _id is a BSON ObjectId (12 bytes)
{
  _id: ObjectId("64b7f37a4e92b315c21d0abc"),
  status: "PAID"
}

// Document B: _id is a BSON String
{
  _id: "64b7f37a4e92b315c21d0abc",
  status: "NEW"
}
```

Both can coexist because the default unique index on `_id` treats different BSON types as distinct values. A query matches only the type provided:

```javascript
const hex = "64b7f37a4e92b315c21d0abc";

db.orders.findOne({ _id: ObjectId(hex) }); // Matches Document A
db.orders.findOne({ _id: hex });           // Matches Document B
```

Do not interpret this as "MongoDB stops using the index when looking up IDs." The `_id_` index can still be used; the problem is that **the lookup key has a different type from the stored key**. Adding indexes or forcing collation generally will not reconcile an `ObjectId` vs. `String` mismatch.

| Aspect | BSON ObjectId | BSON String |
| --- | --- | --- |
| Example value | `ObjectId("64b7f37a4e92b315c21d0abc")` | `"64b7f37a4e92b315c21d0abc"` |
| MongoDB type | `objectId` | `string` |
| BSON value | 12 binary bytes | UTF-8 string with length prefix |
| Typical Java type | `org.bson.types.ObjectId` | `java.lang.String` |
| Raw query via driver | `Filters.eq("_id", new ObjectId(hex))` | `Filters.eq("_id", hex)` |
| Extended JSON export | `{"$oid":"64b7..."}` | `"64b7..."` |

The `{"$oid":"..."}` notation is an **Extended JSON** convention representing a BSON ObjectId; do not assume every JSON object containing an `$oid` key was automatically stored as an ObjectId in the database. Actual stored types can only be verified via BSON queries or tools/codecs that handle Extended JSON properly.

## 2. Why Does Spring Data MongoDB Cause Confusion?

### 2.1. Implicit Rules of `@Id String`

Consider the entity:

```java
package example.orders;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record Order(
        @Id String id,
        String status
) {}
```

Spring Data MongoDB applies special mapping rules to properties annotated with `@Id` (or properties named `id` by convention). When the Java type is `String`, values may be converted to a BSON `ObjectId` **if the string is a valid ObjectId hex representation**. For strings that cannot be converted, the system may store/compare them as `String`. Exact behavior depends on the mapping type, converters, and API call; never guess the BSON type solely from a Java `String` field.

Example:

```java
repository.save(new Order("64b7f37a4e92b315c21d0abc", "PAID"));
```

With `@Id String` and default conversion settings, the ID above **may be written as a BSON ObjectId**. When read back, Spring Data can map the `ObjectId` into a Java `String`, causing logs of `order.id()` to show only the hex string and hide the underlying BSON type.

Conversely, a document imported or written via raw driver with a 24-hex-character `String` `_id` may not be found through a repository that converts ID parameters into `ObjectId`. Verify the behavior of the **exact mapping class and method** used by your application.

### 2.2. `@MongoId` Explicitly Declares the Desired ID Type

If the application intentionally stores **BSON String**, use the Spring Data MongoDB annotation:

```java
package example.orders;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "external_orders")
public record ExternalOrder(
        @MongoId(FieldType.STRING) String id,
        String status
) {}
```

Here, `@MongoId(FieldType.STRING)` expresses the contract to store `_id` as a String even when the value consists of exactly 24 hex characters. Its corresponding repository can use `MongoRepository<ExternalOrder, String>`.

If the application defines IDs as ObjectIds, using the Java type `ObjectId` directly is usually clearer:

```java
package example.orders;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "object_orders")
public record ObjectIdOrder(
        @Id ObjectId id,
        String status
) {}
```

The repository uses `MongoRepository<ObjectIdOrder, ObjectId>`. When an ID arrives from an HTTP path parameter (typically a String), the API layer should validate and parse it into an `ObjectId` **explicitly**. This avoids letting a single Java String be interpreted as two different storage types.

### 2.3. Comparing the Three Models

| Entity | Java Type | Expected `_id` Type | Caveats |
| --- | --- | --- | --- |
| `@Id String id` | String | Implicit conversion to ObjectId when valid | Easy to misread data imported from external systems |
| `@MongoId(FieldType.STRING) String id` | String | BSON String | Does not automatically merge legacy ObjectId documents |
| `@Id ObjectId id` | ObjectId | BSON ObjectId | API should parse/validate IDs at the boundary |

Choose an ID model based on an explicit storage contract; avoid changing annotations hastily just to "make queries work" without checking real data. Changing the mapping can cause previously found documents to stop matching.

## 3. Diagnosing Layer by Layer: Request, Java, BSON

When `GET /orders/{id}` returns 404 even though the document exists, inspect in order:

1. **HTTP input:** record the validated request ID; check whether the API layer trims, changes casing, adds prefixes, or URL-decodes it.
2. **Entity and repository:** check whether the ID property uses `@Id`, `@MongoId`, or custom mapping, and whether the repository generic ID is `String` or `ObjectId`.
3. **Call path:** `repository.findById(...)`, `MongoTemplate.findById(...)`, and driver `collection.find(...)` may follow different conversion paths.
4. **Actual BSON value:** read the document via raw driver and inspect the `_id` type; do not rely solely on UI display strings.
5. **Filter scope:** confirm tenant, status, soft-delete flags, and access permissions match too. An ID type mismatch is not the only reason a query returns empty.
6. **Write/import paths:** trace where documents are created: Spring repositories, `MongoTemplate`, shell scripts, ETL jobs, or services in other languages.

### 3.1. Inspecting Directly via `mongosh`

On a **test database** with sample data:

```javascript
const hex = "64b7f37a4e92b315c21d0abc";

// Differs by BSON type of the query value:
db.orders.findOne({ _id: ObjectId(hex) });
db.orders.findOne({ _id: hex });

// Inspect the BSON type directly in the returned result:
db.orders.aggregate([
  { $match: { _id: { $in: [ObjectId(hex), hex] } } },
  { $project: { _id: 1, idType: { $type: "$_id" }, status: 1 } }
]);
```

If both `findOne` queries return a document, the collection holds **two records with the same logical hex key but different BSON types**. If only one query returns a result, you have evidence of the actual stored type to compare against Spring Data's mapping path.

To inventory `_id` type distribution across the collection, run an aggregation:

```javascript
db.orders.aggregate([
  { $group: { _id: { $type: "$_id" }, documents: { $sum: 1 } } },
  { $sort: { documents: -1 } }
]);
```

This aggregation can scan many documents, so run it on a small collection or test copy first; on large production collections, schedule resources and timing carefully. Use representative sampling and controlled statistics instead of scanning everything during peak traffic.

### 3.2. Using the Raw Java Driver to Distinguish Types

`MongoTemplate.getCollection(...)` returns the MongoDB Java Driver collection, allowing inspection of raw BSON:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.types.ObjectId;

String hex = "64b7f37a4e92b315c21d0abc";
MongoCollection<Document> collection =
        mongoTemplate.getCollection("orders");

Document byObjectId = collection
        .find(Filters.eq("_id", new ObjectId(hex))).first();
Document byStringId = collection
        .find(Filters.eq("_id", hex)).first();

if (byObjectId != null) {
    Object key = byObjectId.get("_id");
    System.out.println(key.getClass().getSimpleName()); // ObjectId
}
if (byStringId != null) {
    Object key = byStringId.get("_id");
    System.out.println(key.getClass().getSimpleName()); // String
}
```

This is diagnostic code using sample data; do not print real IDs or documents containing sensitive data into operational logs. For production observability, record the BSON type, collection name, trace ID, and error code; avoid logging full BSON documents, URIs, or credentials.

Raw driver `Filters.eq("_id", hex)` preserves `String`; raw driver `Filters.eq("_id", new ObjectId(hex))` sends `ObjectId`. When queries go through Spring Data mapping, IDs may be converted according to entity metadata. Therefore, **do not assume a repository sends the exact same BSON as raw driver calls without verifying mapping**.

### 3.3. Do Not Compare Displayed JSON Alone

An API typically serializes `ObjectId` as a hex string, e.g., `"id": "64b7..."`. Two records with different BSON types become indistinguishable after JSON serialization. Other issues like letter casing, whitespace, `null`, or prefixes also cause confusion; distinguish them from BSON type mismatches.

If logs print "found ID X" from a Java `String` field, that alone does not prove `_id` is stored as a BSON String. Inspect the actual BSON value and the executed search command.

## 4. Querying Consistently Under One ID Contract

### 4.1. Standardizing on BSON ObjectId

When database IDs must be ObjectIds, define `ObjectIdOrder` as above and a repository:

```java
package example.orders;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ObjectIdOrderRepository
        extends MongoRepository<ObjectIdOrder, ObjectId> {}
```

At the HTTP boundary, accept a String and parse it cleanly:

```java
import java.util.Optional;
import org.bson.types.ObjectId;

public Optional<ObjectIdOrder> findOrderByPathId(String pathId) {
    if (pathId == null || !ObjectId.isValid(pathId)) {
        return Optional.empty(); // Controller can return HTTP 400 for malformed IDs
    }
    return objectIdOrderRepository.findById(new ObjectId(pathId));
}
```

`ObjectId.isValid(...)` validates the hex representation before instantiating `ObjectId`. In multi-tenant or authorized APIs, still verify tenant/owner access to the document; `findById` alone enforces no authorization. Include tenant filters when querying multi-tenant data.

With `MongoTemplate`, when the entity ID is `ObjectId`, query as follows:

```java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

ObjectId objectId = new ObjectId(pathId); // Validated above
Query query = Query.query(Criteria.where("_id").is(objectId));
ObjectIdOrder order =
        mongoTemplate.findOne(query, ObjectIdOrder.class);
```

### 4.2. When IDs Must Be BSON Strings

If IDs are supplied by an external system and **always** stored as Strings, use `@MongoId(FieldType.STRING)` and a repository with generic ID `String`:

```java
package example.orders;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface ExternalOrderRepository
        extends MongoRepository<ExternalOrder, String> {}
```

Now `findById("64b7f37a4e92b315c21d0abc")` queries by the stored string without automatically treating it as an ObjectId just because it is 24 hex characters. For direct raw driver queries, use `Filters.eq("_id", pathId)` to preserve the String type.

**Accuracy note:** If legacy data holds `ObjectId` `_id`s while the new entity queries only by String, the new entity will not automatically migrate historical records. You need a controlled compatibility reader and migration plan.

### 4.3. Do Not Use `findById(String)` to Probe Both Types

Trying to look up by String first and then falling back to ObjectId can produce unpredictable behavior, especially when `@Id String` triggers implicit conversion or when both records exist.

If you need a **temporary reader** for a mixed collection and the input ID is a valid 24-character hex string, build a raw driver adapter that queries both forms and handles duplicates explicitly:

```java
import com.mongodb.client.model.Filters;
import java.util.ArrayList;
import java.util.List;
import org.bson.Document;
import org.bson.types.ObjectId;

public Document readLegacyOrder(
        String hex, String authenticatedTenantId) {
    if (hex == null || !ObjectId.isValid(hex)) {
        throw new IllegalArgumentException("Expected ObjectId hex");
    }

    var filter = Filters.and(
            Filters.eq("tenantId", authenticatedTenantId),
            Filters.or(
                    Filters.eq("_id", new ObjectId(hex)),
                    Filters.eq("_id", hex)));

    List<Document> matches = mongoTemplate.getCollection("orders")
            .find(filter)
            .limit(2)
            .into(new ArrayList<>());

    if (matches.size() > 1) {
        throw new IllegalStateException("Ambiguous logical order ID");
    }
    return matches.isEmpty() ? null : matches.get(0);
}
```

This is a **temporary migration adapter**, assuming external IDs are ObjectId hex strings, the tenant ID comes from an authenticated session, and the system defines a policy for duplicate documents. Do not use this pattern for arbitrary String IDs, never drop the tenant scope, and never silently pick the first record when the same logical ID exists under both types. If business IDs are not ObjectId hex strings, define a separate String read path.

In production systems, returning a unified business entity from this adapter requires mapping/normalizing the document after confirming both record and access permissions. Never call `save(...)` directly on a partially mapped entity, as undeclared fields can be lost.

## 5. Common Pitfalls in Imports, Mapping, and Joins

### 5.1. Writing Data Through Multiple Paths

Common write sources:

| Write Source | Possible Behavior | What to Check |
| --- | --- | --- |
| Spring Data entity `@Id String` | Implicit ObjectId conversion when valid | Converters and actual stored BSON |
| Entity `@MongoId(FieldType.STRING)` | Saves String per contract | Are there legacy ObjectId documents? |
| Spring Data entity `@Id ObjectId` | Saves ObjectId | Does the API parse incoming IDs properly? |
| `mongosh` | Depends on `ObjectId(...)` vs. string literal | Seed/import scripts |
| Raw Java Driver | Depends on Java type passed to `Filters.eq` and `Document` | Inspect `get("_id").getClass()` |
| ETL/JSON import | Depends on Extended JSON/codec and source types | Post-import BSON data |

A migration job might leave `"64b..."` as a String in `_id`, while the application writer creates BSON ObjectIds. If every report prints IDs as text, the discrepancy may stay hidden until a join or repository change exposes it.

### 5.2. `$lookup` Does Not Join When Keys Differ in Type

Suppose `orders.customerId` is a String `"64b..."` while `customers._id` is the corresponding ObjectId. This pipeline:

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

can produce `customer: []` because the join keys have different BSON types. This is often misdiagnosed as "wrong collection" or "missing index."

If the data follows an explicit String → ObjectId hex contract, you can validate and convert **during migration or in a controlled aggregation expression**, such as `$convert` with `onError`/`onNull` to handle invalid IDs. However, runtime type conversion inside pipelines can prevent index usage or add overhead on large datasets; prefer fixing the long-term storage schema instead of relying on per-query conversion.

### 5.3. `String.equals(...)` Does Not Prove BSON Equality

In Java, `String.valueOf(raw.get("_id"))` can print identical hex text to the API string. Converting both to String in logs proves only **display** equivalence, not BSON type equivalence or how MongoDB indexes compare them.

To verify, inspect `raw.get("_id") instanceof ObjectId` or `instanceof String` on raw BSON alongside the exact query predicate sent by the driver or Spring Data.

## 6. Migrating Mixed-Type Data to a Single Standard

Before migrating, choose the **target standard**: ObjectId or BSON String. Neither choice fits every system. ObjectId works well when the database generates IDs or the domain accepts ObjectIds; String works well for identifiers controlled by external systems, including non-hex identifiers.

Safe steps:

1. **Inventory:** count documents with String vs. ObjectId `_id`s, identify their writers, locate referencing collections, and check for duplicate logical keys.
2. **Classify:** separate true business strings from strings that are merely hex representations of ObjectIds. Never blindly coerce every String into an ObjectId without validation rules.
3. **Update readers:** deploy a compatibility/monitoring reader so the application keeps reading during migration, with a policy when two records share the same logical ID.
4. **Update writers:** ensure every new producer writes only the target type and stops generating mixed types.
5. **Migrate and reconcile:** migrate in controlled batches; verify counts, references, unique constraints, access permissions, and dependent jobs.
6. **Contract:** once legacy data and writers are gone, remove the conversion adapter, temporary metrics, and workaround queries.

### 6.1. `_id` Is Immutable

MongoDB **does not allow updating `_id` in place** on an existing document. You cannot change its type with:

```javascript
// NOT a valid way to change _id type:
db.orders.updateOne(
  { _id: "64b7f37a4e92b315c21d0abc" },
  { $set: { _id: ObjectId("64b7f37a4e92b315c21d0abc") } }
);
```

Changing `_id`'s type requires inserting a **new** document with the target `_id` type and handling the old record under a controlled plan. Copy → verify → delete carries risks if writers remain active, other collections reference `_id`, or both types already coexist. Use locking, version/conditional updates, idempotency, and transactions where multi-document consistency is required; MongoDB transactions require an appropriate replica set or sharded deployment.

Never delete old records before verifying new records and all related references. Test on a snapshot or staging environment with checkpoints and a verified rollback plan.

### 6.2. Do Not Cast Everything to String in the API and Assume the Database Is Uniform

An API can consistently represent IDs as text while the **storage contract** still mandates an explicit type. If you choose ObjectId, parse IDs to `ObjectId` at the application boundary before querying. If you choose String, annotate with `@MongoId(FieldType.STRING)` and preserve raw Strings in BSON. When integrating with external systems, convert at the boundary rather than letting storage entities and JSON responses contradict one another.

## 7. Testing Against Real MongoDB

Mocking `MongoRepository` does not reproduce Spring Data's mapping/BSON behavior. Use Testcontainers or a dedicated test MongoDB service to verify these scenarios.

### 7.1. Sample Fixture Proving BSON Differences

The snippet below is part of a Java test using `MongoTemplate` connected to a test MongoDB instance. It needs no Spring Data entity to demonstrate two distinct `_id` types:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import java.util.List;
import org.bson.Document;
import org.bson.types.ObjectId;

String hex = "64b7f37a4e92b315c21d0abc";
ObjectId oid = new ObjectId(hex);
MongoCollection<Document> collection =
        mongoTemplate.getCollection("diagnostic_orders");

collection.insertMany(List.of(
        new Document("_id", oid).append("status", "PAID"),
        new Document("_id", hex).append("status", "NEW")));

Document a = collection.find(Filters.eq("_id", oid)).first();
Document b = collection.find(Filters.eq("_id", hex)).first();

assertThat(a).isNotNull();
assertThat(b).isNotNull();
assertThat(a.get("_id")).isInstanceOf(ObjectId.class);
assertThat(b.get("_id")).isInstanceOf(String.class);
```

Assertions use AssertJ. Fixtures must run only on a test-owned collection; clean up or use a fresh database before repeating tests. The outcome confirms the `_id` unique index allows two values with different BSON types.

### 7.2. Testing Mapping After Choosing an ID Type

For `ExternalOrder` using `@MongoId(FieldType.STRING)`, assert raw BSON after saving:

```java
String hex = "64b7f37a4e92b315c21d0abc";
externalOrderRepository.save(new ExternalOrder(hex, "NEW"));

Document stored = mongoTemplate.getCollection("external_orders")
        .find(Filters.eq("_id", hex))
        .first();

assertThat(stored).isNotNull();
assertThat(stored.get("_id")).isInstanceOf(String.class);
assertThat(externalOrderRepository.findById(hex)).isPresent();
```

For `ObjectIdOrder`, construct an `ObjectId` and assert `_id` is stored as `ObjectId`. Another valuable test seeds a raw 24-hex-character String into the collection and checks how a `@Id String`-based repository behaves in your **exact Spring Data version**. That validates implicit read/write/query conversion rules directly.

### 7.3. Minimum Test Matrix

| Scenario | Expectation |
| --- | --- |
| DB `ObjectId`, raw `ObjectId` query | Found |
| DB `ObjectId`, raw `String` query | Not found |
| DB `String`, exact raw `String` query | Found |
| DB `String`, raw `ObjectId` query | Not found |
| Same text with both BSON types present | Adapter detects ambiguous ID |
| `@MongoId(FieldType.STRING)` entity saving 24-hex ID | Stored as BSON String, found by repository |
| `@Id ObjectId` entity with non-hex input | API returns validation error before querying |
| `$lookup` String → ObjectId | Does not match automatically like String → String |
| Valid ID belonging to a different tenant | Data must not be returned |
| Re-running migration | Does not overwrite or delete wrong records |

### 7.4. Do Not Mix Functional Tests with Benchmarks

These tests confirm mapping and query **correctness**. When diagnosing performance, use `explain("executionStats")` and telemetry to inspect `totalDocsExamined`, `totalKeysExamined`, command count, network payload, and latency. For BSON ID type mismatches, however, the primary issue to fix is **query semantics and key types**, not raising `limit`, adding indexes, or changing batch sizes.

## 8. Related Errors and How to Distinguish Them

| Symptom | Possible Cause | How to Verify |
| --- | --- | --- |
| `findById` returns empty though UI shows record | BSON ID type mismatch | Compare raw queries with String vs. ObjectId |
| Raw driver finds it, repository does not | `@Id`, `@MongoId`, or converter differences | Inspect entity metadata and raw BSON |
| API lists two records with the same text ID | Both String and ObjectId exist | Check `$type` of `_id` |
| ObjectId parsing error | ID is not a valid 24-character hex string | Check `ObjectId.isValid(...)` at boundary |
| `ClassCastException` on `getString("_id")` | Raw BSON is `ObjectId` | Inspect `get("_id")` type before casting |
| `$lookup` yields empty array | Local/foreign fields have mismatched types or values | Check BSON types of both join keys |
| Query by ID is slow yet returns results | Different issue, e.g., extra filters/sort | Run `explain` and telemetry |
| Correct ID, wrong tenant or soft-deleted | Additional permission/status filters | Inspect complete filter and authorization |
| Records vanish after changing annotation | Queried BSON type changed | Inventory collection; test before/after mapping |

Another subtle bug is **hex casing differences**: ObjectId renders normalized lowercase hex, whereas BSON String stores exact characters and compares according to collation. Casing issues differ from BSON type mismatches; do not blindly apply `toLowerCase()` across everything without checking the ID contract and types.

## 9. Operational Incident Workflow

When unexpected 404 reports arrive:

1. Record the trace ID, collection, mapping type, and validated ID format; never dump entire documents to logs.
2. In an authorized environment, query raw values using both String and ObjectId under the proper tenant scope.
3. Cross-check write and read paths: check whether writers use repositories, raw driver, shell scripts, or ETL, and find where types diverged.
4. Inspect entity and repository generic ID types; if custom `MongoConverter` or `MongoCustomConversions` exist, evaluate their effect on ID mapping.
5. Seed both types in Testcontainers/test MongoDB and write a reproduction test; verify the mapping fix or adapter.
6. Measure how many historical records are affected, plan a migration if needed, and deploy compatible readers before switching writers.
7. Track missing-ID lookups, malformed ID counts, ambiguous-ID hits, and remaining legacy-type document ratios.

Metrics should use bounded labels (such as `id_bson_type=objectId|string|unknown`) rather than raw ID values as tags. Ensure diagnostic queries never bypass tenant or access checks just because they run in debug mode.

## 10. Hands-on Exercises

**Exercise 1 — Diagnosing with `mongosh`.** Insert two documents sharing the same 24-hex-character string where one `_id` is an `ObjectId` and one is a `String`. Write two `findOne` calls and a `$type` aggregation to prove they are distinct. Explain why the `_id_` unique index allows both.

**Exercise 2 — Comparing `@Id String` and `@MongoId(FieldType.STRING)`.** Create two separate entities and repositories, save a 24-character hex ID, and read raw BSON back via the driver. Document the stored types and `findById` results on your current Spring Data MongoDB version.

**Exercise 3 — HTTP Boundary.** Build an order lookup endpoint where IDs are stored as `ObjectId`. Validate the path ID, parse it to `ObjectId`, and query; test malformed strings, nonexistent documents, and documents owned by a different tenant.

**Exercise 4 — Mixed-Type Migration.** Create a dataset containing Strings, ObjectIds, and one colliding logical ID pair. Design a temporary compatibility reader, an ambiguous-ID policy, an immutable `_id` migration strategy, and a verification plan before deleting legacy records.

**Exercise 5 — `$lookup` and Performance.** Seed `orders.customerId` as String and `customers._id` as ObjectId; confirm `$lookup` fails to match. Propose a schema alignment strategy so queries use indexes efficiently, then measure `explain("executionStats")` on a sizable dataset.

**Completion Criteria:** You can distinguish BSON ObjectId from String despite identical hex displays; trace Spring Data MongoDB's ID conversion path; apply `@Id`, `@MongoId(FieldType.STRING)`, and repository types consistently; diagnose using raw driver/`$type`; and plan safe migrations given `_id` immutability.
