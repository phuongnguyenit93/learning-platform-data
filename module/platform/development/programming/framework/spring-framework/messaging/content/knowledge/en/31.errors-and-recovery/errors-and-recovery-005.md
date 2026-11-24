# Distinguishing Idempotent Operations from Side-Effecting Operations

## Objectives

After this lesson, you will be able to:

- Explain idempotency (safe repeatability) and distinguish it from side-effect-free operations.
- Identify risks when retrying a messaging request after a timeout or disconnect.
- Distinguish client retries, message redelivery, and duplicate processing on the consumer.
- Design idempotency keys, deduplication, and result persistence so a business operation produces its effect once within a defined scope.
- Apply these principles with Spring Messaging and RSocket.
- Choose retry policies, transactions, inbox/outbox, or compensation mechanisms suited to the type of side effect.

This lesson belongs to the **Spring Framework - messaging** topic, under the **Errors and Recovery** branch. The focus is making the system behave correctly when the same request can arrive multiple times, especially when the client does not know whether the server already executed the operation.

## 1. What Is Idempotency?

An operation is **idempotent** if executing it once or repeating it multiple times with the same input and business scope yields the same final state.

This can be expressed as:

~~~text
f(f(state, request), request) = f(state, request)
~~~

In other words, after the first execution, repeated invocations of the same request do not add further business effect.

Examples:

| Operation | Idempotent? | Reason |
|---|---|---|
| Set order status to SHIPPED | Yes, for the same order and same status | Repeating still keeps the status as SHIPPED |
| Mark a notification as read | Usually yes | Final state remains read |
| Fetch order details | Usually yes with respect to business state | Reading again introduces no extra business change |
| Increment view count by 1 | No | Each call increments the counter further |
| Debit 100,000 VND from an account | No | Repeating could debit money multiple times |
| Create a new order | Usually no | Each call might create another order |
| Send confirmation email | Not automatically idempotent | Each send could generate another email |

Idempotent does not mean **having no side effects**. Updating order status, recording a payment, or issuing an invoice are all operations with side effects. They can still be designed to be idempotent if the system recognizes repetitions of the same operation and prevents effects from being duplicated.

Conversely, an operation that does not alter business data can still produce technical side effects such as writing audit logs, incrementing metrics, or consuming resources. Therefore, clearly define which states and effects must be protected.

## 2. Why Does Messaging Need Idempotency?

In distributed systems, a client sends a request over the network and waits for the result. There are several points where the connection can fail:

1. The client sends the request, but the request never reaches the server.
2. The request reached the server, but the server has not started processing yet.
3. The server is processing when the connection drops.
4. The server committed the business change, but the response was lost on the way back.
5. The client receives a timeout before knowing the server's final outcome.

The fourth case is especially dangerous. The client sees a timeout and does not know whether the operation succeeded. If the client resends a debit or order-creation command and the server lacks duplicate detection, the effect can happen twice.

**A timeout is an uncertain state, not proof that the server has not executed the operation.**

Therefore, safe retry requires answering two questions:

- Is the error likely transient and recoverable?
- If the request was already processed before the error occurred, will resending the same request create extra effects?

Checking only the exception type is not enough. Retries must consider the business semantics of the operation.

## 3. Idempotent, Retryable, and Side-Effect-Free Are Not the Same

Three concepts are often used interchangeably, yet carry distinct meanings:

| Concept | Meaning |
|---|---|
| Side-effect-free | Does not mutate state or produce external effects within the scope under consideration |
| Idempotent | Repeating the same operation does not add to the final effect |
| Retryable | Can be retried under certain failure conditions while preserving correct behavior |

A side-effect-free operation can usually be retried safely if reads have no special consistency requirements. An idempotent operation can have side effects yet remain safe to repeat. A non-idempotent operation can only be retried safely when the system adds deduplication or transactional protection.

For example, a command to SET account status to ACTIVE updates data yet can be idempotent. A command to INCREMENT a balance or stock quantity is non-idempotent without an execution identifier.

HTTP also uses idempotency for method semantics: PUT and DELETE are defined as idempotent in their intended effect, while POST generally lacks that guarantee. That is an HTTP semantic convention; you cannot infer that every Spring handler or every POST endpoint is non-idempotent. What decides is the business contract and actual implementation.

## 4. Retries in Spring Messaging and RSocket

Spring Messaging provides abstractions for messages and handlers. With Spring RSocket, clients typically use **RSocketRequester** to send requests; servers use **@MessageMapping** to receive and process them.

Example Request-Response handler:

~~~java
@Controller
class PaymentController {

    private final PaymentService payments;

    PaymentController(PaymentService payments) {
        this.payments = payments;
    }

    @MessageMapping("payments.charge")
    Mono<ChargeResult> charge(ChargeCommand command) {
        return payments.chargeOnce(command);
    }
}
~~~

This is an illustrative skeleton. ChargeCommand must carry a stable identifier for the operation, while PaymentService is responsible for checking duplicates and safely executing the business logic.

On the client, a request can be retried with Reactor:

~~~java
Mono<ChargeResult> result = requester
    .route("payments.charge")
    .data(command)
    .retrieveMono(ChargeResult.class)
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(3))
            .jitter(0.5)
            .filter(this::isTransient)
    );
~~~

This snippet is an excerpt to place inside a class that already has `requester`, `command`, and the `isTransient` method; import the corresponding Reactor `Retry` and `Duration` types.

Key points:

- retryWhen resubscribes to the upstream publisher. Each subscription may send a fresh request to the server.
- command and idempotency key must be created stably outside the retried publisher. Do not generate a new key inside defer or per subscription.
- Retry only errors likely to be transient, such as certain connection errors or recoverable overload.
- Do not retry infinitely. Attempt count, wait interval, jitter, and total deadline must be bounded.
- If a timeout occurs after the server commits, the retry must be recognized by the server as the same operation.

RSocket offers multiple interaction models such as Request-Response, Request-Stream, Request-Channel, and Fire-and-Forget. These models describe how requests, responses, and streams are exchanged; by themselves they do not provide exactly-once guarantees for business effects. A connection drop or client retry can still create duplicate requests at the application layer.

In particular, Fire-and-Forget does not return a business response. Publisher completion on the client must not be interpreted as proof that all business side effects committed and were durably stored. If the client needs result confirmation, choose an interaction model with a response or build a separate acknowledgement.

## 5. Idempotency Key: Identifying One Operation Across Multiple Sends

An **idempotency key** is an identifier generated by the caller for a business operation. Every retry of that same operation must reuse the same key.

Example:

~~~text
idempotencyKey = "checkout-2026-000184"
operation      = create payment
amount         = 250000
customer       = customer-42
~~~

If the client resends the same command due to a timeout, the server finds the processed key and returns the stored result instead of debiting again.

A solid design needs these properties:

1. **Stable:** the key does not change across retries of the same operation.
2. **Unique within scope:** the key must be unique within the tenant, account, or business type defined by the system.
3. **Bound to request content:** store a fingerprint or critical business fields to detect reusing the key for a different command.
4. **Durably stored:** for critical operations, deduplication state must survive restarts and work across multiple instances.
5. **Appropriate retention:** key retention must exceed the retry/redelivery window the system commits to support.

Do not use the current timestamp to generate a new key on every retry. Also do not rely solely on a UUID generated on the server after the request arrives, because the client cannot resend that UUID if it timed out before receiving the response.

The key can reside in the business payload or metadata depending on the application contract. If placed in metadata, ensure client and server agree on MIME type, encoder/decoder, and authentication policy. Wherever placed, the key must be transmitted intact across retries.

## 6. Deduplication Must Check Both Key and Content

Checking only whether the key exists is not enough. Suppose the first request uses key K to pay 100,000 VND. Another request accidentally reuses K to pay 500,000 VND. If the server sees only the duplicate key and returns the old result, a client-side bug gets hidden.

An idempotency record should store at least:

| Field | Purpose |
|---|---|
| idempotency_key | Key identifying the operation |
| request_fingerprint | Detects same key with different content |
| status | IN_PROGRESS, COMPLETED, or a retryable error status per contract |
| result/reference | Created result or reference ID to the result |
| created_at / expires_at | Manages deduplication retention window |

Typical processing flow:

1. Receive the request and validate syntax, access permissions, and input data.
2. Compute a normalized fingerprint from the fields that affect business semantics.
3. Attempt to insert the idempotency record with the unique key.
4. If the key is new, execute business logic and persist the result.
5. If the key exists and the fingerprint differs, return a conflict error.
6. If the key is COMPLETED and the fingerprint matches, return the stored result.
7. If the key is IN_PROGRESS, apply a wait policy, return an in-progress status, or let the caller query the result later.

The fingerprint should be derived from a canonical representation. Do not hash arbitrary JSON if property order, number formatting, or default values can vary between two equivalent requests. Select meaningful business fields and normalize them before hashing or comparing.

## 7. Java 17 Example: Preventing Duplicate Execution in a Single Process

The following example uses ConcurrentHashMap to illustrate an operation with side effects protected by an idempotency key. The same key with the same command content receives the same result; the same key with different content is rejected.

Save as **IdempotencyDemo.java**:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class IdempotencyDemo {

    record ChargeCommand(
        String idempotencyKey,
        String customerId,
        long amountInCents
    ) {}

    record ChargeResult(String operationId, long amountInCents) {}

    record StoredResult(ChargeCommand command, ChargeResult result) {}

    static final class PaymentService {
        private final ConcurrentHashMap<String, StoredResult> completed =
            new ConcurrentHashMap<>();

        private final AtomicInteger executions = new AtomicInteger();

        ChargeResult charge(ChargeCommand command) {
            if (command.idempotencyKey() == null
                    || command.idempotencyKey().isBlank()) {
                throw new IllegalArgumentException(
                    "idempotencyKey is required"
                );
            }

            if (command.amountInCents() <= 0) {
                throw new IllegalArgumentException(
                    "amountInCents must be positive"
                );
            }

            StoredResult stored = completed.compute(
                command.idempotencyKey(),
                (key, previous) -> {
                    if (previous != null) {
                        if (!previous.command().equals(command)) {
                            throw new IllegalArgumentException(
                                "Idempotency key reused with different command"
                            );
                        }
                        return previous;
                    }

                    int sequence = executions.incrementAndGet();
                    ChargeResult result = new ChargeResult(
                        "payment-" + sequence,
                        command.amountInCents()
                    );

                    return new StoredResult(command, result);
                }
            );

            return stored.result();
        }

        int executionCount() {
            return executions.get();
        }
    }

    public static void main(String[] args) {
        PaymentService service = new PaymentService();

        ChargeCommand firstCommand = new ChargeCommand(
            "request-123", "customer-7", 2500
        );

        ChargeResult first = service.charge(firstCommand);
        ChargeResult retry = service.charge(firstCommand);

        System.out.println(
            "same-operation=" + first.operationId().equals(retry.operationId())
        );
        System.out.println("executions=" + service.executionCount());

        try {
            service.charge(
                new ChargeCommand("request-123", "customer-7", 3000)
            );
        } catch (IllegalArgumentException ex) {
            System.out.println("same-key-different-command=rejected");
        }
    }
}
~~~

Compile and run with Java 17 or higher:

~~~bash
javac IdempotencyDemo.java
java IdempotencyDemo
~~~

Exact output:

~~~text
same-operation=true
executions=1
same-key-different-command=rejected
~~~

In this example, ConcurrentHashMap.compute performs an atomic update by key within the current process's map. AtomicInteger simply counts how many times the branch creating a new result ran. The second call retrieves the previous result; the third call uses the same key with a different amount and is rejected.

**Limitation of this example:** the map lives only in memory of one process. On restart, data is lost; when running multiple instances, each instance has its own map. This is not a production payment store and does not protect external side effects such as calling a bank. Real systems need durable storage and unique constraints at the database or business service layer.

## 8. Transactions and Atomicity

For side effects inside the same database, the idempotency record and business mutations can be persisted within the same transaction.

Example logic:

~~~text
BEGIN TRANSACTION

INSERT idempotency_record(key, fingerprint, status)
  -- key has a UNIQUE constraint

If insert succeeds:
    update business data
    store result and status = COMPLETED
    COMMIT
    return result

If key already exists:
    read existing record
    compare fingerprint
    if different: return conflict
    if COMPLETED: return stored result
    if IN_PROGRESS: apply wait/query policy

END
~~~

The UNIQUE constraint is a critical safeguard when concurrent requests hit different instances. A check-then-insert using two separate statements without proper transactions/constraints can create a race condition: two requests both see the key missing and both execute the side effect.

In Spring, you can use transactions managed by Spring Data/JDBC/JPA or reactive transactions depending on the stack. With reactive code, use a reactive transaction manager and ensure operations share the same transaction context. Never call blocking database APIs on an event loop just to sidestep transaction issues.

If updating a database and sending a message to a broker/RSocket are two separate side effects, an ordinary database transaction cannot atomically commit both systems. This is where **Transactional Outbox** helps:

1. In the same transaction, update business data and write an outbox event.
2. A publisher reads the outbox and sends events externally.
3. Once sent successfully, mark or save a checkpoint so no event is missed.
4. The consumer uses inbox/deduplication to handle duplicate events safely.

Outbox typically provides at-least-once event delivery. Consumers still need idempotency because the publisher may resend an event after losing an acknowledgement.

## 9. Inbox, Outbox, and Duplicate Message Handling

In messaging, distinguish **message delivery** from **business processing**.

- Outbox ensures business changes and the intent to emit a message are stored in the same transaction.
- Inbox records messages received/processed by the consumer using a stable message ID.
- Deduplication checks the message ID or idempotency key before applying side effects.
- Wrapping the inbox record and business changes in a transaction avoids recording a message as processed while business state failed to commit, or vice versa.

A consumer can follow this flow:

~~~text
receive message
    |
validate message ID and payload
    |
begin transaction
    |
insert inbox record with UNIQUE(message_id)
    |
    +-- duplicate --> return prior outcome / ignore safely
    |
apply business state change
    |
commit
    |
acknowledge or complete processing
~~~

If the message ID already exists, the consumer must know its prior processing status. Never mark a message completed before critical side effects commit. If a message may currently be processed by another worker, you need an IN_PROGRESS status, lease/lock, or appropriate claiming mechanism.

With RSocket request-response, the client can use an idempotency key for the command. With Request-Stream or Request-Channel, each element in the stream needs its own identifier if the consumer can receive duplicates or resume from a checkpoint. One stream-wide key can identify the transfer, while sequence/message IDs identify each chunk.

## 10. Handling External Side Effects

Not all side effects live inside the application's database. Examples:

- Calling a payment gateway.
- Sending email or SMS.
- Provisioning cloud resources.
- Calling an API on another system.
- Publishing events to a broker.

Whether the application commits the database then calls the external service, or calls the external service then commits the database, a failure window exists between the two steps.

Options:

1. **Downstream idempotency key:** forward the same key to the external service if supported. The key must stay stable across all retries.
2. **Outbox:** persist the intent to perform the side effect in the database within the business transaction and process asynchronously.
3. **State machine:** persist step-by-step state, such as PENDING, PROCESSING, SUCCEEDED, FAILED, enabling recovery after restarts.
4. **Reconciliation:** reconcile internal state against the external system when outcomes are ambiguous.
5. **Compensation/Saga:** if an already-occurred side effect cannot be rolled back, run a designed business compensating action.

A compensating action is not always a perfect inverse. For example, a refund is a new business operation with an audit trail, not deleting the payment transaction that occurred.

Never blindly retry an external command merely because the client timed out. First look up its status using an operation ID or idempotency key if the API provides one.

## 11. Safe Retry Policies

A solid retry policy includes:

- **Error classification:** validation, access permission, or data conflict errors normally do not retry; transient connection errors or overload may retry with bounds.
- **Attempt cap:** avoid infinite loops.
- **Exponential backoff:** increase waits between attempts to avoid piling load onto a failing service.
- **Jitter:** add random offset so multiple clients do not retry simultaneously.
- **Deadline:** total retry duration must fit within the business time budget.
- **Retry budget:** cap total retry volume to prevent cascading incidents.
- **Idempotency:** keep the key and business content unchanged across attempts.
- **Observability:** log operation ID, suitably masked/hashed idempotency key, attempt count, error category, and final outcome.

Do not retry every exception. Retrying a permanent business error only increases load and latency. Also avoid combining unbounded retry layers: client, gateway, service, and libraries all retrying can produce far more executions than intended.

When a timeout occurs, distinguish:

- **Timeout before sending:** the request may never have reached the server.
- **Timeout while the server is processing:** outcome is unknown.
- **Timeout after commit:** side effect may have succeeded, only the response was lost.

From the client side, post-send cases usually cannot be distinguished reliably from exceptions alone. Idempotency and outcome lookup are the solutions at the business layer.

## 12. Interaction with RSocket Interaction Models

| Interaction model | Common usage | What to protect |
|---|---|---|
| Request-Response | Create order, update state, charge payment | Idempotency key for command and stored outcome |
| Request-Stream | Query data stream | Retry may replay entire stream; need cursor/checkpoint for large streams |
| Request-Channel | Two-way exchange or multi-chunk upload | Stream identifier, per-chunk sequence, resume and duplicate handling |
| Fire-and-Forget | Send notification without direct response | Do not rely on response to confirm commit; need event ID and tracking if critical |

RSocket request(n) and Reactive Streams backpressure control demand for messages/streams. They do not make a side effect idempotent and do not guarantee a command runs only once. Backpressure controls rate; idempotency controls duplicate effects. These two mechanisms solve different problems.

## 13. Testing Idempotency

A test that invokes a service only once does not prove idempotency. Test these scenarios:

1. Send the same command twice with the same key and same content; only one business effect occurs.
2. Send multiple concurrent requests with the same key; only one request produces the side effect.
3. Reuse the key with different content; server returns a conflict or appropriate error.
4. Server commits yet response is dropped; client retries and receives the stored result.
5. Restart the service between attempts; deduplication persists if the system commits to durable storage.
6. Send the same key to two different instances; database constraints or shared store still prevent duplication.
7. Downstream times out after possibly executing side effects; verify status lookup or downstream key propagation.
8. Duplicate message arrives at consumer; inbox/deduplication prevents repeated updates.
9. Permanent error message; retry policy stops rather than looping infinitely.
10. Message is IN_PROGRESS; duplicate request is handled per the defined policy.

In integration tests, simulate connection loss after transaction commit but before the response reaches the client. That is the easiest scenario to overlook when testing only errors before the server begins processing.

## 14. Common Design Mistakes

- **Generating a new idempotency key on every retry:** the server treats every attempt as a brand-new operation.
- **Storing keys only in memory:** restarts or multiple instances lose deduplication.
- **Not comparing request fingerprints:** the same key can accidentally be reused for different content.
- **Marking COMPLETED before business commit:** can skip operations that never actually succeeded.
- **Committing business state then recording deduplication in a separate transaction:** crashing between steps can duplicate side effects.
- **Assuming Request-Response equals exactly-once:** the response can be lost after the server committed.
- **Retrying all errors:** amplifies load and repeats unrecoverable failures.
- **Multi-layer retries without a budget:** downstream calls can grow exponentially.
- **Using Fire-and-Forget for operations needing confirmation:** the client lacks a business response to know the outcome.
- **No handling for IN_PROGRESS:** two duplicate requests may both execute or the second returns an unclear result.
- **Treating compensation as rollback:** external side effects may not be cleanly reversible.

## 15. Design Checklist

- [ ] Identified which business side effects must never repeat.
- [ ] Identified which operations are idempotent by final state.
- [ ] Commands carry a stable idempotency key across retries.
- [ ] Keys are bound to a request fingerprint.
- [ ] Deduplication is durably persisted and shared across instances if needed.
- [ ] Transactions wrap both the deduplication record and business changes within database scope.
- [ ] External side effects use downstream keys, outbox, state machines, or reconciliation.
- [ ] Consumers have inbox/deduplication for messages that can redeliver.
- [ ] Retries have error classification, attempt caps, backoff, jitter, and deadlines.
- [ ] Timeouts are treated as unknown outcomes when the request may have reached the server.
- [ ] Fire-and-Forget is not used as business acknowledgement.
- [ ] Tests cover duplicates, concurrent requests, crashes, lost responses, and multi-instance setups.

## Conclusion

In messaging systems, retries are necessary to recover from network and transient errors, yet retries can resend an operation the server already executed. Idempotency ensures repeated invocations of the same operation do not double its effect. For critical side effects, combine stable idempotency keys, fingerprints, durable result storage, transactions, and inbox/outbox. RSocket interaction models and Reactive Streams backpressure assist data exchange, while correctness under duplicates must be designed at the business layer.

## References

- [Spring Framework Reference - RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Reference - Messaging](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [Spring Framework Reference - Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [RSocket Protocol](https://rsocket.io/about/protocol/)
- [Reactive Streams Specification](https://www.reactive-streams.org/)
- [Project Reactor Reference - Error Handling and Retry](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
