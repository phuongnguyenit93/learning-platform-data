# Misfires, Overlap, and Recovery Policies in Quartz

> **Chapter:** Quartz  
> **Module:** SPRING_BOOT_INTEGRATION — organizing integration in Spring Boot across HTTP clients, databases, caches, message brokers, and Spring Integration adapters; emphasizing configuration, data contracts, transactions, errors, deduplication, testing, and observability.  
> **Goal:** Design Quartz schedules that avoid unintended overlapping runs, understand misfire instructions, choose recovery behavior when a process/node crashes, and protect business logic from duplicate execution.

A payment reconciliation job is scheduled to run every 5 minutes. At 10:00, the job calls an external system and takes 8 minutes. Meanwhile, the 10:05 and 10:10 trigger times arrive. At 10:12, a Spring Boot node fails and restarts. How many times will Quartz run, on the old schedule or immediately, and could reconciliation run twice?

The answer depends on **three distinct mechanisms**:

1. **Misfire policy** determines how to handle a scheduled firing missed beyond the threshold.
2. **Concurrency policy** determines whether executions of the **same `JobKey`** may run concurrently.
3. **Recovery policy** determines whether Quartz attempts to re-execute an interrupted job after a scheduler crash.

None of these three equates to **exactly-once processing**. Even when Quartz runs only one job at a time, an HTTP request or message already received by downstream systems can still be resent after a failure. That is why integration jobs also need **idempotency**, durable state storage, and reconciliation.

## 1. Terms to Distinguish

| Concept | Meaning | Does Not Guarantee |
| --- | --- | --- |
| **Job** | Java class implementing **`org.quartz.Job`**, defining work executed when Quartz calls **`execute(...)`** | Does not automatically span a transaction across external systems |
| **JobDetail** | Job definition with **`JobKey`** identity, class type, data, and **`requestRecovery`** flag | Does not represent a single execution |
| **Trigger** | Rule generating fire times; has **`TriggerKey`**, next fire time, state, and misfire instruction | Does not store every pending business task |
| **Fire / execution** | One instance of the scheduler granting execution to a `JobDetail` | Does not guarantee side effects occur once |
| **Misfire** | A trigger fails to fire on time and is handled per misfire policy after the delay threshold | Does not imply every missed slot is replayed |
| **Disallow concurrent execution** | Prevents concurrent instances sharing the **same `JobDetail`/`JobKey`** | Does not block other `JobDetail`s or apps not sharing the JobStore |
| **Recovery** | Mechanism attempting to rerun a job interrupted mid-execution when a scheduler/node dies, if recovery is requested and JobStore supports it | Does not roll back or recover partially committed HTTP/DB transactions |
| **Idempotency** | Reprocessing the same operation without producing duplicate business side effects | Does not detect missing work automatically without reconciliation state |

Quartz manages **trigger schedules** and **execution lifecycles**. Which orders updated, which payments settled, which broker events emitted, and which tasks remain pending are business data the application must manage.

## 2. When Does a Trigger Become a Misfire?

Suppose a `CronTrigger` is due at 10:00, 10:05, and 10:10. The scheduler stops or lacks free worker threads and only recovers at 10:12:

~~~mermaid
timeline
    title Expected fire times and when scheduler becomes ready again
    10:00 : First expected fire
    10:05 : Second expected fire
    10:10 : Third expected fire
    10:12 : Scheduler resumes
~~~

Quartz compares **`nextFireTime`** against the current time and the JobStore's **`misfireThreshold`**. If the trigger is late enough, the JobStore applies the matching misfire instruction. Common causes include:

- The scheduler was shut down, a node was killed, or the service redeployed.
- Worker threads were tied up by long-running jobs, leaving no free threads for new triggers.
- The scheduler entered standby mode, or the trigger was paused and resumed.
- JDBC JobStore could not reach the database, or suffered connection pool saturation or locks.
- A node hung, suffered long GC pauses, CPU starvation, or elevated infrastructure latency.

A common Quartz setting is:

~~~properties
org.quartz.jobStore.misfireThreshold=60000
~~~

**60,000 ms** is a widely used default threshold in Quartz JobStore; check your application's effective configuration. Do not interpret this as a strict 60-second timer that instantly flags misses: detection also depends on JobStore polling intervals and when the scheduler acquires triggers.

**Distinguish minor lag from misfire:** a firing delayed by a few seconds due to busy systems is merely scheduling lag, not yet exceeding the misfire threshold. Once marked misfired, a trigger is updated per its instruction, which can alter `nextFireTime` and future execution counts.

## 3. CronTrigger Misfires: Run Once Now or Skip?

`CronTrigger` uses Quartz cron expressions, such as **`0 0/5 * * * ?`** meaning every 5 minutes at second 0. Quartz cron includes a **seconds field**, unlike familiar 5-field Unix cron.

With **`CronScheduleBuilder`**, the key choices are:

| Option | API | Upon Resuming After Downtime |
| --- | --- | --- |
| **Fire once now** | **`withMisfireHandlingInstructionFireAndProceed()`** | Executes once immediately upon handling misfire, then continues the cron schedule |
| **Do nothing** | **`withMisfireHandlingInstructionDoNothing()`** | Discards missed firings; picks the next valid cron point after now |
| **Ignore misfires** | **`withMisfireHandlingInstructionIgnoreMisfires()`** | Bypasses standard misfire handling; may fire consecutively to catch up on missed times |

**SMART_POLICY** is the default when no explicit instruction is selected. For Quartz `CronTrigger`, SMART_POLICY maps to **`FIRE_ONCE_NOW`** in standard misfire handling. Still, declare the policy explicitly so operators know whether the system intends to **catch up once** or **skip**.

### 3.1. Configuring CronTrigger Without Catch-Up

~~~java
import java.util.TimeZone;
import org.quartz.CronScheduleBuilder;
import org.quartz.JobDetail;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;

Trigger cron = TriggerBuilder.newTrigger()
        .withIdentity("invoice-reconciliation-trigger", "billing")
        .forJob(reconciliationJobDetail)
        .withSchedule(CronScheduleBuilder
                .cronSchedule("0 0/5 * * * ?")
                .inTimeZone(TimeZone.getTimeZone("Asia/Ho_Chi_Minh"))
                .withMisfireHandlingInstructionDoNothing())
        .build();
~~~

This example references **`reconciliationJobDetail`** initialized in the complete configuration section below. If the scheduler resumes at 10:12, **`DO_NOTHING`** advances the next fire time to 10:15 (assuming the trigger remains active, no exclusions apply, and matching time zone).

This choice fits when:

- The job refreshes caches, reads current metrics, or updates the **latest** state.
- Each run queries **all overdue work** from the database rather than treating each tick as representing one business period.
- Firing stale ticks adds no value and risks overloading systems after downtime.

### 3.2. Configuring CronTrigger to Run Once After Misfire

~~~java
Trigger catchUpOnce = TriggerBuilder.newTrigger()
        .withIdentity("catch-up-once", "billing")
        .forJob(reconciliationJobDetail)
        .withSchedule(CronScheduleBuilder
                .cronSchedule("0 0/5 * * * ?")
                .inTimeZone(TimeZone.getTimeZone("Asia/Ho_Chi_Minh"))
                .withMisfireHandlingInstructionFireAndProceed())
        .build();
~~~

If 10:00, 10:05, and 10:10 were missed, this policy **does not promise three separate runs**. It typically triggers **one immediate execution** to handle the misfire and then returns to the cron schedule. Therefore, never calculate how many records to process from missed fire counts.

For daily reconciliation, a safer pattern is having the job **query unreconciled dates/documents from the database**. A single post-restart firing can process multiple missing days without replaying every historical cron tick.

### 3.3. Why Limit Use of IGNORE_MISFIRE_POLICY?

Ignoring misfire handling can cause overdue firings to execute in rapid bursts. A job sending periodic emails or calling rate-limited APIs can unleash a flood of requests right as a node recovers. Only use this policy when you understand exact firing counts, downstream load, deduplication, and time bounds.

A misfire policy is not a **durable queue for individual business tasks**. If every billing period must be processed, persist the billing periods durably; Quartz merely wakes up the worker to execute them.

## 4. SimpleTrigger Misfires: Repeat Counts Affect Outcomes

`SimpleTrigger` runs on fixed intervals or bounded repeat counts. Example:

~~~java
import org.quartz.SimpleScheduleBuilder;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;

Trigger heartbeat = TriggerBuilder.newTrigger()
        .withIdentity("heartbeat", "integration")
        .forJob(reconciliationJobDetail)
        .withSchedule(SimpleScheduleBuilder.simpleSchedule()
                .withIntervalInMinutes(5)
                .repeatForever()
                .withMisfireHandlingInstructionNextWithRemainingCount())
        .build();
~~~

Options on **`SimpleScheduleBuilder`**:

| API | Primary Intent |
| --- | --- |
| **`withMisfireHandlingInstructionFireNow()`** | Moves a single firing to the current time |
| **`withMisfireHandlingInstructionNowWithExistingCount()`** | Reschedules starting now while keeping existing repeat count rules |
| **`withMisfireHandlingInstructionNowWithRemainingCount()`** | Reschedules from now and adjusts remaining repeat counts for elapsed intervals |
| **`withMisfireHandlingInstructionNextWithExistingCount()`** | Advances to the next scheduled point while keeping existing repeat count |
| **`withMisfireHandlingInstructionNextWithRemainingCount()`** | Advances to the next scheduled point and recalculates remaining repeat counts |
| **`withMisfireHandlingInstructionIgnoreMisfires()`** | Bypasses standard misfire handling |

For finite `SimpleTrigger`s, the difference between **existing count** and **remaining count** decides how many runs occur after downtime. With **`repeatForever()`**, there is no finite repeat count to preserve. Test exact timestamps (`startAt`, `endAt`, repeat interval, repeat count) rather than guessing from API names alone.

Do not pick **`SMART_POLICY`** just because it looks shorter: Quartz interprets `SimpleTrigger` `SMART_POLICY` differently depending on repeat count and schedule settings. When exact execution counts matter, specify the policy explicitly and test delay scenarios.

## 5. Overlap: Two Executions Running at the Same Time

A job scheduled every 5 minutes occasionally takes 8 minutes to complete. If multiple worker threads are available, Quartz can start another execution of the same `JobDetail` while the previous one is still running, **unless concurrency protection is applied**.

~~~mermaid
gantt
    title 5-minute schedule, 8-minute runtime
    dateFormat HH:mm
    axisFormat %H:%M
    section Without overlap protection
    Fire A :a1, 10:00, 8m
    Fire B :a2, 10:05, 8m
    Fire C :a3, 10:10, 8m
~~~

Overlapping runs can cause:

- The same invoice billed twice, or two jobs updating the same row simultaneously.
- Two batches scanning the same **`PENDING`** records, issuing duplicate downstream calls.
- Two jobs writing caches, indexes, or output files in unpredictable order.
- Connection pool/HTTP pool exhaustion as concurrent jobs stack up.

### 5.1. Using `@DisallowConcurrentExecution`

~~~java
import org.quartz.DisallowConcurrentExecution;
import org.quartz.Job;
import org.quartz.JobExecutionContext;
import org.quartz.JobExecutionException;

@DisallowConcurrentExecution
public class ReconciliationJob implements Job {
    @Override
    public void execute(JobExecutionContext context)
            throws JobExecutionException {
        // Call logic to process missing reconciliation periods.
        // Full implementation in Section 8.
    }
}
~~~

The **`@DisallowConcurrentExecution`** annotation instructs Quartz not to execute two instances of the same **`JobDetail`/`JobKey`** concurrently. Watch out for this common misconception:

~~~text
Job class = ReconciliationJob

JobKey("daily", "billing")   -> prevents overlap among firings of "daily"
JobKey("hourly", "billing")  -> prevents overlap among firings of "hourly"

Two different JobKeys sharing ReconciliationJob
-> can still run concurrently with each other.
~~~

If multiple `Trigger`s target **the same `JobDetail`**, the annotation applies to that shared `JobKey`. If each node creates `JobDetail`s with distinct keys or uses **separate `RAMJobStore`s**, Quartz has no shared boundary to coordinate.

**Blocking overlap does not discard delayed runs.** Triggers retain their schedules and states; firings delayed by an active job can become misfires once the threshold passes. Once the active job finishes, Quartz applies the misfire policy to decide the next run.

### 5.2. Persisting JobDataMap After Execution

**`@PersistJobDataAfterExecution`** tells Quartz to save updates made to `JobDataMap` after execution completes. If a job modifies `JobDataMap` state, pair it with **`@DisallowConcurrentExecution`** so two executions do not overwrite each other's updates:

~~~java
import org.quartz.DisallowConcurrentExecution;
import org.quartz.PersistJobDataAfterExecution;

@PersistJobDataAfterExecution
@DisallowConcurrentExecution
public class StatefulPollingJob implements Job {
    @Override
    public void execute(JobExecutionContext context) {
        var data = context.getJobDetail().getJobDataMap();
        long cursor = data.containsKey("lastSeenId")
                ? data.getLong("lastSeenId") : 0L;
        // Process cursor per business rules ...
        data.put("lastSeenId", cursor + 1);
    }
}
~~~

**Note:** `JobDataMap` does not replace a business database table for critical checkpoints. Never put service/connection objects or non-serializable payloads into a persistent JobStore's `JobDataMap`. If external systems applied a change before Quartz persisted the updated cursor and the process crashed, the next run may repeat work; idempotency at the target remains necessary.

### 5.3. Blocking Overlap Does Not Stop Duplicates When Two Nodes Don't Share a JobStore

If two Spring Boot instances deploy the same schedule yet **each holds its own `RAMJobStore`**, both can fire the job at 10:00. The annotation only guards concurrency within the scope managed by the scheduler/JobStore. To have Quartz distribute schedules across nodes, use a **clustered JDBC JobStore** sharing the same database/scheduler settings and distinct **`instanceId`**s per node.

Even in a valid cluster, tasks calling external systems must still guard against duplicates from network errors and recovery.

## 6. Recovery: What Does Quartz Do When a Scheduler or Node Crashes?

Distinguish two categories of work after downtime:

1. **Triggers that did not fire on time:** classified as **misfires** and handled per the trigger's misfire policy.
2. **Jobs already running when a node died mid-execution:** can be **re-executed** by Quartz if the **`JobDetail` requests recovery** and the JobStore/persistence detects the interrupted run.

When building `JobDetail`:

~~~java
import org.quartz.JobBuilder;
import org.quartz.JobDetail;

JobDetail detail = JobBuilder.newJob(ReconciliationJob.class)
        .withIdentity("reconcile-overdue-periods", "billing")
        .requestRecovery(true)
        .storeDurably()
        .build();
~~~

Inside the job, you can inspect:

~~~java
if (context.isRecovering()) {
    // Quartz is launching a recovery execution for work
    // interrupted by an earlier scheduler failure.
    log.warn("Recovery execution for jobKey={}",
             context.getJobDetail().getKey());
}
~~~

**`requestRecovery(true)`** does not mean Quartz replays every missed cron tick. It applies to **jobs actively executing when a scheduler dies**. Without this flag, Quartz does not automatically recover interrupted executions; subsequent triggers after restart follow normal trigger state and misfire policies.

### 6.1. Why Can Recovery Still Produce Duplicate Side Effects?

~~~mermaid
sequenceDiagram
    participant Q as Quartz Node A
    participant DB as Business DB
    participant X as External Payment API
    participant B as Quartz Node B
    Q->>DB: Mark task in progress
    Q->>X: POST /charge idempotencyKey=invoice-42
    X-->>Q: 200 OK
    Note over Q: Node A crashes before saving DONE status
    B->>B: Detect failed instance
    Note over B: Recover job if requestsRecovery=true
    B->>X: POST /charge idempotencyKey=invoice-42
    Note over X: Returns prior result by idempotency key
    X-->>B: Existing charge result
    B->>DB: Save DONE
~~~

If the Payment API **does not** support idempotency, the second request can charge again. Quartz cannot know the 200 response happened prior to the crash, because external outcomes do not share a transaction with Quartz JobStore.

For jobs touching money, inventory, emails, message brokers, or document generation, require:

- **Stable business operation keys** across retries and recovery, such as **`invoiceId`**, **`orderId + actionType`**, or **`jobType + businessPeriod`**.
- `UNIQUE` constraints/checkpoints in the database and/or downstream-recognized idempotency keys.
- Explicit states **`PENDING / RUNNING / DONE / FAILED / NEEDS_REVIEW`** to track remaining work.
- Retries with backoff and attempt limits; when remote outcomes are unknown, **query status** before repeating non-idempotent commands.
- Reconciliation processes comparing local and remote state after ambiguous failures.

**Never use `fireInstanceId` or current timestamps as idempotency keys** for crash-recoverable operations. Those values change between the original execution and recovery, making downstream systems treat them as distinct requests.

### 6.2. Recovery Differs from Exception Retries

A running job **throwing `JobExecutionException`** is a normal execution error while the scheduler remains alive. Quartz provides no built-in exponential backoff strategy for arbitrary exceptions.

~~~java
try {
    reconciliationService.reconcileDuePeriods();
} catch (RuntimeException ex) {
    // Signal failure to Quartz;
    // avoid infinite refireImmediately loops.
    throw new JobExecutionException("Reconciliation failed", ex);
}
~~~

**`JobExecutionException.setRefireImmediately(true)`** requests immediate refiring; it has no backoff and easily causes tight loops when target systems are down. Flags also exist to unschedule the firing trigger or all triggers, which must follow clear operational policies. For transient integration errors, it is usually safer to persist retryable failure state and let the next scheduled tick or a bounded retry trigger handle it.

**Recovery** handles a scheduler dying mid-execution; **retry** handles errors observed by the job; **misfire** handles triggers missing their scheduled time. Never try to make one mechanism replace the other two.

## 7. Persistent JobStore and Clustering in Spring Boot

**`RAMJobStore`** stores schedules in a single scheduler's memory. After process death/restart, `JobDetail`/`Trigger` are recreated from app config if declared; no persisted history remains to recover interrupted state the way JDBC JobStore can.

**JDBC JobStore** persists schedules, trigger state, and coordination metadata in a database. In a cluster, nodes share **the same Quartz tables** and coordinate trigger acquisition; when one node dies, another can detect and recover work per configuration.

### 7.1. Sample Configuration

~~~yaml
spring:
  quartz:
    job-store-type: jdbc
    jdbc:
      # Use controlled migrations to provision schema before running.
      initialize-schema: never
    wait-for-jobs-to-complete-on-shutdown: true
    properties:
      org:
        quartz:
          scheduler:
            instanceName: BillingQuartzCluster
            instanceId: AUTO
          jobStore:
            isClustered: true
            clusterCheckinInterval: 20000
            misfireThreshold: 60000
          threadPool:
            threadCount: 8
~~~

This example applies once **Quartz tables** matching your Quartz version exist and the datasource is configured in Spring Boot. Use Flyway/Liquibase or database migration workflows to manage the schema. If using auto-initialization for Quartz schemas, inspect your version's scripts carefully because some sample scripts **drop existing tables**; never run destructive schema init modes in production.

**Caution with Spring Boot auto-configuration:** Spring Boot provides `SchedulerFactoryBean` and DataSource-backed JobStore integration. Manually overriding **`org.quartz.jobStore.class`** from plain Quartz guides can break Spring-managed datasource and transaction manager integration. Only change it if you thoroughly understand the active JobStore mechanics and have tested restarts and clustering.

Operational requirements:

| Component | Rule |
| --- | --- |
| **Quartz database** | All cluster nodes point to the same Quartz tables, compatible schema, and adequately sized connection pool |
| **instanceName** | Identical across nodes in the same scheduler cluster |
| **instanceId** | Unique per instance; `AUTO` works cleanly in most deployments |
| **Clocks** | System clocks synchronized (NTP) to prevent trigger/recovery drift |
| **Clustered flag** | Enabled consistently across nodes sharing the JobStore; never mix clustered and non-clustered nodes on the same tables |
| **Thread pool** | Caps concurrent jobs; factor in time jobs spend blocked on I/O |
| **Shutdown** | Graceful shutdown aligned with job durations and container termination limits; not guaranteed if killed abruptly |
| **Deployments** | Avoid overwriting/rescheduling or deleting persisted triggers unintentionally on every startup |

Do not treat **`clustering=true`** as a global distributed lock for arbitrary app code: it coordinates registered Quartz jobs/triggers. If a worker outside Quartz processes the same business tasks, both can still contend on resources; enforce claims and uniqueness at the business layer.

## 8. Complete Example: Safe Schedule Waking Up a Reconciliation Job

Pattern: every 5 minutes, Quartz wakes up the job; the job invokes a service to find **business periods not yet `DONE`** and processes them by business key. If cron ticks are delayed, stale ticks can be skipped because missing business periods stay persisted in the DB.

### 8.1. JobDetail + CronTrigger with Explicit Policies

~~~java
package example.integration.quartz;

import java.util.TimeZone;
import org.quartz.CronScheduleBuilder;
import org.quartz.JobBuilder;
import org.quartz.JobDetail;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ReconciliationQuartzConfiguration {

    @Bean
    public JobDetail reconciliationJobDetail() {
        return JobBuilder.newJob(ReconciliationJob.class)
                .withIdentity("reconcile-overdue-periods", "billing")
                .withDescription("Scan durable pending business periods")
                .requestRecovery(true)
                .storeDurably()
                .build();
    }

    @Bean
    public Trigger reconciliationTrigger(
            JobDetail reconciliationJobDetail) {
        return TriggerBuilder.newTrigger()
                .withIdentity("reconcile-every-five-minutes", "billing")
                .forJob(reconciliationJobDetail)
                .withSchedule(CronScheduleBuilder
                        .cronSchedule("0 0/5 * * * ?")
                        .inTimeZone(TimeZone.getTimeZone("Asia/Ho_Chi_Minh"))
                        .withMisfireHandlingInstructionDoNothing())
                .build();
    }
}
~~~

Choosing **`DO_NOTHING`** here skips **missed cron timestamps**, not pending business data. To ensure that, **`reconcileDuePeriods()`** must query the database backlog rather than only processing **one** period derived from the latest fire time.

### 8.2. Non-Overlapping Job for the Same JobKey

~~~java
package example.integration.quartz;

import org.quartz.DisallowConcurrentExecution;
import org.quartz.Job;
import org.quartz.JobExecutionContext;
import org.quartz.JobExecutionException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@DisallowConcurrentExecution
public class ReconciliationJob implements Job {
    private static final Logger log =
            LoggerFactory.getLogger(ReconciliationJob.class);
    private final ReconciliationService service;

    public ReconciliationJob(ReconciliationService service) {
        this.service = service;
    }

    @Override
    public void execute(JobExecutionContext context)
            throws JobExecutionException {
        log.info("Quartz fire job={}, scheduledAt={}, recovering={}",
                context.getJobDetail().getKey(),
                context.getScheduledFireTime(),
                context.isRecovering());

        try {
            service.reconcileDuePeriods();
        } catch (RuntimeException ex) {
            log.error("Quartz reconcile failed, job={}",
                    context.getJobDetail().getKey(), ex);
            throw new JobExecutionException(
                    "Reconcile failed; pending periods remain durable", ex);
        }
    }
}
~~~

This example uses **constructor injection** on the Quartz job; for that to work, the environment must supply a **Spring-DI-capable `JobFactory`**. One explicit configuration for this example:

~~~java
package example.integration.quartz;

import org.quartz.Job;
import org.quartz.spi.JobFactory;
import org.springframework.beans.factory.config.AutowireCapableBeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class QuartzJobFactoryConfiguration {
    @Bean
    public JobFactory jobFactory(AutowireCapableBeanFactory beanFactory) {
        return (bundle, scheduler) ->
                (Job) beanFactory.createBean(
                        bundle.getJobDetail().getJobClass());
    }
}
~~~

This `JobFactory` only illustrates constructor injection; if the app already defines a custom `JobFactory`, integrate with existing configuration instead of registering duplicates. When customizing the factory, verify **`JobDataMap`** injection or other instantiation rules. Spring Boot may support job autowiring differently depending on version and configuration.

### 8.3. Service Processing Backlog by Business Key

Suppose the database holds a table of periods needing reconciliation:

~~~sql
CREATE TABLE reconciliation_period (
    business_date DATE PRIMARY KEY,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('PENDING', 'RUNNING', 'DONE', 'FAILED')),
    lease_owner VARCHAR(100),
    lease_until TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_reconciliation_due
    ON reconciliation_period (status, business_date);

CREATE TABLE daily_settlement (
    business_date DATE PRIMARY KEY,
    total_amount NUMERIC(18, 2) NOT NULL,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
~~~

**`business_date`** acts as the idempotency key for **`daily_settlement`**. If a date was already calculated and a worker reruns, upserting avoids duplicate rows:

~~~sql
INSERT INTO daily_settlement (business_date, total_amount)
VALUES (:businessDate, :totalAmount)
ON CONFLICT (business_date)
DO UPDATE SET
    total_amount = EXCLUDED.total_amount,
    calculated_at = NOW();
~~~

This upsert assumes the calculation can rerun cleanly with consistent inputs and cutoffs. If outcomes depend on evolving transactions over time, use **snapshots/cutoffs/versions** or adjustment entries so reruns never silently alter finalized reports.

When multiple workers process the backlog, use a short transaction to **claim** each period with a lease instead of holding transactions open across HTTP calls:

~~~sql
-- PostgreSQL: only one worker successfully claims this period.
UPDATE reconciliation_period
SET status = 'RUNNING',
    lease_owner = :workerId,
    lease_until = NOW() + INTERVAL '2 minutes',
    updated_at = NOW()
WHERE business_date = :businessDate
  AND (
       status IN ('PENDING', 'FAILED')
       OR (status = 'RUNNING' AND lease_until < NOW())
  )
RETURNING business_date;
~~~

**0 rows returned** means the worker did not acquire the right to process that period right now. If processing exceeds the lease, renew it safely. When writing final results, check **`lease_owner`/fencing tokens** so a stale worker never overwrites a newer worker's success; leases coordinate workers, without replacing DB and downstream idempotency.

A conceptual orchestrating service:

~~~java
@Service
public class ReconciliationService {
    private final PeriodRepository periods;
    private final ReconciliationWorker worker;

    public ReconciliationService(PeriodRepository periods,
                                 ReconciliationWorker worker) {
        this.periods = periods;
        this.worker = worker;
    }

    public void reconcileDuePeriods() {
        for (LocalDate day : periods.findPendingOrExpired(100)) {
            worker.tryClaimAndReconcile(day);
        }
    }
}
~~~

**`PeriodRepository`** and **`ReconciliationWorker`** are application-defined business abstractions illustrating responsibility boundaries, not built-in Quartz APIs. **`tryClaimAndReconcile`** should separate short claim transactions, external processing, result writes, and completion updates into appropriate transactions. With HTTP or brokers, use **outbox + idempotent consumers** or API idempotency keys; never wrap external side effects in one JDBC **`@Transactional`** assuming cross-system atomicity.

### 8.4. Why Do `requestRecovery(true)` and `DO_NOTHING` Work Well Together?

- **`DO_NOTHING`** skips **missed cron timestamps** during downtime.
- **`requestRecovery(true)`** requests recovery for **jobs already started and interrupted by a scheduler crash**.
- **`@DisallowConcurrentExecution`** keeps executions sharing a **`JobKey`** from overlapping when managed by Quartz.
- **Database backlogs + business idempotency** ensure missed periods are still discovered and safely processed even across repeated executions.

This pattern suits many integration jobs: the scheduler is strictly an **alarm clock**, while durable business data remains the source of truth for pending work.

## 9. Choosing Policies Based on Workload Nature

| Job Type | Misfire Policy to Consider | Overlap | Recovery and Data |
| --- | --- | --- | --- |
| **Cache refresh** from primary source | `DO_NOTHING` if the next run refreshes everything | Usually disallow per `JobKey` | Safe to rerun; no need to replay every tick |
| **Outbox/inbox backlog sweep** | `DO_NOTHING` or `FIRE_ONCE_NOW` | Disallow overlap, or shard safely with worker claims | Store backlog in DB; retries and idempotent consumers |
| **Periodic invoice reconciliation** | `DO_NOTHING` if sweeping overdue periods; `FIRE_ONCE_NOW` to wake immediately after restart | Disallow per `JobKey` + unique business period | `requestRecovery` + checkpoints/leases + reconciliation |
| **Daily report generation** | Choose per SLA deadline; never infer missed dates from fire counts | Prevent generating same report twice | Store **`reportType + businessDate`** key and publication status |
| **Sending emails/notifications** | Never replay ticks blindly; track pending sends durably | Disallow or batch via claims | Outbox, `messageId`, deduplication, rate limiting |
| **Charging money / irreversible actions** | Never auto `FIRE_NOW` without checking prior period state | Disallow, yet idempotency remains vital | Downstream idempotency key and status queries on timeout |
| **Heartbeat/health probe** | `DO_NOTHING`; no value firing for the past | Can skip if previous run is still active | Do not treat tick history as business work |

If business rules mandate running **every period** regardless of downtime, the core solution is persisting **per-period work units** in the database and backfilling them. Misfire settings only decide **when workers are woken up**, not end-to-end business completeness.

## 10. Incident Matrix and Expected Outcomes

| Incident | What Quartz Can Do | What the Application Must Add |
| --- | --- | --- |
| Job runs longer than period | Overlaps unless disallowed; if disallowed, next run waits and may misfire | `@DisallowConcurrentExecution`, thread bounds, idempotent tasks |
| Scheduler down for 20 minutes | Updates triggers per misfire instruction after restart | Scan backlog if every period must be processed |
| Node dies mid-REST call | Recovers execution if `requestRecovery` and JobStore support it | REST idempotency key; query status when outcome is unknown |
| Node dies after DB commit before sending event | Quartz may rerun the job | Transactional outbox in same DB and publisher retries |
| Broker receives event then ACK is lost | Quartz cannot know exact broker side effect | Stable `eventId` and consumer deduplication/inbox |
| Two nodes run independent `RAMJobStore`s | Each node runs its own schedule | Move to JDBC cluster or external leader/claim coordination |
| JDBC cluster loses DB | Cannot acquire/commit triggers normally | DB alerts, retries, backlog recovery once DB returns |
| Cron time zone change or DST | Next fire time shifts with time zone, cron, and calendar | Explicit time zone/cutoffs; test DST transitions if applicable |
| Job throws exception | Execution fails; no built-in exponential retry | `FAILED` status, bounded retries, alerts |
| Worker loses lease while still running | Another worker may claim the same period | Fencing tokens, unique keys, idempotent side effects |

## 11. Observing Scheduler and Business Health

When a job runs slowly or stops running, separate **scheduling** from **business execution**. Track:

| Metric/Log Group | Example Data |
| --- | --- |
| **Scheduling lag** | Delta **`actual fire time - scheduled fire time`** |
| **Execution duration** | Job run duration, p95/p99 percentiles, jobs exceeding limits |
| **Misfires** | Misfired triggers by group, policy, and delay duration |
| **Recovery** | Counts of **`isRecovering=true`**, errors during recovery |
| **Overlap/blocked** | Blocked triggers, busy Quartz workers, thread pool utilization |
| **Backlog** | `PENDING` period count, oldest pending age, `RUNNING` tasks past lease |
| **Business success** | `DONE`, `FAILED`, `NEEDS_REVIEW` period counts, prevented duplicates |
| **Downstream** | HTTP timeouts, retries, rate limits, broker lag, DLQs, unpublished outbox rows |

Quartz provides **`JobListener`**, **`TriggerListener`**, and **`SchedulerListener`** to capture scheduling events. Misfires are observed via **`TriggerListener.triggerMisfired(...)`**; never rely solely on logging inside **`Job.execute(...)`** to detect misfires, since skipped triggers never execute.

Include **`JobKey`**, **`TriggerKey`**, **`scheduledFireTime`**, **`fireTime`**, **`isRecovering`**, **`businessPeriod`**, **`correlationId`**, and **`attempt`** in logs where available. Never use **`fireInstanceId`** as a business idempotency key; reserve it for distinguishing executions in logs and diagnostics.

Quartz metrics never replace business metrics. A scheduler can happily report successful firings while **`reconciliation_period`** piles up overdue tasks. Alert on **backlog age**, convergence rates, and local-vs-downstream drift.

## 12. Testing Misfires, Overlap, and Recovery Scenarios

Tests must deliberately create **failure windows**, not just verify a job runs once.

### 12.1. CronTrigger Misfires

1. Create a short-interval cron trigger in a test environment configured with **`DO_NOTHING`**.
2. Pause the scheduler or trigger longer than **`misfireThreshold`**, then resume.
3. Verify no burst of catch-up firings occurs and `nextFireTime` advances to a valid future slot.
4. Repeat with **`FIRE_ONCE_NOW`**, verifying one misfire execution fires and the schedule continues.

When testing business date logic, inject a **`Clock`** to control time; when testing live Quartz, use reasonable timeouts and polling assertions. Never tie unit tests to exact milliseconds that turn flaky under CI load.

### 12.2. Overlap by JobKey

1. Start the first job with a latch holding it in the running state.
2. Fire a second trigger bound to **the same `JobDetail`**.
3. Assert at most one execution of that `JobKey` runs concurrently when **`@DisallowConcurrentExecution`** is present.
4. Create two `JobDetail`s with distinct keys sharing the same class and prove the annotation does not protect shared business resources across keys.

### 12.3. Restarts and Cluster Failover

1. Run two scheduler instances sharing a **JDBC JobStore** in an integration test with a real database (e.g., PostgreSQL Testcontainers).
2. Assign a job with **`requestRecovery(true)`** to node A and have it signal once started.
3. Abruptly kill node A and wait for the cluster to detect the dead instance.
4. Observe node B launching recovery (**`isRecovering=true`**) and verify business state holds only one logical record/side effect thanks to idempotency keys.
5. Also test jobs **without** `requestRecovery` and misfired triggers after downtime.

**Do not use graceful shutdown to simulate a process crash** when testing recovery: graceful shutdown waits for running jobs to finish and leaves no abandoned in-progress work.

### 12.4. Testing Real Integration Failures

- Process crashes **after downstream HTTP succeeds but before saving `DONE`**.
- Process crashes **after DB commit but before outbox publishing**.
- Broker receives an event yet publisher **misses the ACK**.
- Processing a `businessPeriod` outlasts its lease and a second worker reclaims it.
- Scheduler paused across multiple cron ticks; backlog still drains completely by business keys.
- One node loses connections or the JDBC database drops temporarily; jobs resume smoothly once connectivity returns.

Assert **final business state, zero duplicates, and self-recovery**, not just how many times **`execute(...)`** ran.

## 13. Common Deployment Misconceptions

**"If a job is one minute late, it definitely misfires at exactly one minute."** Misfire threshold is an evaluation threshold, not a hard timer; exact detection still depends on JobStore sweeps and trigger acquisition cycles.

**"Cron `FIRE_ONCE_NOW` catches up all 12 missed ticks."** It typically performs one immediate firing after misfire, without replaying every missed tick. Persist business periods if every period must be processed.

**"`@DisallowConcurrentExecution` blocks all instances of that class across every app."** The annotation applies per **`JobKey`** within the managed scheduler/cluster. Different `JobKey`s or separate `RAMJobStore`s can still run concurrently.

**"`@PersistJobDataAfterExecution` turns `JobDataMap` into a transactional checkpoint for REST."** `JobDataMap` lives strictly inside Quartz JobStore. Remote APIs may commit while `JobDataMap` has not been updated yet.

**"`requestRecovery(true)` guarantees exactly-once."** Recovery can re-run work that already produced side effects before crashing. Idempotency and reconciliation remain your responsibility.

**"If the scheduler fails, just set `refireImmediately` until it succeeds."** Immediate retries without backoff create tight loops, overload downstream services, and starve other triggers.

**"Just put `@Transactional` on `Job.execute` to roll back HTTP/Kafka."** Local database transactions cannot roll back already-committed external side effects; use outboxes, idempotency, or compensations depending on the workflow.

**"With JDBC enabled, skipping clustering still runs once system-wide."** Sharing Quartz tables requires consistent cluster settings, unique instance IDs, and matching DB/schemas. Never mix clustered and non-clustered nodes on the same tables.

**"Zero misfires means zero lost data."** The scheduler may run right on schedule while processing logic drops records or consumers receive duplicates. Quartz does not verify business correctness.

## 14. Pre-Production Checklist

- Confirm **`JobKey`**, **`TriggerKey`**, time zone, schedule, misfire instruction, and business deadlines for every job.
- Distinguish **skipping old ticks**, **firing once immediately**, and **guaranteeing every business period**.
- Apply **`@DisallowConcurrentExecution`** when the same `JobKey` must not overlap; design business claims/unique keys if multiple workers or external apps touch the same data.
- Enable **`requestRecovery(true)`** when interrupted work must be retried, while ensuring external side effects are safe to repeat.
- For multi-node setups, verify **JDBC JobStore clustering**, schema, `instanceId`, recovery behavior, and clock sync.
- Tune timeouts, DB/HTTP pools, `threadCount`, shutdown grace periods, and backoff so jobs never exhaust shared resources.
- Use stable idempotency keys, local transactions, outbox/inbox tables, or compensations matching workflow criticality.
- Maintain backlog/checkpoint tables, leases/fencing tokens if required, dashboards, alerts, and automated reconciliation tasks.
- Test misfires, overlap, sudden crashes, duplicate deliveries, and remote timeouts in integration environments.

## References

- [Quartz Scheduler — Tutorial: More About Triggers](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/tutorial-lesson-04.html)
- [Quartz Scheduler — Tutorial: CronTrigger](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/tutorial-lesson-06.html)
- [Quartz Scheduler — Configuration Reference](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/configuration/)
- [Spring Boot — Quartz Scheduler](https://docs.spring.io/spring-boot/reference/io/quartz.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)

**Takeaway:** Misfire policies decide **what to do when a trigger is late**, `@DisallowConcurrentExecution` decides **whether executions of the same `JobKey` can overlap**, and `requestRecovery` decides **whether to retry a job interrupted by a scheduler crash**. Quartz orchestrates timing; durable business data, idempotency, and reconciliation protect integration outcomes against downtime, duplicates, and unknown failures.
