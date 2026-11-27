# Enabling Reactive Auditing with `@EnableR2dbcAuditing`

Spring Data Relational R2DBC provides auditing to automatically record who created an entity, who modified the entity, and when the creation/modification occurred. In a reactive application, auditing is enabled with `@EnableR2dbcAuditing`. This configuration registers the infrastructure required for Spring Data to apply auditing metadata during entity persistence.

Auditing typically uses four annotations on an entity:

- `@CreatedBy`: the user or principal who created the record.
- `@CreatedDate`: the timestamp when the record was created.
- `@LastModifiedBy`: the user or principal who most recently modified the record.
- `@LastModifiedDate`: the timestamp when the record was most recently modified.

An important difference in R2DBC applications is that auditor information may depend on the reactive request/security context. Therefore, the actor provider should implement `ReactiveAuditorAware<T>` and return a `Mono<T>`, rather than relying on `ThreadLocal` as in some synchronous application approaches.

Auditing is applied in the entity-saving path managed by Spring Data. A SQL statement written directly via `DatabaseClient` or `@Modifying @Query` does not automatically trigger auditing callbacks per row; if using bulk SQL, the application must explicitly update the audit columns in the statement.

## 1. What problem does auditing solve?

In many systems, each record needs to store origin and modification history metadata. For example, a `customer` table may need:

| Column | Meaning |
| --- | --- |
| `created_by` | Account that created the customer |
| `created_at` | Timestamp when the customer was created |
| `last_modified_by` | Account that most recently modified it |
| `last_modified_at` | Timestamp when it was most recently modified |

If every service assigns these fields manually, code can become repetitive and prone to omissions. Spring Data auditing moves that logic into the entity persistence lifecycle. When an entity is saved through the appropriate mapping path, the framework determines whether the entity is new or existing and updates the audit fields according to configuration.

Auditing is useful for:

- Tracing who created and modified data.
- Displaying creation/update timestamps in APIs and UIs.
- Supporting error investigation and change history at the metadata level.
- Keeping audit rules consistent across multiple repositories/services.
- Standardizing time and user sources across entity operations.

Auditing does not automatically create a full version history of every change. The four audit fields only store creation metadata and the most recent modification. If you need an immutable audit trail storing old/new values, change reasons, or business events, you need a history table, an event log, or a dedicated auditing solution.

## 2. Enabling auditing with `@EnableR2dbcAuditing`

Place the annotation on a Spring configuration class:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.r2dbc.config.EnableR2dbcAuditing;

@Configuration
@EnableR2dbcAuditing
public class R2dbcAuditingConfiguration {
}
```

When the application context starts, the annotation registers the auditing components for Spring Data R2DBC. Entities with `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, or `@LastModifiedBy` annotations will be processed in the appropriate persistence lifecycle.

If you need to specify the bean providing the auditor or time, you can reference the bean name via annotation attributes:

```java
@Configuration
@EnableR2dbcAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "dateTimeProvider"
)
public class R2dbcAuditingConfiguration {
}
```

`auditorAwareRef` points to the bean providing the auditor; `dateTimeProviderRef` points to the bean providing the time. If the application only needs timestamps and does not need to store the actor, you can enable auditing without declaring a custom `ReactiveAuditorAware`. If there are multiple beans of the same type, name and reference them explicitly to prevent Spring from choosing the wrong one.

### Commonly used configuration attributes

| Attribute | Meaning |
| --- | --- |
| `auditorAwareRef` | Name of the bean providing the current auditor |
| `dateTimeProviderRef` | Name of the bean providing the current time |
| `modifyOnCreate` | Whether to update modification metadata during creation |
| `setDates` | Whether to automatically populate auditing date/time fields |
| `mappingContextRef` | Specifies the mapping context if the application needs a custom configuration |

`modifyOnCreate` normally defaults to `true`, meaning modification fields may be set even when an entity is newly created. If you want only `createdAt`/`createdBy` on insert and want `lastModifiedAt`/`lastModifiedBy` set only from subsequent updates, you can configure `modifyOnCreate = false`.

`setDates = false` disables setting date/time fields, while auditor metadata can still be processed according to configuration. Clearly identify your requirements and verify the attributes of the Spring Data version in use.

## 3. Declaring auditing fields on an entity

Example `Customer` entity:

```java
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

    @CreatedBy
    @Column("created_by")
    private String createdBy;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @LastModifiedBy
    @Column("last_modified_by")
    private String lastModifiedBy;

    @LastModifiedDate
    @Column("last_modified_at")
    private Instant lastModifiedAt;

    // Constructors, getters, and setters.
}
```

The auditing annotations belong to `org.springframework.data.annotation`. `@Table` and `@Column` belong to Spring Data Relational mapping. Java property names can differ from SQL column names; use `@Column` to map explicitly when the schema uses snake_case or different column names.

### Database schema

The corresponding columns must exist in the table:

```sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    created_by VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE,
    last_modified_by VARCHAR(100),
    last_modified_at TIMESTAMP WITH TIME ZONE
);
```

SQL types should match Java types and the driver. For example, `Instant` is commonly used for absolute points in time; specific SQL types and codecs depend on the database. With PostgreSQL, `TIMESTAMPTZ` can be used; with other databases, choose a timestamp type with corresponding semantics.

Auditing does not automatically create or migrate columns. Schema migrations still need to declare the corresponding fields before the entity is saved.

## 4. `ReactiveAuditorAware<T>` provides who is performing the operation

To automatically populate `@CreatedBy` and `@LastModifiedBy`, Spring Data R2DBC can use a bean implementing `ReactiveAuditorAware<T>`. This interface returns a `Mono<T>` to obtain the auditor in a reactive flow.

Simple example using a fixed auditor for a test environment:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.data.domain.ReactiveAuditorAware;

@Bean
ReactiveAuditorAware<String> auditorAware() {
    return () -> Mono.just("system");
}
```

When the entity is saved, the auditing infrastructure subscribes to the auditor publisher and uses the emitted value to populate fields annotated with `@CreatedBy` or `@LastModifiedBy`. The generic type `String` must be compatible with the audit field type on the entity.

In a real application, the auditor is usually a user ID, username, service account, or principal ID. Choose a stable identifier rather than storing a complex Authentication object in the entity.

### When there is no current auditor

If a request runs in a context without a user, `ReactiveAuditorAware` can return `Mono.empty()`:

```java
@Bean
ReactiveAuditorAware<String> auditorAware() {
    return () -> resolveCurrentUser()
            .map(UserIdentity::id);
}
```

If `resolveCurrentUser()` has no auditor, the publisher completes empty. In that case, Spring Data has no value to assign to the auditor field; the field may keep its existing value or remain null depending on the entity and persistence state. Establish a clear policy for background jobs, scheduled tasks, imports, and anonymous requests.

Do not emit an empty string or fake value just to avoid null if audit data needs to accurately reflect the source actor. You can use a service account such as `batch-import` or `system` when it is a valid business actor.

## 5. Retrieving the auditor from the Spring Security reactive context

In a Spring Security WebFlux application, Authentication information is stored in the reactive security context. You can implement `ReactiveAuditorAware<String>` using `ReactiveSecurityContextHolder`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

@Bean
ReactiveAuditorAware<String> auditorAware() {
    return () -> ReactiveSecurityContextHolder.getContext()
            .map(securityContext -> securityContext.getAuthentication())
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName);
}
```

This code retrieves the Authentication from the Reactor Context, checks that it is authenticated, and uses `getName()` as the auditor. In applications with anonymous authentication, decide whether an anonymous principal is considered a valid actor; you can filter further by Authentication type or specific principal.

If the entity stores a user ID as a UUID or Long, map the principal to the corresponding ID:

```java
@Bean
ReactiveAuditorAware<UUID> auditorAware() {
    return () -> ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getPrincipal)
            .cast(ApplicationPrincipal.class)
            .map(ApplicationPrincipal::userId);
}
```

`ApplicationPrincipal` is the application's principal type. If Authentication has a principal of the wrong type, `cast` can cause the publisher to emit an error. You can use `ofType(ApplicationPrincipal.class)` or check the type before converting to handle multiple principal types more safely.

### Why not use synchronous `SecurityContextHolder`?

In WebFlux, you should not default to retrieving the user from `SecurityContextHolder.getContext()` based on `ThreadLocal`. A reactive pipeline can switch threads; the security context is propagated via Reactor Context. `ReactiveSecurityContextHolder` is the appropriate API to access the security context in a reactive flow.

If `ReactiveAuditorAware` returns `Mono.empty()` while the request is authenticated, check:

- Whether the security filter chain puts the security context into the reactive context.
- Whether the repository save runs in the same reactive pipeline as the request.
- Whether any code manually calls `subscribe()` or switches to a callback executor outside Reactor.
- Whether a new subscription is created that breaks context propagation.
- Whether the principal has the expected type and authenticated state.

## 6. Configuring `DateTimeProvider` and `Clock`

If no custom provider is declared, auditing uses Spring Data's default time source. The application can provide a `DateTimeProvider` to control time, timezone, and testing.

Example using `Clock`:

```java
import java.time.Clock;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.data.auditing.DateTimeProvider;

@Bean
Clock auditingClock() {
    return Clock.systemUTC();
}

@Bean
DateTimeProvider dateTimeProvider(Clock auditingClock) {
    return () -> Optional.of(auditingClock.instant());
}
```

`DateTimeProvider` returns `Optional<TemporalAccessor>`. `Instant` implements `TemporalAccessor`, so it can be used as the time source. `Clock.systemUTC()` helps keep time conventions consistent and avoids depending on the default timezone of the host running the application.

Linking beans to the annotation:

```java
@Configuration
@EnableR2dbcAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "dateTimeProvider"
)
public class R2dbcAuditingConfiguration {
}
```

If no auditor is needed, `auditorAwareRef` can be omitted; if no custom time is needed, `dateTimeProviderRef` can be omitted.

### Using fixed time in tests

You can replace the `Clock` bean with `Clock.fixed(...)` in integration tests:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-15T10:00:00Z"),
        ZoneOffset.UTC
);
```

Then `@CreatedDate` and `@LastModifiedDate` are assigned according to a known timestamp, ensuring assertions do not depend on test execution time. When testing an update, change the clock to a later timestamp or use a controllable clock to verify the timestamp updates properly.

## 7. How do `@CreatedDate` and `@LastModifiedDate` differ?

These two annotations represent two different points in time:

| Annotation | On creation | On entity update |
| --- | --- | --- |
| `@CreatedDate` | Records the creation time | Preserves the original creation value |
| `@LastModifiedDate` | Set when `modifyOnCreate` is enabled | Updates the modification time |

Example:

1. 10:00: customer is inserted; `createdAt = 10:00`.
2. 10:30: customer is updated; `createdAt` remains 10:00, `lastModifiedAt = 10:30`.
3. 11:15: customer is updated again; `createdAt` remains 10:00, `lastModifiedAt = 11:15`.

Do not use `@LastModifiedDate` instead of `@CreatedDate` if the API needs to preserve the original creation time. On creation, the value of `lastModifiedAt` depends on `modifyOnCreate`; if this attribute is disabled, the modification field may not be set on insert.

## 8. `@CreatedBy` and `@LastModifiedBy`

The two auditor annotations have similar semantics to the timestamp annotations:

| Annotation | On creation | On entity update |
| --- | --- | --- |
| `@CreatedBy` | Records the creating actor | Preserves the original creating actor |
| `@LastModifiedBy` | Set when `modifyOnCreate` is enabled | Updates the most recent modifying actor |

For example, a customer created by `alice` and later modified by `bob`:

```text
created_by       = alice
last_modified_by = bob
```

`@CreatedBy` should not be changed to `bob` just because the entity is updated. This field retains the original creator. `@LastModifiedBy` reflects the actor of the most recent modification.

If there is no auditor in the context, the auditor fields do not automatically get a reliable default value. The policy can be to allow null, use a system actor for background jobs, or require authentication before performing operations.

## 9. `modifyOnCreate` and `setDates`

You can adjust metadata creation behavior:

```java
@Configuration
@EnableR2dbcAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "dateTimeProvider",
        modifyOnCreate = false,
        setDates = true
)
public class R2dbcAuditingConfiguration {
}
```

With `modifyOnCreate = false`, "last modified" metadata is not set merely because the entity is being newly created. `createdBy` and `createdDate` are still used for the creation state if corresponding providers exist. When the entity is updated, the modification fields are then updated.

With `setDates = false`, auditing does not automatically set date/time fields. This can be suitable when time is managed by database triggers or another system. When disabled, do not expect `@CreatedDate`/`@LastModifiedDate` to be automatically populated solely from the field annotations.

Verify the configuration in integration tests rather than inferring solely from attribute names. Some differences may depend on the Spring Data version and how the entity is saved.

## 10. Auditing runs in the entity lifecycle

Spring Data R2DBC auditing is integrated into the entity persistence process. When an entity goes through a repository or appropriate entity-oriented operation, the auditing callback can determine its new/existing state and assign metadata before the entity is written.

Example:

```java
return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
        .flatMap(customer -> {
            customer.setName(newName);
            return customerRepository.save(customer);
        });
```

When `save` executes, the auditing callback can update `lastModifiedBy` and `lastModifiedAt` based on the auditor/time provider. Calling the setter `setName` by itself neither triggers auditing nor writes data to the database.

### Entity operations that typically go through auditing

Spring Data entity-oriented operations such as `repository.save(entity)` or `R2dbcEntityTemplate` entity insert/update can trigger lifecycle callbacks. Exact behavior also depends on the API and version, so test the write path the application actually uses.

### Direct SQL does not automatically run auditing callbacks

Example:

```java
databaseClient.sql("""
        UPDATE customer
        SET name = :name
        WHERE id = :id
        """)
    .bind("name", newName)
    .bind("id", id)
    .fetch()
    .rowsUpdated();
```

This statement does not load an entity and does not go through entity auditing callbacks. `lastModifiedAt` and `lastModifiedBy` will not be updated automatically. If direct SQL is an intentional choice, include the audit columns in the statement:

```java
databaseClient.sql("""
        UPDATE customer
        SET name = :name,
            last_modified_at = :modifiedAt,
            last_modified_by = :modifiedBy
        WHERE id = :id
        """)
    .bind("name", newName)
    .bind("modifiedAt", clock.instant())
    .bind("modifiedBy", actorId)
    .bind("id", id)
    .fetch()
    .rowsUpdated();
```

Similarly, bulk updates via `@Modifying @Query`, `DatabaseClient`, or fluent update do not automatically invoke auditing callbacks per row. If using bulk SQL, the application needs to update audit metadata manually or use a well-designed database trigger/policy.

## 11. How new/existing entity detection affects auditing

Auditing needs to know whether an entity is being newly created or modified. Spring Data Relational determines entity state according to newness detection rules: `Persistable.isNew()` if the entity implements `Persistable`; otherwise `@Version` takes precedence; if there is no version, `@Id` is used.

If newness is detected incorrectly, both the INSERT/UPDATE choice and the created/modified metadata may not behave as expected.

Example entity using an assigned ID:

```java
@Table("customer")
public class Customer implements Persistable<UUID> {

    @Id
    private UUID id;

    @Transient
    private boolean newEntity;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant lastModifiedAt;

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }
}
```

This is only a conceptual example; constructors/callbacks must set `newEntity` properly and transition its state after insert. Spring Data Relational's `@Transient` excludes the property from persistence mapping. Do not use `Persistable` if you do not need custom newness logic.

For entities with an ID assigned before insert, looking only at the ID may cause the framework to treat the entity as existing. If an entity is new but `isNew()` returns false, the operation may take the update path and auditing will not treat it as a new creation. Check newness detection when audit metadata is missing or `createdAt` changes unexpectedly.

## 12. Auditing with immutable entities

Immutable entities do not allow direct field mutation. Spring Data can create a new instance through a constructor/persistent creator or property accessor when callbacks add audit metadata. Therefore, audit fields must be present in the constructor or wither/property mapping mechanism that Spring Data can use.

Record example:

```java
@Table("customer")
public record Customer(
        @Id Long id,
        String name,
        @CreatedBy String createdBy,
        @CreatedDate Instant createdAt,
        @LastModifiedBy String lastModifiedBy,
        @LastModifiedDate Instant lastModifiedAt
) {
}
```

A record has a canonical constructor containing the audit fields. When Spring Data creates an instance after the callback, the audit values can be passed via the constructor according to mapping metadata. Use the entity emitted from `save` because it reflects the post-persistence/callback instance and may contain a newly generated ID/version.

For custom immutable classes, ensure an appropriate constructor exists and property names/types are recognized by Spring Data. If callbacks cannot update fields due to the entity design, check constructor mapping, property accessors, and wither implementation.

## 13. Auditing in background tasks and scheduled jobs

Not all persistence operations originate from an HTTP request with a logged-in user. Background tasks may run in schedulers, consumers, or batch imports without a reactive security context.

You can provide a system actor in those flows. One approach is placing the actor value into the pipeline's Reactor Context:

```java
return importCustomers()
        .contextWrite(context -> context.put("auditActor", "customer-import-job"));
```

Then `ReactiveAuditorAware` reads the context:

```java
@Bean
ReactiveAuditorAware<String> auditorAware() {
    return () -> Mono.deferContextual(context ->
            Mono.justOrEmpty(context.<String>getOrEmpty("auditActor"))
    );
}
```

In a real application, you can prioritize the user principal when a security context is present and fall back to the job actor when the pipeline has the `auditActor` key. Define a clear priority order to avoid accidentally assigning `system` to a request with a real user.

When there is no actor, you can return `Mono.empty()` and allow the auditor field to be null, or require every write operation to have an actor. This decision should be reflected in the schema (`NOT NULL` vs. nullable) and tests.

Do not rely on `ThreadLocal` to pass the actor through a reactive pipeline. Use `ReactiveAuditorAware` and the Reactor Context or reactive security context accordingly.

## 14. Separating auditor by tenant or request source

Some systems store both actor and tenant. `ReactiveAuditorAware` is only responsible for returning the auditor value; tenant metadata can be handled separately via service/domain or callbacks depending on the design.

For example, if the auditor needs both user and tenant:

```java
public record AuditActor(String userId, String tenantId) {
}
```

The entity can store two separate fields `created_by` and `created_tenant`, or store a stable actor identifier. Avoid serializing the entire SecurityContext into an audit column.

If `ReactiveAuditorAware` reads the tenant from Reactor Context, ensure the context is set at the request boundary and is not lost when code transitions to a callback API outside Reactor. R2DBC operations must remain within the reactive chain so the auditing callback can read the context.

## 15. Callback ordering and coordinating with custom callbacks

Spring Data R2DBC has lifecycle callbacks for points during entity reading/writing. Auditing is integrated as a callback to assign metadata. Applications can also declare custom callbacks to normalize fields, generate codes, or apply rules before saving.

Custom callback example:

```java
@Component
public class CustomerNormalizeCallback
        implements BeforeConvertCallback<Customer> {

    @Override
    public Customer onBeforeConvert(Customer customer) {
        customer.setName(customer.getName().trim());
        return customer;
    }
}
```

This is a synchronous callback illustrating a mutable entity; a corresponding reactive callback can be used if asynchronous processing is required. When combining custom callbacks with auditing, pay attention to execution order and do not overwrite audit fields after auditing has set them. If a callback depends on ordering, use the ordering mechanism supported in your Spring Data version rather than relying on bean initialization order.

Do not execute blocking database queries inside a callback. Callbacks belong to the reactive persistence path; if asynchronous operations are needed, use the reactive callback API provided by the corresponding Spring Data version.

## 16. Auditing does not replace change history

The `created*` and `lastModified*` fields only tell you the first and most recent actor/timestamp. They do not retain intermediate modifications.

Example:

```text
10:00 alice creates customer, name = "Lan"
10:30 bob changes name = "Lan Nguyen"
11:15 carol changes name = "Lan N."
```

After the final update, the entity may only retain:

```text
created_by       = alice
created_at       = 10:00
last_modified_by = carol
last_modified_at = 11:15
```

Information about `bob` and previous name values is no longer present in these four fields. If you need to store every change, you can design an audit history table:

```sql
CREATE TABLE customer_audit (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    actor_id VARCHAR(100),
    action VARCHAR(50) NOT NULL,
    changed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    old_value JSONB,
    new_value JSONB
);
```

This table is a PostgreSQL example; JSON types and data structures depend on the database. Recording history should be coordinated in a transaction with the entity change if you require preventing a state where one side is written and the other is not. For direct SQL/bulk operations, record audit history explicitly or use an appropriate trigger/outbox.

## 17. Auditing and bulk updates

When performing a bulk update with SQL:

```sql
UPDATE customer
SET status = 'INACTIVE'
WHERE last_login < :cutoff;
```

Spring Data does not instantiate entities for each affected row and does not run auditing callbacks for each entity. If metadata needs to be updated:

```sql
UPDATE customer
SET status = :status,
    last_modified_at = :modifiedAt,
    last_modified_by = :actor
WHERE last_login < :cutoff;
```

Here a single timestamp/actor is used for the entire batch. If different actors or timestamps are required per row, an appropriate SQL design or entity-by-entity processing is needed.

If a database trigger updates timestamps automatically, decide which fields are owned by the database and which are owned by Spring Data auditing. Avoid having both callbacks and triggers write to the same column using different clocks, because the final value may depend on execution order.

## 18. Complete illustrative configuration

Comprehensive example configuring the auditor from the reactive security context and UTC time:

```java
@Configuration
@EnableR2dbcAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "dateTimeProvider",
        modifyOnCreate = true,
        setDates = true
)
public class R2dbcAuditingConfiguration {

    @Bean
    ReactiveAuditorAware<String> auditorAware() {
        return () -> ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication())
                .filter(Authentication::isAuthenticated)
                .map(Authentication::getName);
    }

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider dateTimeProvider(Clock auditingClock) {
        return () -> Optional.of(auditingClock.instant());
    }
}
```

Key imports:

```java
import java.time.Clock;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.data.r2dbc.config.EnableR2dbcAuditing;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
```

This configuration assumes the application uses Spring Security WebFlux and has a principal compatible with `Authentication.getName()`. If not using Spring Security, replace `ReactiveAuditorAware` with the application's actor source. If no auditor is needed, omit the bean and the `auditorAwareRef` attribute.

## 19. Testing auditing

You should test using an R2DBC repository and a real database/driver, because the goal is to verify that callbacks are integrated into the actual persistence path.

### Testing timestamps on insert

With a fixed `Clock`:

```java
Instant expected = Instant.parse("2026-01-15T10:00:00Z");

StepVerifier.create(customerRepository.save(new Customer("Lan")))
        .assertNext(saved -> {
            assertThat(saved.getCreatedAt()).isEqualTo(expected);
            assertThat(saved.getLastModifiedAt()).isEqualTo(expected);
        })
        .verifyComplete();
```

Asserting `lastModifiedAt` on insert assumes `modifyOnCreate = true`. If configured as false, do not expect this field to be set on creation.

### Testing the actor

With a test context having auditor `test-user`, assert:

```java
assertThat(saved.getCreatedBy()).isEqualTo("test-user");
assertThat(saved.getLastModifiedBy()).isEqualTo("test-user");
```

If using `ReactiveSecurityContextHolder`, you can create a security context in the test via Spring Security's test support or set the appropriate context on the publisher. Do not just mock `ReactiveAuditorAware` if the goal is to verify that the request context actually propagates to the callback.

### Testing that updates preserve created fields

1. Insert an entity with actor `alice` and time `t1`.
2. Change the context actor to `bob` and clock to `t2`.
3. Read the entity, modify a property, and call `save`.
4. Assert `createdBy = alice`, `createdAt = t1`, `lastModifiedBy = bob`, `lastModifiedAt = t2`.

This test verifies the auditor source, DateTimeProvider, and created/modified semantics.

### Testing that direct SQL does not automatically trigger auditing

Perform an update with `DatabaseClient` without updating audit columns; re-read the entity and confirm `lastModifiedAt`/`lastModifiedBy` did not change automatically. Then update the SQL to explicitly set these columns and verify the result. This test helps avoid the false assumption that auditing annotations apply to every SQL statement in the application.

## 20. Common mistakes

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| `createdAt` or `lastModifiedAt` is always null | `@EnableR2dbcAuditing` not enabled, missing field annotation, or unmapped column | Check configuration, annotations, and schema |
| `@CreatedBy` is not populated | Missing `ReactiveAuditorAware` or auditor publisher is empty | Check bean, field type, and context |
| Auditor is always anonymous | Security filter/context uses an anonymous principal marked as authenticated | Filter principal types or define an actor policy |
| Auditor exists in request but is lost in repository callback | Detached subscription or leaving the reactive context | Chain publishers; avoid standalone `subscribe()`/callback executors |
| Type mismatch error when assigning auditor | `ReactiveAuditorAware<T>` generic type does not match field | Use consistent ID/principal types |
| `createdAt` changes on update | Entity treated as new or callback/custom code overwrites field | Check `isNew`, `@Version`, `@Id`, and callbacks |
| `lastModifiedAt` does not change on insert | `modifyOnCreate = false` | Verify configuration and business expectations |
| Direct update does not update audit fields | SQL bypasses the entity lifecycle | Set audit columns in SQL or use entity save |
| Timestamp timezone offset mismatch | Using local time/default Clock or incompatible SQL type | Standardize on UTC and check codec/database type |
| Immutable entity does not receive audit values | Constructor/persistent creator missing properties or mapping not recognized | Check constructor, property accessors, and returned entity |
| CreatedBy overwritten on update | Wrong field used or custom callback overwrites it | Separate created and last-modified metadata |
| Audit column does not exist | Auditing does not auto-generate schema | Add migrations for audit columns |

## 21. Workflow for enabling auditing in an application

1. Identify the information to store: actor, timestamp, or both.
2. Add the corresponding columns to the schema via migrations.
3. Add `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, `@LastModifiedDate` to the entity.
4. Enable `@EnableR2dbcAuditing` in a component-scanned configuration.
5. If an actor is needed, declare `ReactiveAuditorAware<T>` with the appropriate type.
6. If time control is needed, declare a `DateTimeProvider` based on `Clock`.
7. Decide `modifyOnCreate` and `setDates` according to desired semantics.
8. Ensure repository/template entity operations go through the same Spring Data infrastructure.
9. For direct SQL/bulk updates, explicitly update audit fields or use a designed database mechanism.
10. Test insert, update, missing actor, background jobs, direct SQL, and immutable entities with integration tests.

## 22. Key takeaways

- Enable reactive auditing with `@EnableR2dbcAuditing` in Spring configuration.
- `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, and `@LastModifiedDate` mark audit fields on the entity.
- `ReactiveAuditorAware<T>` provides the actor as a `Mono<T>`, fitting reactive security/context.
- In WebFlux, retrieve the principal via `ReactiveSecurityContextHolder`; do not rely on synchronous `ThreadLocal`/`SecurityContextHolder`.
- `DateTimeProvider` provides the time; use `Clock.systemUTC()` to standardize and `Clock.fixed()` for testing.
- `modifyOnCreate` determines whether modification metadata is set on insert; `setDates` controls automatic population of date/time fields.
- Auditing runs in the entity persistence lifecycle managed by Spring Data; plain setters do not write to the database.
- `DatabaseClient`, `@Modifying @Query`, and bulk SQL do not automatically run auditing callbacks per entity; audit columns must be updated explicitly.
- Newness detection (`Persistable`, `@Version`, `@Id`) affects how created/modified is classified.
- With immutable entities, ensure constructor/property mapping can receive audit values and use the resulting entity from `save`.
- Auditing only stores creation and most recent modification metadata; if you want full history, you need an audit table/event log/outbox or a separate solution.
- Test with a real database/driver to verify callbacks, security context, timestamps, updates, and direct SQL behavior.

When enabling reactive auditing in Spring Data R2DBC, configure `@EnableR2dbcAuditing`, provide a time source and `ReactiveAuditorAware` when an actor is needed, and annotate the fields on the entity. Audit values are applied when the entity goes through the Spring Data persistence lifecycle. Direct SQL statements still need to update metadata manually, and the actor source in a WebFlux application must be retrieved from the reactive context so it does not depend on the current thread.
