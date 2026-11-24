# Practice Project: Building a Failure and Recovery Runbook in Spring Batch

A batch job that runs successfully for days on end can fail on the most critical day: a missing source file, a changed CSV schema, exhausted database connections, a writer failure mid-chunk, a pod dying after committing data, or an external API processing a request without returning a response. When that happens, operations teams need to know **what to check, which evidence is trustworthy, whether retrying/restarting is allowed, and how to verify data after recovery**.

An answer like "check the logs and rerun the job" is not enough. In Spring Batch, one `JobInstance` can have multiple `JobExecution`s; previously committed chunks do not automatically roll back when a later chunk fails; `JobRepository` holds checkpoints needed for restarts; and side effects to files, brokers, or HTTP APIs are not automatically undone by a database transaction. Re-running with the wrong key can create duplicate data even after fixing the original error.

A **runbook** is a scenario-driven operational document providing a repeatable sequence: *detect → triage → contain → preserve evidence → approved recovery action → reconcile output → close incident*. Under **Spring Batch Core Processing → Practice Projects**, this lesson guides building a complete failure and recovery runbook with a sample project, document templates, metadata SQL queries, error classification, drill exercises, and handover criteria.

Examples use **Spring Batch 5.x**, **Java 17+**, **Spring Boot 3.x**, and **PostgreSQL**. Job names, paths, IDs, and commands are illustrative; before using in production, adapt them to your real system's schemas, permissions, change policies, and data contracts.

## 1. Deliverables to Produce After This Project

After completing the practice project, learners have a **runbook usable for real incident handling**, not just API documentation. Deliverables should include:

| Component | Required Content | Reason |
|---|---|---|
| **Job overview** | Trigger source, business key, input/output, dependencies, schedule. | So on-call responders understand the system they are operating. |
| **Failure classification table** | Symptoms, likely causes, allowed actions, when to escalate. | Do not treat every exception the same way. |
| **Investigation queries** | Query `JobInstance`, `JobExecution`, `StepExecution`, and business data. | Gather evidence instead of guessing from a single log line. |
| **Recovery procedures** | Conditions for retry, restart, stop, reprocess, resource recovery, and data remediation. | Reduce the risk of making an incident worse. |
| **Reconciliation procedure** | Verify counts, business keys, total amounts, skips/rejects, and outbox if present. | Confirm data accuracy after the job reports success. |
| **Incident communication template** | Status, impact, decision, owner, evidence. | Enables consistent coordination and auditing. |
| **Drill scenarios** | Reader, writer, mid-chunk crash, repository errors, duplicate launches. | Prove the runbook is actionable. |
| **Security rules** | Never log payloads/credentials; restrict data-manipulation permissions. | Prevent leaks while resolving incidents. |

This document presents a **completed sample runbook for a hypothetical job**; learners can use this structure to adapt into their own project's runbook.

## 2. Sample Project Context

### 2.1. Job to Operate

Assume the application has a `dailyPaymentImportJob` to import a daily payment file:

~~~text
Scheduler / REST API
       |
       v
dailyPaymentImportJob
       |
       +-- preflightSourceStep
        |     Verify file, schema, and source manifest
       |
       +-- importPaymentsStep
       |     CSV reader -> processor -> JDBC writer
        |     CSV reader -> processor -> JDBC writer
       |
       +-- reconcilePaymentsStep
        |     Reconcile count, amount, and event_id set
       |
       +-- publishPaymentsStep
              Publish batch version passing quality gate
~~~

Input is a CSV placed in a versioned, checksummed staging area; output is written to PostgreSQL under `batchKey`. `JobRepository` uses JDBC metadata to manage executions and restarts. Data is synthetic and contains no real customer information.

### 2.2. Operational Information Table

| Attribute | Illustrative Value |
|---|---|
| Job name | `dailyPaymentImportJob` |
| Purpose | Import valid payments for one day and one source. |
| Trigger | Daily scheduler; role-restricted operational API for recovery when needed. |
| Business key | `businessDate + sourceId + sourceVersion`. |
| Example business date | `2026-11-15` in the agreed business timezone. |
| Example source ID | `warehouse-A`. |
| Example source version | `v1`. |
| Batch key | `2026-11-15:warehouse-A:v1`. |
| Identifying `JobParameters` | `businessDate`, `sourceId`, `sourceVersion`. |
| Non-identifying `JobParameters` | `correlationId`, `triggerType` when used solely for observability. |
| Source manifest | Logical source name, version, checksum, expected data row count. |
| Output | `processed_payment` table, unique constraint `(batch_key, event_id)`. |
| Data quality | Filter/reject strictly per contract; publish after reconciliation. |
| Transaction management | JDBC chunk with appropriate transaction manager. |
| Metadata | Spring Batch `BATCH_*` tables. |
| Monitoring | Job/step status, counters, correlation ID, alerts, and structured logs. |

For real projects, missing fields such as job owner, SLA/SLO docs, dashboard endpoints, environments, contact groups, and operational permissions must be filled in before putting the runbook into service.

### 2.3. Small Input Set for Drills

~~~csv
event_id,currency,amount
PAY-001,USD,100.00
PAY-002,USD,50.00
PAY-003,USD,abc
PAY-004,USD,0.00
PAY-005,USD,25.00
PAY-006,USD,25.00
~~~

Assume rules for a **non-mandatory-ledger demo job**:

- `PAY-001`, `PAY-002`, `PAY-005`, and `PAY-006` are written.
- `PAY-003` is read-skipped because amount cannot be parsed; errors must produce a reject report.
- `PAY-004` is filtered because amount equals 0 per an illustrative rule.
- The file has **6 data rows, excluding the header**.
- `readCount=5`, `readSkipCount=1`, `filterCount=1`, `writeCount=4`, and total output amount equals `200.00 USD` if no other errors occur.

**Business note:** This exercise illustrates orchestration and reconciliation mechanisms. For financial jobs requiring zero dropped transactions, a parse error on one record may need to **block publishing the entire batch** rather than allowing skips.

## 3. Runbooks Must Distinguish Technical State from Data State

Spring Batch concepts:

- **`Job`:** workflow definition.
- **`JobInstance`:** logical unit of work identified by job name and identifying `JobParameters`.
- **`JobExecution`:** a single run attempt of an instance; restarts can create new executions.
- **`StepExecution`:** metadata of a step execution, including counters and status.
- **`BatchStatus`:** lifecycle status such as `STARTING`, `STARTED`, `STOPPING`, `STOPPED`, `COMPLETED`, `FAILED`, `ABANDONED`, or `UNKNOWN` depending on context.
- **`ExitStatus`:** execution result used for flow control and operations, which may carry an exit code distinct from lifecycle status.
- **`ExecutionContext`:** persisted state for restarts/checkpoints; never edit manually without authorization.

A runbook rule worth highlighting prominently:

> **`COMPLETED` does not by itself prove output is right; `FAILED` does not by itself prove all output rolled back.**

In chunk processing, earlier committed chunks can persist when a later chunk fails. If the writer calls an external API, side effects there may exist even if the database transaction rolls back. Therefore, recovery decisions must be based on **metadata and committed data**.

### Failure Timing Diagram

~~~mermaid
flowchart TD
    A["Receive trigger and business key"] --> B["JobRepository creates JobExecution"]
    B --> C["Source preflight"]
    C --> D["Read/process/write by chunk"]
    D --> E["Commit per chunk"]
    E --> F["Reconciliation"]
    F --> G["Publish"]
    A -. "Duplicate schedule/API request" .-> H["Duplicate launch"]
    B -. "Repository/credential error" .-> I["Failure before or at execution creation"]
    C -. "Invalid file/schema" .-> J["Source failure"]
    D -. "Reader/processor/writer error" .-> K["Mid-chunk failure"]
    E -. "Timeout/unclear commit outcome" .-> L["Verify target state"]
    F -. "Count/sum/key mismatch" .-> M["Data quality failure"]
    G -. "Broker/API/file error" .-> N["Non-DB publish/output failure"]
~~~

The runbook must tell the on-call engineer **whether the error happened before or after `JobExecution` creation**, **before or after commit**, and **before or after publish**. Those boundaries determine whether re-running is safe.

## 4. Runbook Template: Static Information Section

The top of a runbook needs enough context for someone new on call to begin without guessing:

~~~yaml
runbook:
  id: RB-BATCH-PAYMENTS-001
  title: "dailyPaymentImportJob - Failure & Recovery"
  ownerTeam: "Data Platform (illustrative)"
  jobName: dailyPaymentImportJob
  environment: "Fill in actual environment"
  businessTimezone: "Asia/Ho_Chi_Minh"
  businessKey: ["businessDate", "sourceId", "sourceVersion"]
  metadataRepository: "Metadata database alias"
  businessDatabase: "Output database alias"
  inputManifestLocation: "Logical manifest path"
  statusDashboard: "Internal dashboard URL"
  loggingDashboard: "CorrelationId/jobExecutionId lookup URL"
  onCallTeam: "On-call operations team"
  dataOwner: "Data quality approver"
  escalationContact: "Internal escalation channel"
  lastReviewed: "Runbook review date"
~~~

Fields marked "fill in actual environment" must be replaced with verified details upon runbook handover. Never put passwords, tokens, private keys, or JDBC URLs containing secrets into documentation. If connection details are needed, store only the **system alias/name** and link to an access-controlled configuration source.

### Scope of Responsibilities

| Role | Incident Responsibility |
|---|---|
| **On-call / operator** | Receive alerts, determine scope, gather metadata, run authorized read-only status checks, maintain incident log. |
| **Batch engineer** | Analyze reader/processor/writer, checkpoints, retry/skip, design recovery and restart. |
| **Data owner** | Decide whether missing/bad data may be skipped, fixed, or reprocessed; approve publish when needed. |
| **DB/platform engineer** | Handle database outages, grants, schemas, connection pools, secret rotation, or scheduler infrastructure. |
| **Dedicated security/on-call** | Coordinate if credential exposure, unauthorized access, or sensitive data in logs is suspected. |
| **Incident commander** | Coordinate broad-impact incidents, record decisions and recovery timestamps per organizational process. |

A runbook should separate **observation permissions** (reading logs/metadata), **state-control permissions** (stop/restart/rollout), and **data-modification permissions** (fixing sources, compensation, reprocessing, DB intervention). Never assume everyone with dashboard access may edit production metadata.

## 5. Incident Intake Procedure

### Step 1: Confirm Which Job the Alert Relates To

Collect at minimum:

| Field | Example |
|---|---|
| `incidentId` | `INC-2026-1116-001` |
| `jobName` | `dailyPaymentImportJob` |
| `businessDate` | `2026-11-15` |
| `sourceId` / `sourceVersion` | `warehouse-A` / `v1` |
| `batchKey` | `2026-11-15:warehouse-A:v1` |
| `jobInstanceId` | `410` if available |
| `jobExecutionId` | `8102` if available |
| `stepName` / `stepExecutionId` | `importPaymentsStep` / `9204` |
| `correlationId` | `req-301` or scheduler trigger ID |
| `detectedAt` | Timestamp with timezone |
| `alertSource` | Batch dashboard, metric, scheduler, API, or data quality gate |
| `businessImpact` | Period not yet published, affected downstream systems |

If the error occurred **before creating a `JobExecution`**, there may be no `jobExecutionId` yet. In that case, trace from scheduler/API launch attempts, correlation IDs, and `JobRepository` connection errors; never invent a fake ID to link events.

### Step 2: Assess Impact Severity

An internal classification example:

| Illustrative Level | Symptoms | Handling Rules |
|---|---|---|
| **SEV-1** | Wrong data published, risk of duplicate transactions, secret exposure, or multiple systems impacted. | Halt publish/consumers when authorized and necessary; notify incident commander, data owner, and specialized teams. |
| **SEV-2** | Critical period delayed, job failed, results unpublished, or reconciliation failed. | Investigate per runbook; recovery requires approval per ownership. |
| **SEV-3** | Non-essential source delayed, transient retry already resolved, no data impact yet. | Monitor and record; review improvements post-incident. |

This is an **example**, not a Spring Batch severity standard. Every organization must apply its own SLA/SLO policies, impact tiers, and escalation paths. Even a small technical bug can be severe if data carries legal/financial weight.

### Step 3: Temporarily Contain Spreading Damage When Needed

If wrong output is suspected, what is needed before restarting may be **halting publication of the data version** or holding downstream in a safe state. Actions such as pausing a scheduler, stopping an execution, or disabling a consumer are production-modifying operations: perform them under existing permissions and approvals, recording timestamp and reason.

Never arbitrarily kill a pod or delete data to "unblock the job." An execution remaining `STARTED` after a process crash and an execution legitimately still running can look identical on a dashboard; verify via workload/process data, locks/transactions, and logs.

## 6. Investigation Step 1: Reading State from `JobRepository`

Spring Batch stores metadata in `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, and parameters/context tables. Use `JobExplorer`, role-restricted operational APIs, or read-only query tools. Examples below use default Spring Batch schema table names and PostgreSQL syntax.

### 6.1. Finding Recent `JobExecution`s for the Job

~~~sql
SELECT
    ji.JOB_INSTANCE_ID,
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.CREATE_TIME,
    je.START_TIME,
    je.END_TIME,
    je.LAST_UPDATED
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = :jobName
ORDER BY je.CREATE_TIME DESC, je.JOB_EXECUTION_ID DESC
LIMIT 20;
~~~

`:jobName` is **bind parameter** notation in JDBC/SQL clients supporting named parameters, not placeholder syntax accepted verbatim by every SQL console. When using another client, substitute that client's bind syntax; never concatenate untrusted data directly into a SQL string.

For `dailyPaymentImportJob`, correlate results with `businessDate` and `sourceVersion`. Filtering by job name alone **is insufficient** because multiple `JobInstance`s across different periods may exist.

### 6.2. Checking Identifying Parameters

In the Spring Batch 5.x schema, the parameters table typically has `PARAMETER_NAME`, `PARAMETER_TYPE`, `PARAMETER_VALUE`, and `IDENTIFYING` columns:

~~~sql
SELECT
    JOB_EXECUTION_ID,
    PARAMETER_NAME,
    PARAMETER_VALUE,
    IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE JOB_EXECUTION_ID = :jobExecutionId
  AND PARAMETER_NAME IN (
      'businessDate', 'sourceId', 'sourceVersion', 'correlationId'
  )
ORDER BY PARAMETER_NAME;
~~~

**Security:** Query only parameters confirmed to be safe. `JobParameters` may hold sensitive data due to misconfiguration; never run `SELECT *` and paste results into chats/tickets. In real projects, replace direct queries with an endpoint returning only allowlisted fields.

Items to record in the incident:

- `jobName` and the execution's **identifying parameter set**.
- `JobInstanceId` and other `JobExecutionId`s of the same instance.
- Are any executions in `STARTING`/`STARTED`/`STOPPING`?
- Was the latest execution `FAILED`, `STOPPED`, `COMPLETED`, or a special status?
- Are there two requests with different correlation IDs yet the same business key?

### 6.3. Checking `StepExecution`s

~~~sql
SELECT
    STEP_EXECUTION_ID,
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    EXIT_CODE,
    START_TIME,
    END_TIME,
    READ_COUNT,
    WRITE_COUNT,
    FILTER_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
~~~

The query reveals the failing step and how much work was performed. Do not infer:

- `WRITE_COUNT=100` means exactly 100 new rows committed: the writer may UPSERT, split/merge, or write to an off-transaction system.
- `ROLLBACK_COUNT=1` means all job data rolled back: earlier chunks may remain.
- `COMPLETED` means no data was skipped/filtered: inspect counters.
- `EXIT_CODE` always describes the full root cause: combine logs, exception categories, and target data.

Avoid dumping `EXIT_MESSAGE` or serializing the entire `ExecutionContext` into tickets if they may contain raw exceptions, SQL parameters, payloads, or secrets.

### 6.4. Using `JobExplorer` in Java

If the application exposes an internal operational API, read executions via `JobExplorer`:

~~~java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;

public final class BatchExecutionInspector {

    private final JobExplorer jobExplorer;

    public BatchExecutionInspector(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public void inspect(long jobExecutionId) {
        JobExecution execution = jobExplorer.getJobExecution(jobExecutionId);

        if (execution == null) {
            throw new IllegalArgumentException("JOB_EXECUTION_NOT_FOUND");
        }

        System.out.printf(
            "jobExecutionId=%d jobInstanceId=%d status=%s%n",
            execution.getId(),
            execution.getJobInstance().getInstanceId(),
            execution.getStatus()
        );

        for (StepExecution step : execution.getStepExecutions()) {
            System.out.printf(
                "step=%s status=%s read=%d write=%d skip=%d rollback=%d%n",
                step.getStepName(),
                step.getStatus(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getSkipCount(),
                step.getRollbackCount()
            );
        }
    }
}
~~~

This is a **metadata-reading** snippet, not performing restarts or mutating state. Output uses only execution IDs, statuses, and counters. Real APIs must enforce authentication/authorization; never expose batch metadata broadly to arbitrary HTTP callers.

## 7. Investigation Step 2: Checking Processes, Logs, and Resources

Metadata is a vital information source yet may **not accurately reflect process state when a process crashes abruptly**. A `JobExecution` showing `STARTED` may correspond to a live process, one waiting on a DB lock, one stuck on networking, or one that died without updating status.

For Kubernetes deployments, **read-only status** examples:

~~~bash
# Illustrative command; replace namespace/label per actual system.
kubectl -n payments get pods -l app=payment-import
kubectl -n payments describe pod payment-import-abc123
kubectl -n payments logs deployment/payment-import --since=30m
~~~

The `logs` command can display sensitive data if the app logged improperly; users need appropriate permissions and must **never copy raw logs containing payloads/secrets into broadly shared channels**. Before concluding a node died, check pod history, restart count, termination reason, and scheduler events, not just a single `kubectl get pods`.

Useful signals:

| Signal | Question to Answer |
|---|---|
| `correlationId` and trigger ID | Did this run come from a scheduler, API, message, or manual action? |
| `jobExecutionId` / `stepExecutionId` | Which execution and step does this log belong to? |
| OOMKilled, restart count, container exit code | Was the process killed or restarted unexpectedly? |
| Database connection pool | Are connection-acquisition timeouts or long-held connections occurring? |
| DB locks / deadlocks | Is the writer waiting on locks or transactions? |
| Disk/volume space | Did file readers/writers hit storage errors? |
| Network/DNS/TLS | Can the job actually reach the database and target API? |
| Outbox pending/age | Did the DB commit while events remain unsent? |
| Input manifest/checksum | Was the source file modified while running? |
| Scheduler overlap | Were multiple triggers fired for the same business key or concurrent instances? |

A safe log example:

~~~json
{
  "event": "batch.step.failed",
  "jobName": "dailyPaymentImportJob",
  "jobExecutionId": 8102,
  "stepName": "importPaymentsStep",
  "stepExecutionId": 9204,
  "correlationId": "scheduler-fire-301",
  "errorCode": "DATABASE_TRANSIENT",
  "rollbackCount": 2
}
~~~

`errorCode` is an **application-normalized** value; Spring Batch does not emit this JSON by default. Never put emails, account numbers, raw CSV lines, unchecked exception messages, JDBC URLs with passwords, or full `ExecutionContext`s into logs.

## 8. Investigation Step 3: Classifying Failures Before Acting

Runbooks must classify by **probable cause and replay safety**, not merely by exception class name:

| Failure Group | Common Symptoms | First Action | When Not to Restart Immediately? |
|---|---|---|---|
| **Source missing/not ready** | Preflight cannot find file/manifest, object storage error. | Verify source delivery schedule, version, and read permissions. | While source is mid-upload or checksum is unfinalized. |
| **Whole-file schema/format invalid** | Header missing columns, mass field-mapping errors. | Block publish, compare contract/`sourceVersion`. | Until a verified source version is available. |
| **Some invalid records** | Read/process skips increase, rejects have `errorCode`. | Evaluate reject policy and error rate. | When critical records are skipped or quality gate fails. |
| **Reader infrastructure error** | Network timeout, missing `SELECT` grant, source DB down. | Check connectivity/permissions and source health. | When reader state or snapshot is no longer consistent. |
| **Writer DB deadlock/timeout** | Transaction rollback, transient SQL error. | Check retry policy and DB health. | When output commit outcome is unclear or writer is non-idempotent. |
| **Writer constraint violation** | Unique, foreign-key, not-null violation. | Distinguish valid duplicates from bad data/schema bugs. | Until knowing which items committed and whether they may be skipped. |
| **`JobRepository`/credential error** | Cannot create execution, checkpoint update fails. | Fix metadata DB/secrets/permissions while preserving history. | When metadata and output risk diverging. |
| **Process crash/OOM** | Pod restarts, execution remains `STARTED`. | Verify workload stopped and output committed. | When writers/API calls might still be running. |
| **Duplicate launch** | `JobExecutionAlreadyRunningException` or already complete. | Look up business key and existing execution. | Never generate random identifying parameters to bypass guards. |
| **Outbox/broker/API failure** | Batch DB succeeds yet events pending, HTTP timeout. | Check remote/outbox/idempotency key status. | Until knowing whether off-DB side effects already occurred. |
| **Reconciliation mismatch** | Count/sum/keys differ from source manifest. | Hold staging, investigate missing/extra/mismatch. | Never publish merely because `loadStep COMPLETED`. |
| **Job stopped on request** | `STOPPING` or `STOPPED`. | Confirm who stopped it, why, checkpoints, and results. | Until approval to resume is granted. |

### Distinguishing Transient from Permanent

A transient error like a deadlock may be suitable for bounded retries/backoff. Wrong schemas, expired unrefreshed passwords, missing grants, business validation errors, or processor bugs **do not disappear on repeated retries**.

Never turn all errors into `.retry(Exception.class)` or `.skip(Exception.class)` just to keep jobs green. A step can be `COMPLETED` despite skipping most input if policies are overly broad; the quality gate decides whether output is publishable.

## 9. Decision Rules: Observe, Stop, Retry, Restart, or Reprocess?

### 9.1. Decision Flowchart

~~~mermaid
flowchart TD
    A["Incident exists for a batchKey"] --> B{"Is an execution truly still running?"}
    B -->|Yes| C{"Risk of bad writes / duplicate effects?"}
    C -->|No| D["Observe; check progress, timeouts, and infra"]
    C -->|Yes| E["Escalate, consider approved stop/pause"]
    B -->|No or stopped| F{"Previous execution status?"}
    F -->|COMPLETED| G["Reconcile output; if reprocessing needed,\ndesign a new revision"]
    F -->|FAILED/STOPPED| H["Fix root cause\n+ verify side effects/commits"]
    F -->|Stale STARTED| I["Confirm process died;\napproved metadata recovery procedure"]
    H --> J{"Is restarting same instance safe?"}
    J -->|Yes| K["Controlled restart\nwith same identifying parameters"]
    J -->|No| L["Reconciliation / compensation /\ndedicated recovery plan"]
    K --> M["Run quality gate\nand verify final data"]
    G --> M
    L --> M
~~~

### 9.2. Options and Prerequisites

| Option | When to Use | Mandatory Prerequisites |
|---|---|---|
| **Observe without intervening** | Job is still running properly, retries within limits, no bad-data risk. | Reliable progress signals; do not ignore SLA/quality alerts. |
| **Batch-mechanism stop** | Need safe stop while job is still running and stop is supported. | Approved; understand stop is cooperative, not an immediate kill. |
| **In-step retry** | Transient error and replay-safe operation. | `retryLimit`, backoff, appropriate transactions/idempotency. |
| **Restart `JobInstance`** | Previous execution `FAILED` or `STOPPED` and job is restartable. | Keep identifying parameters and metadata/checkpoints, fix root cause, verify output. |
| **Reprocess new version** | Period `COMPLETED` yet needs re-running due to changed input/logic. | Meaningful `revision`/`sourceVersion`, output versioning, business approval. |
| **Quarantine/fix records** | Independent erroneous records, business allows fixing/rejecting. | Record identified, audited, classified, and reconciled after fix. |
| **Remote compensation/reconciliation** | Off-DB API/broker/file has unclear side effects. | Business/idempotency key, target verification, dedicated recovery procedure. |
| **Manual metadata intervention** | Exceptional cases like stale execution with no supported recovery path. | Only via approved procedure by someone understanding `JobRepository`/checkpoints; backup, audit, process verification. |

**Never treat "changing timestamp, adding a new `run.id`" as a restart.** If the new parameter is identifying, Spring Batch creates a different `JobInstance`, risking re-reading the source and writing duplicate output.

## 10. Safe Restart Procedure for a `JobInstance`

Suppose:

~~~text
Job name: dailyPaymentImportJob
Identifying parameters:
  businessDate=2026-11-15
  sourceId=warehouse-A
  sourceVersion=v1

JobInstance=410
  JobExecution=8102 FAILED
~~~

### Before Restarting

1. **Confirm the old run truly stopped.** Do not rely solely on a stale timestamp in metadata. Check whether external pods/processes/tasks are still active.
2. **Read `JobRepository` state.** Record `JobInstanceId`, `JobExecutionId`, status, `StepExecution`s, relevant checkpoints, and skip/rollback counters.
3. **Fix the root cause.** For instance, restore DB connectivity, fix grants, deploy the right mapper version, or fix approved data.
4. **Lock down the source data.** Does file `v1` still have the same checksum? If the file's content changed, follow a new source-revision workflow rather than assuming old checkpoints remain compatible.
5. **Verify committed output.** Earlier chunks may remain; the writer must have proper business keys/idempotency to tolerate replay.
6. **Verify off-DB side effects.** If the writer called an API, look up results by idempotency key before resending.
7. **Confirm permissions and approvals.** Record the requester, approver, decision rollback conditions, and monitoring plan.

### Executing the Restart

Spring Batch provides `JobOperator` for operational actions such as lookup, stop, restart, and start. Exact calls depend on version/configuration; an internal operations service may call `jobOperator.restart(jobExecutionId)` on restart-eligible executions.

~~~java
// Pseudocode in an authenticated/authorized operational service.
// Never invoke arbitrarily in production without checking preconditions.
long newExecutionId = jobOperator.restart(8102L);
~~~

Invoke only after confirming the prior execution is genuinely restartable, the job does not set `preventRestart`, identity and checkpoints remain valid, and the root cause is resolved. `restart` creates a new `JobExecution` for the **same `JobInstance`**; it does not create new work by changing identifying parameters.

In some systems, recovery is triggered via `JobLauncher.run(job, sameIdentifyingParameters)` when the prior execution is `FAILED`/`STOPPED` and the job allows restarts. If non-identifying parameters change to record a new correlation, understand they **do not change `JobInstance` identity**. Operational policy must pick one consistent path and avoid firing multiple concurrent restarts.

### After Restarting

1. Record `newJobExecutionId` and link it to the old `JobInstanceId`.
2. Monitor status and new `StepExecution`s; previously `COMPLETED` steps may be skipped on restart per config, while the failed step can re-run.
3. Check written item counts, skips, rollbacks, and DB results by business key.
4. Run/read **reconciliation** against the source manifest.
5. Verify the publish gate and downstream/outbox state.
6. Close the incident only when final data criteria pass, not merely when the new `JobExecution` becomes `COMPLETED`.

### Actions Outside a Normal Restart

- Never delete `BATCH_JOB_INSTANCE` or `BATCH_JOB_EXECUTION` rows to "start fresh cleanly."
- Never update `BATCH_JOB_EXECUTION.STATUS` directly to `FAILED` merely because `STARTED` lingered.
- Never delete `ExecutionContext` before understanding checkpoints and reader/writer restarts.
- Never edit input snapshot `v1` in place and claim the restart still processes the same data.
- Never replay an entire file to an external API before proving idempotency.

If metadata is corrupted or stale after a crash, **only authorized personnel** may perform a special recovery procedure after verifying process/DB side effects and securing backups/audits. General documentation must never provide a copy-paste `UPDATE BATCH_*` SQL snippet for every scenario.

## 11. When `JobExecution` Remains `STARTED` Yet the Pod Died

This is a tricky operational situation. Spring Batch stores persistent metadata, yet if the JVM is killed abruptly, the execution may never receive a final status update. `JobRepository` still considers the instance running and rejects duplicate launches.

The runbook must:

1. Inspect the actual pod/process, node, stop time, and termination reason.
2. Check whether any **other worker, partition, or external task** is still writing data.
3. Check open DB transactions, resource locks, connections, and writer activity.
4. Verify which chunks ultimately committed; if using an outbox/API, verify external events/side effects.
5. Back up/record metadata needed for analysis before running any status-repair procedure.
6. Escalate to batch engineer/DB owner to apply a **controlled metadata recovery procedure** compatible with the Spring Batch version and actual execution state.
7. Restart only after confirming no old execution is still running concurrently and the writer can replay safely.

`JobOperator.stop(executionId)` is a **cooperative stop request** when an execution can still process a stop signal; it does not revive a dead JVM or substitute for investigating stale metadata. Nor is a vanished pod proof that an external API missed the last request.

## 12. Stage-by-Stage Failure Runbooks

### 12.1. Preflight Fails Because File Is Not Ready

**Symptoms:** `preflightSourceStep FAILED`, file not found, missing manifest, or checksum differs from finalized value.

**Investigation:** check source ID, date, version, file-delivery rules, read permissions, and upload status. Never read "the current file" if the same path is being overwritten.

**Recovery:** ask upstream for the complete file and finalize checksum/version, then restart or launch per the `JobInstance` contract. If `v1` content changed, consider a **new `sourceVersion`** and corresponding output revision rather than silently swapping data under old checkpoints.

**Closure criteria:** manifest, checksum, and input version match; load succeeds; reconciliation verifies accurate period output.

### 12.2. Reader Encounters Unparseable Data

**Symptoms:** `FlatFileParseException` or standardized parse error, `readSkipCount` rises.

**Investigation:** determine whether one independent line failed or the whole file changed schema. Check header/schema version before allowing large skip counts.

**Recovery:** for reference sources with explicit reject policies, skip within limits, record quarantine by line/source ref, and reconcile. For mandatory data, fail and fix the source or create a new revision. Never enable `.skip(Exception.class)` to turn the job green.

**Closure criteria:** source line counts are accounted for as accepted/filtered/rejected; quality policy is met; committed output matches expectations.

### 12.3. Processor Business Error

**Symptoms:** `processSkipCount` rises or step `FAILED` with validation error.

**Investigation:** distinguish contractually invalid records from programming bugs like `NullPointerException`, wrong mappings, or unimplemented new rules. Verify whether critical records were skipped.

**Recovery:** fix data or code, and choose restart/reprocess per snapshot/version. If rejecting, require error codes and a remediation owner.

**Closure criteria:** no critical record missing; process skip counts and target data are consistent.

### 12.4. Database Writer Fails Mid-Chunk

**Symptoms:** SQL transient/permanent error, `rollbackCount` rises, `importPaymentsStep FAILED`.

**Investigation:** check transaction manager, `DataSource`, unique constraints, `INSERT` grants, deadlocks/lock timeouts, and committed chunks. Never equate "writer ran" with "committed."

**Recovery:** transient errors may allow bounded retries/backoff; schema/grant errors require infrastructure fixes; constraint errors require checking whether duplicates are valid. Restart the same instance after reconciliation. If commit outcome is unclear, inspect the DB by `(batchKey, eventId)`.

**Closure criteria:** no duplicate rows, no missing business keys, accurate amounts/counts, appropriate terminal metadata.

### 12.5. Duplicate Launch from Scheduler/API

**Symptoms:** `JobExecutionAlreadyRunningException` or `JobInstanceAlreadyCompleteException`, two triggers for the same business key.

**Investigation:** compare `jobName` and identifying parameters, check whether triggers generate new identifying `run.id`/timestamps, and inspect the repository shared across nodes.

**Recovery:** if a valid execution already exists, return its ID/status; never create a second instance. If the instance already `COMPLETED` yet needs reprocessing due to a business revision, obtain approval and create a meaningful version.

**Closure criteria:** one unit of work never has two executions of the same instance running concurrently; unique target result per business key.

### 12.6. `JobRepository` Unreachable

**Symptoms:** errors creating/reading `JobExecution`, metadata not updating, metadata DB connection drop, or expired credentials.

**Investigation:** distinguish network, TLS, DB outage, missing `GRANT`, secret rotation, and pool exhaustion. Trace the launch source when no execution ID exists yet.

**Recovery:** restore repository/secrets/grants, verify checkpoints and committed output, and only then decide on restart. Never fall back to a local temporary repository on one pod or reset `BATCH_*` tables.

**Closure criteria:** repository is stable, metadata aligns with executions, no duplicate processing across trigger sources.

### 12.7. HTTP Writer Timeout or Lost Response

**Symptoms:** partner API call times out; unclear whether the request was processed.

**Investigation:** check `eventId`/`idempotencyKey` on the target side, distinguish permanent HTTP 4xx from transient 429/503, and reconcile requests with existing side effects.

**Recovery:** if the endpoint supports idempotency, retry safely with the **same key**; if outcome is unknown, query status or use compensation. Never skip the item and resend with a new ID.

**Closure criteria:** each event produces exactly one final business effect; audited record of processed requests and pending reconciliations.

### 12.8. Outbox Has Backlog Despite Completed Batch

**Symptoms:** `dailyPaymentImportJob COMPLETED` yet outbox `PENDING`/`IN_FLIGHT` grows, event age exceeds threshold.

**Investigation:** verify DB committed business rows and outbox intent, whether dispatcher/CDC is active, whether broker ACKs, whether leases are valid, and which events are `DEAD`.

**Recovery:** fix broker/dispatcher/schema, handle poison events per policy, and let the dispatcher resend with the old event ID. Never delete `PENDING` rows just to shrink backlog.

**Closure criteria:** backlog returns within threshold, events are ACKed and processed by consumers per contract; duplicates handled by idempotent consumers.

### 12.9. Reconciliation Failure

**Symptoms:** `reconcilePaymentsStep FAILED` even though import step `COMPLETED`; output count/sum/keys differ from manifest.

**Investigation:** check source snapshot, skips/filters, duplicate policy, writer UPSERT, committed data, prior executions of the same instance, and external targets.

**Recovery:** hold output in staging, identify missing/extra/mismatched keys, fix source/code/infra, or use an approved reprocess version. Never edit expected counts by copying counts from output.

**Closure criteria:** all contractual reconciliation checks `PASS`; publish only when data meets criteria.

## 13. Data Verification Step: Never Close an Incident on a Green Status Alone

The runbook needs a **reconciliation checklist** applied after every recovery. For the demo job, define the table:

~~~sql
CREATE TABLE processed_payment (
    batch_key VARCHAR(120) NOT NULL,
    event_id VARCHAR(80) NOT NULL,
    currency VARCHAR(10) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (batch_key, event_id)
);
~~~

### 13.1. Counting Actual Output per Period

~~~sql
SELECT
    COUNT(*) AS output_rows,
    COUNT(DISTINCT event_id) AS distinct_ids,
    COALESCE(SUM(amount), 0.00) AS output_amount
FROM processed_payment
WHERE batch_key = :batchKey
  AND currency = 'USD';
~~~

With the demo file:

~~~text
sourceDataLines   = 6
readSkipCount     = 1
filterCount       = 1
expectedOutput    = 4
actualOutput      = 4
expectedAmountUSD = 200.00
actualAmountUSD   = 200.00
~~~

This count check assumes each source row is classified into exactly one category, the two skip/filter types are the only exclusions, the writer is 1:1, and the job finished per policy. For jobs with deduplication, one-to-many, many-to-one, or multiple sources/targets, adjust the grain and formula.

### 13.2. Finding Duplicate IDs

~~~sql
SELECT event_id, COUNT(*) AS occurrences
FROM processed_payment
WHERE batch_key = :batchKey
GROUP BY event_id
HAVING COUNT(*) > 1;
~~~

With the example primary key, the query cannot return duplicate IDs within the same `batch_key`; it remains useful when working with historical/unconstrained tables or illustrating invariants. **Never treat a unique constraint as proof that no IDs are missing.**

### 13.3. Finding Missing/Extra IDs

Suppose an `accepted_payment` table holds the expected ID and amount set **independently derived** from the source snapshot after validation:

~~~sql
-- Accepted yet missing from output.
SELECT a.event_id
FROM accepted_payment a
LEFT JOIN processed_payment p
  ON p.batch_key = a.batch_key
 AND p.event_id = a.event_id
WHERE a.batch_key = :batchKey
  AND p.event_id IS NULL;

-- Output not belonging to the accepted set.
SELECT p.event_id
FROM processed_payment p
LEFT JOIN accepted_payment a
  ON a.batch_key = p.batch_key
 AND a.event_id = p.event_id
WHERE p.batch_key = :batchKey
  AND a.event_id IS NULL;
~~~

Both queries must return **0 rows** when output is a 1:1 mapping of the accepted set. If `accepted_payment` is populated by copying from `processed_payment` after processing, the check is no longer independent and can legitimize missing-data bugs.

### 13.4. Checking Amount Mismatches by ID

~~~sql
SELECT
    a.event_id,
    a.expected_amount,
    p.amount AS actual_amount
FROM accepted_payment a
JOIN processed_payment p
  ON p.batch_key = a.batch_key
 AND p.event_id = a.event_id
WHERE a.batch_key = :batchKey
  AND a.expected_amount <> p.amount;
~~~

Row counts and total amounts can match even when two records are off in opposite directions. Therefore, reconciling ID + amount per record remains valuable. With multi-currency data, always reconcile by currency and agreed rounding rules.

### 13.5. When Off-Transaction Side Effects Exist

For APIs/brokers/files:

- Verify idempotency/event IDs on the receiving system.
- Distinguish outbox `SENT` from the consumer **having applied business processing**.
- If a file is published, verify manifest, checksum, row count, and version.
- If retrying after a timeout, determine the remote outcome before repeating the operation.
- If multiple `JobExecution`s exist for the same instance, check the **final output by business key**, rather than mechanically summing all `writeCount`s.

## 14. Runbook for Skips, Retries, and Rollbacks

A `Step` can be configured as fault-tolerant:

~~~java
@Bean
Step importPaymentsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<PaymentInput> reader,
        ItemProcessor<PaymentInput, PaymentOutput> processor,
        ItemWriter<PaymentOutput> writer) {

    return new StepBuilder("importPaymentsStep", jobRepository)
        .<PaymentInput, PaymentOutput>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(org.springframework.dao.TransientDataAccessException.class)
        .retryLimit(3)
        .skip(org.springframework.batch.item.file.FlatFileParseException.class)
        .skipLimit(2)
        .build();
}
~~~

This is an **illustrative configuration**; the `PaymentInput`, `PaymentOutput` beans, and reader/processor/writer must be defined in the application. Before allowing skipping `FlatFileParseException`, preflight must check **whole-file format/schema**, because parse errors can signal a contract change rather than a single bad record. For jobs requiring all payments to be processed, never allow skipping parse errors.

### Rules Recorded in the Runbook

| Scenario | Allowed to Continue? | How to Verify |
|---|---|---|
| An optional record has invalid format, policy allows rejects | May skip within limit. | Quarantine + count + source record reference. |
| `skipLimit` exceeded | Not per policy. | Step `FAILED`, assess reject scope. |
| Transient DB deadlock | May retry within limits if writer is replay-safe. | DB healthy, rollback and no duplicate final output. |
| Wrong SQL/schema/permissions | Fail fast, fix infrastructure. | Never turn into write skips. |
| JDBC writer fails mid-chunk | Chunk rolls back if sharing transaction. | Query output; never rely solely on write logs. |
| HTTP writer timeout | Remote effect may have occurred. | Check idempotency key before retrying. |
| Process crashes after commit before checkpoint | May replay on restart. | Unique business key, final data, and checkpoints. |

Never use `.skip(Exception.class)` with a huge threshold merely to achieve `COMPLETED`. Every reject must be accounted for, and the **quality gate** must retain the power to block publishing.

## 15. Production-Changing Action Matrix: Explicit Controls Required

The runbook should classify each operation:

| Action Tier | Examples | Policy |
|---|---|---|
| **Read-only, no changes** | View dashboards, `JobExplorer`, `SELECT` metadata/output, read pod events. | Per granted read-only access; protect sensitive data. |
| **Job control** | Request stop, restart execution, pause scheduler. | Requires explicit preconditions, owner/approval, and audit logging. |
| **Configuration change** | Fix grants, rotate secrets, resize pools, deploy code. | Follow organizational change management. |
| **Data modification** | Quarantine, fix source files, backfill, compensation, reprocess. | Data owner approval; snapshots/backups and reconciliation required. |
| **Batch metadata modification** | Repair stale/corrupted state in `BATCH_*` tables. | Exceptional cases only by authorized specialists with dedicated plan; never provide generic update SQL. |

### Example Recovery Approval Ticket

~~~text
Incident: INC-2026-1116-001
Job / Batch: dailyPaymentImportJob
Business key: 2026-11-15:warehouse-A:v1
Existing JobInstance: 410
Failed JobExecution: 8102
Requested action: Restart same JobInstance after DB connectivity restored
Reason: Transient database failure; writer uses unique (batch_key,event_id)
Preconditions:
  - Previous execution confirmed no longer running
  - Database connectivity recovered
  - Source version/checksum unchanged
  - Prior committed output checked
  - No unresolved external side effect
Approved by: <designated owner>
Operator: <authorized operator>
Expected evidence:
  - New JobExecution ID
  - Reconciliation PASS
  - Published version matches source manifest
~~~

Owner/operator placeholders may only be filled with real identities in internal operational workflows; this example is not a granted approval.

## 16. Communication Template During an Incident

To avoid fragmented updates, keep a short update format:

> **Incident:** `dailyPaymentImportJob` for `2026-11-15:warehouse-A:v1` stopped at `importPaymentsStep`, `JobExecution=8102`.
>
> **Status:** `FAILED`; at least one chunk committed, publication unconfirmed.
>
> **Impact:** This period's data has not been published; downstream dashboards may be delayed. No evidence of permanent data loss yet.
>
> **Evidence:** Job/step metadata, error category `DATABASE_TRANSIENT`, and output query by batch key; no sensitive payloads attached.
>
> **Action:** Verifying DB recovery and output idempotency before requesting restart of the same `JobInstance`.
>
> **Closure criteria:** Reconciliation `PASS`, right source version, no duplicate output, publish succeeded.

Updates should use **exact timestamps with timezone**, avoiding "just now" or "yesterday" when shifts span timezones. Never declare "no data loss" without evidence at source and target.

## 17. Sample Incident Log and Decision Timeline

An **incident timeline** separates observed facts from mere hypotheses:

| Illustrative Time | Type | Entry |
|---|---|---|
| 01:00:00 +07:00 | Observation | Scheduler triggered batch key `2026-11-15:warehouse-A:v1`. |
| 01:00:01 +07:00 | Observation | `JobExecution 8102` created successfully. |
| 01:02:10 +07:00 | Observation | `importPaymentsStep` hit DB timeout; `rollbackCount` rose. |
| 01:02:12 +07:00 | Observation | `JobExecution 8102 FAILED`. |
| 01:05:00 +07:00 | Investigation | DB connectivity checked; no credential values recorded in ticket. |
| 01:07:00 +07:00 | Investigation | Reconciled committed `event_id`s by batch key. |
| 01:10:00 +07:00 | Decision | Data owner/batch engineer approved restarting the same `JobInstance`. |
| 01:11:00 +07:00 | Action | `JobExecution 8103` started. |
| 01:15:00 +07:00 | Observation | Import completed; reconciliation `PASS`. |
| 01:16:00 +07:00 | Observation | Publish completed; downstream confirmed new version. |

This is a **simulated timeline for the practice project**, not actual system history. When creating a real runbook, record operators, ticket/change IDs, and evidence links per organizational policy.

## 18. Practice Project: Implementing Controlled Failure Scenarios

So the runbook does not stay merely on paper, drill in an **isolated test environment** with synthetic data and a dedicated PostgreSQL for integration testing. Never use real customer data, production credentials, or unapproved metadata-editing statements.

### 18.1. Environment Setup

Minimum requirements:

1. A Spring Boot application with the sample job including preflight, import, reconciliation, and publish steps.
2. Working JDBC `JobRepository` with the right metadata schema.
3. `processed_payment` table with unique key `(batch_key,event_id)`.
4. The six-row CSV file from Section 2 with a finalized manifest.
5. Logging with `jobExecutionId`, `stepExecutionId`, and `errorCode`; never print full items.
6. A way to run the job with fixed identifying parameters, for example:

~~~java
JobParameters params = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("sourceId", "warehouse-A", true)
    .addString("sourceVersion", "v1", true)
    .addString("correlationId", "exercise-001", false)
    .toJobParameters();
~~~

Non-identifying `correlationId` tracks the launch attempt; never create a different `JobInstance` when the request ID changes. To **re-run the exercise from scratch on a new instance**, use a controlled reset test environment or intentionally pick a **new `sourceVersion`** per scenario, rather than using random timestamps to paper over inconsistencies.

### 18.2. Scenario A — Missing Source File

**Setup:** Point the manifest to a non-existent test file.

**Expected:** `preflightSourceStep FAILED`, writer never runs, output table has no data for that batch key.

**Runbook drill:** verify file, manifest, permissions, and source version; state who must re-deliver the source; perform recovery in tests once the right file arrives.

**Handover evidence:** preflight status, logged error code `SOURCE_NOT_READY`, output query result, and new execution if restarted.

### 18.3. Scenario B — One Malformed CSV Row

**Setup:** Row `PAY-003` has amount `abc`.

**Expected:** Under demo policy, one `readSkipCount`, four output records, and total `200.00 USD`. If the runbook picks a strict payment policy, expect job failure / blocked publishing.

**Drill:** distinguish a single bad row from a whole-file schema mismatch; check quarantine and quality gates instead of only `BatchStatus`.

**Evidence:** read skip count, reject error code, source data line count, output set, and sum.

### 18.4. Scenario C — JDBC Writer Fails Mid-Chunk

**Setup:** Use a test writer intentionally throwing an exception after executing one or more uncommitted `INSERT`s in the chunk:

~~~java
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.jdbc.core.JdbcTemplate;

final class FailingPaymentWriter implements ItemWriter<PaymentOutput> {

    private final JdbcTemplate jdbc;

    FailingPaymentWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void write(Chunk<? extends PaymentOutput> chunk) {
        for (PaymentOutput row : chunk) {
            jdbc.update("""
                INSERT INTO processed_payment(
                    batch_key, event_id, currency, amount)
                VALUES (?, ?, ?, ?)
                """,
                row.batchKey(),
                row.eventId(),
                row.currency(),
                row.amount()
            );

            if ("PAY-005".equals(row.eventId())) {
                throw new IllegalStateException(
                    "DELIBERATE_WRITER_FAILURE"
                );
            }
        }
    }
}
~~~

This is a **writer dedicated to test fault injection**, not production code. `PaymentOutput` is an example model with properties `batchKey`, `eventId`, `currency`, and `amount`.

**Expected:** If `JdbcTemplate` shares the chunk's datasource/transaction manager, uncommitted changes of the chunk roll back when the exception is neither retried nor skipped. Earlier committed chunks may remain.

**Drill:** reconcile the real database rather than counting writer calls. Perform a safe restart after removing fault injection and confirm no duplicate business keys.

### 18.5. Scenario D — Prior Chunk Commits, Later Chunk Fails

**Setup:** With valid data, pick `chunkSize=2`; inject a controlled error in a chunk after the first chunk committed.

**Expected:** Rows from the first chunk remain after `FAILED`; the failing chunk rolls back if sharing the transaction. Restarting the same `JobInstance` processes the rest from checkpoints.

**Drill:** explicitly record "committed" vs. "uncommitted" in the incident, check the new `JobExecution` linked to the old instance. The writer must have a unique key and be replay-safe.

**Evidence:** output queries before and after restart, metadata of both executions, final reconciliation.

### 18.6. Scenario E — Transient DB Connection Error

**Setup:** In tests, use a fake writer or fault-injection configuration throwing a transient exception permitted by the retry policy on one attempt, then succeeding.

**Expected:** Retries occur within limits; the job reaches `COMPLETED` once the error clears; final output appears once per business key.

**Drill:** distinguish transient errors from permanent wrong credentials/schemas. Never let the job retry `Exception.class` infinitely.

**Evidence:** retry/rollback metrics, execution status, duplicate-free output, and accurate total amount.

### 18.7. Scenario F — Two Sources Launching the Same Business Key Simultaneously

**Setup:** Two threads or two application instances call `JobLauncher.run(...)` concurrently for the same `businessDate`, `sourceId`, and `sourceVersion`; use a step with a latch to keep the first execution running.

**Expected:** No two `JobExecution`s of the same `JobInstance` **run concurrently** when the shared repository is properly configured. Competing calls are rejected/resolved by the repository; `JobExecutionAlreadyRunningException` may occur while the first execution is genuinely running.

**Drill:** report the existing execution to the caller; never add a new identifying timestamp to "dodge" the error. Record both launch attempts' correlation IDs in audit logs if needed.

**Evidence:** `JobInstance`/`JobExecution` metadata, launch outcomes, unique output count.

### 18.8. Scenario G — Crash After Commit Yet Before Response

**Setup:** Simulate lost connection/response after a write operation may have committed. For an HTTP writer, use a fake server that accepts the request and then times out the client; for a DB, use fault injection and query actual state.

**Expected:** The runbook never claims "guaranteed rollback" solely from a timeout. Outcome is verified on the target system via `eventId` or idempotency key.

**Drill:** decide retry, restart, or compensation based on remote state; avoid creating duplicate effects.

**Evidence:** request ID, mock server state, final side-effect count, and reconciliation result.

### 18.9. Scenario H — Quality Gate Fails Despite Load `COMPLETED`

**Setup:** Remove one ID from output or alter an ID's amount after load in the test database to simulate a discrepancy.

**Expected:** Reconciliation detects the mismatch, and `publishPaymentsStep` does not run in the success flow.

**Drill:** use anti-joins and sums by business key; open a data quality investigation ticket rather than immediately re-running.

**Evidence:** expected/actual rows, missing/extra IDs, amount mismatch, and publish status.

## 19. Drill Matrix and Runbook Acceptance Criteria

| Code | Incident | Symptoms to Recognize | Expected Recovery | Evidence to Retain |
|---|---|---|---|---|
| A | Missing source | Preflight `FAILED` | Restore file/version, controlled restart | Manifest/checksum, no pre-processing output |
| B | CSV bad record | Read skip or fail per policy | Reject/quarantine or fix source | Skip counts, source count, quality result |
| C | Writer rollback | Step `FAILED`, rollback count | Fix root cause, restart, replay-safe | Output before/after, no duplicates |
| D | Partial chunks committed | Execution `FAILED` | Resume from checkpoint | Earlier chunks remain, complete final output |
| E | Transient DB outage | Retries/rollbacks | Bounded backoff/retries | No duplicates, job completes |
| F | Duplicate launch | Already running/complete | Use existing execution | One `JobInstance` per business key |
| G | Unknown remote outcome | Timeout | Check idempotency/remote before retry | One final side effect |
| H | Reconciliation mismatch | Load done yet reconcile `FAILED` | Block publish, investigate missing/mismatch | Anti-join, sum, and publish gate |

**A runbook meets acceptance criteria** when someone who did not write the job can read the static info, collect the right metadata, classify the cause, determine whether production changes are permitted, make a reasoned recovery decision, and verify output against data. "All step tests are green" is insufficient if the document omits approvers, omits unclear-outcome cases, or recommends deleting metadata too casually.

## 20. Sample Scenario: An Incident Handled End-to-End

### Initial Situation

The scheduler triggers processing for `2026-11-15:warehouse-A:v1`. `dailyPaymentImportJob` creates `JobInstance 410`, `JobExecution 8102`. Preflight succeeds; after importing several chunks, the database returns a connection error and the step fails.

### Analysis Following the Runbook

1. The operator receives alert `JobExecution=8102 FAILED`, collecting `batchKey` and correlation ID.
2. From `BATCH_STEP_EXECUTION`, identifies `importPaymentsStep` failed, with `COMMIT_COUNT > 0` and `ROLLBACK_COUNT > 0`.
3. Infrastructure checks show database connectivity returned to normal. Conclude the source recovered only after proper connection/transaction test evidence.
4. Queries `processed_payment` by `batchKey` to identify committed rows. Partial output already exists, so **do not delete data and re-run from scratch**.
5. Verifies source manifest/version/checksum is unchanged; writer has primary key `(batch_key,event_id)` and a safe replay policy.
6. Batch engineer/data owner confirms no unknown HTTP side effects exist; approves restarting execution `8102`.
7. A new `JobExecution`, e.g., `8103`, is created for the **same `JobInstance 410`**.
8. After the job finishes, reconciliation verifies the accepted ID set, output count 4, and total `200.00 USD` per fixture.
9. Only after the quality gate passes does the publish step allow publishing the batch version.
10. The operator closes the incident with the new execution ID, reconciliation report, timeline, and root cause.

### Lessons from the Scenario

If you merely see `FAILED` and delete `BATCH_*` to recreate the job, the system risks re-reading and emitting duplicate side effects. If you merely see `COMPLETED` after restart without querying data, missing or extra records remain a risk. A proper runbook forces operators to check both **execution lifecycle and final data state**.

## 21. Security in the Runbook

While troubleshooting an incident, operators often enable verbose logs and export data to investigate. This is the easiest time to leak information if the runbook lacks clear rules:

- Never put passwords, API keys, bearer tokens, private keys, or full JDBC URLs with secrets into tickets.
- Never log/dump full `JobParameters`, `ExecutionContext`, `Chunk`, item objects, or CSV lines containing PII.
- Use vetted `jobExecutionId`, `stepExecutionId`, `correlationId`, error codes, and safe source record references.
- If rejected records must be viewed, access the **role-restricted source/quarantine store**; never copy raw payloads into public chats.
- When sharing logs, attach only minimized excerpts or links to the log system with proper permissions.
- `SELECT` queries must still obey data-access permissions; "read-only" does not mean permitted to view every table.
- If credential exposure is suspected, escalate to security incident response and rotate/revoke per policy; never treat this as a normal retryable error.

The runbook must specify **which data may be exported in an incident record** and **who is permitted to perform advanced investigative actions**.

## 22. Maintaining and Updating the Runbook After Incidents

A runbook should not be written once and forgotten. When schemas, `JobParameters`, transaction boundaries, output destinations, or alerts change, old procedures can lead to wrong recoveries.

Times to review:

- Job switches from a JDBC writer to an API/broker or adds an outbox.
- Chunk size, reader checkpoints, retry/skip config, or restartability changes.
- Input schema, file source, source version, or reconciliation rules change.
- Partitioning/multi-node execution is added or the scheduler changes.
- `JobRepository` and business databases move to separate datasources.
- Credential mechanisms, secret rotation, or DB permissions change.
- A new incident arises not yet covered in the decision table.
- A drill shows commands, dashboards, contacts, or approval conditions are outdated.

An update needs a version, review date, reviewer, and behavioral change summary. If stored in Git, review the runbook like code: describe the reason, scope, risk changes, and drill evidence.

### Post-Incident Review Template

~~~text
Incident ID:
Job / batchKey:
Detection source:
Customer/business impact:
Actual root cause:
First observed failure point:
Committed output at failure:
External side effects:
Recovery action and approver:
New JobExecution ID / jobInstance ID:
Final reconciliation result:
Evidence links:
What worked in the runbook:
What was missing or confusing:
Preventive change:
Owner and follow-up date:
~~~

Never use post-incident reviews solely to count retries or assign personal blame. The goal is confirming root causes, reducing recurrence, and making the next recovery **safer, operationally faster, and easier to verify**.

## 23. Compact Runbook Template Copyable for Other Jobs

~~~markdown
# Runbook: <jobName> — Failure and Recovery

## 1. Static Information
- Owner / on-call:
- Environment / dashboard:
- Trigger source:
- Business key and identifying `JobParameters`:
- JobRepository / business datastore aliases:
- Source manifest/snapshot:
- Output destinations:
- SLA and quality gate:

## 2. Incident Intake
- Incident ID / detection time:
- JobInstanceId / JobExecutionId:
- StepExecutionId / failing step:
- Business key / source version:
- Correlation/trigger ID:
- Alert / error category:
- Business impact:

## 3. Read-Only Investigation
1. Query execution and step counters.
2. Cross-check process/pod with metadata.
3. Check source, checksum, and version.
4. Check committed DB output.
5. Check off-DB side effects.

## 4. Classification
- Reader/processor/writer/repository/publish/reconciliation?
- Transient or permanent?
- Is another execution still running?
- Is commit outcome clear?
- Is restarting safe?

## 5. Approved Recovery
- Action:
- Preconditions:
- Approver / operator:
- New execution (if any):
- Data/side effects to verify:

## 6. Reconciliation
- Source snapshot and expected:
- Actual output count/sum/keys:
- Rejected/filter/skip:
- Duplicate/missing/mismatched keys:
- Remote/outbox results:
- Publish result:

## 7. Incident Closure
- Final BatchStatus / ExitStatus:
- Final quality result:
- Evidence links:
- Owner confirmation:
- Follow-up/prevention:
~~~

This is a **template** that must be filled in for the specific system, not automated commands authorized to mutate production. When finalizing, keep dashboard links and sample queries as close to the real setup as possible, and remove any actions not authorized by operations.

## 24. Common Mistakes When Writing Runbooks

**"If the job fails, re-run the same command."** Without checking whether the command adds an identifying timestamp, whether the old job is still running, or what data already exists at the target. Verify first and preserve restart semantics.

**"If `STARTED` lingers too long, set it to `FAILED` via SQL."** Metadata may be stale while the process is still running or off-DB side effects are still in flight. Mutating metadata is an exceptional action, never a default reflex.

**"Job `COMPLETED`, so close the incident."** Skips, filters, UPSERTs dropping records, or undispatched outboxes may exist. Check quality gates and final data.

**"Writer error means all data rolled back."** Earlier committed chunks may still exist. Off-transaction APIs/files/brokers may also retain side effects.

**"API timeout means the request never arrived."** The target may have committed; check the idempotency key or query remote state.

**"Having `writeCount` means no need to query output."** Counters reflect Spring Batch processing, not always committed business rows across all writers.

**"Adding a new `run.id` is a restart."** Changing identifying parameters creates a new `JobInstance`. A true restart is another `JobExecution` of the same `JobInstance` when state permits.

**"The more DB-editing commands in a runbook, the better."** No. Runbooks must prioritize **observation, preserving evidence, and supported operations**, avoiding copy-paste commands that can break checkpoints.

**"Storing just the exception message is enough."** Messages may contain PII/secrets and insufficiently describe data impact. Use error categories, execution IDs, source references, and reconciliation reports.

**"One global skip threshold applies to every job."** Reject budgets are business decisions; a mandatory accounting record cannot be equated with an optional reference row.

**"No need to drill the runbook if it is thoroughly written."** Broken dashboard links, unusable query syntax, or missing checkpoints as described are only discovered by practicing in a safe environment.

## 25. Final Handover Principles

A good Spring Batch runbook must allow an operator to answer in sequence:

1. **Which job, instance, execution, and data period?**
2. **At which step did failure occur, and before/after which commit boundary?**
3. **Are any other processes or off-transaction effects still active?**
4. **Is the cause transient, bad data, faulty logic, or infrastructure failure?**
5. **What has committed and what is missing/unclear?**
6. **Who is authorized to decide stop/restart/reprocess or data fixes?**
7. **Which action preserves the business key, checkpoints, and idempotency?**
8. **After recovery, does output match the source snapshot and quality contract?**
9. **Has downstream received valid data and can the incident be closed?**

If any question cannot be answered, the runbook must explicitly say **stop acting, gather more evidence, or escalate to the right owner**, rather than offering a risky default action.

## Conclusion

**Building a failure and recovery runbook** in Spring Batch turns knowledge of `JobRepository`, chunk transactions, retry/skip, restarts, idempotency, and reconciliation into **an executable, verifiable operational procedure**. A runbook must not stop at "restart job"; it must identify the business work, commit boundaries, already-written data, off-database side effects, approval authority, and publication criteria.

Through the `dailyPaymentImportJob` project, learners can drill scenarios ranging from missing files, parse errors, writer rollbacks, transient DB failures, and duplicate launches to output mismatches and API timeouts. When every scenario has **investigative evidence, conditional recovery actions, and final output verification**, the runbook becomes a genuine tool for reducing operational risk—especially when fast recovery is needed without losing or duplicating business data.
