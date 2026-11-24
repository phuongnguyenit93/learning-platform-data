# The Path of SUBSCRIBE to the Broker

> Goal: trace a STOMP `SUBSCRIBE` from a WebSocket client through Spring's channels and handlers to the simple broker or an external STOMP broker; understand how the broker stores subscriptions, selects matching messages, and sends `MESSAGE` back to the client; and configure ACK, receipt, user destinations, and authorization correctly for each type of broker.

## 1. What does SUBSCRIBE do?

In STOMP, `SUBSCRIBE` registers a client to receive messages from a destination. The client sends a frame with `destination` and `id`; the server creates a subscription and from then on can send matching `MESSAGE` frames to the client. `SUBSCRIBE` does not carry a business payload like `SEND`; it declares where the client wants to listen.

Example:

```text
SUBSCRIBE
id:prices-sub-1
destination:/topic/prices
ack:auto

^@
```

`id` is a subscription identifier that is unique within a STOMP connection. `destination` is the target name that the broker understands. `ack` chooses how the client acknowledges delivered messages; if omitted, STOMP defaults to `auto`. `^@` in the example represents the NULL byte (`0x00`) that terminates the frame.

STOMP treats a destination as an opaque string. `/topic` is commonly used for publish-subscribe and `/queue` is commonly used for point-to-point, but the actual semantics are determined by the broker and its configuration. Do not infer delivery guarantees from the prefix name alone.

## 2. The full path in Spring

Once the client has opened the WebSocket and the STOMP session, a `SUBSCRIBE` frame passes through the following main components:

```text
WebSocket client
      |
      | STOMP SUBSCRIBE
      v
WebSocket transport / STOMP decoder
      |
      v
clientInboundChannel
      |
      +--> ChannelInterceptor / Spring Security
      |
      |
      +--> UserDestinationMessageHandler (/user/...)
      |
      |
      +--> SimpAnnotationMethodMessageHandler (@SubscribeMapping)
      |
      +--> SimpleBrokerMessageHandler
      |          or
      +--> StompBrokerRelayMessageHandler
                         |
                         v
                 External STOMP broker

Broker publishes the matching message
      |
      v
clientOutboundChannel
      |
      v
STOMP encoder / WebSocket session
      |
      v
WebSocket client receives MESSAGE
```

At the transport layer, Spring decodes the STOMP frame into a Spring `Message<?>`, converts the protocol headers into message headers, and then sends the message into `clientInboundChannel`. The handlers registered on the channel process the message by type (`SUBSCRIBE`, `MESSAGE`, `UNSUBSCRIBE`) and destination.

With an ordinary broker destination such as `/topic/prices`, the message goes to the broker handler. With a `/user/...` destination, Spring has a user destination resolution step. With an application destination mapped by `@SubscribeMapping`, the controller can return a response directly to the client. These branches need to be distinguished when reading logs or debugging.

## 3. Step 1 — decode the frame and create a Spring Message

The client sends `SUBSCRIBE` over WebSocket. Spring converts the frame into a message with key information such as:

- A message type corresponding to `SUBSCRIBE`.
- The destination, for example `/topic/prices`.
- The subscription ID, for example `prices-sub-1`.
- The WebSocket session ID to identify the connection.
- The `Principal`/user if the HTTP handshake was authenticated.
- Other STOMP headers such as `ack`, `receipt`, and broker extension headers.

Spring's internal headers are usually accessed through `SimpMessageHeaderAccessor` or `StompHeaderAccessor`. Application code should use an accessor instead of guessing internal header names.

A valid frame must have `destination` and `id`. If a required header is missing, if it uses a subscription ID that already exists in the same connection, or if the broker cannot create the subscription, the server may return `ERROR` per the STOMP protocol. Each connection is allowed to have multiple subscriptions, but their IDs must be different.

## 4. Step 2 — clientInboundChannel and interceptors

`clientInboundChannel` is the shared entry point for messages from WebSocket clients. This is where the application can apply processing before a message reaches the broker:

- Authentication and authorization by user, message type, and destination.
- Checking that a subscription is within the tenant or room scope that the user is allowed to access.
- Logging/auditing with the session ID, subscription ID, and destination.
- Measuring the number of subscriptions, the frequency of subscribe/unsubscribe, and errors.
- Blocking invalid destinations or headers that exceed limits.

A `ChannelInterceptor` can inspect the message in `preSend`. If the interceptor returns `null`, the message is not forwarded through the channel. When rejecting, the application should record a safe reason so operations can investigate without exposing tokens or sensitive data.

Do not treat a client's ability to send a destination as evidence that they have permission to read that destination. A subscription is a right to read data; permission must be checked before the broker stores the subscription.

## 5. Step 3 — routing by destination prefix

With the common STOMP configuration, Spring uses prefixes to distinguish destinations meant for controllers from destinations meant for the broker:

| Destination | Handling component | Purpose |
|---|---|---|
| `/app/...` | `SimpAnnotationMethodMessageHandler` when a matching `@SubscribeMapping` exists | One-time response when the client subscribes to an application endpoint |
| `/topic/...` | Simple broker or broker relay | Subscription receiving broadcasts from publishers |
| `/queue/...` | Simple broker or broker relay | Subscription with queue semantics provided by the broker |
| `/user/...` | `UserDestinationMessageHandler` | Converts a general destination name into a destination specific to the user/session |

The `/topic` and `/queue` prefixes are commonly used conventions. STOMP does not require every broker to define them the same way. Check the destination syntax, wildcards, queue semantics, and subscription options of the actual broker.

Example of simple broker configuration:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class StompConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
```

In this configuration, `/ws` is the HTTP endpoint used for the WebSocket handshake. `/app` is for messages going into controllers; `/topic` and `/queue` are passed to the simple broker. A `SUBSCRIBE` to `/topic/prices` goes to the broker handler, while a `SUBSCRIBE` to `/app/...` is handled only if there is a mapping such as `@SubscribeMapping`.

## 6. The `@SubscribeMapping` branch: a one-time response from the application

`@SubscribeMapping` maps a STOMP `SUBSCRIBE` to a controller method. It is useful when the client needs to fetch an initial snapshot, for example the current state of a price board or the contents of a chat room.

Example:

```java
import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.simp.annotation.SubscribeMapping;
import org.springframework.stereotype.Controller;

@Controller
class RoomSnapshotController {

    private final RoomService roomService;

    RoomSnapshotController(RoomService roomService) {
        this.roomService = roomService;
    }

    @SubscribeMapping("/room/{roomId}/snapshot")
    public RoomSnapshot snapshot(@DestinationVariable String roomId) {
        return roomService.currentSnapshot(roomId);
    }
}
```

The client subscribes to `/app/room/42/snapshot`. By default, the return value is sent directly through `clientOutboundChannel` to that client; the response does not go through the broker and does not create a long-lived broadcast subscription. If you want to send the result through the broker, you can use `@SendTo` or `@SendToUser`.

A common pattern is to use two subscriptions: `/app/room/42/snapshot` to fetch the initial state and `/topic/room/42/events` to receive continuous updates. Do not map the same prefix to both the controller and the broker unless you intend for both to handle the same message; the handlers may run in parallel and there is no guarantee about processing order between them.

## 7. The `/user` branch: resolving destinations per user

Spring recognizes destinations that start with `/user/` and passes them to `UserDestinationMessageHandler`. For example, the client subscribes:

```text
SUBSCRIBE
id:private-updates
destination:/user/queue/position-updates

^@
```

Spring converts the general destination into a physical destination specific to the user session, such as `/queue/position-updates-user123`. The physical name is an internal detail; the client only needs to know the destination `/user/queue/position-updates`.

This approach prevents two users from subscribing to the same general name and mistakenly receiving each other's private messages. When sending to a user, the server can use `SimpMessagingTemplate.convertAndSendToUser(username, "/queue/position-updates", payload)` or `@SendToUser`.

If a user has multiple WebSocket sessions, by default the message can be sent to all sessions subscribed to that destination. With `@SendToUser(broadcast = false)`, Spring sends only to the session that produced the message. In an environment with multiple application nodes, you need to configure broadcasting for unresolved user destinations if the user may be connected on another node.

When using an external broker, check the mechanism for cleaning up physical queues that are no longer active. The broker may need auto-delete or a destination purge policy after the WebSocket session ends.

## 8. The simple broker branch: storing subscriptions in memory

`SimpleBrokerMessageHandler` is the broker built into Spring. When it receives `SUBSCRIBE`, it records the subscription in an internal registry, associating the destination with the session ID and subscription ID. The broker keeps this information in the memory of the application process.

When a message is sent to a destination, the simple broker finds the subscriptions that match the destination and then creates an outbound message for each matching session. It supports path-style destinations and Ant-style patterns, for example `/topic/prices.*` or `/topic/room/**`, depending on the `PathMatcher` and configuration.

The simple broker is suitable for getting started, demos, or small applications with basic broadcast requirements. It stores subscriptions in memory, serves only the connections that instance manages, and is not suitable as a distributed broker for multiple nodes.

The simple broker supports only part of the STOMP protocol; it does not support ACK, RECEIPT, and some full-broker features. If the application needs message acknowledgement, advanced queue semantics, durability, or clustering, use an external STOMP broker through the broker relay.

## 9. The broker relay branch: forwarding SUBSCRIBE to an external broker

When `enableStompBrokerRelay` is enabled, `StompBrokerRelayMessageHandler` receives messages destined for the broker and forwards them over TCP to a broker that supports STOMP, such as RabbitMQ or ActiveMQ.

Configuration example:

```java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("broker.internal")
            .setRelayPort(61613);
}
```

The relay forwards the `SUBSCRIBE` frame to the broker. The external broker is responsible for creating the subscription, storing the necessary state, selecting messages, and publishing `MESSAGE` according to the destination's semantics. The Spring relay receives the frames the broker returns and routes them back to the correct WebSocket client/session.

The relay maintains one system TCP connection for messages originating from the server-side application and a separate TCP connection for each WebSocket client. The connections that represent clients in the relay are given the configured credentials. The broker manages the actual subscriptions, while Spring maintains the link between the client connection and the corresponding TCP connection.

If the broker loses its connection, the relay automatically tries to reconnect the system connection. Client connections are not automatically restored as an old session; the client needs to detect the failure, reconnect, and resend its subscriptions. Use `BrokerAvailabilityEvent` to monitor the state of the system connection and prepare to handle `MessageDeliveryException` when the broker is unavailable.

## 10. Step 4 — the broker matches the destination and publishes MESSAGE

When a publisher sends a message to a destination that already has subscriptions, the broker chooses the matching subscriptions according to the destination's semantics and the broker's policy. With STOMP, a message sent to the client uses a `MESSAGE` frame.

Example:

```text
MESSAGE
subscription:prices-sub-1
message-id:msg-9081
destination:/topic/prices
content-type:application/json

{"symbol":"ABC","price":125.50}
^@
```

Important headers:

- `subscription`: must match the `id` of the subscription the client created.
- `message-id`: the message identifier provided by the server/broker.
- `destination`: the destination the message is sent to.
- `ack`: present when the subscription uses `client` or `client-individual`; this value is used in the ACK/NACK frame.

The broker can also forward application headers from the original message and add its own headers. Do not assume that one broker's extension headers are present on another broker.

## 11. Step 5 — clientOutboundChannel returns the message to WebSocket

The message published by the broker is put by Spring into `clientOutboundChannel`. This channel passes the message to the corresponding WebSocket session; the STOMP encoder creates the `MESSAGE` frame and sends it over the WebSocket connection.

Because `clientOutboundChannel` is usually backed by a thread pool, the order in which the client receives messages may differ from the order in which the broker published them. If the business logic needs to preserve publish order within the same client session, you can enable `registry.setPreservePublishOrder(true)`. This option increases processing cost, so enable it only when needed.

Spring Security focuses on protecting `clientInboundChannel`; it does not check each message on `clientOutboundChannel`, because one inbound message can produce many outbound messages. Therefore, the subscribe permission needs to be checked strictly before the broker stores the subscription. A subscription that is allowed to read may cause the client to receive many messages later.

## 12. Subscription ID and subscription lifecycle

STOMP 1.2 requires `id` in `SUBSCRIBE`. Within the same connection, each subscription must have its own ID. This ID links:

- The original `SUBSCRIBE` frame.
- The `subscription` header in the corresponding `MESSAGE` frames.
- The `UNSUBSCRIBE` frame used to remove the subscription.

Example of unsubscribe:

```text
UNSUBSCRIBE
id:prices-sub-1

^@
```

A client can subscribe to the same destination multiple times with different IDs; depending on the broker, each subscription may create a separate delivery stream. Avoid unintended duplicate registrations on reconnect or when a UI component is mounted multiple times. The client should keep the subscription handle and call unsubscribe when it no longer needs to receive data.

When the WebSocket session closes, Spring/the broker cleans up the subscriptions tied to that connection. With an external broker, physical queues or durable subscriptions can have their own lifecycle configured by the broker; read the provider's documentation.

## 13. ACK mode: the client acknowledges messages after subscribing

The `ack` header in `SUBSCRIBE` determines how received messages are acknowledged:

| Value | Meaning |
|---|---|
| `auto` | The client does not need to send ACK; the server considers the message received as soon as it is sent. This is the default if the header is omitted and can cause messages to be lost if the client has not finished processing. |
| `client` | The client sends ACK; the acknowledgement is cumulative for the specified message and all earlier messages on the subscription. |
| `client-individual` | The client sends a separate ACK for each message; ACKing one message does not acknowledge earlier messages. |

With `client` or `client-individual`, the `MESSAGE` frame has an `ack` header for the client to use in `ACK` or `NACK`. `NACK` reports that the client did not process the message; the broker may redeliver, discard, or send it to a DLQ depending on the broker's capabilities and policy.

Example of client-individual:

```text
SUBSCRIBE
id:orders-sub-1
destination:/queue/orders
ack:client-individual

^@

MESSAGE
subscription:orders-sub-1
message-id:broker-message-55
ack:ack-token-55
destination:/queue/orders

{"orderId":"ORD-55"}
^@

ACK
id:ack-token-55

^@
```

The value in `ACK.id` in STOMP 1.2 must match the `ack` header of the `MESSAGE` frame. An ACK confirms, at the protocol level, that the client has processed the message; it does not automatically commit a database or guarantee that business side effects have completed. The client still needs to handle duplicates and persist business state durably.

Spring's simple broker does not support ACK/NACK. If the application needs client acknowledgement, redelivery, or broker-specific dead-letter behavior, use the broker relay and confirm that the provider supports the right semantics.

## 14. Receipt: confirming the broker has processed SUBSCRIBE

The client can add a `receipt` header to `SUBSCRIBE` to ask the server to return a `RECEIPT` frame after processing that frame:

```text
SUBSCRIBE
id:prices-sub-1
destination:/topic/prices
receipt:prices-sub-ready

^@

RECEIPT
receipt-id:prices-sub-ready

^@
```

A receipt is useful when the client needs to know the subscription has been processed by the server before taking the next step. It confirms frame processing at the protocol level; it does not confirm that a business message has been sent or that a consumer has processed the message.

The simple broker does not support RECEIPT. With the simple broker, `SessionSubscribeEvent` indicates that Spring has received the SUBSCRIBE frame; if you need to know that the broker handler has finished processing the subscription, Spring offers a server-side option: an `ExecutorChannelInterceptor` on `brokerChannel` and the `afterMessageHandled` callback. With an external broker, check the receipt support and semantics in the broker's documentation.

Do not confuse `SessionSubscribeEvent` with a receipt confirming the subscription is ready. The event is a lifecycle signal in Spring; a receipt is a protocol response from the server/broker.

## 15. `SessionSubscribeEvent` and observing subscriptions

Spring publishes `SessionSubscribeEvent` when it receives a `SUBSCRIBE` frame. The event can be used to audit or record the session, user, destination, and subscription ID.

Example:

```java
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionSubscribeEvent;

@Component
class SubscriptionAuditListener {

    @EventListener
    public void onSubscribe(SessionSubscribeEvent event) {
        SimpMessageHeaderAccessor headers =
                SimpMessageHeaderAccessor.wrap(event.getMessage());

        String sessionId = headers.getSessionId();
        String subscriptionId = headers.getSubscriptionId();
        String destination = headers.getDestination();

        // Record audit/metrics; permission checks were already handled at the inbound channel.
    }
}
```

Do not write tokens, cookies, or whole sensitive payloads into audit logs. You can combine it with `SessionUnsubscribeEvent` to track clients cancelling subscriptions and `SessionDisconnectEvent` to clean up state tied to the session. The disconnect event can appear more than once; cleanup logic must be idempotent.

## 16. Protecting SUBSCRIBE permissions with Spring Security

Spring Security distinguishes the message type `MESSAGE` (usually corresponding to a client sending `SEND`) from `SUBSCRIBE`. These two permissions must be evaluated separately:

- Allow users to subscribe to `/topic/system/notifications` to read notifications.
- Do not allow clients to send `MESSAGE` directly into `/topic/system/notifications`; otherwise clients could forge system messages.
- Allow users to subscribe to `/user/**` or `/topic/private/**` only when they are logged in and have the appropriate permission.
- Check permissions by tenant/room/resource when the destination contains a resource identifier.

Example of an authorization manager for modern Spring Security:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;
import org.springframework.messaging.simp.SimpMessageType;

@Configuration
@EnableWebSocketSecurity
class WebSocketSecurityConfiguration {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {
        messages
                .nullDestMatcher().authenticated()
                .simpSubscribeDestMatchers("/topic/announcements").permitAll()
                .simpSubscribeDestMatchers("/topic/private/**", "/user/**").hasRole("USER")
                .simpSubscribeDestMatchers("/app/**").denyAll()
                .simpDestMatchers("/app/**").hasRole("USER")
                .simpTypeMatchers(SimpMessageType.MESSAGE, SimpMessageType.SUBSCRIBE).denyAll()
                .anyMessage().denyAll();
        return messages.build();
    }
}
```

The rules are evaluated in the order they are declared. For example: allow reading public announcements, require the `USER` role for private topics and user destinations, block subscribing to `/app/**`, allow users to send messages only to `/app/**`, and then deny the remaining message types. Adjust the matchers according to the application's actual destinations and roles.

`@EnableWebSocketSecurity` also requires a CSRF token for STOMP `CONNECT` under the default configuration. The HTTP handshake must be authenticated; the `Principal` is passed by Spring into WebSocket messaging. Authorization on `SUBSCRIBE` is especially important because Spring Security does not filter each outbound message individually.

## 17. How does `SUBSCRIBE` differ from `SEND` and `@MessageMapping`?

| Frame / mapping | Role | Common path |
|---|---|---|
| `SUBSCRIBE /topic/...` | Register to receive repeated messages | `clientInboundChannel` → broker → subscription registry |
| `SEND /app/...` | Send a business request into the application | `clientInboundChannel` → `@MessageMapping` |
| `SUBSCRIBE /app/...` with `@SubscribeMapping` | Get a one-time response from the controller | `clientInboundChannel` → `@SubscribeMapping` → `clientOutboundChannel` |
| `SUBSCRIBE /user/...` | Register to receive private messages for a user/session | `clientInboundChannel` → `UserDestinationMessageHandler` → broker |

An ordinary `@MessageMapping` handles messages sent to an application destination; it is not the default handler for subscriptions. `@SubscribeMapping` is the mapping meant for SUBSCRIBE frames.

## 18. Destination patterns, selectors, and broker-specific limits

STOMP allows a server to support extension headers on `SUBSCRIBE` to adjust delivery semantics, for example a selector or a durable subscription. Those headers are not portable features of every broker.

The simple broker supports path-like destinations and Ant-style patterns per the Spring configuration. An external broker may use its own destination syntax, wildcards, selectors, durable subscriptions, or shared subscriptions. Check the broker's documentation before putting extension headers into the client.

If the destination is `/queue/orders`, you cannot conclude that every broker will distribute messages the same way. Some brokers use competing consumers, some support separate subscriptions, durable consumers, or other policies. Queue/topic semantics are the broker's responsibility.

## 19. Message ordering and concurrency

Spring uses executor-backed channels for inbound and outbound messaging. When multiple messages are processed in parallel, the processing order or the order in which clients receive them can differ from the order in which they entered the channel or were published by the broker.

If you need to preserve outbound order within the same session, use `MessageBrokerRegistry.setPreservePublishOrder(true)`. If you need to preserve inbound receive order per session, you can configure `StompEndpointRegistry.setPreserveReceiveOrder(true)`. Both options have a performance cost; enable them only when the business requirements need it.

Subscriptions across multiple sessions can also receive the same message on a topic. With a queue, how messages are distributed to multiple consumers is defined by the broker. Test ordering, duplicates, concurrency, and load tolerance with the exact broker.

## 20. Common mistakes when tracing SUBSCRIBE

- **Confusing `/app` with a broker prefix:** `/app` is usually reserved for controllers; only `/topic` and `/queue` are passed to the broker in the example configuration.
- **Using `@MessageMapping` to handle subscriptions:** use `@SubscribeMapping` for responses tied to SUBSCRIBE.
- **Thinking `@SubscribeMapping` creates a long-lived subscription:** the response goes straight back to the client by default and is not stored in the broker registry.
- **Not sending a subscription ID or using a duplicate ID:** `MESSAGE`, `ACK`, and `UNSUBSCRIBE` cannot be linked to the correct subscription.
- **Trusting that `/topic` always has the same semantics:** STOMP leaves destination semantics for the broker to decide.
- **Using the simple broker but expecting ACK/RECEIPT:** the simple broker does not support these features.
- **Protecting only SEND and ignoring SUBSCRIBE:** a client can read private data if it is allowed to register for an inappropriate destination.
- **Allowing clients to send MESSAGE directly into broker topics:** this can enable forging of system messages.
- **Treating SessionSubscribeEvent as confirmation that the broker has stored the subscription:** the event indicates that Spring received the frame; use receipt when the broker supports it or monitor the broker handler's completion.
- **Assuming the broker relay automatically recovers every client session:** the relay restores the system connection; clients need to reconnect and subscribe again.
- **Forgetting to cancel subscriptions when a component is no longer used:** it may continue to receive messages and hold unnecessary resources.
- **Assuming the outbound channel is filtered message by message by Spring Security:** you need to protect subscriptions at the inbound channel.

## 21. Testing the SUBSCRIBE path

You should test with a real WebSocket/STOMP client and broker:

1. The client CONNECTs successfully and then SUBSCRIBEs to a valid destination; confirm that the broker received the registration.
2. A publisher sends a message to the right destination; the client receives a `MESSAGE` whose `subscription` matches the registered ID.
3. A publisher sends to a different destination; the client does not receive messages outside its subscription.
4. The client sends multiple SUBSCRIBEs with different IDs; confirm that each subscription is distinguished.
5. The client sends a duplicate ID or omits destination/id; confirm the error per the protocol/server.
6. The client UNSUBSCRIBEs; subsequent messages are no longer sent through that subscription.
7. The client disconnects; the subscriptions tied to the session are cleaned up according to the broker policy.
8. Test `/user/queue/...`: the user receives private messages and other users cannot read them.
9. Test `@SubscribeMapping`: the snapshot response goes back to the correct session and does not create unintended broadcasts.
10. Test `ack:auto`, `ack:client`, `ack:client-individual`, and ACK/NACK if the broker supports them.
11. Test receipt on SUBSCRIBE; confirm that the simple broker does not support it and that the external broker responds correctly if it does.
12. A user without permission to subscribe to a private topic is rejected; a user cannot SEND directly to a forbidden broker topic.
13. Restart the broker relay; the client detects the disconnect, reconnects, and re-registers its subscriptions.
14. Send many messages concurrently; check ordering, duplicates, latency, and queue depth.

When debugging, record the STOMP command, destination, session ID, subscription ID, user, broker type, the time SUBSCRIBE was received, the time of the receipt (if any), the message ID, and the authorization result. Do not log credentials or sensitive payloads.

## 22. Subscription implementation process

1. Choose the destination and determine whether it belongs to a controller, a user destination, or the broker.
2. Define consistent broker/application prefixes in `MessageBrokerRegistry`.
3. Choose the simple broker for basic broadcast or the broker relay for ACK, receipt, durability, clustering, and full broker features.
4. Send SUBSCRIBE with a unique ID, the correct destination, and a suitable ACK mode.
5. Protect SUBSCRIBE by Principal, role, tenant, and resource; block clients from SENDing to destinations meant only for the broker.
6. Use `/user` for private messages and `@SubscribeMapping` for one-time snapshot responses.
7. Confirm that the subscription is ready using a receipt if the broker supports it; distinguish lifecycle events from protocol receipts.
8. Monitor outbound MESSAGE, ACK/NACK, UNSUBSCRIBE, and disconnect; make cleanup idempotent.
9. Test routing, authorization, user isolation, broker restart, ordering, and provider-specific semantics.

## 23. Conclusion

A `SUBSCRIBE` frame travels from WebSocket through the STOMP decoder into `clientInboundChannel`, passes through interceptors and authorization, and is then routed by destination. Broker destinations are handled by `SimpleBrokerMessageHandler` or `StompBrokerRelayMessageHandler`; `/user` destinations are resolved by Spring per user/session; application destinations can be handled with `@SubscribeMapping`.

The broker stores the subscription, matches published messages to destinations, and publishes `MESSAGE` frames through `clientOutboundChannel` to the correct WebSocket session. The subscription ID links SUBSCRIBE, MESSAGE, and UNSUBSCRIBE; the ACK mode determines how the client acknowledges messages. Choose the broker according to the features you need, verify read permission right at SUBSCRIBE, and test both the registration direction and the message-return direction.

## References

- [STOMP Protocol Specification 1.2 — SUBSCRIBE, ACK, NACK and MESSAGE](https://stomp.github.io/stomp-specification-1.2.html)
- [Spring Framework Reference — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework Reference — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework Reference — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework Reference — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework Reference — Annotated Controllers and @SubscribeMapping](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [Spring Security Reference — WebSocket Authorization](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- [Spring Framework Reference — Application Context Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [Spring Framework Reference — Order of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html)