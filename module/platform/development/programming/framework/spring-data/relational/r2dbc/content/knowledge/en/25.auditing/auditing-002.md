# Mapping Creation and Update Timestamps

In Spring Data Relational R2DBC, auditing helps automatically record who created a record, who modified it, and when those operations occurred. Instead of manually assigning createdAt, updatedAt, createdBy, or updatedBy in every service, an application can declare metadata on the entity and enable Spring Data auditing.

Commonly used annotations:

- @CreatedDate: the timestamp when the record was created.
- @LastModifiedDate: the timestamp when the record was most recently modified.
- @CreatedBy: the user or actor who created the record.
- @LastModifiedBy: the user or actor who most recently modified the record.

Auditing must be activated with @EnableR2dbcAuditing. If you want to record the actor, you need to provide ReactiveAuditorAware to retrieve the current actor from the reactive context. If you want to control the time source, you can configure DateTimeProvider and Clock.

Spring Data auditing executes within the entity persistence flow. A SQL statement written directly with DatabaseClient does not automatically run entity auditing callbacks. If there are multiple write paths, you must standardize where timestamps and actors are managed so audit data is neither missing nor inconsistent.

## 1. What problem does auditing solve?

A customer table often needs to store creation and update traces:

| Column | Meaning |
|---|---|
| created_at | Timestamp when the record was created |
| updated_at | Timestamp when it was most recently modified |
| created_by | Person or actor who created it |
| updated_by | Person or actor who modified it |

If each service sets these fields manually, the application can easily run into problems:

- One write flow forgets to update updated_at.
- One service uses local time while another uses UTC.
- A background task has no logged-in user and leaves the actor blank.
- An update accidentally overwrites created_at.
- Tests depend on real wall-clock time and become flaky.

Auditing centralizes this rule in the persistence infrastructure. When an entity is saved through a Spring Data mechanism that supports auditing, the annotated fields are populated according to the entity lifecycle.

Auditing does not replace a full change history. These four fields only tell you the creator, the last modifier, and the corresponding timestamps. If you need to know every modification, old/new values, or reasons for changes, you need to design a separate audit log, event log, or version history.

## 2. Declaring auditing fields on an entity

Example Customer entity:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @LastModifiedDate
    @Column("updated_at")
    private Instant updatedAt;

    @CreatedBy
    @Column("created_by")
    private String createdBy;

    @LastModifiedBy
    @Column("updated_by")
    private String updatedBy;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
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
}
~~~

The auditing annotations belong to Spring Data, not JPA:

- @CreatedDate marks the property holding the creation timestamp.
- @LastModifiedDate marks the property holding the most recent modification timestamp.
- @CreatedBy marks the property holding the auditor at creation time.
- @LastModifiedBy marks the property holding the auditor of the most recent modification.

@Column maps a Java property name to a database column name. A naming strategy can be used instead of explicit declarations, but actual column names must match the schema.

Audit fields should generally not be accepted directly from client requests. The service should let the auditing infrastructure manage them, preventing clients from submitting createdBy or modifying createdAt.

## 3. Enabling auditing for Spring Data R2DBC

Simply adding annotations to the entity is not enough. The application must enable R2DBC auditing:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.r2dbc.config.EnableR2dbcAuditing;

@Configuration
@EnableR2dbcAuditing
public class R2dbcAuditingConfiguration {
}
~~~

When enabled, Spring Data registers reactive auditing infrastructure to populate annotated fields during the entity persistence lifecycle.

If only timestamps are needed, this minimal configuration is usually sufficient. If @CreatedBy or @LastModifiedBy is needed, provide an auditor provider. If there is no auditor provider or no actor is found, the actor fields may remain unset; timestamps can still work independently.

### Configuring modifyOnCreate

@EnableR2dbcAuditing has a modifyOnCreate attribute. Under the default configuration, last-modified fields are also set when an entity is created. This means updatedAt may equal or be very close to createdAt after the initial INSERT.

If business logic wants only created fields on initial creation, you can configure:

~~~java
@Configuration
@EnableR2dbcAuditing(modifyOnCreate = false)
public class R2dbcAuditingConfiguration {
}
~~~

Then @LastModifiedDate and @LastModifiedBy fields are not set merely because the entity is newly created. When the entity is subsequently modified, these fields will reflect the modification.

The setDates attribute can also be used to enable or disable populating date/time fields. Only disable it when the application has another explicitly managed timestamp source.

## 4. Mapping timestamps and actors per operation

With the default configuration modifyOnCreate = true, the general behavior is as follows:

| Field | On INSERT | On UPDATE |
|---|---|---|
| @CreatedDate | Populated | Preserves original creation timestamp |
| @LastModifiedDate | Populated | Updated |
| @CreatedBy | Populated if auditor exists | Preserves original creating actor |
| @LastModifiedBy | Populated if auditor exists | Updated if auditor exists |

If modifyOnCreate = false is configured, last-modified fields are not set during initial creation by auditing alone.

Example:

~~~text
INSERT customer
  created_at = 2026-01-10T09:00:00Z
  updated_at = 2026-01-10T09:00:00Z
  created_by = "alice"
  updated_by = "alice"

UPDATE customer
  created_at = 2026-01-10T09:00:00Z   (unchanged)
  updated_at = 2026-01-12T14:30:00Z   (changed)
  created_by = "alice"                 (unchanged)
  updated_by = "bob"                   (changed)
~~~

The timestamps in this example are illustrative only. Actual values depend on DateTimeProvider, timestamp column precision, and when the callback executes.

@CreatedDate does not mean the timestamp is auto-generated by the database. With application-side auditing, Spring Data sets the value before writing the entity. If you want the database to be the timestamp source, design database defaults or triggers and ensure the INSERT statement does not overwrite that value.

## 5. Configuring ReactiveAuditorAware

@CreatedBy and @LastModifiedBy need to know the current actor. In a reactive application, use ReactiveAuditorAware<T> instead of reading from ThreadLocal in an imperative manner.

Example retrieving the username from the Spring Security Reactor Context:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.data.r2dbc.config.EnableR2dbcAuditing;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;

@Configuration
@EnableR2dbcAuditing(auditorAwareRef = "auditorAware")
public class R2dbcAuditingConfiguration {

    @Bean
    public ReactiveAuditorAware<String> auditorAware() {
        return () -> ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName)
            .filter(name -> !"anonymousUser".equals(name));
    }
}
~~~

The auditor provider returns Mono<String>:

1. ReactiveSecurityContextHolder reads the security context from the Reactor Context.
2. Retrieves the current Authentication.
3. Keeps only valid authentications.
4. Transforms it into the actor name.
5. Returns an empty Mono if there is no suitable actor.

The bean name in auditorAwareRef must match the auditorAware bean name. The generic type String must be compatible with the type of the createdBy and updatedBy properties.

### Do not use imperative SecurityContextHolder in a reactive flow

In a reactive application, do not rely on SecurityContextHolder.getContext() as if every operation always runs on the same thread. Reactor can switch threads during processing. ReactiveSecurityContextHolder retrieves the context via the reactive context, which fits reactive security.

If the application does not use Spring Security, ReactiveAuditorAware can obtain the actor from a reactive context provider, message metadata, or an appropriate application service. What matters is that the actor source follows the subscription/context of the current request.

## 6. Handling background tasks without a logged-in user

Not every write operation starts from an HTTP request. Examples include:

- Scheduled data synchronization jobs.
- Message-processing consumers.
- Batch imports.
- Administrative tasks.
- Migrations or system processes.

In these cases, ReactiveAuditorAware can return Mono.empty(). When every record is required to have an actor, define a clear system identity:

~~~java
@Bean
public ReactiveAuditorAware<String> auditorAware() {
    return () -> ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .filter(Authentication::isAuthenticated)
        .map(Authentication::getName)
        .filter(name -> !"anonymousUser".equals(name))
        .switchIfEmpty(Mono.just("system"));
}
~~~

Here, the actor "system" is an application convention. More specific values such as batch-import, scheduler, or service name can be used to trace the source of changes.

Do not use a default actor if doing so loses important information about who performed the action. If business logic needs to distinguish real users, service accounts, and jobs, design a clear domain of actor values.

For message consumers, the actor can be extracted from message metadata if the publisher is authenticated. Do not trust an arbitrary username string from an unauthenticated payload.

## 7. Configuring DateTimeProvider and Clock

By default, auditing uses Spring Data's time source. You can provide a custom DateTimeProvider to control the timestamp source, which is especially useful when:

- Standardizing on UTC.
- Using a replaceable Clock in tests.
- Controlling time across a multi-service application.
- Generating timestamps under a unified policy.

Configuration example:

~~~java
import java.time.Clock;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.r2dbc.config.EnableR2dbcAuditing;

@Configuration
@EnableR2dbcAuditing(dateTimeProviderRef = "dateTimeProvider")
public class R2dbcAuditingConfiguration {

    @Bean
    public Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean
    public DateTimeProvider dateTimeProvider(Clock auditClock) {
        return () -> Optional.of(auditClock.instant());
    }
}
~~~

DateTimeProvider returns Optional<TemporalAccessor>. Instant is a TemporalAccessor, so it can be used as a time value for entities with a compatible type.

If configuring both an auditor and a date provider simultaneously, declare both references:

~~~java
@EnableR2dbcAuditing(
    auditorAwareRef = "auditorAware",
    dateTimeProviderRef = "dateTimeProvider",
    modifyOnCreate = true
)
~~~

Create only one bean matching each reference name. If bean names do not match or there are multiple ambiguous providers of the same type, the auditing configuration may fail to start as expected.

### Replaceable Clock in testing

In tests, use a fixed Clock:

~~~java
@Bean
public Clock auditClock() {
    return Clock.fixed(
        Instant.parse("2026-01-10T09:00:00Z"),
        ZoneOffset.UTC
    );
}
~~~

Then date/time fields are populated by auditing with a deterministic timestamp. Tests do not need to wait on the real clock or compare timestamps with unnecessary tolerances.

## 8. Choosing a Java type for audit timestamps

The Java type must fit the time semantics and the database column type.

| Java Type | Meaning | When appropriate |
|---|---|---|
| Instant | An absolute point on the UTC timeline | Creation/modification times shared across systems |
| OffsetDateTime | Date and time with a UTC offset | When needing to preserve the offset in exchanged values |
| ZonedDateTime | Date and time with a zone ID | When business logic requires a zone such as Europe/Paris |
| LocalDateTime | Local date and time without zone/offset | Schedules or wall-clock time at a fixed, known location |
| LocalDate | Date only, without time | Business dates, not creation/modification timestamps |

For createdAt and updatedAt representing actual points in time, Instant is usually the easiest choice to exchange across services. When displaying, convert Instant to the user's timezone in the presentation layer.

Do not store audit timestamps as arbitrary strings. Use temporal types and mappings supported by the R2DBC driver so the database can compare, sort, and index them.

## 9. Choosing database column types and timezones

The schema must be compatible with the Java type and R2DBC driver.

Example schema with audit columns:

~~~sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE,
    created_by VARCHAR(150),
    updated_by VARCHAR(150)
);
~~~

This is illustrative PostgreSQL syntax. Timestamp types and ID generation syntax vary across databases.

Some notes:

- PostgreSQL TIMESTAMP WITH TIME ZONE (timestamptz) represents an instant; the database does not preserve the sender's original timezone name.
- PostgreSQL TIMESTAMP WITHOUT TIME ZONE stores date and time without a timezone.
- MySQL TIMESTAMP has conversion rules based on the session time zone; DATETIME does not carry the same conversion semantics.
- Java types and codecs must match the specific column and R2DBC driver.
- Databases may store timestamps with lower than nanosecond precision; read-back values may be rounded or truncated in fractional seconds.

There is no single SQL column type suitable for every database. Choose the semantics first, then verify the mapping with the actual driver.

### Avoiding mixing local time and UTC

If one service stores local time and another stores UTC, but both write to the same timezone-less column, comparisons and sorting can become incorrect.

For audit timestamps, a common convention is:

1. Generate the timestamp as Instant/UTC.
2. Store it using a column type with matching semantics.
3. Read it back as the corresponding temporal type.
4. Convert to the user's zone for display.

If business logic needs to record the timezone where an event occurred, store an additional zone ID or offset separately; do not expect all timestamp types to preserve original zone information.

## 10. Designing a schema for auditing

General schema example:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP,
    created_by VARCHAR(150),
    updated_by VARCHAR(150)
);
~~~

Schema decisions to clarify:

- Is created_at mandatory?
- Can updated_at be NULL until the first update?
- Can created_by and updated_by be absent in system tasks?
- Is the actor a username, user ID, service ID, or another identifier?
- Is an index needed on created_at or updated_at for administrative queries?
- Does the timestamp need millisecond or micro/nanosecond precision?

If the application uses auditing to always assign created_at before INSERT, the column can be NOT NULL. However, every write path must go through auditing or provide a valid value itself.

If existing data is present, migrations must backfill new columns before applying NOT NULL. Do not add a NOT NULL column to a table with existing data without a default or proper backfill step.

### Database defaults and application-side auditing

A default such as:

~~~sql
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
~~~

is only applied when the INSERT statement lets the database apply the default—for example, omitting the column from the INSERT list or using the DEFAULT keyword. If Spring Data sends an explicit NULL value, a normal default will not automatically replace NULL with the current timestamp.

Therefore, choose a single timestamp owner:

- The application uses Spring Data auditing and binds the value.
- The database uses a default/trigger and write statements let the database generate the value.
- Another unified workflow with a clear contract.

Avoid having both the application and database overwrite timestamps without precedence rules.

## 11. Auditing when calling repository.save()

When saving an entity via a Spring Data repository, auditing callbacks can set fields before data is written:

~~~java
public Mono<Customer> createCustomer(String name) {
    Customer customer = new Customer(name);
    return customerRepository.save(customer);
}
~~~

If auditing is enabled:

- createdAt is set on creation.
- updatedAt is set on creation if modifyOnCreate is enabled.
- createdBy is set if the auditor provider emits an actor.
- updatedBy is set on creation if modifyOnCreate is enabled and an auditor exists.

On update:

~~~java
public Mono<Customer> rename(Long id, String newName) {
    return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(
            new CustomerNotFoundException(id)
        ))
        .flatMap(customer -> {
            customer.rename(newName);
            return customerRepository.save(customer);
        });
}
~~~

createdAt and createdBy retain creation metadata. updatedAt and updatedBy are updated by auditing.

Continue the pipeline using the entity returned from save(), as the resulting entity may contain a new ID, version, and updated auditing fields.

## 12. Auditing when using R2dbcEntityTemplate

R2dbcEntityTemplate uses Spring Data Relational's mapping infrastructure and participates in the framework's entity lifecycle.

Insert example:

~~~java
Mono<Customer> saved =
    r2dbcEntityTemplate.insert(Customer.class)
        .using(new Customer("An"));
~~~

Entity update example:

~~~java
Mono<Customer> saved =
    r2dbcEntityTemplate.update(customer);
~~~

Exact APIs may vary by Spring Data version. When using entity operations on the template, auditing is applied according to the lifecycle supported by Spring Data. Always use the returned entity to obtain the latest timestamps and version.

If using the template for bulk-style updates or statements that do not map an entity, do not assume auditing automatically runs per row. Check the specific operation type.

## 13. Auditing when using DatabaseClient or plain SQL

DatabaseClient allows writing custom SQL:

~~~java
return databaseClient.sql(
        "UPDATE customer " +
        "SET name = :name, updated_at = :updatedAt, updated_by = :updatedBy " +
        "WHERE id = :id"
    )
    .bind("name", newName)
    .bind("updatedAt", clock.instant())
    .bind("updatedBy", actor)
    .bind("id", id)
    .fetch()
    .rowsUpdated();
~~~

Here, the application manages updated_at and updated_by manually. Do not assume @LastModifiedDate or @LastModifiedBy will be automatically applied to a handwritten DatabaseClient SQL statement.

If the system has multiple write paths:

- Repository save().
- R2dbcEntityTemplate.
- DatabaseClient.
- Stored procedures or triggers.

define a consistent audit convention. You can let database triggers manage timestamps, or require every plain SQL statement to update audit columns manually. If one write path forgets to update them, audit data becomes inconsistent.

### Bulk updates

An UPDATE statement affecting multiple rows usually does not instantiate an entity per row. Consequently, there is no automatic entity auditing callback per record as in the regular entity save flow.

Example:

~~~sql
UPDATE customer
SET status = :status
WHERE last_login_at < :cutoff;
~~~

If you need to update updated_at and updated_by for all rows, add them to the SQL statement or use a trigger:

~~~sql
UPDATE customer
SET status = :status,
    updated_at = :updatedAt,
    updated_by = :updatedBy
WHERE last_login_at < :cutoff;
~~~

## 14. Auditing and @Version are two separate responsibilities

@CreatedDate and @LastModifiedDate record timestamps. @CreatedBy and @LastModifiedBy record actors. @Version serves optimistic locking.

| Property | Purpose |
|---|---|
| @CreatedDate | Creation timestamp |
| @LastModifiedDate | Most recent modification timestamp |
| @CreatedBy | Creating actor |
| @LastModifiedBy | Most recent modifying actor |
| @Version | Detecting concurrent updates |

Do not use updatedAt instead of version. Two transactions can read the same timestamp, or timestamp precision may be insufficient to distinguish two very close writes. Version is a concurrency token managed by Spring Data with its own semantics.

If an entity has both @Version and auditing, both mechanisms can operate together during a single save. Auditing updates metadata; version verifies write state and increments the version according to optimistic locking rules.

## 15. Audit timestamps are set before commit

Auditing timestamps are usually set in the lifecycle before the write statement completes. Therefore, the following scenario can occur:

1. The entity is assigned updatedAt.
2. The UPDATE is sent.
3. A subsequent operation in the transaction fails.
4. The transaction rolls back.

The database retains the old timestamp because the UPDATE was not committed. However, the Java object in memory may still contain the new timestamp assigned earlier.

Do not treat audit values on the in-memory object as proof that the transaction committed. If a transaction fails, reload the entity from the database before using persisted state as the source of truth.

This is especially important for mutable entities retained in a cache or reused after a reactive transaction fails.

## 16. Testing auditing

Test against a real R2DBC database or Testcontainers to verify timestamp and auditor mappings.

### Testing creation timestamps

With a fixed Clock:

~~~java
Instant fixedInstant =
    Instant.parse("2026-01-10T09:00:00Z");
~~~

After saving a new entity, verify:

- createdAt has a value.
- updatedAt has a value if modifyOnCreate = true.
- createdBy and updatedBy equal the current actor if an auditor is provided.

### Testing updates

1. Create an entity with actor alice.
2. Change the Clock to a different timestamp or use a controllable test DateTimeProvider.
3. Switch the auditor to bob.
4. Save the modified entity.
5. Read it back from the database.
6. Verify createdAt and createdBy are unchanged.
7. Verify updatedAt and updatedBy reflect the modification.

### Testing tasks without an actor

Verify the policy when ReactiveAuditorAware returns Mono.empty():

- Whether actor fields may remain unset.
- Whether the database columns allow NULL.
- Whether a default actor like system is required.

### Testing precision and timezones

Do not always compare timestamps using equals against nanosecond-precision Instants if the database only stores microseconds or milliseconds. Compare according to column precision or verify values normalized under the system's conventions.

Verify round-trip behavior:

1. Write an Instant with fractional seconds.
2. Read it back through the same R2DBC driver.
3. Verify the timestamp matches after accounting for database precision.
4. Run the test with a controlled session timezone if the database performs session-based timezone conversions.

### Testing plain SQL write paths

If the system uses DatabaseClient, add tests proving that audit fields are updated according to the SQL or trigger convention. Do not infer from repository save() tests that bulk updates are also automatically audited.

## 17. Common mistakes

| Mistake | Consequence | How to fix |
|---|---|---|
| Adding @CreatedDate without enabling auditing | Date fields are not automatically set | Use @EnableR2dbcAuditing |
| Using @CreatedBy without an auditor provider | No actor to record | Configure ReactiveAuditorAware |
| Using imperative AuditorAware in a reactive flow | May fail to read the security context properly | Use ReactiveAuditorAware |
| Reading SecurityContextHolder from the current thread | Actor may be wrong or missing when switching threads | Use ReactiveSecurityContextHolder |
| Forgetting modifyOnCreate | Confusion when updatedAt is set right on INSERT | Define create/update policy |
| Client sends createdAt/createdBy | Audit metadata can be spoofed | Do not accept audit fields from requests |
| Mixing LocalDateTime and Instant | Timezone or semantic mismatches | Standardize on a single time type |
| Using DB default while INSERT sends NULL | Default may not be applied | Pick one timestamp owner and control columns in INSERT |
| Writing with DatabaseClient expecting callbacks to run | Audit fields are not updated | Bind audit fields or use a trigger |
| Bulk update forgetting updated_at | Inconsistent audit data | Update in SQL or use a trigger |
| Using updatedAt instead of @Version | Cannot reliably detect concurrency | Use a separate @Version |
| Not backfilling new columns | Migration failure or old rows missing audit data | Backfill before setting NOT NULL |
| Assuming timestamps always have nanosecond precision | Tests fail due to database precision | Compare according to actual precision |
| Keeping an entity after transaction rollback | Object may hold uncommitted timestamps | Reload persisted state |

## 18. Workflow for implementing auditing

You can implement auditing in the following order:

1. Identify which fields need to be recorded: created date, modified date, created actor, modified actor.
2. Choose appropriate Java types and database column types.
3. Add auditing annotations to the entity.
4. Create migrations for audit columns and backfill existing data.
5. Enable @EnableR2dbcAuditing.
6. Configure ReactiveAuditorAware if an actor is required.
7. Configure DateTimeProvider/Clock if a controllable time source is required.
8. Define modifyOnCreate and the actor policy for background jobs.
9. Verify that all write paths apply the same audit rules.
10. Write integration tests for INSERT, UPDATE, background tasks, plain SQL, timezones, and precision.

Do not let auditing depend on implicit conventions. Explicitly define who the actor is, where time is generated, whether last-modified is updated on creation, and how bulk operations are handled.

## 19. Key takeaways

- @CreatedDate and @LastModifiedDate map creation and modification timestamps; @CreatedBy and @LastModifiedBy map actors.
- Auditing must be enabled with @EnableR2dbcAuditing.
- Reactive applications should provide ReactiveAuditorAware<T> to read the actor from the Reactor Context.
- Having no auditor can leave actor fields unset; define a policy for background jobs.
- modifyOnCreate allows last-modified fields to be set on creation by default; it can be disabled if business logic requires.
- Use DateTimeProvider and Clock to control the time source and keep tests deterministic.
- Instant usually fits absolute timestamps; Java types, SQL columns, and R2DBC codecs must be compatible.
- Explicitly choose UTC/timezone and precision; do not mix local time and UTC under the same convention.
- Repositories and entity operations of R2dbcEntityTemplate participate in auditing lifecycles; handwritten DatabaseClient SQL does not automatically trigger entity auditing callbacks.
- Bulk updates must update audit fields manually or rely on well-designed triggers.
- Auditing does not replace @Version, full audit logs, or authorization.
- Timestamps assigned in memory before commit do not prove a transaction committed.
- Do not accept audit metadata from clients and do not let any write path bypass audit rules.
- Test with the actual R2DBC driver/database, including actors, timezones, precision, and plain SQL write paths.
