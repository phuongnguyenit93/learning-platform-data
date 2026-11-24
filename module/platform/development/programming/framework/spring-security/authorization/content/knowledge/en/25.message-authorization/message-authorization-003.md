# MessageMatcherDelegatingAuthorizationManager and Rule Ordering in Spring Security Messaging

## 1. Goal: A Misplaced Rule Can Expose the Wrong STOMP Channel

With Spring WebSocket/STOMP, an application can allow clients to send `SEND /app/chat` to invoke a `@MessageMapping`, and allow clients to `SUBSCRIBE /topic/public/news` to receive events from the message broker. However, clients **must not be allowed to send SEND directly to `/topic/**` or `/queue/**`** to spoof server notifications. Nor should a client be able to subscribe to a private topic merely because it has permission to read a public topic.

Spring Security 6.5 provides `MessageMatcherDelegatingAuthorizationManager`, an `AuthorizationManager<Message<?>>` that applies **message-matcher → authorization-decision pairs**. A defining characteristic is **declaration order**: the manager evaluates matchers in order and selects the delegate of the first matching rule. It does not automatically pick the most specific pattern, nor does it evaluate all matchers and AND their permissions together.

This lesson belongs to the **Message Authorization** section of Spring Security Authorization. After studying it, you will be able to:

1. Distinguish STOMP `CONNECT`, `MESSAGE` (typically from a `SEND` frame), `SUBSCRIBE`, `UNSUBSCRIBE`, `DISCONNECT`, and messages with or without a destination.
2. Properly use `MessageMatcherDelegatingAuthorizationManager.Builder`, `nullDestMatcher`, `simpDestMatchers`, `simpMessageDestMatchers`, `simpSubscribeDestMatchers`, `simpTypeMatchers`, and `anyMessage`.
3. Explain why **specific rules must precede broad rules** when they can match the same message.
4. Separate **sending to the application** from **subscribing to the broker**, preventing `/topic/` and `/queue/` spoofing.
5. Place deny-by-default at the end and prevent a "catch-all permit" from swallowing subsequent rules.
6. Integrate `@EnableWebSocketSecurity` and `AuthorizationManager<Message<?>>` into Spring WebSocket Messaging.
7. Write Java 17+ tests with JUnit 5, constructing real messages via `SimpMessageHeaderAccessor`, inspecting `AuthorizationResult`, and testing **intentionally misordered** configurations.
8. Distinguish message authorization from WebSocket handshake authentication, STOMP CONNECT CSRF, user destinations, object/tenant permissions, and outbound protection logic.

**Version scope:** Spring Security 6.5.x, Spring Framework 6.x, Java 17+. The project in Section 8 consists of **unit tests of the real manager** — no WebSocket server startup or socket mocking required; separate tests for handshake/CSRF/real broker behavior are recommended alongside it.

## 2. The Inbound Model and Trust Boundaries

```text
Browser / STOMP client
   |
   | HTTP handshake (HTTP security, cookie/token/Origin)
   v
WebSocket endpoint
   |
   | CONNECT / SEND / SUBSCRIBE / DISCONNECT frames
   v
clientInboundChannel
   |
   +--> SecurityContextChannelInterceptor / principal
   |
   +--> AuthorizationChannelInterceptor
          |
          v
     MessageMatcherDelegatingAuthorizationManager
          |
          +-- matcher #1 ? -> delegate authorization
          +-- matcher #2 ? -> delegate authorization
          +-- matcher #3 ? -> delegate authorization
          +-- ...
          +-- anyMessage() -> denyAll()
          |
          +-- ALLOW -> application handler or broker routing
          +-- DENY  -> message not forwarded to protected destination
```

The diagram simplifies the **inbound** path. Spring Security WebSocket Message Authorization focuses on **`clientInboundChannel`**; do not infer that every **outbound** message is checked by the same rules. Outbound delivery must be protected through subscription restrictions, broker/user-destination isolation, server-side publication logic, and policies on the emitted data.

### 2.1. Example of 4 Destinations with Different Semantics

| Client action | Destination | Purpose | Appropriate Policy |
| --- | --- | --- | --- |
| `SEND` (MESSAGE) | `/app/chat/send` | Invoke application handler | Authority `CHAT_SEND` |
| `SEND` (MESSAGE) | `/topic/public/news` | **Could spoof broker notifications** | **DENY** |
| `SUBSCRIBE` | `/topic/public/news` | Receive public app notifications | Authority `TOPIC_READ` or intentional public policy |
| `SUBSCRIBE` | `/topic/public/admin/alerts` | Receive admin notifications | Authority `TOPIC_ADMIN` |
| `SUBSCRIBE` | `/topic/private/finance` | Receive sensitive topic | Authority `TOPIC_PRIVATE` + object/tenant policy if needed |
| `SUBSCRIBE` | `/user/queue/inbox` | Receive broker-resolved personal queue | Authenticated + appropriate permission |
| `SUBSCRIBE` | `/queue/inbox-user-x` | Attempt to access raw broker destination | **DENY** |
| `SEND` (MESSAGE) | `/app/admin/execute` | Admin application command | Authority `ADMIN_SEND` |

`/app`, `/topic`, `/queue`, and `/user` are **common configuration conventions** of the Spring STOMP broker, not strings automatically secured by the framework for every application. Check the exact prefixes declared in your `MessageBrokerRegistry`.

## 3. Signatures and Types in Spring Security 6.5

Key classes and interfaces:

```java
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.messaging.access.intercept
    .MessageMatcherDelegatingAuthorizationManager;
import org.springframework.messaging.Message;

// Actual return type of Builder.build():
AuthorizationManager<Message<?>> manager =
    MessageMatcherDelegatingAuthorizationManager.builder()
        .anyMessage().denyAll()
        .build();
```

**Note:** in the code block above, Java does not allow line breaks inside an import statement the way it is wrapped for presentation. The standard import, **used in the runnable project below**, must be written on a single line:

```java
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;
```

Later examples use `AuthorizationManager.authorize(Supplier<Authentication>, Message<?>)`, returning an `AuthorizationResult` with `isGranted()`. `check(...)` still exists in Spring Security 6.5 but is **deprecated**, so new code should not rely on it when `authorize(...)` can be used.

### 3.1. How the Manager Evaluates Each Message

Logically:

```text
for each configured rule in declaration order:
    if rule.matcher.matches(message):
        return rule.authorizationManager.authorize(authentication, messageContext)
return null  // no matcher matched
```

This is **pseudocode**, not an excerpt from the actual source. The critical point is **first matching rule wins**. If a rule matches and its delegate returns DENY, the manager **does not automatically move on to the next rule** looking for ALLOW. If nothing matches and there is no catch-all, `AuthorizationResult` may be `null` (no decision), which is dangerous if an integration layer misinterprets abstention. Therefore, always put `anyMessage().denyAll()` at the end.

### 3.2. Builder Matchers to Know

| Builder | What Does It Match? | When to Use |
| --- | --- | --- |
| `nullDestMatcher()` | Messages without `simpDestination` (typically CONNECT, UNSUBSCRIBE, DISCONNECT, HEARTBEAT...) | Rules for control frames with no destination |
| `simpDestMatchers("/app/**")` | Destination pattern, **no message-type restriction** | Use with caution; both SEND/MESSAGE and SUBSCRIBE can match |
| `simpMessageDestMatchers("/app/**")` | `SimpMessageType.MESSAGE` + destination | Authorizing client SEND to the application |
| `simpSubscribeDestMatchers("/topic/**")` | `SimpMessageType.SUBSCRIBE` + destination | Authorizing client subscriptions |
| `simpTypeMatchers(MESSAGE, SUBSCRIBE)` | Message type regardless of destination | Fallback for data frames with a destination |
| `anyMessage()` | Every message | **Final rule**, normally DENY |
| `matchers(customMatchers...)` | Custom matcher implementation | Routes with complex conditions |
| `hasRole("USER")` | Authority `ROLE_USER` | Role name without prefix when calling |
| `hasAuthority("TOPIC_READ")` | Exact authority `TOPIC_READ` | Exact application permission |
| `authenticated()` | Principal authenticated per trust resolver | Handshake/session/message control |
| `permitAll()` / `denyAll()` | Unconditionally allow or deny | Open only messages that are **truly** intended to be allowed |

**Note:** `simpDestMatchers` does not check `SimpMessageType`; if you write `simpDestMatchers("/topic/**").permitAll()` just intending to allow SUBSCRIBE, you can accidentally allow clients to **MESSAGE/SEND to the broker prefix**.

## 4. Ordering Matters More Than Pattern Specificity

This is the central pitfall of this lesson.

### 4.1. Insecure Configuration: Broad Match First

```java
// COUNTEREXAMPLE — never use as a production configuration.
return MessageMatcherDelegatingAuthorizationManager.builder()
    .simpDestMatchers("/topic/**").permitAll()
    .simpSubscribeDestMatchers("/topic/private/**")
        .hasAuthority("TOPIC_PRIVATE")
    .simpMessageDestMatchers("/topic/**").denyAll()
    .anyMessage().denyAll()
    .build();
```

For `SUBSCRIBE /topic/private/finance`, the first rule `/topic/**` already matches and returns ALLOW. `TOPIC_PRIVATE` **is never checked**.

For `MESSAGE /topic/public/news`, the exact same first rule matches and returns ALLOW. The rule below that denies messages to the broker prefix **is never evaluated**. One misplaced `permitAll()` opened two unintended paths.

### 4.2. Safe Configuration: Type-Specific, Narrow Before Broad, Deny Last

```java
MessageMatcherDelegatingAuthorizationManager.Builder m =
    MessageMatcherDelegatingAuthorizationManager.builder();

m.nullDestMatcher().authenticated();

m.simpMessageDestMatchers("/topic/**", "/queue/**").denyAll();

m.simpSubscribeDestMatchers("/topic/private/**")
    .hasAuthority("TOPIC_PRIVATE");

m.simpSubscribeDestMatchers("/topic/public/admin/**")
    .hasAuthority("TOPIC_ADMIN");

m.simpSubscribeDestMatchers("/topic/public/**")
    .hasAuthority("TOPIC_READ");

m.simpSubscribeDestMatchers("/user/queue/**")
    .hasAuthority("USER_QUEUE");

m.simpMessageDestMatchers("/app/admin/**")
    .hasAuthority("ADMIN_SEND");

m.simpMessageDestMatchers("/app/chat/**")
    .hasAuthority("CHAT_SEND");

m.simpTypeMatchers(SimpMessageType.MESSAGE, SimpMessageType.SUBSCRIBE)
    .denyAll();
m.anyMessage().denyAll();

return m.build();
```

This is a **fragment inside a factory method**, provided in full with imports and tests in Section 8. The configuration above illustrates a policy for a chat application, not a mandatory list of default prefixes.

Put `/topic/public/admin/**` **before** `/topic/public/**`: both can match an admin SUBSCRIBE; the first rule requires `TOPIC_ADMIN`, so an actor holding only `TOPIC_READ` is blocked. For `/topic/private/**` and `/topic/public/**`, the patterns do not overlap in the example; keeping them distinct still helps auditing.

### 4.3. No Need to "Stack" Deny with Allow

You can read the configuration as a priority table:

| Order | Matcher | Decision |
| ---: | --- | --- |
| 1 | No destination | Authenticated |
| 2 | MESSAGE to `/topic/**`, `/queue/**` | DenyAll |
| 3 | SUBSCRIBE `/topic/private/**` | TOPIC_PRIVATE |
| 4 | SUBSCRIBE `/topic/public/admin/**` | TOPIC_ADMIN |
| 5 | SUBSCRIBE `/topic/public/**` | TOPIC_READ |
| 6 | SUBSCRIBE `/user/queue/**` | USER_QUEUE |
| 7 | MESSAGE `/app/admin/**` | ADMIN_SEND |
| 8 | MESSAGE `/app/chat/**` | CHAT_SEND |
| 9 | Remaining MESSAGE or SUBSCRIBE | DenyAll |
| 10 | Any remaining message type | DenyAll |

A `MESSAGE /topic/public/news` stops at **row 2**. A `SUBSCRIBE /topic/public/admin/alerts` skips row 2 because it is not MESSAGE and stops at **row 4**. A `SUBSCRIBE /app/chat/send` does not match row 7 because it is not MESSAGE; it is blocked at **row 9**.

Configuring `simpTypeMatchers(MESSAGE,SUBSCRIBE).denyAll()` overlaps somewhat with `anyMessage().denyAll()`, but is useful to express **default denial of MESSAGE/SUBSCRIBE frames without an explicit rule**. In a real app you may keep both for clarity or use only `anyMessage().denyAll()` if thoroughly tested.

### 4.4. Putting `anyMessage().permitAll()` First Is a Critical Bug

```java
// COUNTEREXAMPLE: every matcher after this is shadowed.
MessageMatcherDelegatingAuthorizationManager.builder()
    .anyMessage().permitAll()
    .simpMessageDestMatchers("/topic/**").denyAll()
    .build();
```

A catch-all permit first renders every subsequent deny rule dead. **Do not assume the builder reorders rules from specific to general.** Tests demonstrating dangerous configurations exist to reproduce bugs, not as deployment recommendations.

## 5. Distinguishing Inbound SEND from Outbound Delivery

A client's STOMP `SEND` frame typically becomes a `SimpMessageType.MESSAGE` on `clientInboundChannel`. Clients are commonly permitted to SEND to `/app/**`, which the application destination prefix routes to `@MessageMapping`.

On the other hand:

```text
Server -> convertAndSend("/topic/public/news", payload)
                |
                v
          Broker outbound delivery
                |
                v
Clients subscribed to "/topic/public/news"
```

Clients wishing to **receive** from a topic must SUBSCRIBE; clients **should not SEND directly** to broker destinations so they cannot spoof system notifications. Therefore:

```java
.simpMessageDestMatchers("/topic/**", "/queue/**").denyAll()
.simpSubscribeDestMatchers("/topic/public/**")
    .hasAuthority("TOPIC_READ")
```

The two matchers **do not conflict**: one applies to MESSAGE and the other applies to SUBSCRIBE.

### 5.1. User Destinations

Spring STOMP supports forms like `/user/queue/notifications`: when a client subscribes, `UserDestinationMessageHandler` can translate it to a session/user-specific broker destination. That does not mean you should open `SUBSCRIBE /queue/**`: a raw broker destination could allow subscribing to a queue meant for another user.

Suggested policy:

```java
.simpSubscribeDestMatchers("/user/queue/**")
    .hasAuthority("USER_QUEUE")
.simpSubscribeDestMatchers("/queue/**").denyAll()
```

The second deny `/queue/**` rule is optional if you already have a deny fallback and no broader rule allowing it; it states the protective intent clearly. In multi-tenant systems, identity/session mapping must also handle non-unique usernames properly; do not assume `/user` is automatically safe for every tenant, every broker relay, or custom `Principal.getName()` values.

### 5.2. `@MessageMapping` Does Not Automatically Verify Object Permissions

Example:

```java
@MessageMapping("/rooms/{roomId}/post")
public void post(@DestinationVariable long roomId,
                 ChatPayload payload, Principal principal) {
    // Must verify principal has access to roomId/tenant.
}
```

This is a **fragment**; `ChatPayload`, imports, broker config, and service policies must be defined. A `CHAT_SEND` gate grants only the functional permission to send chat messages, not permission to write to every room. Check membership/owner/tenant, quota, and room state in the service/repository.

## 6. Configuring Spring Security Messaging with `@EnableWebSocketSecurity`

In Spring Security 6.5, Java configuration typically declares an `AuthorizationManager<Message<?>>` bean:

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
public class WebSocketAuthorizationConfiguration {
    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {
        messages
            .nullDestMatcher().authenticated()
            .simpMessageDestMatchers("/topic/**", "/queue/**").denyAll()
            .simpSubscribeDestMatchers("/topic/private/**")
                .hasAuthority("TOPIC_PRIVATE")
            .simpSubscribeDestMatchers("/topic/public/admin/**")
                .hasAuthority("TOPIC_ADMIN")
            .simpSubscribeDestMatchers("/topic/public/**")
                .hasAuthority("TOPIC_READ")
            .simpSubscribeDestMatchers("/user/queue/**")
                .hasAuthority("USER_QUEUE")
            .simpMessageDestMatchers("/app/admin/**")
                .hasAuthority("ADMIN_SEND")
            .simpMessageDestMatchers("/app/chat/**")
                .hasAuthority("CHAT_SEND")
            .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
```

This is a **Java configuration class with imports**, yet it still requires a Spring application with Spring Messaging/WebSocket broker setup, HTTP authentication, and a registered WebSocket endpoint. Do not treat the bean configuration alone as a complete WebSocket server.

**Version note:** Java WebSocket message authorization switched to `AuthorizationManager` in Spring Security 5.8. Legacy projects using `AbstractSecurityWebSocketMessageBrokerConfigurer`, `MessageSecurityMetadataSourceRegistry`, or SpEL messaging expressions should be migrated with comparative tests, without mixing both mechanisms without clear ordering/interceptor understanding.

### 6.1. Handshake, STOMP CONNECT, and CSRF

Spring Security WebSocket Messaging obtains the principal from the **HTTP handshake** (usually the HTTP session's authentication). With `@EnableWebSocketSecurity`, a **valid CSRF token in inbound STOMP CONNECT** is required by default to strengthen Same-Origin protection; this **is not tested by the manager unit tests** in Section 8.

`nullDestMatcher().authenticated()` in the manager only evaluates authentication for messages without a destination. It **does not replace the STOMP CONNECT CSRF check**, Origin validation, session authentication, network/TLS, or the HTTP handshake endpoint policy.

A request/connection can be rejected **before the message authorization manager is ever called**. When debugging, distinguish:
- HTTP WebSocket handshake status `401/403`, Origin/CORS.
- STOMP CONNECT rejected due to missing/invalid CSRF token.
- `SEND` or `SUBSCRIBE` rejected by message authorization.
- Broker relay refusing subscribe/route, closed session, or nonexistent destination.

**Do not disable CSRF/Same-Origin just to simplify tests.** If cross-origin clients or SockJS must be supported, establish a concrete threat model, Origin allowlist, token validation, and integration tests.

### 6.2. STOMP CONNECT Headers Are Not Identity by Themselves

A client can send native STOMP headers such as `login`, `passcode`, `X-Tenant`, or `X-User`. Do not trust them as authenticated identity unless a trusted authentication interceptor verifies them and builds a valid `Principal`. If using JWT Bearer in STOMP CONNECT, perform authentication in the proper place and protect keys/sessions/expiry.

### 6.3. Not a Replacement for Domain-Level Authorization

A custom matcher can inspect the destination `/app/rooms/42/post`, yet checking room membership in the DB, ownership, and tenant permissions must still occur in the service. For sensitive topics, **SUBSCRIBE** may need a custom `.access(AuthorizationManager<MessageAuthorizationContext<?>>)` evaluating route variables and the authenticated principal, rather than only global `hasAuthority("TOPIC_PRIVATE")`.

The ordering rule still holds: a specific custom matcher must appear **before** a broad `simpSubscribeDestMatchers("/topic/**")` or `anyMessage()`; otherwise, the custom delegate will never be called.

## 7. Test Design: Must Reproduce Ordering Bugs, Not Just Normal Allow Cases

Minimum test case table:

| Message | Actor authorities | Expected | First Rule That Should Match |
| --- | --- | --- | --- |
| CONNECT, null dest | Authenticated | ALLOW | `nullDestMatcher` |
| CONNECT, null dest | Anonymous | DENY | `nullDestMatcher` |
| SUBSCRIBE `/topic/public/news` | TOPIC_READ | ALLOW | Public subscribe |
| SUBSCRIBE `/topic/public/admin/alerts` | Only TOPIC_READ | DENY | **Admin subscribe before broad public** |
| SUBSCRIBE `/topic/public/admin/alerts` | TOPIC_ADMIN | ALLOW | Admin subscribe |
| SUBSCRIBE `/topic/private/finance` | Only TOPIC_READ | DENY | Private subscribe |
| SUBSCRIBE `/topic/private/finance` | TOPIC_PRIVATE | ALLOW | Private subscribe |
| MESSAGE `/topic/public/news` | CHAT_SEND or TOPIC_READ | DENY | Broker send deny |
| MESSAGE `/queue/internal` | ADMIN_SEND | DENY | Broker send deny |
| MESSAGE `/app/chat/send` | CHAT_SEND | ALLOW | App chat send |
| SUBSCRIBE `/app/chat/send` | CHAT_SEND | DENY | MESSAGE-only rule does not match |
| MESSAGE `/app/admin/run` | ADMIN_SEND | ALLOW | Admin send |
| MESSAGE `/app/admin/run` | CHAT_SEND | DENY | Admin send |
| SUBSCRIBE `/user/queue/inbox` | USER_QUEUE | ALLOW | User queue subscribe |
| SUBSCRIBE `/queue/raw` | USER_QUEUE | DENY | Fallback |
| MESSAGE `/app/unmapped` | CHAT_SEND | DENY | Fallback |
| SUBSCRIBE `/topic/unmapped` | TOPIC_READ | DENY | Fallback |
| Misconfigured `simpDestMatchers("/topic/**").permitAll()` first | No authority | **Wrong ALLOW** | Broad permit swallows specific rule |
| Misconfigured `anyMessage().permitAll()` first | No authority | **Wrong ALLOW** | Catch-all permit swallows deny |
| Misconfigured without `anyMessage` | Unmatched message | `null`/abstain can occur | Missing final rule |

**Do not assert only success cases.** A leaky configuration often still passes 100% of positive tests. Testing **broker prefix SEND**, **narrow rules after broad rules**, **SUBSCRIBE where only SEND is allowed**, and **catch-all** are the highest-value cases.

## 8. Standalone Java 17+ Project Testing the Real Manager

This test suite builds `MessageMatcherDelegatingAuthorizationManager` using the 6.5 Builder API, constructs `Message<byte[]>` with `SimpMessageHeaderAccessor.create(type)`, and calls `AuthorizationManager.authorize(...)`. It does not mock decisions with a custom boolean policy. **No WebSocket server startup is needed**, because we are unit-testing matcher/order logic; proving real interceptor wiring and STOMP CONNECT CSRF requires separate integration tests.

### 8.1. Structure and Gradle

```text
messaging-rule-order/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/MessageRuleOrderTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'messaging-rule-order'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.0'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-messaging'
    testImplementation 'org.springframework:spring-messaging'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

`spring-security-messaging` provides `MessageMatcherDelegatingAuthorizationManager`; `spring-messaging` provides `SimpMessageHeaderAccessor`, `Message`, and `MessageBuilder`; `spring-boot-starter-test` provides JUnit 5 and AssertJ. Because the source lives solely under `src/test/java`, dependencies use `testImplementation`.

### 8.2. Full Java Test Code

Create `src/test/java/demo/MessageRuleOrderTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.support.MessageBuilder;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.messaging.simp.SimpMessageType.CONNECT;
import static org.springframework.messaging.simp.SimpMessageType.DISCONNECT;
import static org.springframework.messaging.simp.SimpMessageType.HEARTBEAT;
import static org.springframework.messaging.simp.SimpMessageType.MESSAGE;
import static org.springframework.messaging.simp.SimpMessageType.SUBSCRIBE;
import static org.springframework.messaging.simp.SimpMessageType.UNSUBSCRIBE;

class MessageRuleOrderTest {

    private static Message<?> msg(
            SimpMessageType type, String destination) {
        SimpMessageHeaderAccessor headers =
            SimpMessageHeaderAccessor.create(type);

        if (destination != null) {
            headers.setDestination(destination);
        }

        return MessageBuilder.createMessage(
            new byte[0], headers.getMessageHeaders());
    }

    private static Authentication user(String... authorities) {
        return new UsernamePasswordAuthenticationToken(
            "alice", "test-only",
            AuthorityUtils.createAuthorityList(authorities));
    }

    private static Authentication anonymous() {
        return new AnonymousAuthenticationToken(
            "test-key", "anonymousUser",
            AuthorityUtils.createAuthorityList(
                "ROLE_ANONYMOUS"));
    }

    private static AuthorizationManager<Message<?>> safePolicy() {
        MessageMatcherDelegatingAuthorizationManager.Builder m =
            MessageMatcherDelegatingAuthorizationManager.builder();

        m.nullDestMatcher().authenticated();

        // Clients must never spoof broker publications.
        m.simpMessageDestMatchers(
            "/topic/**", "/queue/**").denyAll();

        // SUBSCRIBE: narrow before broad when same type and overlapping.
        m.simpSubscribeDestMatchers("/topic/private/**")
            .hasAuthority("TOPIC_PRIVATE");

        m.simpSubscribeDestMatchers("/topic/public/admin/**")
            .hasAuthority("TOPIC_ADMIN");

        m.simpSubscribeDestMatchers("/topic/public/**")
            .hasAuthority("TOPIC_READ");

        m.simpSubscribeDestMatchers("/user/queue/**")
            .hasAuthority("USER_QUEUE");

        // SEND/MESSAGE: only to declared application destinations.
        m.simpMessageDestMatchers("/app/admin/**")
            .hasAuthority("ADMIN_SEND");

        m.simpMessageDestMatchers("/app/chat/**")
            .hasAuthority("CHAT_SEND");

        // All other MESSAGE/SUBSCRIBE frames are denied.
        m.simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll();
        m.anyMessage().denyAll();

        return m.build();
    }

    private static boolean allowed(
            AuthorizationManager<Message<?>> manager,
            Authentication authentication,
            SimpMessageType type, String destination) {

        AuthorizationResult decision =
            manager.authorize(
                () -> authentication, msg(type, destination));

        // Null means no-decision/abstain; NEVER treat as ALLOW.
        return decision != null && decision.isGranted();
    }

    @Test
    void authenticatedConnectIsAllowedByNullDestinationRule() {
        assertThat(allowed(
            safePolicy(), user(), CONNECT, null)).isTrue();
    }

    @Test
    void anonymousConnectIsDeniedByNullDestinationRule() {
        assertThat(allowed(
            safePolicy(), anonymous(), CONNECT, null)).isFalse();
    }

    @Test
    void authenticatedHeartbeatMatchesNullDestinationRule() {
        assertThat(allowed(
            safePolicy(), user(), HEARTBEAT, null)).isTrue();
    }

    @Test
    void authenticatedDisconnectMatchesNullDestinationRule() {
        assertThat(allowed(
            safePolicy(), user(), DISCONNECT, null)).isTrue();
    }

    @Test
    void anonymousUnsubscribeIsDenied() {
        assertThat(allowed(
            safePolicy(), anonymous(), UNSUBSCRIBE, null)).isFalse();
    }

    @Test
    void privateSubscribeRequiresPrivateAuthority() {
        assertThat(allowed(
            safePolicy(), user("TOPIC_PRIVATE"),
            SUBSCRIBE, "/topic/private/finance")).isTrue();
    }

    @Test
    void privateSubscribeIsDeniedWithOnlyPublicAuthority() {
        assertThat(allowed(
            safePolicy(), user("TOPIC_READ"),
            SUBSCRIBE, "/topic/private/finance")).isFalse();
    }

    @Test
    void privateSubscribeIsDeniedWithSendAuthority() {
        assertThat(allowed(
            safePolicy(), user("CHAT_SEND"),
            SUBSCRIBE, "/topic/private/finance")).isFalse();
    }

    @Test
    void regularPublicSubscribeAllowsTopicRead() {
        assertThat(allowed(
            safePolicy(), user("TOPIC_READ"),
            SUBSCRIBE, "/topic/public/news")).isTrue();
    }

    @Test
    void publicSubscribeWithoutTopicReadIsDenied() {
        assertThat(allowed(
            safePolicy(), user("CHAT_SEND"),
            SUBSCRIBE, "/topic/public/news")).isFalse();
    }

    @Test
    void adminSubtopicRequiresSpecificAuthorityBeforeBroadRule() {
        assertThat(allowed(
            safePolicy(), user("TOPIC_READ"),
            SUBSCRIBE, "/topic/public/admin/alerts")).isFalse();
    }

    @Test
    void adminSubtopicAllowsTopicAdminAuthority() {
        assertThat(allowed(
            safePolicy(), user("TOPIC_ADMIN"),
            SUBSCRIBE, "/topic/public/admin/alerts")).isTrue();
    }

    @Test
    void adminAuthorityDoesNotImplicitlyGrantPublicRead() {
        assertThat(allowed(
            safePolicy(), user("TOPIC_ADMIN"),
            SUBSCRIBE, "/topic/public/news")).isFalse();
    }

    @Test
    void userQueueSubscriptionRequiresUserQueueAuthority() {
        assertThat(allowed(
            safePolicy(), user("USER_QUEUE"),
            SUBSCRIBE, "/user/queue/inbox")).isTrue();
    }

    @Test
    void userQueueSubscriptionWithoutAuthorityIsDenied() {
        assertThat(allowed(
            safePolicy(), user("TOPIC_READ"),
            SUBSCRIBE, "/user/queue/inbox")).isFalse();
    }

    @Test
    void rawBrokerQueueCannotBeSubscribedTo() {
        assertThat(allowed(
            safePolicy(), user("USER_QUEUE"),
            SUBSCRIBE, "/queue/inbox-user-x")).isFalse();
    }

    @Test
    void topicSendIsDeniedEvenForChatSender() {
        assertThat(allowed(
            safePolicy(), user("CHAT_SEND"),
            MESSAGE, "/topic/public/news")).isFalse();
    }

    @Test
    void topicSendIsDeniedEvenForTopicAdmin() {
        assertThat(allowed(
            safePolicy(), user("TOPIC_ADMIN"),
            MESSAGE, "/topic/public/admin/alerts")).isFalse();
    }

    @Test
    void queueSendIsDeniedEvenForAdminSender() {
        assertThat(allowed(
            safePolicy(), user("ADMIN_SEND"),
            MESSAGE, "/queue/raw")).isFalse();
    }

    @Test
    void appChatSendRequiresChatAuthority() {
        assertThat(allowed(
            safePolicy(), user("CHAT_SEND"),
            MESSAGE, "/app/chat/send")).isTrue();
    }

    @Test
    void appChatSendIsNotGrantedByTopicRead() {
        assertThat(allowed(
            safePolicy(), user("TOPIC_READ"),
            MESSAGE, "/app/chat/send")).isFalse();
    }

    @Test
    void appAdminSendAllowsOnlyAdminAuthority() {
        assertThat(allowed(
            safePolicy(), user("ADMIN_SEND"),
            MESSAGE, "/app/admin/execute")).isTrue();
    }

    @Test
    void chatSenderCannotSendToAdminApplicationDestination() {
        assertThat(allowed(
            safePolicy(), user("CHAT_SEND"),
            MESSAGE, "/app/admin/execute")).isFalse();
    }

    @Test
    void cannotSubscribeToApplicationSendDestination() {
        assertThat(allowed(
            safePolicy(), user("CHAT_SEND"),
            SUBSCRIBE, "/app/chat/send")).isFalse();
    }

    @Test
    void cannotSubscribeToApplicationAdminDestination() {
        assertThat(allowed(
            safePolicy(), user("ADMIN_SEND"),
            SUBSCRIBE, "/app/admin/execute")).isFalse();
    }

    @Test
    void unmatchedApplicationSendIsDeniedByFallback() {
        assertThat(allowed(
            safePolicy(), user("CHAT_SEND"),
            MESSAGE, "/app/unmapped/operation")).isFalse();
    }

    @Test
    void unmatchedTopicSubscriptionIsDeniedByFallback() {
        assertThat(allowed(
            safePolicy(), user("TOPIC_READ"),
            SUBSCRIBE, "/topic/unlisted/messages")).isFalse();
    }

    @Test
    void broadDestinationPermitBeforePrivateRuleIsAnUnsafeBypass() {
        // ONLY illustrates ordering bug; DO NOT use in production.
        AuthorizationManager<Message<?>> insecure =
            MessageMatcherDelegatingAuthorizationManager.builder()
                .simpDestMatchers("/topic/**").permitAll()
                .simpSubscribeDestMatchers("/topic/private/**")
                    .hasAuthority("TOPIC_PRIVATE")
                .simpMessageDestMatchers("/topic/**").denyAll()
                .anyMessage().denyAll()
                .build();

        // This ALLOW is a SECURITY-INCORRECT RESULT.
        assertThat(allowed(
            insecure, user(),
            SUBSCRIBE, "/topic/private/finance")).isTrue();
    }

    @Test
    void broadDestinationPermitAlsoAllowsForgedTopicSend() {
        AuthorizationManager<Message<?>> insecure =
            MessageMatcherDelegatingAuthorizationManager.builder()
                .simpDestMatchers("/topic/**").permitAll()
                .simpMessageDestMatchers("/topic/**").denyAll()
                .anyMessage().denyAll()
                .build();

        // A broad SUBSCRIBE permission exposed SEND as well.
        assertThat(allowed(
            insecure, user(),
            MESSAGE, "/topic/public/news")).isTrue();
    }

    @Test
    void catchAllPermitBeforeDenyAlsoBypassesDeny() {
        AuthorizationManager<Message<?>> insecure =
            MessageMatcherDelegatingAuthorizationManager.builder()
                .anyMessage().permitAll()
                .simpMessageDestMatchers("/topic/**").denyAll()
                .build();

        assertThat(allowed(
            insecure, user(), MESSAGE, "/topic/system")).isTrue();
    }

    @Test
    void broadSubscribeBeforeNarrowAdminRuleIsAnUnsafeBypass() {
        AuthorizationManager<Message<?>> insecure =
            MessageMatcherDelegatingAuthorizationManager.builder()
                .simpSubscribeDestMatchers("/topic/public/**")
                    .hasAuthority("TOPIC_READ")
                .simpSubscribeDestMatchers("/topic/public/admin/**")
                    .hasAuthority("TOPIC_ADMIN")
                .anyMessage().denyAll()
                .build();

        // TOPIC_READ is accepted on the subtopic meant for TOPIC_ADMIN.
        assertThat(allowed(
            insecure, user("TOPIC_READ"),
            SUBSCRIBE, "/topic/public/admin/alerts")).isTrue();
    }

    @Test
    void simpDestMatchersIsNotRestrictedToSendOrSubscribe() {
        AuthorizationManager<Message<?>> typeAgnostic =
            MessageMatcherDelegatingAuthorizationManager.builder()
                .simpDestMatchers("/app/**")
                    .hasAuthority("CHAT_SEND")
                .anyMessage().denyAll()
                .build();

        // The same pattern grants both MESSAGE and SUBSCRIBE.
        assertThat(allowed(
            typeAgnostic, user("CHAT_SEND"),
            MESSAGE, "/app/chat/send")).isTrue();

        assertThat(allowed(
            typeAgnostic, user("CHAT_SEND"),
            SUBSCRIBE, "/app/chat/send")).isTrue();
    }

    @Test
    void hasRoleAddsRolePrefixButHasAuthorityDoesNot() {
        AuthorizationManager<Message<?>> rolePolicy =
            MessageMatcherDelegatingAuthorizationManager.builder()
                .simpSubscribeDestMatchers("/topic/moderators")
                    .hasRole("MODERATOR")
                .anyMessage().denyAll()
                .build();

        assertThat(allowed(
            rolePolicy, user("ROLE_MODERATOR"),
            SUBSCRIBE, "/topic/moderators")).isTrue();

        assertThat(allowed(
            rolePolicy, user("MODERATOR"),
            SUBSCRIBE, "/topic/moderators")).isFalse();
    }

    @Test
    void missingCatchAllReturnsNoDecisionForUnmatchedMessage() {
        AuthorizationManager<Message<?>> incomplete =
            MessageMatcherDelegatingAuthorizationManager.builder()
                .simpSubscribeDestMatchers("/topic/public/**")
                    .hasAuthority("TOPIC_READ")
                .build();

        AuthorizationResult decision = incomplete.authorize(
            () -> user("TOPIC_READ"),
            msg(MESSAGE, "/app/unknown"));

        assertThat(decision).isNull();
    }
}
```

### 8.3. Why Does This Example Properly Test Rule Order?

The test suite constructs **real messages** with `simpMessageType` and `simpDestination` in headers, calling the real manager implementation directly rather than a fake `boolean`. The `allowed(...)` method reads `AuthorizationResult` from `authorize`; any `null` result is treated as **not proven ALLOW**.

The tests intentionally build **insecure managers** scoped to individual test methods to demonstrate *how vulnerabilities can arise*. They are never registered as beans protecting an application. A test asserting ALLOW on a misconfigured manager is **proof of a bug**, not validation of a safe policy.

Test count: **33 JUnit 5 `@Test` methods** (per the illustrative source). Run Gradle to verify compilation and behavior on actual dependency versions; **do not treat the expectations below as an executed run log**.

### 8.4. Running the Tests

```bash
gradle test --tests demo.MessageRuleOrderTest
```

If the project already includes the Gradle Wrapper:

```bash
# Linux/macOS
./gradlew test --tests demo.MessageRuleOrderTest

# Windows PowerShell/cmd
gradlew.bat test --tests demo.MessageRuleOrderTest
```

**Expected outcome:** JUnit tests pass and Gradle reports `BUILD SUCCESSFUL` given compatible JDK 17+, Gradle, and downloaded dependencies. The misconfiguration tests are designed to PASS when **confirming that the manager mistakenly permits access**, so do not take `BUILD SUCCESSFUL` as proof that insecure configurations are safe. HTML report: `build/reports/tests/test/index.html`.

### 8.5. Reading the Tests Across 3 Layers

- **Matcher layer:** does the message have the right type and destination? `simpDestMatchers` does not restrict type, while `simpSubscribeDestMatchers` and `simpMessageDestMatchers` do.
- **Precedence layer:** which matcher comes first among those that match? Does the narrow `/topic/public/admin/**` rule precede `/topic/public/**`?
- **Grant layer:** what do `hasAuthority`, `hasRole`, `authenticated`, `permitAll`, and `denyAll` return? With fallback, every message not explicitly permitted must be DENIED.

This test suite **does not** test `@EnableWebSocketSecurity` wiring, session principal propagation, STOMP CONNECT CSRF, broker relay auth, SockJS, `@MessageMapping` execution, or outbound delivery. Integration tests using a STOMP/WebSocket test client are needed to verify those layers.

## 9. Integration Testing Before Production

Beyond manager unit tests, run a real Spring Boot/WebSocket application with authentication and broker configured.

### 9.1. Testing STOMP CONNECT

Create cases for:

1. HTTP handshake without valid authentication: rejected at the HTTP layer per policy.
2. HTTP authentication present, but STOMP CONNECT lacks CSRF: blocked when default `@EnableWebSocketSecurity` CSRF is enabled.
3. STOMP CONNECT with valid CSRF and authenticated principal: creates session per policy.
4. CONNECT with native `X-User` impersonating someone else: does not replace the server-authenticated Principal.
5. An already connected client cannot grant itself `TOPIC_ADMIN` via STOMP headers.
6. SockJS/cross-origin clients must follow configured Origin/CSRF/trust requirements, not open indiscriminately.

### 9.2. Testing SEND, SUBSCRIBE, and the Broker

After a successful CONNECT:

- A user with `CHAT_SEND` sends `SEND /app/chat/send`: routed to the matching `@MessageMapping`.
- A user with only `TOPIC_READ` sends `SEND /app/chat/send`: blocked.
- A user with `TOPIC_READ` subscribes to `/topic/public/news`: receives **server-emitted** notifications.
- A user sends `SEND /topic/public/news`: blocked right on inbound; other subscribers receive no forged content.
- A user with `TOPIC_READ` subscribes to `/topic/public/admin/alerts`: blocked by **narrow-before-broad precedence**.
- A user with `TOPIC_ADMIN` subscribes to the admin subtopic: allowed per policy and broker setup.
- A user attempts to subscribe directly to `/queue/**` or `/user/<other>/queue/**`: blocked by matchers and user-destination mapping.
- Unmatched destinations and types are blocked by `anyMessage().denyAll()`.
- When permissions/memberships change during a long session, a recheck/re-subscribe/revocation policy must apply per SLA; a prior SUBSCRIBE ALLOW does not turn into a permanent grant.

### 9.3. Testing Tenant and Object-Level Permissions

If the app has `/topic/tenants/{tenantId}/rooms/{roomId}`, verify the authenticated actor's tenant membership and room permissions **at SUBSCRIBE time**; backend publishing must filter by tenant and avoid emitting data to overly broad shared destinations. Two tenants can share room ID=42; never cache decisions keyed solely by ID 42.

A JWT with `SCOPE_chat:read` is a functional permission, yet **does not prove permission to view every tenant/room**. Separate policy in the message manager (which path may be subscribed/sent to) from the domain service (which data may be published).

## 10. Troubleshooting: Right Matchers, Still Wrong Permissions

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| User without `TOPIC_PRIVATE` still subscribes to private | Broad `/topic/**` permitAll matcher appears earlier | Check rule order; narrow before broad |
| User sends SEND to a topic | Used `simpDestMatchers` instead of `simpSubscribeDestMatchers` | Block `simpMessageDestMatchers("/topic/**")` |
| A deny rule never takes effect | `anyMessage().permitAll()` or broad allow appears earlier | Read top to bottom, test first-match |
| User with the right authority is still denied | A broad deny rule appears before the intended allow | Check message type and order |
| Subscribing to `/app/**` is unexpectedly allowed | `simpDestMatchers("/app/**")` matches SUBSCRIBE too | Use `simpMessageDestMatchers` |
| `ROLE_USER` does not match | Confusing `hasRole` and `hasAuthority` prefixes | `hasRole("USER")` adds `ROLE_` automatically |
| MESSAGE `/topic` is accepted despite fallback deny | Another broad rule matched before fallback | Build a real MESSAGE test with the same destination |
| No rule matches, yet app behaves strangely | Manager returns `null`/abstain | Always include `anyMessage().denyAll()` |
| CONNECT is blocked despite `nullDestMatcher().authenticated()` | STOMP CONNECT CSRF, handshake/Origin, or invalid principal | Inspect the actual filter/interceptor |
| Token exists, yet Principal is absent on messages | Handshake auth and messaging context mismatch | Check authentication bridge and interceptor order |
| SUBSCRIBE `/user` allowed, yet receives wrong data | Custom user destination resolution, username collision, or wrong-tenant publish | Check Principal, session ID, destination mapping |
| Broker relay accepts unauthorized messages | Broker/relay authorization differs from inbound app policy | Test end-to-end directly; broker ACLs |
| All SUBSCRIBEs denied after migration | Legacy SpEL rules not translated properly to AuthorizationManager | Test migration by destination/type |
| Private publish still leaks sensitive data | Only a message gate exists, lacking domain policy | Check room membership, tenant, payload projection |
| Inconsistent across multiple instances | Session stickiness, broker relay, cache, or rule deployment mismatch | Test multi-node, policy versions, message paths |
| HTTP 403 even though manager allows | Handshake/CSRF/CORS/other authentication | Distinguish security layers |

## 11. Checklist When Reviewing Rule Ordering

- [ ] An `AuthorizationManager<Message<?>>` bean and `@EnableWebSocketSecurity` are present for the Spring Security version in use.
- [ ] `MessageMatcherDelegatingAuthorizationManager.Builder`, type-specific matchers, and `hasAuthority/hasRole` syntax are used properly.
- [ ] Whenever two patterns overlap, the **specific rule precedes the broad rule**.
- [ ] No `anyMessage().permitAll()` or `simpDestMatchers("/**").permitAll()` appears at the top of the list.
- [ ] MESSAGE to broker prefixes `/topic/**`, `/queue/**` is denied.
- [ ] SUBSCRIBE to private/admin topics has dedicated permissions; cannot inherit public authority accidentally.
- [ ] SEND to application endpoints is granted `CHAT_SEND`/`ADMIN_SEND` per destination; SUBSCRIBE to `/app/**` does not inherit SEND grants.
- [ ] `nullDestMatcher()` and control frames are evaluated alongside CONNECT CSRF/handshake security.
- [ ] Unmatched destinations and unexpected message types hit `anyMessage().denyAll()` at the end.
- [ ] `/user/queue/**` uses safe per-user semantics; raw `/queue/**` broker destinations are not opened.
- [ ] Both **MESSAGE** and **SUBSCRIBE** are tested for the same destination, not just the destination string.
- [ ] Broad-first insecure orderings are tested to catch shadowed rules before production.
- [ ] Token/session/tenant context and object permissions are checked in services, not just matchers.
- [ ] End-to-end STOMP handshake, CONNECT CSRF, SUBSCRIBE, SEND, and delivery tests verify real wiring.
- [ ] Denials are audited/metered without exposing raw tokens, room secrets, or sensitive payloads.

## 12. Hands-On Exercises

**Exercise A — Fix an exposed policy.** Configure `simpDestMatchers("/topic/**").permitAll()` before `simpSubscribeDestMatchers("/topic/private/**").hasAuthority("TOPIC_PRIVATE")`. Write a test proving an unprivileged user can still subscribe, then fix it with type-specific matchers.

**Exercise B — Admin topic nested under public topic.** Require `TOPIC_ADMIN` for `/topic/public/admin/**` and `TOPIC_READ` for `/topic/public/**`. Swap their order and verify a user with only `TOPIC_READ` is mistakenly allowed when the broad rule comes first.

**Exercise C — Broker impersonation.** Have a STOMP client send `SEND /topic/system/notifications` while another client subscribes to the topic. Ensure the forged content does not reach the subscriber when `simpMessageDestMatchers("/topic/**").denyAll()` is active.

**Exercise D — User destinations.** Create two different Principals with the same display name and subscribe to `/user/queue/inbox`; verify outbound routing isolates session/identity so they do not receive each other's messages.

**Exercise E — Scope and tenant.** Add `/topic/tenants/{tenantId}/rooms/{roomId}`; write a custom `AuthorizationManager` evaluating principal tenant membership, room role, and object state. Keep the custom rule before any broad fallback.

**Exercise F — CONNECT CSRF.** Run a STOMP/WebSocket integration test with and without CSRF on CONNECT. Compare it with the `nullDestMatcher().authenticated()` unit test to understand the two distinct layers.

**Exercise G — No-decision.** Remove `anyMessage().denyAll()` and test an unmatched message. Observe the `null`/abstain result, then restore the explicit deny fallback.

**Exercise H — Role prefix.** Test `hasRole("MODERATOR")`, `hasAuthority("MODERATOR")`, and `hasAuthority("ROLE_MODERATOR")` in three independent tests.

## 13. Summary

`MessageMatcherDelegatingAuthorizationManager` maps message matchers to authorization decisions in Spring Messaging/STOMP. **Order is the security contract**: the first matching rule decides; the framework does not automatically sort the "most specific pattern" first.

A safe configuration typically includes:

```java
.nullDestMatcher().authenticated()
.simpMessageDestMatchers("/topic/**", "/queue/**").denyAll()
.simpSubscribeDestMatchers("/topic/private/**")
    .hasAuthority("TOPIC_PRIVATE")
.simpSubscribeDestMatchers("/topic/public/admin/**")
    .hasAuthority("TOPIC_ADMIN")
.simpSubscribeDestMatchers("/topic/public/**")
    .hasAuthority("TOPIC_READ")
.simpMessageDestMatchers("/app/chat/**")
    .hasAuthority("CHAT_SEND")
.simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
.anyMessage().denyAll();
```

**Distinguish** client `MESSAGE/SEND` from `SUBSCRIBE` and avoid broad `simpDestMatchers` when only one type is intended. Block clients from publishing directly to broker prefixes, restrict subscriptions to private/user destinations, and place `anyMessage().denyAll()` last. Manager unit tests catch ordering bugs, while production safety additionally requires handshake authentication, STOMP CONNECT CSRF, user-session routing, broker policies, and object/tenant authorization.

## References

- Spring Security 6.5 — WebSocket Security and rule matchers in Java config: https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/websocket.html
- Spring Security 6.5 API — `MessageMatcherDelegatingAuthorizationManager`: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.html
- Spring Security 6.5 API — `MessageMatcherDelegatingAuthorizationManager.Builder`: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.html
- Spring Security 6.5 API — `Builder.Constraint`: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.Constraint.html
- Spring Security 6.5 API — `AuthorizationChannelInterceptor`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/messaging/access/intercept/AuthorizationChannelInterceptor.html
- Spring Framework — WebSocket/STOMP Messaging: https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html
- Spring Framework — User destinations: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html
- OWASP — WebSocket Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html
