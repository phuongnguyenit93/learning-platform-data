# Redelivery and duplicate responses

Redelivery occurs when the same logical request is re-sent after a transient failure, timeout, dropped connection, or retry mechanism in a client/proxy. A duplicate response happens when the result of the same logical operation is returned or processed multiple times because multiple attempts ran. In gRPC, an RPC may have already been processed and committed by the server while the client still fails to receive the response. The client sees a transport error or deadline expiration and re-sends the request; if the server executes the operation again, side effects can be duplicated.

In Spring gRPC, reliability must be designed across client retries, gRPC statuses/deadlines, server handlers, transactions, and downstream systems. Retries only improve completion rates for recoverable failures; they do not guarantee a business operation runs only once. Handling redelivery safely requires a stable identifier for the operation, persisting idempotency results atomically with side effects, and defining how clients handle repeated responses.

## 1. Why can a request be re-sent?

A common scenario:

```text
Client                    gRPC Server                 Database
  |                            |                          |
  |---- CreateOrder(key=K) --->|                          |
  |                            |---- INSERT order ------->|
  |                            |<--- COMMIT --------------|
  |          X response lost   |                          |
  |<---- UNAVAILABLE/timeout --|                          |
  |                            |                          |
  |---- retry same request --->|                          |
  |                            |---- INSERT order ------->|
  |                            |       duplicate order!    |
```

The server may have already committed before the connection reset or the response was lost. The client cannot infer from a transport error that the server did not execute the operation. This is an ambiguous outcome: the caller does not know whether the operation never started, is still running, committed, or committed with a lost response.

Redelivery can come from:

- Retries implemented explicitly in application code.
- gRPC channel retry policies on retryable statuses.
- Proxies, service meshes, or gateways with their own retry policies.
- Message brokers/job schedulers redelivering messages when workers miss an ACK deadline.
- Operators replaying a request after an incident.
- Clients reconnecting and recovering a stream by resending unacknowledged commands.

Multiple retry layers can multiply attempt counts. For example, 3 client retries and 2 gateway retries can cause more than one server execution. Map out retry ownership and bound total attempts across the entire request path.

Transport retries alone provide no exactly-once guarantee. A client library may hide internal attempts, yet it cannot eliminate ambiguity when the server committed a side effect and the response was lost. The practical goal is an effectively-once business effect: every redelivery of the same logical operation converges to one business outcome via idempotency and durable deduplication.

## 2. Distinguishing RPC attempts from logical operations

One logical operation can have multiple RPC attempts. Each attempt can have its own call ID/trace span, yet all must share the same idempotency key if they represent the same action:

| Concept | Meaning | Lifecycle |
| --- | --- | --- |
| Logical operation ID | Identifies the business operation | Stable across all retries/redeliveries |
| Idempotency key | Key allowing the server to recognize repeated requests | Stable for the same execution intent |
| RPC attempt ID | Identifies one specific invocation | Fresh for each attempt |
| Request/trace ID | Correlates logs and traces | May be fresh per attempt or propagated per trace policy |

Never generate a new random request ID as the idempotency key on each retry. Otherwise the server will not recognize two calls as the same operation. Conversely, never use the idempotency key as a trace ID; one logical operation can span multiple attempts and multiple spans.

The idempotency key must be created at the boundary where the operation begins and retained across retries. It can live in a Protobuf field or metadata. For write operations, a request field usually ties cleanly to the business contract and is easy to store alongside the command. Metadata works when keys are a cross-cutting concern across many methods, though the server must still verify and persist it.

## 3. gRPC retries and their limits

`grpc-java` can apply a retry policy from service config when the channel/provider supports it. A policy typically specifies:

- `maxAttempts`: maximum total attempts, including the initial attempt.
- `initialBackoff` and `maxBackoff`: initial wait and maximum backoff cap.
- `backoffMultiplier`: factor by which wait intervals grow.
- `retryableStatusCodes`: statuses eligible for retry.

Illustrative service config example:

```json
{
  "methodConfig": [{
    "name": [{
      "service": "acme.orders.v1.OrderService",
      "method": "GetOrder"
    }],
    "retryPolicy": {
      "maxAttempts": 4,
      "initialBackoff": "0.2s",
      "maxBackoff": "2s",
      "backoffMultiplier": 2,
      "retryableStatusCodes": ["UNAVAILABLE"]
    }
  }]
}
```

This is an illustrative configuration; how service config is loaded depends on `ManagedChannelBuilder`, the resolver, and the `grpc-java` version. A Spring gRPC starter may provide channel customizers or dedicated properties. Verify the actual configuration used by the channel rather than merely checking that JSON exists in a file.

Retry policies should apply only to methods with suitable semantics. `GetOrder` can usually retry on `UNAVAILABLE`. `CreateOrder` or `ChargeCard` should retry only when the server supports idempotency. Do not put every status into `retryableStatusCodes`: `INVALID_ARGUMENT`, `UNAUTHENTICATED`, and `PERMISSION_DENIED` do not resolve themselves on another attempt.

`UNAVAILABLE` usually signals a transient error, yet does not prove the server produced no side effects. If the server commits and the connection breaks before the response arrives, retrying `UNAVAILABLE` can still re-run the command. Status codes decide whether to retry; idempotency decides whether retrying is safe.

## 4. Retry, commitment, and deadlines

The gRPC retry runtime can buffer requests to retry before a call is committed under implementation rules. Once response headers are received or buffered data exceeds the retry buffer limit, the call may be marked committed and internal retries stop. Commitment/buffering details depend on the gRPC runtime and RPC type; never rely on them as a substitute for business idempotency.

Deadlines apply to the entire logical RPC and should not be reset to a full budget per attempt. Backoff and prior attempts consume remaining time. If each layer sets a fresh longer deadline, total end-to-end duration can exceed the caller's limit.

Example client deadline:

```java
OrderReply reply = orderStub
    .withDeadlineAfter(1200, TimeUnit.MILLISECONDS)
    .getOrder(request);
```

The deadline must cover expected attempts and backoff while remaining within the API's latency budget. When the deadline expires, callers may receive `DEADLINE_EXCEEDED` even if the server already committed the operation. Thus `DEADLINE_EXCEEDED` is also an ambiguous outcome for commands with side effects.

Never retry indefinitely. Use finite `maxAttempts`, bounded backoff, end-to-end deadlines, and retry budgets to avoid retry storms when a dependency is overloaded.

## 5. Choosing statuses and retry policies

Statuses indicate error categories, but not all errors share the same retry semantics:

| Status | Common handling | Note |
| --- | --- | --- |
| UNAVAILABLE | Can retry with backoff | Prior attempt outcome may still be ambiguous |
| RESOURCE_EXHAUSTED | Retry only with recovery signal/wait window | Immediate retry can worsen overload |
| ABORTED | Can rerun transaction at a higher level | Usually requires restarting the full transaction |
| DEADLINE_EXCEEDED | Retry only with remaining budget and idempotent operation | Server may have already completed |
| CANCELLED | Typically do not auto-retry when caller actively cancelled | Distinguish shutdown/transport cancellations |
| INVALID_ARGUMENT | Do not retry | Request must be fixed |
| UNAUTHENTICATED | Refresh credentials per policy before trying | Never blindly retry with stale credentials |
| PERMISSION_DENIED | Do not retry | Permissions or request must change |
| FAILED_PRECONDITION | Usually do not retry as-is | System state must be fixed first |

`ABORTED` can be used on transaction conflicts when the caller needs to rerun a sequence of operations. `UNAVAILABLE` can fit transient dependency failures. Status mapping must stay consistent between service and client; never use `UNAVAILABLE` to mask every exception, as that triggers unnecessary retries.

## 6. Idempotency keys in Protobuf contracts

For commands that create or mutate data, include an idempotency key in the request:

```proto
message CreateOrderRequest {
  string idempotency_key = 1;
  string customer_id = 2;
  repeated OrderLine lines = 3;
}

message CreateOrderReply {
  string order_id = 1;
  string state = 2;
}
```

The client generates the key once per order-creation intent and preserves it across retries. The server must define the key scope, e.g., tenant + principal + service/method + key. Never use an unscoped global key, because two callers could accidentally collide or probe each other's results.

An idempotency record typically stores:

| Field | Purpose |
| --- | --- |
| scope | Tenant/principal/service-method |
| key | Idempotency key |
| request_hash | Detects same key with different payload |
| state | IN_PROGRESS or COMPLETED |
| response | Stored result for replay |
| created_at/expires_at | Retention management |

If the same key arrives with a different payload, return a clear error such as `INVALID_ARGUMENT` or `FAILED_PRECONDITION` per contract. Never return an old response for a request with different content; doing so misleads the caller about what operation ran.

## 7. Persisting deduplication records atomically with side effects

Idempotency is only effective if the server records the key and executes the side effect under a consistent mechanism. With a relational database, you can put a unique constraint on `scope + key` and store the result in the same transaction:

```sql
CREATE TABLE grpc_idempotency (
    tenant_id       VARCHAR(100) NOT NULL,
    principal_id    VARCHAR(200) NOT NULL,
    method_name     VARCHAR(300) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    request_hash    VARCHAR(128) NOT NULL,
    state           VARCHAR(20) NOT NULL,
    response_bytes  BYTEA,
    created_at      TIMESTAMP NOT NULL,
    expires_at      TIMESTAMP,
    PRIMARY KEY (
        tenant_id,
        principal_id,
        method_name,
        idempotency_key
    )
);
```

This example uses PostgreSQL's `BYTEA` type for response bytes; on other databases, pick the corresponding binary type. Include indexes/constraints matching the scope and a partitioning/retention plan as the table grows.

The transaction should follow these rules:

1. Claim the key via an insert protected by a unique constraint.
2. If the key already exists, read the record under the same scope.
3. Compare `request_hash`; reject if payloads differ.
4. If `COMPLETED`, return the stored response.
5. If the key is new, execute the business mutation.
6. Persist the response and set state to `COMPLETED`.
7. Commit the record and business mutation in the same transaction.

The unique constraint is the final barrier preventing two concurrent requests from claiming the same key. Handle unique-key conflicts according to your database's isolation/transaction semantics. Never merely run `SELECT` then `INSERT` without a constraint, because two requests can both see "not found" and execute side effects concurrently.

PostgreSQL example: a unique violation puts the current transaction into an aborted state; you cannot continue running `SELECT` in that same transaction. Roll back the failed transaction, then read the committed record in a fresh transaction and compare the request fingerprint before replaying the response.

## 8. Spring service pattern for handling idempotency

The service can delegate claim/replay to an `IdempotencyExecutor`. The executor must keep key claiming, business mutation, and response persistence in the same transaction:

```java
@GrpcService
final class OrderGrpcService extends OrderServiceGrpc.OrderServiceImplBase {
    private final IdempotencyExecutor idempotency;
    private final OrderApplicationService orders;

    @Override
    public void createOrder(
            CreateOrderRequest request,
            StreamObserver<CreateOrderReply> observer) {
        try {
            RequestScope scope = RequestScope.from(
                AuthContext.currentPrincipal(),
                "acme.orders.v1.OrderService/CreateOrder");

            CreateOrderReply reply = idempotency.execute(
                scope,
                request.getIdempotencyKey(),
                RequestFingerprint.sha256(request),
                CreateOrderReply.parser(),
                () -> {
                    Order order = orders.create(
                        request.getCustomerId(),
                        request.getLinesList());
                    return CreateOrderReply.newBuilder()
                        .setOrderId(order.id())
                        .setState(order.state())
                        .build();
                });

            observer.onNext(reply);
            observer.onCompleted();
        } catch (IdempotencyKeyConflictException conflict) {
            observer.onError(Status.INVALID_ARGUMENT
                .withDescription("idempotency key reused with different request")
                .asRuntimeException());
        } catch (RuntimeException failure) {
            observer.onError(Status.INTERNAL
                .withDescription("create order failed")
                .asRuntimeException());
        }
    }
}
```

This is a skeleton illustrating integration points; `IdempotencyExecutor` must be implemented with transactions, unique constraints, concurrent claim handling, and response storage/replay as described. Never catch all `RuntimeException`s and always return `INTERNAL` in production: map business errors, database unavailability, and transaction conflicts to statuses defined by the contract.

Fingerprints should be computed from a canonical request representation, not unstable `toString()` output. Consider omitting non-semantic fields such as trace metadata; never include credentials in the hash. Scope must come from the verified principal/tenant, not an arbitrary tenant header.

## 9. Handling duplicate requests while IN_PROGRESS

Two attempts carrying the same idempotency key may arrive nearly simultaneously. The second request sees an `IN_PROGRESS` record. There are several strategies:

- Wait for the first request to finish and then read/replay its response.
- Return a retryable status with backoff guidance so the client retries with the same key.
- Return a conflict error if the contract forbids waiting or requests are incompatible.

Choose one consistent strategy. If you return `UNAVAILABLE`/`ABORTED` for in-flight requests, clients may retry rapidly and add load; use backoff, deadlines, and concurrency limits. If waiting, bound the wait duration and avoid holding database locks longer than needed.

`IN_PROGRESS` records must handle crashes. If the claim commits separately before the business transaction, a server crash can leave a dangling record. You need leases/owner tokens, timeout recovery, or a transaction design ensuring records cannot persist indefinitely without a corresponding operation.

For short database transactions, the simplest approach is claiming the record and running the business mutation in the same transaction; competing requests block on the unique constraint/lock until the first transaction commits or rolls back. For long-running work, use a durable state machine, leases, and worker recovery rather than holding a transaction open throughout long processing.

## 10. External side effects and transactional outbox

A database transaction cannot atomically span an HTTP call to a payment provider, sending an email, or publishing to a message broker. If the server calls an external system and crashes before persisting the idempotency response, a retry can invoke the external system a second time.

Recommended pattern:

1. Within one database transaction, claim the idempotency key, persist business state, and write an outbox event.
2. Commit the transaction.
3. A worker reads the outbox and dispatches the event downstream.
4. Downstream receives a stable operation/event ID and deduplicates.
5. The worker marks the event sent; retries when delivery outcome is unknown.

The outbox guarantees business state and intent to emit the event are persisted atomically. It does not by itself guarantee the broker or downstream receives it only once; consumers/downstreams still must deduplicate by event ID or idempotency key.

For payment providers, pass the logical payment operation's idempotency key if the provider supports it. Never create a fresh key per HTTP/gRPC retry. Store the provider reference and outcome state to reconcile cases where a timeout occurred after the payment succeeded.

## 11. Duplicate responses and client handling

Internal gRPC retries usually hide individual attempts beneath a single logical call and deliver only the call's final result to the application observer. However, if the application explicitly invokes the RPC again after a timeout, each invocation is a separate RPC; multiple attempts may return the exact same server-stored response. If the client treats each response as a brand-new command, UI updates, event handlers, or downstream actions can execute twice.

The client must distinguish:

- A replayed response for the same logical operation: same operation/idempotency key, same result.
- A response for a different operation: different key, even with a similar payload.
- An RPC attempt: a single transport attempt, not a new business operation.

Upon receiving a repeated response, the client can update state idempotently by operation ID. For instance, if the UI already marked order `ord-123` as `CREATED`, a subsequent replayed response merely refreshes existing state rather than adding a second order card or re-sending an email.

For consumers handling message/response events, use an inbox/deduplication table keyed by event ID or operation ID. Record the processed event alongside the business side effect in one transaction. Never rely on an in-memory `Set`, since restarts wipe deduplication state.

## 12. Streaming RPCs and redelivery

Do not mechanically apply unary retry logic to streaming. A stream may have already sent or received partial messages before dropping; opening a fresh stream and resending everything can create duplicates or drop messages.

To recover streams, design an application protocol with:

- A stable stream/session ID.
- A sequence number or offset per message.
- Acknowledgements/checkpoints confirming processed messages.
- A resume token/last acknowledged sequence so the client continues from a safe point.
- Idempotent processing on the server/consumer to handle resent messages.

For example, a client sends events with `stream_id` and `sequence`; the server persists unique key `(stream_id, sequence)` along with processing outcomes. On reconnect, the client sends a resume token so the server knows where to resume. If the final response was lost, the client can query sequence status before resending.

With bidirectional streaming, requests and responses advance independently. Specify which request messages and response messages acknowledgements cover and when the server may purge checkpoints. Never treat client-side `onNext` as proof the server committed a message.

## 13. Retention and security of idempotency records

Idempotency records must live at least as long as clients, proxies, brokers, or operators might redeliver requests. Purging records too early lets old requests re-execute side effects. Keeping them forever makes the deduplication table grow without bound.

Define:

- Retention per operation type and retry/replay SLA.
- TTL safely exceeding the maximum retry window and operational replay window.
- Archiving/partitioning/cleanup jobs that never purge active `IN_PROGRESS` records.
- Key scoping by tenant/principal/method to prevent cross-identity replays.
- Authorization checks on reading cached responses, since responses may hold sensitive data.
- Auditing for key conflicts, replay hits, and cleanup.

Do not log raw idempotency keys if keys could be used to query responses. You may log a truncated hash/fingerprint, though never treat a hash as authentication. When the same key arrives with a different request hash, emit alerts or audit events because this indicates a client bug or abuse.

## 14. Observability for retries and deduplication

Metrics and logs should distinguish logical operations from RPC attempts:

| Signal | Meaning |
| --- | --- |
| rpc_attempt_count | Number of transport attempts |
| retry_count | Retry count by method/status |
| idempotency_replay_count | Requests served from stored responses |
| idempotency_conflict_count | Same key with differing request fingerprint |
| in_progress_duplicate_count | Duplicate requests arriving while operation is running |
| deadline_exceeded_count | Calls exhausting their time budget |
| dedupe_store_latency | Time to claim/look up records |
| outbox_lag | Lag processing downstream side effects |

Attach method, status, attempt number, masked/hashed operation ID, and trace ID following cardinality policies. Never use unbounded idempotency keys or user IDs as metric labels, as they cause high cardinality. Never log request payloads, tokens, or payment details.

A sudden spike in retries alongside `UNAVAILABLE` can signal a dependency outage or retry storm. Rising replay hits can be normal after network instability; rising conflicts usually indicate clients misusing keys or integration bugs.

## 15. Test matrix and practice exercise

| Test case | Expected outcome |
| --- | --- |
| New request with key K | Side effect executes once, response is stored |
| Retry with same key and same payload | Returns stored response, side effect not repeated |
| Same key with different payload | Rejected clearly, no side effect executed |
| Two concurrent requests with same key | Only one request claims and executes |
| First request commits but response is lost | Retry receives old result, no second record created |
| First request rolls back | Retry can execute operation per transaction policy |
| Deadline expires after commit | Client retries same key and receives stored result |
| Audit/outbox publish fails | Business state and outbox stay consistent |
| Downstream receives duplicate event | Consumer deduplicates by event ID |
| Stream reconnect | Resumes from checkpoint, no duplicate processing outside policy |
| Idempotency record TTL expires | Post-retention replay behavior is defined |
| Multiple tenants use same key | Scope prevents cross-tenant replay |

**Exercise:** `OrderService.CreateOrder` creates an order and emits an `OrderCreated` event. Clients occasionally receive `DEADLINE_EXCEEDED` after the database commits. The gateway retries `UNAVAILABLE`; the broker worker can also redeliver the outbox event.

1. Add an idempotency key to `CreateOrderRequest` and preserve it across all retries.
2. Add a unique constraint scoped by tenant, principal, method, and key.
3. Persist the request fingerprint, state, and response in the same transaction as the order.
4. Test two concurrent requests with the same key and verify only one order exists.
5. Simulate a lost response after commit; a retry must receive the existing order ID.
6. Write the outbox event in the same transaction with a stable event ID.
7. Deduplicate the event on the consumer so emails/notifications do not fire twice.
8. Configure retry policies only for appropriate statuses, with finite `maxAttempts`/backoff/deadlines.
9. Verify replay/conflict/retry metrics without logging raw keys or payloads.

**Self-check questions:**

- Why does `UNAVAILABLE` not prove the server has not committed?
- How does a logical operation ID differ from an RPC attempt ID?
- What does a gRPC retry policy control, and what does it fail to guarantee?
- Why do deadlines apply to the entire logical call?
- Which factors must scope an idempotency key?
- Why is a unique constraint necessary when two requests with the same key run concurrently?
- How do you persist business mutations and replayable responses atomically?
- Why do external side effects need an outbox and downstream deduplication?
- How do duplicate responses from application retries differ from internal gRPC retries?
- What sequence/checkpoint fields does streaming need for safe resumption?

**Key takeaway:** Redelivery is a normal consequence of distributed systems; clients cannot always know whether the server committed when a response is lost. Use bounded retries and end-to-end deadlines, keep idempotency keys stable across attempts, deduplicate atomically with side effects, and replay the exact same response. For external events/streams, use an outbox, event IDs, sequences, and checkpoints; design clients to handle repeated responses idempotently.
