# AuditorAware, DateTimeProvider, and Actor Context

Auditing lets documents record who created them, who last modified them, and when those operations occurred. In Spring Data Elasticsearch, this mechanism integrates with entity callbacks: when an entity is saved through an auditing-enabled Spring Data path, annotated fields are automatically populated before the document is written.

Two components determine auditing metadata:

- **`AuditorAware<T>`** supplies the identity of the user or process performing the operation.
- **`DateTimeProvider`** supplies the current timestamp to populate created and modified date fields.

For auditing to be meaningful in a real application, you must design the actor context explicitly: user requests, scheduled jobs, batch imports, message consumers, or administrative actions. Not every Elasticsearch write has a logged-in user, and you should not fabricate a fake user merely to ensure audit fields are always non-null.

## 1. What Information Does Auditing Store?

A business document typically needs four audit fields:

| Annotation | Meaning | Example |
|---|---|---|
| `@CreatedBy` | Identity that created the document | `user-1024` |
| `@LastModifiedBy` | Identity that last modified the document | `admin-17` |
| `@CreatedDate` | Creation timestamp | `2026-11-13T09:30:00Z` |
| `@LastModifiedDate` | Last modification timestamp | `2026-11-13T10:15:00Z` |

Example document after creation:

~~~json
{
  "id": "DOC-1001",
  "title": "Inventory policy",
  "createdBy": "user-1024",
  "createdDate": "2026-11-13T09:30:00Z",
  "lastModifiedBy": "user-1024",
  "lastModifiedDate": "2026-11-13T09:30:00Z"
}
~~~

After an administrator updates the document, the fields might become:

~~~json
{
  "id": "DOC-1001",
  "title": "Inventory policy v2",
  "createdBy": "user-1024",
  "createdDate": "2026-11-13T09:30:00Z",
  "lastModifiedBy": "admin-17",
  "lastModifiedDate": "2026-11-13T10:15:00Z"
}
~~~

Creation fields are preserved; last-modified fields reflect the new operation. This supports basic history tracking, though it does not replace an immutable audit log if the system needs to retain every single change.

## 2. Enabling Auditing for Spring Data Elasticsearch

Spring Data Elasticsearch provides the `@EnableElasticsearchAuditing` annotation to activate auditing.

Configuration example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.config.EnableElasticsearchAuditing;

@Configuration
@EnableElasticsearchAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "auditingDateTimeProvider",
        modifyOnCreate = true
)
public class ElasticsearchAuditingConfiguration {
}
~~~

Key attributes:

- `auditorAwareRef`: bean name providing `AuditorAware<?>`.
- `dateTimeProviderRef`: bean name providing `DateTimeProvider`.
- `modifyOnCreate`: specifies whether modification metadata is populated when creating an entity. Defaults to `true` in standard auditing configurations.
- `setDates`: enables/disables populating created and modified date fields; enabled by default.

If no explicit bean names are specified, Spring Data can look up matching beans using default rules. Declaring bean names explicitly via the `ref` attributes prevents ambiguity when the application defines multiple auditing beans.

Configure auditing only once in the application context. Avoid repeating `@EnableElasticsearchAuditing` across multiple configuration classes, as that can produce ambiguous configuration.

## 3. Declaring Audit Fields on an Entity

Audit annotations live in `org.springframework.data.annotation`, not in an Elasticsearch-specific annotation package.

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;

import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "documents")
public class DocumentRecord {

    @Id
    private String id;

    private String title;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String lastModifiedBy;

    @CreatedDate
    @Field(type = FieldType.Date)
    private Instant createdDate;

    @LastModifiedDate
    @Field(type = FieldType.Date)
    private Instant lastModifiedDate;

    // Constructors, getters and setters
}
~~~

Explanation:

- `@CreatedBy` and `@LastModifiedBy` receive values from `AuditorAware`.
- `@CreatedDate` and `@LastModifiedDate` receive values from `DateTimeProvider`.
- `Instant` represents an absolute point in time and fits audit metadata well.
- `@Field(type = FieldType.Date)` declares the Elasticsearch mapping for date fields.

Use a consistent identity format for actor fields, such as a `String` or `UUID` user ID. Avoid storing a username in one flow, an email in another, and a display name in a third; querying and reconciliation later become much harder.

If the system needs both user ID and display name, store them as separate fields or keep the stable ID in the audit field and resolve display names from the identity system.

## 4. AuditorAware<T> Supplies the Actor Identity

`AuditorAware<T>` is a Spring Data interface with the method:

~~~java
Optional<T> getCurrentAuditor();
~~~

Spring Data calls this method whenever it needs to populate `@CreatedBy` or `@LastModifiedBy`. Type `T` must be compatible with the audit field types on the entity.

Example application storing user IDs as `String`:

~~~java
import java.util.Optional;

import org.springframework.data.domain.AuditorAware;
import org.springframework.stereotype.Component;

@Component("auditorAware")
public class CurrentAuditorAware implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        return Optional.of("user-1024");
    }
}
~~~

This is strictly an illustrative example. In a real application, do not hard-code a user ID, or every operation will be attributed to the same person. The auditor must come from the security context or a trusted execution context.

When no auditor exists, you can return `Optional.empty()`. Spring Data then has no value to populate the actor field. Decide clearly whether actor fields may be null or whether the application must supply an actor for every write flow.

## 5. Retrieving the Auditor from Spring Security

In a servlet-based Spring Security application, the authenticated identity is typically held in `SecurityContextHolder`.

Example:

~~~java
import java.util.Optional;

import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component("auditorAware")
public class SecurityAuditorAware implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return Optional.empty();
        }

        return Optional.ofNullable(authentication.getName());
    }
}
~~~

Steps:

1. Read the current `Authentication`.
2. Verify authentication exists and is authenticated.
3. Exclude `AnonymousAuthenticationToken`; an anonymous token can report `isAuthenticated() = true`.
4. Read the principal name via `getName()`.
5. Return `Optional.empty()` if no suitable user is present.

`authentication.getName()` typically returns the username or principal identifier per your authentication configuration. If auditing requires an immutable user ID, extract the ID from a custom principal rather than defaulting to username.

Example with a custom application principal:

~~~java
public interface ApplicationPrincipal {
    String userId();
}
~~~

You can check the principal type:

~~~java
Object principal = authentication.getPrincipal();

if (principal instanceof ApplicationPrincipal applicationPrincipal) {
    return Optional.of(applicationPrincipal.userId());
}

return Optional.ofNullable(authentication.getName());
~~~

The interface name and ID extraction logic must match your application's actual principal. Do not cast the principal recklessly, because some authentication mechanisms return a `String`, `UserDetails`, or another custom type.

## 6. Handling Requests Without a Logged-In User

Not all operations originate from an authenticated HTTP request:

- Scheduled jobs running on a timer.
- Batch data imports.
- Message consumers processing events.
- Data synchronization from external systems.
- Maintenance or migration processes.
- Administrative operations invoked by another service.

There are two common policies:

| Policy | When No Authentication Exists | When Appropriate |
|---|---|---|
| No auditor | Return `Optional.empty()` | Actor fields may be omitted or system flows do not require an actor |
| System actor | Return an ID like `system:nightly-import` | Need clear traceability of which system process wrote the document |

When using a system actor, identify the actor by task or service rather than using a single `"system"` string for everything when distinguishing change sources matters.

Examples:

- `system:nightly-import`
- `system:inventory-reconciliation`
- `service:catalog-sync`

Do not use `anonymous` to represent a system job. Anonymous means an unidentified user, whereas a system actor is a process with a clear business identity.

### Do Not Take the Actor from Arbitrary Client Data

Do not allow requests to supply `createdBy` or `lastModifiedBy` and trust those values directly. A user could spoof someone else's ID.

The auditor must originate from an authenticated security context or a server-controlled system context. When a service writes on behalf of a user, decide explicitly whether the actor is the user, the executing service, or both; do not conflate identities.

## 7. DateTimeProvider Controls the Auditing Timestamp

`DateTimeProvider` belongs to `org.springframework.data.auditing`. This interface provides the current time as `Optional<TemporalAccessor>`.

~~~java
import java.time.Instant;
import java.util.Optional;

import org.springframework.data.auditing.DateTimeProvider;

public class UtcDateTimeProvider implements DateTimeProvider {

    @Override
    public Optional<TemporalAccessor> getNow() {
        return Optional.of(Instant.now());
    }
}
~~~

If implementing it directly, import `java.time.temporal.TemporalAccessor`. In practice, inject a `Clock` to control timezones and simplify testing.

Bean configuration example:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;

@Configuration
public class AuditTimeConfiguration {

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditingDateTimeProvider(Clock auditingClock) {
        return () -> Optional.of(Instant.now(auditingClock));
    }
}
~~~

Here:

- `Clock.systemUTC()` supplies a UTC clock.
- `Instant.now(clock)` obtains the instant from the injected clock.
- `DateTimeProvider` returns a `TemporalAccessor` for the auditing handler to use.

Pair this bean with `dateTimeProviderRef = "auditingDateTimeProvider"` in `@EnableElasticsearchAuditing`.

## 8. Why Inject Clock Instead of Calling Instant.now() Directly?

Calling `Instant.now()` directly in code ties timestamps to the system wall clock. Tests then depend on real execution time, making exact assertions on created or modified timestamps fragile.

When `Clock` is injected, you can swap in a fixed clock:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-13T09:30:00Z"),
        ZoneOffset.UTC
);

Instant now = Instant.now(fixedClock);
~~~

The result is always the specified instant. This helps when testing:

- Whether the creation timestamp matches the expected instant.
- Whether the modified timestamp updates on subsequent saves.
- Whether two operations preserve the expected chronological order.
- Whether UTC storage converts consistently.

In integration tests, you can supply a controllable clock backed by an `AtomicReference<Instant>`; each test updates the reference before saving to verify created and modified dates.

## 9. Choosing a Date/Time Data Type

Common Java types:

| Type | Meaning | Audit Recommendation |
|---|---|---|
| `Instant` | Absolute point on the UTC timeline | Preferred choice for created/modified timestamps |
| `OffsetDateTime` | Date and time with UTC offset | Use when preserving the input offset is needed |
| `LocalDateTime` | Date and time without timezone | Requires an explicit timezone convention |
| `java.util.Date` | Legacy timestamp type | Acceptable in legacy systems |
| `Long` | Epoch value | Use only when the data contract specifies the unit |

For audit metadata, `Instant` is usually the easiest type to reconcile across multiple services and timezones. If `LocalDateTime` is stored, two services in different timezones can interpret the same value as different moments.

Elasticsearch's `date` field type typically has millisecond resolution. If business requirements demand nanosecond precision, consider `date_nanos` and check mapping/conversion support in your Spring Data version. Do not assume that because Java `Instant` has nanosecond precision, a `date` index field retains that precision.

## 10. Rules on Creation vs. Update

When auditing is enabled, annotations define each field's role:

- `@CreatedBy`: identity at creation.
- `@CreatedDate`: timestamp at creation.
- `@LastModifiedBy`: identity of latest modifier.
- `@LastModifiedDate`: timestamp of latest modification.

With `modifyOnCreate = true`, modification fields are also populated when the entity is created. Thus, a new document can have equal `createdDate` and `lastModifiedDate`, as well as equal `createdBy` and `lastModifiedBy`.

With `modifyOnCreate = false`, the auditing handler skips populating modification fields on creation per that policy. Choose the setting based on data semantics and how your application APIs consume those fields.

Example:

| Operation | `createdBy` | `createdDate` | `lastModifiedBy` | `lastModifiedDate` |
|---|---|---|---|---|
| Created by user A | user A | timestamp T1 | user A if `modifyOnCreate` enabled | T1 |
| Updated by user B | user A | stays T1 | user B | T2 |
| Updated by system job | user A | stays T1 | system actor or empty per policy | T3 |

Do not manually update `createdBy` or `createdDate` in normal application logic. They represent initial creation metadata and should remain unchanged once the document has been created.

## 11. Entity Callbacks Are the Auditing Execution Mechanism

Spring Data Elasticsearch integrates auditing through entity callbacks. The auditing callback applies during entity-to-document conversion when using callback-enabled Spring Data APIs.

High-level flow:

~~~mermaid
flowchart TD
    A["Repository.save(entity) or operations.save(entity)"] --> B["Spring Data receives entity"]
    B --> C["Auditing entity callback"]
    C --> D["AuditorAware resolves actor"]
    C --> E["DateTimeProvider resolves timestamp"]
    D --> F["Populate CreatedBy / LastModifiedBy"]
    E --> G["Populate CreatedDate / LastModifiedDate"]
    F --> H["Entity converted into Elasticsearch document"]
    G --> H
    H --> I["Index API writes document"]
~~~

Because auditing relies on Spring Data callbacks, distinguish between write paths:

| Write Path | Should You Expect Auditing to Run Automatically? |
|---|---|
| Repository `save(entity)` | Yes, when auditing is enabled and entity metadata is recognized |
| `ElasticsearchOperations.save(entity)` | Yes, via Spring Data callbacks |
| Sending requests directly via Java API Client | No; bypasses Spring Data entity callbacks |
| Sending direct REST requests | No |
| Scripted updates via `UpdateQuery` | Do not assume entity callbacks populate audit fields |
| Low-level Bulk API | Do not assume callbacks run per object |

For partial updates or scripted updates, if `lastModifiedBy` and `lastModifiedDate` must change, pass those values into the update explicitly or use an entity write path with appropriate callback support.

For bulk ingestion, verify whether the exact bulk API used in your Spring Data version triggers entity callbacks. If the bulk path bypasses callbacks, populate metadata before constructing the bulk request. Do not infer from enabling auditing that every write request is automatically audited.

## 12. Actor Context in Synchronous Requests

For synchronous HTTP requests, `SecurityContext` is usually established during authentication and readable within the same handling thread.

Typical flow:

~~~text
HTTP request
   |
   v
Authentication filter
   |
   v
SecurityContextHolder
   |
   v
Controller / Service
   |
   v
Repository.save(entity)
   |
   v
AuditorAware.getCurrentAuditor()
   |
   v
createdBy / lastModifiedBy
~~~

Do not pass user identity in a request body field and use that field as the auditor. The auditor must come from an authenticated security context or equivalent server-side mechanism.

When a service acts on behalf of a user, distinguish:

- **Actor**: user who initiated the request.
- **Executor**: service or worker that actually performs the operation.
- **Tenant**: data scope to which the operation belongs.

The four default auditing fields capture only actor and timestamp. If both actor and executor are needed, add a separate business field like `executedBy` or record that detail in an audit event.

## 13. Context in @Async, Executors, and Message Consumers

Security context is typically thread-bound. When work moves to another thread, do not assume `SecurityContextHolder` automatically carries the same authentication.

Example:

~~~text
Request thread:
  user-1024
      |
      +---- submit task
                 |
                 v
             Worker thread:
             no default SecurityContext
~~~

Cases to handle:

- `@Async` running on a thread pool.
- Scheduled jobs.
- Kafka/RabbitMQ listeners.
- Batch workers.
- Custom executors.
- Work pushed onto a queue and processed in another process.

Design options:

1. Use Spring Security's executor context propagation when preserving the request context is genuinely needed.
2. Pass the actor ID explicitly inside a server-created, authenticated command/message.
3. Use a system actor for jobs running independently of users.
4. Introduce an actor context abstraction so services do not couple directly to `SecurityContextHolder`.

Do not retain a request security context inside a long-running job after the request ends if security policies disallow it. For cross-process messages, carry authenticated actor metadata in the message envelope and validate the message origin.

### Example Actor Context for System Jobs

You can define an abstraction:

~~~java
public interface ActorContext {
    Optional<String> currentActorId();
}
~~~

A request implementation can read Spring Security. A job implementation can return a system actor named after the task.

The auditing service depends only on `ActorContext` via `AuditorAware`, decoupling identity resolution from the specific execution mechanism.

If using `ThreadLocal` for actor context in workers, always clear the context in a `finally` block after each task. Otherwise, thread pool reuse can leak a previous task's actor into the next task.

## 14. Designing AuditorAware for Both User and System Actors

An application may have multiple actor types. Rather than cramming all logic into one long class, separate actor resolution into an abstraction.

~~~java
public interface ActorProvider {
    Optional<String> currentActorId();
}
~~~

Auditor:

~~~java
import java.util.Optional;

import org.springframework.data.domain.AuditorAware;
import org.springframework.stereotype.Component;

@Component("auditorAware")
public class ApplicationAuditorAware implements AuditorAware<String> {

    private final ActorProvider actorProvider;

    public ApplicationAuditorAware(ActorProvider actorProvider) {
        this.actorProvider = actorProvider;
    }

    @Override
    public Optional<String> getCurrentAuditor() {
        return actorProvider.currentActorId();
    }
}
~~~

An `ActorProvider` can prioritize the authenticated request actor; if absent, inspect the application-established job context; and finally return empty or a system actor per policy.

What matters is an explicit policy. Do not silently fall back to `"system"` for every unauthenticated request, as that can mask security misconfigurations or dropped context.

## 15. Separating Audit Metadata from Immutable Change History

The four auditing fields retain only the current state:

- Who created the document.
- When the document was created.
- Who last modified it.
- When it was last modified.

If a document is edited 20 times, `@LastModifiedBy` holds only the 20th editor. It does not retain all 20 edits.

If full history is required, use a separate audit event or change log:

~~~json
{
  "eventId": "audit-evt-1001",
  "entityId": "DOC-1001",
  "action": "TITLE_CHANGED",
  "actorId": "admin-17",
  "occurredAt": "2026-11-13T10:15:00Z",
  "changes": {
    "title": {
      "old": "Inventory policy",
      "new": "Inventory policy v2"
    }
  }
}
~~~

Audit events require careful design for write permissions, retention, tamper protection, and linkage to business actions. Do not treat `@CreatedBy`/`@LastModifiedBy` fields as an immutable audit log system.

If the document and audit event must be written together reliably, remember Elasticsearch does not provide multi-document ACID transactions across two independent operations. Use an outbox or an event-publishing mechanism backed by your primary data store.

## 16. Testing AuditorAware

`AuditorAware` is a simple interface and can be unit-tested independently without Elasticsearch.

Example testing when no authentication exists:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Optional;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.context.SecurityContextHolder;

class SecurityAuditorAwareTest {

    private final SecurityAuditorAware auditorAware =
            new SecurityAuditorAware();

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void returnsEmptyWhenNoAuthenticationExists() {
        assertThat(auditorAware.getCurrentAuditor())
                .isEqualTo(Optional.empty());
    }
}
~~~

If your implementation constructor takes dependencies or custom principals, adjust the test for the real class.

Tests to include:

- No authentication.
- Unauthenticated authentication object.
- Anonymous authentication.
- Authenticated user.
- Custom principal with user ID.
- Principal of an unexpected type.
- Job context with system actor.
- Context cleared after task completion.

Every test must clean up `SecurityContext` so thread-local state does not bleed into subsequent tests.

## 17. Testing DateTimeProvider with a Fixed Clock

The date provider can be tested in isolation:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.data.auditing.DateTimeProvider;

class AuditingDateTimeProviderTest {

    @Test
    void returnsTimeFromInjectedClock() {
        Instant expected =
                Instant.parse("2026-11-13T09:30:00Z");

        Clock clock = Clock.fixed(expected, ZoneOffset.UTC);

        DateTimeProvider provider =
                () -> Optional.of(Instant.now(clock));

        assertThat(provider.getNow())
                .contains(expected);
    }
}
~~~

In integration tests with Elasticsearch, use a controllable clock to verify:

1. Saving the entity for the first time.
2. Asserting `createdDate` and `lastModifiedDate`.
3. Advancing the clock timestamp.
4. Updating the entity.
5. Asserting `createdDate` is preserved.
6. Asserting `lastModifiedDate` changed.
7. Asserting `createdBy` retains the original actor and `lastModifiedBy` receives the new actor.

Run this test through the repository or `ElasticsearchOperations.save(...)` to verify entity callbacks actually execute.

## 18. Testing Auditing on the Real Write Path

A unit test for `AuditorAware` does not prove auditing is enabled in the application context. You need integration tests verifying the full path.

Scenario outline:

~~~java
@Test
void writesAuditFieldsOnCreateAndUpdate() {
    // 1. Set actor = user-1024 and timestamp T1.
    // 2. Save new entity.
    // 3. Read document back and assert created/modified = user-1024, T1.
    // 4. Switch actor = admin-17 and timestamp T2.
    // 5. Save updated entity.
    // 6. Read back and assert created unchanged, modified = admin-17, T2.
}
~~~

Beyond the happy path, test:

- `AuditorAware` returning empty.
- `modifyOnCreate = false`.
- Entities with pre-assigned IDs.
- Entities with `@Version`.
- Updates using `UpdateQuery` or scripts.
- Bulk ingestion.
- Jobs without user authentication.
- Security context across executors/message listeners.

In particular, entities with pre-assigned IDs can affect how Spring Data determines whether an entity is new or existing. Newness detection relies on metadata such as version and ID. If using deterministic IDs, test `@CreatedDate`/`@CreatedBy` on initial creation; never assume an entity with a pre-assigned ID is automatically treated as new.

## 19. Common Pitfalls

### Forgetting to Enable @EnableElasticsearchAuditing

Having annotations on the entity without auditing configuration leaves fields unpopulated. Enable auditing in the application context and confirm the bean is initialized.

### Using the Wrong Annotation Package

`@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, and `@LastModifiedDate` belong to `org.springframework.data.annotation`. Do not confuse them with Elasticsearch mapping annotations.

### Hard-Coding the Auditor

A static auditor gives every document the same creator/modifier. Resolve the actor from the security context or a server-managed actor context.

### Treating Anonymous as an Authenticated User

An anonymous token can report as authenticated. Exclude `AnonymousAuthenticationToken` or check the principal type properly.

### Background Jobs Lacking an Actor

Scheduled jobs and consumers typically lack a request `SecurityContext`. Choose a policy returning empty or a system actor and clearly identify the task source.

### SecurityContext Not Propagated Across Threads

`SecurityContextHolder` is typically thread-bound. Use supported propagation mechanisms or pass the actor ID explicitly; do not assume executors carry context automatically.

### Using LocalDateTime Without a Timezone Convention

Timezone-less timestamps easily cause confusion when multiple services run across different timezones. Prefer `Instant` for audit timestamps.

### Assuming Update Scripts Run Auditing Callbacks

Scripted updates modify documents directly in Elasticsearch. Pass `lastModifiedBy` and `lastModifiedDate` via script params when audit metadata is required on that path.

### Assuming Four Audit Fields Form an Immutable History

`@LastModifiedBy` retains only the latest actor. To store every change, use a separate audit event or change log.

### Not Testing Entities with Pre-Assigned IDs

Entities with deterministic IDs can affect new-state detection. Test Created fields on actual inserts and consider version metadata where appropriate.

## 20. Process for Implementing Auditing

When introducing auditing into a Spring Data Elasticsearch application:

1. Choose a stable actor ID format, such as user ID or service ID.
2. Define the policy when no authentication is present.
3. Create an `AuditorAware<T>` bean reading the actor from the security/actor context.
4. Create a `DateTimeProvider` bean backed by a UTC `Clock`.
5. Enable `@EnableElasticsearchAuditing` with the proper bean references.
6. Annotate the entity with `@CreatedBy`, `@LastModifiedBy`, `@CreatedDate`, and `@LastModifiedDate`.
7. Select appropriate temporal types and mappings.
8. Configure `modifyOnCreate` according to field semantics.
9. Verify callbacks on Repository and `ElasticsearchOperations.save(...)`.
10. Inspect update, script, and bulk paths to see if they bypass callbacks.
11. Propagate actor context safely across async/job/message processing.
12. Test creation, updates, empty auditor, system actors, and fixed clocks.
13. If full history is required, design dedicated audit events.
14. Monitor for documents missing audit metadata to catch write paths bypassing auditing.

## References

- [Spring Data Elasticsearch — Auditing](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/auditing.html)
- [Spring Data Elasticsearch — EnableElasticsearchAuditing API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/config/EnableElasticsearchAuditing.html)
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html)
- [Spring Data Commons — AuditorAware API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AuditorAware.html)
- [Spring Data Commons — DateTimeProvider API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/auditing/DateTimeProvider.html)
- [Spring Security — SecurityContextHolder](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)

## Conclusion

`AuditorAware<T>` supplies actor identities for `@CreatedBy` and `@LastModifiedBy`; `DateTimeProvider` supplies timestamps for `@CreatedDate` and `@LastModifiedDate`. Enable the mechanism with `@EnableElasticsearchAuditing`, resolve users from an authenticated security context, and use `Clock` to control time—especially in tests. For background jobs, message consumers, scripted updates, and bulk paths, pass the actor or populate metadata according to an explicit policy because not every write path flows through entity callbacks. The four auditing fields describe the creator and latest modifier; when a complete change history is needed, store dedicated audit events separately.
