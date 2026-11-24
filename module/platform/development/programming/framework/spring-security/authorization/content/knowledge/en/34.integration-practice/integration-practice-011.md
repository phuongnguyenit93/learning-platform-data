# Securing Sending and Receiving Messages on Personal STOMP Channels in Spring Security

Messaging apps, per-account notifications, and task boards often use **WebSocket + STOMP** to push real-time data. A “send only to user X” flow is only safe when the system controls **who creates the message, who may send to the recipient, who may subscribe to receive, and which sessions actually receive the data**. Renaming a destination to `/user/queue/inbox` does not automatically replace authentication, authorization, or business-level permission checks.

This practice uses **Spring Boot 3.5.x, Java 17+, Spring Security 6.x, Spring Messaging, and Servlet WebSocket/STOMP**. Configurations, Java source, and JUnit tests follow a Maven project layout; JavaScript client snippets clearly note when the `@stomp/stompjs` library is required. The security principles also remain useful when upgrading to Spring Security 7, though exact APIs for the target version must be verified.

## 1. Security Objectives and Threat Model

Suppose Alice and Bob are allowed to chat with each other. Carol is a user with an account who **does not belong to the conversation**. The system must ensure:

1. Alice sends a message to Bob using a STOMP `SEND` command to a server-handled application destination.
2. The server reads the sender from the **authenticated `Principal`**, verifies chat permissions and input data, and forwards the message to **Bob's user destination**.
3. Bob subscribes via `SUBSCRIBE /user/queue/inbox`; Alice cannot read Bob's inbox by altering the destination string.
4. Carol cannot send messages to Bob merely by editing `to` in the JSON, even though Carol is logged in.
5. Clients cannot publish messages “on behalf of the server” into `/queue/**` or `/topic/**`, or subscribe directly to a physical broker queue that might contain another user's data.
6. Origin, CSRF on STOMP `CONNECT`, HTTP handshake, logout, and session lifecycle are checked per the actual mechanism used.

Both **outbound-from-client (send)** and **inbound-to-client (receive)** directions must be controlled separately:

| Direction | STOMP Frame | Example Destination | Required Decision |
| --- | --- | --- | --- |
| Client → app | `SEND` | `/app/chat/send` | Authenticated, has functional permission, permitted to send to recipient |
| Client → broker | `SUBSCRIBE` | `/user/queue/inbox` | Authenticated; only user-relative subscriptions allowed |
| Client → broker directly | `SEND` | `/queue/inbox`, `/topic/system` | Denied to prevent server impersonation |
| Client → physical queue | `SUBSCRIBE` | `/queue/inbox-userXYZ` | Denied to prevent reading another user's queue/session |
| Server → Bob | Internal message | `convertAndSendToUser("bob", "/queue/inbox", ...)` | Server picks recipient after business policy check |
| Server → Bob's socket | Outbound `MESSAGE` | Per-session destination managed by Spring | Data reaches only mapped and properly subscribed sessions |

**Important point:** Spring Security primarily protects **`clientInboundChannel`** (frames arriving from clients). It does not automatically re-run authorization for each outbound message on `clientOutboundChannel`. Therefore, **checking inbound SUBSCRIBE**, guarding server-side message emission, and configuring the broker properly are decisive.

## 2. Understanding the Three Destination Types and Usernames

Use three separate namespaces:

- `/app/**`: **application destinations**; clients send `SEND` here, and Spring routes to `@MessageMapping` controllers.
- `/user/**`: **user destination prefix**; clients use `/user/queue/inbox` to SUBSCRIBE; Spring maps it to a session-bound destination. This is not a place for clients to choose another user via the path.
- `/queue/**` or `/topic/**`: **broker destinations**; the broker handles subscriptions/notifications already mapped by the server or intentionally public. Never grant direct SEND/SUBSCRIBE to all clients by default.

With configuration:

~~~java
registry.enableSimpleBroker("/queue");
registry.setApplicationDestinationPrefixes("/app");
registry.setUserDestinationPrefix("/user");
~~~

the proper flow is:

~~~text
Logged-in Alice:
  SEND /app/chat/send
  {"to":"bob","body":"Hello Bob"}

Spring @MessageMapping("/chat/send"):
  Principal.getName() == "alice"
  ChatPolicy.canSend("alice", "bob") == true
  convertAndSendToUser("bob", "/queue/inbox", event)

Logged-in Bob:
  SUBSCRIBE /user/queue/inbox
  Spring maps to Bob's session-bound queue
  → Bob receives MESSAGE with from="alice"
~~~

`UserDestinationMessageHandler` translates `/user/queue/inbox` into a **session-specific** destination (the concrete physical name is framework-generated, not an API for clients to guess). Calling `convertAndSendToUser("bob", "/queue/inbox", ...)` on the server normally delivers to **Bob's connected sessions** subscribed to that destination. To reply solely to the session that sent a command, use `@SendToUser(value="/queue/receipts", broadcast=false)` on the appropriate handler.

Never treat the `bob` segment in a client-sent `/user/bob/queue/inbox` string as proof the client is Bob. In this example, clients **may SUBSCRIBE only to the exact path `/user/queue/inbox`**. Longer patterns or physical broker destinations are denied. The server passes the recipient name to `convertAndSendToUser` using a verified Principal/user key.

**Principal identity:** `Principal#getName()` is the connection's identity, taken by Spring from HTTP handshake authentication in standard session setups. In multi-tenant systems, ensure Principal names are **system-wide unique** (e.g., mapped from an immutable user ID with tenant namespace); if two tenants both have a username `bob` and both call `convertAndSendToUser("bob", ...)`, relying on bare username can deliver messages to the wrong person. That is an identity design responsibility, not an automatic guarantee of the `/user` prefix.

## 3. Three Protection Layers Must Work Together

### 3.1. Authentication at the HTTP Handshake

Before STOMP runs, the browser opens a WebSocket via an HTTP Upgrade request. With form login/sessions, Spring Security authenticates the HTTP request and carries the `Principal` into the WebSocket session. Same-origin browsers typically include the session cookie in the handshake per browser cookie rules. If the handshake is unauthenticated yet the configuration lets the socket open, STOMP may have no valid Principal.

**Do not trust `login`, `passcode`, or `sender` headers self-declared by a STOMP client to establish identity.** Spring WebSocket by default does not turn those STOMP headers into HTTP-session authentication. If building a stateless JWT API, implement proper token validation at the handshake or in a `CONNECT` interceptor, calling AuthenticationManager/JwtDecoder and binding Authentication to the session; never read a header and treat a raw username string as the real user.

### 3.2. Authorization for Every Inbound STOMP Frame

After the handshake, a client can repeatedly send `SEND` and `SUBSCRIBE` frames over the same connection. You cannot assume “passed handshake” means permitted to do everything.

With `@EnableWebSocketSecurity` and an `AuthorizationManager<Message<?>>` bean, configure **minimal allowed destinations** and deny by default:

- `SEND /app/chat/send`: user with the required role.
- `SUBSCRIBE /user/queue/inbox`: user with the required role.
- `SEND /queue/**` and `SEND /topic/**`: deny.
- Direct `SUBSCRIBE /queue/**` and `SUBSCRIBE /user/{other}/...`: deny.
- Any other destination: deny until explicitly reviewed.

`simpMessageDestMatchers` matches only messages with `SimpMessageType.MESSAGE` (typically corresponding to client STOMP `SEND`). `simpSubscribeDestMatchers` matches only `SUBSCRIBE`. By contrast, `simpDestMatchers` does not distinguish message types and can easily over-expose routes if misused. Spring applies the **first matching matcher**, so specific rules must precede `simpTypeMatchers(...).denyAll()` and `anyMessage().denyAll()`.

### 3.3. Business Authorization Before Dispatching

Even a user permitted to `SEND /app/chat/send` **is not necessarily permitted to send to every recipient**. `to`, `conversationId`, `owner`, or `from` in the payload are all client-controlled.

In a real service, the policy should check:

- Sender is a member or holds a valid grant in the conversation.
- Recipient is a valid member in the same tenant and is not blocked under product policy.
- Target object is not deleted/revoked, and the action executes within the real tenant scope.
- If sending persists to a database, check permissions and write data with appropriate consistency/transaction guarantees.

**Never read `from` from JSON.** The server fills `from` from `Principal`; for auditing, record the server-side identifier. Never push full internal entities containing sensitive fields into outbound payloads; build a DTO holding only fields the recipient is allowed to view.

## 4. Maven Project Integrating Personal STOMP Configuration

Project structure:

~~~text
secure-stomp-inbox/
├── pom.xml
└── src/
    ├── main/java/com/example/stomp/
    │   ├── StompApplication.java
    │   ├── HttpSecurityConfig.java
    │   ├── WebSocketConfig.java
    │   ├── InboundSecurityConfig.java
    │   ├── ChatPolicy.java
    │   ├── ChatController.java
    │   └── CsrfController.java
    └── test/java/com/example/stomp/
        └── InboundSecurityTest.java
~~~

The example uses three demo users `alice`, `bob`, and `carol`. In `ChatPolicy`, only the pair Alice ↔ Bob may message each other; Carol is authenticated yet cannot send to Bob. This is a learning fixture, not a production friend/group management system.

### 4.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>secure-stomp-inbox</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-websocket</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-messaging</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

The Spring Boot parent manages compatible versions of WebSocket, Spring Messaging, and Spring Security. In this project, no explicit version is needed on each `spring-security-*` artifact. Boot 3/Spring Framework 6 requires JDK 17+.

### 4.2. `StompApplication.java`

~~~java
package com.example.stomp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StompApplication {
    public static void main(String[] args) {
        SpringApplication.run(StompApplication.class, args);
    }
}
~~~

Placing classes in `com.example.stomp` lets `@SpringBootApplication` automatically scan configs, controllers, and services.

### 4.3. `HttpSecurityConfig.java` — Login Before Handshake

~~~java
package com.example.stomp;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class HttpSecurityConfig {

    @Bean
    SecurityFilterChain httpChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login", "/error").permitAll()
                    .requestMatchers("/ws", "/csrf").authenticated()
                    .anyRequest().authenticated()
                )
                .formLogin(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice123"))
                .roles("USER").build();
        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("bob123"))
                .roles("USER").build();
        UserDetails carol = User.withUsername("carol")
                .password(encoder.encode("carol123"))
                .roles("USER").build();
        return new InMemoryUserDetailsManager(alice, bob, carol);
    }
}
~~~

The sample uses **form login + HTTP session** so browsers carry the login session cookie into the WebSocket handshake. These are local demo accounts; never hardcode credentials in production. The HTTP chain requires authentication for `/ws` and `/csrf`. Use HTTPS/WSS in real deployments.

The code does not disable CSRF application-wide. Logged-in users fetch a token from `GET /csrf` and place it into **STOMP CONNECT headers** as shown in section 5. HTTP CSRF and STOMP CSRF are checked at different times.

### 4.4. `WebSocketConfig.java` — Separating Broker/App/User Prefixes

~~~java
package com.example.stomp;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration(proxyBeanMethods = false)
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry endpoints) {
        // By default allow only appropriate origins; do not use allowedOriginPatterns("*").
        endpoints.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/queue");
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
    }
}
~~~

`enableSimpleBroker("/queue")` creates an in-memory broker suitable for single-instance demos, **not a durable queue or multi-node system**. Never add `/app` as a broker prefix, because client `SEND /app/...` must be handled by a server controller. Never open origins with wildcards when using cookies/sessions; if the frontend runs on another origin, configure an explicit origin allowlist and evaluate cookies/CORS/CSRF for your real architecture.

### 4.5. `InboundSecurityConfig.java` — SEND and SUBSCRIBE Policies

~~~java
package com.example.stomp;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration(proxyBeanMethods = false)
@EnableWebSocketSecurity
public class InboundSecurityConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            // CONNECT/DISCONNECT/UNSUBSCRIBE have no destination.
            .nullDestMatcher().authenticated()
            // Allow SEND only to approved application endpoints.
            .simpMessageDestMatchers("/app/chat/send").hasRole("USER")
            // Allow subscribing only to the session's own user-relative inbox.
            .simpSubscribeDestMatchers("/user/queue/inbox").hasRole("USER")
            // All other SEND/SUBSCRIBE frames are blocked, including /queue/**.
            .simpTypeMatchers(
                    SimpMessageType.MESSAGE, SimpMessageType.SUBSCRIBE)
                .denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
~~~

**Meaning:** a `SUBSCRIBE /user/queue/inbox` frame is valid only when authentication has `ROLE_USER`. Frames `SUBSCRIBE /queue/inbox`, `SUBSCRIBE /user/bob/queue/inbox`, `SEND /queue/inbox`, `SEND /user/queue/inbox`, or `SEND /topic/system` fail to match the two allow rules and hit `denyAll`. Blocking `MESSAGE` (SEND) outside application destinations prevents clients from impersonating the server to push into the broker.

`nullDestMatcher().authenticated()` covers messages without a destination, such as `CONNECT` and `DISCONNECT`; with `@EnableWebSocketSecurity`, Spring Security also checks CSRF on `CONNECT`. These are two **separate** checks: valid authentication does not make the CSRF token optional under this protection.

Note that `simpMessageDestMatchers` and `simpSubscribeDestMatchers` do not replace business policies. Any `ROLE_USER` account can **invoke the handler** and **subscribe to its own inbox**; permission to send to a specific recipient is checked in the controller/service afterward.

### 4.6. `ChatPolicy.java` — Permission to Send to the Right Recipient

~~~java
package com.example.stomp;

import org.springframework.stereotype.Service;

@Service
public class ChatPolicy {

    public boolean canSend(String sender, String recipient) {
        // Learning fixture: only Alice and Bob may message each other.
        // Production: query membership/tenant/block/ACL from a trusted source.
        return ("alice".equals(sender) && "bob".equals(recipient))
                || ("bob".equals(sender) && "alice".equals(recipient));
    }
}
~~~

In a real application, policies must rely on conversation relationships and tenants in the database, checking ownership, lock/block status, and up-to-date permissions. Never use a hardcoded allowlist in production; this fixture aims to prove that **Carol with ROLE_USER still cannot send messages to Bob** merely by editing JSON.

### 4.7. `ChatController.java` — Obtaining Sender from Principal

~~~java
package com.example.stomp;

import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    public record SendRequest(String to, String body) {}
    public record InboxMessage(String from, String body) {}

    private final ChatPolicy policy;
    private final SimpMessagingTemplate template;

    public ChatController(ChatPolicy policy, SimpMessagingTemplate template) {
        this.policy = policy;
        this.template = template;
    }

    @MessageMapping("/chat/send")
    public void send(SendRequest command, Principal principal) {
        if (principal == null) {
            throw new AccessDeniedException("Authentication required");
        }
        if (command == null || command.to() == null
                || command.body() == null
                || command.body().isBlank()
                || command.body().length() > 500) {
            throw new IllegalArgumentException("Invalid chat request");
        }

        String sender = principal.getName();
        if (!policy.canSend(sender, command.to())) {
            throw new AccessDeniedException("Recipient not allowed");
        }

        // Server determines from and destination /user/{recipient}/...
        template.convertAndSendToUser(
                command.to(), "/queue/inbox",
                new InboxMessage(sender, command.body()));
    }
}
~~~

When a client sends `SEND /app/chat/send`, the `/app` prefix is stripped before Spring matches `@MessageMapping("/chat/send")`. When Bob subscribes to `/user/queue/inbox`, Spring routes messages to the destination bound to Bob's session. Senders **cannot** declare a trusted `from`: `InboxMessage.from` comes from `Principal`.

Checking `body.isBlank()` and length is only basic validation. In production, also enforce frame size limits, rate limits, anti-spam, safe rendering when displaying HTML, auditing, and offline storage/notifications. Never pass user-supplied bodies directly to `innerHTML` on the frontend; render as text or through a vetted sanitizer.

When messaging a **multi-member conversation**, the server should resolve members from `conversationId` and deliver to the authorized user set rather than letting clients name arbitrary usernames. For database writes, re-verify permissions inside an appropriate transaction if memberships can change between check and write.

### 4.8. `CsrfController.java` — Providing a CSRF Token for STOMP CONNECT

~~~java
package com.example.stomp;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfController {

    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken csrfToken) {
        // Accessible only to logged-in users because the HTTP chain protects /csrf.
        return csrfToken;
    }
}
~~~

In a same-origin session/cookie setup, the client calls `GET /csrf` after login. The endpoint returns a token only for authenticated sessions; never log the token. If the session/cookie changes, the frontend must fetch the token for the new session. Never expose a public CSRF endpoint alongside unsafe cookie/origin configs.

## 5. JavaScript Client: SUBSCRIBE Inbox and SEND to App

This is a **frontend fragment** using `@stomp/stompjs` (installed via a package manager and bundled into a page running at the **same origin** as the app). Before running, open the Spring login page, log in with a demo account, and then run the bundled frontend code. When using HTTPS, the browser uses WSS.

~~~javascript
import { Client } from "@stomp/stompjs";

async function openPersonalInbox() {
    const response = await fetch("/csrf", {
        credentials: "same-origin"
    });
    if (!response.ok) {
        throw new Error("Login before connecting STOMP");
    }
    const csrf = await response.json();

    const secure = window.location.protocol === "https:";
    const scheme = secure ? "wss://" : "ws://";

    const client = new Client({
        brokerURL: scheme + window.location.host + "/ws",
        connectHeaders: {
            [csrf.headerName]: csrf.token
        },
        reconnectDelay: 5000,
        onConnect: () => {
            // Every user subscribes to the SAME user-relative path.
            client.subscribe("/user/queue/inbox", frame => {
                const event = JSON.parse(frame.body);
                // Render event.from and event.body as text, avoiding innerHTML.
                console.log("From", event.from, ":", event.body);
            });
        },
        onStompError: frame => {
            console.error("STOMP broker error:", frame.headers["message"]);
        }
    });

    client.activate();
    return client;
}

function sendToBob(client) {
    // Call after connection is CONNECTED; server verifies recipient.
    client.publish({
        destination: "/app/chat/send",
        body: JSON.stringify({
            to: "bob",
            body: "Hello Bob"
        })
    });
}
~~~

Bob's account must open a **separate logged-in session** and subscribe to the same `/user/queue/inbox` to receive messages. Alice calls `sendToBob(client)` after the `onConnect` event. In real apps, avoid publishing while `client.connected` is false, add send acknowledgments, handle reconnects, and retry safely without duplicate messages.

**Never send spoofed STOMP `user` or `login` headers expecting the server to “trust” the sender.** Policy uses Principal from HTTP/session. For OAuth2/JWT over WebSocket, implement and test a dedicated authentication mechanism; `connectHeaders.Authorization` is not automatically validated by Spring Security without an appropriate interceptor/token processor.

### Visualizing the STOMP Frames

~~~text
# Authenticated user connects, sending a valid CSRF header.
CONNECT
accept-version:1.2
host:localhost
X-CSRF-TOKEN:<session-token>

# Bob or Alice subscribes to THEIR OWN inbox.
SUBSCRIBE
id:inbox-1
destination:/user/queue/inbox

# Alice sends a request, not directly to a broker queue.
SEND
destination:/app/chat/send
content-type:application/json

{"to":"bob","body":"Hello Bob"}
~~~

These lines illustrate **frame structure** only; they omit the STOMP frame terminator byte (`NUL`) and do not replace a client library. Take the CSRF header name from the `/csrf` response rather than hardcoding `X-CSRF-TOKEN` across all configurations.

## 6. Testing Inbound Policy with JUnit 5

The unit/integration context test below directly checks the `AuthorizationManager<Message<?>>` from the configuration above without opening a real socket. It proves **frame type + destination + role** are accepted or denied properly. To prove actual delivery over WebSocket, add a two-session test/harness as in section 7.

Create `src/test/java/com/example/stomp/InboundSecurityTest.java`:

~~~java
package com.example.stomp;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class InboundSecurityTest {

    @Autowired AuthorizationManager<Message<?>> manager;
    @Autowired ChatPolicy policy;

    private Authentication user(String name) {
        return new TestingAuthenticationToken(
                name, "unused", "ROLE_USER");
    }

    private Authentication anonymous() {
        return new AnonymousAuthenticationToken(
                "demo-key", "anonymousUser",
                List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS")));
    }

    private boolean granted(SimpMessageType type,
                            String destination,
                            Authentication authentication) {
        SimpMessageHeaderAccessor accessor =
                SimpMessageHeaderAccessor.create(type);
        if (destination != null) {
            accessor.setDestination(destination);
        }
        Message<byte[]> message = MessageBuilder.createMessage(
                new byte[0], accessor.getMessageHeaders());
        AuthorizationDecision decision =
                manager.check(() -> authentication, message);
        return decision != null && decision.isGranted();
    }

    @Test
    void authenticatedUserCanSendToApplicationHandler() {
        assertTrue(granted(SimpMessageType.MESSAGE,
                "/app/chat/send", user("alice")));
    }

    @Test
    void clientCannotSendDirectlyToBrokerQueue() {
        assertFalse(granted(SimpMessageType.MESSAGE,
                "/queue/inbox", user("alice")));
    }

    @Test
    void clientCannotSendToFakeSystemTopic() {
        assertFalse(granted(SimpMessageType.MESSAGE,
                "/topic/system", user("alice")));
    }

    @Test
    void userCanSubscribeToOwnRelativeInbox() {
        assertTrue(granted(SimpMessageType.SUBSCRIBE,
                "/user/queue/inbox", user("bob")));
    }

    @Test
    void userCannotSubscribeDirectlyToBrokerQueue() {
        assertFalse(granted(SimpMessageType.SUBSCRIBE,
                "/queue/inbox", user("alice")));
    }

    @Test
    void userCannotPutOtherUsernameInSubscribeDestination() {
        assertFalse(granted(SimpMessageType.SUBSCRIBE,
                "/user/bob/queue/inbox", user("alice")));
    }

    @Test
    void otherSubscriptionsAreDeniedByDefault() {
        assertFalse(granted(SimpMessageType.SUBSCRIBE,
                "/topic/private", user("bob")));
    }

    @Test
    void anonymousCannotSubscribeToPrivateInbox() {
        assertFalse(granted(SimpMessageType.SUBSCRIBE,
                "/user/queue/inbox", anonymous()));
    }

    @Test
    void anonymousCannotSendToApplicationHandler() {
        assertFalse(granted(SimpMessageType.MESSAGE,
                "/app/chat/send", anonymous()));
    }

    @Test
    void connectRequiresAuthenticationInMessagePolicy() {
        assertTrue(granted(SimpMessageType.CONNECT,
                null, user("alice")));
        assertFalse(granted(SimpMessageType.CONNECT,
                null, anonymous()));
    }

    @Test
    void aliceAndBobCanChatButCarolIsDeniedByBusinessPolicy() {
        assertTrue(policy.canSend("alice", "bob"));
        assertTrue(policy.canSend("bob", "alice"));
        assertFalse(policy.canSend("carol", "bob"));
        assertFalse(policy.canSend("alice", "carol"));
    }
}
~~~

Run the project from the directory containing `pom.xml`:

~~~bash
mvn test
~~~

**Expected result:** 11 JUnit 5 tests pass when dependencies and runtime match. Specifically, the tests verify decisions of `AuthorizationManager` and the `ChatPolicy` bean; they do **not** verify HTTP login, STOMP `CONNECT` CSRF tokens, handshake, broker delivery, disconnect states, or multi-instance distribution.

The tests target Spring Security 6.x, calling `AuthorizationManager.check(...)`, which returns `AuthorizationDecision`. When upgrading to another API, review deprecations without dropping test coverage. `TestingAuthenticationToken` is a fixture for policy tests; it is **not proof** Spring successfully authenticated a real user's WebSocket handshake.

### One Important Test Frequently Missing

If you assert only that `SUBSCRIBE /user/queue/inbox` is permitted, you have proven only that the **user-relative subscription request** is allowed. You have not proven Bob actually receives messages while Alice/Carol do not receive messages meant for Bob. Write a test with two authenticated sessions both subscribed to `/user/queue/inbox`, have the server send a message, and inspect **which session receives it**. That is where wrong Principal names, broker prefixes, or user-destination configs are caught early.

## 7. Two-Account Integration Test Scenario

Start the application:

~~~bash
mvn spring-boot:run
~~~

Open two browser sessions with separate cookies/sessions (e.g., normal window + private browsing or two profiles):

1. **Bob** logs in at `http://localhost:8080/login` using demo credentials `bob / bob123`. Same-origin page fetches `GET /csrf`, opens `ws://localhost:8080/ws`, sends STOMP `CONNECT` with the token, and then `SUBSCRIBE /user/queue/inbox`.
2. **Alice** logs in on the other session with `alice / alice123`, connects STOMP similarly, subscribes to her personal inbox, and sends `SEND /app/chat/send` with body `{"to":"bob","body":"hello"}`.
3. Observe Bob receiving `{"from":"alice","body":"hello"}`. Alice does **not receive** that message herself unless server logic sends a sender copy; this example does not.
4. Try having Alice `SUBSCRIBE /queue/inbox` or `/user/bob/queue/inbox`. Expect the subscription to be blocked. The app may emit `ERROR` and/or close the socket depending on exception handling; **do not** assert a specific HTTP 403 because traffic is already on STOMP.
5. **Carol** logs in with `carol / carol123` and tries `SEND /app/chat/send` to Bob. The destination is allowed for `ROLE_USER`, yet `ChatPolicy` must deny delivery. Bob **must not** receive any message from Carol.
6. Try `SEND /topic/system` or `SEND /queue/inbox` from Alice; the frame must be rejected before reaching the broker.
7. Open a second session for Bob and subscribe; by default, `convertAndSendToUser("bob",...)` can deliver to **Bob's subscribed sessions**. Verify both receive it; when Bob logs out or the session expires, check disconnection policy and remaining permissions.
8. Send STOMP `CONNECT` with missing or invalid CSRF token; the connection must be rejected per `@EnableWebSocketSecurity`, even if the HTTP session is logged in.
9. Attempt a handshake from an origin not in the allowlist; verify it is blocked per origin configuration. This test requires a real environment because section 6's unit tests do not simulate browser/WebSocket networking.

To prove **no message leaks**, do not just verify Bob receives it: verify Alice and Carol do not receive events with `from="alice"` sent to Bob over other subscriptions. If there is a durable inbox/database, also verify Carol cannot read Alice/Bob's conversation history via REST APIs or replay features.

### Expected Matrix

| Actor | Action | Expectation |
| --- | --- | --- |
| Logged-in Alice | `SEND /app/chat/send` to Bob | Allowed at channel; allowed by business policy |
| Logged-in Bob | `SUBSCRIBE /user/queue/inbox` | Allowed; receives message in right session |
| Logged-in Carol | `SUBSCRIBE /user/queue/inbox` | Allowed **Carol's inbox**, not Bob's |
| Logged-in Alice | `SUBSCRIBE /user/bob/queue/inbox` | Denied |
| Logged-in Alice | `SUBSCRIBE /queue/inbox` | Denied |
| Logged-in Alice | `SEND /queue/inbox` | Denied |
| Logged-in Alice | `SEND /topic/system` | Denied |
| Logged-in Carol | `SEND /app/chat/send` to Bob | Allowed at channel; denied by business policy |
| Anonymous | `SEND /app/chat/send` | Denied |
| Anonymous | `SUBSCRIBE /user/queue/inbox` | Denied |
| Alice with session but bad CSRF | STOMP `CONNECT` | Denied |
| Bob with two sessions | Server sends to user Bob | Bob's subscribed sessions receive per default config |

If a test checks only the HTTP status of the handshake, you have not proven `SEND`/`SUBSCRIBE` permissions on individual STOMP frames. Both layers serve distinct purposes and should be tested separately.

## 8. Why Are `@SendToUser` and `convertAndSendToUser` Insufficient When Misconfigured?

### `@SendToUser`: Replying to the User Attached to the Inbound Message

A controller can return a result to the sender:

~~~java
// Fragment: place inside a @Controller with appropriate @MessageMapping.
@MessageMapping("/profile/ping")
@SendToUser(value = "/queue/replies", broadcast = false)
public Reply ping(Principal principal) {
    return new Reply(principal.getName(), "pong");
}
~~~

This fragment requires declaring `Reply`, imports, and allowing `SEND /app/profile/ping` and `SUBSCRIBE /user/queue/replies` in the policy. `broadcast=false` targets **the calling session** rather than all sessions of the same user. It suits private receipts/errors, yet does not replace payload validation and execution checks in the handler.

### `convertAndSendToUser`: Proactively Sending to a Designated User

~~~java
// Fragment inside a Spring service with SimpMessagingTemplate.
template.convertAndSendToUser(
        verifiedRecipientId,
        "/queue/inbox",
        new InboxMessage(authenticatedSenderId, sanitizedText));
~~~

Ensure `verifiedRecipientId` matches how Spring sets `Principal#getName()` on connected sessions, and that the recipient is truly allowed to receive the message. Taking `verifiedRecipientId` directly from a client body **without policy checks** simply moves the authorization bug to the server side.

**Private delivery does not mean absolute secrecy:** User destinations prevent other users from subscribing by mistake only in a properly configured Spring setup. If you allow `SUBSCRIBE /queue/**`, expose a broker relay to the Internet without ACLs, or publish the same secret payload onto `/topic/**`, user destinations cannot rescue improperly broadcast data.

## 9. CSRF, Origin, Sessions, and JWT

### 9.1. Why Do Handshake and STOMP CONNECT Differ?

Browsers do not enforce same-origin policy on WebSockets the same way as fetch/XHR, so applications must restrict allowed origins and protect against cross-site WebSocket hijacking when using cookies. `@EnableWebSocketSecurity` in the Servlet model requires a **CSRF token on STOMP `CONNECT` frames** by default.

Remember the two checkpoints:

- HTTP GET/Upgrade to `/ws`: HTTP filter chain handles authentication and handshake policies.
- STOMP `CONNECT` after socket opens: Spring Security Messaging checks authentication and CSRF token on STOMP headers before allowing communication.

A GET succeeding with 101 Switching Protocols **does not prove** STOMP CONNECT was accepted. If clients use SockJS fallbacks with POST/iframe, configure HTTP CSRF exceptions **narrowly for the appropriate SockJS endpoints** while keeping CSRF on STOMP CONNECT; never disable CSRF app-wide just to fix fallback errors. This sample uses raw WebSockets without SockJS and needs no HTTP CSRF exemptions for endpoints.

### 9.2. Session/Logout and Open Connections

HTTP session authentication is captured at the handshake. When a user is locked or has permissions revoked, **do not assume** an open WebSocket will automatically close or every `AuthorizationManager` will automatically reload authorities from the database. Define explicit policies: close affected WebSocket sessions, refresh Authentication/check permissions dynamically in handlers, and check revocation in every sensitive operation.

With stateful sessions, a “log out all devices” flow may require invalidating HTTP sessions **and** disconnecting active WebSocket sessions across multiple nodes; test sockets connected prior to revocation.

### 9.3. JWT/OAuth2 Resource Server

If the frontend uses access tokens instead of cookies/sessions, clearly define the **token validation point** at socket open or STOMP CONNECT. With tokens in STOMP headers, a custom `ChannelInterceptor` can decode, verify issuer/audience/expiry, and set the authenticated user in headers using the proper Spring Messaging API. Register the interceptor **in the right order** before the authorization interceptor, handle invalid tokens, ensure untrusted `login`/`user` headers are ignored, and handle re-authentication/revocation when tokens expire.

Spring Security does not automatically apply JWT bearer authentication merely because a client sends `Authorization` in STOMP `CONNECT` headers. Never mock tokens by parsing usernames without signature verification. Standalone bearer tokens have a different threat model for CSRF/cross-origin and credential transport; never copy session config into a stateless API without testing.

## 10. Broker Relays, Multiple Instances, and Privacy

Section 4's sample uses an in-memory simple broker. Running multiple application instances behind a load balancer introduces new issues:

- Bob has a socket on instance B, while Alice sends to instance A. A's local simple broker **may not know** Bob's session on B, so the message never arrives.
- When using a **STOMP broker relay** (RabbitMQ/ActiveMQ), protect credentials/ACLs between apps and the broker; never let external clients log directly into the broker and subscribe to arbitrary queues.
- Spring provides `userDestinationBroadcast` to broadcast unresolved user destinations to locate sessions on other nodes depending on setup. Also evaluate `userRegistryBroadcast`/multi-node registries when needed.
- Per-user/session physical queues need proper lifecycle/cleanup; different brokers have different auto-delete behaviors.
- Disconnects/reconnects can create new sessions or lose undelivered notifications. User destinations do not provide **offline storage, exactly-once delivery, or global ordering** by default.

For sensitive messages, persist authorized records in a database/durable queue per policy and use STOMP solely as a real-time signal; when users load history, **authorization must still verify** recipient/tenant/conversation. Never treat knowing a destination string as sufficient proof of access.

## 11. Common Mistakes and Detection Methods

**Mistake 1: Letting clients `SUBSCRIBE /queue/**`.** This can let users join broker destinations holding others' data. Allow only user-relative `/user/queue/inbox` or reviewed topics, denying direct subscriptions to physical queues.

**Mistake 2: Letting clients `SEND /topic/**` or `SEND /queue/**`.** Users can spoof system announcements or push data into someone else's inbox. Allow `SEND` only to approved `/app/**` endpoints and use controllers/services to emit to the broker.

**Mistake 3: Matching overly broad `simpDestMatchers("/user/**").permitAll()`.** This can permit both MESSAGE and SUBSCRIBE frames across many paths. Use `simpSubscribeDestMatchers` and `simpMessageDestMatchers` to specify frame types explicitly.

**Mistake 4: Taking `from`/`owner` from JSON.** Clients can claim to be Bob. Use the authenticated `Principal`, and verify recipient/conversation membership from server-side sources.

**Mistake 5: Thinking WebSocket handshake authentication is enough.** A logged-in socket can still probe other destinations or alter recipients in payloads. Check every inbound message and business policy.

**Mistake 6: Confusing 101/HTTP 403 with STOMP results.** Handshake success does not mean CONNECT/SUBSCRIBE succeeded. Denying frames at the messaging layer does not necessarily yield HTTP 403, often producing STOMP ERROR/close instead. Test both layers separately.

**Mistake 7: Disabling CSRF globally because CONNECT fails.** With cookie sessions, cross-site socket hijacking is a real threat. Fetch the session's CSRF token for STOMP CONNECT; restrict allowed origins. If using SockJS, exempt only the required HTTP fallback paths per documentation.

**Mistake 8: Skipping real role and tenant checks for the recipient.** `hasRole("USER")` allows calling the handler, not messaging arbitrary people. Add conversation membership, blocklist, tenant, and resource checks.

**Mistake 9: Assuming user destinations deliver to only one tab.** By default a user can have multiple sessions, all receiving when subscribed. Use `@SendToUser(broadcast=false)` when targeting only the current session; design explicit multi-device rules for real systems.

**Mistake 10: Relying on a single instance/local broker.** When recipients connect to another node, messages can be lost. Test cross-node delivery, broker relays, user registries, and reconnect behavior.

**Mistake 11: Not cleaning up queues/sessions after logout.** Old sessions, stale subscriptions, and broker state can retain resources or messages. Set proper lifecycles and retention.

**Mistake 12: Leaking info via logs and payloads.** Never log CSRF tokens, raw JWTs, session IDs, or private payloads. Deny with informative yet non-leaking errors if recipient existence is sensitive.

## 12. Acceptance Checklist

- [ ] HTTP WebSocket handshake requires authentication; origin allowlist is set, HTTPS/WSS in production.
- [ ] STOMP CONNECT verifies CSRF tokens in session setups per `@EnableWebSocketSecurity`.
- [ ] Client SEND is allowed only to approved application destinations; direct broker sends are blocked.
- [ ] Client SUBSCRIBE is allowed only to personal user-relative destinations or authorized topics.
- [ ] `/user/queue/inbox` is mapped per session by Spring; clients cannot pick another user's username in the path.
- [ ] Sender comes from authenticated Principal, never from client-supplied headers/payloads.
- [ ] Recipient/tenant/conversation are checked by business policy before sending.
- [ ] No sensitive payloads are sent to public topics or client-subscribable physical queues.
- [ ] Tests cover anonymous users, authorized/unauthorized users, wrong frame types, lookalike destinations, and sender spoofing.
- [ ] Tests verify Alice → Bob succeeds; Carol → Bob is denied, Bob receives, and Alice/Carol do not receive by mistake.
- [ ] Tests cover valid/invalid CSRF on CONNECT, bad origins, expired sessions, and disconnect/reconnect.
- [ ] With multiple instances, test sender/recipient on different nodes, user destination resolution, and broker ACLs.
- [ ] A strategy exists for revoking permissions on live WebSockets, managing backlogs/offline delivery, and auditing.

## 13. Official Documentation

- Spring Security — WebSocket Security: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
- Spring Framework — STOMP User Destinations: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html
- Spring Framework — STOMP Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html
- Spring Framework — STOMP WebSocket Configuration: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html
- Spring Security — `MessageMatcherDelegatingAuthorizationManager.Builder` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.html
- Spring Security — WebSocket and SockJS CSRF: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html#websocket-same-origin

**Target outcome:** Alice can send a server-validated command to Bob; Bob subscribes to his own user-relative inbox and receives the exact message. Sender spoofing, physical queue subscriptions, direct broker SENDs, sending to unauthorized recipients, unauthenticated connections, and missing CSRF are all rejected by their respective protection layers. Never declare success merely because a WebSocket opened or a single message arrived.
