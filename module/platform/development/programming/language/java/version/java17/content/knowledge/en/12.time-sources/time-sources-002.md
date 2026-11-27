# Relationship Between `InstantSource`, `Clock`, and Time Zones in Java 17

Java 17 added the `java.time.InstantSource` interface to separate **obtaining a point on the timeline** from **interpreting that point in a time zone**. The `java.time.Clock` class implements `InstantSource` and adds time-zone information. These two APIs are closely related but have distinct responsibilities.

You can remember it in three points:

- **`Instant`** represents an absolute point on the timeline, independent of time zones.
- **`InstantSource`** provides the current `Instant` from a replaceable or controllable source, which is very useful for testing.
- **`Clock`** is an `InstantSource` with an added `ZoneId` so date-time APIs can produce results in the chosen time zone.

A time zone does not change an `Instant`. It only determines the local date and time corresponding to that point in time. Understanding this relationship helps avoid bugs when running applications on servers in different time zones, write stable time-based tests, and handle dates and times with daylight saving time (DST).

> **Version:** `InstantSource` was added in Java 17. The examples below use standard Java 17 APIs and require no preview features.

## 1. Starting from Three Distinct Time Concepts

Before comparing the two APIs, it is necessary to distinguish an absolute point in time, a local date-time, and a time zone.

### 1.1. `Instant` — A Point on the Timeline

`Instant` represents a point on the timeline, measured relative to the epoch `1970-01-01T00:00:00Z`. The `Z` suffix means UTC.

```java
import java.time.Instant;

Instant moment = Instant.parse("2025-03-08T10:15:30Z");

System.out.println(moment);
```

Output:

```text
2025-03-08T10:15:30Z
```

`Instant` does not contain a time zone such as `Asia/Ho_Chi_Minh` or `Europe/Paris`. Nor is it "the computer's local time." It is a definite point in time that can be represented in many different time zones.

### 1.2. `LocalDateTime` — Date and Time on a Local Clock

`LocalDateTime` holds a date and time like `2025-03-08T17:15:30`, but **contains no time zone and does not identify a unique Instant**.

```java
import java.time.LocalDateTime;

LocalDateTime local = LocalDateTime.of(2025, 3, 8, 17, 15, 30);

System.out.println(local);
```

Output:

```text
2025-03-08T17:15:30
```

Without knowing the location/time zone, we cannot conclude which UTC instant this local time corresponds to. In places with DST, a local time may even occur twice or not exist at all on a transition day.

### 1.3. `ZoneId` — Time-Zone Rules Used for Conversion

`ZoneId` defines the conversion rules between an `Instant` and a local date-time. For example:

```java
import java.time.ZoneId;
import java.time.ZoneOffset;

ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
ZoneId paris = ZoneId.of("Europe/Paris");
ZoneId utc = ZoneOffset.UTC;
```

Two common groups of zones:

| Group | Examples | Characteristics |
|---|---|---|
| Geographical region time zones | `Asia/Ho_Chi_Minh`, `Europe/Paris`, `America/New_York` | Have historical rules and offset-change rules over time; may apply DST |
| Fixed offsets | `UTC`, `+07:00`, `-05:00` | Fixed offset from UTC, does not change seasonally |

Region-based `ZoneId` values rely on the platform's time-zone data (IANA Time Zone Database/TZDB). Rules may be updated when governments change legal time.

`ZoneOffset` is a form of `ZoneId` describing a fixed offset from UTC. For example, `ZoneOffset.of("+07:00")` always has offset `+07:00`; it does not represent the full historical or DST rules of a geographical region.

## 2. What Is `InstantSource`?

`InstantSource` is an interface in `java.time`, introduced in **Java 17**. It provides one core method:

```java
Instant instant();
```

This method returns the instant as defined by the source. The interface also has default methods `millis()` and `withZone(ZoneId)`, along with factory methods for creating time sources.

An important goal of `InstantSource` is to **decouple dependencies on the system clock**. Instead of calling `Instant.now()` or `System.currentTimeMillis()` directly everywhere, the application receives a time source via a constructor or parameter. During testing, we can replace the system source with a fixed source.

Example:

```java
import java.time.Instant;
import java.time.InstantSource;

InstantSource source = InstantSource.system();
Instant now = source.instant();

System.out.println(now);
```

`InstantSource.system()` returns a source based on the best available system clock. This source is not tied to a specific time zone.

### 2.1. `InstantSource` Only Cares About the Instant

The interface has no `getZone()` method. This is intentional: obtaining an `Instant` does not require knowing where the user is located.

```java
InstantSource source = InstantSource.system();

Instant current = source.instant();
long epochMillis = source.millis();
```

`millis()` returns milliseconds since the UTC epoch. However, the API recommends that most applications use `Instant` rather than raw millisecond values unless there is a specific performance reason.

An `InstantSource` also does not guarantee that its result is always the exact real time from a physical clock. It lets the application supply a **controlled view of time**, such as a fixed point in time in tests or a time source from an external system.

### 2.2. `InstantSource` Is a Functional Interface

`InstantSource` has only one abstract method, `instant()`, so a lambda can be used:

```java
import java.time.Instant;
import java.time.InstantSource;

InstantSource source =
        () -> Instant.parse("2025-01-01T00:00:00Z");

System.out.println(source.instant());
```

In real applications, `InstantSource.fixed(...)` usually expresses intent more clearly than a lambda:

```java
InstantSource source =
        InstantSource.fixed(Instant.parse("2025-01-01T00:00:00Z"));
```

Lambdas are useful for understanding the functional interface aspect or mocking a custom source; factory methods are the readable choice for common cases.

## 3. What Is `Clock` and How Does It Relate to `InstantSource`?

`Clock` is an **abstract class** in `java.time` that implements the `InstantSource` interface. In addition to providing `instant()`, `Clock` also has a `ZoneId`:

```java
public abstract class Clock implements InstantSource {
    public abstract ZoneId getZone();
    public abstract Clock withZone(ZoneId zone);
    public abstract Instant instant();
}
```

The snippet above only illustrates the core methods relevant to this lesson, not the full API declaration.

You can visualize the relationship as:

```text
           InstantSource
           (interface)
                ^
                |
           implements
                |
              Clock
          (abstract class)
           /          \
       instant()     getZone()
          |             |
       instant       time zone
```

Because `Clock` is an `InstantSource`, anywhere an `InstantSource` is accepted can also accept a `Clock`:

```java
InstantSource source = Clock.systemUTC();
Instant now = source.instant();
```

However, the reverse is not automatically true: an arbitrary `InstantSource` might not have a time zone and is not a `Clock`. When you need a `Clock` from that source, use `withZone(ZoneId)`.

### 3.1. Comparison Table

| Feature | `InstantSource` | `Clock` |
|---|---|---|
| What kind of type is it? | Interface | Abstract class |
| Available since | Java 17 | Java 8 |
| Provides `instant()` | Yes | Yes, implements `InstantSource` |
| Has `millis()` | Yes, default method | Yes, inherited/overridden |
| Has time zone `getZone()` | No | Yes |
| Has `withZone(ZoneId)` | Yes, returns `Clock` | Yes, returns `Clock` |
| Fixed source | `InstantSource.fixed(instant)` | `Clock.fixed(instant, zone)` |
| Best used when | Only the instant is needed | Both the instant and time-zone context are needed |

**How to choose:** if logic only needs to know "has the deadline passed?" or "did the event happen before a certain instant?", `InstantSource` is usually sufficient. If logic needs "what date is it today at the branch?", `Clock` is more appropriate because it has a zone to interpret the instant.

## 4. Creating `InstantSource` and `Clock` from the System

### 4.1. Unzoned Time Source

```java
InstantSource source = InstantSource.system();

Instant now = source.instant();
System.out.println(now);
```

This source returns the current `Instant` using the best available system clock. It does not choose a time zone to convert into a local date or time.

### 4.2. Clock in UTC

```java
Clock utcClock = Clock.systemUTC();

Instant instant = utcClock.instant();
ZoneId zone = utcClock.getZone();

System.out.println(instant);
System.out.println(zone); // Z
```

Use UTC when you need an explicit clock independent of the machine's default time zone. The returned `Instant` is still a point on the timeline; the clock's zone will be used by APIs like `LocalDate.now(clock)` when producing a local date.

### 4.3. Clock with an Explicit Zone

```java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
Clock businessClock = Clock.system(businessZone);

Instant now = businessClock.instant();
LocalDate today = LocalDate.now(businessClock);
LocalTime time = LocalTime.now(businessClock);

System.out.println(now);
System.out.println(today);
System.out.println(time);
```

`Clock.system(zone)` uses the system time source and the specified zone. The same instant can produce different local dates/times when used with two clocks that have different zones.

### 4.4. Clock with the Machine's Default Zone

```java
Clock defaultClock = Clock.systemDefaultZone();

System.out.println(defaultClock.getZone());
```

This API uses the default time zone of the JVM/machine. It is convenient for small programs or tools that depend on machine configuration, but it can cause application behavior to change when moving servers, containers, or when the system time-zone configuration changes.

The Java 17 Javadoc recommends avoiding this default when a specific zone can be chosen. For business logic, choose a zone from business or user configuration rather than implicitly picking up the server's zone.

## 5. How Does `InstantSource.withZone` Create a `Clock`?

This is the direct bridge between the two APIs.

`InstantSource` has a default method:

```java
Clock withZone(ZoneId zone);
```

It creates a `Clock` combining the existing instant source with the specified zone.

Example:

```java
InstantSource source = InstantSource.system();

Clock hcmClock = source.withZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);

Clock utcClock = source.withZone(ZoneOffset.UTC);

System.out.println(hcmClock.getZone());
System.out.println(utcClock.getZone());
```

Two clocks are created from the same instant source, but use two different zones.

- `hcmClock.instant()` and `utcClock.instant()` obtain the instant from the underlying source.
- `LocalDate.now(hcmClock)` interprets the instant in `Asia/Ho_Chi_Minh`.
- `LocalDate.now(utcClock)` interprets it in UTC.
- Choosing a zone does not shift the point on the timeline; it only changes how it is converted into a local date/time.

With a fixed source, this difference is easier to observe:

```java
Instant fixedInstant = Instant.parse("2025-01-01T00:30:00Z");
InstantSource fixedSource = InstantSource.fixed(fixedInstant);

Clock hcm = fixedSource.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
Clock utc = fixedSource.withZone(ZoneOffset.UTC);

System.out.println(hcm.instant());
System.out.println(utc.instant());

System.out.println(LocalDate.now(hcm));
System.out.println(LocalDate.now(utc));
```

Output:

```text
2025-01-01T00:30:00Z
2025-01-01T00:30:00Z
2025-01-01
2025-01-01
```

In this example, both dates are still Jan 1 because the chosen instant does not cross a date boundary between the two zones. To see a date difference, change the instant to `2024-12-31T20:00:00Z`: in UTC it is still 2024-12-31, while in Vietnam it is already 2025-01-01.

`InstantSource.withZone` is very useful when a library or service only requires a simple abstraction to obtain instants, while another layer needs to create a zoned `Clock`.

## 6. `Clock.withZone` Changes the Zone, Not the Instant

`Clock` also has `withZone(ZoneId)`. This method returns a clock based on the current clock but using the new zone:

```java
Clock original = Clock.fixed(
        Instant.parse("2025-01-01T00:00:00Z"),
        ZoneOffset.UTC
);

Clock vietnam = original.withZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);

System.out.println(original.instant());
System.out.println(vietnam.instant());

System.out.println(original.getZone());
System.out.println(vietnam.getZone());
```

Output:

```text
2025-01-01T00:00:00Z
2025-01-01T00:00:00Z
Z
Asia/Ho_Chi_Minh
```

Both clocks have the same instant due to the fixed source, but different zones. Do not confuse `withZone` with adding seven hours to an `Instant`.

### 6.1. `withZone` Differs from `Instant.atZone`

These two operations often appear near each other, yet return two different types of objects:

```java
Clock clock = Clock.systemUTC();

Clock localClock = clock.withZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);

Instant instant = clock.instant();
ZonedDateTime localDateTime = instant.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);
```

- `clock.withZone(zone)` creates a **new Clock** with the new zone.
- `instant.atZone(zone)` converts a **specific Instant** into a `ZonedDateTime` in that zone.

If you already have a known instant and want to display it in a time zone, `Instant.atZone` is the direct operation. If you want a time source so multiple `now(clock)` calls share a zone, choose `Clock.withZone` or `Clock.system(zone)`.

## 7. Region-Based ZoneId vs. Fixed ZoneOffset

`ZoneId` can represent either a geographical region or a fixed offset. These two are not equivalent in terms of time rules.

### 7.1. Region-Based Zones

```java
ZoneId newYork = ZoneId.of("America/New_York");
ZoneId paris = ZoneId.of("Europe/Paris");
ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
```

Geographical regions use date-dependent rules. For example, Paris can be UTC+01:00 in winter and UTC+02:00 in summer. New York has its own rules, and you should not infer its offset from Paris's offset.

When handling work schedules, appointments, or location-based events, store a meaningful zone ID such as `Europe/Paris` instead of storing only the current offset.

### 7.2. Fixed Offsets

```java
ZoneOffset utc = ZoneOffset.UTC;
ZoneOffset vietnamOffset = ZoneOffset.of("+07:00");
ZoneOffset minusFive = ZoneOffset.of("-05:00");
```

A fixed offset is appropriate when a protocol or data format mandates a specific offset. It knows nothing about the DST rules of a city or region.

For example, `-05:00` may be the offset of certain places at one time of year, but cannot fully represent `America/New_York` all year round.

### 7.3. Which Zone Type Should You Choose?

| Requirement | Recommended type |
|---|---|
| Absolute point in time for storage/logging/inter-system transfer | `Instant`, typically recorded in UTC |
| Business date of an office in Paris | `ZoneId.of("Europe/Paris")` |
| User schedule in Vietnam | `ZoneId.of("Asia/Ho_Chi_Minh")` |
| Protocol specifies exact `+07:00` offset | `ZoneOffset.of("+07:00")` |
| Only need UTC calculations | `ZoneOffset.UTC` |
| Intentionally using the server's configured zone | `ZoneId.systemDefault()` |

**Do not use a current offset in place of a region-based zone** if business logic requires historical or seasonal rule changes.

## 8. Converting Between Instant and Local Time

### 8.1. From Instant to ZonedDateTime

```java
Instant instant = Instant.parse("2025-03-08T10:00:00Z");

ZonedDateTime hcmTime = instant.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);

ZonedDateTime parisTime = instant.atZone(
        ZoneId.of("Europe/Paris")
);

System.out.println(hcmTime);
System.out.println(parisTime);
```

The same `Instant` is displayed in two different zones. The absolute point in time remains unchanged.

### 8.2. From LocalDateTime to Instant

To convert in the reverse direction, you must supply a zone:

```java
LocalDateTime local = LocalDateTime.of(2025, 3, 8, 17, 0);

Instant instant = local
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toInstant();

System.out.println(instant);
```

If you use `ZoneOffset.of("+07:00")` instead of `Asia/Ho_Chi_Minh`, the conversion still produces an instant for that local time, but based solely on the fixed offset.

### 8.3. From Clock to Local Date and Time

The `now(Clock)` factory methods on date-time classes accept a `Clock`:

```java
Clock clock = Clock.system(
        ZoneId.of("Asia/Ho_Chi_Minh")
);

Instant instant = Instant.now(clock);
LocalDate date = LocalDate.now(clock);
LocalTime time = LocalTime.now(clock);
LocalDateTime dateTime = LocalDateTime.now(clock);
ZonedDateTime zoned = ZonedDateTime.now(clock);
```

`Instant.now(clock)` retrieves the instant; `LocalDate.now(clock)`, `LocalTime.now(clock)`, and similar APIs use the clock's zone to produce local values.

If you only have an `InstantSource`, you can get the instant directly with `source.instant()`. When you need `LocalDate.now(clock)`, convert the source into a clock with `source.withZone(zone)`.

## 9. DST: Why a Region Zone Is More Than Just an Offset

Some regions change their offset seasonally (daylight saving time). This creates two special cases for `LocalDateTime`:

- **Gap:** the clock jumps forward; certain local times do not exist.
- **Overlap:** the clock falls back; certain local times occur twice.

### 9.1. Gap — Local Time Does Not Exist

For example, in Paris on the transition to summer time, the clock jumps from 02:00 to 03:00. `02:30` on that day does not exist under the zone's rules.

```java
ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime localGap = LocalDateTime.of(2025, 3, 30, 2, 30);

ZonedDateTime resolved = localGap.atZone(paris);

System.out.println(resolved);
```

`LocalDateTime.atZone` adjusts a local time falling in a gap forward by the length of the gap. In this example, the result is adjusted to around `03:30+02:00[Europe/Paris]`.

This is automatic behavior of the API; if business rules require rejecting a non-existent time, check the zone rules and validate the input instead of accepting the adjustment by default.

### 9.2. Overlap — Local Time Occurs Twice

When the clock falls back, the same local time can correspond to two different offsets:

```java
ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime localOverlap =
        LocalDateTime.of(2025, 10, 26, 2, 30);

ZonedDateTime first = localOverlap.atZone(paris);
ZonedDateTime later = first.withLaterOffsetAtOverlap();

System.out.println(first);
System.out.println(later);
System.out.println(first.toInstant());
System.out.println(later.toInstant());
```

Both `ZonedDateTime` instances have the same local date and time `02:30` but different offsets, so they represent **two different Instants**. By default `atZone` chooses the earlier offset during an overlap; you can use `withLaterOffsetAtOverlap()` to choose the later occurrence.

### 9.3. When Strict Validation Is Needed

If an application receives a local date-time, zone, and offset together from an external source, you can use `ZonedDateTime.ofStrict` to require that the offset is valid for the zone at that time:

```java
ZonedDateTime validated = ZonedDateTime.ofStrict(
        localDateTime,
        suppliedOffset,
        zone
);
```

If the local time falls in a gap or the offset is invalid during an overlap, the API rejects it with an exception rather than adjusting it automatically. This is the right choice when appointment data must be validated strictly.

## 10. Using InstantSource to Decouple Time Dependencies in Applications

A major benefit of `InstantSource` is that it does not force services to read the system clock directly.

Example of an expiration-checking service:

```java
import java.time.Instant;
import java.time.InstantSource;
import java.util.Objects;

public class ExpirationService {
    private final InstantSource timeSource;

    public ExpirationService(InstantSource timeSource) {
        this.timeSource = Objects.requireNonNull(timeSource);
    }

    public boolean isExpired(Instant expiresAt) {
        return !timeSource.instant().isBefore(expiresAt);
    }
}
```

The production application can pass:

```java
ExpirationService service =
        new ExpirationService(InstantSource.system());
```

Tests can pass a fixed instant:

```java
Instant fixedNow = Instant.parse("2025-01-01T10:00:00Z");

ExpirationService service = new ExpirationService(
        InstantSource.fixed(fixedNow)
);

boolean expired = service.isExpired(
        Instant.parse("2025-01-01T09:59:59Z")
);

System.out.println(expired); // true
```

No need to wait for real time or mock static methods. Every call to `timeSource.instant()` in the test returns the exact chosen instant.

### 10.1. When Only InstantSource Is Needed

The following logic typically only needs `InstantSource`:

- Checking whether a token or session has expired.
- Recording a record's creation timestamp.
- Comparing whether an event occurred before/after a deadline expressed as an `Instant`.
- Capturing the processing time of an operation with an absolute timestamp.
- Attaching timestamps to audit events.

Example:

```java
Instant createdAt = timeSource.instant();
```

No zone is needed just to record an absolute point in time.

### 10.2. When Clock Is Needed

If the logic depends on local date or time, accept a `Clock`:

```java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

public class BillingService {
    private final Clock clock;

    public BillingService(Clock clock) {
        this.clock = clock;
    }

    public LocalDate billingDate() {
        return LocalDate.now(clock);
    }
}
```

When creating the service, configure the business zone:

```java
Clock billingClock = Clock.system(
        ZoneId.of("Asia/Ho_Chi_Minh")
);

BillingService service = new BillingService(billingClock);
```

Tests use a fixed clock:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2025-01-01T16:30:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh")
);

BillingService service = new BillingService(fixedClock);
System.out.println(service.billingDate()); // 2025-01-01
```

If you change the zone to UTC, that same instant might belong to a different local date. That is precisely why the zone must be part of the design when business logic depends on a calendar.

## 11. Fixed, Offset, and Tick Time Sources

Both `InstantSource` and `Clock` have useful factory methods for testing and applications.

### 11.1. `fixed` — Always Fixed Time

`InstantSource`:

```java
InstantSource fixedSource = InstantSource.fixed(
        Instant.parse("2025-01-01T00:00:00Z")
);
```

`Clock`:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2025-01-01T00:00:00Z"),
        ZoneOffset.UTC
);
```

Every call returns the same instant. This is a good choice for testing deadlines, invoice dates, expiration dates, or boundary rules.

### 11.2. `offset` — Shifting a Time Source by a Duration

You can create a source that returns instants shifted relative to a base source:

```java
InstantSource source = InstantSource.system();

InstantSource twoHoursLater = InstantSource.offset(
        source,
        Duration.ofHours(2)
);

System.out.println(twoHoursLater.instant());
```

With `Clock`:

```java
Clock clock = Clock.systemUTC();

Clock simulated = Clock.offset(
        clock,
        Duration.ofDays(1)
);
```

This is a simulated time shift, useful for tests or certain special scenarios. Do not use `offset` to fix a time zone; to change the zone, use `withZone`.

### 11.3. `tick` — Truncating Instants to Ticks

`tick` creates a source that only changes at timestamps truncated to a duration:

```java
InstantSource source = InstantSource.tick(
        InstantSource.system(),
        Duration.ofSeconds(1)
);

System.out.println(source.instant());
```

`Clock` also has a corresponding factory method:

```java
Clock secondClock = Clock.tick(
        Clock.systemUTC(),
        Duration.ofSeconds(1)
);
```

A tick clock is useful when the application does not need resolution finer than a specific tick. Do not assume every call will observe the exact instant a tick transitions; implementations may use caching strategies.

`tickDuration` must be positive. For durations smaller than one millisecond, the API rules require it to divide evenly into one second. Consult the Java 17 Javadoc if choosing a special resolution.

### 11.4. Comparing Factory Methods

| Goal | InstantSource | Clock |
|---|---|---|
| Get system time | `InstantSource.system()` | `Clock.system(zone)` / `Clock.systemUTC()` |
| Fix time | `InstantSource.fixed(instant)` | `Clock.fixed(instant, zone)` |
| Shift time | `InstantSource.offset(source, duration)` | `Clock.offset(clock, duration)` |
| Truncate to ticks | `InstantSource.tick(source, duration)` | `Clock.tick(clock, duration)` |
| Attach a zone | `source.withZone(zone)` returns `Clock` | `clock.withZone(zone)` |

## 12. Clock Is Not a Monotonic Duration Timer

`InstantSource` and `Clock` are used to obtain **wall-clock time** (calendar clock time). The system clock can be adjusted by time synchronization, administrators, or virtualization environments. Therefore, observed instants can jump forward or backward.

If you need to measure **elapsed time** or accurate timeouts within the same process, typically use `System.nanoTime()`:

```java
long start = System.nanoTime();

// Perform the work to be measured.
doWork();

long elapsedNanos = System.nanoTime() - start;
Duration elapsed = Duration.ofNanos(elapsedNanos);

System.out.println(elapsed);
```

Do not subtract two `Instant` values from the system clock as a substitute for a monotonic timer for timeouts. `InstantSource` lets you swap time sources in tests, but does not promise a monotonic clock.

Distinguish between:

- **Actual calendar point in time:** `Instant`, `InstantSource`, `Clock`.
- **Interval between two operations:** `Duration` and a monotonic clock like `System.nanoTime()`.

## 13. Storing and Transmitting Time Data Across Systems

A common design is to store events as `Instant`, while the zone is used when displaying or calculating business dates.

Example:

```java
Instant createdAt = Instant.now(Clock.systemUTC());

// Store createdAt as a UTC timestamp or ISO-8601 string with Z.
String serialized = createdAt.toString();

// When displaying to the user:
ZonedDateTime displayTime = createdAt.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);
```

Benefits:

- Event data preserves a consistent absolute point in time.
- Each client can display according to the user's zone.
- The server does not have to assume the OS time zone.
- Comparing and sorting events is straightforward with Instant.

### 13.1. When Business Logic Needs to Preserve a Scheduled Local Time

An appointment for "09:00 Paris time on April 1" has a different meaning from an event that occurred at a specific Instant.

If a user schedules an appointment in local time and the schedule must follow future DST changes, the data typically needs to store:

- The `LocalDateTime` the user selected.
- The `ZoneId` of the location (e.g., `Europe/Paris`).
- The gap/overlap handling rule if business logic requires an explicit decision.

The application then determines the corresponding `Instant` according to the zone rules at the time of calculation. Storing only the current offset can lose the calendar intent when DST rules change.

If an appointment has already been confirmed as an absolute instant, storing that `Instant` as well is useful to keep the locked-in time. Whether to store both local time and zone depends on the business contract.

## 14. Common Mistakes and How to Handle Them

| Symptom | Cause | Resolution |
|---|---|---|
| Same code produces different dates on servers | Using the machine's default zone | Pass a `Clock` with an explicit business zone |
| Thinking `InstantSource` has a time zone | Confusing source with Clock | `InstantSource` only provides instants; use `withZone` to create a Clock |
| Thinking `withZone` adds hours to an instant | Confusing zone change with time shift | Compare `instant()` before/after; zone only affects interpretation |
| Using `+07:00` instead of a city zone | Fixed offset lacks region/DST rules | Use a geographical `ZoneId` when business logic depends on location |
| Tests depend on real time | Calling `Instant.now()` or `LocalDate.now()` directly in logic | Inject `InstantSource` or `Clock` and use `fixed` in tests |
| Local time does not exist or repeats | DST gap/overlap | Validate using zone rules or use `ofStrict` when needed |
| Measuring timeouts using two Instants | Wall-clock can be adjusted | Use `System.nanoTime()` to measure elapsed time |
| Application time zone changes after deployment | Relying on system default | Put the business zone in configuration and pass it explicitly |

### 14.1. Do Not Use Ambiguous Zone Abbreviations

Strings like `PST`, `CST`, or `IST` can refer to different regions depending on context. Prefer explicit region IDs in `Area/Location` format such as `America/Los_Angeles` or `Asia/Ho_Chi_Minh`.

### 14.2. Do Not Manually Add an Offset to Convert Time

Avoid:

```java
// Do not manually add 7 hours to "convert to Vietnam time."
Instant vietnamTime = Instant.now().plus(Duration.ofHours(7));
```

This creates a **new Instant 7 hours in the future**, rather than converting the display to the Vietnam time zone. Better:

```java
ZonedDateTime vietnamTime = Instant.now()
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
```

The result is the same point in time presented in the Vietnam zone.

## 15. Complete Example: Service Accepting InstantSource and Clock

The following example demonstrates two needs in one application: checking a deadline with an instant and getting an invoice date in the business zone.

```java
import java.time.Clock;
import java.time.Instant;
import java.time.InstantSource;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Objects;

public class TimeService {
    private final InstantSource instantSource;
    private final Clock businessClock;

    public TimeService(InstantSource instantSource, Clock businessClock) {
        this.instantSource = Objects.requireNonNull(instantSource);
        this.businessClock = Objects.requireNonNull(businessClock);
    }

    public boolean isPastDeadline(Instant deadline) {
        return !instantSource.instant().isBefore(deadline);
    }

    public LocalDate businessDate() {
        return LocalDate.now(businessClock);
    }

    public static void main(String[] args) {
        ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

        // Production: same system source, zoned for business logic.
        InstantSource source = InstantSource.system();
        Clock clock = source.withZone(businessZone);

        TimeService service = new TimeService(source, clock);

        System.out.println("Business date: " + service.businessDate());
        System.out.println(
                "Deadline passed: "
                        + service.isPastDeadline(
                                Instant.parse("2025-01-01T00:00:00Z")
                        )
        );
    }
}
```

In tests, replace both dependencies with fixed sources so results are repeatable:

```java
Instant fixedInstant = Instant.parse("2025-01-01T00:30:00Z");
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

InstantSource fixedSource = InstantSource.fixed(fixedInstant);
Clock fixedClock = fixedSource.withZone(businessZone);

TimeService service = new TimeService(fixedSource, fixedClock);

System.out.println(service.businessDate()); // 2025-01-01
System.out.println(
        service.isPastDeadline(
                Instant.parse("2025-01-01T00:00:00Z")
        )
); // true
```

This example can be simplified by injecting only `Clock` if all logic needs both an instant and a zone, because `Clock` is also an `InstantSource`. Separating into two dependencies only makes sense when two parts of the application have different needs or you want to express the contract explicitly.

## 16. Practice Exercises

### Exercise 1 — InstantSource or Clock?

A service only checks whether the current point in time has passed `expiresAt`. It does not need to know any time zone.

**Answer:** Inject `InstantSource`. Compare `source.instant()` with `expiresAt`. When testing, use `InstantSource.fixed(...)`.

### Exercise 2 — Why Can Two Dates Differ?

```java
Instant instant = Instant.parse("2024-12-31T20:00:00Z");

LocalDate utcDate = instant.atZone(ZoneOffset.UTC).toLocalDate();
LocalDate hcmDate = instant.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
).toLocalDate();
```

**Answer:** UTC is `2024-12-31`, while Vietnam is `2025-01-01`. This is the same instant interpreted in two different zones.

### Exercise 3 — Does withZone Change the Instant?

```java
Clock fixed = Clock.fixed(
        Instant.parse("2025-01-01T00:00:00Z"),
        ZoneOffset.UTC
);

Clock hcm = fixed.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
```

**Answer:** No. Both clocks return the same fixed `Instant`. `getZone()` differs, so conversions to local date/time may differ.

### Exercise 4 — Choosing a Zone for a Paris Appointment

A user schedules an appointment for `09:00` in Paris on a future date. Why could storing only `+01:00` be wrong?

**Answer:** Paris may apply a different offset depending on DST rules and the specific date. Storing `ZoneId.of("Europe/Paris")` preserves the region rules; a fixed offset is not enough to interpret every date.

### Exercise 5 — Measuring Execution Time

A piece of code needs to measure execution duration for recording metrics. Should you use `Clock` or `System.nanoTime()`?

**Answer:** Use `System.nanoTime()` to measure a monotonic duration within the process. `Clock`/`InstantSource` are for calendar points in time and are not guaranteed to be monotonic.

## 17. Key Takeaways

- `Instant` is an absolute point in time; by itself it has no time zone.
- `InstantSource` (Java 17) is an abstraction providing `Instant`, making it easy to swap time sources in tests.
- `Clock` implements `InstantSource` and adds a `ZoneId`.
- `InstantSource.withZone(zone)` creates a `Clock`; `Clock.withZone(zone)` creates a clock with another zone based on the same time source.
- `Clock.system(zone)` is appropriate when you need system time with an explicit business zone.
- `Clock.fixed` and `InstantSource.fixed` enable deterministic time testing.
- Region-based `ZoneId` values carry historical/DST rules; `ZoneOffset` is a fixed offset.
- `Instant.atZone(zone)` changes how the instant is represented, not the Instant itself.
- Use `System.nanoTime()` to measure duration; use `InstantSource`/`Clock` for calendar points in time.
- Do not rely on the machine's default time zone for business logic requiring consistent results across environments.

## Official Java 17 References

- [Java SE 17 API — `java.time.InstantSource`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/InstantSource.html).
- [Java SE 17 API — `java.time.Clock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html).
- [Java SE 17 API — `java.time.Instant`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html).
- [Java SE 17 API — `java.time.ZoneId`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html).
- [Java SE 17 API — `java.time.ZoneOffset`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneOffset.html).
- [Java SE 17 API — `java.time.ZonedDateTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html).
- [Java SE 17 API — `java.time.LocalDate`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html).
