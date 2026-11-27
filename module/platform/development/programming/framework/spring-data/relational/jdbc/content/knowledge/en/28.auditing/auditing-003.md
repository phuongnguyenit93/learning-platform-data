# @CreatedDate, @LastModifiedDate, @CreatedBy, and @LastModifiedBy in Spring Data JDBC

## 1. What Does Auditing Record?

Auditing in Spring Data JDBC helps store metadata about when an aggregate was created or updated and which actor performed the operation. The four commonly used annotations are:

| Annotation | Information | Typical Timing |
|---|---|---|
| `@CreatedDate` | Creation time | When the aggregate is first inserted |
| `@LastModifiedDate` | Last modification time | On creation and on every update |
| `@CreatedBy` | Actor who created the data | When the aggregate is created |
| `@LastModifiedBy` | Actor who last modified the data | On creation and on every update |

For example, an order can store `createdAt`, `createdBy`, `lastModifiedAt`, and `lastModifiedBy`. When a user updates the order status, the original creation information is retained, while the modification metadata is updated.

Auditing is useful for operational traceability, bug investigation, displaying "who updated this", and checking the time of the most recent change. It does not automatically create a full history of every data version. `@LastModifiedDate` and `@LastModifiedBy` only retain the most recent modification information on the current row.

## 2. Enabling Auditing for Spring Data JDBC

Declare auditing using `@EnableJdbcAuditing` in Spring configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing
public class JdbcAuditingConfiguration {
}
~~~

When enabled, Spring Data JDBC registers an auditing callback mechanism. This callback populates auditing values onto the entity during the Spring Data JDBC persistence process.

The annotations `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, and `@LastModifiedBy` belong to Spring Data Commons, located in the `org.springframework.data.annotation` package. They are not JPA annotations. With Spring Data JDBC, use `@EnableJdbcAuditing` instead of enabling JPA auditing with `@EnableJpaAuditing`.

If the application uses Spring Boot, place the auditing configuration in a component- or configuration-scanned package. Avoid declaring multiple duplicate repository/auditing configurations without checking scan scope.

## 3. Declaring Audit Metadata on an Entity

Example `PurchaseOrder` aggregate root:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private String status;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @LastModifiedDate
    @Column("last_modified_at")
    private Instant lastModifiedAt;

    @CreatedBy
    @Column("created_by")
    private String createdBy;

    @LastModifiedBy
    @Column("last_modified_by")
    private String lastModifiedBy;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String status) {
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

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
~~~

Key points to note:

- `@Id` marks the aggregate root identifier.
- `@CreatedDate` and `@LastModifiedDate` are placed on timestamp properties.
- `@CreatedBy` and `@LastModifiedBy` are placed on actor properties.
- `@Column` maps the Java property to the column name in the schema.
- The type of the actor property must be compatible with the generic type provided by `AuditorAware<T>`.

`Instant` is a suitable choice for timestamps representing an absolute point in time. If using `LocalDateTime` or another type, align the timezone and conversion behavior across the application, JDBC driver, and database.

The example uses a mutable entity for illustration. Spring Data JDBC also supports immutable entities, provided auditing values can be applied through a constructor, property accessor, or wither compatible with the mapping. If the entity uses a record or immutable class, check the constructor/property mapping of the Spring Data JDBC version in use.

## 4. Providing the Current Actor with AuditorAware

The `@CreatedBy` and `@LastModifiedBy` annotations need to know the current actor. Spring Data obtains the actor through an `AuditorAware<T>` bean.

As a simple example, suppose the application has an abstraction that provides the current user:

~~~java
public interface CurrentActor {
    String username();
}
~~~

Provider configuration:

~~~java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;

@Configuration
public class AuditorConfiguration {

    @Bean
    AuditorAware<String> auditorAware(CurrentActor currentActor) {
        return () -> Optional.ofNullable(currentActor.username());
    }
}
~~~

The generic type `String` must be compatible with the type of `createdBy` and `lastModifiedBy` on the entity. If the application stores user IDs as UUIDs, you can use `AuditorAware<UUID>` and declare both actor properties as `UUID`.

### 4.1. Connecting to Spring Security

If the application uses Spring Security, the provider can obtain the username from the security context:

~~~java
import java.util.Optional;

import org.springframework.data.domain.AuditorAware;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public class SecurityAuditorAware implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || "anonymousUser".equals(authentication.getPrincipal())) {
            return Optional.empty();
        }

        return Optional.of(authentication.getName());
    }
}
~~~

Register the bean and reference it from the auditing configuration:

~~~java
@Configuration
@EnableJdbcAuditing(auditorAwareRef = "auditorAware")
public class JdbcAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return new SecurityAuditorAware();
    }
}
~~~

The bean name in `auditorAwareRef` must match the actual bean. If the application does not use Spring Security, connect `AuditorAware` to the application's authentication mechanism or actor context; you do not need to add Spring Security just to use auditing.

### 4.2. When There Is No Current User

`AuditorAware` returns `Optional.empty()` when no actor can be determined. In that situation, the actor field may not be populated by the auditing handler. Clearly decide the schema and business policy for this case:

- Allow the actor column to be NULL if some operations have no user.
- Use a technical actor such as `system` for schedulers, batch jobs, or migrations.
- Use a service account identifier when an operation is performed by a specific service.

Do not assign a fake username just to avoid NULL. The actor value must accurately reflect the source that performed the operation.

For background tasks, a request's security context is usually not present on the worker thread. Provide a system actor explicitly in the job execution context, or design the provider to distinguish user requests from system tasks.

## 5. Auditing Time and DateTimeProvider

If only the current timestamp is needed, Spring Data auditing can use the default time provider. When you need control over the clock, timezone, or time-based testing, configure a `DateTimeProvider` bean.

Example using `Clock`:

~~~java
import java.time.Clock;
import java.time.temporal.TemporalAccessor;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;

@Configuration
public class AuditTimeConfiguration {

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider dateTimeProvider(Clock auditClock) {
        return () -> Optional.<TemporalAccessor>of(auditClock.instant());
    }
}
~~~

Reference the provider in configuration:

~~~java
@Configuration
@EnableJdbcAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "dateTimeProvider"
)
public class JdbcAuditingConfiguration {
    // Declare the auditor/time provider beans in the appropriate configuration.
}
~~~

Using an injected `Clock` gives the application an explicit time source that is easy to swap in tests. `Clock.systemUTC()` avoids relying on the default timezone of the host running the application.

If the system requires the database to determine the time, you can consider database-level timestamps, defaults, or triggers. However, that is a different time source than the application's auditing callback. Standardize on a single time source to avoid inconsistent timestamp comparisons across write paths.

## 6. When Are Values Assigned?

Auditing in Spring Data JDBC is performed via Spring Data entity callbacks. When an aggregate is saved using a repository or aggregate operations, the auditing callback updates metadata before the entity is converted and written to the database.

| Operation | Created fields | Last-modified fields |
|---|---|---|
| Insert new aggregate | Populated | Typically also populated on creation |
| Update existing aggregate | Retains original creation values | Updated for the modification |
| Read aggregate | Unchanged | Unchanged |
| Hand-written SQL UPDATE | Does not run callbacks automatically | Does not run callbacks automatically |

In standard auditing configuration, modification metadata is set even on creation; the `modifyOnCreate` attribute of the auditing configuration can adjust this behavior in versions that support that attribute.

Created metadata represents the initial creation. Do not overwrite `createdAt` or `createdBy` during normal updates. Modified metadata reflects the most recent modification along a persistence path that executed the auditing callback.

### 6.1. Repository Usage Example

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Creating a new record:

~~~java
PurchaseOrder order = new PurchaseOrder("PENDING");
PurchaseOrder saved = orders.save(order);

System.out.println(saved.getCreatedAt());
System.out.println(saved.getCreatedBy());
System.out.println(saved.getLastModifiedAt());
System.out.println(saved.getLastModifiedBy());
~~~

Then updating the status:

~~~java
PurchaseOrder loaded = orders.findById(saved.getId())
        .orElseThrow();

loaded.setStatus("CONFIRMED");

PurchaseOrder updated = orders.save(loaded);
~~~

When auditing is enabled and the operation goes through Spring Data JDBC persistence callbacks:

- `createdAt` still represents the creation time.
- `createdBy` still represents the creating actor.
- `lastModifiedAt` is updated.
- `lastModifiedBy` reflects the actor performing the edit.

Do not manually set auditing fields in services before calling `save` if the auditing handler is the canonical source. Manual assignment can make metadata inconsistent or mask the actor/time provider.

## 7. Table Structure and Data Types

The schema needs columns corresponding to the entity metadata:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_modified_at TIMESTAMP WITH TIME ZONE,
    created_by VARCHAR(120),
    last_modified_by VARCHAR(120)
);
~~~

This is a PostgreSQL example. Timestamp types and identity syntax vary by DBMS. For databases supporting a timestamp-with-timezone equivalent, that type is usually appropriate when the application stores `Instant`.

Several schema decisions should be aligned:

- Is the actor required? If batch/system tasks can run without an actor, the actor column may need to be nullable or the provider must return a system actor.
- Is the modified timestamp required? If auditing is configured to write modified time on creation, `NOT NULL` can be used; if that behavior is disabled, adjust the schema.
- Is timestamp precision sufficient for the workload? The database may round or truncate fractional seconds.
- Do column names match the mapping? Use `@Column` when explicit clarification is needed.
- Do write paths outside Spring Data JDBC populate all columns? If not, intentional defaults or DB mechanisms are needed.

Do not set `NOT NULL` on the actor column before ensuring every write path provides a valid actor. A migration task or manual SQL script might not have a security context like an ordinary request.

## 8. Custom SQL Does Not Automatically Run Auditing Callbacks

An important point is that auditing callbacks are bound to Spring Data JDBC's persistence path. Hand-written UPDATE statements via `@Modifying @Query` or `JdbcTemplate` do not materialize the entity and run auditing callbacks.

Example query:

~~~java
@Modifying
@Query("""
    UPDATE purchase_orders
    SET status = :status
    WHERE id = :id
    """)
int updateStatus(
        @Param("id") Long id,
        @Param("status") String status
);
~~~

This query does not automatically update `last_modified_at` or `last_modified_by`. If auditing is required for direct SQL, update metadata directly in the SQL statement:

~~~java
@Modifying
@Query("""
    UPDATE purchase_orders
    SET status = :status,
        last_modified_at = :modifiedAt,
        last_modified_by = :actor
    WHERE id = :id
    """)
int updateStatusWithAudit(
        @Param("id") Long id,
        @Param("status") String status,
        @Param("modifiedAt") Instant modifiedAt,
        @Param("actor") String actor
);
~~~

The service can obtain the actor and timestamp from their respective abstractions and pass them as parameters. With direct SQL, the application is responsible for maintaining the rules:

- Do not alter `created_at` and `created_by` in ordinary UPDATEs.
- Update both modified timestamp and actor per policy.
- Bind every value via parameters.
- If the entity has `@Version`, consider adding a version predicate and incrementing version in the same statement.
- Check the update count to know whether the predicate matched.

Another option is to use database triggers or defaults. If you choose this approach, define the database's actor/time source and avoid having application callbacks and triggers overwrite each other.

## 9. Auditing Metadata Is Not an Audit Trail

The four annotations retain only one current set of metadata on the entity. For example, after three updates, the row still only has:

~~~text
created_by       = alice
created_at       = creation timestamp
last_modified_by = bob
last_modified_at = last modification timestamp
~~~

Information about who modified it the first and second times is no longer represented in these fields.

If requirements call for storing the full history:

- Create a separate history/audit table with one row per change.
- Store actor, timestamp, entity ID, action type, and before/after data per policy.
- Write the audit record in the same transaction as the business change if both operations must be atomic.
- Consider a transactional outbox if events need to be emitted to other systems after commit.
- For high regulatory or security requirements, define permissions for modifying/deleting logs and retention periods.

Auditing metadata is useful for current state; an audit trail is a different data model.

## 10. Clock, Timezone, and Actor in Multi-Instance Environments

When an application runs across multiple machines or containers, system clocks can drift. If each instance reads its own clock, two closely spaced operations might record timestamps not strictly in real-world order.

Some practices:

- Use UTC and store points in time as instants.
- Synchronize node clocks using reliable time infrastructure.
- Use a shared `DateTimeProvider` for easier control and testing.
- Do not use timestamps as the sole absolute ordering key if two events can occur at the same instant; add an ID or sequence when ordering is required.
- If canonical database-issued timestamps are required, use consistent database expressions/defaults/triggers across all write paths.

Actors also need a unified convention. A user's username might change; in long-lived systems, storing a stable ID (`UUID`/`long`) is usually better than storing a display name. Display names can be stored in an identity table if needed.

## 11. Auditing and Aggregates

Spring Data JDBC manages an aggregate root together with the components belonging to the aggregate. Audit metadata is usually placed on the aggregate root to represent the timestamp and actor of saving the aggregate.

If a child object changes and the application saves the aggregate root, the auditing callback can update the root's metadata for that persistence operation. This does not automatically create an independent set of metadata for each child row. If each child needs its own actor/time, design the entity/mapping and lifecycle appropriately, or store separate historical events.

Do not turn auditing into a reason to break aggregate boundaries. Determine whether metadata should reflect changes to the root, the child, or individual independent records.

## 12. Testing Auditing

Test via a real repository inside a Spring context to verify that auditing is enabled and callbacks actually execute.

Example test setup:

~~~java
@DataJdbcTest
@Import(JdbcAuditingConfiguration.class)
class PurchaseOrderAuditingTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Test
    void populatesAuditFieldsOnInsert() {
        PurchaseOrder saved = orders.save(
                new PurchaseOrder("PENDING")
        );

        assertThat(saved.getCreatedAt()).isNotNull();
        assertThat(saved.getLastModifiedAt()).isNotNull();
        assertThat(saved.getCreatedBy()).isEqualTo("test-user");
        assertThat(saved.getLastModifiedBy()).isEqualTo("test-user");
    }
}
~~~

This is an illustrative example; the test must provide an `AuditorAware` bean returning `test-user` and import the auditing configuration. If using a custom `DateTimeProvider`, the test can control the clock to assert exact timestamps without depending on wall-clock time.

Scenarios to verify:

| Scenario | What to Verify |
|---|---|
| New insert | Created and modified metadata populated per configuration |
| Entity update | Created fields remain unchanged |
| Entity update | Last-modified fields reflect the new actor/time |
| No actor | `Optional.empty` behavior and nullable constraints match policy |
| System job | Technical actor recorded per convention |
| Direct UPDATE | Modified metadata only changes if SQL/trigger updates it explicitly |
| Immutable entity | Mapping returns entity with applied metadata |
| Multiple repositories | Aggregates share providers as expected |
| Test with fixed clock | Timestamps have deterministic values, easy to assert |

A test with automatic transaction rollback can still inspect the entity returned from `save` within the same test. If you need to verify post-commit data or trigger/database behavior, write an integration test with an appropriate transaction boundary.

## 13. Common Mistakes

| Symptom | Possible Cause | Remedy |
|---|---|---|
| Auditing fields are always NULL | `@EnableJdbcAuditing` not enabled or entity not processed by callback | Enable auditing in the Spring context |
| Created/modified dates populated but actor is NULL | `AuditorAware` not registered or provider returns `Optional.empty` | Configure provider and check actor context |
| Current user not picked up correctly | Security context absent on thread or provider reads wrong principal | Check authentication and async tasks |
| Last-modified not updated with custom SQL | Direct SQL does not execute entity callbacks | Update columns in SQL or use a DB mechanism |
| Created fields overwritten on update | Service manually sets metadata or mapping fails to retain old values | Let auditing manage created fields |
| Insert fails due to NOT NULL actor | Job/migration lacks an actor | Use a system actor or nullable schema per policy |
| Timestamps drift across instances | Inconsistent clocks/timezones | Use UTC, synchronize clocks, or use database time |
| Immutable entity misses audit fields | Incompatible constructor/wither/property mapping | Declare compatible properties/constructor |
| Modified timestamp unchanged in test | Fixed clock or low timestamp precision | Control the clock and check precision |
| Assuming four annotations store full history | Confusing current metadata with an audit trail | Create a history table or event log |
| Triggers and callbacks overwrite each other | Two independent auditing sources | Choose a canonical source or separate responsibilities clearly |
| Column names mismatch | Missing mapping or schema differs from property names | Use `@Column` and verify DDL |

## 14. Implementation Workflow

1. Identify the metadata to store and a stable actor type.
2. Add the four auditing fields to the aggregate root and map columns.
3. Enable `@EnableJdbcAuditing` in Spring Data JDBC configuration.
4. Register `AuditorAware<T>` to provide the current actor.
5. If time control is needed, register a `DateTimeProvider` backed by a `Clock`.
6. Create or migrate the audit columns with appropriate data types and nullability.
7. Use repository/aggregate operations so auditing callbacks are executed.
8. For direct SQL, explicitly update modified metadata or use an intentional database trigger.
9. Test insert, update, absent actor, background jobs, and other write paths.
10. If full history is needed, design a separate audit trail rather than relying solely on last-modified fields.

## 15. Practice Exercises

### Exercise 1 — Enable Auditing

Create an `@EnableJdbcAuditing` configuration and add `@CreatedDate` and `@LastModifiedDate` to an aggregate. Save a new entity and verify that both timestamps are populated.

### Exercise 2 — Actor Provider

Create an `AuditorAware<String>` that reads the actor from a current-actor abstraction. Test a user request, an anonymous request, and a system job. Verify the rule for `Optional.empty`.

### Exercise 3 — Created and Modified

Insert an order under actor A, then update it under actor B. Verify that created metadata remains A and modified metadata changes to B.

### Exercise 4 — Custom DateTimeProvider

Inject a `Clock` into `DateTimeProvider`. In tests, use a controllable clock to verify insert and update timestamps.

### Exercise 5 — Direct SQL

Create an `@Modifying @Query` method that updates status. Observe last-modified fields before including them in SQL, then update timestamp/actor explicitly and compare.

### Exercise 6 — Immutable Aggregate

Convert the entity to a record or immutable class. Configure constructor/property mapping so auditing fields are applied and verify the entity returned from `save`.

### Exercise 7 — Audit Trail

Create a history table storing every order status change. Write the history in the same transaction as the aggregate update and compare that information against last-modified metadata.

### Exercise 8 — Multiple Write Sources

Perform one insert via repository, one via direct SQL, and one from a batch job. Identify the actor/time source for each write path and ensure auditing data is never unintentionally left blank.

## 16. Key Takeaways

- `@CreatedDate` and `@CreatedBy` record the creation timestamp and actor of an aggregate.
- `@LastModifiedDate` and `@LastModifiedBy` record the most recent modification; modified metadata is typically also populated on creation under default configuration.
- Enable auditing for Spring Data JDBC with `@EnableJdbcAuditing`.
- `AuditorAware<T>` provides the actor; its generic type must be compatible with the `@CreatedBy` and `@LastModifiedBy` properties.
- `DateTimeProvider` provides the time; injecting a `Clock` helps standardize on UTC and simplifies testing.
- Auditing callbacks run on Spring Data JDBC persistence paths; custom SQL/`JdbcTemplate` does not run callbacks automatically.
- Created fields preserve initial values; modified fields are updated on subsequent persistence operations.
- Absent actors require an explicit policy: nullable columns, system actor, or service account.
- Last-modified fields store only current state and do not replace an audit trail storing every change.
- Test via repositories inside a Spring context and verify schema, actor provider, clock, immutable mapping, and direct write paths.
