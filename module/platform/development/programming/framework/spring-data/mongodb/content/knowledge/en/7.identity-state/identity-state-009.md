# Composite Identifiers and Structure/Field-Order Requirements in MongoDB

## 1. What Is a Composite Identifier?

In MongoDB, every document has an `_id` field for identification. The most common value is `ObjectId`, but `_id` can also be **a nested document** containing multiple identifier components. This approach is commonly known as a **composite identifier** or *compound identity*. For example, in a multi-tenant application where order numbers are only unique **within each tenant**, the identifier can combine both the tenant ID and order number:

```javascript
{
  _id: {
    tenantId: "acme",
    orderNo: "ORD-001"
  },
  status: "CREATED",
  total: 125000
}
```

The two components `tenantId` and `orderNo` together form a single identifier key. Order `ORD-001` of tenant `acme` is distinct from order `ORD-001` of tenant `beta`. MongoDB enforces the uniqueness of `_id` values within the collection and corresponding deployment constraints.

For **Spring Data MongoDB**, the challenge goes beyond modeling a Java class with two fields. You must decide **the BSON shape written into `_id`**, **the order of fields inside the key document**, how to query via `MongoTemplate` and repositories, how to index, and how to keep the key stable across application versions.

Objectives of this lesson in the **Identity and State** chapter:

- Know when to use a document-typed `_id` versus a simple `ObjectId` paired with a multi-field unique index.
- Understand why **structure, field names, BSON types, and field order** affect composite key comparisons.
- Design and map composite keys to Java classes, and query safely with `MongoTemplate`/repositories.
- Identify implications for indexes, upserts, transactions, migrations, and identifier changes.
- Write tests to prevent missed lookups, logical duplicates, or writing to the wrong document.

## 2. Choosing the Right Identification Approach

MongoDB offers several ways to satisfy "each tenant has unique order numbers":

| Design | Illustrative Document | Uniqueness Constraint | Characteristics |
|---|---|---|---|
| Composite `_id` | `{ _id: { tenantId: "acme", orderNo: "ORD-001" } }` | On the full `_id` value | Uses the business key directly as identity; sensitive to BSON structure |
| `ObjectId` + unique compound index | `{ _id: ObjectId(...), tenantId: "acme", orderNo: "ORD-001" }` | Index `{ tenantId: 1, orderNo: 1 }` with `unique: true` | Easier to change business codes; maintains a separate technical key |
| Composite string | `{ _id: "acme:ORD-001" }` | On the `_id` string | Simple for full-key lookups, but requires separator escaping/normalization and loses field structure |

Example of creating a unique index when choosing a separate technical key:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderNo: 1 },
  { unique: true, name: "uq_tenant_order" }
);
```

Setting `unique: true` on a **compound index over regular fields** does not turn `_id` into a composite key. The two designs have different lifecycles, query patterns, and mutability trade-offs for business codes.

**Consider a composite `_id` when:** the key components are stable, always present, compact, normalized, and the application primarily looks up by the full key. **Consider a technical key + unique index when:** business codes may change, simple foreign references are needed, or there are varied lookup paths and external integrations.

Do not cram excessive fields into `_id` just to avoid creating an index. Overly large keys bloat document and index sizes and complicate every path that passes or receives identifiers.

## 3. Physical Structure of Keys in BSON

Run in `mongosh` on a test database:

```javascript
db.orders.insertMany([
  {
    _id: { tenantId: "acme", orderNo: "ORD-001" },
    status: "CREATED"
  },
  {
    _id: { tenantId: "acme", orderNo: "ORD-002" },
    status: "PAID"
  },
  {
    _id: { tenantId: "beta", orderNo: "ORD-001" },
    status: "CREATED"
  }
]);

db.orders.find({}, { _id: 1, status: 1 });
```

These are three documents with distinct keys. `_id` is not merely an abstract "tuple"; it is **a BSON document with exact field names, value types, and field order**:

```text
_id (BSON document)
├── tenantId (BSON string): "acme"
└── orderNo  (BSON string): "ORD-001"
```

Given `{ tenantId: "acme", orderNo: "ORD-001" }`, the following variants **do not have the same BSON structure**:

```javascript
{ orderNo: "ORD-001", tenantId: "acme" } // Reversed field order
{ tenantId: "acme", orderNo: 1 }         // Changed type from string to number
{ tenantId: "acme", orderNo: "ORD-001", region: "VN" } // Extra field
{ tenantId: "acme" }                     // Missing key component
```

Because MongoDB compares nested documents by both values and key–value pair order in equality matching, **never assume two objects with the same set of properties in different order are equivalent key representations for direct lookups**.

### 3.1. Equality Queries on the Full `_id`

```javascript
// Finds ORD-001 for acme
db.orders.findOne({
  _id: { tenantId: "acme", orderNo: "ORD-001" }
});

// Does not match stored _id if field order is reversed
db.orders.findOne({
  _id: { orderNo: "ORD-001", tenantId: "acme" }
});

// Does not match because orderNo component is missing
db.orders.findOne({
  _id: { tenantId: "acme" }
});
```

When matching an **embedded document**, MongoDB requires a matching document structure in which **field order matters**. This is crucial for `findById(...)`, `deleteById(...)`, `replaceOne(...)`, or upserts if the application constructs BSON keys in inconsistent ways.

### 3.2. Querying Individual Components With Dot Notation

When filtering on individual subfields of `_id`, the order of conditions in the query **does not alter semantics** the way full-document equality does:

```javascript
db.orders.findOne({
  "_id.tenantId": "acme",
  "_id.orderNo": "ORD-001"
});

db.orders.findOne({
  "_id.orderNo": "ORD-001",
  "_id.tenantId": "acme"
});

db.orders.find({
  "_id.tenantId": "acme"
});
```

Both of the first two `findOne` queries express predicates on individual subfields and both find the document in the sample dataset. The last query retrieves all orders belonging to tenant `acme`. Dot notation is suitable for partial-key searches, though **dedicated indexes** must be designed if the workload demands high performance.

Do not infer that queries on `_id.tenantId` and `_id.orderNo` are automatically optimized identically to full-`_id` equality lookups. The index on the whole `_id` and a compound index on **component paths** are two distinct things.

### 3.3. Standardizing Field Names, Types, and Order

Define the key contract explicitly:

| Attribute | Example Contract |
|---|---|
| Names and order | `tenantId` first, `orderNo` second |
| BSON types | Both `string`, never `null` |
| Values | Normalize whitespace/case per business rules before writing |
| Required fields | No field may be omitted |
| Extra fields | Never inject `region`, `_class`, or other metadata into the `_id` subdocument |
| Stability | Do not rename, retype, reorder, or change field meaning across upgrades without migration |

**Distinction:** MongoDB cares about **field order inside the BSON document**, not property order inside an external JSON API. Mappers and serializers may emit fields in an order different from source code declarations; always inspect the actual persisted document.

Systems constructing keys across multiple languages (Java, Node.js, Python, etc.) especially need standardized packing and normalization. Never assume two maps containing the same key/value pairs will serialize to the same byte layout or BSON field order across serializers.

## 4. Mapping Composite Identifiers in Spring Data MongoDB

### 4.1. Modeling With an Explicit Key Type

With Java 17+ and a Spring Data MongoDB version supporting record mapping, you can represent the key as a record:

```java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.repository.MongoRepository;

record OrderKey(String tenantId, String orderNo) {
    OrderKey {
        if (tenantId == null || tenantId.isBlank()
                || orderNo == null || orderNo.isBlank()) {
            throw new IllegalArgumentException("Composite key is incomplete");
        }
    }
}

@Document(collection = "orders")
record PurchaseOrder(
    @Id OrderKey id,
    String status,
    Instant createdAt
) {}

interface PurchaseOrderRepository
        extends MongoRepository<PurchaseOrder, OrderKey> {}
```

In this model, `PurchaseOrder.id` is an `OrderKey` object. With standard default mapping, Spring Data converts the key object into a BSON document `_id`. Field names and order after conversion must match the **agreed BSON contract**; verify actual output whenever custom mappings, `@Field`, converters, aliases, or library upgrades are involved.

Do not put `@Id` on each individual component `tenantId` and `orderNo`. There is **only one Java property representing MongoDB's `_id` field**. Never assume two Java fields both annotated with `@Id` will combine automatically into a compound identifier.

Creating and querying via repository:

```java
OrderKey key = new OrderKey("acme", "ORD-003");
PurchaseOrder order = new PurchaseOrder(
    key, "CREATED", Instant.now());

repository.insert(order);

PurchaseOrder loaded = repository.findById(
    new OrderKey("acme", "ORD-003"))
    .orElseThrow();
```

The snippet assumes `repository` is injected into a service. The repository supports `findById`, `existsById`, and `deleteById` for the declared ID type, while match accuracy depends on the **BSON representation** produced by the converter.

### 4.2. Inspecting Raw BSON Instead of Guessing From Java Objects

When using `MongoTemplate`, you can read the document as `org.bson.Document` to verify its structure:

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

Document raw = mongoTemplate.getCollection("orders")
    .find(new Document("_id", new Document("tenantId", "acme")
        .append("orderNo", "ORD-003")))
    .first();

if (raw != null) {
    Document bsonId = raw.get("_id", Document.class);
    System.out.println(bsonId.toJson());
    System.out.println(bsonId.keySet()); // Inspect actual field order
}
```

`getCollection(...)` returns the synchronous driver collection; this raw check is helpful for verifying BSON layout during debugging. In normal application code, use `MongoTemplate`/repositories with domain types to leverage Spring mapping.

**Watch out for `_class`:** Spring Data can write type hints in certain mapping situations. If a type hint or converter alters the key subdocument structure, exact equality matching can break. Do not strip type info globally or customize converters merely to force one query to pass; first inspect raw documents and standardize the mapping contract across all read/write paths.

### 4.3. Querying With `MongoTemplate` and `Criteria`

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

// Find by ID object, passed through Spring Data mapping.
PurchaseOrder order = mongoTemplate.findById(
    new OrderKey("acme", "ORD-003"), PurchaseOrder.class);

// Find by key components; independent of field order
// required for full-_id equality.
Query byParts = Query.query(
    Criteria.where("_id.tenantId").is("acme")
        .and("_id.orderNo").is("ORD-003"));

PurchaseOrder found = mongoTemplate.findOne(
    byParts, PurchaseOrder.class);

// List all orders for a tenant:
Query byTenant = Query.query(
    Criteria.where("_id.tenantId").is("acme"));
var orders = mongoTemplate.find(
    byTenant, PurchaseOrder.class);
```

If mapping uses BSON field names different from Java property names (e.g., `tenantId` mapped to `tenant`), verify the path mapped by `QueryMapper` and the actual query sent to MongoDB. Never mix Java property names and BSON field names without knowing which layer applies mapping.

## 5. Key Lifecycle: Immutability, Insert, Update, Upsert

### 5.1. `_id` Is an Immutable Identifier

MongoDB does not permit updating `_id` directly on an existing document. That includes modifying any component inside an `_id` subdocument:

```javascript
// Valid: modifying a field OUTSIDE _id
db.orders.updateOne(
  { _id: { tenantId: "acme", orderNo: "ORD-001" } },
  { $set: { status: "PAID" } }
);

// Invalid: attempting to modify a component of _id
db.orders.updateOne(
  { "_id.tenantId": "acme", "_id.orderNo": "ORD-001" },
  { $set: { "_id.orderNo": "ORD-900" } }
);
```

If business rules allow editing order numbers or transferring an order to another tenant, a composite `_id` can be inconvenient. Consider `ObjectId` as a technical key plus a unique index for the business key, or design a controlled process to create the new document, update references, and remove the old document. Copy-and-delete is not atomic by default; if multi-document consistency is required, evaluate transactions and a supported topology.

### 5.2. Inserts and Handling Duplicate Keys

```javascript
db.orders.insertOne({
  _id: { tenantId: "acme", orderNo: "ORD-010" },
  status: "CREATED"
});

// Same full _id, same structure: rejected as duplicate key.
db.orders.insertOne({
  _id: { tenantId: "acme", orderNo: "ORD-010" },
  status: "CREATED"
});
```

A duplicate key error (`E11000`) is an important signal when concurrent requests attempt to create the same order. Never implement "check if found, then insert" and expect two separate operations to guarantee uniqueness under concurrency. Rely on the database's unique constraint paired with a designed retry/idempotency strategy.

With `MongoRepository`, `insert(...)` expresses create-only intent; `save(...)` can update/replace the document when an ID is present. Modifying an object and calling `save(...)` risks overwriting state written by another request. For single-field updates, atomic `$set` updates or optimistic locking with `@Version` (when properly configured and tested) are usually safer.

### 5.3. Upserts Must Use the Canonical Key

```javascript
const id = { tenantId: "acme", orderNo: "ORD-020" };

db.orders.updateOne(
  { _id: id },
  {
    $set: { status: "PAID" },
    $setOnInsert: { createdAt: new Date() }
  },
  { upsert: true }
);
```

In this example, `_id` is always constructed with a **fixed BSON field order and types**. Never generate varying key representations based on JSON parameter ordering, map iteration order, or dynamic concatenation. During concurrent upserts, still inspect results, handle duplicate key errors by design, and avoid updates that violate business invariants.

## 6. How Do Composite Identifiers Relate to Indexes?

### 6.1. The Unique Index on `_id` Covers the Full Key Value

MongoDB creates a default index named `_id_` on the `_id` field. With the key:

```javascript
_id: { tenantId: "acme", orderNo: "ORD-001" }
```

the `_id_` index serves equality queries on the **full `_id` value**. Never assume this index is equivalent to a compound index on the two paths:

```javascript
{ "_id.tenantId": 1, "_id.orderNo": 1 }
```

The two indexes have **different key patterns**. Queries filtering on a subset of the key, such as retrieving all orders for a tenant, need execution-plan analysis and may require a separate index.

### 6.2. Indexes for Component-Based Queries

Suppose the workload frequently asks: "What are the most recent orders for tenant `acme`?". Place `createdAt` outside `_id`, then create an index:

```javascript
db.orders.createIndex(
  { "_id.tenantId": 1, createdAt: -1 },
  { name: "ix_tenant_recent_orders" }
);

db.orders.find({ "_id.tenantId": "acme" })
  .sort({ createdAt: -1 })
  .limit(20);
```

For high-frequency queries looking up both components via dot notation, you may consider:

```javascript
db.orders.createIndex(
  { "_id.tenantId": 1, "_id.orderNo": 1 },
  { name: "ix_tenant_order_parts" }
);
```

If every lookup uses full-`_id` equality with canonical BSON, the built-in `_id_` index is already the direct choice; avoid adding extra indexes unless required by your workload. Every index adds storage and write overhead.

### 6.3. Field Order in Compound Indexes Matters Too

A MongoDB compound index has an ordered **key pattern**, for example:

```javascript
{ "_id.tenantId": 1, createdAt: -1 }
```

differs from:

```javascript
{ createdAt: -1, "_id.tenantId": 1 }
```

This order determines index prefix usage, filtering, and sorting. These are **two separate concepts to keep distinct**:

1. Field order **inside the `_id` subdocument** affects full-document equality matching on the key.
2. Field order **in a compound index definition** affects how the database uses the index for queries and sorts.

They may reference the same field names, yet they are completely different mechanisms.

### 6.4. Measure Instead of Guessing

Run `explain("executionStats")` on representative queries:

```javascript
// Full-key equality lookup
db.orders.find({
  _id: { tenantId: "acme", orderNo: "ORD-001" }
}).explain("executionStats");

// Partial-key lookup
db.orders.find({
  "_id.tenantId": "acme"
}).explain("executionStats");

// Tenant lookup sorted by time
db.orders.find({
  "_id.tenantId": "acme"
}).sort({ createdAt: -1 }).explain("executionStats");
```

Inspect `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, execution time, and stages like `IXSCAN`/`COLLSCAN`. A tiny dataset of a few documents rarely reflects production index selection; test with realistic data volume and tenant skew.

## 7. Validation to Protect Key Structure

A major risk with composite `_id`s is different clients sending malformed structures: omitting `orderNo`, setting `null`, sending numbers instead of strings, or injecting unexpected fields. Application-layer validation helps, while a **collection validator** adds database-level defense.

The following creates a **new** collection requiring `_id` to be an object with exactly two non-empty string fields:

```javascript
db.createCollection("ordersValidated", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["_id"],
      properties: {
        _id: {
          bsonType: "object",
          required: ["tenantId", "orderNo"],
          additionalProperties: false,
          properties: {
            tenantId: { bsonType: "string", minLength: 1 },
            orderNo: { bsonType: "string", minLength: 1 }
          }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

This rule applies to `ordersValidated` and does not affect `orders` from earlier examples. For existing collections, use `collMod` with an appropriate strategy for legacy documents. A validator with `validationAction: "error"` rejects invalid writes according to MongoDB validation rules.

**Validator limitation:** `$jsonSchema` cannot enforce **BSON key order**. A subdocument with the exact two fields in reversed order still passes the type and required checks above. You still need consistent serializers/converters and equality tests on raw documents.

If Spring Data mapping writes type hints into the key or normalizes aliases differently, `additionalProperties: false` may reject writes. Lock down the BSON contract first, inspect actual written documents, and only then apply validation.

### 7.1. Normalizing Input at System Boundaries

Suppose an API accepts tenant and order number as two JSON fields:

```json
{
  "tenantId": "acme",
  "orderNo": "ORD-001",
  "status": "CREATED"
}
```

Good practice is:

1. Authenticate and authorize the request's tenant; never trust a client-supplied `tenantId` unchecked.
2. Verify `tenantId` and `orderNo` are present, properly typed, and non-blank.
3. Normalize casing/Unicode/whitespace **when business rules require it**; do not arbitrarily call `toLowerCase()` if codes are case-sensitive.
4. Construct a canonical `OrderKey` using the committed field order and names.
5. Use a single BSON key-writing mechanism across all create/upsert/migration paths.

This validation protects both data integrity and access control: in multi-tenant applications, querying by `orderNo` alone without constraining `tenantId` risks cross-tenant data exposure even when MongoDB identifiers are valid.

## 8. Transactions, Sharding, and Uniqueness Scope

### 8.1. Transactions Do Not Replace Identity Constraints

For single-document inserts or updates, MongoDB provides document-level atomicity. When a business operation spans multiple documents—such as creating an order and decrementing inventory—multi-document transactions may be needed on a supported **replica set or sharded cluster**. A composite `_id` does not create a transaction by itself, nor does it make multi-document writes atomic.

For example, if two tasks concurrently create an order with the same full key, the unique constraint on `_id` remains essential to prevent duplicate writes; transactions are not a substitute for defining uniqueness. In Spring Data, use `MongoTransactionManager` or `ReactiveMongoTransactionManager` matching your access model when transactions are required.

### 8.2. Sharding Requires Separate Consideration of Shard Keys and Uniqueness

On a sharded collection, examine:

- What is the **shard key**? Does it include tenant to route queries cleanly?
- Do queries include suitable shard key predicates to avoid scatter-gather?
- At **what scope** does your MongoDB version/topology enforce uniqueness for `_id` and unique indexes?
- Are hot shards avoided when tenant distribution is skewed or many records share a shard-key prefix?

Specifically, in sharded configurations where `_id` is not the shard key or lacks an appropriate shard-key prefix, `_id` uniqueness enforcement may only be guaranteed **per shard**. The application must ensure cluster-wide uniqueness per business requirements; never assume sharded collections behave identically to unsharded ones. Shard key and unique index rules depend on MongoDB version and sharding mode, so verify the design before deploying.

Changing a composite `_id` or adding key components **after sharding** can make migrations substantially harder, especially if the shard key depends on those fields. Finalize component names, types, and order early.

## 9. Impact on Queries, Aggregations, and Reactive Access

### 9.1. Aggregating by Individual Key Components

Composite identifiers do not block aggregations. Use subfield paths to group by tenant:

```javascript
db.orders.aggregate([
  { $match: { "_id.tenantId": "acme" } },
  {
    $group: {
      _id: "$_id.tenantId",
      orderCount: { $sum: 1 }
    }
  }
]);
```

When a pipeline groups by `"$_id.tenantId"`, `_id` in the **aggregation output** is the grouping key (here the tenant string); it does not alter `_id` in the source documents.

If data contains multiple key shapes, component-based aggregations might still return results even while full-`_id` equality lookups fail—masking modeling bugs. Inspect inputs and raw BSON rather than relying solely on aggregate reports.

### 9.2. Repository Queries by Component

Repositories can declare queries on subfields. For example:

```java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

interface OrderLookupRepository
        extends MongoRepository<PurchaseOrder, OrderKey> {

    @Query("{ '_id.tenantId': ?0 }")
    List<PurchaseOrder> findOrdersForTenant(String tenantId);

    @Query("{ '_id.tenantId': ?0, '_id.orderNo': ?1 }")
    List<PurchaseOrder> findByKeyParts(String tenantId, String orderNo);
}
```

These queries illustrate actual BSON paths. In systems with custom mapping, inspect the exact query sent to MongoDB and its supporting indexes. Never rely on long, hard-to-trace derived method names and assume mapping matches your intent.

### 9.3. Reactive MongoDB Must Enforce the Same Key Contract

`ReactiveMongoRepository<PurchaseOrder, OrderKey>` or `ReactiveMongoTemplate` uses the MongoDB reactive driver. Although APIs return `Mono`/`Flux`, `_id` BSON representation is a **database** requirement independent of reactive vs. synchronous I/O.

If both synchronous and reactive services write to the same collection, both must apply the exact same schema, key names/types/order, and consistent converters. Never use an unordered `Map` in one service and a `record`/POJO in another and assume full-`_id` lookups will match.

## 10. Migrating When Multiple Key Shapes Already Exist

Common changes that introduce inconsistent data:

- Renaming `orderNo` to `orderId` in Java without migrating legacy records.
- Changing `tenantId` from string to number.
- Reordering two fields in a service serializer across versions.
- Adding `region` into `_id` for new data only.
- Switching from `ObjectId` to a document `_id` while keeping old lookup APIs.

Because `_id` is immutable, **you cannot update part of a key in place** like a status field. Migration must be designed at the document level:

1. **Inventory:** sample raw BSON and tally all key shapes and referencing collections.
2. **Define canonical key:** lock down exact names, types, order, and normalization.
3. **Check logical duplicates:** determine whether documents with differing legacy key shapes represent the same business entity.
4. **Execute safely:** create documents with the new key, migrate data/references on a planned schedule, and consider transactions or dual-sync during transition.
5. **Cut over read/write paths:** coordinate deployments so old services stop emitting malformed keys.
6. **Verify and clean up:** reconcile counts, references, queries, and indexes, removing old records only after confirming backups and rollback plans.

Never run bulk `$set` scripts on `_id`; MongoDB will reject them. Avoid migrations without a plan for concurrent writes, which can cause lost updates while both old and new shapes are active.

## 11. Testing Error-Prone Behaviors

### 11.1. Minimal Test Matrix

| Test | Outcome to Verify |
|---|---|
| Insert two documents with same `orderNo` and different `tenantId` | Treated as two distinct identifiers |
| Re-insert same full `_id` with identical structure | Database rejects with duplicate key error |
| Equality query with exact BSON field order | Finds the right document |
| Equality query with reversed field order | Does not match the document stored in original order |
| Dot-notation query with reversed predicate order | Still finds the right data |
| Query by `_id.tenantId` only | Finds orders for that tenant; inspect index plan |
| Send `orderNo` as number instead of string | Rejected by validator/DTO when schema requires string |
| Send key missing a field or containing an extra field | Rejected by validation |
| Call repository `findById` after `insert` | Finds the same document; raw `_id` matches contract |
| Call `save` with existing ID | Verify update behavior and overwrite risks |
| Attempt to update `_id.orderNo` | MongoDB rejects modifying the identifier |
| Query after converter/serialization upgrade | BSON structure of `_id` remains unchanged |

Tests should run against a real MongoDB instance (e.g., an integration test environment with Testcontainers or a test deployment) to observe actual BSON and index behavior rather than merely mocking `MongoRepository`.

### 11.2. Example Checking Raw Field Order in Java

```java
import java.util.List;
import org.bson.Document;

Document canonical = new Document("tenantId", "acme")
    .append("orderNo", "ORD-001");

List<String> expectedOrder = List.of("tenantId", "orderNo");
List<String> actualOrder = List.copyOf(canonical.keySet());

if (!expectedOrder.equals(actualOrder)) {
    throw new IllegalStateException("Unexpected composite ID field order");
}
```

This checks a `Document` constructed in Java. With Spring Data, also inspect **documents actually written to and read back from MongoDB** via the driver; testing a hand-built `Document` does not prove Spring's converter emits the same layout.

### 11.3. Diagnosing Unexpected Empty `findById` Results

Follow this sequence:

1. Use `mongosh` or the raw driver to read an existing document and print the entire `_id`, including key order and BSON types.
2. Compare against the key Java builds: field names, aliases, order, null/missing fields, string/number types, whitespace, and casing.
3. Compare full-`_id` equality `{ _id: {...} }` against dot-notation queries on individual components.
4. Check whether multiple MongoDB URIs, databases, collections, converters, or service versions write to the collection.
5. Run `explain("executionStats")` to distinguish **data mismatch** from **slow queries due to missing indexes**.

Do not rush to raise connection pool limits or timeouts when queries **miss keys due to differing BSON structures**; that is a modeling and serialization bug.

## 12. Practice and Completion Criteria

**Exercise:** A Spring Data MongoDB service stores orders across multiple tenants. Each tenant may use `orderNo = "ORD-001"`, but no tenant may have two orders with the same code.

1. Create the `orders` collection and insert the three documents from Section 3. Verify the `_id_` index exists.
2. Test full-`_id` queries with matching vs. reversed field order, then query using `_id.tenantId` and `_id.orderNo`. Record the differing results.
3. Build `OrderKey` and `PurchaseOrder` in Spring Data, and declare a repository with ID type `OrderKey`. Practice `insert` and `findById`.
4. Read the document back with `MongoTemplate.getCollection(...)` to verify raw `_id` matches the BSON contract.
5. Create an index supporting queries for all orders of a tenant sorted by `createdAt`; evaluate with `explain`.
6. Create a test collection with `$jsonSchema` as in Section 7; test inserting keys missing a component or using wrong types to verify the validator.
7. Attempt to modify an `_id` component and observe the error; outline a migration process if the business needs to edit `orderNo`.
8. Compare against the `ObjectId` + unique compound index `{ tenantId: 1, orderNo: 1 }` option, stating when to prefer each approach.

**Complete** when you can explain the difference between **document equality and dot notation**, maintain consistent **key structure/order/field types**, query accurately via repositories/`MongoTemplate`, choose indexes based on workload, and handle identifier changes in a controlled way.

Composite identifiers are durable only when every layer agrees on **one BSON contract**: component order, field names, data types, normalization, and immutability. This is the foundation for Spring Data MongoDB to access documents reliably in multi-tenant systems or domains with multi-part business keys.
