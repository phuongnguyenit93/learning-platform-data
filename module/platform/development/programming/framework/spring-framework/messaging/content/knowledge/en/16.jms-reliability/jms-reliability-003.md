# Reply Timeouts and Cleaning Up Temporary Resources

## 1. Request-reply in JMS

Request-reply is a model in which a client sends a request to a service and then waits for the corresponding response. In Jakarta Messaging, the request and the response are still two separate messages. JMS provides two headers to connect them:

- `JMSReplyTo`: the destination the responder sends the response to.
- `JMSCorrelationID`: a value that lets the response refer to the request that produced it.

The requestor can create a temporary reply queue (`TemporaryQueue`), set that queue in `JMSReplyTo`, send the request, and then wait for a message on the queue. The responder reads `JMSReplyTo` from the request and sends the response to that destination. `JMSCorrelationID` helps trace request/response and pair them when many requests share one reply destination.

Request-reply is a synchronous exchange on the caller side, even though the JMS transport is still asynchronous. The caller blocks while waiting. If there is no response before the timeout, the caller gets a timeout result; the service may still be processing the request.

## 2. Three time concepts to keep separate

Do not use a single timeout value for every phase:

| Concept | Meaning | Commonly used mechanism |
| --- | --- | --- |
| Send timeout / send completion | The time or result of the operation that sends the request to the provider | JMS provider, connection, and the send API; `JmsTemplate` does not use `receiveTimeout` to limit sending |
| Reply receive timeout | How long the caller waits for the response after sending the request | `JmsTemplate.setReceiveTimeout(...)` or the corresponding client timeout |
| Request TTL / expiration | How long the broker keeps the request for delivery to the responder | JMS message time-to-live (`JMSExpiration`) |
| Business deadline | The latest moment at which the service should still continue business processing | Deadline or expiry timestamp passed by the application in the payload/property |

Example: the caller waits at most 2 seconds. The request may still sit in the queue for another 10 seconds if no TTL is set. When the responder receives it, the service may take another 5 seconds to process. The reply receive timeout only ends the caller's wait; it does not by itself cancel the message or stop the work on the responder side.

### 2.1. JmsTemplate receive timeout

`JmsTemplate.setReceiveTimeout(long)` sets the wait time for synchronous receive operations, in milliseconds. The default value is `0`, which corresponds to waiting indefinitely. A negative value (for example `-1`) asks to check for an available message without blocking.

For `sendAndReceive(...)`, `JmsTemplate` uses `receiveTimeout` itself to wait for the response on the reply queue. If time runs out with no message, the method returns `null`. Because the default is to wait indefinitely, production applications should explicitly configure a finite timeout.

~~~java
JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
jmsTemplate.setReceiveTimeout(2_000); // wait for the reply for at most 2 seconds
~~~

Do not use `setReceiveTimeout(-1)` for request-reply that needs a response within a defined deadline: a negative value is no-wait, so the response is only received if it is already available at the instant the consumer checks.

### 2.2. Request TTL is not the reply timeout

Time-to-live specifies how long the request remains valid for the broker to deliver. When the TTL expires, the provider may discard a request that has not been delivered. It does not limit how long the responder spends processing after receiving the request, and it does not limit how long the caller waits for the response.

In `JmsTemplate`, `setTimeToLive(...)` only takes effect if `setExplicitQosEnabled(true)` is enabled. If you need a TTL for the request, configure both and choose the TTL according to business policy:

~~~java
JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
jmsTemplate.setExplicitQosEnabled(true);
jmsTemplate.setTimeToLive(5_000); // the request has a 5-second TTL
jmsTemplate.setReceiveTimeout(2_000); // the caller waits 2 seconds for the reply
~~~

In this example, the caller may time out after 2 seconds while the request is still deliverable for another 3 seconds. If the service should not process the request after the deadline, also pass an application-managed `deadlineAt` or `expiresAt` and have the responder check it before starting business processing. The broker's TTL is an additional layer of protection, not a replacement for the business deadline.

## 3. How does JmsTemplate.sendAndReceive() manage the reply queue?

`JmsTemplate` provides `sendAndReceive(...)` overloads that take a destination and a `MessageCreator`. In Spring Framework 6.2, the basic flow is:

1. Create a JMS `TemporaryQueue` for the call.
2. Create a consumer on that temporary queue.
3. Create the request with the `MessageCreator` and set the temporary queue in `JMSReplyTo`.
4. Send the request to the target destination.
5. Wait for the reply according to `receiveTimeout`.
6. Close the reply consumer and producer, then delete the temporary queue in `finally`.

Therefore each independent request-reply call has its own reply destination. Many callers can call the template at the same time without having to create their own reply queue names or share one queue to sort out replies.

Example:

~~~java
Message reply = jmsTemplate.sendAndReceive(
        "pricing.requests",
        session -> {
            TextMessage request = session.createTextMessage("SKU-42");
            request.setJMSCorrelationID("price-request-42");
            return request;
        });

if (reply == null) {
    // No reply before receiveTimeout.
}
~~~

`JmsTemplate` sets `JMSReplyTo` itself during request-reply. There is no need to create a temporary queue yourself for this basic case. The caller can still set `JMSCorrelationID` for logging/tracing; the responder should copy that value into the response.

### 3.1. A TemporaryQueue is scoped to a Connection

JMS creates a temporary destination through a `Session` for convenience, but the actual lifecycle belongs to the `Connection` that created it:

- The destination is created by the provider with a unique name.
- Only the connection that created the temporary destination may create consumers on that destination.
- Other Sessions belonging to the same connection can create consumers.
- A temporary destination should be deleted when it is no longer in use; the provider also deletes it automatically when the connection closes.

In request-reply, the requestor creates the temporary queue and the consumer that receives the reply using the same connection. The responder reads `JMSReplyTo` and then sends the message to the specified destination. The Jakarta Messaging specification illustrates exactly this model.

## 4. A timeout does not cancel the request

This is the operational point most likely to cause bugs. When `sendAndReceive()` returns `null`, all that has happened is that the caller did not receive a reply within the configured time.

The request may be in one of these states:

- Not yet delivered by the broker because the queue still has a backlog.
- Delivered and the responder is processing it.
- The responder has finished but the response has not reached the reply queue.
- The response arrives right at the timeout moment and the caller does not receive it before the consumer closes.
- The responder sends the reply after the caller timed out and the temporary queue has been deleted.

The caller timing out does not automatically send a cancel command to the broker or the responder. If the business needs to cancel the work, you must design a separate cancellation message/API with a request ID, state, and rules for handling races. The responder needs to check cancellation/deadline at safe points before producing side effects.

### 4.1. Late replies

With a temporary queue created by `JmsTemplate`, when the method ends because of a timeout, Spring closes the consumer and deletes the queue. A reply arriving afterwards has no valid place to land; the provider may reject the send operation or handle it according to its own policy. The responder needs to handle reply-send failures in a controlled way and avoid infinite retries.

If you use a fixed/shared reply queue, a late reply may remain in the queue. The consumer must use the correlation ID to distinguish old responses, discard expired messages, and clean up correlation entries that no longer have a waiting caller.

### 4.2. Timeout and request retry

Do not automatically send a new request with a new ID right after a timeout. The previous request may already have been processed successfully; a retry could perform the business operation a second time.

For operations with side effects, keep a stable `requestId` or idempotency key across retries. The responder stores the result by key or applies an idempotent operation so that when it receives the same request again, it can return the old result without performing the side effect again.

### 4.3. Choose the timeout from an end-to-end budget

The caller's timeout must account for queueing time, processing, and returning the response. Set the timeout smaller than the deadline of the outer request if you still need time to propagate errors, write logs, or return an HTTP response.

For example, an HTTP request with a 3-second deadline may spend 2 seconds on JMS request-reply and the rest on processing before/after JMS. This is an application budget; the specific numbers must be based on real latency and the SLA.

Do not set the timeout too short relative to the service's p95/p99 because it will produce many request timeouts while the service still completes. Conversely, an infinite timeout can hold web/server threads, sessions, and connections for longer than necessary.

## 5. Correlation ID and routing the response

`JMSReplyTo` tells the responder where to send the reply. `JMSCorrelationID` tells the application which request the reply belongs to.

The responder typically copies the correlation ID from the request into the response:

~~~java
String correlationId = request.getJMSCorrelationID();
TextMessage reply = session.createTextMessage("price=19.95");
reply.setJMSCorrelationID(correlationId);
~~~

With one temporary queue per call, the dedicated destination already isolates the responses of concurrent requests. The correlation ID is still useful for tracing, logging, and reconciliation. When using a shared reply queue for many requests, the correlation ID becomes an important routing component: the consumer needs a selector or a registry to match the right reply to the waiter.

Do not use the response's `JMSMessageID` as a business request ID. Create a stable application ID and put it in `JMSCorrelationID` or a custom property according to the agreed contract.

## 6. JmsMessagingTemplate and request-reply

`JmsMessagingTemplate` provides the Spring Messaging API on top of `JmsTemplate`:

- `sendAndReceive(destination, Message<?>)` sends a Spring message and returns the reply Spring message or `null` on timeout.
- `convertSendAndReceive(destination, request, targetClass)` converts the request, sends it, receives the reply, and converts the response payload to the target Java type.

To control the timeout, configure the underlying `JmsTemplate` and then pass that template into `JmsMessagingTemplate`:

~~~java
JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
jmsTemplate.setReceiveTimeout(2_500);

JmsMessagingTemplate messagingTemplate =
        new JmsMessagingTemplate(jmsTemplate);

String reply = messagingTemplate.convertSendAndReceive(
        "pricing.requests",
        "SKU-42",
        String.class);

if (reply == null) {
    throw new IllegalStateException("Pricing service did not reply in time");
}
~~~

The example uses `String`, which `SimpleMessageConverter` maps to a `TextMessage`. If you use a DTO, you need to configure a compatible payload converter on both the requestor and the responder. The timeout of the request-reply operation is still the receive timeout on the underlying `JmsTemplate`.

Do not confuse this timeout with the timeout of Spring's `MessagingTemplate` used for `MessageChannel`; that is a different abstraction and has its own configuration.

## 7. How must the responder handle the reply destination?

The responder usually runs in a listener container. It reads `JMSReplyTo`, creates the response, and sends it to that destination. If the request has no `JMSReplyTo`, the message may be an event/command that does not require a response; the listener needs to follow the application contract.

Example with a raw JMS `TextMessage`:

~~~java
@Component
public class QuoteResponder {
    private final JmsTemplate jmsTemplate;

    public QuoteResponder(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @JmsListener(destination = "pricing.requests")
    public void handle(TextMessage request) throws JMSException {
        Destination replyTo = request.getJMSReplyTo();
        if (replyTo == null) {
            // The request does not require a response per the contract.
            return;
        }

        String sku = request.getText();
        String correlationId = request.getJMSCorrelationID();
        String responseBody = "SKU=" + sku + ";price=19.95";

        jmsTemplate.send(replyTo, session -> {
            TextMessage reply = session.createTextMessage(responseBody);
            if (correlationId != null) {
                reply.setJMSCorrelationID(correlationId);
            }
            return reply;
        });
    }
}
~~~

The code is an integration example: the application needs a `ConnectionFactory`, a running broker, the `pricing.requests` queue, and `@EnableJms`. The responder-side `JmsTemplate` can send to the temporary destination the requestor provides. The requestor must keep the connection that created the temporary queue until it finishes receiving the reply.

In a real system, do not let reply-send errors be swallowed. Record the correlation/request ID and the exception; decide on retry based on the error type and the transaction policy. If the reply destination has been deleted because the caller timed out, the responder may hit an error when sending. Do not retry indefinitely a reply that no longer has a recipient.

## 8. A complete Spring requestor example at integration level

Shared timeout configuration:

~~~java
@Configuration
@EnableJms
public class JmsClientConfiguration {
    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setReceiveTimeout(2_000);
        return template;
    }
}
~~~

The service that sends the request:

~~~java
@Service
public class QuoteClient {
    private final JmsTemplate jmsTemplate;

    public QuoteClient(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public String requestQuote(String sku) {
        String requestId = UUID.randomUUID().toString();

        Message reply = jmsTemplate.sendAndReceive(
                "pricing.requests",
                session -> {
                    TextMessage request = session.createTextMessage(sku);
                    request.setJMSCorrelationID(requestId);
                    return request;
                });

        if (reply == null) {
            throw new IllegalStateException(
                    "No quote reply before timeout; requestId=" + requestId);
        }

        if (!(reply instanceof TextMessage textReply)) {
            throw new IllegalStateException(
                    "Expected TextMessage reply; requestId=" + requestId);
        }

        try {
            return textReply.getText();
        } catch (JMSException ex) {
            throw new IllegalStateException(
                    "Cannot read quote reply; requestId=" + requestId, ex);
        }
    }
}
~~~

The main imports for the service include `java.util.UUID`, `jakarta.jms.JMSException`, `jakarta.jms.Message`, `jakarta.jms.TextMessage`, `org.springframework.jms.core.JmsTemplate`, and `org.springframework.stereotype.Service`.

This example needs a JMS provider configured in the application; a Spring/JMS Maven dependency does not install a broker by itself. There is no fixed stdout unless a broker, responder, and actual message are specified. When the responder sends a `TextMessage` within 2 seconds, the service returns the body; if there is no reply, the service throws an exception carrying the request ID for logging/tracing.

## 9. Managing the TemporaryQueue yourself when you need a lower-level JMS API

In most cases, `JmsTemplate.sendAndReceive()` already manages the temporary queue and cleanup. Only create the queue yourself when you need to customize the lifecycle or coordinate multiple operations on the same Session/Connection.

Manual pattern:

~~~java
try (Connection connection = connectionFactory.createConnection();
     Session session = connection.createSession(Session.AUTO_ACKNOWLEDGE)) {

    TemporaryQueue replyQueue = session.createTemporaryQueue();
    try {
        try (MessageProducer producer = session.createProducer(requestQueue);
             MessageConsumer consumer = session.createConsumer(replyQueue)) {

            TextMessage request = session.createTextMessage("SKU-42");
            request.setJMSReplyTo(replyQueue);
            request.setJMSCorrelationID("quote-42");

            connection.start();
            producer.send(request);

            Message reply = consumer.receive(2_000);
            if (reply == null) {
                // Timeout: the request may still be being processed.
            }
        }
    } finally {
        replyQueue.delete();
    }
}
~~~

The illustrative code needs `connectionFactory` and `requestQueue` to be configured already. `Connection`, `Session`, `MessageProducer`, and `MessageConsumer` are closed with try-with-resources; `TemporaryQueue.delete()` runs in `finally` even if send/receive fails or times out.

Do not close or delete the temporary queue before the consumer has finished receiving. Do not use the temporary queue after the connection that created it has closed. If the queue is created and managed by a framework, do not delete it again from application code.

## 10. Shared reply queue and many concurrent requests

A dedicated temporary queue per request is easy to understand and isolates replies by itself, but it creates an additional destination and consumer for every call. With very high traffic, constant creation/deletion can create overhead at the broker/provider.

Another model is a fixed reply queue, or a temporary queue reused with a listener container. In that case you need a correlation registry:

1. The requestor creates a unique correlation ID and registers a waiter before sending the request.
2. The request carries the correlation ID and the shared reply destination.
3. The responder sends the reply with the same correlation ID.
4. The reply listener looks up the waiter by correlation ID and completes the future/promise.
5. A timeout removes the waiter from the registry; a late reply is recorded and discarded.

The Spring Integration JMS outbound gateway supports the reply listener container model; when no reply destination is specified, it can use one TemporaryQueue for the gateway instead of creating one queue per request. This configuration is useful when you need to reuse consumers and manage many replies concurrently.

A shared reply queue needs a bounded registry size, cleanup of expired waiters, and handling of duplicate correlation IDs and late messages. Otherwise the map of waiting replies can grow forever or an old reply can be matched to a new request by mistake.

## 11. Transactions and request-reply

Do not wait for a reply inside the same JMS transaction that has not yet committed. If the request is sent in a transacted Session, the provider usually delivers the request only after the transaction commits. If the caller keeps that transaction open and then waits for the response, the responder may never see the request to answer it.

The Jakarta Messaging specification describes request/reply with a temporary queue where the request is sent in one transaction and the response is received in another. `JmsTemplate.sendAndReceive()` uses a local operation for request/receive; do not treat it as a single atomic transaction spanning the responder's business logic.

If the responder both updates a database and sends a reply, you need to determine the commit order and the possibility of retry. A JMS transaction only coordinates the JMS operations in the Session. The database transaction is a separate resource unless suitable JTA/XA is used; idempotency is still needed to handle redelivery or retry.

For a request with side effects, a timeout does not mean the business operation was rolled back. Returning a timeout to the caller while the responder has already committed can cause the caller to retry and create a duplicate operation. Use a stable request ID, store results by idempotency key, and provide a status-query API if the business needs to know the result after a timeout.

## 12. Common mistakes

- **Leaving the default infinite receive timeout:** the caller may hold a thread forever if the responder does not answer. Set a finite timeout appropriate to the SLA.
- **Confusing receive timeout with TTL:** the timeout stops the caller waiting; the TTL determines how long the request remains valid for the broker to deliver.
- **Assuming a timeout cancels the request:** the responder may still receive and process the request after the caller has returned a timeout.
- **Not checking `null` from `sendAndReceive`:** no reply before the timeout is represented as `null`.
- **Forgetting to clean up a self-created temporary queue:** the queue may hold resources at the broker until the connection closes.
- **Creating a consumer on a different connection:** a temporary destination only allows the owning connection to create consumers.
- **Deleting the queue before the reply consumer closes:** the provider may refuse to delete or the running receive operation may fail.
- **Not setting a correlation ID:** logs and a shared reply queue make it hard to match request/response accurately.
- **Sharing a reply queue without a selector/registry:** one request's reply can be matched to another request by mistake.
- **Retrying with a new request ID after a timeout:** the service may perform the side effect twice.
- **Waiting for a reply inside an uncommitted transaction:** the responder does not see the request to process.
- **Swallowing reply-send errors:** the caller times out without enough logged information to investigate.
- **Using request-reply for long tasks:** holds a waiting thread for a long time; consider an asynchronous command and a result event.
- **Using a temporary queue for flows that need long-term reply storage:** a temporary destination is tied to the connection and is not suitable as a durable result store.

## 13. Testing timeouts and cleanup

Testing needs to observe the caller, the responder, and the broker:

1. The responder replies quickly: the caller receives the correct payload and correlation ID.
2. The responder is not running: the caller returns a timeout at the configured time.
3. The responder replies after the timeout: the caller does not receive the reply; the responder records an error/late reply according to policy.
4. The request's TTL expires before delivery: the responder does not process the expired request.
5. The request is delivered before the TTL but processing takes long: check the business deadline at the responder.
6. Send many concurrent requests: replies are not matched incorrectly between callers.
7. Throw an exception when creating the request, sending, receiving, or cleaning up: the producer/consumer/temporary queue is released.
8. The broker disconnects while waiting: distinguish a timeout from a JMS/provider exception.
9. The caller retries with the same request ID: the responder returns the old result or processes it idempotently.
10. Application restart: no abandoned temporary destinations remain; the shared reply registry is cleaned up correctly.

Metrics should separate the number of requests sent, replies received, timeouts, provider exceptions, late replies, requests that exceeded TTL, responder processing time, temporary destination creation/deletion, and the number of waiters. Logs should include the request ID, correlation ID, destination, and deadline; avoid logging sensitive payloads.

## 14. Design checklist

1. Does the request need an immediate response, or can an asynchronous event be used?
2. Is the reply destination a dedicated temporary queue or a shared/permanent queue?
3. Where is `JMSReplyTo` set and read?
4. Is the correlation ID stable and copied into the response?
5. Is `receiveTimeout` finite and appropriate to the caller's deadline?
6. Is a request TTL needed to drop requests not yet delivered after the deadline?
7. Does the responder check the business deadline before side effects?
8. Is a timeout handled as an undetermined outcome rather than a cancellation?
9. Does a retry keep the same request ID/idempotency key?
10. Is the TemporaryQueue deleted in every branch: success, timeout, and exception?
11. Are the consumer and producer closed before deleting the temporary destination?
12. Does the shared reply queue have a correlation registry, timeout cleanup, and a late-reply policy?
13. Does it avoid waiting for a reply inside an uncommitted transaction?
14. Are there tests for concurrent requests, late replies, broker failure, and cleanup failure?

## 15. Key takeaways

`JMSReplyTo` specifies where the responder sends the response; `JMSCorrelationID` links the response to the request. `JmsTemplate.sendAndReceive()` in Spring 6.2 creates a TemporaryQueue for each call, puts it into the request, waits according to `receiveTimeout`, and then closes the consumer/producer and deletes the queue in `finally`. The default `receiveTimeout` is to wait indefinitely (`0`); a finite timeout returns `null` if there is no reply yet. A timeout does not cancel the request and does not roll back the responder's side effects. The request TTL controls how long the broker is still allowed to deliver the request; the business deadline must be checked separately by the application. When you manage a temporary destination yourself, you must use the same connection to create the consumer and delete the queue after closing the consumer. For retries, keep a stable request ID and make the responder idempotent to avoid repeating business operations.

### References

- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 — Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
- [Spring Framework 6.2.14 — JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Framework 6.2.18 — JmsMessagingTemplate Javadoc](https://www.springframework.org/spring/docs/6.2.18/javadoc-api/org/springframework/jms/core/JmsMessagingTemplate.html)
- [Jakarta Messaging 3.1 Specification — Request/reply and temporary destinations](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Spring Integration 6.2 — JMS outbound gateway and reply handling](https://docs.spring.io/spring-integration/reference/6.2/jms.html)