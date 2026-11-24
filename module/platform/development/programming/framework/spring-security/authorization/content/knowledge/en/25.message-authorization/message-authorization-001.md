# Distinguishing HTTP Handshake Protection from STOMP Message Protection in Spring Security

## 1. The Problem: A Successful WebSocket Connection Does Not Mean Unrestricted Access

Suppose an internal chat application uses Spring Boot, Spring WebSocket, and STOMP:

- User Alice accesses `/ws` to establish a WebSocket connection.
- Alice sends a message using the STOMP `SEND` command to `/app/chat.send`.
- Alice subscribes to receive notifications using `SUBSCRIBE` to `/user/queue/messages`.
- An administrative system broadcasts notifications to `/topic/system`.
- Private chat rooms of tenant A are restricted to members of tenant A.

If Spring Security only checks HTTP:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/ws", "/ws/**").authenticated()
    .anyRequest().denyAll()
);
```

then this helps protect the HTTP path used for the handshake, **not a complete policy for every subsequent STOMP frame**. An upgraded WebSocket connection can remain open for a long time; `SEND`, `SUBSCRIBE`, `UNSUBSCRIBE`, and `DISCONNECT` frames pass through the messaging pipeline rather than creating a new HTTP request through `SecurityFilterChain` each time.

For example, an attacker who has a valid account but does not belong to the `finance` room can still try:

```text
SUBSCRIBE
id:sub-1
destination:/topic/rooms/finance

^@
```

or send to a channel where the application intends only the **server** to be allowed to publish:

```text
SEND
destination:/topic/system
content-type:text/plain

Fake emergency notice^@
```

Without **message-level authorization**, handshake success can lead to unauthorized data reads or broadcasts. The `^@` notation above merely illustrates the STOMP frame terminator (NUL byte), not a literal character that must be typed in a client.

**Core message:** The HTTP handshake protects **transport establishment and initial identity**; STOMP authorization protects **each message type, destination, resource, and context**. The two layers must work together rather than replacing one another.

### Objectives

After this lesson, you will be able to:

1. Describe the flow `HTTP handshake → STOMP CONNECT → SEND/SUBSCRIBE → broker → client`.
2. Distinguish Servlet HTTP `SecurityFilterChain` from Spring Messaging `AuthorizationManager<Message<?>>`.
3. Understand how `Principal` is propagated from HTTP to the STOMP session, and when token-based authentication requires a separate `ChannelInterceptor`.
4. Distinguish `/app/**`, `/topic/**`, `/queue/**`, and `/user/**` destinations.
5. Write an `@EnableWebSocketSecurity` configuration with clear matcher ordering and deny-by-default rules.
6. Prevent clients from sending `SEND` directly to broker destinations to spoof the server.
7. Prevent unauthorized `SUBSCRIBE` to private tenant/user destinations.
8. Understand Same Origin, Origin allowlists, CSRF on STOMP CONNECT, and SockJS considerations.
9. Test both the handshake **and** STOMP frames, including verifying that rejected frames are not forwarded to the broker.
10. Run a standalone Java 17 example simulating the difference between the two layers.

## 2. From HTTP to STOMP: Two Protocols, Two Enforcement Points

A flow may look like this:

```text
Browser                                  Spring Boot / Spring Security
   |
   |  1. GET /ws + Upgrade: websocket
   +--------------------------------------> SecurityFilterChain (HTTP)
   |                                             |
   |                          authentication, URL authorization, origin/CSRF
   |                                             |
   |  2. HTTP 101 Switching Protocols <----------+
   |       (if accepted)
   |
   |  3. STOMP CONNECT frame
   +--------------------------------------> clientInboundChannel
   |                                             |
   |                             CONNECT authentication / CSRF / security
   |                                             |
   |  4. STOMP CONNECTED <------------------------+
   |
   |  5. STOMP SUBSCRIBE /user/queue/messages
   +--------------------------------------> message AuthorizationManager
   |                                             |
   |                              authorization per type + destination
   |                                             |
   |  6. STOMP SEND /app/chat.send
   +--------------------------------------> @MessageMapping + domain policy
   |                                             |
   |                              SimpMessagingTemplate / message broker
   |                                             |
   |  7. STOMP MESSAGE <--------------------------+
```

Note: `101 Switching Protocols` is the success response of a native WebSocket handshake; with SockJS fallback transports, HTTP requests and responses may differ. `STOMP CONNECTED` is the confirmation at the **STOMP protocol layer**, not HTTP 101.

### Boundary Table

| Event | Primary Processing Point | Problem Addressed |
| --- | --- | --- |
| HTTP GET to `/ws` | Servlet `SecurityFilterChain` | Should the HTTP connection request be allowed through? |
| HTTP Upgrade | WebSocket handshake pipeline | Protocol/origin/upgrade rules |
| STOMP `CONNECT` | Inbound message channel | Establishing STOMP session, identity, CSRF/command policy |
| STOMP `SEND` | Inbound channel + handler | Who may send to which destination? Is the payload action allowed? |
| STOMP `SUBSCRIBE` | Inbound channel + broker | Who may subscribe to receive data from which destination? |
| STOMP `UNSUBSCRIBE` | Inbound channel | Stopping a subscription; lifecycle rules |
| STOMP `DISCONNECT` | Inbound channel/lifecycle | Ending the session and cleanup |
| Broker creates STOMP `MESSAGE` | Outbound channel | Delivery to authorized subscribers in the right room/user |
| App reads database when handling SEND | Service/repository | Permissions on actual resources and tenants |

**The transport layer is only the entryway.** A logged-in user may still lack permission to send messages, view private rooms, send company-wide notices, or receive another tenant's data.

## 3. Spring Components to Recognize

| API/Component | Stack | Role |
| --- | --- | --- |
| `HttpSecurity` and `SecurityFilterChain` | Spring Security Servlet | Protects HTTP handshake/SockJS transport requests |
| `@EnableWebSocketMessageBroker` | Spring Framework WebSocket STOMP | Enables STOMP message broker infrastructure |
| `StompEndpointRegistry` | Spring Framework | Registers HTTP/WebSocket endpoints such as `/ws` |
| `MessageBrokerRegistry` | Spring Framework | Application/broker/user destination prefixes |
| `@MessageMapping` | Spring Messaging | Handles inbound SEND directed to the application prefix |
| `SimpMessagingTemplate` | Spring Messaging | Application sends messages to the broker or a user |
| `clientInboundChannel` | Spring Messaging | Where messages **coming in from clients** are processed |
| `clientOutboundChannel` | Spring Messaging | Where messages going from the broker/application out to clients flow |
| `ChannelInterceptor` | Spring Messaging | Intercepts/transforms inbound messages; can perform custom auth |
| `@EnableWebSocketSecurity` | Spring Security Messaging | Enables authorization/security integration for STOMP |
| `AuthorizationManager<Message<?>>` | Spring Security Messaging | Makes authorization decisions for each inbound Message |
| `MessageMatcherDelegatingAuthorizationManager.Builder` | Spring Security Messaging | Routes policies by message type/destination |
| `SimpMessageType` | Spring Messaging | MESSAGE, SUBSCRIBE, CONNECT, DISCONNECT... |
| `StompHeaderAccessor` | Spring Messaging | Reads command/destination/user/session metadata |

### Do Not Confuse WebSocket STOMP with Raw WebSocket

Spring Security WebSocket messaging authorization in the official documentation integrates with **Spring Messaging/STOMP**. If an application uses raw `WebSocketHandler`, Jakarta WebSocket/JSR-356, Socket.IO, or a custom message protocol, **do not assume** `@EnableWebSocketSecurity` will automatically intercept every payload of those technologies. Raw WebSocket requires per-message checks tailored to its own architecture.

This lesson focuses on **Spring MVC/Servlet + STOMP-over-WebSocket**, matching the scope of `Spring Security — WebSocket Security`. A pure WebFlux application with `WebSocketHandler` cannot copy Servlet `HttpSecurity`/message broker configuration verbatim and expect it to work equivalently.

## 4. What Does the HTTP Handshake Authenticate?

The browser opens a connection:

```http
GET /ws HTTP/1.1
Host: app.example.test
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: <base64-client-key>
Origin: https://app.example.test
Cookie: SESSION=<session-cookie>
```

This is an **illustrative request**, not a complete HTTP snippet you can copy and send like a regular API call. The browser may automatically send cookies according to its cookie/origin policies; the server must still authenticate and validate the origin.

If the application uses a login session or HTTP authentication, Spring Security establishes the `Principal` on the HTTP request. According to Spring Framework, the WebSocket session can **inherit the authenticated user of the HTTP handshake**, so subsequent STOMP messages carry that user in Spring message headers.

HTTP security example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HandshakeHttpSecurity {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/ws", "/ws/**").authenticated()
                .anyRequest().denyAll()
            );
        return http.build();
    }
}
```

This is a **Servlet Spring Security application configuration**, requiring real login/session/HTTP authentication and a `/ws` endpoint. It only expresses **HTTP authorization**; it contains no `AuthorizationManager<Message<?>>`. Any request other than `/ws` will be denied in this chain unless the application adds appropriate rules.

### What Does a Successful Handshake Assert?

With the configuration above, it indicates that the request passed the **HTTP conditions** and the WebSocket handshake was valid at the protocol level. It does **not** automatically assert that:

- The caller has the `CHAT_USER`/`ADMIN` role for every STOMP destination.
- The caller has permission to `SUBSCRIBE` to `/topic/tenants/B`.
- The caller has permission to `SEND` to `/topic/system`.
- The JSON payload does not contain a forged sender.
- The user still holds membership when the stream runs 30 minutes later.
- The broker will filter every outbound message by ACL.

## 5. STOMP CONNECT Is a Separate Frame, Not the HTTP Handshake

After the WebSocket opens, the client may send:

```text
CONNECT
accept-version:1.2
heart-beat:10000,10000

^@
```

The server replies, if the STOMP connection is accepted:

```text
CONNECTED
version:1.2

^@
```

A CONNECT frame may include a CSRF token in native STOMP headers depending on the Spring Security configuration and auth model. **STOMP CONNECT is not an HTTP GET Upgrade** and is also **not an OAuth2 token exchange command**.

### Do STOMP login/passcode Headers Authenticate a Browser User?

Spring Framework explains that STOMP defines `login` and `passcode` headers originally intended for STOMP-over-TCP. However, with STOMP over WebSocket in the default configuration, Spring **does not automatically use those two headers to authenticate the user**, expecting instead that the user was already authenticated at the HTTP handshake and propagated in the WebSocket session.

Therefore, a client sending:

```text
CONNECT
login:alice
passcode:my-password

^@
```

**does not mean** Spring Security automatically verifies `alice` in a WebSocket application. If you want an authentication mechanism at STOMP CONNECT, you need a **trusted authentication ChannelInterceptor** that parses and validates tokens/credentials using a legitimate authentication system.

Never take `login`/`passcode` or `X-User-Id` from STOMP headers and attach them to a principal without verification.

## 6. SEND, SUBSCRIBE, and MESSAGE Have Different Meanings

| STOMP command / Spring type | Who initiates in typical scenarios? | Security Meaning |
| --- | --- | --- |
| `CONNECT` | Client | Declares the start of a STOMP session |
| `SUBSCRIBE` | Client | Requests to receive messages from a destination |
| `SEND`, typically mapped to inbound `SimpMessageType.MESSAGE` | Client | Sends a payload to the application/broker |
| `MESSAGE` outbound | Broker/application | Delivers payload to subscribers |
| `UNSUBSCRIBE` | Client | Stops a subscription |
| `DISCONNECT` | Client or lifecycle handling | Ends the session |
| `HEARTBEAT` | Both sides | Keeps the connection alive; does not represent a business action |

In `MessageMatcherDelegatingAuthorizationManager`, `simpMessageDestMatchers(...)` typically targets inbound `SimpMessageType.MESSAGE`, i.e., messages sent from a client to a destination. `simpSubscribeDestMatchers(...)` is the matcher specifically for SUBSCRIBE. `simpDestMatchers(...)` checks destinations **regardless of message type**.

**Common mistake:** granting `SUBSCRIBE /topic/system` unintentionally grants `SEND /topic/system` as well due to an overly broad matcher, allowing clients to spoof system notices.

## 7. /app, /topic, /queue, /user: Destinations Are Not HTTP URLs

A common STOMP configuration:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class MessagingTransportConfig
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry
            .addEndpoint("/ws")
            .setAllowedOrigins("https://app.example.test");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
    }
}
```

This is a **Spring Boot STOMP infrastructure class**: it requires `spring-boot-starter-websocket`, messaging dependencies, and an HTTP server. The domain `app.example.test` is only an example. Origin rules must match the exact allowed websites; do not copy `*` into production. This configuration does not automatically create controllers or chat resources.

### Meaning of the Prefixes

- `/ws`: **HTTP endpoint** for the handshake, *not* a STOMP destination for clients to SEND business messages.
- `/app/**`: clients send to application handlers, such as `@MessageMapping("/chat.send")`.
- `/topic/**`: broker destination commonly used for broadcast/many subscribers.
- `/queue/**`: broker destination typically used for point-to-point/queue semantics (depends on the broker).
- `/user/**`: Spring user-destination abstraction, translated to a user/session-specific destination such as `/user/queue/messages`.

An application can choose different prefixes, because these are **configuration values**, not fixed STOMP protocol paths. An external broker relay has a different topology and permission model from the simple in-memory broker.

### Example Table Based on the Configuration Above

| Path/Destination | Kind | Intended Effect |
| --- | --- | --- |
| `GET /ws` | HTTP handshake | Opens the transport connection |
| `SEND /app/chat.send` | STOMP message | Invokes `@MessageMapping("/chat.send")` |
| `SUBSCRIBE /topic/public` | STOMP subscription | Receives public broadcasts according to policy |
| `SUBSCRIBE /topic/rooms/42` | STOMP subscription | Receives room 42, requires membership/ACL check |
| `SUBSCRIBE /user/queue/messages` | STOMP subscription | Receives private user queue |
| `SEND /topic/system` | STOMP message | **Must reject client** if this is a server-only channel |
| `SUBSCRIBE /queue/**` | STOMP subscription | Should usually deny direct broker queues unless proven necessary |
| `SEND /user/**` | STOMP message | Should not allow impersonating sender/recipient by default |

**Security boundary:** the fact that a destination is recognized by the Spring broker **does not automatically mean a user is allowed to subscribe or send**. Broker routing and message authorization are two distinct responsibilities.

## 8. Which Messages Does Spring Security Protect?

The Spring Security documentation explicitly states that STOMP security integration **intercepts at `clientInboundChannel`**. It **does not attempt to secure all outgoing messages on `clientOutboundChannel`**, largely because of the overhead and typically high volume of outbound messages.

Therefore:

```text
Client SEND/SUBSCRIBE
      |
      v
clientInboundChannel
      |
      +--> Authentication/SecurityContext setup
      +--> AuthorizationChannelInterceptor
      |
      v
@MessageMapping / message broker
      |
      v
clientOutboundChannel
      |
      v
WebSocket client
```

**Important consequence:** subscriptions must be protected **before** registration; at the same time, application sources **must publish the right data to the right destination**. If a service publishes private data to `/topic/public`, an inbound subscription guard cannot turn that content into private data.

Revocation requirements must also be defined:

- When Alice subscribes to room A, permissions are checked.
- Later, an admin removes Alice from the room.
- An active subscription **is not automatically terminated by Spring Security based on the new ACL** merely because data permissions changed.
- If the business requires revocation within seconds, the application must design appropriate unsubscribe/disconnect/revalidation and routing mechanisms.

Do not describe WebSocket/STOMP message authorization as a firewall that automatically filters every outbound byte by user ACL.

## 9. @EnableWebSocketSecurity and AuthorizationManager<Message<?>>

Since Spring Security 5.8, Spring Security WebSocket authorization can use the `AuthorizationManager` API. Java Config pattern:

```java
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
            // CONNECT, DISCONNECT, HEARTBEAT... typically have no destination.
            .nullDestMatcher().authenticated()

            // Only inbound SEND to this application handler.
            .simpMessageDestMatchers("/app/chat.send")
                .hasAuthority("CHAT_SEND")

            // Authenticated users may receive a public-to-users system channel.
            .simpSubscribeDestMatchers("/topic/public")
                .authenticated()

            // User destination: disallow direct subscription to raw broker queues.
            .simpSubscribeDestMatchers("/user/queue/messages")
                .authenticated()

            // Block all inbound SEND/SUBSCRIBE not explicitly granted.
            .simpTypeMatchers(
                SimpMessageType.MESSAGE,
                SimpMessageType.SUBSCRIBE
            ).denyAll()

            // Block remaining message types if not matched above.
            .anyMessage().denyAll();

        return messages.build();
    }
}
```

**This is a Spring Security configuration class**, not standalone code runnable with `javac` because it requires Spring Framework/Messaging/Security dependencies and broker configuration. Together with `MessagingTransportConfig` in the previous section and HTTP security, it illustrates **three separate layers**.

Breakdown:

1. `@EnableWebSocketSecurity` enables integration that controls inbound messages.
2. `AuthorizationManager<Message<?>>` evaluates by message type/destination.
3. `nullDestMatcher().authenticated()` protects messages without a destination (including CONNECT and DISCONNECT depending on the pipeline). **Spring Security still enforces a CSRF requirement for CONNECT according to the corresponding configuration**.
4. `simpMessageDestMatchers("/app/chat.send")` targets inbound SEND/MESSAGE at the application destination; requires `CHAT_SEND`.
5. `simpSubscribeDestMatchers("/topic/public")` grants SUBSCRIBE, **not SEND** to `/topic/public`.
6. `/user/queue/messages` is a user destination; Spring translates it to a session/user-specific destination, but the application must still ensure the server sends data belonging to the corresponding user.
7. `simpTypeMatchers(MESSAGE,SUBSCRIBE).denyAll()` blocks SEND to `/topic/**` or SUBSCRIBE to undeclared rooms.
8. `anyMessage().denyAll()` ensures a fail-closed policy for unapproved message types.

**Note:** this example does not yet grant subscriptions to private rooms. Do not unconditionally add `.simpSubscribeDestMatchers("/topic/rooms/**").authenticated()`, because that only proves the user has an account, **not membership in the room**.

### Why Does Rule Order Matter?

Builder matchers are evaluated in registration order; specific rules must precede catch-all rules.

**Wrong:**

```java
messages
    .simpTypeMatchers(SimpMessageType.SUBSCRIBE).denyAll()
    .simpSubscribeDestMatchers("/topic/public").authenticated();
```

The overly broad first SUBSCRIBE rule causes public subscribe to be denied. Similarly, if a `simpDestMatchers("/**").permitAll()` rule appears before deny, many frames with a destination can bypass specific checks. Put default deny at the end.

### Do Not Apply HTTP Rules to STOMP Destinations

`http.authorizeHttpRequests(...requestMatchers("/topic/**")...)` only matches **HTTP URLs**, not STOMP destinations `/topic/**` inside a WebSocket connection. Do not assume HTTP's `anyRequest().denyAll()` after the handshake will stop a client from sending `SEND /topic/system`.

## 10. Organizing Permissions by STOMP Message Type and Destination

A permission matrix might look like this:

| Inbound frame | Destination | Required Permission | Outcome |
| --- | --- | --- | --- |
| CONNECT | none | Authenticated HTTP principal + CSRF/identity policy | Accept or reject |
| SEND | `/app/chat.send` | CHAT_SEND + room membership in service | Process if sufficient |
| SEND | `/topic/public` | Disallow direct client publishing | DENY |
| SEND | `/topic/system` | Server-only channel | DENY |
| SUBSCRIBE | `/topic/public` | Authenticated | ALLOW |
| SUBSCRIBE | `/topic/rooms/42` | Member of room 42 / matching tenant | ALLOW only if verified |
| SUBSCRIBE | `/topic/rooms/99` | No membership | DENY |
| SUBSCRIBE | `/user/queue/messages` | Authenticated + proper user routing | ALLOW |
| SUBSCRIBE | `/queue/internal` | Disallow raw broker subscription | DENY |
| SEND | `/app/admin.command` | Admin app action + data/context policy | Separate policy |
| SUBSCRIBE | `/app/chat.send` | Application handler is not a broadcast stream | DENY |
| UNSUBSCRIBE | no destination | Lifecycle policy | Allow if session matches |
| DISCONNECT | no destination | Idempotent cleanup | Per session policy |

An app may choose different CONNECT and disconnect rules; **do not use permitAll across all inbound messages** just to reduce test errors. Here, public means "for every authenticated user" — not anonymous callers. If an application allows anonymous public topics, it must design anonymous sessions, origin checks, abuse controls, and privacy separately.

## 11. Propagating Principal from HTTP Session to STOMP

For a Servlet app using session login:

```text
1. Alice logs in via HTTP -> SecurityContext holds user Alice
2. Browser GET /ws sends session cookie
3. SecurityFilterChain verifies session and Principal
4. Spring WebSocket binds Principal to session
5. Inbound STOMP Messages carry Alice's simpUser
6. Message authorization uses Authentication/GrantedAuthority
7. @MessageMapping can inject Principal to identify the sender
```

In the handler:

```java
import java.security.Principal;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {
    private final ChatService chatService;

    public ChatController(ChatService chatService) {
        this.chatService = chatService;
    }

    @MessageMapping("/chat.send")
    public void send(ChatInput input, Principal principal) {
        // Use the verified principal; do not trust client-supplied senderId.
        chatService.sendFromAuthenticatedUser(
            principal.getName(),
            input.roomId(),
            input.text()
        );
    }
}
```

This is a **component fragment**: `ChatService` and `ChatInput` are domain types that must be defined; input/size validation, rate limits, and room/tenant permission checks are needed in the service. `Principal.getName()` may be a username rather than a stable user ID; use a trusted identity mapper if the application has multiple issuers/tenants.

If a client sends `{"senderId":"admin", "text":"..."}` in the payload, the application **must not** trust `senderId` as the sender. Assign the sender from the verified `Principal`; if legitimate service impersonation exists, it must have a dedicated delegation workflow and audit trail.

## 12. Token-Based Authentication at STOMP CONNECT: Special Case

Applications that do not use cookie sessions, such as mobile clients with JWT or SPAs wanting token-only WebSockets, can face a limitation: the browser `WebSocket` API **does not allow setting arbitrary HTTP Authorization headers** on the native handshake like `fetch` does. The SockJS browser client also has request header limitations.

Spring Framework describes one approach: send the token in **STOMP CONNECT native headers** and verify it in a `ChannelInterceptor`:

```text
Client: WebSocket handshake (transport)
   -> STOMP CONNECT with Authorization: Bearer ...
   -> server interceptor validates JWT and sets authenticated user
   -> Spring Security message AuthorizationManager evaluates
```

This is a **different architecture from HTTP-session authentication**. You cannot simultaneously require `GET /ws` to be HTTP-authenticated with a JWT header that the browser cannot send, and expect the token in STOMP CONNECT to rescue the handshake. You must design the HTTP handshake policy to accept the transport according to the trust boundary, and then **block all business messages until the CONNECT token is verified**.

### ChannelInterceptor Authenticating CONNECT

Illustrative structure:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.security.core.Authentication;

public final class StompConnectAuthInterceptor
        implements ChannelInterceptor {

    private final TrustedStompTokenVerifier verifier;

    public StompConnectAuthInterceptor(TrustedStompTokenVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    public Message<?> preSend(
            Message<?> message, MessageChannel channel) {

        StompHeaderAccessor accessor =
            MessageHeaderAccessor.getAccessor(
                message, StompHeaderAccessor.class);

        if (accessor != null
                && StompCommand.CONNECT.equals(accessor.getCommand())) {

            String bearer = accessor.getFirstNativeHeader("Authorization");
            Authentication trusted = verifier.verifyBearer(bearer);

            if (trusted == null || !trusted.isAuthenticated()) {
                throw new org.springframework.security.access
                    .AccessDeniedException("STOMP authentication failed");
            }
            accessor.setUser(trusted);
        }

        return message;
    }
}
```

**This is a Spring component fragment**, requiring an application-implemented `TrustedStompTokenVerifier` that uses a real JWT decoder with issuer/audience/expiry validation, not runnable standalone code. In production, check token type, scopes, revoked accounts, principal mapping, and return errors without leaking credentials. If verification fails, do not let the frame proceed.

### Interceptor Ordering Is a Security Concern

Spring Framework explicitly notes that a custom authentication `ChannelInterceptor` must run **before** the Spring Security authorization interceptor on the inbound channel. A separate configuration can be registered with `@Order(Ordered.HIGHEST_PRECEDENCE + 99)` per Spring Framework guidance; integration tests must be run on the exact version to ensure `SecurityContextChannelInterceptor` and authorization see the verified principal.

Do not design an interceptor that "sets the user from token" after authorization; authorization would then see an anonymous/stale principal or reject incorrectly.

### Is a Public HTTP Handshake Safe?

If the `/ws` handshake is permitted for browsers to allow STOMP token auth, that is **not automatically a business authorization vulnerability** if:

- CONNECT requires a valid JWT and appropriate CSRF/origin policies.
- No business SEND/SUBSCRIBE is processed prior to authentication.
- Connection/handshake rate limits, timeouts, and resource caps are enforced.
- No alternate code path bypasses the inbound interceptor.
- `permitAll()` is not used for all message rules.

However, this policy increases the DoS/connection-exhaustion surface; if reliable authentication at the handshake is possible, it is usually simpler.

### Avoid Tokens in the Query String

URLs like `wss://.../ws?token=...` risk leaking tokens into access logs, tracing, browser history, referrers, or proxy logs depending on the environment. Do not choose query tokens just for convenience; if unavoidable, use extremely short-lived, single-use, tightly scoped credentials and log redaction, according to the threat model. With session cookies, SameSite/CSRF/origin policies are needed to defend against cross-site hijacking.

## 13. Same Origin, CORS, and WebSocket Are Different

A common misconception: browsers automatically enforce the Same Origin Policy on WebSockets just like `fetch`.

Spring Security emphasizes that **WebSockets are not automatically protected by the browser's Same Origin Policy in the same way as XMLHttpRequest/fetch**. A malicious website can attempt to open a WebSocket to the application's domain, and cookies may be sent by the browser according to the applicable cookie rules. This is the basis of **Cross-Site WebSocket Hijacking (CSWSH)**.

Defenses:

1. **Origin allowlist** on the STOMP handshake endpoint, permitting only authorized origins.
2. **CSRF token in STOMP CONNECT** via Spring Security WebSocket integration when using sessions/cookies.
3. Cookie `SameSite`, `Secure`, `HttpOnly`, and proper session management.
4. Authentication and authorization for CONNECT/SEND/SUBSCRIBE.
5. Do not mistake standard HTTP CORS policy for the complete WebSocket origin policy.
6. Do not use `setAllowedOrigins("*")` for sensitive endpoints.
7. Verify whether reverse proxies/gateways preserve and validate the real origin and TLS.

### CSRF at CONNECT

Spring Security documentation states that when using `@EnableWebSocketSecurity`, inbound STOMP `CONNECT` requires a CSRF token as a same-origin protection. The client can fetch the token from a protected HTTP endpoint, then send it as a native STOMP header on CONNECT.

Illustrative client example:

```javascript
const token = await obtainCsrfTokenFromTrustedHttpEndpoint();
const headers = {};
headers[token.headerName] = token.token;
stompClient.connect(headers, onConnected, onError);
```

This is **client pseudocode**; `obtainCsrfTokenFromTrustedHttpEndpoint` must be built with proper origin/session/auth; the exact STOMP connect API depends on the client library/version. The purpose is to show that the CSRF header is sent in **STOMP CONNECT**, not automatically in the HTTP Upgrade.

**Do not** assume disabling HTTP CSRF on `/ws/**` disables CSRF for STOMP CONNECT. Those are two separate enforcement points.

### SockJS

SockJS fallback may use multiple HTTP requests (including POST) for transport. Spring Security docs note cases where **HTTP CSRF may need to be relaxed on the exact SockJS connect path**, while keeping **STOMP CONNECT CSRF**; some fallbacks use iframes, requiring the `X-Frame-Options: SAMEORIGIN` security header if allowed.

Do not disable CSRF application-wide just to "make SockJS work." With `@EnableWebSocketSecurity`, the ability to configure/disable STOMP CONNECT CSRF varies by Spring Security version; official documentation in the 7.1 line still notes it is not directly configurable via the annotation, and provides manual configuration guidance when disabling is strictly required. Avoid recommending disabling CSRF without a serious same-origin/CSWSH analysis.

## 14. /topic Is Not Where Clients Should Freely SEND

A classic case:

```text
Server wants to broadcast:
  MESSAGE /topic/system -> "System maintenance at 2AM"

Authenticated WebSocket attacker sends:
  SEND /topic/system -> "Click malicious link now"
```

If the broker accepts SEND directly to `/topic/system`, an attacker can spoof system notices without going through `@MessageMapping` business checks.

Recommended Spring Security rule: **deny all client inbound MESSAGE frames targeting broker prefixes** `/topic/**`, `/queue/**`, except for extremely specific, explicitly secured exceptions.

Instead, the client sends:

```text
SEND /app/chat.send
{"roomId":"42","text":"Hello"}
```

`@MessageMapping("/chat.send")` receives the request, verifies sender/room membership/rate limit, constructs the server-side message, and then uses `SimpMessagingTemplate.convertAndSend("/topic/rooms/42", ...)` if authorized.

**Note:** `@MessageMapping` does not automatically protect against a client supplying a fake ownerId/roomId. It is a routing point; domain policy is required.

## 15. SUBSCRIBE to a Private Topic: Check Object-Level Permissions

A user in tenant A tries:

```text
SUBSCRIBE
id:sub-secret
destination:/topic/tenants/B/rooms/99

^@
```

A rule `simpSubscribeDestMatchers("/topic/**").authenticated()` only requires the user to have a valid Authentication. It **does not** know whether the user belongs to tenant B or room 99. That is a BOLA/IDOR flaw at the message subscription layer.

A policy like this is needed:

```text
ALLOW SUBSCRIBE /topic/tenants/{tenant}/rooms/{room} if
   authenticated principal
   AND verified membership(subject, tenant)
   AND room.tenantId == tenant
   AND active room membership / ACL
   AND room not deleted or locked
   AND subscription policy allows current context
```

For shared brokers, a single unauthorized SUBSCRIBE can leak **every subsequent message** on that topic, not just one HTTP response.

### Custom Authorization Manager

One approach is writing a custom `AuthorizationManager<Message<?>>` and attaching it to `simpSubscribeDestMatchers(...)`:

```java
@Bean
AuthorizationManager<Message<?>> privateRoomAuthorization(
        RoomSubscriptionPolicy policy) {

    return (authenticationSupplier, message) -> {
        Authentication auth = authenticationSupplier.get();

        SimpMessageHeaderAccessor accessor =
            MessageHeaderAccessor.getAccessor(
                message, SimpMessageHeaderAccessor.class);

        String destination = accessor == null
            ? null : accessor.getDestination();

        boolean allowed = auth != null
            && auth.isAuthenticated()
            && policy.canSubscribe(auth, destination);

        return new org.springframework.security.authorization
            .AuthorizationDecision(allowed);
    };
}
```

This is a **Spring configuration fragment**, requiring imports for `Message`, `Authentication`, `AuthorizationManager`, `SimpMessageHeaderAccessor`, and `RoomSubscriptionPolicy` as an application service. `policy.canSubscribe` must safely parse the destination, load the real room from the server, verify tenant/room membership, and explicitly deny when evidence is lacking. For Spring Security 7 APIs, `AuthorizationDecision` is a valid `AuthorizationResult` and `authorize(...)` is used; the code above relies on target typing of the corresponding interface and must be compiled against the actual dependency version.

Integrating into the builder:

```java
messages
    .simpSubscribeDestMatchers(
        "/topic/tenants/{tenant}/rooms/{roomId}"
    ).access(privateRoomAuthorization)
    .simpTypeMatchers(SimpMessageType.SUBSCRIBE).denyAll()
    .anyMessage().denyAll();
```

This is a **fragment** of the `messageAuthorizationManager` bean; do not write it as a conflicting bean alongside `@EnableWebSocketSecurity` without merging the rules. Verify actual destination extraction/version/path variables, and ensure the custom policy does not trust the tenant String from the destination as proof of membership.

### Blocking Database Access Inside the Manager

Servlet/STOMP inbound channels typically run on Spring Messaging's thread executor, but **that does not mean** you may perform unbounded heavy JDBC lookups on every SUBSCRIBE. Consider DB pools, timeouts, caching/revocation, bounded queues, and rate limits; when using non-blocking data sources, do not carelessly call `Mono.block()` inside the pipeline. `AuthorizationManager<Message<?>>` is a synchronous decision abstraction in this model; if the permission store only exposes reactive APIs, design a clear bridge/boundary rather than pretending the message AuthorizationManager is inherently reactive.

In a WebFlux raw WebSocket application, per-message protection works differently using Reactor operators; do not copy a Servlet Spring STOMP manager verbatim.

## 16. User Destinations and Avoiding Reading Another User's Queue

Spring Framework supports `/user/**` to map subscriptions to destinations specific to a user or session.

Example:

```text
Client Alice subscribes:
  /user/queue/messages

Server sends:
  convertAndSendToUser("alice", "/queue/messages", payload)

Spring routes to:
  an internal queue destination unique to Alice's session(s)
```

The exact internal destination name depends on the implementation and may include a session ID. **Do not** expose translated internal queue names as a public API where clients can arbitrarily SUBSCRIBE.

Common rules:

- Allow users to SUBSCRIBE to `/user/queue/messages` once authenticated.
- Deny direct client SUBSCRIBE to `/queue/**` barring reviewed exceptions.
- Disallow direct client SEND to `/user/**` unless backed by a business command policy.
- When using `convertAndSendToUser`, the recipient ID must be server-verified and context-appropriate.
- When a client has multiple sessions/tabs, understand multi-session delivery behavior and data-scoping requirements.

**Warning:** protecting user destination routing **does not protect the payload** if the application sends Bob's information to Alice's queue. The publisher/service must still verify the correct recipient, tenant, and data.

## 17. Why Is Outbound Not Automatically Checked by Spring Security?

According to Spring Security documentation, WebSocket message security does not secure `clientOutboundChannel` the way it intercepts inbound, largely for performance reasons.

Suppose user Alice has a currently allowed subscription to `/topic/rooms/42`. When an admin revokes Alice from the room, some new messages may still arrive on the old subscription if the system does not handle revocation. That does not contradict the fact that the initial inbound `SUBSCRIBE` was allowed: permissions **changed afterward**.

Strategies:

1. **Re-evaluate on subscribe**; suitable for relatively stable permissions and short sessions.
2. **Short-lived subscriptions / reconnect leases**; force periodic permission refreshes.
3. **Event-driven revocation**; when membership/ACL changes, actively unsubscribe/close related sessions.
4. **App-layer fanout per authorized recipient**; send only to users verified at publish time.
5. **Tenant/resource-partitioned topics** with appropriate broker ACLs when using an external broker.
6. **Data minimization**; avoid publishing private payloads to broad public topics.
7. **Invalidate cached permissions** when a user leaves a tenant/room.

Each option trades off latency, load, and consistency. Publish a revocation SLA (e.g., max 30 seconds) and **test on live connections**, not just new ones.

### A Vulnerability Can Still Occur Even When Inbound Guards Are Right

```text
Alice SUBSCRIBE /topic/public -> ALLOW
Server mistakenly publishes payroll data to /topic/public
Alice receives payroll data
```

Message authorization cannot save you if **the application publishes to the wrong destination**. Sensitive data requires user-/tenant-scoped publishing and proper output policies, not just subscription auth.

## 18. @MessageMapping Must Verify Business Actions

A STOMP SEND can trigger side effects: creating a chat message, changing order status, transferring money, sending invitations, approving tasks.

Application example:

```java
@Controller
public class RoomMessageController {
    private final RoomService rooms;
    private final SimpMessagingTemplate messaging;

    public RoomMessageController(
            RoomService rooms, SimpMessagingTemplate messaging) {
        this.rooms = rooms;
        this.messaging = messaging;
    }

    @MessageMapping("/rooms.post")
    public void post(RoomPostRequest request, Principal principal) {
        var actor = rooms.verifyAuthenticatedActor(principal);
        var room = rooms.requireWritableRoom(
            actor, request.tenantId(), request.roomId());

        var saved = rooms.saveMessage(
            room, actor, request.text());

        messaging.convertAndSend(
            "/topic/tenants/" + room.tenantId()
                + "/rooms/" + room.id(),
            saved.toClientDto());
    }
}
```

This is an **application fragment**: `RoomService`, `RoomPostRequest`, `RoomPostRequest.tenantId()`, and `saved.toClientDto()` are domain APIs to be implemented. `Principal` is verified by session/CONNECT auth; usernames should be mapped to stable subject IDs if needed. Input requires validation, length limits, and HTML/script injection protection depending on client rendering.

Proper workflow:

1. Allow inbound SEND to `/app/rooms.post` only via the message manager.
2. Verify principal/tenant membership/room permission in the **service**.
3. Load the real resource and check room state.
4. Write to the database within an appropriate transaction.
5. Only after success, publish to the destination for the right tenant/resource.
6. If exactly-once/idempotency or transaction boundaries with the message broker are needed, use an appropriate outbox/retry protocol.

Do not rely solely on `hasAuthority('CHAT_SEND')` to allow posting to **every** room. Functional permissions and resource-level entitlements must work together.

## 19. If a Message Has a "sender", Derive It from Principal

Client payload:

```json
{
  "senderId": "admin",
  "tenantId": "tenant-a",
  "roomId": "42",
  "text": "Message to send"
}
```

An attacker can alter `senderId` and `tenantId`. The server must never trust these fields as the basis for authorization.

Design:

```text
actorId = verified Principal / Authentication mapping
requestedTenantId = selector from payload/destination
room = DB lookup by requested room ID + verified tenant scope
ALLOW only if actor has active membership and SEND action
persist senderId=actorId (never senderId from client)
publish DTO with server-proven senderId
```

An unguessable UUID `roomId` still does not replace an object-level access check. Similarly, even if an attacker guesses an internal user destination, raw `/queue/**` subscriptions must be blocked rather than relying on hard-to-guess queue names.

## 20. HTTP CSRF and STOMP CONNECT CSRF Cannot Replace Each Other

With form/cookie sessions, HTTP CSRF protects state-changing HTTP requests. WebSocket handshakes typically use HTTP GET/Upgrade, yet the client may automatically attach cookies per browser policy.

Spring Security enforces CSRF on **inbound STOMP CONNECT** to mitigate cross-site WebSocket hijacking; the token resides in **STOMP headers**, not only HTTP request headers.

If using SockJS fallback transport with POST, the framework may require adjusting the HTTP CSRF matcher for **connect URLs**; however, do not disable HTTP CSRF across all business endpoints. When cross-origin WebSockets are needed, analyze origin policy, cookie SameSite, and CSRF explicitly. "CORS enabled" does not mean CSWSH is solved.

### How to Test CSRF

- Browser with valid origin, session, and valid STOMP CONNECT CSRF → STOMP connection succeeds.
- Browser with valid origin but missing/invalid CSRF → denied CONNECT when policy requires it.
- Origin not in allowlist → handshake rejected at transport layer.
- Attacker supplies fake STOMP login/passcode → does not become Alice.
- SockJS fallback → test transport-specific paths and narrowly scoped HTTP CSRF exceptions.
- Connection exists, but SEND lacks role → STOMP authorization still rejects.

Do not fix a "CONNECT denied" error by opening `permitAll()` for all inbound MESSAGEs.

## 21. Distinguishing Errors: HTTP 401/403 vs. STOMP ERROR and Connection Close

In HTTP REST, clients are used to seeing statuses `401`, `403`, `404`. After a WebSocket Upgrade, however, STOMP frames do not have an HTTP response code per SEND/SUBSCRIBE.

Observable signals:

| Stage | Outcome When Rejected | Difference |
| --- | --- | --- |
| HTTP handshake before upgrade | 401/403/3xx depending on entry point/origin | Still HTTP |
| STOMP CONNECT | ERROR frame or connection closed depending on config | Not a new HTTP 403 |
| STOMP SEND | ERROR/close/handling failure depending on broker/framework | Must test **no side effects** |
| STOMP SUBSCRIBE | Subscription rejected, possibly ERROR/close | Must test **no unauthorized messages received** |
| STOMP MESSAGE already emitted | Cannot "recall" bytes the client already received | Need revocation policy before emission |

Do not write tests that merely expect `.expectStatus().isForbidden()` after WebSocket upgrade to prove `SUBSCRIBE` is blocked. Use a STOMP client, capture ERROR frames, subscription state, broker outputs, and side effects.

Some clients auto-reconnect. If a token/CSRF is invalid, continuous reconnect loops can create load; implement backoff and do not log tokens. Separate authentication failures, policy denials, and broker infrastructure outages for observability.

## 22. Standalone Java 17: An OK Handshake Can Still Be Denied at STOMP

The following program **does not depend on Spring Security**; it simulates two separate decision points:

1. HTTP handshake: the request has an authenticated principal and an allowed origin.
2. STOMP message: checks type, destination, role, tenant/room membership, and denies direct SEND to the broker.

The goal is to prove that "having a session" is not equivalent to "being allowed to SUBSCRIBE/SEND to every destination."

Save the file `HandshakeVsStompAuthorizationDemo.java`:

```java
import java.util.Map;
import java.util.Set;

public class HandshakeVsStompAuthorizationDemo {

    enum Type { CONNECT, SEND, SUBSCRIBE, DISCONNECT }

    record User(
        String id,
        boolean authenticated,
        Set<String> roles,
        Set<String> roomKeys
    ) {}

    record Request(
        Type type,
        String destination,
        String tenant,
        String roomId
    ) {}

    static final Set<String> ALLOWED_ORIGINS =
        Set.of("https://app.example.test");

    static boolean handshake(User user, String origin) {
        return user != null && user.authenticated()
            && ALLOWED_ORIGINS.contains(origin);
    }

    static String decision(
            User user,
            boolean websocketEstablished,
            Request req) {

        if (!websocketEstablished || user == null
                || !user.authenticated() || req == null) {
            return "DENY";
        }

        if (req.type() == Type.CONNECT
                || req.type() == Type.DISCONNECT) {
            return "ALLOW";
        }

        if (req.destination() == null
                || req.destination().isBlank()) {
            return "DENY";
        }

        // Direct client SEND to broker destinations is forbidden.
        if (req.type() == Type.SEND
                && (req.destination().startsWith("/topic/")
                 || req.destination().startsWith("/queue/"))) {
            return "DENY";
        }

        if (req.type() == Type.SEND
                && "/app/chat.send".equals(req.destination())) {
            return user.roles().contains("CHAT_SEND")
                && allowedRoom(user, req) ? "ALLOW" : "DENY";
        }

        if (req.type() == Type.SUBSCRIBE
                && "/topic/public".equals(req.destination())) {
            return "ALLOW";
        }

        if (req.type() == Type.SUBSCRIBE
                && "/user/queue/messages".equals(req.destination())) {
            return "ALLOW";
        }

        if (req.type() == Type.SUBSCRIBE
                && req.destination().startsWith("/topic/tenants/")) {
            String expected =
                "/topic/tenants/" + req.tenant()
                    + "/rooms/" + req.roomId();

            return expected.equals(req.destination())
                && allowedRoom(user, req) ? "ALLOW" : "DENY";
        }

        return "DENY";
    }

    static boolean allowedRoom(User user, Request req) {
        if (req.tenant() == null || req.roomId() == null) {
            return false;
        }

        String roomKey = req.tenant() + "|" + req.roomId();
        return user.roomKeys().contains(roomKey);
    }

    static void show(
            String label, User user,
            boolean connected, Request request) {
        System.out.println(label + ": "
            + decision(user, connected, request));
    }

    public static void main(String[] args) {
        User alice = new User(
            "alice", true,
            Set.of("CHAT_SEND"),
            Set.of("tenant-a|42")
        );
        User bob = new User(
            "bob", true,
            Set.of(),
            Set.of("tenant-a|77")
        );
        User guest = new User(
            "guest", false,
            Set.of(), Set.of()
        );

        boolean aliceConnected =
            handshake(alice, "https://app.example.test");

        System.out.println("Alice HTTP handshake: "
            + (aliceConnected ? "ALLOW" : "DENY"));
        System.out.println("Wrong Origin handshake: "
            + (handshake(alice, "https://evil.example.test")
                ? "ALLOW" : "DENY"));
        System.out.println("Guest HTTP handshake: "
            + (handshake(guest, "https://app.example.test")
                ? "ALLOW" : "DENY"));

        show("Alice STOMP CONNECT",
            alice, aliceConnected,
            new Request(Type.CONNECT, null, null, null));
        show("Alice public SUBSCRIBE",
            alice, aliceConnected,
            new Request(Type.SUBSCRIBE,
                "/topic/public", null, null));
        show("Alice own room SUBSCRIBE",
            alice, aliceConnected,
            new Request(Type.SUBSCRIBE,
                "/topic/tenants/tenant-a/rooms/42",
                "tenant-a", "42"));
        show("Alice other room SUBSCRIBE",
            alice, aliceConnected,
            new Request(Type.SUBSCRIBE,
                "/topic/tenants/tenant-a/rooms/77",
                "tenant-a", "77"));
        show("Alice cross-tenant SUBSCRIBE",
            alice, aliceConnected,
            new Request(Type.SUBSCRIBE,
                "/topic/tenants/tenant-b/rooms/42",
                "tenant-b", "42"));
        show("Alice chat SEND",
            alice, aliceConnected,
            new Request(Type.SEND,
                "/app/chat.send", "tenant-a", "42"));
        show("Alice direct broker SEND",
            alice, aliceConnected,
            new Request(Type.SEND,
                "/topic/public", null, null));
        show("Alice private queue SUBSCRIBE",
            alice, aliceConnected,
            new Request(Type.SUBSCRIBE,
                "/queue/private", null, null));
        show("Bob chat SEND no role",
            bob, handshake(bob, "https://app.example.test"),
            new Request(Type.SEND,
                "/app/chat.send", "tenant-a", "77"));
        show("Disconnected Alice SUBSCRIBE",
            alice, false,
            new Request(Type.SUBSCRIBE,
                "/topic/public", null, null));
        show("Unknown destination",
            alice, aliceConnected,
            new Request(Type.SUBSCRIBE,
                "/topic/internal", null, null));
    }
}
```

Compile and run on JDK 17+:

```bash
javac HandshakeVsStompAuthorizationDemo.java
java HandshakeVsStompAuthorizationDemo
```

Exact stdout:

```text
Alice HTTP handshake: ALLOW
Wrong Origin handshake: DENY
Guest HTTP handshake: DENY
Alice STOMP CONNECT: ALLOW
Alice public SUBSCRIBE: ALLOW
Alice own room SUBSCRIBE: ALLOW
Alice other room SUBSCRIBE: DENY
Alice cross-tenant SUBSCRIBE: DENY
Alice chat SEND: ALLOW
Alice direct broker SEND: DENY
Alice private queue SUBSCRIBE: DENY
Bob chat SEND no role: DENY
Disconnected Alice SUBSCRIBE: DENY
Unknown destination: DENY
```

**Explanation:**

- Alice passes the HTTP handshake because she is authenticated and uses a valid origin.
- That only allows transport establishment; room 42/77 policies are still evaluated at STOMP.
- Bob has a valid HTTP session but lacks `CHAT_SEND`, so he cannot send chat messages.
- Direct SEND to `/topic/public` is denied even though Alice is allowed to subscribe to that channel.
- Subscription `/queue/private` is not whitelisted, so it is DENY.
- Tenant B cannot reuse tenant A's membership.
- Without an established WebSocket, there are no STOMP permissions in this model.

**Transparency limits:** this program does not open sockets, verify cookies/JWTs, check CSRF, parse STOMP frames, or invoke Spring Messaging. `roomKeys` and `roles` are "trusted" in-memory test fixtures. In production, membership, room state, and principals must come from verified sources, tokens/CSRF/origins must be checked by the real stack, and decisions must be enforced on `clientInboundChannel`. `Map` is imported to illustrate that broader mappings could be used, though the demo only needs `Set`; removing the `Map` import leaves the output unchanged.

## 23. Testing the HTTP Handshake: Both Allowed and Denied

An integration test should not merely open a WebSocket and assert "CONNECTED". At minimum, test:

| Handshake scenario | Expectation |
| --- | --- |
| Alice has a valid session and allowed origin | Upgrade/transport succeeds |
| No session for an endpoint requiring authenticated | 401/redirect/deny per entry point |
| Invalid/expired session | Does not create an authorized session |
| Origin from a website not in allowlist | Connection rejected |
| Session A cookie used for tenant B violating policy | Disallow switching tenants solely via URL |
| Reverse proxy strips/rewrites origin or upgrade headers | Policy remains correct after deploy |
| SockJS fallback using POST | HTTP/CSRF policy scoped to the right endpoint, not app-wide |
| Unauthenticated browser sending STOMP headers | Cannot bypass HTTP handshake if policy forbids it |
| JWT in query string | No token leak in logs/traces if architecture permits |
| Handshake flood/concurrent limits | Does not exhaust connection/thread pool |

With Spring Boot, a STOMP test can use `WebSocketStompClient` / `SockJsClient` connecting to a running server. `MockMvc` is great for HTTP, but does not replace a **WebSocket Upgrade + STOMP exchange** test on the wire. If using session authentication, the right user cookie/CSRF is required; if using STOMP JWT authentication, interceptor order must be tested separately.

## 24. Testing Message Authorization: Capture Frames and Side Effects

Minimum matrix:

| Caller | STOMP type | Destination | Expectation |
| --- | --- | --- | --- |
| Alice | CONNECT | none | Allowed if identity/CSRF policy is valid |
| Anonymous | CONNECT | none | Blocked per policy |
| Alice | SEND | `/app/chat.send` | Allowed only with role and room membership |
| Alice | SEND | `/topic/public` | DENY |
| Alice | SEND | `/topic/system` | DENY |
| Alice | SUBSCRIBE | `/topic/public` | ALLOW per policy |
| Alice | SUBSCRIBE | `/topic/tenants/A/rooms/42` | ALLOW if member of room |
| Alice | SUBSCRIBE | `/topic/tenants/B/rooms/42` | DENY without membership in B |
| Alice | SUBSCRIBE | `/queue/admin` | DENY |
| Alice | SUBSCRIBE | `/user/queue/messages` | ALLOW, receives right user payload |
| Bob | SUBSCRIBE | `/topic/rooms/42` | DENY if not a member |
| Bob | SEND | `/app/admin.command` | DENY if missing admin grant |
| Alice | SEND | `/app/chat.send` with `senderId=admin` | Server still records actor Alice |
| Alice | SUBSCRIBE | Unknown destination | DENY |
| Alice after revoke | New subscribe | DENY |
| Alice after revoke | Live subscription | Revoke/cancel/delivery policy meets SLA |

### Required Assertions

- Rejected inbound SEND **neither writes to the DB nor publishes a message**.
- Rejected inbound SUBSCRIBE **receives no private messages** even while the broker is broadcasting.
- User A does not receive messages sent via `convertAndSendToUser("bob", ...)`.
- Tokens/CSRF are not logged in error payloads.
- After membership changes, test both **new connections and live connections**.
- Test whether client auto-reconnect/re-subscribe is re-checked.
- If the broker relay has its own ACLs, test that the broker configuration cannot be bypassed either.

### Do Not Assert Only HTTP Status

A STOMP ERROR frame or connection close after Upgrade cannot be verified with HTTP `expectStatus().isForbidden()` on the same socket. Use STOMP session handlers to observe frames/receipts/errors, and a fake broker/subscriber to confirm data does not reach the client.

## 25. AuthorizationManager Unit Tests Need Both Type and Destination

For message manager unit tests, you can construct a Message using Spring Messaging:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.support.MessageBuilder;

SimpMessageHeaderAccessor headers =
    SimpMessageHeaderAccessor.create(SimpMessageType.SUBSCRIBE);
headers.setDestination("/topic/public");
headers.setLeaveMutable(true);

Message<byte[]> subscribe = MessageBuilder.createMessage(
    new byte[0], headers.getMessageHeaders()
);
```

This is a **JUnit test fixture fragment**, not a standalone program. The test must supply an `Authentication` with appropriate authorities and invoke `AuthorizationManager<Message<?>>` using the Spring Security version's API (for example, `authorize(() -> auth, subscribe)` in newer lines).

Minimum tests:

1. `MESSAGE /topic/public` → DENY.
2. `SUBSCRIBE /topic/public` → ALLOW for authenticated user.
3. `SUBSCRIBE /queue/internal` → DENY.
4. `MESSAGE /app/chat.send` → ALLOW only with `CHAT_SEND`.
5. Unknown type/destination → DENY.
6. Null destination CONNECT → requires authenticated + separate CSRF validation.
7. For private room matchers, verify each path variable/tenant is checked.

A unit test on `AuthorizationManager` **does not test** the handshake, STOMP frame decoding, CSRF token handshake/session propagation, or outbound delivery. Only an integration test via a WebSocket STOMP client covers the full path.

## 26. Broker Relays and External Message Brokers Do Not Remove Application Responsibility

An application may use an in-memory simple broker or relay to RabbitMQ/ActiveMQ/an external STOMP broker.

With a relay:

```text
Client STOMP WebSocket
       |
       v
Spring clientInboundChannel -> security checks
       |
       v
STOMP broker relay
       |
       v
External broker
       |
       v
Outbound data to client subscriptions
```

Points to evaluate:

- Does the broker see the client's identity or only service-level credentials?
- Can clients connect **directly** to the external broker bypassing Spring?
- Do broker destinations have per-tenant/per-user ACLs?
- Can someone publish directly to `/topic/tenants/A` without going through service policy?
- Does broker relay reconnect recreate subscriptions using stale identities/grants?
- Do user destination transformations work correctly when scaling across multiple Spring nodes?
- Does the application filter sensitive payloads before fanout?

**Do not** use a single privileged service credential for the broker and then assume every subscriber is authorized to read every topic. The Spring inbound guard applies only on the path **passing through Spring**; if clients have direct ports to the broker, protection is required at the broker/network layer.

## 27. Performance, Resource Limits, and Rate Limiting

WebSockets are long-lived, so cost is not just a single HTTP request:

- Each socket consumes memory, heartbeat timers, and session metadata.
- Each SUBSCRIBE allocates broker state.
- Each SEND can trigger database writes, validation, and fanout.
- Each private subscription needs membership/ACL checks.
- Each broadcast can multiply into thousands of outbound messages.
- Clients can send excessive frames or large payloads to cause DoS.

Recommended controls:

1. Limit connections per IP/user/tenant and subscriptions per session.
2. Cap frame/message size, send buffers, and timeouts.
3. Rate limit SEND per user/room/action.
4. Use bounded thread pools/queues for the inbound channel and DB connection pool.
5. Set reasonable timeouts for ACL/membership queries; **do not fail open on timeout**.
6. Avoid synchronous N-time ACL lookups for the same message when scoped caching applies.
7. Include subject, tenant, destination/resource, action, and ACL/policy version in cache keys.
8. Invalidate permission caches upon revocation; do not keep positive decisions cached too long.
9. Limit the number of destinations an attacker can probe/request.
10. Test backpressure and slow clients on the outbound path according to broker/framework behavior.

**Performance is not a reason to open `/topic/**` with permitAll**. If membership checks are too expensive, optimize queries, materialized grants, or subscription leases rather than removing authorization checks.

## 28. Common Mistakes

| Mistake | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| Protecting only `GET /ws` | All STOMP SEND/SUBSCRIBE frames may lack policy | Add a message AuthorizationManager |
| Thinking HTTP `anyRequest().denyAll()` blocks `/topic/**` | STOMP destinations are not URLs | Use Spring Messaging security matchers |
| Using `simpDestMatchers("/topic/**").authenticated()` | May allow SEND to the broker as well | Use `simpSubscribeDestMatchers` and deny SEND |
| Allowing clients to SEND to `/topic/system` | Spoofing server announcements | Send only to secured `/app/**` handlers |
| Allowing SUBSCRIBE `/topic/rooms/**` just because authenticated | BOLA/room data leak | Check tenant/room membership |
| Allowing SUBSCRIBE to raw `/queue/**` | Can expose other users' queues | Use `/user/queue/**` and deny raw queues |
| Trusting `senderId` from JSON | Sender spoofing | Use the verified Principal |
| Thinking STOMP `login`/`passcode` auto-authenticates | Spring WebSocket does not do this by default | HTTP auth or custom authenticated CONNECT interceptor |
| Attaching user from STOMP CONNECT token before verification | Identity spoofing | Trusted JWT decoder + proper interceptor order |
| Requiring an HTTP JWT header from browser WebSockets that cannot send it | Handshake fails, leading to unsafe workarounds | Choose browser-compatible auth flow, separate transport/CONNECT |
| Putting tokens in URL/query strings | Leaks via logs/proxies | Avoid; if required, use short-lived tokens and redaction |
| `setAllowedOrigins("*")` with session cookies | Cross-site connection/hijack | Strict origin allowlist + CSRF |
| Disabling CSRF app-wide to fix SockJS | CSRF on HTTP business endpoints | Narrowly adjust only the required transport path |
| Using `@EnableWebSocketSecurity` and thinking CSRF disappears | CONNECT has a CSRF requirement | Supply token in the right STOMP header |
| Testing only HTTP 101 | Unknown whether message-level policy works | Test STOMP SEND/SUBSCRIBE/ERROR |
| Testing only roles, not resource IDs | Cross-tenant/room access | Object-level policy |
| Failing to prevent outbound private data published to wrong topic | Inbound guard cannot prevent data leaks | Destination/data selection in publisher |
| Thinking Spring Security intercepts all outbound messages | Per docs, primarily inbound only | Guard subscriptions, explicit revoke policy |
| Not handling membership revocation on live sockets | Stale subscriptions continue receiving | Disconnect/unsubscribe/lease/re-eval |
| External broker has a public port | Bypasses Spring inbound security | Broker ACL/network isolation |
| Using `@MessageMapping` as an implicit authorization proxy | Controller routing does not replace business policy | Service/DB checks |
| Writing to DB before post-checks | Side effect already occurred | Preauthorize + transactional conditional writes |
| Putting an allow-all matcher before deny | Subsequent security rules are never evaluated | Specific-before-general, default deny |
| Using `AbstractSecurityWebSocketMessageBrokerConfigurer` on Spring Security 7 | Legacy API removed | `@EnableWebSocketSecurity` + AuthorizationManager |
| Logging raw STOMP headers | May contain JWT/CSRF/PII | Log redaction, limited audit |
| Not checking HTTP principal/STOMP token mismatch | Session identity confusion | Explicit identity binding/trust policy |
| Not testing SockJS fallback/Origin | Cross-origin vulnerabilities | End-to-end protocol tests |

## 29. Diagnostic Procedure When CONNECT Succeeds but SEND/SUBSCRIBE Fails

1. Identify whether the client uses **native WebSocket**, SockJS, or a broker relay.
2. Check whether the HTTP handshake goes through the right `SecurityFilterChain`.
3. Check the 101/fallback status response and Origin policy.
4. Inspect the authenticated user on the HTTP request/session.
5. Confirm `@EnableWebSocketMessageBroker` registered `/ws`.
6. Check `@EnableWebSocketSecurity` and the `AuthorizationManager<Message<?>>` bean.
7. If using STOMP JWT, confirm the token is verified and the interceptor runs **before** authorization.
8. Check the CONNECT CSRF token in STOMP native headers.
9. Confirm the inbound message type is MESSAGE or SUBSCRIBE, without confusing it with outbound MESSAGE.
10. Check whether the destination Spring receives matches the broker/application prefixes.
11. Check matcher ordering in `MessageMatcherDelegatingAuthorizationManager`.
12. Check the authenticated principal's actual authorities per the role-mapping system.
13. For private rooms, check membership, tenant, and room state from the database.
14. Check whether the `@MessageMapping` handler processes SEND.
15. If SUBSCRIBE is allowed but receives no data, check the publisher destination and user-destination transformation.
16. If ERROR occurs after Upgrade, do not look for HTTP status codes like REST.
17. Test with user A and user B from different tenants to verify no data leakage.
18. Verify logs/metrics are redacted and do not expose tokens/CSRF.
19. If permissions are revoked, verify whether existing sockets are closed/unsubscribed.
20. Add a regression test for the exact message type + destination + principal + context that failed.

**Important:** if a test only verifies "can connect" without sending any STOMP frames, it only proves the transport layer, not the message-layer policies.

## 30. Pre-Deployment STOMP Security Review Checklist

1. Does the HTTP handshake authenticate the caller properly, or is there a clear STOMP CONNECT auth architecture?
2. Can the browser send the expected credential type, or does the backend expect an unsupported Authorization header?
3. Is the Origin allowlist properly configured and tested cross-origin?
4. Does STOMP CONNECT verify CSRF/identity per current policy?
5. Are STOMP `login`/`passcode` mistaken for user authentication?
6. Is there an `AuthorizationManager<Message<?>>` bean with `@EnableWebSocketSecurity`?
7. Do matchers distinguish `MESSAGE`/SEND from `SUBSCRIBE`?
8. Are clients blocked from direct SEND to `/topic/**` or `/queue/**`?
9. Are clients blocked from subscribing to raw `/queue/**`?
10. Is `/user/queue/**` routed to the right user/session?
11. Do private rooms enforce membership checks against real tenant and room IDs?
12. Are there separate authorities for user SEND, admin commands, and sensitive topic SUBSCRIBEs?
13. Are unknown destinations denied by default (`denyAll`)?
14. Are payload sender/tenant re-verified rather than taken straight from client JSON?
15. Do services handling `@MessageMapping` protect mutations and domain resources?
16. Could a publisher/broker accidentally publish private data to a public topic?
17. Is there a process to cancel/refresh permissions on live sessions after revocation?
18. Is SockJS HTTP POST fallback designed with a narrow CSRF exception?
19. Does an external broker expose public endpoints/ACLs that let clients bypass inbound security?
20. Are subscription count, frame size, rate, memory, and timeouts bounded?
21. Are handshake deny, STOMP CONNECT deny, SEND deny, and SUBSCRIBE deny tested separately?
22. Are multiple concurrent users/tenants and user destinations tested?
23. Are origin spoofing, token replay/expiry, JWT claims, and role mapping tested?
24. Are decisions audited without logging raw JWT/CSRF/passwords?
25. When upgrading Spring Security, have removed legacy APIs and compile/config tests been checked?

**Conclusion:** Protecting WebSocket/STOMP in Spring Security involves **at least two independent boundaries**. HTTP `SecurityFilterChain` protects the handshake and establishes initial identity; `@EnableWebSocketSecurity` along with `AuthorizationManager<Message<?>>` protects **inbound STOMP message types/destinations**. An authenticated handshake does not automatically grant SEND/SUBSCRIBE permissions, and an initially permitted SUBSCRIBE does not guarantee permissions remain valid when ACLs change. Block direct client SEND to the broker, verify room/user/tenant in services, enforce Origin/CSRF, manage subscription revocation, and test end-to-end across both transport and messages.

## Official References

- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html): HTTP principal propagation, `@EnableWebSocketSecurity`, `AuthorizationManager<Message<?>>`, inbound-only enforcement, SEND/SUBSCRIBE destination rules, Same Origin/CSRF/SockJS.
- [Spring Security API — EnableWebSocketSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/socket/EnableWebSocketSecurity.html): annotation enabling authorization manager integration for messages.
- [Spring Security API — MessageMatcherDelegatingAuthorizationManager.Builder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.html): `simpMessageDestMatchers`, `simpSubscribeDestMatchers`, `simpDestMatchers`, `simpTypeMatchers`, `nullDestMatcher`, and `anyMessage`.
- [Spring Framework — STOMP Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html): HTTP identity propagation and default STOMP login/passcode behavior not authenticating browser users.
- [Spring Framework — Token Authentication for STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html): tokens in STOMP CONNECT, `ChannelInterceptor`, interceptor ordering.
- [Spring Framework — Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html): `/ws` endpoint, application destination prefixes, simple broker/broker relay.
- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html): `/user/**`, session-specific destination translation.
- [Spring Framework — Message Flow](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): inbound/broker/outbound channels and messaging pipeline.
- [Spring Framework — STOMP Interception](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/interceptors.html): `ChannelInterceptor` and lifecycle considerations.
- [OWASP — WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html): CSWSH, origin validation, per-message authentication/authorization, logging, DoS/rate limits.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, and object-level authorization.
