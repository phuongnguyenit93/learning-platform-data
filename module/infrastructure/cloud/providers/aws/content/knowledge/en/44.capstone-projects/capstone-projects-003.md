# Building an Event-Driven Order System with Sagas

## Capstone Objectives

You will design and implement an order processing system on AWS. An order request flows across multiple independent services: creating the order, reserving inventory, authorizing payment, creating a shipment, capturing funds, and confirming the order. If a step fails after earlier steps have persisted data, the system must execute compensating actions to bring the business state back to a valid condition.

The project combines **Saga orchestration** using AWS Step Functions with **event-driven integration** via Amazon EventBridge and Amazon SQS. Step Functions orchestrates the business transaction; EventBridge distributes domain events to interested systems; SQS absorbs traffic bursts and decouples consumer processing rates.

After completing this capstone, you will be able to:

- Decompose an order workflow into service boundaries and local transactions.
- Choose between saga orchestration and choreography based on workflow complexity.
- Design state machines with retries, timeouts, catch handlers, and compensations.
- Prevent overselling with conditional writes and optimistic concurrency.
- Handle duplicate requests/events using idempotency keys.
- Avoid dual-writes using the transactional outbox pattern and DynamoDB Streams.
- Separate domain events from commands and side effects.
- Design DLQs, redrives, reconciliation, and manual review workflows.
- Protect APIs, payment credentials, customer data, and IAM permissions.
- Test failure paths, compensations, and eventual consistency.
- Define acceptance criteria, operational procedures, and cost controls for the system.

## 1. Context and Business Problem

An online store accepts orders from web and mobile apps. Each order contains multiple items, quantities, a shipping address, and a payment method. Processing steps span different services and datastores.

For example, an order with three items:

1. Order Service creates the order in `PENDING` status.
2. Inventory Service reserves item quantities.
3. Payment Service authorizes the payment method.
4. Shipping Service creates a shipment with the carrier.
5. Payment Service captures the authorized amount.
6. Order Service confirms the order in `CONFIRMED` status.
7. Notification/Analytics consume domain events to send notifications and update reports.

There is no single ACID transaction spanning all databases and payment providers. If payment fails after inventory has been reserved, the system must release inventory. If shipment creation succeeds but payment capture fails, the system must cancel the shipment and void the authorization. If capture has succeeded but confirming the order fails, a refund may be required.

This is a distributed transaction problem. A saga breaks a long-lived transaction into local transactions and defines corresponding compensating actions. Each service owns its own data; the orchestrator tracks progress and decides the next step.

## 2. Project Scope

### Required Capabilities

- Create orders with an `Idempotency-Key`.
- Validate product data and prices from an authoritative source.
- Conditionally reserve inventory to prevent selling beyond available stock.
- Authorize and capture payments via a mock adapter or sandbox provider.
- Create and cancel shipments via an adapter.
- Orchestrate the saga and its compensations.
- Emit domain events for Order, Inventory, Payment, and Shipping.
- Deliver notifications asynchronously via SQS.
- Persist workflow state and allow querying order progress.
- Handle duplicate delivery, retries, timeouts, DLQs, and manual review.

### Out of Scope for the Initial Version

- Storing or directly processing raw payment card data.
- Complex tax, shipping rate, and promotional pricing calculations.
- Multi-currency settlement and full accounting reconciliation.
- Delivery route optimization.
- Full-domain event sourcing.
- Multi-Region active-active across every service.

Keep the initial scope small enough to prove both the happy path and failure/compensation paths. Expand with additional participants only after core invariants are working.

## 3. Selected AWS Architecture

| Capability | AWS Service / Component | Responsibility |
|---|---|---|
| API ingress | Amazon API Gateway | Receive order requests, authenticate, and throttle requests |
| Business adapter | AWS Lambda | Validate commands, write order + idempotency + outbox in one transaction, and return 202 |
| Saga starter | AWS Lambda | Receive `OrderCreated`, deduplicate by `sagaId`, and call `StartExecution` with a deterministic execution name |
| Orchestration | AWS Step Functions Standard | Orchestrate forward steps and compensations |
| Event routing | Amazon EventBridge custom event bus | Route `OrderCreated` to Saga Starter and domain events to consumers |
| Buffering | Amazon SQS standard queues | Decouple producer/consumer speeds |
| Failure isolation | SQS DLQs and EventBridge target DLQ | Capture unprocessable messages/events |
| Service data | Amazon DynamoDB | Store order, inventory, payment, shipment, and idempotency records |
| Change capture | DynamoDB Streams | Detect committed outbox records |
| Compute | AWS Lambda | Implement service participants and consumers |
| Secrets | AWS Secrets Manager | Store payment/shipping provider credentials |
| Encryption | AWS KMS | Encrypt data and secrets per policy |
| Logs/metrics | Amazon CloudWatch | Monitor requests, sagas, queues, and Lambda |
| Tracing | AWS X-Ray / Step Functions execution history | Trace an order's end-to-end path |
| Infrastructure | AWS CDK or AWS SAM | Define reproducible infrastructure |

This is a serverless architecture well suited for a capstone and variable traffic. If a service requires continuous processing, long runtimes, or advanced network control, Lambda can be replaced with ECS/Fargate while preserving the same saga contracts.

## 4. Overall Architecture Diagram

~~~mermaid
flowchart TD
    C["Web / Mobile client"] --> AP["API Gateway"]
    AP --> OAPI["Order API Lambda"]
    OAPI --> OD[("Orders + Idempotency + Outbox")]
    OD --> OST["Order Outbox Stream"]
    ID --> IST["Inventory Outbox Stream"]
    PD --> PST["Payment Outbox Stream"]
    SD --> SST["Shipping Outbox Stream"]
    OST --> PUB["Outbox Publisher Lambda"]
    IST --> PUB
    PST --> PUB
    SST --> PUB
    PUB --> EB["EventBridge: orders-domain"]
    EB --> STARTER["Saga Starter Lambda"]
    STARTER --> SF["Step Functions Standard Saga"]
    SF --> OS["Order Service Lambda"]
    SF --> IS["Inventory Service Lambda"]
    SF --> PS["Payment Service Lambda"]
    SF --> SS["Shipping Service Lambda"]
    IS --> ID[("Inventory + Reservations + Outbox")]
    PS --> PD[("Payment records + Outbox")]
    SS --> SD[("Shipment records + Outbox")]
    EB --> Q1["Notifications SQS"]
    EB --> Q2["Analytics SQS"]
    EB --> Q3["Fraud Review SQS"]
    Q1 --> N["Notification Lambda"]
    Q2 --> A["Analytics Consumer"]
    Q3 --> F["Fraud Consumer"]
    Q1 --> D1["Notifications DLQ"]
    Q2 --> D2["Analytics DLQ"]
    EB -. delivery failure .-> ED["EventBridge Target DLQ"]
    SF --> CW["CloudWatch / X-Ray"]
    PUB --> CW
~~~

The Order API only writes the `PENDING` order, idempotency record, and `OrderCreated` outbox event; the API does not perform a separate dual-write to call `StartExecution`. Once the transaction commits, DynamoDB Streams triggers the outbox publisher, which sends `OrderCreated` to EventBridge, and a rule routes the event to Saga Starter Lambda to start Step Functions Standard. This startup pattern ensures order creation and the saga start request share a durable outbox record as their link.

Step Functions invokes participants to execute the order transaction steps. Each participant persists its business state change together with an outbox event inside its own local transaction. The outbox publisher pushes domain events to EventBridge. Independent consumers handle notifications, analytics, or fraud signals.

EventBridge does not store saga state. Workflow state lives in Step Functions and the service databases. SQS acts as a consumer buffer; queue backlogs must never alter committed payment or inventory state.

The EventBridge target invokes Saga Starter Lambda. This Lambda uses `sagaId` as a deterministic execution name and holds a role allowing only `states:StartExecution` on the target state machine. With Standard workflows, `StartExecution` with the same name and same input while the execution is still running is idempotent; once the execution finishes, the API returns `ExecutionAlreadyExists` and the name cannot be reused for 90 days. Starter must look up existing executions and confirm matching input/`sagaId`; never generate a new execution name on redelivery. You can store a `SagaRegistry` record keyed by `sagaId` with `STARTING`/`RUNNING` state to recover if the starter crashes between recording and calling `StartExecution`. The EventBridge target role only needs `lambda:InvokeFunction` on Saga Starter.

`OrderConfirmed` is written to the outbox in the same transaction as the `CONFIRMED` transition. The publisher emits the event afterward; EventBridge routes it to notification, analytics, or CRM consumers. Step Functions does not need a separate publish call after the state commits.

## 5. Why Choose Saga Orchestration?

Sagas have two main variants:

| Criterion | Choreography | Orchestration |
|---|---|---|
| Coordination | Each service reacts to events from other services | A central orchestrator decides the next step |
| Business flow | Distributed across consumers | Centralized in a state machine |
| Observability | Must correlate event logs across services | Execution history and per-step status available |
| Compensation | Each participant emits compensating events | Orchestrator invokes compensations in order |
| Best fit | Few participants, simple flows | Many steps, branching errors, and explicit compensations |
| Risk | Hard to see the full flow as event count grows | Workflow definition must be managed and versioned |

This capstone chooses orchestration because the order workflow has multiple sequential steps and requires reverse-order compensation. EventBridge is still used for integration outside the saga. This hybrid avoids forcing every service to infer the entire transaction while keeping out-of-band consumers decoupled.

AWS Step Functions Standard fits long-running sagas that need execution history. Standard workflows support a maximum duration of one year; execution history is retrievable via API for 90 days after execution completion. Express workflows fit short, high-volume event processing; maximum duration is five minutes and semantics depend on the Express type. Choose Standard for the order saga and re-evaluate for other workloads. https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html

## 6. Domain Boundaries and Data Ownership

Do not let every Lambda write directly to the same Orders or Inventory table. Each service owns its own data and business API.

| Service | Owned Data | Primary Operations |
|---|---|---|
| Order | Order, OrderStatus, order version | Create, Confirm, Cancel, Get |
| Inventory | SKU stock, Reservation | Reserve, Release, Commit |
| Payment | Authorization, Capture, Refund | Authorize, Capture, Void, Refund |
| Shipping | Shipment, carrier reference | Create, Cancel, Track |
| Notification | Delivery attempts, preferences | Send, retry, suppress duplicate |

The orchestrator passes `orderId`, `sagaId`, references, and command metadata. Participants never access another service's internal database. For example, Order Service does not decrement stock itself; it calls Inventory Service via a task defined in the saga.

Each service must define contract versioning, validation, and an idempotency policy. Schema changes must remain compatible with running event consumers.

Order Service owns order status and timeline; Inventory owns stock and reservations; Payment owns authorization/capture/refund references; Shipping owns carrier bookings. Participants never write directly to each other's databases. The saga passes only identifiers, command metadata, and operation references needed for compensation.

## 7. Order Lifecycle

Use explicit business states:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> INVENTORY_RESERVED
    INVENTORY_RESERVED --> PAYMENT_AUTHORIZED
    PAYMENT_AUTHORIZED --> SHIPMENT_CREATED
    SHIPMENT_CREATED --> PAYMENT_CAPTURED
    PAYMENT_CAPTURED --> CONFIRMED
    PENDING --> REJECTED
    PENDING --> CANCELLING
    INVENTORY_RESERVED --> CANCELLING
    PAYMENT_AUTHORIZED --> CANCELLING
    SHIPMENT_CREATED --> CANCELLING
    PAYMENT_CAPTURED --> REFUND_PENDING
    CANCELLING --> CANCELLED
    CANCELLING --> COMPENSATION_PENDING
    COMPENSATION_PENDING --> CANCELLED
    COMPENSATION_PENDING --> MANUAL_REVIEW
    REFUND_PENDING --> CANCELLED
    REFUND_PENDING --> MANUAL_REVIEW
    CONFIRMED --> [*]
    CANCELLED --> [*]
    MANUAL_REVIEW --> [*]
~~~

These statuses represent Order Service's business view. Participant services still maintain their own detailed states such as `RESERVED`, `AUTHORIZED`, `CAPTURED`, `VOIDED`, `REFUNDED`, or `SHIPMENT_CANCELLED`.

| Status | Meaning |
|---|---|
| `PENDING` | Order received; allocation steps not yet completed |
| `INVENTORY_RESERVED` | Stock has been reserved |
| `PAYMENT_AUTHORIZED` | Provider authorized payment |
| `SHIPMENT_CREATED` | Carrier accepted shipment creation request |
| `PAYMENT_CAPTURED` | Funds have been captured |
| `CONFIRMED` | Order confirmed to customer |
| `REJECTED` | Rejected by a business rule such as out-of-stock or payment declined |
| `CANCELLING` | Compensations are running |
| `CANCELLED` | Required compensations have completed |
| `COMPENSATION_PENDING` | Side effects remain to be compensated |
| `MANUAL_REVIEW` | Operator verification and audited resolution required |

Order state and saga execution state are two distinct perspectives: order state reflects business progress; saga state reflects running tasks, retries, and compensations.

Never allow clients to submit `status=CONFIRMED` directly. Only the workflow or owning service can perform valid state transitions after business conditions are met.

## 8. Happy Path and Compensation Path

| Forward Step | Local Transaction | Compensation on Downstream Failure |
|---|---|---|
| `CreateOrder` | Create order in `PENDING` | `CancelOrder` |
| `ReserveInventory` | Reserve quantity under a reservation ID | `ReleaseInventory` |
| `AuthorizePayment` | Place payment hold | `VoidAuthorization` |
| `CreateShipment` | Create shipment with carrier | `CancelShipment` |
| `CapturePayment` | Capture authorized funds | `RefundPayment` |
| `ConfirmOrder` | Transition order to `CONFIRMED` | Exception handling / manual review per policy |

If `ReserveInventory` returns out-of-stock, do not authorize payment and mark the order `REJECTED`. If `AuthorizePayment` is declined, release inventory and mark `REJECTED`. If `CreateShipment` fails, void authorization, release inventory, and mark `REJECTED`. If `CapturePayment` fails, cancel the shipment, void authorization, and release inventory. If `ConfirmOrder` fails after capture, verify provider state, then refund, cancel the shipment, and release inventory; if any compensation does not complete, leave the order in `COMPENSATION_PENDING`/`MANUAL_REVIEW`.

Happy path sequence:

1. Create order.
2. Reserve inventory.
3. Authorize payment.
4. Create shipment.
5. Capture payment.
6. Confirm order.
7. Emit `OrderConfirmed`.

If `CreateShipment` fails, the workflow voids authorization, releases inventory, and cancels the order. If `CapturePayment` fails, the workflow cancels the shipment, voids authorization, releases inventory, and cancels the order. If `ConfirmOrder` fails after capture, the workflow must verify payment status with the provider before issuing a refund, then cancel the shipment and release inventory per policy.

Compensation is a new business operation, not a global database rollback. For instance, refunds can take time, a carrier may already have picked up a shipment request, or a third party may reject cancellation. If compensation fails, record `COMPENSATION_PENDING`, store the reason, and escalate to manual review. Never mark the order `CANCELLED` as if every side effect were reversed.

## 9. API Contract for Order Creation

Minimum endpoints:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/orders` | Create an order and emit a saga start request via outbox |
| `GET` | `/orders/{orderId}` | Read current status |
| `GET` | `/orders/{orderId}/events` | Read authorized timeline |
| `POST` | `/orders/{orderId}/cancel` | Request cancellation if allowed by current transition |

Client request:

~~~http
POST /orders
Authorization: Bearer <access-token>
Idempotency-Key: 6a0d4d58-8f9c-4c3f-bb52-6c8f1c5d2f11
Content-Type: application/json
~~~

Example payload:

~~~json
{
  "customerId": "customer-1001",
  "items": [
    {
      "sku": "SKU-RED-01",
      "quantity": 2
    },
    {
      "sku": "SKU-BLUE-03",
      "quantity": 1
    }
  ],
  "shippingAddressId": "address-22",
  "paymentMethodRef": "pmref-customer-1001-01"
}
~~~

The backend must not trust client-supplied `customerId`, item prices, or totals. Extract customer/tenant identity from the verified JWT; fetch prices from a server-side catalog/pricing service or fixture; recalculate the total from server prices and validated quantities; verify that `paymentMethodRef` belongs to the authenticated customer. This is an opaque reference for Payment Service to look up the provider token in a vault; never place provider tokens into the Order record, Step Functions state, events, or logs. Never store PAN/CVV or raw card data.

The response should return `202 Accepted` with `orderId`, `sagaId`, and the status endpoint URL:

~~~json
{
  "orderId": "ord-2026-00042",
  "sagaId": "saga-2026-00042",
  "status": "PENDING",
  "statusUrl": "/orders/ord-2026-00042"
}
~~~

Do not hold an HTTP request open while carriers or payment providers process. Clients poll status or receive push notifications when the saga finishes.

## 10. Idempotency at the API Boundary

Clients may retry requests on timeouts, network drops, or missing responses. If each retry creates a new order, customers could be double-ordered and double-charged.

Idempotency design:

1. The client sends a stable `Idempotency-Key` for a single order intent.
2. The API normalizes the request and computes a request hash.
3. Store the key, customer ID, request hash, order ID, and processing status.
4. If the key already exists with the same request hash, return the same order/saga reference.
5. If the key exists with a different payload, return `409 Conflict`.
6. If the request is still in progress, return the current status instead of starting a new saga.

Idempotency records need retention aligned with business policy, and must never be purged while a saga is running or a dispute requires reconciliation. Never rely on Step Functions execution name alone as your only idempotency layer.

DynamoDB `ClientRequestToken` only makes the same `TransactWriteItems` request idempotent within a 10-minute window; it does not replace a longer-lived business idempotency key at the API boundary.

| Operation | Suggested Idempotency Key |
|---|---|
| `POST /orders` | `tenantId + Idempotency-Key` |
| `ReserveInventory` | `orderId + sku + reservationVersion` |
| `ReleaseInventory` | `orderId + sku + compensationId` |
| `AuthorizePayment` | `orderId + paymentAttempt` |
| `CapturePayment` | `orderId + authorizationId` |
| `VoidAuthorization` | `orderId + authorizationId + compensationId` |
| `RefundPayment` | `orderId + captureId + compensationId` |
| `CreateShipment` | `orderId + shipmentVersion` |
| Event consumer | `consumerName + eventId` |

AWS Lambda Powertools for Java provides an Idempotency utility backed by persistent stores like DynamoDB. The utility helps track processing state, though keys and recovery behavior must still reflect the concrete business operation.

## 11. Event Contract and Correlation

A domain event describes a fact that occurred, not a directive asking a consumer to execute an arbitrary command. Use a standard EventBridge envelope:

~~~json
{
  "source": "com.example.orders",
  "detail-type": "OrderCreated",
  "detail": {
    "eventId": "evt-ord-00042-v1",
    "schemaVersion": "1.0",
    "aggregateType": "Order",
    "aggregateId": "ord-2026-00042",
    "aggregateVersion": 1,
    "sagaId": "saga-2026-00042",
    "correlationId": "req-6a0d4d58",
    "causationId": "cmd-create-order-00042",
    "occurredAt": "2026-11-20T08:00:00Z",
    "customerId": "customer-1001",
    "total": {
      "amountMinor": 125000,
      "currency": "VND"
    }
  }
}
~~~

Key fields:

- `eventId`: stable domain event identifier for consumer deduplication.
- `schemaVersion`: payload version.
- `aggregateId`: order or entity emitting the event.
- `aggregateVersion`: sequence number of changes on the aggregate.
- `sagaId`: distributed workflow identifier.
- `correlationId`: links requests with logs, traces, and events.
- `causationId`: identifies the command or event that caused this change.
- `occurredAt`: business timestamp when the event occurred.

Never put access tokens, payment tokens, full addresses, or unnecessary personal data onto the event bus. Consumers can retrieve detailed data through authorized APIs.

EventBridge adds envelope fields such as `id`, `account`, `region`, `time`, and `version`. `eventId` inside `detail` is the stable producer-generated business event ID used to deduplicate publisher retries; the EventBridge-generated `id` may differ if the same event is submitted via `PutEvents` again. Consumers should use `detail.eventId` for business deduplication.

## 12. Essential Domain Events

| Event | Source | Example Consumers |
|---|---|---|
| `OrderCreated` | Order Service | Fraud, analytics |
| `InventoryReserved` | Inventory Service | Order projection |
| `InventoryReservationFailed` | Inventory Service | Saga/error reporting |
| `PaymentAuthorized` | Payment Service | Order projection |
| `PaymentFailed` | Payment Service | Fraud, support |
| `ShipmentCreated` | Shipping Service | Notification |
| `PaymentCaptured` | Payment Service | Finance, analytics |
| `OrderConfirmed` | Order Service | Email/SMS, CRM |
| `OrderCancellationStarted` | Order/Saga | Support |
| `OrderCancelled` | Order Service | Notification, analytics |
| `CompensationFailed` | Saga/participant | Operations/manual review |

Distinguish `OrderConfirmed` from `SendConfirmationEmail`. The first describes a business event; the second is a command. EventBridge rules should filter domain events by `source` and `detail-type`.

## 13. Transactional Outbox: Avoiding Dual-Writes

A common bug occurs when a service writes to its database and then calls EventBridge. If Lambda crashes between the two calls, the database changed without publishing the event. If the event is published first and the database rolls back, consumers receive a phantom event.

The transactional outbox pattern writes the entity change and the event record in the same database transaction:

~~~mermaid
sequenceDiagram
    participant S as Service Lambda
    participant D as DynamoDB
    participant T as DynamoDB Streams
    participant P as Outbox Publisher
    participant E as EventBridge
    S->>D: TransactWriteItems (entity + outbox)
    D-->>S: Commit atomically
    D->>T: Stream records
    T->>P: Invoke publisher
    P->>E: PutEvents
    E-->>P: Per-entry result
~~~

With DynamoDB, use `TransactWriteItems` to write the order/inventory/payment record and outbox item atomically. Enable DynamoDB Streams on the outbox table or the table holding outbox records. A Lambda publisher reads the stream and calls `PutEvents`.

Notes:

- Stream consumers can receive duplicate records; the publisher must handle duplicates.
- Check `FailedEntryCount` and each entry result in the `PutEvents` response; HTTP success does not mean every event was published.
- The publisher may crash after EventBridge accepts an event but before marking the outbox item as published. Consumers must still deduplicate by `eventId`.
- Record `aggregateVersion` or a sequence number so consumers detect out-of-order events.
- Do not assume multiple items written in the same DynamoDB transaction appear simultaneously or contiguously in the stream.
- Outbox records should carry `PENDING`/`PUBLISHED` status, `eventId`, and aggregate sequence. The publisher updates status to `PUBLISHED` after EventBridge accepts the entry; if a crash occurs between `PutEvents` and the status update, duplicates can still occur, so consumers must deduplicate.
- Add a scheduled sweeper to find stale `PENDING` outbox records and recover when a stream consumer is interrupted or records miss timely processing.
- The EventBridge rule matching `OrderCreated` needs a retry policy, a target DLQ, `lambda:InvokeFunction` permission on Saga Starter, and alarms. Saga Starter's role holds `states:StartExecution` on the specific state machine. Archiving/replay can be enabled for investigation or controlled replay; replays must still pass through idempotent consumers.

DynamoDB Streams retains stream records for only 24 hours. The outbox item serves as the durable record so the publisher sweeper can recover even after stream retention expires or a consumer experiences a prolonged outage.

The transactional outbox solves dual-writes between a local database and event emission. It does not turn multiple service databases into a global transaction. https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html

## 14. Suggested DynamoDB Data Model

You can start with one table per bounded context or a multi-tenant table with explicit key design.

| Table / Item | Partition Key | Sort Key | Contents |
|---|---|---|---|
| `Orders` | `ORDER#<orderId>` | `META` | customer/tenant, totals, status, version, sagaId |
| `OrderItems` | `ORDER#<orderId>` | `ITEM#<sku>` | SKU, quantity, server-side price snapshot |
| `OrderOutbox` | `ORDER#<orderId>` | `EVENT#<sequence>#<eventId>` | event type, schema version, payload, PENDING/PUBLISHED |
| `Idempotency` | `TENANT#<tenantId>#KEY#<key>` | `REQUEST` | request hash, orderId, response, status, expiry |
| `SagaRegistry` | `SAGA#<sagaId>` | `META` | executionName, inputHash, executionArn, STARTING/RUNNING/terminal state |
| `Inventory` | `SKU#<sku>` | `STOCK` | available, reserved, version |
| `Reservations` | `ORDER#<orderId>` | `SKU#<sku>` | reservationId, quantity, state, expiry |
| `Payments` | `ORDER#<orderId>` | `PAYMENT#<operation>` | provider reference, amount, status, idempotency key |
| `Shipments` | `ORDER#<orderId>` | `SHIPMENT` | carrier reference, status, trackingId |
| `ProcessedEvents` | `CONSUMER#<name>#EVENT#<eventId>` | `META` | processedAt, result, expiry |

With DynamoDB transactions, operations can update multiple items/tables within the same account and Region all-or-nothing. Keep transactions small and within a single service boundary. Never use `TransactWriteItems` to coordinate an external payment provider or another service's database. https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transactions.html

In production, choose one table per bounded context or a single-table design based on actual access patterns. The table above is a logical model illustrating ownership; each row does not have to be a separate physical table.

## 15. Reserving Inventory with Conditional Writes

To prevent overselling, the reservation operation must check available quantity within the same update:

~~~text
Update Inventory item:
  SET available = available - :qty,
      reserved = reserved + :qty,
      version = version + 1
  CONDITION available >= :qty
            AND version = :expectedVersion
~~~

In the same transaction, create the reservation record with an `attribute_not_exists` condition on the reservation key. For orders with multiple SKUs, aggregate duplicate SKU lines before building `TransactWriteItems` and update each SKU exactly once; if any condition fails, the entire transaction fails with no partial reservation.

Releasing inventory must also be idempotent: transition a reservation from `RESERVED` to `RELEASED` at most once; if already `RELEASED`, return the prior result; if the reservation never existed, perform a safe no-op. If a reservation is already `COMMITTED`/`SHIPPED`, do not release via normal compensation; use a separate return/restock workflow.

## 16. Payment Adapter and Idempotency

Payment Service should not let the saga workflow call the payment provider directly from multiple different Lambdas. Use a dedicated adapter owning:

- Payment authorization.
- Capture.
- Void authorization.
- Refund.
- Transaction state querying/reconciliation.
- Secret rotation and provider-specific error mapping.

Use deterministic idempotency keys, for example:

- `authorize:<orderId>:<paymentAttempt>`
- `capture:<orderId>:<authorizationId>`
- `refund:<orderId>:<captureId>:<compensationId>`

Store provider transaction IDs and statuses in the Payment table. If a request times out after the provider may have processed it, do not immediately submit a new charge. First query the provider using the idempotency key or reference to verify whether the result committed.

Payment providers vary in semantics, idempotency key expiration, and status codes. The adapter must normalize these differences into a consistent internal contract. Never write card details or provider secrets into Step Functions input/output.

### Shipping Participant

Shipping Service receives `orderId`, validated address, package details, and a shipment idempotency key. `CreateShipment` must return the same carrier reference when invoked with the same business request. If the carrier times out, query the carrier using the merchant reference before creating a new booking.

`CancelShipment` is a conditional compensation: if no shipment was created, return a successful no-op; if `CREATED`/`BOOKED`, cancel per carrier policy; if the parcel has already been handed over or the carrier rejects cancellation, create an exception case for operators to process a return/refund. An HTTP 200 from a carrier does not mean goods have been delivered.

## 17. Saga State Machine with Step Functions

Choose Standard workflow for the saga because the process has multiple steps, compensations, and requires execution history. Workflow inputs should contain only IDs, correlation metadata, and required business references. Do not pass full customer profiles or payment details through state payloads.

Primary flow:

~~~mermaid
flowchart TD
    A["CreateOrder"] --> B["ReserveInventory"]
    B --> C["AuthorizePayment"]
    C --> D["CreateShipment"]
    D --> E["CapturePayment"]
    E --> F["ConfirmOrder + outbox commit"]
    F --> H["Succeed"]
    B -. failure .-> X["Compensation"]
    C -. failure .-> X
    D -. failure .-> X
    E -. failure .-> X
    F -. failure .-> X
    X --> Y["Cancel shipment if created"]
    Y --> Z["Refund capture or void authorization"]
    Z --> R["Release inventory"]
    R --> O["Cancel order"]
    O --> M["Failed / Manual review"]
~~~

Each Task invokes a participant Lambda via the optimized integration `arn:aws:states:::lambda:invoke`. `ResultPath` preserves references such as `reservationId`, `authorizationId`, `shipmentId`, and `captureId` for compensations to reuse. Use `Retry` for transient errors; `Catch` transitions to compensation when a business step fails.

Business rejections should return structured outputs so a `Choice` state can branch—such as `reserved=false` or `authorized=false`—while infrastructure errors trigger `Retry`/`Catch`. Saga Starter Lambda receives `OrderCreated` from EventBridge and calls `StartExecution`. Derive a deterministic execution name from `sagaId`; duplicate deliveries must look up the existing execution or treat `ExecutionAlreadyExists` as a recognized duplicate rather than launching a second saga.

Standard workflows provide an exactly-once execution model at the workflow state level unless `Retry` is configured. That does not eliminate the need for participant idempotency: external providers may have committed side effects even when the caller missed the response, and event delivery can repeat. https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html

## 18. ASL Example: Retry and Catch for a Participant

Below is a state machine excerpt demonstrating how to invoke Inventory Service. Replace Lambda ARNs and state names with your deployment environment's resources. Other steps follow the same pattern with their respective compensations.

~~~json
{
  "Comment": "Order saga - inventory step example",
  "StartAt": "ReserveInventory",
  "States": {
    "ReserveInventory": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:ap-southeast-1:111122223333:function:reserve-inventory",
        "Payload.$": "$"
      },
      "ResultSelector": {
        "reservationId.$": "$.Payload.reservationId",
        "status.$": "$.Payload.status"
      },
      "ResultPath": "$.inventory",
      "Retry": [
        {
          "ErrorEquals": [
            "Lambda.ServiceException",
            "Lambda.AWSLambdaException",
            "Lambda.SdkClientException",
            "Lambda.TooManyRequestsException"
          ],
          "IntervalSeconds": 2,
          "MaxAttempts": 3,
          "BackoffRate": 2,
          "JitterStrategy": "FULL"
        }
      ],
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.failure",
          "Next": "CompensateOrder"
        }
      ],
      "Next": "ContinueSaga"
    },
    "ContinueSaga": {
      "Type": "Succeed"
    },
    "CompensateOrder": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:ap-southeast-1:111122223333:function:cancel-order",
        "Payload.$": "$"
      },
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "Next": "ManualReview"
        }
      ],
      "Next": "Failed"
    },
    "ManualReview": {
      "Type": "Fail",
      "Error": "CompensationFailed",
      "Cause": "Order requires operator review"
    },
    "Failed": {
      "Type": "Fail",
      "Error": "OrderSagaFailed",
      "Cause": "Inventory reservation failed"
    }
  }
}
~~~

In the full workflow, compensations must inspect which steps actually committed. Do not call `ReleaseInventory` if no reservation exists; do not call `RefundPayment` if payment was never captured. If payment status is unknown due to a timeout, query the provider before deciding to void or refund. Define stable business error names such as `OutOfStock`, `PaymentDeclined`, and `CarrierUnavailable` to distinguish business errors from infrastructure failures.

This is a fragment illustrating a single Task and error path, not a complete deployable state machine. A compensation coordinator must read existing operation references, execute only the corresponding compensations, and record each compensation's outcome. If one independent compensation fails, other safe compensations can still proceed before aggregating `MANUAL_REVIEW`.

## 19. Designing Compensations Based on Committed Progress

The orchestrator must store the output/reference of each successful step. On failure, walk backward through completed steps:

1. If `shipmentId` exists, call `CancelShipment`.
2. If `captureId` exists, query payment and call `RefundPayment`; if only `authorizationId` exists, call `VoidAuthorization`.
3. If `reservationId` exists, call `ReleaseInventory`.
4. If `orderId` exists, call `CancelOrder`.
5. If a compensation fails, record `COMPENSATION_PENDING`, store the error, and raise a manual review alert.

Compensations must be idempotent and have dedicated timeouts. A failure in `CancelShipment` should not cause the system to skip all remaining compensations if they are still safe to run. You can record each compensation result, continue independent actions, and finalize the workflow as `COMPENSATED` or `MANUAL_REVIEW`.

Never delete order records to simulate a rollback. Retain `CANCELLED`, `REFUND_PENDING`, `COMPENSATION_FAILED`, and audit metadata for customer support and reconciliation.

## 20. Retries, Timeouts, and Error Taxonomy

Classify errors before configuring `Retry`:

| Category | Examples | Handling |
|---|---|---|
| Transient infrastructure | Lambda throttling, network error, provider 5xx | Retry with exponential backoff and jitter |
| Business rejection | `OutOfStock`, `PaymentDeclined`, invalid address | Do not auto-retry; compensate or return business error |
| Permanent configuration | `AccessDenied`, invalid secret, missing resource | Fail fast, alarm, and fix configuration |
| Ambiguous outcome | Provider timeout when charge may have succeeded | Query/reconcile before retrying side effects |
| Compensation failure | Carrier refuses cancellation, refund pending | Manual review and controlled compensation retry |

Example `Retry` block:

~~~json
{
  "ErrorEquals": [
    "Lambda.ServiceException",
    "Lambda.SdkClientException",
    "States.Timeout"
  ],
  "IntervalSeconds": 2,
  "MaxAttempts": 4,
  "BackoffRate": 2,
  "MaxDelaySeconds": 30,
  "JitterStrategy": "FULL"
}
~~~

Set `TimeoutSeconds` per Task based on participant/provider latency. Set an overall workflow timeout aligned with the order SLA. Never blindly retry `States.ALL`: business rejections and configuration errors will never self-heal.

Step Functions supports `Retry` and `Catch` on `Task`, `Parallel`, and `Map` states. `Retry` supports `IntervalSeconds`, `BackoffRate`, `MaxAttempts`, `MaxDelaySeconds`, and `JitterStrategy`; `Catch` transitions the workflow to an error-handling state. https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html

## 21. EventBridge Routing and SQS Consumers

Create a custom event bus, e.g., `orders-domain-bus`. Define rules matching `source` and `detail-type`:

~~~json
{
  "source": ["com.example.orders"],
  "detail-type": [
    "OrderConfirmed",
    "OrderCancelled"
  ]
}
~~~

This rule can route events to SQS `order-notifications`. Another rule can send `PaymentCaptured` to an analytics or finance queue. Each consumer receives only the events it needs.

SQS standard queues fit when throughput and decoupling matter more than strict ordering. Consumers must tolerate at-least-once delivery and deduplicate. If per-order ordering is needed, design with FIFO queues using `MessageGroupId` per aggregate and verify EventBridge/target compatibility.

Never let Notification Service trigger payment or inventory compensations. Notifications are side effects after business state commits.

Standard queues provide high throughput without strict ordering guarantees. FIFO preserves ordering within each `MessageGroupId`; use `orderId` as the group key if messages for the same order must run sequentially while different orders process in parallel. FIFO's finite deduplication window does not replace database/provider idempotency.

The notification consumer should track delivery attempts and statuses separately. If the email/SMS provider fails, queue retries or the DLQ handle it while the order stays `CONFIRMED`. A read model can subscribe to `OrderCreated`/`OrderConfirmed`/`OrderCancelled` for dashboards, while `GET /orders` should read from the authoritative data source when the latest state is required.

## 22. DLQs, Delivery Retries, and Redrive

There are two distinct failure layers:

| Layer | Failure | DLQ |
|---|---|---|
| EventBridge → SQS target | EventBridge fails to deliver the event to the target | EventBridge target DLQ (standard SQS queue) |
| SQS → Lambda consumer | Consumer receives the message but fails repeatedly | SQS source queue DLQ of matching queue type |

For SQS source queues, configure an appropriate `maxReceiveCount` and a DLQ retention period long enough for investigation. When messages land in a DLQ, inspect exceptions, schema versions, consumer deployments, and dependencies before redriving.

EventBridge has its own retry policy and can route failed target deliveries to a target DLQ. Certain configuration errors such as missing permissions or a non-existent target may go straight to the DLQ without retrying. https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-rule-dlq.html

SQS DLQs isolate messages that consumers cannot process and support redriving after fixing the root cause. With FIFO queues, consider ordering implications when using a DLQ. https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html

Set visibility timeout greater than the consumer's maximum expected processing time. For Lambda SQS event source mappings, AWS recommends a visibility timeout of at least six times the function timeout plus the maximum batching window. Configure `maxReceiveCount` so poison messages do not loop forever; for batch processing, enable `ReportBatchItemFailures` so only failed records retry rather than the whole batch. DLQs need clear retention, encryption, alarms, and ownership.

## 23. Concurrency, Semantic Locks, and Optimistic Concurrency

Sagas do not provide global isolation. Two sagas can attempt to modify the same order, SKU, or payment reference concurrently. Use these mechanisms:

- Increment `version` on every transition.
- Conditional updates requiring the expected current `version` and `state`.
- Dedicated reservation records with their own state and ID.
- Payment capture allowed only while authorization is valid and uncaptured.
- Cancellation allowed only before specific business milestones.
- Idempotency keys for commands and events.
- Semantic locks such as `order.status = PROCESSING` or `activeSagaId` to block conflicting commands.

For example, update an order only when `status = PENDING` and `version = 3`. If another saga already updated it to version 4, the stale operation must fail with a conflict and follow business rules instead of overwriting the newer state.

Do not hold long-lived distributed locks in DynamoDB to mimic global ACID transactions. Prefer conditional writes, and use expiring leases only if locking is genuinely required.

## 24. Handling Duplicates and Event Ordering

EventBridge, SQS standard, and Lambda event source mappings can produce duplicate deliveries. An idempotent consumer should:

1. Read `eventId` and `aggregateVersion`.
2. Check whether the event has already been recorded in the `Inbox`/`ProcessedEvents` store.
3. If already processed, return success without repeating side effects.
4. If the version is older than the current state, ignore it or send it to reconciliation.
5. If a version gap is detected, query the authoritative source or wait for the missing event.
6. Write the processed marker and business update within a single local transaction.

Do not rely solely on timestamps to order events. Use monotonically increasing sequences or versions per aggregate. If strict ordering is required, design partition/group keys and queue types accordingly while still handling duplicates.

Write the `ProcessedEvents`/`Inbox` marker together with the business update in one local transaction when the consumer writes to DynamoDB. If the consumer must call an external provider, persist operation state before the call, pass a provider idempotency key, and reconcile ambiguous outcomes before retrying. Never mark an event completed before the side effect has a confirmed outcome.

## 25. Observability and Auditing

Every request should carry:

- `orderId`
- `sagaId`
- `correlationId`
- `causationId`
- `eventId`
- `aggregateVersion`
- Redacted `paymentReference` or `shipmentReference` stripped of sensitive data

CloudWatch Logs should emit structured JSON. Step Functions execution history reveals which states succeeded or failed along with error outputs. X-Ray connects API Gateway, Lambda, and downstream calls. CloudWatch alarms should monitor:

| Metric / Signal | Meaning |
|---|---|
| Saga success/failure rate | Order completion ratio |
| Saga duration p50/p95/p99 | End-to-end processing latency |
| Compensation count/failure | Number of transactions requiring compensation |
| Payment authorize/capture/void/refund failures | Health of payment integration |
| Inventory reservation conflicts | Stock contention and oversell protection |
| SQS `ApproximateAgeOfOldestMessage` | Consumer backlog |
| DLQ visible messages | Unprocessable messages |
| EventBridge failed invocations | Target delivery failures |
| Lambda errors/throttles/duration | Function errors and capacity |
| Step Functions timed out/aborted | Sagas missing SLAs |

Track additional operational signals:

| Metric / Signal | Purpose |
|---|---|
| `OrdersCreated` | New order volume |
| `CompensationStarted` / `CompensationFailed` | Frequency and reliability of compensations |
| `OrdersManualReview` | Cases requiring operator intervention |
| `InventoryReservationRejected` | Out-of-stock or conditional conflict rate |
| `PaymentDeclined` / `PaymentUnknown` | Distinguish declines from ambiguous provider outcomes |
| DynamoDB `ThrottledRequests` / `TransactionConflict` | Capacity and contention |
| EventBridge DLQ depth / failed invocations | Blocked event deliveries |
| SQS DLQ depth / `ApproximateAgeOfOldestMessage` | Poison messages and consumer backlog |

Create alarms for queue age exceeding SLAs, non-empty DLQs, failed/timed-out sagas, rising compensations/manual reviews, rising transaction conflicts/throttles, and lingering `PaymentUnknown` states. Every alarm needs a runbook and an owner.

Never log bearer tokens, payment tokens, CVV, PAN, secrets, or full street addresses. Audit records should capture before/after state, actor, timestamp, and change reason per retention policy.

## 26. Security and IAM Boundaries

Separate execution roles by component:

| Role | Typical Least-Privilege Permissions |
|---|---|
| API/Order API Lambda | Authenticate requests; write `Orders`, `Idempotency`, and `Outbox` |
| Step Functions role | Invoke specific participant Lambda ARNs; publish to the specific EventBridge bus if the workflow emits events directly |
| Order Lambda role | Read/write `Orders` and `Outbox` |
| Inventory Lambda role | Read/write `Inventory` and `Reservations` |
| Payment Lambda role | Read/write `Payments`; read required provider secrets |
| Shipping Lambda role | Read/write `Shipments`; read required carrier secrets |
| Outbox publisher role | Read DynamoDB Stream and `events:PutEvents` on the specific bus |
| Saga Starter role | `states:StartExecution` on the exact Step Functions state machine |
| EventBridge target role | `lambda:InvokeFunction` on Saga Starter Lambda |
| Consumer role | Consume its own queue and write its own datastore |

Additional controls:

- Configure API Gateway with a JWT/Cognito/OIDC authorizer and throttling.
- Use WAF to protect public APIs against common abuse patterns.
- Store provider credentials in Secrets Manager; avoid hard-coding secrets in Lambda environment variables whenever possible.
- Enable KMS encryption for DynamoDB, SQS, Secrets Manager, and log groups per requirements.
- Scope resource policies for cross-account integrations by source ARN and account.
- Place Lambda inside a VPC only when accessing private resources; evaluate NAT/VPC endpoints to avoid unnecessary egress costs and connectivity errors.
- Enable CloudTrail to audit control-plane changes.
- Keep EventBridge/SQS payloads minimal and enforce appropriate data retention.

Lambda does not need VPC attachment just to call DynamoDB, EventBridge, or SQS over AWS service endpoints. When access to a private database or private service is required, design subnets, security groups, VPC endpoints/NAT, and DNS explicitly; NAT Gateway hours and data processing can generate significant charges. Never include payment tokens, bearer tokens, PAN/CVV, or full addresses in logs or event payloads.

## 27. Infrastructure as Code and Deployment

Use AWS CDK or AWS SAM to provision:

- API Gateway routes and authorizer.
- Lambda functions and execution roles.
- Step Functions Standard state machine.
- DynamoDB tables, indexes, TTLs, and Streams.
- EventBridge custom bus, rules, and targets.
- SQS queues, DLQs, redrive policies, and queue policies.
- CloudWatch log groups, dashboards, and alarms.
- KMS keys and Secrets Manager references.
- Resource-scoped IAM policies.

Separate dev, test, and prod environments by account or stack configuration. Never share payment secrets or queues between test and production. State machine ARNs, table names, and bus ARNs should be injected through deployment outputs or configuration.

Reference repository layout:

~~~text
order-saga/
  README.md
  infra/
    template.yaml
    parameters/
      dev.json
      test.json
  contracts/
    events/
      order-created-v1.json
      inventory-reserved-v1.json
      payment-authorized-v1.json
      order-confirmed-v1.json
  workflows/
    order-saga.asl.json
  services/
    order-api/
    outbox-publisher/
    inventory/
    payment/
    shipping/
    order-state/
    notification/
  tests/
    unit/
    integration/
    contract/
    saga-failure/
    load/
  runbooks/
    payment-unknown.md
    compensation-failed.md
    eventbridge-dlq.md
    sqs-dlq.md
~~~

## 28. CI/CD and Contract Versioning

The pipeline should include:

1. Linting and unit tests for each service.
2. Validation of OpenAPI/API schemas and event JSON schemas.
3. Validation of the ASL definition before deployment.
4. Building Lambda artifacts or container images.
5. Deploying infrastructure to dev.
6. Running integration tests and failure injection.
7. Promoting immutable artifacts to test/staging.
8. Manual approval before production if required by governance.
9. Deploying backward-compatible schema changes before consumer rollouts.
10. Monitoring alarms and rolling back per release plan.

The Step Functions state machine definition also needs version control. Use aliases/versions or an appropriate deployment strategy so running executions are not disrupted unexpectedly. Event consumers must remain able to read event versions still present within the retention/replay window.

## 29. Testing Plan

### Unit Tests

- Validate order items, quantities, and currency.
- Inventory conditional reserve/release logic.
- Payment state transitions.
- Idempotency keys and request hashes.
- Compensation functions.
- Event schema validation.

### Integration Tests

- API → Step Functions → participants.
- DynamoDB transaction + outbox stream.
- Outbox publisher → EventBridge.
- EventBridge rule → SQS.
- SQS → Lambda consumer.
- Secrets/KMS/IAM permissions.

### Failure Injection

| Scenario | Expected Outcome |
|---|---|
| SKU out of stock | Order cancelled; payment is never authorized |
| Payment declined | Inventory released; order cancelled |
| Carrier timeout | Bounded retries, then payment voided and stock released |
| Capture timeout after provider captured | Query provider; never double-charge |
| `ConfirmOrder` fails after capture | Refund/reconciliation and manual review if needed |
| Duplicate API request | Returns the same order reference |
| Duplicate EventBridge/SQS event | Consumer does not repeat side effects |
| Consumer poison message | Message lands in DLQ; alarm triggers |
| Compensation API error | `COMPENSATION_PENDING`, manual review created |
| Two orders buying the last SKU | Only one reservation succeeds |
| Outbox publisher crashes after `PutEvents` | Duplicate deduplicated via `eventId` |
| Saga execution timeout | Alert and reconciliation; state preserved |
| Inventory timeout after commit | Retry returns prior reservation via idempotency key |
| Payment timeout after authorization | Query provider; never authorize twice |
| EventBridge target delivery failure | Retries, then target DLQ and alarm |
| Concurrent `ConfirmOrder` and cancel | Conditional status/version permits only one valid transition |
| Event consumer batch with one failing record | Partial batch failure retries only the failed record without duplicating succeeded records |

Test both the happy path and every failure point. Unit testing individual Lambda handlers alone is insufficient to prove saga recoverability.

## 30. Phased Capstone Implementation Workflow

### Phase 1: Domain Design

- Define order lifecycle and invariants.
- Identify service boundaries.
- Define event contracts and idempotency keys.
- Diagram success and compensation flows.

**Deliverable:** context diagram, state diagram, API contract, and event catalog.

### Phase 2: Order API and Outbox

- Implement `POST /orders` and `GET /orders/{id}`.
- Validate requests, authenticate customers, and compute totals server-side.
- Write order, idempotency record, and outbox event via DynamoDB `TransactWriteItems`.
- Enable DynamoDB Streams and implement Outbox Publisher Lambda.
- Handle partial `PutEvents` failures and add a scheduled sweeper for stale `PENDING` outbox records.

**Deliverable:** orders are created once from a business standpoint despite client retries; `OrderCreated` is never lost during transient publisher failures.

### Phase 3: EventBridge and Step Functions

- Create a custom event bus and an `OrderCreated` rule targeting Saga Starter Lambda.
- Select Standard workflow, write Task/Choice states, and configure `Retry`/`Catch`.
- Store operation references in workflow state.
- Derive deterministic execution names from `sagaId` and handle duplicate `StartExecution`.

**Deliverable:** each order maps to a single traceable saga execution.

### Phase 4: Build Participants

- Implement Order, Inventory, Payment, and Shipping handlers.
- Provision DynamoDB tables and conditional writes.
- Implement idempotency logic.
- Write outbox records inside local transactions.

**Deliverable:** unit tests and service contracts.

### Phase 5: Compensation and Manual Review

- Implement reverse-order compensations and ensure no-op idempotency on repeat calls.
- Distinguish business failures from technical failures.
- Add bounded retries/backoff.
- On compensation failure, record `COMPENSATION_PENDING`/`MANUAL_REVIEW` and raise alerts.

**Deliverable:** compensation workflow and operator runbook.

### Phase 6: Notifications, Security, and Observability

- Route `OrderConfirmed`/`OrderCancelled` to SQS and build independent consumers.
- Scope IAM roles; enable KMS, Secrets Manager, and the API authorizer.
- Add structured logs, metrics, tracing, alarms, and dashboards.
- Verify PII/secret redaction and cost budgets.

**Deliverable:** security review, dashboard, and runbooks.

### Phase 7: Testing and Release

- Run acceptance tests.
- Simulate failures at each participant.
- Verify compensations and manual review.
- Reconcile order, inventory, and payment states.
- Demo duplicate handling and DLQ redrive.

**Deliverable:** demo, test report, architecture decision records, deployment guide, and cost estimate.

## 31. Acceptance Criteria

The capstone is considered complete when:

- Creating an order returns `202` with `orderId`/`sagaId`.
- Repeated requests with the same idempotency key do not create new orders.
- The happy path transitions the order to `CONFIRMED`.
- Inventory reservations prevent overselling under concurrent requests.
- Payment authorize/capture calls do not duplicate transactions on retries.
- Payment failures release inventory and update order state.
- Shipment failures trigger compensations in the proper order.
- Compensation failures transition to `COMPENSATION_PENDING` and trigger alerts.
- Domain events are emitted after local transactions commit.
- Outbox publisher handles partial `PutEvents` failures, duplicates, and pending-event recovery.
- EventBridge rules invoke Saga Starter; Starter deduplicates and starts Step Functions Standard by `sagaId`.
- Consumers deduplicate repeated events.
- SQS poison messages route to DLQs with documented redrive steps.
- `PaymentUnknown` is reconciled with the provider before retrying side effects.
- Compensation failures route to `MANUAL_REVIEW` with an audit record.
- CloudWatch dashboards trace a saga end-to-end by `sagaId`.
- IAM roles grant permissions only to required resources.
- Logs and event payloads contain no payment secrets or raw card data.
- Deployment, testing, cleanup documentation, and cost estimates are provided.

## 32. Costs and Operational Limits

Components are billed along different dimensions:

- API Gateway by request count and API type.
- Lambda by invocations, duration, and memory.
- Step Functions Standard by state transitions.
- DynamoDB by read/write capacity or on-demand requests, storage, and Streams.
- EventBridge by events/operations.
- SQS by requests, payload size, and features used.
- CloudWatch by log ingestion/storage, metrics, and alarms.
- X-Ray by traces.
- KMS by keys and API requests.
- NAT Gateway or data transfer can become significant if VPC-attached Lambdas call the Internet.

Cost controls:

- Use DynamoDB on-demand for demo workloads with unpredictable traffic.
- Keep payloads compact and avoid unnecessary service calls.
- Set log retention instead of keeping logs indefinitely.
- Bound retries and timeouts.
- Never retry business errors.
- Configure budget notifications on sandbox accounts.
- Clean up unused queue messages, test records, and secrets.
- Monitor NAT data processing if Lambdas need outbound provider access.

Do not hard-code a fixed cost figure in the design. Calculate costs for your target Region, request volume, state transitions, durations, payload sizes, and actual retention using AWS Pricing Calculator.

| Service | Primary Cost Drivers | Controls |
|---|---|---|
| API Gateway | Requests and data transfer | Throttling; cache read paths where appropriate |
| Lambda | Invocations, duration, memory, and concurrency | Optimize handlers, timeouts, and reserved concurrency |
| Step Functions Standard | State transitions | Avoid polling and unnecessary state transitions |
| DynamoDB | Read/write requests, storage, Streams, and backups | Design access patterns, use On-Demand for variable traffic, avoid hot partitions |
| EventBridge | Events ingested/processed, archive, and replay | Compact payloads, precise rule patterns, intentional retention |
| SQS | Requests, payloads, and DLQ retention | Batch receives, visibility timeouts, and consumer throughput |
| CloudWatch/X-Ray | Log ingestion/storage, metrics, alarms, and traces | Redaction, sampling, and per-environment retention |
| KMS/Secrets Manager | Keys, secret storage, and API requests | Cache secrets safely, reuse SDK clients |

To scale, cap Payment adapter concurrency to match provider quotas; configure reserved concurrency for critical participants; buffer bursts with SQS; choose well-distributed partition keys; and monitor hot SKUs and contention. Very high-traffic inventory SKUs may require sharded counters or a specialized reservation strategy once the baseline conditional-write design is proven.

## 33. Operational Runbooks

### Stuck Saga

1. Look up `sagaId` in Step Functions.
2. Identify the running or failed state.
3. Inspect the error name/cause and participant logs.
4. Check dependencies: Lambda throttling, DynamoDB condition conflicts, provider timeouts.
5. Never start a new saga with a different key before verifying the state of prior side effects.

### Unknown Payment Outcome

1. Retrieve the payment idempotency key and provider reference.
2. Query the provider for transaction status.
3. If already captured, record the capture reference and continue reconciliation.
4. If not captured, decide whether to retry per the provider contract.
5. Never submit a new charge solely because Lambda timed out.

### Queue Has DLQ Messages

1. Check DLQ depth and oldest message age.
2. Inspect error metadata, schema version, and consumer deployment.
3. Fix the underlying schema, permission, or dependency issue.
4. Test with a single message in a test environment.
5. Redrive in small batches.
6. Monitor duplicate handling and business state after redrive.

### EventBridge Target DLQ

1. Inspect the event envelope, target ARN, target role, and delivery error.
2. Check via `sagaId`/`eventId` whether the saga or consumer already processed the event.
3. Fix permissions, target configuration, or downstream dependencies.
4. Replay/redrive in small batches; preserve the business `eventId` for deduplication.
5. Monitor target delivery metrics and DLQ depth after recovery.

### Compensation Failure

1. Keep the order in `COMPENSATION_PENDING` or `MANUAL_REVIEW`.
2. Record the compensation action, request ID, provider reference, and error.
3. Query actual state from payment/carrier/inventory systems.
4. Retry compensation only with the original idempotency key and verified state.
5. Reconcile order, stock, and payment records before closing the case.

## 34. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Calling multiple databases in one Lambda and assuming global ACID | Partial commits | Saga with local transactions and compensations |
| Publishing events after DB writes without an outbox | Lost events or phantom events | Transactional outbox |
| Missing idempotency keys | Duplicate orders/charges | Stable keys at API and participants |
| Relying solely on Step Functions exactly-once | External side effects repeat on ambiguous outcomes | Idempotency and provider reconciliation |
| Treating compensation as deleting records | Audit trail lost, external side effects unreversed | Explicit business compensations |
| Sharing one queue across all consumers | Slow consumers impact healthy ones | Dedicated queue per consumer |
| No DLQ | Poison messages loop endlessly or vanish | DLQs, alarms, and redrive runbooks |
| Putting too much PII in events | Data exposure risk | Minimal event payloads |
| Unversioned event schemas | Deploying a new consumer breaks older messages | Schema versioning and backward compatibility |
| Retrying all errors | Higher cost, prolonged failures | Error taxonomy and bounded retries |
| Missing conditional stock updates | Overselling | Conditional writes/transactions |
| No semantic locking | Concurrent sagas overwrite each other | Optimistic concurrency and valid transitions |

## 35. Self-Study Exercises

1. Why does an order workflow need a saga when services own separate databases?
2. How does saga orchestration differ from choreography?
3. Why choose Step Functions Standard for the order saga?
4. How does a domain event differ from a command?
5. How do EventBridge and SQS responsibilities differ?
6. Why should the create-order API return `202 Accepted`?
7. What failure does an idempotency key solve at the API boundary?
8. Why should you never trust client-supplied prices and customer IDs?
9. What conditional write is needed for inventory reservation?
10. Why does the payment adapter need a provider idempotency key?
11. How does compensation differ from a database rollback?
12. If `CapturePayment` times out, why shouldn't you retry the charge immediately?
13. How does a transactional outbox solve dual-writes?
14. Why do outbox consumers still need deduplication?
15. What problem does `aggregateVersion` help solve?
16. Why avoid storing the entire order payload in Step Functions state?
17. How does an EventBridge target DLQ differ from an SQS consumer DLQ?
18. When should a FIFO queue be used?
19. How do semantic locks protect the order workflow?
20. If compensation fails, what status should the order remain in?
21. Why doesn't Standard workflow exactly-once replace participant idempotency?
22. Which metrics help detect a queue backlog?
23. How do you safely redrive a DLQ?
24. Which data should never appear in event/log payloads?
25. What criterion proves the system does not oversell?
26. Why doesn't SQS FIFO's deduplication window replace consumer idempotency?
27. Why shouldn't an email/SMS delivery failure automatically cancel a `CONFIRMED` order?

### Answer Hints

1. No single ACID transaction spans multiple datastores/providers; a saga coordinates local transactions and compensations.
2. Orchestration uses a central coordinator; choreography lets participants react to events independently.
3. Long-running workflow requiring durable execution, `Retry`/`Catch`, and execution history.
4. An event describes what happened; a command requests an action to be performed.
5. EventBridge routes events; SQS buffers and decouples consumer processing rates.
6. Asynchronous workflows can take time; the client receives an order reference and polls status.
7. Prevents retried requests from creating duplicate orders or payment attempts.
8. Clients can tamper with payloads; the server must obtain identity and prices from trusted sources.
9. Update available quantity only when `available >= requested`, combined with version/reservation conditions.
10. Retries may repeat requests after timeouts; the provider key identifies the same payment intent.
11. Compensation is a new business operation that can itself fail and requires auditing.
12. The provider may have captured funds despite a lost response; query status first.
13. The entity and outbox event are committed inside the same local transaction.
14. Streams/publishers may redeliver records or crash after publishing.
15. Detects stale, missing, or out-of-order events for the same aggregate.
16. Payloads face size quotas, risk exposing PII, and increase costs; pass only IDs/references.
17. EventBridge DLQs hold failed target deliveries; SQS DLQs hold messages consumers failed to process.
18. When strict ordering per message group is a genuine requirement.
19. Blocks conflicting transitions and protects state/version integrity.
20. `COMPENSATION_PENDING` or `MANUAL_REVIEW`—never pretend rollback completed cleanly.
21. External side effects may have committed without the caller receiving a response; retries/duplicates still require handling.
22. `ApproximateAgeOfOldestMessage`, visible messages, DLQ depth, and Lambda throttles/errors.
23. Fix the root cause, test one message, redrive in small batches, and rely on deduplication.
24. Tokens, PAN/CVV, secrets, bearer credentials, and unnecessary PII.
25. Concurrency tests proving total reservations never exceed available stock.
26. FIFO's deduplication window is finite; consumers can still receive redeliveries after timeouts, redrives, or ambiguous side effects.
27. Notifications are post-commit side effects; delivery failures belong in retry/DLQ flows and must not alter a finalized order transaction.

## 36. Interview Questions

### Does a saga provide ACID transactions across microservices?

No. Sagas achieve eventual consistency through a sequence of local transactions and compensating actions. The business must accept intermediate states and define procedures for failed compensations.

### Why is Step Functions orchestration well suited for an order saga?

The workflow involves multiple steps, error branches, and compensations. Step Functions Standard provides durable orchestration, retry/catch handling, and execution history for operations.

### Can EventBridge replace SQS?

EventBridge excels at pattern-based event routing and fan-out. SQS excels at buffering, consumer-controlled polling, and backpressure. Many architectures use both together.

### Does a transactional outbox guarantee events are published exactly once?

No. An outbox guarantees that the entity update and event record commit together. Publishers can still replay after crashes, so consumers must implement idempotency and deduplication.

### Why is idempotency needed at the API, saga participant, and event consumer layers?

Each boundary has its own retry sources. API clients, Step Functions, provider adapters, EventBridge, and SQS can all repeat requests or messages; idempotency must be enforced wherever side effects occur.

### What if payment has been captured but order confirmation fails?

Query the provider to confirm capture, then execute a refund per business policy or escalate to manual review. Never delete the order and assume payment rolled back.

### How do you prevent overselling when two orders buy the last remaining SKU?

Use conditional updates/transactions checking available quantity and version. Only one transaction can reserve successfully; the other receives a conflict or out-of-stock response.

### Why shouldn't all services share a single Lambda IAM role?

A broad role expands blast radius. Each service should read/write only the datastores and secrets it owns.

### When should you choose choreography over orchestration?

When there are few participants, simple event flows, and independent services reacting to events. When coordinating many steps, timeouts, branches, and explicit compensations, orchestration is easier to observe and reason about.

### How do you redrive a DLQ without creating duplicate shipments or refunds?

Fix the root cause, inspect current business state, reuse original idempotency keys, and rely on consumer deduplication. Redrive in small batches and reconcile outcomes.

### Why doesn't SQS FIFO eliminate the need for idempotency?

FIFO preserves ordering per `MessageGroupId` and offers a finite deduplication window. Consumers still need persistent idempotency because retries, visibility timeout expirations, redrives, or timeouts after side effects can reprocess the same business operation.

## 37. Capstone Handover Checklist

### Business and Architecture

- [ ] Order lifecycle and invariants are defined.
- [ ] Saga happy path and compensation path are diagrammed.
- [ ] Service boundaries and data ownership are clear.
- [ ] Domain events and commands are separated.
- [ ] API and event schemas are versioned.
- [ ] EventBridge `OrderCreated` trigger flows through an outbox, and Saga Starter enforces idempotency by `sagaId`.

### Reliability

- [ ] API idempotency works as designed.
- [ ] Participant operations are idempotent.
- [ ] Payment provider reconciliation is implemented.
- [ ] Inventory uses conditional writes.
- [ ] Outbox prevents dual-writes.
- [ ] Outbox sweeper recovers stale `PENDING` records.
- [ ] Event consumers deduplicate and verify aggregate versions.
- [ ] Retries use backoff, timeouts, and an error taxonomy.
- [ ] Compensation failures route to manual review.
- [ ] EventBridge and SQS DLQs have alarms and redrive runbooks.
- [ ] Visibility timeout, `maxReceiveCount`, and partial batch responses are configured properly.

### Security

- [ ] API authentication/authorization is enforced.
- [ ] IAM roles are separated per service.
- [ ] Secrets are stored in Secrets Manager.
- [ ] DynamoDB/SQS/log encryption is configured appropriately.
- [ ] Raw payment card data is never stored or logged.
- [ ] Event payloads are minimal and free of unnecessary PII.
- [ ] CloudTrail and audit records are configured.

### Operations and Delivery

- [ ] Correlation ID spans API, saga, events, and consumers.
- [ ] Dashboards track saga duration, failures, compensations, and queue age.
- [ ] Alerts exist for DLQs, payment failures, and stuck sagas.
- [ ] Unit, integration, and failure-injection tests pass.
- [ ] IaC, CI/CD, and versioned state machines are in place.
- [ ] Deployment, rollback, cleanup guides, and cost estimates exist.
- [ ] Demo proves happy path, duplicate requests, payment failure, and compensation failure.
- [ ] Dashboards cover `PaymentUnknown`, compensation failures, DynamoDB conflicts, and queue age.

## 38. Official References

### Sagas and Microservices

- [Saga orchestration pattern - AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/saga-orchestration.html)
- [Saga choreography pattern - AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/saga-choreography.html)
- [Saga patterns - AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/saga-patterns.html)
- [Choosing your coordination approach](https://docs.aws.amazon.com/prescriptive-guidance/latest/modernization-integrating-microservices/choosing-approach.html)
- [Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)

### Step Functions

- [Choosing workflow type](https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html)
- [Handling errors in Step Functions workflows](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html)
- [Redrive Step Functions executions](https://docs.aws.amazon.com/step-functions/latest/dg/redrive-executions.html)
- [Invoke Lambda with Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/connect-lambda.html)
- [Amazon States Language](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-amazon-states-language.html)

### EventBridge, SQS, and DynamoDB

- [EventBridge event buses](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-bus.html)
- [EventBridge retry policies](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-rule-retry-policy.html)
- [EventBridge dead-letter queues](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-rule-dlq.html)
- [Archive and replay EventBridge events](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-archive.html)
- [SQS dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [SQS FIFO delivery logic](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-understanding-logic.html)
- [DynamoDB transactions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transactions.html)
- [DynamoDB Streams](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Streams.html)

### Lambda Reliability and Security

- [Powertools for AWS Lambda Java - Idempotency](https://docs.aws.amazon.com/powertools/java/latest/utilities/idempotency/)
- [Lambda best practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [CloudWatch Logs for Lambda](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-cloudwatchlogs.html)
- [X-Ray with Lambda](https://docs.aws.amazon.com/lambda/latest/dg/services-xray.html)
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html)
- [AWS KMS best practices](https://docs.aws.amazon.com/kms/latest/developerguide/best-practices.html)
- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html)

