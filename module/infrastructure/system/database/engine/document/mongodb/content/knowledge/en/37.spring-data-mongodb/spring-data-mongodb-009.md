# Auditing, Creation/Modification Timestamps, and Lifecycle Callbacks in Spring Data MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chapter:** Spring Data MongoDB  
> **Lesson:** Auditing, Creation/Modification Timestamps, and Lifecycle Callbacks

## 1. Problem Statement: Who Created It, Who Modified It, and What Actually Runs Before Saving?

A Java order-management service uses Spring Boot, Spring Data MongoDB, and a MongoDB replica set. Every document needs metadata:

- `createdAt`: creation timestamp.
- `updatedAt`: most recent modification timestamp.
- `createdBy`: identity of the actor that created the document.
- `updatedBy`: identity of the actor that last modified the document.
- `version`: version token for optimistic locking.

It sounds like four annotations are all you need. Yet as soon as a system has multiple ways to update data, critical questions emerge:

1. How does `repository.save(entity)` update timestamps automatically?
2. Does `mongoTemplate.updateFirst(...)` trigger auditing the same way `save()` does?
3. Is `MongoRepository.save()` with a pre-assigned ID classified as an insert or an update?
4. Can you fetch the actor from `SecurityContextHolder` across HTTP requests, scheduled jobs, and async workers?
5. Should data normalization/validation go into `BeforeConvertCallback` or `BeforeSaveCallback`?
6. What happens if a callback emits a Kafka event and the transaction subsequently rolls back?
7. Why might `@CreatedDate` be overwritten in certain flows saving a new entity?
8. When using a reactive repository, can you use a synchronous `AuditorAware`?
9. If the raw MongoDB driver updates a collection, do the annotations still fire?
10. Do you still need a separate immutable audit log for compliance requirements?

Spring Data MongoDB offers **auditing infrastructure** to populate metadata along supported entity-save paths, alongside **entity lifecycle callbacks** to hook into document conversion, saving, and loading. These mechanisms are convenient, yet they are **not database triggers**, do not replace change history, and do not fire on every write path.

### 1.1. Architecture Overview

```text
HTTP request / scheduled job
             │
             ▼
Service layer: validate actor + business input
             │
             ▼
MongoRepository.save / MongoTemplate.save
             │
             ├── determine new vs. existing entity (isNew)
             │
             ├── BeforeConvert event
             │
             ├── BeforeConvert callbacks
             │     ├── custom normalize/validate
             │     └── AuditingEntityCallback
             │          createdAt/updatedAt
             │          createdBy/updatedBy
             │
             ├── MappingMongoConverter
             │     POJO -> BSON Document
             │
             ├── BeforeSave event/callbacks
             │     BSON Document already built
             │
             ├── MongoDB write
             │
             └── AfterSave event/callbacks
                         │
                         ▼
                  returned entity
```

On read:

```text
MongoDB BSON Document
          │
          ├── AfterLoad event
          ├── MappingMongoConverter (BSON -> entity)
          ├── AfterConvert event/callbacks
          ▼
       Java entity
```

Exact event/callback ordering and support depend on API and version; this lesson highlights the boundaries you must control so responsibilities are assigned to the right hooks.

### 1.2. Learning Objectives

After this lesson, you will be able to:

- Configure `@EnableMongoAuditing` and the four auditing annotations.
- Implement `AuditorAware<String>` backed by Spring Security.
- Understand the `setDates` and `modifyOnCreate` defaults.
- Use `Instant`, `DateTimeProvider`, and a controlled `Clock`.
- Distinguish `BeforeConvertCallback`, `BeforeSaveCallback`, `AfterSaveCallback`, `AfterConvertCallback`, and lifecycle events.
- Pick the exact right callback to normalize, validate, attach metadata, or enrich loaded entities.
- Recognize that `updateFirst`, `updateMulti`, `findAndModify`, repository `@Update`, bulk writes, and the raw driver bypass entity auditing.
- Handle actor identity in imperative, reactive, batch, and async contexts.
- Combine optimistic locking with `@Version` and test concurrency.
- Test auditing against a real database rather than mocking annotations.
- Avoid misusing timestamps as an immutable audit history.

---

## 2. What Does Auditing Mean in Spring Data?

In Spring Data, **auditing** is the automatic population of fields recording *who* and *when* an entity was created or modified at framework-supported points in the entity persistence lifecycle.

Four standard annotations:

| Annotation | Meaning | Common Data Types |
|---|---|---|
| `@CreatedDate` | Timestamp when entity was created | `Instant`, `Date`, `LocalDateTime`, supported temporal types |
| `@LastModifiedDate` | Timestamp when entity was last modified | Supported temporal types |
| `@CreatedBy` | Actor that created the entity | E.g., `String`, `UserId` |
| `@LastModifiedBy` | Actor that last modified the entity | Typically matches `AuditorAware<T>` type |

### 2.1. Audit Metadata Is Not a Full Change Log

A document:

```json
{
  "_id": "order-100",
  "status": "SHIPPED",
  "createdBy": "user-7",
  "createdAt": {"$date": "2026-11-14T07:00:00Z"},
  "updatedBy": "warehouse-worker",
  "updatedAt": {"$date": "2026-11-14T08:35:00Z"}
}
```

tells you the *first* and *last* actors and timestamps, yet cannot answer:

- Prior to `SHIPPED`, was the status `PAID` or `CANCELLED`?
- How many times was the document edited?
- Who changed `shippingAddress`?
- Did an actor edit a value and revert it?
- Was metadata altered by a raw update?

For a complete change history, design an **audit trail, version history, outbox, or change-stream pipeline** with dedicated access controls, retention, and integrity guarantees.

### 2.2. Auditing Lives at the Mapping / Application Layer

Spring Data MongoDB auditing runs inside Spring Data's Java entity-processing pipeline. MongoDB Server never reads Java annotations from BSON documents.

Consequences:

- Java code calling Spring Data entity saves gets audited.
- `mongosh` or the raw MongoDB Java Driver writing documents does not trigger Spring callbacks.
- Another microservice sharing the database may bypass Spring auditing.
- `MongoTemplate` query-based updates do not pass through the same entity-save pipeline.

**Never treat `@LastModifiedDate` as a cluster-wide database trigger.**

---

## 3. Dependencies and Project Layout

With Spring Boot, typically include the MongoDB starter:

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
```

When extracting the actor from Spring Security, include the security starter:

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-security</artifactId>
</dependency>
```

When using the reactive stack:

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
</dependency>
```

**Do not include both synchronous and reactive starters together if your app uses only one model.** Let the project's Spring Boot BOM/dependency management manage Spring Data MongoDB versions to avoid binary incompatibilities.

### 3.1. Reference Code Layout

```text
src/main/java/com/example/orders/
  OrdersApplication.java
  config/
    MongoAuditConfiguration.java
  domain/
    OrderDocument.java
  repository/
    OrderRepository.java
  service/
    OrderService.java
  callbacks/
    OrderNormalizationCallback.java
    OrderBeforeSaveCallback.java
src/test/java/com/example/orders/
  OrderAuditingIntegrationTest.java
```

This layout is illustrative. Classes take effect only when picked up by Spring component scanning or imports.

### 3.2. Application MongoDB URI

```yaml
spring:
  data:
    mongodb:
      uri: "mongodb://127.0.0.1:27017/orders_lab"
```

This uses an unauthenticated localhost lab without TLS. Production requires secure connection strings, credentials, TLS, replica set topology, and secret management.

---

## 4. Basic Entity with Auditing Fields

An order document using mutable fields for clarity:

```java
package com.example.orders.domain;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

import java.time.Instant;

@Document(collection = "orders")
public class OrderDocument {

    @Id
    private String id;

    private String customerId;
    private String status;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String updatedBy;

    @Version
    private Long version;

    public OrderDocument() {
    }

    public OrderDocument(String customerId, String status) {
        this.customerId = customerId;
        this.status = status;
    }

    public String getId() {
        return id;
    }

    public String getCustomerId() {
        return customerId;
    }

    public String getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public String getUpdatedBy() {
        return updatedBy;
    }

    public Long getVersion() {
        return version;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
```

Audit fields do not require public setters when Spring Data mapping can populate them directly per entity design. Immutable classes require appropriate constructors, withers, or record mapping.

### 4.1. Distinguish `@Id` and `@Version`

- `@Id` maps the Java ID field to MongoDB `_id`.
- `@Version` supports optimistic locking and participates in new-vs-existing entity detection.
- `@CreatedDate` is not an ID.
- `@LastModifiedDate` is not a version counter.

### 4.2. Prefer `String` for Actor Identity

`String createdBy` is simple and avoids serializing an entire principal or security object into the document. Store a **stable user/service ID**—never store JWTs, session tokens, or objects carrying credentials or permissions.

### 4.3. Never Let Clients Supply Audit Fields

API request DTOs should accept only required business fields:

```json
{
  "customerId": "customer-100",
  "status": "CREATED"
}
```

Never let clients freely send:

```json
{
  "createdBy": "admin",
  "createdAt": "2000-01-01T00:00:00Z"
}
```

and copy them unchecked onto the entity. Audit metadata belongs to server-side actor and clock policies.

---

## 5. Enabling `@EnableMongoAuditing`

Imperative configuration:

```java
package com.example.orders.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

@Configuration
@EnableMongoAuditing
public class MongoAuditConfiguration {
}
```

This registers the auditing infrastructure when the Spring context and MongoDB mapping are properly configured.

### 5.1. Do You Need `AuditorAware` If You Only Want Timestamps?

**Not required.** Per Spring Data documentation, if you only use `@CreatedDate`/`@LastModifiedDate` without `@CreatedBy`/`@LastModifiedBy`, implementing `AuditorAware` is unnecessary.

If you use actor fields, you need a provider to resolve the current actor.

### 5.2. Auditing Is Not Enabled Automatically Just by Using `MongoRepository`

Auditing must be explicitly enabled in configuration; placing annotations on an entity **does nothing** without `@EnableMongoAuditing`.

### 5.3. Place Configuration in a Scanned Package

If `OrdersApplication` lives in `com.example.orders`, `com.example.orders.config` is scanned automatically by Spring Boot's default component scan.

If the configuration sits outside the scan root, import it explicitly or adjust scanning.

### 5.4. Do Not Confuse with JPA Auditing

MongoDB uses:

```java
@EnableMongoAuditing
```

not `@EnableJpaAuditing`. Similarly, MongoDB lifecycle callbacks do not rely on JPA's `@PrePersist` or `@PreUpdate` by default.

---

## 6. Configuring `AuditorAware<String>` from Spring Security

`AuditorAware<T>` is the Spring Data interface that resolves the current actor.

Example:

```java
package com.example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.mongodb.config.EnableMongoAuditing;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

import java.util.Optional;

@Configuration
@EnableMongoAuditing(auditorAwareRef = "currentAuditor")
public class MongoAuditConfiguration {

    @Bean("currentAuditor")
    AuditorAware<String> currentAuditor() {
        return () -> {
            Authentication authentication =
                    SecurityContextHolder.getContext()
                            .getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()
                    || authentication instanceof AnonymousAuthenticationToken) {
                return Optional.empty();
            }

            return Optional.ofNullable(authentication.getName())
                    .filter(name -> !name.isBlank());
        };
    }
}
```

### 6.1. Data Flow

```text
HTTP security filter chain
        │
        ▼
SecurityContextHolder
        │
        └── Authentication
               principal/user ID
                    │
                    ▼
          AuditorAware.getCurrentAuditor()
                    │
                    ▼
              CreatedBy/LastModifiedBy
```

### 6.2. Never Trust Client-Supplied Identity Headers

Wrong:

```java
String actor = request.getHeader("X-User-Name");
```

unless the header is verified by a trusted authentication layer. Clients can easily spoof `"admin"` via headers.

Always read the verified identity established by Spring Security or a trusted, authenticated service identity.

### 6.3. Why Return `Optional.empty()` for Anonymous Requests?

When no authenticated actor exists, `Optional.empty()` indicates no actor is available from the security context. Depending on business rules, the app can:

- Reject writes requiring an authenticated actor.
- Record a dedicated service-account actor via an explicit policy.
- Allow system-created documents to carry an empty actor where permitted.

Avoid mapping every unauthenticated request to `"system"`, as that can mask authentication bugs.

### 6.4. Multiple `AuditorAware` Beans

When the Spring context has multiple `AuditorAware<?>` beans, specify:

```java
@EnableMongoAuditing(auditorAwareRef = "currentAuditor")
```

Otherwise, the framework may fail or pick ambiguously.

### 6.5. Type `T` Must Match

If the entity declares:

```java
@CreatedBy
private String createdBy;
```

then `AuditorAware<String>` matches. If you use a `UserId` value object or `User` entity, verify MongoDB mapping/converters support it and avoid embedding sensitive security attributes.

---

## 7. Auditing in Scheduled Jobs and Background Workers

Not every write originates from an HTTP request.

Examples:

- Scheduled jobs expiring stale orders.
- Kafka consumers updating fulfillment status.
- Batch migrations.
- Retry workers.
- Administrative maintenance scripts.

Outside an HTTP request thread, `SecurityContextHolder` typically holds no authentication.

### 7.1. Never Grab a Random Thread's User Identity

If `AuditorAware` reads a thread-local security context, async workers do not automatically inherit the originating HTTP request's context. Even if context is propagated, evaluate whether attributing a background mutation to the original user makes business sense.

### 7.2. Use Explicit Service Actors

A batch job should carry its own distinct identity, such as:

```text
service:expiry-worker
service:shipment-consumer
service:nightly-import
```

Never label every background worker `admin`, and never write OAuth tokens into `updatedBy`.

### 7.3. Designing Actor Context

A controlled approach:

- HTTP requests: actor from the authenticated principal.
- Message consumers: actor from verified message metadata or a service identity.
- Scheduled jobs: service identity.
- Migrations: approved `migration:<change-id>` actor.

Pass actor explicitly through application service context whenever `SecurityContextHolder` is inapplicable.

### 7.4. A Pitfall with `@Async`

Spring Security context is bound to the current thread. If a service calls:

```java
@Async
public void updateOrderAsync(...) {
    repository.save(order);
}
```

a thread-local `AuditorAware` may fail to see the HTTP request's principal.

Use supported context propagation or an explicit actor parameter; never share a mutable `SecurityContext` object unsafely across tasks.

### 7.5. Never Rely on `ThreadLocal` Arbitrarily in Reactor

Reactive execution switches threads freely. In WebFlux/Reactor, read the actor from **Reactor Context** via `ReactiveAuditorAware` instead of imperative `ThreadLocal` security holders.

---

## 8. `@CreatedDate` and `@LastModifiedDate` Behavior on Insert vs. Save

Suppose a new entity has no ID yet:

```java
OrderDocument order =
        new OrderDocument("customer-100", "CREATED");

OrderDocument saved = repository.save(order);
```

When auditing is enabled and the entity is classified as **new**:

- `@CreatedDate` is set to the creation timestamp.
- `@CreatedBy` is set to the creator actor if the provider returns one.
- `@LastModifiedDate` may also be populated on creation depending on `modifyOnCreate`.
- `@LastModifiedBy` may also be populated on creation depending on `modifyOnCreate`.

### 8.1. Default `modifyOnCreate = true`

`@EnableMongoAuditing` defines:

```java
modifyOnCreate = true
```

This is the documented default. With it, newly created entities are also marked with modification metadata at creation time.

Example document:

```json
{
  "_id": "order-100",
  "status": "CREATED",
  "createdAt": {"$date": "2026-11-14T09:00:00Z"},
  "updatedAt": {"$date": "2026-11-14T09:00:00Z"},
  "createdBy": "user-17",
  "updatedBy": "user-17"
}
```

Some teams prefer `updatedAt` to remain unset until the first real edit. For that, set:

```java
@EnableMongoAuditing(modifyOnCreate = false)
```

Choose one policy and verify behavior on your actual Spring Data version.

### 8.2. `setDates = true`

The attribute:

```java
@EnableMongoAuditing(setDates = true)
```

enables automatic timestamp population and defaults to `true`.

If configured as:

```java
@EnableMongoAuditing(setDates = false)
```

temporal annotations are not populated by the auditing handler. Disable it only when using your own timestamp mechanism.

### 8.3. Subsequent Modifications

```java
OrderDocument existing =
        repository.findById(orderId).orElseThrow();

existing.setStatus("PAID");
OrderDocument updated = repository.save(existing);
```

With auditing active and the entity recognized as existing:

- `createdAt` is preserved.
- `createdBy` is preserved.
- `updatedAt` is updated.
- `updatedBy` is updated.

### 8.4. Does Saving an Unchanged Entity Update `updatedAt`?

Calling `save()` still runs auditing because the framework executes a persistence operation—**it does not diff business fields to see if anything changed**.

Do not assume `updatedAt` changes only when a business field differs.

### 8.5. `@CreatedDate` Is Not the Commit Timestamp

Timestamps come from the application-side time provider when the callback runs prior to writing. That time does not necessarily equal MongoDB's exact commit time.

Inside a long transaction, there can be a gap between callback execution and database commit. If the transaction aborts, a Java object carrying a populated timestamp on the heap does not mean the document persisted.

---

## 9. Choosing Temporal Types: `Instant`, `Date`, `LocalDateTime`

### 9.1. `Instant` Recommended for Event Times

`Instant` represents a point on the UTC timeline:

```java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant updatedAt;
```

It exchanges cleanly across distributed systems, APIs, and databases.

### 9.2. BSON Date and Precision

MongoDB BSON Date represents instants as milliseconds since the Unix epoch.

In Java, `Instant` supports nanosecond precision; when persisted as BSON Date, precision is truncated to **milliseconds**.

Example:

```text
Java Instant:
  2026-11-14T09:00:00.123456789Z

BSON Date:
  2026-11-14T09:00:00.123Z
```

When writing equality assertions in tests, do not expect default mapping to preserve sub-millisecond nanoseconds in MongoDB.

### 9.3. `LocalDateTime` Has No Timezone

`LocalDateTime` represents a calendar date and wall time **without an offset or timezone**. Converting it to BSON Date requires explicit timezone/conversion rules.

In services running across multiple timezones, uncontrolled `LocalDateTime` usage easily causes timestamp drift.

For `createdAt` and `updatedAt`, `Instant` is simpler and safer.

### 9.4. `Date` and `long`

Spring Data auditing supports JDK 8 temporal types, `java.util.Date`, numeric timestamps, and legacy date types per API.

If using `Long`, verify the unit convention of your system. Never assume a `long` stores seconds if the provider emits milliseconds.

### 9.5. Storing Timestamps as Strings?

Storing ISO-8601 strings forfeits native BSON Date sorting, range efficiency, and TTL index support.

For example:

```json
{"updatedAt":"14/11/2026 16:00"}
```

is awkward to query as a date and depends on locale/timezone. Persist native BSON Dates and format for display in the API/UI.

---

## 10. Controlling the Time Source with `DateTimeProvider`

By default, Spring Data uses a provider reading the system clock. Systems often need:

- Deterministic tests.
- Consistent UTC clocks.
- Controlled clocks for simulation.
- Decoupling wall-clock policy from domain logic.

You can supply a custom `DateTimeProvider`.

### 10.1. Configuring `Clock` + `DateTimeProvider`

```java
package com.example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

@Configuration
@EnableMongoAuditing(dateTimeProviderRef = "mongoDateTimeProvider")
public class MongoTimeConfig {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean("mongoDateTimeProvider")
    public DateTimeProvider mongoDateTimeProvider(Clock clock) {
        return () -> Optional.of(Instant.now(clock));
    }
}
```

In a real application, if you also use `AuditorAware`, combine all attributes inside **one** `@EnableMongoAuditing` configuration rather than accidentally enabling auditing twice.

### 10.2. Injecting a `Clock` for Tests

In tests, supply:

```java
Clock.fixed(
        Instant.parse("2026-11-14T09:30:00Z"),
        java.time.ZoneOffset.UTC);
```

Auditing then assigns deterministic timestamps; advance a mutable test clock before updating to verify `updatedAt` advances while `createdAt` stays unchanged.

### 10.3. Host Clock Synchronization

Because auditing uses application-generated timestamps, clock skew can occur across hosts. If two instances differ by 3 minutes, `updatedAt` can appear to move backward.

Production requires NTP synchronization, a strict UTC policy, and clear distinctions among:

- Application write timestamps.
- Server-side `$currentDate` timestamps.
- Actual transaction commit times.
- Business effective dates.

Never rely on `updatedAt` for strict total event ordering in a distributed system without causal/clock guarantees.

### 10.4. Do Not Abuse `DateTimeProvider` for Arbitrary Business Dates

A subscription renewal date or invoice due date is not audit metadata. Do not slap `@CreatedDate` on arbitrary date fields.

---

## 11. `AuditorAware` and `DateTimeProvider` Serve Different Roles

| Component | Question Answered | Related Fields |
|---|---|---|
| `AuditorAware<T>` | Who is acting? | `CreatedBy`, `LastModifiedBy` |
| `DateTimeProvider` | What time is it now? | `CreatedDate`, `LastModifiedDate` |
| `@EnableMongoAuditing` | Is auditing enabled? | All |
| `IsNewStrategy / @Version` | Is the entity new or existing? | Create vs. modify branch |
| `BeforeConvertCallback` | Should the entity change before mapping? | Normalization, auditing |
| `BeforeSaveCallback` | What should be added to the mapped BSON `Document`? | Document-level metadata |
| `AfterConvertCallback` | What should happen after reading into Java? | Enrichment / transient views |

A null audit timestamp may indicate missing enablement or a misconfigured date provider. A null actor points to a missing `AuditorAware` or empty authentication context. Never patch around those by setting audit timestamps manually inside controllers.

---

## 12. `isNew()`: How Does Spring Data Know Insert vs. Update?

Spring Data must classify an entity as **new** or **existing** for several persistence and auditing decisions.

### 12.1. General Rules

Commonly:

- With `@Version`, an uninitialized version (`null` or primitive `0` per rules) signals a new entity.
- Without `@Version`, a `null` ID signals a new entity.
- A non-null ID typically signals an existing entity unless another signal overrides it.
- An entity implementing `Persistable<ID>` controls `isNew()` explicitly.
- Exact behavior depends on mapping, version type, and operation.

### 12.2. Application-Assigned IDs

Example:

```java
OrderDocument order = new OrderDocument(...);
// Suppose the app assigns id before calling repository.save.
```

If the entity **lacks `@Version`** and already has a non-null ID, Spring Data can treat it as existing even though the document has never been inserted. That affects how auditing chooses create vs. modify behavior and how `save()` picks its write path.

Do not "fix" that by unconditionally setting `createdAt` on every `save()`.

### 12.3. `@Version` Assists New-Entity Detection

Example:

```java
@Version
private Long version;
```

When `version` is `null`, the infrastructure typically recognizes the entity as new; once persisted, version increments under optimistic locking semantics.

Primitive version types follow different initial-value rules than wrapper types. Check the documentation for your exact release.

### 12.4. `Persistable<ID>`

An entity carrying a pre-assigned business ID can implement `Persistable`:

```java
import org.springframework.data.domain.Persistable;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;

public class ExternalOrder implements Persistable<String> {
    @Id
    private String id;

    @Transient
    private boolean isNew = true;

    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return isNew;
    }

    // Needs lifecycle hooks to clear the flag after load/save
    // per Spring Data documentation examples.
}
```

**This snippet illustrates the strategy only, not a production-ready entity.** You must clear `isNew` upon loading/saving (e.g., via callbacks) so existing entities are not perpetually flagged new and rejected by duplicate key errors.

### 12.5. Never Use `repository.save` as a "Smart Upsert"

`save()` follows mapping, new-entity detection, and optimistic locking rules. When an ID is pre-assigned, it does not magically inspect the database first to handle every insert/update edge case. If you need key-based upsert semantics, use an explicit upsert operation and set audit fields deliberately.

---

## 13. `@Version` and Optimistic Locking

A separate yet closely related concern: two services read and update the same order concurrently.

```text
Order version = 4
Service A reads version 4
Service B reads version 4

A updates status → save
  version 4 -> 5

B updates shippingAddress → save
  still thinks version 4
  → optimistic locking failure
```

With `@Version`, Spring Data MongoDB provides optimistic locking on supported entity saves.

### 13.1. Example Entity

```java
@Document("orders")
class OrderDocument {
    @Id String id;
    @Version Long version;
    @CreatedDate Instant createdAt;
    @LastModifiedDate Instant updatedAt;
    String status;
}
```

### 13.2. Example Save

```java
OrderDocument order = repository.findById(id).orElseThrow();
order.setStatus("PAID");
repository.save(order);
```

If another write intervened, `save` throws `OptimisticLockingFailureException` under compatible mapping and write concern.

### 13.3. Write Concern

Spring Data MongoDB documentation emphasizes using an acknowledged write concern (`ACKNOWLEDGED` or stronger) to detect optimistic locking errors. Never use unacknowledged writes and expect conflict detection.

### 13.4. Auditing Does Not Replace Optimistic Locking

`updatedAt` alone cannot prevent lost updates. Two clients can update a document within the same millisecond, and timestamps do not perform compare-and-swap.

Use `@Version` or conditional updates checking expected version.

### 13.5. Handling Optimistic Conflicts

Never blindly overwrite the newer document. Instead:

1. Reload the latest state.
2. Check whether changes can be merged safely.
3. Apply your business conflict policy.
4. Perform bounded, idempotent retries only where appropriate.

---

## 14. What Are Lifecycle Callbacks?

Spring Data provides `EntityCallback<T>` interfaces invoked at specific points in the mapping and persistence pipeline.

They offer a type-safe, ordered mechanism for modifying entities at well-defined stages compared to older application event listeners.

### 14.1. Key Callbacks

| Callback | Timing | Suitable Use Cases |
|---|---|---|
| `BeforeConvertCallback<T>` | Before entity converts to BSON `Document` | Normalize fields, prepare persisted values, auditing |
| `BeforeSaveCallback<T>` | After conversion, before MongoDB write | Mutate BSON `Document`, low-level metadata |
| `AfterSaveCallback<T>` | After framework save completes | Observe or adjust returned entity safely |
| `AfterConvertCallback<T>` | After BSON converts back to Java entity | Populate derived transient views, normalize read models |
| `ReactiveBeforeConvertCallback<T>` | Reactive equivalent | Reactor-safe async transformation |
| `ReactiveBeforeSaveCallback<T>` | Reactive equivalent | Mutate BSON before reactive write |
| `ReactiveAfterConvertCallback<T>` | Reactive equivalent | Enrich loaded entity |

Spring Data MongoDB auditing runs via `AuditingEntityCallback` during the **BeforeConvert** stage.

### 14.2. Why Is `BeforeConvert` the Right Place for Entity Changes?

At `BeforeConvert`, the mapper has not yet serialized the Java entity to BSON. Changes made to persistent Java properties appear in the BSON `Document` written afterward.

### 14.3. Why Does `BeforeSave` Require Care?

`BeforeSaveCallback` runs **after the BSON `Document` has already been built**. Spring Data docs note that modifying persistent properties on the Java entity alone at this stage **will not update the `Document` being saved**.

To affect what is actually persisted:

- Modify the Java entity in `BeforeConvertCallback`; or
- Modify the BSON `Document` parameter directly in `BeforeSaveCallback` when justified.

### 14.4. Why Does `AfterSave` Not Guarantee an External Event?

The callback runs after a save call, not necessarily after a multi-document transaction commits. If a subsequent step inside a transaction fails and rolls back, any external API call made inside `AfterSaveCallback` cannot be rolled back.

Never fire critical emails, payments, or Kafka events straight from `AfterSaveCallback`.

---

## 15. `BeforeConvertCallback`: Normalizing Entities Before Saving

Example: product/status fields should be trimmed and uppercased.

```java
package com.example.orders.callbacks;

import com.example.orders.domain.OrderDocument;
import org.springframework.core.annotation.Order;
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
@Order(50)
public class OrderNormalizationCallback
        implements BeforeConvertCallback<OrderDocument> {

    @Override
    public OrderDocument onBeforeConvert(
            OrderDocument entity,
            String collection) {

        if (!"orders".equals(collection)) {
            return entity;
        }

        if (entity.getStatus() != null) {
            entity.setStatus(
                    entity.getStatus().trim().toUpperCase(
                            java.util.Locale.ROOT));
        }

        return entity;
    }
}
```

### 15.1. Why `@Order(50)`?

Per Spring Data MongoDB docs, `AuditingEntityCallback` has order **100** in current releases. A custom callback with order `50` runs before auditing during `BeforeConvert`.

Ordering expresses dependencies cleanly:

```text
BeforeConvert callbacks:
  order 50 → normalize
  order 100 → auditing
  order 200 → optional post-audit adjustment
```

Never rely on class names or bean registration order for business logic.

### 15.2. Keep Mutations Tightly Scoped

Callbacks are cross-cutting infrastructure. Avoid:

- Making network API calls.
- Running unbounded database queries inside callbacks.
- Generating random business values on each retry.
- Arbitrarily altering `createdAt`.
- Calling `repository.save` on the same entity inside a callback (causing infinite recursion).

### 15.3. Mutable vs. Immutable Entities

The example mutates `entity` because `OrderDocument` is mutable. For immutable entities or Java records, the callback must **return a new copied instance** with the updated values—never hack final fields via reflection.

### 15.4. Repeated Execution

A callback may execute multiple times if an entity is saved repeatedly or a transaction retries. Normalization logic must be **idempotent** (like `trim` and `toUpperCase`).

---

## 16. `BeforeSaveCallback`: Modifying the Built BSON `Document`

Example: adding a schema marker directly to BSON before persistence.

```java
package com.example.orders.callbacks;

import com.example.orders.domain.OrderDocument;
import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class OrderBeforeSaveCallback
        implements BeforeSaveCallback<OrderDocument> {

    @Override
    public OrderDocument onBeforeSave(
            OrderDocument entity,
            Document document,
            String collection) {

        if ("orders".equals(collection)) {
            document.put("schemaRevision", 2);
        }

        return entity;
    }
}
```

### 16.1. What Gets Saved?

The BSON document contains `schemaRevision: 2`, even though the Java class has no mapped `schemaRevision` property.

### 16.2. Warning on Consistency Between Entity and BSON

If you add fields to `Document` that do not exist on the Java entity, the entity returned by `save()` **does not reflect everything written to MongoDB**.

When a field belongs to the domain model, declare a mapped property and populate it in `BeforeConvertCallback`.

### 16.3. Anti-Pattern

Wrong:

```java
@Override
public OrderDocument onBeforeSave(
        OrderDocument entity,
        Document document,
        String collection) {

    entity.setStatus("PAID");
    return entity;
}
```

If BSON was already converted with `status: CREATED`, mutating only the Java entity inside `BeforeSave` will not update the saved `Document`.

To change persistent status, do it in `BeforeConvertCallback`—or update `document.put("status", "PAID")` intentionally with appropriate guards.

### 16.4. Never Establish Security Authority Arbitrarily in Callbacks

Never use `BeforeSave` to override ownership or tenant IDs from untrusted sources. Access control belongs in the authentication/service layer and MongoDB authorization policies.

---

## 17. `AfterSaveCallback`: After the Write Completes

A safe example: recording a lightweight metric or setting a transient display field on the returned entity.

```java
package com.example.orders.callbacks;

import com.example.orders.domain.OrderDocument;
import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.AfterSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class OrderAfterSaveCallback
        implements AfterSaveCallback<OrderDocument> {

    @Override
    public OrderDocument onAfterSave(
            OrderDocument entity,
            Document document,
            String collection) {

        // Safe to record sanitized metrics here.
        // Do not send emails, Kafka events, or payments directly.
        return entity;
    }
}
```

### 17.1. Do Not Treat This Callback as "Transaction Committed"

Service flow:

```text
start MongoDB transaction
  save order → AfterSaveCallback runs
  save inventory → fails
abort transaction
```

If `AfterSaveCallback` published a Kafka message when `save(order)` ran, Kafka received an event for an aborted transaction.

### 17.2. Use Outbox Instead of External Side Effects

To publish events reliably after an order commits:

1. Write the order.
2. Write an outbox document.
3. Commit the MongoDB transaction.
4. Background worker reads the outbox and publishes.
5. Consumers deduplicate idempotently.

This solves dual-write consistency; `AfterSaveCallback` is an entity-save hook, not a distributed transaction commit hook.

### 17.3. Logging Inside `AfterSave`

Never log entire raw `Document` objects containing PII or payment data. Log sanitized metadata:

- Entity type.
- Namespace/collection.
- Operation class.
- Sanitized trace/correlation ID.
- Metric counters.

---

## 18. `AfterConvertCallback`: Hooking into Reads

Example entity with a JVM-only display field:

```java
import org.springframework.data.annotation.Transient;

@Transient
private String displayStatus;
```

Callback:

```java
import com.example.orders.domain.OrderDocument;
import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.AfterConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class OrderAfterConvertCallback
        implements AfterConvertCallback<OrderDocument> {

    @Override
    public OrderDocument onAfterConvert(
            OrderDocument entity,
            Document document,
            String collection) {

        // For mutable entities, populate transient fields
        // via appropriate setters.
        return entity;
    }
}
```

### 18.1. Suitable Use Cases

- Derived display fields.
- In-memory normalization of legacy values.
- Lightweight enrichment without external I/O.
- Read-time compatibility for older schemas.

### 18.2. Never Silently Alter Audit Metadata on Read

If a callback modifies `createdAt` in memory while the database holds another value, API responses diverge from stored truth. Keep derived views clearly separate from persisted audit fields.

### 18.3. Never Use `AfterConvert` to Load Related Collections

If reading every entity triggers a secondary query to another collection, a `findAll()` of 1,000 entities fires 1,000 extra queries (N+1) and spikes latency.

Use DTO projections, aggregations, or explicit batch loading instead.

---

## 19. How Do `EntityCallbacks` Differ from `ApplicationEvents`?

Spring Data MongoDB also publishes lifecycle **mapping events** built on Spring's `ApplicationEvent`.

Examples:

- `BeforeConvertEvent`.
- `BeforeSaveEvent`.
- `AfterSaveEvent`.
- `AfterLoadEvent`.
- `AfterConvertEvent`.

### 19.1. Legacy Event Listener Example

```java
import org.springframework.data.mongodb.core.mapping.event.AbstractMongoEventListener;
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertEvent;
import org.springframework.stereotype.Component;

@Component
public class LegacyOrderListener
        extends AbstractMongoEventListener<OrderDocument> {

    @Override
    public void onBeforeConvert(
            BeforeConvertEvent<OrderDocument> event) {
        // Legacy event hook. Prefer EntityCallback
        // when deterministic entity mutation and ordering are needed.
    }
}
```

### 19.2. Why Prefer `EntityCallback` for Entity Mutations?

Per Spring Data documentation:

- `EntityCallback` is invoked synchronously at well-defined checkpoints.
- It can return a newly constructed or modified entity (essential for immutable types).
- Separate imperative and reactive interfaces exist.
- Callbacks support explicit `@Order` / `Ordered` sequencing.

`ApplicationEvent` dispatch relies on `ApplicationEventMulticaster`. If configured with an async task executor, execution order and completion timing are **not guaranteed** the same way.

### 19.3. Event vs. Callback Ordering

Spring Data MongoDB docs note that store-specific `ApplicationEvent`s are still published **before** the corresponding `EntityCallback`.

Do not confuse:

```text
BeforeConvertEvent
      ≠
BeforeConvertCallback
```

If you mix legacy listeners and modern callbacks, trace their order carefully and never mutate audit fields in both places.

### 19.4. Spring Events Are Not Kafka Events

A Spring `ApplicationEvent` is an in-process application context notification. It has none of a message broker's durability, retry, or delivery guarantees.

### 19.5. Root Entities vs. Nested Types

MongoDB lifecycle events fire for **root-level mapped entities**, not separately for every embedded subdocument inside a document. `DBRef`/document references follow separate rules.

Do not expect an embedded `Address` to trigger its own entity lifecycle callbacks whenever its parent `OrderDocument` is saved.

---

## 20. Ordering Auditing Callbacks and Custom Callbacks

Spring Data MongoDB uses `AuditingEntityCallback` to populate audit fields during `BeforeConvert`. Current documentation specifies its default order as **100**.

### 20.1. Why Does Order Matter?

Suppose you need:

1. Normalize `status`.
2. Populate auditing metadata.
3. Compute a derived field using actor and timestamp.

A callback with order `< 100` runs before auditing; a callback with order `> 100` in the same stage runs after auditing.

### 20.2. `@Order` and `Ordered`

```java
@Component
@Order(50)
class NormalizeBeforeConvert
        implements BeforeConvertCallback<OrderDocument> {
    // ...
}
```

Or implement `Ordered` and return the integer precedence.

### 20.3. `LOWEST_PRECEDENCE`

Callbacks without an explicit order typically default to `Ordered.LOWEST_PRECEDENCE`. Never rely on bean names or classpath scan order for business behavior.

### 20.4. `@Order` Cannot Reorder Across Different Stages

Even with `@Order(-100)` on a `BeforeSaveCallback`, it still runs during the **post-conversion `BeforeSave` stage**, never ahead of `BeforeConvert`.

Ordering applies only **within a given checkpoint**, not across pipeline phases.

### 20.5. Avoid Multiple Callbacks Mutating the Same Field

If auditing sets `updatedAt` and a custom callback overwrites it, ownership becomes murky. Keep a single source of truth for metadata and verify it with tests.

---

## 21. Not Every Write Through Spring Data Runs Auditing Callbacks

This is the single most common source of bugs.

### 21.1. Entity Save and Insert

Calls such as:

```java
repository.save(entity);
mongoTemplate.save(entity);
mongoTemplate.insert(entity);
```

flow through the entity mapping and callback pipeline, triggering auditing when enabled.

### 21.2. Query-Based Updates

Calls such as:

```java
mongoTemplate.updateFirst(query, update, OrderDocument.class);
mongoTemplate.updateMulti(query, update, OrderDocument.class);
mongoTemplate.findAndModify(query, update, OrderDocument.class);
```

are **query-based MongoDB updates**, not entity saves traversing `BeforeConvert`/`BeforeSave`. Therefore, do not expect `@LastModifiedDate` to populate automatically as in `save()`.

### 21.3. Repository `@Update`

Declarative update example:

```java
@Query("{ '_id': ?0 }")
@Update("{ '$set': { 'status': ?1 } }")
long setStatusById(String id, String status);
```

Where supported, this executes a query update rather than `save(entity)`. Explicitly include `updatedAt` and `updatedBy` in the update expression or service layer.

### 21.4. `BulkOperations`

```java
mongoTemplate.bulkOps(
        BulkOperations.BulkMode.ORDERED,
        OrderDocument.class);
```

Bulk operations dispatch batched write models and **do not run per-entity lifecycle callbacks with `save()` semantics**; many versions also have `@Version` limitations in bulk mode.

Do not expect automatic auditing on bulk items. Explicitly set audit fields in each bulk update/insert payload or use a tested helper abstraction.

### 21.5. Raw Java Sync Driver

```java
mongoClient.getDatabase("orders_lab")
        .getCollection("orders")
        .updateOne(
                Filters.eq("_id", id),
                Updates.set("status", "PAID"));
```

Spring's `AuditingEntityCallback` is completely absent from this path.

### 21.6. MongoDB Shell and Migration Scripts

A `mongosh` command:

```javascript
db.orders.updateOne(
  { _id: "order-100" },
  { $set: { status: "PAID" } }
);
```

never triggers Java annotations or callbacks. Migrations and operational runbooks must update audit metadata explicitly per policy.

---

## 22. Updating `updatedAt`/`updatedBy` in `MongoTemplate.updateFirst`

Imperative example:

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

import java.time.Clock;
import java.time.Instant;

public class OrderUpdateService {

    private final MongoTemplate mongoTemplate;
    private final Clock clock;

    public OrderUpdateService(
            MongoTemplate mongoTemplate, Clock clock) {
        this.mongoTemplate = mongoTemplate;
        this.clock = clock;
    }

    public void markPaid(String id, String actorId) {
        if (actorId == null || actorId.isBlank()) {
            throw new IllegalArgumentException("Missing actor");
        }

        Query query = Query.query(
                Criteria.where("_id").is(id));

        Update update = new Update()
                .set("status", "PAID")
                .set("updatedAt", Instant.now(clock))
                .set("updatedBy", actorId);

        mongoTemplate.updateFirst(
                query,
                update,
                OrderDocument.class);
    }
}
```

### 22.1. Why Set Auditing Fields Manually?

Because this is a query-based update. Entity auditing annotations never run without converting and saving an `OrderDocument` entity.

### 22.2. Server Clock with `$currentDate`

Alternatively:

```java
Update update = new Update()
        .set("status", "PAID")
        .set("updatedBy", actorId)
        .currentDate("updatedAt");
```

MongoDB sets `updatedAt` using the database server's clock per `$currentDate` semantics.

### 22.3. Client Clock or Server Clock?

Pick **one consistent policy**:

- Entity saves with `@LastModifiedDate` use the application clock.
- `$currentDate` uses the MongoDB server clock.
- Mixing both on the same collection can introduce subtle skew.
- Across multiple services, document the canonical timestamp source explicitly.

### 22.4. Validate Actor and State Transitions

Never read `actorId` from an unverified raw header. Also include state preconditions in the `Query` if business rules require `updatedAt` to change only when a genuine transition happens.

---

## 23. Query Upserts: Creation Fields vs. Modification Fields

Upserts require special handling because a single command may either insert a new document or update an existing one.

MongoDB update modifiers:

- `$setOnInsert`: applied only when the upsert actually inserts a new document.
- `$set`: applied on both insert and update.
- `$currentDate`: sets/updates a server-side timestamp.

Example:

```java
Instant now = Instant.now(clock);

Query query = Query.query(
        Criteria.where("externalOrderId")
                .is(externalOrderId));

Update update = new Update()
        .setOnInsert("createdAt", now)
        .setOnInsert("createdBy", actor)
        .set("updatedAt", now)
        .set("updatedBy", actor)
        .set("status", "RECEIVED");

mongoTemplate.upsert(
        query,
        update,
        OrderDocument.class);
```

### 23.1. Why `$setOnInsert`?

If the document already exists, `createdAt` and `createdBy` must remain untouched.

### 23.2. Avoid Conflicting Operators on the Same Field

Never place the same field under two conflicting modifiers in one update (for example, both `$setOnInsert` and `$currentDate` on `updatedAt`).

### 23.3. Unique Indexes

Concurrent upserts by an external business key require a unique index to prevent duplicate documents:

```javascript
db.orders.createIndex(
  { externalOrderId: 1 },
  { unique: true }
);
```

### 23.4. Auditing and Upserts

Query upserts bypass entity-save auditing. Supply all audit fields explicitly in the `Update` expression as shown.

### 23.5. Version

While Spring Data may apply certain version behaviors on mapped updates, **never assume `save()`-style optimistic locking is enforced on a query update lacking an expected-version predicate**.

Specify both the `version` filter condition and increment semantics explicitly whenever conflict detection is required.

---

## 24. Atomic Updates with Expected Version and Audit Metadata

Suppose the client read order version `4` and only wants to update if nothing else intervened:

```java
Query query = new Query()
        .addCriteria(Criteria.where("_id").is(orderId))
        .addCriteria(Criteria.where("version").is(4L));

Update update = new Update()
        .set("status", "PAID")
        .set("updatedAt", Instant.now(clock))
        .set("updatedBy", actor)
        .inc("version", 1L);

UpdateResult result = mongoTemplate.updateFirst(
        query,
        update,
        OrderDocument.class);
```

### 24.1. Check `modifiedCount`/`matchedCount`

If no document matched the expected version:

- The order does not exist,
- The order exists with a different version, or
- Another filter condition failed to match.

Never return success without checking `UpdateResult`.

### 24.2. Avoid Double-Incrementing Version

Spring Data MongoDB includes automatic version handling in some update operations. When writing `.inc("version", 1L)` manually, verify your exact Spring Data version's behavior so `version` is not incremented twice.

When in doubt, either use `repository.save()` with `@Version` or write integration tests verifying exact stored versions on explicit updates.

### 24.3. `updatedAt` Does Not Replace `version`

Two writes in the same millisecond share identical timestamps. An incrementing numeric `version` provides true compare-and-swap semantics against lost updates.

---

## 25. Embedded Audit Metadata

Spring Data Commons allows placing auditing annotations inside an embedded value object across supported store mappings.

Example:

```java
public class AuditMetadata {
    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String updatedBy;

    // Constructors/getters/setters or immutable mapping.
}

@Document("orders")
public class OrderDocument {
    @Id
    private String id;

    private String status;

    private AuditMetadata audit = new AuditMetadata();
}
```

### 25.1. When Does This Fit?

When many entities share identical metadata fields and you want a uniform embedded schema.

### 25.2. Do Not Confuse Embedded Objects with Separate Lifecycle Callbacks

Auditing infrastructure can traverse embedded objects where supported, yet **never expect MongoDB to emit separate root-style lifecycle callbacks for every embedded sub-object**.

### 25.3. Null Embedded Objects

If `audit` is `null` and cannot be instantiated automatically, auditing may fail to populate nested fields as expected. Write integration tests confirming nested metadata is populated and persisted.

### 25.4. Schema Trade-Offs

A nested layout:

```json
{
  "audit": {
    "createdAt": {"$date":"..."},
    "updatedAt": {"$date":"..."}
  }
}
```

differs from flat root fields. Queries, indexes, and reports must reference dotted paths such as `audit.updatedAt`.

---

## 26. Auditing with Immutable Entities, Records, and Constructors

Increasingly, Java applications adopt immutable domain models.

### 26.1. The Challenge

A Java record:

```java
public record OrderRecord(
        String id,
        String status,
        Instant createdAt,
        Instant updatedAt) {
}
```

has no setters; auditing needs a way to construct an updated instance carrying the metadata.

### 26.2. Spring Data Constructor and Wither Mapping

Spring Data supports immutable mapping through established conventions:

- Persistence constructors.
- Constructor parameter names.
- Wither methods (`withCreatedAt(...)`, etc.).
- Kotlin data classes and Java records in compatible versions.
- Mapping metadata and converters.

Do not force Spring Data to mutate `final` fields via illegal reflection across modern Java runtimes.

### 26.3. Callbacks Must Return the New Instance

In `BeforeConvertCallback<T>`:

```java
@Override
public OrderRecord onBeforeConvert(
        OrderRecord entity,
        String collection) {

    return new OrderRecord(
            entity.id(),
            entity.status().trim(),
            entity.createdAt(),
            entity.updatedAt());
}
```

This demonstrates immutable normalization rather than full record auditing. When using `@CreatedDate`/`@LastModifiedDate` on immutable types, confirm Spring Data can populate those properties via constructors or withers.

### 26.4. Integration Tests Are Essential

Never rely solely on unit tests calling the callback directly. Verify:

1. Inserting an immutable record.
2. Actual BSON timestamps and actors written to MongoDB.
3. Reading the entity back cleanly.
4. Updating the entity without losing `createdAt`.
5. Version increments and conflicts.
6. The framework actually persists the new instance returned by your callback.

---

## 27. Reactive Auditing: Never Mistakenly Use `AuditorAware`

For reactive Spring Data MongoDB, use:

- `@EnableReactiveMongoAuditing`.
- `ReactiveAuditorAware<T>`.
- Matching `Reactive...Callback` interfaces.

### 27.1. Configuration

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.data.mongodb.config.EnableReactiveMongoAuditing;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

@Configuration
@EnableReactiveMongoAuditing(
        auditorAwareRef = "reactiveCurrentAuditor")
public class ReactiveMongoAuditConfiguration {

    @Bean("reactiveCurrentAuditor")
    ReactiveAuditorAware<String> reactiveCurrentAuditor() {
        return () -> ReactiveSecurityContextHolder
                .getContext()
                .map(context -> context.getAuthentication())
                .filter(Authentication::isAuthenticated)
                .map(Authentication::getName);
    }
}
```

### 27.2. Reactor Context

Never read `SecurityContextHolder` thread-locals inside reactive operators. Reactor switches threads across operators, whereas authentication propagates through **Reactor Context**.

### 27.3. Reactive Callbacks

Example:

```java
import org.springframework.data.mongodb.core.mapping.event.ReactiveBeforeConvertCallback;
import reactor.core.publisher.Mono;

@Component
public class ReactiveOrderCallback
        implements ReactiveBeforeConvertCallback<OrderDocument> {

    @Override
    public Mono<OrderDocument> onBeforeConvert(
            OrderDocument entity,
            String collection) {

        entity.setStatus(entity.getStatus().trim());
        return Mono.just(entity);
    }
}
```

### 27.4. Imperative and Reactive Infrastructure Are Separate

Spring Data docs state that synchronous APIs invoke synchronous entity callbacks while reactive APIs invoke reactive callbacks. Never expect a synchronous `BeforeConvertCallback<T>` to fire inside `ReactiveMongoTemplate` operations.

Likewise, `@EnableMongoAuditing` does not enable auditing for the reactive stack.

### 27.5. Never Block Inside a Reactive Callback

Avoid `.block()` or blocking JDBC/HTTP calls inside reactive callbacks. If asynchronous enrichment is needed, compose reactive operators cleanly while guarding against N+1 latency.

---

## 28. Auditing Inside MongoDB Transactions

Spring Data MongoDB participates in transactions when configured with a transaction manager and supporting topology.

### 28.1. Transaction Manager Required

For imperative Spring Data MongoDB:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfig {

    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
```

Once transaction infrastructure is configured, services can use `@Transactional`.

### 28.2. Illustrative Service

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public CheckoutService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void createOrder(OrderDocument order,
                            OutboxDocument event) {
        orders.insert(order);
        outbox.insert(event);
    }
}
```

Conceptual example requiring configured beans/repositories and a replica set or sharded cluster supporting transactions.

### 28.3. When Are Timestamps Assigned?

Auditing callbacks assign `createdAt`/`updatedAt` **before database commit**. If the transaction rolls back, the Java object on the heap still holds those populated timestamps even though MongoDB discarded the write.

Never equate "entity has a non-null `createdAt`" with "transaction committed."

### 28.4. `AfterSave` Is Not After-Commit

If an `AfterSaveCallback` sends an email immediately when `orders.insert` succeeds inside a transaction, and `outbox.insert` subsequently aborts the transaction, the email has already been sent.

For external events, use an outbox or after-commit coordination with recovery—never treat `AfterSave` as a durable publication boundary.

### 28.5. Transaction Retries

When a transaction retries on transient errors, entity callbacks run again on each attempt. Therefore:

- Keep normalization idempotent.
- Avoid external side effects.
- Do not randomly regenerate business IDs per attempt.
- Never publish events directly from callbacks.
- Note that `DateTimeProvider` may return slightly different timestamps across attempts.

### 28.6. `@Transactional` Does Not Turn Raw Driver Calls into Spring Entity Callbacks

Mixing Spring Data repositories and raw MongoDB Java Driver calls inside one transaction without proper session binding breaks both atomicity and audit metadata. Understand transaction propagation and driver session binding.

---

## 29. Auditing Does Not Protect `createdAt` from Tampering

### 29.1. Raw Updates Can Overwrite Metadata

Any user with update privileges on the collection can execute:

```javascript
db.orders.updateOne(
  { _id: "order-100" },
  { $set: { createdAt: new Date("2000-01-01T00:00:00Z") } }
);
```

MongoDB will not inspect Spring Data's `@CreatedDate` to block that write.

### 29.2. Defense Strategies

- Least-privilege RBAC.
- Exclude audit fields from public request DTOs.
- Forbid modifying `createdAt`/`createdBy` in service logic.
- Restrict update expressions to explicit field allowlists.
- Apply database `$jsonSchema` validation where appropriate.
- Maintain a separate append-only audit collection when compliance requires it.
- Enforce audit-log access controls and retention.
- Use optimistic locking for concurrent edits.
- Alert on anomalous metadata modifications.

### 29.3. No Trustworthy "Last Writer Identity" If Actors Can Be Spoofed

If `AuditorAware` reads an arbitrary client-supplied header, `updatedBy` is untrustworthy.

Audit identities must always originate from a verified authentication and authorization context.

### 29.4. Human Actor vs. Service Actor

A scheduled job may update an order on a user's behalf. `updatedBy` should record the service actor actually performing the database write, while any originating human initiator can be tracked separately:

```json
{
  "updatedBy": "service:shipment-consumer",
  "initiatedBy": "user-17"
}
```

Never conflate the two and claim a human directly executed a background worker's write.

---

## 30. Distinguishing Audit Metadata from Change History

| Requirement | `createdAt`/`updatedAt`/`By` | Dedicated Audit History |
|---|---|---|
| Show initial creation / last edit time | Fits | May be overkill |
| Show last modifying actor | Fits | May be overkill |
| View full history of all edits | Insufficient | Required |
| Retain before/after field values | No | Requires explicit design |
| Compliance / forensic investigation | Supplementary only | Stronger tamper-evident mechanism needed |
| Event-driven integration | Insufficient | Outbox / change streams fit |
| Restore previous versions | Insufficient | Version history / backups |
| Detect raw-update tampering of audit fields | No guarantee | Requires controls / monitoring |

### 30.1. Audit Collection

An audit event record might contain:

```json
{
  "_id": "audit-...",
  "entityType": "Order",
  "entityId": "order-100",
  "actorId": "user-17",
  "action": "STATUS_CHANGED",
  "eventTime": {"$date": "2026-11-14T09:30:00Z"},
  "before": {"status": "CREATED"},
  "after": {"status": "PAID"},
  "requestId": "req-..."
}
```

Audit records are sensitive: apply encryption, retention policies, strict access controls, and avoid logging excessive secrets or PII.

### 30.2. Atomic Business Write + Audit Event

If compliance requires audit history to stay strictly synchronized with business state, write both inside a single MongoDB transaction (on supporting deployments) or use an outbox architecture with guarantees.

Never rely on saving the order first and inserting an audit record separately if a failure between the two would lose audit evidence.

### 30.3. Change Streams

MongoDB Change Streams observe collection mutations for integration pipelines, but require:

- Replica set / sharded cluster and appropriate privileges.
- Resume token management.
- Awareness of oplog retention windows.
- Idempotent/deduplicating consumers.
- Schema evolution handling.

Change streams alone cannot identify the application actor unless the mutated document or event carries actor metadata.

---

## 31. Auditing and Time-to-Live (TTL) Indexes

A common design question: to expire documents after 30 days, should a TTL index target `updatedAt` or `createdAt`?

### 31.1. TTL on `createdAt`

If the policy is "delete 30 days after creation," indexing `createdAt` fits cleanly when no legal hold or retention exception applies.

### 31.2. TTL on `updatedAt`

If the policy is "delete after 30 days of inactivity," a TTL index on `updatedAt` can work—with caveats:

- `repository.save()` updates `updatedAt` even when business fields did not change.
- Query-based updates that forget to set `updatedAt` fail to extend the TTL.
- Mixing server-side and app-side clocks causes minor drift.
- MongoDB's TTL monitor deletes asynchronously, not instantaneously.

### 31.3. Never Overload `createdAt` as Business Expiration

`createdAt` is audit metadata, whereas `expiresAt` is a business policy field; keep them separate when lifecycles differ.

Example:

```json
{
  "createdAt": {"$date": "..."},
  "updatedAt": {"$date": "..."},
  "expiresAt": {"$date": "..."}
}
```

### 31.4. TTL Is Not Millisecond-Exact Deletion

MongoDB's TTL background thread runs periodically; never design security controls or strict SLAs assuming a document disappears at the exact millisecond it expires.

---

## 32. Auditing During Imports, Migrations, and Backfills

Legacy documents may lack `createdAt`/`updatedAt`. Reading and calling `save()` on them can overwrite metadata with **migration time** instead of actual historical creation time.

### 32.1. Historical Data Risk

Suppose an order was originally created in 2022 without `createdAt`. A 2026 migration loads and saves orders with auditing enabled.

If the framework classifies them as new or overwrites missing timestamps, historical accuracy is lost.

### 32.2. Migration Strategy

- Extract original creation timestamps from legacy sources.
- Define explicit migration field mappings.
- Track `migratedAt` and `migratedBy` separately.
- Never fabricate `createdAt` from migration time when history matters.
- Restrict service accounts permitted to backfill audit fields.
- Use bounded batch query updates with explicit policies.
- Inspect before/after samples and retain backups.

### 32.3. Raw Bulk Migrations Skip Callbacks

Sometimes skipping entity-save callbacks during a targeted single-field backfill is desirable for speed—just make sure your script sets any required audit metadata explicitly.

### 32.4. Never Trigger Heavy Callback Logic Over Millions of Rows

If a callback queries external services or secondary collections across millions of migrated rows, overhead explodes. Use batched migration tools with checkpoints and metrics.

---

## 33. Complete Repository and Service Example

### 33.1. Repository

```java
package com.example.orders.repository;

import com.example.orders.domain.OrderDocument;
import org.springframework.data.mongodb.repository.MongoRepository;

import java.util.List;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    List<OrderDocument> findByCustomerId(String customerId);
}
```

### 33.2. Service for Creation and Updates

```java
package com.example.orders.service;

import com.example.orders.domain.OrderDocument;
import com.example.orders.repository.OrderRepository;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public OrderDocument create(
            String customerId, String status) {

        OrderDocument order =
                new OrderDocument(customerId, status);

        return repository.insert(order);
    }

    public OrderDocument changeStatus(
            String id, String newStatus) {

        OrderDocument order = repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Order not found: " + id));

        order.setStatus(newStatus);
        return repository.save(order);
    }
}
```

### 33.3. On Creation

- `insert(order)` passes through supported entity mapping and callbacks.
- Creation/modification metadata is populated per configuration.
- ID and version are managed by mapping rules.
- Returns the persisted entity.

### 33.4. On Modification

- `findById` loads the document.
- `save` runs `BeforeConvert` callbacks.
- `updatedAt` and `updatedBy` update when auditing is active.
- `createdAt` and `createdBy` remain preserved for existing entities.
- With `@Version`, concurrency conflicts are detected.

### 33.5. Never Give Clients Unrestricted Entity Control

Map incoming API DTOs containing only allowed fields rather than deserializing requests straight into entities with auditing fields and calling `save` unconditionally. Enforce authorization and business validation.

---

## 34. Integration Testing Against Real MongoDB

A unit test calling `onBeforeConvert()` directly proves only that method's Java code—not that Spring registered the bean, detected `isNew`, or persisted valid BSON.

### 34.1. Testing Tools

Options:

- `@DataMongoTest` for repository/mapping slice tests.
- `@SpringBootTest` when testing Spring Security, auditing config, and transactions together.
- Testcontainers MongoDB configured as a replica set when testing transactions.
- An isolated test/CI MongoDB instance.
- Fixed `Clock` for deterministic assertions.

### 34.2. Timestamp Verification Example

Assuming repository and auditing configuration are initialized in an integration test:

```java
OrderDocument created =
        repository.insert(
                new OrderDocument(
                        "customer-100", "CREATED"));

assertNotNull(created.getCreatedAt());
assertNotNull(created.getUpdatedAt());

Instant firstCreatedAt = created.getCreatedAt();
Instant firstUpdatedAt = created.getUpdatedAt();

created.setStatus("PAID");
OrderDocument saved = repository.save(created);

assertEquals(firstCreatedAt, saved.getCreatedAt());
assertNotNull(saved.getUpdatedAt());
assertFalse(saved.getUpdatedAt().isBefore(firstUpdatedAt));
```

These assertions assume `modifyOnCreate = true`. With `modifyOnCreate = false`, `updatedAt` after `insert` may be `null`, so adjust assertions to match policy.

### 34.3. Inspecting BSON Directly in MongoDB

In `mongosh`:

```javascript
db.getSiblingDB("orders_lab")
  .orders.findOne({ _id: "..." });
```

Verify:

- Audit fields exist in the stored document.
- Date fields are native BSON Dates.
- Actor IDs match expectations.
- ID and version are valid.

Do not rely solely on Java getters.

### 34.4. Testing Actor Resolution

Use an authenticated test principal or controlled `AuditorAware` test bean:

- Insert as actor A → `createdBy = A`.
- Update as actor B → `createdBy = A`, `updatedBy = B`.
- No authentication → matches policy (empty, rejected, or service identity).

### 34.5. Testing That Query Updates Bypass Auditing

1. Create a document and record `updatedAt`.
2. Call `mongoTemplate.updateFirst` setting only `status`.
3. Reload the document from the database.
4. Assert `updatedAt` **did not change automatically** because query updates skip entity auditing callbacks.
5. Repeat setting `updatedAt` explicitly to verify policy compliance.

### 34.6. Testing Version Conflicts

Two copies at the same version:

1. Load A and B.
2. Save A.
3. Save B.
4. Assert `OptimisticLockingFailureException` under an acknowledged write concern.
5. Confirm B did not silently overwrite A.

### 34.7. Testing Callback Ordering

Register two `BeforeConvertCallback` beans with explicit `@Order` values and assert transformation order rather than relying on fragile log timings.

### 34.8. Testing Transaction Rollbacks

When using transactions:

- Insert an entity inside a transaction.
- Callback populates `createdAt`/actor.
- Abort the transaction.
- Verify the database contains no document.
- Verify no external event escaped from callbacks.

---

## 35. Testing with a Fixed `Clock` and Test Actor

An integration test configuration:

```java
@TestConfiguration
class TestAuditConfig {

    @Bean
    @Primary
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2026-11-14T09:30:00Z"),
                ZoneOffset.UTC);
    }

    @Bean("testAuditor")
    AuditorAware<String> testAuditor() {
        return () -> Optional.of("test-user");
    }
}
```

**Note:** If production config defines multiple `AuditorAware` beans and `@EnableMongoAuditing(auditorAwareRef = ...)` names another bean explicitly, `@Primary` alone may not override it. Ensure the test context resolves the intended bean reference.

### 35.1. Why Fixed `Clock` Beats `Thread.sleep`

Sleeping in tests:

```java
Thread.sleep(1000);
```

just to make `updatedAt` greater than `createdAt` slows suites down, adds flakiness, and does not prove where the framework gets its time.

A fixed or controllable `Clock` gives deterministic timestamps with zero sleeping.

### 35.2. BSON Precision

When comparing timestamps read back from MongoDB, choose test instants aligned to millisecond precision or truncate expected values to BSON Date precision.

### 35.3. Never Mock Away `MongoTemplate` When Testing Callbacks

Mocking repositories or `MongoTemplate` only checks method invocations without executing the real mapping lifecycle. Always use integration tests to verify auditing wiring and BSON persistence.

---

## 36. Performance: What Overhead Do Callbacks Add?

### 36.1. Auditing Metadata Is Usually Lightweight

Populating a few fields adds negligible cost in most workloads, consisting of:

- Time provider call.
- Auditor lookup.
- Mapping metadata lookup.
- Callback invocation.
- Object mutation/copying.
- BSON serialization.
- Extra document bytes.

### 36.2. I/O Inside Callbacks Slows Every Save

If `BeforeConvertCallback` calls a user-profile HTTP API for every save:

```text
1000 saves/s
× 1 HTTP request/callback
= 1000 extra network calls/s
```

Never do this when the actor ID is already available in the security context.

### 36.3. N+1 Queries Inside `AfterConvert`

A `findAll()` returning 10,000 documents invokes `AfterConvertCallback` 10,000 times. Secondary database lookups per callback explode latency and connection pool demand.

### 36.4. Bulk Path Trade-Offs

Bulk and query updates skip per-entity auditing and callbacks for throughput:

- Higher write throughput.
- Fewer object conversions.
- Caller must populate metadata and invariants manually.

Never pick bulk writes expecting per-entity hooks to fire.

### 36.5. Relevant Metrics

Monitor:

- Save/insert p95/p99 latency.
- MongoDB writes/sec.
- Custom callback execution duration when non-trivial logic exists.
- Error rates from validation or version conflicts.
- Actor lookup failures.
- MongoDB server latency.
- Audit metadata document size.
- Batch throughput.

### 36.6. Do Not Log Actors at `INFO` on Every Write Unnecessarily

High-volume actor logs bloat storage and leak PII. Keep metric labels low-cardinality—never use user IDs as metric tags.

---

## 37. Common Pitfalls and Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| `createdAt` is null after `save` | `@EnableMongoAuditing` missing | Check configuration and component scan |
| `updatedBy` is null | `AuditorAware` returned empty | Verify `SecurityContext` or service identity |
| `updatedAt` unchanged after `updateFirst` | Query update skips entity auditing | Set audit fields explicitly in `Update` |
| `createdAt` overwritten on `save` | Entity classified as new | Check ID, `@Version`, and `isNew` |
| `updatedAt` populated on insert | `modifyOnCreate = true` | Confirm policy or set to `false` |
| `updatedAt` missing on insert | `modifyOnCreate = false` | Expected under that policy |
| `AuditorAware` bean not found | Bean outside scan or multiple beans | Register bean and set `auditorAwareRef` |
| Wrong actor inside `@Async` | Thread-local security context not propagated | Pass actor explicitly or propagate context |
| Reactive auditing does not run | Using imperative auditing beans | Use `@EnableReactiveMongoAuditing` / `ReactiveAuditorAware` |
| `BeforeSave` edits entity but BSON unchanged | Conversion already occurred | Mutate `Document` or move logic to `BeforeConvert` |
| Event listener fires out of order | Async `ApplicationEventMulticaster` | Use `EntityCallback` for deterministic mutations |
| Callback misses nested objects | Lifecycle applies to root entities | Keep audit metadata on root or map intentionally |
| Callback skipped on raw driver writes | Bypasses Spring Data mapping | Set audit fields manually |
| Bulk write omits actor/time | Skips per-entity callbacks | Include audit fields in bulk payloads |
| `OptimisticLockingFailureException` | Concurrent save with stale version | Reload, reconcile, or retry safely |
| Timestamp timezone mismatch | Using `LocalDateTime` / system default zone | Standardize on `Instant` and UTC |
| `Instant` nanoseconds lost | BSON Date millisecond precision | Normalize expected precision in tests |
| Callback sends event on aborted tx | `AfterSave` runs before commit | Use outbox or after-commit coordination |
| Migration sets all `createdAt` to today | Backfill ignored historical timestamps | Preserve source timestamps; track `migratedAt` |
| Spoofed actor in `updatedBy` | Trusting unverified client header | Read from authenticated principal |
| Auditing missing in Mockito unit tests | Mocks bypass mapping pipeline | Write real integration tests |
| `version` skips increment in bulk | Bulk has distinct `@Version` semantics | Enforce explicit version handling and tests |
| Wrong collection name in callback | Dynamic collection name / SpEL | Inspect callback's `collection` parameter |
| Multiple `@EnableMongoAuditing` configs | Duplicate/conflicting registrations | Keep a single authoritative audit config |
| Huge object stored in `createdBy` | `AuditorAware` returns full principal | Store a compact, stable user ID |
| Save misbehaves with pre-assigned ID | `isNew` detection treats it as existing | Review `@Id`, `@Version`, and `Persistable` |
| Callback saving entity causes recursion | Calling `save` on same entity inside hook | Move persistence orchestration out of hooks |

---

## 38. Case Study: Silent Bug When Switching `save` to `updateFirst`

### 38.1. Initial Implementation

The service updates order status via:

```java
OrderDocument order =
        repository.findById(id).orElseThrow();

order.setStatus("SHIPPED");
repository.save(order);
```

Auditing runs cleanly:

```text
status: SHIPPED
updatedAt: now
updatedBy: warehouse-user
```

### 38.2. Performance Optimization

The team switches to:

```java
mongoTemplate.updateFirst(
        Query.query(Criteria.where("_id").is(id)),
        Update.update("status", "SHIPPED"),
        OrderDocument.class);
```

The update succeeds, yet `updatedAt` and `updatedBy` stay frozen at their old values.

### 38.3. Why?

Query-based updates never materialize or convert an entity through the entity-save pipeline and `AuditingEntityCallback`.

### 38.4. Fix

```java
Update update = new Update()
        .set("status", "SHIPPED")
        .set("updatedBy", authenticatedActorId)
        .currentDate("updatedAt");

mongoTemplate.updateFirst(
        Query.query(Criteria.where("_id").is(id)),
        update,
        OrderDocument.class);
```

### 38.5. Architectural Lesson

Applications mixing entity saves and query updates need a **centralized audit policy at the data-access service layer** rather than hoping every developer remembers to set audit fields manually.

Consider a helper:

```java
public Update withAudit(
        Update update, String actorId) {
    return update
            .set("updatedBy", actorId)
            .currentDate("updatedAt");
}
```

Ensure every approved query-update path calls and tests this helper—while remembering it still does not govern raw driver calls or external migration scripts.

---

## 39. Case Study: Event Emitted Despite Transaction Rollback

### 39.1. Anti-Pattern

```java
@Component
class NotifyAfterSave
        implements AfterSaveCallback<OrderDocument> {

    @Override
    public OrderDocument onAfterSave(
            OrderDocument order,
            Document bson,
            String collection) {

        kafkaPublisher.publish("OrderCreated", order.getId());
        return order;
    }
}
```

### 39.2. What Happens?

Service flow:

```text
start transaction
insert order
  → AfterSaveCallback publishes event
update inventory
  → WriteConflict
abort transaction
```

Kafka already received an event for an order that never committed.

### 39.3. Better Design

- Write both the order and an outbox event inside the same MongoDB transaction.
- Commit the transaction.
- A background worker polls the outbox and publishes to Kafka.
- Consumers deduplicate by event ID.

### 39.4. What Are Callbacks Still Good For?

Use callbacks for metadata enrichment, validation, normalization, or lightweight metrics—never as durable integration-event dispatchers.

---

## 40. Case Study: Actor Lost Inside an Asynchronous Message Consumer

### 40.1. Symptom

The HTTP service sets `createdBy = user-17` properly. A Kafka consumer sharing the same repository updates the order and writes `updatedBy = null`.

### 40.2. Cause

`AuditorAware` reads `SecurityContextHolder`, which is empty on the Kafka consumer thread.

### 40.3. Fix

- Assign a service actor such as `service:fulfillment-consumer`.
- Store the originating human initiator in a separate field if needed.
- Pass scoped, verified actor context into worker services.
- Never forge user principals in `ThreadLocal`.
- Write integration tests for the async consumer path.

### 40.4. Never Infer the Actor from Existing Document Fields

Never copy `createdBy` into `updatedBy` when context is missing; that corrupts the audit trail regarding who actually performed the latest edit.

---

## 41. Case Study: Legacy Data Overwritten with Wrong `createdAt`

### 41.1. Symptom

After a migration, millions of historical documents show `createdAt` equal to the migration deployment date.

### 41.2. Possible Causes

- Backfill ignored source creation timestamps.
- Saving entities with ID/version states caused Spring Data to treat them as new.
- Migration script blindly set `createdAt = now` across all rows.
- Legacy data lacked audit fields and the workflow failed to separate creation from migration.

### 41.3. Remediation

1. Recover authoritative creation timestamps from source records or backups.
2. Distinguish `createdAt` from `migratedAt`.
3. Design migration jobs with snapshots and backups.
4. Dry-run on a small batch first.
5. Apply idempotent conditional updates targeting missing fields only.
6. Verify samples with and without existing fields.
7. Avoid bulk `repository.save()` calls if auditing side effects distort history.

---

## 42. Exercise 1: Enabling Minimal Auditing

Tasks:

1. Create a Spring Boot project with the MongoDB starter.
2. Create a `Customer` entity with ID, `name`, `createdAt`, and `updatedAt`.
3. Enable `@EnableMongoAuditing`.
4. Insert a document via `MongoRepository`.
5. Inspect the BSON in `mongosh`.
6. Update via `save()`.
7. Compare `createdAt` and `updatedAt`.

Question: do timestamp annotations work without declaring an `AuditorAware` bean?

---

## 43. Exercise 2: `createdBy`/`updatedBy`

Create an `AuditorAware<String>` supporting three actors:

- `user-A`.
- `user-B`.
- `service:batch`.

Steps:

1. `user-A` inserts a document.
2. `user-B` updates it.
3. Batch job updates it.
4. Inspect `createdBy` and `updatedBy` after each step.
5. Avoid assuming `SecurityContext` is populated inside scheduled jobs.

Explain why raw JWT tokens must never be stored in `createdBy`.

---

## 44. Exercise 3: `modifyOnCreate`

Run two configurations in the lab:

- `modifyOnCreate = true`.
- `modifyOnCreate = false`.

Compare `updatedAt` and `updatedBy` immediately after insert. Define a clear policy when the UI wants to display "Never edited" for freshly created documents.

---

## 45. Exercise 4: `BeforeConvert` vs. `BeforeSave`

Write two callbacks:

1. `BeforeConvertCallback` trimming the product name.
2. `BeforeSaveCallback` adding `schemaRevision` to the BSON `Document`.

Try mutating a persistent Java field inside `BeforeSave` without modifying the BSON `Document`. Inspect the stored document in `mongosh` and explain the outcome.

---

## 46. Exercise 5: `save` vs. `updateFirst`

Create an order, then:

1. Update `status` via `repository.save()`.
2. Record `updatedAt` and `updatedBy`.
3. Update `status` via `mongoTemplate.updateFirst` setting only `status`.
4. Inspect the auditing fields.
5. Rewrite `updateFirst` using `$currentDate` and explicit actor.
6. Explain why annotations are not MongoDB triggers.

---

## 47. Exercise 6: Timestamps and Precision

Using:

```text
2026-11-14T09:00:00.123456789Z
```

as a fixed clock instant:

1. Insert an entity with `@CreatedDate Instant`.
2. Read the Java object back.
3. Inspect the raw BSON document.
4. Explain millisecond precision truncation.
5. Discuss `LocalDateTime` vs. `Instant`.
6. Design a UTC policy for three services deployed across different timezones.

---

## 48. Exercise 7: Optimistic Locking

Create an entity with `@Version Long version`:

1. Load two copies A and B.
2. Edit and save A.
3. Edit and save B.
4. Observe the exception.
5. Propose a merge/retry policy.
6. Explain why `updatedAt` cannot replace `@Version`.

---

## 49. Exercise 8: Reactive Auditing

Using WebFlux and `ReactiveMongoRepository`:

1. Enable `@EnableReactiveMongoAuditing`.
2. Configure `ReactiveAuditorAware<String>`.
3. Extract the actor from `ReactiveSecurityContextHolder`.
4. Insert via the reactive repository.
5. Verify `createdBy` upon subscription.
6. Implement a `ReactiveBeforeConvertCallback`.
7. Explain why plain `ThreadLocal` `SecurityContextHolder` fails here.

---

## 50. Exercise 9: Transactions and After-Save Side Effects

A callback sends an email inside `AfterSaveCallback`. A service inserts an order inside a transaction, and a subsequent inventory update fails.

Answer:

1. Could the email have already been sent?
2. Is the order still in the database?
3. What caused the two systems to diverge?
4. Propose an outbox design.
5. Write an integration test verifying rollback behavior.
6. Explain how callbacks must behave when transactions retry.

---

## 51. Exercise 10: Backfilling Legacy Data

100,000 documents lack `createdAt` yet carry `legacyCreatedDate`.

1. Design a migration that populates `createdAt` only where missing.
2. Never overwrite documents that already have `createdAt`.
3. Record `migratedAt` and `migratedBy` separately.
4. Ensure batch retries are idempotent.
5. Explain why entity-save callbacks should not dictate the entire migration policy.
6. Verify counts and sample documents after backfilling.

---

## 52. Exercise 11: Auditor Security

A system reads actor ID from an unverified `X-User` HTTP header.

1. Show how `createdBy`/`updatedBy` can be spoofed.
2. Replace it with Spring Security's authenticated principal.
3. Handle `AnonymousAuthenticationToken`.
4. Handle async scheduled jobs.
5. Separate service actors from originating human initiators.
6. Write a test covering unauthenticated requests.

---

## 53. Exercise 12: Choosing an Audit History Solution

Compliance requirements:

- Track every status modification.
- Record before/after values.
- Record actor and timestamp.
- Retain records for 7 years.
- Prevent users from altering audit evidence.

Explain why `@LastModifiedDate`/`@LastModifiedBy` alone are insufficient. Propose an audit collection or event history with RBAC, encryption, retention, tamper-evidence, and transactional/outbox consistency.

---

## 54. Implementation Checklist

### 54.1. Enablement

- [ ] Compatible MongoDB starter added.
- [ ] `@EnableMongoAuditing` or `@EnableReactiveMongoAuditing` configured as appropriate.
- [ ] Configuration resides within the scanned `ApplicationContext`.
- [ ] Spring Data annotations used (not JPA annotations).
- [ ] `auditorAwareRef` specified when multiple providers exist.
- [ ] `modifyOnCreate` and `setDates` policies defined.

### 54.2. Entity Model

- [ ] `createdAt`/`updatedAt` use suitable temporal types, preferring `Instant` where appropriate.
- [ ] `createdBy`/`updatedBy` store stable actor identities, never secrets.
- [ ] `@Version` added wherever optimistic locking is needed.
- [ ] `isNew` behavior understood for pre-assigned IDs.
- [ ] Public DTOs never allow arbitrary overrides of audit fields.
- [ ] Immutable entity mapping and callbacks tested.

### 54.3. Callback Lifecycle

- [ ] Pre-conversion normalization/mutation sits in `BeforeConvert`.
- [ ] BSON-level adjustments sit in `BeforeSave`.
- [ ] Persistent Java properties are not mutated in `BeforeSave` expecting BSON changes.
- [ ] Callback `@Order` defined explicitly where dependencies exist.
- [ ] External side effects kept out of `AfterSave`.
- [ ] JPA lifecycle annotations are never used in place of MongoDB callbacks.
- [ ] Callbacks avoid slow I/O and recursive saves.
- [ ] Reactive code uses reactive callbacks.

### 54.4. Write Paths

- [ ] Inventoried all repository `save`/`insert` paths.
- [ ] Inventoried all `MongoTemplate` `updateFirst`/`updateMulti`/`findAndModify`/`upsert` calls.
- [ ] Inventoried all repository `@Update` queries.
- [ ] Inventoried all bulk operations.
- [ ] Inventoried raw driver, `mongosh`, and migration writers.
- [ ] Every query-based update needing audit metadata sets it explicitly.
- [ ] Timestamp source and actor source policies are consistent.

### 54.5. Transactions and Security

- [ ] Actors resolved from trusted authentication contexts.
- [ ] Scheduled jobs use dedicated service actor identities.
- [ ] `AfterSave` is never treated as transaction commit.
- [ ] External event integrations use outbox/recovery patterns.
- [ ] Optimistic locking and write concern verified.
- [ ] Separate compliance audit history designed where required.

### 54.6. Tests and Monitoring

- [ ] Real MongoDB integration tests cover insert, save, and update.
- [ ] Tests verify actor A, actor B, and unauthenticated cases.
- [ ] Tests confirm `createdAt` remains immutable on update.
- [ ] Tests cover `modifyOnCreate` policy.
- [ ] Tests confirm query updates bypass entity callbacks unless set explicitly.
- [ ] Tests verify `@Version` conflicts.
- [ ] Reactive flows tested if applicable.
- [ ] Transaction rollback behavior tested.
- [ ] BSON Date types and millisecond precision verified.
- [ ] Alerts monitor unexpected null actors or missing audit timestamps.

---

## 55. Common Misconceptions

| Misconception | Reality |
|---|---|
| Adding `@CreatedDate` is enough | Auditing infrastructure must be enabled |
| Auditing always requires `AuditorAware` | Timestamp-only auditing does not require it |
| `@LastModifiedDate` changes only when business fields diff | Any `save` triggers it |
| `updatedAt` is always null on insert | Default `modifyOnCreate = true` populates it |
| `createdAt` comes from MongoDB's commit clock | Usually comes from the app-side time provider before write |
| Spring Data audits every write in the collection | Only writes flowing through supported entity pipelines |
| `updateFirst` triggers `BeforeConvert` | Query updates differ from entity saves |
| The raw driver honors annotations | No |
| Bulk writes always run callbacks | Do not assume so |
| Mutating a Java property in `BeforeSave` updates BSON | BSON was already converted |
| `AfterSave` means transaction committed | No |
| `ApplicationEvent` listeners run in strict order asynchronously | No |
| Callbacks fire independently for embedded sub-objects | Root lifecycle != nested events |
| Callbacks add zero overhead | They add cost, especially if performing I/O or queries |
| Non-null `@Id` always means existing | Depends on `@Version`, `Persistable`, and `isNew` rules |
| `@Version` and `updatedAt` serve the same role | Distinct mechanisms |
| `updatedAt` prevents concurrent overwrites | No |
| `AuditorAware` always sees the user inside `@Async` | No |
| An `X-User` header is a trustworthy actor | Only if authenticated/verified by a trusted layer |
| `ReactiveAuditorAware` uses standard `ThreadLocal` | Must use Reactor Context |
| String dates match BSON Dates | No |
| `Instant` nanoseconds survive in BSON Date | Truncated to milliseconds |
| Having `createdAt` inside a transaction means it committed | Transaction can still roll back |
| Audit fields are a complete audit trail | Only first/last metadata |
| Store the full Spring Security principal in `createdBy` | Store a stable compact user ID |
| Migration `save()` cannot corrupt historical metadata | It can if `isNew`/logic is wrong |
| Audit metadata prevents DB tampering by itself | Requires RBAC, validation, and separate history |
| Failed callbacks always retry safely | Requires idempotency and transaction design |
| Mockito unit tests suffice to verify auditing | Real mapping integration tests are essential |

---

## 56. Official References

The following references come from Spring Data MongoDB and Spring Data Commons. Always match your project's exact release line for callback signatures, auditing options, and mapping behavior.

- [Spring Data MongoDB — Auditing](https://docs.spring.io/spring-data/mongodb/reference/mongodb/auditing.html)
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/mongodb/reference/data-commons/auditing.html)
- [Spring Data MongoDB — Lifecycle Events](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html)
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html)
- [Spring Data MongoDB — Template API](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html)
- [Spring Data MongoDB — Repositories](https://docs.spring.io/spring-data/mongodb/reference/repositories.html)
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html)
- [Spring Data MongoDB — Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking)
- [Spring Data MongoDB API — EnableMongoAuditing](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/config/EnableMongoAuditing.html)
- [Spring Data MongoDB API — BeforeConvertCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/BeforeConvertCallback.html)
- [Spring Data MongoDB API — BeforeSaveCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/BeforeSaveCallback.html)
- [Spring Data MongoDB API — AuditingEntityCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/AuditingEntityCallback.html)
- [Spring Data MongoDB — Bulk Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.bulk-operations)
- [MongoDB Manual — BSON Date](https://www.mongodb.com/docs/manual/reference/bson-types/#date)
- [MongoDB Manual — Optimistic Concurrency and Atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [Spring Security — Servlet Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/index.html)
- [Spring Security — Reactive Authentication](https://docs.spring.io/spring-security/reference/reactive/authentication/index.html)

> **Note:** Examples show configuration scaffolds and Java operations to clarify lifecycle behavior. In real deployments, select dependency versions via the Spring Boot BOM, confirm exact class and interface signatures, and run integration tests against real MongoDB. Do not treat illustrative examples as substitutes for production security, schema migration, or audit compliance runbooks.

---

## 57. Summary

1. **Spring Data MongoDB auditing** automatically populates creation/modification timestamps and actor metadata when entities are saved along supported mapping paths.
2. Enable via **`@EnableMongoAuditing`** using `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, and `@LastModifiedBy`; `AuditorAware` is optional when only timestamps are needed.
3. **`AuditorAware<T>`** resolves the actor from a trusted identity context; batch, async, and reactive flows require explicit actor-propagation policies.
4. **`DateTimeProvider`** supplies the time source; `Instant` and UTC fit distributed systems best, with BSON Date offering millisecond precision.
5. **`modifyOnCreate = true`** by default populates `updatedAt`/`updatedBy` at creation; choose your policy deliberately.
6. Distinguishing **new vs. existing** entities via ID, `@Version`, or `Persistable` directly controls whether creation or modification auditing runs.
7. **`AuditingEntityCallback`** executes at **BeforeConvert**. Use `BeforeConvertCallback` to adjust persistent entity properties; `BeforeSaveCallback` runs after BSON conversion and must mutate the BSON `Document` to affect persisted fields.
8. **Query-based updates, bulk writes, the raw driver, and `mongosh`** bypass the entity-save auditing pipeline; set `updatedAt`/`updatedBy` explicitly per policy.
9. **`AfterSave` is not a transaction commit hook**, so never emit critical external events straight from callbacks; prefer an outbox pattern.
10. **Audit metadata is not an immutable audit log**: compliance requirements call for dedicated audit histories, access controls, retention, and transactional/outbox consistency.
11. Always write **integration tests** verifying stored BSON, actor identities, timestamps, version conflicts, update paths, and callback ordering.

**Operational Principle:** Reliable auditing requires knowing **which write paths invoke callbacks, where actors and timestamps originate, how entity newness is classified, and which updates intentionally bypass the framework**. Only by controlling all four will `createdAt`, `updatedAt`, `createdBy`, and `updatedBy` remain trustworthy reflections of system behavior.
