# Modeling an Order Workflow with a State Machine

This lesson belongs to the **Business Workflow Project** chapter in the **CLOUD_SERVERLESS** module, focusing on how to build and operate an order workflow using a state machine on a serverless platform.

## Learning Objectives

After this lesson, you will be able to:

- Transform an order workflow from an unruly processing chain into a state-and-event model with clear rules.
- Identify the states, events, transition conditions, actions, and terminal states of an order.
- Design asynchronous flows for payment, inventory reservation, order confirmation, and fulfillment/delivery.
- Handle retries, duplicate events, out-of-order events, timeouts, and compensating actions when a step fails.
- Choose between implementing with a workflow engine or with Java functions triggered by HTTP, messages, and events.
- Evaluate access permissions, scalability, cold starts, observability, and cost of a serverless solution.

## 1. Why Does an Order Workflow Need a State Machine?

An order creation request may start with an HTTP request, but the business process does not end when the server returns a response. The system still needs to validate the order, authorize payment, reserve inventory, capture funds, create a shipment, and receive delivery confirmation. Each step may run in a different service and finish in a few milliseconds, several minutes, or longer.

If the entire workflow is written in a single synchronous function, that function has to wait on multiple external services. When one service is slow or fails, the entire request can time out even though some tasks already succeeded. If split into multiple functions without a shared state model, the system can easily process an event twice, miss the next step, or allow invalid business transitions.

A state machine models a business entity through:

- **State:** the current condition of the entity, for example **PAYMENT_PENDING** or **SHIPPED**.
- **Event:** something that has happened or a signal requesting processing, for example **PaymentAuthorized** or **CancelRequested**.
- **Transition:** the rule determining the next state when an event arrives.
- **Guard:** a condition that must hold true before allowing a state transition, for example the payment amount must equal the order total.
- **Action:** work triggered by a state transition, for example calling the inventory reservation service or emitting the **OrderConfirmed** event.
- **Context:** data needed to process the workflow, such as payment ID, reservation ID, payment deadline, and order version.

The general rule can be expressed as:

**current state + event + guard -> new state + action**

A state machine helps answer critical questions: what step is the order currently at, which events are allowed next, which step needs to be retried, and what should be done if the workflow cannot be completed.

### Distinguishing Commands and Events

A command expresses what a component wants the system to do. For example, **AuthorizePayment** asks the payment service to authorize an amount. An event records what has already happened. For example, **PaymentAuthorized** notifies that the provider has successfully authorized the payment.

Distinguishing these two concepts avoids updating state based on an unconfirmed request. Sending an inventory reservation command does not mean the inventory is reserved; only upon receiving the **InventoryReserved** result may the workflow transition to the corresponding step.

An event should have a unique identifier, event type, business entity ID, occurrence timestamp, and correlation metadata. The payload should only contain data necessary for processing and should not carry unrelated sensitive data.

## 2. Defining the Scope and States of an Order

Before writing code, define the business boundaries. This lesson models the lifecycle of an order from the moment the customer submits the request until delivery succeeds or the order is cancelled. Payment, inventory, and shipping are collaborating systems; each system still maintains its own state.

Do not merge every state from every service into one giant enum. An order has its own lifecycle states; a payment transaction may have states **AUTHORIZED**, **CAPTURED**, **VOIDED**, or **REFUNDED**; an inventory reservation may have states **RESERVED**, **RELEASED**, or **EXPIRED**. The order workflow orchestrates those systems and stores the necessary reference IDs.

A reference model:

| State | Meaning | Typical Next Step |
|---|---|---|
| **CREATED** | Order has been recorded, payment processing not yet started | Request payment authorization |
| **PAYMENT_AUTHORIZATION_PENDING** | Waiting for payment authorization result | Reserve inventory, report payment failure, or reconcile |
| **PAYMENT_RECONCILIATION_PENDING** | Payment outcome unknown due to timeout or lost response | Query provider using a stable transaction ID |
| **INVENTORY_RESERVATION_PENDING** | Waiting for the inventory system to reserve stock | Capture payment or start compensation |
| **PAYMENT_CAPTURE_PENDING** | Stock is reserved and waiting for payment capture | Confirm order or compensate |
| **CONFIRMED** | Payment has been captured and order is confirmed | Start order fulfillment |
| **FULFILLMENT_PENDING** | Preparing shipment | Create shipment |
| **SHIPPED** | Order has been handed over to the carrier | Wait for delivery confirmation |
| **DELIVERED** | Order has been delivered successfully | End |
| **PAYMENT_FAILED** | Payment was declined | End or allow customer to create a new request |
| **EXPIRED** | Expired and verified that no payment is pending | End |
| **COMPENSATION_PENDING** | Executing undo actions for previously succeeded steps | Cancel order or escalate to manual handling |
| **CANCELLATION_PENDING** | Processing a cancellation request for a confirmed order | Cancel after refunding and releasing inventory |
| **CANCELLED** | Order is cancelled and required actions are completed | End |
| **MANUAL_REVIEW** | Cannot safely recover automatically | Operations staff review |

Typical terminal states are **DELIVERED**, **PAYMENT_FAILED**, **EXPIRED**, and **CANCELLED**. **MANUAL_REVIEW** is a state requiring intervention; it should not be treated as success.

### Transition Rules

The table below describes the primary flow. Event names are illustrative business names; real projects must standardize schemas and naming conventions across services.

| Current State | Event | Next State | Action or Guard |
|---|---|---|---|
| **CREATED** | **SubmitOrder** | **PAYMENT_AUTHORIZATION_PENDING** | Validate order and send payment authorization command |
| **PAYMENT_AUTHORIZATION_PENDING** | **PaymentAuthorized** | **INVENTORY_RESERVATION_PENDING** | Verify transaction ID, amount, and currency; request inventory reservation |
| **PAYMENT_AUTHORIZATION_PENDING** | **PaymentDeclined** | **PAYMENT_FAILED** | Record decline reason that can be safely displayed |
| **PAYMENT_AUTHORIZATION_PENDING** | **PaymentResultUnknown** | **PAYMENT_RECONCILIATION_PENDING** | Reconcile with provider; do not assume transaction failed |
| **INVENTORY_RESERVATION_PENDING** | **InventoryReserved** | **PAYMENT_CAPTURE_PENDING** | Save reservation ID and request payment capture |
| **INVENTORY_RESERVATION_PENDING** | **InventoryRejected** | **COMPENSATION_PENDING** | Void the created payment authorization |
| **PAYMENT_CAPTURE_PENDING** | **PaymentCaptured** | **CONFIRMED** | Record captured amount and emit **OrderConfirmed** |
| **PAYMENT_CAPTURE_PENDING** | **PaymentCaptureFailed** | **COMPENSATION_PENDING** | Release inventory and void authorization if still valid |
| **PAYMENT_CAPTURE_PENDING** | **PaymentResultUnknown** | **PAYMENT_RECONCILIATION_PENDING** | Reconcile to determine whether funds were captured |
| **CONFIRMED** | **StartFulfillment** | **FULFILLMENT_PENDING** | Send shipment preparation request |
| **FULFILLMENT_PENDING** | **ShipmentCreated** | **SHIPPED** | Save shipment ID and tracking information |
| **SHIPPED** | **DeliveryConfirmed** | **DELIVERED** | Record delivery completion |
| **CONFIRMED** | **CancelRequested** | **CANCELLATION_PENDING** | Check cancellation eligibility; plan refund and inventory release |
| **COMPENSATION_PENDING** or **CANCELLATION_PENDING** | **AllCompensationsSucceeded** | **CANCELLED** | Cancel only after all mandatory compensating actions complete |
| **COMPENSATION_PENDING** or **CANCELLATION_PENDING** | **CompensationFailed** | **MANUAL_REVIEW** | Save error and raise operations alert |

The payment reconciliation result depends on the pending operation in context. If the authorization succeeded, the workflow continues to inventory reservation. If the capture succeeded, the workflow can confirm the order. If the provider confirms the operation failed, the workflow follows the corresponding failure branch. If the status remains unknown, the system continues bounded reconciliation or escalates to manual review.

Do not allow direct transitions from **PAYMENT_FAILED** to **SHIPPED**, or from **DELIVERED** back to **CONFIRMED**. If a customer wants to buy again, create a new order with a new identifier. If a customer requests a return after delivery, model a separate return workflow instead of reopening the old order lifecycle.

### Flow Diagram

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> PAYMENT_AUTHORIZATION_PENDING: SubmitOrder
    PAYMENT_AUTHORIZATION_PENDING --> INVENTORY_RESERVATION_PENDING: PaymentAuthorized
    PAYMENT_AUTHORIZATION_PENDING --> PAYMENT_FAILED: PaymentDeclined
    PAYMENT_AUTHORIZATION_PENDING --> PAYMENT_RECONCILIATION_PENDING: ResultUnknown
    PAYMENT_RECONCILIATION_PENDING --> INVENTORY_RESERVATION_PENDING: ProviderConfirmsAuthorized
    PAYMENT_RECONCILIATION_PENDING --> PAYMENT_FAILED: ProviderConfirmsDeclined
    PAYMENT_RECONCILIATION_PENDING --> EXPIRED: NoAuthorizationAndDeadlinePassed
    INVENTORY_RESERVATION_PENDING --> PAYMENT_CAPTURE_PENDING: InventoryReserved
    INVENTORY_RESERVATION_PENDING --> COMPENSATION_PENDING: InventoryRejected
    PAYMENT_CAPTURE_PENDING --> CONFIRMED: PaymentCaptured
    PAYMENT_CAPTURE_PENDING --> COMPENSATION_PENDING: PaymentCaptureFailed
    PAYMENT_CAPTURE_PENDING --> PAYMENT_RECONCILIATION_PENDING: CaptureResultUnknown
    COMPENSATION_PENDING --> CANCELLED: AllCompensationsSucceeded
    COMPENSATION_PENDING --> MANUAL_REVIEW: CompensationFailed
    CONFIRMED --> CANCELLATION_PENDING: CancelRequested
    CANCELLATION_PENDING --> CANCELLED: RefundAndReleaseSucceeded
    CANCELLATION_PENDING --> MANUAL_REVIEW: CompensationFailed
    CONFIRMED --> FULFILLMENT_PENDING: StartFulfillment
    FULFILLMENT_PENDING --> SHIPPED: ShipmentCreated
    SHIPPED --> DELIVERED: DeliveryConfirmed
    PAYMENT_FAILED --> [*]
    EXPIRED --> [*]
    CANCELLED --> [*]
    DELIVERED --> [*]
~~~

The diagram only shows the main lifecycle states. Compensating actions, retry counts, wait deadlines, and reconciliation details should be stored in the workflow context or history.

## 3. Designing Events and Workflow Data

A successful payment event can have the following structure:

~~~json
{
  "eventId": "evt-8d21",
  "eventType": "PaymentAuthorized",
  "orderId": "ord-1042",
  "occurredAt": "2026-11-17T10:15:30Z",
  "correlationId": "req-71ac",
  "causationId": "cmd-2f90",
  "aggregateVersion": 2,
  "payload": {
    "paymentAuthorizationId": "pay-auth-552",
    "amount": "1290000",
    "currency": "VND"
  }
}
~~~

Each field serves a distinct role:

- **eventId** uniquely identifies the event and is used to detect duplicate deliveries.
- **orderId** identifies the order to update.
- **correlationId** links logs and traces belonging to the same business request.
- **causationId** indicates which command or event produced this event.
- **aggregateVersion** indicates the order version to which the event applies.
- **occurredAt** is the timestamp when the event occurred at the emitter.
- **payload** contains the minimum business data required for verification and processing.

Do not trust every piece of data in an event merely because it came from a message broker. Consumers must authenticate the emitter, validate the schema, and verify **orderId**, payment ID, amount, and currency against stored order data. For provider webhooks, verify the signature using the provider's mechanism.

### Data to Persist

A basic design can use three data groups:

| Data Group | Typical Fields | Purpose |
|---|---|---|
| **orders** | **order_id**, **customer_id**, **status**, **version**, **total_amount**, **currency**, **created_at**, **updated_at** | Store current state and core order details |
| **order_events** | **event_id**, **order_id**, **event_type**, **payload_ref**, **occurred_at**, **processed_at** | Store event trail for auditing and reconciliation |
| **outbox** | **event_id**, **aggregate_id**, **event_type**, **payload**, **created_at**, **published_at** | Ensure events to be published are recorded in the same transaction as the order update |

Additional fields such as **payment_id**, **payment_authorization_id**, **inventory_reservation_id**, **shipment_id**, **workflow_id**, **deadline_at**, and **pending_operation** can be stored as needed. Avoid storing payment card data or unnecessary personal information in the event log.

Current state enables fast queries. Event history explains how the order reached that state. The two types of data serve different purposes. Full event sourcing is not strictly required just because the system maintains an event log.

## 4. Organizing the Workflow in a Serverless Architecture

In a serverless architecture, each Java function typically handles a short processing step. The function receives a trigger, validates input, reads required state, applies rules, and writes results to durable storage. The function can terminate after emitting the next command or event; the business process continues via a message broker, event bus, or workflow engine.

A reference architecture:

~~~mermaid
flowchart TD
    Client[Client application] --> API[HTTP API]
    API --> Create[Java function: CreateOrder]
    Create --> DB[(Order database)]
    Create --> Outbox[(Transactional outbox)]
    Outbox --> Publisher[Outbox publisher]
    Publisher --> Bus[Queue or event bus]
    Bus --> Orchestrator[Workflow engine or event handlers]
    Orchestrator --> Payment[Java function: Payment]
    Orchestrator --> Inventory[Java function: Inventory]
    Orchestrator --> Fulfillment[Java function: Fulfillment]
    Payment --> Provider[Payment provider]
    Inventory --> Stock[Inventory service]
    Fulfillment --> Shipping[Shipping provider]
    Payment --> Bus
    Inventory --> Bus
    Fulfillment --> Bus
    Orchestrator --> DB
~~~

Common triggers:

| Trigger | Role in the Workflow |
|---|---|
| **HTTP** | Receive order creation requests, status queries, or cancellation requests |
| **Message queue** | Process background jobs and results from other services |
| **Event bus** | React to **PaymentAuthorized**, **InventoryReserved**, **ShipmentCreated**, and business events |
| **Scheduler or durable timer** | Trigger processing when an order reaches its payment deadline or a step times out |
| **Workflow engine** | Orchestrate branches, timeouts, retries, waiting for results, and compensating actions across multiple functions |

### Two Ways to Implement a State Machine

**Using a durable-state workflow engine.** An orchestration service manages the execution, current step, results, timeouts, retries, and history. Each step invokes a Java function or integrates with a service. This approach suits long-running workflows with multiple branches that need to wait for events. It requires understanding limits on execution duration, transition counts, input/output sizes, how the engine handles retries, and per-transition costs.

**Managing the state machine in the application.** Each event handler reads state from the database, checks the transition, updates the version, and emits the next event. This approach is flexible and integrates easily with existing data models, but the development team must build locking or optimistic concurrency, retries, timeouts, history, dead-letter queues, reconciliation, and operational tooling themselves.

Both approaches can be combined: a workflow engine orchestrates long-running steps while the business database remains the primary source of truth for the order. Clearly define which system is the source of truth for each field. If the state in the engine and the state in the database diverge, there must be a reconciliation and remediation process.

## 5. Implementing State Transition Rules in Java

State decision logic should be separated from external service calls. The transition decision function can be pure, easy to test, and perform no I/O. The orchestration layer executes actions after validating the transition and safely persisting the change.

The example below illustrates a minimal transition table in Java 17:

~~~java
import java.util.Map;

enum OrderState {
    CREATED,
    PAYMENT_AUTHORIZATION_PENDING,
    INVENTORY_RESERVATION_PENDING,
    PAYMENT_CAPTURE_PENDING,
    PAYMENT_RECONCILIATION_PENDING,
    PAYMENT_FAILED,
    CONFIRMED,
    FULFILLMENT_PENDING,
    SHIPPED,
    DELIVERED,
    COMPENSATION_PENDING,
    CANCELLATION_PENDING,
    CANCELLED,
    EXPIRED,
    MANUAL_REVIEW
}

enum OrderEvent {
    SUBMIT,
    PAYMENT_AUTHORIZED,
    PAYMENT_DECLINED,
    PAYMENT_RESULT_UNKNOWN,
    INVENTORY_RESERVED,
    INVENTORY_REJECTED,
    PAYMENT_CAPTURED,
    PAYMENT_CAPTURE_FAILED,
    CANCEL_REQUESTED,
    START_FULFILLMENT,
    SHIPMENT_CREATED,
    DELIVERY_CONFIRMED,
    ALL_COMPENSATIONS_SUCCEEDED,
    COMPENSATION_FAILED
}

record TransitionKey(OrderState from, OrderEvent event) {}

final class OrderStateMachine {
    private static final Map<TransitionKey, OrderState> TRANSITIONS =
        Map.ofEntries(
            Map.entry(
                new TransitionKey(OrderState.CREATED, OrderEvent.SUBMIT),
                OrderState.PAYMENT_AUTHORIZATION_PENDING
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.PAYMENT_AUTHORIZATION_PENDING,
                    OrderEvent.PAYMENT_AUTHORIZED
                ),
                OrderState.INVENTORY_RESERVATION_PENDING
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.PAYMENT_AUTHORIZATION_PENDING,
                    OrderEvent.PAYMENT_DECLINED
                ),
                OrderState.PAYMENT_FAILED
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.PAYMENT_AUTHORIZATION_PENDING,
                    OrderEvent.PAYMENT_RESULT_UNKNOWN
                ),
                OrderState.PAYMENT_RECONCILIATION_PENDING
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.INVENTORY_RESERVATION_PENDING,
                    OrderEvent.INVENTORY_RESERVED
                ),
                OrderState.PAYMENT_CAPTURE_PENDING
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.INVENTORY_RESERVATION_PENDING,
                    OrderEvent.INVENTORY_REJECTED
                ),
                OrderState.COMPENSATION_PENDING
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.PAYMENT_CAPTURE_PENDING,
                    OrderEvent.PAYMENT_CAPTURED
                ),
                OrderState.CONFIRMED
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.PAYMENT_CAPTURE_PENDING,
                    OrderEvent.PAYMENT_CAPTURE_FAILED
                ),
                OrderState.COMPENSATION_PENDING
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.CONFIRMED,
                    OrderEvent.CANCEL_REQUESTED
                ),
                OrderState.CANCELLATION_PENDING
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.CONFIRMED,
                    OrderEvent.START_FULFILLMENT
                ),
                OrderState.FULFILLMENT_PENDING
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.FULFILLMENT_PENDING,
                    OrderEvent.SHIPMENT_CREATED
                ),
                OrderState.SHIPPED
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.SHIPPED,
                    OrderEvent.DELIVERY_CONFIRMED
                ),
                OrderState.DELIVERED
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.COMPENSATION_PENDING,
                    OrderEvent.ALL_COMPENSATIONS_SUCCEEDED
                ),
                OrderState.CANCELLED
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.CANCELLATION_PENDING,
                    OrderEvent.ALL_COMPENSATIONS_SUCCEEDED
                ),
                OrderState.CANCELLED
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.COMPENSATION_PENDING,
                    OrderEvent.COMPENSATION_FAILED
                ),
                OrderState.MANUAL_REVIEW
            ),
            Map.entry(
                new TransitionKey(
                    OrderState.CANCELLATION_PENDING,
                    OrderEvent.COMPENSATION_FAILED
                ),
                OrderState.MANUAL_REVIEW
            )
        );

    static OrderState next(OrderState current, OrderEvent event) {
        OrderState next = TRANSITIONS.get(new TransitionKey(current, event));
        if (next == null) {
            throw new IllegalStateException(
                "Invalid order transition: " + current + " + " + event
            );
        }
        return next;
    }
}
~~~

This is the transition decision component, not a complete workflow engine. In a real application, you must add:

1. **Guards:** verify the user is authorized to act on the order; amount and currency match; payment ID belongs to the right order; order is not in a terminal state; cancellation request is still valid.
2. **Context:** store transaction ID, reservation ID, payment operation being reconciled, processing deadline, and list of remaining compensation steps.
3. **Persistence:** save the new state and version within a transaction; write the next event to the outbox in the same transaction.
4. **Action handler:** call the payment, inventory, or shipping provider using a request with a stable idempotency key.
5. **Error mapping:** distinguish business errors, transient errors, unknown-result timeouts, and errors requiring human intervention.

Do not call payment APIs directly inside the **next** function. If the external call succeeds but the function crashes before saving state, a subsequent run could repeat the side effect. Record the processing intent and use an idempotency key at the target system so the operation can be safely retried.

## 6. Ensuring Consistent State Updates and Event Publishing

A common mistake is writing to the database and publishing a message as two independent operations:

1. Update the order to **CONFIRMED**.
2. Send **OrderConfirmed** to the event bus.

If the function stops between the two operations, the database has confirmed the order, but the fulfillment service never receives the event. If the order is reversed, a consumer might receive the event before the database commits. This is the dual-write problem.

The transactional outbox solves this problem by writing the order state and an outbox record within the same database transaction. A separate publisher reads unpublished records, sends the messages, and marks them as published. The publisher may still send duplicates if it crashes after sending but before marking; therefore, consumers must remain idempotent.

The process for updating a transition can proceed as follows:

1. Receive the event and validate schema, signature, or emitter.
2. Start a transaction; read the order along with its **version**.
3. Check whether the event has already been processed and whether the transition is valid.
4. Evaluate guards and determine the next state.
5. Update the order conditioned on the old version still matching.
6. Write the next event or command to the outbox in the same transaction.
7. Commit; the publisher emits the message afterward.

Example update with optimistic locking:

~~~sql
UPDATE orders
SET status = :next_status,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE order_id = :order_id
  AND status = :expected_status
  AND version = :expected_version;
~~~

If the number of updated rows is 0, another process may have updated the order or the current state has changed. Re-read and classify the case: duplicate event, stale event, premature event, or genuine conflict. Never overwrite newer state with stale data.

## 7. Retries, Idempotency, and Out-of-Order Events

Messaging systems typically provide at-least-once delivery. That means a message can be redelivered if a consumer times out or fails to acknowledge in time. Retries are normal; duplicated side effects are the problem to prevent.

### Designing Idempotency

An idempotent operation can be executed multiple times while producing an equivalent business outcome. Multiple layers can be applied:

- The order creation API accepts an **Idempotency-Key** from the client and stores the key scoped to the user or tenant. Resending the same key must return the same created order.
- Consumers store processed **eventId** values with a unique constraint per consumer or task type.
- Calls to the payment provider use a stable key, such as **orderId:authorize** or **orderId:capture**. Do not generate a new key for each retry.
- Inventory reservation, release, refund, and shipment creation operations also need a business reference ID or idempotency key.
- State updates must include a version condition so two functions cannot apply the same transition concurrently.

An idempotency key must represent a stable business operation. If a new random key is generated on every retry, the provider may treat each attempt as a different transaction.

### Retry Policy

Only retry recoverable errors, such as transient network errors, rate limits, or temporary service unavailability. Do not retry indefinitely on business errors like a declined card, invalid order, or insufficient inventory.

A common policy:

- Cap the maximum number of attempts.
- Increase wait intervals with exponential backoff and add jitter to prevent many functions from retrying simultaneously.
- Set a timeout for each service call.
- Distinguish function retries, queue retries, and workflow engine retries so total attempts do not multiply unexpectedly.
- After reaching maximum retries, move the message to a dead-letter queue (DLQ), log the error clearly, and raise an alert.
- Only redrive messages from the DLQ after identifying the root cause and verifying the operation can be safely re-executed.

A timeout does not mean an operation failed. For example, a function calls the payment provider, the provider captures the funds, and the response is lost. Treating the timeout as a failure and sending a new transaction could double-charge the customer. When the outcome is unknown, transition to **PAYMENT_RECONCILIATION_PENDING** and query the provider using the original transaction ID or idempotency key.

### Duplicate and Out-of-Order Events

Suppose **ShipmentCreated** arrives before the consumer receives **OrderConfirmed**. Do not automatically discard the event just because the current state does not allow it yet. The earlier message may be delayed, or two event channels may have different latencies.

Distinguish between:

- **Duplicate event:** **eventId** already processed; acknowledge the message without repeating side effects.
- **Stale event:** **aggregateVersion** is lower than the current version; record an audit trail and ignore if already superseded.
- **Premature event:** expected version or prerequisite is not yet met; retain for retry or place into a per-order waiting queue.
- **Conflict:** two competing transitions update the same version; only one transaction commits, and the other must re-read and re-evaluate.

If per-order ordering is needed, use a partition key or message group by **orderId**, while still checking **version** in the database. Do not assume the event bus always preserves global ordering.

## 8. Timeouts, Compensating Actions, and Business Consistency

Order workflows often outlive a single function invocation. Do not keep a function running and sleeping for minutes to wait for payment or delivery. Persist the deadline, end the invocation, and use a durable timer or workflow wait state to resume at the right time.

Timeouts must be handled according to business semantics:

- Payment deadline expired: reconcile with the provider before marking **EXPIRED**.
- Inventory held too long: check payment status and reservation policy before releasing.
- Carrier fails to return a result: query by shipment ID or route tracking to exception handling.
- Function times out: the next execution must determine whether prior side effects already occurred.

### Saga and Compensation

A multi-service process typically lacks an overarching ACID transaction across all systems. If payment was authorized but inventory rejects the reservation, the system must void the authorization. If funds were already captured before discovering the order cannot be delivered, a refund and inventory release may be required.

This is the Saga pattern: a workflow composed of local steps; each succeeded step may have a corresponding compensating action when a later step fails.

| Completed Step | Potential Compensating Action Needed |
|---|---|
| Payment authorization | Void authorization |
| Inventory reservation | Release reservation |
| Payment capture | Refund |
| Shipment created but not handed over | Void label or request shipment cancellation if supported by carrier |

Compensation is not an instantaneous database rollback. It is a new business operation that can fail, requires retries, and must be idempotent. For instance, a refund may take several minutes or require provider confirmation. Therefore, **CANCELLED** should only be recorded once all policy-mandated actions have completed. If the result cannot be verified, transition to **MANUAL_REVIEW** and alert operations.

An order already in **SHIPPED** usually cannot be cancelled by undoing previous steps. In that case, a separate return or delivery-refusal workflow is needed. This rule must be enforced in guards so no cancellation request accidentally reverts an in-transit order to **CANCELLED**.

## 9. Security and Access Control

Each function should only have the permissions needed for its step:

- The order creation function is permitted to create orders and write to the outbox, not to issue refunds.
- The payment function can only invoke required payment operations and read minimal order data.
- The inventory function can only reserve or release stock.
- The fulfillment function can only create or look up shipments.
- Consumers only receive messages from designated queues or topics.

HTTP endpoints must authenticate users and check order ownership by customer or tenant. Do not use a client-supplied **orderId** as proof that the client is allowed to view or cancel the order. Webhooks must verify signatures, timestamps, and replay protection according to the provider's mechanism. Secrets and API keys should live in a secret manager; do not log tokens, card data, or credentials.

Event payloads must be validated for types, size, schema version, and data bounds. For multi-tenant events, consumers must validate tenant context to avoid updating the wrong order. Access permissions to databases, queues, event buses, and secret stores should be scoped per function so they can be audited and revoked independently.

## 10. Workflow Observability and Operations

A distributed workflow must let operators see the journey of an order. Each log and trace should carry correlation identifiers such as **orderId**, **eventId**, **correlationId**, **workflowId**, and step name. Do not log full sensitive payloads merely for debugging convenience.

Useful metrics include:

- Number of orders in each state and average time spent in each state.
- Payment decline, timeout, and reconciliation rates.
- Inventory reservation failure, capture failure, and compensation failure rates.
- Retry counts per step, queue depth, and DLQ message count.
- Number of workflows exceeding deadlines or in **MANUAL_REVIEW**.
- Time from **CREATED** to **CONFIRMED**, and from **SHIPPED** to **DELIVERED**.
- Number of transitions rejected due to duplicate events, stale events, or version conflicts.

Provide a dashboard to query the history of an **orderId**, displaying current state, received events, sent commands, attempt counts, and latest errors. Alerts should tie to business thresholds—such as a spike in orders pending reconciliation or failed compensations—rather than alerting on every function exception.

## 11. Cold Starts, Scaling, and Cost in Serverless Environments

FaaS suits short processing steps triggered by HTTP, messages, or events with variable load. The platform can scale instances up or down based on invocation volume. Databases, queues, and external providers still have their own limits; scaling functions does not automatically scale those downstream services.

Java functions can experience cold starts when the platform creates a new runtime, loads classes, and initializes dependencies. Startup time can be reduced by keeping dependencies lean, avoiding unnecessary heavy framework initialization, safely reusing connection clients across invocations, and setting reasonable timeouts. Do not store business state in static variables or instance memory, because invocations may run on different instances, instances can be reclaimed, and multiple invocations can run concurrently.

Workflow costs typically come from multiple components:

- Invocation count and execution duration of each function.
- CPU or memory allocated to functions.
- Number of state transitions or execution steps in the workflow engine.
- Number of messages, events, retries, and DLQ messages.
- Databases, workflow history storage, logs, traces, and stored data.
- Network data transfer or external service calls.

A short function retried thousands of times can still incur significant cost. A workflow broken into many tiny steps isolates failures well but increases invocation and transition counts. Measure actual execution duration, error rates, and retry counts to balance reliability with cost.

For long waits, use durable wait states and timers instead of keeping functions running. For steady, very high loads with ultra-low latency requirements, compare total cost and complexity of FaaS against always-on services. The decision should be based on workload characteristics, operational requirements, and platform limits.

## 12. Failure Scenarios to Model

| Scenario | Risk | Mitigation |
|---|---|---|
| Client resends **POST /orders** after timeout | Creating two orders for one checkout | Use an idempotency key and unique constraint |
| Provider captured payment but function timed out | Double charging if a new transaction is sent | Reconcile using the original transaction key |
| **PaymentAuthorized** delivered twice | Reserving inventory twice | Detect duplicate **eventId** and use an idempotency key on reservation |
| **InventoryRejected** arrives after a retry | Voiding authorization multiple times | Conditional transitions and idempotent void operation |
| Two functions concurrently process cancellation and shipment creation | Order gets both cancelled and shipped | Optimistic locking, guards, and per-order ordering rules |
| Publisher emits event then crashes before marking outbox | Consumer receives duplicate event | Idempotent consumer |
| Refund fails after cancellation is requested | Order state and actual funds diverge | Stay in **CANCELLATION_PENDING**, bounded retries, and alert |
| Message fails repeatedly | Queue stalls or loses throughput | DLQ, error classification, and redrive after root-cause fix |

## 13. Testing the State Machine

Testing should focus on business rules and distributed scenarios:

1. **Transition tests:** for every valid state-event pair, verify the next state matches the table. For invalid pairs, verify the system rejects them.
2. **Guard tests:** another user cannot cancel the order; wrong amount or currency cannot confirm payment; delivered orders cannot be cancelled via the normal flow.
3. **Idempotency tests:** sending the same event or API idempotency key multiple times produces only one side effect.
4. **Timeout tests:** simulate the provider processing the request while the response is lost; verify the system reconciles instead of creating a new transaction.
5. **Concurrency tests:** two functions update the same version; only one transition commits.
6. **Compensation tests:** inventory reservation succeeds but payment fails; verify inventory is released and authorization is voided.
7. **DLQ and redrive tests:** failed messages are traced, alerted, and safely reprocessed after fixing the root cause.
8. **Event contract tests:** producers and consumers agree on the same schema, version, and meaning of events.

Beyond unit tests, include integration tests with queues, databases, and mock providers. For critical flows, test crashing the function right after a side effect, right before commit, or right after commit to uncover failure windows.

## 14. Process for Implementing an Order Workflow

Implementation can follow this sequence:

1. **Finalize business rules:** align on states, events, guards, terminal states, cancellation conditions, and refund policies.
2. **Design event contracts:** define identifiers, schemas, versions, correlation fields, payloads, and trusted emitters.
3. **Design storage:** define order tables, versioning, event log, outbox, idempotency keys, and deadlines.
4. **Write the pure state machine:** build the transition table and guards; test valid and invalid pairs.
5. **Create Java functions:** separate HTTP, payment, inventory, fulfillment, and consumer handlers by responsibility.
6. **Configure triggers and permissions:** wire HTTP APIs, queues, event buses, timers, or workflow engines; grant least privilege.
7. **Add retries and compensation:** configure timeouts, backoff, DLQs, reconciliation, and idempotent compensating actions.
8. **Set up observability:** structured logs, traces, metrics, dashboards, and business-state alerts.
9. **Test failures and load:** simulate duplicate events, out-of-order events, slow providers, concurrency, and cold starts.
10. **Deploy with controls:** monitor error rates, processing times, workflow backlogs, and costs after release.

## 15. When to Use a State Machine and FaaS?

A state machine is especially useful when a process has multiple steps, branching logic, long duration, dependencies on external systems, or requires knowing the exact state of an entity. Clear transition rules also aid auditing and operations support.

FaaS fits well when each step can be packaged as a short processing unit, triggered on demand or by events, scaled independently, and does not need to hold state in memory. Combining a state machine with FaaS separates business orchestration from per-step computation.

Consider another model or always-on services if the workload runs continuously at high volume, requires persistent connections, streams data continuously, or has latency requirements that cold starts and invocation overhead cannot meet. Regardless of platform choice, business state must still be persisted durably and transitions must remain controlled.

## 16. Practice Exercises

**Exercise 1 — Extend the model:** Add the **RETURN_REQUESTED** state and describe how to handle a return request after an order reaches **DELIVERED**. Identify events, guards, refund actions, and terminal states.

**Exercise 2 — Handle unknown payment outcome:** The payment provider received the request, but the HTTP function timed out before receiving the response. Describe the data to persist, how to reconcile, and conditions to transition the order to **INVENTORY_RESERVATION_PENDING**, **PAYMENT_FAILED**, or **MANUAL_REVIEW**.

**Exercise 3 — Prevent duplicate processing:** An **InventoryReserved** message is delivered three times. Identify the idempotency layers needed in the consumer, database, and subsequent service call.

**Exercise 4 — Handle concurrency:** A customer requests cancellation at the exact moment a fulfillment worker starts creating a shipment. Write the guard and versioned update condition so only one branch is allowed to proceed.

**Exercise 5 — Choose an architecture:** Compare a durable-state workflow engine with an application-managed state machine in a database. List the operational responsibilities, observability, limits, and costs the team must evaluate.

When completing the exercises, verify that every state has a clear meaning, every event has an emitter, every transition has appropriate guards, and every critical side effect has an idempotency or compensation strategy.
