# Varying Email Content Based on Business State

## 1. Why should email content depend on business state?

In an application, email is often how you notify users that an event occurred or that they need to take the next step. The same business object can pass through many states in its lifecycle. For example, an order may move through **Pending payment**, **Confirmed**, **Shipping**, **Delivered**, **Cancelled**, or **Refunded**.

Each state carries a different meaning, so the outgoing email must also change:

- When the order is created, the buyer needs the order code and payment instructions.
- When payment is confirmed, the buyer needs to know the order was accepted.
- When the order is handed to the carrier, the buyer needs the tracking number.
- When delivery completes, the buyer may need to confirm receipt or see support instructions.
- When the order is cancelled, the buyer needs to know the reason and refund status if applicable.

If every send uses a generic subject and body like "Your order has been updated", recipients will not understand what just changed or what to do next. Conversely, if content is generated from business state, the email can accurately communicate **the event, relevant details, the next action, and the right recipient**.

In **Spring Framework Mail**, **JavaMailSender** and **MimeMessageHelper** are responsible for creating and sending messages. Deciding **which email to send, when to send it, to whom, and which content corresponds to which state** belongs to application logic.

An overview flow:

~~~text
User / external system
              |
              v
       Business command
              |
              v
      Validate transition
              |
              v
        Update status
              |
              v
    Create notification event
              |
              v
     Select email content
              |
       +------+------+
       |             |
       v             v
   Plain text       HTML
       |             |
       +------+------+
              |
              v
       MimeMessageHelper
              |
              v
        JavaMailSender
              |
              v
             SMTP
~~~

Key point: **business state is an input for choosing content**, while sending email is a notification task with its own lifecycle and failures.

## 2. Business state vs. state transition events

State describes the current condition of an object. A state transition event describes the object moving from an old state to a new state due to an action or processing outcome.

Example order lifecycle:

~~~text
                 +-------------------+
                 |      CREATED      |
                 +---------+---------+
                           |
                           v
                 +-------------------+
                 | PENDING_PAYMENT   |
                 +---------+---------+
                           |
                    Payment succeeded
                           |
                           v
                 +-------------------+
                 |       PAID        |
                 +---------+---------+
                           |
                    Packing complete
                           |
                           v
                 +-------------------+
                 |      SHIPPED      |
                 +---------+---------+
                           |
                   Delivery succeeded
                           |
                           v
                 +-------------------+
                 |     DELIVERED     |
                 +-------------------+

Other branches:
PENDING_PAYMENT -> CANCELLED
PAID -> CANCELLED (if policy permits)
PAID -> REFUND_PENDING -> REFUNDED
~~~

This diagram is only an example. A real application must define valid transitions according to its own business rules.

### State is not the same as an event

Suppose an order is in the **SHIPPED** state. A user opening the details page, an internal note update, or a data sync might save the record again while the status remains SHIPPED. Not every save means "the order was just shipped".

Distinguish clearly:

| Concept | Question | Example |
|---|---|---|
| **Current state** | What condition is the object in right now? | order.status = SHIPPED |
| **Transition** | What did it just move from and to? | PAID -> SHIPPED |
| **Business event** | What just happened? | OrderShipped |
| **Notification** | Does someone need to be notified? | Send email with tracking code |

If you merely read the current state and send an email every time the entity is saved, the application can send duplicate notifications. A better approach is creating notifications from **confirmed transitions or business events**.

## 3. Mapping content per state

Before writing code, build a mapping table between states, events, recipients, and required information.

Example for an order lifecycle:

| State / event | Typical recipient | Illustrative subject | Core content |
|---|---|---|---|
| PENDING_PAYMENT | Buyer | Order confirmation and payment instructions | Order code, amount, payment deadline, payment link |
| PAID | Buyer | Payment received for your order | Order code, amount paid, next steps |
| PROCESSING | Buyer | Your order is being prepared | Processing status and estimated timeline if available |
| SHIPPED | Buyer | Your order has been shipped | Carrier, tracking code, tracking link |
| DELIVERED | Buyer | Your order has been delivered | Delivery time, support or review instructions |
| CANCELLED | Buyer; sometimes operations | Your order has been cancelled | Reason, amount, and refund status |
| REFUND_PENDING | Buyer | Refund request is being processed | Amount, estimated timeline, refund channel |
| REFUNDED | Buyer | Refund completed | Amount, reference code, refund timestamp |

Not every state needs an email. For instance, a technical state such as **RETRYING_PAYMENT_PROVIDER** may only need internal logs or metrics. Reserve emails for changes that are meaningful to recipients.

### One state can produce multiple notification types

For example, when an order transitions to SHIPPED:

- The buyer receives an email with the tracking number.
- Support staff may receive an internal alert if the order requires special monitoring.
- Operational systems may record events or metrics without sending any email.

Therefore, do not hardcode "one status equals one single email". Determine **event + audience + notification purpose**.

## 4. Designing transition rules before sending email

The application must define valid state transitions. If a user or an integration sends an out-of-order request, do not emit an email as if the action succeeded.

Example:

| Current state | Requested state | Can it be valid? | Reason |
|---|---|---|---|
| PENDING_PAYMENT | PAID | Yes | Payment gateway confirmed success |
| PENDING_PAYMENT | CANCELLED | Yes | Buyer or system cancelled per policy |
| PAID | SHIPPED | Yes | Order was handed over to carrier |
| SHIPPED | DELIVERED | Yes | Delivery confirmation received |
| DELIVERED | PENDING_PAYMENT | No | Not a valid transition in this lifecycle |
| CANCELLED | SHIPPED | Usually no | A cancelled order should not continue shipping without an explicit reinstatement flow |

Do not update status via an arbitrary assignment from a request:

~~~java
// Do not let requests directly dictate every status.
order.setStatus(request.status());
orderRepository.save(order);
~~~

Instead, route state changes through business methods:

~~~java
public void markShipped(String orderId, String trackingNumber) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

    order.markShipped(trackingNumber);
    orderRepository.save(order);
}
~~~

**Order.markShipped(...)** must validate the current state, payment preconditions, shipping details, and transition rules. Only after a valid transition should the application emit a notification event.

## 5. Modeling states with enums

For a lifecycle with a finite set of states, Java enums avoid arbitrary strings:

~~~java
public enum OrderStatus {
    PENDING_PAYMENT,
    PAID,
    PROCESSING,
    SHIPPED,
    DELIVERED,
    CANCELLED,
    REFUND_PENDING,
    REFUNDED
}
~~~

Never store display labels like "Delivered" directly as internal state values. Use stable codes like DELIVERED, then map them to display text per language and context.

A transition can be represented as:

~~~java
public record OrderStatusChanged(
        String orderId,
        OrderStatus previousStatus,
        OrderStatus currentStatus,
        Instant occurredAt
) {
}
~~~

The event captures the previous state, new state, and transition timestamp. For notifications needing a data snapshot, add required fields such as order code, recipient, tracking number, or validated business URLs.

## 6. Using switch to select content by state

For a small set of states and simple logic, a Java switch expression is easy to read:

~~~java
public EmailContent contentFor(OrderStatus status) {
    return switch (status) {
        case PENDING_PAYMENT -> new EmailContent(
                "Order confirmation",
                "Your order is awaiting payment."
        );
        case PAID -> new EmailContent(
                "Payment received",
                "We have received payment for your order."
        );
        case PROCESSING -> new EmailContent(
                "Order is being prepared",
                "Your order is currently being processed."
        );
        case SHIPPED -> new EmailContent(
                "Order has been shipped",
                "Your order has been handed over to the carrier."
        );
        case DELIVERED -> new EmailContent(
                "Order has been delivered",
                "Your order has been delivered to the destination address."
        );
        case CANCELLED -> new EmailContent(
                "Order has been cancelled",
                "Your order was cancelled per request or policy."
        );
        case REFUND_PENDING -> new EmailContent(
                "Refund request in progress",
                "We are processing your refund request."
        );
        case REFUNDED -> new EmailContent(
                "Refund completed",
                "The funds have been refunded via your payment method."
        );
    };
}
~~~

EmailContent can be a record:

~~~java
public record EmailContent(String subject, String body) {
}
~~~

An advantage of switching over an enum without a `default` branch is that the compiler catches unhandled cases when a new enum value is added. However, once an application supports multiple languages, multiple recipient types, multiple templates, or multiple channels, one large switch becomes hard to maintain. At that point, extract mapping into dedicated components.

## 7. Separating email content from transition logic

Do not put all subjects, HTML, and SMTP details directly inside business entities. Entities protect state rules; notification services handle content generation and sending.

One way to divide responsibilities:

| Component | Responsibility |
|---|---|
| Order | Valid states and transitions |
| OrderApplicationService | Orchestrates business actions |
| OrderStatusChanged | Captures the transition event |
| EmailContentResolver | Selects content by event and audience |
| EmailTemplateRenderer | Renders plain text and HTML |
| MailNotificationService | Creates MimeMessage and calls JavaMailSender |
| NotificationRepository / outbox | Stores send intent, processing status, and attempts |

Flow:

~~~text
OrderApplicationService
        |
        v
Order.markShipped(...)
        |
        v
OrderStatusChanged
        |
        v
EmailContentResolver
        |
        v
TemplateRenderer
        |
        v
MailNotificationService
        |
        v
JavaMailSender
~~~

This separation lets you change wording or templates without touching transition rules, and test email content without an SMTP connection.

## 8. Building notification data from a business snapshot

Emails often need data as of the moment the event occurred. If a worker only receives `orderId` and queries the current state at send time, the content may no longer match the original event.

For example:

1. The order transitions from PAID to SHIPPED.
2. The system creates a "Order shipped" notification.
3. The email enters the queue.
4. Before the worker runs, the order transitions to DELIVERED.
5. The worker reads the current state and renders a "Delivered" email.

The recipient may receive the delivery email before the shipped email or miss expected tracking details.

### Snapshot event

An event can carry the data needed at transition time:

~~~java
public record OrderShippedEvent(
        String orderId,
        String orderCode,
        String recipientEmail,
        String customerName,
        String trackingNumber,
        String trackingUrl,
        Instant shippedAt
) {
}
~~~

The worker uses this snapshot to build notification content for the OrderShipped event. If any data must be re-verified or adjusted for permissions at send time, the worker can query additionally while keeping the original event and snapshot rules explicit.

Do not dump an entire entity into the event. Keep only fields needed for the notification, or keep the ID plus a version/snapshot that can be retrieved consistently. Be mindful of personal data in events and outboxes because they may live longer than the initial request.

## 9. Example: selecting content for each order state

You can define a model for email data:

~~~java
public record OrderEmailData(
        String customerName,
        String orderCode,
        OrderStatus status,
        BigDecimal totalAmount,
        String currency,
        String trackingNumber,
        String trackingUrl,
        String nextActionUrl
) {
}
~~~

A resolver returns text/HTML content based on the event:

~~~java
public record RenderedEmail(
        String subject,
        String plainText,
        String htmlText
) {
}

public interface OrderEmailContentResolver {
    RenderedEmail resolve(OrderEmailData data);
}
~~~

Simple implementation:

~~~java
public class DefaultOrderEmailContentResolver
        implements OrderEmailContentResolver {

    @Override
    public RenderedEmail resolve(OrderEmailData data) {
        return switch (data.status()) {
            case PENDING_PAYMENT -> pendingPayment(data);
            case PAID -> paid(data);
            case PROCESSING -> processing(data);
            case SHIPPED -> shipped(data);
            case DELIVERED -> delivered(data);
            case CANCELLED -> cancelled(data);
            case REFUND_PENDING -> refundPending(data);
            case REFUNDED -> refunded(data);
        };
    }

    private RenderedEmail shipped(OrderEmailData data) {
        String subject = "Order " + data.orderCode() + " has been shipped";
        String plain = """
                Hello %s,

                Order %s has been handed over to the carrier.
                Tracking code: %s
                Track here: %s
                """.formatted(
                data.customerName(),
                data.orderCode(),
                data.trackingNumber(),
                data.trackingUrl()
        );

        String html = """
                <html lang="vi">
                  <body>
                    <h1>Order has been shipped</h1>
                    <p>Hello!</p>
                    <p>Order code: <strong>%s</strong></p>
                    <p>Tracking code: <strong>%s</strong></p>
                    <p><a href="%s">Track order</a></p>
                  </body>
                </html>
                """.formatted(
                escapeHtml(data.orderCode()),
                escapeHtml(data.trackingNumber()),
                escapeHtmlAttribute(data.trackingUrl())
        );

        return new RenderedEmail(subject, plain, html);
    }

    // pendingPayment, paid, processing, delivered,
    // cancelled, refundPending, and refunded are implemented similarly.
}
~~~

This is a structural example. `escapeHtml` and `escapeHtmlAttribute` represent context-aware escaping via an appropriate library or template engine; they are not built-in Spring Mail APIs. `trackingUrl` must be constructed from an allowed domain and verified before rendering.

If the resolver handles every state, implement all branches. You can split into separate renderers to avoid one overly large class.

## 10. Sending email with JavaMailSender and MimeMessageHelper

Once content is selected and rendered, the mail-sending service does not need to know transition rules. It only accepts the recipient, subject, plain text, and HTML.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class MailNotificationService {

    private final JavaMailSender mailSender;

    public MailNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(
            String recipient,
            RenderedEmail content
    ) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("notifications@example.com");
        helper.setTo(recipient);
        helper.setSubject(content.subject());
        helper.setText(content.plainText(), content.htmlText());

        mailSender.send(message);
    }
}
~~~

The example assumes the application has configured JavaMailSender and the `From` address is permitted by the SMTP provider. **setText(plainText, htmlText)** supplies two alternative representations; it does not generate state-dependent content itself. The resolver already decided the content before calling the sending service.

### Illustrative Spring Boot configuration

Dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

SMTP submission over STARTTLS:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
~~~

Host and credentials are illustrative values. In production, load secrets from environment variables or a secret manager; never commit real passwords. Port and TLS must match your SMTP provider.

## 11. Do not send email just because an entity is saved

An anti-pattern is sending email directly inside a setter or callback whenever status changes:

~~~java
public void setStatus(OrderStatus status) {
    this.status = status;
    mailSender.send(...); // Do not place side effects inside entities.
}
~~~

This causes several issues:

- The entity becomes coupled to mail infrastructure.
- Emails may be sent before the database transaction commits.
- An ORM may call setters while hydrating entities or updating records.
- Business logic tests must mock SMTP.
- Retries, duplicates, and delivery state cannot be controlled.
- A save does not necessarily correspond to a user-meaningful transition.

Emit an event or create an outbox record from the application service after confirming a valid transition.

## 12. Transactions and email-sending timing

Suppose a service both updates the order and sends an email:

~~~java
@Transactional
public void markShipped(String orderId) {
    Order order = orderRepository.findById(orderId).orElseThrow();
    order.markShipped();
    orderRepository.save(order);

    mailSender.send(...);
}
~~~

This carries risks: SMTP might accept the email, and then the database transaction rolls back. The user receives a "shipped" email while the database still holds the old status. Conversely, if the database commits and SMTP fails, the status changed without sending the email.

### Simple option: send after transaction commit

Spring supports **@TransactionalEventListener** to handle application events according to transaction phase:

~~~java
public record OrderShippedEvent(
        String orderId,
        String recipientEmail,
        String orderCode,
        String trackingNumber,
        String trackingUrl
) {
}
~~~

Publish the event in the business service:

~~~java
@Transactional
public void markShipped(String orderId, ShipmentInfo shipment) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

    order.markShipped(shipment);
    orderRepository.save(order);

    eventPublisher.publishEvent(new OrderShippedEvent(
            order.getId(),
            order.getCustomerEmail(),
            order.getCode(),
            shipment.trackingNumber(),
            shipment.trackingUrl()
    ));
}
~~~

Listener:

~~~java
@Component
public class OrderMailListener {

    private final OrderEmailFacade emailFacade;

    public OrderMailListener(OrderEmailFacade emailFacade) {
        this.emailFacade = emailFacade;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderShipped(OrderShippedEvent event) {
        emailFacade.sendShipped(event);
    }
}
~~~

AFTER_COMMIT ensures the listener runs only after the transaction has committed. However, an in-memory listener **is not a durable queue**. If the process stops after commit but before the listener sends, the event can be lost. If mail sending fails, the application also needs a separate recording and retry mechanism.

### More reliable option: transactional outbox

For critical notifications, store a notification/outbox record in the same database transaction as the status change:

~~~text
Database transaction
    |
    +--> UPDATE order status = SHIPPED
    |
    +--> INSERT notification_outbox
              event_type = ORDER_SHIPPED
              aggregate_id = orderId
              payload = snapshot to send
              status = PENDING
    |
    +--> COMMIT
             |
             v
      Background worker reads outbox
             |
             v
      Render content per event
             |
             v
      JavaMailSender.send(...)
             |
             v
      Record SENT / RETRY / FAILED status
~~~

This commits the state change and notification intent together. Workers can resume pending records after application restarts.

An outbox does not by itself guarantee exactly-once delivery. A worker may send successfully and crash before updating SENT; next time it may send again. Idempotency, attempt tracking, and appropriate reconciliation are needed.

## 13. Preventing duplicate sends with event identity and idempotency

A state may be updated repeatedly by webhooks, job retries, or retried requests. If every execution emits a notification, recipients may receive multiple identical emails.

Each event should have a stable identifier:

~~~java
public record NotificationEvent(
        UUID eventId,
        String aggregateId,
        String eventType,
        Instant occurredAt
) {
}
~~~

Before creating or sending an email, the system can ensure a notification key is processed only once at the business level:

~~~text
notification key:
  orderId + eventType + transitionVersion

Example:
  ORD-123 + ORDER_SHIPPED + version 7
~~~

Do not use only `orderId + status` if an object can legitimately revisit the same state in different cycles. A version or event ID distinguishes transitions.

An outbox/notification table can place a unique constraint on the business key. This prevents two concurrent requests from creating two identical notifications when processing the same transition.

**Database idempotency does not mean exactly-once delivery over SMTP.** SMTP does not participate in a distributed transaction with the database to guarantee atomic commits across both systems. Accept and manage duplicate risk in ambiguous-outcome scenarios.

## 14. Handling retries and delivery states

Not every mail-sending failure should be retried the same way:

| Outcome | Handling approach |
|---|---|
| SMTP temporarily rejects or times out before data submission | Can retry with backoff and attempt cap |
| Wrong credentials or missing send permissions | Fix config/permissions; continuous retries will not help |
| Invalid recipient address | Fix data or mark business error |
| Content/template error | Fix renderer/template before retrying |
| Timeout after server may have received DATA | Status unknown; reconcile before resending |
| SMTP accepts but bounces later | Process delivery/bounce events per provider |

You can persist notification states:

~~~java
public enum NotificationStatus {
    PENDING,
    PROCESSING,
    SENT_TO_PROVIDER,
    RETRY,
    FAILED,
    UNKNOWN
}
~~~

SENT_TO_PROVIDER describes reality more accurately than DELIVERED: a successful send call usually indicates only that SMTP/the provider accepted the submission, not that the message landed in the Inbox.

A notification record can store:

- Event ID and idempotency key.
- Verified recipient.
- Template key and locale.
- Payload/snapshot to render.
- Attempt count and last attempt timestamp.
- Provider response or message ID if available.
- Sanitized error for logging.

Do not retain tokens or sensitive bodies longer than necessary. Apply retention policies and access controls to the outbox table.

## 15. Different content by recipient and role

Status alone does not determine the email. The same event may require different content for different audiences:

| Event | Buyer | Operations staff |
|---|---|---|
| ORDER_PAID | Payment received, next steps | Payment succeeded, process order |
| ORDER_SHIPPED | Tracking code and tracking link | Order handed off, carrier details |
| ORDER_CANCELLED | Cancellation reason and refund | Actor, cause, audit data |

Thus, the template lookup key can include:

~~~text
eventType + audience + locale + channel
~~~

Example:

~~~text
ORDER_SHIPPED + CUSTOMER + vi-VN + EMAIL
ORDER_SHIPPED + OPERATIONS + en-US + EMAIL
~~~

Never send the same internal body to customers if it contains operational notes, risk data, or non-public details.

### Resolving recipients from business data

Recipient addresses must come from an authenticated source authorized to receive the notification. Never trust arbitrary emails passed in unverified webhook payloads. For customer notifications, resolve the active email address and consent status for that mail category.

## 16. Subject, content, and actions should match state

An email should make clear:

1. **What happened?**
2. **Which entity/object is affected?**
3. **What details does the recipient need to know?**
4. **What is the next step, if any?**
5. **Which link opens the right action?**

Example:

| State | Clear subject | Appropriate CTA |
|---|---|---|
| PENDING_PAYMENT | Order awaiting payment | Pay for order |
| PAID | Payment received for order | View order |
| SHIPPED | Order has been shipped | Track shipment |
| DELIVERED | Order has been delivered | View details / Get support |
| CANCELLED | Order has been cancelled | View refund details |
| REFUNDED | Refund issued for order | View transaction details |

Do not show CTAs that are no longer valid. For example, a cancelled order must not still display a "Pay now" button. If the state changes before the user opens the email, the landing page must read the current state and explain the situation rather than blindly executing an action.

## 17. Plain text and HTML must reflect the same state

For multi-format emails, both versions must be generated from the same data and same notification type:

~~~java
helper.setText(plainText, htmlText);
~~~

Example ORDER_SHIPPED:

Plain text:

~~~text
Order ORD-2026-015 has been shipped.
Tracking code: VN123456
Track order: https://example.com/tracking/VN123456
~~~

HTML:

~~~html
<h1>Order has been shipped</h1>
<p>Order code: <strong>ORD-2026-015</strong></p>
<p>Tracking code: <strong>VN123456</strong></p>
<a href="https://example.com/tracking/VN123456">Track order</a>
~~~

Never let HTML state SHIPPED while plain text still states PROCESSING. Nor should the tracking URL in HTML point to a different order than the URL in plain text.

A renderer taking **one notification model** and generating both strings helps preserve consistency. When using a template engine, render plain text and HTML from the same immutable model.

## 18. Multilingual content by locale

Recipients may use different languages. Instead of concatenating strings inside a switch, select templates by **locale**:

~~~text
ORDER_SHIPPED
  ├── vi-VN
  │    ├── subject
  │    ├── plain text
  │    └── HTML
  └── en-US
       ├── subject
       ├── plain text
       └── HTML
~~~

Java example:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");

String subject = messageSource.getMessage(
        "mail.order.shipped.subject",
        new Object[] { orderCode },
        locale
);
~~~

MessageSource can manage strings such as subjects and shared labels. For longer bodies, separate per-locale templates are usually easier to maintain than a properties file containing full HTML.

### Locale notes

- Read locale from the user profile or verified preference.
- Provide a default locale when the user has not chosen one.
- Format dates, times, and currencies per locale while keeping the right business time zone.
- Do not translate internal state codes; translate only display content.
- Ensure plain text and HTML use the same locale.
- Define an explicit fallback if a template is missing for a locale.

Never infer language solely from an email address or domain country code.

## 19. Templates per state and maintainability

As the number of states and email types grows, split templates by event rather than keeping one giant file with many conditional branches.

Example structure:

~~~text
src/main/resources/mail/
  order/
    pending-payment.html
    pending-payment.txt
    paid.html
    paid.txt
    shipped.html
    shipped.txt
    delivered.html
    delivered.txt
    cancelled.html
    cancelled.txt
~~~

A registry can map events to templates:

~~~java
public record TemplatePair(
        String plainTextTemplate,
        String htmlTemplate
) {
}

public class OrderTemplateRegistry {

    public TemplatePair forEvent(OrderEventType eventType) {
        return switch (eventType) {
            case PAYMENT_REQUIRED -> new TemplatePair(
                    "mail/order/pending-payment.txt",
                    "mail/order/pending-payment.html"
            );
            case PAID -> new TemplatePair(
                    "mail/order/paid.txt",
                    "mail/order/paid.html"
            );
            case SHIPPED -> new TemplatePair(
                    "mail/order/shipped.txt",
                    "mail/order/shipped.html"
            );
            case DELIVERED -> new TemplatePair(
                    "mail/order/delivered.txt",
                    "mail/order/delivered.html"
            );
            case CANCELLED -> new TemplatePair(
                    "mail/order/cancelled.txt",
                    "mail/order/cancelled.html"
            );
        };
    }
}
~~~

OrderEventType is an application-defined enum. The example lists only a subset of events; add the remaining types if the system supports them. The template registry selects files, while the template renderer loads and renders data.

### Do not let templates decide transitions

A template can choose how to present the ORDER_SHIPPED event, but it must not decide that an order is allowed to transition from CANCELLED to SHIPPED. Transition rules live in the domain/application service. Templates only present an already-validated event.

## 20. Avoiding emails for changes that do not require notification

An object can undergo many internal changes:

- Editing staff notes.
- Updating sync timestamps.
- Reassigning a support agent.
- Updating technical gateway metadata.
- Fixing an address typo without changing status.

Not every change warrants emailing the customer. Define an explicit **notification policy**:

| Change type | Email customer? | Reason |
|---|---|---|
| Payment succeeded | Usually yes | Important event |
| Order moved to shipping | Usually yes | Recipient needs tracking |
| Internal note updated | No | Not customer-facing information |
| Technical metadata updated | No | Adds no value for the recipient |
| Estimated delivery date changed | Depends on policy | May affect buyer's plans |
| Order cancelled | Usually yes | Needs explanation of outcome and next steps |

A notification policy prevents spam and keeps emails meaningful. Small changes can be batched into a summary if business rules permit.

## 21. Handling out-of-order states or duplicate webhooks

External systems can send webhooks multiple times or out of chronological order. For example:

1. A `payment.succeeded` webhook arrives twice.
2. A `shipment.delivered` webhook arrives before a delayed `shipment.in_transit` webhook.
3. A worker retries an old event after the state has already changed.

If the application simply reads the payload and sends an email immediately, it may send wrong content or duplicate notifications.

### Validate events before emitting notifications

- Verify webhook signatures or the provider's authentication mechanism.
- Use event IDs to prevent duplicate processing.
- Check version/timestamp and current state against business rules.
- Apply valid transitions.
- Create notifications only when the event is accepted.
- Persist the raw event and processing result for investigation.

Do not rely on a standalone timestamp as absolute proof of ordering if the provider has its own version/sequence rules. Follow the event source's contract.

### Conceptual idempotent handling example

~~~java
@Transactional
public void handle(PaymentSucceededWebhook webhook) {
    if (processedEventRepository.existsByExternalId(webhook.eventId())) {
        return;
    }

    Order order = orderRepository.findById(webhook.orderId())
            .orElseThrow();

    order.markPaid(webhook.paymentReference());
    orderRepository.save(order);

    outboxRepository.save(
            NotificationOutbox.orderPaid(order, webhook.eventId())
    );

    processedEventRepository.save(
            ProcessedEvent.from(webhook.eventId())
    );
}
~~~

This is illustrative code; a unique constraint on external event ID and database race-condition handling are required. Checking `existsBy...` and then inserting without a unique constraint can still allow two concurrent requests to process the same event.

## 22. Securing state-dependent data inside emails

Emails leave the system and can be forwarded or stored in many mailboxes. Include only the information the recipient needs.

For example:

- PENDING_PAYMENT emails can include the order code and payment link, without card details.
- SHIPPED emails can include the tracking number and tracking link, without exposing internal notes.
- CANCELLED emails can explain an appropriate reason, without sending staff details or internal investigation notes.
- REFUNDED emails can mention the amount and an appropriate reference code, without displaying full account numbers.

### URLs and tokens

If links require tokens:

- Use HTTPS.
- Tokens must have sufficient randomness, clear expiration, and narrow scope.
- Never log tokens.
- Never send tokens to multiple recipients.
- The landing page must verify permissions and current state.
- Avoid completing sensitive actions on GET alone because email scanners may prefetch links.

### Escaping HTML content

Customer names, cancellation reasons, or descriptions may contain special characters. Escape according to HTML text/attribute context. Never concatenate user input directly into markup or `href`.

For content that may contain markup, define an explicit sanitization policy or allow only restricted formatting. Default escaping in template engines helps, but ensure raw HTML insertion mode is not turned on accidentally.

## 23. Controlling recipients and consent

Business state determines **the notification type**, while recipients must be resolved according to authorization and sending purpose:

- Transactional emails can be sent to the address bound to the account or order, per applicable rules and consent.
- Internal emails go only to authorized groups/addresses.
- Never take arbitrary recipients from unverified webhooks.
- Never put multiple unrelated customers in To/Cc if they must not see one another's addresses.
- For marketing notifications, respect consent, unsubscribes, and applicable legal policies.

If a transactional email has a different buyer and recipient, clarify who receives which information. For example, the parcel recipient may need the delivery schedule, but should not necessarily receive the invoice or payment details.

## 24. Observing and tracing notifications

When emails depend on state, you must be able to trace why an email was generated:

| Field | Purpose |
|---|---|
| eventId | Source event identifier |
| aggregateId | Related order/account/entity |
| previousStatus | State before transition |
| currentStatus | New state |
| notificationType | Email type to send |
| recipientRef | Recipient reference; avoid storing raw emails unnecessarily |
| templateKey | Selected template |
| locale | Rendering language |
| attempt | Send attempt count |
| providerMessageId | SMTP/ESP identifier if available |
| status | PENDING, SENT_TO_PROVIDER, RETRY, FAILED, or UNKNOWN |

Logs should record event ID, notification ID, template key, and sanitized error type. Never log full bodies, SMTP passwords, tokens, or sensitive attachments.

### Distinguishing success milestones

~~~text
Business transition committed
            |
            v
Notification created
            |
            v
Mail provider accepted
            |
            v
Provider / receiving server processing
            |
            v
Delivered / bounced / deferred (if events exist)
            |
            v
Recipient opens or reads (not always observable)
~~~

Do not set status to DELIVERED right when `JavaMailSender.send(...)` returns normally. Use SENT_TO_PROVIDER or SUBMITTED to accurately reflect what the application actually knows.

## 25. Testing state mapping and content

You do not need a live SMTP connection to test content selection. You can unit-test the resolver:

~~~java
@Test
void shippedOrderUsesTrackingMessage() {
    OrderEmailData data = new OrderEmailData(
            "An",
            "ORD-2026-015",
            OrderStatus.SHIPPED,
            new BigDecimal("250000"),
            "VND",
            "VN123456",
            "https://example.com/tracking/VN123456",
            "https://example.com/orders/ORD-2026-015"
    );

    RenderedEmail email = resolver.resolve(data);

    assertTrue(email.subject().contains("has been shipped"));
    assertTrue(email.plainText().contains("VN123456"));
    assertTrue(email.htmlText().contains("VN123456"));
}
~~~

This example uses JUnit 5; the resolver is injected or instantiated in the test. Test other states, locales, URLs, and boundary values as well.

### Testing the mail-sending service with mocks

You can mock JavaMailSender to verify the service creates a MimeMessage and sends it:

~~~java
JavaMailSender sender = mock(JavaMailSender.class);
MimeMessage message = new MimeMessage(Session.getInstance(new Properties()));
when(sender.createMimeMessage()).thenReturn(message);

MailNotificationService service = new MailNotificationService(sender);
service.send("customer@example.net", renderedEmail);

verify(sender).send(message);
~~~

This is a conceptual example; tests must import Jakarta Mail Session, Properties, Mockito, and may need adjustments to compare message objects depending on setup. Mocks verify calls at the application layer; **they do not prove SMTP delivered the message or that email clients render it properly**.

### Testing transitions and notifications separately

Include these test layers:

1. **Domain tests:** valid and invalid transitions.
2. **Application tests:** transitions create the right event/outbox record.
3. **Resolver tests:** events/statuses pick the right subject and template.
4. **Renderer tests:** plain text and HTML contain the same critical data.
5. **Mail service tests:** MIME construction and JavaMailSender invocation.
6. **Integration tests:** use an SMTP test server to inspect MIME/transport.

Separating test layers pinpoints whether a bug lies in business rules, content, or delivery infrastructure.

## 26. End-to-end example: handling an order-shipped event

A clean flow can be split into steps:

**Step 1 — Application service confirms transition**

~~~java
@Transactional
public void shipOrder(String orderId, ShipmentInfo shipment) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

    OrderStatus previous = order.getStatus();
    order.markShipped(shipment);
    orderRepository.save(order);

    outboxRepository.save(
            OrderNotificationOutbox.shipped(
                    order,
                    previous,
                    shipment
            )
    );
}
~~~

`Order.markShipped(...)` checks valid transitions. `OrderNotificationOutbox.shipped(...)` builds the required payload in the same transaction. This is an illustrative structure; entity and repository types are defined by the application.

**Step 2 — Worker reads the outbox**

~~~java
public void process(OrderNotificationOutbox record) {
    if (record.isAlreadyProcessed()) {
        return;
    }

    OrderShippedEvent event = record.toEvent();
    RenderedEmail content = renderer.render(event);
    mailNotificationService.send(event.recipientEmail(), content);

    outboxRepository.markSubmitted(record.id());
}
~~~

Real workers must lock/claim records to prevent two workers from sending simultaneously, persist attempts, and handle exceptions. If sending succeeds while updating the outbox fails, duplicate prevention or reconciliation policies are needed.

**Step 3 — Renderer produces both versions**

~~~java
public RenderedEmail render(OrderShippedEvent event) {
    String subject = "Order " + event.orderCode() + " has been shipped";

    String plain = """
            Order %s has been shipped.
            Tracking code: %s
            Track here: %s
            """.formatted(
            event.orderCode(),
            event.trackingNumber(),
            event.trackingUrl()
    );

    String html = shippedTemplate.render(event);

    return new RenderedEmail(subject, plain, html);
}
~~~

`shippedTemplate` is the application's template renderer; when rendering HTML, escape text and validate URLs. Plain text and HTML use the same event snapshot.

**Step 4 — Mail service sends**

The mail service calls:

~~~java
helper.setText(content.plainText(), content.htmlText());
mailSender.send(message);
~~~

The sending layer does not guess order status itself. It accepts the selected content and is responsible for MIME construction and submission.

## 27. Common design mistakes

| Mistake | Consequence | Better approach |
|---|---|---|
| Sending email inside setters/entities | Domain coupled to SMTP, hard-to-control side effects | Emit events or write outbox from application services |
| Sending on every entity save | Duplicate emails when metadata changes | Send on meaningful transitions/events |
| Relying on current state when worker runs | Content may mismatch the original event | Use appropriate event snapshots/versions |
| One shared template for every state | Recipients cannot tell what happened | Explicit event/status-to-template mapping |
| One giant switch holding all HTML | Hard to maintain and test | Separate resolver, renderer, and templates |
| Plain text and HTML pulling separate data | Both versions may contradict each other | Render from the same immutable model |
| Sending before transaction commit | Emails may announce rolled-back changes | AFTER_COMMIT or outbox |
| Using only in-memory events for critical notices | Events can be lost on process crash | Transactional outbox |
| Blind retries on timeout | Can send duplicates | Event IDs, attempt tracking, and reconciliation |
| Sending the same content to every audience | Leaks internal data | Separate templates and recipient policies per audience |
| Using unverified payload URLs | Open redirect/phishing or SSRF during resource fetches | Build URLs from allowed domains and validate events |
| Marking DELIVERED right after send | Misreports delivery status | Use SENT_TO_PROVIDER and process bounce events |
| Emailing every technical change | Annoys recipients | Notification policy filtering meaningful events |

## 28. State-driven notification design workflow

A workflow applicable to many business entities:

1. **List valid states and transitions** of the entity.
2. **Identify events** emitted when transitions are accepted.
3. **Decide audience and recipients** for each event.
4. **Select content to communicate**: subject, plain text, HTML, links, and attachments if needed.
5. **Create templates by event/locale/audience** as content variants grow.
6. **Persist snapshots or payloads** so delayed sends stay accurate.
7. **Write notification/outbox records** in the same transaction when high reliability is required.
8. **Render and send via JavaMailSender** in the appropriate worker or listener.
9. **Record attempts and outcomes**; apply bounded retries and deduplication.
10. **Verify experience** in email clients while keeping plain-text bodies complete.

Not every application needs an outbox or template engine on day one. For a small system, an application service + resolver + mail service may be enough. As reliability needs, state counts, and volume grow, add queues, outboxes, and dedicated templating.

## 29. Key takeaways

Email content varies with business state when the application maps **transitions or business events** to appropriate notifications. Current state tells you where an entity stands; an event tells you what just happened. Send emails only when a user-meaningful event occurs, not merely because an entity was saved.

In Spring Framework Mail, separate business rules, template selection, content rendering, and mail sending into distinct responsibilities. **JavaMailSender** and **MimeMessageHelper** build the message; `setText(plainText, htmlText)` provides both content versions. Plain text and HTML must use the same data, recipients, and event-appropriate actions.

For critical notifications, pay attention to transaction commit timing, transactional outboxes, event identity, idempotency, retries, and unknown outcomes. Control recipients, locales, URLs, tokens, and sensitive data before sending. **A good email accurately reflects what just happened, speaks clearly to the right recipient, and offers a next step that is still valid.**
