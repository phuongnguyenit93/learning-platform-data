# Route Authorization and Metadata Control in RSocket

> **Context:** RSocket and long streams, in the **Spring Security reactive / Spring WebFlux** ecosystem. This lesson focuses on **RSocket route** authorization, **SETUP/request metadata** security, differences between the **initial request** and **continuation PAYLOADs** of a long stream, and how Spring Security 6.5 uses `RSocketSecurity`, `PayloadSocketAcceptorInterceptor`, and `ReactiveAuthenticationManager`. Examples use **Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x**, RSocket TCP on loopback, and Simple Authentication; JWT/custom metadata extensions are presented separately. Example accounts and passwords are **for practice only**, never for real use on the Internet.

## 1. Lesson objectives

Upon completing this lesson, learners should be able to:

1. Explain why RSocket **is not an HTTP API**: routes live in metadata, not URL paths.
2. Distinguish `SETUP`, `REQUEST_RESPONSE`, `REQUEST_STREAM`, `REQUEST_CHANNEL`, `REQUEST_FNF`, `PAYLOAD`, and `METADATA_PUSH` when reasoning about permissions.
3. Know which metadata carries **routing**, which carries **authentication**, and which carries **business context** such as tenant/tracing; never mix them.
4. Use `@EnableRSocketSecurity` and a `PayloadSocketAcceptorInterceptor` bean with `RSocketSecurity.authorizePayload(...)`.
5. Understand matchers `.setup()`, `.route("...")`, `.matcher(...)`, `.anyRequest()`, and `.anyExchange()`; rules are evaluated in order with first-match-wins.
6. Choose between **authentication at connection setup** or **per request**, especially when multiple users share one RSocket connection.
7. Configure routes restricted to `ROLE_READER`/`ROLE_ADMIN`, without using a blanket `authenticated()` to open every feature.
8. Keep `anyExchange().permitAll()` intentionally for routeless payloads on an already-authorized channel, **without** treating it as permission to skip data checks.
9. Register custom metadata MIME types using `RSocketStrategiesCustomizer` and `MetadataExtractorRegistry`, read them via `@Header`, and treat all client-sent custom metadata as **untrusted**.
10. Design protection for **long-lived streams** across permission changes, token expiration, revocation, reconnect, backpressure, rate/byte quotas, and cancellation.
11. Write integration tests with `RSocketRequester`/`StepVerifier` verifying valid/invalid setup credentials, reader/admin routes, streams, and channels.
12. Understand common mistakes: sending an HTTP Basic header instead of RSocket authentication metadata, missing auth encoder, overly broad route rules, taking roles from a tenant header, and blindly trusting decoded JWTs without verification.

**Key message:** In RSocket, **routes are metadata the client can choose**, and authentication metadata is merely **untrusted credentials until verified**. Authorization must be decided from the **verified principal + route + actual resource**, while also controlling the lifecycle of long-lived streams.

## 2. How does RSocket differ from HTTP?

RSocket is a binary protocol supporting multiple interaction types over one TCP/WebSocket connection:

| RSocket interaction | Common reactive API shape | Security implication |
| --- | --- | --- |
| Request-Response | One request, one response (`Mono<T>`) | Needs authz at initial request |
| Fire-and-Forget | One request, no business response expected | Still needs authz; client `Mono<Void>` completion does not prove server processed it |
| Request-Stream | One request, multiple responses (`Flux<T>`) | Check permissions before opening stream; consider mid-stream revocation |
| Request-Channel | Bidirectional multi-message stream (`Flux<T>` in/out) | Check initial request **and** validate each item, quotas/backpressure |
| Metadata-Push | Sends connection-level metadata outside a specific request | Do not treat metadata push as a route-authorized request |
| SETUP | Negotiates MIME types, keepalive, initial connection credentials/metadata | Can authenticate the client right at connection time |
| Continuation PAYLOAD | Subsequent frames after the initial request (especially channel) | Does not necessarily carry fresh routing metadata |

In REST, a URL like `GET /reports/me` typically identifies the endpoint. With RSocket, a client can call:

```java
requester.route("reports.me")
    .retrieveMono(Report.class);
```

The string `reports.me` is serialized into **routing metadata**, not a URL path. Spring Messaging `@MessageMapping("reports.me")` dispatches to the handler. That **does not mean** the route string is proof that the user has permission.

### 2.1 What is inside a frame?

Conceptually:

```text
RSocket SETUP:
  data MIME type:      application/json or application/cbor
  metadata MIME type:  message/x.rsocket.composite-metadata.v0
  setup auth metadata: UsernamePasswordMetadata / BearerTokenMetadata
  keepalive/lifetime settings
          |
          v
REQUEST_STREAM (route="events.stream"):
  metadata:
    entry 1: message/x.rsocket.routing.v0       -> "events.stream"
    entry 2: message/x.rsocket.authentication.v0 -> token/credentials if per-request auth
    entry 3: message/x.example.tenant.v1         -> "north" if registered by the app
  data: stream-opening payload
          |
          v
PAYLOAD/REQUEST_N/CANCEL:
  frames serving the existing stream
  many frames **do not carry routing metadata again**
```

This is a logical diagram, **not a byte-level dump of a real packet**. Depending on the interaction, a frame may or may not have data/metadata; routing metadata normally appears on the **initial frame of a request**.

### 2.2 What is composite metadata?

RSocket can send multiple metadata entries with different MIME types in one payload. Common composite MIME:

```text
message/x.rsocket.composite-metadata.v0
```

Common entries:

```text
message/x.rsocket.routing.v0
message/x.rsocket.authentication.v0
message/x.example.tenant.v1       (application custom MIME, example only)
```

A MIME type only specifies **how to decode** a metadata entry; it **does not verify the truth** of the value. For instance, `tenant=north` is still a client-controlled string, not an authorized tenant.

## 3. Which layer does RSocket Security run at?

Spring Security RSocket does not rely on HTTP's `SecurityWebFilterChain`. Instead it uses:

- `@EnableRSocketSecurity` to enable RSocket security integration.
- `RSocketSecurity` to declare the authentication and authorization DSL.
- `PayloadSocketAcceptorInterceptor` holding the payload interceptors.
- `SecuritySocketAcceptorInterceptor` attaching payload security to the socket acceptor.
- `AuthenticationPayloadInterceptor` authenticating metadata via reactive authentication machinery.
- `AuthorizationPayloadInterceptor` evaluating `PayloadExchange` against matchers.
- `MapReactiveUserDetailsService` + password encoder for Simple Authentication in the demo.
- `@MessageMapping` from Spring Messaging receiving requests after the routing/security layer.

With Spring Boot 3.x when proper dependencies and auto-configuration are present, **Boot registers the RSocket server and security socket acceptor interceptor**. If you initialize an RSocket server **manually** (without Boot), you must attach `SecuritySocketAcceptorInterceptor` yourself; merely declaring an interceptor bean without wiring it into the server can let requests bypass security.

### 3.1 Entry configuration

```java
@Configuration
@EnableRSocketSecurity
class RSocketSecurityConfig {
    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity rsocket) {
        return rsocket
            .authorizePayload(authz -> authz
                .setup().authenticated()
                .route("events.stream").hasRole("READER")
                .route("admin.audit").hasRole("ADMIN")
                .anyRequest().denyAll()
                .anyExchange().permitAll()
            )
            .simpleAuthentication(Customizer.withDefaults())
            .build();
    }
}
```

This is an **illustrative snippet**; full imports/files are in section 8. It means a connection must authenticate at SETUP; afterward, routes `events.stream` and `admin.audit` have different rules; other requests are denied; non-new-request PAYLOADs are permitted through if not matched by preceding rules.

### 3.2 Why not use @EnableWebFluxSecurity to protect standalone RSocket TCP?

HTTP and RSocket have separate security pipelines. `@EnableWebFluxSecurity` and `ServerHttpSecurity` apply to HTTP WebFlux; RSocket uses `@EnableRSocketSecurity`, `RSocketSecurity`, and payload interceptors. When RSocket uses **WebSocket transport** on an HTTP server, the HTTP handshake layer still needs origin/TLS/gateway checks, but **does not replace** route authorization inside RSocket frames.

Never assume "WebSocket already passed HTTP authentication so every RSocket route is automatically authorized." After upgrade, individual RSocket requests still need explicit policies and designed identity propagation.

## 4. Matcher types in authorizePayload

| Rule | What does it match? | Used for |
| --- | --- | --- |
| `.setup()` | Payload exchange at SETUP | Conditions to open an RSocket connection |
| `.route("events.stream")` | Routing metadata matching pattern | Role/scope by route name |
| `.route("admin.*")` | Pattern via route matcher | Admin route group; avoid overly broad wildcards |
| `.matcher(customMatcher)` | A custom `PayloadExchangeMatcher` | Advanced conditions by exchange type/metadata |
| `.anyRequest()` | Initial request interaction (not each continuation PAYLOAD) | Fallback deny or authenticated for unmatched requests |
| `.anyExchange()` | Remaining exchanges, including non-request types | Final decision for payloads/no-route/metadata push |

**Rules are evaluated in order.** Spring Security uses the **first matching rule**, rather than running all rules to pick the "strongest" one.

### 4.1 Correct order

```java
rsocket.authorizePayload(authz -> authz
    .setup().hasRole("CONNECT")
    .route("status.ping").authenticated()
    .route("events.stream").hasRole("READER")
    .route("admin.audit").hasRole("ADMIN")
    .anyRequest().denyAll()
    .anyExchange().permitAll()
);
```

Order specifics before fallbacks:
- `.setup()` is the rule for SETUP;
- `.route("...")` for defined request routes;
- `.anyRequest().denyAll()` for unknown/invalid unlisted requests;
- `.anyExchange().permitAll()` for remaining exchanges **that are not initial requests** (must be carefully evaluated when metadata push/channels are used).

### 4.2 Wrong: anyRequest before specific routes

```java
// WRONG: every request hits this rule first.
.authorizePayload(authz -> authz
    .anyRequest().authenticated()
    .route("admin.audit").hasRole("ADMIN")
    .anyExchange().permitAll()
)
```

Because `anyRequest()` matches the admin request first, the admin rule becomes ineffective: any authenticated user can bypass route authorization. This is a **privilege escalation** bug, not merely a style issue.

### 4.3 Wrong: anyExchange().permitAll() at the top

```java
// SEVERE BUG: anyExchange matches everything.
.authorizePayload(authz -> authz
    .anyExchange().permitAll()
    .route("admin.audit").hasRole("ADMIN")
)
```

Subsequent rules are never evaluated. Never place broad fallbacks before routes with security restrictions.

### 4.4 Why not default to anyExchange().denyAll()?

In `REQUEST_CHANNEL` or certain interactions, continuation `PAYLOAD`s may **lack fresh routing metadata**. If you `denyAll()` every non-request exchange, you can block payloads belonging to an already-authorized stream.

Per Spring Security RSocket docs, `anyRequest()` matches initial requests, while `anyExchange()` also matches payloads without metadata/routing. The sample config uses `anyRequest().denyAll()` and `anyExchange().permitAll()` to:
1. Block every **initial request** without a route rule;
2. Allow **continuation frames** so an accepted stream/channel can function.

**Do not misunderstand:** `anyExchange().permitAll()` **is not a license** for metadata-push or subsequent payloads to perform unchecked sensitive operations. For `METADATA_PUSH`, `@ConnectMapping`, custom interceptors, or channel mutations, add dedicated checks and/or `matcher(...)` for exchange types needing protection. The demo does not handle privileged metadata-push.

## 5. Authentication at SETUP or per request?

### 5.1 SETUP authentication

The client sends authentication metadata when opening the connection. Scenarios:

- An RSocket connection dedicated to **one identity**;
- A mobile/desktop user maintaining a session connection;
- A service-to-service connection with a stable service principal.

```text
CONNECT TCP/TLS -> SETUP(credentials user=reader)
                     |
                     +-- auth fail -> connection rejected
                     |
                     +-- auth success -> SecurityContext for connection
                                              |
                                              +-- events.stream -> ROLE_READER?
                                              +-- admin.audit   -> ROLE_ADMIN?
```

Pros: reduces verification cost per message/route; the connection uses a stable identity. Cons: if a token/permission is revoked mid-**long stream**, the system does not automatically re-check after every event.

### 5.2 Request-time authentication

A backend gateway may share one RSocket connection across multiple users. In that case, **SETUP** only confirms the app/gateway identity (`ROLE_CONNECT`), while **each request** carries the specific user's credentials:

```text
SETUP: trusted gateway token, role CONNECT
  |
  +-- REQUEST_STREAM route=users.alice.events
  |        authentication metadata: access token of alice
  |
  +-- REQUEST_RESPONSE route=users.bob.profile
           authentication metadata: access token of bob
```

When using request-time auth, never grant user data permissions automatically just because the connection has `ROLE_CONNECT`. The service identity that opens the socket is **distinct** from the user identity used for route/tenant-specific data.

### 5.3 Both can be combined

Spring Security docs describe using auth at both setup and per request. For example:
- Setup credentials carry authority `ROLE_CONNECT`, without `ROLE_READ_PERSONAL_DATA`.
- User request credentials carry scopes/roles used on routes.
- Sensitive routes require user-specific authorities, never relying solely on the setup role.
- Scope and tenant are checked by the server via the trusted principal.

**Important:** Never use user A's token as the "default identity" for an entire connection shared by users B/C. If a backend reuses an `RSocketRequester` with `setupMetadata(userAToken)`, it can accidentally invoke routes on A's behalf during B's requests.

## 6. What RSocket metadata needs to be controlled?

### 6.1 Routing metadata

MIME:

```text
message/x.rsocket.routing.v0
```

Sender uses `requester.route("...")`; responder uses `@MessageMapping("...")`. Clients can **choose the route string themselves**, so:
- Never grant permissions automatically just because a route starts with `admin.` or contains "trusted";
- Register route-specific policies in `authorizePayload`;
- Block unknown request routes with `anyRequest().denyAll()`;
- For route patterns with path variables, variable values are **untrusted input**;
- For routes like `tenant.events.{tenantId}`, verify `tenantId` against the token/connection principal rather than checking only `ROLE_READER`.

### 6.2 Authentication metadata

Common MIME:

```text
message/x.rsocket.authentication.v0
```

Spring Security RSocket provides types:
- `UsernamePasswordMetadata` for **Simple Authentication Metadata Extension**;
- `BearerTokenMetadata` for JWT access tokens;
- `SimpleAuthenticationEncoder` and `BearerTokenAuthenticationEncoder` on the sender side, with corresponding converters on the receiver side.

**Not HTTP headers.** `Authorization: Basic`/`Authorization: Bearer` belong to HTTP, whereas RSocket Simple/Bearer credentials are separate **metadata entries**. If an RSocket client calls `requester.metadata(...)` with the wrong MIME or without registering the encoder, the server may fail to read authentication even with valid credentials.

### 6.3 Composite metadata

Composite metadata allows route + auth + tenant/tracing entries to appear together. Entry order must never determine authority; MIME/codec types and server policy determine meaning.

Example:

```text
Request:
  route MIME: "tenant.events.north"
  authentication MIME: signed token for alice
  tenant MIME: "south"
```

The server **must not** assume the `north` route tenant or `south` tenant header is trustworthy. A request with conflicting metadata should be rejected/audited without leaking tokens. Trusted tenant identity comes from verified authentication + server-side tenant membership/ACL.

### 6.4 Custom metadata requires codec registration

Spring Messaging provides `RSocketStrategies`, `MetadataExtractorRegistry`, and `@Header`. When adding fields like tenant/trace, declare a dedicated MIME, choose a clear codec, and configure the extractor on the server and encoder on the client.

`@Header("tenant-id")` **does not verify** the tenant. It only reads **decoded** metadata. Role/scope authorization belongs in RSocket Security; resource/tenant authorization belongs in the business layer or a trusted custom `ReactiveAuthorizationManager`.

### 6.5 Metadata size and count

RSocket binary framing has metadata length/fragmentation; hardware, Netty codecs, and server policies enforce actual limits. Never let clients send arbitrarily huge metadata:
- Limit frame size, payload size, and decoding depth/types;
- Allowlist MIME types, routes, and metadata keys;
- Never accept an unknown MIME as a default role;
- Constrain tenant IDs/trace IDs (length, characters) to prevent log injection;
- Never log raw authentication metadata;
- Set connection/request/channel quotas, timeouts, and backpressure limits.

## 7. Designing the demo before writing code

The demo uses **one RSocket TCP server**, bound to loopback `127.0.0.1:7000` so demo passwords are never accidentally exposed on the network.

**Identities and permissions:**

| Username | Demo password | Granted authorities |
| --- | --- | --- |
| `reader` | `reader-secret` | `ROLE_CONNECT`, `ROLE_READER` |
| `admin` | `admin-secret` | `ROLE_CONNECT`, `ROLE_READER`, `ROLE_ADMIN` |
| `guest` | `guest-secret` | `ROLE_CONNECT` |

**Route policies:**

| Route | Interaction | Rule | Meaning |
| --- | --- | --- | --- |
| `status.ping` | Request-Response | `authenticated` | Properly set up connection can check status |
| `events.stream` | Request-Stream | `hasRole("READER")` | View 3 sample events |
| `events.channel` | Request-Channel | `hasRole("READER")` | Send 2 messages and receive acknowledgments |
| `tenant.read.{tenant}` | Request-Response | `hasRole("READER")` + server ACL | Reader allowed only for `north`; admin allowed for both |
| `admin.audit` | Request-Response | `hasRole("ADMIN")` | Admin-only route |
| Unlisted route | Any initial request | `denyAll` | Never expose new features by default |
| SETUP | Connection setup | `hasRole("CONNECT")` | Connection requires credentials |
| Continuation payload | Channel/stream payload | `anyExchange permitAll` | Does not replace item validation |

This is a **limited demo**. Production must pull permissions from a trusted IAM/policy DB, encrypt transport, and use proper identities — never these 3 demo accounts.

## 8. Complete Spring Boot 3.5 / Java 17+ project

### 8.1 Dependencies

Create a Spring Initializr project with Java 17+, Spring Boot 3.5.x, Gradle Groovy. With a project already having the Spring Boot plugin and dependency management, the `dependencies` block needs:

```groovy
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
```

**Standalone RSocket TCP does not require `spring-boot-starter-webflux`.** RSocket itself is already reactive, built on Reactor and Spring Messaging. If the same app also serves WebFlux HTTP, you can add `spring-boot-starter-webflux`, but the HTTP security chain is separate. Never replace `spring-security-rsocket` with just `spring-security-web` and assume RSocket route policies are enabled.

### 8.2 File structure

```text
src/main/java/com/example/securestream/
  SecureStreamApplication.java
  RSocketRouteSecurityConfig.java
  EventRSocketController.java
src/main/resources/
  application.yml
src/test/java/com/example/securestream/
  RSocketRouteSecurityTest.java
```

Each public class resides in a properly named Java file. `SecureStreamApplication` is the main class; `RSocketRouteSecurityTest` is an integration test starting the server on a **random port**. No WebFlux HTTP server is needed for this sample.

### 8.3 application.yml

`src/main/resources/application.yml`:

```yaml
spring:
  rsocket:
    server:
      address: 127.0.0.1
      transport: tcp
      port: 7000
```

The RSocket TCP server binds only on localhost; `tcp` does not automatically provide TLS. **For learning only.** For production network exposure, configure RSocket TLS/SSL or trusted TLS-terminating infrastructure; never let Simple Authentication credentials travel over public plaintext TCP.

### 8.4 SecureStreamApplication.java

`src/main/java/com/example/securestream/SecureStreamApplication.java`:

```java
package com.example.securestream;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecureStreamApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecureStreamApplication.class, args);
    }
}
```

### 8.5 RSocketRouteSecurityConfig.java

`src/main/java/com/example/securestream/RSocketRouteSecurityConfig.java`:

```java
package com.example.securestream;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

@Configuration(proxyBeanMethods = false)
@EnableRSocketSecurity
public class RSocketRouteSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder encoder) {

        var reader = User.withUsername("reader")
            .password(encoder.encode("reader-secret"))
            .roles("CONNECT", "READER")
            .build();

        var admin = User.withUsername("admin")
            .password(encoder.encode("admin-secret"))
            .roles("CONNECT", "READER", "ADMIN")
            .build();

        var guest = User.withUsername("guest")
            .password(encoder.encode("guest-secret"))
            .roles("CONNECT")
            .build();

        return new MapReactiveUserDetailsService(
            reader, admin, guest
        );
    }

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity rsocket) {

        return rsocket
            .authorizePayload(authz -> authz
                // First rule: require authenticated CONNECT authority.
                .setup().hasRole("CONNECT")

                // Specific routes before the deny-all fallback.
                .route("status.ping").authenticated()
                .route("events.stream").hasRole("READER")
                .route("events.channel").hasRole("READER")
                .route("tenant.read.{tenant}").hasRole("READER")
                .route("admin.audit").hasRole("ADMIN")

                // An unknown new request must NEVER be public by default.
                .anyRequest().denyAll()

                // Continued PAYLOADs may lack routing metadata.
                // This is NOT a substitute for per-item domain checks.
                .anyExchange().permitAll()
            )
            .simpleAuthentication(Customizer.withDefaults())
            .build();
    }
}
```

**Configuration analysis:**

1. `@EnableRSocketSecurity` configures RSocket support, not the HTTP WebFlux filter chain.
2. The `PayloadSocketAcceptorInterceptor` bean is automatically attached to the RSocket server by Spring Boot when dependencies/auto-config are right.
3. `simpleAuthentication()` uses the RSocket Simple Authentication Metadata Extension, **not HTTP Basic**.
4. `MapReactiveUserDetailsService` returns demo user data, and `PasswordEncoder` stores encoded passwords in memory.
5. `.setup().hasRole("CONNECT")` requires SETUP credentials to have `ROLE_CONNECT`.
6. The `route` rules form a per-permission allowlist. `.route("tenant.read.{tenant}")` matches the route pattern, and the variable value is **untrusted input**.
7. `.anyRequest().denyAll()` denies initial requests to any other route.
8. `.anyExchange().permitAll()` does not open unknown routes because prior requests already matched `anyRequest().denyAll()`; it serves non-new-request exchanges. Review metadata-push, channel data, and custom handlers separately.

**Do not** replace `.anyRequest().denyAll()` with `.anyRequest().authenticated()` just to make testing easier: doing so would leave any newly added route—even administrative ones—requiring only login by default.

### 8.6 EventRSocketController.java

`src/main/java/com/example/securestream/EventRSocketController.java`:

```java
package com.example.securestream;

import java.time.Duration;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class EventRSocketController {

    @MessageMapping("status.ping")
    public Mono<String> ping() {
        return Mono.just("OK");
    }

    @MessageMapping("events.stream")
    public Flux<String> events() {
        return Flux.interval(Duration.ofMillis(100))
            .take(3)
            .map(n -> "event-" + (n + 1));
    }

    @MessageMapping("events.channel")
    public Flux<String> channel(Flux<String> messages) {
        // Limit accepted items in this teaching example.
        // Production also needs byte-size, request-rate and time limits.
        return messages
            .take(2)
            .map(msg -> {
                if (msg.length() > 256) {
                    throw new IllegalArgumentException(
                        "Message too long");
                }
                return "ack:" + msg;
            });
    }

    @MessageMapping("admin.audit")
    public Mono<String> adminAudit() {
        return Mono.just("AUDIT-OK");
    }

    @MessageMapping("tenant.read.{tenant}")
    public Mono<String> tenantRead(
            @DestinationVariable String tenant) {

        // This is a small, deliberate server-side ACL illustration.
        // Route variable is NOT trusted just because it is metadata.
        return ReactiveSecurityContextHolder.getContext()
            .switchIfEmpty(Mono.error(
                new AccessDeniedException("Missing security context")))
            .flatMap(context -> {
                Authentication auth = context.getAuthentication();
                if (auth == null || !auth.isAuthenticated()) {
                    return Mono.error(new AccessDeniedException(
                        "Unauthenticated"));
                }

                boolean permitted =
                    "admin".equals(auth.getName())
                    && ("north".equals(tenant)
                        || "south".equals(tenant));

                permitted = permitted
                    || ("reader".equals(auth.getName())
                        && "north".equals(tenant));

                if (!permitted) {
                    return Mono.error(new AccessDeniedException(
                        "Tenant not permitted"));
                }

                return Mono.just("tenant:" + tenant);
            });
    }
}
```

This is a **simple demo ACL**:
- `reader` has `ROLE_READER` but is only allowed `tenant.read.north`.
- `admin` has `ROLE_READER` and `ROLE_ADMIN`, allowed both `north`/`south`.
- `guest` only has `CONNECT`, so it cannot reach the tenant route because it lacks `ROLE_READER`.

The goal is to prove **route-level roles do not replace ownership/tenant-level checks**. In real applications, `permitted` comes from trusted tenant membership / database / authorization service and must query by verified principal + tenant/resource, never hardcoding usernames.

### 8.7 Error if tenant check is omitted in Controller

If code only used `.route("tenant.read.{tenant}").hasRole("READER")` and then returned data for any tenant in the route variable, user `reader` could call `tenant.read.south` to read south's tenant data. The `READER` rule only says the user has a "read" type of permission, **not which tenant they may read**.

Any route variable, data body, or custom metadata must be treated as **untrusted request input**. Never concatenate a route variable directly into unparameterized SQL or unchecked file paths.

## 9. RSocketRequester sending Simple Authentication metadata

For **RSocket Simple Authentication**, the sender needs:

1. Proper authentication MIME `message/x.rsocket.authentication.v0`.
2. `UsernamePasswordMetadata` carrying username/password.
3. `SimpleAuthenticationEncoder` added to the client's `RSocketStrategies`.
4. `setupMetadata(...)` before connecting if auth is at SETUP; or `metadata(...)` on each request if auth is at request time.
5. TLS on real networks so credentials are not exposed.

Builder example:

```java
MimeType authMime = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(builder ->
        builder.encoder(new SimpleAuthenticationEncoder()))
    .setupMetadata(
        new UsernamePasswordMetadata("reader", "reader-secret"),
        authMime)
    .tcp("127.0.0.1", 7000);
```

This is a **snippet**; it needs imports for `RSocketRequester` from Spring Messaging, `MimeType`/`MimeTypeUtils`, `WellKnownMimeType`, `UsernamePasswordMetadata`, and `SimpleAuthenticationEncoder`. `tcp(...)` in Spring Framework 6.x returns a requester whose connection is established on request; part of the modern client builder API. When finished, call `requester.dispose()` to release resources.

Never copy an HTTP `Authorization: Basic ...` header into RSocket `.metadata(...)` with an arbitrary MIME expecting `.simpleAuthentication()` to understand it: RSocket authentication metadata uses a different format.

### 9.1 Sending per-request metadata (variant)

If an RSocket connection is **already allowed to open** and you want to switch the principal per request, Spring supports `.metadata(credentials, authMime)`:

```java
UsernamePasswordMetadata perRequestUser =
    new UsernamePasswordMetadata("reader", "reader-secret");

Flux<String> stream = requester
    .route("events.stream")
    .metadata(perRequestUser, authMime)
    .retrieveFlux(String.class);
```

The snippet above **assumes** `requester` is already created and the Simple Authentication encoder is registered. If the server uses `.setup().hasRole("CONNECT")`, **SETUP must still provide an identity with `ROLE_CONNECT`**, while per-request credentials can be a different identity. Never use a privileged setup principal that can read personal data as a fallback for multiple users' requests.

### 9.2 Using Bearer JWT metadata instead of Simple Authentication

When using OAuth2 JWT:

```java
@Bean
PayloadSocketAcceptorInterceptor rsocketInterceptor(
        RSocketSecurity rsocket) {

    return rsocket
        .authorizePayload(authz -> authz
            .setup().authenticated()
            .route("events.stream").hasAuthority("SCOPE_events.read")
            .route("admin.audit").hasAuthority("SCOPE_events.admin")
            .anyRequest().denyAll()
            .anyExchange().permitAll())
        .jwt(Customizer.withDefaults())
        .build();
}
```

This is a **replacement bean**; **do not** enable it alongside the Simple Authentication bean above. To work, it needs a real `ReactiveJwtDecoder` configured by the app/Boot, e.g., from a trusted issuer/JWKs. On the sender side, use `BearerTokenMetadata`, `BearerTokenAuthenticationEncoder`, and the RSocket auth MIME; never trust a Base64-decoded JWT payload without verifying the signature.

Note that `hasRole("READER")` checks authority `ROLE_READER`, whereas `hasAuthority("SCOPE_events.read")` checks the exact scope authority. A JWT Resource Server must validate signature, `iss`, `exp`, `nbf`, and `aud` per trust policy; RSocket stream auth does not replace audience validation.

## 10. Real RSocket integration tests with StepVerifier

The tests below start a **real embedded RSocket TCP server** on a random port and use a real `RSocketRequester`, without mocking authentication. The test is responsible for disposing the requester after each request.

### 10.1 File RSocketRouteSecurityTest.java

`src/test/java/com/example/securestream/RSocketRouteSecurityTest.java`:

```java
package com.example.securestream;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.SimpleAuthenticationEncoder;
import org.springframework.security.rsocket.metadata.UsernamePasswordMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

import io.rsocket.metadata.WellKnownMimeType;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(properties = {
    "spring.rsocket.server.address=127.0.0.1",
    "spring.rsocket.server.transport=tcp",
    "spring.rsocket.server.port=0"
})
class RSocketRouteSecurityTest {

    @Value("${local.rsocket.server.port}")
    int port;

    private static final MimeType AUTH_MIME =
        MimeTypeUtils.parseMimeType(
            WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString()
        );

    private RSocketRequester requester(String user, String password) {
        return RSocketRequester.builder()
            .rsocketStrategies(b ->
                b.encoder(new SimpleAuthenticationEncoder()))
            .setupMetadata(
                new UsernamePasswordMetadata(user, password),
                AUTH_MIME)
            .tcp("127.0.0.1", port);
    }

    private Mono<String> request(
            String user, String password, String route) {

        // Use and dispose a dedicated requester for the test.
        return Mono.using(
            () -> requester(user, password),
            r -> r.route(route).retrieveMono(String.class),
            RSocketRequester::dispose
        );
    }

    private Flux<String> stream(String user, String password) {
        return Flux.using(
            () -> requester(user, password),
            r -> r.route("events.stream").retrieveFlux(String.class),
            RSocketRequester::dispose
        );
    }

    private Flux<String> channel(String user, String password) {
        return Flux.using(
            () -> requester(user, password),
            r -> r.route("events.channel")
                .data(Flux.just("one", "two"), String.class)
                .retrieveFlux(String.class),
            RSocketRequester::dispose
        );
    }

    @Test
    void readerCanPing() {
        StepVerifier.create(
            request("reader", "reader-secret", "status.ping"))
            .expectNext("OK")
            .verifyComplete();
    }

    @Test
    void readerCanOpenRequestStream() {
        StepVerifier.create(stream("reader", "reader-secret"))
            .expectNext("event-1", "event-2", "event-3")
            .verifyComplete();
    }

    @Test
    void readerCanOpenChannel() {
        StepVerifier.create(channel("reader", "reader-secret"))
            .expectNext("ack:one", "ack:two")
            .verifyComplete();
    }

    @Test
    void guestCanPingButCannotReadEvents() {
        StepVerifier.create(
            request("guest", "guest-secret", "status.ping"))
            .expectNext("OK")
            .verifyComplete();

        StepVerifier.create(stream("guest", "guest-secret"))
            .expectError()
            .verify();
    }

    @Test
    void readerCannotCallAdminAudit() {
        StepVerifier.create(
            request("reader", "reader-secret", "admin.audit"))
            .expectError()
            .verify();
    }

    @Test
    void adminCanCallAdminAudit() {
        StepVerifier.create(
            request("admin", "admin-secret", "admin.audit"))
            .expectNext("AUDIT-OK")
            .verifyComplete();
    }

    @Test
    void unknownRouteIsNotAllowed() {
        StepVerifier.create(
            request("admin", "admin-secret", "secret.new.route"))
            .expectError()
            .verify();
    }

    @Test
    void wrongSetupPasswordCannotUseConnection() {
        StepVerifier.create(
            request("reader", "wrong-password", "status.ping"))
            .expectError()
            .verify();
    }

    @Test
    void tenantMembershipCheckedAfterRouteRole() {
        StepVerifier.create(
            request("reader", "reader-secret", "tenant.read.north"))
            .expectNext("tenant:north")
            .verifyComplete();

        StepVerifier.create(
            request("reader", "reader-secret", "tenant.read.south"))
            .expectError()
            .verify();

        StepVerifier.create(
            request("admin", "admin-secret", "tenant.read.south"))
            .expectNext("tenant:south")
            .verifyComplete();
    }
}
```

**Important notes:**
- `@Value("${local.rsocket.server.port}")` reads the local RSocket port published to the Environment by Spring Boot 3.x test infrastructure after the embedded server starts. Distinct from HTTP's `server.port`.
- The `unknownRouteIsNotAllowed` test expects an error, though if the framework reports "no route handler found" instead of a security denial, the test only proves the request returns no data. To assert specifically that the rule triggered, add metrics/test authorization manager or custom logging/test spy.
- `.expectError()` in negative tests verifies the request did not succeed, **without distinguishing all RSocket error codes**. In RSocket, errors are typically propagated via stream error signals/ERROR frames rather than direct HTTP 401/403 status codes.
- Auth setup uses demo credentials, currently over TCP loopback. Never use real passwords in committed tests.
- `Mono.using` and `Flux.using` call `dispose()` when the publisher finishes to avoid holding open many RSocket connections.
- The tests have no IdP/JWT and do not prove TLS, token expiry/rotation, or mid-stream revocation. Each of those groups needs separate integration tests.

### 10.2 Run commands

Linux/macOS:

```bash
./gradlew test --tests '*RSocketRouteSecurityTest'
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*RSocketRouteSecurityTest'
.\gradlew.bat bootRun
```

The demo TCP server app is configured on port `7000` for `bootRun`; **tests set port `0`** to avoid colliding with a running app. You do not need to run `bootRun` before running tests.

**Expected outcomes** (not test logs executed during authoring):
- `reader` can ping, open the stream, and open the channel successfully;
- `guest` can only ping, cannot read the stream;
- `reader` cannot call admin;
- `admin` can call admin;
- wrong password SETUP is rejected;
- `tenant` `south` is rejected for `reader`;
- unknown routes return no data.

### 10.3 Changing only @MessageMapping in tests is not enough

If you rename `@MessageMapping("admin.audit")` to `@MessageMapping("admin.download")` while forgetting to update `authorizePayload`, `anyRequest().denyAll()` will block the new route — that is a safe default. Had you written `anyRequest().authenticated()` earlier, the new route could **be open to every logged-in user**.

Therefore, whenever adding a route:
1. Explicitly define the role/scope/tenant policy;
2. Write a negative test for an "authenticated user lacking permission";
3. Only then permit the route in the DSL;
4. Run integration tests over **real RSocket transport**, not just direct controller method calls.

## 11. Registering a custom metadata MIME and reading via @Header

A common requirement: the client sends `tenant-id` to select a dataset or `trace-id` to trace a request. **Metadata must not be trusted as permission**; it is only input.

### 11.1 Server-side metadata extractor

If adding metadata type:

```text
message/x.example.tenant.v1
```

We need to register an extractor for `String`:

```java
package com.example.securestream;

import org.springframework.boot.rsocket.messaging.RSocketStrategiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.codec.StringDecoder;
import org.springframework.util.MimeType;

@Configuration(proxyBeanMethods = false)
public class TenantMetadataConfig {

    public static final MimeType TENANT_MIME =
        MimeType.valueOf("message/x.example.tenant.v1");

    @Bean
    RSocketStrategiesCustomizer tenantMetadata() {
        return strategies -> strategies
            .decoder(StringDecoder.allMimeTypes())
            .metadataExtractorRegistry(registry ->
                registry.metadataToExtract(
                    TENANT_MIME, String.class, "tenant-id"));
    }
}
```

**This is an optional additional Java file**, not needed for the main demo/tests in sections 8–10. `RSocketStrategiesCustomizer` is used by Spring Boot to customize codecs/metadata extractors; the extractor decodes entries by MIME and stores them under key `tenant-id`.

With a custom MIME and String data, we add `StringDecoder.allMimeTypes()` so metadata decoding is not restricted solely to `text/plain`. Never configure "ignore all unknown metadata"; unknown security metadata must be rejected or never allowed to create an identity.

### 11.2 Client sending metadata with route

```java
import org.springframework.core.codec.CharSequenceEncoder;
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester r = RSocketRequester.builder()
    .rsocketStrategies(b -> {
        b.encoder(new SimpleAuthenticationEncoder());
        b.encoder(CharSequenceEncoder.allMimeTypes());
    })
    .setupMetadata(
        new UsernamePasswordMetadata("reader", "reader-secret"),
        AUTH_MIME)
    .tcp("127.0.0.1", 7000);

Mono<String> result = r.route("tenant.read.north")
    .metadata("north", TenantMetadataConfig.TENANT_MIME)
    .retrieveMono(String.class);
```

This is a **client snippet**; it needs imports for `UsernamePasswordMetadata`, `SimpleAuthenticationEncoder`, `Mono`, and `AUTH_MIME` as in section 10. This snippet **is not a complete file**. `CharSequenceEncoder.allMimeTypes()` allows String metadata to be encoded under a custom MIME.

### 11.3 Controller @Header and metadata verification

A handler variant:

```java
@MessageMapping("tenant.read.{tenant}")
public Mono<String> tenantRead(
        @DestinationVariable String tenant,
        @Header(value = "tenant-id", required = false)
        String tenantMetadata) {

    if (tenantMetadata == null
            || !tenantMetadata.equals(tenant)) {
        return Mono.error(new AccessDeniedException(
            "Tenant route and metadata differ"));
    }

    return trustedTenantPolicy.checkCurrentPrincipal(tenant)
        .flatMap(allowed -> allowed
            ? Mono.just("tenant:" + tenant)
            : Mono.error(new AccessDeniedException(
                "Tenant not permitted")));
}
```

**This is a policy method snippet**, not a standalone compilable replacement method: `trustedTenantPolicy` is a service a real app must implement using verified authentication + a trusted ACL. It requires imports `@MessageMapping`, `@DestinationVariable`, `@Header`, `AccessDeniedException`, and `Mono`. We deliberately do not implement `trustedTenantPolicy` by merely comparing two client-controlled strings: **consistent route and metadata still do not mean the user is authorized for that tenant**.

In real applications, tenant metadata may be omitted completely if the tenant is derived from trusted JWT claims/session/membership. The purpose of `@Header` is solely to extract metadata **after decoding**, not to elevate it into a source of authority.

### 11.4 Metadata tests to include

- Missing `tenant-id` when the route requires it → reject;
- Empty/overlong `tenant-id` or characters outside allowlist → reject;
- Route tenant `north`, metadata tenant `south` → reject;
- `reader` with role `READ` who **does not belong to `north`** → reject;
- `admin` permitted for `north`/`south` per trusted ACL → succeed;
- Caller tries sending custom metadata `role=ADMIN` → **must not receive `ROLE_ADMIN`**;
- One payload with multiple entries for the same `tenant` key → deterministic single rule, avoiding arbitrary first/last selection;
- Unsupported MIME and malformed composite metadata → must not bypass auth;
- Malicious `trace-id` containing newlines/escapes/control chars → sanitize before logging;
- Raw authentication metadata must never appear in tracing/metrics.

## 12. JWT and Bearer authentication metadata: when using an IdP

RSocket has the **Bearer Token Authentication Metadata Extension**. In Spring Security, the sender can use `BearerTokenMetadata` and `BearerTokenAuthenticationEncoder`, and the receiver uses `RSocketSecurity.jwt(...)`.

Client example (snippet):

```java
MimeType authenticationMimeType =
    MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString()
    );

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(b ->
        b.encoder(new BearerTokenAuthenticationEncoder()))
    .setupMetadata(
        new BearerTokenMetadata("<REDACTED_SIGNED_JWT>"),
        authenticationMimeType)
    .tcp("127.0.0.1", 7000);
```

Requires imports `BearerTokenMetadata` and `BearerTokenAuthenticationEncoder` from the Spring Security RSocket metadata package. Placeholder `<REDACTED_SIGNED_JWT>` **is not a usable token**.

**Differences from HTTP:**
- Do not send an HTTP `Authorization: Bearer` header expecting RSocket JWT auth to read it automatically.
- The JWT resides in the RSocket auth metadata MIME.
- The server must have an appropriate `ReactiveJwtDecoder` to verify signature and issuer/expiry/audience.
- Scopes are mapped to authorities such as `SCOPE_events.read` per decoder/authorities converter.
- A token for route A must not automatically be sent to service/issuer B if the client connects to multiple backends.

### 12.1 Token expiration in a long stream

When a JWT is verified **at SETUP** or **when opening a request**, a stream can keep emitting data past the original `exp` unless the app enforces rechecks/cancellation. **Do not assume Spring Security automatically cancels all running streams the exact second a token expires**, or re-introspects per event.

For sensitive data:
- Set max stream/session duration;
- Use periodic reauthorization or bind stream lifetime to the verified token expiration;
- When revoked/permissions change, signal connection closure/stream cancellation via a session registry or event-driven policy;
- With request-time auth, require the client to supply a fresh token when opening new requests;
- Use short-lived tokens, refreshing in the OAuth2 Client **outside the RSocket resource stream**, never sending refresh tokens into Resource Server metadata;
- Check downstream ACLs when reading each resource if required by the threat model;
- Stop emitting immediately when a principal is disabled or tenant access is revoked per policy.

## 13. Long streams, request-channel, and per-payload permissions

### 13.1 Request-stream

`events.stream` only needs one initial `REQUEST_STREAM`; the server sends many `PAYLOAD`s until completion or cancellation. The rule `route("events.stream").hasRole("READER")` protects **opening the stream**, without proving every future emitted event remains permitted.

If a stream runs for hours, you need:
- `timeout`/session lifetime;
- periodic recheck/reauthorization or on permission-change events;
- consumer-side cancellation;
- server-side resource policies by tenant/subject;
- active stream quotas per principal;
- limits on event/byte count, memory, and retention for slow clients.

### 13.2 Request-channel

`REQUEST_CHANNEL` carries the initial request with routing metadata; subsequent payloads typically lack a new route. Therefore:
- Check route and identity on the **initial request**;
- Validate each data item for length/schema/tenant/authorization context;
- Prevent a later message from asserting `role=ADMIN` to gain different privileges;
- Require fresh authorization on reconnect/channel restart;
- Respect `request(n)` backpressure/`CANCEL`; never open unbounded streams just because the user is authenticated;
- Enforce per-message and per-channel quotas, not just per-connection rate limiting.

In the demo code, `events.channel` uses `take(2)` and a 256-char String limit for illustration; production must also enforce pre-decode byte limits, quotas, timeouts, and business rule checks.

### 13.3 Metadata-push and SETUP

`METADATA_PUSH` is a connection-level interaction that may be handled by `@ConnectMapping`. **Do not treat it as a route that has passed `.route("...").hasRole(...)`** if the payload lacks request route metadata.

When the app handles metadata-push to change a subscription/tenant/feature flag:
- Explicitly authorize against the current trusted connection principal;
- For identity changes, never accept a metadata push self-declaring a new user;
- Never use metadata-push to "refresh" authentication without going through a trusted auth flow;
- If metadata-push is unused, reject/ignore it via an explicit policy;
- Inspect RSocket `PayloadExchangeType` in custom matchers/interceptors when specific exchange types must be blocked;
- Keep `anyExchange().permitAll()` only when all remaining handlers/interactions are architecturally safe.

### 13.4 Backpressure is not authorization

RSocket uses Reactive Streams demand to relieve stream pressure. However, backpressure:
- Does not know whether a user has scope/role/tenant permission;
- Does not block revoked tokens;
- Does not prevent DoS from a client opening thousands of streams without quotas;
- Does not replace payload validation and network policies.

Backpressure is **flow-control**; authorization is a **security decision**. Both must be designed together.

## 14. Controlling route variables and metadata in dynamic policies

### 14.1 Route variables are untrusted input

```text
tenant.read.north
tenant.read.south
tenant.read.anything
```

If the security DSL uses `route("tenant.read.{tenant}")`, all three routes can match **syntactically**. That neither proves the tenant is valid nor proves the user may read the specified tenant. The controller/service must compare the tenant ID against verified membership; when needed, use custom `.access((authentication, context) -> ...)` and a reactive policy service.

Do not build scopes via unchecked concatenation:
```java
// Bug-prone if metadata/route is client-controlled:
String wanted = "SCOPE_" + tenantIdFromRoute + ".admin";
```

Instead, the server maintains trusted tenant identifiers, grants, and per-resource ACLs; the client request specifies the **target it wants to access**, not the authority granted.

### 14.2 Custom PayloadExchangeMatcher

The Spring Security DSL supports `.matcher(PayloadExchangeMatcher)` and `.access(...)` for complex conditions. The matcher API uses `PayloadExchange`/exchange type and route metadata, rather than HTTP `ServerWebExchange`.

A **DSL structure example**, not a complete Java file:

```java
rsocket.authorizePayload(authz -> authz
    .setup().hasRole("CONNECT")
    .route("tenant.read.{tenant}")
        .access((authentication, context) ->
            policyService.canReadTenant(
                authentication, context))
    .anyRequest().denyAll()
    .anyExchange().permitAll()
);
```

Here `policyService.canReadTenant(...)` is a **hypothetical contract** you must implement, returning `Mono<AuthorizationDecision>` based on trusted user/tenant membership. Do not guess how to extract route variables from `context`: per the docs, matchers can provide route variables, but extraction keys/APIs should be verified against your exact Spring Security version. The complete sample in section 8 uses a route-level role **and** an ACL in the controller to avoid undefined imports/custom APIs.

### 14.3 Do not log arbitrary routes/metadata

Route strings and metadata can contain:
- PII/tenant/customer ID values;
- Escapes/newlines enabling log injection;
- Opaque bearer credentials;
- Unvalidated trace IDs;
- Huge sizes filling up logs.

Only log allowlisted route names, minimized principal IDs, sanitized request/stream correlation IDs, security decisions, and latencies. **Never log raw auth metadata, JWTs, usernames/passwords, token endpoint responses, or byte buffers**.

## 15. Common configuration errors

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Anyone can call admin route | `anyRequest().authenticated()` placed before `route("admin.*")` | Place specific routes first; fallback `denyAll` |
| Admin route is `permitAll` | `anyExchange().permitAll()` placed at top | Move to bottom; add negative tests |
| Cannot connect despite right username/password | Client missing `SimpleAuthenticationEncoder` or wrong auth MIME | Use `UsernamePasswordMetadata` + right MIME/encoder |
| Sending HTTP Basic header to RSocket | Protocol confusion | Use RSocket Simple Authentication metadata |
| Valid Bearer token still rejected | Missing JWT receiver/encoder, wrong issuer/expiry | Check `jwt()` + decoder + metadata MIME |
| Route opens but channel payload errors | `anyExchange().denyAll()` blocks continuation PAYLOADs | Separate initial request policy and non-request policy |
| Channel item treated as metadata permission | Per-message validation missing | Enforce per-item schema/tenant policy |
| Has `READER` role yet reads another tenant | Trusted `{tenant}` route variable | Trusted ACL check in handler/service |
| New handler added and any logged-in user can call it | Overly broad `anyRequest().authenticated()` fallback | Use `anyRequest().denyAll()` |
| Revoked token still emits stream items | Checked only at setup/initial request | Stream lifetime/recheck/cancellation/revocation events |
| Shared connection leaks user A's data to B | Setup identity used instead of request-time identity | Per-request user-specific auth |
| Metadata push changes role | Trusted custom metadata as source of authority | Block self-asserted roles; trusted auth only |
| Custom MIME not read via `@Header` | Missing `metadataExtractorRegistry` or codec | Register MIME, decoder, and metadata key |
| Custom MIME string fails to encode | Encoder only supports `text/plain` | Add appropriate `CharSequenceEncoder.allMimeTypes()` |
| RSocket over WebSocket already HTTP-authenticated | Assumed HTTP handshake covers all routes | Configure RSocket Security separately |
| Manually created server has no security | Forgot to attach `SecuritySocketAcceptorInterceptor` | Attach interceptor to `RSocketServer` |
| Direct controller unit tests pass | Bypassed security socket acceptor | Test via real `RSocketRequester` |
| Unknown route test errors for unclear reason | Nonexistent handler also errors | Inspect error type/security metric; add a disallowed existing handler |
| CORS error with browser WebSocket | Origin/handshake policy | Check HTTP upgrade/origin and RSocket auth separately |
| Many requests spike memory | Unlimited channels/connections | Per-principal quotas, frame limits, timeouts |
| Password leaked on network | Plaintext TCP used for Simple Authentication | TLS or loopback-only demo |
| `@ConnectMapping` mutates business state unchecked | Metadata push/setup bypassed route auth | Separate authorization/validation |
| Route matcher pattern too broad | `admin.*` accidentally matches unintended routes | Exact matches, test patterns |
| Breaks on Spring Security upgrade | DSL/MIME/decoder changes | Pin/test Boot/Security/RSocket versions |

## 16. Responsible debugging workflow

When a connection or route is rejected, identify the **failing stage** before fixing:

1. **TCP/WebSocket**: host, port, DNS, TLS, origin, proxy, handshake; if connection refused, it has not even reached route authorization.
2. **RSocket SETUP**: data/metadata MIME, simple/bearer encoder, credentials, `setup()` rule; if failing right at connect/use, check here.
3. **Routing metadata**: did the client call the exact `route("...")` and does the server have a matching `@MessageMapping`?
4. **Authentication**: was identity verified from SETUP or per-request credentials? Don't stare at a token string and guess.
5. **Authorization**: principal roles/scopes; policy order/fallback; route variables/tenant ACL.
6. **Codec**: do data MIME, custom metadata MIME, and encoder/decoder share the same contract?
7. **Stream lifecycle**: expiry/revocation, backpressure, cancel, timeouts, channel item limits, connector reconnect.
8. **Observability**: logs/error metrics scrubbed of secrets; never enable global wiretap logging raw metadata in production.

RSocket errors are sent via reactive error signals or protocol ERROR frames; **there are no HTTP 401/403 codes per RSocket route**. With RSocket over WebSocket, HTTP status only relates to the handshake/upgrade at a different layer. `expectError()` tests cannot distinguish every security error unless you inspect the exception type.

## 17. Production checklist

- [ ] RSocket TCP/WebSocket endpoints are intentionally exposed with TLS/trusted network boundaries.
- [ ] Spring Boot attaches `SecuritySocketAcceptorInterceptor`, with no unauthenticated standalone server bypass.
- [ ] `@EnableRSocketSecurity` and a `PayloadSocketAcceptorInterceptor` bean are present.
- [ ] Setup vs. per-request authentication matches the identity/connection reuse model.
- [ ] `SimpleAuthenticationEncoder` / `BearerTokenAuthenticationEncoder` and MIME types are correct on the client.
- [ ] JWT access tokens verify signature/issuer/audience/expiry/allowed algorithms; refresh tokens are never sent to the Resource Server.
- [ ] `.setup()` rule is explicit; connection principals do not automatically grant data permissions.
- [ ] Route-specific roles/scopes are declared **before** fallbacks.
- [ ] `anyRequest().denyAll()` blocks unlisted request routes.
- [ ] `anyExchange()` policy is audited for channel follow-ups and metadata push.
- [ ] All route variables and custom metadata are treated as untrusted input.
- [ ] Domain ACL checks principal/tenant/resource ownership when needed.
- [ ] Custom metadata has explicit MIME and extractors; unknown/malformed metadata never grants permissions.
- [ ] No self-asserted `role=ADMIN` metadata/header is ever trusted directly.
- [ ] Long-lived streams have max duration, cancellation, and reauthorization/revocation strategies.
- [ ] Request-channel validates each item for schema/size/tenant/side effects.
- [ ] Per-principal connection/stream/channel quotas, backpressure, frame-size limits, and rate limits are configured.
- [ ] Logs/traces/metrics never store raw tokens, passwords, or authentication metadata.
- [ ] Integration tests run over RSocket transport, covering positive/negative cases, unknown routes, setup errors, streams/channels, and tenant ACLs.
- [ ] Tested with TLS, reverse proxies, WebSocket origins, reconnect/retry, and IdP/JWKS rotation if using JWT.
- [ ] Whenever adding a new handler, update the corresponding route policy/tests before deploying.
- [ ] Have runbooks for account disablement, session revocation, stream termination, and credential leaks.

## 18. Self-practice

**Exercise 1 — Check rule order.** Try moving `anyRequest().authenticated()` before `route("admin.audit").hasRole("ADMIN")`. Why can `reader` be considered eligible for the admin route at the authorization layer? Revert it so the route rule applies first.

**Exercise 2 — Fail-closed fallback.** Rename a route handler to `events.export` without updating the security DSL. Requirement: calling the new route must be denied by `anyRequest().denyAll()`, even for `admin`.

**Exercise 3 — Tenant authorization.** Write an ACL checking that `reader` belongs only to `north`. Even if the client uses `tenant.read.south` and sends metadata `tenant-id=south`, reject it if trusted membership denies it.

**Exercise 4 — Channel payload.** Create a client sending 10,000 messages in `events.channel`. Verify the server accepts at most the policy limit, actually cancels upstream when done, and enforces byte/connection quotas.

**Exercise 5 — Shared connection.** Keep setup identity with role `CONNECT` and require per-request auth. Verify user A cannot use user B's metadata/credentials and does not inherit permissions from the setup principal.

**Exercise 6 — JWT expiry.** Use a very short-exp token on a long stream. Prove with a test that **the policy you wrote** closes the stream on expiry/revocation, without assuming RSocket Security automatically re-checks every PAYLOAD.

**Exercise 7 — Metadata push.** Write `@ConnectMapping` allowing only a trusted client to update a non-sensitive parameter. Prove metadata-push cannot change roles/tenants/access.

### Self-check questions

**1. Is an RSocket route an HTTP URL?** No; it is encoded in routing metadata and used by `@MessageMapping`.

**2. What does `setup().hasRole("CONNECT")` protect?** SETUP/connection establishment; it does not replace domain ACLs on routes.

**3. Why does `anyRequest().denyAll()` come before `anyExchange().permitAll()`?** It blocks unmatched initial requests without accidentally denying all continuation PAYLOADs of a channel.

**4. What if `anyExchange().permitAll()` is placed before `route("admin.audit")`?** The admin rule is never evaluated; route authorization is lost.

**5. Does RSocket Simple Authentication use an HTTP Basic header?** No. It uses `UsernamePasswordMetadata` with the RSocket auth MIME and encoder.

**6. Does custom metadata `tenant=north` verify membership?** No. It is client input, requiring a server-side trusted principal/ACL.

**7. When should auth be sent per request?** When one connection is shared by multiple principals or user-level authorization is needed per request.

**8. When a JWT expires after a stream opens, is the stream cancelled automatically right away?** Do not assume so; refresh/recheck/cancellation/stream lifetime must be designed.

**9. What is a routeless request-channel payload?** A continuation frame inside an open channel that may lack fresh routing metadata; the initial request was authorized, yet data still needs validation.

**10. Why are controller unit tests alone insufficient?** Because they bypass the RSocket socket acceptor/authentication/authorization pipeline. Transport integration tests are needed.

## 19. Summary

Spring Security RSocket enables authorization by connection setup and **route metadata** via `RSocketSecurity.authorizePayload()`. A secure configuration requires:

```java
rsocket.authorizePayload(authz -> authz
    .setup().hasRole("CONNECT")
    .route("events.stream").hasRole("READER")
    .route("admin.audit").hasRole("ADMIN")
    .anyRequest().denyAll()
    .anyExchange().permitAll()
);
```

However, **route patterns do not replace domain ACLs**, **custom metadata is not verified authority**, and **long streams are not automatically reauthorized on every PAYLOAD**. Therefore, combine route policies, trusted authentication, metadata validation, tenant/resource authorization, quotas/backpressure, stream revocation, and real tests over RSocket transport.

**Final takeaway:** Only trust the principal after Spring Security authentication; always validate client-controlled routes/metadata; order route rules before fallbacks; keep long-lived streams bounded with cancellation when permissions change.

### Official references

- [Spring Security 6.5 — RSocket Security](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/rsocket.html)
- [Spring Security 6.5 — RSocketSecurity API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html)
- [Spring Security 6.5 — RSocketSecurity.AuthorizePayloadsSpec API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/rsocket/RSocketSecurity.AuthorizePayloadsSpec.html)
- [Spring Security 6.5 — PayloadExchangeType API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/rsocket/api/PayloadExchangeType.html)
- [Spring Framework 6.2 — RSocket protocol, RSocketRequester, MetadataExtractor](https://docs.spring.io/spring-framework/reference/6.2/rsocket.html)
- [Spring Boot 3.5 — RSocket auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/messaging/rsocket.html)
- [Spring Security RSocket Simple Authentication encoder](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/rsocket/metadata/SimpleAuthenticationEncoder.html)
- [Spring Security RSocket UsernamePasswordMetadata](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/rsocket/metadata/UsernamePasswordMetadata.html)
- [RSocket protocol specifications](https://rsocket.io/about/protocol/)
