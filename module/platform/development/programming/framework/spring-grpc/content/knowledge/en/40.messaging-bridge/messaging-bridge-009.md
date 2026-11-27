# Command Idempotency

## Learning Objectives

After this lesson, you will be able to:

- Explain why commands sent over gRPC or messaging can be processed multiple times.
- Distinguish idempotency from retries, message deduplication, and exactly-once delivery.
- Design command IDs/idempotency keys clearly scoped by tenant and operation.
- Generate request fingerprints to detect key reuse with a different payload.
- Use unique constraints and transactions to apply a business effect at most once in the database.
- Combine the command record, business mutation, and transactional outbox in the same transaction.
- Handle concurrent duplicate requests, in-progress commands, transient failures, and final business failures.
- Design consumer inbox/deduplication when the broker provides at-least-once delivery.
- Protect external side effects using downstream idempotency keys or sagas.
- Choose retention, observability, and concurrency tests for an idempotency contract.

## 1. Why Do Commands Need Idempotency?

In **SPRING_GRPC**, clients send commands via unary RPC or streaming RPC to request an action with side effects—such as creating an order, recording a payment, reserving inventory, or updating state. The service may commit the transaction successfully while the response is lost due to a network timeout, client cancellation, or closed connection before the result arrives.

The client cannot tell for sure whether the command has not run or has already succeeded. If it resends the command as a new request, the service could create a second order, charge twice, or emit two identical events.

**Command idempotency** ensures that sending the same logical command multiple times produces at most one business effect, while allowing retries to receive the previously recorded result. A command may travel over gRPC, be saved to a database, be published via an outbox to a broker, and be processed by a consumer. Each boundary needs a stable identifier and an appropriate deduplication mechanism.

Example: a client sends `PlaceOrder` with command ID `C-123`. The server creates order `O-900` and commits, but the response times out. The client resends `C-123` with the same content. The server recognizes the command already completed and returns the result for `O-900`; no new order is created.

~~~mermaid
sequenceDiagram
    participant C as gRPC Client
    participant G as gRPC Service
    participant DB as Database
    participant O as Outbox Relay
    participant B as Broker
    C->>G: Command ID C-123
    G->>DB: Insert command key + update order + outbox
    DB-->>G: Commit
    G--xC: Response lost
    C->>G: Retry C-123 with same payload
    G->>DB: Lookup command key
    DB-->>G: Completed + stored result
    G-->>C: Replay previous result
    O->>B: Publish event with stable event ID
~~~

Idempotency is especially critical when a system uses retries, load balancers, broker redelivery, or client reconnects. It is part of the command contract, not merely an exception-handling trick.

## 2. Idempotency Is Not the Same as Exactly-Once Delivery

Distinguish these concepts:

| Concept | Meaning | Limitations |
| --- | --- | --- |
| Retry | Resending when no result was received or a recoverable error occurred | Can create duplicate requests |
| Idempotency | Repeating the same operation creates no additional business effect | Requires keys, storage, and replay rules |
| Message deduplication | Identifying messages already processed by a consumer | Scope is usually per consumer/subscription |
| At-least-once delivery | Messages are delivered at least once, possibly multiple times | Consumers must tolerate duplicates |
| Exactly-once delivery | System guarantees single delivery within a defined scope | Does not automatically guarantee end-to-end side effects across multiple systems |

In a messaging bridge, brokers typically favor at-least-once delivery to avoid losing messages. A producer may publish successfully yet crash before recording published status; the relay will publish again. A consumer may commit its business transaction and then lose the acknowledgement, causing the broker to redeliver.

Therefore, the practical goal is **effectively-once business processing within a controlled transaction scope**: using stable command/event IDs, unique constraints, and transactions so side effects commit only once. Never claim the entire chain gRPC → database → broker → consumer has exactly-once semantics if those systems do not share a single transaction coordinator.

## 3. Command IDs and Idempotency Keys

Every command needs an identifier that stays stable across retries. You can place a command ID in the protobuf contract or use a metadata key per API convention. For business commands, an explicit field in the request is usually easier to validate, version, and log.

Example contract:

~~~proto
message PlaceOrderCommand {
  string command_id = 1;
  string customer_id = 2;
  repeated OrderLine lines = 3;
  string currency = 4;
}

message PlaceOrderResult {
  string command_id = 1;
  string order_id = 2;
  string outcome = 3;
}

service OrderCommandService {
  rpc PlaceOrder(PlaceOrderCommand) returns (PlaceOrderResult);
}
~~~

The client generates the command ID before the first send and keeps the exact same ID across all retries of the same operation. Never generate a new UUID inside each retry call, as the server will treat each UUID as a brand-new command.

The command ID is not the caller's identity. The server must extract tenant/client identity from the verified authentication context; never trust an arbitrary tenant ID in the request to scope deduplication.

A key should be scoped by at least:

- Authenticated tenant or owner.
- Operation or command type.
- Command ID/idempotency key.

For example, the unique key is `(tenant_id, command_type, command_id)`. This prevents collisions between two tenants and prevents accidentally reusing a `PlaceOrder` key for a `CancelOrder` operation.

Do not use an access token as an idempotency key. Tokens rotate, contain sensitive material, and do not represent a stable business operation.

## 4. The Same Key Must Accompany the Same Request

A dangerous bug occurs when a client sends command A with key K, then reuses K for command B. If the server only checks whether the key exists and replays the old result, the caller can receive the wrong response or mask an integration bug.

Upon receiving a command, the server should compute a **request fingerprint** from a canonical representation of the business fields. Store the fingerprint alongside the idempotency record. When the key already exists:

- Same fingerprint: this is a retry of the same command; replay the result or return the in-progress state.
- Different fingerprint: key was improperly reused; reject explicitly.
- Cannot determine fingerprint: never guess; report a contract error.

The fingerprint should use SHA-256 over a normalized canonical payload. Explicitly choose which fields participate in the fingerprint: command type, resource ID, amount, currency, line items, and options that alter side effects. Do not include transport metadata such as trace ID, deadline, or retry count in the fingerprint.

Do not default to hashing raw protobuf bytes directly if serialization can vary across schema evolution, field presence, or canonicalization. For the same logical command, the fingerprint must remain stable across supported client versions. You can construct a versioned canonical DTO/encoding and hash that representation.

Example:

~~~java
byte[] fingerprint = sha256(
        canonicalCommandEncoder.encode(command));
~~~

Do not log sensitive payloads merely to debug fingerprints. You can log the hash and redacted audit fields.

## 5. Storing Idempotency Records with a Unique Constraint

Idempotency requires durable storage. An in-memory map is only valid within one process; a restart or routing a request to another replica forgets history.

A minimal table might look like:

~~~sql
CREATE TABLE command_deduplication (
    tenant_id       VARCHAR(100) NOT NULL,
    command_type    VARCHAR(120) NOT NULL,
    command_id      VARCHAR(120) NOT NULL,
    request_hash    CHAR(64) NOT NULL,
    state           VARCHAR(24) NOT NULL,
    result_payload  BYTEA,
    result_version  INTEGER,
    created_at      TIMESTAMP NOT NULL,
    completed_at    TIMESTAMP,
    expires_at      TIMESTAMP,
    PRIMARY KEY (tenant_id, command_type, command_id)
);
~~~

The unique constraint is the final barrier against race conditions. Never rely on a "SELECT first, then INSERT if missing" pattern as the sole mechanism: two concurrent transactions can both SELECT nothing and both execute side effects. A unique key forces only one transaction to win record creation.

Important columns:

- `request_hash`: detects key reuse with a different payload.
- `state`: command state per contract.
- `result_payload`/`result_version`: replayable result.
- `created_at`/`completed_at`: audit and operations.
- `expires_at`: when the record can be purged under the retention policy.

If the result is large, you do not have to store the entire protobuf response. You can store the resource ID, operation ID, or minimal result needed to reconstruct a stable response. However, replay semantics must be clear: the same command returns the same outcome rather than reading newer state and accidentally returning a different result from the first run if the contract requires an immutable response.

## 6. Processing Synchronous Commands in a Single Database Transaction

For commands whose business effects live in the same database, the simplest and strongest approach is executing the steps inside one transaction:

1. Create the idempotency record with the unique key and request fingerprint.
2. If the key already exists, verify the fingerprint and read the stored result.
3. Apply the business mutation.
4. Create the outbox event if a message must be emitted.
5. Save the response/result into the idempotency record and transition state to `COMPLETED`.
6. Commit everything together.

If the transaction rolls back, both the idempotency record and business mutation roll back. The client can retry with the same key; a subsequent retry can become the winning transaction.

With PostgreSQL, you can use `INSERT ... ON CONFLICT DO NOTHING` to contend for record creation without putting the current transaction into a constraint-error state:

~~~sql
INSERT INTO command_deduplication (
    tenant_id, command_type, command_id, request_hash,
    state, created_at
)
VALUES (
    :tenantId, :commandType, :commandId, :requestHash,
    'PROCESSING', CURRENT_TIMESTAMP
)
ON CONFLICT (tenant_id, command_type, command_id)
DO NOTHING
RETURNING command_id;
~~~

If the statement returns a row, the current transaction created the record and owns execution of the command. If it returns no row, read the existing record, compare `request_hash`, and handle according to `state`. For other isolation levels and databases, check unique-conflict and visibility semantics; do not assume PostgreSQL behavior across all database engines.

Spring service example:

~~~java
@Transactional
public PlaceOrderResult execute(
        String authenticatedTenantId,
        PlaceOrderCommand command) {

    String commandId = requireCommandId(command);
    byte[] requestHash = fingerprint(command);

    boolean claimed = dedupRepository.insertIfAbsent(
            authenticatedTenantId,
            "PlaceOrder",
            commandId,
            requestHash);

    if (!claimed) {
        CommandRecord existing = dedupRepository.findRequired(
                authenticatedTenantId,
                "PlaceOrder",
                commandId);

        if (!MessageDigest.isEqual(
                existing.requestHash(), requestHash)) {
            throw new IdempotencyKeyConflictException();
        }

        if (existing.isCompleted()) {
            return resultCodec.decode(existing.resultPayload());
        }

        throw new CommandInProgressException(commandId);
    }

    PlaceOrderResult result = orderDomainService.place(command);

    outboxRepository.append(
            eventFactory.orderPlaced(commandId, result));

    dedupRepository.markCompleted(
            authenticatedTenantId,
            "PlaceOrder",
            commandId,
            resultCodec.encode(result),
            resultCodec.version());

    return result;
}
~~~

This example assumes the repository implements insert-if-absent via a unique constraint and all operations join the same transaction. Do not call brokers, HTTP services, or payment providers directly inside this transaction; network calls prolong locks and external side effects cannot be rolled back.

## 7. Handling Concurrent Duplicates

Two requests with the same key may arrive at two replicas almost simultaneously. Both compute the same fingerprint and both attempt to insert. The unique constraint allows only one transaction to create the record.

In a single synchronous transaction design:

- The transaction that wins the insert performs the business mutation, outbox write, and result storage.
- The other transaction waits for the unique conflict to resolve.
- Once the winning transaction commits, the other transaction reads the `COMPLETED` record and replays the result.
- If the winning transaction rolls back, the other transaction can succeed in inserting and executing the command.

How duplicates behave depends on database isolation and transaction timeouts. Do not hold a transaction open while waiting on an external service. If a command has a long processing time, switch to an asynchronous accepted-command model rather than holding locks for a long time.

If a duplicate observes `PROCESSING` in a design where the claim is committed separately, specify the response clearly: return an operation ID for the client to poll, return a retryable status, or wait for a short bounded window. Never create a second side effect just because the command is taking a while to process.

## 8. Asynchronous Commands: ACCEPTED, Leases, and Recovery

Some commands—generating reports, importing data, or orchestrating workflows—should not execute completely inside a gRPC request. The server can commit a command record in state `ACCEPTED` along with an outbox job in one transaction, then return an operation ID.

Flow:

1. Write the idempotency record with key, fingerprint, and state `ACCEPTED`.
2. Write the command/job message to the outbox in the same transaction.
3. Commit and return the same operation ID for every retry with the same key.
4. A worker picks up the job and claims it using a lease or versioned state.
5. The worker performs the business work and updates state to `COMPLETED`/`FAILED`.
6. The client uses the operation ID to query status or receive a completion event.

A lease needs an owner, `lease_until`, and a fencing/version token so an old worker cannot commit after another worker has reclaimed the lease. When a worker crashes, lease expiration enables recovery. All business steps still require idempotency because a worker may rerun after a crash.

Do not leave state `PROCESSING` indefinitely. Define timeouts, lease expiry, retry limits, and a dead-letter/reconciliation policy. If a command fails transiently, the same operation can be retried; if it fails permanently for business reasons, persist `FAILED`/`REJECTED` per contract so resending the same key does not turn into a new operation.

## 9. Combining Idempotency with a Transactional Outbox

A command often updates a database and then emits an event to a broker. If the database commits but publishing fails, the system has new business state that downstream services do not know about. If it publishes first and the database rolls back, downstream services receive an event for a change that never existed.

A transactional outbox solves dual-write by writing the business mutation and event in the same database transaction:

~~~sql
CREATE TABLE outbox_event (
    event_id        VARCHAR(120) PRIMARY KEY,
    aggregate_id    VARCHAR(120) NOT NULL,
    event_type      VARCHAR(120) NOT NULL,
    payload         BYTEA NOT NULL,
    created_at      TIMESTAMP NOT NULL,
    published_at    TIMESTAMP
);
~~~

Inside the command-handling transaction, insert the outbox event with a stable event ID—for instance derived from the command ID and event type, or an ID generated and saved in the same transaction. A relay reads unpublished events and sends them to the broker.

The relay may publish an event successfully and crash before setting `published_at`. Upon restart, it publishes again. This is intentional at-least-once behavior; the event ID must remain unchanged so consumers can deduplicate.

Do not mark an outbox record published before the broker confirms publishing. Even when the broker confirms, there is still a crash window between publishing and updating the database; consumers still need inbox deduplication.

## 10. Consumer Inbox: Preventing Duplicate Event Processing

Command idempotency at the gRPC ingress does not automatically protect consumers. Consumers must deduplicate by a stable event ID or message ID.

Inbox pattern:

~~~sql
CREATE TABLE processed_message (
    consumer_name   VARCHAR(120) NOT NULL,
    event_id        VARCHAR(120) NOT NULL,
    processed_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Within the same consumer transaction:

1. Insert `(consumer_name, event_id)`.
2. On unique conflict, the message was already processed; do not run business effects again.
3. If insert succeeds, apply the business mutation.
4. Commit the inbox record and business mutation together.
5. Only acknowledge the broker after the transaction commits.

If the consumer commits the database and crashes before acknowledging, the broker redelivers; the inbox record identifies the next delivery as a duplicate. If the business mutation and inbox insert are not in the same transaction, a window remains for duplicating or skipping effects.

If the consumer calls an external service, the inbox transaction cannot atomically encompass the external side effect. Use a downstream idempotency key, a follow-up outbox, or a saga/compensation.

## 11. Idempotency Across Multiple Services and External Side Effects

A command may traverse several steps: gRPC service → order database → payment provider → inventory service → broker. Idempotency at the first service does not automatically make every downstream step idempotent.

Propagate a stable operation/command ID downstream when the contract permits. Each service must scope and store its own idempotency state. Do not use one arbitrary global key across every operation if services have different semantics.

With a payment provider, use the idempotency key supported by the provider and keep that key stable across retries. If a provider does not support one, persist attempts, reconcile transaction status, and design a saga to handle uncertain outcomes.

Do not hold a database transaction open while calling payment/HTTP APIs. A safe sequence is typically:

- Transaction A: create command/order in state `PENDING` and write outbox.
- Worker: call payment with the idempotency key.
- Transaction B: record payment outcome and transition state.
- On failure or uncertain timeout, query/reconcile with the provider before issuing a new charge.
- Emit the new state event via outbox.

This is a multi-transaction workflow, not a single distributed transaction. A saga defines the steps, retries, timeouts, and compensations; idempotency protects each step from executing repeatedly.

## 12. Duplicate Outcomes and gRPC Status

The contract must define what the server returns when receiving the same command again:

| Scenario | Recommended behavior |
| --- | --- |
| New key, valid payload | Execute command and store result |
| Existing key, matching fingerprint, `COMPLETED` | Replay stored result |
| Existing key, different fingerprint | Reject key conflict |
| Existing key, command still processing | Return operation ID/in-progress or retryable status |
| Existing key, final business `FAILED` | Replay stored failure outcome |
| Transient infrastructure error before commit | Roll back so retries with the same key can re-execute |

You can map a key conflict to `ALREADY_EXISTS` or `INVALID_ARGUMENT` per your API contract. `ALREADY_EXISTS` expresses conflict with an already-created command; `INVALID_ARGUMENT` expresses misuse of a key in the request. Pick one consistent status with a stable reason code.

For an in-progress command, `ABORTED` or `UNAVAILABLE` can fit if clients are allowed to retry after a delay; however, if the API models an operation resource, returning the operation ID is usually clearer. Do not return `RESOURCE_EXHAUSTED` solely because a command is in progress unless a quota has been exceeded.

Do not expose internal state, SQL errors, or fingerprints in status descriptions. Use structured status details with a clear schema if clients need a retry delay or operation reference.

## 13. Retention and Protecting the Idempotency Store

Idempotency records must outlive any possible retry/replay window. If records are purged too early, a late retry could execute the command a second time.

Retention depends on the operation type:

- Payment/financial commands may require long retention for compliance and reconciliation.
- Order creation or booking needs retention at least through the client retry window and dispute handling.
- Telemetry/ephemeral commands can use shorter retention if allowed by contract.
- Async commands must retain operation state until completion and through the queryable lookup window.

Index on `expires_at` and purge in small batches to avoid large locks. Never delete commands still in `PROCESSING` or incomplete operations. If archiving is required, retain a tombstone key long enough to prevent old commands from running again.

Idempotency keys can be abused to create unbounded records. Authenticate clients before creating records, limit key length, cap new commands per client/tenant, and enforce retention. Never let callers supply arbitrary keys that bloat database indexes or create unbounded cardinality.

## 14. Observability and Audit

Track:

- New commands, duplicate replays, and key conflicts.
- Shares of `COMPLETED`, `FAILED`, `ACCEPTED`, and `PROCESSING` commands.
- Processing latency and duplicate wait time.
- Unique conflicts by command type.
- Outbox backlog, publish retries, and oldest event age.
- Inbox duplicate counts and consumer lag.
- Lease expiries, worker recoveries, and stuck commands.
- Downstream idempotency conflicts/reconciliations.

Include command IDs in traces/logs per security policy, but never turn every command ID into a metric label because of high cardinality. Log pseudonymized tenant/client, command type, outcome, and correlation ID; never log tokens or full sensitive payloads.

Alert when `PROCESSING` commands exceed maximum age, outbox backlog grows, unusual duplicate conflicts spike, or consumer inbox rejections increase. Rising duplicate replays can be normal during client retries; rising key conflicts usually indicate a client bug or abuse.

## 15. Testing Idempotency and Race Conditions

Tests must check side effects, not only returned status codes:

| Scenario | Expected outcome |
| --- | --- |
| Send command the first time | One business effect and one result record |
| Resend same key, same payload | Replay result; no second effect created |
| Same key, different payload | Reject key conflict |
| Two requests with same key arrive concurrently | Only one transaction executes side effects |
| Transaction rolls back before commit | Retry with same key can execute command |
| Commit succeeds, response lost | Retry returns stored result |
| Relay publishes then crashes before marking published | Event may republish; consumer deduplicates |
| Consumer commits then crashes before ack | Redelivery creates no second business effect |
| Async worker crashes while `PROCESSING` | Safe lease expiry and recovery |
| Downstream timeout with uncertain outcome | Reconcile using operation/idempotency key |
| Record past retention | Behavior matches contract and replay window |

Use barriers/latches to dispatch concurrent requests across two channels or two replicas. Assert that business rows, command records, and outbox events equal exactly one. Never use `Thread.sleep` to randomly induce races.

Test rollback and crash windows by deliberately throwing exceptions before/after commit, before/after publish, and before/after broker acknowledgement. For consumers, verify the inbox record and business mutation share the same transaction.

In Spring integration tests, call the service through a real gRPC generated stub, verify `@Transactional` proxies work, verify the database enforces unique constraints, and verify replayed responses carry the same business result. In-memory repositories cannot substitute for real database concurrency tests.

## 16. Common Implementation Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Generating new command ID on every retry | Server treats retries as new commands | Keep the same key per logical operation |
| Using unverified client-supplied tenant | Can bypass quotas or access another tenant's records | Scope by authenticated principal |
| SELECT before INSERT only | Races create duplicate side effects | Unique constraint and atomic insert |
| Storing key without fingerprint | Same key with different payload replays wrongly | Compare canonical request hash |
| Storing dedup record outside business transaction | Records and side effects diverge | Commit in the same transaction |
| Publishing to broker inside DB transaction | Dual-write and prolonged transactions | Transactional outbox |
| Not deduplicating at consumer | Broker redelivery runs business effects repeatedly | Inbox unique key in the same transaction |
| Purging records too early | Late retries create new side effects | Retention matching operation/replay window |
| Holding DB transaction during external API calls | Long locks, external effects cannot roll back | Outbox/worker/saga |
| Treating timeout as guaranteed failure | Retries may double-charge or double-create | Reconcile and use downstream idempotency |
| In-memory bucket/map as source of truth | Restarts or other replicas process duplicates | Durable database/shared store |

## 17. Practice Exercises and Self-Check Questions

### Practice Exercises

1. Add `command_id` to the protobuf command and ensure clients keep the same ID across retries.
2. Extract tenant/client scope from the authentication `Context` rather than trusting a self-declared tenant field.
3. Create the `command_deduplication` table with a unique key and request fingerprint.
4. Write a transactional service: insert-if-absent, business mutation, outbox insert, and result storage in the same transaction.
5. Send two concurrent requests with the same key; verify only one order is created.
6. Resend the same key with a different payload; verify the server rejects the key conflict.
7. Build an outbox relay that can republish and a consumer inbox dedup in the same transaction as the business effect.
8. Simulate crash windows after commit, after publish, and before acknowledgement; verify retries/redelivery create no duplicate effects.
9. For async commands, implement `ACCEPTED` state, operation ID, lease expiry, and worker recovery.
10. Write a Spring gRPC integration test using a generated stub and a real database.

### Self-Check Questions

**1. Why do commands need idempotency?**  
Because clients may retry after a timeout even when the server already committed; the same logical command must not produce side effects a second time.

**2. When must the command ID be created?**  
Before the first send, and preserved unchanged across all retries of the same operation.

**3. Why is a request fingerprint needed?**  
To detect callers reusing a key for a different payload and avoid replaying an unrelated result.

**4. Why is SELECT followed by INSERT not enough?**  
Two transactions can both observe no record; a unique constraint and atomic insert are required to prevent races.

**5. Why must the command record and business mutation share the same transaction?**  
So you never end up with a saved dedup state without committed business effects, or committed effects without a record blocking retries.

**6. Does an outbox guarantee the broker receives an event only once?**  
No. The relay can republish; a stable event ID and consumer inbox ensure business effects are not repeated.

**7. What must the consumer inbox commit together with?**  
In the same transaction as the consumer's business mutation; only acknowledge the broker after commit.

**8. Does exactly-once delivery mean end-to-end exactly-once business effects?**  
No. Database, broker, and external API boundaries each require their own idempotency/transactions; the practical goal is effectively-once effects within each controlled scope.

## Summary

Command idempotency ensures retries or duplicate deliveries do not create extra business effects. Clients maintain stable command IDs; servers scope keys by authenticated tenant/client and command type, store request fingerprints, and use unique constraints and transactions to combine dedup records, business mutations, stored results, and outbox writes. Duplicates with matching payloads are replayed; matching keys with differing payloads are rejected; long commands can use `ACCEPTED` state, leases, and operation status. Outbox relays can still republish duplicates, so consumers need inbox deduplication in the same transaction as business effects. External side effects require downstream idempotency keys or sagas. Retention, concurrency tests, and crash-window tests are mandatory parts of the operational contract.
