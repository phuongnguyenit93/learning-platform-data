# Rendering Templates Outside Business Transactions When Needed

A Spring application may send order confirmation emails, invoices, or status-change notifications. Typically, business logic must update data in the database first; only afterward does the application build email content from a template and send it via SMTP.

If template rendering or email sending runs inside the business transaction, the transaction can be prolonged by unnecessary work, hold database connections and locks longer, or encounter an external error that makes the business outcome hard to reason about. An email could also be sent before the transaction commits successfully, causing the user to receive notification of a change that was never actually saved.

Therefore, when needed, **separate template rendering from the business-update transaction**. A common organization is fetching the required data into an immutable DTO inside the transaction, committing the change, and then rendering and sending the email in a subsequent step. For systems requiring high reliability, you can use post-commit events or a transactional outbox to hand sending off to a worker.

This does not mean every template must run asynchronously. A small template that only renders from already-fetched data and does not prolong the transaction may not need separation. The decision should be based on processing time, email criticality, data consistency requirements, and how the system recovers on send failure.

## 1. Business Transactions and Email Rendering Are Two Different Jobs

A business transaction typically handles data changes that must commit together:

- Confirming an order.
- Updating payment status.
- Recording change history.
- Deducting inventory or creating related records.
- Saving information needed for notification.

Template rendering is the process of turning data into content:

- Reading an HTML or plain-text template.
- Inserting data into placeholders.
- Applying date, currency, and language formatting.
- Generating the subject, body, and sending metadata strings.

Sending email is an I/O operation with an external system:

- Connecting to SMTP or an email delivery service.
- Authenticating.
- Transmitting the message.
- Receiving an acceptance or rejection response.

You can visualize it as:

~~~text
Business transaction
    |
    +-- Read and validate data
    +-- Update order status
    +-- Write related records
    +-- Create notification data snapshot
    |
    v
COMMIT
    |
    v
Render template
    |
    v
Create MimeMessage
    |
    v
Send via JavaMailSender
~~~

The three parts have different timing and failure modes. A database transaction can roll back its own database changes. An SMTP server is an external system; having sent an email cannot be rolled back merely by rolling back a database transaction.

### 1.1. Example Doing Everything in One Transaction

A commonly seen implementation:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();
    orderRepository.save(order);

    String html = templateRenderer.render(order);
    mailService.send(order.getCustomerEmail(), html);
}
~~~

In this method:

1. The database transaction begins.
2. The order is updated.
3. The template is rendered.
4. The application calls SMTP.
5. The transaction only completes when the method finishes and the interceptor handles commit.

If SMTP is slow, the transaction stays open while waiting. If SMTP throws an exception and that exception rolls back the transaction, the database may not save the changes, yet if SMTP already accepted the email before another error occurred, the email cannot be recalled.

This is an issue of **transaction boundaries and side effects**, not merely a performance issue.

### 1.2. Key Risks

| Problem | What Can Happen |
| --- | --- |
| Slow SMTP response | Database transaction holds resources longer |
| Complex template | CPU, file reads, or data processing lengthen transaction duration |
| Mail send failure | Business logic may roll back even though the database update was valid |
| Transaction rollback after SMTP accepted mail | Email notifies of an uncommitted change |
| Retrying the entire business operation | May re-execute business logic or send duplicate emails |
| Using a JPA entity in a worker | Lazy fields may no longer be accessible after the transaction |

Not every case leads to failure. A fast render call with no I/O that does not prolong the transaction can work fine. However, **sending email over the network inside a business transaction** commonly creates an unnecessary dependency between the database and an external service.

## 2. What Does Rendering Templates Outside a Transaction Mean?

Rendering outside a transaction means building email content is performed after the business transaction has finished, or in a workflow that does not participate in that transaction.

Example:

~~~text
Application service
    |
    | call business bean
    v
OrderService.confirmOrder()
    |
    | @Transactional
    | update database
    | return snapshot DTO
    v
Transaction commit completes
    |
    | transactional method has returned
    v
MailTemplateRenderer.render(snapshot)
    |
    v
JavaMailSender.send(...)
~~~

Here, the **snapshot** is data extracted while the transaction was still active. The renderer does not need to hold a JPA entity or reopen the database to fetch lazy fields.

There are two distinct benefits:

1. **Post-commit rendering:** content is generated after business changes have committed.
2. **Dedicated-worker rendering:** content-building and mail-sending time does not sit inside the user's request or transaction.

These two benefits can be combined, but they are not synonymous. Post-commit rendering on the same thread can still keep an HTTP request waiting; asynchronous rendering decouples processing time from the request.

### 2.1. Not Every Template Engine Needs a Database

A template engine typically takes an existing model and returns a string:

~~~text
Template + Model -> Rendered HTML
~~~

Example:

~~~text
Template:
  Hello {{customerName}},
  Order {{orderNumber}} has been confirmed.

Model:
  customerName = "An"
  orderNumber = "ORD-2026-001"

Result:
  Hello An,
  Order ORD-2026-001 has been confirmed.
~~~

If the model already contains enough data, the renderer does not need to query the database. This is why DTO snapshots are so useful: they turn template rendering into an almost purely data-driven step that can run independently of the persistence context.

### 2.2. When Should You Consider Separating?

Consider separating rendering from the transaction when:

- Templates have many sections, languages, or formatting operations.
- Emails have multiple attachments generated from report data.
- Rendering reads files, accesses storage, or calls external services.
- Multiple emails are generated for a single business operation.
- SMTP has unstable latency.
- HTTP requests should not wait for email sending to complete.
- Emails need retries independent of database updates.
- The system needs to persist the status of each render/send attempt.

If a template has only a few simple fields, generating a short string in the same transaction may not warrant adding events, queues, and workers. Separate based on real needs instead of turning every email into a complex pipeline.

## 3. Data Snapshots: An Important Boundary Between JPA and the Renderer

A common mistake when moving mail sending to a worker is passing entities directly:

~~~java
publisher.publishEvent(new OrderConfirmedEvent(order));
~~~

After the transaction ends, the entity may be detached from the persistence context. If the template accesses a lazy relationship:

~~~java
order.getCustomer().getAddresses()
~~~

a **LazyInitializationException** may occur, or the renderer may unintentionally trigger new queries if a persistence context remains open via another mechanism.

Instead of passing entities, create a **DTO containing only the data the email needs**.

~~~java
public record OrderMailData(
        String recipient,
        String customerName,
        String orderNumber,
        String orderDate,
        String totalAmount,
        String shippingAddress
) {}
~~~

Inside the transaction:

~~~java
@Transactional
public OrderMailData confirmOrder(UUID orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.confirm();

    return new OrderMailData(
            order.getCustomerEmail(),
            order.getCustomerName(),
            order.getNumber(),
            formatDate(order.getConfirmedAt()),
            formatMoney(order.getTotal()),
            order.getShippingAddressText()
    );
}
~~~

When the transactional method returns through the Spring proxy, the transaction is committed before the caller proceeds to the next step in the normal flow. The caller receives the DTO already holding the data needed for rendering.

### 3.1. Why Use Immutable DTOs?

DTOs such as Java records have useful traits:

- Carry only the fields the template needs.
- Do not depend on a Hibernate session.
- Prevent the renderer from accidentally mutating business entities.
- Easy to serialize for storing in a queue or outbox.
- Usable in unit tests without a database.
- Preserve values at the moment the business event was confirmed.

Not every field has to be a String. You can pass **Instant**, **BigDecimal**, enums, or meaningful types and let the renderer format by locale. However, establish stable formatting rules so emails do not change unexpectedly.

### 3.2. Snapshots vs. Reloading Data Differ

There are two strategies:

| Strategy | Approach | Meaning |
| --- | --- | --- |
| **Snapshot** | Record all data needed for rendering in the DTO/event inside the transaction | Email reflects data at the moment the business event occurred |
| **Reload** | Pass only the ID; worker queries database after commit | Email reflects data at the moment the worker reads it |

For example, an order is confirmed at 10:00 with a total of 500,000 VND. At 10:05, a job adjusts data or updates the address before the mail worker sends.

- With a snapshot, the email still shows the data at confirmation time.
- With reload, the email may show newer data.

No single choice fits every system. For invoices, receipts, and event notifications, snapshots are usually important. For reminder emails needing the latest state, reloading can make sense.

### 3.3. Do Not Put Unnecessary Sensitive Data into Events

A snapshot must have enough data to render, but should not include every entity field. Include only information permitted to be sent via email. Avoid putting passwords, internal tokens, sensitive payment data, or unnecessary personal information into event payloads or outboxes.

## 4. Simple Approach: Call a Transactional Service and Render After It Returns

If the requirement is simply to **ensure the transaction finishes before rendering and sending**, you can use two separate beans.

Business bean:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public OrderMailData confirm(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();

        order.confirm();

        return new OrderMailData(
                order.getCustomerEmail(),
                order.getCustomerName(),
                order.getNumber(),
                order.getTotal().toPlainString()
        );
    }
}
~~~

Orchestrator bean:

~~~java
@Service
public class OrderConfirmationFacade {

    private final OrderService orderService;
    private final OrderMailService mailService;

    public OrderConfirmationFacade(
            OrderService orderService,
            OrderMailService mailService
    ) {
        this.orderService = orderService;
        this.mailService = mailService;
    }

    public void confirmAndNotify(UUID orderId) {
        OrderMailData snapshot = orderService.confirm(orderId);

        // confirm() has returned through the proxy;
        // the business transaction has ended.
        mailService.sendConfirmation(snapshot);
    }
}
~~~

Mail-sending bean:

~~~java
@Service
public class OrderMailService {

    private final OrderMailTemplateRenderer renderer;
    private final JavaMailSender mailSender;

    public OrderMailService(
            OrderMailTemplateRenderer renderer,
            JavaMailSender mailSender
    ) {
        this.renderer = renderer;
        this.mailSender = mailSender;
    }

    public void sendConfirmation(OrderMailData data) {
        String html = renderer.render(data);

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, false, "UTF-8"
        );

        try {
            helper.setTo(data.recipient());
            helper.setSubject(
                    "Order confirmation " + data.orderNumber()
            );
            helper.setText(html, true);
        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Could not create confirmation email", ex
            );
        }

        mailSender.send(message);
    }
}
~~~

**MailPreparationException** in the example is an application-defined exception or can be replaced with an appropriate exception type. Import the corresponding Spring/Jakarta classes and handle errors per project conventions.

Call flow:

~~~text
OrderConfirmationFacade
    |
    v
OrderService.confirm()
    |
    +-- Transaction begin
    +-- Update order
    +-- Build OrderMailData
    +-- Commit
    |
    v
Return snapshot
    |
    v
OrderMailService
    |
    +-- Render template
    +-- Build MimeMessage
    +-- Send
~~~

Pros:

- Easy to understand with few components.
- Rendering is guaranteed to occur after the transactional method returns successfully.
- Does not pass detached entities to the renderer.
- Does not send email if the commit fails.

Limitations:

- The request caller still waits for rendering and SMTP.
- If sending fails after commit, the order remains confirmed.
- If the process stops after commit but before calling the mail service, the notification may not be sent.

This approach works when emails do not require a durable async pipeline and sending latency is acceptable.

### 4.1. Note on Spring Proxies and Self-Invocation

In Spring, **@Transactional** is usually applied through a proxy. If a method in the same class calls another `@Transactional` method via **this.method()**, the internal call may bypass the proxy and the annotation will not apply as expected.

Therefore, the example splits **OrderService** and **OrderConfirmationFacade** into two beans. The caller invokes via the bean proxy, so the transaction is managed at the proper boundary.

## 5. Using Transactional Events for Post-Commit Processing

When business logic wants to publish an event and another component handles the email after the transaction succeeds, Spring provides **@TransactionalEventListener**.

Event example:

~~~java
public record OrderConfirmedEvent(
        OrderMailData mailData
) {}
~~~

In the business service:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher publisher;

    public OrderApplicationService(
            OrderRepository orderRepository,
            ApplicationEventPublisher publisher
    ) {
        this.orderRepository = orderRepository;
        this.publisher = publisher;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();

        order.confirm();

        OrderMailData snapshot = new OrderMailData(
                order.getCustomerEmail(),
                order.getCustomerName(),
                order.getNumber(),
                order.getTotal().toPlainString()
        );

        publisher.publishEvent(
                new OrderConfirmedEvent(snapshot)
        );
    }
}
~~~

Listener:

~~~java
@Component
public class OrderMailEventListener {

    private final OrderMailService mailService;

    public OrderMailEventListener(OrderMailService mailService) {
        this.mailService = mailService;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        mailService.sendConfirmation(event.mailData());
    }
}
~~~

The listener is invoked only when the transaction commits successfully. If the transaction rolls back, the event is not processed in the AFTER_COMMIT phase.

### 5.1. Phases of TransactionalEventListener

Spring supports several phases:

| Phase | When the Listener Is Called |
| --- | --- |
| **BEFORE_COMMIT** | Before the transaction commits |
| **AFTER_COMMIT** | After a successful commit |
| **AFTER_ROLLBACK** | After rollback |
| **AFTER_COMPLETION** | After the transaction completes, whether commit or rollback |

For emails confirming a successfully saved business operation, **AFTER_COMMIT** is usually appropriate.

**BEFORE_COMMIT** is unsuitable if the goal is preventing notifications for uncommitted changes: the listener still runs before the commit occurs and the transaction can still fail afterward.

### 5.2. What If There Is No Transaction?

By default, **@TransactionalEventListener** binds to an active transaction. If an event is published when no transaction is active, the listener may not be invoked.

There is an option **fallbackExecution=true** to run the listener even without a transaction, but that changes the semantics of the event. Only enable it when business rules accept handling events not bound to a transaction.

Do not enable fallback just to fix a listener not firing without first verifying whether the event was actually published inside a transaction.

### 5.3. AFTER_COMMIT Does Not Make Emails Durable

In-memory Spring events are not automatically persisted durably. A scenario can still occur:

~~~text
1. Database commit succeeds.
2. Process stops abruptly.
3. Listener has not yet processed the event.
4. No email is sent.
~~~

Transactional events set the right **timing** for processing, but do not by themselves provide event recovery after an application crash.

If the email is a notification that can be retried manually, this approach may suffice. If losing the send intent is unacceptable, consider a durable queue or transactional outbox.

## 6. Asynchronous Rendering and Sending After Commit

If you do not want user requests to wait for rendering or SMTP, you can combine **@TransactionalEventListener(AFTER_COMMIT)** with **@Async**.

Enable async processing:

~~~java
@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean("mailExecutor")
    public Executor mailExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("mail-worker-");
        return executor;
    }
}
~~~

The numbers are examples. Real configuration should be based on SMTP provider speed, send volume, and application capacity.

Listener:

~~~java
@Component
public class AsyncOrderMailListener {

    private final OrderMailService mailService;

    public AsyncOrderMailListener(OrderMailService mailService) {
        this.mailService = mailService;
    }

    @Async("mailExecutor")
    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        mailService.sendConfirmation(event.mailData());
    }
}
~~~

Processing flow:

~~~text
HTTP request
    |
    v
@Transactional confirmOrder()
    |
    +-- Update database
    +-- Publish OrderConfirmedEvent
    +-- Commit
    |
    v
AFTER_COMMIT listener
    |
    v
Submit task to mailExecutor
    |
    v
Worker thread
    |
    +-- Render template
    +-- Create MimeMessage
    +-- Send SMTP
    |
    v
End task
~~~

In this model:

- The business transaction finishes before the listener runs.
- Rendering and SMTP run on an executor thread.
- The HTTP request can finish without waiting for SMTP if the caller thread does not wait on the result.
- Errors in the async task do not automatically propagate back to the already-completed request.

### 6.1. @Async Does Not Automatically Create Retries

If SMTP fails in the async listener, the exception does not roll back the already-committed business transaction. Nor does it automatically make Spring resend the email.

Clearly decide how to handle failures:

- Log with a correlation ID and error status.
- Report error details to the monitoring system.
- Route the task into a retry mechanism.
- Persist send status so operators or workers can resume.
- Distinguish transient errors like timeouts from permanent errors like rejected recipients.

A **ThreadPoolTaskExecutor** also has a bounded queue. If the queue fills up or the application stops, tasks may be rejected or lost depending on configuration and shutdown timing. This is an in-process asynchronous execution mechanism, not a durable queue.

### 6.2. Configure the Executor Deliberately

Do not use an unbounded executor for all emails. When event volume spikes, the system can spawn many threads or build a huge queue, consuming memory and pressuring the SMTP provider.

Configure:

- Minimum and maximum thread counts.
- Queue capacity.
- Thread name prefix for observability.
- Policy when the queue is full.
- Shutdown behavior.
- Metrics for queue depth, active threads, and send failures.

If there are multiple email categories, use separate executors or queues for transactional emails and newsletter emails so one workload does not starve the other.

### 6.3. Do Not Pass JPA Entities into Async Listeners

An async worker runs on a different thread and does not inherit the calling thread's transaction or persistence context. Do not pass an entity expecting the worker to read lazy relationships.

Pass **OrderMailData** or a serializable event payload. If only an order ID is passed, the worker must open a transaction to read data using a clearly defined strategy.

## 7. Transactional Outbox for More Reliable Email Sending

If an important email must not lose its send intent when a process crashes, in-memory events and @Async are usually not enough.

A **transactional outbox** stores an email-send request record in the **same database transaction** as the business change.

Example records:

~~~text
orders
  id = 1001
  status = CONFIRMED

outbox_events
  id = 9001
  event_type = ORDER_CONFIRMED
  payload = { snapshot data ... }
  status = PENDING
~~~

Both are committed in the same transaction:

~~~text
BEGIN TRANSACTION
    UPDATE orders SET status = 'CONFIRMED'
    INSERT INTO outbox_events (..., 'PENDING')
COMMIT
~~~

After commit, a separate worker reads the outbox:

~~~text
Outbox worker
    |
    v
Load pending event
    |
    v
Render template
    |
    v
Send email
    |
    v
Mark event as SENT
~~~

If the process stops after commit, the outbox record remains in the database. The worker can resume when the system restarts.

### 7.1. Outbox Table Example

An illustrative schema:

~~~sql
CREATE TABLE mail_outbox (
    id              UUID PRIMARY KEY,
    event_type      VARCHAR(100) NOT NULL,
    payload         TEXT NOT NULL,
    status          VARCHAR(20) NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP NULL,
    created_at      TIMESTAMP NOT NULL,
    sent_at         TIMESTAMP NULL,
    last_error      TEXT NULL
);
~~~

Fields can vary by database engine and event organization. **payload** can store a serialized DTO, or an identifier for the worker to retrieve a managed snapshot.

### 7.2. Worker Processing the Outbox

Pseudo-code:

~~~java
public void processPendingMail() {
    List<MailOutboxEvent> events =
            outboxRepository.claimPendingBatch(50);

    for (MailOutboxEvent event : events) {
        try {
            OrderMailData data = deserialize(event.payload());
            mailService.sendConfirmation(data);

            outboxRepository.markSent(event.id());
        } catch (Exception ex) {
            outboxRepository.scheduleRetry(
                    event.id(),
                    calculateNextAttempt(event.attempts()),
                    classify(ex)
            );
        }
    }
}
~~~

This is pseudo-code describing the flow. In a real application, **claimPendingBatch** needs locking or a lease mechanism so two workers do not process the same event concurrently. Status updates also need separate transactions and handling for workers dying mid-execution.

### 7.3. What Does the Outbox Solve?

- Email-send intent is persisted alongside business changes.
- Pending events can be recovered after an application restart.
- Retries are decoupled from user requests.
- Provides tracking status and processing history.
- Allows rate limiting and batching sends.

### 7.4. Outbox Does Not Guarantee Exactly-Once Delivery

There is an important scenario:

~~~text
1. Worker sends email.
2. SMTP server accepts email.
3. Worker crashes before updating outbox to SENT.
4. Worker restarts and resends event.
~~~

The recipient may receive the email twice. SMTP and the database do not participate in a single distributed transaction that can roll back atomically. Thus, an outbox typically provides **at-least-once processing** for send intent, rather than guaranteeing an email appears exactly once in an inbox.

To reduce the impact of duplicate sends:

- Generate a stable **event ID**.
- Record the ID in logs and task metadata.
- Design emails or business logic to tolerate duplicate notifications.
- Use an idempotency key if the provider supports one under a specific contract.
- Avoid blindly retrying a completely ambiguous outcome without a policy.

The **Message-ID** header is useful for correlating messages, though by itself it does not force SMTP servers or email clients to deduplicate messages.

## 8. Choosing Between Rendering a Snapshot or Rendering After Worker Reloads Data

When a worker runs after commit, you can pass a snapshot or only pass an ID.

### 8.1. Full Snapshot

Inside the transaction:

~~~java
OrderMailData data = new OrderMailData(
        order.getCustomerEmail(),
        order.getCustomerName(),
        order.getNumber(),
        formatMoney(order.getTotal())
);

outboxRepository.save(
        MailOutboxEvent.pending(
                eventId,
                serialize(data)
        )
);
~~~

The worker reads the payload and renders directly.

Pros:

- Email reflects the exact data at event time.
- No dependency on entities or lazy loading.
- Fewer database re-queries.
- Easy to reproduce content when debugging if the snapshot is stored under policy.

Limitations:

- Larger payload.
- May store personal data in the outbox, requiring retention and access-control policies.
- If the template changes, the same snapshot may render a different email than the previous version.

### 8.2. Storing Only the ID and Reloading

Inside the transaction, the outbox only saves:

~~~json
{
  "eventId": "9001",
  "orderId": "1001",
  "eventType": "ORDER_CONFIRMED"
}
~~~

The worker opens a transaction to read the order and build a new DTO.

Pros:

- Small payload.
- Does not duplicate much data.
- Worker can fetch the latest state.

Limitations:

- Email may differ from the state at event creation time.
- The record may have been deleted or become inaccessible.
- Must define a policy if data changes between event creation and worker execution.

### 8.3. Optionally Saving Both Snapshot and Template Version

For critical emails like invoices or transaction confirmations, you can store:

- Snapshot of data needed for rendering.
- Template key.
- Template version.
- Locale.
- Event ID.
- Business timestamp.
- Determined and validated recipient.

This helps the system explain why an email had particular content and re-render consistently when needed. Weigh storage size and personal-data protection policies.

## 9. Separating TemplateRenderer from MailSender

A clean organization splits two responsibilities:

- **TemplateRenderer** takes data and returns the rendered subject/body.
- **MailSenderService** takes rendered content, builds MimeMessage, and sends.

DTO example:

~~~java
public record RenderedMail(
        String recipient,
        String subject,
        String htmlBody,
        String textBody
) {}
~~~

Interface renderer:

~~~java
public interface MailTemplateRenderer {
    RenderedMail renderOrderConfirmation(OrderMailData data);
}
~~~

Sending service:

~~~java
@Service
public class MailDeliveryService {

    private final JavaMailSender sender;

    public MailDeliveryService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void send(RenderedMail mail) throws MessagingException {
        MimeMessage message = sender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message, false, "UTF-8"
        );

        helper.setTo(mail.recipient());
        helper.setSubject(mail.subject());
        helper.setText(mail.textBody(), mail.htmlBody());

        sender.send(message);
    }
}
~~~

This structure helps:

- Unit test the renderer without SMTP.
- Unit test mail delivery with a mocked JavaMailSender.
- Swap template engines without editing the transport layer.
- Separate template errors from SMTP connection errors.
- Optionally store RenderedMail or snapshot data per policy if needed.

In a large system, **RenderedMail** can also include From, Reply-To, Cc/Bcc, attachment metadata, and a correlation ID. Recipient values must be controlled by business rules; never let the template decide the recipient.

## 10. Template Rendering Example with Mustache

A template engine typically takes a **template** and a **model**, then returns a string. Example using Mustache with placeholders:

File **src/main/resources/templates/mail/order-confirmed.html**:

~~~html
<!doctype html>
<html lang="vi">
<body>
  <h1>Hello {{customerName}}</h1>
  <p>Order <strong>{{orderNumber}}</strong> has been confirmed.</p>
  <p>Total amount: {{totalAmount}}</p>
  <p>Shipping address: {{shippingAddress}}</p>
</body>
</html>
~~~

Model:

~~~java
public record OrderMailData(
        String recipient,
        String customerName,
        String orderNumber,
        String totalAmount,
        String shippingAddress
) {}
~~~

Illustrative renderer:

~~~java
import com.samskivert.mustache.Mustache;
import com.samskivert.mustache.Template;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;
import org.springframework.stereotype.Component;

@Component
public class OrderMailTemplateRenderer {

    private final Template template;

    public OrderMailTemplateRenderer() throws IOException {
        ClassPathResource resource =
                new ClassPathResource(
                        "templates/mail/order-confirmed.html"
                );

        String source = StreamUtils.copyToString(
                resource.getInputStream(),
                StandardCharsets.UTF_8
        );

        this.template = Mustache.compiler().compile(source);
    }

    public String render(OrderMailData data) {
        Map<String, Object> model = Map.of(
                "customerName", data.customerName(),
                "orderNumber", data.orderNumber(),
                "totalAmount", data.totalAmount(),
                "shippingAddress", data.shippingAddress()
        );

        return template.execute(model);
    }
}
~~~

The example illustrates loading a template from the classpath at bean initialization and compiling it once for reuse. In a real application, manage resources/exceptions per project standards, and you can use the template engine's auto-configuration if the corresponding starter is integrated.

Mustache escapes HTML by default for ordinary **{{value}}** placeholders in common usage. Do not use unescaped placeholders such as **{{{value}}}** for user data unless content has been sanitized and HTML is permitted. The template engine does not decide email recipients or sending permissions.

### 10.1. Rendering Without Entities

The renderer only receives **OrderMailData**. It knows nothing about JPA repositories, transaction managers, or SMTP hosts. Thus it can be called post-commit, in an async worker, or in a retry job.

### 10.2. Do Not Re-Compile Templates per Send If Unnecessary

Templates can be compiled once and reused if the template engine supports it. Reading files and compiling on every email can create unnecessary overhead.

If hot reload or runtime template changes are supported, establish a clear caching/invalidation policy. With versioned templates for transactional emails, you can compile/cache by version.

## 11. What Happens If Rendering Fails After Commit?

A template error can occur because of:

- Template file does not exist.
- Wrong placeholder or template syntax.
- Model data missing a required field.
- Template engine fails to initialize.
- New template incompatible with old data.
- Encoding or resource failure.

If rendering runs after commit, **the business change has still been committed**. This is usually right: once an order is confirmed, a template error should not automatically revert the order back to unconfirmed.

However, the system must record the failed email task so it can be reprocessed.

A simple state flow:

~~~text
PENDING
   |
   v
RENDERING
   |
   +-- error --> RETRY_WAIT / FAILED
   |
   v
READY_TO_SEND
   |
   v
SENDING
   |
   +-- error --> RETRY_WAIT / FAILED
   |
   v
SENT
~~~

You can separate rendering status and sending status:

| Status | Meaning |
| --- | --- |
| **PENDING** | Send request has been created |
| **RENDER_FAILED** | Could not build content from template/model |
| **RENDERED** | Content has been generated |
| **SEND_FAILED** | Transport failed to send based on known outcome |
| **SENT_TO_PROVIDER** | SMTP/provider accepted per response |
| **DELIVERY_CONFIRMED** | Delivery signal received per provider definition |

Do not label **SENT_TO_PROVIDER** as "user has read." It is only a milestone at the sending layer.

### 11.1. Error Classification

**Rendering errors** usually relate to templates, data, or encoding. Fixing the template/model may be required before retrying.

**Transient SMTP errors** such as timeouts or temporary server rejections may suit retries with backoff.

**Permanent errors** such as syntactically invalid recipients or policy rejections should generally not be retried infinitely.

**Ambiguous outcomes** such as connection loss after the server may have received DATA must be handled carefully because retrying can send duplicates.

### 11.2. Do Not Let Async Exceptions Disappear

With @Async, exceptions are not thrown back to the already-finished request caller. Record exceptions in the listener/worker, emit appropriate metrics/logs, or transition the task to a retry state. An **AsyncUncaughtExceptionHandler** can help log errors from void async methods, but it does not replace durable queues and persistent state.

## 12. Avoiding Sending Emails Before Transaction Commit

This is the most important principle of business notifications.

Suppose:

~~~text
1. Update order to CONFIRMED.
2. Send confirmation email.
3. A subsequent database operation fails.
4. Transaction rollback.
~~~

The result can be:

~~~text
Database: order is not confirmed
Email: "Your order has been confirmed"
~~~

The two systems are no longer consistent.

If an email confirms a saved change, issue the send task **after a successful commit**:

- Caller invokes transactional service and sends after the method returns.
- Use **@TransactionalEventListener(AFTER_COMMIT)**.
- Use a **transactional outbox** so a worker reads post-commit.

Do not use **BEFORE_COMMIT** for success-confirmation emails if the transaction can still roll back after the listener.

### 12.1. Can a Sent Email Be Rolled Back?

No. SMTP is an external side effect. A database rollback only affects resources participating in that database transaction. It does not delete an email already accepted by an SMTP server.

If business rules require a correction notice when an action is later reversed, generate a new business-meaningful notification instead of assuming the old message can be recalled from the inbox.

## 13. Can @Transactional(propagation = NOT_SUPPORTED) Be Used?

Spring supports **NOT_SUPPORTED** propagation to execute a method without participating in an existing transaction. If the caller has a transaction, Spring can suspend that transaction for the duration of the proxy-managed method call.

Example:

~~~java
@Service
public class MailRenderingService {

    private final MailTemplateRenderer renderer;

    public MailRenderingService(MailTemplateRenderer renderer) {
        this.renderer = renderer;
    }

    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public RenderedMail render(OrderMailData data) {
        return renderer.renderOrderConfirmation(data);
    }
}
~~~

This is useful when you need to ensure a rendering step does not participate in the caller's transaction. However, understand the limits:

- The method must be called through a Spring proxy for propagation to take effect in standard proxy mode.
- It **does not by itself make email sending durable**.
- If the renderer needs database access, those operations are not protected by the suspended transaction.
- Do not pass lazy entities into the renderer expecting data to remain accessible.
- **NOT_SUPPORTED** does not replace **AFTER_COMMIT** when the goal is sending only after the business transaction commits.

Therefore, if you only want to render and send after business logic succeeds, a **post-commit** boundary is usually clearer to express. NOT_SUPPORTED is a propagation-control tool for a specific situation.

## 14. Transaction Boundaries and Data Consistency

An important question: if rendering runs after commit, is the email data still as accurate as when the transaction updated it?

The answer depends on the data source the renderer receives.

### 14.1. Snapshot Inside the Transaction

Inside the transaction, read and format the needed data and put it into a DTO:

~~~java
OrderMailData snapshot = new OrderMailData(
        order.getCustomerEmail(),
        order.getCustomerName(),
        order.getNumber(),
        formatMoney(order.getTotal())
);
~~~

After commit, the renderer only uses the snapshot. This fits when the email describes an event that occurred at a specific point in time.

### 14.2. Reload After Commit

If the event only has orderId, the worker loads the latest order. You must decide whether, if the order was modified, deleted, or changed status, the email should:

- Skip the task?
- Render according to the new state?
- Use historical data?
- Mark the event failed for manual handling?

This is a business rule, not a template engine decision.

### 14.3. Using History or Versions

For workflows requiring auditing, you can store a data version or snapshot at event time. Emails can reference that version instead of reading the current record.

This is useful for invoices, receipts, price notices, and confirmations with legal or financial significance. Comply with data retention and protection policies.

## 15. Organizing Templates and Render Data

An email template should typically have:

- **Template key:** identifies the email type, e.g., ORDER_CONFIRMED.
- **Locale:** recipient's language/region.
- **Subject template:** subject pattern.
- **HTML template:** HTML content.
- **Plain text template:** fallback text content.
- **Model DTO:** data to populate.
- **Template version:** if old content needs to be reproduced.
- **Inline resources/attachments:** if the template references resources.

Model example:

~~~java
public record OrderMailData(
        String recipient,
        String customerName,
        String orderNumber,
        String totalAmount,
        String orderDate,
        String locale
) {}
~~~

One file-naming convention:

~~~text
templates/
└── mail/
    ├── order-confirmed-vi.html
    ├── order-confirmed-vi.txt
    ├── order-confirmed-en.html
    └── order-confirmed-en.txt
~~~

The renderer can pick the template by locale and event type. Template selection should be determined from validated data, not by taking an arbitrary file path from a request.

### 15.1. Do Not Let Templates Decide Transactions

Templates only present data. Do not place database-update, inventory-deduction, payment, or authorization logic inside the template engine. Those belong in application/domain services and business transactions.

### 15.2. Do Not Let Templates Decide Arbitrary Recipients

The recipient is transport information and carries security implications. Store the recipient in a business-validated DTO, or have the worker look it up per policy. Never let template content hold placeholders that decide the recipient on their own.

### 15.3. HTML escaping

The template engine must escape dynamic data according to HTML context. With Mustache, ordinary **{{value}}** placeholders are escaped by default in common usage; unescaped syntax can introduce raw markup into emails.

Do not pass user-supplied HTML into templates without a clear sanitizer and policy. Rendering outside a transaction does not replace input control or HTML security.

## 16. Testing When Rendering Outside Transactions

When separating the template renderer and mail sender, each part can be tested independently.

### 16.1. Unit Testing the Renderer

Pass a sample DTO to the renderer:

~~~java
OrderMailData data = new OrderMailData(
        "customer@example.net",
        "An",
        "ORD-1001",
        "500.000 VND",
        "12/11/2026",
        "vi"
);

String html = renderer.render(data);
~~~

You can verify the result includes customer name, order number, amount, and no unreplaced placeholders. No SMTP server is needed for this test.

### 16.2. Unit Testing the Mail Service

Mock **JavaMailSender** to confirm the service constructs and sends a MimeMessage. Use **ArgumentCaptor** to inspect the message and verify required headers/body via the Jakarta Mail API.

Tests should not depend on random MIME boundary ordering or specific byte encodings unless required by the application.

### 16.3. Integration Testing with an SMTP Capture Server

Use an SMTP sandbox/capture server in the test environment to verify:

- Whether the message is sent by SMTP transport.
- Whether Subject, From, and To are accurate.
- Whether HTML and plain text are packaged properly.
- Whether attachments and inline resources have matching Content-IDs.
- Whether test-environment credentials/TLS are configured properly.

Never use real customer mailboxes for automated tests.

### 16.4. Testing Transaction Boundaries

Verify that an AFTER_COMMIT listener runs only when the transaction commits successfully, and does not run on rollback. With async/outbox, also verify that events are saved, workers can resume after restarts, and retry states update properly.

These checks belong to the project's own testing phase; examples in this article describe expected behavior rather than claiming tests were executed in a repository.

## 17. Common Mistakes When Separating Rendering from Transactions

| Mistake | Cause | How to Fix |
| --- | --- | --- |
| Email reports success even though database rolled back | Sending before commit | Move sending to AFTER_COMMIT or outbox |
| LazyInitializationException in renderer | Passing JPA entity to worker | Create DTO snapshot inside transaction |
| Request still waits long | Moved to AFTER_COMMIT only, but listener runs synchronously | Use async executor or queue when needed |
| Email not sent after restart | Event lives only in memory | Use transactional outbox/durable queue |
| Duplicate emails sent | Worker crashes after SMTP accept before marking sent | Design retries, event IDs, and duplicate handling |
| Template fails while business logic committed | Rendering runs after commit | Record error and retry/alert independently |
| Email uses unexpectedly fresh data | Worker reloads entity after a delay | Store snapshot or data version |
| Async listener does not run | No transaction or event published in wrong place | Check transaction phase and event flow |
| Async task rejected | Executor queue full or shutdown | Monitor queue and use durable mechanism when needed |
| SMTP error does not reach request | Async method does not propagate exceptions to caller | Save error status, log, retry, or dead-letter |

### 17.1. Listener Does Not Run Because Event Was Published Outside a Transaction

**@TransactionalEventListener** depends on a transaction by default. If an event is published from a non-transactional method, the AFTER_COMMIT listener may not be called. Confirm the event is actually published inside the intended transaction; only use fallbackExecution when business rules permit.

### 17.2. Calling the Listener Directly Instead of Publishing an Event

If code calls the listener method directly, the event listener annotation and phase do not take effect as a Spring-managed event. Use **ApplicationEventPublisher.publishEvent(...)** or your chosen message/queue mechanism.

### 17.3. Using @Async Without Enabling Async Processing

Without **@EnableAsync** or proper async configuration, the method may not execute asynchronously as intended. Furthermore, internal calls within the same bean may bypass the async proxy.

### 17.4. Assuming AFTER_COMMIT Automatically Guarantees Exactly-Once

AFTER_COMMIT determines **when the listener is called** in the transaction lifecycle. It does not create a durable record, does not retry automatically, and does not guarantee SMTP accepts only once.

### 17.5. Marking SENT Before SMTP Accepts

If a worker updates status to SENT before calling send, a process crash can lose the task while the database still records it as sent. If it sends first and updates SENT afterward, a crash in between can cause duplicates. Design statuses, retries, and ambiguous-outcome handling within SMTP's limits.

## 18. Choosing a Solution Based on Business Requirements

| Requirement | Potentially Suitable Implementation |
| --- | --- |
| Very small template, synchronous send, no long transaction | Simple render-and-send flow |
| Only need to ensure email is not sent before commit | Call after transactional service returns or use AFTER_COMMIT |
| Request must not wait for SMTP | AFTER_COMMIT combined with @Async |
| Email must retry across process restarts | Transactional outbox or durable queue |
| Content must match data at confirmation time | DTO snapshot stored with event |
| Content must use the latest state | Worker reloads data per policy |
| Multiple email types needing separate tracking | Separate renderer, delivery service, and task status |
| Email has audit value | Snapshot/version/template version and processing history |

There is no single architecture for every application. Determine first whether the email is a **mandatory post-commit side effect** or merely a convenience notification; whether loss on process crash is acceptable; and whether duplicate sends can be tolerated.

## 19. Suggested Architecture for a Spring Mail System

For applications with critical transactional emails, an architecture can be organized as follows:

~~~text
HTTP / Application command
          |
          v
OrderApplicationService
    @Transactional
          |
          +-- Validate command
          +-- Update order
          +-- Build immutable mail snapshot
          +-- Insert outbox event
          |
          v
       COMMIT
          |
          v
Outbox polling worker
          |
          +-- Claim pending event
          +-- Resolve template version/locale
          +-- Render HTML and text
          +-- Build MimeMessage
          +-- JavaMailSender.send(...)
          +-- Update status/retry schedule
          |
          v
 SMTP provider
~~~

Components have clear responsibilities:

- **OrderApplicationService** modifies business data.
- **Mail snapshot** holds email data needed at confirmation time.
- **Outbox worker** handles post-commit tasks and can be rerun.
- **TemplateRenderer** generates subject/body.
- **MailDeliveryService** constructs MIME and calls JavaMailSender.
- **Outbox repository** manages statuses, retries, and history.

For smaller applications, you can omit the outbox and use a post-commit service call. As reliability needs increase, you can move to an outbox without stuffing SMTP logic into domain services.

## 20. Takeaways for Rendering Templates Outside Business Transactions

A **business transaction** should focus on modifying and committing data that must stay consistent. **Template rendering** turns a model into email content; **mail sending** is a side effect with an external system. Separating these three responsibilities keeps transactions shorter, avoids sending emails for rolled-back changes, and allows send errors to be handled independently.

The foundational practice is creating a **DTO snapshot inside the transaction**, letting the transaction commit, and only then rendering and sending. If you want post-commit event-driven handling, use **@TransactionalEventListener(AFTER_COMMIT)**. If requests should not wait, combine with **@Async** or a worker queue. If send intent must survive restarts with durable retries, use a **transactional outbox**.

Remember the limits: AFTER_COMMIT is not automatically durable; @Async does not automatically retry; an outbox does not guarantee SMTP exactly-once; and JPA entities should not be passed to renderers/workers. Choose boundaries fitting your consistency, latency, and reliability requirements in business operations.
