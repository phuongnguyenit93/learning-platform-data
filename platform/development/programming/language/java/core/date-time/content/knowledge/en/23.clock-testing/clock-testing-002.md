# Clock provides the current instant and time zone

## 1. “Now” consists of a time source and a local date interpretation

When code calls `LocalDate.now()`, it depends on both the current instant at runtime and the environment's default time zone. Near midnight, the same instant can already be a new day in Vietnam while still being the previous day in UTC.

`java.time.Clock` turns these two dependencies into an object that can be passed in:

- **Time source:** which `Instant` does the clock return when queried?
- **Time zone:** which `ZoneId` is used when converting that instant into a local date/time?

As a result, a feature can read “now” from a configured source, while tests can replace that source with a controlled clock. There is no need to depend directly on the actual machine time at execution to test a date condition.

`Clock` is an abstract class. Typically, you use its built-in factory methods and pass it to where time is needed, rather than writing a custom clock class from scratch.

## 2. Core methods

| Method | Data returned | Is a time zone needed to interpret the result? |
|---|---|---|
| `clock.instant()` | The instant as an `Instant` | The instant itself does not depend on a time zone |
| `clock.millis()` | Milliseconds from the clock's epoch | Not a local time; it is a numeric representation of the instant |
| `clock.getZone()` | The time zone used to produce dates/times | This is the conversion context |
| `clock.withZone(zone)` | A corresponding clock with a different time zone | Changes the date/time context while keeping the time source per contract |

An `Instant` identifies a point on the timeline; there is no “Instant in Vietnam time” distinct from an “Instant in UTC” for the same point in time. When printing an `Instant`, Java typically uses the `Z` suffix; that does not mean it omitted a time zone that needs to be added to the value.

`millis()` only retains millisecond precision. If sub-millisecond parts supported by the source are needed, use `instant()` instead of converting through a `long` and reconstructing. Also, do not assume that because a clock has a nanosecond-capable API, the hardware source is always accurate to the nanosecond.

## 3. now(clock) uses the clock according to the result type

The main `java.time` types have a `now(Clock)` variant:

```java
Instant instant = Instant.now(clock);
LocalDate today = LocalDate.now(clock);
LocalDateTime local = LocalDateTime.now(clock);
ZonedDateTime zoned = ZonedDateTime.now(clock);
```

This is an illustrative snippet inside a method with a `clock` variable; the standalone program is in section 7.

- `Instant.now(clock)` obtains the instant; the clock's time zone does not shift the instant.
- `LocalDate.now(clock)` uses the clock's instant and time zone to determine the date, then keeps only the date part.
- `LocalDateTime.now(clock)` keeps the local date-time without retaining time zone information in the result type.
- `ZonedDateTime.now(clock)` keeps the date-time, the time zone, and the corresponding offset at that instant.

Therefore, choosing `Clock.systemUTC()` and calling `LocalDate.now(clock)` means getting **the current date in UTC**, not the user's date anywhere else. If a feature relies on the date in Vietnam, you must configure the appropriate time zone or convert according to the time zone defined for that feature.

## 4. Choosing a system clock source explicitly

Common options:

```java
Clock utc = Clock.systemUTC();
Clock vietnam = Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
Clock machineDefault = Clock.systemDefaultZone();
```

This snippet only creates three clock configurations; it does not guarantee that the actual current time will be any fixed value.

| Option | Appropriate meaning |
|---|---|
| `systemUTC()` | System source, UTC context; convenient when the feature primarily needs an instant |
| `system(zone)` | System source with an explicitly configured time zone |
| `systemDefaultZone()` | System source with the environment's default time zone at the time that configuration is created |

The default time zone can differ between a developer's machine, a server, and a test environment. If a business result must follow a specific region, use an explicit configuration instead of implicitly relying on the environment.

`Clock.system(zone)` uses the available system clock; it does not contact a time server in that region. Setting the zone to `Asia/Ho_Chi_Minh` does not change the machine's time zone, re-synchronize the clock, or fix a skewed system source.

## 5. withZone changes the date/time view, without adding seven hours to the Instant

For the instant `2026-10-24T18:30:00Z`:

```text
UTC:                  2026-10-24 18:30
Asia/Ho_Chi_Minh:      2026-10-25 01:30
```

Both representations refer to the exact same instant, but the local dates differ. You can create another clock using `utc.withZone(...)` and compare the date values.

`withZone` does not mutate the original clock. You must use the return value, just like many immutable `java.time` APIs. With a running system clock, two consecutive reads from two clocks can differ because time has elapsed between calls; do not assert that they are always equal to the nanosecond and conclude the time zone configuration is wrong.

The example in section 7 uses `Clock.fixed` so the same `Instant` is returned on every read. A fixed clock is a tool for observing the effect of the time zone in isolation, not a real-time source for production.

## 6. Passing Clock and capturing the instant once when consistency is needed

A class that uses time should receive a `Clock` via its constructor or a parameter. The production environment supplies a system clock; tests can supply another clock without modifying the algorithm.

If a single operation needs to record both the instant and its corresponding local date, capture it once:

```java
Instant captured = clock.instant();
ZonedDateTime localView = captured.atZone(clock.getZone());
```

You should not call `Instant.now(clock)` and then `LocalDate.now(clock)` multiple times and assume they all belong to the same point in time. If the system crosses midnight between calls, the date read later may differ from the date derived from the instant read earlier.

Conversely, if operations intentionally need fresh instants at different steps, read again. Passing a `Clock` helps control dependencies; it does not automatically freeze time or group multiple calls into a time transaction.

Nor does the time zone of a shared clock automatically represent every user. If a feature uses each user's time zone, keep a shared time source and determine the time zone explicitly per request context, rather than mutating global configuration between requests.

## 7. Complete runnable program

Save the following code to `ClockSourceDemo.java`. The program uses Java 17 or later and requires no external libraries. Values are fixed so the output is reproducible.

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.Objects;

public class ClockSourceDemo {
    record CurrentView(Instant instant, ZonedDateTime localDateTime) {}

    static final class TimeService {
        private final Clock clock;

        TimeService(Clock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        CurrentView currentView() {
            Instant captured = clock.instant();
            return new CurrentView(captured, captured.atZone(clock.getZone()));
        }

        LocalDate today() {
            return LocalDate.now(clock);
        }
    }

    public static void main(String[] args) {
        Instant reference = Instant.parse("2026-10-24T18:30:00Z");
        Clock utc = Clock.fixed(reference, ZoneOffset.UTC);
        Clock vietnam = utc.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("utcZone=" + utc.getZone());
        System.out.println("vietnamZone=" + vietnam.getZone());
        System.out.println("sameInstant="
                + utc.instant().equals(vietnam.instant()));
        System.out.println("instantNow=" + Instant.now(vietnam));
        System.out.println("utcDate=" + LocalDate.now(utc));
        System.out.println("vietnamDate=" + LocalDate.now(vietnam));
        System.out.println("vietnamDateTime=" + ZonedDateTime.now(vietnam));
        System.out.println("millisMatch="
                + (vietnam.millis() == reference.toEpochMilli()));

        TimeService service = new TimeService(vietnam);
        CurrentView view = service.currentView();
        System.out.println("captured=" + view.instant());
        System.out.println("localView=" + view.localDateTime());
        System.out.println("today=" + service.today());
        System.out.println("utcStill=" + utc.getZone());
    }
}
```

Compile and run:

```shell
javac ClockSourceDemo.java
java ClockSourceDemo
```

Expected output:

```text
utcZone=Z
vietnamZone=Asia/Ho_Chi_Minh
sameInstant=true
instantNow=2026-10-24T18:30:00Z
utcDate=2026-10-24
vietnamDate=2026-10-25
vietnamDateTime=2026-10-25T01:30+07:00[Asia/Ho_Chi_Minh]
millisMatch=true
captured=2026-10-24T18:30:00Z
localView=2026-10-25T01:30+07:00[Asia/Ho_Chi_Minh]
today=2026-10-25
utcStill=Z
```

`Z` is the representation of offset 0 for `ZoneOffset.UTC`. Both clocks return the same instant, yet `LocalDate.now` produces two different dates because of the time zone.

`TimeService.currentView()` keeps the captured `Instant` and the local date-time derived from that exact instant. `today()` is a separate read operation; in the example it is stable because the source is a fixed clock. With a system source, separate calls can occur at different instants.

The line `utcStill=Z` confirms that creating the Vietnam clock does not change the original UTC clock's configuration.

## 8. Limitations to understand when using Clock

### Not a monotonic elapsed-time clock

The system clock can be adjusted. `Clock` does not guarantee that every read increases monotonically or that it can be used to accurately measure execution duration. When you need to measure short elapsed intervals within a process, tools like `System.nanoTime()` serve that purpose; do not derive a calendar date/time from it.

`Duration.between(startInstant, endInstant)` describes the difference between two read instants. If the instant source is adjusted, that is not automatically a monotonic measurement of how long the program has been running.

### The “current” source can be a simulated source

`Clock` is a replaceable abstraction. It can return a fixed instant or one adjusted for testing; therefore, “current” means current according to the supplied source, and does not by itself prove it is the real external time.

Validating the supplied source at the configuration boundary helps avoid accidentally using a test clock in a production environment. There is no need for a business class to inspect the implementation type and reject fake clocks: choosing the source belongs to application assembly.

### Does not contain locale or business policies

`Clock` does not determine the display locale, working days, holiday schedules, or cutoff times. It provides the instant and the time zone; other rules require the appropriate components.

Passing a `Clock` into a class is also not enough if that class still calls parameterless `LocalDate.now()` or `Instant.now()` on another code path. When you want to control the time source, you must consistently use the received source wherever the same contract is required.

## 9. Practice exercises

1. Change the fixed instant to `2026-10-24T16:30:00Z`. In UTC it is October 24; in Vietnam at that time it is 23:30 on the same day. Observe the date-change boundary compared to the initial example.
2. Keep the original instant and change the time zone to `Asia/Tokyo`. Verify that `Instant.now` stays the same while the local date/time is converted to the new zone.
3. Construct `TimeService` with two fixed clocks having the same instant but different time zones. Identify which method changes its result (`today`) and which part must keep the same instant (`captured`).

References: [Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html), [LocalDate — now(Clock)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#now(java.time.Clock)), and [Instant — now(Clock)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html#now(java.time.Clock)) in Java SE 21.