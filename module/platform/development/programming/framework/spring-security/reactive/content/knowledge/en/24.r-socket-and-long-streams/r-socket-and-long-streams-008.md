# Boundary Between WebSocket Connection Identity and Per-Message Authorization

> **Context:** Spring Security Reactive (Spring WebFlux), WebSockets, and long-lived connections/streams; related to RSocket and STOMP where applicable. This lesson distinguishes **authentication at the HTTP Upgrade handshake** from **authorization on each command, subscription, event, or returned data** after the WebSocket is open. Illustrative examples use Java 17+, Spring Boot 3.3.13, and Spring Security 6.x. This Boot version is only used to present the API; for deployments in 2026, choose a supported version with security patches applied.

## 1. Problem: one connection, many requests with different permissions

A collaborative room management application has two private rooms, `alpha` and `beta`. Alice is allowed to read/write `alpha`; Bob is only allowed to read/write `beta`. Both can **authenticate successfully** to open a WebSocket:

```text
Alice -- GET /ws/rooms + HTTP Upgrade + credentials --> WebFlux
             |
             +-- HTTP SecurityWebFilterChain:
             |     verifies Alice's identity
             |     allows opening WebSocket (101 Switching Protocols)
             |
             +==================== upgraded connection ====================+
             |                                                             |
             | Alice sends READ|alpha    -> check alpha room perm -> ALLOW |
             | Alice sends READ|beta     -> check beta room perm  -> DENY  |
             | Alice sends WRITE|beta|x  -> check beta perm       -> DENY  |
             | Alice's alpha revoked     -> permission registry changes    |
             | Alice sends READ|alpha    -> re-check perm         -> DENY  |
             |                                                             |
             +==================== close connection =======================+
```

**Security differences:**

1. **Connection authentication:** "Which client is on the other end? Were the credentials at the HTTP handshake valid?"
2. **Message authorization:** "Is that exact person, at that exact moment, permitted to perform this operation on this room/record/tenant?"
3. **Subscription/output authorization:** "Is that person allowed to receive **every subsequent event** from this stream, even after permissions change?"

If you only check `authenticated()` on `GET /ws/rooms`, and then treat every frame as permitted, you can introduce **Broken Object Level Authorization (BOLA/IDOR)** or cross-tenant data leaks.

## 2. WebSocket differs from HTTP request-response

Standard HTTP:

```text
GET /api/rooms/alpha -> Security filters -> Controller -> 200
GET /api/rooms/beta  -> Security filters -> Controller -> 403
```

Each new HTTP request passes through the Security filter chain and is authenticated/authorized per that request's policy.

WebSocket:

```text
GET /ws/rooms + Upgrade -> HTTP security (once at handshake)
                           |
                           v
                         HTTP 101
                           |
                    WebSocketSession
                           |
                 Flux<WebSocketMessage> receive()
                           |
             READ|alpha, READ|beta, WRITE|...
                           |
              application-written message handling
```

After HTTP 101, messages run over the upgraded connection. **They do not become new HTTP `GET/POST` requests** for `ServerHttpSecurity.authorizeExchange().pathMatchers(...)` to re-run automatically on each frame. A single handshake URL can carry hundreds of thousands of business commands with different permissions.

In Spring Framework WebFlux, `WebSocketHandler.handle(WebSocketSession)` returns `Mono<Void>`; `session.receive()` returns `Flux<WebSocketMessage>`, and `session.send(Publisher<WebSocketMessage>)` sends outbound messages. These APIs handle **transport**; they do not automatically define permissions like `READ_ROOM` or `DELETE_DOCUMENT`.

### 2.1 Two layers, two questions

| Layer | Inspection source | What it proves | What it does NOT prove |
|---|---|---|---|
| HTTP Upgrade handshake | `SecurityWebFilterChain`, authentication filter, HTTP authorization | Client has a valid identity and may open endpoint `/ws/rooms` | Allowed to read every room, send every event, or subscribe to every channel |
| Connection identity | `WebSocketSession.getHandshakeInfo().getPrincipal()` | Principal bound to the handshake request | That permission remains valid hours later; that all messages are valid |
| Inbound message policy | Service/authorization policy, current ACL, tenant/room ownership | A specific operation on a specific resource is permitted | Automatically authorized for other operations/resources |
| Outbound stream policy | Subscription authorization and emission-time permission checks | Client is allowed to receive an event at emission time | That permission will last forever |
| Database/service enforcement | Repository query with tenant/owner predicate, transaction | Actual object and mutation are protected | That proxy/handshake alone is safe without data checks |

**Principle:** `authenticated()` establishes identity; it does not replace per-object, per-action, per-room, or per-tenant permission checks.

## 3. Where does identity at a WebFlux handshake live?

In Spring Framework WebFlux, `WebSocketSession` has `getHandshakeInfo()`. `HandshakeInfo` provides metadata of the HTTP request that opened the connection:

```java
Mono<Principal> principal =
    session.getHandshakeInfo().getPrincipal();
```

- `getPrincipal()` returns **`Mono<Principal>`**, not a direct `Principal` or Servlet `HttpServletRequest`.
- The `Principal` is supplied by the HTTP handshake authentication mechanism; e.g., an authenticated session cookie, Java client HTTP Basic, or a bearer JWT verified by the Resource Server at Upgrade.
- If the `Mono` is empty, never fabricate a fake identity from `Origin`, `Host`, `X-User`, or client payload.
- `Principal.getName()` is the identity name per the authentication provider. In multi-issuer/multi-tenant systems, you may need a stable composite key `issuer + subject + tenant` rather than just username/email.
- `HandshakeInfo` contains handshake headers/cookies and **must not be logged or passed wholesale into business code**: it can expose Authorization/cookies.

One handling pattern:

```java
@Override
public Mono<Void> handle(WebSocketSession session) {
    return session.getHandshakeInfo().getPrincipal()
        .switchIfEmpty(Mono.error(
            new IllegalStateException("Missing handshake principal")))
        .flatMap(principal -> {
            Flux<WebSocketMessage> replies = session.receive()
                .map(WebSocketMessage::getPayloadAsText)
                .concatMap(text -> authorizeAndHandle(
                    principal.getName(), text))
                .map(session::textMessage);

            return session.send(replies);
        });
}
```

**This is a method fragment**, without definitions/imports for `authorizeAndHandle` and assuming text frames only. The complete project in section 11 handles non-text frames. Most importantly, it receives the principal at handshake yet **checks permissions in `concatMap` for every received message**.

### 3.1 Handshake HTTP SecurityWebFilterChain

Example:

```java
return http
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.GET, "/ws/rooms").authenticated()
        .anyExchange().denyAll())
    .httpBasic(Customizer.withDefaults())
    .build();
```

If the WebSocket handshake GET is protected by Spring Security, a client lacking valid credentials is blocked **before 101**, normally with 401 and a Basic challenge or matching entry point. After success, a `READ|beta` frame does not pass through the HTTP `GET /ws/rooms` matcher again.

**Do not** use `permitAll("/ws/**")` and then assume every connection has a `Principal`. If anonymous handshakes are allowed by design, the handler must enforce a separate anonymous rule and prevent private operations from running.

### 3.2 WebSocket `wss://` and identity

`wss://` uses TLS for the WebSocket connection, protecting against eavesdropping and MITM per the TLS model. It **does not** prove an end-user is logged in, nor does it grant room read permissions. In production, use `wss://`, valid certificates, proxy upgrade/idle timeout policies, and `Secure` cookies.

## 4. Threat model: "entered the chat room" does not mean "read all messages"

Four vulnerability classes:

**A — BOLA/IDOR:** Alice opens a WebSocket successfully and sends `READ|beta`. If the server only trusts connection-wide identity, `beta` data leaks.

**B — Command spoofing:** Alice sends `ADMIN_DELETE|room=beta`. If the client self-declares `"role":"ADMIN"` in JSON and the server trusts it, admin commands can execute.

**C — Subscription leak:** Alice subscribes to `/topic/tenants/beta/events` or `room:beta`, receiving Bob's data because the initial subscription wasn't authorized.

**D — Revoked permissions on a long-lived connection:** At 09:00 Alice has `alpha` permission; at 09:05 admin revokes it. The connection stays open until 17:00; if the server only checks at connect time, Alice continues reading/writing data.

Corresponding defenses:

- Authentication at handshake.
- **Per-message policy**: check operation, resource ID, current user/tenant, and scope/role.
- **Subscription and per-event delivery policy**: do not authorize solely by channel name.
- TTL/reauthentication and revoke/close strategy for long sessions.
- Data-layer enforcement by tenant and owner in queries/mutations.

### 4.1 Never trust "client-claimed" fields

```json
{
  "type": "READ_ROOM",
  "roomId": "beta",
  "userId": "alice",
  "role": "ADMIN",
  "tenant": "beta"
}
```

The client can modify **every** field in the message body. When processing JSON, use `roomId`/`type` strictly as the **requested action**; take identity/role/tenant from verified authentication and server-side policy. Client-supplied `userId`, `role`, and `tenant` fields are **not** proof of authorization.

A safe error response on permission violation might be:

```json
{"type":"ERROR","code":"FORBIDDEN","requestId":"r123"}
```

Never return raw stack traces, private room lists, or sensitive claims explaining overly specific details to the client.

## 5. Authenticate once, authorize many times

### 5.1 Authentication timing

```text
t0: HTTP handshake
    validate session/Bearer/Basic -> Principal Alice
t1: message READ(alpha)
    ACL(current user=Alice, room=alpha, action=READ) -> true
t2: message READ(beta)
    ACL(current user=Alice, room=beta, action=READ) -> false
t3: admin revokes Alice's access to alpha
t4: message READ(alpha)
    ACL(current user=Alice, room=alpha, action=READ) -> false
t5: WebSocket closes/reconnects (if policy requires)
```

**Distinguish clearly:** per-message authorization can rely on a **fixed identity** from the handshake, while current permissions must be rechecked when each operation occurs. If the connection's identity expires or is disabled, the app must actively close the socket/reauth, because token/cookie expiration **does not guarantee** an open WebSocket will close automatically.

### 5.2 When must you re-authenticate every message?

Not every frame has to carry a new bearer token. Several models exist:

| Model | Best fit | Extra work needed |
|---|---|---|
| **Handshake authentication + per-message current ACL** | One browser user per WebSocket, bounded lifetime | Limit session duration, revocation, check scope/room per frame |
| **Periodic reauthentication / on privilege change** | Very long-lived connections, sensitive permissions | Close/reconnect with new credentials, or tightly designed protocol reauth |
| **Per-request/message metadata credentials** | One connection representing multiple end users, e.g., RSocket BFF | Validate token on every payload and map user accurately |
| **Token exchange/OBO for downstream** | Gateway calling APIs with a different audience | Authorization Server issues a new token with the right audience; never forward ID Tokens |
| **Anonymous WebSocket for public feeds** | Public data only | Origin/rate-limiting, disallow private subscriptions or mutations |

### 5.3 Connections shared across multiple users

A microservice may hold **one** WebSocket/RSocket connection to a backend and multiplex Alice/Bob's requests. In this case, the **connection's** principal may be a service account, **not** an end-user. If the backend must check Alice/Bob's permissions, you need a **delegated identity** per operation (token issued by AS for the right audience, per-request metadata in RSocket, or another verified auth contract). Never pass `X-User: alice` inside a payload and treat it as Alice's principal.

## 6. At what points are permissions checked?

| Processing point | Example | Security question |
|---|---|---|
| Handshake | `GET /ws/rooms` | May the user open a connection? Are Origin/TLS/credentials valid? |
| Join or subscribe | `SUBSCRIBE|alpha` | May the user subscribe to the `alpha` stream? |
| Inbound read | `READ|alpha` | May the user view `alpha` data **right now**? |
| Inbound write | `WRITE|alpha|...` | May the user modify it and is the payload valid? |
| Publish/broadcast | Event from business service | Are the recipients still authorized to receive the data? |
| Subscription lifetime | After user revocation | Keep delivering, drop events, or terminate stream? |
| Data access | SQL/R2DBC query | Does the query include tenant/owner predicates? |
| Reconnect | New handshake | Are old credentials still valid; have permissions/Origin changed? |
| Disconnect/logout | Logout or admin revocation | Are corresponding active sockets closed? |

An initially permitted subscription **does not** prove the user may receive every update forever. For sensitive events, check permissions **right before emission** or cancel the subscription upon revocation. Filtering only inbound messages while skipping outbound fan-out can still leak data.

## 7. WebSocket Origin, cookies, and CSWSH

**Cross-Site WebSocket Hijacking (CSWSH)** can occur when an external website opens a WebSocket to your app and the browser automatically attaches an authorized session cookie. If the app relies solely on cookies without restricting origin, the attacking site can exchange frames as the user.

Key points:

1. Browser WebSocket handshakes can include `Origin`. The server must check an `Origin` **allowlist** matching pages permitted to connect.
2. WebSockets **are not governed identically to CORS fetch**; do not treat REST API `Access-Control-Allow-Origin` config as automatic WebSocket protection. Use the framework's WebSocket handshake origin policy.
3. Origin checking is a browser defense; **non-browser clients can spoof Origin**, so Origin is not authentication.
4. Cookie `SameSite`, `Secure`, `HttpOnly`, session timeouts, and CSRF design remain vital; **never** substitute Origin for authentication and message permissions.
5. HTTP CSRF filters typically target unsafe methods. WebSocket Upgrades start with GET; the CSRF filter not blocking GET **does not mean** WebSocket is immune to CSWSH.
6. Never use `allowedOrigins("*")` for private cookie-authenticated WebSockets without dedicated justification and controls.

### 7.1 Configuring Origin on WebFlux WebSocket mapping

Spring Framework instructs using `CorsConfigurationSource` on `WebSocketHandler` or `corsConfigurations` on `SimpleUrlHandlerMapping` to set allowed origins for the handshake. Idea snippet:

```java
CorsConfiguration allowed = new CorsConfiguration();
allowed.setAllowedOrigins(List.of(
    "https://portal.example.com"));

SimpleUrlHandlerMapping mapping = new SimpleUrlHandlerMapping(
    Map.of("/ws/rooms", webSocketHandler), -1);
mapping.setCorsConfigurations(Map.of(
    "/ws/rooms", allowed));
```

This is a **configuration fragment** needing imports and environment management. Use the real domain and run integration tests with valid/invalid `Origin` through proxies. Do not hardcode `portal.example.com` in the localhost demo below because the Java test client authenticates the handshake with Basic credentials rather than impersonating a browser.

### 7.2 Browser WebSocket API and the Authorization header

Standard JavaScript:

```javascript
const socket = new WebSocket("wss://portal.example.com/ws/rooms");
socket.onmessage = (event) => console.log(event.data);
```

The browser `new WebSocket(...)` API **has no option to attach arbitrary HTTP `Authorization` headers** like `fetch`. Therefore the demo uses **Java `ReactorNettyWebSocketClient`** sending an HTTP Basic header to illustrate the handshake; it **is not** production browser code.

For browsers, common options include:

- Browser already logged in via OIDC/form, using HTTPS session cookies with CSWSH/Origin/CSRF policies.
- Issuing a **one-time, short-lived ticket bound to the exact user, audience, WebSocket path, and nonce** via an authenticated HTTPS endpoint; verify and consume the ticket at handshake.
- Designing dedicated subprotocol authentication if required and threat-reviewed; never assume `Sec-WebSocket-Protocol` is a safe place for long-lived bearer tokens.

**Prefer avoiding** placing access tokens in the query `wss://.../ws?token=...`: URLs easily land in ingress logs, tracing, and observability systems. If a product forces a query ticket, use only short-lived single-use tickets, scrub logs, and restrict scope.

## 8. Message types and authorizing operations

Native WebSocket **has no concept of route `/topic/**` or method `POST`** after Upgrade. Applications must define an explicit protocol convention:

```text
READ|alpha
READ|beta
WRITE|alpha|new-content
WRITE|beta|new-content
```

For every frame:

1. Validate frame type (text/binary), size, encoding, and JSON/schema if using JSON.
2. Parse operation and resource ID; reject unknown operations.
3. Obtain the verified identity from handshake, or reauth per protocol if needed.
4. Read **current** permissions from a trusted source and check action + resource + tenant.
5. Only when allowed, execute the query/mutation or establish the subscription.
6. When returning data, send only authorized fields; never broadcast globally and "expect the client to filter."
7. Record audit outcomes without logging raw tokens/PII.

**TOCTOU issue:** permissions can change between `hasPermission` and the `UPDATE` transaction. For sensitive data, enforce tenant/owner predicates **inside the DB query/transaction itself**, not only in a prior in-memory check.

### 8.1 Commands must deny by default

```text
READ|alpha          -> check READ alpha
WRITE|alpha|value   -> check WRITE alpha + validate payload
DELETE|alpha        -> DENY (no published command)
READ|unknown        -> DENY
MALFORMED           -> ERR
```

If a new method is introduced, never allow it automatically via `authenticated()`. Add an explicit policy and tests before enabling the command.

## 9. Long-lived streams: permissions changing after handshake

Permissions may be revoked via an admin API or tenant membership update. Strategies:

- **Check each inbound operation:** before every READ/WRITE, fetch current ACL.
- **Check on subscription creation:** when the client subscribes to a room/topic, check membership.
- **Check each outbound event:** before emitting a new event, verify permissions are still valid.
- **Revocation events:** when admin revokes access, proactively complete/close the stream or remove the subscriber from the room; requires multi-instance event propagation.
- **Connection max age:** overly long connections must reconnect and re-authenticate, especially when a bearer token is used at handshake.
- **Heartbeat/ping/pong:** detects dead peers and can trigger reauth/liveness checks; does not replace authorization.
- **Session/token lifecycle:** cookie logout or bearer `exp` does not automatically close an open WebSocket; enforce strict policies.

### 9.1 Long subscription case

**Illustrative snippet** for an event stream emitted only while the user still holds permission at that moment:

```java
Flux<RoomEvent> safeEvents = roomEvents
    .concatMap(event ->
        permissionService.canRead(
                verifiedUserId, event.roomId())
            .flatMap(allowed -> allowed
                ? Mono.just(event)
                : Mono.error(new AccessDeniedException(
                    "Subscription revoked"))));
```

`roomEvents`, `permissionService`, and `RoomEvent` are undefined here; this is **not** standalone code. It illustrates checking permissions before **each event** and terminating the stream when revoked. Using only `filterWhen` drops denied events while leaving the connection alive; that may suit some feeds, whereas for private rooms you should usually end the subscription and clean up resources.

**Handling silent periods:** if permission is revoked while the stream is quiet, per-event checks won't run until the next event arrives. Listen to revocation signals from pub/sub, set TTLs, or run periodic reauthorization to cut off early. Multiple pods require message bus/cache consistency and race handling.

### 9.2 Separate read and write permissions

A member might be allowed to **read** without being allowed to **write**. Thus checking only "belongs to room" is insufficient in real products. Store grants per action:

```text
permission(user, tenant, room, action)
  where action ∈ {READ, WRITE, MODERATE, SUBSCRIBE}
```

For the lab, a single membership allows both READ and WRITE to keep the example short; expand per business needs. Having `ROLE_USER` only means the user logged in, not that they have permission to read room `beta`.

## 10. WebFlux WebSocket, STOMP, and RSocket: three different models

| Characteristic | Raw WebFlux WebSocket | STOMP over WebSocket | RSocket |
|---|---|---|---|
| Transport/protocol | RFC 6455 frames | STOMP frames over WebSocket | RSocket frames over TCP/WebSocket/... |
| Typical handler | `WebSocketHandler` | `@MessageMapping` and message broker/channel | `@MessageMapping`/`RSocketRequester` |
| Connection | HTTP WebSocket Upgrade | HTTP WebSocket Upgrade then STOMP CONNECT | RSocket SETUP then payload requests |
| Base identity | HTTP handshake principal or custom auth protocol | Handshake + STOMP message user context | SETUP or request metadata authentication |
| Message authz | **App implements for raw messages** | Spring Messaging authorization rules for supported configs | `RSocketSecurity.authorizePayload(...)` |
| Matcher | App operation, room, tenant | Message type, destination, subscription | Payload route, SETUP, request/exchange |
| Long streams | Receive/send `Flux` | `SUBSCRIBE` / broker fanout | request-stream, request-channel, fire-and-forget |
| Risk | Assuming authenticated handshake allows all frames | Subscribing to another user's topic, sending to broker destination | Service SETUP principal applied to all user payloads |
| Do not mis-copy | Servlet `@EnableWebSocketSecurity` into raw WebFlux handler | `SecurityWebFilterChain` protecting only HTTP handshake | HTTP `authorizeExchange` into RSocket payloads |

### 10.1 STOMP message-level authorization

Spring Security's **WebSocket Security via Spring Messaging** documentation demonstrates `@EnableWebSocketSecurity` and `MessageMatcherDelegatingAuthorizationManager` with:

```java
// CONFIGURATION SNIPPET for supported STOMP/Spring Messaging model;
// NOT a configuration that works on raw WebFlux WebSocketHandler.
messages
    .simpDestMatchers("/app/**").hasRole("USER")
    .simpSubscribeDestMatchers("/user/**").authenticated()
    .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
    .anyMessage().denyAll();
```

These rules govern **inbound STOMP message types/destinations** and do not automatically apply to a string like `READ|beta` in the WebFlux demo. Per Spring Security STOMP docs, checking `SUBSCRIBE` permissions is critical: a browser must not subscribe directly to `/topic/admin/**` or someone else's `/queue/**` just because it connected.

**Distinguishing stacks:** Spring Security's "WebSocket Security" page lives in the **Servlet integration** section and assumes Spring Messaging/STOMP infrastructure. Never paste `@EnableWebSocketSecurity` into a **pure WebFlux `WebSocketHandler`** app expecting Spring to authorize raw WebSocket messages automatically.

One more note: Spring Security Messaging generally focuses on protecting **`clientInboundChannel`**. Never treat it as an automatic check on every outbound delivery; recipient/subscription choices and data read permissions must still be right.

### 10.2 RSocket has dedicated setup and request authentication

Spring Security RSocket provides:

- `@EnableRSocketSecurity` and `RSocketSecurity`.
- `PayloadSocketAcceptorInterceptor`/`SecuritySocketAcceptorInterceptor`.
- `AuthenticationPayloadInterceptor`.
- `authorizePayload(...)` with `setup()`, `route(...)`, `anyRequest()`, `anyExchange()`.
- Simple Authentication or JWT metadata depending on stack capabilities.

Illustrative snippet per official docs:

```java
@Bean
PayloadSocketAcceptorInterceptor rsocketInterceptor(
        RSocketSecurity rsocket) {
    rsocket
        .authorizePayload(authz -> authz
            .setup().hasRole("SETUP")
            .route("fetch.profile.me").authenticated()
            .route("fetch.profile.{username}")
                .access((authentication, context) ->
                    checkFriends(authentication, context))
            .anyRequest().authenticated()
            .anyExchange().permitAll())
        .jwt(Customizer.withDefaults());

    return rsocket.build();
}
```

This is a **non-runnable Java snippet** because `checkFriends` is undefined; imports, a `ReactiveJwtDecoder` bean, and RSocket server integration must be added. Note `anyExchange().permitAll()` is **a choice of the docs example**, not advice for every application. For sensitive streams, fail-closed route/payload policies and business ACLs must be carefully verified.

Spring Security RSocket makes clear: if a connection serves only **one** user, SETUP authentication may fit. If a BFF uses **one shared connection for multiple users**, user authentication/context is needed on **each request/payload**, rather than reusing the SETUP service account identity.

### 10.3 WebSocket and RSocket are not synonymous

RSocket has metadata routing and security interceptors at the RSocket request level; raw WebSocket only has message frames and an application-defined protocol. WebSocket can serve as a **transport** for RSocket, yet you must still configure security per RSocket protocol rather than copying `WebSocketHandler` policies for `RSocketRequester`.

## 11. Spring Boot WebFlux Java 17+ example — per-message authorization

The demo builds a raw WebSocket endpoint `/ws/rooms`, authenticating users **via HTTP Basic at handshake**, then checking **current room permissions for every frame**. HTTP Basic is used here because Java integration clients can easily attach an `Authorization` header; browser JavaScript `new WebSocket` cannot arbitrarily attach such headers. Production browsers should use cookies/OIDC or short-lived tickets with Origin protection designed in.

Lab users:

| User | Lab password | Room permissions |
|---|---|---|
| `alice` | `alice-dev-password` | `alpha` |
| `bob` | `bob-dev-password` | `beta` |
| `admin` | `admin-dev-password` | `alpha`, `beta` |

Text protocol format:

```text
READ|alpha                -> OK|READ|alpha|alpha-secret
READ|beta                 -> DENY|FORBIDDEN (for Alice)
WRITE|alpha|new-value     -> OK|WRITTEN|alpha (for Alice)
WRITE|beta|new-value      -> DENY|FORBIDDEN (for Alice)
DELETE|alpha              -> ERR|BAD_COMMAND
```

Writing stores the value in an in-memory map for the lab. Real systems need DB transactions with owner/tenant predicates, durability, concurrent edit handling, and auditing. The demo includes both READ/WRITE under the same membership to focus on **connection identity vs. message-level policy**.

### 11.1 Project structure

```text
webflux-ws-message-authz/
  settings.gradle
  build.gradle
  src/main/java/demo/ws/WebSocketSecurityApplication.java
  src/main/java/demo/ws/SecurityConfiguration.java
  src/main/java/demo/ws/RoomPolicy.java
  src/main/java/demo/ws/RoomWebSocketHandler.java
  src/main/java/demo/ws/WebSocketConfiguration.java
  src/main/java/demo/ws/HealthController.java
  src/test/java/demo/ws/RoomPolicyTest.java
  src/test/java/demo/ws/RoomWebSocketIntegrationTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'webflux-ws-message-authz'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.ws'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The Spring Boot WebFlux starter pulls in Reactor Netty and Spring Framework WebSocket APIs. Do not add Servlet's `spring-boot-starter-web` to the demo. WebSocket tests use `ReactorNettyWebSocketClient` and policy unit tests use `StepVerifier`.

### 11.2 Main application

**src/main/java/demo/ws/WebSocketSecurityApplication.java**

```java
package demo.ws;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSocketSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebSocketSecurityApplication.class, args);
    }
}
```

### 11.3 SecurityConfiguration: authenticate handshake, never assume message rights

**src/main/java/demo/ws/SecurityConfiguration.java**

```java
package demo.ws;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-dev-password"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob-dev-password"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-dev-password"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(
            alice, bob, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/ws/rooms")
                    .authenticated()
                .pathMatchers(HttpMethod.GET, "/health")
                    .permitAll()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Meaning:

- `GET /ws/rooms` is the HTTP handshake endpoint requiring valid authentication. Missing/wrong Basic credentials will not receive `101 Switching Protocols`.
- `GET /health` is public. Other URLs are denied by default.
- Do not build a custom authentication manager or parser inside the WebSocket handler; use Spring Security WebFlux for HTTP.
- `ROLE_USER` and `ROLE_ADMIN` are only for login; **`RoomPolicy` decides room access**. Two users both having `ROLE_USER` do not share the same room permissions.
- Default CSRF still applies to unsafe HTTP methods; the demo only uses GET. Never assume it replaces WebSocket Origin validation.
- Lab credentials must not be used as real credentials; production must use TLS, vault/secret manager, OIDC, or an appropriate authentication mechanism.

### 11.4 RoomPolicy: current permissions, independent of handshake time

**src/main/java/demo/ws/RoomPolicy.java**

```java
package demo.ws;

import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public final class RoomPolicy {

    private final ConcurrentMap<String, Set<String>> memberships =
        new ConcurrentHashMap<>();

    private final ConcurrentMap<String, String> documents =
        new ConcurrentHashMap<>();

    public RoomPolicy() {
        memberships.put("alice", Set.of("alpha"));
        memberships.put("bob", Set.of("beta"));
        memberships.put("admin", Set.of("alpha", "beta"));

        documents.put("alpha", "alpha-secret");
        documents.put("beta", "beta-secret");
    }

    public Mono<String> handle(String verifiedUsername, String frame) {
        return Mono.fromSupplier(() ->
            decide(verifiedUsername, frame));
    }

    private String decide(String username, String raw) {
        if (raw == null
                || raw.getBytes(StandardCharsets.UTF_8).length > 1024) {
            return "ERR|BAD_FRAME";
        }

        String[] fields = raw.split("\\|", 3);
        if (fields.length < 2) {
            return "ERR|BAD_COMMAND";
        }

        String action = fields[0];
        String room = fields[1];

        if (!"READ".equals(action) && !"WRITE".equals(action)) {
            return "ERR|BAD_COMMAND";
        }

        if (!documents.containsKey(room)) {
            // Do not leak rooms that do not belong to the user.
            return "DENY|FORBIDDEN";
        }

        // Read CURRENT ACL for EACH message; do not cache at handshake.
        if (!memberships.getOrDefault(username, Set.of())
                .contains(room)) {
            return "DENY|FORBIDDEN";
        }

        if ("READ".equals(action)) {
            if (fields.length != 2) {
                return "ERR|BAD_COMMAND";
            }
            return "OK|READ|" + room + "|" + documents.get(room);
        }

        if (fields.length != 3 || fields[2].isBlank()
                || fields[2].length() > 256) {
            return "ERR|BAD_COMMAND";
        }

        documents.put(room, fields[2]);
        return "OK|WRITTEN|" + room;
    }

    // Demo only: how permissions can change while WebSocket stays open.
    // NEVER expose this method as a public endpoint!
    public void revoke(String username, String room) {
        memberships.computeIfPresent(username, (key, current) -> {
            Set<String> copy = new HashSet<>(current);
            copy.remove(room);
            return Set.copyOf(copy);
        });
    }
}
```

Notable points:

1. `RoomPolicy.handle(...)` returns `Mono<String>` to compose into the reactive pipeline without calling `block()`.
2. `verifiedUsername` must come from the **server's handshake `Principal`**, never from the client payload.
3. `memberships` is queried on **each message**; `revoke(...)` changes the outcome of the next message without reopening the WebSocket.
4. `ConcurrentHashMap` and `Set.copyOf(...)` serve the lab; production permissions should come from a trusted source with TTL/revocation consistency, usually keyed by tenant/issuer/subject.
5. Alice's `READ|beta` is denied; sharing `ROLE_USER` creates no cross-room access.
6. `WRITE` mutates `documents` only after verifying resource and membership. No data is written when denied.
7. The 1024 **post-decode UTF-8 byte** cap is a lab input-limiting layer; production must still cap WebSocket frame sizes, fragmentation, buffer retention, rates, and memory at transport/config level.
8. For simplicity, the lab shares one membership for READ/WRITE; production has action-specific policies.
9. The lab has no subscriptions/broadcasts; outbound streams must add per-event authorization as in section 9.
10. `revoke(...)` is called only from tests/trusted services; never expose it in a public controller without admin protection and auditing.
11. Atomicity in the lab applies only to map operations; real DB mutations must enforce owner/tenant inside the transaction to prevent TOCTOU.

### 11.5 RoomWebSocketHandler: obtain Principal once, check every frame

**src/main/java/demo/ws/RoomWebSocketHandler.java**

```java
package demo.ws;

import java.security.Principal;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public final class RoomWebSocketHandler implements WebSocketHandler {

    private final RoomPolicy policy;

    public RoomWebSocketHandler(RoomPolicy policy) {
        this.policy = policy;
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        // Identity comes from the Security-checked HTTP handshake.
        return session.getHandshakeInfo().getPrincipal()
            .switchIfEmpty(Mono.error(
                new IllegalStateException(
                    "Authenticated handshake required")))
            .flatMap(principal -> sendAuthorizedReplies(
                session, principal));
    }

    private Mono<Void> sendAuthorizedReplies(
            WebSocketSession session, Principal principal) {

        Flux<WebSocketMessage> replies = session.receive()
            .concatMap(frame -> {
                if (frame.getType() != WebSocketMessage.Type.TEXT) {
                    return Mono.just("ERR|TEXT_ONLY");
                }

                String message = frame.getPayloadAsText();
                return policy.handle(principal.getName(), message);
            })
            .map(session::textMessage);

        return session.send(replies);
    }
}
```

**Why not simply do `session.send(session.receive().map(session::textMessage))`?** Because directly echoing all client messages without parsing/resource checks performs no authorization. Here:

- `getHandshakeInfo().getPrincipal()` provides the connected identity. If empty, the handler grants no permissions.
- `session.receive()` can emit **many** frames throughout the lifetime.
- `concatMap` invokes `RoomPolicy.handle(...)` **for each frame**, preserving response order and avoiding manual `subscribe()` outside the pipeline.
- Binary/control frames are not interpreted as text commands; the demo returns an error for non-TEXT types. In production, evaluate handling of protocol controls, close codes, and binary validation.
- Output consists solely of policy-approved responses; no room data is emitted before checking permissions.
- When the socket closes, reactive receive/send complete/cancel per protocol; do not retain data buffers after callbacks. With Netty pooled buffers, if retaining a buffer across an asynchronous boundary, use proper retain/release APIs; the demo constructs a `String` inside the pipeline without holding raw buffers.

### 11.6 WebSocketConfiguration: map endpoint to handler

**src/main/java/demo/ws/WebSocketConfiguration.java**

```java
package demo.ws;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;

@Configuration(proxyBeanMethods = false)
public class WebSocketConfiguration {

    @Bean
    HandlerMapping webSocketMapping(
            RoomWebSocketHandler handler) {
        return new SimpleUrlHandlerMapping(
            Map.of("/ws/rooms", handler), -1);
    }
}
```

`SimpleUrlHandlerMapping` maps `/ws/rooms` to `WebSocketHandler`, with order `-1` so it is checked before annotated controllers when appropriate. Spring Boot WebFlux auto-configuration provides the necessary WebFlux handler adapters, including WebSocket handling in WebFlux Config; no Servlet WebSocket registration is needed.

**Production Origin policy:** add `CorsConfiguration`/`CorsConfigurationSource` to the mapping/handler for allowed origins (section 7). The lab project is only for testing Java client connections on localhost; it does not yet have a browser-deployment Origin allowlist. Never consider this demo production-ready for private cookie-based WebSockets.

### 11.7 HealthController

**src/main/java/demo/ws/HealthController.java**

```java
package demo.ws;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class HealthController {

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("ok");
    }
}
```

### 11.8 Trying it out

From the project root, with JDK 17+ and compatible Gradle:

```bash
gradle bootRun
```

If using the Gradle Wrapper: `./gradlew bootRun` or Windows `gradlew.bat bootRun`. Plain `curl` cannot establish a full-duplex WebSocket session using a normal HTTP GET; to test frames, use a WebSocket client capable of HTTP Upgrade and sending messages, such as the Java client in section 12 tests.

If using `wscat`/a WebSocket client supporting headers in the lab:

```bash
# Conceptual illustration; use fake credentials on localhost only.
# CLI client must support the handshake Authorization header.
wscat -c ws://localhost:8080/ws/rooms \
  -H "Authorization: Basic <BASE64_CREDENTIALS_DEMO>"
```

`<BASE64_CREDENTIALS_DEMO>` is just a placeholder in the CLI instructions, **not** an immediately usable value; Java tests use `HttpHeaders.setBasicAuth` to encode properly.

Open a connection as Alice and send:

```text
READ|alpha
READ|beta
WRITE|beta|no
```

Expected in order:

```text
OK|READ|alpha|alpha-secret
DENY|FORBIDDEN
DENY|FORBIDDEN
```

These are the results per the lab policy before any test modifies `documents`. `WRITE|alpha|hi` is permitted and causes subsequent `READ|alpha` calls in **the same JVM** to see `hi`.

## 12. Automated testing: policy and WebSocket handshake

### 12.1 Standalone policy tests: revoke changes permissions after identity is established

**src/test/java/demo/ws/RoomPolicyTest.java**

```java
package demo.ws;

import org.junit.jupiter.api.Test;

import reactor.test.StepVerifier;

class RoomPolicyTest {

    @Test
    void aliceCanReadOnlyHerRoom() {
        RoomPolicy policy = new RoomPolicy();

        StepVerifier.create(policy.handle("alice", "READ|alpha"))
            .expectNext("OK|READ|alpha|alpha-secret")
            .verifyComplete();

        StepVerifier.create(policy.handle("alice", "READ|beta"))
            .expectNext("DENY|FORBIDDEN")
            .verifyComplete();
    }

    @Test
    void bobCanReadOnlyHisRoom() {
        RoomPolicy policy = new RoomPolicy();

        StepVerifier.create(policy.handle("bob", "READ|beta"))
            .expectNext("OK|READ|beta|beta-secret")
            .verifyComplete();

        StepVerifier.create(policy.handle("bob", "READ|alpha"))
            .expectNext("DENY|FORBIDDEN")
            .verifyComplete();
    }

    @Test
    void revocationChangesNextMessageAuthorization() {
        RoomPolicy policy = new RoomPolicy();

        StepVerifier.create(policy.handle("alice", "READ|alpha"))
            .expectNext("OK|READ|alpha|alpha-secret")
            .verifyComplete();

        policy.revoke("alice", "alpha");

        StepVerifier.create(policy.handle("alice", "READ|alpha"))
            .expectNext("DENY|FORBIDDEN")
            .verifyComplete();
    }

    @Test
    void deniedWriteDoesNotChangeRoomData() {
        RoomPolicy policy = new RoomPolicy();

        StepVerifier.create(
                policy.handle("alice", "WRITE|beta|stolen"))
            .expectNext("DENY|FORBIDDEN")
            .verifyComplete();

        StepVerifier.create(policy.handle("bob", "READ|beta"))
            .expectNext("OK|READ|beta|beta-secret")
            .verifyComplete();
    }

    @Test
    void successfulWriteRequiresCurrentAccess() {
        RoomPolicy policy = new RoomPolicy();

        StepVerifier.create(policy.handle(
                "bob", "WRITE|beta|new-beta"))
            .expectNext("OK|WRITTEN|beta")
            .verifyComplete();

        StepVerifier.create(policy.handle("bob", "READ|beta"))
            .expectNext("OK|READ|beta|new-beta")
            .verifyComplete();
    }

    @Test
    void unknownCommandAndRoomAreNotAuthorized() {
        RoomPolicy policy = new RoomPolicy();

        StepVerifier.create(policy.handle("alice", "DELETE|alpha"))
            .expectNext("ERR|BAD_COMMAND")
            .verifyComplete();

        StepVerifier.create(policy.handle("alice", "READ|secret"))
            .expectNext("DENY|FORBIDDEN")
            .verifyComplete();
    }
}
```

**6 unit tests** use `StepVerifier` to confirm each message is authorized against the current room; the revocation test intentionally uses **the same user identity** for both calls, yet the outcome changes after `revoke`. This proves per-message policy evaluation, **not** end-to-end propagation of revocation signals to open WebSocket sessions across multiple pods.

### 12.2 Integration test: WebSocket connection with HTTP Basic

**src/test/java/demo/ws/RoomWebSocketIntegrationTest.java**

```java
package demo.ws;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class RoomWebSocketIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    WebTestClient http;

    private URI wsUri() {
        return URI.create(
            "ws://localhost:" + port + "/ws/rooms");
    }

    private Mono<List<String>> exchange(
            String username, String password, String... commands) {

        HttpHeaders headers = new HttpHeaders();
        headers.setBasicAuth(username, password);

        AtomicReference<List<String>> observed =
            new AtomicReference<>();

        var socketClient = new ReactorNettyWebSocketClient();

        return socketClient.execute(wsUri(), headers, session -> {
            Mono<Void> sendCommands = session.send(
                Flux.fromArray(commands).map(session::textMessage));

            Mono<Void> readAnswers = session.receive()
                .map(WebSocketMessage::getPayloadAsText)
                .take(commands.length)
                .collectList()
                .doOnNext(observed::set)
                .then();

            return Mono.when(sendCommands, readAnswers);
        })
        .timeout(Duration.ofSeconds(10))
        .then(Mono.fromSupplier(observed::get));
    }

    @Test
    void missingAuthenticationCannotUpgrade() {
        var client = new ReactorNettyWebSocketClient();

        StepVerifier.create(
                client.execute(wsUri(), new HttpHeaders(),
                    session -> Mono.empty())
                    .timeout(Duration.ofSeconds(5)))
            .expectError()
            .verify();
    }

    @Test
    void wrongPasswordCannotUpgrade() {
        var client = new ReactorNettyWebSocketClient();
        HttpHeaders headers = new HttpHeaders();
        headers.setBasicAuth("alice", "wrong-password");

        StepVerifier.create(
                client.execute(wsUri(), headers,
                    session -> Mono.empty())
                    .timeout(Duration.ofSeconds(5)))
            .expectError()
            .verify();
    }

    @Test
    void aliceOneConnectionReceivesAllowAndDeny() {
        StepVerifier.create(exchange(
                "alice", "alice-dev-password",
                "READ|alpha", "READ|beta"))
            .expectNext(List.of(
                "OK|READ|alpha|alpha-secret",
                "DENY|FORBIDDEN"))
            .verifyComplete();
    }

    @Test
    void bobCannotReadAlphaOnHisOwnConnection() {
        StepVerifier.create(exchange(
                "bob", "bob-dev-password",
                "READ|beta", "READ|alpha"))
            .expectNext(List.of(
                "OK|READ|beta|beta-secret",
                "DENY|FORBIDDEN"))
            .verifyComplete();
    }

    @Test
    void aliceCannotWriteBetaDespiteValidHandshake() {
        StepVerifier.create(exchange(
                "alice", "alice-dev-password",
                "WRITE|beta|illegal", "READ|alpha"))
            .expectNext(List.of(
                "DENY|FORBIDDEN",
                "OK|READ|alpha|alpha-secret"))
            .verifyComplete();
    }

    @Test
    void unknownCommandIsRejectedAfterHandshake() {
        StepVerifier.create(exchange(
                "alice", "alice-dev-password", "DELETE|alpha"))
            .expectNext(List.of("ERR|BAD_COMMAND"))
            .verifyComplete();
    }

    @Test
    void healthIsPublicWithoutWebSocketHandshake() {
        http.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }
}
```

**7 integration tests** (six WebSocket/handshake behaviors and one HTTP health check) perform HTTP Upgrade via Reactor Netty:

- Missing credentials and wrong password → handshake fails to upgrade (publisher errors).
- Alice and Bob are both authenticated, yet can only read the rooms they have permission for.
- Cross-room WRITE request is denied, even though the handshake succeeded.
- Undefined commands are rejected.
- Public routes require no WebSocket.

`WebSocketClient.execute(URI,HttpHeaders,WebSocketHandler)` supports setting HTTP headers for the handshake; `Mono.when(sendCommands,readAnswers)` sends and receives concurrently, and `take(commands.length)` completes the test after enough responses. `timeout` prevents hanging indefinitely if the connection fails.

**Test limitation:** `RoomPolicy` in the integration test is not revoked while the socket is open; post-handshake permission changes are tested at the policy layer (section 12.1). To prove multi-instance end-to-end revocation, add a test that opens a socket, receives an allow, has admin revoke access, sends another message over **the same socket**, and verifies deny/close plus message-bus propagation.

### 12.3 Running tests

```bash
gradle test
```

With an appropriate wrapper: `./gradlew test` or Windows `gradlew.bat test`. In PowerShell you can use `curl.exe` for HTTP.

**Testing status:** the Java snippets follow Spring Framework WebFlux/WebSocket, Spring Security 6.x, and Reactor APIs and were manually reviewed, **without actually running a Gradle build/test** during authoring. The HTTP statuses/bodies described are expected design outcomes; run in an environment with compatible JDK/Gradle/dependencies to confirm. Do not treat expected results as proof that a production system is secure.

## 13. Pitfalls with login and token expiration

### 13.1 What are the limits of HTTP Basic at handshake?

- Java `WebSocketClient` can send Basic Authorization via the HTTP handshake, as in the demo.
- Browser `new WebSocket()` does not allow setting arbitrary Authorization headers.
- Basic credentials risk appearing in proxy logs/packet captures without TLS; always use `wss://` and careful tracing.
- Basic has no logout/refresh tokens like OIDC; production browsers normally use sessions/OIDC.

**Never** "fix" this by putting username/password into the WebSocket URL. Use cookie-sessions or controlled short-lived tickets, or RSocket per-request metadata per design.

### 13.2 JWT expiring mid-session

A JWT with `exp` in 15 minutes may pass the handshake at 14:59, while the connection stays open until 17:00. The HTTP Security filter chain **does not automatically re-run on each frame**. Operational options:

1. Record the connection/credential expiration verified at handshake in the trusted security context.
2. Close the WebSocket when token/session policy expires or enforce a max connection lifetime.
3. Reconnect/re-auth with a fresh token after the browser/SDK completes a valid flow.
4. If the API requires per-message authentication, design a protocol with supported revalidation instead of trusting the stale principal.
5. Coordinate revocation/logout across nodes; account for event latency and races.

Do not inspect raw `exp` from an unverified WebSocket payload; use verified token metadata and active policy.

### 13.3 Login/logout does not automatically handle all sockets

HTTP logout can invalidate a `WebSession`/cookie, yet open WebSockets may remain alive. STOMP + Spring Session has dedicated integration in supported stacks; **do not assume raw WebFlux WebSocket closes all sockets automatically on logout**. Manage a connection registry by stable identity, close/cancel on revocation, handle multi-node cluster distribution, and avoid storing full tokens/PII in the registry.

### 13.4 Renewal inside a single connection

A self-invented message like `{"type":"AUTH_REFRESH","token":"..."}` **is not automatically safe**. You must design a state machine:

- Authenticate the new token using a verifier checking issuer/audience/signature/expiry.
- Prevent unauthorized identity switching: Alice's session must not switch to Bob while keeping old subscriptions.
- Clear old subscriptions/permissions when principal changes.
- Block replay, downgrade, and reuse of revoked tokens.
- Never exempt the refresh command itself from all other authorization checks.

In many products, **closing and reopening the connection** is simpler and easier to control than mid-stream reauth.

## 14. Subscriptions, fan-out, and broadcasting

A common mistake: checking permissions when the client sends `SUBSCRIBE|alpha`, then having the service push every event from `Flux<RoomEvent>` to all sockets.

**Insufficient:**

```java
// ANTIPATTERN: everyone added to the socket list receives everything.
roomEvents.subscribe(event ->
    everySocket.send(event.toString()));
```

This is pseudocode and **not** proper reactive style (manual `subscribe` lacks lifecycle management). A safe design requires:

- Subscriptions keyed by `verifiedUserId + tenant + resource + action`.
- Grant at subscribe time and **revalidate on event emission** or cancel the subscription immediately on revocation.
- Never let clients specify other recipients via headers/body.
- Outbound event serialization must strip unauthorized PII/secrets.
- Backpressure: bounded queues; slow clients are dropped/closed per policy rather than buffering sensitive data indefinitely.
- Cleanup on disconnect: dispose subscriptions, release buffers/resources, leave no orphaned sessions/listeners.
- Event bus distributing revocations across nodes; measure policy-change propagation latency.
- Never embed access tokens in event payloads or traces for correlation.

### 14.1 Room read permission differs from system event permission

A user may be permitted `READ|alpha` without being permitted `room.alpha.audit.admin` events or events belonging to another tenant. Design ACLs by **event type** and **sensitivity**, not solely by room ID. When an event contains a specific record, also check owner/record. "Allowed to view the room overview" does not mean seeing every private message in the room.

## 15. WebFlux Security vs. method security in message handlers

Reactive method security can be enabled for **service methods** using `@PreAuthorize` or `ReactiveAuthorizationManager` per context. However, when a WebSocket handler calls a service from a separate pipeline, do not assume the Reactor `SecurityContext` from the HTTP handshake is always propagated intact to every future service call in every architecture.

If relying on `@AuthenticationPrincipal`/`ReactiveSecurityContextHolder`, explicitly test context propagation in the WebSocket flow and avoid manual `subscribe()` calls that drop context. A simple, reviewable approach for raw WebSocket is **passing the verified identity** to a policy method as in the demo, where the policy reads current ACLs. For complex systems, consider an explicit `AuthorizationContext` containing subject, issuer, tenant, action, resource, and non-sensitive session ID.

**Never pass raw `Principal` objects across threads/caches and keep them alive forever as fresh proof.** The handshake `Principal` is a snapshot; permission/session lifecycles need fresh policies.

## 16. Threat model and test matrix

| Scenario | HTTP handshake | Message/stream | Outcome to guarantee |
|---|---|---|---|
| Missing credentials | 401/redirect, no 101 | Not processed | Private socket does not open |
| Wrong/expired credentials at handshake | Authentication fails | Not processed | No authenticated `Principal` |
| Valid Alice, READ alpha | 101 | Check READ alpha | Allow |
| Valid Alice, READ beta | 101 | Check READ beta | Deny |
| Valid Bob, WRITE alpha | 101 | Check WRITE alpha | Deny, DB unchanged |
| Frame missing type/resource | 101 | Validate schema | Reject message |
| Unknown operation | 101 | Deny-by-default | Not executed |
| Alice revoked after connect | Connection may stay open | Recheck ACL per frame/event | Deny or close immediately |
| User subscribed then revoked | 101 | Revalidate event / revoke signal | No further private data emitted |
| Unknown browser Origin with cookie | Reject per Origin policy | Not processed | Prevents CSWSH |
| Non-browser spoofs Origin without credentials | HTTP auth rejects | Not processed | Origin does not replace authentication |
| JWT `exp` passes while socket stays open | Initial handshake passed | TTL/reauth strategy | Never use expired identity forever |
| Session logout | Socket may persist | Revoke/close registry | No private events received after revoke |
| Token right issuer, wrong audience | JWT validation rejects | Not processed | No `aud` bypass |
| Multi-tenant route/chat message | Valid 101 | Check tenant + room + action + record | No cross-tenant data leak |
| Shared service connection multiplexes users | Service connection auth | Per-request delegated identity | Alice cannot borrow service privileges |
| Binary/oversized frame | Handshake may succeed | Check type/size/buffer | Reject/close and rate-limit |
| Message flood/slow client | May 101 | Backpressure/rate limits | Does not exhaust heap/event loop |
| STOMP broker destination | 101 + CONNECT auth | SEND/SUBSCRIBE rules | Cannot publish/subscribe unauthorized channels |
| RSocket setup vs. payload | Setup granted | Route/payload authz | Do not treat SETUP grant as all resource grants |

## 17. Common errors and fixes

| Mistake | Consequence | Fix |
|---|---|---|
| `/ws/**.authenticated()` then allowing all frames | BOLA, cross-tenant reads | Per-message action/resource ACL |
| Trusting `userId` in JSON messages | User impersonation | Take identity from verified handshake/token |
| Checking permissions only at `SUBSCRIBE` | Data leak after revocation | Revalidate each event, revoke/close |
| Using `permitAll` on private handshake | Anonymous sockets use private protocol | Require authenticated, explicit anonymous policy |
| Skipping WebSocket Origin check | CSWSH on cookie sessions | Allowed origins, SameSite/CSRF design |
| Treating REST CORS headers as WebSocket protection | Misses browser cross-site sockets | Handshake Origin policy |
| JWT expires yet socket lives forever | Stale identity | Reauth/max-age/close policy |
| HTTP logout does not close socket | Post-logout data leak | Connection registry and revoke events |
| `alpha` user sends to `beta` because both are `ROLE_USER` | Object-level authorization bug | Check room membership/tenant |
| Using STOMP `@EnableWebSocketSecurity` in raw WebFlux handler | Wrong stack, rules never run | Use raw handler policy or right framework |
| Copying Servlet `HttpSecurity` into WebFlux | Wrong API stack | `ServerHttpSecurity`/`SecurityWebFilterChain` |
| Assuming RSocket SETUP auth protects every payload | Shared-connection user mix-up | Payload authz and per-request user metadata |
| Forwarding ID Token as downstream Bearer | Wrong token purpose/audience | Use resource-appropriate access tokens |
| Using long-lived query `?access_token=...` | Token leaks in logs | Cookies/short-lived tickets/secure auth |
| Not limiting frames/buffers/queues | DoS/memory exhaustion | WebSocket limits, bounded queues, backpressure |
| Calling blocking JPA from event loop | Throughput drop, timeouts | R2DBC or bounded scheduler boundary |
| Manual `subscribe()` in handler | Lost cancellation/context, leaks | Compose `Mono<Void>` from receive/send |
| "Authz check" then `UPDATE` without tenant predicate | TOCTOU/cross-tenant write | DB predicate/transaction enforcement |
| Delivering private events by client-chosen room name | Cross-tenant broadcast | Server-side subscription registry |
| Not distinguishing 401 from message-level DENY | Client retry/login loops | Clear error contract, proper close codes |

## 18. Checklist for real WebSocket/RSocket deployments

1. Identify the protocol: **raw WebFlux WebSocket**, **STOMP**, or **RSocket**. Choose the matching security integration.
2. Protect HTTP handshakes or SETUP with proper authentication; never grant private sockets anonymously by accident.
3. Enforce TLS/WSS and certificate verification; configure proxy connection upgrades and idle timeouts.
4. Check `Origin` when browsers use session cookies; never trust Origin as credentials.
5. Never place long-lived bearer tokens in URLs/queries or raw telemetry.
6. Read the principal from `HandshakeInfo.getPrincipal()` (WebFlux) or verified protocol metadata.
7. Separate connection identity from per-message/room/tenant authorization.
8. Validate message type, schema, size, room/resource ID, rate, and allowed actions.
9. **Deny by default** for unknown operations/destinations and unlisted tenants.
10. Check current permissions before READ/WRITE/DELETE; enforce data-layer predicates in transactions.
11. For `SUBSCRIBE`, check at subscribe time **and** before emitting events, or cancel immediately on revocation.
12. Define session max-age, JWT `exp`, reauthentication, and logout/revocation propagation.
13. On shared connections, never let a service principal substitute for end-user permissions; use verified delegated tokens/per-request metadata.
14. Never log Authorization headers, cookies, access/refresh tokens, private event payloads, or excessive PII.
15. Cap memory buffers, frame sizes, queue depths, and concurrent connections; design backpressure and cleanup.
16. Never block the Netty event loop with synchronous database/remote calls; test concurrent streams.
17. Write unit tests for current ACL/revocation, WebSocket 101/401 handshakes, cross-room DENY, and E2E long-lived session integration tests.
18. Separate STOMP inbound SEND/SUBSCRIBE from outbound delivery authorization; never assume subscriptions last forever.
19. For RSocket, verify SETUP authorities, route/request authorization, and per-request metadata on shared connections.
20. Review permissions whenever adding commands/subscriptions or changing schemas; test negative cases and race conditions.

## 19. Practice exercises

1. Explain why Spring Security HTTP matcher `GET /ws/rooms` does not automatically block `READ|beta` frames after `101 Switching Protocols`.
2. Give Alice and Bob the same `ROLE_USER`: why can they open the same endpoint yet have different room permissions?
3. Send `READ|alpha` and `READ|beta` on **one connection**. Confirm both allow/deny outcomes without changing the principal.
4. Write a test calling `RoomPolicy.revoke("alice","alpha")` between two READs; explain why caching an ACL snapshot at handshake would be wrong.
5. Add a `DELETE|room` command: it must have its own action permission, rate limit, and DB owner predicate; do not use bare `authenticated()`.
6. Design read-only permissions for a user: allow READ, block WRITE, even after the user has joined the room.
7. Design `SUBSCRIBE|alpha` with an event stream. When revoked mid-stream, how do you stop new events from emitting?
8. Given a stream with zero events for 1 hour, how do you close the connection promptly when a user is revoked even if per-event checks haven't run?
9. Simulate a cross-site browser opening a private WebSocket with auto-sent cookies. Why is Origin validation required? Does Origin replace credentials?
10. Try accessing `ws` from browser JavaScript requiring an arbitrary `Authorization` header. Why doesn't the browser API let you set that header directly?
11. Propose a short-lived one-time ticket for WebSocket handshakes: TTL, nonce, audience, replay prevention, and log redaction.
12. A JWT has 1 minute left when the handshake succeeds, and the connection stays alive for 3 hours. Define max-age/reauth policies and tests.
13. Compare STOMP `SUBSCRIBE /topic/**` with raw WebFlux frame `READ|alpha`. Which Security APIs apply?
14. Compare RSocket `SETUP` auth with `route("fetch.profile.me")` auth. What does a connection shared by multiple users need?
15. Design a BFF forwarding private events to a browser: should permissions come from the service identity or end-user delegated identity?
16. Inject payload `{"userId":"admin","role":"ADMIN"}` into a frame. Explain why the server must never trust those fields.
17. Create WebSocket integration tests for invalid Origin / missing cookie / valid cookie under handshake origin restrictions.
18. Add concurrency/rate tests to catch memory leaks from manual `subscribe()` and unbounded queues.
19. Replace in-memory memberships with an R2DBC database query having a tenant predicate; handle TOCTOU in `UPDATE`.
20. Design a runbook when a token/session is compromised: revoke, close sockets, clear subscriptions, audit, and reauth.

## Conclusion

**Connection identity** only answers "who is allowed to open the WebSocket?". **Per-message authorization** must continue answering "is that person allowed to perform this operation on this object/room/tenant at this moment?". In Spring WebFlux, HTTP `SecurityWebFilterChain` inspects the Upgrade request, `WebSocketSession.getHandshakeInfo().getPrincipal()` provides the authenticated identity, and `receive()`/`send()` handle a message stream that can last for hours. `authorizeExchange` **does not automatically apply** to every frame after 101. You must enforce ACLs on every inbound command, at subscription creation, and on private outbound event emission; handle revocation, token expiry, logout, Origin/CSWSH, TLS, buffer limits, and data-layer authorization. STOMP/Spring Messaging and RSocket have specialized security integrations, yet you must still distinguish connection/SETUP auth from per-message/payload permissions and business data checks.

## Official documentation and standards

1. Spring Framework — Reactive WebSocket API, handshake, handler mapping, receive/send, CORS: https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html
2. Spring Framework 6.1 — `HandshakeInfo.getPrincipal()` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/HandshakeInfo.html
3. Spring Framework 6.1 — WebSocketClient custom headers Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/client/WebSocketClient.html
4. Spring Security — WebFlux Security, authentication and request matchers: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
5. Spring Security — WebSocket Security / STOMP message authorization (Servlet integration): https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/websocket.html
6. Spring Security — RSocket Security, SETUP vs per-request auth and `authorizePayload`: https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/rsocket.html
7. Spring Framework — STOMP message authorization: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html
8. RFC 6455 — The WebSocket Protocol: https://www.rfc-editor.org/rfc/rfc6455
9. OWASP — WebSocket Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html
