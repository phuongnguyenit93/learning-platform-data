# Side Effects and Retries

## 1. Why can retries cause duplicate side effects?

In **SPRING_GRPC**, many RPCs do more than read data—they produce external or persistent changes: creating orders, debiting funds, recording payments, sending device commands, emitting events, or sending notifications. When a client fails to receive a response, it may retry even though the server already executed the side effect.

A typical scenario:

1. The client sends an order creation command.
2. The server writes the order and commits to the database.
3. The connection drops before the response reaches the client.
4. The client sees a timeout or UNAVAILABLE.
5. The client resends the command.
6. If the server treats the second send as a new intent, the system may create two orders.

A timeout only indicates that the caller did not receive a result within the deadline; it does not prove the transaction rolled back. This is an **ambiguous outcome**. Therefore, retries and side effects must be designed together.

The goal is not to promise the network delivers exactly once. The goal is to guarantee that multiple attempts of the same business intent produce only one business effect, through idempotency, transactions, deduplication, and recovery.

## 2. Distinguishing attempt, command, and side effect

These three concepts must be kept distinct:

- **Attempt:** a single RPC transmission. One command may have multiple attempts due to retries.
- **Command:** the caller's stable business intent, e.g., "create an order for this cart".
- **Side effect:** the actual change produced, such as an order row, payment capture, or emitted event.

A retry creates a new attempt, not automatically a new command. The client must maintain a stable identifier for the command across resends.

A naturally idempotent operation can be repeated without changing the effective outcome beyond the first execution, such as setting a configuration state to a specific value. Operations like "increment balance", "create a new order", or "charge card" are generally not naturally idempotent.

For non-idempotent operations, an idempotency key or operation ID is required. The key must represent a business intent, not a single network invocation.

## 3. Failure windows that govern safe retries

| Failure Point | Possible Server State | What the Client Knows | How to Handle |
| --- | --- | --- | --- |
| Before server receives request | No side effect yet | No response | Retry is normally safe |
| After receipt, before business execution | No side effect if not started | May only see timeout | Retry with same command identity |
| Inside transaction, before commit | Transaction may roll back | Client is uncertain | Retry with same key; server resolves outcome |
| After commit, before response | Side effect already exists | Client only sees timeout/UNAVAILABLE | Replay stored result, do not re-execute |
| After response reaches client | Side effect completed | Client knows result | Do not retry unless caller has a new intent |

The hardest window is between commit and response. A database commit and sending a response over HTTP/2 are not a single atomic operation. The server cannot roll back a commit simply because the socket closed.

Idempotency design must protect both the case where the first request never committed and the case where it committed but the response was lost.

## 4. Retry policies do not replace idempotency

gRPC has a client-side retry mechanism when a method has a retry policy configured and the status falls within retryable codes. Some retries can be performed transparently by the runtime when a call has not yet been processed or response headers have not yet been received; configured retry policies can issue new attempts up to bounded attempt counts and backoff.

However, a retry policy only governs resending the RPC. It does not know whether the database committed or whether a payment provider charged the card. Therefore:

- Only enable retries for methods with retryable semantics.
- Commands with side effects need idempotency on the server or downstream.
- Never treat UNAVAILABLE as proof the server did not execute.
- Never retry unboundedly or across multiple layers without counting total attempts.
- Do not use hedging for side effects without safe deduplication.

Transport retries, application retries, proxy retries, and queue redeliveries can compound. If each layer retries 3 times, one command can generate far more attempts than intended. Designate one primary retry coordinator and record attempt counts/correlation.

## 5. Classifying statuses before retrying

Not every status should be retried:

| gRPC Status | Meaning for Retries | Typically Suitable Action |
| --- | --- | --- |
| UNAVAILABLE | May be transient; outcome may be uncertain | Retry with the same idempotency key and backoff |
| DEADLINE_EXCEEDED | Caller ran out of time; server may have committed | Query/retry with same key, do not generate a new key |
| ABORTED | Conflict in workflow, e.g., optimistic locking | Re-read state and re-run the entire use case |
| RESOURCE_EXHAUSTED | Quota or resource overload | Retry only if contract indicates recoverable; honor RetryInfo/backoff |
| FAILED_PRECONDITION | Current state forbids the operation | Wait/fix precondition; do not retry blindly |
| INVALID_ARGUMENT | Invalid request | Fix input before resending |
| NOT_FOUND | Resource does not exist | Do not retry as a network error |
| PERMISSION_DENIED | Unauthorized | Do not retry until permissions change |
| CANCELLED | Caller canceled | Stop unnecessary work; do not assume committed work rolled back |
| INTERNAL/UNKNOWN | Insufficient information to conclude retry is safe | Follow contract and telemetry; avoid blanket retries |

A status is a signal to the caller, not complete proof of commit state. For commands with side effects, an idempotency key or operation-status endpoint is what resolves uncertain outcomes.

## 6. Designing idempotency keys for commands

The client generates the key before the first attempt and keeps it across retries:

```proto
message CreateOrderRequest {
  string customer_id = 1;
  repeated OrderLine items = 2;
  string idempotency_key = 3;
}
```

Rules:

- One order creation intent uses one key.
- Retries of the same intent preserve the same key and payload semantics.
- A user intentionally creating a new order must use a new key.
- Keys should have sufficient entropy or derive from a unique operation ID.
- Scope keys by tenant, client, and RPC method to prevent namespace collisions.
- Never use keys as authentication tokens or proof of access rights.

The server must check authorization on every attempt, even when returning a stored result. A key must never allow another caller to read the command's outcome.

If requests carry per-attempt fields such as trace IDs or transport timestamps, exclude them from the business fingerprint. The fingerprint includes only data affecting the side effect.

## 7. Atomic idempotency: committing business data and command result together

For short commands, the reliable pattern stores the idempotency record, business update, and result in the same transaction:

1. Atomically claim the key via a unique constraint.
2. If the key is new, execute the business operation.
3. Save the operation/result reference.
4. Commit business data and the idempotency record together.
5. Only after commit, send the gRPC response.

Minimum schema:

| Field | Role |
| --- | --- |
| tenant_id, client_id, method | Key scope |
| idempotency_key | Command identifier |
| request_hash | Detects key reuse with a different payload |
| state | PROCESSING/COMPLETED/FAILED if workflow needs it |
| operation_id | Stable business ID |
| result | Data to replay |
| created_at, expires_at | Retention |

A unique constraint on the key scope is mandatory. A SELECT check followed by INSERT without a unique constraint still has a race condition when two attempts arrive concurrently.

Application service pseudo-flow:

```java
@Transactional
public CreateOrderResult create(CreateOrderCommand command) {
    ClaimResult claim = idempotency.claim(command.key(),
                                           fingerprint(command));

    if (claim.isExisting()) {
        return claim.replayResultOrRejectFingerprintMismatch();
    }

    Order order = orderRepository.save(Order.create(command));
    CreateOrderResult result = CreateOrderResult.from(order);

    idempotency.complete(command.key(), result);
    return result;
}
```

The adapter emits the response only after the transactional call through the Spring proxy returns. If the transaction rolls back, both business data and the new idempotency record roll back. If commit succeeds but the response is lost, the retry finds the COMPLETED record and replays the result.

The claim implementation must use an atomic primitive suited to the database. If a duplicate-key error marks the current transaction rollback-only, do not catch the exception and query within the same transaction; roll back and look up in a new transaction, or use insert-if-absent/upsert semantics properly.

## 8. Request fingerprints and key mismatches

Same key with a different payload must be rejected. Otherwise, a client could accidentally reuse Order A's key for Order B and receive A's result as though B had been created.

Build the fingerprint from canonical business input:

- Include customer, items, quantities, amounts, and fields affecting side effects.
- Normalize representation per contract before hashing.
- Exclude trace IDs, deadlines, retry counts, or transport metadata.
- Store the fingerprint version if canonicalization rules might evolve.
- Use a strong hash like SHA-256 over a stable encoding.

If fingerprints match, the request is a retry of the same command. If fingerprints differ, return a conflict/invalid usage error per contract; never run a new side effect under an old key.

Do not blindly hash raw Protobuf bytes if field ordering, unknown fields, or default representations can vary while carrying identical business semantics. Canonicalization must reflect semantics, not just wire bytes.

## 9. Concurrent duplicate requests and in-progress commands

Two attempts with the same key may land on different replicas. The mechanism must operate in a database/shared store, not rely on synchronized blocks or an in-memory map on one instance.

For short transactions:

- The first attempt claims the key and executes the operation.
- The second attempt is coordinated by the unique constraint; it waits on the first transaction or receives a conflict.
- If the first attempt commits, the second reads the COMPLETED record and replays.
- If the first attempt rolls back, the second can claim and execute.
- If waiting exceeds the deadline, the caller retries with the same key later.

For long workflows, you can commit a separate PROCESSING reservation and run a worker. That requires lease expiry, owner tokens, heartbeats, takeover, and recovery. A worker may re-run after a lease timeout, so side effects must still be idempotent. Provide an operation-status query API instead of keeping the client's RPC open for long periods.

Never leave a PROCESSING record stuck permanently after a crash. Recovery jobs must find expired leases and decide whether to retry, mark failed, or route to manual handling.

## 10. Side effects inside vs. outside the database

### Side effects in the same database

If creating an order, updating inventory, and saving the idempotency result live in the same database, run them in a single transaction. Either everything commits or everything rolls back.

When multiple tables are involved, preserve invariants using constraints, locking, or optimistic versioning. Never emit a success response before commit completes.

### Side effects in external systems

A database transaction cannot roll back an email already sent, a payment provider already charged, or a message already published. Do not call external systems inside a transaction assuming a database rollback will undo that side effect.

Options:

- Propagate the idempotency key to the payment/provider if downstream APIs support it.
- Write an outbox event in the same transaction as the business update.
- Use a worker to retry publishing with a stable event ID.
- Consumers deduplicate by event ID/operation ID.
- For multi-service workflows, use sagas and compensation.

## 11. Transactional outbox for events and notifications

If a command updates an order and needs to emit OrderCreated:

1. Within the transaction, create the order.
2. Within the same transaction, create the idempotency result.
3. Within the same transaction, write the outbox event with a stable event ID.
4. Commit.
5. A worker reads the outbox and publishes.
6. The worker marks it sent or retries per policy.
7. Consumers deduplicate events if the broker redelivers.

Outbox ensures the business update and event-emission intent are saved together. It does not guarantee the broker receives it only once: the worker can publish and crash before marking sent. Therefore consumers must be idempotent.

Do not send emails directly inside a transaction. Instead, write the notification intent to the outbox; a worker sends with a provider idempotency key if supported, or records delivery receipts to reduce duplicates.

## 12. Sagas and compensation for multi-service workflows

When a command produces side effects across multiple services/databases, no simple single ACID transaction spans all of them.

Order placement example:

1. Reserve inventory.
2. Authorize payment.
3. Create shipment.
4. Confirm order.

If step 3 fails after payment was authorized, the system needs compensation such as releasing inventory and voiding authorization. This is a saga.

Each saga step requires:

- A stable operation ID.
- Durable state transitions.
- Idempotent commands/consumers.
- Bounded retries with backoff.
- Explicit compensation for completed steps.
- Dead-letter/manual recovery when automatic recovery fails.

Compensation is a new business action to bring the system to an acceptable state; it is not a cross-service database rollback. The system may briefly stay in intermediate states such as PAYMENT_AUTHORIZED or COMPENSATING; the API must represent these states clearly.

## 13. Retry policies, backoff, and overall deadline

Retries must limit both attempts and duration. Exponential backoff with jitter reduces the chance of many clients retrying in lockstep:

```text
delay = min(max_delay, base_delay × 2^attempt) + random_jitter
```

The total budget must stay within the RPC/caller deadline. Each attempt uses the remaining deadline rather than resetting to an unlimited full timeout.

Operational rules:

- Only retry statuses defined by the contract as transient/retryable.
- Keep the idempotency key and request semantics unchanged.
- Honor retry-after/RetryInfo if returned by the server.
- Bound attempts, total elapsed time, and concurrency.
- Use circuit breakers/load shedding when a dependency is overloaded.
- Avoid simultaneous retries across client, gRPC service, proxy, and worker without budgeting the combined total.
- Never retry side effects lacking idempotency/deduplication.

Retry storms can push an already stressed database or downstream service deeper into overload. Under high load, return appropriate RESOURCE_EXHAUSTED/UNAVAILABLE and instruct clients to back off instead of accepting immediate additional attempts.

## 14. Streaming RPCs and replay limits

Unary commands have a finite request so the client can resend the exact request/key. With client-streaming or bidirectional streaming, the client may have sent many messages before the connection drops. You cannot assume the runtime replays the whole stream at the application layer or knows how far the server processed.

Designing streams with side effects requires a resume protocol:

- Each stream has a session/upload ID.
- Each message has a sequence number and idempotency key or stable message ID.
- The server persists receipts/checkpoints in the same transaction as side effects.
- The client reconnects and resumes from the first unacknowledged sequence.
- Duplicate sequences with matching payloads replay the receipt; matching sequences with different payloads trigger a conflict.
- Expiry/cleanup handles abandoned sessions.

For streams carrying multiple independent commands, commit each command and ack after commit. If the stream terminates with an error, already-committed commands persist; the API must document partial commits. If the entire batch must be atomic, use staging/finalize instead of holding a transaction open across the stream.

## 15. Observability and auditing

To investigate duplicate side effects, record:

- Operation ID/idempotency key in a safe or hashed form.
- RPC method and attempt number.
- Claim outcome: NEW, REPLAY, IN_PROGRESS, KEY_MISMATCH.
- Business transaction outcome: committed/rolled back.
- Outbox event ID and delivery attempts.
- Saga state and compensation outcome.
- gRPC status, remaining deadline, and retry delay.

Do not put raw keys, sensitive payloads, or customer/payment data into metric labels. Metrics should use bounded-cardinality labels such as method, outcome, and dependency. Logs/audit trails require appropriate access control, retention, and masking.

Useful indicators include duplicate request rate, replay count, key mismatch count, idempotency conflicts, outbox backlog, publish retries, saga stuck duration, and compensation failures.

## 16. Testing side effects and retries

Testing a single happy path is not enough. Test failure windows and concurrency:

| Test | What to verify |
| --- | --- |
| Retry before server execution | Command executes once |
| Transaction rolls back before commit | Subsequent attempt can execute per policy |
| Commit succeeds, response drops | Retry with same key replays result |
| Two concurrent requests with same key | Only one business side effect |
| Same key, different payload | Rejected; no new side effect |
| Outbox publish then worker crash | Event may be resent, but consumer deduplicates |
| Payment/provider timeout | Retry uses the same downstream idempotency key |
| Saga failure mid-flow | Compensation restores workflow to valid state |
| Deadline expires during retries | Total attempts stop within budget |
| Streaming disconnect | Resuming from checkpoint does not repeat committed commands |

Use two independent transactions/threads to reproduce duplicate races. Use fault injection to drop connections after commit but before response. Test against a real gRPC server and production-like database to verify unique constraints, transaction rollbacks, and status mapping.

## 17. Review checklist

- Commands with side effects have stable identities across attempts.
- Clients keep the same idempotency key across retries of the same intent.
- Server validates fingerprints and rejects key reuse with a different payload.
- Unique constraints protect keys on the shared database/store.
- Claim, business update, and stored result commit atomically whenever possible.
- Responses are sent only after commit.
- Timeouts/UNAVAILABLE are treated as potentially uncertain outcomes.
- Retries have status policies, backoff/jitter, attempt limits, and an overall deadline.
- Side effects without idempotency/deduplication are never retried.
- External effects use downstream keys, outbox, or saga/compensation.
- Consumers deduplicate events; never assuming exactly-once broker delivery.
- Streaming has sessions, sequences, receipts, and a resume protocol.
- Partial commits and workflow states are clearly documented.
- Metrics/logs support tracing without exposing sensitive data.
- Fault-injection and concurrency tests cover all critical failure windows.

In **SPRING_GRPC**, a retry only creates another attempt; it does not prove the previous attempt failed to commit. Identify commands with an idempotency key, persist side effects and results in the same transaction, and emit responses only after commit. For events and external systems outside the database, use outbox, downstream deduplication, or sagas. When a stream disconnects, use sequences/checkpoints to resume instead of assuming the whole stream can safely replay.
