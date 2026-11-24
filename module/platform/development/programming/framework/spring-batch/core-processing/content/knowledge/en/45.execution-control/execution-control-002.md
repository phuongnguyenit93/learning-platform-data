# Starting a Job from a Scheduler in Spring Batch

## 1. Goals and Context

A batch job is rarely run only manually. Real-world systems often need to **automatically launch jobs on a schedule**: end-of-day order aggregation, every-morning payment reconciliation, hourly data synchronization, or end-of-month reporting. In Spring Batch, this responsibility is split into two parts: the scheduler issues launch requests at predefined times; Spring Batch executes the job, stores metadata, and determines whether the job can be run again.

This lesson explains how to **start a job from a scheduler** in the *Execution control* topic of *Spring Batch Core Processing*. You will learn:

- How a scheduler coordinates with `JobLauncher`, `JobRepository`, `JobInstance`, and `JobExecution`.
- How to use `@Scheduled` to invoke a Spring Batch job in Spring Boot.
- How to construct deterministic `JobParameters` to distinguish processing dates, prevent duplicate runs, and support restarts.
- How to handle failures, job status, overlapping schedules, multiple replicas, and missed runs.
- When to replace an in-process scheduler with Quartz, a Kubernetes CronJob, or an external orchestrator.
- How to test trigger logic without waiting for the real cron schedule.

The main examples use Java 17+, Spring Boot 3.x, and Spring Batch 5.x. The demo application has a `dailyOrdersJob` job that runs at 01:10 AM Vietnam time and processes data for the previous day.

## 2. Which Parts Do the Scheduler and Spring Batch Handle?

A scheduler does not replace Spring Batch's Job and Step concepts. It primarily determines **when** to request execution, while the Batch components are responsible for **what** to process, **with which parameters**, and **in what state**.

```text
   Cron schedule / Trigger / External scheduler
                        |
                        v
                   Scheduler
                        |
           determine businessDate
           build JobParameters
                        |
                        v
                   JobLauncher
                        |
                        v
                  JobRepository
                /               \
               v                 v
          JobInstance       JobExecution
                                  |
                                  v
                         Job -> Step(s)
                                  |
                                  v
                      Reader / Processor / Writer
                                  |
                                  v
                          Processing result
```

| Component | Responsibility |
| --- | --- |
| Scheduler | Issues run requests on a cron expression, fixed interval, or event |
| `JobLauncher` | Accepts `Job` and `JobParameters` to request job execution |
| `JobRepository` | Manages job instance, execution, step execution metadata, and status |
| `JobInstance` | Logical identity of a job by name and identifying parameters |
| `JobExecution` | A single execution attempt of an instance, with its own status and timestamps |
| `StepExecution` | Execution data, counts, status, and errors for each step |
| Job/Step listener or monitoring system | Receives final status, records logs, metrics, and alerts |

A scheduler trigger **does not necessarily create a new JobInstance**. If the job has already completed with the same set of identifying parameters, Spring Batch will refuse to re-run that instance. When a job has failed, a subsequent trigger can restart the same instance and create a new JobExecution if restart conditions allow.

## 3. Scheduler Options

| Approach | Best Suited For | Considerations |
| --- | --- | --- |
| Spring `@Scheduled` | Single always-on application, simple schedules, minimal workflows | Schedule depends on app lifecycle; every replica may trigger simultaneously |
| Quartz Scheduler | Complex triggers, persistent schedules, multi-node | Configure JobStore and clustering; write an adapter calling `JobLauncher` |
| Kubernetes CronJob | Running batch jobs as standalone containers/processes | Each schedule creates a workload; design exit codes, retries, missed runs |
| OS Cron | Standalone scripts or applications | Manage runtime environment, logging, locking, and alerting yourself |
| Airflow, Control-M, Jenkins, orchestrators | Workflows with many dependencies, backfills, centralized observability | External system triggers the app; Spring Batch still tracks execution metadata |

For simple batch jobs within one service, `@Scheduled` is a convenient starting point. When you need schedules persisted across restarts, multi-node coordination, or dependencies across pipelines, consider a dedicated scheduler.

## 4. JobParameters Determine Instance Identity

Spring Batch uses the job name and **JobParameters marked as identifying** to identify a `JobInstance`:

```text
JobInstance = Job name + identifying JobParameters
```

Suppose the batch aggregating data for 2026-11-15 is triggered at 01:10 AM on 2026-11-16:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("requestedAt", "2026-11-15T18:10:00Z", false)
    .toJobParameters();
```

`businessDate` is an **identifying** parameter: the same date means the same JobInstance. `requestedAt` is a **non-identifying** parameter: the request timestamp can vary without changing the instance.

| Request Attempt | businessDate | requestedAt | Typical Result |
| --- | --- | --- | --- |
| First run | 2026-11-15 | t1 | Creates new instance and execution |
| Duplicate request after completion | 2026-11-15 | t2 | Rejected because instance is already `COMPLETED` |
| Restart request after failure | 2026-11-15 | t3 | Can create a new JobExecution under the same instance |
| Request while previous run is active | 2026-11-15 | t4 | Rejected because an execution is already running |
| Next business date | 2026-11-16 | t5 | Creates a new JobInstance |

Do not add `run.id`, a timestamp, or a random UUID as an identifying parameter just to guarantee every cron firing runs. Doing so accidentally creates a new instance for the same business date, which can cause duplicate imports or reconciliations.

Conversely, if the business requirement genuinely treats **each trigger** as an independent processing batch, using a per-run identifier can be completely appropriate. The rule must come from the business meaning of JobInstance.

## 5. Configuring Spring Boot and Enabling Scheduling

### 5.1. Dependencies

Gradle example using Spring Boot starters:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

Spring Batch requires a `JobRepository` capable of storing metadata. In production, use a persistent database and deploy the batch schema via migrations or the corresponding administration process.

### 5.2. Disabling Auto-Launch on Application Startup

If the scheduler decides when to run, disable Spring Boot's automatic job execution:

```yaml
spring:
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: never

# DataSource properties are configured in the deployment environment.
```

`spring.batch.job.enabled=false` prevents Spring Boot from automatically running the job via Boot's startup runner. Setting `initialize-schema: never` assumes the metadata schema already exists, fitting deployments managed by migrations. In a fresh H2 test environment, the schema can be initialized via a separate profile.

### 5.3. Enabling the Scheduler

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class BatchApplication {

    public static void main(String[] args) {
        SpringApplication.run(BatchApplication.class, args);
    }
}
```

`@EnableScheduling` enables processing of `@Scheduled` methods on beans in the Spring context. Annotated methods on objects instantiated manually outside the context will not run on a schedule.

## 6. Defining a Job for the Scheduler to Invoke

The following example creates a job with an illustrative tasklet. In a real application, replace the tasklet body with reading, processing, and saving reports for `businessDate`.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class DailyOrdersJobConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(DailyOrdersJobConfiguration.class);

    @Bean("dailyOrdersStep")
    Step dailyOrdersStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager) {

        return new StepBuilder("dailyOrdersStep", repository)
            .tasklet((contribution, chunkContext) -> {
                Object businessDate = chunkContext
                    .getStepContext()
                    .getJobParameters()
                    .get("businessDate");

                log.info("Processing orders for {}", businessDate);

                // TODO: Replace with real order processing by businessDate.
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
    }

    @Bean("dailyOrdersJob")
    Job dailyOrdersJob(
            JobRepository repository,
            @Qualifier("dailyOrdersStep") Step step) {

        return new JobBuilder("dailyOrdersJob", repository)
            .start(step)
            .build();
    }
}
```

The name `dailyOrdersJob` stays constant across dates. Different processing dates are distinguished by `businessDate`, not by appending the date to the job name.

## 7. Launching the Job on a Cron Schedule with @Scheduled and JobLauncher

### 7.1. Setting Up the Time Source

Use a Spring-managed `Clock` so time is easy to test and swap with `Clock.fixed(...)`:

```java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

The cron in the example is set to 01:10 AM in `Asia/Ho_Chi_Minh`. The business date must also be calculated in this same timezone to avoid date drift when the server runs in UTC or another timezone.

### 7.2. The Scheduler Class

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
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
public class DailyOrdersScheduler {

    private static final Logger log =
        LoggerFactory.getLogger(DailyOrdersScheduler.class);

    private static final ZoneId BUSINESS_ZONE =
        ZoneId.of("Asia/Ho_Chi_Minh");

    private final JobLauncher jobLauncher;
    private final Job dailyOrdersJob;
    private final Clock clock;

    public DailyOrdersScheduler(
            JobLauncher jobLauncher,
            @Qualifier("dailyOrdersJob") Job dailyOrdersJob,
            Clock clock) {

        this.jobLauncher = jobLauncher;
        this.dailyOrdersJob = dailyOrdersJob;
        this.clock = clock;
    }

    // Spring cron: second - minute - hour - day - month - day-of-week.
    // 01:10 AM every day, in Vietnam timezone.
    @Scheduled(cron = "0 10 1 * * *", zone = "Asia/Ho_Chi_Minh")
    public void runOnSchedule() {
        LocalDate businessDate =
            LocalDate.now(clock.withZone(BUSINESS_ZONE)).minusDays(1);

        runForDate(businessDate);
    }

    // Shared for scheduled runs and controlled backfill requests.
    public void runForDate(LocalDate businessDate) {
        JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", businessDate.toString(), true)
            .addString("requestedAt", Instant.now(clock).toString(), false)
            .toJobParameters();

        try {
            JobExecution execution =
                jobLauncher.run(dailyOrdersJob, parameters);

            BatchStatus status = execution.getStatus();

            log.info(
                "dailyOrdersJob date={} executionId={} status={}",
                businessDate,
                execution.getId(),
                status
            );

            if (status == BatchStatus.FAILED ||
                status == BatchStatus.STOPPED) {

                log.error(
                    "Batch date={} failed, exitStatus={}",
                    businessDate,
                    execution.getExitStatus()
                );
                // TODO: Record metric or emit operational alert.
            }

        } catch (JobInstanceAlreadyCompleteException ex) {
            log.info(
                "Date {} was already processed successfully; skipping duplicate trigger",
                businessDate
            );
        } catch (JobExecutionAlreadyRunningException ex) {
            log.info(
                "Date {} is currently running; skipping duplicate trigger",
                businessDate
            );
        } catch (JobRestartException |
                 JobParametersInvalidException ex) {
            log.error(
                "Cannot start/restart batch for date {}",
                businessDate,
                ex
            );
        } catch (Exception ex) {
            log.error(
                "Error requesting batch run for date {}",
                businessDate,
                ex
            );
        }
    }
}
```

In this configuration:

1. Spring invokes `runOnSchedule()` according to the cron schedule.
2. The method selects `businessDate` as the previous day in Vietnam time.
3. `runForDate()` builds `JobParameters`, with the business date marked as identifying.
4. `JobLauncher.run(...)` requests creating or restarting an execution.
5. `JobRepository` checks the instance and manages metadata.
6. The scheduler logs the execution ID, status, and relevant exceptions.

**Distinguishing launch errors from processing errors:** `JobLauncher.run(...)` can throw exceptions when an instance is already complete, already running, invalid to restart, or given invalid parameters. With a synchronous launcher, step failures usually result in `JobExecution` having status `FAILED`, which does not mean every processing error is thrown from `run(...)`. Therefore, you need to inspect `BatchStatus` and `ExitStatus`, and monitor the final state.

If the launcher is configured with an asynchronous task executor, `run(...)` can return while the job is still `STARTING` or `STARTED`. In that case, the returned status **is not the final result**. You must use `JobExplorer`, listeners, logs, or monitoring to confirm the job actually finished.

## 8. Understanding Cron Syntax and Timing Options

Spring `@Scheduled` supports **six-field** cron expressions:

```text
second minute hour day-of-month month day-of-week
  0      10    1        *         *         *
```

A few examples:

| Spring Cron | Meaning |
| --- | --- |
| `0 10 1 * * *` | Every day at 01:10:00 |
| `0 0 * * * *` | Top of every hour |
| `0 0 2 * * MON-FRI` | 02:00 Monday through Friday |
| `0 30 23 L * *` | 23:30 on the last day of every month |

With `@Scheduled`, you can externalize the schedule via configuration properties instead of hardcoding it:

```yaml
app:
  batch:
    cron: "0 10 1 * * *"
    zone: "Asia/Ho_Chi_Minh"
```

Then set the annotation values using property placeholders, for example `@Scheduled(cron = "${app.batch.cron}", zone = "${app.batch.zone}")`. When doing so, the `businessDate` calculation logic must also use the same configured zone; the earlier example hardcoded both to Vietnam time for consistent illustration.

### Cron vs. fixedRate and fixedDelay

```java
// Runs at a fixed wall-clock schedule.
@Scheduled(cron = "0 10 1 * * *", zone = "Asia/Ho_Chi_Minh")
void daily() { /* launch */ }

// Interval between the start of consecutive scheduled calls.
@Scheduled(fixedRate = 60_000)
void pollEveryMinute() { /* launch */ }

// Waits 60 seconds after the previous method call finishes.
@Scheduled(fixedDelay = 60_000)
void pollAfterCompletion() { /* launch */ }
```

`fixedDelay` measures time after the **`@Scheduled` method** returns. If the method only launches an asynchronous job and returns, `fixedDelay` does not mean waiting for the whole batch to finish. Similarly, cron firing at a scheduled time does not guarantee the previous job has finished.

In regions with daylight saving time (DST), a local wall-clock time may not exist or may occur twice on transition days; choose the zone and business rules clearly. `Asia/Ho_Chi_Minh` does not currently observe DST, but multi-region systems still need to account for it.

## 9. Preventing Duplicate Runs When Multiple Replicas Enable the Scheduler

An easy-to-miss detail is that **`@Scheduled` runs inside each application instance**. If the same service is deployed across three nodes, all three nodes can fire the trigger at 01:10.

```text
             01:10
               |
      +--------+--------+
      |        |        |
    Node A   Node B   Node C
      |        |        |
      +--------+--------+
               |
          JobRepository
               |
       Same businessDate
```

A `JobRepository` backed by a shared, properly configured database helps Spring Batch prevent multiple active executions for the same JobInstance. However, instance identity **does not fully replace** the requirement that only one node should emit triggers in a cluster.

You can apply:

- Dedicate a separate instance/service to scheduling.
- Use a distributed lock so only one node sends the request per period.
- Use Quartz with a JDBC JobStore and cluster configuration.
- Place scheduling in an external orchestration system instead of inside each replica.

In-JVM locks such as `synchronized` or `ReentrantLock` do not protect against triggers fired from other JVMs.

### Overlapping Runs Across Different Periods

An hourly job that takes 90 minutes per run requires an explicit design decision. If the 10:00 run has not finished when the scheduler triggers the 11:00 run, the two periods have **different identifying parameters**, so they can be two separate JobInstances and can run concurrently.

Define clearly:

- Are two different data periods allowed to run concurrently?
- Do the reader/writer share files, staging tables, or processing locks?
- Are there limits on connection pools, thread pools, CPU, memory, or completion SLAs?
- If overlap is not allowed, will the scheduler wait, skip, or queue the trigger?

Do not rely solely on the "one active execution per JobInstance" rule to resolve resource conflicts across **multiple JobInstances**.

## 10. Restart, Retry, and Scheduled Backfill

Three concepts need to be distinguished:

| Situation | Mechanism | JobParameters |
| --- | --- | --- |
| Transient error in reader/processor/writer | Step-level retry or fault tolerance | Remains the current execution |
| Job failed and is launched again | Spring Batch restart | Keeps the same identifying parameters |
| Need to process missed periods | Backfill over a list of business periods | Each period has a deterministic business key |

A common mistake:

```java
// Unsuitable for restarting the same date if run.id is identifying.
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15")
    .addLong("run.id", System.currentTimeMillis())
    .toJobParameters();
```

Parameters added via `addLong` are identifying by default. On re-invocation, `run.id` changes and Spring Batch may create a new instance instead of restarting the failed one. If the job already wrote partial data before failing, running a new instance can write duplicates.

### When the Application Stops and Misses Schedules

`@Scheduled` does not guarantee catching up on all missed periods while the application was down. For example, if the service is down for three days and then restarts, a cron scheduler may only fire the next future trigger. Calling `LocalDate.now().minusDays(1)` also picks only one date, not the entire missed range needing backfill.

A backfill mechanism should:

1. Determine the list of required business periods that are due.
2. Use `JobExplorer`/metadata and business data to identify periods that have not succeeded.
3. For periods that do not exist yet, launch a new instance with that period's business key.
4. For `FAILED` and restartable periods, reuse the identifying parameters to restart.
5. For `COMPLETED` periods, skip them or handle them via a separate reprocess workflow.
6. Log the backfill reason and the final result.

Example of calling the scheduler method for a specific date:

```java
dailyOrdersScheduler.runForDate(
    LocalDate.parse("2026-11-11")
);
```

This reuses the same JobParameters rules as the cron trigger, avoiding two independent launch mechanisms with two different identity schemes.

### Reprocessing Is Not the Same as Restarting

Restart uses the exact JobInstance that failed or stopped. Once a JobInstance is `COMPLETED`, re-running with the same identifying parameters is normally rejected. Reprocessing an already completed period is a separate business decision that may require data versioning, result-replacement strategies, and auditing. Do not silently increment `run.id` to bypass this safeguard.

## 11. When Using Quartz or an External Scheduler

### Quartz

Quartz is well-suited when you need persistent triggers, complex schedules, misfire policies, or clustering. A Quartz Job is not a Spring Batch Job; an adapter class typically receives Quartz's `JobExecutionContext` and invokes `JobLauncher` with the required `JobParameters`.

Structure:

```text
Quartz Trigger
     |
     v
Quartz Job.execute(context)
     |
     v
Compute businessDate / job parameters
     |
     v
JobLauncher.run(springBatchJob, parameters)
     |
     v
JobRepository + Step(s)
```

If using a Quartz cluster, properly configure a shared JobStore and misfire policy. Ensure Quartz events map to a stable business key instead of using the trigger timestamp as an identifying parameter on every Quartz retry.

### Kubernetes CronJob and One-Shot Processes

Another pattern is an external scheduler starting the application in one-shot mode:

```text
Kubernetes CronJob / Airflow / Cron
                  |
                  v
         Run Java process
                  |
                  v
     ApplicationRunner or CLI entry point
                  |
                  v
       JobLauncher + JobParameters
                  |
                  v
        Monitor final status
                  |
                  v
        Exit code / Logs / Metrics
```

Example command for a one-shot application run:

```bash
java -jar daily-orders.jar --app.batch.mode=once --app.batch.business-date=2026-11-15
```

The two options `app.batch.mode` and `app.batch.business-date` are **custom application properties**, not options Spring Batch understands automatically. You must implement an `ApplicationRunner` or entry point that reads the date, builds `JobParameters`, calls `JobLauncher`, waits for the final status, and returns an appropriate exit code.

With Kubernetes CronJob, `concurrencyPolicy: Forbid` helps prevent overlapping Kubernetes Jobs belonging to the same CronJob. It does not guarantee external systems will not send duplicate requests, nor does it replace Spring Batch idempotency. A scheduled run can still be missed or triggered repeatedly under operational conditions; the business key must remain stable.

### Triggering via API

A continuously running batch service can expose an internal API for external schedulers or operations portals. The API should accept `businessDate` or a period key, enforce authorization, derive identifying parameters, invoke the launcher, and return the JobExecution ID for status tracking. Avoid designing an API that only accepts "run now" without clearly knowing which data period is being processed.

## 12. Monitoring Final Status and Handling Failures

A `@Scheduled` method returning cleanly does not mean the batch succeeded. At a minimum, observe:

| Data | Purpose |
| --- | --- |
| Business date, job name | Know exactly which period was processed |
| JobInstance ID | Identify a logical period |
| JobExecution ID | Distinguish execution/restart attempts |
| `BatchStatus` and `ExitStatus` | Determine status and exit outcome |
| Start/end timestamps | Measure duration and detect SLA breaches |
| `readCount`, `writeCount`, `skipCount` | Observe per-step processing activity |
| Expected period with no successful execution | Detect missed scheduler triggers |

You can attach a `JobExecutionListener` to record logs/metrics when the job actually ends:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class DailyJobListener implements JobExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(DailyJobListener.class);

    @Override
    public void afterJob(JobExecution execution) {
        log.info(
            "Batch finished: id={}, status={}, exitStatus={}",
            execution.getId(),
            execution.getStatus(),
            execution.getExitStatus()
        );
    }
}
```

Register the listener on the job builder with `.listener(...)`. With an asynchronous launcher, a listener or a process reading final metadata is more reliable than only checking the status right when `JobLauncher.run` returns.

An operations system should also alert when **no job succeeds on time**. If the scheduler fails to fire because the service is down or the cron expression is wrong, there may be no `FAILED` execution to detect.

## 13. Testing Scheduler Logic

You do not need to wait until 01:10 to test business date selection and identifying parameters. With `Clock.fixed(...)` and a mocked launcher, you can call `runOnSchedule()` directly:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.launch.JobLauncher;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class DailyOrdersSchedulerTest {

    @Test
    void schedulesPreviousBusinessDate() throws Exception {
        JobLauncher launcher = mock(JobLauncher.class);
        Job job = mock(Job.class);
        JobExecution execution = mock(JobExecution.class);

        when(launcher.run(eq(job), any(JobParameters.class)))
            .thenReturn(execution);
        when(execution.getStatus())
            .thenReturn(BatchStatus.COMPLETED);

        // 18:10 UTC on Nov 15 corresponds to 01:10 on Nov 16 in Vietnam.
        Clock clock = Clock.fixed(
            Instant.parse("2026-11-15T18:10:00Z"),
            ZoneOffset.UTC
        );

        DailyOrdersScheduler scheduler =
            new DailyOrdersScheduler(launcher, job, clock);

        scheduler.runOnSchedule();

        ArgumentCaptor<JobParameters> captor =
            ArgumentCaptor.forClass(JobParameters.class);
        verify(launcher).run(eq(job), captor.capture());

        JobParameters parameters = captor.getValue();

        assertEquals(
            "2026-11-15",
            parameters.getString("businessDate")
        );
        assertTrue(
            parameters.getParameter("businessDate").isIdentifying()
        );
        assertFalse(
            parameters.getParameter("requestedAt").isIdentifying()
        );
    }
}
```

This test verifies how the scheduler constructs the launch request. It does not yet verify that cron actually triggers or Spring Batch restartability. For end-to-end verification, you need integration tests using a real `JobRepository`, a dedicated test metadata database, and a job with controlled state.

Recommended integration test scenarios:

| Scenario | Key Assertion |
| --- | --- |
| First period with no prior instance | Creates one JobInstance and one execution for the right period |
| Repeated trigger after `COMPLETED` | Does not create a new execution for the completed instance |
| Trigger while execution is running | Duplicate request is rejected |
| Restart after `FAILED` | Instance ID stays the same, new execution ID |
| Changing `businessDate` | Different JobInstance ID |
| Previous period still running when next arrives | Follows concurrency policy |
| Near 00:00 boundary across timezones | Selects the correct businessDate |
| Several days of missed schedules | Backfill mechanism processes the missing periods accurately |

For concurrency tests, use a `CountDownLatch` or equivalent synchronization signal to wait until the first execution is **actually running** before issuing the second trigger. Avoid relying on `Thread.sleep`, which makes tests flaky. Clean metadata between tests or isolate databases so old history does not skew results.

## 14. Common Pitfalls

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Job runs on app startup and again at cron time | Boot auto-run still enabled | Set `spring.batch.job.enabled=false` |
| Cron does not invoke method | Missing `@EnableScheduling`, unmanaged bean, app stopped, or wrong cron | Check Spring context, schedule, logs |
| Batch runs for the wrong date | Cron and businessDate calculation use different zones | Use a consistent timezone and inject `Clock` |
| Multiple JobInstances for the same date | Timestamp/`run.id` is identifying | Identify by a stable business key |
| Multiple nodes trigger together | Every replica runs `@Scheduled` | Choose a scheduler leader, distributed lock, or external scheduler |
| Scheduler reports success while job is `FAILED` | Not monitoring final status | Inspect `JobExecution`, listeners, metadata |
| Overlapping runs cause resource contention | Different periods running concurrently | Define concurrency policy and resource locking |
| Missed days are not caught up | In-process scheduler does not persist missed triggers | Build backfill logic or use a persistent scheduler |
| Retry writes duplicate data | Creating a new instance or writer lacks idempotency | Restart with the same identity, use transactions/idempotency |
| Cron tests are flaky | Depending on wall clock and sleep calls | Use `Clock.fixed`, test trigger logic directly |

## 15. Practice Exercise

Extend `dailyOrdersJob` into a job that reads orders by `businessDate`, computes total revenue, and saves the result to a `daily_order_summary` table. Keep the 01:10 AM Vietnam time schedule.

Exercise the following scenarios: run a new period; re-fire the trigger for a completed period; fail a step and restart the same period; run the next period; simulate the app being down for two days and backfill the exact missing dates. For each scenario, inspect both metadata (JobInstance, JobExecution, BatchStatus) and target table data.

Then simulate two replicas firing triggers for the same period and choose a scheduler coordination strategy. The goal is that output data is not duplicated and execution history accurately reflects what happened.

## 16. Conclusion

Launching a Spring Batch job from a scheduler is more than putting `@Scheduled` on a method. The design must define **run timing, data period, JobInstance identity, and re-run policy**. The scheduler calls `JobLauncher` with stable identifying parameters; `JobRepository` persists state to support duplicate prevention and restarts; operations monitor final outcomes, handle missed schedules, and bound concurrency. When these principles stay consistent, you can switch between `@Scheduled`, Quartz, or an external scheduler without compromising job correctness.
