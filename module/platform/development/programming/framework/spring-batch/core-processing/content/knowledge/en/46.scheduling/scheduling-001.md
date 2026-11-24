# Batch Scheduling in Spring Batch

**Batch scheduling** is the mechanism that decides **when** a batch processing job is started: daily at 02:00, every 15 minutes, after end-of-day cutoff, at month-end, or when another job finishes. In **Spring Batch Core Processing**, two responsibilities must be distinguished:

- **The scheduler** determines the trigger time, manages triggers, and may apply policies such as no-overlap execution, holiday calendars, or catch-up runs.
- **Spring Batch** executes the `Job`/`Step` and manages `JobParameters`, status, transactions, metadata, restart, skip, and retry during processing.

Spring Batch **does not itself act as a complete scheduling system**. You can use Spring Framework's `@Scheduled`, Quartz, OS cron, Kubernetes CronJob, or an orchestration platform to trigger the job. The schedule lives in the orchestration layer; execution lives in Spring Batch.

```text
              SCHEDULE
    @Scheduled / Quartz / CronJob
                 |
         create JobParameters
                 |
                 v
          JobLauncher / JobOperator
                 |
                 v
            Spring Batch Job
                 |
        Step A -> Step B -> Step C
                 |
                 v
        JobRepository + database
        (metadata / status / restart)
```

For example, an accounting system has an end-of-day transaction aggregation job. At 02:00 each day, the scheduler triggers `dailySettlementJob` with the business date parameter; Spring Batch reads transactions, computes totals, writes results, and saves status. If the job fails, the policy for **whether to rerun, restart from a checkpoint, or wait for manual intervention** must be designed separately. Having cron alone does not solve this problem.

## 1. Common Scheduling Patterns

| Pattern | Example requirement | Suitable mechanism |
| --- | --- | --- |
| By time of day | 02:00 every day | Cron expression |
| By day of week | 08:30 Monday through Friday | Cron expression with day of week |
| Fixed interval | Every 5 minutes from start time | `fixedRate` or interval trigger |
| Wait until previous run finishes before waiting again | 10 minutes after the previous task finishes | `fixedDelay` if the call actually waits for job completion |
| Event-driven | After the input file has complete data | Event-driven orchestrator, message/event handler, or controlled polling |
| Business calendar | Last business day of the month, excluding holidays | Calendar-aware scheduler, or business-calendar check before launch |
| Run once across multiple machines | One job per reporting period, in a cluster | Distributed scheduler or uniform period-level locking/identification mechanism |

Not every system needs a complex scheduler. A single-instance application with a simple schedule and no requirement to persist missed triggers can start with `@Scheduled`. When requirements include multiple nodes, schedules durable across restarts, misfire policies, or cross-job dependency orchestration, a dedicated scheduler is usually more appropriate.

## 2. Components to Understand

### `Job`, `JobInstance`, and `JobExecution`

`Job` is the job definition, such as `dailySettlementJob`. In Spring Batch, **a `JobInstance` is identified by the job name and the set of `JobParameters` marked as identifying**. Each execution attempt of an instance is a `JobExecution`.

```text
Job: dailySettlementJob

JobParameters: businessDate=2026-11-16
                 |
                 v
       JobInstance for Nov 16
                 |
            JobExecution #1 (FAILED)
                 |
            JobExecution #2 (COMPLETED if restarted)
```

If you use new identifying parameters for each launch, Spring Batch treats it as a **new JobInstance**; in that case, running again is not a restart of the previous instance. If you run again with the same identifying parameters after the instance is `COMPLETED`, Spring Batch typically rejects it with `JobInstanceAlreadyCompleteException`. Both behaviors are especially important for periodically scheduled batch jobs.

### `JobLauncher` and `JobOperator`

In Spring Batch 5.x applications, `JobLauncher.run(job, jobParameters)` is the commonly used API to start a job. `JobOperator` provides higher-level operational actions such as start, stop, and restart. Method signatures and related packages vary across Spring Batch versions; consult the documentation matching your project's dependencies.

### `JobRepository`

`JobRepository` is the metadata store holding `JobInstance`, `JobExecution`, `StepExecution`, `ExecutionContext`, and status information. It supports launch-repeat control and restart. **It is not where cron schedules or missed trigger times are stored**; schedule persistence belongs to the chosen scheduler.

## 3. Cron Expressions in `@Scheduled`

Spring Framework supports **six-field** cron expressions, in order:

```text
 ┌──── second      (0-59)
 │ ┌── minute      (0-59)
 │ │ ┌ hour        (0-23)
 │ │ │ ┌ day       (1-31 or * / ?)
 │ │ │ │ ┌ month   (1-12 or JAN-DEC)
 │ │ │ │ │ ┌ weekday (0-7 or SUN-SAT; 0/7 is Sunday)
 │ │ │ │ │ │
 0 0 2 * * *
```

Typical schedules:

| Spring cron | Meaning |
| --- | --- |
| `0 0 2 * * *` | Daily at 02:00:00 |
| `0 */15 * * * *` | Every 15 minutes, at second 0 |
| `0 30 8 * * MON-FRI` | 08:30 Monday through Friday |
| `0 0 0 1 * *` | 00:00 on the first day of every month |
| `0 0 23 L * *` | 23:00 on the last day of every month, if the Spring cron version in use supports `L` |

**Note:** Linux cron typically has **five fields** (minute, hour, day, month, weekday), whereas Spring cron prepends **seconds**. Do not copy expressions between the two without checking syntax. A schedule like `0 0 2 * * *` means 02:00 daily in Spring, but is not a valid five-field Linux crontab expression.

### Specifying the Timezone

```java
@Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")
public void runEveryMorning() {
    // Trigger the job.
}
```

`zone` prevents the schedule from depending on the default timezone of the host running the application. Without it, the actual firing time can shift when a container or server moves to another timezone. In regions with daylight saving time (DST), skipped or repeated hours can cause the number of triggers to differ from intuition; define a business schedule policy rather than assuming every day has exactly 24 hours.

## 4. Example: Scheduling a Spring Batch Job with `@Scheduled`

The following example targets **Spring Boot 3.x + Spring Batch 5.x**, using Java 17+, Spring Scheduling, and `JobLauncher`. An illustrative job processing by `businessDate` is triggered daily at 02:00 Vietnam time.

### 4.1. Dependencies

With Gradle and the Spring Boot BOM properly configured:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    // Demo database to store BATCH_* metadata; production typically uses a persistent DB.
    runtimeOnly 'com.h2database:h2'
}
```

`@Scheduled` belongs to Spring Framework and is provided via the appropriate Spring starters; with a standard Spring Boot Batch setup, no separate scheduler library is needed for this example. H2 is for demonstration only. In production, you need a persistent metadata database consistent with transactions and the system's restart capability.

### 4.2. Enabling Scheduling

```java
package com.example.batch;

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

`@EnableScheduling` enables detection of `@Scheduled` methods in the Spring context. Without this annotation or an equivalent activation mechanism, methods annotated with `@Scheduled` will not run automatically on schedule.

### 4.3. Declaring the Job and Step

```java
package com.example.batch;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ImportJobConfiguration {
    private static final Logger log =
        LoggerFactory.getLogger(ImportJobConfiguration.class);

    @Bean
    public Job importOrdersJob(JobRepository repository, Step importOrdersStep) {
        return new JobBuilder("importOrdersJob", repository)
            .start(importOrdersStep)
            .build();
    }

    @Bean
    public Step importOrdersStep(JobRepository repository,
                                 PlatformTransactionManager transactionManager) {
        return new StepBuilder("importOrdersStep", repository)
            .tasklet((contribution, chunkContext) -> {
                String businessDate = contribution.getStepExecution()
                    .getJobParameters().getString("businessDate");

                if (businessDate == null || businessDate.isBlank()) {
                    throw new IllegalArgumentException(
                        "Missing job parameter: businessDate");
                }

                log.info("Processing orders for businessDate={}", businessDate);
                // Real application: use reader/processor/writer or call a service.
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
    }
}
```

`JobBuilder` and `StepBuilder` accept `JobRepository` directly, matching the configuration style in Spring Batch 5. The tasklet above only illustrates receiving `JobParameters`; it does not represent a full production data-ingestion pipeline.

### 4.4. Triggering the Job at the Configured Time

```java
package com.example.batch;

import java.time.LocalDate;
import java.time.ZoneId;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionException;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ImportOrdersScheduler {
    private static final Logger log =
        LoggerFactory.getLogger(ImportOrdersScheduler.class);

    private final JobLauncher jobLauncher;
    private final Job importOrdersJob;
    private final ZoneId zoneId;

    public ImportOrdersScheduler(
            JobLauncher jobLauncher,
            @Qualifier("importOrdersJob") Job importOrdersJob,
            @Value("${batch.orders.zone:Asia/Ho_Chi_Minh}") String zone) {
        this.jobLauncher = jobLauncher;
        this.importOrdersJob = importOrdersJob;
        this.zoneId = ZoneId.of(zone);
    }

    @Scheduled(
        cron = "${batch.orders.cron:0 0 2 * * *}",
        zone = "${batch.orders.zone:Asia/Ho_Chi_Minh}"
    )
    public void launch() {
        LocalDate businessDate = LocalDate.now(zoneId);

        JobParameters parameters = new JobParametersBuilder()
            .addString("triggerId", UUID.randomUUID().toString())
            .addString("businessDate", businessDate.toString(), false)
            .toJobParameters();

        try {
            JobExecution execution = jobLauncher.run(importOrdersJob, parameters);

            log.info("Started batch executionId={}, businessDate={}, status={}",
                execution.getId(), businessDate, execution.getStatus());

            if (execution.getStatus() != BatchStatus.COMPLETED) {
                log.error("Batch did not complete successfully: executionId={}, status={}",
                    execution.getId(), execution.getStatus());
                // Production: emit metrics/alerts and apply a retry policy.
            }
        } catch (JobExecutionException ex) {
            log.error("Unable to launch importOrdersJob for {}", businessDate, ex);
            // Production: record the failed trigger and alert operations.
        }
    }
}
```

Explanation:

1. `@Scheduled` specifies **when** to call `launch()`. To vary the schedule per environment, use the `batch.orders.cron` property instead of modifying Java code.
2. `@Qualifier("importOrdersJob")` selects the right `Job` bean when the application has multiple jobs.
3. `businessDate` is the business parameter; in this example it is marked `identifying=false`, while a random `triggerId` is the identifying parameter. Thus **each cron trigger is treated as a new JobInstance**. This is convenient for a demo, but does not satisfy *run once per business period* if multiple application instances are running.
4. `JobLauncher.run(...)` creates and executes the job. With the standard synchronous launcher, the method returns when the job has finished; with an asynchronously configured launcher, it may return as soon as the work starts. Therefore, you must not infer from the moment `launch()` returns that the job has always completed.
5. Not every step failure causes `JobLauncher.run(...)` to throw an exception. A job may return a `JobExecution` in `FAILED` status; therefore, inspect `BatchStatus`/`ExitStatus` and the execution's failure exceptions to record operational outcomes.
6. The `try/catch` here serves logging and alerting when launching fails. Bounded retry mechanisms, failed instance handling, and operational notifications must be designed separately.

### 4.5. Configuring `application.yml`

```yaml
spring:
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always # example only for test DB

batch:
  orders:
    cron: "0 0 2 * * *"
    zone: "Asia/Ho_Chi_Minh"
```

`spring.batch.job.enabled=false` **prevents Spring Boot from automatically running batch jobs at application startup**. Without this setting, in an environment with registered jobs, Boot could run the job once at startup in addition to the `@Scheduled` runs, causing unexpected processing.

`spring.batch.jdbc.initialize-schema=always` is a demonstration setting for test databases. In production, manage the `BATCH_*` schema via migrations or appropriate operational procedures; do not blindly enable automatic schema creation on a shared database.

**Important:** if the application is a process that runs a single job and exits, `@Scheduled` inside that process is not suitable. The scheduler must stay alive to wait for trigger times. For short-lived per-run batch processes, use cron/Kubernetes CronJob or an external orchestrator to start the process at the right time.

## 5. How Do Cron, `fixedRate`, and `fixedDelay` Differ?

Spring supports several `@Scheduled` forms:

```java
// Wall-clock schedule: 02:00 daily in the specified timezone.
@Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")
public void cronTrigger() { /* launch job */ }

// Periodic interval measured from scheduled start times.
@Scheduled(fixedRate = 300_000)
public void fixedRateTrigger() { /* launch job */ }

// Wait 5 minutes after the previous invocation finishes before calling again.
@Scheduled(fixedDelay = 300_000)
public void fixedDelayTrigger() { /* launch job */ }
```

| Mechanism | How the next run is determined | Suitable scenarios |
| --- | --- | --- |
| `cron` | Specific wall-clock time/date on the calendar | Daily reports, end-of-day closing, month-end |
| `fixedRate` | Fixed interval between scheduled start times | Regular polling, short tasks, watch out for overlap |
| `fixedDelay` | Pause after the **method finishes executing** | Repeated processing needing spacing after each completion |

With `fixedDelay`, if the method only **submits a job to an asynchronous executor and returns immediately**, the delay is measured after the *submission method* finishes, **not** after the batch job itself finishes. Similarly, `fixedRate` or cron does not automatically guarantee the old job has finished before the new one starts.

Even when the scheduler runs on a single thread, that only keeps `@Scheduled` invocations within the same process from overlapping at the method level. You should not rely on it to guarantee that two `JobExecution`s never run concurrently across application instances or after an asynchronous launch.

## 6. Designing `JobParameters` by Run Period

Batch scheduling is usually tied to a **data period**: transaction date, reporting month, `windowStart/windowEnd`, or input file ID. What matters is not only what time the trigger fires, but also **which period's data** the job is asked to process.

### Approach A: Each Trigger Is an Independent Job Instance

```java
JobParameters params = new JobParametersBuilder()
    .addString("triggerId", UUID.randomUUID().toString())
    .addString("businessDate", "2026-11-16", false)
    .toJobParameters();
```

Advantage: the scheduler can launch a new run without colliding with a completed instance. Limitation: if two triggers run for the same `businessDate`, Spring Batch treats them as **two instances** and may still reprocess the same data. Preventing duplicates requires idempotency at the business or orchestration layer.

### Approach B: Business Period Identifies the Job Instance

```java
JobParameters params = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16") // identifying by default
    .toJobParameters();
```

With a fixed job name, the date `2026-11-16` identifies a single unique instance. If the job succeeds, another launch request with the same parameters may be rejected as already completed. If the previous job failed or stopped and is restartable, running with the same identifying parameters can create a **new JobExecution belonging to the same JobInstance**. This policy fits use cases that process one data period and require rerun control.

**Restart note:** do not automatically add a `UUID` to identifying parameters when the goal is to **resume a failed run**. Adding a UUID switches to a different JobInstance and may cause already-processed data to be processed again. A *rerun from scratch* after completion also differs from a *restart from checkpoint*; operations must clearly distinguish the two.

### Determining the Business Date

Not every job running at 02:00 on Nov 17 processes Nov 17 data. For example, an after-midnight closing job may process **the previous day**:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate businessDate = LocalDate.now(zone).minusDays(1);
```

The rule for choosing `businessDate` should be based on the data contract and business cutoff. For backfill runs, pass the date or time range **explicitly** via parameters rather than relying solely on `LocalDate.now()`, which would produce the wrong period when run the next day.

## 7. Preventing Two Overlapping Batch Runs

A job that takes 90 minutes on an hourly trigger can produce two concurrent runs. Consequences can include duplicate input reads, table locks, overwritten outputs, or checkpoint contention.

```text
01:00  Job A starts ──────────────────────────> 02:30 finishes
02:00  Next trigger ───────> Job B starts ?
                            |
                Requires a concurrency policy
```

There are four common strategies:

1. **Skip trigger while running:** suitable when new data can be processed in the next period; clearly log the skipped period and monitor backlog.
2. **Queue:** the new trigger is held to run after the old job completes; bound the queue length and account for catch-up behavior.
3. **Controlled parallel execution:** only when each execution processes independent data/partitions and the writer, database, and output paths are concurrency-safe.
4. **Reject duplicate period runs:** use consistent identifying `JobParameters` for the same period along with appropriate scheduling/locking; avoid generating a new UUID per node if the goal is to process each period exactly once.

In a multi-instance application, `@Scheduled` on each instance can **invoke the same method on every node**. `JobRepository` can help prevent two concurrent executions of the *same JobInstance*, but it does not automatically prevent two runs with different `JobParameters`. Furthermore, it is not a cluster-wide trigger election system. When you need to guarantee only one node orchestrates at a time, use a distributed scheduler such as Quartz JDBC clustering, an orchestrator that emits a single trigger, or a distributed lock with a lease timeout and dead-process handling.

You can observe running jobs via `JobExplorer` (for example `findRunningJobExecutions(jobName)` in the version's corresponding API). However, **check-then-launch** consists of two separate operations and is subject to race conditions if multiple nodes check simultaneously; status checks alone are therefore insufficient for exactly-once guarantees.

### Exactly-Once and Idempotency

Running on schedule once does not mean data is affected only once. The scheduler may retry after a network error, the job may be restarted, and the same message/file may be reprocessed. Design idempotency using business keys, unique constraints, period-run state, or appropriate upsert logic. For output files, write to a temporary file and publish the final result in a controlled manner to avoid exposing partial files.

## 8. What Happens When the Application Shuts Down at Trigger Time?

`@Scheduled` is **in-process scheduling inside a running application**. If the application is down at 02:00, it does not automatically record the missed trigger to guarantee a catch-up run when starting up at 03:00. After restart, the scheduler simply continues computing future trigger times from the configuration. Spring Batch metadata also only knows about executions that were actually created.

This leads to three operational requirements:

- Maintain a **record of data periods due for processing** (for example a `batch_schedule_period` table) or a source of truth for due periods.
- Have a **reconciliation/catch-up** mechanism to detect incomplete periods and issue catch-up requests with the exact parameters.
- Have dashboards/alerts based on **expected business periods**, not just counting executions that occurred. If an execution never happened at all, a dashboard watching only `JobRepository` might miss it.

If you need durable triggers and misfire policies, Quartz JDBC JobStore or an external scheduler platform is more suitable. They can persist pending triggers and decide post-downtime handling according to configuration; catch-up policies must still match the specific data semantics.

## 9. Choosing the Right Scheduling Tool

### 9.1. Spring's `@Scheduled`

Suitable for continuously running Spring applications, single-node or already coordinated externally, with relatively simple schedules. Easy to code, externalize cron in properties, and share the Spring context with `Job` beans.

Limitations: triggers live in memory; no durable schedule table, trigger management UI, or built-in cluster/leader election. Changing cron typically requires updating configuration and refreshing/redeploying the application.

### 9.2. Quartz Scheduler

Quartz supports cron triggers, calendars, misfire instructions, persistent job/trigger stores, and clustering when properly configured. You can create a Quartz `Job` adapter that maps `JobDataMap` to `JobParameters` and then invokes the Spring Batch launcher/operator.

```text
Quartz Trigger -> Quartz Job adapter -> Spring Batch Job
       |                                    |
Quartz JobStore                    Spring Batch JobRepository
```

**The two repositories have distinct responsibilities:** Quartz stores schedules/triggers and scheduler state; Spring Batch stores execution metadata, checkpoints, and restart state. Do not use Quartz `JobDataMap` as a substitute for Batch `ExecutionContext`, and do not treat `JobRepository` as Quartz's cron store.

### 9.3. Kubernetes CronJob

Suitable when batch work is packaged in a container that runs to completion and exits. Kubernetes creates a Kubernetes Job/Pod for each scheduled run, and the application inside the Pod runs **one batch job** and exits. Options like `concurrencyPolicy`, schedule, job history limits, and deadlines help orchestrate the process. To prevent overlapping runs of the **same CronJob**, you can set `concurrencyPolicy: Forbid`.

Illustrative infrastructure configuration example:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: import-orders
spec:
  schedule: "0 2 * * *" # Kubernetes cron: 5 fields
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: import-orders
              image: example/import-orders:1.0.0
              args: ["--spring.batch.job.name=importOrdersJob"]
```

The YAML sample only illustrates scheduling; the image must exist, and the application must run the job on container startup and exit with an appropriate exit code. The property/entrypoint used to select the job also depends on the Spring Boot version and how the app launches batches; if the app sets `spring.batch.job.enabled=false`, the launch entrypoint must be adapted for the CronJob model. In this model, do not also add `@Scheduled` for the same job, as it could trigger twice.

Kubernetes CronJob supports timezones via `.spec.timeZone` on Kubernetes versions that provide it; Kubernetes' `schedule` expression has **five fields**, unlike Spring's six-field expression.

### 9.4. OS Cron and Orchestration Platforms

Linux cron can invoke a command or script that launches the batch application. Airflow, Control-M, and similar orchestrators are useful when you need DAGs, cross-job dependencies, complex business calendars, cross-system observability, and date-range backfills. Regardless of the tool chosen, Spring Batch remains responsible for processing and persisting execution metadata.

| Option | Key strengths | Things to watch out for |
| --- | --- | --- |
| `@Scheduled` | Minimal components, fits long-running apps | No durable triggers or cluster coordination out of the box |
| Quartz | Flexible triggers, JDBC store, misfire handling, clustering | Requires separate Quartz configuration, storage, and operations |
| Kubernetes CronJob | Integrates cleanly with container deployments, spawns Pods on schedule | Job must run-and-exit; must handle missed schedules, concurrency, and parameters |
| OS cron | Simple for standalone scripts/jobs | Error tracking, retries, logs, and multi-host runs must be organized separately |
| Orchestrator | Manages dependencies, period-based data, and backfills | Higher infrastructure and operational complexity |

## 10. Error Handling, Retry, and Restart with Scheduling

When the scheduler fires successfully but a step encounters an error, you have a **failed job execution**. When the scheduler cannot invoke the launcher, that is a **launch failure**. When the process is down at trigger time, that is a **missed run**. These three cases require different handling policies.

### Errors During Job Execution

If a job is `FAILED`, inspect `StepExecution` and failure exceptions to diagnose the root cause. For transient item-level errors, Spring Batch's step-level `retry` policy is one option. For errors that fail the entire job, decide when to restart and whether previously committed data can be safely resumed.

### Restart vs. New Run

In Spring Batch, **restart** resumes a `JobInstance` from its previous state based on metadata and step configuration. To restart the right instance, preserve the repository/context and use the matching identifiers; `JobOperator.restart(executionId)` can be used in supported versions. Calling `run(...)` with a new `triggerId` creates a **new instance**, even for the same business date.

### Scheduler-Layer Retries

The scheduler may retry after a delay if launching fails due to infrastructure issues. However, retries must not automatically create a new `JobInstance` and duplicate data processing. For period-based schedules, record incomplete periods and explicitly choose either `restart` or an intentional new run.

### Stopping or Exceeding Processing Time

Monitor duration and set alert thresholds if a job runs longer than normal. When a batch job must be stopped safely, use Spring Batch's stop mechanism and let steps respond; killing a Pod/process can prevent a clean shutdown, so checkpoints and idempotency must be designed to recover on rerun.

## 11. Timestamps, Data Periods, and Business Calendars

Example of a job running at 02:00 AM, processing the previous day's transactions:

```text
Runtime date:            2026-11-17, 02:00 Asia/Ho_Chi_Minh
Business period:         2026-11-16, 00:00 to end of day
Input:                   orders/businessDate=2026-11-16/
Output:                  settlement/2026-11-16.csv
JobParameters:           businessDate=2026-11-16
```

Clearly separate:

- **Trigger time:** when the scheduler fires.
- **Execution time:** when the job actually starts and finishes; may lag behind trigger time while waiting for resources.
- **Business date/window:** the data interval the job processes; may be yesterday, last week, or a backlogged window.

For financial, inventory reconciliation, or reporting batches, do not derive the data period from the job's completion time. If a job starts late across midnight, that inference could shift the period mid-run. Compute the period when building parameters or accept it from the orchestrator and pass it immutably to the execution.

When business operations follow business days only, a Monday–Friday cron is not enough to exclude public holidays or special non-working days. Use a managed business calendar or business-day calculation service and check before launching. During backfill, allow specifying the target period explicitly rather than defaulting to the server's current date.

## 12. Monitoring Schedules and Job Status

A schedule has operational value when it can answer: **which runs should have happened, which ones actually happened, and what were the results?**

Fields worth observing:

| Attribute | Meaning |
| --- | --- |
| `jobName` | Scheduled job |
| `businessDate` or `windowStart/windowEnd` | Data period processed |
| `scheduledAt` | Planned trigger timestamp |
| `launchedAt` | Time the launcher was called |
| `executionId` | `JobExecution` identifier in `JobRepository` |
| `BatchStatus`, `ExitStatus` | Batch status and exit code |
| Start/end time, duration | Detect slow, hung, or SLA-breaching jobs |
| Read/write/filter/skip counts | Track data validity and quality |
| Failure exception | Aid investigation and failure classification |

At a minimum, alert on: overdue data period with **no execution**, `FAILED`/`STOPPED` execution, excessively long execution, abnormal skip rate, or missing output. Log `jobName`, `businessDate`, and `executionId` to correlate scheduler and Spring Batch records. For monitoring, use Micrometer/Actuator as configured for your application; do not rely solely on logs when tracking SLAs.

## 13. Testing Scheduling Mechanisms

Testing can be split into three scopes so you never have to wait for the wall clock to reach cron time:

1. **Test parameter-preparation logic:** call the `businessDate` calculation service directly, verifying timezones, previous day, month-end, or backfill cases. Inject a fixed `Clock` so results do not depend on real time.
2. **Test trigger code:** call the launcher method/service directly with a mocked `JobLauncher` and assert the exact `Job`, name, and identifying parameters passed; no need to wait until 02:00.
3. **Batch job integration test:** run the real job in Spring Test with test database/files, asserting `JobExecution`, output data, and restart behavior. This tests the processing logic independently of whether cron fired on time.

To test the cron expression itself, use Spring's version-appropriate scheduling APIs (such as `CronExpression` in Spring Framework) to compute next fire times from a known instant. Also test timezones, month-end dates, and DST transitions if the timezone observes DST.

## 14. Common Mistakes

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Job runs immediately at startup before scheduled time | Spring Boot auto-launches `Job` on startup | Check `spring.batch.job.enabled=false` in `@Scheduled` setups |
| `@Scheduled` method does not run | Missing `@EnableScheduling`, bean not in Spring context, or invalid cron | Enable scheduling, check component scan and properties |
| Batch runs at the wrong hour | Using default host/container timezone or mixing up 5/6-field cron | Specify zone explicitly, verify Spring cron syntax |
| Job runs multiple times for the same period | Multiple nodes running `@Scheduled`, trigger retries, or random parameters | Use data period as identifier where appropriate, distributed scheduler, and idempotency |
| `JobInstanceAlreadyCompleteException` | Same job name and identifying parameters already `COMPLETED` | Decide whether to skip, run a new period, or intentionally rerun |
| `JobExecutionAlreadyRunningException` | Same `JobInstance` is still running | Define clear overlap policy, avoid launching duplicate instances |
| Job reports `FAILED` but scheduler catches no exception | Launcher can return a `JobExecution` in failed state | Inspect `BatchStatus`/`ExitStatus`, log, and alert |
| Missed runs during service downtime | `@Scheduled` does not persistently store missed triggers | Add reconciliation or use a durable scheduler |
| `fixedDelay` still allows two concurrent jobs | Asynchronous launcher returns before job finishes | Manage concurrency at the execution level, not just the method level |
| Job does not restart from the right point | Identifying parameters changed or metadata/context not preserved | Design JobInstance per period, use persistent repository and restart API |
| Job processes the wrong date after midnight | Calling `LocalDate.now()` inside a step at a different time than the trigger | Pass `businessDate` explicitly in JobParameters |

## 15. Sample Operational Scenario

Suppose a system needs to aggregate the previous day's transactions daily at 02:00:

```text
Scheduler               Orchestrator                 Spring Batch
   |                       |                            |
   | 02:00: trigger        |                            |
   |---------------------->|                            |
   |                       | businessDate = yesterday   |
   |                       | check if period processed? |
   |                       |--------------------------->|
   |                       |         launch             |
   |                       |                            | read/process/write
   |                       |                            | commit/checkpoint
   |                       |<---------------------------|
   |                       | JobExecution + status      |
   |                       |                            |
   |                       | record / alert             |
```

To enforce **exactly one result per day**, in practice you should design three additional pieces: (1) a table or rule defining periods to process, (2) per-period job instance identification or an equivalent coordination lock, and (3) a process to detect missing periods and backfill them. If a job fails, it can be restarted using metadata and checkpoints; if completed data needs to be reprocessed, you need a controlled rerun mechanism that guarantees output is not duplicated.

Thus, batch scheduling is not merely a cron string. A reliable schedule connects **trigger timing, data periods, identifying parameters, overlap policies, failure recovery, and observability** to Spring Batch's exact responsibilities.

## References

- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@EnableScheduling`, `@Scheduled`, cron, fixed rate, and fixed delay.
- [Spring Framework API — `CronExpression`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/support/CronExpression.html): six-field cron syntax and computing next execution times.
- [Spring Batch Reference](https://docs.spring.io/spring-batch/reference/): `Job`, `JobInstance`, `JobExecution`, `JobParameters`, `JobRepository`, and restart model.
- [Spring Boot Reference — Spring Batch](https://docs.spring.io/spring-boot/reference/io/spring-batch.html): configuring job startup execution and Batch infrastructure.
- [Quartz Scheduler Documentation](https://www.quartz-scheduler.org/documentation/): triggers, job stores, clustering, and misfire handling.
- [Kubernetes Documentation — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/): scheduled cron, timezones, and concurrency policies for containerized workloads.
