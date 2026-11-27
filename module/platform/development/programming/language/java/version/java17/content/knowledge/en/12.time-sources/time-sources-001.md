# InstantSource and the System Clock Dependency Problem in Java 17

Many programs need to know the current point in time: recording order creation timestamps, checking token expiration, determining business dates, or measuring processing duration. Calling `Instant.now()` or `System.currentTimeMillis()` directly may seem simple, but it couples business logic to the machine's real clock.

During testing, it is hard to reproduce an exact point in time; when a system runs across multiple time zones, the same instant can correspond to different local dates; when measuring elapsed time, the system clock can be adjusted. Java 17 provides `InstantSource` to decouple the **source of the current instant** from the logic that uses time.

The main idea is: instead of letting business classes read the system clock themselves, pass a time source into them. In production, the source can be the system clock; in tests, the source can be fixed at a known instant.

## 1. The Problem with Depending Directly on the System Clock

Suppose a service checks whether an order has expired:

```java
import java.time.Instant;

public class OrderExpiryService {
    public boolean isExpired(Instant expiresAt) {
        return Instant.now().isAfter(expiresAt);
    }
}
```

This method reads the real time every time it runs. That causes several difficulties:

- **Non-deterministic testing:** results depend on when the test executes. A test might pass today but fail when run on another day.
- **Hard to reproduce bugs:** if a bug occurs right at a date boundary or at the exact moment a token expires, it is not easy to recreate the conditions.
- **Environment dependency:** the host machine might have a misconfigured clock, delayed NTP synchronization, or run in a different time zone.
- **Hard to simulate boundary conditions:** it is not easy to test the exact moment before expiration, at expiration, and after expiration.

One way to improve this is to pass an abstraction representing the time source. In Java 17, the lightweight abstraction for obtaining instants is `InstantSource`.

## 2. What Is InstantSource?

`java.time.InstantSource` is an interface representing a **source of the current instant**. It was added in Java 17. An instant is a point on the global timeline, represented by `java.time.Instant`, independent of time zones.

Key members:

| API | Role |
| --- | --- |
| `InstantSource.system()` | Creates a source based on the system clock. |
| `InstantSource.fixed(Instant)` | Creates a source that always returns a fixed instant. |
| `InstantSource.offset(InstantSource, Duration)` | Creates a source returning instants offset by a duration relative to another source. |
| `InstantSource.tick(InstantSource, Duration)` | Creates a source that truncates instants to the specified time tick. |
| `instant()` | Gets the current instant from the source. |
| `millis()` | Gets the number of milliseconds since the epoch from the source. |
| `withZone(ZoneId)` | Creates a `Clock` using that source with the specified time zone. |

A simple example:

```java
import java.time.Instant;
import java.time.InstantSource;

public class InstantSourceDemo {
    public static void main(String[] args) {
        InstantSource source = InstantSource.system();
        Instant now = source.instant();

        System.out.println(now);
    }
}
```

`InstantSource` focuses solely on providing instants. It does not carry a default time zone like `Clock`. When you need to convert an instant to a local date or time, specify a `ZoneId` separately.

## 3. Distinguishing InstantSource, Clock, Instant, and System.currentTimeMillis

These APIs are all related to time, but they represent different concepts:

| API | Nature | When to use |
| --- | --- | --- |
| `Instant` | A specific point on the timeline | Storing creation/update times, expiration times, event timestamps. |
| `InstantSource` | A source of instants | Decoupling current-time reads from business logic; easy to swap sources in tests. |
| `Clock` | A time source with both an instant and a time zone | Providing time to APIs such as `LocalDate.now(clock)` or `ZonedDateTime.now(clock)`. |
| `System.currentTimeMillis()` | Milliseconds from the epoch according to the system clock | Interacting with APIs that require epoch milliseconds or legacy systems. |
| `System.nanoTime()` | Monotonic time counter for measuring duration | Measuring elapsed time, timeouts, and relative benchmarks. |

`Clock` is an abstract class that implements `InstantSource`. Therefore, a `Clock` can be used anywhere an `InstantSource` is expected; conversely, an `InstantSource` does not necessarily carry time-zone information until `withZone` is called.

### 3.1. Instant Is Not Local Time

`Instant` represents a global point in time, for example:

```java
Instant eventTime = Instant.parse("2026-11-15T10:00:00Z");
```

The `Z` suffix indicates UTC. To display it to a user in a time zone, convert it to `ZonedDateTime`:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant instant = Instant.parse("2026-11-15T10:00:00Z");
ZonedDateTime local = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(local);
```

A time zone is a set of rules for converting between an instant and local calendar time. It can contain daylight saving time (*daylight saving time*) rules, historical offset changes, and adjustments enacted by governing authorities.

Do not store local time without a time zone if the data needs to identify a global point in time. For events that have already occurred, `Instant` is usually the right choice; for appointments in local time, you need to store the `ZoneId` or a zoned time representation depending on business requirements.

### 3.2. InstantSource Is Not a Monotonic Clock

`InstantSource.system()` retrieves the instant from the system clock. This clock can be adjusted by the operating system, NTP, or administrative configuration. A subsequent read may jump forward or backward relative to an earlier read.

Therefore, `InstantSource` is suitable for knowing "what point in time is it now" on the calendar clock, but it is not the right tool for accurately measuring "how much time has elapsed."

To measure duration, use `System.nanoTime()`:

```java
long start = System.nanoTime();

performWork();

long elapsedNanos = System.nanoTime() - start;
System.out.println("Elapsed ns: " + elapsedNanos);
```

`nanoTime` only has relative meaning between reads within the same JVM; do not use it as a timestamp to store in a database or send to other systems. To check a calendar expiration time, use an instant; to measure timeouts or execution duration, use a monotonic source such as `nanoTime`.

## 4. Decoupling System Clock Dependencies with Dependency Injection

Instead of calling `Instant.now()` directly inside business logic, accept an `InstantSource` via the constructor:

```java
import java.time.Instant;
import java.time.InstantSource;
import java.util.Objects;

public class OrderExpiryService {
    private final InstantSource timeSource;

    public OrderExpiryService(InstantSource timeSource) {
        this.timeSource = Objects.requireNonNull(timeSource, "timeSource");
    }

    public boolean isExpired(Instant expiresAt) {
        Instant now = timeSource.instant();
        return !now.isBefore(expiresAt);
    }
}
```

The class does not need to know whether the source is the system clock or a simulated clock. It simply asks for an instant.

In production:

```java
OrderExpiryService service =
        new OrderExpiryService(InstantSource.system());
```

In tests:

```java
Instant fixedNow = Instant.parse("2026-11-15T10:00:00Z");
OrderExpiryService service =
        new OrderExpiryService(InstantSource.fixed(fixedNow));
```

Both environments use the same logic with different time sources. This is simple dependency injection without needing a DI framework.

### 4.1. Why Constructor Injection Is Useful

- The time dependency is explicitly visible in the constructor.
- Tests can control the point in time without changing the machine's clock.
- Business classes do not need to call system APIs in multiple places.
- The source can be swapped in simulation, demo, or integration testing environments.
- Code is easier to read because maintainers clearly see that the logic requires a time source.

Avoid creating a new `InstantSource.system()` inside every business method. Create the source at the composition root or configuration layer and pass it down to the components that need it.

## 5. InstantSource.fixed: Testing at a Specific Point in Time

`InstantSource.fixed(instant)` creates a source that always returns the same instant. It is especially useful when testing conditions before, at, and after a deadline.

Example of an expiration-checking service:

```java
import java.time.Instant;
import java.time.InstantSource;

public class ExpiryTestExample {
    public static void main(String[] args) {
        Instant expiry = Instant.parse("2026-11-15T12:00:00Z");

        OrderExpiryService before = new OrderExpiryService(
                InstantSource.fixed(
                        Instant.parse("2026-11-15T11:59:59Z")));

        OrderExpiryService exactly = new OrderExpiryService(
                InstantSource.fixed(expiry));

        OrderExpiryService after = new OrderExpiryService(
                InstantSource.fixed(
                        Instant.parse("2026-11-15T12:00:01Z")));

        System.out.println(before.isExpired(expiry));   // false
        System.out.println(exactly.isExpired(expiry));  // true
        System.out.println(after.isExpired(expiry));    // true
    }
}
```

In this example, the business rule is defined as **expired at or after the expiration instant**. The expression `!now.isBefore(expiresAt)` expresses that exact boundary.

If the business rule specifies that expiration occurs only when the current time is strictly greater than the expiration time, use `now.isAfter(expiresAt)` and write a separate test for the equality case. What matters is defining the boundary before writing the condition.

### 5.1. Testing Time Boundaries

For a deadline `T`, clearly describe the expected outcome at:

| Point in time | Condition | Example under "expired at or after T" rule |
| --- | --- | --- |
| Before T | `now < T` | Not expired |
| Exactly T | `now = T` | Expired |
| After T | `now > T` | Expired |

Tests using a fixed source do not depend on machine speed, test execution schedule, or real time.

## 6. InstantSource.offset: Simulating Shifted Time

`InstantSource.offset(base, duration)` creates a source that returns instants shifted by a duration relative to the base source. It is useful when you want to simulate a system running ahead or behind by a specific amount.

Example:

```java
import java.time.Duration;
import java.time.InstantSource;

InstantSource system = InstantSource.system();
InstantSource oneDayAhead =
        InstantSource.offset(system, Duration.ofDays(1));

System.out.println("System: " + system.instant());
System.out.println("Ahead:  " + oneDayAhead.instant());
```

The `oneDayAhead` source returns instants equal to the base source plus one day. This is a simulated source for testing date-dependent logic; it does not alter the machine's real clock.

You can create a source shifted into the past using a negative duration:

```java
InstantSource yesterday =
        InstantSource.offset(
                InstantSource.system(),
                Duration.ofDays(-1));
```

`offset` is not a way to modify the system clock. It simply provides a different time view for the component receiving that source.

## 7. InstantSource.tick: Truncating to Time Ticks

`InstantSource.tick(base, duration)` creates a source whose instants are rounded down to the specified tick unit. This is useful when sub-interval resolution is not needed, or when you want to simulate a time source that updates in ticks.

Example:

```java
import java.time.Duration;
import java.time.InstantSource;

InstantSource minuteClock =
        InstantSource.tick(
                InstantSource.system(),
                Duration.ofMinutes(1));

System.out.println(minuteClock.instant());
```

The returned instant is truncated down to the corresponding minute boundary. For example, an instant between `10:42:00` and just before `10:43:00` yields the `10:42:00` minute mark.

Notes:

- Tick does not make time run faster or slower; it changes the resolution of observed instants.
- Two consecutive reads close together may return the same instant.
- The tick duration must be valid and positive according to the API rules.
- Do not use tick to measure elapsed time or accurate timeouts.

If you only need normal system time, there is no need to wrap it in tick. Use it when the logic genuinely accepts resolution at the chosen interval.

## 8. When You Need a Time Zone: Converting InstantSource to Clock

`InstantSource` only provides instants. Many `java.time` APIs accept a `Clock` to obtain both the current instant and a time zone.

The `withZone(ZoneId)` method creates a `Clock` from the source:

```java
import java.time.Clock;
import java.time.InstantSource;
import java.time.LocalDate;
import java.time.ZoneId;

InstantSource source = InstantSource.system();
Clock vietnamClock =
        source.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

LocalDate businessDate = LocalDate.now(vietnamClock);
System.out.println(businessDate);
```

Here:

- `source.instant()` is the global instant.
- `vietnamClock` associates the instant with the `Asia/Ho_Chi_Minh` time zone.
- `LocalDate.now(vietnamClock)` computes the calendar date in that time zone.

If business logic follows the time zone of a branch, user, or market, specify the `ZoneId` explicitly. Avoid relying on `ZoneId.systemDefault()` if results need to be consistent across machines.

### 8.1. Using Clock Directly When Both Instant and Zone Are Needed

If many APIs in the application need a time zone, you can inject `Clock`:

```java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

public class BusinessDateService {
    private final Clock clock;

    public BusinessDateService(Clock clock) {
        this.clock = clock;
    }

    public LocalDate today() {
        return LocalDate.now(clock);
    }
}
```

Production:

```java
Clock productionClock =
        Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
BusinessDateService service = new BusinessDateService(productionClock);
```

Test:

```java
Clock testClock = Clock.fixed(
        Instant.parse("2026-11-15T17:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));
```

`Clock` already has corresponding factories such as `system`, `fixed`, `offset`, and `tick`. Choose `InstantSource` when logic only needs instants; choose `Clock` when logic also needs a zone or the APIs being used require a Clock.

## 9. Deciding Between InstantSource and Clock

| Question | Appropriate choice |
| --- | --- |
| Only need the current instant to compare against a deadline? | `InstantSource` |
| Need to inject a minimal time source without carrying a time zone? | `InstantSource` |
| Need to use `LocalDate.now(clock)` or `ZonedDateTime.now(clock)`? | `Clock` |
| Multiple components need the same time-zone rules? | `Clock` |
| Using legacy APIs that already accept `Clock`? | Keep passing `Clock`; it is also an `InstantSource`. |
| Want to test a fixed local date? | `Clock.fixed(instant, zone)` |
| Want to test a fixed instant without caring about zone? | `InstantSource.fixed(instant)` |

Do not convert everything to `InstantSource` just because it is a newer API. Choose the smallest abstraction that satisfies the class's contract.

## 10. System Clock Dependency Issues in Testing

### 10.1. Avoid Scattered Calls to now()

A class might call `Instant.now()` in multiple places:

```java
if (Instant.now().isAfter(start)) {
    // ...
}

auditRepository.save(new AuditEvent(Instant.now()));
```

The two calls can receive different instants, even if only slightly apart. Sometimes that is desired, but if a single business operation needs a consistent reference point, read it once:

```java
Instant now = timeSource.instant();

if (now.isAfter(start)) {
    // ...
}

auditRepository.save(new AuditEvent(now));
```

Reading once ensures all decisions within the operation use the same reference point. If you want distinct timestamps for individual events, read intentionally at each event boundary.

### 10.2. Testing Expiration Logic Without Waiting for Real Time

Example of checking access permissions:

```java
import java.time.Instant;
import java.time.InstantSource;

public class AccessTokenPolicy {
    private final InstantSource timeSource;

    public AccessTokenPolicy(InstantSource timeSource) {
        this.timeSource = timeSource;
    }

    public boolean isValidUntil(Instant expiresAt) {
        return timeSource.instant().isBefore(expiresAt);
    }
}
```

Tests can create fixed sources before, at, and after the deadline without sleeping:

```java
Instant expiry = Instant.parse("2026-11-15T12:00:00Z");

AccessTokenPolicy before = new AccessTokenPolicy(
        InstantSource.fixed(expiry.minusSeconds(1)));
AccessTokenPolicy at = new AccessTokenPolicy(
        InstantSource.fixed(expiry));
AccessTokenPolicy after = new AccessTokenPolicy(
        InstantSource.fixed(expiry.plusSeconds(1)));

assert before.isValidUntil(expiry);
assert !at.isValidUntil(expiry);
assert !after.isValidUntil(expiry);
```

This example defines a token as valid when `now < expiresAt`. If the contract differs, update the condition and corresponding assertions.

### 10.3. Testing Elapsed Time: A Fixed Source Is Not Enough

`InstantSource.fixed` always returns the same instant. It works well for testing point-in-time rules, but cannot by itself simulate advancing time.

If logic needs to observe time changing across calls, you can write a small test implementation:

```java
import java.time.Instant;
import java.time.InstantSource;
import java.util.Iterator;
import java.util.List;

final class SequenceInstantSource implements InstantSource {
    private final Iterator<Instant> instants;

    SequenceInstantSource(List<Instant> instants) {
        this.instants = instants.iterator();
    }

    @Override
    public Instant instant() {
        if (!instants.hasNext()) {
            throw new IllegalStateException("No test instant remaining");
        }
        return instants.next();
    }
}
```

The test can supply a predefined sequence of instants. This is useful for logic that reads time multiple times; make sure the call order in the test matches the expected contract.

If you want to simulate a clock that can explicitly step forward or backward, build a stateful test clock or use an application time abstraction. Never change the operating system clock in tests.

## 11. Limitations of System Time and Time Zones

Decoupling the time source helps control dependencies, but does not automatically solve all time-related issues.

### 11.1. The Machine Clock Can Be Wrong or Adjusted

The system clock can:

- Run fast or slow relative to standard time.
- Be resynchronized via NTP.
- Be adjusted by an administrator.
- Be affected by VM/container configuration or cloud environments.

`InstantSource.system()` reflects the system clock visible to the JVM. It does not guarantee absolute time accuracy. If the business requires high time reliability, consider clock synchronization, infrastructure time sources, drift monitoring, and discrepancy handling procedures.

### 11.2. The Default Time Zone Is Not a Business Rule

`ZoneId.systemDefault()` returns the default time zone of the JVM/environment. It can differ across developer machines, CI, containers, and production.

If calculating the settlement date in Vietnam, use `ZoneId.of("Asia/Ho_Chi_Minh")` rather than relying on the default zone. If each account has its own time zone, store and use the account's `ZoneId` according to the data contract.

### 11.3. DST and Non-Existent or Repeated Local Times

In regions with daylight saving time, during clock transitions:

- There can be a range of local times that do not exist when the clock jumps forward.
- There can be a range of local times that occur twice when the clock falls back.

A `LocalDateTime` contains no zone, so by itself it does not uniquely identify an instant in these situations. For appointments, you need a `ZoneId` and rules for handling gaps/overlaps; for events that have already occurred, storing an `Instant` is usually clearer.

### 11.4. InstantSource Does Not Replace System.nanoTime

Do not use:

```java
Instant start = source.instant();
performWork();
Duration elapsed = Duration.between(start, source.instant());
```

to measure timeouts that need stability against clock changes. The right approach for measuring duration within the same JVM:

```java
long start = System.nanoTime();
performWork();
long elapsed = System.nanoTime() - start;
```

Use `InstantSource` for calendar points in time; use `System.nanoTime` for elapsed time.

## 12. Designing Business Classes with a Time Source

A useful convention is to pass the time source in the constructor of components that need to know "now." For example:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.InstantSource;
import java.util.Objects;

public class SessionService {
    private final InstantSource timeSource;
    private final Duration sessionLifetime;

    public SessionService(
            InstantSource timeSource,
            Duration sessionLifetime) {
        this.timeSource = Objects.requireNonNull(timeSource);
        this.sessionLifetime = Objects.requireNonNull(sessionLifetime);

        if (sessionLifetime.isNegative() || sessionLifetime.isZero()) {
            throw new IllegalArgumentException(
                    "sessionLifetime must be positive");
        }
    }

    public Instant calculateExpiry() {
        return timeSource.instant().plus(sessionLifetime);
    }

    public boolean isExpired(Instant expiresAt) {
        return !timeSource.instant().isBefore(expiresAt);
    }
}
```

At the composition root:

```java
SessionService sessionService =
        new SessionService(
                InstantSource.system(),
                Duration.ofMinutes(30));
```

In tests:

```java
InstantSource fixed =
        InstantSource.fixed(Instant.parse("2026-11-15T10:00:00Z"));

SessionService sessionService =
        new SessionService(fixed, Duration.ofMinutes(30));

System.out.println(sessionService.calculateExpiry());
```

If the same operation calls `calculateExpiry()` multiple times with a system source, each call gets a new timestamp. If a single consistent reference time is needed for an entire transaction, capture `Instant now` once at the use-case boundary and pass it down to calculations.

## 13. Common Design Mistakes

**Calling `Instant.now()` directly in every business class.**  
Makes logic hard to test and dependent on the real clock. Pass `InstantSource` or `Clock` into classes that need time.

**Using `InstantSource` as a zoned clock.**  
`InstantSource` only provides instants. Use `withZone` to obtain a `Clock`, or inject `Clock` from the start if a zone is needed.

**Using `LocalDateTime.now()` to store global event timestamps.**  
`LocalDateTime` has no zone or offset, so it does not uniquely identify an instant. Use `Instant`, or `OffsetDateTime`/`ZonedDateTime` as required.

**Using `InstantSource.system()` to measure elapsed time.**  
The system clock can be adjusted. Use `System.nanoTime()` to measure durations.

**Relying on `ZoneId.systemDefault()` for business dates.**  
Results can vary across environments. Specify the zone according to business rules.

**Using a fixed source and expecting time to advance automatically.**  
`InstantSource.fixed` always returns the same instant. Use offset/tick or a stateful test implementation if you need to simulate advancing time.

**Reading time multiple times within a single business decision.**  
Successive reads can differ. If the same reference point is needed, read the instant once and pass it to the calculations.

**Assuming InstantSource guarantees an absolutely accurate clock.**  
It only abstracts the time source; clock quality still depends on the system environment.

## 14. Self-Check Questions

**1. What is `InstantSource` used for?**  
It represents a source of the current instant, decoupling time retrieval from business logic.

**2. Which Java version added `InstantSource`?**  
Java 17.

**3. What is the main difference between `InstantSource` and `Clock`?**  
`InstantSource` provides instants; `Clock` is also an instant source but includes a time zone and directly supports calendar APIs that take a Clock.

**4. Why does injecting `InstantSource` make testing easier?**  
Tests can use `InstantSource.fixed` to control the point in time without depending on the real clock.

**5. What is `InstantSource.offset` used for?**  
It creates a time source shifted by a duration relative to a base source, useful for simulating time.

**6. Does `InstantSource.tick` make time run faster?**  
No. It truncates returned instants to the chosen tick interval.

**7. When should you use `Clock` instead of `InstantSource`?**  
When you need a time zone or use APIs like `LocalDate.now(clock)`.

**8. Should you use `InstantSource.system()` to measure the duration of a task?**  
No. Use `System.nanoTime()` to measure elapsed time.

**9. Does `InstantSource.fixed` advance automatically over time?**  
No. It always returns the same instant.

**10. How do you compute business dates consistently across machines?**  
Use `Clock` with a `ZoneId` specified by business rules rather than relying on the machine's default time zone.

## Official References

- [Java SE 17 API — `java.time.InstantSource`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/InstantSource.html): instant sources, `system`, `fixed`, `offset`, `tick` factories, and `withZone`.
- [Java SE 17 API — `java.time.Clock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): zoned clocks and corresponding factories.
- [Java SE 17 API — `java.time.Instant`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): representing instants on the timeline.
- [Java SE 17 API — `java.time.ZoneId`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html): time-zone identifiers and rules.
- [Java SE 17 API — `System.nanoTime()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): measuring relative elapsed time.
