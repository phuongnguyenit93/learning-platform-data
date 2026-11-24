# Jobs Running Duplicate Across Replicas or Failing to Restart

## 1. Recognizing the Problem in Spring Boot Integration

In a **Spring Boot Integration** application, integration flows often run on schedules or in batches to import data from HTTP APIs, synchronize databases, rebuild caches, forward events via RabbitMQ/Kafka, and reconcile results. A job can be triggered by `@Scheduled`, Quartz, Spring Batch `JobLauncher`, broker messages, or an admin API. When deploying multiple replicas or pods, two recurring failures appear:

1. **Duplicate job execution:** the same reconciliation period runs on two pods; records are written twice, partners are called repeatedly, or duplicate emails go out.
2. **Job fails to restart:** after a failed execution or process crash, restarting reports "already complete," "already running," "instance not found," or restarts **from the beginning** instead of resuming from its checkpoint.

Both symptoms often share a root cause: **misidentifying the unit of work and lacking durable cross-replica coordination**. For instance, if each pod generates a fresh `run.id` parameter, Spring Batch sees distinct `JobInstance`s and lets every pod process the same business day simultaneously.

~~~mermaid
flowchart LR
    S["Cron 01:00"] --> A["Replica A"]
    S --> B["Replica B"]
    S --> C["Replica C"]
    A --> J1["JobLauncher"]
    B --> J2["JobLauncher"]
    C --> J3["JobLauncher"]
    J1 --> R[("Shared JobRepository")]
    J2 --> R
    J3 --> R
    R --> D[("Business data")]
~~~

**Warning:** A shared `JobRepository` coordinates execution creation for **the same `JobInstance`**, yet it does not automatically protect against every duplicate scenario. If pods pass **different identifying parameters**, different job names, or miscalculate business keys, the repository treats them as unrelated instances.

This lesson targets **Spring Boot 3.x and Spring Batch 5.x**, while distinguishing `@Scheduled`, Quartz clustered schedulers, and message broker consumers. When upgrading across major versions, verify APIs, metadata schemas, and configuration changes accordingly.

## 2. First Determine What the "Job" Actually Is

The word "job" covers distinct mechanisms; the right fix depends on what triggers it and where state lives:

| Job Type | Who Triggers It? | Where Does State / Locking Live? | Common Duplication Risk |
| --- | --- | --- | --- |
| **Plain Spring `@Scheduled`** | Per-JVM internal scheduler. | No cross-replica state by default. | Every pod fires the cron simultaneously; rolling deploys overlap. |
| **Spring Batch job** | `JobLauncher`, scheduler, API, or operator. | `JobRepository` and Batch metadata tables. | Varying identifying `JobParameters` or unshared repositories. |
| **Quartz job** | Quartz trigger; RAM or JDBC JobStore. | Quartz JobStore, triggers, and job keys. | Per-pod `RAMJobStore`; clustering disabled; duplicate `JobKey`/triggers. |
| **Broker consumer** | RabbitMQ/Kafka message delivery. | Queues/offsets, ACKs, consumer groups, app state. | Redeliveries, retries, distinct consumer groups, non-idempotent side effects. |
| **Kubernetes `CronJob`** | Cluster control plane launches pods. | Kubernetes Job/CronJob objects. | `concurrencyPolicy` and pod retries; non-idempotent tasks. |

For example, putting `@Scheduled` on a method calling `JobLauncher` **does not turn `@Scheduled` into a distributed scheduler**. Every pod still invokes the launcher on schedule. Nor can adding a Spring Batch `JobRepository` fix a Quartz `RAMJobStore`: they are **two independent metadata systems**.

Verify from live logs and configs: how many pods exist, what triggers execution, job/trigger names, run times, identifying parameters, metadata database, outbound service calls, and the batch's business key.

## 3. Spring Batch Identity and Restart Mechanics

Spring Batch distinguishes:

| Component | Definition | Diagnostic Relevance |
| --- | --- | --- |
| `Job` | Defines `Step`s and control flow. | Job name forms part of identity. |
| `JobParameters` | Parameters for a launch, each flagged `identifying`. | **Only identifying parameters** define the `JobInstance`. |
| `JobInstance` | Logical run defined by job name + identifying parameters. | Unit determining whether a run is active, complete, or restartable. |
| `JobExecution` | A single attempt of a `JobInstance`. | A failed `JobInstance` gets a new `JobExecution` on restart. |
| `StepExecution` | Attempt of one step tracking commit, rollback, read/write/skip counts. | Reveals which steps finished and where checkpoints stand. |
| `ExecutionContext` | Persisted state metadata per step/job. | Enables stateful readers/writers to resume on restart. |
| `JobRepository` | Persists metadata and coordinates execution state. | **Must be durable and shared** if multiple pods coordinate Spring Batch. |

Core formula:

~~~text
JobInstance = jobName + identifying JobParameters

dailySettlementJob / businessDate=2026-11-20 / source=bank-A
    JobExecution 1001 -> FAILED
    JobExecution 1002 -> COMPLETED (restart same instance)

dailySettlementJob / businessDate=2026-11-21 / source=bank-A
    JobExecution 1003 -> STARTED (different instance)
~~~

A fresh **`run.id`, UUID, or timestamp** is useful to launch a **genuinely new batch**, yet if marked identifying and regenerated on every retry, it creates a **new `JobInstance`** and loses prior checkpoints. Never fix "already complete" by auto-incrementing `run.id` when the real intent is resuming the same business period.

### 3.1. Error Messages and What They Mean

| Error or Status | Most Likely Cause | Where to Check |
| --- | --- | --- |
| `JobExecutionAlreadyRunningException` | An execution for this instance is still marked active. | Inspect `JobRepository` and owning pod; distinguish truly running vs. `STARTED` orphaned by crash. |
| `JobInstanceAlreadyCompleteException` | Instance already completed; caller tried launching same identity again. | Inspect `JobInstance` and whether intent is "restart" or legitimate "reprocess." |
| `JobRestartException` | Job is non-restartable, metadata/state invalid, or restart rules block it. | Inspect restart config and full stack trace. |
| `JobParametersInvalidException` | Parameters failed job validator/contract. | Check required params, types, `identifying` flags, and business date bounds. |
| `JobInstance` not found on restart | Metadata in another repository, purged, renamed job/identity, or wrong execution ID. | Check datasource, schema, table prefix, and metadata migrations. |
| Restart "succeeds" yet starts from row 1 | New `JobInstance`; reader `saveState=false`; changed input; uncommitted checkpoint. | Compare `JOB_KEY`, identifying params, and step `ExecutionContext`. |
| Step skipped on restart | Step already `COMPLETED` and skipped by default. | Check flow and enable `allowStartIfComplete` only when re-running is genuinely safe. |

Never assume a job is "definitely still running" solely because metadata says `STARTED`: a hard crash can leave `STARTED` instead of `FAILED` or `STOPPED`. Conversely, **never blindly mark a live long-running execution failed** without proving its worker died.

## 4. Causes of Duplicate Job Runs Across Replicas

### 4.1. `@Scheduled` Runs Independently in Every JVM

~~~java
@Scheduled(cron = "0 0 1 * * *", zone = "Asia/Ho_Chi_Minh")
public void importDaily() {
    runImportForYesterday();
}
~~~

With three pods, **all three** normally invoke this method at 01:00. `@EnableScheduling` activates scheduling per application context; it includes no leader election or distributed lock. If each pod calls an external API, the operation executes three times.

Options depending on requirements: a single dedicated scheduler instance; distributed locks/leases; Quartz JDBC clustering; or letting multiple pods call `JobLauncher` backed by a **shared `JobRepository` and deterministic identifying parameters**. Regardless of approach, enforce **business keys and idempotency** at outputs.

### 4.2. Each Pod Uses a Different `JobRepository`

This often happens with differing datasource/schema defaults, in-memory metadata, or unqualified multi-datasource setups. Pod A writes metadata to database A while Pod B writes to database B; both think no job has started.

Verify **datasource URL, schema, table prefix, user privileges, active profiles, and `JobRepository` type** on every pod. In clusters, metadata belongs in shared durable storage with version-appropriate transaction isolation and unique constraints. Never drop constraints from Batch tables to "reduce contention."

### 4.3. Unstable Identifying Parameters

~~~text
Pod A: dailySettlementJob, businessDate=2026-11-20, run.id=1001 (identifying)
Pod B: dailySettlementJob, businessDate=2026-11-20, run.id=1002 (identifying)
=> Two distinct JobInstances despite targeting the same business date.
~~~

Likewise, temporary local file paths, per-pod timestamps, or random UUIDs shift identity. Use **immutable logical keys** such as `businessDate`, `sourceId`, or batch/source version as identifying parameters, normalizing timezones, date formats, casing, and path interpretation.

### 4.4. Multiple Triggers or Overlapping Schedules

Even with one scheduler, a job might be launched by `@Scheduled`, an admin endpoint, a Quartz trigger, and a broker event simultaneously. A slow run exceeding its cadence can overlap the next trigger if each trigger uses a fresh identity.

In Quartz, registering the same logic under multiple `JobKey`s or triggers bypasses `@DisallowConcurrentExecution`: that annotation prevents concurrent execution per **`JobDetail`/`JobKey`**, not across distinct `JobDetail` definitions.

### 4.5. Broker Redeliveries or Scheduler Retries

RabbitMQ and Kafka redeliver after crashes before ACK, timeouts, rebalances, or retries. Redelivery is normal broker behavior, not a bug. If repeated deliveries create new `JobInstance`s or execute non-idempotent writes, side effects duplicate. Stabilize `eventId`/`operationId` relative to `businessKey`, and enforce inbox/unique constraints.

## 5. Three Defense Layers That Work Together

Stop hunting for one magic annotation promising "system-wide exactly-once." Reliable architectures layer three defenses:

1. **Deliberate scheduling:** distributed triggers or leader/lock coordination rather than independent per-pod crons.
2. **Instance identity & durable state:** shared `JobRepository`, consistent identifying parameters, and tracking running/completed jobs.
3. **Idempotent outputs:** unique business keys, conditional upserts, HTTP operation IDs, and inbox/outbox for broker messaging.

| Defense Layer | What It Prevents | What It Does Not Prevent |
| --- | --- | --- |
| Distributed scheduler / leader | Concurrent scheduled triggers across pods | Lease expiring while a slow worker is alive; redeliveries or ad-hoc triggers |
| Shared `JobRepository` + stable identity | Duplicate executions of the same `JobInstance` in Spring Batch | Two distinct identities processing the same data; side effects committed before crash |
| Business idempotency | Duplicate downstream effects if an operation runs twice | Resource exhaustion, backlogs, or stalled jobs |

~~~mermaid
flowchart TD
    A["Triggers across replicas"] --> B{"Schedule coordination?"}
    B -->|"Yes"| C["Leader / Quartz cluster / lock"]
    B -->|"No"| D["Every pod may invoke launcher"]
    C --> E["Shared JobRepository"]
    D --> E
    E --> F["Immutable identifying params by business key"]
    F --> G["Spring Batch JobExecution/StepExecution"]
    G --> H["Idempotent Writer / HTTP / broker"]
    H --> I[("Target data store")]
~~~

## 6. Spring Boot Example: One `JobInstance` Per Business Period

Suppose `dailySettlementJob` runs at 01:10 Vietnam time to process the **previous business day** from source `bank-A`. Even if every replica fires, all replicas pass **identical identifying parameters** to `JobLauncher`.

In Spring Boot 3.x / Spring Batch 5.x, configure a shared PostgreSQL JDBC `JobRepository` and disable Boot's automatic startup execution of all jobs:

~~~yaml
# application.yml — illustrative configuration values
spring:
  datasource:
    url: jdbc:postgresql://batch-db.internal:5432/batch_metadata
    username: ${BATCH_DB_USERNAME}
    password: ${BATCH_DB_PASSWORD}
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: never
~~~

Spring Batch metadata tables **must be created/migrated beforehand**. `initialize-schema: never` pairs cleanly with Flyway/Liquibase; never launch jobs before metadata schemas exist. In multi-datasource apps, verify which datasource backs `JobRepository`, which transaction manager governs metadata, and which datasource writers use.

### 6.1. Constructing Stable Identifying Parameters

~~~java
package com.example.integration.batch;

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
public class DailySettlementScheduler {
    private static final Logger log =
            LoggerFactory.getLogger(DailySettlementScheduler.class);
    private static final ZoneId BUSINESS_ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");

    private final JobLauncher jobLauncher;
    private final Job dailySettlementJob;

    public DailySettlementScheduler(
            JobLauncher jobLauncher,
            @Qualifier("dailySettlementJob") Job dailySettlementJob) {
        this.jobLauncher = jobLauncher;
        this.dailySettlementJob = dailySettlementJob;
    }

    @Scheduled(cron = "0 10 1 * * *", zone = "Asia/Ho_Chi_Minh")
    public void launchPreviousDay() {
        LocalDate businessDate =
                LocalDate.now(BUSINESS_ZONE).minusDays(1);

        JobParameters params = new JobParametersBuilder()
                .addString("businessDate", businessDate.toString(), true)
                .addString("sourceId", "bank-A", true)
                .toJobParameters();

        try {
            JobExecution execution = jobLauncher.run(dailySettlementJob, params);
            log.info("Settlement launch: date={}, executionId={}, status={}",
                    businessDate, execution.getId(), execution.getStatus());
        } catch (JobExecutionAlreadyRunningException ex) {
            log.info("Settlement already running for {}: {}",
                    businessDate, ex.getMessage());
        } catch (JobInstanceAlreadyCompleteException ex) {
            log.info("Settlement already completed for {}: {}",
                    businessDate, ex.getMessage());
        } catch (JobRestartException | JobParametersInvalidException ex) {
            log.error("Settlement launch rejected for {}", businessDate, ex);
            throw new IllegalStateException(
                    "Settlement requires operator attention", ex);
        }
    }
}
~~~

This assumes `dailySettlementJob` is defined, `@EnableScheduling` is active, and all replicas share **the same metadata database**. `jobLauncher.run(...)` may execute synchronously or return immediately in `STARTING`/`STARTED` depending on launcher setup; logging the returned status **does not prove the job finished**.

**Crucial distinction:** the code above does not lock `@Scheduled` across replicas; every pod still calls the launcher. With a shared JDBC `JobRepository` and identical identity, Spring Batch relies on metadata and transactions to coordinate or reject duplicate launches for that instance. To eliminate redundant triggers and pre-launch side effects, pair this with proper scheduler coordination.

Computing `businessDate` from local calendar time is a business rule—not a substitute for handling holidays, weekends, DST in shifting timezones, or late partner files. When rerunning a historical date, pass the **explicit requested date** via admin API/scheduler rather than letting restarts recompute "yesterday."

### 6.2. Avoiding Two Common Identity Mistakes

~~~java
// WRONG when intending to restart the same business period:
new JobParametersBuilder()
        .addString("businessDate", "2026-11-20", true)
        .addLong("run.id", System.currentTimeMillis(), true)
        .toJobParameters();

// RIGHT for identity when restarting the same batch:
new JobParametersBuilder()
        .addString("businessDate", "2026-11-20", true)
        .addString("sourceId", "bank-A", true)
        .toJobParameters();
~~~

Never flip `run.id` to `identifying=false` carelessly without checking impact: non-identifying parameters can vary between executions of the same instance, yet if they alter **inputs or business behavior**, restarts will not reproduce the same batch. Mark every parameter defining **the logical dataset** as identifying.

### 6.3. Defining a Restartable Job and Step

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;

@Bean
Job dailySettlementJob(JobRepository jobRepository, Step settlementStep) {
    return new JobBuilder("dailySettlementJob", jobRepository)
            .start(settlementStep)
            .build();
}
~~~

In Spring Batch 5, `JobBuilder` takes `JobRepository` directly instead of legacy factory builders changed across upgrades. Do not call `preventRestart()` if business rules require resuming failed runs. Spring Batch skips already-`COMPLETED` steps on restart by default; enable `allowStartIfComplete(true)` only for steps intentionally meant to re-execute, as doing so can repeat side effects.

## 7. Choosing a Cross-Replica Coordination Strategy

No single option fits every architecture:

| Approach | How It Works | Best Fit | Risks to Manage |
| --- | --- | --- | --- |
| **Dedicated single scheduler** | Only one scheduler deployment fires crons; workers scale separately. | Small/medium setups with clean topology. | Needs HA for the scheduler; rolling restarts can overlap triggers if uncoordinated. |
| **DB / distributed lock** | Worker runs only while holding a lease for `jobName + businessKey`. | Keeping `@Scheduled` while preventing multi-pod launches. | Lease expires mid-run; clock skew, lock-store outage, split-brain. |
| **Quartz JDBC clustered** | Nodes share a Quartz JDBC `JobStore` and logical scheduler. | Rich schedules, multiple triggers, misfire/failover rules. | Wrong `JobStore`/`JobKey`, clustering off, schema and clock sync. |
| **Spring Batch shared repository** | Multiple pods invoke launcher while metadata coordinates `JobInstance`. | Batch jobs needing instance identity and restart checkpoints. | Still fires redundant triggers; requires exact identifying params and shared DB. |
| **Kubernetes `CronJob` / `Job`** | Orchestrator spawns pods on schedule per `concurrencyPolicy` and retries. | Standalone batch workloads decoupled from HTTP deployments. | Pod retries or overlapping schedules can still repeat side effects. |

Usually, **scheduler coordination and `JobRepository` complement rather than replace each other**. Quartz decides **who fires the trigger**, Spring Batch tracks **execution state and checkpoints**, and idempotency guards **whether targets applied an effect before**.

### 7.1. Distributed Locks: Lease Duration vs. Execution Time

Suppose a lock `settlement:bank-A:2026-11-20` has a 30-minute TTL:

- Pod A acquires the lock and runs for 45 minutes.
- At minute 30, the lease expires while Pod A keeps working.
- Pod B acquires the lock and starts processing the same day.

Setting `lockAtMostFor`/TTL shorter than actual runtime causes **concurrent duplicate runs**. Size leases properly, use **renewal/heartbeats** where supported, and enforce **fencing tokens or target constraints** so stale workers cannot keep writing after losing ownership. Also define policies for clock skew and lock-store outages.

Conversely, overly long leases block retries for ages after a hard crash. A lock only guards **entry into the critical section**; it does not prove which side effects committed or where restarts resume.

### 7.2. Quartz Clustering in Spring Boot

Reference configuration for Quartz JDBC shared across pods:

~~~yaml
spring:
  quartz:
    job-store-type: jdbc
    jdbc:
      initialize-schema: never
    properties:
      org:
        quartz:
          scheduler:
            instanceName: IntegrationScheduler
            instanceId: AUTO
          jobStore:
            isClustered: true
            clusterCheckinInterval: 15000
~~~

All nodes must point to **the same Quartz database**, use the same logical `instanceName`, standardize job/trigger keys, and hold **unique `instanceId`s**. Provision version-matched Quartz tables before startup; never run schema-init scripts that drop or wipe production tables. Keep node clocks synchronized and configure misfire thresholds thoughtfully.

In Quartz, `@DisallowConcurrentExecution` blocks concurrent runs of **the same `JobDetail`** across nodes when JDBC clustering is configured properly. It does not block two distinct `JobDetail`/`JobKey` definitions executing the same business logic. When Quartz triggers Spring Batch, still use deterministic identifying `JobParameters` and a shared `JobRepository`.

**Never run Quartz `RAMJobStore` per pod expecting cluster coordination.** Clustering requires a persistent JDBC `JobStore` configured consistently; setting cluster properties alone will not coordinate nodes using isolated in-memory stores.

## 8. Diagnostic Workflow for Duplicate Jobs

When duplicates hit production, **stop further duplicate side effects** before altering schedules:

1. **Throttle new triggers** via scheduler flags, feature flags, or pausing consumers. For financial or non-idempotent targets, coordinate with downstream owners—never trigger blind retries.
2. **Collect evidence:** business key, `jobName`, identifying parameters, `JobExecutionId`, pod/instance, start/end timestamps, correlation IDs, and trigger source.
3. **Check whether runs shared one `JobInstance` or split across instances** in `JobRepository`.
4. **Inspect scheduler / locks:** how many pods run `@Scheduled`; is Quartz using JDBC clustering or RAM; did leases expire mid-run?
5. **Inspect downstream data:** unique keys, upserts, outbox/inbox rows, idempotency keys, and how far external calls got.
6. **Reconcile before repairing:** row counts, totals, outbound call counts, target states, and suspected duplicates.
7. **Resume gradually** with strict identity, bounded concurrency, and monitoring until backlogs drain.

### 8.1. Read-Only SQL for Inspecting Spring Batch Metadata

These queries illustrate **Spring Batch 5.x metadata schema on PostgreSQL**; verify exact table names, prefixes, schemas, and read-only privileges in your environment:

~~~sql
SELECT
    ji.JOB_NAME,
    ji.JOB_KEY,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.CREATE_TIME,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
    ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'dailySettlementJob'
ORDER BY je.CREATE_TIME DESC
LIMIT 50;
~~~

To inspect identifying parameters of a specific execution:

~~~sql
SELECT
    JOB_EXECUTION_ID,
    PARAMETER_NAME,
    PARAMETER_TYPE,
    PARAMETER_VALUE,
    IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE JOB_EXECUTION_ID = :executionId
ORDER BY PARAMETER_NAME;
~~~

In Spring Batch 5.x, the parameter table uses columns such as `PARAMETER_NAME`, `PARAMETER_TYPE`, and `PARAMETER_VALUE`; **do not copy this query for Spring Batch 4.x**, whose schema differs. If multiple executions for the same day sit under different `JOB_INSTANCE_ID`s, inspect `JOB_KEY` and which identifying parameter changed.

Check step-level commits:

~~~sql
SELECT
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :executionId
ORDER BY STEP_EXECUTION_ID;
~~~

**Never edit `BATCH_*` tables via ad-hoc SQL** to clear running flags or mutate execution status. Unsynchronized edits across Batch tables corrupt restart metadata, and a live worker can keep writing against stale checkpoints.

## 9. Safe Restart Workflow After Failures or Stops

Spring Batch can restart a failed or stopped `JobInstance` when the job permits restarts and metadata is consistent. Safe workflow:

1. **Identify the `JobInstance`** by job name + identifying parameters; avoid launching the wrong business period.
2. **Verify latest execution state** and process ownership. If `STARTED`, confirm whether the worker is alive or crashed.
3. **Fix root cause:** missing file, schema drift, HTTP outage, deadlocks, expired secrets, down broker, or bad input data.
4. **Verify input immutability:** file checksums, API snapshots, pagination stability, schema, and reader versions.
5. **Inspect checkpoints:** did step context save a valid position? Which chunks committed? Did non-DB side effects run before crashing?
6. **Restart the exact `JobInstance`** after fixing the cause, using supported operations and matching identifying parameters / `JobExecution` IDs.
7. **Reconcile data and monitor completion:** row counts, totals, business keys, duplicate counts, remote status, and queue/event lag.

Flowchart:

~~~mermaid
flowchart TD
    A["Job incomplete"] --> B{"Latest execution status?"}
    B -->|FAILED or STOPPED| C["Check root cause + input + checkpoint"]
    B -->|STARTED| D{"Worker still alive?"}
    D -->|Yes| E["Do not restart; monitor or stop cleanly"]
    D -->|No| F["Incident runbook: verify and resolve orphaned metadata"]
    B -->|COMPLETED| G["Do not restart same instance; evaluate new batch need"]
    C --> H["Restart exact JobInstance"]
    F --> H
    H --> I["Idempotency + reconciliation"]
~~~

### 9.1. `JobExecution` Stuck in `STARTED` After a Pod Crash

A sudden process kill can prevent updating `JobExecution` from `STARTED` to `FAILED`. Spring Batch does not automatically clean up orphaned executions across every deployment model. Attempting a restart immediately can fail because the framework thinks the job is **still running**.

Remediation steps:

- Verify deployment state, pod UID, heartbeats/logs/metrics, that the container truly stopped, and that no remote/async workers remain active.
- Block new triggers temporarily; protect outputs via fencing/idempotency in case an old worker resurfaces.
- Record `executionId` plus snapshots of metadata and committed business transactions.
- Use **supported operational tools or `JobRepository` APIs** to transition the orphaned execution into a restartable state per tested runbook. Touch metadata only after confirming zero live workers and documenting audit/rollback steps.
- Restart the exact instance and reconcile chunks that may have committed right before checkpointing.

`JobOperator.stop(executionId)` primarily signals a **living cooperative execution**; calling stop against a dead process does not guarantee metadata recovery. Never build a cron that "marks any `STARTED` older than 10 minutes as `FAILED`" if valid jobs legitimately run longer than 10 minutes.

### 9.2. `COMPLETED` Is Not a Restart Bug

When a `JobInstance` is `COMPLETED`, Spring Batch properly rejects relaunching the same instance. When **reprocessing** is genuinely needed:

1. Confirm whether this is a new input revision or an authorized correction rerun.
2. Introduce a deliberate business version or `reprocessId` parameter if launching a new `JobInstance` is intended.
3. Ensure writers are idempotent, detect payload conflicts, and never duplicate side effects.
4. Never overwrite `COMPLETED` to `FAILED` merely to bypass framework checks.

**Restart** resumes the same logical processing run; **reprocess** launches a newly authorized logical run. Both carry distinct contracts and risks.

## 10. When Restarts Re-Read from the Beginning or Lose Checkpoints

Suppose a job reads a 20,000-line file in chunks of 100, commits 120 chunks, and crashes. On restart, the reader should resume after chunk 120. Common reasons it fails:

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Re-reads from line 1 | Fresh `run.id` each launch; reader `saveState=false`; `ItemStream` not registered. | Keep identifying params stable and register stateful reader lifecycle. |
| Skips wrong rows on resume | Input file edited/inserted/deleted; unstable SQL sort/pagination. | Use immutable inputs, checksums, snapshot IDs, and deterministic key sorting. |
| Completed step runs again causing duplicates | `allowStartIfComplete(true)` set, or new instance created. | Enable only when intended; keep outputs idempotent. |
| Next step misses prior step's context | Wrong reader key name, job vs. step context scope, or serialization mismatch. | Isolate keys; use `ExecutionContextPromotionListener` for cross-step sharing. |
| Checkpoint advanced while target DB missed writes | Metadata and business DB use separate transaction managers. | Align transactions, outbox, or safe reconciliation/replay. |
| Target DB committed while checkpoint did not | Crash between two independent transactional stores. | Unique keys/inbox/idempotent writers; never assume cross-DB exactly-once. |

In chunk-oriented steps, `ItemStream.open(ExecutionContext)` restores state and `ItemStream.update(...)` updates checkpoints per commit before `JobRepository` persists them. Custom readers/writers must implement and **register** `ItemStream` properly rather than holding an in-memory `int currentRow` field.

### 10.1. Transaction Boundaries Determine Recoverability

~~~mermaid
sequenceDiagram
    participant Job as Batch Step
    participant DB as Business DB
    participant Repo as JobRepository
    participant API as External HTTP/Broker
    Job->>DB: Write chunk
    Job->>API: Trigger side effect
    API-->>Job: Processed
    Job->>Repo: Update checkpoint
    Note over Job,Repo: Process crashes before metadata commit
    Note over DB,API: Restart may replay side effect
~~~

This illustrates **independent transactional resources**: rolling back JDBC never undoes an HTTP POST or payment already executed. Even when a Batch writer writes to a different DB than `JobRepository`, checkpoints and business commits can diverge.

Safe designs rely on unique business keys, operation IDs reused across retries/restarts, target-side idempotency, reconciliation, and **transactional outbox** for post-commit event publishing. Never treat a "processed" flag in `ExecutionContext` as a distributed transaction with external partners.

## 11. Upgrading Spring Boot / Spring Batch Without Breaking Restarts

Restart failures often appear right after upgrades due to metadata incompatibilities or altered job/step identities. An upgrade plan must audit:

| Item | What to Verify | Impact If Missed |
| --- | --- | --- |
| **Spring Boot / Spring Batch versions** | Dependency matrix, JDK, Hibernate/JPA, builder APIs. | Missing beans, class errors, wrong transaction managers. |
| **Metadata schema** | Migrate `BATCH_*` tables along the **exact upgrade path**; back up first. | Cannot deserialize params/contexts; launches/restarts fail. |
| **Job identity** | Job names and identifying parameter meanings unchanged. | Spawns duplicate `JobInstance`s and reprocesses historical data. |
| **Step / reader names** | `Step` names, `ItemStream` names, and `ExecutionContext` keys stay stable. | Readers miss saved checkpoints or steps re-run. |
| **`ExecutionContext` serializer** | Legacy serialized values and class names still decode cleanly. | Old failed jobs fail deserialization after deploy. |
| **Transactions / datasources** | `JobRepository` targets right schema; writers share TX when designed. | Checkpoints and business data drift. |
| **Scheduler / Quartz** | Quartz `JobStore`, instance IDs, `JobKey`s, trigger keys, misfire policies, schema. | Duplicate fires or silent schedule stalls post-upgrade. |
| **Application startup** | Did auto-running jobs on startup accidentally re-enable across all pods? | Pods launch batches immediately during rollout. |

### 11.1. Spring Batch 4 → 5 Metadata and API Changes

When upgrading from legacy stacks to Spring Boot 3 / Spring Batch 5, follow the official migration guide closely. For example, Batch 5's parameter schema uses `PARAMETER_NAME`, `PARAMETER_TYPE`, `PARAMETER_VALUE`, and `IDENTIFYING` instead of Batch 4's layout. Deploying new binaries without migrating metadata breaks launches and history reads. Builder APIs (`new JobBuilder(name, jobRepository)`, `new StepBuilder(name, jobRepository)`) also replace legacy factory builders.

Never drop and recreate empty metadata tables as a migration shortcut: you erase checkpoints and execution history while business writes remain committed. **Back up, apply versioned migrations, test restarting real failed jobs on sanitized production snapshots**, and prepare controlled rollbacks.

### 11.2. Safe Rollout Workflow

1. Inventory all `STARTED`/`FAILED`/`STOPPED` `JobInstance`s, long-running jobs, and non-reproducible input sources.
2. Pause new triggers or drain active critical jobs per policy so old and new versions never process the same business window concurrently.
3. Back up metadata and domain tables; execute migrations in strict order.
4. Boot the candidate version in staging against **legacy-version metadata** and verify restarting a real failed instance.
5. Roll out carefully, confirming zero replicas point at mismatched metadata schemas or altered job names.
6. Monitor launch logs, `JobExecutionAlreadyRunningException`, `JobRestartException`, duplicate counts, and target data freshness.
7. Maintain an app rollback plan **paired with schema compatibility**: rolling back binaries does not revert database metadata migrations automatically.

## 12. Two Classic Incident Runbooks

### 12.1. Scenario A: Three Duplicate Reconciliation Records Every Day

**Context:** Three replicas all invoke `@Scheduled` at 01:00. After an upgrade, the reconciliation table receives three identical sets per day.

**Evidence to gather:** Whether the three `JobExecution`s for the same `businessDate` share one `JOB_INSTANCE_ID` or differ, `sourceId` and `run.id` per attempt, `JobRepository` datasource wiring, and whether `@Scheduled` is active on all pods.

**Diagnostic branches:**

- If `JOB_KEY` differs across the three instances due to identifying UUIDs/timestamps → lock identity to immutable business keys.
- If pods wrote to separate repositories → unify shared JDBC metadata, schemas, migrations, and grants.
- If one `JobInstance` ran yet writers still duplicated effects on crashes/retries → inspect transactions, idempotency, event IDs, and broker ACKs.
- If Quartz fired multiple `JobKey`s for the same period → consolidate `JobDetail`/trigger identities, enable JDBC clustering, and enforce concurrency limits.

**Recovery:** Halt duplicate triggers, reconcile by `businessDate + sourceId + operationId`, repair data cleanly under audit and authorization, then re-enable with unified scheduling and tests proving zero duplication. **Never mass-delete duplicate rows before verifying which transactions external partners already settled.**

### 12.2. Scenario B: Pod Killed, Restart Fails with "Already Running"

**Context:** A job ran 50 minutes before a rolling deploy killed the pod; metadata stays `STARTED`. The next scheduler trigger fails with `JobExecutionAlreadyRunningException`.

**Evidence to gather:** Confirm the old pod is truly dead and no remote/async workers remain, capture the latest execution ID, step contexts/checkpoints, committed DB writes, and whether HTTP/broker side effects fired.

**Recovery:** Pause new triggers, verify zero live workers remain, follow your tested runbook using supported APIs/tools to clean the orphaned state, then restart the exact `JobInstance`. If metadata cannot be recovered safely, run an **audited, idempotent reprocess plan** instead of bumping `run.id` to bypass locks.

**Prevention:** graceful shutdown/stop hooks, adequate termination grace periods, worker heartbeats/lifecycle tracking, metadata retention, safe checkpoints, and mid-chunk crash tests.

## 13. Multi-Replica Observability and Testing

### 13.1. Metrics and Logs to Collect

- **Scheduler:** trigger count per pod, job key, business window, lock acquisition success/failure, lease expirations, rejected triggers.
- **Spring Batch:** job name, `JobInstance` ID, `JobExecution` ID, redacted identifying parameters, status, start/end time, duration, `readCount`/`writeCount`/`commitCount`/`rollbackCount`/`skipCount`.
- **Restarts:** overdue `STARTED` executions, restart successes/failures, checkpoint age, context deserialization errors, schema migration errors.
- **Broker / outbound:** event IDs, duplicate counts, consumer lag, retries/DLQs, HTTP 429/timeout counts, side effects awaiting reconciliation.
- **Business:** record counts and totals per `businessDate + sourceId`, duplicate keys, missing rows, partner statuses.

Put `jobName` and job type in metric tags, avoiding high-cardinality tags like `executionId`, `orderId`, or millions of business keys; keep those in access-controlled structured logs and traces with retention policies.

### 13.2. Mandatory Test Scenarios

| Scenario | What Must Be Proven |
| --- | --- |
| Three app contexts/pods call launcher for one `businessDate` | Only one logical `JobInstance` executes validly; downstream effects occur once per contract. |
| Three pods run `@Scheduled` backed by shared `JobRepository` | Multiple triggers fire yet never create triple runs for the same identity. |
| Identifying `run.id` enabled deliberately | Test reproduces multi-instance bug to enforce identity policy. |
| Crash before chunk commit | Transaction rolls back writes; restart resumes from last committed checkpoint. |
| Crash after HTTP side effect before checkpoint | Same `operationId` preserved; idempotency/reconciliation prevents duplicates. |
| Crash leaving `STARTED` orphan | Runbook detects it, blocks concurrent workers, and recovers metadata safely. |
| Already `COMPLETED` `JobInstance` | Restart with identical identifying params fails; reprocess uses intentional new version. |
| Source file/snapshot modified after failure | Checksum or version mismatch detected rather than resuming at unreliable offsets. |
| Rolling deploy while old job runs | Old and new versions never double-process one period; metadata/schemas stay compatible. |
| Quartz JDBC cluster node failover | Triggers avoid duplicate business effects; keys and misfire policies hold. |
| Distributed lock expires mid-run | Fencing or idempotent writers block old and new workers from corrupting data. |
| Broker retries / redeliveries | Consumers avoid duplicate records or uncontrolled repeat partner API calls. |

With Spring Batch, use `@SpringBootTest`/`spring-batch-test`, a **real or Testcontainers metadata database**, and spin up two competing contexts/processes sharing that DB. Never wipe `JobRepository` between the failed attempt and restart inside the same test—doing so erases the checkpoint under test.

Asserting "only one `JobExecution`" is insufficient when workers trigger external side effects: assert **target database rows**, outbound HTTP call counts, and timeout reconciliation. Inject faults at DB commits, `JobRepository` updates, broker publishes, and ACKs rather than mocking methods to return `true`.

## 14. Troubleshooting and Upgrade Checklist

- [ ] Identified all trigger sources (`@Scheduled`, Quartz, Kubernetes, broker, API) and replica counts.
- [ ] Mapped immutable business keys (`businessDate + sourceId + version`) onto identifying `JobParameters`.
- [ ] Confirmed all pods share **one JDBC `JobRepository`** with identical schema, prefix, transactions, and migrations.
- [ ] Verified no UUID, timestamp, or identifying `run.id` changes when **restarting the same batch**.
- [ ] Audited distributed locks, lease durations, fencing, Quartz JDBC clustering, `JobKey`s, clock skew, and overlap prevention.
- [ ] Enforced idempotency/unique constraints, stable operation IDs, and reconciliation on writers, HTTP clients, and consumers.
- [ ] Distinguished `FAILED`/`STOPPED`/orphaned `STARTED`/`COMPLETED` with tested runbooks when standard restart APIs cannot proceed.
- [ ] Verified `ItemStream` readers, `ExecutionContext`s, and immutable input snapshots preserve valid checkpoints.
- [ ] Audited `BATCH_*` schemas, serializers, job/step names, transaction managers, and legacy-job compatibility prior to upgrades.
- [ ] Tested two competing replicas, mid-chunk crashes/restarts, lease expirations, rolling deploys, and duplicate target data.
- [ ] Deployed metrics, structured logs, alerts, and reconciliation tables tracking *what ran* and *what targets applied* beyond scheduler status.

**Conclusion:** "Duplicate jobs across replicas" is a problem of **trigger coordination, `JobInstance` identity, and idempotency**; "jobs failing to restart" is a problem of **metadata, execution states, checkpoints, transactions, and reproducible inputs**. In Spring Boot Integration, solve all layers together—especially across multiple databases, HTTP clients, caches, and brokers. Tweaking cron strings, bumping `run.id`, or editing one metadata row by hand never guarantees accurate business state after crashes or upgrades.
