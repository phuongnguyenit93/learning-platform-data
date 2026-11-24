# Avoiding Real-Time Dependencies in Spring Batch Tests

## 1. Why shouldn't batch data tests use the current clock?

Spring Batch jobs frequently process data by business date, retention window, expiration timestamp, sync window, file arrival time, or recurring schedule. When tests read time directly from the OS using `Instant.now()`, `LocalDate.now()`, or `System.currentTimeMillis()`, results can change simply because of **when the test executes**.

For example, a batch keeps only orders created within the last 24 hours. A test creates an order "23 hours 59 minutes ago" relative to `Instant.now()`, then runs the batch. If the CI runner is slow or context startup takes long, the item can cross the cutoff. With identical code, the test can pass today, fail tomorrow, or flake near midnight.

A reliable time-sensitive test must answer three questions:

1. **What is the reference time?** For example, "today in Hanoi" or `2025-05-12T00:00:00Z`.
2. **Who supplies that time?** Job configuration, business parameters, or a replaceable `Clock`.
3. **What are the boundary conditions?** Are before-cutoff, exact-cutoff, and after-cutoff handled differently?

The goal is for tests to produce identical results on a laptop, CI, servers in other time zones, around midnight, or when re-run months later.

### Easily confused time concepts

| Time concept | Example | Recommended source | How to test |
|---|---|---|---|
| **Event time** | When an order was created | `createdAt` field in input data | Use a fixed `Instant` right in the fixture |
| **Processing time** | When the batch is running | Injected `Clock` | Use `Clock.fixed(...)` |
| **Business date** | Which business day the batch processes | `JobParameters`, usually an ISO date string | Pass a fixed date like `2025-05-12` |
| **Batch metadata time** | When `JobExecution` started/ended | Spring Batch / `JobRepository` | Verify status, ordering, and validity; avoid exact millisecond equality |
| **Database time** | SQL `CURRENT_TIMESTAMP` value | Database clock | Control in persistence layer or use test DB with fixed data |
| **Scheduler time** | When cron triggers the job | Scheduling system | Test parameter-selection logic separately without waiting on real cron |

**Rule:** Test data must use explicit timestamps, while business code must obtain "now" through a controllable dependency.

## 2. Creating a replaceable time source with `java.time.Clock`

Java provides `Clock` in the standard library. We can use the system clock in production and an immutable clock in tests.

### 2.1. Time configuration for production

```java
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BatchTimeConfiguration {

    @Bean
    Clock batchClock() {
        return Clock.systemUTC();
    }
}
```

`Clock.systemUTC()` uses UTC for instants. If business logic computes calendar dates in a local time zone, also inject the business `ZoneId` instead of relying on the host machine's default time zone.

```java
import java.time.ZoneId;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BusinessZoneConfiguration {

    @Bean
    ZoneId businessZone() {
        return ZoneId.of("Asia/Ho_Chi_Minh");
    }
}
```

In business code:

```java
Instant now = clock.instant();
LocalDate businessToday = LocalDate.now(clock.withZone(businessZone));
```

`Instant` represents a point on the UTC timeline. `LocalDate` represents a calendar date; the same `Instant` can fall on two different dates in two different `ZoneId`s.

### 2.2. Setting a fixed clock in tests

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
        Instant.parse("2025-05-12T00:00:00Z"),
        ZoneOffset.UTC
);
```

Every call to `fixedClock.instant()` returns this exact instant, whether the test runs at 9 AM, past midnight, or next year. No `Thread.sleep(...)` is needed to let time pass.

When a Spring Boot test context already defines a production `Clock` bean, override it with a prioritized test bean:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration
public class FixedClockTestConfiguration {

    @Bean
    @Primary
    Clock fixedBatchClock() {
        return Clock.fixed(
                Instant.parse("2025-05-12T00:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
```

Load this configuration into `@SpringBootTest` via `@Import(FixedClockTestConfiguration.class)` or `classes`. `@Primary` selects the test bean when multiple beans of the same type exist. Ensure every component needing time control **actually receives `Clock` via dependency injection**; overriding the bean has no effect on code calling `Instant.now()` directly.

## 3. Practical example: filtering expired records in a processor

Suppose a batch retains events recorded within 48 hours and drops events **older than** the threshold. Processing at fixed time `2025-05-12T00:00:00Z` sets the cutoff at `2025-05-10T00:00:00Z`.

### 3.1. Testable processor

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

import org.springframework.batch.item.ItemProcessor;

record BatchEvent(String id, Instant occurredAt) {}

public final class RecentEventFilter
        implements ItemProcessor<BatchEvent, BatchEvent> {

    private final Clock clock;
    private final Duration retention;

    public RecentEventFilter(Clock clock, Duration retention) {
        this.clock = Objects.requireNonNull(clock);
        this.retention = Objects.requireNonNull(retention);
        if (retention.isNegative()) {
            throw new IllegalArgumentException("retention must not be negative");
        }
    }

    @Override
    public BatchEvent process(BatchEvent item) {
        Instant cutoff = clock.instant().minus(retention);

        // Only drop events older than cutoff; events exactly at cutoff are kept.
        return item.occurredAt().isBefore(cutoff) ? null : item;
    }
}
```

In Spring Batch, `ItemProcessor.process(...)` returning `null` **filters** the item rather than **skipping via exception**. Therefore, tests should inspect `filterCount` rather than `processSkipCount` for this case.

### 3.2. Unit test without real time

```java
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class RecentEventFilterTest {

    private RecentEventFilter processor;

    @BeforeEach
    void setUp() {
        Clock clock = Clock.fixed(
                Instant.parse("2025-05-12T00:00:00Z"),
                ZoneOffset.UTC
        );

        processor = new RecentEventFilter(clock, Duration.ofHours(48));
    }

    @Test
    void shouldFilterEventOlderThan48Hours() throws Exception {
        BatchEvent oldEvent = new BatchEvent(
                "old",
                Instant.parse("2025-05-09T23:59:59Z")
        );

        assertNull(processor.process(oldEvent));
    }

    @Test
    void shouldKeepEventExactlyAtCutoff() throws Exception {
        BatchEvent boundaryEvent = new BatchEvent(
                "boundary",
                Instant.parse("2025-05-10T00:00:00Z")
        );

        assertSame(boundaryEvent, processor.process(boundaryEvent));
    }

    @Test
    void shouldKeepRecentEvent() throws Exception {
        BatchEvent recentEvent = new BatchEvent(
                "recent",
                Instant.parse("2025-05-11T12:00:00Z")
        );

        assertSame(recentEvent, processor.process(recentEvent));
    }
}
```

These cases test the boundary condition **`isBefore` is strictly less than**. Items exactly at the threshold are kept; if business rules require dropping items at the threshold, adjust the predicate and update the corresponding test. All fixture timestamps are meaningful business constants, never computed with `Instant.now().minus(...)`.

### 3.3. A common design mistake

**Depending on real time:**

```java
public BatchEvent process(BatchEvent item) {
    Instant cutoff = Instant.now().minus(Duration.ofHours(48));
    return item.occurredAt().isBefore(cutoff) ? null : item;
}
```

This makes unit tests hard to reproduce against an exact boundary. Even if a test computes "current" time before calling the processor, the clock keeps ticking between operations.

**Controllable in tests:**

```java
public BatchEvent process(BatchEvent item) {
    Instant cutoff = clock.instant().minus(Duration.ofHours(48));
    return item.occurredAt().isBefore(cutoff) ? null : item;
}
```

If a batch runs for a long time and every item must use the **exact same threshold**, it is even better to compute `cutoff` once at the start of execution and pass an immutable `Instant` to the processor. Injecting `Clock` solves testability, yet re-calling `clock.instant()` per item in production can still shift the cutoff while a long job runs.

## 4. Testing a real step with fixed-time test data

Unit tests suffice to verify `RecentEventFilter` logic. Integration tests confirm the processor is wired into the step and Spring Batch updates counters accurately.

The example below uses **Spring Boot 3.x, Spring Batch 5.x, Java 17, JUnit 5**. Test dependencies require `spring-batch-test`, `spring-boot-starter-test`, and H2; the application also needs `spring-boot-starter-batch`. The test defines its own job and clock, launching the step once via `JobLauncherTestUtils`.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.support.ListItemReader;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBatchTest
@SpringBootTest(
        classes = FixedTimeBatchIntegrationTest.TestApplication.class,
        properties = {
                "spring.batch.job.enabled=false",
                "spring.batch.jdbc.initialize-schema=always"
        }
)
class FixedTimeBatchIntegrationTest {

    @Autowired
    private JobLauncherTestUtils testUtils;

    @Test
    void stepShouldFilterOldDataAgainstFixedTime() throws Exception {
        JobExecution jobExecution =
                testUtils.launchStep("filterEventsStep");

        StepExecution stepExecution = jobExecution
                .getStepExecutions()
                .iterator()
                .next();

        assertEquals(BatchStatus.COMPLETED, stepExecution.getStatus());
        assertEquals(3L, stepExecution.getReadCount());
        assertEquals(1L, stepExecution.getFilterCount());
        assertEquals(2L, stepExecution.getWriteCount());
        assertEquals(0L, stepExecution.getProcessSkipCount());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean
        Clock clock() {
            return Clock.fixed(
                    Instant.parse("2025-05-12T00:00:00Z"),
                    ZoneOffset.UTC
            );
        }

        @Bean
        @StepScope
        ListItemReader<BatchEvent> eventReader() {
            // Step-scoped: each execution receives a fresh reader.
            return new ListItemReader<>(List.of(
                    new BatchEvent("old",
                            Instant.parse("2025-05-09T23:59:59Z")),
                    new BatchEvent("boundary",
                            Instant.parse("2025-05-10T00:00:00Z")),
                    new BatchEvent("recent",
                            Instant.parse("2025-05-11T12:00:00Z"))
            ));
        }

        @Bean
        ItemProcessor<BatchEvent, BatchEvent> eventProcessor(Clock clock) {
            return new RecentEventFilter(clock, Duration.ofHours(48));
        }

        @Bean
        Step filterEventsStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                ItemReader<BatchEvent> eventReader,
                ItemProcessor<BatchEvent, BatchEvent> eventProcessor) {

            return new StepBuilder("filterEventsStep", repository)
                    .<BatchEvent, BatchEvent>chunk(2, transactionManager)
                    .reader(eventReader)
                    .processor(eventProcessor)
                    .writer(chunk -> { /* Test writer discards data */ })
                    .build();
        }

        @Bean
        Job filterEventsJob(JobRepository repository, Step filterEventsStep) {
            return new JobBuilder("filterEventsJob", repository)
                    .start(filterEventsStep)
                    .build();
        }
    }
}
```

This test verifies item counts across stages, not transaction commits to a business table because the writer is a no-op. When testing real output, swap in a test-persisting writer and assert `boundary` and `recent` are present while `old` is absent. Use a transaction-supporting database when testing rollbacks/commits.

`@StepScope` on the reader avoids carrying over stale read offsets when a context is reused across executions. However, giving each run a fresh reader does not cure fixtures built with `Instant.now()`: **all timestamps inside fixtures must still be fixed**.

Version note: Spring Batch 5 uses `new StepBuilder(name, jobRepository)` and `.chunk(size, transactionManager)`. With Spring Batch 6 or custom Batch setups, adjust imports/bootstrap to match your actual version.

## 5. Business dates should be stable `JobParameters`

For daily batches, the key question is usually not "what time is it now?" but **"which business date is the job processing?"**.

Suppose a job runs at 01:00 on May 13 to summarize transactions for May 12. If the reader calls `LocalDate.now()`, re-running the job on May 14 silently shifts the dataset. Instead, create an identifying parameter:

```java
import java.time.LocalDate;

import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

LocalDate businessDate = LocalDate.of(2025, 5, 12);

JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", businessDate.toString(), true)
        .toJobParameters();
```

With `JobLauncher`, pass `parameters` at launch time. With `JobLauncherTestUtils`, use `launchJob(parameters)` or `launchStep("stepName", parameters)`.

`.addString(..., true)` marks `businessDate` as an **identifying parameter**, contributing to `JobInstance` identity. When restarting an incomplete job instance, keep the business date unchanged. If a job already `COMPLETED`, re-running with the same identifying parameters is normally rejected by Spring Batch; that is job lifecycle control, not a reason to swap the date for the real clock in tests.

### 5.1. Reading the date into a step-scoped bean

```java
import java.time.LocalDate;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
public ListItemReader<BatchEvent> datedEventReader(
        @Value("#{jobParameters['businessDate']}")
        String businessDateText) {

    LocalDate businessDate = LocalDate.parse(businessDateText);

    // Return sample data or queried data for the exact businessDate.
    return new ListItemReader<>(
            fixtureEventsFor(businessDate)
    );
}
```

`fixtureEventsFor(...)` here is an illustrative helper returning events by date to clarify parameter passing. In real application tests, replace it with the corresponding reader/query/fixture. If the parameter is missing or malformed ISO-8601 (`yyyy-MM-dd`), fail parsing explicitly or validate at job startup.

### 5.2. Computing date ranges in an explicit time zone

To read all transactions for `2025-05-12` in Vietnam time, avoid using a bare `LocalDateTime` and comparing it to UTC timestamps. Construct a half-open interval `[startInclusive, endExclusive)`:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

LocalDate day = LocalDate.parse("2025-05-12");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant startInclusive = day.atStartOfDay(zone).toInstant();
Instant endExclusive = day.plusDays(1)
        .atStartOfDay(zone)
        .toInstant();
```

In SQL queries, apply the condition:

```sql
WHERE created_at >= :startInclusive
  AND created_at < :endExclusive
```

A half-open interval prevents double-counting events occurring exactly at 00:00 the next day and avoids `23:59:59.999` hacks sensitive to database column precision. In DST-observing zones, a calendar day can span 23 or 25 hours, so never blindly add `Duration.ofHours(24)` to find the next day's start.

## 6. Testing time boundaries, time zones, and DST

A time-focused test suite should cover real boundary cases rather than just an "ordinary" day.

| Case | Input data | Expectation to verify |
|---|---|---|
| Before cutoff | `2025-05-09T23:59:59Z` | Dropped when cutoff is `2025-05-10T00:00:00Z` |
| Exact cutoff | `2025-05-10T00:00:00Z` | Retained under `isBefore` |
| After cutoff | `2025-05-10T00:00:01Z` | Retained |
| Date rollover in business zone | An `Instant` corresponding to 00:30 in Vietnam | Business date is the new day, even if UTC is still the previous day |
| DST transition day | `2025-03-30` in `Europe/Paris` | Day interval spans 23 hours |
| Month-end, year-end | Dec 31 → Jan 1; leap year Feb 29 | Date ranges and partition names match |
| Job restarted days later | `businessDate` unchanged | Still reads the original date, never switches to "today" |

Example testing a DST shift without waiting on real time:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

import org.junit.jupiter.api.Test;

class DayBoundaryTest {

    @Test
    void daylightSavingDayCanBe23Hours() {
        ZoneId zone = ZoneId.of("Europe/Paris");
        LocalDate day = LocalDate.of(2025, 3, 30);

        Instant start = day.atStartOfDay(zone).toInstant();
        Instant end = day.plusDays(1)
                .atStartOfDay(zone)
                .toInstant();

        assertEquals(Duration.ofHours(23), Duration.between(start, end));
    }
}
```

If an application only serves Vietnam, `Asia/Ho_Chi_Minh` does not observe DST; however, local-date code may be reused for other markets, so computing via `ZoneId` and `LocalDate` remains cleaner than hardcoding "one day = 24 hours".

### Store in UTC, interpret in the business time zone

A sound practice is persisting instants as UTC `Instant` / timestamps while computing display dates and date intervals in the business `ZoneId`. Avoid relying on `TimeZone.getDefault()` or letting CI runners have a different `TZ` from developer machines. Mutating the global timezone inside tests also interferes with parallel tests; inject `ZoneId` as a dependency instead.

## 7. Do not use `Thread.sleep` to test schedulers or wait for expiration

Suppose a summary job is triggered by `@Scheduled(cron = "0 0 1 * * *", zone = "Asia/Ho_Chi_Minh")`. A test calling `Thread.sleep(...)` until 01:00 is unsuitable: slow, prone to hanging CI, and fails to directly verify date-selection rules.

Instead, keep the scheduler as a thin trigger layer and extract business-date selection into a service accepting `Clock` and `ZoneId`.

```java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

public final class DailyBatchDatePolicy {

    private final Clock clock;
    private final ZoneId businessZone;

    public DailyBatchDatePolicy(Clock clock, ZoneId businessZone) {
        this.clock = clock;
        this.businessZone = businessZone;
    }

    public LocalDate targetDate() {
        // Job runs early in the day to process the previous day's data.
        return LocalDate.now(clock.withZone(businessZone)).minusDays(1);
    }
}
```

Unit test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class DailyBatchDatePolicyTest {

    @Test
    void shouldChoosePreviousBusinessDate() {
        Clock clock = Clock.fixed(
                // 18:00 UTC on 2025-05-12 = 01:00 on 2025-05-13 in Vietnam.
                Instant.parse("2025-05-12T18:00:00Z"),
                ZoneOffset.UTC
        );

        DailyBatchDatePolicy policy = new DailyBatchDatePolicy(
                clock,
                ZoneId.of("Asia/Ho_Chi_Minh")
        );

        assertEquals(LocalDate.of(2025, 5, 12), policy.targetDate());
    }
}
```

In production, the `@Scheduled` method simply calls `batchLauncher.launch(policy.targetDate())`. The unit test verifies date calculation, while a separate integration test can verify the adapter passes the expected parameter to the launcher. **`Clock.fixed` does not control `@Scheduled` firing**: the scheduling framework maintains its own clock and scheduler.

Likewise, if a job configures retry, backoff, or timeouts, test retry conditions and outcomes via the appropriate configuration/policy. Never assert that a stage finishes in an exact number of milliseconds on CI. For asynchronous runs, tests may await a **completion condition** with a reasonable timeout; that is distinct from using real time as **business-deciding input data**.

## 8. Time windows, restarts, and consistent data across an execution

A subtle bug arises when a batch starts at 23:59:59 and reads past 00:00:01:

```text
23:59:59 — first item filtered with "today" as day 12
00:00:00 — calendar date rolls over
00:00:01 — next item filtered with "today" as day 13
```

If items within the same execution use two different windows, outputs become inconsistent and restarts can produce different results. Two standard solutions exist:

**Approach A — Use a fixed `businessDate` determined at launch.** Readers and processors obtain the date from `JobParameters` and compute `startInclusive` / `endExclusive` once. This is usually the cleanest option for daily batches.

**Approach B — Snapshot an `Instant` or `cutoff` at step start.** Use `StepExecutionListener.beforeStep(...)` to store an ISO string in `StepExecution.getExecutionContext()`, and have components read that same value. Example:

```java
import java.time.Clock;
import java.time.Duration;

import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public final class CutoffInitializer implements StepExecutionListener {

    private final Clock clock;

    public CutoffInitializer(Clock clock) {
        this.clock = clock;
    }

    @Override
    public void beforeStep(StepExecution stepExecution) {
        String cutoff = clock.instant()
                .minus(Duration.ofHours(48))
                .toString();

        stepExecution.getExecutionContext()
                .putString("event.cutoff", cutoff);
    }
}
```

When using `ExecutionContext`, consider when metadata is persisted and restart rules. If the window must stay identical **across all restarts of the same job instance**, placing the date/cutoff in identifying `JobParameters` upfront preserves semantics more reliably than recomputing from the clock in `beforeStep`.

In a `CutoffInitializer` unit test, build a `StepExecution` via `MetaDataInstanceFactory.createStepExecution()`, inject `Clock.fixed(...)`, call `beforeStep`, and assert the exact cutoff string. In an integration test, register `.listener(...)` and run the step to verify wiring and reading from execution context.

## 9. When time comes from outside Java code

Injecting `Clock` controls Java code that explicitly uses that clock. It **does not freeze all clocks across the system**.

### 9.1. SQL `NOW()` or `CURRENT_TIMESTAMP`

For instance, this query:

```sql
SELECT *
FROM orders
WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '2 days'
```

still depends on the database clock; Java's `Clock.fixed` has no effect on `CURRENT_TIMESTAMP`. Whenever possible, compute the cutoff in Java and bind it as a query parameter:

```sql
SELECT *
FROM orders
WHERE created_at >= :cutoffInstant
```

Tests supply a fixed `:cutoffInstant` and seed rows with explicit timestamps. `INTERVAL` syntax varies across DBMS vendors, whereas passing a time parameter is database-independent.

If business logic must rely on database time, isolate that logic in the repository and test against an appropriate database with controlled data/transactions. Never assume the DB follows the JVM's fixed clock.

### 9.2. Timestamps generated by Spring Batch

`JobExecution`, `StepExecution`, and `JobRepository` metadata contain system-generated timestamps. Tests should normally verify valid job/step statuses, lifecycle metadata presence, and accurate counters. Avoid asserting that metadata timestamps equal `clock.instant()` from a business bean or differ by "under 1 ms".

### 9.3. External services, files, and messages

If an API returns `expiresAt` or a file carries timestamps, fixtures/mocks must return fixed values. If an external system decides expiration using its own clock, mock the check in unit tests and add contract-level integration tests; never try to make a Java clock represent every external system.

With Kafka/event streams, distinguish the record's **event time** from the **processing time** when the batch receives it. Fixtures should specify both clearly when logic depends on both timestamps.

## 10. Anti-patterns that make tests flaky

| Anti-pattern | Problem | Replacement |
|---|---|---|
| `LocalDate.now()` in test-data builders | Date shifts depending on when tests run | Hardcode `LocalDate.of(2025, 5, 12)` |
| `new Date()` in test compared to `new Date()` in code | Two calls capture two different instants | Inject `Clock.fixed` and assert one fixed instant |
| `Thread.sleep(1000)` to wait for item expiration | Slow, sensitive to CI load | Use two fixed clocks in two separate tests |
| `Thread.sleep(...)` to wait for job completion | Gives no guarantee work finished | Synchronous launcher or bounded wait on completion condition |
| `ZoneId.systemDefault()` for business dates | Depends on host machine timezone | Inject an explicitly configured `ZoneId` |
| `LocalDateTime` for UTC instants | Lacks offset/zone context | Use `Instant` or `OffsetDateTime` per semantics |
| `23:59:59.999` as end of day | Can miss higher-precision timestamps | Half-open range `[start, nextDayStart)` |
| Re-running a `COMPLETED` batch test with identical `JobParameters` | JobRepository rejects re-running the JobInstance | Isolate metadata or use a dedicated test run ID parameter |
| Recomputing cutoff with `now()` per item | Window drifts during long jobs | Snapshot cutoff once or pass `businessDate` |
| Asserting runtime equals a fixed number of ms | CPU/CI/scheduling jitter | Assert business data and execution status |

### Avoiding real-time dependencies in filenames and partitions

If a batch generates `orders-YYYYMMDD.csv` or writes to dated partitions, derive the filename date from the pre-determined `businessDate`. Tests should assert `orders-20250512.csv` inside an isolated test path. Avoid filenames derived from `LocalDate.now()`, as tests can flip outputs past midnight and next-day restarts would target the wrong partition.

### Distinguishing "fixed data" from "a completely deterministic environment"

A test using `Clock.fixed` can still flake due to data read ordering, parallel tests, transaction isolation, random IDs, or race conditions. A fixed clock eliminates **one major source of non-determinism**, while other sources still need explicit control by design.

## 11. Exercise: testing an overdue-data archival job

Suppose a job archives invoices whose `createdAt` is **before the start of 2025-05-12 in Vietnam time**, keeping invoices created at exactly 00:00 on 2025-05-12 in the active table.

Practice requirements:

1. Define `businessDate=2025-05-12` from `JobParameters` and `ZoneId.of("Asia/Ho_Chi_Minh")`; compute `cutoffInstant` from the start of that business day.
2. Build test data with invoices 1 nanosecond before cutoff, exactly at cutoff, and 1 nanosecond after cutoff.
3. Unit test the classifier/processor with a fixed cutoff, without `Instant.now()`.
4. Integration test running the step via `JobLauncherTestUtils`, verifying only older records are archived and `StepExecution` counters match the design.
5. Re-run with the same business date in a separate test execution; confirm no date parameters need updating to "today" for the test to pass.
6. Also test `2025-03-30` in `Europe/Paris` to verify code uses the next day's start instead of adding a hardcoded 24 hours.

**Check question:** If a job starts at 23:59 and finishes at 00:05, should the archived invoice set shift mid-run? For a business-date archival batch, the expected answer is **no**: the cutoff should be anchored to the job's business date.

## 12. References

- [Java SE `Clock` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): `systemUTC`, `fixed`, `offset`, and clock options.
- [Java SE `LocalDate` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): calendar date operations and `atStartOfDay(ZoneId)`.
- [Spring Batch Reference — Job Parameters](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `JobExecution`, and identifying job parameters.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils`, `StepScopeTestUtils`.
- [Spring Batch Reference — Item Processing](https://docs.spring.io/spring-batch/reference/processor.html): `ItemProcessor` returning `null` to filter items.
