# MailSendingMessageHandler in Spring Integration Mail

**MailSendingMessageHandler** is a key component of **Spring Integration Mail** when an application wants to send emails as a step inside a message-processing flow rather than calling `JavaMailSender` directly from every business service. This handler acts as an **outbound channel adapter**: it receives a Spring Integration message at its input, translates the email content appropriately for the mail sender, and triggers sending through the configured transport.

In an application with only one email type, calling `JavaMailSender.send(...)` directly may suffice. However, when a system has multiple event sources, transform, filter, route, retry, error handling, telemetry, or worker-based processing steps, placing email sending at the end of an integration flow helps **decouple orchestration from SMTP transport**.

This lesson explains `MailSendingMessageHandler` in detail within the context of **Spring Framework Mail** and **Spring Integration Mail**: its place in the architecture, input messages, bean configuration, building `SimpleMailMessage`/`MimeMessage`, synchronous vs. asynchronous boundaries, exception handling, outboxes, testing, observability, security, and common mistakes.

One guiding principle throughout: **MailSendingMessageHandler submits emails; it does not guarantee that the email reached the inbox or was read by the recipient.** A successful handler invocation only indicates that the synchronous send operation finished according to the corresponding `JavaMailSender`/transport contract.

## 1. What Problem Does MailSendingMessageHandler Solve?

A processing flow may look like:

~~~text
Order confirmed / Password reset / Report ready
                      |
                      v
             Application event
                      |
                      v
             MessageChannel
                      |
                      v
       Transform / Filter / Enrich / Route
                      |
                      v
         MailSendingMessageHandler
                      |
                      v
                JavaMailSender
                      |
                      v
                  SMTP relay
~~~

In this model:

- **Producer**: the component that creates the email send request.
- **Message**: the object pushed into Spring Messaging/Integration, carrying payload and headers.
- **MessageChannel**: the channel transporting messages between components.
- **Transformer**: converts business data into a mail payload understood by the handler.
- **MailSendingMessageHandler**: the endpoint consuming messages at the end of the outbound flow.
- **JavaMailSender**: the Spring Framework Mail abstraction responsible for creating/sending MIME messages.
- **SMTP relay/provider**: the system receiving SMTP commands and continuing email processing.

This component belongs to **Spring Integration**, whereas `JavaMailSender` and `SimpleMailMessage` belong to **Spring Framework Mail**. Using both libraries together brings mail sending into the Enterprise Integration Patterns model.

### 1.1. Why Not Call sender.send(...) Everywhere?

If controllers, event listeners, batch jobs, and workers all instantiate `JavaMailSender` or call send independently, code easily runs into:

- Inconsistent From/Reply-To formatting.
- Duplicated template and attachment logic.
- Divergent retry rules.
- No unified place to record metrics/traces.
- Difficulty blocking ineligible events.
- Difficulty swapping providers or routing by email type.
- Difficulty testing the end-to-end flow without opening real SMTP.

An integration flow standardizes the steps while allowing the transport to be replaced with a mock/test double.

### 1.2. The Handler Does Not Replace the Business Layer

`MailSendingMessageHandler` does not decide on its own which orders must be emailed, whether a recipient is permitted to receive mail, whether a token has expired, or whether an outbox job has already been processed. Those must be resolved upstream in the appropriate service/filter/policy.

## 2. Where Does the Handler Sit in Spring Integration?

Spring Integration uses several abstractions:

| Component | Role |
| --- | --- |
| **Message<?>** | Payload and headers |
| **MessageChannel** | Communication between endpoints |
| **DirectChannel** | Invokes subscriber synchronously on the sending thread |
| **ExecutorChannel** | Dispatches via an executor, potentially asynchronously |
| **QueueChannel** | Buffers messages in an in-memory queue per configuration |
| **Transformer** | Converts a business DTO into a mail payload |
| **Filter** | Drops/blocks invalid messages per policy |
| **Router** | Selects the next channel |
| **Service activator** | Invokes logic to process a message |
| **Outbound channel adapter** | Sends data to an external system; typically has no reply |
| **MailSendingMessageHandler** | MessageHandler that performs outbound mail sending |

`MailSendingMessageHandler` is essentially a **MessageHandler** used at an outbound endpoint.

### 2.1. Data Diagram

~~~text
Message<OrderMailCommand>
        |
        v
Validate command
        |
        v
Message<SimpleMailMessage>
        |
        v
DirectChannel
        |
        v
MailSendingMessageHandler
        |
        v
JavaMailSender
~~~

For emails needing HTML or attachments, the payload can be built into a **MimeMessage** before entering the handler.

### 2.2. One-Way, Not Request-Reply

When used as an outbound channel adapter, the handler's job is to execute the email-sending side effect. Do not expect a **reply Message** containing a delivery receipt or SMTP provider message ID to be returned in a request-reply flow.

If business logic needs a status result, manage state in an outbox, event store, or dedicated service wrapper.

### 2.3. MessageChannel Does Not Guarantee Durability on Its Own

A message sent through `DirectChannel` or `ExecutorChannel` does not automatically become a durably persisted job. If recovery after a process crash is required, combine it with an outbox or a durable message broker/queue with proper ack/retry mechanics.

## 3. Required Dependencies

When using Spring Boot with compatible dependency version management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.integration:spring-integration-mail'
}
~~~

Spring Integration Mail usually brings in the required Spring Integration dependencies. In projects with custom dependency management, ensure compatible Spring Framework, Spring Integration, and Jakarta Mail versions.

### 3.1. Spring Framework Mail vs. Spring Integration Mail

- **spring-boot-starter-mail**: provides `JavaMailSender`/Jakarta Mail configuration based on auto-configuration conditions.
- **spring-integration-mail**: provides mail integration components, including mail-related endpoints and outbound handlers.

Adding `starter-mail` **does not automatically create an integration flow**. The application still has to declare channels, endpoints/handlers, and processing flows.

### 3.2. Jakarta Mail and javax.mail

In the **Spring Framework 6 / Spring Integration 6 / Spring Boot 3** ecosystem, mail APIs use the **jakarta.mail** namespace. Legacy projects using **javax.mail** may need import updates during upgrades.

Do not randomly mix `javax.mail.internet.MimeMessage` with the Jakarta Mail API of a newer library suite; type errors can occur right at compile time.

### 3.3. Do Not Guess Packages by Name

Spring Integration's handler class is used with its full name:

~~~java
import org.springframework.integration.mail.MailSendingMessageHandler;
~~~

Commonly used related classes:

~~~java
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.SimpleMailMessage;
import jakarta.mail.internet.MimeMessage;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
~~~

Specific APIs and overloads may change across major versions. Examples in this lesson target Spring Integration 6 and Spring Framework 6, with `JavaMailSender` using Jakarta Mail.

## 4. Configuring SMTP Before Attaching the Handler

Before a `MailSendingMessageHandler` can send, the application must have a configured mail sender.

Example **application.yml**:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    username: mail-service
    password: example-placeholder-only
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"
~~~

This is an illustrative configuration for SMTP submission with STARTTLS. In real projects, **passwords must come from a secret manager or runtime secret config**, never stored as real credentials in source code.

### 4.1. Three Common Timeouts

| Property | Meaning |
| --- | --- |
| **mail.smtp.connectiontimeout** | Limit waiting to establish a connection |
| **mail.smtp.timeout** | Limit waiting to read on the socket |
| **mail.smtp.writetimeout** | Limit waiting to write data |

These timeouts do not necessarily add up to a single **overall deadline** for the entire send call. One email involves multiple steps—connect, TLS, AUTH, and DATA—so total duration can exceed any single timeout threshold.

### 4.2. STARTTLS Differs from Implicit TLS

Providers using implicit TLS on the corresponding submission port typically require **mail.smtp.ssl.enable=true** and a different port setting. Do not copy STARTTLS settings across every provider without reading their policy.

### 4.3. SMTP Sender Authorization

An SMTP account may only be authorized to send using certain From domains. Successfully configuring a mail sender does not prove that every From/Reply-To supplied by a request is permitted.

## 5. Minimal Java Config Example: DirectChannel and Handler

Spring application example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.mail.MailSendingMessageHandler;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
public class OutboundMailIntegrationConfig {

    @Bean("outboundMailChannel")
    public MessageChannel outboundMailChannel() {
        return new DirectChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = "outboundMailChannel")
    public MessageHandler outboundMailHandler(
            JavaMailSender javaMailSender
    ) {
        return new MailSendingMessageHandler(
                javaMailSender
        );
    }
}
~~~

Result:

~~~text
outboundMailChannel
        |
        v
outboundMailHandler
        |
        v
JavaMailSender
        |
        v
SMTP provider
~~~

### 5.1. ServiceActivator Attaches the Handler to a Channel

The **@ServiceActivator(inputChannel=...)** annotation on a `MessageHandler` bean registers an endpoint consuming messages from the specified channel in Spring Integration infrastructure.

This is one Java configuration option. Applications can also use Java DSL or XML depending on conventions.

### 5.2. Why Use DirectChannel?

`DirectChannel` dispatches to the subscriber **on the message-sending thread**, so code calling `outboundMailChannel.send(...)` normally waits for the handler to finish or fail.

This is easy to understand and test, but it also means an HTTP thread will be held while SMTP runs if invoked directly from a request.

### 5.3. No Automatic Reply

The handler is an outbound consumer and does not generate a response meaning "email read". If the caller needs to know that the request was **accepted into the system**, return a business status such as outbox enqueued rather than inferring it from the handler.

## 6. Sending SimpleMailMessage Through a Channel

A flow for simple plain-text emails can build a **SimpleMailMessage** first and send it as the payload.

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public final class WelcomeMailPublisher {

    private final MessageChannel outboundMailChannel;

    public WelcomeMailPublisher(
            MessageChannel outboundMailChannel
    ) {
        this.outboundMailChannel =
                outboundMailChannel;
    }

    public void publishWelcome(String recipient) {
        SimpleMailMessage mail =
                new SimpleMailMessage();

        mail.setFrom("welcome@example.org");
        mail.setTo(recipient);
        mail.setSubject("Welcome");
        mail.setText(
                "Thank you for registering an account."
        );

        outboundMailChannel.send(
                MessageBuilder
                        .withPayload(mail)
                        .setHeader(
                                "mailKind",
                                "welcome"
                        )
                        .build()
        );
    }
}
~~~

When using `SimpleMailMessage`, the adapter receives an explicit mail payload rather than having to interpret an arbitrary `String`.

### 6.1. Payload vs. Headers

- The **SimpleMailMessage** payload holds mail fields such as From, To, Subject, and Text.
- The **mailKind** header is Spring Integration message metadata used for routing/logging or observability.
- Do not assume an arbitrary header will be forwarded as an SMTP header or From field.

If you want Spring Message headers mapped into email headers, use an API/mapper or transformer step appropriate to your configuration and version.

### 6.2. What Content Suits SimpleMailMessage?

**SimpleMailMessage** is typically used for simple plain-text emails. It is not the model for HTML multipart, inline images, or complex attachments.

### 6.3. Watch Out for Payload Mutability

`SimpleMailMessage` is an object with setters, not completely immutable. Once a message has been sent through an asynchronous channel, do not keep modifying the payload on the producer thread because a worker may read it while data is changing.

It is better to create a dedicated instance per send intent and never mutate it after publishing.

### 6.4. Validation Cannot Be Skipped

A `SimpleMailMessage` setter is not a mailbox verification service. Validate recipient data before publishing, according to the application's address policies and sending permissions.

## 7. Creating MimeMessage for HTML Emails

For HTML emails, create a **MimeMessage** from `JavaMailSender` and pass it into the integration flow.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.MailPreparationException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class AccountMailFactory {

    private final JavaMailSender mailSender;

    public AccountMailFactory(
            JavaMailSender mailSender
    ) {
        this.mailSender = mailSender;
    }

    public MimeMessage createVerificationMail(
            String recipient,
            String verificationUrl
    ) {
        MimeMessage message =
                mailSender.createMimeMessage();

        try {
            MimeMessageHelper helper =
                    new MimeMessageHelper(
                            message,
                            true,
                            "UTF-8"
                    );

            helper.setFrom("security@example.org");
            helper.setTo(recipient);
            helper.setSubject("Account verification");
            helper.setText(
                    "Open the verification link in your browser.",
                    "<p>Please verify your account "
                  + "using the secure link provided.</p>"
            );

            return message;
        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Cannot prepare verification mail",
                    ex
            );
        }
    }
}
~~~

In the example, **verificationUrl** is not interpolated directly into HTML to avoid putting an unescaped URL straight into an HTML string. In a real application, the URL must be validated/generated at the business layer and rendered through a safe template engine.

### 7.1. Sending MimeMessage into a Channel

~~~java
MimeMessage mimeMessage =
        accountMailFactory.createVerificationMail(
                recipient,
                verificationUrl
        );

outboundMailChannel.send(
        MessageBuilder
                .withPayload(mimeMessage)
                .setHeader(
                        "mailKind",
                        "account_verification"
                )
                .build()
);
~~~

With this pattern, **MimeMessage is prepared before the handler**, separating render/MIME preparation errors from transport errors.

### 7.2. Do Not Create MimeMessage from an Incompatible Sender Arbitrarily

When multiple providers exist with differently configured senders/sessions, keep where `MimeMessage` is created aligned with where sending occurs. Session properties and MIME encoding can affect behavior; design a factory using compatible configuration or normalize the message before switching providers.

### 7.3. MIME and Jakarta Mail Are a Separate Boundary

`MailSendingMessageHandler` does not design HTML templates on the application's behalf. It accepts a prepared mail payload and passes it to the sender. Personalization/HTML escaping, attachment permissions, and template versioning belong to the preparation layer.

## 8. Attachments and Inline Resources

A multipart email requires **MimeMessageHelper** in multipart mode.

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage message =
        javaMailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(
                message,
                true,
                "UTF-8"
        );

helper.setFrom("billing@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Invoice");

helper.setText(
        "Your invoice is attached.",
        "<html><body><p>Your invoice is attached.</p></body></html>"
);

helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(invoicePdfBytes),
        "application/pdf"
);
~~~

Then send the message into the outbound channel.

### 8.1. Resources May Be Read Late

A `FileSystemResource`/`ClassPathResource` attached to a MIME part may not be fully read when `addAttachment` is called. Opening the `InputStream` can happen when Jakarta Mail serializes the message during `send`.

This affects exceptions, latency, and retries. Do not assume "once `addAttachment` succeeded, the file is definitely readable".

### 8.2. InputStream Must Supply Data Appropriately

An already-consumed `InputStream` cannot be re-read when the MIME transport needs it. For small/bounded data, **ByteArrayResource** is often convenient because it can create a fresh `InputStream` from bytes.

For large files, design bounded storage/streaming with proper re-opening mechanics rather than forcing the entire content into memory beyond budget.

### 8.3. Do Not Confuse Inline with Attachment

Inline resources have a Content-ID referenced by HTML; attachments normally display as files. They have different MIME structures and require separate tests.

### 8.4. Do Not Dump Full MIME into Logs

MIME can contain PII, tokens, invoices, and attached files. Observability should log event ID, mail kind, result, duration, and error category instead of dumping message bytes.

## 9. Java DSL: An Alternative Configuration

Besides annotations, you can use **IntegrationFlow**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mail.MailSendingMessageHandler;
import org.springframework.mail.javamail.JavaMailSender;

@Configuration
public class OutboundMailFlowConfig {

    @Bean
    public IntegrationFlow mailFlow(
            JavaMailSender sender
    ) {
        return IntegrationFlow
                .from("outboundMailChannel")
                .handle(
                        new MailSendingMessageHandler(sender)
                )
                .get();
    }
}
~~~

The flow registers a consumer for channel **outboundMailChannel** and uses the handler as the final step.

### 9.1. Choose Only One Registration Style per Flow

Do not attach two handlers to the same `DirectChannel` simultaneously and assume both will process every message in sequence. `DirectChannel` is a point-to-point dispatch channel with subscriber selection; multiple consumers can produce unexpected distribution behavior.

If the goal is sending to multiple destinations, use the proper routing/recipient-list/publish-subscribe pattern rather than registering duplicate consumers accidentally.

### 9.2. Java DSL Is Convenient with Transformer/Filter/Router

Conceptual flow example:

~~~text
businessMailChannel
        |
        v
Filter: allowed recipient?
        |
        v
Transformer: business DTO -> MimeMessage
        |
        v
MailSendingMessageHandler
~~~

Exact DSL configuration for transformers/filters depends on your application's code style and payload types. The handler only owns the final sending step.

## 10. Message<String> Is Not Necessarily a Complete Email

In a message-driven system, many producers send a payload that is just a String:

~~~java
MessageBuilder
        .withPayload("Order has been created")
        .build();
~~~

Do not assume the handler will always infer the right recipient, Subject, From, and content type from that String.

To avoid relying on implicit conversions and under-configured headers, use an explicit transformer step:

~~~text
Message<OrderEvent>
        |
        v
MailComposer
        |
        v
Message<SimpleMailMessage or MimeMessage>
        |
        v
MailSendingMessageHandler
~~~

### 10.1. Why Transform Early?

Once the payload is already a complete mail object:

- The outbound adapter's contract is easy to understand.
- Testing Subject/To/From is more isolated.
- Validation errors surface before sending.
- Less reliance on implicit header mapping.
- Easy reuse across multiple business sources.

### 10.2. If the Project Uses MailHeaders

Spring Integration Mail may offer ways to configure headers/expressions for the outbound adapter depending on the API and version. When applying them, verify the exact contract of your version; do not assume an arbitrary header such as **to** or **subject** will automatically become a MIME header in all configurations.

## 11. Comparing Direct JavaMailSender Calls vs. Handler

| Criterion | Direct JavaMailSender.send | MailSendingMessageHandler |
| --- | --- | --- |
| Purpose | Send mail from application code | Send mail from an integration message |
| Input | SimpleMailMessage, MimeMessage, preparator per overload | Spring Message carrying a compatible mail payload |
| Placement in flow | Implemented manually | Attachable to a channel/endpoint |
| Filter/transform/router | Coded directly | Uses Spring Integration components |
| Sync/async | Per caller execution style | Depends on channel/executor before the handler |
| Retry | Designed manually | Still needs appropriate advice/policy/outbox |
| Delivery receipt | Not built in | Not built in |
| Best suited for | Small flows, minimal orchestration | Multi-step/multi-source integration flows |

**Neither technology is inherently "safer" in every scenario.** A well-configured flow organizes code; durability and correctness still depend on transactions, retries, validation, and monitoring.

## 12. DirectChannel: Synchronous Sending and Error Propagation

When a producer sends through a DirectChannel:

~~~text
HTTP request thread
        |
        v
outboundMailChannel.send(...)
        |
        v
MailSendingMessageHandler
        |
        v
JavaMailSender.send(...)
        |
        +-- return or exception
        |
        v
Producer resumes
~~~

Code sending the message can block until the SMTP operation finishes.

### 12.1. Advantages

- Easy to tell when execution completes.
- Caller can catch exceptions synchronously.
- Easy to test the integration flow.
- No executor queue needed.

### 12.2. Disadvantages

- HTTP request thread waits on the network.
- Timeouts can slow down requests.
- A provider outage can tie up many requests.
- If sending happens inside a `@Transactional` method, the transaction can be prolonged.

### 12.3. Exceptions Are Transport Results, Not Delivery Status

A `channel.send` call completing does not mean the customer received the email. It only indicates the synchronous consumer/transport finished processing per the flow.

## 13. ExecutorChannel and Asynchrony

To offload the handler to an executor, you can use **ExecutorChannel**:

~~~java
import java.util.concurrent.Executor;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.messaging.MessageChannel;

@Bean("outboundMailChannel")
public MessageChannel outboundMailChannel(
        Executor mailExecutor
) {
    return new ExecutorChannel(mailExecutor);
}
~~~

When the producer sends a message, the task can be dispatched to a worker thread.

### 13.1. send Returning Does Not Prove SMTP Completed

With `ExecutorChannel`, returning from `channel.send` may only reflect dispatching/enqueueing onto the executor. SMTP transport runs later and may fail even after the producer has already returned a response.

### 13.2. Error Handling Changes

Exceptions raised on the worker do not automatically return to an HTTP caller that has already finished. Configure an `errorChannel`, error handler/dispatcher, or status/notification recording mechanism suited to your Spring Integration topology.

Do not assume every async exception is automatically stored or retried until it succeeds.

### 13.3. Executor Queue Does Not Equal a Durable Queue

An executor usually holds tasks in memory. If the process crashes before the worker executes, tasks can be lost. For critical emails, place a **transactional outbox** or durable broker before the handler step.

### 13.4. Backpressure and Saturation

If the executor has few threads and an unbounded queue, backlog can grow without bound when SMTP slows down. If the queue is bounded, submissions may be rejected. Configure thread pools, queue capacity, and rejection policies, and measure queue depth/age.

## 14. QueueChannel: Enqueued Is Not Yet Sent

Spring Integration offers **QueueChannel** to hold messages for a polling consumer. However, an in-memory QueueChannel does not survive process restarts by default.

~~~text
Publisher -> QueueChannel -> Polling endpoint -> Mail handler
                   |
                   +-- Waiting messages
~~~

### 14.1. Enqueue Outcome and SMTP Outcome Differ

If the producer only puts a message into `QueueChannel`, "request accepted" is different from "submitted to SMTP". APIs or dashboards must reflect both states.

### 14.2. Poller Determines Processing Rate

A polling endpoint can limit poll interval, messages per poll, and concurrency. If SMTP is slow, the queue will grow; monitor queue delay alongside send latency.

### 14.3. Do Not Use an In-Memory Queue for High-Durability Requirements

For transactional confirmation emails, crash/restart recovery is usually a design requirement. Use an outbox or a properly configured durable message store/broker with appropriate error handling.

## 15. Retry and Request-Reply Semantics

`MailSendingMessageHandler` can be placed in a flow with retry advice or a worker retry loop. However, **sending email is a side effect outside the database**, so retries require caution.

A scenario:

~~~text
MailSendingMessageHandler
        |
        v
SMTP sends DATA
        |
        v
Relay may accept message
        |
        v
Connection closes before final reply
        |
        v
Caller sees exception
        |
        v
Retry may send duplicate
~~~

### 15.1. Do Not Retry Every Exception

Cases:

| Error | Retry? | Reason |
| --- | --- | --- |
| Malformed recipient syntax | Usually no | Deterministically bad data |
| Missing attachment | Depends on cause | Source may need fixing |
| AUTH 535 | Usually stop and fix config | Rapid retries do not help |
| Invalid TLS certificate | Fix trust/endpoint | Do not bypass TLS |
| SMTP 421/450 | Can backoff | Usually a transient error |
| Provider throttling | Backoff/slow down | Avoid exceeding quota |
| Timeout before connect | Limited retry possible | Data usually not sent yet |
| Timeout after DATA | Duplicate risk | Outcome may be unknown |

### 15.2. Retry Is a Business Policy

Attempt counts, backoff, TTL/deadlines, and error classification must follow the mail kind. A password reset email with an expiring link needs different rules than a newsletter.

### 15.3. The Handler Does Not Turn SMTP into a Transaction

You cannot roll back a message already accepted by an SMTP relay merely by rolling back a database transaction.

## 16. Business Transactions and Email

Pattern requiring caution:

~~~java
@Transactional
public void confirmOrder(UUID id) {
    orderRepository.markConfirmed(id);

    outboundMailChannel.send(
            mailMessageFor(id)
    );
}
~~~

If the channel is a `DirectChannel`, the handler may send the email **while the transaction has not yet committed**.

### 16.1. Dangerous Rollback Scenario

~~~text
DB transaction begins
     |
     v
Order marked confirmed
     |
     v
SMTP relay accepts confirmation
     |
     v
DB commit fails / rollback
     |
     v
Customer receives email about an order
that was not actually confirmed
~~~

SMTP does not participate in the same database transaction, so it does not roll back with it.

### 16.2. Separating After Commit

You can structure service orchestration to invoke sending after the transaction commits, or use **@TransactionalEventListener(phase = AFTER_COMMIT)** for workflows not requiring strict durability.

### 16.3. AFTER_COMMIT Is Not Durable Enough

If the process crashes right after commit but before the listener manages to send, the task can be lost. For critical emails, a transactional outbox is the stronger option.

### 16.4. Async Does Not Solve Atomicity

Routing send through an `ExecutorChannel` only runs the work on another thread; it does not guarantee "only send if the transaction commits" or "never lose tasks after a crash".

## 17. Combining a Transactional Outbox with the Handler

A more reliable flow:

~~~text
Business transaction
     |
     +-- Update business record
     +-- Insert outbox mail event
     |
     v
COMMIT
     |
     v
Outbox worker claims pending event
     |
     v
Validate / render / build mail object
     |
     v
MessageChannel
     |
     v
MailSendingMessageHandler
     |
     v
JavaMailSender -> SMTP
     |
     v
Record attempt outcome and next action
~~~

### 17.1. The Outbox Holds the Intent to Send

It enables recovery after restarts, retry control, and backlog visibility. `MailSendingMessageHandler` remains only the final sending step.

### 17.2. Every Attempt Needs Explicit State

An outbox event can have:

~~~text
mail_event_id
mail_kind
recipient_reference
created_at
status
attempts
next_attempt_at
last_attempt_started_at
last_error_category
last_provider_alias
~~~

These fields are application-defined.

### 17.3. Store Rendered Content or DTO Snapshot?

- **DTO snapshot + template version**: can re-render on retry; stores less HTML, though rendering cost may repeat.
- **Rendered content**: allows retrying the exact same content, but stores personalized data and requires retention/access management.
- **Hybrid**: more flexible, though state design requires care.

### 17.4. Outbox Does Not Guarantee Exactly-Once SMTP

The relay may accept and the worker may crash before updating SENT. Retries can send duplicates. Use business idempotency, attempt logs, and reconciliation for unknown outcomes.

## 18. Error Handling for DirectChannel

With a synchronous channel, an exception from the sender/handler can propagate back to the producer on the same call stack.

Example:

~~~java
try {
    outboundMailChannel.send(message);
} catch (RuntimeException ex) {
    // Record failure at the orchestration layer.
    // Do not assert with certainty that the relay has not accepted it.
    recordFailure(ex);
}
~~~

**recordFailure** in the example is an application function.

### 18.1. Catch at the Right Boundary

An HTTP producer does not necessarily need to handle every detailed SMTP exception. An orchestration/outbox service is usually the right place to classify errors, persist status, and decide on retries.

### 18.2. Do Not Swallow Errors and Report Success

If the handler reports an error yet the application catches it and returns "email sent" without persisting status, the system loses reconciliation capability.

### 18.3. Do Not Retry in an Unbounded Loop

A naive catch block calling `outboundMailChannel.send` again in a loop can trigger a storm against the SMTP provider and duplicates. Use a retry policy with backoff, attempt caps, and explicit deadlines.

## 19. Error Handling in Asynchronous Flows

With `ExecutorChannel` or async endpoints, errors occur on the worker and need a dedicated handling path.

~~~text
Publisher thread
       |
       v
ExecutorChannel enqueues work
       |
       +-- Publisher returns
       |
       v
Worker runs handler
       |
       +-- Success -> record completion
       |
       +-- Failure -> error handling / outbox update
~~~

### 19.1. ErrorChannel Is Not Magic

Spring Integration has **errorChannel**, `ErrorMessage`, and error handler mechanisms for certain async flows; the exact path depends on channel type, endpoint, task executor, and configuration.

Configure and actually test that errors reach the intended destination; do not assume every async exception is automatically published to a durable `errorChannel`.

### 19.2. Store State Where Ownership Lives

If an outbox worker owns the event, it should learn whether the attempt succeeded or failed and persist durable state. If a worker merely enqueues onto an `ExecutorChannel` and marks SENT immediately, SMTP may actually fail after the event was already marked finished.

### 19.3. Consider Avoiding Two Unnecessary Queue Layers

An outbox is already a durable queue. Placing a long `ExecutorChannel` queue behind it can obscure true queue wait time and complicate event acknowledgment.

## 20. Header Metadata and MIME Headers

A Spring message may look like:

~~~java
Message<SimpleMailMessage> integrationMessage =
        MessageBuilder
                .withPayload(mail)
                .setHeader(
                        "mailEventId",
                        "mail-1842"
                )
                .setHeader(
                        "mailKind",
                        "order_confirmation"
                )
                .build();
~~~

These headers serve the Spring Integration workflow. Do not assume all of them are sent as MIME headers to the recipient.

### 20.1. Where Should Metadata Live?

- **Mail event ID**: in logs/outbox/traces or internal message headers.
- **Recipient/Subject/Body**: in the validated mail payload.
- **From/Reply-To**: configured per sender identity policy.
- **MIME Content-Type/Content-ID**: set when building `MimeMessage`.

### 20.2. Do Not Mirror Arbitrary Headers into Email

If message headers contain internal IDs, tokens, or tenant data, copying all of them into MIME headers can leak metadata to recipients and intermediate SMTP relays. Map only approved MIME headers.

### 20.3. Correlation for Retries

A stable `mailEventId` links the message, outbox event, and SMTP attempts. However, the MIME `Message-ID` is not a mechanism guaranteeing the provider will deduplicate emails.

## 21. Multi-Provider Router with MailSendingMessageHandler

An application may have multiple `JavaMailSender` beans and multiple outbound channels:

~~~text
                         MailRouter
                         /        \
                        v          v
                  primaryMail   backupMail
                        |          |
                        v          v
                 Handler A     Handler B
                        |          |
                        v          v
                 SMTP A        SMTP B
~~~

Each `MailSendingMessageHandler` uses a sender configured for its respective provider.

### 21.1. Do Not Mutate a Singleton Sender Concurrently

If multiple threads change host/username on the same `JavaMailSenderImpl` before each send, you risk sending with the wrong account/provider. Use separate registered sender instances selected by route.

### 21.2. Routes Must Be Explainable

A routing decision should record:

~~~text
mailEventId
sourceAlias
providerAlias
accountAlias
routeReason
routePolicyVersion
~~~

Actual provider metadata belongs to each **attempt**, not just the root event.

### 21.3. Failover Is Not Always Safe

If attempt A times out after DATA, A may have already succeeded. Switching immediately to B can create a duplicate. Only fail over under a policy that understands the error class and outcome certainty.

### 21.4. From Authorization and DKIM

Backup providers must be authorized to send the application's From domain, with proper SPF/DKIM/DMARC alignment and security compliance. Failover must never bypass sender authorization.

## 22. Observing Handler Performance

A send call can be broken down into:

~~~text
Business view loading
        |
        v
Template render
        |
        v
MimeMessage build
        |
        v
Channel dispatch / queue wait
        |
        v
MailSendingMessageHandler invocation
        |
        v
JavaMailSender.send
        |
        v
SMTP response
~~~

You can measure:

| Metric | Scope |
| --- | --- |
| **mail.template.render.duration** | HTML/text rendering |
| **mail.message.build.duration** | Building mail payload/MIME |
| **mail.channel.queue.delay** | Time message waits before worker |
| **mail.smtp.submit.call.duration** | `sender.send` call |
| **mail.smtp.submit.attempts** | Send attempt count |
| **mail.outbox.pending.count** | Backlog |
| **mail.event.to.relay.acceptance** | Business event to relay acceptance |
| **mail.smtp.failures** | Errors by provider/category |

### 22.1. Handler Duration Differs from SMTP Server Processing

If measured around `JavaMailSender.send`, duration can include DNS, TCP, TLS, AUTH, MIME serialization, lazy attachment reads, DATA, and server replies. Do not treat it as pure provider server processing time.

### 22.2. Async Latency Must Be Measured on the Worker

If a timer only wraps `channel.send` into an `ExecutorChannel`, it may measure dispatch time rather than SMTP. Place the timer at the adapter or a wrapper around `send` inside the worker.

### 22.3. Record Metrics Even on Error

Use `finally` or Micrometer `Timer.Sample` so failed/timed-out durations do not vanish from p95/p99.

## 23. Micrometer Instrumentation for Outbound Flows

An application-side wrapper can measure each attempt:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;

public final class ObservedMailTransport {

    private final JavaMailSender sender;
    private final MeterRegistry registry;

    public ObservedMailTransport(
            JavaMailSender sender,
            MeterRegistry registry
    ) {
        this.sender = sender;
        this.registry = registry;
    }

    public void submit(
            MimeMessage message,
            String mailKind
    ) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            sender.send(message);
        } catch (RuntimeException ex) {
            outcome = "failure";
            throw ex;
        } finally {
            sample.stop(
                    registry.timer(
                            "mail.smtp.submit.call.duration",
                            "kind", mailKind,
                            "outcome", outcome
                    )
            );
        }
    }
}
~~~

This is an example of an **application-built adapter/wrapper** to illustrate the measurement boundary. If using `MailSendingMessageHandler` directly, you can instrument via a `JavaMailSender` decorator, interceptor/advice, or configured wrapper so it does not send twice.

### 23.1. Do Not Add Two Senders Side by Side

Do not let the handler send while also calling `ObservedMailTransport.submit` on the same message just to record metrics: that causes two email-sending side effects. Wrap instrumentation **around a single transport call**.

### 23.2. Choose Low-Cardinality Tags

`kind` should come from a finite set such as `order_confirmation`, `password_reset`, `security_alert`. Never use recipient, Subject, `mailEventId`, or raw exception messages as Timer tags.

### 23.3. Attach Provider When Using Multiple SMTPs

If the flow routes across providers, record the actual provider alias on the attempt. Do not infer the provider from the From header or initial route when failover has occurred.

## 24. Structured Logs and Tracing

A sensible event log:

~~~text
event=mail.smtp.attempt.finished
mailEventId=mail-1842
attemptId=mail-1842-2
mailKind=order_confirmation
provider=primary_smtp
outcome=failure
errorCategory=timeout
durationMs=10120
~~~

This lets you inspect a specific attempt without logging the message body.

### 24.1. Do Not Log payload.toString Blindly

A `MailMessage`/`MimeMessage` or business DTO can contain recipients, tokens, HTML, or attachment metadata. Avoid logging the full message just to debug channel routing.

### 24.2. Traces Can Link Stages

~~~text
order.confirm
    |
    v
outbox.enqueue
    |
    v
mail.worker.process
    |
    +-- mail.transform
    +-- mail.route
    +-- mail.smtp.submit
~~~

When crossing a durable queue or outbox, trace context or span links can connect asynchronous work in compliance with privacy/retention policies.

### 24.3. Do Not Treat Success as Delivered

SMTP submit success is one stage. Bounces, deferrals, or delivered events may come from provider webhooks/APIs if integrated separately; `MailSendingMessageHandler` does not generate those downstream events itself.

## 25. Security in MailSendingMessageHandler Flows

When routing send operations through message channels, protect both data and control flow.

### 25.1. Recipient Validation

- Disallow null/blank recipients.
- Validate syntax per product policy.
- Do not accept multi-recipient lists in fields intended for a single recipient.
- Check sending permissions by tenant and purpose.
- Do not trust recipients passed via arbitrary message headers.

### 25.2. Header Injection

Subject, display name, filename, and header fields must not accept CR/LF or out-of-contract control characters. Use Jakarta Mail/`MimeMessageHelper` APIs and input validation rather than concatenating raw MIME headers from user input.

### 25.3. HTML Template Escaping

User data inside HTML templates must be escaped appropriately. Do not use string concatenation to insert raw HTML/links outside your trust policy.

### 25.4. Attachment Paths and Resources

Do not use user-supplied filenames as unvalidated filesystem paths. Enforce resource access controls, file size, type, retention, and read permissions.

### 25.5. SMTP Credentials

Fetch username/password/token from a secret manager. Never place them into message headers, logs, metrics, traces, or email bodies.

### 25.6. Mail Debug

Jakarta Mail protocol debug can log recipients and metadata; avoid enabling it by default in production, especially options that can expose AUTH data.

## 26. Testing MailSendingMessageHandler Without Real SMTP

This object is a `MessageHandler`, so you can instantiate it in a test and invoke `handleMessage(...)` with a `Message` carrying a `MimeMessage` payload.

JUnit 5/Mockito example:

~~~java
import static org.mockito.Mockito.*;

import java.util.Properties;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.Test;
import org.springframework.integration.mail.MailSendingMessageHandler;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.messaging.support.MessageBuilder;

class MailSendingMessageHandlerTest {

    @Test
    void delegatesMimeMessageToSender() {
        JavaMailSender sender =
                mock(JavaMailSender.class);

        MimeMessage mime = new MimeMessage(
                Session.getInstance(new Properties())
        );

        MailSendingMessageHandler handler =
                new MailSendingMessageHandler(sender);

        handler.handleMessage(
                MessageBuilder.withPayload(mime).build()
        );

        verify(sender, times(1))
                .send(same(mime));
    }
}
~~~

Test goals:

- The handler accepts an integration message containing a `MimeMessage`.
- `JavaMailSender` is invoked once.
- No network request is made.
- No real SMTP account or provider is needed.

### 26.1. Why Use a Real MimeMessage?

An in-memory `MimeMessage` can be created from a dummy `Session`. This lets you test the handler contract without deeply mocking Jakarta Mail internals.

### 26.2. Test Email Content at Another Layer

To verify Subject, From, To, MIME multipart, and attachments, test the factory/composer separately. Handler unit tests should focus on **delegating send** and invocation counts.

### 26.3. Never Send to Real Addresses

Unit tests are not delivery tests. Only mock the sender or use a controlled SMTP capture server in integration tests.

## 27. Testing Exception Propagation

Have `JavaMailSender` throw a simulated error:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.util.Properties;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.Test;
import org.springframework.integration.mail.MailSendingMessageHandler;
import org.springframework.mail.MailSendException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.messaging.support.MessageBuilder;

@Test
void propagatesTransportFailure() {
    JavaMailSender sender = mock(JavaMailSender.class);

    MimeMessage mime = new MimeMessage(
            Session.getInstance(new Properties())
    );

    doThrow(new MailSendException("simulated SMTP failure"))
            .when(sender)
            .send(same(mime));

    MailSendingMessageHandler handler =
            new MailSendingMessageHandler(sender);

    assertThrows(
            RuntimeException.class,
            () -> handler.handleMessage(
                    MessageBuilder.withPayload(mime).build()
            )
    );

    verify(sender, times(1))
            .send(same(mime));
}
~~~

In many flows, Spring Integration may wrap or rethrow exceptions via its `MessagingException` abstraction; tests should assert the error contract at the expected boundary rather than assuming every version preserves the exact outermost exception class.

### 27.1. Do Not Assume Exception Means Not Sent

A `MailSendException` due to a transport error does not prove the relay did not accept DATA. Retry policies need phase classification and unknown-outcome handling.

### 27.2. Testing the Error Channel in Integration Tests

When using `ExecutorChannel`/`errorChannel`, test the real asynchronous flow: the producer may return early, the worker fails to send, `ErrorMessage` arrives on the configured channel, and outbox state is updated.

## 28. Testing a DirectChannel Flow

A test can register the handler as a subscriber:

~~~java
import static org.mockito.Mockito.*;

import java.util.Properties;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.mail.MailSendingMessageHandler;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.messaging.support.MessageBuilder;

@Test
void directChannelDispatchesToMailHandler() {
    JavaMailSender sender =
            mock(JavaMailSender.class);

    MailSendingMessageHandler handler =
            new MailSendingMessageHandler(sender);

    DirectChannel channel = new DirectChannel();
    channel.subscribe(handler);

    MimeMessage mime = new MimeMessage(
            Session.getInstance(new Properties())
    );

    channel.send(
            MessageBuilder.withPayload(mime).build()
    );

    verify(sender, times(1)).send(same(mime));
}
~~~

### 28.1. What the Test Proves

`DirectChannel` accepts the `Message`, dispatches synchronously to the subscriber, and the handler calls the sender.

### 28.2. What the Test Does Not Prove

- A real SMTP server accepts the message.
- TLS/AUTH is configured correctly.
- The email reached the inbox.
- Retry/outbox is durable.
- Async `ErrorChannel` works.

Those behaviors require dedicated tests in an appropriate environment.

## 29. Testing Multiple Providers and Route Selection

If the system has multiple handlers:

~~~text
Message<MailRequest>
        |
        v
Router
   /           \
  v             v
primaryChan   backupChan
  |             |
  v             v
primaryHandler backupHandler
  |             |
  v             v
senderA       senderB
~~~

Tests should cover:

1. Primary route sends via sender A without calling B.
2. Backup route sends via sender B without calling A.
3. Invalid recipient error calls neither sender.
4. Provider A failure is attributed to provider A.
5. Failover only occurs when policy permits.
6. Timeout after DATA does not blindly resend unconditionally.
7. Multiple attempts for the same event are not counted as multiple unique events.
8. Provider metadata is recorded on its corresponding attempt.

### 29.1. Do Not Mutate One JavaMailSenderImpl in Concurrency Tests

Tests should use independent senders to mirror production configuration. Mutating host/username on a single shared sender across threads is both hard to test and error-prone.

### 29.2. Do Not Confuse a Router with an Automatic Load Balancer

A Spring Integration Router forwards messages to channels according to configured logic. It does not inherently supply health checks, rate limits, or retry policies for SMTP providers. Those decisions must be defined explicitly.

## 30. When Should You Avoid MailSendingMessageHandler?

Not every feature needs an integration flow. Calling `JavaMailSender` directly can be appropriate if:

- Only one service sends emails.
- There is no routing, transformer/filter, or queuing.
- Message-building logic is clear and easy to test.
- There is no need to decouple message-driven orchestration.
- The team wants to minimize unnecessary abstraction layers.

`MailSendingMessageHandler` shines when the application already uses Spring Integration or needs to connect outbound mail to multiple message sources.

### 30.1. Do Not Add a Flow Just to Change Syntax

Replacing:

~~~java
sender.send(mimeMessage);
~~~

with a channel + handler that provides no benefit in routing, error handling, testing, or orchestration can complicate the architecture without improving reliability.

### 30.2. Do Not Confuse the Handler with a Provider SDK

`MailSendingMessageHandler` uses Spring Mail's SMTP abstraction. Provider-specific features such as provider-hosted templates, analytics webhooks, or API message IDs may require a different adapter/SDK.

## 31. Common Anti-Patterns

| Anti-pattern | Problem | Fix |
| --- | --- | --- |
| Calling handler from a long HTTP transaction | Holds threads/DB connections | Separate after commit/outbox |
| Assuming ExecutorChannel is durable | Tasks lost on crash | Durable queue/outbox |
| Sending String without clear mail metadata | Missing To/From/Subject | Use transformer to build mail payload |
| Creating SimpleMailMessage then mutating after publish | Race with async consumer | Create dedicated instance, never mutate |
| Putting uncontrolled PII in Integration headers | Easy leaks via logs/tracing | Allowlist metadata |
| Logging full MimeMessage | Exposes body/attachments | Structured safe logs |
| Not configuring SMTP timeouts | Workers can hang indefinitely | Connection/read/write timeouts |
| Catching and ignoring exceptions | False success reporting | Persist state/propagate properly |
| Retrying all errors | Storms/duplicates | Classify and backoff |
| Treating send success as inbox delivered | Wrong semantics | Track relay vs. delivery |
| Sending before database commit | Email contradicts rollback | Outbox/after-commit |
| Marking SENT right on async enqueue | SMTP not actually submitted yet | Ack based on worker outcome |
| Sharing one sender and swapping hosts | Races/wrong provider | Dedicated sender instances |
| Not checking resources before sending | Late file-read failures | Bounded preflight/reopenable source |
| Expecting DirectChannel fan-out with multiple handlers | Unintended dispatch behavior | Proper EIP router/pub-sub |
| Testing against real production SMTP | Risk of sending by mistake | Mockito/capture SMTP tests |
| Counting attempts as unique emails | Skewed dashboards | Two separate metrics |
| Not measuring queue delay | Invisible backlog | Queue/outbox metrics |

## 32. Boundary Testing Matrix

| Group | Scenario | Expected Behavior |
| --- | --- | --- |
| Payload | Valid MimeMessage | Handler invokes sender once |
| Payload | Valid SimpleMailMessage | Flow builds and sends text mail per contract |
| Payload | Untransformed business DTO | Blocked/transformed before handler |
| Validation | Invalid recipient | Transport is not invoked |
| MIME | Template error | Preparation error recorded, SMTP not called |
| Attachment | Missing resource | Error reported before/at serialization per design |
| DirectChannel | Sender succeeds | Caller completes synchronously |
| DirectChannel | Sender fails | Error propagates to caller/handler boundary |
| ExecutorChannel | Slow send | Caller does not treat enqueue as delivery |
| ExecutorChannel | Worker failure | Error reaches configured handler/error state |
| Outbox | Commit succeeds | Durable event processed by worker |
| Outbox | Rollback | No committed send intent created |
| Retry | SMTP 421/450 | Backoff per policy |
| Retry | AUTH/config error | No rapid retry storm |
| Retry | Timeout after DATA | Unknown state/duplicate policy applied |
| Multi-provider | Route A | Only sender A is invoked |
| Multi-provider | Failover A→B | Attempts recorded per provider |
| Observability | Success/failure duration | Metrics recorded for both |
| Security | Headers with PII | Never logged or forwarded arbitrarily |
| Integration | SMTP capture test | Verifies MIME submitted, no real send |

## 33. Frequently Asked Questions

**1. Does MailSendingMessageHandler belong to Spring Framework Mail or Spring Integration?**

It belongs to Spring Integration Mail and uses Spring Framework Mail's mail sender to perform outbound SMTP.

**2. Is it a MessageHandler?**

Yes. It acts as a handler consuming Spring Messaging messages and is registered as an outbound endpoint.

**3. Can it be used with JavaMailSenderImpl?**

Yes. `JavaMailSenderImpl` is the standard implementation for SMTP and can be injected into the handler.

**4. When should SimpleMailMessage be used?**

When you need simple plain-text email without complex HTML/multipart/attachments.

**5. When should MimeMessage be used?**

When you need HTML, `multipart/alternative`, attachments, inline resources, or rich MIME headers.

**6. Does the handler render Thymeleaf templates automatically?**

Do not treat that as the handler's responsibility. Render templates in a composer/transformer before passing the mail payload into the outbound flow.

**7. Can a String payload be sent directly into the handler?**

Do not rely on general assumptions without verifying your version's contract/configuration. For clarity, create `MailMessage`/`MimeMessage` in a transformer beforehand.

**8. Does DirectChannel make email sending synchronous?**

With a synchronous handler and `DirectChannel`, the producer usually waits for handler execution to finish on the same thread. Thus it may wait for SMTP.

**9. Does ExecutorChannel guarantee email was sent successfully when send returns true?**

No. That result may only indicate the message was accepted for dispatch, not that SMTP finished.

**10. Is errorChannel needed when using async?**

A clear asynchronous error-handling strategy is required. You can use `errorChannel` and an appropriate handler while persisting durable state if reliability is required.

**11. Does QueueChannel persist messages across restarts automatically?**

An in-memory `QueueChannel` does not. Durability requires a properly designed message store/broker or transactional outbox.

**12. Does the handler automatically retry SMTP 421?**

Do not assume it does. Retries need policy, advice, or worker orchestration with backoff and limits.

**13. Can you send email inside a `@Transactional` method?**

Technically possible, but risks SMTP side effects not rolling back when the DB transaction rolls back. Separate after commit or use an outbox.

**14. Is an AFTER_COMMIT listener reliable enough?**

It avoids sending before commit, though it is not durable across a crash between commit and send. An outbox is stronger when reliable recovery is required.

**15. Does send success mean the recipient read the email?**

No. SMTP submit success differs from inbox delivery and read/open events.

**16. Does a timeout mean the relay definitely did not accept?**

No. A timeout after DATA can leave the outcome unknown, and retrying carries duplicate risk.

**17. Can multiple SMTP providers be used with the handler?**

Yes—configure multiple senders/handlers, route messages to the appropriate channel, and record provider attribution per attempt.

**18. Does the handler automatically pick the best provider?**

No. Routers, health checks, rate limits, and failover policies are application architecture responsibilities.

**19. Can the handler be tested without an SMTP server?**

Yes. Mock `JavaMailSender`, construct an in-memory `MimeMessage`, call `handleMessage` or send via `DirectChannel`, and verify the invocation.

**20. Why not test using a real Gmail inbox?**

Unit tests would depend on network, accounts, rate limits, spam filtering, and risk sending by mistake. Use a controlled SMTP capture server for integration tests and mocks for unit tests.

**21. Can mailEventId be attached to a Spring Message header?**

Yes for internal correlation, though do not automatically copy it into MIME headers or metric labels. Follow privacy and audit policies.

**22. Does using Spring Integration make SMTP faster?**

Not automatically. It organizes flows and can support concurrency/routing, while network and provider latency still have to be measured and managed.

**23. Why can attachments slow down send even when building is fast?**

Resources may be read during MIME serialization inside `send`; in that case attachment I/O sits inside send-call latency.

**24. Should you create a single handler and swap SMTP hosts per message?**

No, if using a singleton sender across multiple threads. Use independent senders/handlers and safe routing.

**25. What should be logged when sending fails?**

Event ID/attempt ID, mail kind, provider alias, error category, phase when known, and duration. Avoid credentials, bodies, tokens, and unnecessary PII.

## 34. MailSendingMessageHandler Takeaways

**MailSendingMessageHandler is Spring Integration Mail's outbound channel adapter**, connecting a Spring Messaging flow with `JavaMailSender`'s email-sending operations. It fits when an application wants to decouple business producers from transport, standardize transform/filter/router steps, and organize telemetry and error handling within an integration flow.

Use **SimpleMailMessage** for plain-text emails and **MimeMessage/MimeMessageHelper** for HTML or multipart messages. Prepare the proper payload before the handler, validate recipients/From, manage attachments carefully, and never leak sensitive content or credentials into Spring Integration headers or logs.

Choose channels by semantics: **DirectChannel** usually processes synchronously, **ExecutorChannel** offloads work to a worker without making tasks durable, and an in-memory **QueueChannel** does not guarantee recovery after crashes. For critical business emails, a **transactional outbox** preserves send intents and manages retries after commit; the handler remains the SMTP execution step inside the worker.

Finally, **send() returning success differs from an email being delivered or read**. Measure and persist each attempt's result, separate preparation errors from SMTP errors, handle timeouts after DATA cautiously, and only retry/failover under controlled policy. Placed at the right boundary, `MailSendingMessageHandler` makes mail-sending systems structured, observable, and testable without mistaking integration messaging for delivery guarantees.
