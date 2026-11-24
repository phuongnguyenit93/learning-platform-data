# Decoupling Mail Sending Use Cases from the Transport Layer

In a Spring application, sending email often starts with a short call to JavaMailSender. However, if a controller, business service, or use case constructs a MimeMessage itself, configures MimeMessageHelper, and calls JavaMailSender directly, the application logic becomes coupled to email transport details. Later, if you want to switch SMTP providers, move to an email service over HTTP API, send notifications through a queue, or test business logic without an SMTP server, the business code will have to change accordingly.

A more sustainable approach is **to let the use case decide when and why a notification needs to be sent, while the transport adapter is responsible for turning that request into a MIME email and delivering it to the provider**. The two parts communicate through an interface (port) defined by the application. The Spring Mail adapter implements that interface using JavaMailSender.

This separation keeps the use case focused on business rules, makes mail sending replaceable and independently testable, and keeps Spring Mail and Jakarta Mail types in the infrastructure layer.

## 1. The problem when a use case calls JavaMailSender directly

A business service might be written like this:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final JavaMailSender mailSender;

    public OrderService(
            OrderRepository orderRepository,
            JavaMailSender mailSender) {
        this.orderRepository = orderRepository;
        this.mailSender = mailSender;
    }

    public void confirmOrder(Long orderId) throws MessagingException {
        Order order = orderRepository.findById(orderId)
            .orElseThrow();

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setTo(order.getCustomerEmail());
        helper.setSubject("Order confirmed");
        helper.setText(
            "Order " + order.getCode() + " has been confirmed.",
            "<h1>Order confirmed</h1>"
                + "<p>Order code: " + order.getCode() + "</p>"
        );

        mailSender.send(message);
    }
}
~~~

This code works, but a single class is doing too many things:

- Loading the order and executing confirmation rules.
- Deciding when a notification needs to be sent.
- Creating the email subject and body.
- Building the MIME message.
- Choosing multipart and charset.
- Depending on Spring Mail and Jakarta Mail.
- Calling SMTP transport and handling transport errors.

If you switch from SMTP to a provider with an HTTP API, OrderService has to change. If you unit test confirmOrder, the test has to mock MIME-building APIs or spin up a mail-sending environment. If multiple use cases send email, message-building logic can get duplicated and gradually become inconsistent.

The core issue is that **the business decision sits in the same place as how the sending is performed**.

## 2. Defining the responsibilities of each layer

You can split the mail-sending flow into the following responsibilities:

| Component | Responsibility | Should it depend on Spring Mail? |
| --- | --- | --- |
| Controller | Receives HTTP requests, validates input, and calls the use case | Not needed |
| Use case / application service | Executes the business workflow and decides when to notify | No |
| Domain | Business rules and state | No |
| Application port | Defines the contract the use case needs to send content | No |
| Content renderer | Produces subject, plain text, and HTML from business data | Can live in a separate adapter |
| SMTP adapter | Converts the application contract into a MIME message and sends via SMTP | Yes |
| JavaMailSender | Performs sending through Spring Mail configuration | Yes |
| SMTP provider | Receives the message and processes it per provider policy | Outside the application |

The use case can say: "This order has been confirmed; confirmation content needs to be sent to the customer's email address."

The adapter is responsible for: "Create a UTF-8 MIME message, set the recipient, subject, and text/HTML parts, then send it via the configured SMTP server."

The use case does not need to know which SMTP relay delivers the email, which port is used, how TLS is configured, or which library builds the MIME message.

## 3. Architectural flow through port and adapter

In Ports and Adapters (Hexagonal Architecture), the use case calls an outbound interface (outbound port). An adapter in the infrastructure layer implements that interface.

~~~text
                 HTTP / UI
                    |
                    v
              Controller
                    |
                    v
             Application Use Case
                    |
          +---------+----------+
          |                    |
          v                    v
   OrderRepository       MailContentRenderer
       (port)                  (port)
          |                    |
          v                    v
   Database Adapter       Template Adapter
                               |
                               v
                         Rendered Mail
                               |
                               v
                         MailDeliveryPort
                               |
                               v
                      SmtpMailDeliveryAdapter
                               |
                               v
                         JavaMailSender
                               |
                               v
                         SMTP Provider
~~~

Principles:

1. The interface that the use case needs is defined in the application layer.
2. The use case depends on the interface, not on the SMTP implementation.
3. The adapter depends on the application contract and the transport library.
4. Source-code dependencies point inward: infrastructure can know about application, while application does not know about infrastructure.
5. Swapping the adapter does not change business rules as long as the contract stays the same.

MailDeliveryPort is an example name. You can use other names such as OutboundMailPort, EmailGateway, or NotificationDeliveryPort depending on project conventions. What matters is that the interface describes what the application needs rather than copying the transport library's API verbatim.

## 4. Designing the application port

A simple port can accept a Spring-independent DTO:

~~~java
package com.example.application.port.out;

public interface MailDeliveryPort {
    void send(OutgoingMail mail);
}
~~~

DTO:

~~~java
package com.example.application.model;

public record OutgoingMail(
    String recipient,
    String subject,
    String plainText,
    String html
) {}
~~~

OutgoingMail holds the data the application needs to hand off a message. It does not contain MimeMessage, MimeMessageHelper, JavaMailSender, Session, or any Jakarta Mail types.

You can place the contract and DTO in the application package:

~~~text
com.example
├── domain/
│   └── order/
├── application/
│   ├── usecase/
│   │   └── ConfirmOrderUseCase.java
│   ├── port/
│   │   └── out/
│   │       ├── MailDeliveryPort.java
│   │       ├── OrderRepository.java
│   │       └── OrderConfirmationRenderer.java
│   └── model/
│       └── OutgoingMail.java
└── infrastructure/
    └── mail/
        ├── SmtpMailDeliveryAdapter.java
        └── ThymeleafOrderConfirmationRenderer.java
~~~

For a small application, you do not have to create multiple Maven/Gradle modules. You can start with clear package boundaries inside a single module. When the project grows, you can split application, domain, and infrastructure into separate modules so the compiler helps enforce the dependency direction.

### Include in the contract only what the use case needs

If the application only sends simple emails, recipient, subject, plain text, and HTML may be enough. When real requirements arise, the contract can be extended:

- From or reply-to if the business logic allows selecting them.
- Cc/Bcc if the use case needs them.
- A list of attachments with filename, media type, and data source.
- Locale or template identifier.
- Correlation ID for tracing.
- Idempotency key when the system has duplicate-send protection.

Avoid putting every SMTP/Jakarta Mail feature into the port just in case. An overly broad contract keeps the use case coupled to transport details even though the dependency is wrapped in an interface.

### Do not let framework types leak through the port

Avoid contracts like:

~~~java
public interface MailDeliveryPort {
    void send(MimeMessage message);
}
~~~

or:

~~~java
public interface MailDeliveryPort {
    void send(JavaMailSender sender, MimeMessageHelper helper);
}
~~~

These types force the application to know about Jakarta Mail or Spring Mail. The adapter is no longer the sole place responsible for transport conversion.

Similarly, avoid having the use case accept Spring MVC's MultipartFile as an attachment model. Convert the HTTP input into an application command or an appropriate file reference before calling the use case.

## 5. Separating content rendering from transport

An email usually has two stages:

1. Producing content from business data: subject, plain text, HTML, language, template.
2. Turning that content into a message and sending it: MIME parts, headers, attachments, SMTP.

The two stages can be separated using a renderer port and a delivery port.

Renderer contract:

~~~java
package com.example.application.port.out;

public interface OrderConfirmationRenderer {
    OutgoingMail render(OrderConfirmationData data);
}
~~~

Input DTO for the renderer:

~~~java
package com.example.application.model;

import java.math.BigDecimal;

public record OrderConfirmationData(
    String recipient,
    String customerName,
    String orderCode,
    BigDecimal totalAmount
) {}
~~~

The use case does not need to know whether the content is built with Thymeleaf, FreeMarker, or another template engine. It simply asks the renderer to produce the message from the order data.

For a small project, the renderer can be an internal application service instead of a separate port. Only extract it into a port when rendering truly needs to be swappable, depends on a template engine, or needs to be tested independently.

## 6. Building the order confirmation use case

Example use case executing the business steps:

~~~java
package com.example.application.usecase;

import com.example.application.model.OrderConfirmationData;
import com.example.application.model.OutgoingMail;
import com.example.application.port.out.MailDeliveryPort;
import com.example.application.port.out.OrderConfirmationRenderer;
import com.example.application.port.out.OrderRepository;
import com.example.domain.order.Order;

public class ConfirmOrderUseCase {

    private final OrderRepository orderRepository;
    private final OrderConfirmationRenderer renderer;
    private final MailDeliveryPort mailDelivery;

    public ConfirmOrderUseCase(
            OrderRepository orderRepository,
            OrderConfirmationRenderer renderer,
            MailDeliveryPort mailDelivery) {
        this.orderRepository = orderRepository;
        this.renderer = renderer;
        this.mailDelivery = mailDelivery;
    }

    public void execute(Long orderId) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow(() ->
                new OrderNotFoundException(orderId));

        order.confirm();
        orderRepository.save(order);

        OrderConfirmationData data =
            new OrderConfirmationData(
                order.getCustomerEmail(),
                order.getCustomerName(),
                order.getCode(),
                order.getTotalAmount()
            );

        OutgoingMail mail = renderer.render(data);
        mailDelivery.send(mail);
    }
}
~~~

The use case focuses on the workflow: find the order, confirm it, save its state, build the notification data, render the content, and request delivery.

It does not import any class from org.springframework.mail or jakarta.mail.

### Notes on transactions and sending timing

The example above illustrates responsibility separation and is not the optimal implementation for every system. If orderRepository.save(order) runs inside a transaction and the SMTP send happens right after, several situations can occur:

- SMTP accepts the email, but the database transaction rolls back.
- The transaction commits successfully, but SMTP fails or times out.
- The request is retried and produces duplicate emails.

For non-critical notifications or simple applications, synchronous sending may be acceptable. For transactional notifications that require high reliability, consider the outbox pattern or a managed asynchronous sending mechanism.

## 7. Implementing the content renderer with Thymeleaf

The renderer adapter receives the business DTO, renders the template, and returns the neutral contract.

~~~java
package com.example.infrastructure.mail;

import java.util.Locale;

import com.example.application.model.OrderConfirmationData;
import com.example.application.model.OutgoingMail;
import com.example.application.port.out.OrderConfirmationRenderer;

import org.springframework.stereotype.Component;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Component
public class ThymeleafOrderConfirmationRenderer
        implements OrderConfirmationRenderer {

    private final TemplateEngine templateEngine;

    public ThymeleafOrderConfirmationRenderer(
            TemplateEngine templateEngine) {
        this.templateEngine = templateEngine;
    }

    @Override
    public OutgoingMail render(OrderConfirmationData data) {
        Context context = new Context(Locale.forLanguageTag("vi-VN"));
        context.setVariable("customerName", data.customerName());
        context.setVariable("orderCode", data.orderCode());
        context.setVariable("totalAmount", data.totalAmount());

        String html = templateEngine.process(
            "mail/order-confirmation",
            context
        );

        String plainText = """
            Hello %s,

            Your order %s has been confirmed.
            Total amount: %s
            """.formatted(
                data.customerName(),
                data.orderCode(),
                data.totalAmount()
            );

        return new OutgoingMail(
            data.recipient(),
            "Order confirmation " + data.orderCode(),
            plainText,
            html
        );
    }
}
~~~

The HTML template can live in src/main/resources/templates/mail/order-confirmation.html:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<body>
  <h1>Order confirmed</h1>
  <p>Hello <strong th:text="${customerName}">Customer</strong>,</p>
  <p>Order code: <span th:text="${orderCode}">ORD-001</span></p>
  <p>Total amount: <span th:text="${totalAmount}">0</span></p>
</body>
</html>
~~~

th:text escapes text content so dynamic data is not interpreted as markup. If the template builds dynamic URLs, you need to validate allowed schemes and hosts; HTML escaping by itself does not validate that a URL is safe.

The renderer can be replaced with FreeMarker or another template engine without modifying the use case. If the email body is only a few lines and does not need a template, you can build the content directly in an application service.

## 8. Implementing the SMTP adapter with JavaMailSender

The SMTP adapter is the only place in this flow that needs to know about Spring Mail and Jakarta Mail.

~~~java
package com.example.infrastructure.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import com.example.application.model.OutgoingMail;
import com.example.application.port.out.MailDeliveryPort;
import com.example.application.exception.MailDeliveryException;

import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

@Component
public class SmtpMailDeliveryAdapter implements MailDeliveryPort {

    private final JavaMailSender mailSender;

    public SmtpMailDeliveryAdapter(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Override
    public void send(OutgoingMail mail) {
        try {
            MimeMessage message = mailSender.createMimeMessage();

            MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

            helper.setTo(mail.recipient());
            helper.setSubject(mail.subject());
            helper.setText(mail.plainText(), mail.html());

            mailSender.send(message);
        } catch (MessagingException | MailException exception) {
            throw new MailDeliveryException(
                "Could not submit email to the configured transport",
                exception
            );
        }
    }
}
~~~

Application exception:

~~~java
package com.example.application.exception;

public class MailDeliveryException extends RuntimeException {

    public MailDeliveryException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

The adapter performs the mapping:

| Application contract | MIME/Spring Mail |
| --- | --- |
| recipient | helper.setTo(...) |
| subject | helper.setSubject(...) |
| plainText and html | helper.setText(plainText, html) |
| MailDeliveryPort.send | JavaMailSender.send(message) |

The constructor MimeMessageHelper(message, true, "UTF-8") enables multipart and specifies the encoding. The overload setText(plainText, html) creates alternative parts so the email client can choose the appropriate version.

### Why does the adapter translate exceptions?

MessagingException and MailException belong to the infrastructure library. If they escape through the use case, the application once again knows about mail-sending library details.

The adapter translates errors into the application's MailDeliveryException. Callers of the use case can handle errors against a stable contract, while the adapter preserves the original exception as the cause for logging or diagnostics.

Do not catch all exceptions and ignore them. If SMTP submission fails while the use case still reports success, the system loses the ability to detect unsent notifications.

### Do not confuse accepted with delivered

When JavaMailSender.send(...) returns normally, it usually means submission to the transport/server has completed according to the library's contract. It does not prove that the email reached the Inbox, was read by the recipient, or will not bounce afterward.

If the business needs to track delivery status, integrate provider events/webhooks or a delivery status API and store that status separately. Do not name the port's result Delivered if the adapter only knows that SMTP submission succeeded.

## 9. SMTP configuration belongs only in infrastructure

Host, port, credentials, and TLS details belong to transport configuration:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: MAIL_USERNAME
    password: MAIL_PASSWORD
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
~~~

Credential values should be provided through a secret manager or environment variables; do not commit passwords to source control.

The use case does not need to read spring.mail.host, know port 587, or enable STARTTLS itself. Those details are configured for the adapter via Spring Boot auto-configuration.

If you change providers, you can create a new adapter:

~~~text
MailDeliveryPort
      |
      +--> SmtpMailDeliveryAdapter
      |
      +--> ProviderApiMailDeliveryAdapter
      |
      +--> LocalCaptureMailAdapter (test/dev)
~~~

Only one implementation should be registered for a given profile/qualifier at runtime. Avoid letting multiple adapters get component-scanned and injected into the same port without a clear selection rule.

## 10. Dependency registration and wiring

Spring can inject implementations via constructor:

~~~java
@Configuration
public class MailConfiguration {

    @Bean
    public ConfirmOrderUseCase confirmOrderUseCase(
            OrderRepository orderRepository,
            OrderConfirmationRenderer renderer,
            MailDeliveryPort mailDeliveryPort) {
        return new ConfirmOrderUseCase(
            orderRepository,
            renderer,
            mailDeliveryPort
        );
    }
}
~~~

If the use case is already annotated with @Service and its dependencies are registered as beans, manual @Bean declarations are unnecessary. Choose one wiring approach consistent with the project.

For example:

- OrderRepository has a database implementation.
- OrderConfirmationRenderer is implemented by ThymeleafOrderConfirmationRenderer.
- MailDeliveryPort is implemented by SmtpMailDeliveryAdapter.
- ConfirmOrderUseCase receives only the abstractions it needs.

Runtime dependency graph:

~~~text
ConfirmOrderUseCase
   |
   +--> OrderRepository
   |       |
   |       +--> JpaOrderRepositoryAdapter
   |
   +--> OrderConfirmationRenderer
   |       |
   |       +--> ThymeleafOrderConfirmationRenderer
   |
   +--> MailDeliveryPort
           |
           +--> SmtpMailDeliveryAdapter
                    |
                    +--> JavaMailSender
~~~

The application does not need to know which implementation the Spring container selected. Spring is simply the mechanism for wiring adapters into ports.

## 11. Testing the use case without an SMTP server

A major benefit of a port is the ability to replace the SMTP adapter with a fake in unit tests.

~~~java
class FakeMailDeliveryPort implements MailDeliveryPort {

    private final List<OutgoingMail> sent = new ArrayList<>();

    @Override
    public void send(OutgoingMail mail) {
        sent.add(mail);
    }

    public List<OutgoingMail> sentMessages() {
        return List.copyOf(sent);
    }
}
~~~

Use case test:

~~~java
@Test
void confirmingOrderRequestsConfirmationEmail() {
    FakeMailDeliveryPort mailDelivery = new FakeMailDeliveryPort();

    OrderConfirmationRenderer renderer = data ->
        new OutgoingMail(
            data.recipient(),
            "Order confirmation " + data.orderCode(),
            "Order has been confirmed.",
            "<h1>Order confirmed</h1>"
        );

    OrderRepository repository = new InMemoryOrderRepository(
        Order.pending("ORD-100", "customer@example.com")
    );

    ConfirmOrderUseCase useCase =
        new ConfirmOrderUseCase(repository, renderer, mailDelivery);

    useCase.execute(1L);

    assertEquals(1, mailDelivery.sentMessages().size());
    assertEquals(
        "customer@example.com",
        mailDelivery.sentMessages().get(0).recipient()
    );
}
~~~

This test verifies that the use case requests a notification after the confirmation workflow. It does not test SMTP, TLS, MIME encoding, or email clients. Those checks belong to adapter/integration tests.

### Testing mail-sending failures

You can create a fake that throws an exception:

~~~java
MailDeliveryPort failingPort = mail -> {
    throw new MailDeliveryException(
        "Simulated mail transport failure",
        new RuntimeException("Connection refused")
    );
};
~~~

Then verify that the use case or application boundary handles the error as required. For a synchronous use case, the error can propagate to the controller to return an appropriate response. For an outbox/worker, the error is usually recorded and handled according to a retry policy.

## 12. Testing the SMTP adapter separately

The SMTP adapter is responsible for converting the DTO into MIME. You can test it independently by mocking JavaMailSender and checking that the constructed message is right, or by using an SMTP test server such as GreenMail/MailHog in integration tests.

Things to check in the adapter:

- Recipient and subject are assigned correctly.
- UTF-8 charset handles Vietnamese.
- Plain text and HTML are built as multipart/alternative.
- Attachments/inline resources are packaged properly when the contract supports them.
- Errors from JavaMail/Spring Mail are translated into application exceptions.
- TLS/auth configuration is verified in an integration environment.

Unit tests for the use case should not assert MIME boundaries or calls to MimeMessageHelper. Conversely, adapter tests do not need to verify business rules such as whether an order is allowed to be confirmed.

### Local capture adapter

In a development environment, you can swap the SMTP adapter for an adapter that only writes emails to logs/a test mailbox or a capture directory. This lets developers inspect the content without sending mail externally.

A local adapter must be explicitly selected by profile. Never allow local capture to be accidentally used in production, and do not load production SMTP credentials into test environments unnecessarily.

## 13. When to use a semantic notification port?

Not every application needs a generic MailDeliveryPort interface. If the business logic only cares about a specific event, you can define a port in business terms:

~~~java
public interface OrderConfirmationNotifier {
    void notifyOrderConfirmed(OrderConfirmationData data);
}
~~~

Use case:

~~~java
public class ConfirmOrderUseCase {

    private final OrderRepository orders;
    private final OrderConfirmationNotifier notifier;

    public void execute(Long orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow();

        order.confirm();
        orders.save(order);

        notifier.notifyOrderConfirmed(
            new OrderConfirmationData(
                order.getCustomerEmail(),
                order.getCustomerName(),
                order.getCode(),
                order.getTotalAmount()
            )
        );
    }
}
~~~

An email adapter can implement this port by rendering a template and sending via SMTP. Another adapter could send a push notification or call an external notification service.

Comparing the two options:

| Port | What does the use case know? | Suitable when |
| --- | --- | --- |
| MailDeliveryPort | An email message has been created and needs to be sent | The application genuinely needs to control email content or multiple use cases share a delivery contract |
| OrderConfirmationNotifier | An order-confirmed notification needs to be emitted | The business only cares about the event/notification; channel and content are implementation details |

A semantic port keeps the application untied to the email concept if the channel might change. A generic mail port is useful when email is an explicit capability in the application and the content is already standardized.

There is no need to create both layers of abstraction for every use case. Choose the smallest contract that accurately expresses the application's needs.

## 14. Separating synchronous and asynchronous execution

Calling SMTP directly inside the use case is synchronous sending:

~~~text
HTTP request
    |
    v
Use case
    |
    v
JavaMailSender.send()
    |
    v
SMTP response
    |
    v
HTTP response
~~~

Advantages:

- Simple flow.
- Submission errors can be returned immediately.
- Easy to implement for small applications.

Drawbacks:

- The request has to wait for the network and SMTP server.
- Slow SMTP can increase response time.
- Retries can cause duplicate requests.
- SMTP errors can hurt the user experience of the business operation.
- The database transaction and SMTP are not a single atomic transaction.

For important notifications, it is usually better to separate recording the send request from actually transferring the message.

~~~text
HTTP request
    |
    v
Use case
    |
    +--> Update order
    |
    +--> Save notification/outbox record
    |
    v
Database commit
    |
    v
Background worker
    |
    v
MailDeliveryPort
    |
    v
SMTP adapter / provider
~~~

The use case writes an outbox record in the same transaction as the business change. A worker reads the record after commit, renders the content, and sends via the port. When SMTP temporarily fails, the worker can retry without requiring the user to resubmit the order confirmation request.

## 15. Outbox pattern to avoid lost notifications

If the application simply commits the order and then publishes a message to a queue in a separate operation, the following can happen:

- The database commit succeeds, but publishing to the queue fails.
- Publishing to the queue succeeds, but the database rolls back.
- The worker receives the notification before the business data commits.

The outbox pattern closes this gap by storing the event to process in the same database transaction as the business change.

Example table:

~~~sql
CREATE TABLE mail_outbox (
    id              BIGINT PRIMARY KEY,
    event_type      VARCHAR(120) NOT NULL,
    aggregate_id    VARCHAR(120) NOT NULL,
    payload         TEXT NOT NULL,
    status          VARCHAR(30) NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP NULL,
    created_at      TIMESTAMP NOT NULL,
    sent_at         TIMESTAMP NULL
);
~~~

Inside the order confirmation transaction:

1. Update the order status.
2. Insert an outbox record of type OrderConfirmed.
3. Commit both together.

The worker fetches unprocessed records, builds the notification data, calls MailDeliveryPort, and updates the status. If sending succeeds, mark it complete. If a transient error occurs, increment attempts and schedule a retry.

The outbox guarantees the send request is not lost between database commit and enqueue. It **does not by itself guarantee the email is sent exactly once**. SMTP may accept the message while the worker loses connectivity before recording success; the next retry can produce a duplicate email. Idempotency, a delivery key, or provider reconciliation is needed if the business requires it.

## 16. Designing retries and classifying errors

Not every error should be retried the same way.

| Error category | Examples | Common handling |
| --- | --- | --- |
| Transient | Connection timeout, SMTP server unavailable, temporary rate limit | Retry with exponential backoff and jitter |
| Configuration | Wrong credentials, misconfigured TLS, invalid host | Stop aggressive retries, alert operations |
| Content | Malformed recipient, attachment too large, template error | Mark as error needing data/content fix |
| Provider policy | Blocked sender, disallowed file type | Do not retry the same message; handle policy |
| Unknown outcome | Timeout after SMTP DATA may already have been received | Reconcile delivery/provider events or apply idempotency |

The adapter can map certain Spring/Jakarta errors into typed application exceptions. However, avoid relying on free-form error message strings to decide retries. Base decisions on exception types, SMTP response codes, or provider API codes when reliable information is available.

The retry policy should live in the worker/application orchestration, not inside a retry loop inside SmtpMailDeliveryAdapter. The adapter is responsible for a single send attempt; the worker decides when the next attempt happens.

## 17. Managing delivery status and idempotency

A notification record can have the following states:

~~~text
PENDING
   |
   v
PROCESSING
   |
   +---- success ----> SUBMITTED
   |
   +---- transient --> RETRY_WAIT
   |
   +---- permanent --> FAILED
~~~

State names must reflect what the system actually knows. If the SMTP adapter only confirms submission, the state should be SUBMITTED or ACCEPTED_BY_TRANSPORT, not DELIVERED.

To reduce duplicate sends:

- Assign a stable notification ID.
- Use a unique constraint for events that must be sent once per business rule.
- Have workers claim records with an appropriate lock/lease mechanism.
- Store attempt ID and timestamp.
- If the provider supports an idempotency key, pass the key through the provider adapter.
- If the provider emits delivery events, correlate using the provider message ID.

Traditional SMTP does not provide universal idempotency semantics across all servers. You cannot claim exactly-once delivery merely by adding a status column in the database.

## 18. Managing attachments without exposing Spring details

If the use case needs attachments, the contract should describe the data the application needs. Do not put MultipartFile or Resource into the application model.

One option is a file reference:

~~~java
public record MailAttachment(
    String fileId,
    String fileName,
    String contentType
) {}
~~~

The application only passes the file ID and metadata. The adapter or another storage port is responsible for fetching the content from storage.

If the use case genuinely needs to supply bytes, you can define an internal abstraction:

~~~java
public interface AttachmentContent {
    InputStream openStream() throws IOException;
    long size();
}
~~~

This is an application-defined contract; do not use InputStreamResource or FileSystemResource in the application layer.

For large files, prefer a storage reference and a reopenable stream rather than holding all bytes in the DTO. Ensure the file lifecycle lasts long enough for the worker to finish sending, and check access permissions before attaching.

## 19. Keeping transport details out of the domain model

Do not add fields such as SMTP host, SMTP port, SMTP username/password, Jakarta MimeMessage, MIME boundary, SMTP response code, or TLS mode to the Order entity or business value objects just because email needs them.

The domain can hold the customer's email address if that is business data. However, creating the MIME message, choosing encoding, configuring transport, and handling SMTP replies belong to the adapter/infrastructure.

Example domain method:

~~~java
public void confirm() {
    if (status != OrderStatus.PENDING) {
        throw new IllegalStateException(
            "Only pending orders can be confirmed");
    }

    this.status = OrderStatus.CONFIRMED;
}
~~~

The domain does not need to call the mail sender. The use case observes the business outcome and requests notification through the port.

## 20. Common anti-patterns

| Anti-pattern | Consequence | Appropriate approach |
| --- | --- | --- |
| Controller calls JavaMailSender directly | HTTP layer knows transport details | Controller only calls the use case |
| Domain entity sends email itself | Domain depends on framework and side effects | Use case or domain event triggers the port |
| Use case accepts MimeMessage | Jakarta Mail leaks into application | Use DTOs/ports defined by application |
| Each service builds MIME differently | Content and configuration become inconsistent | Use shared renderer and adapter |
| Port copies the entire SMTP API | Application still depends on transport concepts | Keep the contract small based on needs |
| Adapter contains business rules | Changing providers may alter business behavior | Keep policy in use case/domain |
| Catching send errors, logging, and ignoring | Use case reports success even though notification failed | Throw an exception or record retry state |
| Infinite retries inside the adapter | Hard to control timing and causes duplicates | Retry in worker with an explicit policy |
| Calling SMTP inside a long transaction | Holds database connections/locks while waiting on network | Use outbox and worker when reliability is needed |
| Calling SMTP accepted status delivered | Misreports actual delivery | Separate submission status from delivery events |

## 21. When do you not need too many layers?

Not every application needs an architecture with many packages and interfaces. For a very small internal utility, a service using JavaMailSender directly may be enough if there is no need to swap providers or test business logic independently.

Separate ports/adapters when:

- Multiple use cases send email.
- Business rules need to be tested without depending on SMTP.
- There are multiple environments or providers.
- A local capture adapter is needed.
- Sending email is an important side effect of a transaction.
- There is a need to move to a queue, provider API, or another notification channel.
- The team wants to keep the application module free of Spring infrastructure dependencies.

Avoid creating an interface per method just to increase abstraction count. A port is valuable when it establishes a stable, meaningful boundary with replaceable implementations.

## 22. Step-by-step implementation process

You can refactor an existing service in the following order:

1. **Identify the use case**: which business operation needs to emit a notification and under what conditions?
2. **Define the contract**: create the DTO and interface in the application layer containing only the data the use case needs.
3. **Separate content**: extract template rendering into a separate renderer/service if needed.
4. **Create the SMTP adapter**: move MimeMessageHelper, MimeMessage, and JavaMailSender into infrastructure.
5. **Map exceptions**: translate library errors into meaningful application exceptions.
6. **Wire with Spring**: inject the adapter into the port via constructor.
7. **Write use case unit tests**: use a fake port to verify send requests and business rules.
8. **Write adapter tests**: verify MIME, encoding, and SMTP behavior using mocks or a test server.
9. **Choose sync/async model**: decide based on response time, reliability, and retry requirements.
10. **Add an outbox if needed**: save send requests in the same transaction and process them with a worker.

When complete, the dependency flow should look like this:

~~~text
Application:
  ConfirmOrderUseCase
       |
       +--> OrderRepository (port)
       +--> OrderConfirmationRenderer (port)
       +--> MailDeliveryPort (port)

Infrastructure:
  JpaOrderRepositoryAdapter
  ThymeleafOrderConfirmationRenderer
  SmtpMailDeliveryAdapter
       |
       +--> JavaMailSender
       +--> MimeMessageHelper
       +--> SMTP provider
~~~

## 23. Key takeaways

Decoupling mail sending use cases from the transport layer means keeping **business decisions** in application and leaving **MIME/SMTP details** in infrastructure:

- The use case decides when a notification needs to be sent and what data is involved.
- The application port describes the delivery contract the use case needs.
- Application DTOs do not depend on MimeMessage, MimeMessageHelper, or JavaMailSender.
- The renderer is responsible for producing subject, plain text, and HTML from business data.
- The SMTP adapter converts the contract into a MIME message and calls JavaMailSender.
- The adapter translates Spring/Jakarta errors into meaningful application errors.
- Host, port, credentials, and TLS configuration reside in infrastructure/configuration.
- Use case unit tests use a fake port without needing an SMTP server.
- Adapter integration tests verify MIME and transport separately.
- Synchronous sending suits simple flows; outbox/worker suits cases needing reliability, retries, and decoupled processing time.
- SMTP accepted does not mean the email reached the Inbox or was read.
- Choose a generic or semantic port based on actual needs; do not create unnecessary abstractions.

When the use case depends only on a stable contract, the application can swap SMTP adapters, change template engines, or use a provider API without rewriting order confirmation rules. That is the practical benefit of decoupling mail sending use cases from the transport layer in Spring Framework Mail.
