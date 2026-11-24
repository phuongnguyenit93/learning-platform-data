# Replying from a Listener with Return Values and @SendTo in Spring JMS

## 1. From a One-Way Listener to Request-Reply

A method annotated with `@JmsListener` is usually used to receive a message and perform business processing. The method can declare a `void` return type if it only needs to process the message. When the method returns a value, Spring JMS can package that value into a JMS message and send a reply to a destination.

Spring supports three ways to determine where to send the reply:

- **`JMSReplyTo` on the request:** the destination specified by the requester for each message. If this header is present, the listener adapter sends the reply to that destination.
- **`@SendTo`:** the default destination declared on the listener method or class. Spring uses this destination when the request has no `JMSReplyTo`.
- **`JmsResponse<T>`:** the result includes the reply payload and a destination chosen at runtime. This approach is suitable when the destination depends on the request content or the processing result.

This lets the listener focus on processing the request and producing the result. Spring JMS handles converting the result into a JMS message and sending it to the determined destination.

After this lesson, you should be able to:

- Distinguish a one-way listener from a listener with a reply.
- Use a non-void return type to create a reply.
- Choose the destination via JMSReplyTo or @SendTo.
- Use JmsResponse when you need to choose the destination dynamically.
- Return a Spring Message to add headers to the reply.
- Configure the converter and QoS for the reply.
- Combine a reply listener with a JmsTemplate request-reply.
- Handle timeouts, reply-send errors, correlation, and destination security.

## 2. The Return Value Handling Mechanism

Spring JMS uses the listener adapter infrastructure to call the method annotated with `@JmsListener`. When the method returns an object, the adapter converts that object into a `jakarta.jms.Message` using the configured `MessageConverter`, and then sends the message to the response destination.

General flow:

~~~text
Request producer
      |
      | JMS Message
      | may include JMSReplyTo
      v
Request destination / queue
      |
      v
Spring JMS listener container
      |
      v
@JmsListener method
      |
      | returns an object
      v
MessageConverter
      |
      v
JMS reply message
      |
      v
JMSReplyTo or the default destination from @SendTo
      |
      v
Reply consumer
~~~

You need to distinguish two tasks:

- The listener method produces the **business result**.
- The listener adapter performs the **reply transport** via JMS.

If the method returns `void`, Spring has no return value to send as a reply automatically. If the method has a non-void return type, configure an appropriate destination so the reply has a clear place to go.

This mechanism belongs to Spring JMS. The `@SendTo` annotation is reused from the package `org.springframework.messaging.handler.annotation`, but here it configures the response destination for the JMS listener.

## 3. @SendTo: The Default Reply Destination

### 3.1 Basic Example

`@SendTo` declares the default destination for the return value:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Component;

@Component
public class OrderRequestListener {

    private final OrderService orderService;

    public OrderRequestListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @JmsListener(destination = "orders.request")
    @SendTo("orders.reply")
    public OrderStatus process(OrderCommand command) {
        return orderService.process(command);
    }
}
~~~

`OrderCommand`, `OrderStatus`, and `OrderService` are application types. The listener receives a command from `orders.request`, calls the service, and returns the status. Spring converts the result into a JMS message and sends it to `orders.reply` if the request does not provide `JMSReplyTo`.

This example requires:

- `@EnableJms` to enable the annotation-driven listener infrastructure.
- A valid `ConnectionFactory`.
- A suitable listener container factory.
- A MessageConverter capable of converting the request and response types.
- A queue or destination with access permissions according to the broker configuration.

### 3.2 @SendTo Is the Default Destination

If the request has the `JMSReplyTo` header, Spring sends the reply to the destination specified in that header. `@SendTo` is used as the default destination when the request has no `JMSReplyTo`.

You can understand the selection order as:

1. The request has `JMSReplyTo`: send the reply to that destination.
2. The request has no `JMSReplyTo` but the listener has `@SendTo`: use the destination from `@SendTo`.
3. No reply destination is configured: the application cannot determine where to send the reply; you need to add an explicit route if you want to use automatic reply.

Therefore, `@SendTo` does not force every request to receive its reply on the same queue. The sender can specify a separate destination per request using `JMSReplyTo`.

### 3.3 Placing @SendTo at the Class Level

If multiple listener methods use the same default response destination, you can place `@SendTo` on the class:

~~~java
@Component
@SendTo("orders.reply")
public class OrderListenerGroup {

    @JmsListener(destination = "orders.create")
    public OrderStatus create(CreateOrder command) {
        return createOrder(command);
    }

    @JmsListener(destination = "orders.cancel")
    public CancelStatus cancel(CancelOrder command) {
        return cancelOrder(command);
    }
}
~~~

The class-level annotation provides the default reply destination for the listener methods in the class. If a method needs its own default destination, you can declare `@SendTo` on that method to make the method's contract explicit.

## 4. JMSReplyTo: A Destination Chosen by the Requester

### 4.1 The Meaning of JMSReplyTo

`JMSReplyTo` is a standard JMS header that contains a `Destination` the consumer can use to send a reply. This header belongs to the request message; it is not simply a text queue name in every case.

The sender can specify the reply destination when creating the request. The listener adapter reads this header and uses that destination for the return value.

Model:

~~~text
Client                         Listener
  |                                |
  | Request                        |
  | JMSReplyTo = reply destination |
  |------------------------------->|
  |                                | process
  |                                |
  |<-------------------------------|
  | Reply to JMSReplyTo             |
~~~

The strength of this approach is that one listener can serve many callers, each with its own reply destination. The listener does not need to hard-code each client's reply queue.

### 4.2 JmsTemplate Creates a Temporary Reply Queue Itself

`JmsTemplate` provides the request-reply operation `sendAndReceive`. In this operation, Spring creates a `TemporaryQueue` for the request, puts that queue in `JMSReplyTo`, and then waits for the reply on the temporary queue.

When using the convert variant, the caller can work with Java objects:

~~~java
import org.springframework.jms.core.JmsTemplate;

public class OrderRequestClient {

    private final JmsTemplate jmsTemplate;

    public OrderRequestClient(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public String requestStatus(String orderId) {
        Object reply = jmsTemplate.convertSendAndReceive(
                "orders.request",
                orderId
        );

        if (reply == null) {
            throw new IllegalStateException("No reply received in time");
        }

        return (String) reply;
    }
}
~~~

The example uses String to fit Spring JMS's commonly used default converter. If the request or reply is a DTO, configure a compatible MessageConverter, such as a JSON converter, on both the sender side and the listener.

You can configure `receiveTimeout` on JmsTemplate to limit how long the caller waits for the reply. When the timeout expires, the method may return null. The caller ceasing to wait does not cancel the work the listener has already received.

### 4.3 Temporary Destinations and Shared Destinations

A temporary reply queue is convenient for synchronous request-reply because each operation has a temporary destination managed by Spring. It suits a caller waiting for a reply for a finite time.

If you use a fixed reply queue for multiple concurrent requests, you need a mechanism to distinguish which request a reply belongs to. `JMSCorrelationID` is commonly used to link a response to a request. The caller needs to check correlation according to the designed contract; do not accept a reply solely because it appears on the same queue.

A temporary destination also has a lifecycle tied to the connection/session and the provider. Do not treat it as a place to store results long-term for the client to query after a timeout or restart.

## 5. Choosing the Response Destination at Runtime with JmsResponse

### 5.1 When Is a Dynamic Destination Needed?

`@SendTo` suits a listener with a single stable default destination. If where the reply goes depends on the tenant, request type, processing region, or business result, you need to choose the destination at runtime.

Spring JMS provides `JmsResponse<T>` in the package `org.springframework.jms.listener.adapter`. This object packages the response payload together with the target destination.

Example:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.listener.adapter.JmsResponse;
import org.springframework.stereotype.Component;

@Component
public class RegionalOrderListener {

    @JmsListener(destination = "orders.request")
    public JmsResponse<OrderStatus> process(OrderCommand command) {
        OrderStatus status = processOrder(command);

        String destination = "orders.reply." + command.region();

        return JmsResponse.forQueue(status, destination);
    }
}
~~~

`JmsResponse.forQueue` creates a response directed to the queue with the provided name. If you need to send to a topic, the API has the `forTopic` variant. The destination can be decided based on the request data or the processing result.

### 5.2 Controlling Permitted Destinations

A dynamic destination needs to be controlled. Do not arbitrarily concatenate a string sent by the client directly into a queue/topic name. If you do, the client could cause the application to send a response to a destination outside the permitted scope.

You should map the request data through a configured list of destinations or a resolver that checks permissions. For example, only accept region codes in a valid list and create the destination from controlled configuration.

You also need to ensure the broker grants send permission to the listener's connection on the destinations the application is allowed to use.

### 5.3 JmsResponse and @SendTo

The two approaches have different purposes:

| Approach | When to use |
|---|---|
| `@SendTo("orders.reply")` | A fixed default destination, declared explicitly on the listener |
| `JmsResponse.forQueue(payload, name)` | A queue destination decided when processing the request |
| `JmsResponse.forTopic(payload, name)` | A topic destination decided when processing the request |
| `JMSReplyTo` | The request sender specifies the reply destination for each message |

When you need a response route that is dynamic per business logic, JmsResponse makes the destination explicit together with the payload in the method's return value.

## 6. Returning a Spring Message to Add Headers

A listener can return `org.springframework.messaging.Message<T>` instead of just the payload. This approach lets you add metadata via the messaging abstraction before the adapter converts it into a JMS Message.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.support.MessageBuilder;

@JmsListener(destination = "orders.request")
@SendTo("orders.reply")
public Message<OrderStatus> process(OrderCommand command) {
    OrderStatus status = processOrder(command);

    return MessageBuilder
            .withPayload(status)
            .setHeader("app.responseCode", "OK")
            .setHeader("app.schemaVersion", 1)
            .build();
}
~~~

The headers in a Spring Message are metadata at the Spring layer. The adapter maps them according to the JMS message conversion and header mapping mechanism. Check the actual result if you need a specific JMS property for the consumer to use in a selector or broker administration tools.

Do not put passwords, tokens, or secret information in reply headers. Metadata passed through the broker can appear in logs or operational tools.

If you only need to send a simple DTO, returning the DTO directly is easier to read. Only return a Spring Message when you truly need additional metadata.

## 7. Converting the Response into a JMS Message

The listener's return value must be converted into a JMS Message type the provider supports. The listener container factory can configure a `MessageConverter` for both reading the request and creating the reply.

Example with a JSON converter:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;

@Configuration
@EnableJms
public class JmsListenerConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(new MappingJackson2MessageConverter());

        return factory;
    }
}
~~~

This is an illustrative configuration for Spring JMS with an appropriate Jackson dependency. Configure the type mapping and content type according to the application's message contract, especially when the producer and consumer run different versions.

If you use the default SimpleMessageConverter:

- A String is typically converted into a TextMessage.
- A byte[] is converted into a BytesMessage.
- A Map with JMS-supported values is converted into a MapMessage.
- A Serializable object can be converted into an ObjectMessage.

A non-Serializable DTO is not automatically converted into a JMS Message by SimpleMessageConverter. For DTOs, use JSON or a converter with a clear schema.

You need to ensure the converter is compatible in both directions: the request must be converted into the listener's parameter type, and the response must be converted into a JMS Message type the caller can read.

## 8. Configuring Quality of Service for the Reply

Spring lets you configure QoS specifically for the listener container's replies through `setReplyQosSettings` on `DefaultJmsListenerContainerFactory`.

The configurable values include:

- **Priority:** the priority level of the response.
- **Time to live:** how long the response remains valid.
- **Delivery mode:** the delivery mode according to the QoS configuration and the provider's capability.

Example:

~~~java
import org.springframework.jms.support.QosSettings;

QosSettings replyQos = new QosSettings();
replyQos.setPriority(2);
replyQos.setTimeToLive(10_000L);

factory.setReplyQosSettings(replyQos);
~~~

This configuration snippet is added to the factory that creates the listener container. A TTL of 10,000 milliseconds means the reply has a lifetime of 10 seconds per the configured QoS. If the reply arrives after the TTL expires, the broker may discard the message according to the provider's semantics.

The response QoS does not replace the reply wait timeout at the caller. The caller may time out before the TTL expires; conversely, the reply may expire before the caller manages to receive it. The two policies need to be designed together.

## 9. Combining a Reply Listener and JmsTemplate

A complete request-reply flow can use JmsTemplate on the client side and @JmsListener on the server side.

Listener:

~~~java
@Component
public class PriceListener {

    @JmsListener(destination = "price.request")
    @SendTo("price.reply")
    public String quote(String productCode) {
        return "PRICE:" + productCode + ":100";
    }
}
~~~

Client using request-reply:

~~~java
public String getQuote(JmsTemplate jmsTemplate, String productCode) {
    Object reply = jmsTemplate.convertSendAndReceive(
            "price.request",
            productCode
    );

    if (reply == null) {
        throw new IllegalStateException("Price service did not reply");
    }

    return (String) reply;
}
~~~

In this example, JmsTemplate creates a temporary reply queue and puts it into the request's JMSReplyTo. Therefore, the response is sent to that temporary queue; @SendTo("price.reply") is only the default destination when the request has no JMSReplyTo.

To use the fixed destination `price.reply`, the caller can send a regular request and create its own consumer on the reply queue according to the application contract. When there are multiple concurrent requests, a correlation ID is needed to match the correct response to the request. Do not use a shared reply queue without a correlation mechanism.

## 10. Handling Timeouts, Errors, and Late Replies

Synchronous request-reply makes the caller wait for the response. You need to set an appropriate receive timeout and handle the case where there is no reply.

Situations to distinguish:

- The listener has not received the request.
- The listener received it but is processing for a long time.
- The listener finished processing but sending the reply failed.
- The reply was sent but the caller's wait timed out.
- The reply was discarded by the broker due to TTL.
- The converter cannot create or read the response.
- The caller received a response but the correlation does not match the request it is waiting for.

A caller-side timeout does not cancel the listener method. If the listener continues processing after the caller times out, the response may reach a temporary destination that has expired or no longer has a consumer. With a temporary queue, the caller has no long-term storage to query the result again.

For long-running tasks, consider an asynchronous model:

1. The caller sends a command with a request ID.
2. The system returns an accepted or pending status.
3. A worker processes independently.
4. The result is stored or published as an event.
5. The caller receives the event when online or queries the result by request ID.

This approach is more suitable when the processing time is unpredictable or the caller cannot hold a connection waiting for long.

## 11. Correlation ID and Matching Requests with Responses

When using a separate temporary reply queue for each request, the destination already helps limit where the reply is received. When using a shared reply queue for multiple requests, correlation becomes important.

`JMSCorrelationID` can be used to link a response to a request. A common contract is for the response to carry a correlation ID referencing the request ID or the request's JMSMessageID. Both the producer and the consumer must agree on this rule.

Principles:

- Use a stable request ID for each logical operation.
- Do not create a new ID for the same operation on retry.
- Verify the correlation ID before completing a pending future or promise.
- Handle a reply with no correlation ID or with an ID that does not exist.
- Have a retention time limit for pending request state and clean up on timeout.
- Do not use the correlation ID as an authentication token or proof of access rights.

For request-reply using JmsTemplate's built-in API, let the API manage the temporary reply queue. If you implement a shared reply queue yourself, you need to design the consumer, selector, and correlation lifecycle explicitly.

## 12. Transactions and Reply Correctness

A listener can run in a JMS session transaction depending on the container configuration. However, you should not infer that the method returning a response automatically guarantees that the whole business logic and related systems commit atomically.

You need to determine:

- When the listener processes successfully, at what point is the request acknowledged?
- If sending the reply fails, is the request rolled back and redelivered?
- If the database update succeeds but sending the reply fails, will a retry cause repeated side effects?
- Does the response need to be published durably through the broker?
- Is an outbox/inbox or idempotency needed to ensure consistent results?

For business logic with side effects such as payment or order creation, design an idempotent service. Sending the reply and committing the database may belong to different transactions if no suitable coordination mechanism is configured.

## 13. Securing the Response Destination

The destination in JMSReplyTo may be supplied by the request sender. The application needs to control the destinations to which the listener is allowed to send replies.

You should not trust by default every destination the client sends. Consider:

- Broker authorization for send permission to the queue/topic.
- Only accept destinations within the application's scope.
- Use a destination resolver or allow-list if checking is needed.
- Do not let the client control internal destinations arbitrarily.
- Check the caller's read permission on the reply destination.
- Do not let the response contain sensitive data beyond the caller's permissions.

When using JmsResponse to choose a dynamic destination, apply the same allow-list and authorization principles.

## 14. Common Mistakes

- **Returning an object without a reply destination:** the listener has no clear route to send the reply.
- **Thinking @SendTo always overrides JMSReplyTo:** the JMSReplyTo on the request takes precedence; @SendTo is the default.
- **Using @SendTo for a destination that changes per request:** use JmsResponse if you need to choose the destination at runtime.
- **Confusing the reply destination with the request destination:** @JmsListener(destination=...) is where requests are received; @SendTo is the default place to send the reply.
- **A method returns void but expects an automatic reply:** there is no return value for the adapter to send.
- **The converter does not support the return type:** the response cannot be converted into a JMS Message.
- **Receiving JSON as a DTO when only using SimpleMessageConverter:** you need a suitable JSON converter.
- **Using a shared reply queue without correlation:** a response may be matched to the wrong request.
- **The caller times out but the listener continues:** the reply may arrive late or no longer have a consumer.
- **Using a temporary queue as a place to store results long-term:** a temporary destination has its own lifecycle and is unsuitable for querying after a restart.
- **Not controlling a client-supplied JMSReplyTo:** the listener may send data to a destination outside the permitted scope.
- **Confusing reply QoS with receive timeout:** the TTL determines how long the message remains valid; the receive timeout determines how long the caller waits.
- **Assuming the response and database commit are atomic:** you need a clear transaction strategy.

## 15. Testing Response Management

You should have integration tests with the target JMS provider/broker to verify:

1. The listener returns a String and the response is converted into a TextMessage.
2. The listener returns a DTO and the JSON converter creates a message with the correct schema.
3. @SendTo is used when the request has no JMSReplyTo.
4. The JMSReplyTo on the request takes precedence over the default @SendTo.
5. JmsTemplate.sendAndReceive or convertSendAndReceive receives the response from the temporary queue.
6. JmsResponse sends to the queue/topic chosen at runtime.
7. The returned Spring Message has the required headers after mapping.
8. The reply QoS priority and TTL are applied according to the configuration.
9. When there is no reply, the caller handles timeout/null correctly.
10. A late reply is handled according to the policy.
11. Multiple concurrent requests are matched correctly by correlation.
12. A listener error or a reply-send failure is handled according to the transaction/error policy.
13. A destination that is not permitted is rejected by the broker authorization.

Unit tests can call the business service and check the returned object. But creating the JMS Message, choosing the destination, sending the reply, and receiving it via the broker need integration tests.

## 16. Design Checklist

Before using return values and @SendTo, check:

- Does the listener really need request-reply or only one-way processing?
- What data type does the method return and does the converter support it?
- Does the request have a JMSReplyTo or does the listener need a default @SendTo?
- Is a dynamic destination needed and should JmsResponse be used?
- Is it necessary to return a Spring Message to add headers?
- Does the JmsTemplate caller have a timeout and handle null?
- Is the reply queue dedicated or shared? If shared, how is correlation managed?
- Are the reply QoS priority and TTL suitable for the caller's deadline?
- Do the listener and broker have permission to send to the reply destination?
- Has the client-supplied destination been controlled?
- Can retry, redelivery, and transactions cause repeated side effects?
- Are there integration tests for JMSReplyTo, @SendTo, JmsResponse, the converter, and timeouts?

When you understand the relationship among the return value, JMSReplyTo, @SendTo, and JmsResponse, you can build request-reply in Spring JMS with transparent destinations, correctly formatted payloads, and a controllable reply lifecycle.