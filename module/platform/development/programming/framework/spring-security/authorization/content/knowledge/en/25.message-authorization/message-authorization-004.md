# simpDestMatchers, simpSubscribeDestMatchers, and simpTypeMatchers in Spring Security Messaging

> **Module:** Spring Security – authorization → **Message Authorization**. This lesson explains exactly how Spring Security 6.x authorizes incoming STOMP/WebSocket messages in an application: `simpDestMatchers` matches **destination**, `simpSubscribeDestMatchers` matches **SUBSCRIBE + destination**, and `simpTypeMatchers` matches **SimpMessageType**. The focus is on matcher ordering, preventing message spoofing into broker destinations (`/topic/**`, `/queue/**`), restricting SUBSCRIBE, protecting user destinations, and testing rules with `AuthorizationManager<Message<?>>`. Examples use Java 17+, Spring Boot 3.x, Spring Security 6.x, and JUnit 5.

## 1. Why Is HTTP Authorization Not Enough for WebSocket/STOMP?

In REST, the server typically checks permissions per HTTP request:

~~~text
GET  /api/chat/messages
POST /api/chat/send
~~~

With WebSocket/STOMP, however, the initial HTTP request primarily opens the connection. After the connection upgrade, a client can send **many different frames** over the same socket:

~~~text
CONNECT
SUBSCRIBE destination:/topic/public-updates
SEND      destination:/app/chat.send
SEND      destination:/topic/system/announcements
SUBSCRIBE destination:/queue/private-all
DISCONNECT
~~~

If you only check whether the user is allowed to open the WebSocket, you have **not** protected the individual operations performed over that channel.

Two classes of risk:

1. **Producer spoofing:** A client sends `SEND` directly to `/topic/system/announcements`, whereas only the server should publish system announcements.
2. **Unauthorized subscription snooping:** A client sends `SUBSCRIBE` to another topic/queue or a sensitive aggregate queue.

Therefore, Spring Security supports authorization on **inbound messages** using `@EnableWebSocketSecurity` and `AuthorizationManager<Message<?>>`.

### 1.1. Distinguishing STOMP Frames and SimpMessageType

| STOMP frame from client | Typical SimpMessageType | Destination? | Meaning |
| --- | --- | --- | --- |
| `CONNECT` | `CONNECT` | Usually no | Opens the STOMP session |
| `SEND` | `MESSAGE` | Yes | Request to send a message |
| `SUBSCRIBE` | `SUBSCRIBE` | Yes | Subscribes to receive a message stream |
| `UNSUBSCRIBE` | `UNSUBSCRIBE` | Usually no | Cancels a subscription ID |
| `DISCONNECT` | `DISCONNECT` | Usually no | Ends the session |
| Heartbeat/internal frames | `HEARTBEAT`/other types | Usually no | Connection coordination |

**Watch the naming:** The client uses the STOMP command `SEND`, yet Spring Messaging normally represents that inbound command as `SimpMessageType.MESSAGE`. Thus `simpTypeMatchers(MESSAGE)` matches message-send requests from clients, **not** merely `MESSAGE` frames pushed from the server to clients.

In Spring MVC annotated messaging, an application prefix such as `/app` typically routes to `@MessageMapping` handlers; broker prefixes such as `/topic`/`/queue` are served by the broker.

## 2. The Three Matchers in the Title: How Do Their Conditions Differ?

| Matcher | Evaluates | Matches Example | Does **Not** Match Example |
| --- | --- | --- | --- |
| `simpDestMatchers("/app/**")` | Destination matches pattern, **independent of SimpMessageType** | MESSAGE or SUBSCRIBE with destination `/app/chat.send` | CONNECT without destination |
| `simpSubscribeDestMatchers("/topic/**")` | Type = SUBSCRIBE **and** destination matches | SUBSCRIBE `/topic/news` | MESSAGE `/topic/news` |
| `simpTypeMatchers(SUBSCRIBE)` | Type = SUBSCRIBE, **regardless of destination** | Any SUBSCRIBE even on unfamiliar paths | MESSAGE, CONNECT |
| `simpMessageDestMatchers("/app/**")` | Type = MESSAGE **and** destination matches | Client SEND to `/app/chat.send` | SUBSCRIBE to `/app/chat.send` |
| `nullDestMatcher()` | No destination | Typical CONNECT, UNSUBSCRIBE, DISCONNECT | MESSAGE with a valid destination |
| `anyMessage()` | All messages not captured by prior rules | Catch-all | No exceptions |

`simpMessageDestMatchers` is an important variant alongside the three matchers in the title: it is usually safer than `simpDestMatchers` when the intent is to grant permission **only to send** to an application endpoint.

### 2.1. `simpDestMatchers` Does Not Default to SEND Only

~~~java
messages.simpDestMatchers("/app/admin/**")
        .hasRole("ADMIN");
~~~

This rule requires `ROLE_ADMIN` for messages with matching destinations, yet **does not restrict the message type**. Without an earlier rule, a SUBSCRIBE to `/app/admin/any` would also be permitted for an admin.

That does not mean the broker will return data to that subscription; it depends on routing/broker setup. Still, permission rules should be accurate to intent rather than relying on handlers happening to have no route.

### 2.2. `simpSubscribeDestMatchers` Addresses Permission to Read a Topic

~~~java
messages.simpSubscribeDestMatchers("/topic/rooms/*")
        .hasRole("MEMBER");
~~~

It applies to **SUBSCRIBE** on single-segment room topics. It **does not** grant clients permission to SEND directly to that broker topic.

Note, however, that a generic `ROLE_MEMBER` does not yet verify **which room** the user may enter; when rooms contain private data, a room-membership policy keyed by the target ID is required.

### 2.3. `simpTypeMatchers` Is Useful for Denying Undeclared Frames

~~~java
messages.simpTypeMatchers(
        SimpMessageType.MESSAGE,
        SimpMessageType.SUBSCRIBE)
    .denyAll();
~~~

Place this after permitted rules to **deny all unmatched SEND/SUBSCRIBE frames**. A `MESSAGE` targeting `/topic/admin/alerts` without a permitting rule will be blocked.

`simpTypeMatchers` does not inspect paths. Putting `simpTypeMatchers(MESSAGE).authenticated()` too early lets any logged-in user SEND to every destination; that is an anti-pattern.

## 3. Rule Ordering: First Matching Rule Wins

`MessageMatcherDelegatingAuthorizationManager` selects the matching rule in **declaration order**. A broad rule placed first can shadow narrower rules after it.

**Dangerously wrong:**

~~~java
messages
    .simpTypeMatchers(SimpMessageType.MESSAGE).authenticated()
    .simpMessageDestMatchers("/topic/system/**").denyAll()
    .anyMessage().denyAll();
~~~

A logged-in client sending `MESSAGE /topic/system/alerts` hits `MESSAGE.authenticated()` first and never reaches the deny rule. That can become a **message spoofing** path.

**Correct:**

~~~java
messages
    .simpMessageDestMatchers("/app/chat.send").hasRole("MEMBER")
    .simpTypeMatchers(SimpMessageType.MESSAGE).denyAll()
    .anyMessage().denyAll();
~~~

When a client sends SEND to `/app/chat.send`, the `MEMBER` role is checked; when a client sends SEND to broker path `/topic/system/**`, it falls through to deny-by-default.

### 3.1. Another Ordering Pitfall: Overly Broad Destination Matcher

~~~java
// NOT RECOMMENDED
messages
    .simpDestMatchers("/topic/**").authenticated()
    .simpSubscribeDestMatchers("/topic/admin/**").hasRole("ADMIN")
    .anyMessage().denyAll();
~~~

`simpDestMatchers("/topic/**")` captures **both MESSAGE and SUBSCRIBE**, so an authenticated user can SUBSCRIBE to the admin topic without `ROLE_ADMIN`. Change it to:

~~~java
messages
    .simpSubscribeDestMatchers("/topic/admin/**").hasRole("ADMIN")
    .simpSubscribeDestMatchers("/topic/public-updates").authenticated()
    .simpTypeMatchers(
            SimpMessageType.MESSAGE,
            SimpMessageType.SUBSCRIBE).denyAll()
    .anyMessage().denyAll();
~~~

There is no need to open `/topic/**` to client MESSAGE frames. Server-side `SimpMessagingTemplate` can publish internally through the broker; we are guarding **inbound client messages**, not applying the same logic to all server outbound traffic.

### 3.2. When Is `simpDestMatchers` Actually Useful?

- When the **exact same permission** is required for every message type sharing a given destination pattern.
- When combining a **narrower SUBSCRIBE deny rule first** with a broader destination rule afterward, backed by tests proving the unwanted branch is blocked.
- When migrating from legacy configurations that were destination-only and the team clearly understands the impact on MESSAGE/SUBSCRIBE.

If you want SEND only, prefer `simpMessageDestMatchers`. If you want listening only, prefer `simpSubscribeDestMatchers`.

## 4. Prefixes and the Actual Path of a STOMP Message

WebSocket message broker example:

~~~java
@Override
public void configureMessageBroker(
        MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setUserDestinationPrefix("/user");
}
~~~

| Prefix | Intended Handler | Principle |
| --- | --- | --- |
| `/app/**` | Spring `@MessageMapping` handler | Allow SEND with clear purpose and specific permissions |
| `/topic/**` | Broker broadcast | Allow client SUBSCRIBE only to authorized topics; normally **deny client SEND** |
| `/queue/**` | Broker queue destination | Grant SUBSCRIBE only to specific approved queues; do not open `/queue/**` |
| `/user/**` | Logical user destination | Can be translated by Spring into user/session-specific destinations |

These are configured application conventions, not mandatory STOMP protocol rules. Spring can use different prefixes. Matchers must match the **destination Spring actually receives**, not merely the URL shown in the UI.

### 4.1. Never Let Clients Impersonate a "System Producer"

Wrong:

~~~text
Client Alice:
  SEND destination:/topic/system/announcements
  body="Admin has approved your transfer"
~~~

If the broker accepts and distributes it, Alice has spoofed a system announcement.

Right:

~~~text
Client Alice:
  SEND destination:/app/chat.send
       |
       v
@MessageMapping("chat.send") + authorization + validation
       |
       v
Server sends through SimpMessagingTemplate
       |
       v
/topic/public-updates
       |
       v
Clients authorized to SUBSCRIBE that topic receive data
~~~

Client input must be validated: content, size, room membership, source identity, rate limits, and business rules. Do not trust a `sender` field in the payload; use the authenticated `Principal` from the session.

### 4.2. Do Not Open `SUBSCRIBE /queue/**` Arbitrarily

If a user destination such as `/user/queue/inbox` is translated by the framework into a physical queue with a session suffix, letting clients subscribe directly to `/queue/**` could create a path into another user's data. Spring docs emphasize restricting subscriptions and allowing only valid **logical user destinations** rather than broker queue wildcards.

Example:

~~~java
messages
    .simpSubscribeDestMatchers("/user/queue/inbox").authenticated()
    .simpTypeMatchers(SimpMessageType.SUBSCRIBE).denyAll();
~~~

The `/user/queue/inbox` → physical broker destination mapping is managed by the framework, not by clients manually specifying `/queue/user-<id>`.

### 4.3. A Tenant/Room ID in the Destination Does Not Prove Permission

If the destination is `/topic/rooms/42`, a user with `ROLE_MEMBER` is **not necessarily** allowed to read room 42. You must:
1. Check the active Authentication.
2. Extract the room ID from a properly parsed destination.
3. Check the principal's membership in that room against trusted data.
4. Deny when the resource does not exist, is locked, or belongs to another tenant.
5. Evaluate at SUBSCRIBE time and consider revocation/lifecycle for long-lived subscriptions.

Do not trust a room ID or tenant ID in client headers as proof of membership.

## 5. Inbound WebSocket Control Architecture

~~~text
HTTP GET /ws (WebSocket handshake)
  |
  +-- Servlet Spring Security: authenticates HTTP session/cookie/Basic
  +-- WebSocket origin policy at the endpoint
  |
  v
STOMP CONNECT (requires CSRF token by default with @EnableWebSocketSecurity)
  |
  v
clientInboundChannel
  |
  +-- SecurityContext obtained from user/session
  +-- CSRF / same-origin defense
  +-- AuthorizationChannelInterceptor
  |       |
  |       v
  |    AuthorizationManager<Message<?>>
  |       |
  |       +-- nullDestMatcher
  |       +-- simpSubscribeDestMatchers
  |       +-- simpDestMatchers / simpMessageDestMatchers
  |       +-- simpTypeMatchers
  |       +-- anyMessage
  |
  +-- DENY: do not forward inbound frame to business/broker action
  |
  +-- ALLOW: @MessageMapping or broker routing
                    |
                    v
             clientOutboundChannel
                    |
                    v
               subscribed clients
~~~

**Crucial boundary:** Spring Security WebSocket message authorization primarily protects **`clientInboundChannel`**, and does not re-check every message on `clientOutboundChannel`. A single server-published message can reach many subscribers; therefore, permissions must be checked on SUBSCRIBE, not only on SEND.

Additionally, an authorization rule may permit a client to **subscribe**, yet the broker/application can still reject it if the destination does not exist or the protocol is invalid. Conversely, the fact that a message is routed by the broker does not prove room/tenant policies were properly checked.

## 6. Permission Model for a Chat and Notification Application

Choose client types: unauthenticated anonymous, logged-in MEMBER, and logged-in ADMIN with `ROLE_ADMIN`.

| Message type | Destination | MEMBER | ADMIN | Why |
| --- | --- | --- | --- | --- |
| CONNECT | null | Allow (still needs CSRF) | Allow (still needs CSRF) | Connection by authenticated user |
| SUBSCRIBE | `/topic/public-updates` | Allow | Allow | Topic for all logged-in users |
| SUBSCRIBE | `/topic/rooms/42` | Allow* | Allow* | Demo checks MEMBER; production must check room membership |
| SUBSCRIBE | `/topic/admin/alerts` | Deny | Allow | Administrative channel |
| SUBSCRIBE | `/user/queue/inbox` | Allow | Allow | Logical personal queue |
| SUBSCRIBE | `/user/queue/errors` | Allow | Allow | Session error channel |
| SUBSCRIBE | `/queue/private-all` | Deny | Deny | Do not expose raw broker queues directly |
| SUBSCRIBE | `/app/admin/publish` | Deny | Deny | Disallow listening to command destinations |
| MESSAGE (SEND) | `/app/chat.send` | Allow | Allow | Send via application handler |
| MESSAGE (SEND) | `/app/admin/publish` | Deny | Allow | Publish announcement |
| MESSAGE (SEND) | `/topic/public-updates` | Deny | Deny | Disallow direct broker topic publishing |
| MESSAGE (SEND) | `/topic/admin/alerts` | Deny | Deny | Do not spoof server notifications |
| MESSAGE (SEND) | `/app/unknown` | Deny | Deny | No matching rule |
| MESSAGE (SEND) | `/queue/private-all` | Deny | Deny | Do not send directly to broker queue |

*Role-only demo is an **intentional simplification**; rooms holding private data must enforce per-room ownership/membership.

The configuration in the next section places `SUBSCRIBE /app/**` as DENY **before** the `simpDestMatchers("/app/admin/**")` rule. This is a clear example of how a destination-only matcher must be positioned carefully so it does not accidentally permit another message type.

## 7. Spring Boot 3.x / Spring Security 6.x / Java 17+ Project

Demo project:
- Uses Spring MVC + STOMP WebSocket message broker.
- Has an HTTP security filter chain for the handshake.
- Enables Spring Security message authorization with `@EnableWebSocketSecurity`.
- Has two controllers handling client `SEND` and server publishing via `SimpMessagingTemplate`.
- Creates JUnit tests on the **actual `AuthorizationManager` bean**, with simulated inbound messages carrying exact types/destinations to test the policy without opening a socket.
- Does not disable WebSocket CONNECT CSRF: end-to-end STOMP clients must supply a valid token.

The tests below are **policy-level integration tests**: they boot the Spring Context and exercise the real bean, without testing a full socket/CSRF handshake. Because no network connection is needed, the tests run reliably in CI. Production should add end-to-end WebSocket STOMP tests to verify HTTP authentication, Origin, CONNECT CSRF, routing, and broker behavior.

### 7.1. `settings.gradle`

~~~groovy
rootProject.name = 'stomp-message-authorization-lab'
~~~

### 7.2. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo.stompauth'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-messaging'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

**Why is `spring-security-messaging` needed?** Message authorization matchers and managers live in this module, not in regular `spring-security-web`. `spring-boot-starter-websocket` pulls in Spring WebSocket/STOMP components. Do not use WebFlux's `ServerHttpSecurity`/`SecurityWebFilterChain` to configure this **Servlet WebSocket MessageBroker** lesson.

### 7.3. `src/main/java/demo/stompauth/StompAuthApplication.java`

~~~java
package demo.stompauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StompAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(StompAuthApplication.class, args);
    }
}
~~~

### 7.4. `src/main/java/demo/stompauth/BrokerConfiguration.java`

~~~java
package demo.stompauth;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class BrokerConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(
            StompEndpointRegistry registry) {
        // Same-origin by default. Do not open setAllowedOriginPatterns("*").
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(
            MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user");
    }
}
~~~

`/ws` is the HTTP handshake endpoint, not a STOMP destination pattern. `/app` goes to `@MessageMapping`; `/topic` and `/queue` belong to the broker; `/user` is the prefix for user destination conversion. Configuring the broker does not automatically enforce per-frame authorization; Message Security below is required.

To avoid exposing private data, do not configure the broker with a global wildcard subscription and never treat a prefix as proof of tenant/room membership.

### 7.5. `src/main/java/demo/stompauth/MessageSecurityConfiguration.java`

~~~java
package demo.stompauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
public class MessageSecurityConfiguration {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            // CONNECT/DISCONNECT/UNSUBSCRIBE typically have no destination.
            .nullDestMatcher().authenticated()

            // Exception: user/session error notification channel.
            .simpSubscribeDestMatchers("/user/queue/errors").permitAll()

            // Granted subscriptions.
            .simpSubscribeDestMatchers("/user/queue/inbox")
                .hasRole("MEMBER")
            .simpSubscribeDestMatchers("/topic/public-updates")
                .authenticated()
            .simpSubscribeDestMatchers("/topic/rooms/*")
                .hasRole("MEMBER")
            .simpSubscribeDestMatchers("/topic/admin/**")
                .hasRole("ADMIN")

            // Block SUBSCRIBE to application command destinations.
            // MUST precede simpDestMatchers("/app/admin/**").
            .simpSubscribeDestMatchers("/app/**").denyAll()

            // Destination-only: matches any type with this destination.
            // SUBSCRIBE /app/** above is already blocked;
            // MESSAGE /app/admin/** commands require ROLE_ADMIN.
            .simpDestMatchers("/app/admin/**").hasRole("ADMIN")

            // Grant MESSAGE (STOMP SEND) only for the chat command.
            .simpMessageDestMatchers("/app/chat.send")
                .hasRole("MEMBER")

            // All other MESSAGE/SUBSCRIBE frames: deny.
            .simpTypeMatchers(
                SimpMessageType.MESSAGE,
                SimpMessageType.SUBSCRIBE).denyAll()

            // Any remaining message types: deny.
            .anyMessage().denyAll();

        return messages.build();
    }
}
~~~

**Line-by-line order analysis:**

1. `nullDestMatcher().authenticated()` allows messages without a destination **when the user is authenticated**. Spring docs use this for control frames like CONNECT, UNSUBSCRIBE, and DISCONNECT; the CSRF requirement on CONNECT is a **separate check**, not replaced by `authenticated()`.
2. `simpSubscribeDestMatchers("/user/queue/errors").permitAll()` permits subscribing to the error channel at the *authorization* level. It **does not** turn the HTTP handshake or CONNECT anonymous if auth/CSRF is required elsewhere.
3. `/user/queue/inbox` requires `MEMBER`, without opening physical `/queue/**`.
4. `/topic/public-updates` requires an authenticated user.
5. `/topic/rooms/*` requires `MEMBER`; real products must verify per-room membership.
6. `/topic/admin/**` requires `ADMIN` on SUBSCRIBE.
7. `simpSubscribeDestMatchers("/app/**").denyAll()` blocks subscribing to the command namespace.
8. `simpDestMatchers("/app/admin/**").hasRole("ADMIN")` illustrates a destination-only matcher. Because rule 7 already covers every `SUBSCRIBE /app/**`, ADMIN does not accidentally get to listen to the command path in this policy.
9. `simpMessageDestMatchers("/app/chat.send").hasRole("MEMBER")` is a **SEND-only** rule, avoiding granting SUBSCRIBE on the same path.
10. `simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()` blocks all send/subscribe frames without a specific rule.
11. `anyMessage().denyAll()` blocks every remaining type outside the branches evaluated above.

**Constraint:** Each rule using `hasRole("MEMBER")` maps to Spring authority `ROLE_MEMBER`, and `hasRole("ADMIN")` maps to `ROLE_ADMIN`. Do not include the `ROLE_` prefix inside the `hasRole` argument.

**Missing-destination caveat:** `nullDestMatcher` relies on the absence of a destination, so it could also match an artificially constructed `MESSAGE`/`SUBSCRIBE` lacking a destination. In valid STOMP protocol usage, SEND/SUBSCRIBE require a destination. Therefore, blocking malformed frames must be enforced at protocol/broker validation and tested end-to-end; do not equate `nullDestMatcher` with a strict command allowlist. If you need to block such malformed frames directly in `AuthorizationManager`, write a custom matcher checking both type and null destination before this rule.

### 7.6. `src/main/java/demo/stompauth/HttpSecurityConfiguration.java`

~~~java
package demo.stompauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HttpSecurityConfiguration {

    @Bean
    SecurityFilterChain httpSecurity(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/ws", "/csrf")
                            .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                // Do not disable default CSRF!
                .build();
    }

    @Bean
    InMemoryUserDetailsManager users() {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails member = User.withUsername("member")
                .password(encoder.encode("member-pass"))
                .roles("MEMBER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN", "MEMBER")
                .build();

        return new InMemoryUserDetailsManager(member, admin);
    }
}
~~~

The HTTP layer requires authentication for `/ws`. **Do not equate them:** HTTP `requestMatchers("/ws")` checks only the handshake, whereas `simpSubscribeDestMatchers(...)` checks subsequent STOMP messages. In browsers, the `WebSocket` API does not let scripts set arbitrary Authorization headers on the handshake; real deployments typically use HTTP-authenticated sessions/cookies or a designed and verified token flow. HTTP Basic here merely illustrates server-side authentication; it is not a promise that every browser STOMP client can send a custom Basic header.

### 7.7. `src/main/java/demo/stompauth/CsrfController.java`

~~~java
package demo.stompauth;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfController {

    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken token) {
        return token;
    }
}
~~~

For session/cookie-based clients, the application can expose a CSRF token from a protected endpoint to be sent in **STOMP CONNECT headers**. The token must be bound to the CSRF repository and matching session/client identity, never hardcoded or replaced by an arbitrary client-side string. If using SockJS, HTTP transport CSRF and STOMP CONNECT CSRF must be managed separately; do not disable CSRF protection application-wide.

### 7.8. `src/main/java/demo/stompauth/MessagingController.java`

~~~java
package demo.stompauth;

import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

@Controller
public class MessagingController {

    public record ChatInput(String text) {}

    private final SimpMessagingTemplate outbound;

    public MessagingController(SimpMessagingTemplate outbound) {
        this.outbound = outbound;
    }

    @MessageMapping("/chat.send")
    public void chat(ChatInput input, Principal principal) {
        if (input == null
                || input.text() == null
                || input.text().isBlank()
                || input.text().length() > 500) {
            throw new IllegalArgumentException("Invalid text");
        }

        // Sender taken from trusted Principal, not from payload.
        String body = principal.getName() + ": " + input.text();
        outbound.convertAndSend("/topic/public-updates", body);
    }

    @MessageMapping("/admin/publish")
    public void announcement(ChatInput input, Principal principal) {
        if (input == null
                || input.text() == null
                || input.text().isBlank()
                || input.text().length() > 300) {
            throw new IllegalArgumentException("Invalid announcement");
        }

        outbound.convertAndSend(
                "/topic/admin/alerts",
                "Admin " + principal.getName() + ": " + input.text());
    }
}
~~~

`/app/chat.send` routes to `@MessageMapping("/chat.send")`; `MEMBER` clients are permitted to SEND via the manager. The server publishes to `/topic/public-updates` with `SimpMessagingTemplate`; clients receive it only if allowed to SUBSCRIBE. Likewise, `/app/admin/publish` is an `ADMIN` command and only the server publishes to `/topic/admin/alerts`.

This controller **does not perform** HTML/Markdown rendering validation for clients; the receiving UI must escape text to prevent XSS, and rate limits, payload schemas, and auditing should be added as needed. Never place a sensitive room ID inside the payload and assume `hasRole("MEMBER")` suffices to post to every room.

## 8. Testing AuthorizationManager Directly with JUnit 5

Instead of opening a real network WebSocket connection, construct a Spring `Message<?>` with:
- `SimpMessageType`;
- destination;
- a test-constructed `Authentication`.

Then call `AuthorizationManager<Message<?>>.authorize(...)` to inspect `AuthorizationResult.isGranted()`. This is a **policy-bean integration test**, not an end-to-end STOMP connection test. It verifies the exact ordering, type/destination, and role logic in `MessageSecurityConfiguration`.

### 8.1. `src/test/java/demo/stompauth/MessageAuthorizationPolicyTest.java`

~~~java
package demo.stompauth;

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
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(classes = StompAuthApplication.class)
class MessageAuthorizationPolicyTest {

    @Autowired
    AuthorizationManager<Message<?>> manager;

    private Authentication member() {
        return UsernamePasswordAuthenticationToken.authenticated(
                "member",
                "test-only",
                List.of(new SimpleGrantedAuthority("ROLE_MEMBER")));
    }

    private Authentication admin() {
        return UsernamePasswordAuthenticationToken.authenticated(
                "admin",
                "test-only",
                List.of(
                        new SimpleGrantedAuthority("ROLE_ADMIN"),
                        new SimpleGrantedAuthority("ROLE_MEMBER")));
    }

    private Authentication anonymous() {
        return new AnonymousAuthenticationToken(
                "test-key",
                "anonymous",
                List.of(
                        new SimpleGrantedAuthority("ROLE_ANONYMOUS")));
    }

    private Message<?> inbound(
            SimpMessageType type,
            String destination) {

        SimpMessageHeaderAccessor accessor =
                SimpMessageHeaderAccessor.create(type);

        if (destination != null) {
            accessor.setDestination(destination);
        }

        accessor.setLeaveMutable(true);

        return MessageBuilder.createMessage(
                new byte[0],
                accessor.getMessageHeaders());
    }

    private boolean granted(
            Authentication actor,
            SimpMessageType type,
            String destination) {

        AuthorizationResult result = manager.authorize(
                () -> actor,
                inbound(type, destination));

        // Catch-all in policy must always return a decision, never null.
        assertNotNull(result, "Policy returned no decision");
        return result.isGranted();
    }

    @Test
    void memberMaySendChatCommand() {
        assertTrue(granted(
                member(),
                SimpMessageType.MESSAGE,
                "/app/chat.send"));
    }

    @Test
    void anonymousMayNotSendChatCommand() {
        assertFalse(granted(
                anonymous(),
                SimpMessageType.MESSAGE,
                "/app/chat.send"));
    }

    @Test
    void memberCannotSendAdminCommand() {
        assertFalse(granted(
                member(),
                SimpMessageType.MESSAGE,
                "/app/admin/publish"));
    }

    @Test
    void adminMaySendAdminCommand() {
        assertTrue(granted(
                admin(),
                SimpMessageType.MESSAGE,
                "/app/admin/publish"));
    }

    @Test
    void memberMaySubscribePublicUpdates() {
        assertTrue(granted(
                member(),
                SimpMessageType.SUBSCRIBE,
                "/topic/public-updates"));
    }

    @Test
    void anonymousMayNotSubscribePublicUpdates() {
        assertFalse(granted(
                anonymous(),
                SimpMessageType.SUBSCRIBE,
                "/topic/public-updates"));
    }

    @Test
    void memberMaySubscribeRoomTopicUnderDemoRolePolicy() {
        assertTrue(granted(
                member(),
                SimpMessageType.SUBSCRIBE,
                "/topic/rooms/42"));
    }

    @Test
    void memberCannotSubscribeAdminTopic() {
        assertFalse(granted(
                member(),
                SimpMessageType.SUBSCRIBE,
                "/topic/admin/alerts"));
    }

    @Test
    void adminMaySubscribeAdminTopic() {
        assertTrue(granted(
                admin(),
                SimpMessageType.SUBSCRIBE,
                "/topic/admin/alerts"));
    }

    @Test
    void memberMaySubscribeOwnLogicalInbox() {
        assertTrue(granted(
                member(),
                SimpMessageType.SUBSCRIBE,
                "/user/queue/inbox"));
    }

    @Test
    void errorsQueueIsAllowedAtRuleLevel() {
        assertTrue(granted(
                anonymous(),
                SimpMessageType.SUBSCRIBE,
                "/user/queue/errors"));
    }

    @Test
    void directBrokerQueueSubscriptionIsDenied() {
        assertFalse(granted(
                member(),
                SimpMessageType.SUBSCRIBE,
                "/queue/private-all"));
    }

    @Test
    void clientCannotPublishToTopic() {
        assertFalse(granted(
                member(),
                SimpMessageType.MESSAGE,
                "/topic/public-updates"));
    }

    @Test
    void evenAdminCannotPublishDirectlyToBroker() {
        assertFalse(granted(
                admin(),
                SimpMessageType.MESSAGE,
                "/topic/admin/alerts"));
    }

    @Test
    void adminCannotSubscribeApplicationCommand() {
        assertFalse(granted(
                admin(),
                SimpMessageType.SUBSCRIBE,
                "/app/admin/publish"));
    }

    @Test
    void memberCannotSubscribeChatCommand() {
        assertFalse(granted(
                member(),
                SimpMessageType.SUBSCRIBE,
                "/app/chat.send"));
    }

    @Test
    void unknownApplicationMessageIsDenied() {
        assertFalse(granted(
                admin(),
                SimpMessageType.MESSAGE,
                "/app/unknown"));
    }

    @Test
    void authenticatedConnectPassesRuleButStillNeedsCsrf() {
        assertTrue(granted(
                member(),
                SimpMessageType.CONNECT,
                null));
    }

    @Test
    void anonymousConnectIsRejectedByAuthorizationRule() {
        assertFalse(granted(
                anonymous(),
                SimpMessageType.CONNECT,
                null));
    }

    @Test
    void authenticatedDisconnectPassesNullDestinationRule() {
        assertTrue(granted(
                member(),
                SimpMessageType.DISCONNECT,
                null));
    }
}
~~~

### 8.2. Why Does the Test Use `SimpMessageHeaderAccessor`?

Spring Security matchers read **Simp headers** to distinguish `SimpMessageType` and destination, rather than inspecting only the body. A test creating `GenericMessage<>("some text")` with empty headers and expecting it to behave as a STOMP SEND will fail to match properly. `SimpMessageHeaderAccessor.create(type)` and `setDestination` produce messages carrying the exact headers matchers rely on.

### 8.3. Why Does the Test Use `AuthorizationResult`?

In Spring Security 6.5, the modern API provides:

~~~java
AuthorizationResult result = manager.authorize(
        () -> authentication,
        message);

boolean allowed = result != null && result.isGranted();
~~~

`result == null` can mean the manager abstained without a decision. The sample uses `anyMessage().denyAll()`, so an explicit decision is expected for every tested message. In custom systems, **never** treat null/no decision as allow by default.

Spring Security 6.5 still has `check(...)`, yet that method is deprecated in favor of `authorize(...)`; if using an older version, check the exact API before copying the tests.

### 8.4. Test Matrix and What Remains Untested

| Test Group | Proves | Does Not Prove |
| --- | --- | --- |
| MEMBER MESSAGE `/app/chat.send` allow | `simpMessageDestMatchers` rule matches properly | Payload validity or business handler execution |
| MEMBER MESSAGE broker path deny | `simpTypeMatchers(MESSAGE).denyAll()` catches properly | External broker relay actually blocks at network layer |
| ADMIN SUBSCRIBE `/app/admin/publish` deny | SUBSCRIBE deny rule precedes destination matcher | Transport protocol rejects all malformed frames |
| MEMBER SUBSCRIBE `/topic/admin/alerts` deny | ADMIN-only subscription | Topic exists and broker delivers data |
| No-destination CONNECT | `nullDestMatcher` evaluates role/auth | **CONNECT CSRF** or Origin verification |
| SUBSCRIBE `/user/queue/inbox` allow | Logical user path is allowed | Zero user-destination routing bugs at runtime |

Very important limitation: JUnit calling the manager directly **does not** test the WebSocket HTTP handshake, STOMP parser, CONNECT CSRF, user destination translation, authenticated `Principal` in the session, or actual broker delivery. A production system must add end-to-end tests across those boundaries.

### 8.5. Run Commands

With the project's Gradle wrapper:

~~~bash
./gradlew test --tests demo.stompauth.MessageAuthorizationPolicyTest
./gradlew bootRun
~~~

Windows:

~~~text
gradlew.bat test --tests demo.stompauth.MessageAuthorizationPolicyTest
gradlew.bat bootRun
~~~

The tests use the Spring Context and JUnit assertions; there is no `System.out.println` in the code, so there is no fixed business stdout. The expected outcome is that all tests pass; real execution with the chosen Java 17/Boot 3.x/Security 6.x versions is required to confirm.

## 9. STOMP CONNECT, CSRF, and Same Origin

A WebSocket connection spans two different boundaries:

~~~text
HTTP GET /ws
  -> handshake authentication and origin policy

STOMP CONNECT frame
  -> authentication/session association
  -> CSRF in STOMP headers (default with @EnableWebSocketSecurity)
  -> nullDestMatcher rule

STOMP SUBSCRIBE/SEND frames
  -> Spring Security message authorization manager
~~~

WebSocket browser connections are not governed by the Same-Origin Policy the way regular XHR requests are. A malicious site could try opening a WebSocket to a logged-in backend using cookies, which is why Origin/allowed-origins checks and CSRF on STOMP CONNECT are necessary.

Spring Security 6.5 documentation states that `@EnableWebSocketSecurity` requires a **CSRF token in STOMP CONNECT headers** by default. `nullDestMatcher().authenticated()` **does not replace** CSRF verification and does not enforce Same-Origin on its own.

### 9.1. Why Not Attach CSRF to Every SEND?

Spring Security uses STOMP CONNECT CSRF to protect connection/session establishment against Cross-Site WebSocket Hijacking. HTTP CSRF filters apply to HTTP requests; STOMP frames need their own protection mechanism. Do not assume the HTTP filter inspects individual STOMP SEND frames.

### 9.2. Obtaining the CSRF Token and Sending It in CONNECT

A browser/session scenario:

~~~text
1. Browser logs in over HTTPS -> authenticated session.
2. GET /csrf (preserving cookies and origin).
3. JavaScript reads token and header name from response.
4. Browser opens WebSocket /ws.
5. STOMP CONNECT uses headers:
       X-CSRF-TOKEN: <session-token>
6. Server verifies token and matching session before accepting CONNECT.
7. Only then SUBSCRIBE/SEND with message authorization.
~~~

**`<session-token>` is an illustrative placeholder, not a real token.** Header and token names may vary depending on `CsrfTokenRepository`; read them from the real response. Never store secrets in hardcoded JS or write raw tokens to logs. If using SockJS, HTTP transport and CONNECT headers behave differently; never disable CSRF across the entire API just to "fix connect errors."

### 9.3. CORS and WebSocket Origins

CORS is a browser mechanism for HTTP fetch; WebSockets have separate Origin handling. Spring WebSocket endpoints use allowed origins; never allow all origins with `setAllowedOriginPatterns("*")` without a verified auth/CSRF model. Distinguish:
- May a trusted browser origin connect?
- Is the user/session authenticated?
- Does STOMP CONNECT carry a valid CSRF token?
- Is SUBSCRIBE/SEND authorized for the destination?

All four may require separate checks. Never use `permitAll("/ws/**")` or disable CSRF to mask a misconfigured STOMP client.

## 10. Custom Policies by Room or Tenant

Role-only example:

~~~java
messages.simpSubscribeDestMatchers("/topic/rooms/*")
        .hasRole("MEMBER");
~~~

**Insufficient** when each room has distinct participants. Two people who both hold `ROLE_MEMBER` can belong to completely different rooms.

Correct model:

~~~text
SUBSCRIBE /topic/rooms/42
  |
  +-- authenticated principal = alice
  +-- server parses roomId=42
  +-- trusted repository: room 42 belongs to tenant acme
  +-- membership repository: alice active in room 42?
  +-- policy: room status allows subscription?
  |
  +-- allow/deny
~~~

Spring Security can use:

~~~java
// ILLUSTRATIVE: manager must be implemented by the application
messages.simpSubscribeDestMatchers("/topic/rooms/*")
        .access(roomMembershipAuthorizationManager);
~~~

This is an **integration snippet**; `roomMembershipAuthorizationManager` has no implementation in the demo project. It must be an `AuthorizationManager<MessageAuthorizationContext<?>>` handling principal, destination patterns, database truth, and error handling. If the policy backend is unreachable, **never** return allow. Never treat `roomId` or `tenantId` in STOMP headers as proof of membership.

### 10.1. Subscription Lifecycle and Revocation

A SUBSCRIBE is allowed at 10:00. At 10:05 an admin revokes room membership. The broker may already hold the subscription and continue delivering subsequent messages because Spring Security does not re-authorize every outbound message.

For sensitive data, design:
- Active unsubscribe/session-close mechanisms when roles/memberships are revoked.
- Invalidation events and policy revisions so nodes update quickly.
- Periodic/conditional re-authorization where appropriate.
- Broker-level authorization or per-tenant topic isolation when using an external broker.
- Tests covering post-revocation state, not only the initial SUBSCRIBE moment.

**Never claim "inbound security guarantees all outbound traffic is safe."** Checking subscriptions is a critical gate, yet mid-session permission changes require additional policy.

### 10.2. User Destinations and Spoofed Identity

The server can send privately:

~~~java
// ILLUSTRATIVE inside a service with template and verified recipient ID.
messagingTemplate.convertAndSendToUser(
        trustedRecipientName,
        "/queue/inbox",
        eventPayload);
~~~

`trustedRecipientName` must come from a trusted domain/user directory; `eventPayload` must be constructed from authorized business data. Clients subscribe to logical `/user/queue/inbox`; never allow clients to specify another user's physical destination. Never use `fromUser` in the payload to decide the publishing Principal.

### 10.3. Multi-Tenancy

Do not mix tenants into `/topic/rooms/{id}` unless IDs are globally unique and broadcasting separates tenants. Use a scope such as:

~~~text
tenant_id + room_id + subject_id + permission
~~~

Check permissions before subscribing, and when the server publishes, ensure the destination is built from the tenant/resource verified by the domain service. Never concatenate raw user-supplied strings and publish straight to sensitive broker topics.

## 11. Matcher Builder and Extension Options

Beyond the three core matchers:

| API | When to Use |
| --- | --- |
| `simpDestMatchers` | Match destination regardless of type |
| `simpMessageDestMatchers` | Match MESSAGE (STOMP SEND) + destination |
| `simpSubscribeDestMatchers` | Match SUBSCRIBE + destination |
| `simpTypeMatchers` | Match `SimpMessageType` enum |
| `nullDestMatcher` | Match missing destination, typically control frames |
| `anyMessage` | Catch-all for unmatched messages |
| `matchers(customMessageMatcher)` | Plug in a specialized matcher if type + headers + tenant are needed |
| `access(customAuthorizationManager)` | Custom decision using object/domain policy |

In Spring Security 6.5, destination patterns may default to `AntPathMatcher`, and newer versions/configs may support a `PathPatternMessageMatcher`-based builder. Wildcards `*`, `**`, slashes, URL encoding, and path variables must be tested against your exact version. Do not extrapolate assumptions from HTTP matchers like `requestMatchers("/**")` to STOMP without testing.

### 11.1. Pattern Overlap Errors

~~~java
messages
    .simpSubscribeDestMatchers("/topic/**").authenticated()
    .simpSubscribeDestMatchers("/topic/admin/**").hasRole("ADMIN");
~~~

In the configuration above, the second rule no longer protects properly because the broad matcher comes first.

Correct order:

~~~java
messages
    .simpSubscribeDestMatchers("/topic/admin/**").hasRole("ADMIN")
    .simpSubscribeDestMatchers("/topic/public/**").authenticated()
    .simpTypeMatchers(SimpMessageType.SUBSCRIBE).denyAll();
~~~

Even better for production: **avoid broad wildcards** unless every topic in that namespace truly shares the exact same security policy.

### 11.2. No Decision Must Never Turn Into Allow

If a custom `AuthorizationManager` finds no matching rule, it may return null/abstain depending on contract. Applications should include a catch-all deny and test every message type/destination path. Never write logic that treats `null decision => true`.

### 11.3. Why Role-Only Checks Are Not Enough

`hasRole("ADMIN")` proves the authority was granted in the authentication context, not that the client may send announcements on behalf of every tenant. Operations like transferring money, creating orders, joining rooms, or publishing audit logs must check business policies inside handlers/services even after the inbound message passes URL/role checks.

## 12. End-to-End Tests to Add Before Production

The policy-level tests in Section 8 are a first step. Real network tests can use a Spring STOMP client or equivalent test framework:

~~~text
1. HTTP login -> authenticated Principal/session.
2. GET /csrf -> token matching session.
3. WebSocket handshake /ws with valid cookies/origin.
4. STOMP CONNECT with matching CSRF header.
5. SUBSCRIBE /topic/public-updates as member -> subscription accepted.
6. SEND /app/chat.send -> server processes and publishes to topic.
7. SUBSCRIBE /topic/admin/alerts as member -> blocked.
8. SUBSCRIBE /topic/admin/alerts as admin -> subscription accepted.
9. SEND /topic/admin/alerts from client -> blocked.
10. SEND /app/admin/publish from admin -> only server emits notification.
11. CONNECT missing/wrong CSRF -> rejected.
12. Handshake from untrusted origin -> rejected.
13. Revoke membership mid-connection -> policy/connection responds per contract.
~~~

STOMP authorization failures typically produce an ERROR frame or connection termination, **not necessarily HTTP 403**, because the HTTP handshake has already finished. Tests must check STOMP frame behavior rather than inferring from `/ws` HTTP status.

### 12.1. Distinguishing Three Test Layers

| Layer | Verifies | Tooling |
| --- | --- | --- |
| Unit/policy | Matcher type/destination, first-match rules, role decisions | `AuthorizationManager.authorize` with Simp headers |
| Framework integration | Security bean wiring, inbound interceptors, authentication context | `@SpringBootTest` / messaging test setup |
| End-to-end socket | Handshake, CONNECT CSRF, Origin, broker routing, actual frames | WebSocket STOMP test client |

Never rest your entire security posture on a rule test using `GenericMessage` without Simp headers. And never treat policy unit tests as proof that browser CSRF is protected.

## 13. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Client can send to `/topic/system/**` | `simpDestMatchers("/topic/**").authenticated()` is too broad | Allow SEND only to valid `/app/**`, deny other MESSAGEs |
| Regular user subscribes to ADMIN topic | `/topic/**` rule precedes `/topic/admin/**` | Specific-before-general |
| `SUBSCRIBE /app/admin/**` is allowed | `simpDestMatchers` matches every type | Add subscribe deny earlier or use message-only matcher |
| `MESSAGE /topic/public-updates` slips through | `simpTypeMatchers(MESSAGE).authenticated()` placed too early | Use `denyAll` fallback |
| No data arrives on `/user/queue/inbox` | Confused logical user prefix with physical broker queue | Use proper user-destination routing |
| User hears another user's queue | Direct subscription to `/queue/**` | Never open broker queue wildcards |
| CONNECT fails despite valid HTTP Basic | Missing STOMP CONNECT CSRF | Fetch session-matching CSRF token and send in headers |
| `GET /ws` returns 101 but SUBSCRIBE is denied | HTTP handshake and message authorization are separate | Debug inbound matcher/authority |
| Policy test always returns null decision | Missing Simp headers/type/destination | Construct message with `SimpMessageHeaderAccessor` |
| Admin has SEND permission yet is still blocked | Deny matcher precedes allow | Order specific allows before catch-all |
| Unauthenticated user subscribes to errors | `permitAll` rule, yet CONNECT/handshake still blocks | Understand each layer and CSRF |
| Room MEMBER reads foreign room | Role-only check, no membership check | Custom manager + trusted domain DB |
| Broker relay permits traffic violating Spring policy | Security only guards Spring inbound; broker path differs | Broker ACLs/network isolation |
| Revoked user still receives data | Existing subscription does not re-check outbound | Close/unsubscribe/revocation handling |
| Attacker spoofs sender in payload | Trusting `fromUser` field | Derive Principal from session |
| WebSocket from evil origin is accepted | Wildcard origins / CSRF disabled | Allowed Origin + STOMP CSRF |
| Test mistakenly uses `SimpMessageType.SEND` | Spring's enum uses MESSAGE | Use `SimpMessageType.MESSAGE` |
| HTTP `requestMatchers` fails to block STOMP SEND | Applies only to HTTP handshake | Use inbound Message Security |
| Using WebFlux config for servlet STOMP | Wrong stack | Use `@EnableWebSocketMessageBroker` and MessageSecurity |
| Checking only inbound SEND, not SUBSCRIBE | Subscribers can receive sensitive data | Authorize subscriptions separately |
| Catching custom policy exception and allowing | Fail-open on DB/PDP error | Deny/close, log reason code |
| Logging raw STOMP payloads/auth tokens | Sensitive data exposure | Redaction, limit debug logs |
| Subscriber receives multi-tenant events | Server publishes to shared topic | Tenant isolation, resource-aware routing |

## 14. Pre-Deployment Security Checklist

1. Are the HTTP handshake endpoint and STOMP destinations clearly separated?
2. Are `@EnableWebSocketMessageBroker` and `@EnableWebSocketSecurity` configured properly?
3. Is there an `AuthorizationManager<Message<?>>` bean using the version-appropriate builder?
4. Is `simpDestMatchers` used intentionally across multiple message types?
5. If SEND-only is desired, was `simpMessageDestMatchers` used?
6. If listening-only is desired, was `simpSubscribeDestMatchers` used?
7. Is `simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()` placed after allow rules?
8. Does `anyMessage().denyAll()` block all remaining messages?
9. Are specific rules placed before wildcard/general rules?
10. Are clients blocked from direct SEND to `/topic/**`, `/queue/**`?
11. Are clients blocked from free SUBSCRIBE to `/queue/**` physical destinations?
12. Are logical `/user/**` queues restricted to the matching principal?
13. Is tenant/room membership checked against trusted domain data?
14. Do role labels match Spring Security's `ROLE_` convention?
15. Is `Principal` derived from the authenticated session rather than the payload?
16. Does STOMP CONNECT enforce a valid CSRF token and Origin restrictions?
17. Are HTTP handshake/auth and STOMP CONNECT tested separately?
18. Do policy tests use `SimpMessageHeaderAccessor` with accurate types/destinations?
19. Are both SEND and SUBSCRIBE tested for the same destination to catch non-type-specific matchers?
20. Are unauthenticated, MEMBER, ADMIN, and undeclared paths tested?
21. When using an external broker, is the broker protected from direct client bypass?
22. When permissions are revoked, are existing subscriptions/long-lived sockets handled?
23. Is outbound data routed to the right tenant/user without accidental broadcasts?
24. Do logs redact tokens and sensitive payloads?
25. Are rate limits, message size limits, abuse, and spam controls in place?
26. Are regression tests run when upgrading Spring Boot/Spring Security/STOMP brokers?

## 15. Practice Exercises

**Exercise 1 – Matcher differences.** Create a MESSAGE and a SUBSCRIBE with the same destination `/app/chat.send`. Prove `simpDestMatchers` can match both, whereas `simpMessageDestMatchers` matches only MESSAGE.

**Exercise 2 – Specific-before-general.** Place `simpSubscribeDestMatchers("/topic/**").authenticated()` before `/topic/admin/**`. Write a MEMBER SUBSCRIBE test for the admin topic and observe the policy flaw; fix the order.

**Exercise 3 – Broker spoofing.** Construct a MESSAGE `/topic/system/announcements` with `ROLE_ADMIN`. A safe policy still denies it. Explain why only server-side producers should publish.

**Exercise 4 – User queues.** Compare SUBSCRIBE `/user/queue/inbox` with `/queue/private-all`, explaining logical user-destination conversion and the risk of physical broker wildcards.

**Exercise 5 – Type fallback.** Remove `simpTypeMatchers(MESSAGE,SUBSCRIBE).denyAll()` while keeping `anyMessage().denyAll()`; test that behavior is unchanged, and explain why the type fallback rule remains helpful for expressing policy clearly.

**Exercise 6 – CSRF CONNECT.** Run a STOMP browser client with and without a valid CSRF header. Distinguish CONNECT denial due to an invalid token from SUBSCRIBE denial due to a missing role.

**Exercise 7 – Room membership.** Replace `hasRole("MEMBER")` on `/topic/rooms/*` with a custom manager reading room membership from a trusted repository. Test that a user in room A cannot read room B.

**Exercise 8 – Token change.** Revoke `ROLE_ADMIN` while a socket remains open. Design session closure/forced unsubscribe or policy revalidation and verify the broker stops delivering private data.

**Exercise 9 – Command send path.** Add `/app/chat.delete` permitted for `ROLE_MODERATOR` without opening `/app/**` to all authenticated users. Test that unfamiliar MESSAGEs are denied.

**Exercise 10 – E2E.** Create two authenticated STOMP connections, one MEMBER and one ADMIN, testing SUBSCRIBE and SEND through a real broker with valid origin/CSRF. Compare received events against policy unit tests.

**Exercise 11 – Null destination.** Create CONNECT/DISCONNECT and a MESSAGE without a destination. Explain why `nullDestMatcher` differs from `simpTypeMatchers`, and why malformed SENDs must be rejected by the protocol layer or a custom guard.

**Exercise 12 – Different broker.** Replace the simple broker with a broker relay; verify clients cannot bypass Spring inbound authorization by connecting directly to the broker from an untrusted network. Evaluate ACLs on the external broker.

**Completion criteria:** accurately explain the three APIs `simpDestMatchers`, `simpSubscribeDestMatchers`, and `simpTypeMatchers`; distinguish MESSAGE/SUBSCRIBE/CONNECT; order first-match rules properly; prevent SEND to broker prefixes and restrict SUBSCRIBE by principal/tenant/room; test the policy with the real manager using Simp headers, then test full STOMP origin/CSRF end-to-end.

## 16. Official References

- Spring Security 6.5 – **WebSocket Security** (message authorization, first-match rules, CSRF CONNECT, inbound/outbound, user destinations): https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/websocket.html
- Spring Security 6.5 – **MessageMatcherDelegatingAuthorizationManager.Builder API**, `simpDestMatchers`, `simpMessageDestMatchers`, `simpSubscribeDestMatchers`, `simpTypeMatchers`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.html
- Spring Security 6.5 – **AuthorizationManager API**, `authorize` and `AuthorizationResult`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html
- Spring Framework – **STOMP Overview**, frame commands, broker/app prefixes: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/overview.html
- Spring Framework – **STOMP Message Flow**: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html
- Spring Framework – **User Destinations**: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html
- Spring Framework – **Enable STOMP**, simple broker and endpoint setup: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html
- Spring Framework – **WebSocket Allowed Origins**: https://docs.spring.io/spring-framework/reference/web/websocket/server.html
