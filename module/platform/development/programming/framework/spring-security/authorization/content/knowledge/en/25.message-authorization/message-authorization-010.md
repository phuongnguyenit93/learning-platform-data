# Testing Sender Spoofing, Unauthorized Channel Subscriptions, and Out-of-Policy Messages

> **Topic:** Spring Security – message authorization (STOMP over WebSocket, Servlet side). This hands-on lab tests the **inbound application flow**: sender identity, `SUBSCRIBE` permissions, and `SEND` permissions by message type/destination. Examples use Java 17+, Spring Boot with Spring WebSocket, Spring Security Messaging, and JUnit 5.

## 1. Objectives and Threat Model

After this lesson, you must prove through tests that:

1. User A cannot claim to be User B or an administrator by editing `sender`/`from` in the payload or setting custom STOMP headers.
2. Users only subscribe (`SUBSCRIBE`) to permitted channels; knowing a destination name or logging in successfully **does not equate** to permission to view data.
3. Clients cannot send (`SEND`) directly to broker channels (`/topic/**`, `/queue/**`) to spoof system announcements or bypass business processing.
4. Every **message type + destination** pair outside the allowlist is denied by default.
5. Negative tests also verify **zero side effects**: no data persisted, no message broadcast, and no payload leaked to recipients.

Suppose the chat system has the following routes:

| Client Action | Destination | Rule |
| --- | --- | --- |
| `SEND` room message | `/app/rooms/{roomId}/send` | Logged in, actually a room member; author must come from `Principal` |
| `SUBSCRIBE` room messages | `/topic/rooms/{roomId}` | Logged in and a member of that exact room |
| `SUBSCRIBE` general announcements | `/topic/announcements` | Logged in |
| `SUBSCRIBE` personal errors | `/user/queue/errors` | Logged in; uses Spring's user destination |
| `SEND` admin announcement | `/app/admin/announce` | Holds `ROLE_ADMIN` |
| Any `SEND` to `/topic/**`, `/queue/**`, or `/user/**` | Broker/user destination | Deny |
| `SUBSCRIBE` internal/unlisted channels | e.g., `/topic/internal`, `/queue/private` | Deny |

**Important distinction:** STOMP clients send a `SEND` frame, represented as `SimpMessageType.MESSAGE` in the Spring Messaging layer; a `SUBSCRIBE` frame is `SimpMessageType.SUBSCRIBE`. A `MESSAGE` pushed by the server to subscribers is outbound traffic, not a command a client is allowed to emit directly to the broker.

```text
Client ──HTTP handshake (/ws)──> WebSocket session with authenticated Principal
       ──STOMP CONNECT────────> checks connection and STOMP CSRF when enabled by default
       ──SEND/SUBSCRIBE───────> clientInboundChannel
                                 ├─ authentication/identity context
                                 ├─ AuthorizationManager: type + destination + room permission
                                 └─ controller or broker if valid
Server ──brokerChannel / clientOutboundChannel──> authorized subscribers
```

Spring Security primarily secures **`clientInboundChannel`**, rather than automatically checking every outgoing message. Therefore, unauthorized channel subscriptions must be blocked on inbound; an HTTP filter for `/ws` cannot replace this policy.

## 2. Three Security Flaws to Simulate

### 2.1. Sender Spoofing

Alice's legitimate client sends:

```json
{"sender":"admin","text":"Room has been unlocked"}
```

If the server forwards `sender` verbatim from JSON, recipients may believe the message came from `admin`. Variants of the same flaw: sending `fromUserId: "bob"`, setting STOMP header `user: admin`, changing `login`/`passcode` in `CONNECT`, or changing `roomId` to post on behalf of another room. With Spring's STOMP over WebSocket, `login` and `passcode` headers do not automatically replace the HTTP-authenticated identity; nor must the application trust arbitrary client-declared headers.

**Correct invariant:** `stored.sender == principal.getName()` and `broadcast.sender == principal.getName()`. Identity must originate from the server-bound authenticated session (or properly implemented STOMP token authentication via interceptor), never from input data.

### 2.2. Unauthorized Channel Subscription

Alice is a member of room `r1` yet attempts `SUBSCRIBE /topic/rooms/r2`. With only a rule `/topic/rooms/** -> authenticated()`, Alice passes despite not belonging to `r2`. Authorization must evaluate the **resource object** (`roomId`) alongside identity; `ROLE_USER` alone is insufficient.

Likewise, clients must not directly subscribe to `/queue/private` or physical broker destinations generated after Spring resolves `/user/queue/...`. Subscribing to the session's own `/user/queue/errors` path does not grant access to every queue under `/queue/**`.

### 2.3. Out-of-Policy Messages

A client sends `SEND /topic/announcements` with content claiming to come from the system. If the broker accepts it directly, the server can broadcast it to all subscribers without running `@MessageMapping`/application permission checks. Another client sends to `/app/unknown`, `/app/admin/announce` without privileges, or sends a frame lacking a valid destination. These cases must test **frame type, destination, permissions, and payload** separately.

**Do not infer** that merely returning STOMP `ERROR` means safety: the framework/broker may close the connection, return an error, or reject at another layer. The mandatory security outcome is **no unauthorized operation occurs**.

## 3. Sample Configuration: Explicit Allow, Deny by Default

The code snippets below are separate Java files in package `example.messaging` of a Servlet Spring Boot application with dependencies: `spring-boot-starter-websocket`, `spring-boot-starter-security`, `spring-security-messaging`, and `spring-boot-starter-test` (`test` scope). Use dependency versions managed by the Spring Boot BOM. The configuration highlights **message rules**, and does not replace real HTTP authentication, CSRF, or room-membership storage in a project.

**`MessagingWebSocketConfig.java`**

```java
package example.messaging;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class MessagingWebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws"); // Same-origin only by default.
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user");
    }
}
```

**`RoomMembership.java`** — business adapter; must have an implementation querying room membership from trusted data:

```java
package example.messaging;

public interface RoomMembership {
    boolean isMember(String roomId, String username);
}
```

**`MessageSecurityConfig.java`** — place specific rules **before** default-deny rules. `{roomId}` is extracted from the destination, while `Authentication` comes from Spring Security:

```java
package example.messaging;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.messaging.access.intercept.MessageAuthorizationContext;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;

import static org.springframework.messaging.simp.SimpMessageType.MESSAGE;
import static org.springframework.messaging.simp.SimpMessageType.SUBSCRIBE;

@Configuration
@EnableWebSocketSecurity
public class MessageSecurityConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages,
            RoomMembership memberships) {

        AuthorizationManager<MessageAuthorizationContext<?>> roomMember =
                (authentication, context) -> {
                    Authentication user = authentication.get();
                    String roomId = context.getVariables().get("roomId");
                    boolean allowed = user != null
                            && user.isAuthenticated()
                            && !(user instanceof AnonymousAuthenticationToken)
                            && roomId != null
                            && memberships.isMember(roomId, user.getName());
                    return new AuthorizationDecision(allowed);
                };

        return messages
                .nullDestMatcher().authenticated()
                .simpSubscribeDestMatchers("/user/queue/errors").authenticated()
                .simpSubscribeDestMatchers("/topic/announcements").authenticated()
                .simpSubscribeDestMatchers("/topic/rooms/{roomId}")
                    .access(roomMember)
                .simpMessageDestMatchers("/app/rooms/{roomId}/send")
                    .access(roomMember)
                .simpMessageDestMatchers("/app/admin/announce").hasRole("ADMIN")
                .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
                .anyMessage().denyAll()
                .build();
    }
}
```

**Explanation of common pitfalls:**

- `nullDestMatcher().authenticated()` protects frames without a destination such as `CONNECT`, `UNSUBSCRIBE`, and `DISCONNECT`. CSRF checking on `CONNECT` with `@EnableWebSocketSecurity` remains a separate layer; testing `AuthorizationManager` alone does not prove CSRF works.
- `simpMessageDestMatchers(...)` applies to messages from `SEND`; `simpSubscribeDestMatchers(...)` applies to `SUBSCRIBE`. Using a broad `simpDestMatchers("/topic/**").authenticated()` for both types can open a path for clients to publish directly to the broker.
- The room-member rule applies to **both sending and subscribing**. If membership changes while a connection stays open, an appropriate revocation/existing-subscription policy is required; checking at subscribe time does not automatically remove previously granted subscriptions.
- `anyMessage().denyAll()` keeps the system safe when new unlisted destinations or types appear. This rule also ensures new valid messages must be added explicitly.
- A `ROLE_ADMIN` account is permitted to `SEND` to `/app/admin/announce` at the authorization layer; the admin controller must still handle business logic properly. The illustrative setup does not publish that controller.

### 3.1. Identity Binding in the Controller

**`RoomMessageController.java`** — re-verify membership where the mutation happens, and always construct output data using the identity from `Principal`:

```java
package example.messaging;

import java.security.Principal;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Controller;

@Controller
public class RoomMessageController {

    public record SendCommand(String sender, String text) {}
    public record RoomEvent(String sender, String text) {}

    private final SimpMessagingTemplate messaging;
    private final RoomMembership memberships;

    public RoomMessageController(
            SimpMessagingTemplate messaging, RoomMembership memberships) {
        this.messaging = messaging;
        this.memberships = memberships;
    }

    @MessageMapping("/rooms/{roomId}/send")
    public void send(
            @DestinationVariable("roomId") String roomId,
            SendCommand command,
            Principal principal) {

        if (principal == null || !memberships.isMember(roomId, principal.getName())) {
            throw new AccessDeniedException("Not a room member");
        }
        if (command == null || command.text() == null
                || command.text().isBlank() || command.text().length() > 500) {
            throw new IllegalArgumentException("Invalid message text");
        }

        RoomEvent event = new RoomEvent(principal.getName(), command.text());
        messaging.convertAndSend("/topic/rooms/" + roomId, event);
    }
}
```

Here `command.sender()` is **intentionally unused**; that field exists solely to simulate a client trying to spoof identity. In a real design, remove `sender` from the request DTO. Validate payloads (format, length, business-sensitive data) and ensure checks run before DB writes or broadcasts. Controller checks are defense in depth when call paths vary, not a replacement for the policy on `clientInboundChannel`.

## 4. Unit Testing `SEND` and `SUBSCRIBE` Permissions

The goal of pure authorization tests is verifying the **allow/deny** decision for a specific `Authentication`, `SimpMessageType`, and destination. A real WebSocket is unnecessary at this layer.

**`src/test/java/example/messaging/MessageSecurityConfigTest.java`**

```java
package example.messaging;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MessageSecurityConfigTest {

    // Fake test data: Alice is a member of r1, not r2.
    private final RoomMembership memberships =
            (roomId, username) -> "r1".equals(roomId) && "alice".equals(username);

    private final AuthorizationManager<Message<?>> rules =
            new MessageSecurityConfig().messageAuthorizationManager(
                    MessageMatcherDelegatingAuthorizationManager.builder(),
                    memberships);

    private static Authentication user(String username, String role) {
        return new UsernamePasswordAuthenticationToken(
                username, "unused",
                List.of(new SimpleGrantedAuthority("ROLE_" + role)));
    }

    private boolean allowed(Authentication user, SimpMessageType type, String dest) {
        SimpMessageHeaderAccessor headers = SimpMessageHeaderAccessor.create(type);
        headers.setDestination(dest);
        Message<byte[]> incoming =
                MessageBuilder.createMessage(new byte[0], headers.getMessageHeaders());
        var result = rules.authorize(() -> user, incoming);
        return result != null && result.isGranted();
    }

    @Test
    void allowsMemberToSendAndSubscribeWithinOwnRoom() {
        Authentication alice = user("alice", "USER");
        assertTrue(allowed(alice, SimpMessageType.MESSAGE,
                "/app/rooms/r1/send"));
        assertTrue(allowed(alice, SimpMessageType.SUBSCRIBE,
                "/topic/rooms/r1"));
    }

    @Test
    void blocksNonMemberFromSendingAndSubscribingToOtherRoom() {
        Authentication alice = user("alice", "USER");
        assertFalse(allowed(alice, SimpMessageType.MESSAGE,
                "/app/rooms/r2/send"));
        assertFalse(allowed(alice, SimpMessageType.SUBSCRIBE,
                "/topic/rooms/r2"));
    }

    @Test
    void blocksDirectPublishToBrokerEvenWhenSubscribed() {
        Authentication alice = user("alice", "USER");
        assertFalse(allowed(alice, SimpMessageType.MESSAGE,
                "/topic/announcements"));
        assertFalse(allowed(alice, SimpMessageType.MESSAGE,
                "/topic/rooms/r1"));
        assertFalse(allowed(alice, SimpMessageType.MESSAGE,
                "/queue/private"));
    }

    @Test
    void blocksUnknownSubscriptionsAndUnknownApplicationMessages() {
        Authentication alice = user("alice", "USER");
        assertFalse(allowed(alice, SimpMessageType.SUBSCRIBE,
                "/topic/internal"));
        assertFalse(allowed(alice, SimpMessageType.SUBSCRIBE,
                "/queue/private"));
        assertFalse(allowed(alice, SimpMessageType.MESSAGE,
                "/app/unknown"));
    }

    @Test
    void distinguishesMessagePermissionFromSubscribePermission() {
        Authentication alice = user("alice", "USER");
        assertTrue(allowed(alice, SimpMessageType.SUBSCRIBE,
                "/topic/announcements"));
        assertFalse(allowed(alice, SimpMessageType.MESSAGE,
                "/topic/announcements"));
    }

    @Test
    void rejectsAdminSendWithoutAdminRole() {
        assertFalse(allowed(user("alice", "USER"), SimpMessageType.MESSAGE,
                "/app/admin/announce"));
        assertTrue(allowed(user("admin", "ADMIN"), SimpMessageType.MESSAGE,
                "/app/admin/announce"));
    }
}
```

These tests **do not open a real STOMP connection**, so they do not test `CONNECT` headers/CSRF, message delivery, broker-generated STOMP errors, or the relationship between the session and `Principal`. They test only the matcher policy and room permissions under the declared assumptions. Newer Spring Security versions use `AuthorizationManager.authorize`; on older projects, check the API of the running version.

## 5. Testing Anti-Spoofing at the Handler

Alongside message rules, you must prove the handler does not trust client payloads and produces no side effects when the user does not belong to the room. The example below uses Mockito/JUnit 5, checking the **publication destination and entire event** rather than only HTTP/STOMP status.

**`src/test/java/example/messaging/RoomMessageControllerTest.java`**

```java
package example.messaging;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.security.access.AccessDeniedException;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class RoomMessageControllerTest {

    @Test
    void senderInPayloadCannotImpersonateAdmin() {
        SimpMessagingTemplate outbound = mock(SimpMessagingTemplate.class);
        RoomMembership members =
                (room, username) -> "r1".equals(room) && "alice".equals(username);
        RoomMessageController controller = new RoomMessageController(outbound, members);

        controller.send("r1",
                new RoomMessageController.SendCommand("admin", "Hello"),
                () -> "alice");

        verify(outbound).convertAndSend(
                "/topic/rooms/r1",
                new RoomMessageController.RoomEvent("alice", "Hello"));
    }

    @Test
    void sendingToForeignRoomHasNoBroadcastSideEffect() {
        SimpMessagingTemplate outbound = mock(SimpMessagingTemplate.class);
        RoomMembership members =
                (room, username) -> "r1".equals(room) && "alice".equals(username);
        RoomMessageController controller = new RoomMessageController(outbound, members);

        assertThrows(AccessDeniedException.class, () ->
                controller.send("r2",
                        new RoomMessageController.SendCommand("alice", "Secret"),
                        () -> "alice"));

        verifyNoInteractions(outbound);
    }

    @Test
    void invalidPayloadHasNoBroadcastSideEffect() {
        SimpMessagingTemplate outbound = mock(SimpMessagingTemplate.class);
        RoomMembership members = (room, username) -> true;
        RoomMessageController controller = new RoomMessageController(outbound, members);

        assertThrows(IllegalArgumentException.class, () ->
                controller.send("r1",
                        new RoomMessageController.SendCommand("alice", "  "),
                        () -> "alice"));
        verifyNoInteractions(outbound);
    }
}
```

Run in a project with dependencies declared and source files placed in the right package:

```bash
./mvnw test -Dtest=MessageSecurityConfigTest,RoomMessageControllerTest
```

Expected: Maven finishes successfully and **6 message-rule tests + 3 controller tests** all pass. Never treat assumed log/stdout lines as proof; read the runner's actual output. If using Gradle, run the corresponding test classes via `./gradlew test`. The project must supply a `RoomMembership` implementation to boot the real application; the two unit tests above use a fake membership and therefore need no database.

## 6. STOMP Integration Testing: Real Client, Real Session

Unit tests cannot prove whether a client can **send forged headers over the network**. Add integration tests with an embedded server and `WebSocketStompClient` (or a standalone STOMP client), using at least two authenticated accounts Alice/Bob, two rooms `r1`/`r2`, and an admin account. Also include **valid (positive) flows** so a misconfiguration that rejects everything does not falsely turn negative tests green.

**How to structure fixtures:**

1. Alice belongs to `r1`; Bob belongs to `r2`; Admin holds `ROLE_ADMIN`. Both Alice and Bob hold `ROLE_USER`.
2. Use an HTTP handshake with a valid session/cookie or the application's real token mechanism. If using default STOMP CSRF protection, fetch the session-matching token and send it in **native headers of the CONNECT frame**; authenticating the handshake alone is not necessarily enough.
3. Alice and Bob open separate connections, alongside valid monitoring subscribers on `/topic/rooms/r1`, `/topic/rooms/r2`, and `/topic/announcements`. Push received messages into per-session queues, isolated across tests.
4. Drain queues and synchronize connections/subscriptions (ACK or corresponding server signal if supported by the app protocol) before counting messages. Inspect DB state if applicable.
5. After an attack frame, wait for a **bounded timeout** and verify zero unauthorized messages, zero unauthorized records, and zero privilege changes. Distinguish protocol errors, authorization errors, timeouts, and client disconnects.

### 6.1. Matrix of Negative and Positive Test Cases

| ID | Principal / Client-Sent Frame | Expected Observation |
| --- | --- | --- |
| P01 | Alice `SEND /app/rooms/r1/send`, `sender=alice` | Processed; event records Alice; `r1` subscriber receives exactly 1 event |
| N01 | Alice sends to same destination, `sender=admin` | No event recorded as admin; if validly sent, event still records Alice |
| N02 | Alice `SEND /app/rooms/r2/send` even claiming `sender=bob` | Rejected; Bob/`r2` receive nothing, DB adds no record |
| N03 | Alice adds native header `user: admin` or `simpUser: admin` | Self-declared headers do not elevate privileges; server principal remains Alice |
| N04 | Alice supplies `login=admin`/`passcode=...` in STOMP `CONNECT` | Does not turn Alice into admin; if app has a custom auth interceptor, it must verify a real token |
| N05 | Alice `SUBSCRIBE /topic/rooms/r2` | Receives no `r2` data even when server later emits messages |
| N06 | Alice `SUBSCRIBE /queue/private` | Subscription to receive private data is not created |
| N07 | Alice `SUBSCRIBE /topic/internal` | Rejected by default |
| P02 | Alice `SUBSCRIBE /topic/rooms/r1` | Subscription allowed; receives data for her own room |
| P03 | Alice `SUBSCRIBE /user/queue/errors` | Allowed for Alice's session; does not grant access to Bob's physical queue |
| N08 | Alice `SEND /topic/announcements` | No general announcement broadcast to subscribers |
| N09 | Alice `SEND /topic/rooms/r1` | Cannot bypass controller despite being a room member |
| N10 | Alice `SEND /queue/private` or `/user/queue/errors` | Rejected; cannot send directly to broker/user destinations |
| N11 | Alice `SEND /app/admin/announce` | Rejected for lacking `ROLE_ADMIN` |
| P04 | Admin `SEND /app/admin/announce` | Passes message authorization rules; business handler must still exist and validate |
| N12 | Alice `SEND /app/unknown` or `SUBSCRIBE /topic/unknown` | Rejected by `denyAll` |
| N13 | Anonymous/unauthenticated client connects or sends frames | Protected operation does not run; rejection may occur at handshake, CONNECT/CSRF, or authorization |
| N14 | Empty, oversized, or wrong-type JSON payload sent to valid route | No message/record created after validation; response depends on error-handling mechanism |
| N15 | Alice revoked from `r1` after subscribing | Stops receiving sensitive data per designed revocation policy; may require canceling existing session/subscription |

**Test HTTP and STOMP boundaries separately:** test `GET /ws`/handshake with an invalid session; test `CONNECT` missing CSRF or with bad CSRF; then test `SEND`/`SUBSCRIBE` with valid CSRF and session. If combined into one test where CONNECT fails, you never actually tested message authorization.

### 6.2. Sending Raw STOMP Frames to Catch Routing Bugs

A real STOMP client must send standard frames (a blank line separating headers/payload and ending with a NUL byte `0x00`). Two cases to test:

```text
SEND
destination:/topic/announcements
content-type:text/plain

I am the system!
[NUL]
```

```text
SUBSCRIBE
id:probe-r2
destination:/topic/rooms/r2

[NUL]
```

`[NUL]` here is an **illustrative placeholder for the actual NUL byte**, not a literal character string sent on the wire. In the first example, Alice must not cause `/topic/announcements` subscribers to receive the payload. In the second example, after Bob/the server sends an event to `r2`, Alice's connection must not see that content. A test checking only that `subscribe()` returned a client-side subscription object is **not enough** to conclude the server permitted it.

### 6.3. Verification Conditions and Asynchronous Synchronization

- For passing cases, verify the exact `principal`, `destination`, payload, delivery count, and intended recipients; zero outsiders receive the data.
- For rejected cases, confirm **zero side effects** within a reasonable wait window, check audit events if emitted, and re-read the DB if applicable. Do not depend on one fixed STOMP error string because rejections can happen at multiple layers.
- Use `BlockingQueue`/`CountDownLatch`/timeout-bounded await helpers for conditional waiting; avoid fixed `Thread.sleep`. Give each test independent sessions/subscriptions/queues and clean up afterward.
- Send events with unique IDs so previous messages cannot be confused. If a subscription is rejected, do not assume the broker will always emit `ERROR`; conclude based on **receiving zero data** plus server-side verification.
- For open sessions, test revoked permissions alongside new connections. Whether an old subscription keeps receiving must be tested specifically against the product's subscription-cancellation/session-closing mechanism, rather than inferred from `SUBSCRIBE`-time checks.

## 7. Common Testing and Design Mistakes

1. **Checking only `authenticated()`:** Alice and Bob are both logged in, yet can still access each other's resources. Enforce resource checks bound to `roomId`.
2. **Locking down only the controller:** clients sending directly to `/topic/**` on the broker may bypass the controller. Restrict `MESSAGE` to broker prefixes.
3. **Using overly broad `simpDestMatchers`:** the matcher does not distinguish `MESSAGE` and `SUBSCRIBE`; use type-specific matchers and put `denyAll` last.
4. **Trusting `sender` in JSON:** message authorization may look right while event identity is spoofed. Check output/DB; derive actor from the authenticated `Principal`.
5. **Seeing a rejected connection and concluding every rule works:** it might simply be missing `CONNECT` CSRF. Include a positive control that connects validly before sending attack frames.
6. **Asserting only on errors:** does not prove data was not broadcast or saved. Always assert negative side effects and recipient permissions.
7. **Allowing `/queue/**` thinking user queues protect automatically:** clients may use approved `/user/queue/...`; never open physical queues directly.
8. **Checking subscriptions at subscribe time while forgetting permission changes:** sensitive data can leak through surviving subscriptions after revocation; define disconnect/kick/re-auth requirements.
9. **Mixing up authentication and authorization:** `Origin`/CSRF defend against one attack class, not role and membership checks.
10. **Testing with the same account across all branches:** include at least a regular user, a cross-resource user, an admin, and an anonymous caller; combine positive and negative cases.
11. **Assuming raw WebSockets behave like STOMP:** `@EnableWebSocketSecurity` here applies to Spring Messaging/STOMP and does not automatically protect raw WebSocket endpoints using other APIs directly.
12. **Writing tests only with `AuthorizationManager` yet claiming network header spoofing is prevented:** pure unit tests do not verify the handshake layer, token-auth interceptors, or real message forwarding.

## 8. Workflow to Complete the Lab

- **Define the policy:** list every `SimpMessageType + destination + role + ownership condition`; deny all unlisted paths.
- **Test identity:** put a fake `sender` in payloads and native STOMP headers; assert emitted messages use the real `Principal`.
- **Test channel permissions:** test matching member/room, foreign member/room, physical queues, internal channels, and revoked subscriptions.
- **Test send permissions:** test valid `SEND` via `/app/...`, direct sends to `/topic/**`/`/queue/**`, admin routes, and unknown destinations.
- **Test consequences:** confirm zero broadcasts, zero DB writes, and zero content leaks; use multiple sessions and monitor real subscribers.
- **Separate test layers:** fast unit tests for rules/handlers; integration tests with sessions, CSRF, STOMP, and brokers; thoroughly verify success cases too.

### Reference Documentation

- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html): `@EnableWebSocketSecurity`, authorization for `SEND`/`SUBSCRIBE`, inbound limits, and cross-origin protection.
- [Spring Framework — STOMP Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html): propagating `Principal` from HTTP sessions to WebSockets.
- [Spring Framework — Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html): header-based authentication in STOMP `CONNECT` and interceptor ordering.
- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html): how `/user/queue/...` resolves to session-specific destinations.
- [Spring Framework — Testing STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/testing.html): unit and end-to-end testing.

**Completion criteria:** a legitimate client can exercise its exact permissions; it cannot change identity via payload/headers, view channels it does not belong to, or emit out-of-policy messages. Every negative case proves zero unauthorized business actions occur, not merely that an error notice appeared.