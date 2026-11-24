# Retries unsafe with side effects

In Spring Batch, retry allows re-attempting an operation when encountering a recoverable error. However, retrying can cause a piece of code to execute multiple times. If that code produces side effects outside the current transaction, a retry attempt may repeat the action even though the previous attempt actually succeeded.

For example, a writer sends a payment request to a partner API. The partner receives and processes the payment, yet the response times out on the way back. The application sees only a timeout and assumes the request failed. If Spring Batch retries the writer, the same request may be sent again and the customer is charged twice.

The core risk is **not knowing for certain whether the previous attempt already produced the side effect**. A database rollback cannot recall an HTTP request, an email, a published message, or a file written in another system. Therefore, before configuring retry for a reader, processor, writer, or Tasklet, identify which side effects might repeat, whether deduplication exists, and how to reconcile ambiguous outcomes.

## 1. What is a side effect?

A side effect is an observable change outside the pure computation result of a method. In Batch Jobs, common examples include:

- Sending HTTP requests to create orders, charge payments, book reservations, or update partner systems.
- Sending emails, SMS, or push notifications.
- Publishing messages to Kafka, RabbitMQ, or another broker.
- Writing, renaming, moving, or deleting files.
- Writing data to another database not participating in the Step's transaction.
- Calling a service that mutates state in an external system.
- Updating a business counter or status in a resource not managed by the current transaction.

Read operations can also have side effects if an API writes audit records, consumes messages, marks records as read, or advances a server-side cursor. Do not assume every call named `get` or `read` is completely free of side effects.

Conversely, computations such as string normalization, condition checks, calculating tax from already-loaded data, or constructing a new object usually produce no external side effects. Such computations fit `ItemProcessor` better because they can be re-invoked without altering external systems.

## 2. Why can retry repeat side effects?

In a chunk Step, the reader, processor, and writer can be re-invoked during retries or when chunk rollbacks are handled under fault-tolerance policies. The writer can receive the same chunk or a related group of items again during error recovery. Hence, code inside these components must never assume it runs strictly once.

A common scenario with APIs:

```text
Spring Batch                         Partner API
     |                                   |
     |---- POST /payments -------------->| 
     |                                   | Payment processed successfully
     |<--- Response lost / timeout ------X
     |
     | Unknown whether API processed it
     |
     |---- Retry POST /payments -------->| 
     |                                   | May create a second payment
```

The application receives a timeout, yet a timeout only means the client did not receive a response in time. It does not prove the server never executed the request. The server may have committed the change just before the connection dropped or the response was lost.

Similar scenarios:

| Side effect | Situation after first attempt | Risk on retry |
|---|---|---|
| Payment API | Partner charged payment but response timed out | Double charging. |
| Sending email | Mail server accepted message but client disconnected before ACK | Recipient gets duplicate emails. |
| Publishing message | Broker persisted message but producer missed ACK | Message published multiple times. |
| Writing file | File written but Job failed before updating metadata | Overwriting, appending, or creating duplicate files. |
| Separate database | Target database committed, metadata database did not | Writing the same record repeatedly or state divergence. |
| Booking/reservation | External system reserved slot but response timed out | Creating multiple reservations. |

Retry is safe only when the operation can be repeated without causing inconsistency, or when the system can recognize and handle duplicate requests.

## 3. Chunk transactions cannot roll back external systems

A chunk Step normally runs within a transaction managed by the configured `PlatformTransactionManager`. If the writer writes to the same database and the same transaction, uncommitted changes can be rolled back when the chunk fails.

```text
Chunk transaction
  |
  +--> INSERT orders
  +--> UPDATE batch_status
  +--> Exception
  +--> ROLLBACK changes participating in transaction
```

However, a standard JDBC transaction does not cover every resource your code may call:

```text
JDBC Transaction                    External System
  |                                      |
  +--> INSERT orders                     |
  |                                      |
  +--> HTTP POST ----------------------->| Request already processed
  |                                      |
  +--> Exception                         |
  +--> ROLLBACK database                 | Does not auto-rollback
                                         |
                                         +--> Side effect still exists
```

A transaction manager coordinates only the resources enlisted in the transaction it manages. Calling an HTTP client, writing local files, or sending emails does not automatically enlist in a JDBC transaction. If a Job uses two datasources with two independent transaction managers, committing one database is not atomic with the other either.

Therefore, "chunk rollback" does not mean "every action in the chunk is undone." Identify which transaction governs each side effect.

## 4. Retry in an ItemProcessor with side effects

`ItemProcessor` is designed to transform or validate individual items. When a processor calls an external service that mutates state, retrying can repeat that mutation.

Unsafe example:

```java
public class PaymentProcessor
        implements ItemProcessor<OrderInput, PaymentResult> {

    private final PaymentClient paymentClient;

    @Override
    public PaymentResult process(OrderInput order) {
        // Side effect: partner may charge payment right here.
        return paymentClient.charge(order.orderId(), order.amount());
    }
}
```

If `charge` succeeds on the server while the client times out, the processor throws an exception. When the exception is retried, `charge` may execute a second time.

A safer design is for the processor to construct a pure command and persist the execution intent into the database inside the chunk transaction:

```java
public record PaymentCommand(
        String paymentId,
        String orderId,
        BigDecimal amount) {
}

public class PaymentCommandProcessor
        implements ItemProcessor<OrderInput, PaymentCommand> {

    @Override
    public PaymentCommand process(OrderInput order) {
        String paymentId = "payment-for-order-" + order.orderId();
        return new PaymentCommand(
                paymentId,
                order.orderId(),
                order.amount());
    }
}
```

The processor only computes the command and derives a stable business identifier. It does not transmit the payment. The writer can save the command as an outbox record in the same transaction as the order data.

## 5. Idempotency: making repeated operations safe

An operation is idempotent if executing it multiple times with the same identifier and same data produces no additional changes beyond the initial execution's outcome. For example, "set order status to `PAID`" can be idempotent if the update keys on business ID and target state; "add 100,000 VND to balance" is usually not idempotent without a unique transaction ID.

### Idempotency key

When calling an API with side effects, generate a stable idempotency key for one business operation. The same operation must use the same key across all retries.

Example:

```java
String idempotencyKey = "charge-order-" + order.orderId();

paymentClient.charge(
        order.orderId(),
        order.amount(),
        idempotencyKey);
```

The target API must genuinely support this key. Typically, the server stores the key alongside the processing result; if it receives an already-stored key again, the server returns the saved result instead of applying the side effect again.

A good idempotency key should be:

- Stable across retries, rollbacks, and restarts of the same business operation.
- Representative of exactly one business action, not merely one HTTP call.
- Never newly randomized on each retry attempt.
- Persisted or deterministically derived from the business key and operation type.
- Clearly scoped for uniqueness, such as per tenant or merchant if required by the target system.

If the same order can legitimately have multiple charges, using only `orderId` may be insufficient. The key must include the payment attempt or business operation ID to distinguish two valid payments from a duplicate request.

### Idempotency on the target system side

Sending a key from the client is not enough to guarantee safety. The receiving system must check and persist the key atomically with the side effect. If the server only logs the key after charging, a process crash between the two operations can still cause a double charge.

For target databases, you can use a unique constraint on the operation ID or a deduplication table. For partner APIs, read the API contract to confirm semantics, key retention duration, key scope, and how to query prior results.

## 6. Outbox pattern for external side effects

Transactional outbox is a common pattern for decoupling primary data changes from sending external requests/messages.

Within the chunk transaction, the writer writes business data and an outbox record in the same database transaction. A separate relay process reads unsent outbox records, calls the external system, and then marks them sent.

```text
Chunk transaction
  |
  +--> INSERT/UPDATE business data
  |
  +--> INSERT outbox(event_id, payload, status='PENDING')
  |
  +--> COMMIT
          |
          v
Outbox relay
  |
  +--> Read PENDING events
  |
  +--> Send to API/broker with event_id as idempotency key
  |
  +--> Mark SENT
```

If the chunk rolls back, both business data and the outbox record roll back together. No outbox record exists for the relay to send. Once the chunk commits, the intent to emit the side effect is durably stored and can be relayed afterward.

### Example outbox schema

```sql
CREATE TABLE batch_outbox (
    event_id       VARCHAR(100) PRIMARY KEY,
    event_type     VARCHAR(100) NOT NULL,
    aggregate_id   VARCHAR(100) NOT NULL,
    payload        TEXT NOT NULL,
    status         VARCHAR(20) NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    sent_at        TIMESTAMP NULL
);
```

`event_id` must be unique and stable. You can add attempt counts, `next_attempt_at`, last error, lease/lock owner, and indexes to support relay queries.

### Writer saving outbox inside the transaction

Illustrative writer persisting commands into the outbox table:

```java
public class PaymentOutboxWriter implements ItemWriter<PaymentCommand> {

    private final JdbcTemplate jdbcTemplate;

    public PaymentOutboxWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends PaymentCommand> chunk) {
        for (PaymentCommand command : chunk) {
            jdbcTemplate.update("""
                    INSERT INTO batch_outbox
                        (event_id, event_type, aggregate_id,
                         payload, status, created_at)
                    VALUES (?, 'PAYMENT_REQUESTED', ?, ?, 'PENDING', CURRENT_TIMESTAMP)
                    """,
                    command.paymentId(),
                    command.orderId(),
                    serialize(command));
        }
    }
}
```

For the outbox to be truly atomic with business data, `JdbcTemplate` must use the datasource/transaction manager participating in the chunk's transaction. A unique constraint on `event_id` is required. If the writer is re-invoked, duplicate key errors must be handled according to designed semantics; do not catch all insert errors and ignore them, as that can mask unrelated data errors.

### The relay still needs idempotency

An outbox does not provide exactly-once delivery to external systems. The relay may send a request successfully and crash before updating `status = 'SENT'`. When it restarts, the relay will send the same event again.

Therefore, the relay should:

- Use `event_id` as the idempotency key when calling APIs or publishing messages.
- Use claims/leases or locking so multiple relays do not process the same event concurrently by accident.
- Update status only after receiving a successful response.
- Retry transient errors with appropriate backoff and limits.
- Record final failure status for investigation.
- Have a reconciliation process for ambiguous outcomes.

The outbox guarantees the side-effect intent is not lost when the business transaction commits; idempotency at the consumer/target handles duplicate relay deliveries.

## 7. Inbox or consumer deduplication

If a Batch Job publishes messages to a broker, consumers can receive the same message multiple times due to producer retries, broker redeliveries, or consumer crashes after processing but before ACK.

The Inbox pattern stores the processed `message_id` alongside the consumer's business changes within a single transaction:

```text
Message arrives at consumer
       |
       v
BEGIN transaction
       |
       +--> INSERT inbox(message_id) with unique key
       |
       +--> If key exists: do not reprocess
       |
       +--> If key is new: apply business change
       |
       +--> COMMIT
       |
       v
ACK message
```

If the consumer crashes before commit, both the inbox record and the business change roll back; the message can be redelivered and processed. If the transaction commits yet the ACK is lost, the message is redelivered, but the unique key in the inbox prevents the business side effect from running twice.

The inbox must share an appropriate transaction with the business data. Storing `message_id` in one database and updating primary data in another introduces another non-atomic gap.

## 8. Sending emails and notifications

Sending emails is a side effect that cannot be rolled back. If an SMTP server accepts an email while the client times out waiting for the response, retrying can send duplicate emails.

Options:

- Write notification intent into an outbox inside the chunk transaction.
- Use a provider supporting idempotency or request IDs where available.
- Include the business event ID in metadata to detect duplicate notifications on the receiving side if supported.
- Accept at-least-once semantics if the provider lacks deduplication and the business accepts potential duplicates.
- Record delivery status and maintain a lookup/reconciliation procedure for ambiguous results.

Do not send emails directly inside `ItemProcessor` or `ItemWriter` expecting a database transaction rollback to recall the message.

## 9. Writing files and filesystems

Writing files is also a side effect outside database transactions. If a writer creates a file and the chunk rolls back or the Job crashes before updating metadata, a retry/restart may write the file again.

Ways to reduce risk:

- Write to a temporary file whose name includes the business operation ID.
- Flush and close the file before publishing the final file.
- Use atomic rename/move if supported by the filesystem and source/destination share the same filesystem.
- If the target file already exists, verify checksum, manifest, or business key before overwriting.
- Write completion markers/manifests via an idempotent operation.
- Persist export status in the database and reconcile files against metadata.

Example workflow:

```text
orders-2026-11-15.tmp
       |
       +--> write full content
       +--> flush/close
       +--> verify size/checksum
       +--> atomic move
       v
orders-2026-11-15.csv
```

If the process stops before the move, temporary files can be cleaned up or resumed per manifest. If it stops after the move yet before the Step records completion, a rerun must recognize the existing target file as the valid output of that operation instead of creating a second copy or overwriting unrelated data.

Atomic rename is guaranteed only at the filesystem level under specific conditions; it does not form a shared transaction with JobRepository. Metadata tracking and reconciliation are still necessary.

## 10. Writing to another database

If a writer updates a business database while JobRepository lives in a separate metadata database, identify the actual transaction manager in use. A standard JDBC transaction normally manages only a single datasource/connection transaction.

Cases:

- Business data and Batch metadata participate in a single managed transaction: commit/rollback can be atomic within that resource scope.
- Two datasources with independent transaction managers: committing one does not roll back the other.
- With XA/JTA: distributed transactions can coordinate across resources if all resources support and are properly configured for it, though operational cost and complexity are higher.
- Using an outbox or business operation table: often the practical way to coordinate data and side effects across systems.

Do not assume that because a writer is invoked inside a chunk, every database it connects to participates in the same transaction. Verify the transaction manager, datasources, and how repositories/clients obtain connections.

## 11. Safe retry for reader, processor, and writer

### Reader

Read retry is safe when a failed read does not advance the data source past unreturned items. For paginated APIs, use stable cursors; advance the cursor only after the response is confirmed and items enter the pipeline properly. For message queues, understand ACK/NACK semantics and transactional consumption.

If a read API has side effects like consuming tokens, claiming jobs, or marking records as read, use a request ID or recoverable lease. If it is impossible to tell whether the prior read consumed data, you need a status-lookup endpoint or deduplication.

### Processor

Process retry is safest when the processor acts nearly as a pure function: identical input and reference data yield output without altering external systems. If external services must be called, prefer read-only APIs; if an API mutates state, use an idempotency key and explicit timeouts.

### Writer

Write retry is safe when changes reside inside a rollbackable transaction or when the writer is idempotent. Database writers should use business keys/unique constraints/upserts per business rules. Message/API/file writers need an outbox, idempotency keys, or reconcilable operation states.

| Component | Question to answer before enabling retry |
|---|---|
| Reader | Could a failed read already have consumed/marked data at the source? Will re-invoking return the right item? |
| Processor | Does re-invoking for the same item cause side effects or mutate external state? |
| Writer | Could part or all of the output already have been accepted by the target system before the exception? Is deduplication present? |

## 12. Timeouts do not prove an operation failed

A timeout is an ambiguous outcome. The client did not receive a response on time, yet the server may already have executed the operation.

When encountering a timeout on an API with side effects, distinguish three states:

1. **Not processed:** the request never reached the server or the server rejected it before creating side effects.
2. **Already processed:** the server committed the side effect, while the response was lost or delayed.
3. **Unknown:** the client cannot determine the state from the current response.

Never treat the third state as a guaranteed failure and send a brand-new request. Safer handling:

- Resend with the same idempotency key if the API supports it.
- Query operation status using the business key/request ID.
- Reconcile state on the target system before creating a new request.
- If state cannot be determined, transition the operation to a state requiring reconciliation rather than retrying blindly.

## 13. Compensation when rollback is impossible

For side effects already committed in an external system, technical rollbacks usually cannot undo the action. Some business flows may need **compensation**: issuing another business action to offset the effect.

Examples:

- Payment already captured: create a refund transaction.
- Reservation already booked: send a cancel-reservation request.
- Credit limit already granted: issue a limit-revocation operation.
- Data already sent to partner: send an adjustment event or cancellation request.

Compensation is not an atomic rollback. It is a new action that can itself fail and also needs idempotency, retries, and auditing. Store the original operation, compensation status, and business key so you never refund or cancel twice.

For multi-system workflows, the Saga pattern can be used: each step runs a local transaction with a corresponding compensating action if a later step fails. Sagas fit long-running multi-resource workflows when distributed transactions are impractical.

## 14. Retry, Skip, and noRollback do not prevent duplicate side effects

Fault-tolerance mechanisms serve different purposes:

| Mechanism | Purpose | Automatically prevents duplicate side effects? |
|---|---|---|
| Retry | Re-attempt an operation after a recoverable error | No. Requires idempotency or deduplication. |
| Skip | Bypass a faulty item per policy | No. Side effects from an earlier attempt may already exist. |
| Rollback | Undo changes belonging to the current transaction | Does not undo HTTP calls, emails, files, or external resources. |
| `noRollback` | Suppress rollback for a specified exception | No; may even leave partial changes behind if misused. |
| RetryListener | Observe retry attempts | No; listeners neither decide nor deduplicate side effects. |
| Outbox/inbox | Persist intent and deduplicate delivery/consumption | Reduces loss/duplication via transactions and unique keys; consumers still need idempotent handling. |

Skipping after exhausting retries does not prove the first call failed. For example, a payment API may have captured funds while the client timed out on every attempt; if the exception is then skipped, the Job continues while the payment already exists. Query/reconcile the operation before marking an item as failed.

## 15. Why after-commit callbacks are not enough to guarantee delivery

A common idea is calling the API only after the transaction commits, such as via transaction synchronization or a post-chunk callback. This avoids sending requests while the database transaction might still roll back, yet leaves a gap:

```text
Database COMMIT succeeds
       |
       X  Process crashes before API-sending callback
       |
       v
Side effect never sent
```

An after-commit callback is not a durable queue. If the process terminates after commit but before the callback runs, the event can be lost. If the callback runs and the response times out, the outcome is again ambiguous.

Outbox closes this gap by persisting the send intent into the database inside the same transaction. An independent relay reads committed records and delivers them as needed. The relay still needs idempotency because it can send more than once.

## 16. Architecture example: Batch import and event publishing

Suppose a Job imports orders and must emit `OrderImported` to a fulfillment system.

Error-prone design:

```text
Reader -> Processor -> Writer
                         |
                         +--> INSERT orders
                         +--> POST fulfillment API
```

If the API succeeds while the database transaction rolls back, the fulfillment system knows about an order absent from the primary database. If the database commits while the API response times out and the writer retries, the fulfillment system may receive the event twice.

Design using outbox:

```text
Batch chunk transaction
  |
  +--> INSERT orders
  +--> INSERT outbox(OrderImported, event_id)
  +--> COMMIT
          |
          v
Outbox relay
  |
  +--> Publish event_id + payload
          |
          v
Fulfillment consumer
  |
  +--> INSERT inbox(event_id) with unique constraint
  +--> Process order if event_id is new
  +--> COMMIT
```

When the chunk rolls back, neither orders nor outbox events commit. When the chunk commits, the event is durably persisted. The relay can resend if no ACK arrives; the consumer uses an inbox so business changes are not applied twice.

## 17. Choosing a retry policy based on safe repeatability

Do not enable retries solely by classifying exception names. Consider the nature of the operation executing when the exception occurs.

| Scenario | Is retry safe? | Design approach |
|---|---|---|
| Pure database SELECT, no consume/claim | Usually yes | Bounded retry for connection/deadlock errors. |
| Pure computation processor | Usually yes | Keep processor stateless/pure. |
| HTTP GET without side effects | Usually yes, API-dependent | Use timeouts, retry/backoff, and limits. |
| HTTP POST creating payment, no idempotency | Unsafe when outcome unknown | Use idempotency key or status lookup before retrying. |
| Sending email via SMTP without deduplication | No guarantee against duplicate sends | Outbox, provider request ID, or accept at-least-once. |
| Database insert in chunk transaction | Can be safe if rollback truly covers the operation | Verify datasource/transaction manager and unique keys. |
| Publishing messages without deduplication | Can send duplicates | Outbox + inbox/dedup at consumer. |
| Appending to a shared file | Usually unsafe | Temporary file, record ID, manifest, and atomic move. |

Calling an error "transient" does not mean the operation is safe to repeat. For instance, a timeout is transient at the network level, yet a payment request may already have been processed. Both conditions are required: the error is recoverable and the operation has safe replay semantics.

## 18. Observing and reconciling side effects

Whenever an operation can be retried, persist enough information to know which attempts occurred and the final business status:

- Stable business operation ID.
- Idempotency key or event ID.
- JobExecution/StepExecution ID and business key.
- Attempt count, timestamps, and exception type.
- Final status: pending, confirmed, failed, unknown, or needs-reconciliation.
- Response/reference ID from the external system if available.

Do not store passwords, tokens, or sensitive payloads in logs. Use low-cardinality metric tags such as Job, Step, side-effect type, and exception category; never use individual order IDs as metric tags.

For ambiguous outcomes, build a reconciliation Step/Job that queries the target system by operation ID, reconciles status, and decides whether to resend, mark succeeded, or issue compensation. Never auto-retry indefinitely on operations that may have financial or business consequences.

## 19. Testing retries with side effects

Unit tests checking only mock call counts can miss real transaction and crash-timing bugs. Combine unit tests, integration tests, and failure-scenario testing.

Important scenarios:

1. API fails before processing request: retry succeeds on subsequent attempt.
2. API processes successfully while response times out: retry uses the same idempotency key and creates no second side effect.
3. Database rolls back after outbox record is written: neither business data nor outbox record exists.
4. Database commits while relay crashes before sending: relay sends event when restarted.
5. Relay sends successfully while crashing before marking SENT: resend is deduplicated by the consumer.
6. Consumer commits while ACK is lost: message redelivery does not re-apply business changes.
7. Writer re-invoked after rollback: output is not duplicated.
8. File moved while Step metadata not yet updated: restart recognizes output is already complete.
9. Retries exhausted: operation transitions to handling/reconciliation state as specified.

Test against transaction managers, databases, brokers, or API sandboxes close to production. Pure mocks do not prove transaction atomicity or target-system idempotency semantics.

## 20. Common mistakes

### Retrying a side-effecting POST without idempotency

Timeouts can occur after the server already processed the request. Use a stable idempotency key or query operation status before resending.

### Sending emails or publishing messages inside the processor

The processor can re-run for the same item. Decouple side effects from the processor; write intent to an outbox and process via a relay.

### Assuming database rollback cancels HTTP requests

JDBC transactions do not manage HTTP servers. External side effects persist after rollback.

### Generating a new idempotency key on every retry

A new key causes the server to treat the request as a new operation. Derive the key from the business operation and keep it unchanged across all attempts.

### Using an outbox without consumer deduplication

The relay may send the same event multiple times. Consumers need an inbox/unique message ID or idempotent handling.

### Marking SENT before sending

If the process crashes after marking SENT and before sending, the event is lost. Usually send first and mark afterward, while accepting potential duplicate sends handled via idempotency.

### Relying on afterCommit to guarantee events are never lost

The process can crash after database commit and before the callback executes. Persist intent durably in an outbox within the same transaction.

### Treating skip as a way to resolve ambiguous side effects

Skipping does not tell whether the external system processed the request. Query and reconcile the operation before deciding to skip or compensate.

### Treating compensation like automatic rollback

Compensation is a new action that can fail or repeat. It requires its own operation ID, idempotency, retries, and audit trail.

## 21. Decision workflow for retrying an operation

Before adding `.retry(...)` for an exception, answer these questions:

1. Is the exception truly transient, or does it reflect permanent data/configuration errors?
2. Could the operation have already produced a side effect before throwing the exception?
3. If the same operation is invoked again, will the target system recognize duplicate requests?
4. Is there a stable idempotency key or unique business key?
5. Which resources are covered by the current transaction, and which lie outside it?
6. If a response times out and the outcome is ambiguous, is there a status-lookup API?
7. When retries are exhausted, will the operation fail, skip, or enter a reconciliation queue?
8. Are outbox/inbox or compensation needed?
9. Do retry limits, backoff, and timeouts match the SLA?
10. Have you tested crashing between the side effect and metadata updates?

| Condition | Decision |
|---|---|
| Transient error, pure operation, or transaction fully rolls back | May retry with bounds. |
| Transient error while side effect may have occurred | Retry only with idempotency/status lookup/deduplication. |
| Permanent data error | Skip if business rules permit; otherwise fail. |
| Side effect without deduplication and ambiguous outcome | Do not retry blindly; route to reconciliation/manual review. |
| Multi-system flow without distributed transactions | Consider outbox/inbox or Saga/compensation. |

## Conclusion

Retry is unsafe when a prior attempt may already have caused a side effect whose outcome the application cannot verify—especially with HTTP POSTs, payments, emails, messages, files, and non-transactional databases. Chunk rollback only undoes resources participating in the transaction; it does not revoke actions already committed in other systems. Before enabling retry, make operations idempotent with stable keys, unique constraints, or deduplication; use transactional outbox/inbox to coordinate data and events; look up or reconcile status when timeouts yield ambiguous results; and use compensation where completed side effects must be offset by business logic. Retry policies, skips, and listeners do not enforce deduplication on their own—that guarantee must be designed at the business boundary and target system.
