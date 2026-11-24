# Outbox Pattern for Durable Mail Send Requests

In a **Spring Framework Mail** application, direct email sending is often written very concisely:

~~~java
orderRepository.save(order);
mailSender.send(message);
~~~

However, in production, a **database transaction** and an **SMTP submission** are two operations belonging to two separate systems. A database transaction cannot roll back an email already accepted by an SMTP relay; conversely, when an application crashes after committing data but before sending via SMTP, the email may never be sent.

The **transactional outbox pattern** solves this critical gap by **persisting the email send intent in the same database transaction as the business state change**. When the transaction commits, the business state and the mail job coexist durably. When it rolls back, neither is recorded. An independent worker reads committed mail jobs, builds the MIME message, sends via `JavaMailSender`, and updates the state.

An outbox does not turn SMTP into an exactly-once transaction. A worker can succeed in sending and then die before saving `SUBMITTED`, causing the same job to be retried and the email to be sent twice. Therefore, beyond writing to the outbox, the system needs **idempotency, claim/lease, backoff, error classification, attachment management, quota control, auditing, and monitoring**.

This lesson presents the full transactional outbox flow for Spring Mail, from dual-write risks to schema, Java code, multi-worker polling, crash windows, and testing.

## 1. The dual-write problem when sending email

An order confirmation use case:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {

    Order order = orderRepository.require(orderId);

    order.confirm();

    mailService.sendOrderConfirmation(order);
}
~~~

`@Transactional` can manage database changes, but **does not make an SMTP send participate in the transaction**. Possible scenarios:

| Scenario | Consequence |
| --- | --- |
| SMTP accepts email, DB commit fails | Recipient sees confirmation for an uncommitted business action |
| DB commits then JVM crashes before SMTP | No email despite business completion |
| SMTP is slow inside transaction | Holds DB locks longer, increases latency |
| SMTP times out after DATA | Unclear whether relay received it |
| HTTP request is retried | Can create multiple send requests |
| Provider outage | HTTP may fail despite valid business change |

Another approach is also unsafe:

~~~text
1. Commit order transaction.
2. Call mailSender.send(...).
~~~

It has a **crash window between steps 1 and 2**. Adding `try/catch` cannot recover work that was never durably persisted.

## 2. How does the outbox change the architecture?

~~~mermaid
flowchart TD
    A["Business request"] --> B["BEGIN transaction"]
    B --> C["Update domain entities"]
    B --> D["INSERT mail_outbox"]
    C --> E["COMMIT atomically"]
    D --> E
    E --> F["Outbox poller / dispatcher"]
    F --> G["Claim job"]
    G --> H["Compose MIME"]
    H --> I["JavaMailSender.send"]
    I --> J["Persist attempt result"]
~~~

Standard flow:

1. Application service checks authorization and business rules.
2. Within **one DB transaction**, persist the business state and a mail outbox row.
3. Commit the transaction.
4. Worker finds due jobs.
5. Worker claims jobs to prevent multiple processes from handling the same one.
6. Worker builds MIME using approved sender profile/recipient/template.
7. Send via SMTP relay.
8. Record send state or schedule retry.

Key decision: **do not call SMTP inside the business transaction**; the transaction only records the send intent. If workers are stopped for several minutes, the work still exists in the outbox DB.

### What does the outbox guarantee and not guarantee?

| Property | Guaranteed? |
| --- | --- |
| Business state and mail intent commit together | Yes, if sharing the same transactional resource |
| Intent survives JVM restarts | Yes, when DB is durable |
| No intent created on transaction rollback | Yes |
| Worker can retry | Yes, with status/scheduler design |
| No duplicate intent from the same event | Possible via unique key |
| SMTP sends exactly once | **Not guaranteed on its own** |
| Recipient received email in inbox | **Not guaranteed** |
| Provider never rejects email | **Not guaranteed** |

An outbox is a way to create **durable work**, not magic that eliminates the limitations of an external side effect.

## 3. Three concepts: intent, attempt, delivery

**Mail intent** is "the need to send a business notification", for example a payment receipt for order ORD-981.

**Send attempt** is one worker try to submit the intent to a relay.

**Delivery outcome** is the final result on the receiving side, which may arrive later via provider webhook or bounce.

~~~text
Mail intent: payment-receipt-981

Attempt 1:
  temporary SMTP timeout

Attempt 2:
  SMTP relay accepted

Provider feedback:
  deferred -> delivered
~~~

`JavaMailSender.send(...)` returning successfully only proves that submission did not error at that moment; it does not mean the customer read it or the email reached the inbox.

You can name the status `SUBMITTED` rather than `SENT` to avoid confusion with delivered.

## 4. How does an outbox differ from @Async?

One pattern:

~~~java
@Async("mailExecutor")
public void sendEmail(MailCommand command) {
    mailSender.send(buildMessage(command));
}
~~~

`@Async` offloads sending to another thread when the Spring proxy applies properly, but **tasks queued in an in-memory executor can vanish when the process dies**.

| Characteristic | Plain `@Async` | Transactional outbox |
| --- | --- | --- |
| Does not block HTTP thread | Possible | Yes |
| Job survives restarts | Not by default | Yes |
| Atomic with business transaction | No | Yes |
| Durable retry schedule | Needs extra building | Can use DB |
| Attempt history | Not built in | Can be stored |
| Prevents duplicate SMTP | No | Still must handle duplicate possibility |

You can use `@Async` for a dispatcher, but the source of truth must be the committed mail outbox, not merely a queued Runnable.

## 5. How does an outbox differ from a message broker?

A durable broker provides queueing, yet dual-write still exists if you do:

~~~text
Commit business DB
  -> Publish Kafka/RabbitMQ event
~~~

and the JVM crashes after commit before publish.

A transactional outbox can use:

~~~text
A. DB polling:
business DB + outbox -> worker -> JavaMailSender

B. CDC relay:
business DB + outbox -> CDC -> broker -> mail worker
~~~

In both cases, **the business change and outbox row must be in the same transaction**. CDC or a broker adds scaling capability but does not make SMTP exactly-once.

For moderate mail volume, database polling is usually simpler; for high throughput, consider a relay/broker and consumer idempotency.

## 6. Outbox state model

~~~mermaid
flowchart TD
    A["PENDING"] --> B["CLAIMED"]
    B --> C{"Send result"}
    C -->|"Accepted"| D["SUBMITTED"]
    C -->|"Temporary"| E["RETRY"]
    C -->|"Permanent"| F["FAILED_PERMANENT"]
    C -->|"Ambiguous"| G["UNKNOWN_OUTCOME"]
    E --> B
    G --> H["Reconcile / retry policy"]
    H --> B
    A --> I["CANCELED"]
~~~

| Status | Meaning |
| --- | --- |
| `PENDING` | Job committed, not yet processed |
| `CLAIMED` | A worker holds the lease |
| `RETRY` | Job may be retried when `nextAttemptAt` arrives |
| `SUBMITTED` | Relay confirmed submission |
| `UNKNOWN_OUTCOME` | Cannot be certain whether relay received it |
| `FAILED_PERMANENT` | Do not automatically retry the same payload |
| `CANCELED` | Business decision not to send anymore |

A job may need a `HOLD` or `ACTION_REQUIRED` state when credentials/accounts are locked. Status names are application-defined; Spring Mail does not prescribe them.

## 7. Example mail_outbox schema

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(120) NOT NULL,
    purpose VARCHAR(80) NOT NULL,
    business_event_id VARCHAR(160) NOT NULL,
    idempotency_key VARCHAR(320) NOT NULL,
    recipient_contact_id VARCHAR(160),
    sender_profile_id VARCHAR(160) NOT NULL,
    template_id VARCHAR(160) NOT NULL,
    template_version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    status VARCHAR(40) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL,
    lease_owner VARCHAR(160),
    lease_token UUID,
    lease_until TIMESTAMP WITH TIME ZONE,
    submitted_at TIMESTAMP WITH TIME ZONE,
    last_failure_category VARCHAR(100),
    last_failure_message VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_mail_outbox_intent UNIQUE (idempotency_key)
);

CREATE INDEX idx_mail_outbox_due
    ON mail_outbox (status, next_attempt_at, created_at);
~~~

This is illustrative PostgreSQL-style SQL. Data types, index syntax, and claiming mechanics must be adapted to the actual database.

Important columns:

- `id` identifies the job.
- `tenant_id`, `purpose`, `sender_profile_id` protect routing/quota/auditing.
- `business_event_id` links the domain event.
- `idempotency_key` prevents duplicate enqueues.
- `recipient_contact_id` or recipient snapshot is managed per policy.
- `template_id` and `template_version` keep content consistent.
- `payload_json` stores necessary info, avoiding credentials.
- `attempt_count`, `next_attempt_at` support retries.
- `lease_owner`, `lease_token`, `lease_until` support multi-worker coordination.

Do not place SMTP passwords, plaintext reset tokens, Base64 PDFs, or full MIME messages in the outbox without very specific security/retention requirements.

## 8. Idempotency key must be stable per send intent

An example key:

~~~java
String key =
        "payment-receipt:"
        + tenantId + ":"
        + paymentId + ":"
        + recipientContactId + ":v1";
~~~

If a payment event is received twice, the same intent should create **one outbox row**, typically enforced by a DB unique constraint.

Distinguish:

- **HTTP retry:** does not create a new mail job.
- **Duplicate webhook:** does not create a new mail job.
- **Requested resend:** is a new intent, requiring a new key/version.
- **Recipient address change:** policy must specify snapshot vs re-resolution.
- **Multiple recipients:** requires explicit keys per recipient or recipient group.

Do not generate a new UUID as the idempotency key on each repeated call and assume deduplication exists. The UUID job ID can differ from the idempotency key.

### Unique outbox key does not guarantee once-only SMTP

If a worker sends but fails to write status, the job may be sent again. **Enqueue** idempotency and **external submission** idempotency are two distinct problems.

## 9. Writing business state and outbox in the same transaction

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final MailOutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orders,
            MailOutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void confirmOrder(
            UUID orderId,
            AuthenticatedActor actor) {

        Order order = orders.require(orderId);

        order.requireAccess(actor);

        if (order.isConfirmed()) {
            return;
        }

        order.confirm();

        MailOutboxJob job =
                MailOutboxJob.orderConfirmed(
                        order,
                        "order-confirmed:"
                                + order.getId()
                );

        outbox.insertIfAbsent(job);
    }
}
~~~

These classes/methods are application-defined abstractions, not default Spring APIs. Ensure the business entity and outbox share the same DB transaction manager/resource.

When `@Transactional` commits successfully, both business state and job exist; when it rolls back, both roll back.

### Do not put SMTP inside this method

A business transaction should not wait to open TLS connections, construct MIME, and receive SMTP responses. The worker performs external I/O after commit.

## 10. Common mistakes with @Transactional

**Self-invocation:** A method calling `this.transactionalMethod()` can bypass the Spring transaction proxy in standard proxy-based setups.

**Misplaced REQUIRES_NEW:** Writing the outbox in a separate transaction can commit even when the business transaction rolls back, breaking required atomicity.

**Rollback rules:** Checked exceptions and rollback policies must be well understood; do not assume all exceptions trigger rollback identically.

**Separate DB resources:** If business state is in database A and outbox is in database B, two repository calls do not automatically form one atomic transaction.

**Transaction event listener:** `@TransactionalEventListener(phase = AFTER_COMMIT)` can wake up a worker, but **does not replace an outbox record**. If you only send email inside an after-commit listener, the process can still crash between DB commit and the listener.

## 11. Both directions: commit and rollback

~~~text
BEGIN
  UPDATE orders SET status = 'CONFIRMED'
  INSERT INTO mail_outbox (...)
COMMIT
~~~

After commit, the worker can send even after the HTTP request ends.

If it fails:

~~~text
BEGIN
  UPDATE orders ...
  INSERT INTO mail_outbox (...)
ROLLBACK
~~~

After rollback, there is no durable mail intent. This is the core guarantee boundary.

Do not do:

~~~text
COMMIT order
  -> INSERT mail_outbox
~~~

because there is a crash gap. Also do not send SMTP before commit just to reduce latency while ignoring the risk of false notifications.

## 12. Payload: reference or snapshot?

A job can store:

~~~json
{
  "orderId": "order-981",
  "recipientContactId": "contact-77",
  "receiptObjectKey": "receipts/tenant-42/order-981-v1",
  "currency": "VND"
}
~~~

**Reference-only** keeps the payload small, though workers might read data that changed days later.

**Snapshot** preserves content as of event time, aiding audits, though it uses storage and may contain PII.

A balanced approach:

1. Record tenant, purpose, event ID, and recipient intent.
2. Pin template version and locale when needed.
3. Store an immutable snapshot or object reference for critical data.
4. Do not store unnecessary secrets/tokens.
5. Include a payload schema version.
6. Attach tenant-scoped retention and access controls.

A payment receipt needs to reflect the exact amount/status at event time; a marketing email, however, may need to recheck consent immediately before sending.

## 13. Template versions and delayed sends

Suppose a job was created with template version 3, but a worker processes it after an outage when production is already on version 4. If the worker always renders the latest template, the same intent may send different content.

~~~text
templateId: ORDER_CONFIRMED
templateVersion: 3
locale: vi-VN
snapshotId: order-snapshot-981
~~~

For emails requiring auditability, pinning the template/snapshot keeps output consistent. For less sensitive notifications, using the latest template may be acceptable if policy states so explicitly.

User-supplied data inserted into HTML must be contextually escaped; an outbox does not automatically prevent template injection or HTML injection.

## 14. When does the worker start sending?

A dispatcher should:

1. Find due `PENDING` or `RETRY` jobs.
2. Claim a small batch in a short transaction.
3. Commit the claim.
4. Send via SMTP outside the claim transaction.
5. Record the outcome in another short transaction.
6. Continue polling/retrying.

~~~mermaid
flowchart LR
    A["Poll due jobs"] --> B["Claim + lease"]
    B --> C["Commit claim"]
    C --> D["Compose MIME"]
    D --> E["SMTP submission"]
    E --> F["Save outcome"]
~~~

Do not hold DB locks across `mailSender.send(...)` because SMTP can be very slow or time out.

## 15. Claiming with PostgreSQL SKIP LOCKED

A multi-worker batch claim approach:

~~~sql
WITH picked AS (
    SELECT id
    FROM mail_outbox
    WHERE status IN ('PENDING', 'RETRY')
      AND next_attempt_at <= now()
    ORDER BY next_attempt_at, created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox m
SET status = 'CLAIMED',
    lease_owner = :worker_id,
    lease_token = :lease_token,
    lease_until = now() + interval '2 minutes',
    updated_at = now()
FROM picked
WHERE m.id = picked.id
RETURNING m.*;
~~~

`:batch_size`, `:worker_id`, `:lease_token` are bind parameters. A shared token for the batch can still work if result updates always check both job ID and token; per-claim tokens make tracing clearer.

`FOR UPDATE SKIP LOCKED` lets other workers skip rows locked by another transaction. It does not by itself solve lease expiry, duplicate SMTP, or fairness.

Notes:

- Run the query inside a real DB transaction.
- Commit the claim quickly.
- Use an index supporting `status` and `next_attempt_at`.
- Set batch size according to capacity.
- Do not assume this SQL is portable across all databases.
- At high volume, consider fairness across tenants and purposes.


## 16. Leases for recovery when a worker dies

If a worker claims a job and the process crashes, the job will stay `CLAIMED` forever without an expiration mechanism.

~~~text
10:00  Worker A claims job-981
10:01  Worker A crashes
10:02  leaseUntil passes
10:03  Worker B reclaims job-981
~~~

A system can allow reclaim when:

~~~sql
WHERE (
    status IN ('PENDING', 'RETRY')
    AND next_attempt_at <= now()
)
OR (
    status = 'CLAIMED'
    AND lease_until < now()
)
~~~

When reclaiming, generate a new lease token and update the owner. An old worker could pause for a long time and then wake up even after losing its lease.

### Fencing token on completion

Allow only the worker holding the valid lease to update status:

~~~sql
UPDATE mail_outbox
SET status = 'SUBMITTED',
    submitted_at = now(),
    lease_owner = NULL,
    lease_token = NULL,
    lease_until = NULL,
    updated_at = now()
WHERE id = :job_id
  AND status = 'CLAIMED'
  AND lease_token = :lease_token;
~~~

If the updated row count is 0, do not treat the mark operation as successful; the job may have been reclaimed by another worker.

**Fencing only protects DB status.** It cannot recall an SMTP message already sent by the old worker. After lease expiry, two workers can still execute external sends concurrently if the old worker has not stopped.

## 17. Lease duration, heartbeats, and timeouts

If an email with a large attachment takes 90 seconds to send while the lease is only 30 seconds, another worker may reclaim it while the first attempt is still active.

An overly long lease, conversely, slows crash recovery.

Controls:

- Set bounded SMTP timeouts.
- Choose a lease appropriate for expected send duration.
- Renew leases via heartbeats for long jobs.
- Use token/version for conditional renewals.
- Never let a worker hold a job indefinitely.
- Separate heavy report rendering from SMTP attempts when needed.
- Record lease expirations and potential duplicate sends.

Heartbeats must verify the current worker's token; do not allow a worker that has lost its lease to renew or update state.

**Leases do not create exactly-once.** They are a coordination and crash-recovery mechanism.

## 18. Separating the claim transaction from SMTP send

An illustrative scheduler:

~~~java
@Component
public class MailOutboxScheduler {

    private final MailClaimService claims;
    private final MailAttemptProcessor processor;

    public MailOutboxScheduler(
            MailClaimService claims,
            MailAttemptProcessor processor) {
        this.claims = claims;
        this.processor = processor;
    }

    @Scheduled(
        fixedDelayString =
                "${app.mail.outbox.poll-delay-ms:1000}"
    )
    public void poll() {

        List<ClaimedMailJob> batch =
                claims.claimDueJobs(20);

        for (ClaimedMailJob job : batch) {
            processor.process(job);
        }
    }
}
~~~

Claim service puts its transaction separately:

~~~java
@Service
public class MailClaimService {

    private final MailOutboxRepository repository;

    public MailClaimService(
            MailOutboxRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public List<ClaimedMailJob> claimDueJobs(
            int limit) {
        return repository.claimDueJobs(limit);
    }
}
~~~

The worker processes **outside the claim transaction**:

~~~java
@Service
public class MailAttemptProcessor {

    private final JavaMailSender mailSender;
    private final MailComposer composer;
    private final MailAttemptResultService results;

    public MailAttemptProcessor(
            JavaMailSender mailSender,
            MailComposer composer,
            MailAttemptResultService results) {
        this.mailSender = mailSender;
        this.composer = composer;
        this.results = results;
    }

    public void process(ClaimedMailJob job) {

        try {
            MimeMessage message =
                    composer.compose(
                            mailSender,
                            job
                    );

            mailSender.send(message);

            results.markSubmitted(
                    job.jobId(),
                    job.leaseToken()
            );

        } catch (Exception failure) {
            results.recordFailure(
                    job.jobId(),
                    job.leaseToken(),
                    failure
            );
        }
    }
}
~~~

This is an **architectural skeleton**, not a standalone compilable file: corresponding models, repositories, and components must be defined, along with null handling, validation, and exception policies. A production result service must classify errors rather than retrying all exceptions identically.

`MailAttemptResultService` should be a separate bean so `@Transactional` proxying works cleanly and avoids self-invocation within the same class.

## 19. Building MIME from an approved job

An illustrative composer:

~~~java
@Component
public class MailComposer {

    private final SenderPolicy senderPolicy;
    private final RecipientResolver recipientResolver;
    private final MailTemplateRenderer renderer;

    public MimeMessage compose(
            JavaMailSender sender,
            ClaimedMailJob job)
            throws MessagingException {

        ApprovedSenderProfile profile =
                senderPolicy.requireAllowed(job);

        String recipient =
                recipientResolver.resolve(job);

        RenderedMail rendered =
                renderer.render(
                        job.templateId(),
                        job.templateVersion(),
                        job.payload()
                );

        MimeMessage mime =
                sender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(
                        mime,
                        true,
                        "UTF-8"
                );

        helper.setFrom(
                profile.fromAddress()
        );

        if (profile.replyToAddress() != null) {
            helper.setReplyTo(
                    profile.replyToAddress()
            );
        }

        helper.setTo(recipient);
        helper.setSubject(rendered.subject());

        helper.setText(
                rendered.plainText(),
                rendered.htmlText()
        );

        mime.setHeader(
                "X-Correlation-Id",
                job.jobId().toString()
        );

        return mime;
    }
}
~~~

`SenderPolicy`, `RecipientResolver`, `RenderedMail`, and related types are application abstractions. In multi-tenant systems, select the appropriate `JavaMailSender` via a provider/account registry **before** calling `createMimeMessage()`. Never take SMTP hosts/credentials from unverified HTTP requests.

A job existing in the DB does not mean every policy from enqueue time is still valid:

- The sender domain may have been revoked.
- The recipient may have unsubscribed.
- The tenant may have been suspended.
- A security token may have expired.
- An attachment may have been deleted per policy.
- Templates/consent may have changed.

Checks that must be accurate at send time must be re-executed.

## 20. Separating correlation, Message-ID, and provider ID

A system may use:

| Identifier | Role |
| --- | --- |
| Outbox job ID | Identifies the send intent |
| Idempotency key | Prevents duplicate enqueue |
| Attempt ID | Identifies one submission try |
| Correlation ID | Links logs/tracing |
| `Message-ID` header | Supports threading/tracing |
| Provider message ID | Reconciles submission/delivery |
| Business event ID | Links domain events |

Adding a header:

~~~java
mime.setHeader(
        "X-Correlation-Id",
        job.getId().toString()
);
~~~

does not force an SMTP provider or receiving MX to deduplicate. Similarly, `Message-ID` is not a network-wide idempotency guarantee.

Do not assume "the relay will see the same Message-ID and deliver only one email." Rely on provider contracts if they offer a dedicated idempotency API; standard SMTP has no universal idempotency key.

## 21. Crash window after SMTP acceptance

This is the core limitation:

~~~text
1. Worker A claims job-981.
2. Worker A sends full MIME.
3. SMTP server returns 250 OK / accepted.
4. Worker A crashes before UPDATE status = SUBMITTED.
5. Lease expires.
6. Worker B reclaims and resends job-981.
~~~

The recipient **may receive two emails**, even though the outbox has only a single row.

If you try to mark `SUBMITTED` **before** sending to avoid duplicates:

~~~text
1. DB marks SUBMITTED.
2. JVM crashes.
3. SMTP has not been called.
~~~

you instead risk **losing emails**.

Because DB and SMTP cannot commit atomically together, both orderings have a crash window. A transactional outbox primarily provides **at-least-once processing/submission attempts** subject to retry limits; it does not by itself guarantee exactly-once external side effects or inbox delivery.

### Practical production goals

- Never lose durable mail intents due to pre-worker crashes.
- Provide retry mechanisms and recovery for stuck `CLAIMED` jobs.
- Reduce duplicate probability via leases/timeouts/observability.
- Accept and handle duplicates if they occur.
- Define policies for emails that must not be arbitrarily duplicated (e.g., tokens, financial notices).
- Do not promise guarantees that SMTP/providers do not provide.

## 22. SMTP unknown outcome

A tricky scenario:

~~~text
Client sends DATA.
Server has accepted it.
Network drops before client reads response.
Client receives timeout.
~~~

The client cannot tell whether the provider received it. This is an **unknown outcome**, not simply a definite failure.

A classifier might look like:

~~~java
public enum MailFailureCategory {
    TEMPORARY_TRANSPORT,
    PROVIDER_THROTTLED,
    AUTHENTICATION_FAILED,
    INVALID_SENDER,
    INVALID_RECIPIENT,
    MESSAGE_TOO_LARGE,
    CONTENT_POLICY_REJECTED,
    ATTACHMENT_UNAVAILABLE,
    UNKNOWN_OUTCOME,
    UNEXPECTED_ERROR
}
~~~

Inspect SMTP reply codes, enhanced statuses, nested Jakarta Mail exceptions, and provider rules instead of merely checking `exception.getMessage().contains("timeout")` and retrying.

| Failure | Handling direction |
| --- | --- |
| Temporary network error before submission | Retry with backoff |
| Rate limit or transient provider error | Retry per deadline/hint |
| Invalid SMTP AUTH | Hold/alert/rotate secret |
| Unverified sending domain | Do not hot-retry, fix configuration |
| Hard message size reject | Reduce payload or use download link |
| Permanent invalid recipient | Fail/suppress per policy |
| Temporary storage unavailability | Retry within retention window |
| Unknown outcome | Reconcile if provider supports it; retry weighing duplicates |
| Crash after accepted | Job may be resent |

Uncertain failures can also occur when calling a provider HTTP API. Provider-specific idempotency tokens are only useful if there is a clear contract on how the provider handles them.

## 23. Retry backoff and jitter

A temporary provider outage should not cause thousands of workers to retry every 100 ms.

Illustrative schedule:

~~~text
Attempt 1: immediately
Attempt 2: after about 30 seconds
Attempt 3: after about 1 minute
Attempt 4: after about 2 minutes
Attempt 5: after about 4 minutes
...
Cap max delay, attempt count, and job age.
~~~

A Java function with exponential backoff and jitter:

~~~java
public Duration nextDelay(int attemptCount) {

    int exponent =
            Math.min(
                    Math.max(attemptCount - 1, 0),
                    8
            );

    long baseSeconds =
            Math.min(
                    30L * (1L << exponent),
                    3600L
            );

    long jitterSeconds =
            ThreadLocalRandom.current()
                    .nextLong(0L, 16L);

    return Duration.ofSeconds(
            baseSeconds + jitterSeconds
    );
}
~~~

This is an example policy; in practice, define clearly whether attempt count increments at claim time or at send start. If a provider advertises a retry delay, respect that contract.

Do not retry indefinitely on permanent errors such as oversized messages, unauthorized From addresses, or revoked credentials. Those errors should transition to `FAILED_PERMANENT` or `ACTION_REQUIRED`.

## 24. Retries differ by mail purpose

An OTP is only valid for a few minutes. A payment receipt may need longer retries. A marketing campaign may need to stop when the campaign window ends.

| Mail purpose | Special requirement |
| --- | --- |
| OTP | Short TTL; never send expired codes |
| Password reset | Recheck token validity |
| Payment receipt | Keep snapshot/audit, support resend |
| Order status | Check current state and policy |
| Marketing | Consent, unsubscribe, suppression, expiry |
| Operations | Escalate if mail channel fails |

Durability does not mean "keep retrying forever." An email with an expired token or an unsubscribed recipient may have to be canceled according to rules.

## 25. Attachments should live in durable storage

Do not embed large files inside the outbox payload:

~~~java
public record MailCommand(
        String recipient,
        byte[] reportPdf) {
}
~~~

If PDFs are Base64-encoded in JSON and stored in the DB, the outbox table bloats quickly, backups become heavy, and workers easily retain many `byte[]` arrays on the heap.

A lightweight payload:

~~~json
{
  "reportId": "report-981",
  "attachmentStorageKey": "reports/tenant-42/report-981-v1",
  "attachmentBytes": 5242880,
  "attachmentVersion": "v1"
}
~~~

The worker fetches the resource when needed:

~~~java
InputStreamSource source = () ->
        attachmentStorage.openReadableStream(
                job.attachmentStorageKey()
        );

helper.addAttachment(
        "report.pdf",
        source,
        "application/pdf"
);
~~~

`attachmentStorage` is an illustrative application API. The source must be able to open a fresh stream each time Jakarta Mail requests it; an `InputStreamResource` wrapping an already-opened stream may fail on re-reads.

Storage needs:

- Readable from other worker replicas.
- Survives restarts and the retry window.
- Enforces tenant/authorization checks.
- Has immutable versions/checksums when content must stay fixed.
- Has retention/cleanup that does not delete too early.
- Has appropriate size/security policies and malware scanning.

Local `/tmp` of an HTTP request is usually not a durable reference for an outbox job.

## 26. MIME size, queue memory, and backpressure

A 10 MiB attachment can become a MIME part larger than roughly 13 MiB due to Base64/line wrapping, not counting headers and HTML. Providers have their own max message sizes; Spring `JavaMailSender` does not replace application policy.

Set limits on:

- Size of each attachment.
- Total raw attachment bytes.
- Number of attachments and inline images.
- Estimated MIME bytes.
- Number of active SMTP connections/workers.
- Number of jobs claimed ahead of execution.
- Memory/disk for staging and report rendering.
- Rate limits per provider/account.

If a worker claims 2,000 jobs while the executor queue only has capacity 100, the remaining jobs hold leases even though no worker is processing them. **Claim only within actual capacity**.

### A queue is not a memory limit

A queue of 100 tasks holding 20 MiB `byte[]` arrays can still hold roughly 2,000 MiB of raw arrays. Outbox workers should queue **job IDs/lease tokens**, not attachment bytes.

## 27. One or multiple recipients per job?

Two models:

**One job, multiple recipients:** fewer messages, but partial acceptance, To/Cc privacy, and per-recipient retries become complex.

**One job per recipient:** easy to enforce recipient policies, suppression, tracing, quotas, template personalization, and independent retries.

For personalized transactional notifications, one job per recipient is usually easier to control. If sending to multiple recipients in a single SMTP message, understand partial send semantics and avoid exposing recipient emails in To/Cc when they should not see one another.

## 28. Multi-tenant, quotas, and fair scheduling

If workers always pick the oldest job, one tenant with a million marketing emails can delay another tenant's password resets.

You can:

- Separate lanes by purpose.
- Priority classes with dedicated capacity.
- Rate limits per provider account and tenant.
- Fair scheduling across tenants.
- Global quotas per provider.
- Separate concurrency for large attachments.
- Retry caps to prevent a failing batch from starving workers.

A local quota limiter per JVM does not enforce a global provider quota if multiple replicas share an account. Use distributed limiters or intentional capacity partitioning.

Never let bulk marketing monopolize workers while security emails wait indefinitely.

## 29. Safe shutdown and deployment

When a pod/service receives a termination signal:

1. Stop claiming new jobs.
2. Let in-flight attempts finish within an appropriate grace period.
3. Record outcomes if time remains.
4. Never mark `SUBMITTED` before SMTP.
5. Let unfinished `CLAIMED` jobs be recovered via lease expiry.
6. Do not delete attachments that are still in `RETRY`.
7. Retain logs/attempt IDs for investigation.

Graceful shutdown reduces duplicate probability, but **does not eliminate the crash window** immediately after SMTP acceptance.

Misconfigured liveness probes causing restart loops can leave many attempts unable to update status in time. Monitoring and shutdown settings must align with lease/timeout policies.

## 30. Periodic polling and wake-up events

Example scheduler:

~~~java
@Scheduled(
    fixedDelayString =
            "${app.mail.outbox.poll-delay-ms:1000}"
)
public void run() {
    // Claim small batch, process each job,
    // record outcome using lease token.
}
~~~

You can publish a local event after commit to wake workers faster. However, events/listeners are only a latency optimization; if lost due to a crash, the periodic scheduler must still scan the outbox.

Never use `@TransactionalEventListener(AFTER_COMMIT)` **to replace the outbox** with an unpersisted SMTP call.

## 31. Attempt history and audit

An attempts table aids investigation:

~~~sql
CREATE TABLE mail_send_attempt (
    id UUID PRIMARY KEY,
    mail_job_id UUID NOT NULL,
    attempt_number INTEGER NOT NULL,
    worker_id VARCHAR(160),
    provider_id VARCHAR(100),
    provider_account_id VARCHAR(160),
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    finished_at TIMESTAMP WITH TIME ZONE,
    outcome VARCHAR(80),
    failure_category VARCHAR(100),
    provider_message_id VARCHAR(250),
    smtp_reply_code VARCHAR(50)
);
~~~

An attempt may have started and crashed, so `finished_at` can be null. Define consistently at which step `attempt_number` increments.

Do not log raw mail content, credentials, or tokens in attempts/error logs. Recording job ID, provider/account, status, reply code, and reason category is usually sufficient for observability.

## 32. Provider feedback and delivery outcomes

After an SMTP relay accepts, the provider may emit:

~~~text
SUBMITTED
  -> DEFERRED
  -> DELIVERED
  -> BOUNCED
  -> COMPLAINED
~~~

Depending on the provider, data may come via webhooks/APIs or a bounce mailbox; not every SMTP account provides full feedback.

When receiving events:

1. Verify signature/source and provider account.
2. Parse the correct event version.
3. Map provider message ID to outbox job/attempt.
4. Deduplicate events.
5. Update delivery/recipient state.
6. Apply suppression scoped to tenant/purpose.
7. Audit unmappable or anomalous events.

Never trust a raw tenant ID sent by a webhook without verification. Never treat a successful `mailSender.send` call as proof of delivery.


## 33. Monitoring the outbox in production

An HTTP API can record mail intents successfully while workers fail and thousands of emails go unsent. Without observing backlog size and job age, operators may not realize the system has stopped sending.

| Metric | Meaning |
| --- | --- |
| `mail_outbox_pending_count` | Number of waiting jobs |
| `mail_outbox_retry_count` | Jobs waiting for retry |
| `mail_outbox_oldest_pending_age_seconds` | Age of oldest waiting job |
| `mail_outbox_claimed_count` | Jobs currently leased |
| `mail_outbox_expired_lease_total` | Number of expired leases |
| `mail_outbox_submit_total` | SMTP attempts by outcome |
| `mail_outbox_submit_duration_seconds` | Submission latency |
| `mail_outbox_failure_total` | Failures by category |
| `mail_outbox_unknown_outcome_total` | Ambiguous SMTP outcomes |
| `mail_outbox_permanent_failed_count` | Jobs needing intervention |
| `mail_outbox_provider_throttle_total` | Throttling |
| `mail_outbox_attachment_read_failure_total` | Attachment read errors |
| `mail_outbox_delivery_feedback_total` | Delivered/bounced events |

Metric labels can include provider, purpose, error category, or account class. Do not use recipient emails, full subjects, or tokens as labels due to privacy and cardinality.

### Recommended alerts

- Oldest pending age exceeds SLA, especially for security emails.
- SMTP AUTH/TLS failures increase.
- Throttling, retries, or `UNKNOWN_OUTCOME` spike sharply.
- Expired leases increase after a deployment.
- Workers fail to poll successfully for an extended period.
- Attachment storage becomes unreadable.
- Permanent failures rise.
- Outbox table grows rapidly and cleanup is not running.
- Provider feedback fails to map back to jobs.

Do not count total rows alone: a table retaining lots of historical `SUBMITTED` rows can be large yet healthy, whereas a few `PENDING` jobs stuck for hours are alarming.

## 34. End-to-end correlation

A mail job can be traced across:

~~~mermaid
flowchart LR
    A["Business event"] --> B["DB transaction"]
    B --> C["Outbox job"]
    C --> D["Worker attempt"]
    D --> E["SMTP provider"]
    E --> F["Delivery feedback"]
~~~

Example structured log:

~~~text
businessEventId: order-981
mailJobId: mail-981
attemptId: attempt-2
tenantId: tenant-42
purpose: TRANSACTIONAL
senderProfileId: tx-tenant-42
providerId: relay-a
outcome: SUBMITTED
~~~

Log internal IDs and states; do not log full MIME messages, tokens, or credentials.

The API can return `202 Accepted` once **the outbox has committed**, meaning the send request has been durably accepted. Never promise delivered when it has only been enqueued.

## 35. Retention, cleanup, and sensitive data

The outbox and attempt history will grow over time. Policies are needed:

- How long to keep `SUBMITTED` jobs for audit and feedback reconciliation?
- How long to keep `FAILED_PERMANENT` jobs for operations?
- When are payloads containing PII protected and purged?
- Are attachments still needed for retries or resends?
- How should a file referenced by multiple jobs be cleaned up?
- Will late-arriving provider webhooks still have ID mappings?
- Should historical attempts be archived to cheaper storage?
- Does cleanup impact claim transactions/queries?

Do not delete rows immediately after SMTP acceptance if reconciliation and auditing are required, yet do not retain body/recipient PII indefinitely either.

A cleanup task should consider terminal status, retention, active references, and per-tenant data regulations.

## 36. When does the outbox database need optimization?

Common issues at high throughput:

- Slow due-job queries from inadequate indexes.
- Large number of historical rows.
- Claim contention.
- Repeated scanning of retry rows not yet due.
- Cleanup creating many dead tuples.
- Business writes and SMTP workers competing for I/O.
- One marketing tenant dominating the backlog.

Options:

1. Index on status and `next_attempt_at`.
2. Reasonable batch claims, fairness by tenant/purpose.
3. Archive completed rows.
4. Separate active jobs and history tables when justified.
5. Partial indexes/partitioning if supported by the database.
6. CDC relay and broker when throughput demands it.
7. Rate-limit admission and workers.

Do not build a complex CDC architecture for a few hundred emails per day when DB polling works well. Correct transactions and idempotency matter more than premature optimization.

## 37. Testing transaction atomicity

An integration test must prove:

~~~text
BEGIN
  UPDATE order
  INSERT mail_outbox
COMMIT
=> Both order update and outbox job exist together.

BEGIN
  UPDATE order
  INSERT mail_outbox
ROLLBACK
=> Neither exists as a new change.
~~~

Rollback test example:

~~~java
@Test
void rollbackDoesNotLeaveMailIntent() {

    assertThrows(
            BusinessRuleException.class,
            () -> service.performFailingOrderFlow(
                    orderId
            )
    );

    assertFalse(
            outboxRepository.existsByBusinessEventId(
                    orderId.toString()
            )
    );
}
~~~

`performFailingOrderFlow` is an illustrative use case/test seam. Use a real database transaction rather than mocking repositories and inferring atomicity.

If the test is wrapped in `@Transactional` and fixtures have not committed, a worker running on another thread will not see the job. When testing the dispatcher, commit fixtures per contract.

## 38. Testing duplicate requests and idempotency

A domain event may be received twice. Test:

~~~java
@Test
void duplicateOrderEventCreatesOneMailJob() {

    service.confirmOrder(orderId, actor);
    service.confirmOrder(orderId, actor);

    assertEquals(
            1L,
            outboxRepository.countByIdempotencyKey(
                    expectedKey
            )
    );
}
~~~

Beyond sequential checks, test races: two threads/processes inserting the same key concurrently. The DB unique constraint protects against `SELECT exists` followed by both inserting.

This only verifies **enqueue idempotency**. It does not prove SMTP cannot send duplicates after a crash.

An intentional resend request requires a new intent/key and corresponding auditing/authorization.

## 39. Testing workers with an SMTP test server

You can use GreenMail or Mailpit:

~~~text
Committed mail_outbox row
  -> worker claim
  -> MailComposer
  -> JavaMailSender
  -> test SMTP server
  -> assertions MIME + DB state
~~~

Required assertions:

- Due `PENDING` jobs are claimed.
- Test server receives the right From, To, Subject, and correlation ID.
- When relay accepts, worker writes `SUBMITTED`.
- Terminal jobs are not polled again.
- Transient errors transition to `RETRY` and set `nextAttemptAt`.
- Permanent errors do not retry forever.
- Attachments remain available and readable.
- Expired leases can be reclaimed.
- Stale completion tokens cannot update the DB.
- Each test checks only its own messages.

Do not use production inboxes; parallel tests should have isolated SMTP servers or correlation namespaces.

## 40. Crash windows and fault injection

Faults can be simulated at critical boundaries:

| Fault point | Behavior to verify |
| --- | --- |
| Business update before outbox insert | Rollback leaves no half-finished state |
| Outbox insert before commit | No durable job on rollback |
| Commit before poll | Job remains waiting |
| Claim before SMTP | Lease expiry allows reclaim |
| During SMTP send | Classified as transient/unknown |
| SMTP accepted before status update | Job may be resent |
| After status update | Not polled again |
| Old worker using stale lease token | DB update fails |
| File missing before retry | Storage error is classified |
| Credential rotation | Worker uses approved secret version |

A typical test:

~~~text
Fake SMTP sender records one submission.
Simulate worker crash before markSubmitted.
Lease expires and job is reclaimed.
New worker resends; fake sender records second submission.
~~~

This result reflects the real system boundary: the DB outbox and SMTP relay share no joint atomic commit. Tests should not hide duplicates by deleting messages from the capture.

## 41. Testing concurrent multi-worker claiming

Two workers pointing to the same test database:

~~~text
Worker A claims batch of 10
Worker B claims batch of 10
~~~

Verify:

- The same job does not sit under two valid active leases.
- Worker B can claim other rows while A locks one row.
- Expired leases are reclaimed with a new token.
- Stale completion tokens update 0 rows.
- Jobs do not stay stuck `CLAIMED` indefinitely.
- `RETRY` jobs are not claimed before their deadline.
- Batches do not exceed execution capacity.
- Priority jobs are not starved by bulk mail.

A mock repository cannot prove transaction locks/`SKIP LOCKED` work under real contention. Use a test database matching production.

## 42. Testing retries and time

Do not make tests sleep for minutes just to verify exponential backoff. Inject a `Clock`:

~~~java
Clock testClock =
        Clock.fixed(
                Instant.parse(
                        "2026-11-12T00:00:00Z"
                ),
                ZoneOffset.UTC
        );
~~~

Test cases:

- Retry delay increases with attempt count.
- Jitter stays within bounds.
- Maximum age/attempts are enforced.
- Expired OTP/password reset tokens are canceled.
- Recipient unsubscribes before marketing send.
- Hard size rejects do not retry with the same payload.
- Unknown outcomes are logged and handled per policy.
- Workers do not claim before `nextAttemptAt`.
- Graceful shutdown stops accepting new jobs.

## 43. Common design mistakes

### 43.1. Calling SMTP inside @Transactional

SMTP does not roll back with the DB and can hold DB locks during slow network calls.

### 43.2. Relying solely on an AFTER_COMMIT listener

A crash after commit before the listener runs can lose emails if there is no durable outbox.

### 43.3. Relying solely on @Async and an in-memory queue

Unstarted jobs can be lost when the JVM restarts.

### 43.4. Writing outbox with a separate REQUIRES_NEW

The outbox can commit even if the business transaction rolls back.

### 43.5. No idempotency key

Duplicate HTTP requests/webhooks create multiple mail intents.

### 43.6. Treating a unique key as exactly-once SMTP

A crash after relay acceptance can still cause a resend.

### 43.7. Holding the claim transaction across mailSender.send

Causes lock contention and transaction timeouts.

### 43.8. No lease expiration

Worker crashes leave jobs stuck.

### 43.9. No fencing token

An old worker can overwrite status after losing its lease.

### 43.10. Overly short lease

Jobs get reclaimed while the previous SMTP attempt is still running.

### 43.11. Retrying all error types the same way

Hard size, invalid sender, AUTH failures, and timeouts need different policies.

### 43.12. No backoff/jitter

Provider outages cause retry storms.

### 43.13. Not classifying unknown outcomes

Makes auditing and duplicate handling difficult.

### 43.14. Storing Base64 PDFs in the outbox

Bloats DB and heap memory.

### 43.15. Deleting attachments before retries finish

Workers cannot find the file.

### 43.16. Using the latest template without a version policy

Delayed emails end up with content differing from the original intent.

### 43.17. Not rechecking consent/tenant

Can send to unsubscribed users or suspended tenants.

### 43.18. Bulk mail monopolizing all workers

Security emails miss SLAs.

### 43.19. Claiming more jobs than executor capacity

Leases expire before execution, increasing reclaims and duplicates.

### 43.20. Not monitoring backlog age

Long outages go unnoticed while the API still returns accepted.

### 43.21. Treating SUBMITTED as DELIVERED

Relay acceptance does not guarantee inbox delivery.

### 43.22. Cleaning up outbox too early

Loses audit trails and provider feedback mappings.

## 44. Scenario questions

**Q1.** Payment DB commit succeeds during an SMTP outage. How does the outbox help?

The committed job remains in the DB for workers to retry.

**Q2.** Transaction rolls back after inserting into the outbox in the same transaction. Does the job exist?

No, both business state and outbox roll back.

**Q3.** SMTP accepts, then worker crashes before marking SUBMITTED. Can it send twice?

Yes, this is the fundamental crash window.

**Q4.** The @Async executor is killed while tasks are waiting. Are jobs durable?

Not by default. A durable outbox is required.

**Q5.** Two workers poll PENDING simultaneously; how do we prevent duplicate claims?

Atomic DB claiming with locking/conditional updates, leases, and fencing.

**Q6.** An old worker loses its lease and still writes SUBMITTED. What prevents it?

Completion checks the lease token, though the external SMTP side effect may already have occurred.

**Q7.** Provider returns hard message too large. Should we retry as-is?

No, reduce size or change approach.

**Q8.** Does an SMTP timeout after DATA guarantee it wasn't sent?

No, it may be an unknown outcome.

**Q9.** A password reset job waits until the token expires. Should it be sent?

Recheck TTL and cancel per security policy.

**Q10.** Attachment is in local `/tmp`, retried on another pod. Is that okay?

Unlikely; use durable storage accessible by workers.

**Q11.** Tenant A's marketing delays Tenant B's security mail. Fix?

Quotas, priorities, fair scheduling, and reserved capacity.

**Q12.** Can an AFTER_COMMIT listener wake the dispatcher?

Yes, though the outbox row must still be persisted in case the signal is lost.

**Q13.** Does HTTP returning 202 right after outbox commit mean delivered?

No, it only means the send request was durably accepted.

**Q14.** One message has multiple recipients and SMTP partially accepts. What to do?

Track per recipient and avoid duplicate retries; consider splitting one job per recipient.

**Q15.** SMTP credentials were rotated but an old sender cache still uses the old password. What to do?

Invalidate/recreate based on credential version.

**Q16.** Does a rollback test using only mock repositories prove atomicity?

No. A real DB transaction integration test is required.

**Q17.** Does a fixed Message-ID guarantee exactly-once SMTP?

No, providers/receiving servers have no universal obligation to deduplicate.

**Q18.** A worker claims 500 jobs when only 5 slots are free. What's the risk?

Leases expire before execution, causing reclaims and potential duplicates.

## 45. Mental model

~~~mermaid
flowchart TD
    A["Business event"] --> B["Authorization + business validation"]
    B --> C["BEGIN transaction"]
    C --> D["Update business state"]
    C --> E["INSERT outbox unique intent"]
    D --> F["COMMIT"]
    E --> F
    F --> G["Worker claim due job"]
    G --> H["Short DB transaction + lease token"]
    H --> I["Resolve sender / recipient / template / storage"]
    I --> J["JavaMailSender.send"]
    J --> K{"SMTP result"}
    K -->|"Accepted"| L["SUBMITTED"]
    K -->|"Transient"| M["RETRY + backoff"]
    K -->|"Permanent"| N["FAILED_PERMANENT"]
    K -->|"Unknown"| O["Reconcile / retry"]
    M --> G
    O --> G
    L --> P["Provider delivery feedback"]
~~~

Principles to remember:

1. **Business state and outbox are written in the same transaction** to avoid dual-write gaps.
2. **Never call SMTP inside a business transaction** expecting email to roll back.
3. **`@Async` does not create durability**; the source of truth must be a durable job store.
4. **Unique idempotency keys prevent duplicate enqueues**, not all duplicate SMTP sends.
5. **Workers claim atomically**, using leases and DB fencing.
6. **Commit claims before network I/O**, never holding DB locks across SMTP.
7. **Leases need proper expiration/heartbeats** for crash recovery.
8. **SMTP accepted differs from delivered**; timeouts can be unknown outcomes.
9. **Outbox does not guarantee exactly-once external side effects**; duplicates must be tolerated/reconciled.
10. **Retries need backoff, jitter, cutoffs, and failure classification**, never looping infinitely on hard errors.
11. **Payloads/templates/recipients need snapshot/version policies** for delayed jobs.
12. **Attachments use durable storage**, with the outbox holding references instead of large Base64 bytes.
13. **Recheck tenant, sender identity, consent, and token validity at send time** per use case.
14. **Multi-tenant systems need fairness/quotas**, never letting bulk mail delay security mail.
15. **Monitoring backlog age, failures, lease expiry, and unknown outcomes** is essential.
16. **Provider feedback must be verified and mapped to the right job/tenant**.
17. **Test transactions, concurrency, and crash windows** using isolated databases and SMTP test servers.

In Spring Framework Mail, the transactional outbox is **the durable commitment boundary between a business decision and an email send intent**. When the transaction commits, the work remains to be processed; when it rolls back, no corresponding send intent exists. Beyond that boundary, SMTP can still be slow, fail, send duplicates, or produce uncertain results. A sound production architecture manages these limits with idempotency, worker leases, appropriate retries, durable storage, authorization, auditing, and observability so email delivery stays reliable even when infrastructure fails.




