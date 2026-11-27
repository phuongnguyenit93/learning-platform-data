# Testing Expiration Times with a Fixed Source in Java 17

Time-limited features often have to answer the question: **at the time of checking, is the data still valid or has it expired?** For example: a verification code is only valid for 5 minutes, a password reset link is valid for 30 minutes, a ticket can only be used before departure time, or a subscription expires at a specific point in time.

If code calls `Instant.now()` or `LocalDateTime.now()` directly in many places, test results will depend on the machine's real clock. A test might pass on one run and fail on another once real time passes the expiration mark. Using `Thread.sleep()` to wait for time to pass makes tests slow and flaky.

Java provides `java.time.Clock` to decouple the **time source** from business logic. In testing, `Clock.fixed()` creates a clock that always returns the same point in time. This lets you precisely test states **before expiration, at the exact expiration instant, and after expiration** without waiting for the system clock.

## 1. Why Fix the Time Source When Testing?

Suppose a verification code has an expiration instant `expiresAt`. Simple logic might be written as:

```java
boolean isExpired(Instant expiresAt) {
    return Instant.now().isAfter(expiresAt);
}
```

This snippet has two issues:

1. The method reads time from the system clock itself, making it hard for tests to determine the exact "current" value.
2. `isAfter()` only returns `true` when the current instant is **strictly after** `expiresAt`. If the business rule considers the code expired right when it equals `expiresAt`, the condition above is wrong at the equality boundary.

For example, if the code expires at `10:00:00`, the application needs to make clear:

| Check time | Status under rule "expired when now >= expiresAt" |
| --- | --- |
| 09:59:59 | Still valid |
| 10:00:00 | Expired |
| 10:00:01 | Expired |

A test using real time struggles to reproduce these three situations accurately. `Clock.fixed()` lets you explicitly set the check time to verify each case.

## 2. What Is `Clock`?

`Clock` is an abstraction in the `java.time` package representing a time source and time zone. Instead of forcing business code to call the system clock, we pass a `Clock` into places that need to read time.

Some commonly used factory methods:

| API | Meaning |
| --- | --- |
| `Clock.systemUTC()` | System clock in the UTC zone. |
| `Clock.system(ZoneId)` | System clock in the specified zone. |
| `Clock.fixed(Instant, ZoneId)` | Clock that always returns a fixed instant. |
| `Clock.offset(Clock, Duration)` | Clock returning the base clock's time plus a duration. |
| `Clock.tick(Clock, Duration)` | Clock that truncates time to the specified tick unit. |

For expiration testing, the most important factory method is:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-15T10:00:00Z"),
        ZoneOffset.UTC
);
```

Each call to `fixedClock.instant()` receives the same point in time:

```java
System.out.println(fixedClock.instant());
System.out.println(fixedClock.instant());
```

Output:

```text
2026-11-15T10:00:00Z
2026-11-15T10:00:00Z
```

`Clock.fixed()` does not create a countdown clock. It freezes time so code can be tested against a deterministic reference point. To test a different point in time, create another fixed clock with a different instant.

## 3. Designing Expiration Logic to Accept `Clock` Externally

An important principle is to **inject the time source as a class dependency**, rather than calling `Instant.now()` inside business logic.

For example, create an `AccessPolicy` class:

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class AccessPolicy {

    private final Clock clock;

    public AccessPolicy(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public boolean isExpired(Instant expiresAt) {
        Objects.requireNonNull(expiresAt, "expiresAt");

        Instant now = clock.instant();

        // Expired at or after expiresAt.
        return !now.isBefore(expiresAt);
    }
}
```

The `isExpired()` method gets the current instant from `clock.instant()`. In production code, the clock can be `Clock.systemUTC()`; in tests, the clock can be `Clock.fixed(...)`.

### Why Use `!now.isBefore(expiresAt)`?

The rule chosen in this example is:

```java
expired = now >= expiresAt
```

`Instant` has comparison methods:

- `now.isBefore(expiresAt)`: now is before the expiration time.
- `now.isAfter(expiresAt)`: now is after the expiration time.
- `now.equals(expiresAt)`: both instants are equal.

Thus, the expression `!now.isBefore(expiresAt)` means **now is equal to or after the expiration time**.

You can write this equivalently as:

```java
return now.equals(expiresAt) || now.isAfter(expiresAt);
```

However, negating `isBefore()` is shorter and directly expresses the rule that includes equality.

If business logic specifies expiring only **after** the deadline, excluding equality, you can use `now.isAfter(expiresAt)`. Clarify the business contract before writing the condition.

## 4. Using `Clock.fixed()` to Test Before, At, and After Expiration

Create a simple Java test program to see how the three cases are checked.

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

public class ExpirationDemo {

    public static void main(String[] args) {
        Instant expiresAt = Instant.parse("2026-11-15T10:00:00Z");

        Clock beforeClock = Clock.fixed(
                Instant.parse("2026-11-15T09:59:59Z"),
                ZoneOffset.UTC
        );

        Clock exactClock = Clock.fixed(
                Instant.parse("2026-11-15T10:00:00Z"),
                ZoneOffset.UTC
        );

        Clock afterClock = Clock.fixed(
                Instant.parse("2026-11-15T10:00:01Z"),
                ZoneOffset.UTC
        );

        System.out.println(
                new AccessPolicy(beforeClock).isExpired(expiresAt)
        );

        System.out.println(
                new AccessPolicy(exactClock).isExpired(expiresAt)
        );

        System.out.println(
                new AccessPolicy(afterClock).isExpired(expiresAt)
        );
    }
}

final class AccessPolicy {

    private final Clock clock;

    AccessPolicy(Clock clock) {
        this.clock = clock;
    }

    boolean isExpired(Instant expiresAt) {
        return !clock.instant().isBefore(expiresAt);
    }
}
```

Output:

```text
false
true
true
```

Interpretation table:

| Fixed clock | Comparison | `isExpired` result |
| --- | --- | --- |
| 09:59:59Z | `now < expiresAt` | `false` |
| 10:00:00Z | `now = expiresAt` | `true` |
| 10:00:01Z | `now > expiresAt` | `true` |

The three checks do not wait a single second. Each time we create the policy, we pass a clock fixed at the instant under test.

In a real project, `AccessPolicy` should be defined once in its own file; the snippet above puts the class and demo in the same file so learners can run it standalone.

## 5. Writing Unit Tests with JUnit 5

When a project uses JUnit 5, you can write tests that express each boundary case clearly.

Example business class:

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class AccessPolicy {

    private final Clock clock;

    public AccessPolicy(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public boolean isExpired(Instant expiresAt) {
        Objects.requireNonNull(expiresAt);

        return !clock.instant().isBefore(expiresAt);
    }
}
```

Test file `AccessPolicyTest.java`:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class AccessPolicyTest {

    private static final Instant EXPIRES_AT =
            Instant.parse("2026-11-15T10:00:00Z");

    @Test
    void shouldNotBeExpiredOneSecondBeforeDeadline() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-15T09:59:59Z"),
                ZoneOffset.UTC
        );

        AccessPolicy policy = new AccessPolicy(clock);

        assertFalse(policy.isExpired(EXPIRES_AT));
    }

    @Test
    void shouldBeExpiredExactlyAtDeadline() {
        Clock clock = Clock.fixed(
                EXPIRES_AT,
                ZoneOffset.UTC
        );

        AccessPolicy policy = new AccessPolicy(clock);

        assertTrue(policy.isExpired(EXPIRES_AT));
    }

    @Test
    void shouldBeExpiredAfterDeadline() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-15T10:00:01Z"),
                ZoneOffset.UTC
        );

        AccessPolicy policy = new AccessPolicy(clock);

        assertTrue(policy.isExpired(EXPIRES_AT));
    }
}
```

The test names clearly describe the instant and expected outcome. When a test fails, its name immediately indicates which time boundary case needs investigation.

JUnit 5 is an independent testing library; `Clock.fixed()` belongs to JDK 17 and needs no testing library to work. If the project does not yet use JUnit, you can run a demo with `main()` and check results as in the previous section.

### You Can Use a Helper to Create a Fixed Clock

If many tests need to create clocks, you can write a helper:

```java
private static Clock fixedAt(String instant) {
    return Clock.fixed(
            Instant.parse(instant),
            ZoneOffset.UTC
    );
}
```

Then:

```java
@Test
void shouldBeExpiredAtDeadline() {
    AccessPolicy policy = new AccessPolicy(
            fixedAt("2026-11-15T10:00:00Z")
    );

    assertTrue(policy.isExpired(EXPIRES_AT));
}
```

A helper should only be used if it makes tests easier to read. For one or two tests, writing `Clock.fixed()` directly is also clear.

## 6. Testing Expiration Times Calculated from Creation Time

Many systems do not receive `expiresAt` up front, but calculate expiration from when a token, session, or verification code is created.

For example, a token with a 15-minute lifetime. If issued at `issuedAt`, the expiration time is:

```java
Instant expiresAt = issuedAt.plus(Duration.ofMinutes(15));
```

To test this, fix the clock at the token creation time and use the same clock source when checking expiration.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class TokenService {

    private final Clock clock;

    public TokenService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public Token issue() {
        Instant issuedAt = clock.instant();
        Instant expiresAt = issuedAt.plus(Duration.ofMinutes(15));

        return new Token(issuedAt, expiresAt);
    }

    public boolean isExpired(Token token) {
        return !clock.instant().isBefore(token.expiresAt());
    }

    public record Token(Instant issuedAt, Instant expiresAt) {
    }
}
```

A test with fixed clocks:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class TokenServiceTest {

    @Test
    void tokenExpiresAtFifteenMinuteBoundary() {
        Instant issuedAt = Instant.parse("2026-11-15T10:00:00Z");

        Clock atIssueTime = Clock.fixed(issuedAt, ZoneOffset.UTC);
        TokenService service = new TokenService(atIssueTime);

        TokenService.Token token = service.issue();

        assertFalse(service.isExpired(token));
        assertEquals(
                issuedAt.plus(Duration.ofMinutes(15)),
                token.expiresAt()
        );

        Clock atExpiry = Clock.fixed(
                token.expiresAt(),
                ZoneOffset.UTC
        );

        TokenService serviceAtExpiry = new TokenService(atExpiry);

        assertTrue(serviceAtExpiry.isExpired(token));
    }
}
```

The test snippet needs an additional `assertEquals` import alongside the other imports:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
```

This example illustrates two fixed clock sources: a clock at issuance time and a clock at the expiration boundary. Because `Clock.fixed` does not advance on its own, another clock must be created to simulate the later instant.

One note on organization: if a test only needs to verify `isExpired`, it does not necessarily have to test token issuance in the same test. Separating the `expiresAt` calculation test from the expiration boundary test makes the root cause of failures clearer.

## 7. Testing a Point in the Past or Future

`Clock.fixed` can fix any valid instant, including instants in the past or future relative to the machine's real clock.

For example, checking a license that expired the previous year:

```java
Instant expiresAt = Instant.parse("2025-12-31T23:59:59Z");

Clock testClock = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneOffset.UTC
);

AccessPolicy policy = new AccessPolicy(testClock);

System.out.println(policy.isExpired(expiresAt)); // true
```

Or checking a license still valid in the distant future:

```java
Instant expiresAt = Instant.parse("2030-01-01T00:00:00Z");

Clock testClock = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneOffset.UTC
);

AccessPolicy policy = new AccessPolicy(testClock);

System.out.println(policy.isExpired(expiresAt)); // false
```

The strength is that the test does not depend on the date it runs. Whether run today or years later, the clock still returns the exact chosen instant.

## 8. Testing Expiration by Calendar Date and Time Zone

Not all deadlines are stored as exact instants. Some business rules state "valid through the end of November 15 in the store's time zone."

This is a **calendar date** rule, so the zone must be determined before converting to an instant.

For example, a license is valid through `2026-11-15` in the `Asia/Ho_Chi_Minh` time zone. We can treat the end boundary as the start of the next day in that time zone (exclusive upper bound):

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

public class CalendarExpiry {

    static boolean isExpired(
            LocalDate validThrough,
            Clock clock
    ) {
        ZoneId zone = clock.getZone();

        Instant expiresAtExclusive = validThrough
                .plusDays(1)
                .atStartOfDay(zone)
                .toInstant();

        return !clock.instant().isBefore(expiresAtExclusive);
    }
}
```

Testing with a fixed clock:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Clock beforeEnd = Clock.fixed(
        Instant.parse("2026-11-15T16:59:59Z"),
        zone
);

Clock atNextDay = Clock.fixed(
        Instant.parse("2026-11-15T17:00:00Z"),
        zone
);

LocalDate validThrough = LocalDate.of(2026, 11, 15);

System.out.println(CalendarExpiry.isExpired(validThrough, beforeEnd));
System.out.println(CalendarExpiry.isExpired(validThrough, atNextDay));
```

Output:

```text
false
true
```

In this example, `17:00Z` corresponds to `00:00` on November 16 in `Asia/Ho_Chi_Minh`. The license remains valid throughout November 15 and expires the moment the next day begins in that zone.

Use `atStartOfDay(zone)` to convert a calendar date to the start of the day in the chosen time zone. This handles time-zone rules better than manually adding a fixed number of hours to UTC, because some zones have historical changes or daylight saving time rules.

If business logic only has an absolute timestamp, store and compare with `Instant`. If business logic is based on local dates, keep `LocalDate` together with `ZoneId` and clearly define the conversion rule.

## 9. Distinguishing `Instant`, `LocalDateTime`, and `Clock`

These three types have different roles:

| Type | Description | When to use |
| --- | --- | --- |
| `Instant` | An absolute point on the UTC timeline. | Tokens, sessions, timestamps, exact expiration instants. |
| `LocalDateTime` | Local date and time without zone/offset. | Local appointments when the zone is managed separately. |
| `Clock` | Source providing time and zone. | Allowing logic to read system time or fixed time during tests. |
| `LocalDate` | A calendar date without time or zone. | Validity dates or deadlines based on a local calendar. |
| `ZonedDateTime` | Date and time tied to a specific `ZoneId`. | Calendar rules tied to a time zone, such as opening hours or end-of-day deadlines. |

For token or session lifetimes, `Instant` is usually suitable because it represents an absolute point in time. Comparing two `Instant` values does not depend on the display time zone.

`Clock` has a zone because it also supports APIs such as `LocalDate.now(clock)`. When calling only `clock.instant()`, the value is an absolute instant; the zone does not alter that instant.

## 10. Using the Same Clock Throughout a Calculation

A common design mistake is calling the system clock multiple times within a single operation:

```java
Instant issuedAt = Instant.now();
Instant expiresAt = Instant.now().plus(Duration.ofMinutes(5));
```

The two `now()` calls can return two different points in time. The gap is usually small, but in precise calculations or tests, reading time twice can cause discrepancies.

It is better to capture a single instant and reuse it:

```java
Instant now = clock.instant();

Instant issuedAt = now;
Instant expiresAt = now.plus(Duration.ofMinutes(5));
```

This also keeps results consistent: both the issuance time and expiration time are computed from the same reference point.

Similarly, when a method checks multiple conditions relative to the same moment, read the clock once:

```java
public boolean canUse(Instant startsAt, Instant expiresAt) {
    Instant now = clock.instant();

    return !now.isBefore(startsAt)
            && now.isBefore(expiresAt);
}
```

This example defines a **half-open** validity interval (inclusive start, exclusive end): becomes valid when `now >= startsAt` and expires when `now >= expiresAt`.

## 11. Testing Fixed Clocks with Different Expiration Policies

A system may have several kinds of rules:

- Expires right at the boundary (`now >= expiresAt`).
- Remains valid strictly before the boundary (`now < expiresAt`).
- Becomes valid at the start boundary (`now >= startsAt`).
- Validity window `[startsAt, expiresAt)`.
- Having a grace period after expiration.

Express each rule explicitly instead of using a generic comparison without explanation.

Example of a validity window:

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class ValidityWindow {

    private final Clock clock;

    public ValidityWindow(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public boolean isActive(Instant startsAt, Instant expiresAt) {
        Objects.requireNonNull(startsAt);
        Objects.requireNonNull(expiresAt);

        if (expiresAt.isBefore(startsAt)) {
            throw new IllegalArgumentException(
                    "expiresAt must not be before startsAt"
            );
        }

        Instant now = clock.instant();

        return !now.isBefore(startsAt)
                && now.isBefore(expiresAt);
    }
}
```

Testing at both boundaries:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class ValidityWindowTest {

    private static final Instant START =
            Instant.parse("2026-11-15T10:00:00Z");

    private static final Instant END =
            Instant.parse("2026-11-15T11:00:00Z");

    @Test
    void isActiveAtStart() {
        Clock clock = Clock.fixed(START, ZoneOffset.UTC);

        assertTrue(new ValidityWindow(clock).isActive(START, END));
    }

    @Test
    void isNotActiveBeforeStart() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-15T09:59:59Z"),
                ZoneOffset.UTC
        );

        assertFalse(new ValidityWindow(clock).isActive(START, END));
    }

    @Test
    void isNotActiveAtEnd() {
        Clock clock = Clock.fixed(END, ZoneOffset.UTC);

        assertFalse(new ValidityWindow(clock).isActive(START, END));
    }
}
```

The test at the start of the window confirms the start instant is included. The test at the end of the window confirms the expiration instant is excluded. This clarifies the exact boundaries where time-related bugs commonly occur.

## 12. When to Use `Clock.offset()`?

`Clock.offset()` creates a clock based on another clock, shifting time by a `Duration`.

Example:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

Clock base = Clock.fixed(
        Instant.parse("2026-11-15T10:00:00Z"),
        ZoneOffset.UTC
);

Clock fiveMinutesLater = Clock.offset(
        base,
        Duration.ofMinutes(5)
);

System.out.println(base.instant());
System.out.println(fiveMinutesLater.instant());
```

Output:

```text
2026-11-15T10:00:00Z
2026-11-15T10:05:00Z
```

This is a convenient way to test a milestone relative to the base clock. Because the base clock is fixed, the offset clock does not advance with real time either.

It can be used to test a token expiring after 15 minutes:

```java
Clock issueClock = Clock.fixed(
        Instant.parse("2026-11-15T10:00:00Z"),
        ZoneOffset.UTC
);

TokenService issuer = new TokenService(issueClock);
TokenService.Token token = issuer.issue();

Clock atExpiry = Clock.offset(issueClock, Duration.ofMinutes(15));
TokenService verifier = new TokenService(atExpiry);

System.out.println(verifier.isExpired(token)); // true
```

`Clock.offset()` does not mutate the base clock. It returns a new clock with the instant shifted by the duration. If a test needs an explicit absolute instant, `Clock.fixed()` is often easier to read; if it needs to express "15 minutes after the base instant," `Clock.offset()` can be concise.

## 13. Common Mistakes When Testing Expiration

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| Calling `Instant.now()` directly in business logic | Tests depend on the real clock and boundaries are hard to reproduce. | Inject `Clock` and call `clock.instant()`. |
| Using `Thread.sleep()` to wait for expiration | Slow tests dependent on scheduler and timing accuracy. | Use `Clock.fixed()` with instants before/at/after the deadline. |
| Only testing the before-deadline case | Misses comparison bugs at equality. | Include tests for `now < expiresAt`, `now = expiresAt`, and `now > expiresAt`. |
| Using `isAfter()` when business rules expire at equality | Token is still treated as valid right at the expiration instant. | Use `!now.isBefore(expiresAt)` if the rule is `now >= expiresAt`. |
| Using `LocalDateTime` without specifying a zone | Time can be misinterpreted when run in a different time-zone environment. | Use `Instant` for absolute timestamps or manage `ZoneId` explicitly for local date-time. |
| Using a clock whose zone differs from the business zone | Calendar date is calculated as the wrong day. | Create the clock with an explicit zone and test with the same zone. |
| Expecting `Clock.fixed()` to advance over time | Tests always receive the same instant. | Create a new fixed clock or use `Clock.offset()` for shifted instants. |
| Reading time multiple times within one decision | Conditions may evaluate against different instants. | Read `clock.instant()` once into a `now` variable. |
| Assuming a fixed clock tests all system time issues | Does not catch clock skew, server synchronization, or distributed timing issues. | Test logic with fixed clocks; test time infrastructure with dedicated procedures. |

## 14. Integrating with Production Applications

In production, applications typically need the current time from the system. You can pass `Clock.systemUTC()` when constructing services:

```java
Clock productionClock = Clock.systemUTC();

AccessPolicy policy = new AccessPolicy(productionClock);
```

If the application uses a dependency injection framework, register a `Clock` bean or provider and inject it into services that need time. Simple examples using constructor injection are enough to keep the code framework-independent.

Do not use `Clock.fixed()` in normal production configuration, because every read would return the same instant and tokens/deadlines would never expire.

You should also never change the test machine's operating system clock just to test expiration logic. Doing so can affect other processes and requires system privileges. `Clock.fixed()` lets you simulate time at the application level without modifying the real clock.

### Passing Clock via Constructor or Static Utility?

**Prefer constructor injection** for services with time-dependent logic:

```java
public final class PasswordResetService {
    private final Clock clock;

    public PasswordResetService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }
}
```

This lets each test construct the service with its own clock. Static methods calling `Instant.now()` themselves make it hard to replace the time source and easily couple tests to the environment.

If a helper only formats an instant passed into it, it does not need a `Clock`. Only places that actually need to ask "what time is it now?" need a dependency on a clock.

## 15. Practice Exercises

### Exercise 1 — Checking Verification Code Expiration

Create a record:

```java
record VerificationCode(String value, Instant expiresAt) {
}
```

Write a service accepting `Clock` with a method `isExpired(VerificationCode code)`. Rule: the code expires when `now >= expiresAt`.

Create three fixed clocks: one second before expiration, at expiration, and one second after expiration. Determine the expected results.

### Exercise 2 — Token with a 10-Minute Lifetime

Write a service that issues tokens with `issuedAt = clock.instant()` and `expiresAt = issuedAt.plus(Duration.ofMinutes(10))`. Use fixed clocks to test that the token is still valid at minute 9 and expired at minute 10.

### Exercise 3 — Validity Window

Write a method `isActive(startsAt, expiresAt)` with the rule `startsAt <= now < expiresAt`. Write tests for:

- Before the start time.
- Exactly at the start time.
- Inside the window.
- Exactly at the end time.
- After the end time.

### Exercise 4 — Local Date Expiration

A discount voucher is valid through `2026-11-15` in `Asia/Ho_Chi_Minh`. Convert the expiration date into an exclusive upper-bound instant using the start of the next day in that zone. Use fixed clocks to test immediately before and at the upper-bound instant.

### Exercise 5 — Auditing Code for Real Clock Dependencies

Search business classes for calls to `Instant.now()`, `LocalDate.now()`, or `System.currentTimeMillis()`. Identify where a `Clock` should be received externally and rewrite so tests can control time.

## 16. Quick Reference

| Need | How to do it |
| --- | --- |
| Get current time in testable code | Inject `Clock` and call `clock.instant()`. |
| Create fixed time | `Clock.fixed(instant, ZoneOffset.UTC)`. |
| Test before deadline | Fix clock at an instant earlier than `expiresAt`. |
| Test at deadline | Fix clock equal to `expiresAt`. |
| Test after deadline | Fix clock at an instant later than `expiresAt`. |
| Expired at or after deadline | `!now.isBefore(expiresAt)`. |
| Expired strictly after deadline | `now.isAfter(expiresAt)`. |
| Simulate shifted time | `Clock.offset(baseClock, duration)`. |
| Test local calendar date expiration | Use `LocalDate` with an explicit `ZoneId`, convert to instant per business rules. |
| Run production application | Typically inject `Clock.systemUTC()` for instant-based logic. |

**Core principle:** Treat the current time as a replaceable dependency. In Java 17, inject `Clock` into business logic and use `Clock.fixed()` in tests to pin the exact instant under test. With the "expired at or after deadline" rule, `!now.isBefore(expiresAt)` includes the equality boundary. This approach keeps tests fast, reliably repeatable, and focused directly on the critical time boundaries.
