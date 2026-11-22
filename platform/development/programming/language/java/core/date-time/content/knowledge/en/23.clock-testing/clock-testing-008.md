# Testing Before, At, and After Expiration

## 1. The Exact Boundary Case Is a Contract Decision

A feature may work correctly hours before expiration and days after expiration, yet still fail right at the boundary. The cause is often confusing "after the expiration time" with "from the expiration time onward".

Before writing tests, choose a clear rule. In this lesson:

> A value is still valid when `now < expiresAt`; it is expired when `now >= expiresAt`.

Therefore, right at `expiresAt` it is already expired. There is no default `Clock` rule that decides this automatically; it is a choice made by the feature.

| Position of now | Still valid? | Expired? |
|---|---|---|
| Before `expiresAt` | Yes | No |
| Equal to `expiresAt` | No | Yes |
| After `expiresAt` | No | Yes |

These three rows are the minimum meaningful test suite for this boundary condition. The equality case catches an off-by-one comparison operator error that the other two cases cannot distinguish.

## 2. Expressing the Condition with Instant

When the expiration is a global instant in time, use `Instant` for both `now` and `expiresAt` to compare them on the same timeline:

```java
Instant now = clock.instant();
boolean expired = !now.isBefore(expiresAt);
```

`isBefore` is only true when strictly before. Its negation covers both equal to and after.

An equivalent expression is `now.compareTo(expiresAt) >= 0`. Choose whichever is easier to read against the contract; there is no need to use multiple equivalent expressions simultaneously in production code.

Common mistake:

```java
boolean expired = now.isAfter(expiresAt);
```

Under this lesson's contract, the expression above misses the equality case. It is only appropriate if the feature's rule genuinely allows the value to remain valid right at the expiration instant.

Do not test by comparing date-time strings, taking only the date part, or comparing `getEpochSecond()` if nanoseconds are significant. Those approaches can discard information right at the boundary you need to verify.

## 3. Controlling now with Clock.fixed

Instead of calling the real clock and trying to run tests right before expiration, create three fixed sources:

```java
Clock before = Clock.fixed(expiresAt.minusNanos(1), ZoneOffset.UTC);
Clock exactly = Clock.fixed(expiresAt, ZoneOffset.UTC);
Clock after = Clock.fixed(expiresAt.plusNanos(1), ZoneOffset.UTC);
```

These are three independent clocks with the same time-zone specification. They do not advance from before to equal to after when read. Each case must pass the right clock into the feature under test.

There is no need for `Thread.sleep`, changing the operating system clock, or waiting for a future date. If a test fails, it can be re-run with the exact same time data.

The expiration timestamp must be kept constant across all three cases. If each test case recomputes `expiresAt = clock.instant().plus(...)`, you are shifting the deadline along with the test clock, which can make the state always "not expired" and render the test meaningless.

For a feature that creates an expiration from a duration, test the two responsibilities separately: whether creation computes the deadline correctly from the issue timestamp, and whether validation compares correctly against the created deadline.

## 4. Choosing Test Offsets Based on Actual Precision

In pure code using `Instant`, 1 nanosecond before/after is the tightest boundary check for the comparison operator. It does not mean real-world clock sources or databases always have nanosecond precision.

| Test layer | Before/after offsets to watch for |
|---|---|
| Pure function working directly with Instant | Can use ±1 ns to verify the exact comparison |
| Data passing through storage that only keeps milliseconds | Test the boundary at millisecond resolution and reading/writing fractional parts |
| Protocol transmitting only seconds | Define the truncation/rounding rule for fractional parts, then test against that contract |
| Source truncated by Clock.tick | Test the impact of the source potentially still reporting the old timestamp |

Do not use an arbitrary tolerance like "a difference under one second is considered equal" to make tests pass easily when the real rule has no tolerance window. If the product has a grace period, model it explicitly as a separate condition.

Also, do not only test days before and after. Cases far from the boundary can be useful, but they do not replace the exact-boundary and near-boundary cases at the supported precision.

## 5. Reading Time Once for One Decision

If you need to return both the status and the check timestamp, capture `now` once and reuse the same value:

```java
Instant checkedAt = clock.instant();
boolean expired = !checkedAt.isBefore(expiresAt);
```

Do not call the time source separately for each field and assume they happened at the same instant. With a real clock, the first read could be before expiration while the second is after. A single result record using two timestamps can contradict itself.

This does not turn the check into a lock or transaction for a subsequent operation. If the feature must guarantee the state is still valid when writing data, you need to identify the right decision point and coordinate with that operation. The scope of testing in this lesson is classification based on a single captured timestamp.

## 6. Local-Date Expirations Require a Boundary Resolution Step

A requirement like "valid through the end of October 25, 2026 in Vietnam" is not directly an `Instant`: it consists of a date and the feature's time zone.

A clear representation is an **exclusive** upper bound at the start of the next day:

```java
Instant endExclusive = lastValidDate.plusDays(1)
        .atStartOfDay(businessZone)
        .toInstant();
```

With `lastValidDate = 2026-10-25` and zone `Asia/Ho_Chi_Minh`, the boundary is `2026-10-25T17:00:00Z`, which corresponds to 00:00 on October 26 in that zone. Immediately before the boundary it is still valid; at the boundary it is expired under the same condition `now >= endExclusive`.

This approach avoids manually constructing a timestamp like "23:59:59.999..." with a precision that might not match storage. `atStartOfDay(zone)` also follows the valid start-of-day instant according to the zone's rules; it does not assume every zone and every day has a valid 00:00 or is exactly 24 hours long.

Choose the business time zone explicitly. Do not let the host machine's time zone decide the boundary of a date that the feature defined in another zone.

## 7. Complete Runnable Test Program

Save the following code to `ExpirationBoundaryDemo.java`. The program uses Java 17 or later and requires no external libraries. It includes automated checks: if a result differs from expectations, `AssertionError` is thrown and the program fails, rather than just printing output for the reader to guess.

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Objects;

public class ExpirationBoundaryDemo {
    record CheckResult(Instant checkedAt, boolean expired) {}

    static final class ExpirationService {
        private final Clock clock;

        ExpirationService(Clock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        CheckResult check(Instant expiresAt) {
            Objects.requireNonNull(expiresAt);
            Instant now = clock.instant();
            return new CheckResult(now, !now.isBefore(expiresAt));
        }
    }

    record BoundaryCase(String label, Instant now, boolean expectedExpired) {}

    public static void main(String[] args) {
        Instant expiresAt = Instant.parse("2026-10-25T10:00:00Z");
        for (BoundaryCase test : new BoundaryCase[]{
                new BoundaryCase("before", expiresAt.minusNanos(1), false),
                new BoundaryCase("exactly", expiresAt, true),
                new BoundaryCase("after", expiresAt.plusNanos(1), true)
        }) {
            verify(test, expiresAt, ZoneOffset.UTC);
        }

        Clock utc = Clock.fixed(expiresAt, ZoneOffset.UTC);
        Clock vietnam = utc.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        boolean utcResult = new ExpirationService(utc).check(expiresAt).expired();
        boolean vnResult =
                new ExpirationService(vietnam).check(expiresAt).expired();
        if (utcResult != vnResult) {
            throw new AssertionError("instant comparison must be zone independent");
        }
        System.out.println("sameInstantDifferentZone=PASS");

        LocalDate lastValidDate = LocalDate.of(2026, 10, 25);
        ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
        Instant endExclusive = lastValidDate.plusDays(1)
                .atStartOfDay(businessZone).toInstant();
        System.out.println("endExclusive=" + endExclusive);

        verify(new BoundaryCase("dayBeforeEnd",
                endExclusive.minusNanos(1), false), endExclusive, businessZone);
        verify(new BoundaryCase("dayExactlyEnd",
                endExclusive, true), endExclusive, businessZone);
        verify(new BoundaryCase("dayAfterEnd",
                endExclusive.plusNanos(1), true), endExclusive, businessZone);
        System.out.println("allChecks=PASS");
    }

    private static void verify(BoundaryCase test,
                               Instant expiresAt,
                               ZoneId zone) {
        Clock fixed = Clock.fixed(test.now(), zone);
        CheckResult actual = new ExpirationService(fixed).check(expiresAt);
        if (actual.expired() != test.expectedExpired()
                || !actual.checkedAt().equals(test.now())) {
            throw new AssertionError("failed case: " + test.label());
        }
        System.out.println(test.label() + " expired=" + actual.expired());
    }
}
```

Compile and run:

```shell
javac ExpirationBoundaryDemo.java
java ExpirationBoundaryDemo
```

Expected output:

```text
before expired=false
exactly expired=true
after expired=true
sameInstantDifferentZone=PASS
endExclusive=2026-10-25T17:00:00Z
dayBeforeEnd expired=false
dayExactlyEnd expired=true
dayAfterEnd expired=true
allChecks=PASS
```

The checks use `if` statements and throw `AssertionError` directly, so there is no need to enable the `-ea` flag as with Java's `assert` keyword.

`verify` checks both the status and the `checkedAt` timestamp. Expectations are listed explicitly in the `BoundaryCase` data, rather than being recomputed using the same expression the class under test uses.

The time-zone change case keeps the same `Instant` and the same deadline. The expiration result must remain the same because the comparison only uses instants; the time zone affects the step that derives the boundary from a local date, not the before/equal/after relationship between two resolved `Instant` values.

## 8. Bringing the Same Structure into a Project Test Suite

When a project uses JUnit, the three before/equal/after rows can become a parameterized test. Keep the same principles from the program:

- Each case has a `Clock.fixed` and a clearly defined expiration timestamp.
- Expectations are written according to the business rule, without copying the algorithm into the expectation setup.
- A wrong comparison operator must cause the test to fail.
- Do not use real time or sleep to cross the boundary.
- The time source of the object under test is injected, not bypassed in another code path via a no-argument `Instant.now()`.

This example tests a pure decision function. If the expiration is stored in a database, separate integration tests are needed for precision, type conversion, and the data actually read back. If a scheduled job deletes expired data, the correctness of the comparison does not by itself prove the job runs on schedule.

Only add those cases when they are part of the feature's contract. Do not stretch a simple boundary test into an end-to-end system test just to verify one comparison operator.

## 9. Common Mistakes When Testing Expiration

| Mistake | Why is it easy to miss discrepancies? |
|---|---|
| Only testing before and after, not equal | Cannot distinguish `>` from `>=` |
| Using `Clock.systemUTC()` for tests needing a fixed timestamp | Result depends on when the test runs |
| Recomputing the expiration from now in every case | The boundary moves along with the test data |
| Using ±1 ms when data has nanoseconds, or vice versa | May not test the actual precision contract |
| Converting date/time to strings for comparison | May lose fractional parts or depend on format/time zone |
| Only printing results without checking expectations | Program still exits successfully when results are wrong |
| Allowing tolerance to skip the equality case | Blurs the exact boundary being defined |

Do not automatically treat a `null` expiration as meaning "forever" if the contract does not allow it. In this program, the expiration is required to have a value; an unlimited-expiration design must be modeled and tested separately.

## 10. Practice

1. Intentionally change the condition in `ExpirationService` to `now.isAfter(expiresAt)`. Re-run and verify that the `exactly` case fails. This confirms that the test dataset catches the intended boundary bug.
2. Change the contract to "still valid at the exact expiration time". Intentionally update both the condition and the expectations at the boundary; do not just tweak code until the old rows pass.
3. Suppose storage only keeps milliseconds. Add a simulated write/read round-trip following the chosen precision policy, then re-determine the observable near-boundary timestamps at that layer.
4. Change the time zone of the date-based expiration to another zone, recompute `endExclusive`, and keep the before/equal/after tests around that new boundary.

References: [Clock — fixed](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html#fixed(java.time.Instant,java.time.ZoneId)), [Instant — isBefore/isAfter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html), and [LocalDate — atStartOfDay](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#atStartOfDay(java.time.ZoneId)) in Java SE 21.
