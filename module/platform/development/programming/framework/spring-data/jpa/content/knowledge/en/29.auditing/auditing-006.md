# DateTimeProvider, Time Zones, and a Testable Clock

## 1. What Problem Does DateTimeProvider Solve?

Spring Data JPA Auditing automatically records Entity creation and update timestamps via annotations such as `@CreatedDate` and `@LastModifiedDate`. If auditing obtains the current time on its own, the result depends on the system clock of the running process. That makes it difficult to test exact timestamps, simulate future or past times, or ensure all components in the application use the same time source.

`DateTimeProvider` is an extension point that supplies the time value used by Spring Data Auditing. Combining it with `java.time.Clock`, an application can:

- Use a unified time source for auditing.
- Choose UTC or a deliberate business time zone.
- Use a fixed clock in unit/integration tests for deterministic results.
- Advance the clock in tests to verify timestamp updates without waiting in real time.

`Clock` supplies the current instant; `DateTimeProvider` converts that instant into a value Spring Data Auditing understands. The two APIs play related roles and do not replace each other.

## 2. Enabling JPA Auditing

First, enable auditing and register `AuditingEntityListener` on the Entity or mapped superclass:

```java
@Configuration
@EnableJpaAuditing
public class JpaAuditingConfiguration {
}
```

```java
@Entity
@EntityListeners(AuditingEntityListener.class)
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @CreatedDate
    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    @LastModifiedDate
    @Column(nullable = false)
    private Instant lastModifiedAt;
}
```

`@CreatedDate` records the creation time; `@LastModifiedDate` records the last modification time. `@EntityListeners(AuditingEntityListener.class)` connects the Entity to Spring Data's listener. If the listener is missing or `@EnableJpaAuditing` is not enabled, auditing fields may remain unpopulated.

In the example, `Instant` represents an absolute point on the timeline. `updatable = false` prevents JPA from including `createdAt` in regular UPDATE statements. When multiple Entities share audit fields, you can move the fields and listener into a `@MappedSuperclass`.

## 3. Registering Clock and DateTimeProvider

To make auditing obtain time from an application-managed `Clock`, create two beans:

```java
@Configuration
@EnableJpaAuditing(dateTimeProviderRef = "auditingDateTimeProvider")
public class JpaAuditingConfiguration {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    public DateTimeProvider auditingDateTimeProvider(Clock applicationClock) {
        return () -> Optional.of(applicationClock.instant());
    }
}
```

`DateTimeProvider#getNow()` returns `Optional<TemporalAccessor>`. `Instant` implements `TemporalAccessor`, so `applicationClock.instant()` can be returned directly. `dateTimeProviderRef` must match the bean name `auditingDateTimeProvider`.

`Clock.systemUTC()` creates a clock using the system time in the UTC zone. Calling `instant()` yields an absolute point in time; it does not depend on the server's default time zone. If the application has multiple `Clock` beans, use `@Qualifier` or `@Primary` so Spring knows which bean to inject.

Configure `@EnableJpaAuditing` only once in the application context. If auditing is already enabled elsewhere in the configuration, adding a second configuration can cause conflicts or unexpected auditing registration.

## 4. DateTimeProvider and Stored Temporal Types

`DateTimeProvider` returns a `TemporalAccessor`, while the field type on the Entity determines how time is represented and mapped to the database.

| Java Type | Meaning | When Appropriate |
| --- | --- | --- |
| `Instant` | An absolute point on the timeline | Audit timestamps, creation/update times, event times |
| `OffsetDateTime` | Date and time with a UTC offset | When you need to preserve the input's offset and the provider/database supports suitable mapping |
| `LocalDateTime` | Date and time on a local wall clock, without zone/offset | Local business hours when the zone is managed separately |
| `LocalDate` | Calendar date, without time or zone | Birthdates, calendar effective dates |
| `ZonedDateTime` | Date and time with ZoneId and time zone rules | When application logic requires the zone; verify how the provider stores/restores it |

For audit timestamps, `Instant` is usually the clearest choice because it is unambiguous when the application runs across multiple servers or time zones.

`LocalDateTime` does not indicate which time zone a value belongs to. For example, `2026-11-09T09:00` could be 09:00 in Hanoi, Tokyo, or London; converting it to an absolute instant requires knowing the accompanying `ZoneId`.

`OffsetDateTime` preserves an offset such as `+07:00`, but an offset is not equivalent to a time zone with DST rules. `ZonedDateTime` contains a ZoneId, yet not all databases/providers store and restore the full zone ID. If business logic needs to remember both the instant and the original zone, you can store `Instant` alongside a separate `ZoneId` column.

## 5. Distinguishing UTC, Offset, and Time Zone

Three concepts are often confused:

- **UTC:** the global time reference standard. `Instant` can be represented in UTC.
- **Offset:** a fixed difference from UTC at a given moment, such as `+07:00`.
- **ZoneId:** a region time zone identifier with historical and DST rules, such as `Asia/Ho_Chi_Minh` or `Europe/Paris`.

Example:

```java
Instant instant = Instant.parse("2026-11-09T02:00:00Z");
ZonedDateTime vietnamTime = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
OffsetDateTime offsetTime = instant.atOffset(ZoneOffset.ofHours(7));

System.out.println(instant);
System.out.println(vietnamTime);
System.out.println(offsetTime);
```

With Java 17+, output:

```text
2026-11-09T02:00:00Z
2026-11-09T09:00+07:00[Asia/Ho_Chi_Minh]
2026-11-09T09:00+07:00
```

All three values represent the same instant, but `ZonedDateTime` also carries the ZoneId. The `+07:00` offset by itself does not contain the full rules of `Asia/Ho_Chi_Minh`.

## 6. Do Not Rely on the Server's Default Time Zone as a Business Rule

Avoid scattering direct calls to `LocalDateTime.now()` in services, listeners, or Entities. The result depends on the JVM's default time zone and makes tests hard to control.

Do not rely on:

```java
LocalDateTime now = LocalDateTime.now();
```

Instead, inject `Clock`:

```java
public class OrderDeadlineService {
    private final Clock clock;

    public OrderDeadlineService(Clock clock) {
        this.clock = clock;
    }

    public Instant calculateDeadline(Duration duration) {
        return clock.instant().plus(duration);
    }
}
```

If local calendar time is needed, pass the zone explicitly:

```java
LocalDateTime localNow = LocalDateTime.now(clock);
ZonedDateTime businessNow = ZonedDateTime.now(
    clock.withZone(ZoneId.of("Asia/Ho_Chi_Minh"))
);
```

For audit events, store `Instant` and convert to a zone only for display. For appointments or opening hours, store the local rule together with an appropriate `ZoneId`; do not convert local wall-clock times into UTC before knowing the zone.

## 7. Daylight Saving Time (DST) and Non-Existent or Ambiguous Local Times

Some time zones observe daylight saving time. When springing forward, a range of local times may not exist; when falling back, a range of times may occur twice.

For instance, an appointment stored solely as `LocalDateTime` can become ambiguous if the zone applies DST. When scheduling in local time:

1. Store the local date and time chosen by the user.
2. Store the `ZoneId` of the location/business domain.
3. Use `ZoneRules` to detect times falling in a gap or overlap.
4. Define the business policy: reject non-existent times, adjust automatically, or ask the user to choose the offset when a time is repeated.

For events that already happened, storing `Instant` is clearest. For future events scheduled in local time, storing both the local date-time and the ZoneId may be necessary because time zone rules can change by law.

## 8. Configuring Time Zone for JDBC/Hibernate

Choosing `Instant` and `Clock.systemUTC()` is an important step, but you must understand that databases and JDBC drivers still have their own timestamp mapping rules. With Hibernate, you can configure the time zone used when binding/extracting JDBC timestamps:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          time_zone: UTC
```

This setting tells Hibernate to use UTC when interacting with JDBC timestamp APIs that accept a timezone parameter. It does not automatically turn a `TIMESTAMP WITHOUT TIME ZONE` column into a timezone-aware type, nor does it guarantee the database preserves the original ZoneId.

Column types and semantics vary across databases. For example, some databases have timestamp with time zone columns that store a normalized instant without keeping the original zone ID; timestamp without timezone types typically store date/time fields without carrying zone information. Check your dialect, schema migrations, JDBC driver, and how values are read back.

If the schema is managed with Flyway/Liquibase, column type changes must go through proper migrations. `@Column` or Java types alone do not guarantee production schemas are converted safely.

## 9. Controlling Timestamp Precision

Java `Instant` has nanosecond precision, whereas a database column may only store microseconds or milliseconds. After persisting and reloading, values can be truncated or rounded to the database's precision.

Therefore, when writing tests:

- Do not assume every database preserves nanoseconds.
- Use a column precision appropriate for the application.
- Compare timestamps after normalizing to the actual precision, or pick test values with compatible precision.
- Check both time zone and precision when migrating databases.

Do not arbitrarily add or subtract milliseconds just to make tests pass; identify the exact precision used by your schema/provider.

## 10. Using Clock.fixed to Test DateTimeProvider

`Clock.fixed(...)` always returns the same instant, keeping tests independent of the wall clock:

```java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-01-15T08:30:00Z"),
    ZoneOffset.UTC
);

DateTimeProvider provider = () -> Optional.of(fixedClock.instant());

Instant supplied = (Instant) provider.getNow().orElseThrow();
System.out.println(supplied);
```

Java 17+ stdout:

```text
2026-01-15T08:30:00Z
```

This is a unit test for the `Clock`-to-`DateTimeProvider` adapter. To verify actual auditing, wire the test clock into a Spring context with `@EnableJpaAuditing` enabled and persist Entities via a repository.

## 11. Injecting a Fixed Clock in Integration Tests

You can provide a test `Clock` annotated with `@Primary` so `DateTimeProvider` automatically uses it:

```java
@TestConfiguration
public class FixedClockTestConfiguration {
    @Bean
    @Primary
    public Clock testClock() {
        return Clock.fixed(
            Instant.parse("2026-01-15T08:30:00Z"),
            ZoneOffset.UTC
        );
    }
}
```

Integration test:

```java
@SpringBootTest
@Import(FixedClockTestConfiguration.class)
class PurchaseOrderAuditingTest {

    @Autowired
    private PurchaseOrderRepository repository;

    @Test
    void populatesAuditDatesFromInjectedClock() {
        PurchaseOrder order = repository.saveAndFlush(new PurchaseOrder());

        Instant expected = Instant.parse("2026-01-15T08:30:00Z");
        assertEquals(expected, order.getCreatedAt());
        assertEquals(expected, order.getLastModifiedAt());
    }
}
```

This example assumes auditing is enabled, the Entity has the listener, getters exist, and `modifyOnCreate` keeps its default value `true`. In that case, `@LastModifiedDate` is also populated on creation. If the application configures `modifyOnCreate = false`, do not expect the modified field to be set on insert.

## 12. Testing Updates Using MutableClock

`Clock.fixed` works well for testing inserts, but cannot advance time. To test that `@LastModifiedDate` changes when an Entity is updated, you can use an adjustable test Clock:

```java
public final class MutableClock extends Clock {
    private final AtomicReference<Instant> current;
    private final ZoneId zone;

    public MutableClock(Instant initial, ZoneId zone) {
        this(new AtomicReference<>(initial), zone);
    }

    private MutableClock(AtomicReference<Instant> current, ZoneId zone) {
        this.current = current;
        this.zone = zone;
    }

    public void setInstant(Instant instant) {
        current.set(instant);
    }

    @Override
    public Instant instant() {
        return current.get();
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId zone) {
        return new MutableClock(current, zone);
    }
}
```

Register `MutableClock` as a `@Primary` bean in tests, then verify insert and update:

```java
@Test
void createdDateStaysFixedAndModifiedDateAdvances() {
    Instant first = Instant.parse("2026-01-15T08:30:00Z");
    testClock.setInstant(first);

    PurchaseOrder order = repository.saveAndFlush(new PurchaseOrder());
    assertEquals(first, order.getCreatedAt());
    assertEquals(first, order.getLastModifiedAt());

    Instant later = first.plusSeconds(90);
    testClock.setInstant(later);
    order.setStatus(OrderStatus.PAID);
    repository.saveAndFlush(order);

    assertEquals(first, order.getCreatedAt());
    assertEquals(later, order.getLastModifiedAt());
}
```

This test snippet assumes the Entity has `setStatus`, audit field getters, a repository, and `MutableClock` injected. `saveAndFlush` forces JPA to flush so lifecycle auditing executes before assertions. If the Entity is not dirty or does not trigger an UPDATE, `@PreUpdate`/auditing updates may not execute.

## 13. @CreatedBy and @LastModifiedBy

Auditing can record both the creator and the modifier. This mechanism uses `AuditorAware<T>`, independent of `DateTimeProvider`:

```java
@Configuration
@EnableJpaAuditing(
    auditorAwareRef = "auditorProvider",
    dateTimeProviderRef = "auditingDateTimeProvider"
)
public class JpaAuditingConfiguration {
    // Clock and DateTimeProvider beans are declared here.

    @Bean
    public AuditorAware<String> auditorProvider() {
        return () -> Optional.of("system");
    }
}
```

The snippet above only illustrates a fixed auditor. In a Spring Security application, `AuditorAware` typically retrieves the authenticated principal from SecurityContext. For background or batch tasks, define a clear system auditor; do not assume an HTTP user is always present.

The Entity can declare:

```java
@CreatedBy
private String createdBy;

@LastModifiedBy
private String lastModifiedBy;
```

`DateTimeProvider` answers "what time is it now?"; `AuditorAware` answers "who is making the change?". These two sources should be tested independently and can be used together in a single auditing configuration.

## 14. modifyOnCreate and When Audit Values Are Updated

`@EnableJpaAuditing` has a `modifyOnCreate` option. The default is `true`, so `@LastModifiedDate` and `@LastModifiedBy` can be set even when an Entity is first created. If `modifyOnCreate = false`, modified fields are only updated when the Entity changes after creation.

Audit timestamps are assigned during the persist/update lifecycle in which the auditing listener participates. They are not a guarantee of the exact transaction commit time. A transaction may commit later, roll back, or flush multiple times. If business logic requires recording the exact commit timestamp or publishing post-commit events, use an appropriate transaction/event mechanism instead of interpreting `@LastModifiedDate` as a commit timestamp.

For an update, `@LastModifiedDate` is only meaningful when JPA actually detects changes and performs an update. Calling a setter with the same value may not mark the Entity dirty depending on dirty-checking and mappings.

## 15. Application Clock vs. Database Time

A system may have two sources of time:

- The application's Clock used by `DateTimeProvider`.
- The database's clock used by `CURRENT_TIMESTAMP`, column defaults, or triggers.

Do not mix the two sources without an explicit policy. If `createdAt` is written by the application while `updatedAt` is written by a database trigger, clock skew between application nodes and the database can produce unexpected timestamp ordering.

Choose one authoritative source for each group of timestamps. If auditing is managed by Spring Data, use an injected Clock and synchronize nodes via NTP. If the database is the authoritative source, let the database generate timestamps and do not simultaneously overwrite the same field with application auditing.

`Clock` controls time within the process, but cannot fix an inaccurate system clock. Production still requires server clock synchronization and clock drift monitoring.

## 16. Common Pitfalls and Troubleshooting

**`@CreatedDate` or `@LastModifiedDate` remains null.** Check `@EnableJpaAuditing`, `AuditingEntityListener`, the Spring Data JPA dependency, and Entity field access/mapping.

**DateTimeProvider is not used.** Verify that `dateTimeProviderRef` matches the bean name and the bean returns a non-empty `Optional<TemporalAccessor>`.

**Application reports missing or multiple Clock beans.** Mark one bean `@Primary` or use `@Qualifier` in DateTimeProvider.

**Timestamp tests pass intermittently.** Do not call `Instant.now()` or `LocalDateTime.now()` directly in assertions. Inject `Clock.fixed` or a controllable Clock.

**`@LastModifiedDate` does not change.** Check whether the Entity is dirty and issues an UPDATE on flush; calling `save` with the same values does not guarantee an update.

**Timestamps differ by hours across environments.** Check Java types, JVM time zone, JDBC driver, Hibernate's `hibernate.jdbc.time_zone`, session time zone, and database column types.

**Reloaded timestamps differ at nanosecond precision.** The database may store lower precision than Java Instant. Compare at schema precision and check migrations.

**LocalDateTime is ambiguous during DST.** Store ZoneId alongside local time or use Instant for past events; define a gap/overlap policy.

**Audit timestamps are overwritten by both the application and triggers.** Choose one authoritative source per field and avoid two writers overwriting each other.

## 17. Implementation Checklist

- Enable `@EnableJpaAuditing` and register `AuditingEntityListener` on the Entity/mapped superclass.
- Create a `Clock` bean and custom `DateTimeProvider`; point `dateTimeProviderRef` to the exact bean name.
- Prefer `Instant` for audit event timestamps and use UTC as the convention.
- Only use `LocalDateTime` when business semantics are genuinely local time and the zone is managed separately.
- Distinguish UTC offsets from ZoneId; do not assume the database stores zone IDs.
- Check Hibernate/JDBC time zone settings and column types via migrations.
- Determine the database's timestamp precision.
- Use `Clock.fixed` for insert tests; use MutableClock or a controllable clock for update tests.
- Verify `modifyOnCreate` and `@LastModifiedDate` semantics.
- If using `@CreatedBy`/`@LastModifiedBy`, configure and test `AuditorAware` separately.
- Do not mix application and database clocks for the same audit field.

`DateTimeProvider` lets Spring Data Auditing obtain time from a controllable source. Combined with `Clock`, choosing `Instant`/UTC for audit timestamps and managing ZoneId explicitly for business local times enables an application to record consistent times and test inserts/updates deterministically.