# @EnableWebSocketMessageBroker and WebSocketMessageBrokerConfigurer

## Objectives

Spring Framework supports STOMP running over WebSocket to build two-way communication applications following the publish/subscribe model. The @EnableWebSocketMessageBroker annotation enables the STOMP processing infrastructure; the WebSocketMessageBrokerConfigurer interface allows the application to register endpoints, choose a message broker, and configure channels, transport, converters, and other extension points.

After this lesson, you can:

- Explain the role of @EnableWebSocketMessageBroker and WebSocketMessageBrokerConfigurer.
- Register STOMP endpoints through StompEndpointRegistry.
- Distinguish the handshake URL from STOMP destinations.
- Configure application destination prefixes and broker destination prefixes.
- Understand the message flow through clientInboundChannel, brokerChannel, and clientOutboundChannel.
- Write @Controller classes with @MessageMapping, @SubscribeMapping, @SendTo, and @SendToUser.
- Choose between the simple broker and an external STOMP broker relay.
- Send messages from a service with SimpMessagingTemplate.
- Configure user destinations, heartbeats, SockJS, authentication, authorization, and ChannelInterceptor.
- Tune message converters, channel executors, processing order, and transport limits.
- Run a chat broadcast example using Java 17+, Spring Boot 4.1.2, and STOMP.js.

## 1. What is STOMP and why use it over WebSocket?

WebSocket creates a two-way connection between client and server. WebSocket itself only defines how to send text frames, binary frames, and connection control; it does not prescribe the application content inside frames.

STOMP (Simple Text Oriented Messaging Protocol) is a messaging sub-protocol that can run over WebSocket. STOMP defines commands, headers, bodies, and destinations so clients can send, subscribe to receive, and exchange messages under a shared protocol.

A STOMP frame has the general structure:

~~~text
COMMAND
header-name:header-value
another-header:value

message body
^@
~~~

The ^@ symbol at the end represents the null byte that terminates a STOMP frame. Common command examples:

| Command | Direction | Meaning |
|---|---|---|
| CONNECT or STOMP | Client → Server | Open a STOMP session. |
| CONNECTED | Server → Client | Confirm that the STOMP session has been opened. |
| SEND | Client → Server | Send a message to a destination. |
| SUBSCRIBE | Client → Server | Register to receive messages from a destination. |
| MESSAGE | Server → Client | Send a message to a subscriber. |
| UNSUBSCRIBE | Client → Server | Cancel a subscription. |
| DISCONNECT | Client → Server | Gracefully close the STOMP session. |
| RECEIPT | Server → Client | Acknowledge a frame when the broker supports receipts. |
| ERROR | Server → Client | Report a STOMP protocol or processing error. |

STOMP gives the application clear conventions for routing and subscriptions. Clients can use existing STOMP libraries instead of designing a custom JSON protocol on top of raw WebSocket.

### WebSocket endpoint and STOMP destination are two different concepts

A STOMP application typically has an endpoint URL and multiple destinations:

| Value | Type | Purpose |
|---|---|---|
| /ws | WebSocket endpoint URL | Clients open connections and perform the HTTP Upgrade handshake here. |
| /app/chat | Application destination | SENDs here are routed to @MessageMapping methods. |
| /topic/chat | Broker destination | Clients SUBSCRIBE to receive broadcast messages. |
| /queue/notifications | Broker destination | A queue-style destination convention, depending on the broker. |
| /user/queue/alerts | User destination | Spring converts it into a separate destination per user/session. |

The client connects to ws://localhost:8080/ws. After the WebSocket opens, the client sends STOMP frames to /app/chat or subscribes to /topic/chat. Those destinations live in the destination header of STOMP frames; they are not separate handshake URLs.

## 2. What does @EnableWebSocketMessageBroker do?

The @EnableWebSocketMessageBroker annotation enables the STOMP messaging infrastructure over WebSocket for a Spring MVC application.

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {
}
~~~

When this annotation is used, Spring registers the components needed to:

- Map HTTP/WebSocket endpoints.
- Negotiate and handle the STOMP sub-protocol.
- Convert STOMP frames into Spring Messages.
- Route messages to controllers or the message broker.
- Send messages from the broker back to WebSocket sessions.
- Manage subscriptions, user destinations, and lifecycle events.
- Provide channels for extending message processing.

STOMP support belongs to two main modules of the Spring Framework:

- spring-messaging: Message, MessageChannel, MessageHandler abstractions, and messaging annotations.
- spring-websocket: WebSocket transport, STOMP sub-protocol handling, and endpoint integration.

In Spring Boot 4.1.2, you can add spring-boot-starter-websocket to use WebSocket/STOMP in an MVC application.

### Do not confuse with @EnableWebSocket

| Annotation | Infrastructure | How it handles messages |
|---|---|---|
| @EnableWebSocket | Raw WebSocket | WebSocketConfigurer, WebSocketHandlerRegistry, and WebSocketHandler. |
| @EnableWebSocketMessageBroker | STOMP over WebSocket | WebSocketMessageBrokerConfigurer, StompEndpointRegistry, message channels, broker, and @MessageMapping. |

Use @EnableWebSocket when the application wants to define its own protocol and handle frames directly. Use @EnableWebSocketMessageBroker when you want STOMP commands, destinations, subscriptions, and message routing.

Do not enable both annotations at the same time for the same endpoint without a dedicated integration design.

## 3. WebSocketMessageBrokerConfigurer

WebSocketMessageBrokerConfigurer is the interface for customizing the configuration created by @EnableWebSocketMessageBroker.

~~~java
public interface WebSocketMessageBrokerConfigurer {
    void registerStompEndpoints(StompEndpointRegistry registry);

    void configureMessageBroker(MessageBrokerRegistry registry);

    // Other extension callbacks have default implementations.
}
~~~

The two most important callbacks:

- registerStompEndpoints: registers endpoint URLs for clients to connect to.
- configureMessageBroker: chooses the broker and destination routing rules.

Commonly used extension callbacks:

| Callback | Purpose |
|---|---|
| configureClientInboundChannel | Configures the channel receiving messages from clients; usually used to register a ChannelInterceptor or executor. |
| configureClientOutboundChannel | Configures the channel sending messages to clients. |
| configureBrokerChannel | Configures the channel sending messages from server-side code to the broker. |
| configureWebSocketTransport | Configures message size, send timeout, send buffer, and wait time for the first frame. |
| configureMessageConverters | Adds or customizes MessageConverters for payloads. |
| addArgumentResolvers | Adds argument resolvers for annotation-mapped methods. |
| addReturnValueHandlers | Adds handlers for custom return value types. |

You can override only the callbacks you need. Spring's default configuration still applies to the rest.

## 4. Registering STOMP endpoints with StompEndpointRegistry

Endpoints are registered in registerStompEndpoints:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws");
}
~~~

/ws is the URL clients use to start the WebSocket handshake. After the handshake succeeds, STOMP CONNECT is sent over the same connection.

Multiple endpoints can be registered:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws/chat");
    registry.addEndpoint("/ws/notifications");
}
~~~

Each endpoint can have its own origin policy, interceptor, handshake handler, or SockJS setting.

### Allowed origins

Example allowing only a frontend at one origin:

~~~java
registry.addEndpoint("/ws")
        .setAllowedOrigins("https://app.example.com");
~~~

Multiple origins can be allowed:

~~~java
registry.addEndpoint("/ws")
        .setAllowedOrigins(
                "https://app.example.com",
                "https://admin.example.com"
        );
~~~

Or use origin patterns when needed:

~~~java
registry.addEndpoint("/ws")
        .setAllowedOriginPatterns("https://*.example.com");
~~~

An origin consists of scheme, host, and port if present. Allow only the origins that truly need to connect. Origin validation protects browser clients against certain cross-site WebSocket hijacking scenarios; it does not replace authentication or authorization because non-browser clients can send an Origin header themselves.

### Handshake interceptor

Endpoint registration supports handshake interceptors:

~~~java
registry.addEndpoint("/ws")
        .addInterceptors(handshakeInterceptor);
~~~

The interceptor runs during the HTTP handshake, before STOMP CONNECT is processed. You can use it to inspect the request, pass attributes from the HTTP session, or record connection metadata.

If you need to inspect individual STOMP frames such as CONNECT, SEND, or SUBSCRIBE, use a ChannelInterceptor on the inbound channel. A handshake interceptor and a ChannelInterceptor handle two different stages.

### SockJS fallback

SockJS can be enabled:

~~~java
registry.addEndpoint("/ws")
        .withSockJS();
~~~

When SockJS is enabled, the client must use a SockJS client combined with a STOMP client. The endpoint will support fallback transports such as HTTP streaming or long polling when native WebSocket is unavailable.

If using a native WebSocket client, do not configure the server endpoint with SockJS and then connect to it as if it were a plain WebSocket endpoint.

## 5. configureMessageBroker and destination prefixes

configureMessageBroker decides which messages go into application controllers and which messages are forwarded directly to the broker.

Common example:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
}
~~~

This configuration creates two groups of destinations:

- /app: messages clients send here are routed to @MessageMapping methods.
- /topic and /queue: messages are passed to the simple broker to manage subscriptions and broadcasting.

Example:

~~~text
Client SEND /app/chat
        |
        v
Spring looks up @MessageMapping("/chat")
        |
        v
Controller handles it
        |
        v
Controller returns result to /topic/chat
        |
        v
Broker finds subscribers
        |
        v
Client receives MESSAGE /topic/chat
~~~

### Application destination prefix

~~~java
registry.setApplicationDestinationPrefixes("/app");
~~~

The /app prefix helps Spring distinguish messages sent into application code. When a client sends to destination /app/chat, Spring removes the /app prefix before looking up the /chat mapping.

Controller:

~~~java
@Controller
public class ChatController {

    @MessageMapping("/chat")
    public void handle(ChatMessage message) {
        // Handle message here.
    }
}
~~~

The client must SEND to /app/chat to invoke the method above.

Multiple prefixes can be set:

~~~java
registry.setApplicationDestinationPrefixes("/app", "/service");
~~~

Use multiple prefixes when the application wants to partition namespaces for groups of controllers.

### Broker destination prefix

~~~java
registry.enableSimpleBroker("/topic", "/queue");
~~~

Messages with destinations starting with these prefixes are passed to the broker. Clients usually SUBSCRIBE to /topic/chat to receive broadcasts.

With the built-in simple broker, /topic and /queue are only naming conventions. The simple broker does not enforce queue/topic semantics like a full message broker. When using an external broker, destination semantics depend on the broker and its configuration.

### User destination prefix

Spring uses /user by default for user-specific destinations:

~~~text
/user/queue/alerts
~~~

It can be customized:

~~~java
registry.setUserDestinationPrefix("/user");
~~~

Keep the default prefix unless there is a reason to change it. User destinations are converted by Spring into concrete destinations per user or session.

## 6. Simple broker and external broker relay

Spring has two main broker options.

### Simple broker

~~~java
registry.enableSimpleBroker("/topic", "/queue");
~~~

The simple broker is built into Spring and stores subscriptions in memory. It broadcasts messages to connected clients subscribed to matching destinations.

Advantages:

- No need to install a separate broker.
- Easy to run locally, in demos, and in small applications.
- Suitable for learning STOMP flows and testing basic functionality.
- Supports path-style and pattern destinations.

Limitations:

- Subscriptions and broker state live in the application instance's memory.
- Not suitable for multi-instance clustering.
- Supports only a subset of STOMP commands.
- Does not support ACK, RECEIPT, and some advanced STOMP capabilities.
- Does not provide durable messaging like a dedicated broker.
- Should not be used as business queue infrastructure requiring persistence and redelivery.

The simple broker is suitable when messages only need to be broadcast to online clients and may be lost if the server restarts or a client disconnects.

### External STOMP broker relay

When a full broker is needed, the application can relay messages to RabbitMQ, ActiveMQ, or a STOMP-capable broker.

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue");
}
~~~

The broker relay is a Spring MessageHandler. It opens TCP connections to the broker, forwards messages from Spring to the broker, and forwards messages from the broker back to WebSocket clients.

Benefits:

- The broker manages subscriptions and broadcasting.
- Can use ACK, RECEIPT, and other STOMP commands supported by the broker.
- Supports clustering and scaling through the broker.
- Can leverage the broker's persistence, security, routing, and monitoring.
- Multiple application instances can connect to the same broker to distribute messages across instances.

The broker relay needs appropriate host, port, client/system login, and passcode configuration. The broker must have its STOMP protocol endpoint enabled. Spring Framework requires suitable TCP dependencies, typically including Reactor Netty and Netty, when using the relay.

### Comparison

| Criterion | Simple broker | Broker relay |
|---|---|---|
| Install external broker | No | Yes |
| Subscriptions | Stored in Spring's memory | Managed by external broker |
| ACK/RECEIPT | Not fully supported | Depends on broker capabilities |
| Durable messaging | No | Possible, depending on broker |
| Clustering | Not suitable | Supported via broker |
| Operations | Simple | Requires managing broker and credentials |
| Use case | Demos, simple realtime broadcast | Production, multiple instances, broker features |

Do not switch to a broker relay merely by changing prefixes. You must install the broker, enable the STOMP listener, and configure connections, credentials, destination policies, and network access.

## 7. Message flow inside Spring

Spring uses MessageChannels to separate receiving, processing, and sending messages.

Three important channels:

| Channel | Direction | Role |
|---|---|---|
| clientInboundChannel | Client → Spring | Receives messages after STOMP frames are decoded. |
| brokerChannel | Application → Broker | Sends messages from controllers or services to the broker. |
| clientOutboundChannel | Broker/Spring → Client | Sends messages encoded into STOMP frames back to WebSocket sessions. |

Flow with the simple broker:

~~~mermaid
flowchart TD
    A["Browser STOMP client"] --> B["WebSocket session"]
    B --> C["STOMP frame decoder"]
    C --> D["clientInboundChannel"]
    D --> E{"Destination prefix"}
    E -->|/app| F["@MessageMapping controller"]
    E -->|/topic or /queue| G["Simple broker"]
    F --> H["brokerChannel"]
    H --> G
    G --> I["clientOutboundChannel"]
    I --> J["STOMP encoder"]
    J --> K["Subscribed WebSocket clients"]
~~~

Details:

1. The client connects to the /ws endpoint and sends STOMP CONNECT.
2. Spring confirms the STOMP session and attaches the Principal if the HTTP request was authenticated.
3. The client sends SEND or SUBSCRIBE.
4. The STOMP frame is decoded into a Spring Message.
5. The message enters clientInboundChannel.
6. A /app destination is routed to a @MessageMapping method.
7. A /topic or /queue destination is passed to the broker.
8. The controller can return an object; Spring uses a MessageConverter to serialize the object into a payload.
9. The message is sent through brokerChannel.
10. The broker finds matching subscriptions.
11. The message passes through clientOutboundChannel and is encoded into a STOMP MESSAGE frame.
12. The client receives the body and processes it according to the agreed schema.

If using a broker relay, the broker step forwards messages over TCP to the external broker and receives broadcast messages back.

## 8. @MessageMapping and annotated controllers

A @Controller class can declare methods that handle STOMP messages.

~~~java
@Controller
public class GreetingController {

    @MessageMapping("/greeting")
    @SendTo("/topic/greetings")
    public GreetingResponse greeting(GreetingRequest request) {
        return new GreetingResponse("Hello, " + request.name());
    }
}
~~~

When the client SENDs to /app/greeting:

- The /app prefix is used to select the application handler.
- The /greeting part matches @MessageMapping.
- Spring converts the body into GreetingRequest.
- The method processes it and returns GreetingResponse.
- @SendTo routes the result to /topic/greetings.

### Commonly used method parameters

| Parameter/annotation | Use |
|---|---|
| @Payload | Gets the payload converted by a MessageConverter. |
| @Header | Gets a specific header. |
| @Headers | Gets all message headers as a Map. |
| @DestinationVariable | Gets a variable from the destination path. |
| Message<?> | Accesses the full message and payload. |
| MessageHeaders | Reads message headers. |
| SimpMessageHeaderAccessor | Accesses typed Spring messaging headers. |
| StompHeaderAccessor | Reads STOMP command/headers. |
| Principal | Gets the user authenticated during the HTTP handshake. |

Example using destination variables and headers:

~~~java
@MessageMapping("/rooms/{roomId}/messages")
@SendTo("/topic/rooms/{roomId}")
public ChatMessage send(
        @DestinationVariable String roomId,
        @Header("simpSessionId") String sessionId,
        @Payload ChatMessage message) {

    return new ChatMessage(
            roomId,
            message.content(),
            sessionId
    );
}
~~~

For business messages, use explicit DTOs. Do not pass database entities directly if they contain lazy relationships, internal fields, or data that should not be sent to clients.

### Validation and exception handling

Payloads can use Jakarta Validation:

~~~java
@MessageMapping("/orders")
@SendTo("/topic/order-results")
public OrderResult createOrder(@Valid @Payload CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

If a validator is configured, an invalid payload can raise an exception during binding/validation.

Use @MessageExceptionHandler to turn errors into structured responses:

~~~java
@MessageExceptionHandler
@SendToUser("/queue/errors")
public ApiError handleException(IllegalArgumentException exception) {
    return new ApiError("INVALID_REQUEST", exception.getMessage());
}
~~~

Do not send stack traces or internal server details to clients. Error responses should have stable error codes and user-appropriate messages.

## 9. @SubscribeMapping

@SubscribeMapping handles a SUBSCRIBE frame for a specific destination.

~~~java
@Controller
public class InitialDataController {

    @SubscribeMapping("/dashboard")
    public DashboardSnapshot initialDashboard() {
        return dashboardService.snapshot();
    }
}
~~~

If the client SUBSCRIBEs to /app/dashboard, the method can return a snapshot directly to the client via clientOutboundChannel without going through the broker to store a subscription or broadcast.

Use cases:

- Sending initial state when a client opens a screen.
- Returning one-time initialization data.
- Responding to a subscription request without creating a broadcast destination.

If you want the result to go through the broker, combine it with @SendTo or @SendToUser. Do not map the same prefix to both a controller and the broker unintentionally because both may process the message in parallel.

## 10. @SendTo and @SendToUser

### @SendTo

@SendTo specifies the destination to which the method's result is sent:

~~~java
@MessageMapping("/chat")
@SendTo("/topic/chat")
public ChatMessage chat(ChatMessage message) {
    return message;
}
~~~

You can send to multiple destinations:

~~~java
@SendTo({"/topic/chat", "/topic/audit"})
~~~

If @SendTo is not specified, Spring uses the default destination according to the message handler's mapping rules.

### @SendToUser

@SendToUser sends the response to the user associated with the current message:

~~~java
@MessageMapping("/private-message")
@SendToUser("/queue/replies")
public PrivateReply reply(PrivateRequest request) {
    return new PrivateReply("Received");
}
~~~

Client subscribes to:

~~~text
/user/queue/replies
~~~

Spring converts the /user destination into a destination specific to the session/user. If the user has multiple sessions, all matching sessions can receive by default. Set broadcast=false when you only want to reply to the session that sent the request.

### Sending from a service with SimpMessagingTemplate

Messages are not always sent from @MessageMapping. A service or scheduled job can inject SimpMessagingTemplate:

~~~java
@Service
public class NotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void broadcast(String text) {
        messagingTemplate.convertAndSend(
                "/topic/notifications",
                new Notification(text)
        );
    }

    public void notifyUser(String username, Notification notification) {
        messagingTemplate.convertAndSendToUser(
                username,
                "/queue/notifications",
                notification
        );
    }
}
~~~

This approach is useful when an HTTP request, scheduled task, or business service needs to push events to WebSocket subscribers.

## 11. MessageConverter and payload formats

The STOMP frame body is bytes/text data. Spring uses MessageConverter to convert the body into an object for the controller and convert return objects into outbound payloads.

Common payload formats:

- String: simple text.
- JSON: DTOs/records for browser applications.
- Byte array: binary payloads or already-encoded data.
- Custom format: custom converter per schema.

With JSON, the client sends:

~~~json
{
  "content": "hello"
}
~~~

The controller receives the DTO:

~~~java
public record ChatMessage(String content) {
}
~~~

Spring converts JSON into ChatMessage and serializes the response object to JSON when sending out to the broker.

### Customizing converters

WebSocketMessageBrokerConfigurer has the configureMessageConverters callback to add converters. When providing converters yourself, understand that the boolean return value controls whether Spring continues registering default converters.

Skeleton example:

~~~java
@Override
public boolean configureMessageConverters(
        List<MessageConverter> messageConverters) {

    messageConverters.add(customMessageConverter);

    // true allows Spring to register the remaining default converters.
    return true;
}
~~~

Only replace converters when there is a clear schema or serialization requirement. If you omit default converters without replacing them, controllers may fail to convert String/JSON payloads as expected.

Client and server must agree on content-type, JSON fields, encoding, null handling, and schema versioning.

## 12. Authentication and authorization

A STOMP session starts with an HTTP handshake or HTTP transport requests if using SockJS. In a typical web application, Spring Security authenticates the HTTP request and Spring automatically associates the request's Principal with the WebSocket/SockJS session.

Then, Principal can be accessed inside @MessageMapping:

~~~java
@MessageMapping("/profile")
@SendToUser("/queue/profile")
public ProfileResponse profile(Principal principal) {
    return profileService.load(principal.getName());
}
~~~

### STOMP login/passcode is not the default authentication for WebSocket

The STOMP protocol has login and passcode headers in the CONNECT frame, but with STOMP over WebSocket, Spring ignores these headers by default and relies on the user authenticated at the HTTP transport.

Therefore, if using cookie-based sessions:

1. The user logs in via HTTP/Spring Security.
2. The browser sends the cookie in the same-origin WebSocket handshake.
3. Spring takes the Principal from the HTTP request.
4. The Principal is attached to the WebSocket/STOMP session.
5. Messages from the session carry the corresponding user header.

If using JWT or token authentication, you can use a ChannelInterceptor to read the token from a STOMP CONNECT native header, validate the token, and attach the Authentication to the message accessor. Do not log tokens or store long-lived tokens in session metadata.

### Authorization by destination and command

Authentication only determines who is connecting. Authorization decides which destinations a user may SEND to or SUBSCRIBE to.

Example policy:

- Only logged-in users may CONNECT.
- Only the ADMIN role may SUBSCRIBE to /topic/admin.
- Clients may SEND only to /app/**.
- Clients may not SEND directly to /topic/** if the server must control the content.
- Users may receive only their own /user/queue/**.

Spring Security provides WebSocket message authorization through ChannelInterceptor and an authorization manager. Security configuration for STOMP messages must check both message type and destination. In particular, SUBSCRIBE is also an action that requires authorization; protecting only SEND is not enough.

### ChannelInterceptor

You can register an interceptor for the inbound channel:

~~~java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.interceptors(new StompSecurityChannelInterceptor());
}
~~~

In preSend, use StompHeaderAccessor to read the command, destination, and native headers:

~~~java
public class StompSecurityChannelInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        StompHeaderAccessor accessor = StompHeaderAccessor.wrap(message);

        StompCommand command = accessor.getCommand();
        String destination = accessor.getDestination();

        // Check policy by command, user, and destination.
        return message;
    }
}
~~~

An interceptor can inspect, add headers, or reject messages by returning null/throwing an exception per policy. With token authentication, ensure the interceptor runs in the proper order relative to Spring Security's interceptor.

## 13. Channels and executors

Spring uses asynchronous channels to decouple processing stages. clientInboundChannel and clientOutboundChannel are usually backed by thread pools.

You can configure the inbound channel:

~~~java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.taskExecutor()
            .corePoolSize(4)
            .maxPoolSize(16)
            .queueCapacity(1000);
}
~~~

The values above are only examples. Choose thread pool sizes according to workload type:

- CPU-bound: thread count close to the number of processors.
- I/O-bound: may need more threads if handlers wait on databases or external services.
- Blocking handlers: control queue capacity so messages do not accumulate unboundedly.
- Message bursts: monitor queue latency and rejections.

Do not increase max pool size while ignoring queue capacity. With ThreadPoolExecutor, a very large default queue can cause the executor never to scale beyond core pool size as expected.

### Message ordering

Inbound/outbound channels run asynchronously and use multiple threads. Processing order can differ from the order frames were received or messages were published.

If the application needs to preserve inbound order per session:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.setPreserveReceiveOrder(true);
    registry.addEndpoint("/ws");
}
~~~

If you need to preserve outbound order per session:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setPreservePublishOrder(true);
    registry.enableSimpleBroker("/topic", "/queue");
}
~~~

These two settings have a performance cost. Enable them only when business logic depends on ordering.

## 14. Heartbeat and long-lived connections

WebSocket/STOMP connections usually live for a long time. Heartbeats help detect dead connections, NAT/proxy timeouts, and inactive clients.

The simple broker supports STOMP heartbeats when configured with a TaskScheduler:

~~~java
registry.enableSimpleBroker("/topic", "/queue")
        .setHeartbeatValue(new long[] {10_000, 20_000})
        .setTaskScheduler(messageBrokerTaskScheduler);
~~~

The two numbers represent heartbeat intervals in milliseconds for the send/receive directions per STOMP negotiation. You need to configure a suitable TaskScheduler so the broker emits heartbeats and checks timeouts.

When using an external broker relay, heartbeats and connection policies also depend on the broker. Check both heartbeats between the browser and Spring and between Spring and the broker.

The STOMP.js client can configure:

~~~javascript
const client = new Client({
    brokerURL: "ws://localhost:8080/ws",
    heartbeatIncoming: 10000,
    heartbeatOutgoing: 10000,
    reconnectDelay: 5000
});
~~~

Heartbeats help detect abnormal connections; reconnect logic still needs to be implemented on the client. After reconnecting, the client must re-subscribe to needed destinations and resynchronize state if messages were missed.

## 15. WebSocket transport and message limits

A STOMP message can be larger than a single WebSocket frame. Spring can buffer and reassemble message parts according to transport configuration.

Configuration:

~~~java
@Override
public void configureWebSocketTransport(WebSocketTransportRegistration registration) {
    registration
            .setMessageSizeLimit(64 * 1024)
            .setSendTimeLimit(15_000)
            .setSendBufferSizeLimit(512 * 1024)
            .setTimeToFirstMessage(30_000);
}
~~~

Meaning:

| Setting | Meaning |
|---|---|
| setMessageSizeLimit | Limits the size of a STOMP message after receiving/reassembly. |
| setSendTimeLimit | Limits the time spent sending a message to a client. |
| setSendBufferSizeLimit | Limits outbound data waiting to be sent to a client. |
| setTimeToFirstMessage | Wait time for the first message after a WebSocket session is established. |

Slow clients can cause outbound buffers to grow. When the send timeout or buffer limit is exceeded, Spring may close the session per transport policy.

Do not set overly large limits just to avoid payload errors. Realtime payloads should be small, structured, and avoid sending unnecessary heavy data. For large files or binaries, consider HTTP/object storage instead of STOMP broadcasting.

## 16. SockJS and fallback transports

SockJS provides fallback transports when native WebSocket does not work or is blocked by a proxy.

Server:

~~~java
registry.addEndpoint("/ws")
        .setAllowedOrigins("https://app.example.com")
        .withSockJS();
~~~

The client must use a SockJS client as the WebSocket factory for STOMP.js:

~~~javascript
const client = new Client({
    webSocketFactory: () => new SockJS("/ws"),
    reconnectDelay: 5000
});
~~~

SockJS can pick WebSocket, streaming, or long polling. Fallback transports generate multiple HTTP requests under the same endpoint path; security, cookies, CORS, and proxy configuration must match.

If all modern clients support WebSocket and the proxy is properly configured, native WebSocket is simpler. Enable SockJS when there is a real fallback requirement.

## 17. User destinations

Spring supports destinations starting with /user to send messages to a specific user or session.

Client subscribes:

~~~text
/user/queue/notifications
~~~

Server sends:

~~~java
messagingTemplate.convertAndSendToUser(
        username,
        "/queue/notifications",
        notification
);
~~~

Spring uses UserDestinationMessageHandler to convert the logical destination into a unique internal destination per user/session. Multiple users can subscribe to the same logical destination name without receiving each other's messages.

Use @SendToUser in controllers:

~~~java
@MessageMapping("/trade")
@SendToUser("/queue/trade-result")
public TradeResult trade(TradeRequest request, Principal principal) {
    return tradeService.execute(principal.getName(), request);
}
~~~

If a user has multiple sessions, all matching sessions can receive by default. Use broadcast=false when you only want to send back to the session that sent the message.

With an external broker, check the cleanup policy for per-user-session queues/destinations. Across multiple instances, you may need to configure broadcasting for unresolved user destinations so other instances have a chance to find the corresponding session.

## 18. Lifecycle events and cleanup

Spring publishes application events when a STOMP session is created, connected, subscribed, unsubscribed, or disconnected.

Common events:

| Event | Meaning |
|---|---|
| SessionConnectEvent | The client sends STOMP CONNECT. |
| SessionConnectedEvent | STOMP CONNECT has been acknowledged. |
| SessionSubscribeEvent | The client sends SUBSCRIBE. |
| SessionUnsubscribeEvent | The client sends UNSUBSCRIBE. |
| SessionDisconnectEvent | The STOMP/WebSocket session ends. |

You can listen for them:

~~~java
@Component
public class StompSessionEvents {

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        String sessionId = event.getSessionId();
        // Clean up state tied to the session.
    }
}
~~~

SessionDisconnectEvent can be published multiple times in some situations, for example when the client sends DISCONNECT and the transport closes simultaneously. Cleanup must be idempotent: removing subscriptions, presence, or session state multiple times remains safe.

If you need to inspect individual messages, use a ChannelInterceptor. Events only provide lifecycle notifications; they do not replace interceptors.

## 19. STOMP client with STOMP.js

A browser client commonly uses the @stomp/stompjs package.

Install the package:

~~~bash
npm install @stomp/stompjs
~~~

Example:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "ws://localhost:8080/ws",
    reconnectDelay: 5000,
    onConnect: () => {
        client.subscribe("/topic/chat", frame => {
            console.log(frame.body);
        });

        client.publish({
            destination: "/app/chat",
            body: JSON.stringify({ content: "hello" })
        });
    },
    onStompError: frame => {
        console.error("STOMP error:", frame.headers["message"]);
        console.error(frame.body);
    },
    onWebSocketError: event => {
        console.error("WebSocket error:", event);
    }
});

client.activate();
~~~

Steps:

1. The client opens a WebSocket to /ws.
2. STOMP.js sends a CONNECT frame.
3. Spring returns CONNECTED.
4. onConnect runs once the STOMP session is ready.
5. The client subscribes to /topic/chat.
6. The client publishes JSON to /app/chat.
7. Spring routes to @MessageMapping("/chat").
8. The controller returns a response and @SendTo sends it to /topic/chat.
9. The client receives a MESSAGE frame and reads the JSON body.

In real applications, publish only after the required subscriptions have been established. If you need confirmation that the broker has processed a subscription, use STOMP RECEIPT with an external broker that supports receipts; the built-in simple broker does not support receipts.

When the component or application closes, call client.deactivate() to close the STOMP/WebSocket session and release timers/reconnect tasks.

## 20. Runnable Java 17+ example: chat broadcast with Spring Boot 4.1.2

The example uses Spring's built-in simple broker. Clients connect to /ws, subscribe to /topic/chat, and send messages to /app/chat. The controller returns the message to the topic; all subscribed clients receive the broadcast.

### Project structure

~~~text
spring-stomp-chat-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          StompChatApplication.java
          WebSocketConfiguration.java
          ChatMessage.java
          ChatController.java
      resources/
        application.properties
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>spring-stomp-chat-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-websocket</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### application.properties

~~~properties
server.port=8080
~~~

### StompChatApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StompChatApplication {

    public static void main(String[] args) {
        SpringApplication.run(StompChatApplication.class, args);
    }
}
~~~

### WebSocketConfiguration.java

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketTransportRegistration;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.setPreserveReceiveOrder(true);

        registry.addEndpoint("/ws")
                .setAllowedOrigins("http://localhost:8080");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/topic", "/queue");
    }

    @Override
    public void configureWebSocketTransport(WebSocketTransportRegistration registration) {
        registration
                .setMessageSizeLimit(64 * 1024)
                .setSendTimeLimit(15_000)
                .setSendBufferSizeLimit(512 * 1024);
    }
}
~~~

setPreserveReceiveOrder(true) ensures inbound messages from the same session are processed in the order received. In the example, this preserves the SUBSCRIBE-then-SEND order when a client performs two operations consecutively.

### ChatMessage.java

~~~java
package demo;

public record ChatMessage(String content) {
}
~~~

### ChatController.java

~~~java
package demo;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;
import org.springframework.messaging.handler.annotation.SendTo;

@Controller
public class ChatController {

    @MessageMapping("/chat")
    @SendTo("/topic/chat")
    public ChatMessage chat(@Payload ChatMessage message) {
        System.out.println("handled=" + message.content());
        return new ChatMessage("server: " + message.content());
    }
}
~~~

### Running the server

Requires Java 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

Server listens at:

~~~text
http://localhost:8080
~~~

### STOMP.js client

Create a JavaScript frontend with @stomp/stompjs installed:

~~~bash
npm install @stomp/stompjs
~~~

In the client module:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "ws://localhost:8080/ws",
    reconnectDelay: 5000,
    onConnect: () => {
        client.subscribe("/topic/chat", frame => {
            console.log(frame.body);
        });

        client.publish({
            destination: "/app/chat",
            body: JSON.stringify({ content: "hello" })
        });
    }
});

client.activate();
~~~

Output on server console:

~~~text
handled=hello
~~~

Output on browser console:

~~~text
{"content":"server: hello"}
~~~

### Execution flow explanation

1. Spring Boot initializes the MVC application and WebSocket support.
2. @EnableWebSocketMessageBroker enables the STOMP infrastructure.
3. registerStompEndpoints registers the /ws URL.
4. configureMessageBroker sets /app for controllers and /topic, /queue for the simple broker.
5. The browser opens a WebSocket to /ws and sends STOMP CONNECT.
6. The client SUBSCRIBEs to /topic/chat.
7. The client SENDs JSON to /app/chat.
8. Spring routes the /chat part to ChatController.chat.
9. MessageConverter converts the JSON body into ChatMessage.
10. The controller prints handled=hello and returns a new ChatMessage.
11. @SendTo sends the response to /topic/chat.
12. The simple broker finds subscribers and sends a STOMP MESSAGE frame to the browser.
13. The browser prints the JSON body in the console.

The example uses the simple broker, so it only broadcasts to currently connected and subscribed clients. When the application needs durable subscriptions, ACK/RECEIPT, clustering, or message broker persistence, switch to an external broker relay.

## 21. Testing STOMP endpoints

You can test with WebSocketStompClient and StompSessionHandler in Java tests.

Scenarios to verify:

- WebSocket handshake to the right endpoint.
- STOMP CONNECT is acknowledged.
- SUBSCRIBE registers the right destination.
- SEND to /app routes to the right controller.
- Controller returns a message with the right schema and destination.
- Another client subscribed to the same topic also receives the broadcast.
- Messages sent to /user reach only the right user/session.
- Invalid payloads produce structured errors.
- Unauthorized users cannot SEND or SUBSCRIBE to forbidden destinations.
- Client disconnect releases state.
- Reconnect performs resubscription.
- Heartbeat detects dead connections.
- Oversized payloads are rejected per transport limits.
- Broker relay reconnects after a broker restart if using an external broker.

With the simple broker, do not test ACK/RECEIPT as if the broker has full support. Use a real broker when testing features that depend on STOMP broker commands.

## 22. Common mistakes

| Symptom | Cause | How to handle |
|---|---|---|
| HTTP 404 when connecting | Endpoint not registered or client has wrong URL | Check registerStompEndpoints and context path |
| WebSocket opens but STOMP CONNECT fails | Client/server disagree on STOMP sub-protocol or frame | Use a compatible STOMP client and check logs |
| SEND /app does not reach controller | Wrong application prefix or @MessageMapping | Compare /app destination + mapping |
| SUBSCRIBE receives no messages | Subscribed to wrong endpoint URL or destination prefix | Subscribe to /topic or /queue per configuration |
| Controller runs but client receives nothing | Wrong @SendTo destination or client has not subscribed | Check broker prefix and subscribers |
| Client receives unparseable JSON | Mismatched converter/content-type/schema | Check MessageConverter and payload |
| Simple broker does not send RECEIPT | Simple broker does not support receipts | Use an external broker relay if receipts are needed |
| Simple broker loses subscriptions on restart | Subscriptions stored in memory | Use a dedicated broker if durability is needed |
| Multiple instances do not cross-broadcast | Simple broker only manages subscriptions per instance | Use an external broker relay |
| Client can subscribe to sensitive destinations | Missing SUBSCRIBE authorization | Configure Spring Security message authorization |
| Token in STOMP CONNECT has no effect | Spring ignores login/passcode by default for WebSocket transport | Authenticate HTTP or write a CONNECT ChannelInterceptor |
| Client disconnects but presence remains | Non-idempotent cleanup or missed event | Listen to SessionDisconnectEvent and clean up safely |
| Messages arrive out of order | Inbound/outbound channels process asynchronously | Consider setPreserveReceiveOrder and setPreservePublishOrder |
| Slow client causes buffer growth | Outbound client cannot consume messages fast enough | Limit send time, buffer size, and payload |
| Heartbeat does not work | Missing TaskScheduler or wrong interval configuration | Configure scheduler and check both directions |
| SockJS client fails | Server/client do not both enable SockJS | Align withSockJS and SockJS client |
| Broker relay does not connect | Broker has not enabled STOMP TCP listener or wrong credentials/port | Check broker STOMP endpoint and network |

## 23. Deployment checklist

- [ ] Enable @EnableWebSocketMessageBroker on the configuration class.
- [ ] Implement WebSocketMessageBrokerConfigurer.
- [ ] Register endpoint URLs with StompEndpointRegistry.
- [ ] Configure explicit allowed origins.
- [ ] Choose SockJS only when clients need fallback.
- [ ] Set an application destination prefix such as /app.
- [ ] Set broker prefixes such as /topic and /queue.
- [ ] Choose the simple broker or an external broker relay based on durability, ACK, receipts, and clustering requirements.
- [ ] Write @MessageMapping controllers with clear DTOs.
- [ ] Use @SendTo, @SendToUser, or SimpMessagingTemplate for outbound messages.
- [ ] Verify JSON MessageConverter and payload schemas.
- [ ] Authenticate the HTTP handshake or CONNECT token per policy.
- [ ] Authorize both SEND and SUBSCRIBE.
- [ ] Use ChannelInterceptor for per-STOMP-frame checks.
- [ ] Configure heartbeats and reconnect on the client.
- [ ] Configure message size, send time, and send buffer limits.
- [ ] Enable preserve order only if business logic needs it.
- [ ] Clean up session/presence on disconnect and handle duplicate events.
- [ ] Test multiple clients, slow clients, reconnects, broker restarts, and invalid payloads.
- [ ] Monitor sessions, subscriptions, inbound/outbound queues, send buffers, errors, and heartbeat timeouts.

## Key takeaways

- @EnableWebSocketMessageBroker enables STOMP over WebSocket infrastructure.
- WebSocketMessageBrokerConfigurer is the extension point for registering endpoints and configuring the broker/channels/transport.
- StompEndpointRegistry registers the handshake URL; STOMP destinations are in frame headers after the connection opens.
- /app typically routes to @MessageMapping; /topic and /queue route to the broker.
- Simple broker stores subscriptions in memory and fits demos and basic broadcasts; it does not fully support ACK/RECEIPT and does not fit clustering.
- Broker relay forwards STOMP messages over TCP to an external broker.
- @MessageMapping handles SEND; @SubscribeMapping handles subscription requests; @SendTo and @SendToUser route results.
- SimpMessagingTemplate lets services send messages to topics or user destinations.
- Authentication usually comes from the HTTP Principal; Spring ignores login/passcode in STOMP CONNECT over WebSocket by default.
- ChannelInterceptor inspects or enriches individual STOMP messages.
- Heartbeats, reconnects, message limits, send buffers, and authorization are essential in operations.
- Simple broker and external broker have different capabilities; tests must use the same broker type as production.

## Official documentation

- [Spring Framework 7.0.10 Reference: STOMP](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp.html)
- [Spring Framework 7.0.10 Reference: Enable STOMP](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/enable.html)
- [Spring Framework 7.0.10 Reference: Flow of Messages](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/message-flow.html)
- [Spring Framework 7.0.10 Reference: Annotated Controllers](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/handle-annotations.html)
- [Spring Framework 7.0.10 Reference: Simple Broker](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework 7.0.10 Reference: External Broker Relay](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework 7.0.10 Reference: WebSocket Transport](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/server-config.html)
- [Spring Framework 7.0.10 Reference: Authentication](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/authentication.html)
- [Spring Framework 7.0.10 Reference: Authorization](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/authorization.html)
- [Spring Framework 7.0.10 Reference: User Destinations](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/user-destination.html)
- [Spring Framework 7.0.10 Reference: Interception](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/interceptors.html)
- [Spring Framework 7.0.10 Reference: Performance and Ordering](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/configuration-performance.html)
- [Spring Boot 4.1.2 Reference: WebSockets](https://docs.spring.io/spring-boot/4.1/reference/messaging/websockets.html)
- [Spring Getting Started Guide: STOMP over WebSocket](https://spring.io/guides/gs/messaging-stomp-websocket)
- [STOMP Protocol 1.2 Specification](https://stomp.github.io/stomp-specification-1.2.html)
