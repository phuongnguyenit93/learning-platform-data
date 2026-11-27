# Pausing Workflows to Wait for Callbacks or Approvals

A serverless workflow can consist of steps spanning seconds, hours, or even days. Some steps must wait for a partner system to return a result, wait for a manager's approval, or wait for an external event before continuing. If you keep a Java function running and call `sleep()` to wait, the system wastes resources while idle, easily hits timeouts, and fails to recover cleanly when the execution environment is reclaimed.

Workflow orchestration solves this using a durable wait state. The workflow persists progress, pauses at a step, and resumes when it receives a callback, signal, or wait timeout. Java functions only execute during active processing steps; waiting time is managed by the workflow engine and state storage services.

This lesson explains how to design callbacks and approvals safely, how to correlate responses with the exact waiting workflow, and how to handle timeouts, duplicate callbacks, or late callbacks.

## 1. Pausing a workflow vs. keeping a function running

A workflow typically has states such as **RUNNING**, **WAITING**, **SUCCEEDED**, **FAILED**, or **CANCELLED**. Upon reaching a wait step, the orchestration engine saves the current state along with the data required to resume, and then releases the executing worker.

When a valid callback arrives, the engine transitions the workflow to a runnable state and launches the next step. There is no need to keep a Java thread, process, or function invocation alive throughout the wait period.

~~~mermaid
flowchart TD
    A["Start workflow"] --> B["Execute preparation step"]
    B --> C["Send request / create approval"]
    C --> D["Persist WAITING state"]
    D --> E{"Continuation event"}
    E -->|Valid callback| F["Verify and record outcome"]
    E -->|Expired| G["Timeout branch"]
    E -->|Cancelled| H["Cancellation branch"]
    F --> I["Run next step"]
    G --> J["Reject / retry / escalation"]
    H --> K["Terminate or compensate"]
    I --> L["Complete workflow"]
~~~

Each component's responsibility can be outlined as follows:

- **Workflow engine:** persists state, manages wait states, timeouts, and step ordering.
- **Java function:** executes short-lived tasks, dispatches outbound requests, validates callbacks, and runs business logic.
- **Callback endpoint:** receives responses from partners or the approval portal.
- **Database or state store:** stores approvals, correlation IDs, callback outcomes, audit logs, and outbox records when needed.
- **Queue/event bus:** durably transports callbacks or downstream tasks when the architecture uses asynchronous processing.

A wait state does not mean a function is hanging. The engine retains workflow progress; compute is provisioned only when the next step runs. Naming and pricing for wait states vary by provider, so verify wait-duration limits, concurrent waiting execution limits, and state storage costs.

## 2. Scenarios requiring callback waits

Common examples:

| Scenario | Callback sender | Outcome workflow needs to receive |
|---|---|---|
| Order approval | Manager via portal | APPROVED or REJECTED |
| Partner payment processing | Payment provider | Success, failure, or verification needed |
| External document processing | OCR or inspection service | Extracted result, confidence score, or error |
| Delivery | Logistics system | Picked up, in transit, delivered, or exception |
| Waiting for user input | App/web portal | Submitted data or expired |
| Waiting for manual inspection | Operations staff | Inspection outcome and reason |

A callback is a message signaling that a condition has occurred. It may arrive via an HTTP webhook, a queue message, a staff API, or an event from another service. The workflow needs to know which step and execution the callback belongs to, and whether it is still valid.

Never accept a callback carrying only a field like `approved=true` and trust its payload blindly. Authenticate the sender, bind it to the original request, verify permissions, and check the workflow's current state.

## 3. Two ways to correlate callbacks with workflows

### 3.1. Task token issued by the workflow engine

Some orchestration engines provide a task token or callback token when the workflow enters a callback wait step. The worker receives the token and passes it to the component responsible for completing the task. When a valid callback arrives, the integration service uses that token to report success or failure back to the engine.

High-level flow:

~~~mermaid
sequenceDiagram
    participant W as Workflow Engine
    participant F as Java Function
    participant P as Partner / Approver
    participant C as Callback API
    W->>F: Start wait step, issue task token
    Note over W: Task held in WAITING state
    F->>P: Send request and secure callback info
    P->>C: Send outcome with callback identifier
    C->>C: Authenticate sender and validate state
    C->>W: Send task success or task failure
    W->>W: Resume workflow
~~~

A task token typically grants permission to complete that exact waiting task. Anyone holding the token may be able to advance the workflow, so treat it as a bearer secret:

- Never write the token to logs, analytics, or error messages.
- Never embed the token directly in a URL that can appear in browser history, proxy logs, or referrers.
- Encrypt it at rest in the database and restrict read permissions.
- Transmit the token only over authenticated, encrypted channels.
- Bind the token to its corresponding workflow, task, tenant, and expiration.
- Delete or invalidate the token once the task completes or expires.

Not all engines use the same token mechanism, callback API, or expiration model. Some engines require workers to forward the token in a message; others provide direct integrations with queues or APIs. Follow the protocol of the platform you use.

### 3.2. Application-managed correlation ID

Another approach is generating a random callback identifier at the application layer, such as `approvalId` or `correlationId`. The workflow stores this ID in its state; the callback endpoint receives the ID and looks up the mapping record linking to the waiting workflow execution and step.

Example:

~~~text
workflow_id: order-2026-00421
step_id: manager-approval
approval_id: apv_7f1d...
tenant_id: tenant-42
status: WAITING
expires_at: 2026-12-02T10:00:00Z
~~~

A correlation ID locates the right execution, but by itself it does not prove the caller is authorized to approve. If the ID is guessable or leaks into logs, an attacker could attempt to inject callbacks into another workflow. You must also enforce caller authentication, resource authorization, and state validation.

Use an ID with enough randomness to prevent guessing, avoid embedding sensitive data in the ID, and do not treat the ID as a credential. If a callback secret is used as a bearer token, manage it like a task token: high entropy, protected storage, explicit expiration, and single-use enforcement.

### 3.3. Which approach to choose?

| Criterion | Task token | Correlation ID |
|---|---|---|
| Workflow binding | Managed directly by the engine | Application looks up mapping |
| Integration | Tied to workflow engine APIs | Works across multiple engines or callback services |
| Security | Token often grants task-completion authority | ID only locates the record; needs separate authentication and authorization |
| Callback state | Engine typically tracks task completion | Application must store state and deduplicate |
| Business customization | Follows engine protocol | More flexible for approvals, auditing, and multi-channel callbacks |

Both can be combined: expose an `approvalId` to the UI and audit logs, while keeping the task token securely in the backend. The approver only sees the approval ID; the callback service retrieves the encrypted token and submits the result to the workflow engine.

## 4. Designing human approval workflows

An approval workflow typically follows these steps:

1. The workflow creates an approval request and stores the payload to be reviewed.
2. The system notifies authorized approvers.
3. The workflow transitions to `WAITING_APPROVAL`.
4. The approver logs into the portal, reviews full details, and selects approve or reject.
5. The backend verifies permissions, persists the decision, and records an audit entry.
6. The callback service wakes the workflow with the outcome.
7. The workflow continues along the chosen branch.

~~~mermaid
sequenceDiagram
    participant O as Order Workflow
    participant D as Approval DB
    participant N as Notification Service
    participant U as Approver Portal
    participant C as Callback Service
    O->>D: Create WAITING approval
    O->>N: Send approvalId notification
    Note over O: Workflow pauses
    U->>D: Load request details
    U->>C: Submit approve/reject decision
    C->>D: Verify permissions and record decision
    C->>C: Create outbox callback
    C->>O: Resume workflow
    O->>O: Run selected branch
~~~

Email or chat notifications should contain only a link to the portal and a safe reference ID. Never allow users to approve merely by opening a public URL containing a task token. Approvers must sign in; the backend extracts identity from a verified session or token and verifies they are authorized to approve that request.

Registration and notification ordering matters. Create the approval record, link the correlation ID/task token, and enqueue the notification in an outbox before dispatching the request to the partner or approver. With task tokens, the engine's wait task must be initialized before the token is sent externally. With application-managed correlation IDs, if a callback might arrive before the workflow finishes entering its wait state, store the callback in an inbox pending matching and resume only after confirming the workflow is waiting at the right step. This prevents losing early callbacks.

Store at a minimum:

- Approval ID and workflow execution ID.
- Tenant, resource type, and resource ID.
- Assigned approver or authorized group.
- Actual actor who made the decision.
- Decision, reason, and timestamp.
- Current state, expiration time, and version.
- Audit trail for creation, viewing, delegation, approval, rejection, and expiration.

Never let the client submit `approverId` and trust it as the actual approver. The backend must derive identity from verified credentials. If a group of users can approve, define clearly who is eligible, whether one or multiple approvals are required, and whether two approvers can decide concurrently.

### 4.1. Approval, rejection, and requesting more information

Do not model every business outcome as an exception. `APPROVED`, `REJECTED`, and `NEEDS_INFORMATION` are valid workflow outcomes. The workflow can branch on the outcome:

~~~text
WAITING_APPROVAL
    |
    +-- APPROVED ----------> Continue order processing
    |
    +-- REJECTED ----------> Record reason and end
    |
    +-- NEEDS_INFORMATION -> Wait for additional data
    |
    +-- EXPIRED -----------> Remind / escalate / reject
~~~

Technical failures such as database unavailability or callback service timeouts should follow technical retry policies. An approver's rejection is a business outcome and must never be automatically retried as an infrastructure error.

## 5. What must a callback endpoint authenticate and validate?

A callback endpoint is a public HTTP surface or an interface called by external systems. Before resuming a workflow, the endpoint must verify:

1. **Sender authenticity:** verify webhook signatures, OAuth client credentials, mTLS, or the authentication mechanism supported by the partner.
2. **Integrity:** if using signatures, verify against the exact raw request body using the provider's exact algorithm.
3. **Timeliness:** validate timestamps, nonces, or replay-protection windows when supported by the protocol.
4. **Identifier:** determine which approval ID, task token, or correlation ID the callback belongs to.
5. **Authorization:** verify the caller is authorized to complete the task or the user has permission to approve the resource.
6. **State:** accept the callback only when the workflow/task is actively waiting for that outcome.
7. **Expiration:** reject or handle according to policy if the callback arrives after expiration.
8. **Payload:** validate schema, size limits, data types, and allowed values.

If callbacks arrive from a partner, IP allowlisting is only an auxiliary layer; IP checks never replace cryptographic signatures or identity verification. If callbacks come from an internal portal, enforce sessions, CSRF protection appropriate to browser authentication, and server-side authorization.

Never allow a callback payload to specify an arbitrary URL for the workflow to call next. That creates SSRF risks or turns the workflow into a proxy reaching internal addresses. Target URLs must come from trusted configuration and be checked against an allowlist.

## 6. Idempotency: handling duplicate callbacks

Callbacks can be redelivered when the sender misses a response, the callback service times out, or a queue redelivers a message. For example, an approver double-clicks a button; a partner retries the same webhook; or the callback service signaled the workflow but failed before returning 2xx to the caller.

Distinguish clearly between:

- **Delivery ID:** identifies a specific transmission attempt by the sender.
- **Event ID:** identifies the source event, usually stable across retries.
- **Correlation ID:** links the callback to a waiting workflow or step.
- **Idempotency key:** identifies the business operation that must execute only once.

Do not assume these four IDs are identical. Multiple deliveries may share the same event ID and idempotency key. One workflow may receive several distinct events during the same execution.

### 6.1. Callback states and conditional updates

An approval record can use the following states:

| State | Meaning |
|---|---|
| WAITING | Awaiting decision |
| APPROVED | Approved |
| REJECTED | Rejected |
| EXPIRED | Timed out / overdue |
| CANCELLED | Request cancelled |
| CALLBACK_PENDING | Decision saved, waiting to send callback to workflow |
| RESUMED | Workflow engine confirmed receipt of outcome |

State transitions must be atomic. For example, allow updates only from `WAITING` to `APPROVED` or `REJECTED`. Two concurrent callbacks must never both win.

Conceptual SQL statement:

~~~sql
UPDATE approvals
SET status = 'APPROVED',
    decision_by = :actor_id,
    decision_at = :now,
    version = version + 1
WHERE approval_id = :approval_id
  AND status = 'WAITING'
  AND expires_at > :now;
~~~

The application inspects the updated row count:

- One row: the decision was recorded.
- Zero rows: the approval does not exist, has expired, or already has another decision; read the current state to classify.
- More than one row: unique key assumption violated; treat as a data integrity error.

If the exact same callback is redelivered with the same event ID and identical decision, return the previously processed result. If a second callback carries a conflicting decision—for example, `APPROVED` first and `REJECTED` later—return a conflict or record a rejected event; never overwrite the initial decision.

### 6.2. Outbox so resume signals are never lost

There is a dangerous failure gap: the database commits `APPROVED`, but the callback service crashes before signaling the workflow engine. The approver sees success, while the workflow stays stuck in `WAITING`.

A transactional outbox resolves this by writing the decision and the pending callback record in the same transaction:

1. Update the approval from `WAITING` to `APPROVED`.
2. Insert an outbox event containing approval ID, workflow ID, task reference, and outcome.
3. Commit the transaction.
4. A publisher reads the outbox and sends the callback to the workflow engine.
5. Once the engine acknowledges, mark the outbox entry as sent and the approval as `RESUMED`.

If the publisher sends the callback successfully but crashes before marking the outbox entry, it will resend. Therefore, callbacks sent to the workflow engine must also be protected by single-use task tokens, idempotency keys, or the engine's duplicate-handling semantics.

True exactly-once execution across a database and a workflow engine cannot be achieved by a single local transaction alone. The practical goal is at-least-once delivery, durable state persistence, and safe duplicate handling.

## 7. Timeouts, heartbeats, and escalation

Every wait step must have a time limit. Otherwise, workflows can stay in `WAITING` indefinitely, consuming execution quotas or triggering stale work later.

A wait configuration should specify:

- Wait start timestamp.
- Absolute expiration timestamp (`expiresAt`).
- Maximum wait duration per policy.
- Whether reminders are sent and after what delay.
- Whether escalation to another approver occurs.
- Expiration outcome: auto-reject, auto-approve, cancel, or route to manual handling.
- Who is authorized to extend deadlines and extension limits.

Task timeouts, workflow timeouts, and callback API timeouts are three distinct concepts. A workflow can live for days while a task worker runs for seconds. Callback endpoints also need short timeouts so they do not hold HTTP connections open if the workflow engine or database degrades.

Some workflow engines provide heartbeats for callback-waiting tasks or long-running workers. A heartbeat signals that the worker is still alive and can extend the heartbeat timeout per policy. It does not replace durable wait states and does not mean keeping a function running continuously while waiting for human approval. Exact heartbeat accounting, task timeouts, and maximum durations depend on the engine.

Example policy:

~~~text
approval_timeout: 48 hours
reminder_after: 24 hours
escalate_after: 36 hours
on_expiry: REJECT
allow_extension: true
max_extension: 24 hours
~~~

These values are illustrative only. Deadlines must align with SLAs and business policies.

When a timeout occurs, the workflow must enter a deterministic branch: send a reminder, reassign approver, reject, cancel, or create a manual task. Never let a timeout degrade into a generic exception that causes endless workflow retries.

## 8. Handling races between callbacks, timeouts, and cancellations

A callback can arrive at the exact moment a workflow expires or a user cancels the request. Checking state and updating it in two separate operations allows both the callback and timeout handler to read `WAITING` and attempt to finish.

Use an atomic conditional state transition. For instance, the callback only updates when status is `WAITING` and `expires_at > now`; the timeout handler only updates when status is `WAITING` and `expires_at <= now`. A database transaction or conditional write ensures exactly one branch wins.

~~~mermaid
stateDiagram-v2
    [*] --> WAITING
    WAITING --> APPROVED: Valid callback before deadline
    WAITING --> REJECTED: Approver rejected
    WAITING --> EXPIRED: Deadline reached first
    WAITING --> CANCELLED: Request cancelled
    APPROVED --> RESUMED: Workflow receives callback
    REJECTED --> RESUMED: Workflow receives callback
    EXPIRED --> RESUMED: Workflow handles timeout
    CANCELLED --> [*]
    RESUMED --> [*]
~~~

If a callback arrives after `EXPIRED`, the application must enforce an explicit policy: reject the callback, route to a manual review queue, or start a new workflow. Never automatically flip `EXPIRED` to `APPROVED` simply because a callback arrived late.

If the workflow has already been cancelled, a late callback must not restart it unless an approved recovery procedure exists. Late callbacks can be recorded in audit logs for investigation. If an external party already performed a side effect, a compensating action may be necessary.

## 9. Java example: receiving an approval decision

The example below illustrates the structure of a callback handler using records and switch expressions (Java 17+). Repositories and workflow ports are application-implemented adapters. `recordDecisionAndOutbox` must update the approval state and insert the outbox entry in the same transaction.

~~~java
public enum ApprovalDecision {
    APPROVED,
    REJECTED
}

public record ApprovalCommand(
        String approvalId,
        ApprovalDecision decision,
        String reason
) {}

public record ApprovalResult(
        String status,
        boolean accepted
) {}

public interface ApprovalRepository {
    Optional<Approval> find(String approvalId);
    DecisionResult recordDecisionAndOutbox(
            String approvalId,
            String actorId,
            ApprovalDecision decision,
            String reason
    );
}

public ApprovalResult decide(
        ApprovalCommand command,
        AuthenticatedPrincipal principal) {

    Approval approval = approvalRepository.find(command.approvalId())
            .orElseThrow(() -> new NotFoundException());

    authorization.requireCanApprove(principal, approval);

    DecisionResult result = approvalRepository.recordDecisionAndOutbox(
            approval.id(),
            principal.subject(),
            command.decision(),
            command.reason()
    );

    return switch (result) {
        case RECORDED -> new ApprovalResult("CALLBACK_PENDING", true);
        case SAME_DECISION_ALREADY_RECORDED ->
                new ApprovalResult("CALLBACK_PENDING", true);
        case CONFLICT -> new ApprovalResult("CONFLICT", false);
        case EXPIRED -> new ApprovalResult("EXPIRED", false);
    };
}
~~~

`DecisionResult`, `Approval`, `AuthenticatedPrincipal`, repository, and authorization service are illustrative types to be defined by the application. `recordDecisionAndOutbox` must re-verify tenant, assigned approver, version, `WAITING` state, and expiration inside the same transaction so permissions or state cannot change between read and write. Notice that the example does not dispatch the callback directly inside the HTTP handler; a background publisher reads the outbox and resumes the workflow. That lets the endpoint respond quickly once the decision is durably persisted.

For partner callbacks, the handler must verify signatures and event IDs before invoking similar logic. For workflow engine task tokens, the backend looks up the token linked to the approval ID and reports task success/failure using the engine's official API. Never let the approver's browser hold the raw token directly.

## 10. Callback payloads and contract versioning

Callback payloads should be small, explicit, and versioned. Do not resend entire business entities if the workflow can read the latest state from the canonical store. Conceptual payload:

~~~json
{
  "eventId": "evt-98a1",
  "eventType": "approval.decided",
  "schemaVersion": 1,
  "approvalId": "apv-7f1d",
  "workflowId": "order-2026-00421",
  "correlationId": "order-2026-00421:manager-approval",
  "decision": "APPROVED",
  "occurredAt": "2026-12-01T09:15:00Z"
}
~~~

Workers must verify:

- `schemaVersion` is supported.
- `eventType` matches the expected callback type.
- `approvalId` maps to the expected workflow and tenant.
- `correlationId` points to the active wait step.
- `eventId` has not yet been processed, or was processed with the same outcome.
- `occurredAt` and callback expiration satisfy policy.

When evolving schemas, support older versions during a transition window or provide explicit migration steps. Never interpret a missing field using a dangerous default—such as treating a missing `decision` as `APPROVED`.

## 11. Monitoring waiting workflows and operability

Workflows waiting for callbacks can live much longer than compute steps. Dashboards and operational tooling are needed to locate waiting executions, see who or what they are waiting on, and check when they expire.

Useful metrics:

- Count of workflows in each wait state.
- Age of wait states and count of workflows nearing expiration.
- Latency from request dispatch to callback receipt.
- Rates of valid, duplicate, invalid-signature, and late callbacks.
- Pending approvals by tenant, approver, and group.
- Reminder and escalation counts.
- Unsent or failing outbox event counts.
- Callbacks failing to match any workflow/task.
- Workflows stuck beyond SLA thresholds.
- Timeout, cancellation, and manual intervention rates.

Logs should include workflow ID, step ID, approval ID, correlation ID, event ID, and verification outcome. Never log task tokens, secrets, bearer tokens, or sensitive dossier fields. Use trace/correlation IDs to connect logs across functions, callback services, databases, and the workflow engine.

Operational runbooks should support inspecting workflow details, resending outbox callbacks, extending approval deadlines when permitted, or terminating stuck workflows. Every manual action must be authenticated, authorized, and audited.

## 12. Testing callbacks and approvals

Do not test only the happy path. Verify:

1. Valid callback arriving while the workflow is waiting.
2. Callback arriving before the wait state is registered.
3. Duplicate callback with the same event ID and identical outcome.
4. Duplicate callback carrying a conflicting decision.
5. Callback with an invalid signature or out-of-window timestamp.
6. Unauthorized user attempting to approve.
7. Callback belonging to a different tenant or workflow.
8. Callback arriving after the approval has expired.
9. Callback arriving concurrently with timeout or cancellation.
10. Database commit succeeding while the callback publisher crashes.
11. Workflow engine receiving the callback while the publisher fails before marking the outbox.
12. Approver clicking twice or two approvers deciding simultaneously.
13. Workflow being cancelled while a callback is in flight.
14. Callback payload carrying an unsupported schema version.
15. Workflow waiting longer than expected and triggering reminders/escalations.

Use a simulated clock to test timeouts without waiting in real time. Use concurrency tests to verify conditional updates allow only one decision to win. In integration tests, verify expired callback tokens, duplicate callbacks, and how the engine reports task completion.

## 13. Process for designing a safe wait state

1. **Identify the continuation condition.** Is the workflow waiting on a partner callback, queue event, or human decision?
2. **Choose the correlation mechanism.** Use an engine-issued task token or an application-managed correlation ID.
3. **Persist state durably.** Record workflow ID, step ID, tenant, expiration, status, and continuation data.
4. **Secure the callback.** Authenticate callers, verify signatures/tokens, enforce authorization, and validate schemas.
5. **Design idempotency.** Use event IDs and conditional state transitions to handle duplicates.
6. **Design timeouts.** Configure expiration, reminders, escalations, and expiry branches.
7. **Resolve races.** Define precedence between callbacks, timeouts, and cancellations via atomic updates.
8. **Guarantee resume delivery.** Use an outbox or durable retry mechanism when signaling the workflow engine.
9. **Monitor operations.** Track wait times, late callbacks, duplicates, and stuck workflows.
10. **Test failure modes.** Simulate duplicate callbacks, malformed callbacks, crashed workers, and cancelled workflows.

A well-designed wait state has clear identifiers, deadlines, access controls, observable state, and error recovery paths. A callback is merely a signal to advance the workflow; the authoritative decision must still be verified and recorded in the system of record.

## 14. Self-check questions

- Why should `sleep()` not be used to wait for a callback inside a Java function?
- How do durable wait states free up compute and enable workflow recovery?
- How does a task token differ from a correlation ID?
- Why must a task token be protected like a bearer secret?
- Where must approvers be authenticated and authorized?
- How do you prevent duplicate callbacks from applying the same decision twice?
- What failure gap between the database and workflow engine does a transactional outbox close?
- What should happen when a callback arrives concurrently with a timeout or cancellation?
- Why should a late callback not automatically reopen an expired workflow?
- Which metrics help detect workflows waiting too long or stuck?

Pausing a workflow to wait for a callback or approval is a business state with its own lifecycle. Persist waiting state durably, authenticate every continuation signal, handle duplicates via idempotency, and define explicit timeouts. Doing so lets workflows wait for extended periods without keeping functions running continuously, while remaining recoverable when callbacks arrive late or systems fail.
