# Replayability and Failed Record Handling in Spring Framework Mail

In an event-driven email-sending system, calling \`JavaMailSender.send(...)\` is only one step in a message's lifecycle. An order event may have been written to the database before the worker could send the email; SMTP may temporarily refuse connections; a template may fail; or the relay may have accepted the email while the connection dropped before the application received the final response. If the system only logs and moves on, messages can vanish. If it retries or replays blindly, recipients can receive multiple identical emails.

**Replayability is the ability to bring a persisted record back into the processing flow under a controlled policy.** It helps recover failed messages, reprocess after fixing configuration or templates, and support operations while preserving history. Replay must be distinguished from automatic retries: a retry is the next scheduled attempt under a delivery policy; a replay is typically an intentional action returning a failed or quarantined record to processing.

In Spring Framework Mail, JavaMailSender provides neither durable storage for failed emails nor automatic message replay. The application must store the send request, status, attempt count, error reason, and data needed to rebuild the email. For notifications tied to business transactions, a transactional outbox is a common design pattern.

## 1. What problem does replay solve?

Consider the order-creation flow:

1. The user places an order.
2. The application saves the order in the database.
3. The application needs to send a confirmation email.
4. SMTP is temporarily unavailable.

If the application simply tries to send the email inside the request and drops the exception, the order can still be created while the confirmation email is lost. Operators have no reliable record to know which messages must be reprocessed.

A replay-capable system persists the send request alongside business data. Workers can retry once SMTP recovers. If a failure stemmed from a missing template, operators can fix the template and replay the exact failed records. If the recipient address was invalid, the record can be routed to a data-correction state or closed per policy.

### Scenarios commonly needing replay

- SMTP relay temporarily goes down or refuses connections.
- Provider enforces rate limits and requests trying again later.
- Worker stops mid-processing and the record's lease expires.
- Templates or configuration are fixed after a batch of messages failed.
- A software bug in the mail dispatcher has been resolved.
- Records were moved to dead-letter for investigation and are now eligible for reprocessing.
- An operational task needs to selectively replay a set of records after an incident is resolved.

Replay should not be used to resend every already-succeeded email merely because you want to re-run an event. Resending email is an action with external side effects that cannot be recalled once accepted by an SMTP relay.

## 2. Distinguishing retry, replay, and resend

These three concepts are often used interchangeably, yet carry distinct operational meanings:

| Concept | Meaning | Example |
| --- | --- | --- |
| Retry | Worker automatically performs the next attempt on a defined schedule | SMTP returns a temporary error; record is retried after 2 minutes |
| Replay | Returning a stored or failed record to processing under controlled rules | Operator replays a DEAD_LETTER record after fixing a template |
| Resend | Creating an intentional new delivery to the recipient | User requests resending a receipt |
| Re-drive | Moving messages from a dead-letter queue or error store back to the main processing queue | Returning a batch of investigated messages to the primary queue |
| Event replay | Replaying business events or event logs for consumers to reprocess | Re-reading an OrderPlaced event from an event store |

A retry usually preserves the notification ID and increments the attempt count. Replay may continue the same notification ID or create a new delivery generation depending on policy. A resend is usually a new business request with a new ID and its own reason. Event replay can trigger many consumers beyond email, so it must not be treated as a simple resend operation.

### Why not replay business events indiscriminately?

Suppose \`OrderPlaced\` is handled by multiple consumers:

- Email confirmation.
- Inventory deduction.
- Invoice generation.
- Sending data to analytics.

If an operator replays the entire event just to resend an email, other side effects may run a second time. Instead, replay **the email delivery record** or a dedicated command for the target notification.

Event replay is only appropriate when every consumer is idempotent and event replay is an intentionally designed behavior. Never use the event bus as a "resend email" button if that event also drives other business operations.

## 3. Persisting email send requests durably with a transactional outbox

A transactional outbox writes the email send-request record in the same database transaction as the business change. This avoids the scenario where an order commits while the email send request is never saved.

Example:

~~~java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(createOrder(command));

    EmailOutboxMessage message = EmailOutboxMessage.pending(
            UUID.randomUUID(),
            "ORDER_CONFIRMED",
            order.getCustomerId(),
            order.getId());

    outboxRepository.save(message);
    return order;
}
~~~

If the transaction commits, both the order and the outbox record exist. If the transaction rolls back, both roll back. An independent worker reads the outbox and sends emails after commit.

Overall flow:

~~~mermaid
flowchart TD
    A["Business command"] --> B["Database transaction"]
    B --> C["Save domain data"]
    B --> D["Save email outbox record"]
    C --> E["Commit"]
    D --> E
    E --> F["Outbox worker"]
    F --> G["Render email"]
    G --> H["JavaMailSender"]
    H --> I["Update delivery state"]
    I --> J{"Failure?"}
    J -- "Temporary" --> K["Retry schedule"]
    J -- "Permanent" --> L["Failed / dead-letter"]
    K --> F
    L --> M["Operator review and replay"]
~~~

An outbox does not make SMTP part of the database transaction. It ensures **the send requirement is stored durably with business changes**. Sending externally remains an independent operation that can fail or produce uncertain outcomes.

### Do not send SMTP inside the business transaction

Avoid doing this:

~~~java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(createOrder(command));
    mailSender.send(buildConfirmation(order));
    return order;
}
~~~

If SMTP takes several seconds, the database transaction is held open across network waits. If SMTP accepts the email and the database then rolls back, the recipient can receive a confirmation for a non-existent order. If the database commits and the process stops before sending, the email can be lost.

Write the outbox inside the transaction and let a worker send after commit. Never hold row locks or database transactions open while calling SMTP.

## 4. Designing outbox records for replayability

A record must hold enough data to identify the message, control state, and reproduce content per policy. Model example:

~~~java
public enum EmailDeliveryStatus {
    PENDING,
    PROCESSING,
    RETRY_PENDING,
    SUBMITTED,
    SUBMISSION_UNKNOWN,
    FAILED_PERMANENT,
    DEAD_LETTER,
    SUPPRESSED,
    CANCELLED,
    EXPIRED
}
~~~

A record can contain:

| Field | Purpose |
| --- | --- |
| id | Unique ID of the notification |
| idempotency_key | Key identifying the same business request |
| event_type | Source event type, e.g., ORDER_CONFIRMED |
| recipient_id | Recipient ID in the system |
| recipient_snapshot | Address resolved at creation time if policy requires |
| payload | Minimum data to render the email |
| template_key | Name of the template to use |
| template_version | Selected template version if content reproduction is needed |
| status | Current state |
| attempts | Number of worker attempts |
| next_attempt_at | Earliest timestamp allowed for the next attempt |
| lease_owner | Worker currently holding processing ownership |
| lease_until | Lease expiration timestamp |
| last_error_code | Normalized error code |
| last_error_at | Timestamp of the most recent error |
| created_at / updated_at | Management timestamps |
| expires_at | Processing deadline, useful for time-sensitive messages |

You do not necessarily need to store full rendered HTML. You can store payload and template key/version and render when the worker processes. For legal or transactional notices requiring exact reproduction, store a rendered snapshot or reference to a versioned artifact under data protection policies.

### Storing attempt history separately

A single \`attempts\` and \`last_error_code\` column shows only the latest state. When investigation is needed, record per-attempt history:

~~~java
public record EmailDeliveryAttempt(
        UUID id,
        UUID outboxMessageId,
        int attemptNumber,
        Instant startedAt,
        Instant finishedAt,
        String outcome,
        String errorCode,
        String providerMessageId
) {
}
~~~

An attempt history table can record:

- Start/end timestamps.
- Processing worker or instance.
- Outcome: SUBMITTED, RETRYABLE_FAILURE, PERMANENT_FAILURE, or UNKNOWN.
- Normalized error code.
- Provider message ID if available.
- Correlation ID.

Never store SMTP passwords, tokens, full email bodies, or attachment bytes in attempt history. Keep enough data for tracing without turning log tables into uncontrolled email copies.

## 5. State model and transitions

States must clearly show whether a record is waiting, being processed, submitted, temporarily failing, or needing intervention.

~~~text
PENDING
   |
   v
PROCESSING
   |
   +---- SMTP accepted ------------> SUBMITTED
   |
   +---- Temporary failure --------> RETRY_PENDING
   |                                    |
   |                                    v
   |                                 PROCESSING
   |
   +---- Permanent failure --------> FAILED_PERMANENT
   |                                    |
   |                                    v
   |                                 DEAD_LETTER
   |                                    |
   |                                    v
   |                               Manual replay
   |                                    |
   |                                    v
   |                                  PENDING
   |
   +---- Unknown SMTP outcome ------> SUBMISSION_UNKNOWN
   |
   +---- Preference disabled -------> SUPPRESSED
   |
   +---- Expired/cancelled ----------> EXPIRED / CANCELLED
~~~

Not every state is needed in every project. What matters is not lumping temporary failures, permanent failures, and uncertain SMTP outcomes into a single generic FAILED state.

### State meanings

| State | Meaning | Typical action |
| --- | --- | --- |
| PENDING | Persisted, not yet claimed by a worker | Waiting to be processed |
| PROCESSING | Worker holds lease | Wait for worker completion or lease expiration |
| RETRY_PENDING | Recoverable failure, scheduled for retry | Worker processes when due |
| SUBMITTED | SMTP relay accepted message per received response | Do not automatically resend |
| SUBMISSION_UNKNOWN | Unknown whether relay received it | Reconcile or handle per duplicate policy |
| FAILED_PERMANENT | Error requiring data/config fix before retrying | Investigate |
| DEAD_LETTER | Record exceeded retry policy or quarantined | Operator review |
| SUPPRESSED | Not sent per preference/consent/suppression policy | Keep audit, do not retry |
| CANCELLED | Cancelled before submission | Do not send |
| EXPIRED | Past send deadline | Do not send unless a new business decision is made |

### Do not transition states arbitrarily

Examples:

- SUBMITTED should not return to PENDING just because an operator wants to "retry to be sure."
- SUPPRESSED should not be replayed if consent is still disabled.
- FAILED_PERMANENT should return to PENDING only after the root cause is fixed with a replay audit.
- PROCESSING with an expired lease can be reclaimed, but check whether the previous attempt already sent via SMTP.
- SUBMISSION_UNKNOWN needs its own policy; automatic retries can send duplicates.

Use a state transition service to validate current state and transition rules rather than letting multiple places update status directly.

## 6. Classifying errors to decide retries

Not every error should be retried. Distinguish temporary failures, permanent failures, and uncertain outcomes.

| Error group | Example | Action |
| --- | --- | --- |
| Temporary connectivity | Connection timeout, SMTP host temporarily unavailable | Retry with backoff |
| SMTP temporary response | Server returns 4xx code | Typically retry per policy/provider |
| Rate limit | Provider enforces rate limit or short-term quota | Slow down, retry later |
| Authentication | Wrong username/password or expired credentials | Stop blind retries, fix secret |
| Recipient permanent failure | Invalid address or mailbox permanently rejected | FAILED_PERMANENT or suppression |
| Sender/relay policy | Sender not allowed to relay | Fix configuration or permissions |
| Template/resource error | Template not found, parse error, missing resource | Fix artifact/template then replay |
| Invalid business data | Payload missing recipient or required field | Fix data via workflow, do not retry blindly |
| MIME construction error | Unreadable attachment/resource | Fix data or resource |
| SMTP outcome unknown | Connection dropped after sending DATA, no final response received | Reconcile or handle per duplicate policy |

### SMTP 4xx and 5xx

SMTP 4xx responses typically indicate temporary errors; 5xx typically indicate permanent errors for the current request. This is a useful classification rule, yet the application must also inspect context and provider documentation. Some providers have custom codes or specific quota policies.

Do not inspect exception message strings alone to decide retries. Spring Mail may wrap Jakarta Mail exceptions; normalize errors at the transport adapter layer, preserve causes, and extract response codes when reliably provided by the library.

### Pre-send errors vs. post-send errors

If a template fails to render, the email was definitely not submitted via SMTP. This is typically recoverable and safe to replay once fixed.

If the SMTP connection drops after the client sent DATA content but before receiving the final response, the application cannot be sure whether the server accepted the message. This differs from a timeout before a connection was established. Distinguish them to avoid duplicate sends.

## 7. Automatic retries with exponential backoff

A retry policy must bound attempt counts, wait intervals, and message deadlines. A common formula:

~~~text
delay = min(maxDelay, initialDelay * 2^attempt) + jitter
~~~

Example:

| Attempt | Illustrative wait time |
| --- | --- |
| First | Processed immediately when worker claims |
| Attempt 2 | 30 seconds |
| Attempt 3 | 2 minutes |
| Attempt 4 | 10 minutes |
| Attempt 5 | 30 minutes |

Jitter prevents workers from retrying in lockstep right after an outage. Adjust values based on SLAs, providers, and email urgency.

### Persisting retry time on the record

No need to sleep threads with \`Thread.sleep(...)\`. The worker can update:

~~~text
status = RETRY_PENDING
attempts = attempts + 1
next_attempt_at = now + calculated_delay
last_error_code = SMTP_TEMPORARY
~~~

Then the scheduler/queue only claims due records. This avoids tying up worker threads while waiting and makes retry state observable.

### Retry policies by message type

| Email type | Suggested policy |
| --- | --- |
| OTP or reset link | Short TTL, bounded attempts; retry only while challenge remains valid |
| Order confirmation | Durable retry; never drop silently |
| Receipt/invoice | Retry per SLA, track errors to terminal state |
| Newsletter | Enforce expiry, check unsubscribe before each send |
| Promotions | Enforce expiry, frequency cap, and suppression |

Do not retry optional emails after a campaign expires. Do not retry OTPs after the challenge expires. For mandatory transactional notifications, you may retry longer while alerting when SLAs are breached.

### Retry limits and dead-lettering

After max attempts or on permanent failure, a record can transition to DEAD_LETTER. Do not delete the record. Dead-letter is a quarantine area to investigate, fix root causes, and decide whether to replay or close the record.

Dead-letter records should retain:

- Message ID and category.
- Template key/version.
- Attempt count and latest timestamp.
- Normalized error code.
- Correlation ID.
- Relevant provider details if available.

## 8. Claiming records and preventing concurrent sends by multiple workers

With multiple application instances, two workers could both read a PENDING record and both send the email. An atomic claim mechanism is required.

A common approach is leasing:

1. Worker claims the record and writes PROCESSING, lease_owner, lease_until.
2. Claim transaction commits.
3. Worker calls SMTP outside the transaction.
4. Worker updates the outcome and clears the lease.
5. If the process stops, the lease expires and the record can be reprocessed per policy.

~~~mermaid
sequenceDiagram
    participant W1 as Worker A
    participant DB as Outbox DB
    participant SMTP as SMTP
    participant W2 as Worker B

    W1->>DB: Claim record + lease
    DB-->>W1: PROCESSING
    W1->>SMTP: Send message
    Note over W1,SMTP: Network call outside DB transaction
    SMTP-->>W1: Accepted
    W1->>DB: Mark SUBMITTED
    W2->>DB: Claim due records
    DB-->>W2: Record already claimed, skip
~~~

### Do not hold transactions or row locks while calling SMTP

Avoid putting all of the following inside one `@Transactional` method:

~~~java
@Transactional
public void process(EmailOutboxMessage message) {
    message.markProcessing();
    repository.save(message);
    mailSender.send(buildMimeMessage(message));
    message.markSubmitted();
}
~~~

The transaction can hold locks while the network is slow. If SMTP succeeds while the database rolls back, the record can remain in its old state and be resent. Split into short transactional steps:

- Claim record in a transaction.
- Commit claim.
- Send SMTP outside any transaction.
- Update outcome in a new transaction.

### Leases and handling dead workers

Leases should exceed expected processing time yet remain bounded. For emails with large attachments or slow providers, lease renewal may be needed while the worker stays active. Once a lease expires, another worker can reclaim the record.

However, an expired lease does not prove SMTP never received the email. If an old worker paused after SMTP already accepted, a new worker could resend. Thus, leases prevent normal concurrent processing yet **do not by themselves guarantee exactly-once**.

## 9. Example record-claiming repository

Locking details depend on the database. With PostgreSQL, \`FOR UPDATE SKIP LOCKED\` in a transaction lets multiple workers claim disjoint sets of records:

~~~sql
SELECT id
FROM email_outbox
WHERE status IN ('PENDING', 'RETRY_PENDING')
  AND next_attempt_at <= CURRENT_TIMESTAMP
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 50;
~~~

After selecting, update the claimed IDs to PROCESSING, set lease_owner and lease_until, and commit. \`SKIP LOCKED\` is database-specific syntax; on other database engines, use equivalent claiming mechanisms such as optimistic locking, conditional updates, or a queue broker.

An illustrative repository interface:

~~~java
public interface EmailOutboxRepository
        extends JpaRepository<EmailOutboxEntity, UUID> {

    @Query(value = """
            SELECT *
            FROM email_outbox
            WHERE status IN ('PENDING', 'RETRY_PENDING')
              AND next_attempt_at <= CURRENT_TIMESTAMP
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT :batchSize
            """, nativeQuery = true)
    List<EmailOutboxEntity> lockDueMessages(
            @Param("batchSize") int batchSize);
}
~~~

This is a PostgreSQL-oriented example. Implement claiming/updating inside the same transaction, set leases, and ensure selected records are no longer eligible for other workers. Check your database's syntax and limitations before adopting.

## 10. Worker sending email and updating status

Separate claimer, dispatcher, and sender components so transaction boundaries stay clear.

### Claim step

~~~java
@Service
public class EmailOutboxClaimer {

    private final EmailOutboxRepository repository;

    public EmailOutboxClaimer(EmailOutboxRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public List<ClaimedEmail> claimBatch(
            String workerId,
            int batchSize,
            Instant leaseUntil) {

        List<EmailOutboxEntity> due =
                repository.lockDueMessages(batchSize);

        return due.stream()
                .map(entity -> {
                    entity.markProcessing(workerId, leaseUntil);
                    return ClaimedEmail.from(entity);
                })
                .toList();
    }
}
~~~

The claim transaction ends when the method returns through the Spring proxy. The dispatcher invokes this method from another bean, then executes SMTP outside the transaction.

### Dispatch step

~~~java
@Component
public class EmailOutboxScheduler {

    private final EmailOutboxClaimer claimer;
    private final EmailDispatcher dispatcher;

    public EmailOutboxScheduler(
            EmailOutboxClaimer claimer,
            EmailDispatcher dispatcher) {
        this.claimer = claimer;
        this.dispatcher = dispatcher;
    }

    @Scheduled(fixedDelay = 1000)
    public void dispatchBatch() {
        List<ClaimedEmail> batch = claimer.claimBatch(
                "mail-worker-1",
                50,
                Instant.now().plusSeconds(60));

        for (ClaimedEmail message : batch) {
            dispatcher.dispatch(message);
        }
    }
}
~~~

Worker IDs must be unique per instance/process—never hardcode a shared value across all replicas. For example, combine hostname/pod ID with a process UUID. Batch size, poll delay, and lease duration should be configurable.

### Send and record-outcome step

~~~java
@Service
public class EmailDispatcher {

    private final EmailRenderer renderer;
    private final JavaMailSender mailSender;
    private final EmailOutboxStateService stateService;

    public EmailDispatcher(
            EmailRenderer renderer,
            JavaMailSender mailSender,
            EmailOutboxStateService stateService) {
        this.renderer = renderer;
        this.mailSender = mailSender;
        this.stateService = stateService;
    }

    public void dispatch(ClaimedEmail record) {
        try {
            MimeMessage message = renderer.render(record);
            mailSender.send(message);
            stateService.markSubmitted(record.id());
        } catch (MailException exception) {
            stateService.recordFailure(
                    record.id(),
                    classify(exception));
        } catch (MailContentException exception) {
            stateService.markPermanentFailure(
                    record.id(),
                    "CONTENT_ERROR");
        }
    }
}
~~~

This is an illustrative structure; `stateService` methods should open their own transactions. In real applications, preserve exception causes, classify transport errors carefully, and include a branch for uncertain SMTP outcomes. Never catch every RuntimeException and turn it into a generic temporary failure.

### Note on transaction proxies

In Spring, calling a `@Transactional` method from another method on the same instance (self-invocation) normally bypasses the transaction proxy. Therefore, split claimer and state services into separate beans or use explicit transaction mechanisms. Never assume annotations within the same class automatically create new transactions.

## 11. Handling uncertain SMTP outcomes

A difficult case:

1. Application connects to SMTP.
2. Application transmits the DATA section.
3. SMTP relay accepts the email.
4. Connection drops before the client receives the final response.

The application cannot know for sure whether the email was received. If it marks FAILED and retries immediately, the recipient may receive two copies. If it marks SUBMITTED, the email may be lost if the relay never received it.

There is no general way to achieve exactly-once when calling SMTP directly because the database and SMTP do not share one transaction.

### SUBMISSION_UNKNOWN status

For errors occurring at an uncertain stage, you can record:

~~~text
status = SUBMISSION_UNKNOWN
last_error_code = SMTP_FINAL_RESPONSE_MISSING
attempts = attempts + 1
~~~

Then:

- If the provider offers an API/event to look up message IDs, reconcile.
- If the provider supports idempotency keys, pass a stable key per notification.
- If verification is impossible, apply the business-accepted duplicate policy.
- For highly critical emails, route to manual review instead of retrying automatically right away.

### Does Message-ID prevent duplicates?

You can set a stable Message-ID to assist tracing:

~~~java
message.setHeader(
        "Message-ID",
        "<notification-" + notificationId + "@mail.example.com>");
~~~

However, Message-ID is not a mandatory SMTP idempotency mechanism. Providers or mailboxes may still accept two messages sharing the same Message-ID. Use it to correlate logs and provider events; never claim it guarantees deduplication.

## 12. Idempotency and preventing duplicate sends

A notification should have an idempotency key representing the business event and recipient:

~~~text
ORDER_CONFIRMED:order-184:customer-42
~~~

The database can place a unique constraint on `idempotency_key` to prevent creating multiple outbox records for the same request. Example:

~~~sql
CREATE UNIQUE INDEX uq_email_outbox_idempotency
ON email_outbox(idempotency_key);
~~~

If the same event is reprocessed, the application finds the existing record instead of creating an unintended new notification.

### Idempotency is not the same as SMTP deduplication

A unique constraint protects outbox record creation in the database. It cannot stop a provider from delivering two messages if the same record is submitted twice after an uncertain outcome.

Duplicates can be reduced by:

- Claiming records atomically.
- Using appropriate leases and heartbeats.
- Never resending SUBMITTED records.
- Keeping notification IDs stable.
- Using provider idempotency when available.
- Reconciling SUBMISSION_UNKNOWN.
- Storing attempt history.

Still, recognize that systems generally achieve **at-least-once processing** with duplicate potential in certain scenarios, rather than universal exactly-once delivery.

### Retry and replay with the same notification or a new one?

| Scenario | How to handle IDs |
| --- | --- |
| Temporary SMTP failure and not yet submitted | Keep notification ID, increment attempts |
| Template fixed and record definitely not submitted | Can replay same notification ID, record replay audit |
| SUBMISSION_UNKNOWN | Keep ID for reconciliation; do not create new record right away |
| User requests resending an already-SUBMITTED receipt | Create a new resend request linked to the old notification |
| Sending a new campaign | Create a new notification ID for the campaign |

Do not reset attempts to 0 just to make a record look brand new. If a new delivery generation is needed, store a separate generation/replay ID while keeping old history.

## 13. Replaying failed records after fixing root causes

A DEAD_LETTER record should not automatically return to PENDING just because someone clicked a replay button. First confirm the underlying error has been resolved.

Examples:

- Template not found: artifact/template has been properly deployed.
- Invalid recipient: address fixed or a valid business recipient supplied.
- SMTP authentication: SMTP secret/permissions restored.
- Attachment read error: resource restored and re-verified.
- Scanner unavailable: a CLEAN scan result exists for the exact file version.

### Replay workflow

1. Select records by notification ID or bounded search criteria.
2. Inspect category, recipient, template version, status, and attempt history.
3. Verify the record is not already SUBMITTED, or has an explicit resend decision.
4. Confirm the root cause has been fixed.
5. Re-check current consent/preferences, suppression, expiry, and recipient authorization.
6. Verify the payload and template version to be used.
7. Write an audit entry with operator, timestamp, reason, and replay generation.
8. Transition eligible records to PENDING or create a new delivery generation per policy.
9. Worker processes through the normal pipeline.
10. Monitor results and preserve previous attempt history.

### Replay is not arbitrarily editing every column

Do not let operators manually edit status, attempts, recipient, or payload directly in the database with ad-hoc SQL. Build a replay service with validation and auditing to enforce proper state transitions.

Internal API example:

~~~http
POST /internal/mail-outbox/{notificationId}/replay
Content-Type: application/json

{
  "reason": "SMTP credentials have been restored",
  "expectedStatus": "DEAD_LETTER"
}
~~~

This API needs authentication, role-based authorization, CSRF protection if using cookie sessions, rate limiting, and auditing. Never expose replay endpoints publicly to end users unless explicitly required by the business.

### Replay service example

~~~java
@Service
public class EmailReplayService {

    private final EmailOutboxRepository repository;
    private final ReplayAuditRepository auditRepository;
    private final EmailPolicyService policyService;

    public EmailReplayService(
            EmailOutboxRepository repository,
            ReplayAuditRepository auditRepository,
            EmailPolicyService policyService) {
        this.repository = repository;
        this.auditRepository = auditRepository;
        this.policyService = policyService;
    }

    @Transactional
    public void replay(
            UUID notificationId,
            String operatorId,
            String reason,
            EmailDeliveryStatus expectedStatus) {

        EmailOutboxEntity record = repository
                .findByIdForUpdate(notificationId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Record not found"));

        if (record.getStatus() != expectedStatus) {
            throw new IllegalStateException(
                    "Record status changed; refresh before replay");
        }

        if (record.getStatus() != EmailDeliveryStatus.DEAD_LETTER
                && record.getStatus() != EmailDeliveryStatus.FAILED_PERMANENT) {
            throw new IllegalStateException(
                    "Only failed records can be replayed by this operation");
        }

        policyService.assertReplayAllowed(record);

        record.scheduleReplay();
        auditRepository.save(ReplayAuditEntry.created(
                notificationId, operatorId, reason));
    }
}
~~~

This is an internal service example. \`findByIdForUpdate\` must lock the record inside the transaction; \`assertReplayAllowed\` must check category, recipient, consent, expiry, suppression, and business rules. \`scheduleReplay()\` must not delete attempt history or unexpectedly alter payloads. Replay reason and operator ID must be validated.

### Do not replay SUBMITTED via this API

If a record is already SUBMITTED, resending is a new resend request. Require a business reason and create a new notification linked to the original notification. This distinguishes "user-requested resend" from "recovering a failed delivery."

## 14. Controlled batch replay

After an SMTP outage or template bug, hundreds of DEAD_LETTER records may accumulate. Batch replay must restrict scope:

- Filter by a specific template key/version.
- Filter by classified and resolved errors.
- Filter by time window or campaign.
- Exclude SUBMITTED, SUPPRESSED, CANCELLED, EXPIRED, and unreconciled SUBMISSION_UNKNOWN records.
- Apply rate limits to avoid email bursts.
- Run a dry-run before executing.
- Audit batch ID, operator, filters, and selected record count.

### Dry-run

Dry-run only computes and displays:

- Count of eligible records.
- Count of excluded records and reasons.
- Breakdown by category/recipient domain/template version.
- Count of expired or already-submitted records.
- Total size / estimated send rate if attachments exist.

Dry-run modifies no state and never calls SMTP. After reviewing results, the operator can execute the replay for the defined batch.

### Never replay the entire error table

A command like "reset all FAILED to PENDING" is dangerous. It can:

- Resend messages that actually submitted while status update failed.
- Send optional emails to users who unsubscribed.
- Send expired OTPs.
- Send unfixed templates.
- Create traffic spikes against the SMTP provider.
- Replay messages for tenants or recipients that are no longer valid.

Batch replays must require filters, size limits, operator authorization, and auditing.

## 15. Handling failed records by root cause

Do not apply one generic replay action to every failure. The table below suggests actions:

| Root cause | Action before replay | Replayable? |
| --- | --- | --- |
| SMTP timeout before submit | Confirm provider recovered | Yes, per retry policy |
| SMTP 4xx | Follow Retry-After/quota and backoff | Yes |
| SMTP 5xx recipient | Check address and suppression | Only after fixing or new decision |
| SMTP AUTH failure | Fix credentials/permissions and verify connection | Yes |
| Template missing/parse error | Deploy fixed template and verify render | Yes if not yet submitted |
| Payload missing data | Fix data source per audit | Yes after confirming valid recipient/content |
| Unreadable attachment | Restore correct object, verify hash and re-scan | Yes |
| Consent withdrawn | Do not alter to send marketing | No; keep SUPPRESSED |
| Campaign expired | Create new campaign/resend if justified | Do not replay old campaign |
| SUBMISSION_UNKNOWN | Reconcile with provider or decide duplicate risk | Do not auto-replay immediately |
| SUBMITTED | Resend only via a new resend request | Not via failed-record replay |

### Fixed templates

If an error was caused by a template, the record may store the original template key and version. When replaying, decide whether to:

- Re-render with the latest approved template version.
- Render with the version originally bound to the notification.
- Create a new delivery generation explicitly noting the new version.

For routine transactional emails, using the fixed new template may be appropriate. For legal or audited content, changing templates can alter committed wording; establish a clear policy and record versions.

### Changed recipient data

If a recipient's email address changed after the notification was created, do not automatically use the new address for every replay. Decide whether to:

- Use the recipient snapshot from event creation time.
- Use the current verified address.
- Cancel the old notification and create a new one per business rules.

For OTP/reset links, never send an old token to a new address unless the challenge was designed for it. For invoices, the recipient address may need to match transaction records at issuance time.

## 16. Snapshot data, template versions, and reproducibility

Replays can happen hours or days after the event. Meanwhile, customer name, address, order total, or templates may have changed.

There are two ways to store payloads:

### Snapshot at event time

Store the required data when creating the notification:

~~~json
{
  "orderId": "ORD-184",
  "customerDisplayName": "An",
  "orderTotal": "1250000",
  "currency": "VND",
  "locale": "vi-VN"
}
~~~

The advantage is that replays can reproduce content close to event time. The drawback is that records contain personal/financial data needing protection and retention limits.

### Reference to current data

Store the aggregate ID and reload data when the worker runs. This shrinks payloads, yet emails may reflect current state instead of state at event time. If the order changed afterward, a replayed email may differ from what was originally expected.

### Choosing by business semantics

| Content | Typically suitable storage |
| --- | --- |
| Receipts/invoices | Snapshot or immutable transaction data |
| Current status updates | Can read latest state if content is defined that way |
| OTP/reset challenges | Store challenge reference with expiry; never log raw tokens |
| Newsletters/marketing | Store campaign/version and check current preferences at send time |
| Security alerts | Store minimal event data and clear recipient policy |

### Template versions

Storing template key and version tells you which template rendered a record. If only template key is stored, a post-deploy replay may silently use a new template without anyone noticing content changed.

A record can contain:

~~~text
template_key = order-confirmed
template_version = mail-templates-2026.11.12.3
payload_version = 2
~~~

If an old template version is no longer retained, the replay policy must allow upgrading the version or flagging for intervention. Never silently alter content for a message requiring exact reproduction.

## 17. Replay and recipient rights

A record validly created yesterday is not necessarily permitted to be sent today. Before replaying, re-check policies that can change:

- Has the recipient unsubscribed from optional emails?
- Is consent still valid for that campaign?
- Is the email address bounced/suppressed?
- Has the notification expired?
- Does the recipient still belong to the corresponding tenant or transaction?
- Is the recipient still authorized to receive that attachment or sensitive data?
- Does a data deletion or processing restriction request apply?

For mandatory transactional emails, do not apply the exact same boolean preference as marketing. Still, invalid addresses, hard bounces, or unauthorized recipients must be handled.

For optional emails, replays must respect preference state **at the time of sending**. Operators must never use replay to bypass unsubscribe/suppression rules.

## 18. Auditing and protecting operational actions

Replay has external impact, so controls are required:

- Which roles may view, replay, or cancel records.
- Requiring a mandatory reason for replay.
- Whether two-person approval is required for large batches.
- Which categories are prohibited from manual replay.
- Maximum records per batch.
- Rate limits and send windows.
- Handling rules for SUBMISSION_UNKNOWN.
- Auditing resends of already-sent messages.

An audit record can include:

| Field | Content |
| --- | --- |
| audit_id | Action ID |
| notification_id | Target record |
| action | REPLAY_REQUESTED, REPLAY_APPROVED, REPLAY_REJECTED, or CANCELLED |
| operator_id | Acting operator |
| reason | Human-readable justification |
| previous_status | Prior status |
| new_status | New status |
| replay_generation | Replay/generation number |
| occurred_at | Timestamp |
| correlation_id | Links logs and incidents |

Do not allow editing or deleting audit history through normal replay interfaces. Audits should also never store email bodies, tokens, or attachment contents.

### Permissions by action

| Role | Appropriate permissions |
| --- | --- |
| Support | View summary status and sanitized error codes |
| Mail operator | Retry/replay records within assigned scope |
| Security/admin | Handle suppressions, incidents, or sensitive data per procedure |
| Application worker | Claim and update status via authorized services |

These are role examples only. Actual permissions must match your organization and deployment environment.

## 19. Dead-letter queues and operational runbooks

A dead-letter queue (DLQ) holds messages that cannot continue under normal retry policies. With a database outbox, DEAD_LETTER can be a status; with a message broker, a DLQ can be a separate queue.

### When to move to dead-letter?

- Exceeded max retry attempts.
- Unrecoverable permanent error.
- Invalid payload.
- Missing template/version after waiting period.
- Worker unable to process message under current schema.
- Operator manually quarantined for investigation.

### Operational runbook

1. Receive alert on DEAD_LETTER count or rising error rate.
2. Group by error code, template key, provider, and timestamp.
3. Determine whether the issue is widespread or isolated to one recipient/notification.
4. Check provider status, deployments, template versions, and configuration.
5. Fix the root cause in the appropriate environment.
6. Run a dry-run over a clearly filtered record set.
7. Exclude already-SUBMITTED, SUPPRESSED, EXPIRED, or unreconciled SUBMISSION_UNKNOWN records.
8. Replay a small batch first and observe results.
9. Scale up batch size and rate limit once stable.
10. Record incident ID and resolution in the audit log.

Never replay the entire DLQ immediately when SMTP comes back online. A large burst can trigger provider rate-limiting and cause further failures.

### Operational metrics

| Metric | Usage |
| --- | --- |
| Outbox pending count | Track backlog |
| Oldest pending age | Detect messages waiting too long |
| Retry count by error code | Spot recurring failures |
| Dead-letter count | Measure records needing intervention |
| Submission unknown count | Track uncertain outcomes |
| Replay count/operator | Monitor operational actions |
| Duplicate suspicion rate | Spot worker/transport issues |
| SMTP success/temporary/permanent rate | Monitor provider health |

Alerts should trigger on backlog age and error rates rather than absolute counts alone. A queue of 100 records in a system sending millions of emails may be normal; a single security notification stuck for 10 minutes can already be an incident.

## 20. Safe replay with Spring Retry or schedulers

Spring Retry can assist retries within a single execution, yet it does not replace an outbox. If the process stops, in-memory retry state is lost. For replayability across restarts, persist state in a database or message broker.

### Method-level retry

A conceptual example:

~~~java
@Retryable(
        retryFor = TemporaryMailException.class,
        maxAttempts = 4,
        backoff = @Backoff(delay = 1000, multiplier = 2))
public void submit(MimeMessage message) {
    mailSender.send(message);
}
~~~

This snippet illustrates the Spring Retry annotation when the matching dependency and configuration are present. It retries within the current call and does not automatically persist attempt history into the outbox. Do not annotate retries for all `MailException` types; retry only exceptions classified as temporary.

### Durable retry via outbox

With an outbox, after a temporary failure:

~~~java
@Transactional
public void scheduleRetry(
        UUID notificationId,
        Instant nextAttemptAt,
        String errorCode) {

    EmailOutboxEntity record = repository
            .findByIdForUpdate(notificationId)
            .orElseThrow();

    record.markRetryPending(nextAttemptAt, errorCode);
    attemptRepository.save(
            EmailAttemptEntity.retryableFailure(
                    notificationId, record.getAttempts(), errorCode));
}
~~~

The scheduler then claims due records. Retry state survives process restarts and can be observed via queries/metrics.

### Combining both layers properly

You can use short retries in the transport adapter for transient connection blips that recover quickly, while keeping the outbox as the durable mechanism for later attempts. Cap total retries across layers to avoid multiplying attempts unexpectedly. For instance, 3 retries in the adapter times 5 outbox attempts equals 15 sends.

## 21. Cancelling and editing records before replay

Not every failed record should be replayed. Cancellation may be required when:

- The user deleted their account.
- The order was cancelled and the old notice is no longer relevant.
- The campaign expired.
- The recipient is no longer valid.
- The event was superseded by a newer notification.

Cancellation should be an explicit state like CANCELLED or EXPIRED with a reason. Never delete records, to avoid losing audit trails.

### Do not edit payloads arbitrarily

If content is wrong, creating a new notification may be preferable to mutating an old payload. Directly editing records can destroy evidence of what the original record held. If policy allows editing recipient/template/payload, record explicitly:

- Before and after values at a non-sensitive level.
- Who performed the edit and why.
- New payload/template version.
- Whether approval is required.
- Whether the record was ever submitted before.

For SUBMITTED records, never alter historical content; create a new resend request if business rules require it.

## 22. Data protection and retention for failed records

Outboxes and DLQs may store email addresses, names, transaction IDs, rendered content, or attachment references. This is managed data:

- Store only the minimum payload needed for replay.
- Encrypt sensitive data at rest per infrastructure policy.
- Restrict read permissions on outbox and DLQ tables.
- Never log OTPs, reset tokens, passwords, or full message bodies.
- Set retention periods for SUBMITTED, FAILED, and DEAD_LETTER records.
- Purge or anonymize personal data once allowed retention expires.
- Avoid keeping attachment bytes in outbox tables when secure object references can be stored instead.
- When replaying, verify the object version and access rights remain valid.

Retention must balance investigation capabilities, audit requirements, and data minimization principles. A failed record should not exist forever merely because it might be replayed someday.

## 23. Testing retries and replay

Tests must cover success, temporary errors, permanent errors, crashes, and operational actions.

| Scenario | Expected outcome |
| --- | --- |
| Outbox record committed with order | Both exist after commit |
| Business transaction rolls back | No outbox record exists |
| SMTP returns temporary error | RETRY_PENDING and next_attempt_at are persisted |
| SMTP permanent error | FAILED_PERMANENT or DEAD_LETTER |
| Worker stops while PROCESSING | Lease expires; record recovered per policy |
| Two workers claim concurrently | Only one worker receives the record |
| SMTP accepted then process stops before DB update | Handled as unknown/reconciliation; duplicate risk controlled |
| Replay eligible DEAD_LETTER record | Creates audit and transitions status per policy |
| Replay SUBMITTED record | Rejected; requires new resend request |
| Replay when preference is disabled | SUPPRESSED, SMTP not called |
| Replay expired campaign | EXPIRED, not sent |
| Large batch replay | Dry-run, filters, limits, and rate limits applied |
| Payload/template version missing | Does not send unintended content; routed for handling |

### Testing temporary SMTP failures

~~~java
@Test
void schedulesRetryForTemporaryMailFailure() {
    doThrow(new TemporaryMailException("SMTP unavailable"))
            .when(transport).send(any());

    dispatcher.dispatch(claimedEmail);

    verify(stateService).recordRetryableFailure(
            eq(claimedEmail.id()),
            any(Instant.class),
            eq("SMTP_TEMPORARY"));
}
~~~

This illustrative test confirms temporary errors transition to retry state. In real tests, avoid relying on message strings for classification; use normalized exception types/error codes.

### Testing disallowed replay

~~~java
@Test
void doesNotReplaySubmittedRecord() {
    when(repository.findByIdForUpdate(notificationId))
            .thenReturn(Optional.of(submittedRecord));

    assertThrows(
            IllegalStateException.class,
            () -> replayService.replay(
                    notificationId,
                    "operator-7",
                    "Retry request",
                    EmailDeliveryStatus.SUBMITTED));

    verifyNoInteractions(auditRepository);
}
~~~

This illustrates testing the policy of replaying only failed records. If the product supports resending after SUBMITTED, write a separate test for a use case that creates a new notification linked to the original record.

### Testing concurrent worker claiming

Against a real database or integration environment, run two workers concurrently and confirm the same record is never claimed by both. Mock repositories are insufficient to prove locking/skip-locked works properly in the database.

## 24. Common design mistakes

### 24.1. Logging errors and dropping the record

Logs are not a durable queue. Without an outbox or failed-record store, messages are hard to retry reliably and can be lost.

### 24.2. Retrying every exception

Broken templates, invalid recipients, and wrong SMTP credentials do not fix themselves in a few seconds. Classify errors and retry conditionally.

### 24.3. Resetting all FAILED statuses to PENDING

This can send duplicates, violate consent, send expired emails, or replay unfixed content. Use a replay service with filters and auditing.

### 24.4. Replaying domain events just to resend an email

Other consumers may rerun their side effects. Replay dedicated outbox records or notification commands.

### 24.5. Holding a database transaction while calling SMTP

Increases lock hold times and does not resolve uncertainty between the database and SMTP. Claim, send, and update state in separate stages.

### 24.6. Missing leases or atomic claiming

Multiple workers may send the same record. Use locks/leases or equivalent queue claim mechanisms.

### 24.7. Treating expired leases as proof the email was not sent

The old worker may have submitted the email before dying. Account for SUBMISSION_UNKNOWN and duplicate risk.

### 24.8. Not keeping attempt history

Having only last_error is insufficient to investigate failures over time. Store each attempt with error code, timestamp, and correlation.

### 24.9. Replaying SUBMITTED records

This can send duplicates. Resends must be new requests linked to the original notification.

### 24.10. Replaying without checking preferences

A marketing email might be sent after the recipient unsubscribed. Check current policy right before submission.

### 24.11. Replaying with a new template without recording version

Resent content may differ from expected content. Store template version or explicitly record a new generation.

### 24.12. Unbounded batch replays

One action can trigger a massive email burst and cause the provider to rate-limit further. Use dry-runs, small batches, and rate limits.

### 24.13. Treating JavaMailSender success as delivered

That reflects SMTP submission status per response, not confirmation that a mailbox received it. Use provider events/bounces if delivery status is needed.

### 24.14. Deleting dead-letter records after replay

Destroys investigation history. Keep attempts and replay audits; update current status and generation.

## 25. Operational runbook for replaying failed records

A runbook can follow this sequence:

1. Locate the notification ID and category.
2. Inspect status, attempt history, error code, and timestamps.
3. Determine whether the record ever reached SUBMITTED or SUBMISSION_UNKNOWN.
4. Check the failure cause and SMTP/provider status.
5. Verify template key/version and payload.
6. Verify recipient, preferences, suppression, and expiry.
7. Check attachments/resources if present.
8. Fix the root cause in the application/provider first.
9. Run a dry-run or non-sending render check.
10. Replay a single test record per policy.
11. Monitor SUBMITTED/FAILED/RETRY_PENDING and provider events if available.
12. Expand to bounded batch replays once outcomes stabilize.
13. Record audit entries and close the incident.

### When should you NOT replay?

- The record is already SUBMITTED with no new resend request.
- The SMTP outcome is unknown and has not been reconciled.
- An optional email has been unsubscribed/suppressed.
- The campaign or challenge has expired.
- The payload no longer matches business state.
- Recipient or access permissions have not been confirmed.
- Attachments changed or scan results no longer apply.
- Required template version is gone and no replacement policy exists.

## 26. Self-check questions

**1. How does replay differ from retry?**

Retry is the next attempt on an automatic schedule. Replay is a controlled action returning failed/quarantined records to processing, usually after investigating or fixing the root cause.

**2. Why use a transactional outbox for transactional emails?**

Because the send request is saved in the same transaction as business changes, avoiding committed orders without an email-request record.

**3. Does an outbox guarantee an email is sent strictly once?**

No. It guarantees durable request persistence. SMTP may receive a message while the application fails to receive the response; retries can then create duplicates.

**4. Why not replay the entire domain event just to resend an email?**

An event may have multiple consumers and side effects. Replaying the event could rerun inventory, invoicing, or other integrations. Replay dedicated notification/outbox records instead.

**5. What information should a record store for replay?**

Notification ID, category/event type, recipient reference, payload or snapshot, template key/version, status, attempts, next attempt, error code, and audit metadata.

**6. Why keep separate attempt history?**

To know when each attempt occurred, which worker ran it, what outcome happened, and what error code the provider returned, rather than seeing only the latest error.

**7. How are SMTP 4xx and 5xx usually handled?**

4xx are typically temporary errors eligible for retry; 5xx are typically permanent errors for the current request. Always cross-check provider-specific codes and policies.

**8. Why not keep a database transaction open while calling SMTP?**

SMTP is an external network system; holding transactions open increases lock contention and cannot roll back an email already accepted by a relay.

**9. What do leases help with and what do they not solve?**

Leases prevent multiple workers from processing the same record under normal conditions. They do not prove an email was never submitted when a worker dies or pauses.

**10. What does SUBMISSION_UNKNOWN mean?**

The application does not know for certain whether the SMTP relay received the message. Reconcile or apply duplicate policies before retrying.

**11. Should SUBMITTED records be replayed?**

Not through the failed-record replay flow. If resending is needed, create a new resend request with its own ID and audit trail.

**12. Why must marketing email replays re-check preferences?**

Recipients may have unsubscribed after the email was enqueued. Replays must honor consent/suppression at send time.

**13. Why is template version needed?**

A replay after deployment could otherwise render different content. Versions let you reproduce content or explicitly record what was used for the replay.

**14. Should dead-letter records be deleted after replay?**

Never delete history. Preserve attempts and replay audits; update current status and generation.

## Conclusion

**Replayability lets a Spring Mail system recover failed messages while preserving history and controlling duplicate impact.** Persist email requests with a transactional outbox, classify temporary/permanent/unknown errors, store attempt history, and coordinate workers with claims/leases. Automatic retries need backoff, attempt limits, and deadlines; manual replays require verifying the root cause is fixed, checking recipient/preferences/template versions, auditing, and bounding batches. Never replay domain events indiscriminately, never reset all failed records to PENDING, and never treat SUBMITTED as delivered. With uncertain SMTP outcomes, weigh reconciliation and duplicate risk before resending. **A clear retry, dead-letter, and replay workflow ensures transactional emails are never silently dropped while avoiding duplicate or incorrect content when recovering from incidents.**
