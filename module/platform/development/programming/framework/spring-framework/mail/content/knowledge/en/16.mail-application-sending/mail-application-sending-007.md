# Handling Required and Optional Emails in Spring Framework Mail

Not every email an application sends has the same criticality. Password reset emails, verification codes, or security alerts may be an essential part of a user workflow. Order confirmation emails may be a notification obligation the system must keep fulfilling even after the purchase transaction has completed. Meanwhile, newsletters, promotions, or product recommendations are usually optional content: users can opt out, and sending failures must not disrupt the primary feature.

In Spring Framework Mail, both groups can be sent through JavaMailSender. The difference lies in the **business policy surrounding delivery**: when sending is permitted, whether consent is required, how send errors affect the primary operation, whether retries are needed, how state is persisted, and when skipping is allowed.

A good design distinguishes three concepts:

- **Required email:** a message that business logic or product policy requires to be processed. It must not be silently dropped.
- **Optional email:** a message that may be sent when the recipient is eligible and consents; not sending it usually does not affect the main transaction.
- **Delivery mode:** synchronous so the user gets immediate feedback, or asynchronous via a queue/outbox to allow retries and tracking.

A required email does not mean every transaction must block waiting for SMTP. An optional email also does not mean it can be sent regardless of errors or recipient preferences. **Business policy determines whether an email is required; delivery architecture determines how to execute that policy reliably.**

## 1. Distinguishing required and optional emails

### Required emails

Required emails typically serve security, verification, transaction state, or notifications the product commits to delivering to users. For example:

- Verification codes or email address verification links.
- User-requested password reset links.
- Login alerts or security setting change alerts.
- Transaction confirmations, receipts, or invoices per product workflow.
- Order status updates that customers need in order to proceed.
- Critical operational notices mandated by organizational policy.

For this group, the application must record the send, handle errors intentionally, and never silently mark completion if the message has not been processed according to policy.

However, not every transactional email needs to block the primary transaction when SMTP fails. For instance, once an order has been recorded successfully, a temporary failure to send the confirmation email should usually not roll back the order. Instead, the system persists the send request and retries. Conversely, if email is the only channel for a user to receive a verification code before signing in, failing to send the code may prevent the verification step from completing.

### Optional emails

Optional emails typically serve engagement, supplementary content, or marketing. For example:

- Periodic newsletters.
- Promotional announcements, discounts, or campaigns.
- Product recommendations or personalized content.
- Invitations to surveys, webinars, or events.
- Non-essential reminders that users can turn off.
- Onboarding follow-ups or new feature announcements.

This group usually depends on email preferences, consent, or an appropriate legal/policy basis under product rules and applicable regulations. If the user has opted out, the system must skip or mark the message suppressed. If SMTP fails, purchasing, signing in, or updating a profile must not fail just because a marketing email could not be sent.

### Comparison table

| Criterion | Required email | Optional email |
| --- | --- | --- |
| Goal | Security, verification, transactions, or notification obligation | Engagement, supplementary content, marketing |
| Send condition | Per business event and policy | Per event, preferences, consent, and send limits |
| Can users turn it off? | Depends on message type and applicable policy; should not be bundled with marketing | Usually has opt-out or unsubscribe options |
| On SMTP failure | Record, retry, or block steps that genuinely depend on the email | Do not block main operation; bounded retry or skip |
| Is message loss acceptable? | Usually no; track to a terminal state | Acceptable per policy |
| Retries | Clear policy, typically durable for transactional notices | Bounded, may expire or be canceled |
| Audit | Usually requires recording processing trace and outcome | Record consent, suppression, and outcome as needed |
| Examples | OTP, password reset, order confirmation | Newsletter, promotions, product recommendations |

### Do not classify by email title alone

A message titled "Account Notice" is not automatically required. An "Order Update" email could be essential or merely a convenience reminder depending on the workflow. Ask:

1. If not sent, does the user lose the ability to complete an important step?
2. Did the system commit to sending this message?
3. Does the message contain promotional or commercial content?
4. Do users have the right to opt out under product policy?
5. Is there a reliable alternative channel?
6. When sending fails, should business logic wait, retry, or continue?

If a transactional email includes promotional content, classify that content carefully. Consider separating transactional notices from marketing campaigns so optional content does not alter how the entire email is handled.

**Business classification is not legal advice.** Obligations to send, consent, and unsubscribe rights depend on message type, jurisdiction, and applicable regulations. Let product/legal policy define which categories are truly required.

## 2. Separating delivery policy from email content

Avoid having services decide policy with scattered conditionals like:

~~~java
if (isMarketing) {
    // Errors may be ignored
} else {
    // Throw error
}
~~~

This quickly becomes hard to follow as the application adds more notification types. A clearer design separates:

- **Notification type:** message kind, such as PASSWORD_RESET or ORDER_CONFIRMED.
- **Requirement:** required or optional per business rules.
- **Delivery policy:** synchronous, durable asynchronous, or best-effort.
- **Recipient preference:** whether the recipient allows this optional email category.
- **Template:** rendered HTML/text content.
- **Transport:** JavaMailSender or an external email service.

Example enums:

~~~java
public enum MailCategory {
    SECURITY_REQUIRED,
    TRANSACTIONAL_REQUIRED,
    PRODUCT_UPDATE_OPTIONAL,
    MARKETING_OPTIONAL
}

public enum DeliveryMode {
    BLOCKING,
    DURABLE_ASYNC,
    BEST_EFFORT
}
~~~

The two enums answer different questions. MailCategory represents business policy; DeliveryMode represents how delivery is executed. For example:

| MailCategory | Possible DeliveryMode |
| --- | --- |
| SECURITY_REQUIRED | BLOCKING for verification codes needed immediately; or DURABLE_ASYNC for security alerts |
| TRANSACTIONAL_REQUIRED | Typically DURABLE_ASYNC after the transaction commits |
| PRODUCT_UPDATE_OPTIONAL | BEST_EFFORT or DURABLE_ASYNC with expiration |
| MARKETING_OPTIONAL | BEST_EFFORT or bounded queue with consent check before sending |

Do not infer DeliveryMode solely from Category. A required notice may need durable persistence and background sending; an optional notice may need a queue to control send rate.

## 3. Optional email policies and recipient choices

For optional emails, check preferences before creating a send request. For instance, a user might enable newsletters while disabling promotions:

~~~java
public record EmailPreferences(
        boolean productUpdates,
        boolean marketing,
        boolean newsletters
) {
}
~~~

A policy service can evaluate:

~~~java
public boolean maySendOptional(
        MailCategory category,
        EmailPreferences preferences) {

    return switch (category) {
        case PRODUCT_UPDATE_OPTIONAL -> preferences.productUpdates();
        case MARKETING_OPTIONAL -> preferences.marketing();
        default -> true;
    };
}
~~~

This is a minimal example. In real systems, preferences may need consent status, timestamps, collection source, terms version, tenant, campaign type, suppression lists, and email address status.

### Checking preferences at two points

For emails that are queued and sent later, check preferences:

1. **At request creation:** do not enqueue an optional email if the recipient has already disabled that category.
2. **Right before sending:** the recipient may have changed their preference while the email was waiting.

~~~text
User enables newsletter
       |
       v
Campaign creates optional notification
       |
       v
Notification waits in queue
       |
       +---- User unsubscribes
       |
       v
Mail worker checks current preference
       |
       v
SUPPRESSED (do not send)
~~~

If you check only at enqueue time, an email already sitting in the queue could still be sent after the user unsubscribes. Rechecking right before submission reduces that risk.

### Unsubscribe and suppression

For marketing campaigns, the system needs an easy-to-use unsubscribe mechanism and suppression list. When a recipient opts out:

- Record the timestamp and scope of the unsubscribe.
- Stop creating emails in the corresponding category.
- Cancel or suppress unsent jobs if policy requires.
- Recheck preferences before sending waiting jobs.
- Never wipe suppression records just because a new campaign is created.

If an address hard-bounces or is marked as spam, the system can add it to a suppression list to stop future sends. Suppression rules and transactional notification eligibility must be separated by policy; never use a single "email enabled" boolean for all categories.

### Do not mix promotions into required emails

A password reset email should stay focused on resetting the password. Adding promotions can blur message classification and make it harder for recipients to spot the security action required.

Keep them separate:

- Transactional/security emails contain only the information needed for the event.
- Marketing emails are sent separately with consent/preference checks.

If promotional content appears inside a transactional email, review classification and delivery policy before shipping.

## 4. Deciding whether send errors block the primary operation

This is the most critical decision when handling required and optional emails. Ask: **is the email a precondition for completing the current primary operation?**

### When blocking is needed

Suppose a user requests an email OTP code to verify an action. If the system cannot send the code, the user cannot complete verification via that channel. The application should return an appropriate outcome such as "unable to send code right now", allow bounded retries, or offer an alternative support channel.

In this case:

- Do not mark verification as successful.
- Do not return secret codes in responses or logs.
- Do not generate unlimited fresh codes on retry.
- Do not allow expired or revoked tokens to be used.
- Track send failures so users can retry per policy.

### When not to block

Suppose an order has been created and payment succeeded, and the receipt email is temporarily rejected by SMTP. Rolling back the order just because the email failed could leave inconsistent transaction state or trigger unintended refunds.

Instead:

- Commit the order and an email-send request record in the same transaction.
- Have a worker send the email after commit.
- If sending fails transiently, retry.
- If it fails permanently, record an actionable state and alert through appropriate operational channels.

The email remains a required message that must be processed, yet SMTP submission does not sit inside the order creation transaction.

### Decision matrix

| Scenario | What happens to the primary action on SMTP error? | Handling |
| --- | --- | --- |
| Send OTP before verification | Verification step does not complete | Report send failure, retry/alternative channel |
| Send password reset link | Reset is not marked complete | Keep request valid within TTL, retry per policy |
| Send receipt after payment | Transaction still succeeds | Outbox and retry, do not roll back payment |
| Send order confirmation | Order remains recorded | Outbox, retry, and monitor |
| Send newsletter | Primary feature unaffected | Check consent; skip/suppress or bounded retry |
| Send promo after signup | Signup unaffected | Best-effort; never fail signup |

**"Required" describes the obligation to process the message; it does not automatically mean the HTTP request must wait on SMTP.**

## 5. Synchronous vs. asynchronous sending

Spring provides JavaMailSender to send emails. A simple call:

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setTo("user@example.com");
message.setSubject("Notification");
message.setText("Email content");

mailSender.send(message);
~~~

`send` normally invokes SMTP transport on the executing thread. If SMTP is slow or unavailable, the request may block and throw an exception.

### Synchronous (blocking) sending

Advantages:

- Immediate submission result on the current thread.
- Easy to give user feedback when the email is an essential step.
- Simple code flow for small cases.

Drawbacks:

- Request latency depends on SMTP latency and availability.
- SMTP timeouts increase response times.
- If called inside a database transaction, the transaction may stay open while waiting on the network.
- Does not by itself guarantee the email reached the mailbox or was read.
- Hard to retry durably if the process stops mid-flight.

Use synchronous sending only when the submission outcome is truly needed for an immediate response and timeouts are bounded. Never hold a database transaction open while calling SMTP.

### Asynchronous sending

An asynchronous flow persists the send request first, and a worker executes it later:

~~~text
HTTP request / business command
          |
          v
Business transaction
  - update domain data
  - insert email outbox record
          |
          v
        COMMIT
          |
          v
      Mail worker
          |
          v
     Render template
          |
          v
    JavaMailSender.send
          |
          v
   Update delivery state
~~~

Advantages:

- Does not block requests waiting on SMTP.
- Can retry when SMTP fails transiently.
- Provides states for observability and operations.
- Can rate-limit sending and isolate workers from web servers.
- Does not lose send requests when the domain transaction and outbox commit together.

Drawbacks:

- Emails are not submitted immediately.
- Requires managing queues/outboxes, workers, retries, and state.
- Must handle duplicates caused by worker retries or mid-flight crashes.
- Must decide which template version and data are preserved until send time.

For required transactional emails, an asynchronous outbox is usually preferable because it durably persists the send request without coupling the business transaction to SMTP.

## 6. Why not send SMTP inside a database transaction?

Avoid:

~~~java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(createOrder(command));

    mailSender.send(buildConfirmation(order));

    return order;
}
~~~

If SMTP takes 8 seconds, the database transaction can remain open for that duration. If SMTP succeeds while the database transaction rolls back, the recipient may receive a confirmation email for a nonexistent order. Conversely, if the database commits and the process stops before sending the email, the message is lost.

Two systems (database and SMTP) do not participate in a single ACID transaction. You cannot assume a database rollback will recall an email already accepted by an SMTP relay.

### Sending after transaction commit

For simpler cases, Spring supports transaction-bound events:

~~~java
public record OrderPlacedEvent(
        String orderId,
        String recipientEmail
) {
}
~~~

Publish the event inside the transaction:

~~~java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(createOrder(command));

    publisher.publishEvent(new OrderPlacedEvent(
            order.getId(),
            order.getCustomerEmail()));

    return order;
}
~~~

Listen after commit:

~~~java
@Component
public class OrderMailListener {

    private final OrderMailService mailService;

    public OrderMailListener(OrderMailService mailService) {
        this.mailService = mailService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPlaced(OrderPlacedEvent event) {
        mailService.sendOrderConfirmation(event);
    }
}
~~~

This event listener avoids sending before the transaction commits. However, **an in-memory transactional event is not a durable queue**. If the process stops after commit but before the listener runs, the event can be lost. If the listener fails to send, retries must also be designed separately.

You can combine `@Async` with an event listener to run on another thread, but `@Async` only changes execution threading; it does not create durable storage. For required notifications that must not be lost, consider a transactional outbox.

## 7. Transactional outbox for required emails

A transactional outbox stores the email send request in the same transaction as business data. The database guarantees both commit or both roll back together.

Example:

~~~java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(createOrder(command));

    EmailOutboxMessage outbox = EmailOutboxMessage.pending(
            UUID.randomUUID(),
            "ORDER_CONFIRMED",
            order.getCustomerEmail(),
            order.getId());

    outboxRepository.save(outbox);
    return order;
}
~~~

If the transaction commits, both the order and the email outbox record exist. If it rolls back, neither exists. A worker can read the outbox record afterward.

### A simple outbox model

~~~java
public enum OutboxStatus {
    PENDING,
    PROCESSING,
    SUBMITTED,
    RETRY_PENDING,
    FAILED,
    SUPPRESSED
}

public record EmailOutboxMessage(
        UUID id,
        String notificationType,
        String recipient,
        String aggregateId,
        String templateVersion,
        OutboxStatus status,
        int attempts,
        Instant nextAttemptAt
) {
}
~~~

This is an illustrative record; a real persistence entity needs created/updated timestamps, lease/lock fields, sanitized last error, correlation ID, and other fields as needed.

### Commonly needed columns

| Field | Purpose |
| --- | --- |
| id | Unique ID of the notification/outbox event |
| notification_type | Email type; do not infer policy from subject |
| recipient | Recipient verified by business rules |
| aggregate_id | Related order/account/transaction ID |
| payload | Minimal data needed for rendering |
| template_version | Selected template version if content reproducibility is needed |
| status | Processing state |
| attempts | Number of attempts made |
| next_attempt_at | Time when next retry is allowed |
| locked_until / lease_owner | Prevents multiple workers from processing the same record concurrently |
| last_error_code | Normalized error code; never store secrets |
| created_at / updated_at | Audit and operations |

You do not necessarily have to store full rendered HTML in the outbox. You can store the event payload and render when the worker runs. If content must be immutable for auditing, store the template version or rendered snapshot under appropriate data protection and retention policies.

### Worker processing the outbox

~~~java
@Component
public class EmailOutboxWorker {

    private final EmailOutboxRepository repository;
    private final MailDispatcher dispatcher;

    public EmailOutboxWorker(
            EmailOutboxRepository repository,
            MailDispatcher dispatcher) {
        this.repository = repository;
        this.dispatcher = dispatcher;
    }

    @Scheduled(fixedDelay = 1000)
    public void dispatchPending() {
        List<EmailOutboxMessage> messages =
                repository.claimDueMessages(50);

        for (EmailOutboxMessage message : messages) {
            dispatcher.dispatch(message);
        }
    }
}
~~~

`claimDueMessages` must be implemented with database-appropriate transactions/locking so only one worker owns a record during the lease window. Never do a plain SELECT PENDING followed by a separate UPDATE without an atomic claim mechanism; multiple instances could send the same email.

### Updating status after sending

~~~text
PENDING
  |
  v
PROCESSING
  |
  +-- SMTP accepted --> SUBMITTED
  |
  +-- Temporary error --> RETRY_PENDING
  |
  +-- Permanent error --> FAILED
  |
  +-- Optional + preference disabled --> SUPPRESSED
~~~

SUBMITTED means only that the SMTP relay accepted the message according to the response received by the application. It does not mean the recipient received it in the inbox, opened it, or read it.

## 8. Handling optional emails without disrupting business flows

For newsletters or promotions, the primary service must not directly wait on JavaMailSender:

~~~java
@Transactional
public void completeRegistration(RegistrationCommand command) {
    User user = userRepository.save(createUser(command));

    // Registration is complete; marketing email is optional.
    optionalMailService.enqueueWelcomeCampaign(user.getId());
}
~~~

This snippet illustrates the concept. If enqueuing uses the database, write the outbox record in the same transaction; if calling a queue outside the database, address consistency between commit and publish.

When the worker processes the job:

1. Load the recipient and current preferences.
2. Verify the email belongs to the right user/tenant.
3. Check consent for the specific category.
4. Check suppression, unsubscribe, and bounce status.
5. Check frequency cap and campaign expiry.
6. Render the template.
7. Submit the email.
8. Record the outcome or suppress.

If preferences are disabled, update status to SUPPRESSED and do not call SMTP. This is not a send failure; it is the right policy decision.

### Optional emails can expire

An offer valid only until a specific date must not be retried indefinitely after the campaign ends. Store `expires_at`, `campaign_id`, `category`, `consent_version`, `frequency_bucket`, and `suppression_reason`. When a worker picks up an expired job, mark it EXPIRED or SUPPRESSED. Never send an expired promotion just because a queue backed up.

## 9. Building an explicit mail policy

A policy service can return a decision before enqueuing or dispatching:

~~~java
public enum MailDecision {
    ALLOW,
    SUPPRESS,
    REQUIRE_BLOCKING_DELIVERY,
    REQUIRE_DURABLE_DELIVERY
}

public class MailPolicy {

    public MailDecision decide(
            MailCategory category,
            EmailPreferences preferences) {

        return switch (category) {
            case SECURITY_REQUIRED ->
                    MailDecision.REQUIRE_BLOCKING_DELIVERY;
            case TRANSACTIONAL_REQUIRED ->
                    MailDecision.REQUIRE_DURABLE_DELIVERY;
            case PRODUCT_UPDATE_OPTIONAL ->
                    preferences.productUpdates()
                            ? MailDecision.ALLOW
                            : MailDecision.SUPPRESS;
            case MARKETING_OPTIONAL ->
                    preferences.marketing()
                            ? MailDecision.ALLOW
                            : MailDecision.SUPPRESS;
        };
    }
}
~~~

This example expresses a concrete policy: security alerts use a flow requiring immediate feedback, transactional emails use an outbox, and marketing depends on preferences. In a real product, policies may depend on notification type, urgency, fallback channels, locale, and jurisdiction.

### Do not let ambiguous booleans control policy

An API like:

~~~java
sendEmail(message, true);
~~~

does not clarify whether `true` means required, synchronous, retryable, or ignore-errors. Use clearly named enums or policy objects:

~~~java
sendEmail(message, DeliveryMode.DURABLE_ASYNC);
~~~

Or a command carrying both category and policy. Clear naming makes code reviews and operations easier to reason about.

## 10. Sending text or HTML content according to policy

Once policy permits sending and content is rendered, Spring Mail supports SimpleMailMessage for plain text emails and MimeMessageHelper for MIME/HTML/attachments.

### Simple text email

~~~java
public void sendPlainText(
        String recipient,
        String subject,
        String body) {

    SimpleMailMessage message = new SimpleMailMessage();
    message.setFrom("notifications@example.com");
    message.setTo(recipient);
    message.setSubject(subject);
    message.setText(body);

    mailSender.send(message);
}
~~~

### HTML email with plain-text alternative

~~~java
public void sendHtml(
        String recipient,
        String subject,
        String plainText,
        String htmlText) throws MessagingException {

    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            "UTF-8");

    helper.setFrom("notifications@example.com");
    helper.setTo(recipient);
    helper.setSubject(subject);
    helper.setText(plainText, htmlText);

    mailSender.send(message);
}
~~~

These methods handle only constructing and submitting the message. Category, consent, retries, outbox, and failure policies should be handled in the orchestration layer beforehand.

### Do not put policy inside templates

Templates should control presentation only. Never embed logic like "if the user unsubscribed, hide the footer" and still send the marketing email. Permission to send must be checked in the policy/service layer before rendering and before submission.

## 11. Handling Spring Mail errors

JavaMailSender can throw Spring Mail exceptions when creating or sending messages. Most transport errors are represented via MailException or its subclasses. However, not every exception has the same retryability.

### Error classification

| Category | Examples | Retry? |
| --- | --- | --- |
| Configuration error | Wrong SMTP host/port, missing bean | Do not retry blindly; fix config |
| Authentication | Wrong username/password or SMTP permissions | Do not retry continuously; fix credentials/permissions |
| Transient connection error | Connection timeout, server temporarily unavailable | Can retry with backoff |
| Temporary server rejection | SMTP 4xx | Usually retryable per policy |
| Invalid recipient | Bad address or permanent mailbox rejection | Do not retry infinitely |
| Sender/policy rejection | MAIL FROM or relay policy disallowed | Fix configuration/policy |
| MIME creation error | Broken attachment/resource, invalid content | Usually do not retry until data is fixed |
| Template render error | Missing template or syntax error | Do not retry blindly; fix template/config |

Spring Mail exceptions can wrap Jakarta Mail exceptions. If classifying by SMTP response code, normalize in a transport adapter and inspect causes/responses per the library in use. Do not rely on regex-parsing exception message strings as the sole mechanism.

### Example catching MailException

~~~java
try {
    mailSender.send(message);
} catch (MailException exception) {
    // Record normalized error and decide retry/failure.
    throw new MailDeliveryException(
            "Unable to submit email", exception);
}
~~~

This illustrates error wrapping at the transport layer. When rethrowing, the caller or worker must decide how to update state. For optional emails, the caller can record the failure and continue business execution; for required durable emails, the worker moves the record to retry or FAILED.

### Never catch errors and pretend sending succeeded

Avoid:

~~~java
try {
    mailSender.send(message);
} catch (MailException exception) {
    log.warn("Email failed", exception);
}

return "SUCCESS";
~~~

This erases the distinction between SUBMITTED and FAILED. For required emails, messages can disappear silently. For optional emails, failures/suppressions still need to be recorded to measure system health.

## 12. Retries, backoff, and dead-lettering

Retries should depend on error type and category policy.

### Backoff

Do not retry continuously every few milliseconds. A strategy can use exponential backoff:

~~~text
delay = min(maxDelay, initialDelay * 2^attempt) + jitter
~~~

Example schedule:

| Attempt | Illustrative wait time |
| --- | --- |
| 1 | Immediately after job is claimed |
| 2 | 30 seconds |
| 3 | 2 minutes |
| 4 | 10 minutes |
| 5 | 30 minutes |

Values are illustrative only. Tune them for your SMTP provider, urgency, mail volume, and message TTL.

### Per-category policies

| Category | Suggested retry policy |
| --- | --- |
| Security required | Fast but bounded; alert and offer fallback channel on failure |
| Transactional required | Durable retries, potentially longer per SLA; never silently drop |
| Product update optional | Limited retries; cancel on expiration or preference change |
| Marketing optional | Respect campaign expiry, suppression, and frequency cap; may drop permanent errors |

### Dead-letter or actionable failure state

After max attempts, do not delete the record. Move it to FAILED/DEAD_LETTER with the notification ID, category, template key/version, attempt count, normalized last error code, failure timestamp, and correlation metadata.

Do not store credentials, sensitive bodies, or full SMTP transcripts unless required. For required emails, dead-lettered records need monitoring and a replay procedure once the root cause is fixed. For optional emails, jobs can be closed per policy.

## 13. Idempotency and duplicate-send risk

Asynchronous workers can send the same email multiple times if:

- Two workers claim the same outbox record.
- A worker sends successfully but crashes before updating SUBMITTED.
- The SMTP relay accepts the email, yet the response is lost on the network.
- A queue delivers at least once and the consumer does not deduplicate.
- A job is replayed manually without checking prior state.

SMTP does not provide a universal idempotency mechanism to guarantee end-to-end "exactly once" delivery. The Message-ID header helps identify messages, but does not force every mailbox/provider to deduplicate.

### Using notification ID as an internal idempotency key

Example unique key:

~~~text
notification_id = ORDER_CONFIRMED:order-184:recipient-42
~~~

The database can place a unique constraint on this business key so multiple outbox records are not created for the same event/recipient. Workers claim records via locking/lease and persist attempt state.

### Handling uncertain outcomes

If the connection drops after the client sent DATA but before receiving the final response, the application may not know whether the relay accepted it. Retrying can create duplicates. Options:

- Use a provider API with an idempotency key if available.
- Persist a SUBMISSION_UNKNOWN state and handle per policy.
- Use notification IDs and correlation metadata to detect duplicates at the application layer.
- Accept at-least-once with a small duplicate risk if business rules permit.

Do not claim the system guarantees exactly-once delivery just because the outbox has a unique key. An outbox ensures saving the send request atomically with the transaction; it does not eliminate uncertainty after the SMTP relay receives data.

### Avoid generating new OTP codes on every retry

For OTPs or reset tokens, delivery retries should reuse the same still-valid challenge/token per policy rather than generating unlimited new tokens. Tokens must have short lifetimes, attempt limits, revocation support, and must never be logged. If a challenge expires, issue a new one through the proper business workflow.

## 14. What should email delivery status reflect?

A system might use these states:

| State | Meaning |
| --- | --- |
| CREATED | Send request created |
| SUPPRESSED | Not sent due to preference, consent, or suppression policy |
| PENDING | Waiting for a worker |
| PROCESSING | Worker is processing |
| RENDERED | Content has been rendered |
| SUBMITTED | SMTP relay accepted the message |
| RETRY_PENDING | Transient error, awaiting retry |
| FAILED | Permanent error or retry policy exhausted |
| EXPIRED | Optional email expired |
| CANCELLED | Request canceled before submission |

Not every application needs all of these states. Pick enough states to answer:

- Was the send request created?
- Was the email skipped due to preferences?
- Is a worker currently processing it?
- Did content rendering succeed?
- Did the SMTP relay accept it?
- Is a retry or manual intervention needed?

### Submitted does not mean delivered

When JavaMailSender.send returns normally, the application usually knows only that SMTP submission completed per the received response. The relay may still process it afterward. The email can bounce, land in spam, be delayed, or be rejected by the destination mailbox.

If delivered/bounced states are needed, integrate provider events, bounce processing, or corresponding webhooks. Never infer "arrived in inbox" from `send()` not throwing an exception.

## 15. Example orchestrating required and optional emails

An orchestration layer can branch according to policy:

~~~java
@Service
public class ApplicationMailService {

    private final RequiredMailService requiredMailService;
    private final OptionalMailService optionalMailService;
    private final MailPolicy mailPolicy;
    private final PreferenceService preferenceService;

    public ApplicationMailService(
            RequiredMailService requiredMailService,
            OptionalMailService optionalMailService,
            MailPolicy mailPolicy,
            PreferenceService preferenceService) {
        this.requiredMailService = requiredMailService;
        this.optionalMailService = optionalMailService;
        this.mailPolicy = mailPolicy;
        this.preferenceService = preferenceService;
    }

    public void requestEmail(
            MailCategory category,
            String recipientId,
            MailPayload payload) {

        EmailPreferences preferences =
                preferenceService.getFor(recipientId);

        MailDecision decision = mailPolicy.decide(
                category, preferences);

        switch (decision) {
            case SUPPRESS -> optionalMailService.recordSuppressed(
                    category, recipientId, payload);
            case REQUIRE_BLOCKING_DELIVERY ->
                    requiredMailService.sendBlocking(
                            category, recipientId, payload);
            case REQUIRE_DURABLE_DELIVERY ->
                    requiredMailService.enqueueDurably(
                            category, recipientId, payload);
            case ALLOW ->
                    optionalMailService.enqueueBestEffort(
                            category, recipientId, payload);
        }
    }
}
~~~

The classes and DTOs in this example are application-defined components. In real systems, do not load preferences solely by email address if addresses may be shared or unverified; use recipient/user IDs and check authorization. RequiredMailService should not treat every required category as synchronous; the policy example above uses blocking only for the explicitly designated category.

### Why separate RequiredMailService and OptionalMailService?

Both services can share renderers and transports, yet enforce different policies:

- RequiredMailService needs state persistence, retries, alerts, and must never silently discard messages.
- OptionalMailService needs consent/preference checks, unsubscribe handling, suppression, frequency caps, and expiration.
- Both can share the JavaMailSender adapter, MIME builder, and template engine.

Class separation is not mandatory in every project. What matters is that differing policies are explicitly modeled and testable.

## 16. SMTP configuration and limits

Spring Boot can configure the mail sender:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: configured-smtp-user
    password: supplied-by-secret-store
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"
~~~

This is an example configuration for SMTP submission with STARTTLS. Host, port, and security properties must match your actual provider. Credentials come from a secret store/environment, never committed to the repository.

### What do timeouts mean?

- Connection timeout limits time to establish a connection.
- Read timeout limits time waiting for response data.
- Write timeout limits time writing data.

These bounds are especially critical for synchronous sends, because requests can be held while SMTP is slow. For async workers, timeouts free up the worker and let retry policy decide the next step.

### Rate limits and quotas

SMTP providers may enforce per-second, per-day, or per-account limits. Workers should have appropriate rate limits and concurrency. If the provider returns temporary quota/rate errors, retries need backoff; do not scale workers unboundedly.

Optional emails often require per-user/per-campaign frequency caps. Required emails may receive higher queue priority, yet still obey operational limits and provider policies.

## 17. Security and data inside emails

Email is not an appropriate channel for every kind of secret. Even for required emails, content should be limited to necessary information.

### OTPs and reset links

- Tokens must be short-lived and scoped strictly to their purpose.
- Never write tokens into logs or metrics.
- Never send tokens to multiple unauthorized recipients.
- Rate-limit requests and verification attempts.
- Support challenge revocation.
- Use HTTPS for links.
- Never confirm sensitive operations merely because an email was submitted.

### Transactional data

- Include only data the recipient is authorized to view.
- Do not send full sensitive payment details unless necessary.
- Attachments must pass inspection/scanning per policy.
- Document URLs need authorization and appropriate expiration.
- Verify the recipient address before sending.

### Optional emails

- Never send marketing if consent/preferences disallow it.
- Never drop the unsubscribe link from templates.
- Never use sensitive data for personalization beyond permitted purposes.
- Restrict open/click tracking according to privacy policy.
- Never resend expired or canceled campaigns.

### Logging and auditing

Log notification ID, category, template version, status, attempt count, and normalized error code. Avoid logging email bodies, OTPs, reset tokens, passwords, attachment bytes, or URLs containing tokens.

## 18. Testing required and optional email policies

Tests should not merely verify that JavaMailSender was called. They must test **when it is called, when it is not called, and how failures affect business logic**.

| Scenario | Expected outcome |
| --- | --- |
| Required email renders and submits successfully | SUBMITTED state or equivalent |
| Required email hits transient SMTP error | Outbox RETRY_PENDING, request not lost |
| Required email hits permanent error | FAILED/alert or fallback flow per policy |
| OTP email fails to send | Verification is not marked successful |
| Order email fails after order commit | Order persists; email is retried |
| Optional marketing unsubscribed | SUPPRESSED; JavaMailSender not called |
| Preference changes after enqueue | Worker rechecks and suppresses |
| Optional email hits SMTP error | Error recorded; primary action does not fail |
| Campaign expires in queue | EXPIRED; not sent late |
| Worker reruns same outbox ID | Does not create extra business notifications outside policy |
| SMTP response unknown after DATA | State/retry handled per duplicate policy |

### Testing optional service does not send when opted out

~~~java
@Test
void doesNotSendMarketingWhenUserOptedOut() {
    when(preferenceService.getFor("user-42"))
            .thenReturn(new EmailPreferences(false, false, false));

    applicationMailService.requestEmail(
            MailCategory.MARKETING_OPTIONAL,
            "user-42",
            payload);

    verify(optionalMailService).recordSuppressed(
            eq(MailCategory.MARKETING_OPTIONAL),
            eq("user-42"),
            eq(payload));
    verifyNoInteractions(requiredMailService);
}
~~~

This is an illustrative Mockito test. Depending on service design, you may assert repository/outbox status instead of calling a separate `recordSuppressed` method.

### Testing SMTP failures do not roll back the primary transaction

With a transactional outbox, tests should verify:

1. The domain entity is saved.
2. The outbox record is saved in the same transaction.
3. The worker calls SMTP and receives an error.
4. The outbox transitions to RETRY_PENDING or the appropriate status.
5. The domain entity remains persisted after the send failure.

Do not mock transactions and merely assert a method call; write an integration test against a real test database to prove transactional consistency when this guarantee matters.

### What are the limits of testing transactional events?

Tests for `@TransactionalEventListener` should verify that the listener runs only after commit. However, do not treat that test as proof that events survive process restarts. If message durability is required, test outbox/queue persistence.

## 19. Common design mistakes

### 19.1. Sending optional emails in the same transaction as the main operation

A marketing campaign hitting an SMTP error can cause user registration to roll back. Decouple notifications from the main transaction and process them in the background.

### 19.2. Sending required emails without persisting state

If SMTP fails and the exception is ignored, the system has no idea whether the email was processed. Use an outbox or notification state to track it.

### 19.3. Calling SMTP before transaction commit

Recipients may receive confirmations for data that later rolls back. Send after commit or use a transactional outbox.

### 19.4. Using @Async and assuming you have a durable queue

`@Async` runs work on another executor but does not durably persist tasks. Process termination loses queued tasks. Use an outbox/message broker when durability is needed.

### 19.5. Checking consent only at enqueue time

Users may unsubscribe before the worker sends. Recheck preferences right before submission.

### 19.6. One boolean for every email type

A single `emailEnabled=true/false` flag cannot properly represent security, transactional, newsletter, and marketing emails. Use per-category preferences and explicit policies.

### 19.7. Infinite retries

Bad addresses or broken templates do not heal on their own. Classify transient vs. permanent errors, cap attempts, and move actionable errors to dead-lettering.

### 19.8. Retries generating new tokens

Users can receive multiple OTPs/reset links simultaneously and not know which token is valid. Retry the same still-valid challenge per policy; issue a new challenge only when the workflow calls for it.

### 19.9. Treating send() success as inbox delivery

JavaMailSender only reports submission outcome from SMTP responses. Use provider events/bounce handling if delivery status is needed.

### 19.10. Ignoring duplicate protection

Workers can resend after crashing between SMTP acceptance and database updates. Use internal idempotency keys, claim/lease mechanisms, and account for duplicate risk.

### 19.11. Putting marketing content into transactional emails

This muddies message classification, confuses recipients, and complicates consent policies. Keep transactional emails and campaigns separate.

### 19.12. Deleting failed jobs without auditing

Required emails can be lost permanently. Retain terminal state, error codes, notification IDs, and a replay process.

## 20. Design workflow from scratch

When adding a new email type, follow this order:

1. Identify purpose and category: security, transactional, product update, or marketing.
2. Define send conditions, consent/preferences, and eligible recipients.
3. Decide whether the email is a precondition for completing the current action.
4. Choose delivery mode: blocking, durable async, or best-effort.
5. Identify data to store and template version.
6. Create HTML/text templates and view models.
7. Define states, retry policy, expiry, and dead-letter behavior.
8. Create an idempotency key/notification ID.
9. Integrate JavaMailSender through an adapter.
10. Write tests for success, failure, suppression, retries, and duplicates.
11. Add metrics, logs, and alerts per category.
12. Review privacy, security, and recipient policies.

### Example decisions for four email types

| Email type | Category | Delivery | On failure |
| --- | --- | --- | --- |
| Login OTP | SECURITY_REQUIRED | Blocking or flow with immediate feedback | Do not complete verification; allow bounded retries |
| Order confirmation | TRANSACTIONAL_REQUIRED | Durable async via outbox | Order commits; retry and monitor |
| New feature announcement | PRODUCT_UPDATE_OPTIONAL | Best-effort/queue with expiry | Suppress or bounded retry; never block feature |
| Newsletter | MARKETING_OPTIONAL | Queue with consent check | Skip if unsubscribed; job may expire |

This is an illustrative set of choices, not a rigid rule for every system. If product requirements differ, adjust policies while keeping business rules and transport clearly separated.

## 21. Self-check questions

**1. Must required emails always be sent synchronously?**

No. "Required" means the message must be processed per policy. Transactional emails can usually be stored in an outbox and sent in the background so database transactions do not wait on SMTP.

**2. Can optional emails be sent even if the user unsubscribed?**

No. Check preferences/consent per category before creating the job and recheck right before sending.

**3. If an order confirmation email hits an SMTP error, should the order roll back?**

Usually no. The order is the primary transaction; the email should be persisted and retried independently. Only block when the email is genuinely a precondition of that exact step.

**4. Does @TransactionalEventListener(AFTER_COMMIT) guarantee events are not lost on process crash?**

No. It runs after commit, but in-memory events are not a durable queue. A transactional outbox persisting the send request in the same transaction fits better when durability is needed.

**5. Does @Async replace an outbox?**

No. `@Async` offloads work to another executor, but it does not persist tasks durably or provide retries/auditing.

**6. What does JavaMailSender.send() succeeding prove?**

Usually only that SMTP submission was accepted according to the received response. It does not prove the email reached the inbox or was read.

**7. Why check preferences twice?**

Because users can change their preferences after the job is enqueued and before the worker sends it.

**8. Can every MailException be retried?**

No. Transient connection errors can be retried; wrong credentials, invalid addresses, or template errors require fixing the root cause first.

**9. Does an outbox guarantee exactly-once delivery?**

No. It ensures the send request is persisted atomically with the transaction. Duplicates can still occur if the SMTP relay accepted the message but the response was lost or the worker crashed before updating status.

**10. Why do we need an idempotency key?**

To identify the same business message, avoid creating multiple outbox records, or avoid resending outside policy when workers/queues reprocess messages.

**11. Should the entire email body be stored in the outbox?**

Not necessarily. You can store the payload and template version; store rendered snapshots only when needed for reproducibility/auditing under proper data protection policies.

**12. How should expired marketing emails in a queue be handled?**

Mark them EXPIRED or SUPPRESSED and do not send late campaigns. Never retry outdated content indefinitely.

## Conclusion

**Handling required and optional emails requires two explicit business policies, even though both can share Spring JavaMailSender.** Security and transactional emails must be tracked to an appropriate state, retried, and never silently dropped; optional emails must respect preferences/consent, unsubscribes, suppression, and campaign expiration. Only block the primary operation when the email is truly a precondition for that step. For post-commit transactional notifications, a transactional outbox persists send requests alongside business data and runs SMTP in a worker; for OTPs requiring immediate feedback, a blocking flow can be used with controlled timeouts and challenge state. Combining idempotency, backoff retries, clear states, and failure testing helps systems send the right email type, at the right time, to the right recipient.
