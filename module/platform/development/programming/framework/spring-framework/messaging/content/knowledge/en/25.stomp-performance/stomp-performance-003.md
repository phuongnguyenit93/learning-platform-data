# setPreservePublishOrder and Per-Session Send Ordering

## Objective

In Spring WebSocket/STOMP, one message may be published before another, yet the client receives them in a different order. A common cause is that messages on a channel are processed by multiple threads. Spring provides the **setPreservePublishOrder(true)** option to preserve the send order to each WebSocket session.

This lesson explains the guarantee scope of this option, how to configure it, its relationship with client message receive ordering, performance overhead, and how to test it. After this lesson, you will be able to decide when to enable publish ordering and avoid mistaking it for a system-wide ordering mechanism.

## 1. Why Can Send Order Be Reversed?

In a typical STOMP configuration, messages from the broker are passed to **clientOutboundChannel** before being written to a WebSocket session. This channel is usually backed by a ThreadPoolExecutor. Multiple messages can be handed off to different worker threads and finish processing in a different order than they were placed on the channel.

Suppose the application publishes three events in order:

~~~text
publish(event-1)
publish(event-2)
publish(event-3)
~~~

If outbound processing runs in parallel, a session might observe the following result:

~~~text
publish order:  event-1 -> event-2 -> event-3
receive order:  event-2 -> event-1 -> event-3
~~~

This is a noticeable issue when the client updates the UI or state according to an event sequence. For example:

- An order transitions sequentially from CREATED to PAID and then SHIPPED.
- A job emits progress updates of 10%, 40%, 80%, 100%.
- A collaborative editing session receives document mutation operations.
- A dashboard receives status events that must be applied in order.

If the client receives SHIPPED before PAID, UI logic may display an old state after a new state or apply an incorrect transformation.

WebSocket frame ordering on a single connection does not solve this problem by itself. The problem occurs before messages are written to the connection: worker threads can finish processing messages in different orders.

## 2. What Does setPreservePublishOrder(true) Do?

**MessageBrokerRegistry.setPreservePublishOrder(true)** instructs Spring to send messages to clientOutboundChannel one by one in publish order for each client session.

When this flag is enabled, Spring uses the OrderedMessageChannelDecorator mechanism to coordinate message sending. Messages intended for the same session are passed to the outbound channel one message at a time, preserving the publish order emitted by the broker.

Guarantee scope to remember:

- Order is preserved **within the same client session**.
- Each session is handled according to its own send sequence.
- It does not establish a global order across all clients or all sessions.
- It does not automatically determine business order for events published concurrently from multiple threads.
- It incurs performance overhead because it reduces parallel processing on the send path to a session.

This option does not replace designing event ordering at the business layer. It preserves order at Spring's publish-to-client boundary; the application still needs to determine which event must precede another.

## 3. Java Configuration

Configuration is done in the configureMessageBroker method of WebSocketMessageBrokerConfigurer:

~~~java
package com.example.messaging;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");

        // Preserve publish order to each client session.
        registry.setPreservePublishOrder(true);
    }
}
~~~

The key line is:

~~~java
registry.setPreservePublishOrder(true);
~~~

By default, this option is false. When not enabled, Spring can process outbound messages concurrently, and the order clients receive may not match the publish order.

The flag can be enabled with either the simple broker or a broker relay in the message broker configuration. Choosing the simple broker or an external broker does not change the core meaning of the flag at Spring's outbound layer. However, an external broker has its own delivery and ordering rules; both layers must be evaluated when using a relay.

## 4. XML Configuration

If the application uses the XML namespace instead of Java configuration, the same option can be enabled with the preserve-publish-order attribute:

~~~xml
<websocket:message-broker
        application-destination-prefix="/app"
        preserve-publish-order="true">

    <websocket:stomp-endpoint path="/ws"/>

    <websocket:simple-broker prefix="/topic,/queue"/>
</websocket:message-broker>
~~~

The XML attribute corresponding to the Java method is preserve-publish-order. Do not configure both styles just to enable the same behavior; choose the configuration style that fits your application.

## 5. An Example of an Event Sequence Within the Same Session

Suppose an application tracks order processing progress. A service publishes three updates to the user's topic:

~~~java
@Service
public class OrderProgressPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderProgressPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publishProgress(String orderId) {
        messagingTemplate.convertAndSend(
                "/topic/orders/" + orderId,
                new ProgressEvent(orderId, 10, "STARTED")
        );

        messagingTemplate.convertAndSend(
                "/topic/orders/" + orderId,
                new ProgressEvent(orderId, 60, "PROCESSING")
        );

        messagingTemplate.convertAndSend(
                "/topic/orders/" + orderId,
                new ProgressEvent(orderId, 100, "COMPLETED")
        );
    }
}
~~~

Illustrative DTO:

~~~java
public record ProgressEvent(
        String orderId,
        int percent,
        String status
) {
}
~~~

Client subscribing to receive events:

~~~javascript
client.onConnect = () => {
  client.subscribe("/topic/orders/42", (frame) => {
    const event = JSON.parse(frame.body);
    renderProgress(event.percent, event.status);
  });
};
~~~

With setPreservePublishOrder(true), messages published to the same session are sent one by one in publish order. If a client has multiple subscriptions, the outbound order of messages destined for that session is also coordinated by the same principle.

This example assumes the publish calls are executed sequentially in the same processing flow. If multiple threads concurrently publish events for the same order, the application must first establish business order among those threads.

## 6. Per-Session Guarantee, Not Global Ordering

This is the most important limitation of the API.

Suppose two clients A and B both subscribe to /topic/orders. Spring preserves send order separately for A and separately for B. That does not mean:

- The first message is guaranteed to arrive at A before B.
- All sessions process messages at the exact same time.
- Ordering between two independent destinations is synchronized system-wide.
- A message published later from another thread will always be considered a newer business event.

For example, if A and B both receive E1 and E2, Spring preserves publish order for each session. However, network latency, JavaScript processing speed, and callback timing of A and B can differ.

If you need global ordering or a consistent business order across multiple instances, you need an ordering mechanism at the application or broker layer. You can use sequence numbers, partition keys, a sequential processing pipeline per aggregate, or an ordered event log.

Do not use setPreservePublishOrder as a distributed lock. It does not synchronize transactions, database commits, or independent publishers.

## 7. Concurrent Publishers and Business Ordering

A subtle situation arises when multiple threads call SimpMessagingTemplate concurrently.

~~~java
executor.submit(() -> publish("PAID"));
executor.submit(() -> publish("SHIPPED"));
~~~

If the two tasks run concurrently, business order cannot be inferred solely from the order of the two submit lines. The thread pool may execute or call the broker in a different order. setPreservePublishOrder only preserves message order once they enter the publish path to a session; it does not decide which task must win when two publishers compete.

If the business requirement states that PAID must always precede SHIPPED, establish the order before sending:

- Emit events from a sequential stream keyed by orderId.
- Use a dedicated queue or sequential executor per aggregate.
- Assign monotonically increasing sequence numbers where state transitions are decided.
- Publish only after a valid state transition has been committed.
- Allow clients to detect gaps or out-of-order messages using sequence numbers.

Example DTO with sequence:

~~~java
public record OrderEvent(
        String orderId,
        long sequence,
        String eventType
) {
}
~~~

Clients can ignore stale events or buffer an early-arriving event until the event with the preceding sequence has been applied. This approach solves ordering at the business layer and remains useful even when messages traverse multiple services or brokers.

## 8. Client Message Receive Order Is a Separate Setting

setPreservePublishOrder controls messages going from the broker to the client through **clientOutboundChannel**. It does not control the order of messages the client sends to the server.

The inbound flow passes through **clientInboundChannel**. This channel can also be backed by a ThreadPoolExecutor, so messages received from the same session can be processed on different threads.

Since Spring Framework 6.1, there is a separate option:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws");

    // Preserve the processing order of messages received from the same session.
    registry.setPreserveReceiveOrder(true);
}
~~~

The two flags have different scopes:

| Configuration | Message Direction | Purpose |
| --- | --- | --- |
| MessageBrokerRegistry.setPreservePublishOrder(true) | Server → client | Preserves outbound publish order within each session |
| StompEndpointRegistry.setPreserveReceiveOrder(true) | Client → server | Preserves inbound processing order within each session |

If business logic requires both directions, both can be enabled. However, each flag has its own processing overhead. Do not enable them just to make every message "safer"; identify which direction truly needs serialization.

## 9. Ordering in Browser-Side Callbacks

setPreservePublishOrder controls the order in which Spring emits messages to the session. It does not automatically serialize asynchronous work initiated by a JavaScript callback.

Example:

~~~javascript
client.subscribe("/topic/orders", async (frame) => {
  const event = JSON.parse(frame.body);
  await saveToIndexedDb(event);
  render(event);
});
~~~

If the library invokes the callback for E1 and then E2, but saveToIndexedDb for E2 finishes before E1, the UI can still render E2 before E1. This is client task completion order, which differs from frame arrival order.

If the client needs sequential application, a promise chain can be used:

~~~javascript
let processing = Promise.resolve();

client.subscribe("/topic/orders", (frame) => {
  const event = JSON.parse(frame.body);

  processing = processing.then(() => processEvent(event)).catch((error) => {
    reportProcessingError(error);
  });
});
~~~

This queues processing tasks in the order callbacks are invoked. Errors must be handled inside the chain so one error does not leave the promise chain permanently rejected and block all subsequent messages.

For data streams that may arrive duplicated or delayed, sequence numbers remain a more reliable verification mechanism than relying solely on callback timing.

## 10. Performance Cost and When to Enable

When setPreservePublishOrder is enabled, Spring sends messages to each session one message at a time. This reduces outbound parallel processing for the same session and adds coordination overhead.

Actual impact depends on:

- Messages per second per session.
- Payload size and WebSocket write duration.
- Number of connected sessions.
- Thread count and channel executor configuration.
- Whether clients read messages slowly or frequently stall.
- Whether messages must preserve strict order or can be reordered on the client.

Consider enabling when:

- Messages represent consecutive steps of a state transition.
- Clients apply patches or deltas that require strict ordering.
- A subsequent message depends on the outcome of the previous message.
- Reordering produces an invalid state and the client lacks sequence/reordering logic.

You may not need to enable it when:

- Messages are independent, such as independent telemetry metrics.
- Clients always take the latest snapshot and discard stale updates.
- The business layer already includes sequence numbers and clients sort them.
- Throughput is more important than per-session processing order.

Do not guess overhead solely from session count. Benchmark with representative load and measure throughput, p95/p99 latency, queue depth, CPU, memory, and how often clients fall behind. Enable the flag only for application flows that genuinely require ordering when the architecture allows separate configuration.

## 11. Testing Publish Ordering

A useful integration test should verify the actual order of messages received from a session, rather than merely asserting that the configuration property is true.

Procedure:

1. Start the application with a STOMP endpoint and setPreservePublishOrder(true).
2. Connect a client and subscribe to a destination.
3. Publish events with sequences 1, 2, 3, ... in a deterministic flow.
4. Collect messages on the client until the expected count is received.
5. Compare the received sequences against the expected order.
6. Repeat with more messages and higher load to increase the chance of catching race conditions.
7. Connect a second client and verify each session receives the correct sequence, without asserting relative ordering between the two clients.

To demonstrate the effect of the flag, you can run the same scenario with false and true. However, testing with the flag set to false does not necessarily reproduce reordering on every run; race conditions depend on thread scheduling and load. A test that observes no reordering does not prove that the default guarantees ordering.

There should be a separate test for inbound if the application enables setPreserveReceiveOrder(true): send multiple messages sequentially from the same client session and verify the order handlers process them. Do not use an inbound test to draw conclusions about outbound or vice versa.

## 12. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| Enabling the flag preserves order across all clients | The flag preserves order separately within each session; it creates no global clock or global order. |
| This flag orders events by business time | The flag preserves publish order on the outbound path; the application must determine business order beforehand. |
| It also preserves the order of messages sent by clients to the server | Inbound has a separate flag, setPreserveReceiveOrder. |
| Asynchronous JavaScript callbacks will complete in order | The flag does not wait for Promises created by callbacks; the client must serialize processing if needed. |
| Enabling the flag has no performance impact | Sequential sending reduces per-session parallelism and adds overhead. |
| This flag alone provides exactly-once delivery | The flag does not provide durable storage, ACKs, business retries, or exactly-once semantics. |
| It fixes race conditions between publishers | It does not decide business order among tasks running concurrently. |

## 13. Key Takeaways

- By default, clientOutboundChannel can process messages across multiple threads and clients may receive them in a different order than published.
- setPreservePublishOrder(true) preserves outbound order within each client session by sending one message at a time.
- The flag does not create global ordering across sessions and does not resolve business ordering among concurrent publishers.
- setPreserveReceiveOrder(true) is a separate inbound flag, available since Spring Framework 6.1.
- Client-side asynchronous callbacks can finish out of order even when frames arrive in order.
- Preserving order has a cost; benchmark and enable it only when business requirements demand it.
- Sequence numbers and sequential processing per aggregate protect order at the business layer, even when messages traverse multiple systems.

## References

- [Spring Framework — Order of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html)
- [MessageBrokerRegistry Javadoc — setPreservePublishOrder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/config/MessageBrokerRegistry.html)
- [StompEndpointRegistry Javadoc — setPreserveReceiveOrder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/config/annotation/StompEndpointRegistry.html)
- [Spring Framework — Message Flow](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [OrderedMessageChannelDecorator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/broker/OrderedMessageChannelDecorator.html)

