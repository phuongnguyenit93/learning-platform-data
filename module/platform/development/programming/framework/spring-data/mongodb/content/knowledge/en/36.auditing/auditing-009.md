# Distinguishing Last-Modified Metadata from Full Change History

> **Chapter:** Auditing  
> **Module:** `SPRING_DATA_MONGODB` — using Spring Data MongoDB to connect, map documents, and operate on MongoDB via `MongoTemplate` or repositories; practicing queries, aggregations, indexes, transactions, reactive access, testing, and data performance diagnostics.  
> **Goal:** Distinguish *creation/last-modified metadata* from a *multi-version audit trail*; configure Spring Data auditing (`@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, `@LastModifiedBy`) in imperative and reactive flows; identify write paths that do not trigger auditing; design a change history capturing actor, reason, timestamp, revision, before/after values, and request ID; persist state + history consistently using MongoDB transactions; and handle concurrency, retries, security, change streams, historical recovery, and testing.

## 1. How Many Questions About the Past Can One Document Answer?

Suppose the `orders` collection currently holds:

~~~javascript
{
  _id: "o901",
  tenant_id: "t01",
  status: "SHIPPED",
  delivery_address: "12 Nguyen Van A",
  created_at: ISODate("2026-10-10T02:00:00Z"),
  created_by: "customer-22",
  updated_at: ISODate("2026-11-20T03:00:00Z"),
  updated_by: "operator-08"
}
~~~

This document knows **who created** it and **who last modified** it, but it does not know:

- Which statuses the order went through before becoming `SHIPPED`, and when those transitions happened?
- Who changed the delivery address from its old value to its current value?
- Was the edit triggered by a customer request or an internal adjustment?
- How many updates occurred between the creation date and the last modification?
- Did two independent APIs update the same document and overwrite a change?
- Can we prove the state at a specific revision to investigate a dispute?

**Answer:** `createdAt`/`By` and `lastModifiedAt`/`By` alone are **audit metadata on the current record**, not **full change history**.

### 1.1. Two Kinds of Data to Separate

**Current state (one document):**

~~~javascript
{
  _id: "o901",
  status: "SHIPPED",
  revision: NumberLong(3),
  updated_by: "operator-08",
  updated_at: ISODate("2026-11-20T03:00:00Z")
}
~~~

**History (many events, stored separately):**

~~~javascript
[
  {
    _id: "o901:1",
    order_id: "o901",
    revision: NumberLong(1),
    action: "CREATED",
    actor_id: "customer-22",
    changed_at: ISODate("2026-10-10T02:00:00Z")
  },
  {
    _id: "o901:2",
    order_id: "o901",
    revision: NumberLong(2),
    action: "ADDRESS_CHANGED",
    actor_id: "customer-22",
    changed_at: ISODate("2026-11-01T09:15:00Z")
  },
  {
    _id: "o901:3",
    order_id: "o901",
    revision: NumberLong(3),
    action: "SHIPPED",
    actor_id: "operator-08",
    changed_at: ISODate("2026-11-20T03:00:00Z")
  }
]
~~~

This is a conceptual illustration; a real history collection must decide whether to store snapshots, diffs, `requestId`, `tenantId`, schema version, and whether to exclude sensitive fields.

### 1.2. Quick Comparison Table

| Criterion | Last-modified metadata | Full change history |
| --- | --- | --- |
| Where stored | Directly inside the current entity | Separate collection/table/event log |
| Record count | One current record | Many events or revisioned snapshots |
| Who created, when | Known | Can be recorded as the initial event |
| Who last edited, when | Known | Retrievable from the latest event |
| Intermediate edits | **No** | **Yes**, if recorded from the start with no uncaptured write paths |
| Before/after values | **No** from metadata alone | Yes, if designed to store diffs/snapshots |
| Reason, request source | Not by default | Yes, if metadata is added and captured properly |
| Querying past point-in-time state | Cannot be reconstructed | Conditionally possible with complete history/snapshots |
| Storage cost | Low | Grows with edit count and payload size |
| Risk when omitted | Stale/wrong metadata | Gaps in history and broken audit chain |

> **Rule:** `@LastModifiedDate` and `@LastModifiedBy` **do not turn a MongoDB document into an event-sourced aggregate**. For full history, pick a capture strategy covering **every write path**, preserving ordering and storing durably.

## 2. Distinguishing Auditing, Logging, Journaling, CDC, and Event Sourcing

These terms are frequently used interchangeably yet solve different problems:

| Mechanism | Primary Goal | Stores Complete Business History? |
| --- | --- | --- |
| **Spring Data auditing annotations** | Tag who/when created/modified on the entity | No |
| **Application logs** | Diagnose application behavior and errors | Not guaranteed; subject to drops/rotation/redaction |
| **MongoDB journal/WAL** | Crash recovery for server data files | Not a business audit record |
| **MongoDB oplog** | Supports replication and CDC mechanisms | Not a long-term history store |
| **MongoDB change streams** | Observe changes in supported deployments | Can feed capture pipelines, yet needs checkpoints/replay/retention |
| **Transactional audit collection** | Persist change events atomically with business writes | Yes, across write paths enforced by design |
| **Transactional outbox** | Reliably deliver events to downstream systems | Can carry audit events, though delivery retention differs from audit retention |
| **Event sourcing** | Store events as source of truth and rebuild state | Yes, if event model and replay are consistent |
| **Snapshots/versioning** | Store state at some/all milestones | Conditionally; does not capture actor/reason automatically |
| **Backups/PITR** | Restore infrastructure data to an earlier time | Does not replace actor and business-reason traceability |

### 2.1. Common Misconceptions

~~~text
@LastModifiedDate = 2026-11-20 10:00
                 ≠
Every change before 10:00 was recorded.

MongoDB journal exists
                 ≠
You can query "who changed the address field?" from the journal.

Change stream is running
                 ≠
Complete history exists since collection creation.

Outbox event was published
                 ≠
Event stays stored forever per retention policy.
~~~

## 3. Reference Architecture for a Multi-Edit Order

~~~mermaid
flowchart TD
    A["API / job / consumer"] --> B["Application service"]
    B --> C{"Controlled write path?"}
    C -->|"Entity save"| D["Spring Data auditing fields"]
    C -->|"Conditional update"| E["Explicit metadata update"]
    D --> F["MongoDB transaction"]
    E --> F
    F --> G["orders: current state"]
    F --> H["order_history: append-only event"]
    F --> I["Optional outbox: event delivery"]
    H --> J["History query API"]
    I --> K["Dispatcher -> downstream"]
~~~

**Separating responsibilities:**

- **Current collection** optimizes reading current state.
- **History collection** optimizes querying actors, revisions, diffs/snapshots, and reasons.
- **Outbox collection** (if present) optimizes reliable event delivery, retries, and delivery status.

All three need not share the same retention. For example, outbox rows might be purged 30 days after delivery while audit history is retained longer under legal/business obligations—specific durations must come from system policy rather than arbitrary defaults.

## 4. Which Auditing Annotations Does Spring Data MongoDB Offer?

Spring Data provides:

| Annotation | Purpose | Populated By |
| --- | --- | --- |
| `@CreatedDate` | Creation timestamp per auditing lifecycle | `DateTimeProvider`/clock |
| `@LastModifiedDate` | Latest modification timestamp via save/auditing | `DateTimeProvider`/clock |
| `@CreatedBy` | Actor that initialized the entity | `AuditorAware<T>` or reactive equivalent |
| `@LastModifiedBy` | Actor that last modified the entity | `AuditorAware<T>` or reactive equivalent |
| `@Version` | Optimistic concurrency / version field | Spring Data mapping/versioning, **not history** |

### 4.1. Creation and Modification Behavior

~~~text
save new entity
  -> CreatedDate/CreatedBy (when auditing is enabled)
  -> LastModifiedDate/LastModifiedBy may be populated on creation,
     depending on modifyOnCreate and auditing config

save existing entity
  -> LastModifiedDate/LastModifiedBy updated by auditing callback
  -> previous last-modified values replaced on current document
~~~

This is **metadata on the current document**. Spring does not append prior last-modified values into a history collection automatically.

### 4.2. Auditing Can Be Missing or Misattributed

- Without `@EnableMongoAuditing`/`@EnableReactiveMongoAuditing` enabled properly, annotations may not be processed as expected.
- Without `AuditorAware`/`ReactiveAuditorAware`, actor fields may stay unpopulated.
- Background jobs lack an end-user `SecurityContext`; their actor must be declared explicitly.
- Query-level updates and raw driver calls bypass entity save callbacks and **do not auto-update auditing fields**.
- Unsynchronized app clocks can cause timestamp skew across instances.
- Records edited directly via `mongosh` or migrations are not intercepted by Java.

## 5. Configuring Auditing for Spring MVC / Imperative MongoDB

### 5.1. Enabling Auditing

~~~java
// MongoAuditConfig.java
package com.example.audit;

import java.time.Clock;
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

@Configuration
@EnableMongoAuditing(auditorAwareRef = "auditorProvider")
public class MongoAuditConfig {

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean("auditorProvider")
    AuditorAware<String> auditorProvider() {
        return () -> Optional.of("system-demo");
    }
}
~~~

`"system-demo"` is only for a self-contained fixture and is **unsuitable for production**. In real services, the auditor must come from an **authenticated security principal** or an authorized system job actor, never a client-supplied username.

### 5.2. Resolving the Actor from Spring Security

~~~java
import java.util.Optional;
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public final class SecurityAuditorAware
        implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        Authentication auth = SecurityContextHolder
            .getContext().getAuthentication();

        if (auth == null || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken) {
            return Optional.empty();
        }
        return Optional.of(auth.getName());
    }
}
~~~

This implementation is for the **imperative security context**. Replace the demo bean:

~~~java
@Bean("auditorProvider")
AuditorAware<String> auditorProvider() {
    return new SecurityAuditorAware();
}
~~~

Do not register **both** beans under the same name `auditorProvider`. If the app does not use Spring Security, read the actor from another trusted context component while avoiding arbitrary user IDs from request bodies.

### 5.3. System Actors Need Distinct Identities

Common actor categories:

~~~text
USER       -> authenticated account ID / subject
SERVICE    -> service principal / canonical workload identity
SCHEDULER  -> job name + version/owner
MIGRATION  -> deployment / migration ID
UNKNOWN    -> only when genuinely impossible to identify
~~~

To avoid mixing categories, you can define a record:

~~~java
public record AuditActor(
    String type,
    String id
) {}
~~~

Then the auditing field and `AuditorAware<AuditActor>` need a durable matching mapping. Simply stamping `"admin"` everywhere does not prove who acted.

### 5.4. Where Does the Timestamp Come From?

`@CreatedDate`/`@LastModifiedDate` use Spring Data Auditing's time mechanism. Configure a `DateTimeProvider` when a shared clock or test clock is needed:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;
import org.springframework.data.auditing.DateTimeProvider;

DateTimeProvider provider(Clock clock) {
    return () -> Optional.of(Instant.now(clock));
}
~~~

In a full auditing setup, define a `DateTimeProvider` bean and reference it via `dateTimeProviderRef` if needed. Verify the exact configuration attributes supported by your Spring Data version. Remember timestamps here come from the **application clock**, not an immutable server commit timestamp.

## 6. Current Entity with Auditing Metadata

~~~java
// OrderDocument.java
package com.example.audit;

import java.time.Instant;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_audit_009")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    private String status;
    private String deliveryCity;
    private long revision; // Illustrative business revision, managed explicitly.

    @CreatedDate
    private Instant createdAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedDate
    private Instant lastModifiedAt;

    @LastModifiedBy
    private String lastModifiedBy;

    protected OrderDocument() {}

    public OrderDocument(
            String id, String tenantId,
            String status, String deliveryCity) {
        this.id = id;
        this.tenantId = tenantId;
        this.status = status;
        this.deliveryCity = deliveryCity;
        this.revision = 1;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getStatus() { return status; }
    public String getDeliveryCity() { return deliveryCity; }
    public long getRevision() { return revision; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getLastModifiedAt() { return lastModifiedAt; }
    public String getCreatedBy() { return createdBy; }
    public String getLastModifiedBy() { return lastModifiedBy; }

    public void changeCity(String next) {
        this.deliveryCity = next;
    }
}
~~~

In this example `revision` **is not `@Version`**; it illustrates a business revision explicitly updated by the service on state changes. When using `@Version`, Spring Data manages optimistic versions per mapping rules; do not assume both revision mechanisms update identically.

### 6.1. Inserting via Repository

~~~java
// OrderRepository.java
package com.example.audit;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {
}
~~~

~~~java
OrderDocument order = new OrderDocument(
    "o901", "t01", "PENDING", "Hanoi"
);

OrderDocument saved = orderRepository.insert(order);
// With proper auditing config:
//   saved.getCreatedAt() != null
//   saved.getCreatedBy() == "system-demo" (in fixture)
~~~

**Note:** verify auditing values on the entity after insert against an actual auditing callback/config; do not assume annotations execute in unit tests using mocked repositories or when auditing is disabled.

### 6.2. Modifying via `save`

~~~java
OrderDocument current = orderRepository.findById("o901")
    .orElseThrow();
current.changeCity("Da Nang");
OrderDocument savedAgain = orderRepository.save(current);

// lastModifiedAt/lastModifiedBy are reassigned on the current document,
// yet the previous value's history is not automatically recorded elsewhere.
~~~

`save` can replace or upsert documents depending on state and mapping. If two requests read the old entity concurrently, both `save` calls risk a **lost update** unless optimistic locking, version predicates, or an appropriate transaction strategy is used.

## 7. `@LastModifiedDate` Is NOT Guaranteed Across Every Write Path

### 7.1. `MongoTemplate.updateFirst`

~~~java
Query query = Query.query(
    Criteria.where("id").is("o901")
);

mongoTemplate.updateFirst(
    query,
    new Update().set("deliveryCity", "Hue"),
    OrderDocument.class
);
~~~

On a **direct update operator path**, Spring Data does not run the full entity mapping lifecycle like `save(entity)`. Therefore do not rely on `@LastModifiedDate` to automatically update `lastModifiedAt`/`lastModifiedBy`. The update may change `deliveryCity` while auditing fields **retain their old values**.

**Note:** Spring Data's handling of `@Version` in certain update operations is a separate feature; version auto-incrementing does not imply date/by auditing also updated.

### 7.2. Manually Updating Metadata on Operator Updates

~~~java
Instant now = clock.instant();
String actorId = trustedActor.id();

Update update = new Update()
    .set("deliveryCity", "Hue")
    .set("lastModifiedAt", now)
    .set("lastModifiedBy", actorId);

mongoTemplate.updateFirst(query, update, OrderDocument.class);
~~~

`clock` and `trustedActor` are verified/configured dependencies; this is a service snippet. Always check `matchedCount` and enforce tenant/state/version conditions instead of updating by ID without authorization checks.

### 7.3. Write Paths to Review

| Write Path | Passes Through Entity Auditing Callbacks? | Full History Expectation |
| --- | --- | --- |
| `MongoRepository.insert/save` | Usually **yes** when auditing is enabled | Does **not** auto-create history |
| `MongoTemplate.insert/save(entity)` | Usually runs mapping/auditing callbacks | Does not auto-create history |
| `MongoTemplate.updateFirst/updateMulti` | Does not run `save` entity callbacks | Must write event explicitly |
| `findAndModify` | Query/update operator path; do not assume entity-save auditing | Must write event explicitly |
| `bulkOps` / bulk driver | Callbacks/auditing not uniform with single-entity `save` | Must write event explicitly |
| Aggregation pipeline update | Skips entity save callbacks | Must write event explicitly |
| Raw MongoDB Java Driver | Ignores Spring auditing annotations | Must write event explicitly |
| `mongosh`/migration/admin tool | Bypasses application auditing | Needs separate audit/migration trail |
| TTL expiry / server background delete | Not an entity save event | Use another strategy if deletion logs are needed |

A write bypassing Spring auditing is not automatically "wrong". What matters is **defining a mandatory audit contract and governing every write path**.

## 8. `@Version` Detects Concurrency, Yet Does Not Store History

A document can be modified concurrently:

~~~text
Request A reads order rev=7, city="Hanoi"
Request B reads order rev=7, city="Hanoi"

A writes city="Hue"
B writes city="Da Nang"

Without a guard/version, B can overwrite A silently without conflict.
LastModifiedAt only tells the latest timestamp; it does not record what A changed.
~~~

### 8.1. `@Version` Used with Entity Save

~~~java
import org.springframework.data.annotation.Version;

@Version
private Long version;
~~~

When saving an entity mapped by Spring Data, version supports **optimistic locking** on compatible write paths. Saving a stale entity raises `OptimisticLockingFailureException` instead of silently overwriting.

**Practical condition:** to detect write failures reliably, use an **acknowledged write concern**; with `w:0`, exceptions cannot reflect server state reliably.

### 8.2. Version Is Not an Audit Trail

~~~javascript
{
  _id: "o901",
  version: NumberLong(13),
  last_modified_by: "operator-08"
}
~~~

Even at version 13, current metadata **does not hold versions 1–12**. `@Version` detects concurrent writes and enforces ordering; it does not create 12 historical documents.

### 8.3. Business Revision Differs from Mapping Version

Our `OrderDocument` example has an application-managed `revision`. Two clean designs:

1. **Mapping version**: use `@Version` with verified save API semantics.
2. **Business revision**: use a regular `revision` field incremented via `$inc` guarded by `revision == expectedRevision`.

Do not put `@Version` on a field and **also manually `$inc` it** without understanding how Spring Data handles `@Version` in update operators, or you risk double-incrementing.

### 8.4. Revision Used to Order History

If history contains:

~~~text
o901:1 CREATED
o901:2 CITY_CHANGED
o901:3 SHIPPED
~~~

then `revision` is the **logical sequence** for that aggregate. Timestamps must not be the sole ordering key: two instances can have clock skew, two events can share the same millisecond, or commits can finish out of pre-commit timestamp order.

## 9. Designing a Collection for Full Change History

Instead of mutating only the current document, create a dedicated collection such as `order_history_009`.

### 9.1. Fields to Consider

| Field | Example | Why Needed |
| --- | --- | --- |
| `_id` | `o901:2` | Immutable/unique ID per revision |
| `tenant_id` | `t01` | Tenant isolation |
| `order_id` | `o901` | Aggregate key |
| `revision` | `2` | Logical order of the change |
| `command_id` | `cmd-8e72` | Request/retry correlation |
| `action` | `DELIVERY_CITY_CHANGED` | Meaningful business action name |
| `actor_type` | `USER`/`SERVICE` | Principal category |
| `actor_id` | `operator-08` | Verified acting principal |
| `occurred_at` | UTC Timestamp | When app recorded the change |
| `reason_code` | `CUSTOMER_REQUEST` | Standardized reason |
| `before_city` / `after_city` | `Hanoi` / `Hue` | Policy-approved audited values |
| `schema_version` | `1` | History payload schema version |
| `correlation_id` | `req-001` | Links traces/business batches |
| `source` | `ADMIN_API` | Write entrypoint used |

Not every field is needed in every system. **Sensitive data** (exact street addresses, tokens, passwords, payment details) must be classified; "full audit" **does not mean retaining every secret ever seen**.

### 9.2. Three Content Storage Strategies

| History Style | Example | Pros | Cons |
| --- | --- | --- | --- |
| **Full snapshot per revision** | Save entire order at rev2 | Simple point-in-time queries | Storage heavy; risks over-copying PII |
| **Diff/patch per revision** | `city: Hanoi → Hue` | Compact, highlights changed fields | Complex replay; requires handling schema evolution |
| **Domain event** | `DeliveryCityChanged` with actor/reason | Expresses business intent | Does not auto-carry all fields; replay needs rules |

This lesson uses **domain event + before/after of audit-approved fields**. Large systems can combine periodic snapshots with intermediate events to keep replay fast.

### 9.3. Do Not Assume Any Arbitrary Domain Event Suffices for Reconstruction

An event like:

~~~javascript
{
  action: "ORDER_SHIPPED",
  order_id: "o901",
  occurred_at: ISODate("2026-11-20T03:00:00Z")
}
~~~

does not contain enough data to reconstruct every order field. If **point-in-time reconstruction** is required, define schemas, event ordering, reducer/replay semantics, initial snapshots, and delete/migration handling.

## 10. History Entity: Never Overwrite History

~~~java
// OrderHistoryEvent.java
package com.example.audit;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "order_history_009")
public class OrderHistoryEvent {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("order_id")
    private String orderId;

    private long revision;
    private String commandId;
    private String action;
    private String actorType;
    private String actorId;
    private String reasonCode;
    private String beforeCity;
    private String afterCity;
    private Instant occurredAt;
    private int schemaVersion;

    protected OrderHistoryEvent() {}

    public OrderHistoryEvent(
            String id, String tenantId, String orderId,
            long revision, String commandId, String action,
            String actorType, String actorId,
            String reasonCode, String beforeCity,
            String afterCity, Instant occurredAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.orderId = orderId;
        this.revision = revision;
        this.commandId = commandId;
        this.action = action;
        this.actorType = actorType;
        this.actorId = actorId;
        this.reasonCode = reasonCode;
        this.beforeCity = beforeCity;
        this.afterCity = afterCity;
        this.occurredAt = occurredAt;
        this.schemaVersion = 1;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getOrderId() { return orderId; }
    public long getRevision() { return revision; }
    public String getCommandId() { return commandId; }
    public String getAction() { return action; }
    public String getActorId() { return actorId; }
    public String getBeforeCity() { return beforeCity; }
    public String getAfterCity() { return afterCity; }
}
~~~

Omitting public setters **encourages immutability at the application layer**. However, a Java class cannot stop an admin or raw driver from running `update`/`delete` on MongoDB. Real protection requires **least-privilege DB roles, restricted write permissions, backups/retention, monitoring, append-only policies**, and—for compliance—external immutable/WORM storage.

### 10.1. Do Not Use `save(history)` as a Silent Upsert

~~~java
mongoTemplate.insert(historyEvent);
~~~

Prefer `insert` when a history event must be a **new record**, so duplicate `_id` throws an error instead of silently overwriting an existing entry. Never blindly treat every duplicate as "success" without checking **tenant, `commandId`, revision, and payload**.

## 11. Creating Collections and Indexes in a Test Environment

~~~javascript
use spring_data_mongodb_lab

db.createCollection("orders_audit_009");
db.createCollection("order_history_009");

db.order_history_009.createIndex(
  { tenant_id: 1, order_id: 1, revision: 1 },
  { unique: true, name: "uq_tenant_order_revision" }
);

db.order_history_009.createIndex(
  { tenant_id: 1, commandId: 1 },
  { unique: true, name: "uq_tenant_command" }
);

db.order_history_009.createIndex(
  { tenant_id: 1, order_id: 1, occurredAt: -1 },
  { name: "ix_history_time" }
);
~~~

**Important note on field names:** the entity in section 10 uses `@Field("tenant_id")` and `@Field("order_id")`, while `revision`, `commandId`, and `occurredAt` have no alias so their BSON names match the Java properties. Indexes in `mongosh` must use the **actual BSON field names**, rather than assuming snake_case for unaliased fields. If your app uses a custom naming strategy, inspect the real mapping.

### 11.1. Choosing Unique Indexes for commandId

If a `commandId` is unique **within a tenant**, `{tenant_id, commandId}` works. If multiple valid history events can arise from a single command, that unique index will conflict; change it to `{tenant_id, commandId, eventSequence}` or separate a command log.

Base uniqueness on the **business contract**, rather than assuming "unique request ID" fits every domain.

### 11.2. Sharding Considerations

Unique indexes on sharded collections impose shard-key/prefix rules depending on topology and version. Do not assume the compound unique indexes above work unmodified on every sharded cluster. When sharding, design placement, shard keys, transaction routing, and unique constraints upfront.

### 11.3. Never Create Collections/Indexes Inside a Request Transaction

Migrations/deployments should create collections and indexes **before** serving traffic. Never let services alter schemas/indexes while users update orders—it prolongs transactions and hits DDL/version restrictions.

## 12. One Update Operation at Three Guarantee Levels

### 12.1. Updating Only the Current Document

~~~java
mongoTemplate.updateFirst(
    query,
    new Update()
        .set("deliveryCity", "Hue")
        .set("lastModifiedAt", clock.instant())
        .set("lastModifiedBy", actorId),
    OrderDocument.class
);
~~~

Outcome: yields **current state** and **last-modified metadata**, **with no history**.

### 12.2. Updating Current Then Inserting History Without a Transaction

~~~java
mongoTemplate.updateFirst(query, update, OrderDocument.class);
mongoTemplate.insert(historyEvent);
~~~

If inserting history fails after the update was ACKed, current state changed without a history event. If history inserts first and the current update fails, an event claims a change that never occurred.

Two sequential calls **do not equal atomic execution**.

### 12.3. Updating Current and Appending History in the Same Transaction

~~~text
MongoDB transaction T1
    |
    +-- guarded update order revision 4 -> 5
    +-- insert history event (orderId, revision 5)
    |
    +-- COMMIT -> both become visible together
         or
    +-- ABORT  -> neither commits
~~~

This is the strong baseline guaranteeing current state and history advance together when full traceability is required.

**Caveat:** transactions do not automatically cover external scripts, raw drivers outside the session, other database clients, emails/HTTP calls, or direct admin deletes. Govern **all write paths**.

## 13. MongoDB Transaction Manager: Sharing One Session

Example configuration suitable for a **test replica set** or transaction-capable deployment:

~~~java
// MongoTransactionConfig.java
package com.example.audit;

import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfig {
    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        TransactionOptions options = TransactionOptions.builder()
            .readPreference(ReadPreference.primary())
            .readConcern(ReadConcern.SNAPSHOT)
            .writeConcern(
                WriteConcern.MAJORITY.withJournal(true))
            .build();
        return new MongoTransactionManager(factory, options);
    }
}
~~~

With imperative `@Transactional`, Spring binds the MongoDB session to the thread's transaction context when invoked **through a proxy**.

### 13.1. Verify

- Topology is a replica set or sharded cluster supporting multi-document transactions.
- `MongoTemplate` in the service uses the **same `MongoDatabaseFactory`** as `MongoTransactionManager`.
- Avoid `this.methodAnnotatedTransactional()` self-invocations expecting a transaction to open.
- Never keep transactions open across HTTP calls, SMTP, or long-running work.
- Commit write concern and read concern match business durability requirements.
- Both order and history collections are pre-created before the workflow in tests/deployments.

### 13.2. Atomic Commit Differs from Failover Durability

A transaction can be atomic yet commit with a weak write concern (e.g., `w:1`), risking rollback on failover before majority replication. Choose majority/journal settings aligned with your SLO, and **never** assume majority replaces backups or audit retention policies.

## 14. Service Persisting State and History in the Same Transaction

This is the core example: every city-level delivery address change records a new event.

### 14.1. Service Updating with a Revision Guard

~~~java
// OrderChangeService.java
package com.example.audit;

import java.time.Clock;
import java.time.Instant;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderChangeService {
    private final MongoTemplate mongo;
    private final Clock clock;

    public OrderChangeService(
            MongoTemplate mongo, Clock clock) {
        this.mongo = mongo;
        this.clock = clock;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public OrderHistoryEvent changeDeliveryCity(
            String tenantId,
            String orderId,
            long expectedRevision,
            String nextCity,
            String actorId,
            String commandId) {

        requireValid(tenantId, orderId, nextCity, actorId, commandId);
        Instant changedAt = clock.instant();

        Query eligible = Query.query(
            Criteria.where("id").is(orderId)
                .and("tenantId").is(tenantId)
                .and("revision").is(expectedRevision)
        );

        Update change = new Update()
            .set("deliveryCity", nextCity)
            .set("lastModifiedAt", changedAt)
            .set("lastModifiedBy", actorId)
            .inc("revision", 1);

        OrderDocument before = mongo.findAndModify(
            eligible, change,
            FindAndModifyOptions.options().returnNew(false),
            OrderDocument.class
        );

        if (before == null) {
            throw new OrderChangeConflictException(
                "Order missing, wrong tenant or stale revision");
        }

        long nextRevision = expectedRevision + 1;
        OrderHistoryEvent history = new OrderHistoryEvent(
            orderId + ":" + nextRevision,
            tenantId,
            orderId,
            nextRevision,
            commandId,
            "DELIVERY_CITY_CHANGED",
            "USER",
            actorId,
            "CUSTOMER_REQUEST",
            before.getDeliveryCity(),
            nextCity,
            changedAt
        );

        // If history insert fails, the transaction rolls back
        // BOTH the order update and the history insert.
        return mongo.insert(history);
    }

    private static void requireValid(
            String tenantId, String orderId,
            String city, String actorId, String commandId) {
        if (tenantId == null || tenantId.isBlank()
                || orderId == null || orderId.isBlank()
                || city == null || city.isBlank()
                || actorId == null || actorId.isBlank()
                || commandId == null || commandId.isBlank()) {
            throw new IllegalArgumentException(
                "Missing change command fields");
        }
    }
}
~~~

Where:

~~~java
// OrderChangeConflictException.java
package com.example.audit;

public class OrderChangeConflictException extends RuntimeException {
    public OrderChangeConflictException(String message) {
        super(message);
    }
}
~~~

### 14.2. Step-by-Step Explanation

1. **Validate** mandatory inputs; in production `tenantId`/`actorId` must come from a trusted principal/service context.
2. **Guard** on `orderId + tenantId + expectedRevision`. If revision already changed, `findAndModify` matches nothing.
3. **Atomically update** the current document, incrementing revision exactly once.
4. **Return old document** via `findAndModify(...returnNew(false))`, giving history the true `beforeCity` at the prior revision.
5. **Insert history** with deterministic `_id` `orderId:nextRevision` inside **the same transaction**.
6. **Commit** when the method body returns through Spring's transactional proxy.

**Important:** `findAndModify` runs as an update operator; therefore the service **explicitly sets `lastModifiedAt`/`By`**. Never assume `@LastModifiedDate` on the entity fires automatically as in `save`.

### 14.3. Why Read `before` from the Update Result Instead of Reading Earlier?

If you write:

~~~java
OrderDocument before = mongo.findById(orderId, OrderDocument.class);
mongo.updateFirst(onlyById, update, OrderDocument.class);
mongo.insert(historyFrom(before));
~~~

another writer could update the order between `find` and `update` without an appropriate guard/transaction. `findAndModify` with `expectedRevision` inside a transaction guarantees **exact knowledge of which value was replaced**. Another transaction can still trigger a write conflict, in which case the service classifies the error and retries safely if appropriate.

### 14.4. Current State Result

Suppose before:

~~~javascript
{
  _id: "o901",
  tenant_id: "t01",
  deliveryCity: "Hanoi",
  revision: NumberLong(1)
}
~~~

After `changeDeliveryCity(..., expectedRevision=1, nextCity="Hue")` commits:

~~~javascript
{
  _id: "o901",
  tenant_id: "t01",
  deliveryCity: "Hue",
  revision: NumberLong(2),
  lastModifiedBy: "operator-08",
  lastModifiedAt: ISODate("2026-11-20T03:00:00Z")
}
~~~

and history:

~~~javascript
{
  _id: "o901:2",
  tenant_id: "t01",
  order_id: "o901",
  revision: NumberLong(2),
  commandId: "cmd-901-2",
  action: "DELIVERY_CITY_CHANGED",
  actorId: "operator-08",
  beforeCity: "Hanoi",
  afterCity: "Hue"
}
~~~

Timestamps in the JSON are illustrative; actual values come from the service's `Clock` at request time.

### 14.5. What If History Is Duplicate?

Suppose `order_history_009` already contains `_id="o901:2"` while the current order is still at rev1 due to inconsistent data or a conflict test. `mongo.insert(history)` is rejected by the unique constraint; with a proper transaction, the current order **does not commit** at rev2.

Never delete old history entries inside a `catch` block to "push the retry through". That destroys the audit trail.

## 15. "Full" History Requires Recording CREATE and DELETE Too

The service in section 14 records **one mutation type**: changing the city. If orders are created without a `CREATED` event, and later deleted via raw `delete` without history, the audit collection remains **incomplete**.

### 15.1. Recording an Event on Creation

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public OrderDocument createOrder(
        String tenantId,
        String orderId,
        String city,
        String actorId,
        String commandId) {

    OrderDocument order = new OrderDocument(
        orderId, tenantId, "PENDING", city
    );

    OrderDocument inserted = mongo.insert(order);

    mongo.insert(new OrderHistoryEvent(
        orderId + ":1",
        tenantId,
        orderId,
        1L,
        commandId,
        "CREATED",
        "USER",
        actorId,
        "ORDER_SUBMITTED",
        null,
        city,
        clock.instant()
    ));

    return inserted;
}
~~~

This is an **additional method** on a service with `mongo`/`clock` like section 14, not a standalone snippet. Both `insert` calls execute inside **the same transaction**. If inserting history fails, the order insert aborts.

When using Spring auditing, `@CreatedDate`/`By` on the order still record creator/time on the current document. The `CREATED` event adds business provenance **"order created by this command at revision 1"**. Both mechanisms complement rather than replace each other.

### 15.2. Soft Delete (`soft delete`)

For traceable data, many systems use:

~~~javascript
{
  _id: "o901",
  deleted: true,
  deleted_at: ISODate("2026-11-20T10:00:00Z"),
  revision: NumberLong(9)
}
~~~

On soft delete:

1. Set `deleted=true` with tenant/revision guards.
2. Append a `DELETED` or `ARCHIVED` history event in the same transaction.
3. Exclude deleted orders from default business queries.
4. Define retention, privacy, and restore policies.

**Do not treat soft delete as "no need for a data deletion policy"**: PII erasure/anonymization regulations may require extra handling.

### 15.3. Hard Delete (`hard delete`)

If deleting the current document is mandatory, use a transaction:

~~~text
findAndRemove order with tenant/revision predicate
    -> capture permitted pre-deletion fields
    -> insert HARD_DELETED / TOMBSTONE event
    -> commit
~~~

When complying with "right to erasure", the history event may **not be allowed to retain all deleted PII**. Keep only policy-approved minimal metadata (e.g., pseudonymized ID, action, legal basis) or purge/anonymize history when legally mandated.

### 15.4. Every Mutation Path Must Be Governed

To ensure the entire lifecycle is captured:

~~~text
CREATE -> UPDATE -> UPDATE -> DELETE
   |        |         |        |
   v        v         v        v
history  history   history  history
~~~

Batch jobs, migrations, admin commands, direct raw-driver scripts, and restores must all follow the policy. No annotation library can prove that **everyone with MongoDB write access** went through your application service.

## 16. Retries, Duplicates, and Uncertain Commit Outcomes

A distributed system must treat "client timed out" and "server did not write" as **two distinct statements**.

### 16.1. Lost Commit ACK Scenario

~~~text
t0  T1 updates order rev1 -> rev2.
t1  T1 inserts history o901:2 with commandId cmd-002.
t2  MongoDB commits T1 successfully.
t3  Connection drops before client receives commit ACK.
t4  Client receives exception / timeout.
~~~

At `t4`, the order **may already** be at rev2 and history **may already** exist. If the API blindly reruns the command with revision `2 → 3` and a new ID, history ends up with **two business changes** even though the user submitted one request.

### 16.2. Using commandId as an Idempotency Key

Example:

~~~javascript
db.order_history_009.findOne({
  tenant_id: "t01",
  commandId: "cmd-002"
});
~~~

If an event is found, **verify matching tenant, aggregate, action, and payload/fingerprint** and return the persisted result if it is indeed the same command. If not found immediately, do not blindly conclude the transaction never committed either: read concern and uncertain commit outcomes must be evaluated.

A production implementation needs an **idempotent command handler**:

~~~text
Request commandId = X
    |
    +-- X exists, same fingerprint
    |     -> return persisted result.
    |
    +-- X exists, different fingerprint
    |     -> reject conflict; do not execute twice.
    |
    +-- X not seen, prior commit outcome uncertain
    |     -> reconcile or retry per safe protocol.
    |
    +-- X is new, expected revision matches
          -> transaction: update state + insert history(X).
~~~

**Note:** the service in section 14 illustrates **atomic state + history**, **not** a complete API-level idempotency reconciliation flow. Add that before going to production.

### 16.3. Distinguishing Error Labels

| Situation | Conceptual Recommendation |
| --- | --- |
| `TransientTransactionError` | Some errors permit **retrying a fresh transaction body**, bounded and idempotent |
| `UnknownTransactionCommitResult` | Commit outcome uncertain; **retry commit** via driver/session while valid, or reconcile |
| Duplicate history `_id` | Event may already exist; verify payload/command before treating as a valid duplicate |
| Stale `revision` | Another writer won; return conflict or re-read/merge safely |
| Validation error | Fix input/schema; never retry endlessly |

Never write `catch(Exception) { retryService(); }`, as it creates duplicate side effects and hides logic errors.

### 16.4. Optimistic Concurrency and Revision

With self-managed `revision` as in section 14, every mutation expects:

~~~text
expectedRevision = 5
update predicate revision == 5
increment revision -> 6
append history revision 6
~~~

If two writers both attempt `5 → 6`, normally only one workflow can commit state + history; transaction conflicts, conditional updates, and unique history keys catch races.

Never rely on timestamp ordering to "guess who wrote later" and patch lost updates. **Revisions and transaction acknowledgments** are far more trustworthy.

## 17. Querying History with Tenant Isolation

### 17.1. Querying History by Revision in `mongosh`

~~~javascript
db.order_history_009.find(
  { tenant_id: "t01", order_id: "o901" },
  {
    _id: 1,
    revision: 1,
    action: 1,
    actorId: 1,
    occurredAt: 1,
    beforeCity: 1,
    afterCity: 1
  }
).sort({ revision: 1 });
~~~

This returns **history scoped to tenant `t01` and order `o901`**. Production APIs must enforce tenant from the **security context**; never trust a tenant parameter in the URL without authorization checks.

### 17.2. Repository Method

~~~java
// OrderHistoryRepository.java
package com.example.audit;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderHistoryRepository
        extends MongoRepository<OrderHistoryEvent, String> {

    List<OrderHistoryEvent>
    findByTenantIdAndOrderIdOrderByRevisionAsc(
        String tenantId, String orderId);
}
~~~

Small histories can return a `List`; if an order accumulates hundreds of thousands of events, paginate or stream by revision rather than loading everything into RAM.

### 17.3. Keyset Pagination by Revision

~~~java
Query page = Query.query(
    Criteria.where("tenantId").is(authenticatedTenant)
        .and("orderId").is(orderId)
        .and("revision").gt(afterRevision)
)
.with(Sort.by(Sort.Direction.ASC, "revision"))
.limit(100);

List<OrderHistoryEvent> events =
    mongoTemplate.find(page, OrderHistoryEvent.class);
~~~

Import `org.springframework.data.domain.Sort` alongside `Criteria`/`Query`. Using business revision as a cursor scales far better than `skip` pagination across millions of events, provided revisions are monotonic and retention does not create unexpected gaps.

**Do not assume a gap is always a bug** if the system intentionally logs only a subset of actions or prunes old events per retention. If **complete** history is required, enforce an invariant: every successful mutation produces an exact history entry per contract.

### 17.4. Timeline Query by Timestamp

~~~javascript
db.order_history_009.find({
  tenant_id: "t01",
  order_id: "o901",
  occurredAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}).sort({ occurredAt: 1, revision: 1 });
~~~

Use UTC and half-open `[start, end)` intervals to avoid boundary overlaps. Still, **business ordering within an aggregate should rely on `revision`**; timestamps serve mainly for filtering and reporting.

## 18. Retrieving Past State: What Data Is Needed?

### 18.1. Reconstructing State at Revision 5

If history stores a **full snapshot after every write**, fetch revision 5's snapshot directly.

If history stores **diff events only**, you need:

1. Initial state or the latest snapshot prior to rev5.
2. All events from that snapshot through rev5.
3. Reducer/replay logic handling schema versions and field semantics.
4. Guarantees against missing, duplicate, or out-of-order events.

### 18.2. Conceptual Reducer Example

~~~java
OrderState applyEvent(
        OrderState current,
        OrderHistoryEvent event) {

    if (event.getRevision() != current.revision() + 1) {
        throw new IllegalStateException(
            "History has a missing or reordered revision");
    }

    if ("DELIVERY_CITY_CHANGED".equals(event.getAction())) {
        return current.withDeliveryCity(
            event.getAfterCity(),
            event.getRevision()
        );
    }

    throw new UnsupportedOperationException(
        "Unknown event type: " + event.getAction());
}
~~~

`OrderState` and `withDeliveryCity(...)` are illustrative snapshot/replay types/methods not defined in full here. Real event sourcing requires complete reducers for `CREATED`, `DELETED`, migration events, and domain rules.

### 18.3. Even "Full History" Can Be Insufficient

If an event records only `OrderApproved` without capturing the shipping address before/after, you **cannot** reconstruct the shipping address at that moment from that event. "Completeness" is a **contract over captured information scope**, not just a collection name.

### 18.4. Event Time Differs from Commit Time

Application `occurredAt` is typically captured **before commit**. If a transaction pauses several seconds waiting on write concern or replication, that timestamp is not the server commit timestamp.

To reconcile ordering/durability, use revisions, transaction semantics, and (where applicable) CDC/operationTime metadata per contract. Never infer strict commit ordering from `Instant.now()` across multiple nodes.

## 19. Do Change Streams and CDC Replace Transactional History?

MongoDB change streams let you observe inserts, updates, replaces, and deletes on supported replica sets and sharded deployments. They can power **read models or centralized history stores** when infrastructure meets prerequisites.

### 19.1. CDC Flow

~~~mermaid
flowchart LR
    A["MongoDB current collection"] --> B["Change stream consumer"]
    B --> C["Normalize event / metadata"]
    C --> D["Audit datastore"]
    B --> E["Resume token checkpoint"]
    D --> F["History queries"]
~~~

### 19.2. Limitations of CDC

- **Does not know actor/reason** unless the current document or command persisted them.
- Update events may contain only `updateDescription` (modified fields), not the full **before-document**.
- `fullDocument: "updateLookup"` looks up the current document **which may have changed again** by lookup time; never assume it is the exact snapshot at event time under concurrent writes.
- **Pre-images/post-images** require explicit configuration and have retention/availability limits; they are not kept forever by default.
- Resume tokens expire if oplog retention lapses during prolonged consumer outages.
- Consumers can reprocess events after reconnects, requiring idempotency and checkpoints.
- Application bypasses, migrations, and admin edits show up as DB mutations lacking rich business context.

### 19.3. When to Choose CDC?

CDC shines when observing **all writes processed by MongoDB**, including drivers outside Spring Data, and replicating them elsewhere. Yet when **business auditing is mandatory and atomic** with order changes, **transactional history alongside current state** provides a tighter contract.

A hybrid strategy:

~~~text
App transaction: current + domain history
                         |
              Change stream on history
                         |
           Archive / index / analytics
~~~

Here the source of truth for business meaning is the **app-persisted history record**, while change streams distribute/replicate it downstream.

## 20. Security and Trustworthiness of the Audit Trail

### 20.1. Never Let Users Self-Report "Who I Am"

Wrong:

~~~java
history.setActorId(request.getActorId());
~~~

Taking `actorId` straight from an unverified HTTP body lets users impersonate others.

Right in principle:

~~~java
String actorId = authenticatedPrincipal.subject();
String tenantId = authenticatedPrincipal.tenantId();
~~~

`authenticatedPrincipal` is an application interface/abstraction, not built into Java. For background jobs, use a service account and explicitly record correlation IDs and trigger origin.

### 20.2. Never Copy Secrets into History

For example, when a user changes their password:

~~~text
DO NOT store:
beforePassword = "plaintext-old"
afterPassword  = "plaintext-new"
~~~

Store instead:

~~~javascript
{
  action: "PASSWORD_CHANGED",
  actor_id: "user-22",
  occurred_at: ISODate("2026-11-20T03:00:00Z"),
  changed_fields: ["password"]
}
~~~

Never store password hashes, tokens, API keys, full credit cards, or sensitive personal data without an explicit legal/business basis.

### 20.3. PII, Retention, and Right to Erasure

Audits must retain data for compliance while obeying data minimization and retention rules:

- Classify every field and its retention purpose.
- Encrypt at rest and in transit per policy.
- Restrict history read access more tightly than current state where needed.
- Define retention lifetimes, legal anonymization/pseudonymization, and redaction.
- Separate payload from metadata; tokenize or omit sensitive fields.
- Never attach a TTL index to delete history just to save disk space without policy approval.

### 20.4. Protecting History from Tampering or Deletion

A standard MongoDB collection **is not immutable** against users holding update/delete/admin privileges. Therefore:

1. Restrict the app role on history to `insert`, withholding unnecessary update/delete permissions (per MongoDB role capabilities).
2. Segregate operational/migration roles and audit administrative actions.
3. Alert on unexpected history modifications or deletions.
4. Maintain backups and test disaster-recovery restores.
5. For legal tamper-resistance, evaluate WORM/immutable archives, cryptographic hash-chaining, or external evidence services **backed by a proper threat model**.

Hash chaining detects unauthorized tampering yet **does not stop an attacker with full control from rewriting both the chain and signing keys** unless anchors/keys/backups live outside the compromised trust boundary.

### 20.5. History Is Not a Raw HTTP Payload Dump

HTTP bodies can hold secrets, oversized payloads, or prohibited data. History should capture **the specific fields/transitions requiring accountability** plus provenance fingerprints/metadata, rather than dumping raw requests/responses indiscriminately.

## 21. Auditing in Reactive Spring Data MongoDB Applications

Reactive apps use a different lifecycle and actor context than imperative ones.

### 21.1. Enabling Reactive Auditing

~~~java
// ReactiveAuditConfig.java
package com.example.audit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.data.mongodb.config.EnableReactiveMongoAuditing;
import reactor.core.publisher.Mono;

@Configuration
@EnableReactiveMongoAuditing(
    auditorAwareRef = "reactiveAuditorProvider"
)
public class ReactiveAuditConfig {

    @Bean("reactiveAuditorProvider")
    ReactiveAuditorAware<String> reactiveAuditorProvider() {
        return () -> Mono.just("system-demo");
    }
}
~~~

This is a **demo** bean. Production must resolve the actor from the reactive security context or a verified service principal. If the app uses only imperative MongoDB, do not enable reactive auditing just because Reactor is on the classpath.

### 21.2. Reading the Actor from WebFlux Security

~~~java
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public final class ReactiveSecurityAuditorAware
        implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .filter(auth ->
                auth != null && auth.isAuthenticated()
                    && !(auth instanceof AnonymousAuthenticationToken))
            .map(Authentication::getName);
    }
}
~~~

Bean:

~~~java
@Bean("reactiveAuditorProvider")
ReactiveAuditorAware<String> reactiveAuditorProvider() {
    return new ReactiveSecurityAuditorAware();
}
~~~

Register only **one** `reactiveAuditorProvider`. With Spring Security OAuth2/JWT, `Authentication.getName()` may be `sub` or an adapter-configured claim; ensure it is a **stable principal ID** per policy rather than assuming display names never change.

### 21.3. Why ThreadLocal Is Insufficient

Reactive flows can hop across execution threads while carrying `Reactor Context`. Imperative `SecurityContextHolder` is unreliable in WebFlux reactive pipelines. Misusing thread-local actors in history can record:

~~~text
actor = null
actor = "SYSTEM"
actor = a user from a prior request (if custom ThreadLocal leaks)
~~~

In reactive auditing, use `ReactiveAuditorAware`; in custom services, pass a verified `AuditContext` through the reactive chain. Never set a `ThreadLocal` assuming Reactor preserves it.

### 21.4. Reactive Repository Save Still Does Not Produce Full History

~~~java
Mono<OrderDocument> saved = reactiveOrderRepository.save(order);
~~~

When reactive auditing is enabled and callbacks run through the mapping pipeline, the current entity receives `lastModifiedAt`/`By`. However, that save `Mono` **does not emit 10 prior versions** or insert 10 entries into `order_history_009`.

Just like imperative code, reactive `ReactiveMongoTemplate.updateFirst(...)` differs from the `save(entity)` lifecycle. Direct update operators must set metadata and append history in the application service.

## 22. Reactive Transactions: State + History Must Be Sequenced

### 22.1. Configuring the Reactive Transaction Manager

~~~java
// ReactiveMongoTxConfig.java
package com.example.audit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration
public class ReactiveMongoTxConfig {
    @Bean
    ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }

    @Bean
    TransactionalOperator auditTransactionOperator(
            ReactiveMongoTransactionManager manager) {
        return TransactionalOperator.create(manager);
    }
}
~~~

Reactive transactions pass their session through **Reactor Context**. Inside a single MongoDB transaction, the driver **does not support running operations in parallel on the same session**.

### 22.2. Writing History After Matched Update

~~~java
// ReactiveOrderChangeService.java
package com.example.audit;

import java.time.Clock;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderChangeService {
    private final ReactiveMongoTemplate mongo;
    private final TransactionalOperator transactions;
    private final Clock clock;

    public ReactiveOrderChangeService(
            ReactiveMongoTemplate mongo,
            TransactionalOperator transactions,
            Clock clock) {
        this.mongo = mongo;
        this.transactions = transactions;
        this.clock = clock;
    }

    public Mono<OrderHistoryEvent> changeDeliveryCity(
            String tenantId, String orderId,
            long expectedRevision, String nextCity,
            String actorId, String commandId) {

        return Mono.defer(() -> {
            var now = clock.instant();
            Query eligible = Query.query(
                Criteria.where("id").is(orderId)
                    .and("tenantId").is(tenantId)
                    .and("revision").is(expectedRevision)
            );
            Update change = new Update()
                .set("deliveryCity", nextCity)
                .set("lastModifiedAt", now)
                .set("lastModifiedBy", actorId)
                .inc("revision", 1);

            return mongo.findAndModify(
                    eligible,
                    change,
                    FindAndModifyOptions.options()
                        .returnNew(false),
                    OrderDocument.class
                )
                .switchIfEmpty(Mono.error(
                    new OrderChangeConflictException(
                        "Not found or stale revision")))
                .flatMap(before -> {
                    OrderHistoryEvent event =
                        new OrderHistoryEvent(
                            orderId + ":" + (expectedRevision + 1),
                            tenantId, orderId,
                            expectedRevision + 1,
                            commandId,
                            "DELIVERY_CITY_CHANGED",
                            "USER", actorId,
                            "CUSTOMER_REQUEST",
                            before.getDeliveryCity(),
                            nextCity, now
                        );
                    return mongo.insert(event);
                });
        }).as(transactions::transactional);
    }
}
~~~

**Semantics:** `findAndModify` and `insert(history)` subscribe **sequentially** inside the same reactive transaction. If inserting history fails or the update finds no matching order, the transaction aborts and current state does not commit.

This illustrates the concept: production requires input validation, security context, policy reason codes, idempotency reconciliation, and formal transaction options. Never accept unverified actor/tenant values from clients.

### 22.3. Counterexample: `Mono.when` Inside One Transaction

~~~java
// DO NOT use:
Mono.when(
    mongo.updateFirst(eligible, update, OrderDocument.class),
    mongo.insert(historyEvent)
).as(transactions::transactional);
~~~

Both Publishers would execute inside **one transaction session**—parallel same-session operations are unsupported, and history would insert before knowing if the update matched. Use sequential `flatMap`/`then` as shown above.

### 22.4. Never Call `subscribe()` Manually Inside a Transaction

~~~java
// Wrong:
@Transactional
public Mono<Void> change(...) {
    mongo.updateFirst(...).subscribe();
    mongo.insert(history).subscribe();
    return Mono.empty();
}
~~~

Two separate subscriptions run in independent contexts without sharing session or commit boundaries. Return **one composed Publisher** so WebFlux/consumer/`StepVerifier` subscribes once.

### 22.5. Cancellation Does Not Prove MongoDB Rolled Back

If an HTTP request cancels after the driver sends commit, the transaction may commit even though the client receives no acknowledgment. Handle **unknown outcomes** using stable `commandId`, revision, and reconciliation just as in imperative code.

## 23. Should Audits Record Failed Attempts?

Distinguish two categories:

1. **History of committed state changes**: transitions that actually committed.
2. **Security/operational audit of attempted actions**: including denied or pre-commit-failed attempts.

If a transaction aborts, a history event written **inside that transaction** rolls back too. That is right for a **committed change log**, yet it does not record "User A tried editing Order B and was denied".

### 23.1. Two-Layer Design

~~~text
Business change history:
  -> append event in the same business transaction.
  -> holds committed changes only.

Security/attempt log:
  -> written independently per policy, never rolled back with business tx.
  -> captures rejected/denied/rate-limited attempts.
~~~

### 23.2. Attempts Need Not Live in the Same Collection

A security audit event can hold request ID, authenticated actor, action, allow/deny decision, and timestamp; **never** store raw credentials or unclassified sensitive data.

Written to a separate store, it can be decoupled from business transactions; the goal is **recording that an attempt occurred**, not tracking state revisions.

### 23.3. Why an AFTER_ROLLBACK Listener Is Not Enough

If access control rejects a request **before a transaction/event begins**, no domain event fires and `AFTER_ROLLBACK` never runs. Security auditing must trigger at the **security/business decision point**, not solely on transaction callbacks.

To log failed attempts durably even during application crashes, use a persistent queue/delivery or independent audit service—in-memory callbacks alone cannot provide absolute proof.

## 24. Migration, Backfill, and "History Since When?"

Suppose a system already holds 3 million orders from last year, and today you turn on auditing and create `order_history_009`.

### 24.1. Never Fabricate Historical Events

You can backfill a **baseline snapshot**:

~~~javascript
{
  _id: "o901:baseline",
  order_id: "o901",
  action: "BASELINE_IMPORT",
  baseline_at: ISODate("2026-11-20T00:00:00Z"),
  known_revision: NumberLong(1),
  historical_completeness: "FROM_BASELINE_ONLY"
}
~~~

Never fabricate past `CREATED`/`CHANGED` events without historical evidence. A baseline reflects **state at capture time**, not exact prior transitions.

### 24.2. Recording Coverage Scope Explicitly

Define coverage metadata:

~~~text
historyTrackingStartedAt
baselineSource
baselineChecksum
historySchemaVersion
coverageStatus = COMPLETE_FROM_START | FROM_BASELINE | PARTIAL
~~~

This keeps APIs and auditors from mistaking "a history collection exists" for "complete history exists since the order was born".

### 24.3. Running Migrations Alongside Live Traffic

When backfilling while orders continue updating:

- Use an explicit snapshot/consistency strategy.
- Never overwrite newer revisions with an older baseline.
- Support checkpoints/cursors and idempotent restarts.
- Detect gaps and duplicates.
- Plan safe rollbacks and reruns.

A migration may require specific read concerns, change-stream resume tokens, or planned write freezes. **Never** run ad-hoc collection mutations on production without a design and runbook.

### 24.4. Auditing Changes from Legacy Systems

Migration scripts using the raw driver can write entity state yet **do not get actors attached by auditing annotations**. Assign a service/migration actor ID and emit a `MIGRATION_APPLIED` history event per policy, or keep an approved standalone migration log.

## 25. Performance, Size, and Indexes

### 25.1. Cost per Mutation

With transactional history, each order edit incurs:

~~~text
1 current document update
+ 1 append history insert
+ transaction coordination overhead
+ index maintenance
+ replication/journal durability work
~~~

Write volume and storage grow compared to updating a single document; that is the trade-off for traceability and atomicity.

### 25.2. Indexing History by Access Pattern

For queries like:

~~~javascript
db.order_history_009.find({
  tenant_id: "t01",
  order_id: "o901"
}).sort({ revision: 1 });
~~~

the index:

~~~javascript
{ tenant_id: 1, order_id: 1, revision: 1 }
~~~

supports tenant/order filtering and revision sorting while enforcing unique revisions.

The `{tenant_id, commandId}` index supports idempotency lookups. Still, **every index adds write amplification** on append-heavy collections. Never add indexes without real query workloads.

### 25.3. Batch History Must Not Drop Guarantees

Bulk migrations/imports write many history events, yet `bulkOps(UNORDERED)` is not a transaction. If a batch fails partway, earlier events persist. When aggregate state + history must remain atomic, scope transactions logically and handle retries/partial progress.

### 25.4. Never Stuff Unbounded History into an Array on the Current Document

Anti-pattern:

~~~javascript
{
  _id: "o901",
  history: [
    /* hundreds of thousands of ever-growing entries */
  ]
}
~~~

Documents have a BSON size limit; unbounded arrays cause document relocation, write contention, and heavy read/update costs. A separate history collection is far better whenever event counts are not strictly tiny and bounded.

### 25.5. Choosing Snapshot Intervals When Replay Slows Down

To reconstruct rev 100,000, replaying 100,000 events on every read is expensive. One strategy is taking a snapshot every *N* revisions (e.g., 500, benchmarked) and replaying only subsequent events.

Snapshots must also carry revision/schema version, checksums/verification, and retention policies; never treat a corrupted snapshot as proof of complete history.

### 25.6. Useful Metrics

| Metric | Meaning |
| --- | --- |
| `audit.history.insert_failures` | History append failures |
| `audit.transaction.abort_rate` | Transaction conflicts or aborts |
| `audit.revision_conflicts` | Stale writes / optimistic locking |
| `audit.command_duplicates` | Retries / idempotency hits |
| `audit.coverage_gaps` | Current revisions missing matching history |
| `audit.history_write_latency` | Added latency of writing history |
| `audit.history_query_p95` | Timeline query latency |
| `audit.retention_backlog` | Expired records awaiting archival/cleanup |
| `audit.unauthorized_access` | Unauthorized history query attempts |
| `audit.cdc_lag` | Lag replicating history to analytics stores |

Avoid unbounded metric labels like `orderId`, `userId`, or `commandId`; use traces/security logs for per-ID investigation.

## 26. Integration Testing: Audit Metadata Does Not Become History Automatically

Unit tests mocking repositories cannot prove auditing callbacks, MongoDB transactions, unique indexes, or field mappings work. Verify invariants on a test MongoDB instance.

### 26.1. Environment Prerequisites

- Spring Boot + Spring Data MongoDB matching your project version.
- A **test MongoDB replica set** for multi-document transactions (a single-node replica set suffices for basic commit/abort, not failover).
- `MongoAuditConfig`, `MongoTransactionConfig`, and `OrderChangeService` beans.
- `MongoTemplate` and transaction manager sharing the same `MongoDatabaseFactory`.
- Collections created prior to running transactions.
- Per-test isolated fixtures cleaning up only on the managed test DB.
- **Do not** annotate test methods/classes with `@Transactional` when testing service commit/rollback behavior, as an outer test transaction masks real commit/abort outcomes.

### 26.2. Testing Metadata and Transactional History

~~~java
// MongoAuditingHistoryIntegrationTest.java
package com.example.audit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

@DataMongoTest
@Import({
    MongoAuditConfig.class,
    MongoTransactionConfig.class,
    OrderChangeService.class
})
class MongoAuditingHistoryIntegrationTest {
    private static final String TENANT = "it-audit-009";
    private static final String ORDER = "it-order-009";

    @Autowired MongoTemplate mongo;
    @Autowired OrderChangeService service;

    @BeforeEach
    void prepare() {
        if (!mongo.collectionExists(OrderDocument.class)) {
            mongo.createCollection(OrderDocument.class);
        }
        if (!mongo.collectionExists(OrderHistoryEvent.class)) {
            mongo.createCollection(OrderHistoryEvent.class);
        }

        clearFixture();
        mongo.insert(new OrderDocument(
            ORDER, TENANT, "PENDING", "Hanoi"
        ));
    }

    @AfterEach
    void cleanup() {
        clearFixture();
    }

    private void clearFixture() {
        mongo.remove(
            Query.query(
                Criteria.where("id").is(ORDER)
                    .and("tenantId").is(TENANT)
            ),
            OrderDocument.class
        );

        mongo.remove(
            Query.query(
                Criteria.where("orderId").is(ORDER)
                    .and("tenantId").is(TENANT)
            ),
            OrderHistoryEvent.class
        );
    }

    @Test
    void insertFillsAuditingMetadataButNotHistory() {
        OrderDocument current =
            mongo.findById(ORDER, OrderDocument.class);

        assertThat(current).isNotNull();
        assertThat(current.getCreatedAt()).isNotNull();
        assertThat(current.getCreatedBy()).isEqualTo("system-demo");

        // Entity insert does not auto-create history records.
        assertThat(mongo.count(
            Query.query(
                Criteria.where("orderId").is(ORDER)
            ),
            OrderHistoryEvent.class
        )).isZero();
    }

    @Test
    void transactionUpdatesCurrentAndAppendsHistory() {
        OrderHistoryEvent written = service.changeDeliveryCity(
            TENANT, ORDER, 1L,
            "Hue", "operator-08", "cmd-it-009-1"
        );

        OrderDocument current =
            mongo.findById(ORDER, OrderDocument.class);

        assertThat(current.getDeliveryCity()).isEqualTo("Hue");
        assertThat(current.getRevision()).isEqualTo(2L);
        assertThat(current.getLastModifiedBy())
            .isEqualTo("operator-08");
        assertThat(current.getLastModifiedAt()).isNotNull();

        assertThat(written.getId()).isEqualTo(ORDER + ":2");
        assertThat(written.getBeforeCity()).isEqualTo("Hanoi");
        assertThat(written.getAfterCity()).isEqualTo("Hue");
        assertThat(written.getRevision()).isEqualTo(2L);
        assertThat(written.getActorId()).isEqualTo("operator-08");

        assertThat(mongo.findById(
            ORDER + ":2", OrderHistoryEvent.class
        )).isNotNull();
    }

    @Test
    void staleRevisionCannotOverwriteOrAppendHistory() {
        service.changeDeliveryCity(
            TENANT, ORDER, 1L,
            "Hue", "operator-08", "cmd-it-009-first"
        );

        assertThatThrownBy(() ->
            service.changeDeliveryCity(
                TENANT, ORDER, 1L,
                "Da Nang", "operator-09", "cmd-it-009-stale"
            )
        ).isInstanceOf(OrderChangeConflictException.class);

        OrderDocument current =
            mongo.findById(ORDER, OrderDocument.class);
        assertThat(current.getDeliveryCity()).isEqualTo("Hue");
        assertThat(current.getRevision()).isEqualTo(2L);

        assertThat(mongo.count(
            Query.query(
                Criteria.where("orderId").is(ORDER)
            ),
            OrderHistoryEvent.class
        )).isEqualTo(1L);
    }

    @Test
    void duplicateHistoryAbortsCurrentUpdate() {
        // Seed a history event with _id revision 2
        // to simulate conflict and verify atomic rollback.
        mongo.insert(new OrderHistoryEvent(
            ORDER + ":2", TENANT, ORDER, 2L,
            "cmd-existing", "DELIVERY_CITY_CHANGED",
            "USER", "operator-existing",
            "DATA_REPAIR", "Hanoi", "Can Tho",
            java.time.Instant.now()
        ));

        assertThatThrownBy(() ->
            service.changeDeliveryCity(
                TENANT, ORDER, 1L,
                "Hue", "operator-08", "cmd-conflict"
            )
        ).isInstanceOf(DuplicateKeyException.class);

        OrderDocument after =
            mongo.findById(ORDER, OrderDocument.class);
        assertThat(after.getDeliveryCity()).isEqualTo("Hanoi");
        assertThat(after.getRevision()).isEqualTo(1L);

        // Existing event remains intact; failed tx did not delete prior history.
        assertThat(mongo.findById(
            ORDER + ":2", OrderHistoryEvent.class
        ).getCommandId()).isEqualTo("cmd-existing");
    }

    @Test
    void queryUpdateDoesNotAutomaticallyCreateHistory() {
        OrderDocument before =
            mongo.findById(ORDER, OrderDocument.class);
        var previousLastModified = before.getLastModifiedAt();

        mongo.updateFirst(
            Query.query(
                Criteria.where("id").is(ORDER)
                    .and("tenantId").is(TENANT)
            ),
            new Update().set("deliveryCity", "Hai Phong"),
            OrderDocument.class
        );

        OrderDocument after =
            mongo.findById(ORDER, OrderDocument.class);
        assertThat(after.getDeliveryCity())
            .isEqualTo("Hai Phong");

        // updateFirst does not run save-entity auditing callback
        // like repository.save(entity):
        assertThat(after.getLastModifiedAt())
            .isEqualTo(previousLastModified);
        assertThat(mongo.count(
            Query.query(
                Criteria.where("orderId").is(ORDER)
            ),
            OrderHistoryEvent.class
        )).isZero();
    }
}
~~~

**Limitations:** this example uses `@DataMongoTest` following Spring Boot 3.x structure. Some package/test starter names may differ in Spring Boot 4 or custom setups. If your Spring Data version wraps duplicate-key errors differently, inspect the exception/cause before adjusting assertions; **verifying current-state rollback** is the essential assertion.

### 26.3. This Test Does Not Yet Prove "Full History" Across the Whole System

The test above intentionally seeds its fixture via `mongo.insert(new OrderDocument(...))` **without writing a `CREATED` event** to prove auditing annotations **do not auto-create history**. Thus the fixture only has a revision-2 event after the city change, **not a complete history from `CREATE`**.

To verify full system history, add tests covering `createOrder(...)` (section 15), all other transitions, soft/hard deletes, admin/migration paths, and gap detectors. Never claim every production write is audited based on a single happy-path test.

### 26.4. Testing Under Concurrent Writes

Two concurrent requests both sending `expectedRevision=1` can race. On a replica set:

1. Seed an order at revision 1.
2. Execute two `changeDeliveryCity(..., expectedRevision=1)` calls concurrently.
3. Expect one transaction to encounter `WriteConflict`/transient error or no-match depending on interleaving.
4. Assert final current revision is 2 and exactly one revision-2 history event exists.
5. Assert no "phantom" history event was created for the rejected request.

Never test concurrency merely by running two `save` calls on mocked entities. Real behavior depends on transaction isolation, query predicates, and unique indexes.

### 26.5. Testing Failover / Unknown Commit Results

Usually you cannot accurately simulate `UnknownTransactionCommitResult` by throwing `IllegalStateException` **inside** the transaction body. Testing commit ambiguity requires fault injection at the commit boundary, multi-node test clusters, or a test harness supporting driver error labels.

**Never step down or shut down a production primary or shared MongoDB just for learning.**

## 27. Testing Reactive Auditing and History

### 27.1. Testing Auditing Metadata

With `ReactiveAuditConfig`, `ReactiveMongoTemplate`, and repository beans:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import reactor.test.StepVerifier;

OrderDocument sample = new OrderDocument(
    "rx-audit-009", "rx-tenant", "PENDING", "Hanoi"
);

StepVerifier.create(reactiveMongoTemplate.insert(sample))
    .assertNext(saved -> {
        assertThat(saved.getCreatedAt()).isNotNull();
        assertThat(saved.getCreatedBy()).isEqualTo("system-demo");
    })
    .verifyComplete();
~~~

This snippet runs inside a **test method** with `ReactiveMongoTemplate` injected and reactive auditing configured. Clean up the fixture afterward and ensure the test collection exists. Do not treat it as proof of full history.

### 27.2. Testing State + History Transactions

~~~java
StepVerifier.create(
    reactiveOrderChangeService.changeDeliveryCity(
        "rx-tenant", "rx-audit-009", 1L,
        "Hue", "rx-operator", "rx-command-1"
    )
).assertNext(event -> {
    assertThat(event.getBeforeCity()).isEqualTo("Hanoi");
    assertThat(event.getAfterCity()).isEqualTo("Hue");
}).verifyComplete();

StepVerifier.create(
    reactiveMongoTemplate.findById(
        "rx-audit-009", OrderDocument.class
    )
).assertNext(order -> {
    assertThat(order.getRevision()).isEqualTo(2L);
    assertThat(order.getDeliveryCity()).isEqualTo("Hue");
}).verifyComplete();
~~~

Tests require a **replica set**, pre-created collections, and both components sharing the same `ReactiveMongoDatabaseFactory`. Follow up by testing duplicate history: after `expectError`, query current state to confirm **it stays at rev1 and the old city**.

Calling only:

~~~java
Mono<OrderHistoryEvent> deferred =
    reactiveOrderChangeService.changeDeliveryCity(...);
~~~

without subscribing does **not execute** MongoDB commands. `StepVerifier` ensures the publisher actually runs; never call `block()` in WebFlux runtime code.

### 27.3. Reactive Actors Must Be Attached to Context in Tests

With `ReactiveSecurityAuditorAware`, unit/integration tests must attach a security principal to the Reactor Context using Spring Security test utilities (e.g., `contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth))`). Otherwise the auditor emits `Mono.empty()` and `createdBy` stays unset.

Never tweak tests to force actor `"SYSTEM"` and conclude production code resolves real users accurately.

## 28. Common Misconceptions

| Misconception / Symptom | Why It Is Wrong | Fix |
| --- | --- | --- |
| "Having `@LastModifiedDate` gives full edit history" | Annotation overwrites current metadata | Write dedicated history events |
| "`@Version` saves every version" | Version only guards concurrency | Append history/snapshots per revision |
| "MongoDB journal is an audit log" | Journal serves crash recovery, lacks actor/reason | Domain history + access policies |
| "Application logs are enough for auditing" | Logs drop, rotate, and change formats | Persist canonical audit records |
| "Change streams always provide pre-images" | Pre-images need setup and have bounded retention | Check server docs/config; add app history |
| "`updateFirst` auto-updates `LastModifiedDate`" | Skips entity-save auditing callback | Set metadata explicitly |
| "Bulk writes auto-call auditing callbacks per entity" | Bulk API has a different lifecycle | Explicit service/history policy for bulk |
| "One save auto-creates an audit event" | Spring annotations never append to a second collection | Transactional history insert |
| "Two consecutive Java calls are atomic" | Second failure does not undo the first | MongoDB transaction |
| "Transaction committed means external email sent" | External side effects live outside MongoDB | Outbox and idempotent consumers |
| "History reaching revision 10 means 10 events exist" | May miss `CREATE` or certain mutation paths | Check coverage and gaps |
| "Deleting an order needs no event" | Hard delete wipes out current state | Tombstone/history per policy |
| "Timestamps suffice to order history accurately" | Clock skew, equal millis, pre-commit time | Business revision + transaction semantics |
| "`ActorId` from HTTP body is proof" | Easily forged | Authenticated principal / service identity |
| "Full audit means storing every secret" | Violates data minimization | Store only approved/redacted fields |
| "No setters on history class makes it immutable" | Admins/raw driver can still update/delete | Least privilege, monitoring, immutable archives |
| "Duplicate history should always be ignored" | Could be a payload/command conflict | Verify fingerprint |
| "Commit timeout means nothing wrote" | Commit may have succeeded | Unknown outcome handling + idempotency |
| "Imperative `SecurityContextHolder` suffices in reactive" | Reactive uses Reactor Context | `ReactiveAuditorAware` |
| "`Mono.when` inside a tx boosts throughput" | Parallel same-session operations are unsupported | Sequence transaction operations |
| "Migration backfill knows prior editors" | Only current snapshot exists | Mark baseline coverage |
| "Unique index on history prevents deletions" | Uniqueness does not block deletes/admins | Least privilege, backups, external evidence |
| "1-node majority test proves failover resilience" | 1-node majority needs only one member | Dedicated multi-node chaos tests |
| "Having history removes the need for backups" | History can be corrupted/deleted with the DB | Backups, restore tests, retention policy |

## 29. Production Auditing Design Checklist

1. **Define scope:** do you need only "who/when last edited" or "complete history" from creation to deletion?
2. **Define audit coverage:** which entities, fields, actions, and systems must be recorded?
3. **Enable the right auditing mode**: `@EnableMongoAuditing` for imperative, `@EnableReactiveMongoAuditing` for reactive.
4. **Verify `AuditorAware`/`ReactiveAuditorAware`** resolves actors from trusted identities; never accept forged actors from HTTP bodies.
5. **Verify time handling**: UTC, clock sync, time source, distinguishing `occurredAt` from commit.
6. **Do not mistake metadata for history**: `@LastModifiedDate`/`@LastModifiedBy` hold only the latest values.
7. **Do not mistake version for history**: `@Version` catches conflicts, never persists prior states.
8. **Inventory every write path**: repository saves, `MongoTemplate` updates, bulk, raw driver, migrations, admin scripts, TTL, reactive flows.
9. **Set metadata explicitly** on update-operator paths bypassing entity auditing callbacks.
10. **Design the history schema**: action, actor, tenant, aggregate ID, revision, request/command ID, selective before/after values, reason, schema version.
11. **Create unique indexes** matching `tenant+order+revision` and idempotency key invariants.
12. **Emit `CREATE`, `UPDATE`, `DELETE` events** under a unified policy when end-to-end history is required.
13. **Use MongoDB transactions** for current state and history when all-or-nothing is needed.
14. **Guard current state** with tenant, expected revision, and business predicates; never assume plain `save` prevents all lost updates.
15. **Ensure shared `MongoDatabaseFactory`/session** across transactional operations.
16. **Select commit write concern** matching durability requirements; majority/journal do not replace backups.
17. **Handle unknown commit outcomes**, avoiding blind retries or minting fresh command IDs for the same operation.
18. **Assign explicit system actors** for jobs/migrations, distinguishing users, services, and migrations.
19. **Design privacy policies**: field allowlists, redaction, encryption, access controls, and retention windows.
20. **Never assume collections are immutable**: restrict and monitor update/delete/admin privileges.
21. **Mark baselines** when enabling auditing on legacy data; never fabricate historical transitions from guesswork.
22. **Use `revision` for logical ordering** and query history with tenant guards and keyset pagination.
23. **Evaluate CDC/change streams** regarding retention/resume tokens and missing metadata; never substitute blindly for app semantics.
24. **Separate committed change history from denied-attempt/security audits**.
25. **Test on a real MongoDB replica set**: insert metadata, operator bypasses, transaction rollbacks, unique indexes, stale revisions, and reactive sessions.
26. **Run reconciliation jobs** comparing current revisions against history coverage.
27. **Add observability**: history insert failures, revision conflicts, gaps, idempotency duplicates, and latency.
28. **Maintain runbooks** for restoring or repairing history gaps without fabricating evidence.

## 30. Practice Exercises with Answers

### Exercise 1 — Last-Modified

Current order has `createdAt`, `createdBy`, `lastModifiedAt`, and `lastModifiedBy`. Can we tell who edited it before the last modifier?

**Answer:** Not from those fields. They retain only the creator and the latest modifier. Knowing intermediate edits requires storing history events or another trusted historical log from the outset.

### Exercise 2 — Annotations

Name the annotations for creation time and last modification time.

**Answer:**

~~~java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant lastModifiedAt;
~~~

They require matching auditing configuration and mapping paths; they do not append history automatically.

### Exercise 3 — Who Edited?

Where does `@LastModifiedBy` obtain the user ID?

**Answer:** From `AuditorAware<T>` in imperative or `ReactiveAuditorAware<T>` in reactive auditing, backed by an authenticated identity or service principal. Never trust arbitrary actor inputs from request bodies.

### Exercise 4 — Difference Between `save` and `updateFirst`

Why can `updateFirst` change `deliveryCity` without updating `lastModifiedAt`?

**Answer:** Update operators skip the entity-save/auditing-callback pipeline used by `save(entity)`. Explicitly include audit metadata or route through a standardized application service write path.

### Exercise 5 — `@Version`

Does a document at version 8 mean MongoDB retained versions 1–7?

**Answer:** No. `@Version` provides optimistic locking/versioning on current state; it does not persist prior versions.

### Exercise 6 — Two Sequential Writes

A service updates the order then inserts history without a transaction. History insert fails. What can happen?

**Answer:** The order changed while history is missing. Two sequential Java calls do not provide cross-document/collection atomicity.

### Exercise 7 — Transactions

Write the annotation to roll back both the update and history insert together in imperative Spring Data MongoDB.

**Answer:**

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void changeOrderAndAppendHistory(...) {
    // MongoTemplate operations sharing the same MongoDatabaseFactory.
}
~~~

Requires the transaction manager, a replica set/sharded cluster topology, and invocation through a proxy; the annotation alone does not ensure every dependency shares the session.

### Exercise 8 — Returning the Pre-Update Document

Which `MongoTemplate` API updates by predicate and returns the old document in a single operation?

**Answer:** `findAndModify` with `FindAndModifyOptions.options().returnNew(false)` and a predicate covering ID, tenant, and expected revision; a transaction is still needed if inserting history separately.

### Exercise 9 — Race Condition

Two requests both read revision 3 and attempt to write revision 4. How do you prevent a silent overwrite?

**Answer:** Use optimistic version/guard `revision==3`, wrap history insertion in a transaction, and enforce a unique history key per revision. The losing request handles the conflict/retry per business rules instead of overwriting.

### Exercise 10 — History Fields

Besides actor and timestamp, what details explain a city change?

**Answer:** Tenant, aggregate ID, revision, action, before/after city, `reasonCode`, `commandId`/request correlation, schema version, and source if policy requires. Never force storing full street addresses or secrets.

### Exercise 11 — Event ID

Why is `_id="o901:4"` useful for audit history?

**Answer:** Every revision has a deterministic, unique ID. Duplicate appends are caught by the unique constraint; on retry, verify payload/command rather than blindly ignoring duplicates.

### Exercise 12 — Unknown Commit

MongoDB may have committed state + history, yet the client timed out. Can you re-invoke the business operation with a fresh `commandId`?

**Answer:** Not safely by default. Use a stable command ID, reconcile persisted history, and classify commit errors; naive retries can create a second revision and event.

### Exercise 13 — Created Event

An order was inserted via repository with `@CreatedDate`, yet no `CREATED` event exists. Can history be called complete from the beginning?

**Answer:** No. Append a `CREATED` event per contract (typically in the same transaction) if reconstruction/timelines from creation are required.

### Exercise 14 — Hard Delete

Does deleting an order via `deleteById` automatically preserve prior values in history?

**Answer:** No. Use a controlled deletion path: `findAndRemove`/guard, event/tombstone, transaction, and appropriate retention/privacy policies.

### Exercise 15 — Oplog

Can MongoDB's oplog serve as an infinite audit history store for every revision?

**Answer:** No. The oplog serves replication, has finite retention, and lacks business actors/reasons. Oplog-based CDC needs checkpoints/resume tokens and explicit source semantics.

### Exercise 16 — Full Document Lookup

Does change stream `fullDocument:"updateLookup"` always return the exact snapshot from the original update?

**Answer:** Do not assume so under concurrent writes; the lookup can reflect newer state. For exact previous/new images, configure pre/post-images within retention limits or write diff/history inside transactions.

### Exercise 17 — Replay

History recorded only `ORDER_SHIPPED` and a timestamp, omitting address. Can you reconstruct the address at that revision?

**Answer:** Not from that event alone. You need snapshots/diff events holding sufficient data and schema-aware reducers.

### Exercise 18 — Timestamps

Two application instances update the same order while experiencing clock skew. Should you sort by `occurredAt` or `revision`?

**Answer:** By business `revision` for ordering within the same aggregate. Timestamps aid filtering/reporting yet do not prove strict commit order.

### Exercise 19 — Auditing and User Identity

A client sends `actorId="admin"` in the JSON body. Should that go into `@LastModifiedBy`?

**Answer:** No. Take identity from an authenticated principal or service identity. For delegation, store the real principal, delegator, and reason per policy.

### Exercise 20 — Secrets

In password-change history, should you store plaintext old/new passwords for "completeness"?

**Answer:** No. Record action, actor, timestamp, changed field names, and minimal approved metadata. Never store credentials or secrets.

### Exercise 21 — Migration

Today you enable auditing for data that has existed for a year. Can you synthesize 20 historical revisions from current state?

**Answer:** No. Backfill only a baseline snapshot with clear source/time/coverage; never fabricate unverified transitions.

### Exercise 22 — Reactive Actor

A WebFlux app reads thread-local `SecurityContextHolder` to resolve the actor, yet a pipeline hops threads. What is the risk?

**Answer:** The actor may become missing or wrong. Use `ReactiveAuditorAware` backed by Reactor/Reactive Security context, or propagate a trusted context along the pipeline.

### Exercise 23 — Reactive Transactions

`update order` and `insert history` are composed with `Mono.when(...)` inside a `TransactionalOperator`. What is wrong?

**Answer:** They can execute in parallel on the same session, which the reactive MongoDB driver does not support; inserting history must also depend on the update matching. Use sequential `flatMap` inside the transaction.

### Exercise 24 — Failed Attempts

An unauthorized user attempts to edit an order; the request is blocked before the transaction. Will that attempt appear in committed-change history?

**Answer:** Not automatically. Maintain a security/attempt audit independent of committed-change business history; never mix denied attempts into a "committed changes" log as if writes succeeded.

### Exercise 25 — Admins Can Delete Audits

The history entity class has only constructors/getters and no setters. Does that make it immutable in MongoDB?

**Answer:** No. MongoDB roles with update/delete/admin privileges can still alter or delete documents. Enforce least privilege, monitoring, backups, and—if required—WORM/external evidence.

### Exercise 26 — Complete Audit Coverage

An integration test on `repository.save` shows `@LastModifiedDate` updates. Is that enough to claim every write is audited?

**Answer:** Not yet. Test `updateFirst`, bulk, raw driver, migrations, deletes, reactive writes, and all integration paths; also verify the history collection receives matching events.

### Exercise 27 — Backups

If current state + history use majority/journal transactions, are backups still needed?

**Answer:** Yes. Majority/journal do not protect against accidental committed deletes, code bugs, regional outages, or malicious admin history erasure; maintain backups, restore drills, and approved retention.

### Exercise 28 — Guarantee Scope

A system started recording history in 2026 while data dates back to 2024. Should the API label it "complete history"?

**Answer:** No. Expose `FROM_BASELINE_ONLY` or equivalent coverage metadata stating **when history recording began** and known gaps.

## References

- [Spring Data MongoDB — Auditing](https://docs.spring.io/spring-data/mongodb/reference/mongodb/auditing.html): `@EnableMongoAuditing`, `@EnableReactiveMongoAuditing`, actor/time configuration, and mapping metadata.
- [Spring Data MongoDB — Entity Callbacks](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html): lifecycle mapping, `AuditingEntityCallback`, and write-path boundaries.
- [Spring Data MongoDB — Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking): `@Version`, version guards, and conflicts.
- [Spring Data MongoDB — Template CRUD Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `save`, `updateFirst`, `findAndModify`, and bulk operations.
- [Spring Data MongoDB — Client Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): Mongo transaction manager, reactive sessions, and atomic multi-document writes.
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/mongodb/reference/mongodb/auditing.html): `AuditorAware` and `ReactiveAuditorAware` in Spring Data.
- [Spring Data MongoDB — `MongoTemplate` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoTemplate.html): mapping/CRUD, entity-based vs. operator-based writes.
- [Spring Data MongoDB — `ReactiveMongoTemplate` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveMongoTemplate.html): reactive write/result and transaction flows.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): atomic commit/abort, transaction restrictions, and durability.
- [MongoDB Manual — `findAndModify`](https://www.mongodb.com/docs/manual/reference/method/db.collection.findAndModify/): atomic conditional update returning pre/post-update documents.
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/): unique keys for history revisions and command IDs.
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/): CDC, event resume tokens, and consumer operations.
- [MongoDB Manual — Pre- and Post-Images](https://www.mongodb.com/docs/manual/changestreams/#change-streams-with-document-pre--and-post-images): support conditions and image retention.
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): majority/journal/acknowledgment and rollback risks.
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): retry behavior, ambiguity, and topology.
- [MongoDB Manual — Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/): choosing current document, referenced history, and indexing.
