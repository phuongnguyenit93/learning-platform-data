# JobParameters from a Scheduler in Spring Batch

## 1. Role of JobParameters in a Scheduled Job

A Spring Batch application is often triggered on a schedule: end-of-day revenue aggregation, hourly order synchronization, weekly report generation, or period-end settlement for accounts payable. For such jobs, **the scheduler decides when to request a run**, while **`JobParameters` describe which data the run is asked to process**.

For example, a schedule runs at 02:00 daily and processes the previous day's data. At 02:00 on 2026-11-17 Vietnam time, the scheduler may pass:

```text
jobName = dailyOrdersJob
businessDate = 2026-11-16
triggerSource = scheduler
```

Where:

- `dailyOrdersJob` is the job name.
- `businessDate` is the business date to process, which may differ from the current runtime date of the application.
- `triggerSource` indicates the trigger origin, useful for logging and auditing.

The typical execution flow is:

```text
Cron / @Scheduled / Quartz / external scheduler
                   |
                   v
        Compute businessDate
                   |
                   v
        JobParametersBuilder
                   |
                   v
     JobLauncher.run(Job, JobParameters)
                   |
                   v
    JobRepository looks up JobInstance
          |                  |
          v                  v
  Save JobExecution    Handle rerun /
  and StepExecution    duplicate rules
          |
          v
  Step reads JobParameters to process
```

One point must be understood from the start: the `@Scheduled` annotation **does not automatically turn cron time into `JobParameters`**. Developers must write code to compute values, construct `JobParameters`, and call `JobLauncher`, or use a batch orchestrator with equivalent functionality.

## 2. JobParameters, JobInstance, and JobExecution

In Spring Batch, these three concepts are tightly tied to whether a job can be run again:

| Concept | Meaning | Example |
|---|---|---|
| `JobParameters` | Input parameter set for a single run | `businessDate=2026-11-16` |
| `JobInstance` | A logical instance of a job, determined by the job name and **identifying** parameters | `dailyOrdersJob` for Nov 16 |
| `JobExecution` | An actual execution attempt of that instance | First run fails, second run resumes/restarts |

Logical relationship:

```text
JobInstance: dailyOrdersJob / businessDate=2026-11-16
    |
    +-- JobExecution #101  -> FAILED
    |
    +-- JobExecution #102  -> COMPLETED (restart)

JobInstance: dailyOrdersJob / businessDate=2026-11-17
    |
    +-- JobExecution #103  -> COMPLETED
```

Spring Batch identifies a `JobInstance` based on **job name + values of parameters with the identifying flag**. Non-identifying parameters are still persisted for the `JobExecution` and can still be read by steps, but they do not participate in identifying the logical instance.

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addString("triggerSource", "scheduler", false)
        .toJobParameters();
```

In this example, `businessDate` is identifying, while `triggerSource` is non-identifying. If a later run changes `triggerSource` to `manual` while keeping `businessDate`, Spring Batch still considers it the same job instance. This is intentional when a failed job needs to be manually rerun for the same date.

### 2.1. Outcomes When Calling JobLauncher Multiple Times

| Previous instance status | New call's JobParameters | Typical outcome |
|---|---|---|
| No instance yet | New identifying parameters | Creates new instance and execution |
| Running | Same identifying parameters | `JobExecutionAlreadyRunningException` |
| Completed | Same identifying parameters | `JobInstanceAlreadyCompleteException` |
| Failed and restartable | Same identifying parameters | Creates new `JobExecution` to restart the old instance |
| Completed | Different identifying parameters | Creates new job instance |

Specific outcomes are also affected by `JobRepository`, restartability configuration, step status, and parameter validation. For example, a job marked non-restartable may throw `JobRestartException` when asked to run again.

### 2.2. JobParameters Are Not ExecutionContext

`JobParameters` describe the input request, such as business date, filename, or batch identifier. `ExecutionContext` stores runtime state during execution, such as the last read position for restart.

Do not update a date parameter to act as a checkpoint. Instead:

```text
JobParameters:
    businessDate = 2026-11-16
    inputFile = orders-2026-11-16.csv

Step ExecutionContext:
    lastProcessedOrderId = 15600
    readOffset = 327680
```

Spring Batch persists both parameters and context in the repository when using a persistent `JobRepository`. Avoid putting passwords, tokens, sensitive personal data, or large payloads in `JobParameters` because values may remain in the metadata database and logs.

## 3. Designing Parameters from the Schedule

Design `JobParameters` around the **unit of business data the job processes**, rather than merely capturing the timestamp when the scheduler happened to fire.

| Parameter | Example | Identifying? | Notes |
|---|---|---|---|
| `businessDate` | `2026-11-16` | Usually yes | One instance per business day |
| `billingPeriod` | `2026-11` | Usually yes | One instance per accounting period |
| `tenantId` | `tenant-a` | Yes when each tenant is a separate instance | Combined with `businessDate` to isolate tenants |
| `inputFile` | `orders-2026-11-16.csv` | Depends on domain | Can serve as the ingestion batch key |
| `triggerSource` | `scheduler` / `manual` | Usually no | Caller source for auditing |
| `requestedBy` | `nightly-cron` | Usually no | Should not contain sensitive personal information |
| `scheduledAt` | Timestamp of planned schedule time | Depends on policy | Avoid accidentally turning one day into multiple instances |
| `run.id` | `25` | Only when every run truly needs a new instance | Arbitrary use breaks restart semantics |

### 3.1. Why Not Always Use a Timestamp as an Identifying Parameter?

A common pattern that does not fit every job:

```java
JobParameters parameters = new JobParametersBuilder()
        .addLong("run.id", System.currentTimeMillis())
        .toJobParameters();
```

Every call typically creates a new instance, even when both calls ask to process **the same business date**. As a result:

1. A manual retry is easily treated as a brand-new processing batch instead of restarting the failed instance.
2. Two schedulers firing together can create two distinct instances and double-process data.
3. Millisecond-resolution timestamps do not guarantee absolute uniqueness under all concurrency conditions.
4. Duplicate metadata records and duplicate output data easily appear if business logic is not idempotent.

An identifying timestamp is more suitable for jobs with “each trigger is an independent task” semantics. For a daily revenue aggregation job, making `businessDate` the identifying parameter usually reflects the intent better.

### 3.2. Choosing the Business Date from the Schedule

For a cron running at 02:00 on day D to process day D−1:

```java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate businessDate = LocalDate.now(businessZone).minusDays(1);
```

Calculate using an explicit business timezone. `LocalDate.now()` without a zone depends on the JVM's default timezone; local machines, containers, and CI may produce different dates.

If a scheduler fires late across a date boundary, computing the business date from the **actual callback invocation time** can select the wrong period. For accurate catch-up according to the planned schedule, the orchestrator needs to store/pass the **scheduled fire time** and derive `businessDate` from it. Quartz or external schedulers can supply this information, whereas a standard `@Scheduled` method does not receive the fire time directly as an argument.

## 4. Configuring Spring Boot for Scheduled Jobs

The following examples use **Java 17+, Spring Boot 3.x, and Spring Batch 5.x**. Some packages/builders/APIs change in Spring Batch 6.x; consult the corresponding API documentation when using another version.

### 4.1. Dependencies

Example `build.gradle` (Spring Boot plugin or BOM managing versions):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-batch` provides batch infrastructure and the JDBC repository based on application configuration; an appropriate database driver and `DataSource` still need to be configured. If the project already includes these starters, do not add duplicate declarations.

### 4.2. Schedule Properties

`src/main/resources/application.yml`:

```yaml
spring:
  batch:
    job:
      enabled: false

app:
  jobs:
    daily-orders:
      enabled: true
      cron: "0 0 2 * * *"
      zone: "Asia/Ho_Chi_Minh"
```

`spring.batch.job.enabled=false` prevents **Spring Boot from automatically running jobs at application startup**. It does not disable `@Scheduled`, nor does it forbid other code from calling `JobLauncher`. This is useful when you want the scheduler to actively issue launch commands.

The `app.jobs.daily-orders.*` keys are application-defined. Spring does not interpret them automatically until scheduler code reads them via `@Value` or `@ConfigurationProperties`.

Spring cron has **six fields**:

```text
second  minute  hour  day-of-month  month  day-of-week
  0       0      2         *          *         *
```

The string `0 0 2 * * *` means run at **02:00:00 every day** in the specified timezone. Distinguish Spring cron syntax from Linux cron and certain other schedulers.

### 4.3. Enabling Scheduling and Providing a Clock

```java
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration(proxyBeanMethods = false)
@EnableScheduling
public class BatchSchedulingConfiguration {

    @Bean
    Clock batchClock() {
        return Clock.systemUTC();
    }
}
```

`@EnableScheduling` activates `@Scheduled` processing infrastructure in the Spring context. `Clock` is a time dependency injected into the scheduler so unit tests can use `Clock.fixed(...)` without depending on the real system clock.

## 5. Complete Example: Scheduler Building JobParameters and Calling JobLauncher

Suppose there is a `Job` bean named `dailyOrdersJob` to process the previous day's orders. The scheduler class is as follows:

```java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.launch.JobParametersInvalidException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRestartException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        prefix = "app.jobs.daily-orders",
        name = "enabled",
        havingValue = "true")
public class DailyOrdersScheduler {

    private static final Logger log =
            LoggerFactory.getLogger(DailyOrdersScheduler.class);

    private final JobLauncher jobLauncher;
    private final Job dailyOrdersJob;
    private final Clock clock;
    private final ZoneId businessZone;

    public DailyOrdersScheduler(
            JobLauncher jobLauncher,
            @Qualifier("dailyOrdersJob") Job dailyOrdersJob,
            Clock clock,
            @Value("${app.jobs.daily-orders.zone:Asia/Ho_Chi_Minh}")
                    String zoneId) {
        this.jobLauncher = jobLauncher;
        this.dailyOrdersJob = dailyOrdersJob;
        this.clock = clock;
        this.businessZone = ZoneId.of(zoneId);
    }

    @Scheduled(
            cron = "${app.jobs.daily-orders.cron}",
            zone = "${app.jobs.daily-orders.zone:Asia/Ho_Chi_Minh}")
    public void triggerDailyOrders() {
        LocalDate businessDate =
                LocalDate.now(clock.withZone(businessZone)).minusDays(1);

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate.toString(), true)
                .addString("triggerSource", "scheduler", false)
                .toJobParameters();

        try {
            JobExecution execution = jobLauncher.run(
                    dailyOrdersJob, parameters);

            log.info(
                    "Submitted dailyOrdersJob: businessDate={}, "
                            + "executionId={}, status={}",
                    businessDate,
                    execution.getId(),
                    execution.getStatus());

        } catch (JobExecutionAlreadyRunningException ex) {
            log.info(
                    "dailyOrdersJob is already running for businessDate={}",
                    businessDate);

        } catch (JobInstanceAlreadyCompleteException ex) {
            log.info(
                    "dailyOrdersJob already completed for businessDate={}",
                    businessDate);

        } catch (JobRestartException | JobParametersInvalidException ex) {
            log.error(
                    "Cannot launch dailyOrdersJob for businessDate={}",
                    businessDate,
                    ex);
        }
    }
}
```

**Key points in the code:**

1. `@Scheduled` invokes a no-argument method; the method computes `businessDate` and builds `JobParameters`.
2. `businessDate` is identifying: each business date has a single `JobInstance` for this job.
3. `triggerSource` is non-identifying: used only to record the caller origin without creating a new instance.
4. `@Qualifier` selects the right job when the application defines multiple `Job` beans.
5. `@ConditionalOnProperty` allows disabling the scheduler independently in test environments with `app.jobs.daily-orders.enabled=false`.
6. Catching already-running and already-completed cases separately clarifies the reason in logs. Do not treat all such cases as infrastructure errors.
7. `JobLauncher.run(...)` may execute synchronously or return early if configured to run asynchronously. Therefore, the log uses **Submitted** and prints the status upon return; do not assume the job has finished.

In production systems, exception handling should be paired with metrics, alerting, and a controlled retry mechanism. Do not silently swallow `JobRestartException` or `JobParametersInvalidException` without recording them.

### 5.1. Job Receiving JobParameters via StepScope

Here is a minimal demo configuration for the `dailyOrdersJob` bean. The `Tasklet` receives `businessDate` via Spring Expression Language (SpEL):

```java
import java.time.LocalDate;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class DailyOrdersJobConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(DailyOrdersJobConfiguration.class);

    @Bean
    Job dailyOrdersJob(
            JobRepository repository,
            @Qualifier("dailyOrdersStep") Step step) {
        return new JobBuilder("dailyOrdersJob", repository)
                .start(step)
                .build();
    }

    @Bean
    Step dailyOrdersStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            @Qualifier("ordersForDateTasklet") Tasklet tasklet) {
        return new StepBuilder("dailyOrdersStep", repository)
                .tasklet(tasklet, transactionManager)
                .build();
    }

    @Bean
    @StepScope
    Tasklet ordersForDateTasklet(
            @Value("#{jobParameters['businessDate']}")
                    String dateText) {
        return (contribution, chunkContext) -> {
            LocalDate businessDate = LocalDate.parse(dateText);
            log.info("Processing orders for {}", businessDate);

            // Perform business processing for businessDate here.
            return RepeatStatus.FINISHED;
        };
    }
}
```

`@StepScope` ensures that resolving `jobParameters['businessDate']` happens when the step has an execution context. If a singleton Tasklet resolves parameters at application startup, runtime values for each run will not be available.

The example above only logs to illustrate parameter passing. In real batches, `businessDate` is typically used to filter SQL queries, select input files, configure readers, or determine output partitions.

## 6. Accessing JobParameters in Other Components

Besides SpEL injection into `@StepScope` beans, code can obtain parameters from `StepExecution` and `JobExecution`.

### 6.1. In a Listener

```java
public class BusinessDateListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        String date = stepExecution.getJobParameters()
                .getString("businessDate");

        if (date == null) {
            throw new IllegalArgumentException(
                    "Missing required job parameter: businessDate");
        }

        LocalDate parsed = LocalDate.parse(date);
        // Validate the business date or log it.
    }
}
```

The main imported types in Spring Batch 5.x are `org.springframework.batch.core.StepExecution` and `org.springframework.batch.core.StepExecutionListener`.

### 6.2. In a Tasklet via ChunkContext

A `Tasklet` can obtain `StepExecution` from `ChunkContext`:

```java
StepExecution stepExecution =
        chunkContext.getStepContext().getStepExecution();

String businessDate = stepExecution
        .getJobParameters().getString("businessDate");
```

Do not treat `JobParameters` as a mechanism for sharing mutable state between steps. For state computed during job execution, use `ExecutionContext` or an appropriate business persistence mechanism.

## 7. Boundary Between Scheduled Time and Business Date

These two concepts are distinct:

- **Fire time**: the moment the system emits the trigger, e.g., `2026-11-17T02:00:00+07:00`.
- **Business date**: the data date to be processed, e.g., `2026-11-16`.

| Scenario | Fire time | Desired business date |
|---|---|---|
| Normal schedule: 02:00 the next day | 2026-11-17 02:00 +07 | 2026-11-16 |
| Scheduler delayed by 15 minutes | 2026-11-17 02:15 +07 | 2026-11-16 |
| Machine was down, need to catch up missed day | 2026-11-20 10:00 +07 | Missing date, e.g., 2026-11-17 |
| Operator reruns a failed job | 2026-11-20 11:00 +07 | Date of the failed job, e.g., 2026-11-16 |

The example in section 5 uses `LocalDate.now(clock.withZone(businessZone)).minusDays(1)`. This is a clear rule for normal schedule operation, but **not an automatic catch-up solution** for missed periods. If the machine is down for three days, standard Spring `@Scheduled` will not automatically create three job instances for the old days.

For requirements that cannot miss any period, maintain a persistent source of truth determining which business dates need to run: a business schedule table, trigger queue, persistent scheduler, or backfill workflow. Each period must be passed explicitly via `JobParameters`.

### 7.1. Timezone and DST

`@Scheduled(..., zone = "...")` determines which timezone interprets the cron schedule. `Clock` and `ZoneId` in the business-date calculation code must follow the same business rules.

In regions with daylight saving time, an hour may be skipped or repeated on transition days. You must explicitly define:

- What happens if cron falls on a nonexistent hour?
- If an hour occurs twice, is running twice allowed?
- Which timezone defines a business day?

For accounting/financial workflows, determine the business date based on the official enterprise calendar rather than deriving it naively from a local clock.

## 8. Different Periodic Schedules Require Different Parameter Generation

### 8.1. Daily

```java
LocalDate date = LocalDate.now(businessZone).minusDays(1);
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", date.toString(), true)
        .toJobParameters();
```

One job instance per business day makes sense when each day needs a single final result.

### 8.2. Hourly

If data is divided into hourly windows, use a key representing the **start of the interval**:

```java
ZonedDateTime now = ZonedDateTime.now(businessZone);
ZonedDateTime previousHour = now.truncatedTo(
        java.time.temporal.ChronoUnit.HOURS).minusHours(1);

JobParameters parameters = new JobParametersBuilder()
        .addString("windowStart", previousHour.toOffsetDateTime().toString(), true)
        .toJobParameters();
```

In timezones with DST, the offset in the value distinguishes two hourly windows with the same local wall-clock hour. In distributed systems, time boundaries are often normalized using `Instant`/UTC in job parameters while storing the business timezone when display is needed.

### 8.3. Monthly

```java
YearMonth period = YearMonth.now(businessZone).minusMonths(1);

JobParameters parameters = new JobParametersBuilder()
        .addString("billingPeriod", period.toString(), true)
        .toJobParameters();
```

This example requires `import java.time.YearMonth;`. Each monthly period is a job instance; rerunning a completed monthly period should follow a dedicated reprocess workflow rather than changing `run.id` just to bypass duplicate guards.

## 9. Restart, Retry, and Catch-Up from the Scheduler

### 9.1. Job Fails and Scheduler Triggers Again

If the Nov 16 job fails and the scheduler or operator invokes it again with `businessDate=2026-11-16`, Spring Batch can create a new execution under the same instance and perform a restart, depending on job/step configuration and repository state.

Example:

```text
Nov 16 business date
       |
       +-- First launch -> JobExecution 200 (FAILED)
       |
       +-- Retry same identifying parameters
                         |
                         +-- JobExecution 201 (COMPLETED)
```

Do not add a random identifying `run.id` on retries if you need to leverage checkpoints and restart semantics.

### 9.2. Job Already Completed, Scheduler Calls Again

If the scheduler is invoked again with the same `businessDate` after the job is `COMPLETED`, `JobLauncher` normally throws `JobInstanceAlreadyCompleteException`. This is a useful safeguard against duplicate runs at the instance level, **but does not guarantee idempotency for external systems**. For example, an HTTP API might already have accepted a request even if the local database rolled back.

For workflows prone to side effects, combine idempotency keys, unique constraints, publication states, or an outbox pattern as appropriate.

### 9.3. Wanting to Reprocess Already-Completed Data

If the requirement is genuinely to *reprocess* a completed date, decide how to identify the new processing pass:

- Define a data version or business-meaningful `reprocessVersion` as an identifying parameter.
- Record the reason for reprocessing and maintain an audit trail.
- Define whether to overwrite, append/accumulate, or create a new output version; protect data against duplicate processing.

Do not directly edit `BATCH_JOB_EXECUTION` table rows to turn `COMPLETED` into `FAILED`. Metadata also includes step, version, and context rows; manual SQL edits can leave inconsistent state.

### 9.4. Does RunIdIncrementer Run Automatically on Every Cron Trigger?

No. Even if the job is configured with:

```java
new JobBuilder("someJob", jobRepository)
        .incrementer(new RunIdIncrementer())
        .start(step)
        .build();
```

calling `jobLauncher.run(job, parameters)` still uses **the exact parameters passed in**. The incrementer does not run automatically just because a scheduler invokes `JobLauncher`. `JobOperator`'s “start next instance” feature can use the incrementer, but that must be chosen intentionally. For a job identified by `businessDate`, auto-incrementing `run.id` can break the one-instance-per-day design.

## 10. Multiple Schedulers, Multiple App Instances, and Concurrent Runs

An application may run multiple replicas. If every replica enables `@EnableScheduling`, the same cron can trigger multiple methods at the same time:

```text
Replica A -- @Scheduled 02:00 --+
                                +--> JobRepository --> dailyOrdersJob
Replica B -- @Scheduled 02:00 --+
```

For jobs with the same identifying parameters, `JobRepository` usually detects a running or completed instance. However, race conditions can still occur at launch time, and the repository **does not completely replace a distributed coordination system**.

Design options:

| Scale | Applicable coordination approach |
|---|---|
 One JVM, simple schedule | Spring `@Scheduled` and `JobLauncher` |
 Multiple replicas needing a single issuer | Leader election or distributed scheduling lock |
 Need persistent schedules, misfires, clustering | Quartz with persistent job store or standalone scheduler |
 Existing orchestration infrastructure | Kubernetes CronJob, Airflow, enterprise scheduler… passing parameters to the batch |
 Multiple periods needing backfill and audit | Run-plan table/event queue with durable business keys |

**Note:** intentionally generating a new `run.id` on each replica causes replicas to run as separate job instances, increasing the risk of duplicate side effects.

### 10.1. Scheduling Thread vs. JobLauncher Thread

With a synchronous launcher, the `@Scheduled` method may stay occupied until the job finishes; other schedules sharing the pool can be delayed. With an asynchronous launcher, the method can return immediately while the job is still running. Under either mode, define a policy for a new trigger when the previous run is still active: skip, queue, reject, or run in parallel.

`spring.task.scheduling.pool.size` is a Boot property that configures the scheduling thread count when using the auto-configured `ThreadPoolTaskScheduler`, but increasing thread count does not grant permission to run multiple instances for the same business period. Concurrency safety must be designed across the scheduler, repository, and job logic.

### 10.2. Can Exactly-Once Be Achieved via JobRepository Alone?

You cannot infer “end-to-end exactly-once” merely from using identifying parameters. `JobRepository` manages batch state; external effects like sending emails, calling APIs, writing object storage, or publishing messages may require independent deduplication mechanisms. Similarly, if two differently named jobs modify the same dataset, per-job JobInstance locking will not coordinate between them.

## 11. Integrating Quartz or an External Scheduler

Spring `@Scheduled` is a concise choice for simple schedules. Quartz, enterprise schedulers, or orchestration platforms typically supply trigger metadata, including the planned fire time and schedule ID. When receiving a trigger, convert that information into business parameters **at the application boundary**:

```text
Quartz JobExecutionContext
  scheduledFireTime
  jobDataMap
        |
        v
  BusinessDateResolver
        |
        v
  JobParametersBuilder
        |
        v
  Spring Batch JobLauncher.run(...)
```

Do not confuse `org.quartz.JobExecutionContext` with `org.springframework.batch.core.JobExecution`: they belong to two different frameworks and serve different roles.

Example mapping logic once the scheduled timestamp is obtained from the scheduler:

```java
Instant scheduledInstant = scheduledFireTime.toInstant();

LocalDate businessDate = scheduledInstant
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toLocalDate()
        .minusDays(1);

JobParameters params = new JobParametersBuilder()
        .addString("businessDate", businessDate.toString(), true)
        .addString("triggerSource", "quartz", false)
        .toJobParameters();
```

`scheduledFireTime` above represents the `java.util.Date` obtained from Quartz's `JobExecutionContext.getScheduledFireTime()`. Even if the callback arrives late, the parameter still reflects the date corresponding to the **planned** schedule trigger. The minus-one-day rule must still be an agreed business rule.

If an external scheduler invokes a CLI/HTTP endpoint instead of calling `JobLauncher` directly, that command receiver should still perform validation, proper authorization checks, parameter mapping, and instance tracking as above.

## 12. Validating JobParameters Before the Job Starts

Even with a correct cron schedule, invalid parameters can still arise: nonexistent dates, bad formats, missing tenant, or future dates not allowed for processing.

You can use `JobParametersValidator` in job configuration to fail fast on invalid input:

```java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;

import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.JobParametersValidator;

public class BusinessDateValidator implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        String value = parameters.getString("businessDate");
        if (value == null || value.isBlank()) {
            throw new JobParametersInvalidException(
                    "Missing businessDate");
        }

        try {
            LocalDate.parse(value);
        } catch (DateTimeParseException ex) {
            throw new JobParametersInvalidException(
                    "businessDate must use yyyy-MM-dd", ex);
        }
    }
}
```

In Spring Batch 5.x configuration, attach the validator to the builder:

```java
return new JobBuilder("dailyOrdersJob", jobRepository)
        .validator(new BusinessDateValidator())
        .start(dailyOrdersStep)
        .build();
```

The validator helps protect both scheduled launches and manual runs. If the domain needs to validate tenants, allowed periods, or the relationship between `startDate` and `endDate`, extend the validator according to the job's input contract.

## 13. Unit Testing the Scheduler Without Waiting for Cron

Testing parameter-generation logic **does not require waiting until 02:00**, nor enabling real Spring scheduling. You can instantiate the scheduler with `Clock.fixed(...)`, mock `JobLauncher`, and verify the exact `JobParameters` passed in.

Example using JUnit 5 + Mockito + `spring-batch-test`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.test.MetaDataInstanceFactory;

@ExtendWith(MockitoExtension.class)
class DailyOrdersSchedulerTest {

    @Mock
    JobLauncher jobLauncher;

    @Mock
    Job dailyOrdersJob;

    @Test
    void passesPreviousBusinessDateAsIdentifyingParameter()
            throws Exception {

        Clock fixedClock = Clock.fixed(
                Instant.parse("2026-11-16T20:00:00Z"),
                ZoneOffset.UTC);

        DailyOrdersScheduler scheduler = new DailyOrdersScheduler(
                jobLauncher,
                dailyOrdersJob,
                fixedClock,
                "Asia/Ho_Chi_Minh");

        when(jobLauncher.run(eq(dailyOrdersJob), any(JobParameters.class)))
                .thenReturn(MetaDataInstanceFactory.createJobExecution());

        scheduler.triggerDailyOrders();

        ArgumentCaptor<JobParameters> captured =
                ArgumentCaptor.forClass(JobParameters.class);

        verify(jobLauncher).run(eq(dailyOrdersJob), captured.capture());

        JobParameters parameters = captured.getValue();

        // 20:00 UTC on Nov 16 = 03:00 on Nov 17 Vietnam time.
        assertEquals("2026-11-16",
                parameters.getString("businessDate"));
        assertEquals("scheduler",
                parameters.getString("triggerSource"));
        assertTrue(parameters.getParameters()
                .get("businessDate").isIdentifying());
        assertFalse(parameters.getParameters()
                .get("triggerSource").isIdentifying());
    }
}
```

This test proves **the scheduler computes and passes the right parameters**. It does not prove the job actually executes, metadata is written to the database, or cron triggers at the right time.

### 13.1. Testing the Cron Expression Separately

With Spring Framework's `CronExpression`, you can verify the next trigger timestamp in a specific timezone:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.ZoneId;
import java.time.ZonedDateTime;

import org.junit.jupiter.api.Test;
import org.springframework.scheduling.support.CronExpression;

class DailyOrdersCronTest {

    @Test
    void nextFireOccursAtTwoAmInBusinessZone() {
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime after = ZonedDateTime.of(
                2026, 11, 16, 1, 30, 0, 0, zone);

        ZonedDateTime next = CronExpression
                .parse("0 0 2 * * *")
                .next(after);

        assertEquals(
                ZonedDateTime.of(2026, 11, 16, 2, 0, 0, 0, zone),
                next);
    }
}
```

This tests the **cron rule**; the application still needs `@Scheduled`, the scheduler bean, and properties configured accurately. In particular, never use multi-second or multi-minute sleeps just to wait for cron in unit tests.

## 14. Integration Test Running the Job with Parameters from the Test

Integration tests should invoke `JobLauncherTestUtils` or `JobLauncher` with `JobParameters` constructed by the test, then verify execution status and business outcomes.

Example using the demo job from section 5.1, with a test profile having an H2 datasource and metadata schema:

`src/test/resources/application-test.yml`:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:daily_orders_test;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ''
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

app:
  jobs:
    daily-orders:
      enabled: false
      cron: "0 0 2 * * *"
      zone: "Asia/Ho_Chi_Minh"
```

`app.jobs.daily-orders.enabled=false` disables the **scheduler bean**, without disabling the `dailyOrdersJob` definition. The test launches the job explicitly:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBatchTest
@SpringBootTest
@ActiveProfiles("test")
class DailyOrdersJobIT {

    @Autowired
    JobLauncherTestUtils launcherTestUtils;

    @Autowired
    JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    @Qualifier("dailyOrdersJob")
    Job dailyOrdersJob;

    @BeforeEach
    void prepare() {
        repositoryTestUtils.removeJobExecutions();
        launcherTestUtils.setJob(dailyOrdersJob);
    }

    @Test
    void completesForRequestedBusinessDate() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-16", true)
                .addString("triggerSource", "integration-test", false)
                .toJobParameters();

        JobExecution execution = launcherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
    }
}
```

This test assumes the application context has registered the `Job`, `Step`, `JobRepository`, and transaction manager beans matching the demo. `JobRepositoryTestUtils.removeJobExecutions()` deletes metadata across the **entire test repository**; do not use it when other tests share that database concurrently.

In real applications, also verify data written by readers/writers, rollback handling, or checkpoints depending on the objective. `BatchStatus.COMPLETED` alone does not prove business results are correct.

### 14.1. Testing Restart Properly

To test restart, you must:

1. Run the same `businessDate` the first time under a condition that causes the job/step to genuinely fail.
2. Preserve metadata and `ExecutionContext` in `JobRepository`.
3. Fix the failure condition, then relaunch with the same identifying parameters.
4. Verify that `JobInstance` is unchanged, a new `JobExecution` exists, and the reader/step resumes according to restart rules.

Do not call cleanup between the two runs of a restart test; deleting metadata turns the second run into a new instance.

## 15. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Job runs at startup and then again on cron | Both Spring Boot auto-run and `@Scheduled` are active | Set `spring.batch.job.enabled=false` when the scheduler must orchestrate |
| `JobInstanceAlreadyCompleteException` | Same identifying parameters already `COMPLETED` | Treat as expected duplicate guard, or intentionally design a new reprocess instance |
| `JobExecutionAlreadyRunningException` | An instance is already running when another trigger arrives | Choose skip/queue policy; check for multiple replicas |
| `JobParametersInvalidException` | Missing or malformed `businessDate` | Check builder and `JobParametersValidator` |
| Schedule fires on time but processes wrong date | Using JVM timezone or system `LocalDate.now()` | Use business `ZoneId` and test with `Clock.fixed` |
| Backfilling an old date processes yesterday instead | Scheduler derives date solely from current wall-clock time | Pass explicit business date from backfill plan |
| Retry creates a new instance | Adding identifying `run.id`/timestamp on every call | Keep the same identifying parameters when restarting |
| `@Scheduled` does not invoke method | Missing `@EnableScheduling`, bean not in Spring context, invalid cron property, scheduler disabled | Check bean registration, profile, and cron config |
| `@Scheduled` method called from two replicas | Each replica runs its own scheduler | Use distributed coordination or a central scheduler |
| Step receives `businessDate=null` | Missing parameter or bean not properly `@StepScope` | Validate input, use `@StepScope`, and read the right key |
| Log shows submitted but no completion seen | Asynchronous `JobLauncher` or job failed after launch | Inspect latest `JobExecution`, metrics, and step exceptions |
| Unexpectedly many metadata instances | Identifying timestamp changes on every trigger | Design a stable business key |
| Job duplicates results despite instance guard | Non-idempotent external side effects or another job modifying the same data | Design idempotency, constraints, locks, and proper auditing |

## 16. Parameter Design Workflow for a Scheduled Job

When starting to implement scheduling in Spring Batch, clarify each of the following decisions:

1. **Unit of work:** a day, a period, a tenant, a file, or an event?
2. **Identifying key:** which parameters are identifying so there is one logical instance per unit of work?
3. **Time source:** derived from planned fire time or actual callback time? Which timezone is used?
4. **Late and missed schedule policy:** skip, queue, per-period backfill, or alert for handling?
5. **Rerun policy:** same instance when `FAILED`, reject when `COMPLETED`, or separate versioned reprocess?
6. **Concurrency:** can multiple threads/hosts issue commands at once, and who holds orchestration authority?
7. **Parameter passing:** use `JobParametersBuilder`, validation, `JobLauncher`, and `@StepScope` beans.
8. **Operational observability:** log job name, business key, execution ID, final status; alert on job failures.
9. **Testing:** unit test business date calculation with `Clock.fixed`, test cron expressions, integration test repository and batch results.

### Practice Exercises

**Exercise 1 — One Job Instance per Day**

- Configure cron to run at 01:30 in `Asia/Ho_Chi_Minh`.
- Pass `businessDate` as the previous day formatted as `yyyy-MM-dd` and mark it identifying.
- Mark `triggerSource=scheduler` as non-identifying.
- Use Mockito to capture `JobParameters` and verify the business date from a `Clock.fixed`.

**Exercise 2 — Retry and Duplicate**

- Run an integration test with the same `businessDate` twice.
- Observe that once the job is `COMPLETED`, the second call is rejected by instance semantics.
- Introduce an intentional failure case and attempt a restart with the same identifying parameters; verify two `JobExecution`s belong to the same `JobInstance`.

**Exercise 3 — Multi-Day Backfill**

- Design a service accepting a list of missing dates, e.g., Nov 10, Nov 11, Nov 12.
- Build exactly one `JobParameters` request per date; do not call `LocalDate.now()` inside each iteration.
- Define behavior if a date is currently running or already completed; do not generate a random `run.id` to bypass duplicate guards.

**Exercise 4 — Two Replicas**

- Simulate two calls to `JobLauncher.run(...)` with the same identifying parameters.
- Identify the exception/status `JobRepository` actually returns in the test environment.
- Outline how to ensure only one scheduler issues triggers and how to prevent duplicate business side effects in the writer.

## 17. References

- [Spring Batch Reference — Job Parameters](https://docs.spring.io/spring-batch/reference/job/running.html): passing parameters when launching jobs and instance identification rules.
- [Spring Batch Reference — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): job configuration, restartability, and related components.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): job and step testing utilities.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Scheduled`, cron, timezone, and scheduling infrastructure.
- [Spring Framework Javadoc — `CronExpression`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/support/CronExpression.html): parsing and computing next cron trigger times.
- [Spring Boot Reference — Batch](https://docs.spring.io/spring-boot/reference/io/spring-batch.html): Spring Batch integration and Spring Boot auto-run configuration.

