# Asserting Time, Decimals, and Acceptable Tolerances

In Java/Spring Boot testing, **a proper comparison must reflect the meaning of the data**. An expiration timestamp right at a boundary may require nanosecond-level comparison; a `double` calculation may drift slightly due to binary representation; and monetary amounts usually must be calculated and rounded with `BigDecimal` under an explicit rule. Forcing a single `assertEquals(expected, actual)` across every case easily produces tests that fail for the wrong reason—or worse, tests that pass even when business math is wrong.

This lesson explains how to use **JUnit Jupiter assertions** to check time, decimals, and **tolerances/deltas**; how to eliminate dependence on real system clocks; how to separate **data tolerance** from **execution timeout limits**; and how to choose the right precision when testing services, persistence, and HTTP in Spring Boot.

## 1. Three questions before every assertion

Before picking an assertion, answer:

1. **What quantity is being compared?** An instant (`Instant`), calendar date (`LocalDate`), duration (`Duration`), measured value (`double`), or currency (`BigDecimal`)?
2. **How exact must the contract be?** Exact match, accurate after truncation to milliseconds, or within a defined error tolerance?
3. **Where does nondeterminism come from?** System clocks, timezones/DST, low-precision database timestamps, rounding, binary floating point, networks/threads, or CPU load?

| Result type | Usually suitable assertion | Reason |
| --- | --- | --- |
| Two `Instant`s must be identical | `assertEquals(expected, actual)` | Represents the exact same instant; no delta needed when the clock is controlled |
| Timestamp must be before/after a deadline | `assertTrue(actual.isBefore(deadline))` or `assertFalse(...)` | Verifies ordering rules per business logic |
| Measured timestamp may differ by at most 50 ms | `assertTrue(Duration.between(expected, actual).abs().compareTo(tolerance) <= 0)` | Defines tolerance in time units |
| `double` calculation result | `assertEquals(expected, actual, delta)` | Allows intentional absolute error |
| Money with required scale/rounding | `assertEquals(new BigDecimal("..."), actual)` | Compares both value and scale |
| Two `BigDecimal`s only need numeric equality | `assertEquals(0, expected.compareTo(actual))` | Ignores scale differences while comparing numeric values |
| Operation must finish within a time budget | `assertTimeout(Duration, executable)` | Measures execution duration, not business timestamps |

**Never pick a delta just to make a test turn green.** Tolerances must come from domain meaning or system precision limits; a test checking a currency calculation that is off by 1 unit must not allow a 1-unit delta if the requirement demands exact precision.

## 2. Why `double` decimal values may not be strictly equal

`float` and `double` use **binary** floating-point representation. Many decimal fractions, such as `0.1` and `0.2`, have no finite binary representation. Addition can yield a value close to `0.3` rather than equal to the literal `0.3` converted to `double`.

Java 17+ example:

```java
public class FloatingPointDemo {
    public static void main(String[] args) {
        double actual = 0.1 + 0.2;

        System.out.println(actual);
        System.out.println(actual == 0.3);
        System.out.println(Math.abs(0.3 - actual) < 1e-12);
    }
}
```

Run:

```bash
javac FloatingPointDemo.java
java FloatingPointDemo
```

Exact stdout:

```text
0.30000000000000004
false
true
```

Explanation:

- `0.1 + 0.2` produces a `double` slightly larger than the value represented by the literal `0.3`.
- `==` returns `false` because the two `double` values have different bit patterns.
- The absolute distance is smaller than `1e-12`, so the illustrative tolerance check prints `true`.

**Note:** `1e-12` only fits illustrating this tiny addition example, not every measurement. If a quantity represents distance in km, percentages, seconds, or temperatures, choose the tolerance according to **the unit and acceptable accuracy**.

## 3. Using `assertEquals(expected, actual, delta)` in JUnit Jupiter

For `double` values, JUnit Jupiter provides:

```java
assertEquals(expectedDouble, actualDouble, delta);
```

`delta` is the **maximum absolute error**. Under standard semantics, the comparison succeeds when the difference does not exceed the allowed margin, with JUnit's special rules for floating-point edge values such as `NaN` and `Infinity`. Do not assume `delta = 0.01` automatically allows **1%**: it means **0.01 units of measurement**.

Example of an actual calculation check:

```java
@Test
void floatingPointSumUsesAJustifiedTolerance() {
    double actual = 0.1 + 0.2;

    assertEquals(0.3, actual, 1e-12);
}
```

This is a **method inside a JUnit test class** with static import `org.junit.jupiter.api.Assertions.assertEquals` and `@Test` from `org.junit.jupiter.api.Test`; it uses a direct expression to make the phenomenon easy to observe. Below, we test real production code rather than formulas inside the test itself.

Choosing tolerance:

- If the requirement states "accurate within 0.01 °C", `delta = 0.01` has exact meaning in °C.
- If the requirement states "within 0.1% of the expected value", compute **relative tolerance** instead of passing `0.001` directly as an absolute delta.
- If the requirement states "final price must be accurate to 2 decimal places rounded HALF_UP", use `BigDecimal` and compare the rounded value per the rule rather than allowing arbitrary deltas.

Regarding floating-point special values, `NaN` can be treated by JUnit as equal to `NaN` in `double` assertions. Therefore, if the domain requires valid finite measurements, **check finiteness first**:

```java
assertTrue(Double.isFinite(actual), "Result must be finite");
assertEquals(0.3, actual, 1e-12);
```

Do not use a huge tolerance to hide logic bugs—for example, letting actual `0.8` pass against expected `0.3` because `delta = 1.0`. Tolerance accommodates **well-understood** representation or measurement error; it must never relax business contracts.

## 4. Complete example: expiration policy, money, and measurements

Let us build a small class with three independent responsibilities to illustrate three assertion styles:

1. An entitlement **expires as soon as the current time is greater than or equal to the deadline**.
2. An invoice calculates total with tax, rounded to **2 decimal places using HALF_UP**.
3. A measurement function adds two `double`s, tolerating binary representation error while rejecting non-finite inputs.

The Spring Boot project uses **Java 17+**, JUnit Jupiter, and Gradle. Example files:

```text
src/
├── main/java/example/testing/AmountAndTimePolicy.java
├── main/java/example/testing/AmountAndTimeDemo.java
└── test/java/example/testing/AmountAndTimePolicyTest.java
```

### 4.1. Production code: externally injected clock

Create `src/main/java/example/testing/AmountAndTimePolicy.java`:

```java
package example.testing;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class AmountAndTimePolicy {
    private final Clock clock;

    public AmountAndTimePolicy(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public boolean isExpired(Instant deadline) {
        Objects.requireNonNull(deadline, "deadline");
        return !Instant.now(clock).isBefore(deadline);
    }

    public BigDecimal totalWithTax(
            BigDecimal subtotal, BigDecimal taxRate) {
        Objects.requireNonNull(subtotal, "subtotal");
        Objects.requireNonNull(taxRate, "taxRate");

        if (subtotal.signum() < 0 || taxRate.signum() < 0) {
            throw new IllegalArgumentException(
                    "subtotal and taxRate must be nonnegative");
        }

        return subtotal.multiply(BigDecimal.ONE.add(taxRate))
                .setScale(2, RoundingMode.HALF_UP);
    }

    public double sumMeasurements(double first, double second) {
        if (!Double.isFinite(first) || !Double.isFinite(second)) {
            throw new IllegalArgumentException(
                    "measurements must be finite");
        }
        return first + second;
    }
}
```

Why is this design easy to test?

- `Clock` lets the application use the real system clock in production and a **fixed point in time** in tests. `isExpired` does not depend on the date/time of the machine running the tests.
- `Instant` represents an absolute point on the timeline; testing boundaries avoids timezone dependence.
- `BigDecimal` accepts business decimal values; the method makes clear when rounding happens (after multiplication) and which rounding mode applies.
- `sumMeasurements` validates finite inputs so `NaN` or `Infinity` are not treated as valid measurements. If requirements also forbid overflowing into `Infinity`, check the **result** after addition too; this example illustrates two finite inputs whose sum stays within normal range.

### 4.2. Runnable JUnit Jupiter tests

Create `src/test/java/example/testing/AmountAndTimePolicyTest.java`:

```java
package example.testing;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AmountAndTimePolicyTest {

    private static final Instant DEADLINE =
            Instant.parse("2026-03-01T12:00:00Z");

    private static AmountAndTimePolicy policyAt(Instant now) {
        Clock fixedClock = Clock.fixed(now, ZoneOffset.UTC);
        return new AmountAndTimePolicy(fixedClock);
    }

    @Test
    void beforeDeadline_isNotExpired() {
        AmountAndTimePolicy policy =
                policyAt(DEADLINE.minusNanos(1));

        assertFalse(policy.isExpired(DEADLINE));
    }

    @Test
    void exactlyAtDeadline_isExpired() {
        AmountAndTimePolicy policy = policyAt(DEADLINE);

        assertTrue(policy.isExpired(DEADLINE));
    }

    @Test
    void afterDeadline_isExpired() {
        AmountAndTimePolicy policy =
                policyAt(DEADLINE.plusNanos(1));

        assertTrue(policy.isExpired(DEADLINE));
    }

    @Test
    void taxUsesExactDecimalRounding() {
        AmountAndTimePolicy policy = policyAt(DEADLINE);

        BigDecimal actual = policy.totalWithTax(
                new BigDecimal("19.99"),
                new BigDecimal("0.10"));

        assertEquals(new BigDecimal("21.99"), actual);
        assertEquals(2, actual.scale());
    }

    @Test
    void doubleSumUsesExplicitTolerance() {
        AmountAndTimePolicy policy = policyAt(DEADLINE);

        double actual = policy.sumMeasurements(0.1, 0.2);

        assertTrue(Double.isFinite(actual));
        assertEquals(0.3, actual, 1e-12);
    }

    @Test
    void invalidMeasurementIsRejected() {
        AmountAndTimePolicy policy = policyAt(DEADLINE);

        assertThrows(IllegalArgumentException.class,
                () -> policy.sumMeasurements(
                        Double.NaN, 0.2));
    }

    @Test
    void decimalNumericEqualityMayDifferFromObjectEquality() {
        BigDecimal oneDecimal = new BigDecimal("1.0");
        BigDecimal twoDecimals = new BigDecimal("1.00");

        assertNotEquals(oneDecimal, twoDecimals);
        assertEquals(0, oneDecimal.compareTo(twoDecimals));
    }
}
```

There are **7 test methods**, with the first three proving the expiration boundary **before/at/after the deadline** at 1-nanosecond resolution via `Clock.fixed`. Because time does not advance during tests, these checks never suffer from CPU/scheduler flakiness.

In a Spring Boot/Gradle project with plugins and dependency version management already set up, the relevant section in `build.gradle` (Groovy DSL) is:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **supplementary configuration snippet**, not a standalone `build.gradle`. Run:

```bash
./gradlew test --tests example.testing.AmountAndTimePolicyTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.AmountAndTimePolicyTest"
```

**Expectation:** 7 tests pass if the project has Java 17+ and matching dependencies. Gradle/JUnit output depends on logging configuration, so do not assert a fixed stdout string. These tests **do not need** `@SpringBootTest`, a datasource, or a web server: the three rules are verified at the plain Java boundary.

### 4.3. Compiling and running standalone with javac/java

Create `src/main/java/example/testing/AmountAndTimeDemo.java`:

```java
package example.testing;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

public class AmountAndTimeDemo {
    public static void main(String[] args) {
        Instant deadline = Instant.parse(
                "2026-03-01T12:00:00Z");

        AmountAndTimePolicy policy = new AmountAndTimePolicy(
                Clock.fixed(deadline, ZoneOffset.UTC));

        System.out.println(policy.isExpired(deadline));
        System.out.println(policy.totalWithTax(
                new BigDecimal("19.99"),
                new BigDecimal("0.10")).toPlainString());
        System.out.println(
                policy.sumMeasurements(0.1, 0.2));
    }
}
```

Run from the project root (with JDK available):

```bash
javac -d out src/main/java/example/testing/AmountAndTimePolicy.java src/main/java/example/testing/AmountAndTimeDemo.java
java -cp out example.testing.AmountAndTimeDemo
```

Exact stdout:

```text
true
21.99
0.30000000000000004
```

`true` shows the "expires right at the deadline" contract; `21.99` shows tax multiplication rounded; the last value exposes `double` binary error. This command only runs a plain Java demo; **the JUnit assertions are executed by Gradle/the test runner** above.

## 5. Testing points in time with `Instant`, `Clock`, and `Duration`

### 5.1. Exact instant, before/after, and inclusive vs. exclusive boundaries

`Instant` represents a point on the timeline, making it suitable for `expiresAt`, `createdAt`, `processedAt`, and `scheduledAt` when the contract cares about an absolute point in time.

Suppose production code says:

```java
return !Instant.now(clock).isBefore(deadline);
```

This means **now >= deadline** is expired. Because `isBefore` returns `false` when two instants are equal, negating it yields `true` right at the deadline. The three most important tests:

| `now` relative to deadline | Expected `isExpired` |
| --- | --- |
| `deadline.minusNanos(1)` | `false` |
| `deadline` | `true` |
| `deadline.plusNanos(1)` | `true` |

If the business defines "expires only strictly **after** the deadline", the corresponding expression is `Instant.now(clock).isAfter(deadline)`, and the test at the exact deadline must expect `false`. No single boundary comparison fits every application: **the contract defines inclusivity**.

To assert an exact instant:

```java
Instant expected = Instant.parse("2026-03-01T12:00:00Z");
Instant actual = Instant.parse("2026-03-01T12:00:00Z");

assertEquals(expected, actual);
```

This snippet lives inside a test method; `Instant.equals` compares timestamps to the full precision represented by both objects. Do not convert to strings manually when the goal is comparing temporal meaning. If a public API returns an **ISO-8601 string in a fixed format**, add a separate formatting test at the serializer boundary.

### 5.2. `Clock.fixed` to eliminate real-time dependence

**Do not write boundary tests like:**

```java
Instant deadline = Instant.now().plusMillis(5);
assertFalse(service.isExpired(deadline));
```

If the service runs slowly, the host is under load, or a debugger pauses execution, 5 ms can elapse before the assertion runs. The test fails randomly even when logic has not changed.

Better design: **inject `Clock`**. Production can supply:

```java
@Bean
Clock applicationClock() {
    return Clock.systemUTC();
}
```

This is a **Spring configuration method snippet** that belongs inside a `@Configuration` class / bean declaration site with appropriate imports; it is not a standalone Java file. Unit tests build `Clock.fixed(...)` and pass it directly via the constructor as shown in the full example. When simulating "advance 1 second", pass another fixed clock:

```java
Instant t0 = Instant.parse("2026-03-01T12:00:00Z");

Clock before = Clock.fixed(
        t0.minusSeconds(1), ZoneOffset.UTC);
Clock after = Clock.fixed(
        t0.plusSeconds(1), ZoneOffset.UTC);
```

No `Thread.sleep` needed. If a component needs to observe time advancing continuously within a single test, use a mutable/adjustable test clock rather than waiting on wall-clock time. Never assume `Clock.fixed` ticks forward on its own; it always returns the configured instant.

### 5.3. Comparing durations and unit-aware tolerances

`Duration` represents an elapsed time span, commonly used for timeouts, measured latency, TTLs, and time between two events. When two durations must match identically:

```java
Duration expected = Duration.ofSeconds(90);
Duration actual = Duration.between(
        Instant.parse("2026-03-01T12:00:00Z"),
        Instant.parse("2026-03-01T12:01:30Z"));

assertEquals(expected, actual);
```

If the contract permits timestamps to drift by **at most 50 ms**, compare the error using `Duration` itself:

```java
Instant expected = Instant.parse(
        "2026-03-01T12:00:00Z");
Instant actual = expected.plusMillis(35);
Duration tolerance = Duration.ofMillis(50);

Duration difference =
        Duration.between(expected, actual).abs();

assertTrue(difference.compareTo(tolerance) <= 0,
        () -> "Time difference: " + difference);
```

`Duration.between(expected, actual)` is signed: negative if `actual` is before `expected`, positive if after. `abs()` measures two-sided magnitude. `compareTo(...) <= 0` treats **exactly 50 ms as acceptable**. If the contract requires strictly less, use `< 0`. These snippets live **inside a test method**, requiring imports from `java.time` and JUnit.

A 50 ms tolerance must be justified, such as known clock-sync drift between two components or measurement source precision. With `Clock.fixed` and pure logic, a 50 ms tolerance window is usually unnecessary.

### 5.4. Timezones, DST, and precision

- `Instant` represents an absolute point in time; `ZonedDateTime` carries a timezone; `OffsetDateTime` carries an offset. Two values in different timezones can refer to the same instant—when the contract compares **instants**, convert with `toInstant()` before comparing.
- `LocalDate` is a **calendar date**, not an instant; useful for birthdays or business-day deadlines. When determining "today" in Vietnam or UTC, supply the official business `ZoneId`. Never derive a date from an `Instant` without knowing the timezone.
- `LocalDateTime` **carries no timezone or offset**. Never treat two `LocalDateTime` values from two systems as representing the same absolute instant without an explicit timezone rule.
- DST can make a calendar day **23 or 25 hours** long, whereas `Duration.ofDays(1)` is always 24 hours. When the rule means "same local wall-clock time the next day", use a zoned date-time model; when it means "exactly 24 hours later", use `Duration`.
- Persistence/JSON layers may round or truncate nanoseconds down to microseconds or milliseconds. If data only has millisecond precision **by contract**, explicitly normalize both sides with `truncatedTo(ChronoUnit.MILLIS)` before comparing. Never truncate precision merely to make a bug disappear.

Example when the public contract specifies millisecond-precision timestamps:

```java
Instant expected = Instant.parse(
        "2026-03-01T12:00:00.123456Z");
Instant received = Instant.parse(
        "2026-03-01T12:00:00.123Z");

assertEquals(
        expected.truncatedTo(ChronoUnit.MILLIS),
        received.truncatedTo(ChronoUnit.MILLIS));
```

Because the first timestamp has an extra 456 microseconds and the contract only specifies milliseconds, both normalize to `2026-03-01T12:00:00.123Z`. This test requires importing `java.time.temporal.ChronoUnit` and an explicit rule that sub-millisecond fractions are **truncated**, not rounded.

## 6. Absolute tolerance, relative tolerance, and values near zero

### 6.1. Absolute tolerance

With expected `100.0` and actual `100.004` (in °C or another unit), an absolute delta of `0.01` allows a difference up to **0.01 units**. JUnit:

```java
assertEquals(100.0, 100.004, 0.01);
```

When the contract states an error bound in output units, this is clear and easy to review.

### 6.2. Relative tolerance

For quantities spanning from `0.001` to `1_000_000`, a single absolute threshold can be far too tight for large numbers or far too loose for small ones. If the requirement is "at most 0.1% relative error", one common formulation is:

```text
allowed = max(absoluteFloor,
              relativeRate × max(|expected|, |actual|))
pass when |actual − expected| ≤ allowed
```

`absoluteFloor` prevents the threshold from collapsing to 0 near zero. Pick the exact formula per domain; some domains use `|expected|` in the denominator instead of the two-sided max. Tests must express **the agreed formula**, not an invented tolerance.

Illustrative **assertion helper method** for use inside a test class:

```java
static void assertClose(
        double expected,
        double actual,
        double absTolerance,
        double relTolerance) {

    assertTrue(Double.isFinite(expected));
    assertTrue(Double.isFinite(actual));
    assertTrue(absTolerance >= 0 && relTolerance >= 0);

    double scale = Math.max(
            Math.abs(expected), Math.abs(actual));
    double allowed = Math.max(
            absTolerance, relTolerance * scale);

    assertTrue(Math.abs(actual - expected) <= allowed,
            () -> "expected=" + expected
                    + ", actual=" + actual
                    + ", allowed=" + allowed);
}
```

This helper assumes `expected` and `actual` are finite and tolerances are valid; in specialized numerical test code, also watch for overflow during subtraction or multiplication at extreme magnitudes. For ordinary measurements, this clearly illustrates **combining absolute and relative tolerance**.

**Example application:** when a calculation returns roughly `1_000_000` with a 0.1% relative tolerance, the allowed error scales up to about `1_000` (unless the contract sets a stricter cap). Near zero, `absoluteFloor` keeps the relative ratio from becoming meaningless. If the real problem requires monetary precision, never use this relative-tolerance formula instead of `BigDecimal` comparisons.

### 6.3. Selecting boundary cases for tolerances

For an absolute tolerance of 0.01, include cases such as:

| Case | Expected | Actual | Purpose |
| --- | ---: | ---: | --- |
| Exact match | 10.00 | 10.00 | Exact value passes |
| Small drift | 10.00 | 10.005 | Passes when threshold is 0.01 |
| Clear error | 10.00 | 10.02 | Must fail |
| Negative values | -10.00 | -10.005 | Checks signed two-sided math |
| NaN/Infinity | 10.00 | NaN or Infinity | Must not pass when finite numbers are required |
| Very close to 0 | 0.00 | 0.000001 | Verifies whether absolute or relative tolerance applies |

Do not rely on these values to test **exact equality at the `double` tolerance boundary** because decimal literals themselves can suffer representation error. If a test needs an exact boundary, use `BigDecimal` or integer minor units; if testing general tolerance behavior, choose points clearly inside or outside the boundary to avoid binary-rounding noise.

## 7. Currency and exact decimals: `BigDecimal`

### 7.1. Why should money not be calculated directly with `double`?

`double` works well for many approximate measurements and scientific calculations, but binary rounding errors usually clash with monetary rules requiring exact decimal places. `BigDecimal` stores a decimal value via an unscaled integer and an explicit scale; rounding rules are declared explicitly.

**Construct `BigDecimal` from a string or an intentional decimal value**:

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = BigDecimal.valueOf(0.1);
```

Both represent decimal `0.1` as intended in this example. Avoid `new BigDecimal(0.1)` when aiming for exact decimal `"0.1"`, because the `double` constructor preserves the actual binary approximation near 0.1, introducing unexpected trailing digits.

### 7.2. `equals` and `compareTo` have different contracts

`BigDecimal.equals(...)` requires both **numeric value and scale** to match; `compareTo(...) == 0` checks **numeric equality**:

```java
BigDecimal left = new BigDecimal("2.0");
BigDecimal right = new BigDecimal("2.00");

assertNotEquals(left, right);
assertEquals(0, left.compareTo(right));
```

When should you use which?

- Public output must always carry **2 decimal places**, including `2.00`: `assertEquals(new BigDecimal("2.00"), actual)` checks both value and scale.
- Only numeric monetary value matters, not representation: `assertEquals(0, expected.compareTo(actual))` prevents failing solely because `2.0` and `2.00` have different scales.
- If the API returns string `"2.00"`, check formatting/serialization at its own boundary; `BigDecimal.compareTo` does not prove JSON/string formatting is right.

Do not blindly call `stripTrailingZeros()` on both expected and actual and assume scale rules are proven. That can hide bugs when scale or formatting belongs to the contract.

### 7.3. `RoundingMode` is a business requirement, not an assertion trick

For example, `new BigDecimal("1.005").setScale(2, RoundingMode.HALF_UP)` yields `1.01`. Under `RoundingMode.HALF_EVEN`, tie cases can produce different outcomes depending on the last retained digit. The right mode must come from product/accounting requirements, never picked arbitrarily to make tests pass.

`setScale(2, RoundingMode.HALF_UP)` returns a **new `BigDecimal`**; `BigDecimal` is immutable. Assert results after rounding at the exact business step specified. If rounding per line item before summing differs from summing first and rounding once, tests must reflect the specified order.

Example:

```java
BigDecimal rounded = new BigDecimal("1.005")
        .setScale(2, RoundingMode.HALF_UP);

assertEquals(new BigDecimal("1.01"), rounded);
```

When dividing `BigDecimal`, a non-terminating decimal like `1 / 3` throws `ArithmeticException` unless precision/rounding rules are supplied. Use `divide(divisor, scale, roundingMode)` or `MathContext` per contract and assert the rounded result; do not "work around" it by converting through `double`.

### 7.4. Integer minor units

In domains with a stable smallest unit (such as cents), storing and computing in `long` enables exact comparisons and avoids repeated rounding. However, define the unit, overflow bounds, and currency conversion/tax rules carefully; not every currency uses two decimal places. Choose `long` or `BigDecimal` based on the system's money model, and make sure assertions express the right unit.

## 8. `assertTimeout` differs from instant assertions and `Duration` checks

JUnit Jupiter can assert the *execution duration* of a callback via:

```java
assertTimeout(Duration.ofSeconds(2), () -> {
    // Invoke code required to finish within 2 seconds
    operationUnderTest();
});
```

This is an **illustrative snippet inside a test method**, assuming `operationUnderTest()` exists; it is not a runnable class. With `assertTimeout`, the callback runs on the **current thread** and is not aborted mid-execution when the threshold passes: the assertion fails **after the callback finishes**. If the callback hangs forever, `assertTimeout` alone will not stop the test.

Another variant is `assertTimeoutPreemptively(...)`: the callback runs in a **separate thread** and JUnit attempts to abort it once the timeout expires. This introduces specific risks in Spring: Spring Test transactions are typically bound via `ThreadLocal`, so code on the separate thread may not participate in the test-managed transaction/rollback as expected. As a result, DB changes might commit even when the test expects rollback. **Do not casually swap `assertTimeout` for `assertTimeoutPreemptively` in transactional Spring tests.**

Three concepts to keep separate:

| Goal | What is measured | Solution |
| --- | --- | --- |
| Token expires when `now >= deadline` | Business point in time | `Clock.fixed` + `Instant` + boolean assertion |
| Event occurs within ±50 ms of expected timestamp | Difference between two instants | `Duration.between(...).abs()` and unit-aware tolerance |
| Calculation/response finishes within 2 s | Execution elapsed time | `assertTimeout` or appropriate timeout mechanism |

**Performance tests are noisy** due to CI load, GC, JIT warmup, Spring context startup, networking, and scheduling. Timeouts close to average measurements easily cause flakiness. For pure algorithms, verify functional correctness via output values; enforce runtime limits separately if an actual SLA applies, using dedicated performance tests rather than tight wall-clock assertions in CI.

JUnit's `@Timeout`, HTTP client timeouts, database statement timeouts, and HTTP SLAs serve different purposes; never treat a single elapsed-time assertion as proof of production timeout configuration.

## 9. Placing assertions at the right Spring Boot boundaries

### 9.1. Unit tests for time and numeric rules

`AmountAndTimePolicyTest` uses `new AmountAndTimePolicy(Clock.fixed(...))` without booting Spring. This validates business rules accurately, quickly, and deterministically. The subject under test is the **real class**; only `Clock` is swapped.

If the real service receives its clock from a Spring bean, unit tests alone do not prove the bean is wired properly. Write a separate configuration or integration test when bean wiring is a real risk.

### 9.2. HTTP/JSON: verify formatting and timezone after serialization

Suppose an endpoint returns an `Instant` via Jackson JSON. Unit tests verify the deadline rule, but they do not verify whether the JSON response uses ISO-8601, a `Z`/offset suffix, or the expected precision. To prove the HTTP contract, use an MVC slice test (such as `@WebMvcTest` + `MockMvc`) or integration test with the real Jackson configuration.

Parse received timestamps as `Instant` when the contract cares about **the point in time**; if the contract mandates an **exact string representation**, add assertions for formatting too. For monetary JSON values, check both numeric value and formatting/trailing zeros if the API specification requires them; do not infer formatting correctness from `BigDecimal.compareTo`.

### 9.3. Persistence: clarify precision and time sources

A database `TIMESTAMP` column may only store millisecond or microsecond precision under a given configuration, whereas Java `Instant` holds nanoseconds. If code creates `Instant.now(clock)`, persists to the DB, and reads it back, `assertEquals` can fail due to DB truncation. Decide how to normalize or set round-trip tolerance based on the schema and storage contract; only repository/integration tests against a real DB prove this behavior.

If `createdAt` is **database-generated** (`DEFAULT CURRENT_TIMESTAMP`) or populated by Hibernate/database annotations, injecting `Clock.fixed` into a service **does not necessarily control** that timestamp. Test the actual clock source of that field while checking timezone and precision. Never assume "the service clock controls every timestamp" when the database or framework generates timestamps.

In transactional Hibernate/JPA tests, distinguish when an entity is persisted, flushed, and committed; DB-generated values may only appear after flush/refresh. Compare timestamps only after real values are populated and at the precision the DB actually guarantees.

### 9.4. Asynchronous timing and eventual consistency

When logic runs via a scheduler or message broker, do not use `Thread.sleep(100)` and assume the event finished. Prefer an observable signal (future, latch, test probe, or bounded-timeout polling), then assert timestamps and values. Even with bounded polling, keep two failure reasons separate: the behavior never happened versus the timestamp when it happened fell outside business bounds.

When verifying timezone-based schedules, test before/at/after the trigger and on DST transition days for the relevant timezone; comparing local date-time strings alone does not prove the right UTC instant.

## 10. Boundary cases to cover

### Time

- **One smallest contract unit before deadline:** not expired yet.
- **Exactly at deadline:** expired or not according to the stated inclusive/exclusive rule.
- **One unit after deadline:** expired.
- **Across midnight or date rollovers:** evaluate dates in the business timezone, not the CI host's timezone.
- **Same instant with different offsets:** compare `toInstant()` when comparing absolute instants.
- **DB/JSON round-trip:** verify precision intentionally.
- **Clock near boundaries:** never rely on a live `Instant.now()` ticking between assertions.

### Floating-point and tolerances

- Expected equals actual, actual drifts slightly less than tolerance, and actual drifts slightly more than tolerance.
- Negative values, values near zero, very large values; is the tolerance still sensible in its unit?
- `NaN`, `+Infinity`, `-Infinity`: are non-finite inputs/outputs allowed?
- Would changing addition to subtraction or flipping a sign be caught by the tests?
- When using relative tolerance, is there an **absolute floor** near zero?
- When using a delta, could a clearly wrong actual value still slip past?

### `BigDecimal`

- Scale and rounding per contract: e.g., `1.005 → 1.01` under `HALF_UP` at 2 decimal places.
- Two numerically equal values with different scales: pick `equals` or `compareTo` matching the goal.
- Negative amounts, zero, 0% tax rate, very large values/overflow bounds if specified by domain.
- Non-terminating division: explicit rounding rules, never falling back to `double`.
- DB storage and JSON serialization preserve the required precision and format.

## 11. Common mistakes

**1. Calling `assertEquals(0.3, 0.1 + 0.2)` and concluding the program is broken.** `double` math has representation error. If approximate floating-point math is acceptable, use `assertEquals(expected, actual, delta)` with an appropriate tolerance; for exact money, use `BigDecimal`.

**2. Passing a huge `delta` to silence a failing test.** A bug off by 50% still passes if delta is too wide. Tie tolerances to requirements and add a negative check where clearly wrong actual values must fail.

**3. Treating `assertEquals`'s delta as a percentage.** Delta is an **absolute error** in the quantity's unit. If you need a relative ratio, compute it explicitly or use an appropriate matcher and document the normalization.

**4. Ignoring `NaN` and `Infinity`.** Approximate assertions may handle special values according to library rules. When the domain allows only finite numbers, assert `Double.isFinite` or verify production validation.

**5. Comparing `BigDecimal` with `equals` when only numeric value matters.** `2.0` and `2.00` are not equal under `equals`; if scale is not in the contract, use `compareTo(...) == 0`. If scale is in the contract, keep `equals` and test scale explicitly.

**6. Calling `new BigDecimal(0.1)` expecting exact `0.1`.** The `double` constructor preserves the binary approximation rather than the decimal literal. Use `new BigDecimal("0.1")` or `BigDecimal.valueOf(0.1)` as appropriate.

**7. Calling `Instant.now()` repeatedly in timeout/expiry tests.** The clock keeps ticking, making boundary tests flaky. Inject `Clock` and fix time when testing time-based rules.

**8. Mixing `LocalDateTime` and `Instant` while ignoring timezones.** `LocalDateTime` has no timezone; converting to an instant requires a specific zone/offset. Verify the time contract before comparing.

**9. Truncating timestamps to milliseconds everywhere just to pass tests.** That can mask precision loss when an API requires microseconds or nanoseconds. Normalize only to the precision actually promised by storage/transport contracts.

**10. Swapping `assertTimeoutPreemptively` into transactional Spring tests as a harmless alternative.** A separate thread may not inherit the test-managed transaction. Choose timeout mechanisms mindful of state, interruption, and rollback risks; never ignore side effects just because the test passed.

**11. Using `Thread.sleep` to test time-based business rules.** Tests become both slow and scheduling-flaky. Use `Clock.fixed`/test clocks for business rules, and bounded observable signals for asynchronous work.

**12. Testing only middle-of-the-range inputs and skipping boundaries.** Bugs switching `>` and `>=` hide right at the deadline; rounding bugs hide at ties like `1.005`; tolerance bugs hide near the threshold.

## 12. Checklist when reviewing time and numeric assertions

Before concluding a test proves the requirement:

- Did I clearly identify the **quantity, unit, and required precision** to compare?
- For points in time, did I use the right `Instant`/`ZonedDateTime`/`LocalDate` and business timezone?
- If logic depends on the current time, does the test control the `Clock` source and cover before/at/after boundaries?
- If data crosses a database or JSON boundary, are precision and formatting verified at the proper boundary?
- For `double`, is the tolerance absolute or relative, and where did that number come from?
- Does the test catch clearly wrong outputs, invalid `NaN`/`Infinity`, and near-zero values?
- For money, did it use `BigDecimal` or integer minor units, round per policy, and choose the right `equals`/`compareTo`?
- If using `assertTimeout`, did I distinguish **execution duration** from **business points in time** and account for thread/transaction risks?
- Is the test independent of host clock, CI load, `sleep`, default timezone, and shared data?
- Does each assertion justify pass/fail from the contract rather than merely aiming for green tests?

**Key takeaway:** reliable time testing starts with **a controllable clock and clearly defined boundaries**; approximate calculation testing uses **justified, unit-aware tolerances**; exact decimal and currency testing uses **`BigDecimal` with explicit scale and rounding rules**. Choose assertions that express the data's real contract, then exercise the boundaries to ensure bugs are caught.