# Choosing Stable IDs and Handling Data Imported From External Systems

## 1. The Identification Problem in Spring Data MongoDB

In the **Identity and State** chapter of **Spring Data MongoDB**, an ID is not merely a field for looking up documents. An ID is also the contract enabling the application to recognize **the same entity across repeated updates, imports, synchronizations, and error recoveries**.

For example, a sales system imports a product catalog from an ERP. The ERP sends product code `00042` today, then sends code `00042` again tomorrow with a new title. If the application generates a random `ObjectId` on each import without source-identity rules, a single product can split into multiple documents. Conversely, if the product name is used as the ID, renaming the product gets misinterpreted as a brand-new entity.

A solid design must answer:

1. Which ID serves as the **stable internal identifier** in MongoDB?
2. Which key identifies the same record when sent again by an **external system**?
3. Must external IDs be scoped by **source** or **tenant**?
4. What happens when records arrive duplicated, out of order, modified, or deleted?
5. How do you prevent duplicates, handle race conditions, and re-run imports safely without corrupting data?

Examples use Java 17+, Spring Boot 3.x, and Spring Data MongoDB 4.x with `MongoTemplate`/`MongoRepository`. Exact behavior should be verified against your project's library and MongoDB versions.

## 2. Distinguishing Types of Identifiers

| Concept | Example | Role | Should It Change? |
|---|---|---|---|
| MongoDB `_id` | BSON ObjectId or string `ext.ERP.00042` | Unique key of **one document in a collection** | Immutable for the document's lifetime |
| Internal application ID | `prd_8c62...` | Stable identifier used within your own system | Avoid changing; requires migration if mandatory |
| External system ID | ERP: `00042` | Locates the same source record across imports | Treated as data governed by the source contract |
| Composite source + external ID key | (`ERP`, `00042`) | Distinguishes ERP `00042` from CRM `00042` | Stable within the source namespace |
| Business key | SKU `BOTTLE-500-BLUE` | Used for lookups or business rules | Can change due to business policies |
| Event ID / revision | `evt-312`, revision `17` | Identifies a specific event emission or change order | Does not replace entity identity |

Principles to remember:

- **Entity IDs must be stable.** Names, prices, statuses, addresses, and many business keys can change; they are unsuitable as `_id` without an immutability guarantee.
- **External IDs are only unique within the scope committed by the source.** Two systems may issue the same `externalId`; even inside one multi-tenant system, you may need (`tenantId`, `sourceSystem`, `externalId`).
- **Never assume external IDs are always numeric.** Codes `"00042"` and `"42"` can represent two different records; converting `String` to `long` strips leading zeros.
- **Do not use personal data as `_id`** without an explicit requirement. Emails, phone numbers, and display names can change, carry sensitive data, or be guessable.
- **ID and revision solve different problems:** ID answers *who is this?*, while revision answers *which state is newer?*

### Is ObjectId the Only Default Option?

MongoDB supports multiple BSON types for `_id`, provided values meet identifier constraints. **ObjectId** is convenient because the MongoDB driver can generate new IDs quickly; an ObjectId is 12 bytes and embeds a timestamp component. However, that timestamp is not a reliable business timestamp, nor is ObjectId a strict global ordering mechanism for all events.

Applications can also use UUIDs or string IDs. What matters is not whether "ObjectId or UUID is always better", but whether the ID is **unique, stable, easy to reference, and compatible with integration contracts**.

## 3. Choosing Between Internal IDs and Source-Derived IDs

Three common approaches:

| Option | Storage Pattern | Advantages | Risks / Considerations |
|---|---|---|---|
| MongoDB-generated internal ID | `_id: ObjectId(...)`, plus `sourceSystem` and `externalId` fields | Independent of source key format; suitable when one entity merges data from multiple sources | Requires a unique index on the external key and lookup/upsert logic to prevent duplicates |
| Application-generated internal ID | `_id: "prd_..."`, with separate source mapping | Convenient when APIs/public models need long-lived independent IDs | ID must be allocated exactly once; requires maintaining mapping tables/collections |
| Deterministic source-derived ID | `_id: encode(sourceSystem, externalId)` | Re-importing the same record yields the exact same `_id`, convenient for idempotency | Must define collision-free encoding, clear namespaces, and handling if the source changes/reuses IDs |

**Prefer an internal ID independent of the source** when an entity can merge from multiple providers, source keys can be reassigned, or the system might replace its ERP/CRM. When data is a *projection* mirroring a single source record, a source-namespaced derived ID is simple and practical.

Never use naive string concatenation like `source + ":" + externalId` without checking collisions. For instance, (`A:B`, `C`) and (`A`, `B:C`) both yield `A:B:C`. Choose an unambiguous length-prefixed/escaping format or encode each component separately.

## 4. Mapping IDs With Spring Data MongoDB

### 4.1. `@Id` and ObjectId Conversion Behavior

A common entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public class Product {
    @Id
    private String id;
    private String name;

    public Product() {}
    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}
~~~

`@Id` maps the `id` property to BSON `_id`. In Spring Data MongoDB, `String` IDs are commonly converted into BSON `ObjectId` **if the value is validly convertible**. String values that cannot convert to ObjectId remain stored as BSON String. Without controlling this rule, two Java `String` IDs can end up stored with different BSON types.

For example, a 24-character hex string converts to ObjectId under `@Id String`, whereas `"p-42"` is not a valid ObjectId. Queries via the raw Java Driver must supply the exact actual BSON type.

### 4.2. `@MongoId` to Preserve `_id` as BSON String

When the system selects internal string IDs, specify the storage type explicitly:

~~~java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "external_products")
public record ExternalProduct(
        @MongoId(FieldType.STRING) String id,
        String sourceSystem,
        String externalId,
        long sourceRevision,
        String title,
        boolean deleted) {
}
~~~

`@MongoId(FieldType.STRING)` mandates handling the key as BSON String, even if its contents resemble an ObjectId. When using `MongoTemplate` with `ExternalProduct.class`, the mapping knows `id` corresponds to `_id`.

If you want true `ObjectId` in Java, declare the ID as `org.bson.types.ObjectId`. Standardize the ID type before bulk data exists; **changing `_id` type is a migration**, not just swapping an annotation.

### 4.3. `_id` Should Never Be Updated

MongoDB treats `_id` as an immutable document identifier. When a key must change, plan a controlled flow to create a document with the new ID, update references, and retire the old ID. Never expect `new Update().set("_id", ...)` to work like a normal field rename.

When a source system renumbers a record, it is usually better to **keep the internal ID intact and update the external-key mapping/alias**. That preserves references from orders, transactions, and related collections.

## 5. Defining the Ingestion Data Contract

Before writing an importer, agree on the source fields:

~~~json
{
  "sourceSystem": "ERP",
  "externalId": "00042",
  "revision": 17,
  "title": "Water Bottle 500 ml",
  "deleted": false
}
~~~

This is an illustrative payload; real sources might omit `revision` or use different field names.

The ingestion contract should specify:

1. **Namespace:** Which system does `ERP` identify, and is `tenantId`/branch code required?
2. **Identity:** Is `externalId` sensitive to case, whitespace, or leading zeros, and can it be reused after deletion?
3. **Versioning:** Does `revision` increase monotonically per `externalId`, and does it cover deletions?
4. **Event semantics:** Does each record carry full state (*snapshot*) or only field-level changes (*delta*)?
5. **Null/missing fields:** Does `null` mean clear the value, omitted, or unknown?
6. **Deletions:** Do deleted records emit delete events/tombstones, or is periodic reconciliation needed?
7. **Replayability:** If a job crashes after writing data but before checkpointing, can the same event be re-ingested safely?

Do not automatically `trim()`, lowercase, or parse external IDs as numbers unless the contract defines that normalization. `"ab-1"` may differ from `"AB-1"`, and `"00042"` may differ from `"42"`. If the source allows aliases, manage and test those rules separately.

## 6. What Does a Safe Ingestion Pipeline Look Like?

~~~mermaid
flowchart TD
    A["Receive data from API/file/queue"] --> B["Validate schema + namespace + externalId"]
    B --> C["Determine stable entity key"]
    C --> D{"Monotonically increasing revision from source?"}
    D -->|"Yes"| E["Conditional write only if revision is newer"]
    D -->|"No"| F["Use controlled snapshots, source cursors, and reconciliation"]
    E --> G["Unique index guards duplicate IDs"]
    F --> G
    G --> H["Write succeeds or skips duplicate/stale event"]
    H --> I["Checkpoint after durable write"]
    I --> J["Metrics, retries, and periodic reconciliation"]
~~~

Guarantees to separate clearly:

- **Entity uniqueness:** each external key maps to at most one internal document. Solved via `_id`/unique index and identity rules.
- **Retry idempotency:** processing the same event multiple times does not corrupt the final result. Solved via stable keys and revision/event ID checks.
- **No overwriting newer state:** late-arriving old events never regress data to an older state. Solved via trustworthy ordered revisions and conditional updates.
- **No lost events:** after network/worker failures, events can replay from checkpoints, outboxes, or source systems. Solved via durable event pipelines and reconciliation.

A unique index only solves **duplicate creation**; it does not prevent an older event from overwriting a newer state. Likewise, Spring Data's `@Version` serves optimistic locking for internal application writes; it does not carry the meaning of *ERP revision*. Both version concepts can coexist, but their roles must never be swapped.

## 7. Implementation Pattern With `MongoTemplate`: Deterministic ID and Revision

Suppose the requirement is simply building **one internal projection per ERP record**. We derive a deterministic ID from (`sourceSystem`, `externalId`). To avoid delimiter collisions, URL-safe Base64 encode each string and join them with a dot (dots do not appear in the URL-safe Base64 alphabet).

### 7.1. Storage and Event Models

Use the `ExternalProduct` record defined in Section 4.2. Event model:

~~~java
package com.example.integration;

public record ProductChanged(
        String sourceSystem,
        String externalId,
        long revision,
        String title,
        boolean deleted) {
}
~~~

`sourceSystem` and `externalId` follow the source contract verbatim. `revision` is assumed to be **monotonically increasing per identity**; that assumption is critical to the logic below.

### 7.2. Deterministic ID Generator

~~~java
package com.example.integration;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class ExternalKeys {
    private ExternalKeys() {}

    public static String productId(String sourceSystem, String externalId) {
        if (sourceSystem == null || sourceSystem.isBlank()
                || externalId == null || externalId.isEmpty()) {
            throw new IllegalArgumentException("Missing source identifier key");
        }

        Base64.Encoder encoder = Base64.getUrlEncoder().withoutPadding();
        String a = encoder.encodeToString(
                sourceSystem.getBytes(StandardCharsets.UTF_8));
        String b = encoder.encodeToString(
                externalId.getBytes(StandardCharsets.UTF_8));
        return "ext." + a + "." + b;
    }
}
~~~

Given the same key pair, this function always produces the same ID. Base64 encoding here is **not security encryption**; anyone can decode the source and external ID. If sensitive IDs must be hidden or length-bounded, pick an internal ID/mapping collection strategy or a hash function with an explicit collision policy. Source names, ID length, and canonicalization rules must be locked down in a contract; changing encoding rules later generates new IDs.

### 7.3. Safe Import Against Duplicate or Out-of-Order Events

First ensure `ExternalProduct` is in the same package or imported from where the entity lives. The example below assumes `ExternalProduct` resides in `com.example.integration` matching Section 4.2.

~~~java
package com.example.integration;

import com.mongodb.client.result.UpdateResult;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Component;

@Component
public class ExternalProductImporter {
    private final MongoTemplate mongo;

    public ExternalProductImporter(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public void apply(ProductChanged event) {
        validate(event);
        String id = ExternalKeys.productId(
                event.sourceSystem(), event.externalId());

        Query onlyNewer = Query.query(
                Criteria.where("id").is(id)
                        .and("sourceRevision").lt(event.revision()));
        Update changes = new Update()
                .set("sourceRevision", event.revision())
                .set("title", event.title())
                .set("deleted", event.deleted());

        UpdateResult changed = mongo.updateFirst(
                onlyNewer, changes, ExternalProduct.class);
        if (changed.getMatchedCount() == 1) {
            return;
        }

        // No matching record: either does not exist yet,
        // or event is duplicate/stale.
        try {
            mongo.insert(new ExternalProduct(
                    id, event.sourceSystem(), event.externalId(),
                    event.revision(), event.title(), event.deleted()));
        } catch (DuplicateKeyException duplicate) {
            ExternalProduct current =
                    mongo.findById(id, ExternalProduct.class);
            if (current == null
                    || !current.sourceSystem().equals(event.sourceSystem())
                    || !current.externalId().equals(event.externalId())) {
                // May be an unrelated unique index conflict:
                // rethrow instead of silently ignoring.
                throw duplicate;
            }
            // If another worker just inserted or updated, only write
            // if this event's revision is strictly newer.
            mongo.updateFirst(onlyNewer, changes, ExternalProduct.class);
        }
    }

    private static void validate(ProductChanged event) {
        if (event == null
                || event.sourceSystem() == null
                || event.sourceSystem().isBlank()
                || event.externalId() == null
                || event.externalId().isEmpty()
                || event.revision() < 0
                || (!event.deleted()
                        && (event.title() == null
                                || event.title().isBlank()))) {
            throw new IllegalArgumentException("Invalid source event");
        }
    }
}
~~~

Explanation:

1. When the document already exists with `sourceRevision < incoming.revision`, `updateFirst` applies the new state in **one atomic document operation**.
2. When no document exists yet, the importer attempts `insert` with the deterministic `_id`.
3. If another worker concurrently created the document with the same `_id`, MongoDB raises a duplicate key error. The importer verifies identity and **retries the conditional update once**.
4. If the event arrives with an equal or lower revision, the update fails to match and the duplicate insert leaves the existing document untouched.
5. `deleted = true` acts as a **versioned tombstone**: retaining the deleted marker stops stale events from resurrecting pre-deletion state.

For instance, if events arrive in order `v17 → v15 → v17 → v18 (deleted)`, the final state must be v18 with `deleted=true`. A late v16 event cannot reactivate the product. If the source **reuses the same externalId for a different entity**, incorporate lifecycle/generation into the key; revision alone may not suffice.

**Pattern limitations:** This illustrates handling snapshot events with monotonically increasing revisions, not a full production importer. Failures can occur during the second attempt; you still need bounded retries, error classification, post-write checkpoints, event queues/change streams, and monitoring. If events carry deltas (e.g., "add 3"), you cannot replace them with full `set` updates as above; you need event IDs and separate idempotency tracking.

### 7.4. Repository for Reading by Identity

~~~java
package com.example.integration;

import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ExternalProductRepository
        extends MongoRepository<ExternalProduct, String> {

    Optional<ExternalProduct> findBySourceSystemAndExternalId(
            String sourceSystem, String externalId);
}
~~~

The repository enables reading the entity post-import. Using property names `sourceSystem` and `externalId`, Spring Data builds criteria per entity mapping. It **does not enforce uniqueness automatically** if the database lacks a unique index; declaring `Optional` does not create a unique constraint either.

## 8. Unique Indexes and Multi-Source Design

MongoDB provides a default unique index on `_id`. When storing a random internal ID while keeping external keys separate, also protect uniqueness of the source/key pair:

~~~javascript
db.external_products.createIndex(
  { sourceSystem: 1, externalId: 1 },
  { unique: true, name: "uq_source_external" }
);
~~~

If each tenant has its own namespace, consider indexing:

~~~javascript
db.external_products.createIndex(
  { tenantId: 1, sourceSystem: 1, externalId: 1 },
  { unique: true, name: "uq_tenant_source_external" }
);
~~~

Use only the variant matching your actual data model. Before creating a unique index on a populated collection, **inspect and resolve existing duplicates**, and ensure required fields are written consistently. A unique index cannot heal records whose identity has already split.

Another option is metadata annotations:

~~~java
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "external_products")
@CompoundIndex(
    name = "uq_source_external",
    def = "{ 'sourceSystem': 1, 'externalId': 1 }",
    unique = true)
public class ImportedProductIndexModel {
    // Only illustrates index annotations, does not replace the entity in Section 7.
}
~~~

Placing an annotation on a model does not mean the index will be created automatically in production: Spring Data MongoDB index auto-creation depends on configuration, and in practice indexes are usually managed via supervised migrations/deployments. This annotation example **only illustrates index definition** and is not a recommendation to create a second entity for the same collection in a real project.

With a **deterministic ID** as in Section 7, unique `_id` already blocks creating two documents with the same ID. A compound unique index remains valuable to protect the (`sourceSystem`, `externalId`) contract against alternate write paths or future `_id` derivation changes. Changing indexes, changing namespaces, or adding tenants requires planning migration for existing data.

## 9. Complex Ingestion Scenarios

### 9.1. Sources Without Reliable Revisions

Not every API supplies monotonically increasing revisions. `updatedAt` timestamps from multiple servers can suffer clock skew, identical timestamps, or delayed updates. Nor can you infer true order solely from when **a worker received the event**.

Approaches:

- Fetch the **latest snapshot** directly from the source and resync in a controlled manner; never apply stale events as if they were the latest state.
- Use source-provided cursors/sequence numbers and serialize processing per identity.
- For pipelines capable of full reloads, track sync markers and perform **periodic reconciliation** to detect missing or deleted records.
- If a source provides no ordering guarantees, document consistency limits clearly rather than claiming out-of-order handling is solved.

### 9.2. Deletions and Late-Arriving Events

If you physically delete a document immediately upon a delete event, a late-arriving older update event can recreate it. Tombstones preserve `_id`, revision, and deletion status to prevent unintended resurrection. Purging tombstones must rely on **event retention windows, watermarks, and ID-reuse policies**, rather than deleting after an arbitrary timeout.

### 9.3. One Entity Appearing Across Multiple Systems

Customer `crm:123` and `erp:00042` may be the same person. However, this is an **entity resolution** problem and cannot be solved simply because two records share an email or name.

Use a durable internal ID paired with a mapping/alias collection:

~~~json
{
  "_id": "person-7a91",
  "identities": [
    { "sourceSystem": "CRM", "externalId": "123" },
    { "sourceSystem": "ERP", "externalId": "00042" }
  ]
}
~~~

This is a conceptual model. When multiple workers attach aliases, protect uniqueness of each external key, support merges/splits, and update downstream references. For high-cardinality aliases or dedicated per-key unique indexes, an independent mapping collection is often easier to manage. Never auto-merge users solely by mutable or non-unique fields like name/email.

### 9.4. Bulk Imports and Backfills

For millions of records, issuing one network command per record is slow. You can use `MongoTemplate.bulkOps(...)` or driver bulk writes to batch updates/inserts, while preserving:

- deterministic IDs or unique constraints;
- revision predicates blocking stale backfills from overwriting newer events;
- retries and per-operation/batch `DuplicateKeyException` handling;
- checkpoints aligned with durably acknowledged batches;
- bounded batch sizes, memory, and throughput to avoid overwhelming the source or cluster.

Bulk writes are **not automatically an atomic transaction across the whole batch**; when part of a batch fails, inspect individual operation results and support replay. For large backfills, shard batches by source, key, and load, measuring both server metrics and job duration.

### 9.5. Security, Authorization, and Sensitive Data

Never expose sensitive information merely because it appears in an ID or payload. For multi-tenant data, **enforce tenant checks at the access boundary**; knowing a valid ID does not authorize a caller to read the document. Avoid writing payloads containing emails or addresses into error logs, dead-letter queues, or unnecessary secondary indexes.

If a business key changes due to new rules, never quietly mutate `_id`. Plan migrations, aliases/redirects, and historical reference testing. Multi-document updates may require transactions when maintaining cross-document invariants; for rebuildable read models, eventual sync and reconciliation may be more suitable.

## 10. Testing Re-Ingestion and Stability

A valuable test suite uses a real MongoDB instance (e.g., via Testcontainers) to verify BSON, unique indexes, and concurrency races. `@DataMongoTest` focuses on the Spring Data MongoDB layer; this test slice does not provide a MongoDB server on its own.

| Scenario | Expected Result |
|---|---|
Import (`ERP`, `00042`) twice with the same revision | Single document; final content unchanged |
Import `v17` then `v15` | Keeps `v17` data |
Import `v17` twice then `v18` | Ends on `v18` |
Two workers import the same identity on an empty collection | No duplicate documents; newer revision wins |
Import `ERP:00042` and `CRM:00042` | Two separate identities unless a merge rule exists |
Import `"00042"` and `"42"` | Not merged if the source treats them as distinct IDs |
Import v19 marked deleted, then receive v18 update | Remains deleted at v19 |
Restart job after write but before checkpoint | Replays without creating duplicates or regressing revisions |
External ID changes for the same domain entity | Internal ID remains stable with managed mapping/aliases |
Changing `_id` String/ObjectId type | Tests expose BSON type difference and require migration |

You can inspect records directly in the MongoDB shell:

~~~javascript
db.external_products.find(
  { sourceSystem: "ERP", externalId: "00042" },
  { _id: 1, sourceRevision: 1, title: 1, deleted: 1 }
);
~~~

With proper indexes in place, lookups by source/ID pair have an efficient access path. Run `explain("executionStats")` in an appropriate environment to confirm the winning plan and keys/documents examined, especially before rolling out large imports or backfills.

Operational metrics to monitor:

- Events received, applied, skipped as duplicate/stale, and failed validation.
- Duplicate-key exception rate under multi-worker concurrency and retry counts.
- Lag between the latest source version and the stored projection.
- Duplicate-identity documents detected during reconciliation, orphaned records, and backfill duration.
- Ingestion rate, write ops, connection pool utilization, and index health.

## 11. Common Design Mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
Generating a new `ObjectId` on every import of the same record | Spawns multiple documents for one entity | Use stable external keys, unique indexes, or deterministic IDs |
Using name/SKU/email as `_id` when they can change | Breaks links when attributes change | Separate identity from mutable business attributes |
Using a bare `externalId` across all systems | Cross-source collisions | Namespace (`source`, `externalId`), plus tenant if needed |
Parsing all external IDs to integers | Strips leading zeros, breaks alphanumeric codes | Store Strings per the source contract |
Assuming `@Id String` always stores BSON String | Raw queries hit wrong `_id` type | Verify mapping, use `@MongoId(FieldType.STRING)` when needed |
Calling `save` blindly without duplicate/stale checks | Late events overwrite newer state | Trustworthy revisions + conditional atomic updates |
Hard-deleting immediately on delete event | Stale events can resurrect the document | Versioned tombstones and safe cleanup policies |
Running multiple workers without unique indexes | Duplicates created under race conditions | Add unique indexes/mappings and controlled retries |
Equating `@Version` with source revision | Misses conflicts or misorders updates | Keep internal optimistic locking separate from source ordering |
Skipping checkpoints/reconciliation | Transient errors leave long-lived drift | Idempotent replay, durable checkpoints, reconciliation |

## 12. Practice Exercises

**Exercise 1 — Choosing Keys.** A store ingests products from an ERP and Supplier B. Both use code `00042`, SKUs occasionally change, and titles change frequently. Propose `_id`, the source-key storage structure, and unique indexes. Explain when an independent internal ID is needed.

**Exercise 2 — Inspecting BSON Types.** Create two documents whose Java IDs are 24-character hex strings: one entity using `@Id String`, the other using `@MongoId(FieldType.STRING)`. Read via the raw driver and compare `_id` BSON types and query outcomes using `String` vs. `ObjectId`.

**Exercise 3 — Building an Idempotent Importer.** Implement events with `sourceSystem`, `externalId`, `revision`, and `title`. Feed the sequence v7, v8, v7, v8, v9 and confirm the final document holds v9. Test two concurrent threads importing when the document does not yet exist.

**Exercise 4 — Handling Deletions.** Add `deleted` and tombstones to Exercise 3. Send delete v10 followed by update v9; verify the product remains marked deleted. Propose conditions under which tombstones can be purged safely.

**Exercise 5 — Sources Without Revisions.** Suppose daily CSV files only deliver the latest snapshot with no version numbers. Design load ordering, checkpointing, missing-record detection, mid-batch failure handling, and reconciliation. Explain why you cannot infer which event is newer solely from worker arrival time.

## 13. Key Takeaways

In **Spring Data MongoDB**, `_id` must be **unique, stable, and aligned with the entity lifecycle**. `@Id` and `@MongoId` define how identifiers map to BSON; for string IDs, pay close attention to `ObjectId` coercion and choose `FieldType.STRING` when storage type must be preserved.

When ingesting from external systems, maintain **clearly namespaced source keys**, decouple internal IDs from mutable business keys, and build ingestion pipelines with **unique indexes, idempotency, revision checks, tombstones, retries, checkpoints, and reconciliation** as required. `MongoRepository` supports identity lookups and `MongoTemplate` supports conditional updates, yet it is the data contract and synchronization model that ensure an entity is never duplicated or rolled back to stale state.
