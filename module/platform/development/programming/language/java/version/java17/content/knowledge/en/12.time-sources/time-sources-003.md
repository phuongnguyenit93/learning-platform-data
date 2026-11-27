# Time Sources in Java 17: Creating system, fixed, offset, and tick Clocks

Java applications often need to know the current point in time to record order creation timestamps, determine business dates, check deadlines, or order events. If you call `Instant.now()` or `LocalDate.now()` directly everywhere, business logic becomes coupled to the machine's real clock. That makes tests hard to reproduce, because results change depending on when they run.

The `java.time.Clock` API provides a **replaceable time source**. Instead of letting every class read the system clock directly, an application can receive a `Clock` instance via a constructor or parameter. In production, use the system clock; in tests, use a fixed clock; when simulation is needed, use a time-shifted clock or one that only advances in ticks.

This lesson explains four ways to create time sources in Java 17: **system**, **fixed**, **offset**, and **tick**; while also distinguishing absolute instants from time zones, how to inject a clock, and the limitations to know when using tick.

## 1. Why Do We Need a Time Source?

Simple code can retrieve the current point in time directly:

~~~java
import java.time.Instant;

Instant createdAt = Instant.now();
System.out.println(createdAt);
~~~

This snippet is valid, but the class containing the logic has no control over the time source. During testing, each call can return a different instant. If you need to test "an order expires after 30 minutes," the test must rely on the real clock or wait for time to pass.

Instead, obtain time through a `Clock`:

~~~java
import java.time.Clock;
import java.time.Instant;

Clock clock = Clock.systemUTC();
Instant createdAt = Instant.now(clock);
~~~

Now, the time source is an object that can be substituted. The same code can receive:

- a system clock in production;
- a fixed clock in unit tests;
- an offset clock to simulate earlier or later time;
- a tick clock to truncate time to a predefined interval.

`Clock` is not a timer, scheduler, or monotonic counter. It is an abstraction providing **the current instant and the zone used to interpret that instant**.

## 2. Distinguishing Instant, ZoneId, and Clock

These three types often appear together but have different responsibilities:

| Type | Role | Example |
| --- | --- | --- |
| `Instant` | An absolute point on the UTC timeline. | `2026-11-15T10:00:00Z` |
| `ZoneId` | Time-zone rules used to convert an instant into local date/time, including DST rules if any. | `Asia/Ho_Chi_Minh` |
| `Clock` | A source providing an instant and a zone. | `Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"))` |

An instant does not carry a time zone on its own. The same instant can be displayed as different local times:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant instant = Instant.parse("2026-11-15T10:00:00Z");

ZonedDateTime inUtc = instant.atZone(ZoneId.of("UTC"));
ZonedDateTime inHcm = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(inUtc);
System.out.println(inHcm);
~~~

The output represents the same instant, but the local time portions differ:

~~~text
2026-11-15T10:00Z[UTC]
2026-11-15T17:00+07:00[Asia/Ho_Chi_Minh]
~~~

Therefore, when creating a clock, choose the zone according to its business meaning:

- Use UTC when you need a consistent point in time for storage, exchange, or logging.
- Use a specific zone when logic needs the local date/time of a region.
- Avoid implicitly relying on the server's default time zone if business logic requires a specific zone.

## 3. Creating System Clocks: system, systemUTC, and systemDefaultZone

### 3.1. Clock.system(ZoneId)

Creates a clock based on the system clock with the specified zone:

~~~java
import java.time.Clock;
import java.time.ZoneId;

Clock hcmClock = Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Each time `hcmClock.instant()` is called, the clock reads the current instant from the system's time source. APIs like `LocalDate.now(hcmClock)` use the clock's zone to determine the local date.

Example:

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;

public class SystemClockDemo {
    public static void main(String[] args) {
        Clock clock = Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("Instant: " + clock.instant());
        System.out.println("Date: " + LocalDate.now(clock));
        System.out.println("Time: " + LocalTime.now(clock));
    }
}
~~~

`Clock.system(zone)` is suitable when you want system time while explicitly specifying the interpretation time zone.

### 3.2. Clock.systemUTC()

If the application primarily works with UTC instants, use:

~~~java
Clock utcClock = Clock.systemUTC();
Instant now = Instant.now(utcClock);
~~~

This clock has the UTC zone. It is a clear choice for cases needing absolute timestamps without depending on the time zone configured on the host machine.

### 3.3. Clock.systemDefaultZone()

Creates a clock using the JVM's default time zone:

~~~java
Clock defaultClock = Clock.systemDefaultZone();
System.out.println(defaultClock.getZone());
~~~

This option is useful when the application genuinely intends to follow the process's default time-zone configuration. However, results can differ across developer machines, CI runners, containers, and production if configurations are inconsistent.

If business logic requires a fixed zone, use `Clock.system(ZoneId.of("..."))` to express intent clearly.

### 3.4. System Clocks Are Not Monotonic Clocks

System clocks reflect calendar time (wall-clock time). Time can be adjusted by the operating system, NTP synchronization, administrators, or virtualization environments. Thus, two consecutive reads are not guaranteed to advance at a steady pace.

To measure **elapsed time** or execution duration, use `System.nanoTime()`:

~~~java
long start = System.nanoTime();
performWork();
long elapsedNanos = System.nanoTime() - start;
System.out.println("Elapsed ns = " + elapsedNanos);
~~~

Do not use `Instant.now(clock)` for benchmarking or measuring elapsed time if a monotonic clock is required. Use `Clock` for calendar points in time; use `System.nanoTime()` for measuring intervals.

## 4. Creating Fixed Clocks: Clock.fixed

`Clock.fixed(Instant, ZoneId)` creates a clock that always returns **the same instant**. This is a very useful option for unit tests and simulations.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;

Instant fixedInstant = Instant.parse("2026-04-10T03:00:00Z");
Clock fixedClock = Clock.fixed(
        fixedInstant,
        ZoneId.of("Asia/Ho_Chi_Minh")
);

System.out.println(fixedClock.instant());
System.out.println(fixedClock.instant());
~~~

Both calls return:

~~~text
2026-04-10T03:00:00Z
2026-04-10T03:00:00Z
~~~

The clock's time zone does not change the fixed instant. It only affects how APIs convert the instant into local date/time.

### 4.1. Using a Fixed Clock to Test Local Dates

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

public class FixedClockDemo {
    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2026-04-10T18:00:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh")
        );

        System.out.println(Instant.now(clock));
        System.out.println(LocalDate.now(clock));
    }
}
~~~

The instant is 18:00 UTC; in Ho Chi Minh City, that is 01:00 AM the next day. Therefore, the printed local date is:

~~~text
2026-04-11
~~~

This example shows that tests must fix both the **instant** and the **zone** if logic depends on the local date.

### 4.2. Application in Unit Tests

Suppose a service needs to record the order creation timestamp:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

final class OrderService {
    private final Clock clock;

    OrderService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    Instant createdAt() {
        return Instant.now(clock);
    }
}
~~~

Tests do not need to wait or depend on the machine's clock:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

public class OrderServiceDemo {
    public static void main(String[] args) {
        Instant expected = Instant.parse("2026-04-10T03:00:00Z");
        Clock testClock = Clock.fixed(expected, ZoneOffset.UTC);

        OrderService service = new OrderService(testClock);

        System.out.println(service.createdAt().equals(expected)); // true
    }
}
~~~

Tests are repeatable with the same input. This is the biggest benefit of injecting `Clock`: time becomes a controllable dependency.

## 5. Creating Time-Shifted Clocks: Clock.offset

`Clock.offset(baseClock, duration)` creates a clock whose instant equals the base clock's instant plus a duration. The duration can be positive or negative.

~~~java
import java.time.LocalDateTime;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

Instant baseInstant = Instant.parse("2026-04-10T03:00:00Z");
Clock base = Clock.fixed(baseInstant, ZoneOffset.UTC);

Clock twoHoursLater = Clock.offset(base, Duration.ofHours(2));
Clock oneDayEarlier = Clock.offset(base, Duration.ofDays(-1));

System.out.println(twoHoursLater.instant());
System.out.println(oneDayEarlier.instant());
~~~

Output:

~~~text
2026-04-10T05:00:00Z
2026-04-09T03:00:00Z
~~~

An offset clock preserves the base clock's zone; it shifts the returned **instant**.

### 5.1. offset Differs from withZone

Two operations are often confused:

- `Clock.offset(base, duration)` changes the instant by adding a duration.
- `base.withZone(zone)` keeps the instant unchanged, only changing the zone used to represent the date/time.

~~~java
Clock base = Clock.fixed(
        Instant.parse("2026-04-10T03:00:00Z"),
        ZoneOffset.UTC
);

Clock shifted = Clock.offset(base, Duration.ofHours(2));
Clock sameInstantInHcm =
        base.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(base.instant().equals(shifted.instant())); // false
System.out.println(base.instant().equals(sameInstantInHcm.instant())); // true
System.out.println(LocalDateTime.now(base));
System.out.println(LocalDateTime.now(sameInstantInHcm));
~~~

`withZone` is not a way to "add hours"; it only changes how the same point in time is interpreted. If you want to simulate a clock running two hours ahead, use `offset`.

### 5.2. Simulating Time in Tests

Example of a deadline-checking service:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

Instant start = Instant.parse("2026-04-10T03:00:00Z");
Clock fixed = Clock.fixed(start, ZoneOffset.UTC);
Clock thirtyMinutesLater =
        Clock.offset(fixed, Duration.ofMinutes(30));

System.out.println(Instant.now(fixed));
System.out.println(Instant.now(thirtyMinutesLater));
~~~

You can test both the "not expired" and "expired" branches without waiting 30 real minutes. In more complex tests, pass different clocks into the service or create offset clocks per scenario.

## 6. Creating Clocks That Advance in Ticks: Clock.tick

`Clock.tick(baseClock, tickDuration)` creates a clock that gets time from the base clock but **rounds down to tick boundaries**. For example, with a 10-second tick, observed time only changes at 00, 10, 20, 30, 40, and 50 seconds.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.ZoneOffset;

Clock base = Clock.systemUTC();
Clock tenSecondClock = Clock.tick(base, Duration.ofSeconds(10));

System.out.println(tenSecondClock.instant());
~~~

If system time is 12:34:27.800Z, the corresponding tick value is truncated down to 12:34:20Z.

### 6.1. Convenience Factories

Java provides convenient factory methods:

| Factory | Effect |
| --- | --- |
| `Clock.tickMillis(zone)` | Clock ticking by milliseconds. |
| `Clock.tickSeconds(zone)` | Clock ticking by seconds. |
| `Clock.tickMinutes(zone)` | Clock ticking by minutes. |
| `Clock.tick(base, duration)` | Choose your own base clock and tick duration. |

Example:

~~~java
Clock secondsInHcm =
        Clock.tickSeconds(ZoneId.of("Asia/Ho_Chi_Minh"));
Clock minutesUtc = Clock.tickMinutes(ZoneOffset.UTC);
Clock millisUtc = Clock.tickMillis(ZoneOffset.UTC);
~~~

The convenience factories are equivalent to ticking a system clock with the passed-in zone and corresponding duration.

### 6.2. Duration Rules

The tick duration must be **greater than zero**. An invalid duration can cause `Clock.tick` to throw `IllegalArgumentException`. For durations with a sub-millisecond part, the API rules require the duration to divide evenly into one second so ticks can be determined accurately in nanoseconds.

Examples of common intervals:

~~~java
Clock oneSecond = Clock.tick(Clock.systemUTC(), Duration.ofSeconds(1));
Clock fiveMinutes = Clock.tick(Clock.systemUTC(), Duration.ofMinutes(5));
Clock halfSecond = Clock.tick(Clock.systemUTC(), Duration.ofMillis(500));
~~~

Choose the tick interval according to the required precision. A 1-minute tick is unsuitable if the application needs millisecond-accurate timestamps.

### 6.3. Tick Is Not an Event Scheduler

A tick clock only truncates the time values it returns. It **does not emit signals**, does not invoke callbacks on each tick, and does not guarantee tasks run at exact tick marks.

Furthermore, implementations may use caching strategies. As a result, the observed moment when a new tick begins can be later than the actual start of that interval. Do not use `Clock.tick` to accurately measure elapsed time, drive animations, build a scheduler, or replace `ScheduledExecutorService`.

If you need to run a periodic task, use a scheduler:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

var scheduler = Executors.newSingleThreadScheduledExecutor();
scheduler.scheduleAtFixedRate(
        () -> System.out.println("Run task"),
        0,
        10,
        TimeUnit.SECONDS
);
~~~

This demonstration snippet should be shut down with `scheduler.shutdown()` when the application no longer needs the scheduler. The scheduler controls task execution; `Clock.tick` only provides truncated time values.

### 6.4. Ticking by a Duration Is Not Equivalent to Local Calendar Boundaries

Do not assume `Clock.tick(base, Duration.ofDays(1))` correctly expresses "a clock that only changes at midnight in the local time zone." Tick is based on fixed durations, whereas a calendar day in a zone with DST rules can be 23 or 25 hours long.

If business logic needs the current date or start of day in a zone, use calendar APIs:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

LocalDate today = LocalDate.now(clock);
ZonedDateTime startOfDay =
        today.atStartOfDay(clock.getZone());
~~~

`atStartOfDay(zone)` applies time-zone rules to find the start of the calendar day. That is a different concept from ticking by a fixed duration.

## 7. Combining Clock Types

Factories can be combined to build a time source for a specific goal.

### 7.1. Ticking an Offset Clock

~~~java
Clock base = Clock.systemUTC();
Clock shifted = Clock.offset(base, Duration.ofMinutes(15));
Clock shiftedAndTicked =
        Clock.tick(shifted, Duration.ofSeconds(30));
~~~

Time is shifted forward by 15 minutes and then rounded down to 30-second boundaries. This is a simulation example; clearly document the meaning of time shifting in configuration or tests to avoid mistaking it for real time.

### 7.2. Changing the Zone of a Fixed Clock

~~~java
Instant instant = Instant.parse("2026-04-10T03:00:00Z");
Clock fixedUtc = Clock.fixed(instant, ZoneOffset.UTC);
Clock fixedHcm = fixedUtc.withZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);

System.out.println(fixedUtc.instant().equals(fixedHcm.instant())); // true
System.out.println(LocalDate.now(fixedUtc));
System.out.println(LocalDate.now(fixedHcm));
~~~

The instant remains fixed, while the local date can differ if the instant is near a date boundary.

## 8. Injecting Clock into an Application

Instead of calling `Instant.now()` or `LocalDate.now()` directly in every class, pass `Clock` into the places that need to know the time.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Objects;

public final class SubscriptionService {
    private final Clock clock;

    public SubscriptionService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public Instant subscriptionStartedAt() {
        return Instant.now(clock);
    }

    public LocalDate billingDate() {
        return LocalDate.now(clock);
    }
}
~~~

In the composition root or application configuration, create the production clock:

~~~java
Clock applicationClock =
        Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
SubscriptionService service =
        new SubscriptionService(applicationClock);
~~~

In unit tests, pass a fixed clock:

~~~java
Clock testClock = Clock.fixed(
        Instant.parse("2026-04-10T03:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh")
);
SubscriptionService service = new SubscriptionService(testClock);
~~~

Benefits:

- Tests do not depend on the machine's real date and time.
- Pre-deadline and post-deadline instants can be tested using `fixed` and `offset`.
- The zone is chosen explicitly in configuration.
- Business logic does not need to know whether the clock comes from the operating system or a test.

There is no need to inject `Clock` into every single class. Only pass it into components that genuinely depend on time, then pass the resulting values (`Instant`, `LocalDate`, etc.) to classes that do not need to read the clock themselves.

## 9. Time Methods That Accept Clock

Many types in `java.time` have overloads that accept a clock:

~~~java
Instant instant = Instant.now(clock);
LocalDate date = LocalDate.now(clock);
LocalTime time = LocalTime.now(clock);
LocalDateTime localDateTime = LocalDateTime.now(clock);
ZonedDateTime zonedDateTime = ZonedDateTime.now(clock);
OffsetDateTime offsetDateTime = OffsetDateTime.now(clock);
~~~

This makes it possible to share a single time source across multiple value types. Choose the type according to its meaning:

| Type | When to use |
| --- | --- |
| `Instant` | Need an absolute point in time for storage or cross-system exchange. |
| `LocalDate` | Need a calendar date in a zone. |
| `LocalTime` | Need a time of day in a zone. |
| `LocalDateTime` | Need a local date and time without carrying a zone/offset. |
| `ZonedDateTime` | Need a date-time tied to a zone and time-zone rules. |
| `OffsetDateTime` | Need a date-time with a specific UTC offset. |

If you need to store an event timestamp, `Instant` is usually preferred. Convert to local date/time only at the presentation boundary or when business rules genuinely depend on a region's calendar.

## 10. Limitations and Common Mistakes

| Symptom | Cause | How to fix |
| --- | --- | --- |
| Unit tests for the current date pass sometimes and fail other times | Code calls the system clock directly. | Inject `Clock` and use `Clock.fixed` in tests. |
| Dates differ between developer machines and servers | Using `systemDefaultZone()` or different default time zones. | Choose an explicit `ZoneId` per business rules. |
| Thinking `withZone` makes time run faster or slower | `withZone` only changes the zone, not the instant. | Use `Clock.offset` if you need to shift the instant. |
| Using `tick` to run a task every second | `Clock.tick` does not schedule or emit callbacks. | Use `ScheduledExecutorService` or an appropriate scheduler. |
| Daily tick drifts from local midnight | A fixed duration is not equivalent to a calendar day in a zone. | Use `LocalDate` and `atStartOfDay(zone)`. |
| Measuring elapsed time via two system clock reads | Wall clock can be adjusted. | Use `System.nanoTime()` to measure time intervals. |
| Tick duration is zero or negative | Invalid duration. | Use a positive duration as required by the API. |
| Needing high precision while using a minute/second tick | The clock has truncated the returned value. | Choose a smaller duration or an appropriate base clock. |
| Offset clock mistaken for system time | `Clock.offset` changes the returned instant. | Only use for simulation or intentional time rules. |

## 11. Comprehensive Example: Testing Subscription Expiration

The following example models a subscription with a 30-day lifetime. The service takes a clock to check status at the current time:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;

final class Subscription {
    private final Instant startedAt;

    Subscription(Instant startedAt) {
        this.startedAt = Objects.requireNonNull(startedAt);
    }

    boolean isExpired(Clock clock) {
        Instant expiresAt = startedAt.plus(Duration.ofDays(30));
        return !Instant.now(clock).isBefore(expiresAt);
    }
}

public class SubscriptionClockDemo {
    public static void main(String[] args) {
        Instant startedAt = Instant.parse("2026-01-01T00:00:00Z");
        Subscription subscription = new Subscription(startedAt);

        Clock beforeExpiry = Clock.fixed(
                Instant.parse("2026-01-30T23:59:59Z"),
                ZoneOffset.UTC
        );
        Clock atExpiry = Clock.fixed(
                Instant.parse("2026-01-31T00:00:00Z"),
                ZoneOffset.UTC
        );

        System.out.println(subscription.isExpired(beforeExpiry)); // false
        System.out.println(subscription.isExpired(atExpiry)); // true
    }
}
~~~

Both scenarios run instantaneously and the results do not depend on the machine's clock. The example uses `Duration.ofDays(30)` to represent exactly 30 × 24 hours. If the business rule is "expires on the same calendar date next month" or "expires at midnight in a zone," model it using `LocalDate`, `Period`, `ZonedDateTime`, and the corresponding calendar rules rather than treating it as the same duration.

## 12. Practice Exercises

### Exercise 1 — Choose the Clock Type

Choose the appropriate factory:

1. A production application needs the current UTC instant.
2. A unit test needs every read to return the exact same instant.
3. A test needs to simulate time 90 minutes ahead.
4. A report only needs time that updates once per minute.

**Hint:** `systemUTC`, `fixed`, `offset`, and `tickMinutes` respectively.

### Exercise 2 — Distinguish offset and zone

~~~java
Clock base = Clock.fixed(
        Instant.parse("2026-04-10T03:00:00Z"),
        ZoneOffset.UTC
);
Clock plusOneHour = Clock.offset(base, Duration.ofHours(1));
Clock hcmZone = base.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Predict:

- Which clock returns an instant different from `base`?
- Which clock only changes how the instant is converted to local time?

**Answer:** `plusOneHour` returns a different instant; `hcmZone` preserves the instant and changes the zone.

### Exercise 3 — Testing Without Depending on the Real Clock

Write a class `ReminderService` that accepts a `Clock` via its constructor and has a method returning the current date. Create two tests with two `Clock.fixed` instances on different dates to demonstrate that the result is controllable.

### Exercise 4 — Tick and Scheduler

Explain why `Clock.tickSeconds(ZoneOffset.UTC)` cannot replace a scheduler that runs work every second. State the appropriate API for scheduling tasks and the appropriate API for obtaining truncated time.

### Exercise 5 — Calendar Day or Duration?

A service plan expiring "after 24 hours" versus "at the start of the next day in the customer's time zone" are two different requirements. Choose among `Duration`, `LocalDate`, `ZoneId`, and `atStartOfDay` for each case, and explain the impact of a day with a DST transition.

## 13. Key Points When Creating Time Sources

- `Clock` provides an instant and a zone; it decouples business logic from the real clock.
- `Clock.system(zone)` reads system time with the chosen zone; `systemUTC()` uses UTC; `systemDefaultZone()` depends on the JVM's default time zone.
- `Clock.fixed(instant, zone)` always returns the same instant, which is very useful for unit tests.
- `Clock.offset(base, duration)` shifts the base clock's instant; duration can be positive or negative.
- `Clock.tick(base, duration)` truncates down to tick boundaries; `tickMillis`, `tickSeconds`, and `tickMinutes` are convenience factories.
- `withZone(zone)` changes the zone while keeping the instant unchanged; do not confuse it with `offset`.
- Tick is not a scheduler, not a duration timer, and does not automatically represent calendar day boundaries.
- Use `System.nanoTime()` to measure elapsed time; use `Clock`/`Instant` for calendar points in time.
- Inject `Clock` into time-dependent components so tests are deterministic and easy to simulate.

### References

- [Java SE 17 API — `java.time.Clock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html) — system, fixed, offset, tick factories, zones, and Clock contract.
- [Java SE 17 API — `Instant`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html) — representing absolute instants and the `now(Clock)` overload.
- [Java SE 17 API — `ZoneId`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html) — time-zone identifiers and zone rules.
- [Java SE 17 API — `System.nanoTime()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()) — monotonic time source for measuring duration.
- [Java SE 17 API — `ScheduledExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html) — scheduling periodic or delayed tasks.
