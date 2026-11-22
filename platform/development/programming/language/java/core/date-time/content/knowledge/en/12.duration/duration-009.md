# Applying Duration for Deadlines, Latency, and Elapsed Time

In Java, **java.time.Duration** represents an amount of time in seconds and nanoseconds. It is well suited for expressing “a 3-second timeout”, “a token valid for 15 minutes”, “the latency between two points is 120 ms”, or “how long a task has been running”. However, those statements belong to related but not identical problems: a calendar deadline depends on an absolute point in time, whereas measuring latency requires a monotonically increasing time source.

To use Duration correctly, first determine whether you need **an amount of time**, **an end point in time**, or **a measurement of actual elapsed time**. Duration can be added to an Instant to create a deadline, or returned as the result of Duration.between; Duration itself is not a clock, does not count down on its own, and does not store a start time.

This article uses Java 17+ and focuses on creating Duration instances, calculating deadlines, checking expiration, measuring latency, timeouts, retries, testing with Clock, and common mistakes when confusing a wall-clock time source with an elapsed-time clock.

## 1. What Does Duration Represent?

**Duration** represents an amount of time in seconds and nanoseconds. For example:

~~~java
Duration fiveSeconds = Duration.ofSeconds(5);
Duration ninetyMillis = Duration.ofMillis(90);
Duration twentyMinutes = Duration.ofMinutes(20);
Duration oneAndHalfHours = Duration.ofHours(1).plusMinutes(30);
~~~

Duration does not hold a start date, time zone, or deadline. The value **Duration.ofMinutes(20)** is always a 20-minute amount of time; when added to an Instant, it produces a point in time 1,200 seconds later.

| Type | Meaning | Example |
|---|---|---|
| **Duration** | Amount of time measured in seconds/nanoseconds | 15 minutes |
| **Instant** | An absolute point on the timeline | 2026-10-24T10:00:00Z |
| **LocalDateTime** | Local calendar date and time, without a zone | 2026-10-24T17:00 |
| **Period** | Calendar-based amount of time in years/months/days | 1 calendar month |
| **System.nanoTime()** | Counter used to measure elapsed time within the same JVM | start and end tick values |

**Do not confuse Duration with Period.** “Wait exactly 24 hours” is a 24-hour Duration. “Tomorrow at the same local time” is a calendar operation that requires the appropriate LocalDateTime/ZonedDateTime. A calendar month does not have a fixed number of seconds; if business logic says “add one month”, you typically must use calendar rules and Period/plusMonths, which cannot be unconditionally replaced with a 30-day Duration.

## 2. Creating Duration with Factory Methods

Commonly used factory methods:

| Method | Meaning |
|---|---|
| **Duration.ofNanos(n)** | n nanoseconds |
| **Duration.ofMillis(n)** | n milliseconds |
| **Duration.ofSeconds(n)** | n seconds |
| **Duration.ofMinutes(n)** | n minutes |
| **Duration.ofHours(n)** | n hours |
| **Duration.ofDays(n)** | 24 hours per day under the Duration model |

Parts can be combined:

~~~java
Duration timeout = Duration.ofSeconds(2).plusMillis(500);
Duration retryDelay = Duration.ofMillis(250);
Duration ttl = Duration.ofMinutes(15);
Duration wait = Duration.ofHours(1).plusMinutes(30);
~~~

**Duration.ofDays(1)** means 86,400 seconds, not the concept of “the next calendar day in every zone”. When applied to an Instant, it adds an exact 24-hour length on the timeline. When applied to a ZonedDateTime across a Daylight Saving Time transition day, adding 24 hours can differ from adding one calendar day.

### Negative and Zero Values

Duration can also represent zero or negative values:

~~~java
Duration zero = Duration.ZERO;
Duration negative = Duration.ofSeconds(-5);
~~~

A negative Duration can be useful in difference calculations, but it is not a typical timeout policy. In an application's API, you should define whether timeout/TTL must be positive or whether 0 is allowed to mean disabled. Do not assume a negative Duration means “no deadline” unless the contract specifies it.

Some APIs allow a zero or negative duration with special semantics; the exact behavior depends on that API. For example, Thread.sleep does not accept negative values, whereas Duration itself can store negative values.

## 3. Duration Between Two Points in Time

There are two common approaches:

- **Duration.between(start, end)**: returns the amount of time between two measurable Temporals.
- **end.minus(start)**: with two Instants, you can use Instant.until or compute via Duration; Duration.between is usually more readable.

Example:

~~~java
Instant start = Instant.parse("2026-10-24T10:00:00Z");
Instant end = Instant.parse("2026-10-24T10:00:03.250Z");

Duration elapsed = Duration.between(start, end);
~~~

The result is **3 seconds and 250 milliseconds**. If end is before start, the resulting Duration is negative. The method does not automatically swap the two values or guarantee a non-negative elapsed time.

A Duration can be read using:

- **toDays()**: whole number of days under the 24-hour model, truncating any fractional part.
- **toHours()**, **toMinutes()**, **toSeconds()**: whole units.
- **toMillis()**, **toNanos()**: converts to an integer in smaller units; may throw ArithmeticException if the result overflows the long range.
- **toSecondsPart()**, **toMillisPart()**, **toNanosPart()**: extracts the corresponding remainder component.

If you need to display days/hours/minutes/seconds accurately, define how to format and handle negative signs; do not manually add up parts in a way that risks double-counting.

### Not Every Temporal Object Measures the Same Interval

Duration is generally suited for Instant or points in time with an unambiguous amount of time between them. LocalDateTime has no zone, so Duration.between on two LocalDateTime values only measures the gap between two local calendar/clock values. It cannot infer the actual elapsed time if a DST offset change occurs in a specific zone.

With **LocalTime**, the result between two values can be negative when the clock wraps past midnight, because LocalTime does not record a date. For example, Duration.between(23:30, 01:00) does not automatically assume that 01:00 is on the next day. Preserve the date with LocalDateTime or use Instant when you need actual elapsed time.

## 4. Choosing a Clock Based on the Question

One of the most important decisions is **which time source should be used**.

### Wall Clock: Instant.now(clock)

A wall clock returns an absolute timestamp, typically used for logging, generating timestamps, and determining a calendar-based deadline:

~~~java
Instant createdAt = Instant.now(clock);
Instant expiresAt = createdAt.plus(Duration.ofMinutes(15));
~~~

Here, Clock should be provided. Production typically uses Clock.systemUTC(); tests can use Clock.fixed to produce repeatable results.

The system clock can be synchronized or adjusted. Therefore, when measuring “how many milliseconds the code ran”, you should not assume subtracting two Instant.now() calls is the most accurate latency measurement. A wall clock can jump forward or backward.

### Monotonic Clock: System.nanoTime()

To measure the duration of an operation within the same JVM, use the monotonic counter:

~~~java
long started = System.nanoTime();
// Perform the operation to measure
long elapsedNanos = System.nanoTime() - started;
~~~

**System.nanoTime()** is not a calendar timestamp, cannot be directly converted to a UTC date-time, and its absolute value has no independent meaning. Only take the difference between readings within the same measurement. Subtraction is the standard way to measure elapsed time, and it avoids comparing ticks directly with relational operators that can go wrong when the counter wraps around after a very long period.

**Duration** can store a measurement taken from two monotonic readings: Duration.ofNanos(elapsedNanos). The measurement uses System.nanoTime(); Duration merely represents the resulting amount of time.

### Quick Selection Table

| Need | Appropriate Approach |
|---|---|
| When an order was created | Instant.now(clock) |
| Absolute expiration timestamp | expiresAt = createdAt.plus(ttl) |
| Execution time of a code block | System.nanoTime() and the difference between two readings |
| Request latency distribution | Measure nanoTime per request, record/log the latency |
| Tomorrow at 09:00 store local time | Calendar rules + LocalDate/LocalTime + ZoneId |
| Wait 2 seconds then retry | Duration/time unit of a scheduler or timer mechanism |
| Token valid until a stored Instant | Compare current Instant against expiresAt |

## 5. Deadline vs. Duration

**Duration** is an amount of time. **Deadline** is a specific end point in time.

For example, issuing a token at:

~~~text
issuedAt = 2026-10-24T10:00:00Z
ttl = 15 minutes
expiresAt = 2026-10-24T10:15:00Z
~~~

Computing the deadline from the issue time:

~~~java
Instant issuedAt = Instant.parse("2026-10-24T10:00:00Z");
Duration ttl = Duration.ofMinutes(15);
Instant expiresAt = issuedAt.plus(ttl);
~~~

When checking validity, you must define the boundary clearly. A common convention is the half-open interval **[issuedAt, expiresAt)**: valid at issuedAt, but no longer valid when now equals expiresAt.

~~~java
boolean expired = !now.isBefore(expiresAt);
boolean stillValid = now.isBefore(expiresAt);
~~~

Under that rule, **now >= expiresAt** means expired. If you only write now.isAfter(expiresAt), the exact moment of the deadline is treated as not yet expired. This is a common boundary bug.

If multiple comparisons in the same decision must rely on a consistent moment, read Instant.now(clock) **once** and reuse it. Do not call now multiple times and accidentally cross the deadline in the middle of a processing branch.

## 6. Runnable Example: Testable Deadlines

Create the file **DeadlineDurationDemo.java**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;

public class DeadlineDurationDemo {
    private final Clock clock;

    public DeadlineDurationDemo(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public Instant createDeadline(Duration ttl) {
        if (ttl == null || ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException(
                    "ttl must be positive"
            );
        }
        return Instant.now(clock).plus(ttl);
    }

    public boolean isExpired(Instant deadline) {
        Instant now = Instant.now(clock);
        return !now.isBefore(deadline);
    }

    public static void main(String[] args) {
        Clock base = Clock.fixed(
                Instant.parse("2026-10-24T10:00:00Z"),
                ZoneOffset.UTC
        );

        DeadlineDurationDemo atIssue =
                new DeadlineDurationDemo(base);
        Instant deadline =
                atIssue.createDeadline(Duration.ofMinutes(15));

        Clock justBefore = Clock.offset(
                base, Duration.ofMinutes(14).plusSeconds(59)
        );
        Clock atBoundary = Clock.offset(
                base, Duration.ofMinutes(15)
        );

        System.out.println("deadline=" + deadline);
        System.out.println("expiredAtIssue=" +
                atIssue.isExpired(deadline));
        System.out.println("expiredBefore=" +
                new DeadlineDurationDemo(justBefore).isExpired(deadline));
        System.out.println("expiredAtBoundary=" +
                new DeadlineDurationDemo(atBoundary).isExpired(deadline));
    }
}
~~~

Compile and run:

~~~bash
javac DeadlineDurationDemo.java
java DeadlineDurationDemo
~~~

Exact stdout:

~~~text
deadline=2026-10-24T10:15:00Z
expiredAtIssue=false
expiredBefore=false
expiredAtBoundary=true
~~~

**Why are Clock.fixed and Clock.offset useful?** They provide a deterministic time source, making it easy to test before, at, and after the deadline without calling Thread.sleep. Clock.offset shifts the view of time relative to a base clock; it does not change the operating system clock.

Production can pass Clock.systemUTC(); tests can pass Clock.fixed or Clock.offset. This is an example of dependency injection: the service depends on Clock instead of hardcoding the real “now”.

## 7. Measuring Latency Properly with System.nanoTime()

Simple example:

~~~java
long started = System.nanoTime();

String normalized = input.trim().toLowerCase();

long elapsedNanos = System.nanoTime() - started;
Duration elapsed = Duration.ofNanos(elapsedNanos);
~~~

This snippet is only illustrative; for very short operations, JVM overhead, JIT, GC, the scheduler, and the measurement itself can affect the result. Do not treat a single measurement as a reliable benchmark; when comparing performance, use a proper benchmarking approach with enough iterations and a controlled environment.

With a monotonic counter, only **the difference between two readings** is meaningful. Do not print or store the absolute value of nanoTime as a timestamp. If you need to audit “when did it start”, record an Instant separately; if you need “how long did it run”, measure with nanoTime.

### Java 17+ Example with Deterministic Output

To illustrate unit conversions without depending on machine speed, the following program uses a known interval. It is not a benchmark:

~~~java
import java.time.Duration;

public class DurationPartsDemo {
    public static void main(String[] args) {
        Duration elapsed = Duration.ofMillis(2345);

        System.out.println("millis=" + elapsed.toMillis());
        System.out.println("seconds=" + elapsed.toSeconds());
        System.out.println("secondsPart=" + elapsed.toSecondsPart());
        System.out.println("millisPart=" + elapsed.toMillisPart());
        System.out.println("toString=" + elapsed);
    }
}
~~~

Compile and run:

~~~bash
javac DurationPartsDemo.java
java DurationPartsDemo
~~~

Stdout:

~~~text
millis=2345
seconds=2
secondsPart=2
millisPart=345
toString=PT2.345S
~~~

For a positive Duration of 2.345 seconds, toSeconds returns the whole number of seconds, 2; toMillis still preserves the total milliseconds, 2345. Do not confuse total units with remainder parts.

## 8. Timeouts, Sleep, and Retries

Duration describes the length of a timeout/delay, but **how waiting and cancellation work is determined by the executing API**.

- For APIs that accept Duration, pass the unit explicitly: Duration.ofSeconds(2), Duration.ofMillis(250).
- If an API only accepts a long, read carefully whether the parameter is in milliseconds, nanoseconds, or another unit.
- Thread.sleep(long) takes milliseconds; Thread.sleep(millis, nanos) takes two separate parameters. Do not pass a Duration directly to a method that does not support it.
- With ScheduledExecutorService, the schedule unit can be specified via TimeUnit; Duration.toNanos can overflow for very large intervals, so choose an appropriate conversion and bounds.
- For HTTP/client/database timeouts, prefer passing them into the library's official configuration rather than only checking a Duration externally and assuming the inner operation will stop on its own.

A 250 ms delay means “do not run earlier than / scheduled after the delay according to the API”, not a guarantee of exact execution at that instant. CPU load, thread scheduling, and GC can cause a callback to run late.

### Overall Deadline and Per-Attempt Timeout

Suppose you retry up to 3 times, with each request having a 2-second timeout. If each attempt starts a fresh timeout without checking an overall deadline, the entire request can run longer than expected (plus delays and processing time). For an overall deadline, compute the expiration timestamp or remaining time budget after each step:

~~~java
Duration remaining = Duration.between(Instant.now(clock), deadline);
if (remaining.isZero() || remaining.isNegative()) {
    // Time budget exhausted
}
~~~

This is an example of a wall-clock deadline. In systems where timeouts must reliably remain unaffected by wall-clock adjustments while a request is in flight, use a monotonic clock or the appropriate library's deadline mechanism. Also be mindful of distributed systems: an Instant deadline can be sent over the network, but clock skew between sender and receiver must be accounted for.

## 9. Duration Between Local Date-Times and DST

Duration is always an amount of time in seconds/nanoseconds. However, adding a Duration to a local date-time type can differ from adding a calendar day.

Example with ZonedDateTime in a DST zone:

~~~java
ZonedDateTime start = ZonedDateTime.of(
        2026, 3, 7, 12, 0, 0, 0,
        ZoneId.of("America/New_York")
);
ZonedDateTime after24Hours = start.plus(Duration.ofHours(24));
ZonedDateTime nextCalendarDay = start.plusDays(1);
~~~

Under New York's DST rules in 2026, the two values can have different local times because the spring-forward day only has 23 hours on the timeline. **Duration.ofHours(24)** preserves a 24-hour length; **plusDays(1)** preserves advancing one day according to ZonedDateTime calendar rules.

Do not assume “tomorrow at the same time” equals Duration.ofHours(24) if the requirement is local wall-clock time. Conversely, if business logic requires exactly 24 hours to elapse, Duration is the right way to express it.

If you only have two zoneless **LocalDateTime** values, Duration.between cannot know the zone or DST on its own. When you must measure the actual elapsed interval, resolve the appropriate Instants first.

## 10. Precision, Arithmetic Limits, and Negative Signs

Duration stores length in seconds and nanoseconds, but methods that convert the total to a long have limits:

- **toMillis()** or **toNanos()** can throw **ArithmeticException** if the result does not fit in a long.
- **toDays()** returns the whole number of 24-hour days; any remainder is not represented in this integer day count.
- **isNegative()** and **isZero()** help validate a duration before using it as a timeout/TTL.
- Adding or subtracting a Duration with an Instant is also bounded by Instant's valid range; not every arbitrarily large value is valid.

Input validation example:

~~~java
Duration ttl = Duration.ofMinutes(15);

if (ttl.isZero() || ttl.isNegative()) {
    throw new IllegalArgumentException("ttl must be positive");
}
~~~

This is a rule chosen by the application. Another system might use **Duration.ZERO** to mean disabling a timeout; what matters is that the contract is clear before processing.

### Formatting Duration

Duration.toString() uses an ISO-8601-based format, for example:

~~~text
PT2.345S
PT15M
PT1H30M
PT-5S
~~~

This is a technical representation of an amount of time, not a date/time timestamp. **PT15M** means 15 minutes; it contains no start date or time zone.

## 11. Business Example: Request with an Overall Deadline and Elapsed Time Measurement

You may need both to know **when a request arrived** and to measure **how long processing took**. Those two purposes require two corresponding sources:

~~~java
Instant receivedAt = Instant.now(clock);  // Timestamp for logging
long startedTick = System.nanoTime();     // Tick to measure elapsed time

// Call service/read data/process...

long elapsedNanos = System.nanoTime() - startedTick;
Duration processingTime = Duration.ofNanos(elapsedNanos);
~~~

If the deadline is 2 seconds from arrival, create **deadline = receivedAt.plus(Duration.ofSeconds(2))**. However, when enforcing internal timeouts, an Instant-based deadline can be affected if the system clock changes; sensitive systems should convert it into a monotonic budget or use an appropriate deadline/timeout API.

Do not use a single time value for every purpose just to simplify code. A timestamp for logging and a counter for latency answer two different questions.

## 12. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
|---|---|---|
| Using **Duration.ofDays(30)** for “one calendar month” | A month has 28, 29, 30, or 31 days | Use calendar arithmetic/Period per business policy |
| Subtracting Instant.now() calls for benchmarking | The wall clock can be adjusted | Use System.nanoTime() |
| Using an absolute nanoTime value as a timestamp | Unrelated to UTC and only meaningful for differences within the JVM | Only subtract two readings; use Instant for timestamps |
| Checking **isAfter(deadline)** to determine expiration | Exactly at the deadline may still be treated as not expired | Define the boundary clearly; usually use **!now.isBefore(deadline)** |
| Calling now multiple times in a single decision | Can cross the deadline between comparisons | Capture one Instant and reuse it |
| Passing Duration.toNanos() to an API with a huge interval | Can overflow long | Check bounds and use an appropriate unit/API method |
| Treating Duration as a countdown clock | It is only an amount-of-time value, not self-updating | Combine with Clock/Instant or a scheduler/timer |
| Expecting sleep/retry to be accurate to the millisecond | The scheduler and OS can run late | Design deadlines, timeouts, and latency measurements accordingly |
| Using LocalTime to measure a shift across midnight | No date is stored, so the interval can be negative | Include the date or use Instant |
| Adding 24 hours and assuming it is always the same time tomorrow | DST can shift the local hour | Use ZonedDateTime.plusDays(1) for calendar arithmetic |
| Treating a negative Duration as infinite | Not a standard shared meaning | Explicitly define 0/negative policies in the API |
| Timing once and drawing performance conclusions | JIT/GC/scheduler noise | Use a proper benchmark with multiple iterations |

## 13. Checklist for Applying Duration

Before using Duration, answer:

1. **Is it an amount of time or a point in time?** Use Duration for an amount of time; a deadline needs Instant or an appropriate calendar/zoned type.
2. **Does the requirement call for actual elapsed time or calendar advancement?** 24 hours differs from one local day across DST.
3. **What is measuring latency?** Use System.nanoTime() for differences within the same JVM.
4. **Does the deadline have a clear boundary rule?** For example, expired when now >= deadline.
5. **Does the timeout have an overall deadline?** Do not grant the full timeout again on every retry if a total limit is required.
6. **Can Duration be negative or zero?** Define and validate the policy.
7. **Could converting to millis/nanos overflow?** Check large intervals.
8. **Is Clock injected into the service for testing?** Use Clock.fixed/offset for before, at, and after the deadline.
9. **Do timing examples distinguish timestamps from elapsed time?**
10. **Do API/database results preserve units and semantics?**

### Self-Check Questions

**1. Is Duration.ofMinutes(15) an expiration timestamp?**  
No. It is a 15-minute amount of time. Adding it to the Instant of issuance produces the deadline.

**2. What should be used to measure latency within the same JVM?**  
Use the difference between two System.nanoTime() calls, and optionally wrap that difference with Duration.ofNanos(...).

**3. Has a token expired when now equals expiresAt?**  
Under the half-open validity interval [issuedAt, expiresAt), the token is expired when now >= expiresAt.

**4. Is Duration.ofDays(1) the same as tomorrow at the same time in every time zone?**  
No. Duration.ofDays(1) is 24 hours; a calendar day in a DST zone can be 23 or 25 hours long.

**5. Does Duration.between(LocalTime.of(23,30), LocalTime.of(1,0)) automatically return 90 minutes?**  
No. LocalTime has no date and the calculation does not infer midnight; you must use full dates or an explicit business rule.

**6. Why is Clock.fixed useful for testing deadlines?**  
It lets you specify “now” precisely without waiting for real time to pass. Clock.offset can simulate before, at, and after the deadline.

**7. Does Duration automatically cancel a task when it expires?**  
No. It only represents an amount of time. Timeouts must be enforced by the appropriate API/client/scheduler or application logic.

**Key takeaway:** Duration answers **“how long?”**, while Instant answers **“when?”**. A deadline is formed from a point in time plus a Duration; latency measurement requires a monotonic clock; calendar dates and local times require calendar types with ZoneId. Once each meaning is clear, timeouts, retries, and deadlines become easier to test and less prone to boundary bugs.
