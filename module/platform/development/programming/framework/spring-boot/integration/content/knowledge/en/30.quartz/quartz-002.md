# Job, JobDetail, Trigger, and Execution Lifecycle in Quartz

## Goals and Context

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot connects HTTP clients, databases, caches, message brokers, and Spring Integration adapters to build real-world processing flows. Many tasks must run on a schedule: syncing products from partner APIs, sweeping unpublished outbox entries, reconciling transactions, rebuilding caches, or purging expired data.

**Quartz Scheduler** manages execution schedules through four core components: `Job`, `JobDetail`, `Trigger`, and `Scheduler`. This lesson belongs to the **Quartz** chapter and focuses on **Job, JobDetail, Trigger, and the execution lifecycle**—from declaration to firing time, success/failure, misfires, pause/resume, and recovery. In an integration system, the scheduler only decides **when to invoke**; data contracts, transactions, error handling, retries, idempotency, and observability must still be designed at the business and adapter layers.

After this lesson, you will be able to:

- Distinguish between the `Job` class holding execution code, `JobDetail` identifying the work, `Trigger` defining the schedule, and `Scheduler` orchestrating execution.
- Create `JobDetail`, `SimpleTrigger`, and `CronTrigger` beans for Spring Boot auto-configuration.
- Read `JobExecutionContext` and distinguish scheduled run time from actual execution time.
- Explain misfires, concurrency, `JobDataMap`, exceptions, recovery, and trigger states.
- Choose between `RAMJobStore` and JDBC JobStore, and design multi-replica schedulers safely.
- Test registration, execution, cron schedules, and business data while monitoring actual outcomes.

> **Key reminder:** Quartz does not automatically guarantee exactly-once execution, distributed transactions, or safe retries. A re-executed Job can cause duplicate side effects if adapters lack idempotency.

## 1. When Is Quartz a Better Fit Than @Scheduled?

Spring Framework provides `@Scheduled` for simple periodic tasks; Quartz is suitable when execution schedules become part of operational state that must be managed independently.

| Requirement | `@Scheduled` | Quartz |
| --- | --- | --- |
| Simple cron/fixed-delay runs in a single app | Suitable | Also possible |
| Identifying each job/trigger by name and group | Must be built manually | `JobKey`, `TriggerKey` |
| Creating/editing/pausing/resuming schedules at runtime | Requires custom additions | `Scheduler` API |
| Persisting schedules across restarts | No built-in JobStore | JDBC JobStore |
| Configuring missed-schedule (misfire) behavior | Fewer options | Per-trigger policies |
| Coordinating triggers across multiple instances | Must coordinate externally | Quartz clustering with JDBC store |
| Preventing a business transaction from applying twice | Must design manually | **Still must design manually** |

Example: a Catalog sync task runs every 15 minutes. If 3 replicas are deployed with separate RAMJobStores, all three may execute the same logic. JDBC JobStore with clustering can coordinate triggers, but unique constraints, checkpoints, and idempotency are still needed for crash recovery.

## 2. Objects Involved in a Single Execution

~~~mermaid
flowchart LR
    A["Spring Boot"] --> B["Scheduler"]
    B --> C["Trigger: when to run"]
    C --> D["JobDetail: identity + config"]
    D --> E["Job instance: execute(context)"]
    E --> F["Application service"]
    F --> G["HTTP / SQL / cache / broker"]
    H["JobStore"] -.-> B
    I["Quartz thread pool"] -.-> B
~~~

| Component | Function | Do Not Confuse With |
| --- | --- | --- |
| `Job` | Interface with `execute(JobExecutionContext)` | Not a singleton holding business state |
| `JobDetail` | Job definition including Job class, identity, and JobDataMap | Not an execution schedule |
| `Trigger` | Rule for when a JobDetail is fired | Not processing code |
| `Scheduler` | Registers, selects, and coordinates jobs/triggers | Does not automatically make HTTP/DB transactional |
| `JobStore` | Stores metadata and job/trigger state | Not a business checkpoint |
| `JobExecutionContext` | Metadata for a single firing | Not a business data contract |

### 2.1. Job: Execution Code

`org.quartz.Job` only requires the `execute(...)` method:

~~~java
import org.quartz.Job;
import org.quartz.JobExecutionContext;
import org.quartz.JobExecutionException;

public class SampleJob implements Job {

    @Override
    public void execute(JobExecutionContext context)
            throws JobExecutionException {
        var key = context.getJobDetail().getKey();
        System.out.println("Quartz is running " + key);
    }
}
~~~

`System.out.println` is for illustration only. In production systems, use structured logging and never log secrets or sensitive payloads. Quartz creates a **new Job instance for each firing** via `JobFactory`. Therefore, do not store connections, cursors, checkpoints, or tokens in mutable fields of a Job and expect them to persist across runs.

### 2.2. JobDetail: Definition and Identity

~~~java
import org.quartz.JobBuilder;
import org.quartz.JobDetail;

JobDetail detail = JobBuilder.newJob(SampleJob.class)
        .withIdentity("catalogSync", "integration")
        .withDescription("Scheduled Catalog synchronization")
        .usingJobData("sourceSystem", "catalog")
        .storeDurably()
        .build();
~~~

`JobKey` is a name/group pair, such as `catalogSync`/`integration`, used to uniquely identify the job in the scheduler. Two JobDetails can share the same Java class yet have **different JobKeys**, and Quartz treats them as two distinct jobs.

`storeDurably()` allows the job definition to remain even when no triggers are attached; it does not guarantee durable business progress. `usingJobData(...)` passes small configuration values, not a state-storage mechanism replacing a database.

### 2.3. Trigger: Execution Condition

A single JobDetail can have multiple triggers attached, such as a periodic CronTrigger and a SimpleTrigger for an extra run.

~~~java
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;

Trigger once = TriggerBuilder.newTrigger()
        .withIdentity("catalogOnce", "integration")
        .forJob(detail)
        .startNow()
        .build();
~~~

`startNow()` sets the start time to when the trigger object is created. Creating a Trigger object does not immediately execute `execute()`; the scheduler must register the trigger, be started, and have an available thread.

| Trigger | Schedule Pattern | Examples |
| --- | --- | --- |
| `SimpleTrigger` | Single timestamp or interval + repeat count | Run once, every 5 minutes |
| `CronTrigger` | Quartz cron + time zone | 02:00 daily, every 15 minutes |
| `CalendarIntervalTrigger` | Calendar units such as days, weeks, months | Run every month |
| `DailyTimeIntervalTrigger` | Time window within a day and matching days | Every 10 minutes during business hours |

### 2.4. Scheduler: Coordination and Administration

`Scheduler` stores and looks up schedules, decides when to fire a JobDetail, allocates threads, invokes JobFactory, and updates the next fire time.

Common APIs:

- `scheduleJob(detail, trigger)`: creates a new definition and schedule.
- `getJobDetail(jobKey)` / `getTrigger(triggerKey)`: looks up metadata.
- `triggerJob(jobKey)`: requests an immediate extra firing.
- `pauseJob(jobKey)` / `resumeJob(jobKey)`: pauses/resumes associated triggers.
- `rescheduleJob(triggerKey, newTrigger)`: updates a schedule.
- `deleteJob(jobKey)`: removes the job and its associated triggers.
- `start()`, `standby()`, `shutdown(waitForJobsToComplete)`: scheduler lifecycle controls.

Administrative operations can mutate schedule data in JDBC JobStore, so authentication, authorization, and auditing are required; never let a public API choose arbitrary Job classes.

## 3. Spring Boot Quartz Auto-Configuration

With Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-quartz'
}
~~~

When dependencies and auto-configuration conditions match, Boot creates a `SchedulerFactoryBean` and a `Scheduler` bean; `JobDetail`, `Trigger`, and `Calendar` beans are automatically wired into the scheduler.

~~~yaml
spring:
  quartz:
    auto-startup: true
    startup-delay: 5s
    wait-for-jobs-to-complete-on-shutdown: true
    overwrite-existing-jobs: false
    properties:
      org.quartz.threadPool.threadCount: 5
~~~

| Property | Meaning |
| --- | --- |
| `auto-startup` | Whether to start the scheduler automatically when the context is ready |
| `startup-delay` | Delays scheduler start, not individual jobs separately |
| `wait-for-jobs-to-complete-on-shutdown` | Whether to wait for running jobs to finish when shutting down the app |
| `overwrite-existing-jobs` | Whether to overwrite existing JobDetail/Trigger definitions in JobStore at startup |
| `org.quartz.threadPool.threadCount` | Number of threads Quartz allocates for concurrent jobs |

The common default is **RAMJobStore**; schedules reside in process memory. The JDBC JobStore section explains persisting state across restarts and clustering.

Quartz is a separate library managed by Spring Boot dependency management. Keep library versions compatible with Boot, especially when upgrading across Boot/Spring generations.

## 4. Example: Syncing the Catalog API Every 15 Minutes

Suppose the system must read updated products from a partner API and write projections and checkpoints to a database. The scheduler dictates when to run; sync logic belongs to a dedicated use case.

### 4.1. Business Contract

~~~java
// CatalogSyncUseCase.java
public interface CatalogSyncUseCase {
    void synchronizeNextBatch();
}
~~~

A Spring service implementing this interface handles HTTP client calls, data validation, transactions, and checkpoints. This lesson assumes an implementation is already registered in the Spring container.

### 4.2. Job Calling the Use Case

~~~java
// CatalogSyncJob.java
import org.quartz.DisallowConcurrentExecution;
import org.quartz.Job;
import org.quartz.JobExecutionContext;
import org.quartz.JobExecutionException;
import org.springframework.beans.factory.annotation.Autowired;

@DisallowConcurrentExecution
public class CatalogSyncJob implements Job {

    @Autowired
    private CatalogSyncUseCase useCase;

    @Override
    public void execute(JobExecutionContext context)
            throws JobExecutionException {
        try {
            useCase.synchronizeNextBatch();
        } catch (RuntimeException exception) {
            throw new JobExecutionException(
                    "Failed to complete Catalog sync", exception);
        }
    }
}
~~~

In standard Boot configuration, `JobFactory` integrates with Spring to autowire jobs; if you replace `JobFactory` or create the scheduler manually, verify that dependency injection still works. Do not treat a Job as a standard singleton bean and do not store mutable state across firings.

`@DisallowConcurrentExecution` coordinates runs of the **same JobKey** so they do not overlap within a properly configured scheduler; two JobDetails with different JobKeys sharing the same Java class can still run concurrently.

### 4.3. Defining JobDetail and CronTrigger

~~~java
// CatalogQuartzConfiguration.java
import java.util.TimeZone;
import org.quartz.CronScheduleBuilder;
import org.quartz.JobBuilder;
import org.quartz.JobDetail;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogQuartzConfiguration {

    @Bean("catalogSyncJobDetail")
    JobDetail catalogSyncJobDetail() {
        return JobBuilder.newJob(CatalogSyncJob.class)
                .withIdentity("catalogSync", "integration")
                .withDescription("Synchronize Catalog API")
                .storeDurably()
                .requestRecovery(true)
                .build();
    }

    @Bean("catalogSyncTrigger")
    Trigger catalogSyncTrigger(
            @Qualifier("catalogSyncJobDetail") JobDetail detail,
            @Value(
                    "${integrations.catalog.sync-cron:0 0/15 * * * ?}")
                    String cron) {

        return TriggerBuilder.newTrigger()
                .withIdentity("catalogSyncCron", "integration")
                .forJob(detail)
                .withSchedule(
                        CronScheduleBuilder.cronSchedule(cron)
                                .inTimeZone(
                                        TimeZone.getTimeZone(
                                                "Asia/Ho_Chi_Minh"))
                                .withMisfireHandlingInstructionDoNothing())
                .build();
    }
}
~~~

~~~yaml
# application.yml
integrations:
  catalog:
    sync-cron: "0 0/15 * * * ?"
~~~

`integrations.catalog.sync-cron` is a custom application property injected via `@Value`. It is not a built-in Quartz property. Each `JobDetail`/`Trigger` bean is registered by Boot when configuration conditions match; **do not additionally call `scheduler.scheduleJob(...)` for the same job** unless intentional.

The Quartz cron expression `0 0/15 * * * ?` has six fields (second, minute, hour, day-of-month, month, day-of-week), meaning it runs at minutes 0, 15, 30, 45 of every hour at second 0. `?` marks no specific constraint on the day-of-week field. This is Quartz syntax, not 5-field Linux cron.

### 4.4. Startup Sequence

~~~mermaid
sequenceDiagram
    participant B as Spring Boot
    participant S as Quartz Scheduler
    participant T as CronTrigger
    participant J as CatalogSyncJob
    participant U as CatalogSyncUseCase
    B->>S: Register JobDetail and Trigger
    B->>S: Start via auto-startup
    S->>T: Compute nextFireTime
    T-->>S: Fire time reached
    S->>J: Create instance, execute(context)
    J->>U: synchronizeNextBatch()
    U-->>J: Success or error
    J-->>S: Execution outcome
    S->>T: Compute next fire time
~~~

Creating a `JobDetail` bean does not mean the job has executed. The scheduler must start, the trigger must be active, threads must be available, and no other policy may block it.

## 5. Lifecycle of Each Job Execution

The process can be viewed in stages:

1. **Registration**: `JobDetail`/`Trigger` are placed into the JobStore.
2. **Waiting**: Scheduler computes `nextFireTime` and waits until due.
3. **Acquisition**: Quartz acquires an available trigger, considering `JobKey` and the thread pool.
4. **Job instantiation**: `JobFactory` creates an instance and injects dependencies.
5. **Execution**: Calls `execute(JobExecutionContext)` on a Quartz worker thread.
6. **Completion/error**: The handler returns or throws `JobExecutionException`; listeners are notified.
7. **Rescheduling**: The trigger computes the next schedule, completes, or transitions state.
8. **Pause/resume/delete/recovery**: State may change via management APIs or system failures.

Public trigger states include `NORMAL`, `PAUSED`, `COMPLETE`, `ERROR`, `BLOCKED`, and `NONE`. They describe scheduler/trigger state; **they do not guarantee that business logic committed or broker messages were delivered**.

### 5.1. Metadata in JobExecutionContext

~~~java
@Override
public void execute(JobExecutionContext context)
        throws JobExecutionException {

    var jobKey = context.getJobDetail().getKey();
    var triggerKey = context.getTrigger().getKey();

    var scheduledTime = context.getScheduledFireTime();
    var fireTime = context.getFireTime();
    var nextTime = context.getNextFireTime();

    var fireId = context.getFireInstanceId();
    boolean recovering = context.isRecovering();

    // Log necessary metadata, restricting sensitive details.
}
~~~

| Value | Meaning | Usage |
| --- | --- | --- |
| `scheduledFireTime` | When the trigger was scheduled to fire | Measure scheduler latency |
| `fireTime` | When the scheduler actually fired | Compare against scheduled time |
| `nextFireTime` | Next scheduled run time, if any | Operations/scheduling |
| `fireInstanceId` | Identifier for a single firing | Tracing/logging, **not an idempotency key** |
| `isRecovering()` | Whether this run belongs to recovery | Investigation/reconciliation |
| `getRefireCount()` | Number of immediate refires | Not the total HTTP/broker retry count |

Scheduler latency can be roughly measured via `fireTime - scheduledFireTime`. This latency differs from business execution duration from job start until checkpoint commit.

### 5.2. New Job Instance Does Not Mean Fresh Business State

Quartz creates a new Job instance each run, yet effects in the database/broker may remain from previous runs. A job that reads a cursor stored in an instance field expecting the next run to continue from there will be unreliable.

Use a transactional checkpoint table or metadata store, such as `catalog_sync_checkpoint(source, last_version, updated_at)`, to resume accurately after restarts or recovery.

## 6. JobDataMap and Schedule-Attached Data

`JobDataMap` carries small configuration parameters for `JobDetail` and `Trigger`:

~~~java
JobDetail detail = JobBuilder.newJob(SampleJob.class)
        .withIdentity("export", "reports")
        .usingJobData("reportType", "sales")
        .usingJobData("batchSize", 100)
        .build();
~~~

Reading data in the Job:

~~~java
String reportType =
        context.getMergedJobDataMap().getString("reportType");

int batchSize =
        context.getMergedJobDataMap().getInt("batchSize");
~~~

`getMergedJobDataMap()` combines the JobDetail and Trigger maps. If the same key exists in both, the trigger's map overrides the JobDetail value for that firing.

**Keep JobDataMap small and safe**:

- Should hold strings, numbers, configuration names, and stable identifiers.
- Do not store passwords, tokens, Java `DataSource`, `EntityManager`, HTTP clients, or large objects.
- With JDBC JobStore, consider serialization/deserialization and class compatibility across nodes/deploys.
- Do not use JobDataMap as a transaction mechanism or business checkpoint.

### 6.1. @PersistJobDataAfterExecution

~~~java
import org.quartz.DisallowConcurrentExecution;
import org.quartz.PersistJobDataAfterExecution;

@PersistJobDataAfterExecution
@DisallowConcurrentExecution
public class CountingJob implements org.quartz.Job {
    // execute(...) may update JobDetail.JobDataMap.
}
~~~

`@PersistJobDataAfterExecution` tells Quartz to persist the updated `JobDataMap` after execution according to JobStore mechanics. `@DisallowConcurrentExecution` helps prevent races between executions of the same `JobKey`.

However, persisting Quartz's `JobDataMap` **is not atomic with external SQL business operations or HTTP calls**. If sync progress requires exact recovery, persist it in the business database with appropriate transactions/unique constraints.

## 7. SimpleTrigger, CronTrigger, and Reading Schedules

### 7.1. SimpleTrigger

Example starting after 30 seconds and repeating four more times (up to five scheduled firings total):

~~~java
import java.util.Date;
import org.quartz.SimpleScheduleBuilder;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;

Trigger trigger = TriggerBuilder.newTrigger()
        .withIdentity("reconcileOnceSeries", "integration")
        .forJob(detail)
        .startAt(new Date(
                System.currentTimeMillis() + 30_000L))
        .withSchedule(
                SimpleScheduleBuilder.simpleSchedule()
                        .withIntervalInMinutes(5)
                        .withRepeatCount(4))
        .build();
~~~

`repeatCount = 4` means **four repeats after the first firing**, not four total runs. This is a **fixed schedule**, not a retry triggered only when the previous run fails. `repeatForever()` creates an unbounded schedule until altered.

### 7.2. CronTrigger

| Quartz cron | Meaning |
| --- | --- |
| `0 0/15 * * * ?` | Every 15 minutes |
| `0 0 2 * * ?` | 02:00 every day |
| `0 0 9 ? * MON-FRI` | 09:00 Monday through Friday |
| `0 30 23 L * ?` | 23:30 on the last day of every month |

Quartz cron includes a **seconds** field, unlike 5-field Linux cron. Configure time zones explicitly, especially when applications span multiple regions. In daylight saving time zones, times like 02:30 may be skipped or occur twice during clock transitions; test schedules against real time zones.

### 7.3. Slow Schedules and Long-Running Tasks

If a job takes 20 minutes while triggered every 15 minutes:

- Without concurrency control, executions may overlap.
- With `@DisallowConcurrentExecution`, Quartz avoids concurrent runs for the same `JobKey`, but schedules may drift late.
- If the thread pool runs out of threads, other triggers also wait and may misfire.
- Long-running jobs must have timeouts, checkpoints, and controlled cancellation.

Do not use a large thread pool size to mask a hanging HTTP/SQL adapter.

## 8. Misfire: When Quartz Misses the Scheduled Time

**Misfire** occurs when a trigger becomes due but cannot fire within the threshold configured in Quartz. Causes include scheduler downtime, standby mode, thread pool saturation, slow JobStore, or cluster failover.

Misfire policies for `CronTrigger`:

| API | General Meaning | When Appropriate |
| --- | --- | --- |
| `withMisfireHandlingInstructionDoNothing()` | Discard missed runs and wait for the next schedule | Periodic syncs that only need the latest state |
| `withMisfireHandlingInstructionFireAndProceed()` | Fire one catch-up run as soon as possible, then resume schedule | Need to run once immediately upon service recovery |
| `withMisfireHandlingInstructionIgnoreMisfires()` | Bypass normal misfire handling | Only when backlog/burst risk is controlled |

`SimpleTrigger` has different options, such as `FireNow`, `NextWithRemainingCount`, or `NowWithExistingCount`, which alter the next fire time and remaining repeat counts. Do not mechanically copy policies between `CronTrigger` and `SimpleTrigger`.

**Example:** a daily report job runs at 02:00, but the scheduler stops from 01:50 to 04:00. "DoNothing" may skip that reporting period. "FireAndProceed" may trigger once on recovery, but code using `LocalDate.now()` could generate the report for the wrong date. If every day must be processed, record required periods in a work/checkpoint table and have the job sweep incomplete periods.

### Misfire vs. Job Failure

Misfire refers to **the schedule not firing on time**. An exception in `execute(...)` refers to **the execution body of a run**. A job can fire on time and fail; it can also fire late and succeed. Dashboards and recovery policies should separate these two event types.

## 9. Concurrency and @DisallowConcurrentExecution

~~~java
import org.quartz.DisallowConcurrentExecution;

@DisallowConcurrentExecution
public class CatalogSyncJob implements org.quartz.Job {
    // execute(...)
}
~~~

This annotation prevents runs of the **same JobDetail/JobKey** from executing concurrently under Quartz rules. However:

- Two JobDetails with different JobKeys sharing the same Java class can still run together.
- Two independent Quartz schedulers using separate JobStores share no lock.
- Other HTTP endpoints or broker consumers can still modify the same data.
- Crash recovery/replay can re-execute business steps that already occurred.
- If a Job spawns asynchronous child tasks and returns immediately, Quartz considers the Job finished while child work continues.

For critical business logic, use **unique constraints, optimistic locking, claims/leases, or transactions** keyed by business key; `@DisallowConcurrentExecution` only governs concurrency at the scheduler layer.

## 10. JobExecutionException and Retry Policies

If a Job throws `JobExecutionException`, Quartz recognizes the execution failed and notifies listeners. **Throwing an exception does not automatically turn into a retry with exponential backoff.**

~~~java
@Override
public void execute(JobExecutionContext context)
        throws JobExecutionException {
    try {
        useCase.synchronizeNextBatch();
    } catch (RuntimeException exception) {
        throw new JobExecutionException(
                "Catalog sync failed", exception);
    }
}
~~~

`JobExecutionException` supports flags to refire immediately or unschedule in certain cases. Do not enable `refireImmediately` indiscriminately: during prolonged network outages, it can cause tight loops, consume threads, and repeat side effects.

| Error | Retryable? | Notes |
| --- | --- | --- |
| HTTP 503, transient disconnect | Usually yes, bounded | Backoff/jitter, circuit breaker |
| Wrong password, permission denied | Do not retry indefinitely | Alert and fix configuration |
| Invalid schema/JSON | Fix contract | DLQ or quarantine depending on flow |
| SQL deadlock/serialization conflict | Controlled transaction retry | Idempotency and finite attempts |
| Timeout after POST write | Outcome may be unknown | Query status using idempotency key |
| DB committed but broker publish failed | Cannot roll back DB via Quartz | Transactional outbox |

**Retry budget:** if a Job runs every 15 minutes, the HTTP client retries 3 times, and the broker also redelivers, total requests can multiply excessively. Define an end-to-end retry budget, maximum duration, recovery points, and alerts.

## 11. RAMJobStore, JDBC JobStore, and Persistence

### 11.1. RAMJobStore

- Easy for development, no Quartz tables required.
- JobDetail/Trigger state exists only in process memory.
- Dynamically created schedules do not survive restarts.
- Each replica has its own scheduler; multiple nodes may trigger the same logic.

Suitable for demos, tests, or tasks needing neither schedule persistence nor clustering.

### 11.2. JDBC JobStore

Boot configuration connecting Quartz to SQL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-quartz'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

~~~yaml
spring:
  datasource:
    url: ${QUARTZ_DB_URL}
    username: ${QUARTZ_DB_USERNAME}
    password: ${QUARTZ_DB_PASSWORD}

  quartz:
    job-store-type: jdbc
    jdbc:
      initialize-schema: never
    overwrite-existing-jobs: false
    properties:
      org.quartz.scheduler.instanceName: integrationScheduler
      org.quartz.threadPool.threadCount: 8
~~~

In production examples, the Quartz schema must be created **via controlled migrations/provisioning before the app starts**. `initialize-schema: never` prevents Boot from running initialization scripts automatically. Standard Quartz scripts executed under `initialize-schema: always` may **drop existing tables**, making `always` on a database with schedules to preserve very risky.

JDBC JobStore persists scheduler metadata in tables like `QRTZ_JOB_DETAILS`, `QRTZ_TRIGGERS`, `QRTZ_CRON_TRIGGERS`. It **does not persist business processing results** unless the use case writes checkpoints.

### 11.3. Overwrite-existing-jobs and Deploying New Versions

Schedules stored in JDBC do not automatically reflect every Java bean change upon deployment. The `spring.quartz.overwrite-existing-jobs` property affects how Boot handles existing definitions.

- If **code/deployment** is the source of truth for schedules, you may enable overwriting and manage schedule versions explicitly.
- If operators modify schedules via admin APIs, overwriting on every startup can erase operator-intended changes.
- Changing `JobKey`/`TriggerKey` can create **a new schedule while the old one remains**; controlled migration or cleanup is needed.

Do not let both code and a database UI manage schedules simultaneously without clear ownership rules.

## 12. Clustering and Recovery Across Multiple Replicas

Two Spring Boot replicas configured with separate RAMJobStores run two independent Quartz schedulers. If a true cluster scheduler is required, nodes must share a **JDBC JobStore** and enable clustering with distinct instance identities.

~~~yaml
spring:
  quartz:
    job-store-type: jdbc
    jdbc:
      initialize-schema: never
    properties:
      org.quartz.scheduler.instanceName: integrationScheduler
      org.quartz.scheduler.instanceId: AUTO
      org.quartz.jobStore.isClustered: true
      org.quartz.jobStore.clusterCheckinInterval: 10000
      org.quartz.threadPool.threadCount: 8
~~~

Key requirements:

1. Nodes in the same cluster share matching Quartz tables and scheduler name.
2. Instance IDs must be distinct; `AUTO` lets Quartz assign them.
3. System clocks are synchronized closely enough to avoid significant drift.
4. Database and connection pools have sufficient capacity, with vendor-appropriate schema/locking.
5. All nodes have compatible Job classes/versions for stored metadata.
6. Non-clustered nodes do not access the same Quartz tables with incompatible settings.

**Clustering distributes triggers; it does not guarantee exactly-once side effects.** When a node crashes mid HTTP/DB call, Quartz may re-execute without knowing whether the external system already applied the change.

### 12.1. requestRecovery(true)

~~~java
JobDetail detail = JobBuilder.newJob(CatalogSyncJob.class)
        .withIdentity("catalogSync", "integration")
        .requestRecovery(true)
        .storeDurably()
        .build();
~~~

With an appropriate JobStore/recovery setup, `requestRecovery(true)` tells Quartz that a job executing on a failed scheduler instance may need to be re-executed. It does not resume at the exact Java instruction before the crash; it **starts a new execution**. `JobExecutionContext.isRecovering()` identifies these runs.

Therefore you must:

- Read committed checkpoints.
- Avoid repeating business mutations based on already-processed `eventId`/versions.
- Include an outbox in the same transaction when messages must follow SQL writes.
- Account for the "DB committed but Quartz never recorded job completion" case.

## 13. Transactions and Idempotency for Scheduled Integration Jobs

Consider an HTTP → DB → broker sync flow:

~~~mermaid
flowchart LR
    A["CronTrigger"] --> B["CatalogSyncJob"]
    B --> C["CatalogSyncUseCase"]
    C --> D["Catalog HTTP API"]
    C --> E["SQL transaction"]
    E --> F["Update projection"]
    E --> G["Update checkpoint"]
    E --> H["Insert outbox"]
    H --> I["Outbox relay"]
    I --> J["Broker"]
~~~

A safe execution pattern:

1. Read the durably stored checkpoint, never from a Job instance field.
2. Fetch a batch of changes using an HTTP client with timeouts.
3. Validate schema/version, identify business keys, and enforce deduplication rules.
4. Write data, checkpoint, and outbox **in the same SQL transaction** when targeting the same resource.
5. Once committed, the next run starts from the updated checkpoint.
6. A publisher dispatches the outbox; downstream consumers enforce idempotency because events may be redelivered.

If the checkpoint is written **before** data changes in separate transactions, a crash can skip unprocessed records. If data changes occur first without the checkpoint committed, the batch can repeat; idempotent operations are needed.

**Quartz transactions differ from business transactions.** JDBC JobStore uses its own transactions for schedule/trigger metadata. Spring `@Transactional` on a service does not combine HTTP requests, broker publishes, and Quartz metadata into one ACID transaction.

### 13.1. Unknown Outcomes

An HTTP POST timeout after sending does not prove the partner did not receive it. Retries must carry a partner-supported idempotency key and/or reconciliation lookup. Likewise, losing connection during DB commit requires querying by business key/version rather than blindly retrying.

### 13.2. Do Not Hold Transactions Open Across Slow HTTP Calls

Never open a long DB transaction and wait minutes for an HTTP API. Doing so holds connections/locks and can exhaust the pool. Separate fetching, validating, and writing each batch; design atomic check-and-update checkpoints to protect against concurrent runs.

## 14. Controlling the Scheduler at Runtime

A Spring service can inject `Scheduler` to trigger extra runs, pause/resume, and inspect metadata:

~~~java
import org.quartz.JobKey;
import org.quartz.Scheduler;
import org.quartz.SchedulerException;
import org.springframework.stereotype.Service;

@Service
public class QuartzAdminService {

    private final Scheduler scheduler;

    public QuartzAdminService(Scheduler scheduler) {
        this.scheduler = scheduler;
    }

    public void triggerCatalog() throws SchedulerException {
        scheduler.triggerJob(
                JobKey.jobKey("catalogSync", "integration"));
    }

    public void pauseCatalog() throws SchedulerException {
        scheduler.pauseJob(
                JobKey.jobKey("catalogSync", "integration"));
    }

    public void resumeCatalog() throws SchedulerException {
        scheduler.resumeJob(
                JobKey.jobKey("catalogSync", "integration"));
    }
}
~~~

This is an internal admin service without an HTTP controller yet. When exposed via API, require admin authentication, auditing, and rate limiting on manual triggers.

**Pausing does not kill an active job.** `pauseJob(...)` prevents future firings under scheduler rules; an already started execution continues. To stop long-running jobs, design cancellation protocols, timeouts, and/or `InterruptableJob` where appropriate. Never assume Quartz can safely abort arbitrary JDBC transactions or HTTP calls.

For dynamic schedules, calling `checkExists(...)` then `scheduleJob(...)` is not atomic across multiple admin processes. Handle `ObjectAlreadyExistsException` or use locked update mechanisms; use `rescheduleJob(...)` to adjust existing triggers by stable identity.

## 15. Observing Scheduler State and Business Outcomes

Spring Boot Actuator includes a Quartz endpoint on supported versions, such as `/actuator/quartz`, to inspect job/trigger metadata when enabled and authorized. This endpoint **does not guarantee** that business logic committed, messages were published, or backlogs are clear.

Monitor two layers:

| Quartz/scheduler | Business flow |
| --- | --- |
| Trigger nextFireTime, state | Last successful checkpoint |
| Scheduled vs actual fire lag | Source data → projection latency |
| Job duration, exception count | Succeeded/failed record counts |
| Running job count, pool saturation | Outbox queue age, backlog |
| Misfire count, recovery events | Duplicate/retry/DLQ counts |
| Cluster check-in | Downstream HTTP/DB errors/timeouts |

Quartz provides `JobListener` and `TriggerListener` to observe lifecycle events and misfires. Example:

~~~java
import org.quartz.JobExecutionContext;
import org.quartz.JobExecutionException;
import org.quartz.listeners.JobListenerSupport;

public class SyncJobListener extends JobListenerSupport {

    @Override
    public String getName() {
        return "catalog-sync-listener";
    }

    @Override
    public void jobWasExecuted(
            JobExecutionContext context,
            JobExecutionException exception) {
        // Record outcome metrics/logs by JobKey and exception type.
        // Listener must be registered with Scheduler.
    }
}
~~~

This snippet only declares the listener; the application must register it via Scheduler or `SchedulerFactoryBeanCustomizer` as configured.

With Micrometer Observation, use names like `integration.catalog.sync` and low-cardinality tags (`job=catalogSync`, `outcome=success/failure`). Do not use `fireInstanceId`, `orderId`, or `eventId` as high-cardinality metric labels; record those in protected audits/logs/traces as needed.

A trace for a scheduled Job typically begins on a Quartz worker thread. Do not assume trace context from a finished HTTP request automatically propagates across a trigger to a later run.

## 16. Testing JobDetail, Trigger, and Execution

Separate tests by layer:

- **Unit test use case:** fake HTTP/DB/broker to verify idempotency, checkpoints, error classification, and retry limits.
- **Spring Boot integration test:** verify JobDetail, Trigger, Scheduler beans, time zones, and autowiring.
- **Quartz execution test:** use triggers/latches and fake services to measure run counts, non-concurrency, and failures.
- **Persistence/recovery test:** use a real database or Testcontainers to verify schedules across restarts and duplicate behavior.

### 16.1. Testing Job Registration Without Running the Schedule

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.quartz.CronTrigger;
import org.quartz.JobKey;
import org.quartz.Scheduler;
import org.quartz.TriggerKey;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(
        properties = "spring.quartz.auto-startup=false")
class QuartzRegistrationTest {

    @Autowired
    Scheduler scheduler;

    @Test
    void catalogCronIsRegistered() throws Exception {
        var jobKey =
                JobKey.jobKey("catalogSync", "integration");
        var triggerKey =
                TriggerKey.triggerKey(
                        "catalogSyncCron", "integration");

        assertNotNull(scheduler.getJobDetail(jobKey));
        var trigger = scheduler.getTrigger(triggerKey);

        assertInstanceOf(CronTrigger.class, trigger);
        assertEquals("0 0/15 * * * ?",
                ((CronTrigger) trigger).getCronExpression());
    }
}
~~~

This test only checks metadata; it does not prove `execute()` runs. When using a JDBC store, run against a dedicated test database with Quartz tables or Testcontainers.

### 16.2. Testing Cron With Fixed Timestamps

~~~java
import java.time.Instant;
import java.util.Date;
import java.util.TimeZone;
import org.quartz.CronExpression;

CronExpression cron =
        new CronExpression("0 0/15 * * * ?");
cron.setTimeZone(
        TimeZone.getTimeZone("Asia/Ho_Chi_Minh"));

Date next = cron.getNextValidTimeAfter(
        Date.from(
                Instant.parse("2026-01-01T00:01:00Z")));

// 00:01Z = 07:01 in Vietnam; next firing is 07:15.
assertEquals(
        Instant.parse("2026-01-01T00:15:00Z"),
        next.toInstant());
~~~

This snippet shows the assertion portion of a test (requires JUnit imports and test fixture). Use fixed timestamps to verify cron logic instead of `Thread.sleep` waiting 15 minutes. For time zones with DST, add tests for clock-change days.

### 16.3. Testing Real Execution and Recovery

- In the test context, replace `CatalogSyncUseCase` with a counting fake.
- Start the scheduler for the specific test and invoke `triggerJob(...)`.
- Wait using a latch/event with a timeout and assert exact call counts, avoiding arbitrary sleeps.
- Inject an exception from the use case and verify the listener records the failure without infinite automatic retries.
- For `@DisallowConcurrentExecution`, fire two triggers on the same `JobKey` and observe maximum concurrent executions.
- With JDBC JobStore, restart the test scheduler and verify schedule definitions persist.
- Crash/recovery tests must verify DB/business checkpoints, not only Quartz table states.

Never point test schedulers at production databases or live HTTP endpoints. In particular, never enable `spring.quartz.jdbc.initialize-schema=always` on a DB containing data to preserve.

## 17. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Missing `Scheduler` bean | Missing starter or excluded auto-configuration | Check classpath/Boot conditions |
| `JobDetail` bean exists but Job never runs | Scheduler not started, trigger paused, no threads | Check `auto-startup` and trigger state |
| Job fails to inject service | Custom JobFactory does not autowire | Check JobFactory/Spring configuration |
| Job runs multiple times on 3 replicas | Independent RAMJobStores on each node | JDBC clustering or business locking |
| Job runs concurrently despite annotation | Different JobKeys, different schedulers, or external callers | Unique constraints and idempotency |
| Schedules lost after restart | RAMJobStore or dynamic jobs not re-registered | JDBC JobStore when persistence is required |
| Runs at wrong local time | Wrong cron or time zone/DST | Check expression and `nextFireTime` |
| Burst runs after downtime | Inappropriate misfire policy | Choose skip, fire-once, or checkpoint-based catch-up |
| Exceptions occur without retries | Quartz does not retry with backoff by default | Design an explicit retry budget |
| Job fails and loses progress | Checkpoint only in instance field/JobDataMap | Store checkpoint in DB within same transaction |
| Schedule change in code has no effect | Old JDBC definition still persisted | Review `overwrite-existing-jobs` and migrations |
| Job paused but keeps running | Active execution is not killed | Design cancellation/timeouts |
| Quartz schema missing | SQL init script dropped tables | Use migrations and `initialize-schema: never` |
| Quartz reports job success but broker missed event | Side effect outside Quartz not committed | Outbox/ack/business observability |

## 18. Checklist for Implementing a Quartz Integration Job

- [ ] Job only delegates to a use case; HTTP/SQL/cache/broker logic lives in appropriate adapters/services.
- [ ] `JobKey` and `TriggerKey` are unique and stable across deployments.
- [ ] Appropriate Simple/Cron trigger chosen with explicit time zone.
- [ ] Clear misfire policy defined: skip, catch up once, or backfill all periods from checkpoints.
- [ ] Concurrency controlled per `JobKey` and across external trigger sources.
- [ ] RAMJobStore chosen for ephemeral tasks or JDBC JobStore for persistent/clustered schedules.
- [ ] Quartz schema safely migrated, separating scheduler metadata from business data.
- [ ] Local transactions, idempotency, checkpoints, and outbox used where needed.
- [ ] Bounded retries/timeouts; permanent errors trigger alerts and remediation.
- [ ] Scheduled time, fire time, job outcome, and business completion tracked separately.
- [ ] Registration, execution, restart/recovery, misfire, and duplicate handling tested.
- [ ] `JobDataMap`, admin APIs, Actuator, and logs/metrics protected against secret exposure.

**Takeaway:** `Job` defines the code to run; `JobDetail` identifies and configures the job; `Trigger` describes when to run; `Scheduler` coordinates firings and lifecycle. Quartz can persist schedules and coordinate nodes via JDBC JobStore, but integration reliability still depends on **data contracts, transactions, error handling, deduplication, testing, and observability**.

## References

- [Spring Boot — Quartz Scheduler](https://docs.spring.io/spring-boot/reference/io/quartz.html): auto-configuration, JobDetail/Trigger, JDBC store, startup, and overwrite policy.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Scheduled` and Quartz integration.
- [Quartz Scheduler — Tutorials](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/): Job, JobDetail, Trigger, Cron, misfire, JobStore, and listeners.
- [Quartz — JobDetail API](https://www.quartz-scheduler.org/api/2.3.0/org/quartz/JobDetail.html): identity, durability, recovery, and JobDataMap.
- [Quartz — CronTrigger API](https://www.quartz-scheduler.org/api/2.3.0/org/quartz/CronTrigger.html): cron scheduling and misfires.
- [Quartz — Scheduler API](https://www.quartz-scheduler.org/api/2.3.0/org/quartz/Scheduler.html): schedule, trigger, pause, resume, and lifecycle.
