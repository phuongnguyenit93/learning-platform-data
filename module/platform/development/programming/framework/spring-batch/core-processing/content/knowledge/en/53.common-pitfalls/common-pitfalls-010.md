# Calling a Remote Service Inside a Long Transaction: A Common Pitfall in Spring Batch

A Spring Batch Job often combines internal data processing with external services: looking up exchange rates, authenticating customers, calling fee calculation APIs, issuing invoices, pushing notifications, or syncing orders to partner systems. A common architectural mistake is **making HTTP/gRPC calls directly inside a chunk's long-running database transaction**.

When the remote service responds slowly, database transactions and connections can remain held for the entire network wait. If the remote service already executed the operation yet Spring Batch's database transaction rolls back, the two systems can fall out of sync. Naive retries can cause the external service to receive the same command multiple times.

In the **Common Pitfalls** group of **Spring Batch Core Processing**, this lesson explains why this happens, its impact on performance and reliability, how to spot it, strategies to split transactions, and how to test when the remote service fails.

**Core message:** Spring Batch's transaction manages the resources participating in that transaction; it **does not automatically turn an HTTP request into a rollbackable operation**. Do not place remote calls with side effects inside a long transaction expecting rollback to undo both systems.

## 1. Realistic Scenario

Suppose `invoiceSettlementJob` is responsible for:

1. Reading unpaid invoices from the database.
2. Computing amounts.
3. Calling `POST /payments` on an external payment service.
4. Writing paid invoice statuses back to the database.
5. Committing every 100 invoices.

A deceptively reasonable-looking setup:

```text
invoiceSettlementJob
  |
  v
settleInvoicesStep (chunk size = 100)
  |
  +-- ItemReader: reads invoices
  |
  +-- ItemProcessor: calls remote payment service
  |
  +-- ItemWriter: updates invoices table
  |
  +-- commit chunk
```

If each remote call takes 300 ms, 100 sequential calls alone consume roughly **30 seconds**, before counting database I/O, retries, or timeouts. In many chunk-oriented setups, the chunk's database transaction is already open throughout this stage.

If the remote service has a single request stall for 45 seconds due to a network timeout, the transaction stays open even longer. Resulting problems can include:

- Database connections held for long periods, starving available connections for the Job and other applications.
- Rows or database locks modified in the transaction held until commit/rollback.
- Growing pressure on transaction logs/WAL and MVCC/locking resources.
- On timeout, an entire large chunk may roll back and require reprocessing.
- The remote service may have received and executed the request even if the client missed the response.
- When the framework retries, the same invoice may be sent multiple times to the remote service.
- The job slows down, overruns its processing window, and collides with the next scheduled run.

The hardest part is not only the **long transaction**, but the **lack of atomicity between the database and the remote system**.

## 2. Where Does Spring Batch Place Transactions?

For a chunk-oriented Step, Spring Batch typically executes reading, processing, and writing of a chunk inside a transaction boundary managed by `PlatformTransactionManager`.

Conceptual flow:

```text
Chunk transaction START
    |
    +-- read item 1
    +-- process item 1
    +-- read item 2
    +-- process item 2
    |       ...
    +-- read/process item N
    |
    +-- write chunk
    |
Chunk transaction COMMIT
```

Spring Batch 5.x example:

```java
@Bean
Step settlementStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Invoice> reader,
        ItemProcessor<Invoice, Invoice> processor,
        ItemWriter<Invoice> writer) {

    return new StepBuilder("settlementStep", jobRepository)
            .<Invoice, Invoice>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

This is a conceptual configuration; `Invoice` and the reader/processor/writer must be supplied by the application. In Spring Batch 6.x, packages and some Step builder APIs change per version; use the right dependencies.

**Key point:** Moving an HTTP call from `ItemWriter` to `ItemProcessor` or `ItemReader` **does not automatically move the call outside the transaction**. In a chunk-oriented Step, all of these components are normally invoked within the transactional chunk scope.

Adding `@Transactional` to a service called by the processor also does not shorten the transaction. Under the default `REQUIRED` propagation, the service joins the existing transaction. Using `REQUIRES_NEW` spawns another database transaction while the outer transaction remains open and waiting; it does not make HTTP transactional with the database.

### Transactions in `TaskletStep`

Not only chunks: a `Tasklet` executing in a `TaskletStep` is also normally wrapped by Spring Batch in a transaction per Step configuration. Moving remote calls into a single Tasklet does not inherently solve the problem. You must **intentionally design transaction boundaries**, not infer them from Step type names.

### What Can a Transaction Hold?

Not every transaction locks an entire table for its whole duration. The exact impact depends on:

- DBMS and isolation level.
- SQL statements already executed before the remote call.
- Row-level locks, index locks, optimistic/pessimistic locking.
- How the reader opens cursors and connections.
- Driver/pool, flushing, and when DB connections are borrowed.
- Concurrent load and transaction lifetime.

A read-only transaction may hold no write locks, yet can still pin a snapshot or connection and affect MVCC/vacuum cleanup depending on the database. Always observe the real system rather than claiming every long transaction locks all data.

## 3. Why Are Remote Calls Dangerous Inside a Transaction?

### 3.1. Network Latency Has No Reliable Upper Bound

An HTTP call can incur:

```text
DNS lookup
  + TCP connect
  + TLS handshake
  + network latency
  + remote queue
  + remote business processing
  + response transfer
  + proxy/load-balancer retries
```

A 100 ms average does not mean P99 is 100 ms. A few tail-latency requests can stretch out an entire chunk. Calling N requests sequentially inside one transaction compounds wait times.

### 3.2. Occupying Connections and Causing Lock Contention

Suppose the pool has 10 connections and 8 Batch workers hold transactions while waiting on an API. The rest of the application has very few connections left. Other requests queue on `getConnection()` and may time out.

If the worker already ran `UPDATE invoices SET status = 'PROCESSING'` before calling remote, locks on those rows can persist for the entire wait. Other transactions trying to modify the same invoices must wait.

The impact cascades: a slow remote service causes **database congestion**, even though the database was not the original fault.

### 3.3. No Distributed Rollback for Plain HTTP

Database transactions and HTTP requests are two systems with separate commit mechanisms:

```text
Spring Batch / DB                     Remote payment service
-----------------                     ----------------------
BEGIN TX
UPDATE invoice...
POST /payments --------------------->  charge succeeds
                                <----- HTTP 200
UPDATE invoice status...
DB COMMIT -> FAILS

Result:
  Database: invoice is not marked paid
  Remote:   payment already succeeded
```

A database rollback **does not automatically invoke "undo payment"**. A plain HTTP request does not join the transaction manager's XA/2-phase commit. Even when using JTA across XA resources, an external REST API does not magically become an XA resource.

### 3.4. Timeout Does Not Mean the Request Never Executed

A common scenario:

```text
Client sends request
       |
       v
Remote commits payment
       |
       X response lost / read timeout
       |
Client sees timeout
       |
Batch retries request
       |
Remote receives duplicate
```

The client only knows **it received no confirmation**, not whether the remote side processed the request. Therefore, **never retry a command with side effects merely because of a timeout** unless the remote endpoint supports idempotency or a reliable status-lookup API by key.

### 3.5. Rollbacks and Retries Can Reprocess an Item

In chunk-oriented processing, a transaction rollback can cause items in the chunk to be reprocessed, depending on the reader, retry policy, and restartability. Processor/writer callbacks can run more than once for the same business entity.

If the processor makes a `POST` with side effects, an invoice can be sent again when the chunk reprocesses. Counting processor invocations **does not equal** unique business transactions.

## 4. Spotting Symptoms in Logs and Metrics

A Job can exhibit these symptoms:

| Symptom | Likely underlying mechanism |
| --- | --- |
| `jobDuration` spikes when remote slows down | Chunk transaction waiting on network. |
| Connection pool `active` high, `pending` rising | Workers holding connections long. |
| Rising database lock waits / deadlocks | Transactions holding locks while waiting on remote. |
| Rising `rollbackCount`, retry counts | Timeouts/HTTP exceptions rolling back or retrying chunks. |
| Job fails with `CannotAcquireLockException` / transaction timeout | DB contention and transaction duration. |
| Remote receives duplicate requests | Retries after timeout or rollback after remote committed. |
| Job restarts and re-sends old requests | Missing durable idempotency key / outbox status. |
| Business table shows unprocessed while remote processed | Missing atomicity between DB and HTTP. |
| Throughput drops as workers increase | Pool/DB/API saturation or contention. |

Include observable fields in logs and traces:

```text
jobName
jobInstanceId
jobExecutionId
stepExecutionId
businessKey (approved for logging)
outboxEventId / idempotencyKey
remoteOperation
remoteDurationMs
remoteStatusClass (2xx/4xx/5xx/timeout)
attemptNumber
retryDecision
transactionPhase
```

**Never log tokens, payment card details, secrets, PII-containing payloads, or URLs with embedded credentials.** For metrics, do not use `jobExecutionId` or business keys as unbounded-cardinality tags; those belong in detailed log queries.

## 5. "Quick Fixes" That Do Not Solve the Root Problem

### Only Increasing `transaction timeout`

Raising the transaction timeout may reduce timeout failures, yet **lengthens resource hold times and the inconsistency window**. It still does not roll back remote side effects alongside the DB.

### Only Increasing `connection pool size`

A bigger pool may delay connection exhaustion, yet also allows more concurrent transactions against the database and can worsen lock contention. Fix the long-transaction design before scaling pools.

### Moving HTTP from Writer to Processor

In a chunk Step, the processor still normally executes inside the chunk's transaction. If the processor makes many remote calls, the transaction remains just as long.

### Adding `@Transactional(REQUIRES_NEW)` to the Remote Service

`REQUIRES_NEW` affects Spring-managed transactions; it does not turn HTTP into an XA resource. Moreover, the outer transaction can still remain suspended and holding resources while the inner transaction runs. Do not use it to paper over an improper transaction boundary.

### Only Setting `@Transactional(timeout = 5)`

Transaction timeouts bound application/database transactions per their mechanism, yet **do not guarantee the HTTP client aborts promptly**, do not refund charges, and do not provide idempotency. You still need network timeouts and error policies.

### Only Enabling `retry(...)` in Spring Batch

Retry helps with transient errors **when the operation is safe to repeat**. For non-idempotent `POST`s, retry can duplicate side effects. Skip is no answer either: skipping an already-charged invoice without recording its status leaves data inconsistent.

### Spawning Async Threads Inside the Processor

Offloading HTTP to `CompletableFuture.runAsync(...)` and returning before results arrive can let the Job commit while remote work is still in flight. There is no guarantee an async worker inherits the caller's transaction or `SecurityContext`. You need a durable orchestration flow, not merely extra threads.

## 6. Choosing Architecture by the Nature of the Remote Operation

Not all remote calls are alike. Classify first:

| Remote call type | Example | Main risks | Suggested design |
| --- | --- | --- | --- |
| **Read-only lookup** | Fetch exchange rates, reference info | Latency, timeouts, rate limits, data drift over time | Prefetch/cache, stage data pre-chunk, or split into a separate phase. |
| **Idempotent PUT/UPSERT** | Set entity state by deterministic key | Timeout with unknown outcome, ordering, conflicts | Idempotency key/version, bounded retry, separate transactions where possible. |
| **Non-idempotent command** | Charge payment, issue coupon, send SMS | Duplicate side effects on retry/rollback | Transactional outbox, remote idempotency, orchestration state. |
| **Bulk remote API** | Send 1,000 items per request | Batch limits, partial failures, long timeouts | Batch in a remote worker layer, per-item mapping, and replay mechanics. |
| **Long-running remote workflow** | Generate reports, cross-system reconciliation | Cannot wait for completion in one DB transaction | Async command + callback/polling, state machine, timeout/reconciliation. |

Two guiding directions:

1. For **data lookups**, minimize or eliminate waiting on network **inside transactions** via staging/caching and data snapshotting.
2. For **commands mutating external systems**, prefer **persisting durable intent in a short transaction**, then executing remote calls outside the transaction via a dedicated worker.

## 7. Recommended Architecture: Transactional Outbox

**Transactional outbox** is a standard pattern to decouple recording business intent from invoking remote calls.

Instead of calling `POST /payments` directly inside `ItemProcessor` or `ItemWriter`:

1. Spring Batch processes invoices and writes an **outbox command** to the database in the same transaction as required local changes.
2. Chunk commits finish quickly without waiting on HTTP.
3. A worker/dispatcher reads committed outbox rows, claims work, and calls remote **outside any DB transaction**.
4. Upon getting an outcome, the worker updates status in another short database transaction.
5. On error, outbox state enables bounded retries and reconciliation. The remote endpoint needs an idempotency key to prevent duplicate side effects.

```text
Spring Batch Job                             Outbox dispatcher
----------------                             -----------------
BEGIN chunk TX
  read invoice
  validate/transform
  write invoice status=PENDING_REMOTE
  INSERT outbox(commandId, payload, status=NEW)
COMMIT chunk TX
       |
       v
BATCH OUTBOX TABLE  <---- claim in short transaction
                         COMMIT claim transaction
                             |
                             v
                         HTTP POST remote
                         (NO DB transaction held)
                             |
                     +-------+-------+
                     |               |
                  Success          Timeout/error
                     |               |
               short DB TX      short DB TX
               mark SENT        schedule retry /
               + reconcile      UNKNOWN/FAILED
                     |               |
                   COMMIT           COMMIT
```

### Why Does This Pattern Reduce Risk?

- Does not hold chunk transactions open while waiting for network responses.
- Intent to send commits atomically with required local changes.
- Dispatcher can resume after restarts independently of the original Spring Batch process.
- Provides explicit state to monitor backlogs and analyze failures.
- Lets you bound concurrency, rate limits, exponential backoff, and circuit breakers at the remote worker layer.

**Crucial limitation:** Transactional outbox **does not guarantee exactly-once HTTP delivery**. A worker can call remote successfully and crash before marking the outbox row `SENT`. The next run will re-send the same command. Therefore, the remote service must support idempotency or reliable status lookup by command ID.

## 8. Designing the Outbox Schema

PostgreSQL example:

```sql
CREATE TABLE payment_outbox (
    command_id       UUID PRIMARY KEY,
    invoice_id       BIGINT NOT NULL,
    operation        VARCHAR(40) NOT NULL,
    payload_json     JSONB NOT NULL,
    status           VARCHAR(32) NOT NULL,
    attempt_count    INTEGER NOT NULL DEFAULT 0,
    next_attempt_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lease_until      TIMESTAMPTZ NULL,
    worker_id        VARCHAR(100) NULL,
    remote_reference VARCHAR(255) NULL,
    last_error_code  VARCHAR(100) NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_payment_outbox_dispatch
ON payment_outbox (status, next_attempt_at);
```

Illustrative columns:

| Column | Meaning |
| --- | --- |
| `command_id` | Stable ID of a remote intent; used as the idempotency key. |
| `invoice_id` | Business key, joinable to the invoice table. |
| `operation` | Remote operation type, e.g., `CAPTURE_PAYMENT`. |
| `payload_json` | Payload to send; enforce security and minimize PII. |
| `status` | `NEW`, `SENDING`, `SENT`, `RETRY`, `UNKNOWN`, `DEAD`. |
| `attempt_count` | Number of send attempts made by workers per orchestration rules. |
| `next_attempt_at` | Earliest timestamp eligible for the next retry. |
| `lease_until` | Claim lease expiration to prevent concurrent double-processing. |
| `worker_id` | Worker holding the claim, for operations/fencing. |
| `remote_reference` | Remote outcome ID if returned, aiding reconciliation. |
| `last_error_code` | Standardized error code; never store raw tokens/sensitive responses. |

If each invoice may be charged only once per payment obligation, add a **unique business constraint** such as `(invoice_id, operation, business_version)`. A unique `command_id` alone is not enough: a mapping bug could generate two different UUIDs for the same business action.

### Command ID Must Remain Stable Across Retries and Restarts

A common identification scheme:

```text
commandId = stable identifier of invoice + operation + business version
```

You can generate a deterministic UUID from the business key, or generate a random UUID once when writing the outbox row and **reuse that exact persisted ID** on every retry. Never generate a fresh UUID each time a worker calls remote, as that alters the idempotency key.

If remote expects a header:

```http
POST /payments
Idempotency-Key: <stable-command-id>
Content-Type: application/json
```

Actual idempotency contracts depend on the remote service: key retention window, uniqueness scope, handling of same-key different-payload requests, response codes, and result lookup capability. Never assume every API supports headers identically to this example.

## 9. Batch Step Only Writes Intent to the Outbox

Spring Batch 5.x example where `ItemProcessor` performs only local transformation without calling remote. Each invoice maps to a command to dispatch.

```java
import java.util.UUID;

public record Invoice(
        long id,
        String businessKey,
        long amountCents,
        long version) {
}

public record PaymentCommand(
        UUID commandId,
        long invoiceId,
        long amountCents,
        String operation) {
}
```

Processor:

```java
import java.nio.charset.StandardCharsets;
import java.util.UUID;

import org.springframework.batch.item.ItemProcessor;

public final class PaymentCommandProcessor
        implements ItemProcessor<Invoice, PaymentCommand> {

    @Override
    public PaymentCommand process(Invoice invoice) {
        if (invoice.amountCents() <= 0) {
            throw new IllegalArgumentException(
                    "Amount must be positive");
        }

        // A stable logical key for the same invoice/version/operation.
        String logicalKey = invoice.businessKey()
                + ":CAPTURE_PAYMENT:" + invoice.version();

        UUID commandId = UUID.nameUUIDFromBytes(
                logicalKey.getBytes(StandardCharsets.UTF_8));

        return new PaymentCommand(
                commandId,
                invoice.id(),
                invoice.amountCents(),
                "CAPTURE_PAYMENT");
    }
}
```

Note that Java's `UUID.nameUUIDFromBytes` derives an ID from bytes using the JDK's algorithm. This illustrates **deterministic IDs**, not information hiding: if the input business key is guessable, the UUID is guessable too. Use it only with appropriate keys/namespaces; when secrecy or key-hiding is required, generate a random ID once and persist it durably instead of hashing sensitive data into a UUID.

Illustrative PostgreSQL writer:

```java
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Bean
JdbcBatchItemWriter<PaymentCommand> outboxWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<PaymentCommand>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO payment_outbox
                    (command_id, invoice_id, operation,
                     payload_json, status)
                VALUES
                    (:commandId, :invoiceId, :operation,
                     CAST(:payloadJson AS jsonb), 'NEW')
                ON CONFLICT (command_id) DO NOTHING
                """)
            .itemSqlParameterSourceProvider(cmd ->
                    new MapSqlParameterSource()
                            .addValue("commandId", cmd.commandId())
                            .addValue("invoiceId", cmd.invoiceId())
                            .addValue("operation", cmd.operation())
                            .addValue("payloadJson",
                                    "{\"amountCents\":"
                                        + cmd.amountCents() + "}")
            )
            .build();
}
```

This SQL uses **PostgreSQL** syntax. For other DBMSs, substitute the matching upsert/dedup syntax. `ON CONFLICT DO NOTHING` shows a simple idempotent choice; if the same `command_id` appears with a different payload, a real system should detect a **business conflict** rather than silently ignoring it.

Step:

```java
@Bean
Step preparePaymentCommandsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Invoice> invoiceReader,
        PaymentCommandProcessor processor,
        JdbcBatchItemWriter<PaymentCommand> outboxWriter) {

    return new StepBuilder(
            "preparePaymentCommandsStep", jobRepository)
            .<Invoice, PaymentCommand>chunk(200, transactionManager)
            .reader(invoiceReader)
            .processor(processor)
            .writer(outboxWriter)
            .build();
}
```

**Why is this better than calling the API in the processor?** The chunk now performs only local processing and outbox SQL. No HTTP calls execute inside the chunk transaction. If the transaction rolls back, uncommitted outbox commands roll back too—provided **the same database and appropriate transaction manager** are used.

In a real application, if `invoices` must simultaneously update to `PENDING_REMOTE` and insert into outbox, perform both in the same transaction, e.g., via a composite writer sharing the datasource. Never mutate invoice state and commit before inserting the outbox row, as a crash between the two can drop the remote command.

### Points to Watch When Applying

- `InvoiceReader` selects only eligible invoices within the Job scope, avoiding duplicate commands for already completed invoices.
- Use unique business keys to prevent duplicates on Job retry/restart.
- When using two datasources/transaction managers, design cross-DB consistency explicitly; Spring Batch transactions do not span two DBs by default.
- `JobRepository` metadata, outbox rows, and business data are distinct datasets; never purge production outboxes via metadata cleanup.
- Payloads must satisfy security and retention rules; outboxes can hold sensitive payment commands.

## 10. Dispatcher: Hold Transactions Only for Claiming and Status Updates

The dispatcher should have three **distinct** phases:

1. **Claim:** acquire a `NEW`/`RETRY` command in a short DB transaction, recording owner and lease.
2. **Call remote:** perform network I/O outside any database transaction.
3. **Acknowledge/reschedule:** persist the outcome or retry schedule in another short transaction.

Illustrative code using `TransactionTemplate` to make boundaries explicit:

```java
import java.util.Optional;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public final class PaymentOutboxDispatcher {

    private final TransactionTemplate transactionTemplate;
    private final PaymentOutboxRepository outbox;
    private final RemotePaymentGateway gateway;

    public PaymentOutboxDispatcher(
            TransactionTemplate transactionTemplate,
            PaymentOutboxRepository outbox,
            RemotePaymentGateway gateway) {

        this.transactionTemplate = transactionTemplate;
        this.outbox = outbox;
        this.gateway = gateway;
    }

    public void dispatchOne() {
        Optional<PendingPayment> claimed =
                transactionTemplate.execute(status ->
                        outbox.claimNextReady());

        if (claimed == null || claimed.isEmpty()) {
            return;
        }

        PendingPayment payment = claimed.get();

        try {
            // No DB transaction from claim is open here.
            RemoteReceipt receipt = gateway.capture(
                    payment.commandId(),
                    payment.invoiceId(),
                    payment.amountCents());

            transactionTemplate.executeWithoutResult(status ->
                    outbox.markSent(
                            payment.commandId(),
                            payment.claimToken(),
                            receipt.remoteReference()));

        } catch (RemoteOutcomeUnknownException ex) {
            transactionTemplate.executeWithoutResult(status ->
                    outbox.markUnknownForReconciliation(
                            payment.commandId(),
                            payment.claimToken(),
                            "TIMEOUT_OR_UNCERTAIN_RESULT"));

        } catch (RetryableRemoteException ex) {
            transactionTemplate.executeWithoutResult(status ->
                    outbox.scheduleRetry(
                            payment.commandId(),
                            payment.claimToken(),
                            "REMOTE_RETRYABLE_ERROR"));

        }
    }

    public record PendingPayment(
            UUID commandId,
            long invoiceId,
            long amountCents,
            String claimToken) {
    }

    public record RemoteReceipt(String remoteReference) {
    }

    public interface RemotePaymentGateway {
        RemoteReceipt capture(
                UUID commandId,
                long invoiceId,
                long amountCents);
    }

    public interface PaymentOutboxRepository {
        Optional<PendingPayment> claimNextReady();
        void markSent(
                UUID commandId,
                String claimToken,
                String remoteReference);
        void markUnknownForReconciliation(
                UUID commandId,
                String claimToken,
                String errorCode);
        void scheduleRetry(
                UUID commandId,
                String claimToken,
                String errorCode);
    }

    public static class RetryableRemoteException
            extends RuntimeException {
    }

    public static class RemoteOutcomeUnknownException
            extends RuntimeException {
    }
}
```

This is an **implementation skeleton**: `PaymentOutboxRepository` and `RemotePaymentGateway` are application-supplied interfaces without claim SQL, retry clocks, or HTTP transport in the snippet. `TransactionTemplate` here uses the outbox database's transaction manager, and `dispatchOne()` must be invoked from a scope **with no active outer transaction**. If called inside a `@Transactional` method, `TransactionTemplate`'s default `REQUIRED` propagation joins the outer transaction; design entrypoints so schedulers/services invoking the dispatcher do not hold a pre-existing DB transaction.

### A Claim Must Be Atomic

Never write:

```java
if (outbox.findFirstNew() != null) {
    outbox.markSending(...);
}
```

without concurrency control. Two workers can pick the same command before either updates status.

With PostgreSQL, use a short transaction with `SELECT ... FOR UPDATE SKIP LOCKED` and `UPDATE`, or an atomic `UPDATE ... RETURNING` selecting eligible work. Include:

- `lease_until` to recover commands if a worker crashes.
- `claimToken` or generation/fencing number so a stale worker cannot overwrite updates after another worker steals the lease.
- `next_attempt_at` so retries do not spin in a hot loop.
- `attempt_count` and an attempt cap.
- Unique business keys/idempotency on the remote side to avoid duplicate side effects.

### Problem When a Lease Expires While HTTP Is Still Running

`lease_until` is not an absolute mutex. If a remote call outlasts the lease, worker B can reclaim the row while worker A has not finished. Therefore:

1. Set HTTP timeouts shorter than or aligned with lease policy.
2. Renew leases via appropriate coordination for long operations.
3. Use fencing/claim tokens to block stale DB updates.
4. Rely on idempotency keys to protect remote side effects even when duplicate requests occur.

A distributed lock does not replace idempotency on the target system.

## 11. When You Do Not Know Whether the Remote Call Succeeded

Not all remote errors are equal:

| Situation | Is remote side effect known to have occurred? | Suggested action |
| --- | --- | --- |
| HTTP 2xx with confirmation reference | Normally succeeded per contract | Persist `SENT`/`CONFIRMED` in a short transaction. |
| HTTP 400 from pre-processing validation | Contract-dependent; request likely rejected | Persist `REJECTED` and standardized reason; do not retry infinitely. |
| HTTP 429 / 503 | Likely transient, per contract | Retry after backoff, respecting `Retry-After` if present. |
| Connection refused before sending request | Usually no side effect yet, though inspect transport | Bounded retry. |
| Read timeout after sending request | **Uncertain** whether remote committed | Set `UNKNOWN`; query by idempotency/command ID before retrying per API. |
| Client receives HTTP 500 | Do not assume remote rolled back | Check contract; outcome may be unknown. |
| Worker dies after HTTP 200, before DB ack | Remote executed, yet outbox still not `SENT` | Idempotent retry or reconciliation by command ID. |

Some APIs retain retry idempotency only for a limited window (for example, keys kept for a few hours). If a Job can replay days later, handling policies must account for **dedup retention** and durable outcome lookup from the remote service.

Without remote idempotency and without a reconciliation API, the goal of "executing a side effect strictly once across timeouts and crashes" usually cannot be guaranteed by Spring Batch alone. In that case, revise the integration contract or add a business reconciliation process rather than promising exactly-once.

## 12. Timeouts and Retries When Calling Remote Services

Even after decoupling transactions, HTTP clients still need timeouts. Never let a remote call hang indefinitely and hold a worker/outbox claim forever.

Distinguish the limits:

- **Connect timeout:** time allowed to establish a connection.
- **Read/response timeout:** time allowed waiting for response data.
- **Overall deadline:** hard cap for the whole command, potentially spanning multiple retries.
- **Retry backoff:** wait interval between attempts.
- **Rate limit:** requests/sec or concurrent requests accepted by remote.

Example `RestClient` configuration on Spring Framework 6.1+:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Bean
RestClient paymentRestClient() {
    SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();

    factory.setConnectTimeout(Duration.ofSeconds(2));
    factory.setReadTimeout(Duration.ofSeconds(5));

    return RestClient.builder()
            .baseUrl("https://payments.example.internal")
            .requestFactory(factory)
            .build();
}
```

The address in this example is a technical placeholder only, not a real API. Configure URLs via environment/secret management and validate destinations; never take arbitrary URLs from untrusted `JobParameters`.

Example request with idempotency key:

```java
public RemoteReceipt capture(PendingPayment payment) {
    var response = paymentRestClient.post()
            .uri("/payments")
            .header(
                    "Idempotency-Key",
                    payment.commandId().toString())
            .body(new PaymentRequest(
                    payment.invoiceId(),
                    payment.amountCents()))
            .retrieve()
            .body(PaymentResponse.class);

    if (response == null) {
        throw new RemoteOutcomeUnknownException();
    }

    return new RemoteReceipt(response.paymentReference());
}
```

`PendingPayment`, `PaymentRequest`, `PaymentResponse`, and `RemoteReceipt` in the example are project-defined DTOs/records. Status classification, transport exception handling, and timeout durations must align with the remote contract. `retrieve()` may throw exceptions depending on status; **never treat every exception as "no side effect occurred"**.

### Suggested Retry Policy

```text
Attempt 1
  |
  +-- 2xx ------------> SENT
  |
  +-- permanent 4xx --> REJECTED / manual review
  |
  +-- 429/503 --------> RETRY after backoff + jitter
  |
  +-- timeout --------> UNKNOWN -> query remote by key
                             |
                             +-- found success -> SENT
                             +-- known rejected -> REJECTED
                             +-- no answer     -> review / safe retry
```

Cap retries by both attempt count and total duration to avoid retry storms during remote outages. Add jitter to backoffs when multiple workers retry concurrently. A circuit breaker can reduce load on the remote service during incidents, yet a circuit breaker **does not solve side-effect correctness**.

## 13. If the Remote Operation Is Read-Only: Staging and Caching

Not every remote lookup needs an outbox. Suppose a Job checks daily exchange rates before calculating:

```text
ItemReader -> ItemProcessor -> GET /exchange-rate -> ItemWriter
```

If every item fetches the same rate, that adds both network overhead and long chunk transactions. Better options:

### 13.1. Prefetch Once for the Entire Job or Window

```text
Prepare phase (remote lookup, no long DB transaction)
    |
    v
Persist approved reference snapshot / cache
    |
    v
Chunk Step: read -> calculate using local snapshot -> write
```

Identify the snapshot by rate date, source version, and timestamp so restarts remain consistent. If cached only in memory and the Job restarts on another node, results could drift; evaluate business reproducibility requirements.

**Caution:** putting a remote call into a separate `Tasklet` Step **does not automatically run it outside a transaction**, since `TaskletStep` also has a transaction boundary. Place network calls in an orchestrator outside chunk/Tasklet transactions, or explicitly configure service/transaction boundaries and verify the actual call path.

### 13.2. Batch Remote Reads Instead of N Calls for N Items

If the remote service provides a bulk GET API, gather keys to look up, fetch in batches, and store results in a staging table or cache used during the Step. Increasing batch size cuts round-trips, yet must respect request payload limits, timeouts, and rate limits.

### 13.3. Caching with Explicit Consistency

Caching works well when reference data changes infrequently, provided it defines:

- TTL or a fixed version per `JobInstance`.
- Cache-miss policy.
- Invalidation rules when required by the business.
- Memory bounds and key cardinality limits.
- Reproducibility of the same results on restart.

Never cache without pinning data to a point in time if the Job needs auditable results.

## 14. Splitting a Job into Multiple Stages

When remote calls cannot finish quickly and millions of items must be processed, a single synchronous Job may no longer fit.

Example three-stage pipeline:

```text
Job A: Prepare commands
  └── Read invoices -> validate -> write durable outbox
                         |
                         v
                  Dispatcher service
                  (remote HTTP, retries, reconciliation)
                         |
                         v
Job B: Finalize / reconcile
  └── Read confirmed remote outcomes -> update business status
```

Job A may finish `COMPLETED` as soon as commands are durably written, yet that **does not mean all invoices are paid on the remote side**. Define clear states:

- `PREPARATION_COMPLETED`: commands created and committed.
- `REMOTE_PENDING`: outbox rows still awaiting dispatch.
- `REMOTE_CONFIRMED`: outcomes confirmed.
- `RECONCILIATION_FAILED`: ambiguous/mismatched cases requiring intervention.
- `BUSINESS_COMPLETED`: the actual business workflow finished.

These statuses can live in business/state-machine tables rather than default `BatchStatus` values. If a dashboard displays Job A as `COMPLETED`, pair it with backlog/outcome metrics so operators do not mistakenly assume all payments succeeded.

### Choosing Orchestration

| Option | Best suited when | What to watch |
| --- | --- | --- |
| One Job writing outbox + background worker | Slow remote calls, many independent commands | Target state and completion SLA live in the worker tier. |
| Two checkpointed Batch Jobs | Batched staging and finalization phases | Cross-Job dependency orchestration, retries, and restarts. |
| Message queue + consumer | Need flexible remote throughput scaling | Duplicate deliveries possible; consumers must be idempotent. |
| Async remote workflow + callback | Remote returns job/token and processes long | Callback authentication, correlation IDs, timeouts, and reconciliation. |
| Remote service offers bulk API | Large batches can be sent reliably | Partial failures and per-item idempotency. |

No single architecture fits every workflow. The invariant is **never keeping a chunk's database transaction open across long remote waits**.

## 15. Choosing Chunk Size and Worker Count After Decoupling Remote Calls

Removing network waits from chunk transactions usually cuts commit-path latency, yet still requires measurement.

In the outbox-writing Job:

- Larger chunk sizes can cut commit overhead, yet raise memory and rollback scope.
- Writers should use JDBC batching when appropriate.
- Unique constraints/indexes on the outbox must sustain write throughput.
- Updating hot rows together can still cause contention; pick appropriate business keys and partitions.

In the dispatcher:

- **Max in-flight requests** caps concurrent HTTP calls.
- **Remote rate limit** caps requests per second.
- **HTTP connection pool** must size for workers without over-allocating.
- **Outbox claim batch size** balances DB cost and lease duration.
- **Backpressure** prevents unbounded queue growth or overloading remote services.

For instance, a remote service allows only 100 requests/s while each Job produces 10,000 commands/s. Adding dispatcher threads will not overcome the remote rate limit. You need backlog handling, processing SLAs, and rate control—or a bulk API contract.

Track at minimum:

```text
outbox_pending_count
outbox_oldest_age_seconds
outbox_sent_total
outbox_retry_total
outbox_unknown_total
remote_request_duration_seconds
remote_request_error_total
db_transaction_duration_seconds
db_connection_pool_pending
batch_step_rollback_count
```

For metric labels, use bounded-cardinality values such as `operation`, `status`, and `remote_service`; never use `invoiceId` or `commandId` as labels.

## 16. Interaction with Skip/Retry in Spring Batch

Spring Batch supports `faultTolerant()`, `retry(...)`, `skip(...)`, and corresponding listeners. They are valuable when applied to the right error categories, yet do not replace remote-safe architecture.

### 16.1. Internal Data Errors

If an invoice is malformed or misses a required field, configure skips/quality reporting for that specific exception. That is an isolated data error unrelated to remote latency.

### 16.2. Transient Remote Errors

If remote is unresponsive, the right strategy is usually persisting durable commands and retrying in the dispatcher. Never let millions of HTTP retries execute inside the Job's chunk transactions while holding locks/connections.

### 16.3. Ambiguous Remote Outcomes

A timeout can occur after remote already committed. Never classify it definitively as "unprocessed" and retry non-idempotently. Track `UNKNOWN` and reconcile by idempotency key.

### 16.4. When Remote Must Be Called Inside a Chunk

Sometimes architecture cannot change immediately, such as a legacy system requiring a remote check per record without caching support. If forced to keep remote lookups inside chunks:

1. Restrict to read-only or idempotent remote operations.
2. Configure connect/read/overall timeouts and bounded retries.
3. Shrink chunk size to fit remote P95/P99 latency.
4. Monitor DB connection hold time, lock waits, rollbacks, and throughput.
5. Avoid updating/locking business rows before waiting on remote whenever possible.
6. Verify rollback/restart semantics and never assume remote side effects undo automatically.
7. Plan to decouple network I/O from transactions when feasible.

This is a **temporary mitigation**, not default advice for new architectures.

## 17. Differences Between Transaction Timeouts and HTTP Timeouts

| Timeout | Where controlled | Primary effect | What it does NOT guarantee |
| --- | --- | --- | --- |
| DB transaction timeout | Transaction manager/DB | Caps long transactions and commit eligibility | Does not undo remote side effects. |
| Connection timeout | HTTP client | Prevents hanging while establishing connections | Does not bound full response time. |
| Read/response timeout | HTTP client | Prevents waiting forever for response bytes | Does not prove remote never processed it. |
| Overall request deadline | Client/orchestrator | Caps total duration of one attempt | Does not auto-cancel committed remote side effects. |
| Retry budget | Dispatcher | Caps attempts/total retry time | Does not replace idempotency. |
| Outbox lease timeout | Database claim layer | Recovers commands if a worker dies | Does not guarantee the old worker stopped its HTTP call. |

Align these timeouts **cohesively**: an HTTP attempt should not uncontrollably outlast a lease; total retries and timeouts must fit SLAs; short transactions must allow enough time for necessary SQL without spanning network I/O.

Never set every timeout to the exact same number merely for convenience. Each timeout guards a different layer.

## 18. Designing Tests That Catch the Long-Transaction Pitfall

A test checking only that the Job `COMPLETED` does not prove transactions were shortened. To detect HTTP calls inside transactions, test specific boundaries.

### 18.1. Unit Testing Remote Call Placement

When the new design has a pure-data `PaymentCommandProcessor`, tests should prove the processor **never calls the remote gateway**. You can use mocks elsewhere, yet for a pure processor simply assert the output command and deterministic command ID.

```java
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class PaymentCommandProcessorTest {

    @Test
    void createsStableCommandWithoutHttpCall() throws Exception {
        PaymentCommandProcessor processor =
                new PaymentCommandProcessor();

        Invoice invoice =
                new Invoice(10L, "INV-2026-001", 15_000L, 1L);

        PaymentCommand first = processor.process(invoice);
        PaymentCommand second = processor.process(invoice);

        assertThat(first.commandId())
                .isEqualTo(second.commandId());
        assertThat(first.invoiceId()).isEqualTo(10L);
        assertThat(first.amountCents()).isEqualTo(15_000L);
    }
}
```

This test does not prove the rest of the system avoids HTTP calls in another listener. It only verifies that this specific processor is a local transformation.

### 18.2. Testing That Dispatcher Holds No Transaction During HTTP

Create a fake `RemotePaymentGateway` that checks transaction activity when `capture` runs.

Using `TransactionSynchronizationManager`:

```java
import org.springframework.transaction.support
        .TransactionSynchronizationManager;

public final class TransactionInspectingGateway
        implements RemotePaymentGateway {

    @Override
    public RemoteReceipt capture(
            UUID commandId,
            long invoiceId,
            long amountCents) {

        if (TransactionSynchronizationManager
                .isActualTransactionActive()) {
            throw new AssertionError(
                    "Remote HTTP call must not run inside DB transaction");
        }

        return new RemoteReceipt("remote-test-reference");
    }
}
```

This is an illustrative test helper: supply the project's interfaces/records and configure a Spring transaction manager for the check to be meaningful. In integration tests, configure the dispatcher to use `TransactionTemplate` for claim and ack, and invoke the method **outside any outer transaction**.

If a test method is annotated `@Transactional` and calls the dispatcher directly, the outer test transaction can fail the check even though the dispatcher opens short scopes itself. Disable the test-wrapping transaction or use tests with explicitly controlled transaction boundaries.

### 18.3. Testing Slow Remote Calls Hold No DB Transaction

Use an HTTP test server or fake gateway with a `CountDownLatch`:

```text
Test starts dispatcher
   |
   v
Dispatcher claims command -> short DB COMMIT
   |
   v
Remote gateway blocked at latch
   |
   +-- Test probes DB / transaction resources
   |      Expected: claim transaction already committed
   |
Test releases latch
   |
   v
Dispatcher receives response -> short DB COMMIT
```

Check from a **separate** transaction that the command is already in `SENDING` state while the remote call is blocked. That proves the claim transaction already committed. Do not rely solely on `TransactionSynchronizationManager`, which reflects only the current thread's state rather than full lock/connection lifecycles across threads.

### 18.4. Testing Remote Success Followed by DB Ack Failure

Key reliability scenario:

1. Outbox holds command `C` in `NEW` state.
2. Dispatcher claims and calls remote with idempotency key `C`.
3. Remote succeeds and returns a reference.
4. Intentionally fail the DB ack or kill the worker before marking `SENT`.
5. Another worker reclaims after lease expiry/recovery.
6. Remote receives **the exact same key `C`** and returns the same result per idempotency contract.
7. Outbox transitions to `SENT` without creating a second charge.

A test verifying only that remote returns 200 once will never catch the most severe outbox/retry bug.

### 18.5. Testing Timeouts with Uncertain Outcome

1. Fake remote executes the side effect yet intentionally omits the response.
2. Client observes a read timeout.
3. Outbox records `UNKNOWN` or a reconciliation-needed state.
4. Dispatcher queries remote by idempotency key to confirm outcome.
5. Never blindly send a new charge under a different key.
6. Verify logs and final state accurately reflect uncertainty.

### 18.6. Testing Chunk Rollback Neither Loses Nor Duplicates Commands

Create a Job writing to the outbox and trigger a rollback after the writer begins processing. With unique constraints and deterministic command IDs, re-run the chunk or restart the Job:

- Zero committed commands if the entire chunk rolled back.
- After successful retry, exactly one outbox command exists for the business operation.
- Zero remote side effects occur before the outbox transaction commits.
- If the `JobInstance` restarts, the command key still maps to the same business operation.

## 19. Integration Test Example with `spring-batch-test`

Suppose `preparePaymentsJob` only reads invoices and writes to the outbox, sending zero HTTP calls inside the chunk.

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class PaymentOutboxBatchIT {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    @Qualifier("preparePaymentsJob")
    private Job job;

    @Test
    void jobShouldCreateCommittedCommands() throws Exception {
        jobLauncherTestUtils.setJob(job);

        // Test fixture: database already contains 3 valid invoices.
        // Test invoices must be seeded/reset by a dedicated fixture.

        var parameters = new JobParametersBuilder()
                .addString(
                        "benchmarkRunId",
                        UUID.randomUUID().toString(),
                        true)
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchJob(parameters);

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);

        Integer pending = jdbc.queryForObject(
                """
                SELECT COUNT(*)
                FROM payment_outbox
                WHERE status = 'NEW'
                """,
                Integer.class);

        assertThat(pending).isEqualTo(3);
    }
}
```

This example uses **Spring Batch 5.x**, `JobLauncherTestUtils`, JUnit Jupiter, and AssertJ. It is a test skeleton: you must supply the Job bean, reader, writer, outbox schema, and three-invoice fixture. If tests run in parallel or share a database, isolate data so `COUNT(*)` does not pick up commands from another test.

In practice, also assert:

- The three `command_id`s match the three exact invoices.
- Each business operation has at most one command.
- Payload contents are accurate and omit unnecessary sensitive fields.
- Zero HTTP requests were fired during the Job's outbox-preparation phase.
- Invoice and command statuses committed consistently.

## 20. Another Option: Updating Business State After Remote Confirmation

Not every workflow wants to mark an invoice `PAID` inside the chunk. For payments, a state machine is usually safer:

```text
Invoice CREATED
     |
     v
PAYMENT_PENDING (command in outbox)
     |
     v
Remote request sent
     |
     +-- Remote confirms --> PAID
     |
     +-- Remote rejects  --> PAYMENT_REJECTED
     |
     +-- Outcome unknown --> PAYMENT_RECONCILING
```

`PAID` should be assigned only with confirmed proof of payment per the remote contract. If a DB status update to `PAID` fails, the dispatcher can reconcile using the remote reference and command ID.

This is a form of **saga/orchestration** at the business layer: instead of promising a global transaction spanning every system, each step has its own commit, explicit state, and compensation/reconciliation mechanics when needed.

Especially for irreversible actions like sending emails or SMS, there is no true "recall email" compensation. Avoiding duplicate sends, confirming outcomes, and tracking state are essential.

## 21. Operations and Monitoring Principles

To catch problems early, monitor both the Job and the dispatcher:

| Group | Signals to monitor |
| --- | --- |
| Spring Batch | Job status, Step duration, `rollbackCount`, `readCount`, `writeCount`, retries/skips by error type. |
| Database | Transaction duration, active connections, pool wait time, lock waits, deadlocks, long-running queries. |
| HTTP client | Connect/read timeouts, latency P50/P95/P99, HTTP error classes, retry rate, in-flight requests. |
| Outbox | `NEW`/`RETRY`/`UNKNOWN` command counts, age of oldest command, `DEAD` command count. |
| Business | Invoices in `PAYMENT_PENDING`, confirmed remote charges, unresolved reconciliation cases. |

A sample log entry:

```text
INFO payment.outbox.sent
  jobExecutionId=9001
  commandId=<stable-id>
  invoiceBusinessKey=<safe-key>
  remoteService=payments
  remoteReference=<safe-reference>
  durationMs=281
  attempt=2
```

Do not treat a single HTTP 200 as sole proof that the business workflow succeeded if status updates, signature/response validation, or reconciliation remain.

### Production Troubleshooting Guide

When a Job suddenly slows down:

1. Compare duration per Step and chunk/rollback counts.
2. Check connection pool dashboards, DB locks, and long-lived transactions.
3. Analyze remote P95/P99 latency, timeouts, and retries.
4. Inspect distributed traces for a slow request, correlated by safe business key/command ID.
5. Identify where the transaction is held: before, during, or after the remote call.
6. Distinguish slowdowns caused by data volume, remote outages, or pool/chunk config changes.
7. When using an outbox, inspect backlog and dispatcher rate; never blindly raise threads without checking remote rate limits.
8. For `UNKNOWN` outcomes, query remote by idempotency key rather than automatically issuing a new command.

Do not purge outbox rows or `JobRepository` metadata to "speed up the job" without checking restart, audit, and reconciliation impacts. `SENT` outbox rows can be archived under a dedicated retention policy, provided data needed for dedup/auditing remains intact.

## 22. Common Mistakes and Fixes

### Calling HTTP Inside `ItemProcessor` Because "Processors Only Transform Data"

A processor is not pure computation if it contains network calls. In a chunk Step, it normally executes in transaction scope. **Fix:** stage remote lookups or turn remote commands into outbox records.

### Calling Remote Inside Writer Hoping DB Rollback Will Undo It

`ItemWriter` runs inside the DB transaction, yet HTTP does not participate in rollback. **Fix:** commit the outbox command first, let the dispatcher call remote post-commit, and enforce idempotency.

### Retrying All `RestClientException`s Unclassified

A timeout can occur after remote already committed. **Fix:** separate known retryables from unknown outcomes, applying idempotency and reconciliation.

### Increasing Chunk Size to Reduce Commits, Accidentally Lengthening Transaction Holds

If each item has high remote latency, chunk size 1,000 can hold a transaction open for ages. **Fix:** move network calls out of chunks before tuning chunk size; optimize commits only after fixing architecture.

### Switching to `@Async` Without Tracking Outcomes

The Job can report `COMPLETED` while HTTP tasks are still running; a process crash drops in-memory tasks. **Fix:** persist durable commands, use queues/outboxes, and track acknowledgments.

### Wrapping HTTP with `@Transactional(REQUIRES_NEW)`

HTTP remains non-transactional; the outer transaction can still stay open. **Fix:** place remote calls **between** committed short transactions rather than merely swapping annotations.

### Assuming Outbox Guarantees Exactly-Once

Workers can crash after remote commits and before marking `SENT`. **Fix:** stable idempotency keys, remote deduplication, and reconciliation for unknown outcomes.

### Generating a New UUID on Every Retry

Remote sees each attempt as a distinct command. **Fix:** persist the command ID once and reuse it; enforce business-operation uniqueness.

### Deleting the Command on HTTP Timeout

You no longer know whether remote processed it; deleting the command destroys reconcilability. **Fix:** record `UNKNOWN` or an explicit retry/reconciliation state.

### Letting the Dispatcher Run Under an Outer `@Transactional`

`TransactionTemplate` may join the outer transaction by propagation, keeping remote calls inside a long transaction. **Fix:** structure dispatcher entrypoints without an outer transaction, verified by tests and metrics.

### Optimizing Only Speed Without Checking Side Effects

A configuration may run fast yet emit duplicate payments. **Fix:** verify unique business operations, remote references, and post-crash/retry states.

## 23. Practice Exercises

Suppose `shippingOrderJob` reads 50,000 paid orders and calls a remote shipping service to create shipments. The remote API has P95 = 800 ms, occasionally takes 15 seconds, and can return HTTP 503. The database is PostgreSQL, the Job runs on 4 workers, and duplicate shipments must never be created.

### Part A — Analyze the Flawed Design

1. Diagram the transaction boundary of the current Step when `ItemProcessor` calls `POST /shipments`.
2. Estimate network wait time if a 100-item chunk runs sequentially, excluding retries.
3. List which connections/locks can be held and metrics to verify in practice.
4. Describe the scenario where remote creates a shipment yet the HTTP response is lost.
5. Explain why chunk rollback cannot cancel an already created shipment.

### Part B — Refactor to Outbox

1. Design `shipment_outbox` with a stable `command_id`, `order_id`, status, lease, attempt count, and remote reference.
2. Build a Step that only writes outbox commands and `SHIPMENT_PENDING` status inside a short transaction.
3. Enforce a unique constraint for a shipment creation request per order/version.
4. Implement a dispatcher that claims in a short transaction, calls the shipping API outside transactions, and acknowledges in a short transaction.
5. Pass the idempotency key to remote and store the returned reference.

### Part C — Failures and Recovery

1. Remote returns HTTP 503 → retry after backoff without holding a DB transaction.
2. Remote creates shipment then client hits read timeout → mark `UNKNOWN` and query outcome by command ID.
3. Worker dies before DB ack → another worker retries with the same idempotency key without creating a second shipment.
4. Lease expires while worker A is still running → verify fencing/dedup.
5. Spring Batch Job fails and restarts → no duplicate outbox commands created for the same order/version.

### Part D — Benchmarking and Observability

1. Measure Job Step duration, transaction duration, and connection pool metrics before/after refactoring.
2. Compare the Batch's command-creation throughput against the dispatcher's remote-confirmation throughput—these are two **different** quantities.
3. Monitor oldest pending command age and shipment creation SLAs.
4. Assess remote rate-limit budgets and appropriate worker counts.
5. Confirm final data has exactly 50,000 unique shipments when all orders are accepted, not merely that Job A reached `COMPLETED`.

### A Critical Question

If the dispatcher already sent the create-shipment request, remote returned 200, and then `markSent` in the database fails, **which transaction can roll back?** How do actual states on remote and in the database diverge? How will idempotency/reconciliation bring the system back to consistency?

This is precisely why **avoiding remote calls inside long transactions** must go hand in hand with an outcome-coordination strategy, rather than merely moving a few lines of code.

## References

- [Spring Batch Reference – Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): reader/processor/writer lifecycle and chunking.
- [Spring Batch Reference – Transaction Attributes](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/transaction-attributes.html): configuring Step transaction attributes.
- [Spring Batch Reference – Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): retries in fault-tolerant Steps and key considerations.
- [Spring Batch Reference – Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): difference between skips and Step-failing errors.
- [Spring Framework Reference – Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `@Transactional`, propagation, and transaction managers.
- [Spring Framework Reference – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): configuring HTTP clients and calling REST APIs.
- [Microservices.io – Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): persisting messages/commands atomically with local transactions and publishing outside transactions.
- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded Steps and concurrency limits when scaling workers.

