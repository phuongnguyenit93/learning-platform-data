# Misfires and Missed Schedules in Spring Batch

## 1. The Problem: A Schedule Comes Due but the Batch Does Not Run

In batch processing systems, a job is typically triggered at a fixed time: every 5 minutes, daily at 02:00, start of month, or accounting period close. However, the application might be deploying, the scheduler stopped, worker threads exhausted, the database temporarily unreachable, or the previous run still active. When the planned time arrives and the job fails to start, you have a **missed schedule**.

Suppose a system closes daily revenue every day at 02:00 Vietnam time:

```text
Day 10, 02:00  -> reportJob COMPLETED
Day 11, 02:00  -> application down, no execution
Day 12, 02:00  -> application still down
Day 13, 09:00  -> application restarts
```

After restarting, the system must know whether to process days 11, 12, and 13 or only generate one latest report. If launching in bulk, protect the database from overload and prevent duplicate outputs. If skipping, ensure business requirements are still satisfied.

**Misfire** and **missed schedule** are related but not synonymous:

- **Missed schedule** is a business condition: a scheduled slot fell due, but the corresponding work was not fully performed. This concept applies to Spring `@Scheduled`, Quartz, Kubernetes CronJob, or any other scheduler.
- **Misfire** is a scheduler concept, especially in **Quartz**: a trigger was delayed past a threshold recognized by the JobStore, leading to a *misfire instruction* such as skipping or firing immediately.
- **Failed job** is the state of a Spring Batch run that was created and ended `BatchStatus.FAILED`. A missed schedule may **never create any `JobExecution` at all**.

Spring Batch manages jobs/steps, transactions, metadata, checkpoints, and restarts. Spring Batch **does not itself provide a persistent cron scheduler**. The scheduling layer must be configured via Spring Scheduling, Quartz, or an external orchestrator.

Lesson goals: accurately identify missed schedules, understand Quartz misfire policies, choose skip/fire-once/backfill, connect schedulers to Spring Batch using stable identifying parameters, and test schedule recovery safely.

Examples use Java 17+, Spring Framework 6.x, Spring Boot 3.x, Spring Batch 5.x, and Quartz 2.x; projects on other versions should verify matching APIs and metadata schemas.

---

## 2. Three Types of State to Distinguish

### 2.1. Schedule Slot vs. `JobExecution`

A **slot** is one scheduled business work period, such as 02:00 on 2026-11-12. The scheduler may trigger once or multiple times, while Spring Batch may create multiple `JobExecution`s if a restart is needed:

```text
Business schedule slot
  2026-11-12T02:00:00+07:00
            |
            v
Scheduler / Quartz trigger
            |
            v
JobLauncher + identifying JobParameters
            |
            v
Spring Batch JobInstance #71
            |
            +-- JobExecution #241 -> FAILED
            |
            +-- JobExecution #242 -> COMPLETED (restart)
```

| Dimension | Question | Where to observe |
| --- | --- | --- |
| Business slot | Was a due period fully processed? | Slot ledger or separate orchestration state |
| Scheduler | Which triggers should fire, were any delayed, paused, or misfired? | Quartz JobStore, scheduler logs/metrics |
| Spring Batch | Which jobs started, succeeded/failed, and what are checkpoints? | `JobRepository`, `JobExplorer`, `BATCH_*` tables |
| Business outcome | Are reports, files, records, or events accurate and non-duplicated? | Business DB, target systems, reconciliation |

If the scheduler crashes before issuing a run command, **`JobRepository` cannot record a `FAILED` status for a slot that was never launched**. Thus, monitoring `BatchStatus.FAILED` alone is insufficient to detect missed schedules.

### 2.2. Operational Terminology

| Condition | Signal | Primary handling |
| --- | --- | --- |
| Missed schedule | Due slot has no completed result | Skip/coalesce/backfill per policy |
| Delayed trigger | Fired later than nominal time | Check scheduler lag |
| Job failure | `JobExecution` has `FAILED` | Fix root cause and restart the exact `JobInstance` |
| Stop | `JobExecution` transitioned to `STOPPED` on request | Decide controlled restart |
| Overlap | New slot arrives while prior job still runs | Admission control, queue, skip, or concurrency |
| Duplicate launch | Two launchers process the same slot | Unique keys, lock/claim, and job parameters |
| Quartz misfire | Trigger delayed enough for Quartz to apply misfire instruction | Inspect trigger policy and JobStore |

A downtime event can cause a Quartz misfire, producing a late Batch execution; that execution can still fail independently due to invalid business data.

---

## 3. Causes of Missed Schedules

### 3.1. Failures and Downtime

- Scheduler/process/Pod stopped when the trigger time arrived.
- Deployment/rolling restart spanned across the cron tick.
- Scheduler or JobStore temporarily lost connectivity.
- Quartz thread pool ran out of workers; due triggers were not picked up for execution.
- Scheduler was paused/in standby, or a Quartz cluster instance crashed.
- Quartz job concurrency was restricted while the previous run dragged on.
- Bottleneck at the Spring Batch launch layer, connection pool exhaustion, or inability to start a transaction.
- Timezone changes, unsynchronized node clocks, or cron ticks hitting daylight saving time transitions.

### 3.2. Work Taking Longer Than the Interval

```text
10:00  slot A -> starts; finishes 10:12
10:05  slot B -> due while A is still running
10:10  slot C -> due while A is still running
10:15  slot D -> due
```

If allowed to run in parallel, jobs may contend on input/output data. If disallowed, backlog grows; depending on the scheduler, pending fire times can become misfires.

The solution must come from business requirements: can slots B and C be skipped, merged, or must every single one be queued? Adding worker threads does not by itself solve duplicate data or transaction contention.

### 3.3. Cron and Timezones

Every schedule must specify a timezone. For a 02:30 cron in a DST region, the spring-forward day may skip 02:30 altogether; the fall-back day may have two 02:30 instants under different offsets.

Clearly define:

- **Nominal scheduled instant**: the planned schedule timestamp under the configured timezone and cron version.
- **Business date**: the data period processed by the job. For a day N−1 report, business date differs from the trigger date.
- **Actual fire time**: when the scheduler actually invokes the job.
- **Batch start/completion time**: when `JobExecution` starts and finishes.

These values must not be used interchangeably.

---

## 4. How Quartz Detects Misfires

Quartz defines `JobDetail`, `Trigger`, and `Scheduler`. Triggers describe fire times, while the JobStore persists schedule state. When a trigger should have fired but was delayed, Quartz may treat it as a misfire and apply the chosen instruction.

### 4.1. `misfireThreshold`

Typical Quartz configuration:

```properties
org.quartz.jobStore.misfireThreshold=60000
```

Units are milliseconds; a common default is **60,000 ms** (60 seconds). A trigger delayed below the threshold does not necessarily enter misfire handling; a trigger delayed long enough may be flagged as misfired by the JobStore, adjusting its next fire time according to policy.

```text
Expected fire: 02:00:00
Scheduler ready: 02:00:08
Threshold: 60s

=> Delayed 8 seconds; not treated as misfire by default.

Expected fire: 02:00:00
Scheduler ready: 02:07:00
Threshold: 60s

=> Delayed 7 minutes; misfire instruction may be applied.
```

This threshold is **not a Spring Batch timeout**, not a business SLA, does not change `retryLimit`, and does not automatically restart `FAILED` executions.

### 4.2. `RAMJobStore` vs. JDBC JobStore

| Quartz JobStore | Survives JVM restart? | Notes |
| --- | --- | --- |
| `RAMJobStore` | Loses old triggers when JVM dies | For demos/tests or schedules needing no persistence |
| JDBC JobStore | Preserves triggers if DB persists and configured properly | Suitable for downtime recovery and clustering |

Quartz JDBC uses tables like `QRTZ_JOB_DETAILS`, `QRTZ_TRIGGERS`, `QRTZ_CRON_TRIGGERS`. Spring Batch JDBC stores `JobInstance`, `JobExecution`, `StepExecution`, and `ExecutionContext` in `BATCH_*` tables.

Both table sets can reside in the same physical database, but:

- `QRTZ_*` knows triggers and scheduler state.
- `BATCH_*` knows Batch runs that were created.
- Neither **automatically guarantees** every business date has valid output.

### 4.3. When Do Misfires Occur?

Common causes of delayed triggers: scheduler downtime, insufficient threads, paused triggers, concurrency limits, or unreachable JobStore. When a node comes back up, triggers still persisted in the JDBC JobStore are what enable Quartz to recover past schedules.

With `RAMJobStore`, a JVM restart wipes all prior triggers; a Java bean registering a fresh trigger at startup does not mean Quartz remembers missed slots.

---

## 5. Three Main Misfire Policies for Quartz `CronTrigger`

### 5.1. Skip: `DoNothing`

`CronScheduleBuilder.withMisfireHandlingInstructionDoNothing()` tells Quartz to ignore missed fire times and calculate the next matching future cron fire time.

Example: the app is down for three days and restarts at 09:00. With a daily 02:00 schedule, old days are skipped; the next trigger is 02:00 the next day.

Suitable for: cache cleanup, state syncs superseded by the next period, or stale tasks with no remaining value.

### 5.2. Fire Once: `FireAndProceed`

`withMisfireHandlingInstructionFireAndProceed()` tells Quartz to fire once as soon as possible after detecting a misfire, then continue with the future cron schedule.

For example, a 02:00 schedule misses days 11, 12, and 13, and the scheduler restarts at 09:00 on day 13. Firing once upon resume **does not equal producing three separate reports for days 11, 12, and 13**.

Suitable for: snapshot refreshes, syncing latest state, or tasks needing a single catch-up sweep after an outage.

Quartz `CronTrigger`'s `SMART_POLICY` normally resolves to fire-once-now behavior on misfire. For critical workflows, declare the instruction explicitly.

### 5.3. Do Not Adjust Schedule on Misfire: `IgnoreMisfires`

`withMisfireHandlingInstructionIgnoreMisfires()` tells Quartz to bypass misfire adjustments and continue evaluating trigger fire times on schedule. With a large backlog, many triggers can fire back-to-back and spike load; actual count/rate still depends on the trigger, JobStore, concurrency, and resources.

**Do not use `IgnoreMisfires` as an exactly-once guarantee for every historical slot.** Quartz does not replace a business ledger tracking which slots succeeded.

### 5.4. Decision Table

Suppose the scheduler is down from the evening of day 10 until 09:00 on day 13; cron is 02:00 daily:

| Policy | Typical post-recovery result | Risk |
| --- | --- | --- |
| `DoNothing` | Skips days 11–13, waits for day 14 | Loses business periods if each day is required |
| `FireAndProceed` | Fires once around 09:00 on day 13, then waits for day 14 | One run does not produce 3 separate reports |
| `IgnoreMisfires` | May rapidly fire pending times back-to-back | Load spikes and duplicate side effects |
| Per-slot backfill | Dispatches requests for 11, 12, 13 from a ledger | Requires additional logic outside CronTrigger |

The final choice must follow the contract: **does each slot have independent value, or is only the latest state needed?**

### 5.5. Configuring Quartz `CronTrigger` in Java

```java
import java.util.TimeZone;
import org.quartz.CronScheduleBuilder;
import org.quartz.CronTrigger;
import org.quartz.JobDetail;
import org.quartz.TriggerBuilder;

CronTrigger invoiceTrigger = TriggerBuilder.newTrigger()
    .withIdentity("dailyInvoice", "finance")
    .forJob(jobDetail)
    .withSchedule(
        CronScheduleBuilder
            .cronSchedule("0 0 2 * * ?")
            .inTimeZone(TimeZone.getTimeZone("Asia/Ho_Chi_Minh"))
            .withMisfireHandlingInstructionFireAndProceed()
    )
    .build();
```

`0 0 2 * * ?` is a Quartz expression firing at **02:00 daily**. Quartz cron starts with seconds, and `?` denotes no specific value for day-of-month/day-of-week respectively.

Switching to skip missed schedules:

```java
.withMisfireHandlingInstructionDoNothing()
```

Or only when backlog behavior is clearly understood:

```java
.withMisfireHandlingInstructionIgnoreMisfires()
```

These builder snippets are **alternatives** to the instruction in the example, not instructions to chain together.

### 5.6. `SimpleTrigger` Uses Different Policies

`SimpleTrigger` defines schedules by repeat interval/count; instructions such as `FIRE_NOW`, `RESCHEDULE_NEXT_WITH_EXISTING_COUNT`, and `RESCHEDULE_NOW_WITH_REMAINING_REPEAT_COUNT` carry distinct semantics, especially affecting remaining repeat counts. Do not carry `CronTrigger` instructions over to `SimpleTrigger` by assumption.

When a job running every N minutes must produce N outputs corresponding to time intervals, distinguish “Quartz repeat count” from “missing business slots” in your domain design.

---

## 6. How `@Scheduled` Differs from Quartz Misfires

Spring Framework provides `@Scheduled` for cron, `fixedRate`, or `fixedDelay` tasks:

```java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class InvoiceSchedule {

    private final InvoiceBatchLauncher launcher;

    public InvoiceSchedule(InvoiceBatchLauncher launcher) {
        this.launcher = launcher;
    }

    @Scheduled(
        cron = "0 0 2 * * *",
        zone = "Asia/Ho_Chi_Minh"
    )
    public void runDaily() {
        launcher.launchDueInvoices();
    }
}
```

This example requires `@EnableScheduling` and an application-defined `InvoiceBatchLauncher` bean. The periodic callback is purely a trigger mechanism; it does not automatically spawn executions for missed periods.

**Key points:**

- `@Scheduled` does not provide persistent trigger history equivalent to Quartz JDBC JobStore by default.
- When the JVM is down across several cron fire times, old callbacks do not automatically catch up on startup.
- Delays caused by busy scheduler threads differ from schedules missed across shutdowns.
- If every business date is mandatory, the `@Scheduled` method should invoke a **reconciler** that checks unprocessed slots in a durable state table.

### 6.1. `fixedRate`, `fixedDelay`, and Cron

```java
@Scheduled(fixedRateString = "PT5M")
public void runEveryFiveMinutes() { /* ... */ }

@Scheduled(fixedDelayString = "PT5M")
public void runFiveMinutesAfterFinish() { /* ... */ }

@Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")
public void runAtTwoAM() { /* ... */ }
```

| Mechanism | How to think about the schedule | Notes |
| --- | --- | --- |
| `fixedRate` | Even spacing between trigger ticks per scheduler cadence | Busy threads still delay runs; exact semantics depend on scheduler |
| `fixedDelay` | Waits a fixed duration **after the previous run finishes** | Does not anchor to fixed wall-clock instants |
| `cron` | Specific time/date points in a given timezone | Account for DST, downtime, overlap, and business date definitions |

Do not assume `@Scheduled(fixedRate)` endlessly queues missed runs while the application is shut down.

### 6.2. When Is `@Scheduled` Sufficient?

For lightweight **best-effort** tasks like cache eviction or snapshot refreshes, skipping a few fires may be acceptable. For accounting reports, daily revenue, billing, or exports requiring every historical period, use Quartz JDBC or another orchestrator paired with a **persistent schedule-slot ledger**.

---

## 7. Configuring Quartz JDBC with Spring Batch

### 7.1. Dependencies

Gradle Groovy DSL example, assuming the project already uses the Spring Boot BOM:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-quartz'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

H2 is for integration tests; PostgreSQL is an example production database. If your application uses another database, swap the driver and settings accordingly.

### 7.2. Persistent JDBC JobStore Configuration

Example `application.yml` where migrations pre-create Quartz and Spring Batch tables:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db-host:5432/batch_ops
    username: batch_user
    password: replace-with-secret-in-deployment

  quartz:
    job-store-type: jdbc
    jdbc:
      initialize-schema: never
    properties:
      org.quartz.scheduler.instanceName: financeScheduler
      org.quartz.scheduler.instanceId: AUTO
      org.quartz.jobStore.isClustered: true
      org.quartz.jobStore.misfireThreshold: 60000
      org.quartz.threadPool.threadCount: 10

  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: never
```

Explanation:

- `spring.quartz.job-store-type=jdbc` instructs Spring Boot auto-configuration to use Quartz JDBC JobStore instead of RAMJobStore.
- `spring.quartz.jdbc.initialize-schema=never` and `spring.batch.jdbc.initialize-schema=never` assume Flyway/Liquibase or another migration tool already created `QRTZ_*` and `BATCH_*` tables.
- `org.quartz.jobStore.misfireThreshold` sets the misfire threshold; `threadCount` is an example value to size for your workload.
- `isClustered=true` applies when multiple Quartz instances genuinely share **one JDBC JobStore** with proper cluster configuration. Single-node setups may not need clustered mode.
- `spring.batch.job.enabled=false` stops Boot from auto-running Batch jobs on startup when the scheduler controls runs.

Do not carelessly enable `spring.quartz.jdbc.initialize-schema=always` in production: some bundled Quartz initialization scripts drop and recreate tables, wiping persisted triggers. Prefer explicit managed migrations in production.

If the application defines multiple datasources, explicitly designate which serves Quartz (`@QuartzDataSource` under Boot) and which serves Batch (`@BatchDataSource` or version-appropriate Batch configuration).

### 7.3. Registering Quartz `JobDetail` and `CronTrigger`

```java
import java.util.TimeZone;
import org.quartz.CronScheduleBuilder;
import org.quartz.JobBuilder;
import org.quartz.JobDetail;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class DailyInvoiceQuartzConfig {

    @Bean
    JobDetail invoiceJobDetail() {
        return JobBuilder.newJob(InvoiceQuartzBridge.class)
            .withIdentity("invoiceLauncher", "finance")
            .storeDurably()
            .build();
    }

    @Bean
    Trigger invoiceCronTrigger(JobDetail invoiceJobDetail) {
        return TriggerBuilder.newTrigger()
            .withIdentity("invoice2AM", "finance")
            .forJob(invoiceJobDetail)
            .withSchedule(CronScheduleBuilder
                .cronSchedule("0 0 2 * * ?")
                .inTimeZone(
                    TimeZone.getTimeZone("Asia/Ho_Chi_Minh"))
                .withMisfireHandlingInstructionFireAndProceed())
            .build();
    }
}
```

The `InvoiceQuartzBridge` bean must implement `org.quartz.Job`. Jobs/triggers stored in the JDBC JobStore persist across deployments; changing bean definitions does not automatically update every persisted trigger. Define a schedule synchronization policy on deploy.

### 7.4. Quartz → Batch Bridge

The Quartz job should invoke Spring Batch's `JobLauncher` with **stable per-slot** identifying parameters rather than a random UUID on every fire.

Example configuring Quartz jobs to read `ApplicationContext` from `SchedulerContext` via a Spring Boot customizer:

```java
import org.springframework.boot.autoconfigure.quartz.SchedulerFactoryBeanCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class QuartzContextBridgeConfig {

    @Bean
    SchedulerFactoryBeanCustomizer contextKey() {
        return factory ->
            factory.setApplicationContextSchedulerContextKey(
                "springApplicationContext");
    }
}
```

Quartz job adapter:

```java
import java.time.Instant;
import org.quartz.DisallowConcurrentExecution;
import org.quartz.JobExecutionContext;
import org.quartz.JobExecutionException;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.context.ApplicationContext;

@DisallowConcurrentExecution
public class InvoiceQuartzBridge implements org.quartz.Job {

    @Override
    public void execute(JobExecutionContext quartzContext)
            throws JobExecutionException {
        try {
            ApplicationContext app =
                (ApplicationContext) quartzContext.getScheduler()
                    .getContext().get("springApplicationContext");

            JobLauncher launcher = app.getBean(JobLauncher.class);
            Job batchJob = app.getBean("invoiceBatchJob", Job.class);

            Instant nominalFire =
                quartzContext.getScheduledFireTime().toInstant();

            JobParameters parameters = new JobParametersBuilder()
                .addString("schedule.key",
                    quartzContext.getTrigger().getKey().toString(),
                    true)
                .addLong("scheduled.at.epoch.ms",
                    nominalFire.toEpochMilli(), true)
                .addString("quartz.fire.id",
                    quartzContext.getFireInstanceId(), false)
                .toJobParameters();

            launcher.run(batchJob, parameters);
        } catch (Exception e) {
            // Do not request refireImmediately if it is unclear
            // whether the first launch actually created a JobExecution.
            throw new JobExecutionException(
                "Cannot launch invoiceBatchJob", e);
        }
    }
}
```

This illustrates infrastructure wiring; you still need the `invoiceBatchJob` bean, `JobRepository`, and JobStore configuration. Because `JobLauncher` may use an async executor, Quartz's `execute` method **does not necessarily wait for Batch completion**. If overlap must be prevented until the Batch job ends, add instance/slot-level admission control.

**Note on `getScheduledFireTime()`:** Quartz returns the planned time of the trigger firing now. When `FireAndProceed` has already adjusted fire times after a misfire, this value does not guarantee recovering all previously lost nominal slots. Workflows needing every slot must enumerate slots from the original schedule and a ledger.

### 7.5. Limitations of `@DisallowConcurrentExecution`

The `@DisallowConcurrentExecution` annotation prevents Quartz from concurrently running executions of **the same JobDetail/JobKey**. It does not stop a REST API from launching the same Spring Batch job, does not stop two JobDetails with different JobKeys from acting on the same data, and does not hold a lock through Batch execution if the launcher returns asynchronously.

Therefore, for critical jobs, add data-layer protection: slot claims, unique constraints, idempotent writers, or a distributed lock with proper lifecycle.

---

## 8. Strategies for Handling Missed Schedules

A policy must be chosen from business goals before configuring Quartz or `@Scheduled`.

| Strategy | Meaning | Example | Trade-off |
| --- | --- | --- | --- |
| **SKIP** | Drop overdue slot, wait for next schedule | Cache cleanup | No historical output |
| **FIRE_ONCE** | Run once after system recovers | Refresh latest snapshot | Skips individual past periods |
| **COALESCE** | Merge multiple slots into one catch-up unit | Sync all changes since last watermark | Requires watermark-based logic |
| **BACKFILL** | Launch each missing slot | Daily revenue reports, reconciliation | Must throttle backlog/load |
| **MANUAL_REVIEW** | Flag missing slots and wait for operator decision | Fund transfers, high-impact operations | Requires approval workflow |

### 8.1. SKIP

If a job only cleans caches, running yesterday's cleanup late today may have no value. Each future run handles current state. Quartz `DoNothing` can satisfy this.

### 8.2. FIRE_ONCE / COALESCE

A job to “sync all new orders since last checkpoint” can run a single pass once connectivity returns. However, results are accurate only if checkpoints suffice to recover missed changes and the source retains data long enough.

Never assume any job using `LocalDate.now()` is a valid coalesce. If reports must be calculated separately per day, computing today once does not produce past reports.

### 8.3. BACKFILL

If each day needs its own identified result, build a **slot ledger** and a reconciler that finds incomplete slots. You might set:

- At most 3 slots launched per polling sweep.
- At most 1 active Batch execution per tenant and job.
- Slots older than a cutoff require manual review.
- Backlog ordered oldest-to-newest unless the domain specifies otherwise.
- Never relaunch a slot already confirmed `COMPLETED` by Batch.

These numbers are examples; tune them to real runtime, downstream quotas, and SLAs.

### 8.4. MANUAL_REVIEW

For workflows with hard-to-reverse side effects, like disbursing funds, “immediate automatic backfill” is not always safe. Reconcile dispatched instructions with the destination system, apply idempotency keys, and require approval before replaying.

---

## 9. Persistent Slot Ledger When Every Period Must Be Processed

### 9.1. Why Maintain a Ledger?

Quartz stores triggers; Spring Batch stores executions; neither provides a table answering “every revenue period this month must have an approved report.” A dedicated table tracks the status of **every slot**, including slots the scheduler never fired.

Reference SQL schema example:

```sql
CREATE TABLE batch_schedule_slot (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    job_name VARCHAR(120) NOT NULL,
    schedule_key VARCHAR(120) NOT NULL,
    scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    business_date DATE NOT NULL,
    status VARCHAR(24) NOT NULL,
    batch_execution_id BIGINT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    claimed_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    last_error VARCHAR(1000),
    CONSTRAINT uq_batch_slot UNIQUE (
        job_name, schedule_key, scheduled_at
    )
);
```

This DDL is a logical model; adjust identity/timestamp types per SQL dialect. When a single job serves multiple tenants or cron versions, `schedule_key` should precisely identify the schedule/tenant.

Statuses can include `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `SKIPPED`, or other domain statuses.

### 9.2. Slot Lifecycle

```text
Expected slot
     |
     v
PENDING --------- claim once ------------> RUNNING
                                             |
                                   +---------+----------+
                                   |                    |
                                   v                    v
                           Batch COMPLETED         Batch FAILED
                                   |                    |
                                   v                    v
                              COMPLETED               FAILED
                                                        |
                                                   retry/restart
```

Slot status is not `BatchStatus`: a node may crash while the ledger still reads `RUNNING` even though Batch already reached `COMPLETED`. The reconciler must inspect actual results before changing state.

### 9.3. Safely Claiming a Slot Across Multiple Nodes

Workflow:

1. Generate expected slots from cron/business calendar and timezone over a bounded window.
2. Insert-if-absent to materialize missing slots via the unique constraint.
3. Select eligible `PENDING` slots in order.
4. Claim using a transaction/conditional update or suitable database locking.
5. Only the node whose claim succeeds launches Batch.
6. Persist `JobExecution ID` and track terminal status.
7. Reconcile state if a process dies before or after launching.

Conditional update example:

```sql
UPDATE batch_schedule_slot
SET status = 'RUNNING',
    claimed_at = CURRENT_TIMESTAMP,
    attempt_count = attempt_count + 1
WHERE id = :slotId
  AND status = 'PENDING';
```

Only the caller receiving affected row count = 1 holds the right to process that slot. If two nodes merely `SELECT status='PENDING'` and launch before claiming, both can issue duplicate runs.

### 9.4. Stable Identifying `JobParameters`

A slot's `JobInstance` identity must remain **stable** across retries/restarts:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("schedule.key", scheduleKey, true)
    .addLong("scheduled.at.epoch.ms",
        scheduledAt.toEpochMilli(), true)
    .addString("business.date",
        businessDate.toString(), true)
    .addString("correlation.id", traceId, false)
    .toJobParameters();
```

`traceId` is only for tracing and must be non-identifying. If a UUID/current timestamp is always added as identifying, every command creates a new `JobInstance`, losing the ability to safely restart from prior executions.

When a slot already has a `FAILED` execution, inspect and restart the **same `JobInstance`**. When a slot is already `COMPLETED`, simply reconcile the ledger/outputs; do not create a new instance “just to be sure.”

---

## 10. Computing Dates Needing Backfill

### 10.1. Separating Current Date from Data Date

Suppose the Nov 16 02:00 slot aggregates **business date Nov 15**:

```text
scheduled_at: 2026-11-16T02:00:00+07:00
businessDate: 2026-11-15
timezone:     Asia/Ho_Chi_Minh
now:          2026-11-16T09:00:00+07:00
```

When the scheduler resumes at 09:00, business date 15 must be processed if no result exists yet. If it resumes at 01:00, the 02:00 slot is not due yet. Never call `LocalDate.now()` inside a Batch reader for catch-up runs, because backfills may process data from days earlier.

### 10.2. Simple Watermark-Based Planner

For schedules requiring one result per day with no gaps between completed days, you can compute the missing range:

```java
import java.time.LocalDate;
import java.util.List;

public final class DailyBackfillPlanner {

    private DailyBackfillPlanner() { }

    public static List<LocalDate> dueDates(
            LocalDate lastCompletedDate,
            LocalDate latestDueDate,
            long maxPerPoll) {

        if (maxPerPoll <= 0 ||
            !lastCompletedDate.isBefore(latestDueDate)) {
            return List.of();
        }

        return lastCompletedDate.plusDays(1)
            .datesUntil(latestDueDate.plusDays(1))
            .limit(maxPerPoll)
            .toList();
    }
}
```

JUnit 5:

```java
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class DailyBackfillPlannerTest {

    @Test
    void returnsOldestThreeMissingDates() {
        List<LocalDate> actual =
            DailyBackfillPlanner.dueDates(
                LocalDate.of(2026, 11, 10),
                LocalDate.of(2026, 11, 14),
                3);

        assertEquals(List.of(
            LocalDate.of(2026, 11, 11),
            LocalDate.of(2026, 11, 12),
            LocalDate.of(2026, 11, 13)
        ), actual);
    }

    @Test
    void doesNotReturnFutureOrCompletedDates() {
        assertEquals(List.of(),
            DailyBackfillPlanner.dueDates(
                LocalDate.of(2026, 11, 14),
                LocalDate.of(2026, 11, 14),
                3));
    }
}
```

This only handles contiguous watermarks; **it is insufficient if day 11 succeeded, day 12 failed, and day 13 succeeded**. With gaps, rely on per-slot ledger statuses rather than just `lastCompletedDate`.

### 10.3. How Does a Reconciler Work?

A reconciler can be woken by Quartz or `@Scheduled(fixedDelay)`:

```text
Scheduler tick / service startup
          |
          v
Enumerate expected slots <= now
          |
          v
Insert missing slots (unique key)
          |
          v
Query uncompleted slots
          |
          v
Claim with transaction + quota
          |
          v
For each claimed slot:
   - no Batch instance -> launch first execution
   - existing FAILED -> restart if valid
   - existing STARTED -> monitor/reconcile
   - existing COMPLETED -> mark slot complete
          |
          v
Observe Batch status + business result
```

When schedules change over time, version the schedule or persist the cron/timezone effective for each slot. Do not use a new cron expression to retroactively recompute all historical slots.

---

## 11. Distinguishing New Launch, Restart, and Reconcile

### 11.1. Slot Never Launched

```text
Nominal slot: 2026-11-11T02:00+07:00
Ledger: PENDING
Batch JobRepository: no JobInstance for slot
```

The application must perform an **initial launch** using the identifying parameters defined by the slot. Without an existing `JobExecution ID`, `JobOperator.restart` cannot be called.

### 11.2. Slot with `FAILED` Execution

```text
Nominal slot: 2026-11-12T02:00+07:00
JobInstance #52
JobExecution #701 FAILED
```

After fixing the failure and confirming safety, in Spring Batch 5.x you can run:

```java
Long newExecutionId = jobOperator.restart(701L);
```

The framework creates a new `JobExecution` for the **same `JobInstance`**, skips completed steps by default configuration, and restores checkpoints for steps that must rerun if streams/repositories support it. The reconciler updates the slot's reference to the new execution.

### 11.3. Slot Where Batch Is `COMPLETED` but Ledger Is Still `RUNNING`

A process may have crashed after Batch committed but before updating the ledger:

```text
Batch JobExecution: COMPLETED
Business output:   already written
Slot ledger:       RUNNING
```

Do not create a new `JobInstance` with a UUID just to run again. Query `JobExplorer` and verify business output, then reconcile the ledger to `COMPLETED` if the output is valid.

### 11.4. Quartz Retry Does Not Equal Batch Restart

Quartz `JobExecutionException` includes flags such as `refireImmediately`. If a Quartz job launches Batch and times out waiting for a response, Quartz does not necessarily know whether Batch already created an execution. Unconditional refires easily cause duplicate launches.

Safe policy: give each business slot a stable key; after communication errors, look up Batch instance/execution status and choose launch, restart, or reconcile appropriately.

---

## 12. Concurrency, Clustering, and Idempotency

### 12.1. When a Job Runs Past the Next Schedule Tick

| Policy | Behavior |
| --- | --- |
| Allow overlap | Two slots run concurrently, only when data/infrastructure support it |
| Queue/backfill sequential | New slot stays `PENDING` until old slot finishes |
| Skip | Drops new slot if previous work suffices per contract |
| Coalesce | Merges backlog into a single current-state update run |
| Manual | Requires operator decision while old period is still running |

`@DisallowConcurrentExecution` restricts only Quartz executions sharing a `JobKey`; if `JobLauncher` uses an async executor or another caller exists, Batch jobs can still overlap. True overlap prevention requires admission control at the slot/`JobInstance` and output layers.

### 12.2. Quartz Clustering

With a shared JDBC JobStore:

- Quartz nodes must have compatible scheduler names and unique instance IDs.
- Node clocks must be synchronized.
- The database and connection pool must handle trigger-acquisition load.
- JobStore schema/version must match.
- Jobs/adapters must be idempotent across failovers and network faults.

Quartz provides `JobDetail.requestsRecovery()` to recover Quartz job executions after a node crash; this differs from **Spring Batch checkpoint restart**. Inspect Batch metadata to avoid repeating side effects.

### 12.3. No Automatic Exactly-Once for External Systems

A step can do:

```text
1. Send notification to external API -> succeeds
2. Write SENT status to database -> not committed yet
3. Process crashes before metadata checkpoint
4. Restart -> resends notification
```

Spring Batch cannot automatically guarantee exactly-once for APIs outside its transaction. For such workflows, use idempotency keys derived from slot + business record ID, unique constraints, upserts, or a transactional outbox, depending on your infrastructure.

---

## 13. Testing Misfires and Missed Schedules

Test at multiple levels, because validating a cron string alone never proves the system handles downtime properly.

### 13.1. Unit Testing Quartz Policy Configuration

Example assumes an `org.quartz.Job` test fixture named `NoopQuartzJob`:

```java
import org.junit.jupiter.api.Test;
import org.quartz.CronScheduleBuilder;
import org.quartz.CronTrigger;
import org.quartz.JobBuilder;
import org.quartz.JobDetail;
import org.quartz.TriggerBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;

class QuartzPolicyTest {

    @Test
    void skipsLateCronFireTimes() {
        JobDetail jobDetail =
            JobBuilder.newJob(NoopQuartzJob.class)
                .withIdentity("noop", "test")
                .build();

        CronTrigger trigger = TriggerBuilder.newTrigger()
            .forJob(jobDetail)
            .withSchedule(CronScheduleBuilder
                .cronSchedule("0 0 2 * * ?")
                .withMisfireHandlingInstructionDoNothing())
            .build();

        assertEquals(
            CronTrigger.MISFIRE_INSTRUCTION_DO_NOTHING,
            trigger.getMisfireInstruction());
    }
}
```

This test proves the instruction is configured, **not that Quartz actually executes misfire handling on a JDBC JobStore**.

### 13.2. Integration Testing Quartz Misfires

A real test should:

1. Create a Quartz JDBC JobStore and version-matched schema in a test database.
2. Set `misfireThreshold` small enough and configure a trigger with a controlled overdue fire time.
3. Put the scheduler in standby/paused mode or seed a delayed trigger via fixture, then resume.
4. Record how many times Quartz `Job.execute` is actually called.
5. Compare `DoNothing` and `FireAndProceed`, distinguishing nominal vs. actual fire times.
6. Verify the Batch adapter issues only the requests permitted by business policy.

Tests relying on `Thread.sleep` and millisecond-exact timing are often flaky in CI. Separate policy unit tests from Quartz integration tests; use clear time windows/timeouts and avoid asserting on a single poll before the scheduler finishes processing.

### 13.3. Integration Testing Spring Batch Restart

Set up a two-step job:

```text
prepareStep -> COMPLETED
importStep  -> FAILED after several chunks committed

After error is resolved:
  restart same JobInstance
  prepareStep is typically skipped
  importStep reopens with persisted checkpoint
  job -> COMPLETED
```

Tests should verify:

- Two `JobExecution`s with different IDs share the same `JobInstance`.
- `JobExplorer` reads persisted status and execution context.
- The real reader receives the corresponding checkpoint in `ItemStream.open`.
- No business records are lost or duplicated.
- The slot ledger transitions to `COMPLETED` after the Batch execution finishes.

### 13.4. Testing Zero Executions and Stale Ledgers

Two easily overlooked cases:

**No Batch execution:** scheduler was down across the Nov 11 schedule, ledger has a `PENDING` slot, and `JobRepository` has no instance yet; reconciler must perform the initial launch.

**Batch completed, stale ledger:** job reached `COMPLETED` but the node crashed before updating the ledger; reconciler must update the slot from existing metadata/outputs without launching again.

These are critical tests to prove there is no “gap between the two metadata systems.”

### 13.5. Testing Multi-Day Backlog

```text
Cron: daily at 02:00
Last completed slot: day 10
Resume: day 13 at 09:00
Policy: BACKFILL
Max slots per poll: 2
```

Expected:

- Poll 1: claims day 11 and day 12, leaves day 13 waiting.
- Poll 2 after completion: claims day 13.
- Each nominal slot maps to exactly one `JobInstance`.
- All three slots eventually reach `COMPLETED`.
- Polling again creates no new business executions for completed slots.

If resuming at 01:00 on day 13, the 02:00 day 13 slot is not yet due and must wait until scheduled time.

---

## 14. Observability: Measuring Due Schedules vs. Completed Schedules

A system with many `COMPLETED` `JobExecution`s does not necessarily have every scheduled period covered. Measure both scheduler and business data.

| Suggested metric | Meaning |
| --- | --- |
| `scheduler_trigger_lag_seconds` | Gap between actual fire time − scheduled fire time |
| `batch_due_slots_total` | Count of slots that have fallen due |
| `batch_uncompleted_slots_total` | Count of due slots not yet completed |
| `batch_oldest_pending_age_seconds` | Age of the oldest missing slot |
| `batch_active_executions` | Count of currently running executions |
| `batch_failed_executions_total` | Count of `FAILED` executions |
| `batch_backfill_completed_total` | Total slots successfully backfilled |

These are **illustrative metric names**; applications must collect or map them from existing telemetry.

Example with four timestamps:

```text
scheduled_at = 2026-11-16T02:00:00+07:00
triggered_at = 2026-11-16T02:07:00+07:00
started_at   = 2026-11-16T02:08:00+07:00
completed_at = 2026-11-16T02:20:00+07:00
```

- Scheduler delay = 7 minutes.
- Batch start delay = 8 minutes.
- Batch execution duration = 12 minutes.
- End-to-end delay vs. scheduled time = 20 minutes.

Tracking only the 12-minute batch duration misses the startup lag.

### 14.1. Post-Recovery Scheduler Runbook

1. Identify the exact schedule, timezone, and downtime window.
2. Inspect Quartz trigger state or `@Scheduled`/scheduler diagnostics.
3. List **all business slots** that fell due without a completed outcome.
4. Classify each slot: unlaunched, `RUNNING`, Batch `FAILED`, or Batch `COMPLETED` with stale ledger.
5. Fix the underlying infrastructure cause and confirm no old node is still processing.
6. Apply the agreed policy: SKIP, FIRE_ONCE, COALESCE, BACKFILL, or MANUAL.
7. Bound concurrency/quotas, use stable job parameters, and guard side effects.
8. Monitor until backlog returns to normal and reconcile outputs.

When a Batch execution shows `STARTED` after its process died, follow the metadata verification/recovery procedure for your Spring Batch version; never edit SQL statuses by guesswork to force a restart.

---

## 15. Common Configuration and Design Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| No catch-up callback after downtime | `@Scheduled` lacks persistent misfire history | Build a slot ledger or use a persistent scheduler |
| Quartz loses triggers on restart | `RAMJobStore` or JDBC schema reset | JDBC JobStore + migrations |
| Fires only once after missing three days | `FireAndProceed` | If each day is needed, backfill via ledger |
| Never catches up any missed period | `DoNothing` | Correct for SKIP; wrong for full-period reports |
| Burst of back-to-back fires | `IgnoreMisfires` + backlog | Throttle load and define business policy |
| Duplicate outputs after trigger retries | Each fire generates a new identifying UUID | Stable slot keys + idempotent writer |
| Slot stays `RUNNING` even after Batch finished | Node died before updating ledger | Reconcile from `JobExplorer` |
| Batch `FAILED` yet a new job is launched | Did not restart the old instance | Check status and reuse identifying params |
| Quartz runs overlap in cluster | Different JobKeys, async job, external launcher | Claim slots and distributed admission control |
| Schedule fires at shifted hour | Timezone/DST changes | Explicit `ZoneId`, test DST transitions |
| Quartz tables vanish on deploy | Schema initializer ran drop/create scripts | Managed migrations |
| No alert despite missed schedules | Only alerting on `BatchStatus.FAILED` | Compare expected vs. completed slots |
| Restart lacks checkpoints | Non-persistent metadata DB, `ItemStream` not saving state | JDBC `JobRepository` and stream contract |

**Quick diagnostic tip:** if a slot has no `JobExecution`, inspect the scheduler and admission logic first. If a `JobExecution` exists and is `FAILED`, inspect Batch errors, checkpoints, transactions, and restartability. The two branches have different recovery mechanisms.

---

## 16. Practice Exercises

### Exercise 1 — Observing `@Scheduled` Across Application Shutdown

Create a Spring Boot app with `@Scheduled(cron = "0 * * * * *", zone = "Asia/Ho_Chi_Minh")`. Stop the app across two minute boundaries, then start it again.

Task: observe whether missed callbacks fire; explain why persisting expected slots is needed to recover every minute.

### Exercise 2 — Two CronTriggers with Different Misfire Instructions

Create one trigger with `DoNothing` and one with `FireAndProceed`; use Quartz JDBC JobStore in a test and pause the scheduler past the misfire threshold.

Task: measure actual fire time, scheduled fire time, trigger count, and explain why firing once does not guarantee complete daily reports.

### Exercise 3 — Quota-Bounded Backfill Planner

Use `DailyBackfillPlanner` to pick at most three missing days. Extend the ledger to handle a gap on day 12 when days 11 and 13 already completed.

Task: test slot ordering, quota limits, skipping future dates, and preventing duplicate claims when two reconcilers run concurrently.

### Exercise 4 — Quartz Bridge to Spring Batch

Create `invoiceBatchJob` accepting `scheduled.at.epoch.ms` and `business.date`. Trigger the bridge twice for the same nominal slot.

Task: prove only one logical `JobInstance` is used; explicitly handle executions already `COMPLETED`, `STARTED`, or `FAILED`.

### Exercise 5 — Failure After Batch Commit

Let Batch complete but intentionally skip updating the slot ledger. Then run the reconciler.

Task: inspect metadata and business outputs, move the slot to `COMPLETED`, and assert no new execution is launched just to fix the ledger.

### Exercise 6 — Choosing Policy by Business Domain

Recommend SKIP/FIRE_ONCE/COALESCE/BACKFILL/MANUAL for:

- Cache cleanup every 10 minutes.
- Daily revenue reports.
- Product snapshot synchronization.
- Month-end fund transfer disbursements.

Justify slot retention, SLAs, timezones, concurrency, idempotency keys, and recovery after 72 hours of downtime.

---

## 17. Architectural Conclusion

```text
Quartz / @Scheduled / orchestrator
              |
              v
Policy + persistent schedule-slot ledger
              |
              v
Stable identifying JobParameters per slot
              |
              v
Spring Batch JobLauncher / JobOperator
              |
              v
JobRepository + JobExplorer
              |
       +------+---------+
       |                |
   COMPLETED          FAILED
       |                |
       v                v
 Reconcile slot     Diagnose and restart
       |
       v
 Verify business output
```

The core principle is that **misfires belong to the scheduler, while missed schedules belong to business processing requirements**. Quartz can skip schedules, fire once, or process delayed triggers per instruction, but it does not know whether each day requires an independent report. Spring Batch can restart failed executions from metadata, but it cannot list slots that were never launched.

Whenever every business period must be processed accurately, assign stable slot identities, maintain a durable ledger, reconcile state between the scheduler and `JobRepository`, bound backfills, and verify final outputs.

## 18. References

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Scheduled`, `TaskScheduler`, cron, fixed rate, and fixed delay.
- [Spring Boot — Quartz Scheduler](https://docs.spring.io/spring-boot/reference/io/quartz.html): auto-configuration, JobStore, schema initialization, and trigger registration.
- [Quartz 2.3 — CronTrigger Tutorial](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/crontrigger.html): cron syntax and misfire instructions.
- [Quartz 2.3 — SimpleTrigger Tutorial](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/simpletriggers.html): repeat interval/count and misfire policies.
- [Quartz — Configuration Reference](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/configuration/): JobStore, thread pool, and misfire threshold.
- [Spring Batch — Configuring and Running a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): job parameters, job instance/execution, and restart.
- [Spring Batch — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): `JobOperator`, `JobExplorer`, and operations.
- [Spring Batch — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): `BATCH_*` tables.
