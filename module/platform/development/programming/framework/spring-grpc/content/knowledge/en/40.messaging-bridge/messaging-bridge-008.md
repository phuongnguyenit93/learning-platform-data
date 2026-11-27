# Retries Between gRPC and the Broker

## 1. An Operation Has Multiple Retry Layers

In **SPRING_GRPC**, clients invoke RPCs according to a Protocol Buffers contract against a Spring service. The ingress may store a command in a database/outbox, publish via a message broker, and let a consumer execute business logic. Such an operation has several places where retries can occur:

- **gRPC client retry:** re-invoking the RPC upon receiving a recoverable status or an uncertain call outcome.
- **Producer retry:** the Kafka/RabbitMQ client retrying message delivery when the broker or connection temporarily fails.
- **Outbox relay retry:** re-reading records not yet acknowledged by the broker and publishing again.
- **Consumer retry/redelivery:** reprocessing a message when the consumer hits a transient error or acknowledgement/offset commit fails.
- **Downstream RPC retry:** the consumer calling another service and retrying that call.

These layers have distinct goals and failure boundaries. Never turn on unbounded retries at every layer expecting the system to heal itself. Retries must have limits, backoff, error classification, and idempotency mechanisms so one business intent does not produce multiple side effects.

~~~mermaid
flowchart TD
    C["gRPC client"] -->|bounded RPC retry| G["Spring gRPC ingress"]
    G --> O["Database + outbox"]
    O -->|relay retry| P["Broker producer"]
    P --> B["Message broker"]
    B -->|redelivery / consumer retry| W["Consumer"]
    W -->|bounded downstream retry| D["Downstream gRPC"]
    W --> X["Business side effect"]
~~~

## 2. Classify Errors Before Retrying

Retries only help when an error is likely to resolve after a short interval. Malformed requests or permanent business errors will not be fixed by resending the same operation.

| Error | Should retry? | How to handle |
|---|---|---|
| Transient disconnect, broker unavailable | Usually yes | Backoff, cap attempts, and preserve message/operation ID |
| Timeout, uncertain whether server/broker received it | Conditionally | Retry with same idempotency key; query operation if needed |
| Database deadlock or transient error | Usually yes | Retry transaction at a safe boundary |
| Overload or quota | Conditionally | Respect backoff/quota; avoid aggressive retrying |
| `INVALID_ARGUMENT` | No | Fix the request |
| `PERMISSION_DENIED` | No | Fix permissions or policy |
| `UNAUTHENTICATED` | Not automatically | Refresh credentials per auth flow before deciding to re-call |
| `NOT_FOUND` or `FAILED_PRECONDITION` | Usually no | Handle business state |
| Malformed message schema/undeserializable | Never retry infinitely | Quarantine or dead-letter for investigation |
| Unrecoverable consumer business error | No | Record failure state and handle per domain policy |

`UNAVAILABLE` usually indicates a transient error in gRPC. `DEADLINE_EXCEEDED` is an uncertain outcome: the server may have committed before the response was lost. `RESOURCE_EXHAUSTED` should only be retried when the system identifies it as a temporary limit with an appropriate wait interval. Do not apply one generic retryable status list to every RPC.

## 3. Bounded gRPC Client Retries

gRPC Java supports retry policies via service config. Example retry configuration for `SubmitOrder` when receiving `UNAVAILABLE`:

~~~java
Map<String, Object> retryPolicy = Map.of(
        "maxAttempts", 4.0,
        "initialBackoff", "0.1s",
        "maxBackoff", "1s",
        "backoffMultiplier", 2.0,
        "retryableStatusCodes", List.of("UNAVAILABLE"));

Map<String, Object> methodConfig = Map.of(
        "name", List.of(Map.of(
                "service", "orders.v1.OrdersIngress",
                "method", "SubmitOrder")),
        "retryPolicy", retryPolicy);

ManagedChannel channel = ManagedChannelBuilder
        .forTarget(target)
        .defaultServiceConfig(Map.of(
                "methodConfig", List.of(methodConfig)))
        .enableRetry()
        .build();
~~~

`maxAttempts` includes the initial call. This example allows up to four attempts, with increasing backoff capped at one second. Verify that the service config is applied for the target environment's channel/resolver; do not assume every channel enables retries automatically.

Deadlines must be set once for the entire RPC:

~~~java
SubmitOrderReply reply = blockingStub
        .withDeadlineAfter(900, TimeUnit.MILLISECONDS)
        .submitOrder(request);
~~~

Do not create a fresh 900 ms deadline inside a loop for each attempt. Total time across retries, backoff, and network must fit within the caller's deadline. When the budget runs out, the client receives `DEADLINE_EXCEEDED` even though the server might have processed the request.

## 4. RPC Retries Require Business-Layer Idempotency

Suppose the ingress commits the order and outbox successfully, but the gRPC response is lost. The client sees a timeout and retries. If the new call generates a new `commandId` or `eventId`, a single order intent could execute twice.

The request contract should include an idempotency key:

~~~proto
message SubmitOrderRequest {
  string customer_id = 1;
  repeated OrderLine lines = 2;
  string idempotency_key = 3;
}

message SubmitOrderReply {
  string operation_id = 1;
  OperationState state = 2;
}
~~~

The ingress stores a mapping with a unique constraint on `(tenantId, idempotencyKey)`:

1. First time receiving the key: generate a stable `operationId`/`commandId` and store a payload fingerprint.
2. Retry with same key and same payload: return the existing operation and its current state.
3. Same key with different payload: return a conflict per API contract.
4. Command/outbox record reuses the existing ID; do not emit a new business intent.

Checking and creating the mapping must be atomic so two concurrent requests with the same key do not create two operations. Correlation ID may be fresh per RPC attempt; operation ID and idempotency key remain stable across retries of the same intent.

## 5. Distinguishing RPC Retries from Command Retries

When an RPC returns `ACCEPTED`, the ingress has durably recorded the command per contract. If the client retries merely because it wants to know the result, the ingress should return the same `operationId` and current state. Do not publish a new command just because the client re-called the RPC.

If the client receives `DEADLINE_EXCEEDED` or disconnects before learning the outcome, the state may be uncertain. The client should retry with the same idempotency key or query the operation by key/ID. Never generate a new key "just to be sure".

For request/reply holding the RPC open until the worker responds, each RPC attempt can have its own correlation ID and pending future. However, every attempt must still reference the same operation if it represents the same intent. Late replies from an old attempt must never be mismatched onto a new attempt's future.

## 6. Producer Retries and Outbox Relay Retries

Producer retries handle message-sending errors while the producer remains alive. Outbox relay retries handle resuming publishing after a process restart or after the producer exhausts internal retries.

With Kafka, you can configure producer idempotence and strong acknowledgements:

~~~java
props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
props.put(ProducerConfig.ACKS_CONFIG, "all");
props.put(ProducerConfig.RETRIES_CONFIG, Integer.MAX_VALUE);
props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);
~~~

This is an illustrative configuration; align `delivery.timeout.ms`, request timeout, broker replication, and relay time bounds. Producer idempotence reduces duplicates caused by retries within a producer session/protocol. It does not replace stable event IDs or consumer deduplication after a relay restarts and re-publishes an outbox record.

The relay marks an outbox record published only after receiving acknowledgement. If sending fails or the outcome is uncertain, retain the record to retry with the same `eventId` and payload. If the broker received the message but the acknowledgement was lost, the relay may publish again; consumers must tolerate duplicates.

Do not hold a database transaction open while waiting on the broker network. Claim/lease records briefly, publish outside the transaction, then update status conditionally after acknowledgement so multiple relay instances do not contend arbitrarily over the same record.

## 7. Consumer Retries and Redelivery

A consumer can fail after receiving a message. Retry policy depends on the error category:

- **Transient:** database deadlock, downstream unavailable, temporary timeout. Retry with backoff.
- **Permanent:** malformed payload, unsupported schema version, contract-invalid data. Never retry infinitely; route to dead-letter/quarantine.
- **Business rejection:** command cannot execute due to business state. Record `REJECTED` or a failure event; do not treat it as an infrastructure error to retry.

Example Spring Kafka `DefaultErrorHandler` configuration with three retries after initial processing and a dead-letter recoverer:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 3L));

    handler.addNotRetryableExceptions(
            InvalidOrderCommand.class,
            UnsupportedSchemaVersionException.class);

    return handler;
}
~~~

This example requires a `DeadLetterPublishingRecoverer` configured with an appropriate producer. `FixedBackOff` here illustrates a simple policy; systems can use exponential backoff, retry topics, or custom error handlers. Verify retry counts and ack/offset semantics for your version of Spring Kafka.

When a consumer processes successfully but offset commit/ack fails, the message may be redelivered. Thus, retry policy does not eliminate the requirement for idempotency.

## 8. Idempotent Consumers Protect Side Effects

Consumers should deduplicate by `eventId`/`messageId`, not correlation ID, because multiple valid messages in the same workflow share a correlation ID.

For side effects in the same database, persist an inbox marker and update domain state in the same transaction:

~~~java
@Transactional
public void handle(OrderCreatedEvent event) {
    if (inboxRepository.existsByMessageId(event.messageId())) {
        return;
    }

    inboxRepository.insert(event.messageId());
    orderProjection.apply(event);
}
~~~

The database needs a unique constraint on `messageId`; checking and inserting must be protected against races between two consumers. If the transaction rolls back, both the inbox marker and projection update roll back together. If the commit succeeds while the broker offset has not yet committed, redelivery hits the marker and avoids repeating side effects.

If the consumer calls an external system outside the database, pass a stable idempotency key (often derived from operation/event ID) to that API or use a dedicated workflow/outbox. End-to-end exactly-once cannot be guaranteed solely by Kafka producer idempotence or an inbox table in a different service.

## 9. Exponential Backoff, Jitter, and Retry Budgets

Aggressive retries can overload an already struggling service. Increasing backoff creates spacing between attempts:

\[
delay_n = \min(maxDelay,\ initialDelay \times multiplier^n)
\]

Add **jitter** so clients do not retry at the exact same time:

\[
actualDelay_n \sim U(0,\ delay_n)
\]

Example policy: 100 ms initial delay, multiplier 2, 2-second cap, up to three retries. This is only a starting point; tune values to target latency and error type.

Retry budgets should bound:

- Maximum attempts at each boundary.
- Total retry time not exceeding deadline or command expiry.
- In-flight requests/messages and concurrency.
- Overall retry ratio over normal traffic.
- Retry count before moving to dead-letter or alerting operations.

Do not retry validation, schema, or authorization errors. Avoid long in-thread backoffs on consumer threads holding partitions if high throughput is required; use retry topics or an appropriate pause mechanism.

## 10. Do Not Multiply Retries Across Every Layer

Suppose the gRPC client retries four times, the relay retries several times, the consumer retries four times, and the downstream client also retries four times. A single downstream error can amplify work far beyond one initial request.

Assign clear boundary ownership for each retry type:

| Boundary | Retry responsibility |
|---|---|
| gRPC client | Transient transport errors before receiving a result; always preserve idempotency key |
| Ingress/outbox | Persist command once; relay retries publishing |
| Producer client | Retry network/broker errors within delivery timeout |
| Consumer | Retry transient processing errors; permanent errors go to DLQ |
| Downstream client | Bounded retries within remaining deadline and idempotency |

Do not let client retries create new operations, ingress retries create new commands, or relay retries generate new event IDs. One operation may have multiple attempts, but it must retain its identity and state end-to-end.

## 11. Retries, Ordering, and Partitions

Retries can affect message ordering:

- Retrying on the current partition can preserve ordering but stalls subsequent records behind it.
- Retry topics allow the main partition to keep moving, though failed messages may return after newer messages.
- Dead-letter queues isolate failed messages from the main flow, requiring a controlled replay procedure.

If business logic requires per-aggregate ordering, use a stable partition key and control consumer concurrency. Attach `aggregateVersion` to detect missing or out-of-order events. When replaying from a DLQ, do not blindly push old messages straight back into live streams; verify versions and current state first.

## 12. Deadlines and Command Expiry Bound Retries

For synchronous RPCs or request/reply, all attempts and backoff must fit within the client's deadline. Each retry must not receive a fresh full timeout.

For already-accepted asynchronous commands, the RPC deadline only bounds how long the ingress responds. Consumers use `commandExpiresAt` or a dedicated processing budget when business logic has a time limit. Retries must not refresh command expiry:

~~~text
Command created: 10:00
Command expires: 10:05
Attempt 1: 10:01 -> database unavailable
Attempt 2: 10:03 -> downstream timeout
Attempt 3: 10:04:50 -> 10 seconds remaining
After 10:05 -> mark expired; stop retrying
~~~

If expiry has passed, stop retrying side effects. Record operation state `EXPIRED` or an appropriate dead-letter reason. Extending validity must be an explicit new business decision with authorization and audit, never an implicit side effect of retries.

## 13. Circuit Breakers and Backpressure Complement Retries

Retries handle short-lived errors; circuit breakers prevent continuously calling a failing dependency. When a circuit opens, the ingress/consumer can fail fast, letting the outbox or broker hold work and retry later per policy.

Combine:

- **Circuit breaker:** stops new requests to a failing dependency.
- **Bulkhead/concurrency limit:** bounds concurrent tasks.
- **Rate limit/quota:** controls load per tenant or caller.
- **Backpressure:** slows intake when consumers cannot keep up.
- **Retry budget:** limits attempt counts and total retry duration.

Do not retry immediately against an open circuit breaker. Do not maintain unbounded in-memory queues; work that must survive restarts belongs durably in a broker/outbox.

## 14. Testing Retries Across gRPC and the Broker

Tests should simulate failures at every boundary:

| Scenario | What to verify |
|---|---|
| gRPC returns `UNAVAILABLE` before processing | Client retries within bounds using same idempotency key |
| Server commits, response is lost | Retry returns the same operation, no duplicate order created |
| gRPC deadline expires between attempts | Total time stays within deadline; outcome queryable via operation ID |
| Producer hits transient failure | Producer/relay retries with the same event ID |
| Broker receives message, ack is lost | Relay may send duplicate; consumer does not repeat side effects |
| Relay restarts | Pending outbox records continue publishing |
| Consumer hits transient failure | Retries/backoff run exact configured count |
| Consumer hits permanent failure | Message moves to DLQ without infinite retries |
| Consumer commits DB, offset commit fails | Redelivery does not repeat side effects |
| Retry topic reorders messages | Version/ordering policy detects or handles properly |
| Prolonged downstream outage | Circuit breaker and retry budget cap load |
| Command expires during backoff | Retries stop and operation transitions to `EXPIRED` |

Use a real or containerized database and broker for integration tests. Mocking the producer only verifies that code invokes the API; it does not prove acknowledgement, redelivery, offset commits, or dead-letter behavior.

## 15. Metrics and Diagnostics

Monitor per boundary:

- gRPC retry attempts, status codes, deadline exceeded, and idempotency hits.
- Producer send retries, acknowledgement latency, and delivery timeouts.
- Pending outbox count, oldest record age, relay retries, and publish failures.
- Consumer retry counts, redeliveries, processing latency, and DLQ rate.
- Duplicate messages filtered by inbox/idempotency.
- Downstream circuit state, rejected calls, and retry budget exhaustion.
- Queue lag, partition skew, and command expirations.

Use operation ID, correlation ID, and message ID in logs/traces; do not use high-cardinality IDs as metric labels. During investigations, locate an operation and compare attempts across each boundary to see which retries occurred and which milestones committed.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Retrying all gRPC status codes | Repeats requests that cannot succeed | Allowlist transient errors |
| Generating a new idempotency key per retry | Creates multiple operations | Keep key stable per business intent |
| Granting a fresh deadline per attempt | Total duration exceeds budget | Single deadline for the entire RPC |
| Returning `ACCEPTED` before durable save | Command can be lost after response | Commit receipt/outbox first |
| Marking outbox published before broker ack | Loses events | Mark only after acknowledgement |
| Trusting producer idempotence for system-wide exactly-once | Consumer can still duplicate side effects | Inbox/deduplication at consumer |
| Retrying schema-invalid messages forever | Poison message blocks the stream | Non-retryable classification and DLQ |
| Unbounded retries at every layer | Retry storms and load amplification | Retry budgets, backoff, jitter, circuit breakers |
| Replaying DLQ without checking order | Corrupts aggregate state | Version checks and replay policy |

**Key takeaway:** Retries between gRPC and the broker must be designed boundary by boundary: clients retry RPCs, producers/outbox retry publishing, and consumers retry processing. Classify transient vs. permanent errors, bound attempts and total duration with deadlines/command expiries, and use exponential backoff with jitter. Keep idempotency keys, operation IDs, and event IDs stable across retries; use an outbox to preserve publish intent and inbox/idempotent consumers to prevent duplicates. Retries do not replace backpressure, circuit breakers, or dead-letter policies.
