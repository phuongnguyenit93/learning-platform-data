# Auth Session and Token Expiry on Long-Lived Connections

## 1. Problem: An Open Connection Does Not Prove Authorization Remains Valid

In a **Spring Boot - web-runtime** system, **WebSocket**, **STOMP over WebSocket**, **Server-Sent Events (SSE)**, and HTTP streaming connections live far longer than a typical HTTP request. A user may authenticate when opening the connection, yet later their access token expires, they log out, their account is locked, or their permissions are revoked.

**Never assume the framework automatically closes every long-lived connection the moment a token expires.** Authentication usually runs during the HTTP handshake / SSE GET or STOMP `CONNECT`. Subsequent WebSocket messages or SSE events do not automatically become fresh HTTP requests passing back through every Spring Security filter.

Separate four distinct states:
- **HTTP session:** session data held by the Servlet container/Spring Session, with a session ID, idle timeout, and invalidation.
- **Access token:** JWT or opaque token with `exp`/TTL, scopes, issuer/audience, verification rules, and revocation.
- **Transport connection:** the active TCP/WebSocket/SSE stream governed by network lifecycles.
- **Authorization:** current permission to access a topic, tenant, or record, or view/modify data at that instant.

In addition, systems can enforce a **connection lease**: an absolute deadline from authentication until mandatory reconnect/re-auth, independent of ping/pong and TCP timeouts.

This lesson explains when authentication executes, when tokens/permissions must be rechecked, how to handle logout/revocation mid-connection, how to secure SSE/WebSocket across multiple nodes, and walks through a **Spring Boot 3.3.13 + Java 17 SSE lab** where tokens expire mid-stream.

## 2. Expirations That Do Not Substitute for One Another

| Type | What Is Bounded | Automatically Closes All Open WebSockets/SSE? |
| --- | --- | --- |
| JWT `exp` / opaque token TTL | Window during which verifiers accept the credential | **Not by default**; depends on middleware and app policy |
| `HttpSession` `maxInactiveInterval` | Session idle timeout in container/repository | **Depends on integration** (WebSocket/Spring Session) |
| Cookie `Max-Age`/`Expires` | How long the browser keeps/sends the cookie | Does not notify an existing open socket to close |
| WebSocket idle timeout | Network-policy inactivity cutoff | May close even while token is valid |
| SSE async timeout | Lifecycle limit of an open response | Does not check access tokens |
| Heartbeat / ping-pong | Whether the transport connection is alive | Does not prove the user is still authorized |
| Max connection age | Connection age cap per application policy | Can force reconnect despite steady traffic |
| Revocation event | Token/user/session revoked | Must reach the owning instance and be enforced |
| Authorization cache TTL | Cache duration of permission decisions | Does not replace token expiry |

**Example 1:** A JWT expires at 10:15, yet a WebSocket opened at 10:00 stays open at 10:45. If the app verified the JWT only at handshake and kept the saved `Principal`, JWT expiration will not automatically sever that socket.

**Example 2:** A WebSocket sends heartbeats every few seconds to beat proxy idle timeouts. That does not constitute re-logging in or extending an access token.

**Example 3:** The browser loses its cookie, yet the old WebSocket remains open. Future HTTP requests will be unauthenticated, while the open socket requires its own revalidation/termination logic.

## 3. WebSocket Starts with an HTTP Handshake

With **Spring WebSocket on Servlet**, establishing a WebSocket begins with an HTTP Upgrade request:

~~~http
GET /ws HTTP/1.1
Host: example.test
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: ...
Cookie: JSESSIONID=...
~~~

The sample shows structure only; real headers include `Origin` and others.

~~~text
HTTP request /ws
      |
      v
Spring Security HTTP filters
      |
      v
Authentication + Principal
      |
      v
HTTP 101 Switching Protocols
      |
      v
WebSocketSession bound to Principal
      |
      +---- SEND messages
      +---- SUBSCRIBE destinations
      +---- receive server events
      +---- heartbeat
      |
      +---- Recheck token exp/role?
              Depends on application and integration
~~~

Spring Framework can transfer the **Principal from `HttpServletRequest`** onto `WebSocketSession`. Once HTTP Upgrade finishes, individual WebSocket frames **are not processed as new HTTP requests**. You cannot turn an already-sent 101 response into HTTP 401 when the token expires.

### 3.1. Browsers Cannot Arbitrarily Add Authorization Headers to WebSocket Handshakes

The native browser **WebSocket constructor** accepts a URL and subprotocols, not arbitrary HTTP `Authorization` headers like `fetch`. Common approaches:
1. **Cookie/session authentication:** cookies are attached by the browser during the handshake; HTTP security authenticates and sets `Principal`.
2. **STOMP `CONNECT` authentication:** STOMP clients attach a token in the `CONNECT` frame; an app-configured **`ChannelInterceptor`** must verify the token and bind the identity.
3. **Short-lived single-use connection ticket:** a protected HTTPS endpoint issues a ticket, and the WebSocket handshake verifies the short-TTL ticket with replay protection.

Never place **long-lived access or refresh tokens in URL query strings**, where URLs leak into proxy logs, monitoring, analytics, and debugging tools. Never assume adding an `Authorization` STOMP header makes Spring Security parse it automatically without configuring an authentication interceptor.

### 3.2. STOMP CONNECT Differs from HTTP Handshake

STOMP is a messaging protocol over WebSocket/SockJS. **`CONNECT`, `SUBSCRIBE`, and `SEND`** are distinct frames:
- `CONNECT` opens the logical messaging session.
- `SUBSCRIBE` registers interest in a destination.
- `SEND` publishes a message to a destination.
- Heartbeats maintain liveness.

When authentication happens via a `CONNECT` token, protect the underlying HTTP endpoint properly, verify the token on the inbound channel, attach `Principal` safely, and **still check expiry and permissions throughout the connection's lifetime**. An authenticated `CONNECT` does not mean every `SUBSCRIBE` topic is allowed.

## 4. Spring Session WebSocket Integration Alters HttpSession Lifecycles

Both extremes are false: **"HttpSession expiration always closes every WebSocket"** and **"WebSocket can never close when HttpSession expires"**.

Without integration, invalidating an HTTP session does not automatically close sockets managed elsewhere in your app. However, **Spring Session WebSocket integration** offers coordinated components:
- **`SessionRepositoryMessageInterceptor`:** updates Spring Session's last-accessed timestamp when inbound WebSocket messages are processed.
- **`WebSocketRegistryListener`:** tracks mappings between session IDs and WebSocket connections.
- **`SessionDestroyedEvent`/`SessionExpiredEvent`** and companions: enable closing matching sockets when an HTTP session is destroyed or expires, when event infrastructure and integration are wired properly.

Thus an actively chatting user keeps **`HttpSession` from going idle**. By contrast, **JWT `exp` is independent of `HttpSession` idleness**: message activity never extends a JWT's `exp` timestamp.

### 4.1. Enforce Absolute Limits, Not Only Idle Timeouts

If policy requires "users stay signed in at most eight hours before re-authenticating," setting **`maxInactiveInterval=20 minutes`** alone fails: steady activity keeps refreshing the session past eight hours. Enforce an **absolute auth age** or **max connection lease** regardless of ongoing heartbeats or session activity.

### 4.2. Logout Across Multiple Replicas

A user logs out on node A while their WebSocket is attached to node B. Node A's local socket map cannot directly close the connection on B. You need a session repository broadcasting destruction events, a pub/sub or revocation bus, a connection registry keyed by session/token/user ID, and proper cleanup on close. Sticky routing does not replace cluster-wide revocation propagation.

## 5. Access Token Expiry and Permissions Must Be Re-Checked

**A JWT validly signed at connect time is not guaranteed valid later.** A user can be disabled or lose roles before `exp`; likewise, the JWT can reach `exp` while WebSocket or SSE remains open.

| Event | Required Action |
| --- | --- |
| Token reaches `exp` | Stop sensitive data, close or force re-auth/reconnect |
| Token revoked before `exp` | Propagate revocation and sever affected streams |
| User account locked | Reject `SEND`/`SUBSCRIBE`, stop private events |
| Role/tenant membership changed | Reauthorize and drop unauthorized subscriptions |
| User logs out | Invalidate session/token and close connections per policy |
| Transport still exchanges ping/pong | Proves liveness only, not authorization |
| Client reconnects with old token | Re-verify; return 401/403 or reject handshake |
| Refresh with new access token | Validate issuer, audience, `exp`, scopes, owner, then reauthorize |

A connection registry should track at minimum:

~~~text
connectionId       = correlation identifier, NOT the bearer secret
userId             = verified identity
tenantId           = authorized tenant
tokenId            = jti or opaque reference ID
authenticatedAt    = timestamp of authentication
tokenExpiresAt     = access credential expiry
maxConnectionUntil = absolute connection deadline
effectiveExpiry    = min(tokenExpiresAt, maxConnectionUntil)
policyVersion      = authorization/revocation version
~~~

**Never store raw bearer tokens in logs**, and never trust a role snapshot taken at connect time forever. Account for verifier clock skew and keep clocks synchronized via NTP.

## 6. Three Strategies for Bounding Permissions on Long-Lived Connections

### 6.1. Close at Deadline

On valid connect, compute **`effectiveExpiry`** = the earlier of token `exp` and max connection age. At the deadline, stop emitting data, close the WebSocket or complete SSE, and require the client to refresh credentials over HTTPS before reconnecting. Pros: clear, deterministic policy. Con: clients must re-subscribe and resume cursors.

### 6.2. Revalidate Before Every Sensitive Message or Event

Before `SEND`, `SUBSCRIBE`, or emitting private outbound events:
1. Check the token/session is neither revoked nor expired.
2. Check the user is not disabled.
3. Check current roles/scopes and record/tenant ownership.
4. Process or emit data only if all checks pass.

Pros: shrinks the exposure window. Cons: lookup overhead and races if permissions change between check and send; check close to the publish point and handle queued frames.

### 6.3. Periodic Checks Combined with Revocation Events

Some systems recheck every N seconds alongside an event bus for user logout/role changes. Every N seconds is only a **polling interval**, not guaranteed instant revocation when networks, schedulers, or queues lag. Measure **`revokedAt → lastSensitiveEventDeliveredAt`** to quantify real enforcement lag and tune against security SLAs.

Do not apply one check interval blindly to all data: public broadcasts and private financial feeds have very different sensitivity profiles.

## 7. SSE: One HTTP Response Carrying Many Events

Spring MVC uses **`SseEmitter`** to keep an HTTP response open and push multiple SSE events. HTTP authentication normally executes at the start of **`GET /events`**, not automatically before each `emitter.send()`.

~~~text
GET /api/events + Bearer token
          |
          v
HTTP auth on initial request
          |
          v
HTTP 200 text/event-stream
          |
          +---- event 1
          +---- event 2
          +---- token expires
          +---- app rechecks expiry
          +---- stop sensitive events
          +---- complete stream
          |
          v
New GET after refresh/authentication
~~~

**You cannot change HTTP 200 into HTTP 401 after headers and streaming have started.** Instead, stop emitting business data, optionally emit a minimal non-sensitive `auth-expired` event, and complete the stream; the subsequent HTTP request will be checked and receive 401.

### 7.1. Native Browser EventSource and Bearer Headers

Native `EventSource` cannot attach arbitrary `Authorization: Bearer` headers like `fetch`. In browsers:
- Cookie/session auth works, provided SameSite, HTTPS, CORS credentials, and data policies are handled properly.
- If bearer headers are mandatory, use **streaming `fetch`** or an SSE client supporting custom headers.
- Never place long-lived tokens in URL query strings just to use native `EventSource`.

The lab in section 10 uses **`curl` + Bearer header** rather than a native EventSource browser client.

### 7.2. Auto-Reconnect Must Not Turn Into a Retry Loop

`EventSource` reconnects automatically when a stream ends. When a token expires, the client must:
1. Call **`EventSource.close()`** to stop retrying the stale stream.
2. Refresh credentials over HTTPS or prompt for re-login.
3. Open a fresh stream with verified credentials.
4. Resume from an authorized event cursor if replay is supported.

**`Last-Event-ID` is not a credential**: a user must never read another tenant's history simply by guessing an ID.

## 8. WebSocket/STOMP: Protect SUBSCRIBE and SEND, Not Only CONNECT

An authenticated user still **must not** subscribe to someone else's order topic. Enforce checks at multiple stages:
- Handshake/`CONNECT`: verify identity.
- `SUBSCRIBE`: verify user/tenant may receive that destination.
- `SEND`: verify permission to execute that action.
- Publish/fan-out: never broadcast sensitive data to unauthorized subscribers.
- Role changes: drop subscriptions or close connections upon revocation.
- Replay: re-check permissions for each historical event.

Spring Security offers **`@EnableWebSocketSecurity`** and **`AuthorizationManager<Message<?>>`** for Spring Messaging/STOMP, yet **authorization rules do not automatically re-run `JwtDecoder` every second**. If tokens expire after `CONNECT`, enforce a lease policy, `ChannelInterceptor`, or max connection age.

Illustrative non-standalone fragment:

~~~java
@Configuration
@EnableWebSocketSecurity
class StompSecurityRules {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {
        messages
            .nullDestMatcher().authenticated()
            .simpDestMatchers("/app/admin/**").hasRole("ADMIN")
            .simpDestMatchers("/app/**").authenticated()
            .simpSubscribeDestMatchers("/user/queue/**").authenticated()
            .anyMessage().denyAll();
        return messages.build();
    }
}
~~~

This fragment requires Spring Security Messaging, WebSocket/STOMP broker configuration, and imports. Add **object-level authorization** per tenant/user in services or brokers, because `authenticated()` or a role does not automatically grant access to every resource ID.

### 8.1. Same Origin and CSRF

Browsers do not enforce Same-Origin Policy on WebSockets the way they do for fetch/XHR. With cookie-based auth, validate allowed origins and enforce CSRF defenses. Spring Security STOMP message security requires a **CSRF token on `CONNECT`** by default to mitigate cross-site WebSocket requests. Origin validation is an extra layer, not authentication: non-browser clients can spoof Origin.

### 8.2. Close Codes

RFC 6455:
- **`1000`**: normal closure.
- **`1008`**: policy violation, suitable when the user no longer satisfies auth policy.
- **`1011`**: server encountered an unexpected condition.
- **`1006`**: reserved to report abnormal closure when no Close frame arrived; **never send `1006`** in a Close frame.

Custom codes like 4401 are application conventions not universally interpreted by clients. Post-handshake, never attempt to send HTTP 401 over WebSocket frames.

## 9. Refresh/Reconnect and Maximum Session Limits

Recommended flow:

~~~text
HTTP login/token issue over HTTPS
        |
        v
Open SSE/WebSocket with valid identity
        |
        v
Server: connection lease + authorization
        |
        +---- message/event: check current permissions
        +---- timer: check token expiry/connection age
        +---- revocation event: close affected connection
        |
        v
Stop outbound sensitive events / close stream
        |
        v
Client renews access credential securely
        |
        v
Reconnect + re-authenticate + resubscribe
        |
        v
Replay events only after checking owner/tenant
~~~

**Never transmit refresh tokens via STOMP broadcasts, SSE data, or URL queries.** If implementing in-band re-auth on an open WebSocket, both sides need an explicit protocol: validate the new token, clear old permissions, reauthorize every active subscription, prevent user B from inheriting user A's subscriptions, and handle races. Usually **close → refresh → reconnect** is much safer to reason about.

Proxies may still drop connections even while tokens remain valid; use backoff with jitter on reconnect to prevent thundering herds. Never treat ping/pong as a trick to extend JWT `exp`.

## 10. Spring Boot MVC SSE Lab: Self-Expiring and Revocable Tokens

This lab runs **Spring Boot 3.3.13 + Java 17 + Spring MVC + Spring Security** using **short-lived opaque tokens**:
- An HTTP-Basic-protected POST issues a random token with a 12-second TTL.
- The SSE GET endpoint accepts a Bearer token and checks it on stream open.
- Before **every tick**, the app rechecks the token.
- Once expired or revoked, the stream **stops ticking** and completes.
- An invalid token on a **new GET** returns 401.
- A unit test uses a fake `Clock` to verify exact expiry boundaries without sleeping.

**This lab runs strictly on localhost HTTP.** Demo Basic credentials are embedded in code; the token registry is in-memory; GET bearer checking is shown directly in the Controller rather than using OAuth2 Resource Server. Never copy this lab security setup to production. Real apps need HTTPS, token verification at security boundaries, TTL-backed shared stores, rate limits, multi-node revocation, and resource-ownership policies.

### 10.1. Directory Structure

~~~text
long-auth-sse/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/longauth/LongAuthSseApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/longauth/TokenRegistryTest.java
~~~

### 10.2. Complete pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>long-auth-sse</artifactId>
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
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/resources/application.yml`**:

~~~yaml
server:
  port: 8080
  servlet:
    session:
      timeout: 15m
spring:
  mvc:
    async:
      request-timeout: 60s
~~~

The 15-minute `HttpSession` timeout **does not** override the 12-second token TTL. The demo's HTTP Basic chain is stateless, while opaque tokens live in their own registry.

### 10.3. Complete Java Source

**`src/main/java/com/example/longauth/LongAuthSseApplication.java`**:

~~~java
package com.example.longauth;

import java.io.IOException;
import java.security.Principal;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.util.Base64;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@SpringBootApplication
public class LongAuthSseApplication {
    public static void main(String[] args) {
        SpringApplication.run(LongAuthSseApplication.class, args);
    }
}

@Configuration
class SecurityConfig {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("demo")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.POST, "/api/dev-token", "/api/revoke"
                ).authenticated()
                // Lab: Bearer checked manually inside GET controller.
                .requestMatchers(HttpMethod.GET, "/api/events").permitAll()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS
                )
            )
            // Lab curl only. Never copy CSRF bypass into browser apps.
            .csrf(csrf -> csrf.ignoringRequestMatchers(
                "/api/dev-token", "/api/revoke"
            ))
            .build();
    }
}

record TokenGrant(String accessToken, long expiresInSeconds) {}

@Service
class TokenRegistry {
    static final long TTL_SECONDS = 12;

    private final Clock clock;
    private final SecureRandom random = new SecureRandom();
    private final Map<String, Lease> tokens = new ConcurrentHashMap<>();

    record Lease(String username, Instant expiresAt) {}

    TokenRegistry(Clock clock) {
        this.clock = clock;
    }

    TokenGrant issue(String username) {
        byte[] raw = new byte[32];
        random.nextBytes(raw);
        String token = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(raw);
        tokens.put(token, new Lease(
                username, clock.instant().plusSeconds(TTL_SECONDS)
        ));
        return new TokenGrant(token, TTL_SECONDS);
    }

    Optional<Lease> lookup(String token) {
        if (token == null || token.isBlank()) {
            return Optional.empty();
        }
        Lease lease = tokens.get(token);
        if (lease == null) {
            return Optional.empty();
        }
        if (!clock.instant().isBefore(lease.expiresAt())) {
            tokens.remove(token, lease);
            return Optional.empty();
        }
        return Optional.of(lease);
    }

    boolean revoke(String token, String username) {
        Lease lease = tokens.get(token);
        return lease != null
                && lease.username().equals(username)
                && tokens.remove(token, lease);
    }
}

@RestController
class StreamController {
    private final TokenRegistry tokens;
    private final ScheduledExecutorService scheduler =
            Executors.newScheduledThreadPool(2);

    StreamController(TokenRegistry tokens) {
        this.tokens = tokens;
    }

    @PostMapping("/api/dev-token")
    TokenGrant issue(Principal principal) {
        return tokens.issue(principal.getName());
    }

    @PostMapping("/api/revoke")
    ResponseEntity<Void> revoke(
            Principal principal,
            @RequestHeader("X-Demo-Token") String token
    ) {
        return tokens.revoke(token, principal.getName())
                ? ResponseEntity.noContent().build()
                : ResponseEntity.notFound().build();
    }

    @GetMapping(path = "/api/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    ResponseEntity<SseEmitter> events(
            @RequestHeader(value = HttpHeaders.AUTHORIZATION,
                           required = false) String authorization
    ) {
        String token = bearerToken(authorization);
        if (tokens.lookup(token).isEmpty()) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .header(HttpHeaders.WWW_AUTHENTICATE, "Bearer")
                    .build();
        }

        SseEmitter emitter = new SseEmitter(60_000L);
        AtomicInteger counter = new AtomicInteger();
        AtomicReference<ScheduledFuture<?>> task = new AtomicReference<>();

        Runnable cancel = () -> {
            ScheduledFuture<?> f = task.get();
            if (f != null) {
                f.cancel(false);
            }
        };
        emitter.onCompletion(cancel);
        emitter.onTimeout(cancel);
        emitter.onError(error -> cancel.run());

        ScheduledFuture<?> future = scheduler.scheduleAtFixedRate(() -> {
            // Revalidate BEFORE every data emission.
            if (tokens.lookup(token).isEmpty()) {
                try {
                    emitter.send(SseEmitter.event()
                            .name("auth-expired")
                            .data("renew-and-reconnect"));
                } catch (IOException | IllegalStateException ex) {
                    cancel.run();
                    return;
                }
                cancel.run();
                emitter.complete();
                return;
            }

            int n = counter.incrementAndGet();
            try {
                emitter.send(SseEmitter.event()
                        .id(Integer.toString(n))
                        .name("tick")
                        .data("count=" + n));
            } catch (IOException | IllegalStateException ex) {
                // MVC/container handles I/O errors in async responses.
                cancel.run();
            }
        }, 1, 1, TimeUnit.SECONDS);

        task.set(future);
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .cacheControl(CacheControl.noStore())
                .body(emitter);
    }

    private static String bearerToken(String authorization) {
        if (authorization == null
                || !authorization.startsWith("Bearer ")) {
            return null;
        }
        String value = authorization.substring("Bearer ".length());
        return value.isBlank() ? null : value;
    }

    @PreDestroy
    void shutdown() {
        scheduler.shutdownNow();
    }
}
~~~

### 10.4. Code Breakdown

1. **`TokenRegistry`** generates 32-byte opaque tokens with `SecureRandom`, storing username and `expiresAt` in a `ConcurrentHashMap`. Tokens are Base64URL-encoded, not JWTs.
2. **`TTL_SECONDS = 12`** measures expiry from **token issuance**, not from the first SSE tick.
3. **`lookup`** checks whether the token exists and precedes `expiresAt`; expired records are evicted on lookup.
4. **`revoke`** lets only the token-owning username revoke it; the POST endpoint requires Basic auth.
5. **`GET /api/events`** is intentionally `permitAll` in the Spring Security filter so the Controller can demonstrate mid-stream Bearer revalidation. Production should use OAuth2 Resource Server or a proper authentication filter at the HTTP boundary.
6. **`SseEmitter(60_000L)`** sets a 60-second async timeout, while the token lasts only 12 seconds. Upon expiry or revocation, the server stops ticking and completes the stream.
7. **`onCompletion`/`onTimeout`/`onError`** cancel the scheduled task. On `IOException` caused by client disconnect, do not call `completeWithError`; Spring MVC/Servlet async listeners handle the I/O error.
8. **`@PreDestroy`** shuts down the scheduler cleanly on exit.

**Lab limitations:** issued tokens that are never looked up stay in RAM until swept; there is no shared store/eviction/rate limiting, multi-replica support, TLS, or per-tenant sensitive data. With many SSE clients, Servlet writes can block and two scheduler threads will not suffice. Production requires connection caps, bounded queues, an event bus, and monitoring.

**Race condition to keep in mind:** if a token is revoked between `lookup` and `send`, one extra tick could slip through. Checking every second does not give zero-latency revocation; sensitive policies must check closer to publish time and handle queued events.

### 10.5. Unit Test with a Fake Clock Instead of Sleep

**`src/test/java/com/example/longauth/TokenRegistryTest.java`**:

~~~java
package com.example.longauth;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class TokenRegistryTest {
    static final class AdjustableClock extends Clock {
        private Instant now = Instant.parse("2026-01-01T00:00:00Z");

        @Override
        public Instant instant() {
            return now;
        }

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return Clock.fixed(now, zone);
        }

        void advanceSeconds(long seconds) {
            now = now.plusSeconds(seconds);
        }
    }

    @Test
    void expiryAndRevocation() {
        AdjustableClock clock = new AdjustableClock();
        TokenRegistry registry = new TokenRegistry(clock);

        TokenGrant first = registry.issue("alice");
        assertTrue(registry.lookup(first.accessToken()).isPresent());

        assertFalse(registry.revoke(first.accessToken(), "bob"));
        assertTrue(registry.lookup(first.accessToken()).isPresent());

        assertTrue(registry.revoke(first.accessToken(), "alice"));
        assertTrue(registry.lookup(first.accessToken()).isEmpty());

        TokenGrant second = registry.issue("alice");
        assertTrue(registry.lookup(second.accessToken()).isPresent());

        clock.advanceSeconds(12);
        assertTrue(registry.lookup(second.accessToken()).isEmpty());
    }
}
~~~

The test uses a fake `Clock` to verify exact **expiry boundaries** and username-scoped revocation without `Thread.sleep`. It does not replace SSE/network lifecycle integration tests.

### 10.6. Build, Run, and Observe

Requires Java 17+, Maven, and free port 8080, inside `long-auth-sse`:

~~~bash
mvn test
mvn package
java -jar target/long-auth-sse-1.0.0.jar
~~~

**Invalid token:**

~~~bash
curl -i -N -H "Authorization: Bearer invalid" http://localhost:8080/api/events
~~~

Expect **HTTP 401 Unauthorized**; no valid stream starts.

**Linux/macOS Bash with curl and Python 3**:

~~~bash
TOKEN=$(curl -fsS -u demo:demo-pass -X POST http://localhost:8080/api/dev-token | python3 -c 'import json,sys; print(json.load(sys.stdin)["accessToken"])')
curl -i -N -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/events
~~~

**Windows PowerShell (one command per line, using `curl.exe`):**

~~~powershell
$grant = curl.exe -s -u demo:demo-pass -X POST http://localhost:8080/api/dev-token | ConvertFrom-Json
curl.exe -i -N -H "Authorization: Bearer $($grant.accessToken)" http://localhost:8080/api/events
~~~

Real tokens are random strings, so token stdout varies. SSE events appear similarly to:

~~~text
id:1
event:tick
data:count=1

id:2
event:tick
data:count=2

event:auth-expired
data:renew-and-reconnect
~~~

This is a **structural example**, not byte-for-byte stdout: the number of ticks depends on elapsed time between issuance and stream open, scheduling, and buffering. The token expires **12 seconds after the POST issue**, not after 12 ticks.

**Testing revocation while SSE is open (Bash):**

~~~bash
TOKEN=$(curl -fsS -u demo:demo-pass -X POST http://localhost:8080/api/dev-token | python3 -c 'import json,sys; print(json.load(sys.stdin)["accessToken"])')
curl -sN -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/events &
STREAM_PID=$!
sleep 2
curl -i -u demo:demo-pass -X POST -H "X-Demo-Token: $TOKEN" http://localhost:8080/api/revoke
wait "$STREAM_PID"
~~~

A successful POST revoke returns **HTTP 204 No Content**; the next token check stops ticks and completes the stream. This does not guarantee zero-millisecond latency.

**Note:** Basic credentials and Bearer tokens can linger in shell history or process listings. Run only with dummy credentials on localhost; never use production credentials or share tokens externally.

## 11. From Lab to Production Spring Security

An API backed by OAuth2 Resource Server should validate Bearer tokens via Spring Security on **the initial HTTP request**:

~~~java
// Fragment; requires OAuth2 Resource Server starter and issuer/JWK config.
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/events").authenticated()
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

This is an **illustrative fragment** that cannot be pasted directly into the opaque-token lab without switching authentication modes. Even after JWT validation on HTTP GET, the stream still needs **expiry/revocation handling** while emitting events.

### 11.1. Never Rely on SecurityContextHolder Working on Every Thread

Spring MVC/Security uses `ThreadLocal` in many contexts. Scheduled SSE callbacks often run on different threads; **`SecurityContextHolder`** inside a callback does not necessarily hold the original request's `Principal`. Store the verified identity safely inside the connection lease, then query an authorization service or configure proper framework context propagation. Never copy raw bearer tokens into global `ThreadLocal`s.

### 11.2. Permissions per Subscription and Event

If a user still holds a valid token yet loses tenant membership, stop emitting that tenant's data immediately. Apps should:
- Check tenant/owner on `SUBSCRIBE` and before publishing sensitive data.
- Drop subscriptions when policy versions change.
- Never treat `Last-Event-ID` as authentication.
- Authorize permissions when replaying missed events.
- Never broadcast private events to public broker destinations.

## 12. Operations and Infrastructure Protection

**Connection registry:** register on open, clean up on timeout/error/close, cap connections per user/tenant/IP; never retain `SseEmitter`/`WebSocketSession` in unbounded maps.

**SSE/WS networking:** proxies and ingresses enforce their own idle timeouts, header limits, WebSocket Upgrade forwarding, and connection lifetimes. Use heartbeats for liveness without mistaking them for auth refreshes.

**Reconnection:** cap retries and use backoff with jitter so thousands of clients do not storm reconnects simultaneously after a deploy or auth outage.

**Resource quotas:** monitor active connections, thread pools, queued frames, slow-consumer buffers, scheduler tasks, and memory; Servlet writes can block.

**Token security:** never send refresh tokens in URLs or broadcast messages, never log JWTs/`JSESSIONID`, enforce HTTPS/WSS, validate signature/issuer/audience/`exp`, and never use trust-all TLS.

**Multi-node:** propagate logout/revoke/role-change events to nodes holding live connections, use TTL-backed shared session/revocation stores, and test node failures.

**Observability:** track token-expiry closes, denied subscriptions, revoke-to-last-event latency, reconnect rates, and async exceptions statistically; never put credentials in metric labels.

## 13. Common Troubleshooting Table

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| JWT expired yet socket keeps receiving data | Checked only at handshake | Add lease, revalidation, and socket closure |
| HTTP logout yet WebSocket remains open | Session destruction not wired to connections | Spring Session integration or revocation bus |
| STOMP heartbeats keep HTTP session alive | `SessionRepositoryMessageInterceptor` updates last-accessed time | Enforce absolute max age and re-auth |
| User lost role yet topic keeps sending | Subscription never re-evaluated | Per-message/per-resource authorization |
| Native WebSocket cannot send custom Bearer header | Browser API limitation | Cookie+Origin+CSRF or STOMP CONNECT auth |
| Native EventSource cannot send Bearer header | Does not support arbitrary headers | Cookie auth or streaming fetch |
| SSE already 200 cannot turn into 401 | Headers already committed | Complete stream; return 401 on next GET |
| EventSource loops infinitely with expired token | Client fails to call `close()` and refresh | Auth state machine and backoff |
| WebSocket code 1006 | Abnormal connection loss without close frame | Check proxy/network; never send frame 1006 |
| WebSocket code 1008 | Policy violation | Review token/role/owner policy |
| Revoked on node A, node B stream keeps sending | Unsynchronized local state | Shared store/pubsub + lease |
| Many SSE clients exhaust threads | Blocking Servlet writes or weak scheduler | Caps, executor tuning, slow-client policy |
| `Last-Event-ID` reads wrong tenant | Replay skipped reauthorization | Verify owner/tenant per event |
| Token expiry drifts across nodes | NTP/clock skew/caching | Synchronize clocks and policies |
| Refreshed as user B yet still sees A's data | Kept old subscriptions | Disconnect, re-authenticate, re-subscribe |

## 14. Self-Assessment Exercises

**1.** A JWT has a 15-minute `exp`, yet a previously opened WebSocket stays alive for 2 hours. Will the framework always close it automatically?  
**Answer:** No. Verify integration and enforce expiry inside the connection lifecycle.

**2.** Does a STOMP heartbeat prove the user still holds `ROLE_ADMIN`?  
**Answer:** No, it measures only liveness.

**3.** What can Spring Session WebSocket integration do?  
**Answer:** Refresh HTTP session last-accessed time on inbound messages and close sockets on session destruction events when integration and repository events are wired properly.

**4.** Can an actively engaged user stay logged in past an `HttpSession` idle timeout?  
**Answer:** Yes. Enforcing a hard cap requires an absolute max session/connection age.

**5.** SSE already returned HTTP 200, and the token expires. Can you change that stream's status to 401?  
**Answer:** No. Stop data, close the stream, and enforce auth on the next request.

**6.** Can native `EventSource` or `WebSocket` APIs attach arbitrary `Authorization` headers like `fetch`?  
**Answer:** No. Use cookie/session designs or a client/protocol mechanism designed to carry tokens.

**7.** Can an authenticated user freely `SUBSCRIBE` to another tenant's topic?  
**Answer:** Not if access control is enforced—check owner/tenant permissions.

**8.** Which close code is appropriate when closing a WebSocket for policy violation? Can you send 1006?  
**Answer:** 1008 is appropriate; 1006 is reserved and must never be sent in a Close frame.

**9.** User logs out on node A while their socket sits on node B—what must happen?  
**Answer:** Propagate revocation/session destruction via a shared store/event bus, or combine short leases with periodic rechecks.

**10.** Can `Last-Event-ID` replace a token?  
**Answer:** No. It is only a cursor, and replay must still enforce authorization.

**11.** Does checking tokens every second guarantee instant revocation?  
**Answer:** No; scheduler delay, propagation lag, and check-before-send races still exist.

**12.** If a token has an `exp` and the connection already authenticated, what else is needed?  
**Answer:** Connection leases, revalidation, and halting private events when no longer valid.

## 15. Review Checklist

- [ ] Separate token expiry, HTTP session idle timeout, connection lifetime, and authorization.
- [ ] Know exactly where authentication occurs: handshake / SSE GET / STOMP CONNECT.
- [ ] Never assume JWT `exp` closes sockets automatically.
- [ ] Enforce connection leases or revalidation appropriate to data sensitivity.
- [ ] Recheck `SEND`, `SUBSCRIBE`, publish, tenant/owner, and replay.
- [ ] Propagate logout/revocation across multiple nodes.
- [ ] Enforce max connection age independently of heartbeats.
- [ ] Cookie-authenticated WebSockets enforce `Origin` and CSRF properly.
- [ ] Never place long-lived access/refresh tokens in query strings or logs.
- [ ] SSE/client refresh and reconnect implement `close()` and backoff.
- [ ] Clean up scheduled tasks, connection registries, and broker subscriptions.
- [ ] Measure revoke-to-last-event latency and test mid-stream token expiration.

## 16. Conclusion

**An open network connection does not mean authorization remains valid.** Spring Security can authenticate the HTTP handshake or SSE GET; Spring Session can coordinate WebSocket and HTTP session lifecycles. Yet **token `exp`, logouts, revocations, and role/tenant changes** require explicit policies throughout the time a connection remains open.

Sound design follows: **authenticate at connect → record verified identity/lease → revalidate expiry and permissions where needed → halt data/close on policy failure → refresh and reconnect safely**. Heartbeats keep the connection alive, not the user's permissions.

## Official References

- Spring Security — WebSocket Security: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
- Spring Framework — STOMP Authentication: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html
- Spring Framework — Token-based STOMP Authentication: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html
- Spring Framework — STOMP Authorization: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html
- Spring Session — WebSocket Integration: https://docs.spring.io/spring-session/reference/web-socket.html
- Spring Framework — MVC Async/SseEmitter: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- RFC 6455 — WebSocket Close Status Codes: https://www.rfc-editor.org/rfc/rfc6455#section-7.4
- MDN — Server-Sent Events: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
- MDN — WebSocket API: https://developer.mozilla.org/en-US/docs/Web/API/WebSocket
