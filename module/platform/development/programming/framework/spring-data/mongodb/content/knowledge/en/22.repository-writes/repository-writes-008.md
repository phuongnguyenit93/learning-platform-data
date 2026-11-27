# Soft Delete via Consistent Read Conditions and Update Commands

> **Chapter:** Repository Writes  
> **Module:** `SPRING_DATA_MONGODB`

**Soft delete** is a technique that marks a document as no longer visible in normal business workflows without **physically removing** it from MongoDB. It is useful when you need to restore orders, audit operation history, protect referential relationships, or defer physical deletion per data retention policies. However, simply adding a `deleted = true` field is **not enough**: if repositories still call default `findById()` or `findAll()`, deleted records can still leak through; if deletion merely reads an entity and calls `save`, concurrent changes or BSON fields absent from the Java model can be overwritten.

A reliable implementation must unify **both halves of the contract**:

- **Read path**: all business queries that should return active records must enforce tenant/permission scoping and the **not-deleted** state; only admin/recovery read paths may see tombstones.
- **Write path**: soft-delete operations must perform a **single-document atomic update**, verify the record is still active at the expected version, and set deletion flags and metadata; every other write operation must also respect the deleted state.

This lesson belongs to the `SPRING_DATA_MONGODB` module: connecting and mapping documents, operating via `MongoTemplate` or repositories, query design, aggregations, indexes, transactions, reactive access, testing, and performance diagnostics. This section focuses on **consistency between read conditions and update commands in the Repository Writes chapter**, never conflating soft delete with physical delete commands.

## 1. Learning objectives

After this lesson, you will be able to:

1. Define `ACTIVE`/`DELETED` states and data invariants for `deleted`, `deletedAt`, `deletedBy`, and `version`.
2. Write repository methods reading only non-deleted documents; explain why inherited `findById`, `findAll`, `count`, and `existsById` **do not automatically apply soft-delete filters**.
3. Distinguish derived finders from `@Query` when needing tenant constraints, `OR` grouping, and legacy documents missing fields.
4. Build conditional soft-delete commands via repository `@Query` + `@Update` or custom repository fragments backed by `MongoTemplate`.
5. Protect records from lost updates using **expected version**, inspect matched counts, and handle retries/idempotency.
6. Design restoration, conditional unique indexes, legacy data migrations, and physical purge policies after retention periods.
7. Write integration tests against real BSON proving zero tombstone leaks and zero cross-tenant modifications.

## 2. Finalize the data contract before writing repositories

We use an `orders` collection in a multi-tenant system. Proposed schema:

```javascript
{
  _id: "ORD-101",
  tenantId: "TENANT-A",
  orderCode: "SO-2026-101",
  status: "PAID",
  deleted: false,         // BSON Boolean, explicitly present
  version: NumberLong(3),
  updatedAt: ISODate("2026-11-19T08:00:00Z")
  // deletedAt/deletedBy absent while ACTIVE.
}
```

When soft-deleted:

```javascript
{
  _id: "ORD-101",         // ID PRESERVED
  tenantId: "TENANT-A",
  orderCode: "SO-2026-101",
  status: "PAID",         // prior business status preserved
  deleted: true,
  deletedAt: ISODate("2026-11-20T03:00:00Z"),
  deletedBy: "user-42",
  version: NumberLong(4),
  updatedAt: ISODate("2026-11-20T03:00:00Z")
}
```

### 2.1. State table

| State | `deleted` | `deletedAt` | `deletedBy` | Business queries |
| --- | --- | --- | --- | --- |
| `ACTIVE` | BSON `false` | Absent | Absent | Readable when tenant/permissions and other filters match |
| `DELETED` | BSON `true` | UTC timestamp | Verified actor ID | Excluded from normal queries |
| `RESTORED` | BSON `false` | Cleared or archived to audit log | Cleared or archived to audit log | Readable again if business constraints pass |

**Critical invariant:** in the canonical schema, every active document must have an **explicit** `deleted: false`. Never mix `false`, `null`, and missing fields without a compatibility plan. When a document is deleted, record timestamp and actor per audit policy; if audit metadata must be immutable, also write a separate event history rather than relying solely on two fields that can be cleared on restore.

### 2.2. Why not use deletedAt alone?

An alternative is treating `deletedAt != null` as deleted. That approach works, yet remember in MongoDB `{ deletedAt: null }` matches both **BSON null** and **missing fields**. When using predicates such as `$ne: null`, `$exists`, or partial indexes, semantics can diverge from Java intuition.

This lesson uses **Boolean `deleted` as the source of truth for state**, and `deletedAt`/`deletedBy` as metadata. If a project chooses a `deletedAt`-only model, rewrite **every** finder, update predicate, index, and test accordingly; never mix both conventions in the same system.

### 2.3. Flipping a flag vs. real deletion

A soft-delete operation **never** calls `MongoRepository.delete(...)`, `deleteById(...)`, `MongoTemplate.remove(...)`, or `deleteMany(...)`. Those methods normally perform **physical deletion** of documents. Even a derived repository method `deleteByStatus(...)` will not automatically turn into setting `deleted = true`.

Soft delete in this lesson is a **conditional update**. Physical deletion belongs strictly to a separate retention/purge workflow with its own permissions, logging, and recovery policy.

## 3. Business flows requiring consistency

```text
                       HTTP / Service
                            |
                  check tenant permissions
                            |
         +------------------+------------------+
         |                                     |
     READ ACTIVE                           SOFT DELETE
         |                                     |
 tenantId = allowedTenant             tenantId = allowedTenant
 AND deleted = false                 AND _id = requestedId
 AND business filters                AND deleted = false
         |                            AND version = expectedVersion
         v                                     |
  Repository finder                            v
  / Query / count                         Atomic $set flags
  / exists / aggregation                  + $inc version
         |                                     |
         v                                     v
  tombstones hidden                      matchedCount = 1 ?
                                               |
                                 +-------------+--------------+
                                 |                            |
                            Yes: success              No: conflict/not found/
                                                      already deleted/wrong tenant
```

An application might hide tombstones in list views yet still fail if detail lookups by ID, total counts, searches, exports, or aggregations omit `deleted: false`. Conversely, read filters might be airtight while soft deletion remains broken if an ID-based update omits tenant, active state, or current version.

### 3.1. Scenarios to specify upfront

- First deletion: transitions `ACTIVE` to `DELETED`, increments version once.
- Deleting the same document again: choose **no-op** (state-based idempotency) or conflict per API contract; never randomly overwrite the original `deletedAt`/`deletedBy`.
- Two concurrent deletions: one update matches; the other fails version/state check.
- Deletion concurrent with payment: order status updates must also check `deleted: false` and version so they never mutate a deleted document.
- Reading another tenant's document: never return the document or leak its existence via overly specific error messages.
- Restoration: a separate **conditional state transition** with its own permissions and unique-key constraints.

## 4. Java entity: mapping deletion flag, metadata, and version

File `OrderDocument.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String tenantId,
    String orderCode,
    String status,
    Boolean deleted,
    Instant deletedAt,
    String deletedBy,
    @Version Long version,
    Instant updatedAt
) {}
```

`@Id` maps `id` to BSON `_id`. In this example, `ORD-101` is a String ID that is not a 24-hex-character ObjectId. Real projects must verify the stored BSON `_id` type, especially when String IDs could convert to ObjectId under default mapping rules.

`Boolean deleted` is used instead of primitive `boolean` so Java can still represent `null`/missing fields when reading legacy documents. However, **repository finder `findByDeletedFalse` matches only BSON literally equal to `false`**; reading a Java default into memory does not add the field to MongoDB. Standardize `deleted: false` on writes and via migration.

`@Version Long version` gives Spring Data's `save` paths optimistic locking, yet **does not make `@Update` or raw updates automatically check `expectedVersion`**. When using partial updates, write explicit version filters and increment version in the same command.

### 4.1. Why not use save for soft delete?

The code below looks reasonable but carries risks:

```java
// ANTI-PATTERN: read-modify-save full entity simulation.
OrderDocument original = repository.findById("ORD-101")
    .orElseThrow();

OrderDocument deleted = new OrderDocument(
    original.id(),
    original.tenantId(),
    original.orderCode(),
    original.status(),
    true,
    Instant.now(),
    "user-42",
    original.version(),
    Instant.now()
);
repository.save(deleted);
```

With `@Version` and acknowledged write concern, `save` can catch stale writes, yet it **replaces the document with the entity representation**. If BSON contains `legacyIntegration`/`externalMetadata` unknown to `OrderDocument`, those fields **risk disappearing** after `save`. Soft deletion only modifies a few fields, so an **atomic partial update** is usually much safer.

## 5. Repository finders: always constrain deleted = false

File `OrderRepository.java`:

```java
package com.example.shop.orders;

import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    // Reading by ID must check both tenant and non-deleted status.
    Optional<OrderDocument> findByIdAndTenantIdAndDeletedFalse(
        String id, String tenantId);

    Page<OrderDocument> findByTenantIdAndDeletedFalse(
        String tenantId, Pageable pageable);

    List<OrderDocument> findByTenantIdAndDeletedFalseAndStatus(
        String tenantId, String status);

    long countByTenantIdAndDeletedFalse(String tenantId);

    boolean existsByIdAndTenantIdAndDeletedFalse(
        String id, String tenantId);

    // Admin read path, invoke only after checking special privileges.
    Optional<OrderDocument> findByIdAndTenantIdAndDeletedTrue(
        String id, String tenantId);

    @Query("""
        {
          'tenantId': ?0,
          'deleted': false,
          '$or': [
            { 'status': 'NEW' },
            { 'status': 'PAID' }
          ]
        }
        """)
    List<OrderDocument> findActiveNewOrPaid(String tenantId);
}
```

Here:

- `DeletedFalse` is a **derived condition on the Java property** `deleted`; Spring Data sends the corresponding filter to MongoDB.
- `Pageable` supports pagination and sorting; cap page sizes at the service/API boundary.
- `countBy...DeletedFalse` and `existsBy...DeletedFalse` must share the exact same contract as finders, or UI totals will include deleted records.
- `@Query` intentionally puts `tenantId` and `deleted: false` **outside the `$or` group** so all branches remain bounded.
- `findByIdAndTenantIdAndDeletedTrue` is solely an admin/recovery tombstone reader and **must never be exposed unchecked** to clients.

### 5.1. Inherited methods do NOT automatically hide deleted records

Because the repository still `extends MongoRepository<...>`, these inherited APIs exist:

```java
repository.findById(id);
repository.findAll();
repository.existsById(id);
repository.count();
repository.deleteById(id);
repository.delete(entity);
repository.deleteAll();
```

**There is no default mechanism attaching `deleted: false` to all those methods merely because the entity has a `deleted` field.** `findById`, `findAll`, `existsById`, and `count` can still see tombstones; `deleteById`/`deleteAll` can physically delete documents.

Therefore, structure your architecture so business layers only call **policy-enforced** methods:

- Keep repositories in the persistence layer; never expose the raw interface to controllers.
- Wrap operations in authorized services with clear names like `getVisibleOrder`/`listVisibleOrders`.
- Use code reviews and tests to forbid calling unfiltered methods.
- If multiple domains need soft delete, consider a custom base repository implementation or dedicated abstraction—just design it consistently across find, count, exists, aggregation, raw template, and delete; **never assume an ORM-style global filter exists by default**.

### 5.2. A single query missing the delete condition is still a bug

```java
// ANTI-PATTERN: restricts tenant only, still exposes tombstones.
Page<OrderDocument> findByTenantId(
    String tenantId, Pageable pageable);
```

Use:

```java
Page<OrderDocument> findByTenantIdAndDeletedFalse(
    String tenantId, Pageable pageable);
```

When writing queries with `MongoTemplate` or aggregations, apply the same filter there too. Repository filters do not propagate to the raw driver, aggregation pipelines, or queries constructed in another service.

## 6. Repository @Query + @Update: updating instead of physical deletion

Spring Data MongoDB supports repository update methods with `@Update` on versions offering that API. This is a concise option when filters and update payloads are **fixed**.

Add to a dedicated repository or inside `OrderRepository`:

```java
import java.time.Instant;
import org.springframework.data.mongodb.repository.Query;
import org.springframework.data.mongodb.repository.Update;

public interface OrderStatusUpdateRepository
        extends org.springframework.data.mongodb.repository.MongoRepository<
            OrderDocument, String> {

    @Query("""
        {
          '_id': ?1,
          'tenantId': ?0,
          'deleted': false,
          'version': ?2
        }
        """)
    @Update("""
        {
          '$set': {
            'deleted': true,
            'deletedAt': ?3,
            'deletedBy': ?4,
            'updatedAt': ?3
          },
          '$inc': { 'version': 1 }
        }
        """)
    long markDeleted(
        String tenantId,
        String id,
        long expectedVersion,
        Instant deletedAt,
        String actorId
    );
}
```

**Mechanics to understand:**

1. `@Query` expresses **exact ID + tenant + not deleted + current version**.
2. `@Update` builds an update `$set`ting metadata and `$inc`rementing version—not a `delete` command.
3. The `long` return indicates how many documents were updated by the query. Since the filter includes `_id`, valid values are **0 or 1**.
4. `@Update` executes directly on the database, **without relying on lifecycle callbacks** or running automatic optimistic locking like `repository.save`. Thus expected version and version increment must be in the query/update.
5. Supported syntax, binding, and return types must be tested against your **actual Spring Data MongoDB version**; if you need richer result inspection or dynamic conditions, use the repository fragment in the next section.

Avoid creating a second repository solely for one method unless needed; in real projects, **keep the method inside `OrderRepository`**. The separate interface here merely illustrates `@Query` + `@Update` without mixing it with the fragment example below.

### 6.1. How to handle the update result?

```java
long changed = statusUpdateRepository.markDeleted(
    "TENANT-A",
    "ORD-101",
    3L,
    Instant.parse("2026-11-20T03:00:00Z"),
    "user-42"
);

if (changed == 0) {
    // Do not guess the cause, since the filter checks multiple conditions.
    throw new IllegalStateException(
        "Not found, or status/version changed");
}
```

This example assumes `statusUpdateRepository` is injected and `tenantId`/`actorId` were authenticated. Never trust these values simply because they arrived in a request. In a real endpoint, 0 matching records can mean not found, already deleted, stale version, or unauthorized tenant; avoid leaking the existence of another tenant's order.

## 7. Custom repository fragment: explicit conditional update commands

When you need input validation, detailed results, audit rules, or restoration logic, a **repository fragment** backed by `MongoTemplate` scales cleanly.

```text
OrderRepository
  ├── MongoRepository<OrderDocument, String>
  └── OrderSoftDeleteOperations
        └── OrderSoftDeleteOperationsImpl
              └── MongoTemplate + Query + Criteria + Update
```

File `OrderSoftDeleteOperations.java`:

```java
package com.example.shop.orders;

public interface OrderSoftDeleteOperations {
    boolean softDelete(
        String permittedTenantId,
        String id,
        long expectedVersion,
        String actorId);

    boolean restore(
        String permittedTenantId,
        String id,
        long expectedVersion);
}
```

File `OrderSoftDeleteOperationsImpl.java`:

```java
package com.example.shop.orders;

import java.time.Clock;
import java.time.Instant;
import java.util.Objects;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public class OrderSoftDeleteOperationsImpl
        implements OrderSoftDeleteOperations {

    private final MongoTemplate template;
    private final Clock clock;

    public OrderSoftDeleteOperationsImpl(
            MongoTemplate template, Clock clock) {
        this.template = template;
        this.clock = clock;
    }

    @Override
    public boolean softDelete(
            String permittedTenantId,
            String id,
            long expectedVersion,
            String actorId) {

        validate(permittedTenantId, id, expectedVersion);
        if (actorId == null || actorId.isBlank()) {
            throw new IllegalArgumentException("actorId is blank");
        }

        Instant now = clock.instant();

        Query filter = Query.query(
            Criteria.where("id").is(id)
                .and("tenantId").is(permittedTenantId)
                .and("deleted").is(false)
                .and("version").is(expectedVersion));

        Update patch = new Update()
            .set("deleted", true)
            .set("deletedAt", now)
            .set("deletedBy", actorId)
            .set("updatedAt", now)
            .inc("version", 1L);

        return template.updateFirst(
            filter, patch, OrderDocument.class
        ).getMatchedCount() == 1;
    }

    @Override
    public boolean restore(
            String permittedTenantId,
            String id,
            long expectedVersion) {

        validate(permittedTenantId, id, expectedVersion);
        Instant now = clock.instant();

        Query filter = Query.query(
            Criteria.where("id").is(id)
                .and("tenantId").is(permittedTenantId)
                .and("deleted").is(true)
                .and("version").is(expectedVersion));

        Update patch = new Update()
            .set("deleted", false)
            .unset("deletedAt")
            .unset("deletedBy")
            .set("updatedAt", now)
            .inc("version", 1L);

        return template.updateFirst(
            filter, patch, OrderDocument.class
        ).getMatchedCount() == 1;
    }

    private static void validate(
            String tenantId, String id, long expectedVersion) {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(id, "id");

        if (tenantId.isBlank() || id.isBlank()
                || expectedVersion < 0) {
            throw new IllegalArgumentException(
                "Invalid tenant, ID, or version");
        }
    }
}
```

`Criteria.where("id")` uses the **Java property name**, which Spring Data maps to BSON `_id` via `MongoTemplate` entity mapping. `Update` touches only the soft-delete and version fields; fields like `orderCode`, `status`, or legacy metadata are **not rewritten**.

**Regarding `@Version`:** some Spring Data MongoDB update APIs auto-increment version if the update omits version. Here `inc("version", 1L)` is written **explicitly** in `Update` to express complete CAS; the framework should not add a second version increment when version is already present in the update. Test the resulting version after each command against your actual dependency version.

### 7.1. Composing the fragment into OrderRepository

Update the initial repository signature to:

```java
package com.example.shop.orders;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String>,
                OrderSoftDeleteOperations {

    // Keep the DeletedFalse finders declared in Section 5.
}
```

Spring Data composes `OrderSoftDeleteOperationsImpl` into the repository by fragment interface naming and the `Impl` suffix when package scanning/bean registration match. If your project has multiple implementations or customized suffixes, check actual configuration. A `Clock` bean (e.g., `Clock.systemUTC()`) must be supplied to the constructor and can be swapped for a fixed clock in tests.

Example `Clock` configuration:

```java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClockConfig {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

### 7.2. Should you use boolean as the return type?

`true` means the update **matched exactly one document**, while `false` means **no match**. It intentionally avoids distinguishing not found, already deleted, stale version, or wrong tenant—which helps prevent information leakage. If the service must return `409 Conflict` for stale version and `404 Not Found` for missing documents, perform a follow-up read **after** CAS fails, strictly within tenant/authorization boundaries, accepting that data may continue changing concurrently.

**Never auto-retry with the latest version** on soft delete: doing so could delete an order that just transitioned to a state where deletion is disallowed. If retrying, re-read, re-evaluate business rules, and apply clear idempotency rules.

## 8. Why check status and version in the same command?

Consider this unsafe flow:

```text
Request A                     Request B
   |                             |
   |-- findById ORD-101 ----------|
   |  sees deleted=false          |
   |                              |-- updates status to PAID
   |                              |-- increments version 3 -> 4
   |-- update { _id: ORD-101 }     |
   |   set deleted=true           |
   v                              v
Order whose business state changed gets deleted under a stale decision.
```

Even if the initial read filtered `deleted=false`, the **subsequent write** can still act on stale state. Fix this with **a single atomic update command**:

```javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    tenantId: "TENANT-A",
    deleted: false,
    version: NumberLong(3)
  },
  {
    $set: {
      deleted: true,
      deletedAt: ISODate("2026-11-20T03:00:00Z"),
      deletedBy: "user-42",
      updatedAt: ISODate("2026-11-20T03:00:00Z")
    },
    $inc: { version: NumberLong(1) }
  }
)
```

The filter and mutation of **a single document** are executed atomically by MongoDB under its update contract. If version changed, the query no longer matches; if the document was already deleted, `deleted=false` no longer matches. That is why you should never use a "`find` then `update` by ID" pattern that omits status/version preconditions from the write command.

### 8.1. @Version with save is not the only solution

For entities with `@Version`, `repository.save(entity)` on a stale entity can throw `OptimisticLockingFailureException` (when write concern acknowledges results). Yet as noted earlier, saving the entire entity can drop unmapped BSON fields. A version-conditioned `$set` both **preserves other fields** and **prevents stale writes**.

If your application uses optimistic locking elsewhere, best consistency comes when **all operations also check `deleted=false`** before modifying active orders. Otherwise, a payment worker running after deletion could write business updates into a tombstone if its query skips `deleted`.

### 8.2. Contention scenarios

| Scenario | Guard condition | Expected outcome |
| --- | --- | --- |
| A and B both soft-delete version 3 | `version=3 AND deleted=false` | One command matches; the other does not match |
| Soft delete concurrent with status update | Both check version and `deleted=false` | Only one change based on version 3 succeeds |
| Repeated soft delete after timeout | `deleted=false` and expected version | Does not overwrite original deletion time/actor |
| Restore a tombstone at version 4 | `deleted=true AND version=4` | Transitions to active and version 5 |
| Update another tenant's order | Mandatory `tenantId` | Does not match and leaks no data |
| Document physically deleted between steps | Update by ID fails to match | Does not auto-upsert |

### 8.3. Do not guess outcomes after a timeout

If a client times out on an update command, the server may have executed it while the response was lost. Never mutate actor/timestamp and blindly retry forever. Look up the latest state within the authorized tenant, check `version`/audit event/idempotency key, and return the appropriate outcome; if indeterminate, record an unknown state for reconciliation.

For instance, when a soft-delete request carries a unique `requestId`, high-accuracy systems can persist deletion operation IDs or audit records under a unique key. That distinguishes retries of **the same intent** from a new request issued after state changed.

## 9. Reads and updates must share the same definition of "active"

This is a very common design flaw:

```text
Repository list     -> filters deleted=false
Repository findById -> no filter
MongoTemplate count -> no filter
Aggregation export  -> missing $match deleted=false
Soft delete update  -> filters by _id only
```

As a result, the app may hide a record from list pages (returning 404 there) yet still serve it from a detail endpoint, report wrong totals, or keep modifying a deleted order. No standard `@Document` annotation automatically forces every API to obey a global soft-delete filter.

### 9.1. Minimum conventions per read path

| Read path | Safe query |
| --- | --- |
| View detail | `_id = id AND tenantId = permittedTenantId AND deleted = false` |
| Paginated list | `tenantId = permittedTenantId AND deleted = false` + filter/sort/page |
| Count active orders | `tenantId = permittedTenantId AND deleted = false` |
| Check existence | `_id = id AND tenantId = permittedTenantId AND deleted = false` |
| Search by status | Status filter **AND** tenant **AND** deleted false |
| Reporting aggregation | `$match` stage with tenant/permissions and `deleted=false` |
| Admin tombstone API | `tenantId` and `deleted=true`, plus admin privilege check |
| Exports/Batch jobs | Explicitly decide whether tombstones are excluded; never rely on defaults |

### 9.2. MongoTemplate does not inherit filters from repositories

```java
Query query = Query.query(
    Criteria.where("tenantId").is(permittedTenantId)
        .and("deleted").is(false)
        .and("status").is("PAID"));

List<OrderDocument> paidOrders =
    template.find(query, OrderDocument.class);
```

If a service uses `MongoTemplate` instead of a repository, it must add the soft-delete condition to `Query`/`Criteria` itself. With complex dynamic filters, write a clearly named helper such as `activeOrdersOfTenant(...)` and test that every AND/OR branch stays inside tenant/active bounds.

### 9.3. OR must never escape the scope

**Correct:**

```javascript
db.orders.find({
  tenantId: "TENANT-A",
  deleted: false,
  $or: [
    { status: "NEW" },
    { status: "PAID" }
  ]
})
```

**Wrong:**

```javascript
db.orders.find({
  $or: [
    { tenantId: "TENANT-A", deleted: false, status: "NEW" },
    { status: "PAID" }
  ]
})
```

The second query returns every `PAID` order, including deleted documents and other tenants' orders. Functional tests using data from a single tenant might miss this bug; tests must include **other-tenant records and tombstones with the same status**.

### 9.4. Sorting and pagination

```java
PageRequest page = PageRequest.of(
    0, 20,
    Sort.by(
        Sort.Order.desc("updatedAt"),
        Sort.Order.desc("id")));

Page<OrderDocument> result =
    repository.findByTenantIdAndDeletedFalse(
        "TENANT-A", page);
```

This snippet lives inside a service holding `repository` and requires importing `Page`, `PageRequest`, and `Sort`. Including `id` guarantees deterministic ordering when timestamps tie; enforce page size limits at the API so users cannot request unbounded pages. Page counts shift if documents are soft-deleted between page fetches; for stable traversal of large datasets, consider keyset/scrolling pagination with non-null sort keys and appropriate snapshot policies.

## 10. Legacy data missing deleted: false

Suppose a legacy document:

```javascript
{
  _id: "ORD-LEGACY",
  tenantId: "TENANT-A",
  status: "NEW",
  version: NumberLong(2)
  // No deleted, deletedAt, or deletedBy.
}
```

In MongoDB:

```javascript
db.orders.find({ deleted: false })
```

**does not match** this document because the `deleted` field is missing. If the new application switches all finders to `DeletedFalse` immediately, old orders can **vanish from the UI** even though they were never deleted.

### 10.1. Prefer backfilling to the canonical convention

After inventorying the data and evaluating active writers:

```javascript
// Migration example: only on documents MISSING the deleted field.
db.orders.updateMany(
  { deleted: { $exists: false } },
  { $set: { deleted: false } }
)
```

For BSON `deleted: null`:

```javascript
// Only run if business logic confirms null means not deleted.
db.orders.updateMany(
  { deleted: { $type: "null" } },
  { $set: { deleted: false } }
)
```

Never assume every `null` means active if the legacy system used `null` for something else. With multiple writers, plan the rollout carefully: old writers could keep inserting documents without the field after backfill, reintroducing the issue. Deploy updated writers, inspect BSON type distributions, and run verifiable batched migrations.

### 10.2. Dual-format transition period for reads

If you must read before backfill finishes, you can temporarily define "active" as:

```javascript
{
  tenantId: "TENANT-A",
  $or: [
    { deleted: false },
    { deleted: { $exists: false } }
  ]
}
```

Temporary repository method:

```java
@Query("""
    {
      'tenantId': ?0,
      '$or': [
        { 'deleted': false },
        { 'deleted': { '$exists': false } }
      ]
    }
    """)
List<OrderDocument> findLegacyAwareActive(String tenantId);
```

This is a **temporary bridge**, not a permanent default. If soft deletion is permitted on documents missing the field, **update commands must use the same active definition** and handle compatible version fields. If only finders change to show legacy records while updates still require `deleted:false`, users will see orders they cannot delete.

The clean long-term state is **complete backfill**, ensuring writers always store `deleted:false`, and using one single predicate for both reads and writes. Adding `$or` for legacy data can also impact index selectivity; measure it.

### 10.3. Legacy documents missing version

Adding `@Version Long version` to the Java model does not populate `version` in MongoDB. Legacy documents missing `version` can map to `null`; queries checking `version: NumberLong(0)` will not match them.

If the system adopts optimistic locking, backfill `version` and update active writers before enforcing strict CAS:

```javascript
// Example, only after verifying concurrency policy.
db.orders.updateMany(
  { version: { $exists: false } },
  { $set: { version: NumberLong(0) } }
)
```

Never increment or reset the version of documents that already have one. If a legacy source stored `version` as a String, perform a dedicated BSON type migration; custom reading converters **do not** automatically make BSON `NumberLong` comparisons match legacy Strings in updates.

## 11. Restoration: reversing state without erasing history

Restoration (*restore/undelete*) is not merely calling `repository.save` with `deleted=false`. It must verify:

- The document is currently in `deleted=true` state.
- The caller has permission to restore within the tenant.
- The expected version still matches.
- No unique business key or new business constraint is violated.
- History of who deleted it and when remains in the audit log if required.

### 11.1. Conditional restore command

```javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    tenantId: "TENANT-A",
    deleted: true,
    version: NumberLong(4)
  },
  {
    $set: {
      deleted: false,
      updatedAt: ISODate("2026-11-20T04:00:00Z")
    },
    $unset: { deletedAt: "", deletedBy: "" },
    $inc: { version: NumberLong(1) }
  }
)
```

The `restore(...)` method in Section 7's fragment implements the same idea. Once restored, the document reappears in `DeletedFalse` finders, though if the order already has a non-restorable status, the service must block restoration upfront or include status preconditions in CAS.

### 11.2. Do not lose audit history

If `deletedAt` and `deletedBy` are the **only** audit source, `$unset` during restore erases the record of the deletion. In systems requiring traceability, write an immutable audit event such as:

```javascript
{
  orderId: "ORD-101",
  tenantId: "TENANT-A",
  action: "RESTORED",
  actorId: "admin-5",
  occurredAt: ISODate("2026-11-20T04:00:00Z")
}
```

If the audit log lives in another collection and must stay strictly consistent with the restore command, consider a multi-document transaction where supported or outbox/event-driven consistency where appropriate. A single-document `updateFirst` alone does not guarantee an audit event in another collection is written atomically.

### 11.3. Restore commands also need idempotency

A successful restore flips `deleted=true` to `false` and increments version. A second restore with the same expected version will not match; never auto-create a new document. If the API wants to return "already restored" on retry, match against a request ID or valid state rather than swallowing every failure.

## 12. Unique indexes and reusing codes after soft delete

Soft delete keeps old documents in the collection, so an ordinary unique index on `(tenantId, orderCode)` **still treats tombstones as occupying those keys**.

Example:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderCode: 1 },
  { unique: true, name: "uq_all_orders_by_tenant_code" }
)
```

If order `SO-2026-101` is soft-deleted, the app **cannot create a new order with the same code** in that tenant while this unique index exists. That may be desirable when order codes must remain unique **forever** to avoid payment and historical confusion.

### 12.1. Uniqueness only for active records

If the product **allows reusing codes after soft deletion**, use a partial unique index:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderCode: 1 },
  {
    unique: true,
    name: "uq_active_tenant_order_code",
    partialFilterExpression: {
      deleted: false
    }
  }
)
```

This index enforces uniqueness only across documents **matching `deleted:false`**. Tombstones with `deleted:true` are excluded from the index, allowing multiple deleted records with the same business code.

**Two consequences to understand:**

1. Legacy documents **missing `deleted`** also **do not enter the partial index**. Before backfill completes, inserts may bypass the uniqueness constraint you expect. Finish migrating data before relying on this index.
2. When restoring a tombstone, if another active document has already claimed the same code, updating `deleted:true -> false` will **fail with a duplicate key error**. The repository fragment must handle this error and report an appropriate conflict rather than forcing restoration.

Never create both a full unique index and a partial unique index expecting the partial index to allow code reuse: the full unique index still blocks duplicates. Finalize your business key policy before creating indexes.

### 12.2. Indexes serving active read queries

For screens filtering by tenant, status, and time:

```javascript
db.orders.createIndex({
  tenantId: 1,
  deleted: 1,
  status: 1,
  updatedAt: -1,
  _id: -1
})
```

This is a **candidate index** to benchmark, not a universal optimal configuration. If screens frequently filter only `tenantId + deleted` and sort by `updatedAt` without filtering `status`, a different key order may fit better. Having `status` between keys can prevent index-assisted sorting when no status filter is supplied.

Measure real queries with:

```javascript
db.orders
  .find({
    tenantId: "TENANT-A",
    deleted: false,
    status: "PAID"
  })
  .sort({ updatedAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats")
```

Monitor `nReturned`, `totalKeysExamined`, `totalDocsExamined`, sort stages, and execution time. Indexing a boolean flag has low selectivity if nearly all documents are active; its value comes from pairing with tenant and other selective fields.

### 12.3. Indexes do not replace access control

Partial or compound indexes only help constraints and performance; they **do not filter authorization** across all queries. `repository.findAll()` can still return tombstones and other tenants' documents even if the collection has an index on `tenantId, deleted`.

## 13. Purging data after retention periods

Soft delete is not permanent data erasure. If compliance requires retention limits or personal data deletion, build a separate, authorized, and audited **purge workflow**.

### 13.1. Strictly conditioned purge

Example physically deleting orders soft-deleted past the retention cutoff:

```javascript
// Run ONLY after retention policy approval.
db.orders.deleteMany({
  tenantId: "TENANT-A",
  deleted: true,
  deletedAt: {
    $lt: ISODate("2026-01-01T00:00:00Z")
  }
})
```

This command is a **hard delete** and cannot be undone by normal restore operations. Before running it, verify legal holds, backups, cross-collection references, result logging, and expected counts.

### 13.2. TTL indexes when genuinely appropriate

An option for data that can auto-expire is a TTL index on `deletedAt`:

```javascript
// Example retaining 30 days after soft deletion.
db.orders.createIndex(
  { deletedAt: 1 },
  { expireAfterSeconds: 2592000 }
)
```

TTL runs in the background, **does not guarantee exact-second deletion at expiration**, and requires a properly typed BSON Date field; nor does it inspect business rules if active documents accidentally retain `deletedAt`: therefore restore must **unset `deletedAt`** if using a TTL design. Never use TTL when legal holds or multi-collection retention rules apply. When approval or auditing is required prior to purging, an explicit conditional job is safer than automatic TTL.

### 13.3. Links and cross-document references

If `Order` has `Payment`, `Shipment`, or `AuditEvent` documents referencing it by ID:

- Soft-deleting the order **does not automatically delete** related documents.
- Payment/shipment queries must decide whether to return deleted orders or not.
- Do not rely on automatic cascades like in many relational ORMs; Spring Data MongoDB does not automatically cascade soft deletes across relationships.
- If multiple entities must be cancelled/locked simultaneously, consider a transaction/outbox or business state machine instead of only updating `deleted` on the order.

## 14. Common design flaws: unsafe shortcuts

### 14.1. Defining a delete method expecting a soft delete

```java
// ANTI-PATTERN: derived delete is a deletion operation, not soft delete.
long deleteByTenantIdAndStatus(
    String tenantId, String status);
```

The name `deleteBy...` **does not mean** "`$set deleted=true`". For soft deletes, use clearly named update methods like `markDeleted`/`softDelete` and ensure all hard-delete paths remain strictly controlled.

### 14.2. Fixing findAll while forgetting count, exists, and exports

```text
findActive(...)           -> correct
countByTenantId(...)      -> still counts tombstones
existsById(...)           -> still matches tombstones
aggregation revenue       -> still sums deleted orders
CSV report                -> still exports deleted info
```

A soft-delete policy requires a **matrix covering every read path**. Test detail finders, lists, counts, existence checks, searches, sort/pagination, aggregations, and admin paths. There is no "automatic global soft-delete filter" on `MongoTemplate` simply because the repository has `DeletedFalse` methods.

### 14.3. Updating by _id without checking deleted/version

```java
// ANTI-PATTERN: can mutate tombstones or overwrite stale state.
template.updateFirst(
    Query.query(Criteria.where("id").is(id)),
    new Update().set("status", "PAID"),
    OrderDocument.class);
```

Always include authorized tenant, `deleted=false`, and expected version. When explicitly incrementing version in the update, inspect `matchedCount` rather than assuming success simply because no exception was thrown.

### 14.4. Calling repository.save with partially loaded entities

A projection with only a few fields or a Java entity lacking metadata written by another service is **not** safe for full replacement. Soft-deleting via targeted `$set` with CAS avoids dropping out-of-scope fields while still guarding against concurrent writers.

### 14.5. Equating "false" with a missing field

If finders use `DeletedFalse` while legacy writers still insert documents missing `deleted`, those records get silently skipped. Use one canonical model and migration; never let one API treat missing as active while another treats missing as nonexistent.

### 14.6. Unchecked permissions on soft-delete operations

Soft delete **is still a data-mutating action**, not just toggling a UI flag. The service must verify actor, tenant, delete permission, and business constraints (e.g., disallowing deletion of invoiced orders) before calling the repository. When eligibility depends on current state, place that state or version into **the update condition itself** to prevent races between checking and writing.

## 15. Integration testing: neither leak tombstones nor miswrite

Mocking a repository can return whatever list you stub, yet **cannot prove** Spring Data generated the right `deleted:false` filter, wired the fragment properly, preserved unmapped fields with `@Update`, or executed MongoDB version checks atomically. Write integration tests against an isolated MongoDB instance, seeding real BSON via the driver.

Example using JUnit 5/AssertJ and Spring Boot `@DataMongoTest`. Annotation package names may vary across Spring Boot major versions; below is the common Spring Boot 3.x import style. Configure an isolated test MongoDB (such as Testcontainers) before running.

### 15.1. Fixture with active, tombstone, other tenant, and legacy missing field

File `OrderSoftDeleteIntegrationTest.java`:

```java
package com.example.shop.orders;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
class OrderSoftDeleteIntegrationTest {

    private static final Instant NOW =
        Instant.parse("2026-11-20T03:00:00Z");

    @TestConfiguration
    static class TestClockConfig {
        @Bean
        Clock clock() {
            return Clock.fixed(NOW, ZoneOffset.UTC);
        }
    }

    @Autowired MongoTemplate template;
    @Autowired OrderRepository repository;

    private static Document order(
            String id, String tenant, String status,
            Boolean deleted, long version) {

        Document d = new Document("_id", id)
            .append("tenantId", tenant)
            .append("orderCode", "CODE-" + id)
            .append("status", status)
            .append("version", version)
            .append("updatedAt", Date.from(
                Instant.parse("2026-11-19T08:00:00Z")))
            // Real BSON fields absent from the Java entity.
            .append("legacyIntegration",
                new Document("source", "erp-v1")
                    .append("syncToken", "sync-7788"));

        if (deleted != null) {
            d.append("deleted", deleted);
        }
        if (Boolean.TRUE.equals(deleted)) {
            d.append("deletedAt", Date.from(
                Instant.parse("2026-11-19T12:00:00Z")));
            d.append("deletedBy", "admin-old");
        }
        return d;
    }

    private Document raw(String id) {
        return template.getCollection("orders")
            .find(new Document("_id", id))
            .first();
    }

    @BeforeEach
    void seed() {
        // ONLY wipe the whole collection in an isolated TEST database.
        var collection = template.getCollection("orders");
        collection.deleteMany(new Document());

        collection.insertMany(List.of(
            order("ORD-101", "TENANT-A", "PAID", false, 3L),
            order("ORD-102", "TENANT-A", "NEW", false, 1L),
            order("ORD-201", "TENANT-A", "PAID", true, 7L),
            order("ORD-OLD", "TENANT-A", "NEW", null, 2L),
            order("ORD-B01", "TENANT-B", "PAID", false, 3L)
        ));
    }

    @Test
    void normalReadsHideDeletedAndUnnormalizedLegacyDocuments() {
        assertThat(repository
            .findByIdAndTenantIdAndDeletedFalse(
                "ORD-101", "TENANT-A")).isPresent();

        assertThat(repository
            .findByIdAndTenantIdAndDeletedFalse(
                "ORD-201", "TENANT-A")).isEmpty();

        // Inherited CRUD methods have NO soft-delete filter.
        assertThat(repository.findById("ORD-201")).isPresent();

        // Legacy document missing deleted does not match DeletedFalse.
        assertThat(repository
            .findByIdAndTenantIdAndDeletedFalse(
                "ORD-OLD", "TENANT-A")).isEmpty();

        assertThat(repository.countByTenantIdAndDeletedFalse(
            "TENANT-A")).isEqualTo(2L);

        assertThat(repository
            .existsByIdAndTenantIdAndDeletedFalse(
                "ORD-201", "TENANT-A")).isFalse();

        var ids = repository.findActiveNewOrPaid("TENANT-A")
            .stream().map(OrderDocument::id).toList();
        assertThat(ids).containsExactlyInAnyOrder(
            "ORD-101", "ORD-102");
        assertThat(ids).doesNotContain("ORD-B01", "ORD-201");
    }

    @Test
    void softDeleteUsesCasAndPreservesUnmappedBsonFields() {
        boolean changed = repository.softDelete(
            "TENANT-A", "ORD-101", 3L, "user-42");
        assertThat(changed).isTrue();

        Document stored = raw("ORD-101");
        assertThat(stored).isNotNull();
        assertThat(stored.getString("_id")).isEqualTo("ORD-101");
        assertThat(stored.getBoolean("deleted")).isTrue();
        assertThat(stored.getDate("deletedAt").toInstant())
            .isEqualTo(NOW);
        assertThat(stored.getString("deletedBy"))
            .isEqualTo("user-42");
        assertThat(stored.get("version", Number.class)
            .longValue()).isEqualTo(4L);

        // Selective $set update: legacy metadata stays intact.
        Document legacy = stored.get(
            "legacyIntegration", Document.class);
        assertThat(legacy.getString("source"))
            .isEqualTo("erp-v1");
        assertThat(legacy.getString("syncToken"))
            .isEqualTo("sync-7788");

        assertThat(repository
            .findByIdAndTenantIdAndDeletedFalse(
                "ORD-101", "TENANT-A")).isEmpty();

        // Retry with old version or already deleted -> no second update.
        assertThat(repository.softDelete(
            "TENANT-A", "ORD-101", 3L, "user-42")).isFalse();
        assertThat(raw("ORD-101").get("version", Number.class)
            .longValue()).isEqualTo(4L);
    }

    @Test
    void staleVersionOrWrongTenantCannotDelete() {
        assertThat(repository.softDelete(
            "TENANT-A", "ORD-101", 2L, "user-42")).isFalse();

        assertThat(repository.softDelete(
            "TENANT-B", "ORD-101", 3L, "user-42")).isFalse();

        Document stored = raw("ORD-101");
        assertThat(stored.getBoolean("deleted")).isFalse();
        assertThat(stored.get("version", Number.class)
            .longValue()).isEqualTo(3L);
    }

    @Test
    void restoreIsCasAndClearsTombstoneFields() {
        assertThat(repository.restore(
            "TENANT-A", "ORD-201", 7L)).isTrue();

        Document stored = raw("ORD-201");
        assertThat(stored.getBoolean("deleted")).isFalse();
        assertThat(stored.containsKey("deletedAt")).isFalse();
        assertThat(stored.containsKey("deletedBy")).isFalse();
        assertThat(stored.get("version", Number.class)
            .longValue()).isEqualTo(8L);

        assertThat(repository
            .findByIdAndTenantIdAndDeletedFalse(
                "ORD-201", "TENANT-A")).isPresent();

        assertThat(repository.restore(
            "TENANT-A", "ORD-201", 7L)).isFalse();
    }

    @Test
    void otherBusinessUpdatesMustExcludeTombstones() {
        Query safeCondition = Query.query(
            Criteria.where("id").is("ORD-201")
                .and("tenantId").is("TENANT-A")
                .and("deleted").is(false)
                .and("version").is(7L));

        var result = template.updateFirst(
            safeCondition,
            new Update().set("status", "PAID_AGAIN")
                .inc("version", 1L),
            OrderDocument.class);

        assertThat(result.getMatchedCount()).isZero();
        assertThat(raw("ORD-201").getString("status"))
            .isEqualTo("PAID");
    }
}
```

**Execution prerequisites:** this test requires a real MongoDB or Testcontainers configured as an **isolated test database**. The `deleteMany(new Document())` call in `@BeforeEach` wipes all records in the `orders` collection on the connected database. Never point tests at a shared or production database. When upgrading Spring Boot, verify `@DataMongoTest` and `@TestConfiguration` imports against your chosen dependencies.

Fixtures are inserted via `getCollection(...).insertMany(...)` rather than `repository.save(...)` because we need **real BSON containing `legacyIntegration` absent from the entity**, plus a legacy document missing `deleted`. After updating, the raw driver reads back the document to confirm the field was not lost.

### 15.2. Testing the @Query + @Update annotation separately

If your project adopts `OrderStatusUpdateRepository` from Section 6 instead of a fragment, add a test:

```java
// statusUpdateRepository is the bean injected from Section 6's interface.
long changed = statusUpdateRepository.markDeleted(
    "TENANT-A", "ORD-102", 1L,
    Instant.parse("2026-11-20T03:00:00Z"),
    "user-42");

assertThat(changed).isEqualTo(1L);

Document stored = template.getCollection("orders")
    .find(new Document("_id", "ORD-102"))
    .first();

assertThat(stored).isNotNull();
assertThat(stored.getBoolean("deleted")).isTrue();
assertThat(stored.get("version", Number.class)
    .longValue()).isEqualTo(2L);
```

This is an **addition inside a test method** after injecting the repository and seeding in `@BeforeEach`; it is not a standalone test class. Include a case with the same ID and a wrong `expectedVersion` to prove the annotated update never overwrites stale documents.

### 15.3. Do not test by document count alone

A naive test like `assert count = 4` can pass even if one tombstone leaked in and one active document was wrongly excluded. For soft delete, assert:

- **Exact IDs** present/absent in finders and searches.
- Tenant condition across every branch of `OR`.
- `deleted`, `deletedAt`, `deletedBy`, and `version` in raw BSON.
- Legacy/unknown fields surviving partial updates.
- Retries and stale versions never overwriting earlier deletion timestamps/actors.
- Count/exists/page/aggregations following the same active policy.
- Restore preserving data and enforcing unique keys.

### 15.4. Mandatory test matrix

| Scenario | Expectation |
| --- | --- |
| Active document in authorized tenant | Returned by finder |
| Tombstone in authorized tenant | Hidden by normal finders, readable by admin finder |
| Other tenant's document | Neither returned nor modified by current tenant's requests |
| Legacy missing `deleted` | Does not match `DeletedFalse` pre-migration; handled per plan |
| `deleted: null` | Not silently treated as false |
| First soft delete | `deleted=true`, right timestamp/actor, version increments once |
| Repeated delete with old `expectedVersion` | Does not modify document a second time |
| Delete when version was bumped by another writer | Does not match; no overwrite |
| Delete when order is already deleted | Does not match; preserves original `deletedAt`/`deletedBy` |
| Business update executed against tombstone | Does not match when `deleted=false` is enforced |
| Restore with matching version | `deleted=false`, deletion metadata handled cleanly, version increments |
| Restore when business code collides with active doc | Duplicate key conflict when using partial unique index |
| Soft delete on document with unknown fields | Unknown fields preserved |
| Default `repository.findById` | Can still see tombstones; architectural warning |
| Pagination/count/aggregation queries | All process active records only in business flows |
| Purge/TTL tasks | Execute strictly per retention policy and approved privileges |

## 16. Reactive repositories and ReactiveMongoTemplate

Soft-delete semantics **do not change** when moving to reactive stacks. `ReactiveMongoRepository` still inherits methods like `findById` and `deleteById`; they do not auto-apply `deleted:false`. Finders must specify the active condition explicitly.

Example:

```java
package com.example.shop.orders;

import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, String> {

    Mono<OrderDocument> findByIdAndTenantIdAndDeletedFalse(
        String id, String tenantId);

    Flux<OrderDocument> findByTenantIdAndDeletedFalse(
        String tenantId);
}
```

For conditional updates, use `ReactiveMongoTemplate` and inspect `UpdateResult` inside the publisher:

```java
import java.time.Instant;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import reactor.core.publisher.Mono;

public Mono<Boolean> softDeleteReactive(
        ReactiveMongoTemplate template,
        String permittedTenantId,
        String id,
        long expectedVersion,
        String actorId,
        Instant now) {

    // Caller must verify permissions and validate inputs before invoking.
    Query filter = Query.query(
        Criteria.where("id").is(id)
            .and("tenantId").is(permittedTenantId)
            .and("deleted").is(false)
            .and("version").is(expectedVersion));

    Update patch = new Update()
        .set("deleted", true)
        .set("deletedAt", now)
        .set("deletedBy", actorId)
        .set("updatedAt", now)
        .inc("version", 1L);

    return template.updateFirst(
            filter, patch, OrderDocument.class)
        .map(result -> result.getMatchedCount() == 1);
}
```

This illustrative method belongs inside an appropriate Java class. The caller must verify tenant/actor and `expectedVersion`; real apps should supply `now` via an injected `Clock`. An unsubscribed `Mono` performs no update. Test reactive paths using `StepVerifier`, covering success, zero matches, stale versions, and cross-tenant documents.

Never call blocking `MongoTemplate` inside a reactive pipeline and pretend it is non-blocking. Nor should you call reactive `repository.save` on a partial entity instead of selective updates when out-of-model data must be preserved.

## 17. Transactions, auditing, and event-driven consistency

### 17.1. Flipping a flag on one document needs no multi-document transaction

A `$set + $inc` command filtered by `_id/tenant/deleted/version` mutates **one document** atomically. Merely setting a delete flag does not warrant a multi-document transaction.

However, if soft-deleting an order must simultaneously:

- Block shipments or inventory reservations in another collection.
- Write a mandatory audit event in a separate collection.
- Update outstanding balance totals under an immediate consistency invariant.

then decide whether to use a **multi-document transaction** on a supported MongoDB deployment, or an outbox/saga eventual-consistency pattern with error recovery. Soft deletes never cascade across references automatically.

### 17.2. Auditing partial updates

Annotations like `@LastModifiedDate` can be handled by entity callbacks/auditing during `save`; however, `@Update` and `MongoTemplate.updateFirst(...)` must not be assumed to traverse the full entity-save callback lifecycle. That is why this lesson **sets `updatedAt` explicitly** inside `Update`.

`deletedBy` must come from server-side identity/authorization; never trust an arbitrary user ID from a request without verifying privileges. If storing deletion reason, operation code, or correlation ID, define explicit metadata/validation and scrub sensitive values from logs.

### 17.3. Deleted state does not replace business status

`status = PAID` and `deleted = true` can coexist. Soft delete is a **document-lifecycle management axis**, not necessarily overwriting `status` to `DELETED`. If a system uses one single status enum instead of a flag, rewrite all read rules, updates, indexes, and state machines consistently.

Preserving `status` makes restoring prior business state easy, though it also means reports querying `status=PAID` must **include `deleted=false`** when counting active orders.

## 18. Rollout procedure on a live system

### 18.1. Preparation and profiling

Before turning on soft delete, aggregate existing distributions:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: { $type: "$deleted" },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
])
```

Count `bool`, `null`, `missing`, String, or other types to spot legacy records. Also check presence/types of `version` and indexed fields. Never assume old collections already obey the new Java model.

### 18.2. Phased rollout to prevent disappearing records

Reference rollout:

1. **Lock the contract:** `deleted:false` is active, `deleted:true` is tombstone, plus roles of `deletedAt`/`deletedBy`, restore, and retention.
2. **Standardize writers:** ensure new writes always set `deleted:false` and proper BSON `version`.
3. **Add temporary compatibility if needed:** readers can include legacy missing fields during transition, provided update commands match.
4. **Checkpointed backfill:** convert confirmed missing/null records to `deleted:false`, standardize `version`, and reconcile per tenant.
5. **Update all read paths:** detail finders, lists, counts, exists, `@Query`, `MongoTemplate`, aggregations, exports, and internal jobs.
6. **Enable atomic soft delete:** enforce `expectedVersion`, `deleted=false`, and tenant in update filters; inspect results.
7. **Deploy indexes:** active read indexes and unique keys per code-reuse policy; check duplicates before creating.
8. **Test restore and conflicts:** especially when a partial unique index allowed a new record to reuse an old code.
9. **Monitor post-rollout:** tombstone counts, CAS failures, no-match updates, duplicate keys, missing `deleted` rate, and query costs.
10. **Remove legacy compatibility** only after confirming zero legacy documents remain in scope and no old writer omits fields.

### 18.3. Multi-version deployments must account for both directions

A new application supporting soft delete **does not make older instances hide tombstones**. During a rolling deployment, if old instances still call `findAll`, they will continue displaying records soft-deleted by new instances.

When a data contract change has security or compliance impact, coordinate **when writing `deleted=true` starts** against when every reader enforces filtering. You may need feature flags, deploying readers before writers, gateway/service guards, or phasing out old instances first.

## 19. Review checklist and common pitfalls

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Deleted record still visible in detail endpoint | Used inherited `findById` without `DeletedFalse` | Use finder with tenant + `deleted=false` |
| UI shows higher total count than list | `count` omits deleted filter | Use `countByTenantIdAndDeletedFalse` |
| Revenue report includes tombstones | Aggregation missing `$match deleted:false` | Add filter stage to pipeline |
| Legacy records "disappear" after upgrade | BSON missing `deleted`; finder matches only `false` | Backfill or planned compatibility reader |
| Soft delete fails on legacy records | Update filter requires `deleted:false` while field is missing | Standardize schema or sync temporary read/write predicates |
| Two concurrent deletes overwrite `deletedAt` twice | Update did not check active/version | CAS in one command; idempotent retries |
| Deleted another tenant's order | Filter checked ID only or permissions unverified | Mandatory tenant/authorization |
| Deleted order's status still gets updated | Business update omits `deleted=false` | Update every write path |
| Soft delete via `save` drops unmapped metadata | Full document replacement | Use selective `$set` with CAS |
| `@Version` exists yet `@Update` misses stale writes | Forgot `expectedVersion` in query | Add explicit version predicate and `$inc` |
| Restore throws duplicate key | Partial unique index allowed reusing active code | Check code conflict before restore, handle conflict |
| Restored record deleted by TTL | `deletedAt` remained and TTL was active | Unset `deletedAt` or revise retention strategy |
| Soft-deleted yet PII remains in DB | Soft delete is not hard delete | Implement retention/purge workflow |
| `OR` search leaks tombstones or other tenants | Guard placed inside wrong `OR` branch | Keep tenant/`deleted` in outermost `AND` |
| Mock tests pass while real BSON is wrong | Never tested real mapping/filters/updates | Integration-test raw BSON and inspect results |

## 20. Applied exercise

A device management system stores a `devices` collection:

```javascript
{
  _id: "DEV-001",
  tenantId: "TENANT-X",
  serial: "SN-001",
  state: "ONLINE",
  deleted: false,
  version: NumberLong(8),
  updatedAt: ISODate("2026-11-19T10:00:00Z"),
  vendorMetadata: {
    firmware: "2.4",
    lastSyncBatch: "B-992"
  }
}
```

An endpoint may "decommission a device" via soft delete, and restore it provided the serial has not been reused by a replacement device.

Complete these tasks:

1. Write `DeviceRepository` with finders by `id + tenant + deleted=false`, paginated list, and consistent `count`/`exists`.
2. Write a soft-delete command matching `_id = DEV-001`, `tenantId = TENANT-X`, `deleted=false`, `version=8`; `$set` flag, actor, timestamp, and `$inc` version.
3. Demonstrate why `repository.deleteById(...)` is not soft delete and why full-entity `save` can lose `vendorMetadata`.
4. Add a tenant Y document with state `ONLINE` and a tenant X tombstone; test that neither finders nor aggregate counts leak them.
5. Simulate two concurrent requests with `expectedVersion` 8 and verify only one gets matched count 1.
6. Allow serial reuse when soft-deleted: propose a partial unique index on `(tenantId, serial)`; describe what happens on restoring an old device if its serial was already reused.
7. For legacy devices missing `deleted` and `version`, plan the migration before enabling the new finders and CAS.
8. Inspect raw BSON in tests to verify `vendorMetadata` survives soft delete and restore intact.
9. Propose a retention period and explain why TTL may be unsuitable if legal holds apply.

**Solution hints:** enable `DeletedFalse` finders only after canonicalizing the schema, keep tenant + deleted + version inside the same update filter, and mutate lifecycle fields via selective `Update`. A partial unique index allows creating a new device with the same serial while raising a conflict on restore; handle that explicitly in the business contract rather than silently deleting the newer record.

## 21. References

- Spring Data MongoDB — [MongoDB Repositories: Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): derived finders, `@Query`, and method naming.
- Spring Data MongoDB — [MongoDB Repositories: Modifying Queries](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/modifying-methods.html): `@Update` and direct update caveats.
- Spring Data MongoDB — [Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `MongoTemplate.updateFirst`, `@Version`, `findAndModify`, remove, and write results.
- Spring Data Commons — [Custom Repository Implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html): composing repository fragments.
- MongoDB Manual — [Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/): `$set`, `$unset`, `$inc`, and updating documents.
- MongoDB Manual — [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/): partial unique indexes and filter inclusion.
- MongoDB Manual — [TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/): automatic expiration on Date fields.
- MongoDB Manual — [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): single-document atomic updates and multi-document transactions.

## Key takeaways

**Proper soft delete** is an **end-to-end contract across both reads and writes**, not merely adding a `deleted` flag. Across all business queries, always enforce **`tenantId AND deleted=false`** — covering details, lists, counts, existence checks, aggregations, and exports. When deleting, perform a **single atomic update** by `_id`, tenant, `deleted=false`, and expected version; use `$set` for metadata, `$inc` for version, and inspect matched count. Never default to physical `delete` methods or full-replacement `save` as a soft-delete mechanism. Normalize legacy data, manage unique indexes/restores, preserve audits, and verify against real BSON so the policy holds consistently across the entire application.
