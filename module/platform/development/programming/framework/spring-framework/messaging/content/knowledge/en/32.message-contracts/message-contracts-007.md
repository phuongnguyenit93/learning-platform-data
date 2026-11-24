# Idempotency Keys, Result Storage, and Deduplication Window

## Objectives

After this lesson, you will be able to:

- Explain why a messaging request can be sent or processed multiple times even when the client intended to send it once.
- Design idempotency keys scoped by tenant, operation, and request.
- Detect reuse of the same key with a different payload using a request fingerprint.
- Store processing state and results to replay prior responses for duplicate requests.
- Handle two concurrent requests with the same key using unique constraints and transactions.
- Choose an appropriate deduplication retention window (TTL), error policy, and recovery mechanism.

## 1. Why Is Idempotency Needed?

In a messaging system, sending a message and receiving the outcome are two separate events. A client may send a request, the server processes it successfully, yet the response is lost when the connection closes. Not knowing whether the server performed the business action, the client resends the request.

Common causes include:

- Client retries after a timeout because no response arrived.
- Message broker redelivers a message when the consumer has not sent an acknowledgement.
- Consumer completes business processing but the process stops before sending ACK.
- Connection drops after the server commits data yet before the client receives the response.
- User clicks a submit button multiple times or a gateway forwards duplicate requests.
- Multiple consumers or workers receive the same task due to configuration, redelivery, or operational errors.

Example: a client sends a command to create an order. The server creates order **ORD-42** and commits the transaction, but the response never reaches the client. If the request is resent as a new command, the server may create **ORD-43**. The client wanted one order, yet the system created two.

**Idempotency** is a processing contract in which multiple submissions of the same logical operation are treated as a single operation within a defined scope and duration. Upon receiving a duplicate request, the server returns the stored result or reports an in-progress status instead of executing side effects a second time.

Idempotency does not make the network deliver only once. It enables the application layer to tolerate duplicate deliveries safely.

## 2. Idempotent Operations and Idempotency Keys

An inherently idempotent operation can be executed multiple times while leaving the final state identical. For example, setting a resource's status to **ACTIVE** is usually idempotent; incrementing a balance by 100 is not.

For operations that create resources or perform side effects, the client can send an **idempotency key** to identify a unique business intent.

HTTP API example:

~~~http
POST /api/orders
Idempotency-Key: 8a12d3e7-7a25-4f42-9e11-21c4b7f64a10
Content-Type: application/json

{"customerId":"C-17","sku":"BOOK-01","quantity":1}
~~~

If the client retries the same operation after a timeout, it must resend the same key and the same logical content. When the user intentionally creates another order, the client must generate a new key.

In messaging, the key may live in a message header, RSocket metadata, STOMP header, or broker message property. How the key is carried depends on the transport; its semantics belong to the business contract.

A key should have these properties:

- Generated per logical operation, typically as a UUID or sufficiently unpredictable random value.
- Contains no secrets or personal data.
- Reused when retrying the same operation.
- Replaced with a new key when starting a different operation.
- Scoped unambiguously, such as tenant + operation + key.

Avoid using a single global key string if multiple tenants or multiple operation types might use the same value. A common composite key is the tuple:

~~~text
(tenant_id, operation_name, idempotency_key)
~~~

For example, the same key **request-123** can be valid for two different tenants; it can also be used for two different operations if the contract defines separate scopes. That scope must be reflected in the storage's unique constraint.

## 3. Fingerprinting: Preventing Key Reuse with a Different Request

Checking the key alone is not enough. A client might accidentally send the same key with a changed payload—for instance, ordering quantity 1 the first time and quantity 5 the second time.

The server should compute a **request fingerprint** from the business-significant data. Typically SHA-256 is computed over a normalized representation of the method, route, tenant, and payload. When the same key reappears:

- Matching fingerprint: this is a retry of the same operation.
- Different fingerprint: the client is reusing the key in violation of the contract; the server should reject it, typically with a conflict error.

Do not hash raw JSON directly if property ordering or whitespace can change while the logical content stays identical. Canonicalize the JSON or serialize the DTO deterministically. Include only fields affecting business logic in the fingerprint; exclude transport timestamps or trace IDs if they vary across retries.

Example fingerprint inputs:

~~~text
SHA-256(
  tenantId + "\n" +
  HTTP_METHOD + "\n" +
  normalizedRoute + "\n" +
  canonicalRequestBody
)
~~~

A hash is not an authentication or authorization mechanism. The server must still authenticate the sender and verify permissions on every access to the result. Never put access tokens or secrets into fingerprints or logs.

## 4. Storing Processing State and Handled Responses

An idempotency record typically stores:

| Field | Role |
| --- | --- |
| tenant/scope | Separates key scopes |
| idempotency_key | Identifies the logical operation |
| request_hash | Detects the same key with a different payload |
| state | Processing state |
| response_status | Result code or outcome category |
| response_body | Serialized result for replay |
| resource_id | ID of the created/updated resource, if any |
| created_at | Timestamp when the operation was first received |
| completed_at | Timestamp when processing finished |
| expires_at | Deduplication expiration timestamp |

Common states:

- **IN_PROGRESS:** processing ownership has been claimed, but the result is not yet ready.
- **COMPLETED:** business logic completed and the response is stored.
- **FAILED_FINAL:** terminal failure where the contract specifies retries must receive this stored error.
- **FAILED_RETRYABLE:** retriable failure; clear rules are needed to reclaim processing ownership.

Not every system needs all four states. For synchronous handling confined within a short transaction, the **IN_PROGRESS** record may exist only inside that transaction and commit directly as **COMPLETED**. For long-running jobs, **IN_PROGRESS** must be committed so duplicate requests can observe it and receive an in-progress status.

**What response should be stored?** If the API must replay the exact result, store the status, body, content type, and meaningful response headers such as **Location** or version tags. Do not store per-transmission headers such as **Date**, trace IDs, or connection headers. If you only need to prevent repeating side effects, you can store the resource ID and reconstruct the response from current data; that is a different contract from replaying the verbatim response.

For bodies requiring exact replay, store the serialized bytes or string along with the content type. JSONB may normalize structure and does not preserve exact original bytes or field order.

## 5. Designing the Table and Unique Constraint

PostgreSQL schema example:

~~~sql
CREATE TABLE idempotency_record (
    tenant_id          VARCHAR(100) NOT NULL,
    operation_name     VARCHAR(150) NOT NULL,
    idempotency_key    VARCHAR(200) NOT NULL,
    request_hash       CHAR(64) NOT NULL,
    state              VARCHAR(20) NOT NULL,
    response_status    INTEGER,
    response_body      TEXT,
    response_headers   JSONB,
    resource_id        VARCHAR(150),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at       TIMESTAMPTZ,
    expires_at         TIMESTAMPTZ NOT NULL,

    CONSTRAINT pk_idempotency_record
        PRIMARY KEY (tenant_id, operation_name, idempotency_key),

    CONSTRAINT ck_idempotency_state
        CHECK (state IN (
            'IN_PROGRESS',
            'COMPLETED',
            'FAILED_FINAL',
            'FAILED_RETRYABLE'
        ))
);

CREATE INDEX ix_idempotency_expiry
    ON idempotency_record (expires_at);
~~~

The most critical element is the **primary key/unique constraint** on the key scope. Checking via "SELECT first, then INSERT if absent" is unsafe when two requests arrive concurrently: both can read that no row exists and both proceed to execute business logic.

The database must arbitrate key ownership using an insert guarded by a unique constraint. In PostgreSQL, you can use:

~~~sql
INSERT INTO idempotency_record (
    tenant_id,
    operation_name,
    idempotency_key,
    request_hash,
    state,
    expires_at
)
VALUES (
    :tenantId,
    :operationName,
    :key,
    :requestHash,
    'IN_PROGRESS',
    :expiresAt
)
ON CONFLICT (tenant_id, operation_name, idempotency_key)
DO NOTHING;
~~~

If the insert creates one row, the current request claims processing ownership. If it creates zero rows, another request has already claimed that key; the server must read the existing record, compare fingerprints, and decide whether to replay, report in-progress, or reject a key conflict.

Do not replace a unique constraint with a custom distributed lock if the database already stores the business state. Locks and idempotency records should share one source of truth or have a clearly defined synchronization protocol.

## 6. Duplicate Request Handling Workflow

Typical synchronous flow:

~~~mermaid
flowchart TD
    A[Receive request and idempotency key] --> B[Compute request fingerprint]
    B --> C[INSERT record with unique key]
    C --> D{INSERT succeeded?}
    D -->|Yes| E[Execute business logic]
    E --> F[Save response and COMPLETED]
    F --> G[COMMIT transaction and return response]
    D -->|No| H[Read existing record]
    H --> I{Same fingerprint?}
    I -->|No| J[Reject key conflict]
    I -->|Yes| K{State?}
    K -->|COMPLETED| L[Replay stored response]
    K -->|IN_PROGRESS| M[Return in-progress status or wait]
    K -->|FAILED_FINAL| N[Replay final failure]
    K -->|FAILED_RETRYABLE| O[Apply claim/retry policy]
~~~

For a duplicate request with a matching fingerprint:

- If **COMPLETED**, return the stored result. Do not invoke the order creation service again.
- If **IN_PROGRESS**, return an in-progress status (e.g., HTTP 202 with a status query URL), or wait for the result within a bounded timeout. Do not run a second business execution in parallel.
- If **FAILED_FINAL**, return the stored failure per the contract.
- If **FAILED_RETRYABLE**, only one worker may reclaim it atomically; other workers must wait or receive an in-progress status.

For the same key with a different fingerprint, return a conflict (e.g., HTTP 409). Never return the old response for a new payload, as doing so could mislead the client into thinking the new operation succeeded.

## 7. Integrating with Spring and Transactions

With Spring, you can implement the idempotency store using **JdbcTemplate**/repositories and place the idempotency write alongside business data updates in a single transaction.

A short transaction can execute:

1. Insert the idempotency record via **INSERT ... ON CONFLICT DO NOTHING**.
2. If the insert succeeded, apply domain changes in the same transaction.
3. Serialize the response and update the record to **COMPLETED**.
4. Commit both the domain data and response record together.

If the transaction rolls back, both the domain changes and the unfinished idempotency record roll back. A subsequent retry can then claim processing ownership. If the transaction commits yet the response is lost in transit, the retry reads **COMPLETED** and receives the stored result.

The example below illustrates service-level orchestration. The repository methods represent the SQL from the previous section; the actual implementation must rely on a database unique constraint and participate in the same transaction manager.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class CreateOrderHandler {

    private final IdempotencyRepository idempotency;
    private final OrderRepository orders;
    private final OrderResponseMapper responses;

    CreateOrderHandler(
            IdempotencyRepository idempotency,
            OrderRepository orders,
            OrderResponseMapper responses) {
        this.idempotency = idempotency;
        this.orders = orders;
        this.responses = responses;
    }

    @Transactional
    StoredResponse handle(
            String tenantId,
            String key,
            String requestHash,
            CreateOrder command) {

        boolean claimed = idempotency.tryInsert(
                tenantId, "CREATE_ORDER", key, requestHash);

        if (!claimed) {
            IdempotencyRecord existing = idempotency.findForUpdate(
                    tenantId, "CREATE_ORDER", key);

            if (!existing.requestHash().equals(requestHash)) {
                throw new IdempotencyKeyConflictException();
            }

            if (existing.isCompleted()) {
                return existing.storedResponse();
            }

            if (existing.isInProgress()) {
                throw new RequestAlreadyInProgressException();
            }

            throw new IdempotencyRetryPolicyException(existing.state());
        }

        Order order = orders.create(command);
        StoredResponse response = responses.from(order);

        idempotency.markCompleted(
                tenantId, "CREATE_ORDER", key, order.id(), response);

        return response;
    }
}
~~~

This is an illustrative skeleton, not a standalone compilable class: repository interfaces, domain models, mappers, and exceptions must be defined in the application. The mandatory condition is that **tryInsert** relies on a unique constraint and **orders.create** plus **markCompleted** participate in the same transaction. Never catch a business exception and silently commit an **IN_PROGRESS** record.

In PostgreSQL, when two concurrent transactions insert the same unique key, the second insert may block waiting for the first transaction to commit or roll back. If the first commits, the second insert produces zero rows; under **READ COMMITTED** isolation, the subsequent SELECT can read the committed record. If the first rolls back, the second request can insert successfully and become the processing owner. Verify this behavior against your application's actual isolation level and database.

For long-running workflows, do not hold a database transaction open while waiting on an external API. A better pattern is saving **IN_PROGRESS** with a lease/owner token, committing, performing the external work, and then updating the result. Lease expiration and fencing/version tokens are required so an old worker cannot overwrite results after a new worker has claimed ownership.

## 8. Java 17 Example: Single-Process Deduplication

The following example uses **ConcurrentHashMap.putIfAbsent** to demonstrate only one thread executing the operation for a given key. Other threads wait on the same **CompletableFuture** and receive the same result. A SHA-256 fingerprint detects when a key is reused with a different payload.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Supplier;

public class IdempotencyDemo {

    record Response(int status, String body) {}

    static final class Entry {
        final String fingerprint;
        final CompletableFuture<Response> result = new CompletableFuture<>();

        Entry(String fingerprint) {
            this.fingerprint = fingerprint;
        }
    }

    static final class InMemoryIdempotency {
        private final ConcurrentMap<String, Entry> entries =
                new ConcurrentHashMap<>();

        Response execute(
                String scopedKey,
                String payload,
                Supplier<Response> operation) {

            String fingerprint = sha256(payload);
            Entry candidate = new Entry(fingerprint);
            Entry current = entries.putIfAbsent(scopedKey, candidate);

            if (current == null) {
                try {
                    Response response =
                            Objects.requireNonNull(operation.get());
                    candidate.result.complete(response);
                    return response;
                } catch (RuntimeException | Error error) {
                    candidate.result.completeExceptionally(error);
                    entries.remove(scopedKey, candidate);
                    throw error;
                }
            }

            if (!current.fingerprint.equals(fingerprint)) {
                throw new IllegalArgumentException(
                        "Idempotency key reused with a different request");
            }

            return current.result.join();
        }

        private static String sha256(String value) {
            try {
                byte[] digest = MessageDigest.getInstance("SHA-256")
                        .digest(value.getBytes(StandardCharsets.UTF_8));
                return HexFormat.of().formatHex(digest);
            } catch (NoSuchAlgorithmException impossible) {
                throw new IllegalStateException(impossible);
            }
        }
    }

    public static void main(String[] args) {
        InMemoryIdempotency store = new InMemoryIdempotency();
        int[] executions = {0};

        String key = "tenant-17:CREATE_ORDER:client-key-42";
        String payload = "{\"customerId\":\"C-17\",\"quantity\":1}";

        Response first = store.execute(key, payload, () -> {
            executions[0]++;
            return new Response(201, "{\"orderId\":\"ORD-42\"}");
        });

        Response retry = store.execute(key, payload, () -> {
            executions[0]++;
            return new Response(201, "{\"orderId\":\"ORD-43\"}");
        });

        if (!first.equals(retry) || executions[0] != 1) {
            throw new AssertionError("Idempotency contract failed");
        }

        System.out.println("first=" + first.status() + " " + first.body());
        System.out.println("retry=" + retry.status() + " " + retry.body());
        System.out.println("businessExecutions=" + executions[0]);
    }
}
~~~

Run with Java 17:

~~~bash
javac IdempotencyDemo.java
java IdempotencyDemo
~~~

Exact stdout:

~~~text
first=201 {"orderId":"ORD-42"}
retry=201 {"orderId":"ORD-42"}
businessExecutions=1
~~~

This example demonstrates thread coordination within **a single process** only. It does not persist across restarts, does not share state across multiple instances, and has no TTL. The map also retains completed entries indefinitely. Production requires a database/Redis or shared store with persistence, unique constraints/atomic claims, and a cleanup process.

In the demo, the entry is removed when the operation throws an exception so a subsequent request can retry. This policy is safe only when the failure is guaranteed to happen before any side effect or the side effect rolled back. If the operation committed a side effect yet failed before saving the result, deleting the key and rerunning could produce duplicate effects. Production must resolve uncertain states via shared transactions, outboxes, provider idempotency, or reconciliation.

## 9. Deduplication Window (TTL)

Idempotency records do not necessarily live forever. The **TTL** defines how long the server commits to recognizing a used key and returning the prior result.

Choose the TTL based on:

- Maximum retry window of clients, gateways, and brokers.
- Redelivery retention window of the message broker.
- How long users may resubmit an action from the UI.
- Latency of background jobs, scheduled retries, and incident recovery mechanisms.
- Business requirements for preventing duplicate transactions.

The TTL must be longer than the entire supported retry/redelivery window, plus a safety margin for delays and operations. For example, if a broker can redeliver for 48 hours, a 24-hour TTL will not protect against redeliveries after the first day.

Once the TTL expires, the same key may be treated as a new request if the record has been deleted. Therefore:

- Explicitly document the TTL in the API/message contract.
- Delete only expired records per the chosen policy.
- Do not treat the actual cleanup job execution time as the contract; cleanup jobs may run late.
- Consider keeping a tombstone/key hash longer than the response body if business rules still need to block duplicates after purging large results.
- Never delete an **IN_PROGRESS** record merely because `expires_at` passed if a worker may still be running; use leases and controlled ownership revocation.

PostgreSQL cleanup example:

~~~sql
DELETE FROM idempotency_record
WHERE state IN ('COMPLETED', 'FAILED_FINAL')
  AND expires_at < CURRENT_TIMESTAMP;
~~~

This statement is only an example for finalized records. Batch deletes are needed to avoid large transactions on heavily populated tables. For large tables, partition by time or run bounded cleanup jobs. **IN_PROGRESS** records must be handled separately via lease timeouts, worker heartbeats, and reconciliation before retrying.

TTL is part of correctness, not merely storage optimization. Deleting too early permits duplicate side effects; keeping too long increases storage usage and may prevent a valid operation from reusing a key in ways the API did not intend.

## 10. External Side Effects and Transactional Outbox

A database transaction guarantees atomicity only for changes within the same transaction manager/database. It cannot roll back a sent email, a charge at a payment provider, or a message already published to an external broker.

Unsafe example:

1. Insert idempotency record.
2. Call the payment provider and the provider captures funds.
3. Database transaction rolls back due to an error saving the response.
4. Client retries and the payment provider is called a second time.

There is an irreducible window with **@Transactional** alone: an external side effect occurred, yet local state never committed.

Mitigation approaches:

- **Use provider idempotency keys:** pass the same key to payment/email/remote APIs when the provider supports it.
- **Transactional outbox:** in the same transaction as domain records and the idempotency result, write an outbox event. A worker publishes the event and marks it sent; consumers still need deduplication because publishing may repeat.
- **Inbox/dedup at consumers:** store the message ID with processing state and a unique constraint so one message never applies local side effects multiple times.
- **Saga/compensation:** for multi-service workflows, model steps and compensating actions when completed transactions at another service cannot be rolled back.
- **Reconciliation:** periodically reconcile provider state with local state when a call's outcome is ambiguous.

An outbox does not create exactly-once delivery on its own. It atomically records the intent to publish alongside database updates; messages can still be redelivered, so consumers must be idempotent.

## 11. Testing Idempotency

A minimal test suite should cover:

| Scenario | How to Reproduce | Expected Outcome |
| --- | --- | --- |
| First submission | New key, valid payload | Business logic runs and response is stored |
| Sequential retry | Same scope, key, and fingerprint | Same response returned; business logic executes once |
| Concurrent retries | Multiple requests with same key arrive simultaneously | Only one request claims and executes side effects |
| Same key, different payload | Same key, different fingerprint | Conflict; business logic does not run a second time |
| Response lost after commit | Commit succeeds, then drop response | Retry reads and replays stored result |
| Rollback before commit | Force transaction failure | No fake COMPLETED result; retry follows policy |
| Worker in progress | Send duplicate while state is IN_PROGRESS | Wait or return in-progress status; no parallel execution |
| Different tenant | Same key across different tenants | No cross-tenant leak or wrong result returned |
| TTL expired | Resend after window expires | Behavior matches TTL contract |
| Crash during external call | Stop worker after external side effect | Reconciliation/provider key/outbox prevents duplicate execution |
| Large response | Store and replay large response payloads | Result is not truncated or mis-serialized |

In unit tests, mock services and use **AtomicInteger** to count execution attempts. For concurrency tests, use **CountDownLatch** or barriers so threads start simultaneously; do not rely on **Thread.sleep**.

In integration tests, run a real database (e.g., PostgreSQL via Testcontainers) and issue concurrent transactions with the same key. Assert that the unique constraint allows only one record, the domain resource is created only once, and all callers receive the same result or an in-progress status as designed.

A critical test is **commit succeeded but response lost**. Submit the first request, commit the data, deliberately prevent the client from receiving the response, and then resend the same key. If a test merely calls the service twice sequentially without simulating response loss after commit, it has not verified the most important failure mode.

## 12. Common Design Mistakes

- **Generating a new key on every retry:** the server cannot recognize that both requests belong to the same operation.
- **Checking keys only with SELECT before INSERT:** introduces a race condition when two requests arrive concurrently.
- **Not storing a fingerprint:** the same key with a different payload can wrongly receive the old response.
- **Storing only the key without storing the result:** duplicate requests know it ran before, yet cannot replay the result per the contract.
- **Storing results before business commit:** may replay a result for business changes that rolled back.
- **Holding transactions open during remote calls:** locks database rows for a long time, increases contention, and still cannot roll back external side effects.
- **Deleting the key right after sending the response:** the client may never receive the response and retry immediately afterward.
- **TTL shorter than the redelivery window:** old messages arriving late can execute business logic a second time.
- **Unbounded response record sizes:** the idempotency table can grow rapidly in storage size.
- **Assuming end-to-end exactly-once:** networks, brokers, and external services can still deliver duplicates; deduplication is needed at every boundary with side effects.

## 13. Implementation Checklist

- [ ] Clients preserve the same key when retrying the same logical operation.
- [ ] Keys are scoped by tenant/operation and enforced with a unique constraint in shared storage.
- [ ] Fingerprints are computed from canonicalized requests.
- [ ] Same key with a different request is explicitly rejected.
- [ ] Key claiming and domain/result updates use appropriate transactions or atomic protocols.
- [ ] Necessary response/status/resource ID fields are stored for replay.
- [ ] Behavior for duplicates while in progress is clearly defined.
- [ ] TTL is longer than the retry/redelivery window and has a safe cleanup job.
- [ ] IN_PROGRESS has leases/recovery if processing spans multiple transactions.
- [ ] External side effects use provider idempotency, outboxes, inboxes, or reconciliation.
- [ ] Tests cover sequential, concurrent, post-commit response loss, rollback, key conflict, and TTL expiration.
- [ ] Raw keys or sensitive payloads are not logged unnecessarily.

## References

- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Framework Reference — JDBC access](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
- [PostgreSQL — INSERT and ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html)
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)
- [Microservices.io — Idempotent Consumer](https://microservices.io/patterns/communication-style/idempotent-consumer.html)
- [Microservices.io — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html)
