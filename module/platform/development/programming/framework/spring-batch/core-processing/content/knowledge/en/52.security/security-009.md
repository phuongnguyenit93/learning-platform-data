# Auditing Operator Actions in Spring Batch

## 1. What is auditing operator actions?

In Spring Batch operations, an **operator action** is an administrative action actively requested by an operator, internal tool, or orchestration system. Examples include manually running a job for a backfill, requesting to stop a running job, restarting a failed run, or abandoning an execution that must not continue. These actions directly affect data, processing schedules, `JobRepository` state, and restart correctness.

**Auditing operator actions** means systematically recording these actions so you can answer:

- **Who** issued the request? Which authenticated user, service account, or automation?
- **What** was requested? `START`, `STOP`, `RESTART`, `ABANDON`, or another recovery action?
- **What target**? Which job name, `JobInstance`, `JobExecution`, business period, or specific input?
- **When** was the request submitted, accepted, or denied?
- **Why** did the operator perform it? Is there an incident/change ticket or controlled note?
- **What was the request outcome**? Denied for missing permission, validation failure, or command accepted?
- **What actually happened to the batch** afterward? Did the job finish `COMPLETED`, `FAILED`, `STOPPED`, or is it still running?

A log line like `INFO Restarting job` does not answer these questions. Auditing must leave a trail with identity, request identifier, decision state, and correlation back to Spring Batch metadata.

```text
Operator / Scheduler / Automation
          |
          v
  Authentication + Authorization
          |
          +----> DENIED  ------> Audit: denied attempt
          |
          v
     Command API / Service
          |
          +----> Audit: REQUESTED (durable)
          |
          v
       JobOperator / JobLauncher
          |
          +----> Audit: ACCEPTED / FAILED
          |
          v
       JobRepository
          |
          v
      JobExecution / StepExecution
          |
          +----> Job/Step lifecycle events & metrics
```

**Clarify from the start:** auditing that a `RESTART` command was accepted does not mean the job completed. `JobOperator` may accept the request and create a new execution, while actual execution fails later. Record **control-operation outcomes** separately from **batch execution outcomes**.

## 2. Object model and audit scope

### 2.1. Relevant operational APIs

For example, in **Spring Batch 5.2.x**, `JobOperator` provides control operations:

| Action | Typical 5.x API | Meaning | What audit must distinguish |
|---|---|---|---|
| Run job | `JobOperator.start(jobName, parameters)` or `JobLauncher.run(job, parameters)` | Request creating/launching an execution by job name and `JobParameters` | Command received, which instance/execution was created, subsequent outcome. |
| Run next instance | `JobOperator.startNextInstance(jobName)` | Uses `JobParametersIncrementer` to create the next logical run | Which parameters the incrementer generated; whether a new instance was intentional. |
| Request stop | `JobOperator.stop(executionId)` | Sends a stop request to a running execution | **Request accepted** differs from already `STOPPED`. |
| Restart | `JobOperator.restart(executionId)` | Requests resuming an instance via a new execution when state permits | Old execution ID, new execution ID, outcome. |
| Abandon | `JobOperator.abandon(executionId)` | Marks an execution abandoned per API rules | High-impact operation; usually requires elevated privilege and explicit reason. |

In Spring Batch 6.x, several operator methods/APIs and related packages changed; the 6.x line also adds `JobOperator.recover(...)` for executions stuck after an abnormal shutdown. When applying this, consult the **API docs matching your version**; never copy 5.x admin code into a 6.x project without verifying.

Other actions also carry audit significance even outside `JobOperator`: changing schedules, changing replica counts, toggling `@Scheduled` configs, modifying default parameters, adjusting operator permissions, running data backfills, or running an admin script to patch batch state. These require trails in **the system performing the change**, not only in the job control API.

### 2.2. JobInstance and JobExecution in audits

In Spring Batch:

```text
JobInstance = job name + identifying JobParameters

JobInstance 420 (dailyOrdersJob / businessDate=2026-11-15)
  |
  +-- JobExecution 1001  -> FAILED
  |
  +-- JobExecution 1015  -> STARTED / COMPLETED (restart)
```

If an operator restarts execution `1001`, the audit should retain both `targetExecutionId=1001` and `createdExecutionId=1015` when the API returns the new ID. Recording only the job name makes it hard to distinguish multiple runs for the same day; recording only the new execution ID hides which failed attempt the operator asked to restart.

`JobParameters` identify a logical run, **yet you must never assume all parameters are safe to place in audits**. Parameters can hold input paths, tenants, customer keys, URLs with tokens, or even secrets if the application is poorly designed. Audits should store an allowlist of approved business keys or a securely computed fingerprint.

## 3. How audits, application logs, and JobRepository differ

| Source | Answers the question | Strengths | Limitations |
|---|---|---|---|
| **Operator audit trail** | Who requested, why, with what permissions and decision? | Operational/compliance evidence, traceable actions | Requires explicit design; not a complete built-in feature of `JobOperator`. |
| Application logs | What events/errors happened in code? | Good for debugging and correlation | Can be rotated/dropped, noisy/duplicated, lacks audit structure or retention guarantees. |
| JDBC `JobRepository` | Which jobs/steps ran with what statuses and checkpoints? | Framework-managed data, supports restart | Does not store full operator identity, reason, permissions, or denial decisions. |
| Security access logs | Which HTTP requests arrived, with what response status? | Useful for API tracing and denials | Does not necessarily know which `JobExecution` was actually created. |
| Metrics / tracing | Latency, error rate, inter-service paths? | Good for monitoring and alerting | Does not replace per-action detailed audit logs. |

For example, an operator clicks `Restart` and receives HTTP `202 Accepted`. The audit records `RESTART_REQUEST_ACCEPTED` with the new ID; minutes later the batch fails because the source data no longer exists. The final `JobExecution` row is `FAILED`. Both facts are true: **the command was accepted**, yet **the job did not complete successfully**.

Never write `COMPLETED` into the audit event right when `JobOperator.restart(...)` returns. With a synchronous launcher, the call may wait until the job finishes; with an asynchronous launcher, the call returns very early. Design audits with distinct phase names so they do not depend on how the launcher is configured.

## 4. Which fields should each audit event contain?

A good audit record is an **immutable event** with its own ID. One operation can produce multiple events such as `REQUESTED`, `ACCEPTED`, `DENIED`, `FAILED`, or `RECONCILED`, all sharing `requestId` to trace as a chain.

| Field | Example | Meaning |
|---|---|---|
| `auditEventId` | UUID | Unique identifier per event. |
| `requestId`/`operationId` | `req-c4f9...` | Groups all events of one operation request. |
| `occurredAt` | `2026-11-16T03:00:00Z` | Event timestamp in UTC. |
| `actorId` | `operator-73` | Stable identifier from authenticated identity. |
| `actorType` | `HUMAN`/`SERVICE` | Distinguishes human users from service accounts. |
| `initiatedBy` | `scheduler-A` | Initiating agent when requests traverse multiple layers, if verified. |
| `action` | `RESTART` | Type of audited action. |
| `phase` | `REQUESTED`, `ACCEPTED`, `DENIED`, `FAILED` | Control request outcome/phase, not `BatchStatus`. |
| `jobName` | `dailyOrdersJob` | Target job. |
| `targetExecutionId` | `1001` | Existing execution targeted for stop/restart/abandon. |
| `createdExecutionId` | `1015` | New execution created when launch/restart succeeds. |
| `jobInstanceId` | `420` | Groups executions of the same logical instance when known. |
| `parameterFingerprint` | HMAC digest | Identifies parameter set without storing raw secrets. |
| `reason`/`ticketRef` | `INC-4821` | Explains the justification for the action. |
| `authorizationDecision` | `ALLOW`/`DENY` | Separates authorization check outcome from command execution outcome. |
| `resultCode` | `ALREADY_COMPLETED` | Standardized result code; avoid relying on raw exception messages. |
| `source` | `ADMIN_API`, `SCHEDULER`, `CLI` | Origin of the command. |
| `traceId` | W3C trace ID | Links to logs/tracing when available. |

`actorId`, `requestId`, `action`, `phase`, timestamp, and target should form the minimum baseline. `reason` may be mandatory for `ABANDON`, recovery, or post-incident restarts. Never require operators to enter tokens/passwords or personal info just to fill in a reason.

### 4.1. Do not conflate `requestId` and `JobExecutionId`

A request can be denied **before Spring Batch creates an execution**. In that case you still have a `requestId`, with no `createdExecutionId`. For stop, the request targets an existing execution without creating a new ID. With approval workflows, multiple events can occur on one request before sending the command to `JobOperator`.

`requestId` also helps guard against duplicate actions from UI timeouts, double clicks, or API client retries. However, **logging `requestId` alone does not create idempotency**; the system must persist, check, and enforce a dedicated duplicate-request policy.

## 5. Designing an append-only audit table

Example PostgreSQL DDL for an event table `batch_operator_audit_event`. This table is **application-owned**, separate from Spring Batch's `BATCH_*` metadata tables:

```sql
CREATE TABLE batch_operator_audit_event (
    event_id UUID PRIMARY KEY,
    request_id VARCHAR(80) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    actor_id VARCHAR(160) NOT NULL,
    actor_type VARCHAR(24) NOT NULL,
    action VARCHAR(32) NOT NULL,
    phase VARCHAR(32) NOT NULL,
    source VARCHAR(48) NOT NULL,
    job_name VARCHAR(160),
    target_execution_id BIGINT,
    created_execution_id BIGINT,
    job_instance_id BIGINT,
    parameter_fingerprint VARCHAR(128),
    reason VARCHAR(500),
    ticket_ref VARCHAR(100),
    result_code VARCHAR(100),
    trace_id VARCHAR(80),
    details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ck_operator_audit_action CHECK (
        action IN ('START', 'STOP', 'RESTART', 'ABANDON', 'RECOVER')
    ),
    CONSTRAINT ck_operator_audit_phase CHECK (
        phase IN ('REQUESTED', 'ACCEPTED', 'DENIED', 'FAILED', 'RECONCILED')
    )
);

CREATE INDEX idx_operator_audit_request
    ON batch_operator_audit_event (request_id, occurred_at);

CREATE INDEX idx_operator_audit_execution
    ON batch_operator_audit_event (target_execution_id, occurred_at);

CREATE INDEX idx_operator_audit_actor_time
    ON batch_operator_audit_event (actor_id, occurred_at);
```

A successful restart request can emit two rows:

```text
event_id=A1 request_id=R1 action=RESTART phase=REQUESTED
  actor_id=operator-73 target_execution_id=1001

event_id=A2 request_id=R1 action=RESTART phase=ACCEPTED
  actor_id=operator-73 target_execution_id=1001 created_execution_id=1015
```

Do not update row `A1` to `ACCEPTED`: retain every chronological step so incomplete requests are visible if a process crashes. If a `batch_operator_command` table is needed to track current workflow state, that table may be updated, while **historical audit events** should remain append-only.

**Immutability must be enforced by permissions and storage mechanisms**, not merely code conventions. For example, the runtime DB account has only `INSERT`/`SELECT` on the audit table without `UPDATE`/`DELETE`; admin access, retention, backups, and shipping records to immutable storage must be governed separately.

### 5.1. Is a foreign key to `BATCH_JOB_EXECUTION` needed?

Not mandatory. A `DENIED` event might reference a nonexistent ID, and an audit record may need longer retention than batch metadata purged under retention rules. Adding a direct foreign key could block metadata cleanup or cascade-delete audit trails unexpectedly. Typically store the ID for correlation only and manage retention independently per policy.

### 5.2. Schemas and databases used for auditing

For small systems, the audit table and `BATCH_*` can share one database with clear transaction boundaries. For high tamper-resistance requirements, store audits in a separate database, append-only event store, or dedicated audit service with isolated credentials. Separating databases lowers the risk of accidental deletion during batch cleanup, while increasing operational, availability, and cross-system consistency demands.

## 6. Where to record audits in the operator action flow

A secure REST/CLI flow must identify every point where a request can be rejected:

```text
1. API receives request, assigns requestId
2. Authenticate actor (or service identity)
3. Check action permission + job/tenant scope
   - DENIED: write security denial audit
4. Validate reason, target ID, input parameters
5. Persist REQUESTED event durably
6. Call JobOperator or JobLauncher
7a. Command accepted -> ACCEPTED event + execution ID if any
7b. Command failed -> FAILED event + error code
8. Track job lifecycle separately to terminal status
```

**Writing audits only after authorization inside the service misses requests blocked at the security layer.** With `@PreAuthorize` or Spring Security filters, calls are rejected before the method body executes. To audit denials, observe authorization events at the corresponding security layer (e.g., access-denied handler, authorization event listener, or interceptor) and record only safely retrievable metadata.

Validation failures that prevent calling `JobOperator` should still emit a `FAILED`/`REJECTED` event per your model. In the sample DDL above, input errors can normalize to `phase=FAILED`, `result_code=INVALID_REQUEST`, while permission denials use `phase=DENIED`. Avoid dumping everything into `FAILED` without a classifying `resultCode`.

### 6.1. A REST API example

```http
POST /ops/batch/executions/1001/restart
Authorization: Bearer <token>
Idempotency-Key: req-9e35...
Content-Type: application/json

{
  "reason": "Restart after verified upstream outage",
  "ticketRef": "INC-4821"
}
```

Illustrative response when the command is accepted:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "operationId": "req-9e35...",
  "action": "RESTART",
  "targetExecutionId": 1001,
  "createdExecutionId": 1015,
  "commandStatus": "ACCEPTED"
}
```

`ACCEPTED` here **does not mean batch execution 1015 has `COMPLETED`**. The UI should display command status and job status separately, with a progress/metadata tracking view. `Idempotency-Key` is an application-enforced API convention, not a header automatically handled by Spring Batch. Never write real access tokens into audit logs.

## 7. Identifying operators and enforcing permissions

### 7.1. Extracting the actor from the authenticated identity

With Spring Security, read `Authentication` from `SecurityContextHolder`, or inject `Principal`/`@AuthenticationPrincipal` in controllers. `actorId` must come from the **authenticated principal**. Never trust a client-supplied field such as:

```json
{"operatorId":"admin", "action":"ABANDON", "executionId":1001}
```

If clients can supply `operatorId`, any caller can spoof who performed the action. Instead, use the identity provider's immutable subject/user ID; display names can change and should not be the sole audit key.

For machine-to-machine calls, record the **service identity** from token/mTLS/workload identity and, if delegated on behalf of a user, add a verified `initiatedBy` field. Never turn an arbitrary `X-User` header into a trusted identity unless the gateway enforces cryptographic signatures/origin and identity-propagation rules.

### 7.2. Per-action authorization

Never grant all job-control privileges under one overly broad role when operations carry different risks:

| Action | Suggested authority | Notes |
|---|---|---|
| View status/list executions | `BATCH_READ` | Read metadata; may require scoping by job/tenant. |
| Start job with valid parameters | `BATCH_START` | Validate job allowlist and input parameters. |
| Stop running job | `BATCH_STOP` | Stop is a cooperative request, not an OS kill. |
| Restart failed execution | `BATCH_RESTART` | Verify status, checkpoint, and side effects. |
| Abandon execution | `BATCH_ABANDON` | Sensitive privilege; require reason/ticket and possibly approval. |
| Recover stuck execution (6.x) | `BATCH_RECOVER` | Only after verifying the old process is no longer running. |

These authority names are **application conventions**, not built-in Spring Batch authorities. You also need **resource scoping**: an operator cleared to restart `dailyOrdersJob` is not necessarily cleared for payroll, payments, or another tenant's data. Combine RBAC with ABAC/policies on job name, tenant, environment, and action sensitivity.

Example method security config in Spring Boot 3.x:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class OperatorSecurityConfiguration {
}
```

In the service:

```java
@PreAuthorize("hasAuthority('BATCH_RESTART')")
public long restart(long executionId, String reason, String requestId)
        throws Exception {
    // Validate authorization scope, write audit, call JobOperator.
}
```

`@EnableMethodSecurity` must be active and the method must be invoked **through the Spring proxy** for `@PreAuthorize` to apply. If a test instantiates the class with `new` and calls the method directly, the annotation will not enforce permissions. For HTTP APIs using session/cookie authentication, maintain appropriate CSRF protection; auditing never replaces access control.

### 7.3. Denied requests must also be audited

Suppose a user without `BATCH_ABANDON` calls the abandon endpoint. Record at least `requestId`, valid actor if known, action, target ID, timestamp, `DENIED`, and reason code `MISSING_AUTHORITY`. For unauthenticated requests, use an identifier such as `ANONYMOUS` or normalized connection attributes, and never log raw access tokens/credentials.

Avoid storing raw exception messages, full URLs with query parameters, or request bodies in audit records by default. URLs may contain secret keys, sensitive file paths, or customer data. Select and normalize fields before persisting.

## 8. Example audit service implementation for `RESTART`

The example below uses **Spring Boot 3.x, Spring Batch 5.x, and Spring Security 6.x** with ID-based `JobOperator` APIs. This business code focuses on auditing, assuming the Spring context configures `JobOperator`, security, and a durable `OperatorAuditWriter`.

Define the audit writer interface:

```java
public interface OperatorAuditWriter {

    void append(
            String requestId,
            String actorId,
            String action,
            String phase,
            Long targetExecutionId,
            Long createdExecutionId,
            String reason,
            String resultCode);
}
```

Execution service:

```java
import org.springframework.batch.core.launch.support.SimpleJobOperator;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class BatchOperatorService {

    private final JobOperator jobOperator;
    private final OperatorAuditWriter audit;

    public BatchOperatorService(JobOperator jobOperator,
                                OperatorAuditWriter audit) {
        this.jobOperator = jobOperator;
        this.audit = audit;
    }

    @PreAuthorize("hasAuthority('BATCH_RESTART')")
    public long restart(long executionId, String reason, String requestId)
            throws Exception {

        Authentication authentication = SecurityContextHolder
                .getContext().getAuthentication();
        String actorId = authentication.getName();

        if (reason == null || reason.isBlank()) {
            throw new IllegalArgumentException("reason is required");
        }

        // If recording the initial event fails, do not execute privileged command.
        audit.append(requestId, actorId, "RESTART", "REQUESTED",
                executionId, null, reason, null);

        try {
            long newExecutionId = jobOperator.restart(executionId);
            audit.append(requestId, actorId, "RESTART", "ACCEPTED",
                    executionId, newExecutionId, reason, null);
            return newExecutionId;
        } catch (Exception ex) {
            audit.append(requestId, actorId, "RESTART", "FAILED",
                    executionId, null, reason,
                    ex.getClass().getSimpleName());
            throw ex;
        }
    }
}
```

`SimpleJobOperator` does not need to be imported if code depends only on the `JobOperator` interface; that implementation import can be omitted in real code. Verify exact methods/exceptions against your Spring Batch dependency. The demo assumes the request is authenticated and already passed job/tenant scope checks; in production, never rely on a coarse authority alone to allow restarting any execution.

**Key details in this pattern:**

1. `REQUESTED` is recorded **before** invoking the mutating API. If audit storage is unavailable, restart is blocked under this example's fail-closed policy.
2. `ACCEPTED` includes the new execution ID for correlation with `JobRepository`.
3. If `JobOperator.restart(...)` throws, `FAILED` is saved with a normalized error type. Never dump stack traces, full exception messages, or credentials into the audit table.
4. `@PreAuthorize` executes **before the method body**, so denied calls must be audited at the security boundary, not in this `catch` block.
5. Auditing is not automatically atomic with `JobOperator`: the process could crash after restart is accepted but before `ACCEPTED` is written. See the reconciliation pattern below.
6. `authentication.getName()` is safe only when configured as a stable identity provider ID; if it returns a mutable display name, map it to the immutable subject ID.

### 8.1. Writing durable events in a separate transaction

An `OperatorAuditWriter` can use `JdbcTemplate` or JPA to insert into the append-only table. In Spring-managed transactions, place writes in a **separate Spring bean** with `Propagation.REQUIRES_NEW` so audit commits independently of business step transactions.

```java
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JdbcOperatorAuditWriter implements OperatorAuditWriter {

    private final JdbcTemplate jdbc;
    private final Clock clock;

    public JdbcOperatorAuditWriter(JdbcTemplate jdbc, Clock clock) {
        this.jdbc = jdbc;
        this.clock = clock;
    }

    @Override
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void append(String requestId, String actorId,
                       String action, String phase,
                       Long targetExecutionId, Long createdExecutionId,
                       String reason, String resultCode) {

        jdbc.update("""
                INSERT INTO batch_operator_audit_event (
                    event_id, request_id, occurred_at,
                    actor_id, actor_type, action, phase, source,
                    target_execution_id, created_execution_id,
                    reason, result_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                UUID.randomUUID(), requestId,
                java.sql.Timestamp.from(Instant.now(clock)),
                actorId, "HUMAN", action, phase, "ADMIN_API",
                targetExecutionId, createdExecutionId,
                reason, resultCode);
    }
}
```

In applications with multiple transaction managers, specify `@Transactional(transactionManager = "auditTransactionManager", propagation = Propagation.REQUIRES_NEW)` with the matching datasource. On PostgreSQL, verify proper JDBC mappings for `TIMESTAMPTZ` and `UUID` against the actual driver. A `Clock` bean (such as `Clock.systemUTC()`) must also be registered.

The example hardcodes actor type `HUMAN` and source `ADMIN_API` for simplicity; real systems must detect service accounts/schedulers/CLIs and record the true source. This snippet omits `jobName`, `jobInstanceId`, fingerprint, trace ID, and ticket columns; in full implementations, populate all schema fields from trusted data.

`REQUIRES_NEW` starts a new transaction only when invoked through the Spring proxy. Self-invoking `this.append(...)` inside the same class bypasses the proxy. A separate transaction prevents business rollbacks from erasing audits, **yet it does not make two databases or `JobOperator` + audit a single atomic transaction**.

### 8.2. Why not write operator audits inside a chunk transaction?

Suppose an operator restarts a job and a chunk later fails and rolls back. If the audit was written inside the chunk transaction, that audit row could roll back too, erasing evidence that a restart was requested. Audits belong at the **job control boundary** with an independent transaction/lifecycle, regardless of whether an item writer commits or fails.

For high-risk commands, an unreachable audit store may warrant **rejecting the operation** rather than proceeding and hoping console logs survive. That is a design policy to align with operations and availability requirements.

## 9. Auditing when an operation fails midway

There is no guarantee that controller operations, the audit database, and `JobRepository` always commit together. For example:

```text
T1: REQUESTED written successfully
T2: Call JobOperator.restart(1001)
T3: JobRepository creates JobExecution 1015
T4: API process crashes before writing ACCEPTED

Audit shows REQUESTED, no ACCEPTED.
Batch metadata may already contain JobExecution 1015.
```

If a request shows only `REQUESTED` with no outcome, **do not blindly re-invoke restart**: the action may already have happened. Query `JobRepository`, reconcile timestamps, job instance, parameters, and prior commands, and append a `RECONCILED` event recording the investigation finding. The final audit event can record `resultCode=EXECUTION_FOUND` with the discovered execution ID.

### 9.1. Durable command-intake pattern for strict requirements

For systems needing stronger auditing and orchestration, separate **recording the command** from **executing the command**:

```text
API:
  - Authenticate and authorize
  - Insert command (unique requestId, actor, action, target, reason)
  - Insert REQUESTED audit in the same transaction
  - Return operationId

Orchestration worker:
  - Claim committed command
  - Check whether request was already executed
  - Call JobOperator per policy with proper locks/guards
  - Record ACCEPTED / FAILED
  - Reconcile in-flight commands after crashes
```

A `UNIQUE requestId` on the command table catches duplicate submissions, while the audit event table allows multiple events per `requestId`. Command execution still requires **action-level idempotency and business locks**, since the worker can crash immediately after calling `JobOperator`. Neither a queue nor an outbox table promises exactly-once on its own.

### 9.2. Do not misrecord the job's final outcome

A monitoring process may append a `JOB_EXECUTION_COMPLETED` event or link to `JobExecution` once the job reaches a terminal state. Keep lifecycle events separate from operator control audits, or use distinct `eventType`/`category` values; never mutate `ACCEPTED` to `COMPLETED` as if the original command finished only when the job did.

With an asynchronous launch API, `JobExecution` may be `STARTING`/`STARTED` when the HTTP response returns. `JobOperator.stop(...)` only sends a stop signal; it can return before `BatchStatus` reaches `STOPPED`. Monitoring must observe actual state with timeouts and alerts when an execution fails to finish as expected.

## 10. Specific audit needs for high-risk actions

### 10.1. Manual START

For manual runs, record job name, actor, reason, business key, and **filtered parameters** or fingerprint. Picking the wrong `businessDate` can process the wrong day's data, so validation belongs at the audited operation boundary with decision logs.

```text
REQUESTED action=START job=dailyOrdersJob businessDate=2026-11-15
ACCEPTED  action=START createdExecutionId=1015
```

If the system normally runs on a schedule, distinguish `source=SCHEDULER` from `source=ADMIN_API`. Never spoof a human user ID when the scheduler issues the run. For manual backfills routed through a scheduler service, record both the service identity and the verified initiating user.

### 10.2. STOP

`stop` is normally a **cooperative stop request**, not an OS process kill. Audits record `STOP_REQUEST_ACCEPTED` and then track until `BatchStatus.STOPPED`, `FAILED`, or another outcome. If an operator requests stop while a tasklet is blocked, completion may be delayed. Recording both request time and execution end time helps measure stop latency.

### 10.3. RESTART

Restarts must log the target old execution, new execution ID when created, prior status, reason, identifying business keys, and checkpoint/reconciliation status if applicable. Never blindly add an identifying `run.id` just to bypass `JobInstanceAlreadyCompleteException`: doing so typically creates a new instance and risks duplicate processing.

### 10.4. ABANDON

`ABANDON` affects whether an execution can ever be resumed. It is not a shortcut for restarting. Require dedicated privileges, a mandatory reason, ticket/approval per policy, and tamper-resistant audit events. Before executing, operators must confirm no real work is still running and establish how partial data will be handled.

### 10.5. RECOVER after a process crash

In Spring Batch 6.x, `JobOperator.recover(...)` helps recover executions stuck after an abnormal shutdown. Audits should capture evidence that the old process is dead, the target execution, reason, approver, and any new execution if restarted after recovery.

In Spring Batch 5.x, recovering a stuck `STARTED` execution requires a controlled metadata admin procedure—which must also be audited. Never run ad-hoc SQL updating a `STATUS` column and treat recovery as complete; job/step statuses, `ExitStatus`, optimistic locking versions, and `ExecutionContext` must stay consistent for safe restarts.

## 11. Never put secrets or sensitive data in audits

Audit trails usually have long retention periods and broader read audiences than debug logs. Treat them as a **sensitive data store** even when operator actions are just metadata.

Example parameters passed with a job:

```text
businessDate=2026-11-15
tenantId=acme
inputPath=s3://private-bucket/customer-data/...
apiToken=...
dbPassword=...
```

Never call `jobParameters.toString()` and store the raw string in an audit table. For allowed keys, use an **allowlist** and bound value lengths; for sensitive values, store a keyed HMAC fingerprint instead of the raw value. HMAC-SHA-256 with a managed key is far stronger than plain SHA-256 when inputs are low-entropy, since plain hashes can be dictionary-attacked.

Sample policy matrix:

| Information type | Suggested audit policy |
|---|---|
| `jobName`, `jobExecutionId`, action, phase | Record explicitly, as needed for traceability. |
| Organization-public `businessDate` | May record if policy permits. |
| `tenantId` | Check authorization and data policy; may pseudonymize. |
| `inputPath` containing customer names | Never store raw; use safe object revision/ID. |
| Passwords, tokens, secrets | Never record in any plaintext form. |
| Full HTTP body/headers | Never record by default; extract only approved fields. |
| Stack traces/exception messages | Store normalized error codes; put stack traces in controlled technical logs. |
| IP address | Store only with valid purpose and derived from trusted proxies. |

If the API sits behind a reverse proxy, never blindly trust client-supplied `X-Forwarded-For` as origin proof. Use forwarded headers only when infrastructure enforces a trust boundary that strips/overwrites headers at trusted ingress.

Audits also require policies for **retention, read access, encryption, backups, exports, and legally mandated erasure** defined by the organization. Append-only does not mean ignoring data protection policies; when retention requires purging, use an audited administrative workflow rather than letting runtime mutate or delete records freely.

## 12. Integrity and detecting audit tampering

Do not measure audit quality merely by "inserted into a database." An actor with `UPDATE` rights or a privileged DBA could alter history without further protections. Depending on rigor requirements, apply layered defenses:

1. **Least privilege:** runtime gets only `INSERT` and required `SELECT`; batch operators cannot delete or edit audit events.
2. **Append-only at app and DB layers:** append new events to clarify/correct rather than silently overwriting old ones.
3. **Immutable replication:** ship events to WORM storage or a centralized audit platform with retention locks.
4. **Tamper evidence:** hash chains, digital signatures, or batch digests when proof against tampering is required, with separated signing keys.
5. **Clocks and correlation:** synchronized UTC timestamps, event IDs, and request IDs to cross-check across sources.
6. **Audit pipeline monitoring:** alert on failed audit inserts, queue backlogs, stopped exporters, or `REQUESTED` events missing outcomes.

A simple hash chain can detect tampering if the chain head is anchored externally; **storing both events and hashes in the same database where an actor can rewrite everything does not prevent full history rewrites**. Match assurance levels to your threat model and compliance requirements.

## 13. Reconciling operator actions with Spring Batch metadata

Suppose the audit records:

```text
requestId=req-77 action=RESTART actorId=operator-73
targetExecutionId=1001 createdExecutionId=1015 phase=ACCEPTED
```

Query `BATCH_JOB_EXECUTION` metadata (Spring Batch 5.x default schema):

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE je.JOB_EXECUTION_ID IN (1001, 1015);
```

Query the audit table:

```sql
SELECT
    occurred_at,
    actor_id,
    action,
    phase,
    target_execution_id,
    created_execution_id,
    result_code
FROM batch_operator_audit_event
WHERE request_id = 'req-77'
ORDER BY occurred_at, event_id;
```

Then reconcile: are both on the same `JobInstance`, does the new execution exist and finish, do step execution counts align, and did business output commit properly? Default Spring Batch metadata tables **do not fully record who clicked restart and why**, which is why a separate audit table is essential.

In production, use prepared statements/bind parameters for API inputs; literal IDs in the SQL above are illustrative only. Never update `BATCH_JOB_EXECUTION` or `BATCH_STEP_EXECUTION` directly while querying for audit correlation.

### 13.1. Do not confuse event timestamps with system-wide commit order

An event timestamped `10:05:00Z` does not guarantee every change had committed to other databases at that exact instant. Multiple services, transactions, and logging backends experience latency and clock skew. Rely on **ID relationships, repository state, and transaction rules** to establish causality; timestamps are one signal among several, not absolute proof of global ordering.

## 14. Distinguishing human operators from automation

Spring Batch can be invoked by `@Scheduled`, Quartz, Kubernetes CronJobs, CI/CD, internal admin UIs, or APIs. Standardize how accountability is recorded:

| Source | `actorType` | Identity to record | Reason example |
|---|---|---|---|
| Run button in Admin UI | `HUMAN` | Subject ID from identity provider | Ticketed backfill. |
| Daily scheduler | `SERVICE` | Service/workload identity | Scheduled execution. |
| CI ops script | `SERVICE` | CI service principal and pipeline/run ID | Deployment or test data run. |
| User-triggered bot | `SERVICE` + verified `initiatedBy` | Service identity and verified human subject | Approved on-demand automation. |
| Automated recovery system | `SERVICE` | Recovery controller ID and policy version | Conditional stale execution recovery. |

When a service acts on behalf of a user, distinguish the **actual service identity calling the API** from the **human who approved or initiated the workflow**. Never attribute an event to a user solely from an unverified `initiatedBy` field in the request.

## 15. Testing operator action audits

Tests should prove trails are written when the system both accepts **and** rejects actions. Separate audit logic from full batch runs so unit tests stay fast; reserve integration tests for verifying wiring, transactions, and repository behavior.

### 15.1. Unit testing event ordering

With JUnit 5 and Mockito, verify the service records `REQUESTED` before calling `JobOperator` and `ACCEPTED` after obtaining the new ID. Note that the snippet below tests the method body directly; **it does not test `@PreAuthorize`** because it bypasses the Spring Security proxy:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.when;

import java.util.List;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;
import org.mockito.Mockito;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

class BatchOperatorServiceTest {

    private final JobOperator jobOperator = Mockito.mock(JobOperator.class);
    private final OperatorAuditWriter audit = Mockito.mock(OperatorAuditWriter.class);

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void restartWritesRequestAndAcceptanceEvents() throws Exception {
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(
                        "operator-73", "n/a",
                        List.of(new SimpleGrantedAuthority("BATCH_RESTART"))));

        when(jobOperator.restart(1001L)).thenReturn(1015L);

        BatchOperatorService service =
                new BatchOperatorService(jobOperator, audit);

        long newId = service.restart(1001L, "Investigated incident", "req-77");
        assertEquals(1015L, newId);

        InOrder calls = inOrder(audit, jobOperator);
        calls.verify(audit).append("req-77", "operator-73",
                "RESTART", "REQUESTED", 1001L, null,
                "Investigated incident", null);
        calls.verify(jobOperator).restart(1001L);
        calls.verify(audit).append("req-77", "operator-73",
                "RESTART", "ACCEPTED", 1001L, 1015L,
                "Investigated incident", null);
    }
}
```

This test verifies invocation order and required fields, not whether the audit row actually committed to the database. If `AuditWriter` uses `REQUIRES_NEW`, add an integration test proving audit rows persist even when another business transaction rolls back.

### 15.2. Authorization integration tests

With Spring Security Test (`spring-security-test`) and `MockMvc`/`WebTestClient`, cover scenarios such as:

| Test case | Expected outcome |
|---|---|
| User has `BATCH_RESTART` and target job permission | API accepts command and records `REQUESTED`, then `ACCEPTED` or `FAILED`. |
| User lacks `BATCH_RESTART` | HTTP 403; `JobOperator.restart` not called; `DENIED` audited at security boundary. |
| Unauthenticated | HTTP 401 or matching auth flow; denial/unauthenticated audited per policy without spoofing an actor. |
| Has authority but wrong tenant/job scope | Rejected and logged with an explicit reason code. |
| Required reason omitted | `JobOperator` not called; invalid-request event logged if policy requires. |
| Audit store fails to write `REQUESTED` | Privileged action blocked under fail-closed policy. |
| Operator resends identical idempotency key | No unauthorized duplicate task; response reconciled with existing request/command. |

To prove denied requests are audited, wire a real security handler/event listener in Spring Test. Mocking a service and calling `@PreAuthorize` methods without a proxy cannot prove policy enforcement works.

### 15.3. Integration tests with JobRepository

In a test environment with a dedicated JDBC repository:

1. Run a job that intentionally fails and persists the old `JobExecution`.
2. Call the restart API as an authorized operator.
3. Verify audit events `REQUESTED` followed by `ACCEPTED` with the new execution ID.
4. Verify the `JobInstance` matches and the new `JobExecution` was created.
5. Wait for completion and reconcile actual `BatchStatus` with lifecycle monitoring/audits.
6. Confirm audit records survive when test `BATCH_*` tables are cleaned up per policy.

Never test `ABANDON`, `RECOVER`, or metadata fixes against a production database. Failure recovery tests must include verifying the old process is genuinely dead before transitioning stale `STARTED` statuses.

### 15.4. Crash window testing

To test crashes between issuing a command and auditing the outcome, run the API/worker in a separate test process, inject a halt after `JobOperator` runs but before `ACCEPTED` is written, and kill that process. After restart, reconciliation must:

- Find requests with `REQUESTED` and no terminal command outcome.
- Inspect metadata/previously executed commands.
- Write a `RECONCILED` event with supporting evidence/IDs.
- Avoid re-executing the operation unless confirmed safe.

Never kill the JVM running the entire JUnit suite; a real crash test runs the job/command service in an isolated test process or container.

## 16. Incident investigation runbook for an operator action

The following outlines investigating an unexpected job restart that caused output data to be processed twice:

1. **Identify job/execution:** capture job name, `JobInstanceId`, `JobExecutionId`, timeframe, and business keys.
2. **Query audits by execution:** find `RESTART` events matching `targetExecutionId`/`createdExecutionId`.
3. **Identify actor and channel:** which operator or automation, which permissions were used, `requestId`, and source channel.
4. **Read the event chain:** are there `REQUESTED`, `DENIED`, `ACCEPTED`, `FAILED`, or `RECONCILED` events? Were retries sent with the same idempotency key?
5. **Reconcile metadata:** do executions belong to the same instance, or was a new instance created due to changed identifying parameters?
6. **Reconcile data outcomes:** actual record/file/message counts, idempotency keys, outbox entries, or external side effects.
7. **Check schedules/automation:** did a CronJob, Quartz trigger, scheduler replica, or another script fire concurrently?
8. **Document evidence-based findings:** record timeline, actor, policy, and investigation findings in the incident report; never edit or delete original audit rows.

If the audit shows `ACCEPTED` while no execution exists, suspect correlation bugs, metadata cleanup, or transaction/multi-repository misconfiguration. If the repository shows an execution while the audit stops at `REQUESTED`, suspect a crash window requiring reconciliation. Different root causes must never be papered over with one generic status-fixing SQL statement.

## 17. Common mistakes when designing audits

| Symptom | Cause | Improvement |
|---|---|---|
| Unknown who restarted a job | Relying solely on `BATCH_JOB_EXECUTION` | Emit operator audit events in the control plane with authenticated actor. |
| Audit logs "job completed" immediately on API return | Confusing command acceptance with batch lifecycle | Separate `ACCEPTED` from `BatchStatus.COMPLETED`. |
| 403 rejections are invisible | Auditing only inside `@PreAuthorize` methods | Record denials at the security boundary. |
| Logs show `admin` even for unauthorized callers | Trusting client-supplied `operatorId` | Use the authenticated subject and verified delegation. |
| Raw JobParameters dumped | Missing allowlist/redaction | Persist only approved keys and safe fingerprints. |
| One request triggers multiple restarts | UI retries/double clicks without idempotency | Use unique operation IDs/command keys and pre-execution guards. |
| Audit lost when batch rolls back | Audit written inside business transaction | Use an independent transaction and verify data-sync architecture. |
| `REQUESTED` exists without `ACCEPTED` | Crash or audit failure after `JobOperator` ran | Reconcile against `JobRepository` before retrying. |
| `STOP` audit succeeded while job stays `STARTED` | Stop is cooperative; job has not exited yet | Monitor actual status and alert on timeouts. |
| Cannot restart after `ABANDON` | Wrong administrative action used | Restrict permissions and require reason/approval. |
| Audit table wiped during Batch cleanup | Shared schema/retention or cascade foreign keys | Separate ownership/retention and delete privileges; avoid accidental cascades. |
| Audit logs contain passwords | Unfiltered URLs/bodies/headers/exceptions | Apply data minimization, masking, and security reviews. |
| Audits can be tampered with | Runtime holds UPDATE/DELETE rights | Append-only + least privilege + immutable archival copies where needed. |
| Dashboards show conflicting statuses | One shows request phase, the other shows `BatchStatus` | Clearly label `commandStatus` vs. `jobExecutionStatus`. |
| Operator affects another tenant's running job | Checking only a coarse global authority | Enforce job, tenant, and environment scopes. |

## 18. Implementing operator action auditing in a Spring Batch system

When building or hardening an operations control plane, follow this sequence:

1. **Inventory actions:** start, stop, restart, abandon, recover, schedule edits, or backfills.
2. **Define identities and permissions:** per user/service, per action, and scoped by job/tenant/environment.
3. **Design the event schema:** actor, requestId, action, phase, target/created execution IDs, UTC timestamp, and reason/ticket.
4. **Define permitted data:** field allowlists, parameter fingerprints, and rules stripping secrets/PII.
5. **Create an append-only store:** proper write privileges, retention, backups, and tamper-evidence controls as required.
6. **Hook audits into the request lifecycle:** including security-boundary denials and validation failures.
7. **Write before mutating:** choose fail-closed behavior if the audit store is unavailable.
8. **Record command outcomes** and correlate with `JobRepository` without conflating acceptance with completion.
9. **Handle crash windows** using `operationId`/idempotency/reconciliation rather than blind retries.
10. **Test both security and audit data:** unauthorized calls, timeouts, restarts, cooperative stops, parameter changes, rollbacks, and storage failures.
11. **Monitor the audit pipeline** for missing events, write errors, backlogs, or anomalous access.
12. **Run incident drills** tracing a request from principal through execution to final output data.

### Hands-on exercises

**Exercise 1 — Auditing START and RESTART**

- Build an API accepting launch/restart requests with `requestId`, `reason`, and `ticketRef`.
- Extract operator ID from the Spring Security principal, rejecting self-declared `operatorId` in the body.
- Record `REQUESTED` and `ACCEPTED` events with the created execution ID.
- Test both a successful job restart and a request hitting `JobInstanceAlreadyCompleteException`.

**Exercise 2 — Auditing DENIED**

- Create two test accounts: one with `BATCH_READ`, one with `BATCH_RESTART`.
- Use MockMvc to call the restart endpoint with the under-privileged account.
- Verify the API returns 403, `JobOperator` is not invoked, and a `DENIED` audit event includes actor and `requestId`.
- Confirm no password or access token appears in the audit record.

**Exercise 3 — Separating operator command status from batch job status**

- Send `STOP` to a long-running job and record `ACCEPTED` as soon as the request is received.
- Track until `BatchStatus` transitions to `STOPPED` or another terminal state.
- Build a view displaying separate `commandStatus` and `jobExecutionStatus` fields.

**Exercise 4 — Crash after sending command**

- Have a test worker call `JobOperator.restart(...)`, then simulate a crash before writing `ACCEPTED` in a separate test process.
- Write reconciliation reading `JobRepository` and audit records to locate the matching new execution.
- Record `RECONCILED` instead of launching another unverified restart.

**Exercise 5 — Integrity verification**

- Create an application DB role allowed only `INSERT`/`SELECT` on audit events.
- Verify the runtime role cannot update or delete historical rows.
- Export an audit snapshot and define retention/integrity storage aligned with organizational requirements.

## 19. References

- [Spring Batch Reference — JobOperator and Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): job control operations, restart, stop, and operational metadata.
- [Spring Batch 5.2 — Running a Job](https://docs.spring.io/spring-batch/reference/5.2/job/running.html): `JobParameters`, `JobLauncher`, and job instance rules.
- [Spring Batch Reference — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): `BATCH_*` tables and persisted execution data.
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, and service policies.
- [Spring Security Reference — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): authorization decision mechanics and access event integration.
- [Spring Framework Reference — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRES_NEW` and transaction boundaries.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): security event logging principles, sensitive data, integrity, and log protection.

