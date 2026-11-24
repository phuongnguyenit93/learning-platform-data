# Preventing Duplicate Sends When an Operation Is Retried

An email-sending operation may be invoked multiple times when a user double-clicks a button, a browser retries after a timeout, a gateway retries, an application reprocesses a queue message, or a worker restarts after a failure. If every invocation creates a new email, recipients can receive multiple identical messages even though the user performed only one business action.

In **Spring Framework Mail**, **JavaMailSender** sends messages over SMTP, and **MimeMessageHelper** prepares MIME content. Neither API knows on its own whether two calls to **send(...)** represent the same logical operation. To avoid creating duplicate emails, the application must manage **idempotency** in the business layer and persist sending state durably.

A key distinction to understand: an application can guarantee that retrying an operation does not create additional send requests in its database/queue. However, SMTP does not provide universal idempotency to guarantee strict exactly-once email delivery across all network failure scenarios. This lesson separates those two scopes and shows how to design accordingly.

## 1. What is idempotency?

An operation is **idempotent** when repeating the same operation with the same identifier produces no additional business side effects beyond the first execution.

For example, a user clicks "Send invoice" for order ORD-2026-001. The browser sends the request but receives no response due to a slow network. The user clicks again. If the server creates two distinct notifications, two invoice emails may be sent. If the server recognizes this as the same operation, the second request can return the result of the first request without creating another notification.

```text
First call:
  POST /orders/ORD-2026-001/send-invoice
  Idempotency-Key: 8f...a2
          |
          v
  Create notification N-123
          |
          v
  Queue N-123 for sending

Retry call:
  POST /orders/ORD-2026-001/send-invoice
  Idempotency-Key: 8f...a2
          |
          v
  Found already-recorded operation
          |
          v
  Return notification N-123
  Do not create notification N-124
```

Idempotency does not mean every email sent to the same address with the same subject gets merged into one. Two sends may be two legitimate distinct actions. The application must define **what constitutes a single business operation** and assign an identifier to that operation.

## 2. Distinguishing retried operations from intentional resends

Two cases can look identical externally while having different meanings:

| Case | Meaning | Desired behavior |
| --- | --- | --- |
| Browser retry on timeout | Same operation did not receive a response | Return prior result; do not create another notification |
| User double-click | Same operation submitted nearly concurrently | Record only once |
| API gateway retry | Infrastructure resends the same request | Recognize the same idempotency key |
| Worker reprocesses outbox event | Same notification retried after an error | Use stable notification ID and retry policy |
| User clicks "Resend email" after delivery | A new intentional action | Create a new resend operation per business rules |
| User requests invoice for another purchase | Different business event | Create a new notification |

**Never use recipient + subject as an idempotency key.** A person can legitimately receive multiple invoices, notices, or updates with the same subject.

For example, two invoice sends for the same order may be treated as:

- The same operation if the second request is merely a retry of the first.
- A new operation if the user intentionally clicked "Resend a copy" afterward.

This rule must be explicit in the API and data model, rather than guessed from email content.

## 3. What is an idempotency key?

An **idempotency key** is a client- or server-generated identifier representing one logical operation. When a request is retried, the client resends the **same key**. The server uses that key to look up the previously recorded outcome.

Example HTTP request:

```http
POST /api/orders/ORD-2026-001/send-invoice HTTP/1.1
Idempotency-Key: 8f6e4a10-2e58-4b82-9b3c-6b2a7c6f12a2
Content-Type: application/json

{
  "recipient": "customer@example.net"
}
```

If the request is retried, the client sends the exact same `Idempotency-Key` value. The server can return the same notification ID and current status.

### Rules for choosing keys

- A key must be generated per **logical operation**, not per HTTP attempt.
- Keys should have sufficient randomness, such as a UUID.
- Keys must be scoped by tenant, caller, or operation type.
- Never use email addresses, customer names, or personal data as keys.
- Never use keys as an authentication or authorization mechanism.
- Clients must retain the key long enough to resend on timeout; do not generate a fresh UUID per retry.

A scope might include:

```text
tenant_id + operation_name + idempotency_key
```

That way, the same key string across two different tenants or two different operation types is not treated as the same operation.

### Key and request payload must stay consistent

Suppose a client sends:

```text
Idempotency-Key: abc-123
recipient = customer-a@example.net
```

Then reuses key `abc-123` but changes the recipient to `customer-b@example.net`. This is no longer a retry of the same request. The server must detect the mismatch and return a conflict error rather than silently returning the old result or sending to the new recipient.

One way to implement this is storing a **request hash** alongside the key:

```text
scope: tenant-01 / send-invoice
key: abc-123
request_hash: SHA-256(canonical request)
notification_id: N-123
```

When the key already exists:

- Matching hash: return the result of the already-recorded operation.
- Different hash: reject the request because the key was already used for a different payload.

The hash must be computed from data canonicalized by a deterministic rule. Never hash a raw JSON object with non-deterministic field ordering assuming all serializations are identical.

## 4. Two layers of duplicate protection working together

An email-sending system typically needs two kinds of identifiers:

1. **Request idempotency key:** identifies retried client requests.
2. **Business key:** identifies a notification corresponding to a business event, such as "invoice for order X was issued".

These layers address different sources of duplication:

| Layer | What it prevents | Example |
| --- | --- | --- |
| Request idempotency key | Client resending the same request | Double-click or HTTP timeout |
| Business key | Two backend flows creating notifications for one event | Listener and scheduled job handling the same order event |
| Notification ID | Worker retrying the same notification | Worker reprocessing an outbox row |
| Provider idempotency key (if API supports it) | Provider receiving the same send request twice | Resending an API request after timeout |

Not every system needs all four layers. Still, an idempotency key at the HTTP layer alone is insufficient if the backend can create the same notification from two event consumers or two separate jobs.

### Example business key

A key can be constructed from:

```text
notification_type = INVOICE_READY
business_event_id = order-123-invoice-issued-v1
```

The database can place a unique constraint on `(notification_type, business_event_id)`. As a result, two workers trying to create an invoice email for the same event can record at most one notification.

If business rules allow resending a copy, model it as a new operation with its own identifier, such as `resend_request_id`, rather than dropping the unique constraint or mutating keys arbitrarily.

## 5. Do not rely on single-instance in-memory state

An unsafe approach is storing processed keys in a `HashSet` or `ConcurrentHashMap`:

```java
private final Set<String> processedKeys = ConcurrentHashMap.newKeySet();

public void send(String key, String recipient) {
    if (!processedKeys.add(key)) {
        return;
    }

    mailSender.send(buildMessage(recipient));
}
```

This can prevent duplicate calls inside one JVM with a single instance, but fails in real production deployments:

- When the process restarts, the Set is lost.
- Multiple instances have separate memory, so the same key can run on both instances.
- Two threads can both pass the check if check-and-insert logic is not atomic.
- No durable history remains to show whether the email was processed.
- State cannot be recovered after a crash or redeployment.

Idempotency must be stored where all instances can see it with **atomicity**, usually a database with unique constraints/transactions or a distributed store with proper atomic operations.

## 6. Storing idempotency keys and state in the database

An illustrative schema:

```sql
CREATE TABLE mail_idempotency (
    id                  UUID PRIMARY KEY,
    tenant_id           VARCHAR(100) NOT NULL,
    operation_name      VARCHAR(100) NOT NULL,
    idempotency_key     VARCHAR(150) NOT NULL,
    request_hash        VARCHAR(64) NOT NULL,
    notification_id     UUID NOT NULL,
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at          TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uq_mail_idempotency_scope
        UNIQUE (tenant_id, operation_name, idempotency_key)
);

CREATE TABLE mail_notification (
    id                  UUID PRIMARY KEY,
    notification_type   VARCHAR(100) NOT NULL,
    business_event_id   VARCHAR(200) NOT NULL,
    recipient           VARCHAR(320) NOT NULL,
    template_key        VARCHAR(150) NOT NULL,
    template_version    INTEGER NOT NULL,
    status              VARCHAR(30) NOT NULL,
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    next_attempt_at     TIMESTAMP WITH TIME ZONE,
    lease_until         TIMESTAMP WITH TIME ZONE,
    provider_message_id VARCHAR(300),
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    submitted_at        TIMESTAMP WITH TIME ZONE,
    last_error          TEXT,
    CONSTRAINT uq_mail_business_event
        UNIQUE (notification_type, business_event_id)
);
```

This is a starting schema; adjust timestamp types, column lengths, and indexes for your actual database. If storing payloads or mail models, define which fields are allowed, retention windows, and access controls.

Column meanings:

- `tenant_id`, `operation_name`, `idempotency_key`: operation scope.
- `request_hash`: detects key reuse with a different request.
- `notification_id`: links the request to the created notification.
- `business_event_id`: prevents the backend from creating two notifications for the same event.
- `status`: current processing state.
- `attempt_count`, `next_attempt_at`: retry management.
- `lease_until`: expiration time of a worker's temporary processing lease.
- `provider_message_id`: ID returned by the provider if available.
- `submitted_at`: timestamp when SMTP/provider accepted the message per observed outcome.

### Unique constraints are the final guard

Code like:

```java
if (!repository.existsByIdempotencyKey(key)) {
    repository.save(record);
}
```

is unsafe under concurrent requests:

```text
Request A: exists? -> false
Request B: exists? -> false
Request A: insert
Request B: insert
```

Without a database unique constraint, two records can coexist. Let the database enforce uniqueness and use atomic insert/claim operations.

## 7. Handling duplicate requests atomically

The flow must ensure:

1. Check whether the key is already recorded.
2. If present, compare the request hash and return the prior result.
3. If absent, create the notification and insert the key in the same transaction.
4. Commit only when both records are saved successfully.

Pseudocode:

```java
@Transactional
public NotificationReceipt requestInvoiceEmail(
        String tenantId,
        String idempotencyKey,
        InvoiceMailCommand command
) {
    String requestHash = requestHasher.hash(command);

    IdempotencyClaim claim = idempotencyRepository.claim(
            tenantId,
            "SEND_INVOICE",
            idempotencyKey,
            requestHash
    );

    if (!claim.created()) {
        if (!claim.requestHash().equals(requestHash)) {
            throw new IdempotencyConflictException(
                    "Key was already used with another request"
            );
        }
        return notificationRepository.getReceipt(
                claim.notificationId()
        );
    }

    UUID notificationId = claim.notificationId();
    notificationRepository.insertPending(
            notificationId,
            command
    );

    return new NotificationReceipt(notificationId, "PENDING");
}
```

This is an illustrative skeleton; `claim(...)` must be implemented using an atomic database operation. Never do SELECT followed by INSERT without a unique constraint.

### Example atomic operation with PostgreSQL

A common approach uses `INSERT ... ON CONFLICT DO NOTHING`:

```sql
INSERT INTO mail_idempotency (
    id,
    tenant_id,
    operation_name,
    idempotency_key,
    request_hash,
    notification_id,
    created_at
)
VALUES (
    :id,
    :tenantId,
    :operationName,
    :idempotencyKey,
    :requestHash,
    :notificationId,
    CURRENT_TIMESTAMP
)
ON CONFLICT (
    tenant_id,
    operation_name,
    idempotency_key
)
DO NOTHING;
```

Then read the row by scope and key:

```sql
SELECT request_hash, notification_id
FROM mail_idempotency
WHERE tenant_id = :tenantId
  AND operation_name = :operationName
  AND idempotency_key = :idempotencyKey;
```

If the insert created the row, the current request owns the new operation. If the row already existed, the current request reads the prior outcome and compares hashes. Both claiming and inserting the notification must run in the same transaction; if notification creation fails, the claim must roll back too.

For other databases, use equivalent upsert/unique-constraint mechanisms. Verify transaction semantics and isolation levels of your database.

## 8. Transactional outbox: recording send requests with business logic

Another bug occurs when an application updates the database and sends email in the same method:

```java
@Transactional
public void confirmOrder(Order order) {
    order.confirm();
    orderRepository.save(order);

    mailSender.send(buildConfirmationMessage(order));
}
```

Sending over SMTP is a side effect outside the database. The database transaction can roll back, yet the SMTP server cannot roll back an email it already accepted. For example:

1. SMTP accepts the email.
2. Then the database transaction fails.
3. The order rolls back to its old state, but the confirmation email was already sent.

Conversely, if the database commits and SMTP fails, the request does not know how to proceed.

A **transactional outbox** solves recording the send request:

```text
Single database transaction:
  - update order status
  - create PENDING notification
  - create outbox event
          |
          v
       COMMIT
          |
          v
Worker reads outbox
          |
          v
Send email via JavaMailSender
          |
          v
Update notification status
```

What matters is that business state and the send request are recorded **in the same database transaction**. Workers process only committed requests.

### Example outbox table

```sql
CREATE TABLE mail_outbox (
    id              UUID PRIMARY KEY,
    notification_id UUID NOT NULL UNIQUE,
    event_type      VARCHAR(100) NOT NULL,
    payload         JSONB NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    published_at    TIMESTAMP WITH TIME ZONE
);
```

Example business service:

```java
@Transactional
public UUID confirmOrder(UUID orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();
    orderRepository.save(order);

    UUID notificationId = UUID.randomUUID();

    mailNotificationRepository.insertPending(
            notificationId,
            "ORDER_CONFIRMED",
            order.getId().toString(),
            order.getCustomerEmail()
    );

    outboxRepository.insert(
            UUID.randomUUID(),
            notificationId,
            "MAIL_NOTIFICATION_CREATED"
    );

    return notificationId;
}
```

This is a condensed example. A unique constraint on the business event is needed so two calls to `confirmOrder` or two listeners do not create the same notification. If order confirmation itself is idempotent, order state and notifications must update under consistent rules.

### An outbox does not automatically guarantee single email delivery

The outbox ensures the send request is not lost when the business transaction commits. Workers typically operate under **at-least-once** semantics: an event may be read again if a worker crashes or loses acknowledgment. Therefore, workers still need stable notification IDs, claim mechanisms, and delivery-outcome handling.

An outbox solves atomicity between the database and recording work; it does not turn SMTP into an exactly-once system.

## 9. State machine for notifications

Do not use just a single boolean `sent` column. You need states sufficient to distinguish pending, in-progress, accepted, retryable errors, and ambiguous outcomes.

An illustrative state machine:

```text
PENDING
   |
   v
PROCESSING
   |
   +---- SMTP/provider accepts -------> SUBMITTED
   |
   +---- Known transient error -------> RETRY_WAIT
   |
   +---- Known permanent error -------> FAILED
   |
   +---- Ambiguous outcome -----------> UNKNOWN

RETRY_WAIT
   |
   | at next_attempt_at
   v
PROCESSING

UNKNOWN
   |
   +---- Provider confirms receipt ---> SUBMITTED
   |
   +---- Evidence of non-receipt -----> RETRY_WAIT
   |
   +---- Cannot determine ------------> handle per policy
```

Meanings:

| State | Description |
| --- | --- |
| PENDING | Notification recorded, not yet picked up by a worker |
| PROCESSING | A worker holds a temporary processing lease |
| RETRY_WAIT | Retryable error, waiting until the next attempt time |
| SUBMITTED | SMTP/provider accepted the send request per observed outcome |
| FAILED | Permanent error or retry policy exhausted |
| UNKNOWN | Uncertain whether SMTP/provider received the message |

Never name SUBMITTED as DELIVERED solely upon a successful SMTP response. An SMTP server accepting a message does not prove it reached the Inbox; final delivery, bounces, and spam filtering are separate states.

### Why do you need the UNKNOWN state?

Suppose a worker calls SMTP and the connection times out. If the timeout happened before the message was transmitted, retrying is safe. However, if the SMTP server received the full message and the reply was lost in transit, the worker does not know whether the message was accepted.

If the worker automatically retries every timeout, it risks sending duplicates. If it marks permanent failure, the email may be lost. UNKNOWN honestly represents that the system lacks evidence to pick either outcome.

## 10. Claiming notifications so multiple workers do not send concurrently

When running multiple instances, two workers could read the same PENDING notification. An atomic claim mechanism is required.

A common pattern in PostgreSQL is `SELECT ... FOR UPDATE SKIP LOCKED`:

```sql
BEGIN;

SELECT id
FROM mail_notification
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND (next_attempt_at IS NULL
       OR next_attempt_at <= CURRENT_TIMESTAMP)
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 20;

-- Update selected rows to PROCESSING
-- and set lease_until per worker policy.

COMMIT;
```

Workers process only the rows they claimed. `SKIP LOCKED` lets other workers pick up unlocked rows instead of contending on the same notification.

In real implementations, update status and lease inside the transaction, then return the claimed rows. Never hold a database transaction open while waiting on SMTP network I/O.

### What is the purpose of a lease?

If a worker crashes, the PROCESSING state must not remain stuck forever. A lease specifies when temporary ownership expires:

```text
notification N-123
status      = PROCESSING
worker_id   = worker-2
lease_until = 10:05:00Z
```

After the lease expires, the system can consider recovering the work. However, **never assume an expired lease guarantees the email was not sent**. The worker may have sent successfully and crashed before updating the database. In that case, transition to UNKNOWN or apply a reconciliation/retry policy accounting for duplicate risk.

### Do not hold database locks while calling SMTP

SMTP can take several seconds or time out. Holding row locks throughout sending causes:

- Long-running transactions.
- Other workers blocked waiting.
- Database connections occupied.
- Increased deadlocks or lock contention.

Claim and commit first, send outside the transaction, then open a short transaction to record the outcome. Include a lease/claim token so a stale worker cannot overwrite outcomes after ownership has moved on.

## 11. Example email-sending worker in Spring

A worker should separate three steps: claim, send, and record outcome.

### 11.1. Claiming a batch

```java
@Component
public class MailOutboxWorker {

    private final MailNotificationRepository repository;
    private final JavaMailSender mailSender;

    public MailOutboxWorker(
            MailNotificationRepository repository,
            JavaMailSender mailSender
    ) {
        this.repository = repository;
        this.mailSender = mailSender;
    }

    @Scheduled(fixedDelayString = "1000")
    public void processBatch() {
        List<ClaimedNotification> batch =
                repository.claimNextBatch(20);

        for (ClaimedNotification item : batch) {
            processOne(item);
        }
    }
}
```

`claimNextBatch(...)` must perform an atomic claim transaction and return a matching claim token/lease. `@Scheduled` only triggers polling; it does not by itself ensure a notification is processed by only one instance.

### 11.2. Sending and classifying outcomes

```java
private void processOne(ClaimedNotification item) {
    try {
        MimeMessage message = buildMessage(item);
        mailSender.send(message);

        repository.markSubmitted(
                item.notificationId(),
                item.claimToken()
        );
    } catch (MailAuthenticationException ex) {
        repository.markFailed(
                item.notificationId(),
                item.claimToken(),
                "SMTP authentication failed"
        );
    } catch (MailSendException ex) {
        repository.recordSendFailure(
                item.notificationId(),
                item.claimToken(),
                classify(ex)
        );
    } catch (MailException ex) {
        repository.recordSendFailure(
                item.notificationId(),
                item.claimToken(),
                classify(ex)
        );
    }
}
```

This is an illustrative skeleton. `classify(ex)` must rely on identifiable causes and failure stages; never treat every `MailSendException` or `MailException` as safely retryable. When it is unknown whether the SMTP server received the message, record UNKNOWN for policy-based reconciliation.

Do not catch exceptions and ignore them, as the notification may stay stuck in PROCESSING or fail to retry properly. Nor should you record SUBMITTED before calling the sender: if the process crashes before sending, the email is lost while the database claims it was sent.

## 12. Limits of exactly-once when sending over SMTP

This is the most important limitation when designing duplicate prevention.

Consider two operations:

1. Sending the message to the SMTP server.
2. Updating the database to SUBMITTED.

These two operations belong to two separate systems. No shared transaction guarantees both commit or roll back together.

### Failure window producing ambiguous outcomes

```text
Worker                       SMTP server              Database
  |                              |                       |
  |------ DATA / message ------->|                       |
  |                              |                       |
  |<----- 250 accepted ----------|                       |
  |                              |                       |
  X process crash                |                       |
  |                              |                       |
  |                              |                 status still PROCESSING
  |                              |                       |
  |---- restart / retry -------->|                       |
  |                              |                       |
  |                    May receive duplicate email       |
```

If the process crashes after SMTP accepts the message but before the database records SUBMITTED, the next run may send again. The database only knows the final update did not occur; it cannot deduce on its own that SMTP already received the message.

### Why not mark SENT before sending?

If you write the sent status beforehand:

```text
Database: status = SUBMITTED
       |
       X process crash before SMTP
       |
       v
No email sent,
but system stops retrying
```

That merely trades duplicate risk for email-loss risk. No simple ordering solves atomicity between a database and SMTP.

### Accurately stating the guarantee

With plain SMTP, a system can typically achieve:

- **Exactly-once acceptance in the database:** one logical request creates only one notification record.
- **At-least-once processing:** workers may reprocess a notification upon failures.
- **Best-effort duplicate reduction:** lowering duplicate risk via states, claims, stable IDs, and reconciliation.

Never promise **exactly-once delivery** unless the provider/transport explicitly supports idempotency or a deduplication mechanism with a clear contract.

## 13. When a provider offers an idempotency API

Some email providers expose HTTP APIs that support idempotency keys under their own contracts. If supported by your provider:

1. Generate a stable provider key for the notification.
2. Resend the same key when retrying the same notification.
3. Never generate a fresh key per attempt.
4. Read provider policies on key retention window, uniqueness scope, and payload mismatches.
5. Persist the provider message ID and response.

Conceptual example:

```http
POST /provider/messages
Idempotency-Key: notification-7f6b...
Content-Type: application/json

{
  "to": ["customer@example.net"],
  "subject": "Your invoice",
  "html": "<p>...</p>"
}
```

This is a protocol illustration, not a universal endpoint across providers. Follow the official API documentation of your chosen provider.

### JavaMailSender and provider APIs are not the same

`JavaMailSender` usually sends over SMTP. Standard SMTP has no universal idempotency header equivalent to HTTP provider APIs. If provider-level deduplication is required, you may need to use the provider's official API instead of SMTP, or accept SMTP's limitations.

Never add an arbitrary `Idempotency-Key` header to a MIME message expecting every SMTP server to deduplicate automatically. A server honors such a header only if the provider explicitly documents that behavior.

## 14. Does Message-ID prevent duplicate sends?

No. `Message-ID` is an email message identifier under email standards. It is useful for tracing, references, and certain threading mechanisms, but it is not an idempotency key that all SMTP servers or mailboxes are required to use for deduplication.

Example:

```java
message.setHeader(
        "Message-ID",
        "<notification-123@mail.example.org>"
);
```

If sent twice with the same `Message-ID`, servers or clients may still accept and display both messages. Some systems might fold or handle them differently, but applications must never rely on that unguaranteed behavior.

A stable `Message-ID` aids correlation during investigations; **database idempotency and provider idempotency** are the intentional mechanisms that prevent duplicate processing.

## 15. Classifying errors before retrying

Not every mail-sending failure can be retried safely.

| Error type | Examples | Handling |
| --- | --- | --- |
| Error before connecting/transmitting | DNS lookup failure, socket open failure | Usually retryable with backoff |
| Explicit SMTP rejection before receiving message | Authentication failure, rejected sender/recipient | Fix configuration or data; do not retry continuously |
| Explicit temporary SMTP response | Certain 4xx responses | Retry per policy and backoff |
| Successful SMTP response | Server returns acceptance response | Record SUBMITTED; track delivery separately |
| Connection lost after sending body, before final reply | Timeout after DATA | Ambiguous outcome; UNKNOWN and reconcile |
| Database error after SMTP accepted | Failed to record SUBMITTED status | Reconcile; do not assume unsent |
| Template/model error | Missing required variable, missing template | Fix data/template; do not retry SMTP |
| Invalid recipient | Syntax error or permanent rejection | Fix data or mark terminal error |

Spring's `MailException` is a broad wrapper hierarchy; not every subclass tells you with certainty whether the server accepted the message. Classification should rely on whatever transport/provider details are available.

### Exponential backoff

For known transient errors, gradually increase the interval between retries:

```text
attempt 1: wait 10 seconds
attempt 2: wait 30 seconds
attempt 3: wait 2 minutes
attempt 4: wait 10 minutes
attempt 5: wait 30 minutes
```

This is only an example retry schedule; real systems must cap attempts, add jitter to prevent workers from retrying in lockstep, and respect SMTP/provider guidelines.

Never retry infinitely. Once attempts exceed the cap, move the notification to FAILED or a dead-letter/review queue per business rules. For UNKNOWN, policy must weigh duplicate risk and provider status lookup capabilities.

## 16. Handling UNKNOWN state and reconciliation

When a worker is uncertain whether a message was accepted, several options exist:

### Option 1 — Query the provider

If the provider offers an API or event log searchable by notification ID or provider message ID, use that data to verify whether the message was accepted/delivered.

### Option 2 — Provider webhooks/events

Some email services emit webhooks for accepted, delivered, bounced, or deferred states. Store provider events by notification ID and update state. Webhooks can also be redelivered, so webhook endpoints must themselves be idempotent.

### Option 3 — Route to a reconciliation queue

If automated verification is impossible, keep UNKNOWN, log attempt metadata, and route to a separate workflow. Depending on criticality, you can:

- Wait for additional provider events.
- Let operations inspect history.
- Retry after a delay with an explicit warning of duplicate risk.
- Avoid automatic retries if the email is legally sensitive or high-impact.

Never delete an UNKNOWN notification or flip it to FAILED just so a worker picks it up again. State must accurately reflect the system's level of certainty.

## 17. Idempotency at the API endpoint

Example controller:

```java
@RestController
@RequestMapping("/api/orders")
public class InvoiceMailController {

    private final InvoiceMailRequestService requestService;

    public InvoiceMailController(
            InvoiceMailRequestService requestService
    ) {
        this.requestService = requestService;
    }

    @PostMapping("/{orderId}/send-invoice")
    public ResponseEntity<NotificationReceipt> sendInvoice(
            @PathVariable UUID orderId,
            @RequestHeader("Idempotency-Key") String key,
            @AuthenticationPrincipal AppUser user
    ) {
        NotificationReceipt receipt =
                requestService.requestInvoice(
                        user.tenantId(),
                        user.id(),
                        orderId,
                        key
                );

        return ResponseEntity.accepted().body(receipt);
    }
}
```

The controller merely reads the key and delegates to the service. The service must:

- Verify the user is authorized to request sending the invoice for the order.
- Validate key format and length.
- Compute the request hash from the canonicalized operation.
- Claim the key in the database using a unique constraint.
- Create the notification/outbox record in the same transaction.
- Return the same notification ID when receiving the same request again.

Never let clients pass an arbitrary notification ID and trust that the request was already processed. IDs and status must come from authoritative stored records.

### HTTP responses for duplicate requests

A possible convention:

| Scenario | Suggested response |
| --- | --- |
| New key, valid request, notification recorded | 202 Accepted with notification ID |
| Same key, same payload, operation pending/processing | Return notification ID and current status |
| Same key, same payload, already processed | Return stored result |
| Same key with different payload | 409 Conflict |
| Missing key on endpoint requiring idempotency | 400 Bad Request |
| User lacks permission on order/recipient | 403 or 404 per policy |

Exact HTTP status codes depend on your API contract. What matters is that retried requests never create a new notification and clients can tell the recorded state.

## 18. Idempotency keys on the client

The client must generate the key **once per operation** and reuse it across retries:

```javascript
const idempotencyKey = crypto.randomUUID();

async function submitInvoiceRequest(orderId) {
  return fetch("/api/orders/" + orderId + "/send-invoice", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey
    }
  });
}
```

This is a client-side JavaScript example. If the request times out, invoke `submitInvoiceRequest` again with the **same `idempotencyKey`**. When the user initiates an intentional new resend action, generate a new key for the new operation.

Never generate the key inside a retry function itself:

```javascript
// Unsuitable: generates a new key on every retry.
async function retrySend(orderId) {
  const key = crypto.randomUUID();
  // send request with new key
}
```

If a fresh key is generated on every attempt, the server has no way to recognize the requests as the same operation.

## 19. Distinguishing idempotency keys from business event keys

Consider two scenarios:

**Scenario A:** a user invokes the endpoint twice due to a timeout. Both requests share the same `Idempotency-Key`. This is the same client operation.

**Scenario B:** two consumers receive the same `InvoiceIssued` event due to message broker redelivery. Each consumer might generate a different request key or involve no HTTP request at all. Here a stable business event key is needed.

A business key might look like:

```text
INVOICE_READY:order-123:invoice-version-1
```

Database unique constraint:

```sql
CREATE UNIQUE INDEX uq_invoice_notification_event
ON mail_notification (notification_type, business_event_id);
```

If two consumers attempt to create a notification for the same event, only one insert succeeds. The other reads the existing notification and does not create a duplicate.

### Should you use both?

In systems with both HTTP commands and event-driven workflows, it is usually good to have:

- Request idempotency keys for retried client requests.
- Business event keys for notifications triggered by business events.
- Notification IDs for worker retries.

Each key has its own scope. Do not use one arbitrary UUID to replace all three identifiers.

## 20. Synchronous vs. asynchronous sending

### Synchronous sending inside an HTTP request

Flow:

```text
HTTP request
   |
   v
Idempotency check
   |
   v
Build MimeMessage
   |
   v
JavaMailSender.send
   |
   v
HTTP response
```

Advantages are simple code and direct send feedback to the caller. Drawbacks:

- The request holds a connection while SMTP processes.
- Client/gateway timeouts can occur even when SMTP accepted the message.
- HTTP-layer retries easily cause duplicates without durable idempotency records.
- Hard to handle queues, retries, rate limits, and transient errors.

If still sending synchronously, record the operation and state durably before calling SMTP, use a stable key, and handle ambiguous outcomes. Never rely solely on an in-memory flag.

### Asynchronous sending with an outbox

Flow:

```text
HTTP request
   |
   v
Idempotency + transaction
   |
   +-- business update
   +-- notification PENDING
   +-- outbox event
   |
   v
HTTP 202 + notificationId

Worker
   |
   v
Claim notification
   |
   v
JavaMailSender.send
   |
   v
Record SUBMITTED / RETRY_WAIT / FAILED / UNKNOWN
```

Advantages:

- HTTP requests do not wait on SMTP.
- Retries follow policy.
- States exist for observability.
- Sending rate can be throttled.
- Notifications are recorded atomically with the business transaction.

Drawbacks:

- Requires workers, an outbox, and a state machine.
- Must handle concurrency, leases, retries, and dead-letters.
- Still must handle the failure window between SMTP acceptance and database updates.

For business systems requiring reliability, the asynchronous model is usually easier to operate because states and retries are explicitly managed.

## 21. Notes on @Transactional and @Async

Do not assume `@Transactional` and `@Async` automatically provide idempotency:

- `@Transactional` manages only resources participating in the transaction manager; SMTP is outside the database transaction.
- `@Async` merely runs the method on another thread; if a job reruns or multiple instances process concurrently, duplicate risk remains.
- `@Scheduled` can run across multiple instances when scaling out; database claims/locks are required.
- Retry annotations can re-invoke a method; if that method calls SMTP directly without a stable operation ID, it can send duplicates.

Unsafe example:

```java
@Async
@Retryable
public void sendInvoice(String recipient) {
    mailSender.send(buildMessage(recipient));
}
```

This snippet does not identify which calls represent the same operation, persists no durable state, and does not handle ambiguous outcomes. When using a retry framework, retry a notification with a stable ID and persist attempts/status in the database.

### Transactional event listeners do not replace an outbox

`@TransactionalEventListener(AFTER_COMMIT)` ensures events are handled only after the transaction commits. However, if the process crashes after commit and before the listener executes, the in-memory event is lost. When notifications must not be lost, write an outbox row in the same transaction and let workers read from the database.

## 22. Managing intentional resends

A duplicate-prevention system still needs a "Resend email" feature when a user genuinely requests it.

Distinguish clearly:

- **Retry:** reattempting the same notification due to a transient error or uncertain outcome.
- **Resend:** creating a new business operation requested by a user or staff member.

Example data model:

```text
notification_id: N-100
business_event_id: INVOICE_READY:order-123
status: SUBMITTED

resend_request_id: R-201
resend_of_notification_id: N-100
status: PENDING
```

A resend can link back to the original notification while having its own ID and audit record. When business policy permits resending, this action explicitly creates a new notification. It must never reuse the old request's idempotency key.

### Do not resend automatically just because a user did not see the email

A recipient may not see an email because:

- It landed in spam or quarantine.
- A mailbox rule moved it to another folder.
- The provider delivered it, yet the client has not synced.
- The email address was wrong or changed.
- The email bounced after SMTP acceptance.

Before creating a resend, display known status and consider checking provider events. An intentional resend can still create a duplicate email on the recipient's side; the UI should make that clear.

## 23. Retention of idempotency records

Do not delete idempotency records immediately after sending. Clients may retry late because a gateway, queue, or user never received the response.

Retention duration depends on:

- Client/API gateway retry windows.
- Queue and dead-letter queue lifetimes.
- Operational replay windows.
- Audit retention requirements.
- Privacy/data retention policies.

Deleting keys too early causes late retries to be treated as brand-new operations. Keeping them forever can cause unbounded table growth and retain unnecessary data.

Guidelines:

1. Retain keys at least longer than the valid retry window.
2. Retain business event uniqueness for as long as duplicate notifications must be prevented.
3. Sensitive payloads can be purged earlier while keeping minimal idempotency tombstones/metadata.
4. Never delete records in PROCESSING, RETRY_WAIT, or UNKNOWN states.
5. Once retention expires, explicitly decide whether old requests are permitted to create new operations.

## 24. Security and privacy

Idempotency keys are not authentication secrets. Holding a key does not grant permission to view status or send email on behalf of someone else.

The application must still:

- Authenticate the caller.
- Check authorization on the order/customer/recipient.
- Scope keys by tenant and operation.
- Validate key length and character set.
- Avoid logging full email payloads containing PII.
- Never place access tokens or reset tokens in idempotency keys.
- Rate-limit notification creation to prevent abuse.
- Control who is allowed to trigger resends.
- Keep minimal audit metadata sufficient for investigation.

When storing keys in the database, you can store a hash of the key rather than the raw value depending on your threat model—provided lookups stay efficient and uniqueness is not weakened.

## 25. Observability and operations

To know whether the system is sending duplicates, monitor these metrics and logs:

| Metric/field | Meaning |
| --- | --- |
| `idempotency_replay_count` | Number of requests recognized as retries |
| `idempotency_conflict_count` | Number of times a key was reused with a different payload |
| `notification_created_count` | Number of new notifications created |
| `notification_submitted_count` | Number of messages accepted by SMTP/provider |
| `notification_retry_count` | Number of retries |
| `notification_unknown_count` | Number of uncertain send outcomes |
| `notification_failed_count` | Number of terminal notification failures |
| `outbox_lag` | Delay between creation and worker processing |
| `provider_message_id` | Provider identifier for lookups |

Useful log fields:

```text
notificationId=N-123
businessEventId=INVOICE_READY:order-123
attempt=2
status=UNKNOWN
providerMessageId=...
```

Never log entire email bodies, tokens, or payment info just to debug. Use notification IDs to correlate logs across APIs, workers, and providers.

### Distinguishing request replays from actual resends

When a client retries, `idempotency_replay_count` increases without `notification_created_count` increasing correspondingly. That is the desired behavior. If notification counts climb every time the same operation is retried, your keys or unique constraints are not working properly.

## 26. Testing idempotency

Tests must focus on repetition and concurrency scenarios, not just a single successful send.

### Test 1 — Same key, same payload

Send the same request twice:

```text
Request A: key K, payload P
Request B: key K, payload P
```

Expected:

- Only one idempotency record exists.
- Only one notification exists.
- Both responses reference the same notification ID.
- Workers see only one logical notification.

### Test 2 — Same key, different payload

```text
Request A: key K, recipient A
Request B: key K, recipient B
```

Expected:

- The second request receives a conflict error.
- No notification is created for recipient B.
- The previously recorded request is unchanged.

### Test 3 — Two concurrent requests

Fire multiple concurrent requests with the same scope/key/payload.

Expected:

- The database unique constraint allows only one claim to succeed.
- The other requests receive the same notification.
- Only one outbox event exists for the business key.

### Test 4 — Two different keys for the same business event

```text
Request A: key K1, business event E
Request B: key K2, business event E
```

If policy allows one notification per business event, the business-key unique constraint must block the second notification. If business rules allow resends, requests must go through the dedicated resend operation.

### Test 5 — Worker crashes before sending

Claim a notification and terminate the process before calling SMTP.

Expected:

- Lease expiration is detected.
- The notification is recovered per policy.
- No new notification ID is created.

### Test 6 — Worker crashes after SMTP accepts

Simulate SMTP accepting the message while the process crashes before recording SUBMITTED.

Expected:

- The system does not assume the email was definitely not sent.
- The notification can transition to UNKNOWN.
- Reconciliation or duplicate-risk policy is applied.

### Test 7 — Temporary and permanent SMTP rejections

Expected:

- Transient errors are retried with bounds.
- Permanent errors are not retried infinitely.
- Every attempt is recorded.

### Test 8 — Intentional resend request

Send the same invoice again via a new resend operation.

Expected:

- A new notification is created per policy.
- It links to the original notification.
- Audit records who requested the resend and when.

## 27. End-to-end business flow example

Suppose a user clicks "Email invoice" on an order details page.

### Step 1 — Client generates key

The client generates a UUID for the operation and retains it across all retries of that request.

### Step 2 — API checks key

The controller receives `Idempotency-Key`, authenticates the user, and calls the service. The service computes the request hash and claims the key in the database.

### Step 3 — Record notification/outbox

In the same transaction:

- Save the idempotency record.
- Create the PENDING notification.
- Write the outbox event.
- Commit.

If the request is retried with the same key and payload, the server returns the same notification ID.

### Step 4 — Worker claims notification

The worker uses a row lock/lease to claim one notification. Multiple workers must never claim the same in-flight row.

### Step 5 — Render and send

The worker loads the mail model, renders templates, creates `MimeMessage`, configures `MimeMessageHelper`, and calls `JavaMailSender.send(...)`.

### Step 6 — Record outcome

- Explicit SMTP acceptance: record SUBMITTED.
- Known transient error: record RETRY_WAIT.
- Permanent error: record FAILED.
- Ambiguous outcome: record UNKNOWN and reconcile.

### Step 7 — Client polls status

The client can query a status endpoint using the server-issued notification ID after authorization checks. There is no need to resend the action request just to ask whether the email was sent.

```text
Client
  |
  | POST + Idempotency-Key
  v
API / Idempotency service
  |
  | unique key + request hash
  v
Database transaction
  |-- business update
  |-- notification PENDING
  |-- outbox row
  v
Worker claim
  |
  v
Render template
  |
  v
JavaMailSender / SMTP
  |
  v
Record SUBMITTED / RETRY_WAIT / FAILED / UNKNOWN
  |
  v
Status endpoint
```

## 28. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Generating a new UUID on every HTTP retry | Server treats each retry as a new operation | Keep the same key per logical operation |
| Storing keys only in memory | State lost on restart or scale-out | Persist durably in database/distributed store |
| SELECT then INSERT without unique constraint | Concurrent requests insert two rows | Unique index and atomic insert/claim |
| Checking idempotency only in the controller | Backend events/workers still create duplicates | Add business keys and notification uniqueness |
| Calling SMTP inside a database transaction | Cannot roll back external side effects | Use an outbox and worker |
| Marking submitted before sending | Email lost on process crash | Record only after acceptance response |
| Retrying every exception | May duplicate on ambiguous outcomes | Classify errors, use UNKNOWN and reconciliation |
| Treating timeouts as definitely unsent | Can create duplicates | Check failure stage and provider status |
| Using Message-ID for deduplication | SMTP/mailboxes may still accept duplicates | Enforce idempotency in application/provider |
| Treating outbox as exactly-once delivery | Workers can still resend after crashes | Understand outbox as atomic record + at-least-once |
| Using recipient + subject as key | Blocks legitimate future emails | Use request/business operation IDs |
| Not separating retries from resends | Cannot tell intentional new actions apart | Give resends separate operation IDs and audits |
| Purging keys too early | Late retries create new notifications | Set retention beyond retry/replay windows |
| Worker holding DB locks during SMTP | Prolonged locks, lower throughput | Claim in short transaction, send outside transaction |
| Omitting notification IDs from logs | Hard to investigate duplicates | Correlate API, worker, and provider via stable IDs |

## 29. Quick design reference

| Need | Mechanism to use |
| --- | --- |
| Prevent double-click/HTTP retry duplicates | Idempotency key + request hash |
| Prevent two backend listeners creating the same email | Business event key + unique constraint |
| Record send requests atomically with business changes | Transactional outbox |
| Prevent two workers processing the same row | Atomic claim, row lock/lease |
| Retry the same notification | Stable notification ID + attempt state |
| Prevent provider accepting duplicates | Provider API idempotency if supported |
| Handle timeout after transmission | UNKNOWN + reconciliation/policy |
| Allow intentional user resends | New resend operation linked to original notification |
| Investigate whether provider accepted an email | Provider message ID/events and logs |

## 30. Conclusion

To prevent duplicate sends when an operation is retried, the application must identify the **logical operation** rather than treating every method call or HTTP request as a new email. Idempotency keys identify retried requests; request hashes catch keys reused with different payloads; business keys prevent multiple backend flows from creating the same notification; database unique constraints guard concurrent executions. A transactional outbox records send requests alongside business transactions, while workers manage claims, attempts, and delivery states.

In Spring Framework Mail, `JavaMailSender` only performs transport delivery. It does not prevent duplicates on its own. Nor does SMTP guarantee exactly-once delivery when a process loses connectivity after the server may have received the message. Therefore, distinguish SUBMITTED, FAILED, and UNKNOWN, use provider idempotency when available, and reconcile ambiguous outcomes. Intentional resends require a new operation and separate audit trail. This design prevents retried requests from spawning unintended notifications while staying honest about the limits of external email delivery.
