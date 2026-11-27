# Enabling Auditing with `@EnableElasticsearchAuditing`

Spring Data Elasticsearch supports auditing to automatically record who created a document, who last modified it, when it was created, and when it was last updated. When `@EnableElasticsearchAuditing` is enabled, Spring registers auditing infrastructure for entities persisted through Spring Data. The annotations `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, and `@LastModifiedDate` mark the properties to be populated during the entity save lifecycle.

Auditing gives applications consistent origin and timestamp metadata without manually assigning these four properties in every service. To capture the actor performing the operation, the application supplies an `AuditorAware<T>` bean. To control the time source, a `DateTimeProvider`—often paired with a `Clock` for easy testing—can be provided.

Auditing represents business metadata stored inside `_source`. It answers “who created?”, “who last modified?”, and “when?”, but does not automatically create a complete history of every change. If an immutable audit trail is needed, design a dedicated event log or history storage system.

## 1. What Problem Does Auditing Solve?

An entity often needs administrative metadata alongside business data:

- Who created the record.
- When it was created.
- Who last updated it.
- When it was last updated.

If every service assigns these fields manually, code becomes repetitive and inconsistent. One flow forgets to set `lastModifiedDate`, another uses a different timezone, or a batch job fails to record an actor—leaving auditing data unreliable.

Spring Data auditing moves metadata population into the entity persistence lifecycle. When an entity is saved via a repository or `ElasticsearchOperations`, the auditing infrastructure updates annotated properties before the entity is converted into a document to be written to Elasticsearch.

### Example Expected Output

A document after initial creation:

```json
{
  "id": "p-100",
  "name": "Wireless Mouse",
  "createdBy": "alice",
  "createdDate": "2026-11-13T09:00:00Z",
  "lastModifiedBy": "alice",
  "lastModifiedDate": "2026-11-13T09:00:00Z"
}
```

After user `bob` edits the product name:

```json
{
  "id": "p-100",
  "name": "Wireless Mouse Pro",
  "createdBy": "alice",
  "createdDate": "2026-11-13T09:00:00Z",
  "lastModifiedBy": "bob",
  "lastModifiedDate": "2026-11-13T10:30:00Z"
}
```

`createdBy` and `createdDate` reflect the initial creation; `lastModifiedBy` and `lastModifiedDate` reflect the latest modification.

## 2. The Four Auditing Annotations

Common auditing annotations belong to the `org.springframework.data.annotation` package:

| Annotation | Meaning | When Populated |
|---|---|---|
| `@CreatedBy` | Actor who created the entity | Upon initial creation |
| `@CreatedDate` | Timestamp when the entity was created | Upon initial creation |
| `@LastModifiedBy` | Actor who last modified the entity | Upon creation or update depending on configuration |
| `@LastModifiedDate` | Timestamp when the entity was last modified | Upon creation or update depending on configuration |

Entity example:

```java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    private String name;

    @CreatedBy
    @Field(type = FieldType.Keyword)
    private String createdBy;

    @CreatedDate
    @Field(type = FieldType.Date)
    private Instant createdDate;

    @LastModifiedBy
    @Field(type = FieldType.Keyword)
    private String lastModifiedBy;

    @LastModifiedDate
    @Field(type = FieldType.Date)
    private Instant lastModifiedDate;

    // Constructors, getters and setters
}
```

`@CreatedBy` and `@LastModifiedBy` typically match the return type of `AuditorAware<T>`. For instance, `AuditorAware<String>` pairs with `String` properties. Date/time properties should use temporal types supported by Spring Data; `Instant` is convenient for storing UTC timestamps.

Auditing annotations do not automatically turn fields into special Elasticsearch mappings. They govern value population in Spring Data. Field mappings still need to match how the application queries or displays the metadata.

## 3. Enabling Auditing with `@EnableElasticsearchAuditing`

Place the annotation on a component-scanned Spring configuration class:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.config.EnableElasticsearchAuditing;

@Configuration
@EnableElasticsearchAuditing
public class ElasticsearchAuditingConfiguration {
}
```

This annotation registers Spring Data Elasticsearch's auditing infrastructure, including the callback needed to apply auditing metadata during the entity lifecycle.

If the entity only uses `@CreatedDate` and `@LastModifiedDate`, Spring can supply the current timestamp through its default date-time provider. If `@CreatedBy` or `@LastModifiedBy` needs to be populated, the application must provide an `AuditorAware` to resolve the current actor.

### Where to Place Configuration

The configuration class must be discovered by the Spring Boot/Spring application. For example, if the main class is in package `com.example`, the configuration can live in a subpackage to be picked up automatically by component scanning:

```text
com.example
  Application.java
  config
    ElasticsearchAuditingConfiguration.java
  product
    ProductDocument.java
```

If the configuration sits outside component scan scope, the annotation will not be applied even though the file compiles cleanly.

## 4. What Is `AuditorAware<T>`?

`AuditorAware<T>` is a Spring Data abstraction that returns the current actor. It resides in `org.springframework.data.domain` and exposes `getCurrentAuditor()` returning `Optional<T>`.

Simple example using a fixed actor for a test application:

```java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;

@Configuration
public class ElasticsearchAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> Optional.of("system");
    }
}
```

This bean illustrates the mechanism, but it is unsuitable for multi-user systems because every document gets recorded as `system`. In real applications, the actor should come from the authenticated context or be passed via a controlled execution context.

### Linking the Bean with `auditorAwareRef`

If only one `AuditorAware` bean exists, Spring can resolve it automatically through its configuration mechanism. When multiple auditor providers exist, specify the bean name explicitly:

```java
@Configuration
@EnableElasticsearchAuditing(auditorAwareRef = "auditorProvider")
public class ElasticsearchAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> Optional.of("system");
    }
}
```

`auditorAwareRef` is the bean name, not the class name or entity field name. The provider's generic type must be compatible with `@CreatedBy` and `@LastModifiedBy` properties.

## 5. Retrieving the Actor from Spring Security

In applications using Spring Security, the actor is typically the username or subject of the current `Authentication`.

```java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Configuration
public class ElasticsearchAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> {
            Authentication authentication = SecurityContextHolder.getContext()
                .getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()
                    || authentication instanceof AnonymousAuthenticationToken) {
                return Optional.empty();
            }

            return Optional.of(authentication.getName());
        };
    }
}
```

When there is no authenticated user, the provider returns `Optional.empty()`. Auditing then has no actor to assign. If the application needs to record background tasks, a system actor can be supplied through a separate execution context instead of assuming every request has an `Authentication`.

### Why Exclude `AnonymousAuthenticationToken`?

In some Spring Security setups, unauthenticated requests still have an authentication object representing an anonymous user. Checking only `authentication != null` and `isAuthenticated()` could cause an anonymous actor to be recorded as a real user. Checking the token type or an explicit actor rule prevents this.

### Do Not Store the Entire Authentication

Auditing typically only needs a stable identifier such as username, user ID, or service principal. Do not store the `Authentication` object, credentials, access tokens, or full claims in auditing fields.

## 6. Handling Background Tasks and System Actors

A scheduler, message consumer, or batch worker can run outside an HTTP request. In that case, `SecurityContextHolder` may not hold a user actor.

You can define a system actor explicitly at the application layer. One approach is a dedicated context for background tasks:

```java
public final class AuditActorContext {

    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    private AuditActorContext() {
    }

    public static void set(String actor) {
        CURRENT.set(actor);
    }

    public static Optional<String> get() {
        return Optional.ofNullable(CURRENT.get());
    }

    public static void clear() {
        CURRENT.remove();
    }
}
```

`AuditorAware` can read this context or combine it with `SecurityContext` based on the application's precedence rules. When using `ThreadLocal`, always clear it in `finally` so the previous task's actor does not leak into subsequent tasks on a thread pool:

```java
try {
    AuditActorContext.set("nightly-cleanup");
    cleanupService.run();
} finally {
    AuditActorContext.clear();
}
```

With `@Async`, executors, or message listeners, do not assume the security context propagates across threads automatically. To preserve the initiating user's identity, pass the actor explicitly in message/job metadata or configure appropriate context propagation.

## 7. Using `DateTimeProvider` to Control Time

By default, auditing uses the current wall-clock time. To control the time source, register a `DateTimeProvider` and specify it via `dateTimeProviderRef`.

Example using `Clock`:

```java
import java.time.Clock;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;

@Configuration
public class TimeConfiguration {

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditDateTimeProvider(Clock auditClock) {
        return () -> Optional.of(auditClock.instant());
    }
}
```

Combined with the auditing configuration:

```java
@Configuration
@EnableElasticsearchAuditing(
    auditorAwareRef = "auditorProvider",
    dateTimeProviderRef = "auditDateTimeProvider"
)
public class ElasticsearchAuditingConfiguration {
    // AuditorAware bean
}
```

`DateTimeProvider` returns `Optional<TemporalAccessor>`. `Instant` is an appropriate temporal type representing an absolute point in time. When a display timezone is needed, convert at the API/UI layer instead of storing local times without timezone info.

### Why Use `Clock`?

- Production can use `Clock.systemUTC()`.
- Unit/integration tests can use `Clock.fixed(...)`.
- Services avoid calling `Instant.now()` directly in many places.
- `createdDate` and `lastModifiedDate` values become deterministic and easy to assert.

## 8. Complete Auditing Configuration

Example configuration combining actor provider and date-time provider:

```java
import java.time.Clock;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.elasticsearch.config.EnableElasticsearchAuditing;

@Configuration
@EnableElasticsearchAuditing(
    auditorAwareRef = "auditorProvider",
    dateTimeProviderRef = "auditDateTimeProvider"
)
public class ElasticsearchAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> Optional.of("system");
    }

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditDateTimeProvider(Clock auditClock) {
        return () -> Optional.of(auditClock.instant());
    }
}
```

In a real application, replace the fixed actor with a provider reading the current user or service principal. Separate the time and actor configuration beans if you want to test or swap them independently.

## 9. `modifyOnCreate` and `setDates`

`@EnableElasticsearchAuditing` provides options controlling auditing behavior in supported Spring Data versions:

- `setDates`: enables/disables assigning created and modified date properties.
- `modifyOnCreate`: controls whether modification metadata (`@LastModifiedBy`, `@LastModifiedDate`) is populated during initial creation.

By default, auditing typically assigns date fields and `modifyOnCreate` is `true`, so `lastModifiedDate` may equal `createdDate` on initial creation.

Example disabling modification metadata on creation:

```java
@Configuration
@EnableElasticsearchAuditing(
    auditorAwareRef = "auditorProvider",
    modifyOnCreate = false
)
public class ElasticsearchAuditingConfiguration {
}
```

Then `@CreatedBy`/`@CreatedDate` still capture creation, while `@LastModified...` fields are only populated when the entity is modified according to auditing semantics.

If `setDates = false` is set, date auditing is disabled. Do not use this option if the entity relies on `@CreatedDate` or `@LastModifiedDate`.

Attribute names and scope can vary across Spring Data generations; check the Javadoc for your exact version before relying on configuration options.

## 10. Callback Lifecycle When Saving an Entity

Auditing does not execute as a standalone statement; it is applied within Spring Data's entity lifecycle. For saves via a repository or `ElasticsearchOperations`, Spring Data can invoke an entity callback before converting the entity into write data.

```text
Controller / Service
        |
        v
Repository.save(entity)
or ElasticsearchOperations.save(entity)
        |
        v
Auditing callback
        |
        +--> Read AuditorAware
        +--> Read DateTimeProvider
        +--> Assign @CreatedBy / @CreatedDate on create
        +--> Assign @LastModifiedBy / @LastModifiedDate per configuration
        |
        v
Entity conversion / mapping
        |
        v
Elasticsearch Index API
        |
        v
Auditing fields stored in _source
```

Auditing callbacks depend on the write path traversing Spring Data's mapping/callback infrastructure. If the application calls the Elasticsearch Java API Client directly or sends raw REST requests, Spring Data does not run callbacks for those requests automatically.

### Callbacks Are Not Database Triggers

Auditing executes at the Spring Data application layer. Another process writing directly to Elasticsearch will not automatically receive these auditing values. If multiple systems write to the same index, align metadata conventions across all writers.

## 11. `save()` and `saveAll()`

Example using a repository:

```java
ProductDocument product = new ProductDocument();
product.setId("p-100");
product.setName("Wireless Mouse");

productRepository.save(product);
```

When auditing is enabled and callbacks apply, `createdBy`, `createdDate`, `lastModifiedBy`, and `lastModifiedDate` are populated per configuration before the document is saved.

Saving multiple entities:

```java
productRepository.saveAll(products);
```

Verify whether your Spring Data version's `saveAll` path runs through entity callbacks. Low-level bulk APIs accepting `IndexQuery`/raw requests do not necessarily share the same behavior as saving individual entities. If auditing metadata is mandatory, inspect the chosen write path carefully and consider populating metadata explicitly before building bulk actions.

## 12. Partial Updates and APIs That Bypass Entity Callbacks

An important caveat: not every update operation passes through the entity auditing callback.

Example Update API sending only part of a document:

```java
Document partial = Document.create();
partial.put("name", "Wireless Mouse Pro");

UpdateQuery update = UpdateQuery.builder("p-100")
    .withDocument(partial)
    .build();

operations.update(update, IndexCoordinates.of("products"));
```

This update path works with a partial document and does not necessarily load a full entity and execute the auditing callback like `save(entity)`. Therefore, do not assume `lastModifiedDate` and `lastModifiedBy` are updated automatically across all partial updates, update-by-query, scripted updates, or bulk actions.

If auditing is required for partial updates:

- Explicitly set `lastModifiedBy` and `lastModifiedDate` in the partial document.
- Or read the entity, modify its properties, and save it back through a callback-enabled Spring Data path, if cost and concurrency allow.
- Or encapsulate updates in a shared service so all write paths enforce auditing rules.

Example:

```java
Document partial = Document.create();
partial.put("name", "Wireless Mouse Pro");
partial.put("lastModifiedBy", currentActor);
partial.put("lastModifiedDate", clock.instant());
```

Ensure field names and data types match the mapping. Avoid mixing automatic callbacks and manual assignment inconsistently, as values can overwrite each other or diverge.

## 13. Auditing and `@Version` Are Two Different Things

Auditing answers who and when; optimistic locking controls concurrent updates.

| Mechanism | Purpose | Example |
|---|---|---|
| `@CreatedBy` | Who created the document | `alice` |
| `@CreatedDate` | When it was created | `2026-11-13T09:00:00Z` |
| `@LastModifiedBy` | Who last modified it | `bob` |
| `@LastModifiedDate` | When it was last modified | `2026-11-13T10:30:00Z` |
| `@Version` | Control version on updates | Version 7 → 8 |
| `_seq_no` + `_primary_term` | Control operations based on read state | Conditional update token |

An entity can use both auditing and optimistic concurrency. Enabling `@EnableElasticsearchAuditing` does not enable `@Version`, does not add `if_seq_no`/`if_primary_term`, and does not prevent lost updates.

## 14. Mapping Auditing Fields in Elasticsearch

Auditing fields are normally stored in `_source` like regular fields. Choose mapping types based on usage:

| Field | Typical Suitable Mapping | Purpose |
|---|---|---|
| `createdBy` | `keyword` | Filter or group by creating actor |
| `lastModifiedBy` | `keyword` | Filter by last modifying actor |
| `createdDate` | `date` | Filter by creation time, sort, and range queries |
| `lastModifiedDate` | `date` | Filter by last modification time |

Mapping example:

```json
{
  "properties": {
    "createdBy": { "type": "keyword" },
    "createdDate": { "type": "date" },
    "lastModifiedBy": { "type": "keyword" },
    "lastModifiedDate": { "type": "date" }
  }
}
```

If using different field names in Java and Elasticsearch, declare the mapping name explicitly with `@Field(name = "...")` according to entity conventions.

### Storing UTC Timestamps

`Instant` represents a UTC instant. When serialized, values typically take ISO-8601 format ending in `Z`. If the UI needs local time, convert at the presentation layer. Avoid storing `LocalDateTime` if the system must unambiguously identify a global point in time without an accompanying timezone.

## 15. Querying Auditing Metadata

Because auditing fields reside in `_source` with proper mappings, standard Query DSL applies.

Find documents created by a specific actor:

```http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "term": {
      "createdBy": "alice"
    }
  }
}
```

Find documents modified within a time range:

```json
{
  "query": {
    "range": {
      "lastModifiedDate": {
        "gte": "2026-11-01T00:00:00Z",
        "lt": "2026-12-01T00:00:00Z"
      }
    }
  }
}
```

Sort by most recent modification time:

```json
{
  "sort": [
    {
      "lastModifiedDate": {
        "order": "desc"
      }
    }
  ]
}
```

For large audit reports, combine with aggregations or batch exports. Keep in mind that `lastModifiedBy` stores only the latest actor, not a list of every actor who ever modified the document.

## 16. Testing Auditing with Deterministic Actors

Unit and integration tests should control both the actor and time for stable assertions.

Example using `Clock.fixed`:

```java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-11-13T09:00:00Z"),
    ZoneOffset.UTC
);
```

In test configuration, provide an `AuditorAware` returning a fixed actor and a `DateTimeProvider` using the fixed clock. After saving the entity via a repository or `ElasticsearchOperations`, assert:

```java
assertThat(saved.getCreatedBy()).isEqualTo("test-user");
assertThat(saved.getLastModifiedBy()).isEqualTo("test-user");
assertThat(saved.getCreatedDate()).isEqualTo(fixedInstant);
assertThat(saved.getLastModifiedDate()).isEqualTo(fixedInstant);
```

When verifying data via `_search`, ensure a refresh has occurred. Use an appropriate refresh policy in tests or call `IndexOperations.refresh()` after loading fixtures. Do not rely on fixed `Thread.sleep()` delays to wait for refresh.

### Testing Updates

A test can:

1. Save the entity initially with actor `alice` and timestamp T1.
2. Read the entity back.
3. Switch the actor to `bob` and clock to T2.
4. Save the entity a second time through a callback-enabled path.
5. Assert `createdBy`/`createdDate` retain T1/`alice`, while `lastModifiedBy`/`lastModifiedDate` become `bob`/T2.

If testing partial updates, verify separately whether that API path executes callbacks; if not, assert that the service explicitly assigned modification metadata.

## 17. Testing `AuditorAware` with Spring Security

In secured applications, test these cases:

- Valid authentication returns the expected actor.
- Missing authentication returns `Optional.empty()` or a system actor per policy.
- Anonymous authentication is not recorded as an authenticated user.
- Background tasks have an explicit system actor.
- Context is cleared after processing in thread pools.
- Actor names or user IDs do not contain credentials/tokens.

If using `@WithMockUser` in Spring Security Test, verify that the auditor provider reads the principal/name configured by the test. If the application uses a custom principal, map it to a stable actor identifier rather than relying on the principal's `toString()`.

## 18. Limitations of Auditing

Auditing is very helpful for operational metadata, but it is not a full audit trail system.

### Stores Only the Latest State

`@LastModifiedBy` and `@LastModifiedDate` retain only the actor and timestamp of the most recent edit. When the document is updated again, previous values are replaced.

If every change must be tracked, store separate event/audit records, such as:

```json
{
  "entityId": "p-100",
  "action": "PRICE_CHANGED",
  "actor": "alice",
  "occurredAt": "2026-11-13T09:30:00Z",
  "before": { "price": 100 },
  "after": { "price": 120 }
}
```

### Does Not Automatically Cover All Writers

A writer using raw REST, the Elasticsearch Java API Client directly, an ingest pipeline, or another application does not run Spring Data callbacks. Those writers may leave auditing fields unpopulated.

### Does Not Guarantee Immutability

Auditing fields reside inside the document and can be overwritten by anyone with sufficient write permissions. They are neither cryptographic proof nor tamper-evident logs.

### Does Not Authenticate the Actor

`AuditorAware` simply returns whatever value the application provides. If the provider extracts the wrong actor or context leaks across requests, auditing records the wrong actor. Test and safeguard context propagation carefully.

## 19. Designing an Audit Trail When Full History Is Required

If business requirements demand complete traceability, combine entity auditing metadata with an append-only event index:

```text
Business command
      |
      v
Check permissions and state
      |
      +----> Update current document
      |
      +----> Write separate audit event
                    |
                    v
             entityId / actor
             action / timestamp
             before / after or diff
```

Each audit event should have its own ID, timestamp, actor, action, entity ID, and required change details. If the two writes must stay consistent, consider a transactional outbox or event-delivery mechanism matching your architecture; do not assume two independent Elasticsearch requests form an atomic transaction.

An audit index requires restricted write permissions, retention policies, backups, and deletion controls. Under strict compliance rules, evaluate immutable storage or dedicated audit systems.

## 20. Auditing in Bulk Ingestion

When loading data in bulk, the actor may be the user initiating the import or the service account executing it. Distinguish the two concepts when business rules require:

- `createdBy`: actor considered the creator of the record per business rules.
- `lastModifiedBy`: actor/service performing the current write.

For example, an import executed by `migration-service` on behalf of `admin-42`. The application must decide which actor auditing records. You can store extra business fields like `requestedBy` or `importJobId` if you need both the requester and the executing service.

With low-level bulk APIs, populate auditing metadata before constructing `IndexQuery`/bulk actions, or use a write path confirmed to run callbacks. Do not assume raw bulk requests invoke `AuditorAware` automatically.

## 21. Common Configuration Mistakes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `@CreatedDate` is always null | Auditing not enabled, config not scanned, or callback did not run | Check `@EnableElasticsearchAuditing` and persistence path |
| `@CreatedBy` is null | Missing `AuditorAware` or provider returns empty | Register bean and check `SecurityContext` |
| Actor is always `system` | Provider returns a hardcoded actor | Read actor from request/job context |
| `lastModifiedDate` does not change | Partial update or raw client bypasses callback | Assign explicitly or save via entity callback path |
| `createdDate` changes on update | Application logic overwrites field or callback/mapping misconfigured | Do not manually reset created metadata; check callback and update path |
| Dates have timezone offset bugs | Using local time without timezone or inconsistent serialization | Use `Instant`/UTC and convert at the display layer |
| Document not found right after save | Not yet refreshed | Use `WAIT_UNTIL` or refresh index when needed |
| Wrong actor in async worker | Security context not propagated or `ThreadLocal` not cleared | Pass actor explicitly and manage context lifecycle |
| Bulk documents missing audit fields | Low-level bulk API does not run entity callbacks | Populate metadata before creating bulk actions |

## 22. Process for Enabling Auditing in an Application

A clear implementation sequence:

1. Determine whether the recorded actor is a username, user ID, or service principal.
2. Add the four auditing fields to the entity with appropriate types.
3. Choose `keyword` mapping for actors and `date` mapping for timestamps if querying/sorting is needed.
4. Create a configuration class annotated with `@EnableElasticsearchAuditing`.
5. Register `AuditorAware<T>` if `@CreatedBy`/`@LastModifiedBy` are needed.
6. Specify `auditorAwareRef` if multiple providers exist or explicit configuration is preferred.
7. Configure `DateTimeProvider`/`Clock` if time control is required.
8. Verify the configuration class is within component scan scope.
9. Verify repository/`ElasticsearchOperations` save paths trigger callbacks.
10. Address partial updates, update-by-query, raw clients, and bulk actions separately.
11. Test actors, timestamps, creation, updates, and background contexts.
12. Decide whether immutable audit events are needed beyond the four metadata fields.

## 23. Complete Example: Entity, Configuration, and Service

Entity:

```java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "articles")
public class ArticleDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String title;

    @CreatedBy
    @Field(type = FieldType.Keyword)
    private String createdBy;

    @CreatedDate
    @Field(type = FieldType.Date)
    private Instant createdDate;

    @LastModifiedBy
    @Field(type = FieldType.Keyword)
    private String lastModifiedBy;

    @LastModifiedDate
    @Field(type = FieldType.Date)
    private Instant lastModifiedDate;

    // Constructors, getters and setters
}
```

Configuration:

```java
import java.time.Clock;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.elasticsearch.config.EnableElasticsearchAuditing;

@Configuration
@EnableElasticsearchAuditing(
    auditorAwareRef = "auditorProvider",
    dateTimeProviderRef = "auditDateTimeProvider"
)
public class ElasticsearchAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> Optional.of("article-service");
    }

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditDateTimeProvider(Clock auditClock) {
        return () -> Optional.of(auditClock.instant());
    }
}
```

Service:

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;
import org.springframework.stereotype.Service;

@Service
public class ArticleService {

    private final ArticleRepository repository;

    public ArticleService(ArticleRepository repository) {
        this.repository = repository;
    }

    public ArticleDocument create(ArticleDocument article) {
        return repository.save(article);
    }

    public ArticleDocument updateTitle(String id, String title) {
        ArticleDocument article = repository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Article not found: " + id));

        article.setTitle(title);
        return repository.save(article);
    }
}

interface ArticleRepository
        extends ElasticsearchRepository<ArticleDocument, String> {
}
```

This example uses a fixed service actor for readability. In user-facing systems, replace `AuditorAware` with a provider reading the actor from the security context or managed execution context. In `updateTitle`, the entity is read, modified, and saved via the repository so the auditing callback can update modification metadata.

## 24. Conclusion

`@EnableElasticsearchAuditing` enables Spring Data Elasticsearch's auditing infrastructure. Entities use `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, and `@LastModifiedDate` to mark metadata to be recorded. `AuditorAware<T>` provides the current actor; `DateTimeProvider` can control the time source. You can configure providers via `auditorAwareRef` and `dateTimeProviderRef`, and tune modification-date behavior on creation via `modifyOnCreate` in supported versions.

Auditing is applied via entity callbacks when data flows through Spring Data's persistence path. Partial updates, update-by-query, raw REST/Java clients, and low-level bulk actions may bypass callbacks, so verify each write path and assign metadata explicitly when needed. Use `Instant`/UTC, manage actors for background tasks, test with a fixed `Clock`, and do not confuse auditing metadata with optimistic locking. The four auditing fields show who created and who last modified a document; if a full change history or tamper-evident record is needed, add a dedicated audit event/index.

## References

- [Spring Data Elasticsearch – Auditing](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/auditing.html)
- [Spring Data Commons – Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html)
- [Spring Data Elasticsearch – `@EnableElasticsearchAuditing` API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/config/EnableElasticsearchAuditing.html)
- [Spring Data Commons – `AuditorAware` API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AuditorAware.html)
- [Spring Data Commons – `DateTimeProvider` API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/auditing/DateTimeProvider.html)
- [Spring Data Elasticsearch – Entity callbacks](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/entity-callbacks.html)
