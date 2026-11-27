# Deterministic Testing of Time and Actors

In **Spring Data Relational JDBC**, auditing records who created or updated an entity and when the operation occurred. The `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, and `@LastModifiedDate` annotations allow Spring Data to populate metadata when saving aggregates.

By default, auditing obtains the current time and actor from providers in the `ApplicationContext`. That works well in live runs, but can cause tests to depend on the system clock, timezone, `SecurityContext`, or execution order. A good test needs control over two inputs:

- **Time:** provide a `DateTimeProvider` returning a timestamp chosen by the test.
- **Actor:** provide an `AuditorAware<T>` returning an actor chosen by the test.

When both providers are controlled, tests can assert exact metadata on insert and update, verify `createdAt` is not overwritten, confirm `lastModifiedAt` changes, and test cases with no actor. There is no need to wait for the wall clock to advance or rely on whichever account is logged into the test machine.

## 1. Where Does Auditing Operate in Spring Data JDBC?

Auditing is part of the persistence/mapping lifecycle managed by Spring Data. When a repository or `JdbcAggregateTemplate` saves an aggregate, the auditing infrastructure can populate annotated fields before data is written.

| Annotation | Meaning |
| --- | --- |
| `@CreatedBy` | Creator of the entity |
| `@CreatedDate` | Creation timestamp of the entity |
| `@LastModifiedBy` | Actor of the most recent save |
| `@LastModifiedDate` | Timestamp of the most recent save |

Entity example:

```java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.relational.core.mapping.Table;

@Table("audited_document")
public class AuditedDocument {

    @Id
    private Long id;

    private String title;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedAt;

    protected AuditedDocument() {
    }

    public AuditedDocument(String title) {
        this.title = title;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getCreatedBy() { return createdBy; }
    public Instant getCreatedAt() { return createdAt; }
    public String getLastModifiedBy() { return lastModifiedBy; }
    public Instant getLastModifiedAt() { return lastModifiedAt; }
}
```

`String` is used for the actor to keep the example simple. If the application uses a `UserId` type or user entity, the generic type of `AuditorAware<T>` must be compatible with the property types annotated with `@CreatedBy` and `@LastModifiedBy`.

`Instant` fits well when storing an absolute point in time. Spring Data also supports several other Java date/time types; choose a type compatible with the application's schema and JDBC driver.

## 2. Enabling Auditing for Spring Data JDBC

Add `@EnableJdbcAuditing` to configuration:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing
public class JdbcAuditingConfiguration {
}
```

If an entity only has `@CreatedDate` and `@LastModifiedDate`, the application is not required to provide an `AuditorAware`. When using `@CreatedBy` or `@LastModifiedBy`, the auditing infrastructure needs an `AuditorAware` to resolve the current actor.

Example configuring both providers explicitly:

```java
import java.time.Clock;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Configuration
@EnableJdbcAuditing(
        dateTimeProviderRef = "dateTimeProvider",
        auditorAwareRef = "auditorAware"
)
public class JdbcAuditingConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider dateTimeProvider(Clock applicationClock) {
        return () -> Optional.of(applicationClock.instant());
    }

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

            return Optional.of(authentication.getName());
        };
    }
}
```

`DateTimeProvider` returns `Optional<TemporalAccessor>`. The example uses `Clock` so the clock can be swapped in tests; production uses `Clock.systemUTC()`. `AuditorAware<String>` extracts the principal name from Spring Security and returns `Optional.empty()` when no valid user is present.

If the system does not use Spring Security, replace the `AuditorAware` implementation with the application's actor-resolution mechanism, such as a user context, request context, or a system actor for batch jobs.

### 2.1. Configuring modifyOnCreate

`@EnableJdbcAuditing` has a `modifyOnCreate` attribute. The default value is `true`, meaning the entity is considered modified immediately upon creation:

- `@CreatedDate` and `@CreatedBy` are set on insert.
- `@LastModifiedDate` and `@LastModifiedBy` are also set on insert if `modifyOnCreate = true`.

If you want modified fields to have values only after the first update, configure:

```java
@EnableJdbcAuditing(
        dateTimeProviderRef = "dateTimeProvider",
        auditorAwareRef = "auditorAware",
        modifyOnCreate = false
)
```

Tests must reflect this policy. Do not write assertions on `lastModifiedAt` at insert time while forgetting that the project intentionally disabled `modifyOnCreate`.

## 3. Why Should Tests Not Rely on the System Clock?

A test like:

```java
AuditedDocument saved = repository.save(new AuditedDocument("draft"));

assertThat(saved.getCreatedAt()).isCloseTo(
        Instant.now(),
        within(1, ChronoUnit.SECONDS)
);
```

can pass on one machine yet fail on another due to system clock skew or adjustments, slow CI runs, differences between database timestamp precision and `Instant` precision, parallel tests making ordering unpredictable, or mismatched JVM/database timezones.

Do not use `Thread.sleep()` to wait for `lastModifiedAt` to differ from `createdAt`. Sleeping makes tests slow and still fails to guarantee distinct timestamps if the database rounds or truncates precision.

Instead, pass a fixed timestamp to `DateTimeProvider`. The test can set `t0` for insert, then switch to `t1` before update. The result is completely deterministic.

## 4. Creating a Controllable DateTimeProvider and AuditorAware in Tests

A small test context can implement both interfaces. It holds the current instant and actor in `AtomicReference` fields, allowing tests to change values between saves:

```java
import java.time.Instant;
import java.time.temporal.TemporalAccessor;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.AuditorAware;

public class TestAuditContext
        implements DateTimeProvider, AuditorAware<String> {

    private final AtomicReference<Instant> now =
            new AtomicReference<>();

    private final AtomicReference<String> actor =
            new AtomicReference<>();

    public void set(Instant instant, String username) {
        now.set(instant);
        actor.set(username);
    }

    @Override
    public Optional<TemporalAccessor> getNow() {
        return Optional.ofNullable(now.get());
    }

    @Override
    public Optional<String> getCurrentAuditor() {
        return Optional.ofNullable(actor.get());
    }
}
```

Both interfaces are implemented by the same class so tests have a single place to control both time and actor. `AtomicReference` ensures values are read and written safely across threads, though if a test context is shared across parallel tests, each test still needs its own context or proper isolation.

Register this context in test configuration:

```java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@TestConfiguration
@EnableJdbcAuditing(
        dateTimeProviderRef = "testAuditContext",
        auditorAwareRef = "testAuditContext"
)
public class AuditingTestConfiguration {

    @Bean
    TestAuditContext testAuditContext() {
        return new TestAuditContext();
    }
}
```

Spring Data will use the `testAuditContext` bean for both roles. Tests can set the desired values before each repository operation.

If the test context also loads a production configuration annotated with `@EnableJdbcAuditing`, make sure only one suitable auditing configuration exists in the context. For test slices, import the test configuration explicitly and verify which configurations are loaded to avoid duplicate auditing infrastructure registration.

## 5. Testing Insert and Update with Fixed Time and Actors

Repository:

```java
import org.springframework.data.repository.CrudRepository;

public interface AuditedDocumentRepository
        extends CrudRepository<AuditedDocument, Long> {
}
```

Illustrative PostgreSQL schema:

```sql
CREATE TABLE audited_document (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    created_by VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE,
    last_modified_by VARCHAR(100),
    last_modified_at TIMESTAMP WITH TIME ZONE
);
```

Test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;
import org.springframework.context.annotation.Import;

@DataJdbcTest
@Import(AuditingTestConfiguration.class)
class AuditedDocumentRepositoryTest {

    private static final Instant T0 =
            Instant.parse("2026-01-10T10:00:00Z");

    private static final Instant T1 =
            Instant.parse("2026-01-10T10:05:00Z");

    @Autowired
    AuditedDocumentRepository repository;

    @Autowired
    TestAuditContext auditContext;

    @Test
    void keepsCreationMetadataAndUpdatesModificationMetadata() {
        auditContext.set(T0, "alice");

        AuditedDocument created =
                repository.save(new AuditedDocument("Draft"));

        assertThat(created.getId()).isNotNull();
        assertThat(created.getCreatedBy()).isEqualTo("alice");
        assertThat(created.getCreatedAt()).isEqualTo(T0);
        assertThat(created.getLastModifiedBy()).isEqualTo("alice");
        assertThat(created.getLastModifiedAt()).isEqualTo(T0);

        auditContext.set(T1, "bob");
        created.setTitle("Reviewed");
        repository.save(created);

        AuditedDocument reloaded = repository.findById(created.getId())
                .orElseThrow();

        assertThat(reloaded.getTitle()).isEqualTo("Reviewed");
        assertThat(reloaded.getCreatedBy()).isEqualTo("alice");
        assertThat(reloaded.getCreatedAt()).isEqualTo(T0);
        assertThat(reloaded.getLastModifiedBy()).isEqualTo("bob");
        assertThat(reloaded.getLastModifiedAt()).isEqualTo(T1);
    }
}
```

The test proves:

1. The insert uses `T0` and actor `alice`.
2. `createdBy` and `createdAt` record creation information.
3. The update uses `T1` and actor `bob`.
4. Original creation metadata is preserved.
5. Modification metadata reflects the new update.

Here `modifyOnCreate` defaults to `true`, so `lastModifiedBy` and `lastModifiedAt` also receive `alice`/`T0` at insert time. If the project sets `modifyOnCreate = false`, adjust the two creation assertions accordingly; after the update, modification metadata must still be `bob`/`T1`.

`@DataJdbcTest` typically runs tests inside a transaction and rolls back after each test. If you need to verify exact PostgreSQL types or driver-specific behavior, configure the test datasource to use the same database engine as production, such as PostgreSQL Testcontainers. For basic auditing checks, what matters is that auditing callbacks and the actual schema are loaded into the test context.

## 6. Testing DateTimeProvider with a Fixed Clock

If the application already uses `Clock` in production configuration, time can be controlled using `Clock.fixed` instead of creating a dedicated test class:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-10T10:00:00Z"),
        ZoneOffset.UTC
);
```

DateTimeProvider:

```java
DateTimeProvider dateTimeProvider(Clock clock) {
    return () -> Optional.of(clock.instant());
}
```

In tests, inject a fixed `Clock` into the auditing configuration. To test multiple points in time, use a mutable/controllable test clock or create separate contexts per operation. Do not mutate the test runner machine's system clock.

A fixed `Clock` always returns the same instant; thus it fits single-operation or insert tests very well. To test an insert followed by an update at two distinct times, you need a changeable clock or a stateful `DateTimeProvider` like `TestAuditContext`.

## 7. Testing Actors Without Relying on a Real SecurityContext

If production uses Spring Security, `AuditorAware` usually reads the principal from `SecurityContextHolder`. Repository tests do not need to spin up the entire login flow just to test auditing.

You can test in two layers:

- **Repository/auditing tests:** use `TestAuditContext` to supply simulated actors such as `alice`, `bob`, or `batch-import`.
- **Security integration/unit tests:** separately verify that the `AuditorAware` adapter reads the principal accurately from `SecurityContext`.

Example adapter test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

class SecurityAuditorAwareTest {

    private final SecurityAuditorAware auditorAware =
            new SecurityAuditorAware();

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void returnsAuthenticatedUsername() {
        var authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                        "alice",
                        "n/a",
                        List.of()
                );

        SecurityContextHolder.getContext()
                .setAuthentication(authentication);

        assertThat(auditorAware.getCurrentAuditor())
                .isEqualTo(Optional.of("alice"));
    }
}
```

`SecurityAuditorAware` is the application's implementation:

```java
import java.util.Optional;

import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

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

        return Optional.of(authentication.getName());
    }
}
```

This test verifies that the adapter retrieves the right username and cleans up `SecurityContext` after each test. It does not need a database. The repository test above verifies that auditing metadata is written to the database.

In asynchronous applications, `SecurityContext` is typically thread-bound. If work moves to an executor or message listener, propagate the actor context appropriately; otherwise, `AuditorAware` may return `Optional.empty()` even though the originating request had a user.

## 8. Testing the Absent-Actor Case

`AuditorAware<T>` returns `Optional<T>`. When there is no principal, return `Optional.empty()` rather than a fake string like `unknown` unless that is an intentional business convention.

`@CreatedBy`/`@LastModifiedBy` fields may remain unset when there is no auditor. Therefore, the schema should allow nulls if the application genuinely has system job flows without an attached user, or the provider must return an explicit system actor.

| Scenario | Suitable Actor |
| --- | --- |
| Logged-in user action | User ID or stable username |
| Scheduled job | `system:scheduler` or service account |
| Data import | `system:import` or batch ID |
| Migration | `system:migration` |
| Unknown actor and schema allows it | `Optional.empty()` |

Do not use a mutable display name as the auditor key if the application needs long-term traceability. A stable user ID is usually preferable.

## 9. Timestamp Precision, Timezones, and Test Comparisons

`Instant` represents an absolute point in time and avoids local timezone confusion. However, databases may store timestamps at lower precision than Java nanoseconds.

For example, PostgreSQL usually stores `timestamp` at microsecond precision. If a test uses:

```java
Instant expected = Instant.parse("2026-01-10T10:00:00.123456789Z");
```

the value read back may be rounded or truncated to the column/driver precision. For stable tests:

- Use whole-second or microsecond timestamps.
- Or normalize the expected value to the database's precision before comparing.
- Use `Instant`/UTC when comparing absolute points in time.
- If using `LocalDateTime`, explicitly define timezone conversion across JVM, JDBC, and database.

Example normalizing to microseconds:

```java
Instant expected = original.truncatedTo(ChronoUnit.MICROS);
```

Do not widen tolerances excessively to hide timezone or mapping bugs. The goal is to verify the exact value normalized per schema, not to make assertions always pass.

## 10. Testing modifyOnCreate

By default `modifyOnCreate = true`. If business rules want modified fields to reflect only updates after creation, set `modifyOnCreate = false` and write tests expressing that contract:

```java
@EnableJdbcAuditing(
        dateTimeProviderRef = "testAuditContext",
        auditorAwareRef = "testAuditContext",
        modifyOnCreate = false
)
```

Assertions on insert:

```java
assertThat(saved.getCreatedAt()).isEqualTo(T0);
assertThat(saved.getCreatedBy()).isEqualTo("alice");
assertThat(saved.getLastModifiedAt()).isNull();
assertThat(saved.getLastModifiedBy()).isNull();
```

After updating with `T1`/`bob`:

```java
assertThat(updated.getCreatedAt()).isEqualTo(T0);
assertThat(updated.getCreatedBy()).isEqualTo("alice");
assertThat(updated.getLastModifiedAt()).isEqualTo(T1);
assertThat(updated.getLastModifiedBy()).isEqualTo("bob");
```

Both policies are valid. What matters is that configuration and tests agree on the convention desired by the product.

## 11. Write Paths That Do Not Automatically Run Auditing Callbacks

Spring Data JDBC auditing is tied to the persistence lifecycle managed by Spring Data. If the application writes via `JdbcTemplate`, native SQL, stored procedures, or another application, Spring Data's auditing callbacks do not run automatically.

Example:

```java
jdbcTemplate.update(
        "UPDATE audited_document SET title = ? WHERE id = ?",
        "Changed directly",
        id
);
```

The SQL statement above does not automatically invoke `DateTimeProvider` or `AuditorAware`. If custom SQL needs to maintain audit columns, update those columns explicitly, or use a database trigger with an explicit actor/time convention.

When combining Spring Data repositories with direct SQL, verify every write path so records are not left with stale `lastModifiedAt` or `lastModifiedBy` values.

## 12. Delete and Audit Metadata

The `@Created...` and `@LastModified...` annotations do not automatically provide `@DeletedBy` or `@DeletedDate`. Deleting an entity via a repository does not mean Spring Data automatically saves who deleted it and when into an audit record.

If business rules require tracking deletions, you can use soft delete with `deletedAt`, `deletedBy`, and `deleted` fields; record a separate audit event; use an outbox/audit table; or use a database trigger if you want to capture every deletion at the database level.

Soft delete must be designed alongside query conditions so deleted data does not appear on normal screens. With audit events, define transaction boundaries and error handling so events are not written when deletion fails or vice versa.

## 13. Testing Auditing by Layer

| Test Layer | What It Verifies | Tools / Inputs |
| --- | --- | --- |
| `AuditorAware` unit test | Principal maps to the right actor | Simulated `SecurityContext` |
| `DateTimeProvider` unit test | Provider returns the expected timestamp | Fixed `Clock` |
| Repository slice test | Auditing annotations are applied on insert/update | `@DataJdbcTest`, test providers, database |
| Integration test | Timestamps/actors round-trip cleanly with production schema and driver | PostgreSQL/Testcontainers or target DB |
| Service test | Commands pass the right actor/time context and handle errors | Mock repositories or Spring context |

There is no need to mock `DateTimeProvider` and `AuditorAware` together in every test. Pick the right test layer for the question being answered. Repository tests should use real providers with fixed inputs; security adapter tests do not need a database.

## 14. Common Mistakes

| Symptom | Possible Cause | Remedy |
| --- | --- | --- |
| `@CreatedDate` is always null | `@EnableJdbcAuditing` not enabled or entity bypassed Spring Data persistence lifecycle | Check configuration and call repository/template |
| `@CreatedBy` is always null | Missing `AuditorAware`, missing principal, or returns `Optional.empty()` | Register an auditor provider and inspect actor context |
| Tests depend on developer's username | Reading real `SecurityContext` in repository tests | Use `TestAuditContext` or a simulated principal |
| Timestamps vary across runs | Calling `Instant.now()` or system clock directly | Inject a fixed `DateTimeProvider` or `Clock` |
| `lastModifiedAt` already set on insert | `modifyOnCreate` defaults to true | Keep behavior or set false and update tests |
| `createdAt` changes after update | Mapping/auditing misconfiguration or custom SQL overwrites creation field | Check lifecycle callbacks and all write paths |
| Timestamp assertions fail by microseconds | Database precision is lower than `Instant` nanoseconds | Use schema-aligned timestamps or truncate expected values |
| Parallel tests overwrite each other's actor | Shared mutable test context | Isolate contexts or tests; never share state across parallel tests |
| Async job lacks an auditor | `SecurityContext` not propagated to the new thread | Pass actor explicitly or use a system auditor |
| Direct SQL does not update audit fields | `JdbcTemplate` does not run auditing callbacks | Update columns explicitly or use a trigger |
| After delete, deleter info is missing | Auditing annotations do not automatically record delete metadata | Use soft delete or a separate audit event/table |

## 15. Deterministic Testing Workflow

When writing auditing tests:

1. Identify which fields need tracking: timestamp, actor, or both.
2. Enable `@EnableJdbcAuditing` in the appropriate context.
3. Choose schema-compatible audit data types, e.g., `Instant` and `String`/user ID.
4. Provide a fixed or controllable `DateTimeProvider`.
5. Provide a simulated `AuditorAware` with a deterministic actor.
6. Set `T0`/`alice` before insert and assert creation metadata.
7. Set `T1`/`bob` before update and assert creation metadata is kept while modification metadata updates.
8. Verify `modifyOnCreate` per configuration.
9. Use timestamps matching database precision.
10. If production uses custom SQL or driver-specific behavior, test those write paths separately on the target database.

## 16. Practice Exercises

**Exercise 1 — Enable auditing.** Create an entity with the four fields `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, and `@LastModifiedDate`. Enable `@EnableJdbcAuditing` and verify metadata is populated on repository insert.

**Exercise 2 — Fixed time.** Write a `DateTimeProvider` returning a fixed `Instant`. Run the test multiple times and confirm `createdAt` is always identical.

**Exercise 3 — Simulated actor.** Write an `AuditorAware<String>` returning a test-configured actor. Insert with `alice`, update with `bob`, and check all four audit fields.

**Exercise 4 — modifyOnCreate.** Run tests with `modifyOnCreate = true` and `false`. Compare `lastModifiedAt`/`lastModifiedBy` on insert and update.

**Exercise 5 — Absent principal.** Have `AuditorAware` return `Optional.empty()`. Confirm the schema and application handle null auditor fields per policy.

**Exercise 6 — Time precision.** Use a timestamp with nanoseconds, save to the database, and read it back. Identify the column's precision and normalize assertions.

**Exercise 7 — Security adapter.** Write a unit test for an `AuditorAware` implementation using `SecurityContextHolder`, confirming anonymous authentication is never recorded as a real actor.

**Exercise 8 — Direct SQL.** Update a record using `JdbcTemplate`. Observe that auditing callbacks do not run automatically, then add explicit audit metadata updates or a trigger.

### References

- [Spring Data Relational — JDBC Auditing](https://docs.spring.io/spring-data/relational/reference/jdbc/auditing.html): enabling auditing, `AuditorAware`, and metadata for Spring Data JDBC.
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html): `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, `@LastModifiedDate`, `DateTimeProvider`, and `AuditorAware`.
- [EnableJdbcAuditing API](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/jdbc/repository/config/EnableJdbcAuditing.html): `auditorAwareRef`, `dateTimeProviderRef`, `modifyOnCreate`, and `setDates`.
