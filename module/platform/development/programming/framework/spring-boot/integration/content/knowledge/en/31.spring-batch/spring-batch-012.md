# Multiple Jobs, Concurrency, and Duplicate JobInstance Detection

A Spring Boot application may execute multiple Spring Batch workloads: syncing orders from an HTTP API, importing partner database records, reconciling payments, computing daily reports, and emitting outcome events to a broker. When schedulers, HTTP endpoints, message consumers, and multiple replicas all fire triggers, two questions emerge: **which jobs are allowed to run in parallel?** and **do two launch requests represent the same logical unit of business work?**

Spring Batch provides `Job`, `JobParameters`, `JobInstance`, `JobExecution`, and `JobRepository` to model, persist state, and govern restartability. Mastering these concepts prevents re-running completed reports, duplicating data on broker redeliveries, and resource contention when concurrent jobs share databases or HTTP clients.

The running example is an e-commerce platform with two jobs:

- `importOrdersJob`: imports orders by business date (`businessDate`) and tenant.
- `reconcilePaymentsJob`: reconciles payments for the same date, able to run independently once data preconditions hold.

Java examples target **Spring Boot 3.x with Spring Batch 5.x**; in Spring Boot 4.x/Spring Batch 6.x, check packages and APIs for your managed version before copying code verbatim.

## 1. Distinguishing `Job`, `JobInstance`, `JobExecution`, and `StepExecution`

| Component | Meaning | Example |
| --- | --- | --- |
| `Job` | Workload definition including name, steps, and restart policy | `importOrdersJob` |
| `JobParameters` | Arguments supplied at launch; a subset participates in instance identity | `businessDate=2026-11-20`, `tenantId=shop-a` |
| `JobInstance` | **Logical processing run** identified by job name and identifying parameters | Importing orders of `shop-a` for `2026-11-20` |
| `JobExecution` | **A single execution attempt** of a `JobInstance` | Attempt 1 FAILED, attempt 2 COMPLETED |
| `StepExecution` | One execution of a step inside a `JobExecution` | `loadOrdersStep` processed 5,000 records |
| `ExecutionContext` | Persistable state for checkpoints and restarts | Last page read, file offset, cursor to restore |
| `JobRepository` | Metadata store holding instances, executions, statuses, and checkpoints | `BATCH_JOB_*`, `BATCH_STEP_*` tables |

Foundational formula:

~~~text
JobInstance identity = Job name + identifying JobParameters

JobInstance("importOrdersJob", businessDate=2026-11-20, tenantId=shop-a)
    ├── JobExecution #101: FAILED
    └── JobExecution #116: COMPLETED  (restart same instance)

JobInstance("importOrdersJob", businessDate=2026-11-21, tenantId=shop-a)
    └── JobExecution #117: COMPLETED  (different instance)
~~~

A new `JobExecution` after failure **does not necessarily** imply a new `JobInstance`. Spring Batch separates "re-running to recover" from "processing a fresh logical dataset" via identity and execution history.

~~~mermaid
flowchart TD
    A[Trigger: scheduler / HTTP / broker] --> B[Job name + identifying JobParameters]
    B --> C{JobInstance already exists?}
    C -->|No| D[Create new JobInstance]
    C -->|Yes| E{Status of prior execution?}
    E -->|COMPLETED| F[Reject re-running same instance]
    E -->|Running| G[Reject concurrent run of same instance]
    E -->|FAILED or STOPPED| H[Check restart eligibility]
    H -->|Yes| I[Create new JobExecution, restore checkpoint]
    H -->|No| J[Return restart error]
    D --> K[Execute Steps]
    I --> K
~~~

This is the general logical model. A launch can also fail due to invalid parameters, `JobRepository` errors, `UNKNOWN` status, or unrecovered metadata. Execution may be synchronous or asynchronous; returning from a launch call does not guarantee the final job state.

## 2. Selecting Identifying `JobParameters` from Business Keys

By default, parameters added via `JobParametersBuilder` are **identifying**. Pass `false` for observability-only parameters that should not create new instances.

~~~java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-20", true)
        .addString("tenantId", "shop-a", true)
        .addString("requestedBy", "scheduler", false)
        .addString("correlationId", "trace-abc", false)
        .toJobParameters();
~~~

For `importOrdersJob`, `businessDate` and `tenantId` form the business key. `requestedBy` and `correlationId` trace the trigger; changing their values does not turn an existing instance into a new one.

| Launch | Job Name | Identifying Parameters | Non-Identifying Parameters | Relationship |
| --- | --- | --- | --- | --- |
| A | `importOrdersJob` | date=20/11, tenant=A | requestedBy=scheduler | Instance X |
| B | `importOrdersJob` | date=20/11, tenant=A | requestedBy=HTTP | **Same instance X** |
| C | `importOrdersJob` | date=21/11, tenant=A | requestedBy=scheduler | Instance Y |
| D | `importOrdersJob` | date=20/11, tenant=B | requestedBy=scheduler | Instance Z |
| E | `reconcilePaymentsJob` | date=20/11, tenant=A | requestedBy=scheduler | Instance of a **different** job |

**How to choose keys:** ask "which unit of work must have at most one logical `JobInstance`?" For file imports, the answer may be `tenantId + fileChecksum + schemaVersion`; for daily reports, `tenantId + businessDate + reportType`. If source data changes without changing identity, a `COMPLETED` job blocks reprocessing the new data. Conversely, placing current timestamps or random UUIDs into identifying parameters causes *every retry of the same request* to spawn a new instance.

Never inject `System.currentTimeMillis()` as an identifying parameter just to dodge `JobInstanceAlreadyCompleteException`. Doing so eliminates instance-level deduplication. `RunIdIncrementer` helps when **intentionally** creating new instances for independent runs, yet must follow a business contract rather than acting as a Band-Aid for duplicate errors.

### 2.1. Normalizing Keys Before Launch

Normalize and validate:

1. Business dates in an agreed timezone; distinguish `businessDate` from trigger wall-clock time.
2. Canonical formats for tenant, file ID, version, and time ranges; avoid `SHOP-A` and `shop-a` being treated as different tenants.
3. Never place passwords, tokens, PII, or full JSON payloads in `JobParameters` because they persist to metadata.
4. Mark `false` only for values **that do not alter the target dataset or recovery logic**. Never alter core inputs when restarting the same instance.
5. For intentional reprocessing, define explicit identifying `revision` or `sourceSnapshotId` parameters backed by operator approval.

`JobParameters` only identifies the execution; it **does not automatically filter data**. Your `ItemReader`/Tasklet must actively use those parameters to scope queries by date and tenant. A job with the right keys whose reader scans the entire table still causes cross-day duplicates.

## 3. Spring Boot with Multiple Job Beans: Separating Definition from Activation

When Spring Boot auto-configures Spring Batch and finds a single `Job` bean, that job normally launches at application startup. With multiple job beans, you must specify which job to run via `spring.batch.job.name` if startup launch is desired. For API services or always-on workers, the cleaner pattern is **disabling automatic launch** and delegating execution to a scheduler, internal HTTP endpoint, or message handler.

~~~yaml
spring:
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: never
~~~

`initialize-schema: never` is a production example where Batch schemas are managed via migrations. In test setups, initialize schemas once using version/database-matched scripts; never let multiple replicas create or drop schemas at startup. Other property names or auto-configuration locations may differ across Spring Boot versions.

To launch **one** specific job on startup:

~~~yaml
spring:
  batch:
    job:
      name: importOrdersJob
~~~

This second configuration represents an alternative operational mode to `enabled: false`; if automatic launch is disabled, `name` does not trigger startup runs. Across multiple replicas of a web service, auto-running jobs on every startup creates unintended races. Use a coordinated scheduler and shared `JobRepository` instead of startup side effects.

### 3.1. Defining Two Independent Jobs

The example below focuses on registering **two distinct job names**, each with its own step; `tasklet` acts only as a placeholder—production import and reconciliation logic belongs in dedicated readers/processors/writers or tasklets.

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
class OrderBatchJobs {

    @Bean
    Step importOrdersStep(JobRepository repository, PlatformTransactionManager tx) {
        return new StepBuilder("importOrdersStep", repository)
                .tasklet((contribution, context) -> {
                    // Illustration: call import service with transactions/idempotency.
                    return RepeatStatus.FINISHED;
                }, tx)
                .build();
    }

    @Bean
    Step reconcilePaymentsStep(JobRepository repository, PlatformTransactionManager tx) {
        return new StepBuilder("reconcilePaymentsStep", repository)
                .tasklet((contribution, context) -> {
                    // Illustration: read payment snapshot, create reconciliation records.
                    return RepeatStatus.FINISHED;
                }, tx)
                .build();
    }

    @Bean
    Job importOrdersJob(JobRepository repository,
                        @Qualifier("importOrdersStep") Step importOrdersStep) {
        return new JobBuilder("importOrdersJob", repository)
                .start(importOrdersStep)
                .build();
    }

    @Bean
    Job reconcilePaymentsJob(JobRepository repository,
                             @Qualifier("reconcilePaymentsStep") Step reconcilePaymentsStep) {
        return new JobBuilder("reconcilePaymentsJob", repository)
                .start(reconcilePaymentsStep)
                .build();
    }
}
~~~

Each `Job` needs a stable, unique name in the shared repository; keeping bean names aligned with job names aids maintainability. Never rename jobs across deployments if you need to preserve restart history. Any steps sharing stateful components/readers must be checked for thread safety and checkpointing; in real apps, keep business logic out of job wiring classes.

Spring Boot 3.x normally supplies `JobRepository`, `JobLauncher`, and transaction manager via auto-configuration when dependencies and a datasource exist. Never add `@EnableBatchProcessing` arbitrarily to apps relying on auto-configuration, as it alters how infrastructure beans are wired. Verify contracts against your exact Boot version.

## 4. Controlled Launching with `JobLauncher`

In Spring Batch 5.x, applications inject `JobLauncher` and the exact `Job` bean. Avoid taking arbitrary job names from URLs and executing them blindly; enforce allowlists and caller/tenant authorization.

~~~java
import java.time.LocalDate;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
class ImportBatchLauncher {

    private final JobLauncher launcher;
    private final Job importOrdersJob;

    ImportBatchLauncher(JobLauncher launcher,
                        @Qualifier("importOrdersJob") Job importOrdersJob) {
        this.launcher = launcher;
        this.importOrdersJob = importOrdersJob;
    }

    JobExecution launch(LocalDate businessDate, String tenantId, String actor)
            throws Exception {
        JobParameters params = new JobParametersBuilder()
                .addString("businessDate", businessDate.toString(), true)
                .addString("tenantId", tenantId, true)
                .addString("requestedBy", actor, false)
                .toJobParameters();

        return launcher.run(importOrdersJob, params);
    }
}
~~~

In production code, catch specific launch exceptions (`JobExecutionAlreadyRunningException`, `JobInstanceAlreadyCompleteException`, `JobRestartException`, `JobParametersInvalidException`) and map them to the API contract. Using `throws Exception` here keeps the sample focused on job selection and identity creation.

**Important:** whether `JobLauncher.run(...)` runs synchronously or asynchronously depends on launcher configuration. When synchronous, it blocks the HTTP thread until the job completes; for multi-minute/multi-hour jobs, route requests into a bounded launch mechanism returning a `jobExecutionId`/request ID for status polling. When asynchronous, the returned `JobExecution` may still be `STARTING`/`STARTED`—never interpret it as COMPLETED.

Example HTTP contract:

| Situation | Suggested Response | Rationale |
| --- | --- | --- |
| New request accepted | `202 Accepted` with request/execution ID | Client polls status later |
| Instance already running | `200`/`202` pointing to active execution or `409 Conflict` | Pick one explicit idempotent contract |
| Instance already `COMPLETED` | `200 OK` returning prior result, or `409` if API rejects repeats | Never creates a new execution |
| Instance `FAILED` and restart-eligible | Starts new `JobExecution` on **the same instance** | Resumes from valid checkpoint |
| Invalid or unauthorized parameters | `400`/`403` | Prevents out-of-scope executions |

Return "running" or "completed" only after verifying `JobRepository`—never infer it from in-memory app caches. Never catch exceptions and silently inject `run.id` to force execution.

## 5. What Happens on Duplicate `JobInstance` Launches?

Spring Batch identifies a `JobInstance` by job name and **identifying parameter set**. Typical behavior when calling `JobLauncher.run` with the same identity:

| Existing Instance State | Duplicate Identity Launch | Typical Result |
| --- | --- | --- |
| Does not exist | First run | Creates new `JobInstance` and `JobExecution` |
| Active `JobExecution` running | Duplicate command | `JobExecutionAlreadyRunningException` |
| Latest `JobExecution` `COMPLETED` | Duplicate command | `JobInstanceAlreadyCompleteException` |
| `JobExecution` `FAILED` | Re-launch | New `JobExecution` to **restart**, if job/steps allow |
| `JobExecution` `STOPPED` | Re-launch | Restartable once stop state is stable |
| Job not restartable | Re-launch after failure | `JobRestartException` or corresponding restart error |
| `UNKNOWN` status, inconsistent metadata | Re-launch | Do not force forward; investigate and recover operationally |

Concurrent launches colliding right as two transactions insert metadata can raise database/isolation-specific exceptions alongside standard Spring Batch exceptions. External contracts should treat these as "same-identity collision" after re-reading repository state, rather than relying on one exact exception class.

Two special rules:

- **`FAILED` vs. `COMPLETED`:** same identity after `FAILED` restarts cleanly at the checkpoint; forcing a new instance with a timestamp risks re-reading from the start and duplicating side effects.
- **Re-running after `COMPLETED`:** confirm whether business inputs changed or reprocessing is genuinely warranted, then pass an identifying revision or new data-source parameter. Never delete metadata manually to "free" an instance.

Distinct `JobInstance`s are allowed to run concurrently unless restricted otherwise, even under the same job definition; Spring Batch does not globally serialize all instances of a job.

## 6. Concurrency Exists at Multiple Levels

Do not conflate every kind of parallelism into one feature.

| Concurrency Level | What Runs in Parallel | Controlled By | Conditions to Check |
| --- | --- | --- | --- |
| **Multiple jobs** | `importOrdersJob` and `reconcilePaymentsJob` | Scheduler, job launcher/executor | DB contention, data dependencies |
| **Multiple instances** | Same `importOrdersJob` for different dates/tenants | `JobLauncher`, `JobRepository` | Overlapping inputs, idempotency |
| **Parallel steps** | Two independent steps inside one job | `split`, `TaskExecutor` | Genuine transaction/state independence |
| **Multi-threaded step** | Multiple processing units inside one step | Step task executor and concurrency | Reader/processor/writer thread safety, chunk transactions |
| **Partitioning** | Partitions of one step | `Partitioner`/`PartitionHandler` or workers | Disjoint data slices, per-partition restarts |
| **Remote chunking** | Chunks sent over broker to workers | Messaging middleware/adapters | At-least-once delivery, acks, dedup, timeouts |

This lesson focuses on **multiple Jobs and `JobInstance`s**. Running two jobs concurrently does not require multi-threading a step. Conversely, launching two jobs on two threads does not prevent them from contending over the same DB tables or partner HTTP quotas.

### 6.1. Dependency Types to Model

- `reconcilePaymentsJob` runs only after that day's imports complete: enforce via DB completion markers, scheduler workflows, or explicit job flows; blind concurrency risks reconciling incomplete data.
- Two jobs updating the same table with row locks: align transaction boundaries, indexes, and update ordering to avoid deadlocks, or serialize by business key.
- Multiple instances reading from one file: identity must include file/snapshot so reads do not overlap; otherwise lock the resource explicitly.
- Multiple jobs sharing a quota-limited partner API: apply a shared rate limiter/bulkhead instead of letting each job fire unbounded requests.

**`JobRepository` blocks two concurrent executions of the same instance**, yet does not stop two different instances from writing to the same business resource. Enforce "never process the same invoice twice" via domain keys, DB constraints, idempotency, and transactions.

## 7. JDBC `JobRepository` Is the Coordination Point Across Replicas

In multi-pod deployments, use a **shared, durable `JobRepository`**. In Spring Batch 5.x with JDBC, metadata lives in standard tables:

| Table | Contents |
| --- | --- |
| `BATCH_JOB_INSTANCE` | Instance ID, job name, job key |
| `BATCH_JOB_EXECUTION` | Each execution attempt, status, timestamps |
| `BATCH_JOB_EXECUTION_PARAMS` | Parameters and `IDENTIFYING` flag |
| `BATCH_JOB_EXECUTION_CONTEXT` | Job-level state for recovery |
| `BATCH_STEP_EXECUTION` | Step status and read/write/skip counts |
| `BATCH_STEP_EXECUTION_CONTEXT` | Step-level checkpoints |

In production, PostgreSQL/MySQL typically hosts one shared metadata database managed via version-matched migrations. If replicas point to separate `JobRepository` instances, each sees no active record for the same identity and runs anyway—Spring Batch cannot prevent duplicates across disconnected repositories.

The repository layer relies on transactions, locks/unique constraints, and isolation levels when creating `JobExecution`s to resolve launch races. **Reading "no `JobInstance` exists" and then manually inserting/launching is not atomic.** Two pods can both observe "none exists"; let the repository handle creation or enforce a transactional external business lock.

~~~mermaid
sequenceDiagram
    participant S as Scheduler
    participant A as Pod A
    participant B as Pod B
    participant R as JDBC JobRepository
    S->>A: launch(importOrdersJob, date=20/11, tenant=A)
    S->>B: launch(importOrdersJob, date=20/11, tenant=A)
    par Simultaneously
        A->>R: Create/check JobExecution by identity
        B->>R: Create/check JobExecution by identity
    end
    R-->>A: One request creates execution
    R-->>B: Other request: duplicate or already running
    Note over R: DB transaction/isolation resolves conflict
~~~

Isolation settings during metadata creation govern how racing launchers behave. Defaults and exact options vary across versions, repository types, and databases; inspect your Spring Batch settings, verify `create*` transaction behavior, and run race tests against **your real production database engine**. Never weaken isolation or drop unique constraints just to let jobs run in parallel more easily.

If an environment crashes, metadata may remain `STARTED` after the process died. Never update `STATUS` to `FAILED` via SQL just to re-run. Confirm the pod/worker actually terminated, inspect last transactions and side effects, then execute the recovery workflow supported by your version.

### 7.1. Schema and DB Lifecycle Precautions

- Separate metadata tables from business data via schemas or least-privilege grants; ensure app accounts hold exact required permissions.
- Never let multiple pods run schema initialization as ad-hoc migrations in production.
- Size connection pools for concurrent jobs, chunk transactions, and metadata transactions to prevent pool starvation.
- Periodically archive/purge metadata under operational retention policies accounting for active executions and restart windows; never delete records still needed for checkpoints.
- When multiple apps share one `JobRepository`, enforce **globally unique job names** so two different definitions never collide on name and identifying parameters.

## 8. Designing a Bounded Asynchronous Launcher

In HTTP-serving apps, calling `JobLauncher.run` synchronously for multi-minute jobs blocks request threads and times out clients. Configure the launcher with a task executor or queue requests into an internal scheduler.

**However, asynchronous does not mean unbounded concurrency.** Bound worker count and queue depth; reject excess requests cleanly with backpressure when full. Across multiple pods, a thread pool only caps concurrency per pod—not cluster-wide.

A clean flow:

~~~text
POST /internal/batch/import-orders {businessDate, tenantId}
  -> authenticate/authorize + validate input
  -> normalize identifying parameters
  -> persist request and return requestId (only once durable)
  -> bounded launch executor / scheduler
  -> JobLauncher creates JobExecution via shared JobRepository
  -> client GET /internal/batch/executions/{id} to poll status
~~~

To avoid losing commands if a pod crashes before a thread pool picks up the job, **persist requests durably before returning accepted**, such as in an inbox table or broker with proper acks. Pure in-memory `CompletableFuture.runAsync` drops pending jobs on restart.

Never tie HTTP trigger status to `BatchStatus.COMPLETED` when using an async launcher; launch output only means "created/in progress," while final status resides in `JobRepository`.

## 9. Scheduler, HTTP, and Broker Triggering the Same Business Date

Suppose `importOrdersJob` for `2026-11-20` receives three triggers:

1. Scheduler fires at 01:00.
2. Partner hits a re-run endpoint at 01:00:01.
3. Consumer receives a redelivered `StartImport` message because a previous ack was lost.

If all three use **identical** `jobName`, `businessDate`, and `tenantId` identifying parameters, every trigger targets **one logical `JobInstance`**. Duplicates receive "already running" or "already completed" instead of spawning three separate instances.

~~~mermaid
flowchart LR
    A[Scheduler] --> D[Normalize JobParameters]
    B[HTTP retry] --> D
    C[Broker redelivery] --> D
    D --> E[Shared JobRepository]
    E --> F[One logical JobInstance]
    F --> G[JobExecution 1, restart if needed]
~~~

**Parameter consistency is mandatory:** if the scheduler passes `2026-11-20` while the message handler passes current timestamp or a fresh UUID, Spring Batch sees two different identities and runs them in parallel.

For broker triggers:

- Messages must carry stable business keys, schema versions, and event/command IDs.
- Consumers should persist critical launch requests durably (inbox/command table) before acking; acking only after a long synchronous `launcher.run` risks poll timeouts and redelivery.
- Message ingestion can be **at-least-once**; enforce deduplication in the command table or by business key outside `JobRepository`.
- When a data revision warrants a new run, include `revision` explicitly in identity rather than substituting message receipt timestamps.

`JobRepository` tracks job history; it **is not** a transactional broker inbox and does not guarantee once-only side effects across HTTP/DB/brokers.

## 10. Restart and Checkpointing: Preserving Identity During Recovery

When a step fails mid-data, Spring Batch can create a new `JobExecution` under the existing `JobInstance`. To resume properly:

1. Job/steps are configured restartable and metadata persists durably.
2. Readers/writers save adequate checkpoints in `ExecutionContext` per `ItemStream` contract where applicable.
3. Parameters governing data sources and business scope **do not change** between the failed run and restart.
4. Chunk transactions roll back uncommitted writes; non-transactional side effects are idempotent.
5. Source data provides snapshots/versions or deterministic ordering; arbitrary source mutations between runs invalidate checkpoints.

For instance, a reconciliation job reads a file in fixed order with chunk size 100 and fails after committing 1,200 rows: restarting the same instance lets the reader resume from the committed checkpoint. Launching a **new instance** via `run.id` re-reads from line 1 and risks duplicate reconciliation entries.

When writers call HTTP APIs or publish to Pulsar/Kafka, DB transaction rollback does not undo external side effects. Enforce per-record/per-event idempotency keys, outboxes, or durable dispatch mechanisms. Step `skip`, `retry`, and `restart` can invoke processors/writers multiple times.

### 10.1. What Counts as an Intentional Re-Run?

Distinguish the business scenarios:

| Scenario | Recommended Identity | Goal |
| --- | --- | --- |
| Restart failed job for Nov 20 | **Keep** `businessDate=2026-11-20` and tenant | Resume from checkpoint |
| Run report for Nov 21 | **Change** `businessDate` | New dataset |
| Nov 20 source corrected; need revision 2 report | Add identifying `revision=2` or `sourceSnapshotId` | Intentional reprocess, distinct from prior output |
| Duplicate request after HTTP timeout | **Keep** original identity | Block duplicate launch |
| Re-trigger after `COMPLETED` with unchanged input | Do not create new instance | Return existing status/outcome |

This separates **restart** from **rerun**. A job may require policies to supersede or adjust earlier results when issuing a new revision; creating a new `JobInstance` does not automatically keep output data conflict-free.

## 11. Bounding Concurrency by Real Resource Budgets

Spring Batch lets distinct `JobInstance`s run concurrently, yet concurrency must fit infrastructure limits. When multiple jobs simultaneously query databases, call partner REST APIs, hit caches, and emit events, queues amplify failures.

| Resource | Risk Under High Concurrency | Mitigation |
| --- | --- | --- |
| JDBC connection pool | Pool exhaustion, timeouts, deadlocks | Cap job/step concurrency; size pools; tune transactions and indexes |
| CPU/JVM heap | GC pauses, `OutOfMemoryError`, slowdown | Tuned chunk sizes, streaming readers, bounded executors |
| Partner HTTP client | `429`, timeouts, tripped circuit breakers | Per-partner rate limits/bulkheads, jittered retries |
| Broker producer | Full send buffers, duplicate messages on retries | Outbox, bounded in-flight sends, idempotent events |
| Cache | Thundering herd on simultaneous misses | Single-flight coalescing, jitter, source throttling |
| Business tables | Row/range lock contention across jobs | Partition by business key, unique constraints/optimistic locking |
| Metadata repository | Contended transactions, sequence/row locks | Adequately sized shared DB, clean identities, latency monitoring |

Setting distinct `maxConcurrentJobs` caps per workload class (heavy imports, reconciliations, report exports) is effective. Across multiple replicas, enforce **cluster-wide** limits if sharing constrained downstream targets; a pod-local `ThreadPoolTaskExecutor` only caps one pod.

With parallel steps or partitioning, **total** concurrent workers equal pods × jobs × steps/partitions × threads. Compare that product against DB pool limits and partner API quotas rather than tuning one job's thread count in isolation.

## 12. Testing Duplicate Instances and Race Conditions

Sequential tests calling `jobLauncher.run(...)` one after another never prove multi-pod race conditions are handled. Test suites should cover:

| Scenario | Setup | Expectation |
| --- | --- | --- |
| Two differently named jobs, same date | Launch `importOrdersJob` and `reconcilePaymentsJob` | Distinct identities; run concurrently unless resource-constrained |
| Same job, different dates | Launch Nov 20 and Nov 21 | Two separate `JobInstance`s |
| Same job, identical identifying params | Two threads start simultaneously | Never creates two active valid executions for the same instance |
| Differing non-identifying params | Change `requestedBy`, keep tenant/date | Resolves to **the same** `JobInstance` |
| Launch again after `COMPLETED` | Repeat identical identifying params | Rejected or API returns prior result |
| Restart after `FAILED` | Fail mid-chunk, re-launch same identity | New `JobExecution` under same `JobInstance`; zero duplicate side effects |
| New instance with revision | Add identifying `revision` | New instance created and processed per reprocess rules |
| Two pods sharing JDBC repository | Synchronized trigger at barrier | Only one launch wins; loser sees collision |
| Two pods on separate repositories | Intentionally misconfigure datasources | Exposes dangerous duplicate processing; proves single-repo requirement |
| Worker crash/restart | Kill process mid-run | Metadata/checkpoints inspected; recovery neither drops nor duplicates data |
| Broker redelivery | Re-send identical command/event ID | Spawns no extra logical run/side effect outside contract |
| Heavy concurrent load | Many tenants/dates and jobs | DB pool, latency, retries, and queues stay within bounds |

How to test races: use a barrier/`CountDownLatch` to align start times and keep the step running long enough for two launchers to collide, then query the repository to verify **`JobInstance` count, `JobExecution` count, and statuses**. When testing against production-like PostgreSQL/MySQL, observe both Spring Batch exceptions and DB transaction/unique-key errors rather than hard-coding assertions that every race throws one single exception class.

Restart tests must assert **zero duplicate output records**—such as unique constraints on `(tenant_id, order_id, business_date)`—not merely `BatchStatus.COMPLETED`.

## 13. Observability and Operating Multiple Jobs

Monitor signals covering both infrastructure and business contracts:

| Metric / Log | Meaning |
| --- | --- |
| `job.name`, `batch.status`, run duration, queue wait | Slow, failing, or backlogged jobs |
| Duplicate launch rejections and active instance state | How often schedulers/HTTP/brokers replay triggers |
| `JobExecution` restart count per instance | Detects flapping jobs |
| `StepExecution` read/write/filter/skip/rollback counts | Distinguishes bad data from processing bottlenecks |
| Connection pool, deadlocks, HTTP `429`, broker publish latency | Measures concurrency contention |
| Actual processed records and business reconciliation mismatches | Verifies domain correctness |
| Executions stuck `STARTED` too long, heartbeat/`LAST_UPDATED` | Flags dead workers or hung jobs |

Never use raw `tenantId`, `orderId`, `businessDate`, or `jobExecutionId` as metric labels if they create high cardinality. Put correlation IDs, execution IDs, and business keys in access-controlled logs/traces; aggregate metrics by job, status, and error category.

`JobExecutionListener`/`StepExecutionListener` can emit start/end metrics; async systems also need status queries via `JobExplorer`/`JobRepository` rather than relying on the HTTP trigger response. When an execution enters an abnormal state, follow a runbook verifying live processes, committed data, checkpoints, and restart eligibility.

### 13.1. Read-Only Metadata Queries

Reference SQL query for a JDBC repository:

~~~sql
SELECT
    i.JOB_INST_ID,
    i.JOB_NAME,
    e.JOB_EXEC_ID,
    e.STATUS,
    e.START_TIME,
    e.END_TIME
FROM BATCH_JOB_INSTANCE i
JOIN BATCH_JOB_EXECUTION e
    ON e.JOB_INST_ID = i.JOB_INST_ID
WHERE i.JOB_NAME = 'importOrdersJob'
ORDER BY e.CREATE_TIME DESC;
~~~

This query uses column names from the Spring Batch 5.x JDBC schema. Verify exact DDL column names against your project's database and version; in Java apps, query via `JobExplorer` APIs. Never edit metadata via manual SQL to "fix" job statuses.

## 14. A Reliable Multi-Job Design Workflow

1. **Inventory jobs:** what each does, DB/HTTP/broker sources, schedules, and cross-job dependencies.
2. **Define identities:** pick identifying parameters from business keys and standardize formatting across schedulers, HTTP, and message triggers.
3. **Define retry vs. rerun:** keep identity identical for restarts; govern new input revisions via explicit new instances.
4. **Pick triggers:** disable startup auto-run in always-on apps where appropriate; delegate requests to schedulers or a command inbox.
5. **Share `JobRepository`:** validate JDBC schemas, transactions, isolation, and multi-replica visibility.
6. **Set resource budgets:** cap concurrent jobs, step concurrency, DB pools, HTTP rates, and broker backlogs.
7. **Make side effects idempotent:** DB transactions, unique keys, outbox/inbox, and stable event IDs protect retried work.
8. **Specify failure handling:** running-collision, completed-collision, restartable FAILED, invalid params, and worker crashes each get clear responses and runbooks.
9. **Test races:** run truly concurrent launchers against production-equivalent DBs; test checkpoint recovery, duplicates, and event redeliveries.
10. **Observe:** monitor executions, business dates, statuses, retries, resources, business outcomes, and overdue runs.

**Core principle:** `JobInstance` answers "is this the same logical work or new work?", while `JobExecution` answers "how did this execution attempt go?" Combine stable identifying parameters, a shared `JobRepository`, and clear restart policies to block duplicate launches. Then enforce concurrency, transactions, and idempotency across DB/HTTP/brokers so different jobs run safely in parallel while producing accurate results.

### References

- [Spring Batch Reference — Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `JobParameters`, `JobExecution`, and restarts.
- [Spring Boot Reference — Spring Batch](https://docs.spring.io/spring-boot/reference/io/spring-batch.html): multiple Job beans, startup runners, and `spring.batch.job.name`/`enabled`.
- [Spring Batch Reference — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): JDBC metadata, transactions, and launch isolation.
- [Spring Batch Reference — Running a Job](https://docs.spring.io/spring-batch/reference/job/running.html): launchers, parameters, and running jobs.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): parallel steps, multi-threaded steps, partitioning, and thread safety.
- [Spring Batch Reference — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): metadata tables and the `IDENTIFYING` flag.

Code samples follow Spring Batch 5.x conventions; `current` documentation links may reflect Spring Batch 6.x at reading time. Verify exact versions in your Spring Boot BOM and metadata DDL before applying directly to a project.
