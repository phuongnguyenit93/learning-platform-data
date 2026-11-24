# configureMessageBroker and Destination Prefixes

In Spring STOMP over WebSocket, clients send frames with a destination header. Spring needs to determine whether that frame is meant for an application handling method, for the message broker, or for a specific user. The configureMessageBroker method in WebSocketMessageBrokerConfigurer configures this routing rule through MessageBrokerRegistry.

The key point is that each kind of prefix has its own role:

- The application destination prefix routes messages from clients to @MessageMapping or @SubscribeMapping methods.
- The broker destination prefix routes messages and subscriptions to the built-in simple broker or the STOMP broker relay.
- The user destination prefix represents a destination specific to a user/session; Spring resolves it into actual destinations matching the user's sessions.

A destination prefix is a routing convention at the STOMP layer. It is not a URL used to open a WebSocket and does not by itself grant access permissions to clients.

## 1. Where does configureMessageBroker sit in STOMP configuration?

A STOMP configuration typically implements WebSocketMessageBrokerConfigurer and enables the infrastructure with @EnableWebSocketMessageBroker.

There are two configuration parts to distinguish:

- registerStompEndpoints registers the handshake URL that browsers or clients use to open a WebSocket.
- configureMessageBroker configures how destinations are handled in STOMP SEND, SUBSCRIBE, and messages sent from the application.

Example:

~~~java
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
        registry.setUserDestinationPrefix("/user/");
    }
}
~~~

In the example:

- /ws is the endpoint URL for the HTTP Upgrade/WebSocket handshake.
- /app is the prefix for messages sent into application handling methods.
- /topic and /queue are destination prefixes handled by the simple broker.
- /user/ is the logical prefix for destinations directed to a specific user.

The client connects to /ws. Only after the STOMP session is established does the client send SEND or SUBSCRIBE frames with the corresponding destination.

Do not add /ws to STOMP destinations. The endpoint URL and the destination are two different namespaces.

## 2. Application destination prefix

### 2.1. What is setApplicationDestinationPrefixes used for?

setApplicationDestinationPrefixes declares one or more prefixes reserved for messages that should be handled by methods annotated with @MessageMapping or @SubscribeMapping.

Example:

~~~java
registry.setApplicationDestinationPrefixes("/app");
~~~

The client sends a STOMP SEND to:

~~~text
SEND
destination:/app/chat.send

{"text":"Hello"}
~~~

Spring recognizes that the destination starts with /app, strips this prefix part, and then uses the remaining part to look up the method mapping. Therefore, the controller declares:

~~~java
@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(ChatMessage message) {
        return message;
    }
}
~~~

The method uses /chat.send, not /app/chat.send. The /app part has already been removed before the mapping lookup.

### 2.2. Multiple application prefixes can be declared

MessageBrokerRegistry allows passing multiple prefixes:

~~~java
registry.setApplicationDestinationPrefixes(
        "/app",
        "/api"
);
~~~

Then both /app/... and /api/... destinations can be routed to annotated controllers.

Spring automatically appends a trailing / to the prefix if the configured string does not already have one. This helps match on segment boundaries: the prefix /app should not be treated as matching /application.

Declare multiple prefixes only when the application has a clear reason, such as two client groups or two API conventions that must be maintained. Using a single common prefix is usually easier for clients to understand.

### 2.3. If no application prefix is configured

By default, without an application destination prefix, every destination can become eligible to be considered by the annotated method handler. When the application also enables a broker, clearly separating /app from /topic or /queue helps prevent destinations from being handled at the wrong layer.

For an ordinary STOMP application, you should set an explicit application prefix and not reuse the same prefix as broker destinations.

## 3. Broker destination prefix

### 3.1. enableSimpleBroker

enableSimpleBroker enables the simple message broker built into Spring and declares the destination prefixes that this broker handles.

~~~java
registry.enableSimpleBroker("/topic", "/queue");
~~~

The simple broker stores subscriptions in memory and sends messages to connected clients that have subscriptions matching the destination.

Example of a client subscribing:

~~~text
SUBSCRIBE
destination:/topic/prices
id:prices-sub
~~~

A component sends a message to /topic/prices. The simple broker finds subscriptions matching the destination and then publishes the message to those clients.

The /topic and /queue prefixes are common conventions. With the simple broker, both are handled by the built-in broker's subscription and broadcast mechanism. Merely naming a destination /queue does not create competing-consumer queue semantics like a JMS queue or a real queue on an external broker.

### 3.2. Choosing suitable prefixes

A commonly used convention:

| Prefix | Common intent | Example |
|---|---|---|
| /app | Client sends commands/events into the application | /app/orders.create |
| /topic | Broadcast data to matching subscribers | /topic/prices |
| /queue | Queue-style destination per broker convention | /queue/orders |
| /user/ | Logical destination specific to a user/session | /user/queue/notifications |

The names above are conventions, not mandatory STOMP keywords. An external broker may define different semantics for /queue and /topic; check the configuration and documentation of the broker in use.

### 3.3. A broker prefix is not a controller mapping

If a client sends SEND to /topic/prices, the message is routed to the broker according to the declared prefix. It will not invoke a @MessageMapping("/prices") method merely because the trailing name looks similar.

If you want the application to process the message first, the client must send to the application prefix, for example /app/prices.update. If you want the broker to deliver directly, the client uses a broker prefix such as /topic/prices.

This separation helps clearly identify which messages are commands entering business logic and which messages are subscriptions/broadcasts.

## 4. Distinguishing SEND and SUBSCRIBE when routing

STOMP uses different frames for sending messages and registering to receive messages.

- SEND delivers a payload from a client to a destination.
- SUBSCRIBE registers to receive messages sent to a destination.
- MESSAGE is the frame the broker sends back to subscribers.
- UNSUBSCRIBE cancels a registration.

With an application prefix, SEND is usually handled by @MessageMapping. SUBSCRIBE to an application destination can be handled with @SubscribeMapping.

With a broker prefix, SUBSCRIBE registers with the broker. SEND to a broker prefix can be passed by the broker to matching subscribers, depending on the broker's semantics.

Example:

~~~text
Client A                         Spring
   |                               |
   | SEND /app/chat.send           |
   |------------------------------>|
   |                               | remove /app
   |                               | invoke @MessageMapping("/chat.send")
   |                               |
   |<------ MESSAGE /topic/chat ---|
   |                               |
Client B                           |
   |                               |
   | SUBSCRIBE /topic/chat -------->|
   |                               | broker stores subscription
   |<------ MESSAGE /topic/chat ---|
~~~

This is the general flow when the controller sends the result to /topic/chat and the broker publishes it to subscribers.

## 5. Mapping destinations with @MessageMapping

@MessageMapping maps a STOMP message to a controller method based on the destination after the application prefix has been removed.

Example:

~~~java
@Controller
public class OrderController {

    @MessageMapping("/orders.create")
    @SendTo("/topic/orders")
    public OrderCreated create(CreateOrderCommand command) {
        return orderService.create(command);
    }
}
~~~

The client sends to /app/orders.create. Spring removes /app and then looks up the /orders.create mapping.

You can put a shared prefix at the class level:

~~~java
@Controller
@MessageMapping("/orders")
public class OrderController {

    @MessageMapping("/create")
    @SendTo("/topic/orders")
    public OrderCreated create(CreateOrderCommand command) {
        return orderService.create(command);
    }

    @MessageMapping("/{orderId}/cancel")
    @SendTo("/topic/orders")
    public OrderCancelled cancel(
            @DestinationVariable String orderId) {

        return orderService.cancel(orderId);
    }
}
~~~

In the example, the mappings combine into /orders/create and /orders/{orderId}/cancel. The client correspondingly sends /app/orders/create or /app/orders/123/cancel.

By default, Spring uses Ant-style path matching, supporting patterns and path variables. @DestinationVariable extracts the value from the variable part of the destination.

### 5.1. Response destination

If a @MessageMapping method returns a payload, Spring converts the payload into a message sent to the broker. You can use @SendTo to declare the destination explicitly:

~~~java
@MessageMapping("/chat.send")
@SendTo("/topic/chat")
public ChatMessage send(ChatMessage message) {
    return message;
}
~~~

If @SendTo or @SendToUser is not specified, Spring has a default destination rule for the response based on the input destination, usually replacing the application prefix with /topic. Use @SendTo when the application's contract needs a stable and readable destination.

You can send to multiple destinations by declaring multiple values in @SendTo if the use case requires broadcasting to several subscriber groups.

## 6. @SubscribeMapping and the application prefix

@SubscribeMapping handles a STOMP SUBSCRIBE frame whose destination falls under the application prefix.

Example:

~~~java
@Controller
public class DashboardController {

    @SubscribeMapping("/dashboard.initial")
    public DashboardSnapshot initialSnapshot() {
        return dashboardService.currentSnapshot();
    }
}
~~~

Client subscribes:

~~~text
SUBSCRIBE
destination:/app/dashboard.initial
id:dashboard-init
~~~

Spring removes /app, invokes the /dashboard.initial method, and then sends the result directly back to the client that sent SUBSCRIBE. By default, this response does not go through the broker and is not broadcast to every subscriber.

If you want the result of @SubscribeMapping to go through the broker, you can combine it with @SendTo:

~~~java
@SubscribeMapping("/dashboard.initial")
@SendTo("/topic/dashboard")
public DashboardSnapshot initialSnapshot() {
    return dashboardService.currentSnapshot();
}
~~~

This usage suits cases where the client needs an initial snapshot when registering. Subsequent updates can be published to /topic/dashboard.

Do not use @SubscribeMapping as a replacement for a long-lived broker subscription. It usually answers once for the registration operation; receiving continuous updates still requires subscribing to a broker destination.

## 7. User destination prefix

### 7.1. A user destination is a logical destination

Spring supports destinations targeted at a specific user through UserDestinationMessageHandler. The default prefix is /user/.

A client can subscribe:

~~~text
SUBSCRIBE
destination:/user/queue/notifications
id:notifications-sub
~~~

Spring resolves this logical destination into a unique physical destination per user/session. As a result, multiple users can subscribe to the same logical name /user/queue/notifications without receiving each other's messages.

User destinations are especially useful for personal notifications, task status, or results meant only for the logged-in user.

### 7.2. Configuring the user prefix

You can use the default or set it explicitly:

~~~java
registry.setUserDestinationPrefix("/user/");
~~~

If you change the prefix, the client and server must use the same new convention. Do not configure the broker to handle the /user/ prefix directly before Spring has a chance to resolve the user destination.

Complete configuration:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setUserDestinationPrefix("/user/");
}
~~~

### 7.3. Sending a message to a user

The server can send through SimpMessagingTemplate:

~~~java
@Service
public class NotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void notifyUser(
            String username,
            Notification notification) {

        messagingTemplate.convertAndSendToUser(
                username,
                "/queue/notifications",
                notification
        );
    }
}
~~~

username must match Principal.getName() of the authenticated user. The destination passed to convertAndSendToUser is the target part after the user prefix, usually starting with /queue; do not add /user/{username} to this destination parameter.

Spring finds the sessions currently associated with the user and resolves the destination into specific destinations for those sessions.

### 7.4. Sending to a user from a controller

You can use @SendToUser:

~~~java
@MessageMapping("/profile.refresh")
@SendToUser("/queue/profile")
public ProfileView refreshProfile(Principal principal) {
    return profileService.load(principal.getName());
}
~~~

@SendToUser routes the response to the user who sent the message. With multiple sessions of the same user, the broadcast attribute decides whether to send to all sessions or only the session that originated the request; check the default and set broadcast=false if you want to reply only to the current session.

Do not trust a username passed by the client itself in the payload to decide the recipient. Use the Principal authenticated on the server and check access permissions.

## 8. Simple broker and STOMP broker relay

### 8.1. Simple broker

The simple broker is enabled with:

~~~java
registry.enableSimpleBroker("/topic", "/queue");
~~~

Characteristics:

- Built into the Spring application.
- Stores subscriptions in memory.
- Publishes messages to connected clients with matching destinations.
- Easy to configure and suitable for demos, development, or simple applications.
- Supports only a subset of STOMP; does not provide full features such as acknowledgement and receipts.
- Not suitable for clustering or broker-level message persistence requirements.

If the application needs durable queues/topics, acknowledgements, receipts, broker clustering, or backlog management, the simple broker does not fully meet those needs.

### 8.2. STOMP broker relay

The broker relay forwards STOMP frames from Spring to an external message broker that supports STOMP, such as a broker deployed with a STOMP plugin/protocol adapter.

Example:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");

    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("broker.internal")
            .setRelayPort(61613);
}
~~~

In this configuration:

- /app still routes messages to Spring controllers.
- /topic and /queue are forwarded to the external broker.
- The external broker handles subscriptions, queues/topics, and semantics according to its product/configuration.

The broker relay creates TCP connections to the broker and forwards messages between Spring and the broker. The relay has a system connection and client connections managed according to the configuration.

Login credentials, virtual host, heartbeat, and broker address must be configured per environment. Do not hard-code credentials in source control; bind them from a secret manager or deployment security configuration.

### 8.3. Choosing the broker type

| Requirement | Simple broker | Broker relay |
|---|---|---|
| Simple initial configuration | Suitable | Requires an external broker |
| In-memory subscriptions | Yes | Managed by the broker |
| Full STOMP ACK/receipt | No | Depends on the broker |
| Durable queue/topic | Not fully provided | Depends on the broker |
| Clustering and backlog management | Not suitable | Broker can support |
| Operating independently of the Spring process | No | Yes |

When using a relay, the prefixes passed to enableStompBrokerRelay must match destinations supported by the external broker. /queue and /topic are not mandatory syntax for every broker; some brokers have their own way of naming destinations.

## 9. Distinguishing endpoint, application prefix, broker prefix, and user prefix

Four kinds of names are often confused:

| Component | Example | Role |
|---|---|---|
| WebSocket endpoint | /ws | URL to open the HTTP Upgrade connection |
| Application prefix | /app | Routes SEND/SUBSCRIBE to annotated controllers |
| Broker prefix | /topic, /queue | Routes destinations to the message broker |
| User prefix | /user/ | Logical routing to a specific user/session |

A client can:

1. Connect to /ws.
2. Send SEND to /app/orders.create.
3. Register SUBSCRIBE to /topic/orders.
4. Also register /user/queue/notifications to receive private notifications.

Using the same string for an endpoint and a destination does not make them the same route. Choose clear names and keep the client/server contract consistent.

## 10. Prefix matching and PathMatcher

### 10.1. Application prefixes are matched by segment

Spring processes application prefixes along path boundaries. For example, if /app is configured as an application prefix, then /app/orders.create matches; /application/orders.create should not be treated as a destination with the same prefix.

When a prefix does not have a trailing /, Spring adds it automatically in the application destination prefixes configuration.

Do not create multiple overlapping or nearly identical prefixes without reason, because they make routes hard to read and verify.

### 10.2. Default PathMatcher

@MessageMapping mappings use AntPathMatcher by default with / as the separator.

Example:

~~~java
@MessageMapping("/stocks/{symbol}")
public void updateStock(
        @DestinationVariable String symbol,
        StockUpdate update) {
    stockService.update(symbol, update);
}
~~~

The destination /app/stocks/ACME after removing /app matches /stocks/{symbol}, and symbol receives the value ACME.

You can use wildcards such as /stocks/** or template variables such as /stocks/{symbol}. Test patterns that could potentially overlap to ensure only the intended method is selected.

### 10.3. Using a dot as the separator

Some messaging systems prefer a dot-separated convention, for example stock.price.ACME. You can configure the PathMatcher:

~~~java
registry.setPathMatcher(new AntPathMatcher("."));
~~~

When changing the separator, update controller mappings and client destination conventions consistently. In particular, check how the simple broker matches subscription patterns and how an external broker interprets destinations. Do not change the separator on only one side.

## 11. A complete configuration with the simple broker

The following example includes the endpoint, application prefix, broker prefix, and user destination prefix:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class StompWebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");

        registry.enableSimpleBroker("/topic", "/queue");

        registry.setUserDestinationPrefix("/user/");
    }
}
~~~

Controller receiving commands and publishing results:

~~~java
@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(ChatMessage message) {
        return message;
    }
}
~~~

STOMP client:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws");
const client = Stomp.over(socket);

client.connect({}, () => {
    client.subscribe("/topic/chat", frame => {
        console.log("Received:", frame.body);
    });

    client.send(
        "/app/chat.send",
        {"content-type": "application/json"},
        JSON.stringify({text: "Hello Spring"})
    );
});
~~~

This is an illustrative snippet using STOMP.js. The exact API of the client library may vary between versions. On the Spring side, it still receives SEND /app/chat.send, invokes the /chat.send method, and sends the response to /topic/chat.

## 12. MessageBrokerRegistry configuration options

Besides the three prefix groups, MessageBrokerRegistry has several useful options.

### 12.1. Preserving publish order

~~~java
registry.setPreservePublishOrder(true);
~~~

This option asks for messages sent to a client within the same session to be published in order. It has processing overhead, so enable it only when business logic requires stable ordering.

Inbound message processing order and outbound publish order are two separate issues. If you need to preserve the order of messages sent in by clients, check the preserveReceiveOrder configuration on the STOMP endpoint registry for the Spring version in use.

### 12.2. Mapping cache limit

~~~java
registry.setCacheLimit(1024);
~~~

The cache limit adjusts the cache cap for destination registration/mapping. The value should be based on the actual number of patterns and destinations; do not raise it arbitrarily without observing memory and hit rate.

### 12.3. Customizing the broker channel

configureBrokerChannel lets you configure the channel that sends messages from the application to the broker. By default, sending through the broker channel is synchronous so that the sending code can receive an exception if sending fails. You can configure a task executor if asynchronous processing is needed, but you must evaluate the impact on ordering, backpressure, and how exceptions are observed.

Advanced options should be enabled based on operational metrics and clear requirements, without needing to be added to every application.

## 13. Destination access permissions

A prefix only decides the path of a message. It is not an authorization mechanism.

For example, a client sending to /app/admin.delete does not mean the client is allowed to delete data. Controller methods must check the Principal, permissions, and input data; Spring Security messaging configuration must control who can SEND or SUBSCRIBE to which destinations.

You need to determine separately:

- Which clients may SEND to /app/**.
- Which clients may SUBSCRIBE to /topic/**.
- Which destinations are only for authenticated users.
- Which users are allowed to send to another user's destination.
- Which credentials the broker relay uses to connect to the broker.
- Which broker ACLs restrict publish/subscribe permissions when using an external broker.

Especially with user destinations, do not take an arbitrary username from the payload to send messages. Use the authenticated Principal and check permissions before sending.

## 14. Common mistakes when configuring prefixes

### 14.1. Putting /app into @MessageMapping

If the application prefix is configured as /app, Spring removes the prefix before lookup. The correct mapping is /chat.send; declaring /app/chat.send can prevent the method from matching.

### 14.2. Client sending to the wrong prefix

SEND to /topic/chat is handled by the broker; it does not call the @MessageMapping controller. If you want to call the controller, send to /app/chat.send.

### 14.3. Confusing the endpoint URL with a destination

The client must connect to an endpoint such as /ws first and only then send a STOMP destination such as /app/orders.create. Sending an HTTP request to /app/orders.create does not create a STOMP message.

### 14.4. Thinking /queue of the simple broker has real queue semantics

The simple broker broadcasts to every subscriber matching the destination. The /queue prefix is only a route name in the simple broker configuration. Use an external broker if you need real queue semantics, persistence, or competing consumers.

### 14.5. Forgetting to configure the broker prefix

If a client SUBSCRIBEs to /topic/prices while the simple broker only accepts /queue, the subscription will not be handled by the intended broker route.

### 14.6. Configuring a user prefix overlapping with a broker prefix

If the broker accepts /user/** directly, the message may go to the wrong layer before UserDestinationMessageHandler resolves the destination. Ensure the user prefix is handled as a logical destination and that the target after resolution falls under a valid broker prefix.

### 14.7. The external broker does not support the declared prefix

The broker relay only forwards frames. Destinations must follow the broker's syntax and configuration. Check the STOMP plugin, virtual host, queues/topics, and ACLs.

### 14.8. Using the simple broker for ACK or durable subscription requirements

The simple broker does not have all the features of an external broker. Switch to a broker relay if you need ACK/receipt, persistence, durable subscriptions, or clustering.

### 14.9. Not checking the route of @SubscribeMapping

@SubscribeMapping handles SUBSCRIBE to an application prefix and usually returns a response directly to the client. If you expect the response to be broadcast through the broker, you need @SendTo or an explicit route design.

### 14.10. Treating a prefix as a security boundary

Names like /admin or /private do not protect a destination by themselves. Configure authorization at the Spring Security and broker ACL layers.

## 15. Testing the routing configuration

You should test both the Spring configuration and the actual frame behavior.

Main cases:

1. Connection succeeds to the right WebSocket endpoint.
2. SEND /app/... invokes the right @MessageMapping.
3. The /app prefix is removed before looking up the method.
4. SUBSCRIBE /topic/... is received by the simple broker or relay.
5. Messages sent to a broker destination reach the right subscribers.
6. SEND directly to /topic/... does not accidentally invoke a controller.
7. @SubscribeMapping handles SUBSCRIBE to an application destination.
8. The @SubscribeMapping response is sent directly or through the broker according to @SendTo.
9. /user/queue/... is resolved by Principal/session.
10. convertAndSendToUser sends to the right user and corresponding sessions.
11. Custom prefixes work consistently between client and server.
12. Patterns with PathMatcher match the right destinations.
13. The broker relay connects and the broker accepts the destinations.
14. Unauthorized clients are rejected when SENDing or SUBSCRIBing.
15. The preserve publish order option is tested if business logic requires it.

You can use Spring WebSocket/STOMP test support or connect a test broker to verify frames. A unit test that only calls controller methods directly does not test the full destination classification and broker routing steps.

## 16. Pre-release checklist

- Has the WebSocket endpoint URL been separated from STOMP destinations?
- Is the application prefix explicit and consistent?
- Does @MessageMapping omit the application prefix from the annotation?
- Do broker prefixes match the destinations clients subscribe/publish to?
- Does the simple broker or the broker relay fit the storage and ACK requirements?
- Are the semantics of /queue and /topic understood accurately for the broker in use?
- Is the user destination prefix handled by UserDestinationMessageHandler?
- Is the Principal used to identify the user trustworthy?
- Are prefixes and PathMatcher consistent across client, controller, and broker?
- Is authorization configured for SEND/SUBSCRIBE?
- Does the broker relay have appropriate host, port, credentials, virtual host, and ACLs?
- Are there integration tests for important routes and rejection cases?

## 17. References

- [MessageBrokerRegistry — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/simp/config/MessageBrokerRegistry.html)
- [Enable STOMP — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html)
- [Simple Broker — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [External Broker and STOMP Relay — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [User Destinations — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Message Flow — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [@MessageMapping — Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/handler/annotation/MessageMapping.html)
- [@SubscribeMapping — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/simp/annotation/SubscribeMapping.html)
- [SimpMessagingTemplate — Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/messaging/simp/SimpMessagingTemplate.html)

configureMessageBroker defines how Spring classifies STOMP destinations. The application prefix brings messages into controllers, the broker prefix forwards messages to the simple broker or relay, while the user prefix enables sending to an authenticated user's sessions. When the endpoint, destinations, and prefix layers are properly distinguished, the SEND, SUBSCRIBE, and response flows become easy to trace, test, and maintain.