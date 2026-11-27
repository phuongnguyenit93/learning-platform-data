# Risk of Duplicate Writes When Connection Drops After the Database Has Written

A write request can encounter a network failure immediately after the database executes and commits the change. The application sees only a timeout or connection reset and cannot be certain whether the operation succeeded. If it automatically resends the statement as a fresh operation, the system may create duplicate records, debit money twice, reserve inventory multiple times, or trigger repeated side effects.

This is an **ambiguous write outcome** scenario. It differs from errors that definitively happen before the database receives the command or constraint errors explicitly returned by the database. When confirmation is lost, the database may have committed even though the client never received a response.

With Spring Data R2DBC, reactive publishers can be resubscribed by Reactor retries, HTTP clients, gateways, or end users themselves. Consequently, any retryable write operation needs an appropriate deduplication strategy. A common approach is using a stable **idempotency key** backed by a unique constraint, storing the request marker within the same transaction as the business mutation.

## 1. Scenario: Connection Drops After the Database Has Written

Suppose an order creation API sends an insert statement to the database:

1. The application sends the insert order statement.
2. The database receives the command, writes the row, and commits the transaction.
3. The database sends the success result back to the application.
4. The network connection drops before the application receives the response.
5. The application-side publisher terminates with a connection error or timeout.

At step 5, the application cannot conclude with certainty that the insert rolled back. The database may have committed successfully; only the acknowledgement was lost in transit.

### 1.1. Why callers cannot determine the outcome from the exception alone

An exception such as connection reset, timeout, or connection closed indicates that communication with the database did not finish as expected. It does not necessarily prove the database rolled back.

There are three possibilities:

- **Command never reached the database:** no changes were made.
- **Command ran but the transaction had not committed:** once the connection dropped, the database may roll back the transaction upon detecting session termination.
- **Commit succeeded but the acknowledgement was lost:** data was persisted while the caller received an error.

From the client's viewpoint, the last two possibilities look identical: the publisher emits an error with no business result.

### 1.2. Scenario diagram

~~~text
Application              Database
   |                         |
   |---- INSERT order ------>|
   |                         | write data
   |                         | COMMIT
   |<--- success response ---|
   X connection drops before application receives response
   |
   | publisher emits error
   |
   |---- retry INSERT ------>| may create a second record
~~~

The failure happens at the boundary between database commit and application acknowledgement. This is why retrying a write statement must be designed differently from retrying a read query.

## 2. Why Retries Can Create Duplicate Data

Reactive repository methods and queries normally return lazy publishers. Each resubscription to a cold publisher can re-execute the database operation.

Example:

~~~java
public Mono<Order> createOrder(CreateOrderRequest request) {
    Order order = new Order(
            null,
            request.customerId(),
            request.totalAmount()
    );

    return orderRepository.save(order)
            .retry(1);
}
~~~

If the initial subscription inserted and committed yet the response was lost, retrying can run the insert again. If the primary key is database-generated, the second execution can create a new order with a different ID. The database has no way to tell that both commands represent the same business intent unless the application supplies a shared identifier.

### 2.1. Places that may resend requests automatically

Duplicate submissions do not come only from Reactor:

- Reactor `retry` or `retryWhen` in the service.
- HTTP client retries when no response arrives.
- API gateways or reverse proxies retrying requests.
- Users clicking submit again after seeing a timeout.
- Mobile apps resending requests when network connectivity returns.
- Message brokers redelivering messages when a consumer fails to acknowledge.
- Background jobs re-running after a process restart.

Deduplication must therefore be enforced at the storage or business boundary, not merely inside one service-layer retry snippet.

### 2.2. Not every error is retryable

Some errors have unambiguous outcomes:

- Validation failing before writing.
- Foreign key or check constraint violations.
- Business data unique constraint violations.
- SQL syntax errors.
- Data type conversion errors.

Retrying these errors rarely succeeds. For connection failures or timeouts occurring during write/commit, the outcome can be ambiguous and must be reconciled using a stable identifier.

## 3. What Is Idempotency?

An operation is **idempotent** if repeating the same request with the same identifier leaves the final business outcome identical to executing it once.

Examples:

- Setting an order status to `PAID` may be idempotent if writing the same status repeatedly produces no additional side effects.
- Creating a new order is normally not idempotent because each insert can generate another order.
- Incrementing a balance by 100 is not idempotent because running it twice adds 200.
- Reserving 1 unit of stock may not be idempotent if every call decrements stock or increments reservation count.

An idempotency key is a unique code representing a single business intent. The client generates the key before the first send and reuses that exact key for every retry of the same intent.

Example HTTP header:

~~~http
POST /orders
Idempotency-Key: 8d1c9a6e-2f50-4e54-a4b2-1a76c1c5a8d0
Content-Type: application/json
~~~

The server stores the key alongside the processing outcome. If another request arrives with the same key, the server looks up the prior result and returns it instead of executing the business logic a second time.

### 3.1. Keys must remain stable across retries

The key should be created once at the request or command boundary:

~~~java
String idempotencyKey = request.idempotencyKey();

return service.createOrder(idempotencyKey, request.command());
~~~

Do not generate a new key on every publisher subscription. For instance, never generate a UUID inside a supplier that gets retried:

~~~java
// Unsuitable: each subscription can generate a new key.
Mono.defer(() -> service.createOrder(UUID.randomUUID().toString(), command));
~~~

If the key changes with each attempt, the database treats each submission as an independent operation and deduplication breaks down.

### 3.2. Key scoping

Do not use a bare key without scoping. Uniquely scope keys by tenant/client, operation/API name, and client-supplied idempotency key.

A composite unique constraint prevents collisions across clients or operation types:

~~~sql
UNIQUE (tenant_id, operation, idempotency_key)
~~~

Do not use user IDs or sensitive data directly as keys. Keys should be unpredictable, length-bounded, and format-validated.

## 4. Persisting Idempotency Keys with Unique Constraints

A durable approach is creating a request receipt table. Example:

~~~sql
CREATE TABLE command_receipts (
    tenant_id BIGINT NOT NULL,
    operation VARCHAR(80) NOT NULL,
    idempotency_key VARCHAR(120) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    result_order_id BIGINT,
    completed_at TIMESTAMP,
    PRIMARY KEY (tenant_id, operation, idempotency_key)
);
~~~

Column roles:

| Column | Purpose |
| --- | --- |
| `tenant_id` | Authenticated tenant scope |
| `operation` | Business operation represented by the key |
| `idempotency_key` | Stable identifier for a single submission intent |
| `request_hash` | Hash of normalized payload to detect key reuse with different content |
| `result_order_id` | Reference to the created business outcome |
| `completed_at` | Timestamp when the business operation was recorded as complete |

The primary key/unique constraint serves as the final safeguard when two requests with the same key arrive concurrently. A `SELECT`-then-`INSERT` check is unsafe because two concurrent requests can both see no key and then both attempt to insert.

### 4.1. Why is a request hash needed?

A client must not reuse the same key for two different payloads. For example:

- First call with key `K` creates an order totaling 100.
- Next call sends key `K` with a total of 500.

The server must catch misuse of the key. If the payload hash mismatches, return a conflict error instead of returning the old result as if the requests were identical.

Compute the hash from a canonical representation of the meaningful business fields. Avoid hashing raw JSON strings if property ordering, whitespace, or serialization formatting can change without altering business content.

### 4.2. Never store keys only in memory

An in-memory map fails across multiple application instances, process restarts, requests routed to different nodes, or cache evictions. Idempotency records belong in durable storage enforced by a unique constraint.

If using a distributed cache, still evaluate atomicity, persistence, eviction, and behavior when cache connectivity drops.

## 5. Writing the Receipt and Business Data in the Same Transaction

Most importantly, the idempotency receipt and the business mutation must commit together. If the receipt commits in a separate transaction and order creation fails, the key gets marked as used even though no order exists. Conversely, if the order commits without the receipt, a retry can create a second order.

Desired flow:

1. Insert receipt with the key and request hash.
2. Create the order.
3. Save the order ID onto the receipt and mark it complete.
4. Commit both changes in the same transaction.

If any step fails before commit, both the receipt and the order roll back. If commit succeeds yet the acknowledgement drops, retrying with the same key hits the unique constraint and can retrieve the stored outcome.

### 5.1. Repository for receipts

Illustrative interface:

~~~java
public interface CommandReceiptRepository {

    Mono<Integer> insertReceipt(
            Long tenantId,
            String operation,
            String key,
            String requestHash);

    Mono<Integer> completeReceipt(
            Long tenantId,
            String operation,
            String key,
            Long orderId);

    Mono<CommandReceipt> findReceipt(
            Long tenantId,
            String operation,
            String key);
}
~~~

Implementations may use a custom repository, `DatabaseClient`, or `R2dbcEntityTemplate`. Inserting the receipt must rely on the database unique constraint; never replace it with an unprotected `SELECT`-then-`INSERT`.

### 5.2. Work inside the transaction

~~~java
private Mono<OrderResult> createOrderOnce(
        Long tenantId,
        String key,
        String requestHash,
        CreateOrderCommand command) {

    return receiptRepository.insertReceipt(
                    tenantId, "CREATE_ORDER", key, requestHash)
            .then(orderRepository.save(
                    Order.newOrder(command.customerId(), command.totalAmount())))
            .flatMap(saved -> receiptRepository.completeReceipt(
                            tenantId, "CREATE_ORDER", key, saved.getId())
                    .thenReturn(OrderResult.from(saved)));
}
~~~

This method only describes the work placed inside the transaction. In production, the transaction boundary must wrap the entire publisher chain. If inserting the receipt hits a duplicate, the error must terminate and roll back the current transaction before reading the prior receipt.

### 5.3. Wrapping the transaction with TransactionalOperator

~~~java
public Mono<OrderResult> createOrder(
        Long tenantId,
        String key,
        String requestHash,
        CreateOrderCommand command) {

    Mono<OrderResult> oneAttempt = transactionalOperator.transactional(
            createOrderOnce(tenantId, key, requestHash, command));

    return oneAttempt;
}
~~~

In Spring applications, `TransactionalOperator` must be configured with an `R2dbcTransactionManager` backed by the same `ConnectionFactory` as the repositories. Reactive `@Transactional` on a service method can be used instead, provided calls go through the transaction proxy and all operations remain within the publisher chain.

## 6. Handling Duplicate Requests and Returning the Prior Result

When the receipt already exists, the server must:

1. Read the receipt by tenant, operation, and key.
2. Compare the request hash.
3. If the hashes differ, return a conflict because the key was reused for another payload.
4. If the hashes match and the receipt is complete, load the business result or reconstruct the stored response.
5. If the receipt is still in progress under a multi-stage workflow, return a processing status or wait per defined policy.

Example lookup logic:

~~~java
private Mono<OrderResult> returnExistingResult(
        Long tenantId,
        String key,
        String requestHash) {

    return receiptRepository.findReceipt(
                    tenantId, "CREATE_ORDER", key)
            .switchIfEmpty(Mono.error(new IllegalStateException(
                    "Receipt conflict occurred but no receipt is visible yet")))
            .flatMap(receipt -> {
                if (!receipt.requestHash().equals(requestHash)) {
                    return Mono.error(new IdempotencyKeyReuseException(key));
                }

                if (receipt.resultOrderId() == null) {
                    return Mono.error(new OperationStillProcessingException(key));
                }

                return orderRepository.findById(receipt.resultOrderId())
                        .map(OrderResult::from);
            });
}
~~~

When the receipt and order share one transaction, the completed receipt is committed only when the order is saved. Thus, a duplicate request hitting the unique conflict can generally read a complete receipt. If the system uses a multi-stage workflow committing a separate `PROCESSING` state, add leases, timeouts, a recovery worker, and rules for stalled states.

### 6.1. Catch duplicate keys outside the failed transaction

A unique constraint violation in PostgreSQL puts the current transaction into an error state until rollback. Therefore, never catch `DuplicateKeyException` and query the receipt inside the same failed transaction.

Place the lookup outside the transaction operator:

~~~java
public Mono<OrderResult> createOrderIdempotently(
        Long tenantId,
        String key,
        String requestHash,
        CreateOrderCommand command) {

    Mono<OrderResult> transaction = transactionalOperator.transactional(
            createOrderOnce(tenantId, key, requestHash, command));

    return transaction.onErrorResume(
            this::isIdempotencyReceiptConflict,
            error -> returnExistingResult(tenantId, key, requestHash));
}
~~~

`isIdempotencyReceiptConflict` must identify the specific unique constraint on the receipt table rather than treating every `DuplicateKeyException` as a duplicate request. Violations of other unique constraints, such as email or order number, are distinct business errors.

While the first transaction is still running, a second receipt insert may wait for the unique index to resolve. If the first transaction commits, the second request receives a conflict; if the first rolls back, the second can insert the receipt and create the order. Exact locking semantics vary by database, yet the unique constraint acts as the synchronization point between concurrent requests.

## 7. Controlled Retries in Reactor

Reactor provides retry operators, though retrying means resubscribing to the source publisher. For a write publisher, that can re-execute the write statement.

### 7.1. Never blind-retry write operations

Avoid:

~~~java
return orderRepository.save(order)
        .retry(1);
~~~

This code fails to distinguish transient errors safe to retry from errors where the database committed while the acknowledgement was lost. If the initial command succeeded, each retry can create an extra order.

### 7.2. Retry only connection failures considered transient

Once a durable idempotency key is in place, you can retry the entire transaction using the same key and request hash:

~~~java
Mono<OrderResult> oneAttempt = transactionalOperator.transactional(
        createOrderOnce(tenantId, stableKey, requestHash, command));

return oneAttempt
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
                .filter(this::isTransientConnectionFailure))
        .onErrorResume(
                this::isIdempotencyReceiptConflict,
                error -> returnExistingResult(tenantId, stableKey, requestHash));
~~~

This is an illustrative structure. Implement an exception classifier matching your driver/database and ensure duplicate receipt conflicts are never retried as network failures. Retries must open a fresh transaction per attempt; wrap one execution in the transaction boundary and place retry outside that boundary.

If the first attempt committed while the acknowledgement dropped, the next attempt with the same key will not create a second order. It encounters the existing receipt and switches to reading the prior outcome.

### 7.3. Cap retries and use backoff

Retries should specify maximum attempts, exponential backoff or bounded delays, jitter when multiple instances may retry concurrently, an overall timeout, transient failure filters, metrics, and logs.

Never retry infinitely. Aggressive retries can overwhelm the database right when it is already struggling.

### 7.4. Never regenerate keys on each attempt

Compute the key and request hash before constructing the retryable publisher:

~~~java
String stableKey = command.idempotencyKey();
String requestHash = requestHasher.hash(command);

Mono<OrderResult> work = createOrderIdempotently(
        tenantId, stableKey, requestHash, command);
~~~

Never place UUID generation or command creation inside a supplier resubscribed by Reactor. Every attempt for the same intent must carry the same key.

## 8. When Is a Business Unique Constraint Enough?

Some domains have natural unique identifiers, such as an order number, a payment provider reference, a per-tenant invoice number, or a processed source event ID.

A unique constraint on that identifier can prevent duplicate rows:

~~~sql
ALTER TABLE payments
ADD CONSTRAINT uk_payment_provider_reference
UNIQUE (provider_name, provider_reference);
~~~

If the same payment is retried, the database rejects the duplicate reference. The application can then read the existing payment to determine the outcome.

However, a unique business key is sufficient only when that identifier truly represents a single business intent. If one customer can legitimately place multiple identical orders, you cannot arbitrarily enforce uniqueness on customer ID + amount.

Idempotency keys generally suit request/API boundaries; unique business keys suit identifiers inherently unique in the domain. Both can be used together.

## 9. Upsert Does Not Automatically Solve Everything

Some databases support upsert syntax such as PostgreSQL `ON CONFLICT` or MySQL `ON DUPLICATE KEY UPDATE`. Upserts can be helpful when writing a projection or state keyed by a stable identifier.

PostgreSQL example:

~~~sql
INSERT INTO order_requests (tenant_id, idempotency_key, request_hash)
VALUES (:tenantId, :key, :requestHash)
ON CONFLICT (tenant_id, idempotency_key) DO NOTHING;
~~~

If no row was inserted because the key already exists, the application reads the prior receipt and checks the hash. This claims the key without catching a unique constraint exception, yet you must still read the outcome and validate the payload hash.

Do not apply upserts mechanically to order creation. If the `UPDATE` branch overwrites data or fires triggers/side effects, retries can still mutate state unexpectedly. An upsert is idempotent only when the full semantics of the conflict branch are safe under repeated execution.

`ON CONFLICT` and `ON DUPLICATE KEY UPDATE` are database-specific syntax. Verify dialect, R2DBC driver, and Spring Data parameter binding when using native SQL.

## 10. Distinguishing Database Idempotency from External Side Effects

An R2DBC transaction protects only database resources participating in that transaction. It cannot roll back an already-sent HTTP request, an email already dispatched, a payment already captured by a provider, or a message already accepted by a broker.

Example:

1. Insert order and commit successfully.
2. Call a payment provider to capture funds.
3. The provider captures funds, yet the response drops.
4. The application retries and captures again.

A database idempotency receipt alone does not stop the provider from capturing twice unless requests to the provider carry matching deduplication protection.

### 10.1. Propagate idempotency keys to external providers

If the provider supports idempotency keys, pass the same key on every call for the same business operation. Persist the provider reference and status to query state when responses drop.

Never generate a new key per provider call. The key must represent the same payment intent across retries.

### 10.2. Use a transactional outbox for messages/events

When events must be emitted after saving an order, write both the order and an outbox record in the same transaction:

~~~text
R2DBC Transaction:
  INSERT order
  INSERT outbox_event
  COMMIT

Worker:
  read unsent outbox rows
  publish event
  mark as sent
~~~

If the worker publishes successfully yet loses acknowledgement before marking the row sent, the event may be published again. Consumers need an inbox/deduplication key or idempotent processing.

An outbox guarantees the business change and the intent to publish are persisted together. It does not make message delivery end-to-end exactly-once by itself.

### 10.3. Consumer inbox

Consumers can persist the event ID with a unique constraint in the same transaction that processes the data:

1. Claim the event ID in the inbox.
2. If it already exists, skip the duplicate event or return the prior processed result.
3. If new, perform the business mutation.
4. Commit both the inbox record and the business mutation in the same transaction.

This pattern lets at-least-once message delivery avoid duplicating database effects.

## 11. Timeouts, Cancellation, and Transaction State

In R2DBC, an application-side timeout or cancellation does not prove the database failed to write data.

Cases to distinguish:

- Request timed out before the statement was sent.
- Statement was executing and the driver sent a cancellation.
- Database executed the statement, yet the transaction had not committed.
- Commit reached the database, yet the acknowledgement was lost.
- Application terminated after commit but before returning an HTTP response.

Depending on exact timing, the database may have rolled back or committed. Once the connection drops, the application cannot rely on a rollback sent over that same connection to confirm state.

### 11.1. Do not treat timeout as proof of rollback

~~~java
return orderRepository.save(order)
        .timeout(Duration.ofSeconds(2));
~~~

If a timeout occurs, the publisher emits `TimeoutException`. That does not prove the order never committed. Never create a new order under a different key just to "try again safely."

### 11.2. Look up by idempotency key over a fresh connection

After an ambiguous failure, the application can open a new connection to look up the receipt:

~~~java
return createOrderIdempotently(...)
        .onErrorResume(this::isAmbiguousConnectionFailure,
                error -> returnExistingResult(tenantId, key, requestHash));
~~~

This outlines the recovery flow. If the receipt is not visible yet at lookup time, the prior transaction may still be resolving on the database or cleaning up its connection. You may need to retry claiming with the same key under bounded timeout/backoff rather than immediately declaring failure and generating a new key.

### 11.3. TransactionalOperator cannot eliminate commit ambiguity

`TransactionalOperator` opens, commits, or rolls back transactions along the publisher lifecycle. Yet if the connection drops right during commit, the client still cannot know whether commit succeeded. The transaction manager can attempt rollback or connection cleanup, but receiving an exception never guarantees the database did not commit.

An idempotency record persisted in the same transaction as business data is what lets you query final state afterward over a fresh connection.

## 12. Designing Idempotent APIs

An order creation API can follow this contract:

1. Client sends `Idempotency-Key` for each order creation intent.
2. Client reuses the same key if no response arrives and retries are needed.
3. Server authenticates tenant and validates payload.
4. Server computes a normalized payload hash.
5. Server claims the key using a unique constraint.
6. Server creates the order and persists the receipt result in the same transaction.
7. Repeated requests with the same key and payload receive the stored outcome.
8. Repeated requests with the same key and a different payload receive a conflict.

Example response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "orderId": 4821,
  "status": "CREATED"
}
~~~

When an identical request arrives with the same key, the server can return the same body and status under its API policy. You can add a header indicating the response was replayed if the contract requires distinguishing replays.

### 12.1. Keys do not replace authorization

Receipts must be queried within the authenticated tenant/client scope. Never allow another user to read a business outcome merely by knowing a key.

### 12.2. Key retention policy

Receipts must be retained longer than clients, gateways, jobs, or providers might retry. Deleting keys too early lets late retries execute as new operations.

For financial workflows or long-lived data creation, retain idempotency records long-term or enforce unique business references instead of purging on a short TTL.

## 13. Observability and Operations

Record the following in logs/metrics:

- Operation and idempotency key (hashed/masked if needed).
- Authenticated tenant or client ID.
- Request hash or payload version, avoiding sensitive fields.
- Key claim outcome: new, existing, or payload mismatch.
- Retry attempt count and exception type.
- Transaction duration, connection acquisition duration, and commit duration if measurable.
- Final receipt state: completed, processing, or failed per your state model.
- Provider reference when external side effects exist.

Useful metrics include:

| Metric | Meaning |
| --- | --- |
| `idempotency_requests_total` | Total requests carrying a key |
| `idempotency_replays_total` | Requests served a previously stored outcome |
| `idempotency_payload_conflicts_total` | Cases with matching key but mismatched payload |
| `write_ambiguous_failures_total` | Write failures with uncertain commit outcomes |
| `write_retry_attempts_total` | Retry attempts on write operations |
| `idempotency_processing_age` | Age of receipts still in processing state |

Avoid logging raw keys or sensitive payloads unnecessarily. Use correlation IDs to connect logs across APIs, workers, and providers.

## 14. Common Design Mistakes

| Design/mistake | Risk | Solution |
| --- | --- | --- |
| Retrying every `save()` exception | Duplicate writes after commit with lost acknowledgement | Classify errors and use idempotency keys |
| Generating a new key per retry | Each attempt is treated as a brand-new request | Keep keys stable for the same intent |
| `SELECT`-checking key then `INSERT`ing | Two concurrent requests both pass the check | Enforce unique constraint and handle conflicts |
| Writing receipt and order in separate transactions | Receipt can exist without order or vice versa | Write both in the same transaction |
| Catching duplicate and querying in failed transaction | Database may mark the transaction aborted | Let transaction roll back, then query on a fresh connection/transaction |
| Treating every duplicate key as a replay | Can mask unrelated business unique constraint errors | Match the exact receipt constraint |
| Not comparing request hashes | Same key with different payload gets wrong result | Hash normalized payload and return conflict |
| Using an in-memory map | Protection lost on restart or across instances | Persist receipts durably with a unique constraint |
| Using upsert without checking side effects | Triggers or update branches may repeat effects | Define conflict branch semantics explicitly |
| Assuming timeout means rollback | Recreates an already-committed operation | Reconcile using the stable key |
| Including slow HTTP calls in DB transactions | Holds connections long and cannot roll back providers | Use outbox/saga and provider-level idempotency |
| Purging receipts too early | Late retries produce duplicate records | Match retention to retry windows and domain needs |

## 15. Testing Dropped Acknowledgements

A test checking only that a repository returns success cannot prove the system prevents duplicate writes. Simulate scenarios where the database commits yet the application receives no response.

### 15.1. Testing duplicate requests with the same key

Prepare an order creation request with key `K`:

1. Send the first request and verify one order and one receipt exist.
2. Resend the same key and same payload.
3. Verify the second response references the same order ID.
4. Verify total created orders remains one.

### 15.2. Testing same key with different payload

1. Send key `K` with total amount 100.
2. Resend key `K` with total amount 500.
3. Verify the server returns a conflict.
4. Verify the original order remains unchanged.

### 15.3. Testing two concurrent requests

Launch two concurrent requests with identical tenant, operation, key, and payload over two independent connections/transactions. Verify only one claims the key and creates the order; the other waits or receives a conflict and reads the prior result; both final responses reference the same order; and neither two receipts nor two orders exist for that key.

### 15.4. Testing failure before commit

Inject an error after inserting the receipt and before commit. Verify both the receipt and the order roll back. Then resend the same key and verify the request can succeed.

### 15.5. Testing successful commit with dropped response

Use fault injection at the network/proxy layer or test harness to:

1. Let the database commit the transaction.
2. Block or close the connection before the acknowledgement reaches the application.
3. Let the caller receive a timeout or connection error.
4. Resend the same key.
5. Verify the server returns the stored result without creating a second order.

This is the most critical test for this lesson's scenario. Dropping the connection before sending SQL fails to simulate lost acknowledgements after commit.

### 15.6. Testing external side effects

If creating an order triggers payments or publishes messages, verify the provider receives the same idempotency key across retries, the outbox loses no events across process restarts, consumers deduplicate event IDs, and redelivered events cause no duplicate side effects.

## 16. Example Service Test with StepVerifier

~~~java
@Test
void sameKeyAndSamePayloadShouldReturnSameOrder() {
    CreateOrderCommand command = new CreateOrderCommand(7L, new BigDecimal("100.00"));
    String key = "client-request-123";
    String hash = requestHasher.hash(command);

    Mono<OrderResult> first = service.createOrderIdempotently(1L, key, hash, command);
    Mono<OrderResult> replay = service.createOrderIdempotently(1L, key, hash, command);

    StepVerifier.create(first)
            .assertNext(result -> assertThat(result.orderId()).isNotNull())
            .verifyComplete();

    StepVerifier.create(replay)
            .assertNext(result -> assertThat(result.orderId()).isEqualTo(
                    findPreviouslyCreatedOrderId()))
            .verifyComplete();
}
~~~

This snippet illustrates the concept; real tests should capture the first ID from the result directly for comparison and query the database to confirm only one order exists. Never use an out-of-transaction helper if the test needs to verify atomicity between receipt and order.

## 17. Checklist for Designing Retryable Write Operations

- [ ] Identified whether repeating the operation creates duplicate records or side effects.
- [ ] Client generates and retains a stable idempotency key per intent.
- [ ] Keys are scoped by tenant/client and operation.
- [ ] Database enforces a unique constraint protecting the key.
- [ ] Payload hash is stored and compared whenever a key is reused.
- [ ] Receipt and business mutation are persisted inside the same transaction.
- [ ] Duplicate receipts are handled after the attempted transaction rolls back.
- [ ] Retries apply only to classified transient errors and are bounded.
- [ ] Every retry reuses the exact same key and request hash.
- [ ] External side effects have dedicated idempotency/outbox/inbox mechanisms.
- [ ] Receipts are retained long enough to cover the full retry window.
- [ ] Tests cover concurrent duplicates, pre-commit rollback, and dropped acknowledgements after commit.

## 18. Handling Flow When Connection Drops After a Write

~~~mermaid
flowchart TD
    A[Receive command and idempotency key] --> B[Compute request hash]
    B --> C[Start reactive transaction]
    C --> D[Insert receipt with unique key]
    D --> E{Key claim succeeded?}
    E -->|Yes| F[Write business data]
    F --> G[Save result reference in receipt]
    G --> H[COMMIT]
    H --> I{Caller received acknowledgement?}
    I -->|Yes| J[Return result]
    I -->|No| K[Caller sees ambiguous outcome]
    E -->|No, key exists| L[Roll back attempted transaction]
    L --> M[Read receipt using fresh transaction/connection]
    K --> N[Retry or look up with same key]
    N --> M
    M --> O{Request hash matches?}
    O -->|No| P[Return conflict]
    O -->|Yes and completed| Q[Return stored result]
    O -->|No result yet| R[Wait/reclaim per recovery policy]
~~~

## 19. Conclusion

Connection loss after the database has written can cause the application to receive an error even though the transaction committed. Because callers cannot deduce commit state solely from timeouts or connection resets, retrying an unprotected insert or update can create duplicate data or repeat side effects.

Make write operations replay-safe using a stable idempotency key, a unique constraint, and a request hash. Persist the receipt alongside business changes in one transaction; when an existing key is encountered, read the stored outcome after the attempted transaction rolls back and return that result. Retry only transient failures with bounded attempts while reusing the same key. For messages or external services, add an outbox/inbox or provider-level idempotency because R2DBC transactions cannot roll back side effects in external systems.

Tests must include the case where the database commits yet the acknowledgement is lost. When properly designed, a request can be submitted multiple times while a single business intent produces only one data effect within the boundary protected by idempotency.
