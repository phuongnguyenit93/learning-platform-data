# Schedule Timezones in Spring Batch

## 1. Why Is Timezone Part of a Batch Schedule?

In batch systems, a requirement like “run at 02:15 daily” is missing one decisive detail: **02:15 in which timezone?** If a developer machine uses Vietnam time, production runs on UTC, and business data belongs to the New York market, the exact same cron expression can fire at three different absolute instants.

For example, an order reconciliation job must run at **02:15 AM Vietnam time** and process transactions from **the previous business day**. When this rule is stated explicitly:

- 02:15 on 2026-11-16 in `Asia/Ho_Chi_Minh` is 19:15 UTC on 2026-11-15.
- The job's business parameter is `businessDate=2026-11-15`.
- Even if the JVM/host/container is set to UTC, the run is scheduled according to Vietnam time.
- When backfilling is needed, you can still determine the exact data date to process.

Without an explicit timezone, common bugs include jobs firing at shifted hours after deployment, reports off by one day, jobs firing twice during daylight saving transitions, or data getting skipped during schedule shifts.

This lesson belongs to *Spring Batch Core Processing → Scheduling* and focuses on **schedule timezones**: understanding, configuring, testing, and operating a Spring Batch job's schedule.

**Learning objectives**

1. Distinguish absolute instants, local time, offsets, and regional timezones.
2. Configure `@Scheduled(cron = ..., zone = ...)` with Spring Framework to run Spring Batch jobs on business time.
3. Build `JobParameters` identifying the exact data date, preserving idempotency and restartability.
4. Understand skipped and repeated hours caused by daylight saving time (DST).
5. Design deterministic tests with `java.time`, `Clock`, and `CronExpression`.
6. Recognize limitations of in-app schedulers, multi-instance deployments, and backfill needs.

Main examples use **Java 17+, Spring Boot 3.x, Spring Framework 6.x, and Spring Batch 5.x**. Spring Framework APIs can also be used with Spring Batch 6.x when selecting a compatible Spring Boot/Spring Framework release.

---

## 2. Spring Batch and the Scheduler Are Two Separate Responsibilities

**Spring Batch** provides execution components: `Job`, `Step`, `JobLauncher`, `JobRepository`, `JobParameters`, checkpoints, retries, and restarts. A `Job` itself has no concept of “02:15 daily Vietnam time.”

**The scheduler** decides when to send a job run request. The scheduler can be:

- Spring Framework's `@Scheduled` with `@EnableScheduling`.
- Quartz Scheduler with a cron trigger and explicit timezone.
- Kubernetes CronJob with `spec.timeZone` (on Kubernetes versions that support it).
- Apache Airflow, an enterprise scheduler, or a batch orchestration platform.
- A separate application emitting events and invoking jobs via API.

Responsibility flow:

```text
                  Business policy
           "02:15 Asia/Ho_Chi_Minh daily"
                            │
                            ▼
                      Scheduler
                (computes trigger instant)
                            │
                            ▼
                JobLauncher / JobOperator
             (passes Job + JobParameters)
                            │
                            ▼
                   Spring Batch Job
              ┌─────────────┴─────────────┐
              ▼                           ▼
          JobRepository            Reader / Processor /
        stores metadata             Writer, transactions
              │                           │
              └─────────────┬─────────────┘
                            ▼
               Status and output data
```

A proper schedule requires both layers:

- **When to trigger:** cron, timezone, holiday calendars, run window, and missed-run catch-up.
- **Which data to process:** business date, accounting period, data partition, and `JobInstance`-identifying parameters.

Firing at the right time does not guarantee the job processes the right data date. A job running at 00:05 may need to process the previous day; a job running at 22:00 may prepare data for the next day. Encode this rule in `JobParameters` or a dedicated business policy layer.

---

## 3. Java Time Types to Know

Java's `java.time` package has several temporal types. Picking the wrong type commonly causes scheduling bugs.

| Type | Represents | Example | Where to use |
|---|---|---|---|
| `Instant` | An absolute instant on the UTC timeline | `2026-11-15T19:15:00Z` | Logging instants, storing trigger timestamps, comparing instants |
| `LocalDate` | Calendar date without time or timezone | `2026-11-15` | Business date, partition key, report name |
| `LocalTime` | Time of day without date or timezone | `02:15` | Required business wall-clock time |
| `LocalDateTime` | Wall-clock date and time, **does not define a unique instant** | `2026-11-16T02:15` | Schedule input before applying `ZoneId` |
| `ZoneOffset` | Fixed offset from UTC | `+07:00` | Representing an offset at a specific instant |
| `ZoneId` | Regional timezone rules | `Asia/Ho_Chi_Minh` | Location-based schedule policies |
| `ZonedDateTime` | Local date/time combined with timezone and resolved offset | `2026-11-16T02:15+07:00[Asia/Ho_Chi_Minh]` | Computing schedules, displaying market hours |
| `OffsetDateTime` | Date, time, and offset without full regional rules | `2026-11-16T02:15+07:00` | System integration when contracts use offsets |
| `Clock` | Time source replaceable in tests | `Clock.systemUTC()` | Decoupling logic from the machine's real clock |

### 3.1. `ZoneId` vs. `ZoneOffset`

`ZoneOffset.of("+07:00")` represents a fixed offset. `ZoneId.of("Asia/Ho_Chi_Minh")` represents a region with rules in the IANA time zone database (tzdb).

In markets with daylight saving time, offsets vary by season:

- `America/New_York` can be UTC−05:00 or UTC−04:00 depending on the date.
- `Europe/Berlin` can be UTC+01:00 or UTC+02:00.
- `Asia/Ho_Chi_Minh` is currently UTC+07:00 and does not observe DST under current rules.

If the business requires “09:00 New York time,” use `ZoneId.of("America/New_York")`. A fixed `-05:00` offset shifts local summer time by one hour.

### 3.2. One Instant Can Belong to Two Different Calendar Dates

```java
Instant instant = Instant.parse("2026-11-15T19:15:00Z");

ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime inVietnam = instant.atZone(vietnam);
ZonedDateTime inUtc = instant.atZone(ZoneOffset.UTC);

System.out.println(inVietnam);
// 2026-11-16T02:15+07:00[Asia/Ho_Chi_Minh]

System.out.println(inUtc);
// 2026-11-15T19:15Z

System.out.println(inVietnam.toLocalDate());
// 2026-11-16

System.out.println(inUtc.toLocalDate());
// 2026-11-15
```

**This is a single instant**, yet the calendar date differs across the two timezones. Calling `LocalDate.now()` without a `ZoneId` can produce the wrong `businessDate` on servers using a different timezone than developer machines.

### 3.3. `LocalDateTime` Alone Is Insufficient to Determine Run Instant

`LocalDateTime.of(2026, 11, 16, 2, 15)` only says “Nov 16 at 02:15.” You must combine it with a timezone to convert to an `Instant`:

```java
LocalDateTime local = LocalDateTime.of(2026, 11, 16, 2, 15);
ZonedDateTime scheduled = local.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));

Instant actualInstant = scheduled.toInstant();
// 2026-11-15T19:15:00Z
```

In DST regions, certain `LocalDateTime` values either do not exist or occur twice. This is examined in a dedicated section below.

---

## 4. Cron Expressions and Timezones in `@Scheduled`

Spring Framework supports cron schedules via the `@Scheduled` annotation.

```java
@Scheduled(cron = "0 15 2 * * *", zone = "Asia/Ho_Chi_Minh")
public void runDailyBatch() {
    // Submit job run request.
}
```

In Spring syntax, cron normally has **6 fields**, prepending seconds:

```text
┌──────────── second (0)
│ ┌────────── minute (15)
│ │ ┌──────── hour (2)
│ │ │ ┌────── day of month (*)
│ │ │ │ ┌──── month (*)
│ │ │ │ │ ┌── day of week (*)
│ │ │ │ │ │
0 15 2 * * *
```

Examples:

| Spring cron | Meaning | Timezone to apply |
|---|---|---|
| `0 15 2 * * *` | 02:15 every day | `Asia/Ho_Chi_Minh` if batch serves Vietnam |
| `0 0 9 * * MON-FRI` | 09:00 Monday–Friday | Market's timezone |
| `0 30 23 L * *` | 23:30 on the last day of the month | Accounting period's timezone |
| `0 0 0 1 * *` | 00:00 on the first day of each month | Timezone defining the month |
| `0 0 12 * * SUN` | 12:00 Sunday | Business local timezone |

Note: Spring uses six-field cron, whereas traditional UNIX cron expressions have five fields. Do not copy expressions from `crontab` to `@Scheduled` without checking field counts. Quartz has additional conventions and its own day-of-week interpretation; avoid mechanically copying expressions between schedulers.

### 4.1. Meaning of `zone`

Per Spring Framework Javadoc, `zone` is the timezone used to resolve the **cron expression**. When omitted, the scheduler uses its default timezone.

```java
// Accurate 02:15 in Vietnam, regardless of JVM UTC or New York:
@Scheduled(cron = "0 15 2 * * *", zone = "Asia/Ho_Chi_Minh")

// Depends on the scheduler's default timezone:
@Scheduled(cron = "0 15 2 * * *")
```

Explicit configuration is much more stable across containers, CI, and multiple environments. Do not rely on OS timezone or `-Duser.timezone` flags to encode a business rule.

### 4.2. `zone` Applies to Cron, Not Every Schedule Type

`@Scheduled` also offers `fixedRate` and `fixedDelay`:

```java
@Scheduled(fixedRate = 60_000)  // ~60 seconds between start times
public void poll() {}

@Scheduled(fixedDelay = 60_000) // wait 60 seconds after previous run finishes
public void retryPoll() {}
```

These are **interval-based** and do not express “daily at 02:15 in a timezone.” Specifically:

- `fixedRate = 86_400_000` does not mean “daily at 02:15 local time” where DST exists.
- A calendar day can span 23 or 25 hours during DST transitions.
- If the requirement is a local wall-clock schedule, use cron with `zone` or a calendar-aware trigger.
- If the requirement is polling every 10 minutes, `fixedRate`/`fixedDelay` is usually more natural.

### 4.3. Configuring Cron from `application.yml`

Instead of hardcoding schedules in source code, use placeholders:

```yaml
app:
  batch:
    schedule:
      cron: "0 15 2 * * *"
      zone: "Asia/Ho_Chi_Minh"

spring:
  batch:
    job:
      enabled: false
```

Then:

```java
@Scheduled(
    cron = "${app.batch.schedule.cron}",
    zone = "${app.batch.schedule.zone}"
)
public void submitDailyJob() {
    // ...
}
```

`spring.batch.job.enabled=false` prevents Spring Boot from auto-running batch jobs on startup, ensuring launches occur only via your schedule or designed orchestrator. The cron value `"-"` is supported by Spring as a disabled trigger, useful for turning off schedules per environment:

```yaml
app:
  batch:
    schedule:
      cron: "-"
      zone: "Asia/Ho_Chi_Minh"
```

Disabling the schedule **does not remove the job definition**, nor does it block manual launches via other control APIs.

---

## 5. Practical Example: Spring Batch Running on Vietnam Time

### 5.1. Requirements

An e-commerce system needs a `dailyImportJob`:

- Runs at **02:15 daily in `Asia/Ho_Chi_Minh`**.
- Processes orders for the **calendar day before the run date** in Vietnam.
- Records the request timestamp as a UTC `Instant` for observability.
- Maps the same business date to a single `JobInstance`.
- Recognizes duplicate requests if the schedule fires repeatedly.
- Business date logic must be testable without waiting for the real clock.

Assume `dailyImportJob` is already configured as a `Job` bean in the Spring Batch app, with standard Spring Boot component scanning.

### 5.2. Dependencies

Gradle example with Spring Boot 3.x and Spring Batch 5.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    // Used with JDBC JobRepository if the app chooses H2 for demo/test.
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

Production projects should use a persistently operated metadata database rather than in-memory H2 so restart history survives application shutdowns.

### 5.3. `Clock` and `ZoneId` Beans

```java
package com.example.batch.schedule;

import java.time.Clock;
import java.time.ZoneId;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration(proxyBeanMethods = false)
@EnableScheduling
public class ScheduleConfiguration {

    @Bean
    Clock batchClock() {
        return Clock.systemUTC();
    }

    @Bean
    ZoneId businessZone(
            @Value("${app.batch.schedule.zone}") String zoneName) {
        return ZoneId.of(zoneName);
    }
}
```

Two design intents:

1. `Clock.systemUTC()` provides absolute instants independent of the host's default timezone.
2. `ZoneId.of(zoneName)` validates the zone ID syntax on bean creation; an invalid zone fails fast instead of silently falling back to GMT as some legacy `TimeZone` string APIs do.

Moreover, the same `app.batch.schedule.zone` property is referenced by `@Scheduled`. Thus the trigger and data-date calculation rule share one timezone.

### 5.4. Job Scheduling Component

```java
package com.example.batch.schedule;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRestartException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DailyImportScheduler {

    private static final Logger log =
            LoggerFactory.getLogger(DailyImportScheduler.class);

    private final JobLauncher jobLauncher;
    private final Job dailyImportJob;
    private final Clock clock;
    private final ZoneId businessZone;

    public DailyImportScheduler(
            JobLauncher jobLauncher,
            @Qualifier("dailyImportJob") Job dailyImportJob,
            Clock batchClock,
            ZoneId businessZone) {
        this.jobLauncher = jobLauncher;
        this.dailyImportJob = dailyImportJob;
        this.clock = batchClock;
        this.businessZone = businessZone;
    }

    @Scheduled(
        cron = "${app.batch.schedule.cron}",
        zone = "${app.batch.schedule.zone}"
    )
    public void launch() {
        Instant requestedAt = clock.instant();
        LocalDate businessDate =
                businessDateFor(requestedAt, businessZone);

        JobParameters parameters = new JobParametersBuilder()
                // Identifying: one JobInstance per businessDate.
                .addString("businessDate", businessDate.toString(), true)
                // For observability only; does not alter JobInstance.
                .addString("scheduleZone", businessZone.getId(), false)
                .addString("requestedAtUtc", requestedAt.toString(), false)
                .toJobParameters();

        try {
            JobExecution execution =
                    jobLauncher.run(dailyImportJob, parameters);

            log.info("Submitted dailyImportJob: businessDate={}, "
                    + "jobExecutionId={}, status={}",
                    businessDate, execution.getId(),
                    execution.getStatus());

        } catch (JobExecutionAlreadyRunningException ex) {
            log.info("dailyImportJob already running for {}",
                    businessDate);

        } catch (JobInstanceAlreadyCompleteException ex) {
            log.info("dailyImportJob already completed for {}",
                    businessDate);

        } catch (JobRestartException | JobParametersInvalidException ex) {
            log.error("Cannot start dailyImportJob for {}",
                    businessDate, ex);
            throw new IllegalStateException(
                    "Unable to launch dailyImportJob", ex);
        }
    }

    static LocalDate businessDateFor(
            Instant requestedAt, ZoneId businessZone) {
        // Example policy: each night processes the previous day's data.
        return requestedAt.atZone(businessZone)
                .toLocalDate()
                .minusDays(1);
    }
}
```

**Analysis:**

- `@Scheduled(cron, zone)` controls only **when `launch()` is invoked**.
- `requestedAt` is captured as an `Instant` from `Clock`, convenient for logging, lag measurement, and unit tests.
- `businessDateFor(...)` converts the instant to a calendar date in the **business timezone**, then steps back one day per policy.
- `businessDate` is marked `identifying=true`, because in this problem each day needs its own `JobInstance`.
- `requestedAtUtc` is non-identifying. Making the current timestamp identifying would create a new `JobInstance` on every call, losing per-day duplicate detection.
- Once an instance is `COMPLETED`, Spring Batch refuses to rerun that instance as a fresh pass. In the example, this is logged as an already-completed duplicate request.
- While the same instance is running, a new request typically receives `JobExecutionAlreadyRunningException` per configured repository transactions/isolation.
- If the previous instance `FAILED` and the job is restartable, calling with the same identifying parameters triggers a **restart**, rather than being automatically skipped. If restarts require human approval, separate that policy from the automatic schedule.
- `JobLauncher.run(...)` can run synchronously or asynchronously depending on launcher configuration. The status returned immediately is not necessarily final. Read `JobExecution`/repository after the job finishes to know the final outcome.

Choosing `businessDate = previous day` is a **business rule**, not a Spring Batch default. For jobs processing the current day, adjust the calculation accordingly.

### 5.5. Run Date and Data Date Differ

At this instant:

```text
UTC instant:      2026-11-15T19:15:00Z
Asia/Ho_Chi_Minh: 2026-11-16 02:15 (+07:00)
Schedule fires:   2026-11-16 in Vietnam time
businessDate:     2026-11-15
```

If the host runs in UTC and code calls `LocalDate.now().minusDays(1)`, at that exact instant it yields `businessDate=2026-11-14`. That is a date-shift bug even though the cron trigger fired on time. Therefore **trigger timezone and data-date timezone must be designed together**.

### 5.6. Passing `businessDate` to `ItemReader`/`StepScope`

Inside the job, readers can receive parameters via late binding:

```java
@Bean
@StepScope
FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['businessDate']}") String date) {

    String inputFile = "/data/orders-" + date + ".csv";

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("id", "amount")
            .targetType(Order.class)
            .build();
}
```

This illustrates using the date as a resource key; it assumes `Order` and the corresponding Spring Batch imports are declared. In production, handle missing files, encoding, headers, retries, and data contract validation.

Even if the input path is passed directly in `JobParameters` instead of derived from the date, log the **business date** clearly to prevent confusion between trigger date and data date.

---

## 6. DST: Disappearing Hours and Repeated Hours

DST (daylight saving time) is why “one calendar day” cannot be equated with “24 consecutive hours” in every timezone.

### 6.1. Spring-Forward: A Local Hour Does Not Exist

In `America/New_York`, on **2026-03-08**, clocks transition to DST. Local clocks jump from about `01:59:59` to `03:00:00`.

Thus, local time `2026-03-08 02:30` **does not exist** in that region:

```text
America/New_York, 2026-03-08

01:59:59 (UTC−05:00)
       │
       ▼  DST transition
03:00:00 (UTC−04:00)

02:30:00 does not occur
```

Cron `0 30 2 * * *` may have no trigger matching “02:30 local” on that day; whether it skips or compensates depends on the scheduler, version, and misfire policy.

If the business requires **exactly once per day** regardless of DST, document the policy explicitly: skip that day, shift to 03:00, pick another hour, or backfill. Never assume cron automatically guarantees “once every day.”

### 6.2. Fall-Back: A Local Hour Occurs Twice

In `America/New_York`, on **2026-11-01**, clocks fall back from DST to standard time. The `01:00–01:59` hour occurs twice under two offsets:

```text
America/New_York, 2026-11-01

01:30 (UTC−04:00)  ← first occurrence
...
01:59:59 (UTC−04:00)
       │
       ▼  fall back to standard time
01:00 (UTC−05:00)
...
01:30 (UTC−05:00)  ← second occurrence
```

A cron running at `01:30` local time needs an explicit policy for this ambiguous hour. Some triggers/schedulers may treat the two occurrences as distinct instants; actual behavior depends on “next firing” logic, trigger type, and version. Do not assume every scheduler fires twice or once without testing.

### 6.3. Inspecting Local Times with `ZoneRules`

Java lets you verify whether a local time has 0, 1, or 2 valid offsets:

```java
ZoneId newYork = ZoneId.of("America/New_York");

LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);
List<ZoneOffset> gapOffsets =
        newYork.getRules().getValidOffsets(gap);
// gapOffsets.size() == 0: local time does not exist.

LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);
List<ZoneOffset> overlapOffsets =
        newYork.getRules().getValidOffsets(overlap);
// overlapOffsets.size() == 2: local time occurs twice.
```

Imports:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;
```

These values depend on tzdb rules for the chosen year. For long-horizon schedules, keep JDK/container timezone data updated when timezone laws change.

### 6.4. Which Rules Suit Business Batches?

| Business requirement | Policy to consider |
|---|---|
| “Process exactly once per business day” | Use `businessDate` as unique key, store history, reconcile unprocessed days |
| “Run at 02:30 local” | Define behavior on DST gap days; consider shifting to a safer hour |
| “Run strictly every 24 hours” | Use an interval/instant trigger rather than tying to a fixed local hour |
| “Process every hourly slot, including repeated hours” | Key by business period plus offset/instant, not just `LocalDateTime` |
| “Never run concurrently” | Use coordination/locks and policies when a job overruns the next tick |
| “Daily report on New York time” | Derive business date from `America/New_York`, not server timezone |

Scheduling at `04:00` in DST regions reduces gap/overlap risk because transitions rarely hit that hour; nevertheless, verify regional rules and business policies rather than treating it as universal across all countries.

---

## 7. Date-Shift Scenarios Caused by Timezones

### 7.1. UTC Server, Vietnam Schedule

An application declares `@Scheduled(cron = "0 15 2 * * *")` without `zone`. On a Vietnam-timezone dev machine, it fires at 02:15 Vietnam. Deployed to a default UTC container, cron fires at 02:15 UTC, which is 09:15 Vietnam.

If 02:15 Vietnam is required, write:

```java
@Scheduled(cron = "0 15 2 * * *", zone = "Asia/Ho_Chi_Minh")
```

Do not “patch” this by manually adding/subtracting 7 hours in cron across environments. That breaks down with multiple markets or timezone policy changes.

### 7.2. “Yesterday” Depends on Which Timezone?

Given `Instant` `2026-11-15T19:15:00Z`:

| Approach | Resulting previous day |
|---|---|
| `LocalDate.now(ZoneOffset.UTC).minusDays(1)` | `2026-11-14` |
| `LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh")).minusDays(1)` | `2026-11-15` |
| `Instant.parse(...).atZone(ZoneId.of("Asia/Ho_Chi_Minh")).toLocalDate().minusDays(1)` | `2026-11-15` |

The last row is best for testing because it needs no real clock. The top two rows only yield illustrative results if invoked **at that exact assumed instant**.

### 7.3. Accounting Periods Do Not Always Equal `LocalDate`

Some industries use a 17:00 cutoff, trading days starting at 18:00, or overnight retail shifts. In those cases, calling:

```java
instant.atZone(zone).toLocalDate()
```

only yields the **calendar date**, not necessarily the **business date**. You may need a `BusinessCalendar` or `BusinessDateResolver` reflecting business windows, holidays, customer regions, and custom cutoffs.

For instance, if the business day rolls over at 06:00 instead of 00:00, the policy function might be:

```java
static LocalDate businessDateAtSixAm(
        Instant instant, ZoneId zone) {
    ZonedDateTime local = instant.atZone(zone);
    return local.toLocalTime().isBefore(LocalTime.of(6, 0))
            ? local.toLocalDate().minusDays(1)
            : local.toLocalDate();
}
```

This differs from the previous example's “02:15 processes previous day” rule; apply it only when the domain contract specifies an 06:00 cutoff.

---

## 8. `JobParameters`, `JobInstance`, and Duplicate Handling

Timezones decide not only **when** a job runs, but also impact **how each run is identified**.

### 8.1. Identifying Parameters

In Spring Batch, a `JobInstance` is identified by `Job` name and its set of identifying `JobParameters`. For a daily reconciliation job:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("requestedAtUtc",
                "2026-11-15T19:15:00Z", false)
        .toJobParameters();
```

`businessDate` identifies the instance; actual request timestamp serves auditing only.

If code changes to:

```java
.addString("requestedAtUtc",
        Instant.now().toString(), true)
```

every call with a different instant creates a new instance. Duplicate runs on the same day will no longer be caught by a simple `businessDate` key.

### 8.2. When to Add Zone/Region to the Key?

If a single job serves **multiple markets**, `businessDate` `2026-11-15` in Vietnam and New York may refer to two distinct datasets. Then include the market in the identifying key:

```java
new JobParametersBuilder()
        .addString("market", "VN", true)
        .addString("businessDate", "2026-11-15", true)
        .addString("scheduleZone", "Asia/Ho_Chi_Minh", false)
        .toJobParameters();
```

Whether `scheduleZone` is identifying depends on the domain contract. If two regions share one dataset, use a stable business key (like `market`); changing a configured timezone alias should not accidentally create a new instance and reprocess data.

### 8.3. Jobs Running Past the Next Day

The schedule triggers at 02:15 daily, yet day one's job takes 28 hours. The next day, the scheduler will fire again unless blocked. With different identifying `businessDate`s, Spring Batch can create two distinct `JobInstance`s and allow both to run concurrently.

Thus, **per-day uniqueness does not block parallel execution across two different business dates**. If overlapping runs are forbidden, enforce orchestration-level locks, single-worker queues, a Quartz clustered scheduler, or equivalent operational controls.

### 8.4. Restart and Replay

When day 15's job fails and is restarted on day 17, pass `businessDate=2026-11-15` again. Do not recompute `LocalDate.now(zone).minusDays(1)` at restart time, which would jump to day 16 and create a different `JobInstance`.

Good practices:

- For automated runs, resolve business date for **the scheduled period**.
- Persist identifying parameters in run metadata.
- On restart, reuse the failed instance's exact business key.
- On backfill, pass each missing data date explicitly.
- If a `COMPLETED` period must be rerun from scratch, use a clearly defined reprocess workflow rather than arbitrarily changing parameters to bypass duplicate guards.

---

## 9. Scheduled Time, Actual Time, and Business Time

Three timestamps are often conflated:

| Timestamp | Meaning | Where to store |
|---|---|---|
| `scheduledAt` | When the scheduler **planned** to invoke the job | Scheduler trigger/audit mechanism |
| `requestedAt` or `actualTriggerAt` | When the application actually issued the request | Logs/metrics or non-identifying parameter |
| `businessDate` / `businessPeriod` | Data period processed by the job | Identifying `JobParameters` |

For example, the scheduler planned 02:15, but host load delayed the method until 02:17. For a previous-day job, both yield the same business date. However, if a job runs near midnight or gets delayed into the next day, deriving business date from `Instant.now()` at execution time can **shift the period**.

If the system must process **every occurrence** of a schedule (including delayed or backfilled occurrences), use a scheduler that persists planned fire times or a queue of due data periods. Derive `businessDate` from the assigned period, never guessing backward from actual runtime.

Good model for large systems:

```text
Schedule occurrence:
  scheduleId      = dailyImport-VN
  plannedFireAt   = 2026-11-15T19:15:00Z
  zone            = Asia/Ho_Chi_Minh
  businessDate    = 2026-11-15

Request at:
  actualRequestAt = 2026-11-15T19:17:12Z

Batch identity:
  jobName         = dailyImportJob
  identifying     = businessDate=2026-11-15
```

This model supports monitoring trigger lag, identifying data periods, and reconciling missing runs.

---

## 10. Scheduler Downtime, Misfires, and Catch-Up

### 10.1. `@Scheduled` Is Not a Durable Schedule

With in-process Spring `@Scheduled`, when the application stops or restarts, triggers occurring during downtime are normally **not persisted for automatic replay**. If the machine is down from 02:00 to 03:00, the 02:15 schedule can be missed.

Redeploying at 03:00 does not prove yesterday's job ran. Therefore, if “never miss a business period” is required, add:

1. Persist identifiers of periods due for processing, e.g., each `businessDate`.
2. Query history via `JobExplorer`/repository or a business control ledger.
3. Identify periods not yet `COMPLETED`.
4. Submit catch-up jobs with the corresponding identifying parameters.
5. Reconcile outputs for each period.

### 10.2. Handling Missed Executions by Policy

| Policy | Best suited when | Consequences to weigh |
|---|---|---|
| Skip missed triggers | Stale data has no value, e.g., cache polling | A period may go unprocessed |
| Run once upon recovery | Need latest state only | May not cover all missed individual periods |
| Run every missing period | Reconciliation, settlement, reporting, daily ingestion | Needs queuing, stable `businessDate`, and concurrency limits |
| Coalesce missing periods into one job | Workload supports cumulative processing | Must prove equivalence to per-period execution |
| Queue for operator approval | Financial or hard-to-reverse data operations | Requires clear inspection and restart procedures |

Quartz provides richer trigger and misfire handling than basic `@Scheduled`. However, a Quartz trigger's default policy does not automatically become right for every domain; configure and test exact behavior.

### 10.3. Lenient and Fixed Execution in `CronTrigger`

In Spring Framework versions providing these factory methods, `CronTrigger` distinguishes:

- **Lenient execution:** schedules relative to the previous completion, potentially skipping firings when tasks run long.
- **Fixed execution:** schedules relative to planned timestamps, potentially catching up delayed firings.

API example from Spring Framework 6.1.3+:

```java
CronTrigger lenient =
        CronTrigger.forLenientExecution("0 15 2 * * *");

CronTrigger fixed =
        CronTrigger.forFixedExecution("0 15 2 * * *");
```

These two factories illustrate `CronTrigger` policies in supporting versions; when using a custom timezone, configure `TaskScheduler`/clock or trigger for the right zone and check version APIs. They **do not replace** durable schedule persistence across process crashes or multi-node clusters. Do not treat fixed execution as an automatic “exactly one business job per day” guarantee without Spring Batch-level idempotency.

---

## 11. Multi-Instance Applications: Schedules Can Fire Duplicates

Suppose you deploy 3 replicas, each with `@EnableScheduling` and a `@Scheduled` method:

```text
             02:15 in Asia/Ho_Chi_Minh
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
        Replica A    Replica B    Replica C
            │            │            │
            └────────────┼────────────┘
                         ▼
                  JobRepository
```

Every replica may attempt `JobLauncher.run(...)`. `JobRepository` guards creating executions for the same `JobInstance` under proper transactions and isolation levels, but should not be the sole schedule coordinator:

- Replicas still generate redundant launch requests.
- If identifying parameters differ, Spring Batch treats them as separate instances and runs all of them.
- Side effects outside batch transactions (HTTP, files, emails, messages) are not automatically guaranteed exactly-once.
- A node crashing mid-side-effect can cause restarts to repeat partial work.

Appropriate solutions include a leader scheduler, reliable distributed locks, Quartz clustering with a persistent job store, or an external scheduler sending a single request to the batch service. Regardless of choice, jobs still need **business-key idempotency** and recovery mechanisms.

### When Should Concurrent Runs Be Blocked?

Some jobs can process distinct `businessDate`s in parallel, such as independent daily file imports. Others must run strictly sequentially, such as cumulative balance updates depending on the previous period.

Answer separately:

- Block **duplicate runs of the same `businessDate`**?
- Block **two different `businessDate`s from overlapping**?
- Limit how many batches hit one database simultaneously?
- When a job exceeds its schedule interval, should the scheduler queue, skip, or alert?

Timezones define occurrence instants; concurrency controls coordination and data integrity.

---

## 12. Quartz: `CronTrigger` Timezones

When an application needs persistent triggers, clustering, or fine-grained misfire policies, Quartz is often paired with Spring Batch.

Example setting a timezone on a Quartz cron schedule:

```java
import java.util.TimeZone;

import org.quartz.CronScheduleBuilder;

CronScheduleBuilder schedule = CronScheduleBuilder
        .cronSchedule("0 15 2 * * ?")
        .inTimeZone(TimeZone.getTimeZone("Asia/Ho_Chi_Minh"));
```

In Quartz, `?` means “no specific value” for day-of-month/day-of-week. This is Quartz syntax and differs from Spring cron. Never copy an expression between the two libraries without checking.

If the job loads timezone from config:

```java
ZoneId zoneId = ZoneId.of(configuredZone); // validate early
TimeZone quartzZone = TimeZone.getTimeZone(zoneId);

CronScheduleBuilder schedule = CronScheduleBuilder
        .cronSchedule(configuredCron)
        .inTimeZone(quartzZone);
```

The Quartz → Spring Batch bridge must define how **planned fire time**, **trigger identity**, and **`businessDate`** map into `JobParameters`. If recording non-identifying `requestedAt` instead of planned time, ensure backfill procedures do not shift periods. Quartz clustering/persistent stores also require proper database and locking setup; creating `CronScheduleBuilder` alone does not address those.

---

## 13. Timezones in Kubernetes CronJob and External Schedulers

Spring Batch can run each execution as an isolated process/job under Kubernetes CronJob instead of keeping `@Scheduled` inside an app.

Illustrative Kubernetes CronJob with explicit timezone:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-import
spec:
  schedule: "15 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: daily-import
              image: example/daily-import:1.0
```

**Distinctions to note:**

- Kubernetes cron `"15 2 * * *"` normally has **5 fields** (minute, hour, day of month, month, day of week), unlike Spring `@Scheduled`'s 6 fields.
- `timeZone` governs Kubernetes CronJob schedule evaluation on versions supporting that field.
- `concurrencyPolicy: Forbid` controls concurrency **for that specific Kubernetes CronJob**, not replacing data locks or idempotency in Spring Batch.
- Missed schedules follow Kubernetes rules, including `startingDeadlineSeconds` and controller history; verify your cluster's exact semantics.
- Containers must receive the exact **scheduled data date**. Never assume the Pod's current date always matches the expected `businessDate` if Pod startup is delayed.

When orchestrating externally, usually remove or disable internal `@Scheduled` triggers so two schedulers do not fire the same job.

---

## 14. Testing Schedule Timezones Without Waiting Until 02:15

A solid test suite verifies time logic with deterministic inputs, then integration-tests the Spring Batch flow separately as needed.

### 14.1. Testing Next Cron Firing with `CronExpression`

Spring Framework provides `org.springframework.scheduling.support.CronExpression`. You can compute the next occurrence in a specific `ZonedDateTime`.

```java
package com.example.batch.schedule;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.ZoneId;
import java.time.ZonedDateTime;

import org.junit.jupiter.api.Test;
import org.springframework.scheduling.support.CronExpression;

class CronZoneTest {

    @Test
    void nextFireIsTwoFifteenInVietnam() {
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        CronExpression cron =
                CronExpression.parse("0 15 2 * * *");

        ZonedDateTime reference = ZonedDateTime.of(
                2026, 11, 15, 23, 0, 0, 0, zone);

        ZonedDateTime next = cron.next(reference);

        assertEquals(ZonedDateTime.of(
                2026, 11, 16, 2, 15, 0, 0, zone), next);
    }
}
```

`CronExpression.next(...)` uses the supplied temporal object to calculate the next instant. Passing a `ZonedDateTime` in Vietnam time provides the exact timezone context. This is a **cron-expression unit test**; it does not prove how the full scheduler runtime handles missed triggers.

### 14.2. Testing `Instant` → `businessDate` Mapping

```java
package com.example.batch.schedule;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

import org.junit.jupiter.api.Test;

class BusinessDatePolicyTest {

    @Test
    void selectsPreviousDateInBusinessZone() {
        Instant fireAt =
                Instant.parse("2026-11-15T19:15:00Z");
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

        LocalDate businessDate =
                DailyImportScheduler.businessDateFor(fireAt, zone);

        assertEquals(LocalDate.of(2026, 11, 15), businessDate);
    }

    @Test
    void instantMayBelongToDifferentLocalDates() {
        Instant sameInstant =
                Instant.parse("2026-11-15T19:15:00Z");

        assertEquals(LocalDate.of(2026, 11, 16),
                sameInstant.atZone(
                        ZoneId.of("Asia/Ho_Chi_Minh"))
                        .toLocalDate());

        assertEquals(LocalDate.of(2026, 11, 15),
                sameInstant.atZone(ZoneId.of("UTC"))
                        .toLocalDate());
    }
}
```

`DailyImportScheduler.businessDateFor` in section 5 is package-private; this test resides in the same package. Extract this policy into a dedicated bean if multiple jobs share it.

### 14.3. Testing DST Gaps and Overlaps

```java
package com.example.batch.schedule;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.LocalDateTime;
import java.time.ZoneId;

import org.junit.jupiter.api.Test;

class DaylightSavingTest {

    private final ZoneId zone =
            ZoneId.of("America/New_York");

    @Test
    void springForwardHasNoTwoThirtyAm() {
        LocalDateTime local =
                LocalDateTime.of(2026, 3, 8, 2, 30);

        assertEquals(0,
                zone.getRules().getValidOffsets(local).size());
    }

    @Test
    void fallBackHasTwoOneThirtyAmInstants() {
        LocalDateTime local =
                LocalDateTime.of(2026, 11, 1, 1, 30);

        assertEquals(2,
                zone.getRules().getValidOffsets(local).size());
    }
}
```

These tests verify timezone and boundary properties. If using Quartz or a specific `CronTrigger`, add integration tests verifying **actual execution policy** of that scheduler on DST transition days.

### 14.4. Testing with `Clock.fixed`

When services inject `Clock`, replace the real clock with a fixed instant:

```java
Clock fakeClock = Clock.fixed(
        Instant.parse("2026-11-15T19:15:00Z"),
        ZoneOffset.UTC);

Instant requestedAt = fakeClock.instant();

LocalDate businessDate =
        DailyImportScheduler.businessDateFor(
                requestedAt,
                ZoneId.of("Asia/Ho_Chi_Minh"));

assertEquals(LocalDate.of(2026, 11, 15), businessDate);
```

Advantages: tests are independent of CI machine time, require no `Thread.sleep`, and never flake around midnight. You can also mock `JobLauncher` with Mockito and assert `JobParameters` contains the right `businessDate` while `requestedAtUtc` is non-identifying.

### 14.5. Test Scenarios to Cover

| Scenario | What to verify |
|---|---|
| UTC server, Vietnam business time | Occurrence and `businessDate` follow `Asia/Ho_Chi_Minh` |
| Near 00:00 UTC when already next day in Vietnam | Never pulls wrong date from JVM default zone |
| Month/year boundaries | Stepping back with `LocalDate.minusDays(1)` produces exact date |
| DST gap | Policy for nonexistent hour is explicitly handled |
| DST overlap | Duplicate-period guard is enforced |
| Invalid cron config | App fails fast instead of firing at unexpected hours |
| Invalid `ZoneId` config | Invalid config detected at startup |
| Duplicate run on same `businessDate` | Does not create new instance once `COMPLETED`; handles exceptions properly |
| Rerun of `FAILED` instance | Restart reuses the same identifying `businessDate` |
| Scheduler misses a day due to downtime | Backfill detects and processes missing period |
| Job runs into next day | Concurrency policy behaves as designed |
| Multiple business regions | Each region uses appropriate ID, timezone, and calendar |

---

## 15. Designing Observability and Diagnosing Timezone Bugs

In operations, log time fields with explicit semantics:

```text
jobName= dailyImportJob
scheduleZone= Asia/Ho_Chi_Minh
cron= 0 15 2 * * *
businessDate= 2026-11-15
requestedAtUtc= 2026-11-15T19:15:00Z
observedLocal= 2026-11-16T02:15+07:00[Asia/Ho_Chi_Minh]
jobExecutionId= 123456
batchStatus= STARTED
```

If the scheduler supplies planned fire time, also record `plannedFireAtUtc` and measure lag:

```text
scheduleDelay = actualRequestAt - plannedFireAtUtc
```

Never log bare strings like `"02:15:00"` or `"2026-11-16 02:15"` without timezone. They lack the context to pinpoint an instant when debugging multi-region systems or DST transitions.

### Common Mistakes

| Symptom | Common cause | Resolution |
|---|---|---|
| Job shifts by 7 hours when containerized | `@Scheduled` missing `zone`, scheduler default changed | Configure `zone = "Asia/Ho_Chi_Minh"` explicitly |
| Job writes file for the wrong date | Computing `businessDate` via `LocalDate.now()` in default zone | Convert `Instant` to business `ZoneId` before extracting date |
| Job skips a run on a DST day | Local trigger falls inside a DST gap | Define explicit policy and pick a safe hour/trigger |
| Job runs twice during DST change | Local time overlap; scheduler/trigger fires twice | Enforce business keys and idempotency |
| Every deploy creates a new instance for the same day | Identifying timestamp parameter | Keep only stable business keys identifying |
| Job fails to catch up after outage | `@Scheduled` does not persist missed triggers | Add reconciliation/backfill or persistent scheduler |
| Three replicas all launch the job | Each replica runs its own scheduler | Distributed coordination or single scheduler |
| UI displays shifted history timestamps | Parsing DB timestamps without timezone convention | Standardize `Instant`/offset and format in user zone |
| Scheduler and job use different timezones | Trigger uses zone A, `LocalDate.now()` uses zone B | Single configured zone shared by trigger and business policy |
| Job not found on restart | Recomputing `businessDate` at restart time | Persist and pass original identifying parameters |

### Separating Database Time from Business Time

Spring Batch metadata stores timestamps like start/end/update times, with column types and read/write behavior governed by the DB engine, JDBC driver, and framework configuration. Never assume a `LocalDateTime` read from metadata is UTC unless your system explicitly enforces that convention.

When the app stores its own audit events, prefer `Instant` or timestamp-with-offset per data contract. For display, convert to the operator's or market's `ZoneId` while retaining the exact instant for reconciliation.

### Updating tzdb

IANA timezone rules can change by national legislation. For multi-year schedules or markets with shifting DST policies, keep JDK/container tzdb updated. Tzdb changes can alter future trigger instants; re-verify critical schedules after runtime upgrades.

---

## 16. When to Choose `@Scheduled`, Quartz, or an External Scheduler?

| Option | Strengths | Limitations to design around |
|---|---|---|
| Spring `@Scheduled(cron, zone)` | Simple, minimal dependencies, sufficient for small internal jobs | No built-in persistent missed schedules; multiple replicas may fire together |
| Quartz | Triggers, calendars, misfire policies, optional persistent store/cluster | Requires operational setup, DB tables, mapping to `JobParameters` |
| Kubernetes CronJob | Decouples schedule from app process, integrates with Pod/Job lifecycle | Cron syntax differs from Spring; own missed-schedule and concurrency rules |
| Orchestrator like Airflow | Multi-step workflows, history, backfills, dependencies | Larger infrastructure; must align timezone and `businessDate` with Spring Batch |
| Enterprise scheduler | Cross-system orchestration, SLAs, business calendars | Requires strict parameter mapping and end-to-end observability |

Depending on needs, a Spring Batch app can expose launch endpoints via REST API or CLI and delegate all scheduling to an external orchestrator. In that architecture, design jobs to **accept dates/periods via parameters** and rerun safely without depending on the JVM's wall clock.

---

## 17. Practice Exercises

### Exercise 1 — Timezone Conversion

Given `Instant.parse("2026-11-15T19:15:00Z")`, write a program printing:

- Time in UTC.
- Time in `Asia/Ho_Chi_Minh`.
- Calendar date in both zones.
- Business date to process if the policy is “previous day in Vietnam time.”

Explain why calendar dates can differ for the exact same instant.

### Exercise 2 — Job Scheduled in Configured Timezone

Set `app.batch.schedule.cron = "0 15 2 * * *"` and `app.batch.schedule.zone = "Asia/Ho_Chi_Minh"`. Write a bean using `@EnableScheduling` and `@Scheduled` to launch a Spring Batch `Job` accepting `businessDate`. Test with `CronExpression` instead of waiting until 02:15.

### Exercise 3 — Testing with New York

Switch the zone to `America/New_York` and schedule at `02:30`. Use `ZoneRules` to prove `2026-03-08` has no `02:30`. Then define a business policy for what should happen on that day.

### Exercise 4 — Duplicate Runs

Simulate the scheduler invoking the job twice with the same `businessDate` but different `requestedAtUtc` values. Compare outcomes when `requestedAtUtc` is identifying vs. non-identifying. Explain why the latter fits “one instance per day” jobs.

### Exercise 5 — Rerunning an Older Date

Suppose day 15's job failed, and it is restarted on day 17. Design the launch call so it **still processes `businessDate=2026-11-15`**. Never call `LocalDate.now(zone).minusDays(1)` for restart requests.

### Exercise 6 — Missed Occurrence

A `@Scheduled` application is down from 01:55 to 02:40 on 2026-11-16. Design a reconciliation check determining whether business date Nov 15 already has a completed `JobExecution`, and a backfill flow if missing.

### Exercise 7 — Two-Replica Deployment

Deploy the same `@Scheduled` app on two pods. Describe what happens if both call `JobLauncher.run(...)` at 02:15; design a scheduler ownership policy and business-key deduplication.

---

## 18. References

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskScheduler`, `CronTrigger`, `@EnableScheduling`, and `@Scheduled`.
- [Spring Framework — Javadoc @Scheduled (6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html): 6-field cron syntax, `zone` attribute, and disabling cron via `"-"`.
- [Spring Framework — CronExpression](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/support/CronExpression.html): parsing and computing next occurrences with `ZonedDateTime`.
- [Spring Framework — CronTrigger](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/support/CronTrigger.html): cron triggers, lenient/fixed execution, and scheduler clock.
- [Spring Batch — Domain Language of Batch](https://docs.spring.io/spring-batch/reference/domain.html): relationships among `Job`, `JobInstance`, `JobExecution`, and `JobParameters`.
- [Spring Batch — Configuring a JobLauncher](https://docs.spring.io/spring-batch/reference/job/configuring-launcher.html): launching jobs.
- [Spring Batch — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): metadata, instances, and repository transactions.
- [Java SE — ZoneId](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html): zone identifiers and timezone rules.
- [Java SE — ZoneRules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html): gaps/overlaps and valid offsets.
- [Kubernetes — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/): `schedule`, `timeZone`, concurrency, and missed schedules.

A schedule's timezone is the **rule deciding when a job is requested to run**; the data date/period processed is the **business identifier** that must be explicitly computed and stored. A resilient design combines `ZoneId`, `Instant`, `Clock`, `@Scheduled(zone)` or equivalent schedulers with stable `JobParameters`, duplicate guards, and backfill workflows. That way, deploying to UTC hosts, switching business regions, restarting jobs, or crossing DST boundaries will never silently process the wrong data period.
