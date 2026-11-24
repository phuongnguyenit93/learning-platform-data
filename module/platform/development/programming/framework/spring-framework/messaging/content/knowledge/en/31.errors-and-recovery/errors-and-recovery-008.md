# Designing Handling When Part of an Exchange Succeeds

## Objectives

In messaging systems, an operation may comprise multiple steps or multiple data items. Some steps may succeed before the next step fails, the client disconnects, or a timeout expires. This lesson presents how to design request/response contracts, persist partial results, perform safe retries, and recover state in Spring RSocket.

After this lesson, you will be able to:

- Distinguish whole-request errors from partially successful business outcomes.
- Choose Request-Response, Request-Stream, or Channel based on confirmation requirements.
- Design per-item results, operation IDs, and idempotency keys.
- Choose transaction boundaries suited to all-or-nothing or partial success policies.
- Recover after timeouts, connection loss, cancellations, and mid-stream errors.
- Use Reactor and Spring RSocket to return re-checkable partial results.

Examples use Java 17+, Spring Boot 3.x, Spring Messaging, and RSocket. Repository interfaces in the examples represent contracts to be implemented using JDBC, JPA, or R2DBC depending on the application.

## 1. Why Do Partial Success States Occur?

Suppose a client sends a command to reserve 100 products. The server processes them one by one:

1. Checks product A and reserves it successfully.
2. Checks product B and reserves it successfully.
3. Product C is out of stock.
4. While processing product D, the connection drops.

At the moment the connection drops, the first two operations may already have committed to the database. The client may only observe a timeout or transport error. It cannot conclude that the entire batch went unprocessed.

Similar situations occur when:

- One request calls multiple services or multiple data stores.
- A server emits a stream of results, sends several payloads, and then encounters an error.
- The server committed business changes, yet the response was lost on the network.
- The client cancels the subscription or times out while the server is still processing.
- A multi-step workflow has steps that can succeed or fail independently.

Separate three concepts:

- **Business outcome:** a data item was accepted, rejected, or failed processing.
- **Transport outcome:** the client received a payload, an error, or a stream completion signal.
- **Durable state:** the outcome has been persisted in a reliable store and can be queried after connection loss.

A payload produced by the server is not guaranteed to have been received by the client. A lost response likewise does not prove business work did not commit. Good design enables querying durable state when the connection no longer provides enough information.

## 2. Understanding the Semantics of Each RSocket Interaction Model

RSocket has four primary interaction models. Your choice of request model directly shapes how partial success is represented.

| Interaction model | Result semantics | When appropriate |
|---|---|---|
| Request-Response | One request receives one response payload or an error. | An operation with an aggregated outcome, even when individual items have different statuses. |
| Request-Stream | One request produces multiple response payloads. | Server emits multiple results or events over time. |
| Channel | Both sides exchange payload streams in both directions. | Client sends multiple items and server returns corresponding confirmations while the exchange continues. |
| Fire-and-Forget | Client receives no business response payload. | Use only when per-item confirmation via that request is unnecessary and a separate tracking mechanism exists. |

### 2.1. Request-Response Does Not Automatically Give Per-Item Results

Request-Response returns only a single payload. That payload can be an aggregate DTO containing outcomes for multiple items:

- Item A: succeeded.
- Item B: succeeded.
- Item C: rejected due to out of stock.
- Item D: not yet processed.

This is a valid response if the server finished the work it could decide. Expected business errors for individual items should be represented inside the DTO. System errors preventing the server from constructing an aggregate result can terminate the request with an error.

An important point: if the server commits A and B and then hits an infrastructure failure before building the response, the client receives an error yet A and B may still have succeeded. Therefore, for batches with side effects, persist state by operation ID so the client can query back.

### 2.2. Streams Can Emit Results and Then Error

Request-Stream and Channel can emit multiple payloads. For example, the server sends confirmations for A, B, and C, and then the stream terminates with an error.

A client that received A, B, and C can keep those results. Items whose confirmations were not received remain in an unknown state until queried from the server. Never infer that items lacking a payload were definitely not processed.

Each payload should carry stable identifiers such as operation ID, item ID, and sequence number. That lets the client match outcomes back to the original request and spot missing items.

### 2.3. Fire-and-Forget Is Unsuitable When Confirmation Is Needed

Fire-and-Forget provides no response payload for business confirmation. It is not the right choice for operations where the client must know accurately whether each item succeeded.

If asynchronous command submission is still required, return an operation ID via another request or provide a status-query endpoint, event stream, or notification channel. The client must know how to obtain the final outcome.

### 2.4. Resume Does Not Replace Business Confirmation

Session resumption can recover a session and its streams within protocol bounds, provided both sides support it and configurations match. It does not create cross-database transactions, does not persist business outcomes automatically, and does not guarantee side effects happen only once.

Therefore, even when using resume, applications still need operation IDs, idempotency keys, state persistence, and result lookup mechanisms. Reconnect or resume solves connectivity; idempotency and transactions solve business correctness.

## 3. Designing an Explicit Result Contract

Before writing the handler, identify which unit can succeed independently. For a batch, the result should include both overall state and per-item state.

A minimal contract:

~~~json
{
  "operationId": "op-2026-00042",
  "state": "PARTIAL_SUCCESS",
  "items": [
    {
      "itemId": "line-1",
      "status": "SUCCEEDED",
      "message": "Reserved"
    },
    {
      "itemId": "line-2",
      "status": "REJECTED",
      "message": "Insufficient stock"
    },
    {
      "itemId": "line-3",
      "status": "RETRYABLE_FAILURE",
      "message": "Inventory service unavailable"
    }
  ]
}
~~~

Recommended fields:

- **operationId:** unique identifier for the whole command, kept constant across queries and retries.
- **itemId:** stable identifier for an item within the operation.
- **idempotencyKey:** key identifying the business operation for that item.
- **status:** status defined in the API contract.
- **message/code:** human-displayable or machine-processable reason; avoid putting stack traces or secret data in responses.
- **sequence/version:** sequence number or version if results are streamed and may update.
- **updatedAt:** timestamp when status was recorded if the client displays progress.

Statuses can be standardized:

| Status | Meaning | Auto-retry? |
|---|---|---|
| SUCCEEDED | Business logic committed successfully. | No. |
| REJECTED | Business logic rejected per rules, e.g., insufficient stock or invalid data. | No, unless input data or business conditions intentionally change. |
| RETRYABLE_FAILURE | Incomplete due to a transient error and can be tried again. | Yes, after checking idempotency and retry limits. |
| PROCESSING | Server received and is currently processing. | Do not submit a new operation; query status or wait. |
| UNKNOWN | Final outcome cannot be determined yet. | Look up before retrying. |

Overall state can be COMPLETED, PARTIAL_SUCCESS, FAILED, or PROCESSING. Define the calculation rule in the API. For example, PARTIAL_SUCCESS means at least one item SUCCEEDED and at least one item did not; FAILED may mean no item succeeded. If the system must distinguish business rejections from technical failures, keep them in per-item status instead of collapsing into a boolean.

Do not use a single boolean `success` field for the whole batch if it hides per-item outcomes. Clients need to know exactly which parts completed to avoid duplicate processing.

## 4. Choosing Transaction Boundaries

The most important decision is whether items in a batch must succeed together or not.

### 4.1. All-or-Nothing

Use a single transaction when business rules require all changes to commit together or roll back together, such as transferring funds between two accounts in the same database.

Flow:

1. Validate all inputs.
2. Open transaction.
3. Apply all mutations.
4. Persist operation result.
5. Commit if everything succeeds.
6. Roll back if any required step fails.

Send the response only after the transaction commits. If the client loses the response after commit, the client still needs an idempotency key or operation status to know the outcome was recorded.

Do not hold a database transaction open while waiting on network calls or calling multiple remote services. Long transactions hold locks and increase contention risk.

### 4.2. Partial Success

Allow individual items to commit independently when business rules accept some items succeeding while others fail.

For example: importing 100 records, each acceptable independently. Each item can be processed in its own transaction:

1. Read or create the idempotency record for the item.
2. If a final outcome already exists, return the stored result.
3. If not, execute the side effect.
4. Persist the item outcome and business changes in the same transaction.
5. Commit.
6. Move to the next item.

If item 50 hits an infrastructure error, outcomes 1–49 remain saved. The client queries the operation to discover completed items and continues with the incomplete ones.

### 4.3. Multiple Services or Multiple Systems

An ACID transaction usually cannot span multiple independent services. When a workflow involves multiple steps such as reserving inventory, charging payment, and creating a shipment, consider a Saga:

- Each step executes a local transaction.
- Record the state and outcome of each step.
- If a later step fails, run business-appropriate compensating actions.
- Persist the status of compensating actions too; compensations can also fail and require retries.
- Allow querying the operation to see whether the workflow is running, completed, partially completed, or needs intervention.

Compensation is not time-travel rollback. For example, a refund is a new business operation that may incur fees or require processing time. Design explicit states rather than assuming every side effect is cleanly reversible.

## 5. Idempotency: The Foundation of Safe Retries

A request may be processed successfully by the server while the response is lost. If the client resends, the server must recognize it as the same operation.

**Idempotency** means sending the same command with the same identifying key multiple times does not repeat side effects. It does not mean every call must return the exact same wire frame; it means business state is not duplicated and the server can return the stored result.

### 5.1. Generating Stable Keys

Use an operation ID for the batch and an idempotency key for each item. Never generate new keys on every retry.

Example:

- operationId: order-8451-reservation
- itemId: line-01
- idempotencyKey: order-8451-line-01-reserve-v1

If the same key is submitted with a different payload, the server should reject it as a conflict rather than treating it as a valid retry. Storing a hash of a canonicalized payload helps detect this case.

### 5.2. Persisting Keys and Side Effects Atomically

A common design uses an idempotency table:

| Column | Purpose |
|---|---|
| idempotency_key | Unique key for the operation. |
| operation_id | Groups items within the same workflow. |
| request_hash | Detects same key with a different payload. |
| status | PROCESSING, SUCCEEDED, REJECTED, or RETRYABLE_FAILURE. |
| result_payload | Result that can be returned back to the client. |
| updated_at | Update timestamp to detect stalled tasks. |

Update the side effect and the idempotency outcome inside the same database transaction. If the key is saved only after the side effect commits, the server can crash between the two steps and execute twice on retry.

A unique constraint or locking mechanism is needed so two concurrent requests using the same key do not both perform the side effect. If the second request encounters a PROCESSING record, it can wait briefly within bounds or return PROCESSING so the client queries again.

Across multiple services, use inbox/outbox or equivalent deduplication at each service boundary. Never assume a key in service A's database automatically protects side effects in service B.

## 6. Building a Spring RSocket Handler for Batches

The example below uses Request-Response to return an aggregate outcome. Each item is processed idempotently and has its own result.

### 6.1. DTOs

~~~java
package com.example.messaging;

import java.util.List;

public record ItemCommand(
    String itemId,
    String idempotencyKey,
    String sku,
    int quantity
) {}

public record ChannelItemCommand(
    String operationId,
    ItemCommand item
) {}

public record BatchCommand(
    String operationId,
    List<ItemCommand> items
) {}

public enum ItemStatus {
    SUCCEEDED,
    REJECTED,
    RETRYABLE_FAILURE
}

public record ItemOutcome(
    String itemId,
    ItemStatus status,
    String code,
    String message
) {}

public record BatchResult(
    String operationId,
    String state,
    List<ItemOutcome> items
) {}

public record OperationStatusQuery(String operationId) {}

public record BatchStatus(
    String operationId,
    String state,
    List<ItemOutcome> items
) {}
~~~

In production, validate operationId, itemId, idempotencyKey, SKU, and quantity before performing side effects. Cap batch size so a single request cannot consume excessive memory or processing time.

### 6.2. Service Contract

~~~java
package com.example.messaging;

import reactor.core.publisher.Mono;

public interface BatchReservationService {

    Mono<BatchResult> reserve(BatchCommand command);

    Mono<BatchStatus> findStatus(String operationId);
}
~~~

The reserve contract must ensure each item's outcome is durably persisted alongside its corresponding side effect. findStatus reads persisted state by operation ID. This part must be implemented with transactions and an idempotency store; holding results only in controller memory is insufficient to recover after a process restart.

### 6.3. RSocket Controller

~~~java
package com.example.messaging;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class BatchReservationController {

    private final BatchReservationService service;

    public BatchReservationController(BatchReservationService service) {
        this.service = service;
    }

    @MessageMapping("inventory.reserve-batch")
    public Mono<BatchResult> reserve(
        @Payload BatchCommand command
    ) {
        return service.reserve(command);
    }

    @MessageMapping("inventory.operation-status")
    public Mono<BatchStatus> status(
        @Payload OperationStatusQuery query
    ) {
        return service.findStatus(query.operationId());
    }
}
~~~

The client invokes Request-Response via RSocketRequester:

~~~java
Mono<BatchResult> result = requester
    .route("inventory.reserve-batch")
    .data(command)
    .retrieveMono(BatchResult.class);
~~~

When the request returns normally, the client receives the aggregate outcome. If the request times out or hits a transport error, the client uses the previously generated operation ID to query status:

~~~java
Mono<BatchStatus> status = requester
    .route("inventory.operation-status")
    .data(new OperationStatusQuery(command.operationId()))
    .retrieveMono(BatchStatus.class);
~~~

If status is still PROCESSING, the client can wait and poll again with backoff. If status shows some items remain incomplete, the client resends only items eligible under the retry policy while keeping the same idempotency keys. Never create a new operation ID for the exact same operation being recovered.

## 7. Orchestrating Multiple Items with Reactor

A batch can be processed sequentially or concurrently. Choose the operator based on business dependencies and resource limits.

### 7.1. Sequential Processing with concatMap

~~~java
return Flux.fromIterable(command.items())
    .concatMap(item ->
        itemService.processIdempotently(
            command.operationId(),
            item
        )
    )
    .collectList()
    .map(outcomes -> new BatchResult(
        command.operationId(),
        summarize(outcomes),
        outcomes
    ));
~~~

concatMap waits for the current item's publisher to finish before starting the next item. It preserves result order and fits when items depend on each other or load must be serialized. If an item publisher emits an unhandled technical error, the chain fails and stops processing subsequent items.

### 7.2. Bounded Concurrent Processing with flatMap

~~~java
return Flux.fromIterable(command.items())
    .flatMap(
        item -> itemService.processIdempotently(
            command.operationId(),
            item
        ),
        8
    )
    .collectList()
    .map(outcomes -> new BatchResult(
        command.operationId(),
        summarize(outcomes),
        outcomes
    ));
~~~

The argument 8 limits how many inner publishers are processed concurrently. flatMap can emit results out of input order. If you need to preserve ordering while still processing concurrently, consider flatMapSequential, understanding that it may buffer early-completed items while waiting on an earlier item.

Do not set concurrency too high. It can exhaust connection pools, overload downstream services, or increase transaction contention.

### 7.3. Convert Only Expected Business Errors into Per-Item Outcomes

A known business error can be mapped into an ItemOutcome so the batch continues. Error handling must stay scoped inside each item:

~~~java
return itemService.reserve(item)
    .thenReturn(new ItemOutcome(
        item.itemId(),
        ItemStatus.SUCCEEDED,
        "RESERVED",
        "Reservation committed"
    ))
    .onErrorResume(
        InsufficientStockException.class,
        error -> Mono.just(new ItemOutcome(
            item.itemId(),
            ItemStatus.REJECTED,
            "INSUFFICIENT_STOCK",
            "Not enough stock"
        ))
    );
~~~

This is an illustrative pattern. In real systems, the REJECTED outcome also needs to be durably persisted by idempotency key if clients may retry or query later. Database connection errors, downstream timeouts, or programming bugs must not be turned into REJECTED. Those errors should be classified as technical failures, logged, and handled per recovery policy.

Never place an onErrorResume around the entire batch to turn every error into an empty list or a fake success response. That hides committed items and robs the client of accurate recovery.

## 8. Using Channel When Per-Item Confirmation Is Needed

If a client sends a stream of commands and wants per-item outcomes while the server is still processing, Request-Channel is a natural fit.

A Spring handler can accept a Flux of commands and return a Flux of outcomes:

~~~java
@MessageMapping("inventory.reserve-channel")
public Flux<ItemOutcome> reserveChannel(
    @Payload Flux<ChannelItemCommand> commands
) {
    return commands.concatMap(command ->
        itemService.processIdempotently(
            command.operationId(),
            command.item()
        )
    );
}
~~~

In this example, each ChannelItemCommand carries the batch's operationId and an ItemCommand with itemId and idempotencyKey. The server emits ItemOutcome only after durably persisting the corresponding result. Each outcome acts as an application-level confirmation.

If the channel terminates with an error after emitting several outcomes:

1. The client retains the received outcomes and reconciles them by itemId.
2. The client queries operation status for durable outcomes of remaining items.
3. The client resends only incomplete items or items with retryable status.
4. The client keeps the exact same idempotency keys for the same business operations.

Never treat writing a payload to the socket as business confirmation. The confirmation point should be the committed and persisted result in the system.

With a bidirectional channel, specify clearly whether the client may send additional commands while the server is processing, cap the number of in-flight commands, and define cancellation and stream-completion rules. Backpressure helps regulate rate, yet does not replace batch limits, memory bounds, or result-persistence policies.

## 9. Retry and Error Recovery

Retry is a business decision, not just a Reactor operator.

### 9.1. Classifying Errors Before Retrying

| Error group | Example | Action |
|---|---|---|
| Validation | Missing itemId, negative quantity. | Reject; require input fix. |
| Business rejection | Out of stock, insufficient limit. | Record REJECTED; do not auto-retry. |
| Transient infrastructure | Database temporarily unavailable, gateway timeout. | Query status then perform bounded retry if safe. |
| Permanent infrastructure/configuration | Invalid credentials, nonexistent route. | Stop auto-retry; fix config or escalate to operations. |
| Unknown outcome | Timeout after server may have committed. | Query operation first; do not submit a new command with a new key. |

### 9.2. Recovery Workflow

When the client experiences a timeout or disconnect:

1. Retain the original operation ID and idempotency keys already sent.
2. Reconnect per transport policy.
3. Call the operation-status query route.
4. Read the persisted status of each item.
5. Keep SUCCEEDED and REJECTED items untouched.
6. Retry RETRYABLE_FAILURE or missing items only after verifying they have not been processed.
7. Use bounded backoff, jitter, and an appropriate deadline.
8. If status remains PROCESSING for too long, escalate to reconciliation or operational alerting.

Do not retry the entire batch by creating a brand-new operation. If the server partially committed, operations can be duplicated.

### 9.3. Retrying with Reactor

Example retrying a request only on transient errors:

~~~java
return requester
    .route("inventory.operation-status")
    .data(query)
    .retrieveMono(BatchStatus.class)
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(300))
            .maxBackoff(Duration.ofSeconds(5))
            .filter(this::isTransientTransportError)
    );
~~~

Import reactor.util.retry.Retry and java.time.Duration. isTransientTransportError is application-defined error-classification logic. This example illustrates retrying a status read; retrying a write command requires idempotency and must follow the same principles.

Use retry limits, backoff, jitter, and deadlines. Avoid continuous retries when the server is overloaded, as that can worsen the outage. Do not retry validation or business rejection errors.

## 10. Cancellation, Timeouts, and Shutdown

A client canceling a subscription does not mean the server rolled back. Depending on timing and implementation, the server may have committed one or more side effects before receiving the cancellation signal.

For short tasks, cancellation can be wired to stop steps that have not started yet. However, committed side effects must retain their outcomes. For long-running tasks, decouple the operation from the connection lifecycle:

- Client sends a create-operation command.
- Server persists the operation and returns an operation ID.
- Workers process independently of the connection.
- Client tracks progress via status requests, Request-Stream, or notifications.
- Client can disconnect and query again later.

Set timeouts for individual steps and the entire workflow. When a timeout occurs, update to an appropriate status such as UNKNOWN or PROCESSING; do not automatically mark FAILED if prior side effects are unknown.

On shutdown, stop accepting new operations, finish or checkpoint running steps, and release resources. For tasks that must resume after a restart, checkpoints and outcomes must be stored durably, not merely in the memory of a subscribed Flux.

## 11. Observability and Reconciliation

Handling partial success in production requires observing progress and having the ability to repair inconsistent state.

Write structured logs containing:

- operationId and itemId.
- idempotencyKey or a safe hash.
- previous and new status.
- attempt count and processing duration.
- standardized error code.
- correlation ID / trace ID to link logs across services.

Do not write tokens, passwords, personal data, or sensitive payloads to logs.

Useful metrics:

- Counts of COMPLETED, PARTIAL_SUCCESS, FAILED, and PROCESSING operations.
- Rates of item success, rejection, and transient failures.
- Operations stuck in PROCESSING past threshold.
- Retry counts per operation.
- End-to-end latency from command receipt to completion.
- Operations requiring reconciliation or compensation.

A reconciliation process can scan items stuck in PROCESSING too long, compare against actual business state, and update results accordingly. State repairs must be idempotent and maintain an audit trail. Never automatically mark an operation successful merely because a timeout elapsed.

## 12. Common Design Mistakes

| Anti-pattern | Consequence | Fix |
|---|---|---|
| Returning one boolean for the whole batch. | Unknown which items succeeded. | Return per-item status and operation ID. |
| Treating timeout as unprocessed. | Resends committed side effects. | Query status and use idempotency keys. |
| Retrying whole batch with new keys. | Creates duplicate transactions. | Keep original keys and retry only incomplete items. |
| Turning every exception into REJECTED. | Infrastructure failures disguised as business rejections. | Classify errors and catch only expected domain failures. |
| Storing outcomes only in memory. | Loses recovery capability across restarts. | Persist operation/item state in a database or durable store. |
| Sending confirmation before commit. | Client trusts an unpersisted operation. | Emit outcomes only after commit. |
| Using Fire-and-Forget when outcomes matter. | Client has no business status visibility. | Use Request-Response/Channel or a status API. |
| Treating resume as an exactly-once guarantee. | Side effects can still repeat. | Combine resume with idempotency and transactions. |
| Holding long transactions across network calls. | Holds locks, increases timeouts, hard to recover. | Short local transactions and Sagas if needed. |
| Canceling a stream and deleting operation state. | Impossible to know what already committed. | Persist checkpoints and state independently of streams. |

## 13. Pre-Deployment Checklist

- [ ] Decided whether the batch is all-or-nothing or permits partial success.
- [ ] Stable operation ID exists for the whole workflow.
- [ ] Each item has an item ID and a stable idempotency key.
- [ ] Same key with a different payload is detected and rejected.
- [ ] Side effects and idempotency outcomes commit atomically.
- [ ] DTOs distinguish SUCCEEDED, REJECTED, RETRYABLE_FAILURE, and PROCESSING.
- [ ] Client has a status-query route after timeouts or disconnects.
- [ ] Retries are bounded and apply only to transient errors.
- [ ] Side-effecting operations are never retried without idempotency protection.
- [ ] Streams emit confirmations only after outcomes are durable.
- [ ] Cancellation does not erase committed outcomes.
- [ ] Long operations have checkpoints, reconciliation, and shutdown policies.
- [ ] Logs and metrics enable tracing operations/items without leaking sensitive data.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): interaction models, RSocketRequester, and annotated responders.
- [Spring Framework Reference — RSocket Messaging](https://docs.spring.io/spring-framework/reference/rsocket.html#rsocket-annotated-responders): route mapping and reactive handlers.
- [RSocket Protocol](https://rsocket.io/about/protocol/): request frames, stream termination, errors, and session resumption.
- [RSocket Java](https://github.com/rsocket/rsocket-java): connector, transport, and lifecycle implementations.
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/): Flux, Mono, backpressure, cancellation, and retries.
- [Reactive Streams](https://www.reactive-streams.org/): rules for asynchronous data transfer with backpressure.
