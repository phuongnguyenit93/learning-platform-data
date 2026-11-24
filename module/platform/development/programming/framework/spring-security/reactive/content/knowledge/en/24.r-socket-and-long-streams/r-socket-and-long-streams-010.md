# Connection Limits, Resource Caps, and Behavior When a Session Is Revoked in RSocket Security

## 1. Goal and context

This lesson belongs to the **RSocket and long streams** section of the **Spring Security - reactive** module. An RSocket TCP or RSocket-over-WebSocket connection can be long-lived and multiplex many logical requests/streams. This reduces connection setup overhead, yet introduces three operational questions different from short HTTP requests:

1. How do we limit **physical connections**, active requests/streams, queued data, memory, CPU, bandwidth, and stream lifetimes?
2. When a user/tenant/token/authentication session is **revoked**, what happens to a stream that was initially allowed? How do we terminate active streams and prevent opening new ones?
3. How do we implement and test these mechanisms in **Spring Security reactive** without confusing RSocket with WebFlux HTTP, without blocking the event loop, and without leaking credentials or another tenant's data?

After this lesson, you can:

- Separate **physical connection**, **RSocket request/stream**, **authentication session**, **JWT lifetime**, and **HTTP WebSession** into distinct concepts.
- Explain why `RSocketSecurity` checks SETUP/requests/routes but **does not automatically re-authorize every PAYLOAD** inside a long-lived request-stream.
- Design multi-layer quotas: edge/transport admission, SETUP identity, per-principal/tenant in-flight streams, per-route concurrency, per-subscription TTL, and payload/buffer limits.
- Use `Flux.using`, `Sinks.One`, `takeUntilOther`, and Reactor cancellation to release resources on **`onComplete`/`onError`/`cancel`**.
- Handle revocation as **deny new work + notify/cancel active subscriptions**, rather than assuming HTTP logout closes all sockets.
- Design multi-node setups with a **durable revocation source**, pub/sub notifications, and race/reconnect handling.
- Build a Java 17+ / Spring Boot 3.3.13 / Spring Security RSocket example featuring a **stream quota registry**, **proactive stream termination on revocation**, a lab admin endpoint, and `RSocketRequester` + `StepVerifier` tests.
- Know what the example truly caps and **what it does not cap yet**, especially that logical stream quotas **differ** from physical TCP connection quotas.

> In this lesson, "session" may mean an HTTP session, connection-level authentication, access token, or server-side grant/entitlement. There is no single "session revocation" concept that applies automatically to all of them. You must specify **what is being revoked, which source of truth decides, who receives notifications, and how live connections/streams behave**.

## 2. Resource units: connection, request, stream, message

### 2.1. One connection can hold many streams

```text
RSocket TCP / WebSocket connection #17
  |
  +-- SETUP (authentication metadata: principal A)
  |
  +-- stream ID 1: REQUEST_RESPONSE route=profile.me
  |      -> 1 response
  |
  +-- stream ID 3: REQUEST_STREAM route=quotes.watch
  |      -> payload 1, 2, ..., N
  |
  +-- stream ID 5: REQUEST_CHANNEL route=chat.room
  |      <-> bidirectional payloads
  |
  +-- stream ID 7: REQUEST_STREAM route=alerts.watch
         -> payloads for minutes/hours
```

Counting only **1 socket** in the diagram above hides **4 logical interactions** and at least 3 streams capable of holding significant resources.

RSocket has four interaction models:
- **Request-Response**: one request, one response.
- **Fire-and-Forget**: one-way send, no response payload expected.
- **Request-Stream**: one request, multiple payloads returned; supports demand and cancellation.
- **Request-Channel**: both sides can stream payloads.

Do not take `maxConnections` of an HTTP client pool and treat it as the RSocket server request limit. An RSocket server has its own physical listener, and a single connection can multiplex hundreds of logical streams.

### 2.2. Resources to manage at each layer

| Layer | Unit | Risk if unbounded |
| --- | --- | --- |
| Edge/ingress/TCP | Sockets, handshakes/sec, IP, FD, TLS | SYN flood, socket exhaustion, handshake CPU |
| RSocket SETUP | Concurrent connects, metadata bytes, auth attempts | Password/JWT verification storm |
| Identity/quota | Connections per principal/tenant/service | One client monopolizes all connections |
| Request admission | In-flight requests/streams per principal/route | DB/broker/event source overload |
| Stream lifecycle | Max duration, idle time, max items, reconnect | Subscriptions live forever |
| Payload/codecs | Frame bytes, composite metadata, decoder memory | Memory pressure, oversized payloads, decompression |
| Outbound event source | Message rate, per-client demand, queues | Unbounded buffers, slow consumers, data loss |
| Identity/session | Token expiry/revocation, tenant grant state | Streams keep running after permissions are revoked |
| Cluster | Connections/streams per node, shared limits | Per-node limit multiplied by node count |
| Observability | Metrics, labels, logs | Blind to pressure or leaking secrets |

**Connection limit != stream limit != message rate limit.** Set all three according to topology and threat model.

### 2.3. Illustrative resource budgets

A test node might set:

| Target | Illustrative limit | Enforcement point |
| --- | ---: | --- |
| Active TCP/WebSocket connections/node | 500 | Ingress, Netty acceptor/connection admission |
| Handshakes/IP/min | 60 | Edge/gateway, transport admission |
| Connections/principal | 3 | Connection registry after SETUP AuthN |
| Active request-streams/node | 250 | Application stream registry |
| Active streams/principal | 2 | Application stream registry |
| Stream duration | 15–30 minutes | Reactor `take(Duration)`/deadline |
| Items/stream | Per API contract | `take(count)` + application budget |
| Payload bytes | Per DTO/transport/decoder | Transport/codecs, not a single controller `if` |
| Unacknowledged/buffered events | Bounded or reject | Event source/broker/buffer strategy |
| Authentication verification timeout | Per IdP SLO | ReactiveAuthManager/decoder timeouts |
| Revocation propagation | e.g., p99 under 5 seconds | Event bus + process-local registries |

These are **hypothetical values for sizing calculations**, not Spring Boot defaults or copy-paste recommendations. Appropriate values must be validated with load tests, host resources, SLAs, and message sources.

## 3. What does Spring Security RSocket protect?

Spring Security RSocket integrates via `PayloadSocketAcceptorInterceptor` and `RSocketSecurity`:

```java
@Bean
PayloadSocketAcceptorInterceptor rsocketInterceptor(
        RSocketSecurity rsocket) {
    return rsocket
            .authorizePayload(auth -> auth
                    .setup().authenticated()
                    .route("events.stream").hasRole("STREAM")
                    .anyRequest().denyAll()
                    .anyExchange().permitAll())
            .simpleAuthentication(Customizer.withDefaults())
            .build();
}
```

This is a **configuration fragment**; the full example appears in section 8.

- `setup().authenticated()`: here, requires authentication metadata when opening the RSocket connection.
- `route("events.stream").hasRole("STREAM")`: checks caller has `ROLE_STREAM` when starting a request with this route.
- `anyRequest().denyAll()`: rejects unlisted routes.
- `anyExchange().permitAll()`: fallback for payload exchanges lacking initial request routing metadata; does not mean opening permissions for all streams.

**Important limitation:** A `request-stream` that passed route authorization can keep emitting payloads after the token/session is revoked **unless the application has its own cancellation/recheck mechanism**. `AuthorizationPayloadInterceptor` does not automatically re-run policy on every business event of a `Flux` just because a role changed in the database.

### 3.1. Authentication at SETUP or per request?

**SETUP auth:** one connection normally represents one client/user; metadata is verified on connect. Fits personal mobile apps or dedicated service accounts. However, if token `exp` is in the future and the stream outlives the token TTL, initial verification does not automatically sever the stream at the exact `exp` timestamp.

**Per-request auth:** a shared connection serves multiple end users; each request sends its own token metadata. Better for identity isolation on shared connections, yet still does not guarantee per-event rechecks inside a request-stream.

**Both:** SETUP verifies app/gateway identity, each request verifies end user. Test distinct authorities; never let caller B inherit A's authentication from a pool/builder.

### 3.2. HTTP WebSession is not an RSocket connection

HTTP Spring Security's `WebSession.invalidate()` can revoke cookie-based login state, **without closing** a live RSocket TCP socket or cancelling an emitting `Flux`.

If RSocket runs over WebSocket, the HTTP handshake occurs only at upgrade time. Subsequent cookie logout does not force RSocket payloads to be rechecked unless a bridge/connection registry/revocation signaling is implemented. Never treat an HTTP-protecting `SecurityWebFilterChain` as protecting all RSocket routes.

### 3.3. JWT expiry is not an instant disconnect

When using `RSocketSecurity.jwt(...)`, `ReactiveJwtDecoder` checks JWTs during authentication attempts. An already-verified connection/authentication does not automatically receive notifications when a token:
- Passes `exp`;
- Is revoked at the Authorization Server;
- Has its user locked;
- Has its tenant disabled;
- Has its roles/scopes changed.

With stateless JWTs, the backend may have no global "session row" to delete. Rapid revocation requires a denylist/`jti`, identity version, short token TTL, introspection/authorization store, broadcast revocation, or matching connection TTL design. **A single signature verification does not push revocations**.

## 4. Four "session revoked" scenarios and desired outcomes

| Scenario | Auto-terminates open RSocket stream? | Approach |
| --- | --- | --- |
| User logs out of HTTP WebSession | **Not automatically** | App pushes revoke event to RSocket connection registry |
| JWT access token expires | **Not guaranteed** after SETUP | Cap stream/connection TTL, reauthenticate/recheck |
| Client API key revoked | **Not automatically** with SETUP-verified manager | Deny future attempts; force close/cancel active streams |
| Tenant/order permissions changed | **Not automatically** for already-buffered items | Check owner/tenant on data; cancel + drop queued items per SLA |

Behavior that must be **intentionally designed**:

1. **Deny new admission:** new requests/streams from the revoked principal are rejected.
2. **Terminate active streams:** emit a signal (error/complete/cancel) to stop producers and release resources.
3. **Optionally close physical connection:** when revocation applies to the whole connection or security policy requires it.
4. **Reject reconnect:** in SETUP/per-request authentication manager or latest central policy.
5. **Observe and audit:** record who/when/why per policy (redacted), closed stream count, revocation latency, and race behavior.
6. **Prevent stale revival:** multi-node state must persist revoked status across restarts/reconnects, not just a volatile flag in one instance.
7. **Control buffered data:** manage risk of data already queued/in-flight at revocation time.

**Never** create a fallback "if IdP is down, keep streaming with expired tokens." If policy demands current decisions, verification errors must fail-closed or follow an explicitly defined and approved grace period.

## 5. Where does connection admission actually live?

### 5.1. Four defense layers

```text
Internet / internal clients
        |
        | IP rate limit, SYN/handshake, TLS, origin
        v
Ingress / LB / service mesh
        |
        | physical sockets/handshakes/idle connection caps
        v
Reactor Netty TCP / WebSocket transport
        |
        | max frame/metadata size, traffic budget
        v
RSocket SETUP
        |
        | authenticate principal, per-principal connection cap
        v
RSocket request / stream
        |
        | per-route/per-user active stream cap
        v
Reactive handler / DB / broker
```

There are at least two admission tiers:

- **Pre-AuthN:** only IP/connection metadata is available, no trusted user yet. Rate-limit by IP/network/gateway, node-wide socket count, and TLS handshakes.
- **Post-AuthN:** apply trusted per-principal/tenant limits, since a username in an unverified header/SETUP payload is untrusted input.

Never use `principalId` from a request body as a global quota key before verification; attackers can generate endless keys to bypass quotas.

### 5.2. Server physical connection limits differ from client pools

Some Reactor Netty configs like `ConnectionProvider.maxConnections(...)` apply to **client-side connection pools**, especially HTTP/TCP clients. They do not automatically limit **inbound RSocket server connections** just because both use Reactor Netty.

For an RSocket server:
- Use an ingress proxy/L4 LB limiting connections/handshakes in front of the app;
- Or configure Netty transport/server acceptor/connection observers per version;
- Or use `RSocketServerCustomizer` + `SocketAcceptorInterceptor` to enforce admission at SETUP and watch `onClose`, if that is where sufficient metadata exists;
- Cap file descriptors, per-IP quotas, TLS handshake CPU, and connection idle/keepalive;
- Never leak permits if a connection fails during SETUP.

**Pseudocode for connection-layer admission, NOT runnable Java:**

```text
onPhysicalAccept(connection):
    if not globalConnectionPermit.tryAcquire():
        rejectOrClose(connection)
        return
    attach exactly-once release on connection.onClose()
    start SETUP parsing with timeout and max metadata bytes

onAuthenticatedSetup(connection, verifiedIdentity):
    if not principalConnectionPermit(verifiedIdentity).tryAcquire():
        rejectSetupAndClose(connection)
        return
    attach exactly-once release for principal permit on close
    register connectionID -> identity, RSocket dispose handle
    continue RSocket routing

onConnectionClosed(connection):
    release global permit exactly once
    release principal permit if it was acquired
    unregister connectionID
```

This is a pattern to attach into a compatible `RSocketServerCustomizer`/Netty handler, **without** pretending a property `spring.rsocket.server.max-connections` always exists. Connection acceptor APIs can change across Spring Boot/RSocket Java/transport versions. Test integration against real transport, including failed SETUP, client disconnects, half-open sockets, and restarts.

### 5.3. Avoid conflating connection limits with stream limits

Suppose each socket can multiplex 100 streams:
- Cap 100 sockets without capping streams → up to 10,000 streams;
- Cap 100 streams without capping sockets → attackers can open thousands of idle sockets;
- Cap only messages/sec → does not prevent a stream from holding huge memory or a connection holding an FD forever.

Thus the runnable example in section 8 deliberately solves only **logical stream quotas + revoke signals**, while physical socket quotas live at ingress/acceptor per this section. In operational reports, never describe `activeStreams` as `activeConnections`.

## 6. Resource budgets for request-stream/channel

### 6.1. Concurrency limits

Set:
- `maxActiveStreamsPerPrincipal` so one account cannot exhaust producer slots;
- `maxActiveStreamsGlobalPerNode` to protect the process;
- `maxActiveStreamsPerTenant` when multiple users share a tenant;
- `maxInFlightOperationsPerRoute` if a route hits heavy DB/CPU work.

Admission must be **atomic**: two concurrent requests must not both observe "one slot left" and both get admitted. Use CAS/atomic counters, bounded-permit semaphores, or per-principal locks; in multi-node setups, decide whether global quotas must be cluster-consistent or per-node.

### 6.2. Message count and duration quotas

```java
// Illustrative snippet, not a standalone handler:
Flux<Event> limited = upstream
        .take(500)                       // max items
        .take(Duration.ofMinutes(5))     // max subscription lifetime
        .doFinally(signal -> releasePermitExactlyOnce());
```

`take(500)`/`take(Duration)` bound items/time, **not per-item size** and **do not protect upstream memory** if upstream already buffers infinitely. Set `maxInMemorySize` on codecs/transport appropriately, validate schema/length, and bound broker queues.

### 6.3. Backpressure and slow consumers

RSocket Request-Stream supports `REQUEST_N` demand. That helps protocol-level flow control, yet producers or bridges can build large buffers before downstream sends demand:
- Unbounded `onBackpressureBuffer()` → easy `OutOfMemoryError`;
- `publishOn` has prefetch/buffering that must be measured;
- Multicast `Sinks` have varying overflow/drop policies;
- Per-user fan-out subscriptions can multiply broker load;
- Heavy blocking transforms on the event loop add latency to all connections.

Consider:
- bounded queues, drop policies only for loss-tolerant data;
- rejecting slow consumers or disconnecting if backlog exceeds quota;
- bounded concurrency in `flatMap(..., concurrency)`;
- event coalescing/throttling/sampling when business permits;
- never using `onBackpressureDrop` to silently drop financial data needing exactly-once;
- metrics for buffers, requested demand, and dropped events.

### 6.4. Cancellation and cleanup

An RSocket client can send `CANCEL`; upstream Reactor normally receives cancellation and runs `doFinally(CANCEL)`. Still, resources from DB subscriptions, file handles, broker consumers, or registry leases must be **acquired and released exactly once**, even on parse errors, timeouts, or disconnects. For resources tied to publisher lifecycles, `Flux.using`/`Flux.usingWhen` are strong choices; never manually call `subscribe()` in a handler and lose subscription ownership.

## 7. Testable revocation architecture

### 7.1. Defining invariants

The lab example uses identity `alice`:
- Maximum **2 active streams/subject**.
- Maximum **4 active streams node-wide**.
- A subscription lasts at most 20 seconds, max 100 requested items.
- Admin may send `POST /ops/revoke/alice`.
- After revocation, **no new streams are admitted** for `alice`.
- Already-admitted streams receive **error signal** `STREAM_REVOKED` and clean up permits.
- Revoked state does not auto-heal after an RSocket reconnect on the same node while the app is running.
- **Physical RSocket TCP sockets may remain open**, since the demo cancels logical subscriptions without holding connection handles.
- **Simple Authentication credentials may still pass SETUP** because the in-memory user store is not disabled. Request streams are rejected by the application registry. Production must add revocation checks right at AuthN/SETUP to block connections.

This is a contract enforcing **resource entitlement revocation**, not a full implementation of an identity provider or JWT revocation service.

### 7.2. Lease lifecycle and race conditions

```text
Subscriber opens stream
        |
        v
Flux.using resourceSupplier:
    lock bucket(subject)
    if revoked -> fail
    if per-subject quota exceeded -> reject
    atomic global permit -> reserve
    record lease + revocation signal
        |
        v
Flux interval / upstream event source
    take(count)
    take(maxDuration)
    takeUntilOther(lease.revocationSignal)
        |
        +-- normal complete ------+
        +-- error ----------------+--> Flux.using disposer -> release once
        +-- CANCEL ----------------+
        +-- revoke error ----------+
```

Admin revoke:
- Sets `bucket.revoked=true` **inside the lock**;
- Snapshots active leases;
- Emits revoke signals outside the lock;
- Each stream receives the error and runs the disposer;
- New requests once revoked fail immediately.

Setting revoked state **before** emitting signals prevents races: a new request arriving between the two steps already sees `revoked` and is denied. `Sinks.One` remembers terminal signals so a revocation emitted before the subscriber attaches is still received.

**Do not promise zero extra in-flight events** down to the nanosecond of revocation. A payload may already be in network buffers or mid-encoding when admin confirms. If immediate leak prevention is strictly required, enforce entitlements at the data boundary/egress with version epochs and clear ordering/quiescence; every distributed revocation has a propagation window to measure.

## 8. Runnable example: Boot 3.3.13 + RSocket Security + quota/revoke

### 8.1. Project layout

```text
rsocket-resource-revoke/
  settings.gradle
  build.gradle
  src/
    main/
      resources/application.yml
      java/example/rsquota/
        RsQuotaApplication.java
        UsersConfig.java
        HttpSecurityConfig.java
        RSocketSecurityConfig.java
        ActiveStreamRegistry.java
        TickStreamService.java
        TickRoutes.java
        OpsController.java
    test/
      java/example/rsquota/
        ActiveStreamRegistryTests.java
        RSocketRevocationIntegrationTests.java
```

**Demo users:**

| User | Lab password | Role | Permissions |
| --- | --- | --- | --- |
| `alice` | `lab-only` | `STREAM` | Open `ticks.watch` |
| `bob` | `lab-only` | `VIEW` | Can SETUP, cannot open `ticks.watch` |
| `ops` | `lab-only` | `OPS` | HTTP admin revoke, no stream permission |

HTTP WebFlux listener: `127.0.0.1:8080`; RSocket TCP: `127.0.0.1:7000`. Runs loopback-only because demo Simple Authentication metadata/passwords are sent **cleartext** over TCP.

### 8.2. settings.gradle

```groovy
rootProject.name = 'rsocket-resource-revoke'
```

### 8.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-rsocket'
    implementation 'org.springframework.security:spring-security-messaging'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Boot BOM manages compatibility across Spring Framework, Security, and RSocket Java. Do not add `spring-boot-starter-web` (Servlet), and do not use `HttpSecurity` for RSocket. The example pins versions for learning/reproducibility; new projects should choose a supported Boot release and re-run integration tests when upgrading.

### 8.4. application.yml

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  rsocket:
    server:
      transport: tcp
      address: 127.0.0.1
      port: 7000
```

This is **standalone RSocket TCP**, not RSocket-over-WebSocket. Do not send HTTP `curl` to port 7000. The HTTP admin endpoint runs on 8080, requiring HTTP Basic role `OPS` in the lab.

### 8.5. RsQuotaApplication.java

```java
package example.rsquota;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RsQuotaApplication {
    public static void main(String[] args) {
        SpringApplication.run(RsQuotaApplication.class, args);
    }
}
```

### 8.6. UsersConfig.java

```java
package example.rsquota;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;

@Configuration
public class UsersConfig {

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}lab-only")
                .roles("STREAM")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password("{noop}lab-only")
                .roles("VIEW")
                .build();

        UserDetails ops = User.withUsername("ops")
                .password("{noop}lab-only")
                .roles("OPS")
                .build();

        return new MapReactiveUserDetailsService(alice, bob, ops);
    }
}
```

`{noop}lab-only` is **for localhost lab use only**, with no password hashing. Production uses a trusted IdP/password encoder/token issuer, HTTPS, rate limiting, and a secret manager. The user store serves both HTTP Basic and RSocket Simple Authentication, yet the two protocols' policies remain separate.

### 8.7. HttpSecurityConfig.java

```java
package example.rsquota;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class HttpSecurityConfig {

    @Bean
    SecurityWebFilterChain adminHttpSecurity(ServerHttpSecurity http) {
        return http
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .authorizeExchange(ex -> ex
                        .pathMatchers(
                                HttpMethod.GET, "/ops/active")
                        .hasRole("OPS")
                        .pathMatchers(
                                HttpMethod.POST, "/ops/revoke/*")
                        .hasRole("OPS")
                        .anyExchange().denyAll())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                // Lab admin via HTTP Basic, no cookies used.
                .csrf(csrf -> csrf.disable())
                .build();
    }
}
```

Key points:
- `GET /ops/active` and `POST /ops/revoke/{subject}` are restricted to `ROLE_OPS`;
- No session authentication is stored for admin; Basic is sent per request;
- `csrf.disable()` is **only for this header-only lab API**. If browser sessions/cookies are used, evaluate/enable CSRF rather than copying this config;
- Never expose this revoke endpoint to the public Internet;
- HTTP permissions do not replace RSocket role `STREAM`.

### 8.8. RSocketSecurityConfig.java

```java
package example.rsquota;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableRSocketSecurity
public class RSocketSecurityConfig {

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity rsocket) {
        return rsocket
                .authorizePayload(auth -> auth
                        .setup().authenticated()
                        .route("ticks.watch").hasRole("STREAM")
                        .anyRequest().denyAll()
                        .anyExchange().permitAll())
                .simpleAuthentication(withDefaults())
                .build();
    }
}
```

Spring Boot attaches `PayloadSocketAcceptorInterceptor`/`SecuritySocketAcceptorInterceptor` to the RSocket acceptor when auto-config fits. Do not register the interceptor a second time if Boot already does so.

**Distinction needed:** `ROLE_STREAM` allows creating a request to `ticks.watch`. `ActiveStreamRegistry` below additionally checks quotas and the `revoked` flag. A user revoked in the registry can **still pass Simple Authentication SETUP** because the user store is not disabled; however, they cannot admit a new subscription. This is an **intentional and explicitly stated limitation of the demo**.

### 8.9. ActiveStreamRegistry.java — atomic quota + revoke

```java
package example.rsquota;

import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

@Component
public class ActiveStreamRegistry {

    public static final int PER_SUBJECT_LIMIT = 2;
    public static final int GLOBAL_LIMIT = 4;

    private final ConcurrentHashMap<String, Bucket> subjects =
            new ConcurrentHashMap<>();

    private final AtomicInteger activeGlobal = new AtomicInteger();

    private static final class Bucket {
        boolean revoked;
        final Set<Lease> active = new HashSet<>();
    }

    public final class Lease implements AutoCloseable {
        private final Bucket bucket;
        private final Sinks.One<Void> revokeSignal = Sinks.one();
        private final AtomicBoolean closed = new AtomicBoolean();

        private Lease(Bucket bucket) {
            this.bucket = bucket;
        }

        public Mono<Void> revoked() {
            return revokeSignal.asMono();
        }

        private void signalRevoke() {
            revokeSignal.tryEmitError(
                    new AccessDeniedException("STREAM_REVOKED"));
        }

        @Override
        public void close() {
            if (closed.compareAndSet(false, true)) {
                synchronized (bucket) {
                    bucket.active.remove(this);
                    activeGlobal.decrementAndGet();
                }
            }
        }
    }

    public Lease admit(String subject) {
        if (subject == null || subject.isBlank()) {
            throw new AccessDeniedException("Missing subject");
        }

        Bucket bucket = subjects.computeIfAbsent(
                subject, ignored -> new Bucket());

        synchronized (bucket) {
            if (bucket.revoked) {
                throw new AccessDeniedException(
                        "STREAM_REVOKED");
            }
            if (bucket.active.size() >= PER_SUBJECT_LIMIT) {
                throw new IllegalStateException(
                        "PER_SUBJECT_STREAM_LIMIT");
            }

            int newGlobal = activeGlobal.incrementAndGet();
            if (newGlobal > GLOBAL_LIMIT) {
                activeGlobal.decrementAndGet();
                throw new IllegalStateException(
                        "GLOBAL_STREAM_LIMIT");
            }

            Lease lease = new Lease(bucket);
            bucket.active.add(lease);
            return lease;
        }
    }

    public int activeCount() {
        return activeGlobal.get();
    }

    public boolean isRevoked(String subject) {
        Bucket bucket = subjects.get(subject);
        if (bucket == null) {
            return false;
        }
        synchronized (bucket) {
            return bucket.revoked;
        }
    }

    public void revoke(String subject) {
        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException(
                    "Subject is required");
        }

        Bucket bucket = subjects.computeIfAbsent(
                subject, ignored -> new Bucket());

        List<Lease> snapshot;
        synchronized (bucket) {
            bucket.revoked = true;
            snapshot = List.copyOf(bucket.active);
        }

        // Emit signals OUTSIDE the synchronized block.
        snapshot.forEach(Lease::signalRevoke);
    }
}
```

**Why does this avoid oversubscription?**

- `synchronized(bucket)` guards the `revoked` flag, per-subject `active` set, and global count reservation in one per-subject critical section.
- `activeGlobal.incrementAndGet()` is atomic across buckets. If `GLOBAL_LIMIT` is exceeded, it immediately decrements and rejects.
- Once `revoked` is set inside the lock, any subsequent `admit(subject)` is blocked.
- `snapshot` captures active leases so the lock is not held while `Sinks` signaling might trigger callbacks.
- `Sinks.One<Void>` retains the terminal error, so a race where "revoke arrives before the stream attaches its listener" still never misses the signal.
- `close()` uses `AtomicBoolean` to decrement the global count **exactly once** even if cancel/error/dispose fires multiple times.
- `activeCount()` measures only **active logical streams** in the registry, not RSocket socket counts.
- The `subjects` map does not automatically evict revoked buckets. Acceptable for a few-user demo; production needs TTL/eviction and durable revocation state to prevent memory growth, especially with high-cardinality subject IDs.
- `revoke()` does not delete user/password records or close TCP sockets. It only rejects **new streams** and emits errors to admitted leases. Do not describe it as a complete IdP logout.

**Test invariant:** After closing all 4 leases, `activeCount() == 0`, regardless of complete/error/cancel. Once `alice` is revoked, no new `admit("alice")` is accepted even when slots are free.

### 8.10. TickStreamService.java — item cap, duration cap, and cleanup

```java
package example.rsquota;

import java.time.Duration;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;

@Service
public class TickStreamService {

    private final ActiveStreamRegistry registry;

    public TickStreamService(ActiveStreamRegistry registry) {
        this.registry = registry;
    }

    public Flux<String> ticks(
            String verifiedSubject, Integer requestedCount) {

        if (requestedCount == null
                || requestedCount < 1
                || requestedCount > 100) {
            return Flux.error(new IllegalArgumentException(
                    "requestedCount must be between 1 and 100"));
        }

        return Flux.using(
                () -> registry.admit(verifiedSubject),
                lease -> Flux.interval(Duration.ofMillis(250))
                        .map(i -> "tick-" + i)
                        .take(requestedCount.longValue())
                        .take(Duration.ofSeconds(20))
                        .takeUntilOther(lease.revoked()),
                ActiveStreamRegistry.Lease::close);
    }
}
```

**Three properties:**

1. `Flux.using` acquires a lease **on subscription**, not merely when creating the publisher; this avoids reserving slots for an unsubscribed `Mono`/`Flux`.
2. `take(100)`/`take(Duration.ofSeconds(20))` bound the lab's item count and max duration. In production, values must match SLOs; item counts do not replace payload byte limits.
3. `takeUntilOther(lease.revoked())` stops the stream when the registry emits error `STREAM_REVOKED`; the error reaches downstream, and `Flux.using` calls the disposer. Normal completion/cancellation/errors also release.

An errored `Sinks.One` is propagated by Reactor into `takeUntilOther` and triggers a terminal error; depending on version/stack, the RSocket client receives an exception wrapped as a protocol application error. **Never assert a single wire-level exception class or error string across versions**. If clients need identifiable error codes, define a compatible protocol/metadata application error contract rather than relying on raw stack traces.

**Limitation:** `Flux.interval` is a simulated event source without customer data. With real databases/brokers, upstream must genuinely support cancellation/cleanup and stop emitting sensitive items once the lease is revoked. Never wrap a blocking infinite loop in `Mono.just(...)` expecting `takeUntilOther` to interrupt uncooperative I/O.

### 8.11. TickRoutes.java — reading verified subject in RSocket reactive context

```java
package example.rsquota;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class TickRoutes {

    private final TickStreamService service;

    public TickRoutes(TickStreamService service) {
        this.service = service;
    }

    @MessageMapping("ticks.watch")
    public Flux<String> watch(@Payload Integer count) {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .switchIfEmpty(Mono.error(
                        new AccessDeniedException(
                                "Authentication required")))
                .flatMapMany(authentication -> {
                    if (authentication == null
                            || !authentication.isAuthenticated()) {
                        return Flux.error(
                                new AccessDeniedException(
                                        "Authentication required"));
                    }
                    return service.ticks(
                            authentication.getName(), count);
                });
    }
}
```

`authentication.getName()` comes from **validated Spring Security `Authentication`** when RSocket SETUP auth succeeds, never from RSocket data supplied by the caller. In multi-tenant production, quota keys must include verified `issuer+subject/tenant/client identity` to avoid colliding `alice` across realms.

**Reactive context:** Never use Servlet's ThreadLocal `SecurityContextHolder.getContext()` in WebFlux/RSocket. `ReactiveSecurityContextHolder` retrieves `SecurityContext` from the Reactor subscriber context. With custom reactive operators, never call `subscribe()` or `block()` inside a message handler; doing so can break context/cancellation propagation.

### 8.12. OpsController.java — triggering revocation in the lab

```java
package example.rsquota;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OpsController {

    private final ActiveStreamRegistry registry;

    public OpsController(ActiveStreamRegistry registry) {
        this.registry = registry;
    }

    @GetMapping("/ops/active")
    public Map<String, Integer> active() {
        return Map.of("activeStreams",
                registry.activeCount());
    }

    @PostMapping("/ops/revoke/{subject}")
    public ResponseEntity<Void> revoke(
            @PathVariable String subject) {
        registry.revoke(subject);
        return ResponseEntity.noContent().build();
    }
}
```

This HTTP admin endpoint is protected by role `OPS`. It returns 204 once the revoked flag is set and signals are emitted **on the node handling the request**, without promising that every cluster node has received the revocation. In production, publish versioned/sequenced events through a central bus and monitor acknowledgments/propagation; an admin call is not proof of instant cluster-wide synchronization.

**Never expose admin endpoints to end users or assume all requests to `/ops/**` are safe**: enforce mTLS/gateway allowlists, RBAC, auditing, rate limiting, topology-appropriate CSRF, and confirmation workflows. The lesson uses localhost HTTP Basic and `{noop}` for easy practice, never verbatim in production.

### 8.13. Starting up and observing

Linux/macOS, with JDK 17+ and Gradle:

```bash
gradle bootRun
```

If the project has a Gradle Wrapper:
```bash
./gradlew bootRun
```

Windows uses `gradlew.bat bootRun`. HTTP admin listener 8080; RSocket TCP listener 7000. Use `RSocketRequester` in tests to send RSocket requests. `curl` can only call **HTTP admin**:

```bash
curl -i -u ops:lab-only \
  http://127.0.0.1:8080/ops/active

curl -i -u ops:lab-only \
  -X POST \
  http://127.0.0.1:8080/ops/revoke/alice

curl -i -u ops:lab-only \
  http://127.0.0.1:8080/ops/active
```

Expected initial GET response:

```json
{"activeStreams":0}
```

If no RSocket subscriptions are running, `activeStreams` is 0 both before and after revocation. **Revoke alters admission permissions; it does not require initial streams > 0**. To see live cancellation, open `ticks.watch` from tests/clients while calling revoke.

**Windows PowerShell:** use `curl.exe` if `curl -u` syntax is needed; some shells alias `curl` to another command. Lab credentials/passwords may appear in command history/process lists; never use this command with production passwords.

## 9. Pure quota tests with StepVerifier/JUnit

Create `src/test/java/example/rsquota/ActiveStreamRegistryTests.java`:

```java
package example.rsquota;

import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ActiveStreamRegistryTests {

    @Test
    void perSubjectQuotaAndCleanup() {
        ActiveStreamRegistry registry = new ActiveStreamRegistry();

        var first = registry.admit("alice");
        var second = registry.admit("alice");

        assertEquals(2, registry.activeCount());

        assertThrows(IllegalStateException.class,
                () -> registry.admit("alice"));

        first.close();
        first.close(); // idempotent cleanup

        assertEquals(1, registry.activeCount());

        var third = registry.admit("alice");
        assertEquals(2, registry.activeCount());

        second.close();
        third.close();

        assertEquals(0, registry.activeCount());
    }

    @Test
    void globalQuotaCountsAcrossSubjects() {
        ActiveStreamRegistry registry = new ActiveStreamRegistry();

        var a = registry.admit("alice");
        var b = registry.admit("alice");
        var c = registry.admit("bob");
        var d = registry.admit("bob");

        assertEquals(4, registry.activeCount());

        assertThrows(IllegalStateException.class,
                () -> registry.admit("carol"));

        a.close();
        var e = registry.admit("carol");

        b.close();
        c.close();
        d.close();
        e.close();

        assertEquals(0, registry.activeCount());
    }

    @Test
    void revokeBlocksNewAdmissionsAndSignalsExistingLease() {
        ActiveStreamRegistry registry = new ActiveStreamRegistry();

        var lease = registry.admit("alice");

        StepVerifier.create(lease.revoked())
                .then(() -> registry.revoke("alice"))
                .expectError(AccessDeniedException.class)
                .verify();

        assertTrue(registry.isRevoked("alice"));

        assertThrows(AccessDeniedException.class,
                () -> registry.admit("alice"));

        lease.close();
        assertEquals(0, registry.activeCount());
    }

    @Test
    void unrelatedSubjectIsNotRevoked() {
        ActiveStreamRegistry registry = new ActiveStreamRegistry();

        registry.revoke("alice");

        var bob = registry.admit("bob");
        assertEquals(1, registry.activeCount());
        bob.close();
        assertEquals(0, registry.activeCount());
    }
}
```

These tests verify:
- Limit of two streams per subject;
- Limit of four streams node-wide;
- `close()` runs exactly once;
- Revoke emits an error to active leases and blocks new admissions;
- Other subjects continue working;
- **Does not** test physical TCP connections, since this registry only tracks logical stream leases.

**Special note on concurrency tests:** The tests above are deterministic functional tests. Before production, add stress tests with many concurrent threads/virtual clients, randomized cancellation, reconnect, shutdown, and negative permit counter checks; never trust a sequential unit test alone to prove race freedom.

## 10. Integration tests: WebTestClient + RSocketRequester

Create `src/test/java/example/rsquota/RSocketRevocationIntegrationTests.java`:

```java
package example.rsquota;

import java.time.Duration;

import io.rsocket.metadata.WellKnownMimeType;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.http.HttpHeaders;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.SimpleAuthenticationEncoder;
import org.springframework.security.rsocket.metadata.UsernamePasswordMetadata;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "spring.rsocket.server.port=0",
                "spring.rsocket.server.address=127.0.0.1"
        })
@AutoConfigureWebTestClient
class RSocketRevocationIntegrationTests {

    private static final MimeType AUTH_MIME =
            MimeTypeUtils.parseMimeType(
                    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION
                            .getString());

    @Autowired
    WebTestClient http;

    @Autowired
    ObjectProvider<RSocketRequester.Builder> builders;

    @LocalRSocketServerPort
    int port;

    private Mono<RSocketRequester> connect(String user, String pass) {
        return builders.getObject()
                .rsocketStrategies(strategies ->
                        strategies.encoder(
                                new SimpleAuthenticationEncoder()))
                .setupMetadata(
                        new UsernamePasswordMetadata(user, pass),
                        AUTH_MIME)
                .connectTcp("127.0.0.1", port);
    }

    private Flux<String> watch(
            String user, String pass, int count) {
        return connect(user, pass)
                .flatMapMany(requester -> requester
                        .route("ticks.watch")
                        .data(count)
                        .retrieveFlux(String.class)
                        .doFinally(signal ->
                                requester.rsocket().dispose()));
    }

    @Test
    void adminRequiresAuthentication() {
        http.get().uri("/ops/active")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void opsCanReadActiveStreamCount() {
        http.get().uri("/ops/active")
                .headers(h -> h.setBasicAuth("ops", "lab-only"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.activeStreams").isNumber();
    }

    @Test
    void aliceCanReceiveFiniteRequestStream() {
        StepVerifier.create(watch("alice", "lab-only", 3))
                .expectNext("tick-0", "tick-1", "tick-2")
                .expectComplete()
                .verify(Duration.ofSeconds(8));
    }

    @Test
    void bobCanAuthenticateSetupButCannotReadStream() {
        StepVerifier.create(watch("bob", "lab-only", 2))
                .expectError()
                .verify(Duration.ofSeconds(8));
    }

    @Test
    void wrongSetupPasswordIsRejected() {
        StepVerifier.create(watch("alice", "wrong-pass", 2))
                .expectError()
                .verify(Duration.ofSeconds(8));
    }

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void revocationTerminatesActiveStreamAndDeniesNextOne() {
        StepVerifier.create(watch("alice", "lab-only", 80))
                .expectNext("tick-0")
                .then(() -> http.post()
                        .uri("/ops/revoke/alice")
                        .headers(h ->
                                h.setBasicAuth("ops", "lab-only"))
                        .exchange()
                        .expectStatus().isNoContent())
                .expectError()
                .verify(Duration.ofSeconds(8));

        // SETUP may still authenticate Simple credentials.
        // Yet the new stream is not admitted by the registry.
        StepVerifier.create(watch("alice", "lab-only", 2))
                .expectError()
                .verify(Duration.ofSeconds(8));
    }
}
```

**Test explanation:**
- `@LocalRSocketServerPort` (Spring Boot 3.3) obtains the actual dynamic RSocket port of the test server.
- `ObjectProvider<RSocketRequester.Builder>` creates a fresh builder per connection, avoiding retaining setup metadata from the previous user.
- `WebTestClient` tests the HTTP Basic admin policy; `RSocketRequester` actually sends RSocket frames.
- `StepVerifier.expectNext` verifies the stream delivers data, `then(...)` calls HTTP revoke mid-stream, and `expectError` verifies the stream is terminated.
- `@DirtiesContext` after the revocation test prevents the in-memory `revoked` registry state from affecting subsequent tests in the Spring test context.
- `requester.rsocket().dispose()` releases the client connection when the `Flux` completes/cancels; it **must not** be cited as proof the server auto-closes all connections in production.
- Integration tests do not assert an exact RSocket wire exception class; classes/error messages may be wrapped differently across versions.
- The tests do not prove TLS, global per-connection caps, multi-node revocation, external IdP revocation, login cookie logout, or exact time-to-revoke SLOs.
- `gradle test` runs tests only when dependencies/runtime are ready; results described in the lesson are **expected behavior**, not the execution output of a build run here.

Run:

```bash
gradle test
```

With wrapper:

```bash
./gradlew test
./gradlew test --tests example.rsquota.RSocketRevocationIntegrationTests
```

Test concurrency further with load tests:
- Open 3 request-streams with the same username `alice`: the third must fail with a quota error, while the first two continue.
- Open 5 total streams across users: the fifth must fail.
- Revoke while 2 streams are active: both receive the signal and permits drop to 0.
- Client cancels before revocation: must not double-release or produce negative counters.
- Failed SETUP: must not leak connection permits.
- TCP disconnect/kill client: subscription cleanup runs or a watchdog detects the dead connection.
- Burst 1,000 reconnects: edge handshakes/IP quotas must still protect.
- Send oversized frames/metadata: transport decoder must reject per configured limits.

## 11. What the demo does not solve yet and how to extend it

### 11.1. Physical connection caps

`ActiveStreamRegistry` counts logical stream leases. A client can open many TCP connections without subscribing to a route, keeping `activeStreams=0` while file descriptors and memory climb.

Production must add **transport admission** as in section 5, truly tracking `activeConnections`, SETUP attempts/sec, connection durations, max idle/handshake times, and per-IP/per-principal quotas.

### 11.2. Revoking Authentication at SETUP

User `alice` still exists in `MapReactiveUserDetailsService` after `registry.revoke("alice")`, because the endpoint only blocks application stream entitlements. To block **reconnect** right at SETUP:
- `ReactiveAuthenticationManager`/validators must consult the revocation store (by key ID/subject/session version) when authenticating.
- Or when SETUP is authenticated, the connection admission policy checks user/tenant active status from a trusted store.
- With JWT, verify exp/issuer/audience + denylist/`jti`/token version/central entitlement per threat model.
- Revoke events must invalidate auth/authorization caches, not only the handler registry.

Never let an in-memory bean's `revoked` flag act as **the single source of truth** across multi-node deployments or process restarts.

### 11.3. Proactively closing physical connections

If policy requires tearing down **all of a user's connections**, beyond cancelling logical streams you need to:
- Record connection ID, verified principal, and the underlying `RSocket` handle in a connection registry upon successful SETUP;
- Register `onClose`/dispose callbacks to remove registry entries and release permits exactly once;
- On revocation, snapshot the subject's connections and call `dispose()`/close the appropriate transport handle;
- Emit an error/control message with an explicit contract if clients must distinguish revocation from network outages;
- Ensure reconnects are blocked by the updated AuthN policy instead of immediately reopening sockets infinitely.

Calling `RSocketRequester.rsocket().dispose()` in a **client test** does not implement a server-side force-disconnect registry. Never write "revocation closes the TCP session" in a design unless a server connection handle registry exists and is tested on the wire.

### 11.4. Switching from Simple Authentication to JWT

With RSocket JWT:
- Add dependency/config for `ReactiveJwtDecoder`;
- Use `RSocketSecurity.jwt(...)` and Bearer Authentication metadata;
- Check signature, issuer, audience, `exp`/`nbf`, and scopes;
- Use identity key `issuer + subject + tenant`, not bare username;
- If the token is at SETUP, ensure max connection lifetime does not exceed token lifetime per policy;
- If tokens are per-request, evaluate the token on each request; already-open streams still need dedicated rechecks/cancellation;
- If JWTs have no server-side session, "logout" does not mean immediate token revocation until `exp` unless a denylist/introspection/version check exists.

This is an **architectural variant**, not a YAML snippet that safely turns Simple Authentication into JWT without configuring issuers/keys/validators.

## 12. Multi-node revocation: pub/sub is fast but not enough as a source of truth

### 12.1. How one node differs from three nodes

```text
                  Admin: revoke alice
                          |
                          v
                  Durable store
                 revoked(alice)=true
                          |
                          v
                 Revocation event bus
                    /     |     \
                   v      v      v
               Node A   Node B  Node C
                |         |       |
             streams    streams  streams
              alice      alice    alice
                |         |       |
              cancel    cancel   cancel
```

If the load balancer sends the admin request to Node A, a `ConcurrentHashMap` on Node A does not update registries on B/C. Every node holding active streams needs events or polling to cancel.

### 12.2. Durable record + notify + periodic reconcile

Practical design:
1. Write revoked state/version to a **durable trusted store** (appropriate DB/Redis, with TTL/policy).
2. After commit succeeds, publish event `subject,tenant,revocationEpoch,eventId`.
3. Each node subscribes to events, updates local revoked state, snapshots leases/connections, and terminates them.
4. New admissions always check the durable state or a cache with tight TTL/invalidation rather than relying solely on delivered events.
5. After node restart/reconnect, load revoked state rather than starting from `false`.
6. If the event bus drops notifications, periodic reconciliation/outbox/durable streams catch up.
7. Use event IDs/versions to prevent out-of-order revoke/restore from reopening permissions erroneously.
8. Measure delay from revocation commit to termination of the last active stream, setting real SLAs.

**Note that Redis Pub/Sub is not durable like a persistent message queue**; disconnected subscribers can miss events. Never use it as the sole mechanism blocking reconnects; pair it with a durable revocation store or Redis Streams/outbox as appropriate.

### 12.3. Cluster-wide global quotas

For example, a local registry caps at 4 streams/node. Running 5 nodes allows up to 20 streams if clients spread across nodes. If the contract requires **4 streams across the entire cluster**:
- Use a central atomic semaphore/counter/lease store (Redis Lua/DB) with TTL/fencing or a coordinator;
- Per-node local limits are still needed to protect individual processes;
- Lease expiration handles node crashes;
- Proper heartbeats/renewals/cleanup; never trust counters forever if a node dies;
- Choose the trade-off between strict global consistency and availability.

Never call an in-JVM `AtomicInteger` a "global quota" when the application runs across multiple nodes.

### 12.4. Revocation races and in-flight data

Scenario:
1. Node B already encoded a sensitive event for Alice.
2. Node A commits revocation.
3. The event reaches Node B 100 ms later.
4. A payload B already sent before receiving revocation may reach the client after the revocation timestamp.

There is no simple way to "erase from the network" bytes already sent. If strict non-disclosure after a policy timestamp is required:
- enforce version/epoch gating right at the data-send boundary;
- stop sources/quiesce subscriptions and check acknowledgments;
- explicitly define revocation effective time, propagation window, and in-flight items;
- use short-lived streams or server-driven reconnects when stronger guarantees are required.

**Never claim "instant 0ms revocation" just because `Sinks.One.tryEmitError` runs fast in a single JVM**.

## 13. Token/session expiry, idle timeout, and reconnect

### 13.1. Different deadlines

| Deadline | Protects | How to apply |
| --- | --- | --- |
| TLS handshake deadline | CPU/socket resources | Netty/ingress timeout |
| SETUP authentication deadline | Identity store/JWT decoder | Reactive manager timeout |
| Connection idle timeout | Idle FDs/memory | Keepalive + transport/ingress policy |
| Request response deadline | In-flight requests | Reactor `timeout` + cancellation |
| Subscription max lifetime | Long-running streams | `take(Duration)`, forced reconnect |
| JWT `exp` | Token validity | Decoder at authentication + stream policy |
| Server-side session expiry | Stored login/entitlement grants | Central store TTL/revocation event |
| Revocation propagation SLA | Active connection/stream termination | Durable state + broadcast + reconciliation |

**Timeout != revocation.** A stream expiring naturally via `take(Duration)` can complete normally; revocation in the demo emits error `STREAM_REVOKED`; a network disconnect is yet another error category. Clients must classify them to choose reconnect policies.

### 13.2. Client behavior when a stream is revoked

Reasonable:
- Stop automatically retrying with the same credentials;
- Clear/update local auth state per product policy;
- Only request new tokens/reauthenticate once the user or service is re-granted access;
- Do not spam the token endpoint or TCP reconnect in a tight loop;
- Log sanitized event categories, never raw credentials;
- Show UI "session or access expired" per UX without leaking secrets.

Unreasonable:

```java
// WRONG: infinitely retries all errors, including revoked/invalid credentials.
requester.route("ticks.watch")
        .data(100)
        .retrieveFlux(String.class)
        .retry();
```

Retries must target classified **network/transient failures** only, using exponential backoff/jitter, retry caps, total deadlines, and compliant token-refresh behavior. Invalid credentials/revoked/permission denied are not transient availability errors.

### 13.3. Connection keepalive does not replace JWT revalidation

RSocket has `KEEPALIVE` and request demand frames for connectivity/flow control. `KEEPALIVE` does not mean the IdP just confirmed the user still has permissions. A "healthy" TCP socket can hold a policy-stale identity. Therefore heartbeats/keepalives and authentication TTL/revocation must be managed independently.

### 13.4. HTTP logout and RSocket revocation bridge

If an app has WebFlux browser login and RSocket-over-WebSocket:
- HTTP logout invalidates the `WebSession`/cookie;
- Emit an application revocation event keyed by verified user/session key;
- Map the event to the right open RSocket connections/subscriptions under that identity;
- Cancel/dispose per policy;
- Block reconnect/reauth using the old session at both handshake and RSocket SETUP;
- Test browsers with two tabs, multiple devices, multiple nodes, and token/cookie rotation.

**Do not** rely on HTTP's `SecurityWebFilterChain` to re-authenticate every RSocket payload. The two pipelines have independent lifecycles after upgrade.

## 14. Protecting data in shared streams and request-channel

### 14.1. Never use a principal from request data

Wrong:

```java
// WRONG: tenantId is caller-supplied without verifying permissions.
@MessageMapping("prices.tenant")
Flux<Price> prices(String tenantId) {
    return repository.watchTenant(tenantId);
}
```

This is an anti-example, not runnable project code. A client can guess tenant B and subscribe to the wrong data.

Right in principle:

```java
// Illustrative snippet: verifiedIdentity must come from RSocket AuthN.
return currentIdentity()
        .flatMapMany(identity -> repository
                .watchTenant(identity.tenantId())
                .filter(price ->
                        price.allowedFor(identity.subject())));
```

Per-subject/tenant quotas must use the **verified** identity. If the request contains a tenant field, verify it belongs to the principal's allowed tenants and policy queries.

### 14.2. Each channel message may carry different permissions

RSocket `request-channel` has a stream of inbound/outbound payloads. Route auth on the initial request does not guarantee each item is valid:
- Cap item count and size per payload;
- Validate schema and tenant/resource IDs;
- Rate-limit per user/tenant;
- Never let subsequent frames bypass application-level policies;
- On revocation, cancel the entire channel or drop/refuse events per contract;
- Run cleanup for database/broker producers and inbound subscribers.

Never use `anyExchange().permitAll()` in `RSocketSecurity` as an excuse to drop all per-item checks. It handles matching for protocol payloads without routing metadata, not permanent business authorization.

### 14.3. Slow consumer security

A slow subscriber can hold sensitive events in a buffer long **after permissions are revoked**. On revocation:
- Cut the source and release buffers;
- If buffers hold user/tenant data, ensure they are never re-emitted to another subscriber;
- Never use a global multicast `Sink` without tenant isolation;
- Replay event history only per entitlement and retention policy;
- Consider non-replay control signals for revocation, and durable records for policy.

Using `Sinks.many().multicast().directBestEffort()` lets slow subscribers drop events, which does not fit every domain. Using `Sinks.many().replay().all()` can grow buffers unboundedly and replay sensitive data to later subscribers. Pick a strategy matching data sensitivity and correctness.

## 15. Observability and operations runbook

### 15.1. Key metrics

| Metric | Meaning |
| --- | --- |
| `rsocket_active_connections` | Active sockets per node/transport, measured at acceptor |
| `rsocket_setup_attempts_total{result}` | SETUP success/rejected/auth error |
| `rsocket_active_streams` | Concurrent streams actually holding leases |
| `rsocket_stream_reject_total{reason}` | Per-user/global quota, revoked, policy |
| `rsocket_stream_duration_seconds` | Subscription duration p50/p95/p99 |
| `rsocket_stream_cancel_total` | Client/network/service cancellations |
| `rsocket_revocation_events_total` | Revocation events received/processed |
| `rsocket_revocation_to_close_seconds` | Delay from revocation to last stream termination |
| `rsocket_message_bytes` | Payload bytes/frame size distribution |
| `rsocket_buffer_pending_items` | Queue/slow subscriber pressure |
| `rsocket_reconnect_total` | Reconnect attempts, auth vs. network reasons |
| `jvm_threads, fd_used, heap_used` | Node-wide resource pressure |

Never put raw JWTs, passwords, session cookies, emails, high-cardinality full subject IDs, or payload data into metric labels. Use allowlisted tenant/service aliases or approved hashed/aggregated dimensions.

**Difference:** `rsocket_active_streams` is measured in the demo; `rsocket_active_connections` must be measured at transport/acceptor—**never use one variable for both**.

### 15.2. Runbook: when active streams keep growing

1. Check `activeConnections` and `activeStreams` separately.
2. Inspect top routes, tenants, subscription durations, and buffer pressure.
3. Verify `doFinally`/`Flux.using` releases on normal/error/`CANCEL`.
4. Check whether clients are infinitely auto-reconnecting/retrying.
5. Check broker watches/subscriptions when RSocket clients disconnect.
6. Check proxy idle timeouts and keepalive mismatches.
7. Test revoking a test identity in staging; active stream count must drop.
8. Check for negative counters or leaks after node restarts/abrupt disconnects.
9. If facing a connection flood, throttle at ingress/Netty, not only stream quotas.
10. If CPU is high from per-request JWT verification, review caching and rate limiting without relaxing trust/expiry.
11. Never log payloads/headers containing raw credentials to debug.
12. Design drain/rolling restarts: stop new admissions, notify clients, cancel/close streams, wait a bounded drain period.

### 15.3. Runbook: revoked user still receives data

1. Identify whether revocation was applied at the Auth Server, `WebSession`, entitlement DB, or local registry.
2. Check exact IDs: `issuer+sub`, tenant, session ID/`jti`; avoid confusing human display names.
3. Confirm durable state update committed.
4. Check event bus/outbox, offsets, subscriber lag, or Redis Pub/Sub drops.
5. Check which node/connection the user is actually attached to.
6. Check whether the stream is emitting buffered events or freshly reading the DB.
7. Check whether the handler properly cancels sources and cleans up.
8. Check whether reconnects pass through the new AuthN/SETUP validator.
9. Check whether the user holds a second still-valid token/credential.
10. Define the agreed SLA/consistency window; avoid claiming "0 delay" without evidence.

## 16. Common pitfalls

| Symptom | Main cause | Fix |
| --- | --- | --- |
| Stream quota doesn't stop 10,000 TCP sockets | Logical quota != physical cap | Edge/acceptor connection admission |
| `activeStreams` goes negative | Double release | `AtomicBoolean`/`Flux.using` lifecycle |
| Stream never ends | Missing duration/item cap | `take(Duration)` + max item count |
| Subscriber leaves yet broker keeps emitting | Upstream ignores `CANCEL` | Dispose/clean up source and test disconnect |
| Revoked user reconnects successfully | SETUP manager skips durable revoked state | Add validation/rejection in AuthN |
| Revoking on node A doesn't stop node B stream | Local-only registry | Broadcast + durable shared state |
| Using Redis Pub/Sub alone and losing revocations | Events lost while subscriber offline | Durable store/stream/outbox + reconciliation |
| JWT `exp` passes yet stream stays alive | No automatic mid-stream exp recheck | Max lifetime/recheck/cancel policy |
| After HTTP logout, RSocket still receives data | `WebSession` != RSocket connection | Explicit revoke bridge/connection registry |
| `anyExchange().permitAll()` taken as opening all data | Misunderstood RSocket matchers | Route auth + per-item tenant check |
| Buffers grow unboundedly | Unbounded queue/replay/prefetch | Bounded buffers, slow consumer policy |
| One user hogs all streams | Missing per-subject concurrency cap | Atomic per-user quota |
| 4 streams/node yet 5 nodes allow 20 | Local != cluster-global | Distributed lease/quota |
| Revoke emitted yet one more event arrives | Network/in-flight race | Define effective time and egress gate |
| Client retries continuously when revoked | Retrying all exceptions | Classify auth vs. transient network errors |
| Keepalive alone assumed to mean valid identity | Heartbeat != AuthN | Token/session expiry/revocation checks |
| HTTP tests all pass yet RSocket leaks | `WebTestClient` sends no RSocket TCP | `RSocketRequester`/`StepVerifier` |
| Revoke returns HTTP 204 yet other nodes haven't applied it | Local method vs. distributed commit | Acks/metrics/consistent state |
| Client caches same `RSocketRequester` for all users | Cross-tenant credential leakage | Scoped requester/per-request metadata |
| Disabling certificate verification for demos | TLS trust errors ignored | Proper truststore/hostname SAN |
| Slot not freed after revocation | Cleanup didn't run on error | `Flux.using`/`doFinally` tests |
| Reading subject from payload | Attacker picks identity/quota key | Read verified principal from `SecurityContext` |

## 17. Self-check questions

**1. Can one physical RSocket connection hold multiple request-streams?**  
Yes. Multiplexing allows many streams on one connection; connection count alone does not measure total load.

**2. Does capping 100 connections guarantee at most 100 streams?**  
No. One connection can carry many concurrent streams.

**3. Does HTTP's `SecurityWebFilterChain` automatically cap RSocket TCP?**  
No. RSocket has its own acceptor/security pipeline.

**4. Does `RSocketSecurity` automatically authorize every item of a `Flux`?**  
Not by default. Route/SETUP auth is one layer; per-item data policies and revocation require dedicated logic.

**5. How does SETUP auth differ from per-request auth?**  
SETUP binds the connection's identity; per-request auth can switch identities per request on a shared connection.

**6. Does invalidating an HTTP `WebSession` automatically close an RSocket TCP socket?**  
No. You need a bridge/connection registry/notification mechanism.

**7. If a JWT's `exp` passes mid-stream, does RSocket automatically emit an error immediately?**  
Not guaranteed. You need stream deadlines/revalidation/revocation policies.

**8. What is the first requirement when receiving a revocation?**  
Persist/set the revoked state so no new work is admitted, then signal/cancel active streams.

**9. Why use `Sinks.One` instead of an infinite multicast stream per lease?**  
A single terminal signal retains its outcome, preventing missed revoke signals if a subscriber attaches after the event.

**10. Why use `Flux.using` for active stream leases?**  
To acquire on subscribe and release on complete/error/cancel, avoiding leaks or double-releases.

**11. Does `take(Duration)` automatically cap buffer memory?**  
No. Upstream/brokers/codecs must enforce bounded buffers and payload policies.

**12. Does sending `CANCEL` remove session credentials from the IdP?**  
No. It cancels a single logical subscription, without revoking identity credentials.

**13. Does `maxConnections` in a Reactor Netty client pool apply to the inbound RSocket server?**  
Not by default. Configure the proper transport/server layer.

**14. Is a single-JVM `AtomicInteger` a global quota across multiple Kubernetes pods?**  
No. It is process-scoped only.

**15. What if a Pub/Sub event is lost while a node is offline?**  
The node can miss the revocation. Use durable state/outbox/reconciliation and check at admission.

**16. Is it a bug if Simple Authentication SETUP still passes after `revoke` in the demo?**  
Not a code execution bug; the demo only revokes **stream admission** rights. Production wanting to block SETUP must check revoked state in `ReactiveAuthenticationManager`/connection policy.

**17. What is needed to close physical RSocket connections on revocation?**  
A registry mapping verified identity → connection handles, closing/disposing on revocation, `onClose` cleanup, and blocking reconnects.

**18. What error does the RSocket client receive when revoked?**  
The demo emits application-level `STREAM_REVOKED` error; the wire exception may be wrapped by the RSocket stack. Do not treat it as HTTP 401/403.

**19. Stream quota is 2/user, and Alice opens 2 connections with 1 stream each?**  
Both streams consume her quota; Alice's third stream is denied regardless of which socket is used.

**20. Why must quotas use the verified subject rather than a tenant ID from the request payload?**  
Because an attacker can spoof request payloads to evade quotas or read other data.

**21. When is a maximum connection lifetime needed?**  
When SETUP auth/tokens have TTLs or policy requires periodic re-auth/reconnect to avoid overly long-lived connections.

**22. Does keepalive replace token expiry checks?**  
No. Keepalive only checks transport/protocol connectivity/liveness.

**23. Why is revoking after buffering sensitive events hard?**  
Payloads may already be encoded/in-flight; you must define effective times and egress gating, as sent bytes cannot be unsent.

**24. If stream count drops to 0 yet CPU remains high, what could be causing it?**  
Idle sockets, handshake floods, uncancelled decoder/broker work, or TLS/Netty pressure; inspect per-layer metrics.

**25. If a stream carries financial records that cannot be lost, can you arbitrarily use `onBackpressureDrop`?**  
No. You need proper durable delivery/ack/replay policies and bounded backpressure.

**26. Why not retry infinitely after `STREAM_REVOKED`?**  
It is a policy denial, not a transient outage; fresh reauth/grants are required.

**27. What does `@DirtiesContext` accomplish in the revocation integration test?**  
Prevents the in-memory `revoked` flag from remaining set and altering subsequent test cases.

**28. Where should physical connection counts be measured?**  
At ingress/Netty acceptor/transport connection registries, never substituting `activeStreams`.

**29. Why test cancel and error alongside normal completion?**  
Permits must be released on every terminal signal; happy-path-only tests can hide memory/slot leaks.

**30. What is the single most important principle of revocation on long-lived RSocket streams?**  
Deny new admissions from a trusted source, send cancel/error to active subscriptions, release resources, handle reconnects and distributed consistency, and check tenant/owner before any sensitive data.

**Remember:** With RSocket, security does not stop at SETUP AuthN and a `route(...).hasRole(...)` rule. You need **multi-layer quotas** (sockets, SETUP, request-streams, payloads/buffers, durations), **exact resource cleanup**, and a **revocation lifecycle** (durable deny state → notify nodes → cancel active streams/connections → block reconnects → audit). Specifically, **terminating a `Flux` is not closing a socket**, and **HTTP logout does not automatically revoke RSocket**.

## References

- [Spring Security — RSocket Security](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html): SETUP/request authentication, `authorizePayload`, Simple/JWT metadata.
- [Spring Security — RSocketSecurity API](https://docs.spring.io/spring-security/reference/6.3/api/java/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html): `RSocketSecurity` DSL, payload interceptors.
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): request-stream/channel, message routing, SETUP, transport, backpressure.
- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): RSocket server TCP/WebSocket, requester, auto-configuration.
- [Spring Boot 3.3 — RSocketServerCustomizer](https://docs.spring.io/spring-boot/docs/3.3.0/api/org/springframework/boot/rsocket/server/RSocketServerCustomizer.html): custom server acceptor/transport integration.
- [Spring Boot 3.3 — LocalRSocketServerPort](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPort.html): dynamic test port.
- [Project Reactor — Flux.using / usingWhen](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): resource lifecycle, cancellation, `takeUntilOther`.
- [Project Reactor — Sinks](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html): one-shot terminal signals, multicast/replay, backpressure behavior.
- [Project Reactor — Backpressure and Context](https://projectreactor.io/docs/core/release/reference/): demand, cancellation, Reactor Context.
- [RSocket Protocol](https://rsocket.io/about/protocol/): SETUP, REQUEST_STREAM, REQUEST_N, CANCEL, KEEPALIVE, ERROR.
- [RSocket — Authentication Metadata Extension](https://github.com/rsocket/rsocket/blob/master/Extensions/Security/Authentication.md): Simple/Bearer metadata formats.
- [OWASP — Denial of Service Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html): resource quotas and overload policies.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): credential lifecycle, error handling, and brute-force protection.
