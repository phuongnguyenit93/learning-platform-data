# Calculating Duration and Handling Boundary Timestamps

## 1. Time Problems: A Point in Time, an Interval, or a Calendar Date?

In Java, many time-related bugs appear because programs use the same data type for different concepts:

- **Point in time (timestamp/instant):** a specific point on the timeline, such as when an order was created.
- **Duration:** the amount of time elapsed between two points, such as a request taking 350 milliseconds.
- **Calendar date:** November 15, 2026 in a specific time zone.
- **Local time:** 09:30 on a region's clock, which may need a time zone to determine which UTC instant it corresponds to.
- **Business time range:** for example, all transactions belonging to today in Vietnam, or a deadline window from 09:00 to 17:00.

Java 17 includes the Java Time API in the `java.time` package, introduced in Java 8. Commonly used types:

| Type | Represents | Carries a time zone / timeline position? |
|---|---|---|
| `Instant` | A point in time | Has global timeline meaning, normalized to UTC |
| `Duration` | An amount of time in seconds and nanoseconds | No |
| `Period` | An amount of calendar time in years, months, and days | No |
| `LocalDate` | A calendar date | No |
| `LocalTime` | A time of day | No |
| `LocalDateTime` | Local date and time | No |
| `OffsetDateTime` | Date and time with a UTC offset | Has an offset, not necessarily region rules |
| `ZonedDateTime` | Date and time with a region time zone | Has a `ZoneId` and time-zone rules |
| `Clock` | Source of the current time | Defines how instants are obtained and a configured zone |

This topic focuses on **calculating Duration and handling boundary timestamps**: computing elapsed time, defining start/end of a range, handling dates in a time zone, and avoiding bugs from DST or timestamp precision.

An important principle:

> Use `Instant` for points on the timeline, `Duration` for actual elapsed time, `Period` and `LocalDate` for calendar concepts, and convert via `ZoneId` at business boundaries.

## 2. Instant: Representing a Point in Time Independent of Display Time Zone

### 2.1. Creating and Reading Instant

`Instant` represents a point on the timeline, typically used to store record creation timestamps, event receipts, request sends, or task completions.

~~~java
import java.time.Instant;

public class InstantExample {
    public static void main(String[] args) {
        Instant now = Instant.now();
        Instant event = Instant.parse("2026-11-15T14:00:00Z");

        System.out.println("Now: " + now);
        System.out.println("Event: " + event);
        System.out.println("Epoch seconds: " + event.getEpochSecond());
        System.out.println("Nano adjustment: " + event.getNano());
    }
}
~~~

The ISO-8601 string `2026-11-15T14:00:00Z` has the `Z` suffix, meaning UTC. An `Instant` does not carry a time-zone name like `Asia/Ho_Chi_Minh`; it represents a specific point in time.

`Instant` has nanosecond resolution in the API, but the actual precision of the clock, operating system, JVM, and time source may be lower. Do not assume that consecutive calls to `Instant.now()` always produce values separated by a single nanosecond.

### 2.2. Comparing and Shifting Instants

~~~java
Instant start = Instant.parse("2026-11-15T10:00:00Z");
Instant end = start.plusSeconds(90);

System.out.println(start.isBefore(end)); // true
System.out.println(end.isAfter(start));  // true
System.out.println(start.equals(end));   // false
~~~

Commonly used operations:

- `plus(Duration)`, `minus(Duration)`: shift an instant by a duration.
- `isBefore`, `isAfter`, `equals`: compare two instants.
- `getEpochSecond()`, `getNano()`: read time components.
- `toEpochMilli()`: convert to epoch milliseconds, which can lose the sub-millisecond nano portion and throw `ArithmeticException` if outside `long` range.

`Instant` has no concept of "start of day in Vietnam time" until combined with a `ZoneId`.

## 3. Duration: Calculating Elapsed Time

### 3.1. Creating a Duration with `between`

`Duration` represents an amount of time in seconds and nanoseconds. The most common way to compute it is:

~~~java
import java.time.Duration;
import java.time.Instant;

Instant startedAt = Instant.parse("2026-11-15T10:00:00Z");
Instant finishedAt = Instant.parse("2026-11-15T10:02:35.500Z");

Duration elapsed = Duration.between(startedAt, finishedAt);

System.out.println(elapsed);            // PT2M35.5S
System.out.println(elapsed.toSeconds()); // 155
System.out.println(elapsed.toMillis());  // 155500
~~~

`Duration.between(start, end)` computes the interval from `start` to `end`. If `end` is earlier than `start`, the returned Duration is **negative**.

~~~java
Duration positive = Duration.between(
        Instant.parse("2026-11-15T10:00:00Z"),
        Instant.parse("2026-11-15T10:00:05Z")
);

Duration negative = Duration.between(
        Instant.parse("2026-11-15T10:00:05Z"),
        Instant.parse("2026-11-15T10:00:00Z")
);

System.out.println(positive); // PT5S
System.out.println(negative); // PT-5S
System.out.println(negative.isNegative()); // true
~~~

A negative Duration is not an API bug. It can represent a missed deadline, two points passed in reverse order, or a signed offset. If business logic requires a non-negative duration, validate the order of the points instead of silently taking the absolute value.

### 3.2. Creating a Duration from Units

~~~java
Duration zero = Duration.ZERO;
Duration oneSecond = Duration.ofSeconds(1);
Duration halfSecond = Duration.ofMillis(500);
Duration tenMillis = Duration.ofNanos(10_000_000);
Duration oneHour = Duration.ofHours(1);
Duration oneDay = Duration.ofDays(1);
~~~

Common factories:

| Factory | Duration |
|---|---|
| `Duration.ofNanos(n)` | `n` nanoseconds |
| `Duration.ofMillis(n)` | `n` milliseconds |
| `Duration.ofSeconds(n)` | `n` seconds |
| `Duration.ofMinutes(n)` | `n` minutes |
| `Duration.ofHours(n)` | `n` hours |
| `Duration.ofDays(n)` | `n × 24` hours |
| `Duration.parse(text)` | Parses a string in ISO-8601 Duration format |

Important point: `Duration.ofDays(1)` is **exactly 86,400 seconds**, not "one day on a local calendar." A calendar day can be 23 or 25 hours long when clocks undergo a DST transition.

### 3.3. Parsing and Formatting Duration

~~~java
Duration timeout = Duration.parse("PT30S");
Duration retryDelay = Duration.parse("PT1M15S");
Duration workTime = Duration.parse("PT2H30M");

System.out.println(timeout);    // PT30S
System.out.println(retryDelay); // PT1M15S
System.out.println(workTime);   // PT2H30M
~~~

Duration uses ISO-8601 format with prefix `P` and time components after `T`; for example `PT1H` is one hour, `P2D` is two days (two 24-hour periods). Malformed strings throw `DateTimeParseException`.

### 3.4. Component Accessors and Conversion Limits

~~~java
Duration duration = Duration.ofHours(27).plusMinutes(12).plusSeconds(5);

System.out.println(duration.toDays());       // 1: number of full 24-hour days
System.out.println(duration.toHours());      // 27: total hours
System.out.println(duration.toMinutes());    // 1632: total minutes
System.out.println(duration.toSeconds());    // 97925: total seconds
System.out.println(duration.toMillis());     // 97925000
System.out.println(duration.toHoursPart());  // 3: remaining hours after days
System.out.println(duration.toMinutesPart());// 12
System.out.println(duration.toSecondsPart());// 5
~~~

Distinction:

- `toHours()` is the total number of full hours across the entire duration.
- `toHoursPart()` is only the remaining hours after extracting days.
- `toDays()` counts full 24-hour blocks, not calendar days.

Conversions to smaller units like `toMillis()` or `toNanos()` can truncate smaller units (e.g., nanoseconds when converting to milliseconds) and can throw `ArithmeticException` if the result cannot fit in a `long`.

Do not assume an extremely large Duration can always convert to nanoseconds:

~~~java
Duration huge = Duration.ofDays(1_000_000_000L);
// long nanos = huge.toNanos(); // can throw ArithmeticException due to overflow
~~~

When an API receives a duration from configuration, bound the valid range before converting to the unit required by a timeout or scheduler library.

## 4. How Does Duration Differ from Period?

### 4.1. Duration Is Elapsed Time; Period Is a Calendar Span

These two types are easy to confuse:

- `Duration`: measures time intervals in seconds and nanoseconds.
- `Period`: measures calendar spans in years, months, and days.

~~~java
import java.time.Duration;
import java.time.Period;

Duration twoDays = Duration.ofDays(2);
Period calendarTwoDays = Period.ofDays(2);
Period oneMonth = Period.ofMonths(1);
Period oneYear = Period.ofYears(1);
~~~

Examples:

| Requirement | Appropriate type |
|---|---|
| Request runs in 500 ms | `Duration` |
| Cache expires after 15 actual minutes | `Duration` |
| One day later on the local calendar | `Period.ofDays(1)` combined with date/time zone |
| Anniversary next year | `Period.ofYears(1)` or calendar date rule |
| Payment due after 30 calendar days | `Period.ofDays(30)` combined with business date |
| Task must run after exactly 24 hours | `Duration.ofHours(24)` |

### 4.2. A Calendar Day Is Not Always 24 Hours

In regions with DST, the local clock can jump forward or fall back. When transitioning to summer time, a day can have only 23 real hours; when returning to standard time, a day can have 25 real hours.

Example using a zone with DST:

~~~java
import java.time.Duration;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId zone = ZoneId.of("Europe/Paris");
LocalDate date = LocalDate.of(2026, 3, 29);

ZonedDateTime start = date.atStartOfDay(zone);
ZonedDateTime nextStart = date.plusDays(1).atStartOfDay(zone);

Duration elapsed = Duration.between(start, nextStart);

System.out.println(start);
System.out.println(nextStart);
System.out.println(elapsed.toHours()); // on a DST spring-forward day this can be 23 hours
~~~

The exact result depends on the JDK's time-zone rules database at runtime, but under Paris's DST rules on the transition to summer time, the span between the two starts of day is 23 hours.

If replaced with:

~~~java
ZonedDateTime nextBy24Hours = start.plus(Duration.ofHours(24));
~~~

this is the instant after **24 real hours**, which may not coincide with the start of the next calendar day.

### 4.3. Duration.between on LocalDateTime Has Semantic Limits

`LocalDateTime` contains no zone or offset. Therefore:

~~~java
LocalDateTime localStart =
        LocalDateTime.of(2026, 3, 28, 12, 0);
LocalDateTime localEnd =
        LocalDateTime.of(2026, 3, 29, 12, 0);

Duration wallClockDifference =
        Duration.between(localStart, localEnd);
~~~

The result is 24 hours on an **unzoned local date-time axis**. It cannot know whether DST occurred between those two points in a specific region.

If you want to compute actual elapsed time between two points in a region:

~~~java
ZoneId zone = ZoneId.of("Europe/Paris");

ZonedDateTime zonedStart = localStart.atZone(zone);
ZonedDateTime zonedEnd = localEnd.atZone(zone);

Duration actualElapsed = Duration.between(zonedStart, zonedEnd);
~~~

With two `ZonedDateTime` instances, the Duration calculation reflects the distance between the two points on the timeline. This is a core distinction when computing SLAs, runtimes, or actual elapsed durations.

### 4.4. Do Not Use Duration for Calendar Months or Years

`Duration.ofDays(30)` does not mean "one month." A month can have 28, 29, 30, or 31 days. A year can have 365 or 366 days.

If business rules state "renew one month from the registration date," you usually need to operate on zoned dates/instants using `Period.ofMonths(1)`, then define the rule for end-of-month dates:

~~~java
import java.time.LocalDate;
import java.time.Period;

LocalDate registered = LocalDate.of(2026, 1, 31);
LocalDate nextMonth = registered.plus(Period.ofMonths(1));

System.out.println(nextMonth); // 2026-02-28
~~~

Java adjusts non-existent dates to the last valid day of the target month in this addition. This rule is often helpful, though you still need to confirm whether it matches the product's renewal policy.

## 5. Handling Time Boundaries: Use Half-Open Intervals [start, end)

### 5.1. What Is a Half-Open Interval?

A half-open interval has:

- An **included** start bound (inclusive).
- An **excluded** end bound (exclusive).

Notation:

\[
[start, end)
\]

A point `t` belongs to the interval when:

\[
start \leq t < end
\]

In Java:

~~~java
static boolean contains(
        Instant startInclusive,
        Instant endExclusive,
        Instant value
) {
    return !value.isBefore(startInclusive)
            && value.isBefore(endExclusive);
}
~~~

Example:

~~~java
Instant start = Instant.parse("2026-11-15T10:00:00Z");
Instant end = Instant.parse("2026-11-15T11:00:00Z");

System.out.println(contains(start, end, start)); // true
System.out.println(contains(start, end, end));   // false
~~~

### 5.2. Why Avoid Making Both Ends Inclusive?

Suppose there are two adjacent intervals:

~~~text
Interval A: [10:00, 11:00)
Interval B: [11:00, 12:00)
                         ^
                         11:00 belongs to B, not A
~~~

There is no gap, and the 11:00 boundary is never double-counted. If both ends were inclusive, an event at exactly 11:00 could belong to both A and B. If both ends were exclusive, the boundary point would belong to neither interval.

Half-open intervals help:

- Chain consecutive intervals seamlessly.
- Avoid double-counting events occurring right at day or shift transitions.
- Express database queries cleanly.
- Avoid assuming timestamp precision is milliseconds or nanoseconds.

### 5.3. Validating Intervals

A range can be modeled using a record:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

record InstantRange(Instant startInclusive, Instant endExclusive) {
    InstantRange {
        Objects.requireNonNull(startInclusive, "startInclusive");
        Objects.requireNonNull(endExclusive, "endExclusive");

        if (!startInclusive.isBefore(endExclusive)) {
            throw new IllegalArgumentException(
                    "start must be before end"
            );
        }
    }

    boolean contains(Instant value) {
        return value != null
                && !value.isBefore(startInclusive)
                && value.isBefore(endExclusive);
    }

    Duration duration() {
        return Duration.between(startInclusive, endExclusive);
    }

    boolean overlaps(InstantRange other) {
        Objects.requireNonNull(other, "other");
        return startInclusive.isBefore(other.endExclusive)
                && other.startInclusive.isBefore(endExclusive);
    }
}
~~~

Overlap condition for two half-open intervals:

\[
A_{start} < B_{end} \quad \text{and} \quad B_{start} < A_{end}
\]

If A ends right when B begins, the two intervals **do not overlap**. This is usually the desired behavior for work schedules or contiguous time buckets.

## 6. Determining Start and End of a Day by Time Zone

### 6.1. Do Not Use 00:00 to 23:59:59.999

An error-prone approach:

~~~java
// Do not use this precision-assuming approach:
LocalDateTime start = date.atStartOfDay();
LocalDateTime end = date.atTime(23, 59, 59, 999_000_000);
~~~

This solution assumes millisecond precision. However, timestamps can contain nanoseconds, databases can store microseconds or milliseconds, and different systems have different precisions. An event at `23:59:59.999500` would be missed if the upper bound were `23:59:59.999000`.

Use the start of the next day as the **exclusive** end boundary.

### 6.2. Range of a Single Local Day

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;

static InstantRange rangeOfDate(LocalDate date, ZoneId zone) {
    ZonedDateTime start = date.atStartOfDay(zone);
    ZonedDateTime end = date.plusDays(1).atStartOfDay(zone);

    return new InstantRange(
            start.toInstant(),
            end.toInstant()
    );
}
~~~

Example for a date in Vietnam:

~~~java
LocalDate date = LocalDate.of(2026, 11, 15);
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

InstantRange range = rangeOfDate(date, vietnam);

System.out.println(range.startInclusive());
System.out.println(range.endExclusive());
System.out.println(range.duration());
~~~

In a zone without DST transitions like `Asia/Ho_Chi_Minh`, a normal local day is 24 hours long. In a zone with DST, the range's `Duration` can be 23 or 25 hours. The algorithm does not need to hardcode those cases because `atStartOfDay(zone)` and `ZoneId` data determine the boundaries according to region rules.

### 6.3. Multi-Day Range with an Inclusive End Date

User interfaces often accept "from date A to date B," meaning both A and B are included. When converting to a half-open timestamp range:

~~~java
static InstantRange rangeOfInclusiveDates(
        LocalDate fromDate,
        LocalDate toDate,
        ZoneId zone
) {
    if (toDate.isBefore(fromDate)) {
        throw new IllegalArgumentException("End date is before start date");
    }

    Instant start = fromDate.atStartOfDay(zone).toInstant();
    Instant endExclusive = toDate.plusDays(1)
            .atStartOfDay(zone)
            .toInstant();

    return new InstantRange(start, endExclusive);
}
~~~

Example:

~~~java
InstantRange november = rangeOfInclusiveDates(
        LocalDate.of(2026, 11, 1),
        LocalDate.of(2026, 11, 30),
        ZoneId.of("Asia/Ho_Chi_Minh")
);
~~~

This range includes all of November 1 through November 30 in the chosen region's calendar. There is no need to construct "23:59:59.999999999" on the last day.

In applications that handle `LocalDate` maximum values, `toDate.plusDays(1)` can overflow the range and throw `DateTimeException`. If the domain can accept maximum boundary dates, define an explicit bounding policy.

### 6.4. Why Must ZoneId Be Passed from Business Logic?

"Today" is not a global concept. The same Instant can be:

- November 15 in Vietnam time.
- November 14 in a region to the west.
- Another date depending on location and time of day.

If reporting revenue by Vietnam business date, use `Asia/Ho_Chi_Minh`; if reporting by customer region, use the zone determined by the profile or product policy.

Do not use `ZoneId.systemDefault()` for all business logic just because it is convenient. A server may run in UTC, a container may configure a different zone, and a request may belong to a different region from the server.

## 7. DST, Missing Hours, and Repeated Hours

### 7.1. DST Can Prevent Local Time from Mapping One-to-One to Instant

In regions with daylight saving time:

- When clocks jump forward, a span of local time may **not exist**.
- When clocks fall back, a span of local time may **occur twice**.

Therefore, `LocalDateTime` does not always identify a unique point in time. You need a `ZoneId` and possibly a gap/overlap handling policy.

### 7.2. Using `atZone` with Automatic Resolution Rules

~~~java
ZoneId zone = ZoneId.of("Europe/Paris");
LocalDateTime local = LocalDateTime.of(2026, 10, 25, 2, 30);

ZonedDateTime zoned = local.atZone(zone);
System.out.println(zoned);
~~~

When local time falls in a DST overlap (a time occurring twice), `atZone` defaults to the earlier offset per API rules. You can request the later offset:

~~~java
ZonedDateTime laterOccurrence = zoned.withLaterOffsetAtOverlap();
~~~

When local time falls in a DST gap (a non-existent time), `atZone` adjusts to the valid time after the gap. This is convenient behavior, though not always right for business rules.

### 7.3. Explicitly Checking Gap/Overlap via ZoneRules

If the application needs to prompt the user to choose one of the two overlapping times, or reject a non-existent time, you can check:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.zone.ZoneRules;
import java.util.List;

ZoneId zone = ZoneId.of("Europe/Paris");
LocalDateTime local = LocalDateTime.of(2026, 10, 25, 2, 30);
ZoneRules rules = zone.getRules();

List<java.time.ZoneOffset> offsets = rules.getValidOffsets(local);

if (offsets.isEmpty()) {
    System.out.println("Local time falls in a DST gap and does not exist");
} else if (offsets.size() == 1) {
    System.out.println("Single valid instant: " + offsets.get(0));
} else {
    System.out.println("Local time is repeated; offset selection needed: " + offsets);
}
~~~

Rules:

- No valid offsets: local time falls in a gap.
- One valid offset: local time maps to one instant.
- Two valid offsets: local time falls in an overlap; two instants are possible.

In scheduling, flight booking, finance, or local-time deadline systems, define an explicit gap/overlap policy rather than letting `atZone`'s defaults decide on behalf of the user.

## 8. Calculating Duration from Different Time Types

### 8.1. Instant to Instant

This is the clearest case for measuring actual elapsed time:

~~~java
Duration elapsed = Duration.between(
        Instant.parse("2026-11-15T09:00:00Z"),
        Instant.parse("2026-11-15T09:45:30Z")
);
~~~

Both points are already on the same timeline; no zone is needed to compute the distance.

### 8.2. ZonedDateTime to ZonedDateTime

~~~java
ZonedDateTime start = ZonedDateTime.parse(
        "2026-03-28T12:00:00+01:00[Europe/Paris]"
);
ZonedDateTime end = ZonedDateTime.parse(
        "2026-03-29T12:00:00+02:00[Europe/Paris]"
);

Duration elapsed = Duration.between(start, end);
System.out.println(elapsed.toHours()); // 23
~~~

The two local times are one calendar day apart, yet the offset changed from +01:00 to +02:00, so the actual elapsed duration is 23 hours.

### 8.3. OffsetDateTime to OffsetDateTime

`OffsetDateTime` has a specific UTC offset, so it can identify an instant:

~~~java
OffsetDateTime a = OffsetDateTime.parse("2026-11-15T09:00:00+07:00");
OffsetDateTime b = OffsetDateTime.parse("2026-11-15T04:00:00Z");

Duration difference = Duration.between(a, b);
System.out.println(difference); // PT0S
~~~

Two representations with different offsets represent the same instant. If business logic needs a region time zone with historical/DST rules, `OffsetDateTime` does not fully replace `ZonedDateTime`.

### 8.4. LocalDateTime to LocalDateTime

~~~java
LocalDateTime a = LocalDateTime.of(2026, 11, 15, 9, 0);
LocalDateTime b = LocalDateTime.of(2026, 11, 15, 10, 30);

Duration difference = Duration.between(a, b);
System.out.println(difference); // PT1H30M
~~~

The result is the difference between two local values on an unzoned date-time axis. If this represents actual elapsed time of a process in a region with DST, attach a zone/offset first.

### 8.5. LocalDate Cannot Be Used Directly with Duration

~~~java
LocalDate first = LocalDate.of(2026, 11, 1);
LocalDate second = LocalDate.of(2026, 11, 15);

// Duration.between(first, second) is not applicable:
// LocalDate lacks seconds to construct a Duration.

long days = java.time.temporal.ChronoUnit.DAYS.between(first, second);
Period period = Period.between(first, second);
~~~

For two calendar dates, use `Period` or `ChronoUnit.DAYS.between`. Do not force `LocalDate` into a `Duration` without knowing the time zone and start of day.

## 9. Clock: Controlling the Time Source and Writing Testable Code

### 9.1. Why Avoid Scattered Calls to `Instant.now()`?

Business code frequently needs the "current point in time":

~~~java
Instant createdAt = Instant.now();
Instant expiresAt = Instant.now().plus(Duration.ofHours(1));
~~~

Two calls can return slightly different points. Worse, tests depending on real time can be irreproducible. Java provides `Clock` to abstract the time source:

~~~java
Clock clock = Clock.systemUTC();
Instant now = Instant.now(clock);
~~~

Commonly used factories:

| Factory | Meaning |
|---|---|
| `Clock.systemUTC()` | System clock with UTC zone |
| `Clock.system(zone)` | System clock with the specified zone |
| `Clock.fixed(instant, zone)` | Clock always returning the same instant, very useful in tests |
| `Clock.offset(baseClock, duration)` | Clock whose time is shifted relative to the base clock |
| `Clock.tick(baseClock, duration)` | Clock rounded/ticked to the chosen interval |

### 9.2. Injecting Clock into Services

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

class ExpirationService {
    private final Clock clock;

    ExpirationService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    Instant createExpiration() {
        return Instant.now(clock).plus(Duration.ofHours(1));
    }
}
~~~

Production:

~~~java
ExpirationService service =
        new ExpirationService(Clock.systemUTC());
~~~

Test:

~~~java
Instant fixedNow = Instant.parse("2026-11-15T10:00:00Z");
Clock fixedClock = Clock.fixed(fixedNow, ZoneOffset.UTC);

ExpirationService service = new ExpirationService(fixedClock);

System.out.println(service.createExpiration());
// 2026-11-15T11:00:00Z
~~~

Tests do not have to wait for the real clock and do not depend on when they run. You can create `Clock.offset(fixedClock, Duration.ofMinutes(10))` to simulate time advancing or rewinding per scenario.

### 9.3. Clock Is Wall-Clock, Not a Monotonic Timer

`Clock.systemUTC()` reads calendar time from the system. The OS clock can be synchronized or adjusted, so two reads may not accurately reflect monotonically elapsed time.

This leads to two distinct needs:

- **Recording timestamps:** use `Instant`/`Clock`.
- **Measuring execution time, timeouts, latency:** use `System.nanoTime()` to measure elapsed time.

Do not subtract two `Instant.now()` calls as a precision timer for benchmarks or short timeouts if a monotonic clock is required.

## 10. Measuring Execution Time with System.nanoTime()

### 10.1. nanoTime Measures Intervals, Not Timestamps

`System.nanoTime()` returns a value from a monotonic time source with nanosecond resolution for measuring duration. The raw value can be negative, is arbitrary, and is not an epoch timestamp.

~~~java
long start = System.nanoTime();

doWork();

long elapsedNanos = System.nanoTime() - start;
Duration elapsed = Duration.ofNanos(elapsedNanos);

System.out.println("Elapsed: " + elapsed.toMillis() + " ms");
~~~

Points to remember:

- Only care about **the difference between two calls**.
- Do not convert `nanoTime()` into a date-time or store it as a timestamp.
- Subtraction `end - start` is the right pattern for computing elapsed time, even when the counter wraps around, as long as the measured duration is less than the relevant signed range.
- API resolution does not equal physical measurement accuracy.

### 10.2. Creating a Timeout Deadline

One way to check a timeout:

~~~java
import java.time.Duration;

static void runWithBudget(Duration budget) {
    if (budget == null || budget.isNegative() || budget.isZero()) {
        throw new IllegalArgumentException("Budget must be positive");
    }

    final long budgetNanos;
    try {
        budgetNanos = budget.toNanos();
    } catch (ArithmeticException ex) {
        throw new IllegalArgumentException(
                "Budget exceeds nanoTime measurement range",
                ex
        );
    }

    long started = System.nanoTime();

    while (true) {
        doOneUnitOfWork();

        long elapsed = System.nanoTime() - started;
        if (elapsed >= budgetNanos) {
            throw new RuntimeException("Processing timed out");
        }
    }
}
~~~

This illustrates budget measurement, not a complete timeout framework. In real applications, you also need work cancellation mechanisms, interruption, cleanup, and distinguishing timeouts from business errors.

If the Duration is too large, `toNanos()` can overflow; bound it or use a different comparison approach. Do not directly compare two absolute `nanoTime()` values like `System.nanoTime() >= deadline` because the counter can wrap and the origin is meaningless.

### 10.3. Why Should Timeouts Rely on a Monotonic Clock?

Suppose an application computes:

~~~java
Instant deadline = Instant.now().plusSeconds(10);
~~~

and repeatedly compares `Instant.now()` against the deadline. If the system clock is adjusted backward, the timeout can stretch longer than expected; if adjusted forward, the timeout can expire prematurely.

For internal timeouts within a process, measuring elapsed time with `System.nanoTime()` is more resilient to wall-clock changes. For deadlines sent between systems or stored in a database, using an `Instant` is necessary, then converting to a monotonic budget when waiting begins.

## 11. Handling Time Boundaries in Databases

### 11.1. Querying by Date: Use Inclusive Start and Next-Day Exclusive

Suppose an `orders` table has a timestamp column representing order creation time. A user selects November 15, 2026 in the Vietnam time zone.

Compute boundaries:

~~~java
LocalDate date = LocalDate.of(2026, 11, 15);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant from = date.atStartOfDay(zone).toInstant();
Instant until = date.plusDays(1).atStartOfDay(zone).toInstant();
~~~

SQL:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE created_at >= :fromInclusive
  AND created_at <  :untilExclusive
ORDER BY created_at;
~~~

This query includes every timestamp in the selected local date without guessing end-of-day precision.

### 11.2. Why Avoid BETWEEN with Both Ends Inclusive?

SQL `BETWEEN a AND b` typically equals `>= a AND <= b`. If `:to` is set to the start of the next day, records at exactly 00:00 on the next day will be counted in the previous day.

~~~sql
-- Prone to error when :to is the start of the next day:
WHERE created_at BETWEEN :fromInclusive AND :nextDayStart
~~~

Write instead:

~~~sql
WHERE created_at >= :fromInclusive
  AND created_at < :nextDayStart
~~~

With two adjacent intervals, a point right at the start of the new day belongs only to the new day and is never counted twice.

### 11.3. Database Timestamp Precision

Java `Instant` has nanosecond resolution, but a database/driver may store with different precision, such as milliseconds or microseconds. If code constructs an end boundary like `23:59:59.999999999`, rounding or truncation in the database can create unpredictable behavior.

A half-open interval does not care whether timestamps are stored to milliseconds, microseconds, or nanoseconds. It only requires the two bounds to be computed consistently.

### 11.4. Choosing Storage Types Based on Data Semantics

- Events on the timeline: typically store UTC instants or a timestamp type with an explicit time-zone convention.
- Birthdays, accounting dates, holidays: store `LocalDate` or SQL DATE, without attaching UTC if meaningless.
- Daily opening hours: can store `LocalTime` paired with the location's `ZoneId`.
- Zoned appointments: store resolved instant and/or local date-time + zone/offset depending on schedule reconstruction needs.

Do not store `LocalDateTime` and assume it is UTC unless the schema specifies so. When reading legacy data, identify the historical time zone before converting to `Instant`.

## 12. Timestamps, Zones, and User Data

### 12.1. Parsing a Timestamp with an Offset

~~~java
OffsetDateTime input =
        OffsetDateTime.parse("2026-11-15T21:00:00+07:00");

Instant instant = input.toInstant();
~~~

The `+07:00` offset identifies the corresponding point on the timeline. If the input string has no offset:

~~~text
2026-11-15T21:00:00
~~~

then it is only a `LocalDateTime`, and does not yet identify an instant. You need to know the zone or offset from the API contract.

### 12.2. ZoneId and ZoneOffset Are Not the Same

- `ZoneOffset` is a fixed offset from UTC, such as `+07:00`.
- `ZoneId` can be a region name such as `Asia/Ho_Chi_Minh`, with historical and DST rules if applicable.

Geographical regions can change rules by legal decree. Use `ZoneId` when business logic refers to local time in a region, and use `ZoneOffset` when the contract only provides a specific offset.

### 12.3. Displaying an Instant in a Region

~~~java
Instant instant = Instant.parse("2026-11-15T14:00:00Z");

ZonedDateTime vietnamTime = instant.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);
ZonedDateTime parisTime = instant.atZone(
        ZoneId.of("Europe/Paris")
);

System.out.println(vietnamTime);
System.out.println(parisTime);
~~~

Both results represent **the same instant**, yet the calendar times differ. This is why you should store global timestamps and only convert to a zone in the appropriate presentation or business layer.

## 13. Common Boundary Problems

### 13.1. Checking Whether a Deadline Has Passed

~~~java
static boolean isExpired(Instant expiresAt, Clock clock) {
    return !Instant.now(clock).isBefore(expiresAt);
}
~~~

In this example, at exactly `expiresAt`, the result is already expired. If business logic defines the boundary point as still valid, the condition differs; state inclusive/exclusive clearly.

### 13.2. Computing Remaining Time

~~~java
static Duration remaining(Instant deadline, Clock clock) {
    return Duration.between(Instant.now(clock), deadline);
}
~~~

A negative Duration means the deadline has passed. Do not automatically clamp to zero if the caller needs to distinguish "overdue" from "0 seconds left."

### 13.3. Checking Whether Two Schedule Intervals Overlap

For two half-open intervals `[aStart, aEnd)` and `[bStart, bEnd)`:

~~~java
static boolean overlaps(
        Instant aStart,
        Instant aEnd,
        Instant bStart,
        Instant bEnd
) {
    return aStart.isBefore(bEnd) && bStart.isBefore(aEnd);
}
~~~

Before calling, ensure each range is valid (`start < end`). If an interval can be empty or reversed, decide whether to reject it or treat it as non-overlapping.

### 13.4. Computing Time from Start Until Now

~~~java
Instant startedAt = Instant.now(clock);
// ... perform work ...
Instant finishedAt = Instant.now(clock);

Duration elapsed = Duration.between(startedAt, finishedAt);
~~~

This works when both points need to be stored or displayed. If the goal is measuring internal latency with a monotonic clock, prefer `System.nanoTime()`.

### 13.5. Adding One Calendar Day to an Appointment

~~~java
ZonedDateTime appointment =
        ZonedDateTime.of(
                2026, 3, 28, 9, 0, 0, 0,
                ZoneId.of("Europe/Paris")
        );

ZonedDateTime tomorrowSameLocalTime =
        appointment.plus(Period.ofDays(1));

ZonedDateTime after24Hours =
        appointment.plus(Duration.ofHours(24));
~~~

`tomorrowSameLocalTime` targets the same local clock time on the next day, applying zone rules. `after24Hours` is exactly 24 hours later on the timeline. The two results can differ when crossing DST.

## 14. Complete Example: Local-Date Reporting and Processing Duration Measurement

Save the following code as **TimeBoundaryDemo.java**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.List;
import java.util.Objects;

public class TimeBoundaryDemo {

    record InstantRange(Instant startInclusive, Instant endExclusive) {
        InstantRange {
            Objects.requireNonNull(startInclusive);
            Objects.requireNonNull(endExclusive);
            if (!startInclusive.isBefore(endExclusive)) {
                throw new IllegalArgumentException("Invalid range");
            }
        }

        boolean contains(Instant value) {
            return !value.isBefore(startInclusive)
                    && value.isBefore(endExclusive);
        }

        Duration duration() {
            return Duration.between(startInclusive, endExclusive);
        }
    }

    record OrderEvent(String id, Instant createdAt) {
    }

    static InstantRange forLocalDate(LocalDate date, ZoneId zone) {
        ZonedDateTime start = date.atStartOfDay(zone);
        ZonedDateTime end = date.plusDays(1).atStartOfDay(zone);
        return new InstantRange(start.toInstant(), end.toInstant());
    }

    static long countOrders(List<OrderEvent> events, InstantRange range) {
        return events.stream()
                .filter(event -> range.contains(event.createdAt()))
                .count();
    }

    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-15T14:00:00Z"),
                ZoneId.of("UTC")
        );
        ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
        LocalDate businessDate = LocalDate.now(clock.withZone(businessZone));

        InstantRange range = forLocalDate(businessDate, businessZone);

        List<OrderEvent> events = List.of(
                new OrderEvent("A", range.startInclusive()),
                new OrderEvent("B", range.startInclusive().plusSeconds(60)),
                new OrderEvent("C", range.endExclusive().minusNanos(1)),
                new OrderEvent("D", range.endExclusive())
        );

        System.out.println("Business date: " + businessDate);
        System.out.println("Start: " + range.startInclusive());
        System.out.println("End exclusive: " + range.endExclusive());
        System.out.println("Elapsed hours: " + range.duration().toHours());
        System.out.println("Orders in day: " + countOrders(events, range));

        long started = System.nanoTime();
        long count = countOrders(events, range);
        Duration processing = Duration.ofNanos(
                System.nanoTime() - started
        );

        System.out.println("Count: " + count);
        System.out.println("Processing nanos: " + processing.toNanos());
    }
}
~~~

Compile and run with JDK 17:

~~~shell
javac --release 17 TimeBoundaryDemo.java
java TimeBoundaryDemo
~~~

In the output you can observe:

- `A` is right at the start of the day and is counted.
- `B` is inside the range and is counted.
- `C` is immediately before the start of the next day and is counted.
- `D` equals `endExclusive`, so it is not counted in the day under consideration.
- `Clock.fixed` makes the business date in the example completely reproducible when running tests.
- `System.nanoTime()` is used to measure the processing block, not to obtain business timestamps.

## 15. Common Mistakes

| Mistake | Why it is wrong | How to handle |
|---|---|---|
| Using `Duration.ofDays(1)` to find the start of the next day | A calendar day may not be 24 hours long | Use `LocalDate.plusDays(1).atStartOfDay(zone)` |
| Using `23:59:59.999` as end of day | Assumes millisecond precision | Use the interval `[start, nextDayStart)` |
| Using `BETWEEN` with both ends inclusive | Can count records at the start of the next day twice | Use `>= start AND < end` |
| Computing Duration from two `LocalDateTime` values when actual elapsed time is needed | Both values lack zone/DST | Attach `ZoneId` or use `Instant` |
| Using Duration for months/years | Months and years have varying calendar lengths | Use `Period` with appropriate date/zone |
| Using `LocalDateTime` as a UTC timestamp | Lacks offset/zone to identify an instant | Parse an offset or apply a zone per contract |
| Using `ZoneId.systemDefault()` for all logic | Results depend on server configuration | Pass an explicit business zone |
| Using `Instant.now()` to measure short timeouts | Wall clock can be adjusted | Use `System.nanoTime()` |
| Comparing absolute `nanoTime()` values against a deadline | Origin has no timestamp meaning and can wrap | Compare difference `now - start` against budget |
| Calling `Duration.toNanos()` on arbitrary values | Can overflow `long` | Validate range or keep Duration |
| Ignoring negative Duration | Can hide out-of-order arguments or missed deadlines | Define an explicit policy for negative values |
| Assuming every LocalDateTime has one offset | DST gap/overlap breaks this assumption | Use `ZoneRules.getValidOffsets` when an explicit decision is needed |
| Assuming Instant always has real-world nanosecond accuracy | Clocks/OS have lower precision | Distinguish API resolution from source precision |

## 16. Practice Exercises

### Exercise 1 — Calculating Request Duration

Given:

~~~java
Instant start = Instant.parse("2026-11-15T08:00:00Z");
Instant end = Instant.parse("2026-11-15T08:00:02.345Z");
~~~

Compute the Duration, print seconds, milliseconds, and the nano part. Try swapping the two points and explain why the Duration is negative.

### Exercise 2 — Distinguishing Duration and Period

Given the date 2026-01-31, compute:

- After 30 days using Duration.
- After one month using Period.

Explain why the two results do not necessarily match.

### Exercise 3 — Creating a Single-Day Range

Write a method accepting `LocalDate` and `ZoneId`, returning an `InstantRange` over `[start, end)`. Test these points:

- Exact start of day.
- One nanosecond before the end of the range.
- Exact start of the next day.

Determine which points are included.

### Exercise 4 — DST Gap and Overlap

Use `Europe/Paris` and DST transition dates in a year matching your JDK's time-zone data. Compare:

- `date.atStartOfDay(zone)` to the start of the next day.
- Adding `Duration.ofHours(24)`.
- Adding `Period.ofDays(1)`.

Inspect a LocalDateTime in a gap and a LocalDateTime in an overlap using `ZoneRules.getValidOffsets`.

### Exercise 5 — Testing with Clock.fixed

Write a service that computes a deadline 30 minutes from now. Inject `Clock`, then use `Clock.fixed` in tests to verify exact results without depending on the real run time.

### Exercise 6 — Timeout with nanoTime

Write a method that times a piece of work using `System.nanoTime()`, returning a Duration. Do not convert absolute nanoTime values into an Instant. Try enforcing a timeout limit and handling overly large Durations when converting to nanos.

### Exercise 7 — Querying by Date

Suppose a user selects 2026-11-15 in the `Asia/Ho_Chi_Minh` zone. Compute the two Instant boundaries and write an SQL query using `created_at >= :start` and `created_at < :end`. Explain why there is no need to build `23:59:59.999999999`.

### Exercise 8 — Checking Overlap

Write a function checking whether two `InstantRange` intervals overlap. Test two adjacent intervals and two intersecting intervals. Explain the formula `aStart < bEnd && bStart < aEnd`.

## 17. Self-Check Questions

1. What is the difference between `Instant`, `Duration`, `Period`, and `LocalDateTime`?
2. Can `Duration.between(start, end)` return a negative value?
3. Exactly how many seconds does `Duration.ofDays(1)` mean?
4. Why does Duration not accurately represent a calendar month?
5. How does `toDays()` differ from `toDaysPart()`?
6. When can `Duration.toNanos()` throw `ArithmeticException`?
7. What benefit does a half-open interval `[start, end)` provide at boundaries?
8. Why should database queries by date use the start of the next day as the exclusive end?
9. Why is `LocalDateTime` insufficient for computing actual elapsed time across DST?
10. What does `atStartOfDay(ZoneId)` help handle?
11. How do DST gap and overlap differ?
12. When should you use `ZoneId` instead of `ZoneOffset`?
13. How does `Clock.fixed` support testing?
14. Why is `Instant.now()` not a monotonic timer?
15. Why should `System.nanoTime()` only be used via the difference between two calls?
16. When should you use Duration and when should you use Period for business deadlines?

## 18. References

- [Java SE 17 API — Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): creating, computing, comparing, and converting durations.
- [Java SE 17 API — Period](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Period.html): calendar-based amounts of time.
- [Java SE 17 API — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): points in time on the timeline.
- [Java SE 17 API — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): replaceable time sources for testing.
- [Java SE 17 API — ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html): zoned date-time and handling gaps/overlaps.
- [Java SE 17 API — ZoneRules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html): valid offset rules and local-time transitions.
- [Java SE 17 API — System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): measuring duration with a monotonic time source.
- [dev.java — Date Time](https://dev.java/learn/date-time/): Java Time API learning guide.

When calculating elapsed time, use `Duration` across two clearly defined instants. When handling calendar dates, determine the `ZoneId` and use the start of the next day in a half-open interval. When measuring timeouts or latency, use `System.nanoTime()`. These three choices separate points in time, calendar rules, and actual elapsed durations, helping Java 17 code handle date boundaries, DST, and timestamp precision correctly.
