# Passing InstantSource to Test Expiration Rules

> **Topic:** Java 17  
> **Chapter:** Hands-on Practice  
> **Goal:** Decouple fetching the current time from business logic, inject `java.time.InstantSource` into expiration-checking components, and write deterministic tests for before, exactly at, and after the expiration instant.

## 1. The Problem: Expiration Rules Depend on Current Time

Applications frequently need to decide whether an item is still valid or has expired:

- Is an access token still usable?
- Has a login session expired?
- Is a coupon still within its valid period?
- Is a subscription still active?
- Has a reservation passed its confirmation deadline?
- Is a password reset link still valid?

A common direct implementation looks like this:

```java
public boolean isExpired(Instant expiresAt) {
    return Instant.now().isAfter(expiresAt);
}
```

This code reads the system clock directly inside business logic. When testing, the result depends on the exact time the test runs. Tests can flake near the expiration boundary, and it is difficult to test the exact "at the moment of expiration" case reliably.

You should not work around this by calling `Thread.sleep()` to wait for time to pass. That slows down tests, depends on OS thread scheduling, and easily becomes flaky in CI.

The solution is to pass a source of current time into the component enforcing the rule. In Java 17, when only an `Instant` is needed, the right API is `InstantSource`.

## 2. InstantSource in Java 17

### 2.1. What Is InstantSource?

`java.time.InstantSource` is an interface added in Java 17. It represents a source providing the current point in time as an `Instant`:

```java
package java.time;

public interface InstantSource {
    Instant instant();
    default long millis() { ... }

    static InstantSource system() { ... }
    static InstantSource fixed(Instant fixedInstant) { ... }
    static InstantSource offset(InstantSource baseSource, Duration offset) { ... }
    static InstantSource tick(InstantSource baseSource, Duration tickDuration) { ... }
}
```

The snippet above outlines the primary API members, not the actual implementation source code. `instant()` returns the current instant represented by the source. `millis()` returns epoch milliseconds.

An important property: `InstantSource` has no attached time zone. It simply supplies a point on the timeline. This fits expiration rules stored as an `Instant`, such as when a token ceases to be valid.

### 2.2. InstantSource and Clock

`java.time.Clock` has existed since Java 8, and in Java 17 it implements `InstantSource`. Consequently, you can pass a `Clock` wherever an `InstantSource` is expected:

```java
InstantSource source = Clock.systemUTC();
Instant now = source.instant();
```

Difference in intent:

| API | Purpose |
|---|---|
| `InstantSource` | Only needs the current instant on the timeline as an `Instant` |
| `Clock` | Provides both an instant and a time zone, suitable when logic needs local date/time conversions |

If the rule only compares two `Instant` values, using `InstantSource` expresses the minimal dependency. If the logic requires `LocalDate.now(clock)`, local time, or zones, pass `Clock`, or pass `InstantSource` together with an explicit `ZoneId`.

### 2.3. Useful Factory Methods

Java 17 provides built-in ways to construct time sources:

| Factory | Meaning | Use case |
|---|---|---|
| `InstantSource.system()` | Current system wall-clock time source | Production |
| `InstantSource.fixed(instant)` | Always returns the same `Instant` | Deterministic tests |
| `InstantSource.offset(base, duration)` | Shifts a base source's time by a `Duration` | Tests simulating future or past |
| `InstantSource.tick(base, duration)` | Advances only in discrete step increments (ticks) | Simulating a source with coarse step resolution |

Example:

```java
InstantSource productionTime = InstantSource.system();

Instant baseline = Instant.parse("2026-01-01T00:00:00Z");
InstantSource frozenTime = InstantSource.fixed(baseline);

InstantSource tomorrow = InstantSource.offset(
        frozenTime, Duration.ofDays(1));
```

`frozenTime.instant()` always returns `baseline`. `tomorrow.instant()` returns the instant one day after `baseline`. These sources let you test time-dependent logic without changing the OS clock.

## 3. Defining the Expiration Rule Clearly

Before writing code, agree on the exact semantics of `expiresAt`.

A common rule for tokens and sessions is:

- Active when `now < expiresAt`.
- Expired when `now >= expiresAt`.

In other words, the expiration instant is an **exclusive upper bound**: at that exact instant, the item is already expired.

Diagram:

```text
           active                        expired
-------------------------------|------------------------>
                               ^
                           expiresAt

now < expiresAt  => active
now = expiresAt  => expired
now > expiresAt  => expired
```

In Java, this condition is cleanly written using `isBefore`:

```java
boolean isExpired = !now.isBefore(expiresAt);
```

This clearly expresses `now >= expiresAt`. If business rules define something else—for example, a coupon valid through the end of a local calendar day—model that policy explicitly instead of silently changing comparison operators in multiple places.

## 4. Injecting InstantSource into a Service

### 4.1. Modeling an Item with an Expiration Instant

For tokens or sessions, store the expiration timestamp as an `Instant`:

```java
import java.time.Instant;

public record AccessToken(String subject, Instant expiresAt) {
}
```

`Instant` represents an absolute point on the UTC timeline. It is well suited for storing token lifetimes, issuance times, and expiration timestamps.

### 4.2. Writing a Service Accepting InstantSource via Constructor

```java
import java.time.Instant;
import java.time.InstantSource;
import java.util.Objects;

public final class TokenExpirationPolicy {
    private final InstantSource timeSource;

    public TokenExpirationPolicy(InstantSource timeSource) {
        this.timeSource = Objects.requireNonNull(timeSource);
    }

    public boolean isExpired(AccessToken token) {
        Objects.requireNonNull(token);
        Instant now = timeSource.instant();
        return !now.isBefore(token.expiresAt());
    }
}
```

Notice three aspects of this design:

1. The service never calls `Instant.now()`; the time source is an injected external dependency.
2. Within a single evaluation, the service reads the current time once into `now`. This prevents two clock reads during one decision from observing two different timestamps.
3. The expiration rule is clearly expressed as `!now.isBefore(expiresAt)`, meaning expired when `now >= expiresAt`.

### 4.3. Production Configuration

In production, inject the system time source:

```java
InstantSource timeSource = InstantSource.system();
TokenExpirationPolicy policy =
        new TokenExpirationPolicy(timeSource);
```

If the application uses a dependency injection framework, register the source as a shared dependency:

```java
@Configuration
class TimeConfiguration {
    @Bean
    InstantSource instantSource() {
        return InstantSource.system();
    }
}
```

Then inject `InstantSource` into services via their constructors. The snippet above uses Spring-style annotations; without a framework, simply construct the source at the composition root and pass it to constructors as shown first.

### 4.4. Do Not Create the System Source Inside Each Call

Avoid writing:

```java
public boolean isExpired(AccessToken token) {
    InstantSource source = InstantSource.system();
    return !source.instant().isBefore(token.expiresAt());
}
```

This still hardcodes the time dependency inside the method, making tests hard to control and scattering time-source configuration. Create the source at the composition root and inject it into the service.

## 5. Testing with InstantSource.fixed

### 5.1. Why Fixed Sources Are Useful

`InstantSource.fixed(instant)` always returns the same instant. This enables deterministic tests:

- Tests always run with the exact same `now`.
- Independent of the test runner's system clock.
- No waiting with `sleep`.
- Exact verification of the expiration boundary.

Suppose a token expires at:

```java
Instant expiresAt = Instant.parse("2026-05-01T12:00:00Z");
```

We can construct three sources:

```java
InstantSource beforeExpiry =
        InstantSource.fixed(expiresAt.minusSeconds(1));

InstantSource atExpiry =
        InstantSource.fixed(expiresAt);

InstantSource afterExpiry =
        InstantSource.fixed(expiresAt.plusSeconds(1));
```

Each source simulates a scenario without altering the machine's real clock.

### 5.2. Testing the Three Boundary Cases with JUnit 5

Test example:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.time.InstantSource;
import org.junit.jupiter.api.Test;

class TokenExpirationPolicyTest {
    private static final Instant EXPIRES_AT =
            Instant.parse("2026-05-01T12:00:00Z");

    @Test
    void tokenIsActiveBeforeExpiry() {
        var policy = new TokenExpirationPolicy(
                InstantSource.fixed(EXPIRES_AT.minusSeconds(1)));
        var token = new AccessToken("user-1", EXPIRES_AT);

        assertFalse(policy.isExpired(token));
    }

    @Test
    void tokenIsExpiredAtExactBoundary() {
        var policy = new TokenExpirationPolicy(
                InstantSource.fixed(EXPIRES_AT));
        var token = new AccessToken("user-1", EXPIRES_AT);

        assertTrue(policy.isExpired(token));
    }

    @Test
    void tokenIsExpiredAfterBoundary() {
        var policy = new TokenExpirationPolicy(
                InstantSource.fixed(EXPIRES_AT.plusSeconds(1)));
        var token = new AccessToken("user-1", EXPIRES_AT);

        assertTrue(policy.isExpired(token));
    }
}
```

These three tests confirm the policy at the three critical points:

| Current time | `isExpired` result |
|---|---|
| `expiresAt - 1 second` | `false` |
| `expiresAt` | `true` |
| `expiresAt + 1 second` | `true` |

Testing at the exact boundary is especially important. If someone accidentally wrote `now.isAfter(expiresAt)`, the second test would fail because `isAfter` returns `false` when the two instants are equal.

### 5.3. Using a Fixed Reference Instant Constant in Tests

Declare a readable, fixed baseline timestamp via `Instant.parse`. Avoid calling `Instant.now()` inside tests and adding/subtracting offsets, because that couples tests to the real clock and makes failure diffs harder to read.

For example:

```java
private static final Instant TEST_NOW =
        Instant.parse("2026-05-01T12:00:00Z");
```

From this baseline, derive earlier and later timestamps using `minusSeconds`, `plusSeconds`, `minus`, or `plus`. Operations on `Instant` are immutable and return new instances.

## 6. Testing Time Progression with Offset and Mutable Sources

`InstantSource.fixed` works well when each test evaluates a single timestamp. When a test needs to simulate time passing within one scenario, use `InstantSource.offset` or write a test-only mutable implementation.

### 6.1. Using InstantSource.offset

`offset` creates a source whose instant equals the base source plus a `Duration`:

```java
Instant base = Instant.parse("2026-05-01T12:00:00Z");
InstantSource baseSource = InstantSource.fixed(base);

InstantSource oneHourLater = InstantSource.offset(
        baseSource, Duration.ofHours(1));

InstantSource oneDayEarlier = InstantSource.offset(
        baseSource, Duration.ofDays(-1));
```

Because the base source is fixed, both offset sources also produce stable values. This is a concise way to test past/future timestamps without writing a fake class.

### 6.2. Creating a MutableInstantSource for Tests That Advance Time

When testing a service across multiple timestamps, you can create a test-only mutable source:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.InstantSource;
import java.util.concurrent.atomic.AtomicReference;

final class MutableInstantSource implements InstantSource {
    private final AtomicReference<Instant> current;

    MutableInstantSource(Instant initialInstant) {
        this.current = new AtomicReference<>(initialInstant);
    }

    @Override
    public Instant instant() {
        return current.get();
    }

    void advanceBy(Duration duration) {
        current.updateAndGet(instant -> instant.plus(duration));
    }

    void set(Instant instant) {
        current.set(instant);
    }
}
```

`AtomicReference` makes reading and updating the timestamp thread-safe if a test accesses the source from multiple threads. In single-threaded tests, a plain mutable `Instant` field could suffice, though shared sources across threads should have clear semantics.

### 6.3. Testing a Token Across Multiple Timestamps

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class TokenExpirationProgressionTest {
    @Test
    void tokenExpiresAsTimeAdvances() {
        Instant start = Instant.parse("2026-05-01T12:00:00Z");
        Instant expiresAt = start.plus(Duration.ofMinutes(30));

        MutableInstantSource time = new MutableInstantSource(start);
        TokenExpirationPolicy policy = new TokenExpirationPolicy(time);
        AccessToken token = new AccessToken("user-1", expiresAt);

        assertFalse(policy.isExpired(token));

        time.advanceBy(Duration.ofMinutes(29));
        assertFalse(policy.isExpired(token));

        time.advanceBy(Duration.ofMinutes(1));
        assertTrue(policy.isExpired(token));
    }
}
```

This test simulates 29 minutes and then 1 additional minute. It does not wait 30 real-world minutes; the source simply updates the timestamp it returns.

### 6.4. When to Use Fixed, Offset, or Mutable Fakes?

| Source approach | Use when |
|---|---|
| `InstantSource.fixed` | Testing a rule at one specific timestamp |
| `InstantSource.offset` | Testing a timestamp shifted relative to a base source |
| Mutable fake | Testing a multi-step scenario that explicitly advances or sets time |
| `InstantSource.system` | Production application needing real system time |

Do not build a complex mutable fake if a fixed source is enough. Less state makes tests simpler to read and less error-prone.

## 7. InstantSource, Clock, and Time Zones

### 7.1. Token Expirations Should Use Instant

The expiration of a token, lease, or session is usually an absolute point in time. Store it as an `Instant`:

```java
Instant issuedAt = timeSource.instant();
Instant expiresAt = issuedAt.plus(Duration.ofMinutes(15));
```

When checking validity, compare `Instant` with `Instant`. No conversion to local time is needed, and the check does not depend on the server's default time zone.

### 7.2. Local-Date Expiration Rules Require a ZoneId

Some business rules define a coupon as valid through the end of a calendar day in a specific region. In that case, use an explicit time zone, for example:

```java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate validThrough = LocalDate.of(2026, 5, 1);

Instant expiresAtExclusive = validThrough
        .plusDays(1)
        .atStartOfDay(businessZone)
        .toInstant();

boolean expired = !timeSource.instant().isBefore(expiresAtExclusive);
```

Here, the expiration instant is the start of the following day in the business time zone. This avoids assuming every day is exactly 24 hours long; time zones with daylight saving rules can have 23- or 25-hour days.

### 7.3. When Should You Inject Clock?

If a service performs many local date/time calculations, inject `Clock`:

```java
public final class DailyLimitPolicy {
    private final Clock clock;

    public DailyLimitPolicy(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public LocalDate currentBusinessDate() {
        return LocalDate.now(clock);
    }
}
```

Tests can inject `Clock.fixed(instant, zone)`. Since `Clock` implements `InstantSource`, the same clock can also be passed to services that only require `InstantSource`.

If a service needs both an instant and a zone, `Clock` is usually clearer. If it only needs an instant, avoid introducing a time-zone dependency just out of habit with `Clock`.

## 8. Extending the Rule: Remaining Time

Beyond checking whether an item is expired, applications often need to know how much time remains before expiration:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.InstantSource;
import java.util.Objects;

public final class ExpirationPolicy {
    private final InstantSource timeSource;

    public ExpirationPolicy(InstantSource timeSource) {
        this.timeSource = Objects.requireNonNull(timeSource);
    }

    public boolean isExpired(Instant expiresAt) {
        Objects.requireNonNull(expiresAt);
        Instant now = timeSource.instant();
        return !now.isBefore(expiresAt);
    }

    public Duration remaining(Instant expiresAt) {
        Objects.requireNonNull(expiresAt);
        Duration remaining =
                Duration.between(timeSource.instant(), expiresAt);
        return remaining.isNegative() ? Duration.ZERO : remaining;
    }
}
```

If the current instant is past the expiration time, `Duration.between` returns a negative duration; the method normalizes negative results to `Duration.ZERO`. At the exact expiration instant, the result is also zero.

Test example:

```java
@Test
void remainingTimeIsCalculatedFromInjectedSource() {
    Instant now = Instant.parse("2026-05-01T12:00:00Z");
    ExpirationPolicy policy =
            new ExpirationPolicy(InstantSource.fixed(now));

    Duration remaining = policy.remaining(now.plusSeconds(90));

    assertEquals(Duration.ofSeconds(90), remaining);
}

@Test
void remainingTimeNeverBecomesNegative() {
    Instant now = Instant.parse("2026-05-01T12:00:00Z");
    ExpirationPolicy policy =
            new ExpirationPolicy(InstantSource.fixed(now));

    Duration remaining = policy.remaining(now.minusSeconds(1));

    assertEquals(Duration.ZERO, remaining);
}
```

When a business operation needs multiple consistent results within a single decision, read `Instant` once and pass that `now` value into subsequent calculations. Avoid invoking the source multiple times inside a compound check.

## 9. Boundary Testing Rules

### 9.1. Test Before, Exactly At, and After the Boundary

A minimal test suite for an expiration policy should cover:

| Case | Source timestamp | Expected result |
|---|---|---|
| Well before expiry | `expiresAt - 1 day` | Not expired |
| Immediately before expiry | `expiresAt - 1 nanosecond` | Not expired |
| Exact boundary | `expiresAt` | Expired |
| Immediately after expiry | `expiresAt + 1 nanosecond` | Expired |
| Long past expiry | `expiresAt - 1 day` as `now` | Expired |

`Instant` has nanosecond resolution. However, if your database stores timestamps at millisecond or microsecond precision, agree on truncation/rounding rules at the persistence boundary and test at the actual stored precision.

### 9.2. Use Parameterized Tests for Multiple Timestamps

With JUnit 5, use `@ParameterizedTest` and `@MethodSource` to check multiple timestamps without duplicating code:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Instant;
import java.time.InstantSource;
import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.params.provider.Arguments;

class ExpirationBoundaryTest {
    private static final Instant EXPIRES_AT =
            Instant.parse("2026-05-01T12:00:00Z");

    static Stream<Arguments> cases() {
        return Stream.of(
                Arguments.of(EXPIRES_AT.minusNanos(1), false),
                Arguments.of(EXPIRES_AT, true),
                Arguments.of(EXPIRES_AT.plusNanos(1), true));
    }

    @ParameterizedTest
    @MethodSource("cases")
    void appliesExclusiveExpiryBoundary(
            Instant now, boolean expectedExpired) {
        var policy = new TokenExpirationPolicy(
                InstantSource.fixed(now));
        var token = new AccessToken("user-1", EXPIRES_AT);

        assertEquals(expectedExpired, policy.isExpired(token));
    }
}
```

Parameterized tests require the JUnit Jupiter Params dependency. If a project includes only JUnit Jupiter API/Engine without Params, add the test dependency or keep separate test methods.

### 9.3. Do Not Use sleep to Test Expiration

Avoid:

```java
Thread.sleep(1_000);
assertTrue(policy.isExpired(token));
```

This test can fail if the scheduler lags, the system clock is adjusted, or the machine is under heavy load. Fixed or mutable sources are fast and deterministic.

### 9.4. Do Not Modify the OS Clock in Tests

Never alter the machine or CI system clock to test expiration logic. Changing the system clock affects other processes, requires elevated privileges, and destroys test isolation. Passing a dedicated time source to the object under test is enough.

## 10. Distinguishing Absolute Instants from Elapsed Durations

`InstantSource` provides wall-clock instants. This is the right choice for rules like "token expires at 12:00 UTC on day X", but it is not a monotonic stopwatch for measuring elapsed time.

### 10.1. System Clocks Can Be Adjusted

The OS clock can be adjusted by NTP synchronization, manual changes, or virtualization hypervisors. Consequently, two consecutive wall-clock readings are not guaranteed to advance strictly by the real elapsed duration.

For absolute expiration timestamps stored in a database, this is usually acceptable: the application needs to compare against current wall-clock time.

For in-process timeouts or measuring elapsed duration, use a monotonic clock:

```java
long startedAt = System.nanoTime();

performOperation();

long elapsedNanos = System.nanoTime() - startedAt;
Duration elapsed = Duration.ofNanos(elapsedNanos);
```

`System.nanoTime()` is designed to measure elapsed intervals, not calendar date/time. Never convert its value directly into an `Instant`.

### 10.2. Choosing the Right API for the Problem

| Problem | Suitable source |
|---|---|
| Token/session expires at an `Instant` | `InstantSource` |
| Coupon expires by local calendar date | `Clock` or `InstantSource` with `ZoneId` |
| Measuring how long a request took | `System.nanoTime()` |
| In-process timeout | Monotonic clock, typically `System.nanoTime()` |
| Recording record created/updated timestamps | `InstantSource` and `Instant` |

Do not use `InstantSource` for every time-related problem simply because it makes testing easier. Choose the time abstraction that matches the domain concept.

## 11. Time Precision and Cross-System Synchronization

### 11.1. Instant Precision

`Instant` represents timestamps down to nanosecond precision. However, that does not mean the OS clock is always accurate to the nanosecond. Actual resolution depends on the platform and time source.

If a database stores timestamps at millisecond precision, a written value may be rounded or truncated when read back. When testing boundaries:

- Identify the database column precision.
- Truncate/normalize `expiresAt` to that precision before persisting or comparing if required by the contract.
- Write tests verifying equality after a database round-trip.
- Never assume nanosecond values are preserved intact by every storage system.

### 11.2. Never Trust Client-Supplied Time

For access tokens, sessions, or coupons, expiration decisions should rely on server time or an organization-controlled time source. Never allow a client to pass a `now` field and use it directly to decide whether a token is still valid.

In multi-node systems:

- Synchronize server clocks using appropriate operational tooling.
- Define which node or service makes the authoritative expiration decision.
- If a protocol allows clock skew, define the tolerance explicitly and apply it consistently.
- Do not add arbitrary tolerances that unintentionally extend lifetimes.

`InstantSource` makes time dependencies testable and swappable in code; it does not synchronize clocks across machines.

### 11.3. Use the Same Instant Within a Single Decision

When a decision evaluates multiple time-dependent conditions, fetch `now` once:

```java
Instant now = timeSource.instant();

boolean tokenExpired = !now.isBefore(token.expiresAt());
boolean refreshWindowOpen = !now.isBefore(token.refreshAvailableAt());
boolean sessionExpired = !now.isBefore(session.expiresAt());
```

This ensures every condition in the decision uses the exact same point in time. Calling the source separately for each condition could yield inconsistent results if the clock crosses a boundary mid-method.

## 12. Common Mistakes When Injecting Time Sources

| Mistake/misconception | Why it is problematic | Fix |
|---|---|---|
| Calling `Instant.now()` inside a domain service | Tests depend on the real clock | Inject `InstantSource` via constructor |
| Using `now.isAfter(expiresAt)` for `now >= expiresAt` | Misses the exact boundary equality case | Use `!now.isBefore(expiresAt)` |
| Using `Thread.sleep()` in tests | Slow and flaky under scheduler variance | Use `InstantSource.fixed` or a mutable test source |
| Assuming `InstantSource` carries a time zone | Interface supplies only an instant | Use `Clock` or pass `ZoneId` separately for local-date rules |
| Using `InstantSource` for timeouts | Wall clocks can jump backwards or forwards | Use `System.nanoTime()` for elapsed time |
| Reading the source multiple times in one decision | Different reads can straddle an expiration boundary | Capture `Instant now` once and reuse it |
| Sharing a mutable source in production | One component can alter another component's clock | Use the system source in production; keep mutable fakes in tests only |
| Using `InstantSource.tick` for exact boundary checks | Ticking rounds timestamps to step intervals, altering boundary behavior | Use a fixed source or non-ticking system source for expiration |
| Comparing `LocalDateTime` with `Instant` via implicit default zone | Results depend on host configuration | Use `Instant` for absolute timestamps or specify `ZoneId` explicitly |
| Trusting client-supplied `now` | Clients can spoof their clock | Decide using server-controlled time |
| Ignoring database timestamp precision | Round-tripping timestamps can drop sub-millisecond parts | Normalize and test against storage precision |
| Adding undocumented clock-skew allowances | Can unintentionally extend validity | Define explicit tolerances and apply consistently |

## 13. Complete Example: Issuing and Validating Tokens

A single service can use the same time source to record issuance time, compute expiration, and validate validity:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.InstantSource;
import java.util.Objects;

public final class AccessTokenService {
    private final InstantSource timeSource;
    private final Duration tokenLifetime;

    public AccessTokenService(
            InstantSource timeSource,
            Duration tokenLifetime) {
        this.timeSource = Objects.requireNonNull(timeSource);
        this.tokenLifetime = Objects.requireNonNull(tokenLifetime);
        if (tokenLifetime.isNegative() || tokenLifetime.isZero()) {
            throw new IllegalArgumentException(
                    "tokenLifetime must be positive");
        }
    }

    public AccessToken issue(String subject) {
        Instant issuedAt = timeSource.instant();
        Instant expiresAt = issuedAt.plus(tokenLifetime);
        return new AccessToken(subject, expiresAt);
    }

    public boolean isExpired(AccessToken token) {
        Instant now = timeSource.instant();
        return !now.isBefore(token.expiresAt());
    }
}
```

Testing token issuance with a fixed time:

```java
@Test
void issuedTokenUsesInjectedTimeAndConfiguredLifetime() {
    Instant now = Instant.parse("2026-05-01T12:00:00Z");
    var service = new AccessTokenService(
            InstantSource.fixed(now),
            Duration.ofMinutes(15));

    AccessToken token = service.issue("user-1");

    assertEquals("user-1", token.subject());
    assertEquals(now.plus(Duration.ofMinutes(15)), token.expiresAt());
}
```

This test verifies both behaviors: issuance time comes from the injected source, and expiration is computed from the configured lifetime. No global system clock mocking is needed.

In real systems, token objects also carry an ID, issuer, audience, or signature. This example focuses on time rules; token signing and verification must follow the corresponding security protocol.

## 14. Organizing Dependencies in an Application

### 14.1. Creating the Source at the Composition Root

A single application entry point should decide the time source:

```java
public final class Application {
    public static void main(String[] args) {
        InstantSource timeSource = InstantSource.system();

        TokenExpirationPolicy expirationPolicy =
                new TokenExpirationPolicy(timeSource);

        // Pass expirationPolicy to components that need it.
    }
}
```

This clarifies dependencies and makes swapping sources easy in tests or special environments.

### 14.2. Avoid Mutable Global Static Clocks

Never create a mutable static field like `CurrentTime.source` and mutate it inside individual tests. If tests run in parallel, one test can overwrite another test's clock. Constructor injection isolates each instance and reduces coupling.

### 14.3. No Mock Framework Needed for InstantSource

Because `InstantSource` is a small interface with built-in factories, most tests do not need Mockito or any mocking library:

- Use `InstantSource.fixed` for a fixed instant.
- Use `InstantSource.offset` for a relative offset.
- Use a small mutable fake for multi-step timelines.

Mocking frameworks are needed only when complex interaction protocols or invocation counts must be verified. For expiration rules, the return value matters far more than verifying how many times `instant()` was called.

## 15. Practice Exercises

### Exercise 1 — Decouple Instant.now from a Service

Given the legacy service:

```java
public boolean isCouponExpired(Instant expiresAt) {
    return Instant.now().isAfter(expiresAt);
}
```

Refactor it to:

1. Inject `InstantSource` via the constructor.
2. Read the current time once per method call.
3. Treat the coupon as expired at the exact `expiresAt` instant.
4. Write tests with `InstantSource.fixed` for before, at, and after expiration.

### Exercise 2 — Testing Token Expiration

Create an `AccessToken` record and an expiration-checking service. Write three JUnit 5 tests with fixed timestamps:

- `now = expiresAt - 1 second`.
- `now = expiresAt`.
- `now = expiresAt + 1 second`.

Explain why using `isAfter` alone fails the rule for expiration at equal timestamps.

### Exercise 3 — Simulating Time Progression

Create `MutableInstantSource` with an `advanceBy(Duration)` method. Write a test proving a token starts active and then expires when the source advances to the exact boundary.

Do not use `Thread.sleep`.

### Exercise 4 — Calculating Remaining Time

Add a `remaining(Instant expiresAt)` method returning `Duration`. Enforce non-negative results: if already expired, return `Duration.ZERO`. Write tests for 90 seconds remaining and already expired.

### Exercise 5 — Local-Date Coupon Expiration

A coupon is valid through the end of May 1, 2026 in `Asia/Ho_Chi_Minh`. Use `LocalDate`, `ZoneId`, and `InstantSource` to compute the exclusive expiration instant at the start of the next day. Write tests for before and exactly at that instant.

### Exercise 6 — Distinguishing Wall-Clock and Monotonic Time

A request needs a 2-second timeout. Explain why `InstantSource` is not the best tool for measuring elapsed time. Write a snippet using `System.nanoTime()` to measure processing duration.

### Exercise 7 — Dependency Design

An application has three services: token expiration, local-date reporting, and internal timeout measurement. Select the appropriate time dependency for each service and explain:

- `InstantSource`.
- `Clock`.
- `System.nanoTime()`.

## 16. Official Java 17 Documentation

- [Java SE 17 API — InstantSource](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/InstantSource.html): time source interface, `system`, `fixed`, `offset`, `tick`, and `instant` methods.
- [Java SE 17 API — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): time-zone-aware clock and factories like `systemUTC`, `fixed`, `offset`.
- [Java SE 17 API — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): representing points on the timeline and temporal arithmetic.
- [Java SE 17 API — Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): representing durations and computing remaining duration.
- [Java SE 17 API — System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): monotonic clock for measuring elapsed duration.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): `@Test`, parameterized tests, and `@MethodSource`.

**Key takeaway:** To test expiration rules cleanly, inject `InstantSource` into services instead of calling `Instant.now()` directly. Use `InstantSource.system()` in production and `InstantSource.fixed()` in tests; use `offset` or a mutable fake when simulating time progression. Define the expiration boundary explicitly—typically `now >= expiresAt`—and test the equality case. `InstantSource` fits absolute instants; use `Clock` when time zones are needed and `System.nanoTime()` when measuring timeouts or elapsed durations.
