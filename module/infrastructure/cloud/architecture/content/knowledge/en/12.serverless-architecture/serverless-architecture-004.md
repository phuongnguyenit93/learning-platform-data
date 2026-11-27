# Orchestrating Processes with Workflow Services

In a serverless architecture, a business process rarely ends within a single function invocation. For example, when a customer books a room, the system may need to check availability, place a hold, authorize payment, record the booking, send notifications, and update analytics. Each step may run in a different service with its own execution time and failure modes. If a step times out after already completing its work, the system must still determine the outcome and decide whether to retry or roll back.

A **workflow service** provides a mechanism to define and orchestrate multi-step processes, typically as a state machine or workflow definition. It tracks execution state, invokes functions or other services, waits for events, handles timeouts/retries, branches logic, and records outcomes. This keeps orchestration logic cleanly separated from the business code of individual functions.

This lesson belongs to the **Serverless Architecture** chapter of the **CLOUD_ARCHITECTURE** module. The focus is on choosing the right orchestration model, designing recoverable processes, protecting data and identities, and evaluating reliability, scalability, cost, and operational effort through a Well-Architected lens.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Explain the role of a workflow engine in serverless architecture and distinguish orchestration from choreography.
2. Model business processes into states, tasks, choices, waits, parallel branches, timeouts, and error paths.
3. Design bounded retries, idempotency, compensation, and handling of indeterminate outcomes.
4. Choose how to store state/payloads and control duration, size limits, and recoverability.
5. Handle long-running processes, schedules, callbacks, and human approvals.
6. Secure workflows with IAM, tenant isolation, secrets, encryption, and data policies.
7. Observe workflows end-to-end, test failure paths, and estimate costs across state transitions, compute, and integrated services.

## 2. What Problems Do Workflow Services Solve?

### 2.1. Stateful Multi-Step Orchestration

A workflow may combine synchronous and asynchronous steps:

- Call a function to validate input data.
- Call an API or service to reserve a resource.
- Wait for an external provider's response.
- Branch based on business conditions.
- Execute multiple independent tasks in parallel.
- Wait for a user or approver decision.
- Retry transient failures and execute compensation when the business process cannot proceed.
- Persist the final outcome and emit a completion event.

If you code the entire flow inside one long function, that function must hold state in memory and manually manage timeouts, retries, scheduling, and step results. In serverless, a single execution faces strict duration limits, processes can be terminated, and requests can be redelivered. A workflow engine handles stateful coordination so each step executes within its own duration and responsibility boundary.

### 2.2. Booking Flow Example

~~~mermaid
flowchart TD
    START[Receive booking request] --> VALIDATE[Validate data]
    VALIDATE --> HOLD[Place time-limited hold]
    HOLD --> AVAILABLE{Hold succeeded?}
    AVAILABLE -->|No| REJECT[Reject booking]
    AVAILABLE -->|Yes| PAY[Authorize payment]
    PAY --> PAID{Payment confirmed?}
    PAID -->|Yes| CONFIRM[Confirm booking]
    PAID -->|No| RELEASE[Release hold]
    CONFIRM --> NOTIFY[Send notification]
    RELEASE --> FAILED[Mark failed / reconcile]
    NOTIFY --> DONE[Completed]
~~~

The workflow describes **orchestration sequence and branching decisions**. Hold rules, booking ownership, and payment states still belong to their respective domain services. A workflow engine does not automatically turn operations across multiple databases into a single ACID transaction.

### 2.3. A Workflow Engine Is Neither a Queue Nor a Function

| Component | Primary role | Example responsibilities |
|---|---|---|
| **Function / serverless compute** | Execute a single unit of work | Pricing calculation, rule validation, data transformation |
| **Queue / message broker** | Buffer and distribute messages, decoupling producers from consumers | Accept email jobs, process background work at worker pace |
| **Event bus** | Route events to subscribers | Broadcast `BookingConfirmed` to multiple consumers |
| **Workflow service** | Track multi-step progress and coordinate state | Hold → pay → confirm → compensate if needed |
| **Database / business state store** | Store authoritative business data | Bookings, payments, inventory |

A workflow may use queues or event buses for asynchronous steps, but these components have different semantics. A queue holds messages for consumers to process; a workflow maintains the context and progress of a single process execution.

## 3. Orchestration vs. Choreography

### 3.1. Orchestration: One Coordinator Manages Sequence

In orchestration, a workflow engine or orchestrator determines the next step, invokes the corresponding service, and records execution state.

~~~mermaid
sequenceDiagram
    participant Client
    participant W as Workflow
    participant A as Availability
    participant P as Payment
    participant B as Booking
    Client->>W: Start booking workflow
    W->>A: Hold availability
    A-->>W: holdId
    W->>P: Authorize payment
    P-->>W: Authorized
    W->>B: Confirm booking
    B-->>W: Confirmed
    W-->>Client: Workflow completed
~~~

**Advantages:** clear visibility into the overall flow, centralized ordering and state; straightforward expression of timeouts, error paths, approvals, and wait states.

**Trade-offs:** the workflow definition becomes an artifact to manage; contract changes or new steps require updating the workflow. If the orchestrator directly handles every detail across every service, it can become a coupling bottleneck and overly complex coordinator.

### 3.2. Choreography: Services React to Events

In choreography, services publish and consume events. No central workflow engine owns the entire sequence; each service executes its logic upon receiving relevant events.

~~~mermaid
flowchart LR
    BOOK[Booking Service] -->|BookingRequested| BUS[(Event Bus)]
    BUS --> AV[Availability Service]
    AV -->|AvailabilityHeld| BUS
    BUS --> PAY[Payment Service]
    PAY -->|PaymentAuthorized| BUS
    BUS --> BOOK2[Booking Service]
    BOOK2 -->|BookingConfirmed| BUS
    BUS --> NOTIFY[Notification Service]
~~~

**Advantages:** services avoid direct point-to-point calls, subscribers can scale independently, and the model aligns well with event-driven architecture.

**Trade-offs:** harder to view overall progress from one place; tracing, duplicate events, out-of-order events, timeouts, and compensation are scattered across services. A business flow with too many chained reactive events becomes hard to reason about and operate.

### 3.3. Comparison and Choosing the Right Approach

| Criterion | Orchestration | Choreography |
|---|---|---|
| Where progress is managed | Workflow engine/orchestrator | Distributed across producers/consumers |
| Progress observability | Centralized execution history | Requires correlation and telemetry aggregation across services |
| Coupling | Workflow depends on each activity's contract | Services depend on event schemas/semantics |
| Long waits / approvals | Expressed directly in the workflow | Requires custom state storage and callback/event handling |
| Simple flows, fan-out | Usable, though a workflow may be overkill | Often well suited |
| Multi-branch flows and compensation | Easy to express ordering and compensation results | Hard to coordinate when state is distributed |
| Risk | Orchestrator becomes a coupling point | Event chains become hard to trace and terminate cleanly |

Neither model is universally better. They can be combined: a workflow orchestrates steps with strict ordering and state transitions, while a final step emits domain events so independent consumers handle notifications, analytics, or projection updates.

## 4. Modeling Workflows as State Machines

### 4.1. States, Transitions, and Tasks

A state machine defines states and transition rules. For each state, clarify:

- Does it perform work, or merely represent a wait or branch?
- What are its inputs/outputs, and do they have schemas and size limits?
- Where are success/failure conditions evaluated?
- What timeouts, retries, and error types can it handle?
- Does the state have side effects; is re-running it safe?
- Are transitions recorded for recovery and observability?

Common state types (exact names vary by workflow engine):

| State type | Role | Example |
|---|---|---|
| **Task** | Invoke a function, service, or activity | Reserve room, authorize payment |
| **Choice / condition** | Branch based on input/result | Continue if available, reject if sold out |
| **Wait / timer** | Pause until a timestamp or duration | Wait up to 15 minutes for payment |
| **Parallel** | Run multiple independent branches | Send email and update analytics |
| **Map / fan-out** | Iterate over a list of items | Validate multiple legs or line items |
| **Pass / transform** | Forward or reshape data | Normalize payload |
| **Success / fail** | Terminate successfully or in failure | Booking confirmed or rejected |

### 4.2. Business State vs. Workflow Execution State

The workflow engine may report an execution as `RUNNING`, `SUCCEEDED`, `FAILED`, or `TIMED_OUT`. Meanwhile, the Booking service may store the booking as `PENDING`, `CONFIRMED`, `CANCELLED`, or `RECONCILING`. These two state models relate to each other but must not be conflated.

For example, a workflow timeout while calling Payment does not prove the payment failed. The booking may transition to `RECONCILING` while the workflow triggers a reconciliation step. Never automatically mark a booking `FAILED` solely because the orchestrator timed out.

### 4.3. Defining Conditional State Transitions

Avoid vague states like `DONE` when it is unclear which step succeeded. Record explicit semantics:

~~~text
PENDING
  -> HOLD_REQUESTED
  -> HELD
  -> PAYMENT_PENDING
  -> PAYMENT_AUTHORIZED
  -> CONFIRMATION_PENDING
  -> CONFIRMED

Error branches:
  -> REJECTED (preconditions not met)
  -> COMPENSATING (compensation in progress)
  -> CANCELLED (rolled back per policy)
  -> RECONCILING (external outcome indeterminate)
~~~

Workflows should define clear terminal transitions, along with paths for human intervention rather than keeping executions running indefinitely.

## 5. Designing Retries, Timeouts, and Idempotency

### 5.1. Transient Errors vs. Business Errors

Not every error should be retried:

| Error type | Example | Typical appropriate behavior |
|---|---|---|
| Transient network/service error | Connection reset, temporary 503 | Bounded retries with backoff |
| Overload/rate limit | HTTP 429 or service quota | Respect `Retry-After`, cap concurrency |
| Data/validation error | Check-out date before check-in | Do not retry; return business error |
| Permission error | Missing IAM or tenant permission | Do not retry indefinitely; alert and fix permissions |
| Business conflict | Slot just reserved by someone else | Branch or terminate per business rules |
| Indeterminate outcome | Timeout after external service may have committed | Reconcile/query before deciding to retry |

### 5.2. Exponential Backoff and Jitter

A straightforward policy uses exponentially increasing wait times, capped attempts, and jitter so multiple executions do not retry in lockstep.

~~~text
delay(attempt) = min(maxDelay, baseDelay * 2^(attempt - 1))
actualDelay = delay(attempt) + randomJitter
~~~

For example, `baseDelay` of 1 second and `maxDelay` of 16 seconds yield approximate delays of 1, 2, 4, 8, 16 seconds before adding jitter. These numbers are illustrative. Choose intervals based on dependency SLAs, workflow deadlines, and backlog capacity.

Retries must be **bounded** in both attempt count and total duration. If every layer (client, gateway, workflow, SDK, service) retries independently, actual calls multiply. Define a cohesive end-to-end retry strategy to prevent retry storms.

### 5.3. Per-Step Timeouts Must Fit Together

Task timeouts should reflect expected execution time, tail latency, function/API limits, and the overall workflow deadline. The sum of step durations, waits, retries, and compensation must stay within the business objective.

If a workflow has a 20-minute deadline, do not let individual tasks retry for 15 minutes without leaving time for compensation or notifications. Propagate deadlines or remaining time to activities when supported by the platform.

### 5.4. Idempotency Protects Side Effects

A workflow engine may redeliver a task after a timeout or crash recovery. Any task that transfers funds, creates orders, or sends notifications must tolerate repeated execution.

For instance, `paymentReference` is generated once per payment intent and reused across all retries:

~~~json
{
  "bookingId": "booking_913",
  "paymentReference": "payref_7f91",
  "amountMinor": 1500000,
  "currency": "VND"
}
~~~

The Payment Service must persist and validate the reference scoped to the tenant/merchant, returning the consistent logical result on duplicate requests. Idempotency keys need retention long enough to cover retries and reconciliation; avoid using the workflow execution ID as the sole key if multiple executions can represent the same business intent.

**End-to-end exactly-once** generally cannot be assumed from workflow or broker retries alone. The standard pattern is at-least-once delivery + idempotent operations + deduplication + reconciliation.

## 6. Compensation and Sagas for Multi-Service Processes

### 6.1. Distributed Transactions Do Not Auto-Rollback

Inside a single database, a transaction can roll back uncommitted changes. In a workflow calling Availability, Payment, and Booking, however, each service commits its own data. If the final step fails, the workflow engine cannot automatically undo prior steps by rolling back other services' databases.

A **Saga** breaks a long-lived process into local transactions. When the process cannot continue, the system runs predefined **compensating actions** to return the business domain to an acceptable state.

| Completed step | Possible compensating action | Key considerations |
|---|---|---|
| Place hold | Release hold | Hold may already have expired or transitioned state |
| Authorize payment | Void authorization | Different from a refund after capture |
| Capture payment | Refund | Refunds can be asynchronous and may fail |
| Create booking | Cancel booking per policy | May require notification, records, and audit trail |
| Schedule delivery | Cancel or initiate recall | Not all physical side effects are reversible |

Compensation does not necessarily erase history; many domains require recording cancellation/refund states for auditing and reconciliation.

### 6.2. Booking Saga Example

~~~mermaid
flowchart TD
    START[Start] --> HOLD[Hold availability]
    HOLD --> HOK{Hold ok?}
    HOK -->|No| REJECT[Reject booking]
    HOK -->|Yes| AUTH[Authorize payment]
    AUTH --> AOK{Authorization ok?}
    AOK -->|No| REL[Release hold]
    AOK -->|Yes| CONF[Confirm booking]
    CONF --> COK{Confirm ok?}
    COK -->|Yes| EVENT[Publish BookingConfirmed]
    COK -->|No / uncertain| COMP[Void authorization]
    COMP --> REL
    REL --> FAIL[Close or reconcile]
    EVENT --> DONE[Completed]
~~~

This diagram must be refined to match the payment provider's exact semantics. If Payment times out and it is unclear whether authorization succeeded, do not run a blind void; query by `paymentReference` first. If voiding fails, record a reconciliation state and alert operators.

### 6.3. Compensation Can Fail

The workflow must define:

- Retry counts and deadlines for each compensating action.
- Which actions are safe to retry and which idempotency keys apply.
- Persisted states when compensation succeeds, fails, or is indeterminate.
- Evidence, logs, and correlation IDs for support reconciliation.
- Alerting and manual intervention procedures.

Never mark an execution as "rolled back" while a compensating action remains unconfirmed.

## 7. Storing State and Passing Payloads Between Steps

### 7.1. What Data Belongs in State?

A workflow must carry enough information to decide the next step. However, avoid stuffing full business records or large files into execution state when the service imposes size limits, storage costs, or broad access permissions.

Prefer:

- Stable identifiers: `bookingId`, `tenantId`, `paymentReference`, object keys.
- Concise states and outputs needed by subsequent steps.
- Version or sequence numbers when guarding updates.
- Correlation IDs and trace context for observability.
- Minimal sensitive metadata; pass references to protected secret/data stores rather than embedding secrets in state.

For large payloads, store data in controlled object storage or databases and pass references, versions, and necessary access permissions. Handle cases where the referenced object is deleted, modified, or its access expires mid-workflow.

### 7.2. State Machines Are Not Business Databases

Execution history may capture task inputs and outputs depending on platform settings. While helpful for debugging and auditing, workflow history should not become the system of record for bookings, payments, or inventory.

Business databases must remain the authoritative source holding unique constraints, audit trails, and lifecycle policies. Workflow state tracks process progress and can be reconstructed or reconciled against owning services when needed.

### 7.3. Controlling Sensitive Data

Never put passwords, access tokens, PAN/card details, secrets, or unnecessary personal data into execution inputs, events, logs, or error messages. If the workflow service automatically records history, verify:

- What content is stored, for how long, and who can read it.
- What encryption, redaction, or logging limits apply.
- Which region hosts backups/history and whether data residency rules are met.
- Which payloads operators can view in the console.
- How history, events, and replicas are handled upon data deletion requests.

## 8. Long-Running Processes, Wait States, and Callbacks

### 8.1. Long-Running Workflows

Some business processes span minutes, hours, or days:

- Waiting for payment or refund confirmation.
- Waiting for users to submit supporting documents.
- Waiting for administrator approval.
- Scheduling actions at future timestamps.
- Waiting for shipping or document verification partners.

Never keep a function running and sleeping for long periods. A workflow engine can persist wait state, release compute, and resume when a timer expires or a callback arrives.

### 8.2. Callbacks and Task Tokens

A common pattern: the workflow sends a request to an external system alongside a generated correlation/task token. When ready, the external system invokes a callback with the valid token to resume execution. Implementation details vary by workflow engine.

What to protect:

- Tokens must be unpredictable, time-bounded, and bound to the specific execution/tenant.
- Callbacks must authenticate callers via signatures or mTLS per the trust model.
- Duplicate or late callbacks must be handled idempotently.
- Never leak tokens in public URLs/logs or let a callback complete another tenant's task.
- Enforce callback timeouts with an explicit path when no response arrives.

### 8.3. Human Approvals

Manual approvals require authorization, auditing, and validation when resuming the workflow. For example, a large refund request may await manager approval:

1. Workflow creates an approval request with review details.
2. System notifies the authorized group.
3. Approver signs in and authenticates; backend verifies permission for that tenant/transaction.
4. Decision and actor are audit-logged.
5. Valid callback or signal resumes the state machine.
6. If expired, workflow transitions to an expired state or triggers a defined escalation path.

Never treat possessing a secret link alone as sufficient proof that the clicker is authorized to approve.

## 9. Workflow Types, Durations, and Execution Limits

Serverless workflow engines typically offer multiple execution modes. Names and limits vary by provider, but common trade-offs include:

| Execution mode | Characteristics | Best suited when |
|---|---|---|
| **Standard / durable workflow** | Persists detailed state and history; suited for long processes or durable auditable orchestration | Bookings, onboarding, approvals, multi-step processes |
| **Express / high-throughput workflow** | Optimized for high volume and short duration; history/retry/durability semantics may differ | Ingestion, short event processing, high-scale fan-out |
| **Synchronous workflow invocation** | Caller waits for the workflow run result within service limits | APIs needing a direct response from a short workflow |
| **Asynchronous workflow invocation** | Caller receives an execution reference and tracks progress later | Background and long-running processes |

Never assume a synchronous workflow can wait indefinitely or that all workflow modes provide the same exactly-once semantics. Before choosing, check hard limits on maximum duration, transition count, input/output size, concurrency, history retention, execution rate, and pricing for the specific product.

## 10. Security and Responsibility Ownership

### 10.1. Identity and Least Privilege

Workflows often hold permissions to call multiple services. Never assign one execution role with administrative access across the entire system.

- Separate roles/permissions per workflow or task when supported by the platform.
- Grant only the required permissions to invoke functions, publish messages, read objects, and update state.
- Separate permissions to start workflows from permissions to read execution history or mutate state.
- Enforce tenant/resource checks in authorization logic; a workflow execution ID does not replace authorization.
- Manage secrets via a secret manager with rotation; never hard-code them into workflow definitions.
- Validate permissions on callbacks, human approvals, and integration accounts.

### 10.2. Networking and Dependencies

A workflow service may invoke internal cloud services, private endpoints, or public APIs. Evaluate:

- How does the workflow engine connect to VPC/private networks?
- Do functions/activities require NAT, private endpoints, or security groups?
- Where do partner callbacks enter, and how are they authenticated and rate-limited?
- Do egress and inter-region transfers introduce cost or data constraints?
- Do activity timeouts/connection pools align with workflow deadlines?

A task failing due to a missing route to a private database must not be retried endlessly as a transient network glitch. Distinguish configuration errors from transient failures.

### 10.3. Data Governance

Workflows can touch data across multiple regions and services. Classify payloads, identify where execution history, events, backups, and logs are stored, and govern operator and third-party access. When residency or sovereignty rules apply, verify not just the database region, but also workflow history, queues, event buses, observability tools, and callback endpoints.

## 11. Observing and Operating Workflows

### 11.1. Tracking by Workflow and Business Transaction

Useful signals:

| Category | Metrics / logs | Purpose |
|---|---|---|
| Throughput | Started/completed/failed/timed-out executions | Track workflow volume and outcomes |
| Duration | End-to-end duration, task duration, wait time | Identify slow steps |
| Retries | Retry count, backoff duration, error types | Detect flaky dependencies or overly aggressive policies |
| Backlog | Pending workflows, callback age, schedule delay | Spot stalled processes |
| Compensation | Compensation count, failure rate, compensation age | Surface transactions needing intervention |
| Dependencies | Error rate/latency per function, DB, broker, external API | Pinpoint failure sources |
| Cost | Transition count, invocations, duration, storage/history | Track cost per business flow |
| Security | Unauthorized starts/callbacks, history access, policy changes | Detect anomalous access |

Every business flow should carry a correlation ID or business transaction ID across the workflow and all services. Avoid using the execution ID as the sole business identifier, since one business request may spawn multiple executions due to retries, restarts, or sub-flows.

### 11.2. Actionable Alerts

Examples:

- Workflow failure rate exceeds threshold: group by error type and dependency before paging.
- Executions stuck waiting too long: inspect callbacks, partners, and task tokens.
- Compensation failed: page at high severity and trigger reconciliation workflow.
- DLQ growing rapidly: inspect consumers, schemas, or permissions.
- Transition/invocation cost spiking anomalously: check for loops, unbounded retries, or duplicate events.
- Workflow exceeds business deadline: identify the blocked step and responsible owner.

### 11.3. Runbooks

A runbook should specify:

1. How to locate the execution and associated business transaction.
2. How to inspect state/history and errors without exposing sensitive payloads.
3. How to verify true state in Booking, Payment, and Availability services.
4. Conditions under which retrying, resuming, redriving, or triggering compensation is permitted.
5. How to avoid re-executing side effects that already succeeded.
6. How to escalate and record reconciliation outcomes.

Never manually edit execution state or restart a workflow without first verifying the state of side effects in the owning services.

## 12. Cost and Performance

### 12.1. Cost Components

Workflow costs can depend on:

- Execution starts.
- State transitions or requests to the workflow engine.
- Function/activity invocations and compute duration.
- Wait time or held resources, if billed by the service model.
- Storage for execution history, logs, events, and payloads.
- Message brokers, databases, API gateways, NAT/egress, and external services.

An unbounded retry loop degrades reliability while driving up costs. Design explicit retry caps, deadlines, maximum iteration limits, and payload size bounds.

### 12.2. Latency and Transition Count

Every state transition or service call adds overhead. If a process performs only a minor calculation, wrapping it in a workflow adds unnecessary latency and cost. Conversely, cramming 30 unrelated operations into one function makes failures hard to recover from and prone to timeouts.

Group small, pure-compute steps inside a single activity when separate retry or transaction boundaries are unnecessary. Split steps when they involve distinct side effects, dependencies, waits, compensation, or independent observability.

### 12.3. Fan-Out and Concurrency

Parallel/map states can launch large numbers of activities. Cap concurrency, batch sizes, and downstream rates so databases or external APIs are not overwhelmed. If the workflow engine enforces execution or transition quotas, verify headroom and throttling behavior.

## 13. Testing and Releasing Workflows

### 13.1. State-Based and Failure-Scenario Testing

Do not test only the happy path. Test suites should cover:

- Validation failure at the start of the workflow.
- Activity timeout before execution and timeout after committing side effects.
- 429/5xx errors, exhausting max retries, and hitting deadlines.
- Valid callbacks, duplicate callbacks, invalid signatures, and late callbacks.
- Choice branches with no matching case and missing input fields.
- One parallel branch failing while another already produced side effects.
- Compensation succeeding, failing, and returning indeterminate outcomes.
- Stopping, resuming, or redriving workflows according to platform semantics.
- Missing IAM permissions, expired secrets, and unreachable dependencies.

### 13.2. Testing State Machines with Fixtures

| Fixture | Expected verification |
|---|---|
| Valid booking, available, payment authorized | Reaches `CONFIRMED` and emits event with exactly one logical effect |
| Sold out | Terminates `REJECTED`, never calls Payment |
| Payment declined | Releases hold if present and records `FAILED`/`CANCELLED` |
| Payment timeout with unknown result | Queries/reconciles instead of blindly creating a new transaction |
| Late approval callback | Handled per deadline and current state without reviving an invalid execution |
| Activity emits event then crashes | Retry produces no duplicate side effects |

### 13.3. Versioning and Deployment

Workflow definitions and activity contracts must be versioned. Definition changes can affect in-flight executions; platforms may apply new versions to new executions while older ones continue on the prior definition, or follow different semantics. Verify exact service behavior, plan input/output compatibility, and never delete functions or versions still referenced by active executions.

A release plan should include:

- Syntax/schema validation and IAM permission checks.
- Local or staging workflow tests against fixtures.
- Compatibility-ordered deployment of definitions and activities.
- Canary or bounded rollout using safe test data.
- Monitoring failure rates, duration, retries, and costs.
- Documented rollback or forward-fix procedures with clear history and owners.

## 14. Workflow Design Example for a Booking Platform

Suppose a system accepts booking requests and completes them in an asynchronous process. Illustrative goals:

- Accept booking requests within seconds.
- Hold inventory for a limited window.
- Authorize payment; if successful, confirm the booking.
- If unsuccessful, release the hold and update state.
- If the payment outcome is unknown, reconcile instead of guessing.
- Send notifications once the booking is confirmed.

### 14.1. Workflow Logic

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Booking API
    participant WF as Workflow Engine
    participant AV as Availability
    participant PAY as Payment
    participant DB as Booking Store
    participant MSG as Notification
    C->>API: POST /bookings + idempotency key
    API->>DB: Create PENDING booking
    API->>WF: Start execution with bookingId
    API-->>C: 202 Accepted + bookingId
    WF->>AV: Hold inventory
    AV-->>WF: holdId / rejected
    WF->>PAY: Authorize with paymentReference
    PAY-->>WF: Authorized / Declined / Unknown
    WF->>DB: Confirm or set RECONCILING
    WF->>MSG: Notify after confirmed
~~~

The Workflow Engine receives only required identifiers; booking and payment data remain in their owning services. The Booking API returns `202` upon acceptance, and clients poll status or subscribe to notifications.

### 14.2. Pseudocode Workflow Definition

~~~yaml
# Provider-neutral pseudocode, not direct syntax for a specific cloud provider.
workflow: CreateBooking
input:
  bookingId: string
  tenantId: string
  paymentReference: string
states:
  - task: HoldAvailability
    retry: transient-errors-only
    timeout: 10s
    onFailure: RejectBooking
  - task: AuthorizePayment
    idempotencyKey: paymentReference
    timeout: 20s
    onUnknown: ReconcilePayment
    onDeclined: ReleaseHold
  - task: ConfirmBooking
    onSuccess: PublishBookingConfirmed
    onUnknown: ReconcileBooking
  - task: PublishBookingConfirmed
  - task: NotifyCustomer
  - end: SUCCEEDED
~~~

This condensed pseudocode illustrates responsibilities. In production, the workflow must include complete compensation paths, concrete retry policies, per-task permissions, terminal states, and handling for indeterminate activity results.

### 14.3. Responsibility Matrix

| Component | Data/rule owner | Responsibilities |
|---|---|---|
| Booking Service | Bookings | Create bookings, business states, tenant and permission checks |
| Availability Service | Inventory/holds | Hold decisions, hold expiration, release/confirm |
| Payment Service | Payments | Authorize/capture/refund states, provider reconciliation |
| Workflow definition | Process-owning team | Step order, timeouts, branches, retries, compensation, and deadlines |
| Notification Service | Delivery status | Send notifications, handle retries/deduplication |
| Platform/Security | Infrastructure and IAM | Quotas, logging, encryption, roles, and networking |

### 14.4. States Requiring Reconciliation

Suppose the payment provider authorizes successfully, but the response times out. The workflow does not know the outcome. The `ReconcilePayment` activity queries by `paymentReference`:

- If the provider confirms `Authorized`, the workflow proceeds to confirm the booking.
- If the provider confirms `Declined` or no transaction exists, the workflow releases the hold and closes in the appropriate state.
- If the provider still reports `Processing`/`Unknown`, the workflow waits a bounded interval and queries again.
- If still indeterminate at the deadline, transition to `RECONCILING`, trigger an alert, and assign an owner; do not emit `BookingConfirmed`.

The reconciliation process must log every check result and prevent duplicate capture or refund calls on the same payment.

## 15. Common Pitfalls

| Pitfall | Consequence | Redesign approach |
|---|---|---|
| Using the workflow as a business database | No clear system of record, hard data governance | Workflow tracks progress; owning services store business truth |
| Retrying every error | Repeats validation/auth errors, inflates costs | Classify retryable vs. non-retryable and cap total duration |
| Assuming timeout means side effect failed | Creates duplicate transactions | Idempotency keys and reconciliation |
| Assuming workflows auto-roll back multiple services | Data drift across booking, inventory, and payment | Sagas and verified compensation |
| Putting large payloads or secrets in state | Hits size limits, leaks data via history/logs | Pass IDs/references, minimize data, enforce access control |
| Waiting via function sleep | Wastes compute and hits runtime limits | Wait states, timers, or callbacks |
| Unbounded fan-out | Overloads dependencies and exceeds quotas | Concurrency limits, batching, and backpressure |
| Not indexing executions by business ID | Difficult investigation and reconciliation | Correlation IDs and business transaction IDs |
| Changing definitions without accounting for running executions | Old/new activities become incompatible | Versioning, compatibility plans, and controlled rollouts |
| Treating events/notifications as transaction proof | Sends wrong notifications before confirmation | Emit events only after owner commits authoritative state |

## 16. Well-Architected Evaluation

| Pillar | Questions for workflow design | Mitigations and trade-offs |
|---|---|---|
| **Operational Excellence** | Who owns definitions, executions, runbooks, and manual interventions? | Versioning, dashboards, correlation, alerts; more states add operational surface |
| **Security** | What can the workflow/tasks access, what is stored in history, and who can view it? | Least privilege, secret managers, data minimization, auditing, callback controls |
| **Reliability** | How are retries, timeouts, compensation, and `UNKNOWN` states handled? | Idempotency, sagas, reconciliation, DLQs, and failure-path testing |
| **Performance Efficiency** | Are there excessive transitions or service calls? | Combine pure-compute steps, tune concurrency, optimize fan-out |
| **Cost Optimization** | How much do executions, transitions, function duration, history, and logs cost? | Cap loops/retries, keep payloads small, choose right workflow tier |
| **Sustainability** | Does the workflow poll, loop, or hold resources unnecessarily? | Callbacks/timers, deduplication, batching, and efficient execution |

Workflows make processes more resilient when designed well, yet introduce a new platform layer to secure, monitor, and budget. Adopt a workflow engine when the benefits of durable orchestration outweigh its overhead.

## 17. Applied Exercises

### Exercise A — Choosing Orchestration vs. Choreography

An onboarding process has 9 steps, including manual approvals, partner waits, timeouts, and rolling back several actions if rejected.

**Question:** Which model fits better for managing overall state?

**Hint:** Orchestration usually makes long-running flows, branching, and centralized compensation easier to express. Completion events can still use choreography to notify analytics, notifications, and independent consumers.

### Exercise B — Timeout After Payment

The authorize-payment task times out. The workflow immediately retries with a new `paymentReference`, resulting in two charges.

**Question:** What needs to change?

**Hint:** Keep a stable reference per intent, enforce idempotency in Payment Service, query status before issuing a new request, distinguish transient errors from `UNKNOWN`, and reconcile when deadlines expire.

### Exercise C — Failed Compensation

A booking was created and payment authorized; confirming inventory failed. The void-authorization task also times out.

**Question:** Can the workflow immediately mark the booking `CANCELLED`?

**Hint:** Not while the void outcome is indeterminate. Transition to a compensating/reconciliation state, query Payment by reference, apply bounded retries, alert the owner, and conclude only with evidence. Never claim rollback succeeded without confirmation.

### Exercise D — Long-Running Workflow

A document review process may wait up to 5 days for manager approval.

**Question:** Why should a function not run and sleep? How should the callback be secured?

**Hint:** Function sleep consumes runtime, hits execution limits, and is not durable if processes terminate. Use a wait/callback state; callbacks must authenticate the sender and approver permissions, bind to the execution/tenant, prevent replay, expire, and maintain an audit log.

### Exercise E — Fan-Out Causing Traffic Spikes

A workflow processes 50,000 rows and launches one function per row simultaneously. The downstream database supports only 500 concurrent requests.

**Question:** What controls are needed?

**Hint:** Batch rows, cap concurrency, apply rate limiting and backpressure, monitor queues/backlog, and bound retries. Never fan out until the database saturates.

## 18. Pre-Production Checklist for Workflows

- [ ] Business goals, process owners, deadlines, and termination criteria are defined.
- [ ] Orchestration vs. choreography is chosen based on complexity and observability needs.
- [ ] States, transitions, inputs/outputs, error paths, and indeterminate states are explicitly modeled.
- [ ] Tasks have timeouts and bounded retries; business errors do not retry indefinitely.
- [ ] Side effects implement idempotency and reconciliation for post-commit timeouts.
- [ ] Multi-service flows implement compensation/Sagas, including compensation failure handling.
- [ ] Payloads are small, schema-validated, and free of secrets or unnecessary sensitive data.
- [ ] Execution history, logs, callbacks, and backups enforce retention, encryption, and access control.
- [ ] Per-task IAM enforces least privilege; callbacks and human approvals enforce auth/authz/audit.
- [ ] Fan-out enforces concurrency caps, downstream quotas, and backpressure.
- [ ] Correlation/business IDs, dashboards, alerts, DLQs, and reconciliation runbooks exist.
- [ ] Workflow definitions and activity contracts are versioned; in-flight executions are handled during deployments.
- [ ] Happy paths, failure paths, duplicates, out-of-order events, timeouts, late callbacks, and failovers are tested.
- [ ] Costs for transitions, invocations, duration, storage, and dependent services are estimated.
- [ ] Plans exist for periodic reviews, game days, and updates when business rules or dependencies change.

**Key takeaway:** a workflow service orchestrates **process progress**, while domain services still own **their data and business rules**. Reliable processes require explicit states, bounded retries, idempotent side effects, compensation, and evidence-based reconciliation. Combined properly with IAM, observability, quotas, and fault testing, workflows coordinate serverless components into cohesive business processes that remain safe to operate and evolve.
