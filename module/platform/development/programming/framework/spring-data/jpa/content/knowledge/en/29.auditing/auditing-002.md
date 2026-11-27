# @CreatedDate, @LastModifiedDate, and Choosing the Right Temporal Type

Spring Data JPA Auditing automatically records when an entity is created and when it was last modified. Instead of manually setting date and time in every service, you declare annotations on the entity and enable auditing in Spring configuration.

The two commonly used temporal annotations are:

- **@CreatedDate**: records the timestamp when the entity is created.
- **@LastModifiedDate**: records the timestamp when the entity is last modified. With the default configuration, this field is also set when the entity is created.

For audit data that needs to represent a consistent point in time across the entire system, **java.time.Instant** is usually the right choice. However, the temporal type must accurately reflect business semantics and how the database stores timestamps.

## 1. How Does Spring Data JPA Auditing Work?

Auditing is Spring Data's mechanism for automatically populating metadata fields during the entity lifecycle. For JPA, Spring provides **AuditingEntityListener** to participate in entity lifecycle callbacks.

Basic flow:

~~~text
Application calls repository.save(entity)
              |
              v
JPA manages entity in persistence context
              |
              v
Entity is persisted or updated
              |
              v
AuditingEntityListener receives lifecycle callback
              |
              v
AuditingHandler populates createdDate / lastModifiedDate
              |
              v
JPA flushes INSERT or UPDATE to database
              |
              v
Transaction commits
~~~

Auditing is not enabled automatically just because the project has the Spring Data JPA dependency. You must enable the feature with **@EnableJpaAuditing** and register the listener for the entity or mapped superclass to be tracked.

The **@CreatedDate** and **@LastModifiedDate** annotations belong to the **org.springframework.data.annotation** package. The JPA listener belongs to **org.springframework.data.jpa.domain.support**.

## 2. Enabling Auditing in the Application

Create a Spring configuration class:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing
public class JpaAuditingConfiguration {
}
~~~

**@EnableJpaAuditing** registers the auditing infrastructure for Spring Data JPA. This configuration should reside in a package scanned by Spring component scan, or be explicitly imported into the application context.

If the project already has a suitable configuration class, you can place the annotation on that class. There is no need to declare it multiple times across multiple configuration classes.

### 2.1. Registering AuditingEntityListener

JPA needs to know which listener will handle lifecycle callbacks. Declare it on the entity:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class Article {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
}
~~~

In real examples, audit fields are declared in the entity. When multiple entities need auditing, you should group shared fields into a **@MappedSuperclass** to avoid code duplication.

## 3. Declaring @CreatedDate and @LastModifiedDate

The example below uses **Instant** for both creation and modification timestamps:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.MappedSuperclass;
import java.time.Instant;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class AuditedEntity {

    @CreatedDate
    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    @LastModifiedDate
    @Column(nullable = false)
    private Instant lastModifiedAt;

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }
}
~~~

A business entity extending the audit base class:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Article extends AuditedEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    protected Article() {
    }

    public Article(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void rename(String title) {
        this.title = title;
    }
}
~~~

When the entity is created and saved, the listener populates **createdAt** and **lastModifiedAt**. When an existing entity is modified and JPA actually issues an UPDATE, the listener updates **lastModifiedAt**. The **createdAt** field is protected at two layers:

- **@CreatedDate** is responsible for recording the creation time.
- **updatable = false** instructs JPA not to include this column in UPDATE statements generated by the entity manager.

**updatable = false** is a JPA mapping attribute; it is not an absolute database-level safeguard against native SQL or statements executed outside the application. If immutability at the database level is required, you can add appropriate permissions, triggers, or schema rules.

### 3.1. When Are Timestamps Recorded?

With the default configuration **modifyOnCreate = true**:

| Entity State | @CreatedDate | @LastModifiedDate |
|---|---|---|
| Initial persist | Set | Set |
| Update existing entity | Preserved | Updated |
| No changes written by JPA | Preserved | Usually unchanged |
| Bulk JPQL/native UPDATE | Listener does not run automatically | Listener does not run automatically |

If business logic does not want the modified date set upon creation, you can configure:

~~~java
@Configuration
@EnableJpaAuditing(modifyOnCreate = false)
public class JpaAuditingConfiguration {
}
~~~

In that case, auditing does not mark the entity as modified during initial creation. Choose the configuration that matches the semantics of your fields and your system's conventions.

## 4. Choosing the Right Temporal Type

The Java type determines the semantics of temporal data before considering how Hibernate/JDBC maps it to the database.

| Java Type | Meaning | When to Use |
|---|---|---|
| **Instant** | A point on the global timeline, represented in UTC | Audit logs, creation/update timestamps, system events |
| **OffsetDateTime** | Date and time with a UTC offset, e.g., +07:00 | When you need to preserve a known offset alongside the point in time |
| **LocalDateTime** | Local date and time without time zone or offset | Appointments or local business hours when the zone is managed separately |
| **LocalDate** | Date only, without time | Birthdates, effective dates, accounting dates |
| **ZonedDateTime** | Date and time attached to a ZoneId such as Asia/Ho_Chi_Minh | Region-based calendar logic; verify provider/database mapping and storage support |

### 4.1. Why Is Instant Usually Suitable for Auditing?

Suppose a system has users in Vietnam, Japan, and the US. When storing the time a record was created, we usually want every service to interpret it as the exact same moment, regardless of which time zone the server or user is in.

**Instant** represents a point in time on the UTC timeline. For example:

~~~java
Instant createdAt = Instant.parse("2026-11-09T13:00:00Z");
~~~

This is 13:00 UTC. When displaying it to a user in the Vietnam time zone (UTC+07:00), the application can convert it to 20:00 on the same day:

~~~java
ZonedDateTime vietnamTime = createdAt.atZone(
    ZoneId.of("Asia/Ho_Chi_Minh")
);
~~~

Storing a canonical point in time and converting at the presentation layer helps avoid confusion when a system spans multiple time zones or moves servers across regions.

### 4.2. When Should You Not Use LocalDateTime?

**LocalDateTime** contains no time zone or offset. Two values of 20:00 on the same day in Vietnam and another region can represent two different instants, yet LocalDateTime itself cannot distinguish them.

If using LocalDateTime for audit timestamps, the development team must enforce a consistent time zone convention wherever data is created, stored, and read. For events that need to be compared, sorted, or synchronized across regions, Instant is usually safer.

### 4.3. Database and Timestamp Precision

Even when Java uses Instant, column types and storage behavior still depend on the database, JDBC driver, Hibernate dialect, and time zone configuration. Some databases normalize timestamps to UTC; some column types store an offset/zone and some do not.

You should standardize on:

- Storing audit timestamps in UTC or a clearly documented convention.
- Using a database column type appropriate for the deployed dialect.
- Configuring time zones consistently across the application, JDBC, and the database.
- Checking the column's fractional-second precision. A database might only store microseconds or milliseconds, so the value read back may not retain full nanosecond precision from the original Instant.
- Converting to the user's time zone at the presentation layer rather than manually adding/subtracting hours before saving.

Do not use **@Temporal** for java.time types such as Instant or LocalDateTime. **@Temporal** is intended for legacy date/time types such as **java.util.Date** and **java.util.Calendar**.

## 5. Controlling the Time Source with Clock

By default, Spring Data Auditing obtains the current time from the default provider. In systems requiring deterministic testing or a unified time source, you can provide a **DateTimeProvider**.

~~~java
import java.time.Clock;
import java.time.temporal.TemporalAccessor;
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing(dateTimeProviderRef = "auditingDateTimeProvider")
public class JpaAuditingConfiguration {

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditingDateTimeProvider(Clock auditingClock) {
        return () -> Optional.<TemporalAccessor>of(
            auditingClock.instant()
        );
    }
}
~~~

**Clock.systemUTC()** creates a time source in UTC. DateTimeProvider returns the current instant for AuditingHandler to assign to annotated fields.

Benefits of this approach:

- Provides a unified time source across the application.
- Allows replacing Clock with **Clock.fixed(...)** in integration tests.
- Tests do not depend on the wall clock of the test runner machine.
- Enables controlling time in creation and update test scenarios.

Example creating a fixed Clock in tests:

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-11-09T13:00:00Z"),
    ZoneOffset.UTC
);
~~~

To test **@LastModifiedDate**, the test needs to change the instant supplied by the Clock between persist and update. You can use a controllable Clock or replace DateTimeProvider with a test-specific implementation. After writing data, flush, clear the persistence context, and reload the entity to verify values from the database rather than only checking the in-memory object.

## 6. Combining Auditing with createdBy and lastModifiedBy

In addition to timestamps, Spring Data Auditing also supports storing the creator and modifier:

- **@CreatedBy**: who created the entity.
- **@LastModifiedBy**: who last modified the entity.

To populate these fields, you need to provide an **AuditorAware<T>**. For example, an application can retrieve the username from Spring Security:

~~~java
@Bean
AuditorAware<String> auditorAware() {
    return () -> Optional.ofNullable(
        SecurityContextHolder.getContext().getAuthentication()
    )
    .filter(Authentication::isAuthenticated)
    .map(Authentication::getName);
}
~~~

A complete configuration needs to import the Spring Security types and declare the bean in the application context. **@EnableJpaAuditing** will use the appropriate AuditorAware; if multiple beans exist, you can specify the name explicitly using the **auditorAwareRef** attribute.

Example audit fields:

~~~java
@CreatedBy
@Column(updatable = false)
private String createdBy;

@LastModifiedBy
private String lastModifiedBy;
~~~

If the application has background tasks not tied to a logged-in user, AuditorAware should define how to represent the system actor, such as a service account or an agreed-upon identifier. Do not rely on an Authentication always being present if batch jobs also write entities.

## 7. Operations That Can Bypass Auditing

AuditingEntityListener operates on the entity lifecycle managed by JPA. Certain data modification operations do not go through per-entity lifecycle callbacks.

### 7.1. Bulk JPQL UPDATE

Example:

~~~java
@Modifying
@Query("update Article a set a.title = :title where a.id = :id")
int renameDirectly(
    @Param("id") Long id,
    @Param("title") String title
);
~~~

This is a bulk update. JPA sends an UPDATE statement directly to the database instead of loading each entity, mutating the object, and running callbacks per record. Therefore, **@LastModifiedDate** is not updated automatically by the listener.

If you still need to update the timestamp in a bulk query, you must set that field directly in the statement:

~~~java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Query("""
    update Article a
       set a.title = :title,
           a.lastModifiedAt = :modifiedAt
     where a.id = :id
    """)
int renameDirectly(
    @Param("id") Long id,
    @Param("title") String title,
    @Param("modifiedAt") Instant modifiedAt
);
~~~

In this example, the caller must pass the timestamp from the application's unified Clock source. Clearing the persistence context helps avoid continuing to use managed entities that have become stale after the bulk update. Consider transaction boundaries and flushing before executing bulk queries.

### 7.2. Native SQL and Operations Outside JPA

Native SQL statements, stored procedures, ETL jobs, or other applications writing directly to the database also do not invoke AuditingEntityListener. If multiple systems write to the same table, agree on who is responsible for updating audit timestamps. You can use database triggers, or require every writer to actively update audit fields according to a shared convention.

Avoid using both Spring auditing and a database trigger to overwrite the same field without clearly defining the authoritative source. If two places use different time zones or precisions, the results can become unpredictable.

## 8. Testing Auditing

An integration test should verify both fields at different points in time:

1. Create a new entity and call repository.save(...).
2. Call repository.flush() to force synchronization.
3. Clear the persistence context with EntityManager.clear().
4. Reload the entity and assert that createdAt and lastModifiedAt have been set.
5. Advance the Clock or DateTimeProvider to a later point in time.
6. Load the entity, modify a property, flush, and clear.
7. Reload and assert that createdAt is unchanged and lastModifiedAt is updated.

Several notes when writing tests:

- Use a database close to production to verify timestamp mapping and column precision.
- Do not compare nanoseconds if the database only stores lower precision.
- Do not assert only on the just-saved instance because it may still reside in the persistence context.
- Also test the case where the entity is not dirty to understand when the provider issues an UPDATE.
- Have dedicated tests for bulk JPQL/native queries because the listener does not automatically update audit fields in these operations.

## 9. Common Pitfalls and Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| createdAt or lastModifiedAt remains null | @EnableJpaAuditing is not enabled | Add auditing configuration to the application context |
| Listener is not invoked | Entity has not registered AuditingEntityListener | Add @EntityListeners or place the listener on a mapped superclass |
| Subclass entity lacks audit fields | Superclass is not @MappedSuperclass or mapping is incorrect | Check inheritance and JPA mapping |
| lastModifiedAt does not change | Entity is not dirty or no UPDATE is issued | Check dirty checking and actual SQL |
| Bulk update does not change audit timestamp | Bulk JPQL/native SQL bypasses entity callbacks | Set timestamp directly in the query or update entity via JPA |
| createdAt is modified unexpectedly | Setter or logic overwrites creation field | Restrict setters, use updatable=false, and control writers |
| Time discrepancy across environments | Inconsistent time zone or Clock configuration | Standardize on UTC and check JDBC/database |
| Flaky time-based tests | Tests depend on wall clock or database precision | Use a fixed/controllable Clock and compare at column precision |

Some errors also stem from the auditing configuration not being included in the test application context, or the entity listener being placed on a class that does not participate in mapping. When debugging, inspect the Spring configuration, entity mapping, and SQL lifecycle before adding manual setters.

## 10. Implementation Checklist

- [ ] Enabled **@EnableJpaAuditing** in the application context.
- [ ] Entity or **@MappedSuperclass** declares **@EntityListeners(AuditingEntityListener.class)**.
- [ ] Imported the correct **org.springframework.data.annotation.CreatedDate** and **LastModifiedDate**.
- [ ] Selected temporal type based on business semantics; prefer **Instant** for system-wide audit events.
- [ ] Creation timestamp field is protected against unintended updates.
- [ ] Standardized time zone and precision across Java, JDBC, and the database.
- [ ] Reviewed bulk JPQL, native SQL, and writers outside JPA.
- [ ] Integration tests flush, clear, and reload data from the database.
- [ ] If createdBy/lastModifiedBy are needed, configured **AuditorAware** and an actor for background tasks.

## 11. Key Takeaways

**@CreatedDate** stores when an entity was created; **@LastModifiedDate** stores when an entity was last modified. Both require auditing to be enabled and the JPA entity listener to be registered. For audit data that must be compared across multiple servers or time zones, **Instant** is usually the clearest choice because it represents a point on the UTC timeline.

Auditing runs according to the JPA entity lifecycle. Changes made via bulk queries, native SQL, or external tools bypass the listener, so timestamps must be updated intentionally through an explicit mechanism. Test against a real or production-equivalent database to verify time zones, precision, and callback behavior.
