# Authentication, Destination Authorization, Heartbeats, and Connection Recovery with WebSocket/STOMP

## 1. Context and Four Layers of Responsibility

When building a real-time chat, notification, or live dashboard application with Spring WebSocket and STOMP, opening a connection is only the first step. The system must answer four questions across the connection lifecycle:

1. **Authentication:** Who is connecting? Which identity can be trusted?
2. **Authorization:** Which destinations is that identity allowed to send to (`SEND`) and subscribe to (`SUBSCRIBE`)?
3. **Heartbeats:** How do we detect a connection that is no longer exchanging data, especially when TCP/WebSocket does not report closure immediately?
4. **Connection recovery (reconnection):** After a network drop, how does the client reconnect, re-authenticate, and re-subscribe, and how do we prevent lost or duplicate data?

In STOMP over WebSocket, each layer operates at a different stage:

```text
Browser / client application
       |
       | HTTP GET /ws, Upgrade: websocket, Cookie/Origin
       v
[HTTP Security + Origin + WebSocket handshake]
       |
       | WebSocket open, HTTP Principal may already be attached
       v
[STOMP CONNECT: STOMP session, heartbeat negotiation, CSRF/token if configured]
       |
       | CONNECTED
       v
[STOMP SEND, SUBSCRIBE, UNSUBSCRIBE]
       |                 |
       v                 v
/app/** -> Controller    /topic/**, /queue/** -> Message broker
       |
       v
[Message authorization: check frame type + destination + Principal]
       |
       v
[Heartbeats & session monitoring]
       |
       | connection drop / broker error / auth expired
       v
[Client reconnect -> new CONNECT -> re-authenticate -> re-SUBSCRIBE]
```

Keep clear boundaries:

- **An allowed HTTP handshake** does not mean any message may be sent or received.
- **An authenticated Principal** does not mean access to data belonging to other accounts.
- **Heartbeats detect silence/dead connections**; they do not replace authentication, delivery confirmation, or transactions.
- **A successful reconnection** does not mean messages emitted during the outage were recovered.

This lesson uses Spring Framework with a STOMP message broker on the Servlet stack (Spring MVC/Spring Security 6, Java 17+) as its example. Raw WebSocket or WebFlux without STOMP uses different APIs and security flows. For new development environments, use the Spring/Spring Security versions matching your project's dependency management.

## 2. Authentication at HTTP Handshake and STOMP CONNECT

### 2.1 Common case: HTTP authentication carried over to the STOMP session

STOMP over WebSocket starts with an HTTP handshake. If your application authenticates users via Spring Security with cookies/sessions, Spring can extract the `Principal` from the HTTP request, associate it with the WebSocket session, and attach that `Principal` to STOMP messages in that session.

```text
HTTP login (Spring Security) -> HTTP session/cookie
          |
          v
GET /ws (WebSocket upgrade)
          |
          v
Spring Security authenticates request, extracts Principal
          |
          v
Spring WebSocket binds user to WebSocket/STOMP session
          |
          v
STOMP SEND / SUBSCRIBE -> user header -> authorization
```

Example: Alice is logged in and connects to `wss://api.example.com/ws` from an allowed origin. Frames in that session can be associated by Spring with Alice's `Principal`. Inside `@MessageMapping`, a controller can receive `java.security.Principal` or `Authentication` depending on Security integration.

Note: STOMP defines native `login` and `passcode` headers on CONNECT, but by default Spring **does not use** them to re-authenticate a STOMP-over-WebSocket session when relying on HTTP authentication. Never trust client-supplied values in `login` or `X-User-Id` unless verified by the server.

### 2.2 Example protecting the WebSocket endpoint at the HTTP layer

**File `HttpSecurityConfig.java`:**

```java
package com.example.chat;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class HttpSecurityConfig {

    @Bean
    SecurityFilterChain httpSecurityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/ws", "/ws/**").authenticated()
                .anyRequest().authenticated());
        http.formLogin(withDefaults());
        return http.build();
    }
}
```

This is a Spring Security configuration example for Servlet/MVC, not a standalone Java program and not a WebFlux `SecurityWebFilterChain`. It requires authenticated users for `/ws` and all other routes (an **illustrative** default policy; adjust public routes in real apps). `formLogin` represents session-based login; an API using OAuth2/JWT or SSO needs the corresponding authentication setup.

Do not disable CSRF across the entire system just because WebSocket is present. Depending on how Spring Security WebSocket is enabled, CONNECT may require a CSRF token to defend against cross-site attacks. For SockJS fallback, if HTTP CSRF exceptions are needed for POST transports, scope those exceptions strictly to the required endpoints while keeping STOMP CONNECT protection intact.

### 2.3 The role of Origin and its limits

Origin is the web page origin in a browser, such as `https://app.example.com`. Browsers do not apply the exact same-origin rules to WebSocket that they apply to `XMLHttpRequest`; the server must restrict allowed Origins, especially when cookies/sessions are sent automatically.

```java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
            .setAllowedOrigins("https://app.example.com");
}
```

This snippet belongs in `WebSocketMessageBrokerConfigurer` (complete configuration shown later). `setAllowedOrigins` checks Origin during the handshake; it does not authorize `/topic/private` or authenticate identity. Non-browser clients can set arbitrary Origin headers, so **Origin is not an authentication mechanism**. For multi-origin sites, declare an explicit allowlist; avoid `*` on endpoints using sessions/cookies. Behind a proxy, configure trusted forwarded headers so scheme/host resolution is accurate.

### 2.4 When the token is placed in STOMP CONNECT

The browser `WebSocket` API generally does not let JavaScript attach arbitrary HTTP Authorization headers during the handshake. Some systems authenticate in the STOMP CONNECT frame using an `Authorization: Bearer ...` header sent by the STOMP library **after WebSocket opens**.

Proper workflow:

1. The client obtains a token from a trusted source and places it in the native STOMP CONNECT header rather than setting an arbitrary user ID and expecting it to be trusted.
2. A `ChannelInterceptor` registered on `clientInboundChannel` reads the token from the CONNECT frame.
3. The server validates signature, issuer, audience, expiration, and account status via a real authentication service.
4. Only when the token is valid does it create an appropriate `Authentication` and call `StompHeaderAccessor.setUser(authentication)` on CONNECT.
5. Spring retains that `Principal` for subsequent STOMP messages in the same session; message authorization uses the authenticated `Principal`.
6. Ensure the authentication interceptor runs **before** Spring Security's authorization interceptor.

**Illustrative code integrating a real verifier (does not contain JWT verification logic itself):**

```java
package com.example.chat;

import java.util.List;
import java.util.function.Function;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;

public final class BearerConnectInterceptor implements ChannelInterceptor {

    private final Function<String, Authentication> tokenVerifier;

    public BearerConnectInterceptor(
            Function<String, Authentication> tokenVerifier) {
        this.tokenVerifier = tokenVerifier;
    }

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        StompHeaderAccessor accessor =
                MessageHeaderAccessor.getAccessor(
                        message, StompHeaderAccessor.class);

        if (accessor == null
                || accessor.getCommand() != StompCommand.CONNECT) {
            return message;
        }

        List<String> values =
                accessor.getNativeHeader("Authorization");

        if (values == null || values.size() != 1
                || !values.get(0).startsWith("Bearer ")) {
            throw new BadCredentialsException("Missing bearer token");
        }

        String token = values.get(0).substring("Bearer ".length());
        if (token.isBlank()) {
            throw new BadCredentialsException("Empty bearer token");
        }

        Authentication authentication = tokenVerifier.apply(token);
        if (authentication == null || !authentication.isAuthenticated()) {
            throw new BadCredentialsException("Invalid bearer token");
        }

        accessor.setUser(authentication);
        return message;
    }
}
```

The Java structure above is complete, yet **it does not validate tokens on its own**: `tokenVerifier` must be supplied by a real security service that verifies signatures, expiry, issuer/audience, and user status. Never write `token -> new UsernamePasswordAuthenticationToken("alice", ...)` as a production verifier. On an invalid token, throwing `BadCredentialsException` rejects CONNECT through the pipeline.

Register the interceptor in a separate high-precedence configuration class when integrating with Spring Security message authorization:

```java
@Configuration
@Order(Ordered.HIGHEST_PRECEDENCE + 99)
class StompAuthChannelConfig
        implements WebSocketMessageBrokerConfigurer {

    private final BearerConnectInterceptor interceptor;

    StompAuthChannelConfig(BearerConnectInterceptor interceptor) {
        this.interceptor = interceptor;
    }

    @Override
    public void configureClientInboundChannel(
            ChannelRegistration registration) {
        registration.interceptors(interceptor);
    }
}
```

This is a **supplemental** class snippet; import `Configuration`, `Order`, `Ordered`, `ChannelRegistration`, and `WebSocketMessageBrokerConfigurer`. The application must provide a `BearerConnectInterceptor` Spring bean wired with the verifier. `@Order` expresses the need to run before message security, though ordering must be verified if an app has multiple unmanaged configurations. A cookie/session setup generally does not need this bearer interceptor.

**Important note on CSRF:** Spring Security's `@EnableWebSocketSecurity` enforces CSRF checks on CONNECT by default. Even with a valid auth token, CONNECT can be rejected if the expected CSRF token is missing. Cookie/session integration and token-based setups must be designed coherently with your security policy; never disable protections without threat modeling.

## 3. Authorization by Message Type and Destination

### 3.1 What is a STOMP destination?

With a configured broker:

- `/ws` is the **HTTP URL starting the WebSocket/STOMP session**.
- `/app/**` is an **application destination**, typically routing `SEND` messages to `@MessageMapping` methods in the application.
- `/topic/**` is the convention for broadcasting to multiple subscribers with the simple broker.
- `/queue/**` is a convention often used for queue/private channels; with Spring's simple broker, the prefix alone does not provide point-to-point guarantees like a dedicated message broker.
- `/user/**` is **Spring's user-destination syntax**, translating subscriptions into per-WebSocket-session or per-user destinations via the resolver.

A client sending `SEND /app/chat` and `SUBSCRIBE /topic/announcements` are two different actions, even though both carry a `destination`. Never authorize solely by path prefix while ignoring **message type**.

Example:

```text
SEND       /app/chat                   -> controller message
SEND       /topic/announcements        -> must be blocked for regular clients
SUBSCRIBE  /topic/announcements        -> may be permitted
SUBSCRIBE  /user/queue/notifications   -> requires authenticated user
SUBSCRIBE  /topic/admin                -> ADMIN role only
```

If clients are allowed to `SEND` straight to `/topic/admin`, a client could forge messages appearing to come from the server, depending on broker configuration. If regular users can `SUBSCRIBE /topic/admin`, they can read unauthorized data. Therefore, write separate policies for SEND and SUBSCRIBE, denying unlisted cases by default.

### 3.2 Spring Security: AuthorizationManager for STOMP messages

Spring Security supports `@EnableWebSocketSecurity` and `MessageMatcherDelegatingAuthorizationManager` to authorize inbound messages. Illustrative configuration:

**File `StompMessageSecurityConfig.java`:**

```java
package com.example.chat;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
public class StompMessageSecurityConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            .nullDestMatcher().authenticated()
            .simpSubscribeDestMatchers("/topic/admin/**")
                .hasRole("ADMIN")
            .simpSubscribeDestMatchers(
                    "/topic/announcements",
                    "/user/queue/notifications")
                .hasRole("USER")
            .simpDestMatchers("/app/**").hasRole("USER")
            .simpTypeMatchers(
                    SimpMessageType.MESSAGE,
                    SimpMessageType.SUBSCRIBE)
                .denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
```

**Ordering explained:**

1. `nullDestMatcher().authenticated()` requires an authenticated user for messages without a destination. Session-lifecycle frames such as CONNECT/DISCONNECT typically fall here.
2. `simpSubscribeDestMatchers("/topic/admin/**").hasRole("ADMIN")` is placed before broader rules to avoid accidentally granting access to admin topics.
3. `simpSubscribeDestMatchers("/topic/announcements", "/user/queue/notifications").hasRole("USER")` lets `ROLE_USER` subscribe to those two approved destinations.
4. `simpDestMatchers("/app/**").hasRole("USER")` applies to application destinations; if you want to allow only `SEND`, add the specific type matcher/rule and test message types explicitly.
5. Remaining `MESSAGE` or `SUBSCRIBE` frames are denied; finally, any unlisted message type is denied.

This illustrative policy requires **ROLE_USER** for `/user/queue/notifications` and `/topic/announcements`; an account holding only `ROLE_ADMIN` without `ROLE_USER` will match only the ADMIN rules unless a role hierarchy is configured. Design roles explicitly; never assume `ADMIN` automatically implies `USER`.

**Technical note:** `@EnableWebSocketSecurity` secures inbound STOMP messages, not the HTTP handshake—it does not replace HTTP Spring Security configuration. Interceptors run in order; when authenticating via a STOMP CONNECT token, place the authentication interceptor before the authorization interceptor. When Spring Security checks CSRF on CONNECT, clients must send the token per the security contract.

### 3.3 What destination matchers do not do for you

A rule `.simpSubscribeDestMatchers("/topic/rooms/**").hasRole("USER")` only proves the user has role `USER`; it **does not prove** the user belongs to a specific room. When data is scoped by `tenantId`, `roomId`, or `documentId`, authorization must verify ownership/membership against that entity.

For example `/topic/rooms/123`: Alice has `ROLE_USER` but is not a member of room 123 and must be denied. You can build a custom `AuthorizationManager<Message<?>>` to inspect `Principal`, message type, and destination, verify membership via a trusted service, and return a decision. Never accept a client-supplied `roomId` or `userId` as proof of permission. Alternatively, clients can `SUBSCRIBE` to a user destination while the server only emits events the user is permitted to see.

When using user destinations, `/user/queue/notifications` is what the client subscribes to; `SimpMessagingTemplate.convertAndSendToUser(username, "/queue/notifications", payload)` is one way the server sends to that user. The resolver translates it into a session-specific destination. **Never treat a username string in an address as proof of access rights.**

### 3.4 Checking SEND permissions inside controllers too

Inside controllers, validate the user or `Authentication` against business policies. Example assuming `Principal` comes from HTTP/STOMP security:

**File `ChatMessageController.java`:**

```java
package com.example.chat;

import java.security.Principal;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class ChatMessageController {

    @MessageMapping("/echo")
    @SendToUser("/queue/echo")
    public String echo(String body, Principal principal) {
        if (principal == null) {
            throw new IllegalStateException("Authentication required");
        }
        return principal.getName() + ": " + body;
    }
}
```

With `setApplicationDestinationPrefixes("/app")`, a client's `SEND /app/echo` reaches `@MessageMapping("/echo")` if message authorization permits it. With `@SendToUser("/queue/echo")`, matching clients normally subscribe to `/user/queue/echo`. If applying the exact authorization configuration from section 3.2, you must **add a rule** for `/user/queue/echo` before testing, since the illustrative rules only permitted `/user/queue/notifications` and deny other destinations by default. That is an intentional safeguard of deny-by-default, not a broker bug.

The echo example cannot replace membership checks in real chat apps: if a body specifies a room ID, the controller/service must still verify the user is a member before posting into that room.

## 4. Aligning Broker and Endpoint Config with Security

**File `ChatWebSocketConfig.java`:**

```java
package com.example.chat;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class ChatWebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("https://app.example.com");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
```

This is the baseline configuration for a Spring MVC + WebSocket message broker application. Calling `enableSimpleBroker` creates an in-memory simple broker suited for training and small systems; it **is not equivalent** to RabbitMQ/ActiveMQ in persistence, multi-node distribution, delivery acknowledgements, durability, or offline queuing.

Add the security classes from sections 2–3 as required. Choose **one** primary authentication strategy—HTTP or CONNECT token—and enforce channel controls and CSRF consistently. When combining multiple `WebSocketMessageBrokerConfigurer` beans, pay attention to interceptor registration order and application settings.

Using Spring Boot 3.x, Java 17+, and Gradle with Spring dependency management, typical dependencies are:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-messaging'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Place the Java files in the proper package and source set. They are configuration components of a Spring Boot application with an entry point; they cannot run standalone via `javac ChatWebSocketConfig.java` without the Spring classpath. With Spring Boot dependency management, keep Spring library versions aligned instead of mixing incompatible JARs.

## 5. STOMP Heartbeats: Negotiating Intervals and Detecting Dead Connections

### 5.1 What is a STOMP heartbeat?

Since STOMP 1.1, `CONNECT`/`CONNECTED` frames can declare a `heart-beat: x,y` header in milliseconds. Specifically:

- Client `CONNECT heart-beat: cx,cy`: `cx` is the minimum interval between heartbeats the client **can send**; `cy` is the minimum interval the client **wants to receive** data/heartbeats from the server.
- Server `CONNECTED heart-beat: sx,sy`: `sx` is the minimum interval the server **can send**; `sy` is the minimum interval the server **wants to receive** from the client.
- If either side specifies `0` for send or receive, heartbeats in that direction are disabled.
- When both sides agree, the negotiated **client → server** interval is `max(cx, sy)`; **server → client** is `max(sx, cy)`.

Example:

```text
Client: CONNECT   heart-beat:10000,10000
Server: CONNECTED heart-beat:10000,20000

client -> server: max(10000, 20000) = 20000 ms
server -> client: max(10000, 10000) = 10000 ms
```

This is an **expected activity cadence**, not an OS-level guarantee of exact millisecond precision. When application data frames flow regularly, extra heartbeat frames are unnecessary. When the stream is silent, a heartbeat (a single newline byte per spec) lets the receiver verify the channel is still alive.

**Not a delivery acknowledgement protocol:** heartbeats do not confirm that a `SEND` was processed, written to a database, or delivered to subscribers. Use receipts/ACKs and application-level mechanisms when outcomes must be known.

### 5.2 Standalone Java example: computing heartbeat intervals

The following code does not use Spring; it demonstrates interval negotiation. Runnable on Java 17+:

**File `HeartbeatNegotiationDemo.java`:**

```java
public class HeartbeatNegotiationDemo {

    static long agreedInterval(long senderCanSend,
                               long receiverWantsReceive) {
        if (senderCanSend == 0 || receiverWantsReceive == 0) {
            return 0;
        }
        return Math.max(senderCanSend, receiverWantsReceive);
    }

    public static void main(String[] args) {
        long clientSend = 10_000;
        long clientReceive = 10_000;
        long serverSend = 10_000;
        long serverReceive = 20_000;

        long clientToServer = agreedInterval(
                clientSend, serverReceive);
        long serverToClient = agreedInterval(
                serverSend, clientReceive);

        System.out.println("client -> server: " + clientToServer + " ms");
        System.out.println("server -> client: " + serverToClient + " ms");
        System.out.println("disabled direction: "
                + agreedInterval(0, 10_000) + " ms");
    }
}
```

Commands:

```bash
javac HeartbeatNegotiationDemo.java
java HeartbeatNegotiationDemo
```

**Exact stdout:**

```text
client -> server: 20000 ms
server -> client: 10000 ms
disabled direction: 0 ms
```

This program assumes non-negative intervals and does not validate the wire protocol; it clarifies the STOMP heartbeat rule. Do not confuse this interval helper with the actual client/server scheduler.

### 5.3 Enabling heartbeats on Spring's simple broker

Spring's simple broker can emit STOMP heartbeats when given a `TaskScheduler`. Without an appropriate scheduler, declaring heartbeat expectations without configuring the emitter can mislead clients into thinking the session died.

The sample config below is a **variant** of `configureMessageBroker`, intended to replace the `configureMessageBroker` configuration in section 4 rather than running alongside it:

```java
package com.example.chat;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class HeartbeatWebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    private final TaskScheduler scheduler;

    public HeartbeatWebSocketConfig(
            @org.springframework.beans.factory.annotation.Lazy
            TaskScheduler brokerHeartbeatScheduler) {
        this.scheduler = brokerHeartbeatScheduler;
    }

    @Bean
    TaskScheduler brokerHeartbeatScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("stomp-heartbeat-");
        return scheduler;
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("https://app.example.com");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/topic", "/queue")
                .setHeartbeatValue(new long[] {10_000, 20_000})
                .setTaskScheduler(scheduler);
    }
}
```

When integrating into a project, choose **one** broker configuration: use `HeartbeatWebSocketConfig` **instead of** `ChatWebSocketConfig` from section 4, rather than registering two parallel classes on the same endpoint. `@Lazy` is used here because injecting `TaskScheduler` into `WebSocketMessageBrokerConfigurer` can trigger circular dependencies under some Spring auto-configurations. Spring may also provide its own scheduler; inspect existing beans and adjust qualifiers/names if multiple schedulers exist so the right one is used. Scheduler resources must be managed by Spring's application lifecycle.

`setHeartbeatValue(new long[]{10000, 20000})` specifies the broker's desired send/receive intervals. Actual timing also depends on client negotiation, scheduler load, traffic, and receiver timeout thresholds.

### 5.4 Simple broker and broker relay are not the same

With the simple broker, message subscriptions live in application memory; heartbeats are handled by Spring coordinating the scheduler and WebSocket sessions. With multiple independent server instances, the simple broker on instance A does not distribute messages to subscribers on instance B.

With an external broker relay (STOMP-compatible RabbitMQ/ActiveMQ), the application forwards messages to the external broker. The relay manages a **system** connection to the broker plus per-client connections; heartbeats between Spring and the broker are a separate layer from STOMP heartbeats received by clients over WebSocket.

Spring's broker relay can automatically retry the **system connection** when the broker is unreachable (documentation notes a default 5-second retry interval), but **that does not reconnect WebSocket client sessions**. Clients still need reconnection, authentication, and re-subscription logic. When the system connection drops, the server may emit `BrokerAvailabilityEvent` so publishers know the broker is temporarily unavailable.

## 6. Connection Recovery: States and Standard Workflow

### 6.1 Why is client-side reconnection logic necessary?

Wi-Fi drops, mobile network handoffs, proxy idle timeouts, server restarts, or broker incidents can all close a WebSocket/STOMP session. The WebSocket API does not guarantee every network failure raises an immediate signal; heartbeats and transport timeouts help detect silent failures.

Typical client lifecycle:

```text
DISCONNECTED
     |
     | connect WebSocket
     v
SOCKET_OPEN
     |
     | STOMP CONNECT (+ credential/CSRF + heart-beat)
     v
STOMP_CONNECTED
     |
     | re-SUBSCRIBE to permitted destinations
     | resync data from HTTP snapshot + cursor/sequence
     v
READY
     |
     | network drop / server close / heartbeat lost
     v
DISCONNECTED
     |
     | bounded retry delay + jitter/backoff
     +-----> reconnect
```

After a successful reconnect, the **new STOMP session** normally gets a new session ID; subscriptions from the old session are gone. The client must recreate subscriptions after `CONNECTED`, and the server must re-check user permissions on the new session.

Do not send business operations while the app is unsure whether the session can receive replies. For side-effecting messages (payments, critical mutations), use idempotency keys, correlation IDs, and status confirmation APIs instead of blindly replaying every `SEND` whenever the network flickers.

### 6.2 Browser client with @stomp/stompjs

The JavaScript library `@stomp/stompjs` supports heartbeat configuration, reconnect delays, and lifecycle callbacks. The example below uses HTTP cookie/session auth (sent by the browser per cookie policy) and server-permitted destinations.

**File `stomp-client.js`:**

```javascript
import { Client, ReconnectionTimeMode } from "@stomp/stompjs";

const client = new Client({
  brokerURL: "wss://api.example.com/ws",
  reconnectDelay: 1000,
  reconnectTimeMode: ReconnectionTimeMode.EXPONENTIAL,
  maxReconnectDelay: 15000,
  heartbeatOutgoing: 10000,
  heartbeatIncoming: 10000,

  onConnect: () => {
    console.log("STOMP connected");

    // Re-subscribe on every new CONNECTED.
    client.subscribe("/user/queue/notifications", (message) => {
      const event = JSON.parse(message.body);
      handleNotification(event);
    });
  },

  onStompError: (frame) => {
    console.error("STOMP error:", frame.headers["message"]);
  },

  onWebSocketClose: () => {
    console.info("WebSocket closed; client may reconnect");
  }
});

function handleNotification(event) {
  // Compare event.id / sequence before updating UI or state.
  console.log("Event received:", event);
}

client.activate();

// When the user logs out or the page truly no longer needs a connection:
// await client.deactivate();
```

This code is intended for a bundled JavaScript/browser environment with `@stomp/stompjs` installed. Update the URL to your real endpoint, using `wss` over HTTPS. `handleNotification` only logs events for demonstration; real apps must validate JSON structure, reliability, and message ordering.

Explanation of options:

- `heartbeatOutgoing`: client's offered send interval; `heartbeatIncoming`: expected receive interval.
- `reconnectDelay` paired with `ReconnectionTimeMode.EXPONENTIAL`: initial delay that grows across repeated failures up to `maxReconnectDelay`, reducing synchronized retry storms.
- `onConnect` runs after every new `CONNECTED`; place `subscribe` inside this callback so subscriptions are restored.
- `onStompError` handles STOMP `ERROR` frames; do not treat every error as a transient network glitch. If authentication failed or the account was disabled, stop retrying or prompt re-login per UI policy.
- `onWebSocketClose` signals transport closure; reconnection depends on client state and settings. Do not add a separate `setInterval` retry loop alongside the library's built-in mechanism.

When a component unmounts or the user logs out, call `await client.deactivate()` to close and stop the reconnect loop. Avoid creating multiple `Client` instances or leaving them active after navigating away, which causes duplicate subscriptions and resource leaks.

### 6.3 Using a token in CONNECT during reconnect

In token-based strategies, the client needs a valid token for **every** new STOMP CONNECT. If a short-lived token expired, refresh it via a secure auth flow before reconnecting. The library allows updating `connectHeaders` or `beforeConnect` depending on the API.

Illustrative snippet:

```javascript
client.beforeConnect = async () => {
  const token = await trustedTokenProvider(); // Application-supplied function.
  client.connectHeaders = {
    Authorization: "Bearer " + token
  };
};
```

Here `trustedTokenProvider` is an **interface the application must supply**, not a built-in function or standalone runnable example. It must manage secrets securely and never log tokens. If Spring Security enforces CSRF checks on CONNECT, include the CSRF token per your auth flow; setting `Authorization: Bearer` alone does not guarantee CONNECT will pass.

Never place long-lived access tokens in the `brokerURL` query string when safer alternatives exist: URLs can be logged by proxies or monitoring tools. Never take a token from user input and trust unverified contents.

### 6.4 When should automatic retries stop?

Transient failures such as network drops or server maintenance can be retried with exponential backoff and jitter. Non-recoverable errors such as invalid credentials, locked accounts, logged-out sessions, or forbidden destinations should surface an error in the UI and pause retries until state changes.

Bound retries appropriately for UX: for example, after repeated failures show "Connection lost, retrying" with background backoff when permitted. Never assume users stay online or tabs remain in the foreground; browsers throttle background timers, so real-world timing has variance.

## 7. Data Synchronization After Reconnect: What Does STOMP Guarantee?

### 7.1 Heartbeats, receipts, ACKs, and message durability are distinct concepts

| Mechanism | Question answered | What it does NOT guarantee |
| --- | --- | --- |
| Heartbeat | Are both sides still exchanging data? | Message processed successfully or persisted |
| STOMP RECEIPT | Did the broker/receiver process the frame per supported receipt semantics? | Business transaction committed to DB or user read it |
| ACK/NACK | Did the subscriber acknowledge processing per the chosen ack mode? | "Exactly-once" external side effects without idempotency |
| Correlation ID | Which request do logs/events belong to? | Message secrecy, successful delivery, or authorization |
| Sequence/cursor | Were any events missed or reordered? | Automatic resync if server retains no history |
| Idempotency key | Can duplicate requests be handled safely per server policy? | Consistency if keys are misused or improperly stored |

With the in-memory simple broker, disconnected clients generally **do not receive** broadcasts emitted while offline upon reconnecting. If missing messages is unacceptable, design an event/history store or a durable message broker with replay support.

### 7.2 Re-synchronization pattern with sequence IDs

Suppose the server assigns monotonically increasing `eventId`s per stream. The client tracks `lastSeenEventId` and after reconnecting:

1. Establishes the socket and completes STOMP CONNECT.
2. Re-subscribes to required destinations.
3. Calls an HTTP sync API or requests replay from `lastSeenEventId` via a server-supported mechanism.
4. Merges the snapshot/replay with live events received during sync, deduplicating by `eventId` and sorting per contract.
5. Advances `lastSeenEventId` only once events are processed/persisted per client criteria.

You must handle the **race window** between subscribing and snapshotting: either subscribe first and buffer incoming events while fetching the cursor-based snapshot, or use a server protocol that delivers a consistent snapshot + stream boundary. Never simply "refetch once" and assume no new messages arrived during the fetch.

For sending chat messages, use a unique `clientMessageId` and server-side deduplication so that when a client is unsure whether an earlier `SEND` succeeded, it can retry without creating duplicates. For sensitive messages, re-verify read permissions in the replay API rather than relying solely on earlier subscription checks.

### 7.3 Be cautious with "exactly once"

STOMP is only a frame transport protocol; it does not provide end-to-end exactly-once semantics across multiple services, databases, and UIs. Even with a broker supporting ACKs and persistence, an app can redeliver after crashing between processing and ACKing. The realistic goal is **at-least-once + idempotency/deduplication** or an equivalent business pattern, depending on requirements.

## 8. Observing Connections on the Server: Session Events and Broker Availability

Spring publishes events that help applications track connections:

| Event | When does it occur? |
| --- | --- |
| `SessionConnectEvent` | Server receives STOMP CONNECT |
| `SessionConnectedEvent` | Server sent CONNECTED; STOMP session is considered established |
| `SessionSubscribeEvent` | SUBSCRIBE received |
| `SessionUnsubscribeEvent` | UNSUBSCRIBE received |
| `SessionDisconnectEvent` | STOMP session ended; from DISCONNECT or WebSocket close |
| `BrokerAvailabilityEvent` | Broker relay availability changed, usually tied to the system connection |

`SessionDisconnectEvent` can be published **more than once for the same session**, so cleanup code must be idempotent.

Example listening to connect/disconnect events and logging metadata:

**File `StompSessionEvents.java`:**

```java
package com.example.chat;

import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionConnectedEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

@Component
public class StompSessionEvents {

    @EventListener
    public void onConnected(SessionConnectedEvent event) {
        SimpMessageHeaderAccessor headers =
                SimpMessageHeaderAccessor.wrap(event.getMessage());
        System.out.println("STOMP connected session="
                + headers.getSessionId());
    }

    @EventListener
    public void onDisconnected(SessionDisconnectEvent event) {
        System.out.println("STOMP disconnected session="
                + event.getSessionId());
    }
}
```

This is a Spring component illustrating events; in production replace `System.out` with a bounded logger and use idempotent state cleanup. A CONNECTED message may or may not include additional metadata; do not rely on reading cookies/tokens from events and never log credentials.

When tracking presence ("online/offline"), a user can hold **multiple sessions** (multiple tabs/devices). Disconnecting one session does not mean the user is completely offline. Multi-node systems need a distributed presence store and application-level TTLs/heartbeats for accurate global state.

## 9. Testing Authentication, Authorization, Heartbeats, and Reconnection

### 9.1 Security test matrix

Split tests by layer to pinpoint where failures originate:

| Scenario | Expectation |
| --- | --- |
| HTTP handshake without user in cookie auth mode | Blocked by HTTP security/handshake |
| Browser Origin outside allowlist | Fails handshake per policy |
| Valid user, STOMP CONNECT missing CSRF when required by security | CONNECT rejected; HTTP 101 does not mean STOMP session succeeded |
| Invalid or expired STOMP token | Authentication interceptor rejects CONNECT |
| `ROLE_USER` sends `SEND /app/echo` | Dispatched to controller if other conditions pass |
| `ROLE_USER` sends directly to `/topic/admin/alerts` | Blocked; cannot impersonate server broadcast |
| `ROLE_USER` subscribes to `/topic/admin/**` | Blocked |
| `ROLE_ADMIN` subscribes to `/topic/admin/**` | Allowed if authenticated with matching role |
| `ROLE_USER` subscribes to `/topic/rooms/secret` without membership | Blocked by room/user permission check (beyond role alone) |
| User logs out then reconnects with old token | Must not regain revoked access |
| CONNECT frame supplies a self-claimed user ID | Must not overwrite the authenticated Principal |

Testing the HTTP handshake and STOMP CONNECT are two separate steps: an HTTP test may receive 101 while STOMP CONNECT still fails with ERROR. An integration test usually runs a real STOMP client against an embedded server with test accounts; avoid "mocking everything" when verifying the path between HTTP security, channel interceptors, and the broker.

### 9.2 Testing heartbeats under low traffic

Use two heartbeat-capable peers configured with short intervals **in test environments only**, and observe:

- CONNECT/CONNECTED negotiate intervals in both directions.
- When no application frames are sent, heartbeats still fire on schedule.
- When the server/broker stops sending data, the client detects it within a **tolerance window**, not on the exact first millisecond.
- Upon detection, the client marks disconnected, pauses tasks temporarily, and triggers reconnection.
- On reconnect, listeners/handlers/subscriptions are not duplicated.

Avoid testing heartbeats with a naive `Thread.sleep(10000)` asserting "closes after exactly 10 seconds"; schedulers, networking, OS scheduling, and browser throttling introduce variance. Use bounded waits with reasonable tolerance and observe connection signals/states.

### 9.3 Testing reconnect during active messages

Set up a subscribed client, emit several events with `eventId`, drop the connection before the next event, let the client reconnect, and replay missed data via the application's snapshot/replay API. Verify:

- The client has no leftover old subscriptions on the new session, yet **re-subscribes**.
- Events emitted while offline are recovered via the application's replay mechanism (if provided).
- Duplicate events are discarded with no duplicate side effects.
- Permissions are re-evaluated; a user whose permissions were revoked while offline cannot subscribe or replay old data.
- If the server repeatedly rejects auth, reconnection stops or prompts login per policy.

With a broker relay, test broker outages separately from browser WebSocket drops, since the relay system connection and client sessions have independent lifecycles.

### 9.4 Java unit test for retry backoff logic

Example of a simple delay calculation strategy—**does not replace** `@stomp/stompjs`, but lets you unit-test backoff rules:

**File `ReconnectBackoffDemo.java` (Java 17+, no Spring dependency):**

```java
public class ReconnectBackoffDemo {

    static long retryDelayMillis(int failureCount) {
        long delay = 1000;
        for (int attempt = 1; attempt < failureCount; attempt++) {
            delay = Math.min(delay * 2, 16_000);
        }
        return delay;
    }

    public static void main(String[] args) {
        System.out.println("attempt 1: "
                + retryDelayMillis(1) + " ms");
        System.out.println("attempt 2: "
                + retryDelayMillis(2) + " ms");
        System.out.println("attempt 3: "
                + retryDelayMillis(3) + " ms");
        System.out.println("attempt 6: "
                + retryDelayMillis(6) + " ms");
    }
}
```

Run:

```bash
javac ReconnectBackoffDemo.java
java ReconnectBackoffDemo
```

**Exact stdout:**

```text
attempt 1: 1000 ms
attempt 2: 2000 ms
attempt 3: 4000 ms
attempt 6: 16000 ms
```

This demo omits jitter, max-retry caps, and browser timer throttling; real reconnect strategies need those when many clients disconnect simultaneously to avoid a "thundering herd" hitting the server.

## 10. Common Mistakes and How to Fix Them

| Mistake | What can happen | Fix |
| --- | --- | --- |
| Allowing all frames once HTTP handshake succeeds | Authenticated users send/read unauthorized messages | Enforce message authorization per frame/destination, deny-by-default |
| Treating STOMP `login`/`passcode` as auth in Spring | Clients can spoof any username | Use HTTP Principal or real CONNECT token verification |
| Checking Role only without checking room/tenant | Users read other rooms sharing `ROLE_USER` | Enforce entity-level ownership checks on the server |
| Allowing direct `SEND` to `/topic/**` | Clients spoof server broadcasts | Deny client `MESSAGE`/direct broker sends; expose only needed `/app/**` |
| Allowing unrestricted `SUBSCRIBE /topic/private/**` | Internal data leaks | Restrict destinations and check membership |
| Using wildcard Origin with cookies/sessions | Loses browser origin defense | Tight Origin allowlist, proper auth/CSRF |
| Disabling CSRF site-wide for SockJS | Opens CSRF vulnerabilities on other routes | Narrow HTTP exception and protect CONNECT |
| Enabling heartbeats on client without server config | Client falsely thinks server died or misdetects drops | Enable broker heartbeats, scheduler, and STOMP negotiation |
| Assuming heartbeats prove messages were persisted | Data loss during reconnect | Design proper ACK/receipt/snapshot/replay |
| Assuming broker relay reconnects browsers | UI stays stuck offline | Implement reconnect in every STOMP client |
| Calling `subscribe` only on initial load | No messages received after reconnect | Re-subscribe inside every `CONNECTED` handler |
| Reconnecting continuously without backoff | Server overloaded during widespread outages | Backoff + jitter + caps; distinguish auth failures |
| Blindly replaying every `SEND` after disconnect | Duplicate operations, double charges/orders | Idempotency keys and status lookup APIs |
| Assuming one socket per user | Closing one tab marks user offline | Track multiple sessions per user |
| Non-idempotent cleanup in `SessionDisconnectEvent` | Duplicate cleanup runs, corrupt state | Make disconnect cleanup idempotent across repeated events |
| Relying on SimpleBroker for offline storage | Lost notifications while disconnected | Use history/replay or a durable broker |
| Logging tokens or raw STOMP frames | Exposes credentials and private payloads | Log sanitized metadata; never log secrets |

## 11. Implementation Checklist

Before shipping WebSocket/STOMP features to production:

1. **Authentication:** choose HTTP session or CONNECT token as identity source; test identity across reconnects and token expiration.
2. **Origin/CSRF:** tight Origin allowlist, understand cookies/SameSite/proxies and STOMP CONNECT/SockJS CSRF policies.
3. **Destinations:** enumerate permitted SEND and SUBSCRIBE destinations, deny undeclared ones, and enforce resource-level checks.
4. **Heartbeats:** enable a scheduler for the simple broker or configure broker relay, negotiate realistic intervals with clients, and apply timeout tolerances.
5. **Reconnection:** manage a single client instance per lifecycle, exponential backoff (with jitter where needed), re-subscribe in `onConnect`, and stop retrying on logout.
6. **Synchronization:** store cursors/sequences and provide snapshot/replay APIs if data cannot be lost; deduplicate events and use idempotency keys for mutations.
7. **Observability:** track sessions, connected/disconnected counts, broker availability, auth failures, retry counts, missed heartbeats, and delivery gaps; scrub PII from logs.
8. **Testing:** combine unit tests on matchers/policies with integration tests covering HTTP handshake + CONNECT + SUBSCRIBE/SEND + real network drops.

A useful diagnostic checklist when a user reports "WebSocket is connected but no notifications arrive": **Is the HTTP socket open or is STOMP CONNECTED? Does the user have the right Principal? Was SUBSCRIBE allowed, targeting the right destination, on the current session? Is the broker available? Are new events firing or do missed events need replay?** Answering layer by layer pinpoints the root cause quickly.

## 12. References

- [Spring Framework — STOMP Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html): HTTP Principal and STOMP `login/passcode`.
- [Spring Framework — STOMP Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html): validating tokens in CONNECT via `ChannelInterceptor`, ordered before authorization.
- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html): `@EnableWebSocketSecurity`, destination matchers, CSRF/same-origin.
- [Spring Framework — STOMP Authorization](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html): checking permissions on the client inbound channel.
- [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html): `TaskScheduler` and simple broker heartbeats.
- [Spring Framework — Broker Relay](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html): external broker heartbeats and system connections.
- [Spring Framework — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html): `WebSocketStompClient`, heartbeats, and receipts.
- [Spring Framework — STOMP Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html): connect/disconnect events, client-side reconnect responsibility.
- [@stomp/stompjs — Client API](https://stomp-js.github.io/api-docs/latest/classes/Client.html): reconnect/backoff, heartbeats, and client lifecycle.
