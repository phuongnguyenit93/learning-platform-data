# `Clock.systemUTC()` and `Clock.system(ZoneId)`

## Choosing the "now" source and choosing the local date-time view

An application needs to record the creation instant of a submission while also determining "today" in Vietnam time. These two tasks are related but not identical:

- The creation instant is a point on the timeline, typically represented by `Instant`.
- "Today" is a local date, which requires a time zone to determine.

`Clock` combines an instant source with a zone used when deriving dates/times. Two common factories are:

```java
Clock utcClock = Clock.systemUTC();
Clock vietnamClock = Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
```

This is an illustrative snippet; you need to import `java.time.Clock` and `java.time.ZoneId`.

Both read the system time source; the main difference here is the zone configured in the Clock. Choosing the Vietnam zone does not mean `Instant` has seven hours added to it.

## 1. Two components to distinguish in a `Clock`

| Component | API | Meaning |
| --- | --- | --- |
| Instant provided by the clock | `clock.instant()` | An `Instant` |
| Time zone used to derive date and time | `clock.getZone()` | A `ZoneId` |
| Changing the zone for the same clock source | `clock.withZone(zone)` | A Clock with a different zone |

You can visualize it as:

```text
System time source
          │
          ▼
       Instant
          │
          ├── UTC                 → date/time in UTC
          └── Asia/Ho_Chi_Minh    → date/time in Vietnam zone
```

`Clock.systemUTC()` uses the UTC zone. `Clock.system(zone)` uses the passed-in zone. The system factories select the best available system time source; you should not assume the resolution is always nanoseconds just because `Instant` can represent nanosecond precision. [`Clock` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html)

For the same observed instant, changing the zone changes the local date-time view. Consecutive calls to read two real clocks can still return slightly different instants, because time has elapsed between the two reads.

## 2. Which factory is used for which purpose?

### `Clock.systemUTC()`

Suitable when a class needs a system instant source with the source's default zone declared as UTC. For example:

```java
Clock clock = Clock.systemUTC();
Instant createdAt = Instant.now(clock);
```

This is an illustrative snippet. `Instant` does not store a "UTC local time" as a separate hour field; it represents a point in time. Its common string representation ends with `Z`.

If you take:

```java
LocalDate today = LocalDate.now(clock);
```

then "today" here is the date in UTC, because the `LocalDate` class needs the Clock's zone to derive the date. Do not assume that date is always equal to the current date of a user in Vietnam.

### `Clock.system(ZoneId)`

Suitable when the system time source must be paired with a specific business zone:

```java
Clock clock = Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
LocalDate businessToday = LocalDate.now(clock);
```

`businessToday` is calculated in the specified zone. If you use `Instant.now(clock)`, the result is still a point in time, not an instant shifted forward by seven hours.

### Difference from `systemDefaultZone()`

`Clock.systemDefaultZone()` takes the environment's default zone at the time the Clock is created. If the business logic requires a specific zone, choosing `system(zone)` makes that configuration explicit and avoids letting the host machine decide implicitly.

Creating a Clock with a specific zone does not change the default time zone of the JVM or the operating system. It only provides a configured object for your code to use.

## 3. Complete program

Save as `SystemClockZonesDemo.java`. The program uses Java 17 or later:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.Objects;

public class SystemClockZonesDemo {
    record Snapshot(Instant observedAt, LocalDate businessDate) {}

    static final class LearningService {
        private final Clock clock;

        LearningService(Clock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        Snapshot snapshot() {
            Instant observedAt = clock.instant();
            LocalDate businessDate =
                    observedAt.atZone(clock.getZone()).toLocalDate();
            return new Snapshot(observedAt, businessDate);
        }
    }

    public static void main(String[] args) {
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

        Clock systemUtc = Clock.systemUTC();
        Clock systemVietnam = Clock.system(vietnam);

        System.out.println("systemUtcZone=" + systemUtc.getZone().getId());
        System.out.println("systemVietnamZone="
                + systemVietnam.getZone().getId());
        System.out.println("utcConfigured="
                + systemUtc.getZone().normalized().equals(ZoneOffset.UTC));
        System.out.println("vietnamConfigured="
                + systemVietnam.getZone().equals(vietnam));

        Clock changedView = systemUtc.withZone(vietnam);
        System.out.println("changedViewZone=" + changedView.getZone().getId());
        System.out.println("originalStillUtc="
                + systemUtc.getZone().normalized().equals(ZoneOffset.UTC));

        Instant actualNow = Instant.now(systemUtc);
        System.out.println("systemInstantRead=" + (actualNow != null));

        Instant sample = Instant.parse("2024-06-15T18:30:00Z");
        Clock fixedUtc = Clock.fixed(sample, ZoneOffset.UTC);
        Clock fixedVietnam = fixedUtc.withZone(vietnam);

        System.out.println("fixedUtcInstant=" + Instant.now(fixedUtc));
        System.out.println("fixedVietnamInstant=" + Instant.now(fixedVietnam));
        System.out.println("sameFixedInstant="
                + Instant.now(fixedUtc).equals(Instant.now(fixedVietnam)));

        System.out.println("utcDate=" + LocalDate.now(fixedUtc));
        System.out.println("vietnamDate=" + LocalDate.now(fixedVietnam));
        System.out.println("utcLocal=" + LocalDateTime.now(fixedUtc));
        System.out.println("vietnamLocal=" + LocalDateTime.now(fixedVietnam));
        System.out.println("vietnamZoned=" + ZonedDateTime.now(fixedVietnam));

        LearningService service = new LearningService(fixedVietnam);
        Snapshot snapshot = service.snapshot();
        System.out.println("snapshotInstant=" + snapshot.observedAt());
        System.out.println("snapshotBusinessDate=" + snapshot.businessDate());

        Clock explicitUtc = Clock.system(ZoneOffset.UTC);
        System.out.println("explicitUtcConfigured="
                + explicitUtc.getZone().equals(ZoneOffset.UTC));
    }
}
```

Compile and run:

```shell
javac --release 17 SystemClockZonesDemo.java
java SystemClockZonesDemo
```

Stdout:

```text
systemUtcZone=Z
systemVietnamZone=Asia/Ho_Chi_Minh
utcConfigured=true
vietnamConfigured=true
changedViewZone=Asia/Ho_Chi_Minh
originalStillUtc=true
systemInstantRead=true
fixedUtcInstant=2024-06-15T18:30:00Z
fixedVietnamInstant=2024-06-15T18:30:00Z
sameFixedInstant=true
utcDate=2024-06-15
vietnamDate=2024-06-16
utcLocal=2024-06-15T18:30
vietnamLocal=2024-06-16T01:30
vietnamZoned=2024-06-16T01:30+07:00[Asia/Ho_Chi_Minh]
snapshotInstant=2024-06-15T18:30:00Z
snapshotBusinessDate=2024-06-16
explicitUtcConfigured=true
```

The program actually reads the system Clock, but does not print the current instant that changes on every run. The date/time comparison section uses a fixed instant so that stdout can be verified.

## 4. Same instant, two local dates

The sample instant is:

```text
2024-06-15 18:30 UTC
            │
            └── in Asia/Ho_Chi_Minh: 2024-06-16 01:30
```

Therefore:

| Call | UTC Clock | Vietnam zone Clock |
| --- | --- | --- |
| `Instant.now(clock)` on a fixed Clock at the same instant | Same `Instant` | Same `Instant` |
| `LocalDate.now(clock)` | 2024-06-15 | 2024-06-16 |
| `LocalDateTime.now(clock)` | 2024-06-15T18:30 | 2024-06-16T01:30 |
| `ZonedDateTime.now(clock)` | Retains corresponding zone/offset | Retains corresponding zone/offset |

`LocalDate.now(clock)` computes the current date from the Clock's instant and zone. The resulting `LocalDate` does not retain the time zone inside it. [`LocalDate.now(Clock)` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#now(java.time.Clock))

This is why a system checking "does the submission belong to today?" must use a consistent zone. Using the UTC date in one place and the Vietnam date in another can yield two different conclusions around midnight, even when every machine has accurate time.

For an absolute expiration instant, you typically compare `Instant`. For rules based on a zone's calendar date, you need to derive the date using that zone. Do not choose types and Clocks solely based on string-printing habits.

## 5. `withZone` changes the zone, not freezing time or shifting the instant

In the program:

```java
Clock changedView = systemUtc.withZone(vietnam);
```

creates a Clock with the Vietnam zone for the same instant-providing mechanism. The source Clock still retains the UTC zone. There is no need to mutate the original Clock or change global configuration.

However, `withZone` does not make a system clock fixed. Each call to `instant()` on a system Clock is still a read from the time source.

Therefore, the following snippet is not a reliable check:

```java
// Illustrates what should not be used to check zone equivalence.
boolean same = systemUtc.instant().equals(changedView.instant());
```

The two calls can return different instants because they are executed at two different moments. A `false` value does not prove that the zone shifted the instant.

The program uses `Clock.fixed` solely to isolate the effect of the zone at the same instant. In production, choose a system factory; in tests that need reproducibility, pass in a controllable time source.

`Clock.systemUTC()` and `Clock.system(ZoneOffset.UTC)` both express choosing the system source with the UTC zone. You should not rely on whether they are the same object reference or have the same internal implementation class name.

## 6. Passing `Clock` so time-dependent code is testable

The `LearningService` class receives `Clock` via its constructor. In production, the application can wire it up as:

```java
LearningService service = new LearningService(
        Clock.system(ZoneId.of("Asia/Ho_Chi_Minh")));
```

This is a snippet; it needs to be placed in context with the `LearningService` class as in the complete program.

In tests, pass `Clock.fixed` at an instant near a day boundary. The logic does not need to switch to a separate "testing" branch; the time source is what is replaceable.

If inside the class you create a new:

```java
Clock clock = Clock.systemUTC();
```

in each method, passing a test Clock from outside loses its effect. Similarly, a call to `LocalDate.now()` inserted in the middle of code that uses an injected Clock will read a different default source/zone.

Verify that the time-using code path actually depends on the provided object, not just that the class has a field named `clock`. `Clock` is designed to support substituting the time source for purposes such as testing. [Using `Clock` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html)

## 7. Read once when you need a consistent snapshot

The system clock does not stop between two lines of code. If you do:

```java
Instant createdAt = Instant.now(clock);
LocalDate businessDate = LocalDate.now(clock);
```

that is two separate reads. Near midnight, the second read can land on the new day while the first instant is still on the previous day.

In `snapshot()`, the program reads one `Instant` and derives the date from that exact instant:

```java
Instant observedAt = clock.instant();
LocalDate businessDate =
        observedAt.atZone(clock.getZone()).toLocalDate();
```

This approach is appropriate when `businessDate` must express the local date of `observedAt`. It does not mean every application must always capture time once for an entire long-running process. Choose when to read based on the semantics of each operation.

Also do not store `LocalDate.now(clock)` in an initialization constant and reuse it forever as "today". A Clock constant is a source that can be read repeatedly; a read date is only the value at the time of observation.

## 8. What a system Clock does not automatically guarantee

- Choosing UTC does not make the system time more accurate. Both factories still depend on the available system time source.
- Choosing a zone is not an operation that connects to a time server in that zone.
- A system Clock is not a fixed Clock for exact nanosecond-by-nanosecond comparison in tests.
- Do not infer physical precision from the granularity that `Instant` can store.
- System clock time can be adjusted; do not rely on the assumption that every read increases by an exact amount instead of verifying actual requirements.
- A regional time zone can change its offset over time. Use `ZoneId` and zone rules rather than manually adding a fixed number of hours in all cases.

If the goal is to measure the execution duration of a piece of code, distinguish elapsed-time measurement from reading calendar timestamps. This lesson focuses on the "current" source for creating business date-time values, not using a system Clock as a high-precision performance measurement tool.

## 9. Verifying configuration and behavior

Useful checks:

| What to verify | Appropriate way to check |
| --- | --- |
| UTC is configured | Inspect `getZone()`, normalize if you want to compare against a fixed zone |
| Business zone is exact | Compare with the required `ZoneId` |
| Same instant yields different dates across zones | Use a fixed Clock at an instant near midnight |
| Injected Clock is actually used | Run the logic with a fixed date far from the real date |
| Instant and local date in a record are consistent | Derive them from the same read |
| No dependency on host machine | Configure the zone explicitly and avoid mixing in default calls |

When testing local dates, include instants before and after the business zone's day boundary. Testing only at midday makes it easy for a UTC Clock and a Vietnam-zone Clock to produce the same date, hiding a misconfiguration.

## 10. Self-practice

1. Does `Clock.system(Asia/Ho_Chi_Minh)` automatically add seven hours to `Instant`?
2. Which zone does `LocalDate.now(Clock.systemUTC())` return the date in?
3. Why should you not compare two reads of a system Clock using `Instant.equals` and treat that as evidence about time zones?
4. To use the Vietnam zone in production and a fixed instant in tests, what should the business class accept?
5. If the creation instant and the business date must be consistent, should you perform two independent reads near midnight?

Suggested answers:

1. No; the zone is used when deriving local dates and times.
2. UTC.
3. The two reads occur at two different moments; a difference can be due to elapsed time.
4. Accept `Clock` via constructor or parameter, and use that source.
5. Read one instant and derive the date from that same instant if that is required by the record.

Use `systemUTC()` or `system(zone)` to choose a system source with an explicit zone, and pass `Clock` wherever "now" is needed so behavior can be verified.
