# Clock and Time Testing in Spring Batch

## 1. Why Is Time Part of Test Infrastructure?

In Spring Batch applications, many processing rules depend on when a job runs:

- A job only selects orders with `dueAt` before a cutoff time.
- A job aggregates transactions for a **business date** in the company's timezone.
- An item is considered expired once it passes `expiresAt`.
- A job pulls data from "the last 24 hours" or processes records within a time window.
- Records are stamped with `createdAt`, `processedAt`, or `exportedAt` when the writer persists them.
- Retries, restarts, nightly run windows, and end-of-day cutoff rules introduce additional edge cases.

If logic calls `Instant.now()`, `LocalDate.now()`, `new Date()`, or `System.currentTimeMillis()` directly, test outputs can change based on the calendar date, the CI runner's timezone, and execution speed. A test running right around 23:59:59 or 00:00:00 can easily yield different results with unchanged code.

Java's **Clock** is a time abstraction from the `java.time` package. Instead of every component asking the system clock "what time is it now?", we inject a known `Clock` into the processing logic. In production, the clock reads real time; in tests, it returns a frozen or deliberately shifted point in time.

The goal of this lesson is to design **deterministic time-testing infrastructure** for Spring Batch while clearly understanding what an application-injected `Clock` **does not control**.

## 2. Time Types to Distinguish

The Java Time API provides several distinct types. Picking the wrong type is a frequent source of test bugs.

| Type | Meaning | Typical Usage |
| --- | --- | --- |
| `Instant` | An absolute point on the UTC timeline | Audit events, deadlines, timestamps exchanged across systems |
| `LocalDate` | A calendar date without time of day or timezone | Business date, reporting period, daily partitions |
| `LocalDateTime` | Calendar date and time **without timezone/offset** | Internal UI or local schedule data when the zone is known elsewhere |
| `OffsetDateTime` | Date and time with a UTC offset | APIs and records needing to preserve the point's offset |
| `ZonedDateTime` | Date and time with a `ZoneId` and DST rules | Business hours, local run schedules |
| `ZoneId` | Timezone with historical rules and DST | `Asia/Ho_Chi_Minh`, `Europe/Berlin` |
| `Duration` | Elapsed time in seconds/nanoseconds | Timeouts, delays, "after 30 minutes" |
| `Period` | Calendar distance in days/months/years | "After one month", monthly reporting cycles |
| `Clock` | Source of the current instant and default zone when using `now(clock)` APIs | Dependency in processors, services, and test fixtures |

These two lines mean different things:

```java
Instant currentInstant = clock.instant();
LocalDate businessDate = LocalDate.now(clock);
```

`clock.instant()` gives **a point in time**, whereas `LocalDate.now(clock)` derives **the calendar date in the Clock's zone**. The same `Instant` can fall on two different dates in UTC versus Vietnam.

Example:

```java
Instant instant = Instant.parse("2026-03-31T17:00:00Z");

LocalDate utcDay = instant.atZone(ZoneOffset.UTC).toLocalDate();
LocalDate vietnamDay = instant
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toLocalDate();

// utcDay:     2026-03-31
// vietnamDay: 2026-04-01
```

When testing a revenue aggregation job for April 1st in Vietnam time, calling `LocalDate.now(Clock.systemUTC())` will not yield the same business date at that instant.

## 3. Three Essential Clocks for Testing

### 3.1. `Clock.systemUTC()` and `Clock.system(zone)`

These clocks track real time and are typically used in production:

```java
Clock utcClock = Clock.systemUTC();
Clock vietnamClock = Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));

Instant a = utcClock.instant();
Instant b = vietnamClock.instant(); // Same real-time timeline
```

The zone only affects local date/time formatting; it does not make UTC time move faster or slower.

Avoid `Clock.systemDefaultZone()` for critical business rules unless the host machine's timezone is genuinely part of the contract. Developer laptops, containers, CI runners, and deployment servers often have different defaults.

### 3.2. `Clock.fixed()`: Freezing a Point in Time

```java
Instant frozenAt = Instant.parse("2026-05-01T10:00:00Z");
Clock fixedClock = Clock.fixed(frozenAt, ZoneOffset.UTC);

System.out.println(fixedClock.instant()); // Always 2026-05-01T10:00:00Z
System.out.println(fixedClock.instant()); // Still identical
```

This is the most common choice for unit tests. Whether the test runs in milliseconds or minutes, the logic always observes the exact same instant.

### 3.3. `Clock.offset()`: Testing Before and After a Deadline

```java
Clock baseline = Clock.fixed(
        Instant.parse("2026-05-01T10:00:00Z"),
        ZoneOffset.UTC
);

Clock afterThirtyMinutes =
        Clock.offset(baseline, Duration.ofMinutes(30));

assertEquals(
        Instant.parse("2026-05-01T10:30:00Z"),
        afterThirtyMinutes.instant()
);
```

`Clock.offset(...)` creates a new clock shifted relative to a base clock. If the base is `fixed`, the derived clock does not tick either; it is great for setting up before- and after-deadline test cases.

`Clock.tick(...)` truncates time to a specified granularity, such as whole seconds or whole minutes. It is **not a time controller** and does not advance time forward on test command. Use it only when the application genuinely requires lower timestamp precision.

## 4. Making `Clock` an Application Dependency

### 4.1. Registering a Bean for Production

```java
import java.time.Clock;
import java.time.ZoneId;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {

    @Bean
    Clock businessClock() {
        return Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
    }
}
```

Applications can read the timezone ID from configuration to suit different regions, e.g., `app.business-zone=Asia/Ho_Chi_Minh`. What matters is that **the zone is explicitly declared** and used consistently.

Components accept it via constructor injection:

```java
import java.time.Clock;
import java.time.LocalDate;
import org.springframework.stereotype.Service;

@Service
public class BusinessDateService {
    private final Clock clock;

    public BusinessDateService(Clock clock) {
        this.clock = clock;
    }

    public LocalDate today() {
        return LocalDate.now(clock);
    }
}
```

Because `Clock` is a dependency, tests can substitute `Clock.fixed(...)` without modifying business logic. This structure also ensures all components derive business dates from the same time source.

### 4.2. Avoiding Scattered Direct Time Calls

Avoid:

```java
public boolean isExpired(Invoice invoice) {
    return invoice.expiresAt().isBefore(Instant.now());
}
```

Prefer:

```java
public boolean isExpired(Invoice invoice) {
    return invoice.expiresAt().isBefore(clock.instant());
}
```

The only change is the time source, yet this change lets tests verify all three boundaries accurately: **before deadline, at deadline, and after deadline**.

Do not instantiate `Clock.systemUTC()` inside every method call: doing so still couples logic to wall-clock time. Also do not store `Instant.now()` in a `static final` field to simulate "today," because that value freezes at class-load time and can leak state across tests.

## 5. Example: Time-Based Unit Test for `ItemProcessor`

Suppose a batch step processes due invoices. Business rule: **invoices with `dueAt <= now` are selected**, while invoices not yet due are filtered out of the stream.

Model:

```java
import java.time.Instant;

public record Invoice(String id, Instant dueAt) {}
```

Processor:

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;
import org.springframework.batch.item.ItemProcessor;

public final class DueInvoiceProcessor
        implements ItemProcessor<Invoice, Invoice> {

    private final Clock clock;

    public DueInvoiceProcessor(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    @Override
    public Invoice process(Invoice invoice) {
        Instant now = clock.instant();
        return invoice.dueAt().isAfter(now) ? null : invoice;
    }
}
```

In Spring Batch, an `ItemProcessor` returning `null` means **filter the item**. This is not an exception and does not increment the skip count. If a reader returns 3 invoices, 1 is not yet due, and everything else succeeds, you normally expect `readCount=3`, `filterCount=1`, `writeCount=2`.

JUnit 5 test without starting a Spring context:

```java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class DueInvoiceProcessorTest {

    private final Clock clock = Clock.fixed(
            Instant.parse("2026-05-01T10:00:00Z"),
            ZoneOffset.UTC
    );

    private final DueInvoiceProcessor processor =
            new DueInvoiceProcessor(clock);

    @Test
    void processesInvoiceBeforeDeadline() throws Exception {
        Invoice invoice = new Invoice(
                "INV-1",
                Instant.parse("2026-05-01T09:59:59Z")
        );

        assertNotNull(processor.process(invoice));
    }

    @Test
    void processesInvoiceExactlyAtDeadline() throws Exception {
        Invoice invoice = new Invoice(
                "INV-2",
                Instant.parse("2026-05-01T10:00:00Z")
        );

        assertNotNull(processor.process(invoice));
    }

    @Test
    void filtersInvoiceAfterDeadline() throws Exception {
        Invoice invoice = new Invoice(
                "INV-3",
                Instant.parse("2026-05-01T10:00:01Z")
        );

        assertNull(processor.process(invoice));
    }
}
```

These three tests directly confirm the comparison operator semantics: the deadline is **inclusive** of `now`. If the business rule were "strictly before the deadline" (`dueAt < now`), the boundary expectation would flip.

### Testing Time Progression Without Waiting

```java
@Test
void invoiceBecomesDueAfterThirtyMinutes() throws Exception {
    Clock startClock = Clock.fixed(
            Instant.parse("2026-05-01T10:00:00Z"),
            ZoneOffset.UTC
    );
    Invoice invoice = new Invoice(
            "INV-LATER",
            Instant.parse("2026-05-01T10:30:00Z")
    );

    assertNull(new DueInvoiceProcessor(startClock).process(invoice));

    Clock later = Clock.offset(startClock, Duration.ofMinutes(30));
    assertNotNull(new DueInvoiceProcessor(later).process(invoice));
}
```

This example requires importing `java.time.Duration`. Never call `Thread.sleep(...)` to wait for a deadline; tests stay instantaneous, repeatable, and independent of CI speed.

## 6. Key Batch Principle: One Job Run Needs a Stable Timestamp Baseline

`Clock.fixed(...)` in unit tests is not enough to solve a production issue: a batch job can run for **minutes or hours**, crossing midnight or a cutoff boundary.

Suppose a job selects data "before today":

```java
LocalDate today = LocalDate.now(clock);
```

If that statement runs per item, a job starting at 23:59 might process the first half of a file using day D and the second half using day D+1. When restarted the next day, the same `JobInstance` could apply a different filter rule than the first attempt.

Two common design patterns address this:

1. **Snapshot once at job start:** store `asOf` or `businessDate` in the execution context or pass it to processing components instead of re-reading current time for every item.
2. **Pass the cutoff time in `JobParameters`:** the launcher determines `businessDate`/`asOf` before launching; the step reads the exact same value across all chunks and restarts.

For batch jobs requiring **consistent results on restart**, explicit time parameters are usually easiest to test.

### Example: Step-Scoped Processor Using a Fixed `asOf`

Suppose the launcher passes:

```text
asOf = 2026-05-01T10:00:00Z
```

The processor is created once within the `StepExecution` scope and uses that value:

```java
import java.time.Instant;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InvoiceStepConfiguration {

    @Bean
    @StepScope
    ItemProcessor<Invoice, Invoice> dueInvoiceProcessor(
            @Value("#{jobParameters['asOf']}") String asOfText) {

        Instant asOf = Instant.parse(asOfText);
        return invoice -> invoice.dueAt().isAfter(asOf)
                ? null
                : invoice;
    }
}
```

There is no need to call `Clock` per item. This approach locks the cutoff once and can be reproduced with the same input data and `asOf` parameter.

In **Spring Batch 5.x**, parameters can be built when launching the job like this:

```java
Instant asOf = clock.instant();

JobParameters parameters = new JobParametersBuilder()
        .addString("asOf", asOf.toString(), true)
        .addString("businessDate", LocalDate.now(clock).toString(), true)
        .toJobParameters();

JobExecution execution = jobLauncher.run(importJob, parameters);
```

This assumes `JobLauncher`, `Job`, `Clock`, and the corresponding Spring Batch 5.x imports are present. The `true` flag marks an **identifying parameter**. The job name plus its identifying parameters define the `JobInstance`.

**Relationship with restart:**

- A new run for a different business date can carry different parameters.
- When restarting a failed instance, use **the exact same identifying parameters** and preserve that run's cutoff.
- Do not generate a fresh `asOf = Instant.now()` on every restart, as that can turn a restart into a new instance or change which input records are selected.
- A `COMPLETED` instance cannot be rerun with the exact same identifying parameters as an ordinary new execution; intentional reprocessing requires a separate rerun policy.

If `businessDate` defines the job's identity, often only `businessDate` needs to be identifying, while `asOf` is chosen at launch and kept **immutable across executions of that instance**. Design parameter pairs carefully to match restart rules; never vary non-identifying parameters arbitrarily to shift the cutoff of an existing instance.

## 7. Preparing `Clock` in Spring Boot Integration Tests

### 7.1. `@TestConfiguration` Supplying a Fixed Time

When booting a full Spring context, you can provide a test-only `Clock` bean:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = "spring.batch.job.enabled=false")
class BusinessClockIntegrationTest {

    @TestConfiguration
    static class FixedTimeConfiguration {

        @Bean
        @Primary
        Clock fixedTestClock() {
            return Clock.fixed(
                    Instant.parse("2026-03-31T17:00:00Z"),
                    ZoneId.of("Asia/Ho_Chi_Minh")
            );
        }
    }

    @Autowired
    private BusinessDateService businessDateService;

    @Test
    void resolvesBusinessDateFromConfiguredZone() {
        assertEquals(
                LocalDate.of(2026, 4, 1),
                businessDateService.today()
        );
    }
}
```

The test needs `import java.time.LocalDate;`. `@Primary` ensures Spring picks the test clock bean when the application already defines a production `Clock` bean.

**Bean management note:** if the application context has multiple `Clock` beans with distinct qualifiers, `@Primary` may not override the specific qualified bean a component injects; use matching qualifiers or replace the bean via the strategy supported by your Spring Boot version. Never create a shared fixed `Clock` and mutate it across parallel tests; give each scenario clear configuration and state.

### 7.2. Using Spring Batch Test to Run Jobs

In **Spring Batch 5.x**, `spring-batch-test` provides `@SpringBatchTest` and `JobLauncherTestUtils` to launch jobs and steps in tests. An integration test can:

1. Initialize the test database, batch metadata tables, and input fixtures.
2. Inject `Clock.fixed(...)` to control the launch timestamp.
3. Build `JobParameters` with fixed `asOf` and `businessDate`.
4. Run the job via `JobLauncherTestUtils.launchJob(parameters)`.
5. Check `BatchStatus`, read/filter/write counts, and final output data.
6. Clean up metadata, output tables/files, and fixtures strictly inside the test environment.

Execution snippet inside a test configured with `@SpringBatchTest` and a target job assigned to the launcher:

```java
var parameters = new JobParametersBuilder()
        .addString("asOf", "2026-05-01T10:00:00Z")
        .addString("businessDate", "2026-05-01")
        .toJobParameters();

JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

assertEquals(BatchStatus.COMPLETED, execution.getStatus());
// Continue asserting business data and StepExecution counters.
```

This is an illustrative test fragment, not a standalone test class: it requires job, repository, database, and fixture configuration. If the project uses **Spring Batch 6.x**, the test launching utility is `JobOperatorTestUtils`, and several Spring Batch packages moved; consult documentation for that version to adjust imports and launching calls.

### 7.3. Preventing Jobs from Auto-Running When Test Context Starts

In Spring Boot, setting:

```properties
spring.batch.job.enabled=false
```

lets integration tests choose the exact timing and `JobParameters` instead of auto-running jobs at context initialization. This property only controls **Spring Boot auto-launch**; it is not a mechanism for freezing clocks or disabling all `@Scheduled` tasks in the application.

## 8. Testing Timezones and Date Boundaries

### 8.1. Freeze the `Instant`, Choose `ZoneId` Explicitly

```java
Instant point = Instant.parse("2026-11-16T17:30:00Z");

Clock utc = Clock.fixed(point, ZoneOffset.UTC);
Clock hcm = Clock.fixed(
        point,
        ZoneId.of("Asia/Ho_Chi_Minh")
);

assertEquals(LocalDate.of(2026, 11, 16), LocalDate.now(utc));
assertEquals(LocalDate.of(2026, 11, 17), LocalDate.now(hcm));
```

It is the same instant, yet `LocalDate.now(...)` differs. This is a great regression test for jobs aggregating by local date while running on UTC servers.

### 8.2. Prefer Half-Open Intervals `[start, end)`

Suppose a job pulls events occurring on business date `2026-04-01` in Vietnam time:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate date = LocalDate.of(2026, 4, 1);

Instant startInclusive = date.atStartOfDay(zone).toInstant();
Instant endExclusive = date.plusDays(1).atStartOfDay(zone).toInstant();
```

When querying, use a half-open interval:

```sql
SELECT event_id, occurred_at
FROM payment_event
WHERE occurred_at >= :startInclusive
  AND occurred_at <  :endExclusive;
```

Advantages:

- No need to construct `"23:59:59.999999..."` dependent on column timestamp precision.
- An event exactly at midnight of the following day belongs to **exactly one** window.
- Consecutive daily windows neither overlap nor leave gaps.

If the database stores `TIMESTAMP WITHOUT TIME ZONE`, establish the data convention explicitly (such as timezone-stripped UTC values) before binding parameters. Prefer timestamp types with unambiguous instant semantics, such as PostgreSQL `timestamptz`, when available.

### 8.3. Daylight Saving Time (DST)

Not every calendar day is exactly 24 hours long. In timezones observing DST, transition days have 23 or 25 hours.

For example, `Europe/Berlin` transitions to summer time on **2026-03-29**:

```java
ZoneId berlin = ZoneId.of("Europe/Berlin");
LocalDate businessDate = LocalDate.of(2026, 3, 29);

Instant start = businessDate.atStartOfDay(berlin).toInstant();
Instant end = businessDate.plusDays(1).atStartOfDay(berlin).toInstant();

assertEquals(Duration.ofHours(23), Duration.between(start, end));
```

Computing `end` as `start.plus(Duration.ofHours(24))` would spill one hour into the next day. For **calendar-day windows**, calculate boundaries using `LocalDate` and `ZoneId` first, then convert to `Instant`.

Conversely, when DST ends, one local wall-clock hour occurs twice. `LocalDateTime` cannot tell which occurrence is meant. For real events, store `Instant` or an explicit offset; for schedules, define a policy for ambiguous or nonexistent local times.

### 8.4. `Duration` Differs from `Period`

"24 hours ago" is not the same as "yesterday on the local calendar":

```java
Instant last24Hours = clock.instant().minus(Duration.ofHours(24));

LocalDate yesterday = LocalDate.now(clock).minusDays(1);
```

If a job reports on **yesterday**, compute `startOfDay` for `yesterday` and `today` in the business zone; if the job genuinely needs **the trailing 24 hours**, apply `Duration` to `Instant`.

## 9. Retry and Restart: Do Not Let the Clock Change Rules Between Attempts

### 9.1. Retrying an Item

Suppose a processor checks whether an event has expired:

```java
boolean expired = item.expiresAt().isBefore(clock.instant());
```

If the writer encounters a transient error, the framework may retry the item or chunk. During retries, real time advances; an item that had not expired initially can become expired later. Thus, **the exact same item** in **the exact same job run** could receive different outcomes.

This is not a `Clock` bug, but a consequence of basing business decisions on a moving `now`. If the system requires consistent outcomes within a run, compute `asOf` once, pass it to the processor, and use it across all retries and restarts. Only if the true requirement is "check deadline at the exact moment of the API call" does dynamic time make sense—and tests should explicitly specify that policy.

### 9.2. Restarting After Midnight

Consider a job processing Day D data:

```text
23:55 Day D:    JobInstance starts, businessDate = D
23:59 Day D:    Chunk 1 commits successfully
00:01 Day D+1:  Chunk 2 fails
08:00 Day D+1:  Job restarts from checkpoint
```

If the restart calls `LocalDate.now(clock)` to pick input, the job could silently switch to Day D+1 without anyone requesting it. When `businessDate` is a stable `JobParameter`, the job keeps processing Day D data.

To test restart:

- Launch the job with `businessDate=D` and a fixed `asOf`.
- Trigger a controlled failure after some chunks commit.
- Keep `JobRepository` metadata and checkpoint data intact.
- Restart the same `JobInstance` using your version's restart API.
- Verify remaining data is processed under **the same businessDate/cutoff** with no duplicate output.

Do not delete all `JobExecution` records before restarting, because metadata and `ExecutionContext` are part of the recovery state.

### 9.3. `Clock` Does Not Control Transactions or Schedulers

Freezing the processor's `Clock` does not freeze timeouts, retry backoffs, transaction managers, or schedulers. Those components may rely on the system clock, monotonic timers, or separate APIs. To test retry/backoff quickly and deterministically, control **the specific retry/scheduler mechanism** (for instance by injecting a strategy, fake scheduler, or zero backoff in tests) rather than assuming `Clock.fixed(...)` halts everything.

## 10. Known Limits: What Does Your `Clock` Actually Control?

| Component | Does the Injected `Clock` Apply? | Reason |
| --- | --- | --- |
| Service calling `clock.instant()` | Yes | Uses the dependency directly |
| Processor calling `LocalDate.now(clock)` | Yes | Uses the Clock's zone and instant |
| Writer setting `processedAt = clock.instant()` | Yes | Application controls the timestamp value |
| Code calling zero-arg `Instant.now()` | No | Reads the system clock |
| SQL calling `CURRENT_TIMESTAMP` | No | Database determines the timestamp |
| Metadata timestamps set by Spring Batch | Not guaranteed | Framework uses its own timing mechanism |
| Job triggered by `@Scheduled` | Not automatically | Scheduler has its own clock and trigger mechanism |
| HTTP service returning another server's time | No | Time source lives outside the application |
| `Thread.sleep` or elapsed-time timeouts | Not automatically | Independent of business logic's Clock |
| `JobParameters` already carrying `businessDate` | Clock does not alter it | Job execution inputs are immutable by design |

For example, if a writer executes:

```sql
INSERT INTO invoice_log(invoice_id, created_at)
VALUES (:invoiceId, CURRENT_TIMESTAMP);
```

then `created_at` reflects database time even when Java tests inject `Clock.fixed(...)`. If tests need to assert a specific timestamp, have the writer pass the timestamp from Java:

```java
Instant processedAt = clock.instant();
```

and bind `processedAt` as a SQL parameter. Be sure the driver/JDBC mapping of `Instant` to the database timestamp column type is aligned.

Similarly, metadata such as `JobExecution` start/end times managed by Spring Batch do not have to match the application's custom `Clock` bean. Tests should not assert equality against a "frozen" value if the metadata source does not use that clock. For framework metadata, prefer asserting status, timestamp presence, and valid ordering while accounting for storage precision.

## 11. Designing Comprehensive Time Fixtures

For a job selecting invoices with `dueAt <= asOf`, prepare boundary data:

| ID | `dueAt` Relative to `asOf` | Expected |
| --- | --- | --- |
| INV-001 | 1 day before | Selected |
| INV-002 | 1 nanosecond before | Selected if storage retains that precision |
| INV-003 | Exactly equal to `asOf` | Selected when rule is `<=` |
| INV-004 | 1 nanosecond after | Not selected |
| INV-005 | 1 day after | Not selected |
| INV-006 | `null` | Handled per validation policy; never silently treated as overdue |

When testing with a database, timestamp storage precision may only reach microseconds or milliseconds. Writing two timestamps 1 nanosecond apart and reading them back can cause the database to round them to the same value. Adjust fixture offsets to match actual storage precision, while keeping a pure Java test for nanosecond-level comparison.

For a daily aggregation job:

| Case | Test Assertion |
| --- | --- |
| Event right before start of day | Excluded from reporting period |
| Event right at start of day | Included in reporting period |
| Event right before exclusive end | Included in reporting period |
| Event right at exclusive end | Belongs to next period |
| Job starts near midnight | Business date remains stable |
| UTC day D while local is already D+1 | Uses the right `ZoneId` |
| DST spring-forward / fall-back | Window based on calendar date, not hardcoded +24 hours |
| Restart on the next day | Retains original reporting period parameters |

Beyond output rows, an integration test should check `BatchStatus`, persisted records, relevant `StepExecution` counters, and checkpoint state if testing restart. A lone `COMPLETED` status does not prove the job selected the right date or time window.

## 12. `Clock` in Parallel Tests and CI Environments

### Avoid Shared Mutable State

`Clock.fixed(...)` is immutable, making it safe for parallel tests when all tests use the same instant. However, if you write a `MutableClock` with an `advance(...)` method and register it as a suite-wide singleton, two parallel tests can shift time under each other.

Safer options:

- Use distinct `Clock.fixed(...)` instances per unit test or per test context.
- Pass separate `asOf`/`businessDate` values per job execution when testing concurrent runs.
- If a mutable clock is unavoidable, scope it to a single test and synchronize access safely.
- In multi-process jobs, ensure cutoff calculation does not depend on individual workers' local clocks.

### Avoid CI Timezone Dependencies

Do not rely on:

```java
LocalDate today = LocalDate.now();
ZoneId zone = ZoneId.systemDefault();
```

In business-date tests, write instead:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Clock clock = Clock.fixed(
        Instant.parse("2026-03-31T17:00:00Z"),
        zone
);
LocalDate date = LocalDate.now(clock);
```

CI runners may set `TZ=UTC`; many containers default to UTC too. Fixing the zone at the business boundary keeps tests independent of host settings.

### Distinguish "Wall Clock" from "Elapsed Time"

`Clock` models calendar time and instants. For measuring execution duration inside a process, `System.nanoTime()` is generally better because it measures monotonic elapsed time, whereas wall clocks can jump due to system adjustments. Use `Clock.fixed(...)` to test "is it past due?" logic, not to benchmark or measure how many milliseconds a chunk took.

For timeouts, ideal tests drive a fake scheduler or asynchronous signals instead of `Thread.sleep(...)` and tight real-time deadlines. True performance tests should stay separate from time-logic unit tests.

## 13. Common Errors and Troubleshooting

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| Test fails only around midnight | Calling `LocalDate.now()` at different moments | Use `Clock.fixed` in tests; snapshot cutoff per run |
| Results differ between laptop and CI | Different `ZoneId.systemDefault()` | Declare the business zone explicitly |
| Passes in UTC, fails in Vietnam | Confusing `Instant` and `LocalDate` | Convert via `atZone(businessZone)` before extracting date |
| Drops records on DST day | Computing `end = start + 24 hours` | Compute next day's `startOfDay` in the zone |
| Restart picks a new day's file | Recomputing `businessDate` at restart time | Persist date/cutoff in `JobParameters` or checkpoint |
| Clock frozen yet `created_at` changes | SQL `CURRENT_TIMESTAMP` supplied by DB | Pass timestamp from Java or adjust test expectations |
| Clock frozen yet Batch metadata uses real time | Framework does not use app's Clock bean | Check timestamp contracts; avoid asserting unsupported fixed values |
| Timeout test runs slowly | Using `Thread.sleep` / real scheduler | Use fake scheduler, test backoff, or event triggers |
| One test alters time for another | Shared singleton mutable Clock | Scope clock per test; eliminate global mutable state |
| "Expired" test passes/fails intermittently | Deadline placed too close to `Instant.now()` | Use a fixed baseline and test each boundary separately |
| Job reruns with wrong period | Generating new `run.id` and recomputing business date unchecked | Define business period and identifying parameters explicitly |

## 14. Practice Exercises

**Exercise 1 – Overdue Processor.** Write an `ItemProcessor<Invoice, Invoice>` that keeps only due invoices. Use `Clock.fixed(...)` to test three cases: before cutoff, at cutoff, and after cutoff. Switch the rule to `dueAt < now` and update the boundary expectation.

**Exercise 2 – Daily Aggregation in Vietnam.** Given `Instant.parse("2026-03-31T17:00:00Z")`, write a test verifying that the business date in `Asia/Ho_Chi_Minh` is `2026-04-01`. Build a query using `[startOfDay, nextStartOfDay)` and test events right on the boundaries.

**Exercise 3 – Job Crossing Midnight.** Simulate a job starting before midnight and restarting the next day. Pass fixed `businessDate` and `asOf` via `JobParameters`; verify output still belongs to the same period. Do not delete `JobRepository` between the two runs if testing real restart.

**Exercise 4 – DST.** Use `Europe/Berlin` on `2026-03-29`. Verify the interval between two `atStartOfDay(zone)` calls is 23 hours and explain why adding 24 hours is the wrong way to compute "one business day."

**Exercise 5 – Scope of `Clock`.** Write one writer persisting `processedAt` from `clock.instant()` and another using SQL `CURRENT_TIMESTAMP`. Freeze the Clock, run an integration test on a dedicated database, and verify how the two timestamps can diverge.

## 15. Conclusion

In Spring Batch, time should be treated as a **controllable input** to business logic. `java.time.Clock` decouples code from the system clock, while `Clock.fixed(...)` lets unit tests reproduce exact instants and boundary cases. For long-running or restartable batch jobs, injecting `Clock` alone is not enough: `businessDate`/`asOf` must be fixed across the entire lifecycle of a job instance. Combining **`Instant` for absolute points**, **`ZoneId` for business calendar dates**, **`[start, end)` intervals** for data windows, and **isolated test fixtures** keeps jobs consistent across local runs, CI, and production.

### References

- [Java SE – Clock API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html)
- [Java SE – Instant API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
- [Java SE – ZoneId API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html)
- [Spring Batch – JobParameters](https://docs.spring.io/spring-batch/reference/domain.html#jobParameters)
- [Spring Batch – Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Spring Batch – Restarting a Job](https://docs.spring.io/spring-batch/reference/job.html)
