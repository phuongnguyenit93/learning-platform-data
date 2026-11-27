# Compensating Error Flows in Spring Integration Adapters

## 1. Problem Statement: Errors Occur After Another System Already Changed State

In the **SPRING_INTEGRATION_ADAPTERS** module, Spring Integration connects systems via **inbound/outbound adapters**, **gateways**, **pollers**, and **MessageChannels**. A flow can read a file over SFTP, write to a database, call a partner HTTP API, emit an event via Kafka, and send a notification. Trouble begins when **one or more steps succeeded, yet a subsequent step fails**.

Consider an order placement workflow:

1. Receive an order creation request from an HTTP inbound gateway.
2. Reserve inventory in the internal database: succeeds.
3. Call the carrier's HTTP API to create a shipment: succeeds.
4. Send a confirmation message to the payment system via a broker: fails.

If you merely log the exception at step 4, inventory stays reserved and the shipment exists while the order remains incomplete. If you retry the whole flow without checking state, the system could **reserve inventory twice and create two shipments**.

A **compensating error flow** is an error-handling flow designed to **restore business consistency** by executing controlled compensating actions for side effects that already occurred, or by transitioning the process to a state requiring reconciliation/manual action when safe reversal is impossible.

Examples:

- Inventory already reserved → **release the reserved stock** when cancelling the order;
- Shipment already created → **send a shipment cancellation request** if the carrier supports it;
- Payment already captured → **create a refund transaction**, rather than deleting payment history;
- Email or Kafka event already sent → cannot be reliably "recalled"; you can **send a correction notice/compensating event**.

In Spring Integration, an error flow can start from an **ErrorMessage** sent to **errorChannel** or a dedicated error channel. However, **the framework does not automatically deduce which steps to compensate, does not provide rollback across arbitrary systems, and does not turn an ErrorMessage into a durable saga**. The application must define state, business keys, compensation commands, and outcome verification.

### Learning Objectives

After this lesson, learners can:

1. Distinguish **retry**, **rollback**, **compensation**, **reconciliation**, and **manual recovery**.
2. Identify transaction boundaries when integrating File/SFTP, HTTP, JMS/AMQP, Kafka, and databases.
3. Design an error flow that consumes **ErrorMessage** while preserving enough business context to compensate.
4. Model a **saga**-style step sequence, knowing which steps are reversible and which are not.
5. Enforce **idempotency**, bounded retries, durable state data, and protection against double compensation.
6. Handle **timeouts where it is unknown whether the external side succeeded or failed**.
7. Establish testing, auditing, alerting, and runbook strategies for compensation errors.

## 2. Distinguishing Retry, Rollback, and Compensation

These are three distinct mechanisms solving three different classes of problems.

| Mechanism | When Appropriate? | Undoes Committed Effects in External Systems? |
|---|---|---|
| **Retry** | Transient error, idempotent operation | No; can cause duplicates if lacking idempotency |
| **Rollback** | Operations within a single uncommitted transaction | Only within supported transaction boundaries |
| **Compensation** | A step already committed or caused side effects needing remediation | Can restore business consistency via compensating actions, not necessarily the exact prior technical state |
| **Reconciliation** | True outcome unknown or states across systems diverged | Detects discrepancies, leading to retry/compensation/adjustment |
| **Manual intervention** | Insufficient data or no safe automated compensation | Depends on authorized decisions and operational procedures |

### 2.1. Retry Is Not Compensation

An HTTP outbound gateway getting a `503` before the target processes it can retry after backoff. Yet if the request already created a shipment and the response was lost, resending POST could create a second shipment. Then you need an **idempotency key, status lookup API**, or duplicate detection before retrying.

### 2.2. Rollback Does Not Cross Arbitrary Boundaries

A JDBC transaction can roll back uncommitted changes in the same datasource. It **does not automatically roll back** an HTTP call processed by a partner, a renamed SFTP file, a sent email, or a Kafka record already read by another consumer.

Even when using a broker transaction, atomicity spans only resources properly enlisted in that transaction. **Never assume `@Transactional` on a whole Spring Integration flow covers every adapter**.

### 2.3. Compensation Is a New Business Action

Releasing reserved inventory is typically **a new transaction** requiring a new audit record. A refund is also a separate transaction, not deleting the original payment. Systems may incur processing fees, delays, or irreversible actions; compensation achieves business consistency **without identically reverting technical history**.

### 2.4. Not Every Error Needs Compensation

If validation fails **before any side effect**, simply return an error or quarantine the data. If an error is transient and retry is safe, do not immediately cancel the order. If an external operation's outcome is unknown, reconcile before compensating—avoiding cancelling an action that never happened or creating contradictory state.

## 3. Boundaries That Make Compensation Necessary

| Adapter / Gateway | Side Effects That May Have Occurred | Possible Compensation | Limits to Remember |
|---|---|---|---|
| **File inbound/outbound** | File moved, deleted, overwritten | Restore from safe copy or return to queue | Files already read by another consumer may not be recallable |
| **SFTP** | File downloaded, renamed, deleted, or partially uploaded | Send cancel file, transition state, or upload correction | Remote server may have processed file before compensation |
| **HTTP** | Created order, booking, charge, external request | Cancel, release, refund, status update | Timeout leaves outcome unknown; compensating API must be supported by partner |
| **JMS** | Message sent/acked, consumer processed | Send compensating command or new business action | Cannot assume an already-consumed message can be "unsent" |
| **AMQP** | Message reached queue, consumer caused side effects | Compensating event/command, DLQ for processing errors | Ack/nack differs from undoing a committed business action |
| **Kafka** | Record published and read by multiple consumers | Emit adjustment/reversal event | Cannot reliably retract an already-published record |
| **JDBC** | Row committed, another transaction read it | Compensating transaction updating status/releasing resources | Deleting rows can break audits or business constraints |

### 3.1. Do Not Conflate Two Error Categories

**Transport failure:** cannot connect to SFTP, broker disconnects, HTTP timeout. The system may not have created side effects yet.

**Business inconsistency:** two of three services committed; the last service failed. This requires **deciding to continue, perform controlled retry, or compensate**.

If you lump both into one error handler that automatically calls `cancelOrder` on any exception, the system will cancel valid orders or cause further errors.

### 3.2. Understand Delivery Semantics

Receiving an `ErrorMessage` **does not mean the source message has not been acknowledged**. JMS/AMQP containers, Kafka offset commits, File poller filters, and JDBC transactions each have their own mechanics. Error flows must coordinate with them: to retry after a restart, input or recovery commands must be durably persisted.

## 4. Architecture: Forward Flow, Error Flow, and Compensation Flow

~~~mermaid
flowchart TD
    SRC["Inbound adapter/gateway"] --> COR["Correlation and validation"]
    COR --> S1["S1: Reserve inventory"]
    S1 --> SAVE1["Persist state STEP1_DONE"]
    SAVE1 --> S2["S2: Create delivery via HTTP"]
    S2 --> SAVE2["Persist state STEP2_DONE"]
    SAVE2 --> S3["S3: Publish confirmation"]
    S3 --> DONE["COMPLETED"]
    S1 -. "Error" .-> ER["Error publisher if configured"]
    S2 -. "Error" .-> ER
    S3 -. "Error" .-> ER
    ER --> EC["errorChannel or dedicated channel"]
    EC --> CL["Classify + resolve sagaId"]
    CL --> DEC{"Retry, reconcile, or compensate?"}
    DEC -->|"Transient, safe"| RET["Bounded retry"]
    DEC -->|"Outcome unknown"| QUERY["Query/reconcile external state"]
    DEC -->|"Business cancel"| COMP["Durable compensation commands"]
    QUERY --> DEC
    COMP --> C2["C2: Cancel delivery if created"]
    C2 --> C1["C1: Release inventory"]
    C1 --> VERIFIED["COMPENSATED / verified"]
    RET --> S3
    COMP --> EX["Intervention needed if compensation fails"]
~~~

The diagram illustrates an **application-orchestrated saga**. Spring Integration does not auto-generate `C1`/`C2` from `S1`/`S2`; business states and compensation commands must be explicitly defined. The `ErrorMessage` path also appears only when **an exception is actually caught and sent by an error publisher**, not automatically for every synchronous exception.

### 4.1. Separating Three Planes of Responsibility

1. **Message transport:** inbound/outbound adapters, gateways, `MessageChannel`, pollers, and listeners moving messages.
2. **Business orchestration:** saga coordinator tracking completed steps, external effects, and business goals.
3. **Error/recovery control:** classifying errors, choosing retry/reconciliation/compensation, tracking failures, and triggering operations.

For short integrations, the coordinator can reside inside a single service/DB. For long-running or distributed workflows, use a state machine or dedicated workflow engine. Do not deploy a heavy saga engine if the problem is strictly a local DB transaction.

### 4.2. Orchestration vs. Choreography

| Organization | Description | Pros | Caveats |
|---|---|---|---|
| **Orchestration** | Coordinator commands each forward and compensating step | Easy to track global status and compensation order | Coordinator and state store must be highly reliable |
| **Choreography** | Services react to events and emit compensating events | Low coupling to a central coordinator | Harder to see global view; needs correlation and cycle control |

Spring Integration supports building message flows for both, but saga rules and orchestration data must be designed by the application.

### 4.3. Reverse-Order Compensation When Dependencies Exist

If `S1` reserves inventory and `S2` creates a shipment backed by that inventory, cancelling an order usually **cancels the shipment (`C2`) first**, then **releases inventory (`C1`)**. Still, never apply reverse ordering mechanically: when dependencies, cancellation fees, deadlines, or irreversible steps exist, define per-step policies.

## 5. Durable State Model for Compensation

An `ErrorMessage` only exists in the message channel during active processing; to recover across restarts, durably persist **saga state and compensation tasks**.

### 5.1. Suggested Saga States

| State | Meaning |
|---|---|
| NEW | Request received, no side effects created yet |
| RUNNING | Executing forward steps |
| STEP_COMPLETED | Specific step confirmed its result |
| RESULT_UNKNOWN | A step timed out or has an indeterminate outcome |
| COMPENSATION_REQUIRED | Decision made to compensate completed steps |
| COMPENSATING | Compensation commands are executing |
| COMPENSATION_RETRY | A compensation step hit a transient error and awaits retry |
| COMPENSATED | Required compensations confirmed complete |
| COMPLETED | Forward flow succeeded per contract |
| MANUAL_REVIEW | Cannot decide or compensate automatically with safety |
| FAILED_TERMINAL | Stopped in a controlled failure state with evidence |

Not every saga needs every state; what is mandatory is distinguishing **"received ErrorMessage"**, **"scheduled compensation"**, and **"compensation took effect"**.

### 5.2. Illustrative Saga Record

~~~json
{
  "sagaId": "saga-order-274",
  "businessKey": "order-274",
  "tenantId": "tenant-B",
  "state": "COMPENSATION_REQUIRED",
  "version": 7,
  "steps": [
    {
      "name": "RESERVE_INVENTORY",
      "status": "SUCCEEDED",
      "resourceId": "reservation-R274"
    },
    {
      "name": "CREATE_DELIVERY",
      "status": "SUCCEEDED",
      "resourceId": "shipment-S274"
    },
    {
      "name": "PUBLISH_CONFIRMATION",
      "status": "FAILED",
      "resourceId": null
    }
  ],
  "error": {
    "stage": "PUBLISH_CONFIRMATION",
    "classification": "TRANSIENT",
    "correlationId": "import-batch-012",
    "attempt": 3
  }
}
~~~

This is an illustrative business schema, not a built-in Spring Integration type. References like reservation/shipment must come from **actual target-system responses or a trusted data store**, never fabricated from input when request success is uncertain.

### 5.3. Compensation Command Table

A compensation task should include:

- Unique `commandId` and `sagaId`;
- Step name to compensate, target `resourceId`, operation, and reason;
- Stable idempotency key;
- Status `PENDING`/`RUNNING`/`SUCCEEDED`/`RETRY`/`FAILED`;
- Attempt count, deadline, `nextAttemptAt`, and sanitized `lastError`;
- Version to prevent two workers from executing concurrently;
- Owner and confirmation evidence.

**Durability:** if persisting saga state and creating compensation commands in the same database, commit them in a single transaction. If commands must go to a broker, use a **transactional outbox** to avoid recording DB state without publishing the command, or vice versa.

### 5.4. Prevent Stale States from Overwriting Newer States

A late HTTP callback might report `S2` succeeded after the coordinator already decided to compensate. Use **state/version/expected-status checks** to treat late callbacks as verification info or stale events. Never let a stale callback flip `COMPENSATED` back to `RUNNING` or re-grant/re-create shipments without a fresh decision.

## 6. ErrorMessage, MessagingException, and Compensation Decision Context

### 6.1. Where Does ErrorMessage Come From?

In Spring Integration, when an **error handler** on a poller, executor, gateway, or endpoint is configured to publish errors, the exception can be wrapped into an **ErrorMessage** sent to **global `errorChannel`** or a dedicated error channel.

- **ErrorMessage** is a Spring Message whose payload is a **Throwable**.
- **MessagingException** is an exception that can retain **failedMessage** at the failure point.
- **ErrorMessage.getOriginalMessage()** can hold an input Message if provided by the `ErrorMessage` builder; it may be null.
- **MessageHeaders.ERROR_CHANNEL** is the header selecting the error destination when supported by the publisher; setting the header alone does not catch exceptions.

Note: a handler executing **synchronously on a `DirectChannel`** typically throws the exception back to the sender. That error **is not automatically published** to `errorChannel` merely because an `errorChannel` bean exists. JMS/AMQP/Kafka listener adapters also have their own container-level error handlers.

### 6.2. The Error Flow Is Not the Sole Source of Truth

`ErrorMessage` answers **"which Throwable was emitted?"**, yet cannot always answer **"which business steps already committed?"**. For example, on an HTTP timeout at `S2`, `failedMessage` may be `CreateShipmentCommand`, which does not tell you whether the carrier created the shipment. The coordinator must query real state via an idempotency key or external resource lookup.

If a compensation design merely reads `exception.getMessage()` and calls cancel, decisions will lack facts and easily corrupt business data.

### 6.3. Distinguishing failedMessage and originalMessage

~~~text
HTTP order request       -> M0 (OrderRequest)
Transformer              -> M1 (ReserveInventoryCommand)
Inventory reservation    -> OK
Transformer              -> M2 (CreateShipmentCommand)
HTTP outbound gateway    -> timeout

ErrorMessage.payload: MessagingException
  failedMessage: may be M2
ErrorMessage.originalMessage: M0, M1, M2, or null
  depending on what context the endpoint/error strategy passed
~~~

Do not cast every `originalMessage` to `OrderRequest`, nor rely solely on `failedMessage` being non-null. **`sagaId` and `businessKey` must be intentionally maintained** in headers or a state store; when both references are null, use task/flow metadata or the persisted event source.

### 6.4. Illustrative Code Reading Errors for Orchestration

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class OrderSagaErrorRouter {

    private final SagaFailureService failures;

    public OrderSagaErrorRouter(SagaFailureService failures) {
        this.failures = failures;
    }

    @ServiceActivator(inputChannel = "orderErrors")
    public void onError(ErrorMessage error) {
        Throwable cause = error.getPayload();
        Message<?> failed = cause instanceof MessagingException me
                ? me.getFailedMessage()
                : null;
        Message<?> original = error.getOriginalMessage();

        Object id = failed != null
                ? failed.getHeaders().get("sagaId")
                : null;
        if (id == null && original != null) {
            id = original.getHeaders().get("sagaId");
        }

        if (!(id instanceof String sagaId) || sagaId.isBlank()) {
            // Insufficient context: record safe alert for manual handling.
            failures.recordUncorrelatedFailure(cause);
            return;
        }

        // Persist failure durably. DO NOT call all cancel APIs directly inside observer.
        failures.recordAndScheduleDecision(sagaId, cause);
    }
}

interface SagaFailureService {
    void recordAndScheduleDecision(String sagaId, Throwable cause);
    void recordUncorrelatedFailure(Throwable cause);
}
~~~

This is an illustrative skeleton in modern Java, assuming `SagaFailureService` methods are implemented by the application. Without service beans, channels, and error publishing wiring, this code is not a standalone runnable app.

**Key points to note:**

- The error handler must persist durable state or hand off to safe recovery; **returning does not mean the source message succeeded**.
- Swallowing vs. rethrowing exceptions affects listeners/pollers/containers differently; design acknowledgments/transactions explicitly.
- Never persist a raw `Throwable` into the database as an arbitrary payload. Store only exception type, sanitized description, context, and log/trace references.
- Listener invocations **can be retried**; `recordAndScheduleDecision` must be idempotent for the same saga and failure.

### 6.5. Global Channel or Dedicated Channel?

The default **errorChannel** is typically a `PublishSubscribeChannel` with a logging subscriber; do not place side-effecting actions on a global subscriber. For an order workflow, use a dedicated channel like **orderErrors** with clear ownership and recovery policy. Global `errorChannel` can log/alert on errors not specifically routed.

If multiple subscribers receive the same `ErrorMessage`, never let two subscribers both issue shipment cancellation commands. **A single logical coordinator/recovery consumer** should own compensation decisions; other subscribers should only observe or record metrics.

## 7. Compensation Command Model and Execution

### 7.1. Every Compensation Step Needs Preconditions

Never write a bare `cancelShipment(String orderId)` function. Verify:

1. Is the shipment confirmed to exist, or is the outcome unknown requiring reconciliation?
2. Does this shipment genuinely belong to the saga and tenant?
3. Was a cancel request already sent, and was a request ID returned?
4. Is cancellation still permitted given the shipment's current status?
5. Does cancel success mean the target accepted the request or confirmed completion?
6. Could a delayed callback alter state after the cancel command was sent?

### 7.2. Compensation Command Payload

~~~json
{
  "commandId": "comp-saga-274-cancel-shipment",
  "sagaId": "saga-order-274",
  "operation": "CANCEL_SHIPMENT",
  "targetId": "shipment-S274",
  "expectedStep": "CREATE_DELIVERY",
  "idempotencyKey": "saga-order-274-CANCEL_SHIPMENT-v1",
  "attempt": 1,
  "status": "PENDING",
  "deadline": "2026-11-24T08:00:00Z"
}
~~~

This is illustrative business data, **not a built-in API** of Spring Integration. If commands travel over a broker, secure access to the command channel; replaying a cancel command against the wrong target can have major impact.

### 7.3. Dedicated Adapter for Compensation Commands

You can create an **IntegrationFlow** consuming compensation command messages or a service activator on a dedicated channel:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

public record CompensationCommand(
        String commandId,
        String sagaId,
        String operation,
        String targetId,
        String idempotencyKey) {}

@Component
public class CompensationCommandHandler {

    private final CompensationCoordinator coordinator;

    public CompensationCommandHandler(CompensationCoordinator coordinator) {
        this.coordinator = coordinator;
    }

    @ServiceActivator(inputChannel = "compensationCommands")
    public void handle(CompensationCommand command) {
        coordinator.executeUsingPersistedState(command);
    }
}

interface CompensationCoordinator {
    void executeUsingPersistedState(CompensationCommand command);
}
~~~

In a real Java project, records and public top-level types belong in separate source files per Java rules. Here they are grouped for readability, **not as a single complete Java file**. The Spring context must define the channel and a producer sending typed `CompensationCommand` objects to it. The name `compensationCommands` is strictly an application convention.

### 7.4. Division of Labor: Thin Handler, Thick Coordinator

The handler merely forwards the command to the coordinator. The coordinator should:

- Read saga state and command state from the durable store;
- Acquire a claim/lease or optimistic lock to prevent two workers from running the same command;
- Verify preconditions, tenant, resource, and business deadline;
- Invoke the right compensating adapter (HTTP cancel, DB release, event producer...);
- Record verified outcomes or retry/unknown states;
- Orchestrate the next compensating step according to dependencies;
- Emit safe events/audits after state changes.

Spring Integration configuration **does not automatically provide distributed locks or transactional state**. Concurrency guarantees must come from the storage/coordination layer.

## 8. Idempotency and Duplicate Handling

Messages can be redelivered due to retries, broker redelivery, consumer restarts, or timeouts. Compensation commands can also be re-executed. **Without idempotency, compensating twice can be just as dangerous as executing forward twice**.

### 8.1. Example of Non-Idempotent Compensation

Suppose `S1` subtracts 5 units from stock and `C1` adds 5 back. If `C1` runs twice after a retry, stock increases by 10—corrupting inventory. Good design keys off the reservation ID:

~~~text
releaseReservation(reservationId):
    row = loadReservationForUpdate(reservationId)
    if row.status == RELEASED:
        return ALREADY_APPLIED
    if row.status != RESERVED:
        return REQUIRES_RECONCILIATION
    releaseQuantityExactlyOnce(row)
    markReservationReleased(row)
    commit
~~~

The snippet above is **pseudocode**, assuming a single transaction guards both inventory and reservation state. If inventory lives in an external system, you need an API with an idempotency key or a status lookup mechanism.

### 8.2. Stable Idempotency Keys

Derive keys from **`sagaId` + compensation type + target ID or step ID**—never generate a new UUID on each retry for the same intent. The recipient must define the key's scope, retention window, and behavior if a key is reused with a different payload.

### 8.3. Realistic Guarantees

"Exactly once" across HTTP, SFTP, databases, and brokers cannot be inferred from a Spring `MessageChannel`. You can achieve **business-level effectively-once semantics** via durable state, idempotent commands, deduplication, and reconciliation; messages themselves may still be delivered multiple times.

### 8.4. Guarding Against Out-of-Order Events

A compensation may arrive before a forward step confirmation, or an old success event may arrive after compensation already ran. Use version/expected-state checks; if the outcome cannot be determined, pause automation and route to reconciliation rather than guessing.

## 9. Timeouts and Unknown States: The Hardest Case

### 9.1. Three Outcomes to Distinguish

For an HTTP `CreateShipment` request:

| Caller Outcome | Actual Partner Outcome | Appropriate Action |
|---|---|---|
| 2xx with resource ID | Created per contract | Store resource ID and mark step succeeded |
| Clear business 4xx | Rejected if contract confirms not created | Do not compensate a nonexistent shipment |
| Timeout/connection reset after send | May or may not have been created | Query via idempotency key, reconcile before retry/compensation |
| 5xx after partial processing | Depends on API contract | Needs status query or reconciliation |

Never assume a timeout means guaranteed failure at the destination. That assumption is a frequent cause of **double charges**, **duplicate shipments**, and compensating the wrong target.

### 9.2. Reconciliation Workflow

~~~mermaid
flowchart TD
    E["HTTP outbound timeout"] --> U["Mark step RESULT_UNKNOWN"]
    U --> Q["Lookup external status by stable request key"]
    Q --> D{"Outcome?"}
    D -->|"Created"| S["Store target ID, confirm STEP_SUCCEEDED"]
    D -->|"Not created, with proof"| R["Retry within budget or decide to cancel"]
    D -->|"Still unclear"| M["MANUAL_REVIEW or bounded lookup retries"]
    S --> C{"Continue saga or compensate?"}
    C -->|"Continue"| F["Next forward step"]
    C -->|"Cancel"| B["Compensation command with real target ID"]
~~~

If a partner lacks a lookup/idempotency API, never fabricate an outcome. Use manual investigation, transaction report reconciliation, or redesign the protocol before automating compensation.

### 9.3. Delays Can Invalidate Compensation

A booking was created, yet by the time the cancel command arrives, the partner has already shipped the goods. "Cancel" may no longer be permitted; policy must transition to return/refund or other handling instead of retrying the cancel API forever.

## 10. File and SFTP: Compensating File Operations

### 10.1. File Inbound Is Not a Database Transaction

A file inbound adapter reads files from a directory. The poller may use filters to avoid re-reading already accepted files, such as `AcceptOnceFileListFilter` variants or persistent filters. When parsing/DB writing fails, an `ErrorMessage` **does not reset the filter**, does not return the file to inbox, and does not guarantee another consumer hasn't read it.

Manage states explicitly:

| File State | Meaning | Action on Error |
|---|---|---|
| DETECTED | File spotted, processing not confirmed | Wait for stability, lock if needed |
| CLAIMED | Worker took ownership | Prevent multiple pollers from claiming |
| PARSED | Read/validated and business key established | Keep context for replay |
| IMPORTED | DB committed data | Do not blindly re-import; enforce idempotency |
| QUARANTINED | Faulty data isolated | Record reason, owner, retention |
| ARCHIVED | Completed and retained per policy | Never trigger a second import |

If a file fails schema validation upfront, **quarantine** is usually better than compensation because no business side effect occurred. If half a file succeeded, use appropriate transaction scopes or **compensate per confirmed record/batch** rather than deleting the file without knowing what was saved.

### 10.2. SFTP Outbound and Partner-Processed Files

An outbound SFTP adapter may upload a file and rename it to a "ready" location. Once a message is published per partner convention, **deleting the remote file does not mean the partner has not processed the data**. Compensation depends on contract:

- If the file is still in staging and unread by consumers: delete temp file/rename per policy.
- If already published: send a **cancel/correction file** referencing the transaction ID.
- If unsure whether the partner read it: reconcile with the partner system before compensating.
- If upload failed mid-transfer: verify remote checksum/size and temp file state; prevent partial files from being ingested.

### 10.3. Error Flows Differ for Parse Errors vs. Remote Session Errors

SFTP authentication/timeout errors can occur **before a Spring Message exists**, so `failedMessage` may be null. Parse errors occur after the file enters the flow and may have `failedMessage` containing `File` or transformed payloads. Attach flow ID, remote file reference, stage, and correlation from a trusted source.

**Do not stuff sensitive file bytes into `errorChannel` "just in case"**; store a reference to a controlled durable store instead.

## 11. HTTP Gateways: Cancel, Refund, and Idempotent Commands

### 11.1. Synchronous Request/Response

An HTTP inbound gateway usually has a caller waiting for a response. If processing fails, return a contract-compliant **HTTP status and error body**, rather than only publishing an `ErrorMessage` in the background. For example, a validation error prior to side effects can return `400`; a transient failure with unknown state may require a status/response indicating "processing" or asking the client to poll status, per API contract.

For long-running workflows, HTTP inbound can accept the request, persist saga state, and return **202 Accepted with an operationId** if the API is designed asynchronously. Later errors cannot be returned on the already-closed HTTP request; callers need a status query endpoint, callback, or result event.

### 11.2. Outbound HTTP with Non-Fully-Reversible Operations

| Forward Action | Business Compensation Action | Characteristics |
|---|---|---|
| Create booking | Cancel booking | Valid only before service delivery |
| Reserve stock | Release reservation | Needs `reservationId` and duplicate-release protection |
| Capture payment | Refund | Creates a new transaction with fees, deadlines, and financial rules |
| Issue invoice | Void/correcting invoice | Follows accounting rules, not a simple DELETE |
| Create user | Deactivate/revoke grants | Must revoke downstream sessions, tokens, permissions |
| Send notification | Send correction notification | Cannot guarantee recipient hasn't seen initial notice |

**A refund is not a database rollback** and may require approval controls, customer/payment reference verification, or amount limits.

### 11.3. Partners Need an Idempotency Contract

If an external API supports **Idempotency-Key** (per their specification), the client should reuse **the same key across retries of a single forward intent**. Compensating actions must have **a separate stable key for the cancel/refund intent**, never reusing the booking creation key when semantics differ.

Illustrative compensation request structure:

~~~http
POST /api/shipments/shipment-S274/cancel HTTP/1.1
Authorization: Bearer <access-token>
Idempotency-Key: saga-order-274-cancel-shipment
Content-Type: application/json

{"reason":"ORDER_CANCELLED","sagaId":"saga-order-274"}
~~~

The endpoint and headers are **an illustrative hypothetical contract**; not every HTTP service supports a cancel endpoint or idempotency header. Real tokens and credentials must never be logged or placed in `ErrorMessage`.

### 11.4. Distinguishing Sent Compensation Command from Completed Compensation

HTTP `202` from a cancel API may merely mean **the cancellation request was accepted**, not that the shipment is cancelled yet. Coordinator state should be `COMPENSATION_PENDING_CONFIRMATION`, polling or awaiting webhooks per contract until final status. Mark `COMPENSATED` only with real confirmation evidence.

## 12. JMS and AMQP: Ack Does Not Erase Business Side Effects

### 12.1. JMS Inbound Containers

With JMS inbound listeners, transaction/acknowledgment mode determines whether the source message is acked, rolled back, or redelivered. A service activator may throw an exception, yet if an error handler **catches, logs, and returns normally**, the container may see success and acknowledge per config.

Key decisions:

- If business logic **has not caused side effects** and broker redelivery is desired, configure propagation/rollback properly.
- If you **durably persisted saga state + compensation/retry commands**, you may configure acking the source safely afterward to prevent infinite redelivery.
- If side effects already happened outside the broker, redelivery **does not automatically compensate** them.
- For poison messages, enforce retry limits and DLQ/quarantine instead of looping forever.

**A successfully published `ErrorMessage` does not prove JMS transaction rollback or that the source message was retained.**

### 12.2. AMQP/RabbitMQ

RabbitMQ provides ack, reject, nack, requeue, and dead-letter exchange (DLX)/dead-letter queue (DLQ) mechanisms per config. These manage **source message delivery**, not undoing committed bookings or inventory reservations.

| Flow State | Design Choice | Why |
|---|---|---|
| Handler fails before any side effects | Bounded retry/requeue | Message can be reprocessed |
| Handler wrote DB before ack | Dedupe/idempotent write on redelivery | Prevent duplicate writes |
| Error event saved in durable recovery | Ack source per policy once commit is certain | Avoid uncoordinated dual-system retries |
| Compensation failure | Store compensation command, retry separately | Never blindly requeue the entire forward message |
| Message consistently fails schema | DLQ/quarantine | Prevent poison-message loops |

### 12.3. Avoiding Dual Retry Loops

If application advice retries 3 times and broker redelivery retries 5 times, side effects may execute repeatedly without deduplication. For compensation, if a broker also redelivers cancel commands, idempotency must protect both **forward commands** and **compensation commands**.

### 12.4. Do Not Equate DLQ with a Compensation Store

A DLQ isolates unprocessable messages. A saga in `COMPENSATION_REQUIRED` needs **state and a compensation plan**, not merely a message copy in a DLQ. You can enqueue tasks for workers to execute, yet you still need to track modified resources, ordering, and compensation status.

## 13. Kafka: Emitting Compensating Events Instead of "Retracting" Records

### 13.1. What Once Kafka Has Already Published?

Once a Kafka record appears on a topic and other consumers process it, deleting an `ErrorMessage` cannot "undo" all effects. Typically you emit **a new event** describing the business reversal:

~~~json
{
  "eventType": "OrderCancelled",
  "eventId": "event-order-274-cancel-v1",
  "sagaId": "saga-order-274",
  "orderId": "order-274",
  "reasonCode": "FULFILLMENT_FAILED",
  "previousEventReference": "event-order-274-created"
}
~~~

Consumers handle `OrderCancelled` per contract and execute their own compensating actions to restore state. You cannot guarantee all consumers reacted simultaneously merely from producer acknowledgement.

### 13.2. Kafka Transactions Have Scope Limits

Kafka provides transactions for producer operations and, in suitable patterns, consumer offsets. However, this **does not automatically span JDBC databases and external HTTP APIs**. To keep DB updates and Kafka event publishing consistent, use a **transactional outbox** in the DB with an event publisher worker and consumer-side idempotency.

### 13.3. Offsets and Container Error Handlers

In Kafka inbound flows, **Spring for Apache Kafka** provides listener/container error handling (e.g., `CommonErrorHandler` and `DefaultErrorHandler` depending on version). An `ErrorMessage` in Spring Integration does not directly control offset commits or DLTs. When handlers use compensation:

1. Determine whether the error is treated by the container as handled/succeeded;
2. Durably persist saga state and compensation commands before committing per contract;
3. Dedupe replayed records by event ID and business key;
4. Never publish `OrderCancelled` twice causing non-idempotent double compensation;
5. Test restarts, rebalances, and delayed callbacks.

### 13.4. DLT Differs from Compensating Events

A **dead-letter topic (DLT)** holds records unprocessable under a policy. A **compensating event** is an intentional business action (e.g., cancelling an order). A record in a DLT may require manual review; it does not automatically emit `OrderCancelled`.

## 14. JDBC: State Store, Transactions, and Outbox

### 14.1. Saving Saga State Should Be Atomic Where Possible

If a local transaction writes:

- Saga state `COMPENSATION_REQUIRED`;
- Two `PENDING` compensation commands;
- An outbox event for workers to pick up;

commit them **together in one database transaction** when sharing the same DB, ensuring you never record "compensation decided" without saving the commands. Still, HTTP cancel remains outside that transaction; workers execute it afterward and record outcomes independently.

### 14.2. Versioned State Transitions

Illustrative statement example:

~~~sql
UPDATE saga_instance
SET state = 'COMPENSATING',
    version = version + 1
WHERE saga_id = :sagaId
  AND state = 'COMPENSATION_REQUIRED'
  AND version = :expectedVersion;
~~~

Treat the transition as successful only when the updated row count matches expectations. This is **optimistic concurrency**, which does not solve leases, liveness, or transaction isolation on its own across multiple workers.

### 14.3. Outbox Is a Bridge, Not Exactly-Once Magic

An outbox worker reads committed commands, sends them to a broker/HTTP, and marks them sent. If the worker crashes after sending but before updating status, the command may be sent again. Hence **receiver idempotency** and **dedupe** remain essential; outbox closes one class of message loss without eliminating all duplicates.

### 14.4. JDBC Polling Adapters

A JDBC inbound poller can fetch `PENDING` records from the DB; guard claim/locking, timeouts, and retry states. If the poller reads a compensation command and marks it `DONE` before target confirmation, data is easily lost. Use `CLAIMED`/`RUNNING`/`RETRY` states and confirm outcome before `SUCCEEDED`.

### 14.5. Compensating Already-Committed DB Steps

If a reservation was created and committed, releasing it is **a new transaction**. Never delete the reservation row to pretend it never existed: audits typically require recording when it was reserved, when released, and why. If the compensating transaction hits a deadlock, bounded retry is safe when the logic is idempotent.

## 15. Compensation Failure: When Compensation Itself Fails

### 15.1. Do Not Assume Compensation Always Succeeds

A `CancelShipment` call can hit HTTP `503`. A `ReleaseInventory` update can hit a database deadlock. A refund transaction can be rejected due to payment state. When compensation fails, you need **a dedicated error-handling lifecycle**, not merely rethrowing `ErrorMessage` and hoping the entire saga magically reverts to its initial state.

### 15.2. State Machine of Each Compensation Command

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> RUNNING: Worker claims
    RUNNING --> SUCCEEDED: Compensation verified
    RUNNING --> RETRY: Transient error
    RETRY --> RUNNING: Due and within budget
    RUNNING --> RESULT_UNKNOWN: Timeout / unclear outcome
    RESULT_UNKNOWN --> RUNNING: Reconciliation shows not applied
    RESULT_UNKNOWN --> SUCCEEDED: Reconciliation confirms applied
    RUNNING --> MANUAL_REVIEW: No longer safe to auto-compensate
    RETRY --> MANUAL_REVIEW: Retries / deadline exhausted
    SUCCEEDED --> [*]
~~~

### 15.3. Policies When Compensation Fails

| Scenario | Handling Approach |
|---|---|
| HTTP 503 from cancel endpoint | Bounded backoff retry using the same idempotency key |
| Timeout unsure if cancel succeeded | Query status, keep `RESULT_UNKNOWN` |
| API reports shipment already delivered | Do not retry cancel infinitely; open return/refund/manual workflow |
| DB release deadlock | Retry new transaction with concurrency guard |
| Refund rejected by business rules | Escalate to finance/ops, do not flip to `COMPENSATED` |
| Worker crashes while command `RUNNING` | Use lease expiry and idempotency to reclaim |
| Committed deadline expired | Alert owner, record external risk and compensating control |

### 15.4. Mark COMPENSATED Only With Sufficient Evidence

A saga must not be marked `COMPENSATED` merely because all compensation commands were **enqueued**, **published**, or returned HTTP `202`. Require confirmation evidence per step contract; if one step cannot be compensated, the saga may end in `MANUAL_REVIEW`/`FAILED_TERMINAL` with a business dossier.

### 15.5. Compensation of a Compensation?

Do not automatically create commands reversing a compensation when it fails, as that can create infinite alternating chains. If a refund was issued erroneously, fixing it may require a separate approved transaction rather than "auto-recharging" the customer. Financial and legal policies must have explicit authorization.

## 16. Case Study: Error Handling and Compensation in B2B Delivery Flow

### 16.1. Business Context

Company A receives orders from Partner B via SFTP. CSV files contain multiple orders with unique business keys scoped per partner. Spring Integration reads the file, transforms into `OrderCommand`, stores state, reserves inventory in the database, calls Carrier C's HTTP API to create a shipment, and emits an `OrderAccepted` event via Kafka. Another service consumes `OrderAccepted` to issue invoices.

Requirements:

1. Never create duplicate orders when the SFTP poller re-reads a file.
2. If an order is invalid, quarantine the record without creating a shipment.
3. If a shipment was created yet the flow is cancelled, send a cancel shipment command before releasing inventory per policy.
4. If Kafka publish fails transiently, **do not immediately cancel the whole booking** if the outbox can retry and the business still wants completion.
5. If HTTP `CreateShipment` outcome is unclear, query status before recreating or compensating.
6. If compensation fails, maintain clear state and ownership.

### 16.2. Step-by-Step Data Design

| Step | Forward Action | Success Evidence | Compensation If Needed |
|---|---|---|---|
| S0 | Receive and validate file | File hash, batchId, orderId | Quarantine on bad data; no side effects yet |
| S1 | Create order and reserve stock in DB | orderId, reservationId, commit | Release reservation / mark order cancelled |
| S2 | POST CreateShipment to C | shipmentId or confirming status lookup | CancelShipment per C's contract |
| S3 | Write OrderAccepted outbox | Committed outbox event ID | Do not delete emitted event; may emit OrderCancelled |
| S4 | Kafka publisher sends event | Broker acknowledgement and outbox status | Compensating/correction event per consumer contract |

Some applications write `S1` and `S3` in the same local DB transaction so the intent to emit the event is committed alongside order state. HTTP `S2` remains an external boundary managed separately.

### 16.3. Scenario A — Validation Error Before Any Side Effect

A file has a nonexistent product code. The transformer/validator throws an exception before creating a reservation. The error flow should:

1. Locate file/batch/record from context;
2. Classify as `INVALID_INPUT`;
3. Record `REJECTED` status and quarantine the record/file per batch rules;
4. Report the error to B through the appropriate channel;
5. Create no release/cancel compensation commands because **no forward step succeeded to compensate**.

If one file holds multiple orders and one order fails, the contract must specify **all-or-nothing for the file** vs. **per-order partial acceptance**. Compensation must follow committed business units rather than wiping every order in a batch when a single row fails.

### 16.4. Scenario B — HTTP CreateShipment Timeout

`S1` reserved stock. `S2` sends `CreateShipment` and times out; Carrier C may have created the shipment. Error handler:

1. Record saga state `RESULT_UNKNOWN` at `S2`;
2. Never resend `CreateShipment` with a new key;
3. Query C using the stable request ID/idempotency key;
4. If C confirms the shipment exists, store `shipmentId` and decide to proceed forward or cancel;
5. If C confirms it was not created, perform bounded retry or compensate `S1` per policy;
6. If C cannot answer, open `MANUAL_REVIEW`, avoiding both duplicate creation and mistaken cancellation.

**Checkpoint:** the lookup API's answer must be trustworthy. Never infer "not created" merely from a "cache miss".

### 16.5. Scenario C — Shipment Created, Then Business Cancels

Both `S1` and `S2` `SUCCEEDED`. The order is cancelled because Partner B confirms delivery cannot proceed. Coordinator creates two compensation commands:

~~~text
1. CANCEL_SHIPMENT(shipment-S274)
2. RELEASE_RESERVATION(reservation-R274)
~~~

Depending on dependencies, verify `CANCEL_SHIPMENT` before releasing the reservation so stock is not short-allocated. Once both compensations succeed, update order status `CANCELLED` and saga `COMPENSATED`. If C reports the shipment was already delivered, switch to an owned return/refund workflow rather than assuming cancellation worked.

### 16.6. Scenario D — Transient Kafka Failure After Earlier Steps Succeeded

Order is created, shipment confirmed, and `OrderAccepted` outbox awaits send. Kafka producer times out. If the business goal is **completing the order and publishing the event**:

- Keep the saga waiting to publish or mark business complete with event pending per contract;
- Let the outbox publisher retry idempotently;
- Track delay, retry budget, alerts, and consumer lag;
- Do not auto-cancel the shipment simply because Kafka blinked for a few minutes if the event can be safely resent.

Only if a business deadline expires and policy mandates cancelling the order should you trigger compensation with a clear reason. **A technical error at the final step is not automatically a business cancellation request.**

### 16.7. Scenario E — CancelShipment Succeeded, Response Lost

The compensation command calls HTTP cancel and times out after C already cancelled. If the worker retries with a different key, C may return a conflict or charge duplicate cancellation fees. Mark `RESULT_UNKNOWN`, query status by `shipmentId`/cancel key, confirm cancellation, and only then mark the command `SUCCEEDED`.

### 16.8. Sequence Diagram

~~~mermaid
sequenceDiagram
    participant S as SFTP poller
    participant I as Spring Integration flow
    participant DB as Saga state + Inventory DB
    participant P as Delivery API
    participant E as Error flow
    participant W as Compensation worker
    S->>I: CSV file / order-274
    I->>DB: Reserve inventory, record S1_SUCCEEDED
    DB-->>I: reservation-R274
    I->>P: CreateShipment with idempotency key
    P-->>I: shipment-S274
    I->>DB: Record S2_SUCCEEDED
    Note over I: Business cancellation arrives
    I->>DB: Persist COMPENSATION_REQUIRED and commands
    DB-->>E: Recovery work becomes available
    E->>W: CancelShipment command
    W->>P: Cancel shipment-S274
    P-->>W: Cancel confirmed
    W->>DB: Mark C2_SUCCEEDED
    E->>W: ReleaseReservation command
    W->>DB: Release reservation-R274 idempotently
    DB-->>W: Release confirmed
    W->>DB: Saga COMPENSATED + audit
~~~

The diagram depicts **business-triggered cancellation**; if a handler raises an error and an error publisher is present, an `ErrorMessage` can trigger failure recording and compensation decisions. A saga workflow **does not require every cancellation to begin from an ErrorMessage**—business cancellations are equally valid triggers.

### 16.9. Completion Evidence

An order is recorded as `COMPENSATED` when:

- Business/saga ID and confirmed forward steps exist;
- All necessary compensation commands executed against the right targets;
- C confirmed the shipment is voided or in a valid replacement compensating state;
- Inventory holds no stale active reservation;
- Audit captures cancellation reason, decision-maker/policy, and results;
- No `FAILED` or unresolved `RESULT_UNKNOWN` compensation tasks remain.

## 17. Testing Error Flows and Compensation

### 17.1. Testing Error Models and Routing

**Unit tests** should verify:

- The error handler receives `ErrorMessage`, reads `Throwable` and `failedMessage` if present;
- When `failedMessage` is null, `originalMessage` can still yield `sagaId`;
- When both lack `sagaId`, the handler routes the uncorrelated error to operations, **never picking a random saga to cancel**;
- Duplicate errors for the same `sagaId` do not create multiple compensation commands;
- Decisions for retry/compensate/manual rely on saga state, not exception class alone.

### 17.2. Testing a Service Activator Receiving ErrorMessage

Method-level JUnit example using a test-supplied fake service:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandlingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

class SagaErrorRouterTest {

    @Test
    void capturesSagaIdFromFailedMessage() {
        AtomicReference<String> observedId = new AtomicReference<>();

        SagaFailureService fakeService = new SagaFailureService() {
            @Override
            public void recordAndScheduleDecision(
                    String sagaId, Throwable cause) {
                observedId.set(sagaId);
            }

            @Override
            public void recordUncorrelatedFailure(Throwable cause) {
                throw new AssertionError("Unexpected uncorrelated failure");
            }
        };

        Message<String> failed = MessageBuilder
                .withPayload("create-shipment")
                .setHeader("sagaId", "saga-order-274")
                .build();

        ErrorMessage error = new ErrorMessage(
                new MessageHandlingException(failed, "HTTP timeout"));

        new OrderSagaErrorRouter(fakeService).onError(error);

        assertEquals("saga-order-274", observedId.get());
    }
}
~~~

This example assumes `OrderSagaErrorRouter` and `SagaFailureService` are placed in appropriate source files as in Section 6; it is a **unit test for `sagaId` extraction logic**, not verifying that a real integration flow published the `ErrorMessage`. Production requires tests for durable writes and idempotency.

### 17.3. Fault Injection Matrix

| Fault Point | Simulation | Expectation |
|---|---|---|
| Parse before S1 | Schema-invalid CSV | Quarantine, no compensation created |
| DB S1 before commit | Deadlock/rollback | No active reservation; safe retry |
| DB S1 after commit, before reply | Crash | Reconcile via `reservationId`/business key |
| HTTP S2 before send | Deterministic connection failure | Retry or compensate S1 per policy |
| HTTP S2 after send | Timeout with unknown outcome | `RESULT_UNKNOWN`; query C before deciding |
| Kafka S3/S4 | Broker unavailable | Outbox retry, no unnecessary auto-cancel |
| CancelShipment | 503 | Retry with same key, backoff, no premature release |
| CancelShipment | 202 Accepted | Await confirmation, do not mark `SUCCEEDED` yet |
| ReleaseInventory | Duplicate command | Idempotent no-op, stock not added twice |
| Worker | Crash after cancel API, before DB update | Reclaim, query status, prevent duplicate cancel |
| Error channel | No subscriber / failing handler | Preserve failure in durable store or surface blocker |
| Multi-worker | Two workers claim same command | Only one performs valid state transition |

### 17.4. Testing Adapter Semantics

A test that merely asserts an `ErrorMessage` was received **is insufficient**. Verify File filter/SFTP remote file state, HTTP side effects, JMS/AMQP ack/redelivery, Kafka offset/outbox, and DB commits. For broker-backed adapters, use an appropriate integration test environment to verify real container/transaction behavior.

### 17.5. Assertions on Target State

Assertions should check business outcomes:

- No duplicate shipment created when retrying the same request;
- Inventory never released more than once;
- Never marked `COMPENSATED` before confirmation from C;
- After restart, `PENDING`/`RETRY` commands still execute;
- Late callbacks never resurrect already-compensated steps;
- No duplicate `OrderCancelled` events causing duplicate consumer effects;
- Unrelated orders continue processing normally.

## 18. Observability, Auditing, and Alerting

### 18.1. Monitor Both Flows Separately

**Forward flow:** order success rate, latency, retries, pending outbox, inbound/outbound errors.

**Compensation flow:** count of `COMPENSATION_REQUIRED` sagas, `PENDING`/`RETRY`/`RESULT_UNKNOWN` commands, compensation latency, deadline breaches, and cases needing manual action.

Never fold "an order that failed and was compensated" into "successfully completed orders": they are two distinct business outcomes.

### 18.2. Reference Metrics

| Metric | Observed Value |
|---|---|
| `saga_forward_completed_total` | Sagas completing forward |
| `saga_compensation_required_total` | Sagas requiring compensation |
| `saga_compensated_total` | Sagas with verified compensation |
| `saga_compensation_failed_total` | Failed compensation cases |
| `compensation_command_retries_total` | Retry cost per step type |
| `compensation_pending_age` | Age of pending commands |
| `saga_result_unknown_count` | External operations with unknown outcomes |
| `saga_manual_review_count` | Cases needing human action |
| `outbox_pending_count` | Unsent event/command backlog |
| `error_handler_failure_total` | Errors inside the error handler itself |

Never use `sagaId`, `orderId`, or `customerId` as **high-cardinality metric labels**. Use traces/logs to look up individual cases.

### 18.3. Safe Logging and Correlation

A compensation log should include:

~~~text
flow=delivery-compensation
sagaId=saga-order-274
commandId=comp-saga-274-cancel-shipment
step=CANCEL_SHIPMENT
attempt=2
outcome=RETRY_SCHEDULED
errorCategory=TRANSIENT
correlationId=import-batch-012
~~~

Avoid logging access tokens, API keys, payment details, personal file contents, or response payloads containing sensitive data. Propagate correlation across inbound adapters, error flows, command workers, and outbound gateways using intentional headers/context.

### 18.4. Impact-Based Alerts

Priority alerts:

- Saga stuck in `RESULT_UNKNOWN` past allowed threshold;
- Compensation command exhausted retries or approaching deadline;
- Payment captured without completed refund;
- Shipment created while booking is in an inconsistent state;
- Compensation queue stalled despite zero exceptions;
- Recovery store/outbox unavailable or error handler repeatedly failing.

**Zero new ErrorMessages does not prove recovery is healthy**: workers may have stopped polling or queues may be jammed. Monitor last-successful-processing, backlog, and health indicators.

### 18.5. Audits Must Explain Compensation Decisions

Record before/after states, trigger source, deciding human or policy, target IDs, commands, verification results, retry counts, sanitized exceptions, and manual overrides. Retain financial/contractual evidence per retention policy; never purge historical transactions simply because they were compensated.

## 19. Security and Least Privilege in Compensation Flows

### 19.1. Compensation Commands Are Often Privileged

`CancelShipment`, `RefundPayment`, `ReleaseReservation`, `RevokeCredential`, and `DeleteRemoteFile` are all **state-mutating actions**. An error flow may ingest data from external systems; never let partner-supplied error data dictate **resource IDs, tenants, amounts, or compensation command permissions**.

Before executing:

1. Authenticate the producer or error event source;
2. Look up the saga in the trusted state store by validated ID;
3. Verify tenant, contract, resource owner, and business transaction;
4. Fetch target IDs and amounts/quantities from persisted steps—never blindly from `ErrorMessage` payloads;
5. Verify the actor/service principal holds the exact scope for the compensating adapter;
6. Audit both the action and decision.

### 19.2. Preventing Confused Deputy Attacks

Suppose an external HTTP client can freely pass `sagaId` and `errorChannel` headers. Without validation, a client could trick the error router into cancelling another tenant's booking. Separate **user-supplied correlation** from **trusted saga identity**, validate/map at entry points, and restrict `errorChannel` routing.

### 19.3. Separate Forward and Compensation Credentials When Needed

A compensating API like refund may require higher privileges than charge. Never grant global refund credentials to every integration flow. Use dedicated service principals, OAuth scopes, least privilege, approval/amount limits for sensitive compensations, and store credentials in a secret manager.

### 19.4. Manual Operations Authorization

Manual recovery must protect against operators clicking retry/refund repeatedly. Require:

- Appropriate roles and step-up authentication when needed;
- Displaying saga state and side effects before acting;
- Preview/dry-run of planned changes if supported;
- Caps on amounts, deadlines, and high-risk operations;
- Unchanging idempotency keys for the same intent;
- Dual-control approval for high-value financial compensations;
- Auditing and post-action review.

### 19.5. Data Stored in ErrorMessage and Compensation Stores

`failedMessage`/`originalMessage` may hold customer data, tokens, keys, file contents, or payment records. An `ErrorMessage` inside an internal channel **is not inherently a secure data store**. When durable recovery is needed, persist references and minimal payloads, encrypt sensitive fields, enforce read ACLs, configure retention, and never serialize arbitrary full `Throwable`s.

## 20. Operational Runbook: From ErrorMessage to COMPENSATED

### Step A — Locate the Failure

1. Identify the adapter (File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC), flow, and stage;
2. Check whether the exception was thrown directly or published as an `ErrorMessage`;
3. Trace `sagaId`, `businessKey`, and correlation ID via `failedMessage`/`originalMessage` or state store;
4. Do not inspect or export sensitive payloads outside authorized scope;
5. Check whether any task/container/broker error handler already retried earlier.

**Exit criteria:** know where execution stopped and which data sources to inspect.

### Step B — Inspect Forward Side Effects

1. Did `S1` commit the reservation? Does a real `reservationId` exist?
2. Did `S2` create a shipment? Query C if outcome is unknown.
3. Did `S3` write the outbox? Are events already published or pending?
4. Was the SFTP/file input moved, deleted, or marked by a filter?
5. Did the broker ack/commit offset, or is redelivery occurring?
6. Are delayed callbacks, other workers, or retries actively touching the same saga?

**Exit criteria:** durable state clearly shows which steps are confirmed succeeded and which are unknown.

### Step C — Choose the Decision

| Scenario | Action |
|---|---|
| Parse error before side effects | Quarantine, no compensation |
| Transient and forward can still complete | Bounded, idempotent retry |
| HTTP timeout with unknown outcome | Reconcile before retry/compensation |
| Business cancellation after multiple succeeded steps | Create appropriate compensation commands |
| Irreversible effect | Adjustment/reconciliation/manual task |
| Cannot determine source state | Hold in `MANUAL_REVIEW`, do not guess |

**Exit criteria:** decision grounded in business rules and persisted state, not exception type alone.

### Step D — Persist and Execute Compensation Commands

1. Persist `COMPENSATION_REQUIRED`, commands, and outbox within the right transaction boundary.
2. Workers claim commands via lease/version or equivalent concurrency control.
3. Verify permissions, preconditions, and idempotency key before outbound calls.
4. Record actual API/DB/broker results, distinguishing accepted from verified.
5. Perform bounded backoff retries for transient failures.
6. Transition to `RESULT_UNKNOWN`/`FAILED` with an owner when automation is no longer safe.
7. Trigger the next compensating step once dependencies are satisfied.

**Exit criteria:** every command has a recorded status and evidence, not merely a logged error.

### Step E — Verify and Close the Incident

1. Reconcile DB reservations/orders, shipment status, outbox, and affected consumers.
2. Verify no stray side effects remain or any discrepancies are tracked.
3. Record saga as `COMPENSATED`, or `MANUAL_REVIEW`/`FAILED_TERMINAL` as appropriate.
4. Summarize impacted message counts, retry/compensation attempts, and recovery duration.
5. Analyze why the forward flow failed and preventive measures.
6. Update tests, alerts, API contracts, or runbooks to prevent recurrence.

**Exit criteria:** final state is auditable and backed by target-system evidence.

## 21. Anti-Patterns in Compensating Error Flows

| Mistake | Consequence | Fix |
|---|---|---|
| Treating ErrorMessage as saga state | Restarts lose record of completed steps | Durable saga store and compensation commands |
| Every exception triggers cancellation | Cancels orders that could safely retry | Classify errors, steps, and business policy |
| Retrying the whole flow after a late error | Duplicate reservations, shipments, charges | Per-step idempotency and state machine |
| Assuming DB rollback rolls back HTTP/Kafka | External side effects remain | Compensation across external boundaries |
| Assuming HTTP timeout means unexecuted | Duplicate creation / mistaken cancellation | `RESULT_UNKNOWN` and reconciliation |
| Compensating with DELETE losing history | Lost audit trail / business violations | New compensating transaction, clear state |
| Resending ErrorMessage into business input | Throwable violates payload contract | Reconstruct schema-valid command |
| Unbounded compensation retries | Retry storms, API costs, worker exhaustion | Retry budget/backoff/deadline |
| Using a new idempotency key on every retry | Target treats each attempt as a new intent | Stable key per command |
| Running release inventory twice | Stock over-credited | Reservation state and deduplication |
| Marking compensation succeeded on HTTP 202 | Request may still be pending | Await final status or reconcile |
| Two PublishSubscribeChannel subscribers both compensating | Double compensation | Single coordinator owns side effects |
| Using broker DLQ alone as compensation proof | Unknown which forward steps committed | Saga state and side-effect references |
| Ignoring ack/offset and transactions | Lost or duplicated messages | Test source/broker semantics |
| Issuing refunds without business approval | Fraud and financial risk | Authorization, approval, and audit |
| Ignoring late callbacks | Resurrects compensated state | Version and expected-state checks |
| Forgetting compensation failures | Saga stuck unowned | Separate retries, escalation, and owner |
| Not distinguishing business vs. infrastructure errors | Unnecessary cancellations | Retry/reconcile before cancelling |
| Logging full failedMessage | Secret/PII leaks | Structured metadata, masking |
| Not monitoring compensation backlog | Workers stall silently | Last-success metrics, pending age, alerts |

## 22. Design and Implementation Checklist

### A. Contracts and Business Steps

- [ ] Define business goals and terminal states for every outcome.
- [ ] List side effects of every File/SFTP/HTTP/broker/JDBC endpoint.
- [ ] Distinguish rollbackable, compensatable, irreversible, and unknown-outcome steps.
- [ ] Establish stable business keys/`sagaId`/`correlationId`.
- [ ] Define preconditions, response IDs, and idempotency for each forward action where applicable.
- [ ] Define dependency rules and business compensation order.

### B. Error Flow in Spring Integration

- [ ] Know which exceptions throw synchronously and which are published.
- [ ] Configure error channels/handlers matching real pollers, gateways, or listeners.
- [ ] Read `ErrorMessage` payloads as `Throwable`; handle null `failedMessage`/`originalMessage`.
- [ ] Never allow untrusted routing headers or target IDs to dictate compensation commands.
- [ ] Error observers never execute multiple stateless side effects directly.
- [ ] When an error handler fails, failures are still detected and preserved.

### C. State, Consistency, and Recovery

- [ ] Saga state and compensation commands are durably persisted.
- [ ] State transitions enforce concurrency/version checks.
- [ ] Transactional outbox or equivalent syncs state and emitted messages.
- [ ] Both forward and compensation commands handle duplicates safely.
- [ ] Timeouts/unknown outcomes have lookup APIs or manual reconciliation.
- [ ] Retries have backoff, limits, deadlines, and final disposition.
- [ ] Never mark `COMPENSATED` before verifying the compensating action.
- [ ] `MANUAL_REVIEW` sagas have an owner and SLA.

### D. Adapter Compatibility

- [ ] File/SFTP has filters, durable references, quarantine, and replay policies.
- [ ] HTTP has response contracts, idempotency, status lookup, or unknown rules.
- [ ] JMS/AMQP has proper acknowledgments, redelivery, and DLQs.
- [ ] Kafka has offsets/commits, DLTs, and compensating events per consumer contract.
- [ ] JDBC has transaction boundaries, reservation states, and outbox where needed.
- [ ] Never assume a local transaction spans external systems.

### E. Testing and Operations

- [ ] Test every failure point before and after side effects.
- [ ] Test crashes/restarts, duplicate deliveries, late events, and concurrent workers.
- [ ] Test compensation failures, HTTP `202`, and unknown timeouts.
- [ ] Test isolation against compensating the wrong tenant or resource.
- [ ] Maintain logs/traces/correlation, metrics, and alerts on backlogs and deadlines.
- [ ] Maintain runbooks, audits, operator permissions, and sensitive-data policies.

## 23. Self-Check Questions

**Question 1. How does a compensating error flow differ from the default errorChannel?**

**Answer:** `errorChannel` is a `MessageChannel` receiving published `ErrorMessage`s. A compensating error flow is an **application-designed business workflow** that evaluates side effects, decides retry/reconciliation/compensation, and verifies compensating actions. Having `errorChannel` does not give you a saga.

**Question 2. When CSV validation fails before DB writes and HTTP calls, is compensation needed?**

**Answer:** Usually no, because no business side effects occurred. Reject/quarantine and report the data error. If part of a batch already processed, inspect per-record state.

**Question 3. The DB rolled back, yet an earlier partner HTTP call already created a booking. Can we consider the whole workflow rolled back?**

**Answer:** No. A local DB transaction does not cover HTTP. Locate the created booking, decide whether to cancel, and invoke the compensating API with proper authorization, resource ID, and idempotency.

**Question 4. A CreateShipment HTTP request timed out. Should we immediately call CancelShipment?**

**Answer:** Never guess whether it was created. Mark `RESULT_UNKNOWN`, look up by request ID/idempotency key, then decide whether to continue, retry, or compensate based on reliable results.

**Question 5. Why does a compensation command need a stable idempotency key?**

**Answer:** Workers or brokers can redeliver the same command. A stable key prevents cancelling/refunding/releasing multiple times for the same intent, alongside recipient state checks and deduplication.

**Question 6. If inventory release runs twice and adds 5 units to stock each time, what bug occurs?**

**Answer:** Stock is over-credited by 5 units. Track `reservationId`/status and use transactions/locks or idempotent APIs so release takes effect once.

**Question 7. When Kafka event publishing fails after DB and HTTP succeeded, must we always cancel the business transaction?**

**Answer:** No. If the business goal remains valid and an outbox was saved, publishing can retry. Cancel only when business policy/deadlines require it; a technical error is not automatically a business cancellation.

**Question 8. Why doesn't an OrderCancelled event "delete" an earlier OrderCreated event?**

**Answer:** Multiple consumers may have already processed the event. `OrderCancelled` is a new business event instructing consumers to adjust state per contract, not a recall of past records.

**Question 9. Do ErrorMessage.getOriginalMessage() and MessagingException.getFailedMessage() always hold the full saga data?**

**Answer:** No. They can be null or hold only the message at the point of failure. Durable saga state and correlation IDs are the reliable basis for knowing which steps succeeded.

**Question 10. Is a single subscriber on global errorChannel safe for compensating every flow?**

**Answer:** Generally unsuitable. Each flow has different business policies, side effects, and retries. Use dedicated coordinators/recovery handlers, reserving the global error channel for general observability and routing.

**Question 11. In JMS/AMQP, does publishing an ErrorMessage mean the broker will redeliver?**

**Answer:** No. Ack, nack, rollback, and redelivery are governed by the container/broker and how exceptions are handled. Verify explicitly and avoid acking before recovery state is safely persisted.

**Question 12. If a cancel API returns 202 Accepted, can we mark the command SUCCEEDED?**

**Answer:** Not necessarily. `202` may only confirm request acceptance; wait for the final outcome or query status per contract before concluding compensation finished.

**Question 13. Why must compensation commands be stored in a database or durable queue?**

**Answer:** `ErrorMessage` on in-memory channels is not guaranteed to survive restarts. Durable storage supports retries, auditing, concurrency control, and resuming compensation after worker crashes.

**Question 14. If a compensation command is in RUNNING state when a worker crashes, how should it be handled?**

**Answer:** Use lease/claim expiry, check actual external outcome, and enforce idempotency before re-running. Never blindly flip back to `PENDING` and resend while ignoring pre-crash side effects.

**Question 15. Can RefundPayment be treated as an identical undo of a charge?**

**Answer:** No. Refunds are normally separate transactions with their own history, fees, deadlines, conditions, and accounting obligations; they may require approval.

**Question 16. When should a saga move to MANUAL_REVIEW?**

**Answer:** When outcome cannot be verified, compensation exhausted retries/deadlines, the target no longer allows cancellation, approval permissions are missing, or another automated action risks harm. Assign an owner, current state, and remediation plan.

**Question 17. Are transactions needed for saga state and outbox?**

**Answer:** Commit them atomically when in the same DB and updated for the same decision. Yet an outbox can still re-emit messages upon crashes, so receivers still need idempotency.

**Question 18. How do you prove a saga is COMPENSATED?**

**Answer:** Verified compensating status at involved resources, no critical pending/unknown commands remaining, data consistent with policy, and complete audits. Enqueuing commands or logging an `ErrorMessage` is not enough.

## 24. Conclusion

A **compensating error flow** turns a technical integration failure into a **business consistency recovery decision**. In Spring Integration, **MessageChannel**, **adapters/gateways**, **pollers**, **ErrorMessage**, and **errorChannel** transport messages and failure details. Yet the hardest part still belongs to the application: **determining committed steps, persisting state, choosing retry vs. compensation, executing commands safely, and verifying results**.

Remember six principles:

1. **Not every error needs compensation:** pre-side-effect validation differs from post-commit timeouts.
2. **Rollback does not cross boundaries freely:** a DB transaction does not automatically undo HTTP, SFTP, JMS, AMQP, or Kafka effects.
3. **Never guess unknown results:** timeouts require reconciliation before retrying or cancelling.
4. **Compensation must be idempotent and durable:** persist saga state, command IDs, resource IDs, retry budgets, and owners.
5. **Compensation can fail too:** design `MANUAL_REVIEW`, alerts, and operational runbooks.
6. **Conclude completion only upon verification:** an `ErrorMessage`, an HTTP `202`, or an enqueued command does not prove business consistency.

When **ErrorMessage/errorChannel** are properly paired with **saga coordination, transactions/outbox, idempotency, reconciliation, and per-adapter error policies**, Spring Integration systems avoid message loss, duplicate processing, and dangling side effects across external integrations.

### Further Reading

- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`, `errorChannel`, `MessagePublishingErrorHandler`, and error strategies.
- [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): building `IntegrationFlow`, `MessageChannel`, and endpoints.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundaries, propagation, and rollback.
- [Enterprise Integration Patterns — Compensating Action](https://www.enterpriseintegrationpatterns.com/): reference principles for compensation in integration systems.

Java, JSON, YAML, SQL, and Mermaid snippets in this lesson are **educational examples**; channel names, interfaces, partner APIs, and saga schemas must all be adapted for real applications. Verify Spring Boot/Spring Integration versions, confirm adapter/container contracts, and run integration tests before production deployment.
