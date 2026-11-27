# Passing a Time Source into Objects Instead of Calling Time Directly in Java 17

## 1. The Problem When an Object Reads the System Clock Directly

A business class often needs to know the current point in time to determine an invoice date, check whether an order has expired, verify a trial period, or record an update timestamp. A common direct approach looks like this:

~~~java
import java.time.Instant;

public final class TrialService {
    public boolean isExpired(Instant expiresAt) {
        return Instant.now().isAfter(expiresAt);
    }
}
~~~

The code is short and works, but it depends on the real clock of the machine running it. During testing, you cannot actively set the current time to a fixed date. Results can change depending on the day the test runs, the machine's time zone, system clock adjustments, or execution latency.

A test such as:

~~~java
assertTrue(service.isExpired(Instant.now().minusSeconds(1)));
~~~

uses the real clock both when preparing test data and during execution. If the system clock is adjusted between the two calls or the test runs near a time boundary, reproducing failures becomes harder. For business logic with multiple branches by date or hour, tests that depend on real time also struggle to verify past and future scenarios.

The right solution in Java 17 is to **pass a time source into the object**. The `java.time.Clock` API is designed for this purpose: business code accepts a `Clock` and reads time through it. In production, pass a system clock; in tests, pass a fixed clock or a clock with a deterministic offset.

> Instead of letting an object decide "what time is it now" on its own, let the caller creating the object supply that answer.

## 2. `Clock` in the Java Time API

`Clock` is an abstract class in the `java.time` package. It provides a source of the current time along with an associated time zone. Commonly used methods:

| Method | Purpose |
|---|---|
| `Clock.systemUTC()` | Creates a clock using system time in the UTC time zone. |
| `Clock.system(ZoneId)` | Creates a clock using system time in the specified time zone. |
| `Clock.systemDefaultZone()` | Creates a clock using the system's default time zone. |
| `Clock.fixed(Instant, ZoneId)` | Creates a clock that always returns the same instant. |
| `Clock.offset(Clock, Duration)` | Creates a clock whose instant equals the base clock plus an offset. |
| `Clock.tick(Clock, Duration)` | Creates a clock that only updates at the specified tick intervals. |
| `Clock.instant()` | Gets the current instant from the clock as an `Instant`. |
| `Clock.millis()` | Gets the number of milliseconds since the epoch. |
| `Clock.getZone()` | Gets the clock's time zone. |
| `Clock.withZone(ZoneId)` | Returns a clock with the same time source but a different time zone. |

For most business logic, the direct usage is:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;

Clock clock = Clock.systemUTC();

Instant now = Instant.now(clock);
LocalDate todayUtc = LocalDate.now(clock);
~~~

Static factory methods on time types such as `Instant.now(Clock)`, `LocalDate.now(Clock)`, and `ZonedDateTime.now(Clock)` accept a time source as a parameter. This is the connection point between `Clock` and the other date-time types in the Java Time API.

### 2.1. Why Use `Clock` Instead of Defining Your Own Interface?

You could define your own interface such as `TimeProvider` with a `now()` method, but Java already provides `Clock` along with the implementations you need:

- Works directly with `Instant`, `LocalDate`, `LocalDateTime`, and `ZonedDateTime`.
- Built-in support for system clocks, fixed clocks, offset clocks, and tick clocks.
- No need to write custom time-mocking mechanisms in simple tests.
- Integrates seamlessly with the rest of the `java.time` package.

If an application has special requirements such as reading a clock from an external service or needing an abstraction with multiple domain operations, a custom interface may make sense. For most Java 17 applications, however, `Clock` is the standard and simplest choice.

## 3. Constructor Injection: Passing Clock into an Object

An object that depends on time should accept `Clock` via its constructor. Example:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class TrialService {
    private final Clock clock;

    public TrialService(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public boolean isExpired(Instant expiresAt) {
        Objects.requireNonNull(expiresAt, "expiresAt");
        Instant now = Instant.now(clock);
        return !now.isBefore(expiresAt);
    }
}
~~~

Here:

1. `clock` is passed in when the object is created.
2. The `private final` field keeps the time source fixed throughout the service's lifetime.
3. `Objects.requireNonNull` validates the required dependency so configuration errors surface immediately upon object creation.
4. On each check, the service obtains the current instant via `Instant.now(clock)`.
5. The expiration rule is clearly defined: if the current time is **at or after** `expiresAt`, it has expired.

Storing `Clock` rather than storing an `Instant now` in the constructor is crucial. `Clock` represents **a source that can be read repeatedly**; `Instant` is just a single point in time. If you store `Instant.now(clock)` when constructing the service, the object will always use its initialization time and never advance with time.

### 3.1. Where to Create the Production Clock

At the composition root (where application objects are wired together), create the real clock:

~~~java
import java.time.Clock;

public final class Application {
    public static void main(String[] args) {
        Clock clock = Clock.systemUTC();
        TrialService trialService = new TrialService(clock);

        // Wire and run other application components.
    }
}
~~~

In larger applications, you can create a shared bean or dependency and pass it into services via constructor injection. Each service does not need to call `Clock.systemUTC()` to create its own time source; passing it from the initialization layer makes configuration and testing easy to control across the entire application.

### 3.2. Avoid Setters to Swap the Clock After the Object Is Running

A less clear approach is:

~~~java
// Not recommended for required dependencies.
public final class SomeService {
    private Clock clock;

    public void setClock(Clock clock) {
        this.clock = clock;
    }
}
~~~

If the service is called before the setter is invoked, the clock field may not be initialized yet. Swapping the clock mid-lifecycle can also cause inconsistent behavior. For a required time source, constructor injection and a `final` field make the object's contract much clearer.

## 4. Using a Fixed Clock for Deterministic Testing

`Clock.fixed` returns a clock that always supplies the same `Instant`. It is ideal when testing date or point-in-time conditions:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-15T10:00:00Z"),
        ZoneOffset.UTC);

TrialService service = new TrialService(fixedClock);
~~~

Every call to `Instant.now(fixedClock)` returns `2026-11-15T10:00:00Z`. The test does not depend on real time and can run today, tomorrow, or on a CI machine with the exact same result.

### 4.1. Writing Tests with JUnit Jupiter

Example test for expiration rules:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class TrialServiceTest {

    private static final Instant NOW =
            Instant.parse("2026-11-15T10:00:00Z");

    private final Clock fixedClock =
            Clock.fixed(NOW, ZoneOffset.UTC);

    private final TrialService service =
            new TrialService(fixedClock);

    @Test
    void isNotExpiredWhenExpiryIsInFuture() {
        Instant expiresAt = NOW.plusSeconds(60);

        assertFalse(service.isExpired(expiresAt));
    }

    @Test
    void isExpiredWhenExpiryIsInPast() {
        Instant expiresAt = NOW.minusSeconds(60);

        assertTrue(service.isExpired(expiresAt));
    }

    @Test
    void isExpiredAtTheExactExpiryInstant() {
        assertTrue(service.isExpired(NOW));
    }
}
~~~

The three tests cover the three key cases: expiry in the future, expiry in the past, and current time equal to the expiry instant. The third test clarifies the boundary comparison rule. If business rules specify expiring only strictly **after** the deadline, change the comparison and the corresponding test; what matters is making the policy explicit.

### 4.2. Comparing Tests Dependent on the Real Clock vs. Tests Using Clock

| Testing approach | Characteristics |
|---|---|
| Calling `Instant.now()` directly in the service | Results vary with run time; hard to deterministically set past/future times. |
| Passing `Clock.systemUTC()` | Appropriate for production; tests still depend on real time if using this clock. |
| Passing `Clock.fixed(...)` | Every read yields the same instant; ideal for deterministic tests. |
| Passing `Clock.offset(...)` | Simulates a time source shifted from a base clock by a fixed offset. |

The goal is not to make every test use fake time. The goal is to make business logic **time-controllable** when testing requires it.

## 5. Using Offset Clocks to Simulate Future or Past Time

`Clock.offset` creates a clock whose instant equals the base clock plus a `Duration`. Example:

~~~java
Clock base = Clock.fixed(
        Instant.parse("2026-11-15T10:00:00Z"),
        ZoneOffset.UTC);

Clock oneDayLater = Clock.offset(base, Duration.ofDays(1));
Clock oneHourEarlier = Clock.offset(base, Duration.ofHours(-1));

System.out.println(Instant.now(oneDayLater));
System.out.println(Instant.now(oneHourEarlier));
~~~

The outputs are respectively:

~~~text
2026-11-16T10:00:00Z
2026-11-15T09:00:00Z
~~~

Because the base clock is fixed, these offset clocks also return fixed instants. This is a clean way to check behavior at another date or hour without modifying the OS clock.

### 5.1. Testing Date-Based Trial Rules

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

public final class TrialPolicy {
    private final Clock clock;

    public TrialPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean isTrialActive(LocalDate startDate, int trialDays) {
        LocalDate today = LocalDate.now(clock);
        LocalDate endDate = startDate.plusDays(trialDays);
        return !today.isBefore(startDate) && today.isBefore(endDate);
    }
}
~~~

A test can construct a clock at a specific date:

~~~java
Clock testClock = Clock.fixed(
        Instant.parse("2026-11-15T12:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

TrialPolicy policy = new TrialPolicy(testClock);
~~~

In this example, `LocalDate.now(clock)` obtains the date in the zone attached to the clock. With `Asia/Ho_Chi_Minh`, the instant `2026-11-15T12:00:00Z` corresponds to evening on the same date in Vietnam. When testing near midnight, the zone is an essential part of the test data, not a decorative detail.

## 6. Clock and Time Zones: Choosing According to Business Meaning

`Clock` carries both a time source and a `ZoneId`. Remember that **Instant is a point on the timeline**, whereas `LocalDate` and `LocalDateTime` are local calendar values that depend on a time zone when converted from an instant.

### 6.1. Use UTC for Absolute Points in Time

For timestamps used in logging, event storage, or inter-system exchange, `Instant` should generally be used:

~~~java
Instant createdAt = Instant.now(clock);
~~~

`Instant` represents a point on the UTC timeline and contains no local time zone. When displaying to a user, convert it to their zone:

~~~java
ZonedDateTime localView =
        createdAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

### 6.2. Use an Explicit Zone for Business Dates

A "today" report for a store in Vietnam may differ from today on a server located in the US. Therefore, specify the business zone explicitly:

~~~java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
Clock businessClock = Clock.system(businessZone);

LocalDate businessDate = LocalDate.now(businessClock);
~~~

Do not implicitly rely on the server's default time zone via `Clock.systemDefaultZone()` if business logic needs a stable zone. The default value can differ between developer machines, CI runners, and production.

### 6.3. `withZone` Changes the View, Not the Underlying Instant

~~~java
Clock utcClock = Clock.fixed(
        Instant.parse("2026-11-15T23:30:00Z"),
        ZoneOffset.UTC);

Clock vietnamClock = utcClock.withZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(LocalDate.now(utcClock));
System.out.println(LocalDate.now(vietnamClock));
~~~

Both clocks represent the same fixed instant, yet `LocalDate.now` can return different dates because their zones differ. This is why date-based tests need to specify the zone, especially when handling users across multiple countries or timestamps near midnight.

### 6.4. Avoid Manually Adding Hours to Convert Time Zones

Do not do this:

~~~java
// Do not use fixed addition to convert time zones.
Instant local = Instant.now(clock).plus(Duration.ofHours(7));
~~~

Time zones are sets of historical rules and may include daylight saving time (*daylight saving time*) rules. Use `ZoneId` and the Java Time API conversions instead:

~~~java
ZonedDateTime local = Instant.now(clock)
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

When working with zones that observe daylight saving time, `ZonedDateTime` and zone rules data handle skipped or repeated hours properly. A fixed offset such as `ZoneOffset.ofHours(7)` is only appropriate when the contract truly requires a fixed offset, not as a substitute for a geographical time zone.

## 7. Designing Services Without Depending on the System Clock

An application often has many classes that need to know the time. If each class calls `Instant.now()` on its own, timestamps within a single operation can become inconsistent and very hard to control in tests. Pass the same `Clock` into objects that need a time source.

Example of an event-creating service:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class OrderService {
    private final Clock clock;

    public OrderService(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public OrderCreated createOrder(String orderId) {
        Objects.requireNonNull(orderId, "orderId");
        return new OrderCreated(orderId, Instant.now(clock));
    }
}

record OrderCreated(String orderId, Instant createdAt) {
}
~~~

Here, the order creation timestamp is read from the passed-in clock. There is no need to pass `Instant.now()` from the outside every time `createOrder` is called, because the service needs **a time source that can be read at the time of the operation**, not a precomputed timestamp.

### 7.1. Sharing the Same Clock Across Services

~~~java
Clock clock = Clock.systemUTC();

OrderService orderService = new OrderService(clock);
TrialService trialService = new TrialService(clock);
~~~

In production, both services read from one clock configured at the composition root. In tests, you can substitute a single `Clock.fixed` for both to test an end-to-end scenario.

There is no need for a global static clock object. Passing dependencies explicitly makes it clear which classes need time, makes swapping easy in tests, and avoids hidden dependencies in code.

### 7.2. Constructor Injection in a DI Framework

If the application uses a dependency injection framework, you can register a clock bean and inject it via constructors:

~~~java
// Illustrates constructor structure; independent of any specific framework.
public final class AuditService {
    private final Clock clock;

    public AuditService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public Instant recordedAt() {
        return Instant.now(clock);
    }
}
~~~

The framework can provide `Clock.systemUTC()` in the production configuration and a fixed clock in the test configuration. If you do not use a framework, manually constructing it in `main` or an application factory is still dependency injection.

## 8. Clock for LocalDate, LocalDateTime, and ZonedDateTime

Not every time problem requires `Instant`. Choose the type based on what the data means:

| Type | Meaning | How to get from a clock |
|---|---|---|
| `Instant` | Absolute point on the UTC timeline. | `Instant.now(clock)` |
| `LocalDate` | Calendar date without time or zone. | `LocalDate.now(clock)` |
| `LocalTime` | Time on a local clock without date or zone. | `LocalTime.now(clock)` |
| `LocalDateTime` | Local date and time without offset/zone. | `LocalDateTime.now(clock)` |
| `OffsetDateTime` | Date and time with a specific UTC offset. | `OffsetDateTime.now(clock)` |
| `ZonedDateTime` | Date and time tied to a `ZoneId`. | `ZonedDateTime.now(clock)` |

Example of a report needing a local date:

~~~java
LocalDate reportDate = LocalDate.now(
        clock.withZone(ZoneId.of("Asia/Ho_Chi_Minh")));
~~~

Example of an audit event needing a timestamp:

~~~java
Instant eventTime = Instant.now(clock);
~~~

Do not store `LocalDateTime` for a global event without also storing its zone or offset; a local time can be ambiguous across daylight saving time transitions. For events that need to pinpoint an exact instant, `Instant` is usually the easiest type to exchange across systems.

## 9. Testing Time Boundaries

Passing a `Clock` enables testing scenarios that previously required waiting for the real clock to advance:

- Expiration right at the current instant.
- One second before or after expiration.
- First day or last day of a trial period.
- Start of month, end of month, leap day, and New Year's Eve.
- Times near midnight in the business time zone.
- Offset changes caused by daylight saving time in zones that observe it.

### 9.1. Testing Leap Days and End-of-Month Dates

Suppose a service determines whether a report belongs to the current month:

~~~java
public final class MonthlyReportService {
    private final Clock clock;

    public MonthlyReportService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public boolean belongsToCurrentMonth(LocalDate date) {
        YearMonth currentMonth = YearMonth.now(clock);
        return YearMonth.from(date).equals(currentMonth);
    }
}
~~~

Testing with a fixed date:

~~~java
Clock februaryClock = Clock.fixed(
        Instant.parse("2024-02-29T12:00:00Z"),
        ZoneOffset.UTC);

MonthlyReportService service =
        new MonthlyReportService(februaryClock);

assertTrue(service.belongsToCurrentMonth(
        LocalDate.of(2024, 2, 1)));
assertFalse(service.belongsToCurrentMonth(
        LocalDate.of(2024, 3, 1)));
~~~

The year 2024 is a leap year, so February has day 29. The test does not have to wait until February or change the OS clock.

### 9.2. Testing Time Zones Across a Date Boundary

~~~java
Instant nearMidnightUtc =
        Instant.parse("2026-11-15T23:30:00Z");

Clock utc = Clock.fixed(nearMidnightUtc, ZoneOffset.UTC);
Clock vietnam = utc.withZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));

assertEquals(LocalDate.of(2026, 11, 15), LocalDate.now(utc));
assertEquals(LocalDate.of(2026, 11, 16), LocalDate.now(vietnam));
~~~

The two different results are right because the same absolute point in time is viewed from two different time zones. This test is helpful for systems with regional reports or regional business deadlines.

## 10. When You Need to Simulate Advancing Time

`Clock.fixed` does not move forward. That is great for tests needing a stable instant, but may not be enough when you want to test multiple steps over time within a single test.

One option is using `Clock.offset` from different fixed clocks for each phase:

~~~java
Instant start = Instant.parse("2026-11-15T10:00:00Z");
Clock startClock = Clock.fixed(start, ZoneOffset.UTC);
Clock afterTenMinutes = Clock.offset(
        startClock, Duration.ofMinutes(10));
~~~

Or create two service instances with two corresponding fixed clocks to simulate before and after a milestone. This keeps the test simple without needing a mutable stateful clock.

### 10.1. A Mutable Clock Should Only Be an Intentional Test Utility

If multiple steps on the same object must observe time changing, you can write a small `Clock` implementation in the test. Illustrative example:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.util.Objects;

final class AdjustableClock extends Clock {
    private Instant current;
    private final ZoneId zone;

    AdjustableClock(Instant initial, ZoneId zone) {
        this.current = Objects.requireNonNull(initial);
        this.zone = Objects.requireNonNull(zone);
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        return new AdjustableClock(current, newZone);
    }

    @Override
    public Instant instant() {
        return current;
    }

    void advance(Duration duration) {
        current = current.plus(duration);
    }
}
~~~

The test can control time:

~~~java
AdjustableClock clock = new AdjustableClock(
        Instant.parse("2026-11-15T10:00:00Z"),
        ZoneOffset.UTC);

TrialService service = new TrialService(clock);
Instant expiresAt =
        Instant.parse("2026-11-15T10:05:00Z");

assertFalse(service.isExpired(expiresAt));

clock.advance(Duration.ofMinutes(5));

assertTrue(service.isExpired(expiresAt));
~~~

This is a simple test utility, not a production-grade implementation. It is not thread-safe, and `withZone` returns a new clock with the time state at creation; if a test needs multiple zones sharing a single mutable clock, design shared state and explicit synchronization. In most tests, two `Clock.fixed` instances or `Clock.offset` are sufficient.

## 11. Distinguishing Calendar Time from Interval Measurement

An important point: `Clock` describes **current civil clock time** (*wall-clock time*). The system clock can be resynchronized, manually adjusted, or changed by OS mechanisms. Therefore, `Clock` is not a suitable source for accurately measuring elapsed time.

If you need to measure execution duration, timeouts, or benchmarks, use `System.nanoTime()`:

~~~java
long start = System.nanoTime();

performWork();

long elapsedNanos = System.nanoTime() - start;
Duration elapsed = Duration.ofNanos(elapsedNanos);
System.out.println("Elapsed: " + elapsed);
~~~

`System.nanoTime()` uses a monotonic clock (*monotonic time source*) that allows measuring intervals. The returned value is not a timestamp that can be converted into a calendar date and time; you should only take the difference between two reads within the same JVM.

| Goal | Appropriate API |
|---|---|
| Recording order creation timestamp | `Instant.now(clock)` |
| Determining business date in a zone | `LocalDate.now(clock.withZone(zone))` |
| Checking expiration | `Instant.now(clock)` compared to `expiresAt` |
| Measuring method execution time | `System.nanoTime()` |
| Creating monotonic deadlines/timeouts | `System.nanoTime()` or properly designed high-level timeout APIs |
| Performance benchmarking | Dedicated benchmarking tools; do not use wall clock for short durations |

Do not read two `Instant.now(clock)` values and subtract them for benchmarks or clock-adjustment-sensitive timeouts. For measuring durations, a monotonic clock is the right choice.

## 12. Common Design Mistakes

| Practice | Problem | How to handle |
|---|---|---|
| Calling `Instant.now()` scattered across services | Hard for tests to control the point in time; hidden time dependency. | Inject `Clock` via constructor and call `Instant.now(clock)`. |
| Storing `Instant.now(clock)` in constructor and reusing it | Service always uses initialization time. | Store `Clock`, read the instant when business logic needs it. |
| Creating `Clock.systemUTC()` inside every method | Hard to swap time source in tests and configuration. | Create the clock at the composition root and pass it in. |
| Using `Clock.systemDefaultZone()` for logic needing a stable zone | Results depend on server configuration. | Specify an explicit business `ZoneId`. |
| Assuming `Clock.fixed` advances automatically over time | It always returns the same instant. | Use another clock, `Clock.offset`, or an adjustable test utility. |
| Using `Clock` to measure execution duration | Wall clock can be adjusted. | Use `System.nanoTime()` for elapsed time. |
| Thinking `Instant` contains a time zone | `Instant` only represents an absolute point in time. | Use `ZonedDateTime` or convert via `ZoneId` when displaying. |
| Passing `LocalDateTime` across systems as a global timestamp | Lacks offset/zone, can be ambiguous. | Use `Instant` or a type with offset/zone per contract. |
| Allowing null clock | Error only surfaces when business logic reads time. | Validate with `Objects.requireNonNull` in the constructor. |
| Using an unsynchronized mutable clock across threads | Tests or logic can hit race conditions. | Prefer immutable clocks; if mutable is needed, synchronize and restrict to tests. |

## 13. Complete Example: Trial Issuance and Expiration Service

The example below combines constructor injection, creation timestamp, and expiration rules. Both classes can be placed in the same `TrialDemo.java` file if only one class is `public`:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

record Trial(Instant startedAt, Instant expiresAt) {
    Trial {
        Objects.requireNonNull(startedAt, "startedAt");
        Objects.requireNonNull(expiresAt, "expiresAt");
        if (expiresAt.isBefore(startedAt)) {
            throw new IllegalArgumentException(
                    "expiresAt must not be before startedAt");
        }
    }
}

final class TrialManager {
    private final Clock clock;
    private final Duration trialDuration;

    TrialManager(Clock clock, Duration trialDuration) {
        this.clock = Objects.requireNonNull(clock, "clock");
        this.trialDuration =
                Objects.requireNonNull(trialDuration, "trialDuration");
        if (trialDuration.isNegative()) {
            throw new IllegalArgumentException(
                    "trialDuration must not be negative");
        }
    }

    Trial startTrial() {
        Instant startedAt = Instant.now(clock);
        return new Trial(startedAt, startedAt.plus(trialDuration));
    }

    boolean isExpired(Trial trial) {
        Objects.requireNonNull(trial, "trial");
        return !Instant.now(clock).isBefore(trial.expiresAt());
    }
}

public final class TrialDemo {
    private TrialDemo() {
    }

    public static void main(String[] args) {
        Clock clock = Clock.systemUTC();
        TrialManager manager =
                new TrialManager(clock, Duration.ofDays(14));

        Trial trial = manager.startTrial();
        System.out.println("Started: " + trial.startedAt());
        System.out.println("Expires: " + trial.expiresAt());
        System.out.println("Expired: " + manager.isExpired(trial));
    }
}
~~~

In production, `Clock.systemUTC()` is passed into the manager. In tests, a fixed clock can be passed and checked precisely:

~~~java
Instant start = Instant.parse("2026-11-15T10:00:00Z");
Clock clock = Clock.fixed(start, ZoneOffset.UTC);

TrialManager manager =
        new TrialManager(clock, Duration.ofDays(14));

Trial trial = manager.startTrial();
assertEquals(start, trial.startedAt());
assertEquals(start.plus(Duration.ofDays(14)), trial.expiresAt());
~~~

If you need to test the manager after 14 days, create a manager with a corresponding offset/fixed clock or use an adjustable test clock as in section 10. This makes time in tests completely deterministic.

## 14. Practice Exercises

### Exercise 1 — Switching from Direct Time Calls to Clock Injection

Given the class:

~~~java
public final class InvoiceService {
    public Invoice create(String id) {
        return new Invoice(id, Instant.now());
    }
}
~~~

Add a `Clock` field and a constructor accepting the clock, then replace the direct call with `Instant.now(clock)`. Create a production instance using `Clock.systemUTC()`.

### Exercise 2 — Checking Expiration at Boundaries

Write tests for an `isExpired(Instant expiresAt)` method using a fixed clock. Include at least three cases: deadline in the future, deadline in the past, and deadline equal to the current instant. State clearly which equality policy you chose.

### Exercise 3 — Simulating a Business Date

A store closes its daily report at 00:00 in `Asia/Ho_Chi_Minh`. Use `Clock.fixed` to test an instant near 17:00 UTC and determine the corresponding business date. Compare the result with `LocalDate.now(Clock.systemUTC())`.

### Exercise 4 — Distinguishing Clock and nanoTime

Write a snippet that measures the duration of a task using `System.nanoTime()`. Explain why `Instant.now(clock)` should not be used for benchmarking or timeouts.

### Exercise 5 — Testing Advancing Time

Use two fixed clocks or `Clock.offset` to simulate a point before and after a trial deadline. Write two tests for the same service and verify that the result changes according to the injected clock.

### Self-Check Hints

- Exercise 1: The constructor stores `Objects.requireNonNull(clock)` in a `private final` field.
- Exercise 2: Use `Clock.fixed(now, ZoneOffset.UTC)` and verify results match the before/at/after deadline rules.
- Exercise 3: Convert the instant to the business zone; do not add a fixed number of hours in place of `ZoneId`.
- Exercise 4: `nanoTime` measures elapsed time; `Clock` provides wall-clock time.
- Exercise 5: `Clock.offset(fixed, Duration.ofDays(...))` can simulate a future milestone without changing the system clock.

## 15. Principles for Project Adoption

- Objects that need to know the current time should accept `Clock` via their constructor.
- Create system clocks only at the application's assembly point; pass the same time source to services that need it.
- Call `Instant.now(clock)`, `LocalDate.now(clock)`, or equivalent APIs instead of uncontrollable direct calls.
- Use `Clock.fixed` for deterministic tests and `Clock.offset` to simulate offsets; only write a mutable clock when a test genuinely needs time to advance on the same object.
- Choose `ZoneId` according to business rules. Use `Instant` for absolute points in time, converting to a zone when displaying or computing local dates.
- Do not use `Clock` to measure execution time or timeouts sensitive to clock adjustments; use `System.nanoTime()`.
- Do not assume `Clock.systemDefaultZone()` is identical across environments.
- Test boundaries: before deadline, at deadline, after deadline, start/end of day, and time zones.

Passing a time source into objects is a small structural change that makes date-time logic much easier to test and reason about. With Java 17, `Clock` provides the built-in abstraction needed for applications to use the real clock in production and controllable instants in tests.

### References

- [Java SE 17 API — `Clock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html).
- [Java SE 17 API — `Instant`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html).
- [Java SE 17 API — `LocalDate`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html).
- [Java SE 17 API — `ZoneId`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html).
- [Java SE 17 API — `System.nanoTime()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()).
