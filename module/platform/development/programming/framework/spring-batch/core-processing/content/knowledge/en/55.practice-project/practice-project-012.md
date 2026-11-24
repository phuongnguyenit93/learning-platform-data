# Scheduling a Spring Batch Job: A Practice Project from Configuration to Operations

In a Spring Batch application, running a `Job` manually in an IDE is only the first step. In production, jobs usually need to **launch automatically on a schedule**, such as 02:15 daily to import the previous day's orders, 05:00 to reconcile transactions, or at month-end to export reports. The challenge is more than writing a cron expression: the system must also know **which job to run**, **which data period**, **what to do if the job already ran**, **how to prevent duplicate triggers**, **how to handle missed schedules**, and **how to monitor outcomes**.

This practice project builds a Spring Boot application that runs `importOrders` on a schedule. We use `@Scheduled` to trigger, `JobLauncher` to launch, `JobParameters` to identify the business period, and `JobRepository` to persist execution metadata. We then compare with Quartz, Kubernetes CronJobs, and external schedulers to know when to move to a more durable solution.

**API baseline:** Java examples target **Spring Batch 5.2.x, Spring Boot 3.4+/3.5.x, and Java 17**. Code snippets focus on scheduling, so the business step is illustrated with a `Tasklet`; in real projects, replace it with a chunk step using `ItemReader`/`ItemProcessor`/`ItemWriter`. Never mix Spring Batch 5.x code with Spring Batch 6.x imports/APIs without cross-checking.

## 1. Understanding Three Components Before Scheduling

A batch job is triggered by a **scheduler**, yet its execution is managed by **Spring Batch**.

```text
                 Clock / Cron / Event
                          |
                          v
                       Scheduler
             (decides WHEN to run)
                          |
                          v
                    Launch service
          (selects job, builds JobParameters)
                          |
                          v
                      JobLauncher
               (starts JobExecution)
                          |
              +-----------+-----------+
              |                       |
              v                       v
          Job/Step               JobRepository
       (business logic)     (metadata, status,
                                checkpoint)
              |
              v
          JobExecution
      (COMPLETED/FAILED/...)
                          |
                          v
                  Logs / Dashboard
```

| Component | Answers Question | What Should It Not Own? |
| --- | --- | --- |
| `@Scheduled`/`TaskScheduler`/Quartz/CronJob | **When** to trigger? | Does not replace Batch transactions and checkpoints |
| `JobLauncher` | Which `Job` and `JobParameters` to start executing? | Does not decide business schedules |
| `Job` and `Step` | Data processing, execution state, retry/skip/restart? | Does not store the schedule of which days it must run |
| `JobRepository` | Which instances/executions have been recorded? | Does not know a period "should have run" if no execution was ever created |
| `JobExplorer` | Read history/status from the repository | Does not prove a worker is alive merely because status is `STARTED` |
| Orchestrator/SLA registry | Which periods are expected, deadlines, and dependencies? | Does not automatically undo committed business side effects |

**Principle:** The scheduler only issues the launch command; `JobRepository` is the source of truth for existing executions. If the scheduler fails to fire, there may be **no failure record in the repository**. Thus production also needs *missing-run* monitoring, not only `FAILED` monitoring.

## 2. Practice Project Requirements

Assume an `importOrders` workflow:

- Daily at **02:15** in timezone `Asia/Ho_Chi_Minh`, process **the previous day's** orders.
- Job name is `importOrders`; `businessDate` identifies the processed data period.
- For a period already `COMPLETED`, another cron trigger **must not re-ingest duplicates**.
- If the previous run `FAILED` and restart conditions permit, the next run with the **same identifying parameters** is handled under the restart policy.
- Do not auto-run the job when Spring Boot starts merely because the context holds a `Job` bean.
- Logs include `businessDate`, `jobExecutionId`, and status; provide guidance for monitoring, backfill, and error handling.
- Local config uses H2 for easy testing; production requires a persistent metadata database (typically PostgreSQL or an organization-supported database).

Practice scope:

```text
src/main/java/com/example/batch/
    BatchSchedulerApplication.java
    config/BatchClockConfig.java
    config/ImportOrdersJobConfig.java
    service/ImportOrdersLaunchService.java
    schedule/ImportOrdersSchedule.java

src/main/resources/
    application.yml

src/test/java/com/example/batch/
    ImportOrdersLaunchServiceTest.java
```

We implement piece by piece. In the example, the step only logs; the goal is to observe how the scheduler and Batch coordinate. When connecting real data, replace the tasklet body with a reader/processor/writer configured with proper transactions and idempotency.

## 3. Dependencies and Spring Boot Configuration

Gradle example using Spring Boot dependency management already in the project:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The `spring-boot-starter-batch` dependency provides Spring Batch infrastructure, and `spring-boot-starter-jdbc` supports datasource/JDBC and transactions. Some dependencies may already be pulled in transitively by the Batch starter; the snippet explicitly lists components used here. H2 is suitable only for demos/tests; in production, swap in a JDBC driver and an operated/backed-up database.

Configuration in `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: orders-batch

  datasource:
    url: jdbc:h2:mem:ordersbatch;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""

  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

app:
  batch:
    import-orders:
      cron: "0 15 2 * * *"
      zone: "Asia/Ho_Chi_Minh"
```

Two key properties:

- `spring.batch.job.enabled=false`: disables Spring Boot's automatic job execution at application startup. **It does not disable the `Job` or `JobLauncher` beans**. Our scheduler will invoke `JobLauncher` explicitly.
- `spring.batch.jdbc.initialize-schema=always`: creates Spring Batch metadata tables in demo H2 when the app starts. **Do not blindly use `always` on production databases**, where schemas must be managed and upgraded via controlled migrations.

In-memory H2 **does not retain metadata after the JVM exits**. Thus the demo can show cron triggers and `JobInstanceAlreadyCompleteException` within a single application run, yet **cannot verify restarts across a fresh JVM startup**. Testing durable restarts requires a repository backed by persistent storage.

### Spring Boot Auto-Run and Scheduler Are Two Separate Mechanisms

Do not enable `spring.batch.job.enabled=true` and also attach `@Scheduled` to the same job if the goal is to run strictly on schedule. That can run the job **once at startup** and **repeatedly on cron**, causing duplicate triggers or unexpected data-period parameters.

This lesson uses Spring Boot's Batch auto-configuration; **do not add `@EnableBatchProcessing`** merely to make the scheduler work. In Spring Boot 3.x, adding that annotation can change Batch auto-configuration scope, so use it only when intentionally configuring infrastructure manually.

## 4. Enabling Scheduling in the Application

Create the entry point:

```java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class BatchSchedulerApplication {

    public static void main(String[] args) {
        SpringApplication.run(BatchSchedulerApplication.class, args);
    }
}
```

`@EnableScheduling` allows Spring to process `@Scheduled` methods on beans managed by the application context. It does not need or know about Spring Batch upfront; it is a Spring Framework capability.

If the application has multiple scheduled tasks, pay attention to the scheduler thread pool. A default schedule may run on a limited number of threads; if one job runs synchronously for hours, other tasks may be delayed. Declare a scheduler pool when multiple schedules are genuinely needed:

```yaml
spring:
  task:
    scheduling:
      pool:
        size: 4
      thread-name-prefix: "batch-schedule-"
```

This configuration allows multiple scheduled invocations to run more concurrently at the scheduler layer; **it does not mean `JobRepository` allows the same `JobInstance` to run concurrently**. Add overlap prevention policies; never increase pool size as a fix for delayed jobs when the database itself is bottlenecked.

## 5. Cron Expressions and Timezones

Spring `@Scheduled` uses **6-field** cron expressions (the first field is **seconds**):

```text
second minute hour day-of-month month day-of-week
   0      15    2       *        *         *
```

Examples:

| Spring Cron | Interpretation |
| --- | --- |
| `0 15 2 * * *` | 02:15 daily |
| `0 0 6 * * MON-FRI` | 06:00 Monday through Friday |
| `0 30 23 L * *` | 23:30 on the last day of the month (if parser version supports `L`) |
| `0 0 */4 * * *` | Top of every four hours |
| `0 0 3 1 * *` | 03:00 on the first day of the month |

**Do not confuse 5-field Linux/Kubernetes cron with 6-field Spring cron.** Linux `15 2 * * *` corresponds to Spring `0 15 2 * * *`.

Always choose the timezone per business rules. In the example:

```java
@Scheduled(
        cron = "${app.batch.import-orders.cron}",
        zone = "${app.batch.import-orders.zone}")
```

`zone` controls how the schedule is interpreted; it does not automatically control how the application computes `businessDate`. To align both, create a `Clock` in that exact timezone.

Vietnam currently has no DST transitions, yet if deploying schedules in a DST region, times like 02:15 may **not exist** or **occur twice** on transition days. Schedules, deadlines, and business dates need explicit rules; never assume every "day" is exactly 24 hours long.

## 6. Creating a `Clock` for Consistent Business Date Calculation

Instead of calling `LocalDate.now()` in the JVM's default timezone, inject a configured `Clock`:

```java
package com.example.batch.config;

import java.time.Clock;
import java.time.ZoneId;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BatchClockConfig {

    @Bean
    public Clock batchClock(
            @Value("${app.batch.import-orders.zone}") String zone) {
        return Clock.system(ZoneId.of(zone));
    }
}
```

When cron runs at 02:15 on Nov 16 in Vietnam:

```text
LocalDate.now(batchClock) = 2026-11-16
businessDate = 2026-11-15
```

Using `Clock` also facilitates testing with `Clock.fixed(...)`, independent of the CI machine's current date. In production, "previous day" may be replaced by a **business calendar** if the system handles business days, banking days, or holidays. For example, Monday may need to reconcile the preceding Friday; `minusDays(1)` does not fit every domain.

## 7. Creating the Sample `Job` and `Step`

Create `ImportOrdersJobConfig` to run a simple `Tasklet` step. In real projects, replace the tasklet with a chunk-oriented step reading, validating, and writing orders to the database.

```java
package com.example.batch.config;

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
public class ImportOrdersJobConfig {

    private static final Logger log =
            LoggerFactory.getLogger(ImportOrdersJobConfig.class);

    @Bean
    public Step importOrdersStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager) {

        return new StepBuilder("importOrdersStep", repository)
                .tasklet((contribution, context) -> {
                    String businessDate =
                            contribution.getStepExecution()
                                    .getJobParameters()
                                    .getString("businessDate");

                    log.info("Importing orders for businessDate={}",
                            businessDate);

                    // Demo: replace with real data processing in the project.
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }

    @Bean
    public Job importOrdersJob(
            JobRepository repository,
            @Qualifier("importOrdersStep") Step step) {

        return new JobBuilder("importOrders", repository)
                .start(step)
                .build();
    }
}
```

In the code:

- The Spring bean is named `importOrdersJob`, whereas the Batch job's **logical name** is `importOrders` (from `JobBuilder("importOrders", ...)`).
- `StepBuilder("importOrdersStep", repository)` creates the step, and `tasklet(..., transactionManager)` provides the step's transaction manager.
- `businessDate` is read from the execution's `JobParameters`. Never read `LocalDate.now()` directly inside the tasklet to decide which data to process, because on a restart on another day, the step must process the **same period**.
- A tasklet does not prove item-level restarts. With file readers/DB writers, design `ItemStream`/`ExecutionContext` and transactions/idempotency per data source.

This assumes the project has exactly one `JobRepository` and one transaction manager configured by Boot. With multiple datasources or transaction managers, use explicit `@Qualifier`s and check whether business data and metadata share a transaction.

## 8. Separating Job Launching from the Scheduler Layer

Do not put all logic inside a `@Scheduled` method. Create a service taking the **business date** so cron, CLIs, internal endpoints, or external orchestrators can share it without arbitrarily altering `JobParameters`.

```java
package com.example.batch.service;

import java.time.LocalDate;
import java.util.Objects;

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
import org.springframework.stereotype.Service;

@Service
public class ImportOrdersLaunchService {

    private final JobLauncher jobLauncher;
    private final Job importOrdersJob;

    public ImportOrdersLaunchService(
            JobLauncher jobLauncher,
            @Qualifier("importOrdersJob") Job importOrdersJob) {
        this.jobLauncher = jobLauncher;
        this.importOrdersJob = importOrdersJob;
    }

    public static JobParameters parametersFor(LocalDate businessDate) {
        Objects.requireNonNull(businessDate, "businessDate");

        return new JobParametersBuilder()
                .addString("businessDate",
                        businessDate.toString(), true)
                .addString("triggerSource", "scheduler", false)
                .toJobParameters();
    }

    public JobExecution launch(LocalDate businessDate)
            throws JobExecutionAlreadyRunningException,
                   JobRestartException,
                   JobInstanceAlreadyCompleteException,
                   JobParametersInvalidException {

        return jobLauncher.run(
                importOrdersJob,
                parametersFor(businessDate));
    }
}
```

**Why is only `businessDate` an identifying parameter in the example?** Each business date corresponds to one logical unit of work. If cron triggers twice for the same date, both requests target the same `JobInstance` and the repository can reject already-completed/running cases. `triggerSource` is tracking information and does not alter identity.

Do not add `System.currentTimeMillis()`, UUIDs, or an identifying `run.id` on every schedule trigger if the intent is to **restart or prevent duplicate runs for the same period**. Those parameters create a new `JobInstance` on every trigger, preventing the repository from enforcing "this instance is already `COMPLETED`."

If business rules allow **re-running a date with a new source data version**, design `sourceVersion`/`importVersion` as an additional identifying parameter **with business meaning**, paired with rules ensuring the writer does not create duplicate data. Never use random parameters to mask recovery errors.

## 9. Triggering from `@Scheduled`

Create the component bridging cron to the launch service:

```java
package com.example.batch.schedule;

import java.time.Clock;
import java.time.LocalDate;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.repository.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRestartException;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import com.example.batch.service.ImportOrdersLaunchService;

@Component
public class ImportOrdersSchedule {

    private static final Logger log =
            LoggerFactory.getLogger(ImportOrdersSchedule.class);

    private final ImportOrdersLaunchService launchService;
    private final Clock clock;

    public ImportOrdersSchedule(
            ImportOrdersLaunchService launchService,
            Clock batchClock) {
        this.launchService = launchService;
        this.clock = batchClock;
    }

    @Scheduled(
            cron = "${app.batch.import-orders.cron}",
            zone = "${app.batch.import-orders.zone}")
    public void startDailyImport() {
        LocalDate businessDate = LocalDate.now(clock).minusDays(1);

        try {
            JobExecution execution =
                    launchService.launch(businessDate);

            log.info("Submitted importOrders: date={} " +
                            "jobExecutionId={} status={}",
                    businessDate,
                    execution.getId(),
                    execution.getStatus());

        } catch (JobInstanceAlreadyCompleteException ex) {
            log.info("importOrders already completed for date={}",
                    businessDate);

        } catch (JobExecutionAlreadyRunningException ex) {
            log.warn("importOrders already running for date={}",
                    businessDate);

        } catch (JobRestartException
                 | JobParametersInvalidException ex) {
            log.error("Cannot start importOrders for date={}",
                    businessDate, ex);

        } catch (Exception ex) {
            // Keep diagnostic logging for unexpected runtime/infrastructure errors.
            log.error("Unexpected scheduler launch failure: date={}",
                    businessDate, ex);
        }
    }
}
```

When running the application via `BatchSchedulerApplication`:

1. Spring boots the context and configures `JobRepository`, `JobLauncher`, `Job`, and step.
2. `spring.batch.job.enabled=false` prevents Spring Boot from auto-running the job at startup.
3. `@EnableScheduling` activates scheduling infrastructure.
4. At 02:15 `Asia/Ho_Chi_Minh`, Spring invokes `startDailyImport()`.
5. The schedule class computes the business date and calls `ImportOrdersLaunchService.launch(...)`.
6. `JobLauncher` creates or resumes an execution matching repository state and job configuration.
7. Logs include `businessDate`/`jobExecutionId`; final status is read from `JobRepository`/`JobExplorer`.

**An important point:** the log word "Submitted" is intentional. `JobLauncher` can run **synchronously or asynchronously** depending on `TaskExecutor` and configuration. If asynchronous, the returned `JobExecution` may still be `STARTING` or `STARTED`; logging "Submitted" **must not be interpreted as "job succeeded."**

With a synchronous launcher, the call inside `@Scheduled` may wait until the job completes and occupy a scheduler thread the whole time. With an asynchronous launcher, the schedule method returns early, yet another mechanism is needed to track the final execution. Both cases require overlap-prevention policies and status monitoring.

### Why Catch Each Exception Type?

| Exception | Operational Message | What to Do |
| --- | --- | --- |
| `JobInstanceAlreadyCompleteException` | Same `JobInstance` already completed | Treat as valid duplicate trigger or event to monitor; do not auto-rerun |
| `JobExecutionAlreadyRunningException` | Repository records an active execution | Do not launch duplicate; check liveness if status lingers too long |
| `JobRestartException` | Cannot restart per Job/Step/metadata rules | Check status, restartability, and `ExecutionContext` |
| `JobParametersInvalidException` | Parameters failed validation | Fix date/input calculation logic; avoid blind retries |
| Other DB/infrastructure error | Failed to create or coordinate execution as expected | Alert, inspect metadata DB, transactions, and dependencies |

In production, have dedicated alerts/events for critical launch errors. If you only catch and log without a log-monitoring system, the scheduler can miss an entire period without operators noticing.

## 10. Restart, Rerun, and Backfill Are Three Distinct Operations

**Restart:** a `FAILED` or `STOPPED` job is relaunched with identifying parameters belonging to the **same `JobInstance`** to resume from metadata.

**Rerun with a new instance:** the business intentionally creates a different logical processing run, such as a new input source version. Clearly define whether old data is replaced, merged, or kept versioned.

**Backfill:** running missing historical periods, such as Nov 10 through Nov 15. Backfilling may be a restart, a new instance, or skipping already-completed periods depending on metadata.

```text
Business date 2026-11-15
    |
    +-- JobInstance A
          |
          +-- Execution 100 FAILED
          +-- Execution 101 COMPLETED (restart)

Business date 2026-11-14
    |
    +-- JobInstance B
          |
          +-- Execution 102 COMPLETED (backfill missing period)

Business date 2026-11-15, sourceVersion=v2
    |
    +-- JobInstance C, if sourceVersion is identifying
          |
          +-- Execution 103 COMPLETED (rerun new version)
```

A "daily at 02:15" cron does not automatically replay schedules **missed while the application was down**. After 3 days of downtime, cron simply fires at the next tick and computes "yesterday"; the intervening days may have no `JobExecution`s at all.

To support backfills, design an entry point accepting an **explicit** `businessDate`, allow only authorized operators to trigger it, check historical status, and decide whether restart or manual recovery applies. Never use the current date when the job receives an explicit backfill date.

## 11. Choosing the Right Scheduler

@Scheduled is convenient, yet it is not the only solution.

| Solution | Suitable When | Limitations / Additions Needed |
| --- | --- | --- |
| **Spring `@Scheduled`** | One long-running service, few schedules, simple schedules, single scheduler instance | Does not persist misfires/missed ticks, no persistent job triggers, no built-in cluster coordination |
| **Spring `TaskScheduler`** | Need dynamic scheduling/adjustable triggers in-app | Schedules and state must be self-persisted to survive restarts |
| **Quartz with JDBC `JobStore`** | Many schedules, misfire policies, persistent triggers, cluster coordination | Must administer Quartz tables, trigger/job details, and mapping to Batch |
| **Kubernetes `CronJob`** | Batch container runs once and exits; Kubernetes manages schedule | Separate Pod/process lifecycle; CronJob does not replace Batch metadata/checkpoints |
| **Linux cron / systemd timer** | Simple CLI job on a managed host | Needs logging, locking, retries, and permissions; poor fit for large clusters without orchestration |
| **Workflow orchestrator (Airflow, Argo, etc.)** | Multiple dependent jobs, DAGs, SLAs, backfills, cross-job tracking | Extra infrastructure, data contracts, and execution ID mapping |
| **Managed scheduler / cloud event service** | Infrastructure already provides triggers, queues, and explicit retry policies | Requires idempotent endpoints/consumers, security, and duplicate handling |

A straightforward decision rule: if only `importOrders` runs daily on **a single JVM**, `@Scheduled` is usually enough to start. If you need **durable trigger persistence across service downtime**, multi-node runs, user-editable schedules, or controlled misfire retries, Quartz/an external scheduler is usually easier to manage long-term.

### `@Scheduled` Is Not a Persistent Schedule

When the JVM is stopped at 02:15, the `@Scheduled` method does not run. After the JVM restarts at 09:00, it **does not automatically backfill the 02:15 tick**. You need:

- An external job/trigger with missed-run tracking.
- Or a periodic **reconciliation process** comparing expected periods against `JobRepository` metadata and queuing missing periods for orchestration.
- Or a controlled manual backfill runbook if SLAs and frequency allow.

**Never rely on "no `FAILED` rows" to conclude there were no incidents.** A job that never launched has no execution to fail.

## 12. Multi-Instance Deployment: Preventing Duplicate Triggers

In an HA model with two or more JVMs/pods running the same `@Scheduled` code:

```text
02:15:00
  Pod A --> @Scheduled --> launch(importOrders, 2026-11-15)
  Pod B --> @Scheduled --> launch(importOrders, 2026-11-15)
                  |
                  v
            Shared JobRepository
```

Two pods each have their own scheduler. **`@Scheduled` is not a distributed lock.** `JobRepository` enforces instance/execution rules to block some duplicate cases on the same identity, yet it should not be treated as a complete cluster orchestration policy. Simultaneous execution creation can throw contention exceptions; replacing the identifying parameter with a UUID on each pod would let both launch **two different `JobInstance`s**, which is very dangerous.

Options:

1. Run the scheduler on **only one managed instance/leader**; other workers only execute jobs.
2. Use a **Quartz JDBC cluster** with persistent triggers and cluster config per Quartz documentation.
3. Use a **Kubernetes CronJob** or an external scheduler as a single trigger source.
4. Use a distributed lock/lease on trigger with proper TTL, failure handling, and fencing; avoid rolling a lock with a non-atomic boolean column.
5. Even with scheduler locks, still use **stable `JobParameters` and an idempotent writer** because retries/network faults can replay messages.

**Never rely solely on Java `synchronized`** to prevent duplicate runs across multiple pods; it only synchronizes threads within the same JVM. Nor should you assume a Kubernetes CronJob's `concurrencyPolicy: Forbid` prevents all jobs from being run via a manual API or another CronJob object.

## 13. If Using Quartz: How to Integrate?

Quartz has its own `JobDetail` and `Trigger` concepts, distinct from `org.springframework.batch.core.Job`. A Quartz job class is typically an **adapter**: it reads schedule and data from Quartz `JobDataMap`, then calls `ImportOrdersLaunchService.launch(businessDate)`. `JobRepository` continues managing Spring Batch metadata.

```text
Quartz CronTrigger (persistent JDBC)
        |
        v
Quartz Job (adapter)
        |
        v
ImportOrdersLaunchService
        |
        v
JobLauncher -> Spring Batch Job -> JobRepository
```

Distinguish Quartz's "Job" name from the Batch job name. Quartz does not natively understand Spring Batch `StepExecution`s, chunk checkpoints, or `JobInstance` identity.

When clustering is needed, configure **Quartz JDBC `JobStore`**, clustering, and misfire behavior for your version. Quartz's `@DisallowConcurrentExecution` prevents parallel execution of the **same `JobDetail` key** at the Quartz layer under proper infrastructure setup; it does not replace Spring Batch business/metadata protection and does not block another entry point calling `JobLauncher`.

If Quartz runs an adapter while `JobLauncher` uses an **asynchronous** executor, Quartz may think the adapter callback finished while Batch is still running; thus overlap prevention must track the **actual Batch execution lifecycle**, not only the Quartz method duration.

## 14. If Using Kubernetes CronJob

One production option is packaging the application as a **run-once** program: the container starts, runs one `Job` for one period, and exits with an exit code reflecting the result. Kubernetes creates Pods on schedule.

Illustrative manifest example:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: import-orders
spec:
  schedule: "15 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 3600
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 1
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: import-orders
              image: registry.example.com/orders-batch:1.0.0
              args:
                - "--spring.profiles.active=cronjob"
                - "--spring.batch.job.enabled=false"
```

**This manifest is a deployment skeleton, not a complete run-once program.** The image must have an entry point running `importOrders`, computing `businessDate` from schedule/orchestrator input, waiting for terminal `JobExecution`, and returning the right exit code. Use a persistent `JobRepository` database. If reusing the same application that has `@EnableScheduling` without disabling in-process scheduling, the run-once pod might never exit or create two trigger mechanisms; separate config via profiles/entry points.

Kubernetes `spec.timeZone` is supported only in suitable Kubernetes versions; verify cluster version and timezone policy. `concurrencyPolicy: Forbid` prevents overlapping Jobs managed by the **same CronJob controller** under that policy, yet does not guarantee a period won't be triggered from another system. `startingDeadlineSeconds` and `backoffLimit` affect delayed schedules and Kubernetes pod retry counts; coordinate them with Spring Batch restart/idempotency policies.

### What Should a Run-Once Entry Point Do?

```text
Start application in cronjob profile
   |
   v
Compute/read provided businessDate
   |
   v
JobLauncher.run(importOrders, stable JobParameters)
   |
   v
Wait for JobExecution terminal status
   |
   +-- COMPLETED: exit 0 (and quality gates passed)
   +-- FAILED / STOPPED / UNKNOWN: non-zero exit
   +-- already COMPLETED: duplicate policy may exit 0
   +-- launch error: non-zero exit, alert
```

If the container is killed mid-run, metadata may remain `STARTED`; you need a runbook checking status and checkpoints before allowing restart. Never edit metadata via arbitrary SQL to force Kubernetes retries.

## 15. Long-Running Jobs and Overlapping Schedules

Suppose cron triggers at 02:15 daily yet `importOrders` sometimes takes 27 hours. By 02:15 the next day, the previous period's execution is still running:

```text
2026-11-16 02:15 -> businessDate=2026-11-15 STARTED
2026-11-17 02:15 -> businessDate=2026-11-16 NEW INSTANCE
```

Because identifying `businessDate` differs, `JobRepository` **may allow two `JobInstance`s to run concurrently**, depending on job/step and infrastructure. If writers share tables, files, or API rate limits, this can cause contention even though each instance has a valid identity.

You must pick a policy at the **level of the whole `importOrders` job type**, not only "same `businessDate`":

| Policy | While Previous Period Still Runs | When to Use |
| --- | --- | --- |
| **Allow overlap** | Run two periods concurrently | Inputs/outputs are fully partitioned and system handles load well |
| **Forbid overlap** | Do not create new execution while previous runs | Job needs exclusive resources or must avoid overlapping transactions |
| **Queue** | Enqueue new period request durably; run after old finishes | Must not miss periods and cannot overlap |
| **Catch-up** | After previous finishes, scan missing periods | Suitable when SLAs tolerate delayed processing |
| **Skip with alert** | Do not run new period; alert operators to decide | Work must not auto-replay or carries high risk |

@Scheduled alone does not enforce all these policies across **every `JobInstance` and every node**. Implement them in the scheduler/orchestrator or a coordinator service with durable locks/state while keeping period names and execution IDs for auditing.

## 16. Schedule Time Does Not Mean "Data Is Ready"

A 02:15 cron represents only a **clock milestone**, not proof that the source file arrived or upstream reports finished. If the job needs `orders-2026-11-15.csv` yet the partner system is 40 minutes late, options include:

- **Fail fast on source-not-ready**, letting scheduler/orchestrator perform bounded retries per policy; never synthesize an empty dataset.
- **Wait for a "file ready" event** or provider marker/checksum, then trigger the job.
- **Dependency-aware orchestration**: launch only after upstream jobs `COMPLETED` and quality gates passed.
- **Check the source before creating a `JobExecution`** if you want to avoid floods of failures for unready inputs, while ensuring check-and-launch has no race conditions.
- **Wait up to a deadline**: accept late arrivals within a grace period, alerting past deadline.

If the source changes after the job starts—especially when the reader uses offset-based checkpoints—restarts can read a different dataset. Keep source version/checksum/snapshot stable across all runs of the same `JobInstance`.

## 17. Monitoring Scheduled Jobs

A scheduled method being called does not prove the job completed. Distinguish three events:

```text
batch.schedule.triggered
    The scheduler reached the tick and decided to call launch.

batch.job.started / JobExecution created
    JobRepository records the execution and Batch starts processing.

batch.job.finished
    The execution has a final outcome: COMPLETED / FAILED / STOPPED...
```

You can attach a `JobExecutionListener` to record final results independently of sync/async launchers:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class JobOutcomeListener implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(JobOutcomeListener.class);

    @Override
    public void afterJob(JobExecution execution) {
        log.info(
                "Job ended: name={} instance={} execution={} " +
                "businessDate={} status={} exitCode={}",
                execution.getJobInstance().getJobName(),
                execution.getJobInstance().getId(),
                execution.getId(),
                execution.getJobParameters().getString("businessDate"),
                execution.getStatus(),
                execution.getExitStatus().getExitCode());
    }
}
```

Attach with `new JobBuilder(...).listener(new JobOutcomeListener()).start(...).build()` in job configuration. In real systems, write structured logs and status-based alerts rather than printing only to the console. If the JVM is killed before `afterJob`, the callback may not run; repository + liveness/heartbeat and recovery procedures are then required.

Metrics to monitor:

| Perspective | KPI | Source |
| --- | --- | --- |
| Schedule | Expected vs actual triggers, missing runs, lateness | Scheduler/orchestrator + business calendar |
| Job | `JobExecution` status, duration, restart count | `JobRepository`/`JobExplorer` |
| Step | read/write/filter/skip, commit/rollback | `StepExecution` |
| Quality | expected record count, actual record count, skip limits | Application validation + metadata |
| Performance | duration, active jobs, throughput | Micrometer, logs, tracing |
| Infrastructure | metadata DB availability, connection pool, thread/pod health | Metrics/health checks |

If the application was shut down at cron time, the repository has **no execution**, so compare expected schedules against execution history to detect `MISSING_RUN`. A `JobExecution` lingering in `STARTED` after a crash also does not guarantee a live process; verify liveness before recovery.

## 18. Testing with `Clock.fixed` and Mocked `JobLauncher`

Separating the launch service makes `JobParameters` construction deterministic in tests. With JUnit Jupiter tests:

```java
import java.time.LocalDate;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobParameters;

import com.example.batch.service.ImportOrdersLaunchService;

import static org.junit.jupiter.api.Assertions.*;

class ImportOrdersParametersTest {

    @Test
    void sameBusinessDateProducesStableIdentity() {
        LocalDate date = LocalDate.of(2026, 11, 15);

        JobParameters first =
                ImportOrdersLaunchService.parametersFor(date);
        JobParameters second =
                ImportOrdersLaunchService.parametersFor(date);

        assertEquals(first, second);
        assertEquals("2026-11-15",
                first.getString("businessDate"));
        assertTrue(first.getParameter("businessDate").isIdentifying());
        assertFalse(first.getParameter("triggerSource").isIdentifying());
    }

    @Test
    void distinctBusinessDatesProduceDifferentIdentities() {
        JobParameters dayA = ImportOrdersLaunchService.parametersFor(
                LocalDate.of(2026, 11, 14));
        JobParameters dayB = ImportOrdersLaunchService.parametersFor(
                LocalDate.of(2026, 11, 15));

        assertNotEquals(dayA, dayB);
    }
}
```

Test the date computed by the scheduler using `Clock.fixed`:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SchedulerBusinessDateTest {

    @Test
    void usesPreviousDayInConfiguredTimezone() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-16T00:30:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        LocalDate businessDate = LocalDate.now(clock).minusDays(1);

        assertEquals(LocalDate.of(2026, 11, 15), businessDate);
    }
}
```

Add a unit test mocking `JobLauncher` to assert the service passes the right `Job` and `JobParameters`:

```java
import java.time.LocalDate;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.launch.JobLauncher;

import com.example.batch.service.ImportOrdersLaunchService;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class ImportOrdersLaunchServiceTest {

    @Test
    void launchPassesCorrectBusinessDate() throws Exception {
        JobLauncher launcher = mock(JobLauncher.class);
        Job job = mock(Job.class);
        JobExecution execution = mock(JobExecution.class);

        when(launcher.run(eq(job), any(JobParameters.class)))
                .thenReturn(execution);

        ImportOrdersLaunchService service =
                new ImportOrdersLaunchService(launcher, job);

        service.launch(LocalDate.of(2026, 11, 15));

        ArgumentCaptor<JobParameters> captor =
                ArgumentCaptor.forClass(JobParameters.class);
        verify(launcher).run(eq(job), captor.capture());

        assertEquals("2026-11-15",
                captor.getValue().getString("businessDate"));
    }
}
```

These tests do not need to run real cron schedules or wait until 02:15. They test identity-building logic and launcher invocation without relying on real wall-clock time.

### What Should Integration Tests Prove?

With `spring-batch-test` and a controllable test repository, add scenarios:

1. Launch `importOrders` for `businessDate=2026-11-15` and verify execution `COMPLETED`.
2. Launch again with the **exact same identifying params** and verify Spring Batch rejects it if already completed.
3. Intentionally fail a step after a chunk commits; re-run with the same params and verify restart creates no duplicate data.
4. Verify `spring.batch.job.enabled=false`: context startup does not auto-create an execution.
5. Two concurrent requests for the same period: repository/scheduling policy prevents duplicate business effects.
6. Two missed cron days: reconciliation/backfill detects all missing periods.
7. Test process crash/metadata connection loss and proper recovery workflow.
8. Test schedules in the configured timezone; if DST applies, add transition-day tests.

A restart test must **preserve metadata between the `FAILED` run and the retry**; do not recreate an H2 database in each half of the test and claim checkpoints worked. `writeCount` metrics do not substitute for verifying distinct business IDs in target data.

## 19. Operational Procedures: When Schedules Are Missed or Jobs Fail

For production, have a runbook covering:

### Case A — Past Scheduled Time with No `JobExecution`

1. Check whether the scheduler/pod was active at the expected time.
2. Check cron expression, timezone, feature flags/profiles, and configuration.
3. Check inputs/dependencies and the scheduler's retry/misfire mechanism.
4. Compute missing `businessDate`s from the **expected schedule**, not solely from executions in the DB.
5. Backfill each period via the launch service/orchestrator with stable identifying params; monitor to completion.

### Case B — `JobInstanceAlreadyCompleteException`

This may be cron re-firing the same period for an already-`COMPLETED` job. Verify the right instance and quality results. If the business genuinely needs to re-ingest a new data version, follow a versioned/idempotent rerun workflow with auditing; never append an arbitrary UUID.

### Case C — `FAILED`

Check `JobExplorer`, step error, checkpoints, whether the source remained stable, which target data committed, and whether the writer supports replay. If appropriate, restart with the **same identifying parameters**. If unsure about off-transaction side effects, reconcile before re-calling APIs or rewriting files.

### Case D — `STARTED` Too Long or After a Process Crash

Never blindly `UPDATE BATCH_JOB_EXECUTION SET STATUS='FAILED'` just because `LAST_UPDATED` is old. Confirm the process/worker died, check DB/transaction health and existing side effects, then use a recovery mechanism supported by your Batch version and runbook.

### Case E — Overlapping Schedules

Check business identity, whether two different instances or one duplicate-triggered instance exist, data sources, and shared resources. Enforce concurrency policy at the orchestrator/leader level rather than merely adding `synchronized` inside one JVM.

## 20. Production Scheduler Checklist

| Item | Must Verify Before Operations |
| --- | --- |
| Schedule | Correct 5/6-field cron, explicit timezone, holiday/DST policy |
| Identity | `JobParameters` has stable identifying fields, no unintended random run IDs |
| Startup | Does not auto-run off-schedule at application startup |
| Repository | Persistent JDBC metadata DB, schema migrations/backups, proper permissions |
| Restart | Reader/writer have checkpoints or suitable replay/idempotency strategies |
| Concurrency | Overlap rules across periods and across nodes are defined |
| Missing runs | Expected schedule and post-downtime detection/backfill exist |
| Monitoring | Logs job/step IDs, final status, duration, counts, and alerts |
| Quality gates | Technical `COMPLETED` does not guarantee data requirements are met |
| Security | Only authorized scheduler/group can launch; never expose full `JobParameters` |
| Operations | Runbooks exist for `FAILED`/`STARTED`/misfires, backfills, and manual reruns |
| Tests | Unit tests for schedule/params, integration tests for duplicates and restarts |
| Deployment | Single source of truth for scheduling (in-process or external), no dual triggers |
| Cost/performance | Scheduler thread pool, datasource load, and SLAs are monitored |

A key principle is **having a single "source of truth" for schedules**. When migrating from `@Scheduled` to Quartz or a Kubernetes CronJob, disable the old mechanism via profiles/feature flags; running both simultaneously creates competing triggers even though `JobRepository` occasionally blocks some duplicates.

## 21. Project Extension Exercises

Once the demo works, extend piece by piece:

**Exercise 1 — Decoupling run date from the clock.** Create an internal command taking `businessDate` and calling the same `ImportOrdersLaunchService`; restrict execution to authorized operators. Verify an already-`COMPLETED` period does not unintentionally create a new instance.

**Exercise 2 — Moving from H2 to PostgreSQL.** Create the metadata schema via migrations and ensure `JobRepository` retains data across JVM restarts. Fail a middle step, restart the app, and restart the same `JobInstance`.

**Exercise 3 — Missing-run detector.** Store the list of mandatory periods; each morning compare against `JobExplorer` to find periods with no execution or not finished before deadline. Test shutting down the app across two consecutive cron ticks and recovering.

**Exercise 4 — Scheduler cluster.** Run two replicas with the same cron, observe dual triggers, and design a leader/external scheduler or Quartz clustered `JobStore`. Test concurrent launch races for the same period and verify no side effects duplicate.

**Exercise 5 — Externalized scheduling.** Move scheduling to a Kubernetes CronJob or Quartz; keep `ImportOrdersLaunchService` as the shared launch point. Separate profiles so internal cron and external cron never both run concurrently.

**Exercise 6 — Multi-job workflow.** After import succeeds and the quality gate passes, trigger `reconcileOrders` for the same period and output version. Simulate import `FAILED` and ensure downstream never runs prematurely, even when `JobLauncher` runs asynchronously.

## 22. Common Pitfalls When Scheduling Jobs

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Job runs right when app starts | Spring Boot auto-runs jobs at startup | `spring.batch.job.enabled=false` when using app-controlled schedules |
| Cron is not invoked | Missing `@EnableScheduling`, bean not in context, bad cron | Check annotations, profiles, properties, and timezone |
| Cron runs at wrong hour | Confusing 5- and 6-field cron or JVM timezone | Use 6 fields for `@Scheduled`, set explicit `zone` |
| Processes wrong date | Using `LocalDate.now()` in step or wrong timezone | Build `businessDate` from business `Clock` and pass in `JobParameters` |
| Multiple instances run daily for same period | Adding identifying UUID/timestamp | Stable identifying params, idempotency, and cluster scheduling |
| Job does not run a second time after code fix | Same instance already `COMPLETED` | Distinguish restarts, new-version reruns, and backfills |
| Trigger reports success yet job later `FAILED` | Confusing launcher submission with terminal execution | Monitor final `JobExecution` via listeners/repository |
| Scheduler misses ticks during downtime | `@Scheduled` does not store missed ticks | Misfire-aware scheduler or reconciliation/backfill |
| Both pods trigger | `@Scheduled` runs on every instance | Single scheduler leader / Quartz cluster / external trigger |
| Long job delays other schedules | Scheduler thread occupied by synchronous launcher | Configure execution/monitoring properly; never increase concurrency blindly |
| Next day's job overlaps previous day's | Each day has a different identifying param | Overlap/queuing rules at scheduler/orchestrator level |
| Restarts from start and writes duplicates | Reader lacks checkpoints or writer lacks idempotency | `ItemStream`, immutable sources, transactions/idempotency |
| Missed runs invisible on dashboard | Repository only stores created runs | Compare expected schedule against Batch history |
| Pod dies, metadata stays `STARTED` | Could not write terminal status in time | Verify liveness, safe recovery; never edit SQL arbitrarily |
| Quartz allows re-launching while Batch still runs | Quartz adapter returns early due to async launcher | Track actual Batch lifecycle and prevent overlap at workflow level |
| Kubernetes CronJob runs forever without exiting | Image still has in-process scheduler/web server enabled | Separate run-once entry point and appropriate profile |

## 23. References

The URLs below are foundational references; when deploying with Spring Batch 6.x or another Spring Boot version, check APIs against your exact dependencies.

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — `@Scheduled` annotation](https://docs.spring.io/spring-framework/reference/integration/scheduling/annotations.html)
- [Spring Framework — Cron Expressions](https://docs.spring.io/spring-framework/reference/integration/scheduling.html#scheduling-cron-expression)
- [Spring Batch 5.2 — Configuring a Job](https://docs.spring.io/spring-batch/reference/5.2/job/configuring.html)
- [Spring Batch 5.2 — Job Domain, JobInstance, JobExecution](https://docs.spring.io/spring-batch/reference/5.2/domain.html)
- [Spring Batch 5.2 — Advanced Metadata Usage and JobOperator](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html)
- [Spring Batch 5.2 — JobRepository Configuration](https://docs.spring.io/spring-batch/reference/5.2/job/configuring-repository.html)
- [Spring Batch 5.2 — Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html)
- [Spring Boot — Batch Applications](https://docs.spring.io/spring-boot/how-to/batch.html)
- [Spring Boot — Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html)
- [Quartz Scheduler — Documentation](https://www.quartz-scheduler.org/documentation/)
- [Kubernetes — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
- [Java 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html)

**Conclusion:** Scheduling a Spring Batch job is more than writing `@Scheduled(cron=...)`. Clearly separate **determining the schedule**, **selecting the business period**, **launching with stable identifying `JobParameters`**, **persisting metadata in a durable repository**, and **monitoring final outcomes**. For a single JVM and simple schedule, `@Scheduled` is a suitable starting point. With multiple nodes, missed runs, complex SLAs, or multi-job workflows, use Quartz/Kubernetes/an external orchestrator combined with explicit idempotency, backfill, and recovery strategies.
