# Distinguishing Identity at Connection Setup vs. Per-Payload Processing

## 1. The core question: who owns the connection, and who is making the request?

In Spring Security reactive, **RSocket** differs from HTTP in that a connection can live a long time, carry many concurrent requests/streams, and transmit data bidirectionally. When using RSocket with a Gateway, service-to-service communication, or multi-user applications, you cannot assume that **the party establishing the connection** is **the user of every request** passing through that connection.

Consider an example:

~~~text
                           A long-lived RSocket TCP connection
Gateway backend G ─────────────────────────────────────────► RSocket service
  SETUP identity: gateway-service / ROLE_CONNECT
            │
            ├─ REQUEST_RESPONSE route=account.me
            │      request identity: Alice / ROLE_VIEWER
            │      → returns Alice's profile
            │
            ├─ REQUEST_STREAM route=report.feed
            │      request identity: Bob / ROLE_VIEWER
            │      → streams reports belonging to tenant Bob
            │
            ├─ REQUEST_STREAM route=report.feed
            │      request identity: Alice / ROLE_VIEWER
            │      → streams reports of tenant Alice
            │
            └─ REQUEST_CHANNEL with multiple subsequent PAYLOADs
                   → identity / policy is not automatically
                     re-authenticated for every PAYLOAD frame
~~~

Here there are **at least two layers of identity**:

1. **Connection identity**: who is allowed to open and maintain an RSocket connection? Usually a personal device or a gateway/service account, authenticated at **SETUP**.
2. **Request/stream identity**: who is requesting a specific operation? It may be Alice or Bob, authenticated via the authentication metadata of the **stream-initiating request**.

A third issue only appears with long-lived streams:
3. **Authorization while the stream is still running**: if Alice's permission is revoked after opening `REQUEST_STREAM`, does the server re-check before emitting the next event?

**Do not confuse:** "per-request authentication" **does not mean** Spring Security automatically re-authenticates on **every PAYLOAD frame** appearing inside a stream. Per RSocket Security documentation, `anyRequest()` applies to request frames that carry metadata; subsequent payloads typically lack the same metadata and are not automatically checked by a new authorization rule. The application must design additional **per-event checks** when risk or stream duration requires it.

### Learning outcomes

After this lesson, you can:
- Describe `REQUEST_RESPONSE`, `REQUEST_STREAM`, `REQUEST_CHANNEL`, `REQUEST_FNF`, `SETUP`, and `PAYLOAD` interactions.
- Distinguish **SETUP** authentication, **initial request** authentication, and **per-event** re-authorization inside a stream.
- Choose between per-user dedicated connections, multi-user shared connections, or a combined two-layer authentication model.
- Configure `@EnableRSocketSecurity`, `RSocketSecurity`, `PayloadSocketAcceptorInterceptor`, `setup()`, `route()`, and `anyRequest()`.
- Send `UsernamePasswordMetadata` via `setupMetadata(...)` or `metadata(...)` using `SimpleAuthenticationEncoder`.
- Understand the path of JWT bearer metadata, `ReactiveJwtDecoder`, and `jwt(...)` when using access tokens instead of Simple Authentication.
- Retrieve `Authentication` from `ReactiveSecurityContextHolder` without inferring identity from a `userId` in the payload.
- Maintain tenant/owner boundaries when multiple requests/streams run concurrently on a single connection.
- Understand how to handle expiring tokens, revoked permissions, cancellation, reconnect, resume, backpressure, and resource cleanup.
- Practice Java 17+ Spring Boot RSocket/Spring Security and test with `StepVerifier` against a real RSocket TCP server.
- Recognize limitations of the sample tests and build a production testing checklist.

## 2. RSocket is not "a long-running HTTP request"

An RSocket connection usually starts with a **`SETUP`** frame and can then carry multiple streams with different stream IDs. RSocket supports multiplexing and Reactive Streams backpressure; either the responder or the requester can initiate interactions permitted by the protocol.

| Frame/interaction | Meaning | Identity point to watch |
| --- | --- | --- |
| `SETUP` | Establishes the connection and media types/connection metadata | Can carry connection-level credentials |
| `REQUEST_RESPONSE` | One request and one result | Can carry per-request credentials |
| `REQUEST_STREAM` | One request, multiple returned elements | Initial request metadata may hold identity; subsequent elements need their own policy |
| `REQUEST_CHANNEL` | One request with two incoming/outgoing data streams | Do not treat every PAYLOAD in the channel as a new login |
| `REQUEST_FNF` | One message without waiting for a response payload | Must authorize upfront; no response does not mean skipping permission checks |
| `PAYLOAD` continuation | Data part within an already-open request/response stream | Does not run `authorizePayload` by default as a new request |
| `REQUEST_N` | Demand/backpressure | Not a request identity; must not be used to switch users |
| `CANCEL` | Closes/cancels the stream | Must stop ongoing work and release resources |
| `METADATA_PUSH` | Connection-level metadata, not tied to a specific request | Do not treat it automatically as a command to switch the whole connection's principal |

Timeline diagram:

~~~text
TCP/WebSocket transport
        │
        ├──── SETUP (connection identity: gateway)
        │
        ├──── REQUEST_RESPONSE A (metadata: Alice)
        │            └──── PAYLOAD result A
        │
        ├──── REQUEST_STREAM B (metadata: Bob)
        │            ├──── PAYLOAD B1
        │            ├──── PAYLOAD B2
        │            └──── PAYLOAD B3
        │
        ├──── REQUEST_STREAM C (metadata: Alice)
        │            ├──── PAYLOAD C1
        │            └──── PAYLOAD C2
        │
        └──── ... connection remains open
~~~

**Principle:** The transport connection is a transmission medium; identity/authorization is an attribute of a verified security context within a **specific scope**. Never use connection ID, TCP peer IP, or "most recent user" as proof for all streams.

### 2.1. Metadata vs. data

An RSocket payload can have:
- **Data**: business content (e.g., tenant name, report ID, chat message).
- **Metadata**: routing, MIME, authentication metadata, or other protocol information.

The client **can write both data and metadata itself**. Security comes from the server **verifying authentication metadata**, not from it being labeled metadata. A data field `userId=admin` cannot substitute for credentials in authentication metadata.

### 2.2. RSocket and WebFlux: similarities and differences

WebFlux HTTP uses `ServerHttpSecurity`/`SecurityWebFilterChain`. An RSocket server uses `RSocketSecurity` and `PayloadSocketAcceptorInterceptor`. Both share reactive authentication/authorization concepts, but **do not automatically share the entire filter chain**.

HTTP `Authorization: Bearer token` belongs to HTTP headers. An RSocket bearer token travels via the **RSocket authentication metadata extension**, not as a default HTTP header per frame. If RSocket runs over WebSocket, HTTP Upgrade headers do not automatically act as credentials for each RSocket request after the handshake.

## 3. Three authentication strategies

### 3.1. A — Authenticate once at SETUP: one user per connection

Scenario:
- A mobile app opens a dedicated connection for Alice's account.
- A device or desktop app has only one active user at a time.
- The server receives metadata in `SETUP`, verifies it, and attaches the appropriate security context.

~~~text
Alice device
   │ SETUP Bearer(Alice) or SimpleAuth(Alice)
   ▼
RSocket connection Alice
   ├─ request 1 → Alice
   ├─ request 2 → Alice
   └─ stream 3  → Alice
~~~

**Pros:** the client does not need to resend credentials on every request; simple for a single user; low overhead.

**Limitations:**
- Connection identity can be reused on subsequent requests, but the token at SETUP **is not automatically revalidated when `exp` arrives**.
- If Alice logs out, switches users, has permissions revoked, or her token expires while the connection is open, you must actively **close the connection, reauthenticate/reconnect, expire streams, or check policy over time**.
- Connections may be pooled/reused unexpectedly, breaking the "one connection = one user" assumption.
- On Alice's connection, a request payload must never be allowed to self-declare `userId=bob` and read Bob's data.

Choose setup-only when you have architectural guarantees that the connection truly belongs to **one user**, has proper lifecycle/revocation handling, and the app knows how to handle session refresh.

### 3.2. B — Per-request authentication: one connection, many users

Scenario:
- A web backend/service B maintains **one shared RSocket connection** to service A.
- Backend B serves Alice, Bob, and Carol across many HTTP requests.
- Each RSocket request from B passes the corresponding user's credentials/token rather than taking the user from the SETUP connection.

~~~text
Web backend (shared RSocket connection)
   │ SETUP without user or only backend service identity
   │
   ├─ REQUEST_RESPONSE metadata=Alice JWT → process Alice
   ├─ REQUEST_STREAM metadata=Bob JWT     → stream Bob
   └─ REQUEST_RESPONSE metadata=Carol JWT → process Carol
~~~

**Pros:** a single connection serves many users without mixing `SecurityContext`; each request's permissions remain isolated.

**Conditions:** the client must attach the exact credentials **of the user making that request**, and the server must verify issuer/audience/signature/roles for each request. **Do not** attach credentials to a shared `RSocketRequester.Builder` if the goal is multiple users: `setupMetadata` belongs to the connection and does not change per user.

A dangerous bug:

~~~java
// ANTIPATTERN: global variable for a shared connection pool.
static volatile String currentUser;

// Request A arrives: currentUser = "alice"
// Request B arrives: currentUser = "bob"
// Stream A reads currentUser → suddenly sees Bob.
~~~

Identity must flow through request-specific metadata into the **Reactor security context of that specific stream**. Never use `ThreadLocal` or global variables to hold users across asynchronous streams.

### 3.3. C — Authenticate both SETUP and per-request

This model fits a shared gateway/backend that needs to enforce two different permissions:

~~~text
SETUP:
   service account = gateway
   authorities = [ROLE_CONNECT]
   → allowed to open connection, NOT allowed to view user data

REQUEST Alice:
   user account = alice
   authorities = [ROLE_VIEWER]
   → allowed to execute requests viewing Alice's data

REQUEST Bob:
   user account = bob
   authorities = [ROLE_VIEWER]
   → allowed to execute requests viewing Bob's data
~~~

Rules:
- `SETUP` requires authority `ROLE_CONNECT`.
- Business routes require `ROLE_VIEWER` from the request identity.
- Users Alice/Bob **do not have `ROLE_CONNECT`**, so they cannot establish a "gateway" connection themselves.
- The gateway service account **does not have `ROLE_VIEWER`**, so it cannot read resources if per-request credentials are omitted.
- If Alice/Bob belong to different tenants, business authorization must check the tenant per request and resource.

**This is not magical gateway delegation:** the backend must verify both the service SETUP credential and the user request credential; the gateway must not send a fake header or plain text metadata `role=VIEWER` to grant access.

## 4. Spring Security RSocket mechanics

### 4.1. Classes and extension points

| Component | Role |
| --- | --- |
| `@EnableRSocketSecurity` | Enables RSocket Security configuration |
| `RSocketSecurity` | Payload-based authn/authz configuration DSL |
| `PayloadSocketAcceptorInterceptor` | Result of `rsocket.build()`, participates in request interception |
| `SecuritySocketAcceptorInterceptor` | Attaches the payload interceptor to the RSocket socket acceptor |
| `AuthenticationPayloadInterceptor` | Extracts credentials/delegates authentication via the manager |
| `AuthorizationPayloadInterceptor` | Runs authorization rules for matching payload exchanges |
| `ReactiveAuthenticationManager` | Non-blocking credential authentication |
| `MapReactiveUserDetailsService` | In-memory demo users; not a production identity store |
| `simpleAuthentication(...)` | RSocket Simple Authentication Metadata |
| `jwt(...)` | Bearer JWT metadata, requires `ReactiveJwtDecoder` |
| `authorizePayload(...)` | Rules for `setup()`, `route()`, `anyRequest()`, `anyExchange()` |
| `RSocketRequester` | Client builder, setup metadata, and request metadata |
| `ReactiveSecurityContextHolder` | Reads `Authentication` from the reactive execution context |

Spring Boot RSocket server auto-configuration usually attaches `SecuritySocketAcceptorInterceptor` automatically when the right dependencies are present; if building a raw RSocket server outside Boot, you must wire the interceptor manually. **Do not claim the server is protected just because a class has annotations if the actual interceptor is not in the socket acceptor path**.

### 4.2. Basic authn/authz configuration

~~~java
@Configuration
@EnableRSocketSecurity
class SecurityConfig {

    @Bean
    PayloadSocketAcceptorInterceptor interceptor(
            RSocketSecurity rsocket) {

        rsocket
            .authorizePayload(authorize -> authorize
                .setup().hasRole("CONNECT")
                .route("identity.whoami").hasRole("VIEWER")
                .route("tenant.feed").hasRole("VIEWER")
                .anyRequest().denyAll()
                .anyExchange().permitAll()
            )
            .simpleAuthentication(Customizer.withDefaults());

        return rsocket.build();
    }
}
~~~

This is an **excerpt**; the full file is in section 8. Meaning:
- `setup().hasRole("CONNECT")` only accepts connections with `ROLE_CONNECT`.
- `route("identity.whoami").hasRole("VIEWER")` checks requests with viewer permission; identifies the route from request metadata.
- `route("tenant.feed").hasRole("VIEWER")` is a gate on the **stream-opening request**, not an automatic check on every emission.
- `anyRequest().denyAll()` rejects requests with unpermitted routes; preserve matcher ordering.
- `anyExchange().permitAll()` permits exchanges that are not requests with route/metadata; **does not** mean protecting every element with the same rule. Subsequent PAYLOAD frames fall outside ordinary route authorization.
- `simpleAuthentication` supports standard RSocket authentication metadata, not self-declared roles from JSON data.

**Warning:** Rules are evaluated in order; the first matching rule decides. Placing `anyRequest().permitAll()` before `route(...).hasRole(...)` leaves the route unprotected.

### 4.3. SETUP authentication vs. @ConnectMapping

`@ConnectMapping` is a handler invoked by Spring Framework when handling connection setup for setup routes/data. It can serve application logic at connect time, but **is not itself a secure authentication mechanism**.

Do not take `setupData("alice")` from the client and treat it as a logged-in user. Authentication must go through `RSocketSecurity`/credential validation. Nor should `@ConnectMapping` manually `subscribe()` to a long stream and allow logic to proceed before connection authentication completes.

## 5. Sending credentials in the right place with RSocketRequester

### 5.1. RSocket authentication metadata MIME type

The RSocket Authentication Metadata Extension has a well-known MIME type:

~~~java
MimeType authenticationMimeType =
    MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());
~~~

For Simple Authentication, Spring Security provides:
- `UsernamePasswordMetadata(username, password)`.
- `SimpleAuthenticationEncoder` to encode metadata in the right format.

### 5.2. Credentials at SETUP

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies ->
        strategies.encoder(new SimpleAuthenticationEncoder()))
    .setupMetadata(
        new UsernamePasswordMetadata("gateway", "connect-pass"),
        authenticationMimeType)
    .tcp("localhost", 7000);
~~~

This is an example of a client with a `gateway` connection identity. `setupMetadata(...)` is attached to the connection when sending SETUP; it **does not** automatically change when Bob/Alice share the same requester.

### 5.3. Credentials at REQUEST

~~~java
Mono<String> alice = requester
    .route("identity.whoami")
    .metadata(
        new UsernamePasswordMetadata("alice", "alice-pass"),
        authenticationMimeType)
    .retrieveMono(String.class);

Mono<String> bob = requester
    .route("identity.whoami")
    .metadata(
        new UsernamePasswordMetadata("bob", "bob-pass"),
        authenticationMimeType)
    .retrieveMono(String.class);
~~~

Both publishers use **the same `RSocketRequester`**, but different request metadata. The server must never read identity from a connection-level `currentUser` variable.

### 5.4. Bearer JWT at SETUP or request

When using OAuth2/JWT instead of Simple Authentication, Spring Security supports `BearerTokenMetadata`:

~~~java
MimeType authMimeType =
    MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

BearerTokenMetadata aliceToken = ...; // trusted access token from AS

// SETUP: token bound to the connection.
RSocketRequester perUser = RSocketRequester.builder()
    .setupMetadata(aliceToken, authMimeType)
    .tcp("localhost", 7000);

// REQUEST: token attached to a single request on a shared connection.
Mono<String> oneRequest = sharedRequester
    .route("identity.whoami")
    .metadata(aliceToken, authMimeType)
    .retrieveMono(String.class);
~~~

**This is a conceptual snippet, not a standalone file.** `BearerTokenMetadata` must be constructed from a valid access token per your SDK/API version, and the client must handle real credentials securely; there is no real Authorization Server in the Simple Authentication demo project.

Server RSocket Security:

~~~java
@Bean
PayloadSocketAcceptorInterceptor jwtRSocket(
        RSocketSecurity rsocket) {

    return rsocket
        .authorizePayload(authorize -> authorize
            .setup().authenticated()
            .anyRequest().authenticated()
            .anyExchange().permitAll())
        .jwt(Customizer.withDefaults())
        .build();
}
~~~

JWT configuration requires a **trusted `ReactiveJwtDecoder`** (issuer, audience, signature, expiry, algorithms). Do not build a decoder based solely on an un-allowlisted `iss`. If using two identity tiers (service SETUP + end-user REQUEST), define permissions for setup/request per token policy and how the manager maps authorities, rather than copying `authenticated()` for every frame.

### 5.5. Choosing the right credentials for a shared connection

Never use:
- `setupMetadata(userAliceToken)` on a connection pool shared across all users.
- Mutating an `AtomicReference<BearerTokenMetadata> currentToken` on every request because another stream can read the wrong one.
- Copying an HTTP request's `Authorization` header from a Servlet `ThreadLocal` into an unbound Reactor callback.
- Trusting a `payload.userId` or `payload.role` as proof of identity without corresponding token verification.

The right design is to **propagate verified end-user credentials via the request context**, place them into the corresponding request's metadata, and re-authenticate them at the RSocket Resource Server.

## 6. Identity on the first request differs from per-item stream permissions

This is the core focus of "long streams."

### 6.1. A REQUEST_STREAM has many elements but one authorization point at the start

~~~text
T0  REQUEST_STREAM "tenant.feed"
    request metadata: Alice's JWT
    → signature/issuer/audience/exp VALID
    → route authorization PASS
    → stream starts

T1  PAYLOAD item #1
T2  PAYLOAD item #2
T3  Alice's tenant access is revoked
T4  PAYLOAD item #3
T5  PAYLOAD item #4
~~~

If the server only checks permissions at T0, it can **still emit items #3 and #4**. That is not really a Spring Security bug; it is the time-of-check/time-of-use policy of an already-open subscription. Spring Security documentation describes request authorization on requests with metadata, not treating every continuation PAYLOAD as a brand-new request.

A system requiring early revocation must add one or more mechanisms:
- Check permissions **before querying/emitting each sensitive event**.
- Give streams a max duration, forcing the client to reconnect with fresh credentials.
- Proactively cancel/dispose streams when account/tenant membership is revoked.
- Limit token lifetimes and define semantics when a token expires mid-subscription.
- Enforce data boundaries at the **repository/owner/tenant query boundary** so the wrong resource is never emitted even while a stream is alive.
- If data is highly sensitive, reauthorize per item/tenant boundary or replace with short paged requests.

### 6.2. Each PAYLOAD in REQUEST_CHANNEL is not an independent request

`REQUEST_CHANNEL` sends multiple payloads into the server. RSocket carries routing/security metadata on the channel-initiating request, whereas subsequent `PAYLOAD` frames may carry no credentials and may not pass through `AuthorizationPayloadInterceptor` as new requests.

Therefore **never** say "RSocket automatically re-authenticates every message in a channel." If the application wants:
- One user for the whole channel: pin the verified principal at channel start and check role/tenant on each command payload.
- Multiple users in one channel: **do not** assume every message has an authenticated user just because it has a `userId` field. Design a protocol-level authenticated envelope or, better yet, separate requests/streams with their own auth metadata.
- Mid-stream user switching: requires cryptographically verified reauthentication bound to the channel/session with anti-replay/confused-deputy protection; never mutate a global variable.
- Runtime revocation: cancel/deny subsequent messages.

### 6.3. Authn per request does not mean authz per item

Four distinct protection levels:

| Level | Event | What is proven | What is **not** automatically proven |
| --- | --- | --- | --- |
| Connection | SETUP | Gateway/device is permitted to open the connection | Every user request belongs to the gateway |
| Request | Initial `REQUEST_STREAM` | A user has credentials/role to initiate the stream | The user still has permission minutes later |
| Per item | App-level check in `Flux` | The user is currently allowed to receive that item per policy | All other data is allowed |
| Data | DB query/tenant ACL | Each row/object falls within authorized scope | No data leak bugs exist on other paths |

A sound solution **explicitly** chooses which levels must be rechecked based on sensitivity, latency, and revocation requirements.

### 6.4. Example of per-emission authorization with Reactor

~~~java
// Architectural SNIPPET: not a standalone @MessageMapping.
Flux<Event> feed(Authentication authentication, String tenant) {
    String subject = authentication.getName();

    return eventStore.eventsForTenant(tenant)
        .concatMap(event -> membershipService
            .mayRead(subject, tenant, event.id())
            .flatMap(allowed -> allowed
                ? Mono.just(event)
                : Mono.error(new AccessDeniedException(
                    "Access revoked"))));
}
~~~

**Conditions for safety:** `eventStore.eventsForTenant` must filter by the right tenant before returning data; `mayRead` takes the user from verified `Authentication`, never from the event or a header. `concatMap` checks before each event is emitted. With database streaming queries that prefetch multiple rows, understand **prefetch/buffering** and whether data was already read/held in memory before the policy changed; "checking in `map`" does not make previously fetched rows vanish.

## 7. Expiration, logout, revocation, reconnect, and resume issues

### 7.1. JWT expires while the connection is still open

Suppose:
- T0: JWT `exp` is at T+5 minutes; the user opens an RSocket connection and `REQUEST_STREAM`.
- T+5: Token expires.
- T+7: Server is still emitting new PAYLOADs.

**Do not assume** Spring Security will automatically re-run `ReactiveJwtDecoder.decode(...)` when `exp` passes. The decoder is normally called at setup/request authentication time. If the subscription continues, the app needs a clear policy:
1. The stream is bounded to token `exp`; stop/cancel before or at `exp`.
2. The stream accepts the identity checked at open time, but has a short TTL and low-sensitivity data (the risk decision must be reviewed).
3. Re-auth on a new request after an interval; the user fetches a new access token and opens another subscription.
4. Check revocation/membership per emission against an internal system.

**Do not** rely on RSocket `KEEPALIVE` alone to conclude the user is still authorized; heartbeats verify transport liveness, not JWT validity.

### 7.2. User logs out in one tab while a stream in another tab keeps running

Logging out in the frontend or HTTP session does not automatically send cancellation to open RSocket streams. You need:
- Client cancels subscriptions and closes the connection if it is per-user.
- Server maintains a subscription registry (user/tenant/connection/stream) if active cancellation on revocation events is required.
- Update user/tenant state in the DB or a centralized entitlement service.
- Test logout/revocation at time T1 mid-stream, not only on the first request.
- Avoid keeping the user's refresh token in connection state as plain text or logs.

### 7.3. Reconnect vs. session resumption

- **Reconnect:** a new connection; SETUP auth must run again per policy; never trust an `authenticated=true` cache from the old connection.
- **Resume (if enabled):** the protocol can continue a stream after an interruption while state remains. Resuming **does not automatically mean OAuth2 reauthentication**. You must define resumption token/session policies, TTL, and post-reconnect end-user permissions.
- **Retry:** some clients auto-retry requests; never reuse an expired token or attach the wrong user due to thread/context switches.
- **Token refresh:** performed in the client/authorized user flow, then the new token is sent on a new request/connection; never "patch" the token string inside an already-authenticated stream.

### 7.4. Backpressure and security

RSocket backpressure does not replace authorization:
- `REQUEST_N` controls how many items may be sent, not permissions.
- Large queues can buffer data before permissions are revoked. Prefer limiting buffering and checking permissions right before emission.
- Cap active streams per user/tenant, message size, concurrent subscriptions, and stream lifetime to prevent DoS.
- On cancel, clean up subscriptions, DB cursors, schedulers, and in-memory metadata/credentials.

### 7.5. Time-of-check/time-of-use

A decision that "user may access tenant A at T0" does not necessarily hold at T10. If permissions change frequently:
- Choose a concrete consistency model (immediate, near-real-time, expiry-bound).
- Determine whether data sent prior to revocation can be recalled (usually not).
- If rechecking asynchronously, handle races between revocation and event emission; gating at the data source may be needed to avoid emitting an item after revocation.
- Never turn a DB outage into `permitAll`; fail closed when proof is lacking.

## 8. Runnable project: RSocket SETUP service identity, per-REQUEST Alice/Bob

This example is a **Spring Boot 3.3.13, Spring Security 6.3.x, Java 17+** application on RSocket TCP port 7000. It uses **Simple Authentication** to cleanly verify the SETUP/request boundary without depending on an external Authorization Server/JWKS. Production should use tokens/service identities, TLS/mTLS, and proper secret management; **`{noop}` passwords below are for local learning/testing only, never for the Internet**.

Design:
- Service user `gateway` has only role `CONNECT`.
- Alice and Bob have role `VIEWER`, **not** `CONNECT`.
- `SETUP` requires `ROLE_CONNECT`.
- `identity.whoami` and `tenant.feed` require `ROLE_VIEWER`.
- The same connection from `gateway` can send request metadata for Alice or Bob.
- Without request credentials: the SETUP account `gateway` does not have `VIEWER`, so it cannot read user data.
- `tenant.feed` only allows a user to read tenants granted by `TenantPolicy`, checked before **every item** of the `Flux`.
- All other routes are denied by the route policy.
- There is no global `currentUser` variable.

### 8.1. Directory structure

~~~text
rsocket-identity-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── IdentityRSocketApplication.java
    │   │   ├── RSocketSecurityConfig.java
    │   │   ├── TenantPolicy.java
    │   │   └── IdentityController.java
    │   └── resources/application.properties
    └── test/java/demo/
        └── RSocketIdentityTests.java
~~~

### 8.2. settings.gradle

~~~groovy
rootProject.name = 'rsocket-identity-lab'
~~~

### 8.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-rsocket'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Why are these three runtime dependencies needed?**
- `spring-boot-starter-rsocket`: RSocket server/client, messaging, and Reactor transport.
- `spring-boot-starter-security`: core authentication/authorization components.
- `spring-security-rsocket`: RSocket Security DSL, interceptors, and RSocket Simple Authentication metadata classes.

Do not confuse with `spring-boot-starter-webflux`: if only building an RSocket TCP server, you do not need to add an HTTP WebFlux controller. If using RSocket **over WebSocket** in a WebFlux app, the transport/mapping path configuration differs; this example deliberately uses TCP to separate the two layers.

### 8.4. application.properties

~~~properties
spring.application.name=rsocket-identity-lab
spring.rsocket.server.transport=tcp
spring.rsocket.server.port=7000
spring.rsocket.server.address=127.0.0.1
~~~

Binding address `127.0.0.1` is for the local lab only. Production must use TLS/mTLS or private networking, never sending simple username/password in plaintext over the Internet. Tests override the port to `0` so the OS picks a free port.

### 8.5. IdentityRSocketApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IdentityRSocketApplication {

    public static void main(String[] args) {
        SpringApplication.run(IdentityRSocketApplication.class, args);
    }
}
~~~

### 8.6. RSocketSecurityConfig.java

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

@Configuration(proxyBeanMethods = false)
@EnableRSocketSecurity
public class RSocketSecurityConfig {

    @Bean
    MapReactiveUserDetailsService users() {
        // {noop} is for local demo only. Production uses password hashes/IdP.
        UserDetails gateway = User.withUsername("gateway")
            .password("{noop}connect-pass")
            .roles("CONNECT")
            .build();

        UserDetails alice = User.withUsername("alice")
            .password("{noop}alice-pass")
            .roles("VIEWER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password("{noop}bob-pass")
            .roles("VIEWER")
            .build();

        return new MapReactiveUserDetailsService(
            gateway, alice, bob);
    }

    @Bean
    PayloadSocketAcceptorInterceptor rsocketSecurity(
            RSocketSecurity rsocket) {

        return rsocket
            .authorizePayload(authorize -> authorize
                .setup().hasRole("CONNECT")
                .route("identity.whoami").hasRole("VIEWER")
                .route("tenant.feed").hasRole("VIEWER")
                .anyRequest().denyAll()
                .anyExchange().permitAll()
            )
            .simpleAuthentication(Customizer.withDefaults())
            .build();
    }
}
~~~

Key points:
- `.setup().hasRole("CONNECT")` checks connection credentials.
- `.route(...).hasRole("VIEWER")` checks credentials of requests with routes.
- Alice/Bob do not have `CONNECT`; gateway does not have `VIEWER`.
- A user might **send a wrong password** or omit per-request metadata; the system must not approve it just because the SETUP service account succeeded.
- `.anyRequest().denyAll()` blocks routes without an explicit policy; `.anyExchange().permitAll()` handles non-request exchanges without metadata; continuation PAYLOADs must still be checked by the app when needed.
- Spring Boot automatically installs the RSocket security interceptor via auto-config when the right dependencies are present. If bootstrapping `RSocketServer` manually outside Boot, attach `SecuritySocketAcceptorInterceptor`.
- **Do not omit `@EnableRSocketSecurity`** and assume Spring Security HTTP filters will protect RSocket TCP.

### 8.7. TenantPolicy.java

~~~java
package demo;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class TenantPolicy {

    private final Map<String, Set<String>> grants =
        new ConcurrentHashMap<>();

    public TenantPolicy() {
        reset();
    }

    public synchronized void reset() {
        grants.clear();

        Set<String> alice = ConcurrentHashMap.newKeySet();
        alice.add("tenant-a");

        Set<String> bob = ConcurrentHashMap.newKeySet();
        bob.add("tenant-b");

        grants.put("alice", alice);
        grants.put("bob", bob);
    }

    public Mono<Boolean> mayRead(
            String authenticatedUser,
            String tenant) {

        // Simulates dynamic permission check on each subscription/emission.
        // Production: reactive DB/service, non-blocking.
        return Mono.fromSupplier(() -> {
            Set<String> memberships =
                grants.getOrDefault(
                    authenticatedUser, Set.of());

            return memberships.contains(tenant);
        });
    }

    public void revoke(
            String authenticatedUser,
            String tenant) {

        Set<String> memberships = grants.get(authenticatedUser);

        if (memberships != null) {
            memberships.remove(tenant);
        }
    }
}
~~~

Meaning:
- `mayRead` uses the **authenticated name**, never `payload.userId`.
- Each time a subscriber calls `mayRead`, it reads the current membership state.
- `ConcurrentHashMap.newKeySet()` and `Mono.fromSupplier` only simulate nonblocking in-memory access, not a real database.
- `revoke` can cause subsequent checks to return `false`. Unit tests verify this.
- Do not use `MapReactiveUserDetailsService` as a production tenant database.

Limitation: `reset()` is for testing/labs. In production, membership must be managed in a real datastore with access control and auditing; never expose a public REST/RSocket endpoint to reset permissions.

### 8.8. IdentityController.java

~~~java
package demo;

import java.time.Duration;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class IdentityController {

    private final TenantPolicy tenantPolicy;

    public IdentityController(TenantPolicy tenantPolicy) {
        this.tenantPolicy = tenantPolicy;
    }

    @MessageMapping("identity.whoami")
    public Mono<String> whoami() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context ->
                context.getAuthentication().getName());
    }

    @MessageMapping("tenant.feed")
    public Flux<String> feed(@Payload String tenant) {
        return ReactiveSecurityContextHolder.getContext()
            .flatMapMany(context -> {
                String authenticatedUser =
                    context.getAuthentication().getName();

                // 4 items; check current tenant permission before EACH emission.
                return Flux.interval(Duration.ofMillis(80))
                    .take(4)
                    .concatMap(index ->
                        tenantPolicy
                            .mayRead(authenticatedUser, tenant)
                            .flatMap(allowed -> allowed
                                ? Mono.just(authenticatedUser
                                    + ":" + tenant + ":" + index)
                                : Mono.error(
                                    new AccessDeniedException(
                                        "Tenant access revoked"))
                            )
                    );
            });
    }
}
~~~

**Why not take `user` from the payload?** The username is obtained from `ReactiveSecurityContextHolder` of the request/stream already authenticated by Spring Security. The request only supplies `tenant` as the **requested target**; the server still checks against `TenantPolicy` before each emission.

**Do not `subscribe()` manually:** The controller returns `Mono`/`Flux`; the Spring/RSocket framework manages subscription and cancellation. `Flux.interval` only generates four demo events with demand/backpressure. Production has real event sources, concurrency/buffer/timeout limits, and permission checks at the data source.

**Why check before every emission?** If Alice's membership is revoked after the first item, the next item will be denied instead of continuing just because initial route authorization PASSED. However, a race still exists between the check and actual emission; for sensitive data, design a gate near the data boundary and define a consistency policy.

## 9. RSocket integration tests over TCP with StepVerifier

These tests connect to a real RSocket server running on a **random port** inside the application context, rather than calling controller methods directly. They verify:
- SETUP missing credentials or lacking `CONNECT` role.
- Valid gateway SETUP, Alice/Bob requests with `ROLE_VIEWER`.
- One connection serving multiple user requests without mixing identities.
- Omitting per-request credentials leaves `gateway` unable to read user data.
- Wrong password/tenant is blocked.
- Request-stream checks tenant in the application layer.
- Policy reflects permission revocation on a subsequent check.

### 9.1. RSocketIdentityTests.java

~~~java
package demo;

import java.time.Duration;
import java.util.function.Function;

import io.rsocket.metadata.WellKnownMimeType;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.SimpleAuthenticationEncoder;
import org.springframework.security.rsocket.metadata.UsernamePasswordMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(properties = "spring.rsocket.server.port=0")
class RSocketIdentityTests {

    private static final MimeType AUTH_MIME =
        MimeTypeUtils.parseMimeType(
            WellKnownMimeType
                .MESSAGE_RSOCKET_AUTHENTICATION.getString());

    @LocalRSocketServerPort
    int port;

    @Autowired
    RSocketRequester.Builder requesterBuilder;

    @Autowired
    TenantPolicy tenantPolicy;

    @BeforeEach
    void resetPermissions() {
        tenantPolicy.reset();
    }

    private UsernamePasswordMetadata gatewayCredential() {
        return new UsernamePasswordMetadata(
            "gateway", "connect-pass");
    }

    private UsernamePasswordMetadata aliceCredential() {
        return new UsernamePasswordMetadata(
            "alice", "alice-pass");
    }

    private UsernamePasswordMetadata bobCredential() {
        return new UsernamePasswordMetadata(
            "bob", "bob-pass");
    }

    private RSocketRequester sharedRequester() {
        return requesterBuilder
            .rsocketStrategies(builder ->
                builder.encoder(new SimpleAuthenticationEncoder()))
            .setupMetadata(gatewayCredential(), AUTH_MIME)
            .tcp("localhost", port);
    }

    // Close connection after publisher completes, errors, or cancels.
    private <T> Mono<T> usingRequester(
            Function<RSocketRequester, Mono<T>> operation) {

        return Mono.defer(() -> {
            RSocketRequester requester = sharedRequester();

            return operation.apply(requester)
                .doFinally(signal -> requester.dispose());
        });
    }

    private <T> Flux<T> usingRequesterFlux(
            Function<RSocketRequester, Flux<T>> operation) {

        return Flux.defer(() -> {
            RSocketRequester requester = sharedRequester();

            return operation.apply(requester)
                .doFinally(signal -> requester.dispose());
        });
    }

    @Test
    void gatewaySetupPlusAliceRequestReturnsAlice() {
        StepVerifier.create(
            usingRequester(requester -> requester
                .route("identity.whoami")
                .metadata(aliceCredential(), AUTH_MIME)
                .retrieveMono(String.class)))
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void sameConnectionCanProcessAliceThenBobSeparately() {
        StepVerifier.create(
            usingRequesterFlux(requester -> Flux.concat(
                requester.route("identity.whoami")
                    .metadata(aliceCredential(), AUTH_MIME)
                    .retrieveMono(String.class),
                requester.route("identity.whoami")
                    .metadata(bobCredential(), AUTH_MIME)
                    .retrieveMono(String.class)
            )))
            .expectNext("alice", "bob")
            .verifyComplete();
    }

    @Test
    void gatewaySetupIdentityAloneCannotReadUserRoute() {
        StepVerifier.create(
            usingRequester(requester -> requester
                .route("identity.whoami")
                .retrieveMono(String.class)))
            .expectError()
            .verify();
    }

    @Test
    void wrongRequestPasswordDoesNotInheritGatewayPrivilege() {
        StepVerifier.create(
            usingRequester(requester -> requester
                .route("identity.whoami")
                .metadata(
                    new UsernamePasswordMetadata(
                        "alice", "wrong-password"),
                    AUTH_MIME)
                .retrieveMono(String.class)))
            .expectError()
            .verify();
    }

    @Test
    void aliceCanStreamFromTenantA() {
        StepVerifier.create(
            usingRequesterFlux(requester -> requester
                .route("tenant.feed")
                .metadata(aliceCredential(), AUTH_MIME)
                .data("tenant-a")
                .retrieveFlux(String.class)))
            .expectNext(
                "alice:tenant-a:0",
                "alice:tenant-a:1",
                "alice:tenant-a:2",
                "alice:tenant-a:3")
            .verifyComplete();
    }

    @Test
    void aliceCannotRequestTenantBByChangingPayload() {
        StepVerifier.create(
            usingRequesterFlux(requester -> requester
                .route("tenant.feed")
                .metadata(aliceCredential(), AUTH_MIME)
                .data("tenant-b")
                .retrieveFlux(String.class)))
            .expectError()
            .verify();
    }

    @Test
    void bobCanStreamFromTenantB() {
        StepVerifier.create(
            usingRequesterFlux(requester -> requester
                .route("tenant.feed")
                .metadata(bobCredential(), AUTH_MIME)
                .data("tenant-b")
                .retrieveFlux(String.class)))
            .expectNext(
                "bob:tenant-b:0",
                "bob:tenant-b:1",
                "bob:tenant-b:2",
                "bob:tenant-b:3")
            .verifyComplete();
    }

    @Test
    void policyRevocationAffectsSubsequentChecks() {
        StepVerifier.create(
            tenantPolicy.mayRead("alice", "tenant-a"))
            .expectNext(true)
            .verifyComplete();

        tenantPolicy.revoke("alice", "tenant-a");

        StepVerifier.create(
            tenantPolicy.mayRead("alice", "tenant-a"))
            .expectNext(false)
            .verifyComplete();
    }

    @Test
    void requestCannotClaimUnknownUser() {
        StepVerifier.create(
            usingRequester(requester -> requester
                .route("identity.whoami")
                .metadata(
                    new UsernamePasswordMetadata(
                        "mallory", "anything"),
                    AUTH_MIME)
                .retrieveMono(String.class)))
            .expectError()
            .verify();
    }
}
~~~

**Nine tests** are written here. In tests using `expectError()`, exception classes may be wrapped as different RSocket application errors across versions. Therefore, test the actual rejection event without hardcoding exception strings or HTTP status codes (RSocket is not HTTP).

### 9.2. Why not use HTTP's @LocalServerPort?

The right annotation in Spring Boot **3.3.13** for RSocket server tests is:

~~~java
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
~~~

Do not use HTTP web server's `@LocalServerPort` to connect to RSocket TCP. The test sets `spring.rsocket.server.port=0` to pick a random port, avoiding conflicts with a local server. The port is injected via `@LocalRSocketServerPort`.

### 9.3. Testing limitations

The test suite verifies setup/request boundaries with **Simple Authentication**, and does not yet verify:
- JWT signature/JWKS retrieval/issuer/audience/expiry in RSocket.
- Reauthentication with a new JWT on the same connection after token refresh.
- Mid-`REQUEST_STREAM` revocation at exact time T3 (`policyRevocationAffectsSubsequentChecks` only confirms policy changes between two checks).
- Network TLS/mTLS, gateway header/metadata translation, reconnect, and resume.
- Stress testing multiple connections/streams under high load.
- Timeouts/backpressure, stream limits, and cancellation under infrastructure failures.

To test mid-stream revocation, you can build an integration test controlling events with `Sinks.Many` or a deterministic event source with latches rather than relying solely on sleeps/timers. Stop the stream and verify no further items are emitted once the revocation signal has been processed.

### 9.4. Running the project

Requires JDK 17+, Gradle 8.x, and Maven Central for initial dependency download:

~~~bash
gradle test
~~~

With the Gradle Wrapper:

~~~bash
./gradlew test
~~~

On Windows use `gradlew.bat test`. **There is no actual build log here**; `BUILD SUCCESSFUL` can only be confirmed after running in the right environment. The `Mono`/`Flux` tests do not depend on an HTTP port or external Authorization Server.

Run the RSocket server:

~~~bash
gradle bootRun
~~~

The application listens on RSocket TCP `localhost:7000`. This **is not** an HTTP website, so visiting `http://localhost:7000` in a browser will not yield an API response like HTTP/REST. You can use Java `RSocketRequester` as in the tests to call routes.

## 10. Design variant using JWT instead of Simple Authentication

In enterprise environments, the setup credential may be a **service account token**, while the request credential is an **end-user access token**. A diagram:

~~~text
HTTP end users Alice/Bob
           │
           ▼
Gateway with service identity G
           │ SETUP: G token, audience=rsocket-connect
           │ REQUEST Alice: Alice access token, audience=report-api
           │ REQUEST Bob: Bob access token, audience=report-api
           ▼
RSocket resource service:
  SETUP: checks service issuer/aud/role CONNECT
  REQUEST: checks user issuer/aud/role VIEWER
  STREAM ITEM: checks tenant/resource policy
~~~

### 10.1. RSocketSecurity JWT

An excerpt configuration for one JWT trust domain:

~~~java
@Bean
PayloadSocketAcceptorInterceptor jwtInterceptor(
        RSocketSecurity rsocket) {

    return rsocket
        .authorizePayload(authorize -> authorize
            .setup().hasRole("CONNECT")
            .route("identity.whoami").hasRole("VIEWER")
            .route("tenant.feed").hasRole("VIEWER")
            .anyRequest().denyAll()
            .anyExchange().permitAll())
        .jwt(Customizer.withDefaults())
        .build();
}
~~~

You need an appropriate `ReactiveJwtDecoder` bean and authority converter/claim policy compatible with `ROLE_CONNECT` and `ROLE_VIEWER`. **Do not** assume Spring Security turns `scope=connect` into `ROLE_CONNECT` by default: the default JWT scope authority is typically `SCOPE_connect`. If you want `hasRole("CONNECT")`, map roles explicitly per issuer policy or use `hasAuthority("SCOPE_connect")`.

### 10.2. Two issuers or two token profiles

If the setup token is issued by a Gateway Service Identity Provider while end-user JWTs are issued by a separate OIDC issuer:
- Do not use a single decoder accepting arbitrary issuers.
- Build a mechanism classifying trust domains/decoders via a **trusted issuer allowlist**, with the right `aud` for each layer.
- The setup credential must prove the service is allowed to open a connection, without proving Alice's permissions.
- The request token must prove the end user, without granting `ROLE_CONNECT`.
- Avoid "token substitution": an ID Token meant for an OAuth client must never be accepted as an access token for the RSocket resource server.
- Never enable `alg=none`, and never fetch JWKS from a `jku` or attacker-supplied issuer not on an allowlist.
- You may choose **mTLS for service connections + per-request end-user JWT**, rather than forcing every layer into a single JWT auth manager.

### 10.3. Token relay and confused deputy

A Gateway holding a connection might accidentally use its service token to call every resource on behalf of end users; it then becomes a **confused deputy**. You need:
- Explicit mapping from incoming user authentication to outgoing RSocket per-request metadata.
- Never store `currentUser` in a singleton requester.
- Token exchange/audience restriction if the frontend HTTP access token is not intended for downstream.
- Proper Reactor Context propagation; never rely on a mutable `ThreadLocal` when using `publishOn`/`subscribeOn`.
- Auditing combining end-user ID + service connection identity + route/tenant/object.
- Never forward bearer tokens to downstreams not authorized to receive them.

## 11. Identity in Reactor Context and cross-stream leakage bugs

### 11.1. Never use mutable connection state for all users

Wrong:

~~~java
class SharedConnection {
    String currentSubject;

    void setSubject(String name) {
        this.currentSubject = name;
    }

    String getSubject() {
        return this.currentSubject;
    }
}
~~~

Two concurrent requests:
- Request Alice writes `currentSubject = Alice`.
- Request Bob writes `currentSubject = Bob`.
- An event in Alice's stream reads `currentSubject` and sees Bob.

Consequences can include data leaks, misattributed audit logs, wrong permission checks, and cross-tenant access. The right approach is **request-specific `Authentication`** in Reactor Context, or an immutable authenticated context pinned specifically to the subscription.

### 11.2. Reading Authentication in a handler

~~~java
Mono<String> currentSubject() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context ->
            context.getAuthentication().getName());
}
~~~

This is an excerpt. If an asynchronous callback runs on a manually created `new Thread(...)` outside the Reactor chain, the security context does not automatically follow into the new thread. Always compose publishers properly, and never use Servlet's ThreadLocal `SecurityContextHolder.getContext()` to identify users inside an RSocket handler.

### 11.3. Distinguishing authenticated subject from requested subject

A payload:

~~~json
{
  "subject": "admin",
  "tenant": "tenant-victim",
  "reportId": "report-123"
}
~~~

is merely **the client's request**. The backend must get the subject from verified `Authentication` and check:
- Does the requested subject match the identity or is delegated access permitted by policy?
- Does the report belong to a tenant of which the user is a member?
- Are resource owner/ACL valid?
- If the account is disabled/revoked while the stream is running, is it rechecked?

Never create a new `Authentication` based on a JSON payload inside a controller.

## 12. Common authorization errors

| Symptom | Cause | How to check |
| --- | --- | --- |
| Alice/Bob data mixed up on shared connection | End-user credentials put in SETUP or global `currentUser` | Move credentials to per-request metadata |
| Service gateway opens connection and can read user data | `CONNECT` role also granted `VIEWER` or routes too broad | Separate `ROLE_CONNECT` and `ROLE_VIEWER` |
| Alice cannot open RSocket connection | SETUP requires `CONNECT`, Alice only has `VIEWER` | Use trusted service setup credentials |
| Request missing per-request credentials still views data | SETUP principal has `VIEWER` or route permits any authenticated connection | Separate setup/request roles, test missing metadata |
| Bob uses Alice's metadata via requester pool | Global state variable or wrong metadata | Immutable per-request metadata |
| Stream keeps emitting after user logout | Auth only at request start, no per-item revocation | Cancel/recheck/stream TTL |
| JWT expired yet stream keeps running | No expiry enforcement after request opens | TTL/cancel/reconnect strategy |
| `REQUEST_CHANNEL` message spoofs `userId` | Data field treated as identity | Pin verified principal, reauthorize each command |
| `@MessageMapping` route runs without login | Missing `RSocketSecurity` interceptor or route `permitAll` | Check Boot auto-config and matcher order |
| Route needs role but token has scope | `ROLE_*` differs from `SCOPE_*` | Clear converter/prefix policy |
| JWT in HTTP header yet RSocket request is anonymous | RSocket auth metadata not sent | Use `BearerTokenMetadata` |
| Browser RSocket TCP connection fails | Browsers cannot call raw TCP RSocket directly | RSocket over WebSocket + protocol client |
| `@LocalServerPort` does not point to RSocket port | HTTP annotation differs from RSocket port | `@LocalRSocketServerPort` |
| New token yet old requester keeps old identity | Setup credential does not change per request | Reconnect or request-scoped metadata |
| Service verifies valid signature but wrong tenant | Checked JWT route only, skipped object/tenant check | Local membership + repository tenant predicates |
| Gateway has mTLS so all end users are trusted | Service identity != user identity | Separate user request tokens |
| Request at setup rejected due to role | `setup().hasRole` does not match | Check authorities and matcher order |
| Disconnect after revoke triggers infinite retries | No retry budget/backoff | Token refresh + bounded retries + cleanup |

### 12.1. RSocket errors are not HTTP 401/403 codes

RSocket transport communicates using frames/errors, not per-request HTTP status codes. When authentication or authorization is denied, the client receives an RSocket error (usually converted into an exception on the requester side). **Do not assert** that an RSocket request must receive HTTP `401 Unauthorized` or `403 Forbidden` like REST.

With RSocket over WebSocket, the **handshake** HTTP status and RSocket errors occurring **after the connection opens** are two separate issues. Log error metrics separately for setup rejection, request denial, token validation, and stream revocation.

## 13. Security and performance when streaming long-lived data

### 13.1. Do not run blocking DB checks per payload

If per-item authorization accesses a database:
- Use reactive R2DBC/WebClient instead of blocking JDBC on the Netty event loop.
- Index by user/tenant/resource to avoid massive N+1 queries.
- For stable permissions, use short-lived caching paired with a version/revocation signal.
- If cache TTL is long, newly revoked permissions may still be honored; define the maximum window.
- Attach timeouts/retry budgets and fail closed when uncertain.
- Prefer enforcing row-level tenant boundaries in the query so wrong data is never read before filtering.

### 13.2. Cancellation and resource leaks

When a client cancels `REQUEST_STREAM`:
- Stop emitting events once the subscription is cancelled.
- Clean up DB cursors, event-bus subscriptions, buffers, security state, and metric tags.
- Cap active streams per user/tenant/service connection.
- Never retain access tokens in logs or global variables indefinitely.
- Test memory/CPU with thousands of subscriptions on one RSocket connection.

### 13.3. Reauth can disrupt UX

If a client refreshes a token while viewing a dashboard:
- You can terminate the old stream with an application-appropriate "reauth required" error semantic.
- The client obtains a new token via OAuth2 flow/refresh policy and opens a new request-stream.
- Use a verified resume cursor/event ID to avoid losing events, **never** use the resume cursor as a credential.
- Protect against replay/duplicate processing if the request stream has side effects (streams are usually read-only, though `REQUEST_CHANNEL` can write).
- Ensure every reconnect/re-subscribe checks current tenant membership.

### 13.4. Operational observability

Metrics to measure:
- SETUP success/failure counts by anonymized service identity.
- Route authorization success/deny counts by route and permission class, without logging raw JWTs.
- Active connections, active streams, stream age, and cancelled/revoked counts.
- Token validation failures grouped by: issuer, audience, signature, expired, malformed.
- Latency/timeouts of membership checks; cross-tenant denial counts.
- Connect/reconnect/resume rates, event replays, and backpressure pressure.
- Never log Simple Authentication passwords, bearer tokens, refresh tokens, or payload PII.

## 14. Scenario exercises

### Exercise 1 — Single-user mobile

A mobile app only uses Alice's account per connection. Where should authentication happen?

**Hint:** SETUP auth may suffice for initiation if lifetime/revocation policy is clear; sensitive streams may still require per-event checks.

### Exercise 2 — Multi-user gateway

A gateway opens one connection for 200 users. Should it put the first logged-in user's JWT at SETUP?

**Answer:** No. SETUP should authenticate the gateway/service; each request attaches the corresponding end-user credential. Otherwise, every user risks receiving the first identity.

### Exercise 3 — SETUP and REQUEST

Gateway has `ROLE_CONNECT`, Alice has `ROLE_VIEWER`. Gateway sends a GET-like request without user metadata. Is that allowed?

**Answer:** It must not be allowed to read data; `CONNECT` role is distinct from `VIEWER`.

### Exercise 4 — Bob on the same connection

Gateway sends a request for Alice then Bob over the same requester. What should backend `whoami` return?

**Answer:** `alice` for the first request and `bob` for the second, due to per-request authentication metadata; never use a global `currentUser`.

### Exercise 5 — Metadata vs. data

Bob sends payload `{"userId":"alice"}` while metadata holds Bob's credentials. Can the backend open Alice's data?

**Answer:** No, unless Bob has delegated access verified separately by business policy. The authenticated identity remains Bob.

### Exercise 6 — Multi-frame Request-stream

Spring Security checks the route when the stream starts. Does it automatically re-verify the JWT signature on PAYLOAD #2, #3, #4?

**Answer:** Do not assume so. Security route/request matching happens at the initiating request; per-event permission/expiry must be added by your architecture.

### Exercise 7 — Expired JWT

JWT `exp` is 10:05, stream opens at 10:00. At 10:10, should it keep emitting confidential records?

**Answer:** There must be a policy. If strict expiry is required, the stream must stop before/at `exp` or reauthorize, rather than relying on auth at T0.

### Exercise 8 — Logout and reconnect

Alice logs out in the frontend while the backend holds a long stream. What should happen?

**Answer:** The client cancels/closes, and the server receives a revocation signal or checks local state per event, terminating Alice's streams per policy.

### Exercise 9 — Channel with multiple users

An RSocket `REQUEST_CHANNEL` has a different `userId` in each payload. Does that count as reauthentication?

**Answer:** No. Self-declared data does not prove identity. Verified protocol identity or separate requests are required.

### Exercise 10 — TokenRelay

Gateway holds Alice's HTTP JWT. Can it forward it directly over RSocket to any arbitrary service?

**Answer:** No. You must verify proper access token audience/scopes/consent and use RSocket bearer metadata; use token exchange if downstream has a different audience.

### Exercise 11 — Per-item DB check

Per-item authorization uses JDBC `findMembership` inside `Flux.map`. Is that reactive-friendly?

**Answer:** No. Blocking I/O can block the event loop. Use reactive R2DBC/WebClient or reviewed isolation.

### Exercise 12 — Token signature/role

Does a JWT with `scope=read` satisfy `hasRole("READER")` by default?

**Answer:** No. Scopes usually become `SCOPE_read`, not `ROLE_READER`.

### Exercise 13 — Tenant mismatch

Alice is authenticated for `tenant-a` but the payload asks for `tenant-b`. Should she receive `tenant-b`'s event feed?

**Answer:** No, unless verified as authorized by the membership service. The payload is the requested target, not proof of permission.

### Exercise 14 — Shared connection auditing

The audit log only records `connectionId=xyz` without the end-user principal. Is that enough?

**Answer:** Not for multi-user connections. You need both service connection identity and request user identity + route/tenant/decision.

### Exercise 15 — RSocket Resume

A client resumes a stream after a network drop. Does the resume token automatically prove the user's JWT is still valid?

**Answer:** No. Resume is a protocol stream-recovery mechanism; security validity/reauth/TTL must be defined separately.

### Exercise 16 — Gateway impersonation

Gateway has mTLS, receives `userId=admin` from an HTTP body, and crafts per-request auth metadata as `admin`. Is this safe?

**Answer:** No. The gateway must take the principal from **verified incoming authentication**, never from a client-sent body.

### Exercise 17 — anyExchange().permitAll()

Does this rule mean all PAYLOAD events are already authorized?

**Answer:** No. It typically lets exchanges that are not requests with routes/metadata pass through; the app still needs per-event permission checks when required.

### Exercise 18 — Who can open a connection?

If Alice/Bob have `VIEWER` but not `CONNECT`, can they send Alice's request metadata on a SETUP that Alice opened herself?

**Answer:** No, if the setup rule requires `ROLE_CONNECT` and Alice lacks that authority. A valid trusted connection identity is required.

### Exercise 19 — AUTH MIME

Is sending the string `"alice"` in an arbitrary metadata entry considered Simple Authentication?

**Answer:** No. It requires the RSocket authentication metadata MIME/format and server-verified credentials.

### Exercise 20 — What does production QA need beyond the sample tests?

**Answer:** E2E TLS/mTLS, JWT signature/expiry, shared connection concurrency, mid-stream revocation with Sinks, multi-tenant ACLs, reconnect/resume, load/backpressure, cancellation, and service failures.

## 15. Security and architecture checklist

### Authentication

- [ ] Clearly distinguish **connection identity** from **request identity** when using shared connections.
- [ ] `SETUP` has a valid service/device authentication policy and lifecycle.
- [ ] `REQUEST_*` carries per-request auth metadata when one connection serves multiple users.
- [ ] Never store a mutable `currentUser` shared across all streams.
- [ ] Never take principal/roles from payload, `userId`, `tenantId`, or unverified self-declared metadata.
- [ ] JWT access tokens have proper issuer, audience, signature, `alg`, `exp`, and purpose validation.
- [ ] Never use an OIDC ID Token instead of a resource server access token.
- [ ] Service-to-service mTLS does not replace end-user authorization.
- [ ] Token refresh does not silently change the identity of a live SETUP.
- [ ] Reconnect/resume has a clear reauthentication/revalidation policy.

### Authorization and long streams

- [ ] Rules `setup()`, `route()`, `anyRequest()`, `anyExchange()` are ordered properly.
- [ ] Connection role `CONNECT` is not sufficient to view user data.
- [ ] Per-request role `VIEWER` comes only from authenticated metadata.
- [ ] Continuation per-payloads are not assumed to be new authn/authz.
- [ ] For sensitive streams, enforce per-event entitlement checks/cancel-on-revoke/TTL.
- [ ] Authentication is read from the request's Reactor Context, never `ThreadLocal`.
- [ ] Tenant/object permissions are checked at the service/data boundary.
- [ ] Disabled/revoked local memberships are detected within the security SLA.
- [ ] DB entitlement lookups are non-blocking on the event loop.
- [ ] Backpressure/buffers/stream length/active subscriptions are bounded.
- [ ] On cancel, clean up resources and stop emitting events.

### Testing/operations

- [ ] SETUP without credentials / without `CONNECT` → rejected.
- [ ] Valid gateway `CONNECT` + Alice `VIEWER` request → Alice.
- [ ] Same connection + Bob `VIEWER` request → Bob, no context leak.
- [ ] Gateway `CONNECT` without request credentials → cannot access `VIEWER` routes.
- [ ] Wrong per-request password/JWT → rejected.
- [ ] `tenant-b` payload from `tenant-a` Alice → rejected.
- [ ] Valid `tenant-a` Alice stream → emits expected items.
- [ ] Mid-stream revocation → stops events per policy.
- [ ] Expiring JWT mid-stream → handled consistently by policy.
- [ ] Verify `REQUEST_CHANNEL` continuations do not forge identities.
- [ ] Test metrics and trace IDs; never log secrets/raw tokens/PII.
- [ ] Stress test thousands of streams, cancellation, outages, and resume.
- [ ] Production Spring Boot/Security upgraded to a supported version.

## 16. Official references

- Spring Security — RSocket Security, Authentication at Setup versus Request Time, JWT, Authorization: https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html
- Spring Security 6.3 RSocket Security API — `RSocketSecurity` and payload authorization: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html
- Spring Framework — RSocket, SETUP/REQUEST_STREAM/REQUEST_CHANNEL/PAYLOAD, backpressure, and RSocketRequester: https://docs.spring.io/spring-framework/reference/rsocket.html
- Spring Boot 3.3 — RSocket Server Auto-configuration and TCP/WebSocket settings: https://docs.spring.io/spring-boot/3.3/reference/messaging/rsocket.html
- Spring Boot 3.3 Test API — `@LocalRSocketServerPort`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPort.html
- RSocket Protocol — SETUP, REQUEST, PAYLOAD, Metadata, CANCEL, RESUME: https://github.com/rsocket/rsocket/blob/master/Protocol.md
- RSocket Authentication Metadata Extension: https://github.com/rsocket/rsocket/blob/master/Extensions/Security/Authentication.md
- Spring Security — Reactive Security Context: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Project Reactor — Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Spring Security — Reactive OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html

**Remember:** A long-lived RSocket connection is a **transport channel**, not proof that all requests belong to the same end user. Authenticate SETUP to know **who may open the connection**, authenticate each REQUEST with metadata to know **who is requesting the operation**, and for long/sensitive streams **re-check permissions per item or close the stream on revocation/expiry**. In particular, continuation PAYLOADs in `REQUEST_STREAM`/`REQUEST_CHANNEL` **are not re-authenticated by Spring Security by default**; application design must ensure each stream's principal/tenant is preserved accurately without cross-leakage when connections are shared.
