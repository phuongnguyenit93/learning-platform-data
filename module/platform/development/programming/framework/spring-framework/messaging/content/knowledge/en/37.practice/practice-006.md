# Building a Real-Time Update Application with STOMP

> Scope: building a real-time application on Spring Framework using STOMP over WebSocket, from endpoint and broker configuration to controllers, server push, browser clients, security, operations, and testing.

## 1. Objectives

After this lesson, you will be able to:

- Explain the roles of WebSocket and STOMP in bidirectional communication.
- Configure STOMP endpoints, application destinations, and broker destinations.
- Handle client messages with `@MessageMapping` and send data via `@SendTo` or `SimpMessagingTemplate`.
- Distinguish between broadcast topics, queue conventions, and user destinations.
- Connect browsers using `@stomp/stompjs`, subscribe, publish, configure heartbeats, and reconnect.
- Secure WebSocket/STOMP using HTTP authentication, CSRF, and message authorization.
- Choose between the simple broker and an external broker relay.
- Control ordering, thread pools, message sizes, slow clients, and monitoring.
- Write controller tests and end-to-end WebSocket/STOMP tests.

## 2. WebSocket and STOMP

WebSocket establishes a long-lived bidirectional connection between client and server after an HTTP handshake. WebSocket only defines how text/binary frames are transmitted; it does not define the business semantics of frame contents.

STOMP (Simple Text Oriented Messaging Protocol) is a messaging sub-protocol that can run over WebSocket. STOMP defines commands, headers, and a body so clients and servers can exchange operations such as CONNECT, SUBSCRIBE, SEND, MESSAGE, and DISCONNECT.

A STOMP frame has the general form:

```text
COMMAND
header-name:header-value

body
^@
```

The frame terminator character is NUL. Real frames may carry `content-length`, `content-type`, `destination`, `ack`, and other headers depending on the command. Do not parse STOMP manually by ad-hoc string splitting; use client/server libraries that support the protocol.

STOMP is useful when an application needs push updates, chat, dashboards, task status, or notifications to multiple clients. If only standard request/response is needed, HTTP REST may be simpler; WebSocket/STOMP is suitable when the server needs to push messages proactively without waiting for the client to poll.

## 3. Spring's Message Flow Architecture

Spring turns STOMP frames into `Message<?>` and routes them through internal channels:

```text
Browser -- WebSocket/STOMP --> clientInboundChannel
                                  |
                    /app/**      |      /topic/**, /queue/**
                       v         |             v
                @MessageMapping  |        Message Broker
                       |         |             ^
                       +---- brokerChannel ---+
                                                 |
Browser <-- WebSocket/STOMP -- clientOutboundChannel
```

- `clientInboundChannel`: receives messages from WebSocket clients.
- `brokerChannel`: transfers messages emitted by controllers/services to the broker.
- `clientOutboundChannel`: sends messages from the broker back to WebSocket sessions.
- `@MessageMapping`: handles messages whose destination matches the application prefix.
- Broker: manages subscriptions and dispatches messages to matching subscribers.

Typically, destinations starting with `/app` are routed to controllers; destinations starting with `/topic` or `/queue` are routed to the broker. These prefixes are conventions configured by the application.

## 4. Configuring STOMP Endpoints and the Broker

STOMP over WebSocket requires `spring-messaging` and `spring-websocket`. With Spring Boot, add the WebSocket starter matching the Boot version in use; Boot's dependency management manages the Spring Framework version.

Basic configuration:

```java
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
        registry.addEndpoint("/ws")
                .setAllowedOriginPatterns("https://app.example.com");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
```

`/ws` is the HTTP URL used for the WebSocket handshake, not a destination to publish to. After connecting, clients send STOMP frames over that connection.

`setApplicationDestinationPrefixes("/app")` causes messages sent to `/app/chat.send` to be routed to `@MessageMapping("/chat.send")`. `/topic` and `/queue` are handled by the broker. `/user` is used by Spring to resolve per-user/session destinations.

Allow only the actual frontend origins. Avoid `*` when the application uses cookies or credentials; origin checking is a defense layer against unknown websites opening connections to the endpoint.

### 4.1. Simple Broker

`enableSimpleBroker("/topic", "/queue")` enables a simple in-memory broker inside the application instance. It stores active subscriptions and delivers messages to matching sessions.

The simple broker is suitable for demos, development, or small single-instance applications. It supports a subset of the STOMP protocol; it does not fully support ACK, receipts, and several other features, and is not suitable for clustering. When the process restarts, in-memory subscriptions are lost and clients must reconnect and re-subscribe.

The `/topic` name usually denotes publish-subscribe, while `/queue` usually denotes point-to-point. With the simple broker, these two prefixes have no special protocol semantics; they are purely conventions. With an external broker, exact semantics depend on the broker and configuration.

### 4.2. External Broker Relay

When multiple application instances or a more full-featured broker are needed, use a STOMP broker relay:

```java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.setUserDestinationPrefix("/user");
    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("rabbitmq")
            .setRelayPort(61613);
}
```

The example above assumes the broker has a STOMP listener enabled on the corresponding host/port and credentials are configured securely per environment. Do not hard-code usernames/passwords in source code. Relay configuration can set separate client/system logins.

The broker relay opens a TCP connection to the external STOMP broker, forwards messages from Spring to the broker, and forwards messages emitted by the broker back to WebSocket sessions. Thus, one instance can broadcast messages to clients connected to another instance through the shared broker.

The relay does not automatically make all destinations durable. Persistence, queue durability, ACK modes, retention, redelivery, and dead-letter behavior depend on the broker and destination declarations. Check your broker's documentation.

## 5. Building Message Contracts

Use explicit DTOs instead of sending entities directly:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record ChatRequest(
        @NotBlank
        @Size(max = 2000)
        String content) {
}

public record ChatEvent(
        String sender,
        String content,
        java.time.Instant sentAt) {
}
```

`ChatRequest` is the data clients are allowed to send. `ChatEvent` is the data the server emits. The server obtains the sender from `Principal`, rather than trusting a self-declared sender name from the client.

Keep payloads compact, bound lengths, and validate data. For large updates, send an ID or reference so the client can fetch details via an appropriate HTTP/API endpoint instead of broadcasting oversized objects.

## 6. Receiving Messages with @MessageMapping

Controller receiving messages sent to `/app/chat.send`:

```java
import java.security.Principal;
import java.time.Instant;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.annotation.SendTo;
import org.springframework.stereotype.Controller;
import jakarta.validation.Valid;

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/public")
    public ChatEvent send(
            @Valid @Payload ChatRequest request,
            Principal principal) {
        return new ChatEvent(
                principal.getName(),
                request.content(),
                Instant.now());
    }
}
```

The client sends `SEND` to `/app/chat.send`. Spring strips the `/app` application prefix, finds the `/chat.send` mapping, converts the JSON payload into `ChatRequest`, invokes the method, and serializes the return value into a message sent to `/topic/public`.

`@SendTo` specifies the output destination. If no destination is specified, Spring applies a default rule based on the input destination; in real applications, declare it explicitly so the contract is easy to read.

Payload conversion relies on configured `MessageConverter`s. JSON is a common choice for browser clients; both sides must agree on field names, date formats, and schemas.

## 7. Sending Updates from a Service or HTTP Request

Not every message originates from a STOMP client. A scheduled job, service, or REST controller can also emit updates via `SimpMessagingTemplate`:

```java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class LiveUpdatePublisher {

    private final SimpMessagingTemplate messaging;

    public LiveUpdatePublisher(SimpMessagingTemplate messaging) {
        this.messaging = messaging;
    }

    public void publishOrderStatus(OrderStatusUpdate update) {
        messaging.convertAndSend("/topic/orders", update);
    }

    public void publishPrivateUpdate(String username, AccountUpdate update) {
        messaging.convertAndSendToUser(
                username, "/queue/updates", update);
    }
}
```

`convertAndSend` broadcasts to a shared destination. `convertAndSendToUser` sends to a user destination; the corresponding client subscribes to `/user/queue/updates`. Spring maps `/user` to a user/session-specific destination, allowing multiple users to subscribe to the same logical name without receiving each other's messages.

User destinations require proper principal/session mapping. If the same user is logged in across multiple sessions, messages are sent to that user's sessions by default; broadcast behavior can be adjusted as needed.

## 8. SubscribeMapping for Initial Data

`@SubscribeMapping` is suitable when a client subscribes and needs a direct initial response, such as a current snapshot:

```java
@Controller
class DashboardController {

    @SubscribeMapping("/dashboard.initial")
    DashboardSnapshot initialSnapshot() {
        return dashboardService.currentSnapshot();
    }
}
```

The client subscribes to `/app/dashboard.initial`. By default, the return value is sent directly back to the subscribing client rather than broadcast through the broker to all subscribers. After the initial snapshot, subsequent changes can be published to `/topic/dashboard`.

This pattern avoids making a separate HTTP snapshot call before opening a subscription, though you must handle race conditions between fetching the snapshot and receiving updates. If events must not be missed, include a version/sequence in both the snapshot and updates so the client can detect gaps.

## 9. Browser Client with @stomp/stompjs

Install the JavaScript STOMP client:

```bash
npm install @stomp/stompjs
```

Example connecting, subscribing, and publishing:

```javascript
import { Client } from '@stomp/stompjs';

const client = new Client({
  brokerURL: 'wss://api.example.com/ws',
  reconnectDelay: 5000,
  heartbeatIncoming: 10000,
  heartbeatOutgoing: 10000,
  onConnect: () => {
    client.subscribe('/topic/public', (frame) => {
      const event = JSON.parse(frame.body);
      renderChatEvent(event);
    });

    client.subscribe('/user/queue/updates', (frame) => {
      renderPrivateUpdate(JSON.parse(frame.body));
    });
  },
  onStompError: (frame) => {
    console.error('STOMP broker error:', frame.headers['message']);
  },
  onWebSocketError: (event) => {
    console.error('WebSocket error:', event);
  }
});

client.activate();

export function sendChat(content) {
  if (!client.connected) {
    throw new Error('STOMP client is not connected');
  }

  client.publish({
    destination: '/app/chat.send',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ content })
  });
}

export async function disconnect() {
  await client.deactivate();
}
```

`reconnectDelay` allows the client to reconnect automatically after network loss. Every time `onConnect` runs, re-register subscriptions because a new session may not retain previous subscriptions. Heartbeats help detect dead connections or connections closed by a proxy.

If using SockJS fallback, the server registers `registry.addEndpoint("/ws").withSockJS()` and the client uses SockJS as `webSocketFactory`. Do not enable SockJS just because of STOMP; only add it when fallback is required for client/network environments without full WebSocket support.

Do not send messages before `client.connected` is true. The UI should reflect connecting/connected/reconnecting states and handle publish errors. For critical operations, STOMP SEND does not itself guarantee business commit; design appropriate ACKs/receipts or application-level responses.

## 10. Authentication and Authorization

### 10.1. Authentication from the HTTP Handshake

STOMP over WebSocket starts with an HTTP handshake. In applications using cookies/sessions and Spring Security, the authenticated principal on the HTTP request is transferred to the WebSocket session and attached to subsequent STOMP messages.

This is the simplest approach for same-domain browser apps: secure the HTTP handshake with Spring Security, use cookies/sessions, and obtain `Principal` in `@MessageMapping`.

### 10.2. Tokens in STOMP CONNECT

The browser WebSocket API does not allow arbitrarily adding HTTP headers to the handshake. For applications not using cookie sessions, tokens can be sent in STOMP CONNECT headers and processed by a `ChannelInterceptor`. The interceptor validates the token and then calls `StompHeaderAccessor.setUser(authentication)` on the CONNECT message. Spring associates that user with subsequent messages in the session.

Spring ignores STOMP `login` and `passcode` headers by default for STOMP over WebSocket; do not rely on them to authenticate browser clients. Avoid passing tokens via query strings because URLs often appear in access logs, proxy logs, or analytics.

If using a custom authentication interceptor alongside Spring Security, register your interceptor before the security interceptor according to Spring Security's ordering guidance; otherwise, authorization may run before the user is attached to the message.

### 10.3. CSRF for CONNECT

When `@EnableWebSocketSecurity` is enabled, Spring Security requires a CSRF token on inbound STOMP `CONNECT` to enforce the Same-Origin Policy. The browser must obtain the token from an HTTP endpoint or request attribute and send the matching header name/value in the STOMP client's `connectHeaders`.

Client example:

```javascript
const csrf = await fetch('/csrf', { credentials: 'same-origin' })
  .then(response => response.json());

const client = new Client({
  brokerURL: 'wss://api.example.com/ws',
  connectHeaders: {
    [csrf.headerName]: csrf.token
  }
});
```

The `/csrf` endpoint must be provided by the application to return `CsrfToken`. Do not disable CSRF across the whole application just to make WebSocket connect easier. If adjustments are needed, restrict exemptions strictly to the appropriate handshake/SockJS transport URLs and keep other protections active.

### 10.4. Authorization by Message Type and Destination

Protect both `MESSAGE` and `SUBSCRIBE`. If you only check messages sent to controllers without checking subscriptions, clients can subscribe to destinations they are not permitted to read. Conversely, allowing clients to SEND directly to `/topic/**` lets clients spoof broadcasts.

Spring Security example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

import static org.springframework.messaging.simp.SimpMessageType.MESSAGE;
import static org.springframework.messaging.simp.SimpMessageType.SUBSCRIBE;

@Configuration
@EnableWebSocketSecurity
class WebSocketSecurityConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {
        messages
            .nullDestMatcher().authenticated()
            .simpDestMatchers("/app/**").hasRole("USER")
            .simpSubscribeDestMatchers("/topic/public", "/user/**")
                .hasRole("USER")
            .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
```

Specific rules are declared before fallbacks. The example above requires an authenticated user for messages without a destination, allows role USER to send to `/app/**`, subscribe to the specified destinations, and denies remaining MESSAGE/SUBSCRIBE frames as well as any other messages. Adjust destinations to match your actual API.

Do not let clients SEND to `/topic/**` or `/queue/**` when only the server is permitted to broadcast. Enforce tenant/resource-level permissions in business services; a generic role is insufficient to prove a user owns a specific resource.

## 11. Error Handling and Validation

You can use `@MessageExceptionHandler` to translate business errors into user-specific error messages:

```java
public record ChatError(String code, String message) {}

@MessageExceptionHandler
@SendToUser(destinations = "/queue/errors", broadcast = false)
public ChatError handleInvalidMessage(IllegalArgumentException ex) {
    return new ChatError("INVALID_MESSAGE", ex.getMessage());
}
```

Do not send stack traces, SQL details, or secrets to clients. Log exceptions on the server with correlation/session IDs and return stable error codes.

Validate DTOs, bound payload sizes, rate-limit sensitive commands, and check permissions on every action. A long-lived STOMP connection does not mean a client is allowed to send unlimited messages.

## 12. Ordering, Thread Pools, and Backpressure

Spring uses executor-backed channels for inbound/outbound messages. Multiple threads can process messages concurrently, so completion order can differ from receipt/publish order.

If business logic requires preserving order within a client session, you can enable:

```java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws").setAllowedOriginPatterns("https://app.example.com");
    registry.setPreserveReceiveOrder(true);
}

@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setPreservePublishOrder(true);
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
}
```

These options have overhead; enable them only when business requirements demand ordering. They do not create global ordering across multiple users or multiple application instances.

You can configure inbound/outbound executors:

```java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.taskExecutor()
            .corePoolSize(8)
            .maxPoolSize(32)
            .queueCapacity(1000);
}

@Override
public void configureClientOutboundChannel(ChannelRegistration registration) {
    registration.taskExecutor()
            .corePoolSize(8)
            .maxPoolSize(32)
            .queueCapacity(1000);
}
```

These are starting points for benchmarking, not fixed optimal values. If queue capacity is unbounded, the executor may keep queuing tasks instead of scaling threads as expected. For CPU-bound inbound work, a thread count near CPU count may fit; blocking I/O needs separate evaluation.

Slow clients can cause outbound queues and buffers to grow. Configure send time and send buffer limits:

```java
@Override
public void configureWebSocketTransport(WebSocketTransportRegistration registration) {
    registration.setSendTimeLimit(15_000)
            .setSendBufferSizeLimit(512 * 1024)
            .setMessageSizeLimit(128 * 1024);
}
```

These numbers are examples. Choose limits based on message size, concurrent sessions, client speed, and memory budget. Check limits on the WebSocket server, reverse proxy, and broker; one layer may reject a message before another.

## 13. Session Lifecycle and Events

Spring publishes WebSocket/STOMP-related application events, such as `SessionConnectEvent`, `SessionConnectedEvent`, `SessionSubscribeEvent`, `SessionUnsubscribeEvent`, `SessionDisconnectEvent`, and `BrokerAvailabilityEvent`.

You can listen to them to update presence, track session statistics, clean up resources, or observe broker availability. `SessionDisconnectEvent` can fire more than once in some connection-closing flows; cleanup must be idempotent.

Do not use one instance's in-memory session count as the cluster-wide user count without aggregating through a shared store or broker. When using an external broker relay, also monitor broker connections and availability.

## 14. Monitoring and Operations

When `@EnableWebSocketMessageBroker` is enabled, Spring creates `WebSocketMessageBrokerStats` to aggregate infrastructure metrics. This bean logs periodic statistics by default and can be exported via JMX.

Monitor:

- Current WebSocket/SockJS session count and total opened sessions.
- Connect failures, abnormal closes, transport errors, and send-limit exceeded events.
- STOMP CONNECT/CONNECTED/DISCONNECT frame counts.
- TCP connections of the STOMP broker relay.
- Queue depth and active threads of `clientInboundChannel`.
- Queue depth and active threads of `clientOutboundChannel`.
- Message throughput, payload size, error rate, and send latency.
- Subscription count per destination, reconnect rate, and heartbeat timeouts.

A growing inbound channel queue can indicate the application is slow at processing messages. A growing outbound channel queue can indicate slow-reading clients or poor networks. Distinguish these two directions before increasing thread pools.

Do not log full payloads or tokens. Use controlled session IDs/correlation IDs for investigation; avoid high-cardinality metric tags like user ID or message ID.

## 15. Multi-Instance Scaling

The simple broker keeps subscriptions in the memory of a single application instance and does not support clustering. If client A connects to instance 1 and client B connects to instance 2, broadcasting via instance 1's simple broker will not automatically reach subscriptions on instance 2.

When running multiple instances, use an external broker relay or an appropriate distributed messaging architecture. Each application instance connects to the shared broker; the broker distributes messages to relevant sessions across instances.

Additional considerations:

- A WebSocket connection is tied to the backend selected during the handshake; load balancers do not migrate an open connection to another pod.
- On reconnect, clients must re-subscribe and synchronize current state.
- Use a broker relay and an appropriate user destination registry when users can connect across multiple application instances.
- An in-memory presence/session registry is only a local view; share or aggregate it if features require cluster-wide visibility.
- For critical updates, persist business state/events before broadcasting; WebSocket push does not replace a durable event log.
- Clients should use sequence/version numbers to detect missed messages and fetch fresh snapshots via API.

## 16. Testing

There are two main testing layers:

1. **Server-side message test:** load the Spring context, send `Message<?>` into `clientInboundChannel` or use `SimpAnnotationMethodMessageHandler` to test routing, validation, controllers, and outbound results. Unit tests calling controller methods directly are insufficient to verify annotation mappings.
2. **End-to-end test:** start an embedded WebSocket server, connect with a STOMP client such as `WebSocketStompClient`, send CONNECT/SUBSCRIBE/SEND, and verify received MESSAGE frames.

Test cases to include:

- Successful STOMP connection with valid origin and authentication.
- CONNECT missing or with an invalid CSRF token is rejected when Spring Security is enabled.
- Unauthorized users cannot SEND to `/app/**` or SUBSCRIBE to private destinations.
- Clients cannot spoof sender via a payload field.
- `/topic` broadcasts to matching subscribers.
- `/user/queue/**` delivers only to the target user/session.
- `@SubscribeMapping` returns snapshots directly.
- Validation and `@MessageExceptionHandler` return errors matching the contract.
- Reconnect re-registers subscriptions and fetches snapshots to resync.
- Slow clients hit send buffer/time limits without exhausting server resources.
- External broker relay delivers messages between clients connected to different instances.

## 17. Common Mistakes

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| WebSocket handshake 404 | Client URL does not match registered endpoint | Check `/ws`, context path, and proxy routes |
| WebSocket connects but STOMP does not reach CONNECTED | Subprotocol, frame format, or CONNECT security rejected | Inspect STOMP ERROR frame, CSRF, and server logs |
| Client sends SEND but controller does not run | Destination missing `/app` or wrong mapping | Compare application prefix and `@MessageMapping` |
| Controller runs but nobody receives | Client has not subscribed or wrong destination prefix | Check broker prefixes and session subscriptions |
| Client receives duplicate updates | Reconnect subscribed repeatedly or producer emitted duplicates | Use clean subscription lifecycle and event IDs to deduplicate |
| User receives someone else's updates | Using a shared topic for private data or broken user mapping | Use `/user/**`, authenticated principal, and authorization |
| Messages arrive out of order | Inbound/outbound channels process concurrently | Review ordering requirements; consider preserving receive/publish order |
| Server memory grows when clients are slow | Unbounded outbound buffers/queues or oversized payloads | Bound send buffer/time, message size, and publish rate |
| Broadcast does not reach other instances | Using in-memory simple broker | Switch to an external broker relay |
| Sessions are not cleaned up | Abnormal disconnects or non-idempotent cleanup | Monitor session events and timeouts/heartbeats |

## 18. Implementation Checklist

- [ ] WebSocket endpoint has a clear URL and an explicit origin allowlist.
- [ ] Application destination prefixes and broker prefixes are not confused.
- [ ] DTO payloads are validated and size-limited.
- [ ] Controllers obtain identity from the authenticated Principal, never trusting sender fields in payloads.
- [ ] Clients subscribe to the right topic, queue, or user destination.
- [ ] Clients implement reconnect, heartbeats, and re-subscription after reconnect.
- [ ] CONNECT is protected by CSRF when using default Spring Security.
- [ ] Authorization checks both MESSAGE and SUBSCRIBE.
- [ ] Clients cannot publish directly to internal broker destinations.
- [ ] Simple broker is used only when single-instance scope fits; clusters use a broker relay.
- [ ] Thread pools, queue capacity, send time, send buffer, and message size are bounded.
- [ ] Ordering is enabled only when required by business logic and after measuring overhead.
- [ ] Session lifecycle, monitoring, logs, and metrics are configured.
- [ ] Server-side and end-to-end tests cover connect, subscribe, send, security, and reconnect.

## 19. References

- [Spring Framework — STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html): overview of STOMP over WebSocket, destinations, controllers, brokers, user destinations, and clients.
- [Spring Framework — Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html): `@EnableWebSocketMessageBroker`, endpoints, and broker prefixes.
- [Spring Framework — Message Flow](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): `clientInboundChannel`, `brokerChannel`, `clientOutboundChannel`, and message routing.
- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): `@MessageMapping`, `@SubscribeMapping`, `@SendTo`, and `@SendToUser`.
- [Spring Framework — Sending Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html): `SimpMessagingTemplate` and server-side publishing.
- [Spring Framework — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html): STOMP broker relay and external brokers.
- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html): `/user/` destinations and per-user session routing.
- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html): handshake authentication, CSRF CONNECT, and message authorization.
- [Spring Framework — Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html): tokens in STOMP CONNECT and ChannelInterceptor.
- [Spring Framework — Performance](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html): executors, ordering, message size, and send limits.
- [Spring Framework — Monitoring](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/stats.html): `WebSocketMessageBrokerStats`, session, and channel statistics.
- [Spring Framework — Testing](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/testing.html): server-side message tests and end-to-end WebSocket tests.

Specific APIs and configurations depend on the Spring Framework, Spring Boot, Spring Security, and broker versions. Use compatible dependency management and check the exact version documentation before deploying.
