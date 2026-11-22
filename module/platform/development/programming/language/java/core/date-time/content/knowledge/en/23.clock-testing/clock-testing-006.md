# `InstantSource` When Only an Instant Provider Is Needed

## When a Class Does Not Need to Know the Time Zone

A class that checks whether a submission is past its deadline only needs to know:

```text
has the current instant reached or passed the expiration instant?
```

If both values are `Instant`, the class does not need to choose a date according to Vietnam, UTC, or any other zone. Passing a whole `Clock` still works, but the dependency scope is broader than necessary: a Clock also carries a zone to derive local date and time.

Since Java 17, `InstantSource` provides an interface focused on **an instant source**. Business classes can receive this source from the outside, using system time in production and a fixed instant in tests.

## 1. What Does `InstantSource` Provide?

The core call:

```java
Instant now = source.instant();
```

`source` is an `InstantSource`. It can return system time, a fixed instant, or another source depending on configuration.

Key capabilities:

| API | Meaning |
| --- | --- |
| `instant()` | Reads an `Instant` from the source |
| `millis()` | Reads the instant value at millisecond granularity |
| `system()` | Creates a source based on the system clock |
| `fixed(instant)` | Creates a source that always returns the same instant |
| `offset(base, duration)` | Creates a source returning the base source's instant plus an offset |
| `tick(base, duration)` | Creates a source whose instants are truncated to the configured tick |
| `withZone(zone)` | Creates a `Clock` carrying a zone when local date/time is needed |

The interface has no `getZone()`. It describes obtaining an instant without defining "where today is." A source is also not required to return advancing real time; a fixed source is a valid way to use it for testing. [`InstantSource` Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/InstantSource.html)

You can visualize it as:

```text
InstantSource
     │
     └── instant() → Instant
                         │
                         └── only when date/time is needed:
                             choose a ZoneId or create a Clock via withZone
```

## 2. Choosing `InstantSource`, `Clock`, or `Instant`?

These three types serve three different needs:

| Receiver's Need | Usually Appropriate Input |
| --- | --- |
| Only processes an already-observed instant | `Instant` |
| Decides when to read "now", only needs an instant | `InstantSource` |
| Needs both a source of "now" and a zone to derive date/time | `Clock` |

For example:

- A pure function taking `now` and `expiresAt` to compare them may only need two `Instant` values.
- A service that must record the creation instant on each call can accept an `InstantSource`.
- A service that determines the registration date according to a business zone can accept a `Clock`, or accept an instant source and a zone separately if that makes the design clearer.

There is no need to replace every `Clock` in the system just to use the new type. Choose the type based on the information the class actually needs.

`Clock` implements `InstantSource`, so an existing Clock can be passed wherever `InstantSource` is accepted without any adapter. [`Clock` Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html)

```java
InstantSource source = Clock.systemUTC();
```

This is an illustrative snippet; it requires importing `InstantSource` and `Clock`.

Even though the actual object may be a Clock, code accepting `InstantSource` should stick to the instant contract rather than casting back to Clock to retrieve a zone.

## 3. Complete Program: Creating and Checking Deadlines by Instant

Suppose a submission window opens at `issuedAt` and expires at `expiresAt`. When the current instant is **equal to** `expiresAt`, the submission is already overdue. The validity interval is understood as `[issuedAt, expiresAt)`.

Save as `InstantSourceDemo.java`. The program requires Java 17 or later:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.InstantSource;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Objects;

public class InstantSourceDemo {
    record SubmissionWindow(Instant issuedAt, Instant expiresAt) {}

    static final class SubmissionService {
        private final InstantSource source;

        SubmissionService(InstantSource source) {
            this.source = Objects.requireNonNull(source);
        }

        SubmissionWindow openWindow(Duration validity) {
            Objects.requireNonNull(validity);
            if (validity.isNegative() || validity.isZero()) {
                throw new IllegalArgumentException("Thoi han phai duong");
            }

            Instant issuedAt = source.instant();
            return new SubmissionWindow(
                    issuedAt, issuedAt.plus(validity));
        }

        boolean isExpired(SubmissionWindow window) {
            Instant now = source.instant();
            return !now.isBefore(window.expiresAt());
        }
    }

    public static void main(String[] args) {
        Instant observedAt = Instant.parse("2024-06-15T18:30:00Z");
        InstantSource fixed = InstantSource.fixed(observedAt);

        SubmissionService service = new SubmissionService(fixed);
        SubmissionWindow window =
                service.openWindow(Duration.ofMinutes(10));

        System.out.println("issuedAt=" + window.issuedAt());
        System.out.println("expiresAt=" + window.expiresAt());
        System.out.println("expiredAtIssue=" + service.isExpired(window));

        InstantSource justBefore = InstantSource.fixed(
                window.expiresAt().minusNanos(1));
        InstantSource atBoundary =
                InstantSource.fixed(window.expiresAt());
        InstantSource justAfter = InstantSource.fixed(
                window.expiresAt().plusNanos(1));

        System.out.println("expiredJustBefore="
                + new SubmissionService(justBefore).isExpired(window));
        System.out.println("expiredAtBoundary="
                + new SubmissionService(atBoundary).isExpired(window));
        System.out.println("expiredJustAfter="
                + new SubmissionService(justAfter).isExpired(window));

        InstantSource shifted =
                InstantSource.offset(fixed, Duration.ofMinutes(10));
        System.out.println("shiftedInstant=" + shifted.instant());
        System.out.println("originalUnchanged=" + fixed.instant());

        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        Clock clockView = fixed.withZone(vietnam);

        System.out.println("clockViewInstant=" + clockView.instant());
        System.out.println("clockViewZone=" + clockView.getZone().getId());
        System.out.println("localDateFromClock=" + LocalDate.now(clockView));

        InstantSource acceptedClock =
                Clock.fixed(observedAt, vietnam);
        SubmissionWindow fromClock =
                new SubmissionService(acceptedClock)
                        .openWindow(Duration.ofMinutes(10));
        System.out.println("clockAcceptedSameExpiry="
                + fromClock.expiresAt().equals(window.expiresAt()));

        InstantSource system = InstantSource.system();
        System.out.println("systemInstantRead=" + (system.instant() != null));
    }
}
```

Compile and run:

```shell
javac --release 17 InstantSourceDemo.java
java InstantSourceDemo
```

Stdout:

```text
issuedAt=2024-06-15T18:30:00Z
expiresAt=2024-06-15T18:40:00Z
expiredAtIssue=false
expiredJustBefore=false
expiredAtBoundary=true
expiredJustAfter=true
shiftedInstant=2024-06-15T18:40:00Z
originalUnchanged=2024-06-15T18:30:00Z
clockViewInstant=2024-06-15T18:30:00Z
clockViewZone=Asia/Ho_Chi_Minh
localDateFromClock=2024-06-16
clockAcceptedSameExpiry=true
systemInstantRead=true
```

The program reads the system source at the end without printing a "current" value that changes on every run. The business results use a fixed instant so they are reproducible.

## 4. Why Pass the Source In Instead of Creating It Inside the Method?

In production, the application wiring can use:

```java
SubmissionService service =
        new SubmissionService(InstantSource.system());
```

This is an excerpt; it requires the service class from the full program.

In tests, the same class receives `InstantSource.fixed`. There is no need to change business code, wait for time to pass, or alter the system clock.

If a method calls `Instant.now()` or creates `InstantSource.system()` internally, the injected source no longer controls the entire behavior. A class that has a `source` field but still reads time directly elsewhere has only partially decoupled its dependency.

In Java 17, the direct way with an `InstantSource` variable is `source.instant()`. Do not assume an `Instant.now(InstantSource)` overload exists; the source-accepting overload of `Instant.now` in this version takes a `Clock`. There is no need to create a Clock with an arbitrary zone just to call `now` when `instant()` already satisfies the need.

Choose the source at the configuration boundary, and read the source at the exact place where "now" needs to be observed.

## 5. Reading One Instant When Values Must Relate to the Same Observation

The `openWindow` method reads the source once:

```java
Instant issuedAt = source.instant();
Instant expiresAt = issuedAt.plus(validity);
```

Because of this, the 10-minute validity period is calculated from the exact issuance instant.

The following approach has a different meaning because it performs two reads:

```java
Instant issuedAt = source.instant();
Instant expiresAt = source.instant().plus(validity);
```

This snippet illustrates what to avoid if the requirement is `expiresAt = issuedAt + validity`. With a real source, the second read may be later. With a mock source that advances on each read, the difference becomes even more obvious.

You do not have to force every method to read only once in all situations. If you are processing a long workflow and genuinely need to observe the time again, reading again is appropriate. What you need to decide is which values must be derived from the same instant.

## 6. Testing Boundaries with a Fixed Source

Three cases:

```text
expiresAt - 1 nanosecond → not yet expired
expiresAt                → expired
expiresAt + 1 nanosecond → expired
```

directly verify the rule at the boundary.

If you write:

```java
return now.isAfter(expiresAt);
```

then the instant equal to the deadline is not yet considered expired. The formula in this article uses `!now.isBefore(expiresAt)` because the contract chose an exclusive upper bound.

The equality-at-deadline rule is a business decision; what matters is defining it clearly and testing all three sides. Do not wait a real 10 minutes or use `Thread.sleep` to verify a comparison whose inputs you can control.

Using nanosecond offsets in the test does not imply the system source has nanosecond precision. It only tests the comparison logic for `Instant` values that the data type can represent.

## 7. `offset` Shifts the Instant, `withZone` Adds a Local View

The two methods have different effects:

| Operation | Does it change the provided `Instant`? | Purpose |
| --- | --- | --- |
| `InstantSource.offset(base, duration)` | Yes, adds an offset to the base source's instant | Simulates being ahead or behind by a duration |
| `source.withZone(zone)` | No, does not change the instant provided by the base source | Creates a Clock to use a zone when deriving date/time |

In the program:

- `offset` moves the instant from 18:30 to 18:40.
- `withZone(vietnam)` still provides the 18:30Z instant, while the local date is June 16.

A duration offset is not a time-zone offset. `Duration.ofHours(7)` advances the instant by seven hours; choosing the `Asia/Ho_Chi_Minh` zone views the same instant under that zone's rules.

The source created by `offset` does not mutate the `fixed` variable to a new instant. The program prints the original source again to show it is still 18:30.

With a system base source, wrapping it with `offset` still produces a source that reads advancing time. It does not automatically become a fixed source. [`offset` and `withZone` Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/InstantSource.html)

## 8. When a Single Instant Is Enough

Not every class needs to hold a source. If the caller has already captured `now` for the entire operation, a function can accept the instant directly:

```java
static boolean isExpiredAt(Instant now, Instant expiresAt) {
    return !now.isBefore(expiresAt);
}
```

This is an illustrative method placed inside a class; it requires importing `Instant`.

This function does not decide when to read the time, so testing it with two values is very straightforward. The caller can call `source.instant()` once and pass that instant to multiple checks that need to be consistent.

Use `InstantSource` when the receiver needs **the ability to obtain an instant at execution time**. Use `Instant` when the receiver only needs **an already-determined instant value**. Both choices can coexist in the same design.

## 9. Limitations and Caveats When Using Custom Sources

`InstantSource` is an abstraction for an instant provider; it does not guarantee that every source follows real time. A source may be fixed, offset, or have other documented behavior.

When using or implementing a custom source, you should know:

- Whether the source is safe when called by multiple threads.
- Whether the source can throw errors when read.
- Its actual accuracy and resolution.
- Whether time can be adjusted or fail to advance monotonically.
- How reproducibility in tests is controlled.

Do not assume `InstantSource.system()` is a monotonic duration-measuring source or an independent network-synchronized time source. It relies on the available system source. If the goal is measuring performance or elapsed time for an algorithm, choose a tool suited to that requirement rather than inferring it from the name "source".

`millis()` only provides millisecond-level representation; if your logic needs to compare instants with sub-millisecond fractions, keep `Instant` and understand the precision of the underlying source data. Do not convert to integers and unintentionally lose fractional parts.

## 10. Verifying the Design and Self-Practice

A useful test suite for a class that only needs instants:

- A fixed source produces the expected issuance value.
- Instants before, at, and after the deadline.
- The injected source actually governs behavior.
- Negative or zero durations are handled according to the contract.
- Clocks with different zones but the same instant produce the same deadline comparison result.
- Multiple values that must be consistent are derived from the same read.

Self-check questions:

1. Does a service that only compares two `Instant` values necessarily need to know the time zone?
2. Can a `Clock` be passed to an `InstantSource` parameter?
3. Does a fixed source advance on its own after waiting with `sleep`?
4. Is a seven-hour `offset` equivalent to changing the zone to Vietnam?
5. When should you pass an `Instant` instead of a source?

Suggested answers:

1. No, if the business logic is only comparing instants.
2. Yes, because Clock implements this interface.
3. No; it always returns the configured instant.
4. No; one operation shifts the instant, while the other changes the local view.
5. When the receiver only processes an already-observed instant and does not need to read "now" itself.

Use `InstantSource` to accurately express a dependency on an instant provider, choose a real or fixed source at wiring time, and clearly verify the boundaries required by your business logic.
