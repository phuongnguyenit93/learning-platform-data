# Implementing Compensating Actions When Payment or Shipping Fails

In the **Business Workflow Project** chapter, an order typically traverses multiple independent services: reserving inventory, authorizing or capturing payment, creating a shipment, and updating delivery status. Each service has its own database and failure boundary. If a step fails after earlier steps have committed, a single database rollback cannot revert the entire system to its initial state. The workflow needs compensating actions to handle changes that have already occurred.

This lesson belongs to the **CLOUD_SERVERLESS** module, focusing on developing and deploying applications under the serverless model, particularly Java functions triggered by HTTP, messages, or events. Learners address triggers, state, access permissions, retries, idempotency, cold starts, scaling, and cost to determine when to use FaaS. This lesson applies those principles to a business workflow: persisting durable state, orchestrating steps, executing bounded retries, and compensating completed side effects when payment or shipping cannot proceed.

## 1. The Order Workflow Problem

Suppose a customer places an order with three items. The system needs to perform:

1. Create the order in the PENDING state.
2. Reserve items in inventory.
3. Authorize the payment.
4. Create the shipment and hand over details to the carrier.
5. Capture the payment according to business policy.
6. Transition the order to CONFIRMED or FULFILLING.

Each step may run in a separate service or Lambda. One step may commit successfully while the next step fails.

For example: inventory has reserved stock and payment has been authorized, but the shipping provider rejects the delivery address. Simply marking the order FAILED leaves stock reserved and the card limit held. The workflow must execute corresponding compensating actions: void payment authorization and release inventory reservation.

~~~mermaid
flowchart TD
    A["Create order"] --> B["Reserve inventory"]
    B --> C["Authorize payment"]
    C --> D["Create shipment"]
    D --> E["Capture payment"]
    E --> F["Confirm order"]
    D -->|"Permanent failure"| X["Compensation workflow"]
    E -->|"Permanent failure"| X
    X --> V["Void shipment / cancel label"]
    V --> P["Void authorization or refund"]
    P --> I["Release inventory when safe"]
    I --> R["Mark order cancelled / needs review"]
~~~

The compensation order depends on which steps succeeded and the actual state of each system. Never run a fixed list of compensations without checking forward-action outcomes.

## 2. What Is Compensation?

Compensation is a new business operation intended to mitigate or reverse the impact of a committed step. It is not a physical rollback of the previous transaction.

Examples:

- Reserve inventory → Release reservation.
- Authorize payment → Void authorization.
- Capture payment → Refund payment.
- Create shipping label → Void label if the carrier has not yet accepted the parcel.
- Carrier already accepted parcel → Request intercept/return; do not assume label cancellation will retrieve the parcel.
- Send confirmation email → May send a correction email; cannot recall an already sent email.

Compensation can fail, take time, or achieve only partial recovery. A refund may take several days to appear on a statement. Goods that have left the warehouse may need to wait for carrier return before being restocked.

Therefore, the final state is not necessarily an exact replica of the pre-workflow state. States such as REFUND_PENDING, RETURN_IN_PROGRESS, or MANUAL_REVIEW may be needed.

## 3. Distinguishing Retries, Forward Recovery, and Compensation

These three responses are not interchangeable:

| Handling Strategy | Use When | Example |
|---|---|---|
| Retry step | Failure is likely transient; no need to change business direction yet | Payment API returns 503 |
| Forward recovery | Workflow can still complete via an alternative execution path | Primary carrier fails; fall back to secondary carrier |
| Compensation | Cannot or should not proceed; need to handle committed side effects | Invalid address; void authorization and release reservation |

Do not trigger compensation immediately upon a timeout. A timeout only indicates the caller did not receive a response in time; the downstream service may have already executed the operation. Before deciding to compensate, query status using the operation ID or idempotency key if the outcome is unclear.

A transient error should be retried within bounds. Only when the retry budget is exhausted or a permanent error occurs does the orchestrator decide whether to pursue an alternative path or start compensation.

## 4. Mapping Forward Actions and Compensations

Each step in a saga needs a primary action, durable outcome, and compensating action:

| Forward Action | Outcome to Persist | Compensation | Limitations |
|---|---|---|---|
| Create order | orderId, version | Cancel order | May need to retain audit record |
| Reserve inventory | reservationId, expiry | Release reservation | Only release reservations still valid |
| Authorize payment | authorizationId | Void authorization | May expire, or provider may not support void |
| Capture payment | captureId | Refund capture | Refund is a new transaction; may be asynchronous |
| Create shipment label | shipmentId, labelId | Void label | Effective only before certain handover milestones |
| Carrier accepts parcel | trackingId, acceptedAt | Intercept/return request | Retrieval is not guaranteed |
| Send notification | message reference | Send correction | Cannot recall a delivered notification |

This mapping must be confirmed by each domain owner. Action names and compensation capabilities depend on the APIs of the inventory system, payment provider, and shipping carrier.

Do not share a single generic `compensate()` function across all step types. Each compensation needs its resource ID, current state, business constraints, and its own idempotency key.

## 5. Saga Pattern

A Saga is a workflow composed of multiple local transactions. Each local transaction commits within its own service; if the workflow cannot proceed, the saga runs the corresponding compensations for completed steps.

A saga stores at least:

- Saga ID and business entity ID.
- Current workflow state.
- Outcomes of each forward step.
- Resource IDs returned by downstream services.
- Compensation status and attempt counts.
- Correlation IDs and idempotency keys.
- Deadlines, retry policies, and update timestamps.
- Last error and intervention-required status.

A saga does not create a distributed ACID transaction. It manages progress and recovery state across multiple independent transactions.

### 5.1. Orchestration vs. Choreography

There are two ways to structure a saga:

| Style | How It Works | Best Suited When |
|---|---|---|
| Orchestration | An orchestrator stores state and invokes each participant | Workflows have branching, timeouts, compensation, and clear auditing |
| Choreography | Services emit events; other services react and emit subsequent events | Flows have few steps, low coupling, and express cleanly as events |

Orchestration makes it clear which steps completed and which need compensation. Choreography reduces reliance on a central coordinator but can become hard to trace when there are many branches and compensations.

For payment and shipping workflows with multiple side effects, an orchestrator usually makes operations and incident investigation clearer. Participant services still retain ownership of their own data and local transactions.

## 6. Designing the Workflow State Machine

An illustrative state machine:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> INVENTORY_RESERVED
    INVENTORY_RESERVED --> PAYMENT_AUTHORIZED
    PAYMENT_AUTHORIZED --> SHIPMENT_CREATED
    SHIPMENT_CREATED --> PAYMENT_CAPTURED
    PAYMENT_CAPTURED --> CONFIRMED
    INVENTORY_RESERVED --> COMPENSATING: Payment failed
    PAYMENT_AUTHORIZED --> COMPENSATING: Shipping failed
    SHIPMENT_CREATED --> COMPENSATING: Capture failed
    COMPENSATING --> CANCELLED: Compensation complete
    COMPENSATING --> MANUAL_REVIEW: Compensation failed
    CONFIRMED --> [*]
    CANCELLED --> [*]
~~~

Core states:

- PENDING: workflow created.
- INVENTORY_RESERVED: reservation committed.
- PAYMENT_AUTHORIZED: provider confirmed authorization.
- SHIPMENT_CREATED: shipment or label created.
- PAYMENT_CAPTURED: payment captured.
- CONFIRMED: forward workflow completed.
- COMPENSATING: executing one or more compensating actions.
- CANCELLED: mandatory compensations completed.
- MANUAL_REVIEW: cannot recover safely automatically.

Real state machines may need additional states such as PAYMENT_UNKNOWN, SHIPMENT_ACCEPTED, REFUND_PENDING, or RETURN_IN_PROGRESS. Do not force every outcome into SUCCESS/FAILED if downstream systems have intermediate states.

## 7. Determining Compensation by Failure Point

A workflow only compensates forward actions that succeeded or may have succeeded. Examples:

| Failure Point | Completed Steps | Next Action |
|---|---|---|
| Reserve inventory fails | Create order | Cancel order or mark unprocessable |
| Authorize payment fails | Create order, reserve inventory | Release reservation, cancel order |
| Create shipment fails | Reserve inventory, authorize payment | Void authorization, release reservation |
| Capture payment fails definitively | Reserve, authorize, shipment label | Void label if still permitted, void authorization, release inventory when safe |
| Capture times out, outcome unknown | Prior steps and capture request | Query provider by idempotency key before retrying or compensating |
| Carrier rejects after accepting parcel | Inventory, payment, shipment handoff | Intercept/return, refund per policy, restock only once goods are confirmed returned |

If a step never succeeded, no compensation is needed for that step. If the outcome is unknown, reconcile actual state first.

## 8. Compensating in Reverse Order

In a sequential saga, compensations typically run in reverse order of committed forward actions. If inventory was reserved, payment authorized, and a shipment label created, then when capture fails, the workflow can:

1. Void the shipment label if the carrier has not received the parcel.
2. Void the payment authorization if not yet captured.
3. Release the inventory reservation.
4. Update the order to CANCELLED or NEEDS_REVIEW.

Reverse order reduces dependencies on created resources. However, the actual compensation order must follow domain semantics. For instance, do not release inventory if the carrier has already picked up the parcel and the product has not returned to the warehouse.

With parallel steps, there is no single linear reverse order. The orchestrator must wait for active branches to finish, then run compensations for each branch according to the dependency graph.

## 9. Distinguishing Authorization, Capture, and Refund

Payments typically have multiple states:

- **Authorize:** provider verifies and holds the limit; funds have not necessarily transferred.
- **Capture:** requests settlement of funds based on the authorization.
- **Void:** cancels an uncaptured authorization or cancels a transaction per provider capabilities.
- **Refund:** returns captured funds; this is a new transaction.

If shipping fails before capture, voiding the authorization may be appropriate. If capture already succeeded, a refund is required. Do not call void on an already captured charge unless the provider explicitly supports those semantics.

A refund may be in PENDING, SUCCEEDED, or FAILED state. The order should only transition to states matching the refund result; do not mark REFUNDED immediately upon sending the request.

Every payment request needs a stable operation ID and idempotency key. On timeout, query the provider before issuing a new operation that could create a duplicate charge or refund.

## 10. Distinguishing Label Creation from Carrier Handover

Shipping also has distinct milestones:

1. Create shipment record.
2. Purchase or generate shipping label.
3. Schedule pickup.
4. Carrier scans and accepts parcel.
5. Parcel in transit.
6. Delivered successfully or failed.

Voiding a label before carrier acceptance can be a simple compensation. Once the carrier has accepted the parcel, compensation may require an intercept, return-to-sender, or creating a return request. You cannot assume a cancel API stops a parcel already in transit.

Inventory must also be compensated based on physical state. If goods have left the warehouse, releasing a reservation is insufficient; a return workflow and physical inspection are required before adding back to available stock.

## 11. Durable Saga State

Do not keep saga state in static variables or Lambda memory. Execution environments can be replaced, multiple invocations can run concurrently, and retries may land on different instances.

A saga table can contain:

~~~sql
CREATE TABLE business_saga (
    saga_id          VARCHAR(120) PRIMARY KEY,
    order_id         VARCHAR(120) NOT NULL,
    state            VARCHAR(40) NOT NULL,
    current_step     VARCHAR(80),
    version          BIGINT NOT NULL,
    context_json     JSONB NOT NULL,
    last_error_code  VARCHAR(120),
    created_at       TIMESTAMPTZ NOT NULL,
    updated_at       TIMESTAMPTZ NOT NULL
);
~~~

A separate step table:

~~~sql
CREATE TABLE saga_step (
    saga_id          VARCHAR(120) NOT NULL,
    step_name        VARCHAR(80) NOT NULL,
    status           VARCHAR(40) NOT NULL,
    operation_id     VARCHAR(160),
    resource_id      VARCHAR(160),
    attempt_count    INTEGER NOT NULL DEFAULT 0,
    last_error_code  VARCHAR(120),
    updated_at       TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (saga_id, step_name)
);
~~~

One table can serve both forward steps and compensations, provided action type and status are clearly distinguished. Never store full sensitive payment data in `context_json`; store only necessary tokens/references with appropriate access controls.

Every state transition requires optimistic locking or conditional updates so two invocations cannot concurrently drive the saga from a stale version.

## 12. Idempotency for Forward Actions and Compensations

A compensation can be retried if a response is lost or a worker crashes. Therefore, compensations must also be idempotent.

Example keys:

- Forward reserve: sagaId + reserve-inventory.
- Compensation release: sagaId + release-inventory.
- Forward authorize: sagaId + authorize-payment.
- Compensation void: sagaId + void-authorization.
- Compensation refund: sagaId + refund-capture.

Never reuse the same key for a forward action and a compensation, because they are distinct operations.

If inventory release is called twice, the second call must return the processed result or confirm the reservation is already released. If a refund request is retried, the provider must receive the same idempotency key so it does not create two refunds.

In internal databases, use unique constraints/conditional writes. With external providers, use the API's idempotency feature if available and persist the provider operation reference.

## 13. Transactional Outbox and Inbox in a Saga

A participant often needs to both update local state and emit the next event. If the database commits but publishing fails, the saga may hang.

The transactional outbox solves dual-write:

1. In a single transaction, update local business state and insert an outbox event.
2. Commit.
3. Publisher sends the event.
4. Consumer receives the event and uses inbox/idempotency to prevent duplicates.
5. Orchestrator updates saga state based on the committed result.

An outbox publisher can redeliver after a crash. Consumers still require idempotency. Do not mark a step SUCCEEDED merely because a message was published; base it on the participant's result or confirmation event.

## 14. Compensation Failures and Intervention-Required States

Compensations can also fail:

- Payment provider temporarily unavailable.
- Void authorization rejected because funds were already captured.
- Refund stays pending or provider returns an error.
- Shipping carrier cannot intercept.
- Inventory service cannot find the reservation.
- Reservation already expired prior to release.

Do not transition the saga to CANCELLED if mandatory compensations have not completed or been handled per policy. Use states such as COMPENSATION_PENDING, COMPENSATION_FAILED, or MANUAL_REVIEW.

A recovery worker can scan stalled sagas, check leases/deadlines, and resume compensation. Configure retry limits, backoff, alerts, and an operations runbook.

If compensation cannot complete automatically, retain traceable state and create a task for staff. Never delete saga records after errors.

## 15. Timeouts and Unknown Outcomes

Timeouts are difficult because the caller does not know whether the downstream system committed.

Payment capture example:

1. Lambda sends capture request with key K.
2. Payment provider captures successfully.
3. Response is lost.
4. Lambda times out.
5. Saga does not know whether capture succeeded or failed.

Safe actions:

- Do not immediately send a new capture with a different key.
- Query the provider using the authorization/capture reference or idempotency key.
- If capture succeeded, record PAYMENT_CAPTURED and continue.
- If the provider confirms capture did not happen, retry the same operation/key per policy.
- If status remains unknown, stay in PAYMENT_UNKNOWN and route to reconciliation.

Never issue a refund solely because capture timed out. If capture never happened, a refund has no source transaction; if capture did happen, verify the amount and reference before refunding.

## 16. Orchestrator with AWS Step Functions

AWS Step Functions can coordinate Lambda/service steps, persist execution state, apply Retry/Catch, and invoke compensation branches.

Conceptual workflow:

~~~mermaid
flowchart TD
    START["Start order saga"] --> INV["Reserve inventory"]
    INV --> PAY["Authorize payment"]
    PAY --> SHIP["Create shipment"]
    SHIP --> CAP["Capture payment"]
    CAP --> DONE["Confirm order"]
    INV -->|"Failure"| FAIL["Handle failure"]
    PAY -->|"Failure"| REL["Release inventory"]
    SHIP -->|"Failure"| VOID["Void authorization"]
    VOID --> REL
    CAP -->|"Failure"| CANCELSHIP["Cancel label or request intercept"]
    CANCELSHIP --> VOID2["Void authorization"]
    VOID2 --> REL
    REL --> CANCEL["Mark cancelled / review"]
    FAIL --> CANCEL
~~~

In Step Functions, you can use:

- Task states for Lambda or service integrations.
- Retry for bounded transient errors.
- Catch to route to compensation branches.
- Choice to branch on business outcomes.
- Wait for backoff or waiting on callbacks.
- Map/Parallel when steps are independent.
- Execution history to investigate progress.

Step Functions persists orchestration state but does not automatically make external side effects idempotent. Each Task needs a stable operation key and must handle the case where the Task succeeded but the state transition was not recorded due to timeout or retry.

### 16.1. Retry and Catch Must Differentiate Errors

Do not apply Retry to every exception. For example:

- ThrottlingException, service unavailable, or network errors: retry with backoff.
- InvalidAddress or PaymentDeclined: typically business failures; transition to compensation.
- AccessDenied: fix permissions, alert; do not retry continuously.
- Timeout with unknown outcome: query operation status before deciding.

Catch can transition to a compensation state, but that branch must know which steps actually committed. Execution input/output should carry durable resource references and step statuses.

## 17. Orchestration in Java

If building a custom Java orchestrator, model each step and compensation explicitly rather than writing a long chain of try/catch blocks.

~~~java
public interface SagaStep<C> {
    String name();

    StepResult execute(C context);

    CompensationResult compensate(C context);
}
~~~

An orchestrator can:

1. Read saga state and version.
2. Claim orchestration ownership via lease/conditional update.
3. Select the next step.
4. Write RUNNING state and operation ID.
5. Call participant with idempotency key.
6. Record success or failure result.
7. If terminal failure, transition state to COMPENSATING.
8. Run compensations for succeeded steps in dependency order.
9. Record completed state or MANUAL_REVIEW.

Do not hold a database transaction open while making HTTP calls to participants. Record intent/operation first, execute the external call, then record the outcome in a separate transaction; participants must be idempotent to handle crashes between steps.

## 18. Java Model for Steps and Compensation

A simple model:

~~~java
public enum StepStatus {
    PENDING,
    RUNNING,
    SUCCEEDED,
    RETRY_WAIT,
    FAILED,
    COMPENSATING,
    COMPENSATED,
    MANUAL_REVIEW
}

public record StepExecution(
        String sagaId,
        String stepName,
        String operationId,
        String resourceId,
        StepStatus status,
        int attempts) {
}
~~~

Compensation needs the resource ID created by the forward action. For instance, `releaseInventory` needs `reservationId`; `voidAuthorization` needs `authorizationId`; `refund` needs `captureId` and `amount`.

Do not derive resource IDs by guessing from `orderId` if the provider returns a separate reference. Save the response/reference immediately after confirming the operation succeeded.

## 19. Java Compensation Example for Payment

~~~java
public interface PaymentGateway {
    AuthorizationResult authorize(
            String orderId,
            long amountMinor,
            String idempotencyKey);

    VoidResult voidAuthorization(
            String authorizationId,
            String idempotencyKey);

    RefundResult refund(
            String captureId,
            long amountMinor,
            String idempotencyKey);

    PaymentStatus findAuthorization(String authorizationId);
}
~~~

Example authorization compensation service:

~~~java
public CompensationResult voidPaymentAuthorization(
        SagaContext context,
        String authorizationId) {

    String key = context.sagaId() + ":void-authorization";

    PaymentStatus current =
            paymentGateway.findAuthorization(authorizationId);

    if (current.isVoided()) {
        return CompensationResult.ALREADY_COMPLETED;
    }

    if (current.isCaptured()) {
        return CompensationResult.REFUND_REQUIRED;
    }

    if (current.isVoidPending()) {
        return CompensationResult.PENDING_CONFIRMATION;
    }

    VoidResult result =
            paymentGateway.voidAuthorization(authorizationId, key);

    if (result.isCompleted()) {
        return CompensationResult.COMPLETED;
    }

    if (result.isAccepted()) {
        return CompensationResult.PENDING_CONFIRMATION;
    }

    return CompensationResult.RETRY_REQUIRED;
}
~~~

This is pseudocode; real provider APIs may not support querying by authorization ID or may return different statuses. In such cases, use the references and reconciliation endpoints provided by the gateway. Only mark COMPLETED when the provider confirms void completion. HTTP 202 usually only means the request was accepted, so remain in PENDING_CONFIRMATION and verify status afterward. If the authorization was already captured, route to the refund workflow rather than attempting to void.

## 20. Java Compensation Examples for Inventory and Shipping

Inventory release:

~~~java
public CompensationResult releaseReservation(
        SagaContext context,
        String reservationId) {

    String key = context.sagaId() + ":release-inventory";

    InventoryResult result =
            inventory.release(reservationId, key);

    return switch (result.status()) {
        case RELEASED, ALREADY_RELEASED ->
                CompensationResult.COMPLETED;
        case TEMPORARY_FAILURE ->
                CompensationResult.RETRY_REQUIRED;
        case NOT_FOUND ->
                CompensationResult.NEEDS_REVIEW;
    };
}
~~~

Shipping cancellation requires checking carrier status:

~~~java
public CompensationResult cancelShipment(
        SagaContext context,
        String shipmentId) {

    ShipmentStatus status = shipping.find(shipmentId);

    if (status.isLabelCreated() && !status.isCarrierAccepted()) {
        return shipping.voidLabel(
                shipmentId,
                context.sagaId() + ":void-label");
    }

    if (status.isCarrierAccepted()) {
        return shipping.requestInterceptOrReturn(
                shipmentId,
                context.sagaId() + ":intercept-shipment");
    }

    return CompensationResult.NEEDS_REVIEW;
}
~~~

These methods and enums are abstractions. In practice, a carrier may not support intercept, or may require fees and approval. Never release stock immediately upon sending a return request; wait until goods are confirmed returned and inspected.

## 21. Compensation for Workflows with Parallel Steps

An order may reserve stock across multiple warehouses or create shipments for multiple packages. If branches run in parallel, some branches may succeed while others fail.

The orchestrator must:

- Store outcomes separately for each branch/package.
- Compensate only resources that were successfully created.
- Not compensate branches with unknown outcomes before querying their status.
- Limit compensation concurrency to avoid overloading downstream systems.
- Wait for mandatory compensations to finish or route failed branches to MANUAL_REVIEW.
- Aggregate order status based on the outcomes of all branches.

If one package is already delivered and another package fails, you cannot automatically refund the entire order and release all inventory. A partial fulfillment/partial refund policy is required.

## 22. Races Between Cancellation, Timeouts, and Callbacks

A customer may cancel an order at the exact moment a payment callback or shipping event arrives. Competing workflows may try to update state concurrently.

Use:

- Saga version and optimistic locking.
- Conditional state transitions.
- Per-action idempotency keys.
- Unique constraints for external event IDs.
- Explicit terminal state policies.
- Reconciliation when external outcomes are unknown.

For example, if an order has already moved to CANCELLING, a `PaymentCaptured` callback must not automatically move the order to CONFIRMED. The callback must be recorded and routed to the appropriate refund/compensation branch.

Never let a late-arriving callback overwrite the current state machine simply because it was processed last.

## 23. Observability for Sagas and Compensation

Each log/trace must link:

- sagaId.
- orderId or business key.
- stepName and actionType.
- operationId/idempotencyKey reference.
- resourceId such as reservationId, authorizationId, shipmentId.
- attempt and retry delay.
- compensation status.
- correlationId/causationId.
- failure category and downstream response class.

Metrics to track:

- Active sagas by state.
- Sagas past deadline.
- Pending/failed compensations.
- Retry counts per step.
- UNKNOWN payments and REFUND_PENDING counts.
- Pending shipment intercepts/returns.
- Expiring inventory reservations.
- Manual review backlog.
- Time from failure to compensation completion.

Never log payment tokens, card data, or secrets. Do not use `sagaId`/`orderId` as high-cardinality metric dimensions; keep them in logs and traces.

## 24. Testing Compensation

Test suites must cover forward success, failure, and compensation failure.

| ID | Scenario | Expected Outcome |
|---|---|---|
| SAGA-01 | Reserve inventory fails | Payment is not called; order rejected per policy |
| SAGA-02 | Payment authorization declined | Reservation released |
| SAGA-03 | Shipping provider rejects before label creation | Authorization voided, reservation released |
| SAGA-04 | Capture fails definitively | Shipment voided/cancelled if still feasible, authorization voided, stock released per policy |
| SAGA-05 | Capture times out but actually succeeded | Provider queried, capture recorded, not captured twice |
| SAGA-06 | Refund temporarily fails | Stays REFUND_PENDING, bounded retries |
| SAGA-07 | Compensation delivered repeatedly | Single logical compensation effect |
| SAGA-08 | Worker crashes after compensation success before saving state | Retry does not repeat side effect |
| SAGA-09 | Carrier already accepted parcel | Intercept/return flow used, not merely voiding label |
| SAGA-10 | Compensation cannot complete | MANUAL_REVIEW and alert |
| SAGA-11 | Customer cancel races with payment callback | Conditional transition preserves state consistency |
| SAGA-12 | Two shipment branches, one succeeds and one fails | Compensate only the appropriate branch per partial fulfillment policy |

Tests must assert database state and provider stub state. Merely verifying that the orchestrator entered a Catch branch does not prove payment was voided or inventory was released.

## 25. Failure Injection and Test Doubles

Use WireMock or a stub server to simulate payment/shipping behaviors:

- 503 for the first two calls, then 200.
- 429 with Retry-After.
- Timeout after recording the operation.
- 202 response followed later by status changing to SUCCEEDED.
- 400/403 permanent failure.
- Connection reset after server receives request.

Use Testcontainers for databases to verify transactions, unique constraints, and optimistic locking. LocalStack can be used to test some AWS integrations, but separate cloud tests are needed for Step Functions, IAM, callbacks, and service semantics that local emulators do not fully reproduce.

Create fault hooks at key boundaries:

1. After writing saga state.
2. After participant commits but before response reaches the orchestrator.
3. After recording compensation result at the provider but before updating saga state.
4. During retries.
5. When the orchestrator lease expires.
6. When callbacks arrive late or repeatedly.

## 26. Runbook When Compensation Fails

A runbook must define:

1. Locate the saga by sagaId/orderId.
2. Inspect committed forward steps and resource references.
3. Identify which compensations are pending/failed.
4. Query actual state at payment, inventory, and shipping providers.
5. Classify as transient, permanent, or ambiguous outcome.
6. Verify idempotency keys before re-sending actions.
7. Safely retry compensation or create a manual task.
8. Update saga state via conditional transition.
9. Reconcile order, payment, inventory, and shipment.
10. Record audit log and close the incident once business state is verified.

Never run bulk compensation scripts without inspecting resource status. A duplicate refund command can double-refund; releasing a reservation can impact an order that already reallocated stock.

## 27. Security and Access Control

Each participant should only hold required permissions:

- Inventory Lambda only reserves/releases within its inventory scope.
- Payment Lambda only authorizes/voids/refunds using managed credentials.
- Shipping Lambda only creates/cancels/intercepts shipments as authorized.
- Orchestrator only invokes tasks and reads/writes necessary saga state.
- Operators with manual compensation privileges must be audited.

Never put card data or credentials into Step Functions input/output or saga context. Use tokens/references from the payment provider and secret manager. Protect execution history because it may contain business identifiers and downstream error details.

Separate privileges to trigger manual compensation from privileges to view sensitive data where appropriate. An operator may need to coordinate recovery without reading full payment details.

## 28. Cost and Operational Limits

Workflow costs include:

- Step Functions state transitions/executions.
- Lambda invocations and duration.
- Queue/event bus requests.
- Database reads/writes and saga state storage.
- Payment/shipping API calls.
- Retry and compensation attempts.
- Logs, traces, and audit storage.

Prolonged compensation can cost more than the forward path due to retries and reconciliation. Set deadlines, retry budgets, and alerts for stalled sagas. Never hold a Lambda invocation open for minutes waiting for a carrier or refund; persist state and resume via event/callback or scheduled worker.

Cap compensation concurrency. When a downstream service recovers, thousands of sagas may retry at once; gradual ramp-up and rate limiters protect provider quotas.

## 29. Common Pitfalls

**Treating compensation as a database rollback:** Side effects in external services cannot be rolled back by a local transaction. Design dedicated business actions.

**Compensating immediately on timeout:** Downstream may have already committed. Query status by operation reference first.

**Compensating every step from a static list:** Some steps never succeeded or already passed an irreversible milestone. Base decisions on step status and resource state.

**Releasing inventory after carrier pickup:** Risks reselling stock still in transit. Restock only after goods are returned and inspected.

**Refunding immediately after capture timeout:** Capture may not have occurred or may have succeeded. Reconcile before deciding.

**Retrying non-idempotent compensations:** Can trigger duplicate refunds or releases. Use a distinct key per compensation.

**Marking CANCELLED while compensation is still pending:** Misleading business status. Use REFUND_PENDING, RETURN_IN_PROGRESS, or MANUAL_REVIEW.

**Keeping saga state in Lambda memory:** State is lost when environments recycle. Persist durably and use optimistic locking.

**Omitting outbox/inbox:** Events can be lost or processed repeatedly. Use transactional outbox and consumer idempotency.

**Ignoring late callbacks:** Callbacks can overwrite cancellation state. Use conditional state transitions.

**Lacking manual recovery:** Compensations can fail permanently. Maintain runbooks, auditing, and clear ownership.

## 30. Production Checklist

- [ ] Every forward step has durable state and resource references.
- [ ] Every side effect has a stable idempotency key.
- [ ] Every forward step has a compensation or a clear rationale why automatic compensation is impossible.
- [ ] Compensation runs only for succeeded or verified actions.
- [ ] Compensation executes in appropriate dependency/reverse order.
- [ ] Timeouts/ambiguous outcomes are queried before retrying or compensating.
- [ ] Payment authorization, capture, void, and refund are clearly distinguished.
- [ ] Shipment label, carrier acceptance, intercept, and return are clearly distinguished.
- [ ] Inventory is restocked only when physical state permits.
- [ ] Saga state is persisted durably and updated via version/conditional writes.
- [ ] Outbox/inbox protects event delivery and deduplication.
- [ ] Retries have backoff, jitter, max attempts, and deadlines.
- [ ] Compensation failures have pending/failed/manual review states.
- [ ] Parallel branches have partial-success policies and dedicated compensations.
- [ ] Races between cancellation and callbacks are controlled.
- [ ] Metrics track saga age, compensation backlog, and manual review.
- [ ] Logs exclude card data, secrets, and tokens.
- [ ] Integration tests and fault injection cover crash windows.
- [ ] Runbooks exist and manual compensation privileges are audited.
- [ ] Concurrency/rate limits prevent retry storms when providers recover.

## Conclusion

Compensating actions enable a business workflow to recover when a later step fails after earlier steps have committed. For payment and shipping, you must distinguish authorize, capture, void, refund, label creation, carrier acceptance, and return; each action has distinct constraints and states. Compensation is a new business operation that may be asynchronous or require manual intervention.

A reliable saga persists durable state, knows exactly which forward steps succeeded, enforces idempotency on both forward actions and compensations, and inspects unknown outcomes before retrying. The orchestrator may use Java or Step Functions, but it does not replace each participant's local transactions, outbox/inbox, and conditional state transitions. When tests cover crash windows, duplicates, timeouts, compensation failures, and recovery, the system can handle payment and shipping failures while keeping order, payment, and inventory states consistent.
