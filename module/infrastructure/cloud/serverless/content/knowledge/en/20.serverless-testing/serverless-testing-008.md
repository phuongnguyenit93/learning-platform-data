# Testing Workflows with Timeouts, Callbacks, and Compensations

A serverless workflow typically orchestrates multiple Java Lambda functions or external services. One step may finish quickly, while another waits hours for a partner response. When a failure occurs after an earlier step already produced a side effect, the workflow must also execute compensating actions to return the business state to safety.

Testing this class of workflow requires going beyond verifying that each Lambda returns the right result. You must test state transitions, wait times, retries, callbacks, timeouts, compensations, replayability, and indeterminate outcomes. With AWS Step Functions, you can combine Java unit tests, per-state testing, local simulation, and integration tests in an isolated AWS environment.

This lesson focuses on building a test plan for workflows with timeouts, callback task tokens, and Saga compensations; injecting controlled faults; and verifying execution history alongside business state.

## 1. Why must workflows be tested as a system?

Individual Lambdas can work properly when invoked in isolation yet the workflow still fails because:

- A state passes the wrong payload or overwrites needed input with its result.
- Java exception names do not match `ErrorEquals` in Retry/Catch.
- A retry creates a duplicate side effect when the prior attempt succeeded but the response timed out.
- A callback fails to arrive before the deadline.
- A callback arrives after the task already timed out or the workflow ended.
- A task token is sent to the wrong party, leaked, or reused twice.
- Compensations run out of order or run even when the corresponding forward step never succeeded.
- A compensation fails yet the workflow still marks itself as cleanly rolled back.
- A new execution reprocesses data already committed by an earlier execution.
- The workflow finishes technically while business state in the database is inconsistent.

Therefore, verify two layers of results:

1. **Workflow result:** whether the execution succeeded, failed, timed out, or is waiting in a specific state.
2. **Business result:** what actual state the order, payment, reservation, or shipment is in after the workflow finishes.

An execution status of FAILED does not automatically prove every side effect was undone. An execution status of SUCCEEDED does not automatically prove business data is valid if a Lambda swallowed an exception or returned wrong results.

## 2. Workflow model used in testing

Consider an order placement workflow with these steps:

1. Reserve inventory.
2. Charge payment.
3. Create shipment.
4. Send notification.
5. If a step fails, run the appropriate compensating actions.

A failure branch may need to refund payment and then release inventory. If payment was never captured, only inventory needs releasing. If payment status is unknown due to a timeout, the workflow must query the transaction using the idempotency key before deciding whether to refund.

~~~mermaid
flowchart TD
    A["Start order workflow"] --> B["Reserve inventory"]
    B --> C["Charge payment"]
    C --> D["Create shipment"]
    D --> E["Notify customer"]
    E --> F["Succeed"]
    C -->|Failure| G["Release inventory"]
    D -->|Failure| H["Refund payment"]
    H --> G
    G --> I["Mark order failed"]
    I --> J["Fail"]
    H -->|Compensation failure| K["Manual recovery"]
    G -->|Compensation failure| K
~~~

This is a Saga: each business step can have a compensating action. Compensation is not a distributed transaction rollback. It is a new business operation that can itself fail and must be tracked separately.

A callback workflow may wait for a payment provider or human approver. In that case, a Task state sends a request and a task token to a trusted component; the workflow pauses until that component calls `SendTaskSuccess` or `SendTaskFailure`.

## 3. Timeout layers to distinguish

Timeouts can occur at multiple layers. Looking only at a generic timeout message without knowing which layer expired leads to flawed debugging and retry designs.

| Layer | Timeout controlled | What to test |
|---|---|---|
| HTTP client/API | How long the caller waits for a response | Does the caller retry on response timeout? |
| Lambda | Maximum duration of a single invocation | Does the function stop on time and close resources properly? |
| Step Functions Task | How long the Task state may wait to complete | Does the state transition to Catch or fail the execution? |
| Callback heartbeat | Maximum interval between heartbeats | Does the worker send heartbeats reliably with the right task token? |
| Workflow/business deadline | Total time the business process is allowed to span | Can it halt or route to manual handling? |
| Downstream service | Wait time for database, payment provider, or API | Does a timeout yield an indeterminate outcome or partial side effect? |

### 3.1. Lambda timeout vs. Task timeout

Lambda timeout caps the invocation duration. Step Functions Task `TimeoutSeconds` caps how long the state waits for the task to finish. Maintain a sensible relationship between the two limits.

If the Task timeout is shorter than the Lambda timeout, Step Functions can stop waiting while Lambda is still running. Lambda could keep producing side effects after the workflow already branched into failure handling. If the Lambda timeout is shorter than the Task timeout, Step Functions receives the failure from Lambda before the Task times out.

In tests, cover both scenarios:

- Lambda returns an error before the Task timeout.
- Task times out while a downstream operation's outcome remains uncertain.

Never assume a Task timeout automatically halts external operations already started by Lambda. Each side effect needs its own timeouts, idempotency, and status lookup.

### 3.2. Heartbeat timeout

For callbacks or task patterns requiring long-running workers, `HeartbeatSeconds` limits the gap between heartbeat signals. The worker sends heartbeats via the `SendTaskHeartbeat` API to signal that work is still progressing.

Test:

- Heartbeats arrive before the deadline.
- A heartbeat arrives later than `HeartbeatSeconds`.
- A worker sends a heartbeat with an invalid token.
- A worker crashes suddenly and stops sending heartbeats.
- A heartbeat arrives after the task has already timed out.

Heartbeats do not replace `TimeoutSeconds`. Heartbeats detect a stalled worker; the task timeout still caps the total duration the state may run.

### 3.3. Business deadlines

A process may have a business deadline longer than any single invocation—for instance, payment must be confirmed within 30 minutes. Never hold a Lambda running for 30 minutes just waiting.

Use a Wait state, callback task, or stateful workflow to wait. When the deadline expires, the workflow can query provider status, cancel the request, or enter an exception-handling branch.

Tests must verify deadlines are evaluated using consistent business time and timezones. Avoid relying on container local clocks when workflows and providers use UTC timestamps.

## 4. Designing testable timeouts

Overly long timeouts make test suites slow and hard to reproduce. Overly short timeouts can introduce artificial race conditions unlike production. Parameterize configuration per environment while keeping state-transition logic identical.

Example Task state waiting on a callback:

~~~json
{
  "WaitForApproval": {
    "Type": "Task",
    "Resource": "arn:aws:states:::lambda:invoke.waitForTaskToken",
    "Parameters": {
      "FunctionName": "arn:aws:lambda:REGION:ACCOUNT:function:request-approval:test",
      "Payload": {
        "taskToken.$": "$$.Task.Token",
        "orderId.$": "$.orderId",
        "correlationId.$": "$.correlationId"
      }
    },
    "TimeoutSeconds": 30,
    "HeartbeatSeconds": 10,
    "Next": "ProcessApproval",
    "Catch": [
      {
        "ErrorEquals": ["States.Timeout"],
        "ResultPath": "$.approvalTimeout",
        "Next": "ExpireApproval"
      }
    ]
  }
}
~~~

Values of 30 and 10 seconds are suitable only for test fixtures. Production requires deadlines aligned with SLAs and service limits. This callback integration pattern applies to Standard workflows; Express workflows do not support callback task token integration.

Tests should deploy a dedicated test state machine definition or parameterize timeouts to shorten test runs. Never edit production timeouts just to make tests run faster.

### 4.1. Boundary timeout testing

Create scenarios right around the deadline:

- Callback arrives slightly before the timeout.
- Callback arrives right when the timeout can trigger.
- Callback arrives after the timeout.
- Worker sends a heartbeat just before the deadline.
- Worker sends a heartbeat after the deadline.
- Lambda finishes just before the Task timeout.
- Downstream response arrives after the caller has timed out.

Boundary cases uncover races between callbacks, retries, and timeouts. When running integration tests, record UTC timestamps, execution ARNs, masked task token references, and state transitions to reconstruct event ordering.

## 5. Retries and Catch must be tested alongside timeouts

Retries can turn a transient error into a success, but they can also duplicate side effects. `Catch` determines the fallback path after retries exhaust or when an error does not match the retry policy.

Example payment Task:

~~~json
{
  "ChargePayment": {
    "Type": "Task",
    "Resource": "arn:aws:states:::lambda:invoke",
    "Parameters": {
      "FunctionName": "arn:aws:lambda:REGION:ACCOUNT:function:charge-payment:test",
      "Payload.$": "$"
    },
    "Retry": [
      {
        "ErrorEquals": [
          "Lambda.ServiceException",
          "Lambda.AWSLambdaException",
          "Lambda.SdkClientException",
          "Lambda.TooManyRequestsException"
        ],
        "IntervalSeconds": 1,
        "BackoffRate": 2.0,
        "MaxAttempts": 2
      }
    ],
    "Catch": [
      {
        "ErrorEquals": ["Payment.Declined"],
        "ResultPath": "$.paymentError",
        "Next": "ReleaseInventory"
      },
      {
        "ErrorEquals": ["States.Timeout"],
        "ResultPath": "$.paymentTimeout",
        "Next": "ReconcilePayment"
      },
      {
        "ErrorEquals": ["States.ALL"],
        "ResultPath": "$.unexpectedError",
        "Next": "ManualRecovery"
      }
    ],
    "Next": "CreateShipment"
  }
}
~~~

Error names in `ErrorEquals` must match the exact error names returned by the Lambda integration. Do not only check message strings in Java exceptions. Inspect execution history or test responses to verify the error name and cause.

`MaxAttempts` is the number of additional retries after the initial attempt. With `MaxAttempts` set to 2, the Task can execute up to three times total: one initial attempt plus two retries. In tests, record the handler invocation count to avoid misunderstandings.

### 5.1. Testing transient vs. permanent errors

| Scenario | Expected outcome |
|---|---|
| Throttled once, then succeeds | Retries and proceeds |
| Service unavailable through all retries | Transitions to matching Catch |
| Payment declined | Does not retry business error; releases reservation |
| Missing IAM permissions | Fails and reports configuration error |
| Timeout where payment may have succeeded | Reconciles via payment reference/idempotency key |
| Invalid input schema | Routes to rejection or data-error branch |
| Compensation failure | Routes to manual recovery and raises alert |

Do not treat `States.ALL` as a guarantee that every error is caught in all circumstances. Certain special Step Functions errors follow dedicated matching rules. Verify actual error names and design the state machine for the specific error classes you need to handle.

### 5.2. Exponential backoff and timing tests

With `IntervalSeconds` and `BackoffRate`, wait intervals grow across retries. Tests should verify not only call counts, but also that the policy is configured as intended. If `MaxDelaySeconds` or `JitterStrategy` are used in your service version, verify the cap and distribution of retry intervals.

Avoid unit tests that rely on long real sleeps. Validate the ASL structure and run integration tests with short intervals. Measure invocation timestamps in tests to catch retries firing too early or too aggressively.

## 6. Callback task tokens: how the flow works

The callback pattern fits when Step Functions must wait for an external component to finish work. A Lambda initiates the work, receives a task token in its payload, stores the token in a reliable backend, and sends the request to a worker or partner. Upon completion, the callback service calls Step Functions.

~~~mermaid
sequenceDiagram
    participant SF as Step Functions
    participant L as Request Lambda
    participant Q as Queue / Approval store
    participant W as External worker
    SF->>L: Invoke with task token
    L->>Q: Store request + protected token
    L-->>SF: Lambda invocation finishes
    SF->>SF: Task waits for callback
    Q->>W: Dispatch work
    W->>W: Process or await approval
    W->>SF: SendTaskSuccess / SendTaskFailure
    SF->>SF: Proceed to next state
~~~

A task token is a bearer credential: anyone holding the token with the right callback API permissions can attempt to complete the task. Never send tokens to browsers or end users. Never log tokens or place them in metrics, URLs, or public events.

The callback service must authenticate the caller, validate the approval/job ID, check authorization, and map the outcome back to the right task token. Tokens should be stored securely, encrypted at rest, and deleted after the task finishes.

## 7. Testing callback success and failure

For a callback task, test at least these scenarios:

1. Worker sends `SendTaskSuccess` with valid output.
2. Worker sends `SendTaskFailure` with a structured error/cause.
3. Worker never sends a callback and the Task times out.
4. Worker sends a callback with an invalid token.
5. Worker sends the callback twice.
6. Callback arrives after the execution has already ended.
7. Two workers attempt to complete the same approval concurrently.
8. Callback service saves the result successfully but fails before calling Step Functions.
9. Step Functions accepts the callback, yet the callback service loses the response.
10. Callback output exceeds payload limits or violates the schema.

### 7.1. Testing duplicate callbacks

Callbacks may be resent if a client misses the `SendTaskSuccess` response. The callback service must persist processing state and design idempotent actions.

Example approval state:

~~~text
approval_id
execution_arn
task_token_reference
status: PENDING | APPROVED | REJECTED | CALLBACK_SENT
decision_id
updated_at
~~~

When receiving a decision:

1. Check that the approval is still `PENDING`.
2. Save the decision and update status via conditional update/transaction.
3. Send the callback to Step Functions.
4. Record that the callback was sent, or handle the case where the token was already consumed.
5. If the process crashes between steps 2 and 3, a worker retry can resume sending the callback from the saved state.

Never mint a new task token when retrying a callback. Tokens are bound to one specific Task execution.

### 7.2. Heartbeats and worker liveness

If a task requires heartbeats, the worker must call `SendTaskHeartbeat` with the exact token before `HeartbeatSeconds` expires. Test:

- Worker is active and sends heartbeats regularly.
- Worker is deadlocked while the process remains alive.
- Heartbeat API returns a transient error.
- Worker sends a heartbeat for an expired token.
- Worker finishes after the heartbeat timeout has fired.

When a heartbeat times out, Step Functions marks the Task as timed out. The system must detect whether the worker is still running and prevent it from continuing side effects after the workflow entered compensation. Backend leases or cancellation flags can coordinate stopping in-flight work.

## 8. Testing callback token security

Tokens should not be used as business keys or displayed in reports. Store a controlled reference and bind the token to the execution ARN, approval ID, and deadline.

Security tests to include:

- Unauthorized users cannot retrieve tokens from APIs.
- An approval ID cannot be paired with another execution's token.
- Expired or already-consumed tokens cannot complete the task again.
- Tokens never appear in stdout, CloudWatch Logs, or tracing attributes.
- Tokens are never placed in URLs or query strings.
- Callback endpoints authenticate callers and prevent replays.
- The callback service holds only required callback permissions such as `states:SendTaskSuccess`, `states:SendTaskFailure`, and `states:SendTaskHeartbeat`; apply IAM conditions supported by the API and avoid granting state machine edit or Step Functions admin rights unnecessarily.

If a token leaks, treat it as a compromised credential. Restricting the callback service's IAM permissions and limiting Task lifetimes reduces blast radius.

## 9. Saga compensation: identifying what to compensate

Compensations run only for steps that produced side effects and must align with actual state.

Example:

| Forward action | Side effect | Compensation |
|---|---|---|
| Reserve inventory | Holds item quantity | Release reservation |
| Authorize payment | Creates payment authorization | Void authorization |
| Capture payment | Collects funds | Refund if business rules allow |
| Create shipment | Creates shipping order | Cancel shipment if provider supports it |
| Send email | Email already sent | Cannot retract; optionally send a correction notice |

Not every side effect is cleanly reversible. Compensation may establish a new business state, such as payment `REFUNDED`, instead of deleting payment history.

A workflow should persist each side effect's ID immediately after the forward step succeeds. Compensations use that ID to target the exact resource. Never look up objects to compensate using unstable attributes such as timestamps or log ordering.

### 9.1. Compensation ordering

In a sequential Saga, compensations typically run in reverse order of completed steps:

~~~text
Reserve inventory
    -> Authorize payment
        -> Create shipment (fails)

Compensation:
    Cancel shipment if partially created
    -> Void/refund payment
        -> Release inventory
~~~

Actual ordering depends on business relationships. For instance, you may need to cancel a shipment before refunding payment. Map out dependencies and provider states rather than reversing blindly.

Test failure points after every forward step:

- Reserve fails: must not release an uncreated reservation.
- Payment fails: release reservation if reservation succeeded.
- Shipment fails: compensate both payment and reservation.
- Notification fails: decide whether notification is mandatory or retried independently.
- Compensation fails: persist `COMPENSATION_REQUIRED` state and route to recovery.

## 10. Compensations must be idempotent

A compensation may be retried when an external API times out or a callback is replayed. Therefore, compensations must also be idempotent.

For example, calling `releaseReservation(reservationId)` twice must not double-release or corrupt inventory counts. The inventory system can return an already-released outcome if the reservation is already `RELEASED`.

Use a stable key for each compensating action:

~~~text
saga_id = order-1042
compensation_key = release-inventory:order-1042
resource_id = reservation-771
~~~

Persist compensation state:

~~~text
saga_id
step_name
compensation_key
resource_id
status: PENDING | RUNNING | SUCCEEDED | FAILED
attempt_count
last_error
updated_at
~~~

Use unique constraints or conditional updates so two workers cannot execute the same compensation simultaneously. If the provider supports idempotency keys, send the same key across every retry.

### 10.1. Java compensation handler

Example business interfaces:

~~~java
public interface InventoryClient {
    void releaseReservation(String reservationId, String idempotencyKey);
}

public interface CompensationStore {
    boolean claim(String compensationKey);
    void markSucceeded(String compensationKey);
    void markRetryableFailure(String compensationKey, String reason);
}

public final class ReleaseInventoryHandler {

    private final InventoryClient inventory;
    private final CompensationStore store;

    public ReleaseInventoryHandler(
            InventoryClient inventory,
            CompensationStore store) {
        this.inventory = inventory;
        this.store = store;
    }

    public void release(String sagaId, String reservationId) {
        String key = "release-inventory:" + sagaId;

        if (!store.claim(key)) {
            return; // Already completed or another worker holds ownership.
        }

        try {
            inventory.releaseReservation(reservationId, key);
            store.markSucceeded(key);
        } catch (RuntimeException error) {
            store.markRetryableFailure(key, error.getClass().getSimpleName());
            throw error;
        }
    }
}
~~~

This is a simplified example. In production, `claim` must distinguish between already succeeded, currently held by an active lease, and expired lease; a plain boolean is insufficient if callers need to handle distinct states. If inventory updates and compensation status share the same database, use a transaction. If calling an external provider, rely on idempotency keys and reconciliation when outcomes are uncertain.

Never mark a compensation as succeeded before the provider confirms it. If you record `SUCCEEDED` first and the process crashes before the side effect runs, the workflow skips compensating while the reservation remains active.

## 11. Testing compensation success and failure

Minimum test matrix:

| Scenario | Expected outcome |
|---|---|
| Forward step fails before side effect | Corresponding compensation is not invoked |
| Forward step succeeds, later step fails | Compensations run in designed order |
| Compensation succeeds | Records `SUCCEEDED` status |
| Compensation times out after provider executed | Retries with same idempotency key, does not double-compensate |
| Compensation returns transient error | Bounded retries |
| Compensation fails permanently | Manual recovery and alert |
| Compensation invoked twice | Business state unchanged after the first attempt |
| Two executions compensate the same resource | Only one compensating action commits |
| Worker dies after provider success before saving status | Retry/reconcile recognizes side effect already completed |
| One compensation in a chain fails | Clearly records which step still requires recovery |

Tests must assert both database state and provider call counts. Verifying only that `releaseReservation` was called is not enough without verifying the final business outcome.

## 12. Reconciling uncertain outcomes

A hard edge case occurs when the provider executes a side effect but the response is lost. For example, a payment provider captures funds, and Lambda times out before receiving the response. The workflow does not know whether payment succeeded or failed.

Never assume a timeout means the operation failed. Add a reconciliation step:

1. Generate a stable idempotency key before calling the provider.
2. Call the provider with that key.
3. If the response is clear, store the provider transaction ID and status.
4. If it times out, query the provider by idempotency key or transaction reference.
5. If it already succeeded, resume the workflow or run the appropriate compensation.
6. If no transaction exists, retry with the same key.
7. If status remains unclear, escalate to manual recovery instead of creating a new transaction.

Reconciliation is part of the workflow and must be tested. Simulating a lost response after a side effect is one of the most valuable fault injections.

## 13. Java unit tests for idempotency and compensation

Unit tests verify handler logic without starting Step Functions. Use JUnit 5 and Mockito to simulate inventory/payment providers and stores.

Example testing that compensation calls the provider only when claim succeeds:

~~~java
import org.junit.jupiter.api.Test;

import static org.mockito.Mockito.*;

class ReleaseInventoryHandlerTest {

    @Test
    void releasesInventoryWhenClaimSucceeds() {
        InventoryClient inventory = mock(InventoryClient.class);
        CompensationStore store = mock(CompensationStore.class);

        when(store.claim("release-inventory:order-1042"))
                .thenReturn(true);

        ReleaseInventoryHandler handler =
                new ReleaseInventoryHandler(inventory, store);

        handler.release("order-1042", "reservation-771");

        verify(inventory).releaseReservation(
                "reservation-771",
                "release-inventory:order-1042");
        verify(store).markSucceeded("release-inventory:order-1042");
    }

    @Test
    void skipsProviderWhenCompensationIsAlreadyClaimed() {
        InventoryClient inventory = mock(InventoryClient.class);
        CompensationStore store = mock(CompensationStore.class);

        when(store.claim("release-inventory:order-1042"))
                .thenReturn(false);

        ReleaseInventoryHandler handler =
                new ReleaseInventoryHandler(inventory, store);

        handler.release("order-1042", "reservation-771");

        verifyNoInteractions(inventory);
        verify(store, never()).markSucceeded(anyString());
    }
}
~~~

The second test is appropriate only if `claim=false` strictly means already completed or actively owned by another worker and the handler can safely skip. In real implementations, return explicit claim results such as `ALREADY_SUCCEEDED`, `CLAIMED_BY_OTHER`, or `LEASE_EXPIRED` so pending compensations are never accidentally skipped.

Add tests when the provider throws errors:

- Store records retryable failure state.
- Exception is rethrown so Step Functions sees the Task failed.
- Retries reuse the exact same idempotency key.
- Permanent errors are not retried infinitely.

## 14. Layered state machine testing

No single tool validates every aspect of a workflow. Use multiple test layers with clear scopes.

| Test layer | Tooling/approach | What it verifies |
|---|---|---|
| Java unit test | JUnit, Mockito, fake clock | Business logic, retry classification, idempotency, and compensation |
| ASL validation | Step Functions definition validation | State machine syntax and structure |
| State-level test | Step Functions TestState API | Single state with inputs and mock integrations |
| Local simulation | Step Functions Local or suitable emulator | Partial state transitions and control flow |
| AWS integration test | Real state machine in a test account | IAM, Lambda integration, callbacks, timeouts, and execution history |
| End-to-end test | Entry API/event through final business state | Full process behavior and real dependencies |

`TestState` lets you test a single state without running a full execution. Mock integrations can simulate responses/errors from supported service integrations. It does not replace integration testing of the full state machine.

Step Functions Local is useful for local simulation, though it lacks full parity with the live AWS service and may omit certain integrations or newer features. Never use local results as proof that IAM, callback tokens, heartbeats, or timeouts behave properly on AWS.

### 14.1. Validating ASL before execution

Before deploying, check the state machine definition via validation APIs/CLIs or IaC tools. Errors to catch:

- `StartAt` pointing to a nonexistent state.
- `Next` pointing to a nonexistent state.
- States missing required fields.
- Malformed `Retry` or `Catch` blocks.
- JSONPath expressions not matching inputs.
- `ResultPath` overwriting needed data.
- Wrong callback resource ARNs.
- Invalid task timeouts or heartbeats.

Structural validation does not prove Lambda payloads or business contracts are right. Test inputs/outputs separately for each Task.

### 14.2. TestState and mock integrations

With `TestState`, pass a state definition, input, and mock service integration to test:

- Task receives the expected payload.
- `ResultSelector` extracts the intended output slice.
- `ResultPath` places results in the right location.
- `Choice` takes the right branch.
- `Retry`/`Catch` react properly to mocked errors.
- State returns the expected output.

Mocks keep tests fast and deterministic. However, mocks do not prove real downstream services return the same schemas or error names. Add contract tests or integration tests against real dependencies in an isolated environment.

## 15. Integration testing with AWS Step Functions

A complete integration test can:

1. Deploy a test state machine and test Lambdas.
2. Attach an IAM role with only required permissions.
3. Construct input with a dedicated execution ID or test correlation ID.
4. Call `StartExecution`.
5. Poll `DescribeExecution` or execution history.
6. Verify final status and executed states.
7. Query the test database/provider sandbox to verify side effects.
8. Clean up test data after verification.

Never use real production payments, customers, or inventory in timeout/compensation tests. Use provider sandboxes, dedicated databases, or fault-injectable stubs.

Use a unique execution name per test run. Include correlation IDs in inputs to locate executions and logs. Never pass tokens or secrets in execution input.

With Standard workflows, execution history shows which states ran, how many retries occurred, and what errors fired. Logs and history may retain inputs/outputs depending on configuration; never place secrets or task tokens in broadly accessible data.

## 16. Fault injection for workflows

Fault injection introduces controlled failures to test system recovery. Use a test Lambda accepting scenario flags in test inputs or mock integrations to trigger failures such as:

~~~text
scenario=PAYMENT_THROTTLED_ONCE
scenario=PAYMENT_DECLINED
scenario=PAYMENT_SIDE_EFFECT_THEN_TIMEOUT
scenario=CALLBACK_NEVER_ARRIVES
scenario=CALLBACK_DUPLICATED
scenario=REFUND_TIMEOUT_AFTER_SUCCESS
scenario=RELEASE_INVENTORY_DENIED
~~~

Scenario flags must exist strictly in test environments and must never be enabled via public inputs in production.

Inject faults at every boundary:

- Before a side effect begins.
- After a side effect succeeds but before the response is recorded.
- After the callback service saves a decision but before calling Step Functions.
- After the callback is accepted but before the client receives the response.
- While a compensation is executing.
- After a compensation succeeds but before status is persisted.

These fault points expose gaps between systems that do not share a transaction.

## 17. Recommended test case suite

| ID | Scenario | Primary verification |
|---|---|---|
| WF-01 | Happy path | All states complete in the right order |
| WF-02 | Lambda transient error once | Retries and proceeds |
| WF-03 | Lambda exhausts retries | Catch transitions to right branch |
| WF-04 | Task timeout | Execution takes timeout branch or fails per policy |
| WF-05 | Callback success | Workflow continues past callback state |
| WF-06 | Callback failure | Catch handles callback error |
| WF-07 | Callback never arrives | Task times out per deadline |
| WF-08 | Late callback | Token rejected; no new side effects created |
| WF-09 | Duplicate callback | Single business decision committed |
| WF-10 | Missed heartbeat | Task times out per heartbeat policy |
| WF-11 | Payment timeout with unknown outcome | Reconciles before retrying or refunding |
| WF-12 | Shipment failure | Refunds/voids payment then releases inventory |
| WF-13 | Compensation error | Routes to manual recovery and alerts |
| WF-14 | Compensation invoked again | Idempotency preserves business state |
| WF-15 | Two workers compensate concurrently | Only one compensation commits |
| WF-16 | New execution reprocesses batch | Does not repeat already-completed side effects |
| WF-17 | IAM missing callback permissions | Failure detected and clearly audited |
| WF-18 | Invalid callback payload | Does not transition workflow to success |
| WF-19 | Execution stopped while waiting | Worker handles invalidated token safely |
| WF-20 | Secrets/tokens in logs | Zero sensitive credentials logged |

Not every test needs to run on every pull request. Split them into unit/state tests running frequently and integration/fault tests running in scheduled, nightly, or pre-release pipelines. Tests covering payments, tokens, and compensations should sit in release gates commensurate with risk.

## 18. Verifying execution history and business state

After every integration test, inspect:

- Which states started and finished.
- Whether state inputs/outputs match contracts.
- Retry counts and retry intervals.
- Error names, causes, and Catch outputs.
- Whether task token callbacks resumed the right state.
- At which layer a task timeout or heartbeat timeout fired.
- Which compensations ran and in what order.
- Whether final status is `SUCCEEDED`, `FAILED`, `TIMED_OUT`, or another expected state.
- Whether the database shows the right reservation/payment/shipment state.

Do not check only `DescribeExecution.status`. Cross-check the business store:

~~~text
Order: FAILED
Reservation: RELEASED
Payment: REFUNDED
Shipment: NOT_CREATED
Compensation:
  refund-payment: SUCCEEDED
  release-inventory: SUCCEEDED
~~~

This sample outcome reflects a shipment failure after payment was already captured. If the refund failed, the order should be in `COMPENSATION_REQUIRED` requiring operator intervention—never record it as `FAILED_CLEANLY`.

## 19. Avoiding flaky tests and isolating data

Asynchronous workflows easily cause flaky tests when tests sleep for a fixed duration and assume execution finished.

Do:

- Poll execution status with a deadline and short backoff.
- Wait on a specific state/condition rather than fixed sleeps.
- Use unique execution names, batch IDs, and correlation IDs per test.
- Create uniquely prefixed fixture data and clean up afterward.
- Never run parallel tests sharing order IDs, payment references, or reservation IDs.
- Use clock abstractions in Java when business logic computes deadlines.
- Use short timeouts in test state machines while keeping state structure equivalent to production.
- Log execution ARNs on test failures for investigation.

Polling must have an overall deadline. If the deadline expires before execution finishes, fail the test with the execution ARN and last observed state rather than hanging forever.

## 20. Pre-production testing workflow

1. **Define state machine and business invariants.** Document valid states for orders, payments, inventory, and shipments.
2. **Write unit tests for Java handlers.** Test input validation, error classification, idempotency, and compensation.
3. **Validate ASL.** Check state references, JSONPath, Retry/Catch, and callback resources.
4. **Test individual states.** Use `TestState` and mock integrations for payload/error branches.
5. **Test locally.** Use a local simulator for supported control flows.
6. **Deploy test stack.** Use isolated IAM roles, Lambdas, and sandbox databases.
7. **Test timeouts/callbacks.** Verify success, failure, heartbeats, duplicates, late callbacks, and invalid tokens.
8. **Inject faults.** Trigger errors before/after side effects and test reconciliation.
9. **Test compensations.** Verify ordering, idempotency, retries, and manual recovery.
10. **Cross-check business state.** Inspect the database and provider sandbox alongside execution history.
11. **Verify observability.** Confirm logs carry correlation IDs without tokens/secrets.
12. **Run regression and release.** Retain execution ARNs, test reports, and release IDs for traceability.

A workflow is ready only when both the happy path and critical failure branches yield deterministic outcomes. For timeouts and callbacks, prove the system handles late or duplicate responses safely. For compensations, prove side effects are undone once safely or escalated to observable manual recovery.

## 21. Self-check questions

- Why is testing each Lambda individually insufficient to verify a workflow?
- How do Lambda timeout and Step Functions Task timeout differ?
- What kind of failure does `HeartbeatSeconds` detect?
- Why does a timeout not prove a payment provider did not collect funds?
- In what order are `Retry` and `Catch` evaluated?
- How many total invocations can `MaxAttempts` equal to 2 produce?
- What role does a callback task token play, and why must it be protected like a credential?
- How do you test duplicate callbacks and late callbacks?
- Why do callback task tokens work only with Standard workflows?
- How does compensation differ from a transaction rollback?
- How do you ensure compensations are idempotent?
- When should a workflow reconcile instead of retrying immediately?
- What are the limitations of `TestState` and Step Functions Local?
- Why must integration tests check business state in addition to execution status?
- At which boundaries should you inject faults to uncover race conditions?
