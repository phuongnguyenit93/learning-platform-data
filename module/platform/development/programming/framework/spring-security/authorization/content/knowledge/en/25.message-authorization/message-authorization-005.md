# Distinguishing Permission to Send MESSAGE from Permission to SUBSCRIBE in Spring Security

## 1. Scenario: Reading Announcements Does Not Mean Broadcasting Announcements

A Spring WebSocket/STOMP application lets users follow system announcements on `/topic/system/announcements`. Users are **allowed to receive** announcements from the server, yet must not **impersonate the server to broadcast** announcements to subscribers.

Two common STOMP operations from clients:

```text
SUBSCRIBE
id:sub-1
destination:/topic/system/announcements

^@
```

and:

```text
SEND
destination:/topic/system/announcements
content-type:text/plain

Forged announcement from client^@
```

`^@` here merely denotes the position of a STOMP frame's null terminator; it is not an official escape sequence to put literally in requests. The key point is **the same destination, yet different operation types**. A policy checking only the destination, such as `"/topic/**".hasRole("USER")` without constraining message type, can accidentally let clients send directly to a topic meant only for server publishing.

**Rule:** permission to **send** (`STOMP SEND`, typically represented on Spring's inbound side as `SimpMessageType.MESSAGE`) and permission to **subscribe** (`STOMP SUBSCRIBE`, `SimpMessageType.SUBSCRIBE`) are **two separate decisions**. Do not infer that anyone allowed to read a topic may send to it, or that anyone allowed to send to a business endpoint may subscribe to every output channel.

This lesson focuses on **message authorization** in Spring Security, Spring Messaging, and WebSocket/STOMP. Examples target the Spring Boot 3.5.x / Spring Security 6.5 branch; when using 7.x, verify API changes and the corresponding migration guide.

## 2. Concept Map: SEND, MESSAGE, and SUBSCRIBE

| Term | Who Uses It? | Meaning |
| --- | --- | --- |
| STOMP `CONNECT` | Client → server | Opens the STOMP session after the HTTP/WebSocket handshake |
| STOMP `SEND` | Client → server | Sends content to a destination |
| Spring `SimpMessageType.MESSAGE` | On `clientInboundChannel` | Typically represents an inbound `SEND` command from a client |
| STOMP `SUBSCRIBE` | Client → server | Registers to receive messages at a destination |
| Spring `SimpMessageType.SUBSCRIBE` | On `clientInboundChannel` | Client subscription request |
| STOMP `MESSAGE` | Broker/server → client | Data frame pushed by the server/broker to subscribers |
| STOMP `UNSUBSCRIBE` | Client → server | Cancels a prior subscription |
| STOMP `DISCONNECT` | Client → server | Ends the session |
| `@MessageMapping` | Spring controller | Processes messages sent to an application destination |
| `SimpMessagingTemplate` | Server | Publishes to a broker destination or user destination |

The name **MESSAGE** is easily confused: STOMP has an outbound frame named `MESSAGE`, whereas Spring uses `SimpMessageType.MESSAGE` for an inbound application message corresponding to a client `SEND`. When authorizing with `MessageMatcherDelegatingAuthorizationManager`, we are checking **messages entering the server**, not every server-generated outbound STOMP MESSAGE.

### Chat Feature Example

```text
Alice, authority CHAT_SEND:
  SEND /app/chat.send
    -> @MessageMapping("/chat.send")
    -> service checks content/tenant/policy
    -> SimpMessagingTemplate.convertAndSend("/topic/chat.public", ...)
    -> broker delivers MESSAGE to validly subscribed clients

Bob, authority CHAT_READ:
  SUBSCRIBE /topic/chat.public
    -> broker registers subscription
    -> receives MESSAGEs sent by the server

Bob tries:
  SEND /topic/chat.public
    -> DENY, even though Bob has CHAT_READ
```

A user may hold both `CHAT_SEND` and `CHAT_READ`. Yet the server still needs to block direct sends to broker destinations unless it is a purpose-built publish endpoint with matching checks.

## 3. Three Destination Groups to Keep Distinct

In common Spring Framework configuration:

```java
registry.setApplicationDestinationPrefixes("/app");
registry.enableSimpleBroker("/topic", "/queue");
registry.setUserDestinationPrefix("/user");
```

The prefixes carry different meanings:

| Destination | Used For | Suggested Policy |
| --- | --- | --- |
| `/app/chat.send` | Client sends an action to a controller | Only `MESSAGE` if holding `CHAT_SEND` |
| `/app/documents.update` | Client requests a data update | `MESSAGE` + update authority and object policy |
| `/topic/chat.public` | Broker broadcasts public chat | Only `SUBSCRIBE` if holding `CHAT_READ` |
| `/topic/system/announcements` | Server broadcasts system notices | `SUBSCRIBE` per policy, no client SEND |
| `/topic/tenants/alpha/events` | Per-tenant broker topic | `SUBSCRIBE` must verify tenant membership |
| `/user/queue/messages` | Logical user destination | `SUBSCRIBE` for the right user/session |
| `/queue/**` | Physical broker destination | Deny direct client SUBSCRIBE unless intentionally exempted |
| No destination (CONNECT, DISCONNECT...) | Session control | Authentication/CSRF, separate protocol policy |

`setApplicationDestinationPrefixes("/app")` means a STOMP client sending `/app/chat.send` can be dispatched to `@MessageMapping("/chat.send")`, because Spring strips the `/app` prefix before the controller.

`enableSimpleBroker("/topic", "/queue")` means the broker handles those destinations. **Do not equate routing with authorization**: a broker prefix is not a security boundary. If you do not block clients from sending into the broker namespace, clients can bypass business validation inside `@MessageMapping`.

### When Is SUBSCRIBE Treated as "Read"?

A subscription allows the broker to **deliver future messages** at that destination to the client. This is not just a one-shot GET request: the connection can stay open for a long time and keep receiving events after permissions in the database change. Therefore, subscription authorization must account for **revocation, tenant isolation, and time-sensitive data**.

## 4. Authorization Must Evaluate Both Message Type and Destination

Suppose the policy is:

- Holders of `CHAT_SEND` may `SEND /app/chat.send`.
- Holders of `CHAT_READ` may `SUBSCRIBE /topic/chat.public`.
- Authenticated users may `SUBSCRIBE /user/queue/errors` to receive personal errors.
- Clients may not send `MESSAGE` to `/topic/**` or `/queue/**`.
- Clients may not `SUBSCRIBE` to `/app/**`.
- Remaining commands and destinations are denied except for listed control frames.

Truth table:

| Caller | STOMP frame | Destination | Expectation |
| --- | --- | --- | --- |
| CHAT_SEND | SEND | `/app/chat.send` | **PERMIT** |
| CHAT_SEND | SUBSCRIBE | `/topic/chat.public` | DENY without CHAT_READ |
| CHAT_READ | SUBSCRIBE | `/topic/chat.public` | **PERMIT** |
| CHAT_READ | SEND | `/topic/chat.public` | **DENY** |
| CHAT_READ | SEND | `/app/chat.send` | DENY |
| CHAT_SEND+CHAT_READ | SEND | `/app/chat.send` | **PERMIT** |
| CHAT_SEND+CHAT_READ | SUBSCRIBE | `/topic/chat.public` | **PERMIT** |
| CHAT_SEND+CHAT_READ | SEND | `/topic/chat.public` | **DENY** |
| Authenticated | SUBSCRIBE | `/user/queue/errors` | **PERMIT** |
| Authenticated | SUBSCRIBE | `/queue/private` | DENY |
| Authenticated | SUBSCRIBE | `/app/chat.send` | DENY |
| Anonymous | CONNECT | no destination | DENY (for a protected app) |
| Authenticated | CONNECT | no destination | Auth condition met; CSRF/STOMP security still applies |

A good matcher order is: **specific control frame types → permitted MESSAGE/SUBSCRIBE destinations → deny remaining MESSAGE/SUBSCRIBE types → deny everything else**.

## 5. Why Using Only simpDestMatchers Can Be Overly Broad

`MessageMatcherDelegatingAuthorizationManager.Builder` supports several matchers. Most importantly:

```java
// Evaluates destination only, without constraining SimpMessageType.
messages.simpDestMatchers("/topic/chat.public")
        .hasAuthority("CHAT_READ");

// Matches only SimpMessageType.MESSAGE + destination.
messages.simpMessageDestMatchers("/app/chat.send")
        .hasAuthority("CHAT_SEND");

// Matches only SimpMessageType.SUBSCRIBE + destination.
messages.simpSubscribeDestMatchers("/topic/chat.public")
        .hasAuthority("CHAT_READ");
```

These are **independent snippets illustrating API choices**; do not copy all three into one policy as shown above. The first matcher can match both client SEND/MESSAGE and SUBSCRIBE on the same topic, making it unsuitable when granting **read-only access**.

More accurate approach:

- `simpMessageDestMatchers` for designed application SEND routes.
- `simpSubscribeDestMatchers` for channels clients are permitted to follow.
- `simpTypeMatchers` for frame types like CONNECT/DISCONNECT or catch-all MESSAGE/SUBSCRIBE denial.
- `anyMessage().denyAll()` to reject messages not matched by earlier rules.

Spring Security 6.5 JavaDoc clearly distinguishes `simpMessageDestMatchers` from `simpSubscribeDestMatchers` by `SimpMessageType`. Matchers are evaluated in registration order; never place a broad `/topic/**` rule ahead of a detailed deny rule.

### Counterexample: Destination-Only Rule for Topics

```java
messages
    .simpDestMatchers("/topic/**").hasRole("USER")
    .anyMessage().denyAll();
```

If the application uses the same broker prefix for publish and subscribe, a `ROLE_USER` user can pass the guard for `MESSAGE` to the topic. **Do not use this configuration and claim "USER is read-only."**

### The Fix

```java
messages
    .simpSubscribeDestMatchers("/topic/chat.public")
        .hasAuthority("CHAT_READ")
    .simpMessageDestMatchers("/app/chat.send")
        .hasAuthority("CHAT_SEND")
    .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
    .anyMessage().denyAll();
```

The snippet above requires importing `SimpMessageType.MESSAGE` and `SimpMessageType.SUBSCRIBE`. Permitted control frames must be listed before the deny rules; the complete version is in Section 9.

## 6. Journey of a Message Through Spring's Channels

```text
CLIENT SEND /app/chat.send
    |
    v
WebSocket/STOMP transport
    |
    v
clientInboundChannel  <---- Spring Security authorization checks
    |
    v
SimpAnnotationMethodMessageHandler
    |
    v
@MessageMapping("/chat.send")
    |
    v
SimpMessagingTemplate -> brokerChannel
    |
    v
SimpleBroker or external broker relay
    |
    v
clientOutboundChannel
    |
    v
Accepted SUBSCRIBERS
```

For SUBSCRIBE:

```text
CLIENT SUBSCRIBE /topic/chat.public
    |
    v
clientInboundChannel  <---- SUBSCRIBE authorization
    |
    v
Broker registers the session's subscription
    |
    v
When the server publishes, broker delivers MESSAGE to session
```

Per Spring Security documentation, WebSocket authorization protects **`clientInboundChannel`**. It **does not automatically check every message on `clientOutboundChannel`**, primarily due to the cost when one message fans out to many subscribers. Consequently, **the subscription gate is critical**.

Do not assume a newly emitted server event passes through the same `simpSubscribeDestMatchers` manager again. If data sensitivity changes, control must happen at the publish source and subscription lifecycle.

### Simple Broker vs. External Broker Relay

Spring's simple broker is great for learning examples. If using RabbitMQ/ActiveMQ/STOMP relay, you still need to restrict **`clientInboundChannel`** and configure appropriate broker accounts/routing. An external broker does not make `/topic/**` safe if clients can publish or subscribe without authorization through another path.

## 7. Authentication: Being Connected Does Not Mean MESSAGE/SUBSCRIBE Is Allowed

A WebSocket session usually starts with an HTTP handshake. In a Servlet application, Spring can take the `Principal` from the Spring Security–authenticated HTTP request and attach that user to the session's STOMP messages.

```text
HTTP GET /ws (Upgrade: websocket)
  -> HTTP SecurityFilterChain authenticates
  -> WebSocket session holds Principal
  -> STOMP CONNECT
  -> STOMP SEND/SUBSCRIBE
  -> inbound authorization by message type + destination
```

An authenticated user may **CONNECT validly** yet still lack `CHAT_SEND` or `CHAT_READ`. Conversely, a rule permitting STOMP CONNECT does not mean sending/receiving on every topic is permitted.

### STOMP CONNECT Has Its Own CSRF Check

According to Spring Security 6.5 docs, `@EnableWebSocketSecurity` enforces CSRF checks on inbound STOMP CONNECT as a same-origin defense. Browsers do not enforce the Same-Origin Policy on WebSockets the way they do on fetch/XHR, so origin restrictions and an appropriate CSRF policy are required. Typically the CSRF token is sent in **STOMP native headers** on CONNECT rather than putting it in a query parameter, which is unsafe.

**Do not disable CSRF application-wide** just to "get WebSocket running." With SockJS fallback, narrow CSRF adjustments on exact transport URLs may be needed while keeping same-origin/token checks where required.

### JWT in CONNECT Headers Is Not Automatically Verified

Spring Framework by default does not treat STOMP `login`/`passcode` headers as HTTP authentication credentials. If you want bearer tokens in STOMP CONNECT, you must add a custom `ChannelInterceptor` that processes the token and calls `accessor.setUser(authentication)` after verification. Ensure the authentication interceptor runs **before** the authorization interceptor, e.g., using proper ordering per the documentation.

Do not treat a raw `Authorization: Bearer ...` in STOMP headers as granted authority without a component verifying signature/issuer/audience/expiry, and avoid passing tokens in URL query strings where logs/history can capture them.

## 8. Second-Layer Policy: Routed SEND Does Not Mean Valid Content

Even if a `MESSAGE /app/chat.send` frame passes a `hasAuthority("CHAT_SEND")` rule, the controller must still check:

- The real Principal from the session, never trusting `from` in the payload.
- Whether the user belongs to the room/tenant if the request specifies a room.
- Payload length and format; spam/DoS and injection defenses.
- Object-level policies for the room/document/action.
- Appropriate timing/capability within the transaction.
- Send quotas, auditing, and moderation per business rules.
- Never using a client header/userId to spoof the sender.

Counterexample:

```json
{
  "from": "system-admin",
  "roomId": "alpha",
  "text": "This is an official announcement"
}
```

If the controller accepts `from` from JSON and broadcasts it as coming from an admin, a general `CHAT_SEND` privilege turns into impersonation. Use `Principal.getName()` and keep system-announcement flows separate under stronger policies.

Messaging authorization should have two tiers:

```text
MESSAGE access:
  frame type + destination + baseline authority

Business access:
  authenticated principal + tenant + room/member + object state + payload
```

## 9. Spring Security 6.5 Config: Separate Rules for MESSAGE and SUBSCRIBE

`MessageSecurityConfig.java` in the example project:

```java
package demo.stomp;

import static org.springframework.messaging.simp.SimpMessageType.CONNECT;
import static org.springframework.messaging.simp.SimpMessageType.DISCONNECT;
import static org.springframework.messaging.simp.SimpMessageType.HEARTBEAT;
import static org.springframework.messaging.simp.SimpMessageType.MESSAGE;
import static org.springframework.messaging.simp.SimpMessageType.SUBSCRIBE;
import static org.springframework.messaging.simp.SimpMessageType.UNSUBSCRIBE;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
public class MessageSecurityConfig {

    @Bean
    public AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        return configureRules(messages);
    }

    // Package-private so unit tests exercise the exact same policy.
    static AuthorizationManager<Message<?>> configureRules(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
                // Control frames: do not implicitly grant SEND/SUBSCRIBE.
                .simpTypeMatchers(
                        CONNECT, DISCONNECT, UNSUBSCRIBE, HEARTBEAT)
                    .authenticated()

                // SEND to application controller: requires CHAT_SEND.
                .simpMessageDestMatchers("/app/chat.send")
                    .hasAuthority("CHAT_SEND")

                // SUBSCRIBE to broker topic: requires CHAT_READ.
                .simpSubscribeDestMatchers("/topic/chat.public")
                    .hasAuthority("CHAT_READ")

                // Personal feedback channel; requires authentication.
                .simpSubscribeDestMatchers("/user/queue/errors")
                    .authenticated()

                // All other SEND/SUBSCRIBE frames are denied.
                .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()

                // All remaining message types are denied.
                .anyMessage().denyAll();

        return messages.build();
    }
}
```

**Meaning of each rule:**

1. CONNECT/DISCONNECT/UNSUBSCRIBE/HEARTBEAT require only `authenticated`. This **does not replace** `@EnableWebSocketSecurity`'s default CSRF protection on CONNECT.
2. `simpMessageDestMatchers("/app/chat.send")` matches only `SimpMessageType.MESSAGE`, corresponding to client SEND.
3. `simpSubscribeDestMatchers("/topic/chat.public")` matches only `SimpMessageType.SUBSCRIBE`.
4. `/user/queue/errors` has its own subscribe rule without opening all of `/queue/**`.
5. Catch-all `MESSAGE, SUBSCRIBE` deny protects unlisted destinations.
6. `anyMessage().denyAll()` prevents the policy from falling into an unexpected allow state.

This is a sample policy **using `CHAT_SEND`/`CHAT_READ` authorities granted through authentication**. In systems with different roles/authorities, map accurately from the real source; never mint `CHAT_SEND` just because a client sends an arbitrary header.

### Why Block Clients from Sending to /topic/chat.public?

With this setup, clients only SEND to `/app/chat.send`. The controller validates content, and then the server uses `SimpMessagingTemplate` to publish `/topic/chat.public`. This prevents clients from bypassing the controller and impersonating the server publisher.

### Why Block SUBSCRIBE to /app/chat.send?

`/app` is for application message handlers, not broker subscriptions. If a client subscribes directly to `/app/chat.send`, no rule permits it, so it is denied. A user with `CHAT_SEND` does not automatically become a subscriber either.

## 10. WebSocketMessageBrokerConfigurer: Routing and Origin Restrictions

`WebSocketConfig.java`:

```java
package demo.stomp;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry endpoints) {
        endpoints.addEndpoint("/ws")
                .setAllowedOrigins("https://chat.example.org");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry broker) {
        broker.setApplicationDestinationPrefixes("/app");
        broker.enableSimpleBroker("/topic", "/queue");
        broker.setUserDestinationPrefix("/user");
    }
}
```

**Note:** `https://chat.example.org` is an illustrative origin. To run the demo locally, configure the right local origin or use a non-browser client permitted by the handshake; **do not** swap in `setAllowedOriginPatterns("*")` in production just to silence CORS/Origin errors. Origin allowlists and CSRF protect against different threats; never use one as an excuse to drop the other.

Broker prefixes `/topic`/`/queue` handle routing and **do not automatically forbid client SEND**. `MessageSecurityConfig` in Section 9 is what enforces inbound authorization.

### Checking Destinations with Separators

In some setups, brokers/matchers may use `.` as a separator instead of `/`. Verify actual pattern matching and prefixes, especially with broker relays or custom `PathMatcher`s. A `/topic/**` rule will not protect `topic.foo` if the router permits alternate forms. Test every exposed production destination.

## 11. Illustrative Controller: Only Server Publishes to the Broker Topic

`ChatController.java`:

```java
package demo.stomp;

import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    private final SimpMessagingTemplate messaging;

    public ChatController(SimpMessagingTemplate messaging) {
        this.messaging = messaging;
    }

    @MessageMapping("/chat.send")
    public void send(ChatInput input, Principal principal) {
        if (principal == null) {
            throw new IllegalArgumentException("No authenticated sender");
        }
        if (input == null || input.text() == null
                || input.text().isBlank()
                || input.text().length() > 500) {
            throw new IllegalArgumentException("Invalid chat text");
        }

        ChatEvent event = new ChatEvent(
                principal.getName(), input.text().trim());
        messaging.convertAndSend("/topic/chat.public", event);
    }

    public record ChatInput(String text) {}
    public record ChatEvent(String sender, String text) {}
}
```

The client sends `SEND /app/chat.send` with a JSON body such as:

```json
{"text":"Hello everyone"}
```

Once it passes inbound `CHAT_SEND` authority and controller validation, the server publishes an event:

```json
{"sender":"alice","text":"Hello everyone"}
```

This is an **illustrative schema**, not a guarantee of exact runtime serialization without testing. Crucially, the client cannot pass a `sender` property to impersonate someone else, because the server uses the session's `Principal`.

If separate tenants/rooms exist, check membership in the controller/service before publishing and use tenant-bound topics. On long-lived WebSocket connections, do not assume membership remains valid forever merely because the initial handshake succeeded.

### Securing System Announcements

Do not reuse the same `/app/chat.send` endpoint for system announcements relying only on `CHAT_SEND`. A `/app/system.announce` endpoint requires a higher authority/policy (e.g., `SYSTEM_ANNOUNCE`) and only trusted server/services should be able to publish. Direct client SEND to `/topic/system/announcements` must always be denied by inbound policy.

## 12. Configuring HTTP Security for the Handshake

In the Servlet example, the HTTP handshake `GET /ws` still needs proper authentication.

`StompDemoApplication.java`:

```java
package demo.stomp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
public class StompDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(StompDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain httpSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/ws").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    InMemoryUserDetailsManager users() {
        UserDetails writer = User.withUsername("writer")
                .password("{noop}pass")
                .authorities("CHAT_SEND")
                .build();

        UserDetails reader = User.withUsername("reader")
                .password("{noop}pass")
                .authorities("CHAT_READ")
                .build();

        UserDetails both = User.withUsername("both")
                .password("{noop}pass")
                .authorities("CHAT_SEND", "CHAT_READ")
                .build();

        return new InMemoryUserDetailsManager(writer, reader, both);
    }
}
```

**Never use `{noop}pass` in production.** The demo merely illustrates authorities on an authenticated session. The browser WebSocket API does not let scripts freely add HTTP Authorization headers on the handshake; if a browser app uses Basic/cookie login, HTTP authentication must happen before WebSocket connection, alongside SameSite cookies and CSRF/origin rules. A Java STOMP client can send HTTP headers via its client library.

**CSRF note:** `@EnableWebSocketSecurity` still requires a valid CSRF token on inbound STOMP CONNECT per Spring Security docs. Therefore, **HTTP Basic credentials alone do not prove an end-to-end browser STOMP CONNECT will succeed**; client and session/token flows must be configured accordingly.

## 13. Maven Java 17: Example Project and Dependencies

To run the Spring configuration above, you can create a project:

```text
stomp-send-subscribe-security/
├── pom.xml
└── src/
    ├── main/java/demo/stomp/
    │   ├── StompDemoApplication.java
    │   ├── WebSocketConfig.java
    │   ├── MessageSecurityConfig.java
    │   └── ChatController.java
    └── test/java/demo/stomp/
        └── MessageSecurityRulesTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>stomp-send-subscribe-security</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
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
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

**Distinguishing the libraries:** `spring-boot-starter-websocket` supplies the WebSocket/STOMP framework, whereas `spring-security-messaging` contains the authorization components protecting messages. `spring-boot-starter-security` provides authentication/`SecurityFilterChain`. Without the messaging security module, enabling WebSocket routing creates no SEND/SUBSCRIBE policy.

Spring Boot 3.5.16 is a published 3.5 release; for new production deployments, choose a currently supported maintenance branch. The example project targets Spring Security 6.5 APIs; if using Spring Security 7.x, check builder APIs and the migration guide.

### Running Unit Tests Before Starting the Server

```bash
java -version
mvn -version
mvn -q clean test
```

The tests in the next section exercise `AuthorizationManager<Message<?>>` directly. They **do not create a real STOMP WebSocket connection** and do not prove CSRF/origin/JWT transport has been tested. For end-to-end verification, add STOMP client tests with an authenticated handshake and valid CSRF token.

## 14. Direct JUnit Unit Tests for MESSAGE vs. SUBSCRIBE with Spring Security

`MessageSecurityRulesTest.java`:

```java
package demo.stomp;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

class MessageSecurityRulesTest {

    private final AuthorizationManager<Message<?>> rules =
            MessageSecurityConfig.configureRules(
                    MessageMatcherDelegatingAuthorizationManager.builder());

    private static Authentication user(
            String username, String... authorities) {

        return new UsernamePasswordAuthenticationToken(
                username, "n/a",
                AuthorityUtils.createAuthorityList(authorities));
    }

    private static Message<?> message(
            SimpMessageType type, String destination) {

        SimpMessageHeaderAccessor accessor =
                SimpMessageHeaderAccessor.create(type);

        if (destination != null) {
            accessor.setDestination(destination);
        }
        accessor.setLeaveMutable(true);
        return MessageBuilder.createMessage(
                new byte[0], accessor.getMessageHeaders());
    }

    private boolean permitted(
            Authentication user,
            SimpMessageType type,
            String destination) {

        AuthorizationResult result = rules.authorize(
                () -> user, message(type, destination));

        assertNotNull(result, "No authorization decision");
        return result.isGranted();
    }

    @Test
    void writerCanSendToApplicationRoute() {
        assertTrue(permitted(user("writer", "CHAT_SEND"),
                SimpMessageType.MESSAGE, "/app/chat.send"));
    }

    @Test
    void readerCannotSendToApplicationRoute() {
        assertFalse(permitted(user("reader", "CHAT_READ"),
                SimpMessageType.MESSAGE, "/app/chat.send"));
    }

    @Test
    void readerCanSubscribeToChatTopic() {
        assertTrue(permitted(user("reader", "CHAT_READ"),
                SimpMessageType.SUBSCRIBE, "/topic/chat.public"));
    }

    @Test
    void writerWithoutReadAuthorityCannotSubscribe() {
        assertFalse(permitted(user("writer", "CHAT_SEND"),
                SimpMessageType.SUBSCRIBE, "/topic/chat.public"));
    }

    @Test
    void readerCannotPublishDirectlyToBrokerTopic() {
        assertFalse(permitted(user("reader", "CHAT_READ"),
                SimpMessageType.MESSAGE, "/topic/chat.public"));
    }

    @Test
    void evenWriterCannotPublishDirectlyToBrokerTopic() {
        assertFalse(permitted(user("both", "CHAT_SEND", "CHAT_READ"),
                SimpMessageType.MESSAGE, "/topic/chat.public"));
    }

    @Test
    void subscriptionToAppDestinationIsRejected() {
        assertFalse(permitted(user("both", "CHAT_SEND", "CHAT_READ"),
                SimpMessageType.SUBSCRIBE, "/app/chat.send"));
    }

    @Test
    void subscriptionToRawQueueIsRejected() {
        assertFalse(permitted(user("reader", "CHAT_READ"),
                SimpMessageType.SUBSCRIBE, "/queue/private"));
    }

    @Test
    void authenticatedUserCanSubscribeToOwnErrorDestination() {
        assertTrue(permitted(user("reader", "CHAT_READ"),
                SimpMessageType.SUBSCRIBE, "/user/queue/errors"));
    }

    @Test
    void authenticatedUserCanConnectAtAuthorizationLayer() {
        assertTrue(permitted(user("reader", "CHAT_READ"),
                SimpMessageType.CONNECT, null));
    }

    @Test
    void unknownSendDestinationIsDenied() {
        assertFalse(permitted(user("writer", "CHAT_SEND"),
                SimpMessageType.MESSAGE, "/app/unlisted"));
    }

    @Test
    void missingDestinationForMessageIsDenied() {
        assertFalse(permitted(user("writer", "CHAT_SEND"),
                SimpMessageType.MESSAGE, null));
    }
}
```

These are **12 JUnit 5 test methods** testing the message policy directly. `Authentication` in the tests is created as an authenticated principal (three-argument constructor), not a real HTTP login.

**Key strength of the test:** the same destination `/topic/chat.public` permits SUBSCRIBE for `reader`, yet denies MESSAGE for all clients, even a user holding both `CHAT_SEND` and `CHAT_READ`. That proves the policy **does not grant based on destination alone**.

### A Note on API Versions

In Spring Security 6.5, `AuthorizationManager.authorize(...)` (introduced in 6.4) returns `AuthorizationResult`; `AuthorizationResult.isGranted()` reports the decision. JavaDoc 6.5 notes `check(...)` is deprecated in favor of `authorize(...)`. Before copying to Spring Security 5.8 or 7.x, verify the corresponding interface/builder API, especially by compiling and running tests.

### What Do These Tests Not Prove?

They test only pure `MessageMatcherDelegatingAuthorizationManager`. They **do not** verify:

- That `@EnableWebSocketSecurity` installed inbound `ChannelInterceptor`s in the right order.
- HTTP handshake authentication/JWT/cookies.
- STOMP CONNECT CSRF tokens and origin restrictions.
- Broker routing, controller invocation, or JSON serialization.
- User destination transformation, token expiry, or dynamic room membership.
- Broker relay authentication and external broker ACLs.

For end-to-end proof, use a STOMP client running in a test context and assert actual reception or non-reception of server MESSAGEs.

## 15. Pure Java 17: Simulating SEND and SUBSCRIBE Policy

If you do not want to spin up Maven yet, the standalone Java 17 example below clarifies the **decision logic**. It is not a Spring Security implementation and does not simulate handshake/CSRF/broker; it is designed for deterministic stdout.

File `StompPolicyLab.java`:

```java
import java.util.Set;

public final class StompPolicyLab {

    enum Type { CONNECT, MESSAGE, SUBSCRIBE, DISCONNECT }

    record User(boolean authenticated, Set<String> authorities) {
        boolean has(String authority) {
            return authenticated && authorities.contains(authority);
        }
    }

    record Frame(Type type, String destination) {}

    private static boolean allowed(User user, Frame frame) {
        if (!user.authenticated()) {
            return false;
        }

        if (frame.type() == Type.CONNECT
                || frame.type() == Type.DISCONNECT) {
            return true;
        }

        if (frame.type() == Type.MESSAGE
                && "/app/chat.send".equals(frame.destination())) {
            return user.has("CHAT_SEND");
        }

        if (frame.type() == Type.SUBSCRIBE
                && "/topic/chat.public".equals(frame.destination())) {
            return user.has("CHAT_READ");
        }

        if (frame.type() == Type.SUBSCRIBE
                && "/user/queue/errors".equals(frame.destination())) {
            return true;
        }

        // All unlisted destinations/message types: DENY.
        return false;
    }

    private static void example(
            String label, User user, Type type, String destination) {

        System.out.println(label + "="
                + allowed(user, new Frame(type, destination)));
    }

    public static void main(String[] args) {
        User writer = new User(true, Set.of("CHAT_SEND"));
        User reader = new User(true, Set.of("CHAT_READ"));
        User both = new User(true, Set.of("CHAT_SEND", "CHAT_READ"));
        User anonymous = new User(false, Set.of());

        example("writer_send_app", writer,
                Type.MESSAGE, "/app/chat.send");
        example("writer_subscribe_topic", writer,
                Type.SUBSCRIBE, "/topic/chat.public");
        example("reader_subscribe_topic", reader,
                Type.SUBSCRIBE, "/topic/chat.public");
        example("reader_send_topic", reader,
                Type.MESSAGE, "/topic/chat.public");
        example("reader_send_app", reader,
                Type.MESSAGE, "/app/chat.send");
        example("both_send_app", both,
                Type.MESSAGE, "/app/chat.send");
        example("both_subscribe_topic", both,
                Type.SUBSCRIBE, "/topic/chat.public");
        example("both_send_topic", both,
                Type.MESSAGE, "/topic/chat.public");
        example("reader_subscribe_raw_queue", reader,
                Type.SUBSCRIBE, "/queue/private");
        example("reader_subscribe_app", reader,
                Type.SUBSCRIBE, "/app/chat.send");
        example("reader_connect", reader,
                Type.CONNECT, null);
        example("anonymous_connect", anonymous,
                Type.CONNECT, null);
    }
}
```

Run with JDK 17 or higher:

```bash
javac StompPolicyLab.java
java StompPolicyLab
```

Stdout per program logic:

```text
writer_send_app=true
writer_subscribe_topic=false
reader_subscribe_topic=true
reader_send_topic=false
reader_send_app=false
both_send_app=true
both_subscribe_topic=true
both_send_topic=false
reader_subscribe_raw_queue=false
reader_subscribe_app=false
reader_connect=true
anonymous_connect=false
```

Reasons:

- Writer has only `CHAT_SEND`: sending to `/app/chat.send` is valid; subscribing to the topic is invalid.
- Reader has only `CHAT_READ`: subscribing to the topic is valid; SEND to the topic is denied.
- Even a user with both authorities **cannot SEND directly to the broker topic**.
- `/queue/private` and `/app/chat.send` are not listed subscriptions, so they are denied.
- Authenticated CONNECT passes authorization logic in the simulation; there are **no** CSRF/origin/token checks yet.
- Anonymous CONNECT is denied under the example policy.

With real Spring Security, use the matchers in Section 9 to enforce the same logic, and run the Section 14 tests rather than relying on this simulation.

## 16. SUBSCRIBE /user/queue Differs from Direct SUBSCRIBE /queue

Spring supports **user destinations** to send responses to the right recipient.

Server example:

```java
messaging.convertAndSendToUser(
        recipientUsername, "/queue/messages", payload);
```

Clients normally subscribe to:

```text
SUBSCRIBE
id:private-1
destination:/user/queue/messages
```

The framework may translate the logical user destination into a physical broker destination carrying a session-specific suffix. Clients should not be allowed to subscribe directly to physical destinations like `/queue/...-sessionid` simply because they know or guess the name.

**Security point:** permit `simpSubscribeDestMatchers("/user/queue/messages")` for authenticated users, yet **never** open `simpSubscribeDestMatchers("/queue/**").permitAll()`.

However, `/user/queue/messages` does not guarantee payloads reach the right person if the application chooses the wrong username. The data source must:

- Determine the recipient from server-verified identity/membership.
- Never take an arbitrary `recipientUsername` from the client and send secrets without checking permissions.
- Guarantee tenant isolation when usernames can collide across tenants/issuers.
- Check user session counts, multi-device policies, and logout/revocation.
- Disallow client SEND to `/user/queue/messages` except through a dedicated, secured action endpoint.

For private chat apps, `/app/private.send` for senders is typically kept distinct from `/user/queue/messages` for receivers.

## 17. Per-Room or Per-Tenant Topics: Destination Patterns Are Not Enough

Suppose an app has:

```text
/topic/rooms/42
/topic/rooms/43
/topic/tenants/alpha/events
/topic/tenants/beta/events
```

Writing:

```java
messages
    .simpSubscribeDestMatchers("/topic/rooms/**")
    .authenticated();
```

lets any authenticated user subscribe to all rooms unless an additional policy exists. That is **Broken Object Level Authorization** at the messaging layer.

You must check **room membership/tenant**:

```text
ALLOW SUBSCRIBE /topic/rooms/{roomId}
  iff authenticated
  AND membership(subject, roomId) ACTIVE
  AND room.tenantId in subject.authorizedTenants
  AND room.visibility allows subscription
```

And separately for SEND permission:

```text
ALLOW MESSAGE /app/rooms/{roomId}/send
  iff authenticated
  AND senderCanPost(subject, roomId)
  AND room writable
  AND payload/content valid
```

There may be read-only members who can SUBSCRIBE yet not SEND, moderators who can SEND yet cannot view certain restricted channels, and system services that can publish without user room membership.

### Custom AuthorizationManager with Path Variables

Builder `.access(...)` accepts `AuthorizationManager<MessageAuthorizationContext<?>>` to create dynamic policies. Use context destination variables (if supported by the matcher) and the `Authentication` supplier to verify membership **server-side**.

Pseudocode (this is **not a complete class**):

```java
messages
    .simpSubscribeDestMatchers("/topic/rooms/{roomId}")
    .access((authentication, context) -> {
        String roomId = context.getVariables().get("roomId");
        boolean permitted = roomPolicy.canSubscribe(
                authentication.get(), roomId);
        return new AuthorizationDecision(permitted);
    });
```

If `roomPolicy.canSubscribe` queries the database synchronously, account for performance because message authorization typically runs in an interceptor; use proper caching/transaction boundaries and never block unboundedly. Never take `roomId` from an unvalidated payload; canonicalize and cross-check the tenant. With custom managers, **null/abstain or errors** must never turn into PERMIT.

## 18. Why Revoking Permissions Must Handle Active Subscriptions

Suppose Alice subscribes to `/topic/tenants/alpha/events` at 10:00 while her membership is ACTIVE. At 10:15, an admin revokes her membership. While the connection remains alive, the broker may continue pushing events to the old session unless the app handles it.

Spring Security docs confirm authorization applies at **`clientInboundChannel`**; it does not automatically re-evaluate all outgoing messages. Consequently:

- Revoking membership does not necessarily cause the broker to cancel an already-granted subscription.
- When rapid revocation is required, the app must actively cancel subscriptions/sessions or enforce publisher-side audience control.
- You can emit revocation events, disconnect sessions, or maintain a subscription registry keyed by user/tenant/room.
- For highly sensitive data, do not rely solely on SUBSCRIBE-time permission; consider checking send/receive eligibility by entitlement version.
- An expired JWT token while the socket stays open needs a session lifetime/re-authentication policy rather than assuming all rights vanish automatically without a mechanism.

This is a major difference from short-lived HTTP requests: **SUBSCRIBE creates persistent state**. Looking only at an initial successful SUBSCRIBE test is insufficient when permissions change over time.

## 19. Distinguishing Server Publish Rights from Client SEND

The server may broadcast:

```java
messaging.convertAndSend(
        "/topic/system/announcements",
        new Announcement("System maintenance"));
```

This flows through the application/broker path and does not imply clients are allowed to send `MESSAGE` to the same topic. To prevent spoofing:

1. Block inbound `MESSAGE /topic/system/**`.
2. Allow only trusted server components to invoke the publisher.
3. If admin-originated announcements exist, create `/app/system.announce` with a stricter guard.
4. In methods/services, check roles/scopes and audit who triggered it.
5. Never rely on `sender` in the payload to distinguish system messages from user messages.
6. If an external broker exposes credentials, scope broker publisher accounts by namespace.
7. Grant subscribers separate read permissions; non-public notices must not use `permitAll()`.

**Securing a topic requires securing both the publish side and the subscribe side**; those are two distinct rules. If the publisher is a scheduled job, REST controller, or service event, evaluate permissions at the corresponding **data source**.

## 20. End-to-End Tests with a STOMP Client: What Is Needed Beyond Unit Tests?

An end-to-end test can use `WebSocketStompClient`, `SockJsClient`, or a STOMP client supporting handshake credentials. Workflow:

1. Start the Spring application on a random port and configure test identities.
2. Client A performs handshake with a `CHAT_READ` principal and valid CSRF policy.
3. Client A sends `SUBSCRIBE /topic/chat.public`.
4. Client B performs handshake with a `CHAT_SEND` principal and sends `SEND /app/chat.send`.
5. Assert client A receives the exact server-constructed MESSAGE with `sender` equal to B's principal.
6. Client A attempts `SEND /topic/chat.public` and confirms **no** forged MESSAGE is broadcast to subscribers.
7. Client B without `CHAT_READ` attempts to SUBSCRIBE to the topic and assert denied.
8. Test anonymous CONNECT, malicious Origin, and invalid/missing STOMP CSRF.
9. Test socket reconnect, session cleanup, and permission revocation.
10. Use finite timeouts/cancellation so tests never hang.

Illustrative client test pseudocode (not a standalone runnable file):

```java
StompSession reader = connectAuthenticated("reader");
StompSession writer = connectAuthenticated("writer");

subscribe(reader, "/topic/chat.public");
send(writer, "/app/chat.send", "{\"text\":\"hello\"}");
assertReceivedFromServer("writer", "hello");

send(reader, "/topic/chat.public", "{\"sender\":\"system\"}");
assertNoForgedBroadcast();
```

Helpers like `connectAuthenticated`/`assertNoForgedBroadcast` must be implemented with proper CSRF tokens/origins/sessions; never mistake pseudocode for an executed integration test.

### Why Are Section 14 Unit Tests Still Needed?

End-to-end tests depend on ports, schedulers, transport, and session state, making failures harder to debug. Unit tests on `AuthorizationManager<Message<?>>` validate the type+destination matrix quickly and clearly. Integration tests then verify real wiring and CSRF/transport behavior.

## 21. Critical Anti-Patterns

**1. Using `simpDestMatchers("/topic/**").hasRole("USER")` for read access.** The matcher does not restrict to SUBSCRIBE and easily opens inbound MESSAGE.

**2. Letting clients SEND directly to broker prefixes.** Can bypass controller validation and spoof the sender.

**3. Thinking server STOMP MESSAGE and inbound `SimpMessageType.MESSAGE` have the same direction.** Leads to misconfigured matchers.

**4. Using `simpMessageDestMatchers` for subscribe permissions.** Does not match SUBSCRIBE; subscriptions may fall through to unintended rules.

**5. Using `simpSubscribeDestMatchers` for send permissions.** SEND is not checked by a SUBSCRIBE-only matcher.

**6. Missing `anyMessage().denyAll()`.** Easy to leave new destinations/types unprotected when adding features.

**7. Placing a broad `permitAll()` rule before deny rules.** Subsequent catch-alls never take effect for already-matched messages.

**8. Allowing direct `SUBSCRIBE /queue/**`.** Can cross user destination/session boundaries.

**9. Allowing subscription to any room simply for being authenticated.** Lacks room membership/tenant checks.

**10. Securing only CONNECT and assuming SEND/SUBSCRIBE are allowed.** CONNECT is authentication/protocol, not business authorization.

**11. Relying on STOMP `login/passcode` without enabling a custom authentication interceptor.** By default Spring relies on the HTTP Principal.

**12. Passing bearer tokens in URL query parameters.** Can leak into logs/referrers/monitoring; design a proper trusted channel.

**13. Disabling CSRF app-wide to make SockJS work.** Increases Cross-Site WebSocket Hijacking risk.

**14. Allowing browser WebSockets from any origin without a policy.** There is no automatic same-origin enforcement like fetch.

**15. Trusting `from/username/tenant` in client JSON.** Enables sender spoofing and cross-tenant routing.

**16. Revoking permissions while leaving old subscriptions alive indefinitely.** The broker may keep pushing data.

**17. Letting the system broadcast to a sensitive topic without verifying subscribers.** The outbound channel does not reauthorize every message by default.

**18. Testing only the happy path where SEND succeeds.** Misses readers sending to topics or writers subscribing without permission.

**19. Using Spring MVC `@PreAuthorize` on a controller while forgetting inbound broker authorization.** Clients can bypass the controller via broker routes.

**20. Collapsing SEND and SUBSCRIBE roles into one generic `ROLE_USER` when policies differ.** Cannot distinguish read-only from write-only members.

## 22. Production Test Matrix

| # | Scenario | Expectation |
| --- | --- | --- |
| 1 | CHAT_SEND MESSAGE `/app/chat.send` | PERMIT |
| 2 | CHAT_SEND SUBSCRIBE `/topic/chat.public` | DENY without CHAT_READ |
| 3 | CHAT_READ SUBSCRIBE `/topic/chat.public` | PERMIT |
| 4 | CHAT_READ MESSAGE `/topic/chat.public` | DENY |
| 5 | CHAT_READ MESSAGE `/app/chat.send` | DENY |
| 6 | CHAT_SEND+CHAT_READ MESSAGE `/topic/chat.public` | DENY |
| 7 | CHAT_SEND+CHAT_READ SUBSCRIBE `/topic/chat.public` | PERMIT |
| 8 | CHAT_SEND+CHAT_READ MESSAGE `/app/chat.send` | PERMIT |
| 9 | Authenticated SUBSCRIBE `/user/queue/errors` | PERMIT per contract |
| 10 | Authenticated SUBSCRIBE `/queue/private` | DENY |
| 11 | SUBSCRIBE `/app/chat.send` | DENY |
| 12 | MESSAGE `/app/unknown` | DENY |
| 13 | MESSAGE/SUBSCRIBE missing destination | DENY |
| 14 | Anonymous CONNECT | DENY |
| 15 | Authenticated CONNECT missing CSRF | Rejected per STOMP CSRF policy |
| 16 | Handshake Origin not in allowlist | Rejected |
| 17 | Forged payload `sender=system` | Server sets real principal or denies |
| 18 | Tenant alpha SUBSCRIBE topic beta | DENY |
| 19 | Read-only room member SEND room | DENY |
| 20 | Write-only room member SUBSCRIBE room | DENY if policy forbids reading |
| 21 | Membership revoked while socket open | Stops receiving data within revocation SLA |
| 22 | Admin logs out/token expires | Session/policy stops granting indefinitely |
| 23 | External broker relay wrong credentials | No unauthorized publish/subscribe |
| 24 | Server emits announcement | Only authorized subscribers receive it |
| 25 | Client SEND to `/topic/system/**` | Cannot spoof announcements |

A test asserting only that `AuthorizationManager` returns false does not prove all outbound leaks are prevented. When protecting sensitive data, assert that **clients receive no unauthorized messages** and verify broker/session cleanup.

## 23. How to Debug When SEND or SUBSCRIBE Returns an Error

The first question is not "does the user have `ROLE_USER`?" but rather:

1. **What is the frame type?** STOMP SEND → inbound `SimpMessageType.MESSAGE`; SUBSCRIBE → `SimpMessageType.SUBSCRIBE`.
2. **What is the destination?** `/app/chat.send` or `/topic/chat.public`? Is a prefix transformed before the matcher?
3. **Which channel does the message enter?** `clientInboundChannel` or server `brokerChannel`?
4. **Is the user authenticated?** HTTP handshake Principal or custom CONNECT interceptor?
5. **What are the actual authorities?** Do `CHAT_SEND`/`CHAT_READ`/roles/scopes match the contract?
6. **Which matcher comes first?** A broad `simpDestMatchers` can match both types.
7. **Default deny?** Is an unmatched message denied rather than abstained?
8. **CSRF/origin?** Was CONNECT rejected before reaching MESSAGE/SUBSCRIBE?
9. **Was the controller invoked?** Does SEND to `/app` match `@MessageMapping`?
10. **Does the broker hold the subscription?** Was SUBSCRIBE accepted while the broker simply has not emitted an event yet?
11. **User destination?** Did the client subscribe to `/user/queue/...` with the right logical prefix?
12. **Tenant/room membership?** Is the destination format valid yet the user is barred from that room?
13. **Stale subscription?** Did entitlements change without closing the socket?
14. **Broker relay?** Do broker accounts/routing/permissions differ from the simple broker?

Logs/metrics should capture at minimum: user alias, STOMP type, canonical destination (optionally hashing tenant/room), policy rule ID, permit/deny, session ID alias, and reason code. Never log bearer tokens, STOMP credentials, or PII-bearing payloads. Avoid metric labels keyed by raw `roomId`/`sessionId` due to high cardinality.

## 24. Secure Configuration Checklist

- [ ] Understand that STOMP SEND is inbound `SimpMessageType.MESSAGE` and SUBSCRIBE is `SimpMessageType.SUBSCRIBE`.
- [ ] Use `simpMessageDestMatchers` for SEND/application actions.
- [ ] Use `simpSubscribeDestMatchers` for receiving data/broker topics.
- [ ] Do not use generic `simpDestMatchers` for a read-only topic without a type guard.
- [ ] Block client MESSAGE to `/topic/**` and `/queue/**` when broker publishing is server-only.
- [ ] Block direct client SUBSCRIBE to physical `/queue/**` without policy.
- [ ] Open `/app/**` only for actions protected by controllers/services.
- [ ] Include catch-all deny for unmatched MESSAGE/SUBSCRIBE and remaining message types.
- [ ] Test authentication/CSRF/origin rules for both handshake and STOMP CONNECT.
- [ ] Never trust unverified STOMP login/passcode or bearer headers.
- [ ] Never take sender/recipient/tenant from client JSON as the identity source.
- [ ] Verify object/tenant policies and payloads on SEND actions before publishing.
- [ ] Verify real membership on SUBSCRIBE for rooms/tenants/private queues.
- [ ] Revoke/cancel old subscriptions within SLA when entitlements change.
- [ ] Ensure neither the simple broker nor external relays grant clients unexpected publish rights.
- [ ] Unit test the MESSAGE/SUBSCRIBE matrix on the exact same destinations.
- [ ] Run integration tests with a STOMP client confirming zero forged broadcasts or data leaks.
- [ ] Test token expiration, disconnect, reconnect, and SockJS/CSRF/origin.
- [ ] Separate auth failures, SEND denials, SUBSCRIBE denials, and broker errors in monitoring.

**Conclusion:** Spring Security message authorization cannot ask only **"is the destination `/topic/chat.public`?"**. The right question is **"is the caller sending a MESSAGE or registering a SUBSCRIBE to which destination, with what permissions and data?"**. Allowing SUBSCRIBE does not grant SEND, allowing SEND to an application endpoint does not grant direct publishing to the broker, and a successful CONNECT does not replace object/tenant checks per action. Separate message types and destinations cleanly, apply deny-by-default, and test both directions to prevent event spoofing and data leaks.

## Official References

- [Spring Security 6.5 — WebSocket Security](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/websocket.html)
- [Spring Security — WebSocket Security (current)](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- [Spring Security 6.5 — MessageMatcherDelegatingAuthorizationManager.Builder JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.html)
- [Spring Security 6.5 — AuthorizationManager JavaDoc](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Framework — STOMP Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework — STOMP Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html)
- [Spring Framework — STOMP Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html)
- [Spring Framework — STOMP User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework — STOMP Authorization](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html)
