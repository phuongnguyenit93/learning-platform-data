# Purpose and Boundaries of Creation and Modification Metadata

Creation and modification metadata (auditing metadata) indicates **who created a record, when the record was created, who last modified it, and when it was last modified**. In Spring Data JDBC, auditing annotations help an application record this information along the entity save lifecycle without having to assign it manually in every service.

The four commonly used properties are `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, and `@LastModifiedDate`. They provide a basic marker of the origin and most recent update of the data.

It is important to clearly define the scope of this metadata. It does not automatically store the full change history, does not decide whether a user has permission to modify data, and does not replace optimistic locking. Those responsibilities require separate mechanisms.

This lesson explains the purpose of each field, how to enable auditing in Spring Data JDBC, how to obtain the actor and timestamp, where to place metadata in an aggregate, and the limitations when data is modified via direct SQL.

## 1. Why Do We Need Creation/Modification Metadata?

Suppose an orders table has business columns:

~~~text
sales_orders
+----+------------+----------+
| id | order_code | status   |
+----+------------+----------+
| 41 | SO-0041    | DRAFT    |
+----+------------+----------+
~~~

When investigating data, business columns alone may not answer:

- Which user or process created this record?
- When was the record created?
- Who last modified it?
- When did the last update occur?

Metadata can be added:

~~~text
sales_orders
+----+------------+----------+------------+---------------------+---------------+---------------------+
| id | order_code | status   | created_by | created_at          | modified_by   | modified_at         |
+----+------------+----------+------------+---------------------+---------------+---------------------+
| 41 | SO-0041    | DRAFT    | user-102   | 2026-10-03 08:15:00 | user-205      | 2026-10-04 10:42:18 |
+----+------------+----------+------------+---------------------+---------------+---------------------+
~~~

These fields are useful for:

- Displaying creation and last-updated information in admin screens.
- Assisting bug investigation and tracing data origins.
- Determining how old a record is.
- Supporting operational workflows, data checks, and reporting.
- Providing basic context when supporting users.

Creation/modification metadata is especially useful for long-lived data that is updated by multiple users or processes.

## 2. The Four Core Auditing Fields

Spring Data provides four primary annotations for creation and modification metadata.

| Annotation | Meaning | Typical Timing |
|---|---|---|
| `@CreatedBy` | Actor who created the record | When the entity is identified as new |
| `@CreatedDate` | Timestamp when the record was created | When the entity is identified as new |
| `@LastModifiedBy` | Actor who last modified the record | On creation and on modification, depending on configuration |
| `@LastModifiedDate` | Timestamp when the record was last modified | On creation and on modification, depending on configuration |

Example:

~~~java
@Table("sales_orders")
public class SalesOrder {

    @Id
    private Long id;

    private String orderCode;
    private String status;

    @CreatedBy
    @Column("created_by")
    private String createdBy;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @LastModifiedBy
    @Column("modified_by")
    private String modifiedBy;

    @LastModifiedDate
    @Column("modified_at")
    private Instant modifiedAt;
}
~~~

These annotations describe the role of each property. Spring Data JDBC uses an auditing callback during persistence to populate the appropriate values before writing data.

The column names in the example are explicitly declared with `@Column` so the schema and entity are easy to cross-reference. You can rely on the project's naming convention if it is configured consistently.

### 2.1. How Do Created and LastModified Differ?

`createdBy` and `createdAt` describe the original provenance of the record. Once the record has been created, these values are typically preserved across updates.

`modifiedBy` and `modifiedAt` describe the most recent update. They are set on creation if the configuration allows updating modification metadata at creation time, and are refreshed on subsequent modifications.

Example:

~~~text
Step 1: user-102 creates the order
    created_by  = user-102
    created_at  = 08:15
    modified_by = user-102
    modified_at = 08:15

Step 2: user-205 updates the status
    created_by  = user-102
    created_at  = 08:15
    modified_by = user-205
    modified_at = 10:42

Step 3: job-archive updates the archive label
    created_by  = user-102
    created_at  = 08:15
    modified_by = job-archive
    modified_at = 23:00
~~~

In the third step, the last modifier is a background process rather than an end user. This is why an application needs a unified actor convention for both user requests and background jobs.

## 3. Enabling Auditing for Spring Data JDBC

For Spring Data JDBC to automatically populate metadata, auditing must be enabled in configuration.

~~~java
@Configuration
@EnableJdbcAuditing
public class JdbcAuditingConfiguration {
}
~~~

Once enabled, Spring Data registers the auditing component for the entity lifecycle. When an entity is saved through Spring Data JDBC's repository mechanism, the callback can update the annotated properties.

If the application needs to record the current actor, declare an `AuditorAware<T>` bean. The bean's generic type must be compatible with the type of the properties annotated with `@CreatedBy` and `@LastModifiedBy`.

A simple example using a principal name:

~~~java
@Configuration
@EnableJdbcAuditing(auditorAwareRef = "auditorAware")
public class JdbcAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.of("system");
    }
}
~~~

The example above always returns the `system` actor, which is suitable for illustrating configuration but not for applications with logged-in users. In a real application, `AuditorAware` should retrieve the identity from the security context or an authenticated execution context.

If `AuditorAware` is not configured, auditing can still populate date/time fields when enabled, but there is no actor provider to populate the `@CreatedBy` and `@LastModifiedBy` fields.

### 3.1. Retrieving the Actor from Spring Security

The example below retrieves the principal name from Spring Security and excludes anonymous authentication:

~~~java
@Configuration
@EnableJdbcAuditing(auditorAwareRef = "auditorAware")
public class JdbcAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.ofNullable(
                    SecurityContextHolder.getContext().getAuthentication()
                )
                .filter(Authentication::isAuthenticated)
                .filter(authentication ->
                        !(authentication instanceof AnonymousAuthenticationToken)
                )
                .map(Authentication::getName);
    }
}
~~~

The corresponding imports come from Spring Security and Spring Data:

~~~java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
~~~

In a real system, it is better to store a stable actor identifier such as a user ID rather than a display name that may change. You can replace the `String` generic type with `UUID` or an identifier type suited to the application's user model.

### 3.2. An Actor May Be Absent

`AuditorAware` returns `Optional.empty()` when no actor can be determined. The application must decide what happens in this case:

- Allow the actor field to be NULL.
- Use a clearly defined system actor for jobs or migrations.
- Reject the operation if business rules require every change to have an identity.

You should not automatically assign every operation without a security context to a dummy user. Doing so diminishes traceability because users, jobs, migrations, and operational actions become indistinguishable.

## 4. Separating Actor from Access Permissions

Auditing records the identity used to perform an operation. It does not decide whether that identity has permission to perform the operation.

Example:

~~~text
Authentication
      |
      v
Identify current principal
      |
      +-----------------------+
      |                       |
      v                       v
Authorization             AuditorAware
Allowed to edit order?    Who is performing this?
      |                       |
      v                       v
Allow / deny              Record modified_by
~~~

These are related but distinct responsibilities:

- **Authentication:** identifies who the principal is.
- **Authorization:** checks whether the principal is allowed to perform a specific action.
- **Auditing:** records which actor created or modified the record.

Do not use the `createdBy` value as a substitute for permission checks. The fact that a record was created by someone does not mean only that person can edit it. Permissions may depend on roles, tenants, business status, or other policies.

Similarly, do not let clients arbitrarily send `createdBy` or `modifiedBy` in a request and trust those values directly. The actor should be obtained from the security context or a trusted server-side execution context.

## 5. Time Metadata and DateTimeProvider

Spring Data auditing can obtain the current time via the default time-providing mechanism. When you need control over the time source, you can declare a `DateTimeProvider`.

Example using `Clock` to standardize on UTC time:

~~~java
@Configuration
@EnableJdbcAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "dateTimeProvider"
)
public class JdbcAuditingConfiguration {

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider dateTimeProvider(Clock auditingClock) {
        return () -> Optional.of(auditingClock.instant());
    }

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.of("system");
    }
}
~~~

Using `Clock` is beneficial for testing because it can be replaced with a fixed clock. Tests then do not depend on the machine's wall-clock time.

### 5.1. Choosing a Time Type

Some common choices:

| Java Type | Meaning |
|---|---|
| `Instant` | An absolute point on the timeline |
| `OffsetDateTime` | A point in time with a UTC offset |
| `LocalDateTime` | Local date and time without timezone/offset |
| `LocalDate` | Date only, without time |

For auditing timestamps in distributed systems, `Instant` is usually the easiest choice to exchange because it represents a UTC point in time. The UI can convert it to the viewer's timezone when displaying.

If using `LocalDateTime`, an implicit timezone for the data must be agreed upon. Two servers running in different timezones can produce timestamps that are hard to compare without a clear convention.

### 5.2. Choosing One Authoritative Time Source

There are two common ways to assign timestamps:

- The application uses `DateTimeProvider` and writes the value to the column.
- The database uses a default or trigger to assign the timestamp.

Do not let both the application and a trigger update the same field without clearly defining which source is authoritative. If both overwrite each other, the observed value may differ from the time the application thought it wrote.

For auditing managed by Spring Data JDBC, let the application callback be the primary writer and configure the schema accordingly. If your organization requires the database to be the absolute time source, design triggers/defaults intentionally and test how they interact with entity mapping.

## 6. Where to Place Auditing Metadata in an Aggregate?

In Spring Data JDBC, the aggregate root is the consistency boundary of an aggregate. If the goal is to record who created and modified **the order**, metadata is usually placed on the aggregate root.

Example:

~~~text
SalesOrder
    id
    status
    created_by
    created_at
    modified_by
    modified_at
    |
    +-- OrderLine
    +-- OrderLine
~~~

This placement indicates the last time the aggregate was updated through an audited persistence path.

If individual children have independent lifecycles and require separate tracking, metadata can be placed on the corresponding child entity. However, you must understand precisely how Spring Data JDBC persists collection entities.

### 6.1. Root Metadata and Child Metadata Answer Different Questions

| Location | Question Answered |
|---|---|
| Aggregate root | Who created/last modified the aggregate? |
| Child entity | Who created/last modified this child row according to its persistence lifecycle? |
| Separate audit table | Which actions occurred and in what order? |

Do not place the same fields on every entity simply because you can. Each field should have a clear meaning and be updated according to the actual lifecycle of that data.

### 6.2. Caveat When Spring Data JDBC Rewrites Collections

Spring Data JDBC does not behave like an ORM with per-child dirty tracking. When saving an aggregate, referenced entities in a collection may be rewritten according to the aggregate's persistence strategy, including deleting and re-inserting child rows.

Therefore, do not assume that `created_at` on a child always means "the first business time the child was created" if the child row can be replaced during an aggregate save. The metadata may reflect the most recent row insert under the persistence mechanism.

If you need to preserve the original creation time of a child across every root save, design and verify an appropriate child persistence approach, or store business history in a separate table. Do not use persistence auditing metadata as an immutable history if the storage model can recreate child rows.

## 7. Creation/Modification Metadata Is Not a Full Audit History

The four auditing fields only store initial creation information and most recent modification information. They do not tell you every modification that has occurred.

For example, after three updates, a record may only retain:

~~~text
created_by  = user-102
created_at  = 2026-10-03T08:15:00Z
modified_by = user-205
modified_at = 2026-10-04T10:42:18Z
~~~

This information does not tell you:

- Who modified it previously?
- What was the old state?
- Which values changed?
- Which change happened before or after another?
- Why did the user make the change?

If these answers are needed, a separate audit trail is required.

### 7.1. Audit Metadata vs. Audit History

| Characteristic | Auditing Metadata | Audit History |
|---|---|---|
| Write frequency | Once on creation and last modification | Multiple records per event |
| Actors stored | Creator and last modifier | Actor for each action |
| Timestamps stored | Creation time and last modification time | Time of each action |
| Old/new values | No | Can be stored |
| Purpose | Operational metadata of the record | Historical tracing and investigation |
| Storage cost | Low | Higher, grows with event count |

Example audit history:

~~~sql
CREATE TABLE sales_order_audit (
    audit_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    actor_id VARCHAR(100) NOT NULL,
    action VARCHAR(40) NOT NULL,
    old_status VARCHAR(20),
    new_status VARCHAR(20),
    occurred_at TIMESTAMP NOT NULL,
    correlation_id VARCHAR(100)
);
~~~

Each significant action can insert an additional audit row. Real-world design must determine what data is allowed to be stored, retention periods, who can view it, and how to protect sensitive data.

### 7.2. Audit History Can Use an Outbox or Event Log

If changes need to emit events to other systems, an outbox record can be written in the same transaction as the aggregate change. A worker dispatches the event after the transaction commits.

Do not send a message before the database commits and assume both operations always succeed together. A standard database transaction does not automatically encompass an external broker.

Audit history also does not need to contain the entire before-and-after object. Store the fields needed for investigation, compliance, or operations and avoid unnecessarily copying sensitive data.

## 8. Auditing Does Not Replace Optimistic Locking

`modifiedAt` may change after every save, but it should not be used as the mechanism to detect lost updates.

Two requests can read the same timestamp value. Timestamp precision also depends on the column type, database, and driver. Comparing timestamps does not have semantics as clear as a numeric version.

Spring Data JDBC supports optimistic locking with `@Version`:

~~~java
@Table("sales_orders")
public class SalesOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    @LastModifiedDate
    private Instant modifiedAt;
}
~~~

The two fields serve two distinct purposes:

| Field | Question |
|---|---|
| `modifiedAt` | When did the most recent update occur? |
| `modifiedBy` | Who performed the most recent update? |
| `version` | How many versions has the aggregate changed under optimistic locking? |

If two users edit an aggregate concurrently, `@Version` helps detect a save based on a stale version. `@LastModifiedDate` only records the last update timestamp and does not automatically reject conflicting saves.

## 9. Auditing Callbacks and Direct Write Paths

Spring Data JDBC auditing is tied to Spring Data's persistence lifecycle. When saving an entity via a repository, the auditing callback can populate metadata before data is written.

However, a direct SQL statement like:

~~~java
jdbcClient.sql("""
        UPDATE sales_orders
        SET status = :status
        WHERE id = :id
        """)
    .param("status", status)
    .param("id", orderId)
    .update();
~~~

does not go through Spring Data JDBC's entity callback. Therefore, you should not expect `modifiedBy` and `modifiedAt` to be updated automatically.

If a direct SQL path is intentional, choose one of the following approaches:

1. Update the metadata directly in the SQL statement.
2. Use a database trigger as the metadata writer following a unified convention.
3. Route the operation through the repository/domain flow if full lifecycle behavior is needed.

Example updating metadata in SQL:

~~~java
jdbcClient.sql("""
        UPDATE sales_orders
        SET status = :status,
            modified_by = :actor,
            modified_at = :modifiedAt,
            version = version + 1
        WHERE id = :id
          AND version = :expectedVersion
        """)
    .param("status", status)
    .param("actor", actorId)
    .param("modifiedAt", clock.instant())
    .param("id", orderId)
    .param("expectedVersion", expectedVersion)
    .update();
~~~

This example also checks `version` to protect the direct write. In a real application, you must check the affected row count and execute related steps within an appropriate transaction.

### 9.1. Do Not Let Each Write Path Have Different Actor Rules

If the repository writes `modifiedBy` as a user ID while a direct-SQL batch job writes the host name, metadata becomes inconsistent.

Standardize:

- Actor ID format.
- How system users are represented.
- Time source.
- Rules for updating modified fields.
- How version is updated when changing an aggregate.
- Audit/outbox records to write per command type.

You can use a shared actor abstraction at the application layer so both repository flows and SQL adapters receive the same authenticated identity.

## 10. Background Jobs, Schedulers, and Service Accounts

Auditing is not just for HTTP requests. Data can be created or modified by:

- Scheduled jobs.
- Batch imports.
- Message consumers.
- Data migrations.
- Synchronization workflows.
- Operational accounts or service accounts.

These flows typically do not have an end-user `SecurityContext`. If `AuditorAware` only reads the `SecurityContext`, it may return `Optional.empty()`.

Define an actor for each process type. For example:

| Execution Flow | Possible Actor |
|---|---|
| Logged-in user | Stable user ID |
| Scheduled archive job | `system:archive-job` |
| Partner import | `integration:partner-a` |
| Data migration | `migration:release-2026-11` |
| Message consumer | Service identity or producer identity per policy |
| Administrative action | Admin user ID |

If you need to know both the initiator and the executing service, these two pieces of information can be stored separately in an audit event. The `modifiedBy` field should usually contain only one actor according to the chosen convention, rather than packing multiple identity sources into a single string.

With async execution, do not assume the security context is automatically present on every thread. Pass the actor context explicitly or use a configured context propagation mechanism.

## 11. Schema Design for Auditing Metadata

An orders table can be declared as:

~~~sql
CREATE TABLE sales_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_code VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL,

    created_by VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE,
    modified_by VARCHAR(100),
    modified_at TIMESTAMP WITH TIME ZONE,

    version BIGINT NOT NULL
);
~~~

Points to decide:

- Whether actor columns use user ID, UUID, or service identity.
- Whether timestamps are stored in UTC or another timezone convention.
- Whether NULL is allowed when the actor is unknown.
- Whether indexes on `created_at` or `modified_at` are needed for operational queries.
- Whether a separate version column is stored for optimistic locking.
- Whether a separate audit history table is maintained.

Not every table needs all four fields. Immutable lookup tables or technical tables may not need modification metadata. Base this decision on traceability needs and data lifecycle.

### 11.1. Should a Foreign Key Be Used from created_by to the Users Table?

A FK can be created if user records always exist and user lifecycles are managed appropriately. However, if users can be deleted or migrated to another identity system, a hard FK can complicate preserving history.

One option is to store a stable actor ID as a reference value while keeping audit identities in the identity management system. Consider the ability to look up an actor after an account is disabled or deleted.

### 11.2. Indexes for Timestamps

An index on `modified_at` can be useful for jobs searching for stale records or operational dashboards. However, since this field changes frequently, an index also increases write overhead.

Create an index only when an actual query requires it. Do not index every metadata column by default.

## 12. Testing Auditing

Tests should verify that metadata is written properly via the repository path, with controllable actor and clock values.

A test configuration can use a fixed `AuditorAware` and a `DateTimeProvider` returning a known point in time. That way, tests do not depend on the system clock.

Key scenarios:

| Scenario | Expected Result |
|---|---|
| Create new entity | `createdBy` and `createdDate` populated if providers exist |
| Create new entity with modify-on-create enabled | `lastModifiedBy`/`Date` populated per configuration |
| Modify existing entity | `created` metadata preserved; `modified` metadata updated |
| No actor | Auditor fields follow Optional/NULL/system actor policy |
| Run scheduled job | `modifiedBy` reflects the defined service actor |
| Write via repository | Auditing callback is executed |
| Write via direct `JdbcClient` | Metadata does not change automatically unless SQL/trigger updates it |
| Change clock in test | Timestamp has a deterministic value |
| Child entity resaved with aggregate | Verify metadata semantics per how Spring Data JDBC writes collections |

Conceptual test example:

~~~java
@DataJdbcTest
@Import(TestJdbcAuditingConfiguration.class)
class SalesOrderAuditingTest {

    @Autowired
    SalesOrderRepository repository;

    @Test
    void storesCreationAndModificationMetadata() {
        SalesOrder order = SalesOrder.draft();

        SalesOrder created = repository.save(order);

        assertThat(created.getCreatedBy()).isEqualTo("user-42");
        assertThat(created.getCreatedAt())
                .isEqualTo(Instant.parse("2026-11-13T08:00:00Z"));

        // Modify the entity and save again in a separate step.
        SalesOrder loaded = repository.findById(created.getId())
                .orElseThrow();

        loaded.changeStatus("CONFIRMED");

        SalesOrder updated = repository.save(loaded);

        assertThat(updated.getCreatedBy()).isEqualTo("user-42");
        assertThat(updated.getModifiedBy()).isEqualTo("user-42");
    }
}
~~~

This is an illustrative example; the entity must provide the corresponding factory, getters, and domain methods. Real tests should verify that `modifiedAt` changes with a new clock and `createdAt` remains unchanged after an update.

### 12.1. Testing Direct SQL Separately

Another integration test should run an UPDATE via `JdbcClient` and verify that metadata does not change if the SQL statement does not update metadata and the database has no trigger.

This test helps the team clearly see the boundary between the repository lifecycle and direct SQL.

## 13. Common Mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Treating `createdBy` as ownership permission | Creator is mistaken for the only one allowed to edit | Use separate authorization |
| Using `modifiedAt` instead of `@Version` | Lost updates are not reliably detected | Use a numeric version for optimistic locking |
| Expecting `JdbcClient` to invoke auditing callbacks | Metadata is not updated | Write metadata in SQL or use a repository |
| Not configuring an actor for jobs | `createdBy`/`modifiedBy` may be NULL or missing | Define a service actor |
| Using display names as actor IDs | Name changes hinder traceability | Store a stable user/service identifier |
| Overwriting creation metadata on every save | Original creation time is lost | Distinguish created and modified fields |
| Treating the four fields as full history | Intermediate changes are unknown | Use a separate audit history/event log |
| Assigning metadata from request body | Clients can spoof the actor | Read actor from server security context |
| Letting both app and trigger write timestamps | Time source is inconsistent | Choose one authoritative source |
| Placing auditing on every child without understanding persistence | Metadata may reflect row rewrites | Align with the aggregate/entity lifecycle |

## 14. Process for Adding Auditing to an Aggregate

When adding creation/modification metadata to an entity:

**Step 1 — Define the purpose.** Do you need the creator/last modifier and timestamps, or full history?

**Step 2 — Choose the location.** Does metadata belong on the aggregate root, child entity, or a separate audit table?

**Step 3 — Choose data types.** Use a stable actor ID and a time type with clear timezone semantics.

**Step 4 — Enable auditing.** Configure `@EnableJdbcAuditing`.

**Step 5 — Provide the actor.** Implement `AuditorAware` reading an authenticated principal or service identity.

**Step 6 — Provide time if needed.** Use `DateTimeProvider` to control the clock and testing.

**Step 7 — Map the schema.** Create corresponding columns and decide nullability, indexes, and retention.

**Step 8 — Check write paths.** Repository lifecycle includes auditing; direct SQL must update metadata itself or use a trigger by convention.

**Step 9 — Separate other concerns.** Authorization, optimistic locking, audit history, and domain events need their own mechanisms.

**Step 10 — Test actor and time.** Cover user requests, background jobs, async flows, and direct SQL.

~~~text
Entity is created or modified
          |
          v
Which write path?
     /         \
 Repository    Direct SQL
     |              |
     v              v
Auditing callback  SQL/trigger writes it
     |              |
     +-------+------+
             |
             v
created/modified metadata
             |
             +---- Does not replace authorization
             |
             +---- Does not replace @Version
             |
             +---- Does not replace audit history
~~~

## 15. Self-Check Scenarios

**Scenario A — Creator and modifier**

User A creates an order, user B modifies the order. What values should `createdBy` and `modifiedBy` have?

**Hint:** `createdBy` keeps A; `modifiedBy` reflects B after the most recent update.

**Scenario B — Scheduled job**

A job updates the archive status, but there is no logged-in user. What will an `AuditorAware` that only reads `SecurityContext` return?

**Hint:** It may return `Optional.empty()`. Define a dedicated system actor for the job.

**Scenario C — Direct SQL**

An UPDATE statement via `JdbcClient` changes the status. Does `@LastModifiedDate` run automatically?

**Hint:** No. Direct SQL does not go through Spring Data JDBC's auditing callback; you must update metadata in SQL or use a trigger.

**Scenario D — Two concurrent editors**

Two people read the same order concurrently. Is `modifiedAt` sufficient to prevent a stale save?

**Hint:** No. Use `@Version` to detect optimistic locking conflicts.

**Scenario E — Needing all modifications**

The table only has `createdBy`, `createdAt`, `modifiedBy`, and `modifiedAt`. Can you see who modified it the second time?

**Hint:** No. The four fields only keep creation and the most recent modification; an audit history or event log is needed.

**Scenario F — Metadata on a child**

A child is rewritten when the aggregate root is saved. Is `createdAt` on the child guaranteed to reflect when the child was first created in business terms?

**Hint:** Do not assume so. Check Spring Data JDBC's collection persistence strategy; if stable history is required, use an appropriate storage design.

## 16. Summary Notes

| Component | Responsibility |
|---|---|
| `@CreatedBy` | Actor who created the entity |
| `@CreatedDate` | Timestamp when the entity was created |
| `@LastModifiedBy` | Actor who last modified the entity |
| `@LastModifiedDate` | Timestamp when the entity was last modified |
| `@EnableJdbcAuditing` | Enables auditing for Spring Data JDBC |
| `AuditorAware<T>` | Provides the current actor |
| `DateTimeProvider` | Provides time for auditing |
| Aggregate root | Usually where aggregate metadata is placed |
| Direct SQL | Must write metadata explicitly or use a trigger |
| `@Version` | Detects optimistic locking conflicts |
| Authorization | Decides who is allowed to perform an action |
| Audit history | Stores multiple events and changes over time |

**Auditing metadata records the origin and most recent update of data.** In Spring Data JDBC, `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, and `@LastModifiedDate` are populated via the auditing lifecycle when saving entities through a repository. Provide actor and time values with clear conventions, place metadata at the proper aggregate boundary, and remember that direct SQL needs separate handling. If you need access control, lost-update prevention, or complete history, use authorization, `@Version`, and audit history respectively.

## References

- [Spring Data Relational — Auditing](https://docs.spring.io/spring-data/relational/reference/jdbc/auditing.html): enabling JDBC auditing, auditor provider, and creation/modification annotations.
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html): `AuditorAware`, `DateTimeProvider`, and auditing metadata.
- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): aggregate persistence, lifecycle callbacks, and optimistic locking.
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): principal and security context.
