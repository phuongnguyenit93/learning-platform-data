# Building a JMS Request-Reply Exchange with Timeout

## 1. What Is Request/Reply in JMS?

JMS is primarily used for asynchronous messaging, yet the protocol also supports the **request/reply** pattern: one side sends a request to a destination, and the receiving side processes it and sends a reply message back to a destination specified by the caller.

A request/reply exchange typically has these components:

- **Request destination:** queue receiving requests.
- **Request message:** payload and metadata describing the operation to perform.
- **JMSReplyTo:** header containing the destination the processor must use to send the reply.
- **Reply message:** the returned result.
- **JMSCorrelationID:** header used to correlate the reply with the corresponding request.
- **Timeout:** maximum duration the caller waits for a reply before concluding no response was received.

Example price lookup:

~~~text
Pricing Client
     |
     | 1. Request: "SKU-100"
     |    JMSReplyTo = temporary reply queue
     v
orders/pricing.request
     |
     v
Pricing Service
     |
     | 2. Process request
     | 3. Reply: "SKU-100 costs 120000 VND"
     v
Temporary reply queue
     |
     | 4. Caller receives reply or times out
     v
Pricing Client
~~~

Request/reply is appropriate when the caller needs a result to continue an operation and processing time is bounded. If the work is long-running, multi-step, or does not require an immediate response, an asynchronous command combined with events/notifications is usually more appropriate.

## 2. JMS Headers Controlling the Reply Flow

### 2.1. JMSReplyTo

`JMSReplyTo` is a standard Jakarta Messaging header. The requester attaches a `Destination` to this header when sending a request. The responder reads the header and sends the reply to the specified destination.

If `JMSReplyTo` is `null`, the message may be just a notification or one-way data; the responder has no designated destination to reply to.

`JMSReplyTo` can be a queue or a topic. For a one-request-one-reply pattern, a queue is usually easier to control because the message is delivered to a single receiving consumer. If multiple replies or broadcasts are needed, that is a different protocol requiring separate design.

### 2.2. JMSCorrelationID

`JMSCorrelationID` links a reply to a request. There are two common conventions:

1. **Using the request's JMSMessageID:** the provider assigns `JMSMessageID` when sending the request; the responder sets that value into the reply's `JMSCorrelationID`.
2. **Using an application correlation ID:** the requester sets a unique ID in the request's `JMSCorrelationID`; the responder copies the exact value into the reply.

Example:

~~~text
Request:
  JMSMessageID     = ID:broker-12345
  JMSCorrelationID = null
  JMSReplyTo       = temp-queue-42

Reply:
  JMSMessageID     = ID:broker-67890
  JMSCorrelationID = ID:broker-12345
  JMSReplyTo       = null
~~~

If using an application correlation ID, the value is an application-generated string. Per the JMS specification, an application-specified string must not begin with the `ID:` prefix, because that prefix is reserved for provider-generated message IDs.

Do not confuse `JMSMessageID` with `JMSCorrelationID`: message ID identifies a message sent by the broker; correlation ID indicates which message relates to the current message.

### 2.3. Rules When Using a Shared Reply Queue

When multiple requests share a single reply queue, `JMSReplyTo` alone is insufficient. Replies can arrive interleaved, so the requester needs to filter by correlation ID or an equivalent dispatcher mechanism.

Example convention:

- The requester generates a unique correlation ID for each request.
- The requester sends the request with that correlation ID.
- The responder copies the correlation ID into the reply.
- The reply listener receives messages and routes them to the matching future/callback waiting on that ID.

Do not use an unfiltered consumer per request on the same reply queue if consumers could accidentally receive each other's replies. With multiple concurrent requests, use a shared reply listener with a map from correlation ID to the pending response object, or use a gateway mechanism that already manages this.

## 3. Temporary Reply Queue vs. Shared Reply Queue

### 3.1. Per-Request Temporary Queue

Jakarta Messaging allows creating a `TemporaryQueue` for the lifetime of the connection that created it. Only consumers created on the connection owning the temporary destination can receive messages from that queue; producers on other connections can still send to this destination.

This approach fits simple request/reply:

1. The requester creates a temporary queue.
2. The requester sets the queue in `JMSReplyTo`.
3. The requester sends the request.
4. The responder sends the reply to `JMSReplyTo`.
5. The requester receives the reply from the temporary queue.
6. The temporary destination is released when its owning connection closes; Spring also manages creating and cleaning up resources for template request/reply operations.

Advantages:

- Each request has its own reply destination, avoiding filtering replies from other requests.
- Easy to use with minimal configuration.
- No need to manage a shared reply listener and correlation ID table.

Limitations:

- Creating a temporary destination per request can consume resources and add broker operations.
- Brokers/providers may restrict or disallow temporary destinations in certain environments.
- Not suitable for very high request/reply throughput or when long-lived reply listeners are required.

### 3.2. Shared Reply Queue

In high-throughput systems, a fixed reply queue can be used per application or per instance. A reply listener receives all replies and dispatches them by correlation ID.

Design requirements to specify clearly:

- IDs must be unique across all requesters that could receive replies on the queue.
- Every reply must carry the exact correlation ID of the original request.
- The reply listener must handle late replies, duplicate replies, and IDs that are no longer pending.
- When a request times out, remove its corresponding entry from the pending table.
- If multiple instances read from the same queue, prevent instance A from consuming replies meant for instance B. Use per-instance queues, selectors by correlation namespace, or a centralized reply gateway.

Do not let each caller create its own consumer on a shared reply queue without a selector; competing consumers will steal each other's messages.

### 3.3. Which Model to Choose?

| Criterion | Temporary reply queue | Shared reply queue |
|---|---|---|
| Configuration | Simple | More complex |
| Reply isolation | Natural by destination | Requires correlation/dispatch |
| Broker resources | May create a queue per request | A few long-lived queues/listeners |
| High throughput | Must measure temporary destination overhead | Suitable with a well-designed reply dispatcher |
| Timeout management | Caller waits directly | Must clean up pending correlation entries |
| Multiple instances | Each request has its own queue | Must route replies to the right instance |

Start with a temporary reply queue when throughput is moderate and request/reply is simple. Only switch to a shared reply queue when metrics show temporary destination overhead is significant or when a shared reply listener architecture is required.

## 4. How Does Spring JMS Support Request/Reply?

Spring provides multiple API levels:

| API | Role | Return value on timeout |
|---|---|---|
| `JmsTemplate.sendAndReceive` | Sends a JMS Message and receives a JMS Message | `null` |
| `JmsMessagingTemplate.convertSendAndReceive` | Converts payload/Message and receives a typed payload | `null` |
| `JmsClient` (Spring 7+) | Fluent API with per-operation timeouts | `Optional.empty()` |

`JmsTemplate` manages creating/releasing connections, sessions, producers, consumers, and temporary reply queues. For basic request/reply, the template automatically creates a temporary queue and attaches it to the request's `JMSReplyTo`.

`JmsMessagingTemplate` builds on `JmsTemplate`, adding Spring Messaging abstractions and payload conversion. `JmsClient`, introduced in Spring Framework 7.0, provides a fluent API and per-operation options.

**API distinction:** `JmsTemplate` has `sendAndReceive`; the typed `convertSendAndReceive` API belongs to `JmsMessagingTemplate`. Spring 7 adds `JmsClient.sendAndReceive` taking a payload and target class.

## 5. Configuring Timeouts

### 5.1. JmsTemplate.setReceiveTimeout

`JmsTemplate.setReceiveTimeout(long)` configures the wait duration for receive operations in milliseconds. `sendAndReceive` uses this value when waiting for a reply.

Example:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@Bean
JmsTemplate requestReplyJmsTemplate(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setReceiveTimeout(2_000L);
    return template;
}
~~~

Meaningful values:

| Value | Behavior |
|---|---|
| Positive number, e.g. `2000` | Wait at most 2,000 milliseconds |
| `0` | Wait indefinitely |
| Negative number | Check immediately for an available message without waiting |

The default on `JmsTemplate` is `RECEIVE_TIMEOUT_INDEFINITE_WAIT`. Therefore, if no timeout is configured, a receive or request/reply operation can block the calling thread indefinitely.

The timeout must be a positive number for request/reply serving HTTP or interactive operations with an SLA. Do not use the indefinite default on request paths where callers expect a result within a bounded duration.

### 5.2. Per-Operation Timeout with JmsClient

Starting in Spring Framework 7.0, `JmsClient.OperationSpec.withReceiveTimeout(long)` allows setting a separate timeout per operation:

~~~java
import java.util.Optional;

import org.springframework.jms.core.JmsClient;

public class PricingClient {

    private final JmsClient jmsClient;

    public PricingClient(JmsClient jmsClient) {
        this.jmsClient = jmsClient;
    }

    public String quote(String sku) {
        Optional<String> reply = jmsClient
            .destination("pricing.request")
            .withReceiveTimeout(2_000L)
            .sendAndReceive(sku, String.class);

        return reply.orElseThrow(
            () -> new IllegalStateException("Pricing reply timed out"));
    }
}
~~~

`withReceiveTimeout` applies only to subsequent receive operations on that operation handle. Returning `Optional.empty()` means no reply arrived within the wait window; connection errors or send failures are still thrown as `MessagingException`.

`JmsClient` can be created from a `ConnectionFactory` or from a configured `JmsTemplate`:

~~~java
@Bean
JmsClient jmsClient(ConnectionFactory connectionFactory) {
    return JmsClient.create(connectionFactory);
}
~~~

If you need to share existing connection settings, converters, or template properties, create the client from `JmsTemplate`:

~~~java
@Bean
JmsClient jmsClient(JmsTemplate jmsTemplate) {
    return JmsClient.create(jmsTemplate);
}
~~~

### 5.3. Timeout Is Not Message TTL

These two concepts serve different purposes:

- **Receive timeout:** how long the caller waits for a reply.
- **Message Time-To-Live (TTL):** how long the broker is allowed to keep the request for delivery before the message expires.

For example, the caller waits 2 seconds, yet the request may still remain in the queue and be processed afterward. If you want the request to expire at the broker, set TTL separately via QoS settings or `JmsClient.withTimeToLive`.

With `JmsTemplate`, `setTimeToLive` is only applied per QoS configuration when `explicitQosEnabled` is enabled. Do not assume `setReceiveTimeout` automatically sets message expiration.

### 5.4. Timeout Does Not Cancel Processing on the Responder

When the requester times out, the request may already be:

- Not yet delivered by the broker to the responder.
- Sitting in the queue.
- Received by the responder and currently processing.
- Completed, with the reply delayed or lost.
- Sent as a reply, yet the caller missed it before the deadline.

Thus, a timeout only tells the caller it did not receive a reply in time. It does not prove business logic failed, nor does it cancel work on the responder side.

If the operation has side effects, use a request ID/idempotency key for safe retries. On timeout, the caller can query status by request ID instead of resending a command that might trigger the side effect again.

## 6. Complete Example with Spring Framework 6.2

The example below uses plain text strings to keep the payload simple and uses `JmsMessagingTemplate` for request/reply with payload conversion.

### 6.1. Configuring Template and Listener

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.core.JmsMessagingTemplate;

@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    JmsTemplate requestReplyJmsTemplate(
            ConnectionFactory connectionFactory) {

        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setReceiveTimeout(2_000L);
        return template;
    }

    @Bean
    JmsMessagingTemplate jmsMessagingTemplate(
            JmsTemplate requestReplyJmsTemplate) {

        return new JmsMessagingTemplate(requestReplyJmsTemplate);
    }
}
~~~

If the application uses Spring Boot and already has an auto-configured `JmsTemplate`, configure the timeout on the template actually used or create a dedicated bean for request/reply. Avoid creating multiple templates with unclear timeouts and injecting the wrong bean.

### 6.2. Requester

~~~java
import org.springframework.jms.core.JmsMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class PricingRequestClient {

    private final JmsMessagingTemplate jmsMessagingTemplate;

    public PricingRequestClient(JmsMessagingTemplate jmsMessagingTemplate) {
        this.jmsMessagingTemplate = jmsMessagingTemplate;
    }

    public String quote(String sku) {
        String reply = jmsMessagingTemplate.convertSendAndReceive(
            "pricing.request",
            sku,
            String.class
        );

        if (reply == null) {
            throw new IllegalStateException(
                "No pricing reply received within 2000 ms");
        }

        return reply;
    }
}
~~~

`convertSendAndReceive` converts the request into a JMS message, sends it to `pricing.request`, receives the reply, and converts the body into a `String`. If no message arrives before the underlying `JmsTemplate` timeout, the result is `null`.

### 6.3. Responder with @JmsListener

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class PricingRequestListener {

    @JmsListener(destination = "pricing.request")
    public String handle(String sku) {
        if (sku == null || sku.isBlank()) {
            return "ERROR: sku is required";
        }

        return "PRICE:" + sku + ":120000";
    }
}
~~~

When a listener method returns a non-`void` value, Spring converts the result into a JMS message and sends it to the destination in the request's `JMSReplyTo`. For requests created by `JmsTemplate.sendAndReceive` or `JmsMessagingTemplate.convertSendAndReceive`, `JMSReplyTo` points to the temporary reply queue.

There is no need to declare `@SendTo` for this example. `@SendTo` is used to specify a default reply destination when a request lacks `JMSReplyTo` or when the application needs a default destination.

### 6.4. Processing Flow

1. `PricingRequestClient` sends the SKU to `pricing.request`.
2. Spring creates a temporary reply queue and attaches it to `JMSReplyTo`.
3. The listener receives the request, invokes business processing, and returns the result.
4. Spring sends the reply to `JMSReplyTo`.
5. The requester receives the reply and returns the result to the caller.
6. If no reply arrives within 2 seconds, the requester receives `null` and turns it into a timeout per application policy.

The classes above are components in a Spring application that has a `ConnectionFactory` pointing to a running JMS broker. They must be placed in a project with Spring JMS dependencies, Jakarta Messaging, and the corresponding broker configuration; they are not a standalone JDK-only Java program.

## 7. Spring Framework 7 Example with JmsClient

`JmsClient` reduces typed request/reply setup down to a single operation:

~~~java
import java.util.Optional;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsClient;

@Configuration
public class JmsClientConfiguration {

    @Bean
    JmsClient jmsClient(ConnectionFactory connectionFactory) {
        return JmsClient.create(connectionFactory);
    }
}
~~~

Requester:

~~~java
import java.util.Optional;

import org.springframework.jms.core.JmsClient;
import org.springframework.stereotype.Service;

@Service
public class PricingClient {

    private final JmsClient jmsClient;

    public PricingClient(JmsClient jmsClient) {
        this.jmsClient = jmsClient;
    }

    public String quote(String sku) {
        Optional<String> reply = jmsClient
            .destination("pricing.request")
            .withReceiveTimeout(2_000L)
            .sendAndReceive(sku, String.class);

        return reply.orElseThrow(
            () -> new IllegalStateException("Pricing request timed out"));
    }
}
~~~

`JmsClient` uses the default Spring Messaging converter or a converter configured via the client/template. If the payload is a complex DTO, configure the converter/schema explicitly instead of assuming every object will serialize to JSON.

## 8. Using JmsTemplate Directly When a Raw JMS Message Is Needed

`JmsTemplate.sendAndReceive` is useful when you need to construct messages and manipulate headers/properties directly:

~~~java
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class RawPricingClient {

    private final JmsTemplate jmsTemplate;

    public RawPricingClient(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public String quote(String sku) {
        Message reply = jmsTemplate.sendAndReceive(
            "pricing.request",
            session -> session.createTextMessage(sku)
        );

        if (reply == null) {
            throw new IllegalStateException("Pricing reply timed out");
        }

        if (!(reply instanceof TextMessage textMessage)) {
            throw new IllegalStateException("Unexpected JMS reply type");
        }

        try {
            return textMessage.getText();
        }
        catch (jakarta.jms.JMSException ex) {
            throw new IllegalStateException("Cannot read JMS reply", ex);
        }
    }
}
~~~

`sendAndReceive` takes a `MessageCreator` to construct the request message from `Session`. Spring creates a temporary reply queue, sets it on `JMSReplyTo`, sends the request, and waits for a reply according to the configured `receiveTimeout`.

`JmsTemplate` returns a raw `jakarta.jms.Message`; the caller inspects the message type and reads the payload itself. If you only need the converted payload, `JmsMessagingTemplate` or `JmsClient` is usually more concise.

## 9. Responder Manually Building a Reply via JMS API

When a listener needs control over message headers, destination, or QoS, it can receive the raw JMS message and session and send the reply manually.

~~~java
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class ManualReplyListener {

    @JmsListener(destination = "pricing.request")
    public void handle(TextMessage request, Session session)
            throws JMSException {

        Destination replyTo = request.getJMSReplyTo();
        if (replyTo == null) {
            return;
        }

        TextMessage reply = session.createTextMessage(
            "PRICE:SKU-100:120000"
        );

        String requestMessageId = request.getJMSMessageID();
        if (requestMessageId != null) {
            reply.setJMSCorrelationID(requestMessageId);
        }

        MessageProducer producer = session.createProducer(replyTo);
        try {
            producer.send(reply);
        }
        finally {
            producer.close();
        }
    }
}
~~~

This example illustrates the protocol at the JMS level. In a real application, the reply payload should be computed from the request; do not hard-code business data like in the illustrative example.

Spring supports injecting raw `jakarta.jms.Message` and `jakarta.jms.Session` into `@JmsListener` methods. For listener methods returning non-void values, Spring already handles most reply creation and sending logic; only use the manual approach when deep control is needed.

## 10. Using a Fixed Reply Queue and Correlation ID

When a shared reply queue is needed, the requester and responder must follow the same correlation contract.

### 10.1. Request Message Model

~~~text
Request:
  Destination      = orders.request
  JMSCorrelationID = req-7d2f
  JMSReplyTo       = orders.reply

Reply:
  Destination      = orders.reply
  JMSCorrelationID = req-7d2f
~~~

The requester generates a sufficiently unique correlation ID and sets it on the request. The responder copies that value to the reply. The reply listener uses the correlation ID to find the matching waiting request.

If using `JMSMessageID` instead of an application correlation ID, the responder reads the request's message ID and sets it on the reply's `JMSCorrelationID`. This is a common convention and is supported by Spring's `MessageListenerAdapter` when sending responses.

### 10.2. Do Not Receive Replies with an Unfiltered Consumer

Suppose three requests are waiting simultaneously on `orders.reply`:

| Request | Correlation ID |
|---|---|
| R1 | req-A |
| R2 | req-B |
| R3 | req-C |

Replies may arrive in the order R3, R1, R2. If each caller creates its own consumer on the same queue without a selector, one caller can receive another caller's reply.

A shared reply listener can dispatch as follows:

~~~text
orders.reply
    |
    v
Reply Listener
    |
    +-- req-A -> Future R1
    +-- req-B -> Future R2
    +-- req-C -> Future R3
~~~

On timeout, remove the correlation entry from the pending table. Otherwise, the map retains expired futures and grows in memory over time. Late replies must be logged or discarded per policy, never delivered by mistake to a new request.

### 10.3. When to Use Spring Integration JMS Gateway?

If an application needs a shared reply queue, long-lived reply listeners, correlation mapping, timeouts, and concurrent request management, Spring Integration JMS Gateway can be a better fit than writing a custom dispatcher.

The gateway supports temporary queue strategies, fixed reply destinations, reply listeners, and correlation keys. Configure it consistently between producer and responder, and verify behavior against a real broker.

## 11. Handling Timeouts Properly

### 11.1. Distinguish Timeouts from Send Errors

There are two different outcome categories:

| Outcome | Meaning | How to handle |
|---|---|---|
| Reply received | Responder replied | Validate response and continue |
| Timeout, returns null/Optional.empty | No reply received within wait window | Return timeout or query status |
| JMS/Messaging exception | Send, connection, conversion, or receive failed | Classify error and apply retry/fallback |
| Reply with wrong correlation | Reply does not belong to a current request | Log, quarantine, or discard per policy |
| Reply payload invalid schema | Cannot convert/validate result | Handle contract error, do not treat as timeout |

Timeout normally bounds only the waiting phase for the reply. If the broker cannot be reached or sending the request fails, Spring throws an exception instead of returning null as in the no-reply case.

### 11.2. Do Not Retry Blindly

Suppose a caller sends `CreatePayment` and times out after 2 seconds. Payment Service might have already created the payment successfully and only been slow sending the reply. If the caller sends a new command, a second payment may be created.

Solution:

- Include a `requestId` or `idempotencyKey` in the payload.
- Store the processing outcome by key on the responder side.
- If the same key arrives again, return the stored result instead of executing the side effect again.
- When retrying the same intent, preserve the idempotency key; a new correlation ID can be used per exchange to trace individual attempts.
- If supported by the domain, provide a query to check status by request ID.

Do not treat a timeout as a signal to cancel a command. Canceling in-progress work requires an explicit cancellation command, and the responder must support those semantics.

### 11.3. Set Timeouts According to SLA

Timeouts need to balance normal processing duration against caller experience. For example:

- Lightweight data reads: can use a short deadline.
- Tasks involving multiple services or databases: must account for both queue delay and processing time.
- Heavy or long-running tasks: switch to an async workflow instead of holding a thread waiting.

The JMS requester timeout should be less than or equal to the calling upper layer's deadline. If an HTTP request expires before the JMS request/reply, the thread may keep waiting and holding resources even after the caller has disconnected.

### 11.4. Blocking and Thread Limits

`JmsTemplate.sendAndReceive`, `JmsMessagingTemplate.convertSendAndReceive`, and `JmsClient.sendAndReceive` all perform synchronous request/reply. The calling thread is held while sending and waiting for the response.

In systems with high concurrency:

- Use a bounded thread pool for blocking operations.
- Limit the number of in-flight requests.
- Set finite timeouts.
- Monitor queue depth and response times.
- Avoid calling directly from a reactive server's event-loop thread; if needed, offload to a scheduler dedicated to blocking I/O.

If thousands of concurrent requests or long-running tasks are required, an asynchronous model with a correlation registry and result-delivery events is usually more suitable.

## 12. Designing the Response Contract

Do not return only a free-form error string. Define a response contract with status and necessary details.

Example JSON:

~~~json
{
  "requestId": "req-7d2f",
  "status": "COMPLETED",
  "result": {
    "sku": "SKU-100",
    "price": 120000,
    "currency": "VND"
  },
  "errorCode": null,
  "message": null
}
~~~

Possible statuses include:

- `COMPLETED`: business operation finished.
- `REJECTED`: request rejected by business rules.
- `ACCEPTED`: system accepted the request, though the workflow is still running.
- `FAILED`: processing failed per the defined contract.

For synchronous request/reply, `ACCEPTED` is usually insufficient if the caller needs the final result immediately. If a workflow is long, return an operation ID and use APIs/events to track status.

Separate business errors from technical errors:

- Business errors should be represented explicitly in the response, e.g., `REJECTED` with `INSUFFICIENT_STOCK`.
- Transient technical errors can cause the listener to roll back and the message to be redelivered per container configuration.
- Non-retryable errors like invalid payload schemas should be routed to a dead-letter/quarantine flow or return a contracted error response.

If a listener throws an exception, the requester does not automatically receive a business error response. If callers must receive structured errors, the responder must map errors to a response message or the application must use a dedicated error-reply strategy.

## 13. Transactions and Acknowledgements

Request/reply involves two actions: receiving the request and sending the reply. If the listener processes inside a transacted JMS session, receiving the request and sending the response can fall within the same listener container JMS transaction. When processing fails and the transaction rolls back, the request can be redelivered per broker policy.

This avoids the case where the listener acknowledges a request without having sent the reply within the same JMS transaction. However, a JMS transaction does not automatically include a database transaction. If the listener updates a database and then sends a reply, design the commit boundaries carefully.

Some principles:

- Return `COMPLETED` only after business changes have reached a durable state.
- Use idempotency to handle redelivered requests.
- Do not acknowledge before critical side effects have committed.
- If database and JMS must be coordinated, consider outbox/inbox or an appropriate transaction manager.
- Do not hold a long database transaction while a thread waits for a reply from another service.

Request/reply does not automatically guarantee exactly-once. The broker can redeliver on consumer rollback, and the requester can retry after a timeout even if the prior request was already processed.

## 14. Securing the Reply Destination

`JMSReplyTo` is a destination supplied by the requester in the message. The responder needs to control where it is allowed to send replies.

With authenticated internal producers, using the requester-provided `JMSReplyTo` is the standard pattern. With messages from untrusted sources, do not send sensitive data to arbitrary destinations listed in a header without policy checks.

Considerations:

- Broker authorization for request and reply queues/topics.
- Allowlist of permitted reply destinations.
- Authentication of producers/consumers.
- Sensitive data in responses.
- Message size and payload limits.
- Correlation ID must not be used in place of authentication or authorization.

Do not log full payloads if they contain personal information, tokens, or payment data. Log request ID, correlation ID, destination, processing time, and status instead.

## 15. Testing Request/Reply

Tests should run against a real JMS broker or a compatible test broker. Mocking `JmsTemplate` cannot prove `JMSReplyTo`, correlation, temporary queues, or message selectors work properly.

Cases to include:

1. **Happy path:** request is sent, responder replies, caller receives the expected payload.
2. **Timeout:** responder sends no reply; caller receives null/Optional.empty within the configured limit.
3. **Late reply:** responder replies after timeout; the reply is not mistakenly delivered to another request.
4. **Concurrent requests:** multiple requests to the same destination receive matching replies by correlation.
5. **Responder exception:** verify rollback, redelivery, or error reply per policy.
6. **No JMSReplyTo:** verify responder handles requests that do not expect a reply.
7. **Invalid reply type/schema:** caller handles conversion errors in a controlled manner.
8. **Broker unavailable:** send/connection errors are distinguished from reply wait timeouts.
9. **Duplicate request:** idempotency key prevents repeated side effects.
10. **Shutdown:** temporary destinations, consumers, and connections are released according to lifecycle.

You can use Testcontainers with a broker like ActiveMQ Artemis or whichever JMS broker the production system uses. Test both transacted listener and non-transacted listener configurations if both are used in production.

## 16. Common Mistakes

1. **Not setting a receive timeout.** JmsTemplate waits indefinitely by default, potentially blocking threads forever.
2. **Confusing timeout with TTL.** Timeout limits how long the caller waits for a reply; TTL controls how long a message remains valid in the broker.
3. **Assuming timeout cancels the request.** The responder may still be processing and complete side effects after the caller timed out.
4. **Retrying side-effecting requests without idempotency.** Can create duplicate orders or payments.
5. **Using a shared reply queue without correlation.** Callers may receive replies belonging to other requests.
6. **Using non-unique application correlation IDs.** Replies get misrouted or selectors match multiple requests.
7. **Creating a dedicated consumer per request on a shared reply queue.** Competing consumers can steal each other's replies.
8. **Assuming every listener return value has a destination.** If the request lacks JMSReplyTo and the listener has no configured default reply destination, sending the reply may fail.
9. **Throwing an exception while expecting the caller to get an error DTO.** Exceptions do not automatically become a reply contract.
10. **Using request/reply for long-running tasks.** Callers hold threads and depend directly on responder uptime; consider an async workflow.
11. **Trusting JMSReplyTo from untrusted sources.** May send replies to unauthorized destinations.
12. **Using a single global timeout for every use case.** Different operations have different SLAs; Spring 7 JmsClient supports per-operation timeouts.
13. **Confusing JmsTemplate APIs.** JmsTemplate has raw Message `sendAndReceive`; typed `convertSendAndReceive` belongs to `JmsMessagingTemplate`.
14. **Not testing with a real broker.** Mocks cannot verify temporary queues, reply headers, selectors, and correlation.

## 17. Pre-Release Checklist

- [ ] Request destination and reply destination are clearly defined.
- [ ] Requests carry a valid `JMSReplyTo` when a reply is expected.
- [ ] Replies carry the correlation ID matching the contract.
- [ ] Requesters have a finite timeout aligned with the SLA.
- [ ] Reply wait timeouts are distinguished from send/connection errors.
- [ ] Side-effecting requests include an idempotency key.
- [ ] Policies exist for handling late replies and duplicate replies.
- [ ] Temporary queue vs. shared reply queue is chosen based on traffic volume.
- [ ] Shared reply queues have proper correlation dispatchers/selectors.
- [ ] Listener return values or manual replies target a valid destination.
- [ ] Business rejections and technical failures have clear response/error semantics.
- [ ] Transactions/acknowledgements align with side effects.
- [ ] Concurrency and thread resources are bounded for blocking operations.
- [ ] Permissions to send to `JMSReplyTo` are controlled.
- [ ] Integration tests cover timeouts, concurrency, late replies, and broker failures.

## 18. References

- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): JmsTemplate, JmsClient, and request/reply operations.
- [Spring Framework Reference — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html): sending messages, MessageCreator, MessageConverter, and JmsClient.
- [Spring Framework Reference — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): synchronous receive, timeouts, and listeners.
- [Spring Framework Reference — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@JmsListener`, response management, `@SendTo`, and listener return values.
- [Spring Framework Javadoc — JmsTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html): sendAndReceive, setReceiveTimeout, and default values.
- [Spring Framework Javadoc — JmsMessagingTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsMessagingTemplate.html): convertSendAndReceive and typed reply conversion.
- [Spring Framework Javadoc — JmsClient](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsClient.html): fluent client API introduced in Spring Framework 7.0.
- [Spring Framework Javadoc — JmsClient.OperationSpec](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsClient.OperationSpec.html): withReceiveTimeout and sendAndReceive returning Optional.
- [Jakarta Messaging 3.1 Specification — Request/reply and message headers](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): JMSReplyTo, JMSCorrelationID, temporary destinations, and request/reply semantics.
- [Jakarta EE Tutorial — JMS Concepts](https://jakartaee.github.io/jakartaee-documentation/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html): temporary queues and request/reply examples.
- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): gateways, reply listeners, and correlation strategies for shared reply destinations.
