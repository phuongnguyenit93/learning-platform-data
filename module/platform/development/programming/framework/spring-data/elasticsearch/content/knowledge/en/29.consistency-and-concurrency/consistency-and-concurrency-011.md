# Coordinating Multiple Business Operations and Compensation Mechanisms

A business workflow in an application often involves more than writing a single Elasticsearch document. For example, placing an order may require creating an order, reserving inventory, capturing payment, updating transaction status, and projecting data into a search index. Each step can succeed or fail at a different time. If the third step fails after the first two steps completed, the application must know whether to continue, retry, or perform a compensating action.

Spring Data Elasticsearch provides repositories and `ElasticsearchOperations` for reading and writing documents, yet it does not turn a sequence of operations across multiple documents, indices, or systems into a single business transaction. Elasticsearch guarantees atomicity within the scope of an individual document operation, while the Bulk API can return independent success/failure outcomes per item. When coordinating multiple steps, the application must design consistency boundaries, workflow state, idempotency, retries, and compensation.

Key ideas:

- Identify which system is the authoritative source of truth.
- Break workflows into steps with explicit outcomes and states.
- Use local transactions for data belonging to the same transactional resource.
- Use an outbox to durably emit events from a database to Elasticsearch.
- Use a Saga when a business workflow spans multiple steps or services.
- Design compensating actions with business semantics rather than assuming everything can be rolled back.
- Make every step and every compensation safe to re-run.
- Use version/concurrency control so compensation does not overwrite newer changes.

## 1. How can a multi-step business workflow fail?

Suppose a customer places an order. The system needs to:

1. Create an order in a pending state.
2. Reserve item inventory.
3. Capture or confirm payment.
4. Transition the order to confirmed.
5. Update the Elasticsearch index so search and admin pages see the order.

Success flow:

~~~text
Create order
    |
    v
Reserve inventory
    |
    v
Capture payment
    |
    v
Confirm order
    |
    v
Publish event / update Elasticsearch
    |
    v
Workflow completed
~~~

However, what can happen instead:

- The order was created, yet the inventory service timed out.
- Inventory was reserved, yet payment was declined.
- Payment was captured, yet the database failed to update the order.
- The order was confirmed in the database, yet Elasticsearch is unavailable.
- Elasticsearch received the event, yet the publisher missed the acknowledgement and resent it.
- A step timed out on the client while the server actually completed it successfully.

Simply calling services sequentially and throwing an exception on failure can leave inconsistent partial states: money charged for an unconfirmed order, inventory locked for a cancelled order, or an updated database with a stale search index.

## 2. Understanding Elasticsearch's transaction boundaries

Before designing a workflow, know which operations can be considered atomic and which cannot.

### 2.1. Document-level atomicity

An index or update operation on a single document is processed by Elasticsearch as a document-scoped write. Readers never observe half of a document source being replaced.

This does not mean a sequence of multiple requests can be rolled back like a database transaction. For example:

~~~http
PUT /orders/_doc/100
PUT /customers/_doc/42
PUT /payments/_doc/pay-100
~~~

If the first and second requests succeed while the third fails, the two written documents remain. Elasticsearch does not automatically undo prior requests.

### 2.2. The Bulk API is not a transaction

The Bulk API reduces overhead when writing multiple documents, yet each item has its own outcome. A bulk response can contain both succeeded and failed items.

Example:

~~~text
Bulk request
  item 1 -> success
  item 2 -> version conflict
  item 3 -> success
  item 4 -> mapping error
~~~

The application must inspect each item's result, identify which items were applied, and handle errors individually. Never assume one failed item automatically rolls back the others.

### 2.3. No transactions across multiple systems

A business process can combine a relational database, Elasticsearch, a payment gateway, an inventory service, a message broker, and an email or notification service.

Standard `@Transactional` manages the transaction of a configured Spring transactional resource, such as a JPA transaction manager. It does not automatically combine Elasticsearch calls, HTTP requests to a payment gateway, and message publishing into a single shared ACID transaction.

Even with multiple transaction managers, do not assume they deliver distributed atomic commits. Coordinating independent systems requires an explicitly supported distributed protocol or an eventual consistency pattern such as Saga and Outbox.

### 2.4. Role of Spring Data Elasticsearch

`ElasticsearchRepository` and `ElasticsearchOperations` provide abstractions for document operations:

- `save` to write entities.
- `delete` to delete documents.
- `get` or `search` to read.
- Bulk operations to process multiple items.
- Version metadata to detect concurrent updates.

These abstractions do not manage the lifecycle of a business process spanning multiple systems. Workflow orchestration, retries, compensation, and progress persistence belong to the application layer or a workflow engine.

## 3. Choosing the source of truth before coordinating operations

A crucial design decision is determining where authoritative data lives.

In many systems, a relational database holds orders, payment state, and the inventory ledger, while Elasticsearch serves as a search read model. In that setup:

- The database is the authoritative source of business state.
- Elasticsearch is a projection rebuildable from events or the database.
- If the Elasticsearch index lags, business correctness remains intact.
- If documents in Elasticsearch become corrupt or lost, the projection can be rebuilt.

Suitable flow:

~~~text
Command / API
     |
     v
Business database transaction
     |
     +--> Update order state
     |
     +--> Insert outbox event
              |
              v
       Outbox publisher
              |
              v
        Event consumer
              |
              v
      Elasticsearch projection
~~~

Do not rely solely on Elasticsearch Search results to make financial or inventory decisions if the authoritative data source lives in another database. Search indices can lag due to refreshes, event delivery, or retries.

If an application uses Elasticsearch as its primary data store, it must still define explicit transaction boundaries. A single document can be updated atomically, whereas multi-document update sequences require stateful workflows and dedicated error handling.

## 4. Workflow coordination strategies

There are three common groups of approaches.

| Strategy | How it works | When suitable |
|---|---|---|
| Local transaction | Groups changes into one transaction of the same resource | Steps share the same database/resource manager |
| Saga orchestration | A coordinator directs each step and its compensation | Multi-step workflows needing centralized state |
| Saga choreography | Services emit and react to events to advance the process | Relatively independent services with clear event flows |

An outbox is commonly combined with local transactions and Sagas to guarantee durable event emission.

### 4.1. Local transaction

If creating an order and recording an outbox event occur in the same database, perform both in one `@Transactional` method:

~~~java
@Transactional
public Order createOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(
            Order.pending(command)
    );

    outboxRepository.save(
            OutboxEvent.orderCreated(order)
    );

    return order;
}
~~~

If inserting the outbox record fails, the transaction rolls back the order as well. If the commit succeeds, both the order and the event exist in the database. A publisher reads the outbox afterward and forwards the event to consumers.

This is a local database transaction. Elasticsearch is not updated inside that transaction; index updates occur asynchronously.

### 4.2. Saga orchestration

A coordinator drives steps in sequence. Each step defines its forward action, receipt or output to store, success/failure conditions, compensating action, and retry/timeout policy.

Example:

~~~text
Saga: PlaceOrder
    |
    v
Create pending order
    |
    v
Reserve inventory
    |
    v
Capture payment
    |
    v
Confirm order
    |
    v
Publish OrderConfirmed

If Capture payment fails:
    Release inventory
    Cancel pending order
~~~

The coordinator knows which step the workflow is currently at and can resume after a process restart. Do not keep state solely in local variables or an in-memory try/catch chain if the workflow must recover across crashes.

### 4.3. Saga choreography

In choreography, each service completes its own work and emits an event for the next service to react to:

~~~text
OrderCreated
    |
    v
Inventory service
    |
    +--> InventoryReserved
    |
    +--> InventoryReservationFailed

InventoryReserved
    |
    v
Payment service
    |
    +--> PaymentCaptured
    |
    +--> PaymentFailed
~~~

Choreography reduces dependence on a central coordinator, yet can make business flows harder to observe when many events and compensation branches exist. It requires correlation IDs, stable event schemas, idempotent consumers, and a place to track saga status.

Choose orchestration when a workflow has many sequential steps, timeouts, and complex compensation. Choose choreography when services react independently to events and the overall flow does not need fine-grained central control.

## 5. What is compensation?

Compensation is a new business action aimed at mitigating or reversing the effect of a previously completed step.

| Forward action | Compensation |
|---|---|
| Reserve inventory | Release reservation |
| Capture payment | Issue refund |
| Create pending order | Cancel pending order |
| Assign seat | Release seat hold |
| Generate shipment label | Void label if carrier allows |
| Send notification | Send correction notice; cannot unsend an email |

Compensation is not a physical rollback of the original transaction. It can fail and need retries, may not restore the exact prior state, creates additional events/audit records, or may be constrained by business policies and external systems. Some effects cannot be completely undone.

For example, a refund does not erase the original payment capture event; it creates a new refund transaction linked to the original transaction. Sending a correction email does not remove the first email from the recipient's inbox.

### 5.1. Compensation needs the output of the original step

Do not blindly call `releaseInventory(orderId)` without knowing which reservation was created. Store the receipt:

~~~java
public record InventoryReservation(
        String reservationId,
        String orderId,
        String sku,
        int quantity
) {
}
~~~

When compensating, pass the specific `reservationId`. Likewise, a refund requires the payment transaction ID and the actual captured amount. Compensation must target the exact effect produced by that saga.

### 5.2. Compensation is not always a mathematical inverse

If inventory was reserved, releasing the reservation is typically the right compensating action. Yet if goods have already been packed or handed to the carrier, releasing a reservation may be wrong; business logic may require a return, shipment cancellation, or exception handling.

Therefore, compensation must be designed around current state and domain rules, not merely by calling an opposite-sounding method.

## 6. Designing recoverable Saga state

A saga must persist its state durably. Example:

~~~java
public enum SagaStatus {
    STARTED,
    INVENTORY_RESERVED,
    PAYMENT_CAPTURED,
    ORDER_CONFIRMED,
    COMPENSATING,
    COMPENSATION_PENDING,
    COMPENSATED,
    FAILED
}
~~~

A saga record can contain:

~~~java
public class OrderSaga {
    private String sagaId;
    private String orderId;
    private SagaStatus status;
    private String inventoryReservationId;
    private String paymentTransactionId;
    private int retryCount;
    private Instant createdAt;
    private Instant updatedAt;
    private String lastError;
}
~~~

These fields are domain examples; names and structures should match your application. What matters is that the coordinator knows which saga is running, which steps finished, which receipts are needed for compensation, what the latest error was, which steps can retry, and which compensating steps remain pending.

If storing saga state in Elasticsearch, carefully weigh durability, concurrency, and recovery query requirements. For critical coordination state, a transactional database is often more convenient because state updates and outbox writes must happen atomically. Elasticsearch can serve as a read model for a saga dashboard.

## 7. Coordinator: separating forward actions and compensation

Each step can be modeled with an abstraction:

~~~java
public interface SagaStep<C, R> {

    R execute(C context);

    void compensate(C context, R result);
}
~~~

`context` holds the saga ID, order ID, idempotency key, and results from earlier steps. `result` holds the receipt needed for compensation.

Example service interfaces:

~~~java
public interface InventoryService {
    InventoryReservation reserve(
            String orderId,
            String sku,
            int quantity,
            String idempotencyKey
    );

    void release(
            String reservationId,
            String idempotencyKey
    );
}

public interface PaymentService {
    PaymentReceipt capture(
            String orderId,
            long amountMinorUnits,
            String currency,
            String idempotencyKey
    );

    void refund(
            String paymentTransactionId,
            String idempotencyKey
    );
}
~~~

A simple coordinator might express the sequence:

~~~java
public void placeOrder(OrderCommand command) {
    OrderSaga saga = sagaStore.start(command);
    InventoryReservation reservation = null;
    PaymentReceipt payment = null;

    try {
        reservation = inventoryService.reserve(
                command.orderId(),
                command.sku(),
                command.quantity(),
                saga.id() + ":reserve"
        );
        sagaStore.markInventoryReserved(saga.id(), reservation);

        payment = paymentService.capture(
                command.orderId(),
                command.amountMinorUnits(),
                command.currency(),
                saga.id() + ":capture"
        );
        sagaStore.markPaymentCaptured(saga.id(), payment);

        orderService.confirm(command.orderId());
        sagaStore.complete(saga.id());
    } catch (RuntimeException failure) {
        compensate(saga, reservation, payment, failure);
        throw failure;
    }
}
~~~

This is pseudocode to illustrate the flow. In production, do not keep an entire workflow solely on the call stack of a single request. Every step and receipt must be durably persisted before advancing to the next step; workers can then resume workflows after restarts. Also distinguish timeouts with unknown outcomes from errors guaranteed not to have executed.

## 8. Executing compensation in reverse order

If the workflow reserved inventory and then captured payment, cancelling typically requires refunding payment first and releasing inventory second:

~~~java
private void compensate(
        OrderSaga saga,
        InventoryReservation reservation,
        PaymentReceipt payment,
        RuntimeException cause
) {
    sagaStore.markCompensating(saga.id(), cause);

    if (payment != null) {
        try {
            paymentService.refund(
                    payment.transactionId(),
                    saga.id() + ":refund"
            );
            sagaStore.markPaymentRefunded(saga.id());
        } catch (RuntimeException refundFailure) {
            sagaStore.markCompensationPending(
                    saga.id(),
                    "PAYMENT_REFUND",
                    refundFailure.getMessage()
            );
            return;
        }
    }

    if (reservation != null) {
        try {
            inventoryService.release(
                    reservation.reservationId(),
                    saga.id() + ":release"
            );
            sagaStore.markInventoryReleased(saga.id());
        } catch (RuntimeException releaseFailure) {
            sagaStore.markCompensationPending(
                    saga.id(),
                    "INVENTORY_RELEASE",
                    releaseFailure.getMessage()
            );
            return;
        }
    }

    orderService.cancelPending(saga.orderId());
    sagaStore.markCompensated(saga.id());
}
~~~

This code illustrates the structure. A durable coordinator must store each individual compensation status so it retries only the failed step rather than blindly restarting compensation from scratch. If refunding fails, never mark the saga as compensated. You may need to keep retrying the refund before releasing inventory or apply another business rule.

Compensation order usually runs in reverse of the forward order, though it is not always a mechanical reversal. Ordering must follow dependencies and business safety.

## 9. Timeout does not mean the operation failed

This is one of the most dangerous pitfalls when coordinating multiple systems.

Example:

1. The application sends a payment capture request.
2. The payment gateway captures the payment successfully.
3. The response is lost or arrives late.
4. The application times out and assumes payment failed.
5. The saga runs compensation or retries.

If retrying capture without an idempotency key, the customer can be charged twice. If compensating with a refund without knowing whether capture succeeded, you could issue an invalid refund or create reconciliation discrepancies.

For timeouts with unknown outcomes:

- Query transaction status by idempotency key or transaction reference.
- Retry with the same idempotency key if the external API supports it.
- Persist an `UNKNOWN`/`PENDING_CONFIRMATION` state instead of immediately concluding failure.
- Run compensation only after confirming the forward action actually took effect.

## 10. Idempotency for forward actions and compensation

An idempotent step can be called multiple times without duplicating its business effect.

Every action should have a stable key derived from the saga and step:

~~~text
saga-8f2:reserve
saga-8f2:capture
saga-8f2:refund
saga-8f2:release
~~~

The target service must store the key and its processed outcome. When receiving the same key again, it returns the prior result or confirms completion instead of applying the side effect again.

Idempotency must cover inventory reservation, payment capture, refunds, reservation releases, event publishing/consumption, and Elasticsearch projection writes.

Do not assume an operation is idempotent merely because its HTTP method is PUT or DELETE. For example, a script incrementing a counter every time it runs is not idempotent if the request is resent.

## 11. Writing Elasticsearch as a projection using an Outbox

Suppose the order database is the authoritative source of truth and Elasticsearch powers search. When an order is confirmed, update the order and create an event in the same database transaction:

~~~java
@Transactional
public void confirmOrder(String orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();
    orderRepository.save(order);

    outboxRepository.save(
            OutboxEvent.of(
                    "OrderConfirmed",
                    order.getId(),
                    order.getVersion(),
                    serialize(order)
            )
    );
}
~~~

After the transaction commits, a publisher reads the outbox and sends the event to a broker or consumer. The consumer updates Elasticsearch:

~~~java
public void onOrderConfirmed(OrderConfirmed event) {
    OrderDocument document = OrderDocument.from(event);
    elasticsearchOperations.save(document);
}
~~~

This example is a skeleton; add acknowledgements, retries, event schemas, deduplication, and version/ordering checks. The crucial benefit is that the order update and outbox insert share the same database transaction. If the process dies after commit but before publishing, the event remains in the outbox for the publisher to resend.

### 11.1. Why not rely solely on `@TransactionalEventListener`?

`@TransactionalEventListener(phase = AFTER_COMMIT)` runs after a transaction commits, which is useful for internal tasks that do not require durable delivery. However, if the process crashes after commit and before the listener finishes, the in-memory event can be lost.

An outbox closes that gap by writing the event into the database within the same transaction as the business data. Publishers can resume after restarts.

### 11.2. At-least-once delivery and idempotent consumers

Outbox publishers can resend an event if they do not receive an acknowledgement. Therefore, consumers must assume events can arrive multiple times.

A consumer can store processed `eventId` values in an inbox/deduplication table. If the event was already applied, skip the duplicate. For Elasticsearch projections, use a stable document ID and event version to avoid creating duplicate documents or applying an older event after a newer one.

## 12. Writing Elasticsearch projections in order and with versions

One risk of event delivery is that events can arrive out of order:

~~~text
OrderUpdated version 12
OrderUpdated version 11
~~~

If a consumer applies version 11 after version 12 via a replacement write, the projection can regress to an older state.

Safeguards:

- Include the aggregate version in every event.
- Ignore events whose version is not newer than the already-applied version.
- Use optimistic concurrency or external versioning supported by the API.
- Have consumers serialize events per aggregate key if the broker supports partition ordering.

With Spring Data Elasticsearch, entities can declare `@Version` for optimistic locking on supported save/update operations. When a version conflict occurs, reload the latest state and decide whether to apply or skip the event.

When using the low-level Elasticsearch client, use `if_seq_no` and `if_primary_term` to guard operations based on the document version read. Do not fabricate or increment sequence numbers yourself; extract values from responses/get results per your API.

### 12.1. Writing projections using absolute state

For read models, it is usually safer for events to carry the complete new state or sufficient data to build the projection:

~~~java
OrderDocument document = new OrderDocument(
        event.orderId(),
        event.aggregateVersion(),
        event.status(),
        event.totalAmount(),
        event.customerName()
);

elasticsearchOperations.save(document);
~~~

Writing absolute state keyed by version handles duplicates much more cleanly than a script like "increment quantity by 1" or "add money." If events only carry deltas, consumers need strict sequence/version checks and reliable deduplication so the same delta is never applied twice.

## 13. Compensation for multi-document Elasticsearch operations

If a workflow genuinely needs to modify multiple Elasticsearch documents, do not treat the Bulk API as a transaction. Persist the item list and individual statuses:

~~~text
Operation group G-100
  doc A -> APPLIED
  doc B -> FAILED
  doc C -> APPLIED
  doc D -> NOT_ATTEMPTED
~~~

If business logic requires compensation, compensate only the items that were successfully applied and remain eligible. Do not run compensation for failed or unsent items.

### 13.1. Storing before-images or business receipts

To restore a document, the application may need to store:

- Document ID.
- Pre-change state (before-image) or sufficient info to build the compensating action.
- Before/after versions.
- Saga ID and operation ID.
- Operation status.

You do not always need to save the entire source document. If documents are large, store a minimal business receipt or an event representing the change.

### 13.2. Do not restore before-images blindly

Suppose workflow A changes order status from PENDING to PROCESSING. Meanwhile, workflow B updates the shipping address. If workflow A fails and restores the entire before-image, workflow B's address change can be lost.

Compensation should update only the fields owned by that workflow and use version/concurrency conditions to verify the document was not modified by another actor. If the version changed, reload and make a business decision rather than overwriting the entire source.

## 14. Bulk responses: process only genuinely succeeded items

When using the Elasticsearch Java Client, the Bulk API returns an item response for each operation. Iterate through every item to classify outcomes:

~~~java
BulkResponse response = elasticsearchClient.bulk(request);

for (BulkResponseItem item : response.items()) {
    if (item.error() == null) {
        operationStore.markApplied(item.id());
    } else if (isRetryable(item.status(), item.error())) {
        operationStore.markRetryable(
                item.id(),
                item.error().reason()
        );
    } else {
        operationStore.markFailed(
                item.id(),
                item.error().reason()
        );
    }
}
~~~

Type names and getters may vary by Elasticsearch Java Client version. The principle to keep is checking per-item errors rather than looking only at the overall `errors` flag.

Error classification:

- Mapping/validation errors generally require fixing the data or mapping; retrying unchanged usually fails again.
- Version conflicts may require reloading and applying business logic.
- Rejected executions or transient errors can retry with backoff.
- Timeouts may leave uncertainty about whether an item applied; verify state or use idempotent operations.

## 15. Optimistic concurrency during compensation

Compensation is also a write operation and can collide with concurrent updates. Never assume a saga has the right to overwrite newer changes simply because it is rolling back.

For example, a document was at version 7 when the saga updated it. Another user updated it to version 8. Later, the saga attempts to compensate:

~~~text
Saga write: version 7 -> 8
Other writer: version 8 -> 9
Saga compensation attempts based on version 8
       |
       v
Version conflict
~~~

The conflict indicates state changed since the saga executed the original step. The coordinator must:

1. Read the current document.
2. Check whether the fields the saga modified still hold the values the saga set.
3. Determine whether those fields can be reverted without clobbering other changes.
4. Write the compensation with the new concurrency condition if business rules permit.
5. If unsafe, transition to a manual intervention or forward-recovery state.

Do not retry indefinitely with the same stale payload/version. On version conflicts, retries must be based on the latest state and a fresh business decision.

## 16. Retries, backoff, and error classification

Not every error requires immediate compensation. First distinguish transient errors, permanent errors, and ambiguous outcomes.

| Outcome type | Typical action |
|---|---|
| Success | Save receipt and advance to next step |
| Validation/mapping error | Stop forward flow, fix data or start compensation if earlier steps had effects |
| Version conflict | Reload, re-evaluate, and decide on retry |
| Throttling/rejected execution | Retry with backoff and limits |
| Network timeout | Verify outcome via operation ID before retrying/compensating |
| Service unavailable | Bounded retry, then mark pending or compensate |
| Compensation failed | Persist compensation-pending state and retry separately |

Backoff can use exponential delay with jitter to prevent workers from retrying simultaneously. Define maximum attempt caps, overall time budgets, and dead-letter/manual intervention mechanisms.

Do not hold a synchronous HTTP request open for minutes waiting for an entire Saga to finish. You can return a `PENDING` status with an operation ID and let the client poll status or receive a callback/event when the workflow completes.

## 17. Workflow state and operational observability

Workflows must be observable via logs and metrics. Each log/trace should include `sagaId`, `operationId`, `orderId` or business key, `stepName`, `attempt`, `outcome`, `compensationStatus`, and `correlationId`/trace ID.

Metrics should use low-cardinality tags such as step name, outcome, and workflow type. Do not use order IDs, customer IDs, or saga IDs as metric tags, as that creates unbounded time series.

Dashboards should display:

- Active sagas count.
- Sagas pending longer than a threshold.
- Pending compensations count.
- Retry rate by step.
- Unpublished outbox events count.
- Lag from database commit to Elasticsearch projection.
- Version conflicts and bulk item failures.

A workflow in `COMPENSATION_PENDING` is not finished. Ensure alerting and operational runbooks exist to handle it.

## 18. When Elasticsearch updates slowly, should payment be compensated?

If Elasticsearch is purely a read model, the answer is usually no. Once an order is confirmed in the database and the outbox event is committed, slow indexing is a projection synchronization issue, not a reason to refund the customer or release inventory.

The flow should be:

1. Database transaction confirms the order and writes the outbox event.
2. Publisher sends the event.
3. Consumer attempts to write to Elasticsearch.
4. On transient failure, retry.
5. On mapping or bad-data errors, route the event to a dead-letter/repair flow.
6. Once fixed, replay the event or rebuild the projection.

Payment/inventory compensation should only trigger when the Saga's business rules require cancelling the order, such as declined payment or failed reservation. Never tie financial compensation to technical errors in a read model.

## 19. Testing Sagas and compensation

A multi-step workflow needs tests for both happy paths and failure injection.

### 19.1. Happy path

Verify the order is created, inventory reservation is created, payment is captured exactly once, the order transitions to confirmed, the outbox event is created, the Elasticsearch projection updates, and the saga ends in completed state.

### 19.2. Payment fails after reserving inventory

Simulate successful inventory reservation followed by declined payment:

- The reservation is released exactly once.
- The order is cancelled according to business rules.
- No successful payment capture occurs.
- The saga persists compensated state.

### 19.3. Compensation fails

Simulate a failed refund or release:

- The saga is not marked completed/compensated.
- The failed compensation step is recorded individually.
- Retries run only the pending step.
- The idempotency key stays identical across retries.
- Alerts or operational tooling detect the stuck saga.

### 19.4. Timeout with unknown outcome

Simulate a service succeeding while the client times out:

- The coordinator does not immediately assume the action never happened.
- Queries by idempotency key/operation reference.
- Retrying with the same key creates no duplicate effects.
- Compensation runs only after confirming the forward action took effect.

### 19.5. Elasticsearch unavailable

If the database and outbox committed while Elasticsearch is down:

- The order retains its valid business status in the database.
- The outbox event persists.
- Publisher/consumer retries once Elasticsearch recovers.
- Never refund or cancel the order just because the projection has not updated yet.

### 19.6. Version conflict during compensation

Simulate another writer updating the document after the forward action:

- Compensation uses concurrency control and receives a conflict.
- Newer data is not overwritten.
- The coordinator reloads and evaluates the fields needing compensation.
- If unsafe to compensate automatically, transition to manual/forward recovery.

## 20. Checklist for designing multi-operation coordination

- [ ] Identify the source of truth for each aggregate.
- [ ] Identify which operations share the same local transaction.
- [ ] Do not assume `@Transactional` covers Elasticsearch and HTTP services.
- [ ] Do not treat the Bulk API as an all-or-nothing transaction.
- [ ] Split workflows into steps with explicit state and receipts.
- [ ] Choose Saga orchestration or choreography.
- [ ] Define compensation with business semantics.
- [ ] Persist saga state durably to recover after restarts.
- [ ] Use stable idempotency keys for both forward and compensating actions.
- [ ] Distinguish guaranteed failures from timeouts with unknown outcomes.
- [ ] Use an Outbox for events requiring durable emission after database commit.
- [ ] Make consumers idempotent and handle duplicate/out-of-order events.
- [ ] Use version/concurrency control when updating or compensating documents.
- [ ] Inspect per-item outcomes in Bulk responses.
- [ ] Monitor pending compensations, retries, and outbox backlogs.
- [ ] Test failure injection, retries, timeouts, duplicate events, and version conflicts.

## 21. Conclusion

Coordinating multiple business operations requires an explicit stateful workflow. Elasticsearch provides document operations and the Bulk API, yet does not provide a shared ACID transaction across multiple documents or systems. Spring's `@Transactional` manages only the configured transactional resource; it does not automatically roll back payment, inventory, or Elasticsearch when another step fails.

When business data lives in a database and Elasticsearch is a read model, write business changes and outbox events inside a single local transaction, then update the index via idempotent consumers. When business workflows span multiple services, use Saga orchestration or choreography to track each step, persist receipts, and execute compensation when needed.

Compensation is a new business action that can fail and require retries. It must be idempotent, target the exact saga effects, and respect optimistic concurrency so it never overwrites newer changes. When timeouts leave ambiguous outcomes, verify status via operation IDs/idempotency keys before retrying or compensating. A well-designed workflow can resume, compensate, or escalate to manual handling without losing track of business state.
