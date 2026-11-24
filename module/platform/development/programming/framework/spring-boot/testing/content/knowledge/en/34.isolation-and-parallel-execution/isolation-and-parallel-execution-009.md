# Clock, Random Seed, and Reproducibility of a Failed Run

## 1. The Problem: A Test Passes Yesterday Yet Fails Today

Under **Isolation and Parallel Execution** in Spring Boot testing, a test can pass on a laptop and fail in CI without any source code change. Two common sources of nondeterminism are:

- **Real wall-clock time:** code calls `Instant.now()`, `LocalDate.now()`, `System.currentTimeMillis()`, or relies on the default timezone. Running near midnight, across DST transitions, or near TTL/deadline boundaries yields different results.
- **Randomness:** code calls `new Random()`, `Math.random()`, `ThreadLocalRandom.current()`, `UUID.randomUUID()`, or random fixture libraries without saving the seed. On failure, nobody can recreate the exact inputs that triggered the bug.

In parallel tests, the problem deepens: a `Random` instance shared across threads may be free of data races in its implementation, yet **the order in which values are consumed** still depends on thread scheduling. Even a single process-level seed cannot replay a case if threads draw numbers in a different order.

This lesson teaches three layers of control:

1. **Injectable clock:** use `java.time.Clock`, `Clock.fixed(...)`, `Clock.offset(...)`, and a test-only mutable clock instead of depending on real CI wall time.
2. **Seedable randomness source:** use `java.util.random.RandomGenerator` (Java 17), `new Random(seed)`, and a dedicated generator per test/case.
3. **Replaying a specific failure:** log **root seed, case index, derived case seed, instant, zone, test selector, versions, and environment**, and provide a Gradle command to re-run that exact case.

The complete example uses **Java 17, Spring Boot 3.3.0, JUnit Jupiter, and Gradle**. It features a Spring application receiving `Clock` and `RandomGenerator` via constructor injection; unit tests verifying dates/times, deadlines, random sequences, and concurrent isolation; a test generating multiple scenarios from a root seed with single-case replay for case N; and a `@SpringBootTest` verifying test bean overrides. **Expected results** are distinguished from execution results: this document does not claim Gradle was executed.

## 2. Learning Objectives

After this lesson, you can:

1. Distinguish real system time, fake clocks, timezone-based calendar dates, monotonic elapsed time, and virtual scheduler time.
2. Use `Clock.systemUTC()` as the default application dependency instead of hard-coding `Instant.now()` in business logic.
3. Use `Clock.fixed(Instant,ZoneId)` to freeze observed time completely.
4. Use `Clock.offset(base, Duration)` to simulate past/future; understand that offsetting a system clock still ticks.
5. Write `MutableClock extends Clock` backed by `AtomicReference<Instant>` to advance time without `Thread.sleep`.
6. Test boundaries before a deadline, at the exact deadline, and after the deadline.
7. Verify that the same `Instant` yields two different `LocalDate`s under two timezones.
8. Understand why `Instant.now(clock)` and `LocalDate.now(clock)` serve different purposes.
9. Distinguish the `RandomGenerator` interface from the `Random` implementation in Java 17.
10. Explain how the same seed + same algorithm + same method call sequence produces the same pseudorandom sequence.
11. Recognize that logging only the seed is insufficient if code changes algorithms, draw counts, or draw order.
12. Never use `Random(seed)` for passwords/tokens/cryptographic keys; use `SecureRandom` and secure policies.
13. Never share one seeded `Random` across parallel tests expecting deterministic per-test results.
14. Design each test/case with its own random state, independent of case execution order.
15. Derive a stable case seed from root seed + case index using a pure stateless calculation.
16. Allow JUnit to replay a single case via Gradle `-PreproSeed` and `-PreproCaseIndex`.
17. Include the replay command and case metadata in assertion failure exceptions.
18. Use JUnit `TestReporter` to publish the seed into test reports rather than `println`s hidden by test runners.
19. Verify Spring Boot `@TestConfiguration`/`@Primary` overrides for `Clock` and `RandomGenerator`.
20. Understand the pitfalls of a singleton random generator inside a shared Spring `ApplicationContext`.
21. Distinguish Java test RNGs from property/fixture generator RNGs in jqwik/QuickTheories/Instancio (which have their own seed mechanisms).
22. Understand that test ordering, JUnit parallelism, Gradle forks, and external DB/HTTP state can still cause replay divergence even with the same seed.
23. Record JDK, timezone/tzdb, locale, dependency versions, CI runner, and input snapshots when investigating flaky failures.
24. Know that `Clock.fixed` does not automatically advance schedulers, retry backoffs, Redis TTLs, or database server clocks.
25. Follow a reproducing/red-green diagnosis workflow instead of "rerun until green".
26. Write tests with invariants and negative cases rather than brittle hard-coded random literals.
27. Distinguish failures caused by production bugs from failures masked by over-mocked tests.
28. Choose appropriate isolation levels across single JVMs, multiple forks, and CI shards.

## 3. Three Sources of Nondeterminism to Distinguish

| Source | Examples | How to Control |
| --- | --- | --- |
| Wall clock | `Instant.now()`, current date, deadlines | Inject `Clock`, fixed/mutable test clocks |
| PRNG state | `Random.nextInt()`, fixture generation | Record seed, algorithm, draw order; per-case generator |
| Scheduling/external state | Parallel threads, databases, network, timezones, brokers | Isolation, deterministic schedulers/clocks when applicable, fixed test resources, explicit event ordering |

**A seed controls only the PRNG**, not which rows sit in a DB or which thread finishes first. **`Clock.fixed` controls only code calling that injected `Clock`**, not `System.currentTimeMillis()` in third-party libraries, Redis server TTLs, or default task schedulers.

A well-designed reproducible test clearly separates **what is controlled** from **what can still vary**.

## 4. Clock: Turning Time into an Injected Dependency

Anti-pattern:

```java
@Service
class ExpiryService {
    boolean expired(Instant deadline) {
        return Instant.now().isAfter(deadline);
    }
}
```

This is an illustrative snippet (imports omitted). Two problems:

1. `Instant.now()` reads the system clock; a test running near the boundary can cross the deadline mid-assertion.
2. `isAfter` returns `false` **when equal to the exact deadline**. If the contract is "expired as soon as `now >= deadline`", the code has a boundary bug.

Testable design:

```java
@Service
public class DeadlineService {
    private final Clock clock;

    public DeadlineService(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant deadline) {
        Objects.requireNonNull(deadline, "deadline");
        return !clock.instant().isBefore(deadline);
    }
}
```

This is an abbreviated snippet; the full runnable class is in Section 13. The logic expresses `now >= deadline` by negating `isBefore`, making the boundary explicit.

### 4.1. Clock.systemUTC()

```java
Clock productionClock = Clock.systemUTC();
```

This provides current time in UTC. When storing timestamps or comparing global instants, `Instant`/UTC avoids timezone ambiguity.

### 4.2. Clock.fixed()

```java
Clock fixed = Clock.fixed(
        Instant.parse("2026-12-31T23:30:00Z"),
        ZoneOffset.UTC);
```

Every call to `fixed.instant()` returns the exact same `Instant`. This works well for most unit tests verifying logic at a fixed point in time. **Never use `Clock.fixed` with a polling loop waiting for time to pass** if the loop exits only when the clock advances.

### 4.3. Clock.offset()

```java
Clock tomorrow = Clock.offset(
        Clock.systemUTC(),
        Duration.ofDays(1));
```

Offset adds a duration to a base clock. If the base is the system clock, the result still ticks in real time shifted by one day—**not strictly deterministic**. For determinism, offset a `Clock.fixed`:

```java
Clock fixedTomorrow = Clock.offset(
        fixed,
        Duration.ofDays(1));
```

### 4.4. Clock.tick()

`Clock.tick(baseClock, Duration.ofSeconds(1))` makes time advance in discrete "ticks", fitting certain UIs/metrics. It does not create a virtual scheduler and has truncation/caching semantics. Never use `Clock.tick` to verify exact nanosecond timer latencies.

## 5. Instant, LocalDate, ZoneId, and Timezone Boundaries

The exact same physical instant can fall on two different calendar dates:

```java
Instant instant =
        Instant.parse("2026-12-31T23:30:00Z");

Clock utc = Clock.fixed(
        instant, ZoneOffset.UTC);

Clock vietnam = Clock.fixed(
        instant, ZoneId.of("Asia/Ho_Chi_Minh"));

LocalDate utcDate = LocalDate.now(utc);
LocalDate vnDate = LocalDate.now(vietnam);
```

The results are strictly deterministic:

```text
utcDate = 2026-12-31
vnDate  = 2027-01-01
```

Because Vietnam is UTC+07 during the example period, `23:30Z` is already `06:30` the next day in Ho Chi Minh City.

### 5.1. Never Query the Clock Twice for a Consistent Snapshot

Code like:

```java
Instant at = clock.instant();
LocalDate date = LocalDate.now(clock);
```

can capture two inconsistent snapshots if `clock` is a ticking system clock and midnight passes between the two calls. For a receipt needing one consistent snapshot, choose:

```java
Instant at = clock.instant();
LocalDate date =
        LocalDate.ofInstant(at, clock.getZone());
```

In the runnable `ReservationService`, `clock.instant()` is read **once**, and `LocalDate` is derived from that exact instant.

### 5.2. LocalDate.now() Without a Clock

`LocalDate.now()` uses the system default timezone—a mutable process-global setting that differs across dev laptops and CI. In business services, always use `LocalDate.now(clock)` or `LocalDate.ofInstant(instant, businessZone)`.

### 5.3. Timezone Database / tzdb

`ZoneId.of("America/New_York")` encapsulates DST rules from the JDK's `tzdb`. Historical and future rules can shift across JDK/`tzdb` releases. For "exact cross-machine replay", record **JDK vendor/version, `tzdb`**, zone, and instant. `Asia/Ho_Chi_Minh` in the sample is simpler because it has no DST in the tested window, yet does not remove the need for version pinning in complex tests.

## 6. MutableClock: Advancing Time Without Real Waiting

When testing `T-1ms`, `T`, and `T+1ms`, `Clock.fixed` gives a single snapshot; you can build three separate fixed clocks. When a service holds a `Clock` reference, you can also use a test-only `MutableClock`:

```text
MutableClock starts at T - 90 seconds
       |
       +-- DeadlineService.isExpired(T) -> false
       |
       +-- clock.advance(90 seconds)
       |
       +-- DeadlineService.isExpired(T) -> true
       |
       +-- clock.advance(1 second)
       |
       +-- DeadlineService.isExpired(T) -> true
```

No `Thread.sleep(90000)` needed; fast and deterministic.

### 6.1. Mutable Clocks Require Care Under Concurrency

A test-only clock can use `AtomicReference<Instant>` to avoid data races on the timestamp. Even so, Thread A advancing while Thread B reads still yields **interleaving-dependent results**. Parallel tests need one clock per case or latch/barrier coordination, never one shared mutable clock across the entire suite.

### 6.2. MutableClock Does Not Replace a Virtual Scheduler

If the system uses `@Scheduled`, Reactor `Schedulers`, Netty event loops, Redis TTLs, or database `CURRENT_TIMESTAMP`, advancing a Java `Clock` will not automatically "wake up" tasks in those systems. Use dedicated virtual-time schedulers, fake executors, appropriate Testcontainers/server clocks, or different test boundaries. Never claim `Clock.fixed` shortens real retry/backoff delays.

## 7. What Is a Seed? When Does the Same Seed Give the Same Result?

`java.util.Random` is a PRNG. Given the same `long seed` and **the exact same sequence of random method calls**, two `Random` instances emit the identical sequence. Java SE 17 specifies `java.util.Random`'s algorithm for cross-platform portability.

```java
Random left = new Random(20261108L);
Random right = new Random(20261108L);

for (int i = 0; i < 5; i++) {
    assertEquals(
            left.nextInt(1_000_000),
            right.nextInt(1_000_000));
}
```

Snippet requires JUnit static import `assertEquals`. This provides **repeatability**, not security. `Random` is a small-state, predictable LCG; never use it for tokens, password reset links, cryptographic nonces, or secret keys.

### 7.1. Conditions Required to Reproduce a Sequence

A failed run using randomness must record:

- PRNG **implementation/algorithm** (`java.util.Random`, `SplittableRandom`, algorithm name).
- **Full seed value**.
- **Order and count** of generator calls (`nextInt(100)` differs from `nextInt(1000)`).
- How seeds are split across cases/threads.
- Input data external to randomness, timezone, and clock.
- Test code/dependency/JDK versions.

Inserting a single `random.nextBoolean()` before `nextInt(...)` causes the same seed to produce different output because the internal state advanced.

### 7.2. RandomGenerator in Java 17

`java.util.random.RandomGenerator` is the unified interface for PRNGs; `java.util.Random` implements it starting in Java 17. Business services can inject `RandomGenerator`, while tests instantiate `new Random(seed)`.

Benefit: easy to swap algorithms in configuration. Caveat: **the same seed with a different implementation** does not guarantee the same sequence. Therefore, replay metadata must log the algorithm or pin a consistent implementation.

### 7.3. SplittableRandom / ThreadLocalRandom

`SplittableRandom` can spawn independent generators via `split()`, fitting parallel designs. Still, if a shared parent is split in a scheduling-dependent order, child seed assignments differ. `ThreadLocalRandom.current()` offers high throughput in production parallel code, yet provides no public API to set an arbitrary seed for replay; avoid it when tests require exact seed control.

### 7.4. SecureRandom Is a Different Story

`SecureRandom` is for security-sensitive randomness. Never replace it with `new Random(42)` in production just to make a unit test deterministic. When testing token/security boundaries, mock/fake the entropy source **strictly inside tests** with explicit ownership, while integration/security tests use real entropy and assert policies/invariants instead of fixed secret bytes.

## 8. Why a Shared Seeded Random Still Fails to Reproduce Parallel Tests

Suppose two threads A and B share `Random shared = new Random(123)` and call `nextInt()`:

```text
Run 1: Thread A draws #1; Thread B draws #2
Run 2: Thread B draws #1; Thread A draws #2
```

Even though the global sequence `#1, #2` is identical, **which case gets which number** depends on the scheduler. `java.util.Random` is thread-safe, yet thread safety does not guarantee deterministic per-task assignment.

What to do instead:

- Each test method creates `new Random(ownSeed)`.
- Each **scenario/case** creates its own PRNG whose seed is computed by a deterministic pure function of root seed + case index/ID.
- Never use a global counter or `AtomicLong.incrementAndGet()` to assign case seeds in thread execution order.
- Never run `Collections.shuffle(list)` with a global RNG while parallel threads mutate the list.
- Never expect changing JUnit execution order to preserve results if cases draw from the same `Random` instance.

### 8.1. Per-Case Derived Seed

A simple, stable derivation for the lab:

```java
static long caseSeed(long rootSeed, int caseIndex) {
    return rootSeed ^
            (0x9E3779B97F4A7C15L *
                    (caseIndex + 1L));
}
```

This pure function holds no mutable state: given the same root + index, the output seed is identical whether the case runs first or last. The constant simply performs mixing/scrambling via Java integer arithmetic; it is **not a cryptographic KDF** and makes no collision-free guarantee over all inputs.

In the full project, each case uses **one `Random` for input generation** and **another `Random` for the service**; each has its own derived seed. Never let input generation draw from the business service's generator, or adding one new input field silently shifts all subsequent service random values.

### 8.2. Root Seed vs Case Index

The root seed represents **a set of scenarios**. The case index identifies **one scenario in that set**. If case 47 fails:

```text
rootSeed = 20261108
caseIndex = 47
caseSeed = derived(rootSeed,47)
```

This is a diagram, not a `caseSeed` computed/emitted in a live run. Replaying only case 47 reconstructs its inputs directly from `rootSeed, index` without re-running cases `0–46` just to "advance the RNG enough first".

## 9. Reproducing a Failure: The Replay Contract

A good failure report answers:

1. **Which test?** `example.repro.SeedReplayTest.replaySingleCaseFromRootSeedAndIndex`.
2. **Root seed?** E.g., `20261108`.
3. **Case index?** E.g., `47`.
4. **Derived seed?** Recomputed from root/index; printed for diagnostics.
5. **Instant/zone?** E.g., base instant + deterministic offset.
6. **Which command?** A single Gradle line with `--tests` and `-P...` flags.
7. **Build environment?** JDK, Gradle, dependencies, OS/timezone, parallel forks.
8. **Input snapshot?** If DTOs/HTTP payloads/DB fixtures are involved, store them safely for restoration.
9. **Expected/actual result?** Assertion with a clear message.
10. **Is the failure 100% reproducible?** If not, identify the remaining source of nondeterminism.

In the lab, replay a single method and exact case:

```bash
./gradlew test --tests example.repro.SeedReplayTest.replaySingleCaseFromRootSeedAndIndex -PreproSeed=20261108 -PreproCases=80 -PreproCaseIndex=47
```

Gradle forwards these flags as JVM system properties to the test process. If a nonexistent `caseIndex` is supplied (`index >= cases`), the test fails fast with a validation message instead of silently running zero cases.

### 9.1. Where Should the Seed Be Recorded?

- JUnit `TestReporter.publishEntry(...)`: test reporting metadata entry.
- Assertion failure message: contains seed/case index/replay command so CI logs show the exact failure context.
- CI build metadata or test artifacts: lets anyone copy the command.
- Structured logs: seed and scenario ID when non-sensitive.

**Never log secret tokens or real customer PII in replay manifests.** Synthetic PRNG seeds are normally non-sensitive; if a seed derives from real secrets, protect the data and never print raw secrets.

### 9.2. Never Use "Test Failed, Rerun Until Green" Instead of Reproduction

A passing rerun may simply mean scheduling, milliseconds, or random inputs shifted. Record the seed, time, and environment to re-run the **exact failing input**; once fixed, add a regression test for that specific case or general invariant rather than deleting the case from the suite.

## 10. Java 17 + Spring Boot 3.3 Project

File structure:

```text
reproducible-tests-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/repro/
    │   ├── ReproLabApplication.java
    │   ├── ReservationReceipt.java
    │   ├── ReservationService.java
    │   └── DeadlineService.java
    └── test/java/example/repro/
        ├── MutableClock.java
        ├── ReservationServiceTest.java
        ├── SeedReplayTest.java
        └── ReproBootTest.java
```

The lab targets time/random/test reproducibility exclusively. No H2, Docker, HTTP server, or remote message broker is required. `ReservationReceipt` is simulated from a `requestId`, timestamp, and nonsecurity pseudorandom suffix.

### 10.1. settings.gradle

```groovy
rootProject.name = 'reproducible-tests-lab'
```

### 10.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()

    systemProperty 'repro.seed',
            providers.gradleProperty('reproSeed')
                    .orElse('20261108')
                    .get()

    systemProperty 'repro.cases',
            providers.gradleProperty('reproCases')
                    .orElse('80')
                    .get()

    systemProperty 'repro.caseIndex',
            providers.gradleProperty('reproCaseIndex')
                    .orElse('-1')
                    .get()

    // One JVM is sufficient to observe Spring-managed wiring.
    maxParallelForks = 1
}
```

**Explanation:**

- `spring-boot-starter` provides Spring core/auto-configuration without starting an HTTP server.
- `spring-boot-starter-test` includes JUnit Jupiter and Spring Test.
- Mockito is not needed to fake `Clock`/`Random`: Java built-ins are cleaner.
- `repro.seed`, `repro.cases`, and `repro.caseIndex` are **test JVM properties**, populated from Gradle `-P...` project properties for replay.
- `-PreproCaseIndex=-1` means run all cases. Supply another index to replay a single case.
- `maxParallelForks=1` limits test worker JVMs; it does not force all JUnit methods sequential if JUnit parallelism is enabled globally, so pure unit tests remain independently designed.

**Never place a fixed seed into production security random configurations.** Test seeds exist solely to reproduce pseudorandom business simulations.

## 11. ReproLabApplication.java — Production Dependencies

**src/main/java/example/repro/ReproLabApplication.java**

```java
package example.repro;

import java.time.Clock;
import java.util.Random;
import java.util.random.RandomGenerator;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ReproLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ReproLabApplication.class, args);
    }

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    public RandomGenerator applicationRandom() {
        return new Random();
    }
}
```

This is a demo service using a nonsecurity PRNG. A production `RandomGenerator` singleton still holds state shared across requests: each request's output depends on concurrent interleaving. If real business logic requires reproducible per-request outcomes, design a per-request generator/factory or deterministic key-based derivation; if only non-cryptographic balanced randomness is needed, concurrency requirements differ.

**Never** configure a Spring `RandomGenerator` bean with a fixed test seed in default production configuration; tests provide their own `@Primary` override below.

## 12. ReservationReceipt.java and ReservationService.java

### 12.1. ReservationReceipt.java

**src/main/java/example/repro/ReservationReceipt.java**

```java
package example.repro;

import java.time.Instant;
import java.time.LocalDate;

public record ReservationReceipt(
        String requestId,
        String confirmationCode,
        Instant createdAt,
        LocalDate businessDate) {}
```

An immutable record is straightforward to compare with `assertEquals`; all fields are produced from a single business call. The random suffix in the lab is purely illustrative, **not a globally unique ID guarantee** and not a security token.

### 12.2. ReservationService.java

**src/main/java/example/repro/ReservationService.java**

```java
package example.repro;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.random.RandomGenerator;

import org.springframework.stereotype.Service;

@Service
public class ReservationService {

    private final Clock clock;
    private final RandomGenerator random;

    public ReservationService(
            Clock clock,
            RandomGenerator random) {
        this.clock = Objects.requireNonNull(clock);
        this.random = Objects.requireNonNull(random);
    }

    public ReservationReceipt reserve(String requestId) {
        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException(
                    "requestId must not be blank");
        }

        // Take exactly one clock snapshot.
        Instant at = clock.instant();

        // Derive local business date from the same instant.
        LocalDate date = LocalDate.ofInstant(
                at, clock.getZone());

        // Nonsecurity pseudorandom suffix, 0..999999.
        int draw = random.nextInt(1_000_000);

        return new ReservationReceipt(
                requestId,
                requestId + "-" + draw,
                at,
                date);
    }
}
```

### 12.3. Key Design Decisions

1. Constructor injection lets tests construct `new ReservationService(testClock, new Random(seed))` without Spring.
2. Validation executes **before** drawing randomness, so invalid inputs never advance generator state.
3. The clock is read once so `createdAt` and `businessDate` stay consistent even across midnight.
4. `clock.getZone()` supplies the business zone; production uses UTC while tests can override to Asia.
5. `nextInt(1_000_000)` produces a value from 0 to 999,999. It is **not** a unique ID generator or secret token.
6. When multiple threads share a singleton instance, the global order of draws varies; unit tests allocate a dedicated instance per case.

### 12.4. Why Not Assert a Literal Random Value from Memory?

In same-seed tests, the expected value is generated by **an independent `Random` with the same seed**. Thus the test never relies on manually copied/guessed numbers. If a business method adds an extra draw or changes bounds, the test detects the sequence mismatch.

However, comparing two instances of the same algorithm does not prove statistical quality or cryptographic security; those require different tests.

## 13. DeadlineService.java — Exact Boundary Behavior

**src/main/java/example/repro/DeadlineService.java**

```java
package example.repro;

import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class DeadlineService {

    private final Clock clock;

    public DeadlineService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public boolean isExpired(Instant deadline) {
        Objects.requireNonNull(
                deadline, "deadline");
        return !clock.instant().isBefore(deadline);
    }
}
```

Contract: when `now < deadline`, not expired; when `now == deadline` or `now > deadline`, expired. That is why the code uses `!isBefore` instead of `isAfter`.

### 13.1. What If the Deadline Depends on a Business Timezone?

An absolute `Instant deadline` has no timezone ambiguity. If the requirement is "expires at 23:59:59 `Asia/Ho_Chi_Minh`", convert the business local date/time using the proper `ZoneId` and DST rules into an `Instant` before comparing. Never let CI's default timezone dictate deadlines.

### 13.2. Wall Time vs Elapsed Time

Deadlines based on wall-clock timestamps can be affected by NTP clock adjustments. When measuring execution duration or relative timeouts, `System.nanoTime()`/monotonic timers or test schedulers are often more suitable. `java.time.Clock` is a **wall-time source**, not a monotonic stopwatch. Tests should distinguish checking an absolute deadline from measuring elapsed timeouts.

## 14. MutableClock.java — Test-Only Advanceable Clock

**src/test/java/example/repro/MutableClock.java**

```java
package example.repro;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class MutableClock extends Clock {

    private final AtomicReference<Instant> current;
    private final ZoneId zone;

    public MutableClock(Instant initial, ZoneId zone) {
        this(
                new AtomicReference<>(
                        Objects.requireNonNull(initial)),
                zone);
    }

    private MutableClock(
            AtomicReference<Instant> current,
            ZoneId zone) {
        this.current = Objects.requireNonNull(current);
        this.zone = Objects.requireNonNull(zone);
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        return new MutableClock(
                current, newZone);
    }

    @Override
    public Instant instant() {
        return current.get();
    }

    public void advance(Duration amount) {
        Objects.requireNonNull(amount);
        if (amount.isNegative()) {
            throw new IllegalArgumentException(
                    "Use a nonnegative duration");
        }
        current.updateAndGet(
                instant -> instant.plus(amount));
    }
}
```

Because `withZone(...)` shares the same `AtomicReference<Instant>`, a clock view with a different timezone still observes the same absolute instant. `advance` updates the timestamp atomically to avoid lost updates under concurrent calls. Still, two test threads observing instants before/after an update remain execution-order dependent; best practice is **not sharing a `MutableClock` across independent tests**.

**This file lives under `src/test`**, not as a replacement for system time in production. To "freeze all external time" such as SQL server time or Redis TTLs, control/mock those sources separately.

## 15. ReservationServiceTest.java — 8 Unit Tests

**src/test/java/example/repro/ReservationServiceTest.java**

```java
package example.repro;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Random;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReservationServiceTest {

    private static final long SEED = 987654L;

    private static final Instant FIXED =
            Instant.parse("2026-12-31T23:30:00Z");

    private static final ZoneId HCM =
            ZoneId.of("Asia/Ho_Chi_Minh");

    private static Clock clock() {
        return Clock.fixed(FIXED, HCM);
    }

    @Test
    void fixedClockMakesTimeDeterministic() {
        ReservationService service =
                new ReservationService(
                        clock(), new Random(SEED));

        ReservationReceipt receipt =
                service.reserve("A");

        assertEquals(FIXED, receipt.createdAt());
        assertEquals(
                LocalDate.of(2027, 1, 1),
                receipt.businessDate());

        int expected = new Random(SEED)
                .nextInt(1_000_000);

        assertEquals(
                "A-" + expected,
                receipt.confirmationCode());
    }

    @Test
    void sameSeedProducesSameFirstReceipt() {
        ReservationService first =
                new ReservationService(
                        clock(), new Random(SEED));

        ReservationService second =
                new ReservationService(
                        clock(), new Random(SEED));

        assertEquals(
                first.reserve("SAME"),
                second.reserve("SAME"));
    }

    @Test
    void sequenceAdvanceIsPredictable() {
        Random expected = new Random(SEED);

        int draw1 = expected.nextInt(1_000_000);
        int draw2 = expected.nextInt(1_000_000);

        ReservationService service =
                new ReservationService(
                        clock(), new Random(SEED));

        ReservationReceipt first =
                service.reserve("X");
        ReservationReceipt second =
                service.reserve("Y");

        assertEquals(
                "X-" + draw1,
                first.confirmationCode());
        assertEquals(
                "Y-" + draw2,
                second.confirmationCode());
    }

    @Test
    void zoneChangesBusinessDateNotInstant() {
        Clock utc = Clock.fixed(
                FIXED, ZoneOffset.UTC);
        Clock hcm = Clock.fixed(
                FIXED, HCM);

        ReservationReceipt a =
                new ReservationService(
                        utc, new Random(SEED))
                        .reserve("ZONE");

        ReservationReceipt b =
                new ReservationService(
                        hcm, new Random(SEED))
                        .reserve("ZONE");

        assertEquals(a.createdAt(), b.createdAt());
        assertEquals(
                a.confirmationCode(),
                b.confirmationCode());

        assertEquals(
                LocalDate.of(2026, 12, 31),
                a.businessDate());

        assertEquals(
                LocalDate.of(2027, 1, 1),
                b.businessDate());
    }

    @Test
    void deadlineBoundaryIsInclusive() {
        Instant deadline =
                FIXED.plusSeconds(30);

        DeadlineService before =
                new DeadlineService(
                        Clock.fixed(
                                deadline.minusNanos(1),
                                ZoneOffset.UTC));

        DeadlineService at =
                new DeadlineService(
                        Clock.fixed(
                                deadline,
                                ZoneOffset.UTC));

        DeadlineService after =
                new DeadlineService(
                        Clock.fixed(
                                deadline.plusNanos(1),
                                ZoneOffset.UTC));

        assertFalse(before.isExpired(deadline));
        assertTrue(at.isExpired(deadline));
        assertTrue(after.isExpired(deadline));
    }

    @Test
    void mutableClockMovesTimeWithoutSleeping() {
        MutableClock mutable = new MutableClock(
                FIXED, ZoneOffset.UTC);

        DeadlineService service =
                new DeadlineService(mutable);

        Instant deadline =
                FIXED.plusSeconds(90);

        assertFalse(service.isExpired(deadline));

        mutable.advance(Duration.ofSeconds(90));
        assertTrue(service.isExpired(deadline));

        mutable.advance(Duration.ofSeconds(1));
        assertTrue(service.isExpired(deadline));
    }

    @Test
    void invalidRequestDoesNotConsumeRandomness() {
        ReservationService service =
                new ReservationService(
                        clock(), new Random(SEED));

        IllegalArgumentException ex =
                assertThrows(
                        IllegalArgumentException.class,
                        () -> service.reserve("  "));

        assertEquals(
                "requestId must not be blank",
                ex.getMessage());

        int firstDraw = new Random(SEED)
                .nextInt(1_000_000);

        assertEquals(
                "VALID-" + firstDraw,
                service.reserve("VALID")
                        .confirmationCode());
    }

    @Test
    void independentGeneratorsDoNotShareStateAcrossThreads()
            throws Exception {
        ExecutorService pool =
                Executors.newFixedThreadPool(2);

        try {
            Callable<ReservationReceipt> job =
                    () -> new ReservationService(
                            clock(),
                            new Random(SEED))
                            .reserve("PARALLEL");

            Future<ReservationReceipt> first =
                    pool.submit(job);
            Future<ReservationReceipt> second =
                    pool.submit(job);

            ReservationReceipt expected =
                    new ReservationService(
                            clock(),
                            new Random(SEED))
                            .reserve("PARALLEL");

            assertEquals(
                    expected,
                    first.get(15, TimeUnit.SECONDS));
            assertEquals(
                    expected,
                    second.get(15, TimeUnit.SECONDS));
        }
        finally {
            pool.shutdownNow();
        }
    }
}
```

### 15.1. Meaning of the Eight Tests

| JUnit method | Evidence |
| --- | --- |
| `fixedClockMakesTimeDeterministic` | Exact `Instant` + business date + first PRNG draw |
| `sameSeedProducesSameFirstReceipt` | Two `Random`s with same seed and call order produce identical results |
| `sequenceAdvanceIsPredictable` | Draws 1/2 follow deterministic sequence |
| `zoneChangesBusinessDateNotInstant` | Same instant/PRNG, different `LocalDate` due to timezone |
| `deadlineBoundaryIsInclusive` | T-1ns false, T true, T+1ns true |
| `mutableClockMovesTimeWithoutSleeping` | Advances clock 90s without real sleep |
| `invalidRequestDoesNotConsumeRandomness` | Invalid input draws nothing; first valid call remains draw #1 |
| `independentGeneratorsDoNotShareStateAcrossThreads` | Each callable gets its own `Clock` and `Random`, independent of thread order |

### 15.2. Why Doesn't the Concurrency Test Share One Random?

Each callable creates `new Random(SEED)`; both create and consume separate state. Even if the second task runs first under the scheduler, it still gets **its own generator's first draw**, yielding identical receipts. This test proves the isolation design, **not** parallel RNG throughput/performance.

### 15.3. Why Does the Deadline Test Use ±1 Nanosecond?

`Instant` supports nanosecond resolution. Boundary logic `isBefore`/`isAfter` should test the three tightest states rather than sleeping 1 second waiting for expiry. If the production DB persists only millisecond precision, boundary tests must also account for data-source rounding/truncation.

### 15.4. Why Not Assert Two Random Draws Must Differ?

Within a bounded range, two successive draws **can legitimately be equal by chance**. `sequenceAdvanceIsPredictable` verifies the exact PRNG sequence per the algorithm without claiming consecutive draws are always distinct. This prevents flaky failures on valid random events.

## 16. SeedReplayTest.java — Root Seed + Case Index

**src/test/java/example/repro/SeedReplayTest.java**

```java
package example.repro;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.Map;
import java.util.Random;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestReporter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SeedReplayTest {

    private static final Instant BASE =
            Instant.parse("2026-12-27T00:00:00Z");

    private static final long INPUT_MIX =
            0xD1B54A32D192ED03L;

    private static long rootSeed() {
        return Long.parseLong(
                System.getProperty(
                        "repro.seed", "20261108"));
    }

    private static int caseCount() {
        return Integer.parseInt(
                System.getProperty(
                        "repro.cases", "80"));
    }

    private static int selectedCase() {
        return Integer.parseInt(
                System.getProperty(
                        "repro.caseIndex", "-1"));
    }

    private static long caseSeed(
            long root, int index) {
        return root ^
                (0x9E3779B97F4A7C15L *
                        (index + 1L));
    }

    private record Scenario(
            String id,
            Instant instant,
            ZoneId zone,
            long seed) {}

    private static Scenario scenario(
            long root, int index) {
        long seed = caseSeed(root, index);

        // Separate PRNG stream for scenario inputs.
        Random input = new Random(seed ^ INPUT_MIX);

        Instant instant = BASE.plusSeconds(
                input.nextInt(7 * 24 * 60 * 60));

        ZoneId zone = input.nextBoolean()
                ? ZoneOffset.UTC
                : ZoneId.of("Asia/Ho_Chi_Minh");

        return new Scenario(
                "CASE-" + index,
                instant,
                zone,
                seed);
    }

    private static ReservationReceipt execute(
            Scenario scenario) {
        Clock clock = Clock.fixed(
                scenario.instant(),
                scenario.zone());

        return new ReservationService(
                clock,
                new Random(scenario.seed()))
                .reserve(scenario.id());
    }

    @Test
    void scenarioOrderDoesNotChangeCaseResults() {
        long root = rootSeed();

        Map<Integer, ReservationReceipt> before =
                new HashMap<>();

        for (int index = 0; index < 10; index++) {
            before.put(
                    index,
                    execute(scenario(root, index)));
        }

        for (int index = 9; index >= 0; index--) {
            assertEquals(
                    before.get(index),
                    execute(scenario(root, index)));
        }
    }

    @Test
    void replaySingleCaseFromRootSeedAndIndex(
            TestReporter reporter) {
        long root = rootSeed();
        int count = caseCount();
        int onlyIndex = selectedCase();

        assertTrue(
                count >= 1 && count <= 100_000,
                "repro.cases must be in [1,100000]");

        assertTrue(
                onlyIndex >= -1 && onlyIndex < count,
                "repro.caseIndex must be -1 or " +
                "a valid index below repro.cases");

        reporter.publishEntry(
                "repro.seed", Long.toString(root));

        reporter.publishEntry(
                "repro.cases", Integer.toString(count));

        reporter.publishEntry(
                "repro.caseIndex",
                Integer.toString(onlyIndex));

        for (int index = 0; index < count; index++) {
            if (onlyIndex >= 0 && onlyIndex != index) {
                continue;
            }

            Scenario s = scenario(root, index);

            try {
                ReservationReceipt receipt =
                        execute(s);

                int expectedDraw =
                        new Random(s.seed())
                                .nextInt(1_000_000);

                assertEquals(
                        s.id() + "-" + expectedDraw,
                        receipt.confirmationCode());

                assertEquals(
                        s.instant(),
                        receipt.createdAt());

                assertEquals(
                        LocalDate.ofInstant(
                                s.instant(), s.zone()),
                        receipt.businessDate());
            }
            catch (AssertionError | RuntimeException ex) {
                String command =
                        "./gradlew test --tests " +
                        "example.repro.SeedReplayTest." +
                        "replaySingleCaseFromRootSeedAndIndex" +
                        " -PreproSeed=" + root +
                        " -PreproCases=" + count +
                        " -PreproCaseIndex=" + index;

                throw new AssertionError(
                        "Reproduce with: " + command +
                        "; derivedCaseSeed=" + s.seed() +
                        "; instant=" + s.instant() +
                        "; zone=" + s.zone(),
                        ex);
            }
        }
    }
}
```

**Two JUnit methods**:

- `scenarioOrderDoesNotChangeCaseResults` runs indexes `0–9` ascending and then descending; each case derives its own seed so the output for each index stays unchanged.
- `replaySingleCaseFromRootSeedAndIndex` runs 80 cases by default, or only the selected case. On failure, the exception wraps the exact Gradle command + derived seed + instant + timezone. It never turns a failure into a pass; the wrapper rethrows `AssertionError`.

### 16.1. Separating Input RNG and Service RNG

`scenario(...)` uses `new Random(caseSeed ^ INPUT_MIX)` to generate a timestamp and zone. `execute(...)` uses a separate `new Random(caseSeed)` for `ReservationService`. If a new input field is added later, altering the input RNG's draw count changes subsequent **inputs**, without silently shifting the service RNG to draw #N+1.

For strict cross-version reproduction, still preserve the seed derivation/input generation algorithm, timezone rules, and code/dependencies.

### 16.2. Why Don't Cases Depend on Previous Indexes?

Each case needs only `root` and `index` to reconstruct its seed. Running `caseIndex=47` never requires running `0–46` beforehand to advance a global PRNG. This speeds up investigation and keeps replay accurate in parallel suites.

### 16.3. Should You Hard-Code a Default Seed?

Keep a **stable default seed** so smoke/regression runs are reproducible. Alongside it, CI can generate fresh root seeds and store them in build metadata. Never replace a fixed regression seed with a fresh timestamp and discard the ability to re-run previously discovered failures.

### 16.4. TestReporter Is Not Console Logging

JUnit Jupiter injects `TestReporter` into methods to publish entries to the test runner. The Gradle console may suppress report entries unless reporting/`testLogging` is configured; that is why the failure message also includes the replay command. Never rely solely on `System.out.println` when CI runners show stdout only for failing tests.

## 17. ReproBootTest.java — Overriding Clock/RandomGenerator in a Spring Context

**src/test/java/example/repro/ReproBootTest.java**

```java
package example.repro;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Random;
import java.util.random.RandomGenerator;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = ReproLabApplication.class,
        webEnvironment =
                SpringBootTest.WebEnvironment.NONE)
@Import(ReproBootTest.FixedTestBeans.class)
class ReproBootTest {

    private static final Instant FIXED =
            Instant.parse("2026-12-31T23:30:00Z");

    private static final ZoneId ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");

    private static final long SEED = 314159L;

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedTestBeans {

        @Bean
        @Primary
        Clock testClock() {
            return Clock.fixed(FIXED, ZONE);
        }

        @Bean
        @Primary
        RandomGenerator testRandom() {
            return new Random(SEED);
        }
    }

    @Autowired
    ReservationService reservationService;

    @Autowired
    DeadlineService deadlineService;

    @Autowired
    Clock clock;

    @Test
    void springUsesPrimaryTestClockAndRandomGenerator() {
        assertNotNull(reservationService);
        assertNotNull(deadlineService);
        assertEquals(FIXED, clock.instant());

        ReservationReceipt receipt =
                reservationService.reserve("BOOT");

        int expectedDraw = new Random(SEED)
                .nextInt(1_000_000);

        assertEquals(
                "BOOT-" + expectedDraw,
                receipt.confirmationCode());

        assertEquals(FIXED, receipt.createdAt());

        assertEquals(
                LocalDate.of(2027, 1, 1),
                receipt.businessDate());

        assertTrue(
                deadlineService.isExpired(FIXED));
    }
}
```

### 17.1. Why @TestConfiguration + @Primary?

The main app defines production beans `Clock.systemUTC()` and `new Random()`. The test imports `FixedTestBeans` defining two beans of the same types marked `@Primary`. Spring injects the primary test beans into `ReservationService`/`DeadlineService`.

This is test-specific wiring without modifying production code to use a hard-coded seed or frozen clock.

### 17.2. @Import Ensures the Test Config Is Loaded

Nested `@TestConfiguration` classes can be detected by Spring Boot under specific patterns; using `@Import(ReproBootTest.FixedTestBeans.class)` makes the scope explicit and readable. Bean configuration affects the Spring TestContext cache key; if different test classes import different test configurations, contexts may not be shared.

### 17.3. Be Careful with a Singleton RandomGenerator

`@Bean RandomGenerator testRandom()` creates a stateful singleton generator in the Spring context. This demo has **only one Boot integration method** using it once. Adding more methods to the class or reusing the context across test classes advances the random state, making tests harder to reproduce.

For complex integration tests, consider injecting `ObjectProvider<RandomGenerator>` backed by a prototype supplier, or designing a `RandomSourceFactory` that creates independent generators per test/case/request seed. Never call `Random.setSeed(...)` on a singleton shared across parallel test threads expecting isolation.

### 17.4. Is @MockBean Needed?

No. `Clock` and `RandomGenerator` are cleanly overridden as beans. `@MockBean` is typically helpful for replacing external collaborators; mocking `Clock` with Mockito and stubbing every `instant()/getZone()` method easily misses behavior and weakens tests. `Clock.fixed` expresses exact time clearly without network calls.

## 18. Running the Lab

Requires JDK 17, a Gradle Wrapper compatible with Spring Boot 3.3 (e.g., Gradle 8.7), and access to Maven Central/local cache. If no wrapper exists yet, generate one first; copying `build.gradle` alone does not generate `gradlew`.

Linux/macOS — run all tests:

```bash
./gradlew test
```

Run a single class:

```bash
./gradlew test --tests example.repro.ReservationServiceTest
./gradlew test --tests example.repro.SeedReplayTest
./gradlew test --tests example.repro.ReproBootTest
```

Run 80 deterministic cases with a custom root seed:

```bash
./gradlew test --tests example.repro.SeedReplayTest.replaySingleCaseFromRootSeedAndIndex -PreproSeed=1357911 -PreproCases=80 -PreproCaseIndex=-1
```

Replay only case 47:

```bash
./gradlew test --tests example.repro.SeedReplayTest.replaySingleCaseFromRootSeedAndIndex -PreproSeed=1357911 -PreproCases=80 -PreproCaseIndex=47
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.repro.SeedReplayTest.replaySingleCaseFromRootSeedAndIndex -PreproSeed=1357911 -PreproCases=80 -PreproCaseIndex=47
```

**Expected outcome:** 11 JUnit methods pass in valid code: 8 unit tests, 2 replay tests, 1 Spring Boot integration test. The replay test loops over 80 cases **inside one JUnit method**; the JUnit method count stays 11 rather than turning 80 iterations into 80 separate test methods.

| Test class | `@Test` methods | Spring context? |
| --- | ---: | --- |
| `ReservationServiceTest` | 8 | No |
| `SeedReplayTest` | 2 | No |
| `ReproBootTest` | 1 | Yes |
| **Total** | **11** | By class |

**This article makes no claim that Gradle was executed.** When running locally, inspect `build/test-results/test` (JUnit XML) and the Gradle console/HTML report for actual pass/fail/skipped counts. Never print fabricated output such as "BUILD SUCCESSFUL" or measured seed outputs without executing.

## 19. Deliberate Bug Scenario to Practice Replaying

An effective learning exercise is introducing a **temporary bug in a sandbox branch**, never committed to production:

1. Run `SeedReplayTest` with `-PreproSeed=1357911` and `-PreproCases=80`, recording the version/branch.
2. Break `ReservationService.reserve(...)`'s business date, e.g., calling `LocalDate.now(Clock.systemUTC())` instead of deriving it from the injected instant/zone.
3. Certain scenarios using `Asia/Ho_Chi_Minh` near midnight can fail; the assertion wrapper includes the replay command.
4. Copy that command with the `-PreproCaseIndex=N` printed in the exception.
5. Re-run that exact case N on the same source branch/JDK/tzdb/seed.
6. Fix the bug using `LocalDate.ofInstant(at,clock.getZone())`.
7. Re-run case N (regression), followed by the entire root-seed suite.
8. Save case N as a regression test or add the seed to the CI seed corpus.

**Note:** the injected bug in step 2 depends on the scenario's timestamp/zone; not every seed is guaranteed to produce a failure. If a chosen seed happens not to fail, create a boundary case using a fixed-Clock unit test like `zoneChangesBusinessDateNotInstant` and verify. Never claim "reproduced the bug" without actually running it.

### 19.1. Reproducing a Failure Does Not Mean Seed Alone Suffices

If a bug stems from a race, DB transaction isolation, I/O, CPU scheduling, or network timing, re-running with the same root+case seed may still pass. In those cases, also capture event ordering, request payloads, DB snapshots, container versions, and test scheduler/parallel settings. A seed is **one part** of the reproduction contract, not the whole thing.

## 20. What Should a Failure Artifact Contain?

Record enough information for teammates and CI:

```yaml
# Illustrative failure report, not measured output.
test: example.repro.SeedReplayTest.replaySingleCaseFromRootSeedAndIndex
rootSeed: 1357911
caseIndex: 47
caseCount: 80
prngAlgorithm: java.util.Random
sourceRevision: "the exact commit used by the failing run"
jdk: "record java -version output"
gradle: "record gradle wrapper version"
timeZone: "UTC or explicit ZoneId used by case"
instant: "record generated Instant"
locale: "record Locale if formatting matters"
execution:
  forks: 1
  junitParallel: false
fixtures: "reference sanitized fixture snapshot"
failure: "expected vs actual assertion output"
replay: "./gradlew test --tests example.repro.SeedReplayTest.replaySingleCaseFromRootSeedAndIndex -PreproSeed=1357911 -PreproCases=80 -PreproCaseIndex=47"
```

This is a **template**, not a measured live environment. In CI, populate `sourceRevision`, JDK, Gradle, OS/arch, container image digests, and exact failures automatically. Never log secrets/tokens/customer PII as raw fixtures.

### 20.1. Is Logging TestReporter Entries Enough?

It helps attach root/case metadata, provided the test runner collects those artifacts. Gradle's default console output often omits report entries; therefore, the failure wrapper puts a **copyable replay command** directly inside the `AssertionError`.

### 20.2. Building a Regression Corpus

Maintain a corpus of seeds/case indexes that previously caught bugs. CI runs default deterministic seeds first, followed by optional nightly fuzz runs with fresh seeds, saving any new failing seeds for replay. Never delete old seeds after fixing bugs, as they become regression inputs.

## 21. Changing Seeds While Preserving Algorithm and Call Order

To broaden coverage, run multiple root seeds. For any fixed root seed:

```text
root seed 20261108
  case 0 -> derive s0 -> fixed clock and Random(s0)
  case 1 -> derive s1 -> fixed clock and Random(s1)
  case 2 -> derive s2 -> fixed clock and Random(s2)
  ...
  case 79 -> derive s79 -> fixed clock and Random(s79)
```

Case execution order can be shuffled without altering **any individual index's** result. This is crucial when enabling JUnit parallelism or splitting suites across CI shards.

### 21.1. When Case IDs Are Strings

When using a case key like `tenant:invoice:123` instead of an integer index, use a stable hash/seed derivation with a defined version and encoding. **Never** use `Objects.hash(...)` with mutable inputs or environment-dependent hashes without verifying stability; avoid per-process random salts.

One option is hashing the UTF-8 bytes of `rootSeed + canonicalCaseId` with SHA-256 to derive a PRNG seed; note that this is test-case seed derivation and **does not turn `java.util.Random` into a cryptographic generator**.

### 21.2. Never Assign Seeds from a Global Counter in Parallel Runs

`AtomicLong.getAndIncrement()` is thread-safe, yet which thread gets seed N still depends on scheduling. For stable assignment, derive from the case's index/key, not task start timing.

### 21.3. Never Share Fixture Objects

`Clock.fixed` is immutable and safe to share, whereas `Random` is mutable. Even with the same `Clock`, never share a mutable `List` or in-memory repository across cases if tests mutate state. Give each case isolated dependencies to prevent leaks.

## 22. Parallel Tests: JVM, Threads, and Process State

There are at least three parallel execution scopes:

1. **JUnit parallel methods** inside one JVM.
2. **Gradle/Maven test forks** across multiple JVM processes.
3. **CI shards/agents** across multiple containers/machines.

A local static `Random` or static `Clock` belongs only to that JVM. Two Gradle forks do not share static state, yet can still write to the **same external database/Redis/topic** if configured with shared endpoints.

### 22.1. JUnit Parallel Methods

If `junit.jupiter.execution.parallel.enabled=true` is turned on, the lab's independent unit tests already give each method a fresh `Random`/`Clock` and can run concurrently. However, Spring Boot tests sharing a singleton `RandomGenerator` in a cached context must be isolated or serialized separately.

JUnit `@Execution(ExecutionMode.SAME_THREAD)` and resource locks can curb concurrency for stateful groups; do not use them to mask broken isolation while turning parallelism on repo-wide.

### 22.2. Gradle maxParallelForks

`maxParallelForks=1` in the lab keeps a single worker JVM. Increasing forks can boost throughput, yet each JVM maintains its own Spring `ApplicationContext` cache; seed/root metadata must be passed identically to all workers. If case indexes are split across shards, give each shard an explicit index list rather than drawing from a sequential shared PRNG.

### 22.3. Process-Global TimeZone, Locale, and System Properties

Calls such as:

```java
TimeZone.setDefault(
        TimeZone.getTimeZone("UTC"));
Locale.setDefault(Locale.US);
System.setProperty("feature.flag", "true");
```

are **JVM-global mutations**; parallel tests can overwrite each other. Prefer passing `Clock`, `ZoneId`, `Locale`, and config properties via dependency injection or parameters. If global mutation is unavoidable, restore them in `finally` with appropriate synchronization/test resource locks—and recognize it remains unsafe if frameworks read them on background threads.

### 22.4. External State

A replay seed does not reset Redis, PostgreSQL, Kafka offsets, S3 objects, the filesystem, or fake HTTP server state. Reproducing failures requires managing fixture initialization/cleanup and container lifecycles independently. Never confuse `@DirtiesContext` with wiping external provider data.

## 23. Spring Boot Test Configuration and Context Cache

In Spring Boot 3.3, `@TestConfiguration` and `@Import` provide clear bean overrides for tests. However, Spring's TestContext cache keys on merged configuration: if Test Class A defines a fixed clock config while Class B defines another or differs in `@MockBean` definitions, Spring builds separate contexts.

### 23.1. Never Let Random State Leak Across Reused Contexts

`RandomGenerator` is stateful. A singleton bean can outlive multiple JUnit methods/classes inside a cached Spring context. If Test A consumes draw #1 and Test B expects draw #1 for the same seed, B receives draw #2.

Options:

- Unit tests: instantiate a fresh service/`Random` per test.
- Spring integration: provide a factory creating a fresh generator per business operation or per test scope, or use a test-only bean with an appropriate lifecycle.
- When a singleton is unavoidable, capture baseline sequence/snapshot state, serialize tests, and reset safely—never calling `Random.setSeed` while parallel request threads are reading it.
- `@DirtiesContext` after a test forces bean/registry recreation at startup cost without cleaning external state. Use intentionally, not by default.

### 23.2. Clock.fixed Is Immutable and Shareable

A `Clock.fixed` has no advancing state and is safe to share, though business dates still depend on its zone. `MutableClock` is mutable and must not be shared across parallel tests unless deliberately testing coordinated time advances.

### 23.3. @MockBean, @MockitoBean, and Version Boundaries

Spring Boot 3.3 `@MockBean` is the traditional test annotation; newer Boot/Spring Framework versions support `@MockitoBean` with updated semantics/versions. This lesson uses `@TestConfiguration`/`@Primary` so it does not depend on annotation migration. When upgrading Boot, still verify cache keys, context initialization, and test bean resolution.

## 24. Test Data Generation Libraries and Property-Based Testing

When using jqwik, QuickTheories, Instancio, or custom random fixtures:

- Find the library's **official seed/reporting/replay mechanism**.
- Record the library/test engine seed instead of assuming Gradle's `repro.seed` controls the library's internal RNG.
- Many frameworks include shrinkers that minimize failing cases. Save both the **shrunk input** and the original root seed for replay.
- Maintain a deterministic regression suite separate from multi-run fuzz suites.
- Never treat "10,000 random cases passed this time" as proof that no races or bugs exist.
- Under JUnit parallelism and schedulers, pinning a root seed does not guarantee fixed execution ordering.

### 24.1. Testing Invariants vs Exact Output

Strong invariants:

- Confirmation code always starts with `requestId`.
- Numeric suffix lies in `0..999_999`.
- `createdAt` always matches the `Instant` returned by `Clock`.
- `businessDate` is derived from that same instant in `ZoneId`.

When business contracts do not require an exact random sequence, testing invariants is sturdier than asserting literal random numbers. However, **when replaying a sequence defect**, asserting the expected PRNG sequence in a dedicated test remains valuable.

### 24.2. Shrinking a Failure

If randomized case 47 produces a large payload, minimize the data to a minimal counterexample and add a fixed-data regression test. The seed stays helpful for reproducing discovery, whereas minimal deterministic cases are easier to review and maintain long-term in CI.

## 25. Common Pitfalls

### 25.1. Calling Clock.systemUTC() Inside a Service Instead of Injecting It

The test injects a fixed `Clock`, yet business logic calls `Instant.now()`/`Clock.systemUTC()` directly. The test cannot control time and fails near midnight. Pass `Clock` via constructor injection and assert exact `createdAt`.

### 25.2. Querying Clock Twice for One Business Snapshot

Reading timestamp once and calling `LocalDate.now(clock)` separately can straddle midnight. Fix: derive both fields from a single `Instant`.

### 25.3. Relying on the Default Timezone

Passes on a UTC laptop, fails on an `Asia/Ho_Chi_Minh` machine. Use an explicit `ZoneId` and `LocalDate.ofInstant`.

### 25.4. Using Thread.sleep to Wait for Deadlines

`Thread.sleep(1000)` may be too short or slow down the suite. Use fixed/mutable `Clock`s and test `T-1`/`T`/`T+1`.

### 25.5. Offsetting the System Clock Thinking It Is Frozen

`Clock.offset(Clock.systemUTC(), Duration.ofDays(1))` still ticks. To freeze time, wrap `Clock.fixed` first, then offset it.

### 25.6. Same Seed, Changed Draw Order

A developer inserts `nextBoolean()` before `nextInt()`; all subsequent numbers shift. Record algorithm/call order and test specific contracts.

### 25.7. Sharing a Seeded Random in Parallel

Java `Random` is thread-safe, yet task assignment depends on scheduling. Use per-case generators with seeds derived from index/key.

### 25.8. Using ThreadLocalRandom While Logging a Root Seed

There is no public `setSeed` path to replay by root seed as with `new Random(seed)`. Never promise exact replay with `ThreadLocalRandom` without controlling the generator.

### 25.9. Seeding with currentTimeMillis

`new Random(System.currentTimeMillis())` produces unreproducible failures unless the seed is logged. Prefer configurable seeds in tests; production seeds must not leak security material.

### 25.10. Using Random(seed) for Real Tokens

Predictable; use `SecureRandom` and proper security design. Test-only seeded PRNGs must never leak into production secrets.

### 25.11. Not Logging Case Index on Failure

A 10,000-scenario test fails mid-loop with only "expected vs actual". Wrap assertions with seed/index/replay command and save input snapshots.

### 25.12. Setting Seed in JVM A While Tests Run in JVM B

Gradle forks/CI shards have separate JVM properties/processes. Verify Gradle task property forwarding and reporting rather than setting a shell env var on a parent process.

### 25.13. Reproducing Random Inputs Without Resetting the DB

Same seed + same time, yet leftover DB rows change assertions. Fixture/transaction cleanup is mandatory whenever a DB is involved.

### 25.14. Changing Dependencies/JDK During Replay

Random algorithms, timezone rules, JSON serializers, or sorting behavior can differ. Pin JDK/runtime versions and record the source revision.

### 25.15. Deleting Failures After a Rerun Passes

A flaky race can vanish when scheduling shifts. Preserve artifacts, find the root cause, and add deterministic regression or barrier-based concurrency tests.

### 25.16. Mutating System Default Zone/Locale in a Parallel Suite

Global process state affects other tests. Inject explicit `ZoneId`/`Locale` or use resource locks.

### 25.17. Fixed Clock While Redis TTL Uses Real Time

The Redis server expires keys by its own wall clock; advancing a Java `Clock` does not expire Redis keys. Use Redis-specific tests or fake cache TTL clock providers as appropriate.

### 25.18. Clock.fixed Causing an Infinite Polling Loop

Code polling until `clock.instant().isAfter(end)` hangs forever under a fixed `Clock`. Design tests to advance time explicitly or inject a scheduler/ticker for elapsed-time operations.

### 25.19. Wrongly Hard-Coding Expected Random Output

Guessing `nextInt` output from a seed without computing the algorithm makes tests fail nonsensically. Use an independent same-seed generator for expected values or verified golden vectors.

### 25.20. Confusing Reproducible Inputs with Reproducible Scheduling

A check-then-act race still depends on thread interleaving. Use barriers/latches, deterministic schedulers, or concurrency model checking instead of merely trying more seeds.

## 26. Quick Troubleshooting

| Symptom | Primary Cause | What to Check |
| --- | --- | --- |
| Fails only near midnight | `LocalDate.now()`/default timezone | Fixed `Clock` + explicit `ZoneId` |
| CI and laptop yield different `businessDate` | System timezone/`tzdb` | Pin `ZoneId`, JDK/`tzdb` |
| Deadline at exact `T` not expired | Used `isAfter` instead of `>=` | Test `T-1ns`/`T`/`T+1ns` |
| Test `Clock` has no effect | Service calls `Instant.now()` directly | Constructor injection |
| Same seed yet different random result | Draw order/algorithm changed | Lock call sequence/implementation |
| Passes alone, fails in suite | Shared PRNG/Clock/DB/context | Fresh dependencies and cleanup |
| Parallel test uses same seed yet different cases | Shared PRNG scheduling | Derive per case index |
| Repro command runs zero cases | Invalid `caseIndex`/count | Validate bounds early |
| Seed missing in console | `TestReporter` entry not rendered | Failure message + CI artifact |
| Replay case differs from original | Reconstructing inputs via sequential global RNG | Pure per-case seed derivation |
| Spring integration test random changes every run | Production bean injected instead of test bean | `@Primary`/`@Import` |
| Second Boot test gets draw #2 | Cached context singleton RNG | Per-test factory/prototype |
| `UUID.randomUUID` doesn't replay by seed | `SecureRandom`/internal entropy | Inject deterministic test-only ID factory |
| Timezone fixed yet scheduler still waits in real time | `Clock` does not drive schedulers | Virtual-time scheduler/fake executor |
| DB `CURRENT_TIMESTAMP` differs from Java `Clock` | Separate database/server clock | Test provider/explicit injected timestamps |
| Tests near DST shift wrong | `ZoneRules`/`tzdb` semantics | Zone-specific tests, version pinning |
| CI re-run passes after failure | Race or changed external data | Save seed, environment, event order |
| Test receives same random draw twice | Valid by probability | Test range/algorithm, don't assert uniqueness |
| Fixed clock hangs polling loop | Clock never advances | `MutableClock`/test ticker |
| Test ignores `-P` flag | Gradle properties not forwarded | Inspect `build.gradle` `systemProperty` mapping |
| Random seed exposed as a secret | Using seeded PRNG for security tokens | `SecureRandom` and secret policies |

## 27. Testing Strategy by Layer

### 27.1. Pure Unit: Most Clock/Seed Tests

Instantiate services via `new` with fixed/mutable `Clock` and `new Random(seed)`. No Spring context needed; fast execution and clean isolation. Focus on boundary logic and invariants.

### 27.2. Spring Integration: Injection and Configuration

Use `@SpringBootTest`, `@TestConfiguration`/`@Primary`, and assert that injected real services use the test's `Clock` and generator. Avoid abusing context restarts to reset random state when a factory/test scope suffices.

### 27.3. Provider Integration: External Time/Random Consumers

When logic depends on DB `CURRENT_TIMESTAMP`, Redis expirations, Kafka scheduling, or network retries, test the provider boundary separately. A Java service's seed does not govern external servers. Testcontainers isolates resources; it does not virtualize external time automatically.

### 27.4. Full E2E and Chaos/Concurrency

Requires metadata, event traces, user inputs, jitter, timeouts, host scheduling, and external failure injection. A shared root seed proves only the data generator is deterministic, not the entire deployment.

## 28. Hands-On Exercises

1. Change `Clock.fixed` from `2026-12-31T23:30Z` to `2027-01-01T00:30Z`. Explain the UTC/HCM business dates.
2. Switch the zone from HCM to `America/New_York` and add a DST boundary test with an explicit `ZoneId`.
3. Modify `DeadlineService` to use `clock.instant().isAfter(deadline)`. Verify the exact-deadline test fails; then fix it.
4. Try `Clock.offset(Clock.fixed(...), Duration.ofDays(1))`. Assert the returned `Instant` advances by one day without sleeping.
5. Use `MutableClock.advance(Duration.ofMillis(1))` and verify millisecond boundaries.
6. Call `reserve("X")` twice with the same `Random`, comparing against expected draw #1/#2 without asserting distinct outputs.
7. Insert a `random.nextBoolean()` in `ReservationService` before `nextInt`; observe the sequence test fail.
8. Remove validation before the random draw, causing `invalidRequestDoesNotConsumeRandomness` to fail.
9. Replace the injected `Clock` with `Instant.now()` directly and watch `fixedClockMakesTimeDeterministic` fail.
10. Change the root seed from `20261108` to `1357911` and re-run all `SeedReplayTest` cases.
11. Pass `-PreproCaseIndex=47` and confirm only that index executes in the loop.
12. Pass `-PreproCaseIndex=1000` when `count=80` and verify the test fails fast rather than silently skipping.
13. Share one PRNG instance between input generation and the service; observe how adding an input draw shifts service outputs.
14. Run case indexes in reverse order and verify per-index outcomes remain identical.
15. Try a shared `Random` across two threads and explain the difference between thread safety and deterministic assignment.
16. Inject the production `RandomGenerator` singleton across multiple Spring tests; observe sequence leakage under context reuse. Propose a factory/prototype design.
17. Enable JUnit parallelism for pure unit tests, run repeatedly, and confirm they never share a `MutableClock`.
18. Increase Gradle `maxParallelForks` and note JVM boundaries/effects on Spring TestContext caching.
19. Use `TestReporter` and CI artifacts to record root/case seeds.
20. Introduce a sandbox timezone/`LocalDate` bug, copy the replay command from the failure, and fix the regression.
21. Introduce a sandbox deadline-equality bug and write a fixed-clock regression test without randomness.
22. With an external database, add fixture resets so the same seed/time sees the same data.
23. With a test data library, find its native seed/shrink flags rather than assuming Gradle `repro.seed` controls it.
24. Measure real performance with a dedicated monotonic timer instead of misusing `Clock.fixed` for elapsed time.
25. Write a failure artifact containing exact JDK/build/CI branch, timezone, seed, case index, inputs, and error text.

## 29. Pre-Merge Checklist

- [ ] Business code injects `Clock` rather than hard-coding `Instant.now()` in time logic.
- [ ] A single operation takes one time snapshot to derive both `Instant` and `LocalDate`.
- [ ] Timezones are explicit; never rely on host defaults unintentionally.
- [ ] Deadlines are tested before, at, and after the boundary.
- [ ] Tests use `Clock.fixed` or `MutableClock` instead of unnecessary sleeps.
- [ ] Wall clocks are distinguished from monotonic elapsed timers/schedulers.
- [ ] `RandomGenerator`/`Random` implementation and seed are recorded for replay.
- [ ] Test seeds are never used as production security entropy.
- [ ] PRNG state is isolated per test/case; mutable RNGs are never shared across parallel methods.
- [ ] Case seeds are derived from root+index/ID rather than assigned by scheduling order.
- [ ] Input RNG streams are separated from business RNG streams.
- [ ] Tests never assert two random draws must always differ.
- [ ] Failures capture root seed, case index, derived seed, zone, and instant.
- [ ] An exact Gradle replay command with test method selector is provided.
- [ ] Gradle forwards `-P` properties into JVM system properties.
- [ ] Bounds validation runs on `caseCount`/`caseIndex` to avoid silently running zero cases.
- [ ] JUnit `TestReporter` or artifacts record the seed, and error messages contain the replay command.
- [ ] Unit tests never share static `Random`/`MutableClock` across methods.
- [ ] Boot integration `@TestConfiguration`/`@Primary` beans are clearly scoped and verified via assertions.
- [ ] Never reset a singleton PRNG between parallel tests with `Random.setSeed`.
- [ ] Spring TestContext cache reuse and RNG singleton state are accounted for.
- [ ] JUnit/Gradle forks, CI shards, and parallel settings are logged during flake investigations.
- [ ] DB/Redis/network fixtures are initialized/cleaned separately without relying on seeds.
- [ ] JDK, `tzdb`, dependency versions, OS/arch, and source revision are recorded.
- [ ] No PII/tokens/secrets are logged in failure manifests.
- [ ] Fixes are verified by exact replay followed by the full suite.
- [ ] "Expected tests pass" is never reported as an executed PASS without running.
- [ ] Property-based frameworks' own seed/shrink contracts are respected.

## 30. Decision Flow

```text
Test not reproducible?
      |
      +-- Depends on "now" / date?
      |      -> Inject Clock; fixed/mutable boundary test.
      |
      +-- Depends on random inputs?
      |      -> Log algorithm + rootSeed + caseIndex.
      |         Derive per-case PRNG independently.
      |
      +-- Running in parallel?
      |      -> No shared mutable RNG/Clock/state.
      |         Check JUnit workers/forks/order.
      |
      +-- Spring integration context?
      |      -> @TestConfiguration/@Primary beans.
      |         Beware cached singleton PRNG state.
      |
      +-- Involves DB/Redis/broker/server timestamps?
      |      -> Isolate provider fixtures/time/schedulers.
      |
      +-- Still doesn't replay with same seed?
      |      -> Inspect races/interleaving, external data,
      |         timezone/JDK/dependencies/CI settings.
      |
      +-- Caught a failing case?
             -> Copy exact Gradle replay command;
                minimize input; add regression test;
                rerun full suite.
```

**Conclusion:** `Clock` tames business time, `RandomGenerator` + explicit seeds tame pseudorandom inputs, and **per-case derived seeds** allow replaying a specific failure independently of test scheduling. Reliable tests never share a global mutable `Random` or `Clock`, never use `Thread.sleep` for deadlines, and never let the host timezone dictate outcomes. To reproduce a **complete** failure, pair seeds with environment, fixture, and runtime metadata; a seed cannot replace controlling databases, thread interleavings, or external provider clocks.

## 31. Official Documentation

- Java SE 17 — `Clock`, `fixed`/`offset`/`tick`/`ZoneId` semantics: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html
- Java SE 17 — `Instant`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html
- Java SE 17 — `LocalDate`, `now(Clock)`, `ofInstant`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html
- Java SE 17 — `java.util.Random`, seeded algorithm portability and security warning: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html
- Java SE 17 — `RandomGenerator` interface: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html
- Java SE 17 — Random generator algorithm groups: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/package-summary.html
- Java SE 17 — `SecureRandom`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html
- Java SE 17 — `ThreadLocalRandom`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html
- Spring Boot 3.3 — Testing Spring Applications, `@TestConfiguration` and `@Import`: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-applications.html
- Spring Boot 3.3 — Test configuration and auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/testing/index.html
- Spring Framework — TestContext Framework context cache: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- JUnit Jupiter — `TestReporter`, parameter resolution, parallel execution: https://docs.junit.org/current/user-guide/
- Gradle — Testing in Java & JVM projects, `test --tests`, JVM properties, forks: https://docs.gradle.org/current/userguide/java_testing.html