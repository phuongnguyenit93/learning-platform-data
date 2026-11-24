# Retries at the Client, Queue Worker, or Provider

In a Spring Framework Mail application, emails may be sent directly from a request, via a job queue, or through an external email service. At every layer, transient failures can occur: HTTP request timeouts, worker restarts, SMTP `4xx` responses, provider rate limits, or a recipient's mail server temporarily deferring mail.

A common reflex is "if it fails, retry." Yet if **the client, queue worker, and provider all retry without clear ownership**, one business notification can produce multiple identical emails. Conversely, if the application gives up on any exception, critical emails can be lost even when an outage lasted only a few seconds.

This lesson explains **retries at the client, queue worker, or provider** in the context of Spring Mail; how to distinguish a send request from a send attempt and from the SMTP provider's delivery process; and how to use idempotency keys, a transactional outbox, backoff, the `UNKNOWN` state, and webhooks to increase reliability without uncontrolled duplicate sends.

## 1. First, Distinguish the Three Retry Layers

Suppose a user clicks "Send Invoice" in a web application:

```text
Browser / HTTP client
        |
        | POST /orders/123/send-receipt
        v
Spring Boot backend
        |
        | Write email_outbox
        v
Database / queue
        |
        | Worker claims job
        v
Spring Mail / JavaMailSender
        |
        | SMTP submission
        v
SMTP relay / Email provider
        |
        | Delivery retry if destination server temporarily defers
        v
Recipient mail server
        |
        v
Inbox / spam / quarantine
```

Here there are **three distinct places that can retry**:

| Layer | Operation being retried | Who controls it? | Goal |
|---|---|---|---|
| **Client** | Re-calling the HTTP API to request a send | Browser, mobile app, calling service | Ensure the business request is recorded. |
| **Queue worker** | Retrying delivery of an already recorded job | Application and queue/outbox worker | Ensure the job is processed and submitted to SMTP/provider. |
| **Provider** | Retrying delivery of an accepted email to the destination server | SMTP relay/MTA/email provider | Overcome transient errors during delivery. |

All three use the word "retry," yet they act on **different things**:

- The client retries **the request to create a send job**.
- The worker retries **a send attempt** belonging to an existing request.
- The provider retries **delivery** of a message the provider has already accepted.

**Principle:** identify which layer has already taken responsibility before deciding whether an upstream layer needs another retry.

## 2. Three Key Milestones: Not Created, Queued for Processing, Accepted by SMTP

Separate these milestones clearly:

1. **Business request persisted:** the API successfully created an outbox record.
2. **Submission accepted by SMTP/provider:** the sending system received an acceptance reply from upstream.
3. **Delivery confirmed per provider:** the provider or MTA signals that the destination mail server accepted the message.

These three milestones are not equivalent.

```text
POST /send-receipt
   |
   | 202 Accepted: outbox saved
   v
Email worker
   |
   | SMTP 250 / successful submission
   v
Provider accepted
   |
   | Provider retries delivery if needed
   v
Destination mail server
   |
   | Delivery event, if provider supports
   v
Application receives event
```

An HTTP `202 Accepted` may only mean the API persisted a job for processing, not that SMTP has sent anything. A successful `JavaMailSender.send(...)` call usually indicates SMTP submission completed without a synchronous error; it **does not prove the email reached the Inbox or was read**.

Choosing to retry must depend on **which milestone is definitely complete** and **which milestone has an unknown outcome**.

## 3. One Logical Email, Many Attempts, Without Duplicate Jobs

One way to model this:

- `businessEventId`: the business event, such as an order being paid.
- `messageKey`: one logical email that must be sent due to that event.
- `attemptId`: one worker invocation of SMTP/provider.
- `providerMessageId`: the ID returned/supplied by the provider, if any.
- `deliveryEventId`: the ID of a webhook event.

Example:

```text
business_event = order-123-paid
  |
  +-- message_key = msg-a817
        |
        +-- attempt_id = att-1 -> temporary SMTP failure
        +-- attempt_id = att-2 -> SMTP_ACCEPTED
                                |
                                +-- provider delivery attempt #1 -> deferred
                                +-- provider delivery attempt #2 -> delivered
```

When a client resends the same request due to flaky networking, it **should not automatically create another message key**. When a worker retries after a transient error, it **keeps the message key and creates a new attempt ID**. When a provider retries delivery after accepting the email, **the backend does not need to create another email**.

A fresh resend request intentionally triggered by a user at another time may create a new message key according to business rules. Clearly define how an "old retry" differs from a "new send."

## 4. Client Retries: An HTTP Timeout Does Not Mean the Server Did Nothing

Suppose a mobile app sends:

```http
POST /api/orders/123/send-receipt HTTP/1.1
Content-Type: application/json

{"language":"vi","destination":"verified-primary"}
```

The server may have already committed the outbox row and returned `202`, while the response was lost on the network. The client only sees a timeout.

If the client resends the request, the server could create two outbox rows and send two emails unless deduplication is in place.

### 4.1. Using Idempotency-Key for Send-Request APIs

The client generates a stable key for **one action** and sends it along:

```http
POST /api/orders/123/send-receipt HTTP/1.1
Idempotency-Key: 79dd3864-6018-4d85-8e65-1f865c7d42d3
Content-Type: application/json

{"language":"vi","destination":"verified-primary"}
```

If the request times out, the client retries with **the same key and the same payload**, without generating a new key.

Backend behavior:
- First request: creates one outbox row, returns the message key.
- Duplicate request: returns the result of the original request without creating a new job.
- Same key with a different payload: rejects, typically with a conflict error, instead of silently reusing the old job or creating a second one.

Example API response:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "messageKey": "msg-a817",
  "status": "QUEUED"
}
```

This response states that the request was accepted for processing, **not yet that the email was delivered**.

### 4.2. Scope of the Idempotency Key

Do not enforce a system-wide unique constraint on a client-supplied string without context. One design is uniqueness scoped by:

```text
tenant_id + actor_id + operation + idempotency_key
```

For example, `operation=send-order-receipt`. If another actor or another API uses the same key, they should not accidentally receive someone else's result.

Also store a **request fingerprint** derived from canonicalized, business-meaningful fields to detect the same key sent with non-equivalent data. Do not store sensitive tokens or arbitrary full request bodies if unnecessary.

A client-generated key is not an authorization mechanism. The backend must still verify the caller is authorized to request sending that order's email to the intended recipient.

### 4.3. Unique Constraints Must Protect Against Concurrent Requests

The "SELECT first, INSERT if absent" pattern fails when two requests arrive simultaneously; both may see no existing row.

You need a unique constraint and contention-safe insert:

```sql
CREATE TABLE email_request_dedupe (
    tenant_id         VARCHAR(64) NOT NULL,
    actor_id          VARCHAR(64) NOT NULL,
    operation         VARCHAR(80) NOT NULL,
    idempotency_key   VARCHAR(120) NOT NULL,
    request_hash      VARCHAR(64) NOT NULL,
    message_key       VARCHAR(64) NOT NULL,
    created_at        TIMESTAMP NOT NULL,
    PRIMARY KEY (
        tenant_id, actor_id, operation, idempotency_key
    )
);
```

Inside a transaction, insert the dedupe record together with the outbox; upon conflict, fetch the existing record and compare the fingerprint. Handle unique violations or use appropriate database upsert syntax rather than relying solely on application-layer checks.

### 4.4. When Should the Client Retry?

| HTTP outcome | Recommended behavior |
|---|---|
| `202` or success response with message key | Do not create a new request; poll/track status if needed. |
| Timeout/network drop before knowing response | May retry with **the same `Idempotency-Key`**, bounded attempts. |
| `429 Too Many Requests` | Honor `Retry-After` if present and service quotas. |
| `503 Service Unavailable` | Retry with backoff if the API supports idempotency. |
| `400` due to invalid request | Fix the request; do not loop indefinitely. |
| `401/403` | Handle authentication/authorization; do not treat as a temporary SMTP issue. |
| `409` due to reused key with different payload | Do not retry as-is; fix the client flow. |

HTTP retries should be bounded, use backoff/jitter, and never turn a "Send" action into an unbounded loop. Double-click prevention in the UI improves UX, **but does not replace server-side idempotency**.

## 5. Queue Worker Retries: Only Resend Existing Jobs

Once the outbox commits, a worker takes responsibility for sending. Errors can occur during rendering, MIME construction, SMTP connection, or persisting the send outcome.

Lifecycle example:

```text
PENDING
   |
   v
LEASED / SENDING
   |
   +--> SMTP_ACCEPTED
   |
   +--> RETRY_WAIT ----> LEASED / SENDING
   |
   +--> FAILED_PERMANENT
   |
   +--> UNKNOWN ----> reconciliation / manual decision
```

These state names are illustrative, yet you must distinguish:
- not yet processed;
- currently owned by a worker;
- eligible for retry;
- error definitely unresolvable by retrying the same request;
- uncertain outcome;
- accepted by SMTP.

### 5.1. Outbox Transaction

For critical emails, persist the business event and outbox row in the same transaction:

```text
BEGIN
  update order status = PAID
  insert email_outbox(
      message_key,
      business_event_key,
      template,
      status = PENDING
  )
COMMIT
```

This prevents scenarios where an order is paid but the process dies before recording the need to send an email.

A business constraint like `(business_event_key, template, recipient_role)` can prevent creating two logical emails for the same event, though actual uniqueness rules must account for intentional product resends.

### 5.2. Claiming Jobs With Locks or Leases

Two workers must never pick up the same job simultaneously and send it twice. In PostgreSQL, one strategy uses `FOR UPDATE SKIP LOCKED` in a short transaction:

```sql
WITH next_job AS (
    SELECT message_key
    FROM email_outbox
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND next_attempt_at <= CURRENT_TIMESTAMP
    ORDER BY next_attempt_at, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE email_outbox e
SET status = 'LEASED',
    lease_token = :newLeaseToken,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    updated_at = CURRENT_TIMESTAMP
FROM next_job n
WHERE e.message_key = n.message_key
RETURNING e.*;
```

The worker commits the claim transaction before calling SMTP; never hold an open database transaction across network I/O. For queue systems with visibility timeouts, apply the queue's corresponding claim/ack mechanisms.

The lease token serves as a fencing marker: when the worker writes the outcome, use a compare-and-set on the token to stop a stale worker from overwriting a job already claimed by a newer worker:

```sql
UPDATE email_outbox
SET status = :newStatus,
    lease_token = NULL,
    lease_until = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE message_key = :messageKey
  AND lease_token = :leaseToken
  AND status = 'LEASED';
```

If zero rows are updated, the worker must handle the possibility that ownership expired. Fencing protects **database state**, yet it cannot recall an email already accepted by SMTP. If a lease expires while a network call is still in flight, a new worker may send a duplicate; therefore, configure timeouts, suitable lease durations, heartbeats/renewals when needed, and `UNKNOWN` handling.

### 5.3. Acknowledging Queues at the Right Time

With external queues outside the database, avoid:
- Acking before the outbox/result is durably saved and then crashing: loses the job.
- Failing to ack after determining the outcome without a dedupe strategy: redelivers the job.
- Requeueing unboundedly when the error is bad data or templates.

A sound rule is **ack only after durably persisting the processing decision**: success, retry schedule, permanent failure, or uncertain state for reconciliation. Exact mechanics depend on the broker; the outbox/database should remain the reliable source of state.

### 5.4. Do Not Reuse the Same MimeMessage Object Forever

Each attempt should create a fresh `MimeMessage`/`MimeMessageHelper` and render content from controlled data or snapshots. Never share these mutable objects across worker threads.

If content is re-rendered on retry, consider:
- Should it preserve the exact amounts/timestamps from the event time, or read current values?
- Are tokenized links still valid?
- Could the template version have changed between attempts?
- Do attachments still match the approved content?

For legally or financially significant emails, usually store immutable references/versions or snapshots so retries do not alter business content unintentionally.

## 6. SMTP Submission Layer Retries: Understand the Error Before Retrying

When using Spring Mail, the send point is typically:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo(recipient);
helper.setSubject(subject);
helper.setText(plainText, htmlText);

mailSender.send(message);
```

`send(...)` can throw `MailException`, while `MimeMessage` construction can throw `MessagingException`. Do not retry every exception under one blanket rule.

### 6.1. SMTP 4xx and 5xx

SMTP responses generally fall into two categories:

| Reply | Common meaning | Handling approach |
|---|---|---|
| `421` | SMTP service unavailable, closing connection | May retry after backoff if known message was not accepted. |
| `450` | Mailbox temporarily unavailable | Controlled retry at the appropriate layer. |
| `451` | Temporary server error | Retry with backoff. |
| `452` | Temporary resource shortage | Retry after waiting; avoid burst retries. |
| `550` | Mailbox/recipient permanently rejected in typical contexts | Do not resend the same request indefinitely; inspect cause. |
| `552` | Storage/size limit exceeded per server reply | Inspect extended code and description; usually must change content/policy. |
| `554` | Transaction rejected | Usually pointless to repeat the exact request; diagnose. |

This is guidance, **not enough to decide every case automatically**. Check which SMTP command failed (`MAIL FROM`, `RCPT TO`, `DATA`, post-DATA), enhanced status codes like `4.x.x`/`5.x.x`, relay messages, and provider policies. A `4xx` code indicates a temporary error, not that immediate retry is appropriate; quota errors may require longer waits.

### 6.2. Spring Mail Exceptions

Relevant exceptions:

| Exception | Scenario | Auto-retry? |
|---|---|---|
| `MailAuthenticationException` | SMTP authentication failed | Usually requires fixing credentials/config; avoid rapid retries. |
| `MailPreparationException` | Error preparing message | Usually must fix data/template/attachment. |
| `MailParseException` | Failed to parse/construct email | Do not retry the same input until fixed. |
| `MailSendException` | One or more messages failed to send | Inspect cause, messages, and per-recipient states. |
| Other `MailException` | Mail abstraction layer error | Classify by specific cause; do not assume transient. |

Do not rely solely on exception class names to conclude SMTP definitely did not receive the message. For example, a connection drop or timeout **after the server received `DATA`** can leave the application unaware of whether the server accepted the message.

### 6.3. Timeouts and the UNKNOWN State

Suppose:

```text
Worker                     SMTP relay
  |---- DATA + content -------->|
  |---- end-of-DATA ----------->|
  |                              | accept and enqueue
  |<--- connection lost ---------X
  |
  +-- exception / timeout
```

The worker may think it failed; the SMTP relay may have accepted the message. Retrying the entire email immediately can send two copies to the recipient.

For uncertain cases:
1. Save `attemptId` and `messageKey`.
2. Record `UNKNOWN` rather than declaring definitive `FAILED`.
3. Look up provider/SMTP logs if possible.
4. Wait for events or run time-bounded reconciliation.
5. Only retry when policy accepts duplicate risk or non-acceptance is verified.

There is no general way to achieve exactly-once delivery with `JavaMailSender` and generic SMTP alone. Application keys or custom MIME headers do not make SMTP automatically deduplicate.

### 6.4. Multiple Recipients and Partial Success

An email with multiple `To`/`Cc`/`Bcc` addresses can yield complex outcomes:
- some recipients accepted;
- other recipients rejected;
- provider performs partial sends depending on configuration;
- an exception does not necessarily mean all recipients missed the message.

For bulk sending, consider **one logical email per recipient** or at minimum record per-recipient results. Never blindly retry the whole list after a partial failure, as you may resend to those already accepted.

With `MailSendException`, you can inspect failed messages/exceptions exposed by Spring when applicable; details on successful recipients still depend on Jakarta Mail/provider behavior and `sendpartial` settings. Test against your actual relay.

## 7. Provider Retries: Submission Differs From Delivery

Once an SMTP relay or email provider replies accepting submission, it usually takes responsibility for forwarding the email. If the destination mail server returns a temporary error, the MTA/provider can re-queue the message to retry delivery later.

```text
Application --SMTP accepted--> Provider queue
                                 |
                                 +--> delivery attempt #1: 451
                                 |
                                 +--> wait according to provider policy
                                 |
                                 +--> delivery attempt #2: accepted
                                 |
                                 +--> delivered event (if supported)
```

Meanwhile, the backend **must not create a new email submission merely because the provider reported `deferred`**. The provider already holds the message and is retrying delivery per its own policy. Resubmitting can cause duplicates if both copies are later delivered.

Common statuses:
- `processed/accepted`: provider accepted it for processing;
- `deferred`: temporarily delayed, usually still queued;
- `delivered`: successfully delivered per provider definition;
- `bounced`: undeliverable, usually the terminal result of a delivery route;
- `dropped/suppressed`: provider skipped sending due to policy/suppression;
- `complaint`: spam feedback signal if supported by the provider.

Exact event names and semantics vary across providers. Generic SMTP neither guarantees webhooks nor provides a built-in API to query delivery status.

### 7.1. When the Provider Reports Deferred

Recommended behavior:
- Record the event linked to the provider message ID and application message key.
- Display accurate status ("delivering" or "deferred"), never "not sent."
- Respect the provider's retry duration and queue retention limits.
- Wait for subsequent events or check the dashboard/API if needed.
- Consider resubmitting only after the provider confirms the message failed/dropped and business policy allows it.

### 7.2. When the Provider Reports Bounced

Classify by outcome:
- Hard bounce / non-existent address: usually do not auto-resend.
- Soft bounce or temporary error after provider retries exhausted: may require a business decision, never an infinite loop.
- Reputation/suppression policy: fix the root problem; repeated sends worsen reputation.
- Mailbox full: depends on policy; alternative contact channels may apply.

Many providers manage their own suppression lists. The application must avoid automatically resending to suppressed or complained recipients.

### 7.3. When Using an HTTP Email API Instead of SMTP

If sending via a provider API (rather than directly through `JavaMailSender`), the provider may support:
- API-level idempotency keys;
- `429` status codes and `Retry-After` headers;
- provider request/message IDs;
- metadata/custom arguments carrying the `messageKey`.

Those are **API/provider-specific capabilities**, not inherent to SMTP. Read the provider contract and rely only on explicitly supported mechanisms. HTTP submission retries must still separate unknown-outcome timeouts from failures confirmed not received by the provider.

## 8. Who Should Own Retries?

A classic design flaw is stacking multiple retry loops on top of each other:

```text
HTTP client retries 3 times
  × Service-level retry 3 times
  × Worker retries 5 times
  × SMTP library retries 2 times
  = potential 90 submissions
```

The multiplication illustrates the risk when every layer can re-trigger the send operation; exact numbers depend on each layer's idempotency and policies.

Instead, assign clear ownership:

| Layer | Retry authority | Stop / handoff point |
|---|---|---|
| Client | Retry API request with the same idempotency key | Once the API confirms job persistence or returns a non-retryable error. |
| API service | Commit outbox/idempotency; never send and infinitely retry inside HTTP request | Once the job is durably stored. |
| Queue worker | Retry SMTP submission when safe and within budget | Upon SMTP accepted, permanent failure, or `UNKNOWN` needing reconciliation. |
| SMTP provider | Retry delivery after acceptance | Per provider queue lifetime/policy. |
| Application delivery-event handler | Update state and decide next business action | Never blindly resubmit deferred messages. |

**Only one layer should actively retry the same side-effecting operation at a time.** Other layers may retry status checks, but should not repeat sending by default.

## 9. Backoff, Jitter, and Retry Budgets

### 9.1. Exponential Backoff

Instead of retrying every 100 ms, use increasing wait intervals, for example:

```text
attempt 1: send immediately
attempt 2: wait ~2 seconds
attempt 3: wait ~4 seconds
attempt 4: wait ~8 seconds
attempt 5: wait ~16 seconds
```

Numbers are illustrative. Balance transaction timing, link expiration, resource limits, and provider policies.

A basic formula:

```text
delay = min(maxDelay, baseDelay × 2^(attemptNumber - 1))
```

If all workers retry at the exact same boundaries, they can cause a **thundering herd**. Add jitter to spread attempts out:

```text
fullJitterDelay = random(0, cappedExponentialDelay)
```

### 9.2. Example Computing Next Retry Timestamp

```java
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ThreadLocalRandom;

public class RetrySchedule {

    private static final long BASE_SECONDS = 2;
    private static final long MAX_SECONDS = 300;

    public Instant nextAttemptAt(int attemptNumber, Instant now) {
        if (attemptNumber < 1) {
            throw new IllegalArgumentException("attemptNumber >= 1");
        }

        int exponent = Math.min(attemptNumber - 1, 20);
        long cap = Math.min(
            MAX_SECONDS,
            BASE_SECONDS * (1L << exponent)
        );

        long delaySeconds =
            ThreadLocalRandom.current().nextLong(cap + 1);

        return now.plus(Duration.ofSeconds(delaySeconds));
    }
}
```

This illustrates full jitter, not a Spring Mail default rule. In production, set a **minimum delay** to avoid 0-second retries during provider rate limiting. If the provider publishes `Retry-After` via API, prioritize that policy where appropriate.

### 9.3. Retry Budgets

Constrain retries across multiple dimensions:
- maximum attempts per message key;
- total elapsed time since outbox creation;
- business deadline, such as verification link expiration;
- concurrent retries per tenant/provider;
- pending job count and queue depth;
- provider-published quotas/rate limits.

Examples:
- Verification emails valid for 15 minutes: do not retry for a day and send an expired link.
- Invoice emails with a long lifetime: can wait longer, yet still need handling once the budget runs out.
- Urgent alerts may fall back to another channel instead of retrying SMTP for hours.

When the retry budget is exceeded, move to `DEAD_LETTER`/`FAILED_PERMANENT` or an investigation workflow rather than silently dropping the job.

### 9.4. Circuit Breakers and Rate Limiting

If an SMTP provider suffers a broad outage, thousands of workers retrying together increase load and may trigger rate limits. Combine:
- queue concurrency limits;
- per-provider/account rate limiters;
- circuit breakers when upstream is unavailable;
- exponential backoff with jitter;
- alerts when queue backlogs or retry rates spike unusually.

A circuit breaker does not replace an outbox; it temporarily blocks likely-to-fail calls and helps the system recover in a controlled manner.

## 10. Idempotency at Every Layer

Idempotency means repeating **the same logical request** causes no extra unintended business effects within the scope of the designed safeguards.

| Layer | Implementation | Limitation |
|---|---|---|
| Client → API | `Idempotency-Key`, scoped by tenant/operation, fingerprint, unique constraint | Only protects job creation, does not guarantee SMTP exactly-once. |
| Business → Outbox | Unique key on business event + notification type | Must define when intentional resends are permitted. |
| Queue → Worker | Atomic claim, lease/fencing, persisted attempts, message key dedupe | Cannot eliminate every duplicate after an uncertain-outcome timeout. |
| Worker → Provider API | Provider idempotency key if supported by API | Effective only per provider contract and TTL. |
| SMTP submission | No universal idempotency via custom headers | Cannot assume the relay automatically deduplicates. |
| Provider webhook → DB | Unique provider event ID; state transition rules | Events may arrive late, duplicated, or out of order. |

### 10.1. Application Message Key Is Not RFC Message-ID

`Message-ID` is a standard email header typically generated by Jakarta Mail/provider. It serves message identity and threading. An application `messageKey` is an internal ID for a logical email across attempts. A retry may build a new MIME message with a different `Message-ID` yet **the same message key**.

You can attach keys in custom headers:

```java
message.setHeader(
    "X-Application-Message-Key",
    messageKey
);

message.setHeader(
    "X-Mail-Attempt-ID",
    attemptId
);
```

These headers aid tracing, **not SMTP duplicate prevention**. Recipients can inspect raw headers, so never embed secrets or personal data.

### 10.2. Never Reuse an Idempotency Key for a New Business Request

If a user intentionally resends an invoice to another address, that may be a new logical email requiring a new key. If a client merely retries a request because it missed the response, keep the old key.

Document this rule in the API contract rather than guessing based on how many seconds elapsed between button clicks.

## 11. Database Design for Transparent Retries

A reference schema:

```sql
CREATE TABLE email_outbox (
    message_key       VARCHAR(64) PRIMARY KEY,
    business_event_id VARCHAR(120) NOT NULL,
    template_name     VARCHAR(120) NOT NULL,
    recipient_ref     VARCHAR(120) NOT NULL,
    status            VARCHAR(32) NOT NULL,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    next_attempt_at   TIMESTAMP NOT NULL,
    lease_token       VARCHAR(64),
    lease_until       TIMESTAMP,
    provider_id       VARCHAR(255),
    created_at        TIMESTAMP NOT NULL,
    updated_at        TIMESTAMP NOT NULL
);

CREATE TABLE email_attempt (
    attempt_id        VARCHAR(64) PRIMARY KEY,
    message_key       VARCHAR(64) NOT NULL,
    attempt_number    INTEGER NOT NULL,
    started_at        TIMESTAMP NOT NULL,
    finished_at       TIMESTAMP,
    outcome           VARCHAR(32) NOT NULL,
    error_category    VARCHAR(64),
    rfc_message_id    VARCHAR(255),
    provider_id       VARCHAR(255),
    CONSTRAINT fk_email_attempt_outbox
        FOREIGN KEY (message_key)
        REFERENCES email_outbox(message_key),
    CONSTRAINT uq_email_attempt_number
        UNIQUE (message_key, attempt_number)
);
```

You can add an `email_delivery_event` table with a unique provider event ID to process webhooks.

Suggested meanings for outbox statuses:
- `PENDING`: awaiting first send.
- `LEASED`: worker currently owns the job.
- `RETRY_WAIT`: waiting for next attempt timestamp.
- `SMTP_ACCEPTED`: upstream accepted submission.
- `DELIVERED`: corresponding delivery event received.
- `FAILED_PERMANENT`: requires data/policy fix or budget exhausted.
- `UNKNOWN`: unclear whether upstream accepted it.
- `DEAD_LETTER`: moved to separate handling.

Relying solely on an aggregate `status` column can obscure vital history; the attempt table captures per-attempt progression to aid investigation and reconciliation.

## 12. Spring Boot Example: API Writes Outbox, Worker Handles Sending

### 12.1. API Does Not Send SMTP Inside the HTTP Request

Illustrative example:

```java
@RestController
@RequestMapping("/api/orders")
public class OrderReceiptController {

    private final ReceiptRequestService receiptService;

    public OrderReceiptController(
            ReceiptRequestService receiptService) {
        this.receiptService = receiptService;
    }

    @PostMapping("/{orderId}/send-receipt")
    public ResponseEntity<ReceiptRequestResult> requestReceipt(
            @PathVariable String orderId,
            @RequestHeader("Idempotency-Key") String key,
            Principal principal) {

        ReceiptRequestResult result = receiptService.requestReceipt(
            principal.getName(),
            orderId,
            key
        );

        return ResponseEntity.accepted().body(result);
    }
}
```

`ReceiptRequestService` is an application-defined service that must:
1. Verify the actor has permission to send the order's receipt.
2. Validate format and scope of `Idempotency-Key`.
3. Within a transaction, write the dedupe record alongside the outbox.
4. Return the same message key for valid duplicate requests.
5. Reject the same key when meaningful content changed.
6. Never call `JavaMailSender` directly inside the business transaction.

Illustrative result:

```java
public record ReceiptRequestResult(
    String messageKey,
    String status
) {}
```

HTTP `202` means the request was accepted for processing; the UI can display "Send request recorded" rather than "Email arrived in inbox."

### 12.2. Worker Sends and Records Attempts

The service can be invoked by a scheduler or queue consumer:

```java
@Service
public class MailSubmissionWorker {

    private final JavaMailSender mailSender;
    private final MailOutboxRepository repository;
    private final MailRetryPolicy retryPolicy;

    public MailSubmissionWorker(
            JavaMailSender mailSender,
            MailOutboxRepository repository,
            MailRetryPolicy retryPolicy) {
        this.mailSender = mailSender;
        this.repository = repository;
        this.retryPolicy = retryPolicy;
    }

    public void process(ClaimedMailJob job) {
        String attemptId = UUID.randomUUID().toString();

        repository.startAttempt(
            job.messageKey(),
            job.leaseToken(),
            attemptId
        );

        try {
            MimeMessage message =
                mailSender.createMimeMessage();

            MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

            helper.setFrom("no-reply@example.com");
            helper.setTo(job.recipient());
            helper.setSubject(job.subject());
            helper.setText(job.plainText(), job.htmlText());

            message.setHeader(
                "X-Application-Message-Key",
                job.messageKey()
            );
            message.setHeader(
                "X-Mail-Attempt-ID",
                attemptId
            );

            mailSender.send(message);

            repository.markAccepted(
                job.messageKey(),
                job.leaseToken(),
                attemptId,
                message.getMessageID()
            );

        } catch (MailException | MessagingException ex) {
            RetryDecision decision = retryPolicy.classify(
                ex,
                job.attemptNumber()
            );

            repository.recordOutcome(
                job.messageKey(),
                job.leaseToken(),
                attemptId,
                decision
            );
        }
    }
}
```

This is an **illustrative skeleton**, not a full implementation:
- `ClaimedMailJob`, `MailOutboxRepository`, `MailRetryPolicy`, and `RetryDecision` are application-defined interfaces/models.
- The repository must perform atomic claim/lease fencing in short transactions.
- `classify(...)` must consider actual technical causes, SMTP codes, and possible `UNKNOWN` outcomes; never retry every `MailException`.
- `markAccepted(...)` represents the **SMTP submission accepted** milestone, not recipient delivery.
- If saving the outcome to the DB fails after sending, the job may need reconciliation; do not immediately resend.
- Subsequent retries must build a fresh MIME message while keeping `messageKey`.
- Job contents must be secured and bound to the right recipient; never log content, tokens, or attachments.

### 12.3. Do Not Mechanically Wrap Every Send Call With @Retryable

Spring Retry/Resilience4j can be used for network calls **known safe to retry**, yet a decorator around `mailSender.send(message)` can obscure:
- attempt IDs;
- unknown SMTP outcomes;
- partial success;
- retry budgets;
- duplicate sends;
- per-attempt outbox state persisted in storage.

If retrying immediately inside a worker, enforce strict rules and ideally persist each attempt/decision to storage. For emails with irreversible side effects, **durable retries via an outbox are usually easier to control than an in-request retry loop**.

## 13. When the Provider Received It, but the Application Thinks It Failed

This is the most important scenario to design for upfront:

```text
T0: Worker starts attempt #1.
T1: Worker finishes sending email data.
T2: SMTP relay writes message to queue.
T3: Connection drops before worker sees response.
T4: Worker observes timeout.
T5: Job is reassigned because lease expired.
T6: Worker attempt #2 sends the same content.
T7: Recipient may receive two emails.
```

The outcome at T4 must be treated as **unknown** unless there is definitive evidence the provider did not receive the message.

A practical strategy:
1. Before sending, persist `messageKey` and `attemptId`.
2. Attach custom headers or appropriate provider metadata.
3. On ambiguous errors, store the `UNKNOWN` state.
4. Reconcile via provider ID, SMTP logs, or webhooks if available.
5. If verification data is unavailable, apply a risk-acceptance policy per email type.
6. If forced to resend, track both attempts under the same `messageKey`.

High-risk emails, such as password resets or transaction confirmations, may require designing tokens/flows so duplicate sends do not trigger unwanted business actions. A one-time-use verification link validated server-side reduces business risk, even though receiving duplicate emails remains a poor user experience.

## 14. Provider Webhooks, Duplicate Events, and Out-of-Order Events

After SMTP acceptance, a provider may deliver webhooks:

```text
accepted -> deferred -> delivered
```

Yet webhooks can:
- be redelivered for the same event if the endpoint timed out;
- arrive late;
- arrive out of order;
- lack metadata depending on the provider;
- contain sensitive recipient data or bounce reasons.

The handler should:
1. Verify webhook signatures or official authentication mechanisms.
2. Deduplicate using the provider event ID or a stable provider-defined key.
3. Map the provider message ID/custom metadata back to `messageKey` and attempt.
4. Store an immutable or append-only event history.
5. Apply state transition rules so a late `deferred` event never "regresses" state after `delivered`.
6. Never use a `deferred` event as a trigger to call `JavaMailSender.send` again.
7. Restrict access to webhook logs and payloads.

Example table:

```sql
CREATE TABLE email_delivery_event (
    provider          VARCHAR(80) NOT NULL,
    provider_event_id VARCHAR(255) NOT NULL,
    message_key       VARCHAR(64) NOT NULL,
    provider_id       VARCHAR(255),
    event_type        VARCHAR(50) NOT NULL,
    event_at          TIMESTAMP,
    received_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (provider, provider_event_id)
);
```

If the provider does not supply a stable event ID, design deduplication per provider documentation and payload properties; never assume a timestamp is unique.

## 15. Scenario-Based Retry Decision Matrix

| Scenario | Client retry? | Worker retry? | Provider retry? | Note |
|---|---|---|---|---|
| Browser timeout on POST creating outbox | Yes, same idempotency key | Per created job | Not involved yet | Do not create two jobs. |
| API returns `202` and message key | Not needed | Performs initial send | Not involved yet | `202` does not mean delivered. |
| Worker crashes before calling SMTP | No | Yes, after lease reclaim | Not involved yet | Ensure no submission happened. |
| SMTP `451` before accepting DATA | No | Yes, with backoff | Not accepted yet | Record transient error, inspect actual response. |
| SMTP AUTH wrong credentials | No | Do not rapid-retry | No | Fix config/secrets. |
| MIME build error from missing template variable | No | Do not retry same input | No | Fix data or template. |
| SMTP timeout after DATA, unclear if relay received | No | `UNKNOWN`, reconcile before resubmit | May have accepted | Duplicate risk. |
| Provider accepted, delivery deferred | No | Do not submit new send | Yes, per provider policy | Track delivery events. |
| Provider hard bounce | No | Do not retry same email | Usually stops | Handle recipient/policy. |
| Delivered webhook arrives twice | No | No | Not involved | Deduplicate event; send no new email. |
| Valid intentional user resend request | New request with new key per policy | Send new logical email | Per provider | Distinguish from old retry. |

This matrix is directional; actual decisions depend on email type, SMTP/provider responses, state observability, and business policies.

## 16. Operational Observability: Count What Matters

Useful metrics:
- HTTP email send requests and duplicate requests by idempotency key;
- outbox items in `PENDING`, `RETRY_WAIT`, `UNKNOWN`, and dead-letter;
- SMTP attempts per `messageKey`;
- latency from outbox creation to SMTP acceptance;
- SMTP `4xx`/`5xx` and timeout rates;
- lease expiration / job reclaim counts;
- provider deferred, delivered, bounced, and complaint events;
- detected or suspected duplicate submission rate;
- age of oldest job in queue;
- retries per provider/tenant.

Example structured log:

```json
{
  "event": "email.send_attempt",
  "messageKey": "msg-a817",
  "attemptId": "att-2",
  "retryOwner": "outbox-worker",
  "attemptNumber": 2,
  "outcome": "SMTP_ACCEPTED",
  "smtpProvider": "relay-primary",
  "latencyMs": 781
}
```

Avoid logging:
- HTML/plain bodies;
- unnecessary emails or personal data;
- attachment bytes/Base64;
- URLs containing tokens;
- passwords/SMTP credentials;
- full exceptions if they may contain sensitive details.

Correlate logs using `messageKey`, `attemptId`, and correlation IDs. If `Message-ID` or provider ID is available, store it as supplementary metadata. Users must not be able to view someone else's email history just by knowing a message key; lookup endpoints require authorization.

### 16.1. Alerts Worth Watching

- Continuously growing queue backlog.
- Jobs stuck in `RETRY_WAIT` too long.
- Sudden spike in `UNKNOWN` counts.
- Provider repeatedly returning rate limits or connection errors.
- Abnormal spike in bounces/complaints.
- Frequent worker lease reclaims.
- Signals of duplicate sends for the same business event/recipient.
- Sending verification emails after token expiration.

Alerts should distinguish submission incidents from delivery incidents; the remediation for each differs.

## 17. Common Misconceptions

### "Every 4xx should be retried immediately"

No. `4xx` is a temporary response class, yet it can signal rate limits, greylisting, or overload. Apply policy-based backoff and avoid burst requests.

### "If send throws an exception, it definitely wasn't sent"

No. A timeout after `DATA` or a connection drop after the relay accepted the message can produce an `UNKNOWN` outcome.

### "Same message key means SMTP automatically drops duplicates"

No. Generic SMTP makes no deduplication guarantees based on custom headers. Keys aid tracing; use provider-supported idempotency and handle unknown outcomes.

### "More client retries and worker retries mean higher reliability"

No. Overlapping retries can trigger request storms, exceed quotas, and create duplicates. Assign one owning layer per retry type and enforce an overall budget.

### "Provider deferred means the backend must resend"

No. The provider typically still holds the message and retries delivery itself. The backend should only track state, not create a new submission.

### "SMTP accepted means delivered"

No. Submission acceptance does not mean the destination server received it, and delivery does not guarantee the user saw it in their Inbox or opened it.

### "Putting @Retryable around JavaMailSender is enough"

No. You need an outbox, attempt history, `UNKNOWN` status, error classification, backoff, timeouts, and duplicate controls.

### "Idempotency-Key is a form of authorization"

No. The key only identifies repeated requests. The server must still authenticate and authorize the actor, tenant, business object, and recipient.

## 18. Hands-On Exercises

### Exercise 1 — Client Timeout

An HTTP POST to send an invoice committed the outbox row, but the response was lost. Design `Idempotency-Key` and the API response so repeated requests return the same message key without creating a new job.

### Exercise 2 — Two Competing Workers

Two workers read the same `PENDING` job. Use atomic claims or `FOR UPDATE SKIP LOCKED` so only one worker acquires the lease. Explain why lease fencing only protects DB state and cannot recall an SMTP submission that already occurred.

### Exercise 3 — SMTP 451

The SMTP relay returns `451` before accepting data. Design `RETRY_WAIT`, exponential backoff with jitter, an attempt limit, and how to record the error category.

### Exercise 4 — Timeout After DATA

A worker times out after finishing message transmission. Explain why it must not record definitive `FAILED` and design reconciliation before resubmitting.

### Exercise 5 — Provider Deferred

The provider accepted the message and then reported `deferred` due to destination server greylisting. Explain which layer is retrying and why the worker must not call `send(...)` again.

### Exercise 6 — 429 on Provider API

When using an HTTP provider API, you receive `429` and `Retry-After`. Design rate limiting, delay handling, and a provider idempotency key if supported. Contrast this mechanism with generic SMTP.

### Exercise 7 — Retry Budget

Set a limit of at most 5 attempts and a 10-minute deadline for verification emails. Specify how to handle jobs waiting past the deadline or whose token has expired.

### Exercise 8 — Partial Recipient Success

An email has three recipients: two are accepted and one is rejected. Propose a per-recipient tracking model or splitting into one logical email per recipient to avoid resending to those already accepted.

### Exercise 9 — Late Webhook

The provider sends `delivered` and then an older `deferred` event arrives late. Store event history, deduplicate, and update status via a state machine so overall status never regresses.

### Exercise 10 — Investigating Duplicates

A customer receives two confirmation emails. Use business event ID, `messageKey`, `attemptId`, RFC `Message-ID`, and provider message ID to determine whether the duplicate came from the client creating two jobs, a worker retrying an uncertain outcome, or the provider delivering multiple times.

## 19. Summary

**Retries at the client, queue worker, or provider** are three distinct mechanisms that cannot substitute for one another. The client retries the API request to create a job, the worker retries SMTP/provider submission of a persisted job, and the MTA/provider retries delivery after accepting the message.

A reliable Spring Framework Mail design should:
1. Use **Idempotency-Key** for email-creation requests alongside backend unique constraints.
2. Persist requests to a **transactional outbox**; never send directly as an uncontrolled side effect inside business transactions.
3. Have workers **exclusively claim jobs**, persist attempts, and use backoff/jitter with clear limits.
4. Classify errors into **retryable, permanent, and `UNKNOWN`**, especially for timeouts after `DATA`.
5. Once SMTP/provider has accepted, **never resubmit simply because the provider reports `deferred`**; let the provider retry delivery per its policy.
6. Correlate webhooks/provider IDs back to `messageKey`, handle duplicate/out-of-order events, and protect sensitive data.

Idempotency reduces duplicate jobs and sends, yet **does not turn SMTP into exactly-once delivery**. The practical goal is assigning retry ownership to the right layer, recording honest state, minimizing unintended duplicates, and providing a reconciliation path when outcomes are uncertain.
