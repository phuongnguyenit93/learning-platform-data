# Configuring AuditingEntityListener and a Shared Base Audit Class

Spring Data JPA Auditing automatically records information about who created an Entity and when it was created, as well as who last modified it and when it was last modified. This mechanism is useful for business tables that need to track who created data, when it was created, and when the most recent update occurred.

For auditing to work, the application must enable Spring Data JPA Auditing configuration, register `AuditingEntityListener` with JPA, and annotate the properties to be tracked with `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, or `@LastModifiedBy`. When multiple Entities share audit fields, you can group them into a `@MappedSuperclass` to reuse the mapping and listener.

## 1. What Is Auditing and What Is It Used For?

Auditing stores metadata describing the lifecycle of data. A record typically has four pieces of information:

| Property | Annotation | Meaning |
|---|---|---|
| createdAt | `@CreatedDate` | Timestamp when the Entity was created |
| createdBy | `@CreatedBy` | Actor that created the Entity |
| lastModifiedAt | `@LastModifiedDate` | Timestamp when the Entity was last modified |
| lastModifiedBy | `@LastModifiedBy` | Actor that last modified the Entity |

For example, an order record might store:
- createdAt = timestamp when the order was created.
- createdBy = user ID or service account that created the order.
- lastModifiedAt = timestamp when the order's status or details were last updated.
- lastModifiedBy = user or process that performed that update.

Auditing is useful for:
- Tracking changes in administrative applications.
- Supporting bug investigations and data reconciliation.
- Displaying "created by" or "updated at" information.
- Supporting internal control processes.
- Determining whether data was created by a user or a background task.

Auditing metadata is not a complete history of every Entity version. The lastModified fields only retain information about the most recent update. If you need to store the full change history, consider a separate audit log, event log, or Hibernate Envers.

## 2. Auditing Annotations

Spring Data provides four main annotations in the `org.springframework.data.annotation` package:

- `@CreatedDate`: marks the creation timestamp.
- `@LastModifiedDate`: marks the last update timestamp.
- `@CreatedBy`: marks the auditor that created the record.
- `@LastModifiedBy`: marks the auditor that last updated the record.

Example:

~~~java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant lastModifiedAt;

@CreatedBy
private String createdBy;

@LastModifiedBy
private String lastModifiedBy;
~~~

These annotations only describe metadata to be processed by auditing. They do not work automatically if the application has not enabled auditing and the Entity does not have the appropriate listener attached.

For new applications, `java.time` types such as `Instant` or `LocalDateTime` are usually clear choices. `Instant` represents a point on the timeline and is often convenient when storing UTC timestamps; `LocalDateTime` contains no timezone/offset, so a clear timezone convention is required at the application and database layers.

The type of `@CreatedBy` and `@LastModifiedBy` must be compatible with the generic type of `AuditorAware<T>`. If the auditor is a string username, use `AuditorAware<String>` and String audit fields. If using a Long user ID, use `AuditorAware<Long>`.

## 3. Role of AuditingEntityListener

`AuditingEntityListener` is a JPA entity listener provided by Spring Data JPA:

~~~java
import org.springframework.data.jpa.domain.support.AuditingEntityListener;
~~~

The listener connects JPA lifecycle callbacks to Spring Data's auditing handler. Essentially:
- When an Entity is first persisted, the creation callback triggers auditing processing.
- When an Entity is updated, the update callback triggers auditing processing.
- The handler reads the current auditor and current time, then assigns them to the annotated properties.

Register the listener using the JPA annotation:

~~~java
@EntityListeners(AuditingEntityListener.class)
~~~

Example placed on an Entity:

~~~java
@Entity
@EntityListeners(AuditingEntityListener.class)
public class Customer {
    // Entity properties.
}
~~~

When Customer is persisted/updated through JPA, the listener can update the auditing fields before changes are synchronized to the database.

If multiple Entities need auditing, avoid repeating the configuration and four fields on every class. You can place the listener and audit properties in a mapped superclass.

## 4. Enabling Auditing with @EnableJpaAuditing

The application needs to enable auditing in Spring configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing
public class JpaAuditingConfiguration {
}
~~~

`@EnableJpaAuditing` registers the infrastructure needed for Spring Data to process auditing annotations.

If only creation and update dates are needed, this minimal configuration may suffice. If creator/modifier fields are needed, provide an `AuditorAware` bean. If you want to control the time source, you can provide a `DateTimeProvider`.

Two notable configuration attributes:
- `auditorAwareRef`: name of the bean providing the current auditor.
- `dateTimeProviderRef`: name of the bean providing the current timestamp.

`modifyOnCreate` defaults to true, meaning modification fields can also be populated on initial creation. If set to false, modification metadata is not set during creation under this configuration. `setDates` defaults to enabling date field population.

## 5. Providing the Auditor with AuditorAware

The auditor is the actor performing a write operation. In web applications using Spring Security, the auditor is typically obtained from the current Authentication.

Example:

~~~java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Configuration
public class AuditorConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> {
            Authentication authentication =
                    SecurityContextHolder.getContext().getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()
                    || authentication instanceof AnonymousAuthenticationToken) {
                return Optional.empty();
            }

            return Optional.ofNullable(authentication.getName());
        };
    }
}
~~~

Explanation:
1. Obtain Authentication from SecurityContextHolder.
2. If there is no authentication, it is unauthenticated, or it is anonymous, return Optional.empty().
3. If authenticated, use authentication.getName() as the auditor.
4. Spring Data assigns that value to the CreatedBy/LastModifiedBy fields.

This configuration requires Spring Security in the application. If the project does not use Spring Security, implement AuditorAware using an appropriate source, such as the application's user context, tenant information, or a service that identifies the current actor.

Do not return an assumed username for every request. If no auditor exists, decide explicitly whether the auditor field is nullable or whether the application requires a system account. Database constraints and business rules must be consistent with that choice.

## 6. Auditors for Background Tasks and System Processes

Not every write operation originates from an HTTP request. Data can also be created by:
- Schedulers.
- Batch imports.
- Message consumers.
- Synchronization tasks.
- Maintenance jobs.
- Automated workflows.

These flows may not have a SecurityContext. In those cases, `AuditorAware` can return Optional.empty() or use a system identifier following application conventions, such as `system`, `batch-import`, or a service account ID.

Example of a simple provider with a fallback for non-user tasks:

~~~java
@Bean
AuditorAware<String> auditorAware() {
    return () -> {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return Optional.of("system");
        }

        return Optional.ofNullable(authentication.getName());
    };
}
~~~

The `system` fallback is only an illustrative policy. Real systems may need to distinguish batches, schedulers, and service accounts for more accurate traceability.

With asynchronous processing, a new thread does not necessarily inherit the calling thread's SecurityContext. Do not rely on the context always being present in schedulers or message listeners. Propagate the actor identity through message/job metadata or explicitly provide a system auditor.

## 7. Using DateTimeProvider to Control Time

By default, Spring Data uses the current time source. You can provide a DateTimeProvider if you want to standardize timezones, use a Clock for testing, or control the time source.

Example using UTC Instant:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;

@Configuration
public class AuditingTimeConfiguration {

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider dateTimeProvider(Clock auditingClock) {
        return () -> Optional.of(Instant.now(auditingClock));
    }
}
~~~

Wire the bean into auditing:

~~~java
@Configuration
@EnableJpaAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "dateTimeProvider"
)
public class JpaAuditingConfiguration {
}
~~~

DateTimeProvider returns an Optional of TemporalAccessor. Instant implements TemporalAccessor, so it can be used directly with Instant audit fields.

Using Clock instead of scattering Instant.now() calls enables tests to control time. In production environments, Clock.systemUTC() is a common choice; database column types and JDBC mappings still need to be configured consistently.

## 8. Creating a Shared Base Class with @MappedSuperclass

If multiple Entities share the same four audit fields, you can declare them in a base class:

~~~java
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
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @CreatedBy
    @Column(name = "created_by", updatable = false)
    private String createdBy;

    @LastModifiedDate
    @Column(name = "last_modified_at")
    private Instant lastModifiedAt;

    @LastModifiedBy
    @Column(name = "last_modified_by")
    private String lastModifiedBy;

    public Instant getCreatedAt() {
        return createdAt;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }

    public String getLastModifiedBy() {
        return lastModifiedBy;
    }
}
~~~

Meaning:
- `@MappedSuperclass` indicates this class provides mappings for child Entities, but is not itself an independent Entity that can be queried.
- Fields are inherited and mapped into each child Entity's table.
- `@EntityListeners` registers AuditingEntityListener for Entities using the base class.
- `updatable = false` prevents JPA from including createdAt/createdBy in regular UPDATE statements after creation.
- Getters allow the application to read audit metadata without exposing arbitrary setters.

JPA allows mappings and entity listeners to be declared on a mapped superclass to apply to inheriting Entities. Once the listener is registered on the base class, there is no need to repeat the same listener on every child Entity unless there is a clear mapping reason.

## 9. Extending the Audit Base Class in Entities

Example of Customer and PurchaseOrder sharing AuditableEntity:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer extends AuditableEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder extends AuditableEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String orderNumber;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }
}
~~~

Both the customers and purchase_orders tables have the audit columns from the inherited mapping. Each Entity can add its own business properties without redeclaring createdAt, createdBy, lastModifiedAt, and lastModifiedBy.

If the base class contains fields whose names collide with properties of a child Entity, handle the mapping explicitly via appropriate overrides or property renaming. Do not inadvertently map two properties to the same column.

## 10. @MappedSuperclass vs. @Entity Inheritance

Do not confuse `@MappedSuperclass` with an Entity in a JPA inheritance strategy.

| Characteristic | @MappedSuperclass | Entity inheritance |
|---|---|---|
| Has its own table | No | Depends on inheritance strategy |
| Can be queried directly | No | Can query the root Entity |
| Purpose | Share mappings/properties | Model Entity inheritance relationships |
| Inherited fields | Mapped into child Entity tables | Mapped per inheritance strategy |
| Use for audit fields | Very suitable | Possible, but usually more complex than necessary |

For a class that only shares audit metadata, `@MappedSuperclass` is usually simpler because it does not create a root Entity to manage in the persistence context.

If the domain genuinely has an is-a relationship between Entities and needs polymorphic queries by parent type, choose a JPA inheritance strategy such as SINGLE_TABLE, JOINED, or TABLE_PER_CLASS. Do not use Entity inheritance solely to reuse four audit fields.

## 11. Where to Place @EntityListeners

There are two common approaches:

**Registering on each Entity**

~~~java
@Entity
@EntityListeners(AuditingEntityListener.class)
public class Customer {
}
~~~

This approach makes the listener immediately visible on the Entity, but must be repeated on every Entity needing auditing.

**Registering on a mapped superclass**

~~~java
@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class AuditableEntity {
}
~~~

Child Entities share the mapping and listener. This is usually cleaner when most Entities in a module need auditing.

Pick one consistent convention. Avoid registering the same listener redundantly on both the base class and child Entities without understanding JPA callback ordering and inheritance behavior. If a special Entity should not inherit the superclass listener, JPA provides an annotation to exclude superclass listeners; follow the mapping rules and test on your project's provider.

## 12. Access Type: Field Access vs. Property Access

JPA determines the access type based on where mapping annotations such as `@Id` are placed, unless explicitly specified via `@Access`.

If Entities use field access (placing `@Id` on fields), mapping annotations in the mapped superclass should be consistent with field access. For example, AuditableEntity places `@CreatedDate` and `@Column` directly on fields as shown earlier.

If the project uses property access (placing `@Id` on getters), design the audit class using property access accordingly or declare `@Access` explicitly. Mixing annotations across fields and getters unintentionally can cause the provider to ignore mappings or throw errors.

Keep a consistent access strategy across an Entity hierarchy. If the base class and subclass need different access strategies, configure and verify them explicitly according to Jakarta Persistence.

## 13. Table Creation and Migrations for Audit Columns

A mapped superclass does not create its own table. Each child Entity needs the corresponding columns in its own table.

Illustrative DDL example:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by VARCHAR(100),
    last_modified_at TIMESTAMP WITH TIME ZONE,
    last_modified_by VARCHAR(100)
);
~~~

Exact SQL types depend on the database. `Instant` can map to a timestamp type appropriate for the dialect/JDBC driver; check the actual schema rather than assuming every database uses the same type.

In production, manage schemas with Flyway or Liquibase. `@Column(nullable = false)` and `updatable = false` describe mappings for JPA/schema generation; they do not automatically alter an existing table if the application does not run schema updates.

If createdAt is NOT NULL, auditing must be enabled and the listener must run before INSERT. When importing legacy data or writing via direct SQL, supply appropriate created_at values or design suitable defaults/nullability/migrations.

## 14. When Are Audit Fields Updated?

Auditing is tied to JPA lifecycle callbacks:

- When an Entity is persisted for the first time, creation fields are set.
- When an Entity is updated and the update callback runs, modification fields are updated.
- With `modifyOnCreate = true`, modification fields may also be set on initial creation.
- With `modifyOnCreate = false`, modification fields are not set during creation under auditing configuration.

Updating depends on the Entity actually going through the JPA lifecycle. A loaded Entity whose properties are modified and then flushed/committed will have its update processed by the provider when changes need to be written.

Not every database operation triggers entity listeners:
- JPQL bulk UPDATE/DELETE operates directly on data sets and bypasses per-Entity lifecycle callbacks.
- Native SQL also does not invoke AuditingEntityListener.
- Direct JDBC does not trigger JPA callbacks.
- Modifying a child Entity does not necessarily mark the parent Entity dirty and update the parent's lastModifiedAt.

When using bulk updates, update audit fields explicitly in the query or update Entities individually through the persistence context if listeners are required. After a bulk operation, consider clearing/refreshing the persistence context so managed Entities do not retain stale data.

## 15. Distinguishing Auditing from Custom @PrePersist and @PreUpdate

JPA allows declaring custom lifecycle callbacks:

~~~java
@PrePersist
void onCreate() {
    createdAt = Instant.now();
}

@PreUpdate
void onUpdate() {
    lastModifiedAt = Instant.now();
}
~~~

Writing callbacks manually may suffice for small applications, but often leads to:
- Duplicated code across many Entities.
- No standard mechanism to obtain the current auditor.
- Difficulty swapping the time source in tests.
- Different Entities potentially implementing inconsistent rules.
- Difficulty integrating with Spring Security or background tasks.

Spring Data Auditing provides the listener, handler, AuditorAware, and DateTimeProvider to unify this logic. Avoid assigning the same audit field in a custom callback while also letting AuditingEntityListener assign it, as the two mechanisms may overwrite each other depending on callback order.

If specialized rules are needed, extend the design deliberately and ensure only one mechanism is responsible for each field.

## 16. Complete Configuration for Spring Boot 3

Combined configuration example using Jakarta Persistence, auditor from Spring Security, and UTC time:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Configuration
@EnableJpaAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "dateTimeProvider",
        modifyOnCreate = true
)
public class JpaAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> {
            Authentication authentication =
                    SecurityContextHolder.getContext().getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()
                    || authentication instanceof AnonymousAuthenticationToken) {
                return Optional.empty();
            }

            return Optional.ofNullable(authentication.getName());
        };
    }

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider dateTimeProvider(Clock auditingClock) {
        return () -> Optional.of(Instant.now(auditingClock));
    }
}
~~~

If not using Spring Security, replace the auditorAware bean with an implementation retrieving the actor from a custom context/service. If creator/modifier tracking is not needed, omit auditorAware and use only the date annotations.

Place the configuration in a component-scanned package or import it explicitly. With multiple persistence units, verify that the auditing configuration applies to the intended EntityManagerFactory and mapping context; do not assume one configuration automatically applies uniformly across all datasources.

## 17. Testing Auditing on Entity Creation

A repository test can verify that date and auditor fields are populated on persist.

Example:

~~~java
@DataJpaTest
@Import(JpaAuditingConfiguration.class)
class CustomerAuditingTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void setsAuditFieldsWhenCustomerIsCreated() {
        Customer customer = customerRepository.save(
                new Customer("An")
        );

        assertNotNull(customer.getCreatedAt());
        assertNotNull(customer.getLastModifiedAt());
    }
}
~~~

This is an illustrative structure. If the auditor configuration reads from Spring Security, the test must set up Authentication or use a fixed test AuditorAware. If the project uses Spring Boot 3, persistence annotations must belong to the `jakarta.persistence` package.

To verify data has been written to the database, flush and reload the Entity after clearing the persistence context:

~~~java
customerRepository.save(customer);
entityManager.flush();
entityManager.clear();

Customer reloaded = customerRepository.findById(customer.getId())
        .orElseThrow();

assertNotNull(reloaded.getCreatedAt());
~~~

Flushing synchronizes pending changes to the database, but does not mean committing. In tests wrapped in an enclosing transaction, data may still roll back when the test finishes.

## 18. Testing Auditors and Entity Updates

To verify CreatedBy and LastModifiedBy, configure a test auditor with deterministic values. You can use a test AuditorAware returning `Optional.of("test-user")`, or set up Spring Security Authentication.

Cases worth testing:
1. Create Entity: createdAt and createdBy are populated.
2. Create Entity with default modifyOnCreate: lastModifiedAt and lastModifiedBy are populated if an auditor is present.
3. Update Entity: lastModifiedAt and lastModifiedBy change to reflect the current actor.
4. No auditor present: verify Optional.empty() behavior and schema nullability.
5. Background tasks: auditor is the system/service account per policy.
6. Bulk JPQL update: listener does not run automatically; the update statement must manage audit fields itself.
7. Multiple Entities extending mapped superclass: all share the same mapping and listener.
8. Special Entity excluding superclass listeners: verify it does not receive unintended audit callbacks.

When testing update timestamps, avoid assuming two clock calls always differ if the database stores timestamps with limited precision. You can inject a controllable Clock in tests or assert timestamps within database precision.

## 19. Common Pitfalls

**Adding @CreatedDate but forgetting to enable @EnableJpaAuditing**

The annotation does not activate itself. Enable auditing in Spring configuration.

**Forgetting to register AuditingEntityListener**

If the listener is not invoked, audit fields may remain null. Register the listener on the Entity or mapped superclass.

**Using @MappedSuperclass expecting a separate table**

A mapped superclass only shares mappings; tables are created for child Entities.

**AuditorAware generic type does not match @CreatedBy field**

For example, AuditorAware<Long> with a String createdBy can cause conversion or mapping errors. Use matching data types.

**SecurityContext does not exist in batch or async execution**

Background threads may not have an Authentication. Return Optional.empty() or provide a system auditor per policy.

**Registering the listener redundantly**

Placing the listener on the superclass and registering it again on every child Entity may cause callbacks to execute multiple times depending on inheritance configuration. Pick one clear registration point and test it.

**Bulk update does not update audit fields**

JPQL bulk DML and native SQL bypass entity lifecycle callbacks. Update audit fields in the query or update via Entities.

**Assuming modifying a child Entity always updates the parent Entity's timestamp**

JPA only invokes update callbacks for Entities that are actually updated. If the parent's timestamp must change when a child collection changes, design that behavior explicitly.

**Storing LocalDateTime without a timezone convention**

LocalDateTime contains no timezone. Use Instant or define clear time conversion rules.

**Using @Column(nullable = false) when an existing schema lacks the columns**

Database migrations are required before the application writes Entities. Annotations do not replace production migrations.

**Using both AuditingEntityListener and manual assignment in @PrePersist/@PreUpdate**

The two mechanisms can overwrite each other. Designate a single authoritative source for each field.

## 20. Implementation Process for Shared Auditing

When adding auditing to a module:

1. Determine whether you need timestamps, auditors, or both.
2. Choose consistent data types: typically Instant for timestamps and String/Long for auditors.
3. Create an abstract `@MappedSuperclass` holding the audit fields.
4. Place `@EntityListeners(AuditingEntityListener.class)` on the base class or each Entity following a unified convention.
5. Enable `@EnableJpaAuditing` in Spring configuration.
6. Provide `AuditorAware<T>` if using CreatedBy/LastModifiedBy.
7. Provide `DateTimeProvider` if a controllable time source is needed.
8. Have business Entities extend the audit base class.
9. Create migrations for audit columns on each Entity table.
10. Check access types and avoid duplicate mappings.
11. Test creation, update, empty auditor, background tasks, and multiple child Entities.
12. Audit bulk JPQL/native SQL because those operations do not invoke the listener.
13. Verify actual audit data on the target database.

## 21. Conclusion

Spring Data JPA Auditing uses `AuditingEntityListener` to connect JPA lifecycle callbacks with `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, and `@LastModifiedBy`. The application must enable `@EnableJpaAuditing`; if recording the actor, provide `AuditorAware<T>`, and if controlling time, provide `DateTimeProvider`. Placing fields and the listener in a `@MappedSuperclass` lets multiple Entities inherit the same mapping without creating a separate base table. Standardize data types, access strategy, schema migrations, and background-task auditor policies. Bulk JPQL/native SQL does not trigger entity listeners, so update audit fields explicitly there. Test creation, modification, and special write paths to ensure metadata accurately reflects the data lifecycle.