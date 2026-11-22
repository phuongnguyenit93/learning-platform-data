# Designing an Expiration Service with Clock and Repeatable Tests

## 1. Practice Problem

A system creates hold leases with a validity period. When creating a lease, the system needs to record:

- Lease ID.
- Issue timestamp.
- Expiration timestamp.

Afterward, the caller needs to know at the time of inspection whether the lease has expired and how much time remains.

This is a small problem, yet it has common pitfalls: tests that must wait in real time, results that change depending on when the test runs, off-by-one handling at the exact expiration boundary, or a single response using multiple inconsistent "now" values.

We will design a service whose time source is injected via `Clock`, then verify the boundaries using fixed times.

In this exercise, a "hold lease" is just an illustrative data object. The service determines time-based status; it does not build a reservation system, database, or notification job.

## 2. Finalizing the Expiration Contract

Sample policy:

1. The validity duration `lifetime` must be positive.
2. `issuedAt` is obtained from the service's clock when creating the lease.
3. `expiresAt = issuedAt + lifetime`.
4. When `checkedAt < expiresAt`, the lease has not expired.
5. When `checkedAt >= expiresAt`, the lease has expired.
6. The remaining time is floored at `Duration.ZERO`.
7. Invalid inputs or out-of-range additions must fail with an error rather than silently correcting themselves.

The expiration timestamp is an exclusive upper bound. If a lease expires at 10:00:30, then at exactly 10:00:30 it has already expired in terms of time; it does not wait an extra nanosecond.

| Inspection Time | `expired` | `remaining` |
| --- | --- | --- |
| 10:00:00, just issued | `false` | 30 seconds |
| 10:00:29.999999999 | `false` | 1 nanosecond |
| 10:00:30 | `true` | 0 |
| After 10:00:30 | `true` | 0 |

This exercise only considers expiration conditions. States such as canceled, used, or not yet eligible for activation are separate business conditions; do not conflate them into a single time comparison.

## 3. Choosing Instant, Duration, and Clock

### 3.1. Instant for Timestamps

[Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html) represents a point on the timeline. It is suitable for `issuedAt`, `expiresAt`, and `checkedAt` when expiration is based on elapsed time.

There is no need to use `LocalDateTime` and implicitly treat it as UTC. Lacking an offset or zone on a local value makes expiration timestamps hard to interpret across environments.

A time zone can be used to display the deadline to users, but it does not change the instant that the deadline represents.

### 3.2. Duration for Validity Length

[Duration](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html) represents an amount of time in seconds and nanoseconds. For example, `Duration.ofSeconds(30)` expresses the unit more clearly than an unnamed number `30`.

A `Duration` can be zero or negative, so it must be validated against the policy. This exercise chooses to reject both. Another system might allow a zero lifetime for immediate expiration, but that requires a different contract and separate tests.

This is a deadline after a duration. Rules like "end of the third business day" or "end of the month in the customer's zone" require calendar calculations and different policies, and cannot be directly replaced by a fixed `Duration`.

### 3.3. Clock as a Replaceable Time Source

[Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html) lets you provide how the current instant is obtained instead of calling the system clock directly everywhere.

The constructor signature:

```java
ExpirationService(Clock clock);
```

makes the service's dependency on a time source explicit. In production, the application wiring layer can supply `Clock.systemUTC()`. In tests, supply `Clock.fixed(...)` or `Clock.offset(...)`.

The service does not need to know whether the clock comes from the system, a fixed value, or another controlled source. It simply calls `clock.instant()`.

## 4. Why Not Call Instant.now() Directly Inside?

A method that reads system time implicitly has a hidden input:

```java
// Illustrates hidden dependency on system time:
Instant issuedAt = Instant.now();
```

Calling it with the same arguments at two different times produces two different timestamps. That is what you want in production, but it makes boundary testing hard to control.

A test like "create a 100-millisecond lease and sleep for 150 milliseconds" depends on machine speed, system load, and thread scheduling. It also wastes real wall-clock time even though the logic is just a comparison.

With an injected `Clock`, tests can place time immediately before, at, or after the expiration boundary. There is no need to sleep, mutate the global time zone, or intercept static methods.

Constructor dependency injection is enough for a plain Java example; you do not need a framework to get this benefit.

## 5. Designing the Objects

We use three components:

| Component | Responsibility |
| --- | --- |
| `Lease` | Holds the lease ID and timestamps; validates stored data |
| `ExpirationService` | Issues leases and computes status using `Clock` |
| `ExpiryView` | Returns a result snapshot containing the inspection time, status, and remaining duration |

`Lease` and `ExpiryView` are records. Their time fields use immutable types, ensuring results cannot be mutated silently after being returned.

### 5.1. Read "now" Only Once per Operation

When issuing, read `issuedAt` once and compute `expiresAt` from that exact instant.

When inspecting, read `checkedAt` once and use it for both `expired` and `remaining`. If you read the clock separately for each field, execution can cross the boundary between the two calls:

- The first read reports not expired.
- The second read is past the deadline and yields a negative or zero remaining duration.

An `ExpiryView` built from a single `checkedAt` avoids self-contradictory snapshots. Returning `checkedAt` also tells the caller when the observed state was captured.

It does not freeze time after the method returns. The result is a snapshot, not a guarantee that the state will still hold when another operation runs later.

## 6. Complete Java 17+ Program

Save as `ClockExpiryPractice.java`:

```java
import java.time.Clock;
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Objects;

public class ClockExpiryPractice {
    record Lease(String id, Instant issuedAt, Instant expiresAt) {
        Lease {
            Objects.requireNonNull(id);
            Objects.requireNonNull(issuedAt);
            Objects.requireNonNull(expiresAt);
            if (id.isBlank()) {
                throw new IllegalArgumentException("Blank lease ID");
            }
            if (!expiresAt.isAfter(issuedAt)) {
                throw new IllegalArgumentException(
                        "Expiry must be after issue time");
            }
        }
    }

    record ExpiryView(
            Instant checkedAt, boolean expired, Duration remaining) {}

    static final class ExpirationService {
        private final Clock clock;

        ExpirationService(Clock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        Lease issue(String id, Duration lifetime) {
            Objects.requireNonNull(lifetime);
            if (lifetime.isZero() || lifetime.isNegative()) {
                throw new IllegalArgumentException("Lifetime must be positive");
            }
            Instant issuedAt = clock.instant();
            Instant expiresAt = issuedAt.plus(lifetime);
            return new Lease(id, issuedAt, expiresAt);
        }

        ExpiryView inspect(Lease lease) {
            Objects.requireNonNull(lease);
            Instant checkedAt = clock.instant();
            boolean expired = !checkedAt.isBefore(lease.expiresAt());
            Duration remaining = expired
                    ? Duration.ZERO
                    : Duration.between(checkedAt, lease.expiresAt());
            return new ExpiryView(checkedAt, expired, remaining);
        }
    }

    static int checks;

    static void check(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label);
        }
        checks++;
        System.out.println("PASS " + label);
    }

    static void expectThrows(
            String label,
            Class<? extends RuntimeException> expectedType,
            Runnable operation) {
        try {
            operation.run();
        } catch (RuntimeException ex) {
            check(label, expectedType.isInstance(ex));
            return;
        }
        throw new AssertionError(label + ": no exception");
    }

    public static void main(String[] args) {
        Instant origin = Instant.parse("2024-06-01T10:00:00Z");
        Clock fixed = Clock.fixed(origin, ZoneOffset.UTC);
        ExpirationService issuer = new ExpirationService(fixed);
        Lease lease = issuer.issue("hold-A", Duration.ofSeconds(30));

        check("issue time is controlled", lease.issuedAt().equals(origin));
        check("expiry uses lifetime",
                lease.expiresAt().equals(origin.plusSeconds(30)));

        ExpiryView atStart = issuer.inspect(lease);
        check("not expired at issue", !atStart.expired());
        check("initial remaining time",
                atStart.remaining().equals(Duration.ofSeconds(30)));
        check("fixed clock gives repeatable view",
                atStart.equals(issuer.inspect(lease)));

        Clock justBefore = Clock.fixed(
                lease.expiresAt().minusNanos(1), ZoneOffset.UTC);
        ExpiryView before = new ExpirationService(justBefore).inspect(lease);
        check("valid one nanosecond before", !before.expired());
        check("one nanosecond remains",
                before.remaining().equals(Duration.ofNanos(1)));

        Clock exactDeadline = Clock.offset(fixed, Duration.ofSeconds(30));
        ExpiryView exact =
                new ExpirationService(exactDeadline).inspect(lease);
        check("expired exactly at deadline", exact.expired());
        check("zero remains at deadline",
                exact.remaining().equals(Duration.ZERO));

        Clock justAfter = Clock.fixed(
                lease.expiresAt().plusNanos(1), ZoneOffset.UTC);
        ExpiryView after = new ExpirationService(justAfter).inspect(lease);
        check("expired after deadline", after.expired());
        check("remaining is not negative",
                after.remaining().equals(Duration.ZERO));

        Clock sameInstantDifferentZone =
                fixed.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        ExpirationService otherZone =
                new ExpirationService(sameInstantDifferentZone);
        check("zone does not change absolute expiry",
                atStart.equals(otherZone.inspect(lease)));

        expectThrows("zero lifetime rejected",
                IllegalArgumentException.class,
                () -> issuer.issue("hold-B", Duration.ZERO));
        expectThrows("negative lifetime rejected",
                IllegalArgumentException.class,
                () -> issuer.issue("hold-C", Duration.ofSeconds(-1)));
        expectThrows("reversed stored times rejected",
                IllegalArgumentException.class,
                () -> new Lease("hold-D", origin, origin.minusSeconds(1)));

        ExpirationService atLimit = new ExpirationService(
                Clock.fixed(Instant.MAX, ZoneOffset.UTC));
        expectThrows("instant range overflow reported",
                DateTimeException.class,
                () -> atLimit.issue("hold-E", Duration.ofSeconds(1)));

        System.out.println("checks = " + checks);
        System.out.println("expiresAt = " + lease.expiresAt());
    }
}
```

Compile and run:

```shell
javac --release 17 ClockExpiryPractice.java
java ClockExpiryPractice
```

Stdout:

```text
PASS issue time is controlled
PASS expiry uses lifetime
PASS not expired at issue
PASS initial remaining time
PASS fixed clock gives repeatable view
PASS valid one nanosecond before
PASS one nanosecond remains
PASS expired exactly at deadline
PASS zero remains at deadline
PASS expired after deadline
PASS remaining is not negative
PASS zone does not change absolute expiry
PASS zero lifetime rejected
PASS negative lifetime rejected
PASS reversed stored times rejected
PASS instant range overflow reported
checks = 16
expiresAt = 2024-06-01T10:00:30Z
```

If a check fails, `check` throws `AssertionError` and the program fails. It does not just print a value and assume it is correct.

`expectThrows` verifies that invalid inputs or operations actually throw the expected exception type. A call that fails to throw when it should be rejected will fail the check.

The example uses only the standard library so it runs directly with `javac`/`java`. In a project using JUnit, each case can be moved into a corresponding test method while keeping the same `Clock` inputs and expected results.

## 7. Reading the Checks by Goal

### 7.1. Issuing at a Known Timestamp

`Clock.fixed(origin, ZoneOffset.UTC)` always returns the same `origin`. The service issues the lease with `issuedAt` equal to that exact value and `expiresAt` equal to `origin.plusSeconds(30)`.

The check does not compare "close to current real time." It compares against a deterministic timestamp, so running it in any year produces the same result.

### 7.2. One Nanosecond Before the Deadline

Set the clock to `expiresAt.minusNanos(1)`:

- `expired` must be `false`.
- `remaining` must equal `Duration.ofNanos(1)`.

This case tests the exact comparison operator at the boundary. If the implementation truncates to seconds or only looks at the date, it can produce the wrong result.

This is an in-memory check on Java values. If deadlines pass through a database that only stores microseconds or milliseconds, integration tests must account for the actual precision of the column and driver rather than assuming stored data preserves every nanosecond of the input.

### 7.3. Exactly at the Deadline

`Clock.offset(fixed, Duration.ofSeconds(30))` yields an instant equal to `expiresAt` because the `fixed` base does not move.

The condition:

```java
boolean expired = !checkedAt.isBefore(expiresAt);
```

includes equality. Writing `checkedAt.isAfter(expiresAt)` would still treat the exact deadline as not expired, violating the exercise contract.

### 7.4. After the Deadline

One nanosecond after the deadline, `expired` is still `true`, while `remaining` is `ZERO` rather than a negative duration.

Flooring at zero must not be used to hide broken status logic. Both fields are computed from the same `checkedAt` according to the contract.

### 7.5. Same Instant, Different Clock Zone

`fixed.withZone(Asia/Ho_Chi_Minh)` changes the zone used to interpret local date-time values while keeping the same instant on the fixed clock.

Because the service only uses `clock.instant()`, the status and remaining duration do not change. If changing the zone alters the absolute deadline, inspect the code for something like `LocalDateTime.now(clock)` being misinterpreted with the wrong zone.

### 7.6. Invalid Durations and Range Overflow

`Duration.ZERO` and negative durations are rejected immediately per the sample policy. Timestamps loaded into `Lease` must also satisfy `expiresAt > issuedAt`.

An excessively large addition can overflow the `Instant` range. Testing near `Instant.MAX` confirms that an error is reported rather than turning into another deadline or a default value.

In a real application, you should usually enforce a reasonable domain-specific duration limit well before reaching the extreme bounds of Java types.

## 8. Understanding fixed, offset, and System Clocks

| Factory Method | Behavior |
| --- | --- |
| `Clock.systemUTC()` | Reads system time in the UTC zone |
| `Clock.fixed(instant, zone)` | Always returns a fixed instant |
| `Clock.offset(base, duration)` | Base clock's instant plus an offset |
| `clock.withZone(zone)` | Same time source with the specified zone interpretation |

`Clock.offset` does not turn into a clock you can "tick" through an API. If the base is fixed, the offset clock is also fixed; if the base tracks the system clock, the offset clock advances with it.

Do not change the machine's system clock to test a service. Nor should you mutate a shared global `Clock` variable across parallel tests if they need different timestamps.

This exercise creates small service instances with their own clocks for each scenario. They all inspect the same immutable `Lease`, so there is no need to modify an already-issued object to simulate the passage of time.

## 9. Wiring into Production Without Changing Logic

At the composition root, you can wire:

```java
ExpirationService service =
        new ExpirationService(Clock.systemUTC());
```

This is an example of dependency wiring. The business logic in `issue` and `inspect` does not change when switching between the system clock and a test clock.

If a framework manages objects, you can provide a shared `Clock` through its dependency injection mechanism. The key invariant is that the service must not create `Clock.systemUTC()` or call `Instant.now()` internally and ignore the injected dependency.

Avoid having a utility method deep in the call chain read system time on its own. That is still a hidden time source and can make tests non-repeatable even when the top-level service accepts a `Clock`.

When formatting the deadline for display, apply the user's display time zone separately. Do not alter `expiresAt` just to make a formatted string match local time.

## 10. Storage and Handling Expiration

### 10.1. Store the Decided Timestamp

If leases must survive restarts, you typically need to store `issuedAt` and `expiresAt` (or equivalent data per the contract). Do not store only the TTL and recompute `now + TTL` on every read; that renews the lease on every read.

If the configured TTL changes after a lease is issued, you must decide whether existing leases keep their original deadline or are updated under an explicit policy. Do not let reading a new configuration silently change the meaning of stored data.

### 10.2. Cleanup Jobs Differ from Logical Validity

A cleanup job for expired leases may run periodically and lag behind the expiration timestamp. A record still existing in the database does not mean it is still valid.

When handling a request to use a lease, check the time condition per the contract at the point of decision. Cleanup jobs are only for storage management if the design chooses to use them that way.

Similarly, a scheduled timer does not replace checking expiration at the point of use. Jobs can be delayed, systems can restart, or work can be retried.

### 10.3. Snapshots Do Not Guarantee Atomicity

`inspect` returns a snapshot at `checkedAt`. If the application checks and then performs an important action after a delay, the deadline may have passed in between.

If requirements demand consistent checking and state updates under concurrency, you must design conditional updates, transactions, or the appropriate execution mechanism. `Clock` controls the time source; it does not provide database atomicity.

This exercise does not implement that storage layer; this is a boundary to recognize when integrating time logic into a full service.

## 11. Real Clocks Can Be Adjusted

`Clock` does not guarantee that every read is strictly greater than the previous one. The system clock can be synchronized or adjusted.

Under a "compare current time against `expiresAt`" contract, if time steps backward, the remaining duration can increase and a later inspection can yield a different status from an earlier one. That is a consequence of the time source and comparison policy, not a bug in `Clock.fixed`.

If the business requires that once marked expired a lease can never revert to an earlier state, you must persist an irreversible state transition per the contract. Do not expect a pure time comparison to remember previously observed history.

For measuring an elapsed interval within the same process, you may need an appropriate elapsed-time source. For absolute deadlines stored and shared across processes, `Instant` serves a different role. Do not mix the two just because both are called "time."

In a multi-machine system, injecting `Clock` also does not synchronize clocks across nodes. The authoritative time source and where expiration decisions are made must be defined in the deployment architecture.

## 12. Expanding Tests While Keeping Them Repeatable

Scenarios to add as you develop further:

| Scenario | What to Verify |
| --- | --- |
| Blank or whitespace-only ID | Rejected per constraint |
| Missing `Clock` or `Duration` | Clear input error |
| Very small TTL | Not truncated to seconds |
| Large but domain-valid TTL | Deadline computed accurately |
| Clock before stored issue time | Clarify contract without inventing activation states |
| Two reads on the same fixed clock | Identical results |
| Read after DB write | Deadline matches documented precision |
| Renewal | Clarify whether computed from now or from old deadline |

Do not mutate `expiresAt` directly in every test and skip the issuance path. Both deadline calculation and deadline evaluation need to be verified.

If you need to simulate multiple time steps within the same service, you can provide a controllable test clock. That implementation must have a clear contract and be safe under concurrent use. For the independent cases in this exercise, `fixed` and `offset` are sufficient, so there is no need to build an extra complex class.

Do not share mutable test clock state across tests running in parallel if advancing time in one test can affect another.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `Instant.now()` scattered through the service | Hidden time input | Inject `Clock` and use it consistently |
| Testing with real-time sleep | Slow and dependent on OS scheduling | Use fixed timestamps |
| Using `isAfter` for an expire-at-deadline contract | Exact deadline is still accepted | Use a condition that includes equality |
| Reading the clock separately for status and remaining | Snapshot can contradict itself | Read `checkedAt` once |
| Returning negative remaining time | Caller has to infer status | Floor at zero per contract |
| Storing only TTL and recomputing from now on read | Deadline slides continuously | Persist the decided expiration timestamp |
| Using local date-time without a zone as an absolute deadline | Hard to interpret across environments | Use `Instant` for absolute timestamps |
| Relying on cleanup jobs as the only validity check | Expired leases can still be used | Check at the point of use |
| Assuming `Clock` gives atomicity or multi-node sync | Concurrency bugs missed | Design decision/storage layer separately |
| Loosening tolerances arbitrarily to make tests pass | Hides boundary bugs | Verify exact boundary per contract |

## 14. Practice Exercises

1. Rewrite the exact-deadline case in JUnit if the project already uses JUnit. Keep the rule that `checkedAt == expiresAt` is expired.
2. Add checks for a blank ID and a one-nanosecond TTL.
3. Add a method that returns only the expired status while still using the `Clock` dependency rather than calling the system clock directly.
4. Design renewal under two policies: calculated from the renewal time and added to the old deadline. Give an example where they differ; do not pick one implicitly.
5. Store and read `Lease` through a real data store and verify timestamp precision. Distinguish sub-second truncation bugs from time-zone bugs.
6. Design a test for when the clock steps backward. State clearly whether expiration status is a pure function of current time or a recorded irreversible state.
7. Add a "canceled" state and explain why it should not be treated as synonymous with expired.
8. Explain how to check and update a lease when two concurrent requests try to use it, while keeping the time-comparison logic testable.

An easily testable expiration service turns time into an explicit dependency and defines its boundaries precisely. `Clock` lets you control that input; `Instant`, `Duration`, and before/at/after boundary checks turn the contract into repeatable behavior.
