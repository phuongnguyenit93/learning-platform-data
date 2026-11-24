# Defining Boundaries for Spring Mail in a Large System

## 1. An architectural question more important than calling send()

In a small Spring Boot application, sending a confirmation email may be as simple as:

~~~java
simpleMailMessage.setTo(customerEmail);
simpleMailMessage.setSubject("Order created");
simpleMailMessage.setText("Thank you for your purchase.");
mailSender.send(simpleMailMessage);
~~~

As a system grows, the same email-sending need appears in many places: ordering, payments, account management, security, CRM, marketing, customer support, invoicing, reporting, and batch jobs. Each place has different policies for content, recipients, sending authorization, retries, and deadlines.

If every service knows the SMTP configuration, builds `MimeMessage` directly, and decides how to retry, the system easily suffers from:

- Email-sending logic duplicated across many modules.
- Business teams having to understand `MessagingException` or `MailSendException` just to process orders.
- A provider outage slowing down checkout requests or holding database transactions open.
- Switching SMTP providers requiring changes across many services.
- Inconsistent email templates, unsubscribes, and sender authorization.
- Emails sent for rolled-back transactions or lost when a process crashes.
- Retries causing duplicate emails and ambiguity about whether the provider actually accepted a message.
- Lack of clear ownership for multi-tenant quotas, data security, and delivery tracking.

Therefore, **“Defining boundaries for Spring Mail in a large system”** is not merely asking which package should hold `JavaMailSender`, but rather:

> **Which component knows the business rules requiring a notification? Which component decides whether a notification is valid? Which component is responsible for SMTP submission? Where is sending state stored, and who owns failure handling?**

Good boundaries clarify those questions and let different parts evolve independently.

## 2. What does Spring Framework Mail provide, and what does it not provide?

Spring Mail primarily provides abstractions and utilities for **outbound email submission**:

| Component | Role |
|---|---|
| `MailSender` | Interface for sending `SimpleMailMessage` instances |
| `JavaMailSender` | Extension for MIME messages and Jakarta Mail |
| `JavaMailSenderImpl` | Spring's typical implementation |
| `MimeMessageHelper` | Helper for To/From/Subject/body/attachment/inline MIME |
| `MailException` and subtypes | Classifies certain errors at the Spring Mail API level |
| Jakarta Mail `MimeMessage`/`Session` | Underlying MIME model and transport communication |

Spring Boot can auto-configure a default `JavaMailSender` from `spring.mail.*` when auto-configuration conditions are met.

However, **Spring Mail core does not provide a complete notification platform on its own**. It does not automatically:

- Determine which order needs an email.
- Check consent, quiet hours, or suppression lists.
- Schedule sends durably across restarts.
- Guarantee atomicity between the business database and SMTP.
- Store outbox state, attempts, or provider delivery events.
- Guarantee exactly-once email delivery.
- Manage fairness, provider quotas, or tenant budgets.
- Manage template lifecycles, locales, branding, or auditing.
- Build an inbound mailbox processor from `JavaMailSender` alone.

**Architectural conclusion:** place Spring Mail in the **infrastructure/transport adapter** layer. Notification orchestration and policies belong to the application or a dedicated bounded context, not stuffed inside `JavaMailSenderImpl` or `MimeMessageHelper`.

## 3. Five layers of responsibility to distinguish

~~~text
┌────────────────────────────────────────────────────────┐
│ 1. Business domain / application                       │
│  OrderPaid, UserRegistered, InvoiceIssued              │
└───────────────────────────┬────────────────────────────┘
                            │ business intent/event
                            v
┌────────────────────────────────────────────────────────┐
│ 2. Notification policy and orchestration               │
│  Who? Why? Which channel? Consent? Priority? Deadline? │
└───────────────────────────┬────────────────────────────┘
                            │ authorized email intent
                            v
┌────────────────────────────────────────────────────────┐
│ 3. Durable delivery workflow                           │
│  Outbox, schedule, status, lease, idempotency, retry    │
└───────────────────────────┬────────────────────────────┘
                            │ claim + dispatch decision
                            v
┌────────────────────────────────────────────────────────┐
│ 4. Mail transport adapter (Spring Mail)                │
│  MimeMessageHelper, JavaMailSender, SMTP TLS/auth       │
└───────────────────────────┬────────────────────────────┘
                            │ SMTP submission
                            v
┌────────────────────────────────────────────────────────┐
│ 5. Provider + delivery/feedback                        │
│  SMTP accepted, bounce, webhook, message trace         │
└────────────────────────────────────────────────────────┘
~~~

You do not necessarily need five microservices. **Logical boundaries** can simply be five packages/modules within a monolith. What matters is dependency direction and ownership, not the number of repositories or Kubernetes deployments.

| Layer | Owns | Should not own |
|---|---|---|
| Domain | Order, account, invoice rules; business events | SMTP host/password, MIME headers |
| Notification application | Recipient eligibility, template selection, channel policy | Socket/TLS implementation |
| Durable workflow | Job state, claim/lease, retry/expiry, attempt history | Specific business transactions of every domain |
| Transport adapter | Building MIME, SMTP config, calling `JavaMailSender`, describing outcomes | Rules like “has this order been paid?” |
| Provider feedback | Accepted references, bounce/delivery events | Directly mutating order state without domain policy |

## 4. Choosing boundaries around axes of change

A boundary is well-designed when **two independent kinds of change** do not force each other to change:

- Switching SMTP providers requires no edits to `OrderService`.
- Updating an invoice template requires no edits to SMTP connections or quota gates.
- Changing the business rule “send email only when payment is settled” requires no edits to the MIME builder.
- Changing retry/backoff requires no edits to order creation code.
- Changing attachment storage does not force the domain to know `ByteArrayResource`.
- Enabling an email HTTP API instead of SMTP does not force changes across all application request DTOs.

This applies **dependency inversion**: the domain and orchestration depend on contracts controlled by the application; the transport adapter implements those contracts.

Do not define public business interfaces using transport framework classes:

~~~java
// Unsuitable as public domain/application contracts:
void notifyCustomer(MimeMessage message);
void notifyCustomer(JavaMailSender sender);
void notifyCustomer(MessagingException previousError);
~~~

Replace them with contracts expressing **business intent** or a **delivery command** carrying the required data:

~~~java
void requestOrderReceipt(
        OrderId orderId,
        CustomerId customerId);
~~~

Or at the notification boundary:

~~~java
NotificationRequestResult request(
        NotificationIntent intent);
~~~

`OrderId`, `CustomerId`, and `NotificationIntent` are application-defined types. They do not originate from Spring Mail.

## 5. Distinguishing a business event from an email command

A business event describes **what happened**, not all the details of how to send:

~~~text
OrderPaid(orderId, customerId, paidAt, version)
~~~

A notification intent describes an **established desire to notify**:

~~~text
NotificationIntent(
  eventKey,
  recipientRef,
  templateKey=ORDER_RECEIPT,
  locale,
  channel=EMAIL,
  scheduledAt,
  priority
)
~~~

A mail delivery job describes a **technical unit of work**:

~~~text
MailDeliveryJob(
  notificationId,
  providerAccountId,
  senderProfileId,
  renderedContentRef,
  status=PENDING,
  availableAt
)
~~~

Do not have the domain publish an event named `SendSmtpMessage` whenever an order transitions state. That couples the domain to the email channel. An `OrderPaid` event might also trigger push notifications, analytics updates, or invoice generation.

Conversely, a notification system does not need an event bus for every single email. For a small flow, having an application service create a notification intent directly is still sensible. What matters is that **contracts express business intent and keep MIME/SMTP encapsulated inside the adapter**.

## 6. The boundary between “send requested” and “delivered” is distinct

An email request typically progresses through:

~~~text
BUSINESS_EVENT
      |
      v
NOTIFICATION_REQUESTED
      |
      v
PENDING / SCHEDULED
      |
      v
CLAIMED / PROCESSING
      |
      v
SMTP_SUBMITTED
      |
      +-- Provider delivery event -> DELIVERED
      +-- Provider bounce event   -> BOUNCED
~~~

A successful `JavaMailSender.send(...)` call usually indicates the client completed protocol submission to the SMTP server, **not proof that the email entered the recipient's inbox**. Some providers offer delivery webhooks; others provide only server logs or no definitive signal.

Therefore, APIs should express state honestly:

~~~json
{
  "notificationId": "opaque-notification-583",
  "state": "QUEUED",
  "acceptedForProcessing": true
}
~~~

instead of returning:

~~~json
{
  "emailDelivered": true
}
~~~

immediately after writing to the outbox or after `send()` returns.

A large design typically separates **notification job state**, **submission attempts**, and **provider delivery state** when the business needs accurate status tracking.

## 7. Enforcing dependency rules so frameworks do not leak into the domain

A module layout in a modular monolith:

~~~text
com.example.orders
  ├─ domain/
  └─ application/
         |
         | publishes domain event / calls NotificationPort
         v
com.example.notifications
  ├─ api/           Intent, command, query
  ├─ application/   Policy, orchestration, state transitions
  ├─ domain/        Notification model
  └─ spi/           MailDeliveryPort
         ^
         | implemented by
         |
com.example.mail.smtp
  ├─ SpringSmtpMailAdapter
  ├─ MimeMessageFactory
  └─ SmtpConfiguration
~~~

A pragmatic rule:

> **Do not import `org.springframework.mail.*` or `jakarta.mail.*` from business domain/application layers**, unless the application is intentionally building a MIME/mail transport administration tool.

This constraint can be enforced through module boundaries, package-private implementations, dependency checks, or architecture tests. Exact package names do not matter; **responsibilities** and dependency direction are what count.

## 8. Port–adapter: keeping the application API independent of SMTP

At the application/notification layer, define the interface around the **required capability**, not around `JavaMailSenderImpl`'s constructor:

~~~java
package com.example.notifications.spi;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public record OutboundEmail(
        String senderProfileId,
        List<String> recipients,
        String subject,
        String textBody,
        String htmlBody,
        List<EmailAttachmentRef> attachments,
        Map<String, String> safeTags) {
}

public record EmailAttachmentRef(
        String displayFilename,
        String mediaType,
        String storageReference,
        String contentVersion) {
}

public record MailSubmissionReceipt(
        String transportAttemptId,
        String providerReference,
        Instant submittedAt) {
}

public interface MailDeliveryPort {
    MailSubmissionReceipt submit(
            OutboundEmail message);
}
~~~

This is an **illustrative contract** owned by the application, not a Spring Mail type. In a real system, use stronger types instead of making every field a `String` (for example `SenderProfileId`, `RecipientAddress`, `NotificationId`), validate inputs at the boundary, and avoid passing untyped/schemaless tags.

### Why not expose MimeMessage?

If `MailDeliveryPort.submit(...)` takes a `MimeMessage`:

- Callers must understand MIME nesting, header encoding, and Jakarta Mail dependencies.
- Switching transport to an HTTP email API becomes harder because the contract depends on SMTP/MIME.
- Business unit tests have to initialize a mail session.
- Controls over Bcc, sender authorization, and attachments become scattered.

`OutboundEmail` describes an **authorized email ready to send** from the notification orchestration perspective. The adapter translates it into MIME or an HTTP payload for the specific transport.

### Avoid bloated contracts

A port containing 50 SMTP-specific fields becomes just a renamed passthrough abstraction:

~~~text
smtpHost, smtpPort, smtpUsername, smtpPassword,
startTls, debug, connectionTimeout, mimeBoundary, ...
~~~

Those fields belong in **provider profile/infrastructure configuration**, not as data inside every notification command.

## 9. Spring Mail adapter implementing the port

An example SMTP adapter focused on building MIME, attaching files, and sending:

~~~java
package com.example.mail.smtp;

import com.example.notifications.spi.MailDeliveryPort;
import com.example.notifications.spi.OutboundEmail;
import com.example.notifications.spi.MailSubmissionReceipt;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.time.Clock;
import java.util.UUID;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class SpringSmtpMailAdapter
        implements MailDeliveryPort {

    private final JavaMailSender sender;
    private final SenderProfileResolver senderProfiles;
    private final AttachmentStorage attachments;
    private final Clock clock;

    public SpringSmtpMailAdapter(
            JavaMailSender sender,
            SenderProfileResolver senderProfiles,
            AttachmentStorage attachments,
            Clock clock) {
        this.sender = sender;
        this.senderProfiles = senderProfiles;
        this.attachments = attachments;
        this.clock = clock;
    }

    @Override
    public MailSubmissionReceipt submit(OutboundEmail request) {
        SenderProfile profile =
                senderProfiles.resolveAuthorized(
                        request.senderProfileId());
        try {
            MimeMessage message = sender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(
                    message, true, "UTF-8");

            helper.setFrom(profile.fromAddress());
            helper.setTo(request.recipients().toArray(String[]::new));
            helper.setSubject(request.subject());
            if (request.htmlBody() != null) {
                helper.setText(
                        request.textBody() == null
                                ? "" : request.textBody(),
                        request.htmlBody());
            } else {
                helper.setText(request.textBody(), false);
            }

            for (var attachment : request.attachments()) {
                byte[] bytes = attachments.readBounded(
                        attachment.storageReference(),
                        attachment.contentVersion());

                helper.addAttachment(
                        attachment.displayFilename(),
                        new ByteArrayResource(bytes),
                        attachment.mediaType());
            }

            sender.send(message);

            return new MailSubmissionReceipt(
                    UUID.randomUUID().toString(),
                    null, // Standard SMTP does not always return a provider ID.
                    clock.instant());

        } catch (MessagingException ex) {
            throw new MailPreparationFailure(
                    "MIME_PREPARATION_FAILED", ex);
        } catch (MailException ex) {
            throw new MailTransportFailure(
                    "SMTP_SUBMISSION_FAILED", ex);
        }
    }
}
~~~

`SenderProfileResolver`, `AttachmentStorage`, `SenderProfile`, `MailPreparationFailure`, and `MailTransportFailure` are application-defined abstractions and exceptions. `AttachmentStorage.readBounded` is assumed to verify permissions, version, and size before reading bytes. This example prioritizes clarifying **boundaries** over providing a standalone compilable module.

### Mandatory additions for a production implementation

- `MailTransportFailure` does not classify temporary/permanent/unknown on its own; the application needs a classifier based on SMTP phase and provider response.
- `UUID.randomUUID()` here is an illustrative receipt identifier, **not a provider-recognized idempotency key**. Use an attempt ID created and persisted by the workflow prior to submission.
- The adapter must ensure the sender profile belongs to the tenant/route authorized at the application layer, with defensive checks inside the adapter.
- Addresses, headers, filenames, and bodies must pass appropriate validation.
- Do not load unbounded attachments into RAM for large jobs; use reopenable streams or file-backed sources.
- Never leak raw `MimeMessage` or `MessagingException` into the domain.
- Never equate a successful `send(...)` return with final inbox delivery.
- If transport uses an HTTP API instead of SMTP, implement another adapter for the same capability contract, while mapping outcomes according to that API's semantics.

## 10. SMTP configuration must be isolated in infrastructure

In Spring Boot, a simple configuration:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 15000
      mail.smtp.writetimeout: 15000
~~~

The timeout and endpoint values above are examples only, not configurations for any specific provider. Real secrets must come from a secret manager or runtime injection, never committed to source control.

Proper boundary separation:

~~~text
orders/application:
  requestOrderReceipt(orderId)

notifications/application:
  chooseTemplateAndRecipient(...)
  enqueue(...)

mail/infrastructure:
  read spring.mail.*
  create JavaMailSender
  submit MIME message
~~~

What to avoid:

~~~java
// OrderService knowing the SMTP host and password is an obvious code smell.
@Value("${spring.mail.host}")
String smtpHost;

@Value("${spring.mail.password}")
String smtpPassword;
~~~

Naming a class `EmailService` and letting every business module import it does not guarantee a good boundary. Check: does the interface describe a **notification request**, or is it letting the business layer control transport and raw MIME?

### Multiple SMTP providers

When multiple sending routes exist, use separately configured senders/adapters with explicit `@Qualifier` annotations or a registry; do not mutate host/username/password on a shared singleton `JavaMailSenderImpl` across threads. Provider routing is an **application policy**, whereas connections and authentication belong to the **adapter/configuration**.

## 11. Separating template rendering from SMTP transport

A template is more than just `String subject` and `String html`. It also encompasses:

- Template key and version.
- Language/locale.
- Per-tenant branding.
- Variables from business data.
- HTML escaping/sanitization.
- Plain-text fallback.
- Legal footer/opt-out rules.
- A/B testing or variants.

A clean pipeline:

~~~text
OrderPaid event
     |
     v
Select template key ORDER_RECEIPT
     |
     v
Resolve locale + approved tenant brand
     |
     v
Load safe template variables
     |
     v
Render subject + plain text + HTML
     |
     v
Validate content and store snapshot/version
     |
     v
MailDeliveryPort.submit(...)
~~~

**Who owns templates?** It could be the Notification module, a Marketing Content service, or a specific domain (such as legal invoices requiring immutable content). Decide based on content ownership and lifecycle, but **never force the transport adapter to know how to compute taxes, check order state, or evaluate account permissions**.

### Dynamic templates and retries

When a mail job retries 2 hours later, the template or underlying data may have changed. Two options:

| Strategy | Advantages | Risks |
|---|---|---|
| Snapshot rendered content at intent creation | Consistent content across attempts | Stores more PII, requires retention protection |
| Render at submission time | Can reflect the latest information | Template and data changes alter content |

Choose according to business requirements. **Issued invoices** usually require reliable versioned content; **appointment reminders** may need to verify the current schedule before sending. When rendering dynamically, define policies for approved content, data sources, and idempotency.

## 12. Attachments belong to the content boundary, not domain transport

For PDF/CSV/XLSX files:

~~~text
Domain/Application:
  invoiceId, documentVersion
          |
          v
Document service:
  produces approved PDF
          |
          v
Attachment storage:
  payloadRef, mediaType, displayFilename
          |
          v
Mail adapter:
  ByteArrayResource / FileSystemResource
  MimeMessageHelper.addAttachment(...)
~~~

Do not force `OrderService` to know about `ByteArrayResource` or `MimeMessageHelper`. Conversely, mail transport does not need to know how to calculate invoice totals.

For large files, the mail adapter needs a reopenable stream source and size limits; `ByteArrayResource` fits moderately sized in-memory payloads. **A request from the domain should not carry raw SMTP MIME bytes when that content can be passed via a secure storage reference.**

Controls needed at this boundary:

- Attachment access permissions scoped by tenant and job.
- Payload versioning/immutability.
- Max byte limits and dangerous-file protection.
- Safe display filenames; never leak storage paths.
- MIME content types matching actual content.
- Payload retention windows covering retries.
- Data deletion per retention policy once no longer needed.

## 13. Notification policy: who may send to whom?

The Spring Mail layer **does not decide on its own** whether a notification is lawful or valid for a recipient. Notification policy must answer:

1. Is this email transactional, security, service, or marketing?
2. Does the recipient have a verified/accepted address under product rules?
3. Are there suppression lists, unsubscribes, or bounced-address histories?
4. Which sender profiles/domains is the tenant authorized to use?
5. Are there quiet hours or delivery time windows?
6. Does content expire if delayed too long (OTPs, password reset links)?
7. Should security emails take priority over batch marketing?
8. Should another channel be chosen when email is inappropriate?

**Policy belongs to application/notification orchestration**, though the adapter should still maintain technical safeguards: prevent callers from supplying arbitrary SMTP endpoints, credentials, raw `From` addresses, or unapproved headers.

A mail job scheduled last week does not automatically retain permission to send today. For notifications bound by consent/suppression, **re-evaluate eligibility prior to submission** according to agreed rules.

## 14. Transaction boundary: business databases cannot roll back SMTP

A very common architectural mistake:

~~~java
@Transactional
public void payOrder(OrderId orderId) {
    orderRepository.markPaid(orderId);
    mailSender.send(buildEmail(orderId));
}
~~~

Here, if SMTP succeeds and the database transaction then rolls back, the customer may receive a “payment succeeded” email even though the order was not saved as paid. If SMTP is slow, the transaction holds database connections/locks open unnecessarily. If SMTP fails, the business transaction may roll back despite a valid payment — which can be completely wrong behavior for the business.

You cannot make `JavaMailSender.send(...)` part of a database ACID transaction simply by placing it inside a `@Transactional` method.

### A more stable architecture: transactional outbox

~~~text
BEGIN DATABASE TRANSACTION
  Update business aggregate
  Insert notification intent/outbox row
COMMIT
        |
        v
Dispatcher reads committed outbox row
        |
        v
Rate/eligibility checks
        |
        v
SMTP submission outside business transaction
        |
        v
Persist attempt/status
~~~

With this approach:

- If the transaction rolls back, neither the business update nor the outbox intent exists.
- If the transaction commits and the app crashes immediately afterward, the outbox row survives.
- During an SMTP outage, core business workflows do not hold network connections or roll back.
- Schedulers can retry after restarts.
- The system has an audit trail showing that the notification was requested and how far processing got.

### Example application service

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class OrderPaymentApplication {
    private final OrderRepository orders;
    private final NotificationOutbox outbox;

    public OrderPaymentApplication(
            OrderRepository orders,
            NotificationOutbox outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void confirmPayment(OrderId orderId) {
        Order order = orders.confirmPayment(orderId);
        outbox.insertIfAbsent(
                NotificationIntent.orderPaid(
                        order.id(),
                        order.customerId(),
                        order.paymentVersion()));
    }
}
~~~

`OrderRepository`, `NotificationOutbox`, `OrderId`, and `NotificationIntent` are application abstractions. `insertIfAbsent` needs a unique constraint/UPSERT with an idempotency key; merely checking `exists` before inserting is insufficient without race protection.

### What if business data and outbox live in two databases?

You cannot assume atomicity just because two repository methods carry `@Transactional` if they use different transaction managers or databases. Options include:

- Storing the outbox alongside the source business transaction and using CDC or a reliable event relay.
- A shared event log/transaction boundary where appropriate.
- Explicit coordination and reconciliation mechanisms when atomicity is impossible.

Do not label two independent network writes a “transactional outbox” and assume events can never be lost.

## 15. @TransactionalEventListener(AFTER_COMMIT) does not replace a durable outbox

An after-commit event listener:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void afterOrderPaid(OrderPaid event) {
    notificationGateway.requestReceipt(event.orderId());
}
~~~

helps avoid sending emails before the transaction commits. However, it still runs in-memory inside the **current process**:

~~~text
Order DB commit succeeds
   |
   +-- Process crashes before listener can persist intent
   |
Notification request is lost
~~~

After-commit listeners fit **best-effort notifications** where occasional event loss is acceptable or another reconciliation mechanism exists. For notifications that must not be dropped, persist the **intent/outbox within the same transaction** or use an equivalent durable event relay.

Similarly, `@Async` does not make an event durable on its own. It merely offloads execution to an executor and can still lose work if the process terminates.

### Keep boundaries consistent

With an outbox:

~~~text
Transactional business event
   -> durable outbox
   -> asynchronous notification processor
   -> Spring Mail adapter
~~~

With a best-effort listener:

~~~text
Transactional business event
   -> AFTER_COMMIT listener
   -> notification policy
   -> Spring Mail
~~~

Clearly **state the guarantees** of each flow in your ADR or service contract; never describe both flows as having equal reliability.

## 16. Retry boundary: who decides when retrying is allowed?

A `MailException` can represent:

- SMTP misconfiguration or authentication failure.
- Temporary provider rejection.
- Invalid recipient address.
- Connection drop before or after the provider received DATA.
- MIME/attachment construction failure prior to transport.
- Ambiguous client outcome due to a timeout.

The **adapter** knows technical context such as the SMTP phase, response, and provider-specific codes. The **workflow/application** knows attempt count, business deadlines, email type, whether provider feedback already arrived, and whether duplicates are tolerable.

Therefore, a sound separation of authority is:

~~~text
Transport adapter:
  classify technical outcome
    ACCEPTED
    TEMPORARY_REJECTED
    PERMANENT_REJECTED
    AUTH_OR_CONFIGURATION_ERROR
    UNKNOWN_OUTCOME
          |
          v
Delivery workflow:
  decide retry, pause, fail, expire, reconcile
  based on attempts, deadline, business priority
~~~

Do not let `OrderService` catch every `MailException` and call `mailSender.send(...)` three times in a loop. The domain lacks enough context to tell whether SMTP accepted the message or left it unknown, risking duplicate sends.

### Example technical outcome contract

~~~java
public enum SubmissionOutcomeKind {
    ACCEPTED,
    REJECTED_TEMPORARY,
    REJECTED_PERMANENT,
    ROUTE_UNAVAILABLE,
    UNKNOWN
}

public record SubmissionOutcome(
        SubmissionOutcomeKind kind,
        String safeReasonCode,
        String providerReference) {
}
~~~

This contract may be cleaner than `throws MailException` at the notification workflow boundary. However, the adapter must not wrongly assume every exception is temporary. If it is uncertain whether the server accepted the message, return `UNKNOWN` and let the workflow handle it cautiously.

## 17. SMTP outcome UNKNOWN: the boundary that cannot be made atomic

A scenario:

~~~text
Worker claims job #583
    |
    v
SMTP sends DATA
    |
    v
Provider accepts message
    |
    v
Network breaks before client observes final reply
    |
    v
Worker sees exception
    |
    v
Database still says PROCESSING
~~~

If a subsequent worker sees the lease timeout and immediately resends, the recipient may receive two emails. `FOR UPDATE SKIP LOCKED`, `@Transactional`, and `@Async` do not solve atomicity between the database and SMTP.

Options:

1. Persist attempt identity and `UNKNOWN` state whenever the result is uncertain.
2. Reconcile against provider message traces where available.
3. Use a provider idempotency feature **only when the provider truly offers and guarantees those semantics**.
4. Keep a business idempotency key to prevent duplicate initial intents.
5. Define retry/failover rules per notification type based on duplicate risk.
6. Never mistake the `Message-ID` header for an exactly-once delivery guarantee.

This is the critical boundary between **notifications processable with at-least-once semantics** and **exactly-once email delivery** — the latter usually cannot be promised with plain SMTP under real failure conditions.

### Describe guarantees honestly

A service contract can state:

> “Every committed notification intent is persisted in the outbox and attempted according to the retry policy. Duplicates are possible when provider outcomes are uncertain; the system records attempts and runs a reconciliation process.”

This is clearer and safer than promising “exactly one email, never lost or duplicated” without mechanisms capable of proving it.

## 18. Scheduler and state machine boundaries

If an email must be sent at 09:00, Spring Mail does not need to know the business schedule. The dispatcher can persist:

~~~text
notification_id
status = PENDING
scheduled_at = 2026-11-15T09:00:00Z
available_at = 2026-11-15T09:00:00Z
attempt_count = 0
expires_at = nullable
~~~

A state machine:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> CLAIMED: due and owner acquired
    PENDING --> CANCELLED: cancel before submission
    PENDING --> EXPIRED: deadline passed
    CLAIMED --> PROCESSING: record attempt
    CLAIMED --> PENDING: safe release
    PROCESSING --> SUBMITTED: provider accepted
    PROCESSING --> RETRY: classified temporary rejection
    PROCESSING --> FAILED: permanent error
    PROCESSING --> UNKNOWN: ambiguous outcome
    RETRY --> CLAIMED: next available time
    UNKNOWN --> SUBMITTED: reconciliation confirmed
    UNKNOWN --> RETRY: approved replay policy
~~~

These statuses are **application-defined enums**. There is no built-in `PENDING`, `RETRY`, or `UNKNOWN` job lifecycle inside `JavaMailSender`.

### scheduledAt and availableAt are not the same

- `scheduled_at`: the business-desired send time, preserved to measure delay.
- `available_at` or `next_attempt_at`: the earliest time eligible for retry/deferral due to quota, errors, or policy.

When a provider fails, shift `available_at` rather than overwriting the original schedule. When a job expires (for example, an OTP), the workflow marks `EXPIRED` rather than sending stale content late.

### The scheduler is only a wake-up trigger

Spring `@Scheduled` or Quartz can trigger the dispatcher, but the **database/outbox is the durable source of state**. Do not create thousands of in-RAM `ScheduledFuture` tasks and treat that as durable scheduling.

## 19. Multi-worker claiming and workflow ownership

When multiple replicas run, each replica may execute a scheduler. Two workers must never process the same job concurrently in an uncontrolled way:

~~~text
Worker A -> SELECT PENDING job #583
Worker B -> SELECT PENDING job #583
Worker A -> SMTP send
Worker B -> SMTP send
~~~

One PostgreSQL approach is atomic claiming via `FOR UPDATE SKIP LOCKED`:

~~~sql
WITH selected AS (
    SELECT id
    FROM notification_outbox
    WHERE status IN ('PENDING', 'RETRY')
      AND available_at <= CURRENT_TIMESTAMP
      AND scheduled_at <= CURRENT_TIMESTAMP
      AND (expires_at IS NULL
           OR expires_at > CURRENT_TIMESTAMP)
    ORDER BY available_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE notification_outbox AS job
SET status = 'CLAIMED',
    claim_token = :claim_token,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    updated_at = CURRENT_TIMESTAMP
FROM selected
WHERE job.id = selected.id
RETURNING job.id, job.claim_token;
~~~

The claim runs in a **short transaction**. Never hold the transaction and row locks open across network SMTP calls. When saving the outcome, updates must verify `claim_token` and expected status to prevent stale workers from overwriting newer state.

### Expired lease does not mean unsent

When a worker crashes after SMTP accepted but before updating the DB, the job may appear `PROCESSING` with an expired lease. Recovery must recognize that an attempt may already have started, rather than automatically resending without checking `UNKNOWN` and policy.

### Separate concurrency control from rate limiting

`ThreadPoolTaskExecutor.maxPoolSize` bounds concurrent workers; it does not limit messages/second or daily recipient quotas. The workflow/dispatcher needs dedicated rate admission when a shared provider account serves multiple tenants or services.

## 20. API boundary: accept send intents, not raw SMTP commands

For a standalone Notification Service, the API should accept a **validated notification intent**:

~~~http
POST /internal/notifications
Content-Type: application/json
Idempotency-Key: ORDER_PAID-583-v1

{
  "type": "ORDER_RECEIPT",
  "businessRef": "ORDER-583",
  "channel": "EMAIL",
  "locale": "vi-VN",
  "scheduledAt": "2026-11-15T09:00:00+07:00"
}
~~~

Based on the caller's identity, the server resolves the tenant, authorization for `businessRef`, allowed notification types, recipients, and approved sender profiles. Never let clients specify arbitrary values such as:

~~~json
{
  "smtpHost": "10.0.0.1",
  "smtpPort": 25,
  "smtpPassword": "anything",
  "from": "admin@example.com",
  "unlimitedRetries": true
}
~~~

Doing so both violates domain boundaries and turns the notification endpoint into an open relay/SSRF surface.

### What semantics should a synchronous response have?

Once the API persists the notification intent:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "notificationId": "notif-opaque-583",
  "status": "QUEUED"
}
~~~

`202 Accepted` in this example indicates the **request was accepted for processing**, not delivered via SMTP. If an API opts for synchronous SMTP submission, the contract must state explicitly that it is synchronous submission and still not promise inbox delivery.

### Idempotency keys must not be reused carelessly

An HTTP retry after a timeout may reuse the same `Idempotency-Key` to retrieve the original result. However, legitimately resending an invoice a second time requires a distinct event/version key. Scope uniqueness by tenant, type, and business event rather than permanently blocking all future emails to the same recipient.

## 21. Event contracts: domains should not emit MIME bytes

An event consumed by a Notification Service:

~~~json
{
  "eventId": "evt-583-1",
  "eventType": "OrderPaid",
  "aggregateId": "ORDER-583",
  "aggregateVersion": 7,
  "tenantRef": "tenant-opaque",
  "occurredAt": "2026-11-12T09:00:00Z"
}
~~~

An event **does not necessarily** contain email addresses, HTML bodies, or attachment bytes. The notification worker can obtain needed data from an approved read model or snapshot in the event/outbox, depending on consistency and retention needs.

Questions when designing events:

- Does the event carry a stable **identity** to prevent duplicate processing?
- Does it have versioning/schemas so consumers can upgrade independently?
- Does the consumer have enough context without N+1 callbacks into the domain?
- Could referenced data change before rendering time?
- What sensitive data is inside the event, and how long is it retained in the broker?
- If the Notification Service is down for days, from which source can it replay?
- If events arrive out of order, how does the worker react?

Never assume a broker guarantees exactly-once business side effects; consumers must still be idempotent. Publishing events solely after DB commit without a durable outbox still leaves a crash window between commit and publish.

## 22. Choosing same process, separate module, or separate microservice?

A **logical** boundary does not have to be a **deployment** boundary. Common levels of separation:

| Option | When appropriate | Pros | Trade-offs |
|---|---|---|---|
| Separate packages in one app | Small app, single team | Fast to implement, minimal infra | Boundaries are easy to cross accidentally |
| Modular monolith | Multiple modules, single deployment | Enforces dependencies, easier transactions/outbox | Scaling/deployment remains coupled |
| Separate worker process from same codebase | SMTP workload differs from web workload | Independent scaling/shutdown, shields HTTP | Requires shared queue/outbox and ownership |
| Notification microservice | Multiple product teams/channels, independent ops | Independent API/SLA/scaling, centralized policy | Network, broker, data ownership, distributed failures |
| Managed email platform | Team prefers not to run deep mail infra | Sending/bounce/reputation tooling may be provided | Vendor semantics, quotas, data governance, lock-in |

No single architecture fits every organization. Evaluate using these criteria:

1. Number of business teams depending on notifications.
2. Frequency of template, policy, and provider changes.
3. Volume and burstiness of email traffic.
4. SLA, observability, and audit requirements.
5. Security and secret isolation needs.
6. Ability to operate brokers, outboxes, queues, and independent deployments.
7. Data residency boundaries across tenants/regions.
8. Latency, complexity, and incident coordination costs.

### When should you avoid splitting a microservice immediately?

If a single application sends a handful of email types and the team lacks mature messaging/observability infrastructure, introducing an Email Service network hop can increase failures without commensurate value. A **modular monolith** with `NotificationPort`, an outbox, and `SpringSmtpMailAdapter` usually keeps future extraction clean without immediately running a new service.

### When should you split?

If multiple teams continually duplicate SMTP credentials, templates, and delivery logic; batch traffic degrades HTTP latency; or security/compliance mandates isolating mail secrets to one workload, there is a clear case for separating deployments. When splitting, maintain stable API/event contracts rather than shipping JPA entities or `MimeMessage` across HTTP.

## 23. Do not confuse a “shared Java library” with a “central notification service”

A shared library:

~~~text
mail-common.jar
  +-- buildMime(...)
  +-- send(...)
~~~

eliminates some duplicated code, yet **each application still independently**:

- Configures credentials.
- Calls providers directly and consumes account quota.
- Decides retries and timing.
- Stores logs/status, if at all.
- Enforces consent and suppression.
- Redeploys whenever the library changes.

Conversely, a centralized notification service can own orchestration, quotas, the outbox, secrets, and delivery tracking—while adding a network boundary, idempotency contract, backlog management, and queue operations.

**Code sharing and runtime sharing are different decisions.** Never call a shared JAR a “mail platform” if authority and state remain fragmented across apps.

### When is a shared library still useful?

For applications sending controlled local notifications, a library can provide:

- A typed `NotificationClient`.
- Request schema validation.
- OpenTelemetry correlation.
- Infrastructure-level MIME/attachment helpers.
- Standardized safe reason codes.

However, the library must not force business services to depend directly on `JavaMailSenderImpl` just to wrap a `send()` call.

## 24. Who owns recipient resolution?

An invoice email requires a recipient address. There are several options:

**A. The domain application resolves the recipient:**

~~~text
InvoiceIssued
   -> domain produces approved recipient reference
   -> NotificationIntent
~~~

Advantage: the domain knows exactly who is authorized to receive the invoice. Risk: a snapshotted email address can become stale or leak via events.

**B. The notification application queries a directory/profile service:**

~~~text
InvoiceIssued(customerId)
   -> query customer contact preferences
   -> resolve email address
~~~

Advantage: keeps PII out of events and uses up-to-date addresses. Risk: reading after a delay may point to a changed recipient or fail authorization, diverging from the original event.

### Pragmatic rule

- The **domain** determines the **authorized recipient party** by business rules (customer/account/participant).
- **Notification policy** determines the **eligible address/channel** and current preferences.
- The **transport adapter** only accepts **approved addresses** and executes submission.

For sensitive documents, bind the recipient to the issued transaction/version. Never let the adapter query a generic customer table and choose arbitrary recipients on its own.

## 25. Multi-tenancy: security boundaries and quotas must work together

A Notification Service serving multiple tenants needs fields such as:

~~~text
tenantId
notificationId
businessEventKey
templateKey
senderProfileId
providerAccountId
recipientRef
status
~~~

Before handing off to SMTP:

~~~text
Trusted caller/claim
    |
    v
Resolve tenant from authenticated context
    |
    v
Validate business reference ownership
    |
    v
Check sender profile and template permissions
    |
    v
Apply tenant + provider account quotas
    |
    v
Submit through approved provider adapter
~~~

Never trust a caller-supplied `tenantId` or `smtpHost` without authorization. A tenant must not select another tenant's sender profile or force workloads onto an administrative account.

### Quota scopes and secret scopes may differ

Two credentials can belong to the same provider account and share one quota. Rotating credentials does not reset quota. If tenants A and B share an account, enforce an account-wide gate in addition to per-tenant gates; if they use separate accounts, do not merge quotas incorrectly.

### Avoid data leaks through observability

Never use recipient emails, subjects, raw MIME, or message bodies as metric labels. With many tenants, putting `tenantId` on every time series also creates high cardinality. Aggregate by tier/lane/provider in metrics and look up detailed IDs in access-controlled audit logs.

## 26. Separating outbound sending from inbound mailbox reading

`JavaMailSender` is designed for **sending** mail. Reading mailboxes over IMAP/POP3 requires Jakarta Mail `Store`/`Folder` or Spring Integration Mail inbound adapters.

Two distinct flows:

~~~text
Outbound:
  Business event
      -> Notification workflow
      -> Spring Mail/SMTP adapter
      -> Provider

Inbound:
  Provider mailbox
      -> IMAP/POP3 receiver
      -> Dedup/checkpoint
      -> Message validation/security
      -> Inbound business command/event
~~~

Never let an inbound parser invoke arbitrary business repositories directly after reading an email body. Inbound emails are **untrusted input**; enforce sender/workflow authentication, anti-spoofing checks, attachment validation, idempotency, and mapping to authorized commands.

### Why might deployments be separated?

An inbound receiver manages IMAP connection lifecycles, UID/UIDVALIDITY checkpoints, folder state, and reconnect policies, whereas an outbound dispatcher manages SMTP quotas and submission attempts. They have different failure modes and scaling profiles.

If a system only sends mail, do not build an unnecessary inbound service. If inbound processing is required, separate at least the **modules and credentials** clearly; avoid one shared “MailService” holding full mailbox read/write privileges.

## 27. Assigning ownership for every concern

A responsibility matrix keeps teams from finger-pointing:

| Concern | Team or bounded context that should own it | Contract to make explicit |
|---|---|---|
| Business trigger conditions | Domain team | Business event/notification request |
| Authorized recipient party | Domain + profile policy | Recipient reference/eligibility |
| Consent/suppression | Notification/consent authority | Check at send time |
| Templates/locale/branding | Content/notification team | Version, variables, approval |
| PDF/document generation | Document/domain service | Immutable payload ref, MIME type |
| Outbox/attempt lifecycle | Notification platform | Status, retries, idempotency |
| SMTP credentials/TLS | Mail infrastructure/platform | Secret access, rotation |
| Provider quotas/fairness | Delivery operations/platform | Account/tenant rate budgets |
| Delivery/bounce webhooks | Provider integration | Verified events and correlation |
| SLOs/alerts | Platform + product owner | SLOs per notification type |
| Incident replay | Delivery operations with policy | Approval, audit, duplicate risk |

This is an ownership proposal, not a mandatory org chart. In a small organization, one team may own multiple rows; what must be avoided is nobody owning anything because logic is scattered across every service.

## 28. Blast radius and bulkhead isolation

A large system typically has multiple email classes:

~~~text
SECURITY        OTP, password reset, login alert
TRANSACTIONAL   Order receipt, payment confirmation
OPERATIONAL     Error report, system notification
BULK            Newsletter, campaign
~~~

If all share a single FIFO queue and executor, 100,000 bulk jobs can stall OTPs unacceptably. If a provider hangs, blocked threads can even starve HTTP requests.

To limit blast radius:

1. Separate **notification lanes** by SLA and content type.
2. Use bounded executors/queues and backpressure.
3. Enforce quotas per **provider account** and **tenant**.
4. Cap SMTP concurrency separately per account/route.
5. Use priority and fair scheduling rather than plain FIFO.
6. Configure connect/read/write timeouts, retry backoff, and circuit breakers.
7. Never let a bulk provider outage roll back domain transactions.
8. Retain intents durably when quota or providers are unavailable.

Dedicating a separate `ThreadPoolTaskExecutor` to mail instead of reporting jobs helps, yet **does not establish a cluster-wide quota**. Ten pods can hit the same account simultaneously; enforce shared rate admission matching the actual provider quota scope.

### Do not assume “splitting services” isolates every failure

Two microservices can still share a database connection pool, Redis quota store, provider account, or tenant budget. Splitting deployments helps isolate certain faults, but true blast radius depends on **shared resources** and their failure isolation.

## 29. Security boundary: not every service needs SMTP secrets

In a large system, read access to SMTP passwords or API tokens should be granted only to workloads that actually submit email.

~~~text
Order service       -> no SMTP credential
Billing service     -> no SMTP credential
Notification API    -> possibly no direct SMTP credential
Mail dispatcher     -> mail-specific credential
Provider callback   -> webhook verification secret
~~~

Defense layers:

- Secret managers and workload identities/permissions.
- Egress rules restricted to approved SMTP/API endpoints.
- TLS, hostname verification, and appropriate TLS version policies.
- Sender/domain verification and SPF/DKIM/DMARC at the provider/domain.
- Disallow callers from setting arbitrary `From`, `Reply-To`, or endpoints.
- RBAC over templates, payloads, mail jobs, and support tooling.
- Auditing changes to sender profiles, credentials, and quota policies.
- Never log raw messages, SMTP AUTH payloads, or tokens.
- Rotation and revocation procedures avoiding unnecessary downtime.

### Avoid storing credentials in the outbox

The outbox should store only:

~~~text
senderProfileId=ORDERS
providerAccountId=primary-prod
~~~

instead of:

~~~text
smtpPassword=...
oauthAccessToken=...
~~~

Workers fetch secrets at runtime for the authorized profile. During key rotation, queued jobs will not be stuck holding stale secrets in the database.

### Provider failover must respect sender authorization

A `From` address verified on Provider A is not necessarily authorized on Provider B. On failover, the application checks sender eligibility and policy; the infrastructure adapter connects to route B using dedicated credentials. Never blindly “swap the host” when account A fails and send the same `From` through B ignoring SPF/DKIM/DMARC.

## 30. Delivery feedback is a separate inbound event boundary

When a provider sends webhooks for `delivered`, `bounced`, `complained`, or `deferred`:

~~~text
Email provider
     |
     v
Webhook endpoint
     |
     v
Verify signature / timestamp / replay protection
     |
     v
Normalize provider event
     |
     v
Correlate to provider message / submission attempt
     |
     v
Idempotently update delivery state
     |
     v
Business events only when policy requires
~~~

Never allow a public HTTP webhook to directly update `orders.status` just because its payload contains an `orderId`. Provider events can arrive duplicated, out of order, delayed, or forged if unverified.

Fields to inspect:

| Field | Purpose |
|---|---|
| Provider event ID | Callback deduplication |
| Provider message/attempt ID | Correlation |
| Event type | Delivered, bounced, deferred, complaint |
| Provider event time | Timestamp reported by the provider |
| Received time | Timestamp received by the application |
| Verified sender/signature | Origin authentication |
| Tenant/account scope | Prevents cross-tenant updates |

### One email with multiple recipients

If one SMTP submission contains multiple To/Cc/Bcc recipients, delivery and bounces can differ per recipient. A job-level `delivered=true` flag may be insufficient; consider per-recipient outcome storage. Because not all providers emit per-recipient feedback, retain `NOT_TRACKED` or null when no evidence exists rather than inferring delivery success.

## 31. Observability across intent, attempts, and delivery

A useful operational metric set:

| Metric | Question answered |
|---|---|
| `notification_intent_created_total` | How many valid requests were created? |
| `notification_outbox_ready` | How many due jobs are still unsent? |
| `notification_oldest_due_age_seconds` | How long has the oldest due job been waiting? |
| `mail_submission_attempt_total` | How many times was the provider actually called? |
| `mail_submission_accepted_total` | How many attempts did the provider accept? |
| `mail_submission_failure_total` | At which phase did failures occur? |
| `mail_unknown_outcome_total` | How many attempts require reconciliation? |
| `mail_quota_denied_total` | How many attempts were gated by quota? |
| `mail_provider_throttle_total` | How often did the provider return throttling? |
| `mail_delivery_event_total` | How many delivered/bounced events arrived (if tracked)? |
| `mail_notification_expired_total` | How many intents expired before sending? |
| `mail_dispatch_lag_seconds` | How long from scheduled time to attempt? |

**Never label a non-throwing `mailSender.send(...)` count as “delivered count”.** It represents only accepted submission under adapter semantics.

### Tracing across boundaries

~~~text
trace/span: OrderPayment.confirm
      |
      v
eventId / notificationId
      |
      v
Outbox claim
      |
      v
submissionAttemptId
      |
      v
providerReference (if available)
      |
      v
provider callback (possibly hours later)
~~~

Traces do not always outlive email delivery delays; persist correlation IDs durably in database/attempt history. Never attach recipient emails, subjects, or raw MIME to telemetry attributes without appropriate protection policies.

### Log with safe reason codes

~~~text
event=mail_submission_failed
notificationId=opaque-id
attemptId=opaque-attempt
providerProfile=PRIMARY
phase=SMTP_DATA
reasonCode=SMTP_OUTCOME_UNKNOWN
tenantTier=BUSINESS
~~~

Never log raw `MailException.getMessage()` by default: SMTP providers may echo recipient addresses or sensitive details.

## 32. Notification Platform SLOs cannot be just SMTP uptime

Common targets:

- Percentage of transactional emails **beginning submission** within N seconds of `scheduled_at`.
- Maximum age of OTPs sitting in the outbox.
- Submission acceptance rate broken down by provider/lane.
- Time to detect and remediate AUTH/TLS failures.
- Percentage of notification jobs expiring unsent.
- Percentage of feedback callbacks consumed idempotently.

**Delivery into inbox** depends on providers and receiving mail servers; define delivery SLOs only when reliable measurement signals exist. Never claim inbox delivery SLOs backed only by SMTP accepted counts.

Example two-tier SLOs:

~~~text
Orchestration SLO:
  99.9% transactional jobs begin a permitted attempt
  within 60 seconds of scheduledAt,
  excluding explicitly delayed provider quota windows.

Submission SLO:
  99.5% eligible attempts receive a definitive
  accepted/rejected outcome within 30 seconds.
~~~

These figures illustrate contract phrasing only; **they are not universal SLA recommendations**. Measurement methods, windows, exclusions, deadlines, and guarantees must be agreed upon before enforcement.

### Alert on backlog age

A system with a zero SMTP error rate can still send zero mail if the quota gate keeps denying permits. Track **demand, admission, and submission** together. An outbox holding millions of future-scheduled jobs is not necessarily an incident; a backlog that is **already due** and breaching SLAs is what triggers alerts.

## 33. Testing each boundary properly

A sound architecture gives every test layer a clear target:

| Boundary | What the test must prove |
|---|---|
| Business → Intent | Correct event, recipient role, no duplicate intents |
| Intent → Notification policy | Consent, sender authorization, locale, template selection |
| Notification → Outbox | Atomic commit/rollback with the business DB |
| Outbox → Dispatcher | Proper claiming, no premature sends, idempotency, lease/fencing |
| Dispatcher → Rate gate | Tenant/account quotas, denied deferral, no SMTP attempt |
| Renderer → OutboundEmail | Content, template version, HTML escaping, attachment references |
| OutboundEmail → SMTP adapter | MIME headers, To/Cc/Bcc, attachments, text/HTML |
| SMTP adapter → Provider | TLS, AUTH, timeouts, known reply codes, partial/unknown outcomes |
| Provider webhook → State | Signature validation, dedup, out-of-order events |
| SLO/operations | Metrics, backlog age, incident and recovery |

### Domain unit tests without SMTP

~~~java
@Test
void paidOrderCreatesOneReceiptIntent() {
    // Fake repository + fake outbox.
    orderApplication.confirmPayment(orderId);
    verify(outbox, times(1)).insertIfAbsent(
            argThat(intent ->
                    intent.templateKey()
                            .equals("ORDER_RECEIPT")));
}
~~~

This test illustrates intent verification; `verify`, `times`, and `argThat` are helpers from mocking libraries such as Mockito. Even when the SMTP server is down, domain unit tests must run offline.

### MIME adapter tests without real mail

Using `JavaMailSenderImpl.createMimeMessage()` and `MimeMessageHelper`, you can build MIME in memory and inspect `BodyPart.getFileName()` and content types to verify correctness. SMTP integration tests use a sink/test server such as Mailpit or GreenMail with synthetic data.

### Architecture tests

Architecture rules can enforce:

~~~text
orders.domain must not depend on org.springframework.mail
orders.application must not depend on jakarta.mail
notifications.api must not expose JavaMailSender
mail.smtp may depend on notifications.spi
~~~

These rules can be enforced via module structure, ArchUnit, or automated dependency checks. Do not blacklist every occurrence of the word “mail” in package names; the goal is preventing **framework/transport types** from leaking into business contracts.

## 34. Contract testing when notification is a microservice

When a domain service invokes a Notification Service over HTTP or a message bus, the boundary sits at the network and schema. Avoid sharing a JPA entity or `MimeMessage` as the payload contract because:

- Internal schemas evolve with persistence/transport needs.
- Older consumers may not understand newly required fields.
- It creates build/deploy coupling across teams.
- Sensitive data can be serialized accidentally.

Maintain a **versioned contract**:

~~~json
{
  "schemaVersion": 2,
  "notificationType": "ORDER_RECEIPT",
  "eventId": "evt-583-v7",
  "businessRef": "ORDER-583",
  "recipientRef": "customer-opaque-101",
  "templateVersion": "2026-11",
  "requestedAt": "2026-11-12T09:00:00Z"
}
~~~

Important questions:

1. Do new fields have clear defaults?
2. Do older consumers still receive prior event versions?
3. How are unknown notification types rejected or quarantined?
4. Are schema errors retried or treated as permanent failures?
5. Does EventId prevent duplicate broker deliveries?
6. Is notification data purged or anonymized per retention policy?
7. Is sender authorization re-verified by the service rather than trusting every field?

### Contract tests should verify behavior, not only JSON shape

A producer/consumer test should prove:

~~~text
Valid ORDER_RECEIPT event
  -> notification accepted and queued

Same eventId delivered twice
  -> one business notification intent

Unsupported schema version
  -> explicit rejection/quarantine with reason

Unauthorized tenant sender profile
  -> no SMTP submission
~~~

When evolving schemas, use controlled additive evolution; never break existing field semantics and hope every service deploys simultaneously.

## 35. Migration: from direct sending to clear boundaries

An existing application may contain:

~~~text
OrderService -> JavaMailSender
UserService -> JavaMailSender
BillingService -> JavaMailSender
CampaignJob -> JavaMailSender
~~~

You do not have to split out a microservice in a single release. You can migrate incrementally in phases:

### Phase A: wrap behind an adapter with an explicit contract

First create:

~~~text
NotificationPort
  requestOrderReceipt(...)
  requestPasswordReset(...)

SpringSmtpMailAdapter
  send(outboundEmail)
~~~

The application may still send synchronously if that is the existing behavior, but business code no longer imports `JavaMailSender` and `MimeMessageHelper`.

### Phase B: unify notification policy

Move template selection, sender profiles, consent/eligibility checks, and recipient resolution into the notification application module. Avoid modifying every flow at once; start with a low-risk email type.

### Phase C: introduce a durable outbox

For emails requiring reliability, replace direct sends with `enqueue` inside the business transaction. Add a dispatcher, state tracking, attempt history, idempotency keys, and concurrency/rate limits.

### Phase D: split a separate worker process when needed

Run the mail dispatcher in a separate worker deployment from the HTTP app, sharing the codebase or in a dedicated module. By now, the outbox/API contract already separates operational responsibilities.

### Phase E: extract a Notification Service if a business case exists

When traffic and team ownership demand it, replace local module calls with a durable integration contract. Never build a network service first and then figure out how to pass `MimeMessage` over the API; keep request types purely application-level.

### Phase F: operate multi-provider routing and delivery feedback

Add provider routing/qualifiers, account/tenant quotas, delivery webhooks, dashboards, and runbooks as product needs grow. Not every system needs every capability on day one.

## 36. Migrating without duplicate sends during parallel runs

A common migration pitfall:

~~~text
Old code:
  OrderService directly sends email

New code:
  OrderPaid event also creates outbox job

During rollout:
  Same order triggers BOTH paths -> two emails
~~~

To avoid this:

1. Assign explicit notification types and path ownership.
2. Use a feature flag or routing rule ensuring **only one source may emit intents** for a business event.
3. Provide a stable business event/idempotency key.
4. Record a migration version or source reference for reconciliation.
5. Before enabling the new path, verify the old path is disabled for the same scope.
6. Use shadow mode **without SMTP submission** when comparing templates and payloads.
7. Monitor accepted submissions and duplicate business references during rollout.

Do not rely on emitting two events with the same `Message-ID` hoping mail clients will deduplicate them.

### Cutover for pending jobs

If the old scheduler still holds pending jobs, plan carefully:

- Migrate records into the new outbox, or let old workers drain?
- Are terminal/processing states of old jobs reconciled?
- Will jobs that started submission with uncertain outcomes be replayed?
- Did tenant/route mappings or template versions change between old and new systems?
- Is there a crisp cutoff time for stopping old producers and workers?

This is both a **data migration and a workflow migration**, not merely swapping dependency injection.

## 37. How to write an Architecture Decision Record (ADR)

A major boundary decision should be documented so other teams understand the rationale and trade-offs. Template:

~~~markdown
# ADR-012: Spring Mail lives only inside the outbound transport adapter

## Context
- Multiple domains send emails through the same SMTP provider.
- Business layers currently depend directly on Jakarta Mail classes.
- Durable retries and per-account quotas are required.

## Decision
- Domains emit typed business events / notification intents.
- The notification module owns policy, outbox, and job state.
- The mail infrastructure adapter implements MailDeliveryPort
  using JavaMailSender + MimeMessageHelper.
- Workers submit SMTP outside domain DB transactions.
- Provider feedback updates delivery state via a verified adapter.

## Consequences
- More abstractions and database jobs.
- Requires workers, metrics, and incident runbooks.
- Decouples domains from SMTP.
- Does not guarantee exactly-once SMTP; UNKNOWN requires reconciliation.

## Alternatives considered
- Continuing direct JavaMailSender calls.
- Shared SMTP utility library.
- Immediate extraction of a standalone Notification Service.

## Review triggers
- Traffic frequently hits account quotas.
- Multiple teams need independent policy/scaling.
- Provider change or new compliance boundary.
~~~

You do not have to use the exact identifier ADR-012; it is an illustrative format. An ADR should state:

- **Decision**: exact boundaries and which dependencies are forbidden or permitted.
- **Context/rationale**: problems being solved and quality attributes.
- **Trade-offs**: operational overhead, latency, and reliability.
- **Rejected alternatives**: and why.
- **Review triggers**: when scale or requirements change.

An ADR stating only “use microservices for clean architecture” without defining ownership, states, retries, and failure modes is insufficient for implementation.

## 38. Decision matrix: reference architectures

### Architecture A — Small single app, best-effort email

~~~text
Business service
   -> NotificationPort
   -> SMTP adapter
~~~

Suitable when emails are non-critical and losing an occasional notification after a crash is acceptable. Document the guarantee honestly rather than claiming outbox durability. `@TransactionalEventListener(AFTER_COMMIT)` can still prevent sending before commit, though it does not replace a durable queue.

### Architecture B — Modular monolith, business-critical email

~~~text
Business transaction
   -> business data + outbox in same database
   -> dispatcher
   -> MailDeliveryPort
   -> Spring Mail adapter
~~~

Fits many growing Spring systems. Keeps transactions simple and code boundaries clean; worker deployments can be split later.

### Architecture C — Multi-team platform

~~~text
Order/Billing/Identity services
         |
         v
Durable events / Notification API
         |
         v
Notification service
  policy + templates + outbox
         |
         v
Delivery workers per provider/lane
  +-- SMTP adapter
  +-- HTTP mail API adapter
         |
         v
Provider feedback / delivery state
~~~

Appropriate when operational policies, SLAs, scaling, or security demand a dedicated service. Trade-offs include network failures, schema versioning, producer-side outboxes, and duplicate event handling.

### Architecture D — Managed notification platform

~~~text
Business intent
   -> validated notification adapter
   -> external managed notification API
~~~

Can reduce self-built template, rate-limiting, and delivery-tracking code depending on vendor capabilities. Even so, the application still needs idempotency, durable intents for critical flows, authorization, privacy, secret management, and contracts insulated from vendor-specific quirks.

## 39. Criteria for deciding service boundaries

Ask concrete questions:

| Question | Signals favoring a module | Signals favoring a separate service/worker |
|---|---|---|
| Who owns it? | One shared team | Multiple teams needing independent releases |
| Shared transaction needed? | Business + outbox in the same DB | Durable event contract and clear ownership |
| Traffic profile? | Low, steady | Large batches/spikes affecting request paths |
| Provider credentials? | Safe within the same app | Workload-level secret isolation required |
| SLA? | Best effort | Dedicated lanes, worker scaling, and 24/7 ops |
| Template changes? | Infrequent, tied to releases | Frequent, spanning many products |
| Multi-channel? | Just a few emails | Email, push, SMS, and in-app sharing policies |
| Provider setup? | One simple configuration | Multiple accounts, routes, quotas, and delivery events |
| Operational maturity? | No durable broker/platform yet | Existing queues, tracing, and incident ownership |

**Never decide solely by counting lines of email code.** A 100-line adapter might require isolated deployment for security/SLA reasons, while thousands of template lines may happily remain inside a modular monolith if team and lifecycle are unified.

## 40. Anti-patterns when setting Spring Mail boundaries

### 40.1. Domain services constructing MimeMessage directly

~~~java
@Service
public class OrderService {
    private final JavaMailSender sender;
    // ...
}
~~~

The domain becomes coupled to the SMTP framework, hard to switch providers, and hard to unit test offline. Move MIME construction into an infrastructure adapter and have the domain emit intents or call a typed notification port.

### 40.2. EmailService doing everything

An `EmailService` that queries orders, calculates taxes, checks consent, renders templates, drives SMTP, retries, and updates delivery states becomes a **god object**. Separate responsibilities across policy, workflow, renderer, and transport adapter.

### 40.3. Public API accepting SMTP host/password

Callers could create an open relay/SSRF vector or abuse credentials. Approved provider profiles must be resolved server-side with secrets stored in infrastructure.

### 40.4. Wrapping send() in @Transactional

SMTP does not roll back with the database. Sending inside a domain transaction can deliver emails for rolled-back transactions and hold locks open. Use an outbox when notifications require atomic intent.

### 40.5. Treating @Async as durable messaging

An in-RAM executor queue disappears on process restart. `@Async` keeps request paths non-blocking, but does not replace persistence, retries, or ownership.

### 40.6. Assuming AFTER_COMMIT listeners never lose events

After DB commit, the process can still crash before the listener records the send request. If message loss is unacceptable, use a transactional outbox or durable event relay.

### 40.7. Letting the domain retry MailException directly

The domain does not know the SMTP phase or whether the provider accepted the message. Blind retries risk duplicates. Let the adapter classify technical outcomes and the workflow apply retry policy.

### 40.8. Resending every PROCESSING job after lease timeout

Lease expiration does not prove the provider never accepted the message. Track attempt history, `UNKNOWN`, and reconciliation.

### 40.9. Treating SMTP accepted as inbox delivered

Submission success does not mean the recipient saw the email. Delivery feedback is a separate integration boundary when evidence exists.

### 40.10. Sending MimeMessage over a message broker

That couples messaging contracts to Jakarta Mail serialization. Broker events should use versioned typed intents/references rather than forcing consumers onto MIME implementations.

### 40.11. Sharing mail-common.jar while every service holds credentials

A library does not centralize quotas, secrets, or state. Decide explicitly whether a shared runtime is needed; a library only shares code.

### 40.12. Splitting a microservice prematurely and calling it over sync HTTP for all email

Making checkout requests block on Notification Service and SMTP increases latency and cascading failures. For non-urgent emails, prefer durable enqueue returning `202 Accepted` or a job ID per contract.

### 40.13. Letting the transport adapter choose business recipients

An SMTP adapter must not query “which customers paid?” or pick recipients from unauthorized data. Domain/notification policies select eligible recipients; the adapter sends only to the approved list.

### 40.14. Exposing raw SMTP exceptions to business services

`MessagingException` and `MailSendException` are technical details. Do not couple business retry or compensation logic to provider exception text.

### 40.15. Placing template logic inside the JavaMailSender wrapper

Whenever marketing tweaks copy, infrastructure deployments change—easily tangling sender, locale, and consent logic. Keep template policy and rendering inside the notification/content module.

### 40.16. Storing credentials and HTML payloads uncontrollably in the outbox

Credentials must come from secret stores; payloads must follow encryption, RBAC, and retention policies. For large files, store controlled storage references.

### 40.17. Using one executor and FIFO queue for every tenant and email type

Bulk campaigns can delay OTPs. Enforce lanes, fairness, quotas, and concurrency isolation based on SLAs.

### 40.18. Increasing maxPoolSize instead of rate limiting

Concurrency is not messages/second, recipients/day, or per-tenant budgets. Shared account quotas require shared rate admission matching the real scope.

### 40.19. Letting provider webhooks mutate domain state directly

Public callbacks require signature verification, idempotency, correlation, and authorization. Map technical delivery events to approved domain events if the business needs them.

### 40.20. Using Message-ID as an exactly-once key

`Message-ID` helps correlation, not guaranteed deduplication by SMTP servers, providers, or mail clients. Business idempotency and attempt state are still required.

### 40.21. Enabling both the old direct sender and the new outbox during migration

One business event triggers two sending paths and creates duplicates. Use owned routing/feature flags, non-sending shadow mode, and a cutover audit.

### 40.22. Putting a self-reported tenant ID into quota keys

Callers could spoof tenants or burn another tenant's budget. Resolve tenants from authenticated context and validate sender/account mappings.

### 40.23. Not defining ownership for incident handling and replay

When a service fails, nobody owns `UNKNOWN`, DLQs, outbox replays, or credential rotation. Establish runbooks and audited operational permissions.

### 40.24. Over-abstracting without justification

An app with two simple emails does not need 12 microservices, brokers, workflow engines, and complex provider routing. Start with **small, clear logical boundaries**; add infrastructure when real requirements justify it.

## 41. Runbook: provider outage impacting multiple domains

Suppose the primary SMTP provider goes down while Order, Identity, and Billing all have queued emails.

~~~text
Provider outage
      |
      v
Transport detects repeated connection/timeouts
      |
      v
Technical error classification
      |
      v
Circuit breaker / reduced rate
      |
      v
Durable outbox retains notification intents
      |
      v
Ops dashboard shows backlog age by lane
      |
      v
Recovery or approved provider failover
~~~

Steps:

1. Check network/DNS/TLS/auth to distinguish an outage from misconfiguration/expired credentials.
2. Inspect provider status and account quota/concurrency.
3. Verify the outbox continues accepting valid intents.
4. Pause the bulk lane if necessary to protect queues and send budgets.
5. Apply retry backoff/jitter; avoid hot SMTP retry loops.
6. Audit `UNKNOWN` outcomes before replaying or failing over.
7. If switching routes, verify sender verification and quotas on the target route.
8. Monitor backlog drain, expired messages, and accepted throughput.
9. Reconcile jobs affecting critical SLAs, especially expired OTPs.
10. Write a post-incident review: root cause, blast radius, lost/duplicate intents, and policy improvements.

**Domain requests must not fail en masse just because SMTP is down** when notifications are designed asynchronously and are not preconditions for completing business work. Where a flow genuinely requires proving channel reachability upfront, model that as an explicit business precondition rather than mixing `send()` inside the transaction.

### When the notification service itself is completely unavailable

In a modular monolith, business services can still write to the outbox in the shared DB. In microservices, producers need durable events/outboxes or queues with explicit guarantees. If the Notification API times out, callers cannot simply assume the request was lost; use idempotency keys, status queries, and consumer deduplication.

## 42. Runbook: user reports wrong email content

This incident belongs to the **content/notification boundary**, not necessarily SMTP:

1. Identify notificationId, template key/version, and business event reference.
2. Verify the recipient under business authorization.
3. Check whether snapshot-at-intent or render-on-send was used.
4. Determine whether the mismatch came from stale source data, a template bug, or incorrect locale/branding.
5. Never tweak raw SMTP provider settings to patch a template bug.
6. Decide whether to send a correction based on duplicate/PII risk policy.
7. Log an audit trail and add regression tests in the proper renderer/policy module.

For example, an invoice showing the wrong total due to a tax calculation bug must be fixed in the business/document domain, not by altering `MimeMessageHelper.setText(...)` to patch numbers inside the email alone.

### When the recipient is wrong

This may be a security/privacy incident, not just a notification defect:

- Pause the affected route/job if necessary.
- Audit recipient resolution and tenant authorization.
- Determine what data was sent and the affected scope.
- Preserve audit records and follow organizational incident-response procedures.
- Avoid logging raw recipients or bodies broadly while investigating.

Clean boundary design pinpoints the cause: wrong recipient from the domain, directory/profile policy, template variables, or transport envelope mapping.

## 43. Spring Mail boundary acceptance checklist

| Criterion | Evidence |
|---|---|
| Domain does not import Jakarta Mail/Spring Mail | Architecture dependency test |
| Business events and email commands are distinct | Contract docs and typed requests |
| Provider config lives only in required adapters/workloads | Secret/RBAC review |
| Templates/consent are absent from SMTP adapter | Module ownership/code structure |
| Critical email intents persist atomically with business commit | Transaction/outbox integration test |
| Workflow owns retries; adapter owns technical classification | Failure classification tests |
| UNKNOWN is never blindly re-sent | Crash-window tests |
| Multi-worker claiming prevents duplicate simple picks | DB concurrency/lease tests |
| Account/tenant quotas are enforced | Distributed admission/load tests |
| MIME/attachments are accurate | Offline MIME tests and SMTP sink |
| Delivery feedback is verified/deduplicated | Webhook integration tests |
| API never claims delivered upon queueing | Contract/response tests |
| All sender/profile changes are authorized | Security tests |
| Observability separates demand, attempts, and delivery | Dashboards and alert rehearsals |
| Credentials, raw MIME, and unnecessary PII are excluded from logs | Log policy review |
| Incident and replay ownership is assigned | Runbooks and role permissions |
| Migration never runs two sending paths simultaneously | Feature flag/cutover tests |
| Queues and timeouts are bounded | Load/failure tests |

### Walkthrough for tracing architecture on a real notification

Pick one mail type, such as payment confirmation:

~~~text
Payment committed
   |
   v
Find notification intent
   |
   v
Find policy/template decision
   |
   v
Find durable job + status
   |
   v
Find submission attempt
   |
   v
Find SMTP adapter/config
   |
   v
Find provider feedback (if any)
~~~

If any step lacks a source of truth, owner, or observability, a boundary may be missing. You do not need a separate microservice at every step.

## 44. Frequently asked questions

**Which layer should Spring Mail live in?** Typically inside the **infrastructure/transport adapter**. Business domains and applications should communicate through application-defined notification intents/ports rather than `JavaMailSender` or `MimeMessage` directly.

**Does every project need a separate Notification Service?** No. A modular monolith with clear boundaries, an outbox where needed, and a dedicated SMTP adapter usually suffices. Extract a service only when team ownership, scale, security, or SLAs outweigh operational overhead.

**Is an EmailService inside the service package a sufficient boundary?** Not necessarily. If it combines business rules, templates, SMTP, retries, and account policies, it merely bundles everything into a god object. Boundaries must separate responsibilities and dependency directions.

**Should `JavaMailSender` be constructor-injected into OrderService?** Avoid doing so when keeping the domain independent of transport. Inject `NotificationPort` or emit an intent through the application layer instead.

**Should the domain emit `OrderPaid` or `SendReceiptEmail`?** `OrderPaid` describes the business event and serves multiple consumers. `SendReceiptEmail` can be an internal command inside the notification workflow after policy decides to send; avoid putting SMTP commands into domain events unnecessarily.

**Should `MimeMessage` be published over Kafka/RabbitMQ?** Usually no. Use versioned event/notification request schemas with references; let workers build MIME at the transport boundary.

**Does a shared mail-common.jar replace a Notification Service?** No. A shared library reuses code, but does not centralize credentials, quotas, retry state, or operational ownership.

**Why maintain an outbox if `@Async` is already used?** `@Async` dispatches work to an in-process executor; it does not survive crashes. A durable outbox stores sending intent in a database/broker with recovery rules.

**Is `@TransactionalEventListener(AFTER_COMMIT)` enough?** It suffices for some best-effort flows, yet notifications can still be lost if the process crashes after DB commit before the listener persists the intent. Critical notifications require a durable mechanism.

**Should emails ever be sent synchronously in an API?** Possibly when the business truly needs immediate SMTP submission status, volume is low, and latency/failures are acceptable. Most notifications do not need HTTP requests to block on SMTP; durable enqueueing plus status queries is usually more resilient.

**Does HTTP 202 Accepted when sending mail mean the email reached the inbox?** No. It may only mean the request was accepted for processing. Contracts must distinguish QUEUED, SUBMITTED, DELIVERED, and UNKNOWN.

**When `JavaMailSender.send()` succeeds without exceptions, can status be set to DELIVERED?** No. You only know submission finished from the client/SMTP perspective. Delivery requires provider feedback or valid evidence.

**Does the adapter or workflow decide retries?** The adapter classifies technical/transport outcomes; the workflow decides retries using deadlines, attempt counts, notification type, tenant priority, and duplicate risk.

**Why is an UNKNOWN state necessary?** When the network drops after SMTP DATA, the provider may have accepted the message without the client seeing confirmation. Blind retries risk duplicate emails.

**Can SMTP Message-ID be used for deduplication?** The `Message-ID` header aids correlation, not guaranteed deduplication by receivers or providers. Business idempotency keys and attempt state are still needed.

**If a business transaction uses `@Transactional`, does an email sent inside it roll back?** No. SMTP does not participate in database ACID transactions. Save the intent via an outbox and send after commit.

**If the Notification Service is down, what should business services do?** Depends on the contract. With async durable integration, producers save events/outboxes and continue unless email is a synchronous precondition. With synchronous APIs, use timeouts, idempotency, and status queries to avoid duplicates.

**Who should choose templates?** Notification/content policy or the domain owning approved content, depending on business ownership. SMTP transport should only send pre-rendered/validated content.

**Who resolves recipients?** The domain identifies the authorized party; notification policy resolves deliverable addresses, preferences, and suppression; the adapter sends only to authorized addresses.

**Should rendered HTML be stored in the outbox?** Depends on the use case. Snapshots preserve exact content at intent time but store PII requiring encryption/retention; render-on-send requires rules around versions and changing data.

**Should PDF attachments be generated inside MailAdapter?** Usually not. A document/domain service generates the file and passes an approved payload reference; the adapter handles loading bytes into MIME attachments.

**Should tenants pick arbitrary SMTP From addresses?** No. Select from approved sender profiles, verified senders/domains, and proper quota scopes.

**Where do multi-tenant quotas live?** In the notification dispatcher/rate gate scoped by account and tenant, backed by shared state across replicas. Never let business services enforce independent local token buckets without coordinating account-wide quotas.

**Does separating two ThreadPoolTaskExecutors isolate mail completely?** It only isolates part of thread contention. Backpressure, bounded queues, provider rate/concurrency controls, and correctly scoped quota state are still necessary.

**Does inbound email belong in the same MailAdapter?** It can share a repository, but modules and privileges should be separated. Outbound SMTP submission differs from inbound IMAP/POP3 reading in protocols, checkpoints, retries, and trust boundaries.

**Can delivery webhooks write directly to the orders table?** Avoid doing so. Verify the callback, correlate/deduplicate, and let the business application decide how to act on verified events.

**With multiple providers, should one JavaMailSenderImpl mutate its host per job?** Avoid mutating a shared singleton configuration across threads. Use dedicated senders/adapters and a policy-driven route registry or qualifiers.

**When is a separate template microservice justified?** When content lifecycles, approvals, localization, or multiple product teams require independent releases. Otherwise, a notification/content module maintains clean boundaries.

**Should OTPs and newsletters share one queue?** Possibly at very low volume with strict fairness/SLA controls, though at scale dedicated lanes, reserved capacity, or fair scheduling are usually needed to avoid bulk interference.

**How do you prove boundaries are respected?** Via architecture dependency tests, SMTP-free business unit tests, contract tests, outbox recovery tests, MIME adapter tests, provider/feedback integration tests, and runbook ownership.

**Is event-driven architecture mandatory for every email?** Not necessarily. A strongly typed command call backed by an outbox may suffice. Event buses shine with multiple consumers, independent deployments, or heavy durable fan-out, while adding operational and consistency overhead.

**Can broker delayed messages replace a DB scheduler?** Yes if the broker provides needed semantics, though you must still manage job state, cancellations, retries, expiry, and idempotency. Delayed messages alone do not provide exactly-once SMTP.

**If SMTP is replaced with an HTTP email API, must business logic change?** With proper port–adapter boundaries, most domain/application contracts stay intact. Provider-specific capabilities may expand the capability model without exposing HTTP headers or API keys to the domain.

**If an email is a mandatory compliance requirement, should it be sent before completing the transaction?** Model an explicit business state (such as PENDING_NOTIFICATION/REQUIRES_ACK) and define clear contracts for submission/delivery proof. Never assume calling `mailSender.send()` inside a database transaction creates a legal guarantee.

**Should all notifications—both marketing and security—be centralized?** They can share infrastructure and state patterns, while keeping privacy, consent, sender reputation, rate quotas, and SLAs cleanly separated. Enforce explicit policies, lanes, and ownership; centralized does not mean one FIFO queue and one credential.

**How do you prevent dependency cycles?** Domains never call adapters; adapters implement application ports. Notification services accept events/commands from domains and query needed data via explicit read contracts rather than importing entities from every domain.

**If support needs to resend an email, who owns the action?** Notification operations/workflow, enforced by authorization, auditing, reason tracking, and duplicate checks. Never let a support UI invoke `JavaMailSender` directly bypassing policy.

**Should full raw SMTP transcripts be saved for audits?** Usually no. Raw transcripts can contain PII and secrets. Store attempt statuses, reason codes, provider references, timestamps, and minimal compliant metadata.

## 45. End-to-end architecture example: payment confirmation email

Suppose an e-commerce platform must send confirmation once payment is recorded.

### Step 1: domain commits payment state and intent

~~~text
OrderService.confirmPayment(ORDER-583)
  |
  +-- Mark order paid
  +-- Insert outbox event OrderPaid(ORDER-583, version=7)
  +-- Commit same database transaction
~~~

If the transaction rolls back, no email intent exists for that payment. If it commits, the outbox entry survives process restarts.

### Step 2: notification processor receives the event

~~~text
OrderPaid event
  |
  +-- Deduplicate by (eventType, aggregateId, version)
  +-- Validate customer/recipient relationship
  +-- Determine type=ORDER_RECEIPT
  +-- Choose locale=vi-VN
  +-- Resolve approved sender profile=BILLING
  +-- Render template version=2026-11
  +-- Store approved payload/reference
  +-- Create delivery job PENDING
~~~

If the consumer receives the event twice due to broker redelivery, the unique key prevents duplicate intents. If an older event version arrives after an invoice changed, policy decides whether to send or skip.

### Step 3: dispatcher sends email within capacity

~~~text
MailJob status=PENDING
  |
  +-- Check scheduledAt/expiry
  +-- Claim with lease
  +-- Revalidate recipient suppression if applicable
  +-- Resolve account and tenant quota
  +-- Acquire bounded concurrency slot
  +-- Record submission attempt
  +-- Call MailDeliveryPort.submit(...)
~~~

The dispatcher knows nothing about order payment logic beyond the approved fields supplied by the notification application.

### Step 4: Spring Mail adapter builds MIME

~~~java
MimeMessage mime = javaMailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        mime, true, "UTF-8");

helper.setFrom("billing@example.test");
helper.setTo("customer@example.test");
helper.setSubject("Payment successful");
helper.setText(
        "Your order has been paid.",
        "<p>Order <strong>ORDER-583</strong>"
                + " has been paid.</p>");

helper.addAttachment(
        "invoice-ORDER-583.pdf",
        new ByteArrayResource(invoicePdfBytes),
        "application/pdf");

javaMailSender.send(mime);
~~~

This snippet illustrates transport only, assuming recipient, sender, HTML, and bytes were validated by upstream layers. In production, adapters never hardcode business values like this. `ByteArrayResource` is used because the PDF fixture is modest; larger documents require suitable sources to avoid holding huge byte arrays in memory.

### Step 5: workflow persists submission outcome

~~~text
SMTP accepted:
  attempt.status=ACCEPTED
  job.status=SUBMITTED
  submitted_at=...

Temporary reject:
  attempt.status=REJECTED_TEMPORARY
  job.status=RETRY
  next_attempt_at=...

Ambiguous result:
  attempt.status=UNKNOWN
  job.status=UNKNOWN
  reconciliation required
~~~

No response automatically assigns `DELIVERED` simply because `send()` returned. State transitions must check the claim token and expected status during database writes so stale workers cannot overwrite newer states.

### Step 6: provider feedback is handled separately

~~~text
Verified provider webhook
  -> correlate provider message/attempt reference
  -> idempotently record delivered/bounced event
  -> update delivery projection
  -> notify business only if business rule requires
~~~

As a result, delivery issues never tangle committed `OrderPaid` logic. Special workflows like “must confirm the user actually received the document” require dedicated business/workflow confirmation rather than inferring from SMTP.

### Minimum test suite for this example

| Test | What must be verified |
|---|---|
| Order transaction rollback | No notification intent committed |
| Order commit followed by app crash | Outbox entry survives and resumes |
| Event redelivery | Only one intent created per event/version |
| Template missing | Job fails preparation without calling SMTP |
| Provider temporarily unavailable | Durable retry/deferral |
| Client timeout after DATA | Marked UNKNOWN; no blind resend |
| Duplicate provider callback | Single delivery state effect |
| Wrong tenant sender profile | `JavaMailSender` is never called |
| 10x bulk traffic load | Transactional lane stays within SLA |
| Swap SMTP → HTTP adapter | Domain application unit tests remain unchanged |

## 46. Summary

**Defining Spring Mail boundaries in a large system** means deciding **who owns intent, policy, state, transport, and feedback**, rather than merely moving a `mailSender.send()` call into another class.

A well-bounded architecture typically looks like this:

~~~text
Business/domain services
  (events and authorized business intents)
                  |
                  v
Notification application
  (recipient, consent, template, locale, priority)
                  |
                  v
Durable outbox / notification workflow
  (scheduled state, idempotency, claim, retry, audit)
                  |
                  v
Rate, tenant and sender policy
                  |
                  v
MailDeliveryPort
                  |
                  v
Spring Mail infrastructure adapter
  (JavaMailSender, MimeMessageHelper, SMTP, TLS/auth)
                  |
                  v
Email provider
                  |
                  v
Verified provider feedback (if available)
  (delivery events, bounce, correlation, projection)
~~~

Core principles:

1. **Spring Mail is a transport capability**, not a domain model or notification workflow.
2. **Use typed intents/ports instead of exposing `MimeMessage`** in domains or cross-service contracts.
3. **Content, recipients, and consent belong to policy/business boundaries**; the SMTP adapter only delivers approved content.
4. **Persist intents durably alongside business commits when loss is unacceptable**, rather than expecting `@Async` or `AFTER_COMMIT` to provide durability on their own.
5. **Distinguish QUEUED, SUBMITTED, and DELIVERED**, with an UNKNOWN state for uncertain SMTP outcomes.
6. **Retries belong to orchestration policy**, while classification belongs to the technical adapter; never let domains invoke SMTP retries directly on errors.
7. **Isolate SMTP credentials, quotas, and failure blast radius**, especially across multiple tenants, providers, and traffic lanes.
8. **Separate logical boundaries before splitting deployments**; a modular monolith is often a great choice until operational drivers justify microservices.
9. **Define ownership, metrics, runbooks, and contract tests**, because boundaries live beyond package directories.
10. **Preserve an evolutionary path**: start with an in-app adapter, add an outbox/worker, and extract a Notification Service only when scale and ownership truly demand it.

A successful architecture lets Order, Billing, Identity, and other domains focus on their business rules; keeps notification workflows in charge of eligibility and state; and lets Spring Mail evolve how MIME is built, swap SMTP providers, or tune timeouts **without forcing the rest of the system to understand email delivery mechanics**.
