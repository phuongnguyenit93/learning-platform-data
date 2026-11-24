# @EnableWebSocketSecurity and AuthorizationManager<Message<?>>

> **Spring Security – authorization · Message Authorization.** This Knowledge article guides you through securing **Spring Messaging STOMP over WebSocket** using `@EnableWebSocketSecurity` and an `AuthorizationManager<Message<?>>` bean. The topic focuses on **`clientInboundChannel`**: distinguishing `CONNECT`/`SUBSCRIBE`/`SEND` frames, `/app`, `/topic`, `/queue`, and `/user` destinations, authentication from the HTTP handshake, CSRF at STOMP CONNECT, message-type matchers, rule ordering, deny-by-default, and policy testing. The Spring examples use **Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x**, Servlet + Spring WebSocket Message Broker. The pure Java 17 section at the end is a standalone policy simulation, **not** a WebSocket server.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why a WebSocket that has **upgraded from HTTP** still needs a separate authorization layer for **every STOMP frame** arriving from a client.
2. Understand how `@EnableWebSocketSecurity` integrates Spring Security Messaging and picks up the `AuthorizationManager<Message<?>>` bean from the Spring Context.
3. Use `MessageMatcherDelegatingAuthorizationManager.Builder`, `simpMessageDestMatchers`, `simpSubscribeDestMatchers`, `simpTypeMatchers`, `nullDestMatcher`, and `anyMessage` accurately.
4. Distinguish a **STOMP MESSAGE** (sent out by the server/broker) from Spring's `SimpMessageType.MESSAGE` value for an inbound client **SEND**.
5. Prevent clients from sending `SEND` directly to `/topic/**` or `/queue/**` to spoof server notifications.
6. Restrict `SUBSCRIBE` to permitted topics/queues, especially avoiding opening wildcard `/queue/**` which can leak other users' messages.
7. Obtain identity from the authenticated `Principal` in the HTTP handshake or controlled STOMP authentication; never trust `from`, `user`, or roles written by the client in payloads or headers.
8. Protect STOMP `CONNECT` with a CSRF token and Origin/Same-Origin policy, without assuming WebSockets automatically inherit browser Same-Origin protection like HTTP AJAX.
9. Write a Spring Boot/STOMP demo with an inbound message policy, a controller sending valid notifications, and a dedicated error queue.
10. Unit test `AuthorizationManager<Message<?>>` using `MessageBuilder` + `SimpMessageHeaderAccessor`, distinguishing real authentication/anonymous, USER/ADMIN roles, MESSAGE/SUBSCRIBE, and undeclared routes.
11. Recognize scenarios where an object-level/tenant-level policy must be added to a custom `AuthorizationManager<MessageAuthorizationContext<?>>` rather than checking only general roles.
12. Identify the limit of inbound security: outgoing messages are not automatically checked; if a client subscribes to the wrong scope, sensitive content may already be exposed.
13. Build an integration test matrix covering handshake, CSRF, broker routing, session identity, revocation, and resource/tenant boundaries.
14. Run a standalone Java 17 example with exact stdout to self-evaluate a deny-by-default policy.

## 2. STOMP Architecture on Spring WebSocket

A WebSocket connection is merely a bidirectional transport channel. STOMP creates a message-based protocol running inside that channel: a client can send `CONNECT`, `SUBSCRIBE`, `SEND`, and `DISCONNECT` frames; the server/broker can emit `MESSAGE` and session-management frames.

~~~text
Browser / STOMP client
   |
   | HTTP GET /ws, Upgrade: websocket
   | HTTP authentication + Origin policy
   v
WebSocket session, bound Principal
   |
   | STOMP CONNECT [CSRF in native STOMP header]
   | STOMP SUBSCRIBE /topic/announcements
   | STOMP SEND /app/chat.send
   v
Spring clientInboundChannel
   |
   +-- SecurityContextChannelInterceptor
   +-- AuthorizationChannelInterceptor
   |      AuthorizationManager<Message<?>>
   |       - type?
   |       - destination?
   |       - authenticated Principal/authorities?
   |       - allowed to SEND/SUBSCRIBE?
   |
   +-- on MESSAGE /app/* --> @MessageMapping controller
   |                             |
   |                             v
   |                        application service
   |                             |
   |                        SimpMessagingTemplate
   |                             |
   +--------------------------> broker
                                 |
                                 v
                         clientOutboundChannel
                                 |
                                 v
                       subscribed client sessions
~~~

**Key point:** Spring Security WebSocket authorization in this configuration checks **`clientInboundChannel`**, not every frame on `clientOutboundChannel` automatically. Therefore, you must protect **`SUBSCRIBE`** to the right destination before a client can receive data; do not wait until the server has already broadcast and then try to filter sensitive content. If messages are routed through an external broker relay, broker security, relay identity, and routing must also be evaluated.

### 2.1. Destinations Have Multiple Layers of Meaning

| String | Typically Used For | Who Sends / Receives? |
| --- | --- | --- |
| `/ws` | HTTP WebSocket handshake URL | Browser/client connects here; not a STOMP destination |
| `/app/chat.send` | Client sends data to an application handler | Inbound `SEND`; Spring strips the `/app` prefix to find `@MessageMapping("/chat.send")` |
| `/topic/announcements` | Broker broadcast notification | Client `SUBSCRIBE`, application/server `convertAndSend` |
| `/topic/admin` | Admin-only broker stream | Only ADMIN clients may subscribe; clients cannot SEND directly |
| `/queue/**` | Queue-like broker destinations | Should not allow wildcard client subscriptions |
| `/user/queue/errors` | Client subscribes to a personal user destination | Spring resolves this to a queue scoped to the session/user |
| `/user/{username}/queue/x` | App sends to a specific user (server-side) | Via `convertAndSendToUser`, not a right for clients to pick another user |

**Note:** `/topic` and `/queue` are conventions when using the simple broker; they do not automatically make every message secure. A destination string does not prove the principal has access. For multi-tenancy, `/topic/tenant/alpha` requires an alpha membership check, not merely a `/topic/**` matcher.

### 2.2. MESSAGE and SUBSCRIBE Are Two Separate Permissions

Spring's `SimpMessageType.MESSAGE` typically describes an inbound message with a payload, corresponding to a client STOMP `SEND`; `SimpMessageType.SUBSCRIBE` describes a client subscribing to receive messages. The same destination can be evaluated differently depending on the type.

For example, a USER client:
- `SUBSCRIBE /topic/announcements`: allowed to receive announcements.
- `SEND /topic/announcements`: **deny** so clients cannot spoof server notifications.
- `SEND /app/chat.send`: allowed to invoke the controller handler.
- `SUBSCRIBE /app/chat.send`: **deny** because this is not a broadcast channel.
- `SUBSCRIBE /queue/user/private`: **deny**, even though the string looks like a user queue.

Do not write `simpDestMatchers("/topic/**").authenticated()` if the goal is only to allow SUBSCRIBE: that matcher **does not restrict by MESSAGE/SUBSCRIBE type** and can allow SEND to the broker prefix.

## 3. @EnableWebSocketSecurity and AuthorizationManager<Message<?>>

Since Spring Security 5.8, the new configuration approach is based on `AuthorizationManager`; in Spring Security 6.5, use the annotation:

~~~java
@Configuration
@EnableWebSocketSecurity
class SocketMessageSecurity {
    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
                .simpSubscribeDestMatchers("/topic/announcements")
                    .hasRole("USER")
                .simpMessageDestMatchers("/app/chat.send")
                    .hasRole("USER")
                .simpTypeMatchers(
                    SimpMessageType.MESSAGE,
                    SimpMessageType.SUBSCRIBE)
                    .denyAll()
                .nullDestMatcher().authenticated()
                .anyMessage().denyAll();

        return messages.build();
    }
}
~~~

This is an excerpt from a configuration class; imports and the full application are in Section 6. The `AuthorizationManager<Message<?>>` bean is used by Spring Security to check messages on the inbound channel. The generic `Message<?>` is Spring Messaging's `org.springframework.messaging.Message<?>`, not `javax.websocket.Message` and not `HttpServletRequest`.

### 3.1. The Builder and Matcher Order

`MessageMatcherDelegatingAuthorizationManager.Builder` evaluates rules in declaration order; a message is handled by the first matching rule. Therefore, go from **specific exceptions → general rules → deny**.

| Matcher | Based On | Notes |
| --- | --- | --- |
| `simpMessageDestMatchers("/app/chat.send")` | Type MESSAGE + destination | Specifically for inbound SEND |
| `simpSubscribeDestMatchers("/topic/announcements")` | Type SUBSCRIBE + destination | Specifically for subscribing to listen |
| `simpDestMatchers("/app/**")` | Destination, **regardless of type** | Easily overly broad if type is not checked |
| `simpTypeMatchers(MESSAGE,SUBSCRIBE)` | Message type | Denies unmatched data frames |
| `nullDestMatcher()` | Null destination | CONNECT/UNSUBSCRIBE/DISCONNECT usually have no dest; does not mean CONNECT only |
| `anyMessage()` | All remaining messages | Always `denyAll()` in a strict policy |
| `matchers(customMatcher)` | Custom defined | Use when non-standard rules are needed; precedence must be tested |

**Why place `simpTypeMatchers(MESSAGE,SUBSCRIBE).denyAll()` before `nullDestMatcher().authenticated()`?** Because `nullDestMatcher` only checks whether the destination is null, a malformed frame of type MESSAGE that lacks a destination could match it if not blocked beforehand. A strict rule handles all invalid SEND/SUBSCRIBE frames before allowing control frames that have no destination. Some examples in documentation put `nullDestMatcher` first; when building a defensive policy for a real application, testing malformed frames helps decide a safer order.

### 3.2. How AuthorizationManager Receives Authentication

The generic `AuthorizationManager<T>` interface evaluates a secured object using a `Supplier<Authentication>`:

~~~java
// Spring Security 6.5 conceptual signature:
AuthorizationDecision check(
        Supplier<Authentication> authentication,
        Message<?> message);
~~~

In Spring Security 6.5, `check` may be marked deprecated in favor of `authorize` returning `AuthorizationResult`, but it remains available in the 6.5 branch and is used for illustration/unit tests. When upgrading to 7.x, check the actual API signature and update the test method accordingly. Do not mistakenly assign `AuthorizationManager<MethodInvocation>` (method security) or `ReactiveAuthorizationManager<AuthorizationContext>` (WebFlux HTTP) for inbound STOMP messaging.

### 3.3. GRANT/DENY/ABSTAIN

- `AuthorizationDecision(true)`: rule permits the message.
- `AuthorizationDecision(false)`: rule denies it.
- `null` from a manager: may represent **abstain** (no decision). Do not treat null as true.
- Exception from a custom manager: authorization/data-source check failure, not a path to permit.
- With deny-by-default, both a miss and an error must **prevent the protected event from running**; place `anyMessage().denyAll()` so unmatched messages do not slip through.

A custom `AuthorizationManager` can cause unintended side effects if it queries a DB inside `check`. Use a trusted data source, bounds/timeouts, actor/tenant/topic-scoped caching, and auditing; never use a client-supplied boolean in native headers as the result.

## 4. STOMP Authentication Starts Before Authorization

### 4.1. HTTP Handshake Provides the Principal

Under the default Spring WebSocket/Spring Security flow, the `Principal` of the authenticated HTTP request during the WebSocket handshake can be bound to the WebSocket session and subsequent STOMP messages. To protect `/ws`:
- The HTTP `SecurityFilterChain` requires authentication.
- Same-origin/cookie/session and HTTPS/WSS must be configured.
- If using Spring Security HTTP Session, authentication from the session is reused after the upgrade.
- For non-browser clients using HTTP Basic in demos, Basic must be sent on the **HTTP handshake**, rather than arbitrarily treating STOMP `login/passcode` as Spring Security–verified credentials.

**Do not trust client-supplied headers:**

~~~text
CONNECT
login:admin
passcode:topsecret
x-user:alice
x-roles:ROLE_ADMIN
~~~

Spring does not automatically treat these native STOMP headers as a verified Spring Security `Authentication`. If the architecture needs to authenticate a bearer token in STOMP CONNECT (common with SPAs), you must build a `ChannelInterceptor` that verifies the token before authorization, sets the Principal via `StompHeaderAccessor#setUser(...)` per framework contract, and validates interceptor ordering, issuer/audience/expiry, and token rotation policy. Do not merely Base64-decode a JWT payload and set `ROLE_ADMIN`.

### 4.2. Spring's Role Prefix Still Applies

`hasRole("USER")` targets authority `ROLE_USER` by default; `hasRole("ADMIN")` targets `ROLE_ADMIN`. If a Spring Resource Server JWT grants `SCOPE_chat.write` rather than `ROLE_USER`, `hasRole("USER")` will deny. You can write `hasAuthority("SCOPE_chat.write")` or use a reviewed converter; do not map every OAuth scope to an admin role for convenience.

### 4.3. Long-Lived WebSocket Connections and Changing Permissions

A session authenticated at handshake does not automatically refresh its Principal/authorities the moment an admin removes a role in the DB. For secure chat rooms, you need a per-message reauthorization policy, service-layer membership/ACL checks, or disconnect-on-revocation, along with TTL/lifecycle and metrics. Do not assume an initial HTTP login protects every subscription indefinitely when permissions are dynamic.

## 5. CONNECT CSRF, Origin, and TLS: Must Not Be Skipped

The browser WebSocket API does not enforce the Same-Origin Policy the way fetch/XHR automatically blocks cross-origin reads, as many mistakenly assume. Cookies may travel with the handshake if browser rules allow; if the server allows an unfamiliar origin, a malicious page could use the user's session to open a WebSocket and subscribe.

Spring Security requires a **CSRF token on STOMP CONNECT** by default when `@EnableWebSocketSecurity` is enabled, while Spring WebSocket/SockJS provides an allowed-origins mechanism. This is a defense-in-depth layer and does not replace HTTP session authentication.

### 5.1. The CSRF Token Must Travel in Native STOMP Headers

Example controller retrieving the token in HTTP context:

~~~java
@RestController
class CsrfEndpoint {
    @GetMapping("/csrf")
    CsrfToken csrf(CsrfToken token) {
        return token;
    }
}
~~~

A browser on the same origin with the same authenticated session calls `GET /csrf`, receives `headerName` and `token` (as JSON), and attaches them to **STOMP CONNECT native headers**:

~~~javascript
// Pseudocode using an installed STOMP client library and same-origin session.
// csrf is the response from the same-origin endpoint (preserving cookie/session).
const connectHeaders = {
  [csrf.headerName]: csrf.token
};
stompClient.connect(connectHeaders, onConnected, onError);
~~~

**Do not** send the CSRF token only in the HTTP Upgrade header and assume it will be copied automatically into STOMP CONNECT. With SockJS XHR fallbacks, many transports restrict custom HTTP headers; native STOMP headers are the proper mechanism. When using a Java STOMP client, maintain the cookie/session or handshake credentials with the same identity as the CSRF token and CONNECT frame.

### 5.2. Should STOMP CONNECT CSRF Be Disabled?

In Spring Security 6.5, the documentation notes that `@EnableWebSocketSecurity` does not yet expose a direct configuration option to disable the CONNECT CSRF requirement; the docs describe an alternative using custom wiring/XML if an organization accepts a different protection model. **Do not** disable HTTP CSRF application-wide just to get STOMP working. If legitimate cross-origin access is required, design token-based authentication, allowed origins, a CSRF strategy, and a reviewed threat model; keep session/recipient checks intact.

### 5.3. Configuring Origins and Schemes

Keep same-origin defaults in the demo. In deployment:
- Use `wss://` in production; avoid sending tokens/cookies over `ws://` on public networks.
- Restrict trusted origins; do not default to `setAllowedOriginPatterns("*")` with cookie-based auth.
- HTTP CORS and WebSocket handshake Origin are two separate layers to enforce; non-browser clients can forge Origin, so Origin never replaces authentication.
- If using SockJS, review frame-options, HTTP fallback paths, transport CSRF, and exact path matchers.
- Cap connection counts, subscriptions per session, message sizes, per-user/tenant rates, and heartbeat timeouts to prevent abuse.

## 6. Spring Boot 3.5 Demo: End-to-End Message Authorization

The demo protects a public topic scoped to authenticated users and an admin topic. Roles:
- `alice`: `ROLE_USER`. May SEND `/app/chat.send` and SUBSCRIBE `/topic/announcements`.
- `admin`: `ROLE_USER` + `ROLE_ADMIN`. In addition to Alice's permissions, may SEND `/app/admin.broadcast` and SUBSCRIBE `/topic/admin`.
- `viewer`: `ROLE_VIEWER`. May authenticate at the HTTP handshake, but is denied all data SEND/SUBSCRIBE frames in the demo.

Messages sent to `/app/**` are handled by the application controller. Only the server uses `SimpMessagingTemplate` to broadcast to `/topic/**`; clients sending directly to broker prefixes are DENIED.

### 6.1. File Structure

~~~text
src/main/java/demo/socket/SocketSecurityApplication.java
src/test/java/demo/socket/MessageAuthorizationRulesTest.java
~~~

Create a Spring Boot **3.5.x** Java 17+ project and use the dependencies in Section 6.3. A single Java file holds the public class and package-private classes for easy practice; in production, separate configuration, controllers, payload DTOs, authorization policies, and domain services.

### 6.2. SocketSecurityApplication.java File

~~~java
package demo.socket;

import java.security.Principal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.messaging.Message;
import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendToUser;
import org.springframework.messaging.simp.SimpMessageSendingOperations;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.messaging.access.intercept
        .MessageMatcherDelegatingAuthorizationManager;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@SpringBootApplication
public class SocketSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(SocketSecurityApplication.class, args);
    }

    @Bean
    SecurityFilterChain httpSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(requests -> requests
                        .requestMatchers("/ws", "/csrf").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password("{noop}demo")
                    .roles("USER")
                    .build(),
                User.withUsername("admin")
                    .password("{noop}demo")
                    .roles("USER", "ADMIN")
                    .build(),
                User.withUsername("viewer")
                    .password("{noop}demo")
                    .roles("VIEWER")
                    .build());
        // {noop} & HTTP Basic are for demo only; do not use in production.
    }
}

@Configuration
@EnableWebSocketMessageBroker
class StompBrokerConfig implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        // Keep restrictive Origin defaults; do not add wildcards.
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}

@Configuration
@EnableWebSocketSecurity
class SocketMessageSecurity {
    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
                // User error queue: requires Authentication.
                .simpSubscribeDestMatchers("/user/queue/errors")
                    .authenticated()

                // Clients may listen only to granted broker streams.
                .simpSubscribeDestMatchers("/topic/announcements")
                    .hasRole("USER")
                .simpSubscribeDestMatchers("/topic/admin")
                    .hasRole("ADMIN")

                // Clients may SEND only to explicitly listed app handlers.
                .simpMessageDestMatchers("/app/chat.send")
                    .hasRole("USER")
                .simpMessageDestMatchers("/app/admin.broadcast")
                    .hasRole("ADMIN")

                // Block all unmatched SEND/SUBSCRIBE, including
                // clients sending directly to /topic/** or /queue/**.
                .simpTypeMatchers(
                    SimpMessageType.MESSAGE, SimpMessageType.SUBSCRIBE)
                    .denyAll()

                // CONNECT, UNSUBSCRIBE, DISCONNECT... typically have no dest.
                .nullDestMatcher().authenticated()

                // Close all other frames by default.
                .anyMessage().denyAll();

        return messages.build();
    }
}

record ChatRequest(String text, String from) {}
record ChatEvent(String author, String text) {}
record AdminRequest(String text) {}
record ErrorFrame(String code) {}

@Controller
class ChatController {
    private final SimpMessageSendingOperations broker;

    ChatController(SimpMessageSendingOperations broker) {
        this.broker = broker;
    }

    @MessageMapping("/chat.send")
    public void send(ChatRequest request, Principal principal) {
        String message = validatedText(
                request == null ? null : request.text());

        if (principal == null) {
            throw new IllegalArgumentException("Authentication required");
        }

        // DO NOT trust request.from(); always use the verified principal.
        broker.convertAndSend(
                "/topic/announcements",
                new ChatEvent(principal.getName(), message));
    }

    @MessageMapping("/admin.broadcast")
    public void adminBroadcast(AdminRequest request, Principal principal) {
        String message = validatedText(
                request == null ? null : request.text());

        if (principal == null) {
            throw new IllegalArgumentException("Authentication required");
        }

        // @EnableWebSocketSecurity policy ensures ROLE_ADMIN
        // on inbound MESSAGE /app/admin.broadcast.
        broker.convertAndSend(
                "/topic/admin",
                new ChatEvent(principal.getName(), message));
    }

    @MessageExceptionHandler(IllegalArgumentException.class)
    @SendToUser(value = "/queue/errors", broadcast = false)
    public ErrorFrame invalidPayload(IllegalArgumentException error) {
        // Do not expose exception messages or stack traces to clients.
        return new ErrorFrame("INVALID_PAYLOAD");
    }

    private static String validatedText(String text) {
        if (text == null || text.isBlank() || text.length() > 240) {
            throw new IllegalArgumentException("Invalid message text");
        }
        return text.trim();
    }
}

@RestController
class CsrfEndpoint {
    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken token) {
        // Only authenticated callers can retrieve the token per HTTP rules.
        return token;
    }
}
~~~

**Important import syntax note:** The `MessageMatcherDelegatingAuthorizationManager` import above is wrapped so the article does not exceed column width, but **Java imports do not allow line breaks between the package and class name when compiling**. In the real file, replace those two lines:

~~~java
import org.springframework.security.messaging.access.intercept
        .MessageMatcherDelegatingAuthorizationManager;
~~~

with a **single-line** import:

~~~java
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;
~~~

Do not keep both. Aside from that formatting detail, the files/classes depend on Spring Boot 3.5.x/Security 6.5.x and the Gradle setup below. If using an IDE, let the IDE normalize imports; do not add a WebFlux dependency for this Servlet/STOMP build.

### 6.3. Gradle Dependencies

This is the `dependencies` block of a Gradle build already configured with the Spring Boot plugin, dependency management, repositories, and Java 17:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

With Spring Security 6.5, `spring-boot-starter-security` and the WebSocket starter in the Spring Boot-managed dependency graph provide the necessary messaging/security modules; if `org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager` is missing from the classpath, check `spring-security-messaging` in the dependency tree and declare it explicitly if not pulled in. For example:

~~~groovy
implementation 'org.springframework.security:spring-security-messaging'
~~~

Do not mix Spring Security versions outside the BOM. In a real project, run `./gradlew dependencies --configuration runtimeClasspath` to confirm the messaging module is present.

### 6.4. Running the Demo

From the project directory:

~~~bash
./gradlew bootRun
~~~

The server exposes the handshake endpoint `ws://localhost:8080/ws`. Browsers use same-origin **session/cookie auth** managed by the HTTP layer; HTTP Basic in the demo is primarily for Java tools/clients capable of sending credentials on the handshake. **The browser WebSocket API does not provide an option to set arbitrary Authorization headers**; a real browser app should use session login or a purposefully designed token handshake/STOMP strategy.

End-to-end test procedure:
1. Authenticate over HTTP in the same session as the `/ws` handshake.
2. Fetch the CSRF token from HTTP `GET /csrf` using that session.
3. Upgrade the WebSocket at `/ws` from an allowed origin.
4. Send STOMP `CONNECT` with the received CSRF header name/value.
5. Once `CONNECTED`, send `SUBSCRIBE` to a valid topic and `SEND` to `/app/chat.send`.
6. Do not use `login:admin`/`passcode` in STOMP to pretend to gain privileges; they do not replace the Spring Principal.
7. Verify that `ChatEvent("alice", text)` appears on `/topic/announcements`, regardless of `from:"admin"` in the client payload.

### 6.5. Illustrative STOMP Frames (Not Shell Commands)

~~~text
CONNECT
accept-version:1.2
host:localhost
X-CSRF-TOKEN:<token-from-GET-csrf>

^@
SUBSCRIBE
id:sub-1
destination:/topic/announcements

^@
SEND
destination:/app/chat.send
content-type:application/json

{"text":"Hello","from":"admin"}
^@
~~~

The `^@` symbol represents the NUL frame terminator in STOMP in human-readable form, **not** the three literal characters `^`, `@`, newline. The CSRF header name must come from the actual `CsrfToken.getHeaderName()` (which may differ from `X-CSRF-TOKEN`). The demo processes the text/username payload, and the server broadcasts `author` as the verified username rather than the client-supplied `from`.

### 6.6. Expected Behavior Table

| Actor | Inbound frame | Destination | Authorization Outcome |
| --- | --- | --- | --- |
| Alice USER | CONNECT (no dest) | null | authenticated rule, **still requires CSRF** |
| Alice USER | SEND/MESSAGE | `/app/chat.send` | GRANT |
| Alice USER | SUBSCRIBE | `/topic/announcements` | GRANT |
| Alice USER | SEND/MESSAGE | `/topic/announcements` | DENY |
| Alice USER | SUBSCRIBE | `/topic/admin` | DENY |
| Admin ADMIN+USER | SEND/MESSAGE | `/app/admin.broadcast` | GRANT |
| Admin ADMIN+USER | SUBSCRIBE | `/topic/admin` | GRANT |
| Admin ADMIN+USER | SEND/MESSAGE | `/topic/admin` | DENY |
| Viewer VIEWER | SEND/MESSAGE | `/app/chat.send` | DENY |
| Alice USER | SUBSCRIBE | `/queue/anything` | DENY |
| Alice USER | SUBSCRIBE | `/user/queue/errors` | GRANT |
| Anonymous | CONNECT | null | DENY by authn/authz (even if sender supplies a random CSRF token) |
| Alice USER | SEND/MESSAGE | `/app/unknown` | DENY |
| Alice USER | SUBSCRIBE | `/topic/unknown` | DENY |

A unit test checking only that `CONNECT` is authorized does not prove CSRF passed; CSRF is a separate interceptor/handshake check requiring an integration test.

## 7. Unit Testing AuthorizationManager<Message<?>> Directly

Goal: test the exact **manager policy** without starting a WebSocket server. Construct a Spring message with a specific type and destination, and pass a real `Authentication` supplier. Use JUnit 5.

Save `src/test/java/demo/socket/MessageAuthorizationRulesTest.java`:

~~~java
package demo.socket;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class MessageAuthorizationRulesTest {
    @Autowired AuthorizationManager<Message<?>> rules;

    private static Authentication user(String name, String... roles) {
        return UsernamePasswordAuthenticationToken.authenticated(
                name, "unused",
                java.util.Arrays.stream(roles)
                    .map(r -> new SimpleGrantedAuthority("ROLE_" + r))
                    .toList());
    }

    private static Authentication anonymous() {
        return new AnonymousAuthenticationToken(
                "test-key", "anonymous",
                List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS")));
    }

    private static Message<byte[]> inbound(
            SimpMessageType type, String destination) {
        SimpMessageHeaderAccessor accessor =
                SimpMessageHeaderAccessor.create(type);
        if (destination != null) {
            accessor.setDestination(destination);
        }
        return MessageBuilder.createMessage(
                new byte[0], accessor.getMessageHeaders());
    }

    @SuppressWarnings("deprecation") // Spring Security 6.5 check()
    private boolean allowed(Authentication actor, SimpMessageType type,
                            String destination) {
        AuthorizationDecision decision =
                rules.check(() -> actor, inbound(type, destination));
        return decision != null && decision.isGranted();
    }

    @Test
    void userMaySendToAppButNotBroker() {
        Authentication alice = user("alice", "USER");

        assertTrue(allowed(alice, SimpMessageType.MESSAGE,
                "/app/chat.send"));
        assertFalse(allowed(alice, SimpMessageType.MESSAGE,
                "/topic/announcements"));
        assertFalse(allowed(alice, SimpMessageType.MESSAGE,
                "/queue/private"));
        assertFalse(allowed(alice, SimpMessageType.MESSAGE,
                "/app/unknown"));
    }

    @Test
    void subscribeIsDifferentFromSend() {
        Authentication alice = user("alice", "USER");

        assertTrue(allowed(alice, SimpMessageType.SUBSCRIBE,
                "/topic/announcements"));
        assertFalse(allowed(alice, SimpMessageType.SUBSCRIBE,
                "/app/chat.send"));
        assertFalse(allowed(alice, SimpMessageType.SUBSCRIBE,
                "/topic/admin"));
        assertFalse(allowed(alice, SimpMessageType.SUBSCRIBE,
                "/queue/user/private"));
        assertTrue(allowed(alice, SimpMessageType.SUBSCRIBE,
                "/user/queue/errors"));
    }

    @Test
    void adminPrivilegesDoNotPermitDirectTopicSend() {
        Authentication admin = user("admin", "USER", "ADMIN");

        assertTrue(allowed(admin, SimpMessageType.MESSAGE,
                "/app/admin.broadcast"));
        assertTrue(allowed(admin, SimpMessageType.SUBSCRIBE,
                "/topic/admin"));
        assertFalse(allowed(admin, SimpMessageType.MESSAGE,
                "/topic/admin"));
    }

    @Test
    void viewerCannotSendOrSubscribeToPrivateTopic() {
        Authentication viewer = user("viewer", "VIEWER");

        assertFalse(allowed(viewer, SimpMessageType.MESSAGE,
                "/app/chat.send"));
        assertFalse(allowed(viewer, SimpMessageType.SUBSCRIBE,
                "/topic/announcements"));
    }

    @Test
    void authenticatedControlFrameAllowedButAnonymousDenied() {
        Authentication alice = user("alice", "USER");

        assertTrue(allowed(alice, SimpMessageType.CONNECT, null));
        assertTrue(allowed(alice, SimpMessageType.DISCONNECT, null));
        assertFalse(allowed(anonymous(), SimpMessageType.CONNECT, null));
    }

    @Test
    void malformedOrUnknownMessagesAreDenied() {
        Authentication alice = user("alice", "USER");

        assertFalse(allowed(alice, SimpMessageType.MESSAGE, null));
        assertFalse(allowed(alice, SimpMessageType.SUBSCRIBE, null));
        assertFalse(allowed(alice, SimpMessageType.MESSAGE,
                "/topic/admin"));
        assertFalse(allowed(alice, SimpMessageType.OTHER,
                "/topic/announcements"));
    }
}
~~~

These tests prove:
- The builder **distinguishes type** and destination.
- The admin role does not unlock direct client SEND to a broker topic.
- The `anyMessage().denyAll()` fallthrough rule works.
- `nullDestMatcher` does not accidentally allow malformed MESSAGE/SUBSCRIBE frames because type deny is placed first.
- An `AnonymousAuthenticationToken` has `isAuthenticated() == true` in its representation, yet `authenticated()` uses the trust resolver and does not treat it as a validly logged-in user.

**Not yet proven by this unit test:** CSRF token at CONNECT, WebSocket Origin, HTTP handshake authentication, broker relay, session cookies, actual STOMP message routing, and server delivery to subscribers. Those require separate integration tests.

## 8. Integration Test Plan with WebSocketStompClient

An effective integration test should run the server on a random port with a real STOMP client:
- `@SpringBootTest(webEnvironment = RANDOM_PORT)` with `@LocalServerPort`.
- `WebSocketStompClient` + `StandardWebSocketClient` (or the chosen transport), using the test user's session/cookie or HTTP handshake credentials.
- `StompHeaders` containing the CSRF header name/value on `CONNECT` obtained from the HTTP API in the **same session**.
- Handler subscribes to an allowed destination; sends JSON `{"text":"ok","from":"admin"}` to `/app/chat.send` and verifies the server event has `author:"alice"`.
- Repeat tests with VIEWER, ADMIN, wrong topic, missing CSRF, wrong Origin, malformed tokens, and revoked memberships.

Pseudocode for sending/receiving:

~~~java
// Snippet inside an integration test; not a standalone file.
// Earlier, the HTTP handshake was authenticated; CSRF was
// fetched via GET /csrf in the same session and added to CONNECT headers.
StompHeaders connect = new StompHeaders();
connect.add(csrfHeaderName, csrfTokenValue);

StompSession session = client
        .connectAsync(wsUrl, webSocketHeaders, connect, handler)
        .get(5, TimeUnit.SECONDS);

// After CONNECTED:
session.subscribe("/topic/announcements", subscriptionHandler);
session.send("/app/chat.send",
        "{\"text\":\"Hello\",\"from\":\"admin\"}".getBytes(UTF_8));

// subscriptionHandler must receive ChatEvent.author == "alice".
~~~

`connectAsync` parameters/methods may vary across Spring Framework/`WebSocketStompClient` versions; check overloads against your chosen dependency. In particular, `WebSocketStompClient` takes both HTTP handshake headers and STOMP CONNECT headers: put CSRF in the **STOMP** headers, without confusing the two. Do not write integration tests that only send CONNECT and assume all MESSAGE/SUBSCRIBE routing is tested.

### 8.1. Why Testing Only the /ws Handshake Is Not Enough

HTTP GET `/ws` may return `101 Switching Protocols` for an authenticated user, yet afterward:
- STOMP CONNECT may lack CSRF and be rejected;
- the client may try SEND to a broker prefix;
- the user may subscribe to an unauthorized topic;
- a bearer token sent in a STOMP header will not automatically be parsed by the HTTP Authentication filter;
- the session may persist after a role is revoked.

You must test **HTTP authn, STOMP CONNECT, inbound authorization, application business authorization, and outbound visibility**.

### 8.2. 403 Does Not Necessarily Appear as HTTP 403

A STOMP frame denied **after the WebSocket upgrade** is no longer a new HTTP request. The client may see a STOMP ERROR frame, a closed connection, or a session error depending on Spring configuration/error handling. Do not write tests expecting HTTP 403 for every unauthorized SUBSCRIBE/SEND. HTTP 401/403 statuses apply at the handshake; after upgrade, assert STOMP/session behavior and verify no sensitive data is received.

### 8.3. Measuring Message Side Effects

When a client sends an unauthorized SEND to `/app/admin.broadcast`, the test should verify:
1. No server-side business handler execution.
2. No `SimpMessagingTemplate.convertAndSend("/topic/admin",...)`.
3. No subscriber receives an event.
4. Security deny/audit metrics record the right role/destination/type.
5. Session error handling follows contract without leaking stack traces/tokens.

Tests that only assert no HTTP 200 response prove too little, because WebSocket and STOMP have a different response model.

## 9. Room/Tenant Authorization: Custom AuthorizationManager<MessageAuthorizationContext<?>>

The USER role works for a demo, yet is usually **insufficient** for chat rooms/tenants. If the destination is `/topic/rooms/{roomId}`, you must verify that each actor is a member of that room.

### 9.1. Custom Manager Example (Class Snippet)

~~~java
package demo.socket;

import java.util.Map;
import java.util.Set;
import java.util.function.Supplier;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.messaging.access.intercept.MessageAuthorizationContext;

// Assumed PIP on the application server, not from client headers.
interface RoomMemberships {
    boolean canSubscribe(String principalId, String roomId);
}

final class RoomSubscribeManager
        implements AuthorizationManager<MessageAuthorizationContext<?>> {
    private final RoomMemberships membership;

    RoomSubscribeManager(RoomMemberships membership) {
        this.membership = membership;
    }

    @Override
    @SuppressWarnings("deprecation")
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            MessageAuthorizationContext<?> context) {

        Authentication actor = authentication.get();
        String roomId = context.getVariables().get("roomId");
        if (actor == null || !actor.isAuthenticated()
                || actor instanceof AnonymousAuthenticationToken
                || roomId == null
                || !roomId.matches("[a-zA-Z0-9-]{1,48}")) {
            return new AuthorizationDecision(false);
        }

        try {
            return new AuthorizationDecision(
                    membership.canSubscribe(actor.getName(), roomId));
        } catch (RuntimeException failure) {
            // Real system: metric + alert; never fail open.
            return new AuthorizationDecision(false);
        }
    }
}
~~~

This is a separate optional file: in production, the `RoomMemberships` interface reads from a governed source with tenant scoping, TTL, and latency bounds. The `Map` and `Set` imports in this snippet are unnecessary and can be removed by an IDE; they do not affect compilation. When applying the rule:

~~~java
// Snippet inside messageAuthorizationManager Builder:
messages
    .simpSubscribeDestMatchers("/topic/rooms/{roomId}")
        .access(new RoomSubscribeManager(roomMemberships))
    .simpTypeMatchers(SimpMessageType.SUBSCRIBE).denyAll()
    .anyMessage().denyAll();
~~~

Place specific rules **before** general denies. `MessageAuthorizationContext#getVariables()` retrieves matched path variables; do not manually split destinations with `split("/")` without validation and indexing. For MESSAGE frames sent to a room, a corresponding policy is needed for `/app/rooms/{roomId}/send` along with owner/moderator checks in the application service.

### 9.2. Limits of a Synchronous Manager

`AuthorizationManager<Message<?>>` is a synchronous authorization interface. If room membership requires a DB/remote PIP call, **do not** place untimeouted blocking network calls on the inbound executor. You can use a trusted cache with strict TTL/invalidation, or an appropriate message/service-layer architecture for async verification before side effects. If permissions must be exact on every SEND, the service should re-check state/tenant/ACL before publishing. Never use `CompletableFuture.runAsync(...); return true` or fire-and-forget `subscribe()` inside the manager.

### 9.3. A Tenant ID in the Destination Does Not Prove Membership

`SUBSCRIBE /topic/tenant/beta` is a client-chosen request. If Alice only belongs to tenant alpha, a `/topic/tenant/**.authenticated()` matcher is wrong. The manager must take the actor from the authenticated principal and verify membership in tenant beta against a trusted source. When the broker broadcasts sensitive notifications, use per-tenant destinations, subscription-time authorization, server-producer isolation, and a data-retention policy.

### 9.4. Do Not Trust Custom STOMP Headers

Native headers such as `x-tenant`, `role`, `userId`, `isAdmin`, or `subscription-owner` can be forged by the client. They are merely unverified selectors/metadata. `SimpMessageHeaderAccessor#getUser()` is trustworthy when Spring has bound the Principal from a verified handshake or properly implemented token-verification interceptor. Avoid setting the user from the message body.

## 10. User Destinations and Securing Private Queues

Spring supports the `/user/` prefix for user-specific destinations:
- Client Alice subscribes to `/user/queue/errors`.
- The controller uses `@SendToUser(value="/queue/errors",broadcast=false)` or the server calls `convertAndSendToUser(username, "/queue/messages", payload)`.
- Spring resolves this to a broker destination specific to the actual session/user, not merely a shared `/queue/errors` topic for everyone.

Specifically:
- Do not allow clients to subscribe directly to `/queue/**`, as internal broker paths may contain other users' private queues.
- Do not grant permissions based on a username in a STOMP `destination` if that username was supplied by the client.
- `/user/**.permitAll()` can be overly broad; require authentication and restrict individual destinations or check object permissions if sensitive data is involved.
- When notifications must be delivered across multiple devices/sessions, define fanout, offline notifications, data retention, and user-session mapping.
- With an external broker relay, inspect the user-destination prefix configuration, queue TTL/cleanup, and broker ACLs; a Spring inbound deny is not automatically a broker ACL.

### 10.1. Can @SendToUser Serve as the Sole Authorization Layer?

No. `@SendToUser` routes a response to the user/session, yet it does not replace authorization on the message-sending action, does not replace tenant/resource ACLs, and does not protect subscribed broker topics. Inbound authorization, business authorization, and routing must all be right.

### 10.2. Avoid Sending Internal Exception Details

A `@MessageExceptionHandler` can respond with a concise error code like `INVALID_PAYLOAD`. Never return messages containing SQL, bearer tokens, stack traces, or information about another tenant's rooms. Distinguish input validation errors from authorization failures, and avoid reporting details that let an attacker enumerate private rooms/users.

## 11. Hand-Written AuthorizationManager and Default-Deny

Beyond the Builder, you can write the full manager yourself:

~~~java
AuthorizationManager<Message<?>> gate = (authentication, message) -> {
    Authentication actor = authentication.get();
    SimpMessageType type =
            SimpMessageHeaderAccessor.getMessageType(
                    message.getHeaders());
    String destination =
            SimpMessageHeaderAccessor.getDestination(
                    message.getHeaders());

    boolean allowed = actor != null
            && actor.isAuthenticated()
            && type == SimpMessageType.MESSAGE
            && "/app/chat.send".equals(destination)
            && actor.getAuthorities().stream().anyMatch(
                a -> "ROLE_USER".equals(a.getAuthority()));

    return new AuthorizationDecision(allowed);
};
~~~

This is an **excerpt**, not a complete safe replacement: checking `actor.isAuthenticated()` must distinguish anonymous users, account for CONNECT/SUBSCRIBE/control frames, and enforce CSRF. Write a full custom manager only when logic is hard to express with matchers; it is best to start from the Builder for default-deny and readable/testable rules. In 6.5, a lambda matches `AuthorizationManager`'s functional contract; when upgrading versions, check Javadoc and deprecation warnings.

### 11.1. Policies Without Unnecessary Overlapping Rules

Example:

~~~java
messages
    .simpDestMatchers("/topic/**").authenticated()
    .simpSubscribeDestMatchers("/topic/admin").hasRole("ADMIN")
    .anyMessage().denyAll();
~~~

**Wrong:** the first rule already matches `SUBSCRIBE /topic/admin` and can also match SEND, rendering the subsequent ADMIN rule ineffective. Order must put specific rules first and use `simpSubscribeDestMatchers` for subscriptions; avoid wildcard broker prefixes.

### 11.2. An Explicit Deny Rule Beats the Habit of anyMessage.authenticated()

`anyMessage().authenticated()` lets any authenticated client send any undeclared MESSAGE/SUBSCRIBE, including broker topics. A newly added feature can become accessible without anyone remembering to add a rule. Use `anyMessage().denyAll()` and open additional destinations only through explicit review and testing.

### 11.3. Session CONNECT Is Not a License to Send Any Message

CSRF/Origin and authentication at CONNECT prove session-establishment conditions, not that every SUBSCRIBE or SEND is valid. An actor may be permitted to CONNECT yet lack the role to subscribe to an admin topic; the policy must check every inbound frame.

## 12. Comparison with HTTP and Method Security

| Layer | Authorization Input | Used to Protect |
| --- | --- | --- |
| HTTP request security | `HttpServletRequest` | Handshake URL `/ws`, HTTP login, CSRF endpoint |
| WebSocket message security | `Message<?>` with type/destination/Principal | Inbound STOMP SEND/SUBSCRIBE/CONNECT |
| Method security | `MethodInvocation`, `@PreAuthorize` | Proxied service method calls |
| Object/tenant ACL | Principal + resource owner/membership | Specific resources in repositories/business logic |
| Broker ACL | Broker identity, destination rules | Direct queues/topics on an external broker |
| Outbound message filtering | Application event/routing policy | Which actual recipients receive which payloads |

**Multiple layers** are required: HTTP authorization does not imply STOMP authorization; a STOMP role matcher does not prove room membership; `@MessageMapping` is invoked after inbound authorization, yet the business action still requires validation and transactions; a broker relay may accept messages from other sources if misconfigured.

### 12.1. Do Not Confuse with Spring WebFlux WebSocket Handler

`@EnableWebSocketSecurity` here relies on **Spring Messaging/STOMP over the Servlet WebSocket message broker**, not a raw WebFlux/reactive-stream `WebSocketHandler`. If an application uses a reactive WebFlux `WebSocketHandler` without a Spring STOMP broker, it needs separate authentication and policy integration at the handshake and message stream; do not assume this annotation protects arbitrary raw WebSocket payloads.

### 12.2. Do Not Confuse with Spring Integration Messaging

`AuthorizationManager<Message<?>>` with Spring Security Messaging targets the Spring Messaging inbound channel for STOMP, and does not guarantee Spring Security will intercept every Spring Integration channel or JMS/Kafka message. Other transports need authorization at consumers/producers and appropriate broker ACLs.

## 13. Running Standalone Java 17 to See the Policy Clearly

The pure JDK program below simulates the demo's policy. It opens no sockets, has no CSRF, and uses no AOP or Spring Security. We separate actor, type, and destination to show that **a role and a destination** are still not enough; **message type** must also be evaluated.

Save `StompPolicyDemo.java`:

~~~java
import java.util.Set;

public class StompPolicyDemo {
    enum Type { CONNECT, DISCONNECT, SEND, SUBSCRIBE, OTHER }

    record Actor(String name, Set<String> roles, boolean authenticated) {}
    record Frame(Type type, String destination) {}

    static boolean allowed(Actor actor, Frame frame) {
        if (actor == null || !actor.authenticated()
                || frame == null || frame.type() == null) {
            return false;
        }
        String to = frame.destination();

        if (frame.type() == Type.SEND) {
            return ("/app/chat.send".equals(to)
                        && actor.roles().contains("USER"))
                    || ("/app/admin.broadcast".equals(to)
                        && actor.roles().contains("ADMIN"));
        }
        if (frame.type() == Type.SUBSCRIBE) {
            return ("/topic/announcements".equals(to)
                        && actor.roles().contains("USER"))
                    || ("/topic/admin".equals(to)
                        && actor.roles().contains("ADMIN"))
                    || "/user/queue/errors".equals(to);
        }
        if (frame.type() == Type.CONNECT
                || frame.type() == Type.DISCONNECT) {
            // Simulates AUTHN only; does not check CONNECT CSRF.
            return to == null;
        }
        return false;
    }

    private static void show(String label, Actor actor, Frame frame) {
        System.out.println(label + "=" + allowed(actor, frame));
    }

    public static void main(String[] args) {
        Actor alice = new Actor("alice", Set.of("USER"), true);
        Actor admin = new Actor(
                "admin", Set.of("USER", "ADMIN"), true);
        Actor viewer = new Actor("viewer", Set.of("VIEWER"), true);
        Actor anonymous = new Actor("anonymous", Set.of(), false);

        show("alice-connect", alice,
                new Frame(Type.CONNECT, null));
        show("alice-send-chat", alice,
                new Frame(Type.SEND, "/app/chat.send"));
        show("alice-subscribe-news", alice,
                new Frame(Type.SUBSCRIBE, "/topic/announcements"));
        show("alice-send-topic", alice,
                new Frame(Type.SEND, "/topic/announcements"));
        show("alice-subscribe-admin", alice,
                new Frame(Type.SUBSCRIBE, "/topic/admin"));
        show("admin-subscribe-admin", admin,
                new Frame(Type.SUBSCRIBE, "/topic/admin"));
        show("admin-send-topic", admin,
                new Frame(Type.SEND, "/topic/admin"));
        show("viewer-send-chat", viewer,
                new Frame(Type.SEND, "/app/chat.send"));
        show("alice-private-queue", alice,
                new Frame(Type.SUBSCRIBE, "/queue/private"));
        show("anonymous-connect", anonymous,
                new Frame(Type.CONNECT, null));
        show("alice-unknown", alice,
                new Frame(Type.OTHER, "/app/chat.send"));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 StompPolicyDemo.java
java StompPolicyDemo
~~~

**Exact stdout:**

~~~text
alice-connect=true
alice-send-chat=true
alice-subscribe-news=true
alice-send-topic=false
alice-subscribe-admin=false
admin-subscribe-admin=true
admin-send-topic=false
viewer-send-chat=false
alice-private-queue=false
anonymous-connect=false
alice-unknown=false
~~~

Why are these results notable?
- Admin can subscribe to `/topic/admin`, yet **cannot SEND directly** to that broker topic; admin sends via `/app/admin.broadcast`.
- Alice can send chat via the app controller and subscribe to regular announcements; she cannot listen to the admin topic.
- Authenticated viewer still lacks `ROLE_USER`.
- A client may try sending an unfamiliar destination name, but the policy denies by default.
- `CONNECT=true` in this program only simulates authentication; **real STOMP CONNECT also requires a CSRF token and framework checks**.
- This simulator does not verify the Principal from the handshake; a full Spring test must do that.

## 14. Multi-Tenancy, Ownership, and Broker-Level Isolation

Suppose tenants alpha and beta both have room ID `7`. A shared destination `/topic/rooms/7` could mix events if the server distinguishes only `roomId` without distinguishing tenant. Better approach:
- Use a canonical key `(tenantId, roomId)` for DB/repository/topic routing (for example, `/topic/tenants/alpha/rooms/7`).
- On SUBSCRIBE, verify the authenticated principal holds alpha tenant membership and read permission for room 7; any ID in the path is only a selector.
- On SEND `/app/tenants/alpha/rooms/7`, re-verify membership and send permission; do not trust `fromUser` in the payload.
- When the server broadcasts, ensure only alpha data is emitted to the alpha topic. Protect the producer, not only the subscriber.
- For role revocation/tenant switching, invalidate/disconnect subscriptions or apply event policies; do not keep stale ALLOWs indefinitely.
- In a cluster, consistent hashing/broker relay session destinations and routing must preserve tenant isolation; all instances must enforce the same security contract.

### 14.1. Private Object Subscriptions Need Per-Object ACLs

A user belonging to tenant alpha is not automatically permitted to view confidential document `alpha:7`. A custom subscription manager must check the record ACL/owner/classification; for high-impact data, the server may issue dedicated user queues instead of a shared topic. `/user/queue/**` does not automatically prove object-level permission.

### 14.2. Do Not Publish Sensitive Payloads to a Public Topic Hoping to Filter Later

Because Spring Security is inbound-only, an accidental broadcast to `/topic/announcements` can reach every authorized subscriber on that topic. Perform data classification/redaction/recipient selection **before publishing**. For documents, consider publishing only "document updated" with an opaque ID so clients call an authorized REST API to fetch the contents.

## 15. Practical CSRF/Origin and SockJS

| Scenario | What to Check |
| --- | --- |
| Browser same-origin session | GET /csrf, STOMP CONNECT with matching native token, cookie/session preserved |
| Foreign origin where session cookie might be sent | Handshake Origin allowlist + STOMP CONNECT CSRF |
| SockJS XHR fallback | HTTP endpoint paths and CSRF/Frame headers; do not drop site-wide protection |
| Java non-browser client | Origin can be forged; requires authenticated handshake/token, never rely on Origin alone |
| JWT in HTTP handshake | Validate access token properly and bind Principal to the session |
| JWT in STOMP CONNECT | Custom ChannelInterceptor verifies token before message authz |
| Wrong/expired CSRF token or different session | CONNECT rejected; no permission to subscribe |
| TLS offload at ingress | Proxy routing, forwarded headers, and WSS configured properly; avoid mixed content |
| Cross-origin officially required | Separate threat model; never wildcard + cookies + disabled CSRF |
| Session reconnect | Re-authenticate/recheck permissions; do not reuse stale authorization |

For server-side rendered apps, `CsrfToken` can be retrieved from the request attribute or an API token endpoint; for SPAs, token retrieval depends on session/cookie/CORS and the CSRF repository. Never send CSRF tokens to third-party analytics or logs; although a CSRF token is not an access token, it remains security-sensitive within the session lifecycle.

## 16. Observability, Errors, and Operability

Events worth monitoring:
- `WebSocketSessionConnectedEvent`/`SessionConnectEvent`/`SessionSubscribeEvent`/`SessionDisconnectEvent` (exact event names depend on layer and version) for lifecycle visibility, never as a substitute for authorization logic.
- Message rates per actor/tenant/destination; subscription counts per session; denied frame counts.
- Classify handshake authn failures, CSRF CONNECT denials, Origin rejections, message rule denials, PIP/ACL errors, and broker disconnects separately.
- Correlation ID from HTTP handshake → STOMP session ID → message ID, without logging raw JWT/cookie/CSRF tokens.
- Broker relay up/down, user registry state, fanout size, message queue lag, backpressure, and stale subscription cleanup.
- Do not log full chat/document payloads by default; mask PII/tenant secrets and log only fields needed for auditing.

A STOMP authorization exception usually has no new HTTP response; depending on the handler, the client receives an ERROR frame or connection close. If returning friendly business error codes, never leak specifics such as "someone else's room exists but you cannot view it." Use internal deny reasons and stable client-facing codes.

### 16.1. A Broker Outage Must Not Open Access

If the backend ACL/PIP is unreachable, a custom manager should deny/fail closed; never write `catch (...) { return new AuthorizationDecision(true); }`. You may return a transient error so clients reconnect within limits, but never bypass subscription permissions. Cached permission lists must have TTL, versioning, and a revocation strategy.

### 16.2. Reconnect Must Not Carry Over All Old Permissions

When a WebSocket session drops and opens a new connection, re-authenticate the handshake with the current token/cookie; user/room permissions may have changed. If using STOMP auto-reconnect, the client should obtain fresh CSRF/session/tokens as needed; do not retain expired credentials and retry infinitely, causing lockouts or rate-limit exhaustion.

## 17. Pre-Deployment QA Matrix

| Case | Expectation |
| --- | --- |
| Authenticated Alice + valid CONNECT CSRF | CONNECTED |
| CONNECT missing CSRF or wrong session | Rejected before SUBSCRIBE |
| Unauthenticated HTTP handshake | Handshake 401/redirect per entry point |
| Handshake from foreign Origin | Rejected per allowlist |
| Alice SEND /app/chat.send | Handler runs, author = Alice |
| Alice payload from="admin" | Author remains Alice |
| Alice SUBSCRIBE /topic/announcements | Allowed |
| Alice SEND /topic/announcements | Denied, no broker publish |
| Alice SUBSCRIBE /topic/admin | Denied, receives no events |
| Admin SUBSCRIBE /topic/admin | Allowed |
| Admin SEND /app/admin.broadcast | Allowed; server publishes to admin topic |
| Admin SEND /topic/admin directly | Denied despite ROLE_ADMIN |
| Viewer SEND /app/chat.send | Denied |
| Client SUBSCRIBE /queue/private | Denied |
| Client SUBSCRIBE /user/queue/errors | Authenticated; scoped to user destination |
| Client SUBSCRIBE /app/chat.send | Denied, not confused with MESSAGE |
| Unknown destination SEND/SUBSCRIBE | Deny by default |
| Missing destination MESSAGE/SUBSCRIBE | Denied before nullDestMatcher |
| Anonymous CONNECT | Denied |
| Role USER without room membership | Denied by custom manager |
| Tenant beta targets alpha destination | Denied |
| User role revoked while session is live | Follows reauthorization/disconnect SLA |
| Broken broker/ACL service | No fail open |
| Invalid oversized/malformed message | No crash, no privilege bypass, rate limited |
| Remote broker sends policy-violating message | Broker ACL/server producer boundary |
| @MessageMapping self-call/side effect | Business checks before publish |
| Incorrect ROLE_ prefix | Caught by negative authority tests |
| Non-STOMP WebFlux handler | Does not automatically receive protection from this annotation |
| Unit policy tests pass | Does not replace real CSRF/Origin integration tests |
| STOMP ERROR frame | Leaks no SQL/stack/JWT |
| Permitted subscriber receives event from another tenant | Producer validation mandatory |

### 17.1. Mutation Tests

In a test branch, try:
1. Changing `simpMessageDestMatchers("/app/chat.send")` to `simpDestMatchers("/**")` → the negative direct broker SEND test must turn red.
2. Removing `simpTypeMatchers(MESSAGE,SUBSCRIBE).denyAll()` → the unknown destination test must turn red, or `anyMessage().denyAll()` must still protect it.
3. Changing `anyMessage().denyAll()` to `authenticated()` → unexpected message tests must turn red.
4. Allowing `/topic/admin` subscribe with `authenticated()` → Alice's negative test must turn red.
5. Using `ChatRequest.from()` instead of `principal.getName()` → the spoof-author integration test must turn red.
6. Removing the CSRF CONNECT interceptor in the test environment → the missing-CSRF integration test must turn red.
7. Removing the tenant predicate from the room PIP → the cross-tenant subscription test must turn red.
8. Allowing CLIENT direct SEND to `/topic/**` → the broker impersonation test must turn red.

If your tests fail to catch these mutations, the suite has not yet proven the inbound messaging boundaries.

## 18. Common Mistakes

### Mistake 1 — Configuring Only the HTTP SecurityFilterChain
An authenticated handshake does not mean every SEND/SUBSCRIBE is permitted. `@EnableWebSocketSecurity` and an `AuthorizationManager<Message<?>>` bean are required.

### Mistake 2 — Using simpDestMatchers("/topic/**").authenticated()
Does not restrict message type; clients can send directly to the broker topic. Use `simpSubscribeDestMatchers` and deny SEND to broker prefixes.

### Mistake 3 — PermitAll on Every CONNECT Thinking It Is Just a Handshake
CONNECT still requires an authenticated Principal and a session-matching CSRF token; anonymous callers and foreign Origins must not gain subscribe access.

### Mistake 4 — Trusting "role=ADMIN" or "user=alice" Headers
Client-declared native STOMP headers/payloads do not constitute authorities. Derive the Principal from verified HTTP auth or a trusted token-validation interceptor.

### Mistake 5 — Allowing SUBSCRIBE /queue/**
Can expose private queues or internal broker paths. Only allow `/user/queue/<approved>` or ACL-checked topics.

### Mistake 6 — Using Client-Supplied /user/{otherUsername}
User destinations handle routing, not letting clients pick another identity. The server sends to a user using the trusted principal.

### Mistake 7 — Placing Broad Matchers Before Role-Specific Rules
First match wins; an overly broad `authenticated()` can render `hasRole("ADMIN")` meaningless.

### Mistake 8 — anyMessage().authenticated()
Opens every undeclared message to every logged-in user. Use `denyAll` by default.

### Mistake 9 — Assuming Outbound Is Automatically Intercepted by Spring Security
Spring Security documentation states inbound-only. Subscription permissions and producer data-scoping are the primary boundaries.

### Mistake 10 — Disabling Site-Wide CSRF for SockJS
If HTTP CSRF/frame relaxation is needed, scope it strictly to the transport endpoint and maintain a CONNECT token/Origin strategy; never disable globally.

### Mistake 11 — Using WS Instead of WSS in Production
Cookies/tokens/plaintext traffic are exposed; use TLS and properly configured proxies.

### Mistake 12 — Using Origin Alone as Authentication
Non-browser clients can forge Origin; identity and authorization remain mandatory.

### Mistake 13 — Treating STOMP login/passcode as the Spring User
By default, the HTTP handshake Principal is the authn source; if STOMP-level auth is desired, configure dedicated authentication.

### Mistake 14 — Allowing Any Authenticated User to Subscribe to Any Tenant
The tenant in the destination is client input. Membership/object ACLs from a trusted source are required, not just `hasRole("USER")`.

### Mistake 15 — Not Checking Owner/Source in Payload
Trusting `from` enables sender spoofing. Use the server-side Principal instead of copying client userId.

### Mistake 16 — Testing @MessageMapping Only with a Unit Test
Can bypass the inbound manager/CSRF/routing. Test the message manager separately and run STOMP integration tests over the network.

### Mistake 17 — Expecting HTTP 403 for Every Denied STOMP Frame
After upgrade, the protocol is STOMP rather than a new HTTP request; assert ERROR/close/no delivery per contract.

### Mistake 18 — Role Revoked While Session Persists Indefinitely
Authorization/revocation freshness is needed; recheck sensitive messages and disconnect/invalidate per SLA.

### Mistake 19 — Mixing Servlet STOMP with Raw WebFlux WebSocket Handlers
The Spring Messaging inbound annotation does not cover all transports/handlers; choose the right security integration.

### Mistake 20 — Reading Any Global Resource by ID in @MessageMapping
Even when a message is role-AUTHORIZED, DB queries must remain tenant-scoped/object-specific and never leak another tenant's records.

## 19. Implementation Checklist

- [ ] App actually uses Spring STOMP over WebSocket message broker on Servlet, with matching Spring Boot/Security versions.
- [ ] `@EnableWebSocketMessageBroker` registers `/ws`, `/app`, `/topic`, `/queue`, `/user` matching real routing.
- [ ] HTTP handshake `/ws` is authenticated and has an Origin allowlist; production uses WSS.
- [ ] `@EnableWebSocketSecurity` and the `AuthorizationManager<Message<?>>` bean are loaded by Spring.
- [ ] `simpMessageDestMatchers` covers only client SEND to granted `/app/...` endpoints.
- [ ] `simpSubscribeDestMatchers` allows subscribing only to authorized topic/user destinations.
- [ ] Clients are blocked from direct SEND to broker `/topic/**`, `/queue/**`.
- [ ] Specific rules come first, denying unmatched MESSAGE/SUBSCRIBE and `anyMessage().denyAll()`.
- [ ] CONNECT frame verifies authenticated Principal and session-matching CSRF token.
- [ ] STOMP native headers/payloads are not trusted as identity/role/tenant.
- [ ] `hasRole("USER"/"ADMIN")` matches `ROLE_USER`/`ROLE_ADMIN` authorities from the Authentication provider.
- [ ] `@MessageMapping` uses only the server-side Principal and validates body/length/type.
- [ ] Server publishes to the right tenant/topic/recipient; outbound is not automatically authorized by the framework.
- [ ] Room/tenant subscriptions check membership/ACL/revocation rather than relying on global roles.
- [ ] Broker relay, user destinations, session registry, and production transport have a threat model.
- [ ] Real integration tests run for handshake/CONNECT-CSRF/SUBSCRIBE/SEND/denied delivery.
- [ ] Manager unit tests cover MESSAGE vs. SUBSCRIBE, unknown, admin, anonymous, and malformed destinations.
- [ ] Logging/metrics avoid raw tokens, cookies, CSRF, and private chat contents; track denials/errors.
- [ ] Legacy `AbstractSecurityWebSocketMessageBrokerConfigurer` is not used alongside the new model without migration.
- [ ] Unit tests are not claimed to replace signatures, CSRF, or Origin/broker end-to-end tests.

## 20. Review Questions

**Question 1.** Why is `simpDestMatchers("/topic/**").hasRole("USER")` not equivalent to `simpSubscribeDestMatchers("/topic/**").hasRole("USER")`?

**Answer:** The first matcher does not restrict the message type, so a client with ROLE_USER may be permitted to SEND directly to the broker topic. The second matcher permits only SUBSCRIBE frames, while SEND does not match and is denied by fallthrough rules.

**Question 2.** A user with ROLE_ADMIN can SUBSCRIBE to `/topic/admin`. Should they be allowed to SEND directly to that destination?

**Answer:** No. Even admins should invoke a validated `/app/admin.broadcast` handler, while the broker notification is emitted by the server. Permission to subscribe is not permission to publish.

**Question 3.** Once a WebSocket handshake succeeds, can STOMP CONNECT CSRF be skipped?

**Answer:** Not in the default `@EnableWebSocketSecurity` configuration described here. Cross-origin browsers and cookie sessions carry CSWSH risk; a token in STOMP CONNECT alongside an Origin policy is a critical layer.

**Question 4.** Why can `x-user:alice` in a STOMP SEND not be used as the author?

**Answer:** The client can write any value it wants. The controller must use the Principal verified by Spring Security from the handshake or an authorized interceptor.

**Question 5.** Does `AuthorizationManager<Message<?>>` automatically filter every outbound event per subscriber?

**Answer:** No. Spring Security Messaging focuses on inbound; SUBSCRIBE authorization, broker routing, and data-producer validation must be designed so out-of-scope data is never emitted.

**Question 6.** What happens when the ADMIN role is revoked in the middle of a long-lived WebSocket session?

**Answer:** Authentication/authorities from the handshake may be stale. You need a reauthorization policy, ACL lookups, disconnect/reconnect handling, and a revocation SLA; do not assume roles update automatically.

**Question 7.** Should an inbound MESSAGE frame without a destination be allowed by `nullDestMatcher().authenticated()`?

**Answer:** Not in a strict policy. Place `simpTypeMatchers(MESSAGE,SUBSCRIBE).denyAll()` before `nullDestMatcher` to reject malformed data frames.

**Question 8.** Can `@EnableWebSocketSecurity` be used to secure every raw WebFlux `WebSocketHandler`?

**Answer:** No. This integration is for Spring Messaging/STOMP. Raw WebSocket/WebFlux requires separate authentication and message authorization.

**Question 9.** Why does a unit test calling only `builder.check` not prove CONNECT CSRF works?

**Answer:** CSRF is checked in an interceptor during the real STOMP/handshake flow, not by individual role/destination rules; a STOMP integration test is required.

**Question 10.** When two tenants share `roomId` 7, why can you not subscribe to `/topic/rooms/7` for all of them?

**Answer:** The ID is not unique per tenant; you must use tenant-scoped resource identities, memberships, and routing. Otherwise, one tenant could listen to another tenant's notifications.

## 21. Conclusion

**WebSocket message authorization is a triad problem: authenticated actor + message type + permitted destination.** With Spring Security 6.5, `@EnableWebSocketSecurity` and `AuthorizationManager<Message<?>>` express this policy using clear matchers:

~~~text
Authenticated HTTP handshake + allowed Origin + WSS
     |
     v
STOMP CONNECT + CSRF token
     |
     v
clientInboundChannel
     |
     v
AuthorizationManager<Message<?>>
     |
     +-- CONNECT/control frame: authenticated
     +-- MESSAGE /app/...: explicit role/action permission
     +-- SUBSCRIBE /topic/...: explicit role/room ACL permission
     +-- MESSAGE /topic/** or /queue/**: DENY
     +-- unknown/malformed: DENY
     |
     v
@MessageMapping business verification
     |
     v
Server-side broker publish with trusted actor/tenant/recipient
     |
     v
Only authorized subscriptions receive data
~~~

Remember: `/ws` is the handshake URL; `/app/**` is an application destination; `/topic/**` and `/queue/**` are broker destinations; `/user/**` is user-destination routing. Do not equate the right to **send** with the right to **subscribe**; do not treat HTTP authentication as sufficient for every STOMP frame; do not expect Spring to filter outbound messages automatically. **Start with DENY, open only the right frame types and destinations, and verify tenant/object policies at the business boundary.**

## Official Documentation

- [Spring Security 6.5 – WebSocket Security](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/websocket.html): annotation, message manager, inbound types, CSRF, origins, user destinations, and outbound notes.
- [Spring Security – @EnableWebSocketSecurity Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/socket/EnableWebSocketSecurity.html): declaring the `AuthorizationManager<Message<?>>` bean.
- [Spring Security 6.5 – MessageMatcherDelegatingAuthorizationManager.Builder Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.html): `simpMessageDestMatchers`, `simpSubscribeDestMatchers`, `nullDestMatcher`, `anyMessage`.
- [Spring Security 6.5 – MessageAuthorizationContext Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/messaging/access/intercept/MessageAuthorizationContext.html): `getMessage()` and `getVariables()`.
- [Spring Framework – STOMP Message Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html): endpoints, application destination prefixes, broker prefixes.
- [Spring Framework – STOMP Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html): handshake Principal, STOMP headers, and ChannelInterceptor.
- [Spring Framework – User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html): `/user`, `@SendToUser`, `convertAndSendToUser`.
- [Spring Framework – WebSocket Allowed Origins](https://docs.spring.io/spring-framework/reference/web/websocket/server.html#websocket-server-allowed-origins): origin restriction and browser/non-browser boundary.
- [Spring Security – CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF token lifecycle.
