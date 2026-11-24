# Injecting Clock into Your Design for Time-Based Logic Testing

## 1. Why Is Time a Dependency That Must Be Controlled?

Business rules frequently depend on the question “**what time is it right now?**”: has a login session expired, is an order still within its cancellation window, has a discount code become active yet, can an application still be submitted on the closing day, or how overdue is an alert?

Calling **Instant.now()**, **LocalDate.now()**, or **System.currentTimeMillis()** directly inside business logic ties tests to the real wall clock. When a test prepares a timestamp at 10:00:00 and the code runs milliseconds later, boundary comparisons can yield unexpected outcomes. Tests executed near midnight can fail depending on wall-clock timing; tests on machines in different timezones can also produce different results.

In Java 17+, **java.time.Clock** is the standard abstraction for obtaining time. Pass a Clock into business objects via constructor; production code uses a real Clock, whereas unit tests supply a fixed Clock created by the test. This is a form of **dependency injection** and **controlling non-deterministic sources**, just like injecting a repository or random generator.

After this lesson, you will be able to:

- Design services that accept **Clock** rather than reading system time directly.
- Distinguish **Instant**, **Duration**, **LocalDate**, **ZoneId**, and what each represents in business rules.
- Use **Clock.fixed(...)** and **Clock.offset(...)** to test before, exactly at, and after expiration timestamps.
- Provide a Clock bean in Spring Boot and replace it in integration tests without modifying production code.
- Avoid subtle bugs involving timezones, daylight saving time (DST), calendar-day arithmetic, and reading “now” multiple times.
- Understand the boundary: Clock controls only **code that actually uses that Clock**; it does not alter database clocks, external schedulers, or third-party services.

**The goal is not “mock every time call”.** The goal is moving the choice of time source out of business algorithms so logic always runs at an explicit, reproducible point in time.

## 2. Before and After: From Implicit Time Reads to Constructor-Injected Clock

**Design prone to flaky tests:**

~~~java
import java.time.Instant;

class ExpirationPolicyBefore {
    boolean expired(Instant expiresAt) {
        return !Instant.now().isBefore(expiresAt);
    }
}
~~~

If a test constructs expiresAt via Instant.now().plusMillis(1), results can flip depending on CPU speed and OS scheduling. Setting expiresAt far in the past stabilizes the test, but fails to prove the rule **right at the boundary**.

**Testable design:**

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

class ExpirationPolicyAfter {
    private final Clock clock;

    ExpirationPolicyAfter(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    boolean expired(Instant expiresAt) {
        Objects.requireNonNull(expiresAt);
        return !clock.instant().isBefore(expiresAt);
    }
}
~~~

These are two standalone illustrative classes demonstrating the mechanism, not complete Spring Boot code. In the second class, Clock is injected externally. **clock.instant()** represents “now” from the chosen time source; tests can supply a Clock pinned to an exact instant.

Critical comparison operator: **!now.isBefore(expiresAt)** means **now >= expiresAt**. That means the session **is already expired at exact expiresAt**. A different specification might allow usage until the end of that instant; in that case, update the condition and reflect it in tests. Never guess equality boundaries from the method name “expired” alone.

Flow diagram:

~~~text
Spring Boot Application                   Unit Test
          |                                   |
          v                                   v
    Clock.systemUTC()                 Clock.fixed(t0, UTC)
          |                                   |
          +-----------------+-----------------+
                            |
                            v
                   TokenService(Clock)
                            |
                            v
                       clock.instant()
                            |
                            v
               expiration / remaining-time rules
~~~

TokenService logic remains identical in both environments; only the supplied Clock differs.

## 3. Understanding java.time.Clock API and Time Types

**Clock** is an abstraction with three core capabilities: retrieving the current instant **instant()**, providing a timezone **getZone()**, and deriving a Clock with another timezone via **withZone(...)**. Common factories:

| Clock / API | Behavior | When to use |
|---|---|---|
| Clock.systemUTC() | Reads system clock with ZoneOffset.UTC | Default application Clock bean |
| Clock.system(ZoneId.of("Asia/Ho_Chi_Minh")) | Reads system clock in the specified zone | Date/time conversion logic tied to a business timezone |
| Clock.systemDefaultZone() | Depends on OS/JVM timezone | Avoid as an implicit default for business rules requiring a specific zone |
| Clock.fixed(instant, zone) | Always returns the same Instant | Deterministic point-in-time tests without waiting |
| Clock.offset(baseClock, duration) | Returns baseClock's instant plus offset | Testing before/after deadlines; remains fixed if baseClock is fixed |
| Clock.tick(baseClock, duration) | Truncates/rounds time to discrete steps | Systems requiring coarse granularity; unsuitable by default for millisecond boundary tests |
| Instant.now(clock) | Obtains Instant from the passed Clock | Writing Instant business logic while staying testable |
| LocalDate.now(clock) | Obtains date in the Clock's zone | When “today” in the Clock's timezone is desired |

Two semantically equivalent ways to get “now” from a Clock are **clock.instant()** and **Instant.now(clock)**. Pick one consistently across the project. Calling **Instant.now()** without a Clock reads system time directly and should be avoided in testable business rules. **LocalDate.now()** without a Clock likewise reads the system default zone.

Distinguishing date/time classes:

- **Instant:** An absolute point on the UTC timeline, e.g., 2026-11-08T10:00:00Z. Suitable for issuedAt, expiresAt, createdAt, event timestamps, and elapsed-second/minute comparisons.
- **Duration:** An exact time span measured in seconds/nanoseconds, e.g., 15 minutes or 24 hours.
- **LocalDate:** A calendar date, e.g., 2026-11-08; by itself it **has no time-of-day, timezone, or Instant**. Suitable for closing dates, birthdates, or delivery dates defined locally.
- **LocalDateTime:** Date + time **without zone/offset**. You cannot map a LocalDateTime to a unique Instant without zone rules; during DST transitions, an hour may not exist or may occur twice.
- **ZonedDateTime:** Date and time paired with a ZoneId and offset rules, suitable for local-calendar calculations.
- **ZoneId:** A region identifier with time rules, e.g., Asia/Ho_Chi_Minh or America/New_York. ZoneOffset.UTC is a fixed zero offset and does not represent regional DST rules.

**Store expiration timestamps as Instant** when the rule says “after exactly 15 minutes”. When the rule says “submittable through the end of November 8 in Vietnam time”, use **LocalDate + ZoneId** to interpret the business date accurately, converting to Instant when exchanging or persisting absolute timestamps.

## 4. Lock Down the Spec Before Writing Tests: Comparisons and Boundary Points

Suppose a session is issued at **2026-11-08T10:00:00Z** with a **15-minute** lifetime. Its expiration timestamp is **2026-11-08T10:15:00Z**.

| Check time | Relation to expiresAt | Expected expired |
|---|---|---|
| 10:00:00Z | Just issued | false |
| 10:14:59Z | One second before boundary | false |
| 10:15:00Z | Exact boundary | true |
| 10:15:01Z | One second after boundary | true |
| 10:16:00Z | One minute after boundary | true |

When calculating “remaining time”, this example returns **Duration.ZERO** once expired, rather than a negative duration. This is **this lesson's rule**; another real system might represent overdue duration as negative. Never alter expected values if requirements differ.

Also include invalid cases: null lifetime, Duration.ZERO, and negative Duration; missing/blank session owner; invalid tokens whose expiresAt is not after issuedAt. These inputs are explicitly rejected to prevent constructing tokens with invalid lifetimes.

Three complementary test groups:
1. **Values upon issuance:** issuedAt equals the Instant supplied by Clock, and expiresAt equals issuedAt + TTL.
2. **Expiration boundaries:** false before the boundary, true at and after the boundary.
3. **Inputs and invariants:** positive lifetime, non-blank subject, expiresAt strictly after issuedAt.

Do not use Thread.sleep(...) in these tests. Sleep slows suites down and causes flakiness under OS/JVM scheduling, especially around tight boundaries.

## 5. Complete Spring Boot 3.3.5 + Java 17 + JUnit Jupiter Project Example

Below is a complete set of source and test files. The project contains a session issuance/validation service and a business-day policy; both accept Clock via constructor. Unit tests need neither a database nor an HTTP port.

### 5.1. File structure

~~~text
settings.gradle
build.gradle
src/main/java/demo/time/TimeTestingApplication.java
src/main/java/demo/time/ApplicationClockConfiguration.java
src/main/java/demo/time/SessionToken.java
src/main/java/demo/time/TokenService.java
src/main/java/demo/time/BusinessDayPolicy.java
src/test/java/demo/time/TokenServiceTest.java
src/test/java/demo/time/BusinessDayPolicyTest.java
src/test/java/demo/time/ClockSpringIntegrationTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'clock-business-testing'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

Spring Boot starter-test provides JUnit Jupiter and the required testing libraries. **useJUnitPlatform()** tells Gradle to execute tests on JUnit Platform. The example uses Gradle 8.x compatible with Spring Boot 3.3.5; if a project includes Gradle Wrapper, prefer the Wrapper so every machine runs the same Gradle version.

**src/main/java/demo/time/TimeTestingApplication.java**

~~~java
package demo.time;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TimeTestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(TimeTestingApplication.class, args);
    }
}
~~~

**src/main/java/demo/time/ApplicationClockConfiguration.java**

~~~java
package demo.time;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ApplicationClockConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

In real applications, **Clock.systemUTC()** reads system time and uses UTC as the default zone. Using UTC keeps timestamps consistent, though it does not eliminate converting to a **business ZoneId** when rules rely on local calendar days. Spring does not automatically replace third-party Instant.now() calls merely because you declared a Clock bean.

### 5.2. Token definition and time invariants

**src/main/java/demo/time/SessionToken.java**

~~~java
package demo.time;

import java.time.Instant;
import java.util.Objects;

public record SessionToken(
        String owner, Instant issuedAt, Instant expiresAt) {

    public SessionToken {
        if (owner == null || owner.isBlank()) {
            throw new IllegalArgumentException("owner must not be blank");
        }
        Objects.requireNonNull(issuedAt, "issuedAt");
        Objects.requireNonNull(expiresAt, "expiresAt");
        if (!expiresAt.isAfter(issuedAt)) {
            throw new IllegalArgumentException(
                    "expiresAt must be after issuedAt");
        }
    }
}
~~~

Java records make the data effectively immutable across Instant/String components, while the compact constructor enforces invariants: a non-blank owner and **expiresAt > issuedAt**. The record does not generate clock values; it stores received data. Enforcing time invariants at construction blocks malformed tokens early.

### 5.3. Service accepting Clock via constructor

**src/main/java/demo/time/TokenService.java**

~~~java
package demo.time;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class TokenService {

    private final Clock clock;

    public TokenService(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public SessionToken issue(String owner, Duration lifetime) {
        if (lifetime == null || lifetime.isZero()
                || lifetime.isNegative()) {
            throw new IllegalArgumentException(
                    "lifetime must be positive");
        }

        Instant issuedAt = clock.instant();
        Instant expiresAt = issuedAt.plus(lifetime);
        return new SessionToken(owner, issuedAt, expiresAt);
    }

    public boolean isExpired(SessionToken token) {
        Objects.requireNonNull(token, "token");
        Instant now = clock.instant();
        return !now.isBefore(token.expiresAt());
    }

    public Duration remaining(SessionToken token) {
        Objects.requireNonNull(token, "token");
        Instant now = clock.instant();
        Duration left = Duration.between(now, token.expiresAt());
        return left.isNegative() ? Duration.ZERO : left;
    }
}
~~~

Key details:

- TokenService depends solely on **Clock**. Spring autowires the Clock bean because the class has a single constructor; unit tests can call new TokenService(fixedClock) directly.
- Inside **issue(...)**, **clock.instant() is called exactly once** and expiresAt is computed from that same issuedAt. Calling instant() twice could introduce latency between calls and produce unpredictable boundary values.
- **isExpired(...)** checks now >= expiresAt, treating exact equality with expiresAt as expired.
- **remaining(...)** reads now once, computes Duration.between(now, expiresAt), and clamps negative values to ZERO.
- Duration.plus or Instant.plus can throw on extreme durations exceeding Instant's representable range; if an API accepts client-supplied TTLs, cap them at a valid maximum and test that boundary. This example handles ordinary positive TTLs and does not claim to support every representable Duration.

In a real controller, configured lifetimes can be read from application properties and passed into the service. Never construct a new Clock or call Instant.now() per business invocation.

### 5.4. Business-day policy in a fixed timezone

**src/main/java/demo/time/BusinessDayPolicy.java**

~~~java
package demo.time;

import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Objects;

public final class BusinessDayPolicy {

    private final Clock clock;
    private final ZoneId businessZone;

    public BusinessDayPolicy(Clock clock, ZoneId businessZone) {
        this.clock = Objects.requireNonNull(clock, "clock");
        this.businessZone =
                Objects.requireNonNull(businessZone, "businessZone");
    }

    public LocalDate today() {
        return clock.instant().atZone(businessZone).toLocalDate();
    }

    public boolean canSubmitThrough(LocalDate cutoffDate) {
        Objects.requireNonNull(cutoffDate, "cutoffDate");
        LocalDate today = today();
        return !today.isAfter(cutoffDate);
    }
}
~~~

This policy takes both **Clock** and **ZoneId**, because “today” is a **calendar date in a specific region**, not just an Instant. canSubmitThrough() means “submissions allowed through the end of cutoffDate in businessZone”. If a rule requires a 17:00 cutoff on that date, model a zoned date-time explicitly rather than reusing an “end of day” check directly.

BusinessDayPolicy here is a plain Java class for unit testing without @Service. When integrating into Spring, register a bean configured with Clock and the configured business zone. Never force a service to implicitly adopt the host machine's timezone.

## 6. Unit Tests: Clock.fixed and Clock.offset for Exact Boundary Checks

**src/test/java/demo/time/TokenServiceTest.java**

~~~java
package demo.time;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TokenServiceTest {

    private static final Instant T0 =
            Instant.parse("2026-11-08T10:00:00Z");

    private final Clock fixedClock =
            Clock.fixed(T0, ZoneOffset.UTC);

    @Test
    void issuedAndExpiryTimesComeFromInjectedClock() {
        TokenService service = new TokenService(fixedClock);

        SessionToken token =
                service.issue("alice", Duration.ofMinutes(15));

        assertEquals("alice", token.owner());
        assertEquals(T0, token.issuedAt());
        assertEquals(T0.plus(Duration.ofMinutes(15)), token.expiresAt());
    }

    @ParameterizedTest(name = "{index}: elapsed={0}s => expired={1}")
    @CsvSource({
            "0, false",
            "899, false",
            "900, true",
            "901, true",
            "960, true"
    })
    void expirationBoundary(
            long elapsedSeconds, boolean expectedExpired) {
        SessionToken token = new TokenService(fixedClock)
                .issue("alice", Duration.ofMinutes(15));

        Clock checkingClock = Clock.offset(
                fixedClock, Duration.ofSeconds(elapsedSeconds));

        TokenService checkingService =
                new TokenService(checkingClock);

        assertEquals(expectedExpired, checkingService.isExpired(token));
    }

    @Test
    void remainingTimeIsClampedAtZero() {
        SessionToken token = new TokenService(fixedClock)
                .issue("alice", Duration.ofMinutes(15));

        TokenService before = new TokenService(
                Clock.offset(fixedClock, Duration.ofMinutes(14)));
        TokenService after = new TokenService(
                Clock.offset(fixedClock, Duration.ofMinutes(16)));

        assertEquals(Duration.ofMinutes(1), before.remaining(token));
        assertEquals(Duration.ZERO, after.remaining(token));
    }

    @Test
    void rejectsZeroNegativeAndMissingLifetime() {
        TokenService service = new TokenService(fixedClock);

        assertThrows(IllegalArgumentException.class,
                () -> service.issue("alice", Duration.ZERO));
        assertThrows(IllegalArgumentException.class,
                () -> service.issue("alice", Duration.ofSeconds(-1)));
        assertThrows(IllegalArgumentException.class,
                () -> service.issue("alice", null));
    }

    @Test
    void rejectsBlankOwner() {
        TokenService service = new TokenService(fixedClock);

        assertThrows(IllegalArgumentException.class,
                () -> service.issue("  ", Duration.ofMinutes(15)));
    }

    @Test
    void rejectsInvalidTokenTimeOrder() {
        assertThrows(IllegalArgumentException.class,
                () -> new SessionToken("alice", T0, T0));
    }

    @Test
    void fixedClockDoesNotAdvanceWhenCalledAgain() {
        assertEquals(T0, fixedClock.instant());
        assertEquals(T0, fixedClock.instant());
        assertFalse(new TokenService(fixedClock).isExpired(
                new SessionToken(
                        "alice", T0.minusSeconds(60), T0.plusSeconds(60))));
        assertTrue(new TokenService(fixedClock).isExpired(
                new SessionToken(
                        "alice", T0.minusSeconds(60), T0)));
    }
}
~~~

**Test breakdown:**

1. issuedAndExpiryTimesComeFromInjectedClock verifies lifetime calculation from exact T0 without wall-clock interference.
2. expirationBoundary uses **@CsvSource** to execute one invocation per elapsedSeconds and expectedExpired pair. **899 seconds = 14 minutes 59 seconds** is still valid; **900 seconds** is right at expiration; **901 seconds** is past expiration. These tight points catch `<` vs `<=` bugs.
3. Clock.offset(fixedClock, Duration.ofSeconds(...)) creates a **new Clock** at T0 plus offset. Because the base is fixed, checks remain deterministic. **Clock.offset does not “advance” or mutate the original fixedClock**.
4. remainingTimeIsClampedAtZero proves the rule never returns negative Durations.
5. rejectsZeroNegativeAndMissingLifetime and rejectsBlankOwner validate invalid inputs.
6. fixedClockDoesNotAdvanceWhenCalledAgain shows the fixed clock never moves between reads, while also verifying the exact boundary now == expiresAt.

All of the tests above are pure JUnit Jupiter unit tests; no Spring ApplicationContext, Mockito mocks, or Thread.sleep are involved. That keeps execution fast and proves TokenService's business logic directly.

**Never use Clock.systemUTC() in boundary tests.** It still reads real wall-clock time; values can drift between setup and assertion. Clock.fixed guarantees consecutive reads return the exact same Instant.

## 7. Unit Tests: Business Dates, Timezones, and DST Transitions

A single instant can fall on **two different calendar dates** across two timezones. For example, 2026-03-08T04:59:59Z is March 8 in UTC yet still the evening of March 7 in America/New_York. Multi-region applications should not rely on ZoneId.systemDefault() merely because a server runs in a given location.

**src/test/java/demo/time/BusinessDayPolicyTest.java**

~~~java
package demo.time;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BusinessDayPolicyTest {

    private static final ZoneId NEW_YORK =
            ZoneId.of("America/New_York");

    @Test
    void oneInstantCanBelongToDifferentCalendarDays() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-03-08T04:59:59Z"),
                ZoneOffset.UTC);

        BusinessDayPolicy inUtc =
                new BusinessDayPolicy(clock, ZoneOffset.UTC);
        BusinessDayPolicy inNewYork =
                new BusinessDayPolicy(clock, NEW_YORK);

        assertEquals(LocalDate.of(2026, 3, 8), inUtc.today());
        assertEquals(LocalDate.of(2026, 3, 7), inNewYork.today());
    }

    @Test
    void deadlineDayIsIncluded() {
        LocalDate cutoff = LocalDate.of(2026, 3, 8);

        BusinessDayPolicy beforeMidnight = new BusinessDayPolicy(
                Clock.fixed(
                        Instant.parse("2026-03-08T04:59:59Z"),
                        ZoneOffset.UTC),
                NEW_YORK);
        BusinessDayPolicy midnight = new BusinessDayPolicy(
                Clock.fixed(
                        Instant.parse("2026-03-08T05:00:00Z"),
                        ZoneOffset.UTC),
                NEW_YORK);
        BusinessDayPolicy nextDay = new BusinessDayPolicy(
                Clock.fixed(
                        Instant.parse("2026-03-09T04:00:00Z"),
                        ZoneOffset.UTC),
                NEW_YORK);

        assertTrue(beforeMidnight.canSubmitThrough(cutoff));
        assertTrue(midnight.canSubmitThrough(cutoff));
        assertFalse(nextDay.canSubmitThrough(cutoff));
    }

    @Test
    void daylightSavingGapDoesNotChangeCalendarDate() {
        Instant beforeTransition =
                Instant.parse("2026-03-08T06:59:59Z");
        Instant afterTransition =
                Instant.parse("2026-03-08T07:00:00Z");

        ZonedDateTime before = beforeTransition.atZone(NEW_YORK);
        ZonedDateTime after = afterTransition.atZone(NEW_YORK);

        assertEquals(1, before.getHour());
        assertEquals(3, after.getHour());
        assertEquals(LocalDate.of(2026, 3, 8), before.toLocalDate());
        assertEquals(LocalDate.of(2026, 3, 8), after.toLocalDate());
    }

    @Test
    void calendarDayAndTwentyFourHoursAreDifferentAtDst() {
        ZonedDateTime noon = ZonedDateTime.of(
                2026, 3, 7, 12, 0, 0, 0, NEW_YORK);

        ZonedDateTime nextCalendarDay = noon.plusDays(1);
        ZonedDateTime twentyFourHoursLater =
                noon.plus(Duration.ofDays(1));

        assertEquals(12, nextCalendarDay.getHour());
        assertEquals(13, twentyFourHoursLater.getHour());
        assertEquals(
                Duration.ofHours(23),
                Duration.between(noon.toInstant(),
                        nextCalendarDay.toInstant()));
    }
}
~~~

**Why does deadlineDayIsIncluded work this way?** The policy canSubmitThrough(cutoffDate) permits submissions **throughout all of cutoffDate in New York**, not merely until the midnight opening that day. In 2026, New York enters daylight saving time on March 8; the following day starts at **2026-03-09T04:00:00Z** (00:00 EDT), so at that instant it must return false for the March 8 cutoff.

**Important note on DST:** When New York clocks jump from 01:59:59 to 03:00:00 on 2026-03-08, only one second elapses on the UTC timeline. Consequently:
- **plusDays(1)** on ZonedDateTime advances one **local calendar day**.
- **plus(Duration.ofDays(1))** adds exactly **24 hours of elapsed real time**.
- On the spring-forward DST day, the span from 12:00 noon on 03/07 to 12:00 noon on 03/08 in New York is **23 hours**.

Do not use Duration.ofDays(1) to mean “next calendar day” when the business rule is based on LocalDate. Conversely, for a TTL “valid for exactly 24 hours”, using a 24-hour Duration is essential even across DST transitions.

## 8. Spring Boot: Registering a Clock Bean and Overriding It in Tests

For unit tests, new TokenService(Clock.fixed(...)) suffices. However, to verify that **Spring wires the right Clock bean into the service**, write an integration test loading the ApplicationContext.

**src/test/java/demo/time/ClockSpringIntegrationTest.java**

~~~java
package demo.time;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@Import(ClockSpringIntegrationTest.FixedClockConfig.class)
class ClockSpringIntegrationTest {

    @Autowired
    TokenService tokenService;

    @Test
    void tokenServiceUsesInjectedPrimaryTestClock() {
        SessionToken token =
                tokenService.issue("linh", Duration.ofMinutes(5));

        assertEquals(
                Instant.parse("2026-11-08T10:00:00Z"),
                token.issuedAt());
        assertEquals(
                Instant.parse("2026-11-08T10:05:00Z"),
                token.expiresAt());
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedClockConfig {

        @Bean
        @Primary
        Clock fixedClockForTest() {
            return Clock.fixed(
                    Instant.parse("2026-11-08T10:00:00Z"),
                    ZoneOffset.UTC);
        }
    }
}
~~~

How it works:
- In normal runs, bean **applicationClock** comes from ApplicationClockConfiguration.
- The test uses @Import(FixedClockConfig.class) to register **fixedClockForTest**, marked **@Primary**.
- When Spring injects a Clock dependency into TokenService, the @Primary bean wins. The test verifies this via the fixed issuedAt.
- The two beans have **different names**; bean definition overriding does not need to be enabled. Using the same name with overriding disabled can prevent the context from starting; prefer @Primary with a distinct name or explicit replacement configuration.
- @TestConfiguration applies only to tests importing it, preventing a fixed Clock from leaking into production runtime.
- This is a **Spring wiring integration test**, slower than unit tests because it boots the context. Do not use @SpringBootTest for every boundary-comparison case; keep most cases in unit tests.

If an application defines multiple Clock beans for distinct purposes (e.g., operational time vs billing time), use @Qualifier or domain-specific abstractions so injection is unambiguous. Relying accidentally on bean names can make tests run with the wrong time source.

## 9. Running the Example and Inspecting Results

In the directory containing build.gradle:

~~~bash
./gradlew test
~~~

On Windows PowerShell when Gradle Wrapper is present:

~~~powershell
.\gradlew.bat test
~~~

The example files cover the full source and Gradle configuration; **./gradlew** exists only when the project includes Gradle Wrapper. If creating a project from scratch without a Wrapper, use a compatible installed Gradle to generate the Wrapper or run gradle test.

When assertions pass, the test task completes successfully. Open **build/reports/tests/test/index.html** to inspect invocation counts and statuses. In the report, confirm:
- The issuance test returns expected issuedAt/expiresAt.
- @CsvSource cases cover **just before**, **at**, and **just after** expiration.
- Date tests compare UTC and New York at the same Instant.
- The DST test checks 01:59:59 → 03:00:00 with unchanged calendar date.
- The Spring Boot test receives the fixed Clock bean supplied via @Primary.

Avoid asserting on an exact stdout/BUILD SUCCESSFUL string because Gradle's log output varies by version and configuration; rely on exit codes and actual test reports.

To run only the time tests instead of the entire suite:

~~~bash
./gradlew test --tests demo.time.TokenServiceTest
./gradlew test --tests demo.time.BusinessDayPolicyTest
./gradlew test --tests demo.time.ClockSpringIntegrationTest
~~~

JUnit Jupiter with @CsvSource runs one invocation per data row; on failure, the Gradle/JUnit report identifies which elapsedSeconds failed. Because all Instants in the tests are fixed or offset, running on CI across different machine timezones will not alter expected outcomes.

## 10. Time Boundaries Essential for Business Tests

### 10.1. Expiring right at the boundary

Specifications must answer: “Does it expire when **now >= expiresAt** or only when **now > expiresAt**?” The two rules differ solely at exact equality. Writing an **exact-boundary** test is mandatory whenever expiration affects access control or financial decisions.

A common off-by-one mistake:

~~~java
// Wrong for spec "expired exactly at expiresAt".
return clock.instant().isAfter(expiresAt);
~~~

This returns false when now == expiresAt. To match the example's rule, use **!clock.instant().isBefore(expiresAt)**. The snippet above illustrates the expression inside a method, not a standalone Java program.

### 10.2. Zero or negative lifetimes

For TTLs:
- Duration.ZERO would expire a token immediately; the example **rejects creating such tokens**.
- Negative Duration would place expiresAt before issuedAt, violating SessionToken's invariant.
- Very large Durations can overflow Instant.plus; production APIs should define a max TTL for untrusted inputs.
- null is an explicit input error and should not silently fall back to a default TTL unless required by the spec.

If a domain permits one-time tokens with TTL = 0, design and tests must reflect that different rule. Do not treat illustrative behavior as universal for all tokens.

### 10.3. Month-end dates, leap years, and DST

For calendar deadlines, test dates like Feb 28, Feb 29 in leap years, Dec 31 → Jan 1, exact cutoff day, and the next day; where regions observe DST, test those specific zones. Use LocalDate.plusDays(1) for calendar progression; convert to Instant through a ZoneId.

**Never convert LocalDate to Instant by blindly appending 00:00Z.** Nov 8 in Vietnam begins at 17:00Z of the previous UTC day due to UTC+7. When locking a local time of day, specify ZoneId explicitly.

### 10.4. Multiple reads of “now” within one transaction

A subtle bug:

~~~java
// Two reads of the real clock may belong to two different instants.
Instant start = clock.instant();
doBusinessWork();
Instant end = clock.instant();
~~~

This snippet illustrates when you genuinely want two distinct timestamps. When both calculations must rely on **one business decision timestamp**, capture a single Instant at the start of the operation and pass it to subsequent calculations:

~~~java
Instant decisionTime = clock.instant();
boolean expired = !decisionTime.isBefore(expiresAt);
Duration remaining = Duration.between(decisionTime, expiresAt);
~~~

These snippets belong inside a method having expiresAt. Sharing one decisionTime prevents expired from evaluating before the cutoff while remaining evaluates after it. When measuring **execution latency** or timeouts resilient to system-clock adjustments, consider monotonic elapsed-time sources (like System.nanoTime or Timer/Metric APIs), as wall-clock Clock is not a precision performance stopwatch.

## 11. Clock.fixed, Clock.offset, and Simulating Passing Time

**Clock.fixed(t0, UTC)** always returns t0. That is ideal for testing a comparison, yet does not simulate time advancing across multiple steps if a service holds the same fixed Clock instance.

**Clock.offset(base, delta)** yields another Clock at **base.instant() + delta**. If base is fixed, the offset Clock is also fixed. If base is systemUTC, the offset Clock continues ticking with the system clock and **does not give deterministic tests**. Do not confuse offset with “fast-forwarding” the original clock.

In TokenServiceTest, creating one TokenService with the issuance Clock and another with the checking Clock is intentional: it tests a token issued at t0 and checked at later timestamps. In a real application, a single long-lived service holds one system Clock, receiving fresh Instants on each call.

When you need to test **a single service instance** experiencing advancing time:
- Pass a **controllable test Clock implementation** (ensuring getZone/withZone/instant obey the contract).
- Or mock Clock with Mockito and configure **clock.instant()** to return sequential values per invocation; be sure of exact call counts.
- Or design business methods to accept **Instant decisionTime** as a parameter where appropriate, testing multiple instants without mutable Clocks.

That is a scoped design choice; avoid inventing a MutableClock merely to test an expiration check that Clock.fixed covers cleanly.

## 12. Separating the “Clock” from “Date/Time Rules”

For rules involving multiple calculations, inject Clock into a dedicated time-policy class:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.Duration;

final class RenewalPolicy {
    private final Clock clock;

    RenewalPolicy(Clock clock) {
        this.clock = clock;
    }

    boolean canRenew(Instant paidUntil) {
        Instant now = clock.instant();
        Instant renewalWindowStarts =
                paidUntil.minus(Duration.ofDays(7));

        return !now.isBefore(renewalWindowStarts)
                && now.isBefore(paidUntil);
    }
}
~~~

This is a standalone Java class requiring no Spring. Rule: renewal is allowed **from exactly 7×24 hours before paidUntil up to right before paidUntil**; right at paidUntil it is no longer within the window. Another business might want “starting at the beginning of the seventh calendar day before expiration”, in which case Duration.ofDays(7) is inappropriate and LocalDate/ZoneId should be used.

Minimal tests for this policy should cover:
- one second before window opens → false;
- exact window opening → true;
- inside window → true;
- immediately before paidUntil → true;
- at paidUntil and after → false.

This is why a testable Clock is only **infrastructure**. Choosing Duration vs LocalDate math, comparison operators, and timezones are **business rules** that must be documented and tested.

## 13. Spring Boot: What Clock Does Not Control Automatically

Declaring a Clock bean is good practice, yet **it does not automatically switch every time source in the system to that Clock**.

| Time source | Does an injected Clock control it directly? | How to handle |
|---|---|---|
| TokenService calling clock.instant() | Yes | Test with Clock.fixed |
| Service calling Instant.now() directly | No | Refactor to use Clock |
| LocalDate.now() in business logic | No | Use LocalDate.now(clock) or clock.instant().atZone(zone) |
| Database using NOW()/CURRENT_TIMESTAMP | No | Control DB time or adjust how timestamps are supplied; separate integration tests |
| Hibernate/DB default created_at generation | Not guaranteed | Check where timestamps originate: JVM, ORM, or DB |
| @Scheduled triggered by scheduler | Clock bean does not advance schedules by default | Separate business method from trigger and test each; integration test scheduling per real mechanism |
| JWT library verifying exp using its own clock | Not by default | Check clock/skew/tolerance hooks supported by the JWT library |
| External API with its own expiry | No | Use stub/contract/integration tests at the boundary; never assume your clock controls theirs |
| Latency analysis, benchmarks, timeouts | Wall-clock Clock is not the only tool | Use appropriate timers/monotonic clocks and metrics |

**@Scheduled example:** If a daily job sends overdue-invoice alerts, test **findOverdueInvoices(clock.instant())** with a fixed time; separately test that the job fires on its configured cron and zone. Injecting Clock into a service does not make the framework trigger future scheduled runs.

**Database example:** If a service issues tokens via clock.instant() while the created_at column uses DEFAULT CURRENT_TIMESTAMP in the database, those two values can differ. Align time sources per specification or allow and test acceptable drift in integration tests; never assert that every DB timestamp equals token issuedAt down to the nanosecond.

**Finance/regulatory example:** If closing dates depend on jurisdiction, store an explicit ZoneId with rules. “UTC+7” and “Asia/Ho_Chi_Minh” share the same offset currently, yet fixed offsets cannot express regional historical/rule changes. Pick the model matching real requirements.

## 14. Anti-Patterns and Fixes

| Anti-pattern | Consequence | Fix |
|---|---|---|
| Instant.now() scattered in branches | Uncontrollable test timestamps | Inject Clock, capture now once per decision |
| Thread.sleep(1000) to test expiration | Slow, flaky, scheduler-dependent | Use Clock.fixed/Clock.offset |
| Mocking static Instant.now() across all tests | Tied to JVM internals, hard to maintain | Inject Clock into objects |
| Testing only far-past expiration times | Misses `>` vs `>=` off-by-one bugs | Test just before/at/after boundary |
| Using Clock.systemDefaultZone() undocumented | Laptop and CI yield different results | Specify explicit business ZoneId |
| Using LocalDateTime for absolute expiration | Missing zone to resolve exact instant | Store Instant, or OffsetDateTime/ZonedDateTime when needed |
| Using Duration.ofDays(1) for calendar days across DST | Can shift local time of day | Use LocalDate/Period/plusDays appropriately |
| Tests asserting only “no exception thrown” | Misses wrong expiresAt or cutoff date | Assert exact values, boundaries, and zone behavior |
| Defining a fixed test Clock in production config | Application “freezes in time” when deployed | Use Clock.systemUTC in production, @TestConfiguration/@Primary in tests |
| Defining two Clock beans with no selection rule | Ambiguous Spring injection | Explicit @Primary/@Qualifier |
| Assuming Clock bean governs DB/JWT/scheduler | Tests miss real time sources | Integration test at each boundary |
| Testing tight boundaries against real wall time | Tests pass intermittently then fail | Fix test Instants |

**Never use a fixed test Clock in production.** Clock.fixed is solely for simulations and tests. Accidentally registering it in default configuration can give every new session the exact same issuedAt and halt advancing “now”.

## 15. Step-by-Step Process for Applying This to a Real Feature

When refactoring code that currently reads system time:
1. **Clarify the specification:** Does it expire at or after the timestamp? Is TTL elapsed seconds or calendar days? Which timezone governs deadlines? Who owns timestamps across DB/external services?
2. **Locate time reads:** Find Instant.now(), LocalDate.now(), System.currentTimeMillis(), and DB/API timestamps. Identify boundaries you actually control.
3. **Inject Clock via constructor:** Store in a final field; declare a Clock.systemUTC() bean in Spring Boot configuration rather than having services instantiate Clock themselves.
4. **Standardize models:** Instant for absolute timestamps; Duration for real-time TTLs; LocalDate + ZoneId for calendar-date deadlines.
5. **Read “now” once per decision:** Avoid multiple time reads that produce self-contradictory states.
6. **Write unit tests with fixed/offset:** Before/at/after expiry; invalid inputs; date rollovers, DST, and leap years where applicable.
7. **Verify Spring wiring when needed:** @TestConfiguration + @Primary or proper bean override; avoid relying indirectly on real system time.
8. **Test external boundaries:** DB timestamps, schedulers, JWT, external APIs, cache TTL; each component has its own clock and measurement semantics.
9. **Run reliably on CI:** Inspect test results, eliminate sleeps and host-timezone-dependent comparisons.
10. **Keep Clock as a clean dependency:** Do not wrap java.time.Clock in redundant custom abstractions if it already fits the need.

Self-check: suppose someone changes **!now.isBefore(expiresAt)** to **now.isAfter(expiresAt)**. Which test case immediately catches that bug? **now == expiresAt**. If your suite lacks that exact case, Clock was injected cleanly yet the business rule remains unproven.

**Java API reference links:** [Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html), [Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html), [Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html), [LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html), and [ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html).