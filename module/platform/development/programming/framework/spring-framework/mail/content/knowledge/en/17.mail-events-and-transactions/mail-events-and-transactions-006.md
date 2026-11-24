# Placing Email Send Requests into an Outbox

## 1. Why is an outbox needed when sending email?

In a Spring application, a business operation often both writes data to the database and triggers an email. For example, when a customer places an order, the application saves the order and wants to send a confirmation email. These two operations belong to two different systems:

- The database manages transactions and can roll back data.
- The SMTP server is an external system; once it has accepted a message, the database cannot ask SMTP to undo the email.

If email sending is called directly inside the transaction, the application can encounter a situation where the email is sent yet the database transaction rolls back. Conversely, if the database commits first and then sends the email, the process may stop between the two operations and the send request is lost.

This is the **dual write** problem: a single use case must write successfully to two independent places without a distributed transaction guaranteeing both succeed together.

~~~mermaid
flowchart TD
    A[Place order] --> B[BEGIN database transaction]
    B --> C[Save order]
    C --> D[Send email via SMTP]
    D --> E[COMMIT database]
    D --> F[SMTP error]
    E --> G[Order saved]
    F --> H[Email failed to send]
    G --> I[State of two systems out of sync]
~~~

A **transactional outbox** bridges this gap by writing a record representing the **email send intent** into the same database and the same transaction as the business data. A worker reads that record after commit, builds the email, and sends it via Spring Mail.

~~~mermaid
flowchart TD
    A[Application service] --> T[Database transaction]
    T --> O[Save order]
    T --> X[Insert mail outbox record]
    O --> C[COMMIT]
    X --> C
    C --> W[Outbox worker]
    W --> M[Mail service / JavaMailSender]
    M --> S[SMTP server]
~~~

If the transaction commits, both the order and the send request exist. If the transaction rolls back, neither exists. SMTP delivery is handled afterward and can be retried when the provider is temporarily unavailable.

**An outbox guarantees the atomicity of business data and send intent inside the database. It does not make SMTP part of the database transaction and does not by itself guarantee the email is delivered exactly once.**

## 2. Distinguishing an outbox from post-commit event sending

Another approach is using a Spring event:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderConfirmed(OrderConfirmedEvent event) {
    mailService.sendConfirmation(event);
}
~~~

The listener runs only after the transaction commits. This avoids sending an email before business data commits, yet an in-process memory event is not a durable queue.

For example, the process may stop right after commit and before the listener performs the send:

~~~text
Database COMMIT succeeds
          |
          v
Process stops abruptly
          |
          v
Listener has not sent mail yet
          |
          v
No durable job to recover
~~~

Comparison:

| Criterion | AFTER_COMMIT event | Transactional outbox |
|---|---|---|
| Avoids sending before commit | Yes | Yes |
| Stores send intent in same transaction | Not by default | Yes |
| Recovers after process restart | Not built-in | Yes, worker reads record again |
| Stateful retries | Must build yourself | Part of the outbox design |
| Complexity | Lower | Higher |
| Best suited for | Best-effort notifications | Notifications needing durable storage and retries |

You can combine domain events with an outbox: the use case emits a business event, and a handler in the same transaction translates the event into an outbox record. The mandatory condition is that **writing the outbox must participate in the same database transaction** as the business change.

If losing an email causes no business harm, AFTER_COMMIT may suffice. If order confirmation, payment, or access-change emails must still be processed after an application restart, an outbox is the better fit.

## 3. Transactional outbox processing flow

A complete flow consists of two stages:

**Stage 1: Writing business data and send intent**

1. Receive command from a controller or message consumer.
2. Validate business rules.
3. Persist business data inside a database transaction.
4. Create an outbox record describing the email to send.
5. Commit both the business data and the outbox record together.

**Stage 2: Sending the email**

1. Worker looks for outbox records due for processing.
2. Claims a batch of records so other workers do not pick them up simultaneously.
3. Commits the claim status and lease.
4. Builds email content from payload/template.
5. Sends through the Mail service and JavaMailSender.
6. Records successful SMTP submission or failure status.
7. For retryable errors, schedules the next attempt.
8. For unrecoverable errors, moves the record to a state requiring manual intervention.

~~~mermaid
sequenceDiagram
    participant API as Application Service
    participant DB as Database
    participant W as Outbox Worker
    participant SMTP as SMTP Server
    API->>DB: BEGIN
    API->>DB: Save order
    API->>DB: Insert mail outbox
    API->>DB: COMMIT
    W->>DB: Claim pending record
    DB-->>W: Claimed payload + lease
    W->>SMTP: JavaMailSender.send()
    SMTP-->>W: SMTP response
    W->>DB: Mark SUBMITTED or schedule retry
~~~

Workers must not hold a database transaction open while calling SMTP. Network calls can be slow or time out; holding a transaction open increases lock contention, ties up connections, and blocks other business transactions.

## 4. Designing the mail_outbox table

A basic schema can include these columns:

| Column | Meaning |
|---|---|
| id | Unique ID of the outbox record |
| event_key | Business-level idempotency key with a unique constraint |
| aggregate_type | Business entity type, e.g., Order |
| aggregate_id | Related order or account ID |
| event_type | Notification type, e.g., ORDER_CONFIRMED |
| recipient | Recipient email address |
| payload | Snapshot or reference data needed to build the email |
| payload_version | Payload schema version |
| status | PENDING, CLAIMED, RETRY, SUBMITTED, DEAD, or UNKNOWN |
| attempt_count | Number of times a worker has claimed/attempted processing |
| available_at | Earliest timestamp eligible for processing |
| claimed_by | ID of the worker holding the lease |
| lease_token | Token identifying the current claim |
| lease_until | Lease expiration timestamp |
| last_error_code | Normalized error code |
| last_error_at | Timestamp of the most recent error |
| created_at | Timestamp when the outbox record was created |
| submitted_at | Timestamp when SMTP accepted submission |

PostgreSQL DDL example:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    event_key VARCHAR(200) NOT NULL UNIQUE,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(120) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    recipient VARCHAR(320) NOT NULL,
    payload JSONB NOT NULL,
    payload_version INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claimed_by VARCHAR(120),
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    last_error_code VARCHAR(100),
    last_error_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    submitted_at TIMESTAMPTZ,
    CONSTRAINT mail_outbox_status_check
        CHECK (status IN (
            'PENDING', 'CLAIMED', 'RETRY',
            'SUBMITTED', 'DEAD', 'UNKNOWN'
        )),
    CONSTRAINT mail_outbox_attempt_check
        CHECK (attempt_count >= 0)
);

CREATE INDEX mail_outbox_ready_idx
    ON mail_outbox (available_at, created_at)
    WHERE status IN ('PENDING', 'RETRY');

CREATE INDEX mail_outbox_lease_idx
    ON mail_outbox (lease_until)
    WHERE status = 'CLAIMED';

CREATE INDEX mail_outbox_aggregate_idx
    ON mail_outbox (aggregate_type, aggregate_id, created_at);
~~~

The DDL above is a starting point; data types, indexes, and retention must be adjusted to your actual database. PostgreSQL uses JSONB; with MySQL, SQL Server, or Oracle, JSON types, claim syntax, and indexes may differ.

### Why must event_key be unique?

A request can be resent due to client retries, message broker redelivery, or duplicate commands received by the application. If each processing pass creates a new outbox record, the recipient may receive multiple identical emails.

`event_key` represents **a single unique business notification intent**, for example:

~~~text
order:ORD-2026-001:confirmation:v1
account:ACC-901:welcome:v1
payment:PAY-773:receipt:v1
~~~

The unique constraint lets the database reject duplicate writes of the same intent. Keys must be designed around business identity; do not generate a fresh random string on each retry because that cannot prevent duplicate requests.

## 5. Writing to the outbox in the same transaction as the order

Order-placement use case example using Spring transactions:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderService {
    private final OrderRepository orderRepository;
    private final MailOutboxRepository outboxRepository;

    public PlaceOrderService(
            OrderRepository orderRepository,
            MailOutboxRepository outboxRepository) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
    }

    @Transactional
    public UUID placeOrder(PlaceOrderCommand command) {
        Order order = orderRepository.save(
                Order.create(command.customerId(), command.items()));

        String eventKey = "order:" + order.getId()
                + ":confirmation:v1";

        OrderConfirmationPayload payload =
                new OrderConfirmationPayload(
                        order.getId().toString(),
                        order.getCustomerName(),
                        order.getCustomerEmail(),
                        order.getTotal().toPlainString());

        outboxRepository.insert(
                UUID.randomUUID(),
                eventKey,
                "Order",
                order.getId().toString(),
                "ORDER_CONFIRMED",
                order.getCustomerEmail(),
                payload,
                1);

        return order.getId();
    }
}
~~~

Classes such as OrderRepository, MailOutboxRepository, Order, PlaceOrderCommand, and OrderConfirmationPayload are illustrative application-defined abstractions. The essential condition is that both the business repository and the outbox repository use **the same database transaction manager and the same transaction boundary**.

If the outbox insert fails, the order-placement transaction must roll back so no committed order exists without a send intent. If saving the order fails, the outbox must not commit either. Do not catch and swallow an outbox insert exception, as doing so breaks the model's guarantee.

### Outbox insertion repository

With Spring JDBC, a single insert statement can be used:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcMailOutboxRepository implements MailOutboxRepository {
    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;

    public JdbcMailOutboxRepository(
            JdbcTemplate jdbcTemplate,
            ObjectMapper objectMapper) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
    }

    @Override
    public void insert(
            UUID id,
            String eventKey,
            String aggregateType,
            String aggregateId,
            String eventType,
            String recipient,
            Object payload,
            int payloadVersion) {
        try {
            String json = objectMapper.writeValueAsString(payload);
            jdbcTemplate.update("""
                    INSERT INTO mail_outbox (
                        id, event_key, aggregate_type, aggregate_id,
                        event_type, recipient, payload, payload_version
                    )
                    VALUES (?, ?, ?, ?, ?, ?, CAST(? AS jsonb), ?)
                    """,
                    id, eventKey, aggregateType, aggregateId,
                    eventType, recipient, json, payloadVersion);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Cannot serialize mail outbox payload", ex);
        }
    }
}
~~~

The SQL example uses PostgreSQL JSONB syntax. JdbcTemplate participates in the current Spring transaction when configured with the same DataSource/transaction manager. Do not open an independent connection or auto-commit in this repository.

If the unique constraint on event_key is violated, decide based on context: it may be a duplicate command that was already handled. The use case should return an appropriate idempotent result or detect the conflict; never generate a new event_key just to re-insert and send the email a second time.

## 6. Should the payload contain a snapshot or only the aggregate ID?

There are two ways to store data for the worker to construct the email.

**Snapshot payload** contains the fields needed for sending at the time the business operation commits:

~~~json
{
  "orderId": "ORD-2026-001",
  "customerName": "Nguyen Minh Anh",
  "recipient": "customer@example.test",
  "total": "2230000",
  "currency": "VND",
  "locale": "vi-VN"
}
~~~

The advantage is that the email content reflects the state at the moment the event occurred. If the customer changes their email address or the order changes later, the worker still has the saved snapshot. The drawback is that payloads may contain personal data and require schema/retention management.

**Reference payload** contains only the entity's ID:

~~~json
{
  "orderId": "ORD-2026-001"
}
~~~

The worker queries the order when processing. Payloads are smaller and avoid duplicating data, yet the email may reflect the latest state rather than the state when the event occurred. The entity could also be deleted or modified before the worker runs.

| Criterion | Snapshot | Reference |
|---|---|---|
| Reflects state at commit time | Explicit | Not guaranteed |
| Payload size | Larger | Smaller |
| Depends on re-querying domain data | Less | Yes |
| Sensitive data in outbox | Potentially more | Potentially less |
| Best suited for | Receipts, confirmations needing historical content | Notifications needing latest state |

There is no single right choice for every email. Decide based on business semantics, privacy policies, and data retention capabilities.

### Versioning the payload

Outbox records can outlive a single application release. If a new worker reads an old payload whose schema has changed, deserialization may fail or misinterpret data. Use payload_version and maintain backward-compatible readers for still-active versions:

~~~java
public record OrderConfirmationPayloadV1(
        String orderId,
        String customerName,
        String recipient,
        String total,
        String currency,
        String locale) {
}
~~~

When changing the schema, create a new version and route deserialization by payload_version. Do not silently change the meaning of a field concurrently read by old and new workers.
## 7. Safely claiming outbox records with multiple workers

An application may run multiple instances or multiple workers to increase throughput. If all query PENDING records and send them simultaneously, the same email may be processed concurrently multiple times.

Workers must **claim** records in a short transaction. The database must guarantee each record is leased to at most one worker at a time.

With PostgreSQL, `FOR UPDATE SKIP LOCKED` can be used:

~~~sql
WITH candidates AS (
    SELECT id
    FROM mail_outbox
    WHERE
        (status IN ('PENDING', 'RETRY')
            AND available_at <= CURRENT_TIMESTAMP)
        OR
        (status = 'CLAIMED'
            AND lease_until < CURRENT_TIMESTAMP)
    ORDER BY available_at, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 50
)
UPDATE mail_outbox AS item
SET status = 'CLAIMED',
    claimed_by = :worker_id,
    lease_token = gen_random_uuid(),
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    attempt_count = item.attempt_count + 1
FROM candidates
WHERE item.id = candidates.id
RETURNING
    item.id,
    item.event_key,
    item.event_type,
    item.recipient,
    item.payload,
    item.payload_version,
    item.attempt_count,
    item.lease_token,
    item.lease_until;
~~~

Meaning:

- `FOR UPDATE` locks the selected rows during the claim transaction.
- `SKIP LOCKED` lets other workers skip rows currently locked by another worker instead of blocking.
- `LIMIT` caps batch size so one worker does not grab too much work.
- `lease_until` defines when the claim expires if a worker dies or fails to finish.
- `lease_token` identifies the specific claim, preventing a stale worker from updating status after another worker has reclaimed the row.
- `attempt_count` increments when a worker picks up the job; agree consistently on whether this counts claims or actual SMTP attempts.

`gen_random_uuid()` is built into modern PostgreSQL versions; if your database lacks it, generate the token in the application and pass it into the claim statement appropriately. The SQL above is a PostgreSQL example, not portable verbatim across all database engines.

### Claim must commit before sending over SMTP

Separate claiming into its own transactional service:

~~~java
@Service
public class MailOutboxClaimService {
    private final MailOutboxJdbcRepository repository;

    public MailOutboxClaimService(
            MailOutboxJdbcRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public List<ClaimedMail> claimBatch(
            String workerId, int batchSize) {
        return repository.claim(workerId, batchSize);
    }
}
~~~

When the method returns through the Spring transactional proxy, the claim transaction has finished and committed. Only then does the worker call SMTP. Do not wrap the entire poll, send, and status update loop in a single long transaction.

If using Spring Data JPA, claiming can be implemented via native queries or a repository tailored to your database. With PostgreSQL and multiple workers, `SKIP LOCKED` is a common way to avoid contention. Always verify the isolation level and locking behavior of your database.

### Lease expiration and work recovery

If a worker is killed after claiming, rows must not stay stuck forever in CLAIMED. Once `lease_until` has passed, another worker can reclaim them.

The lease should exceed the maximum expected send time, including SMTP connection and write timeouts. For long-running tasks, a worker can periodically renew its lease. If the lease is too short, a second worker may claim the same email while the first is still sending.

`lease_token` guards status updates: a worker may mark success/failure only if the token still matches its own claim. It cannot prevent SMTP from receiving the same email twice if two workers genuinely send concurrently within an overlapping window.

## 8. Sending mail outside the claim transaction

The worker can orchestrate as follows:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MailOutboxWorker {
    private final MailOutboxClaimService claimService;
    private final OutboxMailSender mailSender;
    private final MailOutboxStateService stateService;

    public MailOutboxWorker(
            MailOutboxClaimService claimService,
            OutboxMailSender mailSender,
            MailOutboxStateService stateService) {
        this.claimService = claimService;
        this.mailSender = mailSender;
        this.stateService = stateService;
    }

    @Scheduled(fixedDelay = 1000)
    public void poll() {
        List<ClaimedMail> batch =
                claimService.claimBatch("mail-worker-1", 50);

        for (ClaimedMail item : batch) {
            try {
                mailSender.send(item);
                stateService.markSubmitted(
                        item.id(), item.leaseToken());
            } catch (RetryableMailException ex) {
                stateService.scheduleRetry(
                        item, ex.errorCode(), ex.retryAfter());
            } catch (PermanentMailException ex) {
                stateService.markDead(
                        item.id(), item.leaseToken(), ex.errorCode());
            } catch (UnknownSubmissionException ex) {
                stateService.markUnknown(
                        item.id(), item.leaseToken(), ex.errorCode());
            }
        }
    }
}
~~~

`ClaimedMail`, `OutboxMailSender`, the exceptions, and the state service are illustrative abstractions. In a real application, configure `@EnableScheduling`, stable per-instance worker IDs, and logging/metrics. If using multiple worker threads within one instance, each worker needs its own claim token.

This flow has three transaction boundaries:

1. **Claim transaction:** selects rows and sets leases, then commits.
2. **SMTP call:** runs outside any database transaction.
3. **State transaction:** updates SUBMITTED, RETRY, DEAD, or UNKNOWN once an outcome is known.

### Status updates must verify the lease token

When SMTP accepts the message:

~~~sql
UPDATE mail_outbox
SET status = 'SUBMITTED',
    submitted_at = CURRENT_TIMESTAMP,
    claimed_by = NULL,
    lease_token = NULL,
    lease_until = NULL,
    last_error_code = NULL,
    last_error_at = NULL
WHERE id = :id
  AND status = 'CLAIMED'
  AND lease_token = :lease_token;
~~~

The worker must check the updated row count. If it is 0, the claim expired or another worker modified the row; do not overwrite the newer state with a stale result.

When a retry is needed:

~~~sql
UPDATE mail_outbox
SET status = 'RETRY',
    available_at = :next_attempt_at,
    last_error_code = :error_code,
    last_error_at = CURRENT_TIMESTAMP,
    claimed_by = NULL,
    lease_token = NULL,
    lease_until = NULL
WHERE id = :id
  AND status = 'CLAIMED'
  AND lease_token = :lease_token;
~~~

State-update statements must also run in short transactions. Never update a row solely by ID if there is any chance the old claim expired and another worker took over.

## 9. Bounded retries and backoff

An SMTP provider can temporarily refuse connections, rate-limit traffic, or suffer network errors. The worker should classify errors and schedule retries instead of looping continuously.

A common policy is **exponential backoff with jitter**:

~~~text
delay = min(maxDelay, baseDelay * 2^(attempt - 1))
nextAttempt = now + delay + randomJitter
~~~

Example with a 10-second base delay and 30-minute max delay:

| Attempt | Base delay before jitter |
|---|---:|
| 1 | 10 seconds |
| 2 | 20 seconds |
| 3 | 40 seconds |
| 4 | 80 seconds |
| 5 | 160 seconds |
| 6 | 320 seconds |
| Subsequent attempts | Increases up to a maximum of 30 minutes |

Random jitter prevents multiple workers from retrying in lockstep once a provider recovers. If the provider returns a Retry-After header or guidance, the policy can respect that value within configured bounds.

### Do not retry every error

| Error type | Example | Handling approach |
|---|---|---|
| Temporary | Connection refused, timeout before transmitting message, SMTP 4xx | Retry with backoff |
| Fixable via configuration change | Wrong credentials, incompatible TLS config | Stop rapid retries, alert operations |
| Permanent for message/recipient | Invalid address, SMTP 5xx recipient rejected | DEAD or manual handling needed |
| Invalid content | Template missing variable, unreadable attachment | Fix data/template; do not futilely retry SMTP |
| Uncertain outcome | Timeout after DATA transmitted, client received no final response | UNKNOWN or retry under a duplicate-tolerant policy |

Spring Mail exceptions are not always sufficient on their own to determine whether SMTP accepted a message. Inspect root causes, SMTP codes, protocol stage, and provider reconciliation options.

### DEAD status and manual handling

After the maximum retry count, or when an error is determined to be permanent, transition the record to DEAD. Store normalized error codes, timestamps, attempt counts, and safe diagnostic details. An operations tool can allow:

- Viewing DEAD records by email type and timestamp.
- Inspecting sanitized payloads.
- Fixing source data or configuration.
- Triggering a controlled replay with audit logging.

Never retry infinitely automatically. It creates continuous load, raises costs, and risks getting the sending account suspended by the provider.
## 10. Outbox does not guarantee exactly-once over SMTP

A transactional outbox ensures the application does not lose the **send intent** between database commit and when a worker begins processing. However, another gap remains:

~~~text
Worker sends message
       |
       v
SMTP server returns 250 Accepted
       |
       v
Worker crashes before updating outbox
       |
       v
Lease expires, another worker reclaims
       |
       v
Email may be sent a second time
~~~

The database has not recorded SUBMITTED, while SMTP may already have accepted the message. When a worker retries, the application cannot know for sure whether the previous attempt was accepted by the server.

This is why an outbox typically provides **at-least-once processing**: records are reprocessed until reaching a terminal state or requiring intervention. It does not by itself provide **exactly-once delivery**.

### Why does Message-ID not completely solve duplicates?

The application can generate a stable Message-ID per outbox event and keep it identical across retries:

~~~java
helper.setMessageId(
        "<" + outboxEventId + "@mail.example.test>");
~~~

Message-ID is helpful for reconciliation and identifying the same message. However, standard SMTP does not require servers or mailbox clients to deduplicate messages sharing a Message-ID. Therefore, do not treat Message-ID as a guaranteed idempotency mechanism.

If using an email provider via an HTTP API that supports an **idempotency key**, pass a stable event key and follow the provider's idempotency window and schema. This capability depends on the provider; not all email APIs offer it.

### Reducing duplicate-send risk

- Generate a stable, unique event_key in the database to prevent creating multiple send intents for the same event.
- Keep Message-ID constant across retries to aid tracing and reconciliation.
- If the provider supports an idempotency key, use the outbox event ID as the key.
- Record UNKNOWN status when submission success cannot be determined.
- For emails that must never duplicate, design reconciliation or manual verification workflows for uncertain states.
- Do not blindly retry a message that may already have been accepted by SMTP if duplicate impact is severe.

**Idempotency of creating an outbox record** and **idempotency of sending over SMTP** are two separate problems. A unique event key solves duplicate intent creation in the database; it cannot recall a message already accepted by SMTP.

## 11. UNKNOWN status and retry decisions

When an SMTP client receives an error before starting body transmission, it can conclude submission did not complete and retrying is generally safe. However, if the connection drops after the client has sent the DATA section and before receiving the final response, the state becomes uncertain.

Example:

~~~text
Client                         SMTP server
  |                                  |
  |------ MAIL FROM ---------------->|
  |------ RCPT TO ------------------>|
  |------ DATA --------------------->|
  |------ message body ------------>|
  |------ <CRLF>.<CRLF> ------------>|
  |                                  | May have already saved message
  |       Connection lost            |
  X                                  |
~~~

The worker does not know whether the server committed the message to its queue. There are two options:

| Policy | Behavior | Risk |
|---|---|---|
| Retry immediately | Maximizes chance an email eventually goes out | May send duplicate |
| Move to UNKNOWN for reconciliation | Avoids blind resending | May delay or miss email if server actually did not receive it |

The choice depends on the notification's meaning. Low-impact informational emails can favor retrying; emails involving transaction codes, payment confirmations, or sensitive notices may require reconciliation first.

Not every MailSendException implies UNKNOWN status. Inspect the nested cause, SMTP code, failure stage, and provider reconciliation capabilities. Classify based on technical evidence, not solely on the exception class name.

## 12. Preserving email ordering per business entity

Multiple workers using SKIP LOCKED can process outbox records in different orders. For example, one order generates:

1. ORDER_CONFIRMED.
2. ORDER_SHIPPED.
3. ORDER_DELIVERED.

If the first record hits a retry while the second is ready, another worker might send ORDER_SHIPPED before ORDER_CONFIRMED. If notification ordering matters, additional design is required.

Some approaches:

- Store an aggregate_version or sequence number for each event.
- Claim only the earliest unprocessed event per aggregate.
- Partition workers by aggregate ID so the same aggregate goes through the same stream.
- Use a queue partitioned by aggregate key if forwarding to a broker.

Logical condition example:

~~~text
ORDER_CONFIRMED sequence=1
ORDER_SHIPPED   sequence=2
ORDER_DELIVERED sequence=3

Only allow sequence=2 to be processed once sequence=1
has reached a business-accepted terminal state.
~~~

Not every email needs strict ordering. If two notifications are independent, allowing parallel processing increases throughput and lowers latency. Only add serialization when ordering is a genuine business requirement.

## 13. Workers must be operated and observed as a separate component

An outbox is a durable mechanism, yet without running workers, emails stay queued. The system must monitor backlog health and processing latency.

Useful metrics:

| Metric | Meaning |
|---|---|
| outbox_pending_count | Number of waiting records |
| outbox_oldest_pending_age | Age of the oldest waiting record |
| outbox_claimed_count | Number of records currently holding a lease |
| outbox_expired_lease_count | Number of expired leases |
| outbox_retry_count | Number of records in retry state |
| outbox_dead_count | Number of records needing manual intervention |
| outbox_unknown_count | Number of submissions with uncertain outcome |
| mail_submission_success_total | Count of accepted SMTP submissions |
| mail_submission_failure_total | Count of failed submissions |
| mail_submission_duration | SMTP send duration |

Track **backlog age** in addition to record counts. An outbox with 100 freshly created records may be normal; a single critical record waiting for hours can indicate an incident.

### Logs with correlation IDs

Each outbox record should have a stable ID connecting logs across:

~~~text
HTTP request
  -> orderId
  -> outboxEventId
  -> workerId
  -> SMTP submission attempt
  -> provider message reference (if available)
~~~

Log event_key, aggregate_id, attempt_count, worker_id, status transitions, and normalized error codes. Do not log passwords, access tokens, full HTML bodies, reset tokens, or unnecessary recipient data.

### Operational alerts

- Pending age exceeds threshold.
- Worker stops polling or misses heartbeat.
- Sudden spike in retries.
- DEAD/UNKNOWN records appear or grow rapidly.
- SMTP provider returns authentication, quota, or throttling errors.
- Leases expire repeatedly, indicating hung workers or processing times exceeding configuration.

A good dashboard displays status by email type, provider, time, and error cause without exposing private content.

## 14. Managing outbox data lifecycle

The outbox can grow continuously. A retention policy is needed:

- Retain PENDING, CLAIMED, RETRY, DEAD, and UNKNOWN records as required by operations.
- SUBMITTED records can be archived or purged after an agreed audit window.
- Retain long enough for reconciliation, duplicate investigation, and support inquiries.
- Never delete records with active leases or pending retries.
- If long-term auditing is needed, move minimal metadata to an archive table instead of keeping sensitive payloads indefinitely.

With PostgreSQL, partial indexes on ready states and leases help worker queries avoid full-table scans. However, as data grows large, check query plans, vacuuming, bloat, and partitioning/archival strategies. Do not add indexes to every column since each index adds overhead to inserts and updates.

### Avoid storing sensitive data longer than necessary

Payloads may contain email addresses, names, totals, addresses, or tokens. Do the following:

- Store only the fields needed to build the email.
- Encrypt or protect columns/payloads per data requirements.
- Restrict outbox table read access to workers and operations tooling.
- Do not put secrets or long-lived tokens in payloads.
- Purge or redact payloads after processing if content auditing is unnecessary.
- Align retention with the application's data policies.

## 15. When to use polling and when to use CDC/message brokers?

A worker can poll the outbox table directly with SQL. For moderate traffic, this is simple and easy to operate. When the system needs multiple consumers or high throughput, **Change Data Capture (CDC)** can read outbox changes and publish them to a message broker.

~~~mermaid
flowchart TD
    A[Business transaction] --> B[Business table + Outbox table]
    B --> C{Dispatch method}
    C --> D[Polling worker]
    C --> E[CDC connector]
    D --> F[Mail sender]
    E --> G[Message broker]
    G --> H[Mail consumer]
    H --> F
    F --> I[SMTP / Email provider]
~~~

| Criterion | Polling | CDC + broker |
|---|---|---|
| Components to operate | Database and worker | Database log, connector, broker, consumer |
| Latency | Tied to poll interval | Can be lower |
| Complexity | Lower | Higher |
| Multiple consumers | Must scale claim/dispatch logic | Broker supports fan-out/partitioning |
| Best suited for | Small/medium apps, few event types | Distributed systems, many consumers, high throughput |

CDC does not eliminate the need for idempotency. Connectors or consumers can replay records after a restart; the mail consumer must still handle duplicates and track state by event ID.

When using a broker, a common pattern is an outbox dispatcher/CDC publishing events to the broker while consumers send emails. If the broker receives an event before the dispatcher records its offset/position, the event may be replayed. Consumers must have appropriate deduplication.

**Do not add Kafka just to send an order confirmation email** if a polling worker meets your load and operational requirements. Choose architecture based on throughput, consumer count, latency, and team operational capacity.

## 16. Testing a transactional outbox

The most important test proves that business data and the outbox record share the same transaction outcome.

### Testing transaction commit

When the use case succeeds:

~~~java
@Test
void savesOrderAndOutboxTogether() {
    UUID orderId = placeOrderService.placeOrder(validCommand);

    assertThat(orderRepository.findById(orderId)).isPresent();
    assertThat(outboxRepository.findByAggregateId(orderId.toString()))
            .hasSize(1);
}
~~~

This is an integration test example; repositories and the database must share the same transaction manager. If the test method itself is annotated with @Transactional and rolls back at the end of the test, data may not persist after the test ends. Understand the test transaction vs. use-case transaction before asserting.

### Testing outbox insert failure rolling back the transaction

Simulate an error during outbox insertion and verify the order is not committed:

~~~java
@Test
void rollsBackOrderWhenOutboxInsertFails() {
    doThrow(new IllegalStateException("outbox unavailable"))
            .when(outboxRepository)
            .insert(any(), any(), any(), any(), any(), any(), any(), anyInt());

    assertThatThrownBy(() -> placeOrderService.placeOrder(validCommand))
            .isInstanceOf(IllegalStateException.class);

    assertThat(orderRepository.findAll()).isEmpty();
}
~~~

This illustrative test must run against a real transaction/database to verify rollback. If both the order repository and outbox repository are mocked, the test only verifies call flow rather than proving atomicity.

### Testing successful worker sending

With a PENDING outbox record, the worker claims it, sends successfully, and updates to SUBMITTED. You can mock the mail sender to assert payload/recipient, while testing state transitions against a test database:

~~~java
@Test
void marksRecordSubmittedAfterSuccessfulSend() {
    ClaimedMail claimed = claimService.claimOne("worker-test");

    worker.process(claimed);

    assertThat(outboxRepository.findById(claimed.id()).orElseThrow()
            .status()).isEqualTo("SUBMITTED");
}
~~~

### Testing retries and DEAD

- Temporary failures set status to RETRY with available_at in the future.
- Permanent failures set status to DEAD.
- Exceeding max attempts stops infinite retries.
- When the lease token no longer matches, an old worker cannot update status.
- Expired leases allow a new worker to reclaim.

### Testing contention across multiple workers

Run two workers concurrently over multiple outbox records and verify:

- A record is claimed by only one worker at a time.
- The second worker skips locked rows.
- Records are not lost when one worker stops.
- Batch size and leases behave properly under load.

This test requires a database supporting the exact locking syntax used. H2 may not fully reproduce PostgreSQL SKIP LOCKED behavior; use Testcontainers PostgreSQL or an appropriate integration database when testing real locking.

### Testing the crash window after SMTP acceptance

Simulate a worker sending successfully and crashing before the state update. When the lease expires, the record may be reprocessed. The test should demonstrate the **duplicate risk** explicitly and apply provider idempotency/deduplication where supported rather than claiming exactly-once.

## 17. Common design mistakes

**Writing outbox with REQUIRES_NEW.** If the outbox commits in a separate transaction while the order transaction rolls back, the system can send an email for a non-existent order. Outbox insertion must join the business transaction; REQUIRED propagation is usually appropriate with a shared transaction manager.

**Writing outbox to a different database.** Two independent DataSources are not automatically atomic just because they sit inside one @Transactional method. Rolling back/committing together requires a suitable distributed mechanism; the traditional transactional outbox assumes business data and the outbox share one database transaction.

**Sending SMTP inside the business write transaction.** This pulls network latency into the transaction and creates the scenario where email goes out and the database rolls back. Workers send after commit to preserve boundaries.

**Claiming and holding the transaction during send.** SMTP can be slow or time out, keeping row locks and connections held for long periods. Claim/commit first, send outside the transaction, and update status in a new transaction.

**Missing leases or recovery mechanisms.** A worker crash can leave rows stuck in CLAIMED forever. Use expiring leases and controlled reclaim logic.

**Lease too short.** A second worker may reclaim while the first is still sending. Leases must align with timeouts, batch sizes, and processing times; long tasks need lease renewal heartbeats.

**Not checking lease tokens on update.** A stale worker can overwrite a newer worker's result. Each claim should have a unique token, and every state update must be conditioned on that token.

**Infinite retries or unclassified errors.** Template errors, wrong credentials, and invalid recipients must not be treated like transient timeouts. Use retry policies, max attempts, and DEAD/UNKNOWN states.

**Claiming exactly-once.** An outbox does not eliminate the gap between SMTP acceptance and database updates. Explicitly acknowledge duplicate possibility and use idempotency when supported by the provider.

**Not versioning payloads.** Old records may fail to deserialize after deploying a new release. Use payload_version and keep backward compatibility while old records still exist.

**Storing entire MIME messages in the outbox without a data policy.** HTML, attachments, and tokens can contain sensitive information. Store only required payload fields, protect access, and enforce retention.

## 18. Implementation roadmap in Spring Framework Mail

A step-by-step implementation approach:

1. Identify which email types require durability and the business events that trigger them.
2. Design the outbox table, statuses, event keys, payload versions, and indexes.
3. Create an outbox repository using the same DataSource/transaction manager as business data.
4. Inside `@Transactional` use cases, save business data and insert the outbox record.
5. Build a claim service using database-appropriate locking/leases.
6. Build a worker that fetches batches, commits claims, and invokes the mail adapter outside the transaction.
7. Build a state service to mark SUBMITTED, RETRY, DEAD, or UNKNOWN guarded by lease tokens.
8. Add backoff, jitter, retry limits, and policies for uncertain errors.
9. Add metrics, log correlation, backlog alerts, and an audited replay workflow.
10. Test commit/rollback, multi-worker concurrency, lease expiry, SMTP failures, and crash windows.
11. Establish retention policies and payload protection.

### Component boundaries

~~~text
Application layer
  PlaceOrderService
      |
      +--> OrderRepository
      |
      +--> MailOutboxRepository
                |
                v
          Database transaction

Infrastructure
  MailOutboxClaimService
      |
      v
  MailOutboxWorker
      |
      +--> Template renderer
      |
      +--> MimeMessageHelper
      |
      +--> JavaMailSender
                |
                v
             SMTP
~~~

The application service knows **when to send** and records send intent. The worker knows **when to process records**. The mail adapter knows **how to build and send emails**. This separation lets you swap SMTP providers or templates without changing business transactions.

## 19. When is a transactional outbox unnecessary?

An outbox adds schema, workers, retries, statuses, and operational tooling. Not every email requires that level of guarantee.

Simpler approaches can be chosen when:

- The email is purely convenience-oriented and can be resent manually.
- Losing one email does not corrupt business data or entitlements.
- The application records notification history elsewhere and accepts delivery gaps.
- Traffic is low, email loss risk is small, and outbox operational cost outweighs benefits.

Consider an outbox when:

- Emails reflect committed transactions such as orders, payments, or account changes.
- Send requests must not be lost across process restarts.
- Retries and send-status auditing are needed.
- Multiple workers or multiple instances process traffic.
- The system must decouple SMTP latency from HTTP requests.

Base the decision on **the impact of missed or duplicate emails**, audit requirements, and operational readiness—not merely on whether Spring Mail is already present.

## 20. Principles to remember

A transactional outbox writes **business data and email send intent in the same database transaction**. After commit, a worker claims records with a lease, sends email via JavaMailSender outside the transaction, and updates status in another short transaction.

The design needs event keys to prevent duplicate intent creation, leases/tokens to coordinate multiple workers, bounded retries, an UNKNOWN status for uncertain SMTP outcomes, and payload retention/protection policies. If per-aggregate ordering is required, add sequences or an appropriate partitioning mechanism.

**An outbox guarantees send requests are stored durably alongside business state; SMTP can still receive duplicates if a worker crashes after acceptance.** Design and operate with those semantics, use provider idempotency where available, and never claim exactly-once delivery when SMTP does not provide that guarantee.
