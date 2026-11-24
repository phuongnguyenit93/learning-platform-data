# Permissions on Personal Channels, Shared Topics, and Tenant Data in Spring Security

## 1. Why Is WebSocket Login Not Enough to Protect Data?

A Spring Boot application uses **STOMP over WebSocket** for real-time notifications. Users Alice and Bob belong to tenant `t1`; Carol belongs to tenant `t2`; Mallory has an account yet holds membership in no tenant.

The application has three destination groups:

- **Personal channel:** `/user/queue/notifications` to receive notifications intended for a single user or session.
- **Shared topic:** `/topic/announcements` so every logged-in user can view public in-app announcements.
- **Per-tenant topics:** `/topic/tenants/t1/events` and `/topic/tenants/t2/events` to broadcast events receivable only by members of the respective tenant.

If the system only protects the `/ws` HTTP handshake with `authenticated()`, Carol can still try `SUBSCRIBE /topic/tenants/t1/events` and listen to `t1` data. If clients are allowed `SEND /topic/announcements`, they can spoof system announcements without passing through business logic.

**Principle:** authorization must evaluate **Authentication + STOMP message type + destination + tenant + action**, not merely the handshake URL or prefix. A client permitted to SUBSCRIBE to a topic is not automatically permitted to SEND to that topic.

### Learning Outcomes

After this lesson, you will be able to:
1. Distinguish `/app`, `/topic`, `/queue`, and `/user` from `/ws`.
2. Separate `SimpMessageType.SUBSCRIBE` and `SimpMessageType.MESSAGE`.
3. Use Spring Security 6.5's `@EnableWebSocketSecurity` and `AuthorizationManager<Message<?>>`.
4. Separate personal subscribe, broadcast subscribe, per-tenant subscribe, and publish permissions.
5. Use `MessageAuthorizationContext.getVariables()` to extract `{tenant}` and verify it against server-side membership.
6. Block direct subscriptions to broker queues and direct client SENDs to broker prefixes.
7. Understand why Spring Security protects only `clientInboundChannel` and why additional checks are required in the server publisher.
8. Design revocation, multi-session handling, CONNECT CSRF, origin policies, and real testing.
9. Write a Java 17/Spring Boot 3.5.6 project with unit/integration tests covering the decision matrix.

## 2. STOMP Routing and Trust Boundaries

| Prefix | Example | Function |
|---|---|---|
| `/ws` | `ws://localhost:8080/ws` | HTTP upgrade / WebSocket handshake, not a STOMP address |
| `/app` | `/app/tenants/t1/events` | Client SEND to server `@MessageMapping` handler |
| `/topic` | `/topic/announcements` | Broker destination for multiple subscribers |
| `/topic/tenants/{tenant}` | `/topic/tenants/t1/events` | Per-tenant logical topic; requires an ACL |
| `/queue` | `/queue/notifications-user123` | Broker queue; clients should not access arbitrarily |
| `/user` | `/user/queue/notifications` | Logical user destination resolved by Spring per session |

Spring Messaging flow:

```text
Browser → HTTP GET /ws Upgrade → authenticated WebSocket session
                           |
                  STOMP CONNECT + CSRF
                           |
                    clientInboundChannel
                           |
                    Message AuthorizationManager
                       |          |
                    DENY        ALLOW
                                  |
              +-------------------+-------------------+
              |                                       |
     SEND /app/**                           SUBSCRIBE /topic|/user
              |                                       |
      @MessageMapping                            Broker registry
              |
      Trusted business service
              |
     SimpMessagingTemplate
              |
       clientOutboundChannel → subscribed user/session
```

**Spring Security 6.5 places the message authorization interceptor only on `clientInboundChannel`**. It does not automatically check permissions on every message emitted to `clientOutboundChannel`. Therefore, when sending sensitive tenant data, the server must verify **who may subscribe** and **who may create the content being sent**. When membership changes during a long-lived connection, actively revoke subscriptions or cap subscription lifetime.

### 2.1. Where Does WebSocket Authentication Come From?

With STOMP over WebSocket in the Servlet stack, a WebSocket session typically inherits the `Principal` from the Spring Security–authenticated HTTP handshake. When session/cookie auth is used, the server maps `Authentication` to `simpUser` in Spring Messaging.

Do not trust:
- Default STOMP headers `login=admin` or `passcode=...` as proof of Authentication.
- Client-supplied JSON fields `sender`, `tenant`, or `role`.
- The `t1` segment of a destination as proof the user belongs to `t1`.
- Unverified query parameters `?user=alice` or `X-Tenant-Id`.

Clients only select a **destination**. Authorization decisions come from the **trusted principal and canonical server-side membership**.

## 3. Personal Channel /user/queue and Queue Eavesdropping Risk

Client Alice subscribes:

```text
SUBSCRIBE
id:alice-notifications
destination:/user/queue/notifications
```

Spring's `UserDestinationMessageHandler` translates the logical user destination into a session-specific broker destination (for example, `/queue/notifications-user123`). The server can send:

```java
template.convertAndSendToUser(
    "alice", "/queue/notifications", payload);
```

This **does not mean** Alice may directly `SUBSCRIBE /queue/notifications-user123` or `/queue/**`. An attacker could try guessing session/queue suffixes to listen to another user's data if broker/direct subscriptions are opened too broadly.

Correct rule:

```java
messages.simpSubscribeDestMatchers(
    "/user/queue/notifications").authenticated();
```

At the same time, catch-all deny any `SUBSCRIBE /queue/**` not explicitly granted.

### 3.1. @SendToUser and Multiple Sessions

With:

```java
@MessageMapping("/inbox/ping")
@SendToUser(
    destinations = "/queue/notifications",
    broadcast = false)
public String ping(Principal principal) {
    return "pong:" + principal.getName();
}
```

`broadcast=false` sends the reply only to the **requesting session**, which is useful when one user has multiple tabs. `SimpMessagingTemplate.convertAndSendToUser(...)` in general can deliver to **multiple sessions of the same user**. When a user can operate across multiple tenants across multiple sessions, enforce data classification and tenant scoping on each notification; a logical user destination does not protect the payload by itself.

### 3.2. Scenarios That Must Not Be Allowed

| Client action | Outcome |
|---|---|
| Alice SUBSCRIBE `/user/queue/notifications` | Allow, authenticated |
| Alice SUBSCRIBE `/queue/notifications-user123` | Deny |
| Alice SUBSCRIBE `/user/bob/queue/notifications` | Deny |
| Alice SUBSCRIBE `/user/queue/admin-secrets` | Deny if undeclared |
| Anonymous SUBSCRIBE `/user/queue/notifications` | Deny |

## 4. Shared Topics and SEND/SUBSCRIBE Permissions

A shared topic such as `/topic/announcements` normally allows logged-in users to **listen to system-sent announcements**, without letting clients broadcast announcements themselves.

```text
SUBSCRIBE /topic/announcements → authenticated user: ALLOW
SEND      /topic/announcements → any client: DENY
```

**Wrong configuration:**

```java
// COUNTEREXAMPLE: accidentally opens MESSAGE permission on broker prefix.
messages.simpDestMatchers("/topic/**").authenticated();
```

Because `simpDestMatchers` also matches **MESSAGE** destinations, the rule above can let users send directly to the topic, creating an announcement-spoofing vector. Correct approach:

```java
messages
    .simpSubscribeDestMatchers(
        "/topic/announcements").authenticated()
    .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
    .anyMessage().denyAll();
```

Narrow rules must precede the catch-all deny. Never let private data, personal reports, or individual profiles flow into `/topic/announcements` just because "everyone is logged in."

## 5. Per-Tenant Topics: Multi-Tenant Boundaries

Alice and Bob belong to `t1`, Carol belongs to `t2`. A minimal policy:

| User | SUBSCRIBE t1 | SUBSCRIBE t2 | SEND /app/tenants/t1/events |
|---|---|---|---|
| Alice, t1 member, EVENT_PUBLISH | Allow | Deny | Allow |
| Bob, t1 member, read-only | Allow | Deny | Deny |
| Carol, t2 member, EVENT_PUBLISH | Deny | Allow | Deny |
| Mallory, no membership | Deny | Deny | Deny |
| Anonymous | Deny | Deny | Deny |

The client sends:

```text
SUBSCRIBE
destination:/topic/tenants/t2/events
id:tenant-updates
```

`t2` is a selector, not a credential. The server must check:

```text
isAuthenticated(principal)
AND tenantExists(t2)
AND activeMembership(principal, t2)
AND allowedToSubscribe(principal, "events", t2)
```

For publishing:

```text
isAuthenticated(principal)
AND tenantExists(t2)
AND activeMembership(principal, t2)
AND hasAuthority(principal, "EVENT_PUBLISH")
AND allowedToCreateEvent(principal, resource)
```

**Do not do this:**

```java
// COUNTEREXAMPLE: client declares itself as belonging to the tenant.
boolean granted = payload.tenantId().equals(tenantFromPath);
```

Both the payload and the path are chosen by the caller. They must be verified against the server-owned DB/membership/ACL.

### 5.1. A Tenant Topic Does Not Suffice for Per-Record Permissions

A member of `t1` is not automatically entitled to read **every invoice, payroll report, health record, or secret** of `t1`. If a topic carries sensitive per-record events, enforce per-record authorization at the publisher or publish only a non-sensitive event ID and have clients fetch details via an HTTP endpoint that checks owner/share/tenant permissions.

Often `canSubscribeToTenant(t1)` and `canRead(resource:123)` must be separated.

## 6. AuthorizationManager<Message<?>> in Spring Security 6.5

Spring Security 6.5 supports `@EnableWebSocketSecurity` with `MessageMatcherDelegatingAuthorizationManager`. Key matchers:

| Matcher | Meaning |
|---|---|
| `simpSubscribeDestMatchers("/topic/...")` | Only SUBSCRIBE to the specified destination |
| `simpDestMatchers("/app/...")` | Only MESSAGE/SEND to the specified destination |
| `simpTypeMatchers(CONNECT,...)` | Controls STOMP/SIMP frame types |
| `nullDestMatcher()` | Matches messages without a destination |
| `anyMessage().denyAll()` | Denies all messages lacking an allow rule |
| `.access(customManager)` | Custom policy using `Authentication` and `MessageAuthorizationContext<?>` |

In particular, `MessageAuthorizationContext.getVariables()` returns variables extracted by the destination matcher from the pattern; for example, `"/topic/tenants/{tenant}/events"` can supply `tenant=t1`. Verify this value against canonical membership.

Example:

```java
messages
    .simpSubscribeDestMatchers(
        "/topic/tenants/{tenant}/events")
    .access((auth, ctx) ->
        new AuthorizationDecision(
            acl.canSubscribe(
                auth.get(),
                ctx.getVariables().get("tenant"))));
```

If tenant is null/invalid or auth is unauthorized, the custom manager must return an **explicit deny**. Never return null/abstain for a mandatory security check.

### 6.1. Catch-All Deny and Matcher Ordering

A safe ordered configuration:

1. Authenticated CONNECT/DISCONNECT/UNSUBSCRIBE.
2. SUBSCRIBE to recognized private logical queues.
3. SUBSCRIBE to shared announcements.
4. SUBSCRIBE to tenant topics after membership checks.
5. SEND to `/app/inbox/ping`.
6. SEND to `/app/tenants/{tenant}/events` after publish permission checks.
7. `simpTypeMatchers(MESSAGE,SUBSCRIBE).denyAll()`.
8. `anyMessage().denyAll()`.

Never use `.simpSubscribeDestMatchers("/queue/**").permitAll()` or `.simpDestMatchers("/topic/**").authenticated()` as a shortcut.

## 7. Complete Java 17 / Spring Boot 3.5.6 Project

The example uses **STOMP over WebSocket on the Servlet stack**, Java 17, Spring Boot **3.5.6**, and Spring Security 6.5.x. The setup includes HTTP authentication, WebSocket broker prefixes, message authorization, a membership service, and a publisher that re-checks business permissions.

### 7.1. Directory Tree

```text
stomp-tenant-security/
  pom.xml
  src/main/java/com/example/messages/
    MessageSecurityApplication.java
    HttpSecurityConfig.java
    WebSocketConfig.java
    TenantPermissions.java
    MessageSecurityConfig.java
    EventPublisher.java
    EventsController.java
  src/test/java/com/example/messages/
    MessageAuthorizationTest.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>stomp-tenant-security</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
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
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
```

`spring-boot-starter-websocket` provides WebSocket/STOMP, while `spring-security-messaging` provides message interceptors and authorization. Do not mix this demo with non-STOMP raw WebSocket handlers or RSocket, as they have different protection mechanisms.

### 7.3. MessageSecurityApplication.java

```java
package com.example.messages;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MessageSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(
            MessageSecurityApplication.class, args);
    }
}
```

### 7.4. HttpSecurityConfig.java — Authenticating Before the Handshake

```java
package com.example.messages;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HttpSecurityConfig {
    @Bean
    SecurityFilterChain httpChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .requestMatchers("/ws", "/ws/**").authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .authorities("ROLE_USER","EVENT_PUBLISH")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-pass"))
                .authorities("ROLE_USER")
                .build(),
            User.withUsername("carol")
                .password(encoder.encode("carol-pass"))
                .authorities("ROLE_USER","EVENT_PUBLISH")
                .build(),
            User.withUsername("mallory")
                .password(encoder.encode("mallory-pass"))
                .authorities("ROLE_USER")
                .build());
    }
}
```

Users log in over HTTP before the handshake. The browser WebSocket API does not allow JavaScript to set arbitrary `Authorization` headers; for browsers, use cookies/sessions with proper SameSite/CSRF/origin settings or a verified token handshake architecture rather than assuming Basic is the browser default.

### 7.5. WebSocketConfig.java — Broker and User Destination Prefixes

```java
package com.example.messages;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry broker) {
        broker.enableSimpleBroker("/topic", "/queue");
        broker.setApplicationDestinationPrefixes("/app");
        broker.setUserDestinationPrefix("/user");
    }

    @Override
    public void registerStompEndpoints(
            StompEndpointRegistry endpoints) {
        endpoints.addEndpoint("/ws")
            .setAllowedOrigins("http://localhost:8080");
    }
}
```

`setAllowedOrigins` is an allowlist for the local demo. In deployment, replace it with trusted frontend origins; never set `*` for WebSockets using cookies/sessions. `/topic` and `/queue` are broker destinations; `/user` is the prefix for resolving private destinations and **should not** be used like a regular broker prefix.

### 7.6. TenantPermissions.java — Server-Side Membership Source

```java
package com.example.messages;

import java.util.Map;
import java.util.Set;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component
public class TenantPermissions {

    private final Map<String, Set<String>> members = Map.of(
        "t1", Set.of("alice","bob"),
        "t2", Set.of("carol")
    );

    private boolean validUser(Authentication auth) {
        return auth != null
            && auth.isAuthenticated()
            && !(auth instanceof AnonymousAuthenticationToken);
    }

    private boolean validTenant(String tenant) {
        return tenant != null
            && tenant.matches("[a-z][a-z0-9-]{0,20}")
            && members.containsKey(tenant);
    }

    public boolean canSubscribe(
            Authentication auth, String tenant) {
        return validUser(auth) && validTenant(tenant)
            && members.get(tenant).contains(auth.getName());
    }

    public boolean canPublish(
            Authentication auth, String tenant) {
        if (!canSubscribe(auth, tenant)) return false;
        for (GrantedAuthority a : auth.getAuthorities()) {
            if ("EVENT_PUBLISH".equals(a.getAuthority())) {
                return true;
            }
        }
        return false;
    }
}
```

In-memory data is for study only. Production must map principal IDs via a trusted identity source, verify active membership, scope roles by tenant, and maintain DB consistency. `EVENT_PUBLISH` is **not sufficient** if the user does not belong to the chosen tenant.

### 7.7. MessageSecurityConfig.java — Separating the Four Permission Types

```java
package com.example.messages;

import static org.springframework.messaging.simp.SimpMessageType.CONNECT;
import static org.springframework.messaging.simp.SimpMessageType.DISCONNECT;
import static org.springframework.messaging.simp.SimpMessageType.UNSUBSCRIBE;
import static org.springframework.messaging.simp.SimpMessageType.MESSAGE;
import static org.springframework.messaging.simp.SimpMessageType.SUBSCRIBE;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
public class MessageSecurityConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            TenantPermissions permissions) {

        var rules =
            MessageMatcherDelegatingAuthorizationManager.builder();

        rules
            .simpTypeMatchers(CONNECT, DISCONNECT, UNSUBSCRIBE)
                .authenticated()

            .simpSubscribeDestMatchers(
                "/user/queue/notifications")
                .authenticated()

            .simpSubscribeDestMatchers(
                "/topic/announcements")
                .authenticated()

            .simpSubscribeDestMatchers(
                "/topic/tenants/{tenant}/events")
                .access((auth, ctx) ->
                    new AuthorizationDecision(
                        permissions.canSubscribe(
                            auth.get(),
                            ctx.getVariables().get("tenant"))))

            .simpDestMatchers("/app/inbox/ping")
                .authenticated()

            .simpDestMatchers(
                "/app/tenants/{tenant}/events")
                .access((auth, ctx) ->
                    new AuthorizationDecision(
                        permissions.canPublish(
                            auth.get(),
                            ctx.getVariables().get("tenant"))))

            .simpTypeMatchers(MESSAGE, SUBSCRIBE)
                .denyAll()

            .anyMessage().denyAll();

        return rules.build();
    }
}
```

**Points to note:**
- `@EnableWebSocketSecurity` integrates message authorization and enables CSRF on CONNECT by default.
- `SimpMessageType.MESSAGE` covers `SEND /app/**`; `SUBSCRIBE` uses its dedicated matcher.
- The tenant variable is extracted from `MessageAuthorizationContext.getVariables()`; membership is checked in `TenantPermissions`.
- Only `/user/queue/notifications` is opened; direct broker queues are not opened.
- Only `SUBSCRIBE /topic/announcements` is opened; direct `MESSAGE` to the topic is blocked by the catch-all.
- `anyMessage().denyAll()` closes destinations and message types outside the allowlist.
- `HEARTBEAT` and other message types are not explicitly opened in this example. If real transport needs them, test and add a narrow rule rather than enabling a blanket allow.

### 7.8. EventPublisher.java — Re-Checking Permissions in the Service

```java
package com.example.messages;

import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;

@Service
public class EventPublisher {
    public record EventView(
        String tenant, String sender, String body) {}

    private final TenantPermissions permissions;
    private final SimpMessagingTemplate template;

    public EventPublisher(
            TenantPermissions permissions,
            SimpMessagingTemplate template) {
        this.permissions = permissions;
        this.template = template;
    }

    public void publish(
            Authentication auth, String tenant, String text) {

        if (!permissions.canPublish(auth, tenant)) {
            throw new AccessDeniedException(
                "Publish not permitted");
        }
        if (text == null || text.isBlank()
                || text.length() > 1000) {
            throw new IllegalArgumentException(
                "Message length must be 1..1000");
        }

        EventView event =
            new EventView(tenant, auth.getName(), text);

        template.convertAndSend(
            "/topic/tenants/" + tenant + "/events",
            event);
    }
}
```

The service checks a second time because a method can be called from a job or another HTTP controller without passing through inbound STOMP security. Payload `sender` and `tenant` are constructed by the server from verified Authentication/tenant data; never use privileged fields supplied by the client. For sensitive tenants, also check object-level permissions before outbound emission.

### 7.9. EventsController.java — SEND /app, Reply via /user

```java
package com.example.messages;

import java.security.Principal;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;

@Controller
public class EventsController {
    public record PublishEvent(String body) {}
    private final EventPublisher publisher;

    public EventsController(EventPublisher publisher) {
        this.publisher = publisher;
    }

    @MessageMapping("/tenants/{tenant}/events")
    public void publish(
            @DestinationVariable("tenant") String tenant,
            @Payload PublishEvent payload,
            Principal principal) {

        if (!(principal instanceof Authentication auth)) {
            throw new AccessDeniedException(
                "Missing trusted principal");
        }

        publisher.publish(auth, tenant, payload.body());
    }

    @MessageMapping("/inbox/ping")
    @SendToUser(
        destinations = "/queue/notifications",
        broadcast = false)
    public String ping(Principal principal) {
        return "pong:" + principal.getName();
    }
}
```

Proper STOMP paths:
- Client Alice: `SEND /app/tenants/t1/events`.
- Server: checks publish permission at the message layer and service, then `convertAndSend("/topic/tenants/t1/events", event)`.
- Bob subscribed to `t1` receives the event; Carol in `t2` cannot subscribe to `t1`.
- Client Alice: `SEND /app/inbox/ping`; replies via `@SendToUser` to Alice's session and client subscribes to `/user/queue/notifications`.
- Clients **cannot** SEND directly to `/topic/**`, `/queue/**`, or forge `/user/bob/...` destinations.

## 8. Testing Message Authorization with JUnit 5

The test suite uses `MessageBuilder` + `SimpMessageHeaderAccessor` to construct a `Message<byte[]>` with `simpMessageType` and `simpDestination`. It invokes `AuthorizationManager.authorize(...)` and asserts `AuthorizationResult.isGranted()`.

**This tests the policy inside the Spring application context, not WebSocket E2E**. CONNECT CSRF, origin handshakes, and actual `UserDestinationMessageHandler` queue translation require the separate E2E suite in Section 9.

**`src/test/java/com/example/messages/MessageAuthorizationTest.java`**

```java
package com.example.messages;

import java.util.Arrays;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest
class MessageAuthorizationTest {
    @Autowired AuthorizationManager<Message<?>> manager;
    @Autowired TenantPermissions permissions;

    private static Authentication user(
            String name, String... authorities) {
        List<GrantedAuthority> granted =
            Arrays.stream(authorities)
                .map(SimpleGrantedAuthority::new)
                .map(a -> (GrantedAuthority) a)
                .toList();

        return UsernamePasswordAuthenticationToken.authenticated(
            name, "N/A", granted);
    }

    private static Authentication alice() {
        return user("alice", "ROLE_USER", "EVENT_PUBLISH");
    }

    private static Authentication bob() {
        return user("bob", "ROLE_USER");
    }

    private static Authentication carol() {
        return user("carol", "ROLE_USER", "EVENT_PUBLISH");
    }

    private static Authentication mallory() {
        return user("mallory", "ROLE_USER");
    }

    private static Authentication anonymous() {
        return new AnonymousAuthenticationToken(
            "key", "anonymous",
            List.of(new SimpleGrantedAuthority(
                "ROLE_ANONYMOUS")));
    }

    private static Message<byte[]> frame(
            SimpMessageType type, String destination) {
        SimpMessageHeaderAccessor h =
            SimpMessageHeaderAccessor.create(type);
        if (destination != null) {
            h.setDestination(destination);
        }
        h.setLeaveMutable(true);
        return MessageBuilder.createMessage(
            new byte[0], h.getMessageHeaders());
    }

    private void expect(
            Authentication auth,
            SimpMessageType type,
            String destination,
            boolean granted) {
        AuthorizationResult decision = manager.authorize(
            () -> auth, frame(type, destination));

        assertNotNull(decision,
            "Every frame needs explicit authorization");
        assertEquals(granted, decision.isGranted(),
            type + " " + destination);
    }

    @Test
    void authenticatedConnectCanPassManager() {
        expect(alice(), SimpMessageType.CONNECT, null, true);
    }

    @Test
    void anonymousConnectDenied() {
        expect(anonymous(), SimpMessageType.CONNECT, null, false);
    }

    @Test
    void disconnectAuthenticatedAllowed() {
        expect(alice(), SimpMessageType.DISCONNECT, null, true);
    }

    @Test
    void unsubscribeAuthenticatedAllowed() {
        expect(alice(), SimpMessageType.UNSUBSCRIBE, null, true);
    }

    @Test
    void personalQueueAllowedForAlice() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            "/user/queue/notifications", true);
    }

    @Test
    void personalQueueAllowedForCarol() {
        expect(carol(), SimpMessageType.SUBSCRIBE,
            "/user/queue/notifications", true);
    }

    @Test
    void anonymousPersonalQueueDenied() {
        expect(anonymous(), SimpMessageType.SUBSCRIBE,
            "/user/queue/notifications", false);
    }

    @Test
    void directBrokerQueueDenied() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            "/queue/notifications-user123", false);
    }

    @Test
    void otherUsersLogicalQueueDenied() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            "/user/bob/queue/notifications", false);
    }

    @Test
    void unlistedPrivateQueueDenied() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            "/user/queue/admin", false);
    }

    @Test
    void commonAnnouncementsSubscribeAllowed() {
        expect(bob(), SimpMessageType.SUBSCRIBE,
            "/topic/announcements", true);
    }

    @Test
    void sendingToCommonTopicDenied() {
        expect(alice(), SimpMessageType.MESSAGE,
            "/topic/announcements", false);
    }

    @Test
    void aliceCanSubscribeOwnTenant() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            "/topic/tenants/t1/events", true);
    }

    @Test
    void bobCanSubscribeOwnTenant() {
        expect(bob(), SimpMessageType.SUBSCRIBE,
            "/topic/tenants/t1/events", true);
    }

    @Test
    void carolCannotSubscribeT1() {
        expect(carol(), SimpMessageType.SUBSCRIBE,
            "/topic/tenants/t1/events", false);
    }

    @Test
    void carolCanSubscribeT2() {
        expect(carol(), SimpMessageType.SUBSCRIBE,
            "/topic/tenants/t2/events", true);
    }

    @Test
    void aliceCannotSubscribeT2() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            "/topic/tenants/t2/events", false);
    }

    @Test
    void loggedInNonMemberDenied() {
        expect(mallory(), SimpMessageType.SUBSCRIBE,
            "/topic/tenants/t1/events", false);
    }

    @Test
    void unknownTenantDenied() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            "/topic/tenants/t9/events", false);
    }

    @Test
    void malformedTenantDenied() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            "/topic/tenants/_invalid/events", false);
    }

    @Test
    void aliceCanPublishToT1ViaApp() {
        expect(alice(), SimpMessageType.MESSAGE,
            "/app/tenants/t1/events", true);
    }

    @Test
    void bobCannotPublishWithoutAuthority() {
        expect(bob(), SimpMessageType.MESSAGE,
            "/app/tenants/t1/events", false);
    }

    @Test
    void carolCanPublishToT2ViaApp() {
        expect(carol(), SimpMessageType.MESSAGE,
            "/app/tenants/t2/events", true);
    }

    @Test
    void aliceCannotPublishToOtherTenant() {
        expect(alice(), SimpMessageType.MESSAGE,
            "/app/tenants/t2/events", false);
    }

    @Test
    void carolCannotPublishToT1() {
        expect(carol(), SimpMessageType.MESSAGE,
            "/app/tenants/t1/events", false);
    }

    @Test
    void clientSendToTenantBrokerTopicDenied() {
        expect(alice(), SimpMessageType.MESSAGE,
            "/topic/tenants/t1/events", false);
    }

    @Test
    void clientSendToBrokerQueueDenied() {
        expect(alice(), SimpMessageType.MESSAGE,
            "/queue/notifications", false);
    }

    @Test
    void privatePingViaAppAllowed() {
        expect(bob(), SimpMessageType.MESSAGE,
            "/app/inbox/ping", true);
    }

    @Test
    void unlistedApplicationMessageDenied() {
        expect(alice(), SimpMessageType.MESSAGE,
            "/app/admin/reset", false);
    }

    @Test
    void unlistedTopicDenied() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            "/topic/secret", false);
    }

    @Test
    void subscribeToApplicationRouteDenied() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            "/app/tenants/t1/events", false);
    }

    @Test
    void messageWithoutDestinationDenied() {
        expect(alice(), SimpMessageType.MESSAGE,
            null, false);
    }

    @Test
    void subscribeWithoutDestinationDenied() {
        expect(alice(), SimpMessageType.SUBSCRIBE,
            null, false);
    }

    @Test
    void unlistedMessageTypeDenied() {
        expect(alice(), SimpMessageType.OTHER,
            null, false);
    }

    @Test
    void publisherUsesVerifiedSenderAndTenant() {
        SimpMessagingTemplate template =
            mock(SimpMessagingTemplate.class);
        EventPublisher publisher =
            new EventPublisher(permissions, template);

        publisher.publish(alice(), "t1", "hello");

        verify(template).convertAndSend(
            eq("/topic/tenants/t1/events"),
            eq(new EventPublisher.EventView(
                "t1", "alice", "hello")));
    }

    @Test
    void publisherDeniesCrossTenantBeforeSending() {
        SimpMessagingTemplate template =
            mock(SimpMessagingTemplate.class);
        EventPublisher publisher =
            new EventPublisher(permissions, template);

        assertThrows(
            org.springframework.security.access.AccessDeniedException.class,
            () -> publisher.publish(alice(), "t2", "blocked"));
        verifyNoInteractions(template);
    }

    @Test
    void publisherDeniesReadOnlyMember() {
        SimpMessagingTemplate template =
            mock(SimpMessagingTemplate.class);
        EventPublisher publisher =
            new EventPublisher(permissions, template);

        assertThrows(
            org.springframework.security.access.AccessDeniedException.class,
            () -> publisher.publish(bob(), "t1", "blocked"));
        verifyNoInteractions(template);
    }

    @Test
    void publisherRejectsEmptyBody() {
        SimpMessagingTemplate template =
            mock(SimpMessagingTemplate.class);
        EventPublisher publisher =
            new EventPublisher(permissions, template);

        assertThrows(IllegalArgumentException.class,
            () -> publisher.publish(alice(), "t1", " "));
        verifyNoInteractions(template);
    }

    @Test
    void publisherRejectsOversizeBody() {
        SimpMessagingTemplate template =
            mock(SimpMessagingTemplate.class);
        EventPublisher publisher =
            new EventPublisher(permissions, template);

        assertThrows(IllegalArgumentException.class,
            () -> publisher.publish(
                alice(), "t1", "X".repeat(1001)));
        verifyNoInteractions(template);
    }
}
```

### 8.1. How to Run

```bash
mvn test
```

**Expected outcome:** tests for personal SUBSCRIBE, shared topics, tenants, app SEND, broker bypass, non-members, deny-by-default, and publisher defense-in-depth all pass. This is an **authored and reviewed code suite, not an executed Maven log**. To confirm exact compatibility with your dependency/build environment, run Maven on the project.

These tests invoke the authorization bean directly. They **do not** open a real WebSocket, send STOMP CONNECT with CSRF, or test broker delivery. E2E tests are required to confirm the interceptor is wired on the network and has no bypass path.

## 9. End-to-End STOMP Testing Matrix

Use `@SpringBootTest(webEnvironment = RANDOM_PORT)` with `WebSocketStompClient` or a STOMP browser client using real login sessions/CSRF. A solid suite covers at least:

| Scenario | Action | Outcome to Verify |
|---|---|---|
| Valid CONNECT | Logged-in Alice, valid STOMP CSRF token | CONNECTED |
| CONNECT missing CSRF | Logged-in Alice without token | Rejected |
| Untrusted Origin | Handshake from unfamiliar origin | Rejected |
| Private subscribe | Alice SUBSCRIBE `/user/queue/notifications` | Alice receives reply |
| Private isolation | Bob subscribes to his own private channel | Does not receive Alice's reply |
| Direct queue | Alice SUBSCRIBE `/queue/notifications-user123` | Subscription rejected |
| Shared topic | Bob SUBSCRIBE `/topic/announcements` | Receives server announcement |
| Shared topic spoof | Alice SEND `/topic/announcements` | No forged message emitted |
| T1 subscribe | Alice/Bob SUBSCRIBE `/topic/tenants/t1/events` | Accepted |
| Cross-tenant subscribe | Carol SUBSCRIBE `/topic/tenants/t1/events` | Rejected |
| T2 subscribe | Carol SUBSCRIBE `/topic/tenants/t2/events` | Accepted |
| T1 publish | Alice SEND `/app/tenants/t1/events` | Bob receives t1 event |
| T1 read-only publish | Bob SEND `/app/tenants/t1/events` | Rejected |
| Cross-tenant publish | Alice SEND `/app/tenants/t2/events` | Rejected |
| Private session reply | Alice has two tabs, pings from tab A | Only tab A receives when broadcast=false |
| Membership revoked | Alice removed from t1 while socket stays open | Subscription revoked/disconnected before next sensitive event |

**Do not confuse HTTP 403 with STOMP errors:** once the connection is upgraded, authorization failures may produce a STOMP `ERROR`, close the socket, or report frame failure. Tests must verify **no active subscription, no data received, and no unauthorized publish**, rather than demanding an HTTP status.

### 9.1. Example STOMP Frames

```text
SUBSCRIBE
id:alice-t1
destination:/topic/tenants/t1/events
```

Alice with publish permission:

```text
SEND
destination:/app/tenants/t1/events
content-type:application/json

{"body":"Invoice created"}
```

The two examples above illustrate the frame content produced by a STOMP client. On the wire, STOMP requires a NULL terminator at the end of the frame; the STOMP client library handles that automatically. The client destination is **not** `/topic/tenants/t1/events` when sending a publish command; that is the destination the server publishes to after verifying permissions.

## 10. CONNECT CSRF and Cross-Site WebSocket Hijacking

Browsers do not apply the Same-Origin Policy to WebSockets like fetch/XHR. Spring Security 6.5 requires a CSRF token on **STOMP CONNECT** when using `@EnableWebSocketSecurity`; WebSocket endpoints should also restrict allowed origins.

Browser clients must:
1. Log in with a valid session/cookie.
2. Fetch the CSRF token from the same origin via a protected endpoint/config.
3. Open a WebSocket to `/ws` in the same session.
4. Put the CSRF token into **STOMP CONNECT headers** under Spring's token header name.
5. SUBSCRIBE only after receiving CONNECTED.

If using SockJS, HTTP fallback transports have their own mechanisms; never disable CSRF across the **entire website** just to make SockJS work. For JWT in STOMP CONNECT, you must write and test a `ChannelInterceptor` that verifies the token and sets `Authentication` in the proper order; Spring does not trust STOMP `Authorization`/`login` headers as proof of identity by default.

## 11. Multi-Tenancy in Production

### 11.1. Subscription Authorization Is Time-Bound

A subscription can live for many hours. If a user's membership or role is revoked mid-connection, checking only at SUBSCRIBE time **does not automatically block every subsequent outbound event**. Add:
- Forced unsubscribe/disconnect on revocation.
- Bounded reconnects and TTL-based re-authentication.
- Policy versioning and membership-cache invalidation.
- Per-recipient filtering for highly sensitive data.
- Auditing of principal, tenant, subscription ID, and revocation time.

### 11.2. Per-Tenant Topics Do Not Replace Object-Level ACLs

A member of `t1` may read tenant-level activity yet be barred from viewing payroll reports in `t1`. Never push secrets, full PII, or overly broad record-level data to a tenant broadcast topic. You can emit a summary ID/notification, then have clients fetch details via an HTTP API enforcing record-level permissions.

### 11.3. Multi-Node and Broker Relays

The demo uses `enableSimpleBroker("/topic","/queue")`. Production may use a RabbitMQ/ActiveMQ relay. In that case:
- Secure the network/broker TCP port so clients cannot connect straight to the broker and bypass Spring Security.
- Configure broker-side authorization, rotate credentials, and restrict wildcard permissions.
- Manage auto-delete queues, stale subscriptions, and user destinations across multiple nodes.
- Review `userDestinationBroadcast`/unresolved user destinations when running multiple Spring nodes.
- Test duplicate delivery, message ordering, reconnects, rate limits, and revocation.

### 11.4. Do Not Trust Raw Paths/Strings

Never check tenants with `startsWith("/topic/tenants/t1")` because that matches `t10`. Use destination matchers with captured variables and validate tenant IDs per policy. Path encoding, separators, custom broker naming, and proxy rewrites must be tested in real deployment conditions.

### 11.5. Preventing Floods and Data Exfiltration

Authorization alone does not stop an authorized user from sending millions of messages:
- Rate limit by principal/tenant/session.
- Cap payload sizes and enforce attachment/media restrictions.
- Enforce timeouts, backpressure, queue retention, and delivery quotas.
- Keep logs/metrics free of raw secrets.
- Add anomaly detection for rapid cross-tenant SUBSCRIBE attempts or SENDs to unfamiliar destinations.

## 12. Common Mistakes

| Mistake | Risk | Fix |
|---|---|---|
| Authenticating only `/ws` | Cross-tenant SUBSCRIBE | Message authorization |
| Opening `simpDestMatchers("/topic/**")` | Clients can publish straight to the broker | SEND only to `/app/**` |
| Opening `/queue/**` to SUBSCRIBE | Listening to other users' private queues | Only logical `/user/queue/...` |
| Treating `/user/queue` as proof of record permission | Over-exposing personal data | Check payload/tenant/owner |
| Trusting `tenantId` from JSON | Client self-escalates scope | Canonical membership |
| Omitting publish role | Read-only users can write | Separate `canSubscribe`/`canPublish` |
| Trusting `sender` from client | Impersonation | Trusted Principal |
| Letting ADMIN role bypass tenant | Cross-tenant escalation | Tenant-scoped admin binding |
| Allowing `SUBSCRIBE /topic/**` regardless of tenant | Tenant leak | Dynamic tenant matcher |
| Checking only at STOMP inbound | Jobs/HTTP calling publisher bypass checks | Service guard |
| Assuming outbound security checks every message | Stale subscriptions keep receiving | Revocation/recipient filtering |
| Disabling STOMP CONNECT CSRF | Cross-site WebSocket hijacking | STOMP CSRF token |
| Allowing Origin `*` with cookies/sessions | Cross-origin access | Trusted origin allowlist |
| Treating STOMP `login` as authentication | Identity spoofing | HTTP-authenticated Principal |
| Writing only handshake tests | Misses message-level flaws | Frame/destination/user matrix |
| Treating denied STOMP like HTTP 403 | Wrong protocol layer | ERROR/close/no-delivery tests |
| Leaving direct broker TCP open | Bypasses Spring Security | Firewall and broker ACLs |

## 13. Release Checklist

- [ ] Protect the HTTP WebSocket handshake with Spring Security.
- [ ] Enable `@EnableWebSocketSecurity` and a message `AuthorizationManager`.
- [ ] Distinguish `MESSAGE` and `SUBSCRIBE`.
- [ ] Allow personal-channel SUBSCRIBE only on defined logical `/user/queue/**` paths.
- [ ] Never open direct broker `/queue/**`.
- [ ] Allow shared topics for SUBSCRIBE only; disallow direct client SEND.
- [ ] Enforce per-tenant topics using destination variables and canonical membership.
- [ ] Require stronger publish permissions than subscribe permissions where business rules dictate.
- [ ] Derive authoritative sender/tenant on the server, never from the body.
- [ ] Place a second guard in the business publisher.
- [ ] Put `anyMessage().denyAll()` at the end and test unlisted destinations.
- [ ] Protect STOMP CONNECT with CSRF and restrict origins.
- [ ] Map WebSocket identity from the HTTP session or a trusted token interceptor.
- [ ] Implement a revocation strategy for memberships changing during long subscriptions.
- [ ] Never place record-level secrets onto a tenant broadcast topic if users lack object ACLs.
- [ ] Maintain E2E tests verifying no-delivery and multi-session isolation.
- [ ] Secure external broker networks, queues, and credentials.
- [ ] Put auditing, rate limits, payload size limits, and observability in place.

## 14. Self-Check Questions

**1.** Alice has read permission for topic `t1`; may she SEND directly to `/topic/tenants/t1/events`?

**Answer:** No. Clients must SEND to `/app/tenants/t1/events`, passing through message authorization and the business handler.

**2.** Why should Alice not be allowed to subscribe to `/queue/notifications-user123`?

**Answer:** That is a physical broker destination that could belong to another session. Alice should subscribe only to logical `/user/queue/notifications`, letting Spring resolve it per session.

**3.** Carol is an authenticated user in `t2`; can she subscribe to `t1`?

**Answer:** No. Server-side `t1` membership must be verified, not merely authenticated status.

**4.** Does Spring Security automatically re-check every outbound message after a user is revoked?

**Answer:** No. Standard message authorization focuses on inbound; subscription revocation/reconnect or outbound publisher filtering is required.

**5.** What does `@SendToUser(broadcast=false)` solve?

**Answer:** It sends the reply to the requesting session rather than all sessions of that user; it does not grant document permissions by itself.

**6.** Does protecting WebSocket CONNECT require CSRF?

**Answer:** In the Spring Security 6.5 model with `@EnableWebSocketSecurity`, CONNECT requires a CSRF token to mitigate cross-site WebSocket hijacking; allowed origins are also needed.

## 15. Official References

- [Spring Security 6.5 — WebSocket Security](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/websocket.html): `@EnableWebSocketSecurity`, message matcher rules, SEND vs. SUBSCRIBE, CONNECT CSRF, outbound limitations.
- [Spring Security 6.5 — MessageMatcherDelegatingAuthorizationManager.Builder API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.html): `simpSubscribeDestMatchers`, `simpDestMatchers`, `anyMessage`.
- [Spring Security 6.5 — MessageAuthorizationContext API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/messaging/access/intercept/MessageAuthorizationContext.html): `getVariables()`.
- [Spring Security 6.5 — AuthorizationManager API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authorization/AuthorizationManager.html): `authorize(...)`, `AuthorizationResult`.
- [Spring Framework 6.2 — User Destinations](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/user-destination.html): logical `/user`, `UserDestinationMessageHandler`, `@SendToUser(broadcast=false)`.
- [Spring Framework 6.2 — Authentication](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/authentication.html): HTTP Principal and STOMP user header.
- [Spring Framework 6.2 — Authorization](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/authorization.html): message interceptor and Spring Security.
- [Spring Framework 6.2 — STOMP Message Flow](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/message-flow.html): inbound/broker/outbound channels.

**Key takeaway:** `/user/queue/**` is a logical private destination resolved by Spring per user/session, not a reason to open broker `/queue/**`. `/topic/announcements` is a shared topic with **SUBSCRIBE** access, not a license for clients to **SEND** directly. `/topic/tenants/{tenant}/events` must verify Authentication, membership, and per-tenant permissions from a source of truth on **every SUBSCRIBE/SEND**. Spring Security 6.5 protects `clientInboundChannel`; pair it with business publisher guards, object-level ACLs, and subscription revocation to prevent data leaks when permissions change.