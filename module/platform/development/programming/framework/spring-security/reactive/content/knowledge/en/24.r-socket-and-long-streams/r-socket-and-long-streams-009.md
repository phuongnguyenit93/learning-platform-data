# Identity, Cancellation, and Token Expiration in Long-Lived SSE or Flux

## 1. Problem statement

A **Spring WebFlux** API returns data over **Server-Sent Events (SSE)** or a `Flux<T>` lasting minutes or hours. The client opens a connection with a Bearer access token; Spring Security verifies the token and permits the subscription. At minute 10, the token expires; at minute 12, the account is locked; at minute 15, the browser closes the tab. What happens to the emitted data, the identity held inside the publisher, and upstream resources?

Three distinct questions must be addressed separately:

1. **Identity:** which user created the subscription, who is allowed to receive each event, which tenant is permitted, and where does `SecurityContext` live when a `Flux` switches schedulers?
2. **Unsubscription / cancellation:** do client `EventSource.close()`, `AbortController.abort()`, RSocket `CANCEL`, proxy disconnects, or subscriber `cancel()` actually release listeners, broker consumers, connections, timers, and caches?
3. **Token expiration/revocation:** is a JWT that was valid when opening the stream automatically re-checked by Spring Security throughout the stream? When re-authentication is needed, how do we stop the stream, what signal do we emit, and how do we reconnect safely?

The goal of this lesson is to understand **HTTP SSE**, **Reactor subscriptions**, and **RSocket request-stream** accurately, rather than assuming they share the same lifecycle mechanism. This lesson provides:

- The flow from Bearer authentication to `ReactiveSecurityContextHolder`.
- Comparison between authorization at stream start vs. periodic/per-event permission checks.
- How to stop events after `exp` yourself and how to check rapid permission revocation.
- Cancellation mechanics, `doFinally(SignalType.CANCEL)`, `Flux.usingWhen`, heartbeats, and backpressure management.
- A **Java 17+** pure-JDK example to test lifecycle policies, and a **Spring Boot 4.1.2 WebFlux SSE** application with a JWT Resource Server.
- RSocket security **SETUP vs. per-request metadata**, plus notes on long streams and multiplexed connections.
- Testing 200/401/403, token expiry, cancellation, reconnect, tenant isolation, and logging.

**Core principle:** "Authenticated at the start of an HTTP request" **does not** equate to "token remains active and permissions unchanged at every moment of an infinite stream." If you need that guarantee, you must **design continuous authorization or lifecycle limits** rather than relying solely on `.authenticated()`.

## 2. Distinguishing request, connection, subscription, and event

| Concept | Start point | End point | When does authentication normally happen? |
| --- | --- | --- | --- |
| SSE HTTP request | Client sends `GET` with `Accept: text/event-stream` | Connection closes or response completes/errors | WebFlux Security filters authenticate the request **before** the controller |
| Reactor `Flux` subscription | A subscriber actually subscribes | `onComplete`, `onError`, or `cancel()` | According to how the app puts `Authentication` into Reactor Context; does not re-verify JWT on every `onNext` |
| SSE event | `event:... data:...` on HTTP response | One flushed message | Does not trigger a new authentication request per event |
| RSocket `SETUP` | Opens RSocket connection | Connection closes | Can authenticate at setup |
| RSocket `REQUEST_STREAM` | One logical stream on a connection | Stream completes/errors/CANCEL | Can authenticate per request or inherit setup identity, depending on configuration |
| RSocket `REQUEST_CHANNEL` | Bidirectional stream | Both directions complete/cancel per protocol | Depends on metadata/authorization rules and each request |

### 2.1. Why distinguish them?

In SSE, **one HTTP GET** can have thousands of `onNext` signals yet only one default HTTP Bearer authentication. The `Authorization` header is not resent before each event.

In RSocket, a single **TCP/WebSocket connection** can carry many logical requests, even for multiple users if a gateway multiplexes. Authenticating only at `SETUP` may fit a single-user connection, but is dangerous if the connection is shared across other users.

In Reactor, the same `Flux` can be created once and subscribed to multiple times. Storing a user in a **static field/global mutable variable** can leak one person's data into another's subscription. The right identity must be bound to the **subscriber/request context or a subscription-local immutable snapshot**.

## 3. SSE from HTTP Bearer to Reactor Context

~~~text
Client                               Spring WebFlux API
   |                                        |
   | GET /api/stream                        |
   | Authorization: Bearer <access-token>    |
   |--------------------------------------->|
   |                            AuthenticationWebFilter
   |                            ReactiveJwtDecoder:
   |                              verify signature, iss, aud,
   |                              exp / nbf, allowed algorithm
   |                            JwtAuthenticationToken
   |                            SecurityWebFilterChain:
   |                              require SCOPE_stream.read
   |                            ReactiveSecurityContextHolder
   |                            controller returns Flux<SSE>
   |<---------------------------------------| event seq=0
   |<---------------------------------------| event seq=1
   |<---------------------------------------| event seq=2
   |             ...                        |
   |                                        |
   |      client closes / aborts            |
   |----------------X---------------------->|
   |                            cancel subscription upstream
   |                            release resources (doFinally)
~~~

Spring Security reactive stores the security context via **Reactor Context** per subscriber, rather than treating it as a global immutable `ThreadLocal` on the Netty event loop. `ReactiveSecurityContextHolder.getContext()` returns `Mono<SecurityContext>` when subscribed inside a reactive pipeline with the proper context.

### 3.1. Example reading the principal from Reactor Context

~~~java
Mono<String> currentUserName =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);
~~~

This is a **snippet** inside a Spring reactive pipeline, not a standalone program. It reads the user of **the current subscription**. If you run a publisher via a manual `subscribe()` outside the pipeline or push it onto a scheduler/task queue without propagating the proper context, you may see the context missing.

**Do not use:**

~~~java
// ANTI-PATTERN in reactive code:
Authentication a =
        SecurityContextHolder.getContext().getAuthentication();
~~~

Servlet's ThreadLocal `SecurityContextHolder` is not the primary way to obtain `Authentication` for WebFlux Reactor Context. Do not assume every `publishOn` loses Reactor Context; Reactor Context follows the subscriber properly inside a Reactor pipeline. Risk arises when **detaching from the subscription**, using external callbacks, calling `subscribe()` manually, or mixing other thread/context-propagation mechanisms without a contract.

### 3.2. @AuthenticationPrincipal is a snapshot when the handler runs

In a JWT HTTP resource server, a controller may receive:

~~~java
@GetMapping(value = "/api/stream",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<String>> stream(
        @AuthenticationPrincipal Jwt jwt) {
    // jwt has already been verified by the resource server decoder for this HTTP request.
    return /* a Flux created by the controller */;
}
~~~

This snippet illustrates injection. `Jwt` holds the claims/token timestamps **from the current authentication**. If the user's role is revoked mid-stream, the `Jwt` object **does not mutate by itself**. `Authentication` is a request snapshot unless the application actively consults a fresh policy store.

### 3.3. Scope, tenant, and ownership

Streams with sensitive events often need all three layers:

1. HTTP route requires `SCOPE_stream.read`.
2. Verified JWT claim `tenant_id` must match the tenant/resource requested by the user.
3. Each item received from the broker/database must be filtered by tenant and object-level authorization.

A shared `Flux` emitting events for all tenants and filtering **after serialization** is a dangerous design. Tenant filtering must occur before sensitive data enters an unauthorized channel/subscriber; even better, queries/broker subscriptions should be scoped at the source.

## 4. Can a token expire mid-SSE?

**Yes, and it is very easy to miss.** In a typical JWT Resource Server configuration:

- When the HTTP request starts, `ReactiveJwtDecoder` verifies signature, `iss`, `exp`, `nbf`, and configured validators.
- `SecurityWebFilterChain` checks authorization rules for the request.
- The controller returns `Flux<ServerSentEvent<?>>` and the response starts streaming.
- For each subsequent `onNext`, **there is no default mechanism** to re-invoke the JWT decoder just because the clock passed `exp`.

Thus a stream started at 09:59:59 with a token expiring at 10:00 can **keep sending events after 10:00** if you do not bound the stream or check authorization continuously. Token expiry **does not automatically emit a Reactor `cancel()`** to the subscription.

### 4.1. Three feasible strategies

| Strategy | Behavior | When to use |
| --- | --- | --- |
| **A. Verify only at stream open** | Stream may continue past token expiry | Short streams, low-sensitivity data, policy accepts the lease |
| **B. Cut stream at `exp` or lease deadline** | Emits no events past a server-chosen limit; client must re-auth/reconnect | Recommended baseline for long bearer streams |
| **C. Check both `exp` and current permissions** | Every event or every few seconds queries permission/account/revocation, stops on deny | Sensitive data, where account locks/permission revocations must take effect quickly |

No single duration fits every system. If the permission revocation SLO is 5 seconds, checking every 60 seconds falls short; conversely, querying a database on **every event** in a stream of tens of thousands of events/sec can cause load spikes. Design should account for propagation delay, cache TTL, interval, retry budgets, and fail-closed behavior.

### 4.2. Token `exp` differs from current data access permissions

`exp` is the cryptographic token validity limit. If a user is locked at the IdP or loses tenant permissions, an already-issued JWT can still pass signature/exp checks until it expires; a local-only resource server **does not automatically see** revocation. Re-checking `exp` per event **only addresses expiry**, not role/account revocation. You need a dedicated backend policy: membership store, token version, denylist, introspection, or event-driven invalidation.

### 4.3. Stream deadline and token deadline

You can set:

~~~text
streamDeadline = min(
    jwt.expiresAt,
    subscriptionStart + maximumStreamLease,
    policyRevocationDeadline (if known)
)
~~~

This is a policy formula. A service may cap every stream to a maximum of 5 minutes even if the JWT has 1 hour left, avoiding infinite connections and allowing credentials to be rechecked. If a token lacks `exp`, the **server policy/validator** must decide; never assume "never expires" and open a permanent stream.

## 5. Cancellation: stopping event receipt differs from logout

Clients can stop SSE via:

~~~javascript
const source = new EventSource("/api/stream");
source.addEventListener("tick", (e) => console.log(e.data));

// When the component/page no longer needs the stream:
source.close();
~~~

On clients using `fetch()` streaming, cancel via `AbortController.abort()`. With Reactor clients, call `Disposable.dispose()` / subscription `cancel()`. In RSocket `REQUEST_STREAM`, the receiver sends a `CANCEL` frame.

**Cancellation is neither logout nor token revocation.** It stops **one subscription/stream**; it does not clear server-wide `OAuth2AuthorizedClient` entries, revoke the JWT at the IdP, or close all other streams of the same user.

### 5.1. doFinally distinguishes COMPLETE / ERROR / CANCEL

~~~java
Flux<Long> ticks =
        Flux.interval(Duration.ofSeconds(1))
                .doFinally(signal -> {
                    if (signal == SignalType.CANCEL) {
                        metrics.incrementCancelled();
                    }
                });
~~~

This snippet assumes `metrics` is an app dependency. `doFinally` runs when the publisher completes, errors, or is cancelled; signals include `ON_COMPLETE`, `ON_ERROR`, or `CANCEL`. When a stream is closed by the client and detected by transport, Spring WebFlux usually cancels the upstream publisher. **Immediate detection is not guaranteed** if no data/heartbeat is written and proxies have not reported disconnect.

### 5.2. Heartbeats help detect dead connections

Spring Framework WebFlux recommends **sending periodic data** when streaming, such as SSE comment-only heartbeats:

~~~text
: ping

event: tick
data: 42

: ping

~~~

SSE events require a blank line to terminate. Heartbeats need not contain user tokens, subjects, tenants, or sensitive data. Heartbeat cadence should align with reverse proxy/ingress read timeouts, NAT, and connection counts. Do not send high-frequency heartbeats across hundreds of thousands of connections.

### 5.3. Cancellation must release upstream resources

If a stream uses a broker subscription or database tailing cursor, real cleanup is needed:

~~~java
// Conceptual pattern. resourceFactory / consume / closeAsync
// must be defined for the message broker in use.
Flux.usingWhen(
        resourceFactory.openSubscriber(tenant),
        subscriber -> consume.events(subscriber),
        subscriber -> subscriber.closeAsync(),
        (subscriber, error) -> subscriber.closeAsync(),
        subscriber -> subscriber.closeAsync());
~~~

This is an **architectural snippet**, not a standalone file; `resourceFactory`, `consume`, and `closeAsync` belong to the app's adapter. `Flux.usingWhen` has cleanup branches on complete, error, and **cancel**. Choose an appropriate API if cleanup is blocking (offload to boundedElastic with timeouts), never calling `block()` on the Netty event loop.

A `Flux.create`/`Flux.push` listener attaching callbacks to an SDK must also use `sink.onCancel(...)`/`onDispose(...)` to remove listeners, stop consumers, and release handles. `doFinally` recording a metric **does not automatically** close a connection unless you implement closing.

### 5.4. Never manually subscribe inside a controller

~~~java
// ANTI-PATTERN: detaches upstream from HTTP response cancellation.
Flux<Event> source = broker.events();
source.subscribe(event -> sendSomewhere(event));
return Flux.never();
~~~

If the client closes the browser, the subscription created by `source.subscribe(...)` can keep running because it is not linked to the HTTP stream. Instead **return the composed publisher** so WebFlux manages subscribe/cancel; for external non-Reactor resources, register corresponding cleanup hooks.

## 6. Standalone Java 17: evaluating policy across points in time

Before involving an IdP or Spring, run a Java 17 program simulating a **verified identity** and 4 critical decisions: right tenant, right scope, token not expired, current permission not revoked.

The program below assumes upstream authentication **already verified the JWT**. It **is not a JWT decoder** and has no signing keys; never use raw client claims/headers as `VerifiedIdentity`.

Create `StreamAccessPolicyDemo.java`:

~~~java
import java.time.Instant;
import java.util.Set;

public final class StreamAccessPolicyDemo {

    enum Decision {
        ALLOW, UNKNOWN_TENANT, WRONG_TENANT,
        MISSING_SCOPE, TOKEN_EXPIRED, ACCESS_REVOKED
    }

    record VerifiedIdentity(String tenant,
                            String subject,
                            Set<String> authorities,
                            Instant expiresAt) {
    }

    private StreamAccessPolicyDemo() {
    }

    static Decision evaluate(
            String routeTenant, VerifiedIdentity identity,
            Instant now, boolean currentPermission) {

        if (!Set.of("tenant-a", "tenant-b").contains(routeTenant)) {
            return Decision.UNKNOWN_TENANT;
        }
        if (!routeTenant.equals(identity.tenant())) {
            return Decision.WRONG_TENANT;
        }
        if (!identity.authorities().contains("SCOPE_stream.read")) {
            return Decision.MISSING_SCOPE;
        }
        if (identity.expiresAt() == null
                || !now.isBefore(identity.expiresAt())) {
            return Decision.TOKEN_EXPIRED;
        }
        if (!currentPermission) {
            return Decision.ACCESS_REVOKED;
        }
        return Decision.ALLOW;
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2026-11-07T00:00:00Z");
        VerifiedIdentity reader = new VerifiedIdentity(
                "tenant-a", "user-42",
                Set.of("SCOPE_stream.read"), start.plusSeconds(10));

        VerifiedIdentity noScope = new VerifiedIdentity(
                reader.tenant(), reader.subject(), Set.of(),
                reader.expiresAt());

        System.out.println("at_open="
                + evaluate("tenant-a", reader, start, true));
        System.out.println("at_second_9="
                + evaluate("tenant-a", reader,
                        start.plusSeconds(9), true));
        System.out.println("at_second_10="
                + evaluate("tenant-a", reader,
                        start.plusSeconds(10), true));
        System.out.println("revoked_early="
                + evaluate("tenant-a", reader,
                        start.plusSeconds(2), false));
        System.out.println("tenant_b="
                + evaluate("tenant-b", reader, start, true));
        System.out.println("scope_missing="
                + evaluate("tenant-a", noScope, start, true));
        System.out.println("unknown_route="
                + evaluate("tenant-x", reader, start, true));
    }
}
~~~

Run **without Spring/Maven/IdP**:

~~~bash
javac StreamAccessPolicyDemo.java
java StreamAccessPolicyDemo
~~~

**Stdout determined by code:**

~~~text
at_open=ALLOW
at_second_9=ALLOW
at_second_10=TOKEN_EXPIRED
revoked_early=ACCESS_REVOKED
tenant_b=WRONG_TENANT
scope_missing=MISSING_SCOPE
unknown_route=UNKNOWN_TENANT
~~~

Learning points:

- The exact instant of `expiresAt` is treated as expired because the condition is `now.isBefore(exp)`, **not** `now <= exp`.
- Permission revocation is simulated via `currentPermission=false`, not automatically derived from `exp`.
- `UNKNOWN_TENANT`/`WRONG_TENANT` outcomes block cross-tenant access; real runtimes must also verify issuer/audience and object ownership.
- Fixed `Instant` makes tests deterministic without waiting for wall-clock time.
- There is no HTTP/WebSocket/RSocket in this plain program; it tests policy only, not pretending to test protocol.

## 7. Spring Boot 4.1.2 WebFlux SSE application

The complete sample below uses a **real JWT Resource Server**. Do not embed secrets in source, do not forge fake tokens to become "authenticated," and do not disable security. The API has:

- `GET /healthz`: public health check.
- `GET /api/stream`: requires `SCOPE_stream.read` and a valid IdP-signed JWT.
- `Flux<ServerSentEvent<String>>` emitting a tick every second.
- **Self-terminates the stream** when the clock reaches token `exp` (without waiting for a new request).
- `doFinally` counts `CANCEL`, `ON_ERROR`, and `ON_COMPLETE` terminations with minimal token-free logs.
- Each subscriber has its own `Flux`; no mutable global user principal.

**Intentional limitation:** the sample checks expiry, and **does not automatically check IdP revocation/role changes while the stream is open**. Later sections guide adding dynamic checks for systems requiring rapid revocation.

### 7.1. pom.xml

Create Maven project `reactive-sse-lifecycle`, group `com.example`, Java 17+, `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-sse-lifecycle</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-oauth2-resource-server</artifactId>
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

Spring Boot 4 uses the Resource Server starter name `spring-boot-starter-security-oauth2-resource-server`. Let the Spring Boot BOM manage Framework, Security, and Reactor versions; never mix `spring-boot-starter-webmvc` or Servlet `HttpSecurity` into WebFlux.

### 7.2. application.properties

Create `src/main/resources/application.properties`:

~~~properties
server.port=8080

spring.security.oauth2.resourceserver.jwt.issuer-uri=${DEMO_JWT_ISSUER}
spring.security.oauth2.resourceserver.jwt.audiences=${DEMO_JWT_AUDIENCE}
~~~

When saved, `${...}` represents **Spring property placeholders** starting with `$`. Both environment variables must be supplied by the IdP operator; no fake issuer/credential has real security value.

- `DEMO_JWT_ISSUER`: HTTPS issuer of access tokens.
- `DEMO_JWT_AUDIENCE`: resource identifier for the SSE API, e.g. `events-api` issued by the IdP.
- Test tokens must carry scope `stream.read` so the default mapper creates `SCOPE_stream.read`.
- Tokens must have `exp`; the sample intentionally rejects tokens missing `exp`.
- If the app is multi-tenant, add a tenant validator and per-event ownership as in section 9, rather than relying only on scope.

### 7.3. Complete Java application

Create `src/main/java/com/example/stream/SseLifecycleApplication.java`:

~~~java
package com.example.stream;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

@SpringBootApplication
@EnableWebFluxSecurity
public class SseLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(SseLifecycleApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/healthz").permitAll()
                        .pathMatchers("/api/stream")
                                .hasAuthority("SCOPE_stream.read")
                        .anyExchange().denyAll())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }

    @RestController
    static class Endpoints {
        private static final Logger LOG =
                LoggerFactory.getLogger(Endpoints.class);

        @GetMapping("/healthz")
        Mono<Map<String, String>> healthz() {
            return Mono.just(Map.of("status", "UP"));
        }

        @GetMapping(value = "/api/stream",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
        Flux<ServerSentEvent<String>> stream(
                @AuthenticationPrincipal Jwt jwt) {

            Instant expiresAt = jwt.getExpiresAt();
            if (expiresAt == null
                    || !Instant.now().isBefore(expiresAt)) {
                // Before streaming starts: HTTP status still mutable.
                throw new ResponseStatusException(
                        HttpStatus.UNAUTHORIZED,
                        "Token expiry is required");
            }

            // Captured only for this request; never static/shared.
            // Do not print the token or sensitive claims.
            return Flux.interval(
                            Duration.ZERO, Duration.ofSeconds(1))
                    .takeWhile(seq ->
                            Instant.now().isBefore(expiresAt))
                    .map(seq -> ServerSentEvent.<String>builder()
                            .id(Long.toString(seq))
                            .event("tick")
                            .data("counter=" + seq)
                            .build())
                    .doFinally(signal -> {
                        // Production: use bounded metrics, not raw tokens.
                        if (signal == SignalType.CANCEL) {
                            LOG.debug("sse_closed=cancel");
                        } else if (signal == SignalType.ON_COMPLETE) {
                            LOG.debug("sse_closed=complete");
                        } else if (signal == SignalType.ON_ERROR) {
                            LOG.warn("sse_closed=error");
                        }
                    });
        }
    }
}
~~~

**Why this code matters:**

1. `ServerHttpSecurity` requires `SCOPE_stream.read` right on receiving the request; the JWT is verified by Spring Security Resource Server before the controller.
2. `@AuthenticationPrincipal Jwt` is the verified principal for this request; never manually parse `Authorization` in the controller.
3. `getExpiresAt()` is the `Instant` of the verified JWT. Missing or already expired before creating the stream: returns an authentication error before committing the response.
4. `Flux.interval(Duration.ZERO, Duration.ofSeconds(1))` emits one tick per second. It uses a Reactor scheduler and does not block the Netty event loop.
5. `takeWhile(seq -> Instant.now().isBefore(expiresAt))` checks the time **before emitting each tick**; when the predicate becomes false, the stream completes and the timer subscription is cancelled. The cutoff window is roughly one tick interval plus scheduling delay; nanosecond-exact closure at `exp` is not guaranteed.
6. `.id(Long.toString(seq))` produces an illustrative SSE ID, **not an authorization token**; never use the ID as a permission.
7. `doFinally` distinguishes termination reasons. On expiry completion, the outer signal is normally `ON_COMPLETE`, **not `CANCEL`**; upstream inside `takeWhile` can observe cancellation.
8. When the browser closes the stream, Netty/WebFlux normally cancels the publisher; immediate detection is not guaranteed if the network/proxy does not notify. Periodic ticks also serve as heartbeats to detect disconnects.
9. The sample **does not** emit an "expired token" event containing secrets and does not try to replace HTTP 200 with HTTP 401 after events have been sent (headers already committed).
10. This is a per-request dedicated `Flux`, with no global principal and no spontaneous `source.subscribe()`.
11. This policy **does not replace dynamic revocation** when an account is locked before `exp`.

### 7.4. Running WebFlux with a real IdP

Once the IdP has trusted signing keys/JWKS and real tokens:

~~~bash
export DEMO_JWT_ISSUER='https://idp.example.com/issuer'
export DEMO_JWT_AUDIENCE='events-api'

./mvnw clean package
./mvnw spring-boot:run
~~~

Values are illustrative and must be replaced with real issuer/audience. In PowerShell, use `$env:DEMO_JWT_ISSUER="..."` and `.\mvnw.cmd spring-boot:run`. With Maven installed on Windows without a wrapper, use `mvn spring-boot:run`.

Test:

~~~bash
# Public health:
curl -i http://localhost:8080/healthz

# No token: expect HTTP 401.
curl -i http://localhost:8080/api/stream

# Valid JWT with scope stream.read and aud=events-api.
# -N disables curl output buffering for SSE.
curl -N -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: text/event-stream" \
  http://localhost:8080/api/stream

# Stop the last curl client with Ctrl+C.
~~~

**Without a real token, an E2E JWT test cannot be completed.** The plain Java program in section 6 runs directly with JDK 17. The WebFlux sample does not generate JWTs/IdPs, nor does it claim to have verified a real token or executed Maven if no environment was present.

### 7.5. Expected observable behavior

| Case | Expectation |
| --- | --- |
| `GET /healthz` without Bearer | HTTP 200, `status=UP` |
| `GET /api/stream` without token | HTTP 401 before streaming |
| JWT bad signature, wrong issuer/audience, expired at request | HTTP 401 before streaming |
| Valid JWT missing `SCOPE_stream.read` | HTTP 403 before streaming |
| Valid JWT, right scope | HTTP 200 `text/event-stream`, multiple `tick` events |
| JWT reaches `exp` while stream runs | Stream **completes/closes** on next tick; cannot retroactively emit 401 after commit |
| Client closes/cancels before `exp` | Publisher receives cancel when transport detects it; cleanup/metrics run |
| User revoked before `exp` | Sample **can still continue** until `exp` because it lacks an online policy check |

## 8. Long-lived RSocket: SETUP and per-REQUEST differ

RSocket is not SSE. It uses long-lived connections with framing/metadata and reactive backpressure, and many streams can share one connection. Spring Security RSocket has entry point `PayloadSocketAcceptorInterceptor`, using `RSocketSecurity` and `@EnableRSocketSecurity`.

Per official Spring Security documentation:

- **SETUP authentication:** suitable when one connection belongs to one end user; credentials can be sent in setup metadata.
- **Per-request authentication:** suitable when a shared connection serves multiple users; credentials are sent in each request's metadata.
- **Both:** authenticate the service/workload at SETUP and authenticate the end user on each request.

If you only verify `SETUP` with a JWT expiring in 10 minutes, do not assume RSocket automatically closes all running `REQUEST_STREAM`s right at minute 10. You need dedicated expiry/revocation policies and **never reuse user A's setup authentication for user B's request**.

### 8.1. Configuring RSocket security with JWT

Below is a **bean snippet** from the official model, requiring an RSocket app configured with `ReactiveJwtDecoder` and Spring RSocket dependencies:

~~~java
@Bean
PayloadSocketAcceptorInterceptor rsocketInterceptor(
        RSocketSecurity rsocket) {

    rsocket
        .authorizePayload(authorize -> authorize
            .anyRequest().authenticated()
            .anyExchange().permitAll())
        .jwt(Customizer.withDefaults());

    return rsocket.build();
}
~~~

Enable `@EnableRSocketSecurity` on the configuration class. Spring Boot RSocket Security auto-configuration wires the interceptor when the appropriate dependencies are present; manual configuration requires understanding `RSocketServerCustomizer`.

**This snippet does not replace HTTP `SecurityWebFilterChain`**. It sets up an interceptor at the RSocket protocol layer. `RSocketSecurity.jwt()` requires a `ReactiveJwtDecoder` bean to verify JWTs sent via the Bearer Token Authentication Metadata Extension.

### 8.2. JWT metadata at SETUP and per request

~~~text
Option 1: per connection
Client -> SETUP(metadata: Bearer JWT A) -> RSocket server
Client -> REQUEST_STREAM(route=alerts) -> identity A from setup
Client -> REQUEST_RESPONSE(route=profile) -> identity A from setup

Option 2: per request on shared connection
Service -> SETUP(metadata: service credential) -> RSocket server
Service -> REQUEST_STREAM(metadata: user JWT A) -> identity A
Service -> REQUEST_STREAM(metadata: user JWT B) -> identity B
~~~

A sender snippet for setup auth per Spring Security docs:

~~~java
MimeType authMimeType =
        MimeTypeUtils.parseMimeType(
                WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION
                        .getString());

BearerTokenMetadata tokenMetadata =
        new BearerTokenMetadata(userAccessToken);

Mono<RSocketRequester> requester =
        RSocketRequester.builder()
                .setupMetadata(tokenMetadata, authMimeType)
                .connectTcp(host, port);
~~~

This is a **snippet**, not a standalone file; `userAccessToken`, `host`, and `port` are provided by the real client. For per-request metadata, use `req.route(...).metadata(tokenMetadata, authMimeType).retrieveFlux(...)`. Only send access tokens to trusted RSocket servers; TLS/routes/audience must match.

### 8.3. Token expiring while REQUEST_STREAM is still running

Even when each RSocket request is authenticated, a single `REQUEST_STREAM` can outlive the token checked at request-start. You must choose:

1. **Stream lease:** close the request-stream at token `exp` or after a maximum duration.
2. **Dynamic checks:** execute periodic or per-event permission/tenant checks via an async/reactive policy service.
3. **Renew and re-request:** client obtains a fresh token and sends credentials on a new request; never mutate credentials on a running stream in a way the protocol does not guarantee.
4. **Connection policy:** if setup credentials expire, consider closing the connection/re-running setup. On shared connections, separate service setup credentials from per-request user credentials.
5. **CANCEL cleanup:** handle RSocket `CANCEL` properly on the publisher so broker listeners do not stay alive.
6. **Backpressure:** RSocket supports `REQUEST_N`; producers should not emit infinitely into queues when client demand is low.

An RSocket `CANCEL` usually **cancels only the associated logical stream**, rather than closing the entire multiplexed connection and other streams. Never trigger user-wide logout or token revocation simply because one request-stream was cancelled.

## 9. Continuous authorization when an account is locked before exp

### 9.1. Choosing the permission verification source

Practical options:

| Source | Verifiable information | Revocation latency |
| --- | --- | --- |
| JWT snapshot | `exp`, signed scope/tenant claims | Until expiry unless checked online |
| Account/permission DB | User active status, tenant membership, document access | Transaction/replication/cache delay |
| IdP Introspection | Token `active` per RFC 7662 | Depends on propagation and cache TTL |
| Token version/denylist | Revoked tokens by ID/version | Depends on store/event propagation |
| Authorization service | Dynamic policy by resource and subject | Network latency/availability trade-off |
| Pub/sub revocation event | Pushes permission changes to stream manager | Depends on delivery/retries and subscriber state |

**Not every "user role change" makes introspection return `active=false`.** That depends on the IdP contract. If revocation is required within 5 seconds, measure worst-case time from when an admin changes permissions until the last stream stops receiving data—not merely database query time.

### 9.2. Reactive pseudocode checking every event

~~~java
// Snippet inside a service adapter; entitlementService is a dedicated API
// returning Mono<Boolean> from a trusted data source.
return sourceEvents
        .concatMap(event ->
                entitlementService.canRead(
                        verifiedIssuer,
                        verifiedSubject,
                        verifiedTenant,
                        event.resourceId())
                    .flatMap(allowed -> allowed
                            ? Mono.just(event)
                            : Mono.error(new AccessDeniedException(
                                    "Access revoked"))));
~~~

**This is not a standalone compilable file**; `sourceEvents`, `event.resourceId()`, `entitlementService`, and verified identity must be defined by the application.

Notes:

- `concatMap` preserves event order and only emits when the policy check passes; throughput drops if every event makes a network call.
- If the policy service disconnects, **never** default to `onErrorResume(err -> Mono.just(event))`. Block the stream/fail closed per policy.
- Do not merely filter out events and keep emitting others if a user is completely locked; terminate the subscription.
- If checking periodically, check interval + cache TTL + propagation must stay within the revocation SLA. Note events may still emit between two checks.
- If a stream spans multiple tenants/resources, check permissions per item or partition at the source; a global `allowed=true` across items can leak data.
- Avoid calling the policy service per event under heavy traffic without a rate budget, batching, bounded concurrency, or an approved short cache.

### 9.3. Errors after HTTP headers are sent cannot become 401

Once SSE has returned HTTP 200 and sent several events, status/headers are already committed. If permissions are revoked mid-stream, `Flux.error(new AccessDeniedException(...))` **does not guarantee the client receives HTTP 403**. The framework can close the connection after logging the error, rather than rewriting an already-committed response status.

Two design approaches:

- **Complete/close the stream** immediately upon insufficient permissions; client re-authenticates on a new HTTP request.
- If the business protocol needs an indicator, emit a safe SSE event such as `event: auth_expired` **containing no tokens/PII**, then close; the client must recognize it as a terminal reason and not infinitely reconnect with old credentials.

An SSE terminal event is a **protocol-level notification**, not an OAuth2 token response, nor a substitute for server-side termination. Once the policy check denies access, emit zero further data events afterward.

### 9.4. Per-event rechecks do not eliminate all races

If an event is fetched while the user still has access, and access is revoked **right before writing** bytes, a race still exists. For operations requiring absolute immediate cutoffs, you need stronger transactional policy/queue isolation, bounded leases, and acceptance that network delivery involves buffering. Define revocation lag and prove it via E2E tests, not theory alone.

## 10. Reconnect: fresh tokens must be verified on new HTTP requests

### 10.1. Browser EventSource header limitations

Native browser `EventSource` usage:

~~~javascript
const es = new EventSource("/api/stream", {
  withCredentials: true
});

es.addEventListener("tick", (message) => {
  console.log(message.data);
});

// Clean up resources on unmount/page unload:
es.close();
~~~

**Important:** The native `EventSource(url, {withCredentials})` constructor **has no option to set custom `Authorization: Bearer ...` headers**. Therefore:

- With a **BFF/cookie-backed session**, `EventSource` can use cookies under same-origin/CORS credentials policy, with the gateway/BFF responsible for session/security and safely relaying access tokens.
- With **direct Bearer tokens from the browser**, you need a `fetch`-based SSE client supporting custom headers, or another securely designed mechanism.
- **Never put Bearer tokens in URL query parameters** to avoid leaking them in browser history, access logs, `Referer`, proxies, and tracing.
- Be careful with `withCredentials: true` cross-origin: use a CORS allowlist, never wildcard + credentials; review cookie `SameSite`/CSRF.

### 10.2. fetch + AbortController with Authorization header

~~~javascript
const controller = new AbortController();

async function connectStream(accessToken) {
  const response = await fetch("/api/stream", {
    method: "GET",
    headers: {
      "Accept": "text/event-stream",
      "Authorization": "Bearer " + accessToken
    },
    signal: controller.signal
  });

  if (!response.ok) {
    // 401/403 on the new connection: refresh/login/permission UI.
    // Do not retry indefinitely using the same credential.
    throw new Error("SSE connection refused: " + response.status);
  }

  // Real SSE clients must parse event-stream frames incrementally,
  // including multiline data, id and retry fields.
  return response.body;
}

// When stream is no longer needed:
// controller.abort();
~~~

This is a **client connection/cancellation snippet**, not a complete SSE parser; it returns a `ReadableStream` for a standard library/parser to consume. Never split events with a naive `split("\n\n")` when data has multiline fields or split stream chunks; use a tested SSE parser library. Tokens must be stored/refreshed per the client's security model and never written to local logs.

### 10.3. Auto-reconnecting EventSource can create loops

Browser native `EventSource` has built-in **reconnect** behavior if the connection drops/closes per spec and browser rules. When the server closes due to token `exp`:

- If the client auto-reconnects using the old credentials, new requests can get **401** repeatedly.
- If the server closes after sending an `auth_expired` event, the client should call `es.close()` and prompt re-login/refresh rather than retrying infinitely with the same cookie/token.
- Enforce backoff, jitter, retry budgets, and concurrent connection limits.
- Once fresh credentials are issued, open a **new SSE request** so Spring Security verifies the new token.
- Event `id`/`Last-Event-ID` headers are for data resumption, **not authentication proof** or permission.
- Replay must re-filter by tenant, authorization, and object ownership; never let a user read another tenant's history just by knowing an event ID.

### 10.4. Last-Event-ID and permissions

Example:

~~~http
GET /api/stream HTTP/1.1
Authorization: Bearer <fresh-access-token>
Last-Event-ID: 1024
Accept: text/event-stream
~~~

`Last-Event-ID` is a replay position if supported by the server. It is **client-supplied** and can be forged; the server must enforce scope/tenant/ownership on **every replayed event**, bound history ranges, apply expiry/retention policies, and never treat an event ID as an authorization capability. If replay is not supported, do not pretend to process the ID to avoid client gaps or duplicate processing.

## 11. Backpressure and memory isolation

### 11.1. Flux does not mean the server has infinite memory

A `Flux` emitting faster than the browser/network consumes causes pressure:

- `Flux.interval` can fail with overflow without proper demand; do not assume infinite retention.
- `Flux.create` or broker pushes can buffer if the strategy is unbounded.
- Proxies/nginx can buffer SSE, making clients receive slowly and skewing cancellation/expiry observability.
- Publishers shared across subscribers can have different backpressure semantics than `Flux.defer`/cold publishers.

Define a clear policy: **drop, latest, bounded buffer, or upstream backpressure**. For security-critical events, never "drop and pretend delivered" if business requires exactly-once; consider a message broker + protected cursor/replay.

### 11.2. Avoid unbounded `onBackpressureBuffer()`

~~~java
// Anti-pattern if the source pushes infinitely and clients consume slowly:
source.onBackpressureBuffer();
~~~

If buffers are unbounded, thousands of slow clients can blow up the heap. For real-time UI updates, `onBackpressureLatest()` is sometimes acceptable though it **drops intermediate events**; for transactions/audits, use a queue with retention/replay/deduplication rather than discarding data. Decisions must follow each event type's semantics.

### 11.3. Never emit tenant A's events into subscription B

If using a shared hot `Sinks.Many<Event>`:

~~~text
allTenantsSink
   -> auth for user tenant B
   -> filter after logging/serialization?
   -> browser B
~~~

It is unsafe if raw secrets/events pass through observability systems/buffers not belonging to tenant B. Partition at the broker/topic/key level, query by verified tenant, and perform final authorization before serialization. A `filter(event -> tenant.equals(event.tenant()))` is only one layer of defense; production needs end-to-end data isolation.

### 11.4. Fan-out and cancellation

If a publisher uses `publish().refCount()` or `share()`, cancelling one subscriber **does not necessarily** cancel upstream if other subscribers remain. That is right for intentional fan-out; however, ensure user A unsubscribing does not impact user B, while avoiding keeping upstream alive forever when subscriber count drops to zero. Test `refCount`, broker consumer cleanup, and tenant partitioning.

## 12. Testing with Reactor StepVerifier and WebTestClient

### 12.1. Pure policy unit tests

`StreamAccessPolicyDemo` in section 6 already uses fixed timestamps. Extend JUnit 5 with:

| Test | Input | Expected |
| --- | --- | --- |
| Token at T0 | `exp=T0+10s`, permission active | ALLOW |
| T+9s | Not yet expired | ALLOW |
| T+10s | Exact `exp` timestamp | TOKEN_EXPIRED |
| Revoked at T+2s | `currentPermission=false` | ACCESS_REVOKED |
| Route tenant B, token A | Tenant mismatch | WRONG_TENANT |
| Missing scope | Lacks `SCOPE_stream.read` | MISSING_SCOPE |
| Unregistered route | `tenant-x` | UNKNOWN_TENANT |

Use `Clock.fixed(...)` or pass `Instant` to test without waiting for real time. Never test security expiry against an uncontrolled system clock and claim tests are deterministic under heavy CI load.

### 12.2. Testing cancellation directly with Flux

~~~java
// JUnit/Reactor-Test snippet; reactor-test dependency is required.
AtomicInteger cancelled = new AtomicInteger();

Flux<Long> source = Flux.interval(Duration.ofMillis(10))
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                cancelled.incrementAndGet();
            }
        });

StepVerifier.create(source.take(2))
        .expectNextCount(2)
        .verifyComplete();

// take(2) cancels upstream after 2 elements; upstream doFinally
// can observe CANCEL. Wait for deterministic synchronization if needed.
~~~

This is a **test method snippet**, not a complete class; it needs `reactor-test` and imports. Note the placement of `doFinally`: placed **after `take(2)`**, it observes `ON_COMPLETE` at the outer subscriber. Placed **before `take(2)`**, upstream observes `CANCEL`. Never assert async metric callbacks using arbitrary sleeps; use proper synchronization or dedicated test hooks.

### 12.3. Testing WebFlux authorization

Spring Security Test reactive provides `mockJwt()`. Example:

~~~java
// Snippet inside a WebTestClient integration test with Security filters.
webTestClient.mutateWith(mockJwt()
        .jwt(jwt -> jwt
                .subject("test-user")
                .expiresAt(Instant.now().plusSeconds(30)))
        .authorities(new SimpleGrantedAuthority(
                "SCOPE_stream.read")))
        .get().uri("/api/stream")
        .exchange()
        .expectStatus().isOk();
~~~

**Warning:** `mockJwt()` injects a fake `Authentication` and **does not call the JWT signature decoder**. This test proves authorization for the granted authorities, not real JWT issuer/JWKS/audience/`exp`. For infinite streams, **never use `expectBody()` to wait for stream completion**; consume the response body as a `Flux`, use `take(n)`/`StepVerifier`, and **cancel**.

### 12.4. What must E2E tests verify?

| Scenario | Expectation |
| --- | --- |
| Opening protected SSE without Bearer | HTTP 401 before events |
| Wrong JWT signature/audience/expiry at open | 401 before events |
| Valid JWT missing scope | 403 before events |
| Valid, unexpired JWT, right tenant | 200 + events for right tenant |
| Token expires during stream | Stream completes/closes within lease policy; no events after expiry window |
| Browser `EventSource.close()` | Upstream cancels when disconnect is detected; no listener leak |
| `fetch AbortController.abort()` | Client stops reading, server cleans up subscription |
| Mid-stream policy revocation | Service with continuous authorization stops/fails closed within SLA |
| Fresh token after reconnect | New HTTP request re-authenticates |
| Reconnect with old expired token | 401; no retry storm |
| RSocket setup JWT expires | Policy-dependent; test that it does not stream forever past lease |
| RSocket `CANCEL` on one stream | Only that stream stops; other streams are not cancelled by mistake |
| Multiple users sharing RSocket connection | Per-request auth does not leak context across users |
| Proxy idle timeout and buffering | Heartbeat works, events flush promptly, cancellation is observed |
| Slow subscriber / no demand | Bounded memory/drop policy verified |
| `Last-Event-ID` from another tenant | No cross-tenant data replay |
| IdP outage/permission DB timeout | Fails closed per policy, emits no new data |

### 12.5. VirtualTimeScheduler does not advance Instant.now

`StepVerifier.withVirtualTime(...)` controls the Reactor scheduler's virtual clock and **does not advance the JVM's `Instant.now()`**. If production code uses `Instant.now()` to cut off streams, a test advancing only virtual time may not observe token expiry. Inject a `Clock` for policy time alongside a virtual scheduler for `Flux.interval` for fast tests, or mock the policy/tick source separately.

### 12.6. Never test infinite streams with blocking collection

~~~java
// ANTI-PATTERN on an infinite Flux:
List<Event> all = events.collectList().block();
~~~

It never completes and will hang tests or wait forever. Use `take(3)` + `StepVerifier` and cancel instead. With `WebTestClient` SSE, response bodies may never complete by design; the test harness must set timeouts and expected event counts.

## 13. Observability and security operations

Track **suggested** metrics (do not assume Spring Boot generates these exact names):

| Metric | What it shows |
| --- | --- |
| `sse.active_subscriptions` | Total open streams by bounded route/tenant tags |
| `sse.cancel_total` | Client disconnects/cancellations |
| `sse.complete_total` | Leases/expirations |
| `sse.error_total` | Upstream failures, transport failures |
| `sse.duration_seconds` | Duration distribution P50/P95/P99 |
| `sse.auth_cutoff_total` | Streams cut off due to token exp/permission revocation |
| `rsocket.request_stream_active` | Active logical streams |
| `rsocket.cancel_total` | Logical CANCELs received |
| `stream.authz_recheck_duration` | Cost of DB/IdP policy checks |
| `stream.reconnect_attempts` | Retry storms and client reconnect churn |
| `stream.buffered_events` | Memory pressure for slow subscribers |

These are suggested names. Avoid metric tags with raw tokens, `sub`/emails, unique event IDs, or arbitrary URLs that cause PII/cardinality explosions. Log correlation IDs, trusted route/tenant labels, termination reasons, and policy decision categories; **never** log `Authorization` headers, ID Tokens, access/refresh tokens, raw claims, or payloads containing confidential data.

### 13.1. Detecting leaked subscriptions

Signs of a leaked subscription:

- Browser/tab closes yet broker listeners keep growing.
- `sse.active_subscriptions` fails to drop after clients cancel.
- CPU keeps running timers/tasks for closed connections.
- Heap/backpressure buffers grow alongside disconnected client counts.
- RSocket `CANCEL` does not trigger cleanup of a logical subscription.
- Many "zombie" connections outlive max lease.

Test real network disconnects rather than only unit-test cancellations, because reverse proxies/gateways/TCP half-open states can delay detection.

### 13.2. Server cap policies

Enforce limits:

- Max stream lifetime (e.g., a few minutes per business rules, not implicitly tied to token TTL).
- Max concurrent subscriptions per principal/tenant/instance.
- Max buffered events/bytes, heartbeat intervals, and idle timeouts.
- Max reconnect attempts within a time window; rate limits.
- Max concurrent policy checks, timeouts, and circuit breakers.
- Data retention/replay range for `Last-Event-ID`.
- Token refresh cadence, bounded grace periods, and fail-closed cutoffs.

Never simply crank server/proxy timeouts up to "infinity" to hide cancellation bugs or missing token expiry policies.

## 14. Common mistakes

### 14.1. Assuming SecurityWebFilterChain verifies the JWT before every SSE event

Wrong. By default it runs per HTTP request; the `Flux` emitted afterward does not invoke the JWT decoder on every `onNext`. Fix: stream leases, expiry cutoffs, or continuous policies.

### 14.2. Using ThreadLocal SecurityContextHolder inside a Flux

Incompatible with the Reactor Context model and prone to missing/mixed identities across async callbacks. Use `ReactiveSecurityContextHolder` or inject `@AuthenticationPrincipal` and retain an immutable subscription-local identity.

### 14.3. Taking tenant from query params without checking the token

A `?tenant=tenant-b` param is not proof. Filter brokers/data by verified tenant claims/membership and resource authorization.

### 14.4. Returning `Flux.never()` while creating a side-effect subscription manually

The client closes the stream yet the subscription created via `source.subscribe()` keeps running. Return the composed publisher and clean up via `doFinally`/`usingWhen`/listener hooks.

### 14.5. Assuming `doFinally(CANCEL)` always runs immediately when a user loses Wi-Fi

Network disconnects may not be detected instantly. Periodic heartbeats/writes and proxy timeouts help detection. Test TCP half-open states.

### 14.6. Equating `takeWhile` completion with CANCEL

When `takeWhile` evaluates false, the outer subscriber sees `ON_COMPLETE`; `takeWhile` cancels upstream. Where you place `doFinally` determines which signal you observe.

### 14.7. Sending Access Tokens via SSE events or URL query strings

No. Tokens are credentials, not event data, logs, or `Last-Event-ID`. SSE IDs are only cursors, never authorization.

### 14.8. Using native EventSource and trying to set an Authorization header

The native constructor only accepts `url` and `{withCredentials}`; it does not allow custom Bearer headers. Use a secure BFF cookie flow or a `fetch`-based SSE client supporting headers.

### 14.9. Treating an "expired" SSE event as if it were HTTP 401

Once headers are committed, an SSE terminal event is application protocol and cannot change the prior status code. Clients must interpret the event and stop reconnecting with stale credentials.

### 14.10. Client auto-reconnecting infinitely with an expired token

This can trigger a 401 storm. Handle the `auth_expired` terminal reason, refresh/re-login, and enforce retry budgets/backoff.

### 14.11. RSocket auth at SETUP for a connection shared across multiple users

Setup credentials usually represent the connection/workload identity, not every multiplexed user. Use per-request bearer metadata when user-level auth is needed, and enforce route-level authorization.

### 14.12. Thinking RSocket CANCEL closes the entire connection

`CANCEL` applies to a logical stream; multiplexed connections can continue serving other streams. Clean up per stream properly without logging out the whole user.

### 14.13. Checking only `exp` and ignoring revocation

JWT expiry does not change when an admin locks a user. You need DB/introspection/denylist/event-driven policies aligned with your SLA to stop before expiry.

### 14.14. Rechecking permissions after serializing sensitive data

Too late if the event was already buffered, logged, or serialized outside the tenant. Filter and authorize **before emitting** and at the source whenever possible.

### 14.15. Using permanent permission caches

Indefinite caches let revoked users keep reading data. TTLs/invalidations must fit within the revocation SLA and be tested.

### 14.16. Ignoring backpressure and unbounded buffers

Slow subscribers can fill the heap. Use bounded buffers/drop-latest where semantics allow, or broker replay when events cannot be lost.

### 14.17. Testing only with mockJwt and concluding validation works

`mockJwt()` bypasses the signature decoder; it only tests authorization. E2E requires real/test-issuer signed JWTs, wrong `aud`, expired tokens, and JWKS rotation tests.

### 14.18. Treating SSE, WebSocket, and RSocket as the same protocol

SSE is unidirectional HTTP; RSocket has request/response, request-stream, request-channel, frame metadata, `CANCEL`, and demand. Authorization and reconnect must match the actual protocol.

## 15. Production checklist

1. Identify HTTP SSE, WebSocket, or RSocket and its actual authentication checkpoints.
2. Reactive Spring Security uses `ServerHttpSecurity` and `ReactiveSecurityContextHolder` with proper subscriber context.
3. JWT issuer/signature/exp/nbf/audience and scopes are validated on the initial request.
4. Never treat the token snapshot at stream open as permanent authorization.
5. Choose an explicit **stream lease/exp cutoff**, plus continuous revocation if needed.
6. Enforce token expiry cutoffs before emitting new events, with cancellation cleanup.
7. Set a maximum stream lifetime even when the token is still valid.
8. Check scope/tenant/object ownership on new events and replays.
9. Never turn query params/`Last-Event-ID`/`X-User` headers into credentials.
10. Native `EventSource` uses cookies/BFF, or a `fetch`-based client when Bearer headers are required.
11. Clients renew/reconnect with fresh credentials, backoff, and no infinite retries.
12. Understand HTTP status after response commit cannot change to 401/403.
13. Use heartbeats/periodic writes to detect disconnected clients sooner.
14. Clean up broker listeners/DB cursors/timers on `COMPLETE`/`ERROR`/`CANCEL`.
15. Never manually `subscribe()` and lose HTTP cancellation linkage.
16. Limit active subscriptions, event buffers, and memory per tenant.
17. RSocket distinguishes JWT SETUP vs. per-request metadata, especially on multiplexed connections.
18. RSocket `CANCEL` cleans up only the corresponding logical stream.
19. Test Reactor Context across scheduler/async boundaries, cancellation, and virtual clocks.
20. Test expired/revoked tokens while streams are open; measure end-to-end revocation lag.
21. Never log sensitive tokens/claims; collect metrics for active/cancel/error/reconnect.
22. Have a fail-closed plan for IdP/permission store outages.
23. Ensure CSRF/CORS/SameSite are right for cookie-backed SSE and browser BFFs.
24. Evaluate reverse proxy buffering, idle timeouts, TLS termination, and connection counts.
25. Write runbooks for user revocation, signing key rotation, and token TTL changes.

## 16. Self-check questions

**Question 1.** Does an HTTP JWT verified once when opening SSE automatically re-verify on every `onNext`?

**Answer:** Not by default. To stop after expiry, bound the stream or check time/permissions inside the pipeline yourself.

**Question 2.** Why shouldn't reactive `SecurityContext` be treated as a global ThreadLocal?

**Answer:** Spring Security reactive uses per-subscriber Reactor Context; global/ThreadLocal approaches easily lose or mix identities in async callbacks.

**Question 3.** If a token expires at 10:00 yet SSE still emits events at 10:05, is that necessarily a JWT decoder bug?

**Answer:** No. The decoder verified the initial request; continuous expiration enforcement is a stream lifecycle policy, not built-in automatically.

**Question 4.** When a client calls `EventSource.close()`, does the server always know immediately?

**Answer:** Not necessarily. Transport/proxies must detect the disconnect; periodic heartbeats/writes help detect cancellation sooner.

**Question 5.** Which signal does `doFinally` receive when the subscriber cancels directly?

**Answer:** `SignalType.CANCEL`; with `takeWhile` completing on expiry, the outer operator usually sees `ON_COMPLETE`.

**Question 6.** Can `Last-Event-ID` be used as proof the user has replay permission?

**Answer:** No. It is a client-supplied cursor; replay must authenticate and authorize by tenant/object.

**Question 7.** Can native `EventSource` set `Authorization: Bearer` via its constructor?

**Answer:** No. Use a cookie-backed BFF or a `fetch`-based SSE client supporting custom headers.

**Question 8.** Why is `Flux.usingWhen` useful?

**Answer:** It manages asynchronous resources and has cleanup branches for complete/error/cancel, fitting broker subscriptions and DB cursors.

**Question 9.** Should a shared RSocket connection use user A's setup JWT for user B's requests?

**Answer:** No. Use a service setup identity and per-request user authentication when per-user authorization is required.

**Question 10.** If a JWT is not expired yet an admin locks the user, is `takeWhile(now < exp)` enough?

**Answer:** No. You need current entitlement/account/revocation checks within your SLA.

**Question 11.** Why can't the server change the response to HTTP 401 after SSE has already sent data?

**Answer:** Headers/status are already committed; it can only close/error the stream or emit a designed protocol-level terminal event.

**Question 12.** Why might a `StepVerifier.withVirtualTime` test miss expiry in code using `Instant.now()`?

**Answer:** `VirtualTimeScheduler` controls Reactor scheduler time, not the JVM clock; inject a `Clock` for security policy time.

## 17. Official documentation and further reading

- [Spring Security — Reactive Security Method Support and Reactor Context](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — RSocket Security: setup/request authentication and authorization](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html)
- [Spring Framework — WebFlux Reactive Core, Streaming/Heartbeat](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Framework — WebFlux annotated controller return types](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework — WebFlux ResponseEntity and asynchronous response](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html)
- [Project Reactor — Error handling, doFinally, using/usingWhen](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [Project Reactor — Testing with StepVerifier and VirtualTimeScheduler](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Project Reactor — Backpressure operators](https://projectreactor.io/docs/core/release/reference/coreFeatures/backpressure.html)
- [MDN — EventSource API](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
- [MDN — EventSource constructor options](https://developer.mozilla.org/en-US/docs/Web/API/EventSource/EventSource)
- [MDN — Server-sent events event stream format](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7662 — OAuth2 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
