# Callbacks with Immutable Entities and Returned Objects

> **Chapter:** Lifecycle and Callbacks  
> **Module:** `SPRING_DATA_MONGODB`

In Spring Data MongoDB, an entity can be a Java `record` or a class with `final` fields and no setters. An **immutable** design prevents unintended state mutations, yet raises a natural question: how does a lifecycle callback assign a normalized reference code, add metadata, or adjust a read result when **the original entity cannot be mutated in place**?

The solution is to use **`EntityCallback<T>`** under its value-returning contract: the callback receives the entity, can construct **a new instance of the same type `T`**, and **returns that instance for Spring Data to process further**. However, not every checkpoint has the same effect on persisted data: in `BeforeConvertCallback`, the returned entity is used when building the BSON `Document`; in `BeforeSaveCallback`, BSON has already been built, so you must mutate `Document` itself to alter the written data. `AfterSaveCallback` and `AfterConvertCallback` can replace the entity returned to the caller, yet never trigger another database write automatically.

This topic belongs to the `SPRING_DATA_MONGODB` module: using Spring Data MongoDB to connect, map documents, and operate via `MongoTemplate` or repositories; practicing queries, aggregations, indexes, transactions, reactive access, testing, and performance diagnostics. This lesson focuses on **callback lifecycles, immutable entities, and the semantics of returned objects**, rather than re-explaining all of MongoDB mapping.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish lifecycle `EntityCallback`s from Spring Data MongoDB `ApplicationEvent`s.
2. Identify the **before-convert**, **before-save**, **after-save**, and **after-convert** checkpoints and the actual effect of the return value at each checkpoint.
3. Use a Java `record` or immutable class with **copy/`with...` methods** instead of setters.
4. Write a `BeforeConvertCallback<T>` normalizing persistent fields and returning a new entity.
5. Write a `BeforeSaveCallback<T>` updating the BSON `Document` at the right time; avoid confusing "returning a new object" with "re-mapping BSON."
6. Understand that `AfterSaveCallback<T>` and `AfterConvertCallback<T>` can change the Java result **without automatically writing back to MongoDB**.
7. Register callbacks as Spring beans, control ordering, and manage interactions with auditing, IDs, and versions.
8. Compare imperative and reactive callbacks; write tests reading back raw BSON, original objects, and returned objects.
9. Recognize operations like `updateFirst`, bulk writes, and direct driver calls that bypass the full entity-conversion lifecycle.

## 2. What Is an Immutable Entity in the MongoDB Context?

A Java `record` has components that cannot be mutated directly after construction:

```java
package com.example.shop.orders;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String tenantId,
    String externalRef,
    String normalizedRef,
    Instant createdAt
) {
    public OrderDocument withNormalizedRef(String newRef) {
        return new OrderDocument(
            id, tenantId, externalRef, newRef, createdAt);
    }
}
```

In this example:

- `id` is an application-supplied fixed key, such as `"ORD-101"`. A non-ObjectId-shaped string avoids conflating `String`/`ObjectId` mapping in this lesson.
- `tenantId` handles business partitioning and service-level authorization.
- `externalRef` is a reference such as `" web-014 "` sent by an external system.
- `normalizedRef` is the normalized value for lookup/reconciliation, e.g. `"WEB-014"`.
- `createdAt` is a pre-write timestamp mapped as an `Instant` via converters.

There is no `setNormalizedRef(...)`; calling `withNormalizedRef` returns a **new copy** preserving the remaining four fields. This is the copy-on-write pattern. The original object stays untouched, and **the caller must use the returned value** to see the change.

```java
OrderDocument original = new OrderDocument(
    "ORD-101",
    "TENANT-A",
    " web-014 ",
    null,
    Instant.parse("2026-11-20T02:00:00Z"));

OrderDocument changed = original.withNormalizedRef("WEB-014");

assert original.normalizedRef() == null;
assert changed.normalizedRef().equals("WEB-014");
assert original != changed;
```

These `assert` statements illustrate Java semantics and require enabling assertions at runtime; in real JUnit tests, use AssertJ/JUnit assertions.

### 2.1. Immutable Does Not Mean Fields Cannot Be Store-Populated

Spring Data can instantiate a new instance via constructor/copy/wither when assigning immutable properties on supported mapping paths. Still, never assume the **original input object** is mutated in place when the database assigns an ID or version.

In this lesson, we deliberately supply `id` and `createdAt` up front to isolate callback behavior. When using auto-generated IDs or `@Version`, test the **returned instance**, stored values, and mapping strategy of your exact Spring Data version.

## 3. Processing Flow: Difference Between Entity and BSON Document

Saving a domain entity through `MongoTemplate.insert/save` can be pictured as:

```text
OrderDocument original (immutable)
        |
        v
BeforeConvertCallback<T>
        |  returns OrderDocument E1
        v
MappingMongoConverter
        |  maps E1 -> org.bson.Document D1
        v
BeforeSaveCallback<T>
        |  can change D1 (BSON to write)
        |  returns entity E2 (does NOT remap E2 to D1)
        v
MongoDB write(D1)
        |
        v
AfterSaveCallback<T>
        |  returns entity E3 to caller
        v
Template/repository save result

Read path:
MongoDB Document -> converter creates entity
        -> AfterConvertCallback<T>
        -> caller receives returned entity
```

This is a **logical checkpoint diagram**; mapping events, auditing, ID generation/version handling, and transactions/sessions may also participate depending on configuration and operation.

### 3.1. Critical Decision Table

| MongoDB Callback | Imperative Signature | Mapped to BSON Yet? | If It Returns a New Entity, What Happens? |
| --- | --- | --- | --- |
| `BeforeConvertCallback<T>` | `T onBeforeConvert(T entity, String collection)` | **No** | The new entity becomes the converter's source for BSON |
| `BeforeSaveCallback<T>` | `T onBeforeSave(T entity, Document doc, String collection)` | **Yes** | Returned entity may pass down the chain, yet **only mutating `doc` changes persisted BSON** |
| `AfterSaveCallback<T>` | `T onAfterSave(T entity, Document doc, String collection)` | **Already written** | Returned entity can shape the Java save result; **does not re-save** |
| `AfterConvertCallback<T>` | `T onAfterConvert(T entity, Document doc, String collection)` | **Reading, already converted** | Caller receives replacement entity; **does not update DB** |

**Quick rule of thumb:** To normalize **persistent fields** on an immutable entity before saving → `BeforeConvertCallback`. To edit the generated BSON itself → `BeforeSaveCallback` using `org.bson.Document`. To enrich the returned object after saving/reading → `AfterSave` or `AfterConvert`, while clearly understanding JVM state vs. MongoDB state.

### 3.2. Distinguishing from ApplicationEvent Listeners

MongoDB also provides `BeforeConvertEvent`, `BeforeSaveEvent`, `AfterSaveEvent`, and `AfterConvertEvent` via `AbstractMongoEventListener`. Events suit observation and event-infrastructure integration, yet:

- Event listeners are notification-oriented and generally **lack a contract to return a replacement entity** to the pipeline like `EntityCallback<T>`.
- The event multicaster can be configured asynchronously; listener completion order and timing become unpredictable.
- Entity callbacks are wired directly at Spring Data checkpoints and can **return a new object** or a Publisher emitting a new object.
- Never combine event listeners mutating entities with copy-on-write callbacks on the same fields without explicit ordering/ownership rules.

With an immutable domain model, **prefer EntityCallback whenever data must be adjusted in the persistence lifecycle**. Use event listeners only for other purposes where you fully understand their limits, rather than treating both mechanisms as equivalent. See the Spring Data Commons and MongoDB docs at the end of this lesson.

## 4. BeforeConvertCallback: Returning a New Immutable Entity Before BSON Mapping

This is the natural checkpoint to compute `normalizedRef` from `externalRef`:

File `NormalizeOrderRefCallback.java`:

```java
package com.example.shop.orders;

import java.util.Locale;
import org.springframework.core.annotation.Order;
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
@Order(200)
public final class NormalizeOrderRefCallback
        implements BeforeConvertCallback<OrderDocument> {

    @Override
    public OrderDocument onBeforeConvert(
            OrderDocument entity, String collection) {

        if (entity.externalRef() == null
                || entity.externalRef().isBlank()) {
            throw new IllegalArgumentException(
                "externalRef cannot be blank");
        }

        String normalized = entity.externalRef()
            .trim()
            .toUpperCase(Locale.ROOT);

        if (normalized.equals(entity.normalizedRef())) {
            return entity; // Avoid allocation if already normalized.
        }

        // Immutable: return new instance, NEVER mutate old entity.
        return entity.withNormalizedRef(normalized);
    }
}
```

Note that `@Order(200)` only illustrates relative priority when multiple callbacks share the same phase. Built-in callbacks (such as auditing) also carry their own orders; watch out if multiple callbacks touch the same fields. Do not treat `@Order(200)` as a fixed Spring Data requirement.

### 4.1. Why Must You Return the Copy?

Counterexample:

```java
@Override
public OrderDocument onBeforeConvert(
        OrderDocument entity, String collection) {
    entity.withNormalizedRef("WEB-014");
    return entity; // WRONG: discards the newly created copy.
}
```

`withNormalizedRef(...)` returns a new object, yet the snippet **throws it away**. The converter gets back the original instance, leaving `normalizedRef` null.

Correct:

```java
return entity.withNormalizedRef("WEB-014");
```

This is not just style. **The return-value contract is how new state flows through the lifecycle.**

### 4.2. A Callback Can Return the Same Old Object If No Change Is Needed

A callback is not forced to allocate a new instance on every invocation. If `normalizedRef` is already `"WEB-014"`, returning the original `entity` avoids allocation and keeps logic idempotent:

```java
if (normalized.equals(entity.normalizedRef())) {
    return entity;
}
return entity.withNormalizedRef(normalized);
```

When a service calls `save(...)` multiple times or the callback chain runs across operations, a **stable** normalization is far easier to debug than generating new random values on every callback run.

### 4.3. Caller and Original Object Are Not Identical

```java
OrderDocument original = new OrderDocument(
    "ORD-101", "TENANT-A", " web-014 ", null,
    Instant.parse("2026-11-20T02:00:00Z"));

OrderDocument persisted = template.insert(original);

// The callback created a new copy to persist.
assert original.normalizedRef() == null;
assert persisted.normalizedRef().equals("WEB-014");
```

This snippet assumes `template` is an injected `MongoTemplate` with the callback registered. To prove persistence, **read back raw BSON** rather than only asserting `persisted`. `insert`/`save` and version-specific callback/version/ID steps can affect the returned entity; this example supplies an explicit ID to avoid the auto-ID branch.

### 4.4. Do Not Put External I/O Inside BeforeConvert

Callbacks should be simple, deterministic, and fast. If saving an order makes an HTTP call to look up exchange rates or sends an email inside a callback, that call repeats on retries, adds latency, or fails outside transaction boundaries. Data fetched outside MongoDB belongs in services/workflows with explicit timeouts, caches, policies, and outboxes.

## 5. BeforeSaveCallback: BSON Already Exists — Returning a New Entity Is Not Enough

After `BeforeConvertCallback`, `MappingMongoConverter` converts the entity into `org.bson.Document`. Spring Data then invokes `BeforeSaveCallback`:

```java
public interface BeforeSaveCallback<T> {
    T onBeforeSave(
        T entity,
        org.bson.Document document,
        String collection);
}
```

This is the relevant signature slice, not a full interface to redefine yourself. Spring Data MongoDB explicitly states: **only changes to `Document` affect the ongoing write**. The callback can return a different entity, yet the converter **does not re-run** on that returned entity.

### 5.1. Correct: Add Fields Directly to Document

Suppose a technical `schemaVersion` field must always be integer 2 on write:

File `SchemaVersionBeforeSaveCallback.java`:

```java
package com.example.shop.orders;

import org.bson.Document;
import org.springframework.core.annotation.Order;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveCallback;
import org.springframework.stereotype.Component;

@Component
@Order(400)
public final class SchemaVersionBeforeSaveCallback
        implements BeforeSaveCallback<OrderDocument> {

    @Override
    public OrderDocument onBeforeSave(
            OrderDocument entity,
            Document document,
            String collection) {

        // BSON was already mapped from the entity at the prior checkpoint.
        document.put("schemaVersion", 2);

        // No need to transform the Java object for a field
        // that exists only at the storage layer.
        return entity;
    }
}
```

Result of an insert:

```javascript
{
  _id: "ORD-101",
  tenantId: "TENANT-A",
  externalRef: " web-014 ",
  normalizedRef: "WEB-014",
  createdAt: ISODate("2026-11-20T02:00:00Z"),
  schemaVersion: 2
}
```

Here `schemaVersion` is a technical BSON field unmapped on the record. When reading `OrderDocument` back, the converter ignores it because no matching property exists. If business logic ever needs `schemaVersion` on the domain entity, add it to the model and set it in `BeforeConvertCallback` instead of relying on hidden fields.

Depending on type-mapping config, real BSON may also contain Spring Data's technical `_class` field; the example lists only the fields under observation. Never enable `additionalProperties:false` in a MongoDB validator without accounting for framework-written fields.

### 5.2. Wrong: Returning a Different Entity Without Modifying Document

```java
// COUNTEREXAMPLE: wrong callback for changing persisted BSON.
public OrderDocument onBeforeSave(
        OrderDocument entity,
        Document document,
        String collection) {

    return new OrderDocument(
        entity.id(),
        entity.tenantId(),
        "REF-REPLACED",
        entity.normalizedRef(),
        entity.createdAt());
}
```

This code returns an entity with `externalRef="REF-REPLACED"`, yet the **already-mapped Document** keeps the old `externalRef` unless the callback mutates `document`. This creates confusion between the Java entity seen downstream and what was persisted.

To modify **persistent properties** at the entity level, move the logic to `BeforeConvertCallback`. If you genuinely intend to alter BSON:

```java
public OrderDocument onBeforeSave(
        OrderDocument entity,
        Document document,
        String collection) {

    document.put("externalRef", "REF-REPLACED");
    return entity;
}
```

Keep in mind: mutating only BSON creates a **mismatch** between the returned Java object and MongoDB. For important domain properties, computing them before conversion provides a single consistent contract.

### 5.3. Do Not Arbitrarily Mutate `_id`, Version, or Mapped Field Names

In `BeforeSaveCallback`, `Document` holds **BSON names**, which differ from Java field names if `@Field("...")` is used. Calling `document.put("foo", ...)` without checking the actual BSON name creates an unintended field violating the schema.

Likewise, never arbitrarily alter `_id` or `version` at this checkpoint. ID and version interact with `save`/`insert`, optimistic locking, new-entity detection, and update filters. Changing BSON out of sync with metadata/converters introduces subtle bugs. Maintain clear identity/version ownership and test on real MongoDB.

## 6. AfterSaveCallback: Replacing the Returned Object Does Not Mean Writing Again

`AfterSaveCallback<T>` executes once the save operation has passed the write step. It receives the entity and BSON `Document`, and can return a **different entity** as the result of the save path:

```java
package com.example.shop.orders;

import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.AfterSaveCallback;

public final class ReturnNormalizedAfterSaveCallback
        implements AfterSaveCallback<OrderDocument> {

    @Override
    public OrderDocument onAfterSave(
            OrderDocument entity,
            Document document,
            String collection) {

        // PEDAGOGICAL EXAMPLE: returns a different immutable copy.
        return new OrderDocument(
            entity.id(),
            entity.tenantId(),
            entity.externalRef().trim(),
            entity.normalizedRef(),
            entity.createdAt());
    }
}
```

Here we intentionally **omit `@Component`** so production saves do not silently alter returned results.

If the persisted `externalRef` is `" web-014 "`, this callback returns a Java object with `externalRef="web-014"`. It **performs no second write**, so MongoDB keeps the untrimmed string. If the caller later calls `save(...)` with that cleaned object, the database would change on that **subsequent** write.

This example demonstrates the return-value contract, **not a recommendation to mutate persistent fields after save**. In real applications:

- Use `BeforeConvertCallback` if the persisted field should be normalized.
- Use a separate DTO/view if the UI needs formatted display text.
- Avoid returning an entity shaped identically to the MongoDB model yet silently differing from persisted BSON if re-saved.

### 6.1. AfterSave Is Not an "After Commit" Mechanism

A critical transactional point: **`AfterSaveCallback` is not a "transaction durably committed" callback**. It runs inside the save operation's lifecycle. When `save(...)` runs inside a multi-operation transaction, the transaction can still roll back in a later step or fail on commit.

Never send emails, call payment APIs, or publish non-idempotent Kafka messages inside `AfterSaveCallback` assuming DB commit is guaranteed. For durable side effects, use an outbox written in the same transaction with a post-commit dispatcher, or a dedicated bounded after-commit mechanism.

## 7. AfterConvertCallback: Transforming Read Entities Without Updating DB

Suppose a legacy document lacks `normalizedRef`. We want callers to read a normalized form during migration without reads triggering DB writes:

File `LegacyRefAfterConvertCallback.java`:

```java
package com.example.shop.orders;

import java.util.Locale;
import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.AfterConvertCallback;
import org.springframework.stereotype.Component;

@Component
public final class LegacyRefAfterConvertCallback
        implements AfterConvertCallback<OrderDocument> {

    @Override
    public OrderDocument onAfterConvert(
            OrderDocument entity,
            Document document,
            String collection) {

        if (entity.normalizedRef() != null
                || entity.externalRef() == null) {
            return entity;
        }

        String calculated = entity.externalRef()
            .trim()
            .toUpperCase(Locale.ROOT);

        return entity.withNormalizedRef(calculated);
    }
}
```

What happens:

```text
MongoDB document:
  { externalRef: " web-014 " }  (missing normalizedRef)
             |
             v
MappingMongoConverter -> OrderDocument(normalizedRef=null)
             |
             v
AfterConvertCallback -> NEW OrderDocument(normalizedRef="WEB-014")
             |
             v
Caller receives normalizedRef="WEB-014"

MongoDB still lacks normalizedRef until an actual write occurs.
```

### 7.1. "Reading Returns a Normalized Value" Does Not Prove Data Was Migrated

`AfterConvertCallback` can make an integration test calling only `findById` look as if every document already has the field. To verify a **MongoDB migration**, read raw `org.bson.Document` or query the real schema directly.

A read callback like this is a **read-compatibility shim**, not a substitute for migration. If code reads and then re-saves that computed object, that next save writes `normalizedRef` as a new write—not as a side effect of reading.

### 7.2. Never Use AfterConvert to Enforce Multi-Tenant Security

If a caller is not authorized to read a document, a callback running **after the data was already fetched and mapped** is too late to replace authorization filters. Tenant-scoped queries, authorization, and projections must happen **before/during the query**. Never rely on callbacks to strip sensitive fields across read paths or serve as a primary security boundary.

## 8. Four Checkpoints in One End-to-End Case

With `NormalizeOrderRefCallback`, `SchemaVersionBeforeSaveCallback`, and `LegacyRefAfterConvertCallback` registered:

| Step | Input / Output | Which Copy Changes? |
| --- | --- | --- |
| Caller creates `original` | `externalRef=" web-014 "`, `normalizedRef=null` | Original object |
| `BeforeConvert` | Returns copy with `normalizedRef="WEB-014"` | **Entity passed to converter** |
| Converter | Produces BSON with `normalizedRef="WEB-014"` | New `Document` |
| `BeforeSave` | Adds `schemaVersion:2` to BSON | **Document written** |
| MongoDB write | Stores BSON with both values above | Database |
| `AfterSave` (demo variant excluded) | Returns entity from save path | Caller's Java object |
| Find/read | Loads BSON and maps to record | Fresh Java object |
| `AfterConvert` | Computes normalized only if legacy missing | **Returned Java object**, no write-back |

**Note:** a callback can return the **same instance** when no change is needed. Never assume every checkpoint allocates a copy; what matters is that code uses the returned instance whenever a change occurs.

## 9. Registering EntityCallbacks and Controlling Order

Spring Data discovers `EntityCallback` beans in Spring's `ApplicationContext` and integrates them into matching mapping paths. Two common ways:

### 9.1. `@Component` with Explicit Generic Type

```java
@Component
public final class NormalizeOrderRefCallback
        implements BeforeConvertCallback<OrderDocument> {
    @Override
    public OrderDocument onBeforeConvert(
            OrderDocument entity, String collection) {
        return entity; // Illustrates signature and bean registration only.
    }
}
```

This is a **skeleton**, not a replacement for section 4's full implementation. Implementing `BeforeConvertCallback<OrderDocument>` declares the domain type so Spring Data routes the callback to matching entities.

### 9.2. `@Bean` in `@Configuration`

If avoiding component scanning, declare the bean explicitly:

```java
package com.example.shop.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;

@Configuration(proxyBeanMethods = false)
public class OrderCallbackConfiguration {

    @Bean
    BeforeConvertCallback<OrderDocument> orderRefCallback() {
        return (entity, collection) -> {
            if (entity.externalRef() == null) {
                throw new IllegalArgumentException(
                    "Missing externalRef");
            }
            String value = entity.externalRef()
                .trim()
                .toUpperCase(java.util.Locale.ROOT);
            return entity.withNormalizedRef(value);
        };
    }
}
```

**Do not register this bean alongside `NormalizeOrderRefCallback` from section 4** if you want only one normalization callback: both would run and create redundant configuration. These two snippets show **two registration options**, not two steps to run together.

### 9.3. Lambda Callbacks and Type Filtering

A `@Bean` returning `BeforeConvertCallback<OrderDocument>` is concise, yet Spring Data docs note that lambda objects may not expose full generic type info at runtime for optimal type filtering in all cases. In systems with many entities/callbacks, a **concrete class implementing the typed interface** is easier to inspect and filter cleanly.

Never write a `BeforeConvertCallback<Object>` checking `instanceof` across dozens of entity types unless you truly have a global use case and test every mapping path. Overly broad callbacks add overhead to every insert/save.

### 9.4. Callback Ordering

An entity can have multiple `BeforeConvertCallback<OrderDocument>` beans:

```text
Callback A  @Order(50)   -> entity E1
Callback B  @Order(200)  -> entity E2
Callback C  (default)    -> entity E3
Converter              -> Document from E3
```

Typically **smaller order values run first**. Callbacks in the same phase apply sequentially; each receives the entity returned by the previous one.

Example:

```java
@Component
@Order(50)
public final class ValidateTenantCallback
        implements BeforeConvertCallback<OrderDocument> {
    @Override
    public OrderDocument onBeforeConvert(
            OrderDocument entity, String collection) {
        if (entity.tenantId() == null
                || entity.tenantId().isBlank()) {
            throw new IllegalArgumentException(
                "tenantId is required");
        }
        return entity;
    }
}
```

This validation callback runs before `@Order(200)` normalization. Still, validation order must be deliberate: if one callback transforms a field and another validates it, set their order to reflect **whether validation checks pre- or post-normalization values**.

### 9.5. Avoid Depending on Undeclared Order

If two callbacks both update `normalizedRef` without explicit `@Order` or `Ordered`, effective order is unpredictable or fragile across configs. Never rely on bean names or class-file order in a package. Even better, have **one single owner for each invariant**, or combine tightly coupled steps into one callback.

## 10. Auditing and Immutable Entities

Spring Data MongoDB supports auditing such as `@CreatedDate` and `@LastModifiedDate`. Auditing integrates via entity callbacks prior to conversion, which directly affects setterless objects:

- Auditing needs to populate timestamps or user IDs.
- An immutable entity cannot be mutated like a mutable JavaBean.
- Mapping/auditing infrastructure must construct a **new instance or use a compatible property accessor**.
- Callers must use the **entity returned by save**, not expect the original reference to mutate.

### 10.1. Model Example with `@CreatedDate`

```java
package com.example.shop.orders;

import java.time.Instant;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("audited_orders")
public record AuditedOrder(
    @Id String id,
    String tenantId,
    String externalRef,
    @CreatedDate Instant createdAt,
    @LastModifiedDate Instant updatedAt
) {}
```

When auditing is enabled with the appropriate Spring Data MongoDB configuration (such as `@EnableMongoAuditing` for imperative, or `@EnableReactiveMongoAuditing` for reactive where supported), auditing populates fields at the right checkpoint. **Never** add annotations alone and expect timestamps to populate without enabling auditing.

### 10.2. Avoid Custom Callbacks Overwriting Auditing Fields

Anti-pattern:

```java
// Same createdAt modified in multiple places:
// 1) @CreatedDate via AuditingEntityCallback
// 2) custom BeforeConvertCallback manually calling Instant.now()
// 3) external MongoDB trigger modifying it further
```

When auditing owns `createdAt`/`updatedAt`, avoid writing another callback that arbitrarily sets those fields on every save. On immutable entities, a later callback copying from an older snapshot can accidentally **overwrite** values auditing just populated.

A clean strategy:

- Let auditing own standard audit fields.
- Limit business callbacks to domain fields like `normalizedRef`.
- If callbacks have order dependencies, assign explicit `@Order` and test both inserts and updates.
- For business timestamps tied to a request, pass them from the service per contract rather than sprinkling `Instant.now()` across callbacks.

### 10.3. Order of `AuditingEntityCallback`

Spring Data MongoDB reference docs include a callback ordering table; auditing is typically registered with a specific default order (such as `100` in releases documenting it), while unordered custom callbacks default to lowest precedence. Order numbers only apply **within the same callback checkpoint**; you cannot use them to move `BeforeSave` ahead of `BeforeConvert`.

When upgrading Spring Data, verify your exact release's lifecycle-callbacks table instead of relying on a remembered order from an older version.

## 11. Immutable `@Id` and `@Version`: Callbacks Should Not Replace Store-Managed Fields

Spring Data follows specific rules for:

- `@Id`: document identity; driver/converter may generate an ID on insert if absent.
- `@Version`: optimistic locking/version field; save/update may check expected version and increment it.
- `@CreatedDate`, `@LastModifiedDate`: auditing.

With immutable entities, these values must be represented via compatible constructors/withers. Never let the framework manage `_id`/version while simultaneously tampering with them manually in `BeforeSaveCallback`.

### 11.1. Initially Null ID: Know Who Owns the ID

Another example:

```java
@Document("notes")
public record NoteDocument(
    @Id String id,
    String tenantId,
    String body
) {}
```

When inserting `NoteDocument(null, "TENANT-A", "hello")`, MongoDB/Spring Data can assign an identifier depending on mapping/driver/version. Because the original is immutable, it has no setter to receive the generated ID. Inspect the `insert(...)` return value and read back raw BSON to confirm:

```java
NoteDocument original = new NoteDocument(
    null, "TENANT-A", "hello");

NoteDocument saved = template.insert(original);

// Verify on your running version:
assert saved.id() != null;
// NEVER assume assert original.id() != null.
```

For certain immutable mappings, compatible constructors/withers are needed so Spring Data can instantiate a new copy with assigned properties. Also note a `String` ID may map to a BSON `ObjectId` if formatted like one, so choose an explicit strategy when canonical String IDs are required.

### 11.2. Do Not Turn `BeforeConvert` into a Version Incrementer

Suppose an entity has `@Version Long version`. If a callback runs:

```java
// COUNTEREXAMPLE: manually incrementing version in BeforeConvert.
return new OrderWithVersion(
    entity.id(), entity.version() + 1, /* ... */);
```

while Spring Data also manages version, optimistic-locking predicates can mismatch and reject valid updates. `OrderWithVersion` here is a hypothetical type illustrating the anti-pattern, not a complete class.

For optimistic locking, rely on `@Version`/conditional updates and test concurrent updates; never mutate store-managed fields in callbacks without knowing the exact persistence sequence.

### 11.3. Interaction Between Immutable Copies and `@Version` on Save

When copying an entity, always preserve the current `id`/`version` unless you intentionally intend to create a brand-new aggregate. Accidentally copying with `id=null` turns `save(...)` into a new document insert; altering `version` improperly triggers false optimistic-locking conflicts.

In immutable `with...` methods, always copy **every field that must be retained**. Adding a field to a record constructor causes the compiler to catch constructor call sites that need updating; with custom builders, write tests to ensure no fields get dropped.

## 12. Callbacks Do Not Run for Every MongoDB Operation

`EntityCallback`s attach to checkpoints where Spring Data **converts entities** on supported template/repository paths. That **differs from** arbitrary MongoDB write commands.

### 12.1. Insert/Save via MongoTemplate or Repository

```java
OrderDocument saved = template.insert(order);
OrderDocument savedAgain = repository.save(saved);
```

When callbacks are active, entity-saving operations like these traverse the matching lifecycle. Verify exact behavior when using `insertAll`, entity inheritance, or specialized template options on your version.

### 12.2. `updateFirst`/`updateMulti` Do Not Construct `OrderDocument`

```java
template.updateFirst(
    Query.query(Criteria.where("_id").is("ORD-101")),
    new Update().set("externalRef", " new-ref "),
    OrderDocument.class);
```

This is a **field-level update**, not "load an `OrderDocument` → run BeforeConvert → map and save." Therefore **never assume** `NormalizeOrderRefCallback` will recompute `normalizedRef` after the command above.

When code updates `externalRef` directly, you can:

- Update both `externalRef` and `normalizedRef` together in one atomic update.
- Use an aggregation update pipeline where appropriate.
- Place normalization in the service sharing a pure helper with the callback.
- Design schemas/read models so invariants are enforced by a better-suited mechanism.

### 12.3. `BulkOperations`, Raw Driver, and Scripts Bypass Entity Callbacks

```java
template.getCollection("orders").updateOne(
    new Document("_id", "ORD-101"),
    new Document("$set",
        new Document("externalRef", " raw-from-driver ")));
```

This is a direct driver API call, bypassing Spring Data entity converters and callbacks. Likewise, `mongosh` scripts or services using other drivers know nothing about Spring beans.

**Conclusion:** callbacks are a consistency layer **on the Spring Data mapping path**, not a database constraint covering every writer. If `normalizedRef` must always match `externalRef` regardless of writer, enforce contracts across all writers, add migrations/validation, or adjust storage/query design.

### 12.4. Aggregation Projections and Nested Objects

Never assume an `@Aggregation` returning a DTO, an interface projection, or a nested subdocument runs every checkpoint like a root entity. Spring Data MongoDB docs specify that lifecycle events apply to **root-level types**, and entity callbacks tie to mapped entity paths.

If a callback is expected on an aggregation/projection result, write a dedicated integration test for that exact return type, converter, and repository method. Never cite a `findById(OrderDocument.class)` test as proof every aggregation triggers `AfterConvertCallback<OrderDocument>`.

## 13. Reactive Callbacks: Returning a Publisher Emitting the New Entity

Spring Data separates sync and reactive interfaces. With `ReactiveMongoTemplate` or `ReactiveMongoRepository`, matching callbacks carry the `Reactive...` prefix and return `org.reactivestreams.Publisher<T>`:

| Imperative | Reactive Counterpart |
| --- | --- |
| `BeforeConvertCallback<T>` → `T` | `ReactiveBeforeConvertCallback<T>` → `Publisher<T>` |
| `BeforeSaveCallback<T>` → `T` | `ReactiveBeforeSaveCallback<T>` → `Publisher<T>` |
| `AfterSaveCallback<T>` → `T` | `ReactiveAfterSaveCallback<T>` → `Publisher<T>` |
| `AfterConvertCallback<T>` → `T` | `ReactiveAfterConvertCallback<T>` → `Publisher<T>` |

Reactive operations require subscription. A reactive callback should emit exactly **one valid entity** through its Publisher so Spring Data can continue the lifecycle. Returning `Mono.empty()`, `null`, or a never-completing Publisher is not a safe way to "skip a callback"; return `Mono.just(entity)` when no change is needed.

### 13.1. `ReactiveBeforeConvertCallback` with a Java Record

File `ReactiveNormalizeOrderRefCallback.java`:

```java
package com.example.shop.orders;

import java.util.Locale;
import org.reactivestreams.Publisher;
import org.springframework.data.mongodb.core.mapping.event.ReactiveBeforeConvertCallback;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public final class ReactiveNormalizeOrderRefCallback
        implements ReactiveBeforeConvertCallback<OrderDocument> {

    @Override
    public Publisher<OrderDocument> onBeforeConvert(
            OrderDocument entity, String collection) {

        return Mono.fromSupplier(() -> {
            if (entity.externalRef() == null
                    || entity.externalRef().isBlank()) {
                throw new IllegalArgumentException(
                    "Invalid externalRef");
            }

            String value = entity.externalRef()
                .trim()
                .toUpperCase(Locale.ROOT);

            return value.equals(entity.normalizedRef())
                ? entity
                : entity.withNormalizedRef(value);
        });
    }
}
```

The example uses full reactive API imports. Reactive callbacks are non-blocking and never need `block()`.

### 13.2. `ReactiveBeforeSaveCallback`: Mutating Document Inside a Publisher

```java
package com.example.shop.orders;

import org.bson.Document;
import org.reactivestreams.Publisher;
import org.springframework.data.mongodb.core.mapping.event.ReactiveBeforeSaveCallback;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public final class ReactiveSchemaVersionCallback
        implements ReactiveBeforeSaveCallback<OrderDocument> {

    @Override
    public Publisher<OrderDocument> onBeforeSave(
            OrderDocument entity,
            Document document,
            String collection) {

        return Mono.fromSupplier(() -> {
            document.put("schemaVersion", 2);
            return entity;
        });
    }
}
```

`document` here is still the BSON already produced by the converter. The Publisher emits the entity passed onward; changing persisted data happens via `document.put(...)`, **not** via `Mono.just(entity.with...())` post-conversion.

### 13.3. Never Mix Sync Callbacks and Reactive Callbacks as If They Were One Chain

Spring Data Commons separates callbacks by API flavor: imperative paths evaluate synchronous callbacks; reactive paths evaluate reactive callbacks. Therefore, if the same collection is written via both `MongoTemplate` and `ReactiveMongoTemplate`:

1. Configure each callback group for its actual API path.
2. Share one **pure function** computing `normalizedRef` so the two paths never diverge.
3. Write tests for both templates/repositories when both are used.
4. Never assume a `BeforeConvertCallback<OrderDocument>` bean applies to reactive inserts.

### 13.4. `ReactiveAfterConvertCallback` and Immutable Copies

```java
package com.example.shop.orders;

import java.util.Locale;
import org.bson.Document;
import org.reactivestreams.Publisher;
import org.springframework.data.mongodb.core.mapping.event.ReactiveAfterConvertCallback;
import reactor.core.publisher.Mono;

public final class ReactiveLegacyReadCallback
        implements ReactiveAfterConvertCallback<OrderDocument> {

    @Override
    public Publisher<OrderDocument> onAfterConvert(
            OrderDocument entity,
            Document document,
            String collection) {

        if (entity.normalizedRef() != null
                || entity.externalRef() == null) {
            return Mono.just(entity);
        }

        String normalized = entity.externalRef()
            .trim()
            .toUpperCase(Locale.ROOT);

        return Mono.just(entity.withNormalizedRef(normalized));
    }
}
```

This is an illustrative class; to let Spring Data invoke it automatically, **register it as a bean** (`@Component` or `@Bean`). It alters only the object returned on reads and never updates `normalizedRef` in MongoDB.

### 13.5. Reactive Callbacks Are No Place for Blocking I/O

A reactive callback calling `RestTemplate`, blocking JDBC, or `Thread.sleep` directly blocks event-loop threads. If blocking sources are unavoidable, isolate them carefully with dedicated schedulers and timeouts, though it is far better to **keep I/O out of callbacks** and resolve it in services/adapters with explicit contracts.

Likewise, `Mono.defer`/`Mono.fromSupplier` does not mean "automatically retry-safe": a Publisher can be subscribed again, re-running callbacks. Never generate a fresh random operation ID per callback run for a business flow that already has a fixed idempotency key.

## 14. Integration Test: Comparing Original, Returned Entity, and Raw BSON

To prove copy-on-write, a unit test calling `onBeforeConvert` directly is not enough. Verify:

- **Original**: the input immutable object stays unchanged.
- **Returned**: the `MongoTemplate.insert(...)` return value reflects callback processing.
- **Stored**: real BSON `Document` contains normalized `normalizedRef` and `schemaVersion` stamped in `BeforeSave`.
- **Loaded**: `findById(...)` applies `AfterConvert` to legacy data without writing back to DB.
- **Direct update**: `updateFirst` changes `externalRef` without re-running `BeforeConvert`.

### 14.1. Preparing JUnit 5 + `@DataMongoTest`

With Spring Boot 3.x, use `@DataMongoTest` and `@Import` to register the exact callbacks under test. Tests must point to an **isolated test** MongoDB/database. Other major Spring Boot versions may change test slice packages/annotations; verify your dependencies.

File `OrderCallbackIntegrationTest.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Date;
import java.util.UUID;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
@Import({
    NormalizeOrderRefCallback.class,
    SchemaVersionBeforeSaveCallback.class,
    LegacyRefAfterConvertCallback.class,
    ReturnNormalizedAfterSaveCallback.class
})
class OrderCallbackIntegrationTest {

    @Autowired
    MongoTemplate template;

    private static String newId() {
        return "ORD-" + UUID.randomUUID();
    }

    private static Query byId(String id) {
        return Query.query(Criteria.where("_id").is(id));
    }

    private Document raw(String id) {
        return template.getCollection("orders")
            .find(new Document("_id", id))
            .first();
    }

    private void cleanup(String id) {
        template.getCollection("orders")
            .deleteOne(new Document("_id", id));
    }

    @Test
    void beforeConvertUsesCopyAndBeforeSaveChangesBson() {
        String id = newId();

        OrderDocument original = new OrderDocument(
            id,
            "TENANT-TEST",
            " web-014 ",
            null,
            Instant.parse("2026-11-20T02:00:00Z"));

        try {
            OrderDocument returned = template.insert(original);

            // 1. Original remains immutable.
            assertThat(original.normalizedRef()).isNull();

            // 2. Callback returned a copy for the save path.
            assertThat(returned.normalizedRef())
                .isEqualTo("WEB-014");
            // Demo AfterSave returned object with trimmed externalRef.
            assertThat(returned.externalRef())
                .isEqualTo("web-014");
            assertThat(original.externalRef())
                .isEqualTo(" web-014 ");

            // 3. MongoDB actually persisted the normalized value.
            Document document = raw(id);
            assertThat(document).isNotNull();
            assertThat(document.getString("normalizedRef"))
                .isEqualTo("WEB-014");
            assertThat(document.getString("externalRef"))
                .isEqualTo(" web-014 ");
            assertThat(document.getInteger("schemaVersion"))
                .isEqualTo(2);
            assertThat(document.get("createdAt"))
                .isInstanceOf(Date.class);
        } finally {
            cleanup(id);
        }
    }

    @Test
    void afterConvertReplacesReturnedEntityNotStoredDocument() {
        String id = newId();

        Document legacy = new Document("_id", id)
            .append("tenantId", "TENANT-TEST")
            .append("externalRef", " old-007 ")
            .append("createdAt", Date.from(
                Instant.parse("2026-11-20T02:00:00Z")));

        try {
            // Raw driver bypasses Spring Data entity callbacks.
            template.getCollection("orders")
                .insertOne(legacy);

            OrderDocument loaded =
                template.findById(id, OrderDocument.class);

            assertThat(loaded).isNotNull();
            assertThat(loaded.normalizedRef())
                .isEqualTo("OLD-007");

            // Yet source BSON still lacks the field.
            assertThat(raw(id).containsKey("normalizedRef"))
                .isFalse();
        } finally {
            cleanup(id);
        }
    }

    @Test
    void directFieldUpdateDoesNotReRunBeforeConvert() {
        String id = newId();

        OrderDocument original = new OrderDocument(
            id,
            "TENANT-TEST",
            " web-014 ",
            null,
            Instant.parse("2026-11-20T02:00:00Z"));

        try {
            template.insert(original);

            template.updateFirst(
                byId(id),
                new Update().set("externalRef", " new-008 "),
                OrderDocument.class);

            Document document = raw(id);
            assertThat(document).isNotNull();
            assertThat(document.getString("externalRef"))
                .isEqualTo(" new-008 ");
            assertThat(document.getString("normalizedRef"))
                .isEqualTo("WEB-014");
        } finally {
            cleanup(id);
        }
    }
}
```

**Test safety:** run these tests only on an isolated TEST MongoDB. `cleanup(id)` deletes only the random ID created by the test, never calling `dropDatabase()` or `deleteMany({})`. If other test suites share the collection, assign separate databases per CI job to prevent interference.

### 14.2. Testing the `BeforeSave` and `AfterSave` Contracts Directly

A small unit test clearly shows that **returning another object does not remap BSON**:

```java
package com.example.shop.orders;

import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveCallback;

import static org.assertj.core.api.Assertions.assertThat;

class ReturnValueContractTest {

    @Test
    void beforeSaveReturningCopyDoesNotChangeDocument() {
        OrderDocument original = new OrderDocument(
            "ORD-X", "TENANT-A", " raw ", null, null);
        Document document = new Document(
            "externalRef", " raw ");

        BeforeSaveCallback<OrderDocument> callback =
            (entity, target, collection) ->
                new OrderDocument(
                    entity.id(), entity.tenantId(),
                    "changed-in-memory",
                    entity.normalizedRef(),
                    entity.createdAt());

        OrderDocument returned = callback.onBeforeSave(
            original, document, "orders");

        assertThat(returned.externalRef())
            .isEqualTo("changed-in-memory");
        assertThat(document.getString("externalRef"))
            .isEqualTo(" raw ");
    }
}
```

This is a **unit test invoking the callback directly**, not proving the full Spring Data pipeline—it demonstrates the exact difference between the **returned entity** and the **Document passed into the callback**. The integration test in section 14.1 proves real MongoDB persisted the expected BSON.

### 14.3. Counterexample Test: No Callback on `updateFirst`

The `directFieldUpdateDoesNotReRunBeforeConvert` test intentionally creates the state:

```javascript
{
  externalRef: " new-008 ",
  normalizedRef: "WEB-014"
}
```

This is **inconsistent data** because `updateFirst` modified only `externalRef`. The test is not encouraging inconsistent writes; it proves callbacks are not database constraints and the app must update both fields in sync.

### 14.4. `AfterSave` Specifically: Returning an Object Different from Persisted BSON

In section 14.1's integration test, `ReturnNormalizedAfterSaveCallback` is registered **for test demonstration**. That intentionally yields three distinct states:

```text
Original Java object:
  externalRef = " web-014 "
  normalizedRef = null

Returned Java object after insert:
  externalRef = "web-014"
  normalizedRef = "WEB-014"

Stored MongoDB Document:
  externalRef = " web-014 "
  normalizedRef = "WEB-014"
  schemaVersion = 2
```

This discrepancy is created intentionally to **prove each callback's contract**. In a real business API, **never let the returned entity and stored document diverge on persistent fields** like this. The test guards against mistaking "the API returned clean values" for "clean BSON was persisted."

### 14.5. Testing Callback Copy Behavior Directly

Sometimes you want a quick unit test without starting MongoDB:

```java
@Test
void immutableBeforeConvertCallbackReturnsCopy() {
    OrderDocument original = new OrderDocument(
        "ORD-X", "TENANT-A",
        " web-014 ", null,
        java.time.Instant.parse("2026-11-20T02:00:00Z"));

    NormalizeOrderRefCallback callback =
        new NormalizeOrderRefCallback();

    OrderDocument result =
        callback.onBeforeConvert(original, "orders");

    assertThat(result).isNotSameAs(original);
    assertThat(result.normalizedRef()).isEqualTo("WEB-014");
    assertThat(original.normalizedRef()).isNull();
}
```

This is a test method snippet assuming JUnit/AssertJ imports in a test class. Unit tests prove Java **copy semantics**, not MongoDB mapping or persistence, so integration tests remain necessary.

## 15. Reactive Integration Tests: Must Verify Subscription Too

With the reactive API, calling `reactiveTemplate.insert(entity)` merely builds a Publisher. Reactive callbacks run along the lifecycle only **when subscribed**:

```java
Mono<OrderDocument> pipeline =
    reactiveTemplate.insert(original);

// At this point, insert has NOT occurred.

StepVerifier.create(pipeline)
    .assertNext(saved -> {
        assertThat(saved.normalizedRef())
            .isEqualTo("WEB-014");
    })
    .verifyComplete();
```

This snippet belongs inside an integration test with `reactiveTemplate`, `original`, `StepVerifier`, and AssertJ imports. The lesson highlights the **difference between assembly and subscription**, not suggesting an imperative callback can modify entities on a reactive template.

### 15.1. What Does a Complete Reactive Test Need?

1. A Spring test context with `ReactiveMongoTemplate` and `ReactiveBeforeConvertCallback<OrderDocument>` registered.
2. An appropriate test MongoDB instance/cluster, never pointing to production.
3. Unique test IDs per test to prevent collisions.
4. `StepVerifier`/subscription awaiting terminal signals.
5. Reading raw BSON via the driver/reactive collection or an isolated client, rather than relying only on `findById` which `AfterConvertCallback` could transform.
6. Deleting only the test-created ID once the Publisher completes, never `deleteMany({})` on a shared collection.

Writing only:

```java
Mono<OrderDocument> unused =
    reactiveTemplate.insert(original);
assertThat(unused).isNotNull();
```

proves only that a Publisher object was created—**not that callbacks, inserts, or commits ran**.

### 15.2. Publishers Returned from Reactive Callbacks Must Emit an Entity

Counterexample:

```java
// COUNTEREXAMPLE: Mono.empty() does not mean "leave unchanged".
@Override
public Publisher<OrderDocument> onBeforeConvert(
        OrderDocument entity, String collection) {
    return Mono.empty();
}
```

For entity-transforming callbacks, Spring Data needs an entity value for the next step. An empty Publisher can leave the save flow without a value or fail. Correct:

```java
return Mono.just(entity);
```

To reject invalid data, emit `Mono.error(new IllegalArgumentException(...))` or an appropriate domain exception; never return `Mono.empty()` expecting the save to roll back with clear business semantics.

## 16. What Happens When a Callback Throws an Exception?

A callback can enforce invariants before saving:

```java
@Component
public final class RejectMissingTenantCallback
        implements BeforeConvertCallback<OrderDocument> {

    @Override
    public OrderDocument onBeforeConvert(
            OrderDocument entity, String collection) {

        if (entity.tenantId() == null
                || entity.tenantId().isBlank()) {
            throw new IllegalArgumentException(
                "Missing tenantId");
        }
        return entity;
    }
}
```

If Spring Data runs this callback pre-conversion and it throws, the save fails **before sending that entity's write command**. For reactive callbacks, signal the error with `Mono.error(...)`.

**However:** never interpret a callback throwing an exception as "every prior change in the workflow rolled back." If the app already wrote an earlier document outside a transaction, a callback failing on the second command does not undo the first write. Transactions are required for multi-document atomicity.

### 16.1. Callbacks Do Not Replace Database Validation

`RejectMissingTenantCallback` covers only writers passing through its mapping path. A `db.orders.insertOne(...)` from `mongosh`, raw MongoDB driver, or another service can still insert a document lacking `tenantId` unless MongoDB enforces a validator or permissions restrict direct writes.

Complementary layers:

| Mechanism | What It Protects |
| --- | --- |
| Bean Validation / service validation | Input/domain objects at app entry points |
| Spring Data EntityCallback | Entities traversing Spring Data mapping checkpoints |
| MongoDB `$jsonSchema` validator | BSON writes subject to server-side validation |
| Unique indexes | Key uniqueness under concurrent writes |
| Authorization / tenant filters | Which data users are permitted to read or write |

Never use callbacks to enforce an **authorization** claim callers could spoof. `tenantId` must be established from a verified security context before reaching repositories; callbacks can check it is non-blank, yet cannot prove the user owns that tenant.

### 16.2. Never Catch Callback Exceptions and Fall Back to the Raw Driver

```java
// COUNTEREXAMPLE: callback failed, so service bypasses and writes raw.
try {
    template.insert(entity);
} catch (Exception ignored) {
    template.getCollection("orders")
        .insertOne(new Document("tenantId", null));
}
```

This is never a valid fallback. It undermines data integrity and turns a real error into an uncontrolled bypass producing corrupt BSON. Instead, handle validation errors cleanly at the API/service layer and prohibit unguarded bypass paths.

## 17. Transactions, Retries, and Callbacks with Side Effects

When `MongoTemplate.save(...)` runs inside a transaction, callbacks execute within that operation's lifecycle, yet **callback completion does not mean the transaction committed**:

```text
Transaction begins
    |
    +-- save(Order A)
    |     BeforeConvert/BeforeSave
    |     MongoDB write in transaction
    |     AfterSaveCallback
    |
    +-- save(Order B)
    |     callback throws
    |
    +-- transaction aborts
          |
          +-- A and B changes not committed
          +-- AfterSave of A had ALREADY RUN
```

Therefore:

- Never send emails, charge payments, or publish non-idempotent messages inside `AfterSaveCallback`.
- Never use callbacks to write an audit document to MongoDB **in a separate session** expecting it to roll back with the outer transaction.
- For durable events, store an **outbox document** in the same transaction and dispatch after commit.
- Callbacks can re-run when the application/driver retries a transaction attempt, so all domain transforms need idempotency/operation IDs.

### 17.1. MongoTemplate Callbacks Do Not Make HTTP Requests Exactly-Once

An API gateway might retry an HTTP POST after a timeout. If a callback generates a fresh random ID so every attempt inserts a new document, the prior transaction may have committed while the retry inserts a duplicate.

A stable strategy:

1. Accept or derive an `operationId` at the API/application boundary.
2. Verify tenant identity and payload validity.
3. Enforce a database ID or unique key preventing duplicate application.
4. Keep callbacks strictly to deterministic entity transformations without side effects.
5. When commit outcome is unknown, **reconcile** by operation ID instead of blindly re-running business mutations.

### 17.2. Avoid Mutating `@Version` or IDs Inside Callbacks

Retries can re-run `BeforeConvertCallback`. If a callback unconditionally sets `version=version+1` or generates a new ID, the retry diverges from the initial attempt's identity, breaking optimistic locking and idempotency. Let store-managed properties stay owned by their proper layers, and normalize only the fields the callback actually owns.

## 18. Performance and Responsible Callback Design

Callbacks lie on the hot path of inserts, saves, and reads. A slow callback degrades latency across the entire repository.

### 18.1. Guiding Principles

- **Pure and deterministic:** string normalization, invariant checks, rule-based defaults.
- **No external API calls** per read/write; note `AfterConvertCallback` can run on thousands of entities in one query.
- **No shared mutable state** inside singleton callback beans; multiple threads call the same bean concurrently.
- **No arbitrary cross-collection writes** inside callbacks; they risk recursion, retry amplification, and broken transaction contexts.
- **Never guess collections:** the `collection` parameter is valuable when entities write to collection overrides; if a callback applies only to `orders`, document the collection-override policy.
- **Keep logic idempotent:** re-saving an already-normalized entity produces no further changes.

### 18.2. Distinguishing Projections from Post-Processing

If the goal is merely formatting `"Web #014"` instead of `" web-014 "` for an API response, a DTO mapper is cleaner than an `AfterConvertCallback` running on **every query** for that entity.

If the goal is a **persisted data invariant**, enforce it pre-conversion and across all write paths rather than cosmetically patching objects on read.

If the goal is **legacy migration**, `AfterConvert` can serve as a temporary read shim while you still audit and backfill real stored data; never mistake clean getter outputs for proof MongoDB was backfilled.

### 18.3. Measure Performance in the Right Places

Track:

- Callback execution counts by entity type and phase.
- Callback latency at p50/p95/p99 on realistic datasets.
- Callback validation failure rates.
- Immutable object allocations/copies under large batch workloads.
- Query latency, BSON conversion time, and MongoDB I/O separately via tracing.
- Slowdowns when `AfterConvert` processes N entities or multiple callbacks duplicate work.

Never attach entity IDs or user IDs as high-cardinality metric labels. Keep debug logging controlled and redact sensitive data.

## 19. Common Error Diagnostic Matrix

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| `withNormalizedRef(...)` called yet MongoDB saves null | Callback created copy yet **returned original** | Return the new instance from `BeforeConvertCallback` |
| Returned Java object has new value, raw BSON still has old | Mutated entity in `BeforeSave`/`AfterSave` after conversion/write | Move persistent changes to `BeforeConvert`, or mutate BSON intentionally |
| `BeforeSaveCallback` calls `document.put("x",...)` yet returned object lacks `x` | `x` is not in the domain model / not remapped | Add property to model if needed; test both returned entity and raw BSON |
| `AfterConvertCallback` returns clean value yet collection holds legacy docs | Read callback only adjusts Java object | Run real migration/backfill; never trust getters as storage proof |
| `MongoTemplate.insert` runs callback, `updateFirst` does not | Direct field update has no full-entity lifecycle | Keep invariants synced in updates or share service helpers |
| Repository save returns new object while original is unchanged | Immutable entity / record | Use the **returned** object instead of relying on in-place mutation |
| `@Version` conflict after copy | Copy dropped/altered version or callback bumped version | Copy all fields accurately; let framework own version |
| Duplicate inserts after callback generates ID | ID regenerated across attempts/retries | Fixed operation ID, unique key, and idempotency |
| Callback never runs | Bean unregistered, wrong generic type, or unsupported API path | Check `ApplicationContext`, interface generics, and template path |
| Sync callback works yet reactive does not | Only `BeforeConvertCallback` registered, missing `ReactiveBeforeConvertCallback` | Register matching reactive API and test subscription |
| Reactive test produces no data | Publisher not subscribed or failed to complete | `StepVerifier.verifyComplete()`, handle errors explicitly |
| Reactive callback returns `Mono.empty()` | Fails to emit entity for checkpoint | Return `Mono.just(entity)` or emit intentional error |
| Callback errors only on another entity type | Overly broad generic callback or lambda type erasure | Use concretely typed classes and test multiple domain types |
| Auditing timestamps overwritten multiple times | Custom callback and auditing both own the field | Assign single owner, explicit ordering, and test updates |
| Event listener edits immutable object yet nothing persists | Events have no value-return replacement contract | Use EntityCallback rather than mutating via events |
| AfterSave sends email then transaction rolls back | AfterSave fires before final transaction commit | Transactional outbox, dispatch after commit |
| Callback ignores subdocuments | Root-level lifecycle differs from nested mapping | Enforce in root callback/service or custom converters where needed |
| Performance degrades after enabling callback | N+1 external calls or heavy work on large reads | Remove external I/O, profile, consider DTO mappers |
| BSON field name mismatches Java property | Ignored `@Field` when mutating `Document` | Check mapped BSON name instead of guessing from getter |
| Raw driver bypasses callback | Driver bypasses Spring Data entity mapping | Use MongoDB validators and cross-writer contracts |

## 20. How to Design Safe Callbacks for Immutable Entities

A review workflow before adding any callback:

1. **Identify the invariant:** do you need to alter a persistent field, BSON metadata, returned entity, or display DTO?
2. **Pick the right checkpoint:** persistent fields → `BeforeConvert`; BSON document → `BeforeSave`; read object → `AfterConvert`; post-save object → `AfterSave` only with strong justification.
3. **Choose the copy pattern:** record constructor, copy constructor, or `with...` method; never drop IDs, versions, or audit attributes.
4. **Stay deterministic:** pure normalization, no HTTP calls, and no fresh random IDs per attempt.
5. **Verify ordering:** do auditing or other callbacks touch the same fields?
6. **Verify API flavor:** imperative or reactive? Are both configured if the app uses both?
7. **Audit all write paths:** are there `updateFirst`, `bulkOps`, raw driver calls, migration scripts, or other services?
8. **Write three-layer tests:** original Java object, returned object, and raw persisted BSON.
9. **Test legacy reads:** confirm `AfterConvert` updates returned objects without writing back to DB.
10. **Check transactions:** how are errors/rollbacks and post-save side effects handled?
11. **Check performance:** how does the callback behave across N entities on large reads, without blocking I/O or excessive allocations?
12. **Plan schema evolution:** migrate new/legacy fields deliberately instead of hiding missing data forever behind `AfterConvert`.

### 20.1. Never Use `BeforeSave` to Modify Persistent Entity Fields When `BeforeConvert` Works

This rule follows directly from execution order:

```text
BeforeConvert:
  OrderDocument E -> return E'
  Converter maps E' -> Document
  => persistent fields of E' are saved.

BeforeSave:
  Converter already produced Document D
  return E' without changing D
  => D still holds values from the prior entity.
```

Learners must separate **the ability to return a new object** (supported by several callbacks) from **whether that checkpoint still shapes persisted data** (which differs). That is the single most important takeaway of this lesson.

### 20.2. When You Only Need a DTO, Callbacks May Be the Wrong Tool

For example, to display `"Web #014"` instead of `" web-014 "` without changing stored data, prefer:

```java
public record OrderResponse(
    String id,
    String displayReference
) {
    public static OrderResponse from(OrderDocument order) {
        return new OrderResponse(
            order.id(),
            order.externalRef().trim());
    }
}
```

Keeping formatting in API mappers lets entities accurately mirror persisted data, avoids running `AfterConvert` on every query, and prevents masking legacy data issues. Callbacks remain useful when **every domain read** genuinely shares a consistent conversion rule.

## 21. Applied Exercises

A shipping service manages the `shipments` collection:

```javascript
{
  _id: "SHIP-001",
  tenantId: "TENANT-A",
  rawTrackingCode: "  abc-789 ",
  trackingCode: "ABC-789",
  carrier: "VNPOST",
  createdAt: ISODate("2026-11-20T02:00:00Z"),
  schemaVersion: 2
}
```

Design requirements for immutable entities and callbacks:

### Exercise 1 — Immutable Record

Create a `ShipmentDocument` record with `@Id String id`, `tenantId`, `rawTrackingCode`, `trackingCode`, `carrier`, and `createdAt`. Provide `withTrackingCode(String)` returning a new copy preserving all other fields.

Verify:

```java
ShipmentDocument original = new ShipmentDocument(
    "SHIP-001", "TENANT-A",
    "  abc-789 ", null, "VNPOST", createdAt);

ShipmentDocument next =
    original.withTrackingCode("ABC-789");
```

Here `createdAt` is a prepared `Instant`. Explain why `original.trackingCode()` remains null.

### Exercise 2 — `BeforeConvertCallback`

Write `BeforeConvertCallback<ShipmentDocument>`:

- Reject blank tracking codes.
- Normalize via `trim().toUpperCase(Locale.ROOT)`.
- If already normalized, return the same instance.
- Otherwise return a new copy.
- Preserve `id`/`tenantId`/`createdAt`.

Compare two implementations:

```java
// Wrong
entity.withTrackingCode(normalized);
return entity;

// Correct
return entity.withTrackingCode(normalized);
```

### Exercise 3 — `BeforeSaveCallback`

Write `BeforeSaveCallback<ShipmentDocument>`:

```java
document.put("schemaVersion", 2);
return entity;
```

Why does this persist `schemaVersion` even though the record has no matching property? If you only return a copied record with a new `trackingCode` without modifying `document`, how does the persisted BSON still diverge?

### Exercise 4 — `AfterSaveCallback`

Create a demo callback returning a new `ShipmentDocument` with normalized `carrier` on the **returned object**, without changing BSON. Write a test comparing the object returned from save against actual BSON. Explain why you should not use this for persistent fields in production, and why `AfterSaveCallback` is not an after-commit event.

### Exercise 5 — `AfterConvertCallback`

Seed a legacy document lacking `trackingCode` via the raw driver. Use `AfterConvertCallback` to return a copy deriving `trackingCode` from `rawTrackingCode` on read. Write tests proving:

- `findById` returns `trackingCode="ABC-789"`.
- Raw BSON still lacks `trackingCode`.
- Only an explicit write persists the field.

### Exercise 6 — Auditing and Ordering

Add `@CreatedDate` and `@LastModifiedDate`, enabling Mongo auditing accordingly. If a custom callback also assigns `createdAt`, what ordering must be defined and why should there be only one owner?

### Exercise 7 — `updateFirst` Bypasses the Lifecycle

Try:

```java
template.updateFirst(
    Query.query(Criteria.where("_id").is("SHIP-001")),
    new Update().set("rawTrackingCode", " xy-901 "),
    ShipmentDocument.class);
```

Explain why `trackingCode` can remain `"ABC-789"`. Fix the update to atomically update **both fields** using the service's shared normalization rule.

### Exercise 8 — Reactive Callbacks

Write a `ReactiveBeforeConvertCallback<ShipmentDocument>` returning `Mono.just(copy)` or `Mono.fromSupplier(...)`. Use `StepVerifier` to test inserting and reading BSON after subscription. Explain why `Mono.empty()` and calling `subscribe()` inside callbacks are unsafe.

### Exercise 9 — Testing and Data Protection

Add integration tests covering:

1. Original entity immutability.
2. Returned entity differs from original when normalization occurs.
3. Raw BSON reflects `BeforeConvert` and `BeforeSave`.
4. `AfterConvert` does not auto-migrate legacy data.
5. Direct updates and raw driver writes skip callbacks.
6. Validation errors in callbacks block writes.
7. Duplicate IDs and `@Version` are handled at the proper layers without callbacks inventing new IDs.
8. Transaction rollbacks do not undo external side effects placed in `AfterSave`.

### Solution Strategy

**Separate three layers of state:** the Java entity before the callback, the entity returned by the callback, and the actual BSON in the database. Assert all three. Use `BeforeConvert` for **persisted field values**, `BeforeSave` for **mapped BSON**, and `AfterConvert`/`AfterSave` only to adjust returned Java objects with clear justification. Never expand callback responsibilities into database constraints, authorization, or outbox workflows.

## 22. References

- Spring Data MongoDB — [Lifecycle Events and Entity Callbacks](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html): lifecycle checkpoints, distinguishing event listeners from entity callbacks, sync/reactive callback tables.
- Spring Data Commons — [Entity Callbacks](https://docs.spring.io/spring-data/commons/reference/entity-callbacks.html): value-returning callbacks, ordering, type filtering, and immutable entities.
- Spring Data MongoDB API — [BeforeConvertCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/BeforeConvertCallback.html): returns the entity used prior to conversion.
- Spring Data MongoDB API — [BeforeSaveCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/BeforeSaveCallback.html): `Document` already constructed; only mutating `Document` alters the written payload.
- Spring Data MongoDB API — [AfterSaveCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/AfterSaveCallback.html): returned entity after save.
- Spring Data MongoDB API — [AfterConvertCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/AfterConvertCallback.html): returned entity after load and conversion.
- Spring Data MongoDB API — [ReactiveBeforeConvertCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/ReactiveBeforeConvertCallback.html): Publisher emitting entity prior to conversion.
- Spring Data Commons — [Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/object-mapping.html): immutable properties, constructors, withers, and copy instantiation during mapping.
- Spring Data MongoDB — [Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): `@Id`, `@Field`, converters, and BSON persistence.
- Project Reactor — [Reference Guide](https://projectreactor.io/docs/core/release/reference/): subscription, `Mono`/`Flux`, and reactive chains.

## Key Takeaways

**With immutable entities, a callback must return the exact instance it wants Spring Data to use; calling `with...` and discarding the return value has no effect.** `BeforeConvertCallback` modifies persistent entities **before BSON mapping**, so the returned copy affects persisted data. `BeforeSaveCallback` runs **after mapping**; to alter the BSON being written, you must mutate `org.bson.Document`, not merely return a new entity. `AfterSaveCallback` and `AfterConvertCallback` can replace the **returned Java object** without writing back to MongoDB. To prevent divergence across original, returned, and stored state, assert all three in integration tests, keep callbacks deterministic, distinguish reactive from sync APIs, protect `@Id`/`@Version`, and never substitute callbacks for database validation, authorization, or transactions/outboxes.
