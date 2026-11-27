# Audit Values for Background Data Imports or Scheduled Tasks

Spring Data JPA Auditing automatically records certain entity metadata during persistence lifecycles, typically including creation time, update time, creator, and last modifier. For web requests, user identity can be obtained from the security context. However, when data is imported from files, synchronized from external systems, executed on a schedule, or processed by background workers, there is usually no logged-in user.

Without explicitly designing the task-executing identity, `createdBy` and `lastModifiedBy` may be left empty, attributed to the wrong user, or set to a single generic value across all records that is hard to trace. This article covers how to identify actors for background tasks, configure `AuditorAware`, handle timestamps, perform chunked data imports, and understand limitations when using bulk SQL.

## 1. What Does Spring Data JPA Auditing Record?

Spring Data JPA Auditing typically manages four pieces of information:

| Annotation | Meaning | Typical Timing |
|---|---|---|
| `@CreatedDate` | When the entity was created | When the entity is first persisted |
| `@LastModifiedDate` | When the entity was last modified | On creation and each entity update |
| `@CreatedBy` | Actor that created the entity | When the entity is created |
| `@LastModifiedBy` | Actor that last modified the entity | On creation and each entity update |

These fields describe entity metadata within the application. They do not automatically create a complete history of every change. For example, `lastModifiedBy` only retains the most recent actor, not all previous actors or old/new values of individual properties.

When importing data, distinguish three concepts:

- **Executing actor:** the account or process actually running the import, such as `job:nightly-import`.
- **Initiator:** the person who requested or approved the import, such as an administrator.
- **Data source:** the system or file supplying the records, such as `legacy-crm` or `partner-feed`.

Do not assume these three values are the same. `@CreatedBy` should typically reflect the actor actually writing the entity to the database. If you need to know who initiated the import or where the data came from, store separate fields such as `requestedBy`, `importJobId`, `sourceSystem`, or `sourceRecordId`.

## 2. Configuring Auditing Fields on Entities

Enable auditing with `@EnableJpaAuditing`, register `AuditingEntityListener`, and annotate the fields to be tracked.

Shared fields can be placed in a `@MappedSuperclass` so multiple entities can reuse them:

```java
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.MappedSuperclass;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class AuditableEntity {

    @CreatedDate
    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    @LastModifiedDate
    @Column(nullable = false)
    private Instant lastModifiedAt;

    @CreatedBy
    @Column(length = 100, updatable = false)
    private String createdBy;

    @LastModifiedBy
    @Column(length = 100)
    private String lastModifiedBy;

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public String getLastModifiedBy() {
        return lastModifiedBy;
    }
}
```

A business entity extending this class:

```java
@Entity
public class Customer extends AuditableEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String externalCode;
    private String fullName;
    private String status;

    // Constructors, getters, and business methods
}
```

Temporal fields use `Instant` to represent a point on the timeline. When mapping to the database, agree on column types, UTC storage conventions, and user time zone display rules. Do not take the local time of the job runner machine and store it as if it were UTC.

`updatable = false` prevents JPA from including creation fields in regular UPDATE statements. This is a mapping-level safeguard; direct SQL statements can still modify these columns if written to do so.

## 3. Providing the Actor with AuditorAware

Spring Data JPA retrieves the current actor through the `AuditorAware<T>` interface. Type `T` must match the type of the `@CreatedBy` and `@LastModifiedBy` fields.

The example below prioritizes an explicitly attached background-task actor, then falls back to the user identity from Spring Security. If neither a user nor a job context is present, the application uses the technical actor `system`. Replace this fallback value according to your system's identification conventions.

```java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorAware")
public class JpaAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> AuditActorContext.current().or(() -> {
            Authentication authentication =
                    SecurityContextHolder.getContext().getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()
                    || authentication instanceof AnonymousAuthenticationToken) {
                return Optional.of("system");
            }

            return Optional.ofNullable(authentication.getName())
                    .filter(name -> !name.isBlank())
                    .or(() -> Optional.of("system"));
        });
    }
}
```

This example assumes the application already uses Spring Security. If the application does not have Spring Security, replace the `SecurityContextHolder` lookup with an appropriate identity source, or use only the job context for background tasks. Do not add a Security dependency just to obtain an auditing actor if the system does not need it.

Store a stable identifier such as a user ID, subject, or service account ID. Display names can change over time; storing display names as audit tracking keys makes reconciling historical data harder.

### 3.1. Enabling Auditing and Configuring Time

Spring Data can obtain the current time by default. If you want to control time zones and make tests deterministic, provide a `DateTimeProvider` backed by a `Clock`:

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;

@Configuration
@EnableJpaAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "auditingDateTimeProvider"
)
public class JpaAuditingTimeConfiguration {

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditingDateTimeProvider(Clock auditingClock) {
        return () -> Optional.of(Instant.now(auditingClock));
    }
}
```

If `@EnableJpaAuditing` is already declared in the actor configuration class, keep only one auditing-enabling configuration and add the `Clock`/`DateTimeProvider` beans there. Do not declare multiple independent `@EnableJpaAuditing` configurations arbitrarily.

Use a replaceable `Clock` in tests to assert exact `createdAt` and `lastModifiedAt` values. This is easier to control than waiting for wall-clock time to advance between operations.

## 4. Assigning Identity to Background Tasks and Schedulers

A scheduler normally runs without an HTTP request or a logged-in user. If `AuditorAware` only reads SecurityContext, the result may be `Optional.empty()`. If audit columns require a value, this can cause save operations to fail or leave audit data incomplete.

You can use a thread-scoped context to set the actor explicitly for each run. The context must be cleaned up when finished so a reused thread does not carry over the previous job's identity.

```java
import java.util.Optional;

public final class AuditActorContext {

    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    private AuditActorContext() {
    }

    public static Optional<String> current() {
        return Optional.ofNullable(CURRENT.get());
    }

    public static Scope use(String actor) {
        if (actor == null || actor.isBlank()) {
            throw new IllegalArgumentException("actor must not be blank");
        }

        String previous = CURRENT.get();
        CURRENT.set(actor);

        return () -> {
            if (previous == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(previous);
            }
        };
    }

    @FunctionalInterface
    public interface Scope extends AutoCloseable {
        @Override
        void close();
    }
}
```

Using the context in a scheduler:

```java
@Component
public class NightlyImportJob {

    private final ImportChunkService importChunkService;

    public NightlyImportJob(ImportChunkService importChunkService) {
        this.importChunkService = importChunkService;
    }

    @Scheduled(cron = "0 0 2 * * *")
    public void run() {
        try (AuditActorContext.Scope ignored =
                     AuditActorContext.use("job:nightly-import")) {
            importChunkService.importNextChunk();
        }
    }
}
```

The data-writing service lives in another Spring bean so calls pass through the transaction proxy:

```java
@Service
public class ImportChunkService {

    private final CustomerRepository customerRepository;

    public ImportChunkService(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    @Transactional
    public void importNextChunk() {
        // Read a chunk from the source and create/update Customer records.
        // Repository operations run within the chunk's transaction.
    }
}
```

In this example, `job:nightly-import` is the actor for the write operation. If the import was requested by a user, you can additionally store `requestedBy` to preserve the initiator's identity. Do not replace the executing actor with a username from the source data if that person did not actually perform the write operation.

`ThreadLocal` works when the job and transaction run synchronously on the same thread. If delegating work to an executor, `@Async`, a worker pool, or another thread, the context does not automatically propagate to the new thread. Pass the actor explicitly in the message/command or use a `TaskDecorator` to copy the context and restore the prior context after execution. Do not propagate context by holding an uncleaned static value.

## 5. Auditing When Importing Data via Repositories

When saving entities through the standard JPA lifecycle, the auditing listener has the opportunity to populate metadata fields.

For example, importing a new record:

```java
Customer customer = new Customer();
customer.setExternalCode(row.externalCode());
customer.setFullName(row.fullName());
customer.setStatus("ACTIVE");

customerRepository.save(customer);
```

If the entity is newly created and persisted in the persistence context, `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, and `@LastModifiedBy` are handled per the auditing configuration. With the actor context set to `job:nightly-import`, creator/modifier fields reflect that actor.

When updating an existing record, load the managed entity and update its business properties:

```java
Customer customer = customerRepository
        .findByExternalCode(row.externalCode())
        .orElseGet(Customer::new);

customer.setExternalCode(row.externalCode());
customer.setFullName(row.fullName());
customer.setStatus(row.status());

// If this is a new entity, save to persist.
// If already loaded and managed, dirty checking will write changes on flush.
customerRepository.save(customer);
```

For a new entity, Spring Data JPA uses `save()` to persist or merge depending on the state detected by the repository. For an entity already managed within a transaction, calling `save()` again is usually unnecessary; changes are detected by dirty checking at flush time.

When updating an existing entity, auditing normally preserves `createdAt` and `createdBy` while updating `lastModifiedAt` and `lastModifiedBy`. Do not manually reassign creation fields in import logic.

If the import supports upsert mode, clearly distinguish which cases are inserts and which are updates. Reconciliation keys should be stable, such as codes from the source system. Avoid creating new records on every run simply because previously imported records were not matched.

## 6. Large Data Imports: Chunking and Controlling the Persistence Context

Do not put hundreds of thousands of entities into a single transaction or persistence context by default. That can increase memory consumption, transaction lock duration, and rollback overhead when a single record fails.

For large imports, split data into appropriately sized chunks:

```text
Data source
    |
    v
Read chunk 1 --> transaction 1 --> commit
    |
    v
Read chunk 2 --> transaction 2 --> commit
    |
    v
Read chunk 3 --> transaction 3 --> commit
    |
    v
Import complete
```

Each chunk can be processed by a `@Transactional` service method. When a chunk succeeds, its transaction commits; if a chunk fails, only that chunk rolls back. If business rules require the entire file to succeed or fail together, consider larger transactions, staging tables, or stateful import workflows that support retries and recovery.

When processing many entities in the same transaction, call `flush()` and `clear()` periodically to keep the persistence context small:

```java
for (int i = 0; i < rows.size(); i++) {
    Customer customer = mapRow(rows.get(i));
    customerRepository.save(customer);

    if ((i + 1) % 500 == 0) {
        customerRepository.flush();
        entityManager.clear();
    }
}

customerRepository.flush();
```

This is an illustrative example for a moderately sized chunk; `EntityManager` needs to be injected into the service. `flush()` pushes pending SQL to the database without committing. `clear()` detaches all managed entities, so after clearing do not continue using old objects as if they were still managed. If updating existing entities, manage the order of loading, mutating, flushing, and clearing carefully.

`saveAll()` is convenient in source code but does not mean a single SQL batch statement. Spring Data may invoke save per entity; JDBC batching capability depends on Hibernate, the driver, and configuration. Measure actual performance and configure a batch size suited to your provider and database.

With Spring Batch, the actor should be stable per job/step or import run. If each chunk runs on its own thread, pass the actor through the job's execution context instead of relying on a ThreadLocal on the launching thread.

## 7. Do Bulk JPQL, Native SQL, and JDBC Run Auditing Automatically?

No. JPQL bulk update/delete operations, native SQL, and JDBC statements go straight to the database, bypassing per-entity lifecycles. As a result, `AuditingEntityListener` is not called per row, and `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, and `@LastModifiedBy` are not populated automatically.

Bulk JPQL example:

```java
@Modifying
@Query("""
    update Customer c
       set c.status = :status,
           c.lastModifiedAt = :modifiedAt,
           c.lastModifiedBy = :actor
     where c.id in :ids
    """)
int updateStatusBulk(
        @Param("ids") Collection<Long> ids,
        @Param("status") String status,
        @Param("modifiedAt") Instant modifiedAt,
        @Param("actor") String actor
);
```

With bulk queries, the application must pass the timestamp and actor explicitly. You can obtain the actor from the same service providing the auditing context and the timestamp from a shared `Clock`. After a bulk update, the persistence context may hold stale entities; flush changes that must be kept before the bulk operation and clear/refresh related entities as needed.

Configuring `@Modifying(flushAutomatically = true, clearAutomatically = true)` helps synchronize the persistence context before/after the bulk statement, but does not cause the auditing listener to run per row. Flush/clear only addresses persistence context state.

With JDBC, metadata must also be updated directly:

```sql
UPDATE customer
SET status = ?,
    last_modified_at = ?,
    last_modified_by = ?
WHERE id = ?
```

For upsert statements, only update `last_modified_*` in the update branch; preserve `created_*` on the existing record. In the insert branch, set both creation and update metadata according to system conventions.

If using database triggers to record audit fields automatically, decide whether triggers or the application are the source of truth for each field. Do not let JPA and triggers overwrite each other without clear rules. After a trigger modifies data, entities already in the persistence context may also need refreshing.

## 8. Choosing the Right Actor and Data Source for Business Semantics

Common scenarios:

| Scenario | Actor to Record | Additional Information to Consider Storing |
|---|---|---|
| User uploads a file and system imports asynchronously | Service account or import-executing actor per policy | `requestedBy`, filename, import batch ID |
| Nightly scheduled job | `job:nightly-import` | `jobExecutionId`, run timestamp, data source |
| Synchronization from partner system | `integration:partner-a` | `sourceSystem`, `sourceRecordId` |
| Worker processing messages | Service/worker identity of the consumer | Message ID, correlation ID |
| Administrator editing data in UI | Stable user ID of the administrator | Request ID if needed for tracing |

If you need to record who requested a job, capture that identity when creating the job and pass it along with job metadata. A scheduler running later cannot know the originating user once the original context has ended.

Do not use a single `system` value for all jobs if you need to distinguish tasks. Actors like `job:nightly-import`, `job:reconcile-orders`, or `integration:partner-a` are easier to trace. At the same time, keep naming conventions consistent so audit reports are not fragmented by inconsistent spellings.

If imported data carries a `createdBy` field from a legacy system, decide whether that field represents the creator in the source system or the actor creating the record in the current system. If it is from the legacy source, store it as `sourceCreatedBy` or source metadata. Do not overwrite `@CreatedBy` of the current system with unverified values.

## 9. Testing Auditing for Imports and Scheduled Tasks

At a minimum, test the following cases:

1. Creating an entity inside a job's actor context: `createdBy` and `lastModifiedBy` carry the expected actor; temporal fields are populated.
2. Updating an existing entity: `createdBy` remains unchanged, `lastModifiedBy` switches to the current actor, and the update timestamp refreshes.
3. Running a task with no logged-in user: the fallback actor is applied per policy.
4. Handling errors within a chunk: the transaction rolls back per designed boundaries; the actor context is still cleaned up in `finally`/try-with-resources.
5. Running bulk JPQL or JDBC: verify the statement explicitly updates metadata because the listener does not run.
6. Running concurrent jobs: each job records its own actor, with no ThreadLocal leakage across jobs.

Example testing the actor context:

```java
@Test
void shouldUseJobActorForImportedEntity() {
    try (AuditActorContext.Scope ignored =
                 AuditActorContext.use("job:test-import")) {

        Customer customer = new Customer();
        customer.setExternalCode("C-100");
        customer.setFullName("Example");
        customerRepository.saveAndFlush(customer);

        assertThat(customer.getCreatedBy())
                .isEqualTo("job:test-import");
        assertThat(customer.getLastModifiedBy())
                .isEqualTo("job:test-import");
        assertThat(customer.getCreatedAt()).isNotNull();
        assertThat(customer.getLastModifiedAt()).isNotNull();
    }
}
```

This test assumes the repository and entity have the required getters, auditing is enabled in the test context, and the transaction is flushed before assertions. Even if the test transaction rolls back after the test, that does not invalidate testing callbacks within the persistence context.

To test update timestamps, use a controllable mock `Clock`: create the entity at time T1, advance the clock to T2, modify the entity and flush; assert `createdAt` is still T1 while `lastModifiedAt` is T2. For bulk SQL, separately verify the actor and timestamp values passed into the statement.

## 10. Auditing Metadata Does Not Replace Change History

Spring Data JPA Auditing answers questions such as:

- When was the record created?
- Which actor created the record?
- When was the last update and by whom?

It does not automatically answer:

- What value did a field change from and to?
- Who modified the record in all earlier updates?
- When was the record deleted?
- Which changes belonged to the same import run or business operation?

If full history is required, design an appropriate mechanism in addition:

- **Hibernate Envers** to store entity revisions by configuration and support history queries.
- **Immutable audit tables** to store each change event, actor, timestamp, tracked values, and correlation ID.
- **Outbox/event log** to record business events in the same transaction and forward them reliably.
- **Database triggers** when database-level change tracking is needed, including from external applications.

Choose a solution based on retention, querying, performance, and system scope requirements. Do not add a full history mechanism if requirements only call for the four basic metadata fields.

## 11. Implementation Checklist

- [ ] Entity has `AuditingEntityListener` and auditing fields with matching data types.
- [ ] Application enables `@EnableJpaAuditing` and declares `AuditorAware` clearly.
- [ ] Jobs, schedulers, integrations, and workers have stable, traceable actors.
- [ ] Initiator actor is stored separately if different from the executing actor.
- [ ] Thread-scoped contexts are restored and cleaned up after tasks; async flows have actor propagation.
- [ ] Timestamps follow a consistent UTC/Instant convention and are testable with `Clock`.
- [ ] Imports are split into reasonable chunks; transactions and retries have clear boundaries.
- [ ] Do not assume `saveAll()` always generates a single SQL batch.
- [ ] Bulk JPQL, native SQL, and JDBC explicitly update necessary audit fields.
- [ ] Tests cover creation, update, background actors, chunk failures, and bulk updates.
- [ ] If per-change history is needed, selected an appropriate Envers, audit table, outbox, or trigger approach.

Spring Data JPA Auditing can accurately track import jobs and schedulers when the application intentionally provides the actor and time. For standard entity operations, the listener populates metadata through the JPA lifecycle; for bulk SQL/JDBC, the application must update those fields itself. Distinguishing the executing actor, initiator, and data source makes audit data meaningful and aids traceability when tasks run automatically or are retried.