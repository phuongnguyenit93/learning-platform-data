# Using Commands or DTOs for Email Data

When a Spring application needs to send an order confirmation email, schedule reminder, or payment notification, the mail-sending service must receive the required data: recipient, transaction code, status, content, and possibly attachments. Passing discrete parameters through multiple layers produces long method signatures that are hard to extend and easy to misorder. Passing an entire entity or a large request object couples the email service to unnecessary data.

A clean way to organize this is to use **commands or DTOs (Data Transfer Objects)** to encapsulate data according to the purpose of each boundary in the application. A command represents **the intent to perform an action**, whereas a DTO represents **data transferred between layers or components**. The two concepts can use the same Java construct, yet they differ in meaning and responsibility.

In the context of **Spring Framework Mail**, a command typically describes a business request such as `SendOrderConfirmationCommand` or `SendPasswordResetCommand`. A DTO may hold presentation data for a template such as recipient name, order code, due date, and URL. An application service handles the command, retrieves authoritative data, builds the email model, renders the content, and hands it off to `JavaMailSender` to send over SMTP.

This article explains how to distinguish commands from DTOs, choose what data to pass, design immutable records/classes, validate inputs, organize mail-sending layers, and avoid common pitfalls when using commands/DTOs with Spring Mail.

## 1. Why not pass many separate parameters?

An initial notification method may look very simple:

~~~java
public void sendOrderConfirmation(
        String recipient,
        String customerName,
        String orderCode,
        String status,
        BigDecimal total,
        LocalDate deliveryDate) {
    // Build and send the email.
}
~~~

Once the email adds a locale, URL, support address, and note, the signature keeps growing:

~~~java
public void sendOrderConfirmation(
        String recipient,
        String customerName,
        String orderCode,
        String status,
        BigDecimal total,
        LocalDate deliveryDate,
        Locale locale,
        String detailsUrl,
        String supportEmail,
        String note) {
    // ...
}
~~~

Common issues appear:

- Callers must remember the order of many `String` parameters.
- Adding a new field requires updating the signature and every call site.
- It is not obvious which fields are required and which are optional.
- Some data belongs to different responsibilities: request data, business data, presentation data, and SMTP details.
- Unit tests have to pass many arguments even when testing only one part.

Related values can be grouped into an object:

~~~java
public record OrderMailData(
        String recipient,
        String customerName,
        String orderCode,
        String status,
        BigDecimal total,
        LocalDate deliveryDate) {
}
~~~

The service accepts one clearly named and structured parameter:

~~~java
public void sendOrderConfirmation(OrderMailData data) {
    // Use the packaged data.
}
~~~

This object reduces parameter count, but good design also needs to answer: **is this a command, a request DTO, or a view DTO?** Clear naming and scoped responsibilities help readers understand who creates the data, who is allowed to modify it, and at which step it is used.

## 2. How do commands and DTOs differ?

A **Command** represents a request to perform an action. Its name usually starts with a verb or describes a specific intent, for example:

- `SendOrderConfirmationCommand` — request to send an order confirmation email.
- `SendPasswordResetCommand` — request to send a password reset email.
- `SendInvoiceCommand` — request to send an invoice.
- `NotifyPaymentFailedCommand` — request to notify about a failed payment.

A **DTO** is an object carrying data across a boundary. It does not necessarily request an action. For example:

- `OrderConfirmationRequest` — HTTP request data sent from a client.
- `OrderMailView` — data needed to render a template.
- `RenderedEmail` — generated subject and body representations.
- `AttachmentDescriptor` — metadata referencing an allowed attachment file.

| Aspect | Command | DTO |
| --- | --- | --- |
| Meaning | Request to perform an action | Carries data across a boundary |
| Question answered | "What should the application do?" | "What data does this component need?" |
| Common name | `SendOrderConfirmationCommand` | `OrderMailView` |
| Can it hold data? | Yes, the data needed to perform the action | Yes, that is its primary purpose |
| Does it execute the action itself? | No; a handler/service processes the command | No |
| Should it hold SMTP sending logic? | No | No |
| Usage example | Input to an application service | Input to a renderer/template |

A command can be implemented as a Java record and is also a DTO in the broad sense of a data-transferring object. The difference lies in its **design role**, not in a Java keyword or whether the object has methods.

Do not turn this distinction into a rigid rule requiring two separate classes for every object. For a small use case, a command-named record may suffice. In multi-layered systems, separating commands from view DTOs helps keep boundaries clear.

## 3. Email data flow in a Spring application

A flow can be divided into steps:

~~~mermaid
flowchart TD
    A["HTTP / Scheduler / Event"] --> B["Request DTO or Event DTO"]
    B --> C["Application Service"]
    C --> D["Command / Use case"]
    D --> E["Read and validate business data"]
    E --> F["Mail View DTO"]
    F --> G["Template Renderer"]
    G --> H["RenderedEmail"]
    H --> I["Spring Mail Gateway"]
    I --> J["JavaMailSender"]
    J --> K["SMTP relay"]
~~~

Each component has its own responsibility:

1. **Request DTO or event** brings external data in.
2. **Application service/command handler** orchestrates the use case and enforces business rules.
3. **Mail view DTO** holds only the data needed for display.
4. **Renderer** generates the subject, plain text, and HTML.
5. **Mail gateway** turns the prepared content into a `MimeMessage` and calls `JavaMailSender`.
6. **SMTP relay** accepts the message per connection configuration.

Not every application needs all six classes. For a small service, the renderer and gateway can be combined. However, understanding the boundaries keeps business logic from depending directly on MIME or SMTP details as the system grows.

## 4. Designing commands around business actions

A good command expresses **intent**, not just a generic list of email fields.

For example:

~~~java
public record SendOrderConfirmationCommand(
        UUID orderId,
        String recipient) {
}
~~~

This command states that the application needs to send a confirmation for an order. It does not force callers to supply the total amount, status, customer name, and URL themselves.

The application service can use `orderId` to load authoritative data from the repository, verify that the recipient is allowed to receive the notification, and construct the view model. This avoids trusting critical values supplied by the client.

Another command:

~~~java
public record SendPasswordResetCommand(
        UUID userId,
        String resetRequestId) {
}
~~~

The command identifies the password reset request. The service can check token status, expiration, and recipient from the authentication system. Never let a client pass an arbitrary email address and send an account's token to that address.

### Commands should represent a use case

A command like:

~~~java
public record SendEmailCommand(
        String recipient,
        String subject,
        String html,
        String plainText) {
}
~~~

can be useful in a **generic mail-sending infrastructure**. However, if used as the public API for every business feature, callers have to decide content, recipients, templates, and potentially sensitive data themselves. At that point, the application service loses control over the semantics of each email type.

For important business workflows, specific commands are clearer: `SendInvoiceCommand`, `SendWelcomeEmailCommand`, `SendAppointmentReminderCommand`. A generic gateway can receive `RenderedEmail` at a lower layer after the business layer has determined the content.

## 5. Request DTO, command, and mail view DTO

Three objects may appear in a single flow:

| Object | Who creates it? | What does it contain? | Who uses it? |
| --- | --- | --- | --- |
| Request DTO | Controller/adapter receiving the request | Data the client is allowed to send | Controller and application service |
| Command | Adapter or application layer | Business intent and data needed for the use case | Command handler/application service |
| Mail view DTO | Application service/mapper | Validated, formatted data for the email | Template renderer |

Example request DTO:

~~~java
public record OrderConfirmationRequest(
        @NotBlank
        @Email
        String recipient,
        @Size(max = 120)
        String messageToSeller) {
}
~~~

The request should not let clients decide the order status, amount, or internal template. Those values must be read from the domain/repository.

Command:

~~~java
public record SendOrderConfirmationCommand(
        UUID orderId,
        String recipient,
        String messageToSeller) {
}
~~~

Mail view DTO:

~~~java
public record OrderMailView(
        String customerName,
        String orderCode,
        String statusLabel,
        String formattedTotal,
        String formattedDeliveryDate,
        String detailsUrl,
        String messageToSeller) {
}
~~~

The application service translates the request into a command, then loads business data and builds the view DTO. In a system without an HTTP controller, the command can be created directly by a scheduler, message consumer, or another use case.

### Are all three always required?

No. If the application only has an internal caller, the command can be used as direct input without a separate request DTO. If the renderer only needs two simple values, a view DTO may not need its own class. Split objects when doing so **clarifies a boundary or contract**, not merely to increase file count.

## 6. Designing immutable commands with Java records

A command is usually a snapshot of data at the time of the request. Java records are a good fit when fields can be represented as immutable components:

~~~java
import java.util.UUID;

public record SendOrderConfirmationCommand(
        UUID orderId,
        String recipient) {
}
~~~

A record automatically provides the constructor, accessors, `equals`, `hashCode`, and `toString`. Components are declared final; the object has no generated setters.

If a command holds a collection, remember that a record only makes the component reference final—**it does not automatically make the collection inside immutable**. Make a defensive copy:

~~~java
public record SendBulkNoticeCommand(
        List<String> recipients,
        String noticeCode) {

    public SendBulkNoticeCommand {
        recipients = List.copyOf(recipients);
        if (recipients.isEmpty()) {
            throw new IllegalArgumentException(
                    "Recipient list must not be empty"
            );
        }
    }
}
~~~

`List.copyOf` produces an unmodifiable list referenced by the record and rejects null elements. For nested collections or mutable objects, deeper care is needed.

### When to use a class instead of a record?

Use a class when you need:

- Compatibility with a framework or serializer that requires specific constructors/setters.
- Inheritance or complex object structures where records do not fit.
- Intentional mutable state management.
- Multi-step object construction behavior.

Do not use a mutable command just because a controller wants to populate fields one by one with setters. If a command represents an already-created request, mutating data between steps can cause logs, retries, and execution outcomes to diverge from the original snapshot.

## 7. Validating commands and DTOs

Validation can occur at multiple boundaries, with each check answering a different question.

**Structural validation** checks whether data is present and satisfies basic formatting:

- Is the recipient blank?
- Is the order code formatted properly?
- Does the note exceed the length limit?
- Is the recipient list empty or too large?

**Business validation** checks whether the request is valid in the current state:

- Does the order exist?
- Is the order eligible for a confirmation email?
- Is the recipient associated with the order?
- Has the invoice been issued?
- Is the password reset request still valid?

**Authorization** checks whether the actor has permission to request the action. A syntactically valid email address does not prove the caller is authorized to send data to that address.

Example command with simple validation:

~~~java
public record SendOrderConfirmationCommand(
        @NotNull UUID orderId,
        @NotBlank @Email String recipient) {
}
~~~

If using Bean Validation in an application service, trigger validation via a mechanism aligned with your Spring architecture, or invoke the validator explicitly. Never assume every record is automatically validated just because it carries annotations.

A constructor can also guard basic invariants:

~~~java
public record SendOrderConfirmationCommand(
        UUID orderId,
        String recipient) {

    public SendOrderConfirmationCommand {
        Objects.requireNonNull(orderId, "orderId");

        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                    "recipient must not be blank"
            );
        }
    }
}
~~~

Full email syntax checks should use a proper validator/library; do not write a complex regex yourself and treat it as proof that a mailbox exists.

## 8. Do not trust client data for critical business values

A request might contain:

~~~json
{
  "orderId": "8b3d...",
  "recipient": "buyer@example.net",
  "orderStatus": "PAID",
  "totalAmount": 1000,
  "templateName": "admin-mail"
}
~~~

If clients are allowed to send these fields, the application must determine which fields are actually permitted. `orderStatus` and `totalAmount` must normally come from authoritative business data. `templateName` should be mapped from an allowed notification type rather than accepting arbitrary paths.

A command may only need:

~~~java
public record SendOrderConfirmationCommand(
        UUID orderId,
        String recipient) {
}
~~~

The service then reads status and amount from the repository/domain. This prevents clients from tampering with email content to make an unpaid transaction look paid.

### Recipients also require authorization checks

Accepting a client-supplied recipient is not always appropriate. For account notifications, the recipient may need to be the user's verified email. For invoices, the recipient may need to be the registered billing contact. If the business allows an alternate email address, verify permissions and record the reason per product policy.

## 9. Building a mail view DTO from domain data

An entity often has many fields and relationships unnecessary for an email:

~~~java
class Order {
    // id, customer, payment, lineItems, internalNotes,
    // audit fields, persistence relations...
}
~~~

Do not pass the entire entity into the template just because a few values are needed. Instead, build a presentation DTO:

~~~java
public record OrderMailView(
        String customerName,
        String orderCode,
        String statusLabel,
        String formattedTotal,
        String formattedDeliveryDate,
        String detailsUrl) {
}
~~~

A mapper or application service builds the view:

~~~java
private OrderMailView toMailView(
        Order order,
        Customer customer,
        URI publicBaseUri,
        Locale locale) {

    return new OrderMailView(
            customer.getDisplayName(),
            order.getCode(),
            statusLabelFor(order.getStatus(), locale),
            moneyFormatter.format(order.getTotal(), locale),
            dateFormatter.format(order.getDeliveryDate(), locale),
            buildOrderUrl(publicBaseUri, order.getCode())
    );
}
~~~

Benefits:

- The template sees only the data needed for presentation.
- Internal notes or sensitive fields are not accidentally rendered.
- Unexpected lazy loading during rendering is avoided.
- Date/currency formatting is controlled in one place.
- Renderer unit tests do not need to instantiate JPA entities or a database.

A view DTO should not hold `JavaMailSender`, `MimeMessage`, SMTP passwords, or services. It is **display data**, not mail transport infrastructure.

## 10. Rendering subject, plain text, and HTML from the same view DTO

An email can have three content fields:

~~~java
public record RenderedEmail(
        String subject,
        String plainText,
        String html) {
}
~~~

The renderer accepts the view DTO and produces the result:

~~~java
public interface OrderMailRenderer {
    RenderedEmail render(OrderMailView view, Locale locale);
}
~~~

An implementation can use Thymeleaf:

~~~java
@Component
public class ThymeleafOrderMailRenderer
        implements OrderMailRenderer {

    private final TemplateEngine templateEngine;

    public ThymeleafOrderMailRenderer(
            TemplateEngine templateEngine) {
        this.templateEngine = templateEngine;
    }

    @Override
    public RenderedEmail render(
            OrderMailView view,
            Locale locale) {

        Context context = new Context(locale);
        context.setVariable("mail", view);

        String html = templateEngine.process(
                "mail/order-confirmed",
                context
        );

        String plain = """
                Hello %s,

                Order %s: %s
                Total amount: %s
                Estimated delivery: %s

                View details:
                %s
                """.formatted(
                view.customerName(),
                view.orderCode(),
                view.statusLabel(),
                view.formattedTotal(),
                view.formattedDeliveryDate(),
                view.detailsUrl()
        );

        String subject =
                "Order " + view.orderCode() + " has been confirmed";

        return new RenderedEmail(subject, plain, html);
    }
}
~~~

The HTML template must use escaped output for text data, such as `th:text` in Thymeleaf. URLs in `th:href` must be built from a trusted base URL and validated against policy. The renderer should not query repositories itself to recompute order status.

### Why does using the same view DTO matter?

If plain text re-queries the order after HTML is rendered, the data could change between reads. One representation might say "Processing" while the other says "Delivered". Using a single snapshot/view DTO ensures both representations describe the same state.

## 11. Mail gateway converting RenderedEmail to MimeMessage

The gateway layer handles Spring Mail details:

~~~java
public interface MailGateway {
    void send(OutboundMail mail);
}
~~~

A DTO at the sending boundary:

~~~java
public record OutboundMail(
        String from,
        String recipient,
        String subject,
        String plainText,
        String html) {
}
~~~

Gateway implemented with `JavaMailSender`:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

@Component
public class SpringMailGateway implements MailGateway {

    private final JavaMailSender mailSender;

    public SpringMailGateway(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Override
    public void send(OutboundMail mail) {
        try {
            MimeMessage message = mailSender.createMimeMessage();

            MimeMessageHelper helper =
                    new MimeMessageHelper(message, true, "UTF-8");

            helper.setFrom(mail.from());
            helper.setTo(mail.recipient());
            helper.setSubject(mail.subject());
            helper.setText(mail.plainText(), mail.html());

            mailSender.send(message);
        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Could not create MIME message", ex
            );
        } catch (MailException ex) {
            throw new MailDeliveryException(
                    "SMTP did not accept the send operation", ex
            );
        }
    }
}
~~~

`MailPreparationException` and `MailDeliveryException` in this example are custom application exceptions that need to be defined. You can choose a different handling approach depending on architecture, but you should distinguish message creation errors from mail infrastructure delivery errors. Never catch all exceptions and ignore them, as the application service would not know the operation failed.

A technical note: `MimeMessageHelper` can throw `MessagingException` when creating or modifying a message; `JavaMailSender.send(...)` can throw `MailException`. Specific exceptions and error classification should be based on the API/version in use.

## 12. Complete example: command → application service → DTO → gateway

### 12.1. Command

~~~java
public record SendOrderConfirmationCommand(
        UUID orderId,
        String recipient) {
}
~~~

### 12.2. Application service

~~~java
@Service
public class SendOrderConfirmationHandler {

    private final OrderRepository orderRepository;
    private final CustomerRepository customerRepository;
    private final OrderMailRenderer renderer;
    private final MailGateway mailGateway;
    private final URI publicBaseUri;

    public SendOrderConfirmationHandler(
            OrderRepository orderRepository,
            CustomerRepository customerRepository,
            OrderMailRenderer renderer,
            MailGateway mailGateway,
            @Value("¤{app.public-base-url}") URI publicBaseUri) {

        this.orderRepository = orderRepository;
        this.customerRepository = customerRepository;
        this.renderer = renderer;
        this.mailGateway = mailGateway;
        this.publicBaseUri = publicBaseUri;
    }

    public void handle(SendOrderConfirmationCommand command) {
        Order order = orderRepository.findById(command.orderId())
                .orElseThrow(() -> new OrderNotFoundException(
                        command.orderId()
                ));

        Customer customer = customerRepository
                .findById(order.getCustomerId())
                .orElseThrow(() -> new CustomerNotFoundException(
                        order.getCustomerId()
                ));

        validateRecipient(command.recipient(), customer);
        ensureConfirmationMayBeSent(order);

        Locale locale = customer.getPreferredLocale();

        OrderMailView view = toMailView(
                order,
                customer,
                publicBaseUri,
                locale
        );

        RenderedEmail rendered = renderer.render(view, locale);

        OutboundMail outbound = new OutboundMail(
                "orders@example.org",
                command.recipient(),
                rendered.subject(),
                rendered.plainText(),
                rendered.html()
        );

        mailGateway.send(outbound);
    }

    private void validateRecipient(
            String recipient,
            Customer customer) {
        // Validate syntax and recipient authorization per business rules.
    }

    private void ensureConfirmationMayBeSent(Order order) {
        // Validate order state and sending rules.
    }

    private OrderMailView toMailView(
            Order order,
            Customer customer,
            URI baseUri,
            Locale locale) {
        // Map validated data to the presentation DTO.
        throw new UnsupportedOperationException("Implement mapping");
    }
}
~~~

The repositories, domain classes, and exceptions represent components of a hypothetical application. The `toMailView` method is left as a stub to show where mapping lives; in a real application, implement it with a concrete mapper/service.

### 12.3. Invoking the use case

From a controller, scheduler, or another component:

~~~java
handler.handle(
        new SendOrderConfirmationCommand(
                orderId,
                verifiedRecipient
        )
);
~~~

The caller simply requests a specific action. It does not need to know how to construct MIME, choose a charset, structure multipart, or invoke SMTP.

### Where do responsibilities live?

| Component | Responsibility |
| --- | --- |
| `SendOrderConfirmationCommand` | Represents the intent to send an order confirmation |
| `SendOrderConfirmationHandler` | Orchestrates the use case and runs business checks |
| `OrderMailView` | Carries data needed by the template |
| `OrderMailRenderer` | Generates subject/plain/HTML |
| `OutboundMail` | Carries the rendered message to the gateway |
| `SpringMailGateway` | Creates `MimeMessage` and calls `JavaMailSender` |

For a small application, you can merge `OutboundMail` into `RenderedEmail` or let the renderer return an object matching the gateway directly. Keeping them separate is useful when the renderer and gateway belong to two modules or when sender/recipient controls live at another layer.

## 13. How should attachment data be represented?

If the email includes attachments, avoid putting arbitrary filesystem paths from requests into commands:

~~~java
// Avoid letting clients pass server file paths.
public record SendInvoiceCommand(
        UUID invoiceId,
        String filePath) {
}
~~~

A path could point outside the allowed storage area or cause the application to read unrelated files. Instead, the command can carry a business identifier:

~~~java
public record SendInvoiceCommand(
        UUID invoiceId,
        String recipient) {
}
~~~

The application service fetches the invoice and verified file from storage. An internal DTO for attachments could be:

~~~java
public record MailAttachment(
        String fileName,
        String contentType,
        Resource resource) {
}
~~~

However, passing `Resource` is only appropriate in an internal layer where resource lifecycle and readability are controlled. Never expose this object directly as a JSON request DTO.

For multiple files, copy the list:

~~~java
public record OutboundMail(
        String from,
        String recipient,
        String subject,
        String plainText,
        String html,
        List<MailAttachment> attachments) {

    public OutboundMail {
        attachments = List.copyOf(attachments);
    }
}
~~~

Before attaching, the application must verify file access permissions, size, actual content type, display filename, and malware scanning policy where appropriate. A DTO describing a file does not make the file safe on its own.

## 14. Commands for synchronous and asynchronous sending

In a synchronous flow, the application service calls the gateway and waits for the send result:

~~~text
handle(command)
    -> load data
    -> render
    -> mailGateway.send(...)
    -> return
~~~

This is simple and suits low-volume flows where latency is acceptable and the caller needs to know gateway errors immediately.

In larger systems, a command can create an asynchronous send job:

~~~java
public record QueueOrderConfirmationCommand(
        UUID orderId,
        String recipient,
        String requestId) {
}
~~~

The handler validates the use case, saves a mail job or outbox record, and returns an acceptance result. A worker reads the job, builds the view model, and sends the email.

~~~mermaid
flowchart TD
    A["Application command"] --> B["Business validation"]
    B --> C["Save outbox / mail job"]
    C --> D["Worker picks up job"]
    D --> E["Render email"]
    E --> F["JavaMailSender"]
    F --> G["Update send status"]
~~~

### Do not put MimeMessage into a queue

`MimeMessage` is a stateful infrastructure object coupled to Jakarta Mail. It is not a good payload for a durable queue. Store serializable command/job data instead, such as notification type, resource ID, verified recipient, locale, and allowlisted template code. The worker builds a fresh message when processing.

### Idempotency and retries

If the same command is delivered twice due to message queue redelivery or caller retries, duplicate emails may be sent. For critical notifications, include a request ID or idempotency key and durably persisted job state.

A record might include:

~~~text
request_id: order-confirmation:ORD-2048:v1
purpose: ORDER_CONFIRMATION
order_id: ORD-2048
recipient_id: customer-42
status: PENDING
attempt_count: 0
~~~

This is an illustrative data model. Do not store SMTP credentials or full private content in log payloads. If a job uses data that changes over time, decide explicitly whether to take a snapshot at job creation or fetch the latest state when the worker runs.

## 15. Commands and events are not the same

A **command** asks the application to perform an action: `SendInvoiceCommand`. An **event** describes something that already happened: `InvoiceIssuedEvent`.

| Kind | Example | Meaning |
| --- | --- | --- |
| Command | `SendInvoiceEmailCommand` | Send the invoice email |
| Event | `InvoiceIssuedEvent` | An invoice has been issued |
| DTO | `InvoiceMailView` | Data for presenting the invoice in an email |

An `InvoiceIssuedEvent` can trigger a handler to create a mail-sending command. Or an event handler can build and send the email directly if the architecture is simple. Still, distinguish their semantics:

- Events represent facts that already occurred and should not be renamed as unexecuted requests.
- Commands can fail or be rejected.
- DTOs merely carry data and represent neither events nor actions.

When sending email in response to events, consider that events may be replayed, processed multiple times, or arrive late. Idempotency and duplicate-send policies remain important.

## 16. Should a command contain the complete subject and HTML?

That depends on the layer receiving the command.

For a **business use case**, callers should generally not supply HTML themselves:

~~~java
public record SendPaymentReminderCommand(
        UUID invoiceId,
        String recipient,
        String html) {
}
~~~

If `html` comes from the request, callers can control displayed content, inject unwanted markup, or produce off-brand emails. Moreover, the application service can no longer guarantee the content reflects the invoice state.

Instead:

~~~java
public record SendPaymentReminderCommand(
        UUID invoiceId) {
}
~~~

The handler retrieves the verified recipient, invoice data, and renders an application-managed template.

In **generic mail infrastructure**, an `OutboundMail` object may contain the rendered subject and body. That is a different boundary: content has already been prepared and the gateway is only responsible for sending. Only authorized components should construct this object.

### When is user-customized content allowed?

If the product allows administrators to edit email content, you need a template management workflow: edit permissions, versioning, preview, placeholder validation, HTML sanitization, and approval before publishing. Do not turn a mail-sending endpoint into an arbitrary HTML sender for all users.

## 17. Do not couple commands to Spring Mail

Commands in the application/business layer should avoid importing infrastructure classes such as:

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
~~~

A command like the following exposes mail-sending details:

~~~java
public record SendEmailCommand(MimeMessage message) {
}
~~~

It forces callers to build a MIME message before invoking the use case, inverting responsibilities and making testing harder.

Instead, the command holds simple business data:

~~~java
public record SendWelcomeEmailCommand(UUID userId) {
}
~~~

The application service orchestrates, the renderer creates content, and the gateway uses Spring Mail. If you need to swap the SMTP provider for another email API, the business logic can stay intact.

### Just enough dependency inversion

You can define an interface in the application module:

~~~java
public interface MailGateway {
    void send(OutboundMail mail);
}
~~~

The Spring Mail adapter implements that interface. The application service depends on the abstraction; the adapter depends on `JavaMailSender`. Do not create an interface for every tiny method if the project only has one simple use case. The goal is to isolate **transport details** from business logic.

## 18. Do not pass entities or application contexts into DTOs

Some approaches seem convenient but introduce coupling:

~~~java
public record OrderMailData(
        Order order,
        ApplicationContext applicationContext) {
}
~~~

The template or renderer can then access far more data and services than the email needs. This makes reviewing, testing, and controlling exposed information harder.

A DTO should be an explicit set of fields:

~~~java
public record OrderMailView(
        String customerName,
        String orderCode,
        String statusLabel,
        String formattedTotal,
        String detailsUrl) {
}
~~~

If the template needs a list of items, create a child DTO containing only the formatted name, quantity, and price:

~~~java
public record OrderLineMailView(
        String productName,
        String quantityLabel,
        String formattedLineTotal) {
}
~~~

~~~java
public record OrderMailView(
        String customerName,
        String orderCode,
        List<OrderLineMailView> items,
        String formattedTotal,
        String detailsUrl) {

    public OrderMailView {
        items = List.copyOf(items);
    }
}
~~~

This limits what the template is allowed to see and prevents accidental access to lazy relationships or internal fields.

## 19. Naming commands/DTOs to show intent

Object names should reveal their role:

| Name | Suggested role |
| --- | --- |
| `SendWelcomeEmailCommand` | Request to send a welcome email |
| `SendInvoiceCommand` | Request to send an invoice |
| `OrderConfirmationRequest` | Input data from an API |
| `OrderMailView` | Presentation data for an order email |
| `RenderedEmail` | Rendered content |
| `OutboundMail` | Message prepared for handoff to the gateway |
| `MailAttachment` | Internal attachment resource descriptor |

Avoid generic names like `Data`, `MailInfo`, or `EmailObject` if they do not make clear where the object is used. At the same time, avoid overly long names containing every implementation detail.

A project might organize packages as:

~~~text
mail/
├── application/
│   ├── command/
│   │   └── SendOrderConfirmationCommand.java
│   └── SendOrderConfirmationHandler.java
├── model/
│   ├── OrderMailView.java
│   ├── RenderedEmail.java
│   └── OutboundMail.java
├── rendering/
│   └── ThymeleafOrderMailRenderer.java
└── infrastructure/
    └── SpringMailGateway.java
~~~

This structure is only an example. You can group packages by the `order` feature instead of layers if the project uses feature-based organization. What matters is that commands, view models, and transport adapters have easy-to-follow boundaries.

## 20. Testing command handlers and renderers

Commands/DTOs make unit testing easier because data is packaged into clear objects.

### 20.1. Testing that the handler orchestrates the use case

You can mock the repository, renderer, and gateway:

~~~java
@Test
void sendsConfirmationForExistingOrder() {
    // Arrange:
    // - repository returns order and customer
    // - renderer returns RenderedEmail
    // - gateway is a mock

    handler.handle(
            new SendOrderConfirmationCommand(
                    orderId,
                    "buyer@example.net"
            )
    );

    // Assert:
    // - renderer is called with the expected OrderMailView
    // - gateway is called with the expected OutboundMail
}
~~~

This test checks **orchestration and data passed between layers**, without needing a live SMTP connection.

### 20.2. Testing the renderer with fixed data

~~~java
OrderMailView view = new OrderMailView(
        "An <Bao>",
        "ORD-2048",
        "Confirmed",
        "1,250,000 VND",
        "18/11/2026",
        "https://app.example.org/orders/ORD-2048"
);

RenderedEmail rendered = renderer.render(
        view,
        Locale.forLanguageTag("vi-VN")
);
~~~

Checks:

- Subject contains the order code.
- Plain text contains the status, total amount, delivery date, and URL.
- HTML contains the same facts.
- Names with special characters are escaped in HTML text.
- Plain text keeps the name in raw text form.

### 20.3. Testing the gateway separately from real SMTP

You can use a fake/mock `JavaMailSender` to verify that the gateway creates a `MimeMessage` with the appropriate From, To, Subject, and body. For protocol testing, use an SMTP test server or isolated sandbox.

Not every unit test needs to send a real email. Real SMTP tests can be slow, network-dependent, and risk sending to unintended addresses if test configuration is not isolated.

## 21. Common mistakes when using commands or DTOs

### 21.1. One giant DTO for the entire system

**Problem:** a single object contains recipient, SMTP host, password, template name, HTML, domain entity, file path, and many optional fields. Each service uses only a subset.

**Fix:** split along boundaries: business command, view DTO, rendered content, and transport DTO when truly needed.

### 21.2. Using the request DTO as a command at every layer

The request DTO reflects the external API contract. It may contain client-allowed fields and web validation annotations. An application command should represent an application use case; the two objects may share fields in small cases, but they do not have to be the same type.

### 21.3. Letting the client decide email status or amount

**Problem:** email data can be forged if taken from the request without verification.

**Fix:** load data from the repository/domain and check permissions before rendering.

### 21.4. Putting MimeMessage into a command

**Problem:** the command depends on Jakarta Mail and forces callers to build messages at the wrong layer.

**Fix:** the command carries business intent; the gateway creates the MIME message after content is rendered.

### 21.5. Passing the entire entity into the template

**Problem:** exposes unnecessary fields, lazy loading, and persistence coupling.

**Fix:** create a small, strongly typed view DTO.

### 21.6. Passing uncontrolled HTML into a generic command

**Problem:** any caller can supply arbitrary content, making brand consistency and security policies hard to enforce.

**Fix:** business commands choose controlled templates; only the infrastructure layer accepts already-rendered content.

### 21.7. Mutable DTO modified mid-send

**Problem:** a component modifies the recipient or content after the command is created, causing retries and logs to diverge.

**Fix:** prefer records/immutable objects and defensive copies for collections.

### 21.8. Validating only in the controller

**Problem:** commands can also be created from a scheduler, event consumer, or internal job without going through a controller.

**Fix:** enforce invariants and business validation at the application/domain boundary; controller validation is only an additional input layer.

### 21.9. Using one generic command for all email types

**Problem:** callers choose subject, HTML, and templates themselves, losing business meaning.

**Fix:** use specific commands per use case; generic objects live only in mail infrastructure after content is prepared.

### 21.10. Not handling duplicates on retry

**Problem:** executing the same command multiple times can send multiple identical emails.

**Fix:** use a request ID/idempotency key, persist job state, and define a retry policy.

### 21.11. Putting request file paths into attachment DTOs

**Problem:** the application may read files outside permitted directories.

**Fix:** use authorized file IDs/storage keys, then resolve them to verified internal Resources.

### 21.12. Splitting classes just to have more classes

**Problem:** small projects accumulate intermediate layers that merely forward data without establishing useful boundaries.

**Fix:** split when there is a difference in responsibility, lifecycle, contract, or replaceability. One record and one service can be enough for a simple use case.

## 22. Reasoning exercises

**Question 1.** Should `SendOrderConfirmationCommand` contain `MimeMessage` or `orderId`?

Usually `orderId` and the minimal data needed by the use case. `MimeMessage` is an infrastructure detail created in the gateway after the data has been processed.

**Question 2.** Should `OrderMailView` and the `Order` entity be the same object?

Not necessarily. The entity serves business logic/persistence; the view DTO carries only display fields. Separating the DTO prevents internal data from reaching the template.

**Question 3.** Are commands and DTOs two different Java language constructs?

No. Both can be records or classes. A command emphasizes action intent; a DTO emphasizes transferring data.

**Question 4.** The client sends `totalAmount` in the request. Should that value be used in the invoice email?

Only if the business contract explicitly allows it and the value has been verified. Normally the total amount must come from authoritative invoice/domain data.

**Question 5.** A service only sends a three-field email. Is it mandatory to create separate request DTO, command, view DTO, and rendered DTO classes?

No. Only separate objects when they represent meaningful boundaries. Do not add abstractions that bring no benefit.

**Question 6.** Should `RenderedEmail` contain the SMTP password?

No. Rendered content and SMTP credentials belong to different responsibilities. Credentials are managed in infrastructure configuration/secret stores.

**Question 7.** A command is processed via a message queue and may be redelivered. What should you consider?

Idempotency, request IDs, job state, retries, and duplicate-send risk. Do not assume a command executes strictly once.

**Question 8.** Can a request pass `templateName` and invoke the template engine directly?

Never accept arbitrary template names. Use an allowlisted notification type/enum mapped to fixed templates.

**Question 9.** Does a DTO with `@Email` prove the recipient address exists?

No. The validator only checks syntax format; verifying ownership or deliverability requires a different process.

**Question 10.** Should `Resource` or `MimeMessage` be stored in the database for a worker to send later?

Usually no. Store file identifiers, business IDs, and serializable command data; the worker resolves the Resource and creates the MimeMessage during processing.

## 23. Mental model to remember

When designing an email-sending flow, place the right object at the right boundary:

~~~mermaid
flowchart TD
    A["Request DTO / Event"] --> B["Command: send intent"]
    B --> C["Application Service"]
    C --> D["Authoritative business data"]
    D --> E["Mail View DTO"]
    E --> F["Renderer"]
    F --> G["RenderedEmail"]
    G --> H["Mail Gateway"]
    H --> I["MimeMessageHelper"]
    I --> J["JavaMailSender"]
~~~

Principles to remember:

1. **Commands express actions**, such as `SendOrderConfirmationCommand`; the handler/service executes them.
2. **DTOs carry data across boundaries**, such as request DTOs, mail view DTOs, or rendered content.
3. **Do not trust client data for status, amounts, access permissions, or templates** when the system should decide them.
4. **Use small view DTOs** instead of passing entities or application contexts into templates.
5. **Prefer immutable objects** and defensive copies for collections so data does not mutate between steps.
6. **Keep Spring Mail in the gateway layer**; commands do not need to depend on `MimeMessage` or `JavaMailSender`.
7. **Render plain text and HTML from the same snapshot/view model** to prevent inconsistent representations.
8. **Attachments use authorized file identifiers**, not arbitrary filesystem paths from requests.
9. **Handle idempotency during asynchronous sending or retries** to avoid duplicate emails.
10. **Do not over-engineer**: only create separate objects when they express genuinely distinct contracts or responsibilities.

For a small application, one specific command and one mail service may be enough. As more business flows, templates, providers, or triggers appear, separating commands, view DTOs, renderers, and gateways lets you change delivery mechanics without tangling business logic. `JavaMailSender` remains just the adapter sending MIME over SMTP; commands and DTOs help the application decide **which email to send, to whom, from which data, and what content is allowed to be displayed**.
