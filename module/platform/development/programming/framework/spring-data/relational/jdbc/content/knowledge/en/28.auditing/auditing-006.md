# Auditing with Immutable Entities, New Objects, and Multiple Write Sources

In **Spring Data Relational JDBC**, auditing helps record who created an aggregate, when it was created, and when it was last modified. Commonly used fields are `createdBy`, `createdDate`, `lastModifiedBy`, and `lastModifiedDate`. Spring Data JDBC can populate these fields automatically when an aggregate is saved via a repository or Spring Data persistence APIs.

Auditing requires special attention when domain models are immutable, when the application assigns IDs to new objects itself, and when data can be written through multiple paths. Spring must correctly identify new objects to choose an insert and assign creation metadata; with immutable entities, audit values must be carried onto a new instance; and SQL statements executed outside Spring Data JDBC's lifecycle will not automatically trigger auditing callbacks.

This lesson explains how to enable auditing, provide an auditor and clock, handle immutable objects with withers, detect new objects via IDs, `@Version`, or `Persistable`, and design auditing when repositories, `JdbcAggregateTemplate`, direct SQL, or external systems write data concurrently.

## 1. Auditing Fields in Spring Data JDBC

Spring Data provides four common annotations:

| Annotation | Meaning | When Updated |
|---|---|---|
| `@CreatedBy` | Person or agent creating the aggregate | When the aggregate is identified as new |
| `@CreatedDate` | Timestamp when the aggregate was created | When the aggregate is identified as new |
| `@LastModifiedBy` | Person or agent who last modified it | On creation or modification, depending on configuration |
| `@LastModifiedDate` | Timestamp of the last modification | On creation or modification, depending on configuration |

These annotations live in the `org.springframework.data.annotation` package.

Example mutable aggregate:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    private OrderStatus status;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedDate;
}
~~~

Spring Data JDBC uses the auditing infrastructure to populate annotated properties. These properties are still persisted columns in the database, so the schema must include the corresponding columns with types compatible with the Java types.

## 2. Enabling Auditing for Spring Data JDBC

To activate auditing, add `@EnableJdbcAuditing` to configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing
public class JdbcAuditingConfiguration {
}
~~~

The annotation resides in the `org.springframework.data.jdbc.repository.config` package.

When this configuration is enabled, Spring Data JDBC registers the auditing infrastructure, including `AuditingEntityCallback`. This callback participates in the aggregate write lifecycle and populates auditing fields before the data is converted into write statements.

### 2.1. Auditing Callback Runs Before Writing

Conceptual flow:

~~~mermaid
flowchart TD
    A["Repository.save(aggregate)"] --> B["Spring Data determines whether aggregate is new or existing"]
    B --> C["AuditingEntityCallback"]
    C --> D["Assign Created* / LastModified*"]
    D --> E["BeforeConvert and mapping"]
    E --> F["Generate INSERT or UPDATE statement"]
    F --> G["Database stores audit columns"]
~~~

Key point: auditing is not a task that runs after SQL has finished writing. Audit values must be populated before Spring Data builds the write data, so they are present in the INSERT or UPDATE statement.

### 2.2. Do Not Confuse with AfterConvertCallback

`AfterConvertCallback` runs after relational data is converted into an object during a read. Auditing for writes uses a lifecycle callback prior to conversion for saving. The two callbacks serve opposite directions:

- `AfterConvertCallback`: enriches data after loading an aggregate.
- `AuditingEntityCallback`: populates audit metadata before the aggregate is converted into write data.

If you want `createdDate` or `lastModifiedDate` saved to the database, do not use a post-read callback to assign them.

## 3. Providing the Actor via AuditorAware

`@CreatedBy` and `@LastModifiedBy` need to know who is performing the operation. Spring Data obtains that information from an `AuditorAware<T>` bean.

Example application using Spring Security and storing usernames as `String`:

~~~java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Configuration
@EnableJdbcAuditing(auditorAwareRef = "auditorAware")
public class JdbcAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.ofNullable(
                SecurityContextHolder.getContext().getAuthentication()
            )
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName);
    }
}
~~~

`AuditorAware<String>` must be compatible with the property types annotated with `@CreatedBy` and `@LastModifiedBy`. If the aggregate uses `UUID` for user IDs, the auditor must also return `UUID`.

When there is no current user, `AuditorAware` can return `Optional.empty()`. In that case, auditor fields are not filled with a dummy user. Date fields can still be updated from `DateTimeProvider`.

In applications with anonymous authentication, exclude the anonymous principal if you do not want `anonymousUser` stored as a real user. The exact filtering rule depends on the Spring Security configuration.

### 3.1. Recording Actors for Batches and Background Tasks

Not every write operation originates from an HTTP request. Examples include:

- Nightly data imports.
- Order synchronization schedulers.
- Message listeners handling events.
- Administrative tasks or migrations.

These flows may lack a `SecurityContext`. Define a clear system agent, such as `order-import-service` or `scheduler`, if business requirements call for knowing the write source.

Do not default every unauthenticated case to a specific real user. Auditor values must accurately reflect the performing agent.

## 4. Providing Time with DateTimeProvider and Clock

Without custom configuration, Spring Data uses the default time source. The application can provide a `DateTimeProvider` to control the clock and timezone.

Example using UTC:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing(dateTimeProviderRef = "auditingDateTimeProvider")
public class JdbcAuditingConfiguration {

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

`@CreatedDate` and `@LastModifiedDate` can use temporal types supported by Spring Data such as `Instant` or compatible `java.time` types. Pick a consistent convention, typically storing UTC instants and converting to display timezones in the presentation layer.

The clock can be replaced with a fixed clock in tests to verify exact audit values regardless of when the test runs.

## 5. Auditing with Immutable Entities

With mutable entities, auditing can assign values via setters or property accessors. With immutable entities, fields are typically `final` and there are no setters. Spring Data then needs a way to create a new instance containing the newly assigned audit values.

Spring Data mapping supports immutable objects through constructors and property accessors. A common way to update a property after object creation is providing a **wither**: a method returning a new instance with exactly one property changed.

### 5.1. Immutable Aggregate Example

Example using Lombok `@Value` and `@With` to generate an immutable class with withers:

~~~java
import java.time.Instant;

import lombok.Value;
import lombok.With;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Value
@With
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    Long id;

    String orderNumber;

    OrderStatus status;

    @CreatedBy
    String createdBy;

    @CreatedDate
    Instant createdDate;

    @LastModifiedBy
    String lastModifiedBy;

    @LastModifiedDate
    Instant lastModifiedDate;

    @Version
    Long version;
}
~~~

`@Value` generates final fields, a constructor, and getters; `@With` generates methods such as `withCreatedBy(...)`, `withCreatedDate(...)`, `withLastModifiedBy(...)`, `withLastModifiedDate(...)`, and `withVersion(...)`.

Spring Data can use property accessors to apply audit values and obtain the new instance. For hand-written classes instead of Lombok, provide the corresponding withers or an immutable object-creation strategy compatible with the mapping in the Spring Data version being used.

### 5.2. Why Do Withers Matter?

Suppose auditing needs to update two properties:

1. `createdBy = "alice"`.
2. `createdDate = 2026-11-13T08:00:00Z`.

With an immutable object, fields cannot be mutated directly. The property accessor can invoke withers to produce each successive object:

~~~text
Initial PurchaseOrder
        |
        +-- withCreatedBy("alice")
        v
PurchaseOrder with createdBy
        |
        +-- withCreatedDate(timestamp)
        v
Complete PurchaseOrder
~~~

Callbacks must continue working with the new instance after each change. Spring Data property accessors handle swapping this instance during mapping; application code does not need to call every wither manually before `save()`.

If an immutable class lacks setters, withers, or compatible constructor/property mapping to update audit properties, values may not be applied as intended. Verify via repository integration tests rather than only checking the object's constructor.

### 5.3. Constructors of Immutable Entities

Spring Data needs to know how to instantiate an aggregate from read data. For an immutable class, the constructor or persistence creator must accept the required persistent properties. Properties marked `@Transient` are not database columns and should not be treated as persisted fields.

Do not add arbitrary extra constructors assuming mapping will always pick the right one. When multiple constructors exist, declare the persistence creator using the mechanism supported by your Spring Data version, or keep a single clear constructor.

## 6. How Are New Objects Identified?

Auditing needs to know whether an aggregate is new or existing to decide between `markCreated` and `markModified`. Spring Data JDBC uses an entity newness detection strategy. This decision also governs whether repository `save()` performs an INSERT or an UPDATE.

Common rules:

1. If the entity has a `@Version` property, a `null` version value generally indicates a new entity.
2. If there is no version property, a `null` ID generally indicates a new entity.
3. If the entity implements `Persistable`, the `isNew()` method provided by the entity is used to determine newness.

Exact rules also depend on mapping and Spring Data version, and special care is needed when the application assigns IDs itself.

### 6.1. Database-Generated IDs

With auto-generated IDs, a new object normally has a `null` ID:

~~~java
PurchaseOrder order = new PurchaseOrder(
    null,
    "SO-100",
    OrderStatus.DRAFT,
    null,
    null,
    null,
    null,
    null
);
~~~

Without another newness strategy, Spring Data identifies the object as new, selects INSERT, and auditing populates the `@Created*` fields.

### 6.2. Application-Assigned IDs

If the application assigns a UUID or numeric ID before saving:

~~~java
UUID id = UUID.randomUUID();
~~~

then the ID is already non-null even though the row does not exist yet. Without `@Version` or `Persistable`, Spring Data may consider the object existing and choose UPDATE.

When the update finds no matching row, the operation does not automatically fall back to an insert. Auditing may also enter the modification branch instead of the creation branch.

For entities with pre-assigned IDs, declare how new objects are detected explicitly.

## 7. Using @Version to Identify New Objects with Pre-Assigned IDs

One option is adding a `@Version` property using a wrapper type, such as `Long`:

~~~java
@Id
Long id;

@Version
Long version;
~~~

When creating a new object, leave `version == null`:

~~~java
PurchaseOrder newOrder = new PurchaseOrder(
    UUID.randomUUID(),
    "SO-101",
    OrderStatus.DRAFT,
    null,
    null,
    null,
    null,
    null
);
~~~

With a null version, Spring Data can identify the entity as new even though the ID already has a value. After insert, the framework assigns the initial version. Subsequent updates use version for optimistic locking.

`@Version` serves two related but distinct roles:

- Supporting new vs. existing state detection.
- Detecting concurrent updates via optimistic locking.

Do not use primitive `long` if you need `null` to represent an unassigned version state. Wrapper types distinguish an unpersisted version from valid version numbers.

With immutable entities, Spring Data must also have a way to update the version, such as the `withVersion(...)` wither generated by `@With`.

## 8. Using Persistable When Controlling isNew()

If you prefer not to use `@Version` or have custom newness rules, the entity can implement `Persistable<ID>`:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.domain.Persistable;

public class ImportedOrder implements Persistable<UUID> {

    @Id
    private final UUID id;

    @Transient
    private boolean newEntity;

    public ImportedOrder(UUID id) {
        this(id, true);
    }

    private ImportedOrder(UUID id, boolean newEntity) {
        this.id = id;
        this.newEntity = newEntity;
    }

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public ImportedOrder withNewEntity(boolean value) {
        return new ImportedOrder(id, value);
    }
}
~~~

The `newEntity` property is annotated with `@Transient` so no database column is created for it. `isNew()` returns the application-managed state.

After a successful insert, the state must flip to false so the next `save()` is recognized as an update. For mutable objects, the application can update the flag after saving; for immutable objects, you can use a wither in an after-save callback or return the persisted instance in the application layer.

Example after-save callback for an immutable type:

~~~java
@Component
public class ImportedOrderAfterSaveCallback
        implements AfterSaveCallback<ImportedOrder> {

    @Override
    public ImportedOrder onAfterSave(ImportedOrder aggregate) {
        return aggregate.withNewEntity(false);
    }
}
~~~

Ensure `newEntity` is recognized as transient by mapping and that the callback returns the new instance. If managing state in the service, replace the object with the result returned from save rather than continuing to use an instance still reporting `isNew() == true`.

`Persistable` is a useful tool, though it increases lifecycle-management responsibility on the application. If `@Version` satisfies the newness-detection need, it is usually worth considering first.

## 9. How Auditing Is Applied on Creation and Update

Once auditing is enabled, Spring Data uses newness status to decide how to populate fields:

| Field | On Creation | On Update |
|---|---|---|
| `@CreatedBy` | Sets current auditor | Retains creation value |
| `@CreatedDate` | Sets creation time | Retains creation value |
| `@LastModifiedBy` | Set on creation by default if `modifyOnCreate = true` | Sets current auditor |
| `@LastModifiedDate` | Set on creation by default if `modifyOnCreate = true` | Sets current time |

`modifyOnCreate` defaults to `true`. If business rules require `lastModified*` fields to have values only after the first modification, you can configure:

~~~java
@Configuration
@EnableJdbcAuditing(
    auditorAwareRef = "auditorAware",
    modifyOnCreate = false
)
public class JdbcAuditingConfiguration {
}
~~~

Then `@LastModifiedBy` and `@LastModifiedDate` are not populated on initial creation under this configuration. Choose semantics consistent with the application's reports and APIs.

If `AuditorAware` returns `Optional.empty()`, auditor fields have no user to assign. This does not mean date fields are skipped as well.

## 10. Multiple Write Sources: Which Callbacks Run?

Spring Data JDBC auditing is tied to Spring Data's persistence lifecycle. Not every SQL statement modifying the database goes through that lifecycle.

| Write Source | Spring Data JDBC Auditing Callback |
|---|---|
| Repository `save()` | Yes |
| `JdbcAggregateTemplate.insert()` / `update()` / `save()` | Yes, as it uses Spring Data aggregate infrastructure |
| Derived repository queries for reading | Does not write audit fields simply for reading |
| `@Modifying @Query` executing direct SQL | Do not assume aggregate callbacks are executed |
| `JdbcTemplate` / `NamedParameterJdbcTemplate` | Does not automatically run auditing entity callbacks |
| Stored procedures or SQL scripts | Does not automatically run callbacks |
| Import tools or external apps writing to the DB | Does not run this Spring app's callbacks |
| Database triggers | Executed by the database, independent of Spring callbacks |

This is especially important when multiple writers modify the same table. If one application uses a repository while a batch job uses `JdbcTemplate`, audit columns can be updated differently or missed on one write path.

### 10.1. Repository and JdbcAggregateTemplate

Both APIs share Spring Data JDBC's aggregate mapping infrastructure. When saving an aggregate through a repository or `JdbcAggregateTemplate`, Spring Data lifecycle callbacks are applied, so auditing can populate the corresponding fields.

Example:

~~~java
repository.save(order);
~~~

or:

~~~java
jdbcAggregateTemplate.insert(order);
jdbcAggregateTemplate.update(order);
~~~

These operations still require `@EnableJdbcAuditing`, `AuditorAware`, and appropriate audit properties.

### 10.2. Direct SQL Does Not Run Auditing Callbacks Automatically

Example:

~~~java
namedParameterJdbcTemplate.update("""
    UPDATE purchase_orders
    SET status = :status
    WHERE id = :id
    """, params);
~~~

The statement above modifies the database directly. It does not persist an aggregate through repository save and does not automatically invoke `AuditingEntityCallback`. If audit fields must be updated, do so explicitly in SQL:

~~~sql
UPDATE purchase_orders
SET status = :status,
    last_modified_by = :actor,
    last_modified_date = :modifiedAt
WHERE id = :id;
~~~

Or delegate that task to a database trigger. Choose one primary responsible source to prevent the two mechanisms from overwriting each other's values.

## 11. Choosing an Auditing Strategy When Multiple Applications Write

If multiple applications, batch jobs, or admin tools write to the same table, there are two main approaches.

### 11.1. Application-Layer Auditing

Each writer must adhere to a write contract:

- All Spring Data JDBC flows use auditing callbacks.
- All direct SQL flows pass actor and timestamp themselves.
- Imports/batches supply an explicit system actor.
- Other applications follow the same column and data type conventions.

The advantage is that actor logic integrates with the security context and domain/application layer. The drawback is that every writer must follow the rules; an external script or application might forget.

### 11.2. Database-Layer Auditing

Database triggers can update `created_date` or `last_modified_date` for every write source, regardless of whether the operation comes from Spring Data or another application.

Conceptual example:

~~~sql
-- Trigger syntax depends on the database management system.
-- A BEFORE UPDATE trigger can set:
-- NEW.last_modified_date = CURRENT_TIMESTAMP
~~~

Advantages:

- Every write to the table goes through the same database rules.
- Independent of whether a specific application runs Spring callbacks.
- Useful when multiple services or administrative tools write concurrently.

Limitations:

- Trigger syntax differs across databases.
- The database needs to know who the actor is; `CURRENT_USER` may just be a shared connection account.
- A mechanism is needed to pass the actor into session/database context if you want to store the application user.
- Trigger values can conflict with values sent down by application auditing.
- Auditing logic lives in the database and must be managed alongside schema migrations.

### 11.3. Do Not Let Two Sources Own the Same Field

If a Spring Data callback sets `last_modified_date` using the application clock and a trigger overwrites it with the database clock, the final result depends on execution order. That may be acceptable if the database is the canonical time source, but it must be designed deliberately.

Decide:

- Who owns `created_date`?
- Who owns `last_modified_date`?
- Who supplies `created_by` and `last_modified_by`?
- If an actor is missing, do we store NULL, a system actor, or reject the operation?
- Is the canonical clock the application UTC clock or the database clock?

Do not deploy two independent mechanisms without defining order and authoritative ownership.

## 12. Multiple Writers Within the Same Application

Even within a single application, multiple write paths can exist:

~~~text
HTTP controller
    |
    v
Application service
    |
    +--> Repository.save()
    |
    +--> JdbcAggregateTemplate.update()
    |
    +--> NamedParameterJdbcTemplate.update()
    |
    +--> Batch import
~~~

If the first paths use the aggregate lifecycle while later paths execute direct SQL, auditing will be inconsistent unless direct SQL sets audit fields itself or a trigger exists.

Consolidate write rules into an application service or persistence adapter whenever possible. For bulk updates requiring direct SQL for performance, update audit columns in the same statement or use a trigger per the chosen strategy.

Specifically, bulk updates do not load each aggregate individually, so there is no object for `AuditingEntityCallback` to process. Do not expect the callback to run once per modified row.

## 13. Auditors and Time in Multi-Instance Systems

When an application runs across multiple instances:

- Each instance may have its own security context for the request it is handling.
- Background tasks need a consistent system actor.
- Clocks across machines can drift.
- Some external writers outside Spring may use the database clock.

To keep data comparable:

1. Standardize timestamps on UTC.
2. Synchronize node clocks using an appropriate operational mechanism.
3. Provide a unified `DateTimeProvider`.
4. Use the same actor ID convention across services.
5. Avoid storing mutable display names if stable history is needed; prefer user IDs or service codes.

If a single authoritative timestamp across all writers is needed, database timestamps/triggers may fit better. If choosing the application clock, all writers must follow the same convention.

## 14. Testing Auditing with Immutable Entities and New Objects

A unit test for `AuditorAware` or a wither is not enough to prove auditing works during persistence. Integration tests going through the repository are needed so Spring Data executes lifecycle callbacks.

Scenarios to verify:

| Scenario | What to Verify |
|---|---|
| Insert entity with null ID | `createdBy` and `createdDate` are populated |
| Insert entity with pre-assigned ID and `@Version == null` | Still recognized as new |
| Update saved entity | `created*` stays unchanged, `lastModified*` changes |
| Immutable entity | Repository returns an object with updated audit fields |
| `AuditorAware` returns empty | Auditor fields obey the null/fallback convention |
| `modifyOnCreate = false` | `lastModified*` is not assigned on insert |
| Write via `JdbcTemplate` | Callback does not run automatically; SQL or trigger must handle audit |

### 14.1. Testing with a Fixed Clock

You can provide `Clock.fixed(...)` in tests:

~~~java
@TestConfiguration
static class FixedClockConfiguration {

    @Bean
    Clock auditingClock() {
        return Clock.fixed(
            Instant.parse("2026-11-13T08:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
~~~

When `DateTimeProvider` uses this clock, tests can compare `createdDate` and `lastModifiedDate` exactly without depending on wall-clock time.

### 14.2. Testing That Updates Do Not Overwrite Created Fields

Workflow:

1. Save an aggregate with auditor `alice`.
2. Record `createdBy` and `createdDate`.
3. Switch the auditor to `bob`.
4. Load the aggregate, change its state, and save again.
5. Verify `createdBy` is still `alice`.
6. Verify `lastModifiedBy` is `bob` and `lastModifiedDate` is updated.

With immutable entities, always use the instance returned from the repository after each save because withers and version updates may produce a new object.

## 15. Common Mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| `createdBy` is always NULL | Auditing not enabled or `AuditorAware` returns empty | Check `@EnableJdbcAuditing` and auditor bean |
| Creation date not set | Auditing callback not registered or property not mapped | Check configuration and annotations |
| Immutable entity lacks audit values | Missing withers or suitable property-update mechanism | Provide withers/constructor mapping and test via repository |
| Entity with pre-assigned ID gets UPDATED instead of INSERTED | Default newness assumes entity already exists | Use wrapper `@Version` or `Persistable.isNew()` |
| `createdDate` changes on update | Application logic overwrites it or newness detection is wrong | Verify newness strategy and never set created fields manually |
| `lastModifiedDate` empty on insert | `modifyOnCreate` is set to false | Confirm this is the intended semantics |
| `isNew()` is always true | State does not flip after insert | Use version or update transient flag after save |
| Direct SQL does not update audit | Bypasses Spring Data lifecycle callbacks | Assign audit columns in SQL or use a trigger |
| Audits differ across applications | Writers use different actors/clocks/formats | Standardize the auditing contract or move ownership to the database |
| `createdBy` stores `anonymousUser` | Anonymous principal not excluded | Filter out the anonymous principal in `AuditorAware` |
| Batch job lacks an auditor | No security context | Supply an explicit system actor |
| Times drift across instances | Unsynchronized clocks | Standardize on UTC and time source |

## 16. Process for Implementing Reliable Auditing

When adding auditing to an aggregate, you can follow this sequence:

1. **Design columns:** define actor IDs, timestamps, nullability, and data types.
2. **Enable auditing:** use `@EnableJdbcAuditing`.
3. **Provide the actor:** declare `AuditorAware<T>` and rules for requests, batches, and schedulers.
4. **Provide the clock:** use `DateTimeProvider` if time control is needed.
5. **Annotate properties:** use `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, and `@LastModifiedDate`.
6. **Design immutable mapping:** provide withers or an appropriate property creation strategy.
7. **Define newness:** use null ID, `@Version`, or `Persistable` depending on how IDs are assigned.
8. **Inventory all write sources:** repositories, `JdbcAggregateTemplate`, direct SQL, batches, and external apps.
9. **Choose an authoritative audit source:** application callbacks, writer-managed SQL, or database triggers.
10. **Integration tests:** test insert, update, immutable instances, assigned IDs, and every write path.

## 17. Practice Exercises

### Exercise 1 — Basic Auditing

1. Enable `@EnableJdbcAuditing`.
2. Create an `AuditorAware<String>` reading the principal name.
3. Add the four audit properties to `PurchaseOrder`.
4. Save an order and inspect the database columns.

### Exercise 2 — Immutable Entity

1. Convert `PurchaseOrder` into an immutable class.
2. Use Lombok `@Value` and `@With`, or write withers manually.
3. Keep the audit properties in the constructor.
4. Save and load the aggregate via the repository.
5. Verify the returned instance contains the audit values.

### Exercise 3 — Assigned IDs and Newness

1. Create an aggregate with a pre-assigned UUID.
2. Try saving without `@Version`.
3. Add `@Version Long version` and leave it null on creation.
4. Verify the first operation is INSERT and the next is UPDATE.
5. Try `Persistable.isNew()` if a custom strategy is needed.

### Exercise 4 — Multiple Write Sources

1. Save one aggregate via a repository.
2. Update another aggregate via `JdbcAggregateTemplate`.
3. Update a row using `JdbcTemplate`.
4. Observe which paths trigger auditing callbacks.
5. Add actor/time parameters or a database trigger for the direct SQL path.

### Exercise 5 — Multiple Actors and Clocks

1. Fix the clock in a test.
2. Save an aggregate with actor `alice`.
3. Update with actor `bob`.
4. Verify `createdBy` remains unchanged and `lastModifiedBy` changes.
5. Try a batch job without a security context and provide a system actor.

## 18. Conclusion

Spring Data JDBC auditing populates metadata before an aggregate is converted into write data. `@CreatedBy` and `@CreatedDate` are applied when the entity is identified as new; `@LastModifiedBy` and `@LastModifiedDate` are updated on modification, and by default may also be populated on creation via `modifyOnCreate`.

For immutable entities, provide withers or a new-instance creation mechanism compatible with mapping so audit values and versions are retained in the returned object. When the application assigns IDs itself, do not let Spring infer newness solely from a non-null ID; use a wrapper `@Version` or `Persistable.isNew()` as needed.

Finally, auditing callbacks only cover write paths passing through the Spring Data JDBC aggregate infrastructure. Direct SQL, bulk updates, and external writers must adhere to the audit contract themselves or use database triggers. When multiple write sources exist, establish one authoritative source for actors and timestamps, and verify every write path with integration tests.
