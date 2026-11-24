# Outbound Mail Adapter and Message Channel

When an application needs to send order confirmation emails, status notifications, or emails triggered by business events, the simplest approach is often calling `JavaMailSender.send(...)` directly. However, when a system has multiple event sources and needs flow control, content transformation, routing, rate limiting, or separation of mail-sending logic from business services, **Spring Integration Mail** provides an approach organized around a **message channel** and an **outbound mail adapter**.

In this model, business logic does not necessarily invoke SMTP directly. Business logic emits a **Spring Integration Message** onto a **MessageChannel**. Downstream endpoints can validate data, enrich mail headers, transform the payload, and finally pass the message to the **mail outbound adapter**. The adapter uses Spring's mail-sending infrastructure to submit the message.

The most important point: **the outbound mail adapter is a message-consuming endpoint at the end of a flow**, not an inbox, a durable message broker, or an API reporting that an email has landed in the recipient's mailbox. The channel defines **how work is handed off** between endpoints; the adapter defines **how a message is turned into a mail-sending operation**. Understanding this boundary helps avoid confusing a message being accepted by a channel, SMTP submission, and email delivery.

This lesson belongs to the **Spring Integration Mail** chapter of the **Spring Framework Mail** module, focusing on two components: **Outbound mail adapter and message channel**. The examples use Java, Spring Integration Java DSL, `JavaMailSender`, `MailSendingMessageHandler`, and common channel configurations. The final sections explain sending errors, async processing, pollers, retries, testing, and operational risks.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Explain `MessageChannel`, `Message<?>`, `MessageHandler`, and an outbound channel adapter.
2. Diagram the flow from a business event to SMTP through Spring Integration.
3. Configure an outbound mail adapter using Java DSL or `@ServiceActivator`.
4. Pass the body and mail headers `TO`, `CC`, `BCC`, `FROM`, `REPLY_TO`, `SUBJECT`.
5. Distinguish `String`, `MailMessage`, and `byte[]` payloads; know when a transformer is needed.
6. Choose `DirectChannel`, `ExecutorChannel`, or `QueueChannel` based on desired behavior.
7. Understand the required poller for a `PollableChannel` source on a consuming endpoint.
8. Recognize when sending errors propagate back to the caller and when they must be handled asynchronously.
9. Design a pipeline that does not lose notifications on process restart.
10. Test mail content and flow behavior without sending to production SMTP.

## 2. How Do Spring Mail and Spring Integration Mail Differ?

`Spring Framework Mail` provides abstractions such as:

- `MailSender` and `JavaMailSender` for sending emails.
- `SimpleMailMessage` for simple plain-text content.
- `MimeMessageHelper` for supporting HTML, multipart, inline images, and attachments.
- `JavaMailSenderImpl` for connecting and sending over SMTP.

`Spring Integration` is a framework for **Enterprise Integration Patterns (EIP)**: channels, transformers, routers, filters, service activators, pollers, gateways, and adapters connecting external systems.

`Spring Integration Mail` combines these two domains:

```text
Business application
       |
       v
Spring Integration Message<?>
       |
       v
MessageChannel
       |
       v
Transformer / Header Enricher / Filter / Router
       |
       v
Outbound Mail Adapter
       |
       v
MailSendingMessageHandler
       |
       v
JavaMailSender / SMTP Provider
```

The `org.springframework.messaging.Message<?>` object here is **different** from `jakarta.mail.Message` or `MimeMessage`. One object is an envelope for the **in-application integration flow**, while the other is an **electronic mail** structure.

| Concept | Package or Scope | Responsibility |
| --- | --- | --- |
| `Message<?>` | `org.springframework.messaging` | Payload + headers for the integration pipeline |
| `MessageChannel` | `org.springframework.messaging` | Transfers Spring Integration Messages to consumers |
| `MessageHandler` | `org.springframework.messaging` | Consumes messages from a channel |
| `MailSendingMessageHandler` | Spring Integration Mail | Converts payload/headers into a mail-sending operation |
| `MailMessage` | `org.springframework.mail` | Spring's mail message model |
| `MimeMessage` | `jakarta.mail.internet` | MIME email, headers, and multipart parts |
| `JavaMailSender` | `org.springframework.mail.javamail` | Service for creating/sending MIME and simple mail |

**The two message layers must not be conflated.** Spring Integration headers such as `id` and `timestamp` are only metadata inside the pipeline; they do not automatically become RFC email headers. Headers intended for mail have their own mapping mechanism.

## 3. What Is an Outbound Mail Adapter?

In Spring Integration, an **outbound channel adapter** is an endpoint that consumes messages from a channel and then calls an external system. For mail, the external system is the mail sender/SMTP transport.

Flow outline:

```text
[Integration Message]
         |
         v
    outboundMail
         |
         v
   +-------------+
   | Mail adapter|  -----> SMTP server
   +-------------+
         |
         +--- Does not produce a request/reply style reply payload
```

Being a **one-way** adapter does not mean it cannot report errors. If an operation fails, an exception can still be propagated back to the caller or error infrastructure depending on how the channel dispatches.

### What the Adapter Does Not Do

- Not an inbox for reading incoming email via POP3/IMAP.
- Not an SMTP server receiving mail from clients.
- Does not persist a durable queue in a database by default.
- Does not automatically retry all errors safely.
- Does not provide an exactly-once delivery guarantee.
- Does not provide `delivered`, `bounced`, or `opened` callbacks by default.
- Does not automatically turn an arbitrary business object into a complete email without an appropriate mapping/transformer.

Those capabilities require other components or an additional architectural layer.

## 4. What Role Does MessageChannel Play?

`MessageChannel` is the message conduit between producer and consumer. The producer only needs to know **what to push onto the channel**, without necessarily knowing how the specific SMTP producer is processing it.

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

Message<String> mailRequest = MessageBuilder
        .withPayload("Order has been confirmed.")
        .build();

boolean acceptedByChannel = outboundMail.send(mailRequest);
```

The `send(...)` method returns a boolean according to the channel contract, but **`true` must not be interpreted broadly as the email having been delivered**. With `DirectChannel`, dispatching typically runs on the caller thread; with `QueueChannel`, it may only have been placed into a queue; with `ExecutorChannel`, processing may have been handed off to another executor.

### One Channel Separates Both Sides

```text
OrderService / PaymentService / Scheduler
                   |
                   v
              outboundMail
                   |
                   v
             Mail Adapter
                   |
                   v
               SMTP Relay
```

If you swap the mail adapter for a test handler or switch SMTP providers, the producer does not necessarily have to change. However, **the producer still owns the business responsibility**: who should receive it, when it should be sent, and whether the content is valid.

## 5. Dependencies to Prepare

For a modern Spring Boot project using the `jakarta.mail` namespace, the mail integration module is typically needed:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-mail'
    implementation 'org.springframework.boot:spring-boot-starter-mail'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

This is a Gradle example for a project using Spring Boot dependency management. In some starter/module versions, dependencies are brought in transitively in different ways; inspect the actual dependency graph and avoid declaring incompatible Spring Integration/Spring Framework versions.

With modern Spring Integration, JavaMail classes use `jakarta.mail.*`. Legacy Spring 5/Integration projects may use `javax.mail.*`. Do not mix both namespaces in the same codebase without a clear migration strategy.

### Reference Documentation by Version

Java DSL APIs and packages may change across major versions. The examples use APIs documented in the Spring Integration Mail reference, including `Mail.outboundAdapter(...)`, `IntegrationFlow`, `MailSendingMessageHandler`, and `MailHeaders`. When implementing, cross-check the documentation for the exact Spring Integration version managed by Spring Boot.

## 6. Simplest Example: DirectChannel + Outbound Adapter

This example uses a Spring Boot-configured `JavaMailSender` and a `DirectChannel` to receive text messages.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mail.dsl.Mail;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.messaging.MessageChannel;

@Configuration
public class OutboundMailIntegrationConfig {

    @Bean
    public MessageChannel outboundMail() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow outboundMailFlow(
            MessageChannel outboundMail,
            JavaMailSender mailSender
    ) {
        return IntegrationFlow.from(outboundMail)
                .handle(Mail.outboundAdapter(mailSender))
                .get();
    }
}
```

Meaning of each part:

1. `@Bean outboundMail()` creates the channel that receives send requests.
2. `DirectChannel` dispatches messages directly to a subscriber on the same thread under normal behavior.
3. `IntegrationFlow.from(outboundMail)` receives messages from the channel.
4. `handle(Mail.outboundAdapter(mailSender))` attaches the mail-sending handler at the end of the flow.
5. `get()` completes the DSL configuration.

With a text payload, we need to provide the required mail headers so the adapter knows the recipient, From, and subject. Do not assume that a `String` body alone is enough to send a valid email without a recipient.

## 7. Sending a Message with MessageBuilder

Suppose the `outboundMail` channel has been injected into a service:

```java
import org.springframework.integration.mail.MailHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public final class NotificationPublisher {

    private final MessageChannel outboundMail;

    public NotificationPublisher(MessageChannel outboundMail) {
        this.outboundMail = outboundMail;
    }

    public void publishOrderConfirmed() {
        boolean channelAccepted = outboundMail.send(
                MessageBuilder
                        .withPayload("Order #A123 confirmed.")
                        .setHeader(
                                MailHeaders.TO,
                                "tester@example.net"
                        )
                        .setHeader(
                                MailHeaders.FROM,
                                "notify@example.org"
                        )
                        .setHeader(
                                MailHeaders.SUBJECT,
                                "Order confirmation"
                        )
                        .build()
        );

        if (!channelAccepted) {
            throw new IllegalStateException(
                    "Outbound channel did not accept message"
            );
        }
    }
}
```

The addresses used in the example are **dummy addresses** to illustrate the structure. When running, the SMTP sender must be configured with a test/sandbox server and permitted sender domains.

### Pitfall to Avoid

The `publishOrderConfirmed()` method only checks that the channel returns `true`; **do not name that variable `mailDelivered`**. If the channel is a `DirectChannel` and downstream is synchronous, the method can throw an exception when the sender fails. If the channel is async/queued, the result usually only indicates that the work was accepted into an intermediate layer.

## 8. MailHeaders and Mapping Rules

Spring Integration Mail defines mail header constants:

| Header Constant | Content | Example |
| --- | --- | --- |
| `MailHeaders.TO` | Primary recipient | `tester@example.net` |
| `MailHeaders.CC` | Cc recipient | `supervisor@example.net` |
| `MailHeaders.BCC` | Bcc recipient | `audit@example.net` |
| `MailHeaders.FROM` | Sender address | `notify@example.org` |
| `MailHeaders.REPLY_TO` | Reply-to address | `support@example.org` |
| `MailHeaders.SUBJECT` | Subject | `Order confirmed` |

The mail adapter can map these headers to email properties. **Header names should be taken from `MailHeaders` constants**, rather than guessing raw strings like `"to"` or `"subject"`.

### Headers Are Integration Message Metadata

```text
Message<String>
  payload = "Hello"
  headers:
    mail_to      = "tester@example.net"
    mail_from    = "notify@example.org"
    mail_subject = "Test"
    id           = UUID of Spring Message
    timestamp    = ...
```

This is a conceptual view; the actual string names of headers must use the constants from the library version. `id` and `timestamp` are Spring message metadata, not automatically placed into `Message-ID` and `Date` in MIME.

## 9. Header Enricher to Separate Content from Delivery Metadata

Instead of having every producer set recipient and sender itself, a flow can use a **header enricher** before the outbound adapter:

```text
Message<String> body
       |
       v
Header Enricher
  mail_to = ...
  mail_from = ...
  mail_subject = ...
       |
       v
Outbound Mail Adapter
```

DSL example with fixed test values:

```java
@Bean
public IntegrationFlow simpleMailFlow(
        JavaMailSender mailSender
) {
    return IntegrationFlow
            .from("mailBodyInput")
            .enrichHeaders(h -> h
                    .header(
                            MailHeaders.TO,
                            "tester@example.net"
                    )
                    .header(
                            MailHeaders.FROM,
                            "notify@example.org"
                    )
                    .header(
                            MailHeaders.SUBJECT,
                            "Notification from Integration"
                    ))
            .handle(Mail.outboundAdapter(mailSender))
            .get();
}
```

This example illustrates DSL usage and is not suitable for sending to different recipients when every email uses a fixed To value. In practice, you can enrich from a DTO payload or a validation/transformer step.

### Why Enrich in One Place?

- Centralizes From and Reply-To rules.
- Reduces the chance of individual producers forgetting to set Subject.
- Allows route/tenant-specific policy before reaching the adapter.
- Makes it easy to test header mapping independently from SMTP.
- Helps separate the business payload from mail transport properties.

However, if a header enricher overwrites `MailHeaders.TO` from the producer without control, it can send to the **wrong recipient**. Overwrite/default-overwrite rules must be decided by the flow contract.

## 10. MailHeaders Can Override MailMessage

If the payload is a `MailMessage` that already has a To property, but the Spring Integration Message carries a different `MailHeaders.TO`, Spring Integration documentation states that **the mail header can be used to override the corresponding value in MailMessage**.

```text
Payload MailMessage:
  To = original@example.net

Integration Message Header:
  MailHeaders.TO = override@example.net

After mapping in mail outbound handler:
  Recipient may become override@example.net
```

This is a common source of security and correctness bugs. For instance, if the payload was built from a verified notification but a subsequent enricher step pulls To from untrusted data, the email could be sent to the wrong destination.

Recommendations:

1. Set the recipient in **only one place with clear ownership**.
2. If overriding is required, have an explicit policy and validation.
3. Never let arbitrary user input become an unvalidated mail header.
4. Write a test case with both To in the payload and To in the header to verify precedence.
5. Avoid forwarding all headers from an external message without an allowlist.

## 11. String Payload: Simplest Approach for Text Mail

When the payload is a `String`, the mail outbound handler can create a simple text message and use mail headers to set recipient, subject, and sender.

```java
var integrationMessage = MessageBuilder
        .withPayload("Order paid successfully.")
        .setHeader(MailHeaders.TO, "buyer@example.net")
        .setHeader(MailHeaders.FROM, "billing@example.org")
        .setHeader(MailHeaders.SUBJECT, "Payment successful")
        .build();

outboundMail.send(integrationMessage);
```

Suitable for:

- Plain-text notifications that do not require HTML formatting.
- Demo flows or simple internal notifications.
- Transformer output that is already a complete `String`.

Do not assume a `String` containing `"<h1>Hello</h1>"` will automatically be treated as HTML with `Content-Type: text/html`. To send HTML, inline images, or intentional attachments, use an explicit MIME-building step matching the handler's contract.

## 12. MailMessage Payload: Separating Mail Building from Sending

`MailMessage` is Spring Mail's abstraction, with implementations such as `SimpleMailMessage` for simple content.

```java
import org.springframework.mail.SimpleMailMessage;

SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("notify@example.org");
mail.setTo("tester@example.net");
mail.setSubject("Account notification");
mail.setText("Your account has been updated.");

Message<SimpleMailMessage> request = MessageBuilder
        .withPayload(mail)
        .build();

outboundMail.send(request);
```

When receiving a `MailMessage` payload, the handler can pass the prepared mail object to the sender. This is a way to keep content composition logic at the transformer/business boundary, while the adapter only handles submission.

### Do Not Share a Mutable Object Across Multiple Notifications

`SimpleMailMessage` is mutable. If the same instance is shared across threads and modified via `setTo`/`setText`, content and recipients can get mixed up. Each notification should have its own payload or use an immutable DTO for steps prior to composition.

## 13. byte[] Payload and Attachment Filename

The `MailSendingMessageHandler` documentation describes the ability to map a `byte[]` payload into an attachment; in that case, the `MailHeaders.ATTACHMENT_FILENAME` header is required to specify the file name.

```java
byte[] fileBytes = loadSyntheticBytes();

Message<byte[]> request = MessageBuilder
        .withPayload(fileBytes)
        .setHeader(MailHeaders.TO, "tester@example.net")
        .setHeader(MailHeaders.FROM, "report@example.org")
        .setHeader(MailHeaders.SUBJECT, "Test file")
        .setHeader(
                MailHeaders.ATTACHMENT_FILENAME,
                "sample.bin"
        )
        .build();

outboundMail.send(request);
```

`loadSyntheticBytes()` is a hypothetical application method; when testing, use dummy bytes and an SMTP sandbox.

Limitations:

- Does not automatically build a complex HTML email from `byte[]` alone.
- Do not omit the filename header when the handler contract requires it.
- Do not put files containing sensitive data into uncontrolled logs or test environments.
- For large files, `byte[]` can create memory pressure; consider a dedicated composition step using a re-readable resource.

## 14. DTO Payload and Transformer

A business DTO usually carries more data than a text string:

```java
public record OrderMailCommand(
        UUID notificationId,
        String recipient,
        String orderCode,
        String customerDisplayName
) {}
```

Do not push that DTO directly into the mail adapter and hope the adapter guesses `recipient` and `subject`. Instead, use a transformer or header enricher:

```text
Message<OrderMailCommand>
        |
        v
Validate + Render
        |
        v
Message<String> + MailHeaders.*
        |
        v
Mail adapter
```

Example of preparing a message from a DTO:

```java
public Message<String> toTextMail(
        OrderMailCommand command
) {
    String body = "Hello " + command.customerDisplayName()
            + ", order " + command.orderCode()
            + " has been confirmed.";

    return MessageBuilder.withPayload(body)
            .setHeader(MailHeaders.TO, command.recipient())
            .setHeader(
                    MailHeaders.FROM,
                    "orders@example.org"
            )
            .setHeader(
                    MailHeaders.SUBJECT,
                    "Confirmation " + command.orderCode()
            )
            .setHeader(
                    "appNotificationId",
                    command.notificationId().toString()
            )
            .build();
}
```

Note: `appNotificationId` is an **application-defined internal header**, not an SMTP/MIME header or a Spring Integration Mail constant. Do not assume this header will be echoed back by the provider in delivery webhooks. And recipient/orderCode/displayName values must be validated and encoded/escaped appropriately for the transport and content type.

## 15. Java DSL with Mail.outboundAdapter(host)

Besides passing a `JavaMailSender` bean, Spring Integration Java DSL provides a factory to create an outbound mail adapter by hostname:

```java
@Bean
public IntegrationFlow smtpMailFlow() {
    return IntegrationFlow.from("outboundMail")
            .handle(
                    Mail.outboundAdapter("127.0.0.1")
                            .port(2525)
                            .protocol("smtp")
            )
            .get();
}
```

This example points to a **local SMTP test server on localhost** at port 2525. In a real project, hostname, port, credentials, and TLS settings need to be managed via configuration/secret manager, not hard-coded in source code.

When trying credential configuration directly, Java DSL provides a form like:

```java
Mail.outboundAdapter(smtpHost)
        .port(smtpPort)
        .credentials(smtpUsername, smtpPassword)
        .protocol("smtp")
        .javaMailProperties(properties ->
                properties.put(
                        "mail.smtp.starttls.enable",
                        "true"
                ));
```

This is a DSL describing the adapter; it does not send mail when the bean is initialized. Sending only happens when the flow receives a matching message and the mail handler is invoked.

### When Should You Choose an Injected JavaMailSender?

When a shared `JavaMailSender` is already configured in Spring Boot, using:

```java
.handle(Mail.outboundAdapter(javaMailSender))
```

is usually convenient because it:

- Reuses SMTP host/port, timeouts, TLS, and authentication policy.
- Makes it easy to swap in a sender pointing to an SMTP test server during tests.
- Allows managing multiple separate provider sender beans.
- Avoids scattering mail configuration across integration flows and application properties.

Do not configure both places simultaneously and assume they are guaranteed to stay in sync. If a sender bean and an adapter-host DSL carry two different configurations, you must know which sender the flow actually uses.

## 16. SMTP Configuration in Spring Boot

One way to configure `JavaMailSenderImpl` via Spring Boot:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
```

Notes:

- `STARTTLS` and SMTP implicit TLS are two different connection modes; port and properties must match the provider.
- Do not enable `mail.debug` containing sensitive information in production.
- Timeouts are examples and should be chosen based on workload and SLA; do not block workers indefinitely if a server hangs.
- Credentials should come from secret management, never committed to the repository.
- Specific properties must be compatible with the Jakarta Mail/Angus Mail library on the classpath.

When a flow uses `Mail.outboundAdapter(javaMailSender)`, it uses the configured sender. **Spring Integration does not replace the need for accurate SMTP configuration.**

## 17. Configuration with @ServiceActivator

Spring Integration also supports attaching a `MessageHandler` to a channel using an annotation:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.mail.MailSendingMessageHandler;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.messaging.MessageHandler;

@Configuration
public class MailHandlerConfiguration {

    @Bean
    @ServiceActivator(inputChannel = "outboundMail")
    public MessageHandler outboundMailMessageHandler(
            JavaMailSender mailSender
    ) {
        return new MailSendingMessageHandler(mailSender);
    }
}
```

`@ServiceActivator` registers the handler to consume from `outboundMail`. `MailSendingMessageHandler` is the component that performs mail mapping and delegates sending.

### How Do Java DSL and Annotations Differ?

| Declaration Style | Advantage | When to Use |
| --- | --- | --- |
| `@ServiceActivator` + `MailSendingMessageHandler` | Directly shows the handler and channel | Concise config, need to customize handler |
| `IntegrationFlow.from(...).handle(Mail.outboundAdapter(...))` | Easy to chain enrich/transform/filter/route steps | Pipelines with multiple endpoints |
| XML `int-mail:outbound-channel-adapter` | Fits projects using XML config | Legacy or existing XML configuration |

**Choose one actual consumer registration style per purpose.** If you accidentally register both `@ServiceActivator(inputChannel="outboundMail")` and a flow consuming the same `DirectChannel`, the result is not necessarily that every message goes through both. `DirectChannel` has a subscriber dispatching mechanism; do not rely on subscriber count to accidentally send "copies".

## 18. XML Outbound Channel Adapter

For projects using XML configuration, a common form is:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:int="http://www.springframework.org/schema/integration"
       xmlns:int-mail="http://www.springframework.org/schema/integration/mail"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd
         http://www.springframework.org/schema/integration
         https://www.springframework.org/schema/integration/spring-integration.xsd
         http://www.springframework.org/schema/integration/mail
         https://www.springframework.org/schema/integration/mail/spring-integration-mail.xsd">

    <int:channel id="outboundMail"/>

    <int-mail:outbound-channel-adapter
        channel="outboundMail"
        mail-sender="mailSender"/>
</beans>
```

`mailSender` is a separately declared bean. In Java DSL exercises, do not also add this XML, to avoid configuring two endpoints that unintentionally consume from the same channel.

## 19. DirectChannel: Synchronous Handoff

`DirectChannel` is a `SubscribableChannel`. When a message is sent to the channel, the subscriber handler is normally invoked on the **sending thread**.

```text
HTTP request thread
      |
      v
outboundMail.send(message)
      |
      v
DirectChannel dispatch
      |
      v
MailSendingMessageHandler
      |
      v
JavaMailSender.send(...) -> SMTP I/O
      |
      v
Caller receives completion or exception
```

### Advantages

- Easy to reason about because the flow runs almost like a synchronous call stack.
- The caller can receive downstream exceptions when sending fails.
- No separate thread pool needed if traffic is small.
- Straightforward flow debugging.

### Disadvantages

- The caller is blocked while building/sending the SMTP message.
- If the caller is an HTTP request, latency depends on network/provider.
- If inside a database transaction, it can hold the transaction/connection for a long time.
- Does not provide a queue or durable retry capability on its own.
- Under high traffic, many request threads may send mail concurrently and put pressure on SMTP.

Do not choose synchronous DirectChannel just because it requires minimal configuration while ignoring SMTP submission duration inside main transactions.

## 20. QueueChannel: Accept Work First, Process Later

`QueueChannel` is a `PollableChannel`. The producer places messages into a queue; a **poller** pulls messages from the queue and invokes the mail handler.

```text
Producer thread
     |
     v
QueueChannel (bounded)
     |
     +--> message stored in channel buffer
              |
              v
          Poller thread
              |
              v
       Mail outbound adapter
              |
              v
             SMTP
```

This can reduce producer wait time, but carries risks:

- A default QueueChannel usually lives **in memory**, not as a durable queue.
- If the process restarts, unprocessed messages may be lost.
- If the queue is full, `send(...)` may fail, block until timeout, or be rejected depending on call style/configuration.
- A message polled from the queue does not automatically return to the queue when the SMTP handler throws an exception; retry/requeue mechanics must be designed.
- The producer receiving `send=true` **does not mean SMTP has executed**.

### Queue with Bounded Capacity

```java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.PollableChannel;

@Bean
public PollableChannel queuedMailRequests() {
    return new QueueChannel(100);
}
```

`100` is only an illustrative value. Queue capacity should be based on peak load, SMTP latency, RAM, and admission policy. Do not push tens-of-MiB `byte[]` attachments into thousands of queued messages.

## 21. Poller for Outbound Adapter Reading a PollableChannel

When an endpoint's source is a `QueueChannel`, a **poller** is needed to pull messages out. Spring Integration DSL supports configuring a poller on the endpoint:

```java
@Bean
public IntegrationFlow queuedMailFlow(
        PollableChannel queuedMailRequests,
        JavaMailSender mailSender
) {
    return IntegrationFlow.from(queuedMailRequests)
            .handle(
                    Mail.outboundAdapter(mailSender),
                    endpoint -> endpoint.poller(
                            p -> p.fixedDelay(1000)
                                  .maxMessagesPerPoll(5)
                    )
            )
            .get();
}
```

Values in the example:

- `fixedDelay(1000)`: illustrates polling on a 1,000 ms cycle.
- `maxMessagesPerPoll(5)`: each poll cycle processes at most 5 messages as configured.
- Does not mean a system-wide limit of 5 SMTP connections.
- Does not guarantee exactly-once or durable delivery on its own.

### What Happens Without a Poller?

For an endpoint wired to a `PollableChannel`, a corresponding poller configuration is required (directly or via an appropriate default poller). Without one, the endpoint lacks an active mechanism to drain messages from the queue as intended, or the configuration may be invalid.

This is a key distinction from `DirectChannel`, where the producer pushes messages directly to a subscribed handler and no poller is needed.

## 22. ExecutorChannel: Async Dispatch via TaskExecutor

`ExecutorChannel` uses a `TaskExecutor` to dispatch processing to another thread:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskExecutor;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.messaging.MessageChannel;

@Bean
public MessageChannel asyncMailChannel(
        TaskExecutor mailTaskExecutor
) {
    return new ExecutorChannel(mailTaskExecutor);
}
```

If the sender processes through this channel:

```text
HTTP thread --> ExecutorChannel
                    |
                    v
                TaskExecutor
                    |
                    v
               Worker thread
                    |
                    v
              SMTP mail handler
```

**There is no poller** like QueueChannel, because ExecutorChannel is a subscribable channel dispatching via an executor.

### Things to Consider

- An SMTP exception in the worker does not automatically return to the HTTP caller after a successful handoff.
- Error handling must be properly configured for the async boundary.
- `ThreadPoolTaskExecutor` must have bounds, queue capacity, and a rejection policy.
- ExecutorChannel does not provide database durability by itself.
- Tasks rejected by the executor must be recorded and handled so notifications are not lost.
- The caller's transaction context usually **does not cross the thread boundary** the way it does on the same thread.

If emails are critical, an in-memory executor should only be an execution layer; send requests should be persisted in a database/outbox or durable broker beforehand.

## 23. Comparing the Three Channels by Caller-Observed Outcome

| Channel | Handoff Mechanism | Does Caller Wait for SMTP? | Survives Restart? | Error Handling |
| --- | --- | --- | --- | --- |
| `DirectChannel` | Synchronous dispatch on caller thread | Usually yes | Not by default | Downstream exceptions usually return to caller |
| `ExecutorChannel` | Hands off work to executor | Usually no after handoff | Not by default | Asynchronous error handling |
| `QueueChannel` | Enqueues for poller | No when only enqueueing | In-memory default does not | Errors at poller/worker, needs policy |

**Choosing a channel means choosing processing semantics**, not just picking a bean name. When changing a flow from DirectChannel to ExecutorChannel, exception behavior, transactions, observability, and API responses can all change.

## 24. Do Not Use PublishSubscribeChannel to Send Email Accidentally

`PublishSubscribeChannel` can broadcast the same message to **multiple subscribers**:

```text
              PublishSubscribeChannel
                 /           \
                v             v
        Mail handler A   Mail handler B
                |             |
                v             v
             SMTP A        SMTP B
```

This structure is appropriate when you intentionally want to multicast an event to multiple independent consumers. However, if two subscribers both send email, a single notification may be sent **twice**.

To choose one of two SMTP providers, use routing or an explicit route selector rather than attaching two outbound mail adapters to the same publish-subscribe channel and hoping the framework picks one.

### Multiple Subscribers on DirectChannel Is Not Broadcast Either

`DirectChannel` dispatches messages to a subscriber according to the channel's dispatching strategy. Do not register multiple mail handlers on a single DirectChannel as an uncontrolled backup/failover mechanism: the outcome depends on the dispatcher, load balancing, and exception behavior. If provider routing is needed, design and test it in a dedicated layer.

## 25. Is a Reply Channel Needed?

An outbound mail adapter is a **one-way consumer**. Normally it does not emit a reply message stating that the mail was delivered.

```text
Input Channel -> Outbound Mail Adapter -> External SMTP
                    |
                    +-- no ordinary reply payload
```

Therefore, writing a request-reply gateway that requires a `replyChannel` and waits for a reply from the adapter mismodels the flow. If you need a business outcome:

- Use the submission outcome captured at the send-handling layer.
- Persist status by notification/attempt ID in a repository.
- Optionally emit a separate **status event** after SMTP submission.
- Receive provider webhooks/bounce feedback for later delivery outcomes.

Do not generate a `DELIVERED` reply immediately when `JavaMailSender.send(...)` returns; that is only an observable submission result.

## 26. Gateway Keeps Business Services Unaware of MessageChannel

`@MessagingGateway` can provide an interface that looks like a regular Java method while routing calls into a Spring Integration channel.

```java
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.mail.MailHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@MessagingGateway(defaultRequestChannel = "outboundMail")
public interface TextMailGateway {

    void sendText(
            @Payload String text,
            @Header(MailHeaders.TO) String to,
            @Header(MailHeaders.FROM) String from,
            @Header(MailHeaders.SUBJECT) String subject
    );
}
```

Business service:

```java
@Service
public class OrderNotificationService {

    private final TextMailGateway mailGateway;

    public OrderNotificationService(
            TextMailGateway mailGateway
    ) {
        this.mailGateway = mailGateway;
    }

    public void notifyOrder() {
        mailGateway.sendText(
                "Order confirmed.",
                "tester@example.net",
                "orders@example.org",
                "Order confirmation"
        );
    }
}
```

Ensure appropriate component scan/`@IntegrationComponentScan` configuration so Spring creates the gateway proxy in your project version. A `void` method illustrates a **one-way** send flow with no ordinary reply payload.

**Important:** when using DirectChannel, the gateway call may block until SMTP submission finishes; when using an async/queue channel, the gateway may return right after handoff. Changing the channel can alter business method response times without modifying the interface.

## 27. Common Mistakes When Using a Gateway

| Symptom | Possible Cause |
| --- | --- |
| Gateway bean is not created | Missing component scan/IntegrationComponentScan |
| No handler for channel | Wrong channel name or flow not registered |
| Gateway waits for a nonexistent reply | Interface/gateway configured as request-reply for a one-way adapter |
| Method returns early before SMTP finishes | Async/queue boundary |
| SMTP exception does not reach caller | Processing runs on a worker thread |
| Sent to wrong To/Subject | Incorrect header mapping or precedence |
| Complex DTO used but body is wrong | Missing transformer/mapper |
| Mail-sending method called twice | Two business flows or retry creating duplicates |

A gateway **simplifies the business-side interface**, but does not replace defining reliability and sending outcomes.

## 28. When Using Async, Where Should Status Be Recorded?

A pipeline can record milestones:

```text
BusinessEvent
      |
      v
Notification stored (PENDING)
      |
      v
Publish to channel / claim
      |
      v
Compose mail (PROCESSING)
      |
      v
Mail outbound adapter -> SMTP
      |
      +-- known success --> SUBMITTED
      |
      +-- known failure --> RETRY_WAIT or FAILED
      |
      +-- uncertain result --> UNKNOWN
```

To update status accurately, the business service should not record `SUBMITTED` immediately when `QueueChannel.send(...)` returns `true`. A worker or monitoring layer around the send operation must record the outcome when SMTP submission actually executes.

When multiple components exist in a flow, identify **who owns the status** so two places do not overwrite status with conflicting definitions.

## 29. Error Handling with DirectChannel

With `DirectChannel`, the adapter usually runs in the same call stack when the producer calls `send(...)`. If the SMTP transport encounters an error, the exception can propagate back to the caller, sometimes wrapped by Spring Integration in `MessagingException`.

```java
try {
    outboundMail.send(integrationMessage);
} catch (org.springframework.messaging.MessagingException ex) {
    // Exceptions from the flow may be wrapped.
    // Attach notificationId and classify the error safely.
    recordIntegrationFailure(notificationId, ex);
}
```

Illustrative example; you must also handle Spring Mail exceptions and runtime exceptions appropriate to the flow contract. Do not assume every error is wrapped in a single `MessagingException` class.

### SMTP Failure Is Not Like Validation Failure

| Error | Stage Where It Can Occur | Handling |
| --- | --- | --- |
| Malformed recipient input | Validation/transform/compose | Block before adapter |
| Missing `MailHeaders.TO` | Mapping/compose | Fail fast, alert on configuration |
| Template render exception | Transformer | Do not send incomplete email |
| SMTP authentication error | Mail sender | Fix credential/config, do not blindly retry |
| Temporary SMTP 4xx | Transport | Retry with backoff per policy |
| Permanent SMTP 5xx | Transport | Classify, fix recipient/policy |
| Timeout after DATA | Transport | Outcome may be `UNKNOWN` |
| Executor/Queue rejection | Channel/admission | Must not report submitted |

Avoid a broad `catch (Exception)` that always retries the same message without knowing whether the SMTP server already accepted it.

## 30. Asynchronous Error Handling

When a message goes through `ExecutorChannel` or a `QueueChannel` poller, the caller may have already received a "channel accepted" result long ago. Exceptions raised in the mail handler **do not automatically propagate back to the HTTP caller**.

```text
HTTP request
   |
   v
ExecutorChannel.submit()
   |
   +--> HTTP returns ACCEPTED
                |
                v
         Worker executes mail handler
                |
                +--> SMTP exception
                         |
                         v
                   Async error path
```

Spring Integration has an `errorChannel`/`ErrorMessage` mechanism for asynchronous error handling, but how errors are published depends on the configured channel, poller, task executor, and endpoint error handler. Do not assume every exception automatically appears on a channel without a listener.

### A Simple Error Handler

```java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class MailErrorConsumer {

    @ServiceActivator(inputChannel = "mailErrors")
    public void consume(ErrorMessage errorMessage) {
        Throwable failure = errorMessage.getPayload();

        // Log controlled error class/correlation ID.
        // Do not log full failedMessage, body, or recipient.
        recordMailFailureClass(
                failure.getClass().getSimpleName()
        );
    }
}
```

`recordMailFailureClass(...)` is an illustrative method. For the handler to actually receive errors, you must **configure the error channel of the async flow/poller** or route `ErrorMessage` to the `mailErrors` channel using the API for your version. Merely declaring `@ServiceActivator` above is not enough to guarantee all SMTP errors arrive there.

### When the Error Handler Itself Fails

If the error handler throws an exception or cannot write to the database, you need a clear operational strategy. You can use a durable event/outbox and retry processing so notifications are not lost; do not handle errors by immediately retrying SMTP send inside the error channel without classifying the outcome first.

## 31. ErrorMessage May Contain Sensitive Information

A Spring Integration error may carry a reference to `failedMessage`. Its payload/headers may contain:

- To/Cc/Bcc recipients.
- Customer name or content.
- OTP/magic link/reset token.
- Attachment bytes or resource paths.
- Internal correlation metadata.

Do not do:

```java
logger.error(
        "Mail failed: {}", errorMessage
);
```

and do not serialize the raw `failedMessage` into monitoring events. It is better to log internal `notificationId`/`attemptId`, error type, SMTP stage if evidenced, provider route, and outcome.

### Minimal Diagnostic Sample

```text
notificationId=N-400-123
attemptId=A-400-001
channel=outboundMail
stage=SMTP_SUBMISSION
exceptionClass=MailSendException
outcome=UNKNOWN
```

Do not guess `outcome=FAILED` when a timeout may have occurred after the server already received DATA. Classification must be based on operational context.

## 32. Do Exceptions from MailSendingMessageHandler Automatically Carry Delivery Status?

No. The adapter delegates to `JavaMailSender`, while `MailSendException`, `MailAuthenticationException`, and transport exceptions only describe errors observed during build/submit.

A `MailSendException` may contain:

- A list of failed message objects at the attempt level.
- Nested exceptions from Jakarta Mail.
- Some valid or rejected recipient details if provided by the transport.

However:

- A single message may have multiple SMTP recipients.
- A recipient acknowledged with `250` at RCPT has not necessarily received DATA.
- `sendpartial=true` can cause some recipients to be submitted while the handler still throws an exception.
- A timeout after DATA creates an uncertain state.
- Successful SMTP submission does not mean the email reached the Inbox.

Therefore, the outbound adapter should be paired with a **status management layer** if the product has retries or SLAs.

## 33. Do Not Use an In-Memory Queue as a Durable Mail Outbox

An error-prone architecture:

```text
OrderService updates database
       |
       v
QueueChannel with in-memory queue
       |
       +--> Process crashes before poll
       |
       v
Email request is lost
```

Even when `QueueChannel.send(...)` returns `true`, it only proves the message was accepted by the channel at that moment, with **no guarantee of surviving a restart** if the channel has no corresponding durable store.

### When Is QueueChannel Enough?

- Demos or experimental applications.
- Non-critical emails where losing tasks on restart is acceptable.
- Pipelines with a durable upstream source that can replay according to policy.
- Workloads where losing a notification causes no business impact.

For critical transactional emails, consider a **transactional outbox**, durable queue, or persistence mechanism with confirmation and retry. Spring Integration has other message stores/channel adapters, but their contracts must be configured properly rather than just renaming a channel.

## 34. Transactional Outbox with Spring Integration

A reference architecture:

```text
Business transaction
  UPDATE order
  INSERT mail_notification(PENDING)
          |
          v
        COMMIT
          |
          v
Outbox dispatcher / poller
          |
          v
MessageChannel (carries notification ID / DTO)
          |
          v
Load data + validate + compose
          |
          v
Outbound Mail Adapter
          |
          v
SMTP submission
          |
          v
Persist attempt outcome
```

In this design, the channel can be used to **organize the flow** while the database/outbox guarantees send requests are not lost on process restart.

### Suggested Outbox Data

```text
notification_id
recipient_id
template_key
template_version
data_reference
status = PENDING / PROCESSING / SUBMITTED /
         RETRY_WAIT / FAILED / UNKNOWN
attempt_count
next_attempt_at
created_at
```

It is not mandatory to store raw HTML/MIME or attachment bytes in the database. You can store references to durable data, provided the content is not deleted or altered inconsistently across attempts.

## 35. Do Not Hold a Database Transaction Open During SMTP Send

A problematic example:

```java
@Transactional
public void processMail(UUID notificationId) {
    Notification n = repository.findById(
            notificationId
    ).orElseThrow();

    // Network I/O operation may take several seconds.
    outboundMail.send(toIntegrationMessage(n));

    n.markSubmitted();
}
```

If `outboundMail` is a `DirectChannel`, `send(...)` may call SMTP directly inside the DB transaction. This holds JDBC connections/locks for a long time, and a DB rollback **cannot recall an email already accepted by SMTP**.

Instead, separate them:

1. Claim the notification in a short transaction.
2. Load/render/submit outside any long transaction.
3. Record the outcome in another short transaction.
4. Have a mechanism to handle crashes between SMTP acceptance and the DB update.

This is a reliability trade-off that is not solved simply by replacing `DirectChannel` with `ExecutorChannel`.

## 36. Retry Mechanism: Where Should Ownership Live?

Multiple layers can retry:

- Spring Integration advice/retry around the handler.
- Poller error handling and requeue.
- Worker/outbox scheduler.
- SMTP provider automatically retrying delivery after acceptance.

If all of them retry without coordination, a single notification may be sent multiple times.

### Principles

1. Have **a single owner** responsible for submission retries per notification/attempt.
2. Record each attempt ID, recipient scope, and provider route.
3. Distinguish errors guaranteed not submitted from ambiguous outcomes.
4. Do not retry an entire batch if part of it was already sent.
5. Respect suppression and unsubscribe policies.
6. Configure max attempts, backoff, and jitter.
7. Do not treat `Message-ID` as a universal SMTP deduplication key.
8. Only enable retry advice when its actual behavior matches your policy.

### Example Retry Policy at the Business Layer

```text
Mail handler failure
      |
      v
Classify:
  connection failed before submission -> RETRY_WAIT
  temporary SMTP 4xx (known)          -> RETRY_WAIT
  invalid recipient / permanent       -> FAILED
  timeout after DATA                  -> UNKNOWN
      |
      v
Persist outcome
      |
      v
Outbox worker schedules next attempt if allowed
```

When using Spring Integration retry advice, check the risk of retrying too close to the SMTP side effect: if the previous send was actually received by the server without the client receiving the response, re-invoking the handler can create duplicates.

## 37. Rate Limiting and Backpressure on Message Channels

SMTP providers may enforce limits on:

- Messages per second.
- Recipients per message.
- Concurrent connections.
- MIME size.
- Per-account/domain quota.
- AUTH or session frequency.

Channel choice affects how the system reacts to overload:

| Channel | Overload Symptom | Mitigation |
| --- | --- | --- |
| DirectChannel | Caller/request threads blocked for long periods | Separate durable scheduling, reduce synchronous sending |
| ExecutorChannel | Executor queue grows, tasks rejected | Bounded pool, backpressure, admission |
| QueueChannel | Capacity limit reached, poller falls behind | Bounded capacity, handle rejections |
| Durable broker/outbox | Lag/backlog increases | Scale workers within quota, alert on queue age |

An email with a 20 MiB PDF attachment does not have the same cost as a 1 KiB text email. Do not count only queued messages when size dimensions can cause heap, disk, and network pressure.

### Do Not Add Workers Unboundedly

If an SMTP provider only allows a maximum number of connections or throughput, adding excessive workers can trigger `421/4xx` errors, timeouts, retry storms, and lower overall success rates. Set limits according to actual resources and measure queue lag, error rate, and submit latency.

## 38. Oversized Payloads in QueueChannel

An anti-pattern:

```java
record MailWork(
        UUID notificationId,
        String recipient,
        byte[] invoicePdf
) {}
```

If a queue has 1,000 tasks, each holding an independent 10 MiB PDF, the byte arrays alone occupy around 10,000 MiB in memory, not counting MIME and other objects.

An alternative:

```java
record MailWorkReference(
        UUID notificationId,
        UUID recipientId,
        String attachmentStorageKey
) {}
```

The worker fetches the file when its turn comes, ensuring the source is re-readable and persists across retries. However, the storage key must be protected and point to immutable/versioned content; do not automatically store sensitive data at public URLs.

## 39. Header Filters and Security

In an integration flow, messages can arrive from HTTP, JMS, Kafka, or other systems. If all headers are copied into the outbound mail adapter, untrusted data can interfere:

- `MailHeaders.TO`, `BCC`: changes recipients, leaks information.
- `MailHeaders.FROM`: spoofs sender domain.
- `MailHeaders.REPLY_TO`: redirects replies to a malicious address.
- `MailHeaders.SUBJECT`: injects unwanted values.
- Correlation headers containing access tokens or internal data.

### Control Principles

- Only allow mail headers produced by authenticated and validated code.
- Do not accept arbitrary `From` from an HTTP request if policy restricts to specific sender domains.
- Bcc must be handled according to permissions and purpose.
- Do not echo all headers into the email body or MIME.
- Limit subject length, recipient count, and attachment size.
- Do not use message headers to store long-lived passwords/tokens.
- Apply HTML escaping at the template layer.

**A Header Enricher is not an automatic security mechanism.** It merely sets or computes values; the application must determine which data sources are trusted.

## 40. Outbound Mail Adapter and Complex MIME

Text mail can be handled cleanly with `String` and `MailHeaders`. However, HTML, plain-text alternatives, inline images, and attachments mostly require dedicated MIME logic.

```text
OrderMailCommand
       |
       v
HTML template renderer
       |
       v
MimeMessageHelper:
  setText(plain, html)
  addInline(contentId, resource)
  addAttachment(name, resource)
       |
       v
MimeMessage
       |
       v
JavaMailSender.send(MimeMessage)
```

Do not expect a `String` containing HTML tags to have the outbound handler automatically add multipart/related, CIDs, Content-Type, or business-specific attachments.

### When to Use a Custom Handler for MimeMessage

If the flow has already built a `jakarta.mail.internet.MimeMessage`, an approach with a clear contract is writing a dedicated handler that calls `JavaMailSender.send(MimeMessage)`:

```java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.messaging.MessageHandler;

@Bean
public MessageHandler preparedMimeHandler(
        JavaMailSender sender
) {
    return integrationMessage -> {
        Object payload = integrationMessage.getPayload();
        if (!(payload instanceof MimeMessage mime)) {
            throw new IllegalArgumentException(
                    "Expected MimeMessage payload"
            );
        }
        sender.send(mime);
    };
}
```

Then:

```java
@Bean
public IntegrationFlow preparedMimeFlow(
        MessageHandler preparedMimeHandler
) {
    return IntegrationFlow.from("preparedMimeMail")
            .handle(preparedMimeHandler)
            .get();
}
```

**Distinguish clearly:** this is a **custom outbound MessageHandler in Spring Integration**, not a claim that every version of `MailSendingMessageHandler` automatically accepts every `MimeMessage` payload form through the same mapping. When complex MIME is required, using a transformer/handler with an explicit contract is easier to test.

### Thread-Safety Note

`MimeMessage` is mutable. Do not pass the same instance across multiple threads and modify subject/recipient/attachment concurrently. If the queue is asynchronous, let the worker own building and sending the MIME message for each notification/attempt.

## 41. A Clear Flow: DTO -> Header Enricher -> Text -> Mail Adapter

We can combine the core components:

```text
OrderMailCommand
       |
       v
mailCommands (DirectChannel)
       |
       v
Header Enricher
  - TO from validated recipient
  - FROM from system address
  - SUBJECT from orderCode
       |
       v
Transformer
  OrderMailCommand -> String
       |
       v
Mail Outbound Adapter
       |
       v
SMTP test/sandbox
```

Java DSL example:

```java
@Bean
public IntegrationFlow orderTextMailFlow(
        JavaMailSender mailSender
) {
    return IntegrationFlow.from("mailCommands")
            .enrichHeaders(h -> h
                    .headerExpression(
                            MailHeaders.TO,
                            "payload.recipient"
                    )
                    .header(
                            MailHeaders.FROM,
                            "orders@example.org"
                    )
                    .headerExpression(
                            MailHeaders.SUBJECT,
                            "'Confirmation ' + payload.orderCode"
                    ))
            .transform(
                    OrderMailCommand.class,
                    command -> "Order "
                            + command.orderCode()
                            + " has been confirmed."
            )
            .handle(Mail.outboundAdapter(mailSender))
            .get();
}
```

`OrderMailCommand` is the record declared earlier, with `recipient()` and `orderCode()` accessors. In Spring Expression Language (SpEL), record property access depends on the Spring/SpEL version; if a project cannot resolve `payload.recipient` or `payload.orderCode`, use the corresponding accessor call syntax or an explicit plain Java transformer/enricher. Code must be verified against the actual Spring Integration and Spring Framework versions.

### Why Enrich Before Transforming?

At the start of the flow, the payload is `OrderMailCommand`, so it has `recipient` and `orderCode`. After transforming, the payload is the body `String` and no longer has those properties. If `headerExpression("payload.recipient")` is placed after the transform step, the expression will not find the field.

Therefore, endpoint ordering is not just a matter of presentation:

```text
DTO -> enrich headers -> render body -> send
```

and

```text
DTO -> render body -> enrich from DTO properties -> send
```

are not equivalent unless you have explicitly preserved the DTO data in headers or a separate context.

## 42. Choosing a Transformer for Complex DTOs

A real-world email flow typically has these steps:

1. Validate notification status and recipient eligibility.
2. Select template version.
3. Load snapshotted or versioned data.
4. Render plain/HTML.
5. Create attachments or immutable resource references.
6. Build mail message.
7. Submit using the mail sender.

A transformer is where **data representation** changes, not necessarily where all side effects execute. When each step has a clear contract:

- Unit tests for the transformer only check rendered data.
- Mail composer tests check MIME/headers.
- Outbound adapter tests check submission.
- Integration tests check the full flow against an SMTP sandbox.

Do not turn a transformer into a service that charges money, updates the database, and sends mail all at once. When a flow is retried, those side effects may execute repeatedly.

## 43. Router Between Two Outbound Mail Adapters

If an application has multiple providers or distinct email groups, you can route before the adapter:

```text
mailRequests
      |
      v
Select route
  |
  +---- providerAChannel ---> Adapter A ---> SMTP A
  |
  +---- providerBChannel ---> Adapter B ---> SMTP B
```

When designing:

- The route must be chosen from a list of approved providers.
- Record `providerKey` and `attemptId` before sending.
- Each outgoing route has its own sender/credentials.
- Do not route using arbitrary user input leading to an attacker-controlled SMTP host.
- Do not multicast the same notification to A/B just for "backup" unless duplicates are acceptable.
- Do not automatically fail over an attempt that ended with an SMTP `UNKNOWN` result.

### Example Configuration of Two Flows Consuming Two Channels

```java
@Bean
public IntegrationFlow providerAMailFlow(
        JavaMailSender providerASender
) {
    return IntegrationFlow.from("providerAMail")
            .handle(Mail.outboundAdapter(providerASender))
            .get();
}

@Bean
public IntegrationFlow providerBMailFlow(
        JavaMailSender providerBSender
) {
    return IntegrationFlow.from("providerBMail")
            .handle(Mail.outboundAdapter(providerBSender))
            .get();
}
```

The names `providerAMail` and `providerBMail` are Spring Integration channel endpoints. Routing logic must forward exactly one message to the chosen channel and track the attempt.

## 44. Do Not Confuse a Channel Router with SMTP Retry/Failover

A router chooses the **send path for an untried message**. Retry/failover decides how to handle an **attempt that already had a failed or ambiguous outcome**.

```text
Routing before send:
  Notification N -> choose A -> Attempt 1 on A

Failover after send:
  Attempt 1 on A -> error classification
                   |
                   +--> Retry approved? -> Attempt 2 on B
```

If A already received DATA but the application lost the final response, retrying on B can send a duplicate. Therefore, flow routing must not automatically turn an arbitrary `MailSendException` into "send it next via B".

Most providers continue retrying delivery after acceptance, so receiving a deferred event is not automatically a reason to submit the same email through another provider either.

## 45. Observing Messages at Channel Boundaries

Useful observation milestones:

| Milestone | What Can Be Measured | What Must Not Be Inferred |
| --- | --- | --- |
| Producer creates request | Notification count | SMTP has been called |
| Channel accepts message | Channel acceptance / queue depth | Email has been sent |
| Poller takes message | Queue wait time | SMTP has accepted |
| Transformer completes | Render duration | MIME will render cleanly on all clients |
| Adapter starts | Submission attempt start | Email will be delivered |
| Mail sender returns | Submission duration/result | Inbox arrival |
| Provider delivery webhook | Remote-delivered/bounce if available | User has read it |

Do not use a single metric name `mail_sent_total` for both enqueueing and SMTP acceptance; otherwise, dashboards may report a higher "sent" count than reality when a queue builds a backlog.

### Clear Metric Naming

```text
mail.notifications.created
mail.channel.enqueued
mail.channel.rejected
mail.adapter.attempted
mail.smtp.submitted
mail.smtp.failed
mail.smtp.unknown
mail.queue.oldest.age
mail.provider.remote.delivered
```

The metric names above are application-defined suggestions, not automatic Spring Integration names. An endpoint may provide framework metrics depending on configuration; distinguish framework metrics from business outcome metrics.

## 46. Monitoring and Tracing in IntegrationFlow

A request may traverse multiple endpoints:

```text
HTTP / Event source
      |
      v
Inbound Gateway
      |
      v
Transformer
      |
      v
outboundMail channel
      |
      v
Mail Adapter
      |
      v
SMTP
```

When recording traces:

- Use `notificationId` or an opaque correlation ID.
- Record route, stage, and latency appropriately.
- Limit label cardinality and retention.
- Do not use recipient email, Subject, Bcc, or OTP as trace attributes.
- Do not log the entire Integration Message since the payload may contain content/attachments.

### WireTap Only Observes, Do Not Turn It into an SMTP Duplicate

In Spring Integration, `wireTap` can send a copy of a message to a secondary channel for observation:

```text
outboundMail channel
      |
      +-- tap --> metrics/diagnostic handler
      |
      +--------> mail adapter
```

However, if the secondary channel is also connected to an outbound mail adapter, you can accidentally send a second email. Use wire tap only for **controlled metadata**, avoid storing sensitive bodies/headers, and ensure observation does not affect latency or send outcomes.

## 47. Test 1: Channel + Handler, No Real SMTP Needed

To test flow routing at the channel level, you can replace the mail handler with a test consumer that collects messages.

```java
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import java.util.concurrent.atomic.AtomicReference;
import static org.junit.jupiter.api.Assertions.*;

class DirectChannelRoutingTest {

    @Test
    void deliversMessageToSubscribedHandler() {
        DirectChannel channel = new DirectChannel();
        AtomicReference<Message<?>> observed =
                new AtomicReference<>();

        channel.subscribe(observed::set);

        Message<String> message = MessageBuilder
                .withPayload("Test content")
                .build();

        assertTrue(channel.send(message));
        assertNotNull(observed.get());
        assertEquals(
                "Test content",
                observed.get().getPayload()
        );
    }
}
```

This test verifies the dispatch behavior of `DirectChannel`, **not the mail adapter or SMTP**. It is valuable when developing transformers/headers/filters/routing before wiring up a real sender.

## 48. Test 2: MailSendingMessageHandler Sending via Local SMTP

An integration test can create a `MailSendingMessageHandler` with `JavaMailSenderImpl` and attach it to a `DirectChannel`, then send a `Message<String>` containing `MailHeaders`.

Example using **GreenMail** as an SMTP test server:

```java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.mail.MailHeaders;
import org.springframework.integration.mail.MailSendingMessageHandler;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class OutboundMailAdapterIntegrationTest {

    @Test
    void sendsToLocalSmtpServer() throws Exception {
        GreenMail greenMail = new GreenMail(
                new ServerSetup(
                        0, "127.0.0.1", "smtp"
                )
        );
        greenMail.start();

        try {
            JavaMailSenderImpl sender = new JavaMailSenderImpl();
            sender.setHost("127.0.0.1");
            sender.setPort(greenMail.getSmtp().getPort());

            DirectChannel channel = new DirectChannel();
            channel.subscribe(
                    new MailSendingMessageHandler(sender)
            );

            boolean accepted = channel.send(
                    MessageBuilder.withPayload(
                            "This is a test email."
                    )
                    .setHeader(
                            MailHeaders.TO,
                            "tester@example.net"
                    )
                    .setHeader(
                            MailHeaders.FROM,
                            "notify@example.org"
                    )
                    .setHeader(
                            MailHeaders.SUBJECT,
                            "Mail Integration Test"
                    )
                    .build()
            );

            assertTrue(accepted);
            assertTrue(
                    greenMail.waitForIncomingEmail(5000, 1)
            );

            MimeMessage[] received =
                    greenMail.getReceivedMessages();
            assertTrue(received.length >= 1);
            assertEquals(
                    "Mail Integration Test",
                    received[0].getSubject()
            );
        } finally {
            greenMail.stop();
        }
    }
}
```

The test requires adding a GreenMail dependency compatible with the project's Jakarta Mail namespace. APIs and overloads may vary by version; the example illustrates test organization and does not imply it has been run against the project's test suite.

### What Does the Test Prove?

- DirectChannel delivers the message to the subscribed mail handler.
- The handler maps the text payload + mail headers and invokes the sender.
- The sender can submit to a local SMTP test server.
- The test SMTP server receives a message with the expected Subject.

It does not prove that Gmail/Outlook will render the format properly, nor does it prove the email reached a real person's Inbox.

## 49. Test 3: Verifying MailHeaders Precedence

A scenario to test:

```text
SimpleMailMessage payload:
  To = first@example.net

Integration Message:
  MailHeaders.TO = second@example.net
```

According to the mapping described in the Spring Integration documentation, the `MailHeaders.TO` header takes precedence over the To property.

Testing approach:

1. Create a `SimpleMailMessage` with recipient A.
2. Wrap it in a `Message<?>` with `MailHeaders.TO` = B.
3. Send through the handler to an SMTP test server.
4. Capture **SMTP RCPT TO** or the received recipient to confirm it is B.
5. Verify A was not sent to according to the desired policy.

With this test, reading only the Subject may miss mapping bugs. You need to observe the **actual SMTP envelope recipient**; the `To` header alone is not always enough to prove RCPT commands were issued to the right party.

## 50. Test 4: QueueChannel Does Not Mean Submitted

A unit test can create a `QueueChannel` and **not attach a poller**, then:

```java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

QueueChannel channel = new QueueChannel(2);

Message<String> request = MessageBuilder
        .withPayload("Test email not yet sent")
        .build();

boolean enqueued = channel.send(request);

assertTrue(enqueued);
assertEquals(1, channel.getQueueSize());
```

This example shows that a message can sit in the channel without any email being submitted. In a real test, a poller picks up the message and triggers the handler; only then does an SMTP submission attempt happen.

Do not write an HTTP API that returns "mail delivered" as soon as `QueueChannel.send(...)` returns `true`.

## 51. Test 5: Async Errors Do Not Reach the Caller

A test for `ExecutorChannel` should prove:

- The message can be handed off to the executor.
- The handler runs on a different thread per the executor configuration.
- An SMTP exception is not treated as a synchronous result of the HTTP caller.
- The error channel/handler is configured to receive failures.
- Notification status is updated after worker processing.
- Executor rejection is handled when the queue is full.

Do not use fixed `Thread.sleep(...)` calls to wait; use `CountDownLatch`, `CompletableFuture`, or test framework helpers with bounded timeouts. If a test depends too heavily on thread scheduling, it will become flaky on CI.

## 52. Test 6: Sending Complex MIME Emails

When using a custom handler for `MimeMessage`:

1. Use `JavaMailSender.createMimeMessage()` to create a test email.
2. Use `MimeMessageHelper` with `MULTIPART_MODE_MIXED_RELATED`.
3. Call `setText(plain, html)`, `addInline(...)`, and `addAttachment(...)`.
4. Send the `MimeMessage` into a channel dedicated to prepared MIME.
5. Have the test SMTP server receive the email; parse the MIME tree.
6. Verify the `text/plain`, `text/html`, `multipart/related`, and attachment parts.
7. Read decoded bytes of attachments/inline parts to compare against fixtures.

### Keep Resources Alive Long Enough

`FileSystemResource` and `InputStreamSource` may only be read during serialization/sending. If a producer creates a temporary file, puts a MimeMessage onto an async channel, and deletes the file right after `channel.send(...)`, the worker may encounter a missing attachment.

For async flows, it is better for the worker to fetch data/compose MIME from an **immutable storage reference** within the attempt itself, avoiding passing a mutable `MimeMessage` carrying fragile file references across layers.

## 53. Test 7: Retries and Avoiding Duplicates

An important reliability test:

```text
Attempt 1:
  SMTP test server receives all DATA
  Server closes without final 250 reply
  Application sees timeout / unknown

Expected:
  status = UNKNOWN
  no blind immediate second send
  no automatic fallback to another provider
```

Another test when a connection is refused **before** SMTP submission can verify the appropriate retry policy.

Do not lump all errors together under `catch (MailException) -> channel.send(original)`. For emails with multiple recipients and `sendpartial=true`, some recipients may have already been submitted while the handler still throws an exception.

## 54. Test 8: Preventing Duplicate Consumers

If the system accidentally registers two mail handlers:

```text
outboundMail -> Mail handler A
outboundMail -> Mail handler B
```

A test should verify that the **number of accepted SMTP DATA commands** matches the intended notification count, not the number of registered subscribers. With `PublishSubscribeChannel`, one message may go to both A and B; with `DirectChannel`, the dispatcher may pick one subscriber rather than broadcasting.

Do not treat having two mail handlers on one channel as a default HA/retry mechanism. Design explicit producer, router, and consumer ownership instead.

## 55. Managing IntegrationFlow Lifecycle

Spring Integration endpoints have a lifecycle within the application context. In many configurations, endpoints start automatically when the Spring context boots; in some cases you can explicitly control startup, especially when a provider is not yet ready or maintenance is needed.

### Why Care?

- A poller can start pulling tasks as soon as the service starts.
- If SMTP configuration is wrong, workers can generate bursts of errors immediately upon deployment.
- During shutdown, in-flight tasks must be handled according to policy.
- Stopping an endpoint does not automatically mean in-memory messages have been durably persisted.
- If multiple instances share an outbox, claiming/leasing is needed to prevent concurrent processing.

Endpoint lifecycle and business notification lifecycle are separate concerns. Do not treat `autoStartup=false` as a "safe temporary mail buffer" when the queue still lives only in memory.

## 56. Graceful Shutdown

An outbound mail flow might be sending a large attachment when the application receives a shutdown signal.

```text
Shutdown begins
      |
      v
Stop accepting new work
      |
      v
Wait for in-flight tasks within configured bound
      |
      +-- completed -> record SUBMITTED or FAILED
      |
      +-- interrupted/timeout -> record UNKNOWN or reclaim lease
      |
      v
Release executor / sockets / resources
```

With SMTP send, stopping a thread cannot "roll back" a message the mail server has already received. If the process dies after DATA but before updating the database, another worker may not know the real result and retry, causing a duplicate.

Therefore:

1. Enforce request admission control during shutdown.
2. Do not accept unbounded new notifications.
3. Use a durable outbox/lease expiration for in-flight tasks.
4. Record stage and attempt ID.
5. Only requeue when policy confirms it is safe.
6. Have reconciliation for unknown states.

## 57. Bcc in Flows: Differences Between Headers and SMTP Recipients

`MailHeaders.BCC` is metadata that helps the adapter build the hidden recipient list. However, that is no reason to expose Bcc in logs or broad dashboards.

```java
Message<String> request = MessageBuilder
        .withPayload("Test newsletter")
        .setHeader(
                MailHeaders.TO,
                "primary@example.net"
        )
        .setHeader(
                MailHeaders.BCC,
                "audit@example.net"
        )
        .setHeader(
                MailHeaders.FROM,
                "notice@example.org"
        )
        .setHeader(
                MailHeaders.SUBJECT,
                "Newsletter"
        )
        .build();
```

When testing:

- Verify the test SMTP server sees the Bcc recipient in `RCPT TO`.
- Verify the MIME sent to recipients does not leak the Bcc header according to actual behavior.
- Do not rely solely on a pre-mapping `Message<String>` to draw conclusions about the wire representation.
- Do not log the full message or failed message when exceptions occur.

For personalized notifications requiring recipient privacy, consider one message per recipient instead of grouping multiple To/Cc recipients.

## 58. Correlation ID Does Not Automatically Equal Email Message-ID

An Integration Message typically has headers:

```text
id = UUID of Spring Message
timestamp = ...
correlationId = custom value (if set by application)
```

An SMTP/MIME email has:

```text
Message-ID: <...>
Date: ...
From: ...
To: ...
Subject: ...
```

These two domains are not synchronized by default. `MessageHeaders.ID` used in the pipeline is not `MimeMessage.getMessageID()`, nor is it guaranteed to be the ID returned by a provider in webhooks.

When tracking:

- `notificationId` identifies the business request.
- `attemptId` identifies a single SMTP/provider attempt.
- `providerMessageId` if returned by the provider with an established contract.
- `MimeMessage Message-ID` can be supporting diagnostic info, not a universal unique key for every case.

Do not use subject or email address as a correlation key because they collide easily and risk data exposure.

## 59. Do Not Assume Every Handler Runs Exactly Once

Even if a business event is created once, a notification can be processed again due to:

- Poller or worker restart.
- Slow database transaction commit after SMTP submission.
- Error channel retry.
- Message broker redelivery.
- Manual requeue.
- Connection loss after DATA.
- Failover across SMTP providers.

`MessageChannel` and the outbound adapter do not provide a **global exactly-once SMTP send contract**. If the product needs to reduce duplicates:

- Record notification ID and attempt history.
- Use idempotent claim/lease with a durable store.
- Avoid concurrently sending the same notification that is already `PROCESSING`.
- Do not automatically retry `UNKNOWN` without assessing risk.
- Enforce a business policy for resends.
- Keep an audit trail of manual retries.

Do not merely add `synchronized` in a single instance and assume the entire cluster cannot send duplicates; multiple instances run separate JVMs.

## 60. When Is Spring Integration Mail Not Needed?

Not every system benefits from using channel adapters.

If the requirement is a service method:

```java
public void sendWelcome(String address) {
    SimpleMailMessage message = new SimpleMailMessage();
    message.setTo(address);
    message.setFrom("welcome@example.org");
    message.setSubject("Welcome");
    message.setText("Thank you for signing up.");
    mailSender.send(message);
}
```

and there is no need for routing, transform pipelines, async handoffs, channels, or coordinating multiple systems, calling `MailSender` directly can be easier to understand with less configuration.

**Spring Integration Mail fits better** when:

- Email is part of an existing EIP pipeline.
- Multiple event sources share transformation/routing mechanisms.
- Channel adapters are needed to decouple producers from transport.
- There are multiple enrich, validate, transform, and filter steps.
- You want to compose flows with AMQP, JMS, Kafka, HTTP, or internal systems via corresponding adapters.
- The team already has observability and operations tailored to Spring Integration.

Do not add a framework just to "send emails asynchronously"; a plain outbox worker and `JavaMailSender` can serve simple business needs well.

## 61. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating channel `send=true` as email delivered | Wrong business status | Treat only as channel acceptance per semantics |
| Using HTML `String` and expecting adapter to build HTML MIME | Client sees raw markup | Build HTML MIME or use custom handler |
| Sending an untransformed DTO | Wrong body or mapping failure | Transform/enrich before adapter |
| Forgetting `MailHeaders.TO` | No valid recipient | Validate before sending |
| Assuming `MailHeaders.TO` cannot override payload | Sent to wrong recipient | Test precedence |
| Using arbitrary header strings | Mapping does not work | Use `MailHeaders` constants |
| Attaching pollable channel without a poller | Messages not consumed as expected | Configure poller explicitly |
| Using in-memory QueueChannel for critical emails | Tasks lost on restart | Durable outbox/broker |
| Using ExecutorChannel and catching errors in HTTP caller | Async errors missed | Error channel/status tracking |
| Attaching two mail adapters to publish-subscribe channel | May send duplicates | Router selects one route |
| Adding two consumers for "HA" on a DirectChannel | Unpredictable dispatch for business goals | Clear owner/routing |
| Pushing raw PDF `byte[]` into a large queue | Heap/GC pressure | Storage reference, bounded queue |
| Deleting temp files right after enqueue | Worker cannot read attachment | Manage file lifecycle |
| Holding DB transaction across SMTP | Long locks/connections, rollback cannot undo mail | Short transactions + outbox |
| Retrying every `MailSendException` immediately | Duplicates or retrying permanent errors | Classify + policy |
| Logging full `ErrorMessage` | Leaks recipient/OTP/attachment | Structured safe metadata |
| Treating SMTP accepted as Inbox delivered | Misleading status reporting | Separate provider delivery feedback |
| Not testing subscriber/channel choice | Sync/async/duplicate bugs | Channel + SMTP integration tests |
| Editing sender bean config while flow uses adapter host | Connects to wrong SMTP | Single clear configuration source |
| Putting SMTP credentials in source code | Secret exposure | Secret management/rotation |

## 62. Outbound Mail Flow Checklist

### Configuration

- [ ] `spring-integration-mail` and an appropriate mail implementation are present.
- [ ] `jakarta.mail` or `javax.mail` namespace verified for the version.
- [ ] `JavaMailSender` has accurate host, port, TLS, auth, and timeouts.
- [ ] Mail adapter uses a sender bean or host config with clear ownership.
- [ ] No unintended duplicate endpoints registered on the same channel.

### Message Contract

- [ ] Producer knows whether payload should be `String`, `MailMessage`, or a DTO before transformer.
- [ ] `MailHeaders.TO` and appropriate sender/subject are provided.
- [ ] Header precedence and overwrites are controlled.
- [ ] User input is validated before populating mail headers.
- [ ] Complex HTML/attachments are constructed via dedicated MIME logic.
- [ ] Correlation ID contains no personal data.

### Channel Semantics

- [ ] `DirectChannel`, `QueueChannel`, or `ExecutorChannel` chosen deliberately.
- [ ] Poller configured for `PollableChannel`.
- [ ] Queue/executor has reasonable capacity and backpressure.
- [ ] Enqueueing is not treated as SMTP submission.
- [ ] Async error path is implemented and tested.
- [ ] Durable outbox is in place if notifications must not be lost.

### Reliability

- [ ] Notification ID and attempt ID are tracked.
- [ ] Statuses `PENDING/PROCESSING/SUBMITTED/FAILED/RETRY_WAIT/UNKNOWN` exist.
- [ ] Long DB transactions are not held across SMTP sends.
- [ ] Attempts with ambiguous outcomes are not blindly retried.
- [ ] Shutdown/reclaim/reconciliation strategy exists.
- [ ] Bcc and suppression policies are enforced.

### Testing and Monitoring

- [ ] Unit tests exist for transformers and header mapping.
- [ ] Channel sync/async/queue behavior is tested.
- [ ] SMTP test server is used for integration tests.
- [ ] Recipient, Subject, Content-Type, and MIME are tested where needed.
- [ ] SMTP errors, timeouts, and executor rejections are tested.
- [ ] Metrics separate channel accepted from SMTP submitted.
- [ ] Raw messages/recipients/tokens/attachments are never logged.

## 63. Exercise 1 — Choosing the Right Channel

An application sends non-critical marketing emails via an independent worker; the HTTP request needs to return immediately.

**Question:** Choose DirectChannel or QueueChannel?

**Hint:** QueueChannel + poller or ExecutorChannel can fit an async handoff. However, if send requests must not be lost across restarts, a durable store/outbox/broker outside in-memory channels is required. Do not assume an async channel automatically provides durability.

## 64. Exercise 2 — Handler Does Not Receive Messages

A producer sends messages to `queuedMailRequests`, yet no emails are ever submitted.

**Question:** What should be checked first?

**Hint:** Whether the channel is `PollableChannel` or `SubscribableChannel`, whether the endpoint has started, whether a poller is configured, and whether the handler uses the right input channel and logs/error path.

## 65. Exercise 3 — To Header Does Not Match Payload

A `SimpleMailMessage` payload has To A, but the Integration Message has `MailHeaders.TO` set to B.

**Question:** Can it be sent to B?

**Hint:** Yes. According to the outbound mail handler's mapping, mail headers can override the corresponding MailMessage properties. Test precedence with an SMTP test server and establish clear recipient ownership.

## 66. Exercise 4 — Queue Returns True but Server Has Not Received It

`QueueChannel.send(...)` returns `true`, and the dashboard immediately records `DELIVERED`. Half a minute later, the poller picks up the message.

**Hint:** The dashboard confused channel acceptance with submission/delivery. Record `ENQUEUED` or `PENDING`, then update to `SUBMITTED` when the adapter completes with SMTP evidence.

## 67. Exercise 5 — Sending an HTML Email with Logo and PDF

A producer pushes an HTML string and a `MailHeaders.SUBJECT` into the mail adapter, expecting it to create `multipart/mixed` with a CID image.

**Hint:** Text mapping on the adapter does not automatically construct such complex MIME structures. Use a MIME composer and `MimeMessageHelper`, plus a custom handler sending `MimeMessage`, or choose an integration design with an explicitly supported MIME-building contract.

## 68. Exercise 6 — Errors from Async Flow Vanish

An application uses `ExecutorChannel`, but only wraps `channel.send(...)` in a `try/catch` in the controller. The SMTP server rejects the recipient after the controller has already returned a response.

**Hint:** Exceptions in the worker do not automatically propagate back to the caller. You need an error channel/async handler, persistent attempt state, metrics, and a context-appropriate retry policy.

## 69. Exercise 7 — Two Outbound Adapters Receive the Same Event

A `PublishSubscribeChannel` has two consumers, both mail adapters configured with two different SMTP providers.

**Hint:** Publish-subscribe can broadcast the same message to both consumers, creating duplicate emails. If the goal is selecting route A or B, use a router with an explicit policy and one active provider per notification/attempt.

## 70. Exercise 8 — Crash After SMTP Accepted

A worker calls the mail adapter; the server already received DATA. The process crashes before updating the database.

**Hint:** There is no distributed transaction spanning SMTP and the database. Upon restart, the attempt may remain in stale `PROCESSING` or `UNKNOWN`. Do not automatically retry without evaluating duplicate risk; use an attempt ledger, leases, and reconciliation.

## 71. Exercise 9 — Attachment Disappears in the Queue

A producer creates a temporary PDF file, attaches it using `FileSystemResource`, and pushes the `MimeMessage` onto an async channel. The producer deletes the file right after enqueueing.

**Hint:** MIME serialization may only read the file later inside the worker. Either keep the file alive long enough or put a notification DTO + immutable storage reference on the queue so the worker builds the mail when its turn arrives.

## 72. Exercise 10 — SMTP Response Succeeds but Recipient Sees Nothing

`JavaMailSender.send(...)` throws no exception, yet the recipient does not see the email in their Inbox.

**Hint:** Check provider events, bounces, suppression lists, spam placement, mailbox rules, and delivery feedback. The Spring Integration outbound adapter only proves submission at the observable layer, not Inbox arrival.

## 73. References

- **Spring Integration — Mail Support:** https://docs.spring.io/spring-integration/reference/mail.html
- **Spring Integration — Configuring Message Channels:** https://docs.spring.io/spring-integration/reference/channel/configuration.html
- **Spring Integration — Error Handling:** https://docs.spring.io/spring-integration/reference/error-handling.html
- **Spring Framework — Email Integration:** https://docs.spring.io/spring-framework/reference/integration/email.html

These links help cross-check APIs against the actual library version. In the lesson examples, hostnames and email addresses are illustrative values; replace them with controlled SMTP sandbox configurations and test data before running.

## 74. Conclusion

The **outbound mail adapter** in Spring Integration is an endpoint that consumes `Message<?>` from a **message channel** and delegates email sending to `JavaMailSender`. It helps decouple business producers from SMTP while enabling pipelines for header enrichment, payload transformation, validation, routing, and monitoring. `MailSendingMessageHandler` handles text, `MailMessage`, and common mappings; complex MIME scenarios should be built with a composer/handler with an explicit contract.

**Message channel selection determines system behavior**: `DirectChannel` typically runs on the caller thread, `QueueChannel` requires a poller to pull messages, and `ExecutorChannel` offloads processing to an executor. Changing channels can alter latency, exception propagation, transaction boundaries, and task loss risk. No channel automatically turns SMTP into exactly-once delivery or guarantees Inbox arrival.

In real applications, establish clear ownership for recipients and headers, classify errors by stage, protect sensitive payloads, bound concurrency, and persist notifications/attempts durably if send requests must not be lost. Combining **outbound adapter + channel semantics + reliable outbox + SMTP test server** yields a scalable, testable email system without confusing "accepted by channel", "submitted to SMTP", and "delivered".
