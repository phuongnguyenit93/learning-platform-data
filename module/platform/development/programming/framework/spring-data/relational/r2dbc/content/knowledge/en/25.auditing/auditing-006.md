# Choosing Time Sources, Timezones, and Testing Time

Auditing in Spring Data R2DBC records milestones such as when a record was created and updated, along with who performed the operation. These values seem simple but can become difficult to control if every place calls `Instant.now()` independently, servers run in different timezones, the database uses timestamp types that do not store timezones, or tests depend on the real clock.

To achieve consistent auditing, three decisions are needed: **which time source is authoritative**, **which timezone is used to represent and store values**, and **how to test without depending on when the test runs**. In a Spring application, `Clock` and `DateTimeProvider` centralize the time source; `@EnableR2dbcAuditing` works with `@CreatedDate` and `@LastModifiedDate` to attach timestamps to entities. Choosing between an application clock and a database clock should be based on synchronization needs across writers, testability, and database semantics.

## 1. Time auditing in Spring Data R2DBC

Spring Data Relational supports auditing to automatically populate metadata when an entity is created or modified. Commonly used annotations:

| Annotation | Meaning |
|---|---|
| `@CreatedDate` | Timestamp when the entity was created |
| `@LastModifiedDate` | Timestamp when the entity was most recently modified |
| `@CreatedBy` | Actor that created the entity |
| `@LastModifiedBy` | Actor that most recently modified the entity |

Entity example:

```java
@Table("article")
public class Article {

    @Id
    private Long id;

    private String title;

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

    // Constructors, getters, and business methods.
}
```

When auditing is enabled, Spring Data callbacks can populate these fields during the entity write lifecycle. `@CreatedDate` represents the creation time; `@LastModifiedDate` represents the most recent modification time. The corresponding auditor fields store the actor, such as a username or service account.

Auditing does not automatically define a business timezone for the application. It uses the configured time source and the property's data type. Therefore, design the time source and timestamp types before enabling auditing across multiple services.

## 2. Enabling auditing for R2DBC

Activate auditing with `@EnableR2dbcAuditing` in Spring configuration:

```java
@Configuration
@EnableR2dbcAuditing
public class R2dbcAuditingConfiguration {
}
```

Then Spring Data registers auditing callbacks to populate the annotated properties when entities are written through Spring Data mapping APIs.

If you need to specify a particular time source or auditor, configure the corresponding beans:

```java
@Configuration
@EnableR2dbcAuditing(
    dateTimeProviderRef = "auditingDateTimeProvider",
    auditorAwareRef = "auditorAware"
)
public class R2dbcAuditingConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditingDateTimeProvider(Clock applicationClock) {
        return () -> Optional.of(applicationClock.instant());
    }

    @Bean
    ReactiveAuditorAware<String> auditorAware() {
        return () -> ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName);
    }
}
```

The example above uses `Clock.systemUTC()` as the time source and retrieves the username from the reactive security context. If an operation runs in a background job without a security context, `ReactiveAuditorAware` may complete empty; in that case `@CreatedBy`/`@LastModifiedBy` fields are not populated from this source. The application can provide a default service identity by policy, such as `batch-worker`, instead of assigning a fake user's username.

`DateTimeProvider` returns `Optional<TemporalAccessor>`; `ReactiveAuditorAware<T>` returns `Mono<T>`. These are two different contracts: the time source is supplied synchronously via `DateTimeProvider`, while the auditor can be resolved asynchronously from the reactive context.

If only timestamps are needed, no auditor needs to be declared. If an auditor is needed without Spring Security, `ReactiveAuditorAware` can be implemented from the application's request context or service identity.

## 3. Choosing the time source: application clock or database clock?

There are two common places where timestamps can be generated:

**Application clock:** the application reads time from the OS of the host running the service, typically via `Clock` and `DateTimeProvider`, and writes the value to the database.

**Database clock:** the SQL statement, default, or trigger obtains time from the database server and assigns it to the column.

| Criterion | Application clock | Database clock |
|---|---|---|
| Source | Clock of the application instance | Clock of the database server |
| Testing | Easy to replace with `Clock.fixed` or a mock clock | Requires a test database or DB time-control mechanisms |
| Multiple services writing to the same table | Can drift if machines are unsynchronized | One database provides a shared time source for all writers |
| When value is assigned | Usually before sending the write statement | While the database executes the statement or trigger |
| Auditing integration | Natural with `DateTimeProvider` | Requires letting the database own the column and reading values back if needed |
| Configuration dependencies | Host/VM/container clock synchronization | Database clock synchronization and RDBMS-specific semantics |

There is no single right choice for every system. An application clock is convenient for domain logic and testing. A database clock is useful when multiple applications or tools write to the same table and need a unified time source on the database side.

What matters is choosing one owner for each audit column. If an application callback writes `created_at` and a database trigger also overwrites that column, establish which value is the source of truth and how to retrieve the final value. Avoid having both layers update the same column without clear rules.

## 4. Using Clock instead of calling Instant.now() everywhere

`Clock` is Java's abstraction for a time source. It lets production code use the system clock while tests can substitute a fixed or controllable clock.

Declaring a UTC bean:

```java
@Configuration
public class TimeConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

A service using Clock via constructor injection:

```java
@Service
public class PublicationService {

    private final Clock clock;
    private final ArticleRepository repository;

    public PublicationService(Clock clock, ArticleRepository repository) {
        this.clock = clock;
        this.repository = repository;
    }

    public Mono<Article> publish(Article article) {
        Instant publishedAt = clock.instant();
        return repository.save(article.withPublishedAt(publishedAt));
    }
}
```

Do not call `Instant.now()` directly across many places if logic needs timestamp testing. When `Clock` is injected, tests can control returned values without modifying business code.

`Clock.systemUTC()` does not alter the machine's physical clock. It creates a system clock representing the current instant in UTC. This avoids depending on the JVM's default timezone when obtaining instants.

## 5. Customizing DateTimeProvider for auditing

`DateTimeProvider` is the time source Spring Data auditing uses to retrieve the current value. Combining it with `Clock` lets both business code and auditing share the same abstraction:

```java
@Configuration
@EnableR2dbcAuditing(dateTimeProviderRef = "auditingDateTimeProvider")
public class AuditingConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditingDateTimeProvider(Clock clock) {
        return () -> Optional.of(clock.instant());
    }
}
```

When another temporal type is needed, `DateTimeProvider` can return any `TemporalAccessor` compatible with the audit property. For example:

```java
@Bean
DateTimeProvider auditingDateTimeProvider(Clock clock) {
    return () -> Optional.of(OffsetDateTime.now(clock));
}
```

However, standardize data types across the entire system. `Instant` is usually suitable for audit timestamps because it represents a single point on the timeline, independent of the user's display timezone.

Do not create a `Clock.systemDefaultZone()` for one bean while calling `Instant.now()` or `LocalDateTime.now()` using the default timezone elsewhere. That makes time logic depend on environment configuration and hard to reproduce in tests.

## 6. Instant, OffsetDateTime, ZonedDateTime, and LocalDateTime

Choose the Java type based on the meaning of the data, not solely on the SQL column type.

| Java Type | Meaning | Suitable for |
|---|---|---|
| `Instant` | An absolute point on the UTC timeline | Created/modified timestamps, event times, audit logs |
| `OffsetDateTime` | Date and time with a UTC offset at that moment | API communication or data needing to preserve a known offset |
| `ZonedDateTime` | Date and time with a `ZoneId` and timezone rules | Schedules in geographical timezones, DST transitions |
| `LocalDateTime` | Local date and time, without offset/timezone | Wall-clock time when timezone context is managed separately |
| `LocalDate` | Calendar date, without time | Birth dates, invoice dates, holidays |
| `LocalTime` | Time of day, without date | Opening hours, recurring daily times |

For `created_at` and `last_modified_at`, `Instant` is usually the clearest choice. Two events on two servers in different timezones can still be compared directly because both are instants.

`LocalDateTime` cannot identify a unique instant without a timezone or offset. For example, `2026-11-15T09:00` can correspond to different moments depending on location. Do not use `LocalDateTime` as a system-wide audit timestamp if you later need to correlate logs across multiple regions.

`ZonedDateTime` contains a `ZoneId`, but many SQL column types do not store zone names like `Asia/Ho_Chi_Minh`. If business logic needs to remember the original timezone of an appointment, you can store an instant or local date-time alongside a separate zone ID column.

## 7. Storing UTC and converting to display timezones

A common convention is storing audit timestamps as instants and displaying them in the user's timezone at the API/UI layer.

Example:

```java
Instant createdAt = Instant.parse("2026-11-15T02:00:00Z");

ZonedDateTime vietnamTime = createdAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
ZonedDateTime londonTime = createdAt.atZone(ZoneId.of("Europe/London"));
```

These two `ZonedDateTime` values represent the exact same instant displayed in two different timezones. Stored audit data does not need to change simply because a user views it from another timezone.

When returning API responses, you can serialize `Instant` as ISO-8601 UTC, such as `2026-11-15T02:00:00Z`. Clients can format it according to the user's locale and timezone. If an API accepts a user-entered point in time, require an explicit offset or timezone when it represents an absolute instant.

Do not store preformatted time strings like `15/11/2026 09:00` in timestamp columns. Display strings depend on locale and cannot be safely compared or sorted like temporal types.

## 8. Choosing the right SQL column type

Database timestamp types have different semantics across database engines. Understand the column type before choosing the Java type.

### PostgreSQL

- `TIMESTAMP WITH TIME ZONE` (short name `timestamptz`) represents an instant. PostgreSQL normalizes the instant when storing; it does not retain the original timezone name or offset from the input. When displayed, values are converted according to the session's timezone.
- `TIMESTAMP WITHOUT TIME ZONE` stores date and time components as a local date-time, without a timezone.
- `DATE` stores a calendar date without time of day.

For audit timestamps, `timestamptz` is generally more suitable than `timestamp without time zone` when representing global points in time.

### MySQL

- `TIMESTAMP` has conversion rules based on the session/server timezone when writing and reading.
- `DATETIME` stores date and time components without inherently representing a timezone-aware instant.

Configure connection/session timezones consistently and verify mappings with the R2DBC MySQL driver.

### SQL Server

- `datetimeoffset` stores date and time along with an offset.
- `datetime2` stores date and time without an offset.

If you need to preserve an instant and original offset, `datetimeoffset` can fit; if storing UTC by convention, `datetime2` can also be used, provided there is a strict contract that values are always UTC.

### Type selection guidelines

| Data meaning | Recommended column type |
|---|---|
| Audit events, created/modified instants | Database's timezone/instant-capable timestamp type |
| Calendar date, no time | `DATE` |
| Local time without date | `TIME` |
| Local appointment needing wall-clock time and zone | Store local date-time with zone ID, or instant with zone ID depending on business rules |
| Database-generated timestamps | Timestamp column with appropriate default/trigger and read-only mapping when needed |

A SQL type name does not guarantee every driver maps it to the same Java class. Verify the return type of your R2DBC driver and use converters if necessary.

## 9. JVM, database, and session timezones

An application may run with a different default timezone from the database server. Furthermore, each database connection can have its own session timezone. This matters especially when using timezone-less column types or when the database converts values on read/write.

Helpful principles:

- Use `Clock.systemUTC()` for the application audit time source.
- Store audit timestamps as instants or column types with equivalent semantics.
- Configure a consistent session timezone if the database driver performs session-based conversions.
- Never rely on the JVM default timezone to interpret timestamps.
- Convert to the user's `ZoneId` in the presentation layer.
- When storing local schedules, store the zone ID alongside rather than storing `LocalDateTime` alone.

Do not assume setting `-Duser.timezone=UTC` fixes every problem. It changes the JVM default timezone, but does not configure database sessions, does not change SQL column semantics, and does not synchronize clocks across hosts.

## 10. Daylight Saving Time and ambiguous local times

Some timezones observe Daylight Saving Time (DST), meaning local clocks jump forward or fall back seasonally. When clocks jump forward, a range of local times does not occur. When clocks fall back, an hour of local times occurs twice.

For a DST-observing timezone:

- A local time falling inside the skipped gap when clocks spring forward may not map to a valid instant.
- A local time inside the repeated overlap can correspond to two different instants.

Java's `ZoneId` and `ZoneRules` provide information to detect these cases. When accepting local appointments, the application must specify how to handle nonexistent or ambiguous local times: reject them, choose the earlier/later offset, or ask the user to choose explicitly.

An audit timestamp marks when an event already happened; using `Instant` avoids DST ambiguity. Future schedules, by contrast, may mean "9 AM local time", so storing `LocalDateTime` and `ZoneId` can be more accurate than storing only an instant if timezone rules change.

Do not manually add or subtract one hour to handle DST. Timezone rules change by country and are updated in IANA data. Use `ZoneId`/`ZoneRules` instead of hardcoding offsets.

## 11. Timestamp precision and round-trip discrepancies

`Instant` has nanosecond precision in Java, but databases or drivers may store fewer fractional digits. PostgreSQL timestamps typically support up to microsecond precision; other databases have their own precision and configuration.

For example, an application generates `2026-11-15T02:00:00.123456789Z`, but a column only stores microseconds, so the value read back may be `2026-11-15T02:00:00.123457Z` or truncated per database/driver rules.

In tests, avoid exact nanosecond equality checks if the schema only stores microseconds. Normalize precision before comparing:

```java
Instant expected = clock.instant().truncatedTo(ChronoUnit.MICROS);
```

Rounding versus truncation rules depend on the database. Verify actual round-trip behavior with your driver and choose appropriate precision in the schema.

## 12. Synchronizing clocks across instances

If using an application clock, instances must have synchronized OS clocks. In cloud or container environments, clocks usually depend on the host/virtualization layer, yet you still need to monitor clock skew and configure NTP/chrony properly.

If instance A runs 4 seconds fast and instance B runs 3 seconds slow, two consecutive requests can produce timestamps out of order relative to actual commit order. This affects reports, audit trails, and event processing if the application assumes timestamps define strict ordering.

Even when using a database clock, synchronize the database server's clock and cluster nodes. A database clock centralizes the time source for one database, but does not guarantee accurate physical time if the database host drifts.

Timestamps should not be used as unique keys or absolute proof of commit order. If business ordering is required, use sequences, versions, event offsets, or appropriate ordering keys. `created_at` values can collide due to clock/database resolution.

## 13. Configuring auditing with a UTC application clock

A typical configuration for R2DBC:

```java
@Configuration
@EnableR2dbcAuditing(
    dateTimeProviderRef = "auditingDateTimeProvider",
    auditorAwareRef = "auditorAware"
)
public class AuditingConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditingDateTimeProvider(Clock clock) {
        return () -> Optional.of(clock.instant());
    }

    @Bean
    ReactiveAuditorAware<String> auditorAware() {
        return () -> ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName)
            .defaultIfEmpty("system");
    }
}
```

`defaultIfEmpty("system")` is an illustrative policy for requests without a logged-in user. In real applications, distinguish system jobs, anonymous requests, and user requests with appropriate identities. Do not use a single global default auditor if you need a traceable audit trail.

Corresponding schema:

```sql
CREATE TABLE article (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(300) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_modified_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by VARCHAR(150),
    last_modified_by VARCHAR(150)
);
```

In this model, application auditing owns the timestamp and auditor columns. Do not declare other defaults or triggers that overwrite them unless there is an explicit requirement.

## 14. When are `@CreatedDate` and `@LastModifiedDate` updated?

When auditing is enabled and an entity is written through Spring Data's mapping mechanism, auditing callbacks can populate properties:

- `@CreatedDate` is set when the entity is recognized as new.
- `@LastModifiedDate` is set when the entity is created or modified according to `modifyOnCreate`.
- `@CreatedBy` is obtained from `AuditorAware`/`ReactiveAuditorAware` on creation.
- `@LastModifiedBy` is updated from the current auditor on modification.

`@EnableR2dbcAuditing` includes options such as `modifyOnCreate` and `setDates`. If you want `@LastModifiedDate` populated at creation time, use the default `modifyOnCreate = true`; if you want it set only on subsequent edits, configure otherwise per your Spring Data version's API.

Auditing callbacks run inside the entity save flow, not as database triggers. Timestamps are typically determined before the write SQL executes. Thus `@CreatedDate` is not necessarily the database commit time; it is when the application generated metadata for the write operation.

## 15. Auditing callbacks do not apply to all direct SQL

When using `ReactiveCrudRepository` or `R2dbcEntityTemplate`, Spring Data mapping callbacks can apply auditing. However, when running direct SQL via `DatabaseClient`, the application controls the SQL statement and must not assume entity auditing annotations will run automatically.

Direct SQL example:

```java
public Mono<Long> insertArticle(String title, String actor, Instant now) {
    return databaseClient.sql("""
            INSERT INTO article (
                title, created_at, last_modified_at, created_by, last_modified_by
            )
            VALUES (
                :title, :createdAt, :modifiedAt, :createdBy, :modifiedBy
            )
            """)
        .bind("title", title)
        .bind("createdAt", now)
        .bind("modifiedAt", now)
        .bind("createdBy", actor)
        .bind("modifiedBy", actor)
        .fetch()
        .rowsUpdated();
}
```

Here the code must provide audit columns explicitly. You can inject `Clock` and `ReactiveAuditorAware` into custom repositories to share the same time/auditor source, but you must invoke them explicitly. If the database owns timestamps, omit those columns from the insert so defaults/triggers handle them.

Do not mix `DatabaseClient` raw SQL with the assumption that `@CreatedDate` will populate automatically. This is a frequent source of bugs when part of a repository uses entity mapping and another part uses direct SQL.

## 16. Choosing a database clock when a shared source is needed

If multiple applications or tools write to the same table and need the database as the time source, you can use a default:

```sql
CREATE TABLE audit_event (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

The application inserts without supplying `created_at`:

```sql
INSERT INTO audit_event (event_type)
VALUES (:eventType)
RETURNING id, created_at;
```

In PostgreSQL, `CURRENT_TIMESTAMP`/`now()` returns the transaction start time, not when each statement began. If you need the statement start time, PostgreSQL provides `statement_timestamp()`; if you need the wall-clock time at the moment the function is called, there is `clock_timestamp()`. These three concepts have different semantics in long-running transactions.

Triggers/defaults or insert statements must pick the right function for the requirement. If an audit timestamp should represent when the transaction started, `CURRENT_TIMESTAMP` may fit. If you need the timestamp of each statement within a long transaction, `statement_timestamp()` means something different. Do not pick `clock_timestamp()` just because its name sounds more accurate; define the business meaning first.

With SQL Server, `SYSUTCDATETIME()` or an appropriate time function can be used; MySQL has `CURRENT_TIMESTAMP`/`UTC_TIMESTAMP` functions with server/session semantics. These are database-specific examples, not portable syntax.

## 17. When should triggers be used for auditing?

Triggers can automatically set `created_at` or `last_modified_at` for every SQL statement writing to a table, including writes from other applications not using Spring Data. This is helpful when the database is the source of truth and there are multiple writers.

Advantages:

- Every writer gets the exact same rule applied.
- Applications do not have to populate timestamps in every SQL statement.
- Audit columns can be protected from applications writing arbitrary values.

Trade-offs:

- Time logic lives in the database, requiring trigger migrations and testing.
- Trigger-generated values may not automatically come back in the entity after insert/update.
- Trigger behavior differs across database engines.
- If a trigger overwrites application auditing values, be clear about which source owns the column.

If trigger-generated values are needed immediately in a response, use `RETURNING`/`OUTPUT` where supported by the database or re-read the row after writing. Mark columns read-only in mapping when the application must not write them, without mistaking that annotation for a mechanism that fetches generated values after writes.

## 18. Avoiding mixing application clock and database clock without rules

A confusing design looks like this:

- `@CreatedDate` uses `Clock.systemUTC()`.
- `created_at` has a default `CURRENT_TIMESTAMP`.
- A trigger also overwrites `created_at`.
- Some repositories use `DatabaseClient` passing `LocalDateTime.now()` manually.

Results can vary depending on the write path. Some rows are recorded using the application clock, others using the database, some timestamps lack timezones, and others carry instant semantics.

Establish a clear convention per column:

| Column | Suggested owner | Rule |
|---|---|---|
| `created_at` | Application or database, pick one | Never let two layers overwrite each other |
| `last_modified_at` | Application or database, pick one | Same rule across all update paths |
| `created_by` | Application/security context | Databases usually do not know business users |
| `last_modified_by` | Application/security context | Use consistent auditors for APIs and background jobs |
| `scheduled_local_time` | Domain/application | Store local time alongside `ZoneId` if local schedule preservation is required |

A database clock can serve as the timestamp source while the application remains the source for auditors. That is a reasonable combination if the column contract is documented clearly. Not all metadata must share one source, but each type needs one defined owner.

## 19. Testing with Clock.fixed

`Clock.fixed` returns the exact same instant on every call. It is a simple way to test time-dependent logic:

```java
@Test
void createsArticleWithExpectedTimestamp() {
    Instant fixedInstant = Instant.parse("2026-11-15T02:00:00Z");
    Clock fixedClock = Clock.fixed(fixedInstant, ZoneOffset.UTC);

    DateTimeProvider provider = () -> Optional.of(fixedClock.instant());

    assertThat(provider.getNow()).contains(fixedInstant);
}
```

This test verifies the time source, not the entire auditing callback. For integration tests, inject the fixed clock into the Spring context, save entities via the Repository, and verify `@CreatedDate`/`@LastModifiedDate` fields hold the exact expected values.

`Clock.fixed` fits tests that only need a single timestamp. If you need to verify time advancing between creation and update, use an adjustable clock.

## 20. Creating an AdjustableClock to test created/modified time

A test clock can hold an instant in an `AtomicReference` and let tests advance time:

```java
public final class AdjustableClock extends Clock {

    private final AtomicReference<Instant> current;
    private final ZoneId zone;

    public AdjustableClock(Instant initial, ZoneId zone) {
        this(new AtomicReference<>(initial), zone);
    }

    private AdjustableClock(AtomicReference<Instant> current, ZoneId zone) {
        this.current = current;
        this.zone = zone;
    }

    public void set(Instant instant) {
        current.set(instant);
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId zone) {
        return new AdjustableClock(current, zone);
    }

    @Override
    public Instant instant() {
        return current.get();
    }
}
```

Example testing auditing end-to-end with a Repository:

```java
@Test
void auditingUsesClockForCreateAndUpdate() {
    Instant created = Instant.parse("2026-11-15T02:00:00Z");
    Instant modified = Instant.parse("2026-11-15T03:00:00Z");
    AtomicReference<Long> articleId = new AtomicReference<>();
    adjustableClock.set(created);

    StepVerifier.create(articleRepository.save(new Article("First title")))
        .assertNext(saved -> {
            articleId.set(saved.getId());
            assertThat(saved.getCreatedAt()).isEqualTo(created);
            assertThat(saved.getLastModifiedAt()).isEqualTo(created);
        })
        .verifyComplete();

    adjustableClock.set(modified);

    StepVerifier.create(articleRepository.findById(articleId.get())
        .flatMap(article -> {
            article.setTitle("Updated title");
            return articleRepository.save(article);
        }))
        .assertNext(saved -> {
            assertThat(saved.getCreatedAt()).isEqualTo(created);
            assertThat(saved.getLastModifiedAt()).isEqualTo(modified);
        })
        .verifyComplete();
}
```

This is a test skeleton that needs adapting to your project's constructors, entity types, repositories, and fixtures. The test context must use the exact `AdjustableClock` bean injected into `DateTimeProvider`. The example captures the ID generated from the insert in an `AtomicReference` for the subsequent update step.

## 21. Testing the auditor with the reactive security context

If `ReactiveAuditorAware` reads the Spring Security context, tests must attach the context in the Reactor chain. Do not set only the imperative `SecurityContextHolder` expecting the reactive context to pick it up automatically.

Test skeleton example:

```java
Authentication authentication =
    new UsernamePasswordAuthenticationToken("alice", "n/a", List.of());

Mono<Article> save = articleRepository.save(new Article("Audited"))
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(authentication));

StepVerifier.create(save)
    .assertNext(saved -> assertThat(saved.getCreatedBy()).isEqualTo("alice"))
    .verifyComplete();
```

For the test to work properly, the auditor provider must use `ReactiveSecurityContextHolder` and the entity must have `@CreatedBy`. For requests without authentication, verify your fallback policy or missing-auditor behavior.

## 22. StepVerifier virtual time does not control Clock automatically

`StepVerifier.withVirtualTime(...)` and `VirtualTimeScheduler` control time for scheduler-based Reactor operators such as `delay`, `interval`, or `timeout`. They do not speed up or freeze `Clock.systemUTC()`.

Example:

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofHours(1))
    )
    .thenAwait(Duration.ofHours(1))
    .expectNext(0L)
    .verifyComplete();
```

This test advances the virtual scheduler by one hour without waiting in real time. If code inside calls `clock.instant()`, it still receives values from the clock bean. To control auditing timestamps, inject a separate `Clock.fixed` or `AdjustableClock`.

These are two distinct concepts:

- Reactor virtual time: controls when scheduler signals are emitted.
- Java Clock test double: controls date/time values read by domain/auditing code.

Never use `Thread.sleep()` to wait for time in tests. Use virtual time for Reactor operators and mock clocks for business time logic.

## 23. Testing round-trips against a real database

Unit tests with a fixed clock do not prove the database stores and returns timestamps accurately. Integration tests should verify:

- `Instant` is written into the right column type.
- Read-back values represent the same instant.
- Session timezone does not alter the point in time's meaning.
- Column precision does not fail tests due to nanosecond/microsecond differences.
- Database defaults/triggers apply when columns are omitted from inserts.
- Generated timestamps are returned via `RETURNING`/`OUTPUT` or read back properly.
- `@ReadOnlyProperty` keeps database-managed columns out of inserts/updates.
- `DatabaseClient` raw SQL does not accidentally skip required auditing.

When testing database-generated columns, you do not always have to compare against a fixed application clock instant. You can capture timestamps before/after the operation and verify the value lies within a reasonable interval, while checking defaults/triggers via direct queries. If absolute determinism is required, design test SQL or triggers with controllable inputs instead of relying on the real clock.

## 24. Testing timezones and DST

For audit timestamps, tests should confirm that the exact same instant converts accurately across timezones:

```java
Instant instant = Instant.parse("2026-11-15T02:00:00Z");

ZonedDateTime hcm = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
ZonedDateTime utc = instant.atZone(ZoneOffset.UTC);

assertThat(hcm.toInstant()).isEqualTo(instant);
assertThat(utc.toInstant()).isEqualTo(instant);
```

For local schedules, test timestamps around DST transitions in DST-observing timezones. Use `ZoneRules.getValidOffsets(localDateTime)` to check whether a local time has 0, 1, or 2 valid offsets:

```java
ZoneId zone = ZoneId.of("Europe/Paris");
LocalDateTime local = LocalDateTime.of(2026, 10, 25, 2, 30);
List<ZoneOffset> offsets = zone.getRules().getValidOffsets(local);
```

In the example, dates/times must match the timezone database of the test environment. Do not hardcode assumptions that every year or every region switches DST on the same date. Tests should treat `ZoneRules` as the source of truth.

If a local time has no valid offset, the application must have a handling policy. If there are two offsets, explicitly pick one or require unambiguous input. Past audit events should use `Instant`, never ambiguous local time.

## 25. Testing auditing when using DatabaseClient directly

Direct SQL statements do not automatically execute entity auditing callbacks. Therefore, if a custom repository writes audit columns manually, test the bound values:

```java
public Mono<Long> insertEvent(String type, String actor) {
    Instant now = clock.instant();

    return databaseClient.sql("""
            INSERT INTO audit_event(event_type, created_at, created_by)
            VALUES (:type, :createdAt, :createdBy)
            """)
        .bind("type", type)
        .bind("createdAt", now)
        .bind("createdBy", actor)
        .fetch()
        .rowsUpdated();
}
```

Tests can inject a fixed clock, invoke the method, and query `audit_event` back to verify `created_at` and `created_by`. If the SQL relies on a database default clock, tests must confirm the column is omitted from the insert and the database generates the value.

Do not test `@CreatedDate` on an entity and infer that every `DatabaseClient.sql(...)` call is audited. Each write path must be tested according to its actual mechanism.

## 26. Audit timestamps are not absolute commit order

Two transactions can be assigned timestamps nearly simultaneously, yet commit in a different order. Application clocks can drift across instances; database clocks have finite resolution; transaction-start timestamps can precede actual commit time significantly.

If you need entity change ordering, use `@Version` or an appropriate sequence/version. If you need event ordering in a distributed log, use event offsets, partition sequences, or messaging system metadata. Never use `created_at` as a concurrency control mechanism.

`@LastModifiedDate` is useful for displaying the latest update time and filtering recently changed data. It does not replace optimistic locking and does not prove one update was the latest when multiple writers compete.

## 27. Notes on auditing in batches and bulk updates

When saving individual entities via a Repository or Template, auditing callbacks can apply per entity. However, a bulk update with `DatabaseClient` such as:

```sql
UPDATE article
SET status = :status
WHERE status = :oldStatus;
```

does not automatically execute `@LastModifiedDate` callbacks per entity. If audit timestamps need updating, the SQL statement must update `last_modified_at` explicitly or a database trigger must handle it.

For large bulk updates, a database clock can be convenient so all updated rows receive a single timestamp. If using an application clock, bind the same `Instant` into the statement so every row shares the timestamp. Choose semantics based on reporting and audit requirements.

Across multiple batches, if each batch calls `clock.instant()` separately, timestamps may differ between groups. That is usually reasonable if you want to record when each batch ran. If an entire import needs one shared timestamp, capture the instant once at job start and pass it to every batch; distinguish `job_started_at` from `row_created_at`.

## 28. Common mistakes when choosing time sources

| Symptom | Possible cause | How to fix |
|---|---|---|
| Timestamps off by several hours on display | Confusing instant with local time or differing session timezones | Store instant/UTC and convert in the presentation layer |
| Flaky tests | Using the real clock and asserting exact timestamps | Inject `Clock.fixed` or `AdjustableClock` |
| `@CreatedDate` is not populated | Auditing not enabled or entity bypasses mapping callbacks | Check `@EnableR2dbcAuditing`, entity metadata, and write path |
| `DatabaseClient` insert missing audit fields | Raw SQL does not automatically run entity auditing callbacks | Bind audit values or use database defaults/triggers |
| Default column receives null | Insert statement explicitly passes null | Omit the column from insert or use dialect-appropriate `DEFAULT` |
| Generated column errors on insert | Application attempts to write to a generated column | Mark read-only and exclude the column from write statements |
| Timestamps differ across instances | Clock skew or differing timezone/default configurations | Sync NTP, use UTC, and consider a database clock |
| Timestamp comparison fails after reading back | Database reduces precision | Normalize precision in tests and schema |
| Appointments off by one hour around DST | Storing local time without preserving zone/offset | Store `ZoneId` and define a DST policy |
| `LastModifiedDate` unchanged on bulk update | Bulk SQL bypasses auditing callbacks | Update columns in SQL or use a trigger |

## 29. Workflow for designing time auditing

When implementing auditing for an R2DBC application, follow this sequence:

**Step 1 — Clarify column meaning.** Distinguish audit instants, business dates, local wall-clock times, and appointments.

**Step 2 — Choose the authoritative source.** Decide between application clock or database clock per column; never let multiple layers overwrite each other without rules.

**Step 3 — Choose Java and SQL types.** Use `Instant` for audit events; pick matching SQL timestamp types and verify driver mappings.

**Step 4 — Standardize on UTC.** Use `Clock.systemUTC()`, synchronize host/database clocks, and convert to the user's timezone on display.

**Step 5 — Enable auditing.** Configure `@EnableR2dbcAuditing`, `DateTimeProvider`, `ReactiveAuditorAware`, and annotations on entities.

**Step 6 — Identify write paths.** Repositories/Templates have auditing callbacks; raw SQL must supply audit fields manually or rely on database defaults/triggers.

**Step 7 — Test time.** Use `Clock.fixed` or a controllable clock; use virtual time separately for Reactor schedulers.

**Step 8 — Test the database.** Verify round-trips, session timezones, precision, defaults, and triggers against the real database/driver.

**Step 9 — Verify operations.** Monitor clock skew, timezone configuration, and retention/audit rules.

## 30. Conclusion

Reliable time auditing begins with clearly defining the authoritative time source and data semantics. With Spring Data R2DBC, `@EnableR2dbcAuditing`, `@CreatedDate`, `@LastModifiedDate`, and `DateTimeProvider` help applications populate timestamps from a centralized source; `ReactiveAuditorAware` provides the actor within the reactive context. Injecting `Clock` instead of calling the system clock everywhere lets tests control time cleanly.

For audit events, `Instant` and UTC conventions generally exchange better across multiple services than local date-times. Choose column types according to database semantics, understand session timezones and driver precision, and keep local schedules separate from absolute points in time. An application clock is convenient and easy to test; a database clock is helpful when a single shared source is needed across multiple writers. Choose one owner per audit column and test both Spring Data callbacks and direct SQL paths so timestamps are never missing or unexpectedly overwritten.
