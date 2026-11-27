# Designing Schema Versioning for Coexisting Document Structures

## 1. Why Does MongoDB Need Schema Versioning?

MongoDB stores data as BSON documents and does not require every document in a collection to share the exact same set of fields. This flexibility lets an application add fields, reshape nested structures, or evolve its data model across releases. However, in long-running systems, a single collection may contain documents written by multiple application versions. If the codebase only understands the latest shape, older records can be misread, lose fields on save, or fall out of query matches.

**Schema versioning** attaches a structural version to documents and defines clear rules for reading, writing, and migrating across versions. The goal is not to make every document identical overnight; the goal is to let multiple structures **coexist safely** throughout deployments, migrations, and backward-compatibility windows.

In the **SPRING_DATA_MONGODB** module, this is a core document design skill directly supporting Spring Data MongoDB connections and mapping, operations through **MongoTemplate** or repositories. Versioning choices affect queries, aggregations, indexes, transactions, reactive access, testing, and performance diagnostics.

After this lesson, you should be able to:

1. Distinguish **schema version**, **application version**, and **optimistic-locking version**.
2. Design a schema identifier field, conventions for legacy documents missing metadata, and read/write contracts.
3. Build a reader that understands multiple schemas yet returns a unified domain model.
4. Plan phased rollouts, rolling deployments, and concurrent-update handling during migrations.
5. Design queries, indexes, validation, migrations, and tests for collections holding mixed structures.

## 2. A Running Example: Evolving an Order Structure

Suppose v1 of an order service stores customer name and phone number as two flat top-level fields:

~~~javascript
// Document in schema v1, illustrated for mongosh.
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  schemaVersion: NumberInt(1),
  customerName: "Lan",
  customerPhone: "0901234567",
  items: [
    { sku: "BOOK-01", quantity: NumberInt(2) }
  ],
  totalMinor: NumberLong("199000"),
  placedAt: ISODate("2025-04-10T08:00:00Z"),
  revision: NumberLong("3")
}
~~~

When the application needs to store richer contact details and an address, the team groups customer details into a nested object. New documents look like this:

~~~javascript
// Document in schema v2; distinct _id so it can coexist with the v1 example.
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  schemaVersion: NumberInt(2),
  customer: {
    fullName: "Minh",
    contact: { phone: "0987654321" },
    address: { city: "Ha Noi" }
  },
  items: [
    { sku: "BOOK-02", quantity: NumberInt(1) }
  ],
  totalMinor: NumberLong("129000"),
  placedAt: ISODate("2025-04-11T08:00:00Z"),
  revision: NumberLong("1")
}
~~~

In this example, **totalMinor** is an integer in the smallest currency unit by system convention; floating-point numbers are not used to illustrate money. The **revision** field tracks write conflicts independently of `schemaVersion`. The **placedAt** field is a BSON Date whose meaning stays identical across both versions.

| Item | Schema v1 | Schema v2 | Impact |
| --- | --- | --- | --- |
| Version | schemaVersion = 1 | schemaVersion = 2 | Reader must branch. |
| Customer name | customerName | customer.fullName | Queries and indexes must handle two paths. |
| Phone number | customerPhone | customer.contact.phone | Mapper must normalize paths. |
| Address | Not yet supported | customer.address | New field needs missing/default rules. |
| Line items | items | items | No conversion needed. |
| Total amount | totalMinor | totalMinor | Keep same type and unit. |
| Creation time | placedAt | placedAt | Keep BSON Date. |
| Write concurrency | revision | revision | Never use schemaVersion in place of revision. |

**Both documents can live in the same collection.** That is the exact transitional state the system must handle safely. Avoid spinning up a brand-new collection for every minor structural change when the data still represents the same business entity and shares queries, authorization, and retention rules.

## 3. Designing the `schemaVersion` Contract

A common convention is a top-level integer **schemaVersion** field in each document:

~~~json
{
  "schemaVersion": 2
}
~~~

Placing `schemaVersion` at the root simplifies queries, migrations, analytics, and raw driver reads. This field describes the **stored data layout**, not the version of Spring Boot, the REST API, or the service emitting the document.

### 3.1. What to Decide Before Adding a Version

| Question | Convention to define |
| --- | --- |
| What does a version mean? | Each value identifies a specific structural and semantic contract. |
| Data type of version? | Use BSON Int32 consistently; avoid mixing String and Number in the same field. |
| Old documents lacking the version field? | Default to v1 only after verifying that all unversioned records match schema v1. |
| When to increment the version? | When a change breaks compatibility with published readers/writers, such as renaming fields or changing data semantics. |
| Increment when adding an optional field? | Depends on contract; backward-compatible additions may not require a new version if old readers ignore unknown fields. |
| Encountering an unknown version? | Fail loudly with a clear error, emit metrics, and define operational handling; never silently fall back to v1. |
| Can versions decrease? | Only if an explicitly defined and tested downgrade procedure exists. |
| Lifecycle of old versions? | Define criteria for stopping reads/writes and when compatibility branches can be removed. |

Some teams name the field **_schemaVersion** or use strings like `"v2"`; what matters is picking **one standard**, applying it consistently, and enforcing it with schema validation. Examples in this lesson use **schemaVersion: 1, 2, 3...**.

### 3.2. Distinguishing Three Kinds of "Version"

- **Schema version** describes the *shape of the document*; v1 has `customerName`, v2 has `customer.fullName`.
- **Application version** identifies the *deployed code release*; a single release can read both v1 and v2 concurrently.
- **Optimistic-lock version** is a *per-document mutation counter* used to detect concurrent overwrites. Spring Data MongoDB commonly uses **@Version** for this.

For example, a v2 document can have `schemaVersion = 2` and `revision = 47` after many updates. Editing the shipping address increments `revision` **without changing `schemaVersion`**.

### 3.3. Never Infer Version Solely from Field Presence

A fragile reader heuristic is "if `customer` exists, it must be v2". During transitions that write both old and new fields, that guess easily breaks. A new field may temporarily exist on a v1 document without satisfying the full v2 contract. Use **schemaVersion as the source of structural truth**, paired with validation to enforce fields and types per version.

For genuine legacy documents missing `schemaVersion`, a compatibility branch may treat missing as v1:

~~~javascript
// Apply only after verifying that documents missing schemaVersion are genuinely v1.
const version = doc.schemaVersion == null ? 1 : doc.schemaVersion;
~~~

Never use this rule to mask a `schemaVersion` field that is `null` or the wrong type in newer data. In tests and monitoring, distinguish **missing**, **null**, **string**, and **int** explicitly.

## 4. Choosing a Multi-Schema Operating Strategy

No single rollout pattern suits every system. Three common options:

| Strategy | How it works | Good fit when | Drawbacks |
| --- | --- | --- | --- |
| **Versioned readers** | Reader selects a mapper by `schemaVersion` without modifying data on read | Large collections needing gradual rollout | Must maintain multiple read branches. |
| **Background migration** | Batch job converts old documents to the new schema | You want to converge on a single schema | Must control write contention, DB load, and rollback. |
| **Dual write / compatibility fields** | Temporarily write both old and new fields in one document | Legacy consumers cannot be upgraded yet | Risk of drift between copies and larger documents. |

The first two combine cleanly: the new app reads both v1 and v2 while the background migration runs; once all records reach v2 and no legacy consumers remain, remove v1 reader code. Dual write is a transitional bridge when un-upgraded consumers truly require it.

Avoid "read v1, immediately rewrite as v2" without strict governance. **Lazy migration on read** can work in narrow cases, but turns a GET into a write, affecting latency, `revision`, auditing, and concurrency conflicts under simultaneous reads.

## 5. Designing the Read Path: Multiple Schemas, One Domain Model

Business logic should not scatter version conditionals everywhere. A cleaner approach translates each stored layout into a **canonical read model**.

~~~mermaid
flowchart TD
    A[(Collection orders: v1 and v2)] --> B[Read BSON Document]
    B --> C{schemaVersion?}
    C -->|Missing or 1| D[Adapter V1]
    C -->|2| E[Adapter V2]
    C -->|Other| F[Unsupported schema error]
    D --> G[Canonical OrderView]
    E --> G
    G --> H[APIs, business logic, reports]
~~~

In our order example, the read model only needs name, phone, and total:

~~~java
public record OrderView(
    String id,
    String customerName,
    String phone,
    long totalMinor
) {}
~~~

### 5.1. Example Reader with MongoTemplate

The example below uses **MongoTemplate** to fetch raw BSON documents via the MongoDB Java Driver and normalize them according to `schemaVersion`. This clearly shows where multi-version translation happens; in larger codebases, extract per-version adapters with dedicated tests.

~~~java
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;

public final class OrderReadService {
    private final MongoTemplate mongoTemplate;

    public OrderReadService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public record OrderView(
        String id, String customerName, String phone, long totalMinor
    ) {}

    public OrderView findById(ObjectId id) {
        // Fetch raw BSON Document to avoid forcing v1 records into the v2 entity.
        Document raw = mongoTemplate.getCollection("orders")
            .find(Filters.eq("_id", id))
            .first();

        if (raw == null) {
            return null;
        }

        Object encodedVersion = raw.get("schemaVersion");
        int schemaVersion;
        if (encodedVersion == null && !raw.containsKey("schemaVersion")) {
            schemaVersion = 1; // Apply only when legacy records missing version are confirmed v1.
        } else if (encodedVersion instanceof Integer number) {
            schemaVersion = number;
        } else {
            throw new IllegalStateException("Invalid schemaVersion for " + id);
        }

        String name;
        String phone;
        switch (schemaVersion) {
            case 1 -> {
                name = raw.getString("customerName");
                phone = raw.getString("customerPhone");
            }
            case 2 -> {
                Document customer = raw.get("customer", Document.class);
                if (customer == null) {
                    throw new IllegalStateException("Missing customer for " + id);
                }
                name = customer.getString("fullName");
                Document contact = customer.get("contact", Document.class);
                phone = contact == null ? null : contact.getString("phone");
            }
            default -> throw new IllegalStateException(
                "Unsupported schemaVersion=" + schemaVersion + " for " + id
            );
        }

        Long totalMinor = raw.getLong("totalMinor");
        if (name == null || totalMinor == null) {
            throw new IllegalStateException("Invalid order data for " + id);
        }
        return new OrderView(id.toHexString(), name, phone, totalMinor);
    }
}
~~~

Design highlights in this snippet:

- The reader accepts only **Int32** for declared `schemaVersion`; wrong types fail loudly instead of silently coercing.
- Documents missing the field default to v1 intentionally. **`schemaVersion: null`** is rejected as malformed data.
- Every branch returns **OrderView**, shielding business logic from MongoDB layout details.
- A v2 document missing `customer` or required fields throws an error instead of returning a "fake valid" object.
- Code reads `totalMinor` as BSON Long matching the data contract. If historical data contains Int32, String, or Decimal128, define explicit checked conversion rather than implicit rounding.

**Never load a v1 document through a v2-only entity and `save` the entire object back.** If the v2 entity lacks `customerName`/`customerPhone`, replacing the whole document wipes out legacy fields. During transitions, scope writes to the specific fields changing or use version-aware adapters.

### 5.2. Can You Still Use Repositories?

Yes. Repositories work cleanly once data is uniform or when each document kind has a clean mapper. However, a **MongoRepository** bound directly to the v2 class will not automatically handle v1 schemas. Your options are:

1. Place a **MongoTemplate**/driver normalization layer in front of reads, while using the repository for clean v2 writes.
2. Configure **Spring Data converters** or polymorphic mapping when version rules are well-defined and broad enough to warrant the abstraction.
3. Split collections if business lifecycles truly diverge, using separate repositories while weighing unified queries, indexes, and data lifecycles.

The **_class** field that Spring Data may persist for Java type mapping **should never be overloaded as a business `schemaVersion`**. Package and class names change during refactoring without the data schema changing; conversely, the same Java class can evolve across releases.

## 6. Designing the Write Path and Deployment Compatibility

During rolling upgrades across multiple instances or services, four roles can coexist:

- **R1:** old readers that only understand v1.
- **R2:** new readers that understand both v1 and v2.
- **W1:** old writers that create/update v1 documents.
- **W2:** new writers that create/update v2 documents.

If W2 starts writing **pure v2** documents while R1 still reads them, R1 will fail even if R2 works flawlessly.

| Deployment state | Reads v1 | Reads v2 | Safe to write pure v2? |
| --- | --- | --- | --- |
| Only R1 active | Yes | No | No. |
| R1 and R2 active together | Yes | Only in R2 | No, if R1 might read newly written documents. |
| All read paths running R2 | Yes | Yes | Yes, after verifying external consumers. |
| All migrated and v1 retired | Per legacy retention policy | Yes | Yes. |

### 6.1. Rolling Out via Expand → Migrate → Contract

~~~mermaid
flowchart LR
    A[Expand: Deploy R2 reading v1 and v2] --> B[Enable W2 in a controlled way]
    B --> C[Migrate: Convert v1 documents in batches]
    C --> D[Reconcile, observe, handle errors]
    D --> E[Contract: Remove v1 write and read paths]
~~~

**Expand — Widen Compatibility**

1. Add `schemaVersion` and the new adapter to the codebase.
2. Deploy R2 across every read path: APIs, batch jobs, reports, event consumers, and admin tools.
3. Run R2 against existing v1 data; W1 can continue writing v1 safely.
4. Enable W2 only after confirming all required consumers handle v2.

If a legacy consumer must continue running, you can temporarily **dual write**:

~~~javascript
{
  schemaVersion: NumberInt(2),
  customerName: "Lan",         // Kept for legacy consumers.
  customerPhone: "0901234567", // Kept for legacy consumers.
  customer: {
    fullName: "Lan",
    contact: { phone: "0901234567" }
  }
}
~~~

Dual write helps legacy consumers only if they **do not reject `schemaVersion = 2`** and still read the compatibility fields properly. All write paths must update both copies inside the **same atomic single-document operation**; updating only one side leaves readers seeing conflicting values. Define which fields are the **source of truth** and when dual write ends.

**Migrate — Convert Data Gradually**

1. Count documents in v1, v2, missing version, and invalid versions.
2. Dry-run on a small slice, verify new reads, and inspect query/index impact.
3. Run batched migrations with durable checkpoints and safe restartability.
4. Throttle write rates to avoid spiking app latency, write load, and replication lag.
5. Monitor remaining v1 counts, write conflicts, and failed documents.

**Contract — Clean Up**

1. Confirm zero active v1 writers remain.
2. Confirm no v1 documents remain in the collection (or isolate and handle documented exceptions).
3. Remove legacy adapters, compatibility fields, and legacy indexes once the rollback window closes.
4. Tighten schema validation to allow only v2 once data and consumers are ready.

Order matters. Never delete the v1 branch just because the new release deployed: base cleanup on **live data**, consumer status, and rollback policies.

## 7. Querying a Collection with Two Coexisting Schemas

Lookups on a shared key like `_id` may not care about schema version. Queries by customer name, however, span two paths.

### 7.1. Compatible Queries

~~~javascript
db.orders.find({
  $or: [
    { schemaVersion: NumberInt(2), "customer.fullName": "Lan" },
    { schemaVersion: NumberInt(1), customerName: "Lan" },
    { schemaVersion: { $exists: false }, customerName: "Lan" }
  ]
});
~~~

The third branch is only needed if legacy documents truly omit `schemaVersion`. If all v1 documents explicitly carry `schemaVersion = 1`, two branches suffice. Business filters like order status, tenant, or date range must apply consistently to every branch.

In Spring Data MongoDB, express the equivalent filter via **Criteria.orOperator**:

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Criteria customerName = new Criteria().orOperator(
    Criteria.where("schemaVersion").is(2)
        .and("customer.fullName").is("Lan"),
    Criteria.where("schemaVersion").is(1)
        .and("customerName").is("Lan"),
    new Criteria().andOperator(
        Criteria.where("schemaVersion").exists(false),
        Criteria.where("customerName").is("Lan")
    )
);

Query query = new Query(customerName);
~~~

This illustrates the **query criteria**, not a full repository method. A repository method derived from a single Java property will not automatically generate these multi-path `$or` branches.

### 7.2. Normalizing Data with Aggregation

When reports need a unified representation, use aggregation to inspect `schemaVersion` and project a canonical path:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      totalMinor: 1,
      placedAt: 1,
      customerNameNormalized: {
        $cond: [
          { $eq: ["$schemaVersion", 2] },
          "$customer.fullName",
          "$customerName"
        ]
      }
    }
  }
]);
~~~

Documents missing a version are treated as v1 here. If the collection holds other versions or malformed records, filter or flag them explicitly before running business reports.

Performance note: the normalized expression is computed during aggregation. Placing a **`$match` on `customerNameNormalized`** after **`$project`** may prevent MongoDB from directly using indexes on the underlying field paths the way an upfront **`$or`** filter can. On large collections, compare execution plans rather than judging solely by pipeline neatness.

### 7.3. Indexes During the Two-Schema Phase

Two distinct customer-name paths may need two indexes:

~~~javascript
db.orders.createIndex({ customerName: 1 });
db.orders.createIndex({ "customer.fullName": 1 });
~~~

If queries always filter by `tenantId`, timestamp, or status, design **compound indexes** matching real query shapes. Do not assume an index on `schemaVersion` alone helps: effectiveness depends on selectivity, version distribution, other predicates, and the query planner.

Evaluate with:

~~~javascript
db.orders.find({
  $or: [
    { schemaVersion: 2, "customer.fullName": "Lan" },
    { schemaVersion: 1, customerName: "Lan" }
  ]
}).explain("executionStats");
~~~

When reading the output, inspect keys/documents scanned, returned count, each `$or` branch, chosen index plans, and execution time. Legacy field indexes are temporary overhead that can be dropped once migration and the rollback window finish.

## 8. Controlled Data Migration

Migration transforms a v1 document into a v2 document **while preserving its business meaning**. Separate three tasks: selecting records to convert, computing the new structure, and writing safely.

### 8.1. Auditing Version Distribution

~~~javascript
// Inspect the actual BSON types stored in schemaVersion.
db.orders.aggregate([
  { $group: {
      _id: { $type: "$schemaVersion" },
      documents: { $sum: 1 }
  }},
  { $sort: { documents: -1 } }
]);

// Count v1 documents, including legacy records missing metadata.
db.orders.countDocuments({
  $or: [
    { schemaVersion: NumberInt(1) },
    { schemaVersion: { $exists: false } }
  ]
});

db.orders.countDocuments({ schemaVersion: NumberInt(2) });
~~~

Grouping by **$type** can reveal **int**, **missing**, **null**, **string**, or unexpected types. Before migrating, audit missing fields, same-named fields with changed semantics, and anomalies such as empty or non-String `customerName` values.

### 8.2. Example Migration Using an Update Pipeline

MongoDB supports **aggregation pipelines inside updates**, executing atomically per document. The example below runs a simple conversion once valid `customerName` and `customerPhone` are verified and **no legacy writers run concurrently**:

~~~javascript
db.orders.updateMany(
  {
    $or: [
      { schemaVersion: NumberInt(1) },
      { schemaVersion: { $exists: false } }
    ],
    customerName: { $type: "string" },
    customerPhone: { $type: "string" }
  },
  [
    {
      $set: {
        customer: {
          fullName: "$customerName",
          contact: { phone: "$customerPhone" }
        },
        schemaVersion: NumberInt(2)
      }
    },
    { $unset: ["customerName", "customerPhone"] }
  ]
);
~~~

This pipeline touches only records matching the filter. Non-conforming documents should be logged and handled by policy rather than silently coerced into v2. Setting **schemaVersion = 2** excludes already-converted documents from subsequent runs, making the migration **idempotent** on converted records.

However, **idempotent does not mean concurrency-safe**. If a user updates `customerName` mid-migration, or a W1 instance writes legacy fields after conversion, updates can be overwritten or produce hybrid structures.

### 8.3. Preventing Lost Updates with a Revision Condition

While the application continues writing live traffic, migrate document by document with a conditional check on **revision** (compare-and-set), or another concurrency protocol agreed upon across all writers.

Example for a v1 document carrying a BSON Long `revision`:

~~~javascript
const id = ObjectId("507f1f77bcf86cd799439011");
const before = db.orders.findOne({ _id: id });

if (before &&
    typeof before.customerName === "string" &&
    typeof before.customerPhone === "string") {
  const result = db.orders.updateOne(
    {
      _id: before._id,
      revision: before.revision,
      $or: [
        { schemaVersion: NumberInt(1) },
        { schemaVersion: { $exists: false } }
      ]
    },
    {
      $set: {
        schemaVersion: NumberInt(2),
        customer: {
          fullName: before.customerName,
          contact: { phone: before.customerPhone }
        }
      },
      $unset: {
        customerName: "",
        customerPhone: ""
      },
      $inc: { revision: NumberLong(1) }
    }
  );

  // matchedCount = 0: data changed concurrently; re-read and recompute migration.
  printjson({ matched: result.matchedCount, modified: result.modifiedCount });
}
~~~

The revision guard protects updates only if **every relevant writer** atomically increments `revision` and follows the same concurrency protocol. If a legacy writer modifies a document without bumping `revision`, the migration cannot detect the conflict through this field. For documents lacking `revision`, initialize the counter first or use a different synchronization mechanism; never assume this snippet handles every legacy record out of the box.

In Spring Data MongoDB, **@Version** provides optimistic locking for framework-managed saves; migrations run via `mongosh`, raw driver calls, or custom updates must enforce the matching revision filter explicitly.

### 8.4. Batched, Resumable Migrations

Across millions of documents, a single collection-wide `updateMany` generates heavy write spikes and cannot be throttled cleanly. A production migration job should:

1. Iterate over a stable key such as **_id** combined with a `schemaVersion` filter; avoid increasing `skip` offsets.
2. Process bounded batches with concurrency caps and pause/resume controls.
3. Record checkpoints plus counts of converted, skipped, malformed, and conflicted documents.
4. On conflict, re-read the latest document and recompute the conversion rather than replaying a stale payload.
5. Measure application latency, write latency, replication lag, and query times after each batch.
6. Support safe re-runs targeting only older versions, alongside error tracking for manual remediation of invalid records.

Never wrap an entire large migration inside **one giant transaction**. Single-document update atomicity normally suffices for reshaping individual documents. If changes span multiple documents or collections with cross-document invariants, design an appropriate consistency protocol or scoped transaction for your MongoDB topology.

## 9. Schema Validation While Multiple Structures Coexist

MongoDB lets you configure validators with **$jsonSchema** to enforce BSON types and required fields. During transition, a validator can allow **v1 or v2** using **oneOf**.

Illustrative validator configuration for a new collection:

~~~javascript
db.createCollection("orders_versioned", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      oneOf: [
        {
          required: ["customerName"],
          properties: {
            schemaVersion: { enum: [1] },
            customerName: { bsonType: "string" }
          }
        },
        {
          required: ["schemaVersion", "customer"],
          properties: {
            schemaVersion: { enum: [2] },
            customer: {
              bsonType: "object",
              required: ["fullName"],
              properties: {
                fullName: { bsonType: "string" },
                contact: { bsonType: "object" }
              }
            }
          }
        }
      ]
    }
  }
});
~~~

The v1 branch permits `schemaVersion = 1` **or an omitted field**, while rejecting any other version value if present. The v2 branch requires `schemaVersion = 2` and a `customer` object containing `fullName`. Shared fields are omitted here to focus on versioning; production validators should also cover **items**, **totalMinor**, **placedAt**, **revision** type, optional fields, and dual-write layouts if used.

For existing collections, update validators via **collMod**, choosing **validationLevel** and **validationAction** intentionally. Do not tighten rules to v2-only while v1 records are still updated. Validators prevent invalid writes going forward; they **do not automatically migrate existing stored documents**.

Another pitfall is deploying an overly strict validator that breaks W1 writers during a rolling deployment. Roll out compatible validation first, monitor validation errors, and tighten constraints only after migration completes.

## 10. Mapping with Spring Data MongoDB

The v2 storage class can be expressed cleanly with annotations:

~~~java
import java.time.Instant;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderV2(
    @Id ObjectId id,
    int schemaVersion,
    Customer customer,
    List<LineItem> items,
    long totalMinor,
    Instant placedAt,
    @Version Long revision
) {
    public record Customer(String fullName, Contact contact) {}
    public record Contact(String phone) {}
    public record LineItem(String sku, int quantity) {}
}
~~~

In this model, **schemaVersion** is a normal data property explicitly set to **2** when creating new documents; **revision** powers Spring Data optimistic locking. The two fields are unrelated numerically and cannot substitute for each other.

A repository declared for `OrderV2` provides standard CRUD operations, but **does not automatically adapt v1 documents into v2**:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderV2Repository
        extends MongoRepository<OrderV2, ObjectId> {
}
~~~

While mixed schemas coexist in the collection, avoid calling `findAll` on this repository and assuming every record is v2. Scope queries by version or place a compatibility reader layer in front.

### 10.1. When to Use Custom Converters?

**ReadingConverter** and **WritingConverter** can centralize translation inside Spring Data's mapping layer, especially when many repositories and services share identical rules. Still, any converter must specify clearly:

- Which field identifies the schema version.
- How legacy records missing fields are handled.
- Whether it returns an immutable read model safe against accidental field loss on save.
- Whether unknown versions throw errors or route to quarantine handling.
- Which code paths read via mapping converters versus raw BSON.

Converters are an implementation mechanism; schema and compatibility policies must still be designed independently. If only a few queries require conversion, an explicit adapter like the `MongoTemplate` example can be easier to maintain.

### 10.2. Reactive Access

With **ReactiveMongoTemplate** or reactive repositories, versioning principles remain identical. Readers must inspect the schema of emitted documents, performing normalization with non-blocking transformations in the reactive pipeline. If a separate background migration job runs concurrently, throttle its read/write rate so it does not starve reactive application traffic.

Never execute blocking operations inside Reactor's **map** just to look up extra fields during conversion. If external lookups are required, build an appropriate asynchronous pipeline and evaluate consistency.

## 11. Common Schema Changes and How to Evaluate Them

| Change type | Example | Compatible with old readers? | What to verify |
| --- | --- | --- | --- |
| Add optional field | add `customer.address` | Usually yes, if readers ignore unknown fields | Defaults, missing/null handling, validator. |
| Add required field | add `customer.country` | Not guaranteed | Backfill, creation rules, validation. |
| Rename field | `customerName` → `customer.fullName` | Usually no | Adapters, queries, indexes, API payloads. |
| Change data type | String → BSON Date | Not guaranteed | Parsing, timezone, range queries, indexes, bad inputs. |
| Change unit | whole VND → minor cents | No | Unit contracts, precision, conversion rules. |
| Split one document into multiple collections | order → order + history | Model-dependent | Transactions, references, combined queries. |
| Merge fields | `firstName` + `lastName` → `fullName` | Risk of information loss | Join/split rules, search, rollback. |
| Change state meaning | `status = 1` from "new" to "approved" | No | Semantic migration, not just type mapping. |

A schema version is meaningful because it binds to a **semantic contract**. Keeping the exact same field name while silently altering its unit or meaning without bumping the version is often far more dangerous than an obvious structural change.

## 12. Testing a Multi-Version System

Test suites should cover sample v1 and v2 documents alongside malformed edge cases. Testing against real MongoDB persistence catches mapping issues that pure in-memory Java unit tests miss.

| Case | Expectation |
| --- | --- |
| Read v1 document with `schemaVersion = 1` | Returns canonical `OrderView` with correct name, phone, total. |
| Read legacy document missing `schemaVersion` | Reads as v1 only when matching confirmed legacy policy. |
| Read v2 document | Returns semantically equivalent `OrderView` to v1. |
| `schemaVersion = 3` when reader supports 1 and 2 | Emits clear error/metric; never silently treated as v1. |
| `schemaVersion` is String, null, or Double | Flagged as contract-violating data. |
| V2 missing `customer.fullName` | Does not fabricate valid data; handled per data-quality policy. |
| Convert v1 to v2 and read back | Business values remain intact. |
| Run migration a second time | Leaves already-converted documents untouched. |
| Two writers modify same document concurrently | Conflict detected when revision is used properly. |
| Query by customer name and date range | Matches both v1 and v2 and uses expected indexes. |
| Halt rollout and roll back application | Previous release still reads data within committed compatibility scope. |

A valuable technique is **contract testing**: given identical business inputs, the v1 and v2 adapters must yield identical **OrderView** instances. Verify both values and real BSON types: `ObjectId`, `Int32`, `Long`, `Date`, and `Decimal128` where used.

## 13. Observability and Performance Diagnostics During Transition

Maintaining two schemas carries measurable operational overhead:

1. **Version distribution:** counts by `schemaVersion`, missing, and invalid types.
2. **Migration progress:** remaining v1 count, converted count, skipped count, and error/conflict count.
3. **Read latency:** mapper branching cost, multi-branch queries, and normalization pipelines.
4. **Query performance:** track `executionStats`, index scans, and document scans across both field paths.
5. **Write overhead:** temporary dual-write fields, extra indexes, replication volume, and document sizes.
6. **Compatibility errors:** unknown schema versions, missing required fields, converter failures, validator rejections, and optimistic-locking conflicts.

Example report of version counts distinguishing missing fields:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        $cond: [
          { $eq: [{ $type: "$schemaVersion" }, "missing"] },
          "legacy-missing",
          "$schemaVersion"
        ]
      },
      documents: { $sum: 1 }
    }
  },
  { $sort: { documents: -1 } }
]);
~~~

On large collections, avoid running full-collection scans via aggregation too frequently during peak hours just for dashboards. Track progress from migration batches, write-path metrics, or off-peak scheduled audits.

## 14. Rollback and Criteria for Retiring Legacy Schemas

Rollback is part of schema version design, not an afterthought during an incident. Once a release writes **pure v2** documents, reverting to **R1** code that cannot read v2 fails even if the code deployment rolls back cleanly.

A rollback plan must answer:

- Can the fallback application release read v2 documents?
- Are legacy compatibility fields still dual-written or already dropped?
- Can v1 semantics be reconstructed from v2 without losing information?
- Do snapshots/backups and recovery procedures exist if a migration corrupts data?
- After rolling back, which writers are allowed to emit each schema?

Retire v1 support only when there is evidence that **all required consumers read v2**, **no writers emit v1**, **migration is reconciled**, and **the rollback window has closed**. Only then drop v1 indexes and converters to cut maintenance burden.

## 15. Self-Check Practice

### Exercise 1: Auditing Coexisting Versions

Suppose a collection holds these documents:

~~~javascript
db.orders_lab.insertMany([
  { customerName: "Lan", totalMinor: NumberLong("10000") },
  { schemaVersion: NumberInt(1), customerName: "Minh",
    totalMinor: NumberLong("20000") },
  { schemaVersion: NumberInt(2),
    customer: { fullName: "An", contact: { phone: "0900000000" } },
    totalMinor: NumberLong("30000") },
  { schemaVersion: "2", customer: { fullName: "Ha" },
    totalMinor: NumberLong("40000") }
]);
~~~

Identify the counts of v1, v2, and invalid documents under the Int32 `schemaVersion` contract. Write a query matching customer name `"Lan"` or `"An"` without matching documents with an invalid version type.

**Hint:** the first document is unversioned legacy (treat as v1 only if verified); the second is v1; the third is v2; the last has a String `schemaVersion` and must be flagged as malformed data. Never accept String `"2"` as a valid v2 branch.

### Exercise 2: Planning a Safe Rollout

A system has three instances: one instance only reads v1, while two instances read v1 and v2. Product wants to turn on v2 writes immediately. Choose a rollout order that avoids breaking the old instance.

**Hint:** upgrade the final instance to a compatible reader first; verify dependent jobs and services; then enable v2 writes. If an old reader truly cannot be upgraded, evaluate whether dual writes satisfy that reader and update both field groups atomically in one write.

### Exercise 3: Migration Under Concurrent Updates

A job reads `customerName = "Lan"` from a v1 document. Before the job writes v2, the API updates the name to `"Lan Anh"`. What happens if the job updates by `_id` without checking `revision`?

**Answer:** the job can overwrite the document using stale data and set `customer.fullName = "Lan"`, losing the newer update. Every writer must honor the revision/concurrency condition or an equivalent consistency protocol; on mismatch, the job re-reads and transforms the fresh state.

### Exercise 4: Index Design

An API searches orders by customer name, filters by placement date range, and supports both v1 and v2. Propose queries, indexes, and how to measure them.

**Hint:** use compatible branches for `customerName` and `customer.fullName` combined with `placedAt`; inspect both paths with **`explain("executionStats")`**, evaluate compound indexes on real data, and drop the v1 index only after no query relies on it.

## 16. Summary of Design Principles

- **Store schema version in documents and keep each version's contract explicit.** Versions reflect data layout and meaning, not Java class names.
- **Read new before writing new.** Deploy readers supporting both v1 and v2 before writers produce pure v2.
- **Normalize at the persistence boundary.** Mappers/adapters translate multiple BSON layouts into one canonical domain model.
- **Make migrations verifiable and safely resumable.** Manage batches, checkpoints, malformed records, and write conflicts.
- **Tune queries during dual-schema periods.** Measure indexes, aggregations, dual-write cost, and real latency.
- **Retire compatibility based on evidence.** Remove legacy schemas only when all consumers, data reconciliation, and rollback windows permit.

Mastering schema versioning enables **SPRING_DATA_MONGODB** services to evolve document structures continuously while keeping Spring Data MongoDB, `MongoTemplate`, repositories, and data pipelines stable.
