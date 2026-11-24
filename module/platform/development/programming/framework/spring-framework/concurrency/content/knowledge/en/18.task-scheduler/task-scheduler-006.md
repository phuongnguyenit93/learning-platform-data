# The Scheduler's Clock and the Meaning of Time Used

> **Topic:** Spring Framework – concurrency  
> **Group:** TaskScheduler  
> **Core idea:** `TaskScheduler` has a `java.time.Clock` to determine “now” when computing schedules. However, an **absolute point in time** (`Instant`), a **duration** (`Duration`), a **civil calendar timezone** (`ZoneId`), and **thread-pool execution/wait time** are not the same thing. Choosing the right time type and understanding the boundaries of `getClock()`/`setClock()` prevent running cron at the wrong hour, flaky tests, and mistakenly thinking swapping the clock creates a virtual-time scheduler.

This lesson uses **Spring Framework 6.2.x + Java 17** as its context. The standalone example produces deterministic output; the Spring Context example distinguishes **the clock used to compute schedules** from **the real executor running tasks**. Non-standalone illustrative snippets are explicitly marked.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain what `TaskScheduler#getClock()` returns and what `ThreadPoolTaskScheduler#setClock(Clock)` is used for.
2. Distinguish `Clock`, `Instant`, `Duration`, `LocalDateTime`, `ZonedDateTime`, `ZoneId`, and `System.nanoTime()` by exact units and semantics.
3. Understand why `schedule(task, Instant)` differs from `scheduleAtFixedRate(task, Duration)` and `scheduleWithFixedDelay(task, Duration)`.
4. Predict the date and time of a `CronTrigger` when using a clock's default timezone or when specifying an explicit `ZoneId`.
5. Recognize risks from server timezones, DST, OS clock shifts, and slow tasks/missed triggers.
6. Use `Clock.fixed`/`Clock.offset` to test **schedule calculations** without sleeping or waiting for real cron ticks.
7. Configure a `ThreadPoolTaskScheduler` bean managed by the Spring container and observe a one-shot schedule result with `ScheduledFuture`.
8. Distinguish “virtualizing time” in tests from a **virtual-time scheduler that controls queue advancement**; do not attribute capabilities to `setClock` that the API does not promise.
9. Design logging, metrics, deadlines, and multi-instance policies for scheduled jobs.

## 2. Why Does a Scheduler Need a Clock?

A scheduler must answer several kinds of questions:

- “What time is **now**?” — use a time source to make decisions.
- “Run at **09:00 AM Vietnam time**?” — a civil timezone schedule with rules to convert to an absolute timestamp.
- “Run at exact **Instant 2026-01-01T02:00:00Z**?” — already an absolute timestamp.
- “Repeat **every 10 seconds**?” — a time span, not a time of day.
- “Run next **5 seconds after the previous run finishes**?” — a wait measured from completion, unlike a fixed wall-clock schedule.
- “How many **ms late** was the job relative to schedule?” — comparing actual time against planned time.
- “How long did the job actually use CPU or wait on I/O?” — measuring elapsed time, typically requiring a monotonic source.

Scattering `LocalDateTime.now()` or `System.currentTimeMillis()` throughout code causes results to vary between test/dev/prod environments, makes clock simulation hard, and unintentionally relies on default timezones. An injected `Clock` separates computing “when is now” from calling the system clock directly.

### 2.1. Clock Is a Time Provider Object, Not a Worker Thread

`java.time.Clock` primarily provides:

~~~java
Instant instant();
ZoneId getZone();
Clock withZone(ZoneId zone);
~~~

`Clock` has **no** command to “run a task”, creates no threads, and manages no queues or job state. A `Clock.fixed(...)` always reports the same `Instant`; that helps test time calculations, and **does not** make the CPU/OS or `ScheduledThreadPoolExecutor` automatically advance along with the simulated clock.

### 2.2. TaskScheduler Manages Scheduling and Execution Decisions

Spring `org.springframework.scheduling.TaskScheduler` is an interface for submitting a `Runnable` by a point in time or trigger rule. It can use a clock to determine the current time and pass the clock into `TriggerContext` when calculating the next trigger time.

Role breakdown:

| Component | What Question Does It Answer? | What It Does Not Automatically Guarantee |
| --- | --- | --- |
| `Clock` | What Instant is now? What is the default zone? | Does not run tasks or manage threads |
| `TaskScheduler` | When to submit/run Runnable by Instant, Duration, or Trigger? | Does not guarantee millisecond-exact execution |
| `Trigger` | What Instant should the next trigger be? | Does not execute the task itself |
| `TriggerContext` | What are the clock and prior scheduled/actual/completion times? | Does not persist jobs across restarts |
| `ThreadPoolTaskScheduler` | Implements TaskScheduler on a scheduled executor | Does not provide “cluster-wide single execution” |
| `ScheduledFuture<?>` | Tracks/cancels execution per contract | Not a durable business history |

## 3. TaskScheduler API: Where Does Clock Live?

In Spring 6.2.x, the main methods of `TaskScheduler` carry these signatures:

~~~java
Clock getClock();

ScheduledFuture<?> schedule(
        Runnable task, Instant startTime);

ScheduledFuture<?> schedule(
        Runnable task, Trigger trigger);

ScheduledFuture<?> scheduleAtFixedRate(
        Runnable task, Duration period);

ScheduledFuture<?> scheduleAtFixedRate(
        Runnable task, Instant startTime, Duration period);

ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable task, Duration delay);

ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable task, Instant startTime, Duration delay);
~~~

This is an **illustrative signature listing from the interface**, not a standalone Java file.

- `getClock()`: the clock the scheduler uses for scheduling purposes; defined as a default method on the interface.
- `schedule(task, Instant)`: once at an **absolute timestamp**; if the timestamp is in the past, standard implementations run as soon as possible.
- `schedule(task, Trigger)`: the trigger selects subsequent `Instant`s based on `TriggerContext`, suited for cron and custom rules.
- `scheduleAtFixedRate`: expresses a **periodic start cadence**; depending on worker count and task duration, actual runs may lag.
- `scheduleWithFixedDelay`: expresses **a wait interval after the previous run completes** before starting the next run.

The `TaskScheduler` API must not be confused with `TaskExecutor`: `TaskExecutor.execute` runs tasks immediately per executor mechanics, without taking an `Instant`/`Trigger` to schedule the future.

### 3.1. Default Clock

The `TaskScheduler#getClock()` Javadoc states it returns the clock used for scheduling purposes; the default clock is the system clock in the default timezone. `ThreadPoolTaskScheduler` exposes:

~~~java
Clock getClock();
void setClock(Clock clock);
~~~

In `ThreadPoolTaskScheduler`, the default is equivalent to `Clock.systemDefaultZone()` unless configured otherwise. Do **not** assume every custom `TaskScheduler` always uses the same default: inspect the actual class and app configuration.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
class SchedulerConfig {
    @Bean("businessScheduler")
    ThreadPoolTaskScheduler businessScheduler() {
        ThreadPoolTaskScheduler s = new ThreadPoolTaskScheduler();
        s.setPoolSize(2);
        s.setClock(Clock.systemUTC());
        s.setThreadNamePrefix("business-schedule-");
        return s;
    }
}
~~~

This is a **Spring snippet**, requiring imports for `@Configuration`, `@Bean`, `ThreadPoolTaskScheduler`, and `Clock`. As a bean, Spring initializes/destroys the scheduled executor per lifecycle. `Clock.systemUTC()` gives the clock a UTC zone, rather than forcing every cron in the system to run in UTC: each `CronTrigger` can specify its own zone, and the `@Scheduled` annotation also has a `zone` attribute.

### 3.2. The Scheduler's Clock Does Not Equal Every Business Event's Timezone

Suppose a user has a schedule “09:00 AM in Hanoi”. That is a rule under `ZoneId.of("Asia/Ho_Chi_Minh")`. Even if the scheduler uses `Clock.systemUTC()`, it **can still** run at 09:00 Vietnam time by specifying the zone on the cron trigger. The clock's timezone is **the default when no explicit zone is given**, not a mandatory constraint on all schedules.

Conversely, a `Clock.systemDefaultZone()` on a UTC server cannot guess that the user wanted 09:00 Vietnam time. When local wall-clock scheduling is required, store a valid zone per business entity; do not rely on the pod/node's timezone.

## 4. Distinguishing Six Time Concepts

### 4.1. Instant — An Absolute Point on the Timeline

`Instant` represents a point on the UTC timeline. Example:

~~~text
2026-01-01T02:00:00Z
~~~

That is the exact same **real moment** when displayed as:

~~~text
2026-01-01 09:00 in Asia/Ho_Chi_Minh (+07:00)
2026-01-01 02:00 in UTC
~~~

Creating an `Instant`:

~~~java
Instant when = Instant.parse("2026-01-01T02:00:00Z");
scheduler.schedule(job, when);
~~~

**Snippet**: `scheduler` and `job` must be declared. Use `Instant` for “run at this exact absolute point in time”.

### 4.2. Duration — A Span of Time

`Duration.ofSeconds(10)` represents a **length of 10 seconds**, containing no calendar date, local hour, or timezone:

~~~java
Duration period = Duration.ofSeconds(10);
scheduler.scheduleAtFixedRate(job, period);
~~~

**Snippet**: it does not say “10 AM” or “every day at 09:00”. If you want a daily local 09:00 schedule, use cron/zone; do not assume `Duration.ofHours(24)` equals one calendar day in every timezone.

### 4.3. LocalDateTime — Civil Time Missing a Zone

`LocalDateTime.of(2026, 1, 1, 9, 0)` means “09:00 on a local calendar” **without knowing where on Earth it is**. Therefore, it cannot determine an `Instant` on its own without choosing a `ZoneId` or offset:

~~~java
LocalDateTime local =
        LocalDateTime.of(2026, 1, 1, 9, 0);
ZoneId city = ZoneId.of("Asia/Ho_Chi_Minh");
Instant instant = local.atZone(city).toInstant();
~~~

**Java 17 Snippet**. Use `LocalDateTime` for “date/time” form inputs, then **always** combine with a validated zone before passing to `schedule(..., Instant)`.

### 4.4. ZonedDateTime — Local Date/Time + ZoneId

`ZonedDateTime` carries complete timezone rules: seasonal offsets, DST if applicable, and historical/policy transitions. Using `ZoneId.of("America/New_York")` differs from `ZoneOffset.of("-05:00")` during summer months because New York observes DST while a fixed offset does not.

### 4.5. Clock — A Swappable “Now”

`Instant.now(clock)` and `LocalDate.now(clock)` help make test code deterministic:

~~~java
Clock clock = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

Instant now = Instant.now(clock);
LocalDate today = LocalDate.now(clock);
~~~

**Snippet**: the clock always reports the chosen mark. No thread runs automatically when you call `clock.instant()`. `Clock.withZone(...)` creates a clock on the same timeline with a different presentation/interpretation zone; it does not “shift time forward” by 7 hours when “now” is still the same Instant.

### 4.6. System.nanoTime — Measuring Elapsed Time

If the goal is measuring “how long did the job run”, use:

~~~java
long startNanos = System.nanoTime();
try {
    doWork();
} finally {
    long elapsedNanos = System.nanoTime() - startNanos;
    recordDuration(elapsedNanos);
}
~~~

This is a **snippet** with application-provided `doWork` and `recordDuration`. `System.nanoTime()` is for elapsed differences within the same JVM, not a Unix timestamp, and must not be serialized as a schedule time. Do not convert `nanoTime()` into UTC dates/times.

## 5. Standalone Java 17: One Instant, Two Timezones, and Clock.fixed

Create the file **`ClockSemanticsDemo.java`**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

public class ClockSemanticsDemo {
    public static void main(String[] args) {
        Instant base = Instant.parse("2026-01-01T00:00:00Z");
        ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
        Clock vietnamClock = Clock.fixed(base, hcm);
        Clock utcClock = vietnamClock.withZone(ZoneOffset.UTC);

        System.out.println("instant = " + vietnamClock.instant());
        System.out.println("same instant = "
                + vietnamClock.instant().equals(utcClock.instant()));
        System.out.println("HCM date = " + LocalDate.now(vietnamClock));
        System.out.println("HCM local = "
                + LocalDateTime.now(vietnamClock));
        System.out.println("UTC local = "
                + LocalDateTime.now(utcClock));

        ZonedDateTime nineAm = ZonedDateTime.of(
                LocalDate.of(2026, 1, 1),
                LocalTime.of(9, 0),
                hcm);
        System.out.println("09 HCM in UTC = " + nineAm.toInstant());

        Duration wait = Duration.between(
                vietnamClock.instant(), nineAm.toInstant());
        System.out.println("until 09 HCM = " + wait);

        Clock shifted =
                Clock.offset(vietnamClock, Duration.ofMinutes(30));
        System.out.println("offset instant = " + shifted.instant());
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac ClockSemanticsDemo.java
java ClockSemanticsDemo
~~~

**Deterministic stdout**:

~~~text
instant = 2026-01-01T00:00:00Z
same instant = true
HCM date = 2026-01-01
HCM local = 2026-01-01T07:00
UTC local = 2026-01-01T00:00
09 HCM in UTC = 2026-01-01T02:00:00Z
until 09 HCM = PT2H
offset instant = 2026-01-01T00:30:00Z
~~~

Key observations:

1. `vietnamClock` and `utcClock` share the **same Instant** despite having different `getZone()` values.
2. Local time 07:00 in Vietnam is 00:00 UTC in this example.
3. 09:00 Vietnam time is 02:00 UTC on the same day; do not add 7 hours again to the `Instant` when scheduling.
4. `Duration.between` gives a **2-hour** wait from now until execution.
5. `Clock.offset` shifts the mark reported by the clock by 30 minutes for **calculation testing**, without actually passing 30 minutes on the OS.

**Not a Spring demo:** this is a pure Java SE example to understand time types. The Spring Context example in Section 11 uses a real `TaskScheduler` and `CronTrigger` on a fixed clock to test **calculation**.

## 6. TriggerContext: Passing the Clock Into Next-Execution Calculation

Spring `Trigger` has the method:

~~~java
Instant nextExecution(TriggerContext triggerContext);
~~~

`TriggerContext` provides:

~~~java
Clock getClock();
Instant lastScheduledExecution();
Instant lastActualExecution();
Instant lastCompletion();
~~~

These methods serve distinct roles:

- **`getClock()`:** “now/zone” used to compute the next run, especially when no history exists yet.
- **`lastScheduledExecution()`:** the planned schedule mark of the previous run; not necessarily when the worker actually entered `run()`.
- **`lastActualExecution()`:** when the task actually started on the previous run.
- **`lastCompletion()`:** when the task finished on the previous run.

Why distinguish them? Suppose a task was planned for 09:00, yet the pool was busy until 09:03 when it actually started, finishing at 09:05. A next schedule based on **scheduled 09:00** can differ from one based on **completion 09:05**.

~~~text
09:00      09:03           09:05
  |          |               |
planned    actual          completed
  |          |               |
lastScheduledExecution()    lastCompletion()
             |
      lastActualExecution()
~~~

The diagram is **an illustrative scenario**, not an assumption that every job lags by 3 minutes.

### 6.1. CronTrigger Uses the Clock and History

With `CronTrigger`, Spring pulls the clock/zone from the trigger context when needed. If no separate zone was supplied for cron, schedule calculation uses the timezone of the clock in `TriggerContext`. If an explicit `ZoneId` was passed to the constructor, that zone is used to interpret the cron expression.

Standard Spring cron has 6 fields:

~~~text
second minute hour day-of-month month day-of-week
0      0      9    *            *     *
~~~

The expression `"0 0 9 * * *"` means 09:00 every day in the active timezone; it is **not inherently UTC**.

### 6.2. Context Does Not Persist State Durably

`SimpleTriggerContext` is a simple holder used in calculations/tests. A real scheduler tracks execution context for a trigger in its runtime. If the process restarts, prior in-memory history can be lost; do not assume the scheduler maintains durable job history or replays all missed fires after deployment. If business requirements demand history, leader election, or persistence, use a durable job scheduler with appropriate storage.

## 7. CronTrigger and the Impact of Timezone

Consider the expression:

~~~text
0 0 9 * * *
~~~

If the scheduler's default clock is in **UTC**, it resolves to 09:00 UTC (which is 16:00 in Vietnam on the example date). If using the **Asia/Ho_Chi_Minh** timezone, it resolves to 09:00 Vietnam time (02:00 UTC).

An explicit form:

~~~java
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
CronTrigger businessNine = new CronTrigger(
        "0 0 9 * * *", vietnam);

scheduler.schedule(
        () -> sendDailyReport(),
        businessNine);
~~~

This is a **Spring snippet**, requiring imports for `ZoneId`, `CronTrigger`, `TaskScheduler`, and the `sendDailyReport()` business method. The zone is declared explicitly so the schedule will not shift merely because a container has a different timezone.

### 7.1. Should You Change the JVM's systemDefaultZone?

Setting `user.timezone` for the entire JVM can affect logging, serialization, database clients, default crons, and code calling `LocalDate.now()`. If one job must run in Vietnam time, it is safer to **specify the ZoneId on the job or scheduler** rather than mutating the process-wide timezone without evaluating other subsystems.

In multi-tenant systems, each tenant has its own zone, so store the zone per tenant. One global scheduler clock in UTC can still schedule individual crons in different zones without issue.

### 7.2. Asia/Ho_Chi_Minh and DST

Currently, `Asia/Ho_Chi_Minh` uses a UTC+07 offset with no annual DST transitions. However, global schedules must account for DST zones such as `America/New_York`.

- **Spring forward (gap):** a local time like 02:30 may **not exist** on the day DST starts.
- **Fall back (overlap):** a local time like 01:30 may occur **twice** under two different offsets.
- Local-clock crons need a business policy for skipping, running once, or handling two occurrences. Exact behavior depends on the trigger algorithm/version and history; do not assume every cron engine handles DST identically.
- `ZoneOffset.of("-05:00")` is only a fixed offset; it **does not preserve New York's DST rules** across months.

For “once per day” financial reports, designing deduplication by **business date + zone + job key** is just as important as picking the right cron expression. If a schedule is missed due to downtime or DST, decide whether to backfill or not.

## 8. Clock.fixed in Tests: Where Should It Be Placed?

When testing “what Instant will a 09:00 Vietnam cron fire at”, you **do not need to start a scheduler thread**. Create a `Clock.fixed` and pass it into a `SimpleTriggerContext`:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

SimpleTriggerContext context = new SimpleTriggerContext(fixed);
CronTrigger trigger = new CronTrigger("0 0 9 * * *");

Instant next = trigger.nextExecution(context);
// Expected result: 2026-01-01T02:00:00Z
~~~

This is a **Spring snippet**, requiring imports for `Clock`, `Instant`, `ZoneId`, `SimpleTriggerContext`, and `CronTrigger`. Because `context` has a fixed clock reporting 07:00 in Vietnam, the 09:00 cron for the same day computes **02:00Z**. No sleeping or waiting until real 09:00 is needed.

### 8.1. Testing an Explicit Zone Different From the Clock's Zone

~~~java
Clock fixedHcm = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

SimpleTriggerContext ctx = new SimpleTriggerContext(fixedHcm);

Instant localNine = new CronTrigger(
        "0 0 9 * * *").nextExecution(ctx);

Instant utcNine = new CronTrigger(
        "0 0 9 * * *",
        ZoneId.of("UTC")).nextExecution(ctx);
~~~

**Snippet**. Expect `localNine = 2026-01-01T02:00:00Z` and `utcNine = 2026-01-01T09:00:00Z`. Same cron string with different zones yields two different `Instant`s.

### 8.2. Why Not Set Clock.fixed Directly on a Real Scheduler and Wait for It to Run?

This is a common test-design mistake:

~~~java
ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
scheduler.setClock(Clock.fixed(testInstant, ZoneId.of("UTC")));
scheduler.initialize();
scheduler.schedule(() -> doWork(), testInstant.plusSeconds(10));
// Wrong if expecting a Clock.offset() call to automatically make the task run.
~~~

This is an **anti-pattern snippet**; it needs `testInstant` and `doWork`, and must shut down the scheduler if initialized. Once scheduled, the **underlying scheduled executor** still manages delayed tasks using the JVM's real-time mechanism. Changing a `Clock` variable in a test does not mean the scheduler's queue can be fast-forwarded on demand. `Clock.fixed` does not tick forward; `Clock.offset(...)` creates a **new clock**, without updating the old clock or the queue.

**Rule:** pure unit tests of **trigger calculation** use a fixed clock; real execution tests use a real scheduler + synchronization (future/latch), or a **virtual scheduler / test harness** explicitly built to control queue advancement.

## 9. schedule(Runnable, Instant): Turning “When” Into a Task

A call:

~~~java
Instant start = Instant.now(clock).plusSeconds(30);
ScheduledFuture<?> future = scheduler.schedule(job, start);
~~~

**Snippet**: `clock`, `scheduler`, and `job` are declared dependencies. `schedule` accepts an **absolute Instant**, not a timestamp expressed in a machine's local timezone.

### 9.1. When Instant Is Already in the Past

Per Spring's Javadoc, if `startTime` is in the past, the task runs **as soon as possible**, rather than traveling back in time. “As soon as possible” does not mean synchronously on the caller thread, as scheduling and worker availability still apply.

In the Spring Context demo in Section 11, we intentionally pass `Instant.now(clock).minusSeconds(1)` and wait on `ScheduledFuture.get(timeout)` to verify the task actually completes.

### 9.2. OS Clock Changes

When the app schedules an `Instant` in the future, the implementation may convert it into a delay relative to the current clock at scheduling time. The underlying executor may rely on a relative elapsed-time counter. Thus changing the wall clock **after a task has been queued** does not necessarily shift the precomputed wait time by the exact adjustment. Behavior depends on the implementation and trigger type (one-shot vs. recalculating next runs).

**Do not rely** on assuming “the scheduler always fires at exact hh:mm:ss even if NTP or an admin shifts the system clock” for strict precision requirements; consider clock sync, measuring schedule lag, and handling late/missed triggers via business policy.

## 10. Fixed Rate, Fixed Delay, and Cron: Different Meanings of Time

| Form | Time Parameter | Interpretation | Timezone Dependent? |
| --- | --- | --- | --- |
| `schedule(task, Instant)` | `Instant` | One execution intended at an absolute timestamp | No for defining the timestamp; may use clock when computing delay |
| `scheduleAtFixedRate(task, Duration)` | `Duration` | Repeats at a cadence/period from start time | Not a local wall-clock rule |
| `scheduleWithFixedDelay(task, Duration)` | `Duration` | Waits an interval after the previous task finishes | Not a local wall-clock rule |
| `schedule(task, Trigger)` with `CronTrigger` | Cron string + `ZoneId` | Computes civil dates/times and converts to `Instant` | Yes, when the expression expresses local calendar/hour rules |
| `@Scheduled(cron=..., zone=...)` | Cron + zone | Declarative scheduling in Spring | Yes, per chosen zone |
| `@Scheduled(fixedDelayString=...)` | Duration | After completion, waits the delay | Not a local cron |

### 10.1. Fixed Rate

Example:

~~~java
scheduler.scheduleAtFixedRate(
        () -> pollMetrics(),
        Duration.ofSeconds(10));
~~~

**Snippet**, `scheduler` and `pollMetrics()` belong to the application. The goal is roughly a 10-second cadence between **scheduled start marks**. If a task runs for 15 seconds or the pool saturates, executions can lag; do not silently assume the scheduler spawns unbounded threads to hit every tick.

With `ThreadPoolTaskScheduler` backed by `ScheduledThreadPoolExecutor`, executions of **the same periodic task** do not overlap per the JDK contract; late runs may execute back-to-back. **Different tasks/annotations** can overlap if the pool has workers and workload allows.

### 10.2. Fixed Delay

~~~java
scheduler.scheduleWithFixedDelay(
        () -> pollMetrics(),
        Duration.ofSeconds(10));
~~~

**Snippet**. If a run starts at 09:00, takes 5 seconds, and finishes at 09:00:05, the next run will **not** start before roughly 09:00:15 per fixed-delay semantics. If the previous run took 20 seconds, the next run starts correspondingly later. This fits when you want a “rest” between completions.

### 10.3. Cron

~~~java
scheduler.schedule(
        () -> generateDailySummary(),
        new CronTrigger(
                "0 0 9 * * *",
                ZoneId.of("Asia/Ho_Chi_Minh")));
~~~

**Snippet**. Cron represents **09:00 on the zone's calendar**, not strictly 24 elapsed hours since the prior run. Where DST applies in another zone, a “civil day” can be 23 or 25 elapsed hours long.

### 10.4. Illustrative Diagram

Suppose a task takes 7 seconds and the configured period/delay is 5 seconds:

~~~text
fixed-rate target:  00s  05s  10s  15s  20s ...
task run 1:         [---------7s---------]
task run 2:                    [---------7s---------]
=> actual start may lag behind schedule, depending on pool/implementation

fixed-delay:
task run 1:         [---------7s---------]
wait:                                 [---5s---]
task run 2:                                     [---------7s---------]
=> wait interval is measured from completion
~~~

The diagram only illustrates relationships, not rigid timing results for a specific environment. To verify, log `scheduled/actual/completion` and measure differences.

## 11. Java 17 Spring Context Demo: Real Clock to Run, Fixed Clock to Compute Schedules

The following example **runs** with only `spring-context`, without Spring Boot or a Web server. It proves:

1. `ThreadPoolTaskScheduler` is a container-managed Spring bean.
2. `setClock(Clock.systemUTC())` makes the scheduler expose the UTC zone.
3. A one-shot task with a past `Instant` runs as soon as possible; `ScheduledFuture.get` synchronizes the outcome.
4. `SimpleTriggerContext(Clock.fixed(...))` computes 09:00 cron in Vietnam time **without launching a worker**.
5. Cron with an explicit UTC zone produces a different `Instant`, despite the same expression.

### 11.1. Project Structure

~~~text
spring-clock-demo/
├── pom.xml
└── src/main/java/demo/SchedulerClockDemo.java
~~~

File **`pom.xml`**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-clock-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File **`src/main/java/demo/SchedulerClockDemo.java`**:

~~~java
package demo;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.scheduling.support.CronTrigger;
import org.springframework.scheduling.support.SimpleTriggerContext;

public class SchedulerClockDemo {

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean("businessScheduler")
        ThreadPoolTaskScheduler businessScheduler() {
            ThreadPoolTaskScheduler s = new ThreadPoolTaskScheduler();
            s.setPoolSize(1);
            s.setClock(Clock.systemUTC());
            s.setThreadNamePrefix("clock-demo-");
            return s; // Spring calls initialize and destroy.
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            TaskScheduler scheduler =
                    context.getBean("businessScheduler", TaskScheduler.class);

            System.out.println("scheduler zone = "
                    + scheduler.getClock().getZone());

            // Past mark -> one-shot task runs ASAP, no printing from worker.
            Instant past = scheduler.getClock().instant().minusSeconds(1);
            ScheduledFuture<?> future = scheduler.schedule(() -> { }, past);
            if (future == null) {
                throw new IllegalStateException("no task scheduled");
            }
            future.get(5, TimeUnit.SECONDS);
            System.out.println("past task done = " + future.isDone());

            Clock fixed = Clock.fixed(
                    Instant.parse("2026-01-01T00:00:00Z"),
                    ZoneId.of("Asia/Ho_Chi_Minh"));

            SimpleTriggerContext triggerContext =
                    new SimpleTriggerContext(fixed);

            CronTrigger defaultZoneCron =
                    new CronTrigger("0 0 9 * * *");
            CronTrigger utcCron =
                    new CronTrigger(
                            "0 0 9 * * *",
                            ZoneId.of("UTC"));

            System.out.println("HCM nine = "
                    + defaultZoneCron.nextExecution(triggerContext));
            System.out.println("UTC nine = "
                    + utcCron.nextExecution(triggerContext));
        }
    }
}
~~~

Run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SchedulerClockDemo
~~~

**Stdout printed by the demo class on a successful run**, excluding Maven/Spring's own logs:

~~~text
scheduler zone = Z
past task done = true
HCM nine = 2026-01-01T02:00:00Z
UTC nine = 2026-01-01T09:00:00Z
~~~

### 11.2. Why Does Stdout Not Depend on System Time?

- Zone `Z` comes from `Clock.systemUTC()`, not from the machine's default timezone.
- `past` is computed from the real scheduler clock minus 1 second; at schedule time, it is already in the past. `future.get(5, TimeUnit.SECONDS)` waits for task completion before checking `isDone`; the timeout guards against environment issues.
- Both cron calculations use `Clock.fixed` at 2026-01-01T00:00Z and explicit zones. They do not depend on the current date; no waiting until a real wall-clock hour is needed.
- `CronTrigger` is not submitted to the scheduler to run; we only query `nextExecution` with a mocked context, so the output is deterministic.
- Closing the context automatically destroys `ThreadPoolTaskScheduler` per the Spring lifecycle, leaving no unclosed custom executor behind.

**What this does not prove:** `Clock.fixed` does not make the one-shot task run in a “fake time”. The one-shot task in the example uses the **real** `Clock.systemUTC`, while the fake clock is used solely to test cron calculation.

## 12. `@Scheduled` and the Application's Timezone

Spring `@Scheduled` lets you declare schedules on bean methods if `@EnableScheduling` is enabled:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableScheduling
class SchedulingConfiguration {
}
~~~

~~~java
@Component
class DailyReportJob {

    @Scheduled(
            cron = "0 0 9 * * *",
            zone = "Asia/Ho_Chi_Minh")
    public void runDaily() {
        generateDailyReport();
    }
}
~~~

These are **two Spring class snippets**, requiring imports for `@Configuration`, `@EnableScheduling`, `@Component`, `@Scheduled`, and the `generateDailyReport` method. If the system has multiple `TaskScheduler` beans, configure scheduler selection per Spring's contract; do not assume the annotation automatically picks the bean you want.

### 12.1. When `@Scheduled(zone = ...)` Is Specified

`@Scheduled(cron = ..., zone = "Asia/Ho_Chi_Minh")` specifies the timezone for evaluating the **cron expression**. Therefore running on a UTC or Asia/Singapore server keeps the same 09:00 Vietnam schedule rule, provided the clock/timezone database and system configuration behave consistently.

### 12.2. When `zone` Is Omitted

~~~java
@Scheduled(cron = "0 0 9 * * *")
public void runDaily() { /* business code */ }
~~~

**Snippet**. The schedule will use the scheduler/clock's default timezone per Spring's mechanism, so different deploy environments may interpret 09:00 differently. If business logic requires a specific zone, write `zone` explicitly or configure the clock/trigger clearly.

### 12.3. Fixed Delay and Fixed Rate Are Not Local Cron

~~~java
@Scheduled(fixedDelay = 10, timeUnit = TimeUnit.SECONDS)
public void pollAfterCompletion() { /* poll */ }

@Scheduled(fixedRate = 10, timeUnit = TimeUnit.SECONDS)
public void pollOnCadence() { /* poll */ }
~~~

These are **method snippets**, requiring imports and Spring configuration. They represent relative durations, with no “09:00 in a timezone”. `zone` is a cron parameter, not a switch that turns fixed-rate into a wall-clock calendar schedule.

**Note on Spring MVC/Boot:** `@EnableScheduling` must be enabled in the appropriate application context. If you merely add the method annotation without enabling scheduling or if the bean is not container-managed, the task will not run. Spring Boot may auto-configure a scheduler under specific conditions; do not assume every Boot app defaults to the same pool size or timezone.

## 13. `Clock.systemUTC` and Business Zones: A Practical Strategy

An easy-to-reason-about design is:

- **The shared scheduler clock** uses UTC (`Clock.systemUTC()`), avoiding container timezone dependence.
- Each business cron rule carries an **explicit ZoneId**, e.g., `Asia/Ho_Chi_Minh`, `Europe/Berlin`, `America/New_York`.
- All planned/actual/completion timestamps are stored/logged as **UTC Instants**.
- The UI converts from Instant to local datetime using the user's/tenant's zone.
- For “tenant's today” operations, use `LocalDate.now(clock.withZone(tenantZone))` or convert from Instant, rather than default `LocalDate.now()`.
- Unit-test fixed clocks and timezone boundaries independently from the real scheduler.

Example converting from business date/time to Instant:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate date = LocalDate.of(2026, 1, 1);
LocalTime time = LocalTime.of(9, 0);

ZonedDateTime target = ZonedDateTime.of(date, time, zone);
Instant triggerAt = target.toInstant();
// triggerAt = 2026-01-01T02:00:00Z
~~~

**Snippet**, requiring `java.time` imports. Each schedule can store `zoneId` to handle DST according to its rules. Do not store only a single current offset for a “09:00 daily” schedule in a DST region.

### Should Business Code's Clock Be `scheduler.getClock()`?

For application-wide consistency, you can inject a `Clock` bean into services computing “today” as well as into scheduler configuration. However, ownership boundaries must be clear:

- The scheduler's clock governs the scheduling calculations used by the implementation.
- The business clock can share the same source, yet should be **injected explicitly** instead of reaching into the scheduler from every service.
- Tests can swap the business clock in unit tests without touching a real scheduler.
- If the two clocks differ, have a clear reason and distinguish them in logs/metrics; avoid using a fixed business clock in production.

Example:

~~~java
@Bean
Clock appClock() {
    return Clock.systemUTC();
}

@Bean
ThreadPoolTaskScheduler taskScheduler(Clock appClock) {
    ThreadPoolTaskScheduler s = new ThreadPoolTaskScheduler();
    s.setClock(appClock);
    s.setPoolSize(2);
    return s;
}
~~~

This is a **Spring configuration snippet** inside a `@Configuration` class, not a standalone file. Beans share the clock in production; tests pick a fake business clock or test trigger contexts directly, depending on the goal.

## 14. Wall Clock vs. Elapsed-Time Clock

**Wall clock** (`Clock.systemUTC()`, `Clock.systemDefaultZone()`, `Instant.now()`) anchors timestamps onto civil calendars and storable instants. It can be adjusted by NTP, system config, virtualization, or admin operations. Thus two wall-clock reads might not differ by the exact nanoseconds elapsed.

**Elapsed-time / monotonic sources** like `System.nanoTime()` compare durations inside a JVM. The number returned is not “nanos since 1970” and cannot be carried across processes to compare timestamps.

### 14.1. Do Not Use Clock Directly to Measure Precision Duration

Do not compute sensitive elapsed runtime via:

~~~java
long startMs = System.currentTimeMillis();
doWork();
long elapsedMs = System.currentTimeMillis() - startMs;
~~~

This snippet can be skewed if the system clock is adjusted mid-execution. Measure elapsed time with `System.nanoTime()` where appropriate, or Micrometer `Timer`/metric libraries using their monotonic mechanism.

### 14.2. JDK Scheduled Executor Uses Relative Delay Tracking

JDK's `ScheduledThreadPoolExecutor` uses delayed tasks tracked via an elapsed-time counter suited for timeouts/delays (such as `System.nanoTime` underneath). Setting Spring's `Clock` on the scheduler can affect how **Instants are chosen/compared at schedule creation**, yet does not turn the executor queue's timing into a “clock controllable” via `Clock.fixed`.

Operational consequence: if the OS jumps wall time, an already-queued one-shot converted to a delay and a trigger recalculating its next run **can react differently**. Do not guess a universal catch-up/skip policy for all implementations; test on the exact scheduler you use.

## 15. CronTrigger: Lenient vs. Fixed Execution

A concept not directly inside `Clock`, yet vital when asking about “time used”, is **the anchor mark for the next run**.

In Spring 6.2.x, standard `CronTrigger` uses **lenient execution** semantics: the next run can be calculated from the previous run's **completion** time, so cron marks missed while a task ran long may be skipped.

Spring also provides `CronTrigger.forFixedExecution(expression)` (available since Spring 6.1.3+) to calculate from the previous run's **scheduled** time, handling missed cron marks under fixed-execution policy. Both require examining process downtime, pool saturation, and catch-up requirements:

~~~java
CronTrigger lenient =
        new CronTrigger("0 */5 * * * *");

CronTrigger fixed =
        CronTrigger.forFixedExecution("0 */5 * * * *");
~~~

This is a **snippet**. The two triggers can produce different `nextExecution` sequences when a job runs long. Neither turns an in-memory Spring scheduler into a durable job store across restarts.

### 15.1. Distinguishing “Skip a Tick” From “Guarantee No Lost Job”

A report meant to run **every 5 minutes** might tolerate skipping when the system is busy. A billing job that must process **every billing period** cannot rely solely on cron fire counts. Persist per-period business keys, processing state, and idempotency in a DB/job store so recovery/backfill can inspect them.

### 15.2. A Fake Clock Does Not Decide Catch-Up by Itself

Even if you swap the clock, a trigger still needs **execution context/history** and policy. `Clock.fixed` lets you test “now”, but does not fabricate `lastCompletion` records or replay unexecuted runs. Unit tests must supply `SimpleTriggerContext.update(lastScheduled, lastActual, lastCompletion)` when testing historical marks.

## 16. Testing TriggerContext With Execution History

Suppose you have:

~~~text
lastScheduled = 2026-01-01T02:00:00Z
lastActual    = 2026-01-01T02:02:00Z
lastComplete  = 2026-01-01T02:04:00Z
~~~

The previous timestamps differ because the pool lagged by 2 minutes and the task ran for another 2 minutes. When testing, clarify whether the trigger anchors on **lastScheduled** or **lastCompletion**.

Example with `SimpleTriggerContext`:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-01-01T02:10:00Z"),
        ZoneId.of("UTC"));

SimpleTriggerContext c = new SimpleTriggerContext(fixed);
c.update(
        Instant.parse("2026-01-01T02:00:00Z"),
        Instant.parse("2026-01-01T02:02:00Z"),
        Instant.parse("2026-01-01T02:04:00Z"));

System.out.println(c.lastScheduledExecution());
System.out.println(c.lastActualExecution());
System.out.println(c.lastCompletion());
~~~

This is a **snippet**, requiring imports for `Clock`, `Instant`, `ZoneId`, and `SimpleTriggerContext`. The three printed lines are the three `Instant`s above, independent of real wall-clock time.

If testing `CronTrigger.forFixedExecution` with `lastScheduled`, the next instant can appear before the current clock time in order to process missed schedules; this does not mean the task will run “on time in the past”. A real scheduler must decide how to execute overdue marks.

## 17. Daylight Saving Time (DST): Testing Each Local-Time Rule

Consider reasoning about a cron running at 02:30 local time daily in New York. On the day Spring DST starts, 02:30 may not exist. A Java 17 example checking **local-time validity**:

~~~java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime nonexistent =
        LocalDateTime.of(2026, 3, 8, 2, 30);

int offsets =
        ny.getRules().getValidOffsets(nonexistent).size();

System.out.println("valid offsets = " + offsets);
~~~

This is a **snippet**. With current timezone database rules for New York's DST transition on 2026-03-08, the output is:

~~~text
valid offsets = 0
~~~

This proves **02:30 is an invalid local time** on the gap day; it does not by itself tell whether `CronTrigger` will skip, shift to 03:30, or follow another policy. To confirm cron behavior in your deployed version, test `nextExecution` on a fixed context around the transition.

On the day DST ends, there can be **2 valid offsets** for a local time during the overlap window. If the business rule is “run at most once per local calendar day”, deduplicate by `(tenantId, businessDate, jobType)` or an equivalent key regardless of whether the scheduler fires once or twice.

### 17.1. Do Not Compute “Next Day” as 24 Hours for Calendar Schedules

~~~java
Instant next = previous.plus(Duration.ofHours(24));
~~~

The **snippet** above means “after exactly 24 elapsed hours”, not always “tomorrow at 09:00 in the local timezone”. For calendar rules, convert to `ZonedDateTime` with `ZoneId`, adjust the calendar date, and test DST.

### 17.2. ZoneId vs. ZoneOffset

- `ZoneId.of("Europe/Berlin")`: Berlin's time rules, including DST in applicable periods.
- `ZoneOffset.of("+01:00")`: fixed offset; does not switch to +02:00 in summer.
- `ZoneId.of("Asia/Ho_Chi_Minh")`: regional name in the timezone database, enabling proper historical/policy interpretation; differs from a fixed string `"+07:00"` in representation and regional rule handling.

## 18. Clock Changes Between Calculations: What Is and Isn't Promised

### 18.1. Changing Clock After the Scheduler Is Running

`ThreadPoolTaskScheduler#setClock(...)` is a Spring configuration setter on the scheduler. However, you should not mutate the clock at runtime to “switch a job's timezone” without evaluating pending tasks, delay computations, existing trigger contexts, and `@Scheduled` settings. Giving each cron an explicit zone or reconfiguring jobs through a managed lifecycle is far more predictable.

### 18.2. Changing Zone Does Not Change Instant

`clock.withZone(otherZone)` does not change the real point in time returned by `Clock.fixed`; for clocks sharing the same underlying source, the new zone changes civil calendar interpretation. Yet if you call `LocalDate.now(clock)` or run a cron without an explicit zone, the outcome **can change**.

### 18.3. Shifting System Time Does Not Shift an Already-Waiting Duration

If a delayed job was already enqueued via a relative delay, setting the wall clock backward does not necessarily make the job wait longer by that exact shift. Conversely, a cron computes subsequent runs from the clock/zone and trigger history; behavior can change on the next calculation.

### 18.4. Do Not Treat Execution Time as an SLA Guarantee

`schedule(job, startTime)` expresses an **intended timestamp**, not a hard real-time guarantee. When the task actually starts depends on:

- Whether workers are free or busy.
- Queued/delayed tasks and prioritization policies.
- CPU/GC pauses, I/O, locks, and scheduler overhead.
- OS scheduling, virtualization, shutdown/pause.
- Task errors or error handlers.
- Clock synchronization and wall-time shifts.

Design “what if it is 2 minutes late?” as a business policy, rather than relying solely on a cron expression.

## 19. Measuring Schedule Lag and Task Duration

Three timestamps are commonly useful:

~~~text
plannedAt   = lastScheduledExecution
startedAt   = lastActualExecution
finishedAt  = lastCompletion

scheduleLag = startedAt - plannedAt
taskDuration = finishedAt - startedAt
~~~

At the observability layer, store `plannedAt`, `startedAt`, and `finishedAt` as `Instant`, and use a monotonic timer for execution duration when precision is required. If marks are measured across unsynchronized clocks on different machines, deltas can be skewed; keeping them in the same JVM with a consistent clock is much easier to reason about.

Example:

~~~text
plannedAt  = 09:00:00
startedAt  = 09:00:03
finishedAt = 09:00:07

schedule lag = 3 seconds
run duration = 4 seconds
~~~

When monitoring `CronTrigger`, **planned and actual marks** can diverge; merely logging “job started 09:00:03” is not enough to tell how late it was. Keep planned time in metadata/callbacks or measure via `TriggerContext`/appropriate scheduler instrumentation.

### Useful Metrics

| Metric | Interpretation |
| --- | --- |
| `scheduler_trigger_lag_seconds` | Time from planned to actual start |
| `scheduler_run_duration_seconds` | Task execution duration |
| `scheduler_execution_errors_total` | Total task failures |
| `scheduler_missed_or_skipped_total` | Marks skipped/missed per business rules |
| `scheduler_queue_wait_seconds` | Worker/queue wait time if measurable |
| `scheduler_active_threads` | Scheduler worker utilization |
| `job_business_date`/job key | Whether a business period was duplicated or missed |

Avoid attaching high-cardinality labels like random `jobId` or `userId` to every Prometheus metric. Store detailed IDs in logs/traces/job stores, and keep metric labels bounded.

## 20. Impact of Pool Size, Errors, and Lifecycle

### 20.1. Right Clock, Yet Scheduler Pool Can Still Bottleneck

`ThreadPoolTaskScheduler` relies on a scheduled thread pool. The default pool size is typically 1 unless configured otherwise. With long-running tasks, other triggers can lag even if `Clock` and cron are accurate.

~~~java
@Bean
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler s = new ThreadPoolTaskScheduler();
    s.setPoolSize(4);
    s.setClock(Clock.systemUTC());
    s.setThreadNamePrefix("scheduled-");
    return s;
}
~~~

**Spring configuration snippet**. `setPoolSize(4)` provides up to that configured number of scheduler threads; it does not guarantee 4 jobs/second or exactly-once execution.

### 20.2. Task Failure

In periodic schedules, an unhandled exception can affect future executions depending on implementation/error handler. `ThreadPoolTaskScheduler#setErrorHandler(...)` lets you configure exception handling; log with a job key and business classification, rather than assuming time will heal the error.

Do not treat periodic task failures as a reason to loop infinite retries immediately on the scheduler thread. If retries are needed, define an explicit budget, backoff, and idempotency; a cron tick and a retry for the same business period can collide.

### 20.3. Cancellation and Shutdown

`ScheduledFuture.cancel(...)` alters an already-submitted schedule, yet does not guarantee in-flight I/O tasks stop immediately or roll back side effects. Executor configuration needs shutdown policies, queue management, and graceful shutdown when the context closes.

If the application must preserve scheduling intent across deploys/restarts, an in-memory Spring scheduler is insufficient as a durable scheduler; persist job plans/state or use an appropriate solution. An accurate clock does not replace persistence.

### 20.4. Fake Clocks on Live Schedulers and Resource Leaks

Do not create a new `ThreadPoolTaskScheduler` per request just to give each user a clock. Use a container-managed scheduler and give each job an explicit zone/trigger; creating schedulers per request inflates thread counts and complicates shutdown.

## 21. Multiple Instances/Pods: A Unified Clock Does Not Mean Single Execution

Suppose a service has **3 replicas**, each enabling:

~~~java
@Scheduled(cron = "0 0 9 * * *", zone = "Asia/Ho_Chi_Minh")
public void chargeDaily() {
    processBilling();
}
~~~

This is a **Spring snippet**.

The outcome can be **3 job invocations** at 09:00 if all three replicas run their own schedulers. Configuring a uniform `Clock.systemUTC()` does not prevent duplicates. When jobs have side effects:

- Use leader election / distributed coordination when a single active worker is needed.
- Use a durable job store with atomic claiming, lease/fencing tokens, and dead-node recovery.
- Design idempotency by business key (e.g., tenant + billing date + task type) so duplicates do not issue double invoices.
- Monitor clock skew between pods and external stores.
- Do not rely solely on a TTL distributed lock while forgetting the case where an old worker keeps running after its lease expires.

**A unified clock ensures schedules are interpreted identically; an ownership mechanism decides who is allowed to execute side effects.**

## 22. Testing the Scheduler at the Right Layer

### 22.1. Unit Testing Pure Time Conversion

With `Clock.fixed`, assert:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

assertEquals(
        Instant.parse("2026-01-01T00:00:00Z"),
        fixed.instant());

assertEquals(
        LocalDate.of(2026, 1, 1),
        LocalDate.now(fixed));
~~~

This is a **JUnit 5 snippet**, requiring imports for JUnit assertions and `java.time` types. No scheduler or thread is needed.

### 22.2. Unit Testing CronTrigger With Fixed SimpleTriggerContext

~~~java
SimpleTriggerContext ctx =
        new SimpleTriggerContext(Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh")));

Instant next = new CronTrigger("0 0 9 * * *")
        .nextExecution(ctx);

assertEquals(
        Instant.parse("2026-01-01T02:00:00Z"),
        next);
~~~

This is a **Spring + JUnit 5 snippet**, launching no real tasks. Tests should also cover `CronTrigger` with explicit UTC zone, end-of-month dates, DST gaps/overlaps, and trigger contexts with history.

### 22.3. Testing Real Scheduled Execution With Future or CountDownLatch

~~~java
ScheduledFuture<?> done = scheduler.schedule(
        () -> doSmallWork(),
        scheduler.getClock().instant().minusSeconds(1));

done.get(5, TimeUnit.SECONDS);
assertTrue(done.isDone());
~~~

This is an **integration test snippet** with a running scheduler and deterministic `doSmallWork`. Do not sleep for an arbitrary duration and guess the task probably ran. A generous timeout acts as a safety guard, not the logic verifier.

### 22.4. Do Not Use Clock.fixed as a Queue-Controlling Test Scheduler

A test like “setClock(fixed), schedule(job, now+1h), advance Clock.offset(fixed,+1h), assert job ran” is wrong: `Clock.offset` creates **another Clock object**, without updating the executor's clock or shortening/extending precomputed queue deadlines.

To test scheduling with **virtual time**, use a scheduler/test harness designed to advance time, or extract `Trigger.nextExecution` into a pure function tested independently. With Spring `TaskScheduler` over a real JDK scheduled executor, you must wait for real events or test with a past timestamp.

### 22.5. Testing Different Timezone Environments

Run tests under different JVM default timezones (e.g., UTC and Asia/Ho_Chi_Minh) to verify business crons with explicit `ZoneId` do not change meaning. Do not test only on a developer laptop and then deploy to a UTC container only to suffer a surprise 7-hour shift.

### 22.6. Testing Lag and Capacity

Use a small pool to induce controlled contention; measure `actual - planned`. Test tasks longer than the period, shutdown, pause/resume, exceptions, cancellation, missed fires, and multiple instances. Do not use 1 ms precision as a hard assertion in CI when the goal is testing date/time logic.

## 23. Common Mistakes to Avoid

**Mistake 1 — “The scheduler's Clock is a virtual clock to run tasks whenever desired.”** False. `Clock` only supplies “now/zone”; the thread pool and delay queue have their own execution mechanics.

**Mistake 2 — “Swap in Clock.fixed, tick forward one hour, and cron fires.”** False. A fixed clock does not tick, and creating `Clock.offset` does not drive an already-scheduled executor.

**Mistake 3 — “Instant.parse(...Z) is 09:00 Vietnam time if I write 09:00Z.”** False. 09:00Z is 16:00 in Vietnam under UTC+7; convert local time/zone to `Instant` properly.

**Mistake 4 — “LocalDateTime is already an absolute point in time.”** False. It lacks a timezone.

**Mistake 5 — “ZoneOffset is a ZoneId with DST.”** False. A fixed offset differs from an IANA rule-based region.

**Mistake 6 — “Cron 09:00 is always the user's local 09:00.”** False unless `zone`/`ZoneId` is set per business rules.

**Mistake 7 — “Clock.systemUTC and Clock.systemDefaultZone differ in real elapsed time.”** Usually they share the same underlying real-time source and differ only in the timezone used for interpretation. Do not confuse changing zone with shifting an `Instant`.

**Mistake 8 — “A 24-hour fixed rate = 09:00 every day regardless of DST.”** False in DST zones and for calendar-day requirements.

**Mistake 9 — “Fixed delay measures from start time.”** False: fixed delay measures from **completion** of the previous execution.

**Mistake 10 — “Fixed rate means every execution starts on the exact second.”** False when pools are busy, tasks are slow, or OS scheduling lags.

**Mistake 11 — “CronTrigger only needs an expression to know the timezone.”** False without context/explicit zone; the scheduler/clock's timezone matters.

**Mistake 12 — “If schedule() receives a past time, it drops the job.”** Not per Spring Javadoc for one-shot `Instant`: the task runs as soon as possible.

**Mistake 13 — “Measuring elapsed runtime with System.currentTimeMillis is always accurate.”** False when wall-clock time is adjusted; use a monotonic source for time differences.

**Mistake 14 — “NanoTime is a nanosecond Unix timestamp.”** False. It is only suitable for comparing elapsed differences within the same JVM.

**Mistake 15 — “One scheduler bean guarantees cron runs once across the cluster.”** False. Each instance typically runs its own scheduler, requiring coordination/idempotency.

**Mistake 16 — “@Scheduled returning means business data is durably committed.”** Not if the task spawned fire-and-forget work, a DB transaction/queue hasn't committed, or the process crashes.

**Mistake 17 — “Every TaskScheduler implementation's clock behaves identically.”** Nothing guarantees all adapters/custom schedulers share identical behavior; inspect the exact class/version.

**Mistake 18 — “Switching Clock to UTC automatically fixes all crons.”** Not if `CronTrigger` instances already specify their own timezones or business code reads system default time directly.

**Mistake 19 — “Every CronTrigger replays all missed marks.”** False. Lenient/fixed execution and restart persistence are separate concerns.

**Mistake 20 — “With Clock.fixed, there is no need to clean up the scheduler in tests.”** False. If a test creates a real `ThreadPoolTaskScheduler`, you must still shut it down / close the context.

## 24. Self-Check Exercises

**Question 1.** Given `Clock.fixed(2026-01-01T00:00:00Z, Asia/Ho_Chi_Minh)`, what time is `LocalTime.now(clock)`?

**Answer:** 07:00, because Vietnam is UTC+7 at that timestamp. `clock.instant()` remains 00:00Z.

**Question 2.** What `Instant` will cron `"0 0 9 * * *"` produce first with `SimpleTriggerContext` using the clock above?

**Answer:** 2026-01-01T02:00:00Z. Local 09:00 HCM = UTC 02:00.

**Question 3.** With the same clock, if `CronTrigger` is constructed with `ZoneId.of("UTC")`, what is the result?

**Answer:** 2026-01-01T09:00:00Z. The trigger's explicit zone takes precedence when evaluating cron.

**Question 4.** Is `scheduleAtFixedRate(job, Duration.ofHours(24))` equivalent to “09:00 AM New York time every day”?

**Answer:** No. Fixed rate repeats every 24 elapsed hours, whereas a 09:00 business cron depends on calendar/DST rules.

**Question 5.** Does `ThreadPoolTaskScheduler#setClock(Clock.fixed(...))` cause a delayed queue to fire automatically after a test creates a new `Clock.offset(...)`?

**Answer:** No. `Clock` does not control virtual-time advancement of the underlying executor. Test trigger calculation separately, or use a test scheduler with true virtual time.

**Question 6.** A task is planned for 09:00, actually starts at 09:02, and ends at 09:04. What are the three values in `TriggerContext`?

**Answer:** `lastScheduledExecution≈09:00`, `lastActualExecution≈09:02`, `lastCompletion≈09:04`, assuming a fully recorded execution.

**Question 7.** A job's cron is declared on three pods in the same zone. At 09:00, is a single business side effect guaranteed?

**Answer:** No. Multiple pods can run concurrently; claiming/leadership/idempotency by business key is needed.

**Question 8.** Why shouldn't you measure job duration with `Instant.now()` when accurate elapsed time is needed?

**Answer:** Wall-clock time can be adjusted; use `System.nanoTime()` or an appropriate `Timer` to measure elapsed time inside the JVM.

**Question 9.** Does `@Scheduled(cron="0 0 9 * * *", zone="Asia/Ho_Chi_Minh")` running on a UTC server change to 09:00 UTC?

**Answer:** No, the zone was specified for cron. 09:00 Vietnam time in the example maps to 02:00 UTC.

**Question 10.** A scheduler submits a one-shot task with an `Instant` in the past. What happens?

**Answer:** Per Spring `TaskScheduler`, the task executes as soon as possible rather than running back in time. Execution still depends on workers and system state.

## 25. Pre-Deployment Checklist

- [ ] Distinguish absolute timestamps (`Instant`), local calendar times (`LocalDateTime + ZoneId`), and relative spans (`Duration`).
- [ ] Verify the concrete `TaskScheduler` implementation and actual `getClock()` value.
- [ ] For local business schedules, use an explicit `ZoneId` rather than relying on server timezone.
- [ ] Ensure cron uses Spring's 6-field syntax, with seconds as the first field.
- [ ] For DST zones, define gap/overlap handling and per-period business deduplication.
- [ ] Choose fixed rate/delay for their exact timing semantics without mistaking them for cron.
- [ ] Inject `Clock` for calculations, and test with `Clock.fixed`/`SimpleTriggerContext` when testing schedule math.
- [ ] Do not expect `Clock.fixed` to advance on its own or control a real scheduler's delay queue.
- [ ] Define business deadlines and timeouts; accept that the scheduler is not hard real-time.
- [ ] Measure schedule lag and runtime, using a monotonic source for elapsed durations.
- [ ] Configure pool size, error handler, cancellation, and shutdown explicitly.
- [ ] Do not equate `Clock` configuration with cluster-wide exactly-once guarantees.
- [ ] Establish backfill/recovery procedures for restarts or missed firings.
- [ ] Keep unit-test outcomes independent of current time, laptop timezone, `Thread.sleep`, or real cron firing.
- [ ] Give integration tests futures/latches with timeouts, and always clean up scheduler beans/executors afterward.
- [ ] Log/emit planned/actual/completion timestamps clearly, never using `nanoTime` as a Unix timestamp.

## 26. Summary

**`Clock` answers “when is now, and in which timezone?”; `TaskScheduler` decides “which task is scheduled and executed at which mark?”.** An `Instant` is an absolute timestamp; a `Duration` is a span of time; `ZoneId` governs civil calendar interpretation. `TriggerContext` carries the clock and run history so `CronTrigger` can compute the next mark.

In Spring 6.2.x, `ThreadPoolTaskScheduler` exposes `getClock()` and `setClock(Clock)`. Configuring a UTC clock avoids server-timezone dependence for default calculations; specifying an explicit zone on local crons is the safer way to express business rules. To test time logic, use `Clock.fixed` and query `CronTrigger.nextExecution(SimpleTriggerContext)`; do **not** treat `Clock` as a switch controlling the executor's virtual-time queue.

In production, always account for task duration, worker capacity, DST, crashes/restarts, cluster duplication, idempotency, and observability. **Having the right clock alone is not enough for a job to run once, on time, and business-correctly.**

## Official References

- Spring Framework 6.2 Reference — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework 6.2 Javadoc — `TaskScheduler`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/TaskScheduler.html
- Spring Framework 6.2 Javadoc — `ThreadPoolTaskScheduler` (getClock/setClock): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html
- Spring Framework 6.2 Javadoc — `TriggerContext`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/TriggerContext.html
- Spring Framework 6.2 Javadoc — `CronTrigger`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/support/CronTrigger.html
- Spring Framework 6.2 Javadoc — `SimpleTriggerContext`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/support/SimpleTriggerContext.html
- Spring Framework 6.2 Javadoc — `@Scheduled`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html
- Java SE 17 Javadoc — `Clock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html
- Java SE 17 Javadoc — `Instant`, `Duration`, `ZoneId`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html
- Java SE 17 Javadoc — `ScheduledThreadPoolExecutor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html
