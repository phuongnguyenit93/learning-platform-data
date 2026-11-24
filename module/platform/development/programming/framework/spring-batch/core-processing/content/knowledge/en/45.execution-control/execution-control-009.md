# Duplicate Launch Protection in Spring Batch

In a batch system, the same unit of work can be requested multiple times from a scheduler, a REST API, operator actions, a message broker, or retry mechanisms after a network timeout. If those requests spawn independent runs, the job could double-charge customers, write duplicate outputs, send multiple notifications, or contend over the same output file.

**Duplicate launch protection** is how you prevent duplicate launch requests from causing unintended processing. In Spring Batch, the core mechanism relies on `JobInstance` identity determined by **job name and identifying JobParameters**, combined with `JobRepository` managing `JobExecution`s. It is important to understand that duplicate launch protection, restart after failure, and output idempotency are related yet have distinct scopes.

This lesson belongs to **Spring Batch Core Processing → Execution control**, focusing on choosing business keys, concurrent launch behavior, multi-node protection, launching from schedulers/APIs, failure recovery, and testing race scenarios. Examples use Spring Batch 5.x+ APIs and Java 17+.

## 1. When Do Duplicate Launches Occur?

Suppose the `dailySettlementJob` job settles transactions for business date `2026-11-15`. A scheduler is enabled on two pods; meanwhile, a client resends a request because it never received the first response.

~~~text
01:00:00.000  Pod A: dailySettlementJob(businessDate=2026-11-15)
01:00:00.003  Pod B: dailySettlementJob(businessDate=2026-11-15)
01:00:00.020  API:   dailySettlementJob(businessDate=2026-11-15)
~~~

All three requests describe **the same logical unit of business work**. If every launch generates a random identifying parameter, Spring Batch may treat them as distinct jobs and allow them to run concurrently. That bug usually does not start in the write query—it starts with **misidentifying the run**.

| Duplicate Request Source | Common Cause | Expected Behavior |
|---|---|---|
| Scheduler across multiple app instances | Every node runs `@Scheduled`. | One business period must not run two executions of the same instance concurrently. |
| HTTP client retry | Server received the request, but the client missed the response. | Retried request with the same key is recognized as an existing job. |
| Operator clicks button multiple times | UI sends multiple consecutive requests. | Report running or already completed; do not spawn a duplicate run. |
| Broker redelivers message | ACK failed or message was redelivered. | Messages for the same business work produce no duplicate effects. |
| Job failed and operator re-runs | Need to resume a failed execution. | Allow a **valid restart** per policy. |
| Application just started | Spring Boot auto-run and scheduler both trigger. | Control a single trigger source or align on the same business key. |

The goal is not to forbid every repeated call to `JobLauncher.run(...)`, because some calls may be an intentional **restart**. You must clearly distinguish what constitutes duplicate work, what constitutes new work, and what constitutes retrying failed work.

## 2. How Do Job, JobInstance, and JobExecution Differ?

Spring Batch separates these concepts:

- **`Job`**: the batch process definition, e.g., `dailySettlementJob`.
- **`JobParameters`**: arguments for a launch request, such as business date, store, or request ID.
- **`JobInstance`**: a unique logical unit of work, identified by `jobName` and the set of **identifying parameters**.
- **`JobExecution`**: a single attempt to execute a `JobInstance`, with its own status and metadata.
- **`JobRepository`**: stores identity, status, execution history, and related checkpoints.

Example:

~~~text
Job: dailySettlementJob
Identifying parameters: businessDate=2026-11-15, storeId=ACME
                         |
                         v
                   JobInstance A
                         |
             +-----------+-----------+
             |                       |
       JobExecution #101       JobExecution #102
       status=FAILED           status=COMPLETED
                               (restart of A)
~~~

In this diagram, execution #102 is **a continuation of the same JobInstance A** after failure, not a new job instance. A `JobInstance` that succeeded and reached `COMPLETED` normally cannot be launched again with that exact identity.

### Identifying vs. Non-Identifying JobParameters

Spring Batch lets you mark parameters:

**Identifying = true:** participates in defining a `JobInstance`.

**Identifying = false:** stored in parameters for observability or runtime use, yet **does not create a new JobInstance** when its value changes.

| Job | Identifying Parameters | Non-Identifying | Identity |
|---|---|---|---|
| `dailySettlementJob` | `businessDate=2026-11-15`, `storeId=ACME` | `requestId=req-1` | Instance A |
| `dailySettlementJob` | `businessDate=2026-11-15`, `storeId=ACME` | `requestId=req-2` | **Still Instance A** |
| `dailySettlementJob` | `businessDate=2026-11-16`, `storeId=ACME` | `requestId=req-3` | Instance B |
| `dailySettlementJob` | `businessDate=2026-11-15`, `storeId=OTHER` | `requestId=req-4` | Instance C |
| `anotherJob` | `businessDate=2026-11-15`, `storeId=ACME` | `requestId=req-5` | Different instance because Job name differs |

Java example:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("storeId", "ACME", true)
    .addString("requestId", "req-57", false)
    .toJobParameters();
~~~

From a duplicate-protection perspective, **choosing the right identifying parameters is the most important decision**. Two calls processing the same date/store must produce the same job name and the same identifying parameter set, even when the request ID differs.

## 3. How Does JobRepository Enforce Protection?

Upon receiving `JobLauncher.run(job, parameters)`, Spring Batch uses `JobRepository` to look up or create the `JobInstance` and create an appropriate `JobExecution`. With a standard JDBC JobRepository schema, `BATCH_JOB_INSTANCE` stores the job name and `JOB_KEY` (derived from identifying parameters) with a uniqueness constraint on `(JOB_NAME, JOB_KEY)`.

Execution creation is managed inside a transaction with isolation and database constraints so two concurrent launchers cannot both be accepted for the same instance. This is especially critical across multiple pods/JVMs.

~~~mermaid
flowchart TD
    A["Launch request + identifying parameters"] --> B["JobRepository looks up / creates JobInstance"]
    B --> C{"Instance execution history"}
    C -->|No prior execution| D["Create new JobExecution"]
    C -->|Currently running| E["Reject duplicate launch"]
    C -->|Already COMPLETED| F["Reject re-running completed instance"]
    C -->|FAILED or STOPPED| G["May restart if policy permits"]
    D --> H["Execute job"]
    G --> H
~~~

Key exceptions from `JobLauncher.run(...)`:

| Exception | Typical Context | Appropriate Response |
|---|---|---|
| `JobExecutionAlreadyRunningException` | Instance has an active running execution. | Report that work has already started; do not try to spawn a second run. |
| `JobInstanceAlreadyCompleteException` | Instance already completed, or state disallows re-running per repository rules. | Return completed status and decide whether a new processing period is needed. |
| `JobRestartException` | Non-restartable, or execution state cannot be safely restarted. | Investigate and follow recovery procedures. |
| `JobParametersInvalidException` | Parameters fail the Job's validator. | Return a clear validation error. |

The exact exception raised under a race can also depend on timing and database configuration: unique-constraint or transaction-conflict errors may occur at the JDBC layer before the caller receives the expected high-level exception. Do not rely on a pre-launch status read as your sole duplicate guard.

### Behavior by Status

| Prior Execution Status | When a Request with the Same Identifying Parameters Arrives |
|---|---|
| `STARTING`, `STARTED`, or `STOPPING` | Execution is active; repository blocks parallel execution of the same instance. |
| `COMPLETED` | Does not create a new run for an already-completed instance. |
| `FAILED` | Can create a new `JobExecution` to restart, if the job allows it. |
| `STOPPED` | Can restart per configuration once the execution has genuinely stopped. |
| `ABANDONED` or `UNKNOWN` | Evaluate rules and recoverability; must not be treated automatically as new work. |

**Restart is not a concurrent duplicate execution.** Restart is a new execution of the same `JobInstance`, allowed only when the prior status and restart policy permit.

## 4. Defining a Stable Business Key

For a job meaning "settle once per day per store", the business key can be:

~~~text
(jobName, businessDate, storeId)
~~~

`businessDate` must be computed in a consistent business timezone; `storeId` must follow normalization rules (for example, do not mix `acme` and `ACME` if they represent the same store). Each HTTP request's `requestId` is only for tracing and can be marked non-identifying.

~~~java
import java.time.LocalDate;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

public JobParameters forBusinessDay(
        LocalDate businessDate,
        String storeId,
        String requestId) {
    return new JobParametersBuilder()
        .addString("businessDate", businessDate.toString(), true)
        .addString("storeId", storeId, true)
        .addString("requestId", requestId, false)
        .toJobParameters();
}
~~~

Conversely, the following configuration **breaks duplicate protection**:

~~~java
// Almost every call is guaranteed to create a new JobInstance.
new JobParametersBuilder()
    .addString("businessDate", businessDate.toString(), true)
    .addLong("timestamp", System.currentTimeMillis(), true)
    .toJobParameters();
~~~

Because `timestamp` is identifying, two requests processing the same date get different keys. Similarly, `RunIdIncrementer` or `JobOperator.startNextInstance(...)` is designed to create a **new instance**, not to guard against duplicate scheduling of the same business period.

### When Is a New Identifying Parameter Warranted?

There are valid cases where the same date must be reprocessed with corrected data. You can include `inputVersion` or `revision` in the business key:

~~~text
dailySettlementJob(
  businessDate=2026-11-15,
  storeId=ACME,
  inputVersion=v2
)
~~~

Version v2 is an intentionally distinct instance from v1. That works only if business rules clearly define **whether v2 replaces or supplements v1 results**, how outputs are published, and how duplicate side effects are prevented. A random UUID cannot substitute for that business decision.

## 5. Writing a Controlled Launch Service

Spring Batch 5.x example with Java 17+:

~~~java
import java.time.LocalDate;

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
public class SettlementLaunchService {

    private final JobLauncher launcher;
    private final Job settlementJob;

    public SettlementLaunchService(
            JobLauncher launcher,
            @Qualifier("dailySettlementJob") Job settlementJob) {
        this.launcher = launcher;
        this.settlementJob = settlementJob;
    }

    public JobExecution launch(
            LocalDate date,
            String storeId,
            String requestId)
            throws JobExecutionAlreadyRunningException,
                   JobRestartException,
                   JobInstanceAlreadyCompleteException,
                   JobParametersInvalidException {

        JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", date.toString(), true)
            .addString("storeId", storeId, true)
            .addString("requestId", requestId, false)
            .toJobParameters();

        return launcher.run(settlementJob, parameters);
    }
}
~~~

Key properties of this service:

1. Business identity is constructed deterministically without generating random identifying parameters.
2. `JobRepository` is entrusted with coordinating execution creation; the service does not maintain an in-memory `isRunning` flag.
3. `JobExecutionAlreadyRunningException` and `JobInstanceAlreadyCompleteException` are outcomes handled per the application contract, not writer failures.
4. When a previous run is `FAILED` and the job is restartable, calling with the same identifying parameters may **restart** instead of being rejected; this policy must be clearly communicated to users/API consumers.
5. If the launcher is asynchronous, `run(...)` returning a `JobExecution` does not mean processing is finished; keep monitoring execution status.

This code assumes `dailySettlementJob` has standard Spring Batch configuration and the launcher points to a valid shared `JobRepository` in a multi-node environment.

### REST API Responses

| Outcome | Suggested Response |
|---|---|
| Execution accepted | Return `jobExecutionId`, business key, and status (e.g., HTTP `202 Accepted` if running in the background). |
| Execution already running | Report "in progress"; HTTP `409 Conflict` with a link to the active execution is common. |
| Instance already completed | Return "already completed" with prior outcome, such as HTTP `200 OK`; or `409` if the API contract chooses rejection. |
| Invalid parameters | Return input error, typically HTTP `400`. |
| Prior instance failed | Document whether policy allows auto-restart or requires a dedicated recovery action. |
| Database/JobRepository unavailable | Return infrastructure error; retrying callers must preserve the same identifying parameters. |

When an API requires that **the same idempotency key always receive the exact same response**, you may need a separate request-state store mapping request keys to launch outcomes. `JobInstance` protects batch identity; it does not store every HTTP response automatically.

## 6. Never Use "Check-Then-Launch" as Your Duplicate Lock

The following code opens a race window:

~~~java
// Anti-pattern illustration only; never rely on this as sole protection.
if (jobExplorer.findRunningJobExecutions("dailySettlementJob").isEmpty()) {
    launcher.run(settlementJob, parameters);
}
~~~

Two nodes can both read "no execution running" before either calls the launcher:

~~~text
Node A                       Node B
------                       ------
Check: no job running yet
                             Check: no job running yet
Call launcher
                             Call launcher
~~~

This is a *time-of-check/time-of-use* (TOCTOU) bug. `JobExplorer` is great for displaying info and inspecting running executions, but read results can become stale instantaneously.

Similarly, `synchronized` or `AtomicBoolean` only locks within that object/JVM; it does not block other pods. In-RAM flags also vanish on restart and stay out of sync with `JobRepository` metadata.

**Execution creation must be protected at a shared layer capable of atomic operations**, typically a `JobRepository` backed by a shared database, transactions, and proper unique constraints.

## 7. Multi-Node Duplicate Protection

When multiple pods run the same Spring Batch application, control the entire path from scheduler to repository:

~~~mermaid
flowchart LR
    A["Scheduler / API\nNode A"] --> C["JobLauncher A"]
    B["Scheduler / API\nNode B"] --> D["JobLauncher B"]
    C --> E["Shared JDBC JobRepository"]
    D --> E
    E --> F["BATCH_JOB_INSTANCE\nJOB_NAME + JOB_KEY unique"]
    E --> G["BATCH_JOB_EXECUTION\nstatus and history"]
~~~

Essential requirements:

- Nodes must share the **same logical repository** for jobs that share history. Per-pod local repositories cannot see each other.
- The Spring Batch schema must have proper identity constraints and a properly functioning transaction manager.
- JDBC repository `JobExecution` creation needs isolation compatible with concurrent launchers. Do not arbitrarily lower isolation or drop unique constraints to silence errors.
- Every node must derive identifying parameters from the **same business rules**, not differing by node-local timezone/locale or system clock skew.
- Nodes must handle duplicate-launch outcomes consistently, avoiding turning "job already running" errors into infinite retry loops.

In JDBC JobRepository configuration, execution creation runs inside a transaction; its isolation level is configurable and normally kept strict enough to handle contention. Details depend on the version and repository setup (direct Spring Batch or via Spring Boot). The invariant to preserve is atomicity of execution creation.

### A Different JobInstance Can Still Run at the Same Time

The repository protects per `JobInstance` identity; it is not a distributed lock across all jobs sharing a resource.

~~~text
dailySettlementJob(businessDate=2026-11-15)
dailySettlementJob(businessDate=2026-11-16)
~~~

Two dates are two distinct instances. If each date writes to its own partition, running concurrently may be desirable. If both write to the same `settlement.csv` file or rebuild an entire table, they can collide even when JobRepository works perfectly.

When you need a policy of **"only one process writes resource R at a time"**, add an explicit resource ownership mechanism, such as:

- A database claim/lease with a unique constraint on the resource key.
- A distributed lock provided by a reliable coordination system.
- Output partitioning by partition/job key so independent instances never contend.
- Centralized scheduler orchestration when the protection scope aligns with business rules.

PostgreSQL example of a **durable claim** (not yet a full lease):

~~~sql
CREATE TABLE batch_resource_claim (
    resource_key VARCHAR(200) PRIMARY KEY,
    owner_token VARCHAR(100) NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO batch_resource_claim(resource_key, owner_token)
VALUES (:resourceKey, :ownerToken)
ON CONFLICT (resource_key) DO NOTHING;
~~~

The application checks the inserted row count: **1** means the claim was acquired; **0** means another owner holds the resource. This SQL only illustrates atomic acquisition. Production systems must also handle release, crashes, timeouts, heartbeats, and preventing an old owner from continuing after ownership moved to a new owner (*fencing*).

Never hold a database transaction or row lock open across an entire multi-chunk job just to act as a distributed lock: long transactions cause blocking, lock contention, and conflict with per-chunk short transactions.

## 8. Schedulers Must Build the Same Business Key on Every Node

Example of a job running at 01:00 Vietnam time to process the previous day:

~~~java
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.UUID;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
class DailySettlementScheduler {

    private static final ZoneId BUSINESS_ZONE =
        ZoneId.of("Asia/Ho_Chi_Minh");

    private final SettlementLaunchService launchService;

    DailySettlementScheduler(SettlementLaunchService launchService) {
        this.launchService = launchService;
    }

    @Scheduled(cron = "0 0 1 * * *", zone = "Asia/Ho_Chi_Minh")
    void launchPreviousDay() throws Exception {
        LocalDate businessDate =
            LocalDate.now(BUSINESS_ZONE).minusDays(1);

        launchService.launch(
            businessDate,
            "ACME",
            UUID.randomUUID().toString() // non-identifying requestId only
        );
    }
}
~~~

Across two pods, the same business period produces the exact same `businessDate` and `storeId`. `requestId` differs per trace without altering instance identity.

In real applications, the scheduler should explicitly catch duplicate-launch outcomes and record them appropriately in logs/metrics. Do not catch and swallow **all** exceptions: repository connection failures, invalid parameters, or bean-wiring errors must remain visible.

Additional points:

- `@Scheduled` normally triggers on **every instance** containing that bean. It does not automatically become a cluster-wide singleton scheduler.
- Orchestrating via Kubernetes CronJob, Quartz, or an external scheduler can reduce duplicate requests; the repository remains the authoritative guard by job identity.
- In Spring Boot, `spring.batch.job.enabled=false` disables auto-launching jobs on startup when the application wants controlled launching via a scheduler/API. This is a Spring Boot property, not a replacement for JobRepository.
- When multiple timezones or midnight transitions are involved, compute `businessDate` with a fixed rule rather than letting each host infer from local time.

## 9. Re-Launching After Failure: Restart vs. Duplicate Launch

Suppose the first execution commits chunk 1 successfully and fails on the next chunk:

~~~text
JobInstance A: dailySettlementJob(date=2026-11-15, store=ACME)
    |
    +-- JobExecution #101: FAILED
    |     chunk 1: committed
    |     chunk 2: failed
    |
    +-- JobExecution #102: COMPLETED
          restart of the same instance A
~~~

When `JobInstance A` is in a restartable state, creating `JobExecution #102` is an intentional action. Spring Batch can use `StepExecution` state and `ExecutionContext` to resume per the configured restart mechanism.

Key principles:

1. **Never add an identifying `run.id` or timestamp just to bypass "Job already exists".** That creates a new instance, potentially re-reading all input and duplicating already-committed chunks.
2. **Never delete `BATCH_*` tables before restarting** if you want to preserve checkpoints and execution history.
3. **Do not expect the entire job to roll back when one chunk fails.** Already-committed chunks normally remain.
4. **Writers must tolerate replay.** Use unique business keys, idempotent updates, or appropriate deduplication.
5. **Do not restart before the old execution has truly stopped.** If a node crashed leaving status "running", verify reality and follow an approved recovery procedure.

A job marked non-restartable or an execution in an unrecoverable state will be rejected by repository rules. Calling `JobLauncher` repeatedly will not fix that error on its own.

### What If You Need to Reprocess a `COMPLETED` JobInstance?

Business may ask to recalculate an already-settled day because logic or source data changed. Design an **intentional new business run**:

~~~text
dailySettlementJob
businessDate=2026-11-15
storeId=ACME
revision=2
~~~

`revision` can be an identifying parameter when v2 must be cleanly separated from v1. Clearly define whether v2 replaces v1 results, is stored alongside them, or posts compensating entries, and how side effects like emails or messages behave. A random timestamp merely lets the system create a new instance without answering any of those data questions.

## 10. Duplicate Launch Protection Alone Is Not Exactly-Once

Suppose the job accepts only one execution, yet the writer succeeds on an HTTP API call and then the database transaction rolls back. On restart, the writer may send that HTTP call again. `JobRepository` cannot automatically roll back an external HTTP system.

| Scenario | What Does Duplicate Launch Protection Help With? | What Extra Mechanism Is Needed? |
|---|---|---|
| Two requests with same key while job runs | Prevents parallel executions of the same instance with a proper repository. | Clean API response, execution tracing. |
| Duplicate request after `COMPLETED` | Prevents spawning a new run with the same key. | Return already-processed outcome to caller. |
| Job `FAILED` then restarted | Manages the new execution of the same instance. | Checkpoints, idempotent writer. |
| Two instances for different dates write one file | Not treated as an identity collision. | Distinct filenames or resource lock. |
| Writer increments balance after retry | Does not guarantee addition executes only once. | Unique event IDs, transactions, and deduplicated accumulation. |
| Writer calls API and chunk rolls back | Does not roll back HTTP side effect. | Downstream idempotency keys, outbox, or compensation. |
| API times out and caller resends same request | Same identifying params are recognized. | Idempotent HTTP response store if required by API contract. |

Consistency mechanisms include:

**Unique constraints on business keys.** For example, the output table enforces a unique key `(business_date, store_id, transaction_id)` so a replayed item never creates duplicate rows.

**Idempotent writers.** Write the same final state for the same event; avoid unguarded incremental additions if an event can be replayed.

**Transactional outbox.** Commit business data and outbound event records in the same database transaction; a relay can retry sending while consumers deduplicate by event ID.

**Partitioning or resource locking.** Different instances must not write the same file or global table concurrently without coordination rules.

Duplicate launch protection is the **execution coordination layer**. It does not replace chunk transactions, checkpoints, retry logic, or writer correctness.

## 11. Observability, Error Handling, and Operations

A rejected launch is not necessarily an incident. The system should tell operators which job it collided with and what the prior outcome was.

Useful log fields:

~~~text
jobName=dailySettlementJob
businessDate=2026-11-15
storeId=ACME
requestId=req-57
jobInstanceId=...
jobExecutionId=...
launchOutcome=ALREADY_RUNNING
~~~

Log only parameters approved for operational visibility. `JobParameters` are typically persisted in metadata; never place passwords, secret tokens, or sensitive data inside them.

| Situation | Operational Action |
|---|---|
| Another node's scheduler launches same key | Log duplicate/suppressed event; inspect the running execution. |
| API re-invokes an already-completed period | Return completion details or result link per contract. |
| Restart after `FAILED` | Link new execution to old instance, monitor re-executed steps. |
| Repository unreachable | Alert on infrastructure failure; never silently fall back to a temporary repository. |
| Execution stuck in `STARTED` after crash | Verify external node/task state before touching metadata. |

`JobExplorer` supports metadata queries and `JobOperator` supports appropriate control operations. An execution stuck in "running" metadata after a crash may need recovery, but **never arbitrarily edit/delete `BATCH_JOB_EXECUTION` rows** to "unlock" it. Doing so can destroy checkpoints, audit history, or re-run already-committed data.

Stopping a job is not an instant thread-kill mechanism; understand where execution currently sits, which checkpoints are persisted, and whether non-transactional side effects exist.

## 12. Scenarios to Verify

| Scenario | Input | Expectation |
|---|---|---|
| Two concurrent launches with same key | Same `jobName`, date, store | No two executions of the **same JobInstance run concurrently**. |
| Client retries with new request ID | Same identifying params, different `requestId` | Still resolves to the same JobInstance. |
| Different business date | Different `businessDate` | Two valid JobInstances. |
| Different store | Different `storeId` | Two separate JobInstances; outputs isolated if needed. |
| Instance already `COMPLETED` | Re-invoked with same identifying params | No new run created; caller learns it completed. |
| Instance `FAILED` | Re-invoked with same identifying params | Restarts per policy, creating next JobExecution of same instance. |
| Changing identifying timestamp | Each request carries new timestamp | Spawns new instances; reveals key-design flaw if period must be unique. |
| Two pods using separate repositories | Same business key | Risk of duplicate processing; must share one metadata store. |
| Two different-key instances sharing a file | Same `report.csv` | Contention possible even when JobRepository works properly. |
| One chunk committed before crash | Restart after failure | Verify no lost items and writer produces no duplicate business effects. |

### Testing Concurrent Launches Deterministically

Do not call the launcher twice sequentially and claim you tested races. If the first run finishes quickly, the second simply sees `COMPLETED` rather than testing a request arriving while the instance is actively running.

An integration test can:

1. Start a JDBC `JobRepository` on a test database with proper schema and transactions.
2. Use a test step that holds execution in a running state via a controlled latch/barrier.
3. Submit two near-simultaneous launches with the same identifying parameters, across two threads or two processes if testing cross-JVM behavior.
4. Observe one execution allowed to run while the other is rejected or handled per repository rules.
5. Release the latch, let the job finish; query metadata and business tables to verify the invariant that no two executions of the same instance ran in parallel.
6. Repeat with a different non-identifying `requestId`, then with a different `businessDate`, proving the system separates duplicate work from new work.

Avoid forcing tests to depend on exact thread scheduling or a single exception type when database/isolation behavior varies. What must be asserted is the invariant **no duplicate execution of the same instance** and accurate output effects. If you specifically want to assert `JobExecutionAlreadyRunningException`, hold the first execution genuinely running when the second request arrives.

Beyond races, restart tests must preserve original identifying parameters and required metadata, commit one chunk, trigger failure, then recover and confirm output is complete with zero duplicate records.

## 13. Common Mistakes

**Using `run.id` or current timestamp as an identifying parameter for every request.** Every request becomes a separate JobInstance even for the same date. Only use instance-creating parameters when you genuinely want a new processing period or version.

**Only checking `JobExplorer.findRunningJobExecutions(...)` before launching.** Check results go stale immediately; it is not an atomic lock. Repository execution creation must coordinate concurrency.

**Using `synchronized` or JVM flags as a cluster-wide lock.** Those primitives do not coordinate across pods and cannot replace persistent metadata.

**Giving each node its own JobRepository.** Nodes remain blind to what other nodes ran, risking multiple logical instances for the same business work.

**Assuming JobRepository blocks all jobs from sharing resources.** It identifies by job name and identifying parameters; it does not lock output files or summary tables across distinct instances.

**Deleting batch metadata to "restart" a job.** Wiping history destroys checkpoints, causing the next run to start from scratch and duplicate already-committed chunks.

**Assuming no duplicate job launch means writers cannot write duplicates.** Retries, restarts, HTTP side effects, and different concurrent job instances still pose duplication risks.

**Swallowing all launcher exceptions.** "Job already running" can often be handled as normal state, whereas database, transaction, or invalid-parameter errors require separate handling.

## 14. Design Checklist for Duplicate Launch Protection

1. **Define the business unit of work:** a date/store, a file/version, an account/reconciliation period, etc.
2. **Choose stable identifying parameters:** identical work must share the same `jobName` and keys. Use non-identifying parameters for per-request trace data.
3. **Use one JobRepository matching deployment scope:** schema, unique constraints, isolation, and transactions must cover all coordinating launchers.
4. **Return clear launch outcomes:** distinguish running, already completed, valid restart, invalid parameters, and infrastructure errors.
5. **Protect shared resources outside JobInstance:** partition outputs or use a claim/lease when instances with different keys can still collide.
6. **Make writers retry/restart-safe:** business keys, idempotency, transaction/outbox, and clear recovery procedures.
7. **Test races and crashes:** use controlled concurrent tests, checking both metadata and output data.

A rule of thumb worth remembering:

> **Same business work → same JobInstance. New business work → new JobInstance. Retry after failure → new JobExecution of the old JobInstance.**

## Conclusion

Duplicate launch protection in Spring Batch rests first on **`JobInstance` identity** and **`JobRepository`**'s ability to govern `JobExecution` creation when multiple sources request runs. Identifying parameters must remain stable around the business key; accidentally adding a new timestamp, UUID, or `run.id` to every request turns duplicate requests into valid separate instances.

At the system level, pair that mechanism with API responses, scheduler coordination, restart rules, resource locking across distinct instances, and idempotent writers. When each protective layer has a clear scope, normal launches, timeout retries, and crash recovery all behave consistently, observably, and safely for your data.
