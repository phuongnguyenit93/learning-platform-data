# Why calling `now()` directly makes tests hard to repeat

## 1. "Now" is a hidden input

Suppose a usage code is only valid before an expiration timestamp. A function takes `expiresAt` and calls `Instant.now()` internally to decide whether it can still be used. Looking at the signature, we see only one input; in reality, the result also depends on the point in time returned by the system clock when the function runs.

If you run the same test today and next week, or rerun it after a wait, the execution branch can differ even with identical input data. This is a hidden dependency on the execution environment.

`now()` is not a buggy call. The testing problem lies in the fact that the business-decision logic fetches real time on its own, which the test has no control over. [Java SE 21 — Instant.now()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html#now()) also notes the difference between using the system clock directly and using the overload that accepts a clock source.

A repeatable test needs to control the inputs that affect the outcome, including "now". Not every test has to freeze time, but when you need to test the exact boundary before/at/after a point in time, there must be a way to choose the point of observation.

## 2. Common forms of non-repeatability

### Passing when written, failing on another day

An illustrative snippet inside a method:

```java
boolean expired = !Instant.now().isBefore(expiresAt);
```

If `expiresAt` is hardcoded in the test while "now" is real time, the test does not fix both sides of the comparison. Once past the expiration date, the previously written expectation may no longer hold. Updating the expectation every year only masks the root cause of depending on the clock.

### Two calls are not the same observation

For example, a test records `before = Instant.now()`, calls a function to create a record, and then asserts that `createdAt` must equal `before`. In the interval between the two time reads, time may have already elapsed; clock precision and execution time do not allow relying on equality.

Even within a single business operation, calling `LocalDate.now()` multiple times around midnight can return two different dates. If the operation requires using a consistent point in time, you need to capture the timestamp once and reuse it. Reading it once ensures consistency within the operation; it does not by itself let tests control that point in time.

### Same instant, different zone, different date

`LocalDate.now()` uses the system's default clock and time zone, according to [Java SE 21 — LocalDate.now()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#now()). A due-date test might pass on the author's machine but fail in an environment using a different time zone, especially near a day boundary.

`LocalDate.now(zone)` makes the time zone explicit but still reads real time. It addresses the zone dependency, not the point-in-time dependency. `Instant.now()` does not have the issue of choosing a local date when returning an `Instant`, yet it still depends on the system clock.

## 3. Making the time source an explicit dependency

There are two simple approaches depending on application structure:

| Need | How to pass time in |
| --- | --- |
| A calculation that only needs one point in time to compare | Pass `Instant now` or a determined date into the function |
| A service object that needs to read the time across multiple operations | Receive a `Clock` via constructor or parameter |

For example, a pure calculation function can take both `expiresAt` and `observedNow`; the caller is responsible for deciding the observation timestamp. For a service object, `Clock` is a replaceable time source. [Java SE 21 — Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html) is designed so an application can use the system clock or a controlled clock in tests.

In production, you can provide `Clock.systemUTC()` if the rule uses UTC instants. In tests, `Clock.fixed(instant, zone)` always provides the same chosen point in time. Calls such as `Instant.now(clock)` or `LocalDate.now(clock)` still use the name `now`, but "now" here comes from the passed-in source.

## 4. Choosing the boundary contract before testing

In this example, the usage code expires when `now >= expiresAt`. In other words, only points in time **before** the deadline remain valid. Therefore, the expression is:

```java
return !observedNow.isBefore(expiresAt);
```

If you only used `observedNow.isAfter(expiresAt)`, being exactly at the expiration timestamp would not yet be considered expired. That is a different contract, not a difference caused by the clock. Tests must verify the exact comparison relation that was chosen.

The three cases below use `Instant`, so they can pick points one nanosecond apart from the deadline. This tests the application's comparison logic, not a claim that a physical clock has one-nanosecond precision.

## 5. Complete verification program

Save the code to `RepeatableNowDemo.java`. The program uses Java 17 or later and requires no external testing library. Each failed condition throws an `AssertionError`, so the checks still run even without enabling the `-ea` flag:

```java
import java.time.*;
import java.util.Objects;

public class RepeatableNowDemo {
    static final class ExpiryPolicy {
        private final Clock clock;

        ExpiryPolicy(Clock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        boolean isExpired(Instant expiresAt) {
            Instant observedNow = clock.instant();
            return !observedNow.isBefore(expiresAt);
        }
    }

    private static void check(String label, Instant now,
                              Instant deadline, boolean expected) {
        ExpiryPolicy policy = new ExpiryPolicy(Clock.fixed(now, ZoneOffset.UTC));
        boolean actual = policy.isExpired(deadline);
        if (actual != expected) {
            throw new AssertionError(label + ": expected " + expected
                    + ", got " + actual);
        }
        System.out.println(label + " = " + actual);
    }

    public static void main(String[] args) {
        Instant deadline = Instant.parse("2025-06-10T00:00:00Z");
        check("before deadline", deadline.minusNanos(1), deadline, false);
        check("at deadline", deadline, deadline, true);
        check("after deadline", deadline.plusNanos(1), deadline, true);

        Instant shared = Instant.parse("2025-06-09T18:00:00Z");
        Clock utc = Clock.fixed(shared, ZoneOffset.UTC);
        Clock hcm = utc.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println("UTC date = " + LocalDate.now(utc));
        System.out.println("HCM date = " + LocalDate.now(hcm));
        System.out.println("same instant = "
                + Instant.now(utc).equals(Instant.now(hcm)));
        System.out.println("fixed reads equal = "
                + Instant.now(utc).equals(Instant.now(utc)));

        System.out.println("all checks passed");
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 RepeatableNowDemo.java
java RepeatableNowDemo
```

Output:

```text
before deadline = false
at deadline = true
after deadline = true
UTC date = 2025-06-09
HCM date = 2025-06-10
same instant = true
fixed reads equal = true
all checks passed
```

## 6. Why is this program repeatable?

### Both the observation point and the deadline are decided by the test

`check()` creates `Clock.fixed(now, UTC)` for each case. `isExpired()` uses the provided clock; it does not access any other system time source. Therefore, the same `now` and `deadline` yield the same before/at/after-deadline result on every run.

There is no need to wait until 2025 or change the machine's clock. Dates in the data are merely points in time for the program to compute with; they do not require real time to reach those points.

### The business rule reads the clock only once

In `isExpired()`, the `observedNow` variable stores a single observation for the comparison. For multi-branch logic sharing "now", a similar structure prevents different branches from accidentally reading different points in time.

Do not infer that the entire application may read the clock only once. A long-running operation may need to observe multiple points in time as required; what matters is clarifying when a single consistent point is needed and when a new point in time should be measured/observed.

### Time zone is tested independently of the instant

`utc` and `hcm` in the program both return `2025-06-09T18:00:00Z`. However, the UTC date is June 9, while the date in `Asia/Ho_Chi_Minh` has already moved to June 10. `same instant = true` shows that the date change is not the clock advancing extra hours, but a different zone interpretation.

Because `isExpired()` only compares `Instant` values, the time zone does not change the outcome of that expiration rule. For date-based rules such as "until the end of the business day", you must first choose the business time zone and corresponding date; do not switch to UTC just to make testing easier if doing so changes the business meaning.

## 7. Applying the same design to production code

Where the service is initialized, you can supply the system time source. The following snippet illustrates wiring the object in the same scope where `ExpiryPolicy` is accessible:

```java
ExpiryPolicy production = new ExpiryPolicy(Clock.systemUTC());
```

`systemUTC()` still runs on system time; it only configures the UTC zone for reads that require a zone. When using local-date rules, you can supply `Clock.system(businessZone)` with an explicitly defined `businessZone`. You do not need to change the algorithm just to switch between a real clock and a test clock.

Another option is to keep the calculation logic accepting `Instant observedNow`, while the boundary layer reads `clock.instant()` and passes it in. That approach works well when you want the calculation logic to have no knowledge of how "now" is obtained. Choose a level of separation appropriate to the scope; there is no need to build a large time-management framework just for a single comparison.

Make sure all relevant branches use the passed-in source. If one branch still calls `Instant.now()` or creates `Clock.systemUTC()` internally, the test's fixed clock cannot control that branch.

## 8. Workarounds that do not solve the real problem

**Waiting with `Thread.sleep()`.** This makes tests slow and dependent on OS scheduling; it does not help hit the exact deadline boundary. With `Clock.fixed()`, waiting any amount of time will not advance that clock on its own. To test another point in time, supply a different fixed clock or design a controllable time source as needed.

**Changing the JVM-wide default time zone in tests.** This affects shared state and can cause interference between tests running in parallel. Passing the zone/clock explicitly narrows the dependency right to where it is needed.

**Simply rounding or adding a tolerance window to every comparison.** A tolerance window can be appropriate in integration tests that genuinely observe system timestamps. However, it does not replace testing exact deadline-boundary or day-rollover rules. Do not use a tolerance to mask an unclear boundary contract.

**Re-evaluating the same `now()` expression instead of testing behavior.** If the expectation also reads real time again, both sides can still observe two different points in time. Set a known point in time and verify the resulting branch or expected output value.

## 9. Scope of guarantees and practice exercise

Passing a `Clock` makes the time dependency of the code that uses it controllable. It does not automatically control the time of a database, scheduled jobs, OS timers, or an external service. For tests spanning multiple components, you need to know which component generates the timestamps and which time source is being used.

Exercise: change the expiration contract to "only expired when strictly after the deadline; at the exact deadline it is still valid". Predict the three expected results in order as `false`, `false`, `true`, then update the comparison expression accordingly. Next, keep the original contract and test a business date near midnight across two time zones. These two parts help distinguish comparison-operator bugs from point-in-time/zone selection bugs, rather than lumping everything together as random `now()` failures.
