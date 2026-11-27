# Testing Cancelled, Retried, and Timed-Out Workflows

Business workflows often span multiple function invocations, message deliveries, and callback waits. A workflow might be waiting for customer approval, calling a payment provider, retrying a throttled step, or hitting a partner wait deadline. Therefore, workflow testing cannot merely verify the happy path; it must prove the system behaves properly when a workflow is cancelled, a step fails repeatedly, a timer expires, or multiple signals arrive concurrently.

In serverless environments, function invocations can terminate due to timeouts, scale-in, or runtime errors. An invocation ending does not mean the workflow was cancelled. Workflow state must be persisted durably and coordinated via a state machine, workflow engine, or database with guarded transitions. Cancellation, retries, and wait expiration are business decisions that must be handled explicitly, idempotently, and verifiably.

This lesson focuses on how to test three groups of behaviors: workflow cancellation and compensating side effects; bounded retries per step; and expiration while waiting on a timer or callback. The examples use an order processing flow consisting of inventory checks, payment holds, approval waits, and shipment creation, though the principles apply to Java serverless workflows in general.

## 1. A Workflow Is Different from a Function Invocation

A function invocation is a time-bounded execution of code. A workflow is a stateful business process that can outlive a single invocation and continue across many runs.

Example order processing flow:

1. Accept the order creation request.
2. Check inventory.
3. Hold or confirm payment.
4. Wait for manager approval if the order exceeds a threshold.
5. Create a shipment request.
6. Send a completion notification.

Each step may run in a separate Java function or a workflow engine activity. Between steps, the workflow may wait for minutes or days.

Consequently:

- Stopping a function does not automatically cancel the workflow.
- Cancelling a workflow does not automatically undo already created payments or shipments.
- Retrying an activity does not mean re-running the entire workflow from the beginning.
- Wait expiration requires a durable transition, not merely a finishing thread sleep.
- A cancellation message or timer event may be delivered multiple times.

A workflow needs an execution ID, state, current step, deadline, attempt metadata, and transition history to recover after runtime replacement.

## 2. State Model and Terminal Outcomes

Distinguish running states, waiting states, cancellation-in-progress states, and terminal states.

A reference state model:

~~~mermaid
stateDiagram-v2
    [*] --> RUNNING
    RUNNING --> WAITING
    WAITING --> RUNNING
    RUNNING --> RETRY_WAIT
    RETRY_WAIT --> RUNNING
    RUNNING --> CANCEL_REQUESTED
    WAITING --> CANCEL_REQUESTED
    RETRY_WAIT --> CANCEL_REQUESTED
    CANCEL_REQUESTED --> COMPENSATING
    COMPENSATING --> CANCELLED
    COMPENSATING --> COMPENSATION_FAILED
    TIMED_OUT --> COMPENSATING
    COMPENSATING --> TIMED_OUT
    RUNNING --> SUCCEEDED
    RUNNING --> FAILED
    WAITING --> TIMED_OUT
    RUNNING --> TIMED_OUT
~~~

Meanings:

| State | Meaning |
|---|---|
| RUNNING | Workflow is executing a step |
| WAITING | Waiting for a timer, callback, or external signal |
| RETRY_WAIT | A step failed transiently and is waiting for the next attempt |
| CANCEL_REQUESTED | Cancellation request received; running steps must stop or coordinate |
| COMPENSATING | Undoing reversible side effects |
| SUCCEEDED | Required steps completed |
| FAILED | Workflow failed per policy |
| CANCELLED | Cancellation completed per contract |
| TIMED_OUT | Deadline or wait timeout elapsed |
| COMPENSATION_FAILED | Could not complete compensation; requires reconciliation or intervention |

A separate terminal reason can be stored, such as `USER_CANCELLED`, `APPROVAL_EXPIRED`, or `WORKFLOW_DEADLINE`. This avoids creating a new status enum value for every termination cause.

A workflow should not be marked `CANCELLED` the moment the API receives a cancel request if payment or shipment is still running. `CANCEL_REQUESTED` indicates the request was recorded; a terminal status is set only once the workflow meets its contractual exit condition.

If the deadline expires and the workflow has no side effects needing compensation, it can transition straight to `TIMED_OUT`. If compensation is needed, retain terminal reason `WORKFLOW_DEADLINE`, move through `COMPENSATING`, and only then finish in `TIMED_OUT`. If compensation fails, use `COMPENSATION_FAILED` while preserving the terminal reason so reconciliation knows why the workflow timed out.

## 3. Designing Workflow Data for Testability

An execution table can store:

~~~sql
CREATE TABLE workflow_executions (
    workflow_id          VARCHAR(128) PRIMARY KEY,
    tenant_id            VARCHAR(128) NOT NULL,
    workflow_type        VARCHAR(128) NOT NULL,
    workflow_version     VARCHAR(64) NOT NULL,
    status               VARCHAR(32) NOT NULL,
    current_step         VARCHAR(128) NULL,
    terminal_reason      VARCHAR(64) NULL,
    version              BIGINT NOT NULL DEFAULT 0,
    cancel_requested_at  TIMESTAMP NULL,
    deadline_at          TIMESTAMP NULL,
    created_at           TIMESTAMP NOT NULL,
    updated_at            TIMESTAMP NOT NULL,
    completed_at         TIMESTAMP NULL
);
~~~

Transition history should be stored separately for investigation:

~~~sql
CREATE TABLE workflow_history (
    history_id       VARCHAR(128) PRIMARY KEY,
    workflow_id      VARCHAR(128) NOT NULL,
    from_status      VARCHAR(32) NULL,
    to_status        VARCHAR(32) NOT NULL,
    step_name        VARCHAR(128) NULL,
    reason_code      VARCHAR(64) NULL,
    attempt          INTEGER NULL,
    occurred_at      TIMESTAMP NOT NULL,
    correlation_id   VARCHAR(128) NULL
);
~~~

A wait table can store tokens and deadlines:

~~~sql
CREATE TABLE workflow_waits (
    wait_id          VARCHAR(128) PRIMARY KEY,
    workflow_id      VARCHAR(128) NOT NULL,
    wait_token       VARCHAR(128) NOT NULL,
    wait_type        VARCHAR(64) NOT NULL,
    status           VARCHAR(24) NOT NULL,
    expires_at       TIMESTAMP NOT NULL,
    completed_at     TIMESTAMP NULL,
    UNIQUE (workflow_id, wait_token)
);
~~~

These schemas are relational examples. When using a managed workflow engine, the engine may manage execution history and timer state in place of these tables. Even then, the application still needs business operation identifiers and external state tracking when lookup or reconciliation is required.

## 4. Cancellation Is a Request, Not a Process Kill Switch

An API can allow callers to request cancellation:

~~~http
POST /v1/workflows/wf-918/cancel
Authorization: Bearer <access-token>
Idempotency-Key: cancel-req-72
Content-Type: application/json

{
  "reason": "customer_request"
}
~~~

The response can be:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "workflowId": "wf-918",
  "status": "CANCEL_REQUESTED"
}
~~~

`202` means the system accepted the request and will process it; it does not assert that all side effects have already been undone. If the workflow is already terminal, the API should return the current outcome per contract—such as `SUCCEEDED` or `CANCELLED`—rather than pretending cancellation succeeded.

The cancellation command must:

- Authenticate the caller and verify permissions on the workflow.
- Record the request within a transaction.
- Use an idempotency key so caller retries do not create duplicate requests.
- Check terminal states.
- Signal the worker or workflow engine.
- Return a clear status so the caller can poll or await a callback.

Never use killing a process as a business cancellation mechanism. The runtime may stop the function, but doing so has no idea how to void payments, release inventory, or notify partners.

## 5. Cooperative Cancellation in Java

A worker running a long step should check for cancellation at safe checkpoints. An internal token can be used:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

public final class CancellationToken {
    private final AtomicBoolean requested = new AtomicBoolean(false);

    public void requestCancellation() {
        requested.set(true);
    }

    public boolean isCancellationRequested() {
        return requested.get();
    }

    public void throwIfCancellationRequested() {
        if (isCancellationRequested()) {
            throw new WorkflowCancellationException();
        }
    }
}
~~~

Example in a multi-part processing step:

~~~java
public void processOrder(
        Order order,
        CancellationToken cancellation) {

    validateOrder(order);
    cancellation.throwIfCancellationRequested();

    reserveInventory(order);
    cancellation.throwIfCancellationRequested();

    authorizePayment(order);
    cancellation.throwIfCancellationRequested();

    createShipmentRequest(order);
}
~~~

This is only an in-execution-environment cancellation token. Serverless functions can stop abruptly and in-memory tokens do not survive restarts. Therefore, the source of truth must be durable state in the workflow engine/database; workers must read or receive cancellation signals from that source.

Do not check cancellation in the middle of an indivisible pair of operations if doing so would leave inconsistent business state. Place checkpoints at safe boundaries after side effects are recorded.

## 6. Races Between Cancellation and Completion

A common race condition:

- A worker is completing the final step.
- The caller sends a cancellation simultaneously.
- Both transactions try to transition the workflow to a terminal state.

Only one transition may win. Use optimistic versioning or conditional updates:

~~~sql
UPDATE workflow_executions
SET status = 'CANCEL_REQUESTED',
    cancel_requested_at = CURRENT_TIMESTAMP,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE workflow_id = ?
  AND version = ?
  AND status IN ('RUNNING', 'WAITING', 'RETRY_WAIT');
~~~

If the updated row count is 0, the status changed or the version is stale. Re-read the execution and return the current status.

Completion transitions also require conditions:

~~~sql
UPDATE workflow_executions
SET status = 'SUCCEEDED',
    completed_at = CURRENT_TIMESTAMP,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE workflow_id = ?
  AND version = ?
  AND status = 'RUNNING'
  AND cancel_requested_at IS NULL;
~~~

If cancellation wins first, the worker cannot write `SUCCEEDED` with the old version. If completion committed first, cancellation must return the completed outcome.

Do not merely check status in Java and then update separately; checking and transitioning must be atomic in the database or serialized by the workflow engine.

## 7. Compensating Side Effects with a Saga

Cancellation cannot erase history in external systems. If the workflow already reserved inventory, authorized payment, or created a shipment, compensating actions are needed.

Saga examples:

| Completed Step | Potential Compensating Action |
|---|---|
| Reserve inventory | Release reservation |
| Authorize payment | Void authorization |
| Capture payment | Refund payment if contract permits |
| Create shipment | Cancel shipment or request carrier intercept |
| Send notification | Usually cannot be recalled; send correction notice if needed |

Compensation is not a database rollback. It is a new business action that can fail and requires its own retries.

~~~mermaid
flowchart TD
    A[Reserve inventory] --> B[Authorize payment]
    B --> C[Wait for approval]
    C -->|Approved| D[Create shipment]
    C -->|Cancelled / expired| X[Start compensation]
    D --> E[Workflow succeeded]
    X --> F[Void payment authorization]
    F --> G[Release inventory]
    G --> H[Mark cancelled or timed out]
~~~

Compensation order usually reverses completed steps, though actual order must follow business dependencies. If payment was captured, the refund may be asynchronous and cannot finish immediately.

Every compensating action must be idempotent. If a worker crashes after the provider issues a refund but before the workflow records the outcome, retries must not issue a second refund.

## 8. Distinguishing Retry, Compensation, and Replay

These three actions serve distinct purposes:

- **Retry:** re-executing the same step after a transient failure.
- **Compensation:** executing a business action to offset the side effect of a succeeded step.
- **Replay:** re-running history or part of a workflow for operational purposes, usually requiring version control and idempotency.

For example, if payment authorization returns 503 before producing a result: retrying may be appropriate using the same provider idempotency key or querying the operation. If payment was already authorized and the customer cancels the order: voiding the authorization is compensation, not retrying authorization. If a projection must be rebuilt from event history: that is replay and requires appropriate scoping/targets.

Do not use retry as a substitute for compensation. Do not replay an entire workflow to fix a single failed step if prior side effects already occurred.

## 9. Classifying Errors Before Retrying

| Error Type | Example | Action |
|---|---|---|
| Transient | Network reset, temporary 503, throttling | Bounded retry |
| Permanent | Invalid input, business rule rejection | Stop and transition to `FAILED` |
| Authorization | 401/403 from identity or policy | Do not retry with the same credentials |
| Conflict | Optimistic lock or state changed | Re-read new state; conditional retry |
| Ambiguous outcome | Timeout after provider may have processed request | Query operation or retry with idempotency key |
| Deadline exceeded | Not enough time left for a new attempt | Stop retrying and terminate/reconcile |
| Cancellation | Caller requested cancellation | Do not retry cancelled step; run compensation if needed |

HTTP status is only one signal. For example, 429 typically requires honoring `Retry-After`; 500 may stem from a deterministic bug and should not be retried forever. Error classifiers must follow each dependency's contract.

## 10. Exponential Backoff, Jitter, and Retry Limits

A retry policy typically defines:

- Max attempts, including the initial call.
- Initial delay.
- Multiplier.
- Maximum delay.
- Maximum elapsed time.
- Per-attempt timeout.
- Retryable error classifier.
- Jitter.
- Overall workflow deadline.

Exponential backoff formula:

~~~text
cap(n) = min(maxDelay, initialDelay × multiplier^(n - 1))
actualDelay(n) = random(0, cap(n))
~~~

Full jitter prevents multiple workflows from retrying at the exact same moment. If the provider returns `Retry-After`, do not retry earlier than the requested wait time.

Example:

| Attempt | Backoff Cap | Random Delay |
|---:|---:|---:|
| 1 | 200 ms | 0–200 ms |
| 2 | 400 ms | 0–400 ms |
| 3 | 800 ms | 0–800 ms |
| 4 | 1,600 ms | 0–1,600 ms |
| 5 | 2,000 ms | 0–2,000 ms |

After max attempts, the workflow transitions to error handling, DLQ, or compensation depending on step type. Never keep a function alive merely to sleep for minutes; use durable timers, queue delays, or a workflow engine.

## 11. Retrying Per Step Without Restarting the Whole Workflow

Workflows have checkpoints and durable state. If the email notification step fails after payment and shipment succeeded, do not re-run payment and shipment.

Persist step execution:

~~~sql
CREATE TABLE workflow_steps (
    workflow_id       VARCHAR(128) NOT NULL,
    step_name         VARCHAR(128) NOT NULL,
    status            VARCHAR(32) NOT NULL,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    idempotency_key   VARCHAR(256) NOT NULL,
    next_attempt_at   TIMESTAMP NULL,
    last_error_code   VARCHAR(64) NULL,
    started_at        TIMESTAMP NULL,
    completed_at      TIMESTAMP NULL,
    PRIMARY KEY (workflow_id, step_name)
);
~~~

When retrying:

1. Read workflow and step state.
2. Verify the workflow is not cancelled, terminal, or past deadline.
3. Claim the target step via version/lease.
4. Use the same idempotency key for the same logical operation.
5. Call the dependency within remaining timeout budget.
6. Save the result and transition step state in a transaction.
7. Advance to the next step only after the step commits successfully.

If a managed workflow engine already supports per-state retries, avoid wrapping an unbounded retry loop inside the Java activity. Account for total attempts across engine and HTTP client so requests do not multiply unexpectedly.

## 12. Idempotency for Side Effects and Compensations

A retry can re-invoke an operation that succeeded before the response was lost. Therefore, every side effect needs a stable identity.

Example key:

~~~text
workflowId + stepName + businessOperationVersion
~~~

The same logical operation must use the same key across all attempts. For compensation, use a separate yet stable key, such as `workflowId + compensatePaymentAuthorization`.

Key rules:

- Pass the provider idempotency key if the API supports it.
- Store the provider request ID and outcome.
- Use unique constraints in the database for business operations.
- When outcomes are unclear, look up status before creating a new operation.
- Never generate a new key per retry.
- Retain records long enough to cover retries, redrives, and reconciliation windows.

Idempotency prevents duplicate side effects within the provider's contract. It does not automatically guarantee end-to-end exactly-once semantics across multiple systems.

## 13. Wait States and Durable Timers

A workflow may need to wait for:

- Manager approval.
- Customer confirmation.
- Partner webhook delivery.
- Scheduled delivery time.
- A delay before the next retry.
- Another external event.

Never use `Thread.sleep` or hold a function invocation open for long waits. Persist a durable wait state and let the workflow engine/timer service wake the execution.

A wait record should contain:

- workflow ID.
- unique wait token.
- wait type.
- `created_at` and `expires_at`.
- status (`WAITING`/`COMPLETED`/`EXPIRED`/`CANCELLED`).
- correlation ID for callbacks.
- version/fencing token if multiple consumers exist.

Timer events can arrive late or repeatedly. Handlers must check the wait token and current state before executing transitions.

## 14. Wait Expiry Differs from Function Timeout

These concepts must be separated:

| Concept | Meaning |
|---|---|
| Function timeout | Maximum execution duration allowed for one invocation |
| Step timeout | Maximum time an activity/step is allowed to run |
| Wait expiry | Deadline for waiting on a callback/signal |
| Workflow deadline | Overall cutoff for the entire business process |
| Lease expiry | Timestamp when a worker's claim expires |
| Queue visibility/ack deadline | Window during which a message is hidden or must be acknowledged per provider |

A function timeout should not automatically be treated as a workflow timeout. A worker may time out while the workflow still has remaining deadline and can retry. Wait expiry can occur when no function is currently running. The workflow deadline encompasses execution, retries, and waiting time.

Set consistent time bounds. For example, total workflow deadline is 24 hours; approval wait is 4 hours; each activity has a 30-second timeout and at most 4 attempts. Never let retries extend beyond the workflow deadline.

## 15. Handling Late Callbacks and Duplicate Timers

Suppose a workflow waits for approval until 17:00. An approved callback arrives at 17:02, after the wait expired. Do not automatically accept late callbacks if business rules already moved the workflow to compensation or terminal timeout.

Callbacks should carry:

~~~json
{
  "workflowId": "wf-918",
  "waitToken": "approval-7f2",
  "eventId": "approval-event-31",
  "decision": "APPROVED",
  "occurredAt": "2026-11-17T16:58:00Z"
}
~~~

The handler checks:

- Caller is authorized to send callbacks for this workflow.
- `waitToken` matches the active wait.
- `eventId` has not yet been processed.
- Workflow is still in `WAITING`.
- Receipt timestamp from a trusted clock has not exceeded `expires_at`.
- Callback belongs to the right tenant and approval request.

Use a transaction/conditional update so the callback and timer expiry compete for the transition. Only one wins. The loser reads current state and logs the late/duplicate signal without re-executing side effects.

### Time-Boundary Rules

Define precisely whether a callback is valid when `received_at` is strictly less than or less-than-or-equal to `expires_at`. For example:

~~~text
callback accepted when database_received_at < expires_at
wait expired when database_now >= expires_at
~~~

Use the database or workflow engine clock instead of arbitrary per-worker clocks. Schedulers can deliver timers late; handlers must still evaluate `expires_at` rather than relying on timer arrival time.

## 16. Java: Testable Retry Delay Calculation

To test jitter without waiting in real time, separate delay calculation from sleeping and inject the random source.

~~~java
import java.time.Duration;
import java.util.random.RandomGenerator;

public record RetryPolicy(
        int maxAttempts,
        Duration initialDelay,
        Duration maxDelay,
        Duration maxElapsed) {

    public RetryPolicy {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException("maxAttempts must be >= 1");
        }
        if (initialDelay == null || initialDelay.isNegative()
                || initialDelay.isZero()
                || maxDelay == null
                || maxDelay.compareTo(initialDelay) < 0
                || maxElapsed == null
                || maxElapsed.isNegative()
                || maxElapsed.isZero()) {
            throw new IllegalArgumentException("Invalid retry policy");
        }
    }
}

public final class RetryDelay {

    private RetryDelay() {}

    public static Duration fullJitter(
            RetryPolicy policy,
            int failedAttempt,
            RandomGenerator random) {

        if (failedAttempt < 1
                || failedAttempt >= policy.maxAttempts()) {
            throw new IllegalArgumentException("Invalid failed attempt");
        }

        long initial = policy.initialDelay().toMillis();
        long maximum = policy.maxDelay().toMillis();
        long cap = initial;

        for (int i = 1; i < failedAttempt && cap < maximum; i++) {
            cap = cap > maximum / 2 ? maximum : cap * 2;
        }

        cap = Math.min(cap, maximum);
        long delay = random.nextLong(cap + 1);
        return Duration.ofMillis(delay);
    }
}
~~~

This code only calculates the delay; the workflow engine or scheduler creates the durable timer. Never call `Thread.sleep` for long waits inside a function. Check that the calculated duration does not exceed remaining deadline before scheduling the next attempt.

Unit tests can inject a fake random generator returning boundary values to verify delays of 0 and `cap`. A fake clock can verify `maxElapsed` without waiting in wall-clock time.

## 17. Java: Conditional Cancellation Transition

A command service should update state conditionally instead of doing an unlocked read-then-write.

~~~java
public enum CancelResult {
    ACCEPTED,
    ALREADY_REQUESTED,
    ALREADY_TERMINAL,
    NOT_FOUND
}

public final class WorkflowCancellationService {

    private final WorkflowRepository repository;

    public WorkflowCancellationService(
            WorkflowRepository repository) {
        this.repository = repository;
    }

    public CancelResult requestCancel(
            String workflowId,
            String tenantId,
            String reason,
            String idempotencyKey) {

        var result = repository.requestCancellation(
                workflowId, tenantId, reason, idempotencyKey);

        return result;
    }
}
~~~

The repository must execute the conditional update and write to the outbox in the same transaction. A separate dispatcher reads the outbox and sends retryable signals. If publishing fails after commit, the cancellation remains persisted and the dispatcher retries; the API does not depend on an external network call outside the transaction.

This example omits SQL details since repositories depend on the chosen database. The critical contract is atomic commit of state and outbox; signals must never exist only in the API function's memory.

## 18. Testing Cancellation

Tests must verify both state and side effects.

| Scenario | Expected Outcome |
|---|---|
| Cancel workflow before it starts | No subsequent steps execute; transitions to `CANCELLED` per policy |
| Cancel while `WAITING` | Old timer/callback cannot resume the workflow |
| Cancel while activity is running | Records `CANCEL_REQUESTED`; activity stops at a safe checkpoint |
| Cancel after inventory reservation | Releases reservation exactly once |
| Cancel after payment authorization | Voids authorization or records state needing reconciliation |
| Cancel after payment capture | Executes refund per policy; does not assume rollback |
| Cancel after shipment created | Calls cancel/intercept if feasible; records outcome |
| Cancel twice with same key | Idempotent; does not trigger duplicate compensations |
| Cancel races with completion | Only one terminal transition wins |
| Cancel when workflow already terminal | Returns current state without altering history |
| Worker crashes after receiving cancel | Workflow stays `CANCEL_REQUESTED` and another worker continues |
| Compensation fails | `COMPENSATION_FAILED` or manual handling state |

Verify no new steps start after cancellation wins the transition. If an activity cannot stop immediately, verify it cannot overwrite terminal state and that compensation/reconciliation still triggers.

## 19. Testing Retries

| Scenario | Expected Outcome |
|---|---|
| Succeeds on first attempt | Zero retries |
| Transient error then succeeds | Retries only the failing step |
| Permanent error | Stops immediately, transitions to `FAILED` |
| Max attempts reached | No extra attempts |
| Max elapsed reached | No new attempt scheduled |
| Backoff hits cap | Delay never exceeds `maxDelay` |
| Full jitter | Delay stays within `0..cap` |
| `Retry-After` present | Does not retry before provider-requested time |
| Timeout after side effect | Uses same idempotency key or queries provider before retrying |
| Worker crashes after provider success | Recovery creates no duplicate side effects |
| Nested multi-layer retries | Total attempts are bounded and measurable |
| Transient compensation failure | Retries compensation independently from forward step |
| Workflow already cancelled | Does not retry forward actions |
| Workflow deadline elapsed | Does not start new attempts |

Tests must verify attempt counts, state history, `next_attempt_at`, and dependency call counts. Checking only that the workflow ended in `SUCCEEDED` is insufficient; redundant calls or duplicate side effects could still have occurred along the way.

## 20. Testing Wait Expiry and Callbacks

| Scenario | Expected Outcome |
|---|---|
| Callback arrives before deadline | `WAITING` transitions to `RUNNING`/next state |
| Callback arrives exactly on boundary | Honors published `<` or `<=` rule |
| Callback arrives after deadline | Does not resume workflow; logs late signal |
| Timer fires on time | Wait becomes `EXPIRED` and workflow handles timeout |
| Timer fires late | Still expires based on `expires_at` |
| Timer delivered twice | Only one transition succeeds |
| Callback sent twice | Event ID deduplicated |
| Callback and timer race concurrently | One transaction wins; loser produces no side effects |
| Wait already cancelled | Stale callback/timer does not resurrect workflow |
| Timer for old wait token | Ignored |
| Scheduler outage | Reconciliation finds overdue waits and compensates |
| Worker clock skew | Decisions still rely on trusted DB/engine clock |

### Testing Without Real Sleeps

Use a fake clock or workflow test harness to advance time to just before, right at, and just after deadlines. This is fast, deterministic, and enables testing race conditions without waiting minutes or hours.

## 21. Race Conditions to Trigger Deliberately

Some bugs only surface when signals arrive concurrently:

- Cancel command and completion event.
- Timer expiry and approval callback.
- Two retry workers claiming the same step.
- Lease expiring while an old worker is still running.
- Compensation retry and workflow redrive.
- Provider response arriving after caller timeout.
- Duplicate events during database failover.

Use barriers/latches in integration tests to synchronize two threads, then assert database state and side-effect counts. In serverless integration tests, send two messages with the same workflow ID to two execution environments and verify conditional updates/unique constraints hold.

Never rely on random sleeps hoping to provoke a race. Build deterministic synchronization points so tests are repeatable.

## 22. Testing Durable Workflows After Restarts

A workflow must recover from persisted state when a function or worker stops.

Test steps:

1. Start the workflow and complete several steps.
2. Leave the workflow in `WAITING` or `RETRY_WAIT`.
3. Stop the process/worker or end the invocation.
4. Start a new worker.
5. Recover execution from the state store/workflow engine.
6. Verify completed steps do not re-execute side effects.
7. Verify timers and retry schedules remain intact.
8. Verify pending cancellation signals continue processing.

If state lived only on the Java heap, the workflow would be lost when the execution environment is replaced. Durable state must live outside the process.

## 23. Provider Workflow Engines

Cloud platforms offer their own orchestration services, with differing semantics:

| Platform | Typical Services | Capabilities to Verify |
|---|---|---|
| AWS | Step Functions, Lambda, EventBridge | Retry/Catch, timeouts, wait states, callback task tokens, execution history |
| Google Cloud | Workflows, Cloud Run functions, Pub/Sub | Retry policies, callback/call semantics, execution deadlines, event delivery |
| Azure | Durable Functions, Azure Functions, Service Bus | Durable timers, external events, orchestration replay, retry and cancellation behavior |
| Standalone frameworks | Temporal or equivalent workflow engines | Durable timers, activity retries, cancellation scopes, compensation, and history |

Do not assume a cancel API has identical semantics across engines. Some engines mark an execution cancelled while an external activity continues running until it checks a cancellation signal or times out. Read documentation for the deployed version and test the specific adapter.

### Workflow Replay and Deterministic Code

Some durable engines replay orchestration history to rebuild state. Orchestration code must obey the engine's determinism rules; avoid directly calling random generators, current time, or network I/O inside orchestration logic if the engine requires those operations to run through supported activities/APIs. Place side effects in idempotent activities.

## 24. Observing Cancellation, Retries, and Expiry

Metrics and logs should distinguish three groups:

**Cancellation**
- Cancel requests accepted/rejected.
- Time from `CANCEL_REQUESTED` to terminal state.
- Succeeded/failed compensations.
- Workflows cancelled while activities are still running.
- Cancellation vs. completion races.

**Retry**
- Attempts by step and error class.
- Retry success rate.
- Exhausted attempts.
- Backoff delay and remaining deadline.
- Retry amplification per dependency.

**Wait expiry**
- Open waits count.
- Wait age and expired count.
- Timer delivery lag.
- Late callback count.
- Duplicate timer/callback count.
- Waits stuck after scheduler outages.

Logs should include `workflowId`, `stepName`, `attempt`, controlled `waitToken` or signal ID, transition version, and correlation ID. Never log secret tokens or sensitive payloads. Metric labels must stay low-cardinality; keep workflow IDs in logs and traces.

## 25. Testing in CI and Integration Environments

An effective test suite spans multiple layers:

1. **Unit tests:** classifiers, backoff math, transition guards, and deadline arithmetic.
2. **State-machine tests:** all valid transitions and forbidden transitions.
3. **Repository integration tests:** conditional updates, transactions, unique constraints, and outbox.
4. **Workflow engine tests:** durable timers, retries, callbacks, and cancellation semantics.
5. **Provider contract tests:** HTTP status codes, `Retry-After`, callback signatures, and provider lookup requests.
6. **Fault injection:** crashes before/after side effects, timeouts, duplicate deliveries, and dependency outages.
7. **Concurrency tests:** cancel/completion, callback/expiry, and double claims.
8. **Recovery tests:** worker restarts, scheduler outages, DLQ redrives, and reconciliation.

In CI, fast unit and state-machine tests run on every pull request. Integration tests against real providers or emulators run in dedicated pipelines using isolated test accounts/projects and capped budgets. Never use production payments or shipments to test compensation.

## 26. Common Testing Pitfalls

- **Testing only the happy path:** misses cancel/retry/expiry races; build failure-window tests.
- **Treating invocation timeout as workflow cancellation:** state may still be `RUNNING`; separate the two lifecycles.
- **Marking `CANCELLED` immediately on request:** side effects may remain uncompensated; use `CANCEL_REQUESTED`.
- **Retrying the entire workflow:** payments or shipments may run twice; retry by step/checkpoint.
- **Retrying every exception:** permanent errors loop uselessly; classify errors.
- **Lacking idempotency on compensation:** refunds or releases may run twice; use separate stable keys.
- **Using `Thread.sleep` for long waits:** holds invocations and is non-durable; use timers/workflow waits.
- **Timer handlers not checking wait tokens:** stale timers can advance workflows wrongly; verify tokens/versions.
- **Accepting late callbacks:** revives timed-out workflows; verify deadlines using a trusted clock.
- **Using per-worker clocks:** clock skew produces divergent decisions; use DB/engine time.
- **Skipping race tests:** two terminal transitions can collide; use conditional updates.
- **Skipping restart tests:** in-memory state disappears; test recovery from durable storage.
- **Stacking multiple retry layers:** attempts multiply unexpectedly; assign retry ownership and budgets.
- **Ignoring compensation failures:** orders remain in inconsistent business states; configure alerts and reconciliation.

## 27. Test Design Checklist

Before shipping a workflow to production, verify:

- [ ] Every workflow has a durable execution ID, version, and state.
- [ ] Cancellation commands are idempotent and authorized.
- [ ] `CANCEL_REQUESTED` is distinct from `CANCELLED`.
- [ ] Occurred side effects have compensation or reconciliation plans.
- [ ] Compensations have dedicated idempotency keys.
- [ ] Retry classifiers distinguish transient, permanent, and ambiguous outcomes.
- [ ] Max attempts, max elapsed time, and workflow deadlines are enforced.
- [ ] Retries re-run only the necessary step.
- [ ] Wait states use durable timers rather than sleeping functions.
- [ ] Callbacks and timers carry stable tokens/identities.
- [ ] Late callbacks and duplicate timers are handled.
- [ ] Races between cancellation, completion, and expiry are tested.
- [ ] Restarts do not lose workflow state.
- [ ] Metrics/logs explain transitions and retries.
- [ ] Reconciliation exists for compensations or activities with unknown outcomes.

## 28. Key Takeaways

Workflow cancellation, retries, and wait expiration are business transitions that impact side effects. Cancellation should begin with `CANCEL_REQUESTED`, stop safely, and run compensation if needed. Never equate a function invocation ending with a workflow being cancelled.

Retries require error classification, jittered backoff, max attempts, max elapsed time, and deadlines. Retry only failing steps; enforce idempotency on forward actions and compensations. Long waits must use durable timers, while callbacks and timers need tokens plus conditional transitions to handle duplicates, late arrivals, and deadline races.

Thorough testing must reproduce crashes, duplicates, late callbacks, duplicate timers, concurrent cancel/completion, and worker restarts using fake clocks and fault injection. When state is durable, transitions are conditional, and side effects are idempotent, Java serverless workflows can recover cleanly from failures without repeating side effects or resurrecting finished processes.
