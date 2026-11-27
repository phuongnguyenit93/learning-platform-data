# Document Read, Conversion, Save, and Delete Phases

## 1. Why Understanding the Document Lifecycle Matters

In the **Lifecycle and Callbacks** chapter of **Spring Data MongoDB**, a single call to `repository.save(product)` does not merely convert a Java object to BSON and send a write command. Spring Data may also perform ID mapping, handle auditing, execute **EntityCallbacks**, publish **mapping lifecycle events**, perform type conversion, and return the result to the application.

Similarly, when reading with `MongoTemplate.findOne(...)` or `MongoRepository.findById(...)`, the BSON document must be converted into a Java object. For delete operations, the database typically receives only a **delete condition** rather than loading each entity first before deleting it.

These details are especially important when a system needs to:

- Normalize an SKU before saving, while **preserving** the original identifier.
- Inspect the mapped BSON shape, such as `@Field("sku_normalized")`.
- Observe read/write activity to record metrics or diagnostics.
- Use `@CreatedDate`/`@LastModifiedDate` instead of manually updating timestamps in every service.
- Understand why an `updateFirst(...)` or bulk update **does not invoke the same hooks** as `save(entity)`.
- Avoid sending emails, making HTTP calls, or publishing messages from a callback before the transaction actually commits.
- Avoid confusing a delete event with receiving **every deleted entity in full**.

**Lesson objectives:** map out the read → convert → save → delete phases accurately; distinguish `EntityCallback` from `AbstractMongoEventListener`; build a Spring Data MongoDB example with callbacks on a Java record, reading/writing against real MongoDB; and design tests to verify the boundaries of each mechanism.

> Examples target Java 17+, Spring Boot 3.x, and Spring Data MongoDB 4.x using synchronous `MongoTemplate`/`MongoRepository`. Callback APIs and event publication timing have version- and framework-dependent details. The diagrams below describe the **logical order** of phases and do not guarantee exact ordering across every listener, converter, auditing callback, and driver hook in every version.

## 2. Three Layers to Distinguish

| Layer | Subject Handled | Purpose |
|---|---|---|
| **MongoDB server / Java Driver** | BSON Document, queries, and `insert`/`update`/`delete` commands | Data reads/writes, predicate evaluation, atomicity, write concern |
| **Spring Data mapping/converter** | Java Object ↔ BSON Document | Reading annotations such as `@Document`, `@MongoId`, `@Field`, conversion, and mapping |
| **Spring Data lifecycle hooks** | Objects or events related to lifecycle phases | Callbacks can intercept/modify entities at supported points; events observe processing |

Example field:

~~~java
@Field("sku_normalized")
String normalizedSku
~~~

In Java, the property name is `normalizedSku`; in MongoDB, the physical field is `sku_normalized`. A **before-convert** callback operates on the Java property, whereas a **before-save** callback can inspect the mapped BSON Document as well. Choosing the wrong phase leads to checking the wrong field name or modifying the object too late.

### 2.1. EntityCallback and Application Lifecycle Events Are Not the Same

**EntityCallback** is a Spring Data callback interface invoked as part of the entity processing pipeline at supported points. It can **return a replacement entity**, for example creating a new immutable record after normalization.

**Mapping lifecycle events** are Spring `ApplicationEvent`s, typically listened to via `AbstractMongoEventListener<T>`. Events are suitable for **observation/diagnostics**, but they depend on the event publishing mechanism. If `ApplicationEventMulticaster` uses an asynchronous executor, listener execution order and timing **cannot be relied upon to guarantee business mutations**.

Do not use the terms "callback" and "event listener" interchangeably as if they were the same mechanism. They differ in capabilities, ordering, and execution guarantees.

### 2.2. Not Every Operation Has Hooks

A **raw driver** write, a `MongoTemplate.updateFirst(...)` using update operators, and a `repository.save(entity)` take different execution paths. Do not assume that all of them go through an entity's `BeforeConvertCallback`, `BeforeSaveCallback`, and `AfterSaveCallback`.

## 3. Document Read Lifecycle Diagram

For a query that maps results to a Java entity, the conceptual flow is:

~~~mermaid
flowchart TD
    A["Repository.find... / MongoTemplate.find..."] --> B["MongoDB returns BSON Document"]
    B --> C["AfterLoadEvent (raw Document, if event is published)"]
    C --> D["MappingMongoConverter reads Document"]
    D --> E["Instantiate entity / record"]
    E --> F["AfterConvert callback and corresponding event"]
    F --> G["Return Java entity to caller"]
~~~

The phases:

1. **Query executes on MongoDB**: index/filter/sort remain the server's responsibility.
2. **Receive BSON**: the document has stored field names, not necessarily Java property names.
3. **After load, before convert**: `AfterLoadEvent` provides an observation point for the raw document in operations that publish events.
4. **Conversion**: `MappingMongoConverter` maps fields, data types, IDs, constructor/record components, and custom conversions.
5. **After convert**: `AfterConvertCallback<T>` receives the constructed entity and can return an adapted version; `AfterConvertEvent<T>` allows listeners to observe.
6. **Caller receives result**: it is already a Java entity, not raw BSON.

**Note:** `AfterLoadEvent` is a **mapping event**, which does not mean an `AfterLoadCallback<T>` exists in every Spring Data release. Choose only APIs actually provided by Spring Data MongoDB.

### 3.1. Reading Does Not Mean Saving

An after-convert callback may compute a display value on the returned object, but that **does not automatically write back to MongoDB**. If durable schema migration is needed, it requires an explicit write command and a separate migration/transaction plan.

### 3.2. Projections, Aggregations, and DTOs

Not every query returns the root entity registered with a callback:

~~~java
mongo.find(query, ProductSummary.class, "catalog_entries");
~~~

When returning a DTO/projection or raw `Document`, callbacks registered for `CatalogEntry` may not be invoked the way a `find(..., CatalogEntry.class)` call would. You must test **each specific query path** separately; do not build invariants assuming every read path runs the same listeners.

## 4. Insert/Save Write Lifecycle Diagram

For entity writes going through Spring Data mapping:

~~~mermaid
flowchart TD
    A["Repository.save / MongoTemplate.insert or save"] --> B["Before convert: BeforeConvert hook"]
    B --> C["MappingMongoConverter: entity -> BSON"]
    C --> D["Before write: BeforeSave hook, mapped BSON"]
    D --> E["MongoDB insert/replace/upsert per API semantics"]
    E --> F["After write: AfterSave hook / event"]
    F --> G["Return result to caller"]
~~~

Key points:

- **BeforeConvert**: you have the Java entity; ideal for normalizing fields or creating a new entity before mapping.
- **BeforeSave**: the converter has already built the BSON; suitable for inspecting BSON structure or certain supported representation adjustments.
- **Driver write**: MongoDB executes `insertOne`/`replaceOne`/`update` depending on the actual operation.
- **AfterSave**: execution has passed the write operation and obtained the result; **this does not mean the transaction has committed**.

These points may have both an **EntityCallback** and a corresponding **application event**. Do not assume events and callbacks at the same stage always have a fixed relative order across all versions and event multicaster configurations.

### 4.1. insert Is Not save

| API | General Meaning | What to Watch Out For |
|---|---|---|
| `MongoTemplate.insert(entity)` | Creates a new document | Duplicate `_id`/unique key may fail |
| `MongoTemplate.save(entity)` | Saves entity according to save semantics, typically upsert/replace depending on mapping and ID | Overwriting a document from a stale or partial entity is risky |
| `MongoRepository.save(entity)` | Repository abstraction for saving an entity | Uses mapping lifecycle; not automatically a multi-document transaction |
| `MongoTemplate.updateFirst(query, update, Entity.class)` | Partial update using operators | Does not necessarily run entity save callbacks |
| `MongoTemplate.findAndModify(...)` | Conditional update that can return pre/post-image | Not equivalent to `save(entity)`; read callbacks on the result may differ |
| Raw `MongoCollection.updateOne(...)` | Direct Java Driver command | Bypasses the full Spring Data mapping lifecycle |

A `save` on a **partially loaded entity** can cause data loss when the write path replaces the entire document. When you only want to change one field, consider conditional/partial updates; when you need stale-state protection, use `@Version` and appropriate business CAS.

### 4.2. IDs Generated in the Pipeline

An ID may be determined before or during the write depending on entity mapping, ID type, and ID source. Do not build a rigid rule such as "every ID already exists before BeforeConvert" or "no ID exists before BeforeSave." If callback logic requires an ID, **test the specific ID type/write path in use** or assign the ID explicitly before saving.

## 5. Delete Lifecycle: Usually Has a Query, Not Every Entity

Delete operations differ from read-modify-save:

~~~javascript
db.catalog_entries.deleteMany({
  tenantId: "tenant-a",
  archived: true
});
~~~

MongoDB can delete many documents based on a **query selector** without loading each full entity into Java. Spring Data has lifecycle events such as `BeforeDeleteEvent` and `AfterDeleteEvent` on operation paths that support event publication, but the event does not necessarily contain each deleted entity.

~~~mermaid
flowchart TD
    A["MongoTemplate.remove / Repository.delete"] --> B["Prepare criteria and collection"]
    B --> C["BeforeDeleteEvent when API path supports it"]
    C --> D["MongoDB deleteOne/deleteMany"]
    D --> E["AfterDeleteEvent when API path supports it"]
    E --> F["Return DeleteResult / repository result"]
~~~

**Do not assume there is an onBeforeDelete/onAfterDelete EntityCallback applied per root entity** as an equivalent to `BeforeConvertCallback`. To know which specific documents were deleted, you must proactively record identifiers/snapshots/business events in the service layer or use an appropriate outbox/audit mechanism.

### 5.1. Delete by Query Is Not N Callbacks

A `remove(query, CatalogEntry.class)` call can delete 100 documents, yet the listener **must not be treated as 100 invocations with 100 entities**. Do not use delete lifecycle events to send an email per record or maintain per-document business counters.

### 5.2. Native/Bulk Operations and Bypasses

The Java Driver's `MongoCollection.deleteMany(...)` does not go through `MongoTemplate` mapping events. Bulk writes and custom delete paths must also be verified against the actual API. If you need accurate auditing across every write/delete path, place invariants in services, schema/unique indexes/transactions, or a reliable event pipeline—do not expect entity callbacks to cover every write path.

## 6. Event and Callback Table by Phase

| Phase | Common Mapping Event | Corresponding EntityCallback (if supported) | Primary Data |
|---|---|---|---|
| Before convert to BSON | `BeforeConvertEvent<T>` | `BeforeConvertCallback<T>` | Java Entity |
| Before save after convert | `BeforeSaveEvent<T>` | `BeforeSaveCallback<T>` | Entity + mapped BSON Document |
| After save | `AfterSaveEvent<T>` | `AfterSaveCallback<T>` | Entity + mapped BSON Document |
| After load BSON before convert | `AfterLoadEvent<T>` | Do not assume a same-named callback exists | BSON Document |
| After convert to Java | `AfterConvertEvent<T>` | `AfterConvertCallback<T>` | Java Entity + BSON Document |
| Before delete | `BeforeDeleteEvent<T>` | No default per-entity delete callback | Delete selector/collection |
| After delete | `AfterDeleteEvent<T>` | No default per-entity delete callback | Operation info, not every deleted entity |

Specific interface names for mapping EntityCallbacks:

~~~java
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveCallback;
import org.springframework.data.mongodb.core.mapping.event.AfterSaveCallback;
import org.springframework.data.mongodb.core.mapping.event.AfterConvertCallback;
~~~

In MongoDB reactive infrastructure, Spring Data provides corresponding **Reactive...Callback** interfaces for supported phases, but their publisher return contracts and contexts differ from imperative APIs. Do not mix imperative callbacks with reactive sessions/transactions without verifying the pipeline path.

### 6.1. When to Use What?

- Need to **modify the entity before mapping**: prefer `BeforeConvertCallback<T>`.
- Need to **inspect mapped BSON**: `BeforeSaveCallback<T>` can be an appropriate hook.
- Need **enrichment after reading**: `AfterConvertCallback<T>` if it fits the contract.
- Need to **observe raw BSON before mapping**: `AfterLoadEvent<T>`.
- Need **loosely coupled logging/metrics**: `AbstractMongoEventListener<T>`, paying attention to async multicaster behavior.
- Need **business guarantees across all write paths**: use services, database constraints, transactions/outbox; not callbacks alone.

## 7. Example Entity: Normalized SKU and BSON Name

Suppose the `catalog_entries` collection stores products per tenant. The application keeps the user-entered SKU and a normalized key used for lookup/uniqueness.

~~~json
{
  "_id": "p-101",
  "tenantId": "tenant-a",
  "sku": " bottle-500 ",
  "displayName": "Water bottle 500 ml",
  "sku_normalized": "BOTTLE-500",
  "createdAt": { "$date": "2026-11-20T08:00:00Z" }
}
~~~

**CatalogEntry.java**

~~~java
package com.example.catalog;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_entries")
public record CatalogEntry(
        @MongoId(FieldType.STRING) String id,
        String tenantId,
        String sku,
        String displayName,
        @Field("sku_normalized") String normalizedSku,
        Instant createdAt) {
}
~~~

A repository:

**CatalogEntryRepository.java**

~~~java
package com.example.catalog;

import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogEntryRepository
        extends MongoRepository<CatalogEntry, String> {

    Optional<CatalogEntry> findFirstByTenantIdAndNormalizedSku(
            String tenantId, String normalizedSku);
}
~~~

Here `findFirstByTenantIdAndNormalizedSku` illustrates the **Java property name** in a derived query; the repository query is mapped to the BSON field `sku_normalized`. `Optional<CatalogEntry>` explicitly represents the not-found state; a search returning no document must not be interpreted as a valid entity carrying null values.

### 7.1. Unique Keys Cannot Rely Solely on Callbacks

If business rules forbid two products with the same normalized SKU within a tenant:

~~~javascript
db.catalog_entries.createIndex(
  { tenantId: 1, sku_normalized: 1 },
  { name: "uq_entry_tenant_sku", unique: true }
);
~~~

**A normalization callback does not protect uniqueness under concurrency.** Two concurrent requests can both normalize to `BOTTLE-500`; the unique index is what prevents two documents from sharing the same `tenantId`/`sku_normalized` pair.

### 7.2. Do Not Let Callbacks Change Tenant

`tenantId` must be controlled at the authentication/authorization layer. A callback can validate that a tenant ID is present, but it should not arbitrarily pull a tenant ID from request-local state and silently overwrite the entity. With background jobs, multi-tenancy, reactive contexts, and raw driver write paths, that approach easily causes data leaks.

## 8. BeforeConvertCallback: Normalizing an Immutable Entity

`BeforeConvertCallback<T>` is used when computing a value from an entity **before MappingMongoConverter turns it into BSON**. With a Java record, setters cannot be called; the callback should **return a new record**.

**NormalizeSkuBeforeConvert.java**

~~~java
package com.example.catalog;

import java.util.Locale;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class NormalizeSkuBeforeConvert
        implements BeforeConvertCallback<CatalogEntry> {

    @Override
    public CatalogEntry onBeforeConvert(
            CatalogEntry entity, String collection) {
        if (!"catalog_entries".equals(collection)) {
            return entity;
        }

        if (entity.tenantId() == null
                || entity.tenantId().isBlank()) {
            throw new IllegalArgumentException(
                    "Invalid tenant");
        }
        if (entity.sku() == null || entity.sku().isBlank()) {
            throw new IllegalArgumentException("Empty SKU");
        }

        String normalized = entity.sku()
                .strip()
                .toUpperCase(Locale.ROOT);

        return new CatalogEntry(
                entity.id(),
                entity.tenantId(),
                entity.sku(),
                entity.displayName(),
                normalized,
                entity.createdAt());
    }
}
~~~

When saving a `CatalogEntry` with `sku = " bottle-500 "`, the callback returns a new record with `normalizedSku = "BOTTLE-500"`. The converter then maps it to BSON `sku_normalized: "BOTTLE-500"`.

### 8.1. Why Return the Entity Instead of Only Mutating Document?

If normalized SKU is an important part of domain state, it should be present on the **entity**:

- Callers/mappers/validators can observe the same value.
- `@Field` mapping automatically translates it to the right BSON field name.
- Tests can verify the Java object before and after the callback.
- No "hidden" BSON field is produced that the entity fails to reflect when read/written again.

Do not use `BeforeSaveCallback` just to silently write an important business value into the raw Document while the Java object retains a different state.

### 8.2. Normalization Is a Domain Rule, Not Just a Mapping Utility

The `strip().toUpperCase(Locale.ROOT)` policy in this lesson only suits SKUs following simple ASCII/Latin character conventions. It **does not handle all Unicode case-folding, Vietnamese diacritics, internal whitespace normalization, special characters, or real-world SKU locale policies**.

Normalization must be defined directly in the domain contract, ensuring **every entry path** uses the same policy (APIs, batch jobs, imports, and migrations). Raw driver writes can bypass callbacks; therefore, if multiple services write to the same collection, a single application's callback should not be trusted as a database-wide constraint.

### 8.3. @Order and Multiple Callbacks

Spring Data can register multiple `EntityCallback`s for the same entity type. `@Order`/`Ordered` helps control callback ordering. However, a normalization callback should not secretly depend on another callback having already generated a tenant ID, as that can change when auditing is configured or the framework is upgraded.

If multiple dependent steps are needed, make the ordering explicit and **test the full pipeline outcome**. Do not use callbacks to generate random numbers or call external services before knowing whether the write/commit succeeded.

## 9. BeforeSaveCallback: Inspecting BSON After Mapping

`BeforeSaveCallback<T>` receives:

- The entity after passing through part of the conversion pipeline;
- `org.bson.Document` containing the BSON representation mapped by Spring Data;
- The collection name.

Example requiring the raw BSON to contain the normalized key:

**ValidateMappedDocumentBeforeSave.java**

~~~java
package com.example.catalog;

import java.util.Objects;
import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class ValidateMappedDocumentBeforeSave
        implements BeforeSaveCallback<CatalogEntry> {

    @Override
    public CatalogEntry onBeforeSave(
            CatalogEntry entity,
            Document document,
            String collection) {
        if (!"catalog_entries".equals(collection)) {
            return entity;
        }

        String mappedSku = document.getString("sku_normalized");
        if (mappedSku == null || mappedSku.isBlank()) {
            throw new IllegalStateException(
                    "Missing sku_normalized in BSON");
        }
        if (!Objects.equals(mappedSku, entity.normalizedSku())) {
            throw new IllegalStateException(
                    "BSON and entity are inconsistent");
        }
        return entity;
    }
}
~~~

After `BeforeConvertCallback` and conversion, `document.getString("sku_normalized")` looks up the **BSON field name**, not the Java property `normalizedSku`.

### 9.1. Do Not Use Raw Document as a Second Source of Truth

Some callbacks can modify `Document` directly when the extension point supports it. However, if you call `document.put("sku_normalized", ...)` without keeping the entity in sync:

1. The database holds a different value from the returned object.
2. A subsequent save of that object can overwrite it back.
3. Pre-conversion validation/domain logic may rely on stale data.
4. Partial update paths or raw driver calls do not go through the callback.

That is why the example chooses to **validate the mapped BSON**, rather than silently mutating a business key at the final stage.

### 9.2. Validation and Exceptions in Callbacks

If a synchronous callback throws an exception before the driver write is sent, a normal `save` operation fails. Still, do not rely on callbacks as the **sole line of defense** for invariants:

- They do not protect raw update/bulk/other driver paths.
- They do not replace schema validation, unique indexes, or authorization.
- They do not prove a multi-document transaction committed.

Input validation should still live in the service/domain layer; callbacks help guard a specific persistence path and can catch mapping regressions.

## 10. AfterConvertCallback: Processing Objects After Reading

After BSON is converted into an entity, `AfterConvertCallback<T>` can inspect or enrich the returned object.

**CheckLoadedEntryAfterConvert.java**

~~~java
package com.example.catalog;

import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.AfterConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class CheckLoadedEntryAfterConvert
        implements AfterConvertCallback<CatalogEntry> {

    @Override
    public CatalogEntry onAfterConvert(
            CatalogEntry entity,
            Document document,
            String collection) {
        if (!"catalog_entries".equals(collection)) {
            return entity;
        }

        // Example legacy schema diagnostics:
        // BSON document may lack a newer field in old data.
        if (!document.containsKey("sku_normalized")) {
            // Policy could be to record a metric or warning.
            // Do not write back to the database from a read callback.
        }
        return entity;
    }
}
~~~

This callback intentionally leaves the entity unchanged. If business requirements call for a **temporary display value** not stored in the DB, you can return an enriched immutable copy, but you must consider that the object might be saved later—avoid letting enrichment get silently persisted.

### 10.1. AfterConvert Is Not the Place to Run Automatic Migrations

Suppose millions of old documents lack `sku_normalized`. A read callback can detect the missing field, but it must not automatically:

~~~text
onAfterConvert:
  read old document
  immediately update database
  call external API
  continue returning result
~~~

This pattern creates unexpected write side effects on every query, can cause write loops/contention, increases latency, and triggers recursion. Use a dedicated migration/job with checkpointing, batching, idempotency, and monitoring; let read callbacks simply reflect current data.

### 10.2. AfterLoad and AfterConvert Run at Different Times

| Phase | What Is Observed? | Field Name |
|---|---|---|
| `AfterLoadEvent` | BSON Document before object mapping | `sku_normalized` |
| `AfterConvertCallback` | Mapped Java Object + BSON Document | `entity.normalizedSku()` and `sku_normalized` |

Do not write a listener checking `document.getString("normalizedSku")` if the physical field is `sku_normalized`.

## 11. AfterSaveCallback and Side Effects Outside the Database

`AfterSaveCallback<T>` can observe the entity/document after the write performed by Spring Data:

~~~java
package com.example.catalog;

import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.AfterSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class CatalogAfterSaveMetric
        implements AfterSaveCallback<CatalogEntry> {

    @Override
    public CatalogEntry onAfterSave(
            CatalogEntry entity,
            Document document,
            String collection) {
        // Lightweight metrics/diagnostics may be recorded here if appropriate.
        // Do not send emails or publish guaranteed messages from here.
        return entity;
    }
}
~~~

**Do not treat AfterSave as after-commit.** If `repository.save(...)` runs inside a MongoDB transaction, the callback can be invoked once the write command finishes but before the transaction commits; the transaction can still abort at a later step.

Counterexample:

~~~text
BEGIN TRANSACTION
  save(Order)
    -> AfterSaveCallback sends "Order placed" email
  update(Inventory) fails
ROLLBACK TRANSACTION

Email was sent even though Order was never committed.
~~~

Solutions to consider:

- **Transactional outbox**: store business state and the outbox event in the same transaction; a worker publishes after commit with idempotency.
- For non-durable internal notifications, transaction synchronization `afterCommit` can be used when the transaction is properly managed, though there is still a crash window between commit and callback; do not substitute it for an outbox when delivery guarantees are required.
- Do not perform external API calls inside callbacks that may run multiple times or on unpredictable thread/event contexts.

### 11.1. A Save Can Be Retried

Writes may be replayed at the application level after timeouts, so metrics or side effects in an after-save callback can fire more times than the number of **distinct business intents**. Do not compute revenue, reward points, or payment counts merely by incrementing in an after-save callback.

### 11.2. Do Not Trigger a Recursive Save Loop

If `AfterSaveCallback` calls `repository.save(entity)` for the same entity, the callback is triggered again, easily causing recursion or duplicate writes. Similarly, an `AfterConvertCallback` calling `findById` uncontrollably can create a read loop.

Keep callbacks **short, deterministic, low on side effects, and never re-entering the same lifecycle path**.

## 12. AbstractMongoEventListener: Observing Raw BSON and Deletes

For event-based lifecycles, `AbstractMongoEventListener<T>` lets you override hooks corresponding to published events. The example below counts events strictly for testing/diagnostics.

**CatalogLifecycleObserver.java**

~~~java
package com.example.catalog;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.data.mongodb.core.mapping.event.AbstractMongoEventListener;
import org.springframework.data.mongodb.core.mapping.event.AfterLoadEvent;
import org.springframework.data.mongodb.core.mapping.event.AfterSaveEvent;
import org.springframework.data.mongodb.core.mapping.event.BeforeDeleteEvent;
import org.springframework.stereotype.Component;

@Component
public class CatalogLifecycleObserver
        extends AbstractMongoEventListener<CatalogEntry> {

    private final AtomicInteger afterLoad = new AtomicInteger();
    private final AtomicInteger afterSave = new AtomicInteger();
    private final AtomicInteger beforeDelete = new AtomicInteger();

    @Override
    public void onAfterLoad(AfterLoadEvent<CatalogEntry> event) {
        // event.getSource() is a raw BSON Document.
        afterLoad.incrementAndGet();
    }

    @Override
    public void onAfterSave(AfterSaveEvent<CatalogEntry> event) {
        afterSave.incrementAndGet();
    }

    @Override
    public void onBeforeDelete(BeforeDeleteEvent<CatalogEntry> event) {
        // Delete events relate to the selector/operation,
        // not a full entity for each deleted document.
        beforeDelete.incrementAndGet();
    }

    public int afterLoadCount() { return afterLoad.get(); }
    public int afterSaveCount() { return afterSave.get(); }
    public int beforeDeleteCount() { return beforeDelete.get(); }
}
~~~

**Important note on the event-counting example:** event dispatch can be configured synchronously or asynchronously; these counts are not transactional business counters. The observer's purpose is diagnostics. Do not treat these in-memory counters as official accounting or SLA data sources.

### 12.1. Event Multicaster and Listener Ordering

With a synchronous `ApplicationEventMulticaster`, listeners are invoked on the thread publishing the event. When the multicaster uses an asynchronous `TaskExecutor`:

- A listener may execute after the query call has already returned.
- Relative ordering across multiple listeners/operations may vary.
- Exceptions from a listener may not propagate back to the caller the same way as a synchronous callback.
- Mutating the event source is not a reliable way to modify the entity saved by the persistence layer.

**When logic must affect the entity being saved**, use the appropriate `EntityCallback` and test the save path; do not rely on an async event listener.

### 12.2. Before/After Delete Events Do Not Carry Each Deleted Entity Row

With `remove(Query.query(...), CatalogEntry.class)`, `BeforeDeleteEvent`/`AfterDeleteEvent` may be published at the operation scope. Therefore, do not do:

~~~text
onAfterDelete:
  assume event.getSource() is the deleted entity
  compute order value from that entity
  send an email per document based on that value
~~~

A filter-based delete can affect zero, one, or many documents. Counting `beforeDeleteCount = 1` does not imply one document was deleted.

### 12.3. Avoid Logging Personal Data

`AfterLoadEvent` can expose raw BSON containing every field, including PII, tokens, or sensitive information. Do not log `event.getSource()` verbatim in production. If debugging is needed, log only permitted IDs, operation names, and sanitized metrics according to policy.

## 13. Which API Paths Actually Go Through the Lifecycle?

A Spring Data MongoDB application has many database access paths. You cannot apply the rule "every write has before/after save" across all of them.

| Access Path | Entity Mapping? | Expect Save EntityCallbacks? | Notes |
|---|---|---|---|
| `repository.save(entity)` | Yes | Yes, for the corresponding entity save path | Affected by registered callbacks |
| `mongo.insert(entity)` | Yes | Yes, for the entity insert pipeline | Not equivalent to replace/upsert |
| `mongo.save(entity)` | Yes | Yes, for the entity save pipeline | Beware stale replacement |
| `mongo.find(..., CatalogEntry.class)` | Yes | Not a save; reads have their own hooks | After-load/after-convert |
| `mongo.updateFirst(query, update, CatalogEntry.class)` | Can map property paths in query/update | **Do not** assume full-entity `BeforeConvertCallback` runs | Update operators; does not materialize entity to save |
| `mongo.updateMulti(...)` | Can map query/update | Not a per-entity save | Multiple documents modified atomically individually |
| `mongo.findAndModify(...)` | Maps query/update and can map result entity | Not `save(entity)` | Read hooks on result depend on API path/options |
| `mongo.remove(query, CatalogEntry.class)` | Maps query and collection | Not entity save callbacks | May publish delete lifecycle events |
| `mongo.bulkOps(...).execute()` | Some mapping support per operation | Do not rely on per-item before/after convert/save | Bulk optimization has its own lifecycle path |
| `mongo.getCollection(...).updateOne(...)` | Raw driver path | No | Bypasses Spring Data mapping/callbacks |

Read this table as a **design risk map**: whenever you need callback guarantees for a specific method, verify them with an integration test on the version you are running. In particular, do not infer from "an entity class is passed as an update parameter" that the framework constructs an entity object, runs callbacks, and then updates.

### 13.1. Counterexample: Partial Updates Can Bypass the Normalized Key

Suppose a document is already stored:

~~~json
{
  "_id": "p-101",
  "tenantId": "tenant-a",
  "sku": " bottle-500 ",
  "sku_normalized": "BOTTLE-500"
}
~~~

Another code path executes:

~~~java
mongo.updateFirst(
        Query.query(Criteria.where("id").is("p-101")
                .and("tenantId").is("tenant-a")),
        new Update().set("sku", "  mug-250  "),
        CatalogEntry.class);
~~~

Because this is a partial update, code must not assume `BeforeConvertCallback<CatalogEntry>` will be called to recompute `normalizedSku`. The database may end up with:

~~~json
{
  "sku": "  mug-250  ",
  "sku_normalized": "BOTTLE-500"
}
~~~

That is a **desynchronized business invariant**, even though both fields have valid BSON names.

Options:

1. Have the service layer normalize the SKU and update **both `sku` + `sku_normalized` in the same command**.
2. If computing from current server-side values is needed, use an appropriate aggregation pipeline update and verify its semantics.
3. Centralize property writes into a single tested persistence path; restrict other writers.
4. Use appropriate unique indexes + schema validation, keeping in mind they **do not automatically enforce** `normalize(sku) == sku_normalized`.
5. Run a reconciliation/migration job on legacy data to detect drift.

**Do not treat Java callbacks as MongoDB server triggers.** Java callbacks run only on operations passing through the corresponding Spring Data infrastructure.

### 13.2. Counterexample: Raw Insert Bypasses Even Before-Convert

~~~java
mongo.getCollection("catalog_entries").insertOne(
        new org.bson.Document("_id", "raw-1")
                .append("tenantId", "tenant-a")
                .append("sku", " mug-250 "));
~~~

This is a raw driver operation and does not pass through `NormalizeSkuBeforeConvert`. The document may lack `sku_normalized` unless MongoDB schema validation rejects it. Later reads via the repository **do not automatically re-run save-path before-convert logic**.

### 13.3. When to Choose a Custom Converter Instead of a Callback?

If you need to convert a **data type** (for example, a value object to a custom BSON representation and back), `MongoCustomConversions`/`Converter` may be more appropriate. If you need to normalize an **entity before saving**, `BeforeConvertCallback` is a better fit.

Do not use an entity callback to replace mapping type converters for every field of a type; likewise, do not use a converter to make HTTP calls, enforce tenant authorization, or write audits.

## 14. Root Entities, Nested Objects, DBRefs, and Callback Scope

Spring Data MongoDB lifecycle events are generally published for **root-level document types** in applicable mapping/CRUD operations. A nested object such as `ShippingAddress` inside an `Order` document **does not necessarily receive its own lifecycle events**.

Example:

~~~java
@Document(collection = "orders")
public record OrderDocument(
        @MongoId String id,
        String tenantId,
        ShippingAddress address) {
}

public record ShippingAddress(
        String street,
        String city) {
}
~~~

When `OrderDocument` is saved:

- `BeforeConvertCallback<OrderDocument>` is the callback for the root entity when the save path supports it.
- Do not assume `BeforeConvertCallback<ShippingAddress>` will be invoked as an independent write.
- Embedded objects are mapped by the converter as parts of the root document.
- `@DBRef`/`@DocumentReference` and lazy resolution mechanisms have different lifecycles/lookups; do not treat them as embedded objects always loaded at the same time.

### 14.1. Why the Root-Level Boundary Matters

If you place critical validation only in a callback registered for nested `ShippingAddress`, saving the root `OrderDocument` may not invoke that callback as expected. Validate nested objects from the root callback/domain validation or apply appropriate schema validation.

Do not rely on a value object's callback to guarantee validity of data coming from bulk updates, raw drivers, or external sync systems outside Java.

### 14.2. Constructor Mapping Is Not the Save Lifecycle

When reading BSON into a Java record, `MappingMongoConverter` uses the constructor/record components to materialize the object. Logic inside the constructor can run on **every object instantiation**, even when no database write occurs; by contrast, `BeforeConvertCallback` is typically tied to preparing an entity for a write path.

If a constructor has side effects such as incrementing counters or emitting events, it may fire on read paths too and cause unintended effects. Constructors should stick to immutability/pure validation rather than replacing persistence callbacks.

## 15. Auditing Callbacks: createdAt, updatedAt, createdBy

Spring Data MongoDB provides auditing support for common metadata:

- `@CreatedDate`: entity creation timestamp;
- `@LastModifiedDate`: entity modification timestamp;
- `@CreatedBy` and `@LastModifiedBy`: actor identifier, requiring an `AuditorAware<?>` or equivalent mechanism.

Instead of manually writing timestamp-setting callbacks for every entity, you can enable auditing in configuration:

~~~java
package com.example.catalog;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

@Configuration
@EnableMongoAuditing
public class CatalogAuditingConfig {
}
~~~

The fragment above only illustrates **enabling auditing**. If `@CreatedBy` or `@LastModifiedBy` is needed, an `AuditorAware` bean aligned with your security context is required. For reactive auditing, use `ReactiveAuditorAware` infrastructure and the corresponding reactive annotations/configuration for your version.

An entity may declare:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;

public class AuditedCatalogEntry {
    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;
}
~~~

This is an **illustrative field fragment**, not a complete `@Document`. In a real application, you must add ID mapping, collection mapping, constructors, and getters/setters as appropriate.

### 15.1. Auditing and Custom Callbacks

Auditing is typically performed during the entity conversion lifecycle; its relative order with custom callbacks is affected by `@Order`/`Ordered` and the implementation. If a custom callback requires `createdAt` to already be populated, check ordering or move the logic to the service/domain layer instead of relying on luck.

### 15.2. Update Operators Can Bypass Created/Updated Auditing

`mongo.updateFirst(query, new Update().set("status", "ACTIVE"), Entity.class)` is not the same as `repository.save(entity)`. Do not assume `@LastModifiedDate` on every partially updated document will always advance due to the auditing callback.

With partial updates, you can set `updatedAt` in the same `Update` or use an appropriate server operator according to your consistency contract. If comprehensive auditing across different write paths is required, design a unified strategy instead of assuming every API updates timestamps automatically.

### 15.3. createdAt and IDs Also Have Timing Semantics

`@CreatedDate` can be set when the entity lifecycle identifies a new record. However, "new entity" detection depends on ID/version and mapping; an object with a pre-assigned ID does not automatically get identified as "new" the same way an object without an ID does.

If logic must strictly distinguish create vs. update, use appropriate APIs (`insert` vs. `save`, unique indexes, or `Persistable` when truly needed) and test your framework version. Do not simply compare `id == null` in a callback and treat it as a system-wide classification mechanism.

## 16. @Version, Optimistic Locking, and Callbacks: Different Responsibilities

`@Version` on an entity helps detect stale writes on persistence paths supported by Spring Data. It **is not a lifecycle event** and is not automatically applied identically across raw driver/bulk/custom updates.

Example:

~~~java
import org.springframework.data.annotation.Version;

@Version
private Long version;
~~~

The fragment above belongs inside an entity class with a version field and proper mapping. When `repository.save(entity)` uses optimistic locking, a stale version can cause the write to be rejected with `OptimisticLockingFailureException` if acknowledged writes are enabled.

### 16.1. Do Not Mutate Version in a Callback to "Fix" Stale Data

A callback seeing a stale version and incrementing it is not server-side CAS. Conflict checking must be tied to a **write predicate** protecting the version. Do not use callbacks to bypass stale-entity errors or overwrite newer documents.

### 16.2. AfterSave Does Not Mean the Entity Is Durable on Replicas

Write concern, transaction commit, and replication are different guarantees from a callback being invoked:

- `AfterSaveCallback` may run before transaction commit.
- A write sent over the network that hits a network error may leave the application uncertain of the outcome.
- A reader on a secondary may observe data with lag depending on read preference/concern.

Do not use the firing of an after-save event as proof that "it committed and every system can see it."

## 17. Designing Controlled Deletes: Results, Tenant, and Outbox

To delete an entity safely per tenant, include the **tenant filter in the delete query itself**:

**CatalogEntryDeletionService.java**

~~~java
package com.example.catalog;

import com.mongodb.client.result.DeleteResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class CatalogEntryDeletionService {
    private final MongoTemplate mongo;

    public CatalogEntryDeletionService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public boolean removeOne(
            String authenticatedTenantId,
            String entryId) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || entryId == null || entryId.isBlank()) {
            throw new IllegalArgumentException("Invalid input");
        }

        Query query = Query.query(
                Criteria.where("id").is(entryId)
                        .and("tenantId").is(authenticatedTenantId));

        DeleteResult result =
                mongo.remove(query, CatalogEntry.class);
        return result.getDeletedCount() == 1;
    }
}
~~~

Here `DeleteResult.getDeletedCount()` is the number of documents deleted as reported by MongoDB with an acknowledged result. Do not infer from `BeforeDeleteEvent` that exactly one document was deleted.

### 17.1. What If Auditing Every Deleted Document Is Mandatory?

Suitable options depending on requirements:

1. **Soft delete:** record `deletedAt`/`deletedBy` instead of a physical delete; requires clear indexes, TTL policy, and access control.
2. **Delete a single entity in a transaction:** read entity / write audit or outbox in the same transaction and then delete, with conditions/CAS protecting the document and race testing.
3. **Change streams:** capture changes at MongoDB for sync/auditing if topology/retention and resume handling fit; note that pre-images are not always enabled by default.
4. **Outbox event:** durably store reason/id/deletion policy in a transaction and publish via a worker with an idempotent consumer.

A lifecycle listener cannot replace a durable business log if the service crashes or another system deletes directly.

### 17.2. Dropping a Collection Is Not 1000 Before-Delete Callbacks

`dropCollection` and `deleteMany` have different semantics from per-document entity deletes. Avoid building mandatory audit mechanisms that depend on MongoDB firing **one Java event per document**. For `dropCollection`, also check administrative permissions, test/prod scoping, and migration strategy.

## 18. Integration Test: Proving BeforeConvert → BSON → AfterLoad

Mocking `MongoTemplate` can prove a method was called, but it **does not prove** callbacks are registered in the mapping infrastructure, that BSON uses the expected field names, or that reading actually materializes the entity. You need a real test MongoDB (such as Testcontainers or a dedicated test MongoDB instance).

`@DataMongoTest` in Spring Boot 3.x creates a test slice for Spring Data MongoDB, but it **does not automatically start a MongoDB server**. You must supply a connection to a test MongoDB. Never use a production database.

### 18.1. Seeding and Testing the Save/Read Flow

**CatalogEntryLifecycleIntegrationTest.java**

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
@Import({
        NormalizeSkuBeforeConvert.class,
        ValidateMappedDocumentBeforeSave.class,
        CheckLoadedEntryAfterConvert.class,
        CatalogLifecycleObserver.class,
        CatalogEntryDeletionService.class
})
class CatalogEntryLifecycleIntegrationTest {

    @Autowired MongoTemplate mongo;
    @Autowired CatalogEntryRepository repository;
    @Autowired CatalogLifecycleObserver observer;
    @Autowired CatalogEntryDeletionService deletion;

    private CatalogEntry newEntry(String id, String sku) {
        return new CatalogEntry(
                id,
                "tenant-a",
                sku,
                "Water bottle 500 ml",
                null,
                Instant.parse("2026-11-20T08:00:00Z"));
    }

    @BeforeEach
    void prepare() {
        // Test database must be isolated; never drop a real collection.
        mongo.dropCollection(CatalogEntry.class);
    }

    @Test
    void beforeConvertNormalizesAndBeforeSaveChecksMappedBson() {
        repository.save(newEntry("p-101", " bottle-500 "));

        Document raw = mongo.getCollection("catalog_entries")
                .find(new Document("_id", "p-101"))
                .first();

        assertThat(raw).isNotNull();
        assertThat(raw.getString("sku")).isEqualTo(" bottle-500 ");
        assertThat(raw.getString("sku_normalized"))
                .isEqualTo("BOTTLE-500");
        assertThat(raw.containsKey("normalizedSku")).isFalse();
    }

    @Test
    void findByIdConvertsBsonBackToJavaRecord() {
        repository.save(newEntry("p-101", " bottle-500 "));

        int loadEventsBefore = observer.afterLoadCount();

        CatalogEntry loaded = repository.findById("p-101")
                .orElseThrow();

        assertThat(loaded.normalizedSku())
                .isEqualTo("BOTTLE-500");
        assertThat(loaded.tenantId()).isEqualTo("tenant-a");
        assertThat(loaded.sku()).isEqualTo(" bottle-500 ");

        // Only assert this when using the default synchronous event multicaster.
        assertThat(observer.afterLoadCount())
                .isGreaterThan(loadEventsBefore);
    }

    @Test
    void derivedQueryUsesJavaPropertyAndMappedBsonField() {
        repository.save(newEntry("p-101", " bottle-500 "));

        assertThat(repository
                .findFirstByTenantIdAndNormalizedSku(
                        "tenant-a", "BOTTLE-500"))
                .isPresent()
                .get()
                .extracting(CatalogEntry::id)
                .isEqualTo("p-101");
    }

    @Test
    void tenantScopedDeleteDoesNotRemoveOtherTenant() {
        repository.save(newEntry("p-101", " bottle-500 "));
        repository.save(new CatalogEntry(
                "p-201",
                "tenant-b",
                " bottle-500 ",
                "Water bottle tenant-b",
                null,
                Instant.parse("2026-11-20T08:00:00Z")));

        assertThat(deletion.removeOne(
                "tenant-b", "p-101")).isFalse();
        assertThat(deletion.removeOne(
                "tenant-a", "p-101")).isTrue();

        assertThat(repository.findById("p-101")).isEmpty();
        assertThat(repository.findById("p-201")).isPresent();
    }
}
~~~

### 18.2. Explaining the Tests

The first test proves:

1. `repository.save(...)` executes the SKU normalization callback.
2. The converter maps the `normalizedSku` property to `sku_normalized`.
3. `BeforeSaveCallback` does not throw when BSON is valid.
4. The raw driver reads the actual persisted Document, not just a test-created object.

The read test proves `findById(...)` materializes a `CatalogEntry` with the corresponding Java properties. The event-observation assertion is **deterministic only when the multicaster is synchronous**; if the project uses an async multicaster, do not assert immediate event counts without explicit test synchronization.

The delete test proves **the tenant filter is enforced at the database**. It does not assert one event per deleted document. A `false` result could mean missing or wrong tenant—do not casually leak information about another tenant in API responses.

### 18.3. When Test Callbacks Are Not Registered

If `@DataMongoTest` does not load custom `@Component` callbacks because the test slice scans only part of the application context, `@Import(...)` as shown explicitly registers them.

However, if production registers callbacks via a different configuration (`@Order`, custom converters, auditing), include **at least one integration test matching the near-production context** to avoid passing slice tests while runtime configuration differs.

### 18.4. Testing the Unique Index

If the business requires uniqueness on (`tenantId`, `sku_normalized`), the test must create the index on the **test database** before inserting:

~~~java
import com.mongodb.client.model.IndexOptions;
import org.bson.Document;

mongo.getCollection("catalog_entries").createIndex(
        new Document("tenantId", 1)
                .append("sku_normalized", 1),
        new IndexOptions()
                .name("uq_entry_tenant_sku")
                .unique(true));
~~~

Place this fragment in setup/test code that has `mongo`. Once the index exists, two SKUs normalizing to the same value within the same tenant must be rejected by MongoDB at the unique constraint level; two different tenants may share the same normalized SKU if business rules allow it.

Do not take a single successful normalization callback execution as proof that uniqueness is protected under concurrent writes.

## 19. Integration Test: Partial Update and Raw Driver Bypassing Save Callbacks

When reviewing a system with multiple write paths, testing only `repository.save(...)` is not enough.

### 19.1. Trying updateFirst on an Already Saved Document

Additional test method for `CatalogEntryLifecycleIntegrationTest`:

~~~java
@Test
void partialUpdateDoesNotRecalculateDerivedSkuField() {
    repository.save(newEntry("p-101", " bottle-500 "));

    mongo.updateFirst(
            Query.query(Criteria.where("id").is("p-101")
                    .and("tenantId").is("tenant-a")),
            new Update().set("sku", " mug-250 "),
            CatalogEntry.class);

    Document raw = mongo.getCollection("catalog_entries")
            .find(new Document("_id", "p-101")).first();

    assertThat(raw).isNotNull();
    assertThat(raw.getString("sku")).isEqualTo(" mug-250 ");
    assertThat(raw.getString("sku_normalized"))
            .isEqualTo("BOTTLE-500");
}
~~~

Import `Criteria`, `Query`, and `Update` from `org.springframework.data.mongodb.core.query`. This is an **intentional counterexample test**: after a partial update, the normalized SKU becomes stale because the before-convert callback **does not run on a full entity**. The lesson does not recommend leaving inconsistent state like this in production; update both fields atomically or redesign the write architecture.

### 19.2. Trying a Native Driver Insert

~~~java
@Test
void rawDriverInsertDoesNotInvokeSpringBeforeConvert() {
    mongo.getCollection("catalog_entries").insertOne(
            new Document("_id", "raw-1")
                    .append("tenantId", "tenant-a")
                    .append("sku", " raw-sku "));

    Document raw = mongo.getCollection("catalog_entries")
            .find(new Document("_id", "raw-1"))
            .first();

    assertThat(raw).isNotNull();
    assertThat(raw.containsKey("sku_normalized")).isFalse();
}
~~~

This result proves Java callbacks cannot be treated as **MongoDB server triggers**. If a field must be enforced across **every** write path, consider schema validation, API contracts, and an architecture allowing only controlled writes. Schema validation can enforce that a field is present, though it cannot compute normalized SKUs using Java rules.

### 19.3. Testing Callback Exceptions

~~~java
@Test
void invalidSkuIsRejectedBeforeWriting() {
    assertThatThrownBy(() ->
            repository.save(newEntry("invalid", "   ")))
            .isInstanceOf(IllegalArgumentException.class);

    assertThat(repository.findById("invalid")).isEmpty();
}
~~~

Requires static import `org.assertj.core.api.Assertions.assertThatThrownBy`. This test depends on `NormalizeSkuBeforeConvert` being registered, and the save command is not sent to the driver if the callback throws.

**Do not conclude** that raw driver inserts are also rejected by the same callback. To verify database-wide enforcement, test the raw path + JSON schema validation separately.

## 20. Callbacks in Reactive MongoDB

When using `ReactiveMongoTemplate` or `ReactiveMongoRepository`, Spring Data provides reactive interfaces such as `ReactiveBeforeConvertCallback<T>`. They return a `Publisher<T>` to participate in the asynchronous processing stream.

Illustrative example in a reactive application:

~~~java
package com.example.catalog;

import java.util.Locale;
import org.reactivestreams.Publisher;
import org.springframework.data.mongodb.core.mapping.event.ReactiveBeforeConvertCallback;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ReactiveSkuNormalization
        implements ReactiveBeforeConvertCallback<CatalogEntry> {

    @Override
    public Publisher<CatalogEntry> onBeforeConvert(
            CatalogEntry entity, String collection) {
        return Mono.fromSupplier(() -> {
            if (!"catalog_entries".equals(collection)) {
                return entity;
            }
            if (entity.sku() == null
                    || entity.sku().isBlank()) {
                throw new IllegalArgumentException("Empty SKU");
            }
            String normalized = entity.sku().strip()
                    .toUpperCase(Locale.ROOT);
            return new CatalogEntry(
                    entity.id(),
                    entity.tenantId(),
                    entity.sku(),
                    entity.displayName(),
                    normalized,
                    entity.createdAt());
        });
    }
}
~~~

Notes:

- Reactive callbacks use **Publisher** and are composed into the reactive pipeline; do not call `block()` or `subscribe()` arbitrarily inside the callback.
- `Mono.fromSupplier(...)` defers computation until the publisher is subscribed, ensuring proper error propagation in Reactor.
- Reactive transactions use `ReactiveMongoTransactionManager` and Reactor Context; imperative `MongoTransactionManager` does not automatically protect reactive flows.
- Async event multicasters and reactive EntityCallbacks **are not the same mechanism**.
- Keep a unified pure normalization policy shared between imperative and reactive code; do not copy two divergent implementations and let business keys drift.

### 20.1. Asynchrony Does Not Make Callbacks Safe for Side Effects

If a `ReactiveAfterSaveCallback` publishes a message to Kafka, the message may still be sent before transaction commit or duplicated upon retry/resubscription. The right pattern remains **outbox, idempotency, and commit control**, not merely switching a callback from imperative to reactive.

### 20.2. Avoid Duplicate Callback Registration

An application may have both imperative and reactive callback beans for the same entity class, but how the infrastructure discovers and invokes each must be explicitly configured and tested. Do not assume an imperative callback automatically applies to every reactive repository operation.

## 21. Performance and Observability of Lifecycle Hooks

Callbacks run on persistence paths and can affect the **latency of every related insert/save/find**. A seemingly small snippet that performs an HTTP request, queries another collection, or parses large payloads per entity will noticeably degrade throughput.

| Work Inside Callback | Risk | Better Alternative |
|---|---|---|
| Normalizing a short string in pure Java | Usually low cost | `BeforeConvertCallback` with unit/integration tests |
| Inspecting a mapped BSON field | Low cost if logic is simple | `BeforeSaveCallback` |
| Calling an HTTP API to populate metadata | Unpredictable latency, timeouts, side effects | Service orchestration with explicit retry policy |
| Publishing messages/emails | Sent before commit, duplicates/retries | Transactional outbox |
| Reading multiple other documents to validate | Races, N+1 queries, lock/contention | Conditional writes, transactions, or domain services |
| Reading and saving the entity in AfterConvert | Recursion; every read becomes a write | Dedicated migration/repair job |
| Logging raw Documents verbatim | Leaks PII/secrets, heavy I/O | Structured metrics, redaction |
| Incrementing an in-memory counter in AfterSave | Not durable, not tied to commit, fails multi-instance | Dedicated metrics or durable domain events |

### 21.1. Measure at the Operation Level, Not Only the Callback

To tell whether callbacks are slowing down the application:

1. Measure p50/p95/p99 latency of actual queries/saves.
2. Compare on a representative workload with an **extra callback** enabled/disabled in a test environment.
3. Observe how many times callbacks execute across different API paths.
4. Inspect query plans with `explain("executionStats")` if latency is primarily in MongoDB.
5. Track callback validation errors, network exceptions, and transaction aborts separately.
6. Avoid measuring only a callback via async logs and mistaking that for commit time.

Do not move a business invariant into an async observer just because the observer has lower latency. Data correctness outweighs shaving a few microseconds when designing hooks.

### 21.2. Root Callbacks Can Run Multiple Times

In a batch API with multiple `repository.save(entity)` calls, callbacks may run on each entity save. If the application retries `save` after an error or the caller replays the same operation, callbacks can be invoked again. Hence the need for **idempotency/pure functions**—and never turning callbacks into a place to charge money or increment business counters.

### 21.3. You Do Not Need a Callback for Pure Domain Logic

Not every normalization rule should be "hidden" in the persistence layer. For an SKU used in many places, you can define:

~~~java
public final class SkuPolicy {
    private SkuPolicy() {}

    public static String normalize(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("Empty SKU");
        }
        return input.strip()
                .toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

This is a pure function that services, callbacks, importers, and unit tests can all share. The callback is merely **one enforcement point** of the policy, not the sole source of the rule.

## 22. Common Troubleshooting

| Symptom / Mistake | Possible Cause | Resolution |
|---|---|---|
| `BeforeConvertCallback` does not run | Bean not scanned/imported | Check `@Component`/`@Bean` and test context |
| Callback does not run with `MongoCollection.insertOne` | Raw driver bypasses Spring mapping | Go through Spring Data mapping or apply separate validation |
| `updateFirst` does not normalize related field | Does not materialize entity for save | Update all fields atomically; do not rely on save callbacks |
| `BeforeSaveCallback` reads `normalizedSku` from BSON and gets null | Physical field name is `sku_normalized` | Check `@Field` and raw BSON |
| Callback returns old entity even though it built a new one | Transformed object was not returned | For immutable records, return the new instance |
| Callback sets tenant from thread-local | Risk of data leak / wrong tenant when async | Get tenant from auth context and filter in service |
| Callback modifies ID depending on timing | ID mapping/generation varies | Assign ID explicitly or test lifecycle per type |
| `AfterConvertCallback` updates DB on every read | Reads become writes; risk of recursion | Separate migration job |
| `AfterSaveCallback` sends email but transaction rolls back | Hook may run before commit | Outbox / after-commit policy |
| Application event listener mutates entity but DB does not change | Events lack mutation contract and may be async | EntityCallback for supported operation paths |
| Assuming listener runs in a specific order with auditing | Ordering was not explicitly defined | `@Order` and full-pipeline tests |
| Nested object gets no separate event | Events are typically on root entities | Validate from root/domain/schema |
| Delete event lacks entity | Delete uses query selector; does not load each document | Capture audit/IDs proactively |
| `deleteMany` removes 100 rows but listener counts 1 | Event scope is per operation, not per document | Inspect `DeleteResult`; design separate auditing |
| `findById` returns entity yet AfterLoad was not counted by observer | Async multicaster, unregistered listener, or different API path | Check wiring and synchronize events if needed |
| Callback throws error yet raw driver writes succeed | Callbacks only run on Spring paths | DB schema validation/unique index and writer policy |
| `@CreatedDate` does not update on partial update | Auditing callback does not run like save | Set update timestamp in write or use dedicated policy |
| Custom callback and auditing overwrite each other | Execution order / field ownership unclear | Establish a single owner and test |
| `@Version` does not protect custom updates | Version guard missing on raw/bulk paths | CAS on version in filter |
| Event observer counts duplicate saves | Retries / duplicate subscriptions | Idempotency and metric semantics |
| Logging `event.getSource()` leaks data | Raw BSON contains sensitive info | Redact/allowlist and adjust log levels |
| Mock test passes yet MongoDB data is wrong | Mocks do not run real converters/callbacks | Integration tests against MongoDB |
| Test `dropCollection` targets wrong DB | Test URI not isolated | Dedicated test database; validate test connection |

### 22.1. Quick Verification Procedure

When a normalized field is missing after a save:

1. **Identify the operation**: `repository.save`, `MongoTemplate.save`, `updateFirst`, or raw driver.
2. **Check bean wiring**: is the callback in the Spring context with the right generic entity type?
3. **Check collection/mapping**: `@Document(collection=...)`, `@Field`, ID type, BSON field names.
4. **Verify the actual command** by reading back raw `Document` or using a MongoDB Driver `CommandListener` in a test environment.
5. **Run an integration test** targeting that exact use case, without relying on Mockito verification.
6. **Check other write paths**: do imports, bulk jobs, and migrations follow the same policy?
7. **Fix existing bad data** via a migration/repair job; do not expect reads to heal it automatically.

Do not turn on debug logging of full BSON in production just to chase a mapping bug; you may accidentally write PII, credentials, or business payloads into long-lived logs.

## 23. Hands-On Exercises

**Exercise 1 — Draw timelines.** Draw three separate flows for `findById`, `save(entity)`, and `remove(query)`. Mark exactly where Java objects, raw BSON, and MongoDB commands are used. Distinguish events from callbacks.

**Exercise 2 — Root vs. embedded.** Create an `OrderDocument` entity with a nested `ShippingAddress`. Register callbacks for both root and nested types, then check which hooks a root save actually invokes. Explain why you should not rely on per-object nested events.

**Exercise 3 — Immutable BeforeConvert.** Create a `CatalogEntry` record whose callback returns a new record with a normalized SKU. Verify the original SKU is untouched and the normalized SKU is persisted correctly.

**Exercise 4 — BeforeSave BSON.** Map `normalizedSku` to `sku_normalized` and validate it in `BeforeSaveCallback`. Intentionally read the wrong key `normalizedSku` to observe the difference between Java properties and BSON fields.

**Exercise 5 — AfterLoad vs. AfterConvert.** Register `AbstractMongoEventListener<CatalogEntry>` to observe `AfterLoadEvent`, plus an `AfterConvertCallback<CatalogEntry>`. Record the raw BSON/Java object attributes visible in each hook without logging sensitive data.

**Exercise 6 — AfterSave and rollback.** In a MongoDB replica set test, perform a `save` and then trigger a business error within the same transaction. Prove that the after-save hook can execute before rollback; design an outbox instead of sending email inside the callback.

**Exercise 7 — Partial update bypass.** Save a normalized SKU, then use `updateFirst` to modify only `sku`. Verify that the normalized field becomes stale, and fix the service to update both fields in a single command.

**Exercise 8 — Raw driver bypass.** Use `MongoCollection.insertOne` to write a document without the normalized field. Prove the Java callback does not run, then design schema validation or a writer policy.

**Exercise 9 — Unique business key.** Create a unique index on `(tenantId, sku_normalized)`. Run two concurrent inserts with the same normalized SKU. Distinguish the role of the normalization callback from the database unique constraint.

**Exercise 10 — Delete events.** Run `remove(query)` deleting multiple documents for a tenant. Compare `DeleteResult.getDeletedCount()` against how many times the event listener is called. Do not treat the event count as the number of deleted documents.

**Exercise 11 — Auditing.** Enable `@EnableMongoAuditing` and add `@CreatedDate` and `@LastModifiedDate` to a real entity. Test insert/save/partial update and document which operations update timestamps under your configuration.

**Exercise 12 — @Version.** Add `@Version`, load two copies of an entity, and save them sequentially. Prove optimistic locking is a write condition rather than version-increment logic inside a callback.

**Exercise 13 — Async event multicaster.** Configure an async event multicaster in a test and observe how listeners can run after the caller returns with unguaranteed ordering. Do not write immediate assertions without synchronization.

**Exercise 14 — Reactive callback.** Create a `ReactiveBeforeConvertCallback` returning `Mono`/`Publisher`; test it with `StepVerifier` during a reactive save. Do not call `block()` or `subscribe()` inside the callback.

**Exercise 15 — Mapping integration test.** Using `@DataMongoTest` and an isolated test MongoDB, verify before-convert, BSON mapping, read conversion, delete, and raw driver bypass. Explain why Mockito mocks are insufficient.

**Exercise 16 — Performance.** Seed many documents; measure read/write latency when a callback only normalizes strings, when it performs heavy work, and when it records lightweight metrics. Identify ways to reduce side effects and prevent N+1 queries in callbacks.

## 24. Key Takeaways

In **Spring Data MongoDB**, distinguish **reading BSON → converting to entity**, **entity → converting to BSON → saving**, and **selector-based deletion**. These phases have distinct lifecycle hooks: `BeforeConvertCallback` handles the Java entity before mapping; `BeforeSaveCallback` sees the mapped BSON; `AfterSaveCallback` observes after the write; `AfterLoadEvent` sees raw BSON before mapping; `AfterConvertCallback` sees the entity after mapping. Delete events do not mean you are given a full entity for every deleted document.

**EntityCallback differs from application mapping events.** Callbacks can return a new entity and belong to the persistence pipeline on supported operation paths; events are meant for observation and may be dispatched asynchronously. Do not rely on event listeners to mutate business state or assume callbacks apply to `updateFirst`, bulk writes, and raw driver commands.

**Callbacks do not replace database constraints or transactional design:** normalized business keys need unique indexes when uniqueness is required; lost-update prevention needs CAS/`@Version`; multi-document consistency needs transactions where appropriate; post-commit event/email delivery needs an outbox or a reliable delivery mechanism. Keep pure, lightweight validation/normalization in callbacks, preserve tenant filters, and test against real MongoDB on both save paths and bypass paths before deploying to production.
