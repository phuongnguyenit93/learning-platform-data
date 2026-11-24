# RSocket Security Support Scope and Differences from HTTP WebFlux Security

## 1. Who is this lesson for and what problem does it solve?

This lesson belongs to the **RSocket and long streams** group in the **Spring Security - reactive** module. When building status update systems, price tickers, chat, telemetry, or bidirectional interactive streams, many development teams use Spring WebFlux to expose HTTP APIs and RSocket for continuous message streaming. Both are based on Reactor `Mono`/`Flux`, but **RSocket Security is not HTTP WebFlux Security running on a different port**.

With HTTP WebFlux, Spring Security inspects **HTTP exchanges** via `SecurityWebFilterChain`, HTTP headers, URLs, and HTTP status codes. With RSocket, Spring Security inspects **RSocket SETUP and payload exchanges** via `SocketAcceptorInterceptor`/`PayloadSocketAcceptorInterceptor`, protocol metadata, routing, and RSocket error frames. Even when RSocket is transported inside WebSocket, RSocket messages **do not automatically become new HTTP requests** for `ServerHttpSecurity.authorizeExchange` to re-check.

After this lesson, you can:

1. Explain the RSocket protocol, SETUP, route, metadata, and the four interaction models: request-response, fire-and-forget, request-stream, and request-channel.
2. Distinguish the TCP/WebSocket transport layer from the RSocket application layer and the HTTP WebFlux layer.
3. Understand the exact scope of `@EnableRSocketSecurity`, `RSocketSecurity`, `PayloadSocketAcceptorInterceptor`, `AuthenticationPayloadInterceptor`, `AuthorizationPayloadInterceptor`, and `RSocketSecurityAutoConfiguration`.
4. Distinguish authentication **at SETUP** from **per-request** authentication (first request metadata), especially with a connection shared across multiple users.
5. Write `.setup()`, `.route(...)`, `.anyRequest()`, and `.anyExchange()` rules in the proper order; understand that request-level authorization does not mean checking every item in a long stream.
6. Use Simple Authentication metadata and JWT Bearer Authentication metadata of the right type, without confusing them with HTTP `Authorization: Basic/Bearer`.
7. Build a Java 17+, Spring Boot 3.3.13 example running **HTTP WebFlux 8080** and **RSocket TCP 7000** in the same application, but with **two independent security policies**.
8. Test HTTP using `WebTestClient` and RSocket using `RSocketRequester` + `StepVerifier`, including valid/invalid credentials, missing roles, SETUP failure, and request-stream.
9. Recognize limitations: token expiration while a stream is open, permission revocation, stream data tenant isolation, backpressure, fan-out, cancellation, TLS, proxies, and CORS/CSRF.
10. Choose the right solution for SSE, HTTP streaming, WebSocket, or RSocket rather than assuming all protocols have the same security guarantees.

**Key takeaway:** You need to design **two clear policy layers** when running HTTP WebFlux and RSocket together. Do not assume that protecting `GET /api/**` or the WebSocket handshake automatically protects every RSocket route and every subsequent message.

## 2. What is the RSocket protocol?

RSocket is a bidirectional messaging protocol supporting multiplexing of multiple logical requests over a single connection, demand/backpressure following the Reactive Streams model, and four interaction models.

| Interaction model | Data flow direction | Common Spring requester method |
| --- | --- | --- |
| Request-Response | Send one request, receive one response | `retrieveMono(...)` |
| Fire-and-Forget | Send a message, do not wait for a response payload | `send()` |
| Request-Stream | Send one request, receive multiple items | `retrieveFlux(...)` |
| Request-Channel | Both sides can stream multiple items | `data(Publisher)` + `retrieveFlux(...)` |

These interaction models **are not HTTP methods**. An RSocket `request-stream` is not an HTTP GET, and a `fire-and-forget` is not implicitly equivalent to HTTP POST.

### 2.1. SETUP, route, metadata, and data

When an RSocket client establishes a connection over TCP or WebSocket, it sends an RSocket **SETUP frame** with data/metadata format parameters and optionally carries authentication metadata.

```text
Client / requester                        Server / responder
        |                                            |
        | -- TCP connect / WebSocket upgrade ------> |
        |                                            |
        | -- RSocket SETUP frame ------------------> |
        |    data mime type                          |
        |    metadata mime type                      |
        |    optional auth metadata                  |
        |                                            |
        | -- REQUEST_RESPONSE route=demo.echo -----> |
        |<-------------- PAYLOAD response ---------- |
        |                                            |
        | -- REQUEST_STREAM route=demo.stream -----> |
        |<------------- PAYLOAD item 1 ------------- |
        |<------------- PAYLOAD item 2 ------------- |
        | ---- REQUEST_N demand/cancel, ... -------> |
        |<------------- PAYLOAD item N ------------- |
```

RSocket messages have separate **data** and **metadata**. Routes are typically sent via routing metadata; authentication information is sent using the metadata type per the Authentication Metadata Extension. **Do not put credentials into the data payload and expect the RSocket Security DSL to recognize them automatically**.

RSocket SETUP is connection-level, not an HTTP login endpoint. With TCP transport, there is no HTTP URL/method/status in individual RSocket requests at all. With WebSocket, there is only an **HTTP upgrade handshake** when opening the connection; afterward, application messages are still RSocket frames.

### 2.2. Backpressure is not authorization

In Request-Stream and Request-Channel, `REQUEST_N` indicates how many messages the consumer is requesting; `CANCEL` cancels the stream. This mechanism prevents the producer from sending infinitely when the consumer cannot keep up.

It **does not check** whether the Nth item is still permitted to be viewed when a role has just been revoked. Nor does it check which tenant a record belongs to. You must separate:
- **Transport flow control:** demand/cancel, memory limits, payload limits;
- **Authentication:** credentials at SETUP/request;
- **Authorization:** role/route/resource/tenant;
- **Continuous policy:** expiry/revocation and stream lifetime when needed;
- **Data isolation:** filtering data by user/tenant before fan-out.

An initially accepted stream can run for minutes or hours; checking permissions once does not automatically handle all subsequent permission changes.

## 3. How do HTTP WebFlux Security and RSocket Security differ?

| Aspect | HTTP WebFlux | RSocket |
| --- | --- | --- |
| Transport | HTTP/1.1, HTTP/2 (depending on server) | TCP or RSocket-over-WebSocket |
| Security integration | `WebFilterChainProxy`, `SecurityWebFilterChain`, `ServerHttpSecurity` | `SecuritySocketAcceptorInterceptor`/`PayloadSocketAcceptorInterceptor`, `RSocketSecurity` |
| Unit to inspect | HTTP exchange | RSocket SETUP, request payload exchange, route |
| Route identification | Path/method, e.g. GET `/api/orders/1` | Routing metadata, e.g. `orders.find` |
| Credentials | HTTP Authorization header, cookies, session, mTLS proxy... | Authentication metadata in SETUP/request, transport TLS/mTLS |
| AuthN | HTTP `AuthenticationWebFilter`/resource server flow | `AuthenticationPayloadInterceptor` via `ReactiveAuthenticationManager` |
| AuthZ | `authorizeExchange`, `ServerWebExchangeMatcher` | `authorizePayload`, `setup()`, `route()`, `anyRequest()` |
| Rejection result | HTTP 401/403, `WWW-Authenticate` | RSocket error frame/exception; **not HTTP 401/403** |
| Session storage | WebSession/Session cookie when configured | Connection-level context or per-request metadata, depending on design |
| Long streams | HTTP streaming/SSE over a single request | Request-Stream/Request-Channel with protocol demand |
| Per-item re-auth? | Does not automatically re-check each SSE event | Does not automatically re-check each RSocket PAYLOAD item |
| Browser CORS/CSRF | HTTP CORS/cookie-based CSRF | CORS affects the WebSocket/HTTP handshake at the appropriate layer; RSocket payloads have their own policy |
| Testing | `WebTestClient`, mock HTTP auth | `RSocketRequester`, StepVerifier, security metadata |
| Entry point | `@RestController`, HTTP handlers | `@Controller`/`@MessageMapping` RSocket responders |

**Do not use `@GetMapping` for RSocket routes** or `@MessageMapping` to block an HTTP path. Although both are Spring, the annotation handlers belong to two different messaging models.

### 3.1. Example of “HTTP is protected so RSocket is safe too” — wrong

```java
// HTTP SecurityWebFilterChain only protects HTTP exchanges.
@Bean
SecurityWebFilterChain httpSecurity(ServerHttpSecurity http) {
    return http.authorizeExchange(ex -> ex
            .pathMatchers("/api/**").authenticated()
            .anyExchange().permitAll())
        .build();
}
```

The code above **does not** create a policy for `RSocketRequester.route("admin.export")` sent over TCP. If the RSocket server opens a separate port, a client can connect directly to the RSocket port without ever calling `/api/**`. You must declare RSocket Security for the RSocket server.

### 3.2. RSocket-over-WebSocket is not identical to HTTP either

```text
Browser / RSocket client
   |
   | HTTP GET /rsocket + Upgrade: websocket
   v
WebFlux server: HTTP handshake/filter rules
   |
   | After upgrade succeeds
   v
RSocket SETUP + REQUEST_* + PAYLOAD frames
   |
   v
RSocket Security / @MessageMapping routes
```

If the HTTP handshake requires a cookie or Bearer token, that is the **first check layer**. It does not automatically make the `SecurityContext` of every RSocket message become the authenticated user, unless you have a **verified identity propagation integration**. Conversely, a `permitAll` handshake does not mean every RSocket route will be `permitAll` if RSocket Security is configured properly.

When using RSocket over WebSocket, you should check all of the following:
- Allowed origins, TLS `wss://`, proxy upgrade/idle timeouts;
- HTTP handshake authorization if needed;
- RSocket SETUP and route authorization;
- Credential forwarding/trust boundary between handshake and metadata;
- Reconnect and connection lifecycle.

## 4. Official Spring Security RSocket integration scope

Spring Security supports RSocket through `SocketAcceptorInterceptor`. `PayloadSocketAcceptorInterceptor` converts an RSocket interaction into a `PayloadExchange` for `PayloadInterceptor` instances to process. Key classes:

| Component | Role |
| --- | --- |
| `@EnableRSocketSecurity` | Enables Spring Security configuration infrastructure for RSocket |
| `RSocketSecurity` | RSocket authentication/authorization DSL |
| `PayloadSocketAcceptorInterceptor` | Aggregates security payload interceptors |
| `SecuritySocketAcceptorInterceptor` | Wires the security payload interceptor into the RSocket acceptor |
| `AuthenticationPayloadInterceptor` | Converts authentication metadata into an attempt and invokes the reactive manager |
| `AuthorizationPayloadInterceptor` | Invokes the reactive authorization manager for SETUP/request |
| `ReactiveAuthenticationManager` | Verifies credentials (simple or JWT accordingly) |
| `AuthenticationPayloadExchangeConverter` | Reads RSocket Simple Authentication metadata |
| `BearerPayloadExchangeConverter` | Reads RSocket Bearer Token Authentication metadata |
| `ReactiveJwtDecoder` | Validates JWT when using `.jwt(...)` |
| `RSocketRequester` | Spring Messaging requester; sends route/data/metadata |
| `@MessageMapping` | RSocket route handler in an annotated responder |
| `RSocketMessageHandler` | Dispatches messages to handlers |

Spring Boot provides `RSocketSecurityAutoConfiguration` to wire `SecuritySocketAcceptorInterceptor` into the RSocket server when the appropriate dependencies/beans are present. **When using Spring Boot auto-configuration, do not manually add a second interceptor unless you know why it is needed**, to avoid running auth logic twice. In a plain non-Boot setup, you must connect the security interceptor to the RSocket server using the corresponding RSocket server customizer API.

### 4.1. Basic DSL

```java
@Bean
PayloadSocketAcceptorInterceptor rsocketInterceptor(
        RSocketSecurity rsocket) {
    return rsocket
        .authorizePayload(auth -> auth
            .anyRequest().authenticated()
            .anyExchange().permitAll())
        .simpleAuthentication(Customizer.withDefaults())
        .build();
}
```

This is an **illustrative configuration snippet**, not a complete class. It tells RSocket Security how to decode Simple Authentication metadata and require authentication for request exchanges carrying routing metadata. There is no HTTP `SecurityWebFilterChain` in this DSL.

### 4.2. Rules must follow order

```java
rsocket.authorizePayload(auth -> auth
    .setup().hasRole("SETUP")
    .route("admin.*").hasRole("ADMIN")
    .route("events.stream").hasRole("STREAM")
    .anyRequest().authenticated()
    .anyExchange().permitAll());
```

Meaning:
- `setup()`: checks connection SETUP; can require a dedicated role for callers allowed to open a connection.
- `route("admin.*")`: checks specific route metadata, here admin-style routes.
- `route("events.stream")`: permission for requests with the corresponding route.
- `anyRequest()`: fallback for requests not matched by preceding routes.
- `anyExchange()`: fallback for exchanges not belonging to the preceding groups; in this example typically permits payload frames without route metadata.

**The first matching rule wins**; rules do not accumulate. If you put `anyRequest().permitAll()` before `route("admin.*").hasRole("ADMIN")`, the admin route can be left open unintentionally.

**Why is `anyExchange().permitAll()` at the end?** A request-stream/request-channel consists of multiple payloads, and not every payload/frame carries route metadata like the initial request. Placing `anyExchange().denyAll()` carelessly can break subsequent frames of a stream. This **does not** allow an unauthenticated initial request: `anyRequest()` protects request initiation that has a route. However, you must verify behavior with every frame type in a real application.

### 4.3. Protecting both SETUP and requests at the same time

Three patterns:
1. **SETUP authentication**: the connection is bound to a single caller, suitable when the connection belongs to one user/service.
2. **Per-request authentication**: the connection is shared across multiple users; each request carries its own metadata.
3. **Combined**: SETUP verifies an application/service identity with role `SETUP`, while each request verifies a different user identity/scope.

Approach 3 is often useful when a gateway/server application opens a shared RSocket connection while serving multiple end users. If you only authenticate SETUP with the service's credentials and all requests reuse the connection, you **cannot** conclude that the caller of each request is the actual end user.

## 5. Authentication at SETUP vs. per-request

### 5.1. SETUP authentication

```text
Client alice
  -> TCP connect
  -> SETUP(authentication metadata: alice/password or bearer token)
  -> Server verifies and binds identity at connection scope
  -> Request 1, request 2, request-stream reuse the established connection
```

Suitable for:
- Personal mobile app connections;
- A dedicated service account per connection;
- Streams where the connection has the same identity throughout its lifetime;
- Preventing callers without a specific authority from opening an RSocket connection.

Limitations:
- Credentials can expire **after setup succeeds**.
- Roles/tenants can change while the connection remains open.
- If multiple users share the connection, the setup identity is insufficient to distinguish individual users.
- Do not cache `Authentication` globally across all connections.

**Do not assume** Spring Security automatically re-runs JWT verification on every PAYLOAD just because the token expires mid-stream; you need token lifetime/revalidation/reconnect policies and stream termination according to your threat model.

### 5.2. Request authentication

```text
An application connection opened with service credentials
  |
  +-- REQUEST route=orders.find
  |      auth metadata: end-user A
  |      -> token verify -> subject A
  |
  +-- REQUEST route=orders.find
  |      auth metadata: end-user B
  |      -> token verify -> subject B
  |
  +-- REQUEST_STREAM route=events
         auth metadata: end-user C on initial request
         -> followed by multiple PAYLOAD frames
```

In a Spring requester:

```java
// ILLUSTRATIVE SNIPPET, assuming requester and authMimeType are already configured.
return requester.route("orders.find")
        .metadata(bearerTokenMetadata, authMimeType)
        .data(orderId)
        .retrieveMono(OrderDto.class);
```

This is **per-request auth metadata**, not an HTTP `Authorization` header. If you send a user token at SETUP on a connection shared among all users, you can cause severe **identity leakage/cross-tenant authorization** issues.

### 5.3. Route authorization is different from data authorization

`.route("orders.find").hasAuthority("SCOPE_orders:read")` only checks the scope for the request type; the handler/service must still verify:
- Verified `sub`/client ID;
- Granted `tenant_id`;
- That the order belongs to the right tenant + owner;
- Applicable row-level policies/permissions;
- That payloads from another tenant are not emitted in a shared stream.

The RSocket Security DSL **does not automatically turn route parameters into ownership checks**.

## 6. Simple Authentication Metadata and JWT Metadata

### 6.1. Simple Authentication

The RSocket Simple Authentication Metadata Extension sends a username/password pair in metadata. To encode on the client, add:

```java
RSocketRequester.Builder builder = ...;

builder.rsocketStrategies(
    strategies -> strategies.encoder(new SimpleAuthenticationEncoder()));
```

Sending SETUP metadata:

```java
MimeType authMime = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

UsernamePasswordMetadata credentials =
    new UsernamePasswordMetadata("alice", "lab-only");

Mono<RSocketRequester> connection = builder
    .setupMetadata(credentials, authMime)
    .connectTcp("localhost", 7000);
```

**Very important:** Simple Authentication metadata **does not encrypt the username/password secret**. If transported over cleartext TCP, credentials can be observed on the network. The lab below intentionally binds RSocket TCP to `127.0.0.1` and uses sample users/passwords. **Production must use TLS/mTLS or an appropriate secure transport**, password management, and rate limiting. Do not copy cleartext TCP lab settings for cross-host traffic.

`RSocketSecurity.basicAuthentication(...)` is an older mechanism replaced by `simpleAuthentication(...)` in newer Spring Security versions. Do not copy `BasicAuthenticationEncoder` samples from legacy docs into 6.3 without checking compatibility.

### 6.2. JWT Bearer Authentication Metadata

RSocket Security supports the Bearer Token Authentication Metadata Extension for JWT. On the receiver:

```java
// CONFIGURATION SNIPPET: inside a dedicated RSocketSecurity bean.
rsocket
    .authorizePayload(auth -> auth
        .anyRequest().authenticated()
        .anyExchange().permitAll())
    .jwt(Customizer.withDefaults());
```

You need a `ReactiveJwtDecoder` configured with issuer/signature/JWK, timestamp validator, and an **audience appropriate for the RSocket service**. Refer to Spring Security JWT Resource Server documentation to build the decoder; however, **an HTTP `oauth2ResourceServer().jwt()` bean is not a substitute for configuring `RSocketSecurity.jwt(...)`**.

On the requester:

```java
MimeType authMime = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

BearerTokenMetadata token =
    new BearerTokenMetadata("JWT_ACCESS_TOKEN_VALUE");

// Per connection:
Mono<RSocketRequester> connection = builder
    .setupMetadata(token, authMime)
    .connectTcp("localhost", 7000);

// Or per request:
Flux<Event> events = requester
    .route("events.stream")
    .metadata(token, authMime)
    .retrieveFlux(Event.class);
```

The snippets above are **illustrative fragments**, without a real JWT or `Event` model. Only use an **access token** with the proper audience/scopes/issuer; do not arbitrarily use an ID token as a bearer credential. Do not store JWTs in logs, traces, or raw error messages. For multi-tenant systems, tokens must be validated and mapped properly.

### 6.3. Which metadata type?

The RSocket Authentication Metadata Extension uses the well-known MIME `message/x.rsocket.authentication.v0` for the authentication metadata wrapper, with Simple/Bearer subtypes inside; Spring Security provides `UsernamePasswordMetadata` and `BearerTokenMetadata`. Do not attach metadata under an arbitrary content MIME or place the token in a JSON body expecting the framework to decode it automatically.

### 6.4. Request-time JWT is not automatic refresh

If a token expires before a subsequent request starts, that request must be rejected if the decoder/validator is checking properly. However, **an active request stream does not mean each PAYLOAD frame will automatically resend the JWT and re-check `exp`**. If fast revocation is needed:
- Limit maximum stream duration or connection TTL;
- Force reconnect/re-authentication after an interval;
- Check entitlements at the time sensitive data is emitted;
- Cancel streams if the user/tenant is revoked by policy;
- Design cache invalidation and propagate revocation events from the authoritative source;
- Do not use an infinite `Flux.interval` while forgetting quotas/cancellation.

## 7. Java 17+ example running two protocols in the same application

**Demo goal:** HTTP WebFlux on port 8080, RSocket TCP on port 7000. The same `MapReactiveUserDetailsService` stores two users, but with two different policies:

| User | Password (lab) | Granted role | HTTP `/http/private` | RSocket `demo.echo` | RSocket `demo.stream` |
| --- | --- | --- | --- | --- | --- |
| `alice` | `lab-only` | `ROLE_STREAM` | 403 | Allowed | Allowed |
| `bob` | `lab-only` | `ROLE_WEB` | Allowed | Allowed | Denied |
| Anonymous | None | None | 401 | SETUP rejected | Cannot reach route |

This very difference shows that **the identity store can be shared, but HTTP and RSocket policies are not automatically shared**. The RSocket lab uses authentication at SETUP; per-request testing will have separate guidance later.

### 7.1. Structure

```text
webflux-rsocket-boundaries/
  settings.gradle
  build.gradle
  src/main/resources/application.yml
  src/main/java/example/boundaries/
    BoundariesApplication.java
    IdentityConfig.java
    HttpSecurityConfig.java
    RSocketSecurityConfig.java
    HttpRoutes.java
    RSocketRoutes.java
  src/test/java/example/boundaries/
    SecurityBoundaryTests.java
```

Java classes are in the same package `example.boundaries`. Avoid using `@RestController` for RSocket handlers: `@MessageMapping` belongs to Spring Messaging.

### 7.2. settings.gradle

```groovy
rootProject.name = 'webflux-rsocket-boundaries'
```

### 7.3. build.gradle

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

    // RSocket Security is a separate module, not just
    // adding starter-security / HTTP resource-server.
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

`spring-boot-starter-rsocket` provides RSocket transport/messaging. `spring-security-rsocket` is the module implementing RSocket Security; `spring-security-messaging` provides related messaging security infrastructure. `spring-boot-starter-webflux` is standalone HTTP WebFlux. Use the Spring Boot BOM rather than arbitrarily mixing different Spring Security versions.

### 7.4. application.yml

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

Here RSocket TCP runs **without HTTP** on port 7000, while WebFlux handles HTTP on port 8080. Both ports are bound to localhost to reduce risk from the cleartext Simple Authentication demo. Production requires TLS and network policies; do not simply expose this port to the Internet.

### 7.5. BoundariesApplication.java

```java
package example.boundaries;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundariesApplication {

    public static void main(String[] args) {
        SpringApplication.run(BoundariesApplication.class, args);
    }
}
```

### 7.6. IdentityConfig.java

```java
package example.boundaries;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;

@Configuration
public class IdentityConfig {

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}lab-only")
                .roles("STREAM")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password("{noop}lab-only")
                .roles("WEB")
                .build();

        return new MapReactiveUserDetailsService(alice, bob);
    }
}
```

`{noop}` is for lab use only; it does not hash passwords and does not protect against brute force. Do not use hardcoded passwords or an in-memory user store in public deployments. Production requires a proper password encoder, account lockout/rate limiting, and a trusted identity provider.

User `alice` has `ROLE_STREAM`, and `bob` has `ROLE_WEB`. The user store data is used to verify credentials, but **HTTP SecurityConfig and RSocketSecurityConfig decide permissions separately**.

### 7.7. HttpSecurityConfig.java

```java
package example.boundaries;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class HttpSecurityConfig {

    @Bean
    SecurityWebFilterChain webfluxSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                HttpMethod.GET, "/public/ping")
                        .permitAll()
                        .pathMatchers(
                                HttpMethod.GET, "/http/private")
                        .hasRole("WEB")
                        .anyExchange().denyAll())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

**HTTP** policy:
- `GET /public/ping`: anonymous 200.
- `GET /http/private`: role WEB → bob 200; alice 403; missing credentials 401.
- HTTP Basic authentication is only used to demonstrate independent policies; production requires HTTPS, rate limiting, and an appropriate auth scheme.
- `anyExchange().denyAll()` blocks HTTP routes outside the lesson scope.
- Do not declare any `RSocketSecurity` here: the HTTP WebFilterChain does not match `demo.echo` or `demo.stream` as metadata routes.

### 7.8. RSocketSecurityConfig.java

```java
package example.boundaries;

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
                .authorizePayload(authorize -> authorize
                        // Require authentication when opening a connection.
                        .setup().authenticated()

                        // Route demo.echo requires a valid user.
                        .route("demo.echo").authenticated()

                        // Stream route is only for ROLE_STREAM.
                        .route("demo.stream").hasRole("STREAM")

                        // Other requests are denied by default.
                        .anyRequest().denyAll()

                        // Frames without route metadata
                        // within an already-started interaction.
                        .anyExchange().permitAll())
                .simpleAuthentication(withDefaults())
                .build();
    }
}
```

**Detailed explanation:**

1. `@EnableRSocketSecurity` enables building the RSocket-specific DSL.
2. `PayloadSocketAcceptorInterceptor` is attached to the RSocket acceptor by Spring Boot when the right dependencies/auto-configuration are present; no need to manually declare a global HTTP WebFilter.
3. `.setup().authenticated()` requires Simple Authentication metadata right at SETUP. Do not confuse with Spring WebFlux HTTP Basic cookies/sessions.
4. `.route("demo.echo").authenticated()` allows both `alice` and `bob` to call the route.
5. `.route("demo.stream").hasRole("STREAM")` allows only `alice` to open the request stream.
6. `.anyRequest().denyAll()` disallows unlisted routes, even if SETUP is already authenticated.
7. `.anyExchange().permitAll()` allows payload exchanges that are not part of the initial request (not carrying routing metadata) to pass through, which is necessary for certain streaming frames. **This does not automatically open access to the `demo.stream` route**.
8. `.simpleAuthentication(withDefaults())` enables handling RSocket Simple Authentication metadata via the reactive authentication infrastructure. The user store lives in the `IdentityConfig` bean.
9. Rules run in order, first-match-wins. Do not put `anyRequest().permitAll()` before a restricted route.
10. Route security only checks the action type and role; data with an owner/tenant still needs checking in the service.

### 7.9. HttpRoutes.java

```java
package example.boundaries;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HttpRoutes {

    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("message", "HTTP-PONG");
    }

    @GetMapping("/http/private")
    public Map<String, String> privateInfo() {
        return Map.of("message", "HTTP-WEB-ONLY");
    }
}
```

This is a real HTTP controller running on `http://127.0.0.1:8080`. `@GetMapping` does not define an RSocket route. There are no HTTP request handlers `/demo.echo` or `/demo.stream`.

### 7.10. RSocketRoutes.java

```java
package example.boundaries;

import java.time.Duration;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class RSocketRoutes {

    @MessageMapping("demo.echo")
    public Mono<String> echo(@Payload String name) {
        return Mono.just("echo:" + name);
    }

    @MessageMapping("demo.stream")
    public Flux<String> stream(@Payload Integer requestedCount) {
        int n = Math.max(0, Math.min(
                requestedCount == null ? 0 : requestedCount, 5));

        return Flux.range(1, n)
                .delayElements(Duration.ofMillis(150))
                .map(index -> "event-" + index);
    }
}
```

Explanation:
- `@MessageMapping("demo.echo")` handles RSocket Request-Response, returning `Mono<String>`.
- `@MessageMapping("demo.stream")` handles RSocket Request-Stream, returning `Flux<String>`.
- `@Payload` extracts message data, not an `Authorization` header.
- `requestedCount` is clamped from 0 to 5 so the demo does not generate an infinite stream from arbitrary input.
- `Flux.range(...).delayElements(...)` simulates steady events; this is **not** a production business stream.
- Route authorization has already run before the handler, but if the stream contains tenant-sensitive data, the handler/service must still filter every record by the verified identity's tenant/owner.
- Do not call `block()` or manually `subscribe()` inside the responder.

### 7.11. Running the server

Requires JDK 17+ and Gradle compatible with Spring Boot 3.3.13. From the project directory:

```bash
gradle bootRun
```

If using the Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows uses `gradlew.bat bootRun`. The application has two listeners:
- HTTP WebFlux: `127.0.0.1:8080`.
- RSocket TCP: `127.0.0.1:7000`.

**Do not use browser URL `http://127.0.0.1:7000` to test RSocket**: it is a binary TCP protocol, not HTTP. Use `RSocketRequester` or an RSocket-capable client.

### 7.12. Testing HTTP

```bash
curl -i http://127.0.0.1:8080/public/ping
curl -i http://127.0.0.1:8080/http/private
curl -i -u bob:lab-only \
  http://127.0.0.1:8080/http/private
curl -i -u alice:lab-only \
  http://127.0.0.1:8080/http/private
```

**Expected** results:
1. Public ping → HTTP 200 and `{"message":"HTTP-PONG"}`.
2. Private without header → HTTP 401 with Basic challenge.
3. Bob with right password + ROLE_WEB → HTTP 200 and `{"message":"HTTP-WEB-ONLY"}`.
4. Alice with right password but missing ROLE_WEB → HTTP 403.

Responses may include additional headers from Spring Security/Netty. Do not use hardcoded usernames/passwords or cleartext HTTP outside a localhost lab.

## 8. Full testing of both security chains

This test suite uses a **real Java RSocket client**, not `mockJwt()` or an HTTP test simulating RSocket. We use:
- `WebTestClient` to test HTTP;
- `RSocketRequester.Builder` connecting via RSocket TCP and sending Simple Authentication metadata;
- `StepVerifier` to verify async success/error and stream sequences;
- `@LocalRSocketServerPort` to avoid depending on port 7000 in CI runs.

### 8.1. SecurityBoundaryTests.java

Create `src/test/java/example/boundaries/SecurityBoundaryTests.java`:

```java
package example.boundaries;

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
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.rsocket.server.port=0")
@AutoConfigureWebTestClient
class SecurityBoundaryTests {

    private static final MimeType AUTH_MIME =
            MimeTypeUtils.parseMimeType(
                    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION
                            .getString());

    @Autowired
    WebTestClient http;

    @Autowired
    ObjectProvider<RSocketRequester.Builder> requesterBuilders;

    @LocalRSocketServerPort
    int rsocketPort;

    private Mono<RSocketRequester> connect(
            String username, String password) {
        return requesterBuilders.getObject()
                .rsocketStrategies(strategies ->
                        strategies.encoder(
                                new SimpleAuthenticationEncoder()))
                .setupMetadata(
                        new UsernamePasswordMetadata(
                                username, password),
                        AUTH_MIME)
                .connectTcp("127.0.0.1", rsocketPort);
    }

    @Test
    void publicHttpRouteIsOpen() {
        http.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("HTTP-PONG");
    }

    @Test
    void anonymousHttpPrivateRouteIs401() {
        http.get().uri("/http/private")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().exists(
                        HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void bobCanUseHttpPrivateRoute() {
        http.get().uri("/http/private")
                .headers(h -> h.setBasicAuth("bob", "lab-only"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message")
                .isEqualTo("HTTP-WEB-ONLY");
    }

    @Test
    void aliceHasRSocketRoleButNotHttpRole() {
        http.get().uri("/http/private")
                .headers(h -> h.setBasicAuth("alice", "lab-only"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void aliceCanEchoViaRSocket() {
        StepVerifier.create(
                connect("alice", "lab-only")
                        .flatMap(requester -> requester
                                .route("demo.echo")
                                .data("Java")
                                .retrieveMono(String.class)
                                .doFinally(signal ->
                                        requester.rsocket().dispose())))
                .assertNext(value ->
                        assertEquals("echo:Java", value))
                .verifyComplete();
    }

    @Test
    void aliceCanOpenThreeItemStream() {
        StepVerifier.create(
                connect("alice", "lab-only")
                        .flatMapMany(requester -> requester
                                .route("demo.stream")
                                .data(3)
                                .retrieveFlux(String.class)
                                .doFinally(signal ->
                                        requester.rsocket().dispose())))
                .expectNext("event-1", "event-2", "event-3")
                .expectComplete()
                .verify(Duration.ofSeconds(15));
    }

    @Test
    void bobCanEchoButCannotOpenProtectedStream() {
        StepVerifier.create(
                connect("bob", "lab-only")
                        .flatMapMany(requester -> requester
                                .route("demo.stream")
                                .data(2)
                                .retrieveFlux(String.class)
                                .doFinally(signal ->
                                        requester.rsocket().dispose())))
                .expectError()
                .verify(Duration.ofSeconds(15));
    }

    @Test
    void wrongSetupPasswordIsRejected() {
        StepVerifier.create(
                connect("alice", "incorrect-password")
                        .flatMap(requester -> requester
                                .route("demo.echo")
                                .data("test")
                                .retrieveMono(String.class)
                                .doFinally(signal ->
                                        requester.rsocket().dispose())))
                .expectError()
                .verify(Duration.ofSeconds(15));
    }

    @Test
    void missingSetupCredentialsAreRejected() {
        StepVerifier.create(
                requesterBuilders.getObject()
                        .connectTcp("127.0.0.1", rsocketPort)
                        .flatMap(requester -> requester
                                .route("demo.echo")
                                .data("test")
                                .retrieveMono(String.class)
                                .doFinally(signal ->
                                        requester.rsocket().dispose())))
                .expectError()
                .verify(Duration.ofSeconds(15));
    }

    @Test
    void unknownRouteDeniedEvenForAlice() {
        StepVerifier.create(
                connect("alice", "lab-only")
                        .flatMap(requester -> requester
                                .route("demo.not-registered")
                                .data("test")
                                .retrieveMono(String.class)
                                .doFinally(signal ->
                                        requester.rsocket().dispose())))
                .expectError()
                .verify(Duration.ofSeconds(15));
    }
}
```

The tests above **do not** assert the exact message/class of the RSocket exception; different Spring/RSocket versions may encode `REJECTED_SETUP`, `REJECTED`, `APPLICATION_ERROR`, or another wrapper. The security invariant is that **the RSocket requester receives an error and must not receive protected data**.

**Why use `ObjectProvider<RSocketRequester.Builder>`?** The builder provided by Boot is prototype/stateful. Calling `getObject()` each time retrieves a fresh builder, preventing `alice`'s credentials from remaining stored when testing `bob` on the same builder. That is also an important lesson for multi-user applications.

**Limitations:** The tests use cleartext localhost TCP and do not prove TLS/production certificates, multi-tenant record filtering, timeout/keepalive/load, or midstream revocation. Those require separate tests. `WebTestClient` only tests the HTTP `SecurityWebFilterChain`; it does not "send RSocket" on behalf of `RSocketRequester`.

### 8.2. Running tests

```bash
gradle test
```

With the Gradle Wrapper:

```bash
./gradlew test
```

If running the real server on port 7000 at the same time, the RSocket tests use a dynamic port thanks to `spring.rsocket.server.port=0` and `@LocalRSocketServerPort`, avoiding conflicts. HTTP tests use `RANDOM_PORT`. To run just the class:

```bash
./gradlew test --tests example.boundaries.SecurityBoundaryTests
```

**Reading results properly:** HTTP 401/403 are HTTP responses. RSocket rejections are RSocket protocol error signals, with no HTTP 403 status. Do not test a TCP RSocket system by sending `curl -i` to port 7000.

## 9. RSocket-over-WebSocket: same WebFlux server, different security layer

In a WebFlux application, instead of a separate RSocket TCP port, Boot can have RSocket use the WebSocket transport at `/rsocket`.

**Replacement YAML snippet** for `application.yml` in section 7:

```yaml
server:
  port: 8080

spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
```

When the RSocket server attaches to the WebFlux web server, do not simultaneously assume TCP port 7000 and a WebSocket path. `mapping-path` applies only to the WebSocket transport. Boot supports this topology when the app is reactive WebFlux and the web server uses Reactor Netty.

A client can connect:

```java
// ILLUSTRATIVE SNIPPET: must configure the requester's
// authentication metadata and transport security.
RSocketRequester requester =
        RSocketRequester.builder()
                .webSocket(
                        URI.create("ws://localhost:8080/rsocket"));
```

This is a cleartext lab. Production uses `wss://`, trusted HTTPS certificates, origin allowlists, and WebSocket upgrade policies. Even though the handshake is an HTTP GET, **the `demo.stream` route metadata still requires RSocket Security**.

### 9.1. Why checking only the handshake is not enough

A WebSocket connection can be very long-lived. If HTTP Security allows the handshake when a browser has a session/cookie, afterward Spring WebFlux request filters **are not automatically invoked again** for each RSocket message. You must determine:
- Where the RSocket client's identity comes from: SETUP metadata, per-request metadata, or an explicitly designed trusted handshake bridge;
- If the browser session logs out mid-session, whether the open connection is terminated;
- If the WebSocket is reconnected by a proxy, how the client re-sends credentials;
- If the same connection serves multiple users, whether user-specific credentials are sent on every request;
- If cookies are exposed to CSRF/cross-site WebSocket hijacking, whether origin checks and session policies are adequate.

**Do not automatically equate** the `SecurityContextHolder`/`ReactiveSecurityContextHolder` of the HTTP upgrade with the context of RSocket payloads unless there is a properly implemented and tested propagation integration.

### 9.2. CORS is not RSocket authorization

CORS is a browser mechanism for HTTP cross-origin requests. RSocket over WebSocket has an HTTP handshake and distinct origin/WebSocket rules; however, request-level RSocket route auth must still verify credentials through the RSocket security layer.

Do not enable wildcard CORS or open WebSocket to all origins just to bypass connection errors. Gateways/proxies also need to support `Upgrade`, timeouts, and appropriate frame sizes.

## 10. Securing long streams: harder than checking a single request

### 10.1. Authorization at stream start does not guarantee forever

Suppose `alice` has `ROLE_STREAM` and opens `demo.stream` or a production stream lasting 2 hours. After 10 minutes, an admin revokes the role.

If RSocket Security only checks at SETUP/request initiation, the stream can keep running because the earlier permission decision was already accepted. **The framework does not automatically issue a new authentication request before every event**.

Strategies depending on requirements:
- Cap stream lifetime and force reauthentication after `maxDuration`.
- Periodically re-check entitlements/revocation via a nonblocking service.
- Cancel active subscriptions upon receiving user/tenant revoked events.
- Prevent a broker/topic from emitting tenant B data into tenant A's stream.
- Use bounded queues/backpressure/bulkheads to avoid memory exhaustion.
- Enforce downstream fan-out security per subscription.
- Define clear reconnect policies and token refresh/credential renewal.

**Do not use an unbounded `Flux.interval(Duration.ZERO)` without quotas/cancellation**, especially when streaming sensitive data. Also do not call a blocking DB inside a handler `map` on the Netty event loop; use reactive repositories or appropriate schedulers/bulkheads.

### 10.2. Backpressure and cancellation

RSocket Request-Stream communicates demand via `REQUEST_N`. If the caller only needs three items and uses `take(3)`, the producer must observe cancellation and release resources.

```java
// ILLUSTRATIVE SNIPPET inside a service.
return eventRepository.watch(verifiedTenantId)
        .filter(event -> event.allowedFor(verifiedSubject))
        .take(Duration.ofMinutes(5))
        .doFinally(signal -> auditSubscriptionClosed(signal));
```

This is a fragment; repository/event, audit logic, and imports must be defined. `verifiedTenantId`/`verifiedSubject` **must** come from verified Authentication/claims, not verbatim from the RSocket payload sent by the caller. Route-based authorization alone does not prevent data leaks if the service subscribes to the wrong topic.

### 10.3. One connection, many logical streams

Multiplexing means a single RSocket connection can concurrently carry:
- A request-stream for user A;
- A request-response for user B;
- A channel between two services;
- Event subscriptions for multiple tenants.

If you use user A's SETUP credentials as a shared `Authentication` and omit per-request metadata for user B, you can **mix up identities** across streams. For shared connection pools, design per-request bearer/JWT metadata or a token exchange/gateway model ensuring each request has the right principal.

Avoid caching an `Authentication` or an `RSocketRequester.Builder` with mutable credential state and sharing it across all users.

### 10.4. Request-Channel does not treat every message as a new request

RSocket Request-Channel allows both sides to send a `Flux` of data. Route/credentials may be on the **initial request**; subsequent PAYLOAD frames do not automatically carry new credentials.

When a channel contains multiple events with different owners:
- Validate identity when starting the channel;
- Enforce data policies on each event if required by the threat model;
- Validate type/schema/size of inbound payloads;
- Limit total items, rate, and idle timeout;
- Cancel the channel on revocation or policy expiration;
- Do not turn `anyExchange().permitAll()` into "skip all permissions on subsequent messages." It is only a routing-level fallback; application-level validation is still required.

### 10.5. RSocket errors differ from HTTP

HTTP WebFlux has status lines `401 Unauthorized`/`403 Forbidden` and optionally `WWW-Authenticate`.

RSocket returns an **error frame** with the appropriate error code/exception type:
- Invalid SETUP may be rejected while the connection is being established;
- Requests with insufficient roles receive an error signal;
- An already-started request-stream can be terminated with an error frame;
- Reconnection and retry policies must depend on the error type, never infinitely retrying invalid credentials.

RSocket tests should assert `StepVerifier.expectError()` and ensure no protected items are received. If a product client needs to distinguish authentication failure from permission failure, build an appropriate error contract rather than arbitrarily faking HTTP status codes inside payloads.

## 11. HTTP SSE, WebSocket, and RSocket: which to choose?

| Need | HTTP streaming/SSE WebFlux | WebSocket | RSocket |
| --- | --- | --- | --- |
| Unidirectional server → browser | SSE is natural | Possible | Request-Stream |
| Continuous bidirectional | Unnatural in a single HTTP request | Yes | Request-Channel |
| Native browser support | EventSource/fetch streaming | WebSocket API | Requires an RSocket client library |
| Request routing | URL/method | Custom message protocol | Metadata route |
| Built-in request/stream semantics | HTTP response stream | App-designed | Request-Response/Stream/Channel/FnF |
| Network backpressure | Reactive server and transport-dependent; not equivalent to RSocket REQUEST_N | App must manage flow manually | RSocket demand signaling |
| Spring default security | `SecurityWebFilterChain` for GET/SSE | HTTP handshake + custom message policy | `RSocketSecurity` for SETUP/request route |
| Where tokens live | HTTP Authorization/cookie | Handshake or app messages | SETUP/request auth metadata |
| Auto re-auth per item? | No | No | No |
| HTTP proxies/load balancers | Common | Needs upgrade/idle support | TCP/WebSocket-specific support |

**SSE is still an HTTP request.** Spring Security HTTP checks AuthN/AuthZ when the GET starts; afterward, events on the same response do not re-run `WebFilterChain`. This is **similar** to RSocket long-lived streams: if midstream revocation is needed, the app must design an additional mechanism.

**Plain WebSocket is not RSocket either.** WebSocket does not inherently define RSocket routes, request-response, or demand frames; if using RSocket-over-WebSocket, both client and server must understand the RSocket protocol on top of WebSocket.

## 12. JWT, issuer, audience, and authorization for RSocket

When using `rsocket.jwt(...)` for token-based auth:
- Configure `ReactiveJwtDecoder` to trust a specific issuer.
- Validate JWS signature, `exp`/`nbf`, allowed algorithms, and key rotation.
- **Validate the audience** for the RSocket service; matching issuer alone does not prove the token is meant for this server.
- Map scope → GrantedAuthority, e.g. `SCOPE_events:read`; roles are not automatically inferred from arbitrary custom claims.
- Perform tenant/owner checks in the message handler/service.
- Check whether `sub` represents a user or a service account, per issuer.
- Avoid using an OIDC ID Token as an access token for an RSocket Resource Server.

Example policy using a mapped authority:

```java
// ILLUSTRATIVE CONFIGURATION SNIPPET.
rsocket.authorizePayload(auth -> auth
    .setup().authenticated()
    .route("events.stream").hasAuthority("SCOPE_events:read")
    .anyRequest().denyAll()
    .anyExchange().permitAll());
```

**Do not** directly trust a `scope=events:read` field placed by the client in the RSocket data body; it must come from a verified token claim or a policy from a trusted service.

### 12.1. Token at SETUP vs. request

If the client uses JWT at setup:
- Credentials are typically verified upon connection;
- The connection may remain alive after token expiry unless a revalidation policy exists;
- Reconnect should fetch a valid token and re-run SETUP;
- Revocation must be pushed to connection/stream cancellation if rapid reflection is required.

If the client uses per-request JWT:
- Each new request can carry a fresh token;
- Suitable for a shared connection serving multiple users;
- Does not turn individual PAYLOAD events inside a request-stream into new request-level authentications;
- Must check cache/decoder/tenants and avoid logging tokens.

### 12.2. Do not use HTTP bearer header instead of RSocket auth metadata

```http
GET /rsocket
Authorization: Bearer <token>
Upgrade: websocket
```

This header (if present) belongs to the **WebSocket HTTP handshake**, not authentication metadata of RSocket SETUP or request messages. A Spring RSocket receiver does not automatically infer the user from it. If you want to pass identity between the handshake layer and RSocket, you must design a well-protected/well-tested bridge; usually it is simpler and clearer to send RSocket Bearer metadata per the security DSL.

## 13. Operational security: TLS, credentials, availability

### 13.1. Encryption of RSocket transport

- RSocket TCP cleartext: do not send real passwords/tokens over the network.
- RSocket TCP TLS: verify chain/hostname/SAN and use proper certificates/keystore/truststore.
- RSocket-over-WebSocket: use `wss://` with trusted TLS termination, check origins/proxies.
- For service-to-service, consider mTLS, network policies, and secrets rotation.
- TLS only protects transport and peer identity; **route authorization is still required**.

Spring Boot 3.3 provides RSocket server configuration such as `spring.rsocket.server.ssl.bundle`, but client RSocket TLS/mTLS setup must align with the transport, truststore, and deployment. Do not copy a `tcp://` URL and assume it encrypts automatically.

### 13.2. Connection limits and idle timeouts

RSocket multiplexing saves connections but easily creates long-lived high-load sessions:
- Limit connection counts and concurrent streams;
- Limit payload size and item counts;
- Set sensible keepalive/ping/idle timeouts to detect dead peers;
- Retry/reconnect with backoff/jitter, without spamming on invalid credentials;
- On reconnect, resend authentication metadata and re-check permissions;
- Enforce memory/buffer quotas/backpressure and cancellation;
- Clean up subscriptions on client disconnect;
- Plan sticky load balancing or state models if clustering is needed.

Do not assume that a user authenticated on node A has an "HTTP WebSession" on node B for RSocket TCP. The two protocols have different state storage lifecycles; multi-node architectures must design connection routing and state/identity persistence separately.

### 13.3. Observability without leaking secrets

Metrics to track:
- SETUP auth success/failure and denial categories;
- Per-route request allow/deny counts;
- Active connections/streams by service alias (do not use raw user emails);
- Request-Stream duration p95/p99;
- Cancellation, stream errors, backpressure/buffer pressure;
- JWT decoder latency/JWK/issuer errors if using tokens;
- Reconnect rates and invalid credential retries.

Do not log Simple password metadata, raw JWTs, raw RSocket frames containing secrets, session cookies, token headers, private keys, or full payloads of other tenants. Disable wiretap/body logging in production or redact thoroughly.

## 14. Common pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| HTTP `/public/ping` works, RSocket connect fails | TCP server 7000 not running / wrong port | Check `spring.rsocket.server.port`, network |
| HTTP is authenticated but RSocket SETUP is rejected | Two different mechanisms; metadata not sent | Send Simple/JWT RSocket auth metadata |
| RSocket route works even though HTTP `/http/private` returns 403 | Independent policies | Configure RSocket route roles separately |
| RSocket setup succeeds but stream route is rejected | Valid credentials, missing `ROLE_STREAM` | Check `RSocketSecurity` route permissions |
| Sending HTTP `Authorization: Bearer` to TCP 7000 | Protocol mismatch | Use `RSocketRequester`/metadata |
| Using `curl -i` on TCP 7000 | TCP is not HTTP | Use an RSocket client |
| Simple Authentication over public TCP | Credentials sent unencrypted | Enable TLS or secure transport, prefer standard tokens |
| WebSocket handshake 101 but RSocket route rejected | RSocket payload security is independent | Send/verify per-request or setup metadata |
| WebSocket handshake `permitAll` opens all RSocket routes | RSocket Security omitted | Enable/validate RSocket interceptor/policies |
| `.anyRequest().permitAll()` before restricted route | First matching rule wins | Place restrictive routes before catchall |
| `.anyExchange().denyAll()` breaks streams | Subsequent exchanges lack route metadata | Design fallback matching RSocket semantics |
| SETUP as user A, connection pool sends requests for B | Identity leakage | Per-request auth metadata, isolate connections |
| Token expired but stream keeps emitting events | Not revalidated per item | Stream TTL, revoke/cancel, periodic entitlement checks |
| Role revoked but connection still holds principal | Cached setup identity | Reconnect/revalidation/revocation invalidation |
| Valid JWT signature but for another service | Missing audience validator | Validate issuer + audience + scopes |
| Request stream sends another tenant's data | Only route protected, not resource | Filter tenant/owner in service/event source |
| HTTP WebFilter does not see RSocket routes | Two separate pipelines | Separate `SecurityWebFilterChain` + `RSocketSecurity` |
| Wildcard CORS to "fix" RSocket error | CORS is not RSocket AuthZ | Separate handshake/origin/metadata layers |
| `WebTestClient` cannot test RSocket | HTTP test tool | `RSocketRequester` + `StepVerifier` |
| RSocket error test lacks HTTP 401 | Errors are sent via RSocket frames | Assert error signal/protocol code |
| Long-lived connections never released | Forgot cancel/dispose/idle handling | Lifecycle hooks, timeouts, cleanup |

## 15. Production checklist

1. Identify the RSocket transport: TCP/TLS, WebSocket/WSS, and exposed ports/paths.
2. Enable the right RSocket Security modules and interceptor, tested against the actual deployment port/transport.
3. Maintain **separate policies** for HTTP WebFlux `SecurityWebFilterChain` and `RSocketSecurity`.
4. Decide clearly between SETUP authentication, per-request authentication, or both.
5. Avoid shared connections carrying a fixed user's credentials when multiplexing traffic for multiple users.
6. If using Simple Authentication, use it only over encrypted transport; avoid sample passwords.
7. If using JWT, verify signature, issuer, audience, `exp`/`nbf`, and service-appropriate authority mapping.
8. Protect sensitive RSocket routes with a restrictive allowlist and `anyRequest().denyAll()` where appropriate.
9. Verify `.anyExchange()` for subsequent stream/channel payloads; do not mistake it for bypassing AuthN.
10. Enforce tenant/owner/resource authorization in the service, not only route matching.
11. Have a policy for token expiry/revocation while long streams are open.
12. Cap stream lifetime, item rate, buffers/memory, concurrent subscribers, and connections.
13. Configure cancellation/cleanup and retry/reconnect with backoff; do not retry invalid credentials infinitely.
14. Use TLS/WSS/mTLS/ingress allowlists, verifying hostnames/certificates and origin rules.
15. Do not assume HTTP handshake authentication automatically transfers to RSocket payload identity.
16. Keep HTTP/WebSocket/RSocket error semantics separate; do not emit HTTP 401 inside TCP frames.
17. Do not log password metadata, raw JWTs, private keys, or sensitive raw stream payloads.
18. Test HTTP separately with `WebTestClient`; test RSocket separately with `RSocketRequester` + `StepVerifier`.
19. Test anonymous/wrong SETUP credentials, valid user missing role, unknown route, long-lived stream cancellation, and tenant leakage.
20. If multi-node, design sticky routing/connection lifecycle, shared state/revoke signals, and failover load tests.
21. When upgrading Spring Boot/Spring Security, re-check RSocket Security modules and RSocket transport APIs; do not copy Servlet HTTP configuration.
22. Maintain dashboards for auth failures, denied routes, stream durations, cancellation, buffer pressure, and active connections.

## 16. Self-check questions

**1. Does HTTP's `SecurityWebFilterChain` automatically protect the RSocket TCP port?**  
No. RSocket TCP is not an HTTP exchange. An RSocket Security policy is required at the acceptor.

**2. What entry point does RSocket Security use?**  
`@EnableRSocketSecurity` + `RSocketSecurity` builds a `PayloadSocketAcceptorInterceptor`, wired into the RSocket acceptor via Boot auto-configuration or an appropriate customizer.

**3. What is the biggest difference between `@GetMapping` and `@MessageMapping`?**  
`@GetMapping` routes HTTP path/method; `@MessageMapping` receives an RSocket route in messaging metadata.

**4. Are HTTP 401/403 how RSocket reports AuthN/AuthZ errors?**  
No. RSocket uses protocol error signals/frames/exceptions.

**5. When should you authenticate at SETUP?**  
When a connection belongs to a fixed user/service and policy allows the identity to live for the connection lifecycle.

**6. When is per-request metadata needed?**  
When a connection is shared across multiple end users, or when different identities/permissions are needed per request.

**7. Does RSocket SETUP auth automatically re-check tokens on every event?**  
Not by default. Long streams need duration caps and revalidation/revocation policies where required.

**8. Is Simple Authentication metadata encrypted?**  
No; TLS/WSS/secure transport is mandatory outside a localhost lab.

**9. Are JWTs in RSocket sent via an HTTP Authorization header or something else?**  
Normally via the RSocket Bearer Token Authentication Metadata Extension in SETUP/requests, not as an HTTP header on every message.

**10. Why are `anyRequest()` and `anyExchange()` different?**  
`anyRequest()` targets request exchanges that have routing metadata; `anyExchange()` also includes other exchanges, such as subsequent payloads without a route. Apply them according to frame/interaction semantics.

**11. If user `bob` has `ROLE_WEB`, why is RSocket `demo.stream` still denied?**  
Because the stream route requires `ROLE_STREAM`. A shared user store does not mean shared policies.

**12. `alice` has `ROLE_STREAM` but gets 403 on HTTP `/http/private`—is that a bug?**  
No. The HTTP route requires `ROLE_WEB`; the RSocket route requires `ROLE_STREAM`.

**13. Does `.route("admin.*").hasRole("ADMIN")` guarantee a user cannot access another tenant's data?**  
No. Tenant/ownership/resource-level checks belong in the service/data layer.

**14. What does backpressure guarantee, and what does it not guarantee?**  
It helps control stream rate/demand; it does not automatically guarantee authentication, authorization, revocation, or data isolation.

**15. RSocket over WebSocket already did a handshake with an HTTP cookie—does a protected route automatically have the user?**  
Not automatically. Verified identity propagation must be designed, or RSocket metadata auth must be used.

**16. Can `WebTestClient` be used to test RSocket TCP messages?**  
No. Use `RSocketRequester` and `StepVerifier`.

**17. Why shouldn't you share an `RSocketRequester.Builder` containing credentials across all users?**  
The builder is stateful; it easily sends the wrong user's credentials and causes cross-tenant leaks. Create builders/requesters with proper scoping, isolation, or per-request metadata.

**18. What happens if a token expires mid-request-stream?**  
There is no guarantee the framework will automatically stop the stream based solely on token expiry; policy must handle recheck/cancel/reconnect.

**19. What happens if `.anyRequest().permitAll()` is placed before a privileged route?**  
Because first-match-wins, the route can be left open unintentionally.

**20. Why must `ws://` not be confused with `wss://`?**  
`wss://` uses TLS; credentials in metadata can be exposed if transported in cleartext over the network.

**21. Can the same app run both HTTP and RSocket?**  
Yes. For example, HTTP port 8080 and RSocket TCP port 7000 or an RSocket-over-WebSocket path on WebFlux; each pipeline needs its own policy.

**22. Do SETUP errors and route errors come from different sources?**  
Yes. A SETUP failure usually rejects the connection, whereas a route authorization failure emits an error for the request; do not assume the same error code/class across all versions.

**23. When a client reconnects after a failure, does it need to re-authenticate?**  
Yes, because it is a new connection; send valid metadata, evaluate revocation/expiry, and do not retry invalid credentials infinitely.

**24. What is the role of `ReactiveJwtDecoder` when using RSocket JWT?**  
Verifying the token's signature/claims; `RSocketSecurity` `jwt(...)` coordinates with it to turn the token into a trusted `Authentication`.

**25. When is RSocket not the best choice?**  
If you only need standard HTTP APIs or simple one-way SSE; RSocket adds requirements around client libraries, proxies, monitoring, TLS, and connection lifecycle.

**26. Does an `@MessageMapping` returning `Flux` automatically protect every `Flux` element with a role check?**  
No. Route initiation is checked by the interceptor; the service must check permissions/resources for each element's data per your threat model.

**27. Can RSocket Security be omitted if the gateway already authenticated the handshake?**  
Only when trusted identity propagation and application-side authorization are explicitly designed, documented, and thoroughly tested; by default, do not omit this layer.

**28. Why is `@LocalRSocketServerPort` useful in CI?**  
It lets tests start the RSocket server on a dynamic port and inject the actual port, avoiding conflicts with other servers.

**29. Which test clearly distinguishes the two security layers?**  
Bob accesses HTTP `/http/private` successfully but is denied on RSocket `demo.stream`; conversely, Alice gets the RSocket stream but gets 403 on HTTP private.

**30. What should you remember when implementing request-channel for multiple tenants?**  
Route/credential metadata is not automatically sent on every item; you must check tenant/owner at the application level, limit streams, and handle revocation/cancellation.

**Remember:** **RSocket Security protects RSocket SETUP, request metadata, and routes; HTTP WebFlux Security protects HTTP exchanges.** Both can coexist in one Spring Boot app, but neither replaces the other. Use encrypted transport, send credentials in the right metadata, decide between connection vs. request authentication, order rules from specific to fallback, enforce data-level permissions, and design specifically for long streams.

## References

- [Spring Security — RSocket Security](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html): interceptors, SETUP vs request auth, Simple/Bearer metadata, `authorizePayload`.
- [Spring Security — RSocketSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html): `@EnableRSocketSecurity`, matcher DSL, and `PayloadSocketAcceptorInterceptor`.
- [Spring Security 6.3 — PayloadSocketAcceptorInterceptor API](https://docs.spring.io/spring-security/site/docs/6.3.6/api/org/springframework/security/rsocket/core/PayloadSocketAcceptorInterceptor.html): payload interceptors and socket acceptor.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain` and `ServerHttpSecurity`.
- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): TCP vs WebSocket RSocket server, `RSocketRequester.Builder`, annotated responders.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.rsocket.server.address`, port, transport, SSL.
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): interaction models, setup/request metadata, route matching, backpressure, annotated controllers.
- [Spring Boot 3.3 — LocalRSocketServerPort API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPort.html): RSocket server test port injection.
- [Spring Team — Getting Started with RSocket Security](https://spring.io/blog/2020/06/17/getting-started-with-rsocket-spring-security/): Simple Authentication metadata, setup/test patterns.
- [RSocket Protocol](https://rsocket.io/about/protocol/): SETUP, request-stream/channel, demand and error signals.
- [RSocket Authentication Metadata Extension](https://github.com/rsocket/rsocket/blob/master/Extensions/Security/Authentication.md): Simple/Bearer authentication metadata types.
- [Project Reactor — Reference](https://projectreactor.io/docs/core/release/reference/): backpressure, cancellation, Reactor Context.
