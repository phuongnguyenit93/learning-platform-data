# The Path of a Message Published from the Server to Subscribers

## Objectives

After this lesson, you can:

- Describe the complete path of a message published by the server to STOMP subscribers.
- Distinguish `brokerChannel`, `clientOutboundChannel`, and `clientInboundChannel`.
- Use `SimpMessagingTemplate` to send messages from a service, an HTTP endpoint, or a background task.
- Understand how the return value of `@MessageMapping` goes through the broker and reaches subscribers.
- Distinguish broadcasting to a shared destination from sending to a single user via `/user/`.
- Follow the differences between the simple broker and the STOMP broker relay.
- Understand the roles of the subscription registry, the outbound executor, send ordering, and broker state.
- Identify why a successful send into a channel does not mean the subscriber has processed the message.

## 1. The big picture

In Spring STOMP over WebSocket, the server does not look up each WebSocket session itself to write data. The server creates a Spring `Message<?>` and sends it to the broker channel; the broker finds the subscriptions whose destination matches and publishes a STOMP `MESSAGE` to the corresponding clients.

The flow when the server publishes to a shared destination:

~~~text
Service / HTTP controller / scheduled task
                 |
                 v
        SimpMessagingTemplate
                 |
                 v
        Spring Message<?>
        destination + headers + payload
                 |
                 v
            brokerChannel
                 |
                 v
        Simple broker handler
        or STOMP broker relay
                 |
                 v
        Find subscriptions matching the destination
                 |
                 v
        clientOutboundChannel
                 |
                 v
        STOMP encode / WebSocket handler
                 |
                 v
           WebSocket session
                 |
                 v
           Client receives MESSAGE
~~~

If the message is sent to a destination of the `/user/` form, Spring performs an additional user destination resolution step before the broker routes it:

~~~text
SimpMessagingTemplate
        |
        v
    brokerChannel
        |
        v
UserDestinationMessageHandler
        |
        v
Destination specific to the user/session
        |
        v
       Broker
        |
        v
clientOutboundChannel -> WebSocket -> client
~~~

Spring uses three main channels:

| Channel | Direction | Role |
|---|---|---|
| `clientInboundChannel` | Client → server | Receives STOMP frames from WebSocket clients after decoding |
| `brokerChannel` | Server → broker | Receives messages published from server code for the broker to process |
| `clientOutboundChannel` | Server → client | Carries messages from the broker to the corresponding WebSocket session |

These channels create boundaries between where a message is created, where it is routed, and where it is written down to the client connection. This is the core of the server-side message flow in Spring Framework 7.0.10.

## 2. Subscribers must register first

Before the server publishes a message, the client has usually already connected over STOMP and sent a `SUBSCRIBE` to the destination it wants to receive from.

Example of a client subscribing to price updates:

~~~text
SUBSCRIBE
id:quotes-ui
destination:/topic/quotes
ack:auto

^@
~~~

Spring receives the frame over WebSocket, decodes it into a Spring `Message<?>`, and sends it into `clientInboundChannel`. The broker handler processes the subscribe request and stores the subscription in the broker's registry.

Only after the subscription is registered does the broker have the information to route messages to the client. A client can register for multiple destinations or multiple subscriptions for the same destination; each subscription has its own ID.

The key point: the server publishes a message to a destination, and the broker is responsible for finding the matching subscribers. Business code usually does not need to know the session ID or the specific WebSocket connection of each subscriber.

## 3. Publishing a message from any server component

The most common way is to inject `SimpMessagingTemplate` and call `convertAndSend`.

~~~java
@Service
public class QuotePublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public QuotePublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(QuoteUpdate update) {
        messagingTemplate.convertAndSend("/topic/quotes", update);
    }
}
~~~

`SimpMessagingTemplate` converts the payload into a Spring `Message<?>` using a suitable message converter, attaches the destination, and sends the message to `brokerChannel`.

This code can be called from:

- A service after a business update succeeds.
- An HTTP controller after receiving a REST request.
- A scheduled task that publishes data periodically.
- An application event listener after a domain event occurs.
- A component that processes background data or receives results from another system.

Example of calling from an HTTP endpoint:

~~~java
@RestController
@RequestMapping("/api/quotes")
public class QuoteRestController {

    private final QuotePublisher publisher;

    public QuoteRestController(QuotePublisher publisher) {
        this.publisher = publisher;
    }

    @PostMapping
    public ResponseEntity<Void> publish(@RequestBody QuoteUpdate update) {
        publisher.publish(update);
        return ResponseEntity.accepted().build();
    }
}
~~~

When the REST request completes, the message has been sent through the messaging infrastructure according to the configuration. The HTTP response `202 Accepted` in the example is only the endpoint's decision; it does not prove that the browser has received or processed the message.

### convertAndSend and send

Use `convertAndSend(destination, payload)` when you want Spring to convert an object into a message.

~~~java
messagingTemplate.convertAndSend(
        "/topic/orders",
        new OrderUpdate("ORD-1001", "SHIPPED")
);
~~~

Use `send(Message<?>)` when you already have a Spring `Message<?>` and want to control the headers:

~~~java
Message<OrderUpdate> message = MessageBuilder
        .withPayload(new OrderUpdate("ORD-1001", "SHIPPED"))
        .setHeader("eventType", "OrderShipped")
        .build();

messagingTemplate.send(
        MessageBuilder.fromMessage(message)
                .setHeader(SimpMessageHeaderAccessor.DESTINATION_HEADER, "/topic/orders")
                .build()
);
~~~

For a pre-built message, the destination header must have a valid value. You can use `SimpMessageHeaderAccessor` to create and set dedicated messaging headers instead of arbitrarily naming headers yourself.

## 4. What does BrokerChannel do?

`brokerChannel` is the `MessageChannel` that server-side application code uses to send messages to the broker. `SimpMessagingTemplate` is configured by Spring to send into this channel.

When a message goes into `brokerChannel`:

1. Spring converts the payload into a Spring `Message<?>` and attaches the destination.
2. The broker-side handlers receive the message from the channel.
3. If the destination is a user destination, `UserDestinationMessageHandler` resolves the destination before the broker processes it.
4. The simple broker or the broker relay accepts the routed message.
5. The broker finds the subscriptions that match the destination.
6. The broker publishes the message to `clientOutboundChannel` for each matching subscriber.

`brokerChannel` is not a WebSocket channel, and it is not a place that stores messages for clients. It is the point that moves messages from server code to the broker's routing mechanism.

### A message can come from a controller or a service

An HTTP controller and a background service can send to the same destination:

~~~java
messagingTemplate.convertAndSend("/topic/system-status", status);
~~~

This allows different publishing sources to use the same routing mechanism. Subscribers do not need to know whether a message came from an HTTP request, a scheduler, or another service.

## 5. The return value from @MessageMapping also goes through the broker

Another source of server-side messages is the return value of a method annotated with `@MessageMapping`.

~~~java
@Controller
public class GreetingController {

    @MessageMapping("/greeting")
    @SendTo("/topic/greetings")
    public GreetingReply greet(GreetingRequest request) {
        return new GreetingReply(
                request.name(),
                "Hello, " + request.name()
        );
    }
}
~~~

The client sends a request to an application destination:

~~~text
SEND
destination:/app/greeting
content-type:application/json

{"name":"Lan"}^@
~~~

Processing flow:

1. The frame is decoded and passed into `clientInboundChannel`.
2. The `/app` prefix routes the message to the annotated controller.
3. Spring calls `GreetingController.greet(...)`.
4. The return value is converted into a payload by the message converter.
5. `@SendTo("/topic/greetings")` sets the outbound destination.
6. Spring sends the message through `brokerChannel`.
7. The broker finds the subscriptions on `/topic/greetings`.
8. The broker publishes a STOMP `MESSAGE` through `clientOutboundChannel` to the subscribers.

If `@SendTo` is not used, Spring can derive a default destination from the input destination: for example, `/app/greeting` is mapped to `/topic/greeting`. Use `@SendTo` when you want to declare the destination explicitly or publish to multiple destinations.

`@SendTo` is a convenience built on a message-sending mechanism similar to `SimpMessagingTemplate`. For complex logic, the controller can inject the template and proactively publish messages from the method.

### @SubscribeMapping has a different path

`@SubscribeMapping` handles a subscribe frame to an application destination. By default, the return value is sent directly to the client through `clientOutboundChannel`, does not go through `brokerChannel` to be broadcast, and is not stored as a long-lived broker subscription.

Example:

~~~java
@Controller
public class DashboardController {

    @SubscribeMapping("/dashboard/snapshot")
    public DashboardSnapshot snapshot() {
        return dashboardService.currentSnapshot();
    }
}
~~~

The client subscribes to `/app/dashboard/snapshot` to receive the initial snapshot. Afterwards, the client can subscribe to `/topic/dashboard-updates` to receive continuous updates through the broker.

Use this approach when you need a one-time response for the subscriber. If you want to send to the broker and broadcast, you can combine it with `@SendTo` or use `SimpMessagingTemplate`.

## 6. Sending to a single user with /user/

A broadcast destination such as `/topic/quotes` sends the message to every matching subscription. When you need to send data privately to one user, Spring provides user destinations.

Client subscribes:

~~~text
SUBSCRIBE
id:private-alerts
destination:/user/queue/alerts
ack:auto

^@
~~~

The server sends to the user named `alice`:

~~~java
messagingTemplate.convertAndSendToUser(
        "alice",
        "/queue/alerts",
        new Alert("Your report is ready")
);
~~~

Spring receives the logical destination `/user/alice/queue/alerts`, finds that user's active sessions, and converts it into physical destinations specific to each session, for example:

~~~text
/user/alice/queue/alerts
          |
          v
/queue/alerts-user-sessionA
/queue/alerts-user-sessionB
~~~

The client still subscribes using the shared destination `/user/queue/alerts`; the client does not need to know the internal suffix.

By default, if a user has multiple sessions, all sessions subscribed to that destination can receive the message. With `@SendToUser`, you can set `broadcast = false` to send only to the session that issued the current request.

User destinations usually rely on the `Principal` determined during the WebSocket handshake. Therefore, you need to configure authentication and ensure that the user name the server passes to `convertAndSendToUser` matches the identity that Spring manages.

### User destinations across multiple servers

If the application runs on multiple nodes, a user may be connected to a different node from the one publishing the message. You can configure `userDestinationBroadcast` to broadcast unresolved user destinations to other nodes to try to process.

When using an external broker, look at the broker's policy for cleaning up per-session destinations/queues to avoid keeping queues that are no longer active.

## 7. Simple broker and broker relay

Spring has two main ways of handling subscriptions and broadcasting.

| Characteristic | Simple broker | STOMP broker relay |
|---|---|---|
| Subscription registry | In the memory of the Spring application | Managed by the external broker |
| Routing | Spring's simple broker handler | Relayed over STOMP/TCP to the broker |
| Scope | Suitable for simple, single-node applications | Suitable for dedicated brokers and multi-node deployments |
| STOMP features | Supports only part of the protocol | Depends on the external broker |
| Storage and redelivery | Does not provide message persistence like a dedicated broker | According to the broker's configuration and capabilities |

### Simple broker

Configuration:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

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
~~~

The simple broker stores subscriptions in memory and publishes messages to connected clients whose destinations match. It supports path-style and pattern destinations. The subscription registry is lost when the application stops.

The simple broker suits small applications or when you need a quick start. It supports only part of STOMP; features such as ACK, receipt, and clustering need to be checked against the documentation for the Spring version in use.

### STOMP broker relay

When using an external broker, replace the configuration with:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("localhost")
            .setRelayPort(61613)
            .setSystemLogin("system")
            .setSystemPasscode("system-secret")
            .setClientLogin("web")
            .setClientPasscode("web-secret");
}
~~~

The relay sends messages from the server to the broker over a shared TCP connection called the **system connection**. This connection is for messages originating from the server-side application. The relay also creates a separate TCP connection for each WebSocket client to forward the client's frames to the broker and receive the messages the broker sends back.

When the broker publishes a message to a client, the relay passes the frame back to Spring, then the message goes through `clientOutboundChannel` and is written down to the appropriate WebSocket session.

The broker relay has a mechanism to reconnect the system connection when the broker temporarily loses its connection. However, the WebSocket client still needs its own reconnect logic. The external broker must have STOMP support enabled and be configured with suitable destinations, credentials, heartbeat, ACLs, and queue policies.

## 8. clientOutboundChannel and message ordering

After the broker finds a subscriber, the message is sent into `clientOutboundChannel`. This channel delivers the message to the corresponding WebSocket session; Spring converts the message into a STOMP frame and writes it to the socket.

In the default configuration, the outbound channel is backed by a thread pool. Multiple messages can be processed on different threads, so the order the client observes can differ from the order in which the broker published them.

If the application needs to preserve publish order within the same client session, enable:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setPreservePublishOrder(true);
}
~~~

When enabled, messages within the same client session are published through `clientOutboundChannel` sequentially in order. This option has a small performance cost; enable it only when ordering is truly a business requirement.

Preserving outbound order does not replace a sequence number at the business layer. If the client needs to detect messages that are missing, duplicated, or out of order due to retries/reconnects in another system, put a sequence/version into the payload and let the client check it.

## 9. Sending a message does not mean the subscriber has processed it

The following steps are different events:

1. `SimpMessagingTemplate` sends the Spring message to `brokerChannel`.
2. The broker receives the message and finds subscribers.
3. Spring/the broker passes the STOMP `MESSAGE` down to WebSocket.
4. The client receives the frame.
5. The client application parses the payload and processes the business logic.

A successful send result at step 1 does not prove that step 4 or 5 has completed. If you need business confirmation, design a response/event with a correlation ID or a suitable acknowledgement protocol.

A few notes:

- The simple broker publishes to existing subscriptions; it is not a durable message store from which offline clients can receive messages later.
- With a broker relay, durability, queue retention, redelivery, and acknowledgement depend on the broker and the subscription configuration.
- If a destination has no matching subscriber, no client receives the message from that publication.
- If the payload needs to be JSON, configure a suitable message converter and check the schema between server and client.
- Avoid sending large objects or publishing at too high a frequency; monitor frame size, the number of subscribers, the outbound queue, and send time.

## 10. BrokerAvailabilityEvent and send failures

When using a broker relay, the system connection to the broker can be lost and then restored. Spring publishes a `BrokerAvailabilityEvent` so the application knows whether the broker is available or unavailable.

You can observe the event:

~~~java
@Component
public class BrokerStatusListener
        implements ApplicationListener<BrokerAvailabilityEvent> {

    @Override
    public void onApplicationEvent(BrokerAvailabilityEvent event) {
        if (event.isBrokerAvailable()) {
            log.info("STOMP broker is available");
        }
        else {
            log.warn("STOMP broker is unavailable");
        }
    }
}
~~~

Components that send messages should observe this state and still handle `MessageDeliveryException` when calling the template. Do not assume the broker relay is always available just because WebSocket clients are still connected.

Other events useful for operations:

- `SessionConnectEvent`: the client starts a STOMP session.
- `SessionConnectedEvent`: the broker has returned CONNECTED.
- `SessionSubscribeEvent`: the client registers a subscription.
- `SessionUnsubscribeEvent`: the client cancels a subscription.
- `SessionDisconnectEvent`: the STOMP session ends; this event can be published multiple times for the same session, so handling must be idempotent.

## 11. Integration example: the server publishes order events

The classes below are integration beans in a Spring MVC + WebSocket application with STOMP enabled. This is an application configuration example, not a standalone Java program.

Endpoint and broker configuration:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

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
~~~

Payload:

~~~java
public record OrderUpdate(
        String orderId,
        String status,
        long version
) {}
~~~

Publisher:

~~~java
@Service
public class OrderEventPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderEventPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(OrderUpdate update) {
        messagingTemplate.convertAndSend("/topic/order-updates", update);
    }

    public void publishForUser(String username, OrderUpdate update) {
        messagingTemplate.convertAndSendToUser(
                username,
                "/queue/order-updates",
                update
        );
    }
}
~~~

HTTP endpoint that triggers publishing:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderUpdateController {

    private final OrderEventPublisher publisher;

    public OrderUpdateController(OrderEventPublisher publisher) {
        this.publisher = publisher;
    }

    @PostMapping("/{orderId}/status")
    public ResponseEntity<Void> updateStatus(
            @PathVariable String orderId,
            @RequestBody StatusRequest request) {

        OrderUpdate update = new OrderUpdate(
                orderId,
                request.status(),
                request.version()
        );

        // In a real application, call the publisher after the business update commits.
        publisher.publish(update);

        return ResponseEntity.accepted().build();
    }
}

public record StatusRequest(String status, long version) {}
~~~

Client subscribes:

~~~text
SUBSCRIBE
id:order-updates-ui
destination:/topic/order-updates
ack:auto

^@
~~~

When the HTTP endpoint calls the publisher, the message goes through `brokerChannel`, the broker finds the subscription `order-updates-ui`, and then Spring sends a STOMP `MESSAGE` down to the WebSocket session:

~~~text
MESSAGE
destination:/topic/order-updates
subscription:order-updates-ui
message-id:broker-message-id
content-type:application/json

{"orderId":"ORD-1001","status":"SHIPPED","version":3}^@
~~~

The `message-id` header and how native headers are represented depend on the broker/protocol handler. The JSON payload is produced from `OrderUpdate` through the configured message converter.

## 12. Common mistakes

1. **Calling the template but the client does not receive anything.** Check that the client SUBSCRIBEd before publishing and whether the destination matches.
2. **Sending to the wrong prefix.** `/app` is usually for controller mappings; `/topic` and `/queue` are usually for the broker according to the Spring configuration.
3. **Assuming brokerChannel sends straight to the socket.** This channel passes the message to the broker handler for routing.
4. **Managing WebSocket sessions yourself in a service.** Use `SimpMessagingTemplate` so the broker chooses sessions by subscription.
5. **Using /topic for private sending.** Use `convertAndSendToUser` and have the client subscribe to `/user/queue/...`.
6. **Using /user but the broker receives it directly.** Configure the destination prefix so that `UserDestinationMessageHandler` processes it before the broker.
7. **Assuming @SubscribeMapping creates a long-lived subscription.** By default the return value is sent directly to the client as a one-time response.
8. **Assuming @SendTo sends directly over WebSocket.** The return value still goes through brokerChannel and the broker.
9. **Assuming every subscriber receives the message even when offline.** The simple broker keeps subscriptions in memory; delivery to offline clients depends on the broker and durable subscriptions.
10. **Assuming outbound order is always preserved.** Enable `setPreservePublishOrder(true)` when per-session ordering is required.
11. **Treating HTTP 202 or a successful template send as the client having processed it.** To know that business processing has completed, you need a separate acknowledgement/event response.
12. **Ignoring broker availability.** With a broker relay, observe `BrokerAvailabilityEvent` and handle `MessageDeliveryException`.
13. **Configuring the relay but the broker has not enabled STOMP.** Check the broker's STOMP listener port, credentials, virtual host, and heartbeat.
14. **Not checking subscribe and send permissions.** Protect endpoints, destinations, and user destinations according to the identity of the WebSocket session.
15. **Sending payloads without a stable schema.** Use DTOs/records, a version or event type, and test the converter on both sides.

## 13. Testing checklist

- [ ] The client connects to the correct STOMP endpoint and receives CONNECTED.
- [ ] The client sends SUBSCRIBE to the intended destination.
- [ ] Verify that the subscription has been registered by the broker before publishing.
- [ ] Call `SimpMessagingTemplate.convertAndSend` from a service or HTTP endpoint.
- [ ] Confirm the message goes through brokerChannel and reaches the broker handler.
- [ ] Confirm that only subscribers with a matching destination receive the STOMP MESSAGE.
- [ ] Check the payload converter, content type, and headers.
- [ ] Test the `@MessageMapping` return value and `@SendTo`.
- [ ] Test the direct `@SubscribeMapping` response.
- [ ] Test `convertAndSendToUser` with a user having one and multiple sessions.
- [ ] Test the simple broker and the broker relay if the application supports both.
- [ ] Check outbound ordering when many messages are published quickly.
- [ ] Disconnect the broker relay and confirm BrokerAvailabilityEvent along with send failure handling.
- [ ] Test the case of no subscribers or a subscriber disconnecting.
- [ ] Verify that the client reconnects and resubscribes after the WebSocket loses its connection.

## 14. Conclusion

A message published from the server starts in a service, controller, or background task. `SimpMessagingTemplate` converts the payload into a Spring `Message<?>` and sends it to `brokerChannel`. The broker processes the destination, finds the matching subscriptions, and publishes the message through `clientOutboundChannel`; Spring encodes it into a STOMP `MESSAGE` and writes it down to the WebSocket session. With `/user/`, Spring resolves the destination into an address specific to the user/session before the broker routes it. The simple broker keeps subscriptions in memory; the broker relay passes messages over a TCP connection to a dedicated broker. You need to check outbound ordering, broker state, and application-level acknowledgement to know whether a message has reached the subscriber and how far it has been processed.

## Official references

- [Spring Framework 7.0.10 Reference: Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html) — the three channels, the flow from the controller to the broker and from the broker to clientOutboundChannel.
- [Spring Framework 7.0.10 Reference: Sending Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html) — using SimpMessagingTemplate from any application component.
- [Spring Framework 7.0.10 Reference: Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html) — return value, @SendTo, @SendToUser, and @SubscribeMapping.
- [Spring Framework 7.0.10 Reference: User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html) — resolving /user destinations by user/session.
- [Spring Framework 7.0.10 Reference: Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html) — storing subscriptions in memory and broadcasting to matching destinations.
- [Spring Framework 7.0.10 Reference: External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html) — the broker relay and TCP connections.
- [Spring Framework 7.0.10 Reference: Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html) — the system connection, client connections, heartbeat, and reconnect.
- [Spring Framework 7.0.10 Reference: Order of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html) — clientOutboundChannel processing order and setPreservePublishOrder.
- [Spring Framework 7.0.10 Reference: Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html) — BrokerAvailabilityEvent and STOMP session lifecycle events.
