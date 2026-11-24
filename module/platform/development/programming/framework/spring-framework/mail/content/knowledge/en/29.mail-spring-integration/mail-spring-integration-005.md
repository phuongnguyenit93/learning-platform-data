# Routing Messages by Email Type

## 1. What Is Inbound Email Routing?

In **Spring Integration Mail**, an application can receive emails from a mailbox via **IMAP/POP3**, turn each email into a **Spring Integration Message**, and route the message to different processing flows. **Routing messages by email type** is the step that decides which department or workflow an email should reach based on extracted and classified signals.

For example, a shared inbox address might receive:

- Customer support request emails.
- Reply emails for an existing ticket.
- Invoices and documents sent by partners.
- Delivery Status Notifications (DSN) reporting that a sent email bounced.
- Automated alerts from monitoring systems.
- Spam, malformed messages, or messages of unrecognized types.

If all emails go to a single handler, that handler ends up containing sprawling if/else branches, MIME parsing, ticket lookups, bounce updates, attachment storage, and error handling. This makes testing hard, blurs security boundaries, and lets failures in one email type impact the rest.

Spring Integration lets you separate three responsibilities:

1. **Mail ingestion:** connect to the mail server and receive messages.
2. **Classification:** extract required attributes and determine the business type.
3. **Routing:** forward the classified message to the appropriate channel/handler, with a fallback branch for unknown cases.

**Routing here means in-application routing**, not forwarding an email from one mail server to another. The job of **RecipientListRouter**, **HeaderValueRouter**, **MethodInvokingRouter**, or **@Router** in Spring Integration is to select the **destination Spring Message channel**, not to re-send the email over SMTP.

## 2. A Business Example

Suppose a company has an integration mailbox:

~~~text
automation@example.com
~~~

The mailbox receives these emails:

| Received Email | Signal | Business Type | Handler |
|---|---|---|---|
| Customer asks about order status | Support request content | SUPPORT_REQUEST | Create ticket |
| Customer replies to support email | In-Reply-To/References and valid ticket | SUPPORT_REPLY | Update ticket |
| Partner sends invoice PDF | Authorized partner source, valid attachment | INVOICE | Invoice ingestion workflow |
| Receiving system returns DSN | MIME report-type=delivery-status | DELIVERY_REPORT | Bounce/delivery reconciliation |
| Internal system sends alert | Authenticated source and accepted format | SYSTEM_ALERT | Incident workflow |
| Email lacks clear signals | No match or conflicting signals | UNKNOWN | Quarantine/triage |

This is an **application rule table**, not message types pre-declared inside Spring Integration Mail.

An email with a PDF attachment **is not automatically an invoice**; a Subject containing the word "invoice" does not prove the sender is a trusted partner either. The classifier must combine **structural signals, mailbox context, business data, and trust level**.

## 3. Spring Integration Mail Flow Diagram

~~~text
                IMAP / POP3 mailbox
                        |
                        v
              Mail inbound adapter
                        |
                        v
                 rawMailChannel
                        |
                        v
             Normalize / MIME parse
                        |
                        v
              Durable inbox + dedup
                        |
                        v
              EmailTypeClassifier
                        |
                        v
               classifiedChannel
                        |
                        v
                 @Router
             /      |       \
            /       |        \
      support   delivery     invoice
      channel    channel     channel
         |         |           |
         v         v           v
      Ticket     Bounce      Document
      handler    handler      handler
            \      |       /
             \     |      /
                  UNKNOWN
                     |
                     v
            Quarantine / triage
~~~

In a system that cannot afford to lose mail, the **durable inbox** step should occur before business side effects. You can classify before persisting if both the result and raw message are stored atomically in the same workflow, but never delete/mark an email as processed on the server before persisting enough state to recover.

## 4. Distinguishing Email Type, MIME Type, and Payload Type

The word "type" has three distinct meanings:

**Business email type:**

~~~text
SUPPORT_REQUEST
SUPPORT_REPLY
INVOICE
DELIVERY_REPORT
SYSTEM_ALERT
UNKNOWN
~~~

**MIME Content-Type:**

~~~text
text/plain
text/html
multipart/alternative
multipart/mixed
multipart/report
application/pdf
~~~

**Payload type in Spring Integration:**

~~~text
jakarta.mail.internet.MimeMessage
Custom InboundEmail record
Custom MailEvent record
String / byte[] / other payload type
~~~

Do not use these three concepts interchangeably. An invoice email can be **multipart/mixed**, and a support email can also be **multipart/mixed**. Both contain HTML and a PDF yet must go to different handlers.

To keep business routing easy to understand, determine **EmailType** first and route on that value rather than routing directly on raw Content-Type strings.

## 5. What Roles Do Spring Mail and Spring Integration Mail Play?

| Component | Role in Application |
|---|---|
| **JavaMailSender** | Creates/sends email over SMTP; not an inbound mailbox router |
| **Jakarta Mail Session/Store/Folder/Message** | Connects to IMAP/POP3 and reads email content |
| **ImapMailReceiver / Pop3MailReceiver** | Mail-receiving components in Spring Integration Mail |
| **MailReceivingMessageSource** | Acts as the source for a polling flow |
| **IMAP IDLE inbound adapter** | Receives mailbox change signals when the server supports IDLE |
| **Transformer** | Normalizes `MimeMessage` into application data |
| **Filter** | Blocks messages that do not meet a condition |
| **Router** | Selects one or more output channels |
| **ServiceActivator** | Processes messages on the matching channel |
| **Error channel** | Receives errors in flows with async error handling |
| **Persistent inbox/queue** | Persists deduplication state and enables independent retries |

**Spring Integration** organizes these components into **Enterprise Integration Patterns** such as Message Channel, Message Router, Filter, Transformer, and Service Activator.

Not all endpoints share a single ACID transaction. Specifically, the **IMAP/POP3 server does not participate in the application's database transaction**, and a channel successfully delivering a message does not mean business processing is complete.

## 6. Routing Is a Channel Decision, Not Automatic Processing Success

Suppose:

~~~text
INVOICE email
     |
     v
Router -> invoiceChannel
     |
     v
InvoiceHandler
     |
     +-- Object storage unavailable
     |
     v
Exception
~~~

The router picked the right channel, yet invoice processing still failed. Therefore you must have:

- **Inbox state** for each received email.
- **Error handling** and retries tailored to each type.
- **Idempotency** so retries do not create two invoices or tickets.
- **Quarantine/dead-letter** handling for unprocessable data.
- **Metrics** separating classification errors, routing errors, and handler errors.

A design that treats "routed" as "processed" risks losing data when the application crashes or a downstream service is temporarily unavailable.

## 7. Defining EmailType as a Domain Enum

Example:

~~~java
public enum EmailType {
    DELIVERY_REPORT,
    SUPPORT_REPLY,
    SUPPORT_REQUEST,
    INVOICE,
    SYSTEM_ALERT,
    UNKNOWN
}
~~~

The declaration order in the enum does not imply priority by itself; the order of **classifier rules** determines what is evaluated first.

Certain types require special trust levels:

- **DELIVERY_REPORT**: based on trustworthy DSN structure and correlation, not a "Delivery failure" Subject.
- **SUPPORT_REPLY**: requires matching the ticket via thread/correlation and verifying reply authorization.
- **INVOICE**: cannot rely solely on a `.pdf` filename; needs source policy, format, and file checks.
- **SYSTEM_ALERT**: requires an authenticated source instead of letting any sender put "ALERT" in the Subject.
- **UNKNOWN**: a valid classifier outcome when evidence is insufficient, not necessarily an exception.

## 8. Normalized Inbound Model

Do not force every handler to read **MimeMessage** directly and parse MIME parts itself. You can design a shared model:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Map;

public record InboundEmail(
        String inboxId,
        String tenantId,
        String mailboxId,
        String fromAddress,
        List<String> toAddresses,
        String subject,
        String messageId,
        List<String> referenceMessageIds,
        String plainText,
        String sanitizedHtml,
        List<AttachmentRef> attachments,
        String rawMessageRef,
        Instant receivedAt,
        EmailType type,
        Map<String, String> routingFacts
) {
}

public record AttachmentRef(
        String storageKey,
        String safeDisplayName,
        String detectedMediaType,
        long sizeBytes
) {
}
~~~

This is an **illustrative domain model**, not a built-in Spring Integration class.

Principles when designing the model:

1. **tenantId/mailboxId** come from authenticated connector configuration, never trusting sender-supplied MIME headers.
2. **inboxId** is a durable identifier for deduplication and tracing.
3. **rawMessageRef** references the stored EML in a protected store for auditing.
4. **attachments** only carry references to stored/scanned or quarantined data rather than stuffing entire files into Spring Messages.
5. **sanitizedHtml** differs from raw HTML, since HTML received via email is untrusted.
6. **type** is the classification output; you can store the classifier version separately.
7. **routingFacts** holds only normalized metadata, avoiding raw bodies or unnecessary PII in metric labels.

In a real application, enforce validation and defensive copies for lists/maps; the model here focuses on responsibility boundaries.

## 9. Choosing When to Classify

There are three strategies:

| Timing | Benefit | Trade-off |
|---|---|---|
| **Before persisting** | Fast routing, avoids storing irrelevant emails | If the process crashes before persisting, trace can be lost; hard to reclassify |
| **After persisting raw EML** | Provides source data for retries, audits, and classifier updates | Uses storage; raw content must be protected |
| **Two-phase: coarse and deep** | Initial classification by headers, then deep MIME/attachment inspection as needed | Requires managing state and differences between the two classifications |

For business systems needing reliability, a common choice is:

~~~text
Fetch -> assign mailbox identity -> persist safely
      -> parse -> classify -> route -> process
~~~

For very high-traffic mailboxes, you can optimize with **header-first inspection**, but never treat unverified header-based classification as sufficient for sensitive actions.

## 10. Basic Dependencies and Configuration

Example of a modern **Spring Boot** project using Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-mail'

    // When the application also sends outbound SMTP.
    implementation 'org.springframework.boot:spring-boot-starter-mail'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

**Spring Integration Mail** supports inbound email; `starter-mail` for SMTP sending is often used in the same application but is not mandatory for every inbound-only application.

The Java examples below use **jakarta.mail.***, matching Spring Framework/Spring Integration lines built on Jakarta Mail. Older projects using **javax.mail.*** must pick compatible dependencies and APIs without mixing namespaces.

Verify that **Spring Boot, Spring Integration, and Jakarta Mail** belong to the same supported generation. DSL/annotation details may vary across versions; the snippets below illustrate a sound architecture rather than replacing provider-specific receiver/authentication configuration.

## 11. Creating an Inbound Receiver and Wiring an Input Channel

With Spring Integration Mail, one option is **polling IMAP** using **ImapMailReceiver** combined with **MailReceivingMessageSource**.

Model:

~~~text
ImapMailReceiver
        |
        v
MailReceivingMessageSource
        |
        v
Inbound channel adapter + Poller
        |
        v
mailRawChannel
~~~

Flow declaration outline:

~~~java
import java.util.concurrent.TimeUnit;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mail.MailReceivingMessageSource;

@Configuration
public class MailPollingFlowConfiguration {

    @Bean
    public IntegrationFlow imapPollingFlow(
            MailReceivingMessageSource source
    ) {
        return IntegrationFlow
                .from(
                        source,
                        spec -> spec.poller(
                                Pollers.fixedDelay(
                                        30,
                                        TimeUnit.SECONDS
                                )
                        )
                )
                .channel("mailRawChannel")
                .get();
    }
}
~~~

This snippet assumes **MailReceivingMessageSource** has already been declared as a bean by the application with an appropriate **ImapMailReceiver**. The mail receiver must have explicit endpoint, TLS, authentication, and message read/mark policies. Never put username/password in source code or log URLs containing credentials.

This is a **polling** flow, not IMAP IDLE. If using IDLE, the inbound adapter and reconnect handling differ, while the downstream **normalize -> classify -> route** pipeline can be reused.

### Note on Input Payload

Depending on the adapter, header mapper, and receiver configuration, the payload may be a **Jakarta Mail Message/MimeMessage** or an already converted form. The examples below assume the payload is a **MimeMessage**.

Before wiring steps together, verify the exact adapter contract in your Spring Integration version. Never blindly cast every payload to `MimeMessage` if the actual receiver configuration produces a different payload type.

## 12. Declaring MessageChannels with Stable Names

To demonstrate routing, you can use **DirectChannel** beans:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class MailRoutingChannels {

    @Bean
    public MessageChannel mailRawChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel mailClassifiedChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel mailDeliveryReportChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel mailSupportReplyChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel mailSupportRequestChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel mailInvoiceChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel mailSystemAlertChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel mailUnknownChannel() {
        return new DirectChannel();
    }
}
~~~

In practice, **Spring Integration can auto-create/resolve some channels by name** depending on configuration. Declaring them explicitly here documents which channels exist and allows operators to attach interceptors/metrics per channel.

### What Does DirectChannel Mean?

**DirectChannel** invokes the subscriber directly on the sender's thread. It is not a durable queue. If a handler throws an exception, the error can propagate upstream within the same synchronous call chain.

When asynchronous processing or stronger isolation is needed, you can move to **ExecutorChannel**, **QueueChannel**, a message broker, or a **persistent inbox + worker**. However, switching channels does not automatically add durable storage or exactly-once semantics; persistence and acknowledgment must be explicitly configured.

## 13. Normalizing MimeMessage Before Routing

A message from the inbound adapter might look like:

~~~text
From: customer@example.net
To: support@example.com
Subject: Re: Ticket #123
In-Reply-To: <ticket-123@service.example>
Content-Type: multipart/mixed
~~~

Do not make every handler re-parse headers, MIME, and attachments itself. A **Transformer** can convert from the Jakarta Mail object to the domain model:

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.integration.annotation.Transformer;
import org.springframework.stereotype.Component;

@Component
public class MailNormalizationTransformer {

    private final InboundMailNormalizer normalizer;
    private final EmailTypeClassifier classifier;

    public MailNormalizationTransformer(
            InboundMailNormalizer normalizer,
            EmailTypeClassifier classifier
    ) {
        this.normalizer = normalizer;
        this.classifier = classifier;
    }

    @Transformer(
            inputChannel = "mailRawChannel",
            outputChannel = "mailClassifiedChannel"
    )
    public InboundEmail normalize(MimeMessage raw)
            throws Exception {

        InboundEmail candidate = normalizer.normalize(raw);
        return classifier.withType(candidate);
    }
}
~~~

**InboundMailNormalizer** and **EmailTypeClassifier** are application-defined interfaces/services, not built-in Spring Integration classes.

What the normalizer should do depends on the problem:

- Attach **mailboxId/tenantId** from trusted receiver configuration.
- Extract From/To/Subject/Message-ID, In-Reply-To/References as needed.
- Parse MIME within size/depth/part limits.
- Extract plain text/HTML and attachment references.
- Persist the raw email or durable identifier before causing side effects.
- Determine safe routing signals and suspicion flags.

The example only expresses **channel and type bindings**; production design must supply mailbox context from the authenticated adapter. If ingestion spans multiple mailboxes, never use a default normalizer that hardcodes every email to the same tenant.

## 14. Separating the Classifier from the Spring Router

The **Classifier** decides which type an email belongs to. The **Router** decides which channel that type goes to.

~~~text
InboundEmail raw facts
         |
         v
EmailTypeClassifier
         |
         +-- EmailType.INVOICE
         |
         v
Spring Integration Router
         |
         +-- mailInvoiceChannel
~~~

Benefits of separating the two steps:

- Unit test the classifier as a pure business function without booting Spring Integration.
- Change channel topology without editing classification rules.
- Upgrade classifier versions without altering retry/dispatch logic.
- Reclassify emails sitting in `UNKNOWN` via a controlled workflow.
- Logs/metrics show whether an error occurred in **classification** or **routing/channel resolution**.

A signal model:

~~~java
public record ClassificationSignals(
        boolean suspiciousOrMalformed,
        boolean correlatedDeliveryReport,
        boolean authorizedTicketReply,
        boolean trustedInvoiceSource,
        boolean validatedInvoiceAttachment,
        boolean authenticatedSystemAlert,
        boolean eligibleSupportRequest
) {
}
~~~

These booleans represent values verified by appropriate components. For instance, **authorizedTicketReply** is not the result of the Subject containing "Re:", but of ticket/thread correlation and reply authorization checks.

## 15. Classifier Example with Priority Ordering

~~~java
public final class DefaultEmailClassifier {

    public EmailType classify(ClassificationSignals signals) {

        if (signals.suspiciousOrMalformed()) {
            return EmailType.UNKNOWN;
        }

        if (signals.correlatedDeliveryReport()) {
            return EmailType.DELIVERY_REPORT;
        }

        if (signals.authorizedTicketReply()) {
            return EmailType.SUPPORT_REPLY;
        }

        if (signals.trustedInvoiceSource()
                && signals.validatedInvoiceAttachment()) {
            return EmailType.INVOICE;
        }

        if (signals.authenticatedSystemAlert()) {
            return EmailType.SYSTEM_ALERT;
        }

        if (signals.eligibleSupportRequest()) {
            return EmailType.SUPPORT_REQUEST;
        }

        return EmailType.UNKNOWN;
    }
}
~~~

The order in this example is an **illustrative policy**, not a universal order for every organization:

- DSN emails are checked early to avoid putting bounces into support tickets.
- Verified replies are distinguished from new support requests.
- Invoices require both an eligible source and a validated attachment.
- System alerts count as alerts only with authentication evidence.
- Cases lacking sufficient signals fall into `UNKNOWN`.

If multiple rules match simultaneously without an explicit business precedence, you can choose **AMBIGUOUS/UNKNOWN for triage** rather than silently picking the first branch.

### Do Not Use Self-Declared Sender Booleans

Signals such as `trustedInvoiceSource`, `correlatedDeliveryReport`, or `authenticatedSystemAlert` must come from **system verification processes**, not a self-declared MIME header:

~~~text
X-Email-Type: INVOICE
~~~

An external sender can easily add that header. If using custom headers, verify a **trusted source**, signature, or controlled delivery channel.

## 16. Routing with @Router

Spring Integration's **@Router** annotation can accept a domain payload and return the destination channel name:

~~~java
import org.springframework.integration.annotation.Router;
import org.springframework.stereotype.Component;

@Component
public class InboundEmailRouter {

    @Router(inputChannel = "mailClassifiedChannel")
    public String route(InboundEmail email) {
        return switch (email.type()) {
            case DELIVERY_REPORT -> "mailDeliveryReportChannel";
            case SUPPORT_REPLY -> "mailSupportReplyChannel";
            case SUPPORT_REQUEST -> "mailSupportRequestChannel";
            case INVOICE -> "mailInvoiceChannel";
            case SYSTEM_ALERT -> "mailSystemAlertChannel";
            case UNKNOWN -> "mailUnknownChannel";
        };
    }
}
~~~

In the example:

1. The transformer creates an **InboundEmail** with a resolved type.
2. **@Router** receives `InboundEmail` from **mailClassifiedChannel**.
3. The **route(...)** method returns the corresponding channel bean name.
4. Spring Integration forwards the message to the chosen channel.
5. A **ServiceActivator** registered on that channel executes the business logic.

**Do not return null** to handle `UNKNOWN` unless you know the exact semantics of the router and discard configuration in use. An explicit **mailUnknownChannel** preserves unclassified emails and keeps them observable.

### Switch Expressions and Exhaustive Cases

Routing on an enum with an explicit **switch** forces developers adding a new `EmailType` to decide its channel (depending on whether the language/expression enforces exhaustiveness at compile time). This is safer than dynamic string routing that could build channel names from untrusted input.

## 17. Channel Processing with Service Activator

Example:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class MailBusinessHandlers {

    private final TicketService ticketService;
    private final InvoiceIngestionService invoiceService;
    private final DeliveryReportService deliveryReportService;
    private final AlertIngestionService alertService;
    private final MailTriageService triageService;

    public MailBusinessHandlers(
            TicketService ticketService,
            InvoiceIngestionService invoiceService,
            DeliveryReportService deliveryReportService,
            AlertIngestionService alertService,
            MailTriageService triageService
    ) {
        this.ticketService = ticketService;
        this.invoiceService = invoiceService;
        this.deliveryReportService = deliveryReportService;
        this.alertService = alertService;
        this.triageService = triageService;
    }

    @ServiceActivator(inputChannel = "mailSupportRequestChannel")
    public void createTicket(InboundEmail email) {
        ticketService.openFromInboundMail(email);
    }

    @ServiceActivator(inputChannel = "mailSupportReplyChannel")
    public void appendReply(InboundEmail email) {
        ticketService.appendAuthorizedReply(email);
    }

    @ServiceActivator(inputChannel = "mailInvoiceChannel")
    public void ingestInvoice(InboundEmail email) {
        invoiceService.ingest(email);
    }

    @ServiceActivator(inputChannel = "mailDeliveryReportChannel")
    public void recordDelivery(InboundEmail email) {
        deliveryReportService.process(email);
    }

    @ServiceActivator(inputChannel = "mailSystemAlertChannel")
    public void recordAlert(InboundEmail email) {
        alertService.ingest(email);
    }

    @ServiceActivator(inputChannel = "mailUnknownChannel")
    public void quarantine(InboundEmail email) {
        triageService.quarantine(email);
    }
}
~~~

**TicketService, InvoiceIngestionService, DeliveryReportService, AlertIngestionService, and MailTriageService** are application interfaces/services. Spring Integration only provides the mechanism to invoke them when a message arrives on the matching input channel.

Handlers should be **idempotent** by `inboxId` and business key. A message may be redelivered after retries, restarts, or re-enqueueing; a handler must never assume it runs only once.

## 18. Routing with Java DSL and Channel Mapping

Besides the **@Router** annotation, Spring Integration Java DSL allows declaring routing inside an **IntegrationFlow**. A common approach:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class ClassifiedMailFlow {

    @Bean
    public IntegrationFlow routeClassifiedMail() {
        return IntegrationFlow
                .from("mailClassifiedChannel")
                .route(
                        InboundEmail.class,
                        InboundEmail::type,
                        mapping -> mapping
                                .channelMapping(
                                        EmailType.DELIVERY_REPORT,
                                        "mailDeliveryReportChannel"
                                )
                                .channelMapping(
                                        EmailType.SUPPORT_REPLY,
                                        "mailSupportReplyChannel"
                                )
                                .channelMapping(
                                        EmailType.SUPPORT_REQUEST,
                                        "mailSupportRequestChannel"
                                )
                                .channelMapping(
                                        EmailType.INVOICE,
                                        "mailInvoiceChannel"
                                )
                                .channelMapping(
                                        EmailType.SYSTEM_ALERT,
                                        "mailSystemAlertChannel"
                                )
                                .defaultOutputChannel(
                                        "mailUnknownChannel"
                                )
                )
                .get();
    }
}
~~~

This snippet illustrates **payload-based routing with channel mappings**. Overloads and DSL classes must match your actual Spring Integration version.

**Choose one declaration style:** if you already use **@Router(inputChannel = "mailClassifiedChannel")** as in the previous section, do not also configure a DSL flow on the same channel unless intentionally designing **competing consumers**. Two routers registered as independent subscribers on a `DirectChannel` can conflict or make endpoint selection nondeterministic depending on channel/dispatcher.

In this document, the `@Router` and DSL snippets are **two alternative options**, not two beans to enable together.

### Why Is Channel Mapping Better Than Building Channel Names from Strings?

Do not let sender-declared data control the output channel:

~~~java
// Anti-pattern: email-declared value dynamically constructs channel name.
return "mail" + rawHeaderValue + "Channel";
~~~

A malicious or malformed email could cause the router to look up an invalid or unintended channel. Use an **enum allowlist** and deterministic mappings to keep the topology safe.

## 19. Header-Based Routing: When to Use HeaderValueRouter?

Spring Integration provides **HeaderValueRouter** to use a Spring Message header as the routing key, for example:

~~~text
Spring Message:
  payload = InboundEmail
  headers:
    emailType = INVOICE
~~~

Conceptual flow:

~~~text
Classification transformer
      |
      +-- Set header emailType = INVOICE
      |
      v
HeaderValueRouter(emailType)
      |
      +-- INVOICE -> mailInvoiceChannel
      +-- UNKNOWN -> mailUnknownChannel
~~~

Mandatory condition: **`emailType` in the Spring Message header must be produced by the application's classifier**, not copied automatically from a raw MIME header like **X-Email-Type** from the sender.

In Spring Integration, **Spring Message headers** and **MIME headers** are not the same system:

- MIME headers come from the email and can be forged.
- Spring Message headers pass metadata inside the integration pipeline.
- Do not assume internal metadata becomes trustworthy merely by placing it into a Spring Message header.
- Transformers/header enrichers must preserve data source boundaries and only populate trusted keys after verification.

A **payload-based router** fits best when the domain model has a typed `EmailType`. **HeaderValueRouter** fits when the routing key is shared metadata across multiple payloads or determined by middleware.

## 20. Single Destination vs. Multiple Destinations?

Sometimes one email serves multiple purposes:

~~~text
Invoice email:
  -> Persist document
  -> Create audit event
  -> Update reporting
~~~

Distinguish between:

- **Router selecting the primary business flow**: e.g., `INVOICE` goes to `invoiceChannel`.
- **Post-processing fan-out**: the invoice service emits an event after successful ingestion to audit/reporting.
- **RecipientListRouter / PublishSubscribeChannel**: can deliver the same Spring Message to multiple channels/subscribers when required by design.

Do not route an email directly to three side-effecting handlers and treat all three as one atomic transaction:

~~~text
Invoice email
  |
  +-- create invoice (success)
  +-- write audit (success)
  +-- send acknowledgement (failure)
~~~

If synchronous fan-out lacks an appropriate transaction boundary, retrying the email may create duplicate invoices.

Safer architecture:

~~~text
INVOICE -> InvoiceIngestionService
             |
             v
       DB transaction commit
             |
             v
       Business outbox event
             |
         +---+---+
         |       |
         v       v
        Audit   Report
~~~

**Single-destination routing for the primary responsibility** clarifies ownership and rollback. Additional side effects can be triggered from a durable event after primary business work commits.

## 21. Precedence Rules and Conflicts

An email can carry multiple signals at once:

~~~text
Subject: Re: Invoice #123
In-Reply-To: <ticket-123@service.example>
Attachment: invoice.pdf
From: external-partner@example.net
Content-Type: multipart/mixed
~~~

Should this be treated as **SUPPORT_REPLY** or **INVOICE**?

There is no universal answer. Guiding principles:

1. **Check mailbox authorization and context first.** A dedicated invoice mailbox may prioritize the invoice flow over a support mailbox.
2. **Verify trustworthy correlation.** A thread verified to belong to an existing ticket is a stronger signal than "Re:" in the subject.
3. **Never treat an attachment as sole proof.** A PDF file might just be supporting documentation attached to a reply.
4. **Use policy-documented precedence**, never relying on the incidental iteration order of a map.
5. **When conflicts cannot be resolved**, route to triage/`UNKNOWN` rather than silently picking the less safe branch.

For example, you can add an enum:

~~~java
public enum ClassificationOutcome {
    MATCHED,
    AMBIGUOUS,
    UNKNOWN,
    REJECTED_UNSAFE
}
~~~

Then persist both **type** and **outcome** so operators know what evidence drove routing. Even if policy only uses `EmailType.UNKNOWN`, store a separate reason code such as **CONFLICTING_SIGNALS** or **UNVERIFIED_SENDER**.

## 22. DSN/Bounce: Do Not Classify by Subject Alone

A DSN may have a MIME structure like:

~~~text
Content-Type: multipart/report;
  report-type=delivery-status
  |
  +-- text/plain
  |
  +-- message/delivery-status
  |
  +-- message/rfc822-headers (optional)
~~~

Inside the **message/delivery-status** part there may be:

~~~text
Final-Recipient: rfc822; customer@recipient.example
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 User unknown
~~~

A trustworthy classifier should combine:

- MIME subtype and DSN **report-type**.
- Structured delivery-status fields.
- Message source checks or appropriate ingestion path.
- **Correlation** with a notification-recipient sent by the application.
- Guards against spoofed DSNs, backscatter, and duplicates.

Avoid:

~~~java
// Insufficient to determine DELIVERY_REPORT.
if (subject.contains("Mail delivery failed")) {
    return EmailType.DELIVERY_REPORT;
}
~~~

An external sender can craft a regular email with such a Subject. If a handler uses that spoofed email to suppress a recipient, the system could wrongly block legitimate users.

### Distinguish Routing from Delivery Status Confirmation

An email classified as `DELIVERY_REPORT` is not enough to conclude all recipients hard-bounced. The handler still has to parse:

- **Action** (`failed`/`delayed`/`delivered`/...).
- **Status** and `Diagnostic-Code`.
- The specific affected recipients.
- Provider event/notification correlation.
- Appropriate delivery state transition policies.

The router only selects **mailDeliveryReportChannel**, while **DeliveryReportService** is responsible for verifying and updating durable state.

## 23. Classifying Replies via In-Reply-To/References

A reply email may carry:

~~~text
Message-ID: <reply-456@customer.example>
In-Reply-To: <support-123@service.example>
References: <support-123@service.example>
Subject: Re: Support request 123
~~~

To route as **SUPPORT_REPLY**, the application can:

1. Extract `In-Reply-To` and `References` from headers via Jakarta Mail.
2. Match against the application's **outbound_message_correlation** table.
3. Look up a valid ticket linked to that message ID/correlation token.
4. Check whether the sender or tenant is authorized to update the ticket per policy.
5. If matched and authorized, classify as `SUPPORT_REPLY`.
6. Otherwise, route to `SUPPORT_REQUEST` or `UNKNOWN` depending on mailbox policy.

**Do not treat In-Reply-To as authentication proof.** A sender can forge headers and reference someone else's Message-ID if they have seen that value. Authorization to modify a ticket must be verified independently.

### When the Subject Contains a Ticket Code

Example:

~~~text
Subject: [TICKET-123] I want to add an image
~~~

A ticket code can be a supporting signal, but if codes are guessable it is insufficient to grant ticket-update permissions. Use an **opaque reply token** or per-thread reply addresses, combined with identity/authorization checks and retention policies.

## 24. Classifying Invoices: Is an Attachment Necessary or Sufficient?

An email carrying **invoice.pdf** is not automatically a valid invoice.

Example:

~~~text
From: vendor@example.net
To: invoices@example.com
Subject: Invoice INV-2026-104
Content-Type: multipart/mixed
Attachment: invoice.pdf
~~~

The classifier can use:

| Signal | Confidence Level |
|---|---|
| Receiving mailbox is the configured invoice mailbox | Useful initial routing signal |
| From belongs to partner allowlist | Requires source authentication, not mere string matching |
| DKIM/DMARC from appropriate trust boundary | Strengthens domain evidence, does not prove business validity |
| MIME part has attachment | Indicates presence of a file |
| File type verified from bytes and policy | Stronger than extension alone |
| Invoice number matches order/partner | Business evidence |
| Document signature/format is valid | Problem-dependent |

Routing can be split into two phases:

~~~text
Header-level candidate = POSSIBLE_INVOICE
          |
          v
Attachment quarantine / scan / metadata validation
          |
          v
CLASSIFIED = INVOICE or UNKNOWN/REJECTED_UNSAFE
~~~

If file scanning is slow, do not hold the IMAP session and router thread waiting. Persist the email and hand off to a document validation worker with its own budget and timeout.

## 25. Classifying System Alerts

Some organizations receive emails from monitoring systems or external services:

~~~text
From: monitor@alerts.example
Subject: CRITICAL Database latency
X-Alert-Type: database
~~~

**Do not** route into automated incident remediation solely because the Subject starts with "CRITICAL" or carries an `X-Alert-Type` header.

Verify:

- Whether the receiving mailbox/channel is dedicated and protected.
- Whether the provider supplies a signature, API credential, or domain authentication mechanism.
- Whether the message corresponds to a registered integration.
- Whether the payload matches a valid schema without arbitrary commands.
- How tightly the alert handler's blast radius is bounded.

If system emails can trigger restarts, grant access, or transfer assets, require **out-of-band approval or authentication** for risky actions.

### Email Is Not a Trusted Command Channel by Default

Receiving an email from an address that "looks like admin" is insufficient to perform a sensitive operation. Routing only selects the next inspection workflow; it never grants authority to the sender.

## 26. Where Should Unknown Emails Go?

The `UNKNOWN` flow should be designed as a normal business outcome:

~~~text
Unknown or ambiguous email
           |
           v
mailUnknownChannel
           |
           v
Store reason code + raw reference
           |
           v
Quarantine / manual triage queue
           |
           +-- Reclassify after rule update
           +-- Assign to support
           +-- Reject under policy
           +-- Delete after retention
~~~

Reasons can be standardized:

~~~text
UNSUPPORTED_MIME
MALFORMED_MESSAGE
UNTRUSTED_SENDER
CONFLICTING_SIGNALS
NO_MATCHING_RULE
MISSING_REQUIRED_ATTACHMENT
CORRELATION_NOT_FOUND
POLICY_REJECTED
~~~

Do not use an `UNKNOWN` channel to **silently drop** unclassified emails if there is any risk of losing critical business data.

At the same time, do not store all spam and huge attachments indefinitely. Enforce retention policies, size caps, quarantine storage, and abuse protection.

## 27. Multi-Dimensional Routing: Tenant, Mailbox, and Type

In SaaS, **EmailType** alone is often insufficient to select a handler:

~~~text
Tenant A / support inbox / SUPPORT_REPLY
    -> Tenant A ticket service

Tenant B / support inbox / SUPPORT_REPLY
    -> Tenant B ticket service

Tenant A / invoice inbox / INVOICE
    -> Tenant A invoice workflow
~~~

Proper model:

~~~text
Authenticated mailbox configuration
           |
           +-- tenantId
           +-- mailboxId
           +-- allowed email types
           |
           v
EmailTypeClassifier
           |
           v
Router -> typed channel
           |
           v
Tenant-scoped handler (authorization enforced)
~~~

Do not construct dynamic channel names from a **sender-supplied tenantId**. In most cases, handlers can share **the same channel per EmailType** while executing with an authenticated tenant context and tenant-scoped repository authorization.

If strong isolation is required, you can partition workers/queues by tenant or tenant group, provided routing and quota topology are governed by internal configuration rather than raw MIME headers.

## 28. Routing and Deduplication: Do Not Rely on a Single Poll

An email can appear multiple times in an inbound flow:

- IMAP polling fetches the same message again before the application marks it or saves a checkpoint.
- IMAP IDLE disconnects and resyncs from an older UID.
- POP3 keeps messages on the server and re-downloads them in a later session.
- The process crashes after persisting but before updating mailbox state.
- An email is copied/moved between folders and appears under a different folder identifier.
- Multiple workers read the same mailbox concurrently.

If the router forwards every duplicate to **TicketService.openFromInboundMail(...)**, the application may create multiple tickets from one email.

**Routing is not a deduplication mechanism.** You need a durable **inbox identity** before triggering side effects.

Example:

~~~text
IMAP:
  (tenantId, mailboxId, folderId, uidValidity, uid)

POP3:
  (tenantId, mailboxId, uidl)

Application:
  inboxId (generated after successful unique insert)
~~~

Never rely on the `Message-ID` header alone as an absolute unique key: the header may be missing, duplicated, altered, or arbitrarily forged by a sender.

## 29. Inbox Pattern: Persist First, Route Later

A reliability-first design:

~~~text
IMAP/POP3 adapter
       |
       v
Extract mailbox identity
       |
       v
BEGIN DATABASE TRANSACTION
  INSERT mail_inbox with unique source identity
  INSERT routing_work_item
COMMIT
       |
       v
Business worker reads inboxId
       |
       v
Parse / classify / route
       |
       v
Handler transaction
       |
       v
PROCESSED or RETRY/QUARANTINED
~~~

If the same message is fetched again, the unique constraint prevents inserting a duplicate inbox record. If persisted successfully yet not routed due to a crash, **routing_work_item** remains for a worker to pick up.

Table example:

~~~sql
CREATE TABLE mail_inbox (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id         VARCHAR(120) NOT NULL,
    mailbox_id        VARCHAR(120) NOT NULL,
    folder_id         VARCHAR(300),
    uid_validity      BIGINT,
    imap_uid          BIGINT,
    pop3_uidl         VARCHAR(600),
    raw_object_key    VARCHAR(1200),
    classified_type   VARCHAR(50),
    classifier_version VARCHAR(50),
    state             VARCHAR(40) NOT NULL,
    received_at       TIMESTAMP WITH TIME ZONE,
    ingested_at       TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

PostgreSQL partial unique indexes example:

~~~sql
CREATE UNIQUE INDEX uq_mail_inbox_imap
ON mail_inbox (
    tenant_id, mailbox_id, folder_id,
    uid_validity, imap_uid
)
WHERE imap_uid IS NOT NULL;

CREATE UNIQUE INDEX uq_mail_inbox_pop3
ON mail_inbox (tenant_id, mailbox_id, pop3_uidl)
WHERE pop3_uidl IS NOT NULL;
~~~

This is an **illustrative schema**. In practice, validate required protocol identity fields so multiple records with null UIDs cannot be inserted, and add separate work item/attempt tables for complex workflows.

### Transaction Boundary

The database commit **does not commit atomically with the IMAP/POP3 server**. When persisted to the inbox successfully before marking the message on the server, the next poll may still see the message. This is acceptable behavior when deduplication works properly.

Thus, the realistic goal is **at-least-once ingestion + idempotent processing**, not "every email is received strictly once" from Spring Integration alone.

## 30. IMAP UID, UIDVALIDITY, and Routing Checkpoints

An IMAP **message sequence number** can shift when other messages are deleted/expunged. For durable identification and checkpointing:

~~~text
mailbox = support-A
folder = INBOX
UIDVALIDITY = 91320
UID = 4221
~~~

A UID is only meaningful within the same mailbox and the same `UIDVALIDITY` generation. When `UIDVALIDITY` changes, resynchronize using appropriate deduplication.

Typical checkpoint bug:

~~~text
UID 100 -> routed successfully
UID 101 -> inbox save error
UID 102 -> routed successfully

lastUID = 102
~~~

UID 101 could be skipped forever if the worker only queries UIDs greater than `lastUID` on the next run.

Safer approaches:

- Only advance a **contiguous checkpoint** after every previously seen UID is durably persisted; or
- Store per-UID/inbox record state, leaving UID 101 in `RETRY` while the discovery cursor advances conditionally.

**Do not use the IMAP Seen flag as proof an email was processed**, because other users may read the message, clients can flip flags, and `Seen` does not synchronize with business DB commits.

## 31. POP3 UIDL and Routing

With POP3, many servers support **UIDL** to identify emails in a maildrop. A typical identity:

~~~text
(mailboxId, uidl)
~~~

Do not use **POP3 message number** as a durable key: sequence numbers shift when messages are deleted.

If a POP3 server does not support stable UIDL:

- Define a fallback deduplication policy using a hash/raw bytes or metadata tuple.
- Document the confidence level and scope of the fingerprint.
- Never rely solely on Subject + From (two distinct emails can share them).
- Never delete emails from the server before data is durably persisted.

Spring Integration Mail helps receive messages, yet does not solve every mailbox identity rule on its own. That must be designed around the receiving adapters and inbox store.

## 32. State Machine for Emails After Receipt

An illustrative state machine:

~~~text
DISCOVERED
    |
    v
PERSISTED
    |
    v
CLASSIFYING
    |
    +-- invalid MIME --> QUARANTINED
    +-- insufficient evidence --> NEEDS_TRIAGE
    |
    v
CLASSIFIED
    |
    v
ROUTED
    |
    v
PROCESSING
    |
    +-- transient failure --> RETRY_WAIT
    +-- permanent policy rejection --> QUARANTINED
    |
    v
PROCESSED
~~~

The **ROUTED** state does not equal **PROCESSED**. A message delivered to a channel whose handler fails still needs retries or an investigable failure state.

### State and Retries by Email Type

| Type | When Retries May Fit | Side Effect to Guard |
|---|---|---|
| SUPPORT_REQUEST | Temporary ticket API/database failure | Avoid duplicate tickets |
| SUPPORT_REPLY | Ticket service unavailable | Avoid duplicate comments |
| INVOICE | Temporary storage/validation service failure | Avoid ingesting duplicate invoices |
| DELIVERY_REPORT | Temporary delivery-status DB failure | Avoid updating bounce twice |
| SYSTEM_ALERT | Temporary incident platform failure | Avoid opening duplicate incidents |
| UNKNOWN | Reclassification after policy fix | Never lose raw email or cause processing loops |

Do not infinitely retry malformed MIME or untrusted senders. Moving to quarantine can be the right outcome and should be monitored.

## 33. Error Channel vs. Unknown Channel

Two concepts easily confused:

The **Unknown channel** handles **messages successfully received and parsed that match no business route**.

The **Error channel** handles **exceptions inside the integration pipeline** per each endpoint/channel's error-handling configuration.

Example:

~~~text
Valid email that matches no rule
     -> mailUnknownChannel

MIME parser throws MessagingException
     -> error handling / mail quarantine

Invoice handler throws DatabaseUnavailable
     -> retry/error handling

Router returns wrong channel name
     -> routing/channel resolution error
~~~

Do not catch every exception and assign `EmailType.UNKNOWN`:

~~~java
try {
    return classifier.classify(email);
} catch (Exception exception) {
    return EmailType.UNKNOWN;  // hides code/infrastructure error
}
~~~

A database disconnection error does not mean the email is of type `UNKNOWN`. Preserve the **error category** and `RETRY` state for transient failures.

### Does ErrorChannel Work Automatically?

Spring Integration provides **ErrorMessage** and error channel mechanisms, yet how an exception reaches an error channel depends on the **endpoint, poller, thread boundary, and error-handling configuration**. With a **synchronous DirectChannel**, exceptions can propagate back to the caller; with a poller/executor, errors can be wrapped into an `ErrorMessage` sent to a configured error channel.

Do not assume simply creating a bean named **errorChannel** guarantees every exception from every flow is durably handled. Verify the actual endpoint contract and ensure inbox items are never marked `PROCESSED` when a handler fails.

## 34. Classifying Errors for Proper Retries

| Error Group | Example | Response |
|---|---|---|
| **Mail server/network** | IMAP disconnect, read timeout | Reconnect/reconcile UID/UIDL |
| **Authentication** | Token revoked, expired credentials | Refresh/re-authorize, alert |
| **Malformed MIME** | Unparseable structure | Quarantine, do not hot-retry |
| **Unsafe content** | Malware attachment, malicious HTML | Quarantine, never route to business handler |
| **Classification ambiguous** | Multiple rules unresolved | UNKNOWN/triage |
| **Business downstream** | Ticket service/DB unavailable | Retry from durable inbox |
| **Routing misconfiguration** | Target channel does not exist | Alert on deployment/config error |
| **Authorization** | Tenant mismatch, insufficient permission | Reject/quarantine, audit |

Do not keep an IMAP session open while retrying a business API. Persist MIME/metadata first and let business workers retry independently.

## 35. Queues and Channels: Choosing by Guarantee Requirements

Spring Integration has several channel types, and they are not equivalent:

| Option | Characteristics | When Appropriate |
|---|---|---|
| **DirectChannel** | Invokes subscriber on current thread | Short, synchronous pipelines |
| **ExecutorChannel** | Dispatches via TaskExecutor | Decouples threads, increases concurrency; not durable |
| **QueueChannel** | Buffers messages for polling consumer | Buffering; default does not survive crashes |
| **PublishSubscribeChannel** | Broadcasts to multiple subscribers | Intentional fan-out |
| **Broker-backed channel** | External queue/topic | Decouples services, durable per broker config |
| **Inbox DB + worker** | Stores message state in database | Audit, retry, idempotency, transaction control |

For messages with attachments or large bodies, do not hold connection-bound **MimeMessage** objects inside in-memory queues for long. Persist raw EML/attachments and pass **inboxId/metadata** to consumers.

### Do Not Treat a Message Leaving a Channel as Business Commit

Moving a message from channel A to channel B is purely a messaging operation. If a handler updates a database and emits events, manage transactions, outboxes, and idempotency explicitly.

## 36. Backpressure and Isolation by Email Type

Suppose a mailbox receives 10,000 invoices and only 10 support replies:

~~~text
10,000 INVOICE messages
10 SUPPORT_REPLY messages
~~~

If everything is processed synchronously in arrival order, ticket replies could wait hours even though the ticket handler is fast.

One design:

~~~text
mailRawChannel
     |
     v
Classifier
     |
     +--> Invoice queue   -> 4 document workers
     |
     +--> Support queue   -> 2 ticket workers
     |
     +--> Delivery queue  -> 2 DSN workers
     |
     +--> Unknown queue   -> bounded triage
~~~

Required:

- **Quotas/in-flight caps** per type and tenant.
- **Bounded queues** to avoid unbounded RAM growth or backlogs.
- Separate **retry budgets**; one failing email type must not starve all workers.
- **Oldest due age** and SLAs per channel/stream.
- **Expired jobs** policy so stale OTP emails are not processed automatically.

Using a single **ExecutorChannel** with an unbounded thread pool is not a sustainable performance solution.

## 37. Standardizing Metadata for Observability and Tracing

Once an email enters the application, it should carry traceable internal metadata:

~~~text
inboxId:        INB-1001
tenantId:       tenant-A
mailboxId:      support-primary
sourceProtocol: imaps
mailIdentity:   UIDVALIDITY=903, UID=1045
classifier:     email-type-v3
emailType:      SUPPORT_REPLY
routeChannel:   mailSupportReplyChannel
state:          PROCESSING
attempt:        2
traceId:        7d0c...
~~~

This metadata supports:

- Checking which channel an email routed to.
- Diagnosing why routing produced `UNKNOWN`.
- Distinguishing retries of the same inbox item from a new email.
- Investigating when the same `Message-ID` appears in two mailboxes.
- Knowing which classifier version decided the type.
- Measuring latency from mailbox arrival to business completion.

### Spring Message Header or Domain Record?

Some metadata can go into **Spring MessageHeaders** for correlation/observability, under strict control:

- **MessageHeaders** created by Spring Integration differ from email MIME headers.
- Do not promote arbitrary sender-supplied fields into trusted metadata.
- Store only necessary fields; never copy raw bodies/attachments into headers.
- Across brokers, header serialization and mapping may change.
- The source of truth for inbox processing is a durable database/ledger, not in-memory headers.

## 38. Recording Metrics by Email Type Without Leaking Data

A routing dashboard should answer:

| Logical Metric | Meaning |
|---|---|
| **mail.inbound.discovered** | Number of message identities observed |
| **mail.inbound.persisted** | Number of unique inbox items saved |
| **mail.inbound.classified** | Emails classified per type |
| **mail.inbound.routed** | Messages forwarded to target channels |
| **mail.inbound.routing.errors** | Channel selection/resolution failures |
| **mail.inbound.unknown** | Emails requiring triage |
| **mail.inbound.processing** | Processed counts by type and result |
| **mail.inbound.queue.age** | Age of unfinished items per type |
| **mail.inbound.reclassified** | Reclassified email count |
| **mail.inbound.duplicates** | Duplicates filtered by deduplication |

Bounded labels to use:

~~~text
email_type=INVOICE|SUPPORT_REQUEST|SUPPORT_REPLY|...
result=success|failed|retry|quarantined
stream=inbound-support|inbound-finance|...
error_category=parser|auth|routing|downstream|...
~~~

**Never put** Subject, email address, Message-ID, specific UID, attachment filename, or `inboxId` into **Prometheus metric labels**, as that causes high cardinality and leaks personal data.

Micrometer example:

~~~java
import io.micrometer.core.instrument.MeterRegistry;

public final class MailRoutingMetrics {

    private final MeterRegistry registry;

    public MailRoutingMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void routed(EmailType type) {
        registry.counter(
                "mail.inbound.routed",
                "email_type", type.name()
        ).increment();
    }
}
~~~

If you need to know how many emails **completed processing successfully**, add a separate metric or `result=processed` at the handler boundary. The **routed** counter cannot substitute for **processed**.

### When to Increment the Counter?

If incremented before `channel.send` succeeds, an exception can inflate "routed" even when dispatch failed. Define exact semantics:

- **routing_decision_total**: classifier/router picked a channel.
- **routing_dispatched_total**: dispatch to channel succeeded.
- **processing_completed_total**: handler confirmed business completion.

Counters only aid observation; they do not share a transaction with the database. For exact accounting of inbox items, query the durable status table.

## 39. Detecting Rule Regressions and Classification Ratio Shifts

Example after deploying a classifier update:

~~~text
Before deploy:
  SUPPORT_REQUEST  50%
  SUPPORT_REPLY    30%
  INVOICE          15%
  UNKNOWN           5%

After deploy:
  SUPPORT_REQUEST  10%
  SUPPORT_REPLY     5%
  INVOICE          15%
  UNKNOWN          70%
~~~

Total volume may be unchanged, yet a spike in `UNKNOWN` signals a **rule regression, parser bug, email schema shift, or missing correlation data**.

Monitor:

- Email type distribution over time.
- `UNKNOWN`/`AMBIGUOUS` ratio and reason codes.
- Parser error ratio.
- Ratio of ticket replies failing correlation.
- Invoice validation rejection rate by reason group.
- Ratio of delivery reports failing notification correlation.
- Age of the triage queue.

Do not fire alerts on percentage swings when sample sizes are tiny. Apply **time windows, minimum volume thresholds, and baselines** tailored to each stream.

## 40. Tagging Classifier Version and Reclassification

When classification rules change, emails sitting in `UNKNOWN` can be reclassified:

~~~text
Inbox item INB-1001
  raw EML persisted
  classifier_version=v2
  type=UNKNOWN
  reason=UNRECOGNIZED_INVOICE_FORMAT
       |
       | deploy classifier v3
       v
  reclassify (controlled)
       |
       v
  type=INVOICE
  route to invoice workflow
~~~

Ensure:

1. Reclassify only **eligible items**, never arbitrarily re-running already `PROCESSED` emails.
2. Record **previous type, new type, classifier version, and timestamp** for audit.
3. Preserve the **same inboxId** without creating a new inbound email.
4. Re-check tenant/sender authorization under current policy.
5. Do not trigger duplicate side effects if an email was partially processed.
6. Rate-limit bulk reclassification so it does not starve production workers.

Reclassification does not require mutating raw data. If raw EML is persisted, **keep the original message immutable** and store classifier output as versioned metadata.

## 41. Unit Testing the Classifier Without an SMTP Server

Because the classifier only takes normalized signals, it can be tested as a pure function:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class DefaultEmailClassifierTest {

    private final DefaultEmailClassifier classifier =
            new DefaultEmailClassifier();

    @Test
    void routesCorrelatedDsnToDeliveryReport() {
        ClassificationSignals signals = new ClassificationSignals(
                false, // suspiciousOrMalformed
                true,  // correlatedDeliveryReport
                false, // authorizedTicketReply
                false, // trustedInvoiceSource
                false, // validatedInvoiceAttachment
                false, // authenticatedSystemAlert
                false  // eligibleSupportRequest
        );

        assertEquals(
                EmailType.DELIVERY_REPORT,
                classifier.classify(signals)
        );
    }

    @Test
    void doesNotTreatPdfAsInvoiceWithoutTrustedSource() {
        ClassificationSignals signals = new ClassificationSignals(
                false,
                false,
                false,
                false, // unverified source
                true,  // syntactically valid PDF/attachment
                false,
                false
        );

        assertEquals(
                EmailType.UNKNOWN,
                classifier.classify(signals)
        );
    }

    @Test
    void suspiciousMessageGoesToUnknown() {
        ClassificationSignals signals = new ClassificationSignals(
                true,  // suspiciousOrMalformed
                true,  // looks like a DSN
                false,
                false,
                false,
                false,
                false
        );

        assertEquals(
                EmailType.UNKNOWN,
                classifier.classify(signals)
        );
    }
}
~~~

These tests verify **classification policy** without needing a Spring `ApplicationContext`, IMAP server, or SMTP. They assume signals were already verified upstream, so test **signal extraction and verification** from MIME/headers separately.

### Cases to Add

- Email missing Subject.
- Blank or duplicate Message-ID.
- Reply with "Re:" that matches no ticket.
- Delivery report without notification correlation.
- Invoice from a trusted source whose attachment fails policy.
- Alert with Subject CRITICAL whose source is unauthenticated.
- Two rules matching simultaneously; classifier picks precedence or `AMBIGUOUS` per contract.
- Email with multiple recipients and distinct tenant permissions.
- Malformed MIME and oversized payloads.

## 42. Unit Testing That the Router Picks the Right Channel

With `@Router`, channel selection logic can be extracted into a pure function:

~~~java
public final class EmailChannelMapping {

    public String channelFor(EmailType type) {
        return switch (type) {
            case DELIVERY_REPORT -> "mailDeliveryReportChannel";
            case SUPPORT_REPLY -> "mailSupportReplyChannel";
            case SUPPORT_REQUEST -> "mailSupportRequestChannel";
            case INVOICE -> "mailInvoiceChannel";
            case SYSTEM_ALERT -> "mailSystemAlertChannel";
            case UNKNOWN -> "mailUnknownChannel";
        };
    }
}
~~~

The router can delegate to this service:

~~~java
@Router(inputChannel = "mailClassifiedChannel")
public String route(InboundEmail email) {
    return channelMapping.channelFor(email.type());
}
~~~

Unit test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class EmailChannelMappingTest {

    private final EmailChannelMapping mapping =
            new EmailChannelMapping();

    @Test
    void mapsInvoiceToInvoiceChannel() {
        assertEquals(
                "mailInvoiceChannel",
                mapping.channelFor(EmailType.INVOICE)
        );
    }

    @Test
    void mapsUnknownToTriageChannel() {
        assertEquals(
                "mailUnknownChannel",
                mapping.channelFor(EmailType.UNKNOWN)
        );
    }
}
~~~

This tests the routing decision, not whether Spring Integration actually delivers messages to the channel bean. That part needs a separate **integration test**.

## 43. Integration Testing Router and Handler Without Real IMAP

To verify annotations/DSL wire the right channels, start a Spring test context with the channels and handlers, then **send a normalized InboundEmail** into `mailClassifiedChannel`.

Architecture:

~~~text
JUnit + Spring Integration test context
       |
       v
send InboundEmail(type=INVOICE)
       |
       v
mailClassifiedChannel
       |
       v
Router
       |
       v
mailInvoiceChannel
       |
       v
Test handler / mock InvoiceService
       |
       v
verify exactly one invoice processing call
~~~

Assertions to include:

- Invoice reaches the invoice handler, not ticket/DSN.
- `DELIVERY_REPORT` reaches the delivery handler.
- `UNKNOWN` is quarantined or recorded for triage.
- If the handler throws an error, the inbox item is **not marked PROCESSED**.
- No undeclared channel names or missing subscribers exist.
- Once a message is deduplicated, re-sending causes no second side effect.

When testing multiple types, use fixtures with distinct addresses/subjects/tenants so you do not accidentally assert against the wrong message.

### Testing with @SpringIntegrationTest

Spring Integration provides test support for flows, channels, and endpoint mocks in its test module. Annotation names, test context setup, and endpoint replacement depend on the library version. Only add them when verifying real wiring/dispatch; pure unit tests for classifiers/route mappings do not need to boot the full context.

## 44. End-to-End Testing with an IMAP/POP3 Test Server

To test from mailbox to handler, use a **test mail server** supporting SMTP to receive messages and IMAP/POP3 for clients to read them.

Example architecture:

~~~text
JUnit
   |
   +-- Start test SMTP + IMAP/POP3 server
   |
   +-- Deliver test MIME messages:
   |     1 support reply
   |     1 invoice with PDF
   |     1 DSN delivery report
   |     1 unknown email
   |
   v
Spring Integration Mail inbound adapter
   |
   v
Normalizer + classifier + router
   |
   +-- Ticket store
   +-- Invoice store
   +-- Delivery status store
   +-- Triage store
   |
   v
Assert each message reaches one correct workflow
~~~

You can use a **Jakarta Mail-compatible version of GreenMail**, a containerized server, or another test harness matching project infrastructure.

Items to verify at this layer:

- The receiver actually reads emails from the mailbox.
- Payload type and MIME content match what the normalizer expects.
- IMAP `UID`/`UIDVALIDITY` or POP3 `UIDL` is stored accurately.
- A second poll/reconnect does not trigger duplicate side effects.
- Mailbox A is never tagged with mailbox B's `tenantId`.
- MIME with attachments/DSN is classified accurately.
- Unmatched emails go to `UNKNOWN` rather than vanishing.
- Connections and test mailboxes are cleaned up after each test.

Never use personal mailboxes or production SMTP merely to test routing; test data must be synthetic and isolated.

## 45. Runbook: Email Arrives in Inbox but Does Not Reach Handler

When an email appears in the mailbox without creating a ticket/invoice/delivery update, investigate layer by layer:

### Step 1 — Verify the Receiver

- Are the mailbox and folder configured correctly?
- Do IMAP/POP3 connect and authenticate successfully?
- Is the poller running, or has IMAP IDLE reconnected after disconnect?
- Have connection limits or provider throttles been hit?
- Was the email filtered out before entering `mailRawChannel`?

### Step 2 — Verify Inbox Persistence

- Is there a record for the `UID`/`UIDVALIDITY` or `UIDL`?
- Did a unique key cause the message to be treated as a duplicate?
- Were raw EML/attachments persisted safely?
- Did the checkpoint advance before commit?
- Is the inbox item sitting in `PERSISTED`, `CLASSIFIED`, or `RETRY_WAIT`?

### Step 3 — Verify Classification

- Which classifier version is running?
- What is the `EmailType`?
- Which sources verified the routing signals?
- Was the email marked `UNKNOWN` due to missing correlation, missing attachment, or untrusted source?
- Are there parser errors with MIME multipart/charsets?

### Step 4 — Verify Routing

- Does the target channel exist with the exact name?
- Is there a subscriber/`ServiceActivator` on that channel?
- Were both `@Router` and a DSL router accidentally configured competing on the same input channel?
- Did a filter or header mapping strip required metadata?
- Was an exception routed to `errorChannel` or propagated back to the poller?

### Step 5 — Verify the Handler

- Which `inboxId` did the handler receive?
- Is there a pending retry or dead-letter/quarantine entry?
- Are downstream databases/APIs available?
- Did an idempotency key skip processing because business work already completed?
- Did a transaction roll back or state update fail after a side effect?

### Step 6 — Controlled Recovery

If the email is already persisted, prefer **replaying from the inbox record** under its idempotency key. Never wipe/re-download the whole mailbox or push an unverified raw payload straight into a business handler as a "quick fix".

## 46. Runbook: Sudden Spike in UNKNOWN Ratio

An abnormally high `UNKNOWN` chart can result from:

- Changes to a partner's domain/email format.
- Mailbox folder or provider filter rule changes.
- A buggy classifier release or changed rule precedence.
- Ticket/notification correlation system temporarily unavailable.
- MIME parser failing on a new charset/attachment format.
- Changes in `Authentication-Results` or trusted metadata from the mail gateway.
- An unusual spam campaign.

Procedure:

1. Identify start time, affected mailbox, tenant, and email type.
2. Compare **reason code distribution**, not just total `UNKNOWN`.
3. Inspect a few **authorized** inbox samples in a secure investigation environment.
4. Separate **no matching rule** from **parser/database exceptions**; their root causes differ.
5. Check recent deployments/provider changes near the onset time.
6. If caused by a missing rule, update the classifier and replay eligible items in a controlled way.
7. If caused by malicious email, tighten quarantine/rate limits and protect the system without relaxing source verification.
8. Check prior side effects to avoid duplicates during reprocessing.

Do not turn all `UNKNOWN` into `SUPPORT_REQUEST` just to make dashboards look "cleaner". That can feed spam, spoofed DSNs, or invalid documents into business workflows.

## 47. Runbook: Emails Processed Multiple Times

Common causes:

~~~text
Poll/reconnect -> same message fetched again
       |
       +-- Missing unique inbox identity
       +-- Wrong IMAP UIDVALIDITY checkpoint
       +-- POP3 UIDL not persisted
       +-- Mark Seen failed then retried
       +-- Two pods reading the same mailbox
       +-- Router re-dispatches on downstream error
       +-- Non-idempotent handler
~~~

Steps:

1. Determine whether two records share the same **mailbox identity** or are genuinely two separate emails.
2. Inspect **inboxId, UID/UIDVALIDITY/UIDL, Message-ID, and raw MIME hash** within the proper scope.
3. Check the unique constraint and transaction of the inbox write step.
4. Check worker claim/lease behavior and active poller count.
5. Check whether the handler is idempotent by `inboxId` and business key.
6. If an email was partially processed, retry only unfinished steps based on durable state.
7. Fix checkpoints/reconciliation rather than automatically deleting all read messages.

In particular, achieving an **exactly-once effect** on operations with external side effects requires idempotency in the target service or reconciliation; a router and outbox alone are not enough.

## 48. Common Anti-Patterns When Routing Emails

| Anti-Pattern | Consequence | Alternative |
|---|---|---|
| Classifying DSN solely by Subject | Spoofed DSN enters delivery handler | Parse structured DSN and correlate |
| Deciding invoice based on `.pdf` attachment | Arbitrary files enter invoice workflow | Verify source and content |
| Using From as proof of ticket permission | Spoofed sender modifies others' tickets | Verify correlation and authorization |
| Using MIME Content-Type as EmailType | Mixed emails hold multiple business types | Classifier with a business model |
| Copying `X-Email-Type` as a trusted routing header | Senders control the router | Internal header created only after verification |
| Building dynamic channel names from input | Broken topology or unintended flow access | Enum/allowlist channel mapping |
| Missing default UNKNOWN route | Unmatched emails drop or throw unhandled exceptions | Explicit triage/quarantine |
| Catching all exceptions as UNKNOWN | Hides DB, parser, and config failures | Separate business unknown from technical errors |
| One giant handler with many if/elses | Hard to test, broad blast radius | Dedicated classifier, router, handlers |
| Using Seen flag as processed state | Lost mail or misprocessing when users read mail | Separate durable inbox state |
| Using IMAP sequence number as unique key | Numbers shift on expunge | `UIDVALIDITY` + `UID` |
| No deduplication before side effects | Duplicate tickets/invoices | Unique inbox key and idempotent handlers |
| Treating DirectChannel as a durable queue | Work lost on crash | Durable inbox DB/broker |
| Treating routing success as business complete | No retry when handler fails | State machine and commit boundary |
| Keeping Folder-bound MimeMessage in async queue | Folder closed errors, memory/network leaks | Persist raw EML and pass `inboxId` |
| One unbounded executor for all types | Invoice spikes lag support replies | Bounded queues and per-type capacity |
| Logging raw MIME for debugging | Exposes PII/attachments/tokens | Metadata/redacted logs |
| Unit tests only verifying router method called | Unknown if channel has proper subscriber | Channel/flow integration tests |
| Enabling both annotation and DSL router on one channel | Competing subscriptions/unclear dispatch | Choose one deliberate topology |
| Retrying entire flow regardless of side effects | Handler re-runs already succeeded parts | Idempotent workflow + stateful retry |

## 49. Design for Clarity Before Optimization

A small application with only two email types can start with:

~~~text
IMAP poller -> normalize -> classify -> @Router
                                |
                  +-------------+------------+
                  |                          |
                  v                          v
                SUPPORT                    UNKNOWN
                  |                          |
                  v                          v
                Ticket                    Triage
~~~

When invoices, bounces, multiple tenants, or strict SLAs are added, you can evolve to:

~~~text
Mailbox poller
     |
     v
Durable inbox
     |
     v
Classification worker
     |
     v
Typed message broker / work queues
     |
     +-- Ticket worker group
     +-- Invoice worker group
     +-- Delivery worker group
     +-- Triage worker group
~~~

You do not need a broker from day one if a database inbox and workers handle the load. However, when one mail type runs heavy tasks like OCR/virus scanning, isolate its worker resource budget so it does not stall the entire inbound flow.

### When Should You Avoid Routing by Email?

If a partner or provider offers a **reliable, metadata-rich webhook/API** for events or files, that is often better than IMAP/POP3:

- Bounce/delivery events from an ESP with event IDs and cryptographic signatures.
- Partner invoices via an authenticated API.
- System alerts via a webhook with a strict schema.
- Ticket updates through an integrated support platform.

Email routing may still be needed for partners lacking APIs, but never assume it is the safest integration channel for every sensitive data flow.

## 50. End-to-End Example: From Mailbox to a Ticket Reply

Suppose a customer replies to a support email:

~~~text
Message:
  From: customer@example.net
  To: support@example.com
  Subject: Re: Ticket 123
  In-Reply-To: <support-outbound-123@service.example>
  Content-Type: multipart/alternative
~~~

Processing flow:

1. **IMAP receiver** reads the message at its resolved UID.
2. **Inbox writer** stores the raw EML under controlled access and identity by `mailbox+UIDVALIDITY+UID`, generating `inboxId` **INB-1001**.
3. **Normalizer** extracts headers and plain text/HTML (within MIME limits).
4. **Correlation service** matches `In-Reply-To` against ticket 123 and verifies sender authorization.
5. **Classifier** returns **SUPPORT_REPLY**, recording the classifier version.
6. **Spring Integration @Router** selects **mailSupportReplyChannel**.
7. **TicketService** appends the reply with idempotency key **INB-1001** and commits the database.
8. **Inbox status** transitions to **PROCESSED**.
9. If needed, the application can mark Seen/move the mail only after persisting and processing per policy.

If the service fails at step 7, the item enters `RETRY_WAIT`. When retrying from the inbox, there is no need to re-download the `MimeMessage` from the mail server. If the ticket API already saved the reply before the response was lost, the idempotency key prevents creating a duplicate reply.

### What If the Reply Is Unauthenticated?

Suppose **In-Reply-To** matches ticket 123 yet the sender lacks authorization. The classifier must not set **authorizedTicketReply=true**. Per policy, the email goes to **UNKNOWN/triage** or a separate verification workflow instead of automatically appending a comment to the ticket.

## 51. Implementation Checklist for Routing by Email Type

**Classification and Topology**

1. Have all business **EmailType** values to handle been enumerated?
2. Is there a clear precedence order or conflict-resolution policy?
3. Is there an **UNKNOWN/AMBIGUOUS** fallback?
4. Does the router map each enum value to a channel with a subscriber?
5. Have you chosen either `@Router` or a DSL router, avoiding accidental competing registrations?
6. Are classifier, router, and handlers separated for independent testing?

**Security and Data**

7. Do mailbox/tenant identities come from a trusted source?
8. Are MIME headers kept distinct from Spring Message headers?
9. Are sources/correlations verified before routing sensitive emails?
10. Are HTML/attachments bounded and sanitized/scanned appropriately?
11. Is one tenant prevented from using another tenant's routing rules/channels?
12. Is there a policy against logging raw EML, credentials, and PII?

**Reliability and Recovery**

13. Is there an inbox identity using IMAP `UID+UIDVALIDITY` or POP3 `UIDL`?
14. Is there a unique constraint preventing duplicate processing?
15. Are emails persisted before marking/deleting on the server?
16. Can retries run from inbox records without re-fetching the mailbox?
17. Are handlers idempotent with explicit state transitions?
18. Are error channels, retries, dead-letter, and quarantine clearly separated?
19. Is there reconciliation on process crashes or IMAP reconnects?

**Performance and Operations**

20. Are there limits on emails/attachments parsed per batch?
21. Is capacity isolated across invoice, support, delivery, and triage when needed?
22. Do queues/backlogs enforce bounded policies?
23. Are `UNKNOWN` ratio, route errors, processing age, and duplicates measured?
24. Is there a controlled way to reclassify unprocessed emails when rules change?
25. Have classifier unit tests, routing integration tests, and mailbox end-to-end tests been written?

A checklist is a design tool, not proof that installing Spring Integration Mail automatically grants all these guarantees.

## 52. Takeaways

**Routing messages by email type** in Spring Integration Mail is the process of turning a mailbox email into a classified internal message and dispatching it to the right handler:

~~~text
IMAP/POP3 -> Normalize/Persist -> Classify -> Router
                                         |
                      +------------------+-------------------+
                      |                  |                   |
                    Ticket             Invoice             Delivery
                      |                  |                   |
                      +------------------+-------------------+
                                         |
                                         v
                                Business state / audit
~~~

Key takeaways:

- **EmailType** is a business type; do not equate it with **MIME Content-Type** or Java payload classes.
- **Transformers/classifiers** determine types from normalized data and trustworthy evidence; **Routers** map types to channels.
- **@Router**, Java DSL routers, `HeaderValueRouter`, and `ServiceActivator` are Spring Integration tools that work together, requiring a consistent topology and contract.
- **UNKNOWN/triage** is a mandatory design branch for emails with insufficient signals; technical exceptions require their own error/retry flow.
- **IMAP Seen, UID, POP3 UIDL, and Message-ID** serve different roles; idempotency requires a mailbox-scoped identifier and durable processing state.
- **Successful routing is not successful processing.** Handlers need idempotency, proper transactions, retries, and quarantine.
- **External emails are untrusted**: From, Subject, MIME headers, attachments, and custom headers never grant workflow permissions on their own.
- **Measure outcomes** using classified/routed/processed counters, `UNKNOWN` reason codes, queue age, and layered tests.

**A well-designed inbound email system does more than tell "this is an invoice vs. a support email"—it proves why that branch was chosen, preserves emails on failure, and prevents untrusted data from triggering the wrong business workflow.**





