# Mapping the Creator and Updater

In a Spring Data R2DBC application, many tables need to store who created a record and who most recently modified it. Beyond the actor information, systems often need creation and update timestamps to display history, assist incident investigation, or support operational workflows.

Spring Data provides an auditing mechanism to automatically populate these properties during the entity save lifecycle. Annotations such as `@CreatedBy`, `@LastModifiedBy`, `@CreatedDate`, and `@LastModifiedDate` describe the metadata to store; `@EnableR2dbcAuditing` enables auditing for R2DBC; and `ReactiveAuditorAware<T>` provides the current user reactively.

Auditing avoids having every Service manually assign `createdBy`, `updatedBy`, or timestamps under inconsistent rules. However, the application still must establish a trusted identity source, handle unauthenticated requests, provide the corresponding schema, and understand that direct SQL write statements do not automatically execute entity auditing callbacks.

## 1. Auditing metadata of an entity

A record typically has four metadata properties:

| Annotation | Meaning | When assigned |
|---|---|---|
| `@CreatedBy` | Creator of the record | When the entity is first inserted |
| `@CreatedDate` | Creation timestamp of the record | When the entity is first inserted |
| `@LastModifiedBy` | Most recent updater | On insert and when the entity is updated, depending on `modifyOnCreate` |
| `@LastModifiedDate` | Most recent update timestamp | On insert and when the entity is updated, depending on `modifyOnCreate` |

For example, a customer record might be stored as follows:

```text
id              = 42
email           = "an@example.com"
created_by      = 1008
created_date    = 2026-10-01T08:30:00Z
last_modified_by   = 1012
last_modified_date = 2026-10-05T14:12:00Z
```

The creator remains user `1008`, while the most recent updater is user `1012`. When the record is updated again, `createdBy` and `createdDate` are preserved; `lastModifiedBy` and `lastModifiedDate` are updated to the new actor and timestamp.

### 1.1. Auditing is not a full log of every change

The `created...` and `lastModified...` properties only store creation and most recent update metadata. They do not store the complete change history, before/after values, reasons for modification, or every user who ever edited the record.

If the business requires full history, design a separate audit table, event log, or appropriate temporal/history mechanism. Do not use `@LastModifiedBy` as an append-only audit trail system.

### 1.2. Actor identity must come from a trusted source

Do not take `createdBy` or `lastModifiedBy` from the request body and assign it directly to the entity. A client could send someone else's ID. The auditor must be obtained from an authenticated security context or a trusted system context established by the application.

## 2. Declaring auditing metadata in an entity

Customer entity example:

```java
package com.example.store.customer.persistence;

import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record CustomerEntity(
        @Id Long id,
        String email,
        @Column("display_name") String displayName,
        @CreatedBy @Column("created_by") Long createdBy,
        @LastModifiedBy @Column("last_modified_by") Long lastModifiedBy,
        @CreatedDate @Column("created_date") Instant createdDate,
        @LastModifiedDate @Column("last_modified_date") Instant lastModifiedDate
) {
}
```

In the example:

- `@CreatedBy` and `@LastModifiedBy` mark the properties storing the actor's ID.
- `@CreatedDate` and `@LastModifiedDate` mark the timestamp properties.
- `@Column` maps Java property names to specific column names.
- `Instant` represents an absolute point in time, suitable when the system needs consistent timestamps across timezones.

The type of the auditor property must be compatible with the type emitted by `ReactiveAuditorAware<T>`. Here both use `Long`. If the application stores usernames, UUIDs, or another ID type, use that same type for both the provider and the auditing properties.

### 2.1. Mutable classes can be used

If the entity is a regular class, you can declare the auditing fields and corresponding getters/setters. Spring Data will update metadata through the entity's property access mechanism. With immutable entities such as records or classes with `final` fields, the mapping infrastructure needs to create a new instance when values change; a record is a concise option if the constructor represents the full state.

Do not add public setters solely to make auditing work if your model already uses constructor mapping and Spring Data's immutable access mechanism. Test insert/update on your project's actual Spring Data version.

## 3. Enabling R2DBC auditing

For Spring Data R2DBC to automatically apply auditing annotations, enable the configuration with `@EnableR2dbcAuditing`.

```java
package com.example.store.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.r2dbc.config.EnableR2dbcAuditing;

@Configuration
@EnableR2dbcAuditing(auditorAwareRef = "auditorProvider")
public class R2dbcAuditingConfiguration {
}
```

`@EnableR2dbcAuditing` registers auditing infrastructure for Spring Data R2DBC, including callbacks needed to populate metadata during the entity save lifecycle. `auditorAwareRef` explicitly specifies the bean providing the current auditor. If the application only has one matching `ReactiveAuditorAware` bean, Spring can auto-select it based on configuration; declaring the name explicitly avoids ambiguity when there are multiple providers.

Commonly used options:

- `auditorAwareRef`: name of the bean providing the creator/updater.
- `dateTimeProviderRef`: name of the bean providing the current time if you want to customize the clock source.
- `setDates`: enables/disables populating timestamp properties.
- `modifyOnCreate`: determines whether `LastModified...` fields are assigned on insert.

By default, auditing typically populates date fields automatically and treats creation as the first modification. If `modifyOnCreate = false` is set, `LastModifiedBy`/`LastModifiedDate` properties are not assigned on creation under that configuration. Only change the default when the data contract explicitly requires it.

## 4. Providing the current user with ReactiveAuditorAware

In R2DBC, data access operations are reactive. The actor must be provided using `ReactiveAuditorAware<T>`, returning `Mono<T>`, rather than using a synchronous provider that may rely on ThreadLocal.

### 4.1. The ReactiveAuditorAware interface

`ReactiveAuditorAware<T>` resides in Spring Data Commons and has a method returning the current auditor as `Mono<T>`. When a valid user exists, the provider emits the ID or auditor object; when there is no auditor, the provider can complete empty.

Example of an application using Spring Security WebFlux with a principal containing the user ID:

```java
package com.example.store.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

@Configuration
public class AuditorConfiguration {

    @Bean
    ReactiveAuditorAware<Long> auditorProvider() {
        return () -> ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .filter(Authentication::isAuthenticated)
                .filter(authentication ->
                        !(authentication instanceof AnonymousAuthenticationToken))
                .map(Authentication::getPrincipal)
                .filter(AppPrincipal.class::isInstance)
                .cast(AppPrincipal.class)
                .map(AppPrincipal::userId);
    }
}
```

`AppPrincipal` is the application's principal type, for example:

```java
public record AppPrincipal(Long userId, String username) {
}
```

Processing flow:

1. `ReactiveSecurityContextHolder.getContext()` retrieves the security context from the Reactor Context.
2. Extracts the current `Authentication`.
3. Accepts only authenticated authentications and excludes anonymous authentication.
4. Extracts the principal and checks that it is an instance of `AppPrincipal`.
5. Returns `userId` as the auditor.

In a real application, the principal may be a `UserDetails`, `Jwt`, `JwtAuthenticationToken`, or a custom type. Map from the system's actual principal to the actor ID. Do not assume every authentication has the same principal type.

### 4.2. Why use ReactiveSecurityContextHolder?

In WebFlux, execution can switch across multiple threads. The current thread does not stably represent the request. `ReactiveSecurityContextHolder` reads the security context from the Reactor Context, making it suitable for reactive pipelines.

Do not use ThreadLocal-based `SecurityContextHolder.getContext()` as the default source for reactive auditing. That approach can return the wrong user or no user when execution switches threads, unless the application has a dedicated, explicitly configured context propagation mechanism.

### 4.3. What if there is no authentication?

`ReactiveAuditorAware` can return `Mono.empty()` if no authenticated user is found. Auditing can still populate timestamps, while the auditor field receives no new value. How this is handled depends on the application's schema and policy:

- Allow `created_by`/`last_modified_by` to be null for operations without a user.
- Require every operation to have an actor and reject writes if there is no identity.
- Use an explicit system actor for background tasks, migrations, or internal jobs.

Do not automatically use a default user ID for every anonymous request. That can corrupt audit history and mask unauthenticated requests.

### 4.4. Background tasks and system actors

Schedulers, message consumers, or batch jobs may run outside an HTTP security context. If business rules require every record to have `createdBy`/`lastModifiedBy`, define a dedicated system actor identity and apply it within the background task context.

For example, a job can run under a dedicated profile or orchestration flow with auditor `SYSTEM_ACTOR_ID`. Only use a system fallback where it is certain the work is internal. Do not place `switchIfEmpty(Mono.just(SYSTEM_ACTOR_ID))` globally if that would also turn unauthenticated requests into system operations.

If you need to distinguish multiple actor types, you can store a broader identifier such as `actor_type` alongside `actor_id`, or use a well-defined value object/enum convention. Do not use a fake numeric ID that collides with real user IDs.

## 5. Mapping creation and update timestamps

### 5.1. Using Instant for absolute points in time

`Instant` represents a point on the UTC timeline. It fits `createdDate` and `lastModifiedDate` when multiple services, users, or systems operate in different timezones.

Other temporal types such as `LocalDateTime`, `OffsetDateTime`, or `java.util.Date` may also be supported depending on mapping and database. However, `LocalDateTime` carries no timezone/offset information; if used, storage and interpretation rules must be clearly defined. Do not mix local and UTC timestamps in the same column without a convention.

### 5.2. Using DateTimeProvider when clock control is needed

By default, auditing gets the current time from Spring Data's provider. If you want to standardize the clock source or test with a fixed timestamp, you can provide a custom `DateTimeProvider`.

```java
@Configuration
@EnableR2dbcAuditing(
        auditorAwareRef = "auditorProvider",
        dateTimeProviderRef = "auditingDateTimeProvider")
public class R2dbcAuditingConfiguration {

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditingDateTimeProvider(Clock auditingClock) {
        return () -> Optional.of(auditingClock.instant());
    }
}
```

`DateTimeProvider` returns a `TemporalAccessor` wrapped in an `Optional`. Using `Clock` allows tests to replace the real clock with a fixed clock. When configuring both `auditorAwareRef` and `dateTimeProviderRef`, ensure both bean names match the references in the annotation.

In the complete example, the `ReactiveAuditorAware<Long>` bean `auditorProvider` is still declared as in the previous section. You can combine the beans into the same `@Configuration` class if that fits the project structure.

### 5.3. Timestamp column schema

PostgreSQL example:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(254) NOT NULL UNIQUE,
    display_name VARCHAR(120) NOT NULL,
    created_by BIGINT,
    last_modified_by BIGINT,
    created_date TIMESTAMPTZ,
    last_modified_date TIMESTAMPTZ
);
```

`TIMESTAMPTZ` stores a point in time with PostgreSQL's timezone-aware semantics. Java/database conversion rules should be verified for your driver and version. For other databases, choose the corresponding column type and specify timezone conventions explicitly.

If auditing is mandatory for all records, you can set `NOT NULL` on the corresponding columns once migrations have backfilled old data and the provider always returns a valid auditor. If some tasks have no user, decide clearly between using a system actor or allowing null before applying constraints.

### 5.4. Migrating existing tables

When adding auditing to a table with existing data, do not immediately add `NOT NULL` columns without values for existing rows. A migration process can be:

1. Add the auditing columns as nullable or with appropriate defaults.
2. Backfill `created_date` for existing rows with a known meaningful timestamp; if no exact source exists, clearly record it as the migration timestamp or an unknown marker per data policy.
3. Backfill `created_by`/`last_modified_by` with a migration/system actor if policy requires.
4. Inspect existing rows.
5. Apply `NOT NULL` only once every write path provides a value.

Do not assign a fake user as the creator for legacy data without evidence. If the original actor is unknown, keep null or use a clearly defined and documented sentinel value.

## 6. Auditing in the R2DBC entity save lifecycle

When `@EnableR2dbcAuditing` is enabled, Spring Data registers an auditing callback to populate entity metadata during the save lifecycle. Repositories and `R2dbcEntityTemplate` use Spring Data's mapping infrastructure, so auditing annotations are applied in those corresponding entity operations.

Overview flow:

```text
Repository.save(entity)
        |
        v
Spring Data R2DBC mapping pipeline
        |
        v
Auditing entity callback
        |
        +--> determine whether entity is new or existing
        +--> retrieve auditor from ReactiveAuditorAware
        +--> retrieve time from DateTimeProvider
        +--> assign Created... / LastModified...
        |
        v
Convert entity and execute SQL
        |
        v
Database
```

### 6.1. On insert

With default settings allowing date assignment and `modifyOnCreate`, an insert can populate:

- `createdBy` from the current auditor.
- `createdDate` from the date/time provider.
- `lastModifiedBy` from the current auditor.
- `lastModifiedDate` from the date/time provider.

`modifyOnCreate` can be set to `false` if the application wants `LastModified...` fields to appear only after the first update. Align this rule with your schema and API.

### 6.2. On update

When an existing entity is saved through a persistence path with auditing callbacks:

- `createdBy` is preserved.
- `createdDate` is preserved.
- `lastModifiedBy` is updated to the current auditor if available.
- `lastModifiedDate` is updated according to the date/time provider.

Do not take audit fields from requests to overwrite existing metadata. Let callbacks manage these fields.

### 6.3. Immutable entities

For records or immutable classes, callbacks must return the entity state updated with metadata via Spring Data's accessor/mapping mechanism. A record constructor or appropriate wither lets the framework create a new instance containing the audit values. Do not assume the input object will be mutated in place; use the entity returned from `save` when reading updated metadata.

Example:

```java
return customerRepository.save(customer)
        .map(saved -> {
            // saved has createdBy, createdDate, and version/metadata after saving.
            return saved;
        });
```

## 7. Write paths that do not automatically run auditing callbacks

Spring Data R2DBC auditing is tied to the entity mapping lifecycle. Not every SQL statement executed in an application goes through that lifecycle.

### 7.1. DatabaseClient and direct SQL

Example:

```java
databaseClient.sql("""
        UPDATE customers
        SET display_name = :displayName
        WHERE id = :id
        """)
    .bind("displayName", displayName)
    .bind("id", id)
    .fetch()
    .rowsUpdated();
```

This is a direct SQL statement. It does not materialize an entity and invoke auditing callbacks; therefore `lastModifiedBy` and `lastModifiedDate` are not automatically updated simply because `@EnableR2dbcAuditing` is enabled.

If a direct write path requires auditing, explicitly include those values in the SQL:

```sql
UPDATE customers
SET display_name = :displayName,
    last_modified_by = :actorId,
    last_modified_date = :modifiedAt
WHERE id = :id
```

`actorId` and `modifiedAt` values must come from the application's trusted context. Use bound parameters; never concatenate data into SQL strings.

### 7.2. Modifying queries in Repositories

A `@Query` performing direct update/delete should likewise not be assumed to run full entity auditing callbacks like `save(entity)`. If using modifying queries, verify the behavior of your Spring Data version and manage audit columns manually in the SQL statement if needed.

### 7.3. Database triggers

If multiple applications or tools outside Spring Data write to the same table, auditing callbacks in one application cannot observe those other writes. You can use database triggers or a database-level auditing mechanism to cover every writer.

Do not let both callbacks and triggers write the same column using two different time rules without a clear owner. Choose a single primary source for each audit field to avoid unpredictable overwrites.

## 8. Separating auditing metadata from API models

`createdBy`, `lastModifiedBy`, `createdDate`, and `lastModifiedDate` are server-managed metadata. Create or update requests should not let clients decide these values.

Request example:

```java
public record UpdateCustomerRequest(
        String displayName
) {
}
```

The response can expose part of the metadata per the API contract:

```java
public record CustomerResponse(
        Long id,
        String email,
        String displayName,
        Long createdBy,
        Long lastModifiedBy,
        Instant createdDate,
        Instant lastModifiedDate
) {
}
```

The Service layer maps the entity to the response. Do not bind requests directly into entities with audit fields, as clients could supply extra `createdBy`, `createdDate`, or other internal fields if the binding mechanism allows it.

If you do not want to expose internal user IDs, the response can return only timestamps or publicly permitted display names. Whether to return metadata is a decision of the API contract and access-control policy.

## 9. Auditing and business execution timestamps

`@LastModifiedDate` reflects when the entity was updated through the persistence lifecycle. It is not necessarily when a specific business action started, was approved, or completed.

For example, an order's metadata may be edited multiple times for note updates, while the payment timestamp needs to be stored separately as `paidAt`. Do not use `lastModifiedDate` to replace business timestamps such as:

- `submittedAt` — when the order was submitted.
- `approvedAt` — when the order was approved.
- `paidAt` — when payment occurred.
- `cancelledAt` — when the order was cancelled.
- `shippedAt` — when handed over to the carrier.

These fields should be assigned within the corresponding business actions. Auditing metadata provides general timestamps for entity creation and last persistence modification.

## 10. Testing auditing

Tests should verify both provider configuration and actual results after insert/update. Mocking `ReactiveAuditorAware` can help test Services, but integration tests must confirm callbacks are registered and database columns are written properly.

### 10.1. Testing ReactiveAuditorAware

You can verify that the provider returns the correct actor when the Reactor Security Context holds an authentication. Example using a test principal:

```java
AppPrincipal principal = new AppPrincipal(1008L, "an");
Authentication authentication =
        new UsernamePasswordAuthenticationToken(principal, "n/a");
SecurityContext context = new SecurityContextImpl(authentication);

StepVerifier.create(auditorProvider.getCurrentAuditor()
        .contextWrite(ReactiveSecurityContextHolder.withSecurityContext(
                Mono.just(context))))
        .expectNext(1008L)
        .verifyComplete();
```

This example illustrates placing a security context into the Reactor Context. In real tests, use the appropriate authentication constructor and the application's actual principal type.

### 10.2. Testing inserts

With `@DataR2dbcTest` or an integration test using a real `ConnectionFactory`, perform an insert through the repository and check:

- The ID is generated properly.
- `createdBy` and `lastModifiedBy` match the test auditor.
- `createdDate` and `lastModifiedDate` are populated.
- Column values in the database match the returned entity.

`StepVerifier` can be used to verify the publisher:

```java
StepVerifier.create(repository.save(newCustomer))
        .assertNext(saved -> {
            assertThat(saved.createdBy()).isEqualTo(1008L);
            assertThat(saved.lastModifiedBy()).isEqualTo(1008L);
            assertThat(saved.createdDate()).isNotNull();
            assertThat(saved.lastModifiedDate()).isNotNull();
        })
        .verifyComplete();
```

### 10.3. Testing updates

After inserting, change a business property and call `save`:

```java
StepVerifier.create(repository.findById(id)
        .flatMap(current -> repository.save(current.withDisplayName("Anh An"))))
        .assertNext(saved -> {
            assertThat(saved.createdBy()).isEqualTo(originalCreatedBy);
            assertThat(saved.createdDate()).isEqualTo(originalCreatedDate);
            assertThat(saved.lastModifiedBy()).isEqualTo(1012L);
            assertThat(saved.lastModifiedDate())
                    .isAfterOrEqualTo(originalLastModifiedDate);
        })
        .verifyComplete();
```

This example assumes the entity has a `withDisplayName` method returning a new instance and the test context provides auditor `1012`. If using a fixed clock, you can assert exact timestamps instead of just checking greater-than-or-equal.

### 10.4. Testing without an auditor

Test scenarios with an empty security context, anonymous user, or wrong principal type. Clearly specify whether the application allows null audit actors or requires a system actor. Tests should reflect the chosen policy rather than relying on unintended default behavior.

### 10.5. Testing direct SQL paths

If using `DatabaseClient` or modifying queries, test that audit columns are explicitly updated or that database triggers enforce the rules properly. Do not expect callbacks to run automatically on direct SQL paths.

### 10.6. Testing the clock

If using a custom `DateTimeProvider`, inject `Clock` so tests can use a fixed timestamp:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-10-05T14:12:00Z"),
        ZoneOffset.UTC);
```

This keeps tests independent of system time and allows asserting exact persisted values.

## 11. Common mistakes

### Adding annotations but forgetting to enable auditing

Without enabling `@EnableR2dbcAuditing`, auditing callbacks are not registered under that configuration. Check the Spring configuration and provider beans.

### Using synchronous AuditorAware in R2DBC

R2DBC requires `ReactiveAuditorAware<T>` to retrieve the auditor from the reactive context. Using a ThreadLocal-based synchronous provider may fail to see the security context when execution switches threads.

### Using the wrong auditor type

If the provider emits `Long` while the `@CreatedBy` property is `String`, mapping may fail or conversions may behave unexpectedly. Keep the provider's generic type consistent with audit property types.

### Accepting anonymous authentication as a real user

Some setups mark anonymous authentication as authenticated under Spring Security's API. Checking only `isAuthenticated()` may not be enough; filter out anonymous tokens or explicitly check valid principal types.

### Using a default system actor for every request

A global fallback can falsely record unauthenticated requests as system operations. Only use a system actor in clearly defined internal job/service contexts.

### Allowing clients to send createdBy or lastModifiedBy

These are server-managed metadata. Retrieve the actor from the security context or system context; never trust client-supplied values.

### Assuming DatabaseClient automatically runs auditing callbacks

Direct SQL does not go through the entity lifecycle like `save(entity)`. If audit fields must be updated, bind values explicitly or use database triggers under a unified policy.

### Overwriting auditing timestamps with database defaults/triggers

If both the application and database write timestamps, the final value depends on execution order and configuration. Choose one primary time source per column or clearly define how they coordinate.

### Using LastModifiedDate for business timestamps

When an entity is saved is not synonymous with when payment, approval, or completion occurred. Create separate business fields.

### Treating auditing as a full history

`created...` and `lastModified...` only retain the creator and most recent updater. If full history is needed, design a separate audit log/event history.

## 12. Workflow for applying auditing to a table

1. Decide whether to record actor, creation time, update time, or all four fields.
2. Choose a stable actor type, such as a `Long` or UUID user ID.
3. Declare `@CreatedBy`, `@LastModifiedBy`, `@CreatedDate`, and `@LastModifiedDate` in the entity.
4. Create corresponding columns in the schema and migrate existing data.
5. Enable `@EnableR2dbcAuditing` and declare `ReactiveAuditorAware<T>`.
6. Retrieve the actor from `ReactiveSecurityContextHolder` or a trusted system context.
7. Define policies for anonymous requests, background jobs, and system actors.
8. Choose `Instant` or a temporal type matching schema/timezone semantics.
9. Use `DateTimeProvider`/`Clock` if time control and deterministic tests are needed.
10. Ensure write operations go through the Repository/Template entity lifecycle or set audit fields explicitly for direct SQL.
11. Keep audit fields out of request models and control which fields are exposed in responses.
12. Test insert, update, empty actor, background tasks, raw SQL, and migrations.

## 13. Checklist

- [ ] Entity has the appropriate auditing annotations.
- [ ] `@EnableR2dbcAuditing` is enabled in configuration.
- [ ] `ReactiveAuditorAware<T>` bean returns the correct actor type.
- [ ] Provider retrieves identity from reactive security context or a trusted system context.
- [ ] Anonymous authentication is handled under an explicit policy.
- [ ] Background jobs have dedicated actor rules if full auditing is needed.
- [ ] `createdBy`/`lastModifiedBy` are never taken directly from request bodies.
- [ ] Schema has corresponding columns and migrations have handled existing data.
- [ ] Timestamps follow a consistent timezone convention.
- [ ] `modifyOnCreate` matches the intended meaning of LastModified fields.
- [ ] Returned entity from `save` is used when working with immutable entities.
- [ ] Direct SQL explicitly updates audit columns or uses intentional database triggers.
- [ ] Audit metadata is separated from business timestamps and full audit trails.
- [ ] Integration tests exist for insert/update and no-auditor cases.

Auditing in Spring Data R2DBC helps automatically record creators, updaters, and timestamps through the entity lifecycle. When `@EnableR2dbcAuditing` is enabled, a properly typed `ReactiveAuditorAware` is provided, and actors are retrieved from a trusted reactive context, Repositories and Templates can manage audit fields consistently. Direct SQL write paths, background tasks, and full-history requirements still need dedicated design so audit data accurately reflects the actual actors and timestamps.
