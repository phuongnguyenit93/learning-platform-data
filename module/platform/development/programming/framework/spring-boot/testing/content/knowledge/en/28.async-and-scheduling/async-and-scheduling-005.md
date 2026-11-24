# Clock, Schedulers, and Testing Time-Based Tasks

In Spring Boot applications, many behaviors are only correct at **a specific point in time**: orders expire after 15 minutes, tokens become invalid upon hitting expiry, reports run at 09:00 in the business timezone, data-scanning tasks trigger every minute, or jobs must not execute twice even if two schedulers fire simultaneously. Tests for these behaviors often become unstable when they call `Instant.now()` directly, use `Thread.sleep(...)`, depend on the CI machine's clock, or let `@Scheduled` run automatically in every `@SpringBootTest`.

This Knowledge lesson focuses on **Clock, schedulers, and testing time-based tasks**, part of the **Async and Scheduling** group of the **Spring Boot – testing** module. The most important principle is separating **business time** from **when the scheduler wakes up work**. You can swap `java.time.Clock` to test the decision "is it due yet?" instantaneously, yet **you cannot assume swapping a `Clock` bean will make Spring `@Scheduled` jump into the future**. A sustainable testing approach is extracting processing logic into a directly callable service, unit-testing it with a controllable clock, and reserving a small number of integration/smoke tests with finite timeouts for the real scheduler.

Examples use **Java 17+, Spring Boot 3.5.16, Spring Framework 6.2.x, JUnit Jupiter 5, Spring Scheduling, and Awaitility**. The illustrative project contains an *in-memory* task queue to observe semantics; it is **not a distributed scheduler or production persistence system**. With real data, you need a database/queue, transactions, idempotency, and proper multi-replica coordination.

## 1. Learning objectives

- Understand differences among `Instant`, `LocalDateTime`, `ZonedDateTime`, `ZoneId`, `Duration`, and `Clock`.
- Know how to inject `Clock` instead of calling `Instant.now()`/`LocalDateTime.now()` scattered across domain code.
- Use `Clock.fixed(...)`, `Clock.offset(...)`, and a mutable test clock to test before/at/after deadlines.
- Choose the exact comparison boundary `dueAt <= now` and test "at the exact second" and "1 nanosecond before" without waiting.
- Distinguish `fixedRate`, `fixedDelay`, `initialDelay`, and Spring's six-field cron.
- Configure `zone` on cron and recognize risks from DST, OS timezones, and CI clocks.
- Understand that `@EnableScheduling`, `@Scheduled`, `TaskScheduler`, `ThreadPoolTaskScheduler`, and `@Async` solve different problems.
- Design a thin task adapter to test services without triggering real schedules.
- Prevent schedulers from running unexpectedly when Spring TestContext caches contexts or test classes run in the same suite.
- Write deterministic time tests in pure JUnit, test `Clock` wiring with `@SpringBootTest`, and test cron with `CronExpression`.
- Write `@Scheduled` smoke tests with **bounded eventual assertions** instead of `Thread.sleep(...)`.
- Test idempotency/concurrency when two triggers pick up the same due job.
- Recognize risks of schedulers running across multiple pods, crash retries, clock skew, and side effects.
- Distinguish what is **time simulation** from what is **real scheduler execution** in test reports.

## 2. Two kinds of clocks that must not be conflated

At least two "clocks" are at play:

| Role | Example | What does it decide? | What should tests do? |
|---|---|---|---|
| **Business clock** | `Clock` injected into service | Task is due, token expired, validity window | Use `Clock.fixed`/mutable clock, call service directly |
| **Scheduling clock / executor** | `TaskScheduler`, scheduled executor, container runtime | When a thread wakes up to invoke the method | A few smoke tests / controlled scheduler tests |
| **Monotonic elapsed time** | `System.nanoTime()`, timer metrics | How long an operation took | Measure duration, never as business timestamps |
| **External system clock** | DB server, Redis TTL, Kafka timestamp | Time controlled by backend | Test real backend; Java `Clock` does not control it |
| **Distributed node clocks** | NTP/VM/pod time | Time relationship across multiple machines | Clock skew, leases, tolerances, and monotonic guards |

**Key example:** A bean `Clock.fixed(Instant.parse("2030-01-01T00:00:00Z"), UTC)` makes `Instant.now(clock)` return the year 2030. It **does not automatically** make `@Scheduled(fixedRate=1000)` run 1,000 times faster or produce 30 years of scheduled invocations. `TaskScheduler` has its own `getClock()` method; `ThreadPoolTaskScheduler` can be configured with `setClock(...)`, yet a standalone `Clock` bean does not automatically replace the scheduling clock of every executor.

### 2.1. Breaking down a clean flow

```text
Real wall-clock / Spring TaskScheduler
        |
        | @Scheduled every 1 minute
        v
CleanupTick.tick()
        |
        | calls method directly, contains no business logic
        v
DueTaskService.processDue()
        |
        | Instant cutoff = injected Clock.instant()
        v
TaskStore.markDue(cutoff)
        |
        | marks tasks with dueAt <= cutoff, not yet completed
        v
side effect / persistence

Unit tests only need to call DueTaskService.processDue()
with Clock.fixed or MutableClock.
Only smoke tests wait for the scheduler to call CleanupTick.tick().
```

Thanks to this separation, dozens of time-boundary scenarios run in milliseconds without waiting for a real scheduler on every scenario.

## 3. Why does calling `Instant.now()` directly make tests flaky?

A service:

```java
// COUNTER-EXAMPLE: result depends on the machine's real time.
public boolean expired(Instant expiresAt) {
    return !expiresAt.isAfter(Instant.now());
}
```

is hard to test at the exact boundary, especially if the test computes `expiresAt` from one `now()` call and the service calls `now()` again. Even a few microseconds apart, "at deadline" and "before deadline" can get mixed up.

Fix:

```java
public final class ExpiryPolicy {
    private final Clock clock;

    public ExpiryPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean expired(Instant expiresAt) {
        return !expiresAt.isAfter(clock.instant());
    }
}
```

This is a Java snippet requiring `java.time.Clock` and `Instant`, not a standalone demo file. With `Clock.fixed`, both test and service see the exact same instant. To test the future, swap the `Clock` or advance a mutable clock — **never sleep**.

### 3.1. Fixing one `now` per processing run

When processing 1,000 tasks, do not call `clock.instant()` inside every comparison if the rule expects **one consistent cutoff**. The service should capture:

```java
Instant cutoff = clock.instant();
return store.markDue(cutoff);
```

Every task in the batch is evaluated against the same instant. If different items need distinct timestamps, express that contract clearly and test it. This is a business semantics decision, not just a performance optimization.

## 4. Choosing the right time type for the domain

| Type | Represents | Used for |
|---|---|---|
| `Instant` | UTC point on timeline | Deadlines, expiry, `createdAt`, event timestamps |
| `Duration` | Elapsed time span | 15-minute TTL, timeouts, retry delays |
| `LocalDate` | Calendar date without time/timezone | Report dates, accounting periods |
| `LocalDateTime` | Local wall time **without zone/offset** | Meeting time input before attaching a business zone |
| `ZonedDateTime` | Calendar time with timezone rules | "09:00 daily in Hanoi", DST |
| `OffsetDateTime` | Timestamp with UTC offset | API/event serialization carrying offset |
| `ZoneId` | Time zone with DST history | Local-time scheduling |
| `Clock` | Provider of `Instant`/`ZoneId` | Injected dependency for domain time |

**Store `Instant` in the data store** when representing an absolute deadline; convert to `ZonedDateTime` only for calendar calculations or display. Do not store `LocalDateTime` and assume "UTC or Asia/Ho_Chi_Minh depending on the host machine" — that easily breaks when switching CI/cloud regions.

**Two different problems:**

- "15 minutes from creation": `createdAt.plus(Duration.ofMinutes(15))`.
- "Every day at 09:00 Hanoi time": compute using `ZoneId.of("Asia/Ho_Chi_Minh")` or a zoned cron, not equivalent to adding 24 hours if a business zone observes DST in the future or elsewhere.

## 5. Three practical Clock types for testing

### 5.1. `Clock.systemUTC()`

Used in production when absolute timestamps are needed in the app:

```java
@Bean
Clock applicationClock() {
    return Clock.systemUTC();
}
```

This does not eliminate clock skew across multiple nodes; it simply provides a replaceable time source in Java code.

### 5.2. `Clock.fixed(...)`

```java
Clock fixed = Clock.fixed(
        Instant.parse("2026-11-08T00:00:00Z"),
        ZoneOffset.UTC);

assertEquals(
        Instant.parse("2026-11-08T00:00:00Z"),
        fixed.instant());
```

This is a snippet with imports `Clock`, `Instant`, `ZoneOffset`, and `assertEquals`. Reading `fixed.instant()` any number of times returns the same value. Useful for expiry, boundaries, timezone serialization, and business calculations.

### 5.3. `Clock.offset(...)`

```java
Clock future = Clock.offset(
        fixed, Duration.ofHours(2));
```

Creates an offset view relative to the base clock. If the base clock is fixed, `future` does not tick either. If the base clock is the system clock, `future` keeps advancing with the system clock at the given offset.

### 5.4. Mutable test Clock

In tests simulating "before → at → after" checkpoints, a small `MutableClock` backed by `AtomicReference<Instant>` lets you advance time without waiting. The project's test helper in Section 21 ensures `withZone(...)` shares the same instant state instead of accidentally creating a separate timeline.

**Do not put `MutableClock` in production** just for test convenience. Business code should depend on the standard `Clock` interface, while tests manage the substitute clock implementation.

## 6. Due boundary: `isAfter`, `isBefore`, and `equals`

If a task must be processed when **`now >= dueAt`**, use:

```java
boolean due = !dueAt.isAfter(now);
```

Truth table:

| `now` | `dueAt` | `now >= dueAt`? |
|---|---|---:|
| 09:59:59.999999999 | 10:00:00 | No |
| 10:00:00.000000000 | 10:00:00 | Yes |
| 10:00:00.000000001 | 10:00:00 | Yes |

**Do not test by sleeping until nearly 10:00 in real life.** Set the `Clock` to 09:59:59.999999999 and advance by one nanosecond. Testing "exact boundary" cases catches off-by-one bugs that tests using timestamps minutes apart would miss.

If the business contract uses `now > dueAt` (overdue *strictly after* the timestamp), update logic and tests accordingly. **Never silently change the comparison operator just to make a test pass.**

## 7. Why is `Thread.sleep` almost always a weak testing approach?

```java
// COUNTER-EXAMPLE: waiting 1 second hoping @Scheduled ran.
Thread.sleep(1000);
assertTrue(taskCompleted);
```

This gives no proof the scheduler actually ran. CI may be busy, a GC pause may stall execution, Docker may be slow, the thread pool may have a backlog, or the method may have thrown an exception. Conversely, sleeping 1 second per test slows down the whole suite.

**Choose by test type:**

- Business deadlines: **`Clock.fixed`/`MutableClock`**, no sleep.
- Async completion: **Awaitility** with condition + finite timeout.
- Single trigger: **`CountDownLatch`** and `await(timeout)`.
- Reactive virtual time: `StepVerifier.withVirtualTime` for publishers using compatible Reactor schedulers, **not** for controlling Spring `@Scheduled` directly.
- Long-running scheduling semantics: a few end-to-end tests or dedicated controlled scheduler tests.

The purpose of a finite timeout is providing **failure diagnostics** when a job never runs, not removing all time elements from smoke tests.

## 8. Spring Scheduling: what does enabling `@EnableScheduling` mean?

Spring processes `@Scheduled` when scheduling annotation processing is active, typically via `@EnableScheduling`:

```java
@SpringBootApplication
@EnableScheduling
public class SchedulerLessonApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                SchedulerLessonApplication.class, args);
    }
}
```

This is a real file in the example from Section 17. When `@EnableScheduling` is present, Spring scans beans with `@Scheduled` and registers their corresponding tasks. **Merely having `@Scheduled` on the classpath does not make tasks run automatically if scheduling is not enabled in the context.**

### 8.1. Why do tests get polluted?

A `@SpringBootTest` loading the full context can start scheduling infrastructure. If a scheduled bean is active during tests, it can:

- Delete rows that another test has not asserted yet.
- Send real emails/messages if using the wrong profile.
- Mutate caches or print logs while tests run.
- Cause hard-to-reproduce races due to timing differences between local and CI.
- Persist inside a cached `ApplicationContext` and keep ticking across test methods/classes.

**Demo solution:** Isolate the scheduled adapter into a bean created only when `demo.cleanup.enabled=true`; default **false**. Business tests that do not need the scheduler keep it false. Only a dedicated smoke test turns it to true with a short interval.

In real systems, scheduler enablement must follow clear environment policies; "defaulting jobs off in tests" does not mean forgetting to test scheduler wiring.

## 9. `fixedDelay`, `fixedRate`, and `initialDelay`

| Setting | Definition | Best for | Pitfall |
|---|---|---|---|
| `fixedDelay` | Delay measured from **when previous run finishes** to next start | Polling/cleanup, less overlap within the same task | Long runs slow down cadence |
| `fixedRate` | Periodic cadence measured from **planned start times** | Sampling/heartbeats needing steady cadence | Under overload can drift/backlog; no real-time guarantee |
| `initialDelay` | Wait before the first run of `fixedDelay`/`fixedRate` | Giving the app warm-up time | Not a "delay on every run" |
| `cron` | Computes next run by calendar schedule | 09:00 reports, nightly runs | Zone/DST/calendar semantics |
| `TaskScheduler.schedule(task, Instant)` | Run a task once near the given instant | One-shot tasks in a single JVM | Restart/crash loses the task |

Example:

```java
@Scheduled(fixedDelay = 5, timeUnit = TimeUnit.SECONDS)
public void pollAfterCompletion() { /* ... */ }

@Scheduled(fixedRate = 10, timeUnit = TimeUnit.SECONDS)
public void sampleEveryTenSeconds() { /* ... */ }
```

Snippets require `Scheduled` and `TimeUnit`, not standalone runnable files.

**Do not interpret `fixedRate` as "guaranteed exactly one execution every 10 seconds".** OS scheduling, CPU, GC, execution time, queues, and thread pools can delay jobs. If the method also has `@Async`, some variants can overlap, requiring business idempotency/locking.

## 10. `@Scheduled` in Spring 6.2: period, properties, and scheduler qualifier

The demo uses:

```java
@Scheduled(
    fixedDelayString = "${demo.cleanup.fixed-delay-ms:60000}",
    initialDelayString = "${demo.cleanup.initial-delay-ms:1000}",
    timeUnit = TimeUnit.MILLISECONDS)
public void tick() {
    service.processDue();
}
```

Using placeholders, tests can set `100` milliseconds while production keeps 60,000 milliseconds if scheduling is enabled. In Spring 6.2, `@Scheduled.timeUnit` applies to fixed delay/rate/initial delay and supports values parsed in duration formats; **cron does not use `timeUnit`**.

Spring `@Scheduled.scheduler` can specify the qualifier or bean name of a `TaskScheduler`/`ScheduledExecutorService` when an app has multiple schedulers. Do not create two beans and assume Spring picks the right one by component-scan order.

Note that Spring `@Scheduled` methods normally accept no arguments; normal return values are not results that JUnit asserts directly. Putting logic into a value-returning service method is much easier to test.

## 11. Six-field cron and timezones

Spring cron expression format:

```text
second minute hour day-of-month month day-of-week
0      0      9    *            *     MON-FRI
```

Example:

```java
@Scheduled(
    cron = "0 0 9 * * MON-FRI",
    zone = "Asia/Ho_Chi_Minh")
public void weekdayReport() { /* ... */ }
```

Meaning: runs at 09:00 Monday–Friday Vietnam time, while the app/scheduler is running and not delayed by load or other conditions. **Cron is not an exactly-once guarantee**: if the app is down at 09:00, Spring `@Scheduled` normally does not automatically "catch up" missed runs like a durable job scheduler.

### 11.1. Disabling cron via placeholder

```java
@Scheduled(
    cron = "${demo.report.cron:-}",
    zone = "Asia/Ho_Chi_Minh")
public void report() { /* ... */ }
```

The `-` value is `Scheduled.CRON_DISABLED` for cron expressions; this pattern is great for toggling schedules via config. Do not assume this applies to `fixedRateString`/`fixedDelayString` (they parse differently).

### 11.2. CronExpression for calendar unit tests

```java
CronExpression expression =
        CronExpression.parse("0 0 9 * * MON-FRI");

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime saturday =
        ZonedDateTime.of(
                2026, 11, 7, 12, 0, 0, 0, zone);

ZonedDateTime next = expression.next(saturday);
// 2026-11-09 09:00 in Asia/Ho_Chi_Minh (Monday).
```

This is a snippet; `CronCalendarTest` contains the runnable assertion. Calendar tests at the `CronExpression` level **do not start a scheduler**, because we are testing **schedule calculation**, not executor threads.

## 12. DST: local times that sometimes do not exist or happen twice

Not every timezone has 24-hour days:

- On spring-forward DST, an hour can be **skipped** (nonexistent local time).
- On fall-back DST, an hour can **occur twice** (ambiguous local time).
- A cron job running at 02:30 in a DST-observing zone must be tested on transition dates.
- Jobs running on month-end, February 29, or holidays also need clear calendar contracts.

Example 2026 in `America/New_York`: on March 8, local time jumps from 01:59 to 03:00. `ZonedDateTime` + `ZoneId` reflect these timezone rules.

**Do not expect "run exactly once at 02:30" when 02:30 does not exist that day.** Define the policy: skip, next valid instant, or compensate; test scheduling/cron/operational scheduler logic against that policy. Do not treat `Clock.systemDefaultZone()` on a UTC CI host as the business timezone.

### 12.1. Avoid comparing local times for absolute expiry

If a token is issued at `Instant` T and expires in 15 minutes, compute `T.plus(Duration.ofMinutes(15))`. Do not convert to local time, add 15 minutes, and assume DST has no effect. For billing calendars like "Nth day of month", use dedicated `LocalDate`/`ZonedDateTime` logic.

## 13. Java `Clock` is not a timer or executor

`Clock.fixed` **does not** run `Runnable`s, spawn threads, or trigger deadlines. It simply returns an `Instant` as specified.

Conversely, `TaskScheduler` has APIs like:

```java
// Snippet: TaskScheduler scheduler and Runnable action.
ScheduledFuture<?> future = scheduler.schedule(
        action, Instant.now().plusSeconds(10));
```

The scheduler has its own clock and underlying executor. A service `Clock` fixed at 2030 does not mean `scheduler.schedule(..., timeFromFixedClock)` waits in simulated time; scheduling uses real clock/OS scheduling. Spring's `TaskScheduler.getClock()` exposes the scheduler's clock; `ThreadPoolTaskScheduler.setClock(...)` can set a clock for scheduling calculations, yet **changing the clock without changing executor/trigger semantics does not automatically provide a reliable virtual-time scheduler**.

**Testing approach:** Unit-test calculation of the desired instant; when proving firing/wakeup, use a dedicated scheduler test with a controlled clock/executor or a bounded smoke test on the real runtime. Do not make 100 unit tests wait on timers.

## 14. Designing the test pyramid for time

| Test level | What it runs with | Reliable signal |
|---|---|---|
| Pure Java unit | `Clock.fixed`/MutableClock | Deadline boundaries, idempotency, business rules |
| Calendar unit | `CronExpression`/`ZonedDateTime` | Next trigger, zone, DST |
| Spring context wiring | `@SpringBootTest` + `@Primary Clock` | Clock bean injected; scheduler disabled |
| Scheduled smoke | `@SpringBootTest` with `@Scheduled` on + Awaitility | Real tick eventually processes overdue record |
| Full persistence integration | Testcontainers + DB transactions | Atomic claim/lease and rows across instances |
| Multi-instance/distributed | Two app replicas/worker processes | Duplicate prevention/failover/retry |
| Production-like observation | Metrics/logs/traces/timezone config | Drift, SLA, missed runs, operational safety |

**Most "is the task due?" scenarios belong in pure Java unit tests.** Only a handful of smoke tests belong to "is the schedule actually registered, does the scheduler call the adapter?". Bugs in distributed locking or databases cannot be proven with a single-JVM in-memory map.

## 15. Runnable project: demo goals

We build an application with `TimedTask` items:

- `id`: unique identifier in the store.
- `dueAt`: an absolute `Instant`.
- `completed`: whether it has been processed.
- `TaskStore`: stored in `ConcurrentHashMap`, transitioning `completed=false → true` atomically per key.
- `DueTaskService`: captures **one snapshot** `clock.instant()` and evaluates due tasks.
- `CleanupTick`: thin adapter with `@Scheduled`; exists only when `demo.cleanup.enabled=true`.
- Production `Clock`: `systemUTC`, overridden in tests by a fixed `Clock`.
- `ScheduledTickSmokeTest`: uses Awaitility and a 5-second timeout to verify the real scheduler runs.

Directory tree:

```text
clock-scheduler-testing/
  settings.gradle
  build.gradle
  src/main/java/com/example/timetest/
    SchedulerLessonApplication.java
    TimeConfiguration.java
    TimedTask.java
    TaskStore.java
    DueTaskService.java
    CleanupTick.java
  src/test/java/com/example/timetest/
    MutableClock.java
    DueTaskServiceTest.java
    CronCalendarTest.java
    DueTaskSpringIntegrationTest.java
    ScheduledTickSmokeTest.java
```

**No production persistence**. When the JVM stops, tasks in `ConcurrentHashMap` vanish. This demo intentionally focuses on testing time/callback boundaries; critical job systems need a DB/job queue for recovery and multi-replica coordination.

## 16. Gradle settings and dependencies

**`settings.gradle`**

```groovy
rootProject.name = 'clock-scheduler-testing'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
    testImplementation 'org.awaitility:awaitility'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter` brings the core Spring context/scheduling foundation; no HTTP stack or DB is needed. `spring-boot-starter-test` brings JUnit, AssertJ/Mockito, and Spring Test; explicit `awaitility` keeps the smoke test from relying accidentally on a transitive dependency. The Spring Boot BOM manages dependency versions in the example. For Maven projects, use equivalent `spring-boot-starter`, `spring-boot-starter-test`, and `awaitility` under `test` scope with a compatible JUnit Platform.

**Java 17+** is the minimum; Java 21 virtual threads are not needed. If production uses a different Boot/Spring version, verify corresponding annotations/packages and behavior before copying.

## 17. Application bootstrap and Clock bean

**`src/main/java/com/example/timetest/SchedulerLessonApplication.java`**

```java
package com.example.timetest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class SchedulerLessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                SchedulerLessonApplication.class, args);
    }
}
```

**`src/main/java/com/example/timetest/TimeConfiguration.java`**

```java
package com.example.timetest;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

`Clock.systemUTC()` keeps business code independent of the host's default timezone. When a test wants to control time, define a `@Primary Clock` bean in test config; do not use `ReflectionTestUtils` to mutate fields or mock static `Instant.now()`.

`@EnableScheduling` still activates scheduling infrastructure in the context; whether the `CleanupTick` job bean **exists or not** is decided by `demo.cleanup.enabled`, as shown in Section 20.

## 18. Domain record and in-memory store

**`src/main/java/com/example/timetest/TimedTask.java`**

```java
package com.example.timetest;

import java.time.Instant;
import java.util.Objects;

public record TimedTask(
        String id, Instant dueAt, boolean completed) {

    public TimedTask {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(dueAt, "dueAt");
    }
}
```

**`src/main/java/com/example/timetest/TaskStore.java`**

```java
package com.example.timetest;

import java.time.Instant;
import java.util.Optional;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class TaskStore {

    private final ConcurrentHashMap<String, TimedTask> tasks =
            new ConcurrentHashMap<>();

    public void put(TimedTask task) {
        Objects.requireNonNull(task, "task");
        tasks.put(task.id(), task);
    }

    public Optional<TimedTask> find(String id) {
        return Optional.ofNullable(tasks.get(id));
    }

    public int markDue(Instant cutoff) {
        Objects.requireNonNull(cutoff, "cutoff");
        AtomicInteger transitions = new AtomicInteger();

        for (String id : tasks.keySet()) {
            tasks.computeIfPresent(id, (key, current) -> {
                if (current.completed()
                        || current.dueAt().isAfter(cutoff)) {
                    return current;
                }

                transitions.incrementAndGet();
                return new TimedTask(
                        current.id(), current.dueAt(), true);
            });
        }
        return transitions.get();
    }

    public void clear() {
        tasks.clear();
    }
}
```

**Why use `computeIfPresent`?** In `ConcurrentHashMap`, per-key remapping is performed atomically with respect to corresponding updates. Two callers checking the same task cannot both transition `false → true`: the second caller sees the task already completed and skips marking it again. The concurrency test verifies this case within **a single JVM**.

**Important limitations:** Iterating `tasks.keySet()` is weakly consistent under concurrent inserts/deletes; a newly added task may only be seen on the next tick. The `transitions` counter reflects transitions in that scan, not a durable event count. `TaskStore.put` can overwrite an old ID; production must use DB unique constraints and proper claim protocols. `clear()` is solely for test isolation in the demo, **not** an operation for clearing a production database.

### 18.1. The problem with side effects

In the demo, flipping a `completed` boolean is the side effect. In reality, you might need to send emails, transfer funds, or publish messages; `markDue` and external side effects may span two separate resource managers. **Marking completed before sending** risks losing work if sending fails; **sending then marking** risks duplicate sends on crash. You need idempotency keys, outbox/retry policies, and independent tests. An in-memory atomic map does not prove end-to-end exactly-once execution.

## 19. Service: business clock is the source of truth for deadlines

**`src/main/java/com/example/timetest/DueTaskService.java`**

```java
package com.example.timetest;

import java.time.Clock;
import java.time.Instant;
import org.springframework.stereotype.Service;

@Service
public class DueTaskService {

    private final Clock clock;
    private final TaskStore store;

    public DueTaskService(Clock clock, TaskStore store) {
        this.clock = clock;
        this.store = store;
    }

    public int processDue() {
        Instant cutoff = clock.instant();
        return store.markDue(cutoff);
    }
}
```

The business method has no `@Scheduled`. Tests can call it directly. Every `processDue()` invocation captures a single `cutoff`, so if processing 10,000 tasks spans past a new deadline, all are evaluated against the same snapshot. This guarantees a clear "batch time".

**Why return `int`?** To test the number of **state transitions** an invocation actually performed. The scheduler adapter can log/emit metrics separately, while tests do not have to verify a void method was called and infer the data is right. Core tests assert both the `int` count and `TimedTask.completed`.

## 20. Scheduled adapter: separating schedule from business logic

**`src/main/java/com/example/timetest/CleanupTick.java`**

```java
package com.example.timetest;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        prefix = "demo.cleanup",
        name = "enabled",
        havingValue = "true")
public class CleanupTick {

    private final DueTaskService service;
    private final AtomicInteger executions = new AtomicInteger();

    public CleanupTick(DueTaskService service) {
        this.service = service;
    }

    @Scheduled(
            fixedDelayString =
                    "${demo.cleanup.fixed-delay-ms:60000}",
            initialDelayString =
                    "${demo.cleanup.initial-delay-ms:1000}",
            timeUnit = TimeUnit.MILLISECONDS)
    public void tick() {
        service.processDue();
        executions.incrementAndGet();
    }

    public int executions() {
        return executions.get();
    }
}
```

In the demo, if `demo.cleanup.enabled` is unset, `CleanupTick` **is not created** (since `matchIfMissing` defaults to false), so no periodic job runs. The smoke test sets it to true to test Spring scheduling wiring. In production, choose an appropriate cadence and configure error observability.

**Do not put `@Scheduled` on `DueTaskService.processDue()`**: doing so forces business tests to load scheduling infrastructure, hinders isolation, and risks concurrent executions. A thin adapter lets you test wiring separately.

### 20.1. What if the task throws an exception?

In many scheduler setups, exceptions in periodic tasks are logged by the error handler and subsequent runs remain scheduled. **Do not assume an exception will fail the JUnit test**, because it happens on a separate scheduler thread. Smoke tests must observe real state/events, and production needs logging/metrics/alerts and retry/dead-letter handling where appropriate.

### 20.2. Stopping scheduling in regular tests

You can set:

```properties
demo.cleanup.enabled=false
```

in test-specific configuration. Do not rely solely on `@DirtiesContext` after a job already ran and produced side effects. If multiple scheduled beans exist, audit all of them and apply a consistent enablement policy; tests should enable only the specific job under smoke test.

## 21. MutableClock helper for unit tests

**`src/test/java/com/example/timetest/MutableClock.java`**

```java
package com.example.timetest;

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
        this(new AtomicReference<>(
                Objects.requireNonNull(initial, "initial")), zone);
    }

    private MutableClock(
            AtomicReference<Instant> current, ZoneId zone) {
        this.current = current;
        this.zone = Objects.requireNonNull(zone, "zone");
    }

    public void advance(Duration amount) {
        Objects.requireNonNull(amount, "amount");
        if (amount.isNegative()) {
            throw new IllegalArgumentException(
                    "Clock advance cannot be negative");
        }
        current.updateAndGet(now -> now.plus(amount));
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        return new MutableClock(current, newZone);
    }

    @Override
    public Instant instant() {
        return current.get();
    }
}
```

`MutableClock` uses `AtomicReference<Instant>` so time updates are safely visible across threads in tests. `withZone` creates a `Clock` view sharing the same instant state with a different zone, honoring the `Clock` contract. It **creates no timers/executors** and does not trigger scheduled beans automatically; you still invoke `service.processDue()` or let the scheduler wake up.

If a test does not need to advance time, prefer `Clock.fixed` over a custom helper. `MutableClock` is valuable when a single scenario checks multiple consecutive timestamps.

## 22. Pure JUnit: testing before/at/after deadline and idempotency

**`src/test/java/com/example/timetest/DueTaskServiceTest.java`**

```java
package com.example.timetest;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DueTaskServiceTest {

    private static final Instant NOW =
            Instant.parse("2026-11-08T10:00:00Z");

    private MutableClock clock;
    private TaskStore store;
    private DueTaskService service;

    @BeforeEach
    void setUp() {
        clock = new MutableClock(NOW, ZoneOffset.UTC);
        store = new TaskStore();
        service = new DueTaskService(clock, store);
    }

    @Test
    void beforeDeadlineDoesNotCompleteTask() {
        store.put(new TimedTask(
                "a", NOW.plusNanos(1), false));

        assertEquals(0, service.processDue());
        assertFalse(store.find("a").orElseThrow().completed());
    }

    @Test
    void exactlyAtDeadlineCompletesTask() {
        store.put(new TimedTask("a", NOW, false));

        assertEquals(1, service.processDue());
        assertTrue(store.find("a").orElseThrow().completed());
    }

    @Test
    void advancingOneNanosecondCrossesBoundary() {
        store.put(new TimedTask(
                "a", NOW.plusNanos(1), false));

        assertEquals(0, service.processDue());

        clock.advance(Duration.ofNanos(1));

        assertEquals(1, service.processDue());
        assertTrue(store.find("a").orElseThrow().completed());
    }

    @Test
    void repeatedTickDoesNotProcessCompletedTaskTwice() {
        store.put(new TimedTask(
                "due", NOW.minusSeconds(10), false));

        assertEquals(1, service.processDue());
        assertEquals(0, service.processDue());
        assertTrue(store.find("due").orElseThrow().completed());
    }

    @Test
    void onlyTasksDueByOneSnapshotAreChanged() {
        store.put(new TimedTask(
                "past", NOW.minusSeconds(1), false));
        store.put(new TimedTask(
                "exact", NOW, false));
        store.put(new TimedTask(
                "future", NOW.plusSeconds(1), false));

        assertEquals(2, service.processDue());
        assertTrue(store.find("past").orElseThrow().completed());
        assertTrue(store.find("exact").orElseThrow().completed());
        assertFalse(store.find("future").orElseThrow().completed());
    }

    @Test
    void twoConcurrentInvocationsClaimOnlyOnce()
            throws Exception {

        store.put(new TimedTask("shared", NOW, false));

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> first =
                    pool.submit(service::processDue);
            Future<Integer> second =
                    pool.submit(service::processDue);

            assertEquals(
                    1, first.get() + second.get());
            assertTrue(
                    store.find("shared").orElseThrow().completed());
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void changingZoneDoesNotChangeInstant() {
        Clock vietnam = clock.withZone(
                ZoneId.of("Asia/Ho_Chi_Minh"));

        assertEquals(NOW, vietnam.instant());
        assertEquals(
                ZoneId.of("Asia/Ho_Chi_Minh"),
                vietnam.getZone());
    }
}
```

There are **7 JUnit tests**. No `Thread.sleep`; tests use a fixed `NOW` or mutable clock. The 1-nanosecond boundary is verified precisely. The concurrency test only proves the in-memory `ConcurrentHashMap` handles two calls in **one JVM**, not multi-pod/database exactly-once execution. `shutdownNow()` releases the executor at the end even if an assertion fails.

One note: `Future.get()` has no timeout in the pure Java example (tasks are tiny and the executor is test-controlled); if this test is adapted to stress race/lock code that might deadlock, use `future.get(2, TimeUnit.SECONDS)` so the suite does not hang. The real smoke test below always uses a finite timeout.

## 23. Calendar tests: cron and daylight saving

**`src/test/java/com/example/timetest/CronCalendarTest.java`**

```java
package com.example.timetest;

import java.time.ZoneId;
import java.time.ZonedDateTime;
import org.junit.jupiter.api.Test;
import org.springframework.scheduling.support.CronExpression;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CronCalendarTest {

    @Test
    void weekdayNineAmAfterSaturdayFallsOnMonday() {
        CronExpression expression =
                CronExpression.parse("0 0 9 * * MON-FRI");

        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime saturday =
                ZonedDateTime.of(
                        2026, 11, 7, 12, 0, 0, 0, zone);

        ZonedDateTime next = expression.next(saturday);

        assertEquals(
                ZonedDateTime.of(
                        2026, 11, 9, 9, 0, 0, 0, zone),
                next);
    }

    @Test
    void springForwardSkipsLocalTwoAmHour() {
        ZoneId zone = ZoneId.of("America/New_York");
        ZonedDateTime justBefore =
                ZonedDateTime.of(
                        2026, 3, 8, 1, 59, 0, 0, zone);

        ZonedDateTime nextMinute =
                justBefore.plusMinutes(1);

        assertEquals(3, nextMinute.getHour());
        assertEquals(0, nextMinute.getMinute());
    }
}
```

The first test uses **fixed calendar data**: Saturday 2026-11-07 at 12:00 Vietnam time → the next weekday 09:00 cron occurrence is Monday 2026-11-09. The second test demonstrates the DST gap in New York, without **automatically concluding** whether Spring `@Scheduled` will skip or compensate the trigger as business requires.

When cron depends on a business zone, pass a `ZonedDateTime` in that zone to `CronExpression.next`. Test month-end, leap-year, and DST overlap/gap cases if the business operates in regions with clock changes.

## 24. Spring integration: Clock override without running the job

**`src/test/java/com/example/timetest/DueTaskSpringIntegrationTest.java`**

```java
package com.example.timetest;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        properties = "demo.cleanup.enabled=false")
@Import(DueTaskSpringIntegrationTest.FixedTestClock.class)
class DueTaskSpringIntegrationTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedTestClock {

        @Bean
        @Primary
        Clock fixedTestClock() {
            return Clock.fixed(
                    Instant.parse("2026-04-01T12:00:00Z"),
                    ZoneOffset.UTC);
        }
    }

    @Autowired
    TaskStore store;

    @Autowired
    DueTaskService service;

    @Autowired
    Clock clock;

    @Autowired(required = false)
    CleanupTick tick;

    @BeforeEach
    void resetOnlyDemoStore() {
        store.clear();
    }

    @Test
    void serviceUsesPrimaryFixedClockBean() {
        Instant cutoff =
                Instant.parse("2026-04-01T12:00:00Z");

        assertEquals(cutoff, clock.instant());

        store.put(new TimedTask(
                "before", cutoff.minusNanos(1), false));
        store.put(new TimedTask(
                "exact", cutoff, false));
        store.put(new TimedTask(
                "after", cutoff.plusNanos(1), false));

        assertEquals(2, service.processDue());
        assertTrue(
                store.find("before").orElseThrow().completed());
        assertTrue(
                store.find("exact").orElseThrow().completed());
        assertEquals(
                false,
                store.find("after").orElseThrow().completed());
    }

    @Test
    void scheduledAdapterIsAbsentWhenDisabled() {
        assertNull(tick);
    }
}
```

Two tests verify Spring bean wiring:

- Fixed `@Primary Clock` is selected when injected into `DueTaskService`, overriding `Clock.systemUTC` from production config.
- `demo.cleanup.enabled=false` omits `CleanupTick` from the context, preventing a scheduled thread from mutating state while asserting business logic.
- `store.clear()` clears **only the demo's in-memory store**. With a real shared Redis/database, do not `clear all`; scope by test owner.
- `@SpringBootTest` tests no real network; the project has no HTTP server.

**Note:** Configuring a fixed `Clock` for the business service does not change the scheduling clock. If another scheduled bean remains enabled, it can still run on wall-clock time during tests; manage all scheduled beans of the app, not just one.

## 25. Smoke test enabling the real scheduler with bounded waiting

**`src/test/java/com/example/timetest/ScheduledTickSmokeTest.java`**

```java
package com.example.timetest;

import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
        "demo.cleanup.enabled=true",
        "demo.cleanup.initial-delay-ms=100",
        "demo.cleanup.fixed-delay-ms=100"
})
class ScheduledTickSmokeTest {

    @Autowired
    TaskStore store;

    @Autowired
    CleanupTick tick;

    @BeforeEach
    void beforeEach() {
        store.clear();
    }

    @AfterEach
    void afterEach() {
        store.clear();
    }

    @Test
    void aRealScheduledTickEventuallyProcessesOverdueTask() {
        String id = "smoke-" + UUID.randomUUID();

        store.put(new TimedTask(
                id, Instant.now().minusSeconds(30), false));

        await()
                .atMost(Duration.ofSeconds(5))
                .pollInterval(Duration.ofMillis(25))
                .untilAsserted(() -> {
                    assertTrue(
                            store.find(id)
                                    .orElseThrow()
                                    .completed());
                    assertTrue(tick.executions() > 0);
                });
    }
}
```

**There is 1 smoke test**:

1. The Spring Boot context enables `@EnableScheduling` and creates the `CleanupTick` bean because the property is true.
2. The real scheduler executes `tick()` with 100 ms fixed delay and 100 ms initial delay (in the demo test).
3. `DueTaskService` uses the system UTC business clock; the task has `dueAt` 30 seconds in the past relative to wall-clock time.
4. Awaitility polls task state for at most **5 seconds**, failing if the scheduler never processes it.
5. The test also checks `tick.executions() > 0` to confirm the callback was invoked.
6. `@AfterEach` clears the demo store; the scheduling context may continue running until context teardown, though no external persistence tasks exist.

**The smoke test uses real timing**, because its goal is proving Spring wired the scheduler and the callback runs. It does not prove "ticks run every 100 ms accurately", does not prove production scheduling SLAs, and should not be multiplied into hundreds of tests. If CI is slow, tune the timeout purposefully per test SLA; do not raise it indefinitely or revert to hard sleeps.

### 25.1. Avoiding shared contexts across test groups

`DueTaskSpringIntegrationTest` uses `demo.cleanup.enabled=false` and imports a fixed `Clock`; `ScheduledTickSmokeTest` sets the property to true. Spring TestContext treats them as distinct context configurations, so business tests do not accidentally share a running scheduler. If a project has multiple test classes sharing `true`, the scheduler can keep ticking while the cached context stays alive; split suites or enable scheduling selectively.

## 26. Total test count and run commands

| Class | Number of `@Test` | What it protects |
|---|---:|---|
| `DueTaskServiceTest` | 7 | Deadline boundaries, idempotency, in-JVM concurrency, zone |
| `CronCalendarTest` | 2 | Weekday cron, DST gap |
| `DueTaskSpringIntegrationTest` | 2 | Fixed Clock injection, disabling periodic adapter |
| `ScheduledTickSmokeTest` | 1 | Real scheduler invokes callback, eventual completion |
| **Total** | **12** | Time logic and scheduling wiring in separate layers |

Command:

```bash
./gradlew test
```

PowerShell:

```powershell
.\gradlew.bat test
```

Expected `BUILD SUCCESSFUL` if Java 17, Spring Boot 3.5.16, dependencies, and build environment match. **This is an expected result from reviewed code, not a claim that Gradle was executed on the learner's repository.** There is no fixed business stdout; tick counts may exceed 1 and vary per run. The JUnit report is typically at `build/reports/tests/test/index.html`.

If creating a new project without a Gradle wrapper, generate the wrapper via Gradle/IDE before running. Docker, PostgreSQL, or HTTP networking are unnecessary because the demo uses an in-memory store.

## 27. How to debug when time tests fail

Check in order:

1. **Which business clock is in use?** `Clock.systemUTC`, or a fixed test bean chosen via `@Primary`?
2. **How is the cutoff calculated?** Seconds/millis/nanos, inclusive/exclusive?
3. **Where are tasks stored?** In-memory store, DB, or queue; is leftover data from an earlier test present?
4. **Is `@EnableScheduling` present?** Is the scheduled bean actually in the Spring context?
5. **Is the enablement property set right?** Is `demo.cleanup.enabled=true` set on the smoke context?
6. **Are fixed delay/initial delay parsed properly?** Any milliseconds/seconds mix-up?
7. **Is there a custom `TaskScheduler` bean or executor?** Check qualifiers, thread pool, queue, and backlog.
8. **Did the task throw an exception?** Did the error handler log it without failing the JUnit thread?
9. **Are there concurrent methods/replicas?** Could the same task ID be processed twice?
10. **Is CI timezone/DST interfering?** Does logic use `Instant` or `LocalDateTime.now()`?
11. **What is the mock/await waiting on?** Is the condition observing the right side effect?
12. **Are tasks running after test cleanup?** Is a cached context/scheduler lifecycle still alive?

**Do not start by "increasing sleep to 10 seconds".** First determine whether the test checks business time or scheduler wakeup, then pick the proper tool.

## 28. Scheduler error handling, retries, and idempotency

A job can run once, fail halfway through, and run again. A system may also have multiple nodes and executor threads. Operational policy must answer:

- If a task times out, does it retry? Does each retry use backoff/jitter and a max limit?
- If processing sends a message successfully then DB commit fails, will the next run send a duplicate?
- If the handler throws an exception, does the next scheduled tick still run or get cancelled?
- If a task runs longer than `fixedRate`, can concurrent executions happen under the executor/`@Async` config?
- If the app restarts, are unprocessed jobs still in the DB?
- If two nodes both hit 09:00, which node owns the job?
- If node A's clock is 2 seconds ahead of node B, which clock does the due query use?
- Are there idempotency keys, outbox/unique constraints, or database claims to prevent double execution?

**Demo idempotency:** `TaskStore.markDue` transitions false→true once per key within the same JVM. It does **not** prove external side effects occur once. With a database, atomic claiming is usually required:

```sql
-- Conceptual PostgreSQL snippet; adapt to your actual schema.
UPDATE scheduled_jobs
SET status = 'CLAIMED'
WHERE id = :id
  AND status = 'PENDING'
  AND due_at <= :cutoff;
```

Only the worker with `affectedRows=1` proceeds. Yet even with atomic claiming, crashes between claim and side effect still need lease expiration, idempotency, or an outbox. Never assume `@Scheduled` provides distributed locking.

## 29. Multiple replicas: schedulers can fire redundantly

If two pods both run with `@Scheduled(cron=...)` enabled, **normally both** register and fire the method on their own schedules. Basic Spring Scheduling is not a cluster-aware scheduler with leader election or durable job leasing.

Practical strategies:

- **Dedicate one replica to run schedulers:** separate deployment or leader election, with failover handling.
- **Distributed lock:** DB/Redis lock with TTL/lease and fencing tokens if needed; measure/test clock skew and failure modes.
- **Database atomic claiming:** query/claim tasks by status + `dueAt` with appropriate transactions/isolation.
- **Quartz clustered JDBC job store:** use when durable/clustered scheduling semantics are needed; test with a real DB.
- **Managed external scheduler/queue:** platform cron or message delivery; still requires idempotency.
- **Idempotent handler/outbox:** protects side effects despite retries/duplicates.

**Test at the right level:** Run two worker processes or two application contexts connected to the same test DB, trigger the same due task, and assert only one atomic claim or one idempotent external side effect per contract. **Two calls to the demo's `ConcurrentHashMap` are not enough** for multi-process proof.

### 29.1. Lock TTL and clock skew

If locks rely on each node's local clock, clock drift can make both nodes think a lease expired. Use DB/server timestamps, monotonic lease mechanisms, and fencing tokens. In tests, simulate skewed clocks and crash/restarts rather than only running happy paths with the same `Clock.fixed`.

## 30. Schedule states and DST in production

Distinct terminology:

- **Scheduled-at:** when the business job was supposed to run.
- **Started-at:** when the executor actually started the callback.
- **Completed-at:** when the handler finished.
- **Next scheduled execution:** next trigger computed from cron/fixed delay/rate.
- **Misfire:** a planned execution was missed (server down/overloaded).
- **Catch-up/backfill:** processing missed runs after the service recovers.

Plain `@Scheduled` does not provide full durable misfire policies like a persistent scheduler. With a jobs table keyed by `due_at`, each tick querying `due_at <= now` can **sweep and catch up** unprocessed tasks, provided you bound batch size, maintain idempotency, and avoid catch-up storms.

Cron 09:00 in a business timezone follows local calendar time; two 09:00 occurrences in different seasons/places correspond to different UTC instants. In tests, freeze `Instant` and pass an explicit `ZoneId` for calendar logic. For DST overlaps/skips, define the expected behavior before asserting.

## 31. `@Async` does not make `@Scheduled` an automatically managed job

`@Scheduled` decides *when to invoke*; `@Async` decides *whether to hand execution to another executor* when the bean/method goes through the proper proxy. Combining both annotations can cause overlap, lost context, or hidden exceptions.

Anti-pattern example:

```java
// COUNTER-EXAMPLE: scheduler callback moves on while async side effects still run.
// Without idempotency/locking, multiple jobs can overlap.
@Scheduled(fixedRate = 1000)
public void trigger() {
    asyncService.doWork();
}
```

In production:

- Define run ownership / atomic claiming.
- Do not assume async `void` exceptions throw back to the calling thread.
- Test futures/`CompletionStage` with deadlines instead of sleep.
- Verify context propagation for `SecurityContext`/MDC/tracing.
- Do not shut down the scheduler assuming async workers cancel running tasks automatically.
- Size dedicated executor capacity, queues, and rejection policies appropriately.

A smoke test proving the callback was invoked **does not prove the async job finished**; await the proper completion state.

## 32. Reactor virtual time differs from Spring Scheduler clock

Reactor Test provides:

```java
// Snippet, requires reactor-test and a Reactor publisher using virtual scheduler.
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofDays(1)))
    .thenAwait(Duration.ofDays(1))
    .expectNext(0L)
    .verifyComplete();
```

In the right context, `StepVerifier.withVirtualTime` tests a publisher using Reactor's `VirtualTimeScheduler` without waiting 24 real hours. However, this **does not automatically make**:

- Spring `@Scheduled` jump one day into the future.
- PostgreSQL/Redis TTLs jump ahead in time.
- Regular Java `ScheduledExecutorService` become virtual.
- An external API alter its timestamps.
- Any custom scheduler supplied before `StepVerifier` installs virtual time obey it.

When testing reactive code, create the publisher **inside the supplier** passed to `withVirtualTime` so operators pick up the virtual scheduler properly. This is a conceptual snippet; the runnable project does not add the `reactor-test` dependency because the lesson focuses on Spring Scheduling and `java.time.Clock`.

## 33. Verifying real expiry and periodic cleanup in databases

Systems using MongoDB TTL indexes or Redis EXPIRE have a **backend expiration clock** independent of Java's `Clock`. Freezing the business `Clock` does not fast-forward Mongo's TTL monitor or the Redis server.

Good pattern:

1. Unit tests verify the service **writes `expiresAt`/TTL** accurately per `Clock`.
2. Repository/integration tests verify the field/index/TTL is configured properly.
3. A small number of backend expiry tests use bounded eventual waits, without demanding millisecond-exact deletion.
4. Clean up data by test owner even if TTL hasn't expired, rather than relying on expiry as the sole teardown.
5. For long retention policies, test "day 30" using a fixed domain `Clock` instead of having CI sleep 30 days.

If a scheduler periodically polls a jobs table, prioritize testing the SQL query `due_at <= cutoff` with a real DB and fixed cutoff; smoke scheduling only verifies the job triggers the method properly.

## 34. Common errors and fixes

| Symptom | Possible cause | Fix |
|---|---|---|
| Test times out after `Thread.sleep(1000)` | Scheduler busy / not running at expected cadence | Await condition with deadline, inspect logs |
| `dueAt` matches time yet test fails randomly | Calling `now()` multiple times | Inject fixed `Clock`, snapshot cutoff |
| Off-by-one at deadline | Wrong `isAfter`/`isBefore` check | Test 1ns before/at/after |
| Passes locally, fails on CI at 09:00 | Different system default timezone | Explicit `Instant` + `ZoneId` |
| Wrong weekday cron | Confusing Spring 6-field cron with Unix 5-field cron | `CronExpression.parse` + calendar tests |
| Job runs twice on Kubernetes | Each pod runs `@Scheduled` | Distributed claim/lock, idempotency |
| Fixed Clock enabled yet job does not fire early | Business `Clock` differs from scheduler clock | Call service directly in unit tests |
| Another test's fixture gets deleted | Scheduled bean still running in context | Disable job property in regular tests |
| `@Scheduled` does not run | Missing `@EnableScheduling` or bean not created | Check annotations, conditional property |
| Job keeps running after a test class | Cached Spring context still alive | Separate contexts / disable job |
| Scheduled method throws yet JUnit passes | Exception occurred on background thread | Assert postconditions, alerts/metrics |
| Async event finishes after assertion | Did not await actual completion | Awaitility/future/latch with timeout |
| Code works normally yet fails on DST transition | Nonexistent/ambiguous local time | `ZonedDateTime`/`CronExpression`/DST cases |
| `Instant` serialized without offset | `LocalDateTime` instead of `Instant` | Keep absolute timestamps / ISO 8601 |
| "Exactly once" passes in JVM yet prod sends twice | No distributed lock/outbox | Integration test with two workers/backend |
| Advancing `MutableClock` doesn't delete DB TTL rows | Backend clock is independent | Test backend expiry separately |
| Task state vanishes on restart | Store is in-memory only | Durable job table/queue |
| Job disabled in test yet ticks still appear | Another scheduling bean still active | Inventory all scheduled components |
| `fixedRate` job overlaps with `@Async` | Caller does not await worker, shared state | Atomic claim/idempotency/capacity |

## 35. Practice exercises

### Exercise A — Fixed Clock

Deadline `2026-11-08T10:00:00Z`. Write tests at `09:59:59.999999999`, `10:00:00`, and `10:00:00.000000001`. Under contract `dueAt <= now`, what are the expectations?

**Answer:** No, yes, yes. Use `Clock.fixed`/`MutableClock` and `Instant`, no sleep.

### Exercise B — Business Clock vs scheduler

You mark a `Clock.fixed(Instant.parse("2030-01-01T00:00:00Z"), UTC)` bean as `@Primary` and expect `@Scheduled(fixedDelay=5000)` to immediately run 10 years' worth of ticks. Why is that wrong?

**Answer:** Business `Clock` and `TaskScheduler` clock/executor are independent unless explicitly wired together; `Clock` does not create timers. Test the processing method directly; smoke-test the scheduler separately.

### Exercise C — FixedDelay vs FixedRate

A job takes 7 seconds; how does `fixedDelay=5s` differ from `fixedRate=5s`?

**Answer:** `fixedDelay` waits 5 seconds **after** the previous run finishes; `fixedRate` targets a cadence from start times, yet backlog/executor/overlap semantics depend on configuration and never promise running strictly every 5 seconds under heavy load.

### Exercise D — Cron timezone

Cron `0 0 9 * * MON-FRI` sets `zone=Asia/Ho_Chi_Minh`. A CI host uses UTC timezone. Should you assert the callback fires at 09:00 UTC?

**Answer:** No. Cron uses the explicit business zone; test next occurrence with `ZonedDateTime`/`ZoneId`.

### Exercise E — DST

A daily 02:30 cron job in New York. On spring-forward DST day, 02:30 local time does not exist. Can you guarantee a callback at exactly 02:30 that day using `@Scheduled` alone?

**Answer:** No. Define a misfire/DST policy and use trigger/calendar tests, and use a durable scheduler if the contract requires catch-up.

### Exercise F — Polluted test suite

`@SpringBootTest` boots both `CleanupTick` and a repository test. Mid-assertion, the scheduled tick cleans up a row. How do you fix it?

**Answer:** Disable conditional scheduling in regular tests; test the service by direct invocation, and turn on the smoke test separately. Do not lengthen sleep.

### Exercise G — Same job twice

Two threads concurrently call `processDue()` on `TaskStore`. Can both transition a task `false→true`? What does the demo test protect, and what does it NOT protect?

**Answer:** Per-key `computeIfPresent` allows only one transition within the JVM; it does not prove exactly-once across multiple JVMs/DBs/external side effects.

### Exercise H — Multi-pod

Two Spring Boot pods both enable `@Scheduled(cron=...)`. Why are reports sent twice? Propose DB claiming, distributed locking, or a durable scheduler.

### Exercise I — Quartz/misfire

The app is down from 08:55 to 09:15, cron is 09:00. After restart, does Spring `@Scheduled` automatically run a catch-up for 09:00?

**Answer:** It does not provide durable catch-up/misfire guarantees by default. If required, use persisted jobs/Quartz/DB job tables with an explicit policy.

### Exercise J — Test timeout

An async test only calls `Thread.sleep(500)` and checks status. Under heavy CI load it fails. What replaces it?

**Answer:** Awaitility `await().atMost(...).untilAsserted(...)` or `CountDownLatch.await(timeout)`, waiting on conditions instead of guessing speed.

### Exercise K — Redis TTL

You inject a fixed Clock set to tomorrow, yet Redis EXPIRE still uses server time. How must domain unit tests and TTL integration tests differ?

**Answer:** Unit-test expected TTL/`expiresAt`; integration-test the real backend and wait for eventual expiry when the contract requires it.

### Exercise L — Future.get

Two futures are tested concurrently and one deadlocks; unbounded `get()` hangs the suite. How to improve?

**Answer:** `get(duration, TimeUnit)` and `finally shutdownNow`; failures should be bounded. In the pure unit demo, threads are tiny; production-grade concurrency regression tests need deadlines.

### Exercise M — NTP clock skew

One node runs 2 seconds fast and claims jobs, while another runs 2 seconds slow and thinks its lease is still valid. What should multi-node tests simulate?

**Answer:** Clock skew, leases/fencing, server-time sources, crash/restart, and duplicate side effects.

### Exercise N — Measuring performance

A developer uses `Instant.now(clock)` to measure CPU elapsed time of a method. What goes wrong when `Clock` is fixed in a test?

**Answer:** Duration can be 0 even while the method ran; use monotonic timers like `System.nanoTime()`/Micrometer `Timer` for elapsed runtime, not the business `Clock`.

## 36. Code review checklist

- [ ] All business deadlines/expiry rely on injected `Clock` or an explicit time source.
- [ ] Production `Clock` uses `systemUTC`/zone per policy, not implicit host defaults.
- [ ] Deadlines are stored as `Instant` when representing absolute points in time.
- [ ] Tests cover before/at/after deadlines, including the one-nanosecond boundary.
- [ ] Service captures a single cutoff per batch when the business contract requires it.
- [ ] Unit tests do not `sleep` waiting for a deadline.
- [ ] `MutableClock` is used only in tests, and `withZone` has proper semantics.
- [ ] Cron expressions are verified as six fields with explicit `ZoneId`/`zone`.
- [ ] DST/holiday/month-end cases are covered when the domain depends on calendars.
- [ ] `fixedRate`/`fixedDelay`/`initialDelay` are chosen for their true semantics.
- [ ] `@EnableScheduling` and `@Scheduled` are enabled intentionally.
- [ ] Scheduled adapter is thin and the business method is directly callable.
- [ ] Scheduler is disabled by default or isolated in unrelated tests.
- [ ] Swapping `Clock` is not confused with speeding up `TaskScheduler`/executors.
- [ ] Scheduling smoke test uses bounded waits/timeouts and asserts real side effects.
- [ ] Exact tick counts or exact execution milliseconds are not inferred from smoke tests.
- [ ] Scheduled contexts from other tests do not pollute fixtures.
- [ ] Task concurrency/idempotency is tested in-JVM and out-of-JVM as needed.
- [ ] Multi-replica schedulers use distributed ownership or claiming if side effects must not repeat.
- [ ] Critical tasks have retry/backoff/lease/recovery policies.
- [ ] Job state persists across restarts if required by contract.
- [ ] Exceptions on scheduler threads are captured via metrics/logs/alerts, not swallowed silently.
- [ ] For async, tests await actual completion, not merely callback invocation.
- [ ] Reactive virtual time is applied only to compatible Reactor operators/schedulers.
- [ ] Backend TTL/DB/server clocks are tested at their own boundary.
- [ ] Test fixtures/cleanup are scoped, not wiping a shared database because of scheduler ticks.
- [ ] Timezones, UTC offsets, and calendar rules are documented in API/test contracts.
- [ ] Monotonic timers are used for elapsed time instead of a fixed business `Clock`.
- [ ] QA conclusion explicitly states whether code was only reviewed or actually executed.

**Conclusion:** **`Clock` controls business time; schedulers trigger methods on a schedule.** By separating those two responsibilities, most deadline testing becomes completely deterministic with `Clock.fixed` and a mutable test clock. `@Scheduled`, `fixedRate`, `fixedDelay`, and cron still require a few smoke tests with timeouts to verify wiring, while multi-instance coordination, DB claiming, retries, and "exactly once" must be tested at the proper infrastructure layer. Never replace a cleanly bounded design with `Thread.sleep(...)` or expect every JVM/CI run to tick smoothly with zero jitter.

### Official references

- Java 17 — `java.time.Clock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html
- Java 17 — `Instant`, `Duration`, `ZonedDateTime`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html
- Spring Framework 6.2 — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework 6.2 — `@Scheduled` Javadoc, fixedDelay/fixedRate/cron/timeUnit: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html
- Spring Framework 6.2 — `TaskScheduler` getClock/schedule: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/TaskScheduler.html
- Spring Framework 6.2 — `CronExpression`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/support/CronExpression.html
- Spring Boot 3.5 — Task Scheduling and Pool Configuration: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.5 — Integration Testing: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- JUnit Jupiter — Lifecycle, parallel execution and timeouts: https://junit.org/junit5/docs/current/user-guide/
- Awaitility — Condition-based asynchronous testing: https://github.com/awaitility/awaitility/wiki/Usage