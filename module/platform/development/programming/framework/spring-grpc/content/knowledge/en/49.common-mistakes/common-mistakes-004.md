# Retrying Non-Idempotent Commands

## 1. Common mistake: retrying a command as if it never ran

In **SPRING_GRPC**, many RPCs execute commands with side effects: creating an order, debiting an account, capturing a payment, increasing a balance, issuing a coupon, or sending a command to a device. A dangerous mistake is when a client receives a timeout/`UNAVAILABLE` error and resends the command as a brand-new request without any mechanism to recognize the previous attempt.

For example, a client calls `DebitAccount` with `amount = 100`:

1. The server receives the request and debits 100.
2. The database commit succeeds.
3. The response is lost because the connection drops.
4. The client receives `DEADLINE_EXCEEDED`.
5. The client retries with the same content, but the server treats it as a new command.
6. The account is debited another 100.

The client only knows it did not receive a response; it does not know whether the server committed or not. This is an **ambiguous outcome**. Retrying a non-idempotent command without deduplication can duplicate side effects.

Key principle: **a retry is a new attempt of the same business intent, not a new intent**. If the server cannot recognize that, the client cannot infer the outcome from a timeout alone.

## 2. How do idempotent and non-idempotent operations differ?

An idempotent operation can be executed multiple times with the same intent without changing the final effective result after the first execution. For example, setting a device state to OFF is usually idempotent.

A non-idempotent operation produces additional effects each time it executes:

- Increasing a balance by 100.
- Creating a new order.
- Charging a card again.
- Sending an email or SMS.
- Issuing a new voucher.
- Incrementing a counter or issuing a physical command.

Do not judge idempotency solely by HTTP/gRPC method name or identical request payloads. Examine the side effects and business semantics. An RPC named `Update` can be non-idempotent if it accumulates a value; an RPC named `Create` can be safe when the server deduplicates by an operation key.

## 3. A timeout does not prove the server did not execute

A command can fail at several points:

| Failure window | Possible state | Safe action |
| --- | --- | --- |
| Request has not reached server | No side effect yet | Can resend with same command identity |
| Server received but has not started processing | No side effect yet | Retry per contract |
| Transaction is running and rolls back | No committed changes | Retry can execute |
| Database committed, response has not reached client | Side effect already exists | Replay result, do not re-execute |
| Downstream executed, downstream response lost | External side effect may already exist | Query/retry using downstream idempotency key |
| Response reached client | Caller knows the outcome | Only send a new command for a new intent |

`DEADLINE_EXCEEDED` only tells the caller it ran out of wait time. `UNAVAILABLE` only tells the caller the call did not complete because the service/transport was unavailable. Neither is proof that the transaction did not commit.

In particular, committing to the database and sending the gRPC response are not part of the same transaction. The server can commit successfully and then fail in the process or network before the client receives the response.

## 4. Why is blind retrying more dangerous in multi-layer systems?

A command can be retried in multiple places:

- The client application retries on its own.
- A gRPC retry policy creates a new attempt when the call remains eligible for retry.
- An API gateway or proxy has a retry policy.
- A worker/queue redelivers the command.
- A downstream service retries calls to a provider.

If each layer retries without a consistent command identity propagated end-to-end, the number of side effects can multiply exponentially. For example, 3 client retries, 2 gateway retries, and 3 worker retries can generate far more attempts than intended.

Retries must have one clear owner per workflow. Every layer that retries must preserve the same operation ID/idempotency key and obey a shared attempt/deadline limit.

A gRPC retry policy governs transport attempts; it does not provide exactly-once semantics for business operations. The runtime may retry under conditions where a call is still retryable, but the application must not rely on internal retry details to protect side effects.

## 5. When should you NOT retry?

Do not automatically retry a non-idempotent command if the server/downstream lacks a deduplication mechanism and the outcome may have already occurred.

Cases where blind retries should generally be avoided:

- No idempotency key or stable operation ID exists.
- A payment provider does not support idempotency and has no transaction lookup API.
- A device command may already have been executed without a command sequence/status.
- It is impossible to determine whether a transaction committed.
- A new request could create a new business action instead of querying the previous result.

When the outcome is unclear, prefer querying operation status, reconciling via a business reference, or routing to a reconciliation workflow. If the contract provides no verification path, stop automatic retries and report an indeterminate status to the caller/operation owner.

Do not ask the user to click a button again to submit a new request with a new key when the old command may have succeeded. The UI should preserve command identity and allow checking the result.

## 6. Generate the operation ID or idempotency key before the first attempt

The client generates the key once for a single business intent, before sending the first RPC:

```proto
message DebitAccountRequest {
  string account_id = 1;
  int64 amount = 2;
  string idempotency_key = 3;
}

message DebitAccountReply {
  string operation_id = 1;
  int64 new_balance = 2;
}
```

Rules:

- The same debit intent uses the same key across all retries.
- A user creating a new debit command must use a new key.
- The key must persist across process restarts if the client can retry after restarting.
- Scope the key by tenant, client/application, and RPC method.
- Do not generate the key inside an interceptor per attempt.
- Do not use the key as a credential or replacement for authorization.

If the client generates a new UUID on every retry, the server sees distinct commands and cannot deduplicate. The key must be created at the boundary where the business intent is formed and retained long enough for the retry/recovery window.

## 7. Request fingerprints prevent reusing a key for a different payload

The server must detect cases where the same key is sent with changed command contents. Build a fingerprint from canonical business inputs:

- Target resource/aggregate.
- Amount, currency, and operation type.
- Fields that determine side effects.
- Semantics version if the command contract evolves.

Do not include trace ID, retry count, deadline, or transport metadata in the fingerprint. Canonicalize the representation before hashing so the same intent yields a stable fingerprint.

When the key already exists:

- Same fingerprint: this is another attempt of the same command; return the stored result or in-progress status.
- Different fingerprint: reject because the key was already used for another command.

Never return the old command's result when the new payload differs. This is a critical client bug that should be logged and measured separately.

## 8. Deduplicate atomically within the business transaction

For short commands whose side effects reside in the same database, store the idempotency record and business update in the same transaction.

The record table can store:

| Field | Role |
| --- | --- |
| tenant_id/client_id/method | Scope key |
| idempotency_key | Intent identifier |
| request_hash | Fingerprint |
| operation_id | Stable business ID |
| result/status | Replayable result |
| created_at/expires_at | Retention period |
| state | State if required by workflow |

Create a unique constraint on the scoped key. A separate SELECT check followed by an INSERT is unsafe because two concurrent requests can both observe the key as absent.

Pseudo-flow:

```java
@Transactional
public DebitResult execute(DebitCommand command) {
    String hash = fingerprint(command);

    boolean claimed = idempotencyRepository.insertIfAbsent(
        command.tenantId(),
        command.clientId(),
        "accounts.v1.AccountService/Debit",
        command.idempotencyKey(),
        hash
    );

    if (!claimed) {
        IdempotencyRecord record =
            idempotencyRepository.findRequired(command.scope());

        if (!record.requestHash().equals(hash)) {
            throw new IdempotencyKeyReuseException();
        }

        return record.completedResult();
    }

    Account account = accounts.findRequired(command.accountId());
    account.debit(command.amount());

    DebitResult result = DebitResult.from(account);
    idempotencyRepository.complete(command.idempotencyKey(), result);
    return result;
}
```

`insertIfAbsent` must be an atomic operation protected by a unique constraint, such as a database-specific insert-on-conflict. Do not implement it as an unlocked SELECT followed by an INSERT.

When the transaction commits, the business update and idempotency result coexist. If the transaction rolls back, both roll back together. If the commit succeeds but the response is lost, a retry with the same key finds the completed record and replays the result.

With a duplicate-key exception, the transaction may already be marked rollback-only. Do not catch the exception and assume you can keep querying inside that same transaction; use an appropriate insert-if-absent or roll back and look up in a new transaction.

## 9. Handling two concurrent requests with the same key

A client may retry while the first attempt is still running, or two requests with the same key may hit two different replicas. An in-memory map or `synchronized` block in a single JVM is insufficient protection.

For short transactions, the unique index in the database acts as the shared coordination point:

1. The first attempt inserts the idempotency key.
2. The second attempt hits the unique key and waits for the first transaction's outcome or receives a conflict per database behavior.
3. If the first attempt commits, the second attempt reads the record and replays it.
4. If the first attempt rolls back, the second attempt can claim and execute it.
5. If waiting exceeds the deadline, the caller retries with the same key.

For long-running work, a separate `PROCESSING` reservation can be committed. In that case, there must be a lease expiry, owner token, heartbeat, and recovery after worker crashes. A takeover worker may re-run, so side effects must still be deduplicated. Never leave a `PROCESSING` record stuck forever.

## 10. Downstream must also receive the same command identity

If the server deduplicates in its database and then calls a payment provider, without sending an idempotency key to the provider, a double charge can still occur if the provider processed the request and the response was lost.

Propagate operation identity downstream:

- Use the same operation ID or a separate key stably mapped per provider.
- Persist the provider transaction/reference ID.
- Retry with the same provider key; do not generate a new key per attempt.
- If the provider offers a status query API, use it to resolve ambiguous outcomes.
- If the provider does not support deduplication, build reconciliation/manual review instead of retrying blindly.

Do not reuse one key across different operations such as authorize, capture, and refund. Each type of side effect needs its own identity or a key derived per operation type.

## 11. Outbox and sagas for side effects outside the database

A database transaction cannot roll back a payment provider, email, broker, or external service.

If a command must emit an event, write the business state, idempotency result, and outbox event in the same transaction. A dispatcher publishes after commit with a stable event ID; consumers deduplicate because broker delivery can repeat.

For multi-service workflows, use a saga:

- Each step has an operation ID and durable state transitions.
- Commands/consumers at each step are idempotent.
- Retries are bounded and use backoff.
- Completed steps have corresponding compensation when the workflow fails.
- Include timeouts, stuck-state detection, and manual recovery.

Compensation is a new business action, not a cross-database rollback. For example, voiding an authorization or releasing inventory must have its own identity and its own idempotency.

## 12. Retry policies and gRPC status codes

Do not retry every status:

| Status | Handling for non-idempotent commands |
| --- | --- |
| UNAVAILABLE | Outcome may be unknown; retry with same key only if server deduplicates |
| DEADLINE_EXCEEDED | Do not assume rollback; query status or retry with same key |
| ABORTED | Re-read state and re-run workflow per contract; do not repeat old write |
| RESOURCE_EXHAUSTED | Back off/respect RetryInfo; do not retry aggressively |
| FAILED_PRECONDITION | Wait/fix business state; do not retry blindly |
| INVALID_ARGUMENT | Fix request; do not retry the exact payload |
| PERMISSION_DENIED | Do not retry until permissions change |
| NOT_FOUND | Handle missing resource per contract, do not retry as a transport error |
| CANCELLED | Stop cancellable work; committed side effects still remain |

`DEADLINE_EXCEEDED` and `UNAVAILABLE` do not tell you for sure whether the server committed. For idempotent operations, keep the same key across retries. For operations without deduplication, use status queries/reconciliation.

## 13. Backoff, deadlines, and attempt limits

Retries require exponential backoff and jitter to avoid many clients retrying at the exact same instant:

```text
delay = min(max_delay, base_delay × 2^(attempt - 1))
wait  = delay + random_jitter
```

Configure:

- Maximum attempts.
- Maximum elapsed time.
- Overall deadline for the command.
- Retry concurrency limits.
- Transient vs. permanent error classification.
- Circuit breaker or load shedding when a dependency is overloaded.

Before each attempt, check the remaining deadline. Do not grant a fresh full timeout on every attempt. Do not retry simultaneously at client, server, proxy, and worker without accounting for total execution attempts.

If the retry budget is exhausted while the outcome remains unknown, return an indeterminate result per API contract and provide the operation ID for lookup. Never switch to a new key just to "try one more time."

## 14. Streaming commands cannot be retried like unary RPCs

With client-streaming or bidirectional streaming, the client may have sent several messages before the connection drops. The server may have already committed part of the command stream.

An explicit resume protocol is needed:

- Stable stream/session ID.
- Sequence number for each command/chunk.
- Idempotency key or message ID for each side effect.
- Receipt/checkpoint stored in the same transaction as the side effect.
- Client reconnects and resumes sending from unacknowledged sequence numbers.
- Duplicate sequence with same payload replays the receipt; differing payload is rejected.

If the stream processes each message independently, commit and acknowledge per message; an error at the end of the stream does not roll back already-committed messages. If atomicity across the whole batch is required, use staging/finalize rather than a transaction held open across the network.

Do not automatically open a new stream and replay all messages unless the server deduplicates by sequence.

## 15. When a command cannot be made idempotent

Some physical side effects or legacy systems do not support idempotency, operation lookup, or shared transactions. In such cases, acknowledge the limitation:

- Do not automatically retry after errors with an unknown outcome.
- Log the operation attempt and correlation reference before sending.
- Query status through an independent channel if available.
- Reconcile against the system that owns the side effect.
- Route indeterminate cases to a manual review queue.
- Design compensation if business rules permit.

Do not claim exactly-once delivery without durable deduplication where the side effect occurs. "Sending once" on the client cannot guarantee the server or provider executed once when a response is lost.

## 16. Testing to prove retries do not duplicate side effects

| Scenario | Assertion |
| --- | --- |
| Retry before server receives request | Only one effective command |
| Commit then drop response | Retry with same key replays result |
| Transaction rollback | Next attempt can claim key and execute |
| Two concurrent requests with same key | Only one business side effect |
| Same key, different payload | Rejected |
| Provider processes but response is lost | Retry with same downstream key does not double-charge |
| Outbox publish then crash | Consumer deduplicates event |
| Saga fails mid-workflow | Compensation runs safely and is retryable |
| Deadline expires during retries | Does not exceed deadline/attempt budget |
| Stream disconnect | Resume does not repeat committed sequences |
| No deduplication available | Client does not auto-retry ambiguous outcomes |

Use two independent transactions/threads to reproduce duplicate races. Fault injection must accurately simulate the failure window after commit and before response; throwing an exception inside the transaction does not substitute for this scenario.

Verify database state, provider references, outbox/inbox tables, and gRPC statuses. Testcontainers or a provider test environment helps verify unique constraints and real semantics.

## 17. Review checklist

- Network attempts are distinguished from business command intents.
- Non-idempotent commands are not auto-retried when outcomes may be unknown.
- Keys are generated once before the first attempt and preserved across all retries.
- Fingerprints detect key reuse with differing payloads.
- Unique constraints/deduplication reside in a shared durable store.
- Idempotency record and business update commit in the same transaction.
- Responses are sent only after commit; retries after lost responses replay the stored result.
- Concurrent duplicate requests are handled in the database, not just in memory.
- Downstream providers receive a stable key or support status lookup/reconciliation.
- External events use an outbox; consumers deduplicate.
- Multi-service workflows have sagas/compensation when needed.
- Retryable statuses, backoff, deadlines, and attempt budgets are defined.
- Streaming includes sequence numbers, receipts, and a resume protocol.
- When deduplication is impossible, blind retries stop and outcomes are reconciled.
- Fault-injection tests cover commit-before-response and duplicate concurrency.

In **SPRING_GRPC**, retrying a non-idempotent command can duplicate side effects because a timeout does not prove the server failed to commit. Keep a single command identity across all attempts, deduplicate atomically within the business transaction, and propagate that identity to external systems. If the outcome cannot be determined or deduplicated, query or reconcile rather than issuing a new request. For streaming, sequence numbers and checkpoints are required for safe resumption.
